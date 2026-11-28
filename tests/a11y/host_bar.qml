import QtQuick
import QtQuick.Window
import "Model.mjs" as Model

// Lane 2 BarWidget host.
//
// BarWidget.qml imports qs.Commons, qs.Ui and Model.mjs, and NO Quickshell
// type of its own, so the file instantiated here is a byte-for-byte copy of
// the repo's -- make_hosts.py copies it without a single edit and
// asserts the bytes match. The only substitutions are the three objects the
// Omarchy bar host injects (`bar`, its `shell`, and the Service instance),
// exactly as the contract at BarWidget.qml:12-17 describes.
//
// Never shown. A Window root with visible:false maps nothing on the
// compositor and Qt enumerates it for accessibility all the same.
Window {
  id: host
  visible: false
  width: 600
  height: 40
  title: "BAR PROBE"

  // Scenario comes from a plain file so one generated tree serves every
  // state without regenerating it.
  function scenarioName() {
    var xhr = new XMLHttpRequest()
    xhr.open("GET", Qt.resolvedUrl("barscenario.txt"), false)
    xhr.send()
    return (xhr.status === 200 || xhr.status === 0) ? String(xhr.responseText).trim() : "idle"
  }
  property string scenario: host.scenarioName()

  // The three states R7 (ARCHITECTURE.md:478) says must never be told apart
  // by colour alone, and since 2026-11-25 a fourth, "noservice" (D-A11Y-14),
  // in which the host hands no service at all. `playing` also carries the channel number, because
  // M2-03 8.1 says the number is spoken as "channel 101" and never as a
  // bare digit string.
  QtObject {
    id: fakeService
    property bool configured: host.scenario !== "unconfigured"
    property bool playing: host.scenario === "playing"
    property var nowPlaying: host.scenario === "playing" ? ({ id: "c1", name: "BBC One HD" }) : null
    property int nowPlayingChno: 101
    property bool pipOn: false
    property bool refreshing: false
    property string status: host.scenario === "error" ? "error" : "ready"
    // D-REL-16 (rule 10): the guide and the bar report their build stamp
    // (reportBuildStamp) and read the service's buildNotice. A service with
    // neither reads as one from before the stamps -- "cache" -- and every
    // footer and bar name this host grades would carry the cache words, which
    // no real service on this tree gives. So the notice is the real
    // Model.buildVerdict over what this fake is reported, never a constant.
    property var reportedStamps: ({})
    function reportBuildStamp(file, stamp) { fakeService.reportedStamps = Model.withReportedStamp(fakeService.reportedStamps, file, stamp) }
    readonly property string buildNotice: Model.buildVerdict({ reported: fakeService.reportedStamps,
                                                               loadedDisk: Model.PLUGIN_VERSION, onDisk: Model.PLUGIN_VERSION }).notice
    function refresh() {}
    function stop() {}
    function zap(direction) {}
  }

  QtObject {
    id: fakeShell
    // D-A11Y-14: the "noservice" state is a host that has none to hand.
    function serviceFor(id) { return host.scenario === "noservice" ? null : fakeService }
    function toggle(id, payload) {}
  }

  QtObject {
    id: fakeBar
    property var shell: fakeShell
    property string position: "top"
    property bool vertical: false
    property int barSize: 32
    property color barForeground: "#e0e0e0"
    property color urgent: "#ff5555"
    property string fontFamily: "monospace"
    property bool foregroundAnimationEnabled: false
    function showTooltip(item, text) {}
    function hideTooltip(item) {}
    function registerClickTarget(item) {}
    function unregisterClickTarget(item) {}
    function moduleWidgets(name) { return [] }
  }

  Loader {
    id: widgetLoader
    anchors.fill: parent
    source: "BarWidget.qml"
    onStatusChanged: {
      if (status === Loader.Error) { console.warn("BAR_LOADER_ERROR"); Qt.exit(3) }
    }
    onLoaded: {
      item.bar = fakeBar
      if (host.scenario !== "noservice") item.service = fakeService
      console.warn("BAR_SCENARIO " + host.scenario)
      // Readback of the shipping widget's own derived state, so an
      // assertion about what the bus says can be paired with what the
      // widget actually holds. Printed as one line the checker parses.
      // D-A11Y-15: with no service the widget says it is starting until its
      // resolve timer's first ask came back empty, and "service not loaded"
      // from then on, which is the state L2-BAR-08 reads; so that scenario
      // reports only once that ask is behind it.
      var report = function() {
        console.warn("BAR_READBACK " + JSON.stringify({
          scenario: host.scenario,
          glyph: item.glyph,
          glyphCodePoint: item.glyph.length > 0 ? item.glyph.codePointAt(0) : 0,
          accessibleName: item.Accessible.name,
          nowPlayingName: item.nowPlayingName,
          nowPlayingChno: item.nowPlayingChno,
          // D-REL-16: what the bar reported and what it reads back.
          reported: fakeService.reportedStamps,
          buildNotice: item.buildNotice,
          tooltip: item.tooltip
        }))
        console.warn("BAR_HOST_READY")
      }
      if (host.scenario === "noservice") { afterFirstMiss.interval = item.resolveMs + 250; afterFirstMiss.report = report; afterFirstMiss.start() }
      else Qt.callLater(report)
    }
  }
  Timer { id: afterFirstMiss; property var report: null; repeat: false; onTriggered: if (report) report() }

  // Timebox: the probe exits on its own even if the checker dies.
  Timer { running: true; interval: 25000; onTriggered: { console.warn("BAR_TIMEBOX"); Qt.exit(0) } }
}
