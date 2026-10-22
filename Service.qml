// The socket observer builds its Socket from a Component (spike caveat C1),
// and that nested component reaches the ids of this file (root, the retry
// timer). Bound is the semantics we want and the semantics we already have:
// there is exactly one creation context here.
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
import "Model.mjs" as Model

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
  // The one spelling of the state file's path: stateFile watches it, the
  // no-write notice names it, and the guide's no-write surface (R23e) names
  // it with the notice's own words.
  readonly property string stateFilePath: stateDir + "/state.json"
  readonly property string runtimeDir: (Quickshell.env("XDG_RUNTIME_DIR") || cacheDir) + "/omarchy-iptv"
  readonly property string socketPath: runtimeDir + "/mpv.sock"
  readonly property string helperPath: decodeURIComponent(Qt.resolvedUrl("bin/omarchy-iptv").toString().replace(/^file:\/\//, ""))
  // D-HOST-1. Qt.resolvedUrl resolves against the QML that is RUNNING, so this
  // is the directory the loaded component came from -- which is exactly the
  // directory `omarchy plugin update` has just rewritten underneath it.
  readonly property string manifestPath: decodeURIComponent(Qt.resolvedUrl("manifest.json").toString().replace(/^file:\/\//, ""))
  // The version on DISK. Model.PLUGIN_VERSION is the version compiled into the
  // component that is running. They agree at release time (the gate proves it),
  // so a disagreement here means a hot reload left an older component mounted
  // and the user is looking at an interface the update was supposed to replace.
  property string onDiskVersion: ""
  readonly property bool staleBuild: Model.staleBuild(Model.PLUGIN_VERSION, onDiskVersion)

  // ---- timing constants, in one place (UX.md 5.9)
  readonly property int refreshDebounceMs: 300
  readonly property int epgRecomputeMs: 5 * 60 * 1000
  readonly property int epgTickMs: 30 * 1000
  readonly property int healthCheckMs: 10 * 1000
  // The shutdown ladder's grace periods live with its reducer in the model
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
  // M5-01 (2.3): the gap between a seek reply and the next seek run.
  readonly property int seekThrottleMs: 300
  readonly property int playerProbeRetryMs: 500    // the one ambiguous-probe re-read (4.5)
  readonly property int stopSettleMs: 5 * 1000     // backstop that clears `stopping` (4.10)
  readonly property int focusRetryMs: 500
  // D-PIP-5 widened this from 6, and cost nothing by doing so. Focus now
  // waits for a window the compositor can name rather than dispatching at a
  // class, so an attempt made before the player's socket has attached
  // resolves nothing and has to be retried - and dispatchFocus() ends the
  // loop the moment one lands, where before it always spent all six. Six
  // seconds, still bounded, still stopped by `playerUp` going false.
  readonly property int focusRetries: 12
  readonly property int healthFailuresBeforeRestart: 2
  // Watchdog bound for one playlist/EPG helper run (S-05). The helper has
  // its own 60 s download deadline; this is the belt and braces for a
  // helper that is stuck anywhere else (DNS, TLS, a parser bug).
  readonly property int helperTimeoutMs: 180 * 1000
  // D-SINK-19 round 13, R23c: the bound on the start-up `state init`, which
  // every state write and the held load wait on. Before it there was none:
  // a FIFO at state.json hung the init in open() (R23b closes that in the
  // helper) and the service waited for ever, untold, leaving an orphaned
  // helper at every start. Measured 2026-10-13 on this 4-core machine, 30
  // runs each of the real init over a fresh and an existing file: idle
  // 214-215 ms; six busy loops (1.5x oversubscribed) median 543, max 968
  // ms; twelve (3x) median 1246, max 1769 ms. 15 s is 8.5x the worst of
  // those and 70x idle: a start that slow is already failing the user, and
  // a false timeout costs one session in the no-write mode, told, with
  // nothing lost -- a smaller harm than waiting for ever.
  readonly property int stateInitTimeoutMs: 15 * 1000
  // How long a terminated init has to exit before it is killed outright.
  readonly property int stateInitKillGraceMs: 2 * 1000
  // D-SINK-19 round 14, R24d (D-SRC-25): the bound is over the WHOLE
  // start-up check -- mkdirProc and stateInitProc alike, armed when mkdir
  // starts (startStartupCheck), the 15 s spent by whichever is running. A
  // filesystem that hangs mkdir hangs the init too, and the first version
  // armed the watchdog only at the init, so a hung mkdir left the load
  // waiting for ever, untold. And the init bounds ITSELF (the helper's
  // STATE_INIT_DEADLINE, SIGALRM at the top of the verb, longer than this
  // bound plus the grace) so a shell that stops first leaves nothing
  // running past it (D-SRC-24). Neither reaches a process in uninterruptible
  // sleep on a hung filesystem: a signal waits until the kernel lets go.

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
  // `lastEntryWrite` USED TO BE HERE (round 8, R18b): this service's record of
  // its own last entry write, from which the funnel ESTIMATED what the host
  // stores and skipped a write it judged the host would answer `false` to.
  // R19a (round 9) withdrew it: on the lagging host a publish that goes
  // A -> B -> A brought the record back and the funnel skipped writes the
  // host would have stored. updateEntryInline's own answer is the dirty
  // check; Model.sameOwnWrite settles the cycle (see writeOwnedEntry).
  // D-SRC-18 (R19d): a held key mirror DROPPED because its state save failed
  // leaves the entry exactly as it was. The first later save that lands pays
  // that debt with one mirror (Model.owedMirrorAction, from stateFile's
  // `saved`), so an input the failed write carried does not sit on the entry
  // to be re-adopted, seen "now", over a later in-app edit at the next start.
  property bool entryMirrorOwed: false
  readonly property var settings: Model.settingsWithOwnWrite(hostSettings, ownWrite)
  // D-SINK-19 round 11 (R21, the product owner's decision of 2026-10-13):
  // the bar entry's `playlistUrl` and `epgUrl` are read ONCE, by the
  // migration of an install written before the change, which named its
  // active source by the URL there. reconcile() adopts them while the LANDED
  // state does not carry the migration marker (Model.entryMigratedOf over
  // `landedState`), and from the moment it does a value found there is
  // refused, reported once (Model.entryInputNotice) and stripped by the next
  // owned write. The `omarchy bar set` URL route is gone; the Sources screen
  // is the one place a source is added, switched or edited. The credential
  // lives only in the plugin's own 0600 state.json, and the entry carries
  // the key.
  // The active source's record and its playlist URL: what every fetch, label
  // and host line uses. Derived from state.json's `activeKey`, so a switch
  // moves it in the same event-loop turn as the state write and nothing in
  // the plugin waits for the host to echo anything back (rule 9).
  readonly property var activeSourceRecord: Model.activeSourceRecord(root.userState)
  readonly property string playlistUrl: root.activeSourceRecord ? String(root.activeSourceRecord.url || "") : ""
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
  // ---- logos (M2-04, RULING-LOGOS.md (dev branch)). Off by default, and the reader
  // is Model.optInSetting rather than boolSetting: an unknown value here
  // would contact third parties, so this one fails closed.
  readonly property bool showLogos: settings.showLogos
  // Where the fetched files live, and "" whenever they must not be read:
  // no active source, or the setting off. The guide binds its column to this,
  // so turning the setting off empties the column in the same turn rather
  // than leaving the last playlist's pictures on screen.
  // Derived through Model.logoDirFor and NOWHERE else: the set a fetch
  // announces is tagged through the same call (fetchLogos), and the guide
  // compares the two. The first D-LOGO-11 repair tagged with the cache
  // directory while this bound the logos directory, and every slot was blank.
  readonly property string logoDir: root.showLogos ? Model.logoDirFor(root.activeCacheDir) : ""
  // What enabling logos would disclose, counted from the cache and contacting
  // nothing. The guide shows these numbers BEFORE the switch is thrown
  // (ruling rule 6): a generic "may contact third parties" is not informed
  // consent when the real answer is countable.
  function logoSurvey() { return Model.logoSurvey(root.channels) }
  // D-SINK-19: "there is an active source", not "the bar entry holds a URL".
  // The entry holds no URL at all after this change, so the old test would
  // read as unconfigured for every install -- which is exactly what an OLDER
  // build does to a migrated one, cost 2 of the change.
  readonly property bool configured: root.activeSourceKey !== ""
  // The EPG URL THE USER SET for the active source: the active record's own
  // epgUrl once the history knows the source (an EPG URL belongs to the
  // source it was set for, D-SRC-10; the settings follow it through
  // reconcile), the raw setting while no record exists or the setting does
  // not validate (the helper then reports it, as in 0.1.0).
  //
  // Since M4-01 repair 3 this is no longer the URL the fetch uses -- see
  // `epgFetchUrl` below, which falls back to the playlist's own declaration.
  // Everything that PERSISTS a guide URL still reads this one, and that is
  // the point of the split.
  // D-SINK-19: the RECORD is the only place a guide URL the user set is
  // stored now. The input setting survives as the fallback for the one case
  // that has no record -- a CLI `epgUrl` set before any source exists, and an
  // invalid one, which D16 has to surface rather than swallow.
  // R21: the record's own, and nothing else -- a guide URL on the bar entry
  // reaches the record through the migration or not at all, so neither the
  // raw input nor a held value (round 9's pendingEpg) is a fallback any more.
  // Model.activeEpgUrlOf holds the decision (rule 12: the round-8 lens
  // reverted this read inline and nothing went red).
  readonly property string activeEpgUrl: Model.activeEpgUrlOf(root.activeSourceRecord)
  // M4-01 repair 3 (D-EPG-2). The guide URL actually in force, and where it
  // came from: the user's own value when they set one, otherwise the
  // `url-tvg` / `x-tvg-url` the playlist declared, which the helper has
  // parsed into channels.json as `epgUrlHint` since the first parser and
  // which nothing has ever read.
  //
  // RESOLVED HERE, EVERY TIME, AND NEVER PERSISTED (Model.resolveEpgUrl
  // decision 1). `activeEpgUrl` above is untouched and still means "the URL
  // the USER set for the active source": it is what persistActive writes,
  // what the Sources form edits, and what `onActiveEpgUrlChanged` clears the
  // EPG cache for. The hint is a third input that joins them only at the
  // fetch, so nothing in the persist or settings path can mistake it for a
  // value the user typed, and no source record ever carries it.
  //
  // It is also why the clear-the-cache branch of onActiveEpgUrlChanged stays
  // keyed to `activeEpgUrl` and not to this: `channelsMeta` is emptied on
  // every source swap (clearSourceData), so a resolved hint goes to "" on a
  // swap, and wiping epg-now.json / epg-status.json on a swap would be a new
  // defect rather than the setting-owns-its-cache rule it looks like.
  readonly property var epgSource: Model.resolveEpgUrl({
    userUrl: root.activeEpgUrl,
    hint: root.channelsMeta ? root.channelsMeta.epgUrlHint : ""
  })
  // The URL every EPG fetch uses. Redacted everywhere else: `epgSourceHost`
  // is what any sink gets, and the URL itself only ever reaches the helper's
  // environment (D-SINK-8).
  readonly property string epgFetchUrl: root.epgSource.url
  readonly property string epgUrlOrigin: root.epgSource.origin
  readonly property bool epgFromPlaylist: root.epgSource.origin === Model.EPG_ORIGIN_PLAYLIST
  readonly property string epgSourceHost: root.epgSource.host
  // The one line that makes the provenance visible, for the Sources screen
  // and the source form: "" when the URL is the user's own.
  readonly property string epgOriginNotice: Model.epgOriginNotice(root.epgSource.origin)
  readonly property bool epgConfigured: epgFetchUrl !== ""
  // scheme + host only; safe to render anywhere
  readonly property string sourceLabel: Model.sourceLabel(playlistUrl)
  readonly property string sourceHost: Model.hostOf(playlistUrl)

  // ---- sources (M2-01, ARCHITECTURE-SOURCES.md section 4, rulings SR1-SR9).
  // The active source is named by its KEY in state.json's `activeKey`
  // (D-SINK-19, which overturns the persistence half of D1/D4; the bar entry
  // carries `sourceKey` as a mirror and no URL at all); the history lives in
  // userState.sources (state.json v2, D2); each source has its own cache
  // directory under cacheDir/sources/<key>/ (D5).
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
  // D16 / SR8: the validation result when the `playlistUrl` INPUT is set but
  // invalid. Since R21 an input exists only during the migration, so this is
  // set only for an invalid URL a 0.13.x entry carried; a value found on the
  // entry after the marker has landed is refused and never validated here.
  //
  // D-SINK-19 narrowed what this may do. It used to be a statement about the
  // ACTIVE source, because the setting WAS the active source: a typo in
  // `omarchy bar set ... playlistUrl` matched no record, the active key went
  // "", the cache unbound and the guide showed the validation sentence over an
  // empty body. Now the setting is an input and the active source is in
  // state.json, so a rejected input must not take a working source away -- the
  // D16 behaviour is kept for the case D16 was written for, which is a bad CLI
  // value that is the ONLY configuration there is (`invalidInputBlocks`).
  property var settingsInvalid: null
  // Does the rejected input become the guide's error state and stop the
  // helper? Only when there is no active source to show instead.
  readonly property bool invalidInputBlocks: Model.invalidInputBlocks(root.settingsInvalid, root.activeSourceKey)
  // Whether reconcile() has run since the state loaded (the first one is
  // forced: Model.reconcileAction's "migrate").
  property bool reconciled: false
  // R21b. Every value this session has migrated or refused off the bar
  // entry, by setting (Model.entryInputsSeenAfter): what tells a value the
  // user set from the host's stale publish of one already handled (rule 9),
  // so neither is adopted twice nor reported twice. IN MEMORY ONLY, by
  // ruling: round 10 persisted a digest of it (entryInputs) and the next
  // review broke it three ways. Never published: the values can carry
  // credentials.
  property var entryInputsSeen: ({})
  // R21b. What this session reported, as { setting, reason } -- names and
  // reasons only, never a value. The harness reads it through pointerState
  // to count the reports; the user reads the notification and the console.
  property var entryInputReports: []
  property var cacheQueue: []                          // FIFO of { args, onDone } for cacheProc (section 4.7)
  property var cacheJob: null
  // R25a (D-SINK-19 round 15, D-SRC-30): the texts asked for since the last
  // save that LANDED -- an echo is only a text still in flight. stateFile's
  // `saved` clears it when the last text asked for lands; the echo of THAT
  // save then carries the base and is ignored as `unchanged`, and an older
  // own text coming back later is a backup put back, another writer's
  // (Model.reloadDisposition). It used to hold the last eight texts written,
  // and a restored copy of one of them was ignored and then written over.
  property var recentSaves: []
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
  // D-SINK-19. From the state, not by matching a URL. Model.activeKeyOf
  // resolves a key that names no record to "", so an evicted source, a CLI
  // `state source remove` and a hand-edited file all read as "no active
  // source" rather than as a cache directory nobody owns.
  readonly property string activeSourceKey: Model.activeKeyOf(root.userState)
  readonly property string activeSourceId: activeSourceKey
  readonly property string activeSourceLabel: {
    var rec = Model.findSource(root.userState.sources, root.activeSourceKey)
    return rec ? rec.label : root.sourceLabel
  }
  readonly property string activeCacheDir: (root.stateLoaded && root.cacheReady && root.activeSourceKey !== "")
    ? Model.sourceCacheDir(root.cacheDir, root.activeSourceKey) : ""
  readonly property int sourceCount: Model.asList(root.userState.sources).length
  // R28e: the cap is Model.sourcesFull's decision, here as everywhere.
  readonly property bool canAddSource: !Model.sourcesFull(root.userState) && !root.probing
  // View objects for the guide (SR1, ordered per SR32); `sourcesChanged` is
  // this property's change signal (SR3) and fires on every state, settings,
  // error or clock change.
  // `epgFromPlaylist` reaches the view objects so the active row can read
  // `EPG from playlist` rather than `EPG` (M4-01 repair 3): the user must be
  // able to tell a URL the provider declared from one they typed, which is
  // the whole reason the hint is not persisted.
  readonly property var sources: Model.sourceViews(root.userState, root.activeSourceKey, root.nowSec, root.sourceErrors, root.epgFromPlaylist)

  // ---- data (read by Guide.qml / BarWidget.qml; never mutated by them)
  property var channels: []                 // Model.prepareChannels output, in the ACTIVE order
  // D-SG-3: keyed by channel id, and read with ids from state.json and from
  // IPC `play`, so null-prototype from the start -- on a plain `({})` the id
  // `constructor` found the Object function and read as a loaded channel.
  property var channelIndex: Model.keyedMap()
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
  // PO 2026-09-24, amending R8 / R11 and UX ruling 9: the mark now SURVIVES a
  // restart. { id: <epoch> }, loaded from the ACTIVE SOURCE's cache rather
  // than state.json -- channel ids are global across sources, so a
  // state-level map would mark another provider's working channel, and it
  // would fall inside D-ID-1's id-rotation blast radius, which that defect
  // records as excluded precisely because this used to be session-only.
  // Per source, that exclusion stays true.
  // PAUSE LIVE TV (2026-09-24). What the player last told us. The health tick
  // already asks mpv for `pause` every few seconds, so this costs no new
  // traffic -- it was being read and thrown away.
  //
  // This comment used to say "not rewind: the streams are not seekable
  // (1 of 22 measured)". That read the wrong property. `seekable` is false
  // on every live stream, and 31 of 32 rewound anyway: the truth is in
  // `demuxer-cache-state.seekable-ranges`, and mpv's default cache -- the
  // 50 MiB back buffer plus the donated 150 MiB forward quota, 200 MiB in
  // all -- holds a measured 353-359 s of history on a 4.7 Mbps stream and a
  // median 411 s across the owner's source (the live-rewind spike, sections
  // 3, 4 and 11, and the M5-01 live-rewind design, both on the dev branch).
  // Rewind is the `rewind` state below. What the measurement says about PAUSE: the pause
  // itself is bounded by the forward quota alone, 150 MiB over the bitrate
  // (265 s at 4.7 Mbps), with or without history behind it -- and once the
  // total reaches 200 MiB a pause EATS the rewind window, one second of
  // history per paused second, down to the 93 s the back buffer owns
  // outright. Pause and rewind compose in both orders (spike 11.2).
  property bool paused: false
  // M5-01 LIVE REWIND (design section 2.3, on the dev branch). The `rewind` object of
  // the last helper reply that carried one -- `status`, `pause`, `probe` and
  // `seek` all do -- or null until the player has said anything. Null is
  // "unknown", never zero (D-DEAD-1): the bar and the footer show nothing
  // until there is a number. Numbers and booleans only, never a string from
  // the stream (2.1). Cleared in play() beside `paused`, because every
  // `loadfile` restarts the timeline at zero and the history with it
  // (spike 11.1, measured 10 ms after the reply).
  property var rewind: null
  // The last `seek` reply said the request was already at the floor. A
  // backward press while this holds spawns nothing: the helper would read,
  // clamp and refuse again at a process launch each, and a held key would
  // do that five times a second. Cleared by the next reply that shows room
  // for a step, by a forward or live seek, and by play().
  property bool seekAtFloor: false
  // Presses coalesce (2.3): a press while a seek is in flight, or inside the
  // 300 ms throttle after a reply, adds to this signed sum instead of
  // queueing a process. Model.coalesceSeek caps it at the last-read history
  // so a sum past the floor is never asked for. `seekLiveQueued` is the one
  // request that is not a sum: it replaces whatever was pending.
  // real, not int: the cap is the last-read history, a float, and an int
  // truncated a sub-second cap to 0 -- "queued, pending 0" and nothing run
  // (review of the integrated tree, F-RWD-17's sibling finding).
  property real seekPending: 0
  property bool seekLiveQueued: false
  // Wall seconds of the last reply that carried `rewind`, and of the moment
  // `paused` flipped true. "Behind live" holds while playing and counts up
  // only while paused, from whichever of the two is later: a reply that
  // lands mid-pause already includes the seconds paused before it.
  property int rewindAtSec: 0
  property int pausedAtSec: 0
  // The 1 Hz clock the paused count-up reads. NOT `nowSec`: that tick is
  // 30 s (epgTickMs) and re-derives every EPG fraction on the guide, so a
  // 1 Hz tick on it would re-render the whole list once a second to move
  // one number. This clock runs only while paused with a reading to count
  // from (behindTick below), so while playing nothing re-renders at all.
  property int behindTickSec: 0
  // `b back` is hinted whenever something plays and the last range read is
  // non-empty (2.5): a rewind pressed inside the first seconds of a zap
  // lands on the first keyframe and moves nothing (spike 11.1).
  readonly property bool canRewind: Model.canRewindNow({ playing: root.playing, rewind: root.rewind })
  // Seconds behind live as of now, or null while there is no zero point.
  // The composer is Model.behindLiveNow so the count-up is a function a test
  // can call (rule 12), not arithmetic in a binding.
  readonly property var behindLive: Model.behindLiveNow({
    rewind: root.rewind,
    nowSec: root.behindTickSec,
    pausedSinceSec: root.paused ? Math.max(root.rewindAtSec, root.pausedAtSec) : null
  })
  onPausedChanged: {
    if (root.paused) {
      root.pausedAtSec = Math.floor(Date.now() / 1000)
      root.behindTickSec = root.pausedAtSec
    }
  }
  // Every `seek` reply, with the helper's own verdict: `applied`, `clamped`,
  // `refused`, `atFloor`, `atEdge` and the `rewind` object (2.1). The guide
  // composes its 3 s transient from it; the service never emits a sentence.
  // The handler name on the guide side is pinned by test_pip.py's
  // signal-join test, the way pipOutcome is.
  signal seekReplied(var reply)
  // M3-02: the audio and subtitle tracks the player last reported and the
  // state of the question (idle | asking | ready | failed). `tracksQueued`
  // is a request that arrived while another control ran: the channel is
  // one-at-a-time and the panel is open and waiting, so it is issued when
  // that control returns rather than dropped.
  property var tracks: []
  property string tracksState: "idle"
  property var tracksQueued: null
  // Whether anything is still showing the tracks. Set while the picker is
  // open, so a channel change knows the difference between "throw the rows
  // away" and "ask again about the new channel".
  property bool tracksWanted: false
  // A `status` that could not be issued because the control channel was
  // busy. Drained on the next reply, like tracksQueued: the pause refusal
  // needs an answer from the player and has no other way to get one before
  // the ten-second health tick.
  property bool statusQueued: false
  // WHICH channel the rows in `tracks` describe. Freshness used to be
  // inferred from tracksState and tracks.length, and that could not survive
  // a reply in flight across a channel change: the stale reply wrote the old
  // channel's rows and flipped the state to ready, and every later gate then
  // read as "already answered". The panel showed the previous stream's
  // tracks with the new one playing, permanently, and Enter sent the old
  // stream's numbering to the new one. A stamp cannot be fooled that way.
  property string tracksFor: ""
  // The channel the in-flight request was issued for, so its reply can be
  // recognised as stale rather than trusted.
  property string tracksAsking: ""
  // The channel the last ask was issued for -- automatic or explicit, since
  // requestTracks sets it either way. Cleared when the playing channel
  // changes, when the picker closes, and when a health status shows the
  // player alive; that last one is the recovery edge, and without it a
  // single unanswered ask pinned the panel for the rest of the channel.
  // Without the stamp at all, the gate re-armed on its own `running: false`
  // reply and spawned helpers until the picker closed (D-TRK-6).
  property string tracksAskedFor: ""
  // How many times THIS channel has been re-asked after an observed-alive
  // edge. Reset when the playing channel changes and when the picker closes
  // (cancelTracks) or the rows are dropped (clearTracks) -- opening the
  // picker does NOT reset it, because opening runs requestTracks directly
  // and never consults this. The cap is Model.TRACKS_RECOVERY_MAX, so the
  // decision stays where a test can reach it (D-TRK-8).
  property int tracksRecoveries: 0
  // A new play, a stop, a death: whatever the player reported was about the
  // stream before this one. The rows go either way; whether we ask again
  // depends on whether anyone is looking.
  //
  // The re-ask is NOT issued here. nowPlaying is assigned before the helper
  // runs, so asking now reads the track list of the file still loaded and
  // reports the OLD channel's selection as the new channel's -- measured on
  // a real player: aid was 2 before the change and 1 after, while the panel
  // still said 2. The play REPLY is the first moment the loadfile is done,
  // so that is where the question goes.
  onNowPlayingChanged: {
    if (root.tracksWanted && root.nowPlaying) {
      root.tracks = []
      root.tracksFor = ""
      root.tracksAskedFor = ""
      root.tracksRecoveries = 0
      root.tracksState = "asking"
      root.tracksQueued = null
    } else {
      root.clearTracks()
    }
  }
  property var failedAt: Model.keyedMap()   // D-SG-3: keyed by channel id
  // The file behind it. Loaded on every source switch, so the marks a source
  // carries arrive with its channels and leave with it.
  readonly property string failedPath: root.activeCacheDir === ""
    ? "" : root.activeCacheDir + "/failed.json"
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
  // M5-01 ruling D10, as ONE expression (F-RWD-19). `healthBusy` is what the
  // health tick counts as a strike; `controlRunning` is the raw Qt fact, so
  // an observer can tell "nothing running" from "a seek running" -- the
  // exemption makes healthBusy false in BOTH, and a check that cannot
  // distinguish them cannot go red for a missing exemption (F-RWD-18).
  readonly property bool controlRunning: controlProc.running
  readonly property bool healthBusy: Model.healthBusy({ running: controlProc.running, kind: root.controlKind })
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
  // D-SRC-15 (R9, R11). The three facts that say whether state.json on disk
  // is OLDER than memory, read by Model.reloadDisposition before any reload
  // is applied and by Model.entryFlushDisposition before the held entry
  // mirror is written: whether a save is PENDING (issued, and the
  // FileView has not yet reported on THAT text -- Model.stateSaveLanded,
  // read by content and not by counting `saved` signals, which a burst of
  // writes coalesces: R13, measured 2026-10-12), whether the last write
  // failed, and whether the helper's start-up `state init` exited 0.
  // `stateSavesInFlight` is 0 or 1 and keeps its name for the harness.
  property int stateSavesInFlight: 0
  property string lastSaveText: ""
  // D-SINK-19 round 11, R21a. The state the last LANDED save serialised (or
  // the file as it was loaded): what the plugin's own disk is known to hold.
  // The ONE question asked of it is whether it carries the migration marker
  // (Model.entryMigratedOf): until it does the bar entry's URLs are migration
  // inputs and no owned write may take them off (Model.retiredInputsToKeep),
  // and from then on they are refused. Memory is not asked, because memory
  // carries the marker from the moment the migration runs and a write that
  // fails leaves the disk without it. null before the first load.
  // `lastSaveState` is the object behind lastSaveText, promoted when that
  // text lands.
  property var landedState: null
  property var lastSaveState: null
  property bool stateSaveFailed: false
  property bool stateInitOk: false
  property int stateReloadsIgnored: 0                   // observable by the harness; never a URL
  // R15: the same reloads counted BY REASON -- one number per reason
  // Model.reloadDisposition answers, applied and ignored alike, keyed by the
  // reason string (Model.countReload). Never a URL. The harness reads it as
  // pointerState's `stateReloadsByReason`; the plain total above could not
  // go red for the start-up chmod reload because the own-write echo after
  // every start satisfied it.
  property var stateReloadsByReason: ({})
  // D-SINK-19 round 12, R22a. A STATE THAT DID NOT LOAD IS NEVER WRITTEN.
  // `stateLoadKind` is Model.stateLoadKind of the latest load ("" before the
  // first): "loaded", "absent", "permission", "not-a-file", "io-error" or
  // "unparsed". `stateInitFound` is the start-up `state init`'s verdict on
  // the path BEFORE it touched anything (Model.stateInitFound; "" until it
  // exits), the one witness that tells a missing file from an unreadable
  // directory -- FileView reports both as FileNotFound (measured, see
  // Model.STATE_LOAD_ERRORS). `stateWriteBlocked` is the no-write mode: ""
  // while writes are allowed, else the reason; every state write and every
  // owned entry write is refused while it is set, the migration does not
  // run, and a later load that IS a state lifts it. `stateBlockTold` makes
  // the notice once per episode; `stateWritesRefused` counts the refusals
  // for the harness. None of them ever holds a URL.
  property string stateLoadKind: ""
  property string stateInitFound: ""
  property bool stateLoadRetried: false
  property string stateWriteBlocked: ""
  property bool stateBlockTold: false
  // R23c: set by stateInitWatchdog when it terminates the init; read once,
  // by the init's exit (Model.stateInitFound answers "timeout").
  property bool stateInitTimedOut: false
  property int stateWritesRefused: 0
  // D-SINK-19 R26a (2026-10-16): READ BEFORE WRITE, asynchronously. A save
  // the gate allows first reloads state.json and is decided on what that
  // load finds, through the dispositions every load already goes through:
  // the base is written over, a foreign text is merged (R24a) and then
  // written, a load that is not a state blocks (R22) and nothing is
  // written. The FileView's watch is lost, WITHOUT a signal, when the path
  // is replaced or re-pointed (a rename over a link, `sed -i`, rm and copy,
  // `ln -sfn` to another file or to another folder: measured,
  // spikes/filewatch-links), so the save was the first time the session
  // learned of it and it wrote memory over another file, or created a 0644
  // state.json in an empty folder (D-SINK-21). Model.stateSavePlan decides
  // each save; Service.saveState carries it out.
  // `stateVerifyPending`: the reload is out and the save waits for its
  // load. `stateVerifyDone`: the save issued by that load's finish (no
  // second read). `stateInHandler`: the depth inside stateFile's own
  // handlers (R26b). `stateWriteTurn`: saveState called from a turn of its
  // own (Qt.callLater). The counters are for the harness: verifies
  // finished, watchdog finishes (no load in stateVerifyWatchdog's 2 s),
  // reads skipped for a write in flight, re-reads of a liftable no-write
  // mode, saves deferred to a turn of their own, and the slowest read.
  property bool stateVerifyPending: false
  property bool stateVerifyDone: false
  property int stateInHandler: 0
  property bool stateWriteTurn: false
  property double stateVerifyAt: 0
  property int stateVerifies: 0
  property int stateVerifyNoLoad: 0
  property int stateVerifySkipped: 0
  property int stateVerifyRetries: 0
  property int stateSavesDeferred: 0
  property double stateVerifyMsMax: 0
  // R27a (D-SINK-22, window a). `stateWriteWaiting`: a save asked while our
  // previous write is in flight is HELD for that write to land, then reads;
  // before R27 it skipped its read. The counters are the harness's and the
  // measurement's: saves that met the wait (every call, so a burst's
  // coalescing is a ratio of these to the writes), wait episodes, waits the
  // write never answered within stateWriteWaitWatchdog's bound, writes
  // issued, and the longest wait. None of them ever holds a URL.
  // R29a (2026-10-20, the lead's ruling): the read before a save is bounded
  // as R26a bounded it, and only so -- R27a's window-c second read and the
  // no-write mode it led to, and R28a's held save past the bound with its
  // schedule, re-reads and notice, are withdrawn (finishStateVerify).
  // R27d (D-SRC-44): this session's one-time migration found Sources full
  // and did not run (it never evicts); told once. Booleans, never a URL.
  property bool migrationHeldFull: false
  property bool migrationFullTold: false
  // F1: the key of the record this session's migration added ("" when it
  // added none), so a merge that drops that record at the cap holds the
  // migration again rather than landing its marker (Model.mergeForeignState).
  // A source key, never a URL.
  property string migrationAddedKey: ""
  property bool stateWriteWaiting: false
  property bool stateWriteWaitExpired: false
  property double stateWriteWaitAt: 0
  property int stateSavesWaited: 0
  property int stateWriteWaits: 0
  property int stateWriteWaitTimeouts: 0
  property int stateWritesIssued: 0
  property double stateWriteWaitMsMax: 0
  // R5: the key whose entry mirror is WAITING for a parked state save
  // (Model.pointerWritePlan "wait-entry"); null when nothing waits. Written
  // by settleEntryFlush once that save has LANDED (R11), never before it.
  property var pendingEntryKey: null
  // D-SINK-18. What the last `config shield` run said about the file the host
  // persists our source URLs into: Model.CONFIG_SHIELD_UNKNOWN ("") until the
  // first run exits, then "private" or "exposed" for ever after -- a RE-check
  // never puts it back to unknown, because the previous answer still holds
  // until a new one contradicts it, and resetting it would make every persist
  // defer behind a re-check it did not need to wait for.
  property string hostConfigShield: Model.CONFIG_SHIELD_UNKNOWN
  // The one deferred persist, held while the first shield run is in flight.
  // One slot, collapsed to the LAST intent for the same reason persistFailed
  // collapses: replaying an older pair would write back a source the user has
  // already moved off. { playlistUrl, epgUrl } or null.
  property var pendingPersist: null
  property bool configShieldRerun: false
  // Which persist failure happened last. Since R13 no source call returns
  // it (a refused entry mirror is logged, not reported, SR25 as amended
  // 2026-10-12); it is kept as the one record of the LAST failure for the
  // harness and for a reader of the log: "persist_failed" (no writable bar
  // entry), "config_unsafe" (the host settings file could not be made
  // private, D-SINK-18) or "state_write_failed" (the plugin's own state.json
  // could not be written, which is the failure the guide now reports).
  // The distinction is worth carrying because the sentences give opposite
  // advice -- persist_failed sends the user to `omarchy bar set`, which is
  // precisely what must not happen with a credentialed URL.
  property string lastPersistFailure: "persist_failed"
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
  property var entryOwners: Model.keyedMap()
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
  // D-SINK-16: this shell adopted a player that was not verifying the stream's
  // certificate, the probe has migrated it, and the channel it is already
  // streaming must be re-established before anything else is sent to it. Set
  // from the probe's verdict, never cleared by it (an ambiguous first probe
  // migrates and the retry then has nothing to report), and spent by
  // reestablishForTls().
  property bool tlsReloadPending: false
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
  // The channel of the most recent failure. The guide reads it to decide
  // whether an open is "come back after a dead stream" or a fresh start
  // (UX 1.3). Distinct from `failedAt`, which is every mark ever: this is
  // the ONE that just happened, and a new play clears it.
  property string lastFailedId: ""
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

  // ---- picture in picture (M2-05, M2-05-PICTURE-IN-PICTURE.md (dev branch))
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
  // Both constants are Model's, not copies of them: the class is the one
  // buildMpvArgv launches the player with and the tag is the one the plan
  // dispatches, and a second spelling of either here would be a rule written
  // twice that nothing compares (engineering rule 12 (dev branch)).
  readonly property string pipClass: Model.PIP_CLASS
  readonly property string pipTag: Model.PIP_TAG
  // The window-owning mpv pid, from `player probe` and from `player start`.
  // Addressing by class ALONE is a defect, not a shortcut: a user's own
  // `mpv --wayland-app-id=omarchy-iptv` reproduces as a second client
  // (QA-PLAYER PLY-RST-11), and floating, shrinking and pinning a stranger's
  // window is damage. 0 means "we do not know", and PiP refuses.
  property int playerPid: 0
  // hyprctl on PATH, a live instance signature (G-8) AND a compositor that
  // speaks the one dispatch spelling this plugin builds (PIP15, below).
  property bool pipAvailable: false
  // WHICH configuration provider the compositor runs, read once from
  // `hyprctl systeminfo`. PIP15: the spelling is chosen from that answer and
  // from nothing else. There is no second spelling to fall back to - under a
  // Lua provider the legacy dispatcher form is a Lua SYNTAX error (G-1), and
  // an exit code could not tell us to retry anyway (PIP11) - so a provider
  // this plugin cannot address takes PiP off the offer here, at the one
  // moment we can say so, rather than dispatching strings the compositor
  // will not parse and reporting `dispatch_failed` fifteen seconds later.
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
  // D-PIP-4 / 4.7 step 3. One read in flight OUTSIDE a request, so the state
  // this plugin reports can be re-derived the moment a player becomes ours.
  // The bound that makes it safe to fire from three places at once, and the
  // reason Model.pipDeriveGate has a `reading` clause.
  property bool pipPeeking: false
  // D-PIP-5. The same read answers "which window is ours?", which is what
  // focus needs and never had: the class-only selector it used focused a
  // stranger's window of the same app id three times out of three.
  property bool pipFocusPending: false
  // Bounds (parallel rule 3 (dev branch)). At most 3 rounds of at most
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
  // between; the helper's `find_player` finds the same process by its argv.
  // Taken over the player's own private socket rather than out of a helper
  // reply, because that one connection covers all three ways a player
  // becomes ours - a cold start, a respawn, and a reattach after
  // `omarchy restart shell` - through a single seam.
  readonly property int pipPidRequestId: 4

  // The outcome of one PiP request: { ok, requested, state: "on"|"off",
  // code, error: { code } }, where `code` is one of Model.pipStatusText's
  // six and everything else is diagnosis. Emitted once per request - for a
  // sequence that ran, after it has been VERIFIED against the compositor,
  // and for a refusal that never started, immediately.
  //
  // The guide turns `code` into its footer line through Model.pipStatusText;
  // this service never emits a user-facing sentence. The handler name on the
  // other side of this signal is pinned by test_pip.py (dev branch tests), because a
  // Connections block with `ignoreUnknownSignals` set silently listens for a
  // signal that does not exist - which is how the guide's footer was wired
  // to nothing at all until integration.
  signal pipOutcome(var result)

  // Emitted after a successful playlist helper run; the guide shows
  // `Refreshed - N channels` for a manual refresh (UX 6.1, D-LIVE-05).
  signal playlistRefreshed(int channelCount, bool manual)

  // ---- sources signals (SR3). Payloads are URL-free: `reason` comes from
  // Model.statusReason, `host` from the validator.
  //   sourceProbeFinished({ ok, id, channelCount, groupCount, reason, host,
  //                         cancelled, replacedId, code? }) after an add / URL edit /
  //     never-fetched switch / retry probe; on ok the switch is committed.
  //   sourceSwitched(id) once the new source's cache (or its absence) is in
  //     `channels`. sourceRemoved(id). sourcesPersistFailed(reason) when
  //     the plugin's own state.json could not be written
  //     ("state_write_failed", R13: the state write is the switch, so this
  //     is the failure a switch, a remove or an adoption can have) or the
  //     host settings file could not be made private ("config_unsafe",
  //     D-SINK-18, reachable only through a URL-bearing patch, which no
  //     shipping write composes). "persist_failed" -- a bar entry
  //     updateEntryInline cannot rewrite -- is raised by writeOwnedEntry
  //     ONLY for a caller that does not pass `announce` false, and BOTH
  //     callers pass it (writeActive, setShowLogos): a refused KEY mirror is
  //     logged and repaired on the next start, and a refused logo write
  //     reports through its return value, which the guide renders itself
  //     (SR25 as amended 2026-10-12; the round-4 review's DQ-C7). The reason
  //     set is Model.PERSIST_FAILURE_REASONS and the guide renders the
  //     sentence for THE reason it is handed (Model.persistFailureMessage).
  signal sourceProbeFinished(var result)
  signal sourceSwitched(string id)
  signal sourceRemoved(string id)
  signal sourcesPersistFailed(string reason)
  // Answer to requestClipboard() (D9; the ONLY paste path since D-CLIP-1):
  // the raw clipboard text for the guide to sanitize; never logged. Emitted
  // only when the helper's `clipboard` verb answered ok -- a failure code,
  // a malformed line or a watchdog kill answers nothing, so a paste can
  // never clear a field by accident.
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
    // A new play is never paused: the flag belongs to the stream that was
    // playing, and carrying it over would show a pause nobody asked for.
    root.paused = false
    // M5-01: and it has no history. Every loadfile empties the cache and
    // restarts the timeline at zero (spike 11.1), so the readout goes absent
    // -- not to zero -- until the player reports again, and a seek that was
    // waiting its turn was aimed at the stream this play replaces.
    root.clearRewind()
    // D-SINK-16: and it subsumes a reload owed for the channel this play
    // replaces. The load about to go out asserts the same properties and
    // refuses rather than loads, so re-establishing the old channel afterwards
    // would buy a second rebuffer and nothing else.
    root.tlsReloadPending = false
    // A new play puts the last failure behind us: the next guide open is a
    // fresh start, not a come-back.
    root.lastFailedId = ""
    if (Model.hasOwnKey(root.failedAt, key)) {
      root.failedAt = Model.withoutFailed(root.failedAt, key)
      root.persistFailed("clear", key)
    }
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
  // Model.zapArgs (engineering rule 12 (dev branch)) - it was the one argv builder still spelled
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
    // M5-01: the history goes with the player; a press queued behind the
    // stop has nothing to seek in.
    root.clearRewind()
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

  // M3-01: hide or unhide a group by name. Returns whether it is hidden
  // NOW, or null when the reducer refused (the cap) and nothing was written.
  function toggleHiddenGroup(name) {
    var next = Model.toggleHiddenGroup(root.userState, name)
    if (next === root.userState) return null
    root.userState = next
    root.saveState()
    return Model.isGroupHidden(root.userState, name)
  }

  // Save the current search into Favourites. Returns the verdict the guide
  // shows, so a refusal (empty, already saved, at the cap) is visible in the
  // moment rather than being a keystroke that appears to do nothing.
  function saveSearch(query) {
    var result = Model.withSavedSearch(root.userState, query, Math.floor(Date.now() / 1000))
    if (result.added) {
      root.userState = result.state
      root.saveState()
    }
    return { added: result.added, reason: result.reason }
  }

  function forgetSearch(query) {
    root.userState = Model.withoutSavedSearch(root.userState, query)
    root.saveState()
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
  // Zapping steps PAST channels already known to be dead. One wheel flick
  // calls this up to three times, so on a list where roughly one in eight is
  // dead a single flick could hand the user two black screens and two failure
  // toasts. Bounded, never empty-handed, and it reports what it skipped --
  // see Model.zapStep for why each of those is a refusal of a mistake.
  //
  // `zapSkipped` is what the last zap stepped over, so the bar and the guide
  // can say so rather than silently walking past rows the user can see.
  property int zapSkipped: 0
  // Raised when a zap stepped over something, with the words to show. The
  // guide renders it; the bar has no transient surface, so a wheel zap is
  // reported the next time the guide is opened via the row's own mark.
  signal zapSkippedDead(string text)

  function zap(delta) {
    if (!root.nowPlaying) return false
    var ring = Model.zapRing(root.channels, root.userState, root.nowPlaying)
    var hop = Model.zapStep(ring, root.nowPlaying.id, delta, root.failedAt)
    if (!hop.channel) return false
    root.zapSkipped = hop.skipped
    // Say so. Skipping rows the user can see without telling them would be
    // the guide lying about state (UX principle 4) -- and an unwired notice
    // is exactly what the 0.7.10 preflight caught: the composer existed, the
    // property was set, and nothing ever read either of them.
    if (hop.skipped > 0) root.zapSkippedDead(Model.zapSkipNotice(hop.skipped))
    return root.play(Model.channelId(hop.channel), true, root.nowPlaying.launchedFrom)
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
  // same path the CLI does instead of a copy of it (engineering rule 12 (dev branch)).
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

  // D-PIP-5. Focus is read-then-act now, like every other window command
  // this plugin issues. The D-PIP-1 repair fixed the spelling and kept the
  // selector, which was `class:omarchy-iptv`; with a user's own
  // `mpv --wayland-app-id=omarchy-iptv` open, the live pass watched it focus
  // the STRANGER'S window three times out of three. Design 4.2 had already
  // ruled that narrowing by pid is not optional - focus was the one verb
  // nobody applied it to.
  //
  // So there is nothing to dispatch until the compositor has been asked
  // which window is ours, and the focus retry timer (UX 7.5) was built for
  // exactly that wait: the mpv window maps a moment after launch. mpv binds
  // its IPC socket before the video output creates a surface, so the pid is
  // known by the time there is a window to aim at, and an attempt made
  // before then simply resolves nothing and retries.
  function focusPlayer() {
    // A read already in flight answers this one too. Anything else the gate
    // refuses - no pid, a PiP sequence in progress - means there is nothing
    // coming and nothing to aim at, so the intent is dropped rather than
    // held forever.
    if (root.pipPeek() || root.pipPeeking) {
      root.pipFocusPending = true
      return true
    }
    root.pipFocusPending = false
    return false
  }

  // The one place a focus command leaves this plugin. `address` came out of
  // the pid-narrowed lookup; the builder checks it again against the address
  // pattern (PIP7) and answers [] rather than a guess, so an empty vector
  // means "we cannot say which window", never "focus whatever matches".
  function dispatchFocus(address) {
    var argv = Model.focusPlayerArgv(address)
    if (argv.length === 0) return false
    Quickshell.execDetached(argv)
    // The retry loop (UX 7.5) exists because the mpv window maps a moment
    // after launch and a focus dispatched before then reaches nothing. We
    // only get here with a window the compositor listed a few milliseconds
    // ago, so this one lands and there is nothing left to retry. Before
    // D-PIP-5 nothing could know that, and the loop dispatched its whole
    // budget every time.
    root.wantFocus = false
    root.focusAttempts = 0
    focusTimer.stop()
    return true
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
      return root.pipRefuse(want, "bad_mode")
    // The same function the guide's `p` key asks before it calls in at all
    // (Model.pipKeyRequest), so the two surfaces cannot drift into refusing
    // for different reasons or in different words. The guide answers what it
    // can see; this is the authority, because only the service knows whether
    // the player's pid is known. PiP never starts a player (4.10), and
    // "nothing playing" covers a player whose pid we do not have, because
    // addressing by class alone is the one thing this feature must not do.
    var gate = Model.pipKeyRequest({ available: root.pipAvailable,
                                     playing: root.playing && root.playerPid > 0 })
    if (!gate.ok) return root.pipRefuse(want, gate.code)
    if (root.pipBusy)
      return root.pipRefuse(want, "busy")
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

  // A request that never started. The answer goes back to the caller AND out
  // on pipOutcome, so the guide's footer says the same thing whether the
  // refusal was decided here or fifteen steps later - `bad_mode` and `busy`
  // have no line in Model.pipStatusText and so say nothing, which is right:
  // a second `p` while the first is still applying is not news.
  function pipRefuse(requested, code) {
    var result = { ok: false, kind: "pip", requested: requested,
                   state: root.pipOn ? "on" : "off", code: String(code),
                   error: { code: String(code) } }
    root.pipOutcome(result)
    return result
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
    var live = Model.pipFindWindow(text, root.playerPid, root.pipClass)
    if (!live.ok) {
      // Garbage, no match, or more than one match. Never act on a guess.
      root.pipFinish(false, String(live.reason || "no_window"))
      return
    }
    root.pipLive = live
    if (root.pipPhase === "resolve") {
      // The answer to "am I in PiP?" is read out of the compositor, not out
      // of a boolean this shell may not even have been alive to set (4.7),
      // and the mode is resolved against that same read by the same function
      // the model's own tests drive.
      root.pipOn = Model.pipActive(live)
      root.pipIntent = Model.pipResolveIntent(root.pipMode, live)
      if (root.pipIntent === "on") {
        // What the window WAS. Written to the player before the first
        // dispatch, so a shell that dies mid-sequence still leaves something
        // that knows how to put the window back. NOT rewritten when PiP is
        // already on: `pip on` twice must not overwrite the restore point
        // with the PiP box's own rectangle.
        if (!root.pipOn) root.pipWriteMpv("on", live)
        root.pipPhase = "monitors"
        root.pipReadMonitors()
        return
      }
      // The tag is what says "we did this to this window" (design 4.8). A
      // window the user floated and pinned themselves with SUPER+O carries
      // none, so `pip off` has nothing of ours to undo and must not drag it
      // back to a rectangle out of a stale snapshot - or, worse, resize a
      // TILED window, which changes the split ratio of the user's layout.
      if (!Model.pipHasTag(live)) {
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
    var monitor = Model.pipFindMonitor(text, live ? live.monitor : -1)
    var geom = monitor ? Model.pipGeometry(monitor, Model.pipOptions(root.pipConfig())) : null
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
    var plan = Model.pipPlan(root.pipLive, root.pipSnapshot, root.pipGeom, root.pipIntent)
    if (!plan || plan.length === 0) {
      if (root.pipRound > 1) {
        root.pipOn = Model.pipActive(root.pipLive)
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
    // Model.pipDispatchAccepted reads the reply as a KEYWORD - the
    // compositor prints exactly `ok`, and a refusal arrives as
    // `warning: ...` with rc 0 - so it is the cheap first filter and
    // nothing more. Asking it here rather than re-testing the text with a
    // regex of our own keeps "what does the compositor's reply mean" in one
    // place.
    if (line !== "" && !Model.pipDispatchAccepted(line)) {
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

  // The single definition of success in this feature. What was ASKED FOR is
  // the geometry on the way in and the snapshot on the way out, and
  // Model.pipVerify compares a fresh read against it field by field.
  function pipCheck(live) {
    var expected = root.pipIntent === "off" ? root.pipSnapshot : root.pipGeom
    var verdict = Model.pipVerify(live, root.pipIntent, expected)
    if (verdict.ok) {
      root.pipOn = root.pipIntent === "on"
      root.pipFinish(true, "")
      return
    }
    if (root.pipRound >= root.pipMaxRounds) {
      // Stop, leave the window as it is, and say so. A half-applied PiP is
      // visible, and the next `p` reads this same live state and either
      // finishes it or undoes it (design 4.10).
      root.pipOn = Model.pipActive(live)
      // The mismatch the readback found, for the journal. It is a field
      // name from a fixed set, never compositor text and never a value.
      console.warn("omarchy-iptv pip: the window did not reach the requested state ("
                   + String(verdict.reason || "unknown") + ")")
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
    // One of the six codes section 5 gives copy for, decided by
    // Model.pipResultCode from the verdict - so the guide renders a line
    // this service never composed, and a failure reason the model does not
    // recognise becomes `dispatch_failed` rather than leaking a raw
    // compositor word into the footer.
    var result = { ok: ok, kind: "pip", requested: requested,
                   state: root.pipOn ? "on" : "off",
                   code: Model.pipResultCode({ ok: ok, reason: root.pipReason }, intent) }
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
    // Nothing left to focus either: the window went with the process, and a
    // pending focus would be aimed at an address that no longer exists.
    root.pipFocusPending = false
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
    // A pid we did not have is the first moment the window can be found at
    // all, so it is the first moment the question in 4.7 step 3 can be
    // answered. On the reattach path this runs before the socket is even
    // armed, which is why the restart case is covered twice over.
    root.pipPeek()
  }

  // ---- what picture in picture IS, asked of the compositor (4.7, D-PIP-4)
  //
  // A request re-reads the window before it plans, which is why `p` kept
  // working across `omarchy restart shell`. This is the other half: the same
  // read, taken once when a player becomes ours, so that what the plugin
  // REPORTS follows the window too. Before it, `status.pip.on` answered
  // false on 30 consecutive samples with the box demonstrably in the corner,
  // the bar tooltip never gained its line, and an accepted request replied
  // `"was":false`.
  //
  // Nothing here remembers anything: the decision is Model.pipDeriveState,
  // which is given the compositor's own bytes and no previous value at all.
  function pipPeek() {
    var gate = Model.pipDeriveGate({ pid: root.playerPid, busy: root.pipBusy, reading: root.pipPeeking })
    if (!gate.ok) return false
    root.pipPeeking = true
    hyprPeekProc.running = true
    pipPeekWatchdog.restart()
    return true
  }

  // The read came back. A request that started in the meantime owns the
  // answer - its read is fresher and it is about to verify it - so this
  // stands down rather than overwriting a verified state with an older one.
  function pipApplyPeek(text) {
    pipPeekWatchdog.stop()
    root.pipPeeking = false
    var wantedFocus = root.pipFocusPending
    root.pipFocusPending = false
    var derived = Model.pipDeriveState(text, root.playerPid, root.pipClass)
    // `decided` false means the read could not see OUR window: garbage, no
    // match, or two matches. Saying "off" on the strength of that would be
    // the same defect pointing the other way, so nothing is written. A
    // request that started in the meantime owns the answer too - its read is
    // fresher and it is about to verify it.
    if (derived.decided && !root.pipBusy) root.pipOn = derived.on
    // D-PIP-5: focus the window this read RESOLVED. An undecided read leaves
    // the address empty, the builder refuses it, and nothing is dispatched -
    // which is the honest answer when we cannot say which window we mean.
    if (wantedFocus && derived.decided) root.dispatchFocus(derived.address)
  }

  // The two mpv-side writes (4.6). Both go over the socket the service
  // already holds; a dead socket answers false and that is recorded, never
  // fatal - the compositor half is what PiP actually is.
  function pipWriteMpv(intent, live) {
    // Kept in memory too, so an exit in the same session does not depend on
    // a round trip; the player's copy is what survives a shell restart. Set
    // BEFORE the write, because the write can fail and the compositor half
    // still applies - the snapshot must describe what we are about to do
    // either way. The "off" case does NOT clear it here: Model.pipPlan and
    // Model.pipVerify are both still to read it; pipFinish clears it.
    //
    // Model.pipMpvCommands derives the snapshot from the same live read, so
    // what goes into the player and what stays in memory are one function's
    // output rather than two that could drift.
    if (intent === "on") root.pipSnapshot = Model.pipSnapshotFor(live)
    var sock = root.playerSocket
    if (!root.socketAttached()) return false
    var commands = Model.pipMpvCommands(intent, { live: live, mpvArgs: root.mpvArgs })
    for (var i = 0; i < commands.length; i++) root.socketWrite(sock, commands[i], 0)
    if (sock.flush) sock.flush()
    return true
  }

  // Read the snapshot back out of the surviving player. Needed in exactly one
  // case - the shell restarted while in PiP and the user then exits - so it
  // is one get_property issued from onPlayerAttached, and a failure degrades
  // to "unpin and unfloat", never to stuck (4.5, 4.7).
  function pipRequestSnapshot(sock) {
    root.socketWrite(sock, ["get_property", Model.PIP_SNAPSHOT_KEY], root.pipSnapshotRequestId)
    root.socketWrite(sock, ["get_property", "pid"], root.pipPidRequestId)
  }

  // Our own replies on the player socket, routed by request id. Returns true
  // when the line was ours, so the event router never sees it.
  function pipNoteReply(line) {
    var reply = Model.parsePlayerReply(line)
    if (!reply) return false
    if (reply.requestId === root.pipSnapshotRequestId) {
      root.pipSnapshot = reply.ok ? Model.pipParseSnapshot(reply.data) : null
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
  // The URLs are read directly, never through the derived `configured` /
  // `epgConfigured` bindings: from on<Url>Changed those may not have been
  // re-evaluated yet, which is what kept an epgUrl set at runtime from ever
  // loading (D-LIVE-02). Since D-SINK-19 `playlistUrl` is the ACTIVE
  // RECORD's URL rather than the bar entry's; the rule is the same and so is
  // the reason for it.
  function refreshPlaylist(force) {
    if (root.playlistUrl === "") return
    if (playlistProc.running) {
      if (force) root.playlistRerun = true
      return
    }
    refreshDebounce.restart()
  }

  function refreshEpg(force) {
    // M4-01 repair 3: the RESOLVED URL, so a playlist-declared guide fetches
    // like a typed one. Read directly and never through `epgConfigured`, for
    // the reason D-LIVE-02 recorded above.
    if (root.epgFetchUrl === "") return
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
      // D-HOST-2. The stale-build notice has never been observed to fire, and
      // the only way anyone tried to observe it was by measuring the pixel
      // width of a footer line. That is not an instrument. These three make it
      // a value: what the RUNNING component believes it is, what is on disk
      // beside it, and the verdict the footer reads. Version strings carry no
      // credential and no path, so this adds nothing to the redaction surface.
      paused: root.paused,
      // M5-01: the last `rewind` object the player reported, or null until
      // it has (2.1, 2.2). Numbers and booleans only; nothing in it is a
      // string from the stream, so it adds nothing to the redaction surface.
      rewind: root.rewind,
      behindLive: root.behindLive,
      // D-LOGO-8: how many logos the shell currently knows are on disk. It
      // exists so the streaming fix can be OBSERVED rather than inferred --
      // the defect was precisely that this number stayed 0 until the fetch
      // exited, and nothing outside the guide could see that.
      logos: Model.logoHaveCount(root.logoHave),
      build: {
        running: Model.PLUGIN_VERSION,
        onDisk: root.onDiskVersion,
        stale: root.staleBuild
      },
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
  // busy, unknown_source, not_ready. persist_failed and config_unsafe
  // (D-SINK-18) are no longer returned by any call since R13: a source call
  // reports on the state write being issued, and a refused entry mirror is
  // logged. Messages are Model.sourceErrorMessage sentences. Asynchronous
  // outcomes arrive through sourceProbeFinished and sourcesPersistFailed.

  function sourceResult(ok, code, message, id, field) {
    var out = { ok: ok, code: code, message: message || "", id: id || "" }
    if (field) out.field = field
    return out
  }

  // `persistFailureResult` USED TO BE HERE (D-SINK-18): the result for a
  // refused entry write, returned by removeSource. Gone with R13 / SR25 as
  // amended: a source call reports on the STATE write, which is issued
  // synchronously and cannot be refused, and a refused entry mirror is
  // logged and repaired on the next start. The failure a source call can
  // still have is the state write failing later, which stateFile's
  // saveFailed reports through sourcesPersistFailed("state_write_failed").

  function sourcesReady() {
    // R22a: refused, not made in memory only -- nothing made now would be kept.
    // R26a (D-SRC-35): and one reload asked for, so a file that is back lifts
    // the mode for the NEXT call (this one is refused either way, R26e).
    root.recheckStateBlock()
    if (root.stateWriteBlocked !== "") return root.sourceResult(false, "state_unreadable", Model.sourceErrorMessage("state_unreadable"), "")
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
      // M2-09 GS11: the other half of "a cleared guide URL takes its cache
      // with it". The ACTIVE source reaches that through onActiveEpgUrlChanged
      // below, which also catches a change made from outside the plugin; this
      // is an INACTIVE source edited in the Sources form, where activeEpgUrl
      // never moves and nothing else would notice the file is now an orphan.
      if (key !== root.activeSourceKey && String(rec.epgUrl || "") !== "" && next && String(next.epgUrl || "") === "") {
        root.queueCacheJob(["epg-clear", "--key", key], null)
      }
      // D-SINK-19: an EPG URL edit of the ACTIVE source used to be copied
      // into the bar entry here, because that entry was where the active
      // source's guide URL lived. The record is the only place now, and
      // `activeEpgUrl` reads it, so the state write above IS the persist and
      // there is nothing to carry into the host's file. One fewer write, and
      // one fewer URL in a file this plugin does not own.
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
    root.recheckStateBlock()
    if (root.stateWriteBlocked !== "") return root.sourceResult(false, "state_unreadable", Model.sourceErrorMessage("state_unreadable"), key)
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
    // D-SINK-19: clearing the pointer. The state write IS the removal, and
    // this reports on it being ISSUED (R13; its failure, if any, arrives
    // through stateFile's saveFailed as sourcesPersistFailed with its own
    // reason). Only the entry mirror can be refused, and a stale mirror
    // naming a record that is gone resolves to "no active source"
    // (Model.adoptActiveSource step 3 requires the key to name a record, and
    // Model.removeSource itself clears the pointer in the state it returns,
    // R3), so a refused mirror is logged and repaired on the next start
    // (SR25 as amended 2026-10-12), never reported as the removal failing.
    if (wasActive && !root.persistActive("")) {
      console.warn("omarchy-iptv: removed the active source but could not mirror the cleared key into the bar entry")
    }
    root.sourceRemoved(key)
    // R27d: a migration held because Sources was full runs now there is room
    // -- deferred, after the removal's own save has been asked for.
    if (root.migrationHeldFull) Qt.callLater(root.retryHeldMigration)
    return root.sourceResult(true, "ok", "", key)
  }

  // R27d: one function rather than a closure, so Qt.callLater folds a burst
  // of removals into one reconcile.
  function retryHeldMigration() { if (root.migrationHeldFull) root.reconcile(true) }

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
    // beginSwitch BEFORE the active key moves: assigning it fans out through
    // activeSourceKey -> activeCacheDir -> onActiveCacheDirChanged in the same
    // turn, and that handler can call finishSwitch.
    root.beginSwitch()
    // D-SINK-19: persistActive writes the active key into the state (which is
    // what every binding in this service reads, so the switch happens in this
    // turn) and then mirrors it into the host entry.
    if (!root.persistActive(key)) {
      // The entry mirror failed; the switch itself has already happened.
      // Report it and let the switch finish, rather than aborting a change
      // that is already in our own state file.
      console.warn("omarchy-iptv: switched source but could not mirror the key into the bar entry")
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

  // The paste path (D9; the only one since D-CLIP-1; Guide.qml pasteInto):
  // the helper's `clipboard` verb as argv (R8), which runs wl-paste with a
  // pipe, reads at most Model.CLIPBOARD_MAX_BYTES and terminates it at the
  // cap, EOF or its own deadline; the reply is one JSON line, parsed by
  // Model.parseClipboardReply, the text back through clipboardText(text),
  // never logged. The helper is the process allowed to hold the bytes
  // briefly and die; this one holds only the bounded reply. The shell
  // process itself never asks Qt. clipboardWatchdog is the outer bound.
  function requestClipboard() {
    if (clipboardProc.running) return false
    clipboardProc.command = Model.clipboardArgv(root.helperPath)
    clipboardProc.running = true
    clipboardWatchdog.restart()
    return true
  }

  // ------------------------------------------------------------ internals

  // `source` is the cache directory the text was read from (D-PERF-4: the
  // LRU holds one entry per source, so a refresh replaces its own slot).
  function applyChannels(text, source) {
    var t0 = Date.now()
    root.switchReadMs = root.switching ? t0 - root.switchStartedAt : 0
    var lru = root.preparedLru
    var prepared = Model.preparedLruFind(lru, text, source)
    if (!prepared) {
      var parsed = Model.parseChannels(text)
      var channels = parsed.ok ? Model.prepareChannels(parsed.channels) : []
      prepared = { text: text, source: String(source || ""), channels: channels, channelIndex: Model.indexById(channels),
                   chnoIndex: Model.buildChnoIndex(channels), channelsMeta: parsed.meta,
                   // D-ID-3. The scheme-1 -> scheme-2 map of THIS list, computed
                   // once here where the O(n) parse is already paid: it hashes
                   // every URL and folds every name, tens of milliseconds on 10,000 rows in
                   // node, which no LRU hit inside the 150 ms switch budget can
                   // afford. The map depends on the channels alone; what it is
                   // applied to (the state) is decided at apply time below.
                   idRemap: Model.channelIdRemap(channels) }
    }
    if (text !== "" && prepared.channels.length > 0) root.preparedLru = Model.preparedLruNext(lru, prepared, root.preparedLruSize)
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
    root.adoptIdScheme(prepared.idRemap)
    // A now-playing recovered from the player's stash resolves against the
    // cache the moment it lands (4.5); until then it is name-only.
    root.reconcileNowPlaying()
    // And D-SINK-16's reload needs the same arrival: the helper resolves the id
    // against this cache directory, which the reattach ran before.
    root.reestablishForTls()
  }

  // D-ID-3. Move the loaded state onto the id scheme of the channel set that
  // was just applied. The helper does the same to state.json when the active
  // fetch carries --state-dir (D-ID-1), but this service then wrote the state
  // it had loaded BEFORE the helper ran straight back over that file
  // (handlePlaylistExit -> applyPlaylistStatus -> adoptSourceStats ->
  // saveState), on the same fetch, every time observed
  // (QA-HEADLESS-2026-09-21.md on the dev branch, section 1): the rewrite reaches
  // neither memory nor, for longer than its own write, disk. Remapping the
  // in-memory state against every applied list makes this service's writes
  // agree with the helper's, so the order of the two writers stops mattering.
  // Idempotent: scheme 2 is a substitution (Model.channelIdRemap), so after
  // one pass no reference is a key of the map, `moved` is 0 and nothing is
  // written; a list on another scheme-1 vintage (a rotated URL, a probe of a
  // different source) has no key in the state either. Guarded on stateLoaded
  // for the record only: activeCacheDir is "" until the state has loaded, so
  // channels.json cannot be applied before the state is.
  function adoptIdScheme(remap) {
    if (!root.stateLoaded) return
    var moved = Model.remapStateIds(root.userState, remap)
    if (!(moved.moved > 0)) return
    root.userState = moved.state
    root.saveState()
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

  // R23c: the start-up init, bounded. The watchdog (stateInitWatchdog) TERMs
  // a run that has not exited within stateInitTimeoutMs and KILLs it after
  // stateInitKillGraceMs; either way QProcess reaps it, and its exit handler
  // decides the held load as the no-write mode. The helper itself no longer
  // blocks on anything at the state path (R23b); this is the second fix,
  // for whatever else could hold it.
  function startStateInit() {
    stateInitProc.running = true
  }

  // R24d: the start-up check begins with mkdir, and so does its one bound.
  function startStartupCheck() {
    root.stateInitTimedOut = false
    mkdirProc.running = true
    stateInitWatchdog.restart()
  }

  // R24d: mkdir's exit. A run the watchdog stopped never starts the init --
  // the filesystem that held mkdir would hold it too -- and is decided at
  // once as the timed-out check it is.
  function startupMkdirExited() {
    if (root.stateInitTimedOut) root.stateInitExited(-1)
    else root.startStateInit()
  }

  // The start-up `state init`'s exit (stateInitProc's handler calls this,
  // and so does a start-up check stopped in mkdir, with exitCode -1).
  function stateInitExited(exitCode) {
    stateInitWatchdog.stop()
    stateInitKill.stop()
    root.dirsReady = true
    // R11: the helper's exit code is read, not assumed. A failed init (the
    // state directory could not be made, say) means the save below may
    // fail too, and the entry mirror must not strip the URL on top of it.
    // R23c: a run the watchdog stopped is a failed one, whatever it exited.
    root.stateInitOk = exitCode === 0 && !root.stateInitTimedOut
    if (!root.stateInitOk) console.warn("omarchy-iptv: state init " + (root.stateInitTimedOut ? "was stopped after " + Math.floor(root.stateInitTimeoutMs / 1000) + " s" : "exited " + exitCode) + "; state.json may be unwritable")
    // R22a: the witness the held load was waiting for. A fresh install is
    // applied here; anything else is re-read once (the helper restores the
    // modes it finds) and then blocks. R23c: a timed-out init is no
    // witness at all, and the held load decides as the no-write mode
    // ("init-timeout", Model.stateLoadDecision).
    root.stateInitFound = Model.stateInitFound(stateInitStdout.text, exitCode, root.stateInitTimedOut)
    root.decideStateLoad()
    // R5: the parked state save FIRST, then the entry mirror that waited
    // for it. The other order is the pointer-less source the review found.
    // R11: "then" means once the save has LANDED -- settleEntryFlush reads
    // the in-flight count and waits for stateFile's `saved`; the call here
    // answers the one case with nothing in flight.
    if (root.stateSavePending) root.saveState()
    root.settleEntryFlush()
    root.runNextCacheJob()
  }

  // D-SINK-19 round 12, R22a. EVERY load of state.json arrives here first,
  // from stateFile's onLoaded and onLoadFailed alike, and is classified
  // before anything is applied (Model.stateLoadKind). Only a load that IS a
  // state reaches applyUserState -- and it lifts the no-write mode, which is
  // what "a later successful load lifts it" means. Anything else waits for,
  // or is judged with, the helper's start-up verdict (decideStateLoad).
  // R26a: and it is the read a parked save waits for. Whatever load comes
  // -- the reload saveState asked for, or one a change raised first -- has
  // been decided by the time the handler returns, so the save goes then,
  // from a turn of its own (R26b): never from inside the handler.
  function stateLoadArrived(result) {
    root.stateInHandler = root.stateInHandler + 1
    try {
      var kind = Model.stateLoadKind(result)
      root.stateLoadKind = kind
      if (kind === "loaded") {
        root.liftStateBlock()
        root.applyUserState(result.text)
      } else {
        root.decideStateLoad()
      }
    } finally {
      root.stateInHandler = root.stateInHandler - 1
    }
    if (root.stateVerifyPending && root.stateInHandler === 0) Qt.callLater(root.finishStateVerifyLater)
  }

  // R26b: a save asked for from the caller's turn is asked again from one
  // of its own, which is where the write is issued.
  function saveDeferredState() {
    if (!root.stateSavePending || root.stateVerifyPending) return
    root.stateWriteTurn = true
    try { root.saveState() } finally { root.stateWriteTurn = false }
  }

  // R26a (D-SRC-35): a source verb meeting a no-write mode a load can lift
  // asks for one reload (Model.stateBlockRecheck); the verb is refused now,
  // and if the file is back the load lifts the mode for the next call.
  function recheckStateBlock() {
    if (!Model.stateBlockRecheck({ blocked: root.stateWriteBlocked, inHandler: root.stateInHandler > 0,
                                   verifyPending: root.stateVerifyPending })) return
    root.stateVerifyRetries = root.stateVerifyRetries + 1
    stateFile.reload()
  }

  function finishStateVerifyLater() { if (root.stateVerifyPending) root.finishStateVerify(false) }

  // R27a (window a): the write a held save was waiting for has been reported
  // (from stateFile's `saved` / `saveFailed`, `timedOut` false) or was not
  // within stateWriteWaitWatchdog's bound (`timedOut` true: the held save
  // goes to its read anyway, and if the view still holds the write the read
  // is dropped and its own 2 s bound decides -- R29a: as R26a decided it,
  // so the wait never outlasts that bound). The held save is asked again
  // from a turn of its own, never from inside the handler (R26b); there it
  // reads, then writes.
  function endStateWriteWait(timedOut) {
    if (!root.stateWriteWaiting) return
    root.stateWriteWaiting = false
    stateWriteWaitWatchdog.stop()
    var ms = Date.now() - root.stateWriteWaitAt
    if (ms > root.stateWriteWaitMsMax) root.stateWriteWaitMsMax = ms
    if (timedOut) {
      root.stateWriteWaitTimeouts = root.stateWriteWaitTimeouts + 1
      root.stateWriteWaitExpired = true
      console.warn("omarchy-iptv: a state.json write was not reported within " + ms + " ms; the next save reads the file first all the same")
    }
    if (root.stateSavePending) Qt.callLater(root.saveDeferredState)
  }

  // R26a: the read-before-write is over -- its load decided (or, from the
  // watchdog, no load came in 2 s and the save goes as it did before R26,
  // counted and logged). A no-write mode the load set refuses the parked
  // save; anything else issues it, with no second read.
  // R29a (2026-10-20, the lead's ruling): BACK TO R26a'S BOUND FOR A SILENT
  // READ. R27a made a second silence the no-write mode, whose lift dropped
  // the held change; R28a held the save past the bound on a schedule, and a
  // stalled read that answered late returned the OLD text, over which the
  // save then wrote another program's write (round 2's live review, a slow
  // FUSE file). Each attempt to hold a change across a read that does not
  // answer for 2 s made a new silent loss, so D-SINK-22's window c stays as
  // it is on 0.14.2: the save is written without its read, counted
  // (stateVerifyNoLoad) and logged.
  function finishStateVerify(timedOut) {
    root.stateVerifyPending = false
    stateVerifyWatchdog.stop()
    var ms = Date.now() - root.stateVerifyAt
    root.stateVerifies = root.stateVerifies + 1
    if (ms > root.stateVerifyMsMax) root.stateVerifyMsMax = ms
    if (timedOut) {
      root.stateVerifyNoLoad = root.stateVerifyNoLoad + 1
      console.warn("omarchy-iptv: state.json was not read back within " + ms + " ms of a save; saving without the read")
    }
    if (root.stateWriteBlocked !== "") {
      root.stateSavePending = false
      root.stateWritesRefused = root.stateWritesRefused + 1
      return
    }
    if (!root.stateSavePending) return
    root.stateVerifyDone = true
    try { root.saveState() } finally { root.stateVerifyDone = false }
  }

  // Model.stateLoadDecision, carried out. Called by a load that is not a
  // state and by the start-up init's exit, in whichever order they come.
  function decideStateLoad() {
    if (root.stateLoadKind === "" || root.stateLoadKind === "loaded") return
    var d = Model.stateLoadDecision({ kind: root.stateLoadKind, loadedBefore: root.stateLoaded,
                                      initFound: root.stateInitFound, retried: root.stateLoadRetried })
    if (d.act === "fresh") {
      // The one load failure that is a fresh install: FileNotFound, AND the
      // helper found nothing there before it created the file.
      root.applyUserState("")
      // R24c (round 14, D-SRC-19 / D-DOC-8): and RE-ARM the watch. Measured
      // in a nested cage on a private bus (spikes/filewatch, set r24): a
      // FileView whose path's DIRECTORY did not exist at its first load --
      // the production fresh-install shape, XDG_STATE_HOME present and
      // omarchy-iptv/ under it absent -- raises nothing for the rest of the
      // session, the init's creation of the file, a helper rename and an
      // in-place garbage write included (sequence Q); one explicit reload()
      // after the start-up mkdir/init re-arms it, and every later change is
      // seen (R, T, R2). The reload it causes is the identity under R24a:
      // it carries the init's created text (or our own save), and
      // Model.sameState of the init's empty default and parseState("") is
      // true, so with a save of ours held it is ignored as the base, and
      // with none it is applied over an equal memory.
      stateFile.reload()
    } else if (d.act === "retry") {
      root.stateLoadRetried = true
      stateFile.reload()
    } else if (d.act === "block") {
      root.blockStateWrites(d.reason)
    }
  }

  // The no-write mode (R22a). Every state write is refused from here on
  // (saveState's gate), the held entry mirror is dropped and no owned entry
  // write is made (writeOwnedEntry), reconcile does nothing, and the source
  // verbs answer `state_unreadable`. Memory stands: at a start it is the
  // empty default and nothing is applied, mid-session it is what the session
  // last had. Told once per episode, by Model.stateUnreadableNotice's
  // sentence, which carries a reason and the path and never a URL.
  function blockStateWrites(reason) {
    var r = String(reason || "io-error")
    if (root.stateWriteBlocked === r) return
    root.stateWriteBlocked = r
    root.stateSavePending = false
    root.settleEntryFlush()
    if (root.stateBlockTold) return
    root.stateBlockTold = true
    var path = root.stateFilePath
    // R27e (D-SRC-42): a block that begins once a state has loaded is titled
    // "Saving has stopped", here and in the notification; one Model sentence.
    var midSession = root.stateLoaded
    console.warn("omarchy-iptv: " + Model.stateUnreadableJournal(r, path, midSession))
    root.notify("stateUnreadable", { reason: r, path: path, midSession: midSession })
  }

  function liftStateBlock() {
    if (root.stateWriteBlocked === "") return
    console.warn("omarchy-iptv: state.json loaded again; writes resume (they were refused: " + root.stateWriteBlocked + ")")
    root.stateWriteBlocked = ""
    root.stateBlockTold = false
  }

  // state.json -> userState (v1 files migrate in memory, section 2.2), then
  // the startup sequence of section 4.4: reconcile the settings into the
  // history and run the one-time cache migration. A reload caused by one
  // of this service's own writes is skipped: the in-memory state is newer
  // than what an earlier atomic write may still be delivering (R10).
  function applyUserState(text) {
    // D-SRC-15 (R9): a reload never replaces in-memory state that is newer
    // than the file. Model.reloadDisposition holds the reasons (our own write
    // echoed back; a save parked behind the start-up dirs; a write in flight;
    // a write that failed). The reload this guards is the helper's start-up
    // `state init` chmod of the existing file, which arrives with the
    // PRE-adoption text while the adoption's save is still parked; applied,
    // it dropped the adopted key and record, and the parked save then wrote
    // the loss to disk. An ignored reload runs nothing below: neither
    // reconcile nor the cache layout.
    // R24a (round 14, D-SRC-22): and whether the text is the disk as the
    // service last knew it (landedState, the BASE) or a FOREIGN write -- a
    // hand-run helper verb, a restore -- which is merged while a change is
    // held instead of being ignored and then written over.
    var disposition = Model.reloadDisposition({ loadedBefore: root.stateLoaded,
                                                ownWrite: root.recentSaves.indexOf(text) !== -1,
                                                matchesBase: root.stateLoaded && Model.sameState(text, root.landedState),
                                                memoryMatchesBase: root.stateLoaded && Model.sameState(root.userState, root.landedState),
                                                savePending: root.stateSavePending,
                                                savesInFlight: root.stateSavesInFlight,
                                                saveFailed: root.stateSaveFailed })
    // R26a: a load met by a read-before-write is counted under its own name,
    // so a check that needs a genuine save-parked reload (key-scenario's D3
    // and W3) is never satisfied by the read every save now makes.
    root.stateReloadsByReason = Model.countReload(root.stateReloadsByReason, (root.stateVerifyPending ? "pre-save-" : "") + disposition.reason)
    if (disposition.act === "merge") {
      root.mergeForeignText(text)
      return
    }
    if (disposition.act !== "apply") {
      root.stateReloadsIgnored = root.stateReloadsIgnored + 1
      // R14: this `return` IS the decision. Without it the reload is counted
      // as ignored and then applied anyway, and only the live arm can tell.
      return
    }
    // Section 15's race: what arrives is a snapshot of the file from before
    // this shell wrote anything, so it is a base to merge onto, not a
    // replacement. Model.stateOnLoad() replays the play this shell recorded
    // while the read was in flight and refuses to resurrect a record already
    // consumed; both answers are the one rule, so neither is decided here.
    // R21a: the file as it is, before anything is merged onto it, is what the
    // disk is known to hold -- and whether it carries the migration marker.
    var onDisk = Model.parseState(text)
    root.landedState = onDisk
    var adopted = Model.stateOnLoad(Model.trimRecents(onDisk, root.maxRecents),
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

  // D-SINK-19 round 14, R24a (D-SRC-22). A FOREIGN write arrived while this
  // session holds a change the file does not (a save parked, in flight or
  // failed). Model.mergeForeignState decides every field; this carries it
  // out: the merge becomes memory, the foreign text becomes the base (it is
  // what the disk holds now), one console line per conflict (the field and a
  // source key, never a URL), and a save is asked for whenever what is on
  // disk -- or about to be, when one of ours is still in flight and would
  // land after it -- is not the merge. Then the tail every applied state
  // runs: the session outcome, reconcile, the cache layout.
  function mergeForeignText(text) {
    var theirs = Model.parseState(text)
    var merged = Model.mergeForeignState(root.landedState, root.userState, theirs, { migrationKey: root.migrationAddedKey })
    for (var i = 0; i < merged.conflicts.length; i++) console.warn("omarchy-iptv: " + Model.mergeConflictLine(merged.conflicts[i]))
    // F1: the record this session's migration added did not land as ours --
    // another program took the place it used ("full"), or added the same
    // playlist itself ("changed"). No marker was carried, so the entry keeps
    // both URLs, and the migration is HELD: the reconcile below retries it
    // at once (Model.reconcileAction's `heldFull`), which over "changed"
    // finds the record and migrates, and over "full" holds it under the one
    // "Sources is full" card (adoptActive tells it, once) until a removal.
    if (merged.migrationHeld !== "") {
      console.warn("omarchy-iptv: " + Model.migrationHeldAgainLine(merged.migrationHeld))
      root.migrationHeldFull = true
      root.migrationAddedKey = ""
    }
    // R25b (D-SRC-31): an in-app addition the merge dropped at a cap is never
    // dropped silently -- one journal line each (a key, never a URL), and the
    // user told once for the whole merge.
    var drops = Model.mergeDropLines(merged.dropped)
    for (var j = 0; j < drops.length; j++) console.warn("omarchy-iptv: " + drops[j])
    if (drops.length > 0) root.notify("mergeDropped", { dropped: merged.dropped })
    root.landedState = theirs
    root.userState = merged.state
    var behind = !Model.sameState(merged.state, theirs)
                 || (root.stateSavesInFlight > 0 && !Model.sameState(merged.state, root.lastSaveState))
    var settled = root.userState
    root.noteSessionOutcome("loaded")
    if (behind && root.userState === settled) root.saveState()
    root.reconcile(true)
    root.startCacheLayout()
  }

  function saveState() {
    // R22a / R22b: THE gate. Every writer of state.json in this service goes
    // through this function (reconcile's adoption, the cache layout,
    // favourites, hidden groups, saved searches, recents, the session record,
    // the source verbs, the probe commit, the key mirror's plan, the D-ID-3
    // remap, the stats adoption), so the no-write mode is decided once, here.
    // "park" is also the answer before any state has loaded: a save then has
    // nothing known to merge onto, so it waits for the load (stateOnLoad
    // replays the session record onto the file) rather than writing the
    // empty default over a file nobody has read.
    // R26a / R26b: and then Model.stateSavePlan says what this call does --
    // join a read already out, re-read before writing, defer to a turn of
    // its own, or write. The only setText is below the plan's "write".
    var gate = Model.stateWriteGate({ blocked: root.stateWriteBlocked, loaded: root.stateLoaded, dirsReady: root.dirsReady })
    var plan = Model.stateSavePlan({ verifyPending: root.stateVerifyPending, gate: gate, blocked: root.stateWriteBlocked,
                                     inHandler: root.stateInHandler > 0, verifyDone: root.stateVerifyDone,
                                     writeTurn: root.stateWriteTurn, inFlight: root.stateSavesInFlight,
                                     waitExpired: root.stateWriteWaitExpired })
    if (plan === "join" || plan === "park") {
      root.stateSavePending = true
      return
    }
    if (plan === "refuse") {
      root.stateSavePending = false
      root.stateWritesRefused = root.stateWritesRefused + 1
      return
    }
    if (plan === "wait") {
      // R27a (window a): held for our write in flight. stateFile's `saved`
      // (or `saveFailed`) ends the wait and asks again from a turn of its
      // own (endStateWriteWait), which reads; bounded by its own watchdog.
      root.stateSavePending = true
      root.stateSavesWaited = root.stateSavesWaited + 1
      if (!root.stateWriteWaiting) {
        root.stateWriteWaiting = true
        root.stateWriteWaits = root.stateWriteWaits + 1
        root.stateWriteWaitAt = Date.now()
        stateWriteWaitWatchdog.restart()
      }
      return
    }
    if (plan === "defer") {
      root.stateSavePending = true
      root.stateSavesDeferred = root.stateSavesDeferred + 1
      Qt.callLater(root.saveDeferredState)
      return
    }
    if (plan === "verify") {
      // The file as it is NOW, through stateFile's own load handlers; the
      // save waits for that load (stateLoadArrived), bounded by the watchdog.
      if (gate === "refuse") root.stateVerifyRetries = root.stateVerifyRetries + 1
      root.stateSavePending = true
      root.stateVerifyPending = true
      root.stateVerifyAt = Date.now()
      stateFile.reload()
      stateVerifyWatchdog.restart()
      return
    }
    // R27a: no write is issued without its read any more, so this counter
    // stays 0; it is kept, under its R26 name, so the harness can say so.
    if (root.stateSavesInFlight > 0 && !root.stateVerifyDone) root.stateVerifySkipped = root.stateVerifySkipped + 1
    root.stateSavePending = false
    root.stateWritesIssued = root.stateWritesIssued + 1
    var text = JSON.stringify(root.userState, null, 2) + "\n"
    // R25a (D-SRC-30): the burst since the last landed save, which `saved`
    // clears. Capped only so a run of failed saves cannot grow it for ever.
    var saves = root.recentSaves.slice()
    saves.push(text)
    while (saves.length > 8) saves.shift()
    root.recentSaves = saves
    // Marked BEFORE setText: the file is older than memory from here until
    // stateFile reports on THIS text (R9, R13). The text is kept so `saved`
    // can tell this write from an earlier one still being reported on.
    root.lastSaveState = root.userState
    root.lastSaveText = text
    root.stateSavesInFlight = 1
    stateFile.setText(text)
  }

  // D-SRC-15 (R11). Run when anything the held entry mirror waits on moves:
  // the helper's start-up exit, a state save landing, a state save failing.
  // Model.entryFlushDisposition decides; this only does what it says. A
  // "drop" leaves the entry EXACTLY as it is -- the URL still on it is the
  // only copy of a source whose state write did not land, and the next start
  // re-adopts it -- and logs a line that carries the reason and no URL.
  function settleEntryFlush() {
    var d = Model.entryFlushDisposition({ pendingKey: root.pendingEntryKey, blocked: root.stateWriteBlocked, dirsReady: root.dirsReady,
                                          initOk: root.stateInitOk, saveFailed: root.stateSaveFailed,
                                          savePending: root.stateSavePending,
                                          savesInFlight: root.stateSavesInFlight })
    if (d.act === "flush") {
      root.flushPendingEntry()
    } else if (d.act === "drop") {
      root.pendingEntryKey = null
      if (d.reason === "save-failed") root.entryMirrorOwed = true   // R19d: owed to the next landed save
      console.warn("omarchy-iptv: the bar entry is left as it is (" + d.reason + "); the source stays where it was")
    }
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
      sourceHost: kind === "epg" ? root.epgSourceHost : root.sourceHost,
      error: { code: "helper_timeout", message: "helper timed out" }
    })
  }

  // Runs against the active source's own cache directory; nothing runs
  // while it is unknown ("" before startup finished, or unconfigured) or
  // while the configured URL is invalid (D16: the status is synthesized).
  function runPlaylistHelper() {
    // D-SINK-19: `invalidInputBlocks`, not `settingsInvalid`. A typo in the
    // CLI input must not stop the ACTIVE source refreshing; that URL was
    // validated when its record was written.
    if (root.playlistUrl === "" || root.activeCacheDir === "" || root.invalidInputBlocks || playlistProc.running) return
    root.playlistAttempted = true
    root.playlistTimedOut = false
    // D-ID-1. `--state-dir` is what makes the one-time id remap run, and it is
    // REQUIRED for it: the helper touches no state file without it, by design.
    // That is the whole safety property, and it is why only THIS call site
    // carries the flag. The active source's fetch is the one moment we know
    // the user means this list, so it is the one moment the saved references
    // may be rewritten to match it. The source PROBE at sourceProbeProc below
    // must never pass it -- probing a candidate the user may cancel must not
    // rewrite favourites against a list they never adopted.
    //
    // Without this line the helper still writes scheme-2 ids into channels.json
    // while the migration sits dead, so 4,898 of 5,221 rows change id with
    // nothing repairing the references to them. The fix would CAUSE the loss it
    // exists to prevent, on an ordinary refresh. Two reviewers refused the
    // change for exactly that, and they were right: the lane could not land it
    // because Service.qml was not in its ownership, which was my error and not
    // theirs (parallel rule 1 (dev branch), ownership follows the coupling).
    // R24e (round 14, D-SRC-27): not in the no-write mode -- the remap is a
    // writer of state.json too, and that mode writes nothing to it.
    playlistProc.command = Model.playlistFetchArgv(root.helperPath, root.activeCacheDir, Model.fetchStateDir(root.stateDir, root.stateWriteBlocked))
    // D-SINK-8: the URL carries the provider's credentials and goes in the
    // environment, never on argv, where /proc/<pid>/cmdline shows it to every
    // local user for the life of the fetch. Assigned immediately before the
    // run, every run: the assignment REPLACES the previous value (measured on
    // Quickshell 0.3.1, see Model.fetchEnvironment), so a stale URL cannot
    // survive a source switch.
    playlistProc.environment = Model.fetchEnvironment(root.playlistUrl)
    playlistProc.running = true
    playlistWatchdog.restart()
  }

  // `epg` with a URL in the environment fetches (the helper honours its own
  // TTL, decision 5); `epg --now-only` recomputes now/next from the cached
  // window and contacts nobody.
  function runEpgHelper(nowOnly) {
    if (epgProc.running || root.activeCacheDir === "") return
    if (nowOnly) {
      if (!root.epgLoaded) return
      epgProc.nowOnly = true
      epgProc.command = Model.epgFetchArgv(root.helperPath, root.activeCacheDir, true)
    } else {
      if (root.epgFetchUrl === "") return
      root.epgAttempted = true
      epgProc.nowOnly = false
      epgProc.command = Model.epgFetchArgv(root.helperPath, root.activeCacheDir, false)
    }
    root.epgTimedOut = false
    // D-SINK-8: the EPG URL can carry credentials too, so it travels in the
    // environment like the playlist's. The `--now-only` run is handed {}
    // deliberately rather than left alone: the assignment REPLACES the value
    // the last fetch set (measured, see Model.fetchEnvironment), so the
    // offline recompute runs with no URL in its environment at all.
    epgProc.environment = Model.fetchEnvironment(nowOnly ? "" : root.epgFetchUrl)
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
    // M3-02: a queued tracks request goes out once this handler is done,
    // whatever this reply was. Deferred rather than inline because the
    // branches below return early and some issue a control of their own.
    if (root.statusQueued) Qt.callLater(root.askPlayerStatus)
    if (root.tracksQueued) Qt.callLater(root.issueQueuedTracks)
    // M5-01: a press that coalesced behind this run goes out once the
    // handler is done. Deferred for the same reason as the two above, and
    // AFTER the drain at the bottom takes the slot synchronously: a zap
    // queued behind this reply outranks a seek, which play() has by then
    // dropped as aimed at the previous stream.
    if (Model.seekQueuePending(root.seekState())) Qt.callLater(root.issueSeek)
    // Whatever this reply was, an open picker may ask again -- the whole
    // rule is Model.shouldRefreshTracks, which is a function and not a
    // conjunction here precisely because two comments in a row described a
    // rule this code did not have. The last of them said "at most once per
    // channel", and the same commit that wrote it added the recovery edge
    // in the healthy-status branch below, which makes it once per channel
    // per observed-alive edge. Read the function.
    else if (Model.shouldRefreshTracks({
               wanted: root.tracksWanted,
               playingId: root.nowPlaying ? String(root.nowPlaying.id || "") : "",
               rowsFor: root.tracksFor,
               askedFor: root.tracksAskedFor,
               recoveries: root.tracksRecoveries })) Qt.callLater(root.refreshTracks)
    if (kind === "tracks") {
      // The helper is authoritative (decision 5): the rows are what mpv has
      // AFTER any selection, never what was asked.
      // A reply for a channel that is no longer playing describes the wrong
      // file: drop it and leave the panel asking, so the re-ask above fires.
      var asked = root.tracksAsking
      root.tracksAsking = ""
      var playingId = root.nowPlaying ? String(root.nowPlaying.id || "") : ""
      if (asked !== "" && asked !== playingId) {
        root.drainPendingPlay()
        return
      }
      if (status.ok === true && status.running === true) {
        root.tracks = Model.parseTracks(status)
        root.tracksFor = playingId
        root.tracksState = "ready"
      } else if (status.ok === true) {
        // The helper says no player answered. That is "did not answer", not
        // "nothing is playing": nowPlaying, the bar and the highlighted row
        // all still name the channel, and a panel contradicting them is a
        // panel the user has to decide between.
        root.tracks = []
        root.tracksFor = ""
        root.tracksState = root.nowPlaying ? "failed" : "idle"
      } else {
        root.tracksState = "failed"
      }
      // A zap queued behind this reply must not wait for the health tick:
      // this branch returns early on two paths (a stale-channel reply and a
      // failed one), so it owes the drain itself. The `pause` branch does
      // the same below (D-PLY-23). This comment has been wrong about that
      // branch twice -- once saying the gap was filed when no id existed,
      // once saying a pause could never be in flight across a zap -- which
      // is why it now says only what is true of the branch it sits in.
      root.drainPendingPlay()
      return
    }
    if (kind === "seek") {
      // M5-01 (design 2.3). The helper read, clamped, seeked and read again;
      // its reply is the whole verdict and `success` from mpv was never
      // evidence (spike 11.4). Nothing here decides whether the seek moved:
      // the guide's transient and the bar's number come from the reply.
      //
      // A zap queued behind this run means the reply describes the stream
      // the user has already left: play() cleared `rewind` when the zap was
      // asked for, and the drain below spawns `play` directly, so writing
      // these numbers back would put the OLD stream's clock on the new
      // channel's bar for up to a health tick. Stale replies apply nothing
      // and say nothing (the tracks branch above does the same by channel).
      // And a reply that lands after stop() or the player's EOF describes a
      // player that is gone: nothing plays, so nothing is behind live, and
      // the guide would otherwise show a transient for it (review finding).
      // Both of those are Model.seekQueueStep's `reply` event: it decides
      // whether the reply is applied and announced, what it means for the
      // readout (through Model.rewindApply), the at-floor memory after it,
      // and that the 300 ms throttle counts from THIS reply rather than from
      // the press. applySeekPlan only obeys. A zap queued behind the seek
      // outranks any press that coalesced behind it: the press was aimed at
      // the stream the zap replaces, and play() has already dropped it.
      var seekPlan = Model.seekQueueStep(root.seekState(), { kind: "reply", status: status, ctx: root.seekCtx() })
      root.applySeekPlan(seekPlan)
      if (seekPlan.announce) root.seekReplied(status)
      // D-PLY-24: every path of a new branch owes the queued play its drain,
      // and this branch has only one path, so it is here and not in an else.
      root.drainPendingPlay()
      return
    }
    if (kind === "pause") {
      // M5-01: a `pause` reply carries the rewind numbers too (2.1), so the
      // bar's `-m:ss` is current from the key the user just pressed rather
      // than from the next 10 s status tick.
      root.applyRewind(status)
      // The helper is authoritative: the optimistic flip is corrected here if
      // the player refused, or if there was no player to ask.
      if (status.ok === true && status.running === true && status.paused !== undefined
          && status.paused !== null) {
        root.paused = status.paused === true
      } else if (status.ok === true && status.running !== true) {
        root.paused = false
      } else if (status.ok !== true) {
        // D-PLY-20's other half, found in the 0.9.0 preflight. Both branches
        // above require ok === true, so the REFUSAL -- the case the comment
        // above says is corrected here -- fell through and left the
        // optimistic flip from togglePause standing. That flag is not
        // internal: it drives the bar's glyph and tooltip and the footer's
        // resume hint, so the bar read "Paused" over a playing stream until
        // the ten-second health poll happened to correct it. A refusal
        // means we do not know, so ask: the `status` branch above is the
        // one place that learns the truth from the player itself. QUEUED
        // rather than issued, because the drain below takes the single
        // control slot synchronously while this was deferred -- so the ask
        // was refused by runControl and dropped, and the optimistic flip
        // stood for a health tick anyway. That is the defect D-PLY-20 was
        // filed for, reintroduced by D-PLY-23's own repair. Issued here AND
        // self-queueing: askPlayerStatus re-arms when the channel is busy,
        // and the next reply drains it. Setting the flag alone would strand
        // it whenever there was no queued play to produce that next reply.
        Qt.callLater(root.askPlayerStatus)
      }
      // D-PLY-23. Every branch that returns early owes the queued play its
      // drain, or a zap issued while this reply was in flight waits for the
      // ten-second health tick. The `tracks` branch was given this when it
      // was written; `pause` was left, and the comment there said a pause
      // could never be in flight across a zap -- which is false, `c` and the
      // bar wheel are one keystroke apart. Outside the if/else so it runs on
      // every path, including the refusal that issues a status of its own.
      root.drainPendingPlay()
      return
    }
    if (kind === "status") {
      var code = status.error ? String(status.error.code) : ""
      if (Model.statusHealthy(status)) {
        // A player observed ALIVE is the one edge on which an open picker
        // may ask again, and it is what D-TRK-6's bound took away: a single
        // `running: false` reply -- a cold start inside the socket-bind
        // window, or a wedge the health poll then restarts -- stamped the
        // channel as asked and nothing ever unstamped it, so the panel sat
        // on "the player did not answer" for the rest of that channel.
        // `statusHealthy` is false for the reply shape that caused the loop,
        // so this cannot restore it: a dead player still gets one ask.
        if (root.tracksWanted) root.tracksAskedFor = ""
        root.healthFailures = 0
        if (status.paused !== undefined && status.paused !== null) root.paused = status.paused === true
        // D-PLY-14: a healthy player that its own stash says is on this exact
        // channel is proof the channel plays, so any failure mark it still
        // carries is stale and goes. The only other clear runs when a play
        // STARTS, so without this a transient first-load error left a channel
        // the user was watching showing "Failed - Space to retry".
        var beforeHealthy = root.failedAt
        root.failedAt = Model.failedAfterHealthy(root.failedAt,
                                                 root.checkPlayerChannel(status),
                                                 root.nowPlaying)
        // D-PLY-14 clears in memory; the mark is durable now, so the clear
        // has to reach the file too or it returns at the next guide open.
        if (root.failedAt !== beforeHealthy && root.nowPlaying)
          root.persistFailed("clear", String(root.nowPlaying.id || ""))
        // M5-01 (2.3): the 10 s status tick re-syncs "behind live" from the
        // player, which also absorbs seeks made with mpv's own arrow keys --
        // live in the player window today, since the plugin passes no
        // --input-default-bindings override. AFTER the D-PLY-14 call above:
        // the node suite bounds that call's distance from the healthy test
        // as a proxy for "it sits in the healthy branch", and a block
        // inserted ahead of it is what turns the proxy red.
        root.applyRewind(status)
      } else if (Model.helperCannotTell(code)) {
        // The helper cannot tell (stub, crash, or a damaged part the stub
        // refused, D-REL-7): neither healthy nor a strike, so a missing
        // subcommand never reaps a working player.
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
    // D-SINK-24: option names only, redacted -- never the refused token whole.
    var rejectedLine = Model.mpvRejectedLine(extra.rejected)
    if (rejectedLine !== "") console.warn(rejectedLine)
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
    // D-SINK-16, and BEFORE the stash is looked at, for two reasons. The
    // readings decide whether this player may be fed at all, and that question
    // outranks which channel it is on; and the ambiguous-stash branch below
    // RETURNS to be retried 500 ms later, by which time the helper's own
    // migration has already happened and the second probe would honestly report
    // nothing to do - so the flag has to be taken on the first answer that
    // carries it. Only ever set here, never cleared (the property's comment).
    //
    // 0.13.0 made every player this plugin LAUNCHES verify (D-SINK-13), but
    // every one of those four layers lives on the launch argv, and an adopted
    // player's argv is whatever the version that started it wrote. The
    // maintainer raised exactly that against the shipped 0.13.0 (#10389): we
    // were not merely leaving a stale setting there, we were sending that
    // process new provider headers and new credentialed URLs.
    var tls = Model.playerTlsVerdict(probe.tls)
    if (!tls.safe) {
      console.warn("omarchy-iptv: the player will not verify the stream's certificate, stopping it")
      root.stopUnadoptedPlayer("unverified")
      return
    }
    if (tls.action === "reload") root.tlsReloadPending = true
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
    // M5-01 (2.2): the zero point lives on the player, so a shell restart
    // recovers "behind live" from the probe reply the way the channel is
    // recovered from the stash, with the number continuous across it.
    // Model.parsePlayerProbe carries it, coerced by Model.parseRewind
    // (numbers finite or null, booleans strict); the service lane's first
    // version re-parsed the reply text and said the probe parser did not
    // carry it, which was true of the design and not of the tree.
    root.applyRewind({ ok: true, running: probe.running === true, rewind: probe.rewind })
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
    root.reestablishForTls()
  }

  // D-SINK-16's second half: the player has been MIGRATED, and now the channel
  // it is already streaming is re-established so that nothing continues on a
  // connection that was opened without verification.
  //
  // THE RELOAD IS DELIBERATE AND IT IS NOT BELT-AND-BRACES. Setting
  // `tls-verify` covers the NEXT load - that much the lead measured on
  // 2026-10-07, attacker GETs 1 -> 0 on one unchanged process. Whether an
  // ALREADY-OPEN stream picks the change up for its ongoing segment fetches was
  // NOT measured, and this does not assume either answer: it closes the
  // connection and opens a new one, which makes the unmeasured behaviour
  // irrelevant instead of trusted. The cost is one visible rebuffer, once, on
  // the first reattach after an upgrade - a player this shell started is
  // already verifying, so it answers "feed" and nothing here fires.
  //
  // It waits for `activeCacheDir`, because the helper resolves a channel id
  // against the cache DIRECTORY and the reattach deliberately runs before that
  // exists (the stash names the channel ~130 ms in; the cache lands later). So
  // this is called from both of reconcileNowPlaying()'s own call sites and
  // delivers on whichever is late. Residual, stated rather than hidden: if the
  // cache never lands at all - no source configured - the reload never fires
  // and that one already-open connection runs to the end of its stream
  // unverified. Every LATER load on that player is verified by the migration
  // and by apply_channel's refusal.
  function reestablishForTls() {
    // D-SINK-16. The three conditions are a FUNCTION (rule 12), because the
    // first version of this guard cleared the flag whenever `nowPlaying` was
    // null, and null there means two different things: "the user stopped", for
    // which nothing is owed, and "not assigned yet", which is the
    // reattach-after-upgrade moment itself -- the flag is set before
    // nowPlaying is. Clearing it there dropped the reload for good, since it
    // is armed in exactly one place, and the already-open unverified stream
    // then ran to the end of its stream. Found by the review of the lane that
    // wrote this.
    var want = Model.tlsReloadDisposition({
      pending: root.tlsReloadPending, stopping: root.stopping,
      userStopped: root.userStopped,
      nowPlayingId: root.nowPlaying === null ? null : String(root.nowPlaying.id),
      cacheDir: root.activeCacheDir, playerUp: root.playerUp
    })
    if (want === "none") return false
    if (want === "clear") {
      // Nothing of ours is playing any more: whatever replaces it goes through
      // apply_channel, which asserts the same thing and refuses rather than
      // loads.
      root.tlsReloadPending = false
      return false
    }
    // "hold": still owed, and the shell is not ready. The flag STAYS set so a
    // later call delivers it.
    if (want !== "deliver") return false
    root.tlsReloadPending = false
    console.warn("omarchy-iptv: re-establishing the channel on an adopted player that was not verifying certificates")
    return root.reapplyIntent(String(root.nowPlaying.id))
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
    return root.stopUnadoptedPlayer("foreign")
  }

  // The same ladder under a second name, because D-SINK-16 ends in it for a
  // different reason and the session record should say which: a player that
  // could not be made to verify the stream's certificate is stopped rather than
  // fed, and that is not the same event as a player we could not identify.
  function stopUnadoptedPlayer(outcome) {
    root.playSeq += 1
    root.playerWanted = false
    playerSocketTimer.stop()
    root.playerPending = false
    root.nowPlaying = null
    // Nothing of ours plays now, so a reload owed to D-SINK-16 is owed to
    // nothing.
    root.tlsReloadPending = false
    root.noteSessionOutcome(outcome)
    Quickshell.execDetached(Model.helperArgv(root.helperPath, Model.playerStopArgv(root.socketPath, root.playSeq)))
    return true
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
    // 4.7 step 3, the compositor half of the same recovery: the snapshot
    // above says what the window WAS, this says what it IS. Both are needed
    // and neither substitutes for the other - a shell that reattached to a
    // player in PiP has no memory of either (D-PIP-4).
    root.pipPeek()
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
  // copy of itself in the spec file (engineering rule 10 (dev branch)).
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
    if (id !== "") {
      // Applied locally at once and persisted in the same turn. The local
      // apply is not an optimisation: the file is reloaded asynchronously, so
      // waiting for it would leave the row unmarked for as long as a process
      // launch takes -- and engineering rule 9 is that a plugin never waits for
      // its own write to come back.
      root.failedAt = Model.withFailed(root.failedAt, id, Math.floor(Date.now() / 1000))
      root.persistFailed("mark", id)
      root.lastFailedId = id
    }
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
    // M5-01: no player, no history, and no seek to deliver to it.
    root.clearRewind()
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
    root.entryOwners = Model.keyedMap()
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
      if (root.epgFetchUrl !== "" && (!root.epgLoaded || Model.epgNowStale(root.epgMeta, Math.floor(Date.now() / 1000)))) root.refreshEpg(true)
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

  // D-SINK-19. SET THE ACTIVE SOURCE. The state is the authority and the bar
  // entry is a mirror, which is the whole point of the change: the key goes
  // into the plugin's own 0600 state.json, and the host's shell.json gets a
  // pointer and no credential.
  //
  // The ORDER here is load-bearing in the other direction from D-SINK-18's.
  // The state write comes FIRST and cannot be refused: it is our own file, it
  // is already private, and it is what every binding in this service reads.
  // So a switch completes in this turn whatever the host does, and nothing
  // waits for an echo (rule 9). The entry write that follows can be refused
  // -- there may be no writable bar entry at all -- and that is logged and
  // repaired on the next start, NOT a failed switch, because the fact it
  // mirrors is already recorded (SR25 as amended 2026-10-12). Before this
  // change the entry WAS the fact, so a failed write had to abort the
  // switch; keeping that would now refuse a switch that has already
  // happened. What CAN fail a switch is the state write itself, and that is
  // reported from stateFile's saveFailed ("state_write_failed", R13).
  //
  // `key` is "" to clear the active source (removeSource).
  //
  // R5. The ORDER is Model.pointerWritePlan's and not this function's: state
  // first, and the entry WAITS when the state save is parked behind the
  // start-up dirs (saveState sets stateSavePending; stateInitProc's exit
  // writes the parked state and then settles the held entry). A shell that
  // dies in between leaves the URL still on the entry, which the next start
  // re-adopts -- never a source nobody points at.
  //
  // R13. The entry waits for the state write to LAND on every route, the
  // dirsReady one included: "write-entry-after-saved" holds the key and
  // settleEntryFlush writes it from stateFile's `saved`, or leaves the entry
  // exactly as it is from `saveFailed`. The plan is handed the in-flight
  // count because adoptActive saves and then reaches here through
  // Qt.callLater with the key already in memory -- "nothing moved" with a
  // write still in the air was the round-3 P1 -- and the sticky failure
  // because after a failed write the file is older than memory until a
  // later save lands, and a mirror written then would strip the one copy.
  function persistActive(key) {
    var want = Model.activeKeyText(key)
    var next = Model.withActiveKey(root.userState, want)
    var plan = Model.pointerWritePlan({ keyMoved: next !== root.userState, dirsReady: root.dirsReady,
                                        savePending: root.stateSavePending,
                                        savesInFlight: root.stateSavesInFlight,
                                        saveFailed: root.stateSaveFailed })
    for (var i = 0; i < plan.steps.length; i++) {
      var step = plan.steps[i]
      if (step === "save-state" || step === "defer-state") {
        root.userState = next
        root.saveState()
      } else if (step === "wait-entry") {
        root.pendingEntryKey = want
      } else if (step === "write-entry-after-saved") {
        // Held, then decided at once: with a save in flight the disposition
        // waits for `saved`; with the last save failed and nothing in flight
        // it drops the hold here, because nothing else would wake it.
        root.pendingEntryKey = want
        root.settleEntryFlush()
      } else if (step === "write-entry") {
        return root.persistEntryKey(want)
      }
    }
    // A held entry: accepted, not refused; nothing has been written to the
    // host's file yet. The state write it waits for CAN fail (an unwritable
    // directory, a full disk -- the FileView reports it through saveFailed),
    // and then the entry is not written at all (R11 / R13, settleEntryFlush)
    // and the failure is reported from there, as the state write's own.
    return true
  }

  // The second half of a "wait-entry" plan, run by settleEntryFlush once the
  // parked state save has LANDED (stateFile's `saved`, R11) -- never from
  // stateInitProc's exit directly, which only issues that save. The last key
  // asked for wins: every owned write states every owned key, so one write
  // for the latest value is the same file as one write per value.
  function flushPendingEntry() {
    if (root.pendingEntryKey === null) return
    var key = root.pendingEntryKey
    root.pendingEntryKey = null
    root.persistEntryKey(key)
  }

  // D-SINK-18's gate, kept and now asked about the ENTRY rather than about a
  // pair of URL arguments (Model.entryShieldDecision, which is where the
  // reasoning about whether a KEY is a secret lives). Three answers:
  //
  //   persist  write now -- the file is known private, or this write carries
  //            no URL. Every shipping write is this answer after D-SINK-19,
  //            because the plugin no longer puts a URL in that file; the
  //            other two stay reachable for the write that would, and the
  //            test that proves it feeds a URL-bearing patch through the real
  //            decision rather than grepping for one (rule 14)
  //   refuse   do not write; the file is known not private and the helper
  //            could not make it so. Surfaced exactly like every other
  //            persist failure, through sourcesPersistFailed -- F-UX-7 was
  //            filed for a refusal nobody saw
  //   defer    hold the key and let the shield's exit decide. Only reachable
  //            before the first run exits, because QML cannot block on a
  //            Process; `true` is returned, which is "accepted, not refused",
  //            and NOTHING has been written at that point
  //
  // The shield itself is NOT retired with the URLs, and not for symmetry: a
  // user can still put a credential in that file with their own hand
  // (`omarchy bar set ... playlistUrl <url>`, a route R21 refuses but cannot
  // stop anyone typing; and every 0.13.x entry the migration reads), and the
  // chmod this runs is the only thing that limits who can read it in the
  // window before the plugin adopts or refuses it and writes the entry back
  // without it.
  function persistEntryKey(key) {
    var patch = Model.ownedEntryPatch(root.settings, { sourceKey: Model.activeKeyText(key) })
    var decision = Model.entryShieldDecision(root.hostConfigShield, patch)
    if (decision === Model.CONFIG_REFUSE) {
      root.refuseUnsafePersist()
      // D-SINK-18, found by the review: without this the refusal is PERMANENT
      // until the shell restarts. The state is only ever refreshed after a
      // successful write and at start-up, so a user who reads the message,
      // runs the chmod it names and tries again was refused again, by an
      // answer taken before they fixed anything. Telling someone to do a thing
      // and then ignoring that they did it is worse than not telling them.
      // Re-arming here costs one short-lived process per refusal, and a
      // refusal is already the rare path.
      root.runConfigShield()
      return false
    }
    if (decision === Model.CONFIG_DEFER) {
      root.pendingPersist = { sourceKey: Model.activeKeyText(key) }
      root.runConfigShield()
      return true
    }
    return root.writeActive(key)
  }

  // The refusal, in one place so the deferred path and the immediate path say
  // the same thing. No URL in either message (rule 5): the guide's sentence
  // comes from Model.sourceErrorMessage("config_unsafe") and names the chmod,
  // not `omarchy bar set`, which would write the credential into the user's
  // shell history for ever.
  //
  // D-SINK-19: no shipping write reaches this any more, because the plugin
  // writes no URL into the host's file. It is kept, and kept reachable
  // through Model.entryShieldDecision, for the write that would.
  function refuseUnsafePersist() {
    root.lastPersistFailure = "config_unsafe"
    console.warn("omarchy-iptv: refusing to save a source URL into settings other users can read; see the config shield warning above")
    root.sourcesPersistFailed("config_unsafe")
  }

  // Mirror the active source's KEY into the host entry (D-SINK-19; it was the
  // URL pair under D1 until 0.13.3). Reached only through persistEntryKey,
  // which is what decides whether this write is allowed to happen at all
  // (D-SINK-18), and from onConfigShieldExit for a write that deferred.
  //
  // The write is applied LOCALLY on success and the guide redraws from that;
  // the plugin never waits for the host to echo its own settings back
  // (D-LIVE-20 / D-LIVE-21, see `settings` above) -- and since D-SINK-19 it
  // does not depend on this write at all: the active key is already in
  // state.json, which is what every binding here reads. The failure HERE is
  // only a missing host or an entry updateEntryInline cannot rewrite:
  // `false` from a writable entry is its `!dirty` branch (shell.qml:1114),
  // i.e. the host already stores exactly what we asked for, which is success.
  //
  // R13 / SR25 as amended: `announce` false. The key is already in
  // state.json, so a refused mirror loses nothing -- the next start repairs
  // it (Model.adoptActiveSource step 2 rewrites a mirror that disagrees with
  // the state) -- and reporting it as a failed switch sent the user to
  // `omarchy bar set` for a switch that had succeeded. The funnel still logs
  // the refusal.
  function writeActive(key) {
    return root.writeOwnedEntry({ sourceKey: Model.activeKeyText(key) }, "settings change", false)
  }

  // THE ONLY PLACE THIS PLUGIN WRITES THE BAR ENTRY (D-LOGO-2, D-SINK-19).
  //
  // There were two call sites, and D-LOGO-2 is what having two cost: each
  // named the keys IT cared about, so each wrote the other's one-write-behind
  // value back to disk and the two could revert one another. The patch rule
  // fixed that; collapsing the writers is what stops the next key repeating
  // it (rule 15: the search is for the shape, and the shape was "a writer
  // that decides for itself what the entry contains").
  //
  // `Model.ownedEntryPatch` names every owned key at its current effective
  // value, and `Model.entryWith` carries every key we do NOT own through the
  // host's wholesale replace while dropping the retired URL keys -- so any
  // write here also heals an entry left behind by an older build.
  // `announce` is false for the logo toggle, which reports its own failure
  // through its return value: `sourcesPersistFailed` is the SOURCES screen's
  // error channel and raising it for a logo switch would put a source error
  // on screen for something that is not one. (R13 made it false for the key
  // mirror as well; see writeActive.)
  //
  // R16: `patchOnly` true is the PATCH-ONLY write. The caller (setShowLogos,
  // under Model.ownedWriteMode) passes it before the first state load and
  // while a state write is parked, in flight or failed: the overrides then
  // carry `showLogos` alone, so the patch's `sourceKey` is the host's own
  // value (ownedEntryPatch over `settings`), never memory's, and the write
  // does not pay a mirror a failed save left owing (R19d). What it does with
  // the retired URL keys is NOT its own decision any more (R21): every owned
  // write asks Model.retiredInputsToKeep over the LANDED migration marker,
  // which keeps every one until the marker has landed and none after it.
  //
  // `settings`, not `hostSettings`, is load-bearing (D-LOGO-2): `settings`
  // carries our own last write laid over the host's one-write-behind
  // publish, so a key this write does not override goes out at the value we
  // last wrote. Composed from `hostSettings`, the key mirror's write after a
  // logo toggle would carry the PRE-toggle showLogos back to disk on the
  // lagging host. Pinned by the node suite on the dev branch (the R16
  // funnel pin, and the service-order driver, which composes from whichever
  // this line names). Healing the entry is
  // the key mirror's job once the file agrees with memory again (writeActive
  // under R13), and the mirror never passes this.
  function writeOwnedEntry(overrides, what, announce, patchOnly) {
    // R22a: in the no-write mode the entry is left exactly as it is -- it may
    // hold the only copy of an input the unread file could not tell us about.
    if (root.stateWriteBlocked !== "") {
      // R27e's rule-15 sibling (D-SRC-42): the journal says why in the words
      // of the episode -- a block that began after a load is saving stopped.
      console.warn("omarchy-iptv: the bar entry is left as it is (" + (root.stateLoaded ? "saving to state.json has stopped" : "state.json was not loaded") + "); no " + what + " written")
      return false
    }
    if (!root.shell || typeof root.shell.updateEntryInline !== "function"
        || !Model.barEntryWritable(root.shell.barConfig, root.pluginId)) {
      console.warn("omarchy-iptv: no writable bar entry for the " + what)
      if (announce !== false) {
        root.lastPersistFailure = "persist_failed"
        root.sourcesPersistFailed("persist_failed")
      }
      return false
    }
    var patch = Model.ownedEntryPatch(root.settings, overrides)
    patch.id = root.pluginId
    // R21a / R21b, decided here, in the one funnel, for EVERY owned write,
    // heal and patch alike: until the migration marker has LANDED the entry
    // keeps every retired URL key it carries (the URL there may be the only
    // copy of what the migration's state write carries), and from then on
    // every owned write strips them, whatever they are. R17a's held/consumed
    // rule and R20c's landed-state rule for the patch are withdrawn: the
    // only question left is the marker's.
    var published = Model.findBarEntry(root.shell.barConfig, root.pluginId)
    var keep = Model.retiredInputsToKeep(published, Model.entryMigratedOf(root.landedState))
    var entry = Model.entryWith(published, patch, { keep: keep })
    // R19a (round 9): NO SKIP ON AN ESTIMATE. Every owned write is handed to
    // the host, and updateEntryInline's own answer is the dirty check: `false`
    // from a writable entry is "already stored", which is success. Round 8
    // skipped the hand-over when the plugin's record of its last write said
    // the host stored this entry already, and on the lagging host a publish
    // that went A -> B -> A brought that record back: a logo OFF, the strip
    // of a re-set refused credential and the strip of a re-set EPG input
    // were each skipped while the host would have stored them.
    var stored = root.shell.updateEntryInline(root.pluginId, entry)
    // R18b's first clause, which ALONE settles the cycle: the own-write
    // record is reassigned only when it differs from the one in force
    // (Model.sameOwnWrite). Reassigning an equal record re-evaluates
    // `settings` and fires onSettingsChanged -> reconcile -> this funnel
    // again: round 7's lagging-host loop, a refused playlistUrl beside a
    // pending EPG, at about 3,000 no-op writes a second.
    var record = Model.ownWriteOf(root.hostSettings, Model.ownedEntryPatch(root.settings, overrides))
    if (!Model.sameOwnWrite(root.ownWrite, record)) root.ownWrite = record
    // A heal states every owned key, so it pays any mirror a failed save
    // left owing (R19d).
    if (patchOnly !== true) root.entryMirrorOwed = false
    // Nothing was written (`false`): the file is as it was, and the gate in
    // front of the next write is no staler than before. Re-arming here would
    // spend a process on every hand-over the lagging host answers `false` to.
    if (stored === false) return true
    // D-SINK-18. Re-arm for the NEXT write. The file can be recreated 0644
    // while the shell runs -- omarchy-refresh-config copies the 0644 package
    // default with `cp -f`, which keeps an existing file's mode but gives a
    // file it CREATES the umask's -- and nothing tells a plugin that happened.
    // This run is not what protects the write above (the shield at service
    // start, or the deferred one, did that); it is what makes sure the gate in
    // front of the next one is answering about the file as it is now.
    //
    // THE RESIDUAL, which is not zero and must never be written as zero.
    // D-SINK-19 changed WHOSE credential is at stake here and did not remove
    // the window. The plugin no longer writes a provider URL into this file,
    // so a write that lands on a 0644 file now exposes a source KEY and not a
    // credential -- which is a 32-bit confirmation of a guessed URL rather
    // than the URL (Model.entryShieldDecision states that trade). What is
    // still a credential is the one the USER puts there with
    // `omarchy bar set ... playlistUrl <url>` (refused since R21, and read by
    // the migration before it): it sits in the file from their shell's write
    // until this plugin refuses or adopts it and writes the entry back
    // without it, and the chmod below is the only thing narrowing who can
    // read it in between.
    // `hostConfigShield` answers about the file as of the last shield run, so
    // a recreation that lands after that run and before this write is not
    // seen. Two windows, and they are different sizes:
    //   - the shield's own latency, measured on this machine (4 cores, one
    //     `config shield` per run, n=12 each): 194-213 ms idle, median 197;
    //     271-1076 ms with eight CPU spinners on four cores, median 919. It
    //     is a process start, so it scales with load exactly as D-SINK-9's
    //     shield does. A URL-bearing persist that lands during it defers;
    //     a key-only one does not, because the gate does not fire for a
    //     write that carries no secret -- and after a write this is how long
    //     the gate stays one run behind.
    //   - the gap from that run's exit to the next persist, which is however
    //     long the user goes between source edits and is therefore UNBOUNDED
    //     in time. It is bounded in EVENTS: the answer is at most one shield
    //     run old, and a run follows service start, every persist and every
    //     logo toggle.
    // What closes the second window is making every persist wait for its own
    // fresh answer -- the defer machinery already exists, so it is a one-line
    // change from "consult the cached state" to "always defer" -- at the cost
    // of the latency above on each source add, edit and switch. Not taken
    // this round: the brief says shield at start and after each persist, and
    // the trade is the product owner's to make rather than this lane's.
    root.runConfigShield()
    return true
  }

  // `applyOwnWrite(key)` USED TO BE HERE. Nothing called it (dead since
  // b2a4986; the D-SINK-19 review found it carrying six live assertions). The
  // own-write record is made where the write is made, in writeOwnedEntry.

  // D-SINK-18. Start the shield, or remember to start it again. Setting
  // `running = true` on a Process that is already running is not a queue, so
  // a second request while one is in flight is folded into one re-run on exit
  // -- the same shape as playlistRerun / epgRerun above.
  function runConfigShield() {
    if (configShieldProc.running) {
      root.configShieldRerun = true
      return
    }
    configShieldProc.running = true
  }

  // The verb's answer. `hostConfigShield` moves from unknown to private or
  // exposed and never back to unknown: Model.configShieldState fails closed,
  // so a helper that did not run, crashed or printed nothing reads as exposed
  // rather than leaving every future persist deferred for ever.
  function onConfigShieldExit(out) {
    root.hostConfigShield = Model.configShieldState(out)
    var pending = root.pendingPersist
    root.pendingPersist = null
    if (pending) {
      if (root.hostConfigShield === Model.CONFIG_SHIELD_PRIVATE) {
        root.writeActive(pending.sourceKey)
      } else {
        // The caller was told `true` and has already moved on, so the one
        // piece of its state that outlives it has to be unwound here:
        // switchSource and the probe commit both open a switch before
        // persisting, and a switch nothing finishes would leave the sources
        // API answering `busy` until switchTimeout fires.
        if (root.switching) root.abortSwitch()
        root.refuseUnsafePersist()
      }
    }
    // Drained through a Timer, not by starting the Process from inside its
    // own exit handler: the same shape as playlistRerun / epgRerun, which
    // restart their debounce rather than re-entering the slot they are in.
    if (root.configShieldRerun) {
      root.configShieldRerun = false
      configShieldDebounce.restart()
    }
  }

  // M2-04. The logo switch, written through the host the same way the source
  // URLs are and applied locally in the same turn (D-LIVE-20 / D-LIVE-21: the
  // host publishes barConfig one write behind, so waiting for the echo means
  // waiting forever).
  //
  // `false` is returned only for a real persist failure. The caller shows the
  // count BEFORE calling this; nothing here asks again.
  function setShowLogos(on) {
    var want = on === true
    if (root.showLogos === want) return true
    // D-LOGO-2, the other direction: this used to name showLogos alone and
    // wrote the one-write-behind playlist and EPG URLs back with it. There is
    // no second updateEntryInline in this file any more -- D-SINK-19 put both
    // writers behind writeOwnedEntry, so this one cannot disagree with the
    // source writer about what the entry contains, and it now REMOVES a URL
    // an older build left in the entry instead of carrying it forward.
    //
    // D-SINK-18: still not gated, and the reason is sharper than it was. The
    // write carries `sourceKey` and `showLogos` (or `showLogos` alone, the
    // patch below) and no URL of the plugin's own. What it does with a URL a
    // user put on the entry is the funnel's (R21): kept until the migration
    // marker has landed, stripped by every write after -- which ended
    // D-SINK-20, the patch-only toggle on the lagging host writing back a URL
    // the plugin's own heal had just stripped, a refused credential included.
    // Do NOT narrow the keep to "while no own-write override is in force":
    // that decides from the host's state, which knows nothing of the disk,
    // and strips the only copy of what a failed migration write carried.
    // What both get is the shield re-arm, which tightens the file and
    // shortens the drift window by one more event. writeOwnedEntry re-arms
    // the shield itself, so there is no second call here: one write, one
    // re-arm.
    //
    // R16 (round-4 review P1, rule 15: this is writeOwnedEntry's SECOND
    // caller, and R13 gated only the first). While a state write is parked,
    // in flight or failed, the file is older than memory and the URL on the
    // entry may be the only copy of a source whose write did not land; this
    // write used to mirror the in-memory key and strip that URL, and the
    // next start found the record nowhere. Model.ownedWriteMode decides from
    // four inputs: "patch" writes `showLogos` alone and leaves `sourceKey` as
    // the host publishes it (ownedEntryPatch takes the key from `settings`);
    // "heal" is today's write. Either way the retired URL keys are the
    // funnel's (R21, above). The mirror itself is written by writeActive
    // once the file agrees with memory, under R13.
    //
    // R16 as amended (round 6): `stateLoaded` is the fourth input. Before
    // stateFile's first load userState is Model.emptyState() and no save
    // flag is raised, so the three flags answered "heal" and the toggle
    // mirrored sourceKey "" and stripped a URL set while the shell was down
    // -- the only copy of it. Nothing on the guide's path waits for the
    // load (openSources needs serviceReady, toggleLogos inSources), so the
    // gate is here, where the write is decided.
    var mode = Model.ownedWriteMode({ blocked: root.stateWriteBlocked,
                                      stateLoaded: root.stateLoaded,
                                      savePending: root.stateSavePending,
                                      savesInFlight: root.stateSavesInFlight,
                                      saveFailed: root.stateSaveFailed })
    if (mode.mode === "none") {
      console.warn("omarchy-iptv: logo setting not written (" + mode.reason + "); the bar entry is left as it is")
      return false
    }
    if (mode.mode === "patch") {
      console.warn("omarchy-iptv: logo setting written alone; the bar entry's source keys are left as they are (" + mode.reason + ")")
      return root.writeOwnedEntry({ showLogos: want }, "logo setting", false, true)
    }
    return root.writeOwnedEntry({ sourceKey: root.activeSourceKey, showLogos: want }, "logo setting", false)
  }

  // One process per mark or clear, which is affordable because a failure is
  // rare -- not per keystroke, per zap or per tick. Fire and forget: the
  // in-memory map is already correct, and a failed write costs a mark, not a
  // wrong one.
  Process { id: failedProc }
  Connections {
    target: failedProc
    // Drain the queue. Without this a second mark raised while the first was
    // still being written would sit there for ever -- which is how the kill
    // this replaced came to exist.
    function onExited(exitCode, exitStatus) {
      if (root.failedQueue.length === 0) return
      var q = root.failedQueue.slice()
      var next = q.shift()
      root.failedQueue = q
      root.runFailedJob(next)
    }
  }

  // A one-deep queue rather than a kill. This used to SIGTERM its own
  // in-flight write and start another, which loses the write it killed --
  // and the two calls that collide are exactly the common pair: a play
  // clearing a mark while the previous failure is still being written.
  property var failedQueue: []

  function persistFailed(action, id) {
    if (root.activeCacheDir === "" || str(id) === "") return false
    var job = { action: action, id: str(id), dir: root.activeCacheDir }
    if (failedProc.running) {
      // Collapse to the LAST request per id: a clear after a mark is the
      // truth, and replaying both in order would write the mark back.
      var q = root.failedQueue.filter(function (j) { return j.id !== job.id })
      q.push(job)
      root.failedQueue = q
      return true
    }
    root.runFailedJob(job)
    return true
  }

  function runFailedJob(job) {
    failedProc.command = Model.failedArgv(root.helperPath, job.action, job.id, job.dir)
    failedProc.running = true
  }

  function str(v) { return v === undefined || v === null ? "" : String(v) }

  // The marks of the source whose channels are loaded. Pruned on arrival: the
  // TTL, and any id the current playlist does not have -- which is what makes
  // an id rotation, a provider reshuffle and a removed channel all self-heal
  // instead of leaving marks that name nothing.
  // The raw list as it came off disk. Kept because the prune needs the CHANNELS
  // to decide what is stale, and the two files load independently -- on a cold
  // start failed.json can arrive first.
  property var failedRaw: []

  function applyFailed(text) {
    root.failedRaw = Model.parseFailed(text)
    root.pruneFailed()
  }

  // D-DEAD-1, found live: this used to pass `Model.knownIdSet(root.channels)`
  // straight through. With no channels loaded yet that is `{}` -- an EMPTY
  // object, which is truthy -- so every mark was dropped as "not in the
  // playlist" and the marks silently vanished on every cold start.
  //
  // `prunedFailed` already distinguishes "no channels, cannot tell" from "here
  // are the channels": it takes null for the first. The bug was entirely at
  // this call site, and the unit test passed because it tested the function
  // with null rather than the caller with what the caller actually sends.
  function pruneFailed() {
    var known = root.channels.length > 0 ? Model.knownIdSet(root.channels) : null
    root.failedAt = Model.failedIndex(Model.prunedFailed(root.failedRaw, root.nowSec, known))
  }

  // Re-prune when the channels arrive, whichever file won the race.
  onChannelsChanged: root.pruneFailed()

  // Pause or resume what is playing. Returns false when there is nothing to
  // pause, so a caller can say so rather than appearing to work.
  //
  // The local flip is applied at once and the helper confirms it on the next
  // health tick: the bar must not wait a process launch to show the state the
  // user just asked for (rule 9). A refusal corrects it within a tick.
  // -> "" on success, else a reason. Two different failures used to share one
  // `false` and the guide said "Nothing is playing" for both, including when
  // something WAS playing and the helper slot was merely busy. A message that
  // is wrong about why is worse than no message.
  function togglePause() {
    if (!root.nowPlaying) return "idle"
    var want = !root.paused
    if (!root.runControl("pause", Model.playerPauseArgv(root.socketPath, want ? "on" : "off"))) return "busy"
    root.paused = want
    return ""
  }

  // ---- M5-01 LIVE REWIND (design section 2.3, on the dev branch)
  //
  // The keypress path goes through the one control slot, like `pause`. The
  // helper does every piece of cache arithmetic -- it reads the range,
  // clamps the target to the floor plus 2 s or the edge minus 0.5 s, issues
  // ONE absolute seek and reads `time-pos` back (2.1); QML never computes a
  // target. What the service owns is the queue: presses that arrive while a
  // seek is in flight, or inside the 300 ms throttle after a reply, are
  // summed and capped by Model.coalesceSeek rather than spawned one by one.
  //
  // F-RWD-19: every DECISION the queue takes is Model.seekQueueStep's, and
  // every reply's meaning for the readout is Model.rewindApply's, so each
  // one is a line a node test drives and a mutation reddens. What is left
  // here is what Qt owns -- `controlProc.running`, `seekThrottle.running`,
  // `Date.now()`, property writes, starting the timer, `runControl` and the
  // signal. Of every branch below a reader can say which of the two it is.

  // The queue's own three fields, and what the service knows about the world
  // when an event reaches it (F-RWD-19). Every DECISION below is
  // Model.seekQueueStep's; these two compose its arguments out of Qt state
  // and nothing else, so a reader can see exactly what the reducer is told.
  function seekState() {
    return { pending: root.seekPending, liveQueued: root.seekLiveQueued, atFloor: root.seekAtFloor }
  }

  function seekCtx() {
    return {
      playing: root.playing, stopping: root.stopping, userStopped: root.userStopped,
      controlBusy: controlProc.running, throttled: seekThrottle.running,
      rewind: root.rewind, socket: root.socketPath,
      pendingPlayId: root.pendingPlayId, currentEntryId: root.currentEntryId,
      stepS: Model.REWIND_STEP_S
    }
  }

  // The one place a plan becomes Qt state: property writes, the timer, the
  // single control slot. Nothing here chooses anything. Returns the plan's
  // reply, which is what the IPC verbs serialise and the guide reads.
  function applySeekPlan(plan) {
    root.seekPending = plan.state.pending
    root.seekLiveQueued = plan.state.liveQueued
    root.seekAtFloor = plan.state.atFloor
    if (plan.clearReadout) {
      root.rewind = null
      seekThrottle.stop()
    }
    if (plan.readout) {
      // `rewind` is null, never {}, until the player says; a reading of
      // "none" restamps the zero point the same as a reading of numbers.
      if (plan.readout.clear) root.rewind = null
      else if (plan.readout.store) {
        root.rewind = plan.readout.rewind
        root.rewindAtSec = Math.floor(Date.now() / 1000)
        root.behindTickSec = root.rewindAtSec
      }
    }
    // The 300 ms throttle counts from THIS reply; the throttle timer
    // re-drives the queue when it elapses.
    if (plan.restartThrottle) seekThrottle.restart()
    if (plan.argv.length === 0) return plan.reply
    if (root.runControl("seek", plan.argv)) return plan.reply
    // A spawn the reducer asked for and runControl did not give us. runControl
    // refuses only while the slot is busy, which the reducer checked in the
    // same synchronous turn, so this is unreachable by construction rather
    // than a live path -- and it is here because "applying" for a run that
    // never happened is the false success CN15 forbids. The sum is spent
    // either way, exactly as it was before this refactor.
    root.seekPending = 0
    root.seekLiveQueued = false
    return root.seekRefuse(plan.reply && plan.reply.requested !== undefined ? plan.reply.requested : 0, "busy")
  }

  // Every reply that carries a `rewind` object refreshes the state --
  // `status`, `pause`, `probe` and `seek` all do. What a reply MEANS is
  // Model.rewindApply: whether to store, the coerced object, whether to
  // clear, and the at-floor memory after it. The entry-id drop and the
  // floor-clear rule live there (F-RWD-19).
  function applyRewind(status) {
    var readout = Model.rewindApply({ status: status, currentEntryId: root.currentEntryId,
                                      atFloor: root.seekAtFloor, stepS: Model.REWIND_STEP_S,
                                      // F-RWD-24: a queued play means every reading in
                                      // flight is the stream the user has left.
                                      zapping: root.pendingPlayId !== "" })
    root.seekAtFloor = readout.atFloor
    if (readout.clear) { root.rewind = null; return }
    if (!readout.store) return
    root.rewind = readout.rewind
    root.rewindAtSec = Math.floor(Date.now() / 1000)
    root.behindTickSec = root.rewindAtSec
  }

  // The player went away and the queue was aimed at it: play(), stop() and
  // the socket's EOF. What `clear` resets is the reducer's answer, so the
  // list cannot drift away from the one the queue itself keeps.
  function clearRewind() {
    root.applySeekPlan(Model.seekQueueStep(root.seekState(), { kind: "clear", ctx: root.seekCtx() }))
  }

  // The IPC verbs' argument is read by Model.seekVerbSeconds (design 2.4):
  // empty is one step, a positive whole number is itself, anything else is
  // 0 and refused as bad_seconds. The service lane had written a second
  // parser here while the model was closed to it; the review found the
  // tested one dead (rule 12) and this one with different limits.

  function seekRefuse(requested, code) {
    return Model.seekRefusal(requested, code, root.rewind)
  }

  // A relative seek of `seconds` (negative is back). Returns the reply the
  // IPC verbs serialise: accepted requests say "applying" when the helper
  // was spawned now and "queued" when the press coalesced behind a run in
  // flight or the throttle; refusals carry a code. Which of those it is --
  // and the refusals, and the coalescing, and the at-floor memory -- is
  // Model.seekQueueStep's decision, not this function's.
  function seekBy(seconds) {
    return root.applySeekPlan(Model.seekQueueStep(root.seekState(),
                                                  { kind: "press", by: seconds, ctx: root.seekCtx() }))
  }

  // Back to the live edge, or as near as the cache reaches (ruling D8): the
  // helper seeks to the range end minus 0.5 s and the reply says what
  // remains. It never re-tunes; only Enter on the row reloads.
  function seekLive() {
    return root.applySeekPlan(Model.seekQueueStep(root.seekState(),
                                                  { kind: "live", ctx: root.seekCtx() }))
  }

  // Drive the queue: spawn the queued seek if the slot is free and the
  // throttle has elapsed. Called from the throttle timer and after every
  // control reply (the press drives it through seekQueueStep itself).
  function issueSeek() {
    root.applySeekPlan(Model.seekQueueStep(root.seekState(), { kind: "issue", ctx: root.seekCtx() }))
  }

  // M3-02 (PLAN-M3 decision 5). Ask the player for its tracks, selecting
  // one first when `select` is { type, id }. "" when issued, "queued" when
  // another control holds the channel, "idle" when nothing plays.
  function requestTracks(select) {
    if (!root.nowPlaying) {
      root.clearTracks()
      return "idle"
    }
    root.tracksWanted = true
    root.tracksState = "asking"
    root.tracksAsking = String(root.nowPlaying.id || "")
    root.tracksAskedFor = root.tracksAsking
    if (!root.runControl("tracks", Model.playerTracksArgv(root.socketPath, select || null))) {
      root.tracksQueued = { select: select || null }
      return "queued"
    }
    return ""
  }

  // One `status` to the player, deferred so it is issued after the reply
  // that asked for it has finished unwinding (the channel is one at a time).
  // The `status` branch above is the only place that learns pause, the
  // channel and the health verdict from the player itself.
  function askPlayerStatus() {
    if (root.userStopped || root.stopping || !root.playerUp) { root.statusQueued = false; return }
    // Keeps asking until the channel is free. runControl returns false while
    // another control holds it, and the caller used to discard that.
    root.statusQueued = !root.runControl("status", ["status", "--socket", root.socketPath])
  }

  function cancelTracks() {
    root.tracksWanted = false
    root.tracksQueued = null
    root.tracksAsking = ""
    root.tracksAskedFor = ""
    root.tracksRecoveries = 0
  }

  // The channel changed under an open picker and the play has now landed.
  function refreshTracks() {
    if (!Model.shouldRefreshTracks({
          wanted: root.tracksWanted,
          playingId: root.nowPlaying ? String(root.nowPlaying.id || "") : "",
          rowsFor: root.tracksFor,
          askedFor: root.tracksAskedFor,
          recoveries: root.tracksRecoveries })) return
    root.tracksRecoveries += 1
    root.requestTracks(null)
  }

  function clearTracks() {
    root.tracks = []
    root.tracksFor = ""
    root.tracksAsking = ""
    root.tracksAskedFor = ""
    root.tracksRecoveries = 0
    root.tracksState = "idle"
    root.tracksQueued = null
    root.tracksWanted = false
  }

  function issueQueuedTracks() {
    var queued = root.tracksQueued
    if (!queued) return
    root.tracksQueued = null
    root.requestTracks(queued.select)
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
    // D-ID-1: NO `--state-dir` here, deliberately, and this absence is
    // load-bearing rather than an oversight. A probe runs for every source
    // add, edit, switch and re-check, including ones the user then cancels.
    // Passing the flag would remap the global favourites against a playlist
    // that never became the active list. The helper touches no state file
    // without the flag, so this is safe by construction.
    sourceProbeProc.command = Model.playlistProbeArgv(root.helperPath, Model.sourceCacheDir(root.cacheDir, dirKey))
    // D-SINK-8: a candidate's URL is as credentialed as the active one, so it
    // goes in the environment too, assigned immediately before the run so a
    // re-check of source B never runs with source A's URL (the assignment
    // replaces, measured; see Model.fetchEnvironment).
    sourceProbeProc.environment = Model.fetchEnvironment(rec.url)
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
      root.sourceProbeFinished({ ok: false, id: key, channelCount: 0, groupCount: 0, reason: Model.sourceErrorMessage("unknown_source"), code: "unknown_source", host: "", cancelled: false, replacedId: "" })
      return
    }
    // R22a: a probe that ENDS in the no-write mode (started before a reload
    // that was not a state) records nothing. Its commit is a state write and
    // a key mirror, and an add or a switch that would not be kept is refused
    // here as the verbs that start one are; nothing is deleted either (the
    // start-up prune drops a directory no record names).
    if (root.stateWriteBlocked !== "") {
      root.sourceProbeFinished({ ok: false, id: key, channelCount: 0, groupCount: 0, reason: Model.sourceErrorMessage("state_unreadable"), code: "state_unreadable", host: host, cancelled: false, replacedId: "" })
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
        // R27c (D-SRC-41): the cap, against the state as it is NOW -- after any
        // merge that landed while the probe ran (a hand-run `state source add`
        // can take the last place). Until R27 the commit appended a 51st
        // record, which the next start's parse drops, silently. Refused with
        // `too_many`, told through the probe's own result; nothing recorded,
        // the probe's directory goes. An edit's old record is gone by here,
        // so a replacement never trips it.
        if (!known && Model.sourcesFull(st)) {
          root.queueCacheJob(["remove", "--key", dirKey], null)
          console.warn("omarchy-iptv: the new source was not added: Sources is full (" + Model.MAX_SOURCES + ")")
          root.sourceProbeFinished({ ok: false, id: key, channelCount: 0, groupCount: 0, reason: Model.sourceErrorMessage("too_many"), code: "too_many",
                                     host: host, cancelled: false, replacedId: "" })
          return
        }
        if (known) {
          // The same URL arrived while the probe ran (S5: a second add, or
          // the migration of an entry that named it): that record wins and
          // the counts land on it. Its own guide URL stands; R19c's
          // later-by-time landing of the form's is withdrawn with R21.
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
          // D-SINK-19: `newKey`, not `rec.key`. They differ when a colliding
          // record appeared through the CLI while the probe ran (S5, the
          // `known` branch above), and the pointer has to name the record the
          // history actually kept. The URL pair this used to pass hid that:
          // `rec.url` was right either way, so the bug could not show.
          if (!root.persistActive(newKey)) {
            console.warn("omarchy-iptv: adopted source but could not mirror the key into the bar entry")
          }
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

  // D-SINK-19, round 11 (R21). WHAT THE BAR ENTRY'S URLS MEAN: one
  // migration, then nothing.
  //
  // While the LANDED state does not carry the migration marker
  // (Model.entryMigratedOf over `landedState`), the entry's `playlistUrl` and
  // `epgUrl` are adopted exactly as they were before round 11 (R1: a URL
  // before any key is trusted; R4: a guide URL onto the active record), and
  // the marker rides the same state write (Model.adoptActiveSource). The
  // entry keeps them until that write has landed (R13, Model.retiredInputsToKeep).
  // From then on nothing on the entry is an input: a value found there is
  // refused, reported once per value (Model.entryInputNotice, through
  // reportEntryInput) and stripped by the owned write this asks for. An
  // EMPTY value is never a command, in either phase: the plugin strips the
  // keys on its own writes, the host comes to report them absent, and if
  // that meant "no active source" the host catching up would un-configure
  // the plugin. Clearing the active source is `removeSource`.
  //
  // The decision is Model.reconcileAction (what this write means) and
  // Model.adoptActiveSource (what the active source is now), so a test can
  // call both (rule 12). This function moves the session's in-memory record
  // of what it has handled (`entryInputsSeen`), reports, and hands the plan on.
  function reconcile(force) {
    // R22a: in the no-write mode the migration does not run, nothing is
    // reported and nothing is stripped -- whether the marker landed is
    // exactly what the unread file would have said.
    if (!root.stateLoaded || root.stateWriteBlocked !== "") return
    var s = root.settings
    var playlist = String(s.playlistUrl || "")
    var epg = String(s.epgUrl || "")
    var plan = Model.reconcileAction({ first: !root.reconciled, force: force === true,
                                       migrating: !Model.entryMigratedOf(root.landedState),
                                       playlist: playlist, epg: epg, seen: root.entryInputsSeen,
                                       heldFull: root.migrationHeldFull })
    root.reconciled = true
    // Every value this reconcile looked at is handled from here on: adopted
    // below, or refused and reported here. The host's stale publish of it
    // (rule 9) is neither adopted nor reported again.
    root.entryInputsSeen = Model.entryInputsSeenAfter(root.entryInputsSeen, { playlistUrl: playlist, epgUrl: epg })
    for (var i = 0; i < plan.report.length; i++) root.reportEntryInput(plan.report[i], "retired")
    // "ignore" with no guide URL to adopt is the ordinary steady state.
    if (!(plan.act === "ignore" && !plan.adoptEpg)) root.adoptActive(playlist, epg, plan)
    // R21b: a refused value leaves by the next owned write, and this is it --
    // deferred, never from inside the settings' own change notification.
    if (plan.refused.length > 0) Qt.callLater(root.stripEntryInputs)
  }

  // R21b. The owned write that takes a refused value off the bar entry: the
  // PATCH-ONLY shape (R16), every owned key at the value the plugin already
  // acts on and nothing moved, so it needs no gate -- it cannot mirror a key
  // the file does not have, and once the marker has landed the funnel strips
  // every retired key (Model.retiredInputsToKeep). The key mirror's own heal
  // stays persistActive's, under R13. On the lagging host the publish keeps
  // showing the value after the strip; the write that answers it is a no-op
  // the host answers `false` to, and Model.sameOwnWrite settles the cycle
  // (R19a). One function rather than a closure, so Qt.callLater folds a burst
  // of settings changes into one write.
  function stripEntryInputs() {
    if (!Model.entryMigratedOf(root.landedState)) return
    root.writeOwnedEntry({}, "refused bar setting", false, true)
  }

  // R21b. The one report of a value taken off the bar entry without being
  // adopted: a desktop notification and a console line, both the sentence
  // Model.entryInputNotice composes from the setting's NAME and the reason --
  // never the value (rule 5) -- and one { setting, reason } on
  // `entryInputReports` for the harness to count. Called once per value:
  // reconcile() only asks for a value `entryInputsSeen` has not seen.
  function reportEntryInput(setting, reason) {
    var notice = Model.entryInputNotice(setting, reason)
    console.warn("omarchy-iptv: " + notice.body)
    root.notify("entryInputRefused", { setting: setting, reason: reason })
    var reports = root.entryInputReports.slice()
    reports.push({ setting: String(setting), reason: String(reason) })
    while (reports.length > 32) reports.shift()
    root.entryInputReports = reports
  }

  // D-SINK-19. ONE resolver for the state load, the `shell` arrival, the
  // migration of an install whose active source was named by a URL on the
  // bar entry, and a settings change (R1).
  //
  // Model.adoptActiveSource holds the decision (and the reasoning for the
  // order it takes it in). What belongs here is only the consequences: write
  // the state if it moved -- the migration marker rides that write (R21a) --
  // mirror the key into the entry, which is also what takes the URLs out of
  // it once that write has landed, and surface an invalid migration value
  // through D16's synthesized status.
  //
  // Idempotent by construction: a second run over the same inputs finds the
  // values seen (reconcileAction) and the state's own `activeKey` answering.
  function adoptActive(playlist, epg, plan) {
    var entry = { playlistUrl: playlist, epgUrl: epg, sourceKey: String(root.settings.sourceKey || "") }
    var out = Model.adoptActiveSource(root.userState, entry, Math.floor(Date.now() / 1000), "",
                                      { adoptUrl: plan.adoptUrl === true, adoptEpg: plan.adoptEpg === true,
                                        migrating: plan.migrating === true })
    root.settingsInvalid = out.invalid
    // R21c: a guide URL the migration found with no source to guide, and one
    // that does not validate, are reported and stripped -- never held.
    if (out.noSourceEpg) root.reportEntryInput("epgUrl", "no-source")
    if (out.refusedEpg) root.reportEntryInput("epgUrl", "invalid")
    // R29d: a guide URL that came with an unusable playlist is told WITH it,
    // in one notice, and goes with it (the owned write strips both once the
    // marker has landed); never adopted onto the active source.
    if (out.invalid) root.reportEntryInput("playlistUrl", out.epgWithInvalid ? "invalid-pair" : "invalid")
    else if (out.epgWithInvalid) root.reportEntryInput("epgUrl", "invalid-pair")
    if (out.marked) console.warn("omarchy-iptv: migrating the bar entry: its URLs are read this once, and the Sources screen is where sources are kept from now on")
    if (out.marked) root.migrationAddedKey = out.added
    // R27d (D-SRC-44): the migration did not run -- Sources is full and it
    // never evicts. The entry keeps its URL (no marker, so the funnel keeps
    // it), the user is told ONCE (Model.entryInputNotice "full": no URL, no
    // label), and the next reconcile after a removal tries again.
    if (out.full) {
      root.migrationHeldFull = true
      if (!root.migrationFullTold) {
        root.migrationFullTold = true
        root.reportEntryInput("playlistUrl", "full")
      }
    } else if (out.adoptedUrl) {
      root.migrationHeldFull = false
    }
    if (out.moved) {
      // A new source starts clean: the previous source's reason and host
      // must not stay on screen while its first fetch runs (UX 4.5,
      // D-LIVE-10). The fetch itself is driven by the new cache's freshness
      // once its directory is bound (section 4.4 step 6), never from here.
      // `moved`, not "the input changed": a refused value over a working
      // source used to blank that source's status line (review P3).
      root.playlistStatus = ({ ok: false, kind: "playlist", stale: false, error: null })
      root.playlistLoadWarnings = []
      root.lastError = ""
    }
    if (out.changed) {
      root.userState = out.state
      root.saveState()
    }
    if (out.invalid) {
      // D16, narrowed by D-SINK-19: the error becomes the guide's body only
      // when there is no active source to show instead (re-applied by
      // clearSourceData when the cache directory unbinds, D-SRC-03).
      root.applyInvalidStatus()
      if (!root.invalidInputBlocks) console.warn("omarchy-iptv: ignoring an invalid playlistUrl setting; the active source is unchanged")
    }
    // The entry still carries a URL (a 0.13.x entry, a value just adopted,
    // or a refused one), or its mirrored key disagrees with the state. One
    // owned write fixes both; Model.adoptActiveSource decides (`writeEntry`).
    // Deferred: never write the host's settings from inside their own change
    // notification. persistActive saves the state again only if the key
    // actually moves, so the save above is not duplicated, and its ORDER
    // against the entry write is Model.pointerWritePlan's (R5): the entry
    // waits for the save above -- the one that carries the marker -- to
    // LAND (R13), and until it has, the funnel keeps the URLs (R21a).
    //
    // An INVALID value is written out too, and that is deliberate: a value
    // that failed validation can still carry credentials (`ftp://u:p@h/x`,
    // or a URL over the 2,048 cap), rule 5 treats whole URLs as secrets, and
    // the plugin has already reported it.
    if (out.writeEntry) {
      var key = out.key
      Qt.callLater(function() { root.persistActive(key) })
    }
  }

  // The synthesized status for an invalid configured URL (D16, SR8): the
  // UX 5.4 sentence, no host, no helper run.
  function applyInvalidStatus() {
    if (!root.invalidInputBlocks) return
    var code = String(root.settingsInvalid.code || "invalid")
    root.playlistStatus = ({ ok: false, kind: "playlist", stale: false, sourceHost: "", error: { code: code, message: Model.sourceErrorMessage(code) } })
    root.lastError = root.statusReason
  }

  // D-SRC-10's settings write-back is GONE (D-SINK-19). It existed because a
  // switch copied the new source's epgUrl INTO the bar entry, so a reconcile
  // that declined to adopt a carried-over epgUrl had to put the record's own
  // value back there. The entry carries no EPG URL now: `activeEpgUrl` reads
  // the record, the record is the only store, and there is nothing to sync.
  // The non-adoption rule itself is unchanged -- Model.reconcileSources still
  // leaves a known record's own epgUrl alone when the setting did not change
  // in the same write.

  // Section 4.4 step 4: once per state file, move the 0.1 single cache
  // into the active source's directory. Needs `shell`, because the active key
  // may still have to be migrated off the bar entry (adoptActive, D-SINK-19);
  // without a configured source the legacy files are deleted.
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
  // EPG files and logo folders of inactive sources.
  function schedulePrune() {
    if (root.pruned) return
    root.pruned = true
    root.queuePrune()
  }

  // D-LOGO-20 (R32f): the same prune again at every source switch
  // (onActiveCacheDirChanged, once the start-up one has been queued), so the
  // install-wide logo bound ARCHITECTURE section 8 item 17 states -- 1.22 GiB
  // for the active source plus 1.22 GiB for each source given logos within
  // the day -- holds at every moment of a session and not only after a
  // restart: a session that switched through fifty sources with logos on
  // used to keep all fifty folders until the next start. Keys only; the
  // helper skips a folder a running fetch holds and says so once.
  function queuePrune() {
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
    if (root.epgFetchUrl !== "" && !epgProc.running) root.refreshEpg(true)
  }

  // Reset the per-source data to "nothing known yet" so no reason, count
  // or programme of the previous source survives a swap (D-LIVE-10). An
  // invalid configured URL keeps its synthesized status: the directory
  // unbinds after reconcile() set it, and the guide must not fall back to
  // `Loading playlist...` for good (D-SRC-03).
  function clearSourceData() {
    root.channels = []
    root.channelIndex = Model.keyedMap()
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
    // The announced logo set belongs to the directory it was announced for,
    // and that directory is the one being left. Clearing it here is belt to
    // the tag's braces: a set tagged for the old directory is blank in every
    // slot already (Model.logoSlot), but it would still be COUNTED on the IPC
    // status. What a still-running fetch prints after this lands tagged for
    // ITS directory (flushLogoNames), blank in every slot, until the new
    // playlist loads and fetchLogos() stops it and starts one for this one.
    root.logoHave = ({})
    root.logoPending = []
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

  // D-SG-3: own keys into a null-prototype copy.
  function withKey(obj, key, value) {
    var out = Model.keyedMap()
    for (var k in obj) if (Model.hasOwnKey(obj, k)) out[k] = obj[k]
    out[key] = value
    return out
  }

  function withoutKey(obj, key) {
    var out = Model.keyedMap()
    for (var k in obj) if (k !== key && Model.hasOwnKey(obj, k)) out[k] = obj[k]
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
  // D-LIVE-19, and D-SINK-19 changed what reaches it. The active source's
  // in-memory data goes with the active key, so the channel list, the group
  // column and the counts are gone by the time the guide draws its setup
  // surface; without this the cleared state was only reached through the
  // cache directory unbinding, and any path that leaves the directory bound
  // left the previous source's rows behind the `No playlist configured` body.
  // The history record and the cache on disk survive (the setup surface
  // offers `Saved sources (n)`, and picking one rebinds the directory).
  //
  // What no longer arrives here is `omarchy bar set ... playlistUrl ""`: the
  // entry holds no URL to clear, and an empty input is the ordinary steady
  // state rather than a command (see reconcile). Removing the active source,
  // in the app or through the CLI's `state source remove`, is what clears the
  // pointer now. That lever is GONE and it is stated in the release notes
  // rather than quietly replaced.
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
      // M2-09 GS11 / D-GS-4: the cache the URL produced goes with the setting.
      // Without this, epg-now.json, epg-status.json and epg-window.txt outlive
      // the field, the next start loads them, and the guide-data warning they
      // carry is back in the footer for a guide source the user has removed.
      // Removing a source already deletes its whole directory; a setting the
      // user cleared gets the same treatment for the part of it that setting
      // owns. The playlist half of the cache is untouched. Since D-SINK-19 a
      // guide URL is cleared in the Sources screen (or by `state source
      // update` through the CLI): `omarchy bar set ... epgUrl ""` is an empty
      // INPUT, which is a no-op (R4), and never arrives here.
      if (root.activeSourceKey !== "") root.queueCacheJob(["epg-clear", "--key", root.activeSourceKey], null)
      return
    }
    // A cache swap in flight fetches the EPG from its freshness check.
    if (!root.pendingFreshness) root.refreshEpg(true)
  }
  // M4-01 repair 3. The resolved URL changes on its own whenever the
  // playlist cache lands (channelsMeta arrives after activeEpgUrl has long
  // since settled), so the hinted first fetch has no other trigger: this is
  // the "" -> hint edge that onActiveEpgUrlChanged cannot see.
  //
  // Only the non-empty edge is handled. The empty edge belongs to
  // onActiveEpgUrlChanged, which owns clearing the cache a SETTING produced;
  // a hint going away on a source swap must not delete anything, and
  // clearSourceData has already emptied the in-memory guide data by then.
  //
  // A settings write that sets an epgUrl moves both properties and so calls
  // refreshEpg twice; `epgDebounce` is what makes that one helper run.
  onEpgFetchUrlChanged: {
    if (root.epgFetchUrl === "" || root.pendingFreshness) return
    root.refreshEpg(true)
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
    // D-LOGO-20 (R32f): a source became active -- a switch, or the first
    // source added -- so the folders of the sources left behind are aged
    // now, not at the next start. `pruned` is set by the start-up prune
    // (schedulePrune), which this directory's FIRST value, at start, must
    // not double; the start-up one is queued in the same turn it is set.
    if (root.pruned && root.activeCacheDir !== "") root.queuePrune()
  }

  Component.onCompleted: {
    // Argv-only. Creates the private cache/state/runtime dirs before any
    // FileView write or mpv socket bind can need them (open risk 2), then
    // state.json itself with mode 0600 (stateInitProc, S-02).
    root.startStartupCheck()
    // D-SINK-18, and it is FIRST among the things that must happen before a
    // URL can be persisted, not merely early: the shield decides whether a
    // persist is allowed at all, and a persist that arrives before this run
    // exits is held rather than written (persistActive's defer branch). It is
    // independent of mkdirProc's chain on purpose -- it touches none of the
    // plugin's own directories and must not wait on them.
    root.runConfigShield()
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
    // R15 (DQ-B9): an entry mirror still HELD at exit never got its save
    // landed (a parked save never issued, a write still in flight). The entry
    // is left exactly as it is and the next start re-adopts it (R1); this
    // line is what makes that visible in the journal. The key is a key or
    // "", never a URL, and is not logged either way.
    if (root.pendingEntryKey !== null) console.warn("omarchy-iptv: exiting with a bar-entry mirror still held (state save not landed); the entry is left as it is and the next start re-adopts it")
    Quickshell.execDetached(Model.helperArgv(root.helperPath,
      Model.playerOrphanCheckArgv(root.socketPath, Quickshell.processId, Model.PLAYER_ORPHAN_GRACE_SEC)))
  }

  // ------------------------------------------------------------ files

  // The four cache views follow the active source's directory (D5). Content
  // is only ever applied from onLoaded / onLoadFailed (R1: after a path
  // change the view still reports the previous file until then).
  // D-HOST-1. Read once at load and re-read when the directory changes, which
  // is precisely the moment an update lands. printErrors stays off: a missing
  // manifest is not a user-facing error, it just means we cannot tell, and
  // staleBuild answers false for an empty version rather than guessing.
  FileView {
    id: manifestFile
    path: root.manifestPath
    // watchChanges is kept, and it is NOT what makes this work. D-HOST-2: an
    // update REPLACES the file rather than editing it -- measured, a git
    // fast-forward took manifest.json from inode 495084 to 495097 -- so a
    // watcher bound to the old inode never fires, and the notice this exists
    // for stayed silent through the exact update it was built to catch. The
    // watcher stays because an in-place edit is free to catch; the reload
    // below is what actually catches an update.
    watchChanges: true
    printErrors: false
    onLoaded: root.onDiskVersion = Model.manifestVersion(text())
    onLoadFailed: root.onDiskVersion = ""
  }

  // Re-read the manifest from its PATH, which is the only way to see a file
  // that was replaced underneath us. Called when the guide opens: that is the
  // moment the notice would be shown, so it is the moment the answer has to be
  // current, and it costs one small read against a 150 ms budget whose open
  // work measures about 20 ms.
  function recheckBuild() {
    manifestFile.reload()
  }

  FileView {
    id: channelsFile
    path: root.activeCacheDir === "" ? "" : root.activeCacheDir + "/channels.json"
    watchChanges: true
    printErrors: false
    onLoaded: {
      root.applyChannels(text(), root.activeCacheDir)
      root.finishSwitch()
      // M2-04. A refreshed playlist can name logos the cache has never seen,
      // and a switch to another source has a logo directory of its own. The
      // fetch is a no-op when the setting is off, so this costs nothing to
      // anyone who has not opted in.
      root.fetchLogos()
    }
    onLoadFailed: {
      root.applyChannels("")
      root.finishSwitch()
    }
    onFileChanged: reload()
  }

  FileView {
    id: failedFile
    path: root.failedPath
    watchChanges: true
    printErrors: false
    onLoaded: root.applyFailed(text())
    onLoadFailed: root.applyFailed("")
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
    path: root.stateFilePath
    watchChanges: true
    atomicWrites: true
    printErrors: false
    // R22a: a load is classified before anything is applied. A failed load is
    // NOT an empty state: that was the round-11 P1 (an empty state, migrated
    // and marked, written over a file that merely could not be read).
    onLoaded: root.stateLoadArrived({ loaded: true, text: stateFile.text() })
    onLoadFailed: (error) => root.stateLoadArrived({ loaded: false, error: error })
    // Fires for our own atomic write AND for a bare chmod of the file, mode
    // changed or not (measured 2026-10-11, D-SRC-15); applyUserState decides
    // whether what the reload delivers is newer than memory (R9).
    onFileChanged: reload()
    // R9 / R11 / R13: `saved` is NOT one per setText -- a burst coalesces
    // queued writes and the replaced ones raise nothing (measured, see
    // Model.stateSaveLanded) -- so the write is landed when the view's text
    // IS the last text asked for. An earlier write's `saved` changes
    // nothing: the later write reports on itself. The flag is what tells a
    // reload the file is older than memory, and the held entry mirror is
    // written only once it is clear.
    // R26b: both outcome handlers count as inside stateFile, so a save they
    // reach (settleEntryFlush -> the key mirror -> reconcile) is deferred.
    onSaved: {
      root.stateInHandler = root.stateInHandler + 1
      try {
        if (Model.stateSaveLanded(stateFile.text(), root.lastSaveText)) {
          root.stateSavesInFlight = 0
          root.stateSaveFailed = false
          root.landedState = root.lastSaveState   // R21a: what the disk holds now, the marker included
          root.recentSaves = []                   // R25a: nothing in flight, so no later reload is an echo
          // R27a: a save held for this write now reads, from a turn of its own.
          root.stateWriteWaitExpired = false
          root.endStateWriteWait(false)
        }
        root.settleEntryFlush()
        // R19d (D-SRC-18): a mirror a failed save withheld is paid by the first
        // save that lands with nothing else outstanding -- deferred, never from
        // inside the FileView's own signal, and for the key active THEN.
        if (Model.owedMirrorAction({ owed: root.entryMirrorOwed, pendingKey: root.pendingEntryKey,
                                     savePending: root.stateSavePending, savesInFlight: root.stateSavesInFlight,
                                     saveFailed: root.stateSaveFailed }) === "rewrite") {
          root.entryMirrorOwed = false
          Qt.callLater(function() { root.persistActive(root.activeSourceKey) })
        }
      } finally {
        root.stateInHandler = root.stateInHandler - 1
      }
    }
    onSaveFailed: (error) => {
      root.stateInHandler = root.stateInHandler + 1
      try {
        // R27a: and a save held for this write, failed or not, reads first.
        if (Model.stateSaveLanded(stateFile.text(), root.lastSaveText)) {
          root.stateSavesInFlight = 0
          root.stateWriteWaitExpired = false
          root.endStateWriteWait(false)
        }
        // The error is an enum, never a path or a URL. Logged on EVERY failure.
        console.warn("omarchy-iptv: state.json could not be written (error " + error + "); the in-memory state stands")
        // R13: the state write IS the switch / remove / adoption, so its
        // failure is the one a source call can have, reported here with a
        // reason of its own rather than from the call that issued it (which
        // returned when the write was issued, SR25 as amended 2026-10-12).
        // Signalled once per failure EPISODE -- the flag below is sticky until
        // a later write lands -- because one switch issues two writes (the
        // touch, then the key move) and the guide would show the line twice.
        if (!root.stateSaveFailed) {
          root.lastPersistFailure = "state_write_failed"
          root.sourcesPersistFailed("state_write_failed")
        }
        root.stateSaveFailed = true
        root.settleEntryFlush()
      } finally {
        root.stateInHandler = root.stateInHandler - 1
      }
    }
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
      // M5-01 ruling D10: a seek run does not count as busy. The three-
      // strikes restart guards a helper that never returns, which the 8 s
      // control watchdog now terminates; a slot re-occupied every few
      // hundred milliseconds by a sub-second verb under a held key is the
      // benign case it must not punish. The predicate is `root.healthBusy`,
      // ONE expression declared beside `controlRunning` above, so a node
      // test drives the exemption (Model.healthBusy) and an observer can
      // read it (F-RWD-18, F-RWD-19).
      var tick = Model.healthTick(root.healthSkips, root.healthBusy)
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
    // M5-01 (2.3): the next seek run starts no sooner than 300 ms after the
    // previous reply. A held key repeats at about 30 Hz; without this the
    // slot would spawn a helper per reply and the presses in between would
    // still coalesce, so the throttle costs no movement, only processes.
    id: seekThrottle
    interval: root.seekThrottleMs
    repeat: false
    onTriggered: root.issueSeek()
  }

  Timer {
    // M5-01: the paused count-up. 1 Hz, and only while paused with a
    // reading to count from; while playing "behind live" holds and this
    // timer does not run, so nothing re-renders.
    id: behindTick
    interval: 1000
    repeat: true
    running: Model.behindTickRunning({ paused: root.paused, rewind: root.rewind })
    onTriggered: root.behindTickSec = Math.floor(Date.now() / 1000)
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
    // R26a: the read before a save is bounded. No load in 2 s: the save goes
    // without it, as it did before R26 (counted, and one console line).
    // R29a: R28a's schedule bound here is withdrawn; the bound is this one.
    id: stateVerifyWatchdog
    interval: 2000
    repeat: false
    onTriggered: if (root.stateVerifyPending) root.finishStateVerify(true)
  }

  Timer {
    // R27a (window a): the bound on a save held for our write in flight. A
    // write the view has not reported in 2 s releases the held save to its
    // read (endStateWriteWait), which has a bound of its own; nothing here
    // writes.
    id: stateWriteWaitWatchdog
    interval: 2000
    repeat: false
    onTriggered: if (root.stateWriteWaiting) root.endStateWriteWait(true)
  }

  Timer {
    // R23c: the bound on the start-up `state init` (startStateInit). The
    // shape of playlistWatchdog: TERM, flag, and the exit handler decides --
    // plus a KILL after a grace, because nothing else would ever reap a
    // helper that ignored the TERM, and the init is the one run the whole
    // start waits on.
    // R24d: armed when mkdir starts, and it stops whichever of the two
    // start-up processes is running.
    id: stateInitWatchdog
    interval: root.stateInitTimeoutMs
    repeat: false
    onTriggered: {
      var proc = mkdirProc.running ? mkdirProc : stateInitProc.running ? stateInitProc : null
      if (proc === null) return
      console.warn("omarchy-iptv: " + (proc === mkdirProc ? "start-up mkdir" : "state init") + " exceeded " + Math.floor(root.stateInitTimeoutMs / 1000) + " s, terminating it")
      root.stateInitTimedOut = true
      proc.signal(15)
      stateInitKill.restart()
    }
  }

  Timer {
    id: stateInitKill
    interval: root.stateInitKillGraceMs
    repeat: false
    onTriggered: {
      var proc = mkdirProc.running ? mkdirProc : stateInitProc.running ? stateInitProc : null
      if (proc === null) return
      console.warn("omarchy-iptv: " + (proc === mkdirProc ? "start-up mkdir" : "state init") + " ignored the terminate signal, killing it")
      proc.signal(9)
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
    // is no unbounded wait anywhere in this feature (engineering rule 3 (dev branch)).
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
    // The same bound on the read that is NOT part of a sequence. Without it
    // an hyprctl that never exits would latch `pipPeeking` and the state
    // would stop being re-derived for the rest of the session - silently,
    // which is the shape of defect this feature already carries one of
    // (engineering rule 3 (dev branch), D-PIP-4).
    id: pipPeekWatchdog
    interval: root.pipStepMs
    repeat: false
    onTriggered: {
      if (hyprPeekProc.running) hyprPeekProc.signal(15)
      root.pipPeeking = false
      if (root.debugTiming) console.warn("omarchy-iptv pip: a state read did not answer in "
                                         + Math.floor(root.pipStepMs / 1000) + " s")
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
    function onExited(exitCode, exitStatus) { root.startupMkdirExited() }
  }

  Process {
    // S-02: FileView creates a missing file with mode 0644 and keeps the
    // mode of an existing one, so the helper pre-creates state.json 0600
    // (O_EXCL, so the check-and-create is race-free; an existing file is
    // only chmod-ed) before the first saveState(), which dirsReady gates.
    // Argv only; the helper prints one JSON line, read at the exit for its
    // `found` (R22a) and otherwise discarded.
    id: stateInitProc
    command: ["python3", root.helperPath, "state", "--state-dir", root.stateDir, "init"]
    // R22a: the reply is READ now. Its `found` is what was at the path before
    // the helper touched it, and only `absent` lets a FileNotFound load be a
    // fresh install (Model.stateInitFound).
    stdout: StdioCollector { id: stateInitStdout; waitForEnd: true }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") console.warn("omarchy-iptv state init:", Model.redactUrls(text.trim()))
    }
  }
  Connections {
    target: stateInitProc
    function onExited(exitCode, exitStatus) { root.stateInitExited(exitCode) }
  }

  Process {
    // D-SINK-18: deny group and other on the HOST's settings file before any
    // source URL is persisted into it. The twin of stateInitProc one file up,
    // for the same reason (a writer that keeps whatever mode it finds) over a
    // file this plugin does not own, which is why it refuses rather than
    // creates. Argv only, and no path argument exists to pass: the helper
    // computes the one file it may touch from $HOME, as the host does.
    id: configShieldProc
    command: Model.configShieldArgv(root.helperPath)
    stdout: StdioCollector { id: configShieldStdout; waitForEnd: true }
    stderr: StdioCollector {
      waitForEnd: true
      // Worth a line both ways: a refusal is the reason a later persist
      // fails, and a mode this plugin CHANGED on a file it does not own is
      // something the user should be able to find afterwards. Redacted like
      // every other helper channel even though this verb prints no URL.
      onStreamFinished: if (text.trim() !== "") console.warn("omarchy-iptv config shield:", Model.redactUrls(text.trim()))
    }
  }
  Connections {
    target: configShieldProc
    function onExited(exitCode, exitStatus) { root.onConfigShieldExit(configShieldStdout.text) }
  }

  Timer {
    // Drains configShieldRerun (see onConfigShieldExit): a re-check asked for
    // while a run was in flight, started once the Process is idle again.
    id: configShieldDebounce
    interval: 150
    repeat: false
    onTriggered: root.runConfigShield()
  }

  // ---- logos (M2-04). ONE process, and it only ever runs after the user has
  // read the host count and said yes. It is started from the settings change
  // and after a refresh, never from the guide opening: a fetch on open would
  // contact sixty-three hosts every time the guide is summoned.
  Process {
    id: logoFetchProc
    // D-LOGO-8: read the fetch AS IT RUNS, not at the end. The summary object
    // arrives last, so waiting for it meant a first enable showed nothing for
    // a quarter of an hour while the logos the user was looking at were
    // already on disk. Every line is one name; the last line is the summary.
    stdout: SplitParser {
      splitMarker: "\n"
      onRead: function (line) { root.onLogoLine(line) }
    }
  }
  Connections {
    target: logoFetchProc
    // D-LOGO-16: the watchdog runs exactly while the process does, whoever
    // started or stopped it (fetchLogos, the setting, a source switch).
    function onRunningChanged() {
      if (logoFetchProc.running) logoFetchWatchdog.restart()
      else logoFetchWatchdog.stop()
    }
    function onExited(exitCode, exitStatus) {
      logoFetchWatchdog.stop()
      // Nothing is reported to the user on success: the pictures appearing is
      // the report. A failure is not an error either -- a logo host being
      // down is not a reason to interrupt someone watching television -- so
      // it is logged and the rows keep their blank slots.
      if (exitCode !== 0) console.log("[iptv] logo fetch exited", exitCode)
      // Whatever the stream did not deliver, the summary already did; this
      // just makes sure the last partial batch lands -- tagged for the
      // directory THIS process was started for, which is why a batch from a
      // fetch that outlived a source switch cannot land in the new source's
      // set (Model.logoHaveMerge).
      // ...unless the setting went OFF while the process was dying: the
      // off-path cleared the set, and a trailing line delivered on the way
      // out must not repopulate it (a review found `ipc status` counting
      // logos with the switch off).
      if (root.showLogos) root.flushLogoNames()
      else root.logoPending = []
      // A fetch that was stopped because the source changed underneath it is
      // started again, for the directory that is current NOW, and never
      // before the old process is gone. Drained through a Timer, not by
      // starting the Process from inside its own exit handler: the same
      // shape as playlistRerun / epgRerun / configShieldRerun. The plan
      // (Model.logoFetchPlan) says "skip" if the setting was turned off
      // meanwhile.
      if (root.logoFetchAgain) {
        root.logoFetchAgain = false
        logoRerunDebounce.restart()
      }
    }
  }

  // Names seen on the stream but not yet folded into `logoHave`. A plain
  // array, mutated in place: nothing binds to it, and rebuilding the map per
  // line would be O(n squared) over 1,436 lines.
  property var logoPending: []

  function onLogoLine(line) {
    var name = Model.logoStreamName(line)
    if (name !== "") {
      root.logoPending.push(name)
      logoFlushTimer.restart()
      return
    }
    // The summary: authoritative, and it replaces rather than adds, so a file
    // that went away between the stream and the end is not claimed. An EMPTY
    // summary replaces too: everything swept (D-LOGO-11) means nothing
    // announced, and a length guard here once let a stale set outlive it.
    var names = Model.logoSummaryNames(line)
    if (names !== null) {
      root.logoPending = []
      root.logoHave = Model.logoHaveSet(names, root.logoFetchDir)
      root.logoFetchSeq += 1
    }
    // R30c: a run that stopped at the logo folder's ceiling or at its time
    // limit, or found another run holding the folder, exits 0 and says so
    // on a stderr this Process never reads; this is the one line that
    // reaches the journal. Counted, fixed words, no URL (rule 5).
    var notice = Model.logoSummaryNotice(line)
    if (notice !== "") console.log(notice)
  }

  Timer {
    // D-LOGO-16 (R30e): the OUTER bound on a logo fetch, which was the one
    // network-facing helper here without one. The helper stops itself
    // first -- each logo has LOGO_DEADLINE_MS and the run starts nothing
    // after LOGO_RUN_DEADLINE_MS -- and this sits a logo deadline and a
    // minute past that (Model.LOGO_FETCH_WATCHDOG_MS), so a run that stops on
    // time is read to its summary and one that cannot is terminated. Not
    // playlistWatchdog's 180 s: a first enable of 1,436 logos took about a
    // quarter of an hour (D-LOGO-8). Armed and disarmed by logoFetchProc's
    // own running state; onExited flushes what landed and leaves the next
    // run to the next refresh. No URL is logged.
    id: logoFetchWatchdog
    interval: Model.LOGO_FETCH_WATCHDOG_MS
    repeat: false
    onTriggered: {
      if (!logoFetchProc.running) return
      console.warn("omarchy-iptv: logo fetch exceeded " + Math.floor(Model.LOGO_FETCH_WATCHDOG_MS / 1000) + " s, terminating it")
      logoFetchProc.signal(15)
    }
  }

  // Batched, because every assignment to `logoHave` re-evaluates the source
  // binding of every visible row. A quarter of a second is far below the eye
  // and far above the fetch rate.
  Timer {
    id: logoRerunDebounce
    interval: 50
    repeat: false
    onTriggered: root.fetchLogos()
  }

  Timer {
    id: logoFlushTimer
    interval: 250
    repeat: false
    // The same guard the exit path has (rule 15: a sibling found by the
    // final review): a line delivered after the switch went OFF must not
    // repopulate the set through this timer either.
    onTriggered: {
      if (root.showLogos) root.flushLogoNames()
      else root.logoPending = []
    }
  }

  function flushLogoNames() {
    if (root.logoPending.length === 0) return
    // Tagged with the directory the RUNNING fetch was started for, never the
    // current one: after a source switch those differ, and the merge then
    // answers a set for the old directory, which no slot draws.
    var pending = root.logoPending
    root.logoPending = []
    root.logoHave = Model.logoHaveMerge(root.logoHave, pending, root.logoFetchDir)
    root.logoFetchSeq += 1
  }
  // Bumped when a fetch finishes, so the guide's Image sources can be asked
  // to reload: a file that was missing when the row was built is on disk now.
  property int logoFetchSeq: 0
  // `{ dir, names: { <file name>: true } }` for every logo the last fetch
  // found on disk, cached ones included, tagged with the cache directory the
  // fetch was started for (Model.logoHaveSet). `({})` means "nothing fetched
  // yet", and every slot stays blank until a fetch for THIS directory
  // answers: a set tagged for another directory is blank too, which is what
  // keeps a switch between two sources sharing a provider from pointing an
  // Image at a file in the new directory that no fetch has bounded.
  property var logoHave: ({})
  // The cache directory the fetch in `logoFetchProc` was started for. Every
  // line that process prints is tagged with THIS, not with activeCacheDir,
  // because the two differ for as long as a fetch outlives a source switch.
  property string logoFetchDir: ""
  // Set when a running fetch is signalled to make way for another directory;
  // read once by onExited, which starts the fetch again for whatever
  // directory is current then.
  property bool logoFetchAgain: false

  function fetchLogos() {
    // Guarded three times over, because this is the one function in the
    // plugin that contacts hosts the user did not choose: the setting must be
    // on, a source must be active, and a fetch must not already be running
    // FOR THIS DIRECTORY. One running for another directory is stopped and
    // started again on its exit: letting it run on announced the old
    // directory's names for minutes while the rows were the new source's,
    // and the new directory got no sweep of its own. The decision is
    // Model.logoFetchPlan, so a node test can reach it.
    var plan = Model.logoFetchPlan({ showLogos: root.showLogos, wantDir: Model.logoDirFor(root.activeCacheDir),
                                     running: logoFetchProc.running, runningDir: root.logoFetchDir })
    if (plan === "skip") return false
    if (plan === "restart") {
      root.logoFetchAgain = true
      root.logoPending = []
      logoFetchProc.signal(15)
      return false
    }
    // The tag is the LOGOS directory, through the same call `logoDir` is
    // bound through, so the guide's comparison (Model.logoSlot) can match.
    root.logoFetchDir = Model.logoDirFor(root.activeCacheDir)
    logoFetchProc.command = Model.logoFetchArgv(root.helperPath, root.activeCacheDir)
    logoFetchProc.running = true
    return true
  }

  // D-LOGO-3. Turning it ON starts a fetch; turning it OFF must STOP the one
  // already running, or the switch the user just threw goes on contacting
  // third parties for as long as the fetch takes -- which on a 1,445-channel
  // list is minutes. The `have` set is cleared in the same turn so the rows
  // blank immediately rather than after the process dies.
  onShowLogosChanged: {
    if (root.showLogos) {
      root.fetchLogos()
    } else {
      root.logoHave = ({})
      root.logoPending = []
      if (logoFetchProc.running) {
        // Through the same flag the source switch uses, so a user who throws
        // the switch off and on again before the process has died gets a
        // fetch after all: onExited asks the plan, and the plan says "skip"
        // while the setting is off and "start" once it is on again.
        root.logoFetchAgain = true
        logoFetchProc.signal(15)
      }
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

  // ---- picture in picture (M2-05). Six Processes, argv arrays only, no
  // shell anywhere: two that decide once whether PiP is offered at all,
  // three that READ the compositor (a request's clients read, its monitors
  // read, and the out-of-band peek 4.7 step 3 needs), and one that asks it
  // for something.

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
    // PIP15, and the ONE question this feature asks the compositor about
    // itself: which configuration provider is it running? Under a Lua
    // provider `hyprctl dispatch` wraps its argument as
    // `return hl.dispatch(<arg>)`, which is the form Model builds and the
    // only form this plugin knows. The answer is read once, here.
    //
    // There is no second arm. The legacy dispatcher spelling is a Lua SYNTAX
    // error under this provider (G-1), so "try the other one when the first
    // fails" is a guaranteed second failure - and it could never fire
    // anyway, because an exit code cannot report a refused effect (PIP11). A
    // fallback that cannot be triggered and would not work if it were reads
    // like safety and is worse than none.
    id: hyprInfoProc
    command: ["hyprctl", "systeminfo"]
    stdout: StdioCollector { id: hyprInfoStdout; waitForEnd: true }
    stderr: StdioCollector { waitForEnd: true }
  }
  Connections {
    target: hyprInfoProc
    function onExited(exitCode, exitStatus) {
      // Anything else - an older Hyprland on the hyprlang provider, or a
      // systeminfo this build does not print - means a compositor whose
      // dispatch language we do not speak. PiP is then hidden rather than
      // broken: `p` says so immediately instead of dispatching strings that
      // cannot parse and calling it `dispatch_failed` fifteen seconds later.
      root.pipProvider = /configProvider:\s*lua/i.test(String(hyprInfoStdout.text)) ? "lua" : "other"
      root.pipAvailable = exitCode === 0 && root.pipProvider === "lua"
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
    // The same question as hyprClientsProc, asked OUTSIDE a request, and
    // deliberately a separate process rather than a shared one. A request's
    // pipeline owns that one step by step under its own watchdog, and it
    // refuses to start a read while one is running; a peek landing in the
    // middle of a sequence would either be dropped or answer the wrong
    // phase's question. Two processes, one rule (Model.pipDeriveState).
    id: hyprPeekProc
    command: ["hyprctl", "-j", "clients"]
    stdout: StdioCollector { id: hyprPeekStdout; waitForEnd: true }
    stderr: StdioCollector { waitForEnd: true }
  }
  Connections {
    target: hyprPeekProc
    function onExited(exitCode, exitStatus) { root.pipApplyPeek(hyprPeekStdout.text) }
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
    // The paste path (D9; the only one since D-CLIP-1; R8): the helper's
    // `clipboard` verb, whose stdout is ONE JSON line of at most
    // Model.CLIPBOARD_MAX_CHARS characters of text, so this collector can
    // never hold more than the bounded reply -- the first fix ran wl-paste
    // here and collected its whole output before cutting it. Runs only on a
    // user paste, never on a clipboard change (the change-driven read was
    // the defect). The command is set per run (requestClipboard). Its
    // stderr is discarded on purpose: the verb prints nothing there by
    // contract and the text may go nowhere but the reply (rule 5). This
    // Process never carries fetchEnvironment: nothing here inherits a URL.
    id: clipboardProc
    stdout: StdioCollector { id: clipboardStdout; waitForEnd: true }
    stderr: StdioCollector { waitForEnd: true }
  }
  Connections {
    target: clipboardProc
    function onExited(exitCode, exitStatus) {
      clipboardWatchdog.stop()
      var reply = Model.parseClipboardReply(clipboardStdout.text)
      if (!reply) return
      root.clipboardText(reply.text)
    }
  }
  Timer {
    // D-CLIP-1 (R2, R8): the OUTER bound. The helper has its own deadline
    // (Model.CLIPBOARD_TIMEOUT_MS) after which it terminates wl-paste and
    // answers "timeout"; this timer sits beyond that deadline plus the kill
    // grace, so a helper that answers on time is read, and a helper that
    // cannot answer at all (a wl-paste stuck in the kernel, an interpreter
    // that never started) is killed. The bound kills a CHILD; the shell
    // never waits on it. Both numbers live in Model so they are testable.
    id: clipboardWatchdog
    interval: Model.CLIPBOARD_WATCHDOG_MS
    repeat: false
    onTriggered: {
      if (!clipboardProc.running) return
      console.warn("omarchy-iptv: clipboard helper exceeded " + Math.floor(Model.CLIPBOARD_WATCHDOG_MS / 1000) + " s, terminating it")
      clipboardProc.signal(15)
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
    // PAUSE LIVE TV. An IPC verb rather than only a guide key, because this is
    // the first action in the product you want while WATCHING -- with the
    // guide closed -- rather than while browsing. contrib/bindings.lua shows
    // the global binding.
    function pause(): string {
      var why = root.togglePause()
      if (why === "") return root.paused ? "paused" : "playing"
      return why === "busy" ? "busy" : "nothing playing"
    }
    // M5-01 LIVE REWIND (design 2.4, rulings D5, D6). `back [seconds]`,
    // `forward [seconds]`, `live`. The argument is a POSITIVE integer, so no
    // sign has to survive `omarchy-shell <id> <verb>`; empty means one step
    // (Model.REWIND_STEP_S). Replies are JSON like `channel` and `pip`: an
    // accepted request answers {"ok":true,"kind":"seek",...,"state":
    // "applying"|"queued"} and no more, because whether it MOVED is a fact
    // only the helper's read-back establishes, one process round-trip away;
    // a refusal is reported with its code and never as a success (CN15).
    // contrib/bindings.lua suggests SUPER+SHIFT+H / L / R.
    function back(seconds: string): string {
      var n = Model.seekVerbSeconds(seconds)
      return JSON.stringify(n === 0 ? root.seekRefuse(0, "bad_seconds") : root.seekBy(-n))
    }
    function forward(seconds: string): string {
      var n = Model.seekVerbSeconds(seconds)
      return JSON.stringify(n === 0 ? root.seekRefuse(0, "bad_seconds") : root.seekBy(n))
    }
    function live(): string { return JSON.stringify(root.seekLive()) }
    function stop(): string { root.stop(); return "ok" }
    function next(): string { return root.zap(1) ? "ok" : "nothing playing" }
    function previous(): string { return root.zap(-1) ? "ok" : "nothing playing" }
    function refresh(): string { root.refresh(); return "ok" }
    function status(): string { return JSON.stringify(root.statusSummary()) }
  }
}
