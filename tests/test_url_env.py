"""D-SINK-8: the fetch verbs take their URL from $OMARCHY_IPTV_URL.

A marketplace maintainer reviewing 0.9.1 (omacom/omarchy-plugin-marketplace
#8998) reported what docs/ARCHITECTURE.md section 6 had accepted as D-SINK-3:
the shell handed the credentialed playlist and EPG URLs to this helper as a
--url argv item, so they sat in /proc/<pid>/cmdline, world-readable, for as
long as a fetch ran. /proc/<pid>/environ is not world-readable, and the helper
fetches with urllib and spawns nothing, so an environment variable closes the
exposure. `playlist` and `epg` now read --url when given, else the variable;
--url stays for a human at their own shell.

These cases run the helper as a subprocess, the way the shell does, because
the sink under test is the process boundary itself: what the child reads from
its environment, and what it writes to its two output streams. The variable
is controlled explicitly on every run, so a value in the test runner's own
shell can neither make a case pass nor make it fail.

Run: python3 -m unittest discover -s tests
"""
import calendar
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

from helper_loader import load_helper          # redirects HOME and $XDG_* first
from test_helper import LocalHttp

helper = load_helper()
ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER = ROOT / "bin" / "omarchy-iptv"
FIXTURES = ROOT / "tests" / "fixtures"
PLAYLIST = str(FIXTURES / "basic.m3u")
EPG_PLAYLIST = str(FIXTURES / "epg-channels.m3u")
XMLTV = str(FIXTURES / "epg-basic.xml")
# 2026-09-12 21:00:00 UTC, the clock tests/test_epg.py runs the fixture at.
NOW = calendar.timegm((2026, 9, 12, 21, 0, 0, 0, 0, 0))
VAR = "OMARCHY_IPTV_URL"
# A synthetic credential and a path that nothing else prints. "playlist" would
# be a useless path to assert on: it is the verb's own name in every status.
SECRET = "SYNTH3TIC"
SECRET_PATH = "/s3cr3t-p4th/get.php"
# Port 1 is never listening: a credentialed URL that fails to connect at once.
UNREACHABLE = "http://user:%s@127.0.0.1:1%s" % (SECRET, SECRET_PATH)


def run(*args, url=None):
    """Run the helper in a child process. `url` is the value of
    $OMARCHY_IPTV_URL for that child; None leaves the variable unset even
    when the shell running the tests has it. -> (exit code, last JSON line
    or None, stdout, stderr)."""
    env = dict(os.environ)
    env.pop(VAR, None)
    if url is not None:
        env[VAR] = url
    completed = subprocess.run([sys.executable, str(HELPER), *args],
                               capture_output=True, text=True, env=env, timeout=30)
    text = completed.stdout.strip()
    payload = json.loads(text.splitlines()[-1]) if text else None
    return completed.returncode, payload, completed.stdout, completed.stderr


def read_json(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


class PlaylistUrlEnvTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = tmp.name

    def test_variable_alone_fetches_that_url(self):
        code, status, _, stderr = run("playlist", "--cache-dir", self.cache, url=PLAYLIST)
        self.assertEqual(code, 0, stderr)
        self.assertTrue(status["ok"])
        self.assertEqual(status["kind"], "playlist")
        self.assertEqual(status["channelCount"], 3)
        channels = read_json(os.path.join(self.cache, helper.CHANNELS_FILE))
        self.assertEqual([c["name"] for c in channels["channels"]],
                         ["BBC One HD", "CNN International, Europe feed", "Plain Channel"])

    def test_variable_alone_fetches_over_http_with_the_credential(self):
        # The HTTP form of the same proof, at the sink: the server records
        # which path was asked for and whether the userinfo arrived as Basic
        # auth, so a fetch of anything but the variable's value is red here.
        server = LocalHttp({SECRET_PATH: LocalHttp.serve_playlist})
        self.addCleanup(server.close)
        code, status, _, stderr = run("playlist", "--cache-dir", self.cache,
                                      url=server.url(SECRET_PATH, userinfo="user:" + SECRET))
        self.assertEqual(code, 0, stderr)
        self.assertTrue(status["ok"])
        self.assertEqual(status["channelCount"], 1)
        self.assertIn(SECRET_PATH, server.seen)
        self.assertTrue(server.seen[SECRET_PATH].get("Authorization", "").startswith("Basic "))

    def test_flag_wins_when_both_are_given(self):
        # Both directions, so precedence is proven rather than one side of it:
        # a good flag over a bad variable succeeds, a bad flag over a good
        # variable fails on the flag's path.
        code, status, _, stderr = run("playlist", "--url", PLAYLIST, "--cache-dir", self.cache,
                                      url="/nonexistent-from-the-variable.m3u")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(status["channelCount"], 3)
        code, status, _, _ = run("playlist", "--url", "/nonexistent-from-the-flag.m3u",
                                 "--cache-dir", self.cache, url=PLAYLIST)
        self.assertEqual(code, 1)
        self.assertFalse(status["ok"])
        self.assertEqual(status["error"]["code"], "not_found")

    def test_neither_given_is_a_bad_url_status_not_a_usage_error(self):
        # The service switches on error.code; an argparse usage exit (status
        # 2, no JSON) is the one shape it cannot act on. An empty variable
        # counts as not given.
        for value in (None, ""):
            with self.subTest(variable=value):
                code, status, stdout, stderr = run("playlist", "--cache-dir", self.cache, url=value)
                self.assertEqual(code, 1, stderr)
                self.assertIsNotNone(status, stdout)
                self.assertFalse(status["ok"])
                self.assertEqual(status["kind"], "playlist")
                self.assertEqual(status["error"]["code"], "bad_url")
                self.assertEqual(status["sourceHost"], "")
                self.assertNotIn("usage:", stderr)
                self.assertNotIn("Traceback", stderr)
                self.assertEqual(len(stdout.strip().splitlines()), 1)

    def test_source_host_is_the_host_only(self):
        server = LocalHttp({SECRET_PATH: LocalHttp.serve_playlist})
        self.addCleanup(server.close)
        code, status, stdout, stderr = run("playlist", "--cache-dir", self.cache,
                                           url=server.url(SECRET_PATH, userinfo="user:" + SECRET))
        self.assertEqual(code, 0, stderr)
        self.assertEqual(status["sourceHost"], "127.0.0.1")
        self.assertEqual(read_json(os.path.join(self.cache, helper.CHANNELS_FILE))["sourceHost"], "127.0.0.1")
        self.assertEqual(read_json(os.path.join(self.cache, helper.PLAYLIST_STATUS_FILE))["sourceHost"], "127.0.0.1")
        for secret in (SECRET, SECRET_PATH):
            self.assertNotIn(secret, stdout + stderr)

    def test_variable_never_reaches_stdout_or_stderr_on_failure(self):
        code, status, stdout, stderr = run("playlist", "--cache-dir", self.cache, url=UNREACHABLE)
        self.assertEqual(code, 1)
        self.assertFalse(status["ok"])
        self.assertEqual(status["sourceHost"], "127.0.0.1")
        self.assertIn("127.0.0.1", stdout)
        self.assertNotIn("Traceback", stderr)
        for secret in (SECRET, SECRET_PATH):
            self.assertNotIn(secret, stdout + stderr)
        written = pathlib.Path(self.cache, helper.PLAYLIST_STATUS_FILE).read_text(encoding="utf-8")
        for secret in (SECRET, SECRET_PATH):
            self.assertNotIn(secret, written)


class EpgUrlEnvTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = tmp.name
        code, _, _, stderr = run("playlist", "--url", EPG_PLAYLIST, "--cache-dir", self.cache)
        self.assertEqual(code, 0, stderr)

    def epg(self, *extra, url=None):
        return run("epg", "--cache-dir", self.cache, "--now", str(NOW), *extra, url=url)

    def test_variable_alone_fetches_that_url(self):
        code, status, _, stderr = self.epg(url=XMLTV)
        self.assertEqual(code, 0, stderr)
        self.assertTrue(status["ok"])
        self.assertEqual(status["kind"], "epg")
        self.assertFalse(status["fromCache"])
        self.assertEqual(status["sourceHost"], "local file")
        self.assertEqual(status["matched"], 8)
        self.assertEqual(status["programmeCount"], 14)

    def test_flag_wins_when_both_are_given(self):
        code, status, _, stderr = self.epg("--url", XMLTV, url="/nonexistent-from-the-variable.xml")
        self.assertEqual(code, 0, stderr)
        self.assertFalse(status["fromCache"])
        self.assertEqual(status["programmeCount"], 14)
        code, status, _, _ = self.epg("--url", "/nonexistent-from-the-flag.xml", url=XMLTV)
        self.assertEqual(code, 1)
        self.assertFalse(status["ok"])
        self.assertEqual(status["error"]["code"], "not_found")

    def test_variable_never_reaches_stdout_or_stderr_on_failure(self):
        code, status, stdout, stderr = self.epg(url=UNREACHABLE)
        self.assertEqual(code, 1)
        self.assertFalse(status["ok"])
        self.assertEqual(status["sourceHost"], "127.0.0.1")
        self.assertIn("127.0.0.1", stdout)
        self.assertNotIn("Traceback", stderr)
        for secret in (SECRET, SECRET_PATH):
            self.assertNotIn(secret, stdout + stderr)
        written = pathlib.Path(self.cache, helper.EPG_STATUS_FILE).read_text(encoding="utf-8")
        for secret in (SECRET, SECRET_PATH):
            self.assertNotIn(secret, written)




class ShieldTest(unittest.TestCase):
    """D-SINK-9: a fetch verb makes itself non-dumpable before it reads the
    URL from its environment, so /proc/<pid>/environ is refused to everyone
    but root and a crash writes no core. Observed on the real /proc from a
    same-uid reader, not reasoned about: the first draft of the D-SINK-8
    docs said "only your own account can read" the environment, and a
    dumpable process's environ is readable by every program that account
    runs -- measured, both ways, 2026-10-01."""

    def test_the_shield_makes_the_calling_process_non_dumpable(self):
        code = (
            "import sys, ctypes; sys.path.insert(0, %r)\n"
            "from helper_loader import load_helper\n"
            "h = load_helper()\n"
            "libc = ctypes.CDLL(None)\n"
            "print(libc.prctl(3, 0, 0, 0, 0), int(h.SHIELDED), libc.prctl(3, 0, 0, 0, 0))\n"   # PR_GET_DUMPABLE
        ) % os.path.dirname(os.path.abspath(__file__))
        # The shield runs at module level, so LOADING the helper is what makes
        # the process non-dumpable: before load 1 (read in the subprocess
        # before the import), after load 0, and SHIELDED records success.
        code = code.replace("h = load_helper()\n", "before = ctypes.CDLL(None).prctl(3, 0, 0, 0, 0)\nh = load_helper()\n")
        code = code.replace("print(libc.prctl(3, 0, 0, 0, 0), int(h.SHIELDED), libc.prctl(3, 0, 0, 0, 0))",
                            "print(before, int(h.SHIELDED), libc.prctl(3, 0, 0, 0, 0))")
        out = subprocess.run([sys.executable, "-c", code], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr.decode("utf-8", "replace"))
        self.assertEqual(out.stdout.decode().split(), ["1", "1", "0"])

    def test_a_fetch_verb_refuses_its_environment_to_a_same_uid_reader(self):
        """The verb, not the function: run `playlist` against a server that
        holds the request open, read the live process's /proc from this
        same-uid test, and expect EACCES on environ while cmdline stays
        readable and carries no URL. Then the fetch must still succeed,
        which is the proof the URL arrived by the only route left."""
        import http.server, threading
        served = threading.Event()
        release = threading.Event()
        body = b"#EXTM3U\n#EXTINF:-1 tvg-id=\"a\" group-title=\"G\",Alpha\nhttp://127.0.0.1:1/a\n"

        class Hold(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                served.set()
                release.wait(10)
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Hold)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)   # cleanups run last-first: close after shutdown
        self.addCleanup(server.shutdown)
        cache = tempfile.mkdtemp(prefix="omarchy-iptv-shield-")
        self.addCleanup(shutil.rmtree, cache, True)
        needle = "SYNTH3TIC%d" % os.getpid()
        env = dict(os.environ)
        env["OMARCHY_IPTV_URL"] = "http://user:%s@127.0.0.1:%d/p.m3u" % (needle, port)
        proc = subprocess.Popen([sys.executable, HELPER, "playlist", "--cache-dir", cache],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertTrue(served.wait(10), "the helper never asked the server")
            # Alive, mid-fetch, and we are the same uid with no capabilities.
            with self.assertRaises(PermissionError):
                open("/proc/%d/environ" % proc.pid, "rb").read()
            with open("/proc/%d/cmdline" % proc.pid, "rb") as fh:
                cmdline = fh.read()
            self.assertNotIn(needle.encode(), cmdline)
            self.assertNotIn(b"--url", cmdline)
        finally:
            release.set()
            out, err = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 0, err.decode("utf-8", "replace"))
        status = json.loads(out.decode().strip().splitlines()[-1])
        self.assertTrue(status.get("ok"), status)
        self.assertEqual(status.get("channelCount"), 1)
        self.assertNotIn(needle.encode(), out + err)

if __name__ == "__main__":
    unittest.main()
