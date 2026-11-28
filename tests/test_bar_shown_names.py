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
# The host kit the tree is built from: OMARCHY_PATH, as tests/a11y/make_tree.py
# and fidelity.py read it, so the builder can be run against another
# Omarchy (how F-HARNESS-99 was proven: red on 4.5.0-3 with the old builder,
# green with the new one on 4.5.0-3 and on the 4.0.6 extract).
OMARCHY = os.environ.get("OMARCHY_PATH", "/usr/share/omarchy")
SHELL = OMARCHY + "/shell"

# The fake bar and service are host_bar.qml's (tests/a11y), with the name
# driven from the fixture. Every name is set in turn and read back at once:
# QML re-evaluates a binding on read, so each reading is that name's.
PROBE_HEAD = r"""
import QtQuick
import QtQuick.Window
import "Model.mjs" as Model
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
    // D-REL-16 (rule 10): the bar reports its stamp and reads buildNotice; a
    // service with neither reads as one from before the stamps ("cache"),
    // which no real service on this tree gives. host_bar.qml's fake, the
    // real Model.buildVerdict over what it is reported.
    property var reportedStamps: ({})
    function reportBuildStamp(file, stamp) { fakeService.reportedStamps = Model.withReportedStamp(fakeService.reportedStamps, file, stamp) }
    readonly property string buildNotice: Model.buildVerdict({ reported: fakeService.reportedStamps,
                                                               loadedDisk: Model.PLUGIN_VERSION, onDisk: Model.PLUGIN_VERSION }).notice
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
"""

PROBE = PROBE_HEAD + r"""
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
        // D-REL-16: what the widget reported when the host's bar let it
        // resolve this service, then its words for another build's guide
        // beside it (a cache notice) and for no service at all (D-A11Y-14).
        var reported = JSON.parse(JSON.stringify(fakeService.reportedStamps))
        fakeService.nowPlaying = null
        fakeService.playing = false
        fakeService.reportBuildStamp("Guide.qml", "99.0.0")
        var cache = { notice: item.buildNotice, tooltip: item.tooltip, accessibleName: item.Accessible.name }
        item.service = null
        var none = { notice: item.buildNotice, tooltip: item.tooltip, accessibleName: item.Accessible.name }
        console.log("BAR_SHOWN " + JSON.stringify({ names: out, reported: reported, stamp: item.buildStamp, cache: cache, none: none }))
        Qt.exit(0)
      })
    }
  }
  Timer { running: true; interval: 20000; onTriggered: { console.log("BAR_SHOWN_TIMEBOX"); Qt.exit(4) } }
}
"""

# D-A11Y-15. The same fakes, with a host that hands NO service at first: the
# widget is given its bar, asks, finds none and starts its resolve timer.
# `late` hands the service only after the timer's first ask came back empty;
# `tick` has it there for that first ask. Every tooltip the widget ever held
# and every accessible name, is recorded as it changes, so "never said
# missing" is a statement about all of them and not about the instants the
# probe read.
START_TAIL = r"""
  property bool handOut: false
  property var heard: []
  property var spoken: []
  property var marks: []
  readonly property string nameNow: host.widget ? host.widget.Accessible.name : ""
  onNameNowChanged: if (host.widget) host.spoken.push(host.nameNow)
  property var widget: null
  function mark(at) {
    var item = host.widget
    host.marks.push({ at: at, tooltip: item.tooltip, accessibleName: item.Accessible.name, misses: item.resolveMisses, seen: item.serviceSeen })
  }
  Connections {
    target: host.widget
    function onTooltipChanged() { host.heard.push(host.widget.tooltip) }
  }
  Loader {
    anchors.fill: parent
    source: "BarWidget.qml"
    onStatusChanged: if (status === Loader.Error) { console.log("BAR_SHOWN_ERROR"); Qt.exit(3) }
    onLoaded: {
      host.widget = item
      item.bar = fakeBar
      host.heard.push(item.tooltip)
      host.mark("handed")
      if ("%(mode)s" === "tick") early.start(); else afterMiss.start()
    }
  }
  // tick: the service is there before the first ask (at resolveMs, 500).
  Timer { id: early; interval: 200; onTriggered: { host.mark("before the first ask"); host.handOut = true; settled.start() } }
  // late: one ask has come back empty; the next one finds it.
  Timer { id: afterMiss; interval: 750; onTriggered: { host.mark("after one miss"); host.handOut = true; settled.start() } }
  Timer {
    id: settled
    interval: 700
    onTriggered: {
      host.mark("resolved")
      host.widget.service = null
      host.mark("gone")
      console.log("BAR_SHOWN " + JSON.stringify({ marks: host.marks, heard: host.heard, spoken: host.spoken }))
      Qt.exit(0)
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

    def observe(self, names, probe=None):
        work = tempfile.mkdtemp(prefix="omarchy-iptv-bar-")
        self.addCleanup(shutil.rmtree, work, True)
        tree = os.path.join(work, "tree")
        home = os.path.join(work, "home")
        os.makedirs(home, mode=0o700)
        build = {"PATH": "/usr/bin:/bin", "HOME": home, "A11Y_TREE": tree, "A11Y_REPO": REPO, "LANG": "C.UTF-8",
                 "OMARCHY_PATH": OMARCHY}
        for script in ("make_tree.py", "make_hosts.py"):
            done = subprocess.run([sys.executable, "-I", os.path.join(HERE, "a11y", script)], env=build,
                                  capture_output=True, text=True, timeout=120)
            self.assertEqual(done.returncode, 0, script + ": " + done.stdout[-400:] + done.stderr[-400:])
        with open(os.path.join(tree, "barshown.qml"), "w", encoding="utf-8") as fh:
            fh.write(probe if probe is not None else PROBE % json.dumps(names))
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
        seen = self.observe([v["name"] for v in names])["names"]
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

    def test_the_bar_reports_its_build_stamp_and_speaks_the_notice(self):
        """D-REL-16 (the lead's call A1) and D-A11Y-14, observed on the SHIPPING
        widget: handed a bar, it resolves the service and reports its own stamp
        -- the value build_stamps.py reads off BarWidget.qml -- and, beside a
        guide of another build and with no service at all, its tooltip and
        accessible name carry the words the model composes. Under this host's
        stand-in, not the host's bar: the caged arms observe that."""
        got = self.observe([])
        stamps = json.loads(subprocess.run([sys.executable, "-I", os.path.join(REPO, "scripts", "build_stamps.py"), "--json"],
                                           capture_output=True, text=True, timeout=60, check=True).stdout)
        sep = " \u00b7 "
        self.assertEqual({"BarWidget.qml": stamps["BarWidget.qml"]}, got["reported"])
        self.assertEqual(stamps["BarWidget.qml"], got["stamp"])
        self.assertEqual({"notice": "cache",
                          "tooltip": "IPTV" + sep + "click to open the guide\nLoaded mid-update" + sep
                                     + "remove ~/.cache/quickshell/qmlcache, then restart the shell",
                          "accessibleName": "IPTV, idle, loaded mid-update, remove the QML cache and restart the shell"},
                         got["cache"])
        self.assertEqual({"notice": "",
                          "tooltip": "IPTV" + sep + "service not loaded, run omarchy restart shell\nIf that does not help, "
                                     "remove ~/.cache/quickshell/qmlcache and restart again",
                          "accessibleName": "IPTV, service not loaded"},
                         got["none"])

    def start_probe(self, mode):
        hand = "function serviceFor(id) { return fakeService }"
        self.assertEqual(1, PROBE_HEAD.count(hand))
        head = (PROBE_HEAD % "[]").replace(hand, "function serviceFor(id) { return host.handOut ? fakeService : null }")
        return self.observe([], head + START_TAIL % {"mode": mode})

    def test_a_service_the_bar_waits_for_is_starting_until_the_first_miss(self):
        """D-A11Y-15, observed on the SHIPPING widget: handed a bar whose host
        has no service yet, it says it is starting; once its timer has asked
        and found none it says the service is not loaded; when the service
        comes it says what the service says; and a service that then goes
        away is missing at once, never starting again."""
        got = self.start_probe("late")
        sep = " \u00b7 "
        gone = {"tooltip": "IPTV" + sep + "service not loaded, run omarchy restart shell\nIf that does not help, "
                           "remove ~/.cache/quickshell/qmlcache and restart again",
                "accessibleName": "IPTV, service not loaded"}
        self.assertEqual([
            dict(at="handed", tooltip="IPTV" + sep + "starting\u2026", accessibleName="IPTV, starting", misses=0, seen=False),
            dict(gone, at="after one miss", misses=1, seen=False),
            dict(at="resolved", tooltip="IPTV" + sep + "click to open the guide", accessibleName="IPTV, idle", misses=1, seen=True),
            dict(gone, at="gone", misses=1, seen=True),
        ], got["marks"])
        self.assertEqual(["IPTV, starting", "IPTV, service not loaded", "IPTV, idle", "IPTV, service not loaded"], got["spoken"])

    def test_a_service_found_at_the_first_ask_is_never_said_to_be_missing(self):
        """D-A11Y-15: the miss is counted AFTER the ask, so a service the
        timer's first ask finds takes the bar from starting to its own words
        with no "service not loaded" between -- over every tooltip the widget
        held, through its own change signal -- until the service really goes."""
        got = self.start_probe("tick")
        sep = " \u00b7 "
        self.assertEqual([("handed", "IPTV, starting", 0, False), ("before the first ask", "IPTV, starting", 0, False),
                          ("resolved", "IPTV, idle", 0, True), ("gone", "IPTV, service not loaded", 0, True)],
                         [(m["at"], m["accessibleName"], m["misses"], m["seen"]) for m in got["marks"]])
        heard = got["heard"]
        self.assertEqual("IPTV" + sep + "starting\u2026", heard[0])
        self.assertIn("IPTV" + sep + "click to open the guide", heard)
        self.assertEqual([], [t for t in heard[:-1] if "service not loaded" in t], heard)
        self.assertIn("service not loaded", heard[-1])
        self.assertEqual(["IPTV, starting", "IPTV, idle", "IPTV, service not loaded"], got["spoken"])


if __name__ == "__main__":
    unittest.main()
