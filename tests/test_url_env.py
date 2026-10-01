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


if __name__ == "__main__":
    unittest.main()
