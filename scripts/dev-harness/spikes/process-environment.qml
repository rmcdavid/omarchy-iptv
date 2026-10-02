// scripts/dev-harness/spikes/process-environment.qml -- the measurement that
// D-SINK-8's contract rests on, kept so "measured" means "re-runnable":
//
//   timeout 20 quickshell -p scripts/dev-harness/spikes 2>&1 | grep SPIKE
//
// On Quickshell 0.3.1 / Qt 6.11.2 (2026-10-01) it printed:
//   SPIKE1 PATH=true HOME=true OMARCHY_IPTV_URL=true     environment MERGES
//   SPIKE2 after reset: OMARCHY_IPTV_URL=false PATH=true  re-assigning REPLACES
//   SPIKE3 null unsets HOME=true var=true                 null UNSETS
// Those three facts are what Service.qml's three `.environment =` sites and
// Model.fetchEnvironment's comment rely on. Needs a Wayland display; starts no
// window. Not part of the gate.
import QtQuick
import Quickshell
import Quickshell.Io

ShellRoot {
  id: root
  property int phase: 0

  // Phase 1: environment set -> does PATH survive (merge) and is our var there?
  // Phase 2: same Process object, environment reset to {} -> is the var GONE?
  // Phase 3: environment set to {X: null} -> does null unset an inherited var?
  Process {
    id: p
    stdout: StdioCollector {
      onStreamFinished: {
        var t = text
        var has = function (k) { return t.split("\n").some(function (l) { return l.indexOf(k + "=") === 0 }) }
        if (root.phase === 1) {
          console.log("SPIKE1 PATH=" + has("PATH") + " HOME=" + has("HOME") + " OMARCHY_IPTV_URL=" + has("OMARCHY_IPTV_URL"))
          root.phase = 2
          p.environment = ({})
          p.running = true
        } else if (root.phase === 2) {
          console.log("SPIKE2 after reset: OMARCHY_IPTV_URL=" + has("OMARCHY_IPTV_URL") + " PATH=" + has("PATH"))
          root.phase = 3
          p.environment = ({ "HOME": null, "OMARCHY_IPTV_URL": "again" })
          p.running = true
        } else {
          console.log("SPIKE3 null unsets HOME=" + !has("HOME") + " var=" + has("OMARCHY_IPTV_URL"))
          Qt.quit()
        }
      }
    }
  }
  Component.onCompleted: {
    root.phase = 1
    p.command = ["env"]
    p.environment = ({ "OMARCHY_IPTV_URL": "http://user:secret@h.example/x" })
    p.running = true
  }
}
