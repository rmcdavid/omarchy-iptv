import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import qs.Commons
import "Model.js" as Model

// Dev harness for io.github.rmcdavid.iptv -- a standalone Quickshell config
// that loads the three plugin entry points straight from the repo with fake
// `shell`, `manifest`, `bar` and `settings` objects, so the plugin can be
// smoke-tested without installing it into the user's shell.
//
// Started by scripts/dev-harness/run.sh, which prepares a scratch config
// root (Commons/ and Ui/ symlinked from /usr/share/omarchy/shell so that
// `import qs.Commons` resolves) and scratch XDG cache/state/runtime dirs.
//
// Environment (all set by run.sh):
//   OMARCHY_IPTV_ROOT       repo root (absolute)
//   OMARCHY_IPTV_PLAYLIST   playlist URL or path handed to the service
//   OMARCHY_IPTV_EPG        EPG URL (optional)
//   OMARCHY_IPTV_OPEN       "1" opens the guide right after load
//   OMARCHY_IPTV_VERTICAL   "1" fakes a vertical bar
//   OMARCHY_IPTV_SHOW_NAME  "false" hides the bar label
//   OMARCHY_IPTV_LABEL_MAX  barLabelMaxWidth setting
//   OMARCHY_IPTV_ORDER      channelOrder setting ("playlist" | "number")
//   OMARCHY_IPTV_ENTRY_MS   numberEntryMs setting
//   OMARCHY_IPTV_BAR_NUMBER "false" hides the channel number in the bar
//   OMARCHY_IPTV_HARNESS_WINDOW "floating" hosts the guide in a FloatingWindow (harness-only; see floatingGuide)
//
// Drive it with `run.sh ipc <fn> [args]` (IpcHandler target "harness").
ShellRoot {
  id: harness

  readonly property string repoRoot: Quickshell.env("OMARCHY_IPTV_ROOT")
  // Harness-only window mode (docs/SPIKE-CAGE-HEADLESS.md). "floating" hosts
  // the guide in a FloatingWindow, an xdg toplevel, so it maps under a
  // compositor with no layer-shell (headless cage) and wtype and grim reach
  // it. It is handed to Guide.qml as an INITIAL property through
  // Loader.setSource, before the guide's own window Loader decides, so the
  // layer-shell component is never instantiated in floating mode; assigning
  // it after load would build the production window first and swap it out.
  readonly property bool floatingGuide: Quickshell.env("OMARCHY_IPTV_HARNESS_WINDOW") === "floating"
  readonly property string pluginId: "io.github.rmcdavid.iptv"
  property string lastTooltip: ""
  // The last 20 source signal payloads (URL-free by contract), for `signals()`.
  property var signalLog: []
  // `failPersist true` takes `updateEntryInline` off the fake shell api, the
  // way a host that cannot rewrite our bar entry leaves it (SR25: the
  // service only signals sourcesPersistFailed, no argv fallback). It no
  // longer merely returns `false`: a `false` return from a writable entry is
  // the host's `!dirty` branch, which means "already stored", i.e. success.
  property bool persistFails: false
  // The last pipOutcome() payload, so a scenario can read what the service
  // decided AFTER it read the compositor back, not what it intended.
  property var lastPipOutcome: null
  // The entry shell.json starts with. The live value lives in
  // fakeHost.shellConfig from here on; `barEntry` below reads it back.
  readonly property var seedBarEntry: ({
    id: harness.pluginId,
    playlistUrl: Quickshell.env("OMARCHY_IPTV_PLAYLIST") || "",
    epgUrl: Quickshell.env("OMARCHY_IPTV_EPG") || "",
    refreshMinutes: 360,
    mpvArgs: Quickshell.env("OMARCHY_IPTV_MPV_ARGS") || "",
    showChannelName: Quickshell.env("OMARCHY_IPTV_SHOW_NAME") !== "false",
    maxRecents: 10,
    barLabelMaxWidth: parseInt(Quickshell.env("OMARCHY_IPTV_LABEL_MAX") || "180", 10),
    // M2-03. Seeded like every other key so `set`/`setStored` drive the same
    // path at runtime; the defaults match manifest.json exactly, because a
    // harness that is more generous than the real entry is the fake this
    // project has been bitten by (CLAUDE.md rule 10).
    channelOrder: Quickshell.env("OMARCHY_IPTV_ORDER") || "playlist",
    numberEntryMs: parseInt(Quickshell.env("OMARCHY_IPTV_ENTRY_MS") || "2000", 10),
    barShowChannelNumber: Quickshell.env("OMARCHY_IPTV_BAR_NUMBER") !== "false",
    // M2-05, same rule: seeded so `set pipCorner ...` drives the real path,
    // and with the design's own defaults so this fake is never more generous
    // than the bar entry a user actually has. These three join manifest.json
    // when lane V1's Model.SETTING_RANGES lands (handover request 1).
    pipCorner: Quickshell.env("OMARCHY_IPTV_PIP_CORNER") || "top-right",
    pipSizePercent: parseInt(Quickshell.env("OMARCHY_IPTV_PIP_PERCENT") || "30", 10),
    pipMargin: parseInt(Quickshell.env("OMARCHY_IPTV_PIP_MARGIN") || "16", 10)
  })
  // What the host has actually stored (the shell.json truth), as opposed to
  // what it has published to the plugin, which can lag it by one write.
  readonly property var barEntry: Model.findBarEntry(fakeHost.barConfig, harness.pluginId)
  readonly property var manifest: ({
    id: harness.pluginId,
    name: "IPTV",
    version: "0.1.0-harness",
    kinds: ["bar-widget", "overlay", "service"],
    keepLoaded: true
  })

  function log() {
    var parts = []
    for (var i = 0; i < arguments.length; i++) parts.push(String(arguments[i]))
    console.log("[harness] " + parts.join(" "))
  }

  function record(name, payload) {
    var next = harness.signalLog.slice()
    next.push({ signal: name, at: Date.now(), payload: payload })
    while (next.length > 20) next.shift()
    harness.signalLog = next
    harness.log(name, JSON.stringify(payload))
  }

  // The detached player's state, read defensively. A pre-M2-02 Service has
  // none of these properties, and the scenario has to run against it to show
  // its checks failing there first; an undefined read must therefore never
  // throw and never invent a value. `socketAttached` is the observer's real
  // state, `playerUp` what the UI binds - they differ exactly during the
  // birth edge, which is the interesting window.
  function addPlayerState(out, s) {
    out.playerUp = s.playerUp === undefined ? null : s.playerUp
    out.playerPending = s.playerPending === undefined ? null : s.playerPending
    out.playerWanted = s.playerWanted === undefined ? null : s.playerWanted
    var sock = s.playerSocket
    out.socketAttached = sock === undefined ? null : (sock !== null && sock.connected === true)
    out.stopping = s.stopping === undefined ? null : s.stopping
    out.playSeq = s.playSeq === undefined ? null : s.playSeq
    out.currentEntryId = s.currentEntryId === undefined ? null : s.currentEntryId
    out.entryOwners = s.entryOwners === undefined || s.entryOwners === null ? null : Object.keys(s.entryOwners).length
    var end = s.lastEndFile
    out.lastEndFile = end === undefined || end === null ? null : { reason: end.reason, entryId: end.entryId }
    out.reconcilePending = s.reconcilePending === undefined ? null : s.reconcilePending
    out.notifiedFailureId = s.notifiedFailureId === undefined ? null : s.notifiedFailureId
    // Redacted at the source (rememberStderr -> Model.redactUrls), so a
    // scenario can assert on it without a credential reaching the log.
    out.playerStderr = s.mpvStderrTail === undefined ? [] : s.mpvStderrTail
    // Pre-change only: the attached ladder's rung. Reported so the old tree
    // stays inspectable from the same driver.
    if (s.stopStage !== undefined) out.stopStage = s.stopStage
  }

  // M2-05. The PiP state a scenario can read, every field optional for the
  // same reason addPlayerState's are: the SAME harness has to drive a
  // pre-change checkout, because that comparison is what makes a scenario
  // evidence rather than a claim (CLAUDE.md rule 10).
  //
  // `on` is the service's VERIFIED read of the compositor, not an intent, so
  // a scenario that asserts on it is asserting the same fact the feature
  // itself acts on (PIP11). `playerPid` is here because the pip-scenario
  // needs it: the stub compositor's canned clients JSON is rewritten to
  // carry the pid the service actually holds, so the pid-narrowed lookup is
  // exercised for real rather than stepped over.
  function pipSnapshot(s) {
    if (!s) return { available: null, on: null, applying: null, reason: null, playerPid: null, lastOutcome: null }
    return {
      available: s.pipAvailable === undefined ? null : s.pipAvailable,
      on: s.pipOn === undefined ? null : s.pipOn,
      applying: s.pipBusy === undefined ? null : s.pipBusy,
      reason: s.pipReason === undefined ? null : s.pipReason,
      provider: s.pipProvider === undefined ? null : s.pipProvider,
      playerPid: s.playerPid === undefined ? null : s.playerPid,
      snapshot: s.pipSnapshot === undefined || s.pipSnapshot === null ? null : true,
      lastOutcome: harness.lastPipOutcome
    }
  }

  // M2-03 10.6 / CN23. The number-entry state the four verbs answer with, in
  // one place so `number`, `commitNumber`, `cancelNumber` and `numberState`
  // cannot drift apart. Read defensively, like addPlayerState: a pre-M2-03
  // guide has none of these properties, and a scenario has to run against one
  // to show its checks failing there first (CLAUDE.md rule 10), so an
  // undefined read must answer null rather than throw or invent a value.
  //
  // URL-free by construction: a buffer, a label, channel names, a scope id
  // and a query. Nothing here ever holds a playlist URL.
  // The channel view is not exposed by the guide, so it is found by
  // objectName through the object tree. Harness-only: nothing shipped depends
  // on it.
  //
  // Takes a LIST of names and returns WHICH ONE it forced, or "" for none.
  // It used to resolve the single literal "resultList" and return a bool, and
  // the comment here claimed that a changed id would make the number
  // "visibly wrong rather than quietly optimistic". That was false in two
  // ways at once. The only caller discarded the return, so nothing was
  // visible; and the moment the guide can present a second view, a run with
  // that view on screen force-lays-out nothing, creates no delegates, and
  // reports a fast, plausible number for an empty screen -- which is the
  // quietly optimistic failure the sentence promised could not happen.
  // A budget instrument that cannot say what it measured is not an
  // instrument. openMs now puts the answer in its payload and a run that
  // names the wrong view is void rather than fast.
  function layoutView(g, names) {
    for (var i = 0; i < names.length; i++) {
      var found = harness.findById(g, names[i], 0)
      if (found && typeof found.forceLayout === "function") {
        found.forceLayout()
        return names[i]
      }
    }
    return ""
  }

  // How many delegates the view actually instantiated, which is the quantity
  // the grid work is budgeted in: on a list this is rows, on a grid it is
  // columns x rows and it grows with the column count, so a paint time
  // without it cannot be compared with another paint time.
  function realisedCount(g, name) {
    var v = harness.findById(g, name, 0)
    if (!v || !v.contentItem || !v.contentItem.children) return -1
    var kids = v.contentItem.children
    var n = 0
    for (var i = 0; i < kids.length; i++) {
      // contentItem carries non-delegate children (highlight, header); a
      // delegate is counted by the property every channel delegate declares.
      if (kids[i] && kids[i].hasOwnProperty("index")) n++
    }
    return n
  }

  // Every objectName that can be the guide's channel view, newest first.
  // A name that is not on this list cannot be measured, and openMs says so by
  // reporting view:"" rather than by returning a number for it.
  readonly property var channelViews: ["resultList"]

  function findById(node, wanted, depth) {
    if (!node || depth > 12) return null
    try {
      if (String(node.objectName) === wanted) return node
    } catch (e) {}
    var kids = node.children
    if (!kids) return null
    for (var i = 0; i < kids.length; i++) {
      var hit = harness.findById(kids[i], wanted, depth + 1)
      if (hit) return hit
    }
    return null
  }

  function numberSnapshot(g) {
    if (!g || g.numberEntry === undefined || g.numberEntry === null) {
      return { ok: false, error: "no_verb", active: null, buffer: null, kind: null, label: null,
               targetName: null, matches: null, ordinal: null, scopeId: null, cursorIndex: null,
               query: null, resume: null, cursorId: null, hasNumbers: null, cursorName: null, transient: null,
               queryLive: null }
    }
    var e = g.numberEntry
    var r = g.numberResolution === undefined || g.numberResolution === null ? {} : g.numberResolution
    var row = g.currentRows !== undefined && g.currentRows.length > g.cursorIndex && g.cursorIndex >= 0 ? g.currentRows[g.cursorIndex] : null
    return {
      ok: true,
      error: "",
      active: e.active === true,
      buffer: String(e.buffer === undefined ? "" : e.buffer),
      kind: String(r.kind === undefined ? "" : r.kind),
      label: String(r.label === undefined ? "" : r.label),
      targetName: g.numberTargetName === undefined ? null : String(g.numberTargetName),
      matches: r.matches === undefined ? 0 : r.matches,
      ordinal: r.ordinal === undefined ? 0 : r.ordinal,
      // The pre-entry snapshot, which is what Esc and Backspace restore.
      scopeId: String(e.scopeId === undefined ? "" : e.scopeId),
      cursorIndex: e.cursorIndex === undefined ? null : e.cursorIndex,
      query: String(e.query === undefined ? "" : e.query),
      cursorId: String(e.cursorId === undefined ? "" : e.cursorId),
      // CN21: the window in which a digit continues the number an auto-commit
      // closed early. Inactive AND armed is the state D-CHNO-2 turns on.
      resume: e.resume === true,
      hasNumbers: g.hasNumbers === undefined ? null : g.hasNumbers,
      numberWidth: g.numberWidth === undefined ? null : g.numberWidth,
      cursorIndexLive: g.cursorIndex,
      // F-HARNESS-1. `query` above is the PRE-ENTRY snapshot, the one Esc and
      // Backspace restore. Nothing exposed the LIVE search text, which made the
      // board's own rule for this defect -- "assert the exact query string read
      // back over IPC, never the row count" -- unimplementable: there was no
      // verb to read it back with. Named the way `cursorIndexLive` already is,
      // for the same reason.
      queryLive: String(g.query === undefined ? "" : g.query),
      cursorName: row === null ? "" : String(row.name),
      cursorChno: row === null ? "" : String(row.chnoLabel === undefined ? "" : row.chnoLabel),
      transient: g.transientText === undefined ? null : String(g.transientText)
    }
  }

  // The guide form as `state()` reports it: URL fields and the server pass
  // through Model.maskUrl, credentials become the mask token, and every
  // field carries its length, so a scenario can verify a paste without the
  // value reaching the terminal (docs/QA-SOURCES.md section 6).
  function formSnapshot(g) {
    var f = g.form
    if (!f) return null
    var values = {}
    var fields = Model.formFields(f)
    for (var i = 0; i < fields.length; i++) {
      var id = fields[i]
      var raw = String(f.values && f.values[id] !== undefined && f.values[id] !== null ? f.values[id] : "")
      var shown
      if (id === "password" || id === "username") shown = raw === "" ? "" : Model.MASK
      else if (Model.isUrlField(id) || id === "server") shown = Model.maskUrl(raw)
      else shown = raw
      values[id] = {
        value: shown, length: raw.length,
        masked: Model.isUrlField(id) ? Model.fieldMasked(f, id) : id === "password",
        revealed: Model.isUrlField(id) ? Model.fieldRevealed(f, id) : false
      }
    }
    return {
      kind: f.kind, origin: f.origin, sourceId: f.sourceId, focus: f.focus, probing: f.probing === true,
      probeHost: f.probeHost, probeKind: f.probeKind, error: f.error, values: values, parent: f.parent ? f.parent.kind : ""
    }
  }

  // ---- fake host config plumbing, in the real host's SHAPE AND ORDER
  //
  // /usr/share/omarchy/shell/shell.qml declares, in this order:
  //   59  property var shellConfig
  //   66  onShellConfigChanged: ... pluginRegistry.pluginsChanged()
  //       -> Connections (1052) -> syncPluginApis() (861)
  //       -> shellApi.barConfig = publicBarConfig() (326 -> shell.barConfig)
  //   109 readonly property var barConfig: shellConfig.bar
  // A QML change handler runs BEFORE the bindings that depend on the same
  // property are re-evaluated, so `publicBarConfig()` publishes the bar of
  // the PREVIOUS shellConfig: a plugin sees shell.json one write late. An
  // external write is flushed by the assignment after it (the user config
  // FileView re-reads the foreign change); the plugin's own write is the
  // last assignment there is, so its echo never arrives -- D-LIVE-20 and
  // D-LIVE-21. Reproduced here literally so the harness cannot mask it
  // again; the plugin must apply its own writes itself.
  QtObject {
    id: fakeHost
    property var shellConfig: ({ version: 1, bar: { layout: { left: [], center: [], right: [harness.seedBarEntry] } } })
    onShellConfigChanged: harness.syncPluginApis()
    readonly property var barConfig: fakeHost.shellConfig && fakeHost.shellConfig.bar
      ? fakeHost.shellConfig.bar : ({ layout: { left: [], center: [], right: [] } })
  }

  // shell.qml persistShellConfig (109-114): a deep copy becomes shellConfig.
  function persistShellConfig(nextConfig) {
    fakeHost.shellConfig = JSON.parse(JSON.stringify(nextConfig))
  }

  // shell.qml syncPluginApis (861-881): every plugin api is handed a fresh
  // deep copy of whatever `shell.barConfig` currently reads as.
  function syncPluginApis() {
    fakeShell.barConfig = JSON.parse(JSON.stringify(fakeHost.barConfig))
    if (barLoader.item) barLoader.item.settings = Model.findBarEntry(fakeShell.barConfig, harness.pluginId)
  }

  // The active source of a bar config as its 8-hex key (or "" when unset):
  // comparable across the stored / published sides without printing a URL.
  function entryKey(barConfig) {
    var url = Model.settingsFrom(Model.findBarEntry(barConfig, harness.pluginId)).playlistUrl
    var normalized = Model.normalizeSourceUrl(url, { origin: "cli" })
    return normalized === "" ? "" : Model.sourceKey(normalized)
  }

  // shell.qml applyShellConfig (76-89) driven by the user config FileView:
  // a FOREIGN change to shell.json is re-read and assigned a second time.
  // The host's own FileView.setText does not re-trigger its watcher, which
  // is why only external writes get this second assignment.
  function applyShellConfig() {
    fakeHost.shellConfig = JSON.parse(JSON.stringify(fakeHost.shellConfig))
  }

  Timer {
    // The user config FileView's asynchronous reaction to a foreign write.
    id: hostReloadTimer
    interval: 0
    repeat: false
    onTriggered: harness.applyShellConfig()
  }

  // Store a setting without the user config re-read: only the mutator half
  // of an external write. This is the real window a plugin sees between
  // `omarchy bar set` persisting and the FileView noticing the file, and it
  // is the state in which the host already stores a value the plugin has
  // not seen -- where updateEntryInline answers `!dirty` / false for a
  // change that is in fact already saved.
  function storeSetting(key, value) {
    var copy = JSON.parse(JSON.stringify(fakeHost.shellConfig))
    var arr = copy.bar.layout.right
    for (var i = 0; i < arr.length; i++) {
      if (arr[i] && typeof arr[i] === "object" && String(arr[i].id) === harness.pluginId) arr[i][key] = value
    }
    harness.persistShellConfig(copy)
  }

  // Change a setting at runtime the way `omarchy bar set` would: the IPC
  // mutator persists it (assignment 1), then the FileView notices the
  // changed file and applies it again (assignment 2).
  function setSetting(key, value) {
    harness.storeSetting(key, value)
    hostReloadTimer.restart()
  }

  // ---- fake PluginShellApi (services/PluginShellApi.qml surface)
  QtObject {
    id: fakeShell
    property var barConfig: ({ layout: { left: [], center: [], right: [harness.seedBarEntry] } })
    property var bar: fakeBar
    function serviceFor(id) { return String(id) === harness.pluginId ? serviceLoader.item : null }
    function summon(id, payloadJson) {
      harness.log("summon", id, payloadJson || "")
      if (!guideLoader.item) return false
      guideLoader.item.open(payloadJson || "{}")
      return true
    }
    function hide(id) {
      harness.log("hide", id)
      if (guideLoader.item) guideLoader.item.close()
      return true
    }
    function toggle(id, payloadJson) { return isPluginOpen(id) ? hide(id) : summon(id, payloadJson) }
    function isPluginOpen(id) { return guideLoader.item ? guideLoader.item.opened === true : false }
    // shell.qml updateEntryInline (1078-1116) exactly: rewrite the layout
    // entry in a clone, compare with JSON.stringify, return false WITHOUT
    // persisting when nothing changed (1114), otherwise persistShellConfig
    // and return true. The echo back to the plugin is whatever
    // persistShellConfig's assignment produces -- which, by the ordering
    // reproduced in fakeHost, is the PREVIOUS bar. Nothing here hands the
    // plugin its own write; the plugin applies that itself.
    // Keys only in the log: the entry carries playlistUrl / epgUrl, which
    // may embed credentials and must not reach the terminal (S-08).
    property var updateEntryInline: harness.persistFails ? undefined : (function updateEntryInline(id, entry) {
      var e = entry || {}
      harness.log("updateEntryInline", id, "keys:", Object.keys(e).join(","), "playlist", e.playlistUrl ? "(set)" : "(none)", "epg", e.epgUrl ? "(set)" : "(none)")
      if (String(id) !== harness.pluginId || typeof e !== "object") return false
      var copy = JSON.parse(JSON.stringify(fakeHost.shellConfig))
      var sections = ["left", "center", "right"]
      var dirty = false
      for (var s = 0; s < sections.length; s++) {
        var arr = copy.bar.layout[sections[s]] || []
        for (var i = 0; i < arr.length; i++) {
          if (!arr[i] || typeof arr[i] !== "object" || String(arr[i].id) !== harness.pluginId) continue
          var next = { id: harness.pluginId }
          for (var k in e) if (k !== "id") next[k] = e[k]
          if (JSON.stringify(arr[i]) !== JSON.stringify(next)) { arr[i] = next; dirty = true }
        }
      }
      if (!dirty) { harness.log("updateEntryInline: nothing changed (already stored)"); return false }
      // persistShellConfig republishes fakeShell.barConfig through
      // syncPluginApis -- one write behind, exactly like the real host.
      harness.persistShellConfig(copy)
      return true
    })
  }

  // Source signals (URL-free payloads by contract) go to the log and to the
  // `signals()` ring so a scripted scenario can follow them. The clipboard
  // answer (clipboardText) is deliberately not observed: it may carry
  // credentials.
  Connections {
    target: serviceLoader.item
    function onSourceProbeFinished(result) { harness.record("sourceProbeFinished", result) }
    function onSourceSwitched(id) { harness.record("sourceSwitched", { id: id, channels: serviceLoader.item ? serviceLoader.item.channels.length : -1 }) }
    function onSourceRemoved(id) { harness.record("sourceRemoved", { id: id }) }
    function onSourcesPersistFailed(reason) { harness.record("sourcesPersistFailed", { reason: reason }) }
    function onConfiguredChanged() { harness.record("configuredChanged", { configured: serviceLoader.item ? serviceLoader.item.configured : null }) }
    // M2-05. The VERIFIED outcome of one PiP sequence, which is the only
    // moment the service claims anything worked. A pre-change service has no
    // such signal and Connections simply never fires this, which is what
    // lets the same harness drive both trees.
    function onPipOutcome(result) {
      harness.lastPipOutcome = result
      harness.record("pipOutcome", result)
    }
  }

  // ---- fake PluginBarApi (Ui/PluginBarApi.qml surface)
  QtObject {
    id: fakeBar
    property var shell: fakeShell
    property color foreground: Color.foreground
    property color barForeground: Color.bar.text
    property color background: Color.bar.background
    property color urgent: Color.urgent
    property string fontFamily: Style.font.family
    property string position: "top"
    property bool vertical: Quickshell.env("OMARCHY_IPTV_VERTICAL") === "1"
    property int barSize: vertical ? Style.bar.sizeVertical : Style.bar.sizeHorizontal
    property bool transparent: false
    property bool foregroundAnimationEnabled: true
    function showTooltip(target, text) { harness.lastTooltip = String(text); harness.log("tooltip:", text) }
    function hideTooltip(target) {}
    function registerClickTarget(target) {}
    function unregisterClickTarget(target) {}
    function moduleWidgets(id) { return barLoader.item ? [barLoader.item] : [] }
    function run(command) { harness.log("bar.run", command) }
  }

  // ---- the three entry points, loaded from the repo
  Loader {
    id: serviceLoader
    source: "file://" + harness.repoRoot + "/Service.qml"
    onLoaded: {
      item.shell = fakeShell
      item.manifest = harness.manifest
      harness.log("service loaded; helper", item.helperPath, "cache", item.cacheDir, "socket", item.socketPath)
    }
    onStatusChanged: if (status === Loader.Error) console.warn("[harness] Service.qml failed to load")
  }

  Loader {
    id: guideLoader
    // The initial property is passed only in floating mode: a pre-change tree
    // (OMARCHY_IPTV_PLUGIN_ROOT at a baseline) has no such property and must
    // still load in the default mode for a rule-11 comparison.
    Component.onCompleted: setSource("file://" + harness.repoRoot + "/Guide.qml",
                                     harness.floatingGuide ? { harnessFloatingWindow: true } : {})
    onLoaded: {
      item.shell = fakeShell
      item.manifest = harness.manifest
      item.service = serviceLoader.item
      harness.log("guide loaded")
    }
    onStatusChanged: if (status === Loader.Error) console.warn("[harness] Guide.qml failed to load")
  }

  // A fake bar strip along the top edge hosting the widget (right-aligned
  // like the default section).
  PanelWindow {
    id: fakeBarWindow
    anchors { top: true; left: true; right: true }
    implicitHeight: fakeBar.vertical ? Style.bar.sizeVertical : Style.bar.sizeHorizontal
    color: Color.bar.background
    WlrLayershell.namespace: "omarchy-iptv-harness"
    WlrLayershell.layer: WlrLayer.Top
    exclusionMode: ExclusionMode.Ignore

    Text {
      anchors.left: parent.left
      anchors.leftMargin: Style.space(10)
      anchors.verticalCenter: parent.verticalCenter
      text: "omarchy-iptv dev harness"
      color: Color.bar.text
      opacity: 0.6
      font.family: Style.font.family
      font.pixelSize: Style.font.caption
    }

    Loader {
      id: barLoader
      anchors.right: parent.right
      anchors.rightMargin: Style.space(10)
      anchors.verticalCenter: parent.verticalCenter
      source: "file://" + harness.repoRoot + "/BarWidget.qml"
      onLoaded: {
        item.bar = fakeBar
        item.settings = Model.findBarEntry(fakeShell.barConfig, harness.pluginId)
        harness.log("bar widget loaded")
      }
      onStatusChanged: if (status === Loader.Error) console.warn("[harness] BarWidget.qml failed to load")
    }
  }

  // ---- driver: `qs ipc -p <root> call harness <fn> [args]` (see run.sh)
  IpcHandler {
    target: "harness"

    function open(payload: string): string { fakeShell.summon(harness.pluginId, payload); return "ok" }
    // PERF-01 / M2-04. Times the guide's own open path, in-engine, so the
    // number is not a round trip through the socket and a shell. The guide is
    // closed first so every call measures a real open, and the list is forced
    // to lay out (forceLayout) before the clock stops: without that the
    // delegates -- which is where the logo Images live -- are created after
    // the measurement and the budget measures nothing.
    function openMs(times: int): string {
      var g = guideLoader.item
      if (!g) return "{}"
      var n = times > 0 ? times : 5
      var out = []
      var forced = ""
      for (var i = 0; i < n; i++) {
        fakeShell.hide(harness.pluginId)
        var t0 = Date.now()
        fakeShell.summon(harness.pluginId, "{}")
        // The return is USED. Discarding it is what made the old instrument
        // blind: `view` below is the only thing that says the number belongs
        // to the screen the caller thinks it measured.
        forced = harness.layoutView(g, harness.channelViews)
        out.push(Date.now() - t0)
      }
      return JSON.stringify({ ms: out, rows: g.currentRows.length,
                              logoColumn: g.logoColumn, showLogos: g.showLogos,
                              view: forced,
                              realised: forced === "" ? -1 : harness.realisedCount(g, forced) })
    }
    function close(): string { fakeShell.hide(harness.pluginId); return "ok" }
    // The theme tokens the guide paints with, as THIS shell resolved them, so
    // a headless capture is checked against the running value rather than a
    // number copied from a theme file; and which window the loaded guide
    // reports hosting it (the harness-only floating mode, or production).
    function theme(): string {
      var g = guideLoader.item
      // Which window the guide LOADED, read from the loaded object's own
      // type (String(hostWindow) is "<class>(0x...)"), never from the
      // property that asked for it: a `harnessFloatingWindow` reading true
      // beside an instantiated layer window would have said "floating" about
      // a window no headless capture can see. The address is dropped. The
      // class behind PanelWindow is platform-specific -- measured under cage
      // it is qs::wayland::layershell::WaylandPanelInterface, not the
      // PanelWindowInterface the qmltypes export -- so "Panel" is the token.
      var host = g && g.hostWindow ? String(g.hostWindow).split("(")[0] : ""
      var kind = host.indexOf("FloatingWindow") >= 0 ? "floating"
               : host.indexOf("Panel") >= 0 ? "layer" : "none"
      return JSON.stringify({
        background: String(Color.background), menuBackground: String(Color.menu.background),
        guideWindow: kind, guideWindowType: host
      })
    }
    function toggle(): string { return fakeShell.toggle(harness.pluginId, "{}") ? "ok" : "no" }
    function query(text: string): string { if (guideLoader.item) guideLoader.item.setQuery(text); return "ok" }
    function mode(): string { if (guideLoader.item) guideLoader.item.switchMode(); return "ok" }
    function move(delta: int): string { if (guideLoader.item) guideLoader.item.moveCursorBy(delta, true); return "ok" }
    function scope(delta: int): string { if (guideLoader.item) guideLoader.item.moveScopeBy(delta); return "ok" }
    function setScope(id: string): string { if (guideLoader.item) guideLoader.item.setScope(id); return "ok" }
    function activate(keepOpen: bool): string { if (guideLoader.item) guideLoader.item.activate(keepOpen); return "ok" }
    function favorite(): string { if (guideLoader.item) guideLoader.item.toggleFavoriteAt(guideLoader.item.cursorIndex); return "ok" }
    function remove(): string { if (guideLoader.item) guideLoader.item.removeAt(guideLoader.item.cursorIndex); return "ok" }
    // Play a channel by id without going through the guide, so a player
    // scenario needs no window focus and no keystrokes. keepOpen is true:
    // the service does the playback half and leaves focus alone.
    function play(id: string): string {
      var s = serviceLoader.item
      return s && s.play(String(id), true, "") ? "ok" : "no"
    }
    // ---- channel numbers (M2-03). `channel` is a PASSTHROUGH to the service
    // function the plugin's own IPC verb calls, not a second implementation
    // of it: a scenario that drove a copy would prove nothing about the verb
    // a user runs (CLAUDE.md rule 12). A pre-change service has no
    // tuneByNumber, and the scenario has to run against one to show its
    // checks failing there first, so the absence answers rather than throws.
    function channel(n: string): string {
      var s = serviceLoader.item
      if (!s || typeof s.tuneByNumber !== "function") return JSON.stringify({ ok: false, kind: "channel", error: { code: "no_verb" } })
      return JSON.stringify(s.tuneByNumber(String(n)))
    }
    // The channel-number index, counts only: no names, no ids, no URLs.
    function chnoIndex(): string {
      var s = serviceLoader.item
      var ix = s ? s.chnoIndex : null
      if (!ix) return JSON.stringify({ hasNumbers: null, count: null, duplicates: null, maxLabelLen: null })
      return JSON.stringify({ hasNumbers: ix.hasNumbers === undefined ? null : ix.hasNumbers,
                              count: ix.count === undefined ? null : ix.count,
                              duplicates: ix.duplicates === undefined ? null : ix.duplicates,
                              maxLabelLen: ix.maxLabelLen === undefined ? null : ix.maxLabelLen })
    }
    // ---- channel numbers, the GUIDE side (M2-03 10.6, ruling CN23). The
    // four verbs the plan specified and nobody built, which is why scenarios
    // N1-N16 and N21-N24 had no runner at all.
    //
    // `number` feeds one character at a time through `handleSharedKey`, which
    // is the guide's real router for these keys and carries the listMode
    // guard of 2.9 -- so a digit typed in search mode stays literal here for
    // the same reason it does on a keyboard (N16), and the unnumbered-
    // playlist transient (N14) is reached through the same routing as well.
    // Driving pushNumberEntry directly would step over both. "<" is
    // Backspace; anything else is refused rather than silently ignored,
    // because a scenario that typed "x" and saw nothing would read as a pass.
    function number(keys: string): string {
      var g = guideLoader.item
      if (!g || typeof g.handleNumberKey !== "function" || typeof g.handleSharedKey !== "function")
        return JSON.stringify(harness.numberSnapshot(null))
      var text = String(keys)
      for (var i = 0; i < text.length; i++) {
        var ch = text.charAt(i)
        if (ch === "<") g.handleSharedKey({ text: "\b", modifiers: 0, key: Qt.Key_Backspace })
        else if (Model.isNumberEntryKey(ch)) g.handleSharedKey({ text: ch, modifiers: 0, key: 0 })
        else return JSON.stringify({ ok: false, error: "bad_key", key: ch })
      }
      return JSON.stringify(harness.numberSnapshot(g))
    }
    function numberState(): string { return JSON.stringify(harness.numberSnapshot(guideLoader.item)) }
    // Enter and Space, with their two meanings (CN1). The answer carries the
    // state AFTER the commit, plus what the commit reported, so a scenario
    // sees both halves in one round trip.
    function commitNumber(play: bool, keepOpen: bool): string {
      var g = guideLoader.item
      if (!g || typeof g.commitNumberEntry !== "function") return JSON.stringify(harness.numberSnapshot(null))
      var landed = g.commitNumberEntry({ play: play, keepOpen: keepOpen, reason: "enter" })
      var out = harness.numberSnapshot(g)
      out.landed = landed
      return JSON.stringify(out)
    }
    function cancelNumber(): string {
      var g = guideLoader.item
      if (!g || typeof g.cancelNumberEntry !== "function") return JSON.stringify(harness.numberSnapshot(null))
      var cancelled = g.cancelNumberEntry()
      var out = harness.numberSnapshot(g)
      out.cancelled = cancelled
      return JSON.stringify(out)
    }
    // ---- picture in picture (M2-05). A PASSTHROUGH to the service function
    // the plugin's own IPC verb calls, not a second implementation of it: a
    // scenario driving a copy would prove nothing about the verb a user runs
    // (CLAUDE.md rule 12). A pre-change service has no requestPip, and the
    // scenario has to run against one to show its checks failing there
    // first, so the absence answers rather than throws.
    function pip(mode: string): string {
      var s = serviceLoader.item
      if (!s || typeof s.requestPip !== "function")
        return JSON.stringify({ ok: false, kind: "pip", error: { code: "no_verb" } })
      return JSON.stringify(s.requestPip(String(mode)))
    }
    // The guide's `p` goes through the same service entry point, so the two
    // surfaces cannot drift. Answers no_verb on a pre-M2-05 tree.
    function pipKey(): string {
      var s = serviceLoader.item
      if (!s || typeof s.togglePip !== "function")
        return JSON.stringify({ ok: false, kind: "pip", error: { code: "no_verb" } })
      return JSON.stringify(s.togglePip())
    }
    function pipState(): string { return JSON.stringify(harness.pipSnapshot(serviceLoader.item)) }
    function stop(): string { if (serviceLoader.item) serviceLoader.item.stop(); return "ok" }
    function refresh(): string { if (serviceLoader.item) serviceLoader.item.refresh(); return "ok" }
    function zap(delta: int): string { return serviceLoader.item && serviceLoader.item.zap(delta) ? "ok" : "no" }
    function set(key: string, value: string): string {
      var v = value
      if (value === "true") v = true
      else if (value === "false") v = false
      else if (/^-?\d+$/.test(value)) v = parseInt(value, 10)
      harness.setSetting(key, v)
      return "ok"
    }
    // `set` without the user config re-read: the host stores the value but
    // has not published it yet, so the plugin still sees the previous one.
    function setStored(key: string, value: string): string {
      var v = value
      if (value === "true") v = true
      else if (value === "false") v = false
      else if (/^-?\d+$/.test(value)) v = parseInt(value, 10)
      harness.storeSetting(key, v)
      return "ok"
    }
    function tooltip(): string { return harness.lastTooltip }
    // ---- sources (M2-01): the service actions, results as JSON. Arguments
    // may carry a URL; results, `sources()` and `state()` never do. Pass ""
    // for an argument you do not need (qs ipc passes strings positionally).
    function addSource(playlistUrl: string, epgUrl: string, label: string): string {
      var s = serviceLoader.item
      return s ? JSON.stringify(s.addSource({ playlistUrl: playlistUrl, epgUrl: epgUrl, label: label })) : "{}"
    }
    function updateSource(key: string, json: string): string {
      var s = serviceLoader.item
      var fields = {}
      try { fields = JSON.parse(json || "{}") } catch (e) { return JSON.stringify({ ok: false, code: "bad_json" }) }
      return s ? JSON.stringify(s.updateSource(key, fields)) : "{}"
    }
    function removeSource(key: string): string { var s = serviceLoader.item; return s ? JSON.stringify(s.removeSource(key)) : "{}" }
    function switchSource(key: string): string { var s = serviceLoader.item; return s ? JSON.stringify(s.switchSource(key)) : "{}" }
    function retrySource(key: string): string { var s = serviceLoader.item; return s ? JSON.stringify(s.retrySource(key)) : "{}" }
    function cancelProbe(): string { var s = serviceLoader.item; return s ? JSON.stringify(s.cancelProbe()) : "{}" }
    function xtream(server: string, username: string, password: string): string {
      var s = serviceLoader.item
      return s ? JSON.stringify(s.buildXtreamSource({ server: server, username: username, password: password })) : "{}"
    }
    function sources(): string { var s = serviceLoader.item; return s ? JSON.stringify(s.sources) : "[]" }
    // M2-04. Drives the REAL Sources key path (handleSourcesLetter) rather
    // than calling the toggle directly, so a scenario exercises the same
    // dispatch a keystroke would: `g` must reach toggleLogos through the
    // letter table, not around it.
    // Drives the REAL list-mode key path (handleListLetter -> the Model
    // letter table -> the guide action), so a scenario exercises the same
    // dispatch a keystroke would rather than calling the action directly.
    function listKey(text: string): string {
      var g = guideLoader.item
      if (!g) return "no"
      g.handleListLetter(text)
      return "ok"
    }
    function sourcesKey(text: string): string {
      var g = guideLoader.item
      if (!g) return "no"
      if (text === "enter") { g.openSources(); return "ok" }
      if (text === "confirm") { g.confirmLogos(); return "ok" }
      if (text === "cancel") { g.cancelRemove(); return "ok" }
      g.handleSourcesLetter(text)
      return "ok"
    }
    function activeCache(): string { var s = serviceLoader.item; return s ? s.activeCacheDir : "" }
    // The edit form's view of a record with the URLs masked (the raw
    // playlistUrl / epgUrl fields are dropped so nothing leaks into the terminal).
    function sourceEdit(key: string): string {
      var s = serviceLoader.item
      var e = s ? s.sourceForEdit(key) : null
      if (!e) return "null"
      return JSON.stringify({ id: e.id, label: e.label, labelCustom: e.labelCustom, kind: e.kind, origin: e.origin, host: e.host, playlistMasked: e.playlistMasked, epgMasked: e.epgMasked })
    }
    // SR31 name for the same view: masked strings only.
    function editMasked(key: string): string { return sourceEdit(key) }
    // The last 20 source signal payloads, oldest first.
    function signals(): string { return JSON.stringify(harness.signalLog) }
    // "true" (or no argument) takes updateEntryInline off the shell api, the
    // way a host that cannot write our entry leaves it; "false" restores it.
    // (A `false` RETURN is no longer a failure: with a writable entry it is
    // the host's `!dirty` branch, i.e. the value is already stored.)
    function failPersist(on: string): string {
      harness.persistFails = !(String(on) === "false" || String(on) === "0")
      return harness.persistFails ? "persist fails" : "persist ok"
    }
    // What the host has STORED for our entry (shell.json) versus what it has
    // PUBLISHED to the plugin (shell.barConfig). They differ by one write
    // after a plugin's own updateEntryInline: the regression D-LIVE-20 is
    // exactly a plugin that waits for `published` to catch up with `stored`.
    // Both sides are reported as source keys, never URLs (S-08).
    function hostEntry(): string {
      return JSON.stringify({ stored: harness.entryKey(fakeHost.barConfig), published: harness.entryKey(fakeShell.barConfig) })
    }
    function widget(): string {
      var w = barLoader.item
      if (!w) return "{}"
      // `number` is what the bar actually DRAWS (so barShowChannelNumber
      // false and a vertical bar both report ""), `chno` what it knows.
      return JSON.stringify({ service: w.service !== null, glyph: w.glyph, label: w.showLabel ? w.nowPlayingName : "",
                              number: w.showNumber === true ? String(w.nowPlayingChno) : "",
                              chno: w.nowPlayingChno === undefined ? null : String(w.nowPlayingChno),
                              tooltip: w.tooltip, width: w.implicitWidth })
    }
    function state(): string {
      var g = guideLoader.item
      var s = serviceLoader.item
      var out = { guide: null, service: null }
      var s2 = serviceLoader.item
      if (g) {
        out.guide = {
          opened: g.opened, mode: g.mode, query: g.query, scopeId: g.scopeId, effectiveScope: g.effectiveScope,
          cursorIndex: g.cursorIndex, rows: g.currentRows.length, resultTotal: g.resultTotal, truncated: g.truncated,
          rowsHaveDetail: g.rowsHaveDetail, emptyKind: g.emptyKind, bannerKind: g.bannerKind, bannerText: g.bannerText,
          scopeLabel: g.scopeLabelText, footer: g.footerStatusText, warning: g.warningText, narrow: g.narrow, showColumn: g.showColumn,
          cursorName: g.currentRows.length > g.cursorIndex && g.cursorIndex >= 0 ? g.currentRows[g.cursorIndex].name : "",
          // The cursor row's DETAIL line, composed the way the delegate
          // composes it. Without this a scenario can prove a failure mark
          // reached the service and never that the row says so, which is the
          // grep-shaped acceptance rule 14 exists to forbid.
          cursorDetail: (function () {
            if (!(g.currentRows.length > g.cursorIndex && g.cursorIndex >= 0)) return ""
            var c = g.currentRows[g.cursorIndex]
            var id = Model.channelId(c)
            return Model.rowDetail({
              showGroup: Model.rowShowsGroup({ scopeIsGroup: g.scopeIsGroup, groupsNarrow: g.groupAxis.narrows }),
              group: Model.primaryGroup(c),
              failedAt: Model.failedWhen(g.failedMap[id], g.nowSec),
              nowTitle: "", nextTitle: "" })
          })(),
          scopes: g.scopeList.map(function(e) { return e.id + "=" + e.count }),
          // Sources screens (SR31): mode transitions, the cursor and the form
          // with masked values and lengths.
          returnMode: g.guide ? String(g.guide.returnMode || "") : "",
          sourceCursor: g.sourceCursor, sourceCursorKind: g.sourceCursorKind, sourceCount: g.sourceCount,
          formFocus: g.formFocus, formActive: g.formActive, formProbing: g.formProbing,
          // D-SRC-04: the Sources result line (a failed switch probe) and the
          // derived `Fetching from <host>...` text; both URL-free.
          sourcesNotice: g.sourcesNotice !== undefined ? g.sourcesNotice : "",
          sourcesProbeText: g.sourcesProbeText !== undefined ? g.sourcesProbeText : "",
          invalidSettingsText: g.invalidSettingsText !== undefined ? g.invalidSettingsText : "",
          footerHint: g.footerHintText !== undefined ? String(g.footerHintText).replace(/<[^>]*>/g, "") : "",
          form: harness.formSnapshot(g),
          // M2-03 10.6: the guide's own number state, so a scenario can read
          // the entry and the column without a screenshot.
          hasNumbers: g.hasNumbers === undefined ? null : g.hasNumbers,
          channelOrder: g.serviceReady && g.service.channelOrder !== undefined ? String(g.service.channelOrder) : null,
          numberEntry: harness.numberSnapshot(g),
          numberWidth: g.numberWidth === undefined ? null : g.numberWidth,
          // M2-04 logos: the column and its width, so a scenario can read
          // whether the slot is reserved without a screenshot, plus what the
          // consent screen WOULD say (it is composed from a survey that
          // contacts nothing, so reading it here contacts nothing either).
          showLogos: g.showLogos === undefined ? null : g.showLogos,
          logoColumn: g.logoColumn === undefined ? null : g.logoColumn,
          logoWidth: g.logoWidth === undefined ? null : g.logoWidth,
          logoDir: g.logoDir === undefined ? "" : String(g.logoDir),
          confirmKind: g.confirmKind === undefined ? "" : String(g.confirmKind),
          confirmMessage: g.confirmMessage === undefined ? "" : String(g.confirmMessage),
          // PAUSE LIVE TV: what the bar and the guide actually say, so a
          // scenario can observe the state rather than infer it.
          paused: s2 && s2.paused !== undefined ? s2.paused : null,
          // D-LOGO-8: how many logos the shell knows are on disk RIGHT NOW.
          // The defect was that this stayed 0 until the fetch exited.
          logoCount: s2 && s2.logoHave ? Object.keys(s2.logoHave).length : null,
          // keep-my-place diagnostics: which failure the guide can see, and
          // whether the cursor restore is still pending or was consumed.
          lastFailedId: g.lastFailedId === undefined ? null : String(g.lastFailedId),
          restoreCursorTo: g.restoreCursorTo === undefined ? null : String(g.restoreCursorTo),
          placeMark: g.placeMark === undefined || g.placeMark === null ? null : JSON.stringify(g.placeMark),
          pauseHint: (function () {
            var pairs = Model.footerHints({ mode: "list", playing: g.playingId !== "",
                                            paused: s2 && s2.paused === true })
            var hit = pairs.filter(function (p) { return p[0] === Model.PAUSE_KEY })
            return hit.length ? hit[0][1] : ""
          })()
        }
      }
      if (s) {
        out.service = s.statusSummary()
        out.service.failedAt = s.failedAt
        // ---- detached player (M2-02), every field optional so the SAME
        // harness drives a pre-change checkout: that comparison is what
        // makes a scenario evidence rather than a claim (CLAUDE.md rule 10).
        harness.addPlayerState(out.service, s)
        out.service.healthSkips = s.healthSkips
        out.service.activeSourceKey = s.activeSourceKey
        out.service.stateLoaded = s.stateLoaded
        out.service.cacheReady = s.cacheReady
        out.service.probing = s.probing
        out.service.probingKey = s.probingKey
        out.service.switching = s.switching
        out.service.sourceErrors = s.sourceErrors
        out.service.settingsInvalid = s.settingsInvalid ? { code: s.settingsInvalid.code } : null
        out.service.cacheLayout = s.userState.cacheLayout
        out.service.sourceCount = s.sourceCount
        out.service.canAddSource = s.canAddSource
        // M2-03. statusSummary() already carries hasNumbers and channelOrder
        // on a current service; these are the settings as the SERVICE read
        // them, which is what a `set channelOrder number` scenario watches.
        out.service.numberEntryMs = s.numberEntryMs === undefined ? null : s.numberEntryMs
        out.service.barShowChannelNumber = s.barShowChannelNumber === undefined ? null : s.barShowChannelNumber
        out.service.nowPlayingChno = s.nowPlayingChno === undefined ? null : s.nowPlayingChno
        // M2-05. statusSummary() carries its own `pip` block on a current
        // service; this is the richer one a scenario drives against, with the
        // player pid the stub compositor's fixture has to match.
        out.service.pip = harness.pipSnapshot(s)
        out.service.persistFails = harness.persistFails
      }
      return JSON.stringify(out)
    }
  }

  Component.onCompleted: {
    harness.log("root", harness.repoRoot, "playlist", harness.barEntry.playlistUrl ? "(set)" : "(none)")
    if (Quickshell.env("OMARCHY_IPTV_OPEN") === "1") openTimer.start()
  }

  Timer {
    id: openTimer
    interval: 600
    repeat: false
    onTriggered: fakeShell.summon(harness.pluginId, "{}")
  }
}
