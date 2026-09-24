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
// R7 / UX 4.8: glyph per state (never color-only) in a BarIconButton slot,
// the now-playing name elided at Style.space(barLabelMaxWidth) on
// horizontal bars, glyph only on vertical bars, the full name in the
// tooltip. Left click toggles the guide, right click stops, middle click
// refreshes, wheel zaps one step per tick (Util.wheelSteps).
BarWidget {
  id: root
  moduleName: "io.github.rmcdavid.iptv"

  // Service.qml instance. It can be created after this widget, so we
  // re-resolve on a short timer until the host hands it out (open risk 6).
  property var service: null
  property int wheelAccumulator: 0

  // ---- timing constants (UX.md 5.9)
  readonly property int labelAnimMs: 180
  readonly property int glyphAnimMs: 160
  readonly property int resolveMs: 500
  readonly property int resolveTries: 20

  // View-side settings come from the injected entry; the service carries the
  // same values for the guide (decision 7).
  // Model.boolSetting is the ONE reading of a boolean setting (R2). This
  // widget reads its own injected entry rather than going through the
  // service's settingsFrom, so without it the rule lives in two files.
  readonly property bool showChannelName: Model.boolSetting(setting("showChannelName", true))
  readonly property int labelMaxWidth: Style.space(Model.clampSetting("barLabelMaxWidth", setting("barLabelMaxWidth", 180)))
  // M2-03 4.5: independent of showChannelName on purpose. `[ 󰕧 101 ]` on a
  // crowded bar is the useful case, and it is only reachable if the two
  // settings are separate.
  readonly property bool showChannelNumber: Model.boolSetting(setting("barShowChannelNumber", true))

  readonly property bool serviceReady: service !== null
  readonly property bool playing: serviceReady && service.playing === true
  readonly property string nowPlayingName: playing && service.nowPlaying ? String(service.nowPlaying.name || "") : ""
  // PAUSE LIVE TV: the glyph, the tooltip and the accessible name all branch
  // on it, so it is read once here.
  readonly property bool paused: playing && service.paused === true
  // The service derives this from the loaded cache. Guarded for `undefined`
  // because the harness runs this widget against a pre-change service too,
  // and an undefined read must never invent a value (engineering rule 10 (dev branch)).
  readonly property string nowPlayingChno: playing && service.nowPlayingChno !== undefined ? String(service.nowPlayingChno) : ""
  readonly property bool configured: serviceReady && service.configured === true
  readonly property bool refreshing: serviceReady && service.refreshing === true
  readonly property bool hasError: serviceReady && service.status === "error"
  // M2-05 / PIP2: picture in picture gets ONE tooltip line and no new mouse
  // gesture - every gesture is already spoken for. Guarded for `undefined`
  // like nowPlayingChno above: a service that predates PiP reports nothing,
  // and an undefined read must never invent a value (engineering rule 10 (dev branch)).
  readonly property bool pipOn: serviceReady && service.pipOn === true
  readonly property string glyph: Model.barGlyph({ playing: root.playing, error: root.hasError, paused: root.paused })
  readonly property bool showLabel: !root.vertical && root.showChannelName && root.nowPlayingName !== ""
  // Vertical bars stay glyph-only (UX 8 #12); the number is in the tooltip.
  readonly property bool showNumber: !root.vertical && root.showChannelNumber && root.nowPlayingChno !== ""
  readonly property color barFg: bar ? bar.barForeground : Color.foreground
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  // Idle dims like tailscale's inactive icon; playing and error are full.
  // D-RUNG-3 / D-RUNG-5: dim toward the BACKGROUND, not toward black.
  // Qt.darker reduces HSV value, which raises contrast against a pale
  // background, so the idle glyph rendered BOLDER than the active one on five
  // light themes. Alpha does the same job on a dark theme and the right thing
  // on a light one. The value lives in Model.js so a test calls the shipping
  // number rather than transcribing it (rule 12).
  property color glyphColor: root.playing || root.hasError ? root.barFg : Util.alpha(root.barFg, Model.BAR_IDLE_ALPHA)
  // M2-03 6.4: Model.barTooltip prepends the number to the playing line when
  // `chno` is non-empty, on vertical bars too, where the label is glyph-only.
  readonly property string tooltip: Model.barTooltip({
    serviceMissing: !root.serviceReady,
    configured: root.configured,
    playing: root.playing,
    name: root.nowPlayingName,
    chno: root.nowPlayingChno,
    error: root.hasError,
    refreshing: root.refreshing,
    pip: root.pipOn, paused: root.paused
  })

  Behavior on glyphColor {
    enabled: !root.bar || root.bar.foregroundAnimationEnabled
    ColorAnimation { duration: root.glyphAnimMs }
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

  function handlePress(button) {
    if (root.bar) root.bar.hideTooltip(root)
    root.resolveService()
    if (button === Qt.RightButton) {
      if (root.service) root.service.stop()
    } else if (button === Qt.MiddleButton) {
      if (root.service) root.service.refresh()
    } else {
      root.openGuide()
    }
  }

  function handleWheel(delta) {
    root.resolveService()
    var step = Util.wheelSteps(root.wheelAccumulator, delta)
    root.wheelAccumulator = step.remainder
    if (step.steps === 0 || !root.service) return
    // Scroll up = previous, scroll down = next (UX 3.3).
    var direction = step.steps > 0 ? -1 : 1
    var count = Math.min(3, Math.abs(step.steps))
    for (var i = 0; i < count; i++) root.service.zap(direction)
  }

  implicitWidth: root.vertical ? root.barSize : icon.implicitWidth + numberHolder.width + labelHolder.width
  implicitHeight: root.vertical ? icon.implicitHeight : root.barSize

  Accessible.role: Accessible.Button
  // M2-03 8.1: the number is spoken as "channel 101", never as a bare digit
  // string.
  Accessible.name: Model.barAccessibleName({ playing: root.playing, name: root.nowPlayingName,
                                             chno: root.nowPlayingChno, error: root.hasError, paused: root.paused })

  // Mirrors WidgetButton: registered click targets keep receiving clicks
  // while a bar popup (KeyboardPanel) is open.
  property var registeredBar: null

  function syncClickRegistration() {
    if (root.registeredBar && root.registeredBar.unregisterClickTarget) root.registeredBar.unregisterClickTarget(root)
    root.registeredBar = root.bar
    if (root.registeredBar && root.registeredBar.registerClickTarget) root.registeredBar.registerClickTarget(root)
  }

  onBarChanged: {
    root.syncClickRegistration()
    root.resolveService()
  }
  Component.onCompleted: {
    root.syncClickRegistration()
    root.resolveService()
  }
  Component.onDestruction: if (root.registeredBar && root.registeredBar.unregisterClickTarget) root.registeredBar.unregisterClickTarget(root)

  Connections {
    target: root.bar
    function onShellChanged() { root.resolveService() }
  }

  Timer {
    id: resolveTimer
    property int tries: 0
    interval: root.resolveMs
    repeat: true
    running: false
    onTriggered: {
      tries++
      root.resolveService()
      if (root.service || tries >= root.resolveTries) resolveTimer.stop()
    }
  }

  // Glyph in the standard icon slot (Style.bar.iconSlot / iconFont). The
  // root MouseArea below owns hover, clicks and wheel for icon + label
  // together (UX 7.3), so the button itself is display-only.
  BarIconButton {
    id: icon
    anchors.left: parent.left
    anchors.verticalCenter: parent.verticalCenter
    bar: root.bar
    text: root.glyph
    foreground: root.glyphColor
    useActiveColor: false
    interactive: false
    pressable: false
  }

  // The channel number, between the glyph and the name (M2-03 4.5). It sits
  // OUTSIDE the name's Style.space(barLabelMaxWidth) budget and never elides:
  // half a channel number is worse than none, and the name is the part that
  // can lose characters and stay useful.
  Item {
    id: numberHolder
    anchors.left: icon.right
    anchors.verticalCenter: parent.verticalCenter
    height: root.barSize
    width: root.showNumber ? number.implicitWidth + Style.spaceReal(8.5) : 0
    clip: true
    Behavior on width { NumberAnimation { duration: root.labelAnimMs; easing.type: Easing.OutCubic } }

    Text {
      id: number
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
      textFormat: Text.PlainText
      text: root.nowPlayingChno
      visible: root.showNumber
      color: root.barFg
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      renderType: Text.NativeRendering
      verticalAlignment: Text.AlignVCenter
    }
  }

  Item {
    id: labelHolder
    anchors.left: numberHolder.right
    anchors.verticalCenter: parent.verticalCenter
    height: root.barSize
    width: root.showLabel ? Math.min(label.implicitWidth, root.labelMaxWidth) + Style.spaceReal(8.5) : 0
    clip: true
    Behavior on width { NumberAnimation { duration: root.labelAnimMs; easing.type: Easing.OutCubic } }

    Text {
      id: label
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
      width: Math.min(implicitWidth, root.labelMaxWidth)
      textFormat: Text.PlainText
      text: root.nowPlayingName
      visible: root.showLabel
      color: root.barFg
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      renderType: Text.NativeRendering
      elide: Text.ElideRight
      verticalAlignment: Text.AlignVCenter
    }
  }

  MouseArea {
    id: hitArea
    anchors.fill: parent
    acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    onEntered: {
      root.resolveService()
      if (root.bar) root.bar.showTooltip(root, root.tooltip)
    }
    onExited: if (root.bar) root.bar.hideTooltip(root)
    onClicked: function(mouse) { root.handlePress(mouse.button) }
    onWheel: function(wheel) { root.handleWheel(wheel.angleDelta.y) }
  }
}
