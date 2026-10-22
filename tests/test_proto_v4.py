"""D-SG-3 and D-PERF-3 in Qt's own JavaScript engine.

The shell runs the model in Qt 6's V4, and the node suite runs it in V8.
CLAUDE.md rule 10: a test double must never be more forgiving than the real
thing, and node was: V4 (Qt 6.11.2) has no String.prototype.trimEnd or
trimStart, so a model that called them passed every node check and threw on
every guide open. So both halves of this round are observed here, in the qml
runtime, offscreen, under an address-space limit, and ended by the pid this
file recorded if it does not end by itself:

  * ProtoPathsV4Test runs tests/proto-paths.mjs -- every browse and apply path
    the model has, over groups, names, tvg-ids, favourites, hidden groups,
    saved searches and source labels spelled like members of Object.prototype
    -- and holds it to tests/fixtures/proto-paths.json, the expectation the
    node suite holds the same probe to (R30f).
  * WhitespaceV4Test runs the replacements of the quadratic whitespace and
    authority patterns (R30g) against the patterns they replaced, in V4, on
    ordinary strings: the same answer, character for character, and the ONE
    measured difference of the native trim (U+0085) stated rather than hidden.

PROTO_V4_MODEL names another tree's Model.mjs (a red run against the code
before the change); by default this tree's.
"""
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QML_BIN = "/usr/lib/qt6/bin/qml"
DEADLINE_S = 60


def model_path():
    return os.path.abspath(os.environ.get("PROTO_V4_MODEL") or os.path.join(ROOT, "Model.mjs"))


def run_qml(test, body):
    """Run a QML probe whose Component.onCompleted prints `RESULT <json>`;
    return the parsed JSON. The probe runs with HOME and every XDG directory
    in a private scratch directory (Qt writes a cache under HOME), offscreen,
    under `prlimit --as` where util-linux has it, and is ended by ITS pid --
    recorded here from Popen, never looked up by name -- if it has not exited
    by the deadline."""
    root = tempfile.mkdtemp(prefix="iptv-v4-")
    test.addCleanup(shutil.rmtree, root, True)
    os.chmod(root, 0o700)
    probe = os.path.join(root, "probe.qml")
    with open(probe, "w", encoding="ascii") as handle:
        handle.write("import QtQuick\n")
        handle.write('import "file://%s" as Model\n' % model_path())
        handle.write('import "file://%s" as Probe\n' % os.path.join(ROOT, "tests", "proto-paths.mjs"))
        # A throw is a RESULT too, so a probe that cannot run (a red run
        # against a tree without the names it calls) ends at once rather
        # than at the deadline.
        handle.write("QtObject {\n  Component.onCompleted: {\n    try {\n")
        handle.write(body)
        handle.write('\n    } catch (e) { console.log("RESULT " + JSON.stringify({ probeError: String(e) })) }')
        handle.write("\n    Qt.exit(0)\n  }\n}\n")
    home = os.path.join(root, "home")
    env = {"PATH": "/usr/bin:/bin", "HOME": home, "XDG_CACHE_HOME": home + "/.cache",
           "XDG_CONFIG_HOME": home + "/.config", "XDG_DATA_HOME": home + "/.local/share",
           "XDG_RUNTIME_DIR": root, "LANG": "C.UTF-8", "QT_FORCE_STDERR_LOGGING": "1",
           "QT_QPA_PLATFORM": "offscreen"}
    cap = ["prlimit", "--as=2500000000", "--"] if shutil.which("prlimit") else []
    out_path = os.path.join(root, "out.txt")
    with open(out_path, "wb") as out:
        proc = subprocess.Popen(cap + [QML_BIN, probe], env=env, stdout=out, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, cwd=root)
        pid = proc.pid
        deadline = time.monotonic() + DEADLINE_S
        while proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if proc.poll() is None:
            # Ours, by the pid Popen gave us; prlimit execs the qml runtime in
            # place, so this pid IS the probe.
            os.kill(pid, signal.SIGKILL)
            proc.wait()
            test.fail("the qml probe did not finish within %d s and was killed (pid %d)" % (DEADLINE_S, pid))
    with open(out_path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    test.assertEqual(proc.returncode, 0, "the qml probe failed:\n" + text[-4000:])
    # split("\n"), not splitlines(): JSON.stringify leaves U+2028, U+2029
    # and U+0085 unescaped, and splitlines() would cut the line at them.
    for line in text.split("\n"):
        at = line.find("RESULT ")
        if at != -1:
            return json.loads(line[at + len("RESULT "):])
    test.fail("the qml probe printed no RESULT line:\n" + text[-4000:])
    return None


@unittest.skipUnless(os.access(QML_BIN, os.X_OK), "Qt's qml runtime is not installed")
class ProtoPathsV4Test(unittest.TestCase):
    """R30f in V4: nothing a provider or a user names can reach Object.prototype,
    and every such name is listed, hidden, found and written like any other."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "tests", "fixtures", "proto-paths.json"), encoding="utf-8") as handle:
            cls.expected = json.load(handle)["expected"]

    def setUp(self):
        self.result = run_qml(self, '    console.log("RESULT " + JSON.stringify(Probe.runProtoPaths(Model)))')

    def test_no_path_throws(self):
        self.assertEqual(self.result["errors"], [])

    def test_object_prototype_is_untouched(self):
        self.assertTrue(self.result["prototypeUnchanged"],
                        json.dumps([self.result["prototypeBefore"], self.result["prototypeAfter"]]))
        self.assertEqual(self.result["prototypeAfter"]["enumerable"], [])

    def test_every_path_answers_as_the_shared_expectation_says(self):
        out = self.result["out"]
        self.assertEqual(sorted(out), sorted(self.expected))
        for field, want in self.expected.items():
            with self.subTest(field):
                self.assertEqual(out[field], want)

    def test_every_group_is_listed(self):
        names = [g[0] for g in self.result["out"]["groups"]]
        self.assertEqual(names, ["News", "__proto__", "constructor", "hasOwnProperty", "toString", "valueOf"])

    def test_nothing_written_carries_a_key_the_plugin_did_not_put_there(self):
        keys, entry = self.result["out"]["written"]
        self.assertNotIn("count", keys)
        self.assertEqual(entry, '{"id":"x","sourceKey":"k"}')


# R30g's replacements against the patterns they replaced. Ordinary strings:
# every whitespace character `\s` knows and U+0085, alone, doubled and around
# a word; the URL shapes validateSourceUrl and the file branch see. Nothing
# here is long (the input rule: a bound is shown by arithmetic and by
# equivalence, never by a long run).
WHITESPACE_BODY = r"""
    var ws = ["\t", "\n", "\u000b", "\f", "\r", " ", "\u0085", "\u00a0", "\u1680", "\u2000", "\u200a",
              "\u2028", "\u2029", "\u202f", "\u205f", "\u3000", "\ufeff", "x", "-", ""]
    var inputs = []
    for (var i = 0; i < ws.length; i++) for (var j = 0; j < ws.length; j++) {
      inputs.push(ws[i] + "a" + ws[j]); inputs.push(ws[i] + ws[j] + "a b" + ws[j] + ws[i]); inputs.push(ws[i] + ws[j])
    }
    var bad = { trimEnd: [], trim: [], trimWithoutNel: [], edge: [], cleanName: [] }
    for (var k = 0; k < inputs.length; k++) {
      var s = inputs[k]
      if (Model.trimEndSpace(s) !== s.replace(/\s+$/, "")) bad.trimEnd.push(s)
      if (s.trim() !== s.replace(/^\s+|\s+$/g, "")) bad.trim.push(JSON.stringify(s))
      var t = s.split("\u0085").join("")
      if (t.trim() !== t.replace(/^\s+|\s+$/g, "")) bad.trimWithoutNel.push(JSON.stringify(t))
      if (Model.trimEdgeSpace(s) !== s.replace(/^[ \u00a0]+|[ \u00a0]+$/g, "")) bad.edge.push(s)
      var oldClean = s.replace(/^[\s-]+/, "").replace(/\s+$/, "")
      if (Model.displayName({ name: s }, 1) !== (oldClean !== "" ? oldClean : "Channel 1")) bad.cleanName.push(s)
    }
    var hosts = ["[::1]", "[2001:db8::1]", "[::]", "[1.2.3.4]", "[::ffff:1.2.3.4]", "[fe80::1%25eth0]",
                 "[fe80::1%eth0]", "[]", "[:]", "[x::1]", "[2001:db8::1", "2001:db8::1]", "[::1]x", "[::1]]"]
    var ipv6 = []
    for (var h = 0; h < hosts.length; h++) {
      var was = /^\[[0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*(?:%25[A-Za-z0-9._~-]+)?\]$/.test(hosts[h])
      if (Model.isIpv6Literal(hosts[h]) !== was) ipv6.push(hosts[h])
    }
    var cuts = ["/a/b", "/a?b", "/a#b", "/a?b#c", "?", "#", "/a\u2028?b", "/a?b\u2028c", "/a?b\u2028c#d",
                "/a\u2029b?c", "/a\nb?c", "/a?b\rc", "", "/a/b/c.m3u"]
    var cut = []
    for (var c = 0; c < cuts.length; c++) if (Model.cutQueryAndFragment(cuts[c]) !== cuts[c].replace(/[?#].*$/, "")) cut.push(cuts[c])
    console.log("RESULT " + JSON.stringify({ count: inputs.length, bad: bad, ipv6: ipv6, cut: cut,
      hasTrimEnd: typeof "".trimEnd, hasTrimStart: typeof "".trimStart }))
"""


@unittest.skipUnless(os.access(QML_BIN, os.X_OK), "Qt's qml runtime is not installed")
class WhitespaceV4Test(unittest.TestCase):
    """R30g in V4: the linear replacements answer what the quadratic patterns
    answered, on the engine the shell runs."""

    def setUp(self):
        self.result = run_qml(self, WHITESPACE_BODY)

    def test_the_corpus_is_not_empty(self):
        self.assertGreaterEqual(self.result["count"], 1200)

    def test_trimEndSpace_and_the_names_built_on_it_answer_as_the_pattern_did(self):
        self.assertEqual(self.result["bad"]["trimEnd"], [])
        self.assertEqual(self.result["bad"]["cleanName"], [])

    def test_trimEdgeSpace_answers_as_the_edge_pattern_did(self):
        self.assertEqual(self.result["bad"]["edge"], [])

    def test_the_native_trim_differs_from_the_pattern_only_by_U_0085(self):
        # Measured, and stated: V4's String.prototype.trim also takes U+0085
        # (NEL), which `\s` does not match; node's does not. Every disagreeing
        # input holds a NEL, and with the NELs taken out nothing disagrees.
        # What the helper does with a NEL, measured on ordinary input rather
        # than claimed (the recheck's P3): clean_name and the group cut keep
        # an INTERIOR U+0085 verbatim in channels.json (`Name\x85 One` is
        # written as typed), str.strip() takes one at the EDGES (NEL is
        # whitespace to Python), and clean_field folds any NEL to a space in
        # the guide's fields. So the edges V4's trim() and the old pattern
        # see are the same, and an interior NEL is trimmed by neither.
        self.assertNotEqual(self.result["bad"]["trim"], [])
        for shown in self.result["bad"]["trim"]:
            self.assertIn("\u0085", json.loads(shown))
        self.assertEqual(self.result["bad"]["trimWithoutNel"], [])

    def test_isIpv6Literal_and_cutQueryAndFragment_answer_as_the_patterns_did(self):
        self.assertEqual(self.result["ipv6"], [])
        self.assertEqual(self.result["cut"], [])

    def test_the_engine_still_lacks_trimEnd(self):
        # Why trimEndSpace exists. When a Qt update adds them this goes red,
        # and the helper can become the native call.
        self.assertEqual([self.result["hasTrimEnd"], self.result["hasTrimStart"]], ["undefined", "undefined"])


if __name__ == "__main__":
    unittest.main()
