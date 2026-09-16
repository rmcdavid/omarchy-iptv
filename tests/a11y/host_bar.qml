import QtQuick
import QtQuick.Window

// Lane 2 BarWidget host.
//
// BarWidget.qml imports qs.Commons, qs.Ui and Model.js, and NO Quickshell
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
  // by colour alone. `playing` also carries the channel number, because
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
    function refresh() {}
    function stop() {}
    function zap(direction) {}
  }

  QtObject {
    id: fakeShell
    function serviceFor(id) { return fakeService }
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
      item.service = fakeService
      console.warn("BAR_SCENARIO " + host.scenario)
      // Readback of the shipping widget's own derived state, so an
      // assertion about what the bus says can be paired with what the
      // widget actually holds. Printed as one line the checker parses.
      Qt.callLater(function() {
        console.warn("BAR_READBACK " + JSON.stringify({
          scenario: host.scenario,
          glyph: item.glyph,
          glyphCodePoint: item.glyph.length > 0 ? item.glyph.codePointAt(0) : 0,
          accessibleName: item.Accessible.name,
          nowPlayingName: item.nowPlayingName,
          nowPlayingChno: item.nowPlayingChno
        }))
        console.warn("BAR_HOST_READY")
      })
    }
  }

  // Timebox: the probe exits on its own even if the checker dies.
  Timer { running: true; interval: 25000; onTriggered: { console.warn("BAR_TIMEBOX"); Qt.exit(0) } }
}
