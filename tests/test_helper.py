"""CLI-level tests for bin/omarchy-iptv (subprocess, temp cache dir)."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER = ROOT / "bin" / "omarchy-iptv"
FIXTURES = ROOT / "tests" / "fixtures"


def run(*args, env=None):
    merged = dict(os.environ)
    if env:
        merged.update(env)
    completed = subprocess.run([sys.executable, str(HELPER), *args], capture_output=True, text=True, env=merged, timeout=30)
    payload = None
    if completed.stdout.strip():
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    return completed.returncode, payload, completed.stderr


class PlaylistCommandTest(unittest.TestCase):
    def test_local_playlist_writes_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, status, _ = run("playlist", "--url", str(FIXTURES / "basic.m3u"), "--cache-dir", tmp)
            self.assertEqual(code, 0)
            self.assertTrue(status["ok"])
            self.assertEqual(status["kind"], "playlist")
            self.assertEqual(status["channelCount"], 3)
            self.assertEqual(status["groupCount"], 3)
            self.assertFalse(status["stale"])
            channels = json.loads((pathlib.Path(tmp) / "channels.json").read_text(encoding="utf-8"))
            self.assertEqual(channels["version"], 1)
            self.assertEqual(channels["count"], 3)
            self.assertEqual(channels["sourceHost"], "local file")
            self.assertEqual(channels["channels"][0]["id"], "t:bbc1.uk")
            written = json.loads((pathlib.Path(tmp) / "playlist-status.json").read_text(encoding="utf-8"))
            self.assertEqual(written["channelCount"], 3)
            mode = (pathlib.Path(tmp) / "channels.json").stat().st_mode & 0o777
            self.assertEqual(mode, 0o600)

    def test_missing_file_reports_error_and_keeps_stale_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            run("playlist", "--url", str(FIXTURES / "basic.m3u"), "--cache-dir", tmp)
            code, status, stderr = run("playlist", "--url", "/nonexistent/list.m3u", "--cache-dir", tmp)
            self.assertEqual(code, 1)
            self.assertFalse(status["ok"])
            self.assertEqual(status["error"]["code"], "not_found")
            self.assertTrue(status["stale"])
            self.assertIn("not found", stderr)
            self.assertTrue((pathlib.Path(tmp) / "channels.json").exists())

    def test_refuses_unsupported_scheme(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, status, _ = run("playlist", "--url", "ftp://h.test/x.m3u", "--cache-dir", tmp)
            self.assertEqual(code, 1)
            self.assertEqual(status["error"]["code"], "unsupported_scheme")
            self.assertFalse(status["stale"])

    def test_empty_playlist_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = pathlib.Path(tmp) / "empty.m3u"
            empty.write_text("#EXTM3U\n", encoding="utf-8")
            code, status, _ = run("playlist", "--url", str(empty), "--cache-dir", tmp)
            self.assertEqual(code, 1)
            self.assertEqual(status["error"]["code"], "empty_playlist")


class CliContractTest(unittest.TestCase):
    SUBCOMMANDS = ("playlist", "epg", "play", "stop", "status", "state")

    def test_every_subcommand_is_implemented(self):
        # Exit 3 (not implemented) must never appear; failures are structured errors.
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "no.sock")
            cases = (
                (["epg", "--now-only", "--cache-dir", tmp], "no_cache"),
                (["play", "--id", "t:x", "--cache-dir", tmp, "--socket", missing], "no_cache"),
                (["play", "--url", "http://h.test/a.m3u8", "--socket", missing], "not_running"),
                (["stop", "--socket", missing], "not_running"),
                (["status", "--socket", missing], "not_running"),
            )
            for args, expected in cases:
                code, payload, _ = run(*args)
                self.assertEqual(code, 1, args)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["kind"], args[0])
                self.assertEqual(payload["error"]["code"], expected, args)
            code, payload, _ = run("state", "--state-dir", tmp, "show")
            self.assertEqual(code, 0)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["kind"], "state")

    def test_usage_errors_exit_2_without_json(self):
        for args in (["playlist"], ["play"], ["play", "--id", "a", "--url", "b"], ["state"], ["state", "favorite", "add"], ["bogus"]):
            code, payload, _ = run(*args)
            self.assertEqual(code, 2, args)
            self.assertIsNone(payload, args)

    def test_help_lists_every_subcommand(self):
        completed = subprocess.run([sys.executable, str(HELPER), "--help"], capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0)
        for name in self.SUBCOMMANDS:
            self.assertIn(name, completed.stdout)
        self.assertNotIn("TODO", completed.stdout)

    def test_xdg_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "XDG_CACHE_HOME": os.path.join(tmp, "cache"),
                "XDG_STATE_HOME": os.path.join(tmp, "state"),
                "XDG_RUNTIME_DIR": os.path.join(tmp, "run"),
            }
            code, status, _ = run("playlist", "--url", str(FIXTURES / "basic.m3u"), env=env)
            self.assertEqual(code, 0)
            cache = pathlib.Path(tmp) / "cache" / "omarchy-iptv"
            self.assertTrue((cache / "channels.json").is_file())
            self.assertEqual(cache.stat().st_mode & 0o777, 0o700)
            code, payload, _ = run("state", "favorite", "add", "t:bbc1.uk", env=env)
            self.assertEqual(code, 0)
            self.assertTrue((pathlib.Path(tmp) / "state" / "omarchy-iptv" / "state.json").is_file())
            code, payload, _ = run("status", env=env)
            self.assertEqual(code, 1)
            self.assertEqual(payload["error"]["code"], "not_running")
            self.assertFalse(payload["running"])

    def test_exactly_one_json_line_on_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            for args in (["playlist", "--url", str(FIXTURES / "basic.m3u"), "--cache-dir", tmp],
                         ["playlist", "--url", "/nonexistent.m3u", "--cache-dir", tmp],
                         ["status", "--socket", os.path.join(tmp, "none.sock")]):
                completed = subprocess.run([sys.executable, str(HELPER), *args], capture_output=True, text=True, timeout=30)
                self.assertEqual(len(completed.stdout.strip().splitlines()), 1, args)
                json.loads(completed.stdout)

    def test_stderr_and_stdout_never_contain_the_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "https://user:secretpw@h.test/get.php?username=u&password=p&type=m3u_plus"
            completed = subprocess.run([sys.executable, str(HELPER), "playlist", "--url", url, "--cache-dir", tmp, "--timeout", "0.001"],
                                       capture_output=True, text=True, timeout=30)
            self.assertEqual(completed.returncode, 1)
            for secret in ("secretpw", "password=p", "get.php"):
                self.assertNotIn(secret, completed.stdout + completed.stderr)
            self.assertIn("h.test", completed.stdout)

if __name__ == "__main__":
    unittest.main()
