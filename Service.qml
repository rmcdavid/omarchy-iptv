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
//   - the single mpv Process and the now-playing state (decisions 1 and 2)
//   - the plugin IPC target       (omarchy-shell io.github.rmcdavid.iptv <fn>)
// Guide.qml receives this object as `service` (shell.qml injects it on load);
// BarWidget.qml resolves it through bar.shell.serviceFor(moduleName).
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
  readonly property string tvGlyph: "󰕧"

  // ---- settings (decision 7). shell.barConfig is refreshed by the host on
  // every shell.json change (shell.qml syncPluginApis), so these re-evaluate
  // after `omarchy bar set io.github.rmcdavid.iptv <key> <value>`.
  readonly property var settings: Model.findBarEntry(shell ? shell.barConfig : null, pluginId)
  readonly property string playlistUrl: String(Model.settingOf(settings, "playlistUrl", "")).trim()
  readonly property string epgUrl: String(Model.settingOf(settings, "epgUrl", "")).trim()
  readonly property int refreshMinutes: Model.clampInt(Model.settingOf(settings, "refreshMinutes", 60), 60, 5, 1440)
  readonly property string mpvArgs: String(Model.settingOf(settings, "mpvArgs", ""))
  readonly property int maxRecents: Model.clampInt(Model.settingOf(settings, "maxRecents", 10), 10, 1, 50)
  readonly property bool configured: playlistUrl !== ""

  // ---- data (read by Guide.qml / BarWidget.qml; never mutated by them)
  property var channels: []
  property var channelIndex: ({})
  property var channelsMeta: ({})
  property var epgNow: ({})
  // Named userState: `state` would shadow QQuickItem.state.
  property var userState: Model.emptyState()
  property var playlistStatus: ({ ok: false, kind: "playlist", stale: false, error: null })
  property var epgStatus: ({ ok: false, kind: "epg", stale: false, error: null })
  readonly property bool refreshing: playlistProc.running
  readonly property bool cacheLoaded: channels.length > 0

  // ---- playback
  property var nowPlaying: null            // { id, name, group, url, since }
  readonly property bool playing: mpvProc.running && nowPlaying !== null
  property bool userStopped: false
  property var mpvStderrTail: []
  property string lastError: ""

  // ------------------------------------------------------------ public API

  // Start (or switch to) a channel. First launch spawns the single mpv
  // Process; while it runs, zapping goes through the helper's IPC `play`.
  function play(channel) {
    if (!channel || !channel.url) return false
    var nowSec = Math.floor(Date.now() / 1000)
    root.userStopped = false
    root.lastError = ""
    root.nowPlaying = {
      id: Model.channelId(channel),
      name: String(channel.name || ""),
      group: String(channel.group || Model.UNGROUPED),
      url: String(channel.url),
      since: nowSec
    }
    root.userState = Model.recordPlayed(root.userState, channel, root.maxRecents, nowSec)
    root.saveState()
    if (mpvProc.running) {
      // TODO(FE): implement `play` in bin/omarchy-iptv (loadfile <url> replace
      // + set_property title/force-media-title + per-channel headers) and
      // queue a second zap while controlProc is still running.
      runControl(["play", "--id", root.nowPlaying.id, "--socket", root.socketPath, "--cache-dir", root.cacheDir])
    } else {
      launchMpv(channel)
    }
    return true
  }

  function playId(id) {
    var channel = root.channelIndex[String(id || "")]
    return channel ? root.play(channel) : false
  }

  // Ask mpv to quit. Exit code 0 after a user stop is silent (no notification).
  function stop() {
    if (!mpvProc.running) return
    root.userStopped = true
    // TODO(FE): implement `stop` in bin/omarchy-iptv (sends ["quit"]).
    runControl(["stop", "--socket", root.socketPath])
    stopFallbackTimer.restart()
  }

  // Bar scroll: previous/next channel inside the current channel's group
  // (Favorites/Recent are virtual groups resolved through state).
  function zap(delta) {
    if (!root.nowPlaying) return
    var list = Model.channelsInGroup(root.channels, root.nowPlaying.group, root.userState)
    var next = Model.nextInGroup(list, root.nowPlaying.id, delta)
    if (next) root.play(next)
  }

  function toggleFavorite(id) {
    root.userState = Model.withFavorites(root.userState, Model.toggleFavorite(root.userState.favorites, id))
    root.saveState()
  }

  // Debounced: settings changes, timers and the bar's middle click all funnel
  // through here so the helper never runs twice for one user action.
  function refreshPlaylist(force) {
    if (!root.configured) return
    if (playlistProc.running && !force) return
    refreshDebounce.restart()
  }

  function refreshEpg() {
    if (root.epgUrl === "" || epgProc.running) return
    // TODO(FE): implement `epg` in bin/omarchy-iptv; until then this records
    // a not_implemented status that Guide.qml may show as a hint.
    epgProc.command = ["python3", root.helperPath, "epg", "--url", root.epgUrl, "--cache-dir", root.cacheDir]
    epgProc.running = true
  }

  function notify(title, body, urgency) {
    Quickshell.execDetached(["omarchy-notification-send", "--app-name", "IPTV", "-u", urgency || "normal", "-g", root.tvGlyph, String(title), String(body || "")])
  }

  // ------------------------------------------------------------ internals

  function applyChannels(text) {
    var parsed = Model.parseChannels(text)
    root.channels = parsed.ok ? parsed.channels : []
    root.channelIndex = Model.indexById(root.channels)
    root.channelsMeta = parsed.meta
  }

  function applyUserState(text) {
    root.userState = Model.parseState(text)
  }

  function saveState() {
    stateFile.setText(JSON.stringify(root.userState, null, 2) + "\n")
  }

  function applyPlaylistStatus(text) {
    var status = Model.parseHelperStatus(text, "playlist")
    root.playlistStatus = status
    if (status.ok !== true && status.error) root.lastError = String(status.error.message || "")
  }

  function applyEpgNow(text) {
    var doc = Model.parseJsonObject(text)
    root.epgNow = doc && doc.channels && typeof doc.channels === "object" ? doc.channels : ({})
  }

  function runPlaylistHelper() {
    if (!root.configured || playlistProc.running) return
    playlistProc.command = ["python3", root.helperPath, "playlist", "--url", root.playlistUrl, "--cache-dir", root.cacheDir]
    playlistProc.running = true
  }

  function runControl(args) {
    if (controlProc.running) {
      console.warn("omarchy-iptv: control helper busy, dropping", args[0])
      return
    }
    controlProc.command = ["python3", root.helperPath].concat(args)
    controlProc.running = true
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
  }

  function rememberStderr(line) {
    var tail = root.mpvStderrTail.slice()
    tail.push(String(line || "").replace(/\s+$/, ""))
    while (tail.length > 5) tail.shift()
    root.mpvStderrTail = tail
  }

  onPlaylistUrlChanged: root.refreshPlaylist(true)
  onEpgUrlChanged: root.refreshEpg()

  Component.onCompleted: {
    // Argv-only. Creates the private cache/state/runtime dirs before any
    // FileView write or mpv socket bind can need them.
    mkdirProc.running = true
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
    interval: 300
    repeat: false
    onTriggered: root.runPlaylistHelper()
  }

  Timer {
    id: refreshTimer
    interval: root.refreshMinutes * 60 * 1000
    repeat: true
    running: root.configured
    triggeredOnStart: true
    onTriggered: root.refreshPlaylist(false)
  }

  Timer {
    // EPG now/next is recomputed from the cached programme window; the
    // helper only re-downloads when its own TTL expired (decision 5).
    id: epgTimer
    interval: 5 * 60 * 1000
    repeat: true
    running: root.epgUrl !== ""
    onTriggered: root.refreshEpg()
  }

  Timer {
    // TODO(FE): health check. Every tick while mpv runs, ask the helper for
    // `status`; two consecutive IPC failures -> mpvProc.signal(15), then one
    // automatic relaunch of nowPlaying (guard against loops).
    id: healthTimer
    interval: 10 * 1000
    repeat: true
    running: mpvProc.running
    onTriggered: {}
  }

  Timer {
    // If mpv ignores `quit` (hung), terminate it.
    id: stopFallbackTimer
    interval: 2000
    repeat: false
    onTriggered: if (mpvProc.running) mpvProc.signal(15)
  }

  // ------------------------------------------------------------ processes

  Process {
    id: mkdirProc
    command: ["mkdir", "-p", "-m", "700", root.cacheDir, root.stateDir, root.runtimeDir]
  }

  Process {
    id: playlistProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.applyPlaylistStatus(text)
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") console.warn("omarchy-iptv playlist:", text.trim())
    }
    onExited: {
      // Deterministic reload; do not rely on inotify surviving the helper's
      // atomic rename (ARCHITECTURE.md, open risks).
      channelsFile.reload()
      playlistStatusFile.reload()
    }
  }

  Process {
    id: epgProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.epgStatus = Model.parseHelperStatus(text, "epg")
    }
    onExited: epgFile.reload()
  }

  Process {
    id: controlProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var status = Model.parseHelperStatus(text, "control")
        if (status.ok !== true && status.error) {
          root.lastError = String(status.error.message || "")
          console.warn("omarchy-iptv control:", root.lastError)
        }
      }
    }
  }

  Process {
    // The one and only mpv instance (decision 2). Destroying this object
    // kills mpv, which is why the service is keepLoaded.
    id: mpvProc
    stderr: SplitParser {
      onRead: function(line) { root.rememberStderr(line) }
    }
    onExited: function(exitCode, exitStatus) {
      stopFallbackTimer.stop()
      var name = root.nowPlaying ? root.nowPlaying.name : ""
      var stopped = root.userStopped
      root.nowPlaying = null
      root.userStopped = false
      if (stopped || exitCode === 0) return
      // 2 = mpv could not play the file; 1/4 = init error / killed by signal.
      var detail = root.mpvStderrTail.length > 0 ? root.mpvStderrTail[root.mpvStderrTail.length - 1] : ("mpv exited with code " + exitCode)
      root.lastError = detail
      root.notify("Could not play " + (name || "channel"), detail, "critical")
    }
  }

  // omarchy-shell io.github.rmcdavid.iptv play <channelId> | stop | next | prev | refresh | status
  IpcHandler {
    target: root.pluginId

    function play(id: string): string { return root.playId(id) ? "ok" : "unknown" }
    function stop(): string { root.stop(); return "ok" }
    function next(): string { root.zap(1); return "ok" }
    function prev(): string { root.zap(-1); return "ok" }
    function refresh(): string { root.refreshPlaylist(true); return "ok" }
    function status(): string {
      return JSON.stringify({
        configured: root.configured,
        channels: root.channels.length,
        playing: root.playing,
        nowPlaying: root.nowPlaying,
        playlist: root.playlistStatus,
        lastError: root.lastError
      })
    }
  }
}
