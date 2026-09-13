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


class StubCommandTest(unittest.TestCase):
    def test_stubs_return_not_implemented_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            for args in (["epg", "--url", "http://h.test/e.xml", "--cache-dir", tmp],
                         ["play", "--id", "t:x", "--cache-dir", tmp],
                         ["stop"], ["status"], ["state", "dump", "--state-dir", tmp]):
                code, payload, _ = run(*args)
                self.assertEqual(code, 3, args)
                self.assertEqual(payload["ok"], False)
                self.assertEqual(payload["error"]["code"], "not_implemented")
                self.assertEqual(payload["error"]["message"], "not implemented")

    def test_usage_error(self):
        code, payload, _ = run("playlist")
        self.assertEqual(code, 2)
        self.assertIsNone(payload)

    def test_help(self):
        completed = subprocess.run([sys.executable, str(HELPER), "--help"], capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0)
        self.assertIn("playlist", completed.stdout)


if __name__ == "__main__":
    unittest.main()
