"""CLI-level tests for bin/omarchy-iptv (subprocess, temp cache dir).

Network tests talk to throw-away servers on 127.0.0.1 only, never the
network.
"""
import gzip
import http.server
import json
import os
import re
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
    SUBCOMMANDS = ("playlist", "epg", "play", "stop", "status", "state", "cache", "config")

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
            code, payload, _ = run("cache", "--cache-dir", tmp, "remove", "--key", "not-a-key")
            self.assertEqual(code, 1)
            self.assertEqual(payload["kind"], "cache")
            self.assertEqual(payload["error"]["code"], "bad_key")
            # D-SINK-18. No path to give it, so the scratch config home is
            # named through the environment; it has no shell.json, which is a
            # structured refusal and not an exit 3.
            code, payload, _ = run("config", "shield", env={"XDG_CONFIG_HOME": os.path.join(tmp, "config")})
            self.assertEqual(code, 1)
            self.assertEqual(payload["kind"], "config")
            self.assertEqual(payload["error"]["code"], "config_absent")

    def test_usage_errors_exit_2_without_json(self):
        # A bare `playlist` is no longer a usage error: --url is optional
        # since D-SINK-8 (the shell passes the URL in $OMARCHY_IPTV_URL), and
        # neither given is a JSON `bad_url` status (tests/test_url_env.py).
        for args in (["play"], ["play", "--id", "a", "--url", "b"], ["state"], ["state", "favorite", "add"],
                     ["state", "source"], ["state", "source", "add"], ["cache"], ["cache", "remove"],
                     ["config"], ["config", "shield", "/etc/passwd"], ["bogus"]):
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
        """D-SINK-57 (2026-10-29): a typed LOOPBACK source whose redirect names
        another port is redirected to another HOST, refused at connect
        (tests/test_destinations.py holds that). So the two servers stand in
        for two PUBLIC hosts here, through the one test seam that reads
        127.0.0.1 as global (helper_loader.loopback_reads_public), with the
        helper run in this process -- the seam reaches no subprocess."""
        import contextlib
        import io
        from helper_loader import loopback_reads_public
        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, loopback_reads_public(helper), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = helper.main(["playlist", "--url", self.first.url("/cross", "user:pw"), "--cache-dir", tmp,
                                "--timeout", "5"])
        status, stderr = json.loads(out.getvalue().strip().splitlines()[-1]), err.getvalue()
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

class SharedRedactionVectors(unittest.TestCase):
    """The same fixture tests/Model.test.js runs.

    CLAUDE.md: a rule implemented in both JavaScript and Python gets ONE shared
    fixture that both implementations run. Before this existed the two were
    pinned by disjoint hand-written lists whose every vector carried exactly one
    '@', so D-SINK-1 was invisible to both suites at once.
    """

    def vectors(self):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "fixtures", "redaction-vectors.json"), encoding="utf-8") as fh:
            return json.load(fh)["vectors"]

    def test_every_shared_vector_keeps_its_host_and_loses_every_credential(self):
        bad = []
        for v in self.vectors():
            out = helper.redact_urls(v["text"])
            if v["host"] not in out:
                bad.append("%s -> host missing: %s" % (v["why"], out))
                continue
            for frag in v["mustNotAppear"]:
                if frag in out:
                    bad.append("%s -> leaked %r: %s" % (v["why"], frag, out))
        self.assertEqual([], bad)

    def test_f_sink_15_the_display_reading_prints_the_rfc_host_on_every_bare_http_vector(self):
        """F-SINK-15 (2026-10-29): the DISPLAY side of the shared fixture, which
        only the node suite ran (sourceLabel, hostOf). The helper's display
        printer is source_host (urllib's RFC reading), and it must print each
        bare http(s) vector's `rfcHost` (or its `host` where the two readings
        agree) and none of `displayMustNotAppear`. The model's sourceLabel
        ended its userinfo at JS whitespace and printed the USERNAME for the
        two F-SINK-15 vectors; this side never did, and the test keeps the
        two mirrors on one reading. Mutation-checked: a source_host that cut
        the userinfo at whitespace goes red on both."""
        bare = [v for v in self.vectors() if re.match(r"^https?://", v["text"], re.I)]
        self.assertGreaterEqual(len(bare), 20)
        self.assertEqual(2, sum(1 for v in bare if re.match(r"^https?://[^/?#]*\s[^/?#]*@", v["text"])))
        bad = []
        for v in bare:
            host = helper.source_host(v["text"])
            want = v.get("rfcHost", v["host"]).lower()
            leaked = [f for f in v.get("displayMustNotAppear", v["mustNotAppear"]) if f in host]
            if host != want or leaked:
                bad.append("%s -> %r %r" % (v["why"], host, leaked))
        self.assertEqual([], bad)

    def test_r32a2_every_vector_with_an_exact_py_output_gets_it(self):
        """R32a''' (2026-10-22): a vector carrying `py` pins the EXACT helper
        output -- the restored sentence punctuation (`'`, `"`, `<`, `>`
        included, D-SINK-33) and the accepted costs that are seen rather
        than described: D-SINK-34, a DELIMITER inside a password ends the
        run, one split vector per delimiter and no other; D-SINK-35. Every
        other union member inside a password has a vector asserting the
        HOST and never the username (D-SINK-36: under R32a'' this helper
        printed `http://myuser<U+FEFF>ss@prov.test/live/1.ts`). The node
        suite reads `js` the same way."""
        exact = [v for v in self.vectors() if "py" in v]
        self.assertGreaterEqual(len(exact), 20)
        bad = ["%s -> %r" % (v["why"], helper.redact_urls(v["text"])) for v in exact
               if helper.redact_urls(v["text"]) != v["py"]]
        self.assertEqual([], bad)
        for ch in ["\t", "\n", "\x0b", "\x0c", "\r", " "]:
            self.assertTrue(any(v.get("accepted") == "D-SINK-34" and "pa" + ch + "ss@" in v["text"] and v["host"] == "myuser"
                                for v in exact), repr(ch))
        self.assertEqual(6, sum(1 for v in exact if v.get("accepted") == "D-SINK-34"))
        for ch in ["\ufeff", "\x85", "\x1c", "\x1d", "\x1e", "\x1f", "\u2028", "\xa0"]:
            self.assertTrue(any("accepted" not in v and "pa" + ch + "ss@" in v["text"] and v["host"] == "prov.test"
                                and v["py"] == "Failed to open http://prov.test." and "myuser" in v["mustNotAppear"]
                                for v in exact), repr(ch))
        for ch in ["'", '"', "<", ">"]:
            self.assertTrue(any("pa" + ch + "ss@" in v["text"] and v["host"] == "prov.test" for v in exact), ch)
        self.assertTrue(any(v.get("accepted") == "D-SINK-35" and v["host"] == "user.name" for v in self.vectors()))

    def test_r32a2_one_whitespace_class_shared_with_the_model(self):
        """R32a''' (D-SINK-36; R32a'' before it, D-SINK-32, D-SINK-33): TWO
        classes for two purposes. A READER refuses the union: _URL_SPACE
        (validate_source_url) matches exactly URL_SPACE_CHARS, the union of
        JS \\s, Python \\s and U+FEFF enumerated as `codePoints` in
        tests/fixtures/url-whitespace.json. A REDACTOR delimits at ASCII:
        the run (_URL_TAIL_RE) and the authority (_URL_DELIMITER) of a
        free-text URL end at URL_DELIMITER_CHARS, the six `delimiters` in
        the same file, and at nothing else. The node suite holds
        Model.isUrlSpaceAt and Model.isUrlDelimiterAt to the same file.
        Every code point of the whole range is asked, so each class is
        exactly its list. Lane-bounds-s3's helper had two classes the
        wrong way round (a password holding U+FEFF printed the username);
        lane-bounds-s4's ended the run at the union and printed the
        username and the tail for U+FEFF where 0.14.3 printed the host."""
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "fixtures", "url-whitespace.json"), encoding="utf-8") as fh:
            doc = json.load(fh)
        want = {int(e["code"][2:], 16) for e in doc["codePoints"]}
        delims = {int(e["code"][2:], 16) for e in doc["delimiters"]}
        self.assertEqual(len(want), doc["unionCount"])
        self.assertEqual(len(delims), doc["delimiterCount"])
        self.assertEqual(sorted(ord(c) for c in helper.URL_SPACE_CHARS), sorted(want))
        self.assertEqual(sorted(ord(c) for c in helper.URL_DELIMITER_CHARS), sorted(delims))
        self.assertTrue(all(c < 0x80 for c in delims))
        wrong = [hex(c) for c in range(0x110000)
                 if (helper._URL_SPACE.match(chr(c)) is not None) != (c in want)]
        self.assertEqual([], wrong[:8])
        delim_wrong = [hex(c) for c in range(0x110000)
                       if (helper._URL_DELIMITER.match(chr(c)) is not None) != (c in delims)]
        self.assertEqual([], delim_wrong[:8])
        # The run's class is the exact complement of the delimiters.
        tail_wrong = [hex(c) for c in range(0x110000)
                      if (helper._URL_TAIL_RE.match(chr(c)) is not None) == (c in delims)]
        self.assertEqual([], tail_wrong[:8])
        py_space = {c for c in range(0x110000) if re.match(r"\s", chr(c))}
        self.assertTrue(delims < py_space < want)
        self.assertEqual(sorted(want - py_space), [0xFEFF])
        # Every union member that is not a delimiter is URL text: inside a
        # password the host prints; after a URL it is copied through.
        split = [hex(c) for c in sorted(want - delims)
                 if helper.redact_urls("x http://myuser:pa%sss@h.test/x y" % chr(c)) != "x http://h.test y"]
        self.assertEqual([], split)
        swallowed = [hex(c) for c in sorted(want - delims)
                     if helper.redact_urls("see http://h.test%snext" % chr(c)) != "see http://h.test%snext" % chr(c)]
        self.assertEqual([], swallowed)
        for c in sorted(delims):
            self.assertEqual(helper.redact_urls("http://u:p@h.test/x%sSECRET@tail" % chr(c)), "http://h.test%sSECRET@tail" % chr(c), hex(c))
        # Quotes and angle brackets are trailing punctuation, not run ends.
        self.assertEqual(helper._TRAILING_PUNCTUATION, ".,;:!?)]'\"<>")
        for ch in "'\"<>":
            self.assertNotIn(ch, helper.URL_SPACE_CHARS)
            self.assertNotIn(ch, helper.URL_DELIMITER_CHARS)
            self.assertEqual(helper.redact_urls("x http://u:pa%sss@h.test/x y" % ch), "x http://h.test y", ch)
        for ch in "'\"<>.":
            self.assertEqual(helper.redact_urls("%shttp://u:p@h.test/x%s" % (ch, ch)), "%shttp://h.test%s" % (ch, ch), ch)

    def test_r32a2_the_second_arm_of_the_predicate(self):
        """R32a'' (D-SINK-35 narrowed): a NON-NUMERIC port -- a `:` after the
        authority's last `@` whose text, up to `;`, `=` or `&`, is non-empty
        and not all digits -- followed by a later `@` withholds, dotted host
        or not; a numeric or empty port, a bracketed literal and a value
        with no later `@` do not. The residual, stated: a dotted username
        before a digits-only password prefix prints as the host."""
        for url in ["http://user.name:pa/ss@h.test/x", "http://me@mail.test:pa/ss@h.test/x", "http://h.test:pa/me@x.test/y",
                    "http://h.test:8080x/me@x.test/y", "http://h.test:p?me@x", "http://me@mail.test:pa&x=1/ss@h.test/x",
                    "http://:pa/me@x", "http://h.test:pa;x=1/me@x"]:
            self.assertTrue(helper.host_withheld(url), url)
            self.assertEqual(helper.redact_urls(url), "http://" + helper.HOST_WITHHELD, url)
        for url in ["http://user.name:2024/ab@host/x", "http://h.test:/me@x.test/y", "http://[::1]:pa/me@x", "http://h.test:pa/ss",
                    "http://h.test:;=&/a@b", "http://me@mail.test:pa/ss y@z", "http://user.name:2024&p=x/a@b"]:
            self.assertFalse(helper.host_withheld(url), url)
        self.assertEqual(helper.redact_urls("http://user.name:2024/ab@host/x"), "http://user.name")
        self.assertEqual(helper.fallback_channel_name("http://user.name:pa/ss@h.test/x", "channel"), "Stream")
        self.assertEqual(helper.validate_source_url("http://h.test:pa/me@x.test/y")["code"], "invalid")

    def test_the_shared_fixture_still_carries_the_case_that_started_it(self):
        texts = [v["text"] for v in self.vectors()]
        self.assertGreaterEqual(len(texts), 8)
        self.assertTrue(any("qa@pass" in t for t in texts),
                        "the doubled-@ vector is the reason this fixture exists")


if __name__ == "__main__":
    unittest.main()


class StateReaderParityTest(unittest.TestCase):
    """D-SINK-23, second half (PARITY, 2026-10-24): the helper's normalize_source
    and Model.parseState read a STORED url the same way -- validated as origin
    `cli`, the record keeping the validated form, a url that fails dropping
    the record, epgUrl cleared rather than dropped. The shared fixture is
    tests/fixtures/state-reader-urls.json; tests/Model.test.js runs the same
    rows through the JS reader. This is the python half; it was green before
    the JS half changed, which is the point: the fixture is what the shell now
    has to match."""

    def test_normalize_state_reads_every_fixture_row_as_the_fixture_says(self):
        fixture = FIXTURES / "state-reader-urls.json"
        self.assertTrue(fixture.exists(), "tests/fixtures/state-reader-urls.json is missing")
        cases = json.loads(fixture.read_text(encoding="utf-8"))["cases"]
        self.assertGreaterEqual(len(cases), 15)
        self.assertGreaterEqual(sum(1 for c in cases if c["kept"] is False), 4)
        self.assertGreaterEqual(sum(1 for c in cases if c["kept"] and c["url"] != c["outUrl"]), 4)
        for c in cases:
            record = {"key": "aaaaaaa1", "url": c["url"], "epgUrl": c["epgUrl"], "kind": "http", "label": "",
                      "labelCustom": False, "origin": "guide", "addedAt": 1, "lastUsed": 1, "fetchedAt": 0,
                      "channelCount": 0, "groupCount": 0}
            state = helper.normalize_state({"version": 2, "cacheLayout": 2, "sources": [record]})
            sources = state["sources"]
            self.assertEqual(len(sources) == 1, c["kept"], c["why"])
            if c["kept"]:
                self.assertEqual(sources[0]["url"], c["outUrl"], c["why"])
                self.assertEqual(sources[0]["epgUrl"], c["outEpgUrl"], c["why"])
                self.assertEqual(sources[0]["kind"], c["kind"], c["why"])


class CasefoldDiffPinTest(unittest.TestCase):
    """D-SRC-12 (the optional pin, 2026-10-24). The two mirrors fold a host
    and a label with their own runtime's Unicode tables (`host.lower()`
    here, `host.toLowerCase()` in the model), and the tables disagree on 28
    code points today (three Latin Extended-D letters and the 25 Medefaidrin
    capitals) -- a node-vs-CPython version fact, accepted on the board
    because no provider host carries them and ASCII-only folding would stop
    folding every Cyrillic or Greek capital a user types. What this pins is
    that the DISAGREEMENT SET is known: tests/fixtures/casefold-diff.json
    holds each runtime's whole non-identity lowering table (every code point
    whose lower() is not itself, surrogates excluded) and the set where the
    two differ. This half asserts CPython's table equals the fixture's
    python table, recomputes the diff from the fixture's two tables and
    asserts it equals the pinned set, and runs every pinned code point
    through the shipping validator and label_key, so the join is a call.
    tests/Model.test.js is the node half. A runtime whose tables move goes
    red here rather than being discovered as two cache directories for one
    source. The suite WRITES its own half of the fixture only under
    CASEFOLD_FIXTURE_REWRITE=1 (the node suite likewise); without the flag
    it reads and pins."""

    FIXTURE = FIXTURES / "casefold-diff.json"

    @staticmethod
    def code_point_name(cp):
        return "U+%04X" % cp

    @classmethod
    def own_table(cls):
        table = {}
        for cp in range(0, 0x110000):
            if 0xD800 <= cp <= 0xDFFF:
                continue
            ch = chr(cp)
            low = ch.lower()
            if low != ch:
                table[cls.code_point_name(cp)] = " ".join(cls.code_point_name(ord(c)) for c in low)
        return table

    @staticmethod
    def diff_of(python_table, node_table):
        keys = set(python_table) | set(node_table)
        return sorted((k for k in keys if python_table.get(k) != node_table.get(k)), key=lambda k: int(k[2:], 16))

    def test_the_disagreement_set_is_pinned_and_reaches_the_validator(self):
        import unicodedata
        own = self.own_table()
        if os.environ.get("CASEFOLD_FIXTURE_REWRITE") == "1":
            data = json.loads(self.FIXTURE.read_text(encoding="utf-8")) if self.FIXTURE.exists() else {}
            data.setdefault("node", {"runtime": "", "lower": {}})
            data["python"] = {"runtime": "CPython %s, unicodedata %s" % (sys.version.split()[0], unicodedata.unidata_version), "lower": own}
            data["diff"] = self.diff_of(own, data["node"]["lower"])
            data["_comment"] = [
                "D-SRC-12: the code points where CPython's str.lower and node's toLowerCase disagree.",
                "`python.lower` and `node.lower` are each runtime's whole non-identity lowering table over",
                "U+0000..U+10FFFF (surrogates excluded): code point -> the code points of its lower form.",
                "`diff` is where the two tables differ; both suites recompute it from the two tables and pin it.",
                "Written by the suite that owns each half under CASEFOLD_FIXTURE_REWRITE=1:",
                "  CASEFOLD_FIXTURE_REWRITE=1 python3 -m unittest discover -s tests -p test_helper.py",
                "  CASEFOLD_FIXTURE_REWRITE=1 node tests/Model.test.js",
                "and read, never written, otherwise. ASCII only.",
            ]
            self.FIXTURE.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        self.assertTrue(self.FIXTURE.exists(), "tests/fixtures/casefold-diff.json is missing")
        data = json.loads(self.FIXTURE.read_text(encoding="utf-8"))
        python_table = data["python"]["lower"]
        node_table = data["node"]["lower"]
        self.assertGreater(len(python_table), 1000)
        self.assertGreater(len(node_table), 1000)
        # (1) this runtime's table is the one the fixture holds
        self.assertEqual(own, python_table, "CPython's lowering table moved: re-run under CASEFOLD_FIXTURE_REWRITE=1 and re-read the diff")
        # (2) the disagreement set is exactly the pinned one
        diff = self.diff_of(python_table, node_table)
        self.assertEqual(diff, data["diff"])
        self.assertEqual(len(diff), 28)
        self.assertIn("U+A7CE", diff)
        self.assertIn("U+16EA0", diff)
        # (3) every pinned code point reaches the shipping folders as a call
        for name in diff:
            cp = int(name[2:], 16)
            ch = chr(cp)
            want = "".join(chr(int(c[2:], 16)) for c in python_table.get(name, name).split(" "))
            checked = helper.validate_source_url("http://" + ch + ".test/", origin="cli")
            self.assertTrue(checked["ok"], name)
            self.assertEqual(checked["host"], want + ".test", name)
            self.assertEqual(helper.host_port_of(checked["url"]), want + ".test", name)
            self.assertEqual(helper.label_key(ch), want, name)

