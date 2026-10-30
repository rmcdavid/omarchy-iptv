"""F-SINK-14 (2026-10-29): what the BAR draws, observed rather than composed.

The node suite calls every composer the bar uses (Model.barTooltip,
Model.barAccessibleName) over the shared shown-names fixture; this runs the
SHIPPING BarWidget.qml itself -- copied byte for byte by the accessibility
harness's own builder (tests/a11y/make_hosts.py proves the digest), under its
stand-in for the host kit -- offscreen, and reads what the widget holds for
each fixture name: the text of every Text it draws (the label is one of
them), its tooltip and its Accessible.name. Before F-SINK-14 the label
read the raw name, so a playlist name holding a credentialed URL was drawn on
the bar in full while the guide row beside it printed the host.

Offscreen, a private HOME and XDG dirs, no DISPLAY, no Wayland socket, a core
limit of zero and a timeout: nothing reaches the desktop. Skips where Qt's
`qml` or the Omarchy shell is absent. The bus half -- that this
Accessible.name is what a screen reader hears -- is the a11y harness's
L2-BAR-02 (tests/a11y/check_bus.py), and is latent on this desktop behind
D-GS-3.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
QML = os.environ.get("QML_BIN", "/usr/lib/qt6/bin/qml")
SHELL = "/usr/share/omarchy/shell"

# The fake bar and service are host_bar.qml's (tests/a11y), with the name
# driven from the fixture. Every name is set in turn and read back at once:
# QML re-evaluates a binding on read, so each reading is that name's.
PROBE = r"""
import QtQuick
import QtQuick.Window
Window {
  id: host
  visible: false
  width: 600
  height: 40
  readonly property var names: %s
  QtObject {
    id: fakeService
    property bool configured: true
    property bool playing: true
    property var nowPlaying: null
    property int nowPlayingChno: 101
    property bool pipOn: false
    property bool refreshing: false
    property bool paused: false
    property string status: "ready"
    function refresh() {}
    function stop() {}
    function zap(direction) {}
  }
  QtObject { id: fakeShell; function serviceFor(id) { return fakeService } function toggle(id, payload) {} }
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
  function drawn(item, out) {
    if (!item) return out
    if (typeof item.text === "string" && item.textFormat !== undefined && item.visible) out.push(item.text)
    var kids = item.children || []
    for (var i = 0; i < kids.length; i++) drawn(kids[i], out)
    return out
  }
  Loader {
    anchors.fill: parent
    source: "BarWidget.qml"
    onStatusChanged: if (status === Loader.Error) { console.log("BAR_SHOWN_ERROR"); Qt.exit(3) }
    onLoaded: {
      item.bar = fakeBar
      item.service = fakeService
      Qt.callLater(function () {
        var out = []
        for (var i = 0; i < host.names.length; i++) {
          fakeService.nowPlaying = { id: "c" + i, name: host.names[i] }
          out.push({ drawn: host.drawn(item, []), tooltip: item.tooltip, accessibleName: item.Accessible.name })
        }
        console.log("BAR_SHOWN " + JSON.stringify(out))
        Qt.exit(0)
      })
    }
  }
  Timer { running: true; interval: 20000; onTriggered: { console.log("BAR_SHOWN_TIMEBOX"); Qt.exit(4) } }
}
"""


class BarShownNamesTest(unittest.TestCase):

    def setUp(self):
        if not os.path.isfile(QML) or not os.path.isdir(os.path.join(SHELL, "Ui")):
            self.skipTest("no Qt qml runtime or no Omarchy shell here; the bar cannot be observed")

    def fixture(self):
        with open(os.path.join(HERE, "fixtures", "shown-names.json"), encoding="utf-8") as fh:
            return json.load(fh)["names"]

    def observe(self, names):
        work = tempfile.mkdtemp(prefix="omarchy-iptv-bar-")
        self.addCleanup(shutil.rmtree, work, True)
        tree = os.path.join(work, "tree")
        home = os.path.join(work, "home")
        os.makedirs(home, mode=0o700)
        build = {"PATH": "/usr/bin:/bin", "HOME": home, "A11Y_TREE": tree, "A11Y_REPO": REPO, "LANG": "C.UTF-8"}
        for script in ("make_tree.py", "make_hosts.py"):
            done = subprocess.run([sys.executable, "-I", os.path.join(HERE, "a11y", script)], env=build,
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(done.returncode, 0, script + ": " + done.stdout[-400:] + done.stderr[-400:])
        with open(os.path.join(tree, "barshown.qml"), "w", encoding="utf-8") as fh:
            fh.write(PROBE % json.dumps(names))
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": home, "XDG_CONFIG_HOME": home + "/.config",
               "XDG_CACHE_HOME": home + "/.cache", "XDG_DATA_HOME": home + "/.local/share",
               "XDG_STATE_HOME": home + "/.local/state", "XDG_RUNTIME_DIR": home,
               "QT_QPA_PLATFORM": "offscreen", "QT_FORCE_STDERR_LOGGING": "1"}
        run = subprocess.run(["prlimit", "--core=0", "--", QML, "-I", tree, os.path.join(tree, "barshown.qml")],
                             cwd=tree, env=env, capture_output=True, text=True, timeout=60)
        lines = [l for l in (run.stdout + run.stderr).splitlines() if "BAR_SHOWN " in l]
        self.assertEqual(len(lines), 1, (run.stdout + run.stderr)[-800:])
        return json.loads(lines[0].split("BAR_SHOWN ", 1)[1])

    def test_the_bar_draws_tooltips_and_names_the_shown_name(self):
        names = self.fixture()
        seen = self.observe([v["name"] for v in names])
        self.assertEqual(len(seen), len(names))
        sep = " \u00b7 "
        bad = []
        for v, got in zip(names, seen):
            if v["js"] not in got["drawn"]:
                bad.append("%s: the label draws %r" % (v["why"], got["drawn"]))
            if got["tooltip"] != "Playing 101" + sep + v["js"]:
                bad.append("%s: tooltip %r" % (v["why"], got["tooltip"]))
            if got["accessibleName"] != "IPTV, playing channel 101, " + v["js"]:
                bad.append("%s: accessible name %r" % (v["why"], got["accessibleName"]))
            text = json.dumps(got, ensure_ascii=False)
            bad.extend("%s: %r leaked" % (v["why"], frag) for frag in v["mustNotAppear"] if frag in text)
        self.assertEqual([], bad)


if __name__ == "__main__":
    unittest.main()
