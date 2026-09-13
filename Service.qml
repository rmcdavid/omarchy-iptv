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
  readonly property bool epgConfigured: epgUrl !== ""
  // scheme + host only; safe to render anywhere
  readonly property string sourceLabel: Model.sourceLabel(playlistUrl)
  readonly property string sourceHost: Model.hostOf(playlistUrl)

  // ---- sources (M2-01, ARCHITECTURE-SOURCES.md section 4, rulings SR1-SR9).
  // The active source is still `playlistUrl` / `epgUrl` on the bar entry
  // (D1); the history lives in userState.sources (state.json v2, D2); each
  // source has its own cache directory under cacheDir/sources/<key>/ (D5).
  // The guide binds `sources` (view objects, SR1) and `activeSourceId`; it
  // never sees a state record or a URL outside sourceForEdit().
  property var limits: ({ url: 2048, label: 64, server: 512, field: 256, sources: 50 })   // TODO(lane1): replace with Model.LIMITS
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
  property var probeEdit: null                         // pending replacement record of a URL edit (applied only on success)
  property var sourceErrors: ({})                      // session-only { key: reason }, URL-free (Model.statusReason)
  property var settingsInvalid: null                   // validation result when playlistUrl is set but invalid (D16, SR8)
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
  readonly property string activeSourceKey: root.activeSourceKeyFor(root.userState, root.playlistUrl)
  readonly property string activeSourceId: activeSourceKey
  readonly property string activeSourceLabel: {
    var rec = root.findSource(root.userState.sources, root.activeSourceKey)
    return rec ? rec.label : root.sourceLabel
  }
  readonly property string activeCacheDir: (root.stateLoaded && root.cacheReady && root.activeSourceKey !== "")
    ? root.sourceCacheDir(root.cacheDir, root.activeSourceKey) : ""
  readonly property int sourceCount: Model.asList(root.userState.sources).length
  readonly property bool canAddSource: root.sourceCount < root.limits.sources && !root.probing
  // View objects for the guide (SR1); `sourcesChanged` is this property's
  // change signal (SR3) and fires on every state, settings or error change.
  readonly property var sources: root.sourceViews(root.userState, root.activeSourceKey, root.sourceErrors)

  // ---- data (read by Guide.qml / BarWidget.qml; never mutated by them)
  property var channels: []                 // Model.prepareChannels output
  property var channelIndex: ({})
  property var channelsMeta: ({})
  property var epgNow: ({})                 // tvg-id -> { now, next }
  property var epgMeta: ({})
  // Named userState: `state` would shadow QQuickItem.state.
  // v2 shape from the start (Model.emptyState() is still v1 until Lane 1
  // lands; TODO(lane1): replace with Model.emptyState()).
  property var userState: ({ version: 2, cacheLayout: 0, favorites: [], recents: [], lastPlayed: null, sources: [] })
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
    root.userState = root.carrySources(Model.recordPlayed(root.userState, channel, root.maxRecents, nowSec))
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
    root.userState = root.carrySources(Model.withFavorites(root.userState, Model.toggleFavorite(root.userState.favorites, id)))
    root.saveState()
    return Model.isFavorite(root.userState, id)
  }

  function removeRecent(id) {
    root.userState = root.carrySources(Model.removeRecent(root.userState, id))
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
    if (root.epgUrl === "") return
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
      epg: { configured: root.epgConfigured, loaded: root.epgLoaded, pending: root.epgPending, reason: root.epgReason },
      playlistReason: root.statusReason,
      warnings: root.playlistWarnings,
      lastError: root.lastError,
      activeSource: root.activeSourceSummary(),
      sources: root.sourcesSummary(root.userState, root.activeSourceKey)
    }
  }

  // ------------------------------------------------------------ sources API (SR2)
  // Every action returns { ok, code, message, id } synchronously (`id` = the
  // record concerned, "" when none; `field` names the offending form field
  // on a validation failure). Codes: ok, empty, scheme, invalid,
  // relative_path, unsafe_path, too_long, duplicate (id = the existing
  // record), too_many, label_taken, label_too_long, server_empty,
  // server_scheme, server_path, user_empty, pass_empty, user_too_long,
  // pass_too_long, busy, unknown_source, not_ready, persist_failed.
  // Asynchronous outcomes arrive through sourceProbeFinished.

  function sourceResult(ok, code, message, id, field) {
    var out = { ok: ok, code: code, message: message || "", id: id || "" }
    if (field) out.field = field
    return out
  }

  function sourcesReady() {
    if (!root.stateLoaded || !root.cacheReady) return root.sourceResult(false, "not_ready", "Sources are still loading", "")
    if (root.probing || root.switching) return root.sourceResult(false, "busy", root.probing ? "A fetch is already running" : "A switch is in progress", root.probingKey)
    return null
  }

  // Add a source (S1, S2): sanitize, validate both URLs, refuse duplicates
  // of a fetched record (an unfetched duplicate is re-probed instead, so a
  // failed first-run add can be resubmitted as-is), cap at 50, record with
  // fetchedAt 0, then probe into its own cache directory; the settings are
  // committed only when the probe succeeds (D8, SR7). `kind: "xtream"`
  // marks a record built by buildXtreamSource (view kind, UX 8.1).
  function addSource(fields) {
    var f = fields || {}
    var gate = root.sourcesReady()
    if (gate) return gate
    var playlist = root.validateSourceUrl(f.playlistUrl)
    if (!playlist.ok) return root.sourceResult(false, playlist.code, playlist.message, "", "playlistUrl")
    var epg = root.validateEpgField(f.epgUrl)
    if (!epg.ok) return root.sourceResult(false, epg.code, epg.message, "", "epgUrl")
    var st = root.userState
    var origin = f.kind === "xtream" ? "xtream" : (String(f.origin || "") || "guide")
    var existing = root.findSourceByUrl(st.sources, playlist.url)
    var label = root.labelInput(f.label)
    if (existing) {
      if (existing.fetchedAt > 0) return root.sourceResult(false, "duplicate", "Already in Sources as " + root.quoted(existing.label), existing.key)
      // Never fetched (a failed add, or a CLI record): adopt the form's
      // values and probe again.
      var patch = { epgUrl: epg.url }
      if (label.given) {
        var takenBy = root.labelTaken(st.sources, label.text, existing.key)
        if (label.tooLong) return root.sourceResult(false, "label_too_long", "Label too long - max " + root.limits.label + " characters", existing.key, "label")
        if (takenBy) return root.sourceResult(false, "label_taken", "A source named " + root.quoted(label.text) + " already exists", existing.key, "label")
        patch.label = label.text
        patch.labelCustom = true
      }
      root.userState = root.patchSource(st, existing.key, patch)
      root.saveState()
      return root.startProbe(existing.key, existing.key, "retry", true)
    }
    if (st.sources.length >= root.limits.sources) return root.sourceResult(false, "too_many", "Sources is full - remove one first (max " + root.limits.sources + ")", "")
    var finalLabel, custom
    if (label.given) {
      if (label.tooLong) return root.sourceResult(false, "label_too_long", "Label too long - max " + root.limits.label + " characters", "", "label")
      if (root.labelTaken(st.sources, label.text, "")) return root.sourceResult(false, "label_taken", "A source named " + root.quoted(label.text) + " already exists", "", "label")
      finalLabel = label.text
      custom = true
    } else {
      finalLabel = root.uniqueLabel(root.deriveLabel(playlist.url, playlist.kind), root.labelsOf(st.sources))
      custom = false
    }
    var added = root.addSourceRecord(st, {
      url: playlist.url, epgUrl: epg.url, kind: playlist.kind, label: finalLabel, labelCustom: custom, origin: origin
    }, Math.floor(Date.now() / 1000))
    root.userState = added.state
    root.saveState()
    return root.startProbe(added.key, added.key, "add", true)
  }

  // Edit a source (S4, S6). Label and EPG changes commit at once (an EPG
  // change of the active source is persisted and refreshed in the
  // background). A changed playlist URL probes into the new key's
  // directory first; the record moves to the new key, the old directory is
  // deleted and the settings follow only when the probe succeeds (SR7).
  function updateSource(id, fields) {
    var f = fields || {}
    var key = String(id || "")
    var gate = root.sourcesReady()
    if (gate) return gate
    var st = root.userState
    var rec = root.findSource(st.sources, key)
    if (!rec) return root.sourceResult(false, "unknown_source", "That source no longer exists", key)
    var patch = {}
    var label = root.labelInput(f.label)
    var epgUrl = rec.epgUrl
    if (f.epgUrl !== undefined) {
      var epg = root.validateEpgField(f.epgUrl)
      if (!epg.ok) return root.sourceResult(false, epg.code, epg.message, key, "epgUrl")
      epgUrl = epg.url
    }
    var urlChanged = false
    var playlist = null
    if (f.playlistUrl !== undefined) {
      playlist = root.validateSourceUrl(f.playlistUrl)
      if (!playlist.ok) return root.sourceResult(false, playlist.code, playlist.message, key, "playlistUrl")
      if (playlist.url !== rec.url) {
        var other = root.findSourceByUrl(st.sources, playlist.url)
        if (other) return root.sourceResult(false, "duplicate", "Already in Sources as " + root.quoted(other.label), other.key, "playlistUrl")
        urlChanged = true
      }
    }
    if (f.label !== undefined) {
      if (label.tooLong) return root.sourceResult(false, "label_too_long", "Label too long - max " + root.limits.label + " characters", key, "label")
      if (label.given) {
        if (root.labelTaken(st.sources, label.text, key)) return root.sourceResult(false, "label_taken", "A source named " + root.quoted(label.text) + " already exists", key, "label")
        patch.label = label.text
        patch.labelCustom = true
      } else {
        // Empty label: back to the derived default (UX 5.6).
        var derivedFrom = urlChanged ? playlist : { url: rec.url, kind: rec.kind }
        patch.label = root.uniqueLabel(root.deriveLabel(derivedFrom.url, derivedFrom.kind), root.labelsOf(st.sources, key))
        patch.labelCustom = false
      }
    }
    patch.epgUrl = epgUrl
    if (!urlChanged) {
      root.userState = root.patchSource(st, key, patch)
      root.saveState()
      if (key === root.activeSourceKey && epgUrl !== root.epgUrl) {
        if (!root.persistActive(rec.url, epgUrl)) return root.sourceResult(false, "persist_failed", "Could not save the settings", key)
      }
      return root.sourceResult(true, "ok", "", key)
    }
    // URL change: build the replacement in memory; nothing in the history
    // moves until the probe succeeds.
    var replacement = {}
    for (var k in rec) replacement[k] = rec[k]
    for (var p in patch) replacement[p] = patch[p]
    replacement.url = playlist.url
    replacement.kind = playlist.kind
    replacement.key = root.allocateSourceKey(root.sourcesWithout(st.sources, key), playlist.url)
    replacement.fetchedAt = 0
    replacement.channelCount = 0
    replacement.groupCount = 0
    if (!replacement.labelCustom && f.label === undefined) {
      replacement.label = root.uniqueLabel(root.deriveLabel(playlist.url, playlist.kind), root.labelsOf(st.sources, key))
    }
    root.probeEdit = replacement
    return root.startProbe(key, replacement.key, "edit", key === root.activeSourceKey)
  }

  // Remove a source (S7): drops the record, deletes its cache directory
  // through the helper and, when it was active, clears the settings so the
  // guide returns to the first-run state (playback, if any, continues).
  function removeSource(id) {
    var key = String(id || "")
    if (!root.stateLoaded || !root.cacheReady) return root.sourceResult(false, "not_ready", "Sources are still loading", key)
    if (root.probing && (root.probingKey === key || root.probeDirKey === key)) return root.sourceResult(false, "busy", "That source is being fetched", key)
    if (root.switching) return root.sourceResult(false, "busy", "A switch is in progress", key)
    var removed = root.removeSourceRecord(root.userState, key)
    if (!removed.removed) return root.sourceResult(false, "unknown_source", "That source no longer exists", key)
    var wasActive = key === root.activeSourceKey
    root.userState = removed.state
    root.saveState()
    root.sourceErrors = root.withoutKey(root.sourceErrors, key)
    root.queueCacheJob(["remove", "--key", key], null)
    if (wasActive) {
      if (!root.persistActive("", "")) {
        root.sourceRemoved(key)
        return root.sourceResult(false, "persist_failed", "Removed, but the settings could not be cleared", key)
      }
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
    var rec = root.findSource(root.userState.sources, key)
    if (!rec) return root.sourceResult(false, "unknown_source", "That source no longer exists", key)
    if (key === root.activeSourceKey) return root.sourceResult(true, "ok", "", key)
    if (!(rec.fetchedAt > 0)) return root.startProbe(key, key, "switch", true)
    root.userState = root.touchSource(root.userState, key, Math.floor(Date.now() / 1000))
    root.saveState()
    root.beginSwitch()
    if (!root.persistActive(rec.url, rec.epgUrl)) {
      root.abortSwitch()
      return root.sourceResult(false, "persist_failed", "Could not save the settings", key)
    }
    return root.sourceResult(true, "ok", "", key)
  }

  // Xtream form (S6, D10): builds the get.php / xmltv.php URLs and adds
  // them as an ordinary source. The password lives only inside the URLs
  // from here on; it is never stored or logged on its own.
  function buildXtreamSource(fields) {
    var f = fields || {}
    var built = root.xtreamUrls({ server: f.server, username: f.username, password: f.password })
    if (!built.ok) return root.sourceResult(false, built.code, built.message, "", built.field)
    return root.addSource({ playlistUrl: built.playlistUrl, epgUrl: built.epgUrl, label: f.label, kind: "xtream" })
  }

  // The only call that hands a URL to the guide: the edit form binds
  // `playlistMasked` / `epgMasked` and reveals the raw value on Ctrl+R.
  function sourceForEdit(id) {
    var rec = root.findSource(root.userState.sources, String(id || ""))
    if (!rec) return null
    return {
      id: rec.key, key: rec.key, label: rec.label, labelCustom: rec.labelCustom, kind: rec.kind, origin: rec.origin,
      host: root.hostForRecord(rec),
      playlistUrl: rec.url, epgUrl: rec.epgUrl,
      playlistMasked: root.maskUrl(rec.url), epgMasked: root.maskUrl(rec.epgUrl)
    }
  }

  // Probe again a record that failed to fetch (S8); a fetched record is
  // simply switched to.
  function retrySource(id) {
    var key = String(id || "")
    var gate = root.sourcesReady()
    if (gate) return gate
    var rec = root.findSource(root.userState.sources, key)
    if (!rec) return root.sourceResult(false, "unknown_source", "That source no longer exists", key)
    if (rec.fetchedAt > 0 && key !== root.activeSourceKey) return root.switchSource(key)
    return root.startProbe(key, key, "retry", true)
  }

  // Abort the running probe (UX 1.2 step 8): the helper is terminated, the
  // probe's cache directory is discarded, a record added by this probe is
  // dropped again and sourceProbeFinished carries `cancelled: true`.
  function cancelProbe() {
    if (!root.probing) return root.sourceResult(true, "ok", "", "")
    var key = root.probingKey
    root.probeCancelled = true
    probeWatchdog.stop()
    sourceProbeProc.signal(15)
    return root.sourceResult(true, "ok", "", key)
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
    root.userState = root.carrySources(Model.trimRecents(root.parseStateV2(text), root.maxRecents))
    root.stateLoaded = true
    root.reconcile()
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
    if (root.playlistStatus.ok === true) root.playlistWarnings = Model.statusWarnings(root.playlistStatus)
    else root.lastError = root.statusReason
  }

  function applyEpgStatus(text) {
    root.epgStatus = Model.parseHelperStatus(text, "epg")
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
      sourceHost: kind === "epg" ? Model.hostOf(root.epgUrl) : root.sourceHost,
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
      if (root.epgUrl === "") return
      root.epgAttempted = true
      epgProc.nowOnly = false
      epgProc.command = ["python3", root.helperPath, "epg", "--url", root.epgUrl, "--cache-dir", root.activeCacheDir]
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
      // The history row shows counts without opening N status files.
      if (root.activeSourceKey !== "") {
        root.userState = root.withSourceStats(root.userState, root.activeSourceKey, status)
        root.saveState()
      }
      if (manual) root.notify("playlistRefreshed", { channelCount: status.channelCount, groupCount: status.groupCount })
      root.playlistRefreshed(Number(status.channelCount) || 0, manual)
      // US6: the EPG follows the playlist (the helper restricts programmes
      // to the playlist's ids). Fetch it when none is loaded or its now/next
      // window has expired; a run already in flight is repeated (D-LIVE-02).
      if (root.epgUrl !== "" && (!root.epgLoaded || Model.epgNowStale(root.epgMeta, Math.floor(Date.now() / 1000)))) root.refreshEpg(true)
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
      root.epgStatus = status
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
    var entry = root.entryWith(Model.findBarEntry(root.shell.barConfig, root.pluginId), { playlistUrl: playlistUrl, epgUrl: epgUrl })
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
    var rec = mode === "edit" ? root.probeEdit : root.findSource(root.userState.sources, key)
    if (!rec) return root.sourceResult(false, "unknown_source", "That source no longer exists", key)
    if (sourceProbeProc.running) return root.sourceResult(false, "busy", "A fetch is already running", root.probingKey)
    root.probingKey = key
    root.probeDirKey = dirKey
    root.probeMode = mode
    root.probeCommit = commit
    root.probeCancelled = false
    root.probeTimedOut = false
    root.sourceErrors = root.withoutKey(root.sourceErrors, key)
    sourceProbeProc.command = ["python3", root.helperPath, "playlist", "--url", rec.url, "--cache-dir", root.sourceCacheDir(root.cacheDir, dirKey)]
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
    var edit = root.probeEdit
    root.probingKey = ""
    root.probeDirKey = ""
    root.probeMode = ""
    root.probeCancelled = false
    root.probeTimedOut = false
    root.probeEdit = null
    var st = root.userState
    var rec = mode === "edit" ? edit : root.findSource(st.sources, key)
    var host = rec ? root.hostForRecord(rec) : ""
    var nowSec = Math.floor(Date.now() / 1000)
    if (cancelled) {
      // Discard the directory the probe was writing; an add's record goes
      // with it (the form keeps the typed values, UX 5.5).
      root.queueCacheJob(["remove", "--key", dirKey], null)
      if (mode === "add") {
        root.userState = root.removeSourceRecord(st, key).state
        root.saveState()
      }
      root.sourceProbeFinished({ ok: false, id: key, channelCount: 0, groupCount: 0, reason: "", host: host, cancelled: true, replacedId: "" })
      return
    }
    var status = Model.parseHelperStatus(timedOut ? root.helperTimeoutStatus("playlist", false) : text, "playlist")
    if (!rec) {
      root.sourceProbeFinished({ ok: false, id: key, channelCount: 0, groupCount: 0, reason: "That source no longer exists", host: "", cancelled: false, replacedId: "" })
      return
    }
    if (status.ok === true) {
      var newKey = key
      if (mode === "edit") {
        // The replacement takes the old record's place; the old directory goes.
        newKey = rec.key
        st = root.replaceSourceRecord(st, key, rec)
        root.queueCacheJob(["remove", "--key", key], null)
        root.sourceErrors = root.withoutKey(root.sourceErrors, key)
      }
      st = root.withSourceStats(st, newKey, status)
      st = root.touchSource(st, newKey, nowSec)
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
    // Failure (S8): the previous active source is untouched; the record
    // keeps fetchedAt 0 (an edit's replacement is dropped, the original
    // stays intact) and carries a session-only reason.
    var reason = Model.statusReason(status)
    if (mode === "edit") root.queueCacheJob(["remove", "--key", dirKey], null)
    root.sourceErrors = root.withKey(root.sourceErrors, key, reason)
    root.sourceProbeFinished({ ok: false, id: key, channelCount: 0, groupCount: 0, reason: reason, host: host, cancelled: false, replacedId: "" })
  }

  // D3 / SR8: the settings are the source of truth for the active source;
  // the history follows them. Runs on state load and on every playlistUrl /
  // epgUrl change (a CLI `omarchy bar set` included). Idempotent.
  function reconcile() {
    if (!root.stateLoaded) return
    var out = root.reconcileSources(root.userState, root.playlistUrl, root.epgUrl, root.activeSourceKey, Math.floor(Date.now() / 1000))
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
      // state shows the validation reason instead.
      root.playlistStatus = ({ ok: false, kind: "playlist", stale: false, sourceHost: "", error: { code: out.invalid.code, message: root.invalidReason(out.invalid.code) } })
      root.lastError = root.statusReason
    }
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
        root.userState = root.withCacheLayout(root.userState, 2)
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
    if (root.cacheStale(root.playlistStatus, root.refreshMinutes, nowSec)) root.refreshPlaylist(true)
    if (root.epgUrl !== "" && !epgProc.running) root.refreshEpg(true)
  }

  // Reset the per-source data to "nothing known yet" so no reason, count
  // or programme of the previous source survives a swap (D-LIVE-10).
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
    root.lastError = ""
  }

  function activeSourceSummary() {
    var rec = root.findSource(root.userState.sources, root.activeSourceKey)
    return rec ? { id: rec.key, label: rec.label, host: root.hostForRecord(rec) } : null
  }

  // ------------------------------------------------------------ Model shims
  // TODO(lane1): every function in this section mirrors a Model.js function
  // of ARCHITECTURE-SOURCES.md section 3 with the same signature. Once Lane
  // 1's `feat(model): source logic` merges, replace each body with
  // `return Model.<name>(...)` (or sed `root.<name>(` -> `Model.<name>(`)
  // and delete the shim. Pure, ES5, null-safe, no URL ever logged.

  // TODO(lane1): replace with Model.sanitizeInput
  function sanitizeInput(text, max) {
    var s = String(text === undefined || text === null ? "" : text).replace(/[\u0000-\u001f\u007f-\u009f]/g, "")
    s = s.replace(/^[ \u00a0]+|[ \u00a0]+$/g, "")
    return s.length > max ? s.substring(0, max) : s
  }

  // UX-SOURCES.md 5.4 copy for the synchronous codes.
  // TODO(lane1): replace with Model.sourceReason
  function invalidReason(code) {
    var table = {
      empty: "Enter a playlist URL or path",
      scheme: "Start with http://, https://, or / for a local file",
      invalid: "Invalid URL - check the host",
      relative_path: "Use an absolute path (starts with /, not ~)",
      unsafe_path: "Path not allowed",
      too_long: "Too long - max 2,048 characters"
    }
    return table[String(code || "")] || "Invalid URL"
  }

  // TODO(lane1): replace with Model.validateSourceUrl
  function validateSourceUrl(text) {
    function fail(code) { return { ok: false, code: code, message: root.invalidReason(code), kind: "", url: "", host: "" } }
    function checkPath(path) {
      var unsafe = ["/proc", "/sys", "/dev"]
      for (var u = 0; u < unsafe.length; u++) if (path === unsafe[u] || path.indexOf(unsafe[u] + "/") === 0) return fail("unsafe_path")
      return { ok: true, code: "ok", message: "", kind: "file", url: path, host: "" }
    }
    var s = root.sanitizeInput(text, root.limits.url + 1)
    if (s === "") return fail("empty")
    if (s.length > root.limits.url) return fail("too_long")
    if (s.charAt(0) === "/") return checkPath(s)
    if (s.charAt(0) === "~" || s.indexOf("./") === 0 || s.indexOf("../") === 0) return fail("relative_path")
    var m = s.match(/^([A-Za-z][A-Za-z0-9+.-]*):([\s\S]*)$/)
    if (!m) return fail("scheme")
    var scheme = m[1].toLowerCase()
    var rest = m[2]
    if (scheme === "file") {
      if (rest.indexOf("//") !== 0) return fail("invalid")
      var fileRest = rest.substring(2)
      var slash = fileRest.indexOf("/")
      if (slash === -1) return fail("invalid")
      var filePath = fileRest.substring(slash)
      try { filePath = decodeURIComponent(filePath) } catch (e) { return fail("invalid") }
      return checkPath(filePath)
    }
    if (scheme !== "http" && scheme !== "https") return fail("scheme")
    if (rest.indexOf("//") !== 0) return fail("invalid")
    var after = rest.substring(2)
    if (/\s/.test(after)) return fail("invalid")
    var end = after.length
    var stops = ["/", "?", "#"]
    for (var i = 0; i < stops.length; i++) {
      var at = after.indexOf(stops[i])
      if (at !== -1 && at < end) end = at
    }
    var authority = after.substring(0, end)
    var tail = after.substring(end)
    var atSign = authority.lastIndexOf("@")
    var userinfo = atSign === -1 ? "" : authority.substring(0, atSign)
    var hostport = atSign === -1 ? authority : authority.substring(atSign + 1)
    var host, port
    if (hostport.charAt(0) === "[") {
      var close = hostport.indexOf("]")
      if (close === -1) return fail("invalid")
      host = hostport.substring(0, close + 1)
      var portPart = hostport.substring(close + 1)
      if (portPart !== "" && portPart.charAt(0) !== ":") return fail("invalid")
      port = portPart.substring(1)
    } else {
      var colon = hostport.lastIndexOf(":")
      host = colon === -1 ? hostport : hostport.substring(0, colon)
      port = colon === -1 ? "" : hostport.substring(colon + 1)
    }
    host = host.toLowerCase()
    if (host === "") return fail("invalid")
    if (port !== "" && !/^\d+$/.test(port)) return fail("invalid")
    if (port === (scheme === "http" ? "80" : "443")) port = ""
    var hashAt = tail.indexOf("#")
    if (hashAt !== -1) tail = tail.substring(0, hashAt)
    var queryAt = tail.indexOf("?")
    var path = queryAt === -1 ? tail : tail.substring(0, queryAt)
    var query = queryAt === -1 ? "" : tail.substring(queryAt + 1)
    if (path === "") path = "/"
    var url = scheme + "://" + (userinfo !== "" ? userinfo + "@" : "") + host + (port !== "" ? ":" + port : "") + path + (query !== "" ? "?" + query : "")
    return { ok: true, code: "ok", message: "", kind: "http", url: url, host: host }
  }

  // EPG is optional: "" is fine, anything else must validate.
  function validateEpgField(text) {
    var s = root.sanitizeInput(text, root.limits.url + 1)
    if (s === "") return { ok: true, code: "ok", message: "", url: "" }
    var v = root.validateSourceUrl(s)
    if (!v.ok) return { ok: false, code: v.code, message: "EPG: " + v.message.charAt(0).toLowerCase() + v.message.substring(1), url: "" }
    return { ok: true, code: "ok", message: "", url: v.url }
  }

  // TODO(lane1): replace with Model.sourceKey
  function sourceKey(url) { return Model.fnv1a32(url) }

  // TODO(lane1): replace with Model.allocateSourceKey
  function allocateSourceKey(sources, url) {
    var existing = root.findSourceByUrl(sources, url)
    if (existing) return existing.key
    var base = root.sourceKey(url)
    var key = base
    var n = 2
    while (root.findSource(sources, key)) key = base + "-" + (n++)
    return key
  }

  // TODO(lane1): replace with Model.findSource
  function findSource(sources, key) {
    var list = Model.asList(sources)
    for (var i = 0; i < list.length; i++) if (list[i] && list[i].key === key) return list[i]
    return null
  }

  // TODO(lane1): replace with Model.findSourceByUrl
  function findSourceByUrl(sources, url) {
    var list = Model.asList(sources)
    for (var i = 0; i < list.length; i++) if (list[i] && list[i].url === url) return list[i]
    return null
  }

  function sourcesWithout(sources, key) {
    var out = []
    var list = Model.asList(sources)
    for (var i = 0; i < list.length; i++) if (list[i] && list[i].key !== key) out.push(list[i])
    return out
  }

  function labelsOf(sources, exceptKey) {
    var out = []
    var list = Model.asList(sources)
    for (var i = 0; i < list.length; i++) if (list[i] && list[i].key !== exceptKey) out.push(list[i].label)
    return out
  }

  // { given, text, tooLong } for a label field: control characters
  // stripped and trimmed before the length check so a pasted newline
  // never counts.
  function labelInput(text) {
    var cleaned = String(text === undefined || text === null ? "" : text).replace(/[\u0000-\u001f\u007f-\u009f]/g, "").replace(/^[ \u00a0]+|[ \u00a0]+$/g, "")
    return { given: cleaned !== "", text: root.sanitizeInput(cleaned, root.limits.label), tooLong: cleaned.length > root.limits.label }
  }

  // TODO(lane1): replace with Model.validateLabel (case-insensitive, self excluded)
  function labelTaken(sources, label, selfKey) {
    var wanted = String(label || "").toLowerCase()
    var list = Model.asList(sources)
    for (var i = 0; i < list.length; i++) {
      if (list[i] && list[i].key !== selfKey && String(list[i].label).toLowerCase() === wanted) return list[i].key
    }
    return ""
  }

  function quoted(text) { return Model.QUOTE_OPEN + String(text || "") + Model.QUOTE_CLOSE }

  // UX-SOURCES.md 5.6. TODO(lane1): replace with Model.deriveLabel
  function deriveLabel(url, kind) {
    var label
    if (kind === "file") {
      var parts = String(url || "").replace(/\/+$/, "").split("/")
      label = parts[parts.length - 1] || "local file"
    } else {
      var after = String(url || "")
      var sep = after.indexOf("://")
      if (sep !== -1) after = after.substring(sep + 3)
      var end = after.length
      var stops = ["/", "?", "#"]
      for (var i = 0; i < stops.length; i++) {
        var at = after.indexOf(stops[i])
        if (at !== -1 && at < end) end = at
      }
      var hostport = after.substring(0, end)
      var atSign = hostport.lastIndexOf("@")
      if (atSign !== -1) hostport = hostport.substring(atSign + 1)
      if (hostport.indexOf("www.") === 0) hostport = hostport.substring(4)
      label = hostport || "source"
    }
    return label.length > root.limits.label ? label.substring(0, root.limits.label) : label
  }

  // TODO(lane1): replace with Model.uniqueLabel
  function uniqueLabel(label, existing) {
    var taken = {}
    var list = Model.asList(existing)
    for (var i = 0; i < list.length; i++) taken[String(list[i]).toLowerCase()] = true
    var base = root.sanitizeInput(label, root.limits.label)
    if (!taken[base.toLowerCase()]) return base
    for (var n = 2; ; n++) {
      var tail = " " + n
      var candidate = base.substring(0, root.limits.label - tail.length).replace(/ +$/, "") + tail
      if (!taken[candidate.toLowerCase()]) return candidate
    }
  }

  // SR4: userinfo, every query value except type / output, and the
  // fragment become "****"; paths are never masked.
  // TODO(lane1): replace with Model.maskUrl
  function maskUrl(url) {
    var s = String(url || "")
    var m = s.match(/^(https?:\/\/)(?:([^\/?#]*)@)?([^\/?#]*)([^?#]*)(?:\?([^#]*))?(?:#(.*))?$/i)
    if (!m) return s
    var out = m[1].toLowerCase() + (m[2] !== undefined ? "****@" : "") + m[3] + m[4]
    if (m[5] !== undefined) {
      var parts = m[5].split("&")
      for (var i = 0; i < parts.length; i++) {
        var eq = parts[i].indexOf("=")
        if (eq === -1) continue
        var name = parts[i].substring(0, eq)
        parts[i] = name + "=" + (name === "type" || name === "output" ? parts[i].substring(eq + 1) : "****")
      }
      out += "?" + parts.join("&")
    }
    if (m[6] !== undefined) out += "#****"
    return out
  }

  // UX-SOURCES.md 5.4 / 1.8: server must be http(s)://host[:port] with
  // no path, credentials percent-encoded with the RFC 3986 unreserved set.
  // TODO(lane1): replace with Model.xtreamUrls
  function xtreamUrls(fields) {
    var f = fields || {}
    function fail(code, message, field) { return { ok: false, code: code, message: message, field: field, playlistUrl: "", epgUrl: "", host: "" } }
    function enc(v) {
      return encodeURIComponent(v).replace(/[!'()*]/g, function(c) { return "%" + c.charCodeAt(0).toString(16).toUpperCase() })
    }
    var server = root.sanitizeInput(f.server, root.limits.server)
    if (server === "") return fail("server_empty", "Enter the server URL", "server")
    if (!/^https?:\/\//i.test(server)) return fail("server_scheme", "Server must start with http:// or https://", "server")
    var v = root.validateSourceUrl(server)
    if (!v.ok) return fail("invalid", "Invalid URL - check the host", "server")
    var m = v.url.match(/^(https?:\/\/)(?:([^\/?#]*)@)?([^\/?#]*)(.*)$/)
    if (!m || m[2] !== undefined || (m[4] !== "/" && m[4] !== "")) return fail("server_path", "Server is just http://host:port - no path", "server")
    var base = m[1] + m[3]
    var userRaw = String(f.username === undefined || f.username === null ? "" : f.username).replace(/[\u0000-\u001f\u007f-\u009f]/g, "").replace(/^[ \u00a0]+|[ \u00a0]+$/g, "")
    var passRaw = String(f.password === undefined || f.password === null ? "" : f.password).replace(/[\u0000-\u001f\u007f-\u009f]/g, "").replace(/^[ \u00a0]+|[ \u00a0]+$/g, "")
    if (userRaw === "") return fail("user_empty", "Enter the username", "username")
    if (userRaw.length > root.limits.field) return fail("user_too_long", "Username too long - max " + root.limits.field + " characters", "username")
    if (passRaw === "") return fail("pass_empty", "Enter the password", "password")
    if (passRaw.length > root.limits.field) return fail("pass_too_long", "Password too long - max " + root.limits.field + " characters", "password")
    var credentials = "username=" + enc(userRaw) + "&password=" + enc(passRaw)
    return {
      ok: true, code: "ok", message: "", field: "",
      playlistUrl: base + "/get.php?" + credentials + "&type=m3u_plus&output=ts",
      epgUrl: base + "/xmltv.php?" + credentials,
      host: v.host
    }
  }

  function hostForRecord(rec) {
    if (!rec) return ""
    if (rec.kind === "file") return "local file"
    return root.validateSourceUrl(rec.url).host
  }

  // SR1 view object. TODO(lane1): replace with Model.sourceView
  function sourceView(rec, activeKey, errors) {
    var fetched = rec.fetchedAt > 0
    return {
      id: rec.key, key: rec.key, label: rec.label,
      kind: rec.origin === "xtream" ? "xtream" : (rec.kind === "file" ? "file" : "url"),
      host: root.hostForRecord(rec), hasEpg: rec.epgUrl !== "",
      channelCount: fetched ? rec.channelCount : -1, groupCount: fetched ? rec.groupCount : 0,
      cachedAt: rec.fetchedAt, lastUsedAt: rec.lastUsed, active: rec.key === activeKey,
      origin: rec.origin, labelCustom: rec.labelCustom,
      errorReason: errors && errors[rec.key] ? String(errors[rec.key]) : ""
    }
  }

  function sourceViews(st, activeKey, errors) {
    var out = []
    var list = st && st.sources ? st.sources : []
    for (var i = 0; i < list.length; i++) out.push(root.sourceView(list[i], activeKey, errors))
    return out
  }

  // TODO(lane1): replace with Model.sourcesSummary
  function sourcesSummary(st, activeKey) {
    var out = []
    var list = st && st.sources ? st.sources : []
    for (var i = 0; i < list.length; i++) {
      var rec = list[i]
      out.push({ id: rec.key, label: rec.label, host: root.hostForRecord(rec), active: rec.key === activeKey, channelCount: rec.channelCount, lastUsed: rec.lastUsed })
    }
    return out
  }

  // TODO(lane1): replace with Model.sourceCacheDir
  function sourceCacheDir(cacheDir, key) {
    if (!cacheDir || !/^[0-9a-f]{8}(-[0-9]{1,3})?$/.test(String(key || ""))) return ""
    return cacheDir + "/sources/" + key
  }

  // TODO(lane1): replace with Model.activeSourceKey
  function activeSourceKeyFor(st, playlistUrl) {
    if (!playlistUrl) return ""
    var v = root.validateSourceUrl(playlistUrl)
    if (!v.ok) return ""
    var rec = root.findSourceByUrl(st ? st.sources : [], v.url)
    return rec ? rec.key : ""
  }

  // Section 2.1 field rules for one record; null drops it.
  function parseSourceRecord(raw) {
    if (!raw || typeof raw !== "object") return null
    var key = String(raw.key || "")
    if (!/^[0-9a-f]{8}(-[0-9]{1,3})?$/.test(key)) return null
    if (typeof raw.url !== "string") return null
    var playlist = root.validateSourceUrl(raw.url)
    if (!playlist.ok) return null
    var epg = typeof raw.epgUrl === "string" && raw.epgUrl !== "" ? root.validateSourceUrl(raw.epgUrl) : null
    var origins = ["guide", "xtream", "cli", "migrated"]
    function count(v) { var n = Math.floor(Number(v) || 0); return n > 0 ? n : 0 }
    return {
      key: key, url: playlist.url, epgUrl: epg && epg.ok ? epg.url : "", kind: playlist.kind,
      label: root.sanitizeInput(raw.label, root.limits.label) || root.deriveLabel(playlist.url, playlist.kind),
      labelCustom: raw.labelCustom === true,
      origin: origins.indexOf(raw.origin) !== -1 ? raw.origin : "guide",
      addedAt: count(raw.addedAt), lastUsed: count(raw.lastUsed), fetchedAt: count(raw.fetchedAt),
      channelCount: count(raw.channelCount), groupCount: count(raw.groupCount)
    }
  }

  // v1 or v2 text -> v2 object. TODO(lane1): replace with Model.parseState
  function parseStateV2(text) {
    var st = Model.parseState(text)
    var parsed = Model.parseJsonObject(text)
    var sources = []
    var list = parsed ? Model.asList(parsed.sources) : []
    for (var i = 0; i < list.length && sources.length < root.limits.sources; i++) {
      var rec = root.parseSourceRecord(list[i])
      if (!rec || root.findSource(sources, rec.key) || root.findSourceByUrl(sources, rec.url)) continue
      sources.push(rec)
    }
    return root.cloneState(st, { sources: sources, cacheLayout: parsed && parsed.cacheLayout === 2 ? 2 : 0 })
  }

  // TODO(lane1): replace with Model.cloneState
  function cloneState(st, patch) {
    var base = st || Model.emptyState()
    var out = {
      version: 2,
      cacheLayout: base.cacheLayout === 2 ? 2 : 0,
      favorites: Model.asList(base.favorites).slice(),
      recents: Model.asList(base.recents).slice(),
      lastPlayed: base.lastPlayed || null,
      sources: Model.asList(base.sources).slice()
    }
    for (var k in patch) out[k] = patch[k]
    return out
  }

  // The shipped reducers (recordPlayed, withFavorites, removeRecent,
  // trimRecents) rebuild {version, favorites, recents, lastPlayed} and drop
  // the v2 keys; carry them from the state in memory.
  // TODO(lane1): remove once every Model reducer goes through cloneState
  function carrySources(next) {
    var prev = root.userState
    return root.cloneState(next, {
      sources: next && next.sources !== undefined ? next.sources : Model.asList(prev.sources).slice(),
      cacheLayout: next && next.cacheLayout !== undefined ? next.cacheLayout : (prev.cacheLayout === 2 ? 2 : 0)
    })
  }

  // TODO(lane1): replace with Model.withCacheLayout
  function withCacheLayout(st, n) { return root.cloneState(st, { cacheLayout: n }) }

  // TODO(lane1): replace with Model.addSource (validation happens in addSource above)
  function addSourceRecord(st, fields, nowSec) {
    var key = root.allocateSourceKey(st.sources, fields.url)
    var sources = Model.asList(st.sources).slice()
    sources.push({
      key: key, url: fields.url, epgUrl: fields.epgUrl || "", kind: fields.kind, label: fields.label, labelCustom: fields.labelCustom === true,
      origin: fields.origin || "guide", addedAt: nowSec, lastUsed: nowSec, fetchedAt: 0, channelCount: 0, groupCount: 0
    })
    return { state: root.cloneState(st, { sources: sources }), key: key }
  }

  function patchSource(st, key, patch) {
    var sources = []
    var list = Model.asList(st.sources)
    for (var i = 0; i < list.length; i++) {
      if (list[i].key !== key) { sources.push(list[i]); continue }
      var next = {}
      for (var k in list[i]) next[k] = list[i][k]
      for (var p in patch) next[p] = patch[p]
      sources.push(next)
    }
    return root.cloneState(st, { sources: sources })
  }

  function replaceSourceRecord(st, key, record) {
    var sources = []
    var list = Model.asList(st.sources)
    for (var i = 0; i < list.length; i++) sources.push(list[i].key === key ? record : list[i])
    return root.cloneState(st, { sources: sources })
  }

  // TODO(lane1): replace with Model.removeSource
  function removeSourceRecord(st, key) {
    var removed = root.findSource(st.sources, key)
    return { state: root.cloneState(st, { sources: root.sourcesWithout(st.sources, key) }), removed: removed || null }
  }

  // TODO(lane1): replace with Model.touchSource
  function touchSource(st, key, nowSec) { return root.patchSource(st, key, { lastUsed: nowSec }) }

  // TODO(lane1): replace with Model.withSourceStats
  function withSourceStats(st, key, status) {
    if (!status || status.ok !== true) return st
    return root.patchSource(st, key, {
      fetchedAt: Number(status.fetchedAt) || Math.floor(Date.now() / 1000),
      channelCount: Number(status.channelCount) || 0,
      groupCount: Number(status.groupCount) || 0
    })
  }

  // TODO(lane1): replace with Model.reconcileSources
  function reconcileSources(st, playlistUrl, epgUrl, previousActiveKey, nowSec) {
    var out = { state: st, changed: false, activeKey: "", added: "", evicted: [], invalid: null }
    if (!playlistUrl) return out
    var playlist = root.validateSourceUrl(playlistUrl)
    if (!playlist.ok) {
      out.invalid = playlist
      return out
    }
    var epg = root.validateEpgField(epgUrl)
    var epgNorm = epg.ok ? epg.url : ""
    var rec = root.findSourceByUrl(st.sources, playlist.url)
    if (rec) {
      out.activeKey = rec.key
      var patch = {}
      if (rec.key !== previousActiveKey) patch.lastUsed = nowSec
      if (rec.epgUrl !== epgNorm) patch.epgUrl = epgNorm
      for (var k in patch) {
        out.state = root.patchSource(st, rec.key, patch)
        out.changed = true
        break
      }
      return out
    }
    // Unknown URL (S5): add it with a derived label; the very first v2 run
    // attributes the pre-existing setting to the migration.
    var sources = Model.asList(st.sources).slice()
    var evicted = []
    while (sources.length >= root.limits.sources) {
      var oldest = -1
      for (var i = 0; i < sources.length; i++) {
        if (oldest === -1 || sources[i].lastUsed < sources[oldest].lastUsed) oldest = i
      }
      evicted.push(sources[oldest].key)
      sources.splice(oldest, 1)
    }
    var origin = st.cacheLayout !== 2 && sources.length === 0 ? "migrated" : "cli"
    var added = root.addSourceRecord(root.cloneState(st, { sources: sources }), {
      url: playlist.url, epgUrl: epgNorm, kind: playlist.kind,
      label: root.uniqueLabel(root.deriveLabel(playlist.url, playlist.kind), root.labelsOf(sources, "")),
      labelCustom: false, origin: origin
    }, nowSec)
    out.state = added.state
    out.changed = true
    out.added = added.key
    out.activeKey = added.key
    out.evicted = evicted
    return out
  }

  // TODO(lane1): replace with Model.entryWith
  function entryWith(entry, patch) {
    var out = {}
    if (entry && typeof entry === "object") for (var k in entry) out[k] = entry[k]
    for (var p in patch) out[p] = patch[p]
    out.id = root.pluginId
    return out
  }

  // TODO(lane1): replace with Model.cacheStale
  function cacheStale(status, refreshMinutes, nowSec) {
    if (!status || status.ok !== true) return true
    var fetchedAt = Number(status.fetchedAt) || 0
    if (fetchedAt <= 0) return true
    return nowSec - fetchedAt >= (Number(refreshMinutes) || 0) * 60
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

  onPlaylistUrlChanged: {
    // A new source starts clean: the previous source's reason and host must
    // not stay on screen while its first fetch runs (UX 4.5, D-LIVE-10).
    // The fetch itself is driven by the new cache's freshness once its
    // directory is bound (section 4.4 step 6), never directly from here.
    root.playlistStatus = ({ ok: false, kind: "playlist", stale: false, error: null })
    root.playlistWarnings = []
    root.lastError = ""
    root.reconcile()
  }
  onEpgUrlChanged: {
    // Same rule as refreshEpg: read the setting itself. With the derived
    // `epgConfigured` (stale false on an empty -> value change) this handler
    // took the "cleared" branch and the first EPG never loaded (D-LIVE-02).
    if (root.epgUrl === "") {
      root.epgLoaded = false
      root.epgAttempted = false
      root.epgNow = ({})
      root.epgStatus = ({ ok: false, kind: "epg", stale: false, error: null })
      return
    }
    // A cache swap in flight fetches the EPG from its freshness check.
    if (!root.pendingFreshness) root.refreshEpg(true)
  }
  onMaxRecentsChanged: {
    var trimmed = Model.trimRecents(root.userState, root.maxRecents)
    if (trimmed !== root.userState) {
      root.userState = root.carrySources(trimmed)
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
