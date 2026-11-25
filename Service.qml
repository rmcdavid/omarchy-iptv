// The socket observer builds its Socket from a Component (spike caveat C1),
// and that nested component reaches the ids of this file (root, the retry
// timer). Bound is the semantics we want and the semantics we already have:
// there is exactly one creation context here.
pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Io
// D-HOST-11: the host's bar sections (Commons.Util.barSections), handed to
// the bar-entry walkers, and nothing else of the kit. Qualified only, as the
// host names its own; nothing here names a theme singleton unqualified.
import qs.Commons as Commons
import "Model.mjs" as Model
import "Service-pip.js" as ServicePip
import "Service-player.js" as ServicePlayer
import "Service-rewind.js" as ServiceRewind
import "Service-sources.js" as ServiceSources

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
// Most of its functions keep only a one-line forwarder here, at its old
// place; each body lives in one of the four code-behinds imported above,
// Service-pip.js, Service-player.js, Service-rewind.js, and
// Service-sources.js, which all run in this file's own scope (D-REL-14;
// SERVICE-SPLIT.md on `dev`). Edit a body there, never its forwarder.
//
// Edits to THIS file or to its code-behinds only apply after `omarchy
// restart shell`. keepLoaded carries this object over the host's plugin
// reload, and the engine keeps the component it first compiled: measured
// across a version change with code-behinds (D-REL-14's call (d)), the
// host's reload, a rescan and a disable and an enable all ran the build
// the shell first loaded, this file and every code-behind together, and
// the guide and the bar with them.
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
  // D-PLY-35: the watchdog over the verb the player slot is running, derived
  // from the helper's own bounds for THAT verb (Model.playerWatchdogMs says
  // how); with no verb running, the same Timer bounds the birth edge, 12 s.
  // It used to be one 12 s for every verb, under a start's own 14 s.
  readonly property int playerTimeoutMs: Model.playerWatchdogMs(root.playerKind)
  // Watchdog for one `play` or `status` helper run. `controlProc` was the
  // only one of the four Processes without one, and it is the one that holds
  // the single control slot: a helper that never exits blocks every later
  // zap and every health check for the rest of the session. Generous next to
  // a ~130 ms run and next to the helper's own --ipc-timeout, because this
  // is the belt and braces, not the deadline. D-SINK-102: 8 s plus the two
  // questions to the player's relay that `play` now asks, its status and the
  // load's registration (Model says why). D-PLY-39 (2026-11-18): that 10 s is
  // now the BOUND the helper runs every control verb inside, its waits on mpv
  // ending by its own deadline, and this watchdog adds the margin (15 s).
  readonly property int controlTimeoutMs: Model.playerWatchdogMs("play")
  // M5-01 (2.3): the gap between a seek reply and the next seek run.
  readonly property int seekThrottleMs: 300
  readonly property int playerProbeRetryMs: 500    // the one ambiguous-probe re-read (4.5)
  // Backstop that clears `stopping` (4.10). D-PLY-40 (2026-11-18): the
  // detached stop's own worst case with the margin (Model.playerWatchdogMs
  // says why), where it was 5 s: a stop still laddering then drew the
  // "outlived a stop" probe and a second `player stop`.
  readonly property int stopSettleMs: Model.playerWatchdogMs("stop")
  // The old backstop's moment, kept for the one case it was right about: a
  // stop the lock record superseded is refused at once, and the player is
  // looked for at 5 s, as PLY-STOP-07 has it (stopLookTimer).
  readonly property int stopLookMs: 5 * 1000
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
  readonly property var hostSettings: Model.settingsFrom(Model.findBarEntry(shell ? shell.barConfig : null, pluginId, Commons.Util.barSections))
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
  // D-SINK-112 (the review of round 5's build and its recheck, 2026-11-17):
  // what each logo authority of the channel list names, read once per list
  // while logos are on -- the authority of every logo whose scheme and
  // authority as written could name a host, whatever follows them -- so the
  // guide's column test looks a row's authority up rather than reading it
  // again on every keystroke (Model.logoAuthorityHosts).
  readonly property var logoAuthorityHosts: root.showLogos ? Model.logoAuthorityHosts(root.channels) : Model.keyedMap()
  function logoSurvey() { return ServiceSources.logoSurvey() }
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
  // D-SINK-40: the active playlist's URL decides whether a hint whose
  // LITERAL host is on this machine or a local network may be adopted (only
  // on the playlist's own host); the helper's connect-time check decides
  // the rest.
  readonly property var epgSource: Model.resolveEpgUrl({
    userUrl: root.activeEpgUrl,
    hint: root.channelsMeta ? root.channelsMeta.epgUrlHint : "",
    playlistUrl: root.playlistUrl
  })
  // D-SINK-40: what the active Sources row says beyond "EPG from playlist":
  // a hint that was refused, naming its host, or one adopted over plain http
  // under an https playlist (Model.epgHintRowState).
  readonly property var epgHintState: Model.epgHintRowState({
    userUrl: root.activeEpgUrl,
    hint: root.channelsMeta ? root.channelsMeta.epgUrlHint : "",
    playlistUrl: root.playlistUrl
  })
  // The URL every EPG fetch uses. Redacted everywhere else: `epgSourceHost`
  // is what any sink gets, and the URL itself only ever reaches the helper's
  // environment (D-SINK-8).
  readonly property string epgFetchUrl: root.epgSource.url
  readonly property string epgUrlOrigin: root.epgSource.origin
  readonly property bool epgFromPlaylist: root.epgSource.origin === Model.EPG_ORIGIN_PLAYLIST
  readonly property string epgSourceHost: root.epgSource.host
  // D-SINK-40: where a guide fetch's URL came from, for the helper's
  // connect-time policy (Model.fetchEnvironmentFor): the origin above, the
  // active playlist's URL (only its host is passed on) and the class its
  // first hop connected to, from channels.json.
  readonly property var epgProvenance: ({
    origin: root.epgUrlOrigin,
    playlistUrl: root.playlistUrl,
    playlistClass: root.channelsMeta && root.channelsMeta.sourceClass ? String(root.channelsMeta.sourceClass) : ""
  })
  // The one line that makes the provenance visible, for the Sources screen
  // and the source form: "" when the URL is the user's own.
  readonly property string epgOriginNotice: Model.epgOriginNotice(root.epgSource.origin)
  readonly property bool epgConfigured: epgFetchUrl !== ""
  // scheme + host only; safe to render anywhere
  readonly property string sourceLabel: Model.sourceLabel(playlistUrl)
  // D-SINK-109: the host the guide's loading, empty and failure lines, the
  // IPC status verb and a timed-out fetch's status name -- `[host withheld]`
  // where the Sources form would withhold it (Model.sourceShownHost).
  readonly property string sourceHost: Model.sourceShownHost(playlistUrl)

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
  // D-SRC-69 (2026-10-27). A probe asked for while a cache job that could
  // take its folder RUNS (Model.probeWaitsFor: a prune that does not keep
  // it, a removal of that key) is HELD: probingKey and the rest are set and
  // `probing` reads true, but the helper starts only at that job's exit
  // (handleCacheExit -> launchProbe); every job decided meanwhile counts it
  // in flight (cacheJobContext).
  property bool probeHeld: false
  // D-SRC-69: probes started this session, and per key the count of the
  // LAST one that started writing into sources/<key>. A cache job carries
  // the count it was queued at, so a removal can tell a folder it was asked
  // to take from one a later probe has started filling (Model.cacheJobArgs).
  // Keys only, memory only.
  property int sourceProbeSeq: 0
  property var sourceProbeClaims: ({})
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
  property var cacheQueue: []                          // FIFO of { args, onDone, seq } for cacheProc (section 4.7); a prune's args are ["prune"] until it runs (D-SRC-69)
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
  readonly property bool probing: sourceProbeProc.running || root.probeHeld
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
  readonly property var sources: Model.sourceViews(root.userState, root.activeSourceKey, root.nowSec, root.sourceErrors, root.epgFromPlaylist, root.epgHintState)

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
  // The guide-data store (D-EPG-11, R31a): the file's text and a
  // null-prototype index tvg-id -> [offset, length] into it, never a parsed
  // map of every channel. Model.epgEntry(store, id) parses one entry when
  // a row asks; Model.epgCoverage counts the index. `Model.emptyEpgStore()`
  // is the reset, never `({})`: a plain object has no index and reads as
  // "no guide data" either way, but one spelling keeps the shape one thing.
  property var epgNow: Model.emptyEpgStore()
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
  // D-SRC-71: the failed status's code, so the guide's "<reason> from
  // <host>" names no host for a local failure (Model.failureFromHost).
  readonly property string statusCode: Model.statusCode(playlistStatus)
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
  // The intent (playSeq) whose play() kept previousPlaying. A start of THAT
  // intent that answered ok spends the label: D-PLY-52's kept adoption puts
  // previousPlaying back, and a label nothing spent relabelled a later
  // refused start to a channel no player plays any more (the recheck of
  // lane RA, 2026-11-01).
  property int previousPlayingSeq: -1
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
  property bool stateInitRetried: false   // D-REL-8: the one re-run of the init has been spent
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
  // D-SRC-64: the held pair itself rests in the state (`migrationPending`,
  // Model.migrationPendingOf), never in a property here.
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
  // D-SRC-49 / D-SINK-22 (b)(c): a `state mode` asked while one runs is
  // folded into one re-run on exit (the configShieldRerun shape); the count
  // is what the harness and the IPC status read.
  property bool stateModeRerun: false
  property int stateModeRuns: 0
  // D-SINK-103 (2026-11-14): NO WRITE BEFORE THE FILE IS PRIVATE. The
  // FileView's atomic writer gives the new state.json the mode the old one
  // had (and the umask's to one it creates), so a 0644 file restored at the
  // path -- or one a link points to, in a folder other accounts can enter --
  // took every credential written after it at 0644 until the after-save
  // repair (measured, QA-RESULTS "D-SINK-103" on the dev branch). So every write waits
  // for the helper's `state private` to say the file is 0600
  // (Model.stateSavePlan's "private"). `statePrivatePending`: that run is out
  // and every save joins it. `statePrivateDone`: the call is its confirmed
  // finish, which issues the write. `statePrivateAbandoned`: its watchdog
  // failed the save at the bound, so the exit that may still come decides
  // nothing. The counts are the harness's: runs started, and runs that did
  // not confirm (no write followed). None of them ever holds a URL.
  property bool statePrivatePending: false
  property bool statePrivateDone: false
  property bool statePrivateAbandoned: false
  // `statePrivateCreated`: the run answered `created` (nothing was at the
  // path; the helper made it 0600 and empty) and our write has not landed or
  // failed yet; with `statePrivatePending` it is what makes a load of that
  // empty file ours (stateLoadArrived, Model.statePrivateEcho), counted in
  // `statePrivateEchoes`.
  property bool statePrivateCreated: false
  property int statePrivateRuns: 0
  property int statePrivateRefusals: 0
  property int statePrivateEchoes: 0
  // D-STATE-11 (2026-11-21): the refusal word whose notice this failure
  // episode has told (tellStateSaveRefused; Model.statePrivateRefusalTell),
  // "" when none. Cleared where `stateSaveFailed` is: a write that lands, or a
  // merge that leaves nothing unsaved. A fixed word, never a path or a URL.
  property string statePrivateTold: ""
  // A string property holding the LAST persist failure's code USED TO BE
  // HERE (D-SRC-67, P23 lane A's second finding, 2026-10-24, removed by
  // lane A2 the same day): set by the three failure sites and
  // the D-SRC-43 clear, and READ BY NOTHING -- not the guide, not the model,
  // not the IPC summary. The reason a failure is reported with is the
  // sourcesPersistFailed(reason) signal's argument, carried to the guide's
  // sentence by Model.persistFailureMessage; a property set in four places
  // and read in none looked like a surface and was not one. A node check
  // pins that no shipped source names it, this comment included.
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
  // D-PLY-64 (4.14): THIS Service object's half of the owner claim, beside
  // the shell's pid. The host can destroy the Service and create another in
  // the same shell (Omarchy 4.5.0's migrations did), and the pid cannot tell
  // the two apart, so each object draws its own token once, here, and passes
  // it on every verb that claims the player and on its orphan check: in
  // OMARCHY_IPTV_ARGS on the probe, the start and the restart, and on the
  // orphan check's argv, the one form execDetached starts (onDestruction
  // below). A plain property with an initializer
  // that reads nothing notifiable: evaluated once, at creation, and nothing
  // assigns it.
  property string ownerToken: Model.playerOwnerToken()
  // `stopping` keeps its name; what changed is its source (its readers are
  // many more than the four this said it had; QA-RESULTS "D-PLY-39, -40 and
  // -43" on the dev branch lists them). It is true from the keystroke until socket EOF
  // confirms the death (or the stop's own bound, stopSettleMs), and while it
  // is true a play() always starts a fresh player instead of zapping a dying
  // socket (4.10). D-PLY-40: or until a `player start` of an intent issued
  // after the stop answers ok (handlePlayerResult): under the lock that start
  // ran either after the stop's whole ladder or before the stop, which the
  // seq rule then supersedes, so the stop can no longer touch what it
  // started. And the stopped player's EOF ends it even when a play made
  // after the stop is still on its way (handlePlayerGone) -- but no EOF
  // ends it while a start that went out before this stop, inside an earlier
  // stop's settle or over a player it may ladder itself, is still in flight
  // (D-PLY-69, D-PLY-72, staleStartInFlight). D-PLY-73: and a stop the
  // shell issues itself (stopUnadoptedPlayer: a player that outlived the
  // user's stop, or one it will not adopt) opens the same settle, with its
  // own `stopSeq` and bound.
  property real stopAt: 0
  readonly property bool stopping: stopAt > 0
  // The intent number the last stop() went out with (D-PLY-40): what a
  // start's reply `seq` is compared with to tell an intent issued after it.
  property int stopSeq: 0
  // The review of 9d604cf: a start issued BEFORE the last stop answered ok
  // while that stop settles. Its player was up a moment ago, and whether the
  // stop then laddered it or was refused (`busy` behind that very start's
  // lock) nothing here can see when no socket is attached, so the backstop
  // probes for it (stopSettleTimer) rather than leave it unobserved.
  // D-PLY-75: stop() also sets it when a question about a player was open
  // as it was pressed -- a confirmation pending, a re-read owed
  // (`probeRetried`), a probe in flight, or, while the settle before it
  // still ran, this flag or a stop the shell issued itself (`stopByShell`)
  // -- so that stop's look and backstop ask it again. D-PLY-78: and such a
  // start refused or stopped by its watchdog, nothing named
  // (lookForWithdrawn).
  property bool stopOlderStartOk: false
  // D-PLY-69: the intent number the player slot's start or restart went out
  // with, and whether a stop was still settling then (issuePlayerSession).
  // D-PLY-72: and whether it went out over a player it may ladder itself --
  // the observer on one, a restart, or an owed replacement. A start that
  // went out before the last stop with either is the one an EOF cannot be
  // read past: see staleStartInFlight().
  property int sessionSeq: 0
  property bool sessionInStop: false
  property bool sessionOverPlayer: false
  property int healthSkips: 0
  // The event router's state (4.8). `entryOwners` maps mpv's own
  // playlist_entry_id to the channel that load was for, so a failure that
  // arrives after the user has zapped away still names the right channel;
  // the gate FAILS OPEN, so an unknown id degrades the name and never
  // suppresses the notification.
  property int currentEntryId: 0
  property var entryOwners: Model.keyedMap()
  property var lastEndFile: null            // { entryId, reason, fileError }
  // D-PLY-66: the "Stream failed" report that waits for the relay's answer
  // (askRelayThenRaise), null when none does.
  property var relayAskReport: null
  property bool playerIdle: false           // observed idle-active, informational
  property string playerKind: ""            // which player verb is in flight
  property bool probeRetried: false         // the one ambiguous-probe re-read (4.5)
  // D-SINK-71: the TLS reading's `migrated` on the ambiguous first probe, read
  // only by the retry that follows it (while `probeRetried` is true). The
  // first probe migrates and marks the player, and the retry reads the mark
  // (D-SINK-72); the memo is kept for a player whose mark mpv refused, where
  // the retry would read nothing left to do. The restart episode needs the
  // first answer, as tlsReloadPending keeps it for a player of this build.
  property bool probeRetryMigrated: false
  // `playSeq` as it stood when the probe in flight was ISSUED (4.10). A
  // probe answers about the world it was sent into; an intent issued after
  // it - a play from the guide, or over IPC one frame after the shell came
  // back - is the newer word and must not be overruled by the older answer.
  property int probeSeq: 0
  // D-PLY-76: `playSeq` as it stood when an ambiguous answer armed the one
  // re-read (probeRetryTimer). An intent issued since -- a play, a stop --
  // is the newer word over that answer as much as over a probe in flight,
  // so the re-read is not sent (probeOverruled).
  property int probeRetrySeq: 0
  property bool reconcilePending: false     // resolve nowPlaying once the cache lands
  // D-SINK-16: this shell adopted a player that was not verifying the stream's
  // certificate, the probe has migrated it, and the channel it is already
  // streaming must be re-established before anything else is sent to it. Set
  // from the probe's verdict, never cleared by it (an ambiguous first probe
  // migrates, and the retry reports it again from the mark the first left
  // unless mpv refused the mark, D-SINK-72), and spent by
  // reestablishForTls().
  property bool tlsReloadPending: false
  property string playerSourceKey: ""       // the source the recovered stash belongs to
  property int playerSocketError: 0         // last QLocalSocket::LocalSocketError, diagnostics only
  // A stop whose EOF never came, so the ladder did not end the player. The
  // stop is detached and its reply is by design unobservable, so this is
  // the only way to notice one that was refused (4.9, 4.10). D-PLY-75: a
  // stop pressed while it is set takes it over (stop()), since that stop
  // makes the answer stale.
  property bool stopConfirmPending: false
  // The review of 9d604cf (F-PLY-3): that probe is the early look's
  // (stopLookTimer), which stops the player only when the lock record shows
  // the stop superseded, never while the stop's own record stands.
  property bool stopConfirmLook: false
  // D-PLY-73: the settle running waits on a stop issued on the backstop's
  // own probe (applyProbe), so its backstop ends it and looks no further. Every
  // other stop -- the user's, and one the shell issues itself
  // (stopUnadoptedPlayer) -- is looked at once by its backstop, and this is
  // what ends that chain: without it a player that outlives every stop drew
  // a probe and a stop once a backstop for ever, `stopping` true nearly all
  // the while. Set only after such a stop and cleared by both openers of a
  // settle (stop() and stopUnadoptedPlayer), which are the only callers of
  // the backstop's restart(), so the backstop reads what the settle it ends
  // was opened with.
  property bool stopFromBackstop: false
  // D-PLY-75: the settle running was opened by a stop the shell issued itself
  // (stopUnadoptedPlayer), always over a player a probe or an adoption found
  // up. Read only by stop(): a user's stop pressed while it settles inherits
  // that player, so its look and backstop look for it even with nothing
  // attached. Set there, cleared by stop().
  property bool stopByShell: false
  // Whose failure has already been toasted for this play. `player start`'s
  // own first-load window and socket EOF are two independent detectors of
  // the same dead stream (4.8 signals 1 and 3) and either can win the race;
  // this keeps the user's toast count at one.
  property string notifiedFailureId: ""
  // D-HOST-5 (owner, 2026-10-28): one slot per notice kind -- the id the
  // notification server returned for the kind's last card, whether a post of
  // it is in flight, and the notice held behind it (Model.notifyPost). In
  // memory only: the server is this shell's own and its ids restart with it.
  property var notifySlots: Model.keyedMap()
  // D-PLY-35: set by playerWatchdog when it TERMs the helper, read once by
  // handlePlayerResult. A start or restart the watchdog ended has answered
  // nothing about the player: it may have spawned one and loaded the channel
  // into it before the signal landed (measured).
  property bool playerTimedOut: false
  // D-PLY-35: a start the watchdog ended ({kind, intent}: its verb and the
  // channel it was for) while the reattach probe finds out what it left;
  // null otherwise. Settled by settleTimedOutPlay() on the probe's answer.
  property var timedOutPlay: null
  // Restart on adoption (owner, 2026-10-31 and 2026-11-01): the reattach
  // found a player ANOTHER build of this plugin launched (the probe's
  // `launch`), adopted it for a hold, and owes its replacement -- one
  // automatic `player start --keep-pause` of the same channel once the
  // channel list is applied (Model.olderRestartDisposition). null when
  // nothing is owed; else { seq, unsafe, spent, expired, migrated, player }:
  // the intent the restart was issued under, whether the player read unsafe,
  // whether the restart was issued (or deferred: it plays on, fed nothing,
  // until the user's next channel change replaces it), whether the hold ran
  // out, whether the probe had to change its settings in place -- the
  // stream it has open may predate them, so the hold's end does not defer it
  // (D-SINK-71, Model.olderRestartDisposition) -- and which player it was
  // opened for, so a later probe of that same player keeps it (D-SINK-73,
  // Model.olderRestartOpen). Opened by Model.olderRestartOpen and rebuilt
  // only through Model.olderRestartWith, which carries every field.
  property var olderRestart: null
  readonly property bool olderRestartOwed: !!root.olderRestart
  // The four zap sites read this in place of playerUp: while a restart is
  // owed a channel change is a `player start`, which replaces the older
  // player in the same call (the helper refuses to feed it anyway).
  readonly property bool zapReady: root.playerUp && !root.olderRestartOwed
  // This shell already restarted a player another build launched and the
  // restart answered ok: a later probe that reads the replacement as another
  // build's again is not restarted twice (design 4.4.3).
  property bool olderRestartDelivered: false
  // D-PLY-52: the observer the player slot's start or restart was issued
  // over, when it was attached to a live player then; null otherwise. A
  // refusal that finds this SAME observer still attached was refused before
  // the helper laddered anything (a laddered player's EOF releases it, and
  // every later attempt is a fresh object), so the player it watches plays on.
  property var sessionSocket: null
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
  // TWO GATE RESULTS SHAPE EVERYTHING BELOW -- and the PiP functions, which
  // are in Service-pip.js since D-REL-14, each reached through its forwarder
  // below -- and both of them override the design's own text (section 14,
  // rulings PIP10 and PIP11):
  //
  //   PIP11. An exit code cannot detect failure here. `hyprctl dispatch`
  //   answers rc 0 `ok` for a dispatch aimed at an address that does not
  //   exist, and a real refusal arrives as `warning:` TEXT on stdout, also
  //   with rc 0 (QA-RESULTS D-PIP-2). rc is non-zero only for a Lua parse
  //   error - that is, only for a bug in our own string. So SUCCESS IS
  //   DEFINED IN EXACTLY ONE PLACE: pipVerify() compares a fresh read of
  //   `hyprctl -j clients` against what was asked for. Nothing in this file
  //   or in Service-pip.js may branch on a dispatch's exit status or on its
  //   output. The stdout of a step is captured for the journal and for
  //   nothing else.
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

  function play(id, keepOpen, launchedFrom) { return ServicePlayer.play(id, keepOpen, launchedFrom) }

  function playArgs(key) { return ServicePlayer.playArgs(key) }

  function stop() { return ServicePlayer.stop() }

  function restartPlayer() { return ServicePlayer.restartPlayer() }

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

  function zap(delta) { return ServicePlayer.zap(delta) }

  function channelByNumber(text) { return ServicePlayer.channelByNumber(text) }

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
    // F-SINK-14: the reply prints the name the bar and the row print.
    var name = Model.sinkText(found.name)
    // play() refuses when mpv is missing or the entry has no URL. Reporting
    // that as ok:true would be a lie about the one thing this verb exists to
    // do; the success shape is unchanged for the case it describes.
    if (!root.play(id, true, "")) {
      return { ok: false, kind: "channel", id: id, chno: label, name: name,
               error: { code: "play_failed", message: "could not start channel " + asked } }
    }
    return { ok: true, kind: "channel", id: id, chno: label, name: name }
  }

  function focusPlayer() { return ServicePlayer.focusPlayer() }

  function dispatchFocus(address) { return ServicePlayer.dispatchFocus(address) }

  // ------------------------------------------------------------ picture in picture (M2-05)

  function togglePip() { return ServicePip.togglePip() }

  function requestPip(mode) { return ServicePip.requestPip(mode) }

  function pipRefuse(requested, code) { return ServicePip.pipRefuse(requested, code) }

  function pipReadClients() { return ServicePip.pipReadClients() }

  function pipReadMonitors() { return ServicePip.pipReadMonitors() }

  function pipApplyClients(text) { return ServicePip.pipApplyClients(text) }

  function pipApplyMonitors(text) { return ServicePip.pipApplyMonitors(text) }

  function pipPlanRound() { return ServicePip.pipPlanRound() }

  function pipRunNextStep() { return ServicePip.pipRunNextStep() }

  function pipNoteStep(text, exitCode) { return ServicePip.pipNoteStep(text, exitCode) }

  function pipCheck(live) { return ServicePip.pipCheck(live) }

  function pipFinish(ok, code) { return ServicePip.pipFinish(ok, code) }

  function pipReset() { return ServicePip.pipReset() }

  function notePlayerPid(value) { return ServicePip.notePlayerPid(value) }

  function pipPeek() { return ServicePip.pipPeek() }

  function pipApplyPeek(text) { return ServicePip.pipApplyPeek(text) }

  function pipWriteMpv(intent, live) { return ServicePip.pipWriteMpv(intent, live) }

  function pipRequestSnapshot(sock) { return ServicePip.pipRequestSnapshot(sock) }

  function pipNoteReply(line) { return ServicePip.pipNoteReply(line) }

  function pipConfig() { return ServicePip.pipConfig() }

  function refreshPlaylist(force) { return ServiceSources.refreshPlaylist(force) }

  function refreshEpg(force) { return ServiceSources.refreshEpg(force) }

  // D-HOST-5 (owner, 2026-10-28). Every notice the plugin posts goes through
  // here, and through its kind's slot (Model.notifyPost): the post runs as a
  // Process of its own, `omarchy-notification-send -p` prints the id the
  // server returned, and the next post of that kind sends it back as `-r`,
  // so a repeated notice refreshes its card in place instead of stacking a
  // new one. Until D-HOST-5 the post was detached with a fixed `-r`, which
  // Omarchy's server never replaces. A post of a kind already in flight is
  // held and goes out when that one answers; kinds never wait on each other.
  function notify(event, params) {
    var step = Model.notifyPost(root.notifySlots, event, params)
    root.notifySlots = step.slots
    if (step.argv) root.runNotify(String(event), step.argv)
  }

  // One post of `event`: a Process from notifyComponent, argv only (the
  // wrapper is busctl underneath, no shell). Bounded by its own watchdog
  // (Model.NOTIFY_POST_TIMEOUT_MS). Should the object not be made, the post
  // still goes out, detached and untracked as every post did before
  // D-HOST-5 -- a notice is never dropped for want of its id.
  function runNotify(event, argv) {
    var run = notifyComponent.createObject(root, { kind: event })
    if (run === null || run === undefined) {
      console.warn("omarchy-iptv: could not make a notification process; posting it untracked")
      Quickshell.execDetached(argv)
      root.handleNotifyExit(null, event, 1, 0, "")
      return
    }
    run.command = argv
    run.running = true
  }

  // A post answered (or was ended). The slot keeps the id it printed, or
  // none, and a notice of the same kind held meanwhile goes out with it.
  // `exitStatus` non-zero is a crash or a signal (the watchdog's TERM): its
  // stdout is no answer.
  function handleNotifyExit(run, event, exitCode, exitStatus, text) {
    var step = Model.notifyAnswered(root.notifySlots, event, text, Number(exitStatus) === 0 ? exitCode : -1)
    root.notifySlots = step.slots
    if (run) run.destroy()
    if (step.argv) root.runNotify(event, step.argv)
  }

  // The post's watchdog fired: a post still running is ended, and its exit
  // frees the slot (handleNotifyExit) with no id kept.
  function notifyOverdue(run) {
    if (!run || !run.running) return
    console.warn("omarchy-iptv: a notification post exceeded " + Math.floor(Model.NOTIFY_POST_TIMEOUT_MS / 1000) + " s, terminating it")
    run.signal(15)
  }

  // `nowPlaying` as the IPC reports it: the shipped literal plus the playing
  // channel's number (3.3). Null when nothing plays, exactly like the property.
  // F-SINK-14: composed by Model.ipcNowPlaying, which redacts the name, the
  // group and the scope it was launched from as the bar and the row do.
  function nowPlayingSummary() {
    return Model.ipcNowPlaying(root.nowPlaying, root.nowPlayingChno)
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

  function sourceResult(ok, code, message, id, field) { return ServiceSources.sourceResult(ok, code, message, id, field) }

  // `persistFailureResult` USED TO BE HERE (D-SINK-18): the result for a
  // refused entry write, returned by removeSource. Gone with R13 / SR25 as
  // amended: a source call reports on the STATE write, which is issued
  // synchronously and cannot be refused, and a refused entry mirror is
  // logged and repaired on the next start. The failure a source call can
  // still have is the state write failing later, which stateFile's
  // saveFailed reports through sourcesPersistFailed("state_write_failed").

  function sourcesReady() { return ServiceSources.sourcesReady() }

  function addSource(fields) { return ServiceSources.addSource(fields) }

  function updateSource(id, fields) { return ServiceSources.updateSource(id, fields) }

  function removeSource(id) { return ServiceSources.removeSource(id) }

  function retryHeldMigration() { return ServiceSources.retryHeldMigration() }

  function switchSource(id) { return ServiceSources.switchSource(id) }

  function buildXtreamSource(fields) { return ServiceSources.buildXtreamSource(fields) }

  function sourceForEdit(id) { return ServiceSources.sourceForEdit(id) }

  function retrySource(id) { return ServiceSources.retrySource(id) }

  function cancelProbe() { return ServiceSources.cancelProbe() }

  function requestClipboard() { return ServiceSources.requestClipboard() }

  // ------------------------------------------------------------ internals

  function applyChannels(text, source) { return ServiceSources.applyChannels(text, source) }

  function adoptIdScheme(remap) { return ServiceSources.adoptIdScheme(remap) }

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
    // D-SINK-103: the EMPTY file `state private` creates when nothing is at
    // the path is ours, made for the write that follows it, and a view that
    // watches the folder may load it first (a file that appears reloads).
    // Read as a state it is "unparsed", which mid-session is the no-write
    // mode -- for a file this shell made a moment ago -- so such a load
    // decides nothing (Model.statePrivateEcho).
    if (Model.statePrivateEcho({ pending: root.statePrivatePending, created: root.statePrivateCreated, result: result })) {
      root.statePrivateEchoes = root.statePrivateEchoes + 1
      return
    }
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
                                      initFound: root.stateInitFound, retried: root.stateLoadRetried,
                                      initRetried: root.stateInitRetried })
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
    } else if (d.act === "reinit") {
      // D-REL-8: the init answered nothing readable (an empty or partial stub
      // mid-update, a stub refusing its parts): run it once more, after a
      // moment, under the start-up bound again. Its exit lands here again
      // with a verdict, or with "unknown" a second time and today's path.
      root.stateInitRetried = true
      stateInitRetry.restart()
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
    // D-STATE-11's review (2026-11-21): this card goes out on the refused
    // notice's id and replaces it, so the refusal told is told no longer, and
    // one after the block lifts is told again (tellStateSaveRefused).
    root.statePrivateTold = ""
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
    // D-SRC-33: and the user told once per merge that kept the other
    // program's version of something over a change made here (the journal
    // line was the only word until now): Model.mergeConflictNotice's
    // sentences, through the one notify path -- a field name, never a
    // value, and since D-SINK-69 never a source's key, which the journal
    // line above keeps. The in-flight and parked branches reach here alike.
    if (merged.conflicts.length > 0) root.notify("mergeConflict", { conflicts: merged.conflicts })
    // F1: the record this session's migration added did not land as ours --
    // another program took the place it used ("full"), or added the same
    // playlist itself ("changed"). No marker was carried; the merge re-parked
    // the pair from the record it dropped (D-SRC-64; the entry is empty by
    // now), and the migration is HELD: the reconcile below retries it
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
    // D-SRC-43: the merge equals the other program's file and nothing of
    // ours is in the air -- the disk holds memory, so a failure flag the
    // save that never landed raised has nothing left to be about: cleared
    // here, with the burst record (no echo of ours is coming). The owed
    // entry mirror (R19d) is NOT paid here; it is paid by the next landed
    // save, as before -- owedMirrorAction is asked only from onSaved.
    if (Model.mergeLeavesNothingUnsaved(merged.state, theirs, { savesInFlight: root.stateSavesInFlight })) {
      if (root.stateSaveFailed) console.warn("omarchy-iptv: the other program's write holds everything this session has; the earlier failed save is no longer pending")
      root.stateSaveFailed = false
      root.statePrivateTold = ""   // D-STATE-11: the episode is over
      root.recentSaves = []
    }
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
                                     waitExpired: root.stateWriteWaitExpired,
                                     privatePending: root.statePrivatePending, privateDone: root.statePrivateDone })
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
    if (plan === "private") {
      // D-SINK-103: the read is done and the write decided -- and the file
      // is made 0600 BEFORE it, by the helper (requestStatePrivate). The
      // write is issued by that run's confirmed reply (finishStatePrivate),
      // so no text of ours lands in, or passes through, a file other
      // accounts can read; a run that does not confirm writes nothing.
      root.stateSavePending = true
      root.requestStatePrivate()
      return
    }
    // R27a: no write is issued without its read any more, so this counter
    // stays 0; it is kept, under its R26 name, so the harness can say so.
    // D-SINK-103: the write now comes from the `state private` reply that
    // followed the read, so that finish counts as the read's too.
    if (root.stateSavesInFlight > 0 && !root.stateVerifyDone && !root.statePrivateDone) root.stateVerifySkipped = root.stateVerifySkipped + 1
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

  function applyPlaylistStatus(text) { return ServiceSources.applyPlaylistStatus(text) }

  function adoptSourceStats(status) { return ServiceSources.adoptSourceStats(status) }

  function applyEpgStatus(text) { return ServiceSources.applyEpgStatus(text) }

  function setEpgStatus(status) { return ServiceSources.setEpgStatus(status) }

  function applyEpgNow(text) { return ServiceSources.applyEpgNow(text) }

  function helperTimeoutStatus(kind, stale) { return ServiceSources.helperTimeoutStatus(kind, stale) }

  // D-SINK-47, D-SINK-48 (2026-10-29): the one way a helper is started on a
  // Process. Model.helperSpawn takes the private values -- a cache folder
  // named by a key, a channel id, a scope, the user's mpv tokens -- off the
  // argv, where /proc shows them to every account, and into the environment;
  // the command and the environment are assigned together, immediately
  // before the run, every run, because an assignment REPLACES the previous
  // value on the same Process (measured on Quickshell 0.3.1, see
  // Model.fetchEnvironment) and that is what keeps one run's values out of
  // the next. `environment` is the run's own (a fetch's URL and provenance,
  // rule 5); {} for every other run.
  function runHelper(proc, argv, environment) {
    var spawn = Model.helperSpawn(argv, environment)
    proc.command = spawn.command
    proc.environment = spawn.environment
    proc.running = true
  }

  function runPlaylistHelper() { return ServiceSources.runPlaylistHelper() }

  function runEpgHelper(nowOnly) { return ServiceSources.runEpgHelper(nowOnly) }

  function runControl(kind, args) { return ServicePlayer.runControl(kind, args) }

  function handleControlResult(text) { return ServicePlayer.handleControlResult(text) }

  function drainPendingPlay() { return ServicePlayer.drainPendingPlay() }

  function reapplyIntent(id) { return ServicePlayer.reapplyIntent(id) }

  function checkPlayerChannel(status) { return ServicePlayer.checkPlayerChannel(status) }

  // ------------------------------------------------------------ the detached player
  //
  // ARCHITECTURE-PLAYER.md sections 4.4 to 4.10, with the shape corrections
  // of section 13 (the socket observer is a Component, one fresh object per
  // attempt). Nothing in this block, or in the functions in Service-player.js
  // its forwarders reach (D-REL-14), ever execs mpv: `player start` is
  // idempotent - it adopts a live player or spawns one under a lock - so
  // every call here is safe to repeat and none of them is a spawn gate.

  function startPlayer(channel) { return ServicePlayer.startPlayer(channel) }

  function issuePlayerSession(verb, channel, fromRung) { return ServicePlayer.issuePlayerSession(verb, channel, fromRung) }

  function staleStartInFlight() { return ServicePlayer.staleStartInFlight() }

  function lookForWithdrawn() { return ServicePlayer.lookForWithdrawn() }

  function runPlayer(kind, args) { return ServicePlayer.runPlayer(kind, args) }

  function runPlayerProbe() { return ServicePlayer.runPlayerProbe() }

  function handlePlayerResult(text) { return ServicePlayer.handlePlayerResult(text) }

  function playerFirstLoadFailed(first) { return ServicePlayer.playerFirstLoadFailed(first) }

  function probeOverruled() { return ServicePlayer.probeOverruled() }

  function applyProbe(text) { return ServicePlayer.applyProbe(text) }

  function openOlderRestart(unsafe, migrated, pid, stash) { return ServicePlayer.openOlderRestart(unsafe, migrated, pid, stash) }

  function endOlderRestart() { return ServicePlayer.endOlderRestart() }

  function reestablishAdopted() { return ServicePlayer.reestablishAdopted() }

  function refusedWhilePlaying(status, code, reason) { return ServicePlayer.refusedWhilePlaying(status, code, reason) }

  function reestablishForTls() { return ServicePlayer.reestablishForTls() }

  function markDeadSession() { return ServicePlayer.markDeadSession() }

  function noteSessionOutcome(outcome) { return ServicePlayer.noteSessionOutcome(outcome) }

  function stopForeignPlayer() { return ServicePlayer.stopForeignPlayer() }

  function stopUnadoptedPlayer(outcome) { return ServicePlayer.stopUnadoptedPlayer(outcome) }

  function reconcileNowPlaying() { return ServicePlayer.reconcileNowPlaying() }

  // ---- the socket observer (spike caveats C1 to C10)
  //
  // A Quickshell Socket whose connect attempt fails is bricked permanently,
  // and re-arming one that is already connected arms a hidden zero-delay
  // auto-reconnect that bricks it the moment mpv dies. So: one fresh object
  // per attempt, never reused, never re-armed.

  function socketAttached() { return ServicePlayer.socketAttached() }

  function releasePlayerSocket() { return ServicePlayer.releasePlayerSocket() }

  function attachPlayerSocket() { return ServicePlayer.attachPlayerSocket() }

  function armPlayerSocket() { return ServicePlayer.armPlayerSocket() }

  function socketWrite(sock, command, requestId) { return ServicePlayer.socketWrite(sock, command, requestId) }

  function onPlayerAttached(sock) { return ServicePlayer.onPlayerAttached(sock) }

  function onSocketError(err) { return ServicePlayer.onSocketError(err) }

  function handlePlayerLine(line) { return ServicePlayer.handlePlayerLine(line) }

  function rememberEntry(entryId, target) { return ServicePlayer.rememberEntry(entryId, target) }

  function raiseStreamFailure(target, reason) { return ServicePlayer.raiseStreamFailure(target, reason) }

  function raiseLocalPlayFailure(target, reason) { return ServicePlayer.raiseLocalPlayFailure(target, reason) }

  function settleTimedOutPlay(found) { return ServicePlayer.settleTimedOutPlay(found) }

  function raisePlayerStopped(target, reason) { return ServicePlayer.raisePlayerStopped(target, reason) }

  function raiseOutputFailure(target, output, reason) { return ServicePlayer.raiseOutputFailure(target, output, reason) }

  function askRelayThenRaise(report) { return ServicePlayer.askRelayThenRaise(report) }

  function handleRelayAnswer(text) { return ServicePlayer.handleRelayAnswer(text) }

  function raiseDeath(report) { return ServicePlayer.raiseDeath(report) }

  function rememberStderr(line) { return ServicePlayer.rememberStderr(line) }

  function handlePlayerGone() { return ServicePlayer.handlePlayerGone() }

  function handlePlaylistExit(text) { return ServiceSources.handlePlaylistExit(text) }

  function handleEpgExit(text, nowOnly) { return ServiceSources.handleEpgExit(text, nowOnly) }

  // ------------------------------------------------------------ sources internals

  function persistActive(key) { return ServiceSources.persistActive(key) }

  function flushPendingEntry() { return ServiceSources.flushPendingEntry() }

  function persistEntryKey(key) { return ServiceSources.persistEntryKey(key) }

  function refuseUnsafePersist() { return ServiceSources.refuseUnsafePersist() }

  function writeActive(key) { return ServiceSources.writeActive(key) }

  function writeOwnedEntry(overrides, what, announce, patchOnly) { return ServiceSources.writeOwnedEntry(overrides, what, announce, patchOnly) }

  // `applyOwnWrite(key)` USED TO BE HERE. Nothing called it (dead since
  // b2a4986; the D-SINK-19 review found it carrying six live assertions). The
  // own-write record is made where the write is made, in writeOwnedEntry.

  function runConfigShield() { return ServiceSources.runConfigShield() }

  // D-SRC-49 / D-SINK-22 (b)(c). Start `state mode`, or remember to start it
  // again: `running = true` on a running Process is not a queue, so a second
  // landed save while one runs is folded into one re-run on exit -- the same
  // shape as runConfigShield. Never through cacheProc: that slot's command is
  // `cache --cache-dir`, and a state-file repair on the cache verb is the join
  // D-ID-1 keeps apart. Bounded by its own TERM-only watchdog (D-SRC-37 (c)).
  function requestStateMode() {
    if (root.stateWriteBlocked !== "") return
    if (stateModeProc.running) {
      root.stateModeRerun = true
      return
    }
    stateModeProc.command = Model.stateModeArgv(root.helperPath, root.stateDir)
    root.stateModeRuns = root.stateModeRuns + 1
    stateModeProc.running = true
    stateModeWatchdog.restart()
  }

  // The verb's answer: a `changed` is a mode this plugin repaired on its own
  // file, worth a line the user can find afterwards; `kept` is the steady
  // state and silent. A stopped run prints nothing and changes nothing.
  function handleStateModeExit(exitCode, text) {
    stateModeWatchdog.stop()
    var reply = Model.stateModeReply(text)
    if (reply && (reply.file === "changed" || reply.folder === "changed")) {
      console.warn("omarchy-iptv: state.json's mode was repaired after a save (file " + reply.file + ", folder " + reply.folder + ")")
    } else if (!reply && exitCode !== 0) {
      console.warn("omarchy-iptv: state mode exited " + exitCode + "; state.json keeps whatever mode it has until the next save or start")
    }
    if (root.stateModeRerun) {
      root.stateModeRerun = false
      Qt.callLater(root.requestStateMode)
    }
  }

  // D-SINK-103. Start `state private` for the save the read has decided
  // (saveState's "private"), on its own Process, bounded by its own
  // watchdog. Every save asked while it runs joins it (the plan's "join"),
  // so one run covers them all and the write that follows carries whatever
  // memory holds by then. A Process still running here is a run the
  // watchdog already gave up on that no signal has ended: no second run can
  // start on it, and no write goes without one, so this save fails now,
  // told, rather than waiting on a run nothing bounds.
  function requestStatePrivate() {
    if (statePrivateProc.running) {
      root.finishStatePrivate({ ok: false, why: "still-running" })
      return
    }
    root.statePrivatePending = true
    root.statePrivateRuns = root.statePrivateRuns + 1
    statePrivateProc.command = Model.statePrivateArgv(root.helperPath, root.stateDir)
    statePrivateProc.running = true
    statePrivateWatchdog.restart()
  }

  // The run's exit, with its one line (Model.statePrivateReply reads it, and
  // fails closed). A run its watchdog abandoned has had its save failed
  // already; its exit decides nothing.
  function handleStatePrivateExit(exitCode, text) {
    statePrivateWatchdog.stop()
    if (root.statePrivateAbandoned) {
      root.statePrivateAbandoned = false
      return
    }
    if (!root.statePrivatePending) return
    root.finishStatePrivate(Model.statePrivateReply(text, exitCode))
  }

  // The write the read decided, issued only on a confirmed reply, from this
  // turn (the Process's exit, never one of stateFile's own handlers, R26b),
  // so the gap between the file being 0600 and the writer opening it is the
  // helper's exit, this handler and the write job's start, not one turn:
  // about 20 ms, measured to the writer's link, which follows its open
  // (D-SINK-103, spikes/state-private/RESULT-2026-11-14-interval.txt).
  // Anything else writes nothing: the save fails the way a failed
  // write fails (noteStateWriteFailed: the in-memory state stands, the user
  // is told once per episode, the next change writes it).
  function finishStatePrivate(reply) {
    root.statePrivatePending = false
    statePrivateWatchdog.stop()
    if (!reply || reply.ok !== true) {
      root.statePrivateRefusals = root.statePrivateRefusals + 1
      root.statePrivateCreated = false
      root.stateSavePending = false
      // A fixed word, never a path or a URL (Model.statePrivateReply).
      console.warn("omarchy-iptv: state.json was not written: it could not be made private first (" + String(reply ? reply.why : "no-reply") + "); the in-memory state stands")
      root.noteStateWriteFailed()
      root.tellStateSaveRefused(reply ? reply.why : "")
      return
    }
    // A mode this plugin changed, or a file it created, is worth a line the
    // user can find afterwards; `kept` is the steady state and silent.
    if (reply.file !== "kept") {
      console.warn("omarchy-iptv: state.json was made private before a save (file " + reply.file + ")")
    }
    // A load that came in meanwhile set the no-write mode: this run's answer
    // is the save's, so it is refused, as the read's finish refuses it.
    if (root.stateWriteBlocked !== "") {
      root.statePrivateCreated = false
      root.stateSavePending = false
      root.stateWritesRefused = root.stateWritesRefused + 1
      return
    }
    if (!root.stateSavePending) {
      root.statePrivateCreated = false
      return
    }
    // The empty file the run created is ours until this write lands or fails
    // (onSaved / onSaveFailed clear it with the burst's last report).
    root.statePrivateCreated = reply.file === "created"
    root.statePrivateDone = true
    try { root.saveState() } finally { root.statePrivateDone = false }
  }

  // A state write that did not happen, from either place that learns it:
  // stateFile's saveFailed and a `state private` that did not confirm
  // (D-SINK-103). R13: the state write IS the switch / remove / adoption, so
  // its failure is the one a source call can have, signalled once per
  // failure EPISODE -- the flag is sticky until a later write lands --
  // because one switch issues two writes (the touch, then the key move) and
  // the guide would show the line twice.
  function noteStateWriteFailed() {
    if (!root.stateSaveFailed) {
      root.sourcesPersistFailed("state_write_failed")
    }
    root.stateSaveFailed = true
    root.settleEntryFlush()
  }

  // D-STATE-11 (2026-11-21). A `state private` refusal over a state.json
  // that LOADS -- a link the writer would save elsewhere (`split-link`),
  // another account's file (`not-owned`), a mode that would not hold
  // (`unconfirmed`) -- is no load failure, so the no-write mode never begins
  // and the guide's "Could not write state.json" line, shown only while the
  // guide is open, was all the user had. Its notice is told here: once per
  // failure episode and cause (Model.statePrivateRefusalTell), as a
  // notification on the no-write notice's id (one card for the file's
  // trouble) and the journal, in the words of
  // Model.statePrivateRefusalNotice: why, what becomes of a change, and the
  // fix. Nothing else changes, and on purpose: memory stands
  // (noteStateWriteFailed's flag, so a reload of the file is not applied over
  // it), and every later save still reads and asks `state private`, which
  // refuses each while the cause stands and confirms the first after the
  // fix, whose write carries everything held -- no restart, no reload.
  // And not while the no-write mode stands (the review, 2026-11-21): a run
  // that was out when a load began it answers after that block's card,
  // which names the cause that stops every write and which this card would
  // replace on the same id. Nothing is marked told, so a refusal after the
  // block lifts is told then.
  function tellStateSaveRefused(why) {
    if (root.stateWriteBlocked !== "") return
    if (!Model.statePrivateRefusalTell(why, root.statePrivateTold)) return
    root.statePrivateTold = String(why)
    console.warn("omarchy-iptv: " + Model.statePrivateRefusalJournal(why, root.stateFilePath))
    root.notify("stateUnreadable", { reason: String(why), path: root.stateFilePath, refused: true })
  }

  function onConfigShieldExit(out) { return ServiceSources.onConfigShieldExit(out) }

  function setShowLogos(on) { return ServiceSources.setShowLogos(on) }

  // One process per mark or clear, which is affordable because a failure is
  // rare -- not per keystroke, per zap or per tick. Fire and forget: the
  // in-memory map is already correct, and a failed write costs a mark, not a
  // wrong one.
  Process { id: failedProc }
  Connections {
    target: failedProc
    function onExited(exitCode, exitStatus) { root.handleFailedExit() }
  }

  function handleFailedExit() { return ServiceSources.handleFailedExit() }

  // A one-deep queue rather than a kill. This used to SIGTERM its own
  // in-flight write and start another, which loses the write it killed --
  // and the two calls that collide are exactly the common pair: a play
  // clearing a mark while the previous failure is still being written.
  property var failedQueue: []

  function persistFailed(action, id) { return ServiceSources.persistFailed(action, id) }

  function runFailedJob(job) { return ServiceSources.runFailedJob(job) }

  function str(v) { return v === undefined || v === null ? "" : String(v) }

  // The marks of the source whose channels are loaded. Pruned on arrival: the
  // TTL, and any id the current playlist does not have -- which is what makes
  // an id rotation, a provider reshuffle and a removed channel all self-heal
  // instead of leaving marks that name nothing.
  // The raw list as it came off disk. Kept because the prune needs the CHANNELS
  // to decide what is stale, and the two files load independently -- on a cold
  // start failed.json can arrive first.
  property var failedRaw: []

  function applyFailed(text) { return ServiceSources.applyFailed(text) }

  function pruneFailed() { return ServiceSources.pruneFailed() }

  // Re-prune when the channels arrive, whichever file won the race.
  onChannelsChanged: root.pruneFailed()

  function togglePause() { return ServiceRewind.togglePause() }

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
  // in the service's own rewind functions -- in Service-rewind.js since
  // D-REL-14, each reached through its forwarder below -- is what Qt owns:
  // `controlProc.running`, `seekThrottle.running`, `Date.now()`, property
  // writes, starting the timer, `runControl` and the signal. Of every
  // branch there a reader can say which of the two it is.

  function seekState() { return ServiceRewind.seekState() }

  function seekCtx() { return ServiceRewind.seekCtx() }

  function applySeekPlan(plan) { return ServiceRewind.applySeekPlan(plan) }

  function applyRewind(status) { return ServiceRewind.applyRewind(status) }

  function clearRewind() { return ServiceRewind.clearRewind() }

  // The IPC verbs' argument is read by Model.seekVerbSeconds (design 2.4):
  // empty is one step, a positive whole number is itself, anything else is
  // 0 and refused as bad_seconds. The service lane had written a second
  // parser here while the model was closed to it; the review found the
  // tested one dead (rule 12) and this one with different limits.

  function seekRefuse(requested, code) { return ServiceRewind.seekRefuse(requested, code) }

  function seekBy(seconds) { return ServiceRewind.seekBy(seconds) }

  function seekLive() { return ServiceRewind.seekLive() }

  function issueSeek() { return ServiceRewind.issueSeek() }

  function requestTracks(select) { return ServiceRewind.requestTracks(select) }

  function askPlayerStatus() { return ServiceRewind.askPlayerStatus() }

  function cancelTracks() { return ServiceRewind.cancelTracks() }

  function refreshTracks() { return ServiceRewind.refreshTracks() }

  function clearTracks() { return ServiceRewind.clearTracks() }

  function issueQueuedTracks() { return ServiceRewind.issueQueuedTracks() }

  function beginSwitch() { return ServiceSources.beginSwitch() }

  function abortSwitch() { return ServiceSources.abortSwitch() }

  function finishSwitch() { return ServiceSources.finishSwitch() }

  function startProbe(key, dirKey, mode, commit) { return ServiceSources.startProbe(key, dirKey, mode, commit) }

  function launchProbe() { return ServiceSources.launchProbe() }

  function handleProbeExit(text) { return ServiceSources.handleProbeExit(text) }

  function reconcile(force) { return ServiceSources.reconcile(force) }

  function stripEntryInputs() { return ServiceSources.stripEntryInputs() }

  function reportEntryInput(setting, reason) { return ServiceSources.reportEntryInput(setting, reason) }

  function adoptActive(playlist, epg, plan) { return ServiceSources.adoptActive(playlist, epg, plan) }

  // D-REL-15: adoptActive's deferred persistActive(key), built HERE, on the
  // root, and never in a code-behind. A function expression made inside a
  // code-behind and handed to Qt.callLater can take the QML engine down (a
  // SIGSEGV in libQt6Qml; a ReferenceError instead when its function had
  // read the root first, which no reading of the source can be held to)
  // when this Service is deleted after the call is scheduled and before it
  // runs; the same closure made in a function of this file logs a TypeError,
  // and so it does when a code-behind calls this function (measured under
  // gdb, 2026-11-24). A closure, and not Qt.callLater(root.persistActive,
  // key): callLater folds calls of one function before the next turn into
  // one, with the last arguments, so two adoptions in one turn would persist
  // only the second key; each closure is its own call, both keys in order,
  // as before the split. It stays on the root, written inline: the service
  // split guard refuses a function expression in a code-behind.
  function persistActiveLater(key) {
    Qt.callLater(function() { root.persistActive(key) })
  }

  function applyInvalidStatus() { return ServiceSources.applyInvalidStatus() }

  // D-SRC-10's settings write-back is GONE (D-SINK-19). It existed because a
  // switch copied the new source's epgUrl INTO the bar entry, so a reconcile
  // that declined to adopt a carried-over epgUrl had to put the record's own
  // value back there. The entry carries no EPG URL now: `activeEpgUrl` reads
  // the record, the record is the only store, and there is nothing to sync.
  // The non-adoption rule itself is unchanged -- Model.reconcileSources still
  // leaves a known record's own epgUrl alone when the setting did not change
  // in the same write.

  function startCacheLayout() { return ServiceSources.startCacheLayout() }

  function schedulePrune() { return ServiceSources.schedulePrune() }

  function queuePrune() { return ServiceSources.queuePrune() }

  function queueCacheJob(args, onDone) { return ServiceSources.queueCacheJob(args, onDone) }

  function cacheJobContext() { return ServiceSources.cacheJobContext() }

  function runNextCacheJob() { return ServiceSources.runNextCacheJob() }

  function handleCacheExit(text) { return ServiceSources.handleCacheExit(text) }

  function applyFreshness() { return ServiceSources.applyFreshness() }

  function clearSourceData() { return ServiceSources.clearSourceData() }

  function activeSourceSummary() { return ServiceSources.activeSourceSummary() }

  // ------------------------------------------------------------ helpers

  // Host for the probe signal (UX-SOURCES 5.5): never a path, query or
  // userinfo; `local file` for a path (the guide's failure line drops the
  // host for kind `file`, the `Added` transient shows it); `[host withheld]`
  // where the Sources form would withhold it (D-SINK-109,
  // Model.sourceShownHost), so the Sources list's probe failure line does
  // not name a username. The form re-reads it through formLineHost.
  function hostForRecord(rec) {
    return rec ? Model.sourceShownHost(rec.url) : ""
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
  // D-SINK-38 (round 7, 2026-10-22, the owner's decision): and the shield is
  // asked again on every HOST publish of shell.json, through its debounce
  // -- from onHostSettingsChanged below, not from here (round 8, the lead's
  // answer to round 7's open question): `settings` also re-evaluates on the
  // plugin's own ownWrite reassignment, so a re-arm here cost an owned
  // write the funnel's run plus one or two debounce runs; the host's signal
  // fires once per publish and never for the override.
  // The host's reset commands (omarchy-reinstall-configs, the quattro
  // upgrade's copy, omarchy-refresh-config on a missing file) can re-create
  // the file 0644 mid-session, and until now the shield ran only on the
  // service's own events (start, an owned write, a refusal, the deferred
  // path), so a recreated file stayed 0644 until the next start whenever
  // the plugin had no write to make (the no-write states, R22a and R21e,
  // with a URL on the entry). One ~200 ms helper run per publish, folded
  // into one re-run while one is in flight (runConfigShield). No loop: the
  // verb chmods only a file that is not yet private and does nothing
  // otherwise (`changed: false`, the helper's own idempotence test), so the
  // one publish a chmod can raise through the host's file watch meets a run
  // that changes nothing; and sameOwnWrite already bounds the lagging
  // host's publish cycle. Pinned through the service harness.
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
  // D-SINK-38 (round 8): and the shield's debounce is re-armed here, once
  // per host publish -- the republish of unchanged content, the file replaced
  // by the package default, the lagging host's late echo of an owned write.
  // The verb chmods only a file that is not yet private (`changed: false`
  // otherwise), so the one publish a chmod can raise meets a run that
  // changes nothing; a shield exit re-arms nothing by itself.
  onHostSettingsChanged: { if (root.ownWrite && !Model.ownWriteInForce(root.hostSettings, root.ownWrite)) root.ownWrite = null; configShieldDebounce.restart() }
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
      root.epgNow = Model.emptyEpgStore()
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
    root.runWhichMpv()
    // M2-05 G-8: is there a compositor to talk to at all, and which dispatch
    // spelling can it parse? Both answers are read once, here, so the `p`
    // key can refuse honestly instead of firing into the dark.
    root.runPipProbe()
    // Reattach (4.5). Until the probe answers - about 130 ms - the UI shows
    // idle rather than guessing. `--owner-pid` claims a surviving player for
    // this shell, and `--owner-token` for this Service object (D-PLY-64),
    // which is what tells the previous shell's -- or the previous Service's
    // -- orphan-check to do nothing.
    root.runPlayerProbe()
  }

  // PO-2: the service object is destroyed both by a shell restart and by the
  // plugin being disabled or removed, and Quickshell 0.3.1 gives no way to
  // tell them apart at this point - so we must NOT stop the player here.
  // That would kill playback on the very restart this milestone exists to
  // survive. The discriminator is the owner claim, read 6 s later by a
  // detached helper: a successor that has claimed the player by then names
  // another pid, and a restart that has not is a dead pid once the old
  // shell has exited (an old shell that outlives the grace is D-HOST-8), so
  // only "the claim still names a pid that is still alive" means the plugin
  // was disabled or removed (4.14). Nothing here assumes the new shell is
  // quick: omarchy-restart-shell waits up to 60 s for it to answer (4.0.6 and
  // 4.5.0 alike), and a large bar answers past ten seconds.
  //
  // D-PLY-64: "a successor shell" includes a successor SERVICE in this same
  // shell, which the host creates when it reads the plugin as disabled for a
  // moment and enabled again (Omarchy 4.5.0's migrations replaced shell.json
  // under it). Its claim has this pid, so the check also carries this
  // object's `ownerToken` and reads a claim with another token as
  // reassigned. The token rides on this run's argv: execDetached's command
  // list is the one form measured to start here -- a { command, environment }
  // object is refused as a TypeError and nothing runs (measured 2026-11-06,
  // an offscreen quickshell 0.3.2), which would read as a genuine disable
  // that leaves the channel playing -- and the token is no private value: it
  // authorizes nothing, and names nothing outside the user's own 0700 runtime
  // directory (Model.playerOwnerToken).
  Component.onDestruction: {
    // R15 (DQ-B9): an entry mirror still HELD at exit never got its save
    // landed (a parked save never issued, a write still in flight). The entry
    // is left exactly as it is and the next start re-adopts it (R1); this
    // line is what makes that visible in the journal. The key is a key or
    // "", never a URL, and is not logged either way.
    if (root.pendingEntryKey !== null) console.warn("omarchy-iptv: exiting with a bar-entry mirror still held (state save not landed); the entry is left as it is and the next start re-adopts it")
    Quickshell.execDetached(Model.helperArgv(root.helperPath,
      Model.playerOrphanCheckArgv(root.socketPath, Quickshell.processId, Model.PLAYER_ORPHAN_GRACE_SEC, root.ownerToken)))
  }

  // ------------------------------------------------------------ files

  // The four cache views follow the active source's directory (D5). Content
  // is only ever applied from onLoaded / onLoadFailed (R1: after a path
  // change the view still reports the previous file until then).
  // D-HOST-1. Read when the view is made, and re-read three ways, because
  // its path never changes (it is this component's own directory) and a
  // FileView reloads only when it is told to. printErrors stays off: a
  // missing manifest is not a user-facing error, it just means we cannot
  // tell, and staleBuild answers false for an empty version rather than
  // guessing.
  // D-HOST-16. The first way is the host's hand-off. The host hands a kept
  // service a FRESH manifest object at every rescan, and an update's own
  // rescan is one (shell.qml's _syncServices, `kept.manifest =
  // shell.publicPluginManifest(m)`, a JSON copy for a plugin that is not
  // first-party; read in the host, not yet watched under a real update). The
  // service used that object only for its id, so between an update and the
  // next guide open `status` read the version from the service's creation.
  // The object is a trigger only: its version is the host's reading, and the
  // dev harness hands `0.1.0-harness`, so the file is what is read.
  onManifestChanged: manifestFile.reload()
  FileView {
    id: manifestFile
    path: root.manifestPath
    // The second way is the watcher, for an in-place edit. It is NOT what
    // catches an update. D-HOST-2: an update REPLACES the file rather than
    // editing it -- measured, a git fast-forward took manifest.json from
    // inode 495084 to 495097 -- so a watcher bound to the old inode never
    // fires, and the notice this exists for stayed silent through the exact
    // update it was built to catch. A replacement raises nothing and leaves
    // the view watching nothing until a reload re-arms it (the contract's
    // FileView facts, measured on stateFile). Until D-HOST-16 this said an
    // in-place edit was "free to catch" while nothing answered the watcher:
    // Quickshell's FileView.qml declares no fileChanged handler, and every
    // view measured here reloads from its own onFileChanged, so the handler
    // below is what makes the watch read anything (whether the C++ view
    // would ever reload by itself is read nowhere and not measured).
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.onDiskVersion = Model.manifestVersion(text())
    onLoadFailed: root.onDiskVersion = ""
  }

  // The third way: re-read the manifest from its PATH, which is the only way
  // to see a file that was replaced underneath us. Called when the guide
  // opens: that is the moment the notice would be shown, so it is the moment
  // the answer has to be current, and it costs one small read against a
  // 150 ms budget whose open work measures about 20 ms.
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
        // D-SRC-39: decided from the burst record, not the last text alone.
        var outcome = Model.stateSaveOutcome({ viewText: stateFile.text(), lastSaveText: root.lastSaveText, recentSaves: root.recentSaves })
        if (outcome.last) {
          root.stateSavesInFlight = 0
          root.statePrivateCreated = false   // D-SINK-103: the created file holds our text now
          root.stateSaveFailed = false
          root.statePrivateTold = ""         // D-STATE-11: the episode is over
          root.landedState = root.lastSaveState   // R21a: what the disk holds now, the marker included
          root.recentSaves = []                   // R25a: nothing in flight, so no later reload is an echo
          // R27a: a save held for this write now reads, from a turn of its own.
          root.stateWriteWaitExpired = false
          root.endStateWriteWait(false)
        } else if (outcome.landed) {
          // D-SRC-39: an EARLIER write of the burst landed -- the disk holds
          // its text now, whatever the later write does -- so it is the base
          // from here, and the texts before it are no longer echoes to come.
          // The later write is still in flight: nothing else moves.
          root.landedState = outcome.state
          root.recentSaves = outcome.remaining
        }
        // D-SRC-49 / D-SINK-22 (b)(c): the landed save was the last asked for
        // and nothing is in flight -- the file at the path is ours now, with
        // whatever mode it had or was created with -- so the helper's `state
        // mode` repairs it, from a turn of its own (never from inside the
        // FileView's handler, R26b), on its own Process. Coalesced in
        // requestStateMode; nothing here waits on it.
        if (outcome.last) Qt.callLater(root.requestStateMode)
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
        // D-SRC-39: the same decision as onSaved's (rule 15); a failed
        // earlier write of a burst lands nothing, so only `last` is read.
        if (Model.stateSaveOutcome({ viewText: stateFile.text(), lastSaveText: root.lastSaveText, recentSaves: root.recentSaves }).last) {
          root.stateSavesInFlight = 0
          root.statePrivateCreated = false   // D-SINK-103: no write of ours is coming to fill it
          root.stateWriteWaitExpired = false
          root.endStateWriteWait(false)
        }
        // The error is an enum, never a path or a URL. Logged on EVERY failure.
        console.warn("omarchy-iptv: state.json could not be written (error " + error + "); the in-memory state stands")
        // R13: the state write IS the switch / remove / adoption, so its
        // failure is the one a source call can have, reported here with a
        // reason of its own rather than from the call that issued it (which
        // returned when the write was issued, SR25 as amended 2026-10-12),
        // once per failure EPISODE (noteStateWriteFailed, shared with the
        // `state private` that does not confirm, D-SINK-103).
        root.noteStateWriteFailed()
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
    // D-REL-8: the one re-run of a start-up init that answered nothing
    // readable (decideStateLoad's `reinit`), a second after its exit -- long
    // enough for git to have finished rewriting the stub in place (measured
    // in milliseconds), short enough that a start inside that window is not
    // a session without writes. Armed under the start-up watchdog again.
    id: stateInitRetry
    interval: 1000
    repeat: false
    onTriggered: {
      console.warn("omarchy-iptv: state init answered nothing readable; running it once more")
      root.stateInitTimedOut = false
      root.startStateInit()
      stateInitWatchdog.restart()
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
      // D-SRC-69: a probe still held behind a cache job that has not exited
      // in the probe's whole budget fails as a timeout, with nothing to stop.
      if (root.probeHeld) {
        console.warn("omarchy-iptv: source probe waited " + Math.floor(root.helperTimeoutMs / 1000) + " s for a cache job to finish; giving up")
        root.probeTimedOut = true
        root.handleProbeExit("")
        return
      }
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
    // D-PLY-35: the interval follows the verb in flight (playerTimeoutMs);
    // runPlayer() sets `playerKind` before it restarts this, so each run is
    // bounded by its own verb's worst case.
    id: playerWatchdog
    interval: root.playerTimeoutMs
    repeat: false
    onTriggered: {
      if (playerProc.running) {
        console.warn("omarchy-iptv: player helper exceeded " + Math.floor(root.playerTimeoutMs / 1000) + " s, terminating it")
        // D-PLY-35: so its exit is read as stopped, not as a refusal.
        root.playerTimedOut = true
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
    // ours - which another launcher, or a person typing a `--seq`, leaves
    // behind (a terminal `omarchy-iptv player stop`, the documented uninstall
    // escape hatch, runs on `--seq 0`, which is never superseded and, since
    // D-PLY-77, leaves the record's seq where it was). Found
    // live: the UI went idle while the player kept playing. One probe
    // re-reads the record, and applyProbe() then stops it with a sequence
    // that is past whatever is recorded.
    //
    // The review of 9d604cf: and a start issued before the stop that
    // answered ok while it settled (stopOlderStartOk) is looked for too,
    // with nothing attached: its player was up, and a stop refused `busy`
    // behind that start's own lock left it playing unobserved under an idle
    // bar. One probe: a stop that took finds nothing. D-PLY-75: and so when
    // the stop took over a question about a player that was open as it was
    // pressed (stop() sets stopOlderStartOk then).
    //
    // D-PLY-73: a stop the shell issues itself (stopUnadoptedPlayer) opens
    // a settle of its own, and this backstop looks at it once as it looks at
    // the user's -- except the stop this probe leads to, whose settle it
    // ends here and looks no further (stopFromBackstop): so the shell sends
    // no more stops after the user's than it did before those settles
    // existed, and a player that outlives every stop does not hold
    // `stopping` for good.
    id: stopSettleTimer
    interval: root.stopSettleMs
    repeat: false
    onTriggered: {
      root.stopAt = 0
      root.userStopped = false
      stopLookTimer.stop()
      var older = root.stopOlderStartOk
      root.stopOlderStartOk = false
      if (root.stopFromBackstop || root.nowPlaying !== null || root.stopConfirmPending) return
      if (!root.socketAttached() && !root.playerUp && !older) return
      console.warn("omarchy-iptv: the player outlived a stop, re-reading its sequence")
      root.stopConfirmPending = true
      root.runPlayerProbe()
    }
  }

  Timer {
    // The review of 9d604cf (F-PLY-3, PLY-STOP-07): the backstop above waits
    // out the stop's own worst case since D-PLY-40, and a stop the lock
    // record SUPERSEDED -- another launcher's higher --seq, or a typed one
    // such as player-scenario's P10 `--seq 9999` -- is refused at once and
    // leaves the player playing, which the old 5 s backstop caught at 5 s
    // and the 18.25 s one would catch at 18.25 s. So this looks at the old
    // moment and acts only
    // on that case: the probe (stopConfirmLook) stops the player when the
    // record is past this stop's sequence, and changes nothing while the
    // record is the stop's own (it is laddering) or older (it is waiting for
    // the lock), which is D-PLY-40's case. It ends nothing: `stopping` and
    // `userStopped` are the backstop's and the EOF's.
    //
    // The recheck of 2cfeb74: the look still runs one `player probe` over a
    // stop that is only laddering or waiting for the lock -- that is the
    // price of the 5 s catch; only the second `player stop` is gone -- so
    // its line says what it does and claims nothing the probe has not
    // found. A superseded stop then logs "stopping a player that survived a
    // superseded stop" from applyProbe.
    id: stopLookTimer
    interval: root.stopLookMs
    repeat: false
    onTriggered: {
      if (!root.stopping || root.nowPlaying !== null || root.stopConfirmPending) return
      if (!root.socketAttached() && !root.playerUp && !root.stopOlderStartOk) return
      console.warn("omarchy-iptv: a stop has not ended after 5 s, reading the player's sequence")
      root.stopConfirmPending = true
      root.stopConfirmLook = true
      if (!root.runPlayerProbe()) {
        root.stopConfirmPending = false
        root.stopConfirmLook = false
      }
    }
  }

  Timer {
    // Restart on adoption: the hold. A player another build launched plays on,
    // fed nothing, while the channel list is applied; when the hold runs out
    // first the restart is deferred to the user's next channel change, or the
    // player stopped when it cannot be made safe (Model.olderRestartDisposition).
    // D-SINK-71: except a player the probe had to migrate, which keeps waiting
    // for the list and is restarted when it lands. Marking `expired` and
    // asking the disposition is all this does.
    id: olderRestartTimer
    interval: Model.OLDER_RESTART_HOLD_MS
    repeat: false
    onTriggered: {
      var ep = root.olderRestart
      if (ep === null) return
      root.olderRestart = Model.olderRestartWith(ep, { expired: true })
      root.reestablishAdopted()
    }
  }

  Timer {
    // The single re-read of an ambiguous probe (4.5): an idle or stashless
    // player is either a racing start or a foreign one, and 500 ms tells
    // them apart without a second guess.
    //
    // D-PLY-76: unless an intent was issued since the answer that armed it
    // (probeRetrySeq). A play made in these 500 ms with the observer on that
    // idle player was zapped into it, and the re-read, going out after the
    // play and so not stale, still read it idle before the zap had loaded:
    // the shell stopped the player and cleared `nowPlaying`, and the zap's
    // ok and the player's EOF then named nothing -- the play dropped with no
    // card. A stop made in them was followed by this re-read, which found a
    // player that outlived the stop and adopted it or stopped it -- with the
    // observer attached a second stop over the one the stop was laddering,
    // and with nothing attached (a reattach) the only look at that player.
    // Now that answer is overruled as a stale one is: the play or the stop
    // owns the outcome (the zap feeds a player of this build, the helper's
    // build gate routes any other to a start; the stop takes the owed
    // re-read over, stop() reading `probeRetried`, so its own look and
    // backstop look for that player even with nothing attached -- the
    // review of 8504ba8). A re-read already out when the intent comes is
    // stale, as before. Asked of the sequence
    // alone, not of `probeRetried`: the observer attaching meanwhile resets
    // that (onPlayerAttached), and a play made after it was the same zap.
    id: probeRetryTimer
    interval: root.playerProbeRetryMs
    repeat: false
    onTriggered: {
      if (root.playSeq !== root.probeRetrySeq) {
        root.probeOverruled()
        return
      }
      root.runPlayerProbe()
    }
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
      // D-PLY-58: and a channel adopted from ANOTHER source is not on this
      // list whatever its id finds there (D-PLY-51's rule, for the relaunch).
      var channel = Model.adoptedSourceMatches(root.playerSourceKey, root.activeSourceKey)
        ? root.channelIndex[String(root.nowPlaying.id)] : null
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
    // D-PLY-43: a retry made while an earlier stop settles is the user's
    // play (play() cleared `userStopped`), so it runs; what it may not do is
    // zap the socket that stop is tearing down, so the branch is the play
    // fork's own (Model.playFork): a start while `stopping`, which the lock
    // and the seq rule order after the stop. A stop pressed meanwhile stops
    // this Timer, clears `nowPlaying` and sets `userStopped` (D-LIVE-15).
    onTriggered: {
      if (root.userStopped || !root.nowPlaying) return
      var id = String(root.nowPlaying.id)
      var fork = Model.playFork({ socketAttached: root.socketAttached(), playerPending: root.playerPending,
                                  stopping: root.stopping, controlBusy: controlProc.running,
                                  restartOwed: root.olderRestartOwed })
      if (fork === "queue") {
        root.pendingPlayId = id
        return
      }
      if (fork === "zap") {
        root.runControl("play", root.playArgs(id))
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
    command: Model.stateInitArgv(root.helperPath, root.stateDir)
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
    // D-SRC-49 / D-SINK-22 (b)(c): the helper's `state mode` after every
    // landed save (requestStateMode). Argv only; the one JSON line is read at
    // the exit and otherwise discarded. Its stderr is redacted like every
    // other helper channel although the verb prints no URL.
    id: stateModeProc
    stdout: StdioCollector { id: stateModeStdout; waitForEnd: true }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") console.warn("omarchy-iptv state mode:", Model.redactUrls(text.trim()))
    }
  }
  Connections {
    target: stateModeProc
    function onExited(exitCode, exitStatus) { root.handleStateModeExit(exitCode, stateModeStdout.text) }
  }

  Process {
    // D-SINK-103: the helper's `state private` BEFORE every write of
    // state.json (requestStatePrivate). The write is issued only on its
    // confirmed reply, read at the exit (Model.statePrivateReply). Argv only;
    // its stderr -- the refusal's sentence, which names no path -- is
    // redacted like every other helper channel.
    id: statePrivateProc
    stdout: StdioCollector { id: statePrivateStdout; waitForEnd: true }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (text.trim() !== "") console.warn("omarchy-iptv state private:", Model.redactUrls(text.trim()))
    }
  }
  Connections {
    target: statePrivateProc
    function onExited(exitCode, exitStatus) { root.handleStatePrivateExit(exitCode, statePrivateStdout.text) }
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

  function onLogoLine(line) { return ServiceSources.onLogoLine(line) }

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

  function flushLogoNames() { return ServiceSources.flushLogoNames() }
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

  function fetchLogos() { return ServiceSources.fetchLogos() }

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
    function onExited(exitCode, exitStatus) { root.handleWhichExit(exitCode) }
  }

  function runWhichMpv() { return ServicePlayer.runWhichMpv() }

  function handleWhichExit(exitCode) { return ServicePlayer.handleWhichExit(exitCode) }

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
    function onExited(exitCode, exitStatus) { root.handlePipWhichExit(exitCode) }
  }

  function runPipProbe() { return ServicePip.runPipProbe() }

  function handlePipWhichExit(exitCode) { return ServicePip.handlePipWhichExit(exitCode) }

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
    function onExited(exitCode, exitStatus) { root.handlePipInfoExit(exitCode) }
  }

  function handlePipInfoExit(exitCode) { return ServicePip.handlePipInfoExit(exitCode) }

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
    // D-PLY-66: `player refused`, the one question asked of the player's
    // relay after a failed open (askRelayThenRaise). Its own slot, because
    // the control slot may be busy at the socket's EOF and the relay answers
    // for about a second only.
    id: relayAskProc
    stdout: StdioCollector { id: relayAskStdout; waitForEnd: true }
    stderr: StdioCollector { id: relayAskStderr; waitForEnd: true }
  }
  Connections {
    target: relayAskProc
    function onExited(exitCode, exitStatus) { root.handleRelayAnswer(relayAskStdout.text) }
  }
  Timer {
    // D-PLY-66: the bound on the relay question. The card it holds is told
    // HERE, as the player told it, and the helper is ended; its late exit
    // then finds nothing waiting.
    id: relayAskWatchdog
    interval: Model.RELAY_ASK_TIMEOUT_MS
    repeat: false
    onTriggered: {
      root.handleRelayAnswer("")
      if (relayAskProc.running) relayAskProc.signal(15)
    }
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

  // D-SRC-37 (c), 2026-10-24: ONE shape over the four processes that had no
  // bound while every other helper slot had one -- cacheProc (the FIFO every
  // cache job runs through, writing into the cache directory: a stalled
  // mount there held the queue for the session), failedProc (the same
  // directory), configShieldProc and whichProc. TERM only, like every
  // watchdog but the start-up one (R23c has the KILL half because the whole
  // start waits on that run; nothing waits on these). Each is restarted
  // where its `running = true` is set and stopped in the exit handler the
  // harness runs. The bound is helperTimeoutMs, the playlist slot's: a
  // cache prune over a large directory is the longest of them and is well
  // inside it; the point is a bound, not a tight one. On fire, cacheProc's
  // queue is DROPPED with one line -- the jobs are re-derivable (the
  // start-up prune, a remove, epg-clear; the next start prunes again), and
  // a queue behind a stalled slot would only stall in turn -- and so is
  // failedProc's (the in-memory map is already right; a lost mark costs a
  // mark, as the slot's comment says). The two decide-once processes
  // (configShield, which) print nothing when stopped, which their exit
  // handlers already read as "not private" and "no mpv".
  Timer {
    id: cacheWatchdog
    interval: root.helperTimeoutMs
    repeat: false
    onTriggered: {
      if (!cacheProc.running) return
      var job = root.cacheJob
      console.warn("omarchy-iptv: cache " + (job ? job.args[0] : "?") + " exceeded " + Math.floor(root.helperTimeoutMs / 1000) + " s, terminating it; "
                   + root.cacheQueue.length + " queued cache job(s) dropped")
      root.cacheQueue = []
      cacheProc.signal(15)
    }
  }
  Timer {
    id: failedWatchdog
    interval: root.helperTimeoutMs
    repeat: false
    onTriggered: {
      if (!failedProc.running) return
      console.warn("omarchy-iptv: failed-channel helper exceeded " + Math.floor(root.helperTimeoutMs / 1000) + " s, terminating it; "
                   + root.failedQueue.length + " queued mark(s) dropped")
      root.failedQueue = []
      failedProc.signal(15)
    }
  }
  Timer {
    id: configShieldWatchdog
    interval: root.helperTimeoutMs
    repeat: false
    onTriggered: {
      if (!configShieldProc.running) return
      console.warn("omarchy-iptv: config shield exceeded " + Math.floor(root.helperTimeoutMs / 1000) + " s, terminating it")
      configShieldProc.signal(15)
    }
  }
  Timer {
    id: stateModeWatchdog
    interval: root.helperTimeoutMs
    repeat: false
    onTriggered: {
      if (!stateModeProc.running) return
      console.warn("omarchy-iptv: state mode exceeded " + Math.floor(root.helperTimeoutMs / 1000) + " s, terminating it")
      stateModeProc.signal(15)
    }
  }
  Timer {
    // D-SINK-103: the bound on `state private`, the start-up check's (the
    // same verb family on the same path; the helper's own alarm ends it at
    // 30 s). At the bound the run is TERMed and its save FAILED now, told,
    // rather than held on a run that no signal may end (a filesystem in
    // uninterruptible sleep): no write goes without the run's reply.
    id: statePrivateWatchdog
    interval: root.stateInitTimeoutMs
    repeat: false
    onTriggered: {
      if (!statePrivateProc.running || !root.statePrivatePending) return
      console.warn("omarchy-iptv: state private exceeded " + Math.floor(root.stateInitTimeoutMs / 1000) + " s, terminating it")
      root.statePrivateAbandoned = true
      statePrivateProc.signal(15)
      root.finishStatePrivate({ ok: false, why: "timeout" })
    }
  }
  Timer {
    id: whichWatchdog
    interval: root.helperTimeoutMs
    repeat: false
    onTriggered: {
      if (!whichProc.running) return
      console.warn("omarchy-iptv: which mpv exceeded " + Math.floor(root.helperTimeoutMs / 1000) + " s, terminating it")
      whichProc.signal(15)
    }
  }
  Timer {
    // D-PLY-26: the PiP start-up pair (runPipProbe): `which hyprctl`, then
    // `hyprctl systeminfo`; whichever is running is the one stopped.
    id: pipProbeWatchdog
    interval: root.helperTimeoutMs
    repeat: false
    onTriggered: {
      var proc = hyprWhichProc.running ? hyprWhichProc : hyprInfoProc.running ? hyprInfoProc : null
      if (proc === null) return
      console.warn("omarchy-iptv: " + (proc === hyprWhichProc ? "which hyprctl" : "hyprctl systeminfo") + " exceeded " + Math.floor(root.helperTimeoutMs / 1000) + " s, terminating it")
      proc.signal(15)
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

  // D-HOST-5 (owner, 2026-10-28): one notice post, made per post by
  // runNotify(). `omarchy-notification-send -p` prints the id the server
  // returned (the wrapper's busctl call waits for the server's answer, which
  // this shell's own notification server gives on its event loop; the
  // Process keeps that wait off it), read whole by the collector: one short
  // line from the host's own wrapper. `guard` is the post's watchdog, running
  // exactly while the post is; the exit frees the kind's slot and destroys
  // the object (handleNotifyExit). argv only (runNotify sets `command`).
  Component {
    id: notifyComponent

    Process {
      id: notifyRun
      property string kind: ""
      stdout: StdioCollector { id: notifyOut; waitForEnd: true }
      property Timer guard: Timer {
        interval: Model.NOTIFY_POST_TIMEOUT_MS
        repeat: false
        running: notifyRun.running
        onTriggered: root.notifyOverdue(notifyRun)
      }
      property Connections exits: Connections {
        target: notifyRun
        function onExited(exitCode, exitStatus) {
          root.handleNotifyExit(notifyRun, notifyRun.kind, exitCode, exitStatus, String(notifyOut.text))
        }
      }
    }
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
    function channel(n: string): string { return Model.ipcJson(root.tuneByNumber(n)) }
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
    function pip(mode: string): string { return Model.ipcJson(root.requestPip(mode)) }
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
      return Model.ipcJson(n === 0 ? root.seekRefuse(0, "bad_seconds") : root.seekBy(-n))
    }
    function forward(seconds: string): string {
      var n = Model.seekVerbSeconds(seconds)
      return Model.ipcJson(n === 0 ? root.seekRefuse(0, "bad_seconds") : root.seekBy(n))
    }
    function live(): string { return Model.ipcJson(root.seekLive()) }
    function stop(): string { root.stop(); return "ok" }
    function next(): string { return root.zap(1) ? "ok" : "nothing playing" }
    function previous(): string { return root.zap(-1) ? "ok" : "nothing playing" }
    function refresh(): string { root.refresh(); return "ok" }
    // F-SINK-16: every JSON reply through Model.ipcJson, which escapes the
    // C1 controls JSON.stringify passes through to the caller's terminal.
    function status(): string { return Model.ipcJson(root.statusSummary()) }
  }
}
