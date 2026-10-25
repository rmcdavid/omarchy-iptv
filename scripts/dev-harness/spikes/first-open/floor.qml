// scripts/dev-harness/spikes/first-open/floor.qml -- the FLOOR probe for the
// D-PERF-2 attribution spike (2026-10-24): what a bare Quickshell window costs
// from `visible = true` to its first swapped frame, in the same nested cage
// the open instrument runs in. Driven over IPC by run.sh beside it; it ships
// nothing and loads nothing of the plugin.
//
//   qs ipc -p <this file> call probe create <kind>      build the window object (not shown)
//   qs ipc -p <this file> call probe present <kind>     visible = true; the clock starts
//   qs ipc -p <this file> call probe result             the run: tFirst (ms to the first
//                                                       frameSwapped), tBacker, frames in the
//                                                       500 ms after it, done
//   qs ipc -p <this file> call probe dismiss <kind>     (`show` and `hide` are qs ipc subcommands)
//   qs ipc -p <this file> call probe destroy <kind>     drop the window object (lever c)
//   qs ipc -p <this file> call probe opacity <kind> <v> the content's opacity (lever a: 0 is a
//                                                       mapped window drawing nothing)
//   qs ipc -p <this file> call probe quit
//
// Kinds: rect (one Rectangle), text (Rectangle + one Text, the guide's font
// alias), glyphs (the guide's Nerd Font glyph set at the sizes it uses, and
// an ASCII sample at every text size), panel (a PanelWindow -- in the cage it
// never maps, no layer shell; recorded, bounded by the driver).
//
// Colours and sizes are literals: CONVENTION-EXCEPTION, a probe outside the
// theme, never shipped, never loaded by the plugin. The glyphs are copied by
// codepoint from model/build.mjs GLYPHS (rule 8: glyphs live in QML by
// codepoint); the comment beside each names the source key.
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

ShellRoot {
  id: root

  readonly property double tEngine: Date.now()
  property var run: null
  readonly property int tailMs: 500
  // "monospace" is what Style.font.menuFamily resolves to for the guide
  // (Commons/Style.qml: fontFamily defaults to the fontconfig alias), so the
  // alias resolution is part of what this probe pays, as the guide does.
  readonly property string family: "monospace"
  readonly property string glyphSet: "\udb81\udd02"    // tv
    + " " + "\udb81\udd67"   // tvPlay
    + " " + "\udb81\udd03"   // tvOff
    + " " + "\udb83\udfd1"   // tvPause
    + " " + "\udb81\udcce"   // star
    + " " + "\udb81\udc0a"   // play
    + " " + "\udb80\udc26"   // alert
    + " " + "\udb80\uddd8"   // loading
    + " " + "\udb81\udc50"   // refresh
    + " " + "\udb80\udeda"   // history
    + " " + "\udb81\udc11"   // sources
    + " " + "\udb80\udd2c"   // check
    + " " + "\udb80\ude08"   // eye
    + " " + "\udb80\ude09"   // eyeOff
    + " " + "\udb81\udc15"   // plus
    + " " + "\udb80\udf06"   // key
    + " " + "\udb80\udfeb"   // pencil
    + " " + "\udb80\udd59"   // closeCircle
    + " " + "\udb81\ude1c"   // dialpad
  readonly property string asciiSample: "0123456789 ABCDEFGHIJKLMNOPQRSTUVWXYZ abcdefghijklmnopqrstuvwxyz :.-/()[]"

  function frame(kind) {
    var r = root.run
    if (!r || r.done || r.kind !== kind) return
    var now = Date.now()
    if (r.tFirst < 0) { r.tFirst = now - r.tShow; tail.restart() }
    r.frames = r.frames + 1
    root.run = r
  }
  function backer(kind, on) {
    var r = root.run
    if (!r || r.done || r.kind !== kind || !on || r.tBacker >= 0) return
    r.tBacker = Date.now() - r.tShow
    root.run = r
  }
  Timer {
    id: tail
    interval: root.tailMs
    onTriggered: { var r = root.run; if (r) { r.done = true; root.run = r } }
  }

  component ProbeWin: FloatingWindow {
    id: w
    required property string kind
    property Component content: null
    property real contentOpacity: 1
    visible: false
    color: "transparent"
    implicitWidth: 1280
    implicitHeight: 720
    title: "first-open probe " + kind
    onBackingWindowVisibleChanged: root.backer(w.kind, w.backingWindowVisible)
    Item {
      id: probe
      anchors.fill: parent
      Connections { target: probe.Window.window; function onFrameSwapped() { root.frame(w.kind) } }
    }
    Loader { anchors.fill: parent; sourceComponent: w.content; opacity: w.contentOpacity }
  }

  Component {
    id: rectContent
    Rectangle { color: "#1e1e2e" }
  }
  Component {
    id: textContent
    Rectangle {
      color: "#1e1e2e"
      Text {
        anchors.centerIn: parent
        textFormat: Text.PlainText
        color: "#cdd6f4"
        font.family: root.family
        font.pixelSize: 12
        text: "101  BBC One HD  12:30 News at Noon"
      }
    }
  }
  Component {
    id: glyphContent
    Rectangle {
      color: "#1e1e2e"
      Column {
        anchors.centerIn: parent
        spacing: 4
        // The guide draws its glyphs at Style.font.icon (14) and iconSmall (11),
        // its text at caption 10, bodySmall 11, body 12, title 14, heading 16
        // and displayLarge 28 (Guide.qml's Style.font.* uses, counted).
        Repeater {
          model: [14, 11]
          Text { required property int modelData; textFormat: Text.PlainText; color: "#cdd6f4"; font.family: root.family; font.pixelSize: modelData; text: root.glyphSet }
        }
        Repeater {
          model: [10, 11, 12, 14, 16, 28]
          Text { required property int modelData; textFormat: Text.PlainText; color: "#cdd6f4"; font.family: root.family; font.pixelSize: modelData; text: root.asciiSample }
        }
      }
    }
  }

  Loader { id: ldRect;   active: false; sourceComponent: ProbeWin { kind: "rect";   content: rectContent } }
  Loader { id: ldText;   active: false; sourceComponent: ProbeWin { kind: "text";   content: textContent } }
  Loader { id: ldGlyphs; active: false; sourceComponent: ProbeWin { kind: "glyphs"; content: glyphContent } }
  Loader {
    id: ldPanel
    active: false
    sourceComponent: PanelWindow {
      id: pw
      visible: false
      anchors { top: true; bottom: true; left: true; right: true }
      color: "transparent"
      WlrLayershell.namespace: "first-open-probe"
      onBackingWindowVisibleChanged: root.backer("panel", pw.backingWindowVisible)
      Item { id: pp; anchors.fill: parent; Connections { target: pp.Window.window; function onFrameSwapped() { root.frame("panel") } } }
      Rectangle { anchors.fill: parent; color: "#1e1e2e" }
    }
  }
  function loaderFor(kind) {
    if (kind === "rect") return ldRect
    if (kind === "text") return ldText
    if (kind === "glyphs") return ldGlyphs
    if (kind === "panel") return ldPanel
    return null
  }

  IpcHandler {
    target: "probe"
    function pid(): string { return String(Quickshell.processId) }
    function uptime(): string { return String(Date.now() - root.tEngine) }
    function create(kind: string): string {
      var l = root.loaderFor(kind)
      if (!l) return JSON.stringify({ ok: false, error: "kind" })
      if (l.active) return JSON.stringify({ ok: true, created: false })
      var t0 = Date.now()
      l.active = true
      return JSON.stringify({ ok: l.status === Loader.Ready, created: true, createMs: Date.now() - t0 })
    }
    function destroy(kind: string): string {
      var l = root.loaderFor(kind)
      if (!l) return JSON.stringify({ ok: false, error: "kind" })
      l.active = false
      return JSON.stringify({ ok: true })
    }
    function opacity(kind: string, value: string): string {
      var l = root.loaderFor(kind)
      if (!l || !l.item || l.item.contentOpacity === undefined) return JSON.stringify({ ok: false, error: "kind" })
      l.item.contentOpacity = Number(value)
      return JSON.stringify({ ok: true, opacity: l.item.contentOpacity })
    }
    function present(kind: string): string {
      var l = root.loaderFor(kind)
      if (!l || !l.item) return JSON.stringify({ ok: false, error: "not-created" })
      if (root.run && !root.run.done) return JSON.stringify({ ok: false, error: "busy" })
      var t0 = Date.now()
      root.run = { kind: kind, tShow: t0, tFirst: -1, tBacker: -1, frames: 0, done: false, sinceEngine: t0 - root.tEngine }
      l.item.visible = true
      var r = root.run
      r.setMs = Date.now() - t0
      root.run = r
      return JSON.stringify({ ok: true, kind: kind, setMs: r.setMs })
    }
    function dismiss(kind: string): string {
      var l = root.loaderFor(kind)
      if (!l || !l.item) return JSON.stringify({ ok: false, error: "not-created" })
      l.item.visible = false
      return JSON.stringify({ ok: true })
    }
    function result(): string {
      var r = root.run
      if (!r) return JSON.stringify({ state: "none" })
      return JSON.stringify({ state: r.done ? "done" : "running", kind: r.kind, tFirst: r.tFirst, tBacker: r.tBacker,
                              frames: r.frames, setMs: r.setMs, sinceEngine: r.sinceEngine })
    }
    function quit(): string { Qt.quit(); return "bye" }
  }
}
