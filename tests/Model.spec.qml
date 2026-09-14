import QtQuick
import QtTest
import "../Model.js" as Model

// Proves Model.js loads inside the Qt QML engine (no ES module syntax, no
// node-only globals) and that the QML-side results match the node tests:
// normalization vectors, ranking tiers, the two-mode keyboard state machine,
// scope transitions, the zap ring, settings clamps and mpv argv.
// Run: QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml
TestCase {
  id: spec
  name: "IptvModel"

  readonly property var channels: Model.prepareChannels([
    { id: "1", name: "BBC One HD", group: "UK", searchKey: "bbc one hd uk" },
    { id: "2", name: "CBBC", group: "Kids", searchKey: "cbbc kids" },
    { id: "3", name: "One America", group: "US", searchKey: "one america us" },
    { id: "4", name: "Sky News", group: "News", searchKey: "sky news news" },
    { id: "5", name: "BBC Two", group: "UK", searchKey: "bbc two uk" },
    { id: "6", name: "The One Show", group: "UK", searchKey: "the one show uk" },
    { id: "7", name: "Rai Uno", group: "One World", searchKey: "rai uno one world" }
  ])
  readonly property var userState: ({ version: 1, favorites: ["5", "1"], recents: [{ id: "4", name: "Sky News", at: 1 }], lastPlayed: null })

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
    var argv = Model.buildMpvArgv({ socketPath: "/tmp/s", name: "N", url: "http://u", headers: { "User-Agent": "VLC" }, extraArgs: [] })
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
    compare(Model.validateSourceUrl("http://h.test/a b").url, "http://h.test/ab")
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

  function test_formatting() {
    compare(Model.formatCount(1204), "1,204")
    compare(Model.epgFraction(150, 100, 200), 0.5)
    compare(Model.epgFields({ now: { title: "Old", start: 1, stop: 10 } }, 20).nowTitle, "")
    compare(Model.rowDetail({ showGroup: true, group: "UK", nowTitle: "X", nextTitle: "Y" }), "UK · Now: X · Next: Y")
    compare(Model.footerStatus({ count: 5, truncated: true, resultTotal: 1240, cap: 200 }), "First 200 of 1,240 · keep typing")
    compare(Model.barGlyph({ playing: true }), Model.GLYPHS.tvPlay)
  }
}
