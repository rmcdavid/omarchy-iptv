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
//   - the single mpv Process and the now-playing state (decisions 1, 2, 12)
//   - the plugin IPC target       (omarchy-shell io.github.rmcdavid.iptv <fn>)
// Guide.qml receives this object as `service` (shell.qml injects it on load);
// BarWidget.qml resolves it through bar.shell.serviceFor(moduleName).
//
// Privacy (R12): nothing here ever logs, notifies or exposes a playlist,
// EPG or stream URL beyond scheme + host. Argv arrays only (section 8).
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
  // (STOP_QUIT_GRACE_MS, STOP_KILL_GRACE_MS, HEALTH_SKIPS_BEFORE_RESTART).
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
  readonly property var settings: Model.settingsFrom(Model.findBarEntry(shell ? shell.barConfig : null, pluginId))
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
  property var nowPlaying: null             // { id, name, group, launchedFrom, since }
  readonly property bool playing: mpvProc.running && nowPlaying !== null
  property var failedAt: ({})               // session-only { id: "HH:MM" } (R11)
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
  // D-LIVE-15: a `stop` that arrives while a helper call is in flight is
  // sent as soon as that call returns; a `play` over IPC that finds no
  // socket (player just relaunched) or no answer is retried with backoff.
  property bool stopPending: false
  property int playRetries: 0
  readonly property int relaunchDelayMs: 200
  readonly property int playRetryBaseMs: 300
  readonly property int playRetryMax: 3        // 300 + 600 + 900 ms = 1.8 s
  // D-LIVE-17: rung of the shutdown ladder already taken ("" idle, "quit",
  // "term", "kill"; Model.stopEscalation), a play() that arrived while the
  // old player was on its way out (started from handleMpvExit, never over
  // the dying socket) and the health ticks skipped in a row behind an
  // in-flight helper call (Model.healthTick).
  property string stopStage: ""
  readonly property bool stopping: stopStage !== ""
  property bool playAfterExit: false
  property int healthSkips: 0
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
    if (mpvProc.running && root.nowPlaying && root.nowPlaying.id === key) {
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
    root.previousPlaying = mpvProc.running ? root.nowPlaying : null
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
    if (mpvProc.running) {
      if (root.stopping) {
        // The player is on its way out (stop or health restart): the new
        // channel starts from handleMpvExit once the exit is observed and
        // never over the dying socket (D-LIVE-17).
        root.playAfterExit = true
        return true
      }
      if (controlProc.running) {
        // A zap burst: remember only the last target, applied when the
        // current helper call returns.
        root.pendingPlayId = key
      } else {
        root.runControl("play", ["play", "--id", key, "--socket", root.socketPath, "--cache-dir", root.activeCacheDir])
      }
      if (root.wantFocus) root.focusPlayer()
    } else {
      root.launchMpv(channel)
    }
    return true
  }

  // Ask mpv to quit over IPC, then SIGTERM, then SIGKILL, each after its
  // grace period (Model.stopEscalation, D-LIVE-17). nowPlaying clears at
  // once so the bar and the guide drop the channel; the process itself is
  // gone within the ladder's bound. A user stop never notifies.
  function stop() {
    root.pendingPlayId = ""
    root.wantFocus = false
    focusTimer.stop()
    // Nothing queued may resurrect the player after a stop (D-LIVE-15).
    relaunchTimer.stop()
    playRetryTimer.stop()
    root.relaunchPending = false
    root.playAfterExit = false
    root.playRetries = 0
    root.nowPlaying = null
    if (!mpvProc.running) {
      root.stopPending = false
      root.stopStage = ""
      stopTimer.stop()
      return
    }
    root.userStopped = true
    // A stop while the ladder already runs only cancelled the queued play.
    if (!root.stopping) root.escalateStop()
  }

  // One rung of the shutdown ladder; stopTimer re-arms for the next one
  // until handleMpvExit observes the exit (D-LIVE-17).
  function escalateStop() {
    if (!mpvProc.running) {
      stopTimer.stop()
      root.stopStage = ""
      return
    }
    var step = Model.stopEscalation(root.stopStage)
    if (step.action === "quit") {
      if (controlProc.running) root.stopPending = true
      else root.runControl("stop", ["stop", "--socket", root.socketPath])
    } else if (step.signal > 0) {
      if (step.signal === 9) console.warn("omarchy-iptv: mpv ignored SIGTERM, sending SIGKILL")
      mpvProc.signal(step.signal)
    }
    root.stopStage = step.action
    if (step.waitMs > 0) {
      stopTimer.interval = step.waitMs
      stopTimer.restart()
    } else {
      stopTimer.stop()
    }
  }

  // Health verdict: the player is unresponsive. It already failed to answer
  // over IPC, so the ladder starts at SIGTERM (SIGKILL after the grace
  // period); one automatic relaunch of nowPlaying follows the exit, never
  // racing the dying instance (D-LIVE-15, D-LIVE-17).
  function restartPlayer() {
    if (!mpvProc.running || root.stopping) return
    console.warn("omarchy-iptv: mpv unresponsive, restarting player")
    root.healthFailures = 0
    root.healthSkips = 0
    root.relaunchPending = !root.relaunched && root.nowPlaying !== null
    root.stopStage = "quit"
    root.escalateStop()
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
        // restore, handleMpvExit starts nowPlaying afresh (D-LIVE-17).
        root.playRetries = 0
      } else if (status.ok !== true && status.error) {
        var reason = Model.statusReason(status)
        var code = String(status.error.code)
        if (code === "not_running" && root.nowPlaying && !mpvProc.running) {
          // mpv vanished between two zaps: start a fresh player.
          root.lastError = reason
          var channel = root.channelIndex[root.nowPlaying.id]
          if (channel) root.launchMpv(channel)
        } else if ((code === "not_running" || code === "ipc_error") && mpvProc.running && root.nowPlaying
                   && !root.userStopped && root.playRetries < root.playRetryMax) {
          // The socket of a player that just (re)started is not up yet, or
          // mpv did not answer in time: retry with backoff instead of
          // losing the zap (D-LIVE-15).
          root.playRetries += 1
          playRetryTimer.interval = root.playRetryBaseMs * root.playRetries
          playRetryTimer.restart()
        } else {
          root.lastError = reason
          console.warn("omarchy-iptv: play failed:", reason)
          // The switch did not happen; mpv still plays the previous channel.
          if (mpvProc.running && root.previousPlaying) root.nowPlaying = root.previousPlaying
        }
      } else if (status.ok === true) {
        root.playRetries = 0
        root.previousPlaying = null
      }
    } else if (kind === "stop") {
      if (status.ok !== true && status.error && String(status.error.code) === "not_running" && !mpvProc.running) {
        root.nowPlaying = null
      }
    }
    // A stop requested while this call was in flight goes out now and
    // cancels any queued zap.
    if (root.stopPending) {
      root.stopPending = false
      root.pendingPlayId = ""
      if (mpvProc.running) root.runControl("stop", ["stop", "--socket", root.socketPath])
      return
    }
    // Apply the last queued zap of a burst.
    if (root.pendingPlayId !== "" && mpvProc.running) {
      var id = root.pendingPlayId
      root.pendingPlayId = ""
      root.runControl("play", ["play", "--id", id, "--socket", root.socketPath, "--cache-dir", root.activeCacheDir])
    } else {
      root.pendingPlayId = ""
    }
  }

  function launchMpv(channel) {
    var extra = Model.splitMpvArgs(root.mpvArgs)
    if (extra.rejected.length > 0) console.warn("omarchy-iptv: ignoring mpvArgs tokens:", extra.rejected.join(" "))
    root.mpvStderrTail = []
    root.stopStage = ""
    root.healthSkips = 0
    stopTimer.stop()
    // Known exposure (S-03, documented in the README): the FIRST channel's
    // stream URL and header values sit in mpv's argv for the life of the
    // process, readable by other local accounts through /proc/<pid>/cmdline
    // (`ps aux`), even after zapping to other channels over IPC. Later
    // channels only ever travel over the 0600 socket. Removing it means
    // starting mpv idle and loading the first channel over IPC too, which
    // is the M2 detached-mpv rework (R10); not changed in M1.
    mpvProc.command = Model.buildMpvArgv({
      socketPath: root.socketPath,
      name: channel.name,
      url: channel.url,
      headers: channel.headers || {},
      extraArgs: extra.args
    })
    mpvProc.running = true
    if (root.wantFocus) {
      root.focusAttempts = 0
      focusTimer.restart()
    }
  }

  function rememberStderr(line) {
    var clean = Model.redactUrls(String(line || "").replace(/\s+$/, ""))
    if (clean === "") return
    var tail = root.mpvStderrTail.slice()
    tail.push(clean)
    while (tail.length > 5) tail.shift()
    root.mpvStderrTail = tail
  }

  function handleMpvExit(exitCode, exitStatus) {
    stopTimer.stop()
    focusTimer.stop()
    playRetryTimer.stop()
    var current = root.nowPlaying
    var stopped = root.userStopped
    var userPlay = root.playAfterExit
    var relaunch = root.relaunchPending || userPlay
    root.userStopped = false
    root.relaunchPending = false
    root.playAfterExit = false
    root.stopPending = false
    root.stopStage = ""
    root.pendingPlayId = ""
    root.playRetries = 0
    root.healthSkips = 0
    if (relaunch && current && !stopped) {
      var channel = root.channelIndex[current.id]
      if (channel) {
        // The health check gets one automatic relaunch per player; a play()
        // the user issued during the shutdown starts a fresh one (D-LIVE-17).
        root.relaunched = !userPlay
        if (!userPlay) root.wantFocus = false
        // Deferred, not from inside the exit handler: the old socket file
        // is gone and an in-flight helper call has returned by then, and a
        // stop() in the meantime cancels it (D-LIVE-15).
        relaunchTimer.restart()
        return
      }
    }
    root.nowPlaying = null
    if (stopped || exitCode === 0) return
    // Non-zero exit without a user stop: stream failure (decision 12, R11).
    var reason = root.mpvStderrTail.length > 0
      ? root.mpvStderrTail[root.mpvStderrTail.length - 1]
      : ("mpv exited with code " + exitCode)
    root.lastError = reason
    if (current) {
      root.failedAt = Model.withFailed(root.failedAt, current.id, Model.formatClock(Math.floor(Date.now() / 1000)))
      root.notify("streamFailed", { name: current.name, reason: reason })
    }
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
  // keys we do not own). A no-op when the settings already match; `false`
  // (nothing changed / bare-string entry / no host) while a change was
  // needed emits sourcesPersistFailed (R2).
  function persistActive(playlistUrl, epgUrl) {
    if (root.playlistUrl === playlistUrl && root.epgUrl === epgUrl) return true
    if (!root.shell || typeof root.shell.updateEntryInline !== "function") {
      root.sourcesPersistFailed("persist_failed")
      return false
    }
    var entry = Model.entryWith(Model.findBarEntry(root.shell.barConfig, root.pluginId), { playlistUrl: playlistUrl, epgUrl: epgUrl, id: root.pluginId })
    if (root.shell.updateEntryInline(root.pluginId, entry) !== true) {
      console.warn("omarchy-iptv: updateEntryInline refused the settings change")
      root.sourcesPersistFailed("persist_failed")
      return false
    }
    return true
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
    // Health check while mpv runs: helper `status` over the socket; two
    // consecutive failures, or three ticks in a row behind an in-flight
    // helper call, -> SIGTERM, SIGKILL -> one automatic relaunch (D-LIVE-17).
    id: healthTimer
    interval: root.healthCheckMs
    repeat: true
    running: mpvProc.running
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
    // Drives the shutdown ladder (D-LIVE-17): each rung re-arms it for the
    // next grace period; handleMpvExit stops it.
    id: stopTimer
    interval: Model.STOP_QUIT_GRACE_MS
    repeat: false
    onTriggered: root.escalateStop()
  }

  Timer {
    // One automatic relaunch after the health check reaped a hung player,
    // or the channel a play() asked for during a shutdown (D-LIVE-17), a
    // moment after the exit (D-LIVE-15). Skipped once the user stopped or a
    // play() already started a new player.
    id: relaunchTimer
    interval: root.relaunchDelayMs
    repeat: false
    onTriggered: {
      if (mpvProc.running || root.userStopped || !root.nowPlaying) return
      var channel = root.channelIndex[root.nowPlaying.id]
      if (channel) root.launchMpv(channel)
      else root.nowPlaying = null
    }
  }

  Timer {
    // Retry of a `play` over IPC that found no socket or no answer
    // (D-LIVE-15). If another helper call is in flight the retry is queued
    // as the burst target and applied when that call returns.
    id: playRetryTimer
    interval: root.playRetryBaseMs
    repeat: false
    onTriggered: {
      if (!mpvProc.running || root.userStopped || root.stopping || !root.nowPlaying) return
      var id = String(root.nowPlaying.id)
      if (controlProc.running) root.pendingPlayId = id
      else root.runControl("play", ["play", "--id", id, "--socket", root.socketPath, "--cache-dir", root.activeCacheDir])
    }
  }

  Timer {
    // The mpv window maps a moment after launch; retry the focus dispatch a
    // few times so Enter lands on the player (UX 7.5).
    id: focusTimer
    interval: root.focusRetryMs
    repeat: true
    onTriggered: {
      if (!root.wantFocus || !mpvProc.running || root.focusAttempts >= root.focusRetries) {
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
    // The one and only mpv instance (decision 2). Destroying this object
    // kills mpv, which is why the service is keepLoaded.
    id: mpvProc
    // mpv prints its messages ("Failed to open ...") on stdout; keep stderr
    // too for loader/driver errors.
    stdout: SplitParser {
      onRead: function(line) { root.rememberStderr(line) }
    }
    stderr: SplitParser {
      onRead: function(line) { root.rememberStderr(line) }
    }
  }
  Connections {
    target: mpvProc
    function onExited(exitCode, exitStatus) { root.handleMpvExit(exitCode, exitStatus) }
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
