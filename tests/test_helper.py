"""CLI-level tests for bin/omarchy-iptv (subprocess, temp cache dir).

Network tests talk to throw-away servers on 127.0.0.1 only, never the
network.
"""
import gzip
import http.server
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from helper_loader import load_helper

ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER = ROOT / "bin" / "omarchy-iptv"
FIXTURES = ROOT / "tests" / "fixtures"
helper = load_helper()
SMALL_PLAYLIST = b"#EXTM3U\n#EXTINF:-1 tvg-id=\"local.test\",Local\nhttp://stream.example.test/x.m3u8\n"


class LocalHttp:
    """Loopback HTTP server for hardening tests. `seen[path]` holds the request
    headers of the last request for that path. Routes:
      /playlist   a small valid playlist
      /trickle    a 200 that drips playlist lines forever (S-05)
    Extra routes: {path: callable(handler)}."""

    def __init__(self, routes=None):
        seen = self.seen = {}
        table = self.routes = {"/playlist": self.serve_playlist, "/trickle": self.serve_trickle}
        if routes:
            table.update(routes)

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                seen[self.path] = dict(self.headers.items())
                route = table.get(self.path)
                if route is None:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                route(self)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def url(self, path, userinfo=""):
        return "http://%s127.0.0.1:%d%s" % (userinfo + "@" if userinfo else "", self.port, path)

    @staticmethod
    def serve_playlist(handler):
        handler.send_response(200)
        handler.send_header("Content-Type", "audio/x-mpegurl")
        handler.send_header("Content-Length", str(len(SMALL_PLAYLIST)))
        handler.end_headers()
        handler.wfile.write(SMALL_PLAYLIST)

    @staticmethod
    def serve_trickle(handler):
        handler.send_response(200)
        handler.send_header("Content-Type", "audio/x-mpegurl")
        handler.send_header("Content-Length", str(10 ** 9))
        handler.end_headers()
        line = b"#EXTINF:-1,Drip\nhttp://stream.example.test/drip.m3u8\n"
        try:
            while True:
                handler.wfile.write(line)
                handler.wfile.flush()
                time.sleep(0.05)
        except OSError:
            return   # the client gave up: the deadline fired

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


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


class RedirectTest(unittest.TestCase):
    """S-06: a redirect to another origin drops the Basic credentials derived
    from a user:pw@ source URL; redirects to non-http(s) schemes are refused.
    Two loopback servers on different ports stand in for two hosts."""

    def setUp(self):
        self.other = LocalHttp()
        self.addCleanup(self.other.close)

        def redirect(to):
            def route(handler):
                handler.send_response(302)
                handler.send_header("Location", to)
                handler.send_header("Content-Length", "0")
                handler.end_headers()
            return route

        self.first = LocalHttp({
            "/cross": redirect(self.other.url("/playlist")),
            "/same": redirect("/playlist"),
            "/ftp": redirect("ftp://127.0.0.1:9/secret/list.m3u"),
            "/file": redirect("file:///etc/passwd"),
            "/data": redirect("data:text/plain,%23EXTM3U"),
            "/loop": redirect("/loop"),
        })
        self.addCleanup(self.first.close)

    def fetch(self, path):
        with tempfile.TemporaryDirectory() as tmp:
            return run("playlist", "--url", self.first.url(path, "user:pw"), "--cache-dir", tmp, "--timeout", "5")

    def test_cross_origin_redirect_drops_authorization(self):
        code, status, stderr = self.fetch("/cross")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(status["channelCount"], 1)
        self.assertEqual(self.first.seen["/cross"]["Authorization"], "Basic dXNlcjpwdw==")
        self.assertNotIn("Authorization", self.other.seen["/playlist"])
        self.assertNotIn("Cookie", self.other.seen["/playlist"])
        self.assertEqual(self.other.seen["/playlist"]["User-Agent"], helper.USER_AGENT)

    def test_same_origin_redirect_keeps_authorization(self):
        code, status, stderr = self.fetch("/same")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(status["channelCount"], 1)
        self.assertEqual(self.first.seen["/playlist"]["Authorization"], "Basic dXNlcjpwdw==")

    def test_redirects_to_other_schemes_are_refused(self):
        for path in ("/ftp", "/file", "/data"):
            code, status, stderr = self.fetch(path)
            self.assertEqual(code, 1, path)
            self.assertEqual(status["error"]["code"], "unsafe_redirect", path)
            self.assertEqual(status["sourceHost"], "127.0.0.1")
            for secret in ("user:pw", "passwd", "secret", "list.m3u", "EXTM3U", "127.0.0.1:9"):
                self.assertNotIn(secret, json.dumps(status) + stderr, path)
            if path == "/ftp":
                # ftp passes urllib's own check and is refused by our handler.
                self.assertEqual(status["error"]["message"], "playlist from 127.0.0.1 redirected to an unsupported scheme 'ftp'")
            else:
                # file:/data: are refused by urllib itself (3xx HTTPError).
                self.assertEqual(status["error"]["message"], "playlist redirect from 127.0.0.1 not followed")

    def test_redirect_loop_is_an_error_not_a_hang(self):
        started = time.monotonic()
        code, status, _ = self.fetch("/loop")
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertEqual(code, 1)
        self.assertEqual(status["error"]["code"], "unsafe_redirect")

    def test_request_origin(self):
        self.assertEqual(helper.request_origin("HTTPS://User:pw@Host.Test:8443/x?y"), ("https", "host.test", 8443))
        self.assertEqual(helper.request_origin("http://h.test/x"), ("http", "h.test", None))
        self.assertNotEqual(helper.request_origin("https://h.test/"), helper.request_origin("http://h.test/"))


class HardeningTest(unittest.TestCase):
    """Size caps, unsafe paths, timeouts and status bookkeeping (docs/QA.md test inventory)."""

    def test_sparse_65mb_file_is_too_large_without_reading_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            huge = os.path.join(tmp, "huge.m3u")
            open(huge, "wb").close()
            os.truncate(huge, 65 * 1024 * 1024)
            started = time.monotonic()
            code, status, stderr = run("playlist", "--url", huge, "--cache-dir", tmp)
            self.assertLess(time.monotonic() - started, 2.0)
            self.assertEqual(code, 1)
            self.assertEqual(status["error"]["code"], "too_large")
            self.assertNotIn(tmp, json.dumps(status) + stderr)   # base name only (D-QA-12)
            self.assertIn("huge.m3u", status["error"]["message"])

    def test_unsafe_paths_are_refused_without_echoing_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = os.path.join(tmp, "link.m3u")
            os.symlink("/proc/self/environ", link)
            for source in ("/proc/self/environ", "/dev/zero", "/sys/kernel/vmcoreinfo", link):
                code, status, stderr = run("playlist", "--url", source, "--cache-dir", tmp)
                self.assertEqual(code, 1, source)
                self.assertEqual(status["error"]["code"], "unsafe_path", source)
                self.assertNotIn("/proc/self", json.dumps(status) + stderr)
            code, status, _ = run("playlist", "--url", "/nonexistent/dir/list.m3u", "--cache-dir", tmp)
            self.assertEqual(status["error"]["code"], "not_found")
            self.assertEqual(status["error"]["message"], "playlist file not found: list.m3u")

    def test_gzip_bomb_playlist_is_too_large(self):
        with tempfile.TemporaryDirectory() as tmp:
            bomb = os.path.join(tmp, "bomb.m3u.gz")
            with open(bomb, "wb") as handle:
                handle.write(gzip.compress(b"#EXTM3U\n" + b"\0" * (65 << 20), compresslevel=1))
            self.assertLess(os.path.getsize(bomb), 1 << 20)
            code, status, _ = run("playlist", "--url", bomb, "--cache-dir", tmp)
            self.assertEqual(code, 1)
            self.assertEqual(status["error"]["code"], "too_large")

    def test_timeout_is_honoured_against_a_silent_server(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)   # accepts the TCP handshake, never answers
        self.addCleanup(listener.close)
        port = listener.getsockname()[1]
        with tempfile.TemporaryDirectory() as tmp:
            started = time.monotonic()
            code, status, _ = run("playlist", "--url", "http://127.0.0.1:%d/list.m3u" % port, "--cache-dir", tmp, "--timeout", "0.5")
            self.assertLess(time.monotonic() - started, 5.0)
            self.assertEqual(code, 1)
            self.assertEqual(status["error"]["code"], "network")
            self.assertEqual(status["sourceHost"], "127.0.0.1")
            self.assertTrue((pathlib.Path(tmp) / "playlist-status.json").is_file())

    def test_local_http_download_reads_the_whole_body_in_chunks(self):
        server = LocalHttp()
        self.addCleanup(server.close)
        with tempfile.TemporaryDirectory() as tmp:
            code, status, stderr = run("playlist", "--url", server.url("/playlist"), "--cache-dir", tmp, "--timeout", "5")
            self.assertEqual(code, 0, stderr)
            self.assertEqual(status["channelCount"], 1)
            self.assertEqual(status["sourceHost"], "127.0.0.1")
            self.assertEqual(server.seen["/playlist"]["User-Agent"], helper.USER_AGENT)
            self.assertNotIn("Authorization", server.seen["/playlist"])

    def test_trickling_server_trips_the_wall_clock_deadline(self):
        # S-05: --timeout is per socket operation; a server that keeps sending
        # a byte at a time must still be cut off by the wall-clock budget.
        server = LocalHttp()
        self.addCleanup(server.close)
        with tempfile.TemporaryDirectory() as tmp:
            started = time.monotonic()
            code, status, stderr = run("playlist", "--url", server.url("/trickle"), "--cache-dir", tmp, "--timeout", "5",
                                       env={helper.HTTP_DEADLINE_ENV: "1"})
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 4.0, "deadline did not fire (%.1f s)" % elapsed)
            self.assertEqual(code, 1)
            self.assertEqual(status["error"]["code"], "timeout")
            # D-LIVE-11: the message never states a duration (the guide shows
            # "Timed out", the README states the deadline).
            self.assertEqual(status["error"]["message"], "playlist download from 127.0.0.1 exceeded its deadline")
            self.assertNotRegex(status["error"]["message"], r"\d+ ?s\b")
            self.assertEqual(status["sourceHost"], "127.0.0.1")
            self.assertNotIn("/trickle", json.dumps(status) + stderr)
            self.assertIn("exceeded its deadline", stderr)

    def test_default_deadline_is_sixty_seconds_or_three_times_the_timeout(self):
        original = os.environ.pop(helper.HTTP_DEADLINE_ENV, None)
        try:
            self.assertEqual(helper.http_deadline(20), 60.0)
            self.assertEqual(helper.http_deadline(0.5), 60.0)
            self.assertEqual(helper.http_deadline(30), 90.0)
            os.environ[helper.HTTP_DEADLINE_ENV] = "junk"
            self.assertEqual(helper.http_deadline(20), 60.0)
            os.environ[helper.HTTP_DEADLINE_ENV] = "0.25"
            self.assertEqual(helper.http_deadline(20), 0.25)
        finally:
            os.environ.pop(helper.HTTP_DEADLINE_ENV, None)
            if original is not None:
                os.environ[helper.HTTP_DEADLINE_ENV] = original

    def test_status_file_written_on_failure_with_fetched_at_carried_over(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, first, _ = run("playlist", "--url", str(FIXTURES / "basic.m3u"), "--cache-dir", tmp)
            self.assertEqual(code, 0)
            code, status, _ = run("playlist", "--url", os.path.join(tmp, "missing.m3u"), "--cache-dir", tmp)
            self.assertEqual(code, 1)
            written = json.loads((pathlib.Path(tmp) / "playlist-status.json").read_text(encoding="utf-8"))
            self.assertEqual(written, status)
            self.assertFalse(written["ok"])
            self.assertTrue(written["stale"])
            self.assertEqual(written["fetchedAt"], first["fetchedAt"])
            self.assertEqual(written["sourceHost"], "local file")

if __name__ == "__main__":
    unittest.main()
