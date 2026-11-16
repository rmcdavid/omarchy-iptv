// scripts/dev-harness/spikes/state-private/shell.qml -- D-SINK-103's probe:
// what mode Quickshell's FileView (atomicWrites, Qt's QSaveFile) gives the
// file it writes and every temporary it writes through. ONE FileView,
// declared exactly as Service.qml's stateFile is, over $PROBE_FILE. After
// its first load (or load failure) it makes ONE write of a text carrying
// $PROBE_MARKER as a credential, in the order $PROBE_PRE / $PROBE_POST say:
//   PROBE_PRE   a helper argv (JSON) run BEFORE the write; the write is made
//               only on a reply that says ok -- D-SINK-103's order, with the
//               argv the driver built through Model.statePrivateArgv
//   PROBE_POST  a helper argv run after `saved` -- the after-save repair,
//               Model.stateModeArgv, the order 0.19.1 has with no PRE
// and then quits. measure.sh runs this under gdb and reads the modes at
// every syscall the writer makes. Holds no window and draws nothing.
import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
  id: root
  property bool started: false
  readonly property var pre: JSON.parse(Quickshell.env("PROBE_PRE") || "[]")
  readonly property var post: JSON.parse(Quickshell.env("PROBE_POST") || "[]")
  readonly property string marker: Quickshell.env("PROBE_MARKER") || "D103MARKER"

  function go() {
    if (root.started) return
    root.started = true
    if (root.pre.length > 0) {
      preProc.command = root.pre
      preProc.running = true
    } else {
      root.write()
    }
  }
  function write() {
    console.log("PROBE write")
    fv.setText(JSON.stringify({ version: 2, cacheLayout: 2, favorites: [], recents: [], activeKey: "d103d103",
                                sources: [{ key: "d103d103", url: "http://u:" + root.marker + "@provider.test/get.php", epgUrl: "",
                                            kind: "http", label: "provider.test", labelCustom: false, origin: "guide" }] }, null, 2) + "\n")
  }
  // The pre-write run's reply: its last line, ok and `private`, or no write.
  function confirmed(text) {
    var lines = String(text || "").trim().split("\n")
    try {
      var o = JSON.parse(lines[lines.length - 1])
      return o.ok === true && o.kind === "state" && o.action === "private"
    } catch (e) {
      return false
    }
  }

  Process {
    id: preProc
    stdout: StdioCollector { id: preOut; waitForEnd: true }
  }
  Connections {
    target: preProc
    function onExited(exitCode, exitStatus) {
      console.log("PROBE pre " + exitCode + " " + preOut.text.trim())
      if (exitCode === 0 && root.confirmed(preOut.text)) root.write()
      else Qt.callLater(Qt.quit)
    }
  }
  Process {
    id: postProc
    stdout: StdioCollector { id: postOut; waitForEnd: true }
  }
  Connections {
    target: postProc
    function onExited(exitCode, exitStatus) {
      console.log("PROBE post " + exitCode + " " + postOut.text.trim())
      Qt.callLater(Qt.quit)
    }
  }
  Timer {
    interval: 20000
    running: true
    onTriggered: { console.log("PROBE gave up after 20 s"); Qt.quit() }
  }

  FileView {
    id: fv
    path: Quickshell.env("PROBE_FILE")
    watchChanges: true
    atomicWrites: true
    printErrors: false
    onLoaded: { console.log("PROBE loaded"); Qt.callLater(root.go) }
    onLoadFailed: (error) => { console.log("PROBE loadFailed " + error); Qt.callLater(root.go) }
    onSaved: {
      console.log("PROBE saved")
      if (root.post.length > 0) {
        postProc.command = root.post
        postProc.running = true
      } else {
        Qt.callLater(Qt.quit)
      }
    }
    onSaveFailed: (error) => { console.log("PROBE saveFailed " + error); Qt.callLater(Qt.quit) }
  }
}
