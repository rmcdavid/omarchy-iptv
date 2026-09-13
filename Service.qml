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
        root.runControl("play", ["play", "--id", key, "--socket", root.socketPath, "--cache-dir", root.cacheDir])
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

  function runPlaylistHelper() {
    if (root.playlistUrl === "" || playlistProc.running) return
    root.playlistAttempted = true
    root.playlistTimedOut = false
    playlistProc.command = ["python3", root.helperPath, "playlist", "--url", root.playlistUrl, "--cache-dir", root.cacheDir]
    playlistProc.running = true
    playlistWatchdog.restart()
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
      if (root.epgUrl === "") return
      root.epgAttempted = true
      epgProc.nowOnly = false
      epgProc.command = ["python3", root.helperPath, "epg", "--url", root.epgUrl, "--cache-dir", root.cacheDir]
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
      root.runControl("play", ["play", "--id", id, "--socket", root.socketPath, "--cache-dir", root.cacheDir])
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

  onPlaylistUrlChanged: {
    // A new source starts clean: the previous source's reason and host must
    // not stay on screen while its first fetch runs (UX 4.5, D-LIVE-10).
    root.playlistStatus = ({ ok: false, kind: "playlist", stale: false, error: null })
    root.playlistWarnings = []
    root.lastError = ""
    root.refreshPlaylist(true)
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
    // FileView write or mpv socket bind can need them (open risk 2), then
    // state.json itself with mode 0600 (stateInitProc, S-02).
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
      else root.runControl("play", ["play", "--id", id, "--socket", root.socketPath, "--cache-dir", root.cacheDir])
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
    command: ["mkdir", "-p", "-m", "700", root.cacheDir, root.stateDir, root.runtimeDir]
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
