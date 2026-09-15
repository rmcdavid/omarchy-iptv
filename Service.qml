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
  // Watchdog for one `play` or `status` helper run. `controlProc` was the
  // only one of the four Processes without one, and it is the one that holds
  // the single control slot: a helper that never exits blocks every later
  // zap and every health check for the rest of the session. Generous next to
  // a ~130 ms run and next to the helper's own --ipc-timeout, because this
  // is the belt and braces, not the deadline.
  readonly property int controlTimeoutMs: 8 * 1000
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
  // Model.settingsFrom carries the three M2-03 keys (7.1) alongside the seven
  // shipped ones, clamped through the same SETTING_RANGES ladder.
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
  // ---- channel numbers (M2-03 section 7, rulings CN2 and CN3). Read by
  // Guide.qml (numberEntryMs) and BarWidget.qml (barShowChannelNumber);
  // channelOrder re-derives root.channels through applyOrder().
  readonly property string channelOrder: settings.channelOrder
  readonly property int numberEntryMs: settings.numberEntryMs
  readonly property bool barShowChannelNumber: settings.barShowChannelNumber
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
  property var channels: []                 // Model.prepareChannels output, in the ACTIVE order
  property var channelIndex: ({})
  // Channel numbers (M2-03 1.4). Keyed by number, never by position, so it
  // survives a channelOrder flip untouched; its `byKey` / `order` entries are
  // indices into the PLAYLIST-order array, which is why channelByNumber()
  // resolves against preparedActive.channels and not root.channels.
  property var chnoIndex: Model.buildChnoIndex(null)
  // The prepared LRU entry root.channels was derived from, so flipping
  // channelOrder re-derives without re-parsing the cache (5.2). Not the LRU
  // head: an empty or failed load is never stored there.
  property var preparedActive: null
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
  // The playing channel's number label, "" when it has none or when it is not
  // in the active source's cache (3.3). Derived, not stored on `nowPlaying`:
  // four paths build that literal (a play, a re-scope, the player-stash
  // recovery, reconcileNowPlaying) and a number that is stale in one of them
  // is worse than no number at all. The loaded cache is the only authority.
  readonly property string nowPlayingChno: {
    if (!root.nowPlaying) return ""
    var channel = root.channelIndex[String(root.nowPlaying.id || "")]
    // Model.prepareChannels writes chnoLabel on every row at load time (1.3),
    // so this is a property read, not a parse.
    return channel ? String(channel.chnoLabel || "") : ""
  }
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
  // PO-3's record has been spent by this shell (marked, or the play's own
  // ending seen). One-way until the next play opens a new one: it is what
  // stops a state.json load - our own clear having not reached disk yet -
  // from putting a consumed record back and marking the same channel twice.
  property bool sessionConsumed: false
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
  // D-PLY-11. The health tick can finally see which channel the player is
  // on, so a label that has diverged from it is repaired by re-applying the
  // user's intent (ruling CL5). Bounded, and reset by every play(): a player
  // that will not take the channel must not be re-zapped once a tick for the
  // rest of the session - two attempts and then the divergence is reported
  // and left alone, which is still strictly better than never noticing.
  property int channelRepairs: 0
  readonly property int channelRepairMax: 2
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
  // `playSeq` as it stood when the probe in flight was ISSUED (4.10). A
  // probe answers about the world it was sent into; an intent issued after
  // it - a play from the guide, or over IPC one frame after the shell came
  // back - is the newer word and must not be overruled by the older answer.
  property int probeSeq: 0
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
  property var playlistLoadWarnings: []
  // PO-10 / D-PLY-5: the mpvArgs options that hand the stream address to
  // another program are kept (PO-5) but never kept quiet. This is not a
  // helper's warning list - it is derived from the setting itself, so it
  // appears the moment the option is in force and goes the moment it is
  // removed, with no play required to notice it.
  readonly property var playerArgWarnings: Model.labelWarnings(Model.splitMpvArgs(root.mpvArgs).warnings, "player")
  // What the guide's one warning line reads (Guide.qml warningText). The
  // player's line comes first: it is about where the user's credentials go,
  // and a playlist parse warning that outranked it would hide it for good on
  // any playlist that has one. Labelled entries carry their own wording, so
  // the guide needs no third list.
  readonly property var playlistWarnings: root.playerArgWarnings.concat(Model.asList(root.playlistLoadWarnings))
  // The same for the EPG helper's `warnings[]` (epg-status.json carries the
  // window's warnings on every successful run, `--now-only` included), shown
  // by the guide as `Guide data warning: ...` and cleared by the next clean
  // EPG load, by a cleared epgUrl and by a source swap.
  property var epgWarnings: []

  // ---- picture in picture (M2-05, docs/M2-05-PICTURE-IN-PICTURE.md)
  //
  // TWO GATE RESULTS SHAPE EVERYTHING BELOW, and both of them override the
  // design's own text (section 14, rulings PIP10 and PIP11):
  //
  //   PIP11. An exit code cannot detect failure here. `hyprctl dispatch`
  //   answers rc 0 `ok` for a dispatch aimed at an address that does not
  //   exist, and a real refusal arrives as `warning:` TEXT on stdout, also
  //   with rc 0 (QA-RESULTS D-PIP-2). rc is non-zero only for a Lua parse
  //   error - that is, only for a bug in our own string. So SUCCESS IS
  //   DEFINED IN EXACTLY ONE PLACE: pipVerify() compares a fresh read of
  //   `hyprctl -j clients` against what was asked for. Nothing in this file
  //   may branch on a dispatch's exit status or on its output. The stdout of
  //   a step is captured for the journal and for nothing else.
  //
  //   PIP10. The action argument is IGNORED: float and pin toggle
  //   unconditionally, and asking to UNSET one on a tiled window floats it. So
  //   no step is ever issued blind. Every round re-reads the compositor, the
  //   plan's conditionals are decided from that read, and a round that did
  //   not achieve the intent is re-planned from the state that now exists
  //   rather than repeated. That is also what makes a user's own SUPER+T or
  //   SUPER+O mid-sequence self-correcting instead of inverting.
  //
  // The state of record is the compositor, never a remembered boolean:
  // `pipOn` below is only ever written from a verified read. What the window
  // WAS before PiP is remembered in the player itself
  // (user-data/omarchy-iptv-pip), so it has exactly the window's lifetime
  // and survives both a channel change and `omarchy restart shell` (4.5).
  readonly property string pipClass: "omarchy-iptv"
  readonly property string pipTag: "iptv-pip"
  // The window-owning mpv pid, from `player probe` and from `player start`.
  // Addressing by class ALONE is a defect, not a shortcut: a user's own
  // `mpv --wayland-app-id=omarchy-iptv` reproduces as a second client
  // (QA-PLAYER PLY-RST-11), and floating, shrinking and pinning a stranger's
  // window is damage. 0 means "we do not know", and PiP refuses.
  property int playerPid: 0
  property bool pipAvailable: false          // hyprctl on PATH and a live instance signature (G-8)
  // "lua" or "legacy": WHICH SPELLING the compositor can parse, resolved once
  // from `hyprctl systeminfo`. Not a fallback ladder - under a Lua config
  // provider the legacy spelling is a Lua SYNTAX error (G-1), so "try the
  // other one on failure" is a second guaranteed failure, and rc could not
  // tell us to try anyway (PIP11). One selection, made from the host's own
  // answer, verified like everything else by reading the state back.
  property string pipProvider: ""
  property bool pipOn: false                 // VERIFIED, never intended
  property string pipMode: ""                // the request in flight: on | off | toggle ("" = idle)
  property string pipIntent: ""              // what that resolved to against the live state
  property string pipPhase: ""               // resolve | monitors | dispatch | verify
  property int pipRound: 0
  property var pipQueue: []                  // argv vectors left in this round
  property var pipGeom: null                 // { x, y, w, h } asked for
  property var pipLive: null                 // last pipFindWindow() result
  property var pipSnapshot: null             // what the window was before PiP (from the player)
  property string pipReason: ""              // last failure code, "" after a success
  readonly property bool pipBusy: root.pipMode !== ""
  // Bounds (CLAUDE.md "Working in parallel" 3). At most 3 rounds of at most
  // 8 steps, each step and each read watched for 2 s, and the whole sequence
  // capped so `pipBusy` can never latch.
  readonly property int pipMaxRounds: 3
  readonly property int pipMaxSteps: 8
  readonly property int pipStepMs: 2 * 1000
  readonly property int pipSequenceMs: 15 * 1000
  // mpv request ids: 1 and 2 are the two subscriptions onPlayerAttached
  // already makes. 3 reads our snapshot back after a shell restart (4.5).
  readonly property int pipSnapshotRequestId: 3
  // And 4 asks the player for its own pid. G-2 proved mpv's `pid` property
  // is the pid Hyprland reports for the window, with no wrapper process in
  // between; the helper resolves it the same way (bin/omarchy-iptv:3029).
  // Taken over the player's own private socket rather than out of a helper
  // reply, because that one connection covers all three ways a player
  // becomes ours - a cold start, a respawn, and a reattach after
  // `omarchy restart shell` - through a single seam.
  readonly property int pipPidRequestId: 4

  // The outcome of one PiP sequence, once it has been VERIFIED against the
  // compositor: { ok, requested, state: "on"|"off", error: { code } }. The
  // guide turns the code into its footer line (copy lives in lane V1); this
  // service never emits a user-facing sentence.
  signal pipOutcome(var result)

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
    // A false negative here costs one redundant `player start`, which adopts
    // the live player and re-zaps it (4.7). It is cheap, not free: an
    // adopting start re-applies its own channel over anything that landed
    // while it was adopting, and nothing orders the two (D-PLY-11 T-A, and
    // ruling CL4 withholds the instrument that would). That ordering has
    // never been observed to fire - 0 in 30 live bursts - but "only costs"
    // overstated what is known and it is corrected here.
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
    root.sessionConsumed = false        // a new record, not the spent one
    // A PO-3 mark owed from before this play was about the record this play
    // has just replaced. Leaving it owed would land it on the channel now
    // starting, which is the opposite of what PO-3 is for.
    root.deadSessionPending = false
    root.saveState()
    root.wantFocus = !keepOpen
    root.channelRepairs = 0             // a new intent, a fresh repair budget
    // The fork (Model.playFork). `player start` is idempotent - it adopts a
    // live player and zaps it - so a wrong answer costs one extra ~130 ms
    // helper run. It was recorded here that the fork is "never a correctness
    // gate"; that was asserted, never measured, and it is now known to be
    // too strong. `playerPending` makes `playerUp` true synchronously, so
    // every call after the first in a COLD burst takes the zap branch and
    // aims at a socket mpv has not bound yet; wave two measured what happens
    // when one of those lands and the cold start then applies its own
    // channel over it - ten user-visible divergences in twenty cold bursts.
    // The fork stays as it is (a zap aimed at a socket that is about to
    // exist is how a burst stays responsive, and ruling CL4 withholds the
    // instrument that would order the two slots); what was fixed is the far
    // end, where the start now stands down instead of overwriting, and this
    // shell re-applies its intent when the two disagree.
    //
    // While `stopping` is true we always take the start branch, so a zap can
    // never be written to a socket that is being torn down (4.10).
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
  // the one the player was started with (4.6, requirement 11). The rule is
  // Model.zapArgs (CLAUDE.md 12) - it was the one argv builder still spelled
  // here, and the decision it makes reaches all the way into the helper.
  function playArgs(key) {
    return Model.zapArgs(root.socketPath, root.activeCacheDir, key, root.nowPlaying)
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
    root.channelRepairs = 0
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

  // The channel a typed number resolves to, or null (M2-03 3.2). Exact match
  // first, else the lowest number that starts with it; NO duplicate cycling,
  // because a script asking for 12 must get the same channel every time.
  //
  // Resolved against the playlist-order array the index was built from, never
  // against root.channels: with channelOrder "number" those two disagree on
  // every position (5.2).
  function channelByNumber(text) {
    var base = root.preparedActive ? root.preparedActive.channels : root.channels
    return Model.channelByNumber(base, root.chnoIndex, text)
  }

  // The `channel` IPC verb's answer, as an object so the harness drives the
  // same path the CLI does instead of a copy of it (CLAUDE.md rule 12).
  //
  // Rulings CN1 and CN10: inside the guide digits only move the cursor, but
  // out here there is no cursor and no one browsing - somebody bound a key to
  // this, so it TUNES. It is play(id, true, "") exactly as the `play` verb
  // calls it, so the zap ring falls back to the channel's own group.
  // URL-free by construction: an id, a number, a name and a code.
  function tuneByNumber(text) {
    var asked = Model.sanitizeInput(String(text === undefined || text === null ? "" : text), Model.MAX_CHNO_LABEL)
    var found = root.channelByNumber(text)
    if (!found) {
      return { ok: false, kind: "channel",
               error: { code: "unknown_chno", message: "no channel " + asked } }
    }
    var id = Model.channelId(found)
    var label = String(found.chnoLabel || "")
    var name = String(found.name || "")
    // play() refuses when mpv is missing or the entry has no URL. Reporting
    // that as ok:true would be a lie about the one thing this verb exists to
    // do; the success shape is unchanged for the case it describes.
    if (!root.play(id, true, "")) {
      return { ok: false, kind: "channel", id: id, chno: label, name: name,
               error: { code: "play_failed", message: "could not start channel " + asked } }
    }
    return { ok: true, kind: "channel", id: id, chno: label, name: name }
  }

  function focusPlayer() {
    Quickshell.execDetached(Model.focusPlayerArgv())
  }

  // ------------------------------------------------------------ picture in picture (M2-05)

  // The guide's `p` key (design section 5). Same answer shape as the IPC
  // verb, so both surfaces refuse for the same reasons in the same words.
  function togglePip() {
    return root.requestPip("toggle")
  }

  // The one entry point. Returns SYNCHRONOUSLY with what is knowable
  // synchronously - whether the request was accepted, and why not if it was
  // refused - and never with a claim of success: success is a fact about the
  // compositor that only a readback can establish (PIP11), and that readback
  // is two process round-trips away. The verified outcome arrives on
  // pipOutcome() and is readable in `status`.
  function requestPip(mode) {
    var want = String(mode || "").toLowerCase()
    if (want !== "on" && want !== "off" && want !== "toggle")
      return { ok: false, kind: "pip", requested: want, error: { code: "bad_mode" } }
    if (!root.pipAvailable)
      return { ok: false, kind: "pip", requested: want, error: { code: "no_compositor" } }
    // PiP never starts a player (design 4.10). "Nothing playing" covers both
    // no player and a player whose pid we do not know, because addressing by
    // class alone is the one thing this feature must not do.
    if (!root.playing || root.playerPid <= 0)
      return { ok: false, kind: "pip", requested: want, error: { code: "nothing_playing" } }
    if (root.pipBusy)
      return { ok: false, kind: "pip", requested: want, error: { code: "busy" } }
    root.pipMode = want
    root.pipIntent = ""
    root.pipRound = 0
    root.pipQueue = []
    root.pipGeom = null
    root.pipLive = null
    root.pipReason = ""
    root.pipPhase = "resolve"
    pipSequenceWatchdog.restart()
    root.pipReadClients()
    return { ok: true, kind: "pip", requested: want, was: root.pipOn, state: "applying" }
  }

  // Every phase begins here. The read is the same read the verification uses,
  // which is the point: there is one way to learn what the window is.
  function pipReadClients() {
    if (hyprClientsProc.running) return
    hyprClientsProc.running = true
    pipStepWatchdog.restart()
  }

  function pipReadMonitors() {
    if (hyprMonitorsProc.running) return
    hyprMonitorsProc.running = true
    pipStepWatchdog.restart()
  }

  // `hyprctl -j clients` came back. One function, three phases, because all
  // three want exactly the same thing: the truth about our window, right now.
  function pipApplyClients(text) {
    pipStepWatchdog.stop()
    if (!root.pipBusy) return
    var live = root.pipFindWindow(text, root.playerPid, root.pipClass)
    if (!live.ok) {
      // Garbage, no match, or more than one match. Never act on a guess.
      root.pipFinish(false, String(live.reason || "no_window"))
      return
    }
    root.pipLive = live
    if (root.pipPhase === "resolve") {
      // The answer to "am I in PiP?" is read out of the compositor, not out
      // of a boolean this shell may not even have been alive to set (4.7).
      root.pipOn = root.pipIsOn(live)
      root.pipIntent = root.pipMode === "toggle" ? (root.pipOn ? "off" : "on") : root.pipMode
      if (root.pipIntent === "on") {
        // What the window WAS. Written to the player before the first
        // dispatch, so a shell that dies mid-sequence still leaves something
        // that knows how to put the window back. NOT rewritten when PiP is
        // already on: `pip on` twice must not overwrite the restore point
        // with the PiP box's own rectangle.
        if (!root.pipOn) root.pipWriteMpv("on", root.pipSnapshotFrom(live))
        root.pipPhase = "monitors"
        root.pipReadMonitors()
        return
      }
      // The tag is what says "we did this to this window" (design 4.8). A
      // window the user floated and pinned themselves with SUPER+O carries
      // none, so `pip off` has nothing of ours to undo and must not drag it
      // back to a rectangle out of a stale snapshot - or, worse, resize a
      // TILED window, which changes the split ratio of the user's layout.
      if (!root.pipHasOurTag(live)) {
        root.pipSnapshot = null
        root.pipOn = false
        root.pipFinish(true, "")
        return
      }
      root.pipPhase = "dispatch"
      root.pipPlanRound()
      return
    }
    if (root.pipPhase === "verify") {
      root.pipCheck(live)
      return
    }
    root.pipPlanRound()
  }

  function pipApplyMonitors(text) {
    pipStepWatchdog.stop()
    if (!root.pipBusy) return
    var live = root.pipLive
    var monitor = root.pipFindMonitor(text, live ? live.monitor : -1)
    var geom = monitor ? root.pipGeometry(monitor, root.pipOptions(root.pipConfig())) : null
    if (!geom) {
      root.pipFinish(false, "no_monitor")
      return
    }
    root.pipGeom = geom
    // Read the windows again rather than planning against the read the
    // monitor lookup was entered on. It costs one more process on the way in
    // and it is what makes "decided from a fresh read" literally true of
    // every conditional step, rather than true to within a round trip
    // (PIP10).
    root.pipPhase = "dispatch"
    root.pipReadClients()
  }

  // One round: decide from the read we are holding, then run what it decided.
  // `pipLive` here is at most a few milliseconds old - it is the read this
  // round was entered on - which is what "read the live state and act
  // conditionally" means in a process-driven engine (PIP10).
  function pipPlanRound() {
    // Counted here, unconditionally, because this is also the termination
    // proof: at most pipMaxRounds passes, and a re-plan that has nothing
    // left to try stops instead of asking the compositor the same question
    // for ever.
    root.pipRound += 1
    var plan = root.pipPlan(root.pipLive, root.pipSnapshot, root.pipGeom, root.pipIntent)
    if (!plan || plan.length === 0) {
      if (root.pipRound > 1) {
        root.pipOn = root.pipIsOn(root.pipLive)
        root.pipFinish(false, "dispatch_failed")
        return
      }
      // First pass with nothing to do: the window may already be exactly
      // right. Verify anyway - the compositor, not an empty plan, is what
      // decides whether we are done (PIP11).
      root.pipPhase = "verify"
      root.pipReadClients()
      return
    }
    if (plan.length > root.pipMaxSteps) plan = plan.slice(0, root.pipMaxSteps)
    root.pipQueue = plan
    root.pipRunNextStep()
  }

  function pipRunNextStep() {
    if (!root.pipBusy) return
    var queue = root.pipQueue
    if (!queue || queue.length === 0) {
      root.pipPhase = "verify"
      root.pipReadClients()
      return
    }
    var argv = queue[0]
    root.pipQueue = queue.slice(1)
    if (!argv || argv.length < 3) {
      // A builder refused to produce a vector (a value that did not match the
      // address regex or the integer range, 4.11 / PIP7). Refusing is the
      // correct outcome; carrying on past it is not.
      root.pipFinish(false, "bad_step")
      return
    }
    hyprDispatchProc.command = argv
    hyprDispatchProc.running = true
    pipStepWatchdog.restart()
  }

  // PIP11 in one function: the exit code and the text are diagnostics, never
  // a verdict. `hyprctl` says `ok` for a dispatch that did nothing at all, so
  // the only thing this does is move to the next step.
  function pipNoteStep(text, exitCode) {
    pipStepWatchdog.stop()
    if (!root.pipBusy) return
    var line = String(text || "").trim()
    if (line !== "" && /(^|\n)\s*(error|warning):/i.test(line)) {
      // Redacted like every other process output, though by construction a
      // dispatch vector holds an address, integers and constants and nothing
      // a provider or the user controls (4.11).
      console.warn("omarchy-iptv pip:", Model.redactUrls(line.split("\n")[0]))
    }
    if (exitCode !== 0) {
      // Non-zero means a Lua parse or nil-call error, i.e. a bug in OUR
      // string, never a refused effect. Worth one line; the verdict is still
      // the readback below.
      console.warn("omarchy-iptv pip: the compositor could not parse a dispatch (rc " + exitCode + ")")
    }
    root.pipRunNextStep()
  }

  // The single definition of success in this feature.
  function pipCheck(live) {
    var verdict = root.pipVerify(live, root.pipSnapshot, root.pipGeom, root.pipIntent)
    if (verdict.ok) {
      root.pipOn = root.pipIntent === "on"
      root.pipFinish(true, "")
      return
    }
    if (root.pipRound >= root.pipMaxRounds) {
      // Stop, leave the window as it is, and say so. A half-applied PiP is
      // visible, and the next `p` reads this same live state and either
      // finishes it or undoes it (design 4.10).
      root.pipOn = root.pipIsOn(live)
      console.warn("omarchy-iptv pip: the window did not reach the requested state ("
                   + String(verdict.mismatch || []).substring(0, 120) + ")")
      root.pipFinish(false, "dispatch_failed")
      return
    }
    // Re-plan from what is true NOW, rather than repeating what was planned
    // against what was true then. This is the branch that absorbs a user's
    // own SUPER+T or SUPER+O landing in the middle of our sequence.
    root.pipPhase = "dispatch"
    root.pipPlanRound()
  }

  function pipFinish(ok, code) {
    pipSequenceWatchdog.stop()
    pipStepWatchdog.stop()
    var requested = root.pipMode
    var intent = root.pipIntent
    // The player's record of what the window was is retired only once the
    // window is verifiably back, and the user's own auto-window-resize goes
    // back with it. On a FAILED exit both are kept: the window is still in
    // the corner, so the record still describes something true, and the next
    // `p` reads the live state and finishes or undoes the half-applied
    // sequence using that same snapshot.
    if (ok && intent === "off") {
      root.pipWriteMpv("off", null)
      root.pipSnapshot = null
    }
    root.pipReason = ok ? "" : String(code || "")
    root.pipMode = ""
    root.pipIntent = ""
    root.pipPhase = ""
    root.pipQueue = []
    root.pipRound = 0
    var result = { ok: ok, kind: "pip", requested: requested,
                   state: root.pipOn ? "on" : "off" }
    if (!ok) result.error = { code: root.pipReason, intent: intent }
    root.pipOutcome(result)
  }

  // The player is gone, so the window it owned is gone, and with it every
  // piece of state this feature has (PIP3: PiP does not survive stop and
  // replay - press the key again).
  function pipReset() {
    pipSequenceWatchdog.stop()
    pipStepWatchdog.stop()
    root.playerPid = 0
    root.pipOn = false
    root.pipMode = ""
    root.pipIntent = ""
    root.pipPhase = ""
    root.pipQueue = []
    root.pipGeom = null
    root.pipLive = null
    root.pipSnapshot = null
  }

  // `player probe` and `player start` both report the mpv pid; G-2 proved it
  // is the pid Hyprland reports for the window, with no wrapper in between.
  function notePlayerPid(value) {
    var pid = Math.floor(Number(value) || 0)
    if (pid <= 0 || pid === root.playerPid) return
    root.playerPid = pid
  }

  // The two mpv-side writes (4.6). Both go over the socket the service
  // already holds; a dead socket answers false and that is recorded, never
  // fatal - the compositor half is what PiP actually is.
  function pipWriteMpv(intent, snapshot) {
    // Kept in memory too, so an exit in the same session does not depend on
    // a round trip; the player's copy is what survives a shell restart. Set
    // BEFORE the write, because the write can fail and the compositor half
    // still applies - the snapshot must describe what we are about to do
    // either way. The "off" case does NOT clear it here: pipPlan and
    // pipVerify are both still to read it; pipFinish clears it.
    if (intent === "on") root.pipSnapshot = snapshot
    var sock = root.playerSocket
    if (!root.socketAttached()) return false
    var commands = root.pipMpvCommands(intent, snapshot, root.mpvArgs)
    for (var i = 0; i < commands.length; i++) root.socketWrite(sock, commands[i], 0)
    if (sock.flush) sock.flush()
    return true
  }

  // Does this window carry the tag we dispatch? It is the marker that says
  // the plugin put this window where it is, and the difference between a
  // window `p` should EXIT and a window the user floated themselves, which
  // `p` should ENTER (design 4.8).
  function pipHasOurTag(live) {
    var tags = live && live.tags ? live.tags : []
    for (var i = 0; i < tags.length; i++) if (String(tags[i]) === root.pipTag) return true
    return false
  }

  // Read the snapshot back out of the surviving player. Needed in exactly one
  // case - the shell restarted while in PiP and the user then exits - so it
  // is one get_property issued from onPlayerAttached, and a failure degrades
  // to "unpin and unfloat", never to stuck (4.5, 4.7).
  function pipRequestSnapshot(sock) {
    root.socketWrite(sock, ["get_property", "user-data/omarchy-iptv-pip"], root.pipSnapshotRequestId)
    root.socketWrite(sock, ["get_property", "pid"], root.pipPidRequestId)
  }

  // Our own replies on the player socket, routed by request id. Returns true
  // when the line was ours, so the event router never sees it.
  function pipNoteReply(line) {
    var reply = root.parsePlayerReply(line)
    if (!reply) return false
    if (reply.requestId === root.pipSnapshotRequestId) {
      root.pipSnapshot = reply.ok ? root.pipReadSnapshot(reply.data) : null
      return true
    }
    if (reply.requestId !== root.pipPidRequestId) return false
    if (reply.ok) root.notePlayerPid(reply.data)
    return true
  }

  // The settings entry the guide and the service both read (design section
  // 6). Read from the bar entry rather than from `settings`, because
  // `pipOptions` is the clamp for these three keys and running a value
  // through two different clamps is how they drift apart.
  function pipConfig() {
    return Model.findBarEntry(root.shell ? root.shell.barConfig : null, root.pluginId) || ({})
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

  // `nowPlaying` as the IPC reports it: the shipped literal plus the playing
  // channel's number (3.3). Null when nothing plays, exactly like the property.
  function nowPlayingSummary() {
    var np = root.nowPlaying
    if (!np) return null
    return { id: np.id, name: np.name, group: np.group, chno: root.nowPlayingChno,
             launchedFrom: np.launchedFrom, since: np.since }
  }

  // JSON summary for the IPC `status` verb; URL-free by construction.
  function statusSummary() {
    return {
      configured: root.configured,
      sourceHost: root.sourceHost,
      status: root.status,
      channels: root.channels.length,
      groups: Model.groupChannels(root.channels).length,
      // So a script can tell "this playlist is not numbered" from "you asked
      // for a number that does not exist" (3.3).
      hasNumbers: root.chnoIndex.hasNumbers === true,
      channelOrder: root.channelOrder,
      lastUpdated: root.lastUpdated,
      playing: root.playing,
      nowPlaying: root.nowPlayingSummary(),
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
      // M2-05. `on` is the last VERIFIED read of the compositor, never an
      // intent: a script that asks whether picture in picture is on gets the
      // same answer the feature itself acts on (PIP11).
      pip: {
        available: root.pipAvailable,
        on: root.pipOn,
        applying: root.pipBusy,
        reason: root.pipReason
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
      prepared = { text: text, channels: channels, channelIndex: Model.indexById(channels),
                   chnoIndex: Model.buildChnoIndex(channels), channelsMeta: parsed.meta }
    }
    if (text !== "" && prepared.channels.length > 0) {
      var next = [prepared]
      for (var k = 0; k < lru.length && next.length < root.preparedLruSize; k++) if (lru[k] !== prepared) next.push(lru[k])
      root.preparedLru = next
    }
    var t1 = Date.now()
    // The LRU entry always holds PLAYLIST order; the display order is derived
    // from it here and again whenever channelOrder changes (5.2), so a flip
    // costs one O(n) gather and no helper run.
    root.preparedActive = prepared
    root.channels = Model.orderChannels(prepared.channels, root.channelOrder, prepared.chnoIndex)
    root.channelIndex = prepared.channelIndex
    root.chnoIndex = prepared.chnoIndex
    root.channelsMeta = prepared.channelsMeta
    root.switchParseMs = t1 - t0
    root.switchAssignMs = Date.now() - t1
    // A now-playing recovered from the player's stash resolves against the
    // cache the moment it lands (4.5); until then it is name-only.
    root.reconcileNowPlaying()
  }

  // Re-derive root.channels from the prepared (playlist-order) array when
  // channelOrder changes at runtime (5.2). Favorites and Recents keep their
  // own orders: they are lists the user built, not the provider (CN4).
  function applyOrder() {
    if (!root.preparedActive) return
    root.channels = Model.orderChannels(root.preparedActive.channels, root.channelOrder,
                                        root.preparedActive.chnoIndex)
  }

  onChannelOrderChanged: root.applyOrder()

  // state.json -> userState (v1 files migrate in memory, section 2.2), then
  // the startup sequence of section 4.4: reconcile the settings into the
  // history and run the one-time cache migration. A reload caused by one
  // of this service's own writes is skipped: the in-memory state is newer
  // than what an earlier atomic write may still be delivering (R10).
  function applyUserState(text) {
    if (root.stateLoaded && root.recentSaves.indexOf(text) !== -1) return
    // Section 15's race: what arrives is a snapshot of the file from before
    // this shell wrote anything, so it is a base to merge onto, not a
    // replacement. Model.stateOnLoad() replays the play this shell recorded
    // while the read was in flight and refuses to resurrect a record already
    // consumed; both answers are the one rule, so neither is decided here.
    var adopted = Model.stateOnLoad(Model.trimRecents(Model.parseState(text), root.maxRecents),
                                    root.userState,
                                    { loadedBefore: root.stateLoaded, savePending: root.stateSavePending,
                                      maxRecents: root.maxRecents })
    root.userState = adopted.state
    root.stateLoaded = true
    var merged = root.userState
    // The file can carry a record this shell has already spent, because our
    // own clear may not have reached disk yet. That answer belongs to the
    // same decision as every other ending, not to a condition here.
    root.noteSessionOutcome("loaded")
    // The merged state exists only in memory until it is written; a shell
    // that dies before that is exactly the case PO-3 needs the record for.
    // noteSessionOutcome() has already written if it changed anything.
    if (adopted.write && root.userState === merged) root.saveState()
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
      root.playlistLoadWarnings = Model.statusWarnings(root.playlistStatus)
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
    controlWatchdog.restart()
    return true
  }

  function handleControlResult(text) {
    controlWatchdog.stop()
    var kind = root.controlKind
    root.controlKind = ""
    var status = Model.parseHelperStatus(text, kind)
    if (kind === "status") {
      var code = status.error ? String(status.error.code) : ""
      if (Model.statusHealthy(status)) {
        root.healthFailures = 0
        root.checkPlayerChannel(status)
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
        var verdict = Model.playFailureVerdict(status.error.code, {
          playerUp: root.playerUp,
          nowPlaying: root.nowPlaying !== null,
          userStopped: root.userStopped,
          retriesLeft: root.playRetries < root.playRetryMax
        })
        if (verdict === "start") {
          // The player vanished between two zaps. The `not_running` /
          // `still there` disambiguation collapses (4.7): `player start`
          // adopts a live player and spawns a dead one, so the same call is
          // right either way.
          root.lastError = reason
          var channel = root.channelIndex[root.nowPlaying.id]
          if (channel) root.startPlayer(channel)
        } else if (verdict === "retry") {
          // mpv did not answer in time, or something held the lock: retry
          // with backoff instead of losing the zap (D-LIVE-15).
          root.playRetries += 1
          playRetryTimer.interval = root.playRetryBaseMs * root.playRetries
          playRetryTimer.restart()
        } else if (verdict === "unknown") {
          // A reply we could not read, or one that never reached the player
          // at all. The status branch above has had this guard from the
          // start; the play branch fell into the rollback instead, which
          // WRITES nowPlaying with no load to match it - and then drains the
          // burst's last intent unconditionally two lines later.
          root.lastError = reason
          console.warn("omarchy-iptv: could not tell whether the channel changed:", reason)
        } else {
          root.lastError = reason
          console.warn("omarchy-iptv: play failed:", reason)
          // The switch did not happen; mpv still plays the previous channel.
          if (root.playerUp && root.previousPlaying) root.nowPlaying = root.previousPlaying
        }
      } else if (status.ok === true) {
        root.playRetries = 0
        root.previousPlaying = null
        // The zap's own entry id AND the zap's own channel, so a failure
        // that arrives after the next zap still names this one (4.8). Taking
        // the owner from nowPlaying recorded whichever intent happened to be
        // current when the REPLY landed - exactly the case the ring exists
        // for, and why the "Stream failed" toast could name a channel that
        // never failed.
        root.rememberEntry(status.entryId, Model.replyTarget(status, root.nowPlaying))
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

  // Ruling CL5's repair, and the only one allowed: the shell holds the
  // user's intent, so when the player is on a different channel the fix is
  // to send the intent again. Relabelling nowPlaying from the player would
  // turn a visible reporting bug into a silent wrong channel - the user
  // watching something they did not choose, with the interface agreeing.
  function reapplyIntent(id) {
    var key = String(id || "")
    if (key === "" || root.stopping || root.userStopped) return false
    if (!root.nowPlaying || String(root.nowPlaying.id) !== key) return false
    if (!root.playerUp) return false
    if (controlProc.running) {
      root.pendingPlayId = key
      return true
    }
    return root.runControl("play", root.playArgs(key))
  }

  // D-PLY-11's detection half. `status` now carries the player's own
  // now-playing record (4.6), so the health tick asks the one question it
  // never asked: which channel. Every divergence wave two produced was still
  // there two health ticks later, because nothing looked and nothing
  // corrected it. Under ruling CL6 the contract is that the label and the
  // player agree WITHIN ONE HEALTH TICK, which is exactly this.
  function checkPlayerChannel(status) {
    if (root.stopping || root.userStopped || !root.nowPlaying) return "unknown"
    var verdict = Model.reconcileVerdict(status.stash, root.nowPlaying, root.activeSourceKey)
    if (verdict.state === "agree") root.channelRepairs = 0
    if (verdict.state !== "diverged") return verdict.state
    if (root.channelRepairs >= root.channelRepairMax) return "diverged"
    root.channelRepairs += 1
    console.warn("omarchy-iptv: the player is not on the channel the guide names; re-applying it")
    root.reapplyIntent(verdict.repair)
    return "diverged"
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
    root.probeSeq = root.playSeq
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
      // A start or a restart that answered ok IS the relaunch, delivered.
      // Leaving the queue armed is how the health path fired a SECOND
      // `player restart --from term` at the player it had just respawned,
      // one tick after the observer reattached (the timer's `playerUp`
      // branch reads a healthy new player as "still not answering").
      relaunchTimer.stop()
      root.playRetries = 0
      // The reply's own channel, not whatever is current now: a start that
      // stood down left a DIFFERENT channel on the player, and that entry id
      // belongs to that channel.
      root.rememberEntry(status.entryId, Model.replyTarget(status, root.nowPlaying))
      // D-PLY-11, ruling CL5. The helper says which channel it left on the
      // player. During a cold burst that can be the burst's FIRST intent
      // while the shell is holding the eighth - measured 10 times in 20 - or
      // a newer one this start stood down for. Either way the shell is
      // authoritative: if the player is not on the channel the user asked
      // for, send the intent again rather than relabel the interface.
      var repair = Model.sessionIntentRepair(status, root.nowPlaying)
      if (repair !== "") {
        console.log("omarchy-iptv: the player start settled on another channel; re-applying the intent")
        root.reapplyIntent(repair)
      }
      // The helper has just reported a live player of this shell's making,
      // so the observer belongs on it. Doing nothing here is the second
      // half of the reported P1: `wanted` false leaves the 250 ms retry
      // timer off, and nothing else ever looks again.
      var follow = Model.playerSessionFollowUp({
        attached: root.socketAttached(),
        stopping: root.stopping,
        userStopped: root.userStopped,
        nowPlaying: root.nowPlaying !== null
      })
      if (follow === "attached" || follow === "abandoned") {
        // Already observed, or a stop really did overtake this start - the
        // two legitimately interleave, because the helper releases the lock
        // before its first-load window precisely so a stop ladder can get
        // in. Do not hunt for a socket that is being torn down; that would
        // be twelve journal lines for a player nobody wants any more.
        root.playerPending = false
      } else {
        // The player is up but the observer has not attached yet: keep the
        // birth edge rather than blinking the bar to idle, bounded by the
        // watchdog, and keep hunting for the socket.
        root.playerWanted = true
        root.armPlayerSocket()
        playerWatchdog.restart()
        // `recover`: a live player and no idea what it is playing. Read the
        // identity back out of its own stash, which is the reattach path of
        // 4.5 unchanged - the same answer a shell restart gets.
        if (follow === "recover") root.runPlayerProbe()
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
    // Ordering survives the restart, and an intent issued after this probe
    // went out is the newer word (4.10, section 15). Both answers come from
    // the one call because the resync moves the counter the other is
    // measured against.
    var verdict = Model.probeVerdict(probe.seq, root.probeSeq, root.playSeq)
    root.playSeq = verdict.seq
    if (verdict.stale) {
      // Everything below is about a world the user has since moved on from;
      // the play they issued owns the outcome, and drainPendingPlay() is
      // about to deliver it.
      root.probeRetried = false
      return
    }
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
    // M2-05: the reattach path learns the window-owning pid too, so PiP
    // works on a player this shell did not start (4.7).
    root.notePlayerPid(probe.pid)
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
    // Only when the observer is not on it yet: raising the birth edge over a
    // live socket buys nothing and ends in the watchdog's "did not become
    // observable" twelve seconds later.
    root.playerPending = !root.socketAttached()
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
    // The mark is raised, so the record is spent. Retiring it goes through
    // the same decision as every other ending rather than being written
    // here: that is what makes the clear stick when the write loses its
    // race with state.json's own load.
    root.noteSessionOutcome("marked")
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
    var verdict = Model.sessionAfterOutcome(root.userState, outcome, root.deadSessionPending,
                                            root.sessionConsumed)
    root.deadSessionPending = verdict.pending
    root.sessionConsumed = verdict.consumed
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
    // M2-05 4.5. One more read on the same connection: what the window was
    // before PiP, out of the player that outlived us. Needed only when the
    // shell restarted while in PiP and the user then exits; a failure or an
    // `active:false` degrades the exit to "unpin and unfloat", never to
    // stuck.
    root.pipRequestSnapshot(sock)
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
    // Our own get_property answer (M2-05 4.5), routed by request id before
    // the event router sees it. Everything else falls through unchanged.
    if (root.pipNoteReply(line)) return
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
    // Model.playerDeathKind() decides what this EOF was, because a helper
    // that ladders a player down and spawns its replacement under one lock
    // delivers the old one's death here while that call is still running.
    var death = Model.playerDeathKind({
      sessionInFlight: playerProc.running && (root.playerKind === "start" || root.playerKind === "restart"),
      relaunchPending: root.relaunchPending,
      nowPlaying: current !== null,
      hasChannel: current !== null && !!root.channelIndex[String(current.id)],
      userStopped: stopped,
      stopping: root.stopping
    })
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
    // M2-05 / PIP3. The window PiP was applied to is gone, so PiP is over -
    // including on a respawn, which brings back a different window with a
    // different pid. Nothing remembers an intent across a window's lifetime
    // to re-apply it later; the user presses the key again.
    root.pipReset()
    if (death === "respawn") {
      // A rung of the ladder the helper is running right now, for this very
      // channel. The intent is unchanged, so the birth edge is held, the
      // observer keeps hunting - it is already retrying when the new mpv
      // binds, with no dependence on the helper's reply arriving - and the
      // user is told nothing, because nothing has ended. The record outlives
      // this death for the same reason a queued relaunch does.
      root.playerPending = true
      root.playerWanted = true
      root.armPlayerSocket()
      root.noteSessionOutcome("respawning")
      return
    }
    if (death === "relaunch") {
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
      root.playlistLoadWarnings = []
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
    // No stale numbers across a swap: the number space belongs to one source
    // (1.5), and a guide showing the previous playlist's numbers would let a
    // digit tune to a channel that is no longer loaded.
    root.chnoIndex = Model.buildChnoIndex(null)
    root.preparedActive = null
    root.channelsMeta = ({})
    root.playlistStatus = ({ ok: false, kind: "playlist", stale: false, error: null })
    root.playlistLoadWarnings = []
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

  // ============================================================ STAND-IN-M2-05-V1
  //
  // TEMPORARY. Every function in this block belongs to lane V1 (task
  // M2-05-02) and ships in Model.js; this lane needs them to build the
  // service half before that branch merges, so they are here with the EXACT
  // names and signatures docs/M2-05-PICTURE-IN-PICTURE.md gives them.
  //
  // HOW TO SWAP, when lane V1 has merged: each wrapper below is one line and
  // the comment on it is the line that replaces it. Do all of them, then
  // delete everything under the HELPERS marker. Nothing outside these two
  // markers calls one of those helpers, and tests/test_pip.py asserts it.
  //
  //   grep -c 'STAND-IN-M2-05-V1' Service.qml     must be 0 at integration
  //
  // Three of these are NOT in the design and are requested of lane V1 in the
  // handover: pipVerify (PIP11 has no verification function in the design),
  // pipFindMonitor, pipIsOn, pipSnapshotFrom and pipReadSnapshot.

  function pipOptions(config) { return STANDIN_pipOptions(config) }                                  // -> return Model.pipOptions(config)
  function pipFindWindow(clientsJson, pid, cls) { return STANDIN_pipFindWindow(clientsJson, pid, cls) } // -> return Model.pipFindWindow(clientsJson, pid, cls)
  function pipFindMonitor(monitorsJson, id) { return STANDIN_pipFindMonitor(monitorsJson, id) }      // -> return Model.pipFindMonitor(monitorsJson, id)
  function pipGeometry(monitor, opts) { return STANDIN_pipGeometry(monitor, opts) }                  // -> return Model.pipGeometry(monitor, opts)
  function pipPlan(live, snapshot, geometry, intent) { return STANDIN_pipPlan(live, snapshot, geometry, intent) } // -> return Model.pipPlan(live, snapshot, geometry, intent)
  function pipVerify(live, snapshot, geometry, intent) { return STANDIN_pipVerify(live, snapshot, geometry, intent) } // -> return Model.pipVerify(live, snapshot, geometry, intent)
  function pipLuaDispatch(verb, args) { return STANDIN_pipLuaDispatch(verb, args) }                  // -> return Model.pipLuaDispatch(verb, args)
  function pipLegacyDispatch(verb, args) { return STANDIN_pipLegacyDispatch(verb, args) }            // -> return Model.pipLegacyDispatch(verb, args)
  function pipMpvCommands(intent, snapshot, mpvArgs) { return STANDIN_pipMpvCommands(intent, snapshot, mpvArgs) } // -> return Model.pipMpvCommands(intent, snapshot, mpvArgs)
  function pipRestoreAutoResize(mpvArgs) { return STANDIN_pipRestoreAutoResize(mpvArgs) }            // -> return Model.pipRestoreAutoResize(mpvArgs)
  function pipIsOn(live) { return STANDIN_pipIsOn(live) }                                            // -> return Model.pipIsOn(live)
  function pipSnapshotFrom(live) { return STANDIN_pipSnapshotFrom(live) }                            // -> return Model.pipSnapshotFrom(live)
  function pipReadSnapshot(data) { return STANDIN_pipReadSnapshot(data) }                            // -> return Model.pipReadSnapshot(data)
  function parsePlayerReply(line) { return STANDIN_parsePlayerReply(line) }                          // -> return Model.parsePlayerReply(line)

  // ---------------------------------------------- STAND-IN-M2-05-V1-HELPERS

  function STANDIN_pipClampInt(value, lo, hi, fallback) {
    if (value === undefined || value === null || value === "") return fallback
    var n = Number(value)
    if (!isFinite(n)) return fallback
    n = Math.floor(n)
    if (n < lo) return lo
    if (n > hi) return hi
    return n
  }

  function STANDIN_pipOptions(config) {
    var c = (config && typeof config === "object") ? config : {}
    var corners = ["top-right", "top-left", "bottom-right", "bottom-left"]
    var corner = String(c.pipCorner === undefined || c.pipCorner === null ? "" : c.pipCorner)
    if (corners.indexOf(corner) < 0) corner = "top-right"
    return { corner: corner,
             sizePercent: STANDIN_pipClampInt(c.pipSizePercent, 15, 60, 30),
             margin: STANDIN_pipClampInt(c.pipMargin, 0, 200, 16) }
  }

  function STANDIN_pipParse(text) {
    var out = null
    try { out = JSON.parse(String(text === undefined || text === null ? "" : text)) } catch (e) { out = null }
    if (!out || Object.prototype.toString.call(out) !== "[object Array]") return null
    return out
  }

  function STANDIN_pipPair(value) {
    if (!value) return null
    var a = Math.floor(Number(value[0])), b = Math.floor(Number(value[1]))
    if (!isFinite(a) || !isFinite(b)) return null
    return [a, b]
  }

  function STANDIN_pipFindWindow(clientsJson, pid, cls) {
    var list = STANDIN_pipParse(clientsJson)
    if (list === null) return { ok: false, reason: "no_window" }
    var want = Math.floor(Number(pid) || 0)
    if (want <= 0) return { ok: false, reason: "no_window" }
    var name = String(cls || "")
    var hits = []
    for (var i = 0; i < list.length; i++) {
      var c = list[i]
      if (!c || typeof c !== "object") continue
      if (String(c["class"]) !== name) continue
      if (Math.floor(Number(c.pid) || 0) !== want) continue
      hits.push(c)
    }
    if (hits.length === 0) return { ok: false, reason: "no_window" }
    if (hits.length > 1) return { ok: false, reason: "ambiguous" }
    var w = hits[0]
    var address = String(w.address || "")
    if (!/^0x[0-9a-f]{1,16}$/.test(address)) return { ok: false, reason: "bad_address" }
    var at = STANDIN_pipPair(w.at), size = STANDIN_pipPair(w.size)
    if (at === null || size === null) return { ok: false, reason: "bad_address" }
    // A RULE-applied tag reads back as "default-opacity*" on this machine; a
    // DISPATCHED one does not (G-11). Compare with the marker stripped.
    var tags = [], raw = w.tags
    if (raw && Object.prototype.toString.call(raw) === "[object Array]") {
      for (var t = 0; t < raw.length; t++) tags.push(String(raw[t]).replace(/\*+$/, ""))
    }
    var ws = (w.workspace && typeof w.workspace === "object") ? Math.floor(Number(w.workspace.id) || 0) : 0
    return { ok: true, address: address, at: at, size: size,
             floating: w.floating === true, pinned: w.pinned === true,
             monitor: Math.floor(Number(w.monitor) || 0), workspaceId: ws, tags: tags }
  }

  function STANDIN_pipFindMonitor(monitorsJson, id) {
    var list = STANDIN_pipParse(monitorsJson)
    if (list === null) return null
    var want = Math.floor(Number(id))
    for (var i = 0; i < list.length; i++) {
      var m = list[i]
      if (m && typeof m === "object" && Math.floor(Number(m.id)) === want) return m
    }
    return null
  }

  // Section 4.4, corrected by the gate: the defaults on a 1366x768 scale-1
  // transform-0 monitor with reserved [0, 26, 0, 0] give 410x230 at (940, 42)
  // - the document's own worked example said (932, 42) and was 8 px wrong.
  function STANDIN_pipGeometry(monitor, opts) {
    var m = (monitor && typeof monitor === "object") ? monitor : null
    if (!m) return null
    var o = (opts && typeof opts === "object") ? opts : STANDIN_pipOptions(null)
    var scale = Number(m.scale)
    if (!isFinite(scale) || scale <= 0) scale = 1
    // hyprctl monitors reports PHYSICAL pixels; a dispatcher speaks logical.
    var lw = Math.round(Number(m.width) / scale), lh = Math.round(Number(m.height) / scale)
    if (!isFinite(lw) || !isFinite(lh) || lw <= 0 || lh <= 0) return null
    if (Math.abs(Math.floor(Number(m.transform) || 0)) % 2 === 1) { var s = lw; lw = lh; lh = s }
    var res = m.reserved && m.reserved.length === 4 ? m.reserved : [0, 0, 0, 0]
    var r0 = Math.floor(Number(res[0]) || 0), r1 = Math.floor(Number(res[1]) || 0)
    var r2 = Math.floor(Number(res[2]) || 0), r3 = Math.floor(Number(res[3]) || 0)
    // Global layout coordinates: `move` takes them, and only a rule
    // expression would use per-monitor ones.
    var mx = Math.floor(Number(m.x) || 0), my = Math.floor(Number(m.y) || 0)
    var x0 = mx + r0 + o.margin, y0 = my + r1 + o.margin
    var x1 = mx + lw - r2 - o.margin, y1 = my + lh - r3 - o.margin
    if (x1 - x0 < 2 || y1 - y0 < 2) return null
    var w = Math.round(lw * o.sizePercent / 100)
    if (w < 240) w = 240
    if (w > x1 - x0) w = x1 - x0
    var h = Math.round(w * 9 / 16)                 // 16:9 by convention; 4:3 letterboxes inside
    if (h > y1 - y0) {
      h = y1 - y0
      w = Math.round(h * 16 / 9)
      if (w > x1 - x0) w = x1 - x0
    }
    w = w - (w % 2); h = h - (h % 2)
    if (w < 2 || h < 2) return null
    var right = o.corner === "top-right" || o.corner === "bottom-right"
    var bottom = o.corner === "bottom-left" || o.corner === "bottom-right"
    return { x: right ? x1 - w : x0, y: bottom ? y1 - h : y0, w: w, h: h }
  }

  function STANDIN_pipHasTag(live, tag) {
    var tags = live && live.tags ? live.tags : []
    for (var i = 0; i < tags.length; i++) if (tags[i] === tag) return true
    return false
  }

  function STANDIN_pipIsOn(live) {
    return !!live && live.floating === true && live.pinned === true && STANDIN_pipHasTag(live, "iptv-pip")
  }

  function STANDIN_pipSnapshotFrom(live) {
    if (!live || !live.ok) return null
    return { active: true, at: live.at, size: live.size,
             floating: live.floating === true, pinned: live.pinned === true,
             monitor: live.monitor, workspace: live.workspaceId, v: 1 }
  }

  function STANDIN_pipReadSnapshot(data) {
    if (!data || typeof data !== "object" || data.active !== true) return null
    var at = STANDIN_pipPair(data.at), size = STANDIN_pipPair(data.size)
    if (at === null || size === null) return null
    return { active: true, at: at, size: size,
             floating: data.floating === true, pinned: data.pinned === true,
             monitor: Math.floor(Number(data.monitor) || 0),
             workspace: Math.floor(Number(data.workspace) || 0), v: 1 }
  }

  // Section 4.3, with the G-3 correction: `action` is ignored and both verbs
  // toggle, so every float and pin step stays behind a fresh read. The
  // unpin-before-unfloat order is load-bearing - `pin` applies to floating
  // windows, and unfloating a pinned window clears the pin by itself.
  function STANDIN_pipPlan(live, snapshot, geometry, intent) {
    var steps = []
    if (!live || !live.ok) return steps
    var a = live.address
    if (intent === "on") {
      if (!geometry) return steps
      if (live.floating !== true) steps.push(root.pipDispatch("float", { address: a }))
      steps.push(root.pipDispatch("resize", { address: a, x: geometry.w, y: geometry.h }))
      steps.push(root.pipDispatch("move", { address: a, x: geometry.x, y: geometry.y }))
      if (live.pinned !== true) steps.push(root.pipDispatch("pin", { address: a }))
      steps.push(root.pipDispatch("alter_zorder", { address: a }))
      steps.push(root.pipDispatch("tag", { address: a, tag: "+iptv-pip" }))
      return steps
    }
    if (intent !== "off") return steps
    var snap = (snapshot && typeof snapshot === "object") ? snapshot : {}
    steps.push(root.pipDispatch("tag", { address: a, tag: "-iptv-pip" }))
    if (live.pinned === true && snap.pinned !== true) steps.push(root.pipDispatch("pin", { address: a }))
    if (snap.floating === true) {
      steps.push(root.pipDispatch("resize", { address: a, x: snap.size[0], y: snap.size[1] }))
      steps.push(root.pipDispatch("move", { address: a, x: snap.at[0], y: snap.at[1] }))
    } else if (live.floating === true) {
      steps.push(root.pipDispatch("float", { address: a }))
    }
    return steps
  }

  // PIP11. What the compositor must report for the request to count as done.
  // Deliberately exact on all five fields: the gate measured `at` and `size`
  // landing on the requested integers to the pixel, so a tolerance here would
  // only hide the failure it was added to survive.
  function STANDIN_pipVerify(live, snapshot, geometry, intent) {
    var bad = []
    if (!live || !live.ok) return { ok: false, mismatch: ["no_window"] }
    var tagged = STANDIN_pipHasTag(live, "iptv-pip")
    if (intent === "on") {
      if (!geometry) return { ok: false, mismatch: ["no_geometry"] }
      if (live.floating !== true) bad.push("floating")
      if (live.pinned !== true) bad.push("pinned")
      if (!tagged) bad.push("tag")
      if (live.at[0] !== geometry.x || live.at[1] !== geometry.y) bad.push("at")
      if (live.size[0] !== geometry.w || live.size[1] !== geometry.h) bad.push("size")
      return { ok: bad.length === 0, mismatch: bad }
    }
    if (intent !== "off") return { ok: false, mismatch: ["no_intent"] }
    var snap = (snapshot && typeof snapshot === "object") ? snapshot : null
    if (tagged) bad.push("tag")
    // With no snapshot the exit degrades to "unpin and unfloat and let the
    // layout take it", which is what the Omarchy precedent does
    // unconditionally. Degraded, never stuck (4.5).
    var wantFloating = !!snap && snap.floating === true
    var wantPinned = !!snap && snap.pinned === true
    if (live.floating !== wantFloating) bad.push("floating")
    if (live.pinned !== wantPinned) bad.push("pinned")
    if (wantFloating) {
      if (live.at[0] !== snap.at[0] || live.at[1] !== snap.at[1]) bad.push("at")
      if (live.size[0] !== snap.size[0] || live.size[1] !== snap.size[1]) bad.push("size")
    }
    return { ok: bad.length === 0, mismatch: bad }
  }

  // 4.11 and ruling PIP7. Two kinds of value may reach a dispatch string and
  // no others: an address that matched /^0x[0-9a-f]{1,16}$/, and integers
  // inside [-100000, 100000]. Everything else is a constant in this file.
  // The regex is applied in pipFindWindow and applied AGAIN here so a later
  // caller cannot route around it.
  function STANDIN_pipInt(value) {
    var n = Number(value)
    if (!isFinite(n)) return null
    n = Math.floor(n)
    if (n < -100000 || n > 100000) return null
    return n
  }

  function STANDIN_pipArgs(verb, args) {
    var verbs = ["float", "pin", "resize", "move", "tag", "alter_zorder"]
    if (verbs.indexOf(String(verb)) < 0) return null
    var a = (args && typeof args === "object") ? args : {}
    var address = String(a.address || "")
    if (!/^0x[0-9a-f]{1,16}$/.test(address)) return null
    var out = { address: address }
    if (verb === "resize" || verb === "move") {
      out.x = STANDIN_pipInt(a.x)
      out.y = STANDIN_pipInt(a.y)
      if (out.x === null || out.y === null) return null
    }
    if (verb === "tag") {
      // The only two tag literals this feature has. Not a pattern that
      // accepts a name: nothing playlist-derived may ever reach this string.
      out.tag = String(a.tag || "")
      if (out.tag !== "+iptv-pip" && out.tag !== "-iptv-pip") return null
    }
    return out
  }

  function STANDIN_pipLuaDispatch(verb, args) {
    var a = STANDIN_pipArgs(verb, args)
    if (a === null) return null
    var parts = ['window = "address:' + a.address + '"']
    if (verb === "resize" || verb === "move") { parts.push("x = " + a.x); parts.push("y = " + a.y) }
    if (verb === "tag") parts.push('tag = "' + a.tag + '"')
    if (verb === "alter_zorder") parts.push('mode = "top"')
    if (verb === "float") parts.push('action = "toggle"')
    return ["hyprctl", "dispatch", "hl.dsp.window." + verb + "({ " + parts.join(", ") + " })"]
  }

  // For a Hyprland whose config provider is not Lua. The COMMA spelling from
  // omarchy-capture-webcam-resize, never the space spelling
  // omarchy-hyprland-window-pop uses - that one has no window selector at all
  // and would resize whatever the user is working in.
  function STANDIN_pipLegacyDispatch(verb, args) {
    var a = STANDIN_pipArgs(verb, args)
    if (a === null) return null
    var target = "address:" + a.address
    if (verb === "float") return ["hyprctl", "dispatch", "togglefloating", target]
    if (verb === "pin") return ["hyprctl", "dispatch", "pin", target]
    if (verb === "resize") return ["hyprctl", "dispatch", "resizewindowpixel", "exact " + a.x + " " + a.y + "," + target]
    if (verb === "move") return ["hyprctl", "dispatch", "movewindowpixel", "exact " + a.x + " " + a.y + "," + target]
    if (verb === "alter_zorder") return ["hyprctl", "dispatch", "alterzorder", "top," + target]
    return ["hyprctl", "dispatch", "tagwindow", a.tag + "," + target]
  }

  function STANDIN_pipRestoreAutoResize(mpvArgs) {
    var tokens = String(mpvArgs || "").split(/\s+/)
    var value = true
    for (var i = 0; i < tokens.length; i++) {
      var t = tokens[i]
      if (t === "--no-auto-window-resize") { value = false; continue }
      if (t === "--auto-window-resize") { value = true; continue }
      if (t.indexOf("--auto-window-resize=") !== 0) continue
      var v = t.substring("--auto-window-resize=".length).toLowerCase()
      value = !(v === "no" || v === "false" || v === "0")
    }
    return value
  }

  function STANDIN_pipMpvCommands(intent, snapshot, mpvArgs) {
    if (intent === "on") {
      return [["set_property", "user-data/omarchy-iptv-pip", snapshot || { active: false, v: 1 }],
              ["set_property", "auto-window-resize", false]]
    }
    return [["set_property", "user-data/omarchy-iptv-pip", { active: false, v: 1 }],
            ["set_property", "auto-window-resize", STANDIN_pipRestoreAutoResize(mpvArgs)]]
  }

  function STANDIN_parsePlayerReply(line) {
    var obj = null
    try { obj = JSON.parse(String(line || "")) } catch (e) { return null }
    if (!obj || typeof obj !== "object") return null
    if (obj.event !== undefined) return null            // an event is never a reply
    if (obj.request_id === undefined) return null
    var err = String(obj.error === undefined ? "" : obj.error)
    return { requestId: Math.floor(Number(obj.request_id) || 0), error: err,
             ok: err === "success", data: obj.data === undefined ? null : obj.data }
  }

  // ======================================================== end STAND-IN-M2-05-V1

  // Which spelling the compositor can parse, decided once from its own
  // answer rather than by trying one and reading an exit code that cannot
  // report a refused effect (PIP11).
  function pipDispatch(verb, args) {
    return root.pipProvider === "legacy" ? root.pipLegacyDispatch(verb, args)
                                         : root.pipLuaDispatch(verb, args)
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
    // M2-05 G-8: is there a compositor to talk to at all, and which dispatch
    // spelling can it parse? Both answers are read once, here, so the `p`
    // key can refuse honestly instead of firing into the dark.
    hyprWhichProc.running = true
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
    // The control slot's watchdog. `playlistProc`, `epgProc` and
    // `playerProc` all had one; `controlProc` did not, and it is the slot
    // that serialises every zap and every health check - one helper stuck
    // there is the end of channel switching until the shell restarts.
    //
    // A terminated helper produces no stdout, which parses to `no_output`,
    // and `no_output` is a "cannot tell" on both branches now: it is never
    // a health strike and never a failed switch. Killing the slot must not
    // be able to report that the user's channel change failed.
    id: controlWatchdog
    interval: root.controlTimeoutMs
    repeat: false
    onTriggered: {
      if (!controlProc.running) return
      console.warn("omarchy-iptv: " + (root.controlKind || "control") + " helper exceeded "
                   + Math.floor(root.controlTimeoutMs / 1000) + " s, terminating it")
      controlProc.signal(15)
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
    // One bound per compositor round trip. A read or a dispatch that has not
    // exited in 2 s is terminated and the sequence ends reporting it: there
    // is no unbounded wait anywhere in this feature (CLAUDE.md rule 3).
    id: pipStepWatchdog
    interval: root.pipStepMs
    repeat: false
    onTriggered: {
      if (hyprClientsProc.running) hyprClientsProc.signal(15)
      if (hyprMonitorsProc.running) hyprMonitorsProc.signal(15)
      if (hyprDispatchProc.running) hyprDispatchProc.signal(15)
      if (!root.pipBusy) return
      console.warn("omarchy-iptv pip: the compositor did not answer in " + Math.floor(root.pipStepMs / 1000) + " s")
      root.pipFinish(false, "timeout")
    }
  }

  Timer {
    // And one bound on the whole sequence, so `pipBusy` can never latch and
    // lock the user out of the key for the rest of the session.
    id: pipSequenceWatchdog
    interval: root.pipSequenceMs
    repeat: false
    onTriggered: {
      if (!root.pipBusy) return
      console.warn("omarchy-iptv pip: giving up after " + Math.floor(root.pipSequenceMs / 1000) + " s")
      root.pipFinish(false, "timeout")
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
        //
        // CL3: this line is the only witness for "exactly one relaunch, never
        // a second one aimed at the healthy new player", which is half of the
        // D-PLY-1 fix. Without it the harness assertion matches a string both
        // the fixed and the broken tree emit, so it passes either way and
        // proves nothing. Do not remove it without replacing the witness.
        console.log("omarchy-iptv: relaunching the unresponsive player, seq " + (root.playSeq + 1))
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

  // ---- picture in picture (M2-05). Five Processes, argv arrays only, no
  // shell anywhere: two that decide once whether PiP is offered at all, two
  // that READ the compositor, and one that asks it for something.

  Process {
    // G-8. Without hyprctl on PATH, or without a live instance signature,
    // PiP is hidden rather than broken: `p` says so and the IPC verb answers
    // no_compositor.
    id: hyprWhichProc
    command: ["which", "hyprctl"]
    stdout: StdioCollector { waitForEnd: true }
  }
  Connections {
    target: hyprWhichProc
    function onExited(exitCode, exitStatus) {
      if (exitCode !== 0 || Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE") === "") {
        root.pipAvailable = false
        return
      }
      hyprInfoProc.running = true
    }
  }

  Process {
    // Which dispatch spelling this compositor can parse. Under a Lua config
    // provider `hyprctl dispatch` wraps its argument as
    // `return hl.dispatch(<arg>)`, so the legacy spelling is a Lua SYNTAX
    // error and no spelling of it reaches the compositor at all (G-1). The
    // answer decides the builder ONCE; it is never a retry ladder, because
    // an exit code cannot tell us to retry (PIP11).
    id: hyprInfoProc
    command: ["hyprctl", "systeminfo"]
    stdout: StdioCollector { id: hyprInfoStdout; waitForEnd: true }
    stderr: StdioCollector { waitForEnd: true }
  }
  Connections {
    target: hyprInfoProc
    function onExited(exitCode, exitStatus) {
      // Absent means an older Hyprland with the hyprlang provider, which is
      // exactly the host the legacy spelling exists for.
      root.pipProvider = /configProvider:\s*lua/i.test(String(hyprInfoStdout.text)) ? "lua" : "legacy"
      root.pipAvailable = exitCode === 0
    }
  }

  Process {
    // The state of record. Read at the start of every sequence, before every
    // re-plan, and once more at the end - that last read is the ONLY thing
    // in this feature that decides whether it worked.
    id: hyprClientsProc
    command: ["hyprctl", "-j", "clients"]
    stdout: StdioCollector { id: hyprClientsStdout; waitForEnd: true }
    stderr: StdioCollector { waitForEnd: true }
  }
  Connections {
    target: hyprClientsProc
    function onExited(exitCode, exitStatus) { root.pipApplyClients(hyprClientsStdout.text) }
  }

  Process {
    id: hyprMonitorsProc
    command: ["hyprctl", "-j", "monitors"]
    stdout: StdioCollector { id: hyprMonitorsStdout; waitForEnd: true }
    stderr: StdioCollector { waitForEnd: true }
  }
  Connections {
    target: hyprMonitorsProc
    function onExited(exitCode, exitStatus) { root.pipApplyMonitors(hyprMonitorsStdout.text) }
  }

  Process {
    // One step at a time. `command` is a vector a builder produced from a
    // regex-checked address, clamped integers and compile-time constants
    // (4.11, PIP7) - never bar.run() and never Util.execArgv, both of which
    // are `bash -lc` underneath.
    id: hyprDispatchProc
    stdout: StdioCollector { id: hyprDispatchStdout; waitForEnd: true }
    stderr: StdioCollector { id: hyprDispatchStderr; waitForEnd: true }
  }
  Connections {
    target: hyprDispatchProc
    function onExited(exitCode, exitStatus) {
      root.pipNoteStep(hyprDispatchStdout.text + "\n" + hyprDispatchStderr.text, exitCode)
    }
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

  // omarchy-shell io.github.rmcdavid.iptv toggle | play <id-or-url> |
  // channel <n> | stop | next | previous | refresh | status   (R9)
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
    // Tune by channel number (M2-03 3.2, rulings CN1 and CN10). A string
    // argument like every other verb, so `007`, `7-1` and `  12  ` all work
    // from a shell; it is run through the same parse the guide uses.
    //
    // Its own verb rather than a third fallback inside `play`: play already
    // resolves an id and then a URL, and `play 101` becomes ambiguous the day
    // a provider ships tvg-id="101".
    //
    // A mistyped keybinding must not raise a desktop popup, so a failure is
    // this JSON and nothing else - no notification, no toast (6.5).
    function channel(n: string): string { return JSON.stringify(root.tuneByNumber(n)) }
    // Picture in picture (M2-05). `pip on`, `pip off`, `pip toggle`.
    //
    // The reply is what is knowable when the key is pressed, and no more.
    // Refusals are synchronous and final: bad_mode, no_compositor,
    // nothing_playing, busy. An ACCEPTED request answers
    // {"ok":true,"kind":"pip","requested":"on","was":false,"state":"applying"}
    // and nothing else, because success here is a fact about the compositor
    // that only a readback can establish (PIP11) and that readback is two
    // process round-trips away. Poll `status` for the verified answer: its
    // new `pip` block carries { available, on, applying, reason }, where
    // `reason` is the last failure code (dispatch_failed, no_window,
    // ambiguous, timeout, ...) and "" after a success.
    function pip(mode: string): string { return JSON.stringify(root.requestPip(mode)) }
    function stop(): string { root.stop(); return "ok" }
    function next(): string { return root.zap(1) ? "ok" : "nothing playing" }
    function previous(): string { return root.zap(-1) ? "ok" : "nothing playing" }
    function refresh(): string { root.refresh(); return "ok" }
    function status(): string { return JSON.stringify(root.statusSummary()) }
  }
}
