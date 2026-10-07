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

    M5-01 taught it the seek semantics docs/SPIKE-LIVE-REWIND.md 11.4 and
    12.2 measured, NO MORE FORGIVING than mpv 0.41 (CLAUDE.md rule 10):
    `seek <t> absolute` always answers `success`; the position moves only
    when the target lies inside a `seekable-ranges` entry of the
    `demuxer-cache-state` prop, and then echoes the target exactly (72 of
    72); outside it the position is unchanged and one error-level
    `Cannot seek in this stream` log-message event is pushed (31 of 31); a
    NEGATIVE target is an offset from the cache end, not a refusal (F-RWD-7,
    5 of 5). `seek_moves=False` is the underrun case: a target inside the
    range that still moves nothing. `show-text` is recorded in `osd`.

    D-SINK-16 taught it the two certificate properties, and taught it that a
    `set_property` on an ordinary property is READABLE afterwards -- which is
    what real mpv does and what this fake used to answer `property not found`
    to, making it MORE forgiving than mpv in the one direction that matters
    here (CLAUDE.md rule 10): the shipping code now reads `tls-verify` back
    rather than trusting the set reply, and a fake that could not answer a
    read-back would have let that read look impossible. The seeded defaults are
    mpv 0.41's own (`tls-verify` NO, `stream-lavf-o` empty), so a FakeMpv with
    no `props` is a player launched the way 0.12.1 launched one; `props` and
    `refuse` between them express the upgraded player and the player whose set
    does not take, and `missing` expresses a property that cannot be read at
    all.

    And the ordering mpv really has (F-RWD-15, measured 2026-10-03): the
    reply to `seek` means QUEUED. The position moves, the `seek` event is
    sent to every client and -- for a dropped seek -- the refusal line is
    sent to the clients that subscribed, all `seek_lag_s` AFTER the reply,
    on another thread, the way the playloop executes a queued seek after
    the IPC thread has answered. A read sent at once can be answered first
    and echo the old position; 1 of 12 did on the real player. `seek_lag_s`
    0 is the synchronous fake the direct-socket semantics tests drive;
    the verb tests run lagged. `seek_silent=True` is the pathological case
    that neither executes nor refuses, for the bound. Log messages reach
    only connections that asked for them, as on mpv.
    """

    REFUSAL_LINE = "Cannot seek in this stream. You can force it with '--force-seekable=yes'.\n"
    # mpv 0.41's own defaults for the two D-SINK-16 properties: `--tls-verify`
    # defaults to NO (`mpv --list-options`), and `stream-lavf-o` is an empty
    # key-value map that the JSON IPC answers as {}.
    TLS_DEFAULTS = {"tls-verify": False, "stream-lavf-o": {}}

    def __init__(self, path, props=None, event_first=False, silent=False, refuse=(), close_on_quit=True,
                 entry_ids=True, user_data=None, seek_moves=True, seek_lag_s=0.0, seek_silent=False,
                 missing=()):
        self.path = path
        self.props = dict(self.TLS_DEFAULTS)
        self.props.update(props or {})
        self.missing = set(missing)
        for name in self.missing:
            self.props.pop(name, None)
        self.event_first = event_first
        self.silent = silent
        self.refuse = set(refuse)
        self.close_on_quit = close_on_quit
        self.entry_ids = entry_ids
        self.user_data = dict(user_data or {})
        self.seek_moves = seek_moves
        self.seek_lag_s = seek_lag_s
        self.seek_silent = seek_silent
        self.log_conns = set()
        self.command_times = []
        self.seeks = []
        self.osd = []
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
        mpv emits start-file / end-file / seek / property-change -- and a
        log-message only to the connections that subscribed, as mpv does."""
        payload = (json.dumps(event) + "\n").encode("utf-8")
        with self.lock:
            targets = list(self.conns)
            if event.get("event") == "log-message":
                targets = [c for c in targets if c in self.log_conns]
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
                        self.command_times.append(time.monotonic())
                        if message["command"][0] == "request_log_messages":
                            self.log_conns.add(conn)
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
            if name in self.missing:
                return {"error": "property not found", "request_id": request_id}
            with self.lock:
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
            # Real mpv stores it, and a later get_property answers with it. A
            # fake that answered `property not found` to the read-back of its
            # own write is more forgiving than mpv in exactly the direction
            # D-SINK-16's fix depends on (rule 10). A name in `missing` stays
            # unreadable: that is the wedged / too-old player.
            if name not in self.missing:
                with self.lock:
                    self.props[name] = command[2]
            return {"error": "success", "data": None, "request_id": request_id}
        if command[0] == "loadfile" and self.entry_ids:
            with self.lock:
                self.entry_id += 1
                entry = self.entry_id
            return {"error": "success", "data": {"playlist_entry_id": entry}, "request_id": request_id}
        if command[0] == "seek":
            self.seek(command)
            return {"error": "success", "data": None, "request_id": request_id}
        if command[0] == "show-text":
            with self.lock:
                self.osd.append(list(command[1:]))
            return {"error": "success", "data": None, "request_id": request_id}
        return {"error": "success", "data": None, "request_id": request_id}

    def seek(self, command):
        """mpv 0.41's measured seek: see the class docstring. Records
        (target, landed) in `seeks`; a refusal pushes the log line."""
        amount = float(command[1])
        mode = command[2] if len(command) > 2 else "relative"
        position = self.props.get("time-pos")
        ranges = []
        state = self.props.get("demuxer-cache-state")
        if isinstance(state, dict):
            ranges = [(float(r["start"]), float(r["end"])) for r in state.get("seekable-ranges", [])]
        landed = False
        target = None
        if isinstance(position, (int, float)) and not isinstance(position, bool):
            target = amount if mode == "absolute" else position + amount
            if mode == "absolute" and amount < 0 and ranges:
                # F-RWD-7: a negative absolute target counts from the END.
                target = ranges[-1][1] + amount
            inside = any(start <= target <= end for start, end in ranges)
            if inside and self.seek_moves:
                landed = True
        with self.lock:
            self.seeks.append((target, landed))

        def execute():
            if self.seek_silent:
                return
            if landed:
                self.props["time-pos"] = target
                self.inject({"event": "seek"})
            else:
                self.inject({"event": "log-message", "prefix": "cplayer", "level": "error",
                             "text": self.REFUSAL_LINE})
        if self.seek_lag_s > 0:
            threading.Timer(self.seek_lag_s, execute).start()
        else:
            execute()

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
            # D-SINK-16: asserted and READ BACK before anything else, because
            # everything below this is the act of telling an unverified process
            # about a channel.
            ["set_property", "tls-verify", True],
            ["set_property", "stream-lavf-o", {}],
            ["get_property", "tls-verify"],
            ["get_property", "stream-lavf-o"],
            ["set_property", "pause", False],
            ["set_property", "aid", "auto"],
            ["set_property", "sid", "auto"],
            ["set_property", "title", "$>ESPN"],
            ["set_property", "force-media-title", "ESPN"],
            ["set_property", "user-agent", "VLC/3.0.20"],
            ["set_property", "referrer", "http://ref.example.test/"],
            ["set_property", "http-header-fields", ["X-Forwarded-For: 1.2.3.4", "Cookie: a=b"]],
            ["loadfile", "http://stream.example.test/live/espn.m3u8", "replace"],
        ])
        self.assertEqual(len(stdout.strip().splitlines()), 1)
        self.assertNotIn("espn.m3u8", stdout + stderr)

    def test_a_channel_change_resets_the_track_selection(self):
        """M3-02 / 0.9.0 preflight. mpv keeps `aid` and `sid` across a
        loadfile exactly as it keeps `pause`, so a user who picked the
        Spanish audio on one channel got track 2 of the NEXT channel --
        whatever that happens to be -- with the picker cleared and nothing on
        screen saying why. Two shipped sentences promised the opposite. The
        reset is atomic with the load for the same reason the pause reset is:
        the shell's own view is optimistic and cannot be.
        """
        server = self.start()
        code, _, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        sets = [c for c in server.commands if c[0] == "set_property"]
        self.assertIn(["set_property", "aid", "auto"], sets)
        self.assertIn(["set_property", "sid", "auto"], sets)
        # Before the loadfile, or the new channel loads with the old track.
        load = server.commands.index(["loadfile", "http://stream.example.test/live/espn.m3u8", "replace"])
        for prop in ("aid", "sid"):
            self.assertLess(server.commands.index(["set_property", prop, "auto"]), load)

    def test_clears_headers_for_a_channel_without_any(self):
        server = self.start(props={"option-info/user-agent/default-value": "mpv-default-ua"})
        code, payload, _, stderr = self.play("--id", "t:bbc1.uk")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["name"], "BBC One HD")
        self.assertEqual(server.commands, [
            ["set_property", "tls-verify", True],
            ["set_property", "stream-lavf-o", {}],
            ["get_property", "tls-verify"],
            ["get_property", "stream-lavf-o"],
            ["set_property", "pause", False],
            ["set_property", "aid", "auto"],
            ["set_property", "sid", "auto"],
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
        self.assertIn(["set_property", "title", "$>T\u00e9l\u00e9 Qu\u00e9bec"], server.commands)
        self.assertIn(["set_property", "force-media-title", "T\u00e9l\u00e9 Qu\u00e9bec"], server.commands)

    def test_title_is_sent_with_the_raw_marker_so_mpv_never_expands_it(self):
        # S-01: mpv expands ${property} in `title`; "$>" keeps the rest literal.
        playlist = os.path.join(self.dir, "expand.m3u")
        pathlib.Path(playlist).write_text('#EXTM3U\n#EXTINF:-1 tvg-id="x.test",${path} ${options/input-ipc-server}\nhttp://user:pw@stream.example.test/x.m3u8\n', encoding="utf-8")
        run("playlist", "--url", playlist, "--cache-dir", self.cache)
        server = self.start()
        code, payload, stdout, stderr = self.play("--id", "t:x.test")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["name"], "${path} ${options/input-ipc-server}")
        self.assertIn(["set_property", "title", helper.MPV_RAW_PREFIX + "${path} ${options/input-ipc-server}"], server.commands)
        self.assertEqual(helper.MPV_RAW_PREFIX, "$>")
        self.assertIn(["set_property", "force-media-title", "${path} ${options/input-ipc-server}"], server.commands)
        self.assertEqual(sum(1 for c in server.commands if c[:2] == ["set_property", "title"]), 1)
        self.assertNotIn("user:pw", stdout + stderr)


class TlsVerificationTest(MpvTestCase):
    """D-SINK-16: apply_channel asserts the certificate properties, and REFUSES
    to load when it cannot make them safe.

    The maintainer raised this against the SHIPPED 0.13.0
    (omacom/omarchy-plugin-marketplace#10389): 0.13.0 made every player this
    plugin LAUNCHES verify, by four layers that all live on the launch argv, and
    an adopted player's argv belongs to whatever version started it. Our own
    filing (D-PLY-25) called that stale state a user could restart away; he named
    the part that makes it live, which is that the helper goes on sending that
    same process new provider headers and new credentialed URLs.

    The failure case is the point of this class. `pause`, `aid` and `sid` are
    best effort because getting them wrong costs a black screen; TLS is not,
    because loading is the act of handing over the credential. `refuse` is the
    set that does not take and `missing` is the property that cannot be read -
    FakeMpv answers both the way mpv does (see its docstring, rule 10).
    """

    FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "player-tls.json"
    LOADFILE = ["loadfile", "http://stream.example.test/live/espn.m3u8", "replace"]

    def test_the_property_names_are_the_fixture_and_not_a_second_copy(self):
        """Rule 13: two literals joined by a name are joined by nothing. The
        shared fixture names them and Model.test.js asserts its own constants
        against the same two strings."""
        names = json.loads(self.FIXTURE.read_text(encoding="utf-8"))["properties"]
        self.assertEqual([helper.MPV_TLS_VERIFY_PROP, helper.MPV_STREAM_OPTS_PROP],
                         [names["verify"], names["streamOptions"]])

    def test_the_shared_fixture_decides_the_rule_in_both_languages(self):
        """Rule 12: one fixture, both implementations. tests/Model.test.js runs
        the same cases through Model.tlsPropertiesSafe."""
        cases = json.loads(self.FIXTURE.read_text(encoding="utf-8"))["cases"]
        self.assertGreaterEqual(len(cases), 15)
        got = ["%s: %s" % (c["name"], helper.tls_properties_safe(c["verify"], c["optionCount"])) for c in cases]
        want = ["%s: %s" % (c["name"], c["safe"]) for c in cases]
        self.assertEqual(got, want)
        # The vectors that matter most are the ones a more forgiving reader would
        # wave through, so assert the fixture still carries them.
        self.assertIn(1, [c["verify"] for c in cases])
        self.assertIn(False, [c["optionCount"] for c in cases])
        self.assertEqual([c["safe"] for c in cases].count(True), 1)

    def test_both_properties_are_set_and_read_back_before_the_loadfile(self):
        server = self.start()
        code, _, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        names = [c[:2] for c in server.commands]
        load = server.commands.index(self.LOADFILE)
        for command in (["set_property", "tls-verify"], ["set_property", "stream-lavf-o"],
                        ["get_property", "tls-verify"], ["get_property", "stream-lavf-o"]):
            self.assertIn(command, names, command)
            self.assertLess(names.index(command), load, command)
        # In that order, and the set before its own read-back: a read taken
        # first would grade the player as it was found, not as it was left.
        self.assertLess(names.index(["set_property", "tls-verify"]), names.index(["set_property", "stream-lavf-o"]))
        self.assertLess(names.index(["set_property", "tls-verify"]), names.index(["get_property", "tls-verify"]))
        self.assertLess(names.index(["set_property", "stream-lavf-o"]), names.index(["get_property", "stream-lavf-o"]))
        # And the values are the safe ones, not merely the right properties.
        self.assertIn(["set_property", "tls-verify", True], server.commands)
        self.assertIn(["set_property", "stream-lavf-o", {}], server.commands)

    def test_a_pre_upgrade_player_is_migrated_and_then_loaded(self):
        """The exposure, closed: a player with mpv's own defaults and a stale
        `tls_verify=0` left in `stream-lavf-o` by a user argument 0.12.1 did not
        reserve. Both are gone before the URL goes out, and the channel plays."""
        server = self.start(props={"tls-verify": False, "stream-lavf-o": {"tls_verify": "0"}})
        code, payload, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["ok"])
        self.assertIn(self.LOADFILE, server.commands)
        self.assertIs(server.props["tls-verify"], True)
        self.assertEqual(server.props["stream-lavf-o"], {})

    def test_a_player_already_verifying_is_left_as_it_is_and_loaded(self):
        server = self.start(props={"tls-verify": True})
        code, payload, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["ok"])
        self.assertIn(self.LOADFILE, server.commands)
        self.assertIs(server.props["tls-verify"], True)

    def test_a_refused_tls_verify_aborts_before_the_loadfile(self):
        server = self.start(refuse={"tls-verify"})
        code, payload, stdout, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 1)
        self.assertEqual(payload["kind"], "play")
        self.assertEqual(payload["error"]["code"], "tls_unverified")
        self.assertNotIn(self.LOADFILE, server.commands)
        self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])
        # And nothing about the channel reached it either: the refusal is raised
        # before the title, so an unsecurable player is not even relabelled.
        self.assertEqual([c for c in server.commands if c[:2] == ["set_property", "title"]], [])
        self.assertEqual([c for c in server.commands if c[:2] == ["set_property", "http-header-fields"]], [])
        # Rule 5: the refusal names no URL and no header value, on either stream.
        for secret in ("espn.m3u8", "stream.example.test", "VLC/3.0.20", "ref.example.test"):
            self.assertNotIn(secret, stdout + stderr, secret)

    def test_a_refused_stream_lavf_o_clear_aborts_before_the_loadfile(self):
        """The layer-3 shape: mpv's own flag says yes while FFmpeg's AVOption
        says no, and the AVOption wins (measured, D-SINK-13). A clear that does
        not take is therefore a refusal, not a warning."""
        server = self.start(props={"tls-verify": True, "stream-lavf-o": {"tls_verify": "0"}},
                            refuse={"stream-lavf-o"})
        code, payload, _, _ = self.play("--id", "t:espn.us")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "tls_unverified")
        self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])

    def test_an_unreadable_property_aborts_before_the_loadfile(self):
        """A set that answers `success` is a statement about the request, not
        about the value, so the read-back is the judge - and a player that
        cannot be read is not a player that can be graded safe."""
        for name in ("tls-verify", "stream-lavf-o"):
            with self.subTest(property=name):
                server = self.start(missing={name})
                code, payload, _, _ = self.play("--id", "t:espn.us")
                self.assertEqual(code, 1)
                self.assertEqual(payload["error"]["code"], "tls_unverified")
                self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])
                server.close()
                self.server = None

    def test_the_refusal_is_a_failed_play_and_not_a_silent_no_op(self):
        """The caller has to treat it as a failed play: exit 1, an `ok: false`
        reply with the stable code the shell switches on, and a journal line.
        Model.playFailureVerdict("tls_unverified") is "failed" on the other side
        of that boundary (tests/Model.test.js)."""
        self.start(refuse={"tls-verify"})
        code, payload, stdout, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 1)
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "tls_unverified")
        self.assertIn("verify", payload["error"]["message"])
        self.assertIn("tls-verify", stderr)
        self.assertEqual(len(stdout.strip().splitlines()), 1)

    def test_the_journal_line_carries_the_readings_and_nothing_out_of_the_map(self):
        """Diagnosable without being a sink: a three-valued flag and a count.
        `stream-lavf-o` can hold a proxy address with credentials in it."""
        self.start(props={"stream-lavf-o": {"tls_verify": "0", "http_proxy": "http://u:pw@proxy.test"}},
                   refuse={"tls-verify", "stream-lavf-o"})
        code, payload, stdout, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "tls_unverified")
        self.assertIn("tls-verify reads False", stderr)
        self.assertIn("stream-lavf-o holds 2 entries", stderr)
        for secret in ("u:pw", "proxy.test", "http_proxy", "tls_verify"):
            self.assertNotIn(secret, stdout + stderr, secret)

    def test_mutating_the_refusal_into_best_effort_lets_the_url_out(self):
        """Rule 11 where there is no `before`: break the one decision this
        function exists to make and watch the load happen anyway.

        assert_tls_verification() differs from its three neighbours in exactly
        one way - it raises instead of shrugging - so the mutation is to shrug.
        If this passes, the test above it is proving nothing.
        """
        server = self.start(refuse={"tls-verify"})
        original = helper.assert_tls_verification

        def best_effort(client, label):
            try:
                original(client, label)
            except helper.HelperError:
                return
        helper.assert_tls_verification = best_effort
        self.addCleanup(setattr, helper, "assert_tls_verification", original)
        code, payload, _, _ = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, "the mutation must reach the load, or the test above is decoration")
        self.assertTrue(payload["ok"])
        self.assertIn(self.LOADFILE, server.commands)
        self.assertIs(server.props["tls-verify"], False)


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
    def test_media_title_is_redacted_like_every_provider_string(self):
        # F-SINK-12 (review of the M5-01 round, pre-existing since M2-02):
        # media-title is the channel name the helper set through
        # --force-media-title, provider text, and it went out on stdout
        # verbatim. A name that carries a credentialed URL reaches the
        # sink as scheme and host only, like everything else the helper
        # prints.
        props = dict(STATUS_PROPS)
        props["media-title"] = "Sky One see http://user:s3cret@provider.example.test/live/tok/x.m3u8 now"
        self.start(props=props)
        code, payload, stdout, stderr = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["mediaTitle"], "Sky One see http://provider.example.test now")
        for secret in ("s3cret", "user:", "/live/", "tok", "x.m3u8"):
            self.assertNotIn(secret, stdout + stderr)

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
            # M5-01: the same for the rewind readout -- STATUS_PROPS carries
            # no time-pos, and "no position yet" is null, never zero.
            "rewind": None,
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
