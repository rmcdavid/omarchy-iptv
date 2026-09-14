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
//
// Drive it with `run.sh ipc <fn> [args]` (IpcHandler target "harness").
ShellRoot {
  id: harness

  readonly property string repoRoot: Quickshell.env("OMARCHY_IPTV_ROOT")
  readonly property string pluginId: "io.github.rmcdavid.iptv"
  property string lastTooltip: ""
  // The last 20 source signal payloads (URL-free by contract), for `signals()`.
  property var signalLog: []
  // `failPersist true` makes the fake updateEntryInline refuse every change
  // (SR25: the service only signals sourcesPersistFailed, no argv fallback).
  property bool persistFails: false
  property var barEntry: ({
    id: harness.pluginId,
    playlistUrl: Quickshell.env("OMARCHY_IPTV_PLAYLIST") || "",
    epgUrl: Quickshell.env("OMARCHY_IPTV_EPG") || "",
    refreshMinutes: 360,
    mpvArgs: Quickshell.env("OMARCHY_IPTV_MPV_ARGS") || "",
    showChannelName: Quickshell.env("OMARCHY_IPTV_SHOW_NAME") !== "false",
    maxRecents: 10,
    barLabelMaxWidth: parseInt(Quickshell.env("OMARCHY_IPTV_LABEL_MAX") || "180", 10)
  })
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

  // Change a setting at runtime the way `omarchy bar set` would: the host
  // replaces barConfig wholesale, which is what the service binds to.
  function setSetting(key, value) {
    var next = {}
    for (var k in harness.barEntry) next[k] = harness.barEntry[k]
    next[key] = value
    harness.barEntry = next
    fakeShell.barConfig = { layout: { left: [], center: [], right: [harness.barEntry] } }
    if (barLoader.item) barLoader.item.settings = harness.barEntry
  }

  // ---- fake PluginShellApi (services/PluginShellApi.qml surface)
  QtObject {
    id: fakeShell
    property var barConfig: ({ layout: { left: [], center: [], right: [harness.barEntry] } })
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
    // Applies the entry to the fake barConfig the way the host does
    // (shell.qml updateEntryInline: full-entry replace, `id` forced, false
    // when nothing changed), so the service observes its own writes.
    // Keys only in the log: the entry carries playlistUrl / epgUrl, which
    // may embed credentials and must not reach the terminal (S-08).
    function updateEntryInline(id, entry) {
      var e = entry || {}
      harness.log("updateEntryInline", id, "keys:", Object.keys(e).join(","), "playlist", e.playlistUrl ? "(set)" : "(none)", "epg", e.epgUrl ? "(set)" : "(none)")
      if (harness.persistFails) { harness.log("updateEntryInline refused (failPersist)"); return false }
      if (String(id) !== harness.pluginId || typeof e !== "object") return false
      var next = { id: harness.pluginId }
      for (var k in e) if (k !== "id") next[k] = e[k]
      if (JSON.stringify(next) === JSON.stringify(harness.barEntry)) return false
      harness.barEntry = next
      fakeShell.barConfig = { layout: { left: [], center: [], right: [harness.barEntry] } }
      if (barLoader.item) barLoader.item.settings = harness.barEntry
      return true
    }
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
    source: "file://" + harness.repoRoot + "/Guide.qml"
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
        item.settings = harness.barEntry
        harness.log("bar widget loaded")
      }
      onStatusChanged: if (status === Loader.Error) console.warn("[harness] BarWidget.qml failed to load")
    }
  }

  // ---- driver: `qs ipc -p <root> call harness <fn> [args]` (see run.sh)
  IpcHandler {
    target: "harness"

    function open(payload: string): string { fakeShell.summon(harness.pluginId, payload); return "ok" }
    function close(): string { fakeShell.hide(harness.pluginId); return "ok" }
    function toggle(): string { return fakeShell.toggle(harness.pluginId, "{}") ? "ok" : "no" }
    function query(text: string): string { if (guideLoader.item) guideLoader.item.setQuery(text); return "ok" }
    function mode(): string { if (guideLoader.item) guideLoader.item.switchMode(); return "ok" }
    function move(delta: int): string { if (guideLoader.item) guideLoader.item.moveCursorBy(delta, true); return "ok" }
    function scope(delta: int): string { if (guideLoader.item) guideLoader.item.moveScopeBy(delta); return "ok" }
    function setScope(id: string): string { if (guideLoader.item) guideLoader.item.setScope(id); return "ok" }
    function activate(keepOpen: bool): string { if (guideLoader.item) guideLoader.item.activate(keepOpen); return "ok" }
    function favorite(): string { if (guideLoader.item) guideLoader.item.toggleFavoriteAt(guideLoader.item.cursorIndex); return "ok" }
    function remove(): string { if (guideLoader.item) guideLoader.item.removeAt(guideLoader.item.cursorIndex); return "ok" }
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
    // "true" (or no argument) makes every updateEntryInline refuse; "false" restores it.
    function failPersist(on: string): string {
      harness.persistFails = !(String(on) === "false" || String(on) === "0")
      return harness.persistFails ? "persist fails" : "persist ok"
    }
    function widget(): string {
      var w = barLoader.item
      if (!w) return "{}"
      return JSON.stringify({ service: w.service !== null, glyph: w.glyph, label: w.showLabel ? w.nowPlayingName : "", tooltip: w.tooltip, width: w.implicitWidth })
    }
    function state(): string {
      var g = guideLoader.item
      var s = serviceLoader.item
      var out = { guide: null, service: null }
      if (g) {
        out.guide = {
          opened: g.opened, mode: g.mode, query: g.query, scopeId: g.scopeId, effectiveScope: g.effectiveScope,
          cursorIndex: g.cursorIndex, rows: g.currentRows.length, resultTotal: g.resultTotal, truncated: g.truncated,
          rowsHaveDetail: g.rowsHaveDetail, emptyKind: g.emptyKind, bannerKind: g.bannerKind, bannerText: g.bannerText,
          scopeLabel: g.scopeLabelText, footer: g.footerStatusText, warning: g.warningText, narrow: g.narrow, showColumn: g.showColumn,
          cursorName: g.currentRows.length > g.cursorIndex && g.cursorIndex >= 0 ? g.currentRows[g.cursorIndex].name : "",
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
          form: harness.formSnapshot(g)
        }
      }
      if (s) {
        out.service = s.statusSummary()
        out.service.failedAt = s.failedAt
        out.service.stopStage = s.stopStage
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
