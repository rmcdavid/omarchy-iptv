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
  readonly property int stopFallbackMs: 2000
  readonly property int focusRetryMs: 500
  readonly property int focusRetries: 6
  readonly property int healthFailuresBeforeRestart: 2

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

  // ---- data (read by Guide.qml / BarWidget.qml; never mutated by them)
  property var channels: []                 // Model.prepareChannels output
  property var channelIndex: ({})
  property var channelsMeta: ({})
  property var epgNow: ({})                 // tvg-id -> { now, next }
  property var epgMeta: ({})
  // Named userState: `state` would shadow QQuickItem.state.
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
  property string controlKind: ""
  property var mpvStderrTail: []
  property string lastError: ""
  property bool manualRefresh: false
  property bool manualEpgRefresh: false
  property bool playlistRerun: false
  property bool epgRerun: false
  property bool dirsReady: false
  property bool stateSavePending: false

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
      if (!keepOpen) root.focusPlayer()
      return true
    }
    var nowSec = Math.floor(Date.now() / 1000)
    root.userStopped = false
    root.relaunchPending = false
    root.relaunched = false
    root.healthFailures = 0
    root.lastError = ""
    root.failedAt = Model.withoutFailed(root.failedAt, key)
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
      if (controlProc.running) {
        // A zap burst: remember only the last target, applied when the
        // current helper call returns.
        root.pendingPlayId = key
      } else {
        root.runControl("play", ["play", "--id", key, "--socket", root.socketPath, "--cache-dir", root.cacheDir])
      }
      if (root.wantFocus) root.focusPlayer()
    } else {
      root.launchMpv(channel)
    }
    return true
  }

  // Ask mpv to quit over IPC; SIGTERM after stopFallbackMs if it ignores us.
  // A user stop never notifies.
  function stop() {
    root.pendingPlayId = ""
    root.wantFocus = false
    focusTimer.stop()
    if (!mpvProc.running) {
      root.nowPlaying = null
      return
    }
    root.userStopped = true
    root.relaunchPending = false
    if (!controlProc.running) root.runControl("stop", ["stop", "--socket", root.socketPath])
    stopFallbackTimer.restart()
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
  function refreshPlaylist(force) {
    if (!root.configured) return
    if (playlistProc.running) {
      if (force) root.playlistRerun = true
      return
    }
    refreshDebounce.restart()
  }

  function refreshEpg(force) {
    if (!root.epgConfigured) return
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
      source: root.sourceLabel,
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
      lastError: root.lastError
    }
  }

  // ------------------------------------------------------------ internals

  function applyChannels(text) {
    var parsed = Model.parseChannels(text)
    root.channels = parsed.ok ? Model.prepareChannels(parsed.channels) : []
    root.channelIndex = Model.indexById(root.channels)
    root.channelsMeta = parsed.meta
  }

  function applyUserState(text) {
    root.userState = Model.trimRecents(Model.parseState(text), root.maxRecents)
  }

  function saveState() {
    if (!root.dirsReady) {
      root.stateSavePending = true
      return
    }
    root.stateSavePending = false
    stateFile.setText(JSON.stringify(root.userState, null, 2) + "\n")
  }

  function applyPlaylistStatus(text) {
    root.playlistStatus = Model.parseHelperStatus(text, "playlist")
    if (root.playlistStatus.ok !== true) root.lastError = root.statusReason
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

  function runPlaylistHelper() {
    if (!root.configured || playlistProc.running) return
    root.playlistAttempted = true
    playlistProc.command = ["python3", root.helperPath, "playlist", "--url", root.playlistUrl, "--cache-dir", root.cacheDir]
    playlistProc.running = true
  }

  // `epg --url` fetches (the helper honours its own TTL, decision 5);
  // `epg --now-only` recomputes now/next from the cached window.
  function runEpgHelper(nowOnly) {
    if (epgProc.running) return
    if (nowOnly) {
      if (!root.epgLoaded) return
      epgProc.nowOnly = true
      epgProc.command = ["python3", root.helperPath, "epg", "--now-only", "--cache-dir", root.cacheDir]
    } else {
      if (!root.epgConfigured) return
      root.epgAttempted = true
      epgProc.nowOnly = false
      epgProc.command = ["python3", root.helperPath, "epg", "--url", root.epgUrl, "--cache-dir", root.cacheDir]
    }
    epgProc.running = true
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
        if (root.healthFailures >= root.healthFailuresBeforeRestart && mpvProc.running) {
          console.warn("omarchy-iptv: mpv unresponsive, restarting player")
          root.healthFailures = 0
          root.relaunchPending = !root.relaunched && root.nowPlaying !== null
          mpvProc.signal(15)
        }
      }
    } else if (kind === "play") {
      if (status.ok !== true && status.error) {
        var reason = Model.statusReason(status)
        root.lastError = reason
        console.warn("omarchy-iptv: play failed:", reason)
        if (String(status.error.code) === "not_running" && root.nowPlaying) {
          // mpv vanished between two zaps: start a fresh player.
          var channel = root.channelIndex[root.nowPlaying.id]
          if (channel && !mpvProc.running) root.launchMpv(channel)
        }
      }
    } else if (kind === "stop") {
      if (status.ok !== true && status.error && String(status.error.code) === "not_running" && !mpvProc.running) {
        root.nowPlaying = null
      }
    }
    // Apply the last queued zap of a burst.
    if (root.pendingPlayId !== "" && mpvProc.running) {
      var id = root.pendingPlayId
      root.pendingPlayId = ""
      root.runControl("play", ["play", "--id", id, "--socket", root.socketPath, "--cache-dir", root.cacheDir])
    } else {
      root.pendingPlayId = ""
    }
  }

  function launchMpv(channel) {
    var extra = Model.splitMpvArgs(root.mpvArgs)
    if (extra.rejected.length > 0) console.warn("omarchy-iptv: ignoring mpvArgs tokens:", extra.rejected.join(" "))
    root.mpvStderrTail = []
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
    var clean = Model.scrubUrls(String(line || "").replace(/\s+$/, ""))
    if (clean === "") return
    var tail = root.mpvStderrTail.slice()
    tail.push(clean)
    while (tail.length > 5) tail.shift()
    root.mpvStderrTail = tail
  }

  function handleMpvExit(exitCode, exitStatus) {
    stopFallbackTimer.stop()
    focusTimer.stop()
    var current = root.nowPlaying
    var stopped = root.userStopped
    var relaunch = root.relaunchPending
    root.userStopped = false
    root.relaunchPending = false
    root.pendingPlayId = ""
    if (relaunch && current && !stopped) {
      var channel = root.channelIndex[current.id]
      if (channel) {
        root.relaunched = true
        root.wantFocus = false
        root.launchMpv(channel)
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
    root.applyPlaylistStatus(text)
    // Deterministic reload; do not rely on inotify surviving the helper's
    // atomic rename (ARCHITECTURE.md, open risk 1).
    channelsFile.reload()
    playlistStatusFile.reload()
    var manual = root.manualRefresh
    root.manualRefresh = false
    var status = root.playlistStatus
    if (status.ok === true) {
      if (manual) root.notify("playlistRefreshed", { channelCount: status.channelCount, groupCount: status.groupCount })
    } else {
      root.notify("playlistError", { reason: root.statusReason, cachedAt: status.stale === true ? root.lastUpdated : "" })
    }
    if (root.playlistRerun) {
      root.playlistRerun = false
      refreshDebounce.restart()
    }
  }

  function handleEpgExit(text, nowOnly) {
    var status = Model.parseHelperStatus(text, "epg")
    if (!nowOnly) {
      root.epgStatus = status
      root.manualEpgRefresh = false
      if (status.ok !== true) root.notify("epgError", { reason: Model.statusReason(status) })
    }
    epgFile.reload()
    if (root.epgRerun) {
      root.epgRerun = false
      epgDebounce.restart()
    }
  }

  onPlaylistUrlChanged: root.refreshPlaylist(true)
  onEpgUrlChanged: {
    if (!root.epgConfigured) {
      root.epgLoaded = false
      root.epgAttempted = false
      root.epgNow = ({})
      root.epgStatus = ({ ok: false, kind: "epg", stale: false, error: null })
      return
    }
    root.refreshEpg(true)
  }
  onMaxRecentsChanged: {
    var trimmed = Model.trimRecents(root.userState, root.maxRecents)
    if (trimmed !== root.userState) {
      root.userState = trimmed
      root.saveState()
    }
  }

  Component.onCompleted: {
    // Argv-only. Creates the private cache/state/runtime dirs before any
    // FileView write or mpv socket bind can need them (open risk 2).
    mkdirProc.running = true
    whichProc.running = true
  }

  // ------------------------------------------------------------ files

  FileView {
    id: channelsFile
    path: root.cacheDir + "/channels.json"
    watchChanges: true
    printErrors: false
    onLoaded: root.applyChannels(text())
    onLoadFailed: root.applyChannels("")
    onFileChanged: reload()
  }

  FileView {
    id: playlistStatusFile
    path: root.cacheDir + "/playlist-status.json"
    watchChanges: true
    printErrors: false
    onLoaded: root.applyPlaylistStatus(text())
    onFileChanged: reload()
  }

  FileView {
    id: epgFile
    path: root.cacheDir + "/epg-now.json"
    watchChanges: true
    printErrors: false
    onLoaded: root.applyEpgNow(text())
    onLoadFailed: root.applyEpgNow("")
    onFileChanged: reload()
  }

  FileView {
    id: epgStatusFile
    path: root.cacheDir + "/epg-status.json"
    watchChanges: true
    printErrors: false
    onLoaded: {
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
    id: refreshTimer
    interval: root.refreshMinutes * 60 * 1000
    repeat: true
    running: root.configured
    triggeredOnStart: true
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
    // consecutive failures -> SIGTERM -> one automatic relaunch.
    id: healthTimer
    interval: root.healthCheckMs
    repeat: true
    running: mpvProc.running
    onTriggered: {
      if (controlProc.running || root.userStopped) return
      root.runControl("status", ["status", "--socket", root.socketPath])
    }
  }

  Timer {
    // If mpv ignores `quit` (hung), terminate it.
    id: stopFallbackTimer
    interval: root.stopFallbackMs
    repeat: false
    onTriggered: if (mpvProc.running) mpvProc.signal(15)
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

  Process {
    id: mkdirProc
    command: ["mkdir", "-p", "-m", "700", root.cacheDir, root.stateDir, root.runtimeDir]
    onExited: {
      root.dirsReady = true
      if (root.stateSavePending) root.saveState()
    }
  }

  Process {
    id: whichProc
    command: ["which", "mpv"]
    stdout: StdioCollector { waitForEnd: true }
    onExited: function(exitCode, exitStatus) { root.mpvAvailable = exitCode === 0 }
  }

  Process {
    id: playlistProc
    stdout: StdioCollector { id: playlistStdout; waitForEnd: true }
    stderr: StdioCollector {
      id: playlistStderr
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") console.warn("omarchy-iptv playlist:", Model.scrubUrls(text.trim()))
    }
    onExited: root.handlePlaylistExit(playlistStdout.text)
  }

  Process {
    id: epgProc
    property bool nowOnly: false
    stdout: StdioCollector { id: epgStdout; waitForEnd: true }
    stderr: StdioCollector {
      id: epgStderr
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") console.warn("omarchy-iptv epg:", Model.scrubUrls(text.trim()))
    }
    onExited: root.handleEpgExit(epgStdout.text, epgProc.nowOnly)
  }

  Process {
    id: controlProc
    stdout: StdioCollector { id: controlStdout; waitForEnd: true }
    stderr: StdioCollector { id: controlStderr; waitForEnd: true }
    onExited: root.handleControlResult(controlStdout.text)
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
    onExited: function(exitCode, exitStatus) { root.handleMpvExit(exitCode, exitStatus) }
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
