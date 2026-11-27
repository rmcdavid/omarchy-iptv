"""D-HOST-15's caged readout (scripts/dev-harness/spikes/barconfig-window/
analyze.py), driven over logs in the shapes the rig block, the host's
console.trace() and service-log.patch write them.

The verdicts the lane records rest on three decisions of this reader, so
each is held here: which API object the service was handed (the --probe
line above shell.qml 958), whether the window was open (the service's
onShellChanged read its layout's sections as sequences) and when it closed
(the first barConfig assignment to that object whose sections are Arrays),
and whether the state load fell inside it. The lines below are copies of
lines the caged runs printed (lane-dh15m, 2026-11-27), cut to the fields the
reader reads, with the Quickshell log prefix and its colour codes as
written.
"""
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYZE = os.path.join(HERE, "..", "scripts", "dev-harness", "spikes", "barconfig-window", "analyze.py")


def load():
    spec = importlib.util.spec_from_file_location("bcw_analyze", ANALYZE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = "\x1b[34m DEBUG\x1b[97m qml\x1b[0m: "
SEQ = "left=seq(0) centerBegin=seq(0) center=seq(0) centerEnd=seq(0) right=seq(1) tray=undef(-)"
ARR = "left=array(0) centerBegin=array(0) center=array(0) centerEnd=array(0) right=array(1) tray=undef(-)"
ARRC = ARR.replace(" ", ",")
API = "PluginShellApi_QMLTYPE_29(0x7fffd013a7a0)"
SVC = "Service_QMLTYPE_149(0x7ffff02a58e0)"


def created(t):
    return P + "IPTV-LOG %d created %s" % (t, SVC)


def before(t, answer):
    return P + "RIG-W %d 5 beforeApi ensureService %s held=none heldShape=none bar=yes barApi=no panel=no" % (t, answer)


def api(t):
    return [P + "RIG-W %d 6 api %s service=no shape=%s" % (t, API, SEQ.replace(" ", ",")),
            P + "on_PluginShellApisChanged (qs:@/qs/shell.qml:1816)",
            "createScopedPluginShell (qs:@/qs/shell.qml:648)",
            "pluginShellFor (qs:@/qs/shell.qml:728)",
            "finalize (qs:@/qs/shell.qml:919)",
            "ensureService (qs:@/qs/shell.qml:939)",
            " (qs:@/qs/services/PluginRegistry.qml:680)"]


def shell_changed(t, sections, entry):
    return (P + "IPTV-LOG %d shellChanged shell=%s %s entry=%s entryMaxRecents=10 boundMaxRecents=10 "
            "boundPlaylistSet=false || cfg=object/false/[object V4ReferenceObject]" % (t, API, sections, entry))


def published(t):
    return P + "RIG-W %d 7 service %s shell=%s sameAsCache=true shape=x" % (t, SVC, API)


def assigned(t, shape=ARRC):
    return [P + "RIG-W %d 10 widgetRegistryChanged revision=1 ours=no" % t,
            P + "RIG-W %d 11 apiBarConfig %s shape=%s service=yes" % (t, API, shape)]


def settings_changed(t, sections, entry, mr):
    return (P + "IPTV-LOG %d settingsChanged %s entry=%s entryMaxRecents=%d boundMaxRecents=10 boundPlaylistSet=false"
            % (t, sections, entry, mr))


def state_load(t, sections, kept, trim, entry):
    return (P + "IPTV-LOG %d stateLoad onDisk=15 kept=%d diskMarker=false diskSources=0 trimMax=%d %s entry=%s "
            "entryMaxRecents=%d boundMaxRecents=%d boundPlaylistSet=true || cfg=object" % (
                t, kept, trim, sections, entry, trim, trim))


def plan(t, act, adopt):
    return P + "IPTV-LOG %d adoptActive act=%s adoptUrl=%s migrating=true playlistSet=%s refused=" % (
        t, act, adopt, adopt)


def saved(t):
    return P + "IPTV-LOG %d saved last recents=15 marker=true sources=1" % t


def verdicts(mod, lines):
    recs = mod.services(mod.parse(lines))
    return [mod.verdict(r) for r in recs], recs


class BarconfigWindowReadout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load()

    def test_a_window_closed_before_the_load(self):
        lines = ([created(100), settings_changed(100, "left=undef(-) right=undef(-)", "[]", 10),
                  before(140, "fresh")] + api(141) + [shell_changed(141, SEQ, "[]"),
                  settings_changed(142, SEQ, "[]", 10), published(143)]
                 + assigned(148) + [settings_changed(148, ARR, "[id,maxRecents,playlistUrl,refreshMinutes]", 25),
                                    state_load(151, ARR, 15, 25, "[id,maxRecents,playlistUrl,refreshMinutes]"),
                                    plan(152, "adopt", "true"), saved(1282)])
        (v,), (rec,) = verdicts(self.mod, lines)
        # The service's own reading at the first syncPluginApis after it
        # exists: the settings change that follows the close, never the
        # ones before it (at its creation, and inside the window).
        self.assertEqual(rec["firstSync"], {"t": 148, "sections": "array",
                                            "entry": "[id,maxRecents,playlistUrl,refreshMinutes]",
                                            "entryMaxRecents": "25"})
        self.assertEqual(v["handed"], "fresh")
        self.assertEqual(v["window"], "open")
        self.assertTrue(v["defaults"])
        self.assertEqual(v["openMs"], 7)
        self.assertEqual(v["closedBy"], "widgetRegistryChanged")
        self.assertEqual(v["load"], "after")
        self.assertEqual(v["trim"], "15->15")
        self.assertEqual(v["markerSave"], "after-close")
        self.assertEqual(rec["shell"]["creator"][:5],
                         ["on_PluginShellApisChanged", "createScopedPluginShell", "pluginShellFor", "finalize",
                          "ensureService"])

    def test_a_load_inside_the_window_and_the_marker_first(self):
        lines = ([created(100), before(140, "fresh")] + api(141) + [shell_changed(141, SEQ, "[]"), published(143),
                 state_load(240, SEQ, 10, 10, "[]"), plan(241, "migrate", "false"), saved(1500)]
                 + assigned(6600))
        (v,), _ = verdicts(self.mod, lines)
        self.assertEqual(v["window"], "open")
        self.assertEqual(v["load"], "inside")
        self.assertEqual(v["trim"], "15->10")
        self.assertEqual(v["firstPlan"], "migrate(adoptUrl=false,playlist=false)")
        self.assertEqual(v["markerSave"], "before-close")
        self.assertEqual(v["openMs"], 6459)

    def test_a_cached_object_read_as_arrays_is_no_window(self):
        lines = [created(100), before(140, "cached"), shell_changed(141, ARR, "[id,maxRecents,playlistUrl,refreshMinutes]"),
                 published(143), state_load(151, ARR, 15, 25, "[id,maxRecents,playlistUrl,refreshMinutes]")]
        (v,), _ = verdicts(self.mod, lines)
        self.assertEqual(v["handed"], "cached")
        self.assertEqual(v["window"], "closed")
        self.assertFalse(v["defaults"])
        self.assertEqual(v["load"], "after")

    def test_a_fresh_object_read_as_arrays_is_closed_at_once(self):
        # A fresh object whose sections already read as Arrays at
        # onShellChanged opens no window: it is closed there, so a marker
        # saved later is after the close (the second code recheck's
        # surviving mutant closed only a shell that read no section).
        lines = [created(100), before(140, "fresh"), shell_changed(141, ARR, "[id,maxRecents,playlistUrl,refreshMinutes]"),
                 published(143), state_load(151, ARR, 15, 25, "[id,maxRecents,playlistUrl,refreshMinutes]"),
                 plan(152, "adopt", "true"), saved(1282)]
        (v,), (rec,) = verdicts(self.mod, lines)
        self.assertEqual(v["handed"], "fresh")
        self.assertEqual(v["window"], "closed")
        self.assertEqual((rec["closed"], rec["closedBy"]), (141, "fresh-array"))
        self.assertEqual(v["markerSave"], "after-close")
        self.assertEqual(v["load"], "after")

    def test_an_assignment_still_read_as_sequences_does_not_close_it(self):
        lines = ([created(100), before(140, "fresh")] + api(141) + [shell_changed(141, SEQ, "[]"), published(143)]
                 + assigned(148, SEQ.replace(" ", ",")) + [state_load(151, SEQ, 10, 10, "[]")] + assigned(300))
        (v,), _ = verdicts(self.mod, lines)
        self.assertEqual(v["openMs"], 159)
        self.assertEqual(v["load"], "inside")

    def test_two_services_are_read_apart(self):
        first = ([created(100), before(140, "fresh")] + api(141) + [shell_changed(141, SEQ, "[]"), published(143)]
                 + assigned(148))
        second = ([created(5000), before(5040, "fresh")] + api(5041) + [shell_changed(5041, SEQ, "[]"), published(5043),
                  state_load(5060, SEQ, 10, 10, "[]")] + assigned(5070))
        vs, recs = verdicts(self.mod, first + second)
        self.assertEqual(len(recs), 2)
        self.assertEqual([v["load"] for v in vs], ["none", "inside"])
        self.assertEqual(vs[1]["openMs"], 29)

    def test_the_playlist_is_read_off_the_fixture(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as h:
            with open(os.path.join(h, "shell.json.start"), "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "bar": {"layout": {"left": [], "right": [
                    {"id": "io.github.rmcdavid.iptv", "playlistUrl": "/elsewhere/play.m3u"}]}}}, fh)
            self.assertEqual(self.mod.fixture_playlist(h), "/elsewhere/play.m3u")
            os.unlink(os.path.join(h, "shell.json.start"))
            self.assertEqual(self.mod.fixture_playlist(h), os.path.join(h, "play.m3u"))

    def test_a_start_read_again_elsewhere_still_names_the_playlist(self):
        # main() compares state.json's sources with the playlist the
        # fixture named, wherever the start's files are read from now.
        import contextlib
        import io
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as h:
            with open(os.path.join(h, "qs.log"), "w", encoding="utf-8") as fh:
                fh.write("\n".join([created(100), before(140, "fresh")] + api(141)
                                   + [shell_changed(141, SEQ, "[]"), published(143)] + assigned(148)) + "\n")
            with open(os.path.join(h, "shell.json.start"), "w", encoding="utf-8") as fh:
                json.dump({"version": 1, "bar": {"layout": {"right": [
                    {"id": "io.github.rmcdavid.iptv", "playlistUrl": "/elsewhere/play.m3u"}]}}}, fh)
            with open(os.path.join(h, "state.json.end"), "w", encoding="utf-8") as fh:
                json.dump({"recents": [], "entryMigrated": True, "activeKey": "k1",
                           "sources": [{"key": "k1", "url": "/elsewhere/play.m3u"}]}, fh)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.mod.main(["analyze.py", h, "x.1"])
        self.assertIn("state.json at the end: recents 0, marker True, sources 1 (the playlist), activeKey set",
                      out.getvalue())

    def test_a_load_that_read_no_array_is_never_after(self):
        # A load whose readout names no section, or reads them undefined (no
        # shell yet: the defaults too), is not counted as after the window
        # (the recheck of 616061f: such a load read as "after").
        for readout, kind in (("threw=TypeError", "unknown-none"),
                              ("left=undef(-) centerBegin=undef(-) center=undef(-) centerEnd=undef(-) right=undef(-) "
                               "tray=undef(-)", "unknown-mixed")):
            lines = ([created(100), before(140, "fresh")] + api(141) + [shell_changed(141, SEQ, "[]"), published(143)]
                     + assigned(148) + [state_load(151, readout, 10, 10, "[]")])
            (v,), _ = verdicts(self.mod, lines)
            self.assertEqual(v["load"], kind)

    def test_the_first_load_is_judged(self):
        # A service's FIRST state load is the one the window is judged by,
        # whatever a later one reads (the code recheck's surviving mutant
        # read the last).
        lines = ([created(100), before(140, "fresh")] + api(141) + [shell_changed(141, SEQ, "[]"), published(143),
                 state_load(151, SEQ, 10, 10, "[]")] + assigned(300)
                 + [state_load(900, ARR, 15, 25, "[id,maxRecents,playlistUrl,refreshMinutes]")])
        (v,), (rec,) = verdicts(self.mod, lines)
        self.assertEqual(len(rec["loads"]), 2)
        self.assertEqual(v["load"], "inside")
        self.assertEqual(v["trim"], "15->10")
        self.assertEqual(v["trimMax"], "10")

    def test_another_objects_assignment_does_not_close_it(self):
        # Only an assignment to the API object the service was handed closes
        # its window (the code recheck's other surviving mutant closed it at
        # any object's).
        other = [P + "RIG-W 148 10 widgetRegistryChanged revision=1 ours=no",
                 P + "RIG-W 148 11 apiBarConfig PluginShellApi_QMLTYPE_30(0x7fffce6db7e0) shape=%s service=yes" % ARRC]
        lines = ([created(100), before(140, "fresh")] + api(141) + [shell_changed(141, SEQ, "[]"), published(143)]
                 + other + [state_load(151, SEQ, 10, 10, "[]")] + assigned(300))
        (v,), (rec,) = verdicts(self.mod, lines)
        self.assertEqual(rec["closed"], 300)
        self.assertEqual(v["openMs"], 159)
        self.assertEqual(v["load"], "inside")

    def test_sections(self):
        self.assertEqual(self.mod.sections(SEQ), "seq")
        self.assertEqual(self.mod.sections(ARR), "array")
        self.assertEqual(self.mod.sections("nothing here"), "none")


if __name__ == "__main__":
    unittest.main()
