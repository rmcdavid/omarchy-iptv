import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import qs.Commons

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
    // Keys only: the entry carries playlistUrl / epgUrl, which may embed
    // credentials and must not reach the terminal (S-08).
    function updateEntryInline(id, entry) {
      var e = entry || {}
      harness.log("updateEntryInline", id, "keys:", Object.keys(e).join(","), "playlist", e.playlistUrl ? "(set)" : "(none)", "epg", e.epgUrl ? "(set)" : "(none)")
      return true
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
          scopeLabel: g.scopeLabelText, footer: g.footerStatusText, narrow: g.narrow, showColumn: g.showColumn,
          cursorName: g.currentRows.length > g.cursorIndex && g.cursorIndex >= 0 ? g.currentRows[g.cursorIndex].name : "",
          scopes: g.scopeList.map(function(e) { return e.id + "=" + e.count })
        }
      }
      if (s) {
        out.service = s.statusSummary()
        out.service.failedAt = s.failedAt
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
