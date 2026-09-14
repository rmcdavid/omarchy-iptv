"""mpv JSON IPC tests for bin/omarchy-iptv (play / stop / status) against a
fake mpv server on a unix socket. No real mpv, no network.

Run: python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import os
import pathlib
import shutil
import socket
import tempfile
import threading
import time
import unittest

from helper_loader import load_helper

helper = load_helper()

PLAYLIST = """#EXTM3U
#EXTINF:-1 tvg-id="bbc1.uk" group-title="UK",BBC One HD
http://stream.example.test/live/bbc1.m3u8
#EXTINF:-1 tvg-id="espn.us",ESPN
#EXTVLCOPT:http-user-agent=VLC/3.0.20
#EXTVLCOPT:http-referrer=http://ref.example.test/
#KODIPROP:inputstream.adaptive.stream_headers=X-Forwarded-For=1.2.3.4&Cookie=a%3Db
http://stream.example.test/live/espn.m3u8
"""
STATUS_PROPS = {
    "media-title": "BBC One HD",
    "path": "http://user:pw@provider.example.test/live/u/p/1.m3u8",
    "pause": False,
    "idle-active": False,
    "mpv-version": "mpv 0.41.0",
}


def run(*args):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(args))
    lines = out.getvalue().strip().splitlines()
    payload = json.loads(lines[-1]) if lines else None
    return code, payload, out.getvalue(), err.getvalue()


class FakeMpv:
    """Accepts connections on a unix socket, records every command and answers
    like mpv: {"error": "success", "data": ..., "request_id": N}.

    Each connection is served by its own thread, because the detached player
    keeps a persistent subscriber on the socket while control calls come and
    go: a server that handled one connection at a time would deadlock the
    second caller (and would be more forgiving than mpv, which names its
    clients ipc_0 / ipc_1 and correlates by request_id).

    It also mirrors three things real mpv does that the M2-02 paths depend on:
    `user-data/<node>` sub-paths store and read back per node while the top
    level is not writable, `loadfile` answers with a playlist_entry_id, and
    events can arrive unasked at any moment (`inject`).
    """

    def __init__(self, path, props=None, event_first=False, silent=False, refuse=(), close_on_quit=True,
                 entry_ids=True, user_data=None):
        self.path = path
        self.props = props or {}
        self.event_first = event_first
        self.silent = silent
        self.refuse = set(refuse)
        self.close_on_quit = close_on_quit
        self.entry_ids = entry_ids
        self.user_data = dict(user_data or {})
        self.commands = []
        self.log_levels = []
        self.entry_id = 0
        self.lock = threading.Lock()
        self.conns = []
        self.workers = []
        self.running = True
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(path)
        self.server.listen(8)
        self.server.settimeout(0.05)
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while self.running:
            try:
                conn, _ = self.server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            worker = threading.Thread(target=self.handle, args=(conn,), daemon=True)
            with self.lock:
                self.conns.append(conn)
                self.workers.append(worker)
            worker.start()

    def inject(self, event):
        """Push an unsolicited event line to every live connection, the way
        mpv emits start-file / end-file / log-message / property-change."""
        payload = (json.dumps(event) + "\n").encode("utf-8")
        with self.lock:
            targets = list(self.conns)
        for conn in targets:
            try:
                conn.sendall(payload)
            except OSError:
                continue

    def handle(self, conn):
        conn.settimeout(3)
        try:
            if self.event_first:
                conn.sendall(b'{"event":"start-file"}\nnot json at all\n')
            buffer = b""
            while True:
                try:
                    chunk = conn.recv(4096)
                except (TimeoutError, OSError):
                    return
                if not chunk:
                    return
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    message = json.loads(line.decode("utf-8"))
                    with self.lock:
                        self.commands.append(message["command"])
                    if self.silent:
                        continue
                    reply = self.reply_for(message)
                    if reply is None:
                        return
                    conn.sendall((json.dumps(reply) + "\n").encode("utf-8"))
        finally:
            with self.lock:
                if conn in self.conns:
                    self.conns.remove(conn)
            try:
                conn.close()
            except OSError:
                pass

    def reply_for(self, message):
        command = message["command"]
        request_id = message.get("request_id")
        if command[0] == "quit":
            return None if self.close_on_quit else {"error": "success", "request_id": request_id}
        if command[0] == "request_log_messages":
            with self.lock:
                self.log_levels.append(command[1])
            return {"error": "success", "request_id": request_id}
        if command[0] == "get_property":
            name = command[1]
            if name in self.props:
                return {"error": "success", "data": self.props[name], "request_id": request_id}
            if name.startswith("user-data/"):
                node = name.split("/", 1)[1]
                with self.lock:
                    if node in self.user_data:
                        return {"error": "success", "data": self.user_data[node], "request_id": request_id}
                return {"error": "property not found", "request_id": request_id}
            if name == "user-data":
                with self.lock:
                    return {"error": "success", "data": dict(self.user_data), "request_id": request_id}
            return {"error": "property not found", "request_id": request_id}
        if command[0] == "set_property":
            name = command[1]
            if name in self.refuse:
                return {"error": "property unavailable", "request_id": request_id}
            if name == "user-data":
                # Verified on mpv 0.41: the top level is not writable.
                return {"error": "error accessing property", "request_id": request_id}
            if name.startswith("user-data/"):
                with self.lock:
                    self.user_data[name.split("/", 1)[1]] = command[2]
                return {"error": "success", "request_id": request_id}
            return {"error": "success", "data": None, "request_id": request_id}
        if command[0] == "loadfile" and self.entry_ids:
            with self.lock:
                self.entry_id += 1
                entry = self.entry_id
            return {"error": "success", "data": {"playlist_entry_id": entry}, "request_id": request_id}
        return {"error": "success", "data": None, "request_id": request_id}

    def close(self):
        self.running = False
        self.thread.join(2)
        with self.lock:
            targets = list(self.conns)
            workers = list(self.workers)
        for conn in targets:
            try:
                conn.close()
            except OSError:
                pass
        for worker in workers:
            worker.join(2)
        self.server.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass


class MpvTestCase(unittest.TestCase):
    def setUp(self):
        # AF_UNIX paths are limited to ~108 bytes: keep the socket under /tmp.
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-test-", dir="/tmp")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.sock = os.path.join(self.dir, "mpv.sock")
        self.cache = os.path.join(self.dir, "cache")
        playlist = os.path.join(self.dir, "list.m3u")
        pathlib.Path(playlist).write_text(PLAYLIST, encoding="utf-8")
        code, _, _, stderr = run("playlist", "--url", playlist, "--cache-dir", self.cache)
        self.assertEqual(code, 0, stderr)
        self.server = None

    def start(self, **kwargs):
        self.server = FakeMpv(self.sock, **kwargs)
        self.addCleanup(self.server.close)
        return self.server

    def play(self, *args):
        return run("play", *args, "--cache-dir", self.cache, "--socket", self.sock, "--ipc-timeout", "1")


class PlayTest(MpvTestCase):
    def test_sets_title_headers_then_loadfile_in_order(self):
        server = self.start()
        code, payload, stdout, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload, {"ok": True, "kind": "play", "id": "t:espn.us", "name": "ESPN"})
        self.assertEqual(server.commands, [
            ["set_property", "title", "$>ESPN"],
            ["set_property", "force-media-title", "ESPN"],
            ["set_property", "user-agent", "VLC/3.0.20"],
            ["set_property", "referrer", "http://ref.example.test/"],
            ["set_property", "http-header-fields", ["X-Forwarded-For: 1.2.3.4", "Cookie: a=b"]],
            ["loadfile", "http://stream.example.test/live/espn.m3u8", "replace"],
        ])
        self.assertEqual(len(stdout.strip().splitlines()), 1)
        self.assertNotIn("espn.m3u8", stdout + stderr)

    def test_clears_headers_for_a_channel_without_any(self):
        server = self.start(props={"option-info/user-agent/default-value": "mpv-default-ua"})
        code, payload, _, stderr = self.play("--id", "t:bbc1.uk")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["name"], "BBC One HD")
        self.assertEqual(server.commands, [
            ["set_property", "title", "$>BBC One HD"],
            ["set_property", "force-media-title", "BBC One HD"],
            ["get_property", "option-info/user-agent/default-value"],
            ["set_property", "user-agent", "mpv-default-ua"],
            ["set_property", "referrer", ""],
            ["set_property", "http-header-fields", []],
            ["loadfile", "http://stream.example.test/live/bbc1.m3u8", "replace"],
        ])

    def test_user_agent_falls_back_to_libmpv_without_option_info(self):
        server = self.start()
        code, _, _, _ = self.play("--id", "t:bbc1.uk")
        self.assertEqual(code, 0)
        self.assertIn(["set_property", "user-agent", helper.MPV_DEFAULT_USER_AGENT], server.commands)

    def test_url_verb_names_the_host_and_sends_no_headers(self):
        server = self.start()
        code, payload, stdout, stderr = self.play("--url", "https://user:pw@live.example.test/secret/path.m3u8?token=abc")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload, {"ok": True, "kind": "play", "id": None, "name": "live.example.test"})
        self.assertEqual(server.commands[-1], ["loadfile", "https://user:pw@live.example.test/secret/path.m3u8?token=abc", "replace"])
        self.assertIn(["set_property", "http-header-fields", []], server.commands)
        for secret in ("user:pw", "secret", "token=abc"):
            self.assertNotIn(secret, stdout + stderr)

    def test_unknown_channel_never_touches_mpv(self):
        server = self.start()
        code, payload, _, stderr = self.play("--id", "t:nope")
        self.assertEqual(code, 1)
        self.assertEqual(payload["kind"], "play")
        self.assertEqual(payload["error"]["code"], "unknown_channel")
        self.assertEqual(payload["id"], "t:nope")
        self.assertIn("t:nope", stderr)
        time.sleep(0.05)
        self.assertEqual(server.commands, [])

    def test_missing_cache_is_no_cache(self):
        self.start()
        code, payload, _, _ = run("play", "--id", "t:bbc1.uk", "--cache-dir", os.path.join(self.dir, "nowhere"), "--socket", self.sock)
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "no_cache")

    def test_rejects_unsafe_urls(self):
        server = self.start()
        for bad in ("file:///etc/passwd", "--script=/tmp/evil.lua", "javascript:alert(1)", ""):
            code, payload, _, _ = self.play("--url=" + bad)
            self.assertEqual(code, 1, bad)
            self.assertEqual(payload["error"]["code"], "unsupported_scheme", bad)
        time.sleep(0.05)
        self.assertEqual(server.commands, [])

    def test_not_running_when_socket_is_missing(self):
        code, payload, _, _ = self.play("--id", "t:bbc1.uk")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "not_running")
        self.assertFalse(payload["ok"])

    def test_events_and_junk_lines_are_skipped(self):
        server = self.start(event_first=True)
        code, payload, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(server.commands[-1][0], "loadfile")

    def test_header_failure_aborts_before_loadfile(self):
        server = self.start(refuse={"http-header-fields"})
        code, payload, _, _ = self.play("--id", "t:espn.us")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "ipc_error")
        self.assertIn("http-header-fields", payload["error"]["message"])
        self.assertNotIn(["loadfile", "http://stream.example.test/live/espn.m3u8", "replace"], server.commands)

    def test_title_failure_is_tolerated(self):
        server = self.start(refuse={"title"})
        code, payload, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertIn("refused to set title", stderr)
        self.assertEqual(server.commands[-1][0], "loadfile")

    def test_silent_mpv_times_out(self):
        self.start(silent=True)
        started = time.monotonic()
        code, payload, _, _ = run("play", "--id", "t:bbc1.uk", "--cache-dir", self.cache, "--socket", self.sock, "--ipc-timeout", "0.3")
        elapsed = time.monotonic() - started
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "ipc_error")
        self.assertIn("did not answer", payload["error"]["message"])
        self.assertLess(elapsed, 2.0)

    def test_utf8_channel_names_reach_mpv_unescaped(self):
        playlist = os.path.join(self.dir, "utf8.m3u")
        pathlib.Path(playlist).write_text("#EXTM3U\n#EXTINF:-1 tvg-id=\"tq.ca\",T\u00e9l\u00e9 Qu\u00e9bec\nhttp://stream.example.test/tq.m3u8\n", encoding="utf-8")
        run("playlist", "--url", playlist, "--cache-dir", self.cache)
        server = self.start()
        code, payload, _, _ = self.play("--id", "t:tq.ca")
        self.assertEqual(code, 0)
        self.assertEqual(payload["name"], "T\u00e9l\u00e9 Qu\u00e9bec")
        self.assertEqual(server.commands[0], ["set_property", "title", "$>T\u00e9l\u00e9 Qu\u00e9bec"])
        self.assertEqual(server.commands[1], ["set_property", "force-media-title", "T\u00e9l\u00e9 Qu\u00e9bec"])

    def test_title_is_sent_with_the_raw_marker_so_mpv_never_expands_it(self):
        # S-01: mpv expands ${property} in `title`; "$>" keeps the rest literal.
        playlist = os.path.join(self.dir, "expand.m3u")
        pathlib.Path(playlist).write_text('#EXTM3U\n#EXTINF:-1 tvg-id="x.test",${path} ${options/input-ipc-server}\nhttp://user:pw@stream.example.test/x.m3u8\n', encoding="utf-8")
        run("playlist", "--url", playlist, "--cache-dir", self.cache)
        server = self.start()
        code, payload, stdout, stderr = self.play("--id", "t:x.test")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["name"], "${path} ${options/input-ipc-server}")
        self.assertEqual(server.commands[0], ["set_property", "title", helper.MPV_RAW_PREFIX + "${path} ${options/input-ipc-server}"])
        self.assertEqual(helper.MPV_RAW_PREFIX, "$>")
        self.assertEqual(server.commands[1], ["set_property", "force-media-title", "${path} ${options/input-ipc-server}"])
        self.assertEqual(sum(1 for c in server.commands if c[:2] == ["set_property", "title"]), 1)
        self.assertNotIn("user:pw", stdout + stderr)


class StopTest(MpvTestCase):
    def test_ok_when_mpv_closes_without_answering(self):
        server = self.start(close_on_quit=True)
        code, payload, _, stderr = run("stop", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload, {"ok": True, "kind": "stop"})
        self.assertEqual(server.commands, [["quit"]])

    def test_ok_when_mpv_answers(self):
        self.start(close_on_quit=False)
        code, payload, _, _ = run("stop", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])

    def test_not_running_when_unreachable(self):
        code, payload, _, _ = run("stop", "--socket", self.sock)
        self.assertEqual(code, 1)
        self.assertEqual(payload["kind"], "stop")
        self.assertEqual(payload["error"]["code"], "not_running")


class StatusTest(MpvTestCase):
    def test_reports_host_never_path(self):
        self.start(props=STATUS_PROPS)
        code, payload, stdout, stderr = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload, {
            "ok": True, "kind": "status", "running": True, "mediaTitle": "BBC One HD",
            "pathHost": "provider.example.test", "paused": False, "idle": False, "mpvVersion": "mpv 0.41.0",
            # D-PLY-11: the health tick's reconciliation input. A player that
            # carries no record of ours answers null rather than dropping the
            # key, so the shell can tell "nothing to compare" from "the
            # helper is too old to be asked".
            "stash": None,
        })
        self.assertNotIn("path\"", stdout.replace("pathHost", ""))
        for secret in ("user:pw", "/live/", "1.m3u8"):
            self.assertNotIn(secret, stdout + stderr)

    def test_status_carries_the_players_own_now_playing_record(self):
        # D-PLY-11, the plan's step 2. Without this the health tick asks the
        # player five questions and never the one that matters - which
        # channel - so a shell whose label has diverged from the player has
        # no way to find out, which is why every divergence wave two produced
        # was still there two health ticks later.
        stash = helper.player_stash("t:espn.us", "ESPN", "Sport", "g:QA", "a1b2c3d4", 3000, 7,
                                    entry_id=2, verb="play")
        self.start(props=STATUS_PROPS, user_data={"omarchy-iptv": stash})
        code, payload, stdout, stderr = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["stash"], stash)
        self.assertEqual(payload["stash"]["id"], "t:espn.us")
        self.assertEqual(payload["stash"]["seq"], 7)
        self.assertEqual(payload["stash"]["verb"], "play")
        # Rule 5: the record has never carried a URL and this new sink does
        # not become the first one.
        self.assertNotIn("://", stdout + stderr)

    def test_missing_properties_become_null(self):
        self.start(props={"mpv-version": "mpv 0.41.0", "pause": True})
        code, payload, _, _ = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0)
        self.assertIsNone(payload["mediaTitle"])
        self.assertIsNone(payload["pathHost"])
        self.assertTrue(payload["paused"])
        self.assertIsNone(payload["idle"])

    def test_local_path_reports_local_file(self):
        self.start(props={"path": "/home/user/video.mkv"})
        code, payload, stdout, _ = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(payload["pathHost"], "local file")
        self.assertNotIn("video.mkv", stdout)

    def test_stale_socket_file_is_unlinked(self):
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(self.sock)
        listener.close()  # the file stays, nobody listens: ECONNREFUSED
        self.assertTrue(os.path.exists(self.sock))
        code, payload, _, stderr = run("status", "--socket", self.sock)
        self.assertEqual(code, 1)
        self.assertEqual(payload["kind"], "status")
        self.assertFalse(payload["running"])
        self.assertEqual(payload["error"]["code"], "not_running")
        self.assertFalse(os.path.exists(self.sock))
        self.assertIn("stale socket", stderr)

    def test_missing_socket_is_not_running(self):
        code, payload, _, _ = run("status", "--socket", self.sock)
        self.assertEqual(code, 1)
        self.assertEqual(payload["running"], False)
        self.assertEqual(payload["error"]["code"], "not_running")

    def test_regular_file_at_socket_path_is_left_alone(self):
        pathlib.Path(self.sock).write_text("not a socket", encoding="utf-8")
        code, payload, _, _ = run("status", "--socket", self.sock)
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "not_running")
        self.assertTrue(os.path.exists(self.sock))


if __name__ == "__main__":
    unittest.main()
