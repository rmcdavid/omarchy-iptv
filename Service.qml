// The socket observer builds its Socket from a Component (spike caveat C1),
// and that nested component reaches the ids of this file (root, the retry
// timer). Bound is the semantics we want and the semantics we already have:
// there is exactly one creation context here.
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import "Model.js" as Model

// Service.qml -- headless state owner for io.github.rmcdavid.iptv
// (manifest kind "service", keepLoaded). Exactly one instance per shell,
// however many monitors or bars exist. It owns:
//   - the settings snapshot, derived from shell.barConfig (ARCHITECTURE.md, decision 7)
//   - the channels / EPG caches  (FileView over ~/.cache/omarchy-iptv)
//   - favorites / recents / lastPlayed (FileView over ~/.local/state/omarchy-iptv)
//   - every helper run            (python3 bin/omarchy-iptv <subcommand>)
//   - the DETACHED player and the now-playing state (ARCHITECTURE-PLAYER.md)
//   - the plugin IPC target       (omarchy-shell io.github.rmcdavid.iptv <fn>)
// Guide.qml receives this object as `service` (shell.qml injects it on load);
// BarWidget.qml resolves it through bar.shell.serviceFor(moduleName).
//
// Privacy (R12): nothing here ever logs, notifies or exposes a playlist,
// EPG or stream URL beyond scheme + host. Argv arrays only (section 8).
//
// M2-02: mpv is no longer our child. It is spawned by the helper as a
// setsid'd grandchild (`player start`), so it survives `omarchy restart
// shell`; this service observes it over its own 0600 JSON IPC socket and
// reattaches on start (`player probe`). Nothing here may ever exec mpv:
// `player start` is the only spawn path, and its /proc scan plus flock are
// what keep a second window impossible (requirement 1).
//
// keepLoaded: edits to THIS file only apply after `omarchy restart shell`.
Item {
  id: root

  // Injected by shell.qml ensureService(): the capability-scoped
  // PluginShellApi and the public manifest. Both can arrive after creation.
  property var shell: null
  property var manifest: null

  readonly property string pluginId: manifest && manifest.id ? String(manifest.id) : "io.github.rmcdavid.iptv"
  readonly property string home: Quickshell.env("HOME")
  readonly property string cacheDir: (Quickshell.env("XDG_CACHE_HOME") || (home + "/.cache")) + "/omarchy-iptv"
  readonly property string stateDir: (Quickshell.env("XDG_STATE_HOME") || (home + "/.local/state")) + "/omarchy-iptv"
  readonly property string runtimeDir: (Quickshell.env("XDG_RUNTIME_DIR") || cacheDir) + "/omarchy-iptv"
  readonly property string socketPath: runtimeDir + "/mpv.sock"
  readonly property string helperPath: decodeURIComponent(Qt.resolvedUrl("bin/omarchy-iptv").toString().replace(/^file:\/\//, ""))

  // ---- timing constants, in one place (UX.md 5.9)
  readonly property int refreshDebounceMs: 300
  readonly property int epgRecomputeMs: 5 * 60 * 1000
  readonly property int epgTickMs: 30 * 1000
  readonly property int healthCheckMs: 10 * 1000
  // The shutdown ladder's grace periods live with its reducer in Model.js
  // (STOP_QUIT_GRACE_MS, STOP_KILL_GRACE_MS, HEALTH_SKIPS_BEFORE_RESTART);
  // the ladder itself now runs inside one detached helper (4.9).
  // ---- detached player timings (ARCHITECTURE-PLAYER.md 4.4, 4.7, spike C6)
  readonly property int playerSocketRetryMs: 250   // reattach tick
  readonly property int playerSocketTries: 12      // burst cap: 12 x 250 ms = 3 s (C6)
  readonly property int playerTimeoutMs: 12 * 1000 // watchdog for one player verb
  readonly property int playerProbeRetryMs: 500    // the one ambiguous-probe re-read (4.5)
  readonly property int stopSettleMs: 5 * 1000     // backstop that clears `stopping` (4.10)
  readonly property int focusRetryMs: 500
  readonly property int focusRetries: 6
  readonly property int healthFailuresBeforeRestart: 2
  // Watchdog bound for one playlist/EPG helper run (S-05). The helper has
  // its own 60 s download deadline; this is the belt and braces for a
  // helper that is stuck anywhere else (DNS, TLS, a parser bug).
  readonly property int helperTimeoutMs: 180 * 1000

  // ---- settings (decision 7, R2). shell.barConfig is refreshed by the host on
  // every shell.json change (shell.qml syncPluginApis), so these re-evaluate
  // after `omarchy bar set io.github.rmcdavid.iptv <key> <value>`.
  //
  // D-LIVE-20 / D-LIVE-21: that refresh is one shellConfig write behind. The
  // host publishes barConfig from `onShellConfigChanged` (shell.qml:66),
  // which runs before the `barConfig` binding it reads (shell.qml:109) has
  // re-evaluated, so every plugin gets the previous bar. An external write
  // is flushed by the write after it (the user config FileView re-reads the
  // foreign change and assigns shellConfig again); the plugin's own write is
  // the last one there is, so its echo never comes. `settings` therefore
  // lays our own successful write over the host's value until the host
  // catches up or somebody else writes (Model.settingsWithOwnWrite).
  readonly property var hostSettings: Model.settingsFrom(Model.findBarEntry(shell ? shell.barConfig : null, pluginId))
  property var ownWrite: null                          // { base, value }: our write, applied locally
  readonly property var settings: Model.settingsWithOwnWrite(hostSettings, ownWrite)
  readonly property string playlistUrl: settings.playlistUrl
  readonly property string epgUrl: settings.epgUrl
  readonly property int refreshMinutes: settings.refreshMinutes
  readonly property string mpvArgs: settings.mpvArgs
  readonly property int maxRecents: settings.maxRecents
  readonly property int barLabelMaxWidth: settings.barLabelMaxWidth
  readonly property bool showChannelName: settings.showChannelName
  readonly property bool configured: playlistUrl !== ""
  // The EPG URL in force for the active source: the active record's own
  // epgUrl once the history knows the source (an EPG URL belongs to the
  // source it was set for, D-SRC-10; the settings follow it through
  // reconcile), the raw setting while no record exists or the setting does
  // not validate (the helper then reports it, as in 0.1.0).
  readonly property string activeEpgUrl: {
    var rec = Model.findSource(root.userState.sources, root.activeSourceKey)
    if (!rec) return root.epgUrl
    if (root.epgUrl !== "" && Model.normalizeSourceUrl(root.epgUrl, { kind: "epg", origin: "cli" }) === "") return root.epgUrl
    return String(rec.epgUrl || "")
  }
  readonly property bool epgConfigured: activeEpgUrl !== ""
  // scheme + host only; safe to render anywhere
  readonly property string sourceLabel: Model.sourceLabel(playlistUrl)
  readonly property string sourceHost: Model.hostOf(playlistUrl)

  // ---- sources (M2-01, ARCHITECTURE-SOURCES.md section 4, rulings SR1-SR9).
  // The active source is still `playlistUrl` / `epgUrl` on the bar entry
  // (D1); the history lives in userState.sources (state.json v2, D2); each
  // source has its own cache directory under cacheDir/sources/<key>/ (D5).
  // The guide binds `sources` (view objects, SR1) and `activeSourceId`; it
  // never sees a state record or a URL outside sourceForEdit().
  readonly property bool debugTiming: Quickshell.env("OMARCHY_IPTV_DEBUG") === "1"
  readonly property int epgMaxAgeSec: 86400            // inactive sources' EPG files are aged by `cache prune`
  readonly property int switchTimeoutMs: 5 * 1000      // `switching` is released by the first cache load; this is the backstop
  property bool stateLoaded: false                     // stateFile applied once (v2 parsed, reconciled)
  property bool cacheReady: false                      // `cache migrate` done (or not needed) for this state file
  property bool cacheMigrating: false
  property bool pruned: false
  property bool pendingFreshness: false                // a cache swap is in flight: decide on a refresh from playlist-status.json
  property bool switching: false                       // between a committed switch and the new cache's first load / failure
  property string probingKey: ""                       // record a probe concerns ("" when idle); for a URL edit the record being edited
  property string probeDirKey: ""                      // key whose cache directory the probe writes into
  property string probeMode: ""                        // add | edit | switch | retry
  property bool probeCommit: false
  property bool probeCancelled: false
  property bool probeTimedOut: false
  property var probeAdd: null                          // pending record of an add probe (recorded only when it succeeds, SR23)
  property var probeEdit: null                         // pending replacement record of a URL edit (applied only when its probe succeeds, SR7)
  property var sourceErrors: ({})                      // session-only { key: reason }, URL-free (Model.statusReason)
  property var settingsInvalid: null                   // validation result when playlistUrl is set but invalid (D16, SR8)
  // Snapshot of the settings the last reconcile() saw (D-SRC-02 / D-SRC-10):
  // which of playlistUrl / epgUrl changed in one settings write decides
  // whether the epgUrl is adopted; the active key it resolved is the
  // `previousActiveKey` of the next run (never a binding read mid-update).
  property bool reconciled: false
  property string reconciledPlaylistUrl: ""
  property string reconciledEpgUrl: ""
  property string reconciledActiveKey: ""
  property var cacheQueue: []                          // FIFO of { args, onDone } for cacheProc (section 4.7)
  property var cacheJob: null
  property var recentSaves: []                         // texts this service wrote to state.json (own-write reloads are skipped)
  property double switchStartedAt: 0
  property double switchReadMs: 0                      // debug timing: file read, parse+prepare+index, binding fan-out
  property double switchParseMs: 0
  property double switchAssignMs: 0
  // Two-entry LRU of prepared channel data keyed by the exact channels.json
  // text (section 4.5 mitigation): switching back to a source skips
  // parse + prepare + index. A refresh rewrites the file, so a stale entry
  // simply never matches again.
  property var preparedLru: []
  readonly property int preparedLruSize: 2
  readonly property bool probing: sourceProbeProc.running
  readonly property string probingId: probingKey
  readonly property string activeSourceKey: Model.activeSourceKey(root.userState, root.playlistUrl)
  readonly property string activeSourceId: activeSourceKey
  readonly property string activeSourceLabel: {
    var rec = Model.findSource(root.userState.sources, root.activeSourceKey)
    return rec ? rec.label : root.sourceLabel
  }
  readonly property string activeCacheDir: (root.stateLoaded && root.cacheReady && root.activeSourceKey !== "")
    ? Model.sourceCacheDir(root.cacheDir, root.activeSourceKey) : ""
  readonly property int sourceCount: Model.asList(root.userState.sources).length
  readonly property bool canAddSource: root.sourceCount < Model.LIMITS.sources && !root.probing
  // View objects for the guide (SR1, ordered per SR32); `sourcesChanged` is
  // this property's change signal (SR3) and fires on every state, settings,
  // error or clock change.
  readonly property var sources: Model.sourceViews(root.userState, root.activeSourceKey, root.nowSec, root.sourceErrors)

  // ---- data (read by Guide.qml / BarWidget.qml; never mutated by them)
  property var channels: []                 // Model.prepareChannels output
  property var channelIndex: ({})
  property var channelsMeta: ({})
  property var epgNow: ({})                 // tvg-id -> { now, next }
  property var epgMeta: ({})
  // Named userState: `state` would shadow QQuickItem.state. v2 shape
  // (ARCHITECTURE-SOURCES 2.1); every reducer goes through Model.cloneState.
  property var userState: Model.emptyState()
  property var playlistStatus: ({ ok: false, kind: "playlist", stale: false, error: null })
  property var epgStatus: ({ ok: false, kind: "epg", stale: false, error: null })
  property bool playlistAttempted: false
  property bool epgAttempted: false
  property bool epgLoaded: false
  readonly property bool refreshing: playlistProc.running
  readonly property bool epgRefreshing: epgProc.running
  readonly property bool cacheLoaded: channels.length > 0
  readonly property bool epgPending: epgConfigured && !epgLoaded && (epgProc.running || !epgAttempted)
  readonly property bool playlistFailed: !!(playlistStatus && playlistStatus.ok !== true && playlistStatus.error)
  readonly property bool epgFailed: epgAttempted && !!(epgStatus && epgStatus.ok !== true && epgStatus.error)
  readonly property string lastUpdated: Model.formatClock(playlistStatus && playlistStatus.fetchedAt ? playlistStatus.fetchedAt : (channelsMeta && channelsMeta.generatedAt ? channelsMeta.generatedAt : 0))
  readonly property string statusReason: Model.statusReason(playlistStatus)
  readonly property string statusHost: Model.statusHost(playlistStatus) || root.sourceHost
  readonly property string epgReason: Model.statusReason(epgStatus)
  // R8 status vocabulary: ready | loading | refreshing | cached | error
  readonly property string status: {
    if (!root.configured) return "ready"
    if (!root.cacheLoaded) {
      if (root.playlistFailed) return "error"
      return "loading"
    }
    if (root.playlistFailed || (root.playlistStatus && root.playlistStatus.stale === true)) return "cached"
    if (root.refreshing) return "refreshing"
    return "ready"
  }
  // Wall clock, advanced by the 30 s tick so EPG fractions and now/next
  // boundaries re-evaluate without per-row timers (R8).
  property int nowSec: Math.floor(Date.now() / 1000)

  // ---- playback
  //
  // Liveness (4.7, spike caveat C3). `playerPending` is the synchronous
  // birth edge `mpvProc.running` used to give: startPlayer() sets it in the
  // same turn as the keystroke, so the bar lights up on the same frame as
  // it did when mpv was our child. The death edge is socket EOF, 2-3 ms
  // after mpv dies, instead of a 10 s poll. `playerSocket` is null between
  // attempts (a Socket object is never reused after a failed connect), so
  // every read of it is null-guarded.
  property var nowPlaying: null             // { id, name, group, launchedFrom, since }
  property var playerSocket: null           // the live Socket object, or null (C1)
  property bool playerWanted: false         // arms playerSocketTimer
  property bool playerPending: false        // a start we issued is not observable yet
  readonly property bool playerUp: (root.playerSocket !== null && root.playerSocket.connected) || root.playerPending
  readonly property bool playing: playerUp && nowPlaying !== null
  property var failedAt: ({})               // session-only { id: "HH:MM" } (R11)
  // PO-3 lost a race and is waiting for state.json (see markDeadSession()):
  // the probe answered "no player" before the state FileView loaded, so the
  // verdict has to be re-run from applyUserState() once there is a file to
  // decide on.
  property bool deadSessionPending: false
  property bool userStopped: false
  property bool relaunchPending: false
  property bool relaunched: false
  property int healthFailures: 0
  property bool mpvAvailable: true
  property bool wantFocus: false
  property int focusAttempts: 0
  property var pendingPlayId: ""
  property var previousPlaying: null       // restored when a switch over IPC fails
  property string controlKind: ""
  property var mpvStderrTail: []
  property string lastError: ""
  property bool manualRefresh: false
  property bool manualEpgRefresh: false
  property bool playlistRerun: false
  property bool epgRerun: false
  property bool playlistTimedOut: false     // set by the watchdog before it kills the helper
  property bool epgTimedOut: false
  property bool dirsReady: false
  property bool stateSavePending: false
  // D-LIVE-15: a `play` over IPC that finds no socket (player just
  // relaunched) or no answer is retried with backoff.
  property int playRetries: 0
  readonly property int relaunchDelayMs: 200
  readonly property int playRetryBaseMs: 300
  readonly property int playRetryMax: 3        // 300 + 600 + 900 ms = 1.8 s
  // 4.10: the intent sequence number. Service.qml is its only issuer; the
  // helper only compares and records it, so a `stop` and a `play` that reach
  // two detached helpers out of order still execute in the order the user
  // issued them. It survives a restart through `player probe`'s reply.
  property int playSeq: 0
  // `stopping` keeps its name and its four read sites; what changed is its
  // source. It is true from the keystroke until socket EOF confirms the
  // death (or the 5 s backstop), and while it is true a play() always
  // starts a fresh player instead of zapping a dying socket (4.10).
  property real stopAt: 0
  readonly property bool stopping: stopAt > 0
  property int healthSkips: 0
  // The event router's state (4.8). `entryOwners` maps mpv's own
  // playlist_entry_id to the channel that load was for, so a failure that
  // arrives after the user has zapped away still names the right channel;
  // the gate FAILS OPEN, so an unknown id degrades the name and never
  // suppresses the notification.
  property int currentEntryId: 0
  property var entryOwners: ({})
  property var lastEndFile: null            // { entryId, reason, fileError }
  property bool playerIdle: false           // observed idle-active, informational
  property string playerKind: ""            // which player verb is in flight
  property bool probeRetried: false         // the one ambiguous-probe re-read (4.5)
  property bool reconcilePending: false     // resolve nowPlaying once the cache lands
  property string playerSourceKey: ""       // the source the recovered stash belongs to
  property int playerSocketError: 0         // last QLocalSocket::LocalSocketError, diagnostics only
  // A stop whose EOF never came, so the ladder did not end the player. The
  // stop is detached and its reply is by design unobservable, so this is
  // the only way to notice one that was refused (4.9, 4.10).
  property bool stopConfirmPending: false
  // Whose failure has already been toasted for this play. `player start`'s
  // own first-load window and socket EOF are two independent detectors of
  // the same dead stream (4.8 signals 1 and 3) and either can win the race;
  // this keeps the user's toast count at one.
  property string notifiedFailureId: ""
  // Warnings of the last successful playlist load (D-LIVE-18), URL-free;
  // the guide shows them until the next successful load without warnings.
  // A failed refresh keeps them: the cache in use is still that load's.
  property var playlistWarnings: []
  // The same for the EPG helper's `warnings[]` (epg-status.json carries the
  // window's warnings on every successful run, `--now-only` included), shown
  // by the guide as `Guide data warning: ...` and cleared by the next clean
  // EPG load, by a cleared epgUrl and by a source swap.
  property var epgWarnings: []

  // Emitted after a successful playlist helper run; the guide shows
  // `Refreshed - N channels` for a manual refresh (UX 6.1, D-LIVE-05).
  signal playlistRefreshed(int channelCount, bool manual)

  // ---- sources signals (SR3). Payloads are URL-free: `reason` comes from
  // Model.statusReason, `host` from the validator.
  //   sourceProbeFinished({ ok, id, channelCount, groupCount, reason, host,
  //                         cancelled, replacedId }) after an add / URL edit /
  //     never-fetched switch / retry probe; on ok the switch is committed.
  //   sourceSwitched(id) once the new source's cache (or its absence) is in
  //     `channels`. sourceRemoved(id). sourcesPersistFailed(reason) when
  //     updateEntryInline refused a change ("persist_failed").
  signal sourceProbeFinished(var result)
  signal sourceSwitched(string id)
  signal sourceRemoved(string id)
  signal sourcesPersistFailed(string reason)
  // Answer to requestClipboard() (the wl-paste fallback of D9): the raw
  // clipboard text for the guide to sanitize; never logged.
  signal clipboardText(string text)

  // ------------------------------------------------------------ public API (R9)

  // Start (or switch to) a channel by id. `keepOpen` true = preview from the
  // guide (no focus change); false = close-and-focus semantics, the service
  // only does the focus part. `launchedFrom` is the zap ring scope
  // (Model.launchScope); defaults to the channel's own group.
  function play(id, keepOpen, launchedFrom) {
    var channel = root.channelIndex[String(id || "")]
    if (!channel || !channel.url) return false
    if (!root.mpvAvailable) {
      whichProc.running = true
      root.notify("mpvMissing", {})
      return false
    }
    var key = Model.channelId(channel)
    // Enter on the row already playing: no reload, just focus (UX 8 #4).
    // A false negative here only costs one redundant `player start`, which
    // adopts the live player and re-zaps it (4.7).
    if (root.playerUp && root.nowPlaying && root.nowPlaying.id === key) {
      // Re-selected from another list: the zap ring follows the list the
      // user is in (UX 3.4, D-LIVE-12). A new object so bindings notice.
      var from = String(launchedFrom || "")
      if (from !== "" && from !== String(root.nowPlaying.launchedFrom)) {
        root.nowPlaying = {
          id: root.nowPlaying.id,
          name: root.nowPlaying.name,
          group: root.nowPlaying.group,
          launchedFrom: from,
          since: root.nowPlaying.since
        }
      }
      if (!keepOpen) root.focusPlayer()
      return true
    }
    var nowSec = Math.floor(Date.now() / 1000)
    root.userStopped = false
    root.relaunchPending = false
    root.relaunched = false
    root.playRetries = 0
    relaunchTimer.stop()
    playRetryTimer.stop()
    root.healthFailures = 0
    root.lastError = ""
    root.failedAt = Model.withoutFailed(root.failedAt, key)
    root.notifiedFailureId = ""
    // A play cancels a pending stop-confirmation: the player that is coming
    // up is wanted, whatever the one before it did.
    root.stopConfirmPending = false
    root.playSeq += 1                       // every play is a new intent (4.10)
    root.previousPlaying = root.playerUp ? root.nowPlaying : null
    root.nowPlaying = {
      id: key,
      name: String(channel.name || ""),
      group: Model.primaryGroup(channel),
      launchedFrom: String(launchedFrom || "") || Model.groupScopeId(Model.primaryGroup(channel)),
      since: nowSec
    }
    root.userState = Model.recordPlayed(root.userState, channel, root.maxRecents, nowSec)
    root.saveState()
    root.wantFocus = !keepOpen
    // The fork is never a correctness gate (F2): `player start` is
    // idempotent - it adopts a live player and zaps it - so the worst a
    // wrong answer costs is one extra 130 ms helper run. While `stopping`
    // is true we always take the start branch, so a zap can never be
    // written to a socket that is being torn down (4.10).
    if (root.playerUp && !root.stopping) {
      if (controlProc.running) {
        // A zap burst: remember only the last target, applied when the
        // current helper call returns.
        root.pendingPlayId = key
      } else {
        root.runControl("play", root.playArgs(key))
      }
      if (root.wantFocus) root.focusPlayer()
    } else {
      root.startPlayer(channel)
    }
    return true
  }

  // `play --id ... --scope ... --since ...`: the additive session flags make
  // a zap refresh the now-playing stash inside mpv, which is what lets a
  // shell restart recover the channel the user last switched TO rather than
  // the one the player was started with (4.6, requirement 11).
  function playArgs(key) {
    var np = root.nowPlaying
    var args = ["play", "--id", String(key), "--socket", root.socketPath, "--cache-dir", root.activeCacheDir]
    if (np && np.id === key) {
      var scope = String(np.launchedFrom || "")
      if (scope !== "") args = args.concat(["--scope", scope])
      var since = Math.floor(Number(np.since) || 0)
      if (since > 0) args = args.concat(["--since", String(since)])
    }
    return args
  }

  // The UI contract is unchanged: nowPlaying and the timers clear
  // synchronously, so the bar and the guide drop the channel on the
  // keystroke. The ladder itself - quit, SIGTERM at 2 s, SIGKILL at 4 s -
  // now runs inside ONE detached helper (4.9), which is strictly stronger
  // than the QML version: no rung can be starved behind a busy control
  // channel, the pid comes from /proc so a wedged mpv is reachable, and the
  // ladder completes even if this shell is killed one millisecond from now.
  // A user stop never notifies. Issued unconditionally: `player stop`
  // against nothing is a cheap no-op that also tidies a stale socket.
  function stop() {
    root.pendingPlayId = ""
    root.wantFocus = false
    focusTimer.stop()
    // Nothing queued may resurrect the player after a stop (D-LIVE-15).
    relaunchTimer.stop()
    playRetryTimer.stop()
    playerSocketTimer.stop()
    root.relaunchPending = false
    root.playRetries = 0
    root.nowPlaying = null
    root.userStopped = true
    root.playerPending = false
    // Stop hunting for a socket, but keep an attached one: its EOF is how
    // we learn the ladder finished (and is what clears `stopping`).
    root.playerWanted = false
    root.playSeq += 1
    root.stopAt = Date.now()
    stopSettleTimer.restart()
    // The user asked for it, so nothing died unattended: the session record
    // has done its job and a reattach must not find it (PO-3 would then mark
    // a perfectly good channel red).
    root.noteSessionOutcome("stopped")
    Quickshell.execDetached(Model.helperArgv(root.helperPath, Model.playerStopArgv(root.socketPath, root.playSeq)))
  }

  // Health verdict: the player is unresponsive. `player restart --from term`
  // runs the ladder and the spawn under ONE lock acquisition, which removes
  // the stop-then-start race two independent detached calls would have; IPC
  // is by definition not answering here, so rung 1 is skipped. The
  // bookkeeping is unchanged: one automatic relaunch per player.
  function restartPlayer() {
    if (!root.playerUp || root.stopping) return
    if (!root.nowPlaying) return
    var channel = root.channelIndex[root.nowPlaying.id]
    if (!channel) return
    if (root.relaunched) {
      // The one automatic relaunch for this player is spent: ladder it down
      // and show idle, which is what the QML ladder did with
      // relaunchPending false (a quit exits 0, i.e. silently).
      console.warn("omarchy-iptv: mpv unresponsive again, stopping the player")
      root.stop()
      return
    }
    if (playerProc.running) {
      // The one player slot is busy (a start or a probe): try again in a
      // moment rather than dropping the verdict.
      root.relaunchPending = true
      relaunchTimer.restart()
      return
    }
    console.warn("omarchy-iptv: mpv unresponsive, restarting player")
    root.healthFailures = 0
    root.healthSkips = 0
    root.relaunchPending = !root.relaunched && root.nowPlaying !== null
    root.relaunched = true
    root.playSeq += 1
    root.issuePlayerSession("restart", channel, "term")
  }

  function toggleFavorite(id) {
    root.userState = Model.withFavorites(root.userState, Model.toggleFavorite(root.userState.favorites, id))
    root.saveState()
    return Model.isFavorite(root.userState, id)
  }

  function removeRecent(id) {
    root.userState = Model.removeRecent(root.userState, id)
    root.saveState()
  }

  // Manual refresh (r, middle click, IPC): notifies on success and failure
  // (R12). Timer refreshes go through refreshPlaylist(false) and notify only
  // on failure.
  function refresh() {
    root.manualRefresh = true
    root.manualEpgRefresh = true
    root.refreshPlaylist(true)
    root.refreshEpg(true)
  }

  // Zap ring (UX 3.4): the list the channel was launched from.
  function zap(delta) {
    if (!root.nowPlaying) return false
    var ring = Model.zapRing(root.channels, root.userState, root.nowPlaying)
    var next = Model.nextInGroup(ring, root.nowPlaying.id, delta)
    if (!next) return false
    return root.play(Model.channelId(next), true, root.nowPlaying.launchedFrom)
  }

  function focusPlayer() {
    Quickshell.execDetached(Model.focusPlayerArgv())
  }

  // Debounced: settings changes, timers and the bar's middle click all funnel
  // through here so the helper never runs twice for one user action.
  // The URL settings are read directly, never through the derived
  // `configured` / `epgConfigured` bindings: from on<Url>Changed those may
  // not have been re-evaluated yet, which is what kept an epgUrl set at
  // runtime from ever loading (D-LIVE-02).
  function refreshPlaylist(force) {
    if (root.playlistUrl === "") return
    if (playlistProc.running) {
      if (force) root.playlistRerun = true
      return
    }
    refreshDebounce.restart()
  }

  function refreshEpg(force) {
    if (root.activeEpgUrl === "") return
    if (epgProc.running) {
      if (force) root.epgRerun = true
      return
    }
    epgDebounce.restart()
  }

  function notify(event, params) {
    var argv = Model.notifyArgv(event, params)
    if (argv) Quickshell.execDetached(argv)
  }

  // JSON summary for the IPC `status` verb; URL-free by construction.
  function statusSummary() {
    return {
      configured: root.configured,
      sourceHost: root.sourceHost,
      status: root.status,
      channels: root.channels.length,
      groups: Model.groupChannels(root.channels).length,
      lastUpdated: root.lastUpdated,
      playing: root.playing,
      nowPlaying: root.nowPlaying,
      // Additive, and URL-free by construction: channel ids, a clock time
      // and booleans. The detached player can only be verified from outside
      // the shell now, so the acceptance gates need the observer's own view
      // (`playing` alone cannot distinguish a birth edge from an attached
      // socket), and the session failure marks the guide paints red.
      failedAt: root.failedAt,
      player: {
        up: root.playerUp,
        pending: root.playerPending,
        attached: root.socketAttached(),
        wanted: root.playerWanted,
        stopping: root.stopping,
        seq: root.playSeq,
        entryId: root.currentEntryId
      },
      favorites: root.userState.favorites.length,
      recents: root.userState.recents.length,
      epg: { configured: root.epgConfigured, loaded: root.epgLoaded, pending: root.epgPending, reason: root.epgReason, warnings: root.epgWarnings },
      playlistReason: root.statusReason,
      warnings: root.playlistWarnings,
      lastError: root.lastError,
      activeSource: root.activeSourceSummary(),
      sources: Model.sourcesSummary(root.userState, root.activeSourceKey)
    }
  }

  // ------------------------------------------------------------ sources API (SR2)
  // Every action returns { ok, code, message, id } synchronously (`id` = the
  // record concerned, "" when none; `field` names the offending form field
  // on a validation failure). Codes (UX-SOURCES 5.4, SR17, SR18): ok, empty,
  // scheme, invalid, relative_path, unsafe_path, too_long, duplicate (id =
  // the existing record), too_many, label_taken, label_too_long,
  // server_empty, server_scheme, server_path, server_userinfo,
  // server_too_long, user_empty, pass_empty, user_too_long, pass_too_long,
  // busy, unknown_source, not_ready, persist_failed. Messages are
  // Model.sourceErrorMessage sentences. Asynchronous outcomes arrive through
  // sourceProbeFinished.

  function sourceResult(ok, code, message, id, field) {
    var out = { ok: ok, code: code, message: message || "", id: id || "" }
    if (field) out.field = field
    return out
  }

  function sourcesReady() {
    if (!root.stateLoaded || !root.cacheReady) return root.sourceResult(false, "not_ready", Model.sourceErrorMessage("not_ready"), "")
    if (root.probing || root.switching) return root.sourceResult(false, "busy", Model.sourceErrorMessage("busy"), root.probingKey)
    return null
  }

  // Add a source (S1, S2): Model.addSource sanitizes, validates both URLs
  // and the label, refuses duplicates (`duplicate` carries the existing id;
  // the guide retries a never-fetched one through retrySource) and the cap;
  // the new record is held in memory and probed into its own cache
  // directory; it is recorded and the settings are committed only when the
  // probe succeeds (D8, SR7, SR23). `kind: "xtream"` marks a record built
  // by buildXtreamSource (view kind, UX 8.1).
  function addSource(fields) {
    var f = fields || {}
    var gate = root.sourcesReady()
    if (gate) return gate
    var origin = f.kind === "xtream" ? "xtream" : (String(f.origin || "") || "guide")
    var added = Model.addSource(root.userState, { playlistUrl: f.playlistUrl, epgUrl: f.epgUrl, label: f.label, origin: origin }, Math.floor(Date.now() / 1000))
    if (!added.ok) return root.sourceResult(false, added.code, added.message, added.key, root.resultField(added.code, added.message))
    root.probeAdd = Model.findSource(added.state.sources, added.key)
    return root.startProbe(added.key, added.key, "add", true)
  }

  // Edit a source (S4, S6). Label and EPG changes commit at once (an EPG
  // change of the active source is persisted and refreshed in the
  // background). A changed playlist URL yields a replacement record
  // (Model.updateSource) that is probed into the new key's directory first;
  // the history moves to it, the old directory is deleted and the settings
  // follow only when the probe succeeds (SR7).
  function updateSource(id, fields) {
    var key = String(id || "")
    var gate = root.sourcesReady()
    if (gate) return gate
    var rec = Model.findSource(root.userState.sources, key)
    if (!rec) return root.sourceResult(false, "unknown_source", Model.sourceErrorMessage("unknown_source"), key)
    var updated = Model.updateSource(root.userState, key, fields || {}, Math.floor(Date.now() / 1000))
    if (!updated.ok) return root.sourceResult(false, updated.code, updated.message, updated.key, root.resultField(updated.code, updated.message))
    if (!updated.urlChanged) {
      root.userState = updated.state
      root.saveState()
      var next = Model.findSource(updated.state.sources, key)
      if (next && key === root.activeSourceKey && next.epgUrl !== root.epgUrl) {
        if (!root.persistActive(rec.url, next.epgUrl)) return root.sourceResult(false, "persist_failed", Model.sourceErrorMessage("persist_failed"), key)
      }
      return root.sourceResult(true, "ok", "", key)
    }
    // URL change: the replacement lives in memory; nothing in the history
    // moves until the probe succeeds.
    root.probeEdit = Model.findSource(updated.state.sources, updated.key)
    return root.startProbe(key, updated.key, "edit", key === root.activeSourceKey)
  }

  // Remove a source (S7): drops the record, deletes its cache directory
  // through the helper and, when it was active, clears the settings so the
  // guide returns to the first-run state (playback, if any, continues).
  function removeSource(id) {
    var key = String(id || "")
    if (!root.stateLoaded || !root.cacheReady) return root.sourceResult(false, "not_ready", Model.sourceErrorMessage("not_ready"), key)
    if (root.probing && (root.probingKey === key || root.probeDirKey === key)) return root.sourceResult(false, "busy", Model.sourceErrorMessage("busy"), key)
    if (root.switching) return root.sourceResult(false, "busy", Model.sourceErrorMessage("busy"), key)
    var removed = Model.removeSource(root.userState, key)
    if (!removed.removed) return root.sourceResult(false, "unknown_source", Model.sourceErrorMessage("unknown_source"), key)
    var wasActive = key === root.activeSourceKey
    root.userState = removed.state
    root.saveState()
    root.sourceErrors = root.withoutKey(root.sourceErrors, key)
    root.queueCacheJob(["remove", "--key", key], null)
    if (wasActive && !root.persistActive("", "")) {
      root.sourceRemoved(key)
      return root.sourceResult(false, "persist_failed", Model.sourceErrorMessage("persist_failed"), key)
    }
    root.sourceRemoved(key)
    return root.sourceResult(true, "ok", "", key)
  }

  // Switch (S3, D7): a source with a cache commits at once (settings
  // write -> cache FileViews rebind -> redraw from its channels.json ->
  // background refresh when stale); a never-fetched source probes first.
  function switchSource(id) {
    var key = String(id || "")
    var gate = root.sourcesReady()
    if (gate) return gate
    var rec = Model.findSource(root.userState.sources, key)
    if (!rec) return root.sourceResult(false, "unknown_source", Model.sourceErrorMessage("unknown_source"), key)
    if (key === root.activeSourceKey) return root.sourceResult(true, "ok", "", key)
    if (!(rec.fetchedAt > 0)) return root.startProbe(key, key, "switch", true)
    root.userState = Model.touchSource(root.userState, key, Math.floor(Date.now() / 1000))
    root.saveState()
    root.beginSwitch()
    if (!root.persistActive(rec.url, rec.epgUrl)) {
      root.abortSwitch()
      return root.sourceResult(false, "persist_failed", Model.sourceErrorMessage("persist_failed"), key)
    }
    return root.sourceResult(true, "ok", "", key)
  }

  // Xtream form (S6, D10, SR16-SR18): Model.xtreamUrls builds the get.php /
  // xmltv.php URLs (no scheme guessing, no userinfo, credentials never
  // truncated) and they are added as an ordinary source. The password lives
  // only inside the URLs from here on; it is never stored or logged on its own.
  function buildXtreamSource(fields) {
    var f = fields || {}
    var built = Model.xtreamUrls(f.server, f.username, f.password)
    if (!built.ok) return root.sourceResult(false, built.code, built.message, "", built.field)
    return root.addSource({ playlistUrl: built.playlistUrl, epgUrl: built.epgUrl, label: f.label, kind: "xtream" })
  }

  // The only call that hands a URL to the guide: the edit form binds
  // `playlistMasked` / `epgMasked` and reveals the raw value on Ctrl+R.
  function sourceForEdit(id) {
    return Model.sourceForEdit(root.userState, String(id || ""))
  }

  // Probe again a record that failed to fetch (S8); a fetched record is
  // simply switched to.
  function retrySource(id) {
    var key = String(id || "")
    var gate = root.sourcesReady()
    if (gate) return gate
    var rec = Model.findSource(root.userState.sources, key)
    if (!rec) return root.sourceResult(false, "unknown_source", Model.sourceErrorMessage("unknown_source"), key)
    if (rec.fetchedAt > 0 && key !== root.activeSourceKey) return root.switchSource(key)
    return root.startProbe(key, key, "retry", true)
  }

  // Abort the running probe (UX 1.2 step 8): the helper is terminated, the
  // probe's cache directory is discarded, a pending add or replacement is
  // dropped and sourceProbeFinished carries `cancelled: true`.
  function cancelProbe() {
    if (!root.probing) return root.sourceResult(true, "ok", "", "")
    var key = root.probingKey
    root.probeCancelled = true
    probeWatchdog.stop()
    sourceProbeProc.signal(15)
    return root.sourceResult(true, "ok", "", key)
  }

  // wl-paste fallback of D9 (Guide.qml pasteInto): argv only, the text
  // comes back through clipboardText(text) and is never logged.
  function requestClipboard() {
    if (clipboardProc.running) return false
    clipboardProc.running = true
    return true
  }

  // ------------------------------------------------------------ internals

  function applyChannels(text) {
    var t0 = Date.now()
    root.switchReadMs = root.switching ? t0 - root.switchStartedAt : 0
    var prepared = null
    var lru = root.preparedLru
    for (var i = 0; i < lru.length; i++) {
      if (lru[i].text === text) { prepared = lru[i]; break }
    }
    if (!prepared) {
      var parsed = Model.parseChannels(text)
      var channels = parsed.ok ? Model.prepareChannels(parsed.channels) : []
      prepared = { text: text, channels: channels, channelIndex: Model.indexById(channels), channelsMeta: parsed.meta }
    }
    if (text !== "" && prepared.channels.length > 0) {
      var next = [prepared]
      for (var k = 0; k < lru.length && next.length < root.preparedLruSize; k++) if (lru[k] !== prepared) next.push(lru[k])
      root.preparedLru = next
    }
    var t1 = Date.now()
    root.channels = prepared.channels
    root.channelIndex = prepared.channelIndex
    root.channelsMeta = prepared.channelsMeta
    root.switchParseMs = t1 - t0
    root.switchAssignMs = Date.now() - t1
    // A now-playing recovered from the player's stash resolves against the
    // cache the moment it lands (4.5); until then it is name-only.
    root.reconcileNowPlaying()
  }

  // state.json -> userState (v1 files migrate in memory, section 2.2), then
  // the startup sequence of section 4.4: reconcile the settings into the
  // history and run the one-time cache migration. A reload caused by one
  // of this service's own writes is skipped: the in-memory state is newer
  // than what an earlier atomic write may still be delivering (R10).
  function applyUserState(text) {
    if (root.stateLoaded && root.recentSaves.indexOf(text) !== -1) return
    root.userState = Model.trimRecents(Model.parseState(text), root.maxRecents)
    root.stateLoaded = true
    root.reconcile(true)
    root.startCacheLayout()
    // The reattach probe beat the file here (it usually does: ~130 ms from
    // Component.onCompleted against however long a FileView takes). Now
    // there is a state to decide on, so PO-3's verdict runs (4.6).
    if (root.deadSessionPending) root.markDeadSession()
  }

  function saveState() {
    if (!root.dirsReady) {
      root.stateSavePending = true
      return
    }
    root.stateSavePending = false
    var text = JSON.stringify(root.userState, null, 2) + "\n"
    var saves = root.recentSaves.slice()
    saves.push(text)
    while (saves.length > 8) saves.shift()
    root.recentSaves = saves
    stateFile.setText(text)
  }

  function applyPlaylistStatus(text) {
    root.playlistStatus = Model.parseHelperStatus(text, "playlist")
    if (root.playlistStatus.ok === true) {
      root.playlistWarnings = Model.statusWarnings(root.playlistStatus)
      root.adoptSourceStats(root.playlistStatus)
    } else {
      root.lastError = root.statusReason
    }
  }

  // The history row shows counts without opening N status files: a
  // successful status of the active source (a helper run, or its
  // playlist-status.json loading after a cache swap: the migrated cache, a
  // CLI record fetched by the startup refresh, D-SRC-01) lands on the record
  // when it carries something the record does not have yet.
  function adoptSourceStats(status) {
    var key = root.activeSourceKey
    if (key === "" || !root.stateLoaded) return
    if (!Model.sourceStatsDiffer(Model.findSource(root.userState.sources, key), status)) return
    root.userState = Model.withSourceStats(root.userState, key, status, Math.floor(Date.now() / 1000))
    root.saveState()
  }

  function applyEpgStatus(text) {
    root.setEpgStatus(Model.parseHelperStatus(text, "epg"))
  }

  // The one place epg-status.json becomes state, so the file reload and the
  // helper exit cannot diverge. Warnings follow applyPlaylistStatus exactly
  // (D-LIVE-18): adopted from a successful run only, kept across a failed
  // one because the window still in use is that successful run's.
  function setEpgStatus(status) {
    root.epgStatus = status
    if (status && status.ok === true) root.epgWarnings = Model.statusWarnings(status)
  }

  function applyEpgNow(text) {
    var parsed = Model.parseEpgNow(text)
    root.epgNow = parsed.channels
    root.epgMeta = parsed.meta
    root.epgLoaded = parsed.ok
  }

  // Status JSON for a helper the watchdog killed (S-05): fixed text, host
  // only, so every sink (guide, notification, console) stays URL-free.
  function helperTimeoutStatus(kind, stale) {
    return JSON.stringify({
      ok: false,
      kind: kind,
      stale: stale,
      sourceHost: kind === "epg" ? Model.hostOf(root.activeEpgUrl) : root.sourceHost,
      error: { code: "helper_timeout", message: "helper timed out" }
    })
  }

  // Runs against the active source's own cache directory; nothing runs
  // while it is unknown ("" before startup finished, or unconfigured) or
  // while the configured URL is invalid (D16: the status is synthesized).
  function runPlaylistHelper() {
    if (root.playlistUrl === "" || root.activeCacheDir === "" || root.settingsInvalid || playlistProc.running) return
    root.playlistAttempted = true
    root.playlistTimedOut = false
    playlistProc.command = ["python3", root.helperPath, "playlist", "--url", root.playlistUrl, "--cache-dir", root.activeCacheDir]
    playlistProc.running = true
    playlistWatchdog.restart()
  }

  // `epg --url` fetches (the helper honours its own TTL, decision 5);
  // `epg --now-only` recomputes now/next from the cached window.
  function runEpgHelper(nowOnly) {
    if (epgProc.running || root.activeCacheDir === "") return
    if (nowOnly) {
      if (!root.epgLoaded) return
      epgProc.nowOnly = true
      epgProc.command = ["python3", root.helperPath, "epg", "--now-only", "--cache-dir", root.activeCacheDir]
    } else {
      if (root.activeEpgUrl === "") return
      root.epgAttempted = true
      epgProc.nowOnly = false
      epgProc.command = ["python3", root.helperPath, "epg", "--url", root.activeEpgUrl, "--cache-dir", root.activeCacheDir]
    }
    root.epgTimedOut = false
    epgProc.running = true
    epgWatchdog.restart()
  }

  function runControl(kind, args) {
    if (controlProc.running) return false
    root.controlKind = kind
    controlProc.command = ["python3", root.helperPath].concat(args)
    controlProc.running = true
    return true
  }

  function handleControlResult(text) {
    var kind = root.controlKind
    root.controlKind = ""
    var status = Model.parseHelperStatus(text, kind)
    if (kind === "status") {
      var code = status.error ? String(status.error.code) : ""
      if (Model.statusHealthy(status)) {
        root.healthFailures = 0
      } else if (code === "not_implemented" || code === "no_output") {
        // The helper cannot tell (stub or crash): neither healthy nor a
        // strike, so a missing subcommand never reaps a working player.
        if (root.healthFailures === 0) console.warn("omarchy-iptv: status check unavailable:", Model.statusReason(status))
      } else {
        root.healthFailures += 1
        if (root.healthFailures >= root.healthFailuresBeforeRestart) root.restartPlayer()
      }
    } else if (kind === "play") {
      if (root.stopping) {
        // An answer from a player on its way out: nothing to retry or
        // restore, the next play() starts a fresh one (4.10).
        root.playRetries = 0
      } else if (status.ok !== true && status.error) {
        var reason = Model.statusReason(status)
        var code = String(status.error.code)
        if (code === "not_running" && root.nowPlaying) {
          // The player vanished between two zaps. The `not_running` /
          // `still there` disambiguation collapses (4.7): `player start`
          // adopts a live player and spawns a dead one, so the same call is
          // right either way.
          root.lastError = reason
          var channel = root.channelIndex[root.nowPlaying.id]
          if (channel) root.startPlayer(channel)
        } else if (code === "ipc_error" && root.playerUp && root.nowPlaying
                   && !root.userStopped && root.playRetries < root.playRetryMax) {
          // mpv did not answer in time: retry with backoff instead of
          // losing the zap (D-LIVE-15).
          root.playRetries += 1
          playRetryTimer.interval = root.playRetryBaseMs * root.playRetries
          playRetryTimer.restart()
        } else {
          root.lastError = reason
          console.warn("omarchy-iptv: play failed:", reason)
          // The switch did not happen; mpv still plays the previous channel.
          if (root.playerUp && root.previousPlaying) root.nowPlaying = root.previousPlaying
        }
      } else if (status.ok === true) {
        root.playRetries = 0
        root.previousPlaying = null
        // The zap's own entry id, so a failure that arrives after the next
        // zap still names this channel (4.8).
        root.rememberEntry(status.entryId, root.nowPlaying)
      }
    }
    // Apply the last queued zap of a burst.
    root.drainPendingPlay()
  }

  // The last target of a zap burst, applied once the channel is free. It
  // goes over IPC when the player is up and starts one when it is not; both
  // are the same user intent, so neither may be dropped.
  function drainPendingPlay() {
    var id = root.pendingPlayId
    root.pendingPlayId = ""
    if (id === "" || root.stopping || root.userStopped || !root.nowPlaying) return
    if (root.playerUp) {
      if (!controlProc.running) root.runControl("play", root.playArgs(id))
      else root.pendingPlayId = id
      return
    }
    var channel = root.channelIndex[id]
    if (channel) root.startPlayer(channel)
  }

  // ------------------------------------------------------------ the detached player
  //
  // ARCHITECTURE-PLAYER.md sections 4.4 to 4.10, with the shape corrections
  // of section 13 (the socket observer is a Component, one fresh object per
  // attempt). Nothing in this block ever execs mpv: `player start` is
  // idempotent - it adopts a live player or spawns one under a lock - so
  // every call here is safe to repeat and none of them is a spawn gate.

  // Cold start, and the recovery path for every "the player is not there"
  // answer. `playerPending` is set synchronously so the bar lights up on
  // this frame; the socket observer is armed in the same turn, so it is
  // already retrying when mpv binds ~150 ms later (4.4 step 13).
  function startPlayer(channel) {
    if (!channel) return
    root.mpvStderrTail = []
    root.lastEndFile = null
    root.currentEntryId = 0
    root.healthSkips = 0
    root.healthFailures = 0
    if (playerProc.running) {
      // The one player slot is busy: keep the intent and apply it when the
      // call in flight returns, the way a zap burst coalesces.
      root.playerPending = true
      root.playerWanted = true
      root.armPlayerSocket()
      root.pendingPlayId = Model.channelId(channel)
      return
    }
    root.issuePlayerSession("start", channel, "")
    if (root.wantFocus) {
      root.focusAttempts = 0
      focusTimer.restart()
    }
  }

  // `player start` / `player restart`: one helper call carrying the channel
  // id (never the URL), the intent seq, the zap-ring scope for the stash and
  // this shell's pid as the owner claim (4.14).
  function issuePlayerSession(verb, channel, fromRung) {
    var extra = Model.splitMpvArgs(root.mpvArgs)
    if (extra.rejected.length > 0) console.warn("omarchy-iptv: ignoring mpvArgs tokens:", extra.rejected.join(" "))
    var np = root.nowPlaying
    var key = np ? String(np.id) : Model.channelId(channel)
    var scope = np ? String(np.launchedFrom || "") : ""
    var since = np ? Math.floor(Number(np.since) || 0) : 0
    var argv = verb === "restart"
      ? Model.playerRestartArgv(root.socketPath, root.activeCacheDir, key, root.playSeq, scope, since, extra.args, fromRung, Quickshell.processId)
      : Model.playerStartArgv(root.socketPath, root.activeCacheDir, key, root.playSeq, scope, since, extra.args, Quickshell.processId)
    root.playerPending = true
    root.playerWanted = true
    root.armPlayerSocket()
    return root.runPlayer(verb, argv)
  }

  // The player slot: its own Process with its own watchdog, so a cold start
  // can never starve a `play` or a `status` on controlProc (F1).
  function runPlayer(kind, args) {
    if (playerProc.running) return false
    root.playerKind = kind
    playerProc.command = Model.helperArgv(root.helperPath, args)
    playerProc.running = true
    playerWatchdog.restart()
    return true
  }

  // Reattach (4.5): lock-free, side-effect-free except for one stale-socket
  // unlink, and it claims the player for this shell.
  function runPlayerProbe() {
    if (playerProc.running) return false
    return root.runPlayer("probe", Model.playerProbeArgv(root.socketPath, Quickshell.processId))
  }

  function handlePlayerResult(text) {
    playerWatchdog.stop()
    var kind = root.playerKind
    root.playerKind = ""
    if (kind === "probe") {
      root.applyProbe(text)
      root.drainPendingPlay()
      return
    }
    var status = Model.parseHelperStatus(text, "player." + kind)
    if (status.ok === true) {
      var warnings = Model.statusWarnings(status)
      if (warnings.length > 0) console.warn("omarchy-iptv: player " + kind + ":", warnings.join("; "))
      root.relaunchPending = false
      root.playRetries = 0
      root.rememberEntry(status.entryId, root.nowPlaying)
      if (root.socketAttached()) {
        root.playerPending = false
      } else if (root.stopping || root.userStopped || root.nowPlaying === null) {
        // A stop overtook this start. The two legitimately interleave: the
        // helper releases the lock before its first-load window precisely
        // so a stop ladder can get in. Do not go hunting for a socket that
        // is being torn down - that would be twelve journal lines for a
        // player nobody wants any more.
        root.playerPending = false
      } else {
        // The player is up but the observer has not attached yet: keep the
        // birth edge rather than blinking the bar to idle, bounded by the
        // watchdog, and keep hunting for the socket.
        root.playerWanted = true
        root.armPlayerSocket()
        playerWatchdog.restart()
      }
      var first = status.firstLoad && typeof status.firstLoad === "object" ? status.firstLoad : null
      if (first && String(first.state) === "failed") root.playerFirstLoadFailed(String(first.reason || ""))
      root.drainPendingPlay()
      return
    }
    root.playerPending = false
    var code = status.error ? String(status.error.code) : ""
    var reason = Model.statusReason(status)
    if (code === "superseded") {
      // A later intent already won under the lock; this one never happened.
      // That intent wrote its own record and owns it, so this one leaves it.
      root.noteSessionOutcome("superseded")
      root.drainPendingPlay()
      return
    }
    if (code === "mpv_missing") {
      root.mpvAvailable = false
      whichProc.running = true
      root.playerWanted = false
      playerSocketTimer.stop()
      root.nowPlaying = null
      root.notify("mpvMissing", {})
      // The user has been told, in a critical toast, that the player program
      // is not installed. Leaving the record would spend that same event a
      // second time as a red row on the next reattach (PO-3).
      root.noteSessionOutcome("mpvMissing")
      return
    }
    if ((code === "busy" || code === "no_socket") && root.nowPlaying && !root.userStopped
        && !root.stopping && root.playRetries < root.playRetryMax) {
      // Another launcher holds the lock, or the spawn did not bind in time:
      // the existing backoff, not a second spawn (4.4 step 12).
      root.playRetries += 1
      playRetryTimer.interval = root.playRetryBaseMs * root.playRetries
      playRetryTimer.restart()
      root.noteSessionOutcome("retrying")
      return
    }
    root.lastError = reason
    console.warn("omarchy-iptv: player " + kind + " failed:", reason)
    root.playerWanted = false
    playerSocketTimer.stop()
    var target = root.nowPlaying
    root.nowPlaying = null
    root.playRetries = 0
    // The player never started: the same class of event the non-zero exit
    // of an attached mpv used to report (requirement 6).
    if (!root.userStopped && !root.stopping) root.raiseStreamFailure(target, reason)
    // Terminal either way. The toast above is the user's copy of this event
    // when the play was theirs; when a stop overtook it, stop() already
    // retired the record. Neither leaves anything for a reattach to mark.
    root.noteSessionOutcome("failed")
  }

  // `player start` observed the first load fail on its own connection (F3,
  // signal 1 of 4). Under --idle=once mpv exits on that failure, so socket
  // EOF is about to say the same thing; whichever wins, the user sees one
  // toast.
  function playerFirstLoadFailed(reason) {
    var target = root.nowPlaying
    if (reason !== "") root.rememberStderr(reason)
    root.raiseStreamFailure(target, reason !== "" ? reason : Model.PLAYER_GENERIC_FAILURE)
    if (!root.socketAttached()) {
      root.playerPending = false
      root.playerWanted = false
      playerSocketTimer.stop()
      root.nowPlaying = null
      // No socket means no EOF is coming to say this again: the toast the
      // user just saw is the whole story, so the record ends here too.
      root.noteSessionOutcome("failed")
      return
    }
    // The socket is live, so handlePlayerGone() is moments away and owns the
    // record; retiring it here would only race that.
    root.noteSessionOutcome("attached")
  }

  function applyProbe(text) {
    var probe = Model.parsePlayerProbe(text)
    if (!probe.valid) {
      // Garbage, a truncated line or an error reply is not evidence of a
      // player; the 10 s poll and the next play() both recover.
      root.playerPending = false
      return
    }
    // Ordering survives the restart: the next intent is one past whatever
    // the lock file recorded (4.10). This is also the repair for a sequence
    // that some other launcher pushed ahead of ours.
    root.playSeq = Math.max(root.playSeq, probe.seq + 1)
    if (root.stopConfirmPending) {
      root.stopConfirmPending = false
      if (probe.running) {
        // The stop was refused and the player is still there. Now that the
        // sequence is resynced, the ladder cannot be superseded again.
        console.warn("omarchy-iptv: stopping a player that survived a superseded stop")
        root.stopForeignPlayer()
      } else {
        root.playerWanted = false
        playerSocketTimer.stop()
        root.playerPending = false
        // The detached stop landed after all. stop() already retired the
        // record; saying so again costs nothing and keeps this branch on the
        // same decision as every other ending.
        root.noteSessionOutcome("stopped")
      }
      return
    }
    if (!probe.running) {
      root.playerWanted = false
      playerSocketTimer.stop()
      root.playerPending = false
      root.nowPlaying = null
      // Nothing is playing and nothing claimed to have stopped it: if a
      // session record survived, that channel died unattended (PO-3).
      root.markDeadSession()
      return
    }
    if (!probe.responsive) {
      console.warn("omarchy-iptv: the player is not answering, stopping it")
      root.stopForeignPlayer()
      return
    }
    var stash = probe.stash
    if (stash === null || stash.playing !== true || probe.idle === true) {
      // Under --idle=once an idle player exists only between spawn and the
      // first loadfile, so this is either a racing start or a foreign /
      // pre-M2-02 player. Re-read once before deciding (4.5).
      if (!root.probeRetried) {
        root.probeRetried = true
        probeRetryTimer.restart()
        return
      }
      root.probeRetried = false
      console.warn("omarchy-iptv: found a player this shell cannot identify, stopping it")
      root.stopForeignPlayer()
      return
    }
    root.probeRetried = false
    // Restored from the stash inside the surviving process, BEFORE the
    // channel cache exists: the bar and the guide are correct immediately
    // and the zap ring is fixed by reconcileNowPlaying() when the cache
    // lands (4.5, 4.6, requirement 11).
    root.userStopped = false
    root.stopAt = 0
    stopSettleTimer.stop()
    root.playerSourceKey = String(stash.sourceKey || "")
    root.nowPlaying = {
      id: String(stash.id),
      name: String(stash.name || ""),
      group: String(stash.group || ""),
      launchedFrom: String(stash.launchedFrom || ""),
      since: Math.floor(Number(stash.since) || 0)
    }
    if (stash.entryId) root.rememberEntry(stash.entryId, root.nowPlaying)
    root.reconcilePending = true
    root.playerPending = true
    root.playerWanted = true
    root.armPlayerSocket()
    playerWatchdog.restart()
    root.reconcileNowPlaying()
  }

  // Ruling PO-3. The probe says nothing is running; if state.json still
  // holds a session record, the channel it names died with no shell attached
  // to notice - so the guide gets a red row, silently, and the record is
  // cleared. A toast for something that stopped minutes ago, possibly on
  // another login, is noise that arrives without context.
  //
  // The race: this runs from the probe reply, about 130 ms after
  // Component.onCompleted, while stateFile loads whenever it loads - either
  // can win. Model.deadSessionVerdict() refuses to decide on a state that
  // has not landed (it would read the empty default, drop the mark, and
  // write that empty default over the user's file) and asks to be called
  // again; applyUserState() drains that.
  function markDeadSession() {
    var verdict = Model.deadSessionVerdict(root.userState, root.stateLoaded, root.failedAt,
                                           Model.formatClock(Math.floor(Date.now() / 1000)))
    root.deadSessionPending = verdict.pending
    if (!verdict.mark) return
    root.failedAt = verdict.failed
    if (!verdict.write) return
    root.userState = verdict.state
    root.saveState()
  }

  // The player is gone for good and nobody needs marking: an explicit stop,
  // The other half of PO-3, and the ONE place any player outcome is allowed
  // to reach the session record. Every branch below that ends in "the player
  // is gone" or "the player is still coming" says so here in one word and
  // Model.sessionAfterOutcome() decides, because the rule is the same rule
  // everywhere - a record must not outlive the shell that saw how the play
  // ended - and a rule spelled out per branch is a rule three branches will
  // get wrong. They did: a failed start, a missing mpv and an abandoned
  // relaunch each left the record behind, so the next reattach marked that
  // channel red a second time for a failure the user had already been shown
  // and already dealt with.
  //
  // Like markDeadSession() this is assignments and a write gate, no rule of
  // its own: the verdict carries the deferred-PO-3 flag as well as the state,
  // and hands back the same state object when there is nothing to clear, so
  // this writes only when it actually changed something.
  function noteSessionOutcome(outcome) {
    var verdict = Model.sessionAfterOutcome(root.userState, outcome, root.deadSessionPending)
    root.deadSessionPending = verdict.pending
    if (!verdict.write) return
    root.userState = verdict.state
    root.saveState()
  }

  // A player that exists but is not ours to show: wedged, foreign, or from
  // a version that did not stash its identity (migration, section 8). It
  // ends in nothing playing, so the session record goes with it.
  function stopForeignPlayer() {
    root.playSeq += 1
    root.playerWanted = false
    playerSocketTimer.stop()
    root.playerPending = false
    root.nowPlaying = null
    root.noteSessionOutcome("foreign")
    Quickshell.execDetached(Model.helperArgv(root.helperPath, Model.playerStopArgv(root.socketPath, root.playSeq)))
  }

  // The second half of the reattach: the stash named the channel, the cache
  // resolves it. A playlist that changed while the shell was down degrades
  // to name-only rather than resolving to the wrong row, and a stash from
  // another source is never resolved against this one.
  function reconcileNowPlaying() {
    if (!root.reconcilePending || !root.nowPlaying || !root.cacheLoaded) return
    if (root.playerSourceKey !== "" && root.activeSourceKey !== "" && root.playerSourceKey !== root.activeSourceKey) {
      root.reconcilePending = false
      return
    }
    root.reconcilePending = false
    var np = root.nowPlaying
    var channel = root.channelIndex[String(np.id)]
    if (!channel) return
    var group = Model.primaryGroup(channel)
    root.nowPlaying = {
      id: np.id,
      name: String(channel.name || np.name),
      group: group,
      launchedFrom: String(np.launchedFrom || "") || Model.groupScopeId(group),
      since: np.since
    }
  }

  // ---- the socket observer (spike caveats C1 to C10)
  //
  // A Quickshell Socket whose connect attempt fails is bricked permanently,
  // and re-arming one that is already connected arms a hidden zero-delay
  // auto-reconnect that bricks it the moment mpv dies. So: one fresh object
  // per attempt, never reused, never re-armed.

  function socketAttached() {
    return root.playerSocket !== null && root.playerSocket.connected === true
  }

  function releasePlayerSocket() {
    if (root.playerSocket === null) return
    var s = root.playerSocket
    root.playerSocket = null      // drop the reference first
    s.destroy()                   // deferred by QML, safe from inside a handler (C10)
  }

  // Returns true iff attached. Synchronous: a failed connect emits `error`
  // and never a state change, so `connected` on the next line is the only
  // authoritative answer (C5).
  function attachPlayerSocket() {
    if (root.socketPath === "") return false          // C8: arming with "" is a silent no-op
    root.releasePlayerSocket()
    var s = playerSocketComponent.createObject(root)
    if (s === null) {
      console.warn("omarchy-iptv: could not create the player socket observer")
      return false
    }
    root.playerSocket = s
    // createObject() is typed QObject, so the linter cannot see Socket's
    // own properties here; the type is guaranteed by the Component below.
    // qmllint disable missing-property
    s.connected = true
    if (s.connected) return true
    // qmllint enable missing-property
    root.playerSocket = null
    s.destroy()                   // a failed connect bricks it: discard (C1)
    return false
  }

  function armPlayerSocket() {
    if (root.socketAttached()) return      // C2: never re-arm a live socket
    playerSocketTimer.tries = 0
    if (root.attachPlayerSocket()) return
    playerSocketTimer.restart()
  }

  function socketWrite(sock, command, requestId) {
    if (!sock || sock.connected !== true) return false   // C7: a write to a dead socket vanishes
    sock.write(JSON.stringify({ command: command, request_id: requestId }) + "\n")
    return true
  }

  // Called from inside the Socket's own onConnectionStateChanged, so it
  // reads the object it is handed and never root.playerSocket (C4).
  function onPlayerAttached(sock) {
    root.playerPending = false
    root.playerWanted = true
    root.probeRetried = false
    // Observed properties are dropped when a connection closes, so a new
    // shell subscribes for itself rather than inheriting (4.4 step 13).
    root.socketWrite(sock, ["request_log_messages", "error"], 1)
    root.socketWrite(sock, ["observe_property", 1, "idle-active"], 2)
    if (sock.flush) sock.flush()
  }

  // Quickshell logs one WARN per failed attempt itself, so this stays quiet
  // by default; the burst cap is what keeps that bounded (C6).
  function onSocketError(err) {
    root.playerSocketError = Number(err)
    if (root.debugTiming) console.warn("omarchy-iptv: player socket error", String(err))
  }

  // Event router (4.8). Every line is one JSON object from mpv's own socket.
  // The routing DECISION is Model.routePlayerEvent(): which entry is
  // loading, whether the last end-file still stands, idle-active, and the
  // log tail. This method is the four property writes that decision implies,
  // and nothing else - a rule that lived here could only ever be pinned by a
  // copy of itself in the spec file (CLAUDE.md 10).
  function handlePlayerLine(line) {
    var before = { entryId: root.currentEntryId, lastEndFile: root.lastEndFile, idle: root.playerIdle, tail: root.mpvStderrTail }
    var next = Model.routePlayerEvent(before, line)
    // Unchanged fields come back by reference, so this writes only what moved.
    if (next.entryId !== before.entryId) root.currentEntryId = next.entryId
    if (next.lastEndFile !== before.lastEndFile) root.lastEndFile = next.lastEndFile
    if (next.idle !== before.idle) root.playerIdle = next.idle
    if (next.tail !== before.tail) root.mpvStderrTail = next.tail
  }

  // Which channel a load belonged to (Model.rememberEntryOwner): at most
  // four entries, and the gate fails open, so an unknown id degrades the
  // name and never suppresses a toast.
  function rememberEntry(entryId, target) {
    var owners = Model.rememberEntryOwner(root.entryOwners, entryId, target)
    if (owners === root.entryOwners) return
    root.entryOwners = owners
    root.currentEntryId = Math.floor(Number(entryId))
  }

  // One toast per failed play, whichever detector saw it first (R11, S-04).
  function raiseStreamFailure(target, reason) {
    if (!target) return
    var id = String(target.id || "")
    if (id !== "" && root.notifiedFailureId === id) return
    root.notifiedFailureId = id
    root.lastError = reason
    if (id !== "") root.failedAt = Model.withFailed(root.failedAt, id, Model.formatClock(Math.floor(Date.now() / 1000)))
    root.notify("streamFailed", { name: String(target.name || ""), reason: reason })
  }

  function rememberStderr(line) {
    var tail = Model.pushPlayerLog(root.mpvStderrTail, line)
    if (tail === root.mpvStderrTail) return
    root.mpvStderrTail = tail
  }

  // Socket EOF: the one-for-one replacement for mpvProc.onExited, and the
  // only death signal that covers quit, SIGTERM, SIGKILL and a segfault
  // alike - 2 to 3 ms after the fact instead of a 10 s poll (4.8 signal 3).
  // The exit code is replaced by Model.endedReport() over the last end-file:
  // whether the user hears about this death (our own stop and the .m3u8
  // redirect IPTV masters emit on every load say nothing), which channel it
  // names, and with what text. Read before any of the state below is
  // cleared, which is also what keeps the decision out of this method.
  function handlePlayerGone() {
    focusTimer.stop()
    playRetryTimer.stop()
    playerSocketTimer.stop()
    var current = root.nowPlaying
    var end = root.lastEndFile
    var stopped = root.userStopped
    var report = Model.endedReport({
      lastEndFile: end,
      owners: root.entryOwners,
      nowPlaying: current,
      userStopped: stopped,
      stopping: root.stopping,
      tail: root.mpvStderrTail
    })
    var relaunch = root.relaunchPending && current !== null && !stopped
    root.lastEndFile = null
    root.currentEntryId = 0
    root.playerIdle = false
    root.playerPending = false
    root.playerWanted = false
    root.userStopped = false
    root.relaunchPending = false
    root.stopConfirmPending = false     // the EOF is the confirmation
    root.pendingPlayId = ""
    root.playRetries = 0
    root.healthSkips = 0
    root.healthFailures = 0
    // The death IS the end of the stop (4.10); the 5 s backstop is only for
    // a stop that never had a player to observe.
    root.stopAt = 0
    stopSettleTimer.stop()
    if (relaunch && root.channelIndex[String(current.id)]) {
      // The health verdict's one automatic relaunch, a moment after the
      // exit: the old socket file is gone by then and a stop() in the
      // meantime cancels it (D-LIVE-15, D-LIVE-17).
      root.wantFocus = false
      relaunchTimer.restart()
      // The record outlives this death on purpose: the same channel is
      // coming back in a moment, and if the shell dies in between, nothing
      // watched the outcome after all.
      root.noteSessionOutcome("relaunching")
      return
    }
    root.nowPlaying = null
    // Terminal: the player is gone and nothing is bringing it back, whatever
    // the verdict says. This is where a clean end, a crash we have just
    // toasted and a stop we did not issue all leave the session record
    // behind if nobody clears it, and the next reattach would read that as a
    // channel that died unattended (PO-3).
    root.noteSessionOutcome("ended")
    root.entryOwners = ({})
    if (!report.notify) return
    // report.reason is the log-message tail when there is one ("Failed to
    // open scheme://host" says what actually went wrong), else mpv's own
    // generic file_error. Both are redacted, the tail twice (in python and
    // again in Model.pushPlayerLog).
    root.raiseStreamFailure(report.target, report.reason)
  }

  function handlePlaylistExit(text) {
    playlistWatchdog.stop()
    var timedOut = root.playlistTimedOut
    root.playlistTimedOut = false
    if (timedOut) {
      // The killed helper wrote no status file for this run; reloading the
      // one on disk would replace this error with the previous result.
      root.applyPlaylistStatus(root.helperTimeoutStatus("playlist", root.cacheLoaded))
    } else {
      root.applyPlaylistStatus(text)
      playlistStatusFile.reload()
    }
    // Deterministic reload; do not rely on inotify surviving the helper's
    // atomic rename (ARCHITECTURE.md, open risk 1).
    channelsFile.reload()
    var manual = root.manualRefresh
    root.manualRefresh = false
    var status = root.playlistStatus
    if (status.ok === true) {
      // The counts landed on the history record in applyPlaylistStatus.
      if (manual) root.notify("playlistRefreshed", { channelCount: status.channelCount, groupCount: status.groupCount })
      root.playlistRefreshed(Number(status.channelCount) || 0, manual)
      // US6: the EPG follows the playlist (the helper restricts programmes
      // to the playlist's ids). Fetch it when none is loaded or its now/next
      // window has expired; a run already in flight is repeated (D-LIVE-02).
      if (root.activeEpgUrl !== "" && (!root.epgLoaded || Model.epgNowStale(root.epgMeta, Math.floor(Date.now() / 1000)))) root.refreshEpg(true)
    } else {
      root.notify("playlistError", { reason: root.statusReason, cachedAt: status.stale === true ? root.lastUpdated : "" })
    }
    if (root.playlistRerun) {
      root.playlistRerun = false
      refreshDebounce.restart()
    }
  }

  function handleEpgExit(text, nowOnly) {
    epgWatchdog.stop()
    var timedOut = root.epgTimedOut
    root.epgTimedOut = false
    var status = Model.parseHelperStatus(timedOut ? root.helperTimeoutStatus("epg", root.epgLoaded) : text, "epg")
    if (!nowOnly) {
      root.setEpgStatus(status)
      root.manualEpgRefresh = false
      if (status.ok !== true) root.notify("epgError", { reason: Model.statusReason(status) })
    } else if (timedOut) {
      console.warn("omarchy-iptv: epg --now-only helper timed out")
    }
    epgFile.reload()
    if (root.epgRerun) {
      root.epgRerun = false
      epgDebounce.restart()
    }
  }

  // ------------------------------------------------------------ sources internals

  // Write the active source through the host (D1): the full entry is passed
  // because updateEntryInline replaces it wholesale (entryWith keeps the
  // keys we do not own).
  //
  // The write is applied LOCALLY on success and the guide redraws from that;
  // the plugin never waits for the host to echo its own settings back
  // (D-LIVE-20 / D-LIVE-21, see `settings` above). A persist failure is only
  // a missing host or an entry updateEntryInline cannot rewrite: `false`
  // from a writable entry is its `!dirty` branch (shell.qml:1114), i.e. the
  // host already stores exactly what we asked for, which is success.
  function persistActive(playlistUrl, epgUrl) {
    if (root.playlistUrl === playlistUrl && root.epgUrl === epgUrl) return true
    if (!root.shell || typeof root.shell.updateEntryInline !== "function"
        || !Model.barEntryWritable(root.shell.barConfig, root.pluginId)) {
      console.warn("omarchy-iptv: no writable bar entry for the settings change")
      root.sourcesPersistFailed("persist_failed")
      return false
    }
    var entry = Model.entryWith(Model.findBarEntry(root.shell.barConfig, root.pluginId), { playlistUrl: playlistUrl, epgUrl: epgUrl, id: root.pluginId })
    root.shell.updateEntryInline(root.pluginId, entry)
    root.applyOwnWrite(playlistUrl, epgUrl)
    return true
  }

  // Apply our own write to `settings` at once. Assigning `ownWrite` makes
  // the `settings` binding re-evaluate, which runs the ordinary
  // onSettingsChanged -> reconcile() path: exactly what the echo would have
  // done, in the same event loop turn. The override lapses by itself as soon
  // as the host reports anything other than the value it had when we wrote.
  function applyOwnWrite(playlistUrl, epgUrl) {
    root.ownWrite = Model.ownWriteFor(root.hostSettings, playlistUrl, epgUrl)
  }

  function beginSwitch() {
    root.switchStartedAt = Date.now()
    root.switching = true
    switchTimeout.restart()
  }

  function abortSwitch() {
    switchTimeout.stop()
    root.switching = false
  }

  // The new source's channels.json (or its absence) has been applied.
  function finishSwitch() {
    if (!root.switching) return
    switchTimeout.stop()
    root.switching = false
    if (root.debugTiming) {
      console.info("omarchy-iptv switch " + Math.round(Date.now() - root.switchStartedAt) + " ms (" + root.channels.length + " channels; read "
                   + Math.round(root.switchReadMs) + " ms, prepare " + Math.round(root.switchParseMs) + " ms, bindings " + Math.round(root.switchAssignMs) + " ms)")
    }
    root.sourceSwitched(root.activeSourceKey)
  }

  // One probe at a time (section 4.6): `playlist` into the source's own
  // directory. `key` is the record concerned, `dirKey` the directory
  // written (they differ for a URL edit), `mode` add | edit | switch |
  // retry, `commit` whether success writes the settings.
  function startProbe(key, dirKey, mode, commit) {
    var rec = root.probeRecord(mode, key)
    if (!rec || sourceProbeProc.running) {
      root.probeAdd = null
      root.probeEdit = null
      if (!rec) return root.sourceResult(false, "unknown_source", Model.sourceErrorMessage("unknown_source"), key)
      return root.sourceResult(false, "busy", Model.sourceErrorMessage("busy"), root.probingKey)
    }
    root.probingKey = key
    root.probeDirKey = dirKey
    root.probeMode = mode
    root.probeCommit = commit
    root.probeCancelled = false
    root.probeTimedOut = false
    root.sourceErrors = root.withoutKey(root.sourceErrors, key)
    sourceProbeProc.command = ["python3", root.helperPath, "playlist", "--url", rec.url, "--cache-dir", Model.sourceCacheDir(root.cacheDir, dirKey)]
    sourceProbeProc.running = true
    probeWatchdog.restart()
    return root.sourceResult(true, "ok", "", key)
  }

  function handleProbeExit(text) {
    probeWatchdog.stop()
    var key = root.probingKey
    var dirKey = root.probeDirKey
    var mode = root.probeMode
    var commit = root.probeCommit
    var cancelled = root.probeCancelled
    var timedOut = root.probeTimedOut
    var pending = mode === "add" ? root.probeAdd : (mode === "edit" ? root.probeEdit : null)
    root.probingKey = ""
    root.probeDirKey = ""
    root.probeMode = ""
    root.probeCancelled = false
    root.probeTimedOut = false
    root.probeAdd = null
    root.probeEdit = null
    var st = root.userState
    var rec = pending || Model.findSource(st.sources, key)
    var host = root.hostForRecord(rec)
    var nowSec = Math.floor(Date.now() / 1000)
    if (cancelled) {
      // SR7: the directory the probe was writing is discarded; a pending
      // add or replacement was never recorded (SR23) and the form keeps its
      // values (UX 5.5).
      root.queueCacheJob(["remove", "--key", dirKey], null)
      root.sourceProbeFinished({ ok: false, id: key, channelCount: 0, groupCount: 0, reason: "", host: host, cancelled: true, replacedId: "" })
      return
    }
    var status = Model.parseHelperStatus(timedOut ? root.helperTimeoutStatus("playlist", false) : text, "playlist")
    if (!rec) {
      root.queueCacheJob(["remove", "--key", dirKey], null)
      root.sourceProbeFinished({ ok: false, id: key, channelCount: 0, groupCount: 0, reason: Model.sourceErrorMessage("unknown_source"), host: "", cancelled: false, replacedId: "" })
      return
    }
    if (status.ok === true) {
      var newKey = key
      if (pending) {
        // Record the pending add now (SR23), or move the edited record to
        // its new key (SR7): the old record and its directory go.
        if (mode === "edit") {
          st = Model.removeSource(st, key).state
          root.queueCacheJob(["remove", "--key", key], null)
          root.sourceErrors = root.withoutKey(root.sourceErrors, key)
        }
        var known = Model.findSourceByUrl(st.sources, pending.url)
        if (known) {
          // The same URL arrived through the CLI while the probe ran (S5):
          // that record wins and the counts land on it.
          newKey = String(known.key)
        } else {
          newKey = Model.allocateSourceKey(st.sources, pending.url)
          var record = pending
          if (newKey !== pending.key) {
            record = {}
            for (var k in pending) record[k] = pending[k]
            record.key = newKey
          }
          st = Model.cloneState(st, { sources: st.sources.concat([record]) })
        }
        // A key that moved (a colliding record appeared meanwhile) leaves
        // the probe's directory behind: it is dropped and the freshness
        // check fetches the source again.
        if (newKey !== dirKey) root.queueCacheJob(["remove", "--key", dirKey], null)
      }
      st = Model.withSourceStats(st, newKey, status, nowSec)
      st = Model.touchSource(st, newKey, nowSec)
      root.userState = st
      root.saveState()
      if (commit) {
        if (newKey === root.activeSourceKey) {
          // Already the active directory (a retry of the active source):
          // the FileViews watch it, but reload deterministically.
          channelsFile.reload()
          playlistStatusFile.reload()
        } else {
          root.beginSwitch()
          if (!root.persistActive(rec.url, rec.epgUrl)) root.abortSwitch()
        }
      }
      root.sourceProbeFinished({
        ok: true, id: newKey, channelCount: Number(status.channelCount) || 0, groupCount: Number(status.groupCount) || 0,
        reason: "", host: host, cancelled: false, replacedId: mode === "edit" ? key : ""
      })
      return
    }
    // Failure (S8): the previous active source is untouched. A pending add
    // or replacement was never recorded and its directory goes (SR23); an
    // existing record keeps fetchedAt 0 plus a session-only reason for the
    // result line (SR26).
    var reason = Model.statusReason(status)
    if (pending) root.queueCacheJob(["remove", "--key", dirKey], null)
    else root.sourceErrors = root.withKey(root.sourceErrors, key, reason)
    root.sourceProbeFinished({ ok: false, id: key, channelCount: 0, groupCount: 0, reason: reason, host: host, cancelled: false, replacedId: "" })
  }

  // D3 / SR8: the settings are the source of truth for the active source;
  // the history follows them. Runs on state load (`force`: the file was
  // re-read, reconcile whatever the settings are) and on every settings
  // change, both keys (a CLI `omarchy bar set` included, D-SRC-02). It
  // reads `settings` as one object: from inside onSettingsChanged the
  // derived playlistUrl / epgUrl bindings may not have re-evaluated yet.
  // Idempotent: an unrelated settings write is a no-op.
  function reconcile(force) {
    if (!root.stateLoaded) return
    var s = root.settings
    var playlist = String(s.playlistUrl || "")
    var epg = String(s.epgUrl || "")
    var first = !root.reconciled
    var playlistChanged = first || playlist !== root.reconciledPlaylistUrl
    var epgChanged = first || epg !== root.reconciledEpgUrl
    if (!force && !playlistChanged && !epgChanged) return
    // D-SRC-10: an epgUrl that did not change in the settings write that
    // changed the playlist was written for the previous source (a switch
    // wrote it); it is not adopted. A state load takes the settings as
    // they are (both keys were the user's or a switch's, D3).
    var adoptEpg = first || force === true || epgChanged
    var previousKey = first || force === true ? Model.activeSourceKey(root.userState, playlist) : root.reconciledActiveKey
    var out = Model.reconcileSources(root.userState, playlist, epg, previousKey, Math.floor(Date.now() / 1000), "", { adoptEpg: adoptEpg })
    root.reconciled = true
    root.reconciledPlaylistUrl = playlist
    root.reconciledEpgUrl = epg
    root.reconciledActiveKey = out.invalid ? "" : String(out.activeKey || "")
    if (playlistChanged) {
      // A new source starts clean: the previous source's reason and host
      // must not stay on screen while its first fetch runs (UX 4.5,
      // D-LIVE-10). The fetch itself is driven by the new cache's freshness
      // once its directory is bound (section 4.4 step 6), never from here.
      root.playlistStatus = ({ ok: false, kind: "playlist", stale: false, error: null })
      root.playlistWarnings = []
      root.lastError = ""
    }
    root.settingsInvalid = out.invalid
    if (out.changed) {
      root.userState = out.state
      root.saveState()
    }
    for (var i = 0; i < out.evicted.length; i++) {
      console.warn("omarchy-iptv: source history full, evicting", out.evicted[i])
      root.queueCacheJob(["remove", "--key", out.evicted[i]], null)
    }
    if (out.invalid) {
      // D16: never run the helper for garbage; the guide's error empty
      // state shows the validation reason instead (re-applied by
      // clearSourceData when the cache directory unbinds, D-SRC-03).
      root.applyInvalidStatus()
      return
    }
    if (!adoptEpg && out.activeKey !== "") {
      // D-SRC-10: the record did not take the carried-over epgUrl, so the
      // settings follow the record (its own EPG, or none). Deferred: never
      // write the settings from inside their own change notification.
      var rec = Model.findSource(root.userState.sources, out.activeKey)
      var recEpg = rec ? String(rec.epgUrl || "") : ""
      if (rec && Model.normalizeSourceUrl(epg, { kind: "epg", origin: "cli" }) !== recEpg) {
        Qt.callLater(function() { root.syncSettingsEpg(playlist, recEpg) })
      }
    }
  }

  // The synthesized status for an invalid configured URL (D16, SR8): the
  // UX 5.4 sentence, no host, no helper run.
  function applyInvalidStatus() {
    if (!root.settingsInvalid) return
    var code = String(root.settingsInvalid.code || "invalid")
    root.playlistStatus = ({ ok: false, kind: "playlist", stale: false, sourceHost: "", error: { code: code, message: Model.sourceErrorMessage(code) } })
    root.lastError = root.statusReason
  }

  // D-SRC-10 follow-up of reconcile(): the settings' epgUrl is the previous
  // source's; write the active record's own value unless the settings moved
  // on meanwhile. A refused write is reported like any other persist failure.
  function syncSettingsEpg(playlistUrl, epgUrl) {
    if (String(root.settings.playlistUrl || "") !== playlistUrl) return
    if (!root.persistActive(playlistUrl, epgUrl)) console.warn("omarchy-iptv: could not clear the previous source's epgUrl from the settings")
  }

  // Section 4.4 step 4: once per state file, move the 0.1 single cache
  // into the active source's directory. Needs the settings (shell) to know
  // the key; without a configured source the legacy files are deleted.
  function startCacheLayout() {
    if (root.cacheReady || root.cacheMigrating || !root.stateLoaded || !root.shell) return
    if (root.userState.cacheLayout === 2) {
      root.cacheReady = true
      root.schedulePrune()
      return
    }
    root.cacheMigrating = true
    var args = ["migrate"]
    if (root.activeSourceKey !== "") args = args.concat(["--key", root.activeSourceKey])
    root.queueCacheJob(args, function(status) {
      root.cacheMigrating = false
      if (status.ok === true) {
        root.userState = Model.withCacheLayout(root.userState, 2)
        root.saveState()
      }
      root.cacheReady = true
      root.schedulePrune()
    })
  }

  // Section 4.4 step 7: once per start, drop orphan directories and age the
  // EPG files of inactive sources.
  function schedulePrune() {
    if (root.pruned) return
    root.pruned = true
    var args = ["prune", "--keep"]
    var sources = root.userState.sources
    for (var i = 0; i < sources.length; i++) args.push(sources[i].key)
    if (root.activeSourceKey !== "") args = args.concat(["--active", root.activeSourceKey])
    args = args.concat(["--epg-max-age", String(root.epgMaxAgeSec)])
    root.queueCacheJob(args, null)
  }

  // Section 4.7: one cacheProc, a FIFO of { args, onDone }; failures are
  // logged with the action and code only.
  function queueCacheJob(args, onDone) {
    var queue = root.cacheQueue.slice()
    queue.push({ args: args, onDone: onDone })
    root.cacheQueue = queue
    root.runNextCacheJob()
  }

  function runNextCacheJob() {
    if (cacheProc.running || root.cacheQueue.length === 0 || !root.dirsReady) return
    var job = root.cacheQueue[0]
    root.cacheQueue = root.cacheQueue.slice(1)
    root.cacheJob = job
    cacheProc.command = ["python3", root.helperPath, "cache", "--cache-dir", root.cacheDir].concat(job.args)
    cacheProc.running = true
  }

  function handleCacheExit(text) {
    var job = root.cacheJob
    root.cacheJob = null
    var status = Model.parseHelperStatus(text, "cache")
    if (status.ok !== true) console.warn("omarchy-iptv: cache " + (job ? job.args[0] : "?") + " failed:", status.error ? status.error.code : "error")
    if (job && typeof job.onDone === "function") job.onDone(status)
    root.runNextCacheJob()
  }

  // Section 4.4 step 6: after a cache swap, playlist-status.json decides
  // whether the source is refreshed in the background (older than
  // refreshMinutes, never fetched, or last run failed).
  function applyFreshness() {
    if (!root.pendingFreshness) return
    root.pendingFreshness = false
    if (root.activeCacheDir === "") return
    var nowSec = Math.floor(Date.now() / 1000)
    if (Model.cacheStale(root.playlistStatus, root.refreshMinutes, nowSec)) root.refreshPlaylist(true)
    if (root.activeEpgUrl !== "" && !epgProc.running) root.refreshEpg(true)
  }

  // Reset the per-source data to "nothing known yet" so no reason, count
  // or programme of the previous source survives a swap (D-LIVE-10). An
  // invalid configured URL keeps its synthesized status: the directory
  // unbinds after reconcile() set it, and the guide must not fall back to
  // `Loading playlist...` for good (D-SRC-03).
  function clearSourceData() {
    root.channels = []
    root.channelIndex = ({})
    root.channelsMeta = ({})
    root.playlistStatus = ({ ok: false, kind: "playlist", stale: false, error: null })
    root.playlistWarnings = []
    root.playlistAttempted = false
    root.epgNow = ({})
    root.epgMeta = ({})
    root.epgLoaded = false
    root.epgAttempted = false
    root.epgStatus = ({ ok: false, kind: "epg", stale: false, error: null })
    root.epgWarnings = []
    root.lastError = ""
    root.applyInvalidStatus()
  }

  function activeSourceSummary() {
    var rec = Model.findSource(root.userState.sources, root.activeSourceKey)
    if (!rec) return null
    var view = Model.sourceView(rec, root.activeSourceKey, root.nowSec, "")
    return { id: view.id, label: view.label, host: view.host }
  }

  // ------------------------------------------------------------ helpers

  // Host for the probe signal (UX-SOURCES 5.5): Model.hostOf, never a path,
  // query or userinfo; `local file` for a path (the guide's failure line
  // drops the host for kind `file`, the `Added` transient shows it).
  function hostForRecord(rec) {
    return rec ? Model.hostOf(rec.url) : ""
  }

  // The form field a failed action concerns (for the harness; the guide
  // maps codes to fields itself).
  function resultField(code, message) {
    var c = String(code || "")
    if (c === "label_taken" || c === "label_too_long") return "label"
    if (String(message || "").indexOf("EPG:") === 0) return "epgUrl"
    return "playlistUrl"
  }

  // The record a probe concerns: a pending add or replacement lives in
  // memory until its probe succeeds (SR23, SR7); every other record is in
  // the history.
  function probeRecord(mode, key) {
    if (mode === "add") return root.probeAdd
    if (mode === "edit") return root.probeEdit
    return Model.findSource(root.userState.sources, key)
  }

  function withKey(obj, key, value) {
    var out = {}
    for (var k in obj) out[k] = obj[k]
    out[key] = value
    return out
  }

  function withoutKey(obj, key) {
    var out = {}
    for (var k in obj) if (k !== key) out[k] = obj[k]
    return out
  }

  // ------------------------------------------------------------ signal handlers

  // One handler for both URL settings (D-SRC-02): reconcile() reads the new
  // `settings` object itself and resets the per-source status when the
  // playlist changed (the derived playlistUrl / epgUrl bindings may still
  // hold the previous values inside this handler).
  onSettingsChanged: root.reconcile()
  // Our own write stands in for the host's value only until the host
  // reports something else -- its (late) echo of our own value, or a
  // foreign change such as `omarchy bar set`. Both make the host
  // authoritative again, so the override is dropped here rather than left
  // to lapse on its own: a host value that later returns to what it was
  // when we wrote must not resurrect a spent override. Dropping it before
  // `settings` re-evaluates is what a QML change handler does by
  // construction (it runs before the bindings that depend on the same
  // property), which is also the host behaviour this works around.
  onHostSettingsChanged: if (root.ownWrite && !Model.ownWriteInForce(root.hostSettings, root.ownWrite)) root.ownWrite = null
  // D-LIVE-19: `omarchy bar set io.github.rmcdavid.iptv playlistUrl ""` at
  // runtime. The active source's in-memory data goes with the setting, so
  // the channel list, the group column and the counts are gone by the time
  // the guide draws its setup surface; without this the cleared state was
  // only reached through the cache directory unbinding, and any path that
  // leaves the directory bound left the previous source's rows behind the
  // `No playlist configured` body. The history record and the cache on disk
  // survive (the setup surface offers `Saved sources (n)`, and setting a URL
  // again rebinds the directory and reloads it).
  onConfiguredChanged: if (!root.configured) root.clearSourceData()
  onActiveEpgUrlChanged: {
    // Read the property itself, not a derived flag: with `epgConfigured`
    // (stale false on an empty -> value change) this handler took the
    // "cleared" branch and the first EPG never loaded (D-LIVE-02).
    if (root.activeEpgUrl === "") {
      root.epgLoaded = false
      root.epgAttempted = false
      root.epgNow = ({})
      root.epgStatus = ({ ok: false, kind: "epg", stale: false, error: null })
      root.epgWarnings = []
      return
    }
    // A cache swap in flight fetches the EPG from its freshness check.
    if (!root.pendingFreshness) root.refreshEpg(true)
  }
  onMaxRecentsChanged: {
    var trimmed = Model.trimRecents(root.userState, root.maxRecents)
    if (trimmed !== root.userState) {
      root.userState = trimmed
      root.saveState()
    }
  }
  onShellChanged: {
    // The host injects `shell` after creation; the settings may only be
    // readable now (the migration needs the active key).
    root.reconcile()
    root.startCacheLayout()
  }
  onActiveCacheDirChanged: {
    // The four cache FileViews rebind their paths (R1): an empty path fires
    // nothing, so clear in memory; otherwise reset so nothing of the previous
    // source survives and let playlist-status.json decide on a refresh.
    root.clearSourceData()
    root.pendingFreshness = root.activeCacheDir !== ""
    if (root.activeCacheDir === "") root.finishSwitch()
  }

  Component.onCompleted: {
    // Argv-only. Creates the private cache/state/runtime dirs before any
    // FileView write or mpv socket bind can need them (open risk 2), then
    // state.json itself with mode 0600 (stateInitProc, S-02).
    mkdirProc.running = true
    whichProc.running = true
    // Reattach (4.5). Until the probe answers - about 130 ms - the UI shows
    // idle rather than guessing. `--owner-pid` claims a surviving player for
    // this shell, which is what tells the previous shell's orphan-check to
    // do nothing.
    root.runPlayerProbe()
  }

  // PO-2: the service object is destroyed both by a shell restart and by the
  // plugin being disabled or removed, and Quickshell 0.3.1 gives no way to
  // tell them apart at this point - so we must NOT stop the player here.
  // That would kill playback on the very restart this milestone exists to
  // survive. The discriminator is the owner claim, read 6 s later by a
  // detached helper: a successor shell has re-claimed the player well
  // inside the grace (omarchy-restart-shell pings every 100 ms for 2 s), so
  // only "the claim still names a pid that is still alive" means the plugin
  // was disabled or removed (4.14).
  Component.onDestruction: {
    Quickshell.execDetached(Model.helperArgv(root.helperPath,
      Model.playerOrphanCheckArgv(root.socketPath, Quickshell.processId, Model.PLAYER_ORPHAN_GRACE_SEC)))
  }

  // ------------------------------------------------------------ files

  // The four cache views follow the active source's directory (D5). Content
  // is only ever applied from onLoaded / onLoadFailed (R1: after a path
  // change the view still reports the previous file until then).
  FileView {
    id: channelsFile
    path: root.activeCacheDir === "" ? "" : root.activeCacheDir + "/channels.json"
    watchChanges: true
    printErrors: false
    onLoaded: {
      root.applyChannels(text())
      root.finishSwitch()
    }
    onLoadFailed: {
      root.applyChannels("")
      root.finishSwitch()
    }
    onFileChanged: reload()
  }

  FileView {
    id: playlistStatusFile
    path: root.activeCacheDir === "" ? "" : root.activeCacheDir + "/playlist-status.json"
    watchChanges: true
    printErrors: false
    onLoaded: {
      root.applyPlaylistStatus(text())
      root.applyFreshness()
    }
    onLoadFailed: {
      // Never fetched: no status yet, so the freshness check fetches.
      root.applyFreshness()
    }
    onFileChanged: reload()
  }

  FileView {
    id: epgFile
    path: root.activeCacheDir === "" ? "" : root.activeCacheDir + "/epg-now.json"
    watchChanges: true
    printErrors: false
    onLoaded: root.applyEpgNow(text())
    onLoadFailed: root.applyEpgNow("")
    onFileChanged: reload()
  }

  FileView {
    id: epgStatusFile
    path: root.activeCacheDir === "" ? "" : root.activeCacheDir + "/epg-status.json"
    watchChanges: true
    printErrors: false
    onLoaded: {
      // The file is the last known fetch result at startup. Later, a
      // `--now-only` recompute rewrites it with ok:true although the source
      // was not contacted; that must not clear the `Guide data unavailable`
      // banner, which stays until a fetch succeeds (UX 4.6, D-LIVE-08).
      // handleEpgExit owns the status of every `--url` run.
      if (epgProc.nowOnly) return
      root.applyEpgStatus(text())
      root.epgAttempted = true
    }
    onFileChanged: reload()
  }

  FileView {
    id: stateFile
    path: root.stateDir + "/state.json"
    watchChanges: true
    atomicWrites: true
    printErrors: false
    onLoaded: root.applyUserState(text())
    onLoadFailed: root.applyUserState("")
    onFileChanged: reload()
  }

  // ------------------------------------------------------------ timers

  Timer {
    id: refreshDebounce
    interval: root.refreshDebounceMs
    repeat: false
    onTriggered: root.runPlaylistHelper()
  }

  Timer {
    id: epgDebounce
    interval: root.refreshDebounceMs
    repeat: false
    onTriggered: root.runEpgHelper(false)
  }

  Timer {
    // The first fetch is driven by the cache's freshness (section 4.4 step
    // 6), not by service start: a fresh cache after `omarchy restart shell`
    // is no longer re-downloaded (R9). Timer semantics otherwise unchanged.
    id: refreshTimer
    interval: root.refreshMinutes * 60 * 1000
    repeat: true
    running: root.configured
    triggeredOnStart: false
    onTriggered: {
      root.refreshPlaylist(false)
      root.refreshEpg(false)
    }
  }

  Timer {
    // EPG now/next is recomputed from the cached programme window; the
    // helper only re-downloads when its own TTL expired (decision 5).
    id: epgRecomputeTimer
    interval: root.epgRecomputeMs
    repeat: true
    running: root.epgConfigured && root.epgLoaded
    onTriggered: root.runEpgHelper(true)
  }

  Timer {
    // 30 s wall-clock tick: the guide re-derives fractions and now/next
    // boundaries from nowSec (R8).
    id: epgTick
    interval: root.epgTickMs
    repeat: true
    running: true
    onTriggered: root.nowSec = Math.floor(Date.now() / 1000)
  }

  Timer {
    // Health check while the player runs: helper `status` over the socket;
    // two consecutive failures, or three ticks in a row behind an in-flight
    // helper call, -> `player restart --from term` -> one automatic
    // relaunch (D-LIVE-17, 4.13). It is the only detector of a
    // wedged-but-connected mpv, and the degraded-mode detector if the
    // socket observer is ever unusable, so it must NOT be gated on
    // `playerUp` alone: a stale false would switch off its own reconciler.
    id: healthTimer
    interval: root.healthCheckMs
    repeat: true
    running: root.playerUp || root.nowPlaying !== null
    onTriggered: {
      if (root.userStopped || root.stopping) return
      var tick = Model.healthTick(root.healthSkips, controlProc.running)
      root.healthSkips = tick.skips
      if (tick.restart) root.restartPlayer()
      else if (tick.check) root.runControl("status", ["status", "--socket", root.socketPath])
    }
  }

  Timer {
    // Watchdog (S-05): a playlist helper still running after helperTimeoutMs
    // is terminated; handlePlaylistExit then reports "helper timed out"
    // (status `error` without a cache, `cached` with one). No URL is logged.
    id: playlistWatchdog
    interval: root.helperTimeoutMs
    repeat: false
    onTriggered: {
      if (!playlistProc.running) return
      console.warn("omarchy-iptv: playlist helper exceeded " + Math.floor(root.helperTimeoutMs / 1000) + " s, terminating it")
      root.playlistTimedOut = true
      playlistProc.signal(15)
    }
  }

  Timer {
    id: epgWatchdog
    interval: root.helperTimeoutMs
    repeat: false
    onTriggered: {
      if (!epgProc.running) return
      console.warn("omarchy-iptv: epg helper exceeded " + Math.floor(root.helperTimeoutMs / 1000) + " s, terminating it")
      root.epgTimedOut = true
      epgProc.signal(15)
    }
  }

  Timer {
    // Same bound for a source probe (section 4.6).
    id: probeWatchdog
    interval: root.helperTimeoutMs
    repeat: false
    onTriggered: {
      if (!sourceProbeProc.running) return
      console.warn("omarchy-iptv: source probe exceeded " + Math.floor(root.helperTimeoutMs / 1000) + " s, terminating it")
      root.probeTimedOut = true
      sourceProbeProc.signal(15)
    }
  }

  Timer {
    // Backstop for `switching` (risk R1): released by the new cache's first
    // load or failure; if neither arrives (a host that applied the settings
    // asynchronously, or not at all) the guide is unblocked here.
    id: switchTimeout
    interval: root.switchTimeoutMs
    repeat: false
    onTriggered: {
      if (!root.switching) return
      console.warn("omarchy-iptv: switch did not observe a cache load within " + root.switchTimeoutMs + " ms")
      root.finishSwitch()
    }
  }

  Timer {
    // The reattach loop (spike section 6). Each tick builds a FRESH Socket:
    // an object that has once failed to connect is dead forever, and the
    // thing we are retrying against is exactly the peer that just died, so
    // reusing one is guaranteed to fail silently. The burst is capped at
    // 12 tries = 3 s (C6): every failed attempt writes one WARN line to the
    // journal, and a free-running 250 ms loop is ~14k lines an hour. When
    // the burst is spent, one `player probe` decides whether there is
    // anything to attach to at all.
    id: playerSocketTimer
    interval: root.playerSocketRetryMs
    repeat: true
    running: false
    property int tries: 0
    onTriggered: {
      if (!root.playerWanted || root.socketAttached()) {
        playerSocketTimer.stop()
        return
      }
      playerSocketTimer.tries += 1
      if (root.attachPlayerSocket()) {
        playerSocketTimer.tries = 0
        playerSocketTimer.stop()
      } else if (playerSocketTimer.tries >= root.playerSocketTries) {
        playerSocketTimer.tries = 0
        playerSocketTimer.stop()
        root.runPlayerProbe()
      }
    }
  }

  Timer {
    // One bound for the player slot (F1): a helper verb that hangs is
    // terminated, and a `playerPending` that no socket ever confirmed is
    // released, so the birth edge can never latch the UI into "playing".
    id: playerWatchdog
    interval: root.playerTimeoutMs
    repeat: false
    onTriggered: {
      if (playerProc.running) {
        console.warn("omarchy-iptv: player helper exceeded " + Math.floor(root.playerTimeoutMs / 1000) + " s, terminating it")
        playerProc.signal(15)
        return
      }
      if (root.playerPending) {
        console.warn("omarchy-iptv: the player did not become observable")
        root.playerPending = false
      }
    }
  }

  Timer {
    // Backstop for `stopping` (4.10): normally cleared by the socket EOF
    // that confirms the death. A stop issued with no player attached has no
    // EOF coming, so this releases it.
    //
    // It is also where a stop that did NOT take is caught. `player stop` is
    // detached, so its reply is unobservable by construction, and it aborts
    // as `superseded` whenever the lock record holds a higher `--seq` than
    // ours - which a terminal `omarchy-iptv player stop` (the documented
    // uninstall escape hatch) or any other launcher leaves behind. Found
    // live: the UI went idle while the player kept playing. One probe
    // re-reads the record, and applyProbe() then stops it with a sequence
    // that is past whatever is recorded.
    id: stopSettleTimer
    interval: root.stopSettleMs
    repeat: false
    onTriggered: {
      root.stopAt = 0
      root.userStopped = false
      if (root.nowPlaying !== null || root.stopConfirmPending) return
      if (!root.socketAttached() && !root.playerUp) return
      console.warn("omarchy-iptv: the player outlived a stop, re-reading its sequence")
      root.stopConfirmPending = true
      root.runPlayerProbe()
    }
  }

  Timer {
    // The single re-read of an ambiguous probe (4.5): an idle or stashless
    // player is either a racing start or a foreign one, and 500 ms tells
    // them apart without a second guess.
    id: probeRetryTimer
    interval: root.playerProbeRetryMs
    repeat: false
    onTriggered: root.runPlayerProbe()
  }

  Timer {
    // The health verdict's automatic relaunch, or a verdict that could not
    // be issued because the player slot was busy. Skipped once the user
    // stopped or a play() already started a new player (D-LIVE-15).
    id: relaunchTimer
    interval: root.relaunchDelayMs
    repeat: false
    onTriggered: {
      if (root.userStopped || root.stopping || !root.nowPlaying) return
      if (playerProc.running) { relaunchTimer.restart(); return }
      var channel = root.channelIndex[String(root.nowPlaying.id)]
      if (!channel) {
        // The channel left the playlist (a source swap, a refresh that
        // dropped it) while the relaunch was queued: the one automatic
        // relaunch handlePlayerGone() kept the record for is never coming,
        // so the record ends here instead of outliving the shell.
        root.nowPlaying = null
        root.noteSessionOutcome("abandoned")
        return
      }
      if (root.playerUp) {
        // Still there and still not answering: the verdict stands.
        root.playSeq += 1
        root.issuePlayerSession("restart", channel, "term")
      } else {
        root.startPlayer(channel)
      }
    }
  }

  Timer {
    // Retry of a play that could not land: a zap the player did not answer,
    // or a start that lost the lock (`busy`) or did not bind in time
    // (`no_socket`). The same backoff as v0.2.0, 300 * n, three tries.
    id: playRetryTimer
    interval: root.playRetryBaseMs
    repeat: false
    onTriggered: {
      if (root.userStopped || root.stopping || !root.nowPlaying) return
      var id = String(root.nowPlaying.id)
      if (root.playerUp) {
        if (controlProc.running) root.pendingPlayId = id
        else root.runControl("play", root.playArgs(id))
        return
      }
      var channel = root.channelIndex[id]
      if (channel) root.startPlayer(channel)
    }
  }

  Timer {
    // The mpv window maps a moment after launch; retry the focus dispatch a
    // few times so Enter lands on the player (UX 7.5). `playerPending`
    // keeps the budget alive across a cold start (4.7).
    id: focusTimer
    interval: root.focusRetryMs
    repeat: true
    onTriggered: {
      if (!root.wantFocus || !root.playerUp || root.focusAttempts >= root.focusRetries) {
        focusTimer.stop()
        root.wantFocus = false
        return
      }
      root.focusAttempts += 1
      root.focusPlayer()
    }
  }

  // ------------------------------------------------------------ processes

  // Process.exited(exitCode, exitStatus) carries a QProcess::ExitStatus that
  // the linter cannot resolve from the Quickshell.Io qmltypes, so every
  // inline `onExited:` (typed or not) trips [signal-handler-parameters].
  // The handlers therefore live in Connections blocks, which lint clean and
  // behave identically at runtime (D-LIVE-14).
  Process {
    id: mkdirProc
    command: ["mkdir", "-p", "-m", "700", root.cacheDir, root.cacheDir + "/sources", root.stateDir, root.runtimeDir]
  }
  Connections {
    target: mkdirProc
    function onExited(exitCode, exitStatus) { stateInitProc.running = true }
  }

  Process {
    // S-02: FileView creates a missing file with mode 0644 and keeps the
    // mode of an existing one, so the helper pre-creates state.json 0600
    // (O_EXCL, so the check-and-create is race-free; an existing file is
    // only chmod-ed) before the first saveState(), which dirsReady gates.
    // Argv only; the helper prints one JSON line that is discarded.
    id: stateInitProc
    command: ["python3", root.helperPath, "state", "--state-dir", root.stateDir, "init"]
    stdout: StdioCollector { waitForEnd: true }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") console.warn("omarchy-iptv state init:", Model.redactUrls(text.trim()))
    }
  }
  Connections {
    target: stateInitProc
    function onExited(exitCode, exitStatus) {
      root.dirsReady = true
      if (root.stateSavePending) root.saveState()
      root.runNextCacheJob()
    }
  }

  Process {
    id: whichProc
    command: ["which", "mpv"]
    stdout: StdioCollector { waitForEnd: true }
  }
  Connections {
    target: whichProc
    function onExited(exitCode, exitStatus) { root.mpvAvailable = exitCode === 0 }
  }

  Process {
    id: playlistProc
    stdout: StdioCollector { id: playlistStdout; waitForEnd: true }
    stderr: StdioCollector {
      id: playlistStderr
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") console.warn("omarchy-iptv playlist:", Model.redactUrls(text.trim()))
    }
  }
  Connections {
    target: playlistProc
    function onExited(exitCode, exitStatus) { root.handlePlaylistExit(playlistStdout.text) }
  }

  Process {
    id: epgProc
    property bool nowOnly: false
    stdout: StdioCollector { id: epgStdout; waitForEnd: true }
    stderr: StdioCollector {
      id: epgStderr
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") console.warn("omarchy-iptv epg:", Model.redactUrls(text.trim()))
    }
  }
  Connections {
    target: epgProc
    function onExited(exitCode, exitStatus) { root.handleEpgExit(epgStdout.text, epgProc.nowOnly) }
  }

  Process {
    id: controlProc
    stdout: StdioCollector { id: controlStdout; waitForEnd: true }
    stderr: StdioCollector { id: controlStderr; waitForEnd: true }
  }
  Connections {
    target: controlProc
    function onExited(exitCode, exitStatus) { root.handleControlResult(controlStdout.text) }
  }

  Process {
    // Source probe (section 4.6): `playlist` into a candidate source's own
    // directory, independent of the active source's refresh.
    id: sourceProbeProc
    stdout: StdioCollector { id: probeStdout; waitForEnd: true }
    stderr: StdioCollector {
      id: probeStderr
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") console.warn("omarchy-iptv probe:", Model.redactUrls(text.trim()))
    }
  }
  Connections {
    target: sourceProbeProc
    function onExited(exitCode, exitStatus) { root.handleProbeExit(probeStdout.text) }
  }

  Process {
    // Cache directory jobs (section 4.7): migrate / remove / prune, keys only.
    id: cacheProc
    stdout: StdioCollector { id: cacheStdout; waitForEnd: true }
    stderr: StdioCollector {
      id: cacheStderr
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") console.warn("omarchy-iptv cache:", Model.redactUrls(text.trim()))
    }
  }
  Connections {
    target: cacheProc
    function onExited(exitCode, exitStatus) { root.handleCacheExit(cacheStdout.text) }
  }

  Process {
    // Clipboard fallback (D9): the text is data for the guide's field only;
    // capped here so a huge selection never becomes a binding value.
    id: clipboardProc
    command: ["wl-paste", "--no-newline", "--type", "text"]
    stdout: StdioCollector { id: clipboardStdout; waitForEnd: true }
    stderr: StdioCollector { waitForEnd: true }
  }
  Connections {
    target: clipboardProc
    function onExited(exitCode, exitStatus) {
      root.clipboardText(exitCode === 0 ? String(clipboardStdout.text).substring(0, Model.LIMITS.url * 4) : "")
    }
  }

  Process {
    // The player slot (F1): `player start` / `restart` / `probe`. Separate
    // from controlProc so a cold start - which can take seconds, since the
    // helper watches the first load - can never starve a zap, a status poll
    // or a stop. mpv itself is NOT a child of this process: the helper
    // double-forks it away, which is the whole point of the milestone.
    id: playerProc
    stdout: StdioCollector { id: playerStdout; waitForEnd: true }
    stderr: StdioCollector {
      id: playerStderr
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") console.warn("omarchy-iptv player:", Model.redactUrls(text.trim()))
    }
  }
  Connections {
    target: playerProc
    function onExited(exitCode, exitStatus) { root.handlePlayerResult(playerStdout.text) }
  }

  // The socket observer, one fresh object per attempt (spike C1, and the
  // binding amendment in ARCHITECTURE-PLAYER.md section 13). A Socket that
  // has once failed to connect ignores every later instruction in silence,
  // so the declarative single-object form the design first prescribed is
  // the one shape that cannot reattach.
  Component {
    id: playerSocketComponent

    Socket {
      path: root.socketPath

      onConnectionStateChanged: {
        // NB: this fires SYNCHRONOUSLY inside `connected = true`, before
        // the playerUp binding re-evaluates. Read `this`, never
        // root.playerUp or root.playerSocket (C4).
        if (this.connected) {
          playerSocketTimer.stop()
          root.onPlayerAttached(this)
          return
        }
        if (root.playerSocket !== this) return    // already replaced
        root.releasePlayerSocket()                // peer gone; never re-arm this one
        root.handlePlayerGone()
      }

      // A failed connect emits THIS and nothing else - no state change (C5).
      // QLocalSocket::LocalSocketError is not resolvable from the qmltypes,
      // the same lint case as Process.onExited (D-LIVE-14).
      // qmllint disable signal-handler-parameters
      onError: function (err) { root.onSocketError(err) }
      // qmllint enable signal-handler-parameters

      parser: SplitParser {
        splitMarker: "\n"
        onRead: function (line) { root.handlePlayerLine(String(line)) }
      }
    }
  }

  // omarchy-shell io.github.rmcdavid.iptv toggle | play <id-or-url> | stop |
  // next | previous | refresh | status   (R9)
  IpcHandler {
    target: root.pluginId

    function toggle(): string {
      if (root.shell && typeof root.shell.toggle === "function") {
        return root.shell.toggle(root.pluginId, "{}") ? "ok" : "unavailable"
      }
      return "unavailable"
    }
    function play(id: string): string {
      var key = String(id || "")
      if (!root.channelIndex[key]) {
        var byUrl = Model.findByUrl(root.channels, key)
        key = byUrl ? Model.channelId(byUrl) : ""
      }
      return key !== "" && root.play(key, true, "") ? "ok" : "unknown"
    }
    function stop(): string { root.stop(); return "ok" }
    function next(): string { return root.zap(1) ? "ok" : "nothing playing" }
    function previous(): string { return root.zap(-1) ? "ok" : "nothing playing" }
    function refresh(): string { root.refresh(); return "ok" }
    function status(): string { return JSON.stringify(root.statusSummary()) }
  }
}
