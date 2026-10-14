// scripts/dev-harness/spikes/filewatch/shell.qml -- R23g's probe: what
// Quickshell's FileView does to its watch. ONE FileView, declared exactly as
// Service.qml's stateFile is (watchChanges, atomicWrites, printErrors false,
// onFileChanged: reload()), over the file named by $FVPROBE_FILE. Every
// signal it raises is counted and printed; the driver (measure.sh) changes
// the file from outside and asks for the counts over `qs ipc`.
import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
  id: root
  property int changed: 0
  property int loaded: 0
  property int failed: 0
  property int saved: 0
  property int saveFailed: 0
  property string lastText: ""
  // R25a (round 15): the ORDER of signals, each with the tag of the text the
  // view holds at that moment -- what a burst's echoes carry. `burst` issues
  // n setText in one turn; `spread` one per timer tick (0 ms: one per event
  // loop turn), the shape of the service's saves across turns.
  property var log: []
  property int spreadLeft: 0
  property int spreadDone: 0
  property string spreadPrefix: ""
  property int pad: 0
  function tagOf(t) {
    var m = /"t:([A-Za-z0-9_-]+)"/.exec(String(t))
    return m ? m[1] : (String(t) === "" ? "-" : "?")
  }
  function ev(kind) { var a = root.log.slice(); a.push(kind + ":" + root.tagOf(fv.text())); root.log = a }
  function spreadTurn() {
    root.spreadDone += 1
    root.ev("set" + root.spreadDone)
    fv.setText(root.textFor(root.spreadPrefix + root.spreadDone))
    if (root.spreadDone < root.spreadLeft) Qt.callLater(root.spreadTurn)
  }
  function textFor(tag) {
    var p = ""
    for (var i = 0; i < root.pad; i++) p += "x"
    return JSON.stringify({ version: 2, favorites: ["t:" + tag], sources: [], pad: p }, null, 2) + "\n"
  }
  function note(kind, extra) {
    console.log("FVPROBE " + kind + " " + String(extra === undefined ? "" : extra))
  }
  FileView {
    id: fv
    path: Quickshell.env("FVPROBE_FILE")
    watchChanges: true
    atomicWrites: true
    printErrors: false
    onTextChanged: root.ev("text")
    onLoaded: { root.ev("loaded"); root.loaded += 1; root.lastText = fv.text(); root.note("loaded", root.lastText.length) }
    onLoadFailed: (error) => { root.failed += 1; root.note("loadFailed", error) }
    onFileChanged: { root.ev("changed"); root.changed += 1; root.note("fileChanged"); reload() }
    onSaved: { root.ev("saved"); root.saved += 1; root.note("saved") }
    onSaveFailed: (error) => { root.ev("saveFailed"); root.saveFailed += 1; root.note("saveFailed", error) }
  }
  Timer {
    id: spreadTimer
    repeat: true
    onTriggered: {
      root.spreadDone += 1
      root.ev("set" + root.spreadDone)
      fv.setText(root.textFor(root.spreadPrefix + root.spreadDone))
      if (root.spreadDone >= root.spreadLeft) stop()
    }
  }
  IpcHandler {
    target: "probe"
    function save(text: string): string { fv.setText(text); return "ok" }
    function reload(): string { fv.reload(); return "ok" }
    // R24c: the other candidate re-arm, tried only if reload() is not one --
    // the path set to "" and back, which tears the watch down and builds it
    // again.
    function repath(): string { var p = fv.path; fv.path = ""; fv.path = p; return "ok" }
    function burst(n: int, prefix: string, pad: int): string {
      root.pad = pad
      for (var i = 1; i <= n; i++) { root.ev("set" + i); fv.setText(root.textFor(prefix + i)) }
      return "ok"
    }
    function spread(n: int, prefix: string, pad: int, ms: int): string {
      root.pad = pad; root.spreadLeft = n; root.spreadDone = 0; root.spreadPrefix = prefix
      // A Timer of interval 0 never fired here (measured: 0 saves), so 0 ms
      // is one save per event-loop turn through Qt.callLater instead.
      if (ms <= 0) { Qt.callLater(root.spreadTurn); return "ok" }
      spreadTimer.interval = ms; spreadTimer.start()
      return "ok"
    }
    function events(): string { return JSON.stringify(root.log) }
    function clearEvents(): string { root.log = []; return "ok" }
    function counts(): string {
      return JSON.stringify({ changed: root.changed, loaded: root.loaded, failed: root.failed,
                              saved: root.saved, saveFailed: root.saveFailed, text: root.lastText })
    }
  }
}
