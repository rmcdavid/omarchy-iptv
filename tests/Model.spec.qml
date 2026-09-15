import QtQuick
import QtTest
import "../Model.js" as Model
import "fixtures/chno-cases.js" as ChnoCases
import "fixtures/pip-cases.js" as PipCases

// Proves Model.js loads inside the Qt QML engine (no ES module syntax, no
// node-only globals) and that the QML-side results match the node tests:
// normalization vectors, ranking tiers, the two-mode keyboard state machine,
// scope transitions, the zap ring, settings clamps and mpv argv.
// Run: QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml
TestCase {
  id: spec
  name: "IptvModel"

  // The chno values (M2-03 10.2) cover a duplicate pair (12 on two rows), a
  // subchannel (7.1 between 7 and 12), leading zeros (007 is 7), a channel
  // with no number at all and one whose number is unusable.
  readonly property var channels: Model.prepareChannels([
    { id: "1", name: "BBC One HD", group: "UK", searchKey: "bbc one hd uk", chno: "101" },
    { id: "2", name: "CBBC", group: "Kids", searchKey: "cbbc kids", chno: "007" },
    { id: "3", name: "One America", group: "US", searchKey: "one america us", chno: "12" },
    { id: "4", name: "Sky News", group: "News", searchKey: "sky news news", chno: "12" },
    { id: "5", name: "BBC Two", group: "UK", searchKey: "bbc two uk", chno: "7.1" },
    { id: "6", name: "The One Show", group: "UK", searchKey: "the one show uk" },
    { id: "7", name: "Rai Uno", group: "One World", searchKey: "rai uno one world", chno: "HD" }
  ])
  readonly property var chnoIndex: Model.buildChnoIndex(spec.channels)
  readonly property var userState: ({ version: 1, favorites: ["5", "1"], recents: [{ id: "4", name: "Sky News", at: 1 }], lastPlayed: null })

  // The two bindings of ARCHITECTURE-PLAYER.md 4.7 as Service.qml declares
  // them, including the null guard of spike caveat C3: the observer handle is
  // null between attempts, because a Quickshell Socket whose connect failed is
  // bricked for good and has to be replaced rather than re-armed.
  QtObject {
    id: liveness
    property var socket: null
    property bool playerPending: false
    property var nowPlaying: null
    readonly property bool playerUp: (liveness.socket !== null && liveness.socket.connected) || liveness.playerPending
    readonly property bool playing: liveness.playerUp && liveness.nowPlaying !== null
  }

  // ---- the lane-PB event router (design section 10) ----
  //
  // These cases used to replay a transcript through a COPY of Service.qml's
  // rules written here, because the rules were QML methods on a live Service
  // and nothing outside a running shell could call them. A copy is worth very
  // little: with the superseding rule deleted from the shipping
  // handlePlayerLine - every zap raising a false "did not play" - all four
  // cases still passed. So the rules moved into Model.js (M2-02-06 PR-4) and
  // this driver now calls them.
  //
  // What is left here is only what Service.qml itself is: the loop, the
  // property writes, and the notify call. Model.routePlayerEvent() per line
  // exactly as handlePlayerLine() does it, Model.endedReport() at EOF exactly
  // as handlePlayerGone() does it (which also clears the last end-file and
  // the entry id), Model.rememberEntryOwner() for the ring. "EOF" stands for
  // the socket closing, the only moment a toast can be raised. Break a rule
  // in Model.js and these cases go red without anyone editing them.
  function routePlayer(transcript) {
    var lines = transcript.lines || []
    var owners = transcript.owners || ({})
    var current = transcript.nowPlaying || null
    var state = Model.playerRouterState(null)
    var toasts = []
    for (var i = 0; i < lines.length; i++) {
      if (lines[i] === "EOF") {
        var report = Model.endedReport({
          lastEndFile: state.lastEndFile,
          owners: owners,
          nowPlaying: current,
          userStopped: transcript.userStopped === true,
          stopping: transcript.stopping === true,
          tail: state.tail
        })
        if (report.notify) toasts.push({ name: report.target ? String(report.target.name) : "", reason: report.reason })
        state = { entryId: 0, lastEndFile: null, idle: state.idle, tail: state.tail }
        continue
      }
      state = Model.routePlayerEvent(state, lines[i])
    }
    return { lastEndFile: state.lastEndFile, entryId: state.entryId, idle: state.idle, tail: state.tail, toasts: toasts }
  }

  // The entry-ownership ring as Service.qml rememberEntry() fills it: one
  // entry per `player start` / `play` reply, newest last.
  function ownersFor(pairs) {
    var owners = ({})
    for (var i = 0; i < pairs.length; i++) owners = Model.rememberEntryOwner(owners, pairs[i][0], pairs[i][1])
    return owners
  }

  function ids(rows) {
    var out = []
    for (var i = 0; i < rows.length; i++) out.push(rows[i].id)
    return out
  }

  function test_searchKey() {
    compare(Model.searchKey("BBC-One HD", "UK: News"), "bbc one hd uk news")
    compare(Model.searchKey("Télé Québec", ""), "tele quebec")
    compare(Model.searchKey("Kids TV", "Animation;Kids;Religious"), "kids tv animation kids religious")
  }

  function test_normalizeNfdAndScripts() {
    // String.prototype.normalize must exist in the Qt engine for NFD folding.
    compare(Model.normalizeText("Café NFD"), "cafe nfd")
    compare(Model.normalizeText("ÉCOLE"), "ecole")
    compare(Model.normalizeText("Первый канал"), "первый канал")
    compare(Model.normalizeText("NHK 総合"), "nhk 総合")
  }

  function test_fnv1a32() {
    compare(Model.fnv1a32(""), "811c9dc5")
    compare(Model.fnv1a32("a"), "e40c292c")
    compare(Model.fnv1a32("foobar"), "bf9cf968")
  }

  function test_channelId() {
    compare(Model.channelId({ tvgId: "bbc1.uk", url: "http://a" }), "t:bbc1.uk")
    compare(Model.channelId({ url: "foobar" }), "u:bf9cf968")
  }

  function test_displayNameNeverUrl() {
    var rows = Model.prepareChannels([{ name: "http://h.test/x", tvgName: "Arte", url: "http://h.test/x" }, { name: "", url: "u2" }])
    compare(rows[0].name, "Arte")
    compare(rows[1].name, "Channel 2")
  }

  function test_rankingTiers() {
    compare(ids(Model.filterChannels(channels, "one", 10).rows), ["3", "1", "6", "7"])
    // both BBC rows are favorites in userState: playlist order inside the tier
    compare(ids(Model.filterChannels(channels, "bbc", 10, userState).rows), ["1", "5", "2"])
    // a single favorite sorts first inside its tier, never above a better tier
    compare(ids(Model.filterChannels(channels, "bbc", 10, { favorites: ["5"] }).rows), ["5", "1", "2"])
    compare(ids(Model.filterChannels(channels, "bbc", 10, { favorites: ["2"] }).rows), ["1", "5", "2"])
    compare(ids(Model.filterChannels(channels, "bbc uk", 10).rows), ["1", "5"])
    // D-LIVE-01: the cap is for search results; an empty query browses every row.
    var browse = Model.filterChannels(channels, "", 2)
    compare(browse.total, 7)
    compare(browse.rows.length, 7)
    compare(browse.truncated, false)
    var capped = Model.filterChannels(channels, "b", 1)
    compare(capped.rows.length, 1)
    compare(capped.truncated, true)
    compare(Model.MAX_ROWS_DEFAULT, 200)
  }

  function test_ungroupedLastAndFallbackScope() {
    // D-LIVE-06: Ungrouped closes the column even when it appears first.
    var rows = Model.prepareChannels([{ name: "A", url: "1" }, { name: "B", group: "News", url: "2" }, { name: "C", group: "Kids", url: "3" }])
    var names = Model.groupChannels(rows).map(function(g) { return g.name })
    compare(names, ["News", "Kids", "Ungrouped"])
    // D-LIVE-07: an emptied Recent falls back to Favorites, else All.
    compare(Model.fallbackScope(Model.scopeEntries(channels, userState), "recent"), "recent")
    compare(Model.fallbackScope(Model.scopeEntries(channels, { version: 1, favorites: ["5"], recents: [], lastPlayed: null }), "recent"), "favorites")
    compare(Model.fallbackScope(Model.scopeEntries(channels, null), "recent"), "all")
  }

  function test_statusReasonTable() {
    // D-LIVE-03 / D-LIVE-11: terse reasons, no helper sentence, no seconds.
    compare(Model.statusReason({ ok: false, error: { code: "not_a_playlist", message: "source from h is not an M3U playlist" } }), "Not an M3U playlist")
    compare(Model.statusReason({ ok: false, error: { code: "timeout", message: "playlist download from h exceeded its deadline" } }), "Timed out")
    compare(Model.statusReason({ ok: false, error: { code: "network", message: "could not reach h: timed out" } }), "Timed out")
  }

  function test_scopeEntriesAndLists() {
    var entries = Model.scopeEntries(channels, userState)
    compare(entries[0].id, "recent")
    compare(entries[1].id, "favorites")
    compare(entries[1].count, 2)
    compare(entries[2].id, "all")
    compare(entries[3].kind, "header")
    compare(entries[4].id, "g:UK")
    compare(ids(Model.channelsForScope(channels, "favorites", userState)), ["5", "1"])
    compare(ids(Model.channelsForScope(channels, "g:UK", userState)), ["1", "5", "6"])
    compare(Model.moveScope(entries, "all", 1), "g:UK")
    compare(Model.moveScope(entries, "recent", -1), "g:One World")
    compare(Model.initialScope(channels, userState), "favorites")
    compare(Model.initialScope(channels, null), "all")
  }

  function test_keyboardStateMachine() {
    var g = Model.guideState("favorites")
    compare(g.mode, "search")
    g = Model.withQuery(g, "s")
    compare(g.scopeId, "all")
    compare(g.restoreScopeId, "favorites")
    g = Model.withQuery(g, "")
    compare(g.scopeId, "favorites")
    g = Model.toggleMode(g)
    compare(g.mode, "list")
    g = Model.withQuery(g, "bbc")
    var esc = Model.onEscape(g)
    compare(esc.close, false)
    compare(esc.state.query, "")
    compare(esc.state.mode, "list")
    esc = Model.onEscape(esc.state)
    compare(esc.close, true)
    compare(Model.withQuery(Model.guideState("g:UK"), "sky").scopeId, "g:UK")
    compare(Model.effectiveScope("recent", "x"), "all")
    compare(Model.moveCursor(0, -1, 5, true), 4)
    compare(Model.moveCursor(4, 10, 5, false), 4)
  }

  function test_zapRing() {
    compare(Model.launchScope("favorites", "", { group: "UK" }), "favorites")
    compare(Model.launchScope("recent", "", { group: "UK" }), "g:UK")
    compare(Model.launchScope("favorites", "sky", { group: "UK | SPORTS" }), "g:UK | SPORTS")
    compare(ids(Model.zapRing(channels, userState, { id: "5", group: "UK", launchedFrom: "favorites" })), ["5", "1"])
    compare(Model.nextInGroup(channels, "7", 1).id, "1")
    compare(Model.nextInGroup(channels, "1", -1).id, "7")
  }

  function test_state() {
    compare(Model.toggleFavorite(["a"], "b"), ["a", "b"])
    compare(Model.pushRecent([], { id: "x", name: "X" }, 10, 5), [{ id: "x", name: "X", at: 5 }])
    compare(Model.removeRecent({ version: 1, favorites: [], recents: [{ id: "x", name: "X", at: 1 }], lastPlayed: null }, "x").recents, [])
    compare(Model.parseState("garbage"), Model.emptyState())
  }

  function test_sessionRecord() {
    // ARCHITECTURE-PLAYER.md 4.6 / section 8 / PO-3: what the player was last
    // ASKED to play, so a shell that comes back to a dead player can mark that
    // row failed in the guide instead of toasting minutes after the fact.
    // Additive and nullable - STATE_VERSION stays 2 and a file without the key
    // reads as null, which is what an upgrade from v0.2.0 hands us.
    var played = Model.recordPlayed(Model.emptyState(), { tvgId: "bbc1.uk", name: "BBC One HD", url: "http://u:p@h.test/s.m3u8" }, 10, 1758000123)
    compare(played.session, { id: "t:bbc1.uk", name: "BBC One HD", at: 1758000123 })
    compare(JSON.stringify(played.session).indexOf("://"), -1)
    // The service writes JSON.stringify(userState, null, 2) and reads it back
    // through parseState: the key has to survive that round trip.
    compare(Model.parseState(JSON.stringify(played, null, 2)).session, played.session)
    compare(Model.parseState('{"version":2,"favorites":["a"]}').session, null)
    compare(Model.parseState('{"session":{"name":"no id"}}').session, null)
    compare(Model.parseState('{"session":{"id":"t:x","at":"7"}}').session, { id: "t:x", name: "", at: 7 })
    compare(Model.clearSession(played).session, null)
    compare(Model.clearSession(played).lastPlayed, played.session)   // Recents is untouched
    compare(Model.clearSession(Model.emptyState()).session, null)
    compare(Model.stateSession(played), played.session)
    compare(Model.stateSession(Model.emptyState()), null)
    compare(Model.stateSession(null), null)
  }

  // Service.qml noteSessionOutcome() line for line: call, take the deferred
  // PO-3 flag from the verdict, write only when the state changed. That is
  // the whole of what the component does with the record, so the cases below
  // break when the rule in Model.js does, not when this file is edited
  // (CLAUDE.md 12 - the router cases learned that the hard way).
  function noteOutcome(svc, outcome) {
    var v = Model.sessionAfterOutcome(svc.userState, outcome, svc.deadSessionPending, svc.consumed)
    svc.deadSessionPending = v.pending
    svc.consumed = v.consumed
    if (v.write) { svc.userState = v.state; svc.writes += 1 }
    return svc
  }

  function freshSession(played) {
    return { userState: played, deadSessionPending: false, consumed: false, writes: 0 }
  }

  // applyUserState() line for line: merge the arriving file, then route it
  // through the SAME decision as every player answer.
  function stateLoads(svc, text, loadedBefore, savePending) {
    var adopted = Model.stateOnLoad(Model.parseState(text), svc.userState,
                                    { loadedBefore: loadedBefore, savePending: savePending, maxRecents: 10 })
    svc.userState = adopted.state
    var merged = svc.userState
    noteOutcome(svc, "loaded")
    if (adopted.write && svc.userState === merged) svc.writes += 1
    return svc
  }

  // PO-3's other half. deadSessionVerdict() above only ever fires on a record
  // it FINDS, so which endings leave one behind is the whole of whether a
  // reattach marks a channel red for a failure the user was already shown and
  // already dealt with. The rule is about the witness, not the failure: the
  // record must not outlive the shell that saw how the play ended, and
  // survives exactly one thing - a player still running or still on its way.
  // The defect this closes: a failed `player start`, a missing mpv and an
  // abandoned relaunch each kept it.
  function test_sessionOutcomeRetiresTheRecord() {
    var played = Model.recordPlayed(Model.emptyState(), { tvgId: "bbc1.uk", name: "BBC One HD" }, 10, 1758000123)
    compare(Model.PLAYER_OUTCOMES.length, 13)
    var endings = ["stopped", "ended", "foreign", "failed", "mpvMissing", "abandoned"]
    for (var i = 0; i < endings.length; i++) {
      var svc = freshSession(played)
      noteOutcome(svc, endings[i])
      compare(svc.userState.session, null)
      compare(svc.writes, 1)
      compare(svc.userState.lastPlayed, played.session)      // Recents survives every ending
      // The reattach after this shell is gone has nothing left to mark.
      compare(Model.deadSessionVerdict(svc.userState, true, ({}), "21:30").mark, false)
    }
    var alive = ["superseded", "retrying", "relaunching", "attached"]
    for (var j = 0; j < alive.length; j++) {
      var live = freshSession(played)
      noteOutcome(live, alive[j])
      compare(live.userState.session, played.session)
      compare(live.writes, 0)
      // Kill the shell here and nothing witnessed the outcome: PO-3 marks.
      compare(Model.deadSessionVerdict(live.userState, true, ({}), "21:30").failed, { "t:bbc1.uk": "21:30" })
    }
    // A first load that failed with a live socket hands the record to the EOF
    // rather than racing it, and the EOF retires it.
    var handoff = freshSession(played)
    noteOutcome(handoff, "attached")
    compare(handoff.userState.session, played.session)
    noteOutcome(handoff, "ended")
    compare(handoff.userState.session, null)
    compare(handoff.writes, 1)
    // Idempotent: a second ending has nothing to clear and writes nothing.
    noteOutcome(handoff, "stopped")
    compare(handoff.writes, 1)
    // A word the rule does not name is inert: a misspelled call site costs a
    // stale mark at worst, never a dropped one.
    compare(Model.sessionAfterOutcome(played, "mpv_missing").known, false)
    compare(Model.sessionAfterOutcome(played, "mpv_missing").terminal, false)
    compare(Model.sessionAfterOutcome(played, "mpv_missing").state.session, played.session)
    // The deferred half of PO-3 rides on the same verdict. A probe that found
    // no player before state.json landed owes a mark; an ending settles that
    // event, a player still on its way must leave it owed.
    var owed = { userState: Model.emptyState(), deadSessionPending: true, writes: 0 }
    noteOutcome(owed, "retrying")
    compare(owed.deadSessionPending, true)
    owed.userState = played                             // the FileView lands
    compare(Model.deadSessionVerdict(owed.userState, true, ({}), "21:30").mark, true)
    var settled = freshSession(played)
    settled.deadSessionPending = true
    noteOutcome(settled, "mpvMissing")
    compare(settled.deadSessionPending, false)
    compare(settled.userState.session, null)
  }

  // D-PLY-3. The clear above happens in memory; whether it reaches disk
  // depends on saveState()'s dirsReady gate and on which of state.json's own
  // loads wins. When the write lost, the next load put the record straight
  // back and the following shell start marked the same channel a second
  // time with the same HH:MM (2 runs in 3, live). Consumption is one-way.
  function test_consumedRecordNeverComesBack() {
    var played = Model.recordPlayed(Model.emptyState(), { tvgId: "bbc1.uk", name: "BBC One HD" }, 10, 1758000123)
    var stale = JSON.stringify(played)          // the bytes our clear has not reached yet
    var svc = freshSession(played)
    noteOutcome(svc, "marked")                  // markDeadSession() raised PO-3's red row
    compare(svc.userState.session, null)
    compare(svc.consumed, true)
    stateLoads(svc, stale, true, false)         // the FileView delivers the old file
    compare(svc.userState.session, null)
    compare(Model.deadSessionVerdict(svc.userState, true, ({}), "21:30").mark, false)
    stateLoads(svc, stale, true, false)         // and again
    compare(svc.userState.session, null)
    // A record this shell has NOT consumed is exactly what PO-3 needs kept.
    var fresh = freshSession(Model.emptyState())
    stateLoads(fresh, stale, true, false)
    compare(fresh.userState.session, played.session)
    compare(Model.deadSessionVerdict(fresh.userState, true, ({}), "21:30").mark, true)
  }

  // D-PLY-4, ARCHITECTURE-PLAYER.md section 15: measured at 14 losses in 30
  // trials. state.json is read asynchronously while a play can be issued at
  // once, so the text that arrives is the file from BEFORE the play; taking
  // it wholesale threw away the record that play had just written.
  function test_startupRaceKeepsThePlayItRacedWith() {
    var file = '{"version":2,"favorites":["t:fav"],"recents":[{"id":"t:old","name":"Old","at":100}]}'
    var svc = freshSession(Model.emptyState())
    svc.userState = Model.recordPlayed(svc.userState, { tvgId: "bbc1.uk", name: "BBC One HD" }, 10, 1758000123)
    stateLoads(svc, file, false, false)         // the FileView finally lands
    compare(svc.userState.session, { id: "t:bbc1.uk", name: "BBC One HD", at: 1758000123 })
    compare(svc.userState.favorites, ["t:fav"])                 // only the file knows this
    compare(svc.userState.recents.length, 2)
    compare(svc.userState.recents[0].id, "t:bbc1.uk")
    compare(svc.writes > 0, true)                               // and it is persisted
    // The consequence the race cost: a reattach can mark the channel that
    // died unattended.
    compare(Model.deadSessionVerdict(svc.userState, true, ({}), "21:30").failed, { "t:bbc1.uk": "21:30" })
    // A later load is an external edit and wins; the record is not resurrected.
    var after = freshSession(Model.emptyState())
    after.userState = Model.recordPlayed(after.userState, { tvgId: "bbc1.uk", name: "BBC One HD" }, 10, 1758000123)
    stateLoads(after, '{"version":2,"favorites":["t:new"]}', true, false)
    compare(after.userState.favorites, ["t:new"])
    compare(after.userState.session, null)
  }

  // The other half of D-PLY-4: a play issued inside the startup probe's
  // ~130 ms window was not merely stripped of its record, it was dropped -
  // the probe's "nothing is running" cleared nowPlaying and drainPendingPlay
  // needs one. 28 of 30 trials never started playing against 396a69a.
  function test_probeAnIntentHasOvertakenKeepsOnlyItsResync() {
    compare(Model.probeVerdict(5, 0, 0), { seq: 6, stale: false })   // the startup probe
    compare(Model.probeVerdict(5, 0, 3), { seq: 6, stale: true })    // a play went out after it
    compare(Model.probeVerdict(0, 2, 2), { seq: 2, stale: false })
    // Measured before the resync, or a lock file that names a higher
    // sequence than a just-started shell makes every probe look stale - and
    // PO-3's mark silently stops being raised at all.
    var v = Model.probeVerdict(7, 0, 0)
    compare(v.stale, false)
    compare(v.seq, 8)
    compare(Model.probeVerdict(1, 9, 9).seq, 9)                      // never backwards
  }

  // D-PLY-1, the P1: a helper that ladders a player down and spawns its
  // replacement under one lock delivers the old one's death to the observer
  // while that call is still running. Read as an ending it cleared
  // nowPlaying and playerWanted, the success reply then read the cleared
  // nowPlaying as "a stop overtook this start" and armed nothing, and the
  // interface sat idle while the new player kept playing.
  function test_deathInsideOurOwnRespawnIsNotAnEnding() {
    var live = { sessionInFlight: false, relaunchPending: false, nowPlaying: true, hasChannel: true, userStopped: false, stopping: false }
    compare(Model.playerDeathKind(live), "ended")
    live.sessionInFlight = true
    compare(Model.playerDeathKind(live), "respawn")     // trigger B: `player start`
    live.relaunchPending = true
    compare(Model.playerDeathKind(live), "respawn")     // trigger A: the health verdict
    live.userStopped = true
    compare(Model.playerDeathKind(live), "ended")       // our own stop outranks it
    live.userStopped = false
    live.sessionInFlight = false
    compare(Model.playerDeathKind(live), "relaunch")
    live.hasChannel = false
    compare(Model.playerDeathKind(live), "ended")
    // And the reply: a live player the helper just reported is always worth
    // arming for; when we no longer know what it plays, read the stash.
    compare(Model.playerSessionFollowUp({ attached: true, nowPlaying: true }), "attached")
    compare(Model.playerSessionFollowUp({ attached: false, nowPlaying: true }), "hunt")
    compare(Model.playerSessionFollowUp({ attached: false, nowPlaying: false }), "recover")
    compare(Model.playerSessionFollowUp({ attached: false, nowPlaying: false, stopping: true }), "abandoned")
    compare(Model.playerSessionFollowUp({ attached: false, nowPlaying: true, userStopped: true }), "abandoned")
  }

  function test_settingsClamps() {
    var s = Model.settingsFrom({ refreshMinutes: "5", barLabelMaxWidth: 9999, maxRecents: 0, playlistUrl: " http://x " })
    compare(s.refreshMinutes, 15)
    compare(s.barLabelMaxWidth, 600)
    compare(s.maxRecents, 1)
    compare(s.playlistUrl, "http://x")
    compare(Model.settingsFrom({}).refreshMinutes, 360)
    compare(Model.settingsFrom({}).barLabelMaxWidth, 180)
  }

  function test_mpvArgv() {
    // M2-02: the launch argv carries no channel at all - no URL, no "--",
    // no header options, no per-channel title (S-03). The channel arrives
    // over the 0600 socket, so `--idle=once` is what makes this possible.
    var argv = Model.buildMpvArgv({ socketPath: "/tmp/s", stateDir: "/home/u/.local/state/omarchy-iptv", name: "N", url: "http://u", headers: { "User-Agent": "VLC" }, extraArgs: [] })
    compare(argv[0], "mpv")
    compare(argv.indexOf("--") !== -1, false)
    compare(argv.indexOf("http://u") !== -1, false)
    compare(argv.filter(function(t) { return t.indexOf("://") !== -1 }).length, 0)
    compare(argv.filter(function(t) { return t.indexOf("--user-agent") === 0 }).length, 0)
    compare(argv.indexOf("--idle=once") !== -1, true)
    compare(argv.indexOf("--title=$>IPTV") !== -1, true)   // S-01: raw marker, never property-expanded
    compare(argv.indexOf("--force-media-title=IPTV") !== -1, true)
    compare(Model.splitMpvArgs("--Profile=x --no-idle --cache=yes").args, ["--cache=yes"])
    compare(Model.splitMpvArgs("--log-file=/tmp/x --osd-msg1=${path} --cache=yes").args, ["--cache=yes"])
    // PO-11: the player is told where to write. The screenshot is durable
    // (the user asked for it) and lives under the state directory; the
    // resume record `Q` writes is not worth keeping and stays in the runtime
    // directory, private and gone at logout. Neither is $HOME any more.
    var dirs = Model.playerDirs("/run/user/1000/omarchy-iptv/mpv.sock", "/home/u/.local/state/omarchy-iptv")
    compare(dirs.cwd, "/run/user/1000/omarchy-iptv")
    compare(dirs.screenshots, "/home/u/.local/state/omarchy-iptv/screenshots")
    compare(dirs.watchLater, "/run/user/1000/omarchy-iptv/watch-later")
    compare(argv.indexOf("--screenshot-dir=/home/u/.local/state/omarchy-iptv/screenshots") !== -1, true)
    compare(argv.indexOf("--watch-later-dir=/tmp/watch-later") !== -1, true)
    // --watch-later-dir is reserved (a resume record names a stream path);
    // --screenshot-dir is not, so a user can still choose their own.
    compare(Model.splitMpvArgs("--watch-later-dir=/home/u --screenshot-dir=/home/u/Pictures").args, ["--screenshot-dir=/home/u/Pictures"])
  }

  function test_playerArgv() {
    // The frozen lane interface (ARCHITECTURE-PLAYER.md section 9): every
    // value its own argv member, user tokens attached to --mpv-arg=, and no
    // player argv ever carrying a URL.
    var start = Model.playerStartArgv("/tmp/s", "/tmp/c", "t:bbc1.uk", 41, "g:uk", 1758000123, ["--cache=yes"])
    compare(start.slice(0, 4), ["player", "start", "--socket", "/tmp/s"])
    compare(start.indexOf("--seq") !== -1 && start[start.indexOf("--seq") + 1], "41")
    compare(start[start.length - 1], "--mpv-arg=--cache=yes")
    compare(Model.playerStopArgv("/tmp/s", 42, "term"), ["player", "stop", "--socket", "/tmp/s", "--seq", "42", "--from", "term"])
    compare(Model.playerProbeArgv("/tmp/s", 301706), ["player", "probe", "--socket", "/tmp/s", "--owner-pid", "301706"])
    compare(Model.helperArgv("/p/bin/omarchy-iptv", ["player", "stop"]), ["python3", "/p/bin/omarchy-iptv", "player", "stop"])
    var probe = Model.parsePlayerProbe('{"ok":true,"kind":"player.probe","running":true,"responsive":true,"pid":7,"idle":false,"seq":41,"stash":{"schema":1,"id":"t:bbc1.uk","name":"BBC One HD","launchedFrom":"g:uk"},"owner":null}')
    compare([probe.valid, probe.running, probe.pid, probe.stash.launchedFrom], [true, true, 7, "g:uk"])
    compare(Model.parsePlayerProbe("not json").valid, false)
    compare(Model.parsePlayerEvent('{"event":"end-file","reason":"error","playlist_entry_id":2,"file_error":"loading failed"}').kind, "end-file")
    compare(Model.endedVerdict({ reason: "error", file_error: "loading failed" }, false, false).notify, true)
    compare(Model.endedVerdict({ reason: "eof" }, false, false).kind, "silent")
  }

  function test_playerRouterZapStaysSilent() {
    // 4.8, verified on mpv 0.41: a zap emits end-file{reason:"stop"} and then
    // start-file for the new entry, and "stop" with no user stop is a FAILURE
    // verdict - so the only thing standing between a zap and a false "BBC One
    // did not play" toast is the start-file superseding the end-file.
    var owners = ownersFor([[1, { id: "t:a", name: "Channel A" }], [2, { id: "t:b", name: "Channel B" }]])
    var zap = [
      '{"event":"start-file","playlist_entry_id":1}',
      '{"event":"end-file","reason":"stop","playlist_entry_id":1}',
      '{"event":"start-file","playlist_entry_id":2}'
    ]
    var live = routePlayer({ lines: zap, owners: owners, nowPlaying: { id: "t:b", name: "Channel B" } })
    compare(live.toasts, [])
    compare(live.lastEndFile, null)      // nothing terminal is pending
    compare(live.entryId, 2)
    // And the superseded end-file cannot come back later: if the player dies
    // after the zap that is a crash naming the channel now playing, with the
    // generic reason - never entry 1 and never the zap's own "stop".
    var died = routePlayer({ lines: zap.concat(["EOF"]), owners: owners, nowPlaying: { id: "t:b", name: "Channel B" } })
    compare(died.toasts.length, 1)
    compare(died.toasts[0].name, "Channel B")
    compare(died.toasts[0].reason, Model.PLAYER_GENERIC_FAILURE)
    // The silence is the start-file's doing, not a free pass for "stop": the
    // same end-file with no load after it is a failure the user must see (a
    // load we issued was replaced and then the process died).
    var orphanStop = routePlayer({ lines: [
      '{"event":"start-file","playlist_entry_id":1}',
      '{"event":"end-file","reason":"stop","playlist_entry_id":1}',
      "EOF"
    ], owners: owners, nowPlaying: { id: "t:a", name: "Channel A" } })
    compare(orphanStop.toasts, [{ name: "Channel A", reason: Model.PLAYER_GENERIC_FAILURE }])
    // A .m3u8 master resolves through redirect on nearly every load: never terminal.
    var master = routePlayer({ lines: [
      '{"event":"start-file","playlist_entry_id":1}',
      '{"event":"end-file","reason":"redirect","playlist_entry_id":1}',
      "EOF"
    ], owners: owners, nowPlaying: { id: "t:a", name: "Channel A" } })
    compare(master.toasts, [])
  }

  function test_playerRouterNamesTheChannelThatDied() {
    // F4 / 4.8: end-file{error} for entry 1 can arrive after the user has
    // already zapped to entry 2, so the toast and the red guide row come from
    // entryOwners, not from nowPlaying. The gate FAILS OPEN: an unknown or
    // missing entry id degrades which channel is named and never suppresses
    // the toast.
    var owners = ownersFor([[1, { id: "t:a", name: "Channel A" }], [2, { id: "t:b", name: "Channel B" }]])
    var now = { id: "t:b", name: "Channel B" }
    function burst(endLine, extra) {
      return routePlayer({ lines: [
        '{"event":"start-file","playlist_entry_id":1}',
        '{"event":"start-file","playlist_entry_id":2}',
        endLine, "EOF"
      ], owners: owners, nowPlaying: now, userStopped: extra === "userStopped", stopping: extra === "stopping" })
    }
    var slow = burst('{"event":"end-file","reason":"error","playlist_entry_id":1,"file_error":"loading failed"}')
    compare(slow.toasts.length, 1)
    compare(slow.toasts[0].name, "Channel A")
    compare(slow.toasts[0].reason, "loading failed")
    // Fail open, three ways.
    compare(burst('{"event":"end-file","reason":"error","playlist_entry_id":99,"file_error":"loading failed"}').toasts,
            [{ name: "Channel B", reason: "loading failed" }])
    compare(burst('{"event":"end-file","reason":"error","file_error":"loading failed"}').toasts,
            [{ name: "Channel B", reason: "loading failed" }])
    compare(burst('{"event":"end-file","reason":"error","playlist_entry_id":"junk","file_error":"loading failed"}').toasts,
            [{ name: "Channel B", reason: "loading failed" }])
    // What we caused is silent, whatever mpv reported (PO-4 for a clean end).
    compare(burst('{"event":"end-file","reason":"error","playlist_entry_id":1,"file_error":"loading failed"}', "userStopped").toasts, [])
    compare(burst('{"event":"end-file","reason":"error","playlist_entry_id":1,"file_error":"loading failed"}', "stopping").toasts, [])
    compare(burst('{"event":"end-file","reason":"eof","playlist_entry_id":1}').toasts, [])
    compare(burst('{"event":"end-file","reason":"quit","playlist_entry_id":1}').toasts, [])
  }

  function test_playerEntryOwnersRing() {
    // The ring Service.qml rememberEntry() keeps (4.8): mpv's own
    // playlist_entry_id -> the channel that load was for, four deep. Four is
    // what a zap burst can outrun, and when it does the gate fails open -
    // the toast degrades to the channel now playing rather than vanishing.
    var pairs = []
    for (var i = 1; i <= 5; i++) pairs.push([i, { id: "t:" + i, name: "Channel " + i }])
    var owners = ownersFor(pairs)
    compare(Object.keys(owners), ["2", "3", "4", "5"])
    compare(owners["5"], { id: "t:5", name: "Channel 5" })
    // Entry 4 is still in the ring: its death names Channel 4, not what is
    // playing now.
    var known = routePlayer({ lines: [
      '{"event":"start-file","playlist_entry_id":5}',
      '{"event":"end-file","reason":"error","playlist_entry_id":4,"file_error":"loading failed"}',
      "EOF"
    ], owners: owners, nowPlaying: { id: "t:5", name: "Channel 5" } })
    compare(known.toasts, [{ name: "Channel 4", reason: "loading failed" }])
    // Entry 1 fell off the back. The user still gets the toast.
    var forgotten = routePlayer({ lines: [
      '{"event":"start-file","playlist_entry_id":5}',
      '{"event":"end-file","reason":"error","playlist_entry_id":1,"file_error":"loading failed"}',
      "EOF"
    ], owners: owners, nowPlaying: { id: "t:5", name: "Channel 5" } })
    compare(forgotten.toasts, [{ name: "Channel 5", reason: "loading failed" }])
    // A reply with no entry id, and a start whose target is not known yet,
    // record nothing rather than poisoning the ring with a blank row.
    compare(ownersFor([[0, { id: "t:x", name: "X" }], ["junk", { id: "t:y", name: "Y" }], [3, null]]), ({}))
  }

  function test_playerRouterLogTailKeepsOnlyTheHost() {
    // S-01 / D-QA-01: the failure text comes from request_log_messages "error",
    // redacted in python before it crosses into QML and again here, and it is
    // the tail - not mpv's generic "loading failed" - that the toast quotes.
    // Only error and fatal are kept, and only the last five lines.
    var credentialed = "http://user:pw@provider.test:8080/live/secret-token/1.m3u8"
    var run = routePlayer({ lines: [
      '{"event":"log-message","level":"info","prefix":"cplayer","text":"Playing: ' + credentialed + '"}',
      '{"event":"log-message","level":"error","prefix":"stream","text":"Failed to open ' + credentialed + '\\n"}',
      '{"event":"end-file","reason":"error","playlist_entry_id":1,"file_error":"loading failed"}',
      "EOF"
    ], owners: ownersFor([[1, { id: "t:a", name: "Channel A" }]]), nowPlaying: { id: "t:a", name: "Channel A" } })
    compare(run.tail, ["[stream] Failed to open provider.test"])          // the info line is not kept
    compare(run.toasts, [{ name: "Channel A", reason: "[stream] Failed to open provider.test" }])
    var blob = JSON.stringify(run)
    compare(blob.indexOf("pw@"), -1)
    compare(blob.indexOf("secret-token"), -1)
    compare(blob.indexOf("://"), -1)
    compare(blob.indexOf("8080"), -1)
    // Six error lines, five kept, oldest dropped - the same bound Service.qml
    // rememberStderr() has always had, and it is memory only.
    var lines = []
    for (var i = 1; i <= 6; i++) lines.push('{"event":"log-message","level":"error","prefix":"ffmpeg","text":"line ' + i + '"}')
    var tail = routePlayer({ lines: lines }).tail
    compare(tail.length, 5)
    compare(tail[0], "[ffmpeg] line 2")
    compare(tail[4], "[ffmpeg] line 6")
    // A fatal is kept too; a reply, an unknown event and junk are ignored.
    var mixed = routePlayer({ lines: [
      '{"event":"log-message","level":"fatal","prefix":"","text":"could not open ' + credentialed + '   "}',
      '{"request_id":1,"error":"success","data":"mpv 0.41.0"}',
      '{"event":"seek"}',
      "not json at all"
    ] })
    compare(mixed.tail, ["could not open provider.test"])
  }

  function test_playerUpTruthTable() {
    // 4.7: playerUp replaces mpvProc.running at some twenty read sites, so it
    // has to keep the SYNCHRONOUS birth edge the process gave (playerPending,
    // set inside startPlayer()) while gaining a sub-second death edge from
    // socket EOF. With caveat C3: between attempts there is no socket object
    // at all, and reading .connected off null would throw inside the binding.
    var table = [
      { socket: null, pending: false, up: false },                    // at rest
      { socket: null, pending: true, up: true },                      // the birth edge: no socket yet
      { socket: { connected: false }, pending: false, up: false },    // a fresh object, not yet connected
      { socket: { connected: false }, pending: true, up: true },      // connecting, start in flight
      { socket: { connected: true }, pending: false, up: true },      // attached: the steady state
      { socket: { connected: true }, pending: true, up: true }        // attached before the reply landed
    ]
    for (var i = 0; i < table.length; i++) {
      liveness.nowPlaying = null
      liveness.socket = table[i].socket
      liveness.playerPending = table[i].pending
      compare(liveness.playerUp, table[i].up, "playerUp row " + i)
      compare(liveness.playing, false, "no channel is never playing, row " + i)
      liveness.nowPlaying = { id: "t:a", name: "Channel A" }
      compare(liveness.playing, table[i].up, "playing = playerUp && nowPlaying, row " + i)
    }
    // The death edge: the object is dropped, not re-armed, and the binding
    // has to survive that without a channel of its own.
    liveness.socket = { connected: true }
    liveness.playerPending = false
    compare(liveness.playerUp, true)
    liveness.socket = null
    compare(liveness.playerUp, false)
    compare(liveness.playing, false)
  }

  // D-PLY-11, ruling CL5. Service.qml's checkPlayerChannel() and the repair
  // in handlePlayerResult(), line for line: ask the decision, count the
  // repair, re-apply the SHELL's id. The service half is the counter and the
  // one runControl call; break a rule in Model.js and this goes red without
  // anyone editing this file (CLAUDE.md 12).
  function repairDriver(svc) {
    return {
      // the health tick, once `status` carries the player's own record
      tick: function (stash) {
        var v = Model.reconcileVerdict(stash, svc.nowPlaying, svc.sourceKey)
        if (v.state === "agree") svc.repairs = 0
        if (v.state !== "diverged") return v.state
        if (svc.repairs >= 2) return v.state
        svc.repairs += 1
        svc.zapped.push(v.repair)
        return v.state
      },
      // a `player start` / `player restart` that answered ok
      session: function (status) {
        svc.owners = Model.rememberEntryOwner(svc.owners, status.entryId, Model.replyTarget(status, svc.nowPlaying))
        var repair = Model.sessionIntentRepair(status, svc.nowPlaying)
        if (repair !== "") svc.zapped.push(repair)
        return repair
      }
    }
  }

  function test_playerChannelIsRepairedByReapplyingTheIntent() {
    var svc = { nowPlaying: { id: "t:qa.eight", name: "Eight" }, sourceKey: "a1b2c3d4", repairs: 0, zapped: [], owners: ({}) }
    var drive = repairDriver(svc)
    // The measured cold burst: one `player start` carrying the burst's FIRST
    // intent answers ok, long after the shell moved on to the eighth.
    var reply = { ok: true, kind: "player.start", id: "t:qa.first", name: "First", entryId: 2, applied: true, playing: null }
    compare(drive.session(reply), "t:qa.eight")
    compare(svc.zapped, ["t:qa.eight"])
    // The interface is NEVER relabelled from the player. That is the whole
    // of CL5: the alternative leaves the user watching a channel they did
    // not choose with the interface agreeing.
    compare(svc.nowPlaying.id, "t:qa.eight")
    // The entry the reply carries belongs to the channel that reply is
    // about, not to whatever is current now.
    compare(svc.owners["2"], { id: "t:qa.first", name: "First" })
    // A start that stood down and left the shell's own intent playing asks
    // for nothing.
    var down = { ok: true, kind: "player.start", id: "t:qa.first", entryId: 1, applied: false, playing: { id: "t:qa.eight", name: "Eight" } }
    compare(drive.session(down), "")
    compare(svc.zapped.length, 1)
    compare(svc.owners["1"], { id: "t:qa.eight", name: "Eight" })
  }

  function test_theHealthTickSeesTheDivergenceAndBoundsItsRepairs() {
    var svc = { nowPlaying: { id: "t:qa.eight", name: "Eight" }, sourceKey: "a1b2c3d4", repairs: 0, zapped: [], owners: ({}) }
    var drive = repairDriver(svc)
    var agreed = Model.playerStash({ id: "t:qa.eight", name: "Eight", sourceKey: "a1b2c3d4", seq: 7, verb: "play" })
    var wrong = Model.playerStash({ id: "t:qa.first", name: "First", sourceKey: "a1b2c3d4", seq: 1, verb: "start" })
    compare(drive.tick(agreed), "agree")
    compare(svc.zapped, [])
    // A player that never answered this question before now answers it every
    // health tick - which is the CL6 contract, "within one health tick".
    compare(drive.tick(wrong), "diverged")
    compare(svc.zapped, ["t:qa.eight"])
    // Bounded: a player that will not take the channel is reported, not
    // re-zapped once every tick for the rest of the session.
    compare(drive.tick(wrong), "diverged")
    compare(drive.tick(wrong), "diverged")
    compare(drive.tick(wrong), "diverged")
    compare(svc.zapped, ["t:qa.eight", "t:qa.eight"])
    // Agreement returns the budget, so the next divergence is repaired too.
    compare(drive.tick(agreed), "agree")
    compare(drive.tick(wrong), "diverged")
    compare(svc.zapped.length, 3)
    // A helper too old to carry the record raises nothing at all.
    compare(drive.tick(null), "unknown")
    compare(svc.zapped.length, 3)
  }

  function test_privacy() {
    compare(Model.redactUrls("Failed to open http://u:p@h.test/x?y."), "Failed to open h.test")
    compare(Model.sourceLabel("http://u:p@tv.example.net:8080/get.php?u=1"), "http://tv.example.net")
    compare(Model.hostOf("/home/x/list.m3u"), "local file")
  }

  function test_columnAnchor() {
    // D-LIVE-16: pinned entries show the column from the top; groups are contained.
    var entries = Model.scopeEntries(channels, userState)
    var all = Model.columnAnchor(entries, "all")
    compare(all.index, 2)
    compare(all.top, true)
    var group = Model.columnAnchor(entries, "g:UK")
    compare(group.index, 4)
    compare(group.top, false)
    compare(Model.columnAnchor(entries, "g:Gone").index, -1)
    compare(Model.columnAnchor(null, "all").index, -1)
  }

  function test_stopLadder() {
    // D-LIVE-17: quit -> SIGTERM -> SIGKILL, each after its grace period.
    compare(Model.STOP_QUIT_GRACE_MS, 2000)
    compare(Model.STOP_KILL_GRACE_MS, 2000)
    var step = Model.stopEscalation("")
    compare(step.action, "quit")
    compare(step.waitMs, 2000)
    step = Model.stopEscalation(step.action)
    compare(step.signal, 15)
    step = Model.stopEscalation(step.action)
    compare(step.signal, 9)
    compare(step.waitMs, 0)
    compare(Model.stopEscalation("kill").signal, 0)
    compare(Model.healthTick(0, true).skips, 1)
    compare(Model.healthTick(2, true).restart, true)
    compare(Model.healthTick(2, false).check, true)
  }

  function test_playlistWarnings() {
    // D-LIVE-18: one footer line, URL-free, empty without warnings.
    var status = Model.parseHelperStatus('{"ok": true, "kind": "playlist", "warnings": ["truncated to 50000 channels (500 entries skipped)", "see http://u:p@h.test/x"]}', "playlist")
    compare(Model.statusWarnings(status), ["truncated to 50000 channels (500 entries skipped)", "see h.test"])
    compare(Model.warningLine(Model.statusWarnings(status)), "Playlist warning: truncated to 50000 channels (500 entries skipped) (+1 more)")
    compare(Model.warningLine([]), "")
    compare(Model.statusWarnings({ ok: false, warnings: ["x"] }), [])
    compare(Model.footerStatus({ count: 50000, lastUpdated: "01:53", warning: "Playlist warning: x" }), "Playlist warning: x")
    compare(Model.footerStatus({ count: 5, playingName: "Arte", warning: "Playlist warning: x" }), Model.GLYPHS.play + " Arte" + Model.SEP + "s stop")
  }

  // ---- Sources (M2-01): the same vectors as tests/Model.test.js, proving
  // decodeURIComponent, encodeURIComponent, toLowerCase on IDN hosts, Date
  // arithmetic and object copies behave in the V4 engine.
  function test_sourceLimitsAndGlyphs() {
    compare(Model.LIMITS.url, 2048)
    compare(Model.LIMITS.label, 64)
    compare(Model.LIMITS.sources, 50)
    compare(Model.MASK, "****")
    compare(Model.STATE_VERSION, 2)
    compare(Model.SOURCE_KEYS.open, "o")
    compare(Model.GLYPHS.sources, "󰐑")
    compare(Model.GLYPHS.eye, "󰈈")
    compare(Model.GLYPHS.eyeOff, "󰈉")
    compare(Model.GLYPHS.check, "󰄬")
  }

  function test_validateSourceUrl() {
    var ok = Model.validateSourceUrl(" HTTP://Provider.Example.TEST:80/get.php?username=u&password=p ")
    compare(ok.ok, true)
    compare(ok.url, "http://provider.example.test/get.php?username=u&password=p")
    compare(ok.host, "provider.example.test")
    compare(Model.validateSourceUrl("https://iptv-org.github.io:443/iptv/countries/us.m3u#x").url, "https://iptv-org.github.io/iptv/countries/us.m3u")
    compare(Model.validateSourceUrl("http://u:p@h.test:8080/x?y=1").url, "http://u:p@h.test:8080/x?y=1")
    compare(Model.validateSourceUrl("http://[::1]:8080/list.m3u").host, "[::1]")
    compare(Model.validateSourceUrl("http://Bücher.EXAMPLE/list.m3u").url, "http://bücher.example/list.m3u")
    compare(Model.validateSourceUrl("file://host/srv/tv/a%20b.m3u").url, "/srv/tv/a b.m3u")
    compare(Model.validateSourceUrl("FILE:///srv/tv/local.m3u").kind, "file")
    compare(Model.validateSourceUrl("/srv/tv/local.m3u\n").url, "/srv/tv/local.m3u")
    compare(Model.validateSourceUrl("http://h.test/a\u0000b").url, "http://h.test/ab")
    compare(Model.validateSourceUrl("").code, "empty")
    compare(Model.validateSourceUrl("provider.test/list.m3u").code, "scheme")
    compare(Model.validateSourceUrl("javascript:alert(1)").code, "scheme")
    compare(Model.validateSourceUrl("http://h .test/").code, "invalid")
    compare(Model.validateSourceUrl("file:///%zz").code, "invalid")
    compare(Model.validateSourceUrl("~/tv/list.m3u").code, "relative_path")
    compare(Model.validateSourceUrl("/proc/self/environ").code, "unsafe_path")
    compare(Model.validateSourceUrl("http://h.test/" + new Array(2050).join("a")).code, "too_long")
    compare(Model.validateSourceUrl("", { kind: "epg" }).ok, true)
    compare(Model.validateSourceUrl("ftp://x", { kind: "epg" }).message, "EPG: start with http://, https://, or / for a local file")
    compare(Model.validateSourceUrl("ftp://x").message, "Start with http://, https://, or / for a local file")
    compare(Model.validateSourceUrl("/" + new Array(2100).join("x")).message, "Too long · max 2,048 characters")
  }

  function test_sourceKeysAndLabels() {
    compare(Model.sourceKey("https://iptv-org.github.io/iptv/countries/us.m3u"), "d5977d8a")
    compare(Model.sourceKey("http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts"), "d990c2e4")
    compare(Model.sourceKey("/srv/tv/local.m3u"), "b0eed9fb")
    compare(Model.allocateSourceKey([{ key: "d5977d8a", url: "http://other.test/" }], "https://iptv-org.github.io/iptv/countries/us.m3u"), "d5977d8a-2")
    compare(Model.sourceCacheDir("/c", "d5977d8a"), "/c/sources/d5977d8a")
    compare(Model.sourceCacheDir("/c", "../x"), "")
    compare(Model.deriveLabel("http://www.NAS.local:9981/x"), "nas.local:9981")
    compare(Model.deriveLabel("/home/dag/tv/channels.m3u"), "channels.m3u")
    compare(Model.uniqueLabel("tv.example.net", ["TV.example.net"]), "tv.example.net 2")
    compare(Model.validateLabel("provider", [{ id: "1", label: "Provider" }], "").code, "label_taken")
    compare(Model.validateLabel("provider", [{ id: "1", label: "Provider" }], "1").ok, true)
    compare(Model.validateLabel(new Array(66).join("x"), [], "").message, "Label too long · max 64 characters")
  }

  function test_maskUrl() {
    compare(Model.maskUrl("http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts"), "http://provider.example.test/get.php?username=****&password=****&type=m3u_plus&output=ts")
    compare(Model.maskUrl("http://u:p@h.test:8080/x?token=abc&flag"), "http://****@h.test:8080/x?token=****&flag")
    compare(Model.maskUrl("http://h.test/x?a=1#frag"), "http://h.test/x?a=****#****")
    compare(Model.maskUrl("https://iptv-org.github.io/iptv/countries/us.m3u"), "https://iptv-org.github.io/iptv/countries/us.m3u")
    compare(Model.maskUrl("/home/dag/tv/channels.m3u"), "/home/dag/tv/channels.m3u")
  }

  function test_xtreamUrls() {
    var x = Model.xtreamUrls("http://Provider.Example.TEST:8080/", "u", "p")
    compare(x.ok, true)
    compare(x.playlistUrl, "http://provider.example.test:8080/get.php?username=u&password=p&type=m3u_plus&output=ts")
    compare(x.epgUrl, "http://provider.example.test:8080/xmltv.php?username=u&password=p")
    compare(Model.xtreamUrls("https://h.test", "a b", "p&q").playlistUrl, "https://h.test/get.php?username=a%20b&password=p%26q&type=m3u_plus&output=ts")
    compare(Model.encodeQueryValue("a b!*'()~-._/@:+"), "a%20b%21%2A%27%28%29~-._%2F%40%3A%2B")
    compare(Model.xtreamUrls("h.test:8080", "u", "p").code, "server_scheme")
    compare(Model.xtreamUrls("http://h.test/get.php?x=1", "u", "p").code, "server_path")
    compare(Model.xtreamUrls("http://h.test", "u", "").code, "pass_empty")
    compare(Model.xtreamUrls({ server: "http://h.test", username: "u", password: "p" }).host, "h.test")
    compare(Model.validateXtream({ server: "", username: "u", password: "p" }).field, "server")
  }

  function test_sourceViewsAndCopy() {
    var now = Math.floor(new Date(2026, 8, 13, 21, 40).getTime() / 1000)
    var rec = { key: "d990c2e4", url: "http://tv.example.net:8080/get.php?username=u&password=p", epgUrl: "http://tv.example.net:8080/xmltv.php?username=u&password=p", kind: "http", label: "Provider", labelCustom: true, origin: "xtream", addedAt: 1, lastUsed: now - 600, fetchedAt: 2, channelCount: 1475, groupCount: 28 }
    var view = Model.sourceView(rec, "d990c2e4", now)
    compare(view.id, "d990c2e4")
    compare(view.kind, "xtream")
    compare(view.host, "tv.example.net:8080")
    compare(view.hasEpg, true)
    compare(view.active, true)
    compare(view.lastUsedText, "used 21:30")
    compare(view.url, undefined)
    compare(Model.sourceDetail(view, false), "active · tv.example.net:8080 · Xtream · 1,475 channels in 28 groups · EPG")
    compare(Model.sourceDetail(view, true), "active · used 21:30 · tv.example.net:8080 · Xtream · 1,475 channels in 28 groups · EPG")
    compare(Model.sourceAccessibleName(view), "Provider, tv.example.net:8080, 1,475 channels in 28 groups, active, EPG, last used 21:30")
    compare(Model.sourceView({ key: "b0eed9fb", url: "/srv/tv/local.m3u", kind: "file", lastUsed: 0, fetchedAt: 0 }, "", now).channelCount, -1)
    compare(Model.formatLastUsed(now - 86400, now), "used yesterday")
    compare(Model.formatLastUsed(Math.floor(new Date(2025, 8, 3, 10, 0).getTime() / 1000), now), "used 3 Sep 2025")
    compare(Model.formatLastUsed(0, now), "never used")
    compare(Model.sourcesHeaderCount(3), "3 sources")
    compare(Model.confirmRemoveMessage("NAS Tvheadend", false), "Remove “NAS Tvheadend”? Its cache is deleted too.")
    compare(Model.sourceErrorMessage("duplicate", { label: "Provider" }), "Already in Sources as “Provider”")
    compare(Model.fetchingLine("tv.example.net", "url"), "Fetching from tv.example.net…")
    compare(Model.sourceTransient("switched", { label: "NAS Tvheadend", channelCount: 84 }), "Switched to NAS Tvheadend · 84 channels")
    var views = Model.sourceViews({ sources: [rec, { key: "b0eed9fb", url: "/srv/tv/local.m3u", kind: "file", lastUsed: now, fetchedAt: 0 }] }, "b0eed9fb", now, {})
    compare(views[0].id, "b0eed9fb")
    compare(JSON.stringify(views).indexOf("://"), -1)
  }

  function test_stateV2AndReducers() {
    compare(Model.emptyState(), { version: 2, cacheLayout: 0, favorites: [], recents: [], lastPlayed: null, session: null, sources: [] })
    var v1 = Model.parseState('{"version":1,"favorites":["t:bbc1.uk"],"recents":[],"lastPlayed":null}')
    compare(v1.version, 2)
    compare(v1.favorites, ["t:bbc1.uk"])
    compare(v1.sources, [])
    var added = Model.addSource(Model.emptyState(), { playlistUrl: "HTTP://Provider.Example.TEST:80/get.php?username=u&password=p&type=m3u_plus&output=ts", label: "", origin: "xtream" }, 1000)
    compare(added.ok, true)
    compare(added.key, "d990c2e4")
    compare(added.state.sources[0].label, "provider.example.test")
    compare(Model.addSource(added.state, { playlistUrl: "http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts" }).code, "duplicate")
    var round = Model.parseState(JSON.stringify(added.state))
    compare(round.sources.length, 1)
    compare(round.sources[0].key, "d990c2e4")
    compare(Model.recordPlayed(added.state, { id: "c1", name: "C" }, 10, 5).sources.length, 1)
    compare(Model.withFavorites(added.state, ["c1"]).sources.length, 1)
    var upd = Model.updateSource(added.state, "d990c2e4", { playlistUrl: "http://provider.example.test:8080/get.php?username=u&password=p&type=m3u_plus&output=ts" }, 2000)
    compare(upd.urlChanged, true)
    compare(upd.replacedKey, "d990c2e4")
    compare(upd.key, "85ac744a")
    compare(upd.state.sources.length, 2)
    compare(Model.removeSource(upd.state, "d990c2e4").state.sources.length, 1)
    var rec = Model.reconcileSources(Model.emptyState(), "https://iptv-org.github.io/iptv/countries/us.m3u", "", "", 5)
    compare(rec.added, "d5977d8a")
    compare(rec.state.sources[0].origin, "migrated")
    compare(Model.activeSourceKey(rec.state, "HTTPS://iptv-org.github.io:443/iptv/countries/us.m3u"), "d5977d8a")
    compare(Model.sourceForEdit(added.state, "d990c2e4").playlistMasked, "http://provider.example.test/get.php?username=****&password=****&type=m3u_plus&output=ts")
    compare(JSON.stringify(Model.sourcesSummary(added.state, "d990c2e4")).indexOf("://"), -1)
    compare(Model.entryWith({ id: "x", refreshMinutes: 30 }, { playlistUrl: "u" }), { id: "x", refreshMinutes: 30, playlistUrl: "u" })
    compare(Model.cacheStale({ ok: true, fetchedAt: 1000 }, 15, 1000 + 900), true)
    compare(Model.cacheStale({ ok: true, fetchedAt: 1000 }, 15, 1000 + 899), false)
  }

  function test_sourcesModesAndForms() {
    var g = Model.openFirstRun(Model.guideState("all"))
    compare(g.mode, "sourceEdit")
    compare(g.form.origin, "firstRun")
    compare(g.form.focus, "playlist")
    compare(Model.formFocusOrder(g.form, { savedSources: 2 }), ["playlist", "epg", "savedSources", "xtream", "load"])
    // paste masks at once, typing never masks mid-flight
    var pasted = Model.withFormValue(g, "playlist", "http://h.test/x?token=1")
    compare(Model.fieldMasked(pasted.form, "playlist"), true)
    var typed = Model.withFormValue(g, "playlist", "http://h.test/x?token=1", { typed: true })
    compare(Model.fieldMasked(typed.form, "playlist"), false)
    compare(Model.footerHints({ mode: "sourceEdit", form: pasted.form })[2], ["Ctrl+R", "reveal"])
    var revealed = Model.toggleReveal(pasted, "playlist")
    compare(revealed.form.revealed.playlist, true)
    compare(Model.footerHints({ mode: "sourceEdit", form: revealed.form })[2], ["Ctrl+R", "hide"])
    compare(Model.moveFormFocus(revealed, 1, {}).form.revealed.playlist, false)
    compare(Model.moveFormFocus(revealed, 1, {}).form.focus, "epg")
    compare(Model.toggleReveal(Model.withFormValue(g, "playlist", "http://h.test/x"), "playlist").form.revealed.playlist, false)
    // Esc: clear first, then close
    var esc = Model.onEscape(pasted)
    compare(esc.close, false)
    compare(esc.state.form.values.playlist, "")
    compare(Model.onEscape(esc.state).close, true)
    compare(Model.onEscape(Model.withFormProbing(pasted, true, { host: "h.test" })).cancelProbe, true)
    // Xtream from first run keeps the parent
    var x = Model.openXtreamForm(pasted)
    compare(x.mode, "sourceXtream")
    compare(x.form.parent.values.playlist, "http://h.test/x?token=1")
    compare(Model.onEscape(x).state.form.values.playlist, "http://h.test/x?token=1")
    // Sources from list mode and back
    var views = [{ id: "a", active: false }, { id: "b", active: true }]
    var s = Model.openSources(Model.withMode(Model.guideState("g:UK"), "list"), views)
    compare(s.mode, "sources")
    compare(s.returnMode, "list")
    compare(s.sourceCursor, 1)
    compare(Model.sourcesRowKind(2, 2), "add")
    compare(Model.sourcesRowKind(3, 2), "xtream")
    compare(Model.footerHints({ mode: "sources", cursorKind: "source" }).length, 7)
    var back = Model.onEscape(s).state
    compare(back.mode, "list")
    compare(back.scopeId, "g:UK")
    var add = Model.openAddForm(s)
    compare(add.form.focus, "playlist")
    compare(Model.closeForm(add, "saved").state.mode, "sources")
    compare(Model.closeForm(add, "saved").state.returnMode, "list")
    var rm = Model.startRemove(s, 2)
    compare(rm.mode, "confirmRemove")
    compare(Model.afterRemove(rm, 1).sourceCursor, 0)
    compare(Model.afterRemove(rm, 0).form.origin, "firstRun")
    // UX 1.7: the active source removed while Sources stays open, then Esc
    // -> the first-run form (Saved sources link), not the M1 empty state.
    var stayed = Model.afterRemove(rm, 1)
    compare(stayed.mode, "sources")
    var escUnconfigured = Model.onEscape(stayed, { configured: false })
    compare(escUnconfigured.close, false)
    compare(escUnconfigured.state.mode, "sourceEdit")
    compare(escUnconfigured.state.form.origin, "firstRun")
    compare(escUnconfigured.state.form.focus, "playlist")
    compare(escUnconfigured.state.returnMode, "")
    compare(Model.onEscape(stayed, { configured: true }).state.mode, "list")
    // SR11: a CLI `~` path reconciles and resolves as the active source.
    var tilde = Model.reconcileSources(Model.withCacheLayout(Model.emptyState(), 2), "~/list.m3u", "", "", 1)
    compare(tilde.invalid, null)
    compare(tilde.state.sources[0].kind, "file")
    compare(Model.activeSourceKey(tilde.state, "~/list.m3u"), tilde.added)
    compare(Model.addSource(tilde.state, { playlistUrl: "~/x.m3u" }).code, "relative_path")
    compare(Model.sourceTransient("added", { label: "list.m3u", host: "local file", channelCount: 20, groupCount: 9 }), "Added list.m3u · 20 channels in 9 groups")
    compare(Model.validateUrlForm({ label: "", playlist: "x.test/a", epg: "" }, [], "").error.code, "scheme")
    compare(Model.footerStatus({ configured: true, count: 84, lastUpdated: "09:12", activeLabel: "NAS", sourceCount: 2 }), "NAS · 84 channels · updated 09:12")
  }

  // The EPG helper's warnings[] (epg-status.json) get the same treatment
  // with their own wording; the playlist's win when both have something.
  function test_epgWarnings() {
    var status = Model.parseHelperStatus('{"ok": true, "kind": "epg", "warnings": ["no EPG channel id matches a playlist tvg-id", "see http://u:p@e.test/xmltv.php?x=1"]}', "epg")
    compare(Model.statusWarnings(status), ["no EPG channel id matches a playlist tvg-id", "see e.test"])
    var line = Model.warningLine(Model.statusWarnings(status), "epg")
    compare(line, "Guide data warning: no EPG channel id matches a playlist tvg-id (+1 more)")
    compare(Model.warningLine(["a"], "epg"), "Guide data warning: a")
    compare(Model.warningLine(["a"]), "Playlist warning: a")
    compare(Model.statusWarnings({ ok: false, kind: "epg", warnings: ["x"] }), [])
    compare(Model.footerWarning(["p"], ["e"]), "Playlist warning: p")
    compare(Model.footerWarning([], ["e"]), "Guide data warning: e")
    compare(Model.footerWarning([], []), "")
    compare(Model.footerWarning([], Model.statusWarnings(status)), line)
    // Precedence (UX 6.1) is unchanged: a warning never displaces a playing,
    // refreshing or pending state, and the empty states keep the slot blank.
    compare(Model.footerStatus({ configured: true, count: 8, lastUpdated: "01:53", warning: line }), line)
    compare(Model.footerStatus({ configured: true, count: 8, refreshing: true, warning: line }), "Refreshing" + Model.ELLIPSIS)
    compare(Model.footerStatus({ configured: true, count: 8, epgPending: true, warning: line }), "Guide data loading" + Model.ELLIPSIS)
    compare(Model.footerStatus({ configured: true, count: 8, playingName: "Arte", warning: line }), Model.GLYPHS.play + " Arte" + Model.SEP + "s stop")
    compare(Model.footerStatus({ configured: true, count: 8, transient: "Saved", warning: line }), "Saved")
    compare(Model.footerStatus({ configured: false, count: 0, warning: line }), "")
  }

  // PO-10 / D-PLY-5: an mpvArgs option that hands the stream address to
  // another program is kept (PO-5) and shown on the one warning line the
  // guide already has. This walks the whole path in the V4 engine, exactly
  // as Service.qml composes it and Guide.qml renders it - no reimplementation
  // (CLAUDE.md 12): the strings below are what a user would read.
  function test_playerOptionWarning() {
    var handoff = "mpvArg --ytdl" + Model.MPV_HANDOFF_TEXT
    // Service.qml: playerArgWarnings, derived from the setting itself.
    compare(Model.splitMpvArgs("--profile=low-latency --ytdl=yes").args, ["--profile=low-latency", "--ytdl=yes"])
    compare(Model.splitMpvArgs("--profile=low-latency --ytdl=yes").warnings, [handoff])
    compare(Model.splitMpvArgs("--profile=low-latency").warnings, [])
    compare(Model.splitMpvArgs("--ytdl=no").warnings, [])
    var player = Model.labelWarnings(Model.splitMpvArgs("--ytdl=yes").warnings, "player")
    compare(player, ["Player warning: " + handoff])
    // Service.qml: playlistWarnings = playerArgWarnings ++ playlistLoadWarnings.
    // Guide.qml: warningText = footerWarning(service.playlistWarnings, epgWarningList).
    var alone = Model.footerWarning(player.concat([]), [])
    compare(alone, "Player warning: mpvArg --ytdl hands the stream address to another program")
    compare(Model.footerStatus({ configured: true, count: 8, lastUpdated: "01:53", warning: alone }), alone)
    var both = Model.footerWarning(player.concat(["truncated to 50000 channels"]), ["1 programme dropped"])
    compare(both, alone + " (+1 more)")
    // Without the option nothing changes for anybody else (D-LIVE-18).
    compare(Model.footerWarning([].concat(["truncated to 50000 channels"]), []), "Playlist warning: truncated to 50000 channels")
    compare(Model.footerWarning([], []), "")
    // The value is never shown: it can carry a credentialed URL of its own.
    var proxy = Model.labelWarnings(Model.splitMpvArgs("--ytdl-raw-options=proxy=http://u:pw@prox.test:8080").warnings, "player")
    compare(proxy.length, 1)
    compare(proxy[0].indexOf("prox.test") === -1, true)
    compare(proxy[0], "Player warning: mpvArg --ytdl-raw-options" + Model.MPV_HANDOFF_TEXT)
    // Precedence (UX 6.1 / D-LIVE-22) is untouched: the warning still sits
    // below playing, refreshing and the transient slot.
    compare(Model.footerStatus({ configured: true, count: 8, playingName: "Arte", warning: alone }), Model.GLYPHS.play + " Arte" + Model.SEP + "s stop")
    compare(Model.footerStatus({ configured: true, count: 8, refreshing: true, warning: alone }), "Refreshing" + Model.ELLIPSIS)
  }

  // D-LIVE-19: one body surface at a time. Clearing playlistUrl at runtime
  // takes the rows, the group column and the counts with it, so the setup
  // surface is never drawn over a still-rendered channel list.
  function test_guideSurfaceClearedPlaylist() {
    var loaded = Model.guideSurface({ serviceReady: true, configured: true, channelCount: 10, status: "ready", rowCount: 10, query: "", scopeId: "all", narrow: false, sources: 3 })
    compare(loaded.empty, "")
    compare(loaded.showList, true)
    compare(loaded.showColumn, true)
    compare(loaded.channelCount, 10)
    var cleared = Model.guideSurface({ serviceReady: true, configured: false, channelCount: 10, status: "ready", rowCount: 10, query: "", scopeId: "all", narrow: false, sources: 3 })
    compare(cleared.empty, "unconfigured")
    compare(cleared.hasChannels, false)
    compare(cleared.showList, false)
    compare(cleared.showColumn, false)
    compare(cleared.channelCount, 0)
    compare(cleared.setup, true)
    // The record outlives the cleared setting, so the first-run screen shows
    // `Saved sources (3)` instead of pretending nothing was configured.
    compare(cleared.savedSources, 3)
    compare(Model.footerStatus({ configured: false, count: cleared.channelCount, lastUpdated: "15:13" }), "")
    var first = Model.reconcileSources(Model.withCacheLayout(Model.emptyState(), 2), "http://h.test/a.m3u", "", "", 1)
    var after = Model.reconcileSources(first.state, "", "", first.added, 2)
    compare(after.state.sources.length, 1)
    compare(after.activeKey, "")
    compare(after.invalid, null)
    compare(Model.activeSourceKey(after.state, ""), "")
    // The rest of the state machine is as shipped.
    compare(Model.guideSurface({ serviceReady: false }).empty, "service")
    compare(Model.guideSurface({ serviceReady: true, configured: true, channelCount: 0, status: "loading" }).empty, "loading")
    compare(Model.guideSurface({ serviceReady: true, configured: true, channelCount: 0, status: "error" }).empty, "error")
    compare(Model.guideSurface({ serviceReady: true, configured: true, channelCount: 7, rowCount: 0, query: "sky", scopeId: "all" }).empty, "noMatches")
    compare(Model.guideSurface({ serviceReady: true, configured: true, channelCount: 7, rowCount: 0, query: "", scopeId: "favorites" }).empty, "noFavorites")
    compare(Model.guideSurface({ serviceReady: true, configured: true, channelCount: 7, rowCount: 0, query: "", scopeId: "g:UK" }).empty, "emptyScope")
    compare(Model.guideSurface({ serviceReady: true, configured: true, channelCount: 7, rowCount: 7, narrow: true }).showColumn, false)
    compare(Model.guideSurface({ serviceReady: true, configured: true, channelCount: 7, rowCount: 7, narrow: true }).showList, true)
  }

  // D-LIVE-20 / D-LIVE-21. The host publishes `barConfig` to a plugin from
  // its `shellConfig` change handler (shell.qml:66) and reads it out of a
  // binding declared further down (shell.qml:109). This proves the QML fact
  // that makes that lag inevitable -- a change handler runs BEFORE the
  // bindings that depend on the same property are re-evaluated, whichever
  // order they are declared in -- so a plugin can never rely on the echo of
  // its own write and must apply it itself.
  QtObject {
    id: handlerFirst
    property var cfg: ({ bar: { v: "old" } })
    onCfgChanged: spec.seenFirst.push(handlerFirst.derived ? String(handlerFirst.derived.v) : "(null)")
    readonly property var derived: handlerFirst.cfg && handlerFirst.cfg.bar ? handlerFirst.cfg.bar : ({ v: "none" })
  }

  QtObject {
    id: bindingFirst
    property var cfg: ({ bar: { v: "old" } })
    readonly property var derived: bindingFirst.cfg && bindingFirst.cfg.bar ? bindingFirst.cfg.bar : ({ v: "none" })
    onCfgChanged: spec.seenSecond.push(bindingFirst.derived ? String(bindingFirst.derived.v) : "(null)")
  }

  property var seenFirst: []
  property var seenSecond: []

  function test_hostEchoLagsByOneWrite() {
    seenFirst = []
    seenSecond = []
    handlerFirst.cfg = { bar: { v: "new" } }
    bindingFirst.cfg = { bar: { v: "new" } }
    // The handler saw the PREVIOUS value of the derived binding either way.
    compare(seenFirst, ["old"])
    compare(seenSecond, ["old"])
    // It catches up only after the handler has returned, so the value a
    // handler published is always one write behind.
    compare(String(handlerFirst.derived.v), "new")
    compare(String(bindingFirst.derived.v), "new")
  }

  function test_ownSettingsWriteAppliesLocally() {
    var hostA = Model.settingsFrom({ id: "p", playlistUrl: "http://h.test/a.m3u", epgUrl: "", refreshMinutes: 45 })
    var hostB = Model.settingsFrom({ id: "p", playlistUrl: "http://h.test/b.m3u", epgUrl: "", refreshMinutes: 45 })
    var write = Model.ownWriteFor(hostA, "http://h.test/b.m3u", "")
    // Applied at once, against the host value we wrote on.
    compare(Model.ownWriteInForce(hostA, write), true)
    compare(Model.settingsWithOwnWrite(hostA, write).playlistUrl, "http://h.test/b.m3u")
    compare(Model.settingsWithOwnWrite(hostA, write).refreshMinutes, 45)
    // The late echo of our own value lapses it and changes nothing.
    compare(Model.ownWriteInForce(hostB, write), false)
    compare(Model.settingsWithOwnWrite(hostB, write).playlistUrl, "http://h.test/b.m3u")
    // A foreign write wins.
    var hostC = Model.settingsFrom({ id: "p", playlistUrl: "http://h.test/c.m3u" })
    compare(Model.settingsWithOwnWrite(hostC, write).playlistUrl, "http://h.test/c.m3u")
    // Clearing the active source is the same mechanism (D-LIVE-21).
    compare(Model.settingsWithOwnWrite(hostB, Model.ownWriteFor(hostB, "", "")).playlistUrl, "")
    // Only an entry updateEntryInline can rewrite counts as writable.
    compare(Model.barEntryWritable({ layout: { right: [{ id: "p", playlistUrl: "x" }] } }, "p"), true)
    compare(Model.barEntryWritable({ layout: { right: ["p"] } }, "p"), false)
  }

  // UX 6.3 footer precedence, proved in the Qt engine as well as in node
  // (D-LIVE-22). A cached copy is a degraded state, so
  // `N channels - cached HH:MM - offline` outranks the pending guide-data
  // line and both warning kinds; only a transient, the bounded-search line,
  // playing or a refresh may cover it. This is where the ladder meets the
  // service state machine: Guide.qml raises the rung from the R8 status
  // vocabulary (`stale: serviceStatus === "cached"`), which the service sets
  // for a failed refresh and for a stale cache alike.
  function test_footerPrecedenceCachedOverWarnings() {
    var epgWarn = Model.footerWarning([], ["1 programmes for channels not in the playlist dropped"])
    var bothWarn = Model.footerWarning(["truncated to 50,000 channels"], ["1 programmes for channels not in the playlist dropped"])
    var cached = "8 channels" + Model.SEP + "cached 22:49" + Model.SEP + "offline"
    compare(Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", stale: true, warning: epgWarn }), cached)
    compare(Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", stale: true, warning: bothWarn }), cached)
    compare(Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", stale: true, epgPending: true, warning: bothWarn }), cached)
    compare(Model.footerStatus({ configured: true, count: 8, stale: true, warning: epgWarn }), "8 channels" + Model.SEP + "cached" + Model.SEP + "offline")
    // The rungs above it are unchanged, cached or not.
    compare(Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", stale: true, refreshing: true, warning: epgWarn }), "Refreshing" + Model.ELLIPSIS)
    compare(Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", stale: true, playingName: "Arte", warning: epgWarn }), Model.GLYPHS.play + " Arte" + Model.SEP + "s stop")
    compare(Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", stale: true, transient: "Refreshed", warning: epgWarn }), "Refreshed")
    // A fresh copy leaves both warnings on their own rungs, playlist first.
    compare(Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", warning: bothWarn }), "Playlist warning: truncated to 50,000 channels")
    compare(Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", warning: epgWarn }), "Guide data warning: 1 programmes for channels not in the playlist dropped")
    // An error with no cache still speaks in the body, not the footer (D-LIVE-09).
    compare(Model.footerStatus({ configured: true, count: 0, stale: true, warning: bothWarn }), "")
  }

  // ---- channel numbers (M2-03) ----
  //
  // The point of running these in the Qt engine as well as in node is the
  // character scanner, the integer comparator and the numeric coercions:
  // V4 and node must agree exactly, or a number parses one way in the guide
  // and another way in the unit tests.

  function test_parseChnoSharedVectors() {
    // The same file tests/Model.test.js requires (one fixture, two engines).
    var cases = ChnoCases.CASES
    // A fixture that failed to load would make this test pass by doing nothing.
    verify(cases.length >= 30)
    var ok = 0
    var bad = 0
    for (var i = 0; i < cases.length; i++) {
      var c = cases[i]
      var got = Model.parseChno(c.input)
      compare(got.ok, c.ok, "parseChno(" + JSON.stringify(c.input) + ") " + c.why)
      if (c.ok) {
        ok++
        compare(got.key, c.key, "key of " + JSON.stringify(c.input))
        compare(got.label, c.label, "label of " + JSON.stringify(c.input))
        compare(got.sort, c.sort, "sort of " + JSON.stringify(c.input))
      } else {
        bad++
        compare(got.key, "")
        compare(got.sort, -1)
      }
    }
    verify(ok > 0)
    verify(bad > 0)
    // The V4 engine must not turn the integer sort into a double.
    compare(Model.parseChno("99999.999").sort, 99999999)
    compare(Model.parseChno(12).key, "12")
    compare(Model.parseChno(null).ok, false)
  }

  function test_buildChnoIndex() {
    var idx = spec.chnoIndex
    compare(idx.hasNumbers, true)
    compare(idx.count, 5)
    compare(idx.duplicates, 2)
    compare(idx.maxLabelLen, 3)
    compare(JSON.stringify(idx.order), "[1,4,2,3,0]")
    compare(JSON.stringify(idx.labels), '["7","7.1","12","12","101"]')
    compare(JSON.stringify(idx.byKey["12"]), "[2,3]")
    compare(JSON.stringify(idx.byKey["7"]), "[1]")
    // CN6 / 1.5: junk and absent numbers are simply not in the index.
    compare(spec.channels[5].chnoKey, "")
    compare(spec.channels[6].chnoKey, "")
    compare(spec.channels[1].chnoLabel, "7")
    compare(spec.channels[1].chnoSort, 7000)
    var empty = Model.buildChnoIndex(null)
    compare(empty.hasNumbers, false)
    compare(empty.count, 0)
    compare(empty.maxLabelLen, 0)
  }

  function test_resolveChno() {
    var idx = spec.chnoIndex
    compare(Model.resolveChno(idx, "101", -1).channelIndex, 0)
    compare(Model.resolveChno(idx, "101", -1).kind, "exact")
    // CN7: the number you see is the number you type.
    compare(Model.resolveChno(idx, "007", -1).channelIndex, 1)
    compare(Model.resolveChno(idx, "7", -1).channelIndex, 1)
    // CN9: the duplicate pair cycles off the cursor, statelessly.
    compare(Model.resolveChno(idx, "12", -1).channelIndex, 2)
    compare(Model.resolveChno(idx, "12", 2).channelIndex, 3)
    compare(Model.resolveChno(idx, "12", 2).ordinal, 2)
    compare(Model.resolveChno(idx, "12", 3).channelIndex, 2)
    compare(Model.resolveChno(idx, "12", -1).matches, 2)
    // A half-typed subchannel previews its first child; CN8 folds the comma.
    compare(Model.resolveChno(idx, "7.", -1).channelIndex, 4)
    compare(Model.resolveChno(idx, "7,1", -1).channelIndex, 4)
    compare(Model.resolveChno(idx, "7.1", -1).kind, "exact")
    // A prefix picks the lowest number, not the first row.
    compare(Model.resolveChno(idx, "1", -1).label, "12")
    compare(Model.resolveChno(idx, "1", -1).kind, "prefix")
    // 5.2: the guide cycles off a channel id, because channelOrder "number"
    // hands it a reordered array in which a playlist index names nothing.
    compare(Model.chnoIdAt(idx, 2), "3")
    compare(Model.chnoIdAt(idx, 5), "")
    compare(Model.resolveChno(idx, "12", "3").channelIndex, 3)
    compare(Model.resolveChno(idx, "12", "4").channelIndex, 2)
    compare(Model.resolveChno(idx, "205", -1).kind, "none")
    compare(Model.resolveChno(idx, "", -1).kind, "none")
    compare(Model.resolveChno(Model.buildChnoIndex([]), "1", -1).kind, "none")
    // CN2.5, the early commit.
    compare(Model.chnoUnambiguous(idx, "101"), true)
    compare(Model.chnoUnambiguous(idx, "7"), false)
    compare(Model.chnoUnambiguous(idx, "1"), false)
  }

  function test_orderChannelsAndColumn() {
    // CN5.2: identity for the shipped default, with no copy.
    compare(Model.orderChannels(spec.channels, "playlist", spec.chnoIndex) === spec.channels, true)
    compare(Model.orderChannels(spec.channels, "number", Model.buildChnoIndex([])) === spec.channels, true)
    var ordered = Model.orderChannels(spec.channels, "number", spec.chnoIndex)
    var ids = []
    for (var i = 0; i < ordered.length; i++) ids.push(ordered[i].id)
    // 7, 7.1, 12, 12, 101, then the unnumbered tail in playlist order.
    compare(ids.join(","), "2,5,3,4,1,6,7")
    // The input is untouched.
    compare(spec.channels[0].id, "1")
    compare(Model.channelOrderOf(" Number "), "number")
    compare(Model.channelOrderOf("alpha"), "playlist")
    // CN4.2: the width formula, in Style.space units.
    compare(Model.chnoColumnUnits(spec.chnoIndex.maxLabelLen), 32)
    compare(Model.chnoColumnUnits(0), 24)
    compare(Model.chnoColumnUnits(99), 56)
  }

  function test_numberEntryAndCopy() {
    var e = Model.pushNumberKey(Model.numberEntry(), "1", { scopeId: "g:UK", query: "sky", cursorIndex: 4 })
    compare(e.changed, true)
    compare(e.entry.buffer, "1")
    e = Model.pushNumberKey(e.entry, "0", { scopeId: "all", cursorIndex: 99 })
    compare(e.entry.buffer, "10")
    // The snapshot is the one taken on the FIRST key.
    compare(e.entry.scopeId, "g:UK")
    compare(e.entry.cursorIndex, 4)
    var back = Model.popNumberKey(e.entry)
    compare(back.buffer, "1")
    var gone = Model.popNumberKey(back)
    compare(gone.active, false)
    compare(gone.scopeId, "g:UK")
    compare(Model.cancelNumberEntry(e.entry).scopeId, "")
    compare(Model.isNumberEntryKey("."), true)
    compare(Model.isNumberEntryKey("-"), false)
    compare(Model.isNumericQuery("7,1"), true)
    compare(Model.isNumericQuery("7.1234"), false)
    // CN6.2 / 6.3, the strings the guide renders.
    compare(Model.footerStatus({ configured: true, count: 7, transient: "Stopped",
      numberEntry: { active: true, buffer: "12", kind: "exact", label: "12", name: "One America", matches: 2, ordinal: 1 } }),
      "Channel 12" + Model.SEP + "One America (1 of 2)")
    compare(Model.chnoStatus("none", "205", "", 0, 0, true), "No channel 205")
    compare(Model.chnoStatus("noNumbers", "", "", 0, 0, false), "No channel numbers in this playlist")
    // M2-05 section 5 inserts `p pip` after `s stop`, so the digits hint
    // moved one along and both lists grew by one.
    compare(Model.footerHints({ mode: "list", hasNumbers: true })[9][0], "0-9")
    compare(Model.footerHints({ mode: "list" }).length, 10)
    compare(Model.footerHints({ mode: "list", hasNumbers: true }).length, 11)
    compare(Model.footerHints({ mode: "list", hasNumbers: true, numberEntry: { active: true } }).length, 5)
    compare(Model.rowAccessibleName({ name: "BBC One HD", chno: "101" }), "Channel 101, BBC One HD")
    compare(Model.rowAccessibleName({ name: "The One Show", chno: "" }), "The One Show")
  }

  // CN21 / D-CHNO-2 in the engine that actually runs the guide. Typing 1015
  // on this fixture auto-commits on 101 (nothing extends it) and the 5 then
  // used to open a NEW entry that tuned somewhere of its own with no error.
  function test_numberEntrySequenceCN21() {
    var entry = Model.numberEntry()
    var resolution = Model.resolveChno(null, "", -1)
    var commits = []
    var keys = "1015"
    for (var i = 0; i < keys.length; i++) {
      var step = Model.numberKeyStep(entry, spec.chnoIndex, keys.charAt(i), { cursorId: "6", cursorIndex: 5, scopeId: "all", query: "" })
      compare(step.changed, true)
      entry = step.entry
      resolution = step.commit ? Model.resolveChno(null, "", -1) : step.resolution
      if (step.commit) {
        commits.push(Model.chnoStatus(step.commit.kind, step.commit.label, "BBC One HD", step.commit.matches, step.commit.ordinal, true))
        // The auto-commit leaves the digit window running, and the buffer armed.
        compare(step.timer, "restart")
        compare(step.entry.active, false)
        compare(step.entry.resume, true)
      }
    }
    // The 5 resumed 101 rather than starting a new number.
    compare(entry.active, true)
    compare(entry.buffer, "1015")
    compare(resolution.kind, "none")
    var done = Model.numberCommitStep(entry, resolution, "BBC One HD", { play: false, reason: "timeout" })
    commits.push(done.plan.status)
    compare(commits, ["Channel 101" + Model.SEP + "BBC One HD", "No channel 1015"])
    // A miss restores the row the user was on before the first digit, and
    // refuses to play whatever the preview passed over (CN1).
    compare(done.plan.restore, true)
    compare(done.plan.play, false)
    compare(done.snapshot.cursorIndex, 5)
    compare(done.entry.resume, false)
    // The instant path, unchanged: 101 alone still commits on its last digit.
    var quick = Model.numberKeyStep(Model.numberKeyStep(Model.numberKeyStep(Model.numberEntry(), spec.chnoIndex, "1", { cursorId: "6" }).entry,
      spec.chnoIndex, "0", {}).entry, spec.chnoIndex, "1", {})
    compare(quick.commit === null, false)
    compare(quick.commit.kind, "exact")
    compare(quick.resolution.channelIndex, 0)
  }

  // CN9 / D-CHNO-1 in V4. The fixture's 12 is a duplicate pair (ids 3 and 4,
  // playlist indices 2 and 3). Typing it again has to reach the twin, and it
  // only can if the cycle is resolved against the cursor as it was before the
  // first digit: "1" previews 101 on the way, moving the live cursor off both.
  function test_duplicateCycleFromTheSnapshotCursor() {
    function typeTwelve(cursorId) {
      var step = Model.numberKeyStep(Model.numberEntry(), spec.chnoIndex, "1", { cursorId: cursorId, cursorIndex: 0 })
      compare(step.commit, null)               // 101 still extends "1"
      return Model.numberKeyStep(step.entry, spec.chnoIndex, "2", {})
    }
    var first = typeTwelve("6")                // parked on a channel with no number
    compare(first.resolution.channelIndex, 2)
    compare(first.commit.ordinal, 1)
    compare(first.commit.matches, 2)
    var second = typeTwelve("3")               // now parked on the first twin
    compare(second.resolution.channelIndex, 3)
    compare(second.commit.ordinal, 2)
    var third = typeTwelve("4")                // and the wrap
    compare(third.resolution.channelIndex, 2)
    compare(third.commit.ordinal, 1)
    // CN20: the verb a script calls must not cycle, whatever the guide does.
    compare(Model.channelByNumber(spec.channels, spec.chnoIndex, "12").id, "3")
    compare(Model.channelByNumber(spec.channels, spec.chnoIndex, "12").id, "3")
  }

  // Gate A1 in the engine that actually runs the guide: the modifier bits
  // here are the real Qt enum values, so this also pins that Model.js's
  // integer copies of them match Qt's.
  function test_numberKeyRouting() {
    var base = { hasNumbers: true, active: false, modifiers: 0 }
    function act(patch) {
      var o = { text: base.text, hasNumbers: base.hasNumbers, active: base.active, modifiers: base.modifiers, backspace: false }
      for (var k in patch) o[k] = patch[k]
      return Model.numberKeyAction(o)
    }
    compare(act({ text: "1" }), "digit")
    // The two that must not be rejected.
    compare(act({ text: "1", modifiers: Qt.ShiftModifier }), "digit")
    compare(act({ text: "1", modifiers: Qt.KeypadModifier }), "digit")
    compare(act({ text: ",", modifiers: Qt.KeypadModifier }), "digit")
    // The three that must be.
    compare(act({ text: "1", modifiers: Qt.ControlModifier }), "pass")
    compare(act({ text: "1", modifiers: Qt.AltModifier }), "pass")
    compare(act({ text: "1", modifiers: Qt.MetaModifier }), "pass")
    // Model.js carries its own integer copies of the Qt bits; they must be
    // the same integers Qt uses, or the mask would silently mean nothing.
    compare(Model.CHNO_CHORD_MASK & Qt.ControlModifier, Qt.ControlModifier)
    compare(Model.CHNO_CHORD_MASK & Qt.AltModifier, Qt.AltModifier)
    compare(Model.CHNO_CHORD_MASK & Qt.MetaModifier, Qt.MetaModifier)
    compare(Model.CHNO_CHORD_MASK & Qt.ShiftModifier, 0)
    compare(Model.CHNO_CHORD_MASK & Qt.KeypadModifier, 0)
    compare(act({ backspace: true, active: true }), "backspace")
    compare(act({ backspace: true, active: false }), "pass")
    compare(act({ text: "5", hasNumbers: false }), "noNumbers")
    // CN1: the destructive outcome this feature could have, refused.
    compare(Model.chnoCommitPlan("none", "205", "", 0, 0, { play: true }).play, false)
    compare(Model.chnoCommitPlan("none", "205", "", 0, 0, { play: true }).restore, true)
    compare(Model.chnoCommitPlan("exact", "101", "Sky", 1, 1, { play: true }).play, true)
  }

  function test_chnoSearchAndSettings() {
    // CN5 / 2.8: the all-digit head insertion, and the shipped 4-argument
    // call unchanged beside it.
    var bare = Model.filterChannels(spec.channels, "101", 200, [])
    compare(bare.rows.length, 0)
    var floated = Model.filterChannels(spec.channels, "101", 200, [], spec.chnoIndex)
    compare(floated.rows.length, 1)
    compare(floated.rows[0].id, "1")
    compare(floated.total, 0)
    compare(Model.filterChannels(spec.channels, "one", 200, [], spec.chnoIndex).rows.length,
            Model.filterChannels(spec.channels, "one", 200, []).rows.length)
    // CN3 / CN2 / 7.1: the three new settings.
    var s = Model.settingsFrom({ id: "x", channelOrder: "number", numberEntryMs: 99999, barShowChannelNumber: "false" })
    compare(s.channelOrder, "number")
    compare(s.numberEntryMs, 5000)
    compare(s.barShowChannelNumber, false)
    compare(Model.settingsFrom({}).numberEntryMs, 2000)
    compare(Model.settingsFrom({}).channelOrder, "playlist")
    compare(Model.settingsFrom({}).barShowChannelNumber, true)
    compare(Model.channelByNumber(spec.channels, spec.chnoIndex, "007").id, "2")
    compare(Model.channelByNumber(spec.channels, spec.chnoIndex, "205"), null)
  }

  // ---- picture in picture (M2-05 10.2) ----
  //
  // The SAME vectors tests/Model.test.js runs, in the engine that actually
  // executes Model.js. Not a duplicate of the node suite: V4 is ES5-only and
  // its JSON, its regexes and its number handling are a different
  // implementation, and a builder that emits a Lua expression is exactly the
  // kind of code where an engine difference would surface as a dispatch the
  // compositor cannot parse - which is the defect this wave exists to fix.
  function test_pictureInPictureGeometry() {
    var rows = PipCases.GEOMETRY
    for (var i = 0; i < rows.length; i++) {
      var got = Model.pipGeometry(PipCases.MONITORS[rows[i].monitor], rows[i].opts)
      compare(JSON.stringify(got), JSON.stringify(rows[i].box), rows[i].why)
    }
    // Section 6, and the clamps behind it.
    compare(Model.pipOptions({ pipCorner: "BOTTOM-LEFT", pipSizePercent: 1e9, pipMargin: -4 }).corner, "bottom-left")
    compare(Model.pipOptions({ pipSizePercent: 1e9 }).sizePercent, 60)
    compare(Model.pipOptions({ pipMargin: -4 }).margin, 0)
    compare(Model.pipOptions({ pipCorner: "middle" }).corner, "top-right")
    compare(Model.settingsFrom({}).pipCorner, "top-right")
    compare(Model.settingsFrom({}).pipSizePercent, 30)
    compare(Model.settingsFrom({}).pipMargin, 16)
    // The monitor lookup the service runs before this, in the same engine.
    // V4's JSON.parse is its own implementation, and this one is handed raw
    // `hyprctl -j monitors` stdout.
    var monitors = JSON.stringify([PipCases.MONITORS.live, PipCases.MONITORS.offset])
    compare(Model.pipFindMonitor(monitors, 4).name, "HDMI-A-1")
    compare(Model.pipFindMonitor(monitors, 9), null)
    compare(Model.pipFindMonitor(monitors, null), null)
    compare(Model.pipFindMonitor("{not json", 0), null)
    compare(JSON.stringify(Model.pipGeometry(Model.pipFindMonitor(monitors, 4), { corner: "bottom-left", sizePercent: 25, margin: 10 })),
            JSON.stringify({ x: 1930, y: 440, w: 480, h: 270 }))
  }

  function test_pictureInPictureBoundary() {
    // PIP7 in V4: a hostile value is refused, never escaped.
    var hostile = PipCases.HOSTILE_ADDRESSES
    for (var i = 0; i < hostile.length; i++) {
      compare(Model.pipExpression("tag", { window: "address:" + hostile[i], tag: "+iptv-pip" }), "", String(hostile[i]))
      compare(Model.pipDispatchArgv("move", { window: "address:" + hostile[i], x: 1, y: 2 }).length, 0, String(hostile[i]))
    }
    var coords = PipCases.HOSTILE_COORDS
    for (var c = 0; c < coords.length; c++) {
      compare(Model.pipExpression("move", { window: "address:" + PipCases.PLAYER_ADDRESS, x: coords[c], y: 0 }), "", String(coords[c]))
    }
    compare(Model.pipExpression("move", { window: "address:" + PipCases.PLAYER_ADDRESS, x: 940, y: 42 }),
            "hl.dsp.window.move({ window = \"address:0x559c6893d940\", x = 940, y = 42 })")
    // D-PIP-1: one argv item after `dispatch`, and the namespace focus really
    // lives at. Two bare tokens are what did not work.
    var focus = Model.focusPlayerArgv()
    compare(focus.length, 3)
    compare(focus[0] + " " + focus[1], "hyprctl dispatch")
    compare(focus[2], "hl.dsp.focus({ window = \"class:omarchy-iptv\" })")
    compare(focus[2], Model.pipExpression("focus", { window: Model.PIP_CLASS_SELECTOR }))
  }

  function test_pictureInPicturePlan() {
    var live = Model.pipFindWindow(JSON.stringify([PipCases.CLIENTS.otherApp, PipCases.CLIENTS.tiled]), PipCases.PLAYER_PID)
    compare(live.ok, true)
    compare(live.address, PipCases.PLAYER_ADDRESS)
    compare(live.tags.join(","), "default-opacity")
    compare(Model.pipFindWindow(JSON.stringify([PipCases.CLIENTS.foreign]), PipCases.PLAYER_PID).reason, "no_window")
    compare(Model.pipFindWindow(JSON.stringify([PipCases.CLIENTS.tiled, PipCases.CLIENTS.twin]), PipCases.PLAYER_PID).reason, "ambiguous")
    compare(Model.pipFindWindow("{not json", PipCases.PLAYER_PID).reason, "bad_clients")

    var geo = Model.pipGeometry(PipCases.MONITORS.live, Model.pipOptions({}))
    var snapshot = Model.pipSnapshotFor(live)
    var enter = Model.pipPlan(live, null, geo, "on")
    compare(enter.length, 6)
    compare(enter[1][2], "hl.dsp.window.resize({ window = \"address:0x559c6893d940\", x = 410, y = 230 })")
    compare(enter[2][2], "hl.dsp.window.move({ window = \"address:0x559c6893d940\", x = 940, y = 42 })")
    // PIP10: the float and pin steps are conditional on a fresh read, because
    // the action argument is ignored and a blind toggle would undo them.
    var inPip = Model.pipFindWindow(JSON.stringify([PipCases.CLIENTS.inPip]), PipCases.PLAYER_PID)
    compare(Model.pipPlan(inPip, null, geo, "on").length, 4)
    compare(Model.pipActive(inPip), true)
    compare(Model.pipActive(Model.pipFindWindow(JSON.stringify([PipCases.CLIENTS.userPopped]), PipCases.PLAYER_PID)), false)
    compare(Model.pipResolveIntent("toggle", inPip), "off")

    // D-PIP-4 / 4.7 step 3. The engine the service actually runs in, asked
    // the question a shell that has just restarted has to answer: the
    // window is still in the corner and this process has no memory of it.
    // `status.pip.on` said false on thirty consecutive samples here.
    var fresh = Model.pipDeriveState(JSON.stringify([PipCases.CLIENTS.foreign, PipCases.CLIENTS.inPip]),
                                     PipCases.PLAYER_PID, Model.PIP_CLASS)
    compare(fresh.decided, true)
    compare(fresh.on, true)
    compare(fresh.address, PipCases.PLAYER_ADDRESS)
    compare(Model.barTooltip({ playing: true, name: "BBC One", pip: fresh.on }).split("\n")[1], Model.PIP_TOOLTIP_ON)
    // And back down again when the user tiled it while this shell was dead.
    compare(Model.pipDeriveState(JSON.stringify([PipCases.CLIENTS.tiled]), PipCases.PLAYER_PID, Model.PIP_CLASS).on, false)
    // A read that could not see OUR window decides nothing, rather than
    // announcing "off" on the strength of having seen nothing.
    compare(Model.pipDeriveState("{not json", PipCases.PLAYER_PID, Model.PIP_CLASS).decided, false)
    compare(Model.pipDeriveState(JSON.stringify([PipCases.CLIENTS.tiled, PipCases.CLIENTS.twin]),
                                 PipCases.PLAYER_PID, Model.PIP_CLASS).reason, "ambiguous")
    compare(Model.pipDeriveGate({ pid: 0 }).code, "no_pid")
    compare(Model.pipDeriveGate({ pid: PipCases.PLAYER_PID, busy: true }).code, "busy")
    compare(Model.pipDeriveGate({ pid: PipCases.PLAYER_PID }).ok, true)

    var exit = Model.pipPlan(inPip, snapshot, geo, "off")
    compare(exit.length, 3)
    compare(exit[0][2], "hl.dsp.window.tag({ window = \"address:0x559c6893d940\", tag = \"-iptv-pip\" })")
    compare(exit[1][2], "hl.dsp.window.pin({ window = \"address:0x559c6893d940\" })")
    compare(exit[2][2], "hl.dsp.window.float({ window = \"address:0x559c6893d940\" })")

    // PIP11: the only definition of success is the state read back.
    compare(Model.pipVerify(inPip, "on", geo).ok, true)
    compare(Model.pipVerify(Model.pipFindWindow("[]", PipCases.PLAYER_PID), "on", geo).reason, "no_window")
    compare(Model.pipResultCode(Model.pipVerify(inPip, "on", { x: 0, y: 0, w: 410, h: 230 }), "on"), "dispatch_failed")
    compare(Model.pipDispatchAccepted("ok"), true)
    compare(Model.pipDispatchAccepted("warning: =[C]:-1: Window does not qualify to be pinned"), false)

    // 4.5 / 4.6: the mpv half and the reply reader, in V4's JSON.
    compare(JSON.stringify(Model.pipMpvCommands("off", { mpvArgs: "--no-auto-window-resize" })[0]),
            JSON.stringify(["set_property", "auto-window-resize", false]))
    compare(Model.pipRestoreAutoResize("--auto-window-resize=no"), false)
    compare(Model.pipRestoreAutoResize(""), true)
    compare(Model.pipParseSnapshot(JSON.stringify(snapshot)).size.join(","), "650,718")
    compare(Model.pipParseSnapshot("{not json"), null)
    compare(Model.parsePlayerReply("{\"error\":\"success\",\"data\":{\"active\":true},\"request_id\":42}").requestId, 42)
    compare(Model.parsePlayerReply("{\"event\":\"start-file\"}"), null)

    // Section 5: the copy and the key, in the engine the guide runs in.
    compare(Model.listLetterAction("p"), "pip")
    compare(Model.listLetterAction("P"), "pip")
    compare(Model.listLetterAction("z"), "")
    compare(Model.pipStatusText("nothing_playing"), "Nothing playing")
    compare(Model.pipStatusText("no_compositor"), "Picture in picture needs Hyprland")
    compare(Model.pipKeyRequest({ available: true, playing: false }).code, "nothing_playing")
    compare(Model.pipKeyRequest({ available: true, playing: true }).ok, true)
    compare(Model.barTooltip({ configured: true, playing: true, name: "Sky", pip: true }), "Playing Sky\nPicture in picture: on")
    compare(Model.barTooltip({ configured: true, playing: true, name: "Sky" }), "Playing Sky")
  }

  function test_formatting() {
    compare(Model.formatCount(1204), "1,204")
    compare(Model.epgFraction(150, 100, 200), 0.5)
    compare(Model.epgFields({ now: { title: "Old", start: 1, stop: 10 } }, 20).nowTitle, "")
    compare(Model.rowDetail({ showGroup: true, group: "UK", nowTitle: "X", nextTitle: "Y" }), "UK · Now: X · Next: Y")
    compare(Model.footerStatus({ count: 5, truncated: true, resultTotal: 1240, cap: 200 }), "First 200 of 1,240 · keep typing")
    compare(Model.barGlyph({ playing: true }), Model.GLYPHS.tvPlay)
  }
}
