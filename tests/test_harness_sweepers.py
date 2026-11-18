"""F-HARNESS-87: the two harness sweepers see a helper the way the service
starts it.

Since D-SINK-50 the service runs the helper as `python3 -I <helper> <verb>`.
argv-scenario's sweeper and fixtures/rewind-sweep.py read argv[1] as the
helper's path, so they saw no helper: argv-scenario's positive controls went
red and its leak check passed on nothing, and rewind-scenario counted no
`player seek` run. Both now read the script past the interpreter's flags
(fixtures/helper_argv.py), the reader key-scenario.sh carries as
HELPER_ARGV_PY.

These tests RUN the two sweepers, as the scenarios do, against stand-ins of
the helper: a script that only sleeps, started with the service's own argv
shape. Every stand-in is this test's own child and is ended through its
Popen handle. Neither scenario runs here (both hold a display).
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "scripts" / "dev-harness" / "fixtures"
NEEDLE = "s3cr3t-needle-87"


class SweeperCase(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix="omarchy-iptv-sweep-")
        self.addCleanup(shutil.rmtree, self.work, True)
        self.helper = os.path.join(self.work, "bin", "omarchy-iptv")
        self.other = os.path.join(self.work, "bin", "something-else")
        os.makedirs(os.path.dirname(self.helper))
        for path in (self.helper, self.other):
            with open(path, "w") as fh:
                fh.write("import time\ntime.sleep(20)\n")

    def stand_in(self, *argv, env=None):
        """One stand-in process with exactly this argv after the interpreter."""
        base = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
        base.update(env or {})
        proc = subprocess.Popen([sys.executable, *argv], env=base, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(proc.wait, 5)
        self.addCleanup(proc.kill)
        return proc

    def sweeper(self, name, *args, env=None):
        base = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        base.update(env or {})
        done = subprocess.run([sys.executable, str(FIXTURES / name), *args], env=base, capture_output=True, text=True, timeout=30)
        self.assertEqual((done.returncode, done.stderr), (0, ""))


class RewindSweepTest(SweeperCase):
    def test_a_seek_run_started_as_the_service_starts_it_is_counted_and_nothing_else_is(self):
        seek = ("player", "seek", "--socket", "/x/mpv.sock", "--by", "-10")
        counted = [self.stand_in("-I", self.helper, *seek),          # the service's shape (D-SINK-50)
                   self.stand_in(self.helper, *seek),                # a tree from before it
                   self.stand_in("-I", "-B", "-X", "utf8", self.helper, *seek)]
        self.stand_in("-I", self.helper, "player", "pause", "--socket", "/x/mpv.sock")   # the helper, no seek
        self.stand_in("-I", self.other, *seek)                                               # a seek, not the helper
        self.stand_in("-c", "import time; time.sleep(20)", self.helper, "seek")              # names no script
        out = os.path.join(self.work, "sweep.json")
        self.sweeper("rewind-sweep.py", "0.5", self.helper, out)
        with open(out) as fh:
            got = json.load(fh)
        self.assertEqual(sorted(got["pids"]), sorted(proc.pid for proc in counted))
        self.assertEqual(got["runs"], 3)
        self.assertEqual(got["verbs"], {"player seek --socket": 3})


class ArgvSweepTest(SweeperCase):
    def records(self):
        out = os.path.join(self.work, "sweep.jsonl")
        self.sweeper("argv-sweep.py", "0.5", out, env={"ARGV_NEEDLE": NEEDLE, "ARGV_HELPER": os.path.realpath(self.helper)})
        with open(out) as fh:
            return {row["pid"]: row for row in (json.loads(line) for line in fh if line.strip())}

    def test_a_helper_started_as_the_service_starts_it_is_seen_with_its_verb_and_where_the_needle_is(self):
        url = "http://user:%s@example.test/list.m3u" % NEEDLE
        in_env = self.stand_in("-I", self.helper, "playlist", "--cache-dir", "/x", env={"OMARCHY_IPTV_URL": url})
        on_argv = self.stand_in("-I", self.helper, "epg", "--url", url)
        clean = self.stand_in(self.helper, "status")
        self.stand_in("-I", self.other, "playlist", "--url", url)        # not the helper: never recorded
        self.stand_in("-I", self.helper)                                 # the helper with no verb: nothing to key on
        got = self.records()
        self.assertEqual(sorted(got), sorted([in_env.pid, on_argv.pid, clean.pid]))
        row = got[in_env.pid]
        self.assertEqual((row["verb"], row["cmdline_has_needle"], row["environ_has_needle"], row["env_var_present"],
                          row["environ_carriers"], row["environ_refused"]),
                         ("playlist", False, True, True, ["OMARCHY_IPTV_URL"], False))
        row = got[on_argv.pid]
        self.assertEqual((row["verb"], row["cmdline_has_needle"], row["environ_has_needle"]), ("epg", True, False))
        row = got[clean.pid]
        self.assertEqual((row["verb"], row["cmdline_has_needle"], row["environ_has_needle"], row["env_var_present"]),
                         ("status", False, False, False))
        self.assertTrue(all(row["samples"] >= 2 for row in got.values()), got)


class ReaderParityTest(unittest.TestCase):
    """key-scenario.sh carries the reader as text (HELPER_ARGV_PY) for its
    `python3 -c` scanners; fixtures/helper_argv.py is the sweepers' copy.
    Two copies joined by nothing drift, so both are run over one table."""

    VECTORS = [
        ["python3", "-I", "/p/bin/omarchy-iptv", "playlist", "--cache-dir", "/c"],
        ["python3", "/p/bin/omarchy-iptv", "status"],
        ["/usr/bin/python3", "-I", "-B", "/p/bin/omarchy-iptv"],
        ["python3", "-X", "utf8", "-W", "ignore", "-I", "/p/h", "player", "seek"],
        ["python3", "-c", "print(1)", "/p/h", "seek"],
        ["python3", "-m", "http.server", "/p/h"],
        ["python3", "-I"],
        ["python3"],
        ["python3", "-", "x"],
        ["python3", "-X"],
        [],
    ]

    def test_the_two_copies_answer_alike_and_as_stated(self):
        text = (ROOT / "scripts" / "dev-harness" / "key-scenario.sh").read_text(encoding="utf-8")
        found = re.search(r"^HELPER_ARGV_PY='\n(.*?)^'\n", text, re.S | re.M)
        self.assertIsNotNone(found, "key-scenario.sh no longer carries HELPER_ARGV_PY as a quoted block")
        embedded = {}
        exec(found.group(1), embedded)
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(FIXTURES))
        try:
            import helper_argv
        finally:
            sys.path.remove(str(FIXTURES))
        for argv in self.VECTORS:
            with self.subTest(argv=argv):
                self.assertEqual(helper_argv.helper_argv(list(argv)), embedded["helper_argv"](list(argv)))
        self.assertEqual(helper_argv.helper_argv(self.VECTORS[0]), ("/p/bin/omarchy-iptv", ["playlist", "--cache-dir", "/c"]))
        self.assertEqual(helper_argv.helper_argv(self.VECTORS[3]), ("/p/h", ["player", "seek"]))
        self.assertEqual([helper_argv.helper_argv(v) for v in self.VECTORS[4:8]], [None, None, None, None])
        self.assertTrue(helper_argv.read_argv(os.getpid())[0].endswith("python3") or "python" in helper_argv.read_argv(os.getpid())[0])
        self.assertIsNone(helper_argv.read_argv("0"))


if __name__ == "__main__":
    unittest.main()
