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
  function note(kind, extra) {
    console.log("FVPROBE " + kind + " " + String(extra === undefined ? "" : extra))
  }
  FileView {
    id: fv
    path: Quickshell.env("FVPROBE_FILE")
    watchChanges: true
    atomicWrites: true
    printErrors: false
    onLoaded: { root.loaded += 1; root.lastText = fv.text(); root.note("loaded", root.lastText.length) }
    onLoadFailed: (error) => { root.failed += 1; root.note("loadFailed", error) }
    onFileChanged: { root.changed += 1; root.note("fileChanged"); reload() }
    onSaved: { root.saved += 1; root.note("saved") }
    onSaveFailed: (error) => { root.saveFailed += 1; root.note("saveFailed", error) }
  }
  IpcHandler {
    target: "probe"
    function save(text: string): string { fv.setText(text); return "ok" }
    function reload(): string { fv.reload(); return "ok" }
    // R24c: the other candidate re-arm, tried only if reload() is not one --
    // the path set to "" and back, which tears the watch down and builds it
    // again.
    function repath(): string { var p = fv.path; fv.path = ""; fv.path = p; return "ok" }
    function counts(): string {
      return JSON.stringify({ changed: root.changed, loaded: root.loaded, failed: root.failed,
                              saved: root.saved, saveFailed: root.saveFailed, text: root.lastText })
    }
  }
}
