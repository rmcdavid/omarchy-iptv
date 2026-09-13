import QtQuick
import qs.Commons
import qs.Ui
import "Model.js" as Model

// BarWidget.qml -- bar entry point for io.github.rmcdavid.iptv.
// One instance per bar surface (per monitor); it owns no state. Everything
// it shows comes from Service.qml, resolved through the widget-scoped
// PluginShellApi (bar.shell.serviceFor). Host-injected properties come from
// the qs.Ui BarWidget base: `bar`, `moduleName`, `settings`.
//
// Interactions (PRODUCT.md US4): left click = guide, right click = stop,
// scroll = previous/next channel in the current group, middle click =
// refresh the playlist.
BarWidget {
  id: root
  moduleName: "io.github.rmcdavid.iptv"

  // Service.qml instance. It can be created after this widget, so we
  // re-resolve on a short timer until the host hands it out.
  property var service: null

  readonly property bool showChannelName: setting("showChannelName", true) !== false
  readonly property string glyph: "󰕧"
  readonly property string nowPlayingName: service && service.nowPlaying ? String(service.nowPlaying.name || "") : ""
  readonly property bool playing: service ? service.playing === true : false
  readonly property bool configured: service ? service.configured === true : false
  readonly property bool hasError: service && service.playlistStatus && service.playlistStatus.ok !== true && !!service.playlistStatus.error
  readonly property string label: !root.vertical && root.showChannelName && root.nowPlayingName !== ""
    ? root.glyph + "  " + Model.elide(root.nowPlayingName, 24)
    : root.glyph
  readonly property string tooltip: {
    if (!root.service) return "IPTV: service not loaded"
    if (!root.configured) return "IPTV: set a playlist with\nomarchy bar set " + root.moduleName + " playlistUrl <url>"
    if (root.nowPlayingName !== "") return "IPTV: " + root.nowPlayingName + "\nright click stops, scroll zaps"
    if (root.hasError) return "IPTV: " + String(root.service.playlistStatus.error.message || "error")
    var count = root.service.channels ? root.service.channels.length : 0
    return "IPTV: " + count + " channels" + (root.service.playlistStatus && root.service.playlistStatus.stale ? " (cached)" : "")
  }

  function resolveService() {
    if (root.service) return
    if (root.bar && root.bar.shell && typeof root.bar.shell.serviceFor === "function")
      root.service = root.bar.shell.serviceFor(root.moduleName)
    if (!root.service && !resolveTimer.running) resolveTimer.start()
  }

  function openGuide() {
    // bar.shell is scoped to our own id; toggle() reaches the overlay Loader
    // in shell.qml (multi-kind plugins route to the panel loader).
    if (root.bar && root.bar.shell && typeof root.bar.shell.toggle === "function")
      root.bar.shell.toggle(root.moduleName, "{}")
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Accessible.role: Accessible.Button
  Accessible.name: root.nowPlayingName !== "" ? "IPTV, playing " + root.nowPlayingName : "IPTV guide"

  onBarChanged: root.resolveService()
  Component.onCompleted: root.resolveService()

  Timer {
    id: resolveTimer
    property int tries: 0
    interval: 500
    repeat: true
    running: false
    onTriggered: {
      tries++
      root.resolveService()
      if (root.service || tries >= 20) resolveTimer.stop()
    }
  }

  // WidgetButton is what the clock / keyboard-layout widgets use, so hover,
  // tooltip and click-forwarding from open KeyboardPanels match the bar.
  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.label
    tooltipText: root.tooltip
    active: root.playing
    // TODO(UX): decide whether "playing" should use the bar's active color
    // (bar.urgent by convention) or stay in the plain foreground.
    useActiveColor: true
    fontSize: Style.bar.iconFont
    onPressed: function(mouseButton) {
      if (mouseButton === Qt.RightButton) {
        if (root.service) root.service.stop()
      } else if (mouseButton === Qt.MiddleButton) {
        if (root.service) root.service.refreshPlaylist(true)
      } else {
        root.openGuide()
      }
    }
    // TODO(FE): accumulate touchpad deltas with Util.wheelSteps so one notch
    // is one channel on mice and slow swipes do not skip on touchpads.
    onWheelMoved: function(delta) {
      if (root.service && delta !== 0) root.service.zap(delta < 0 ? 1 : -1)
    }
  }
}
