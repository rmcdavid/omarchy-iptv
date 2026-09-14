"""Detached player tests for bin/omarchy-iptv (`player start|stop|restart|
probe|orphan-check`), against a stub mpv on PATH and a fake mpv on the socket.

No real mpv, no network, no window. The stub is a real process, so the /proc
scan, the pid re-verification and the stop ladder are exercised for real.

The shared vectors in tests/fixtures/player-argv.json are run here and by
tests/Model.test.js, which is what keeps the JavaScript and Python mirrors of
the launch argv, the stop ladder and the end-of-playback verdict from
drifting apart.

Run: python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import os
import pathlib
import re
import shutil
import signal
import socket
import stat
import subprocess
import tempfile
import threading
import time
import unittest

from helper_loader import load_helper
from test_mpv import FakeMpv

helper = load_helper()

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "player-argv.json"

# A credentialed URL, a token in the path and a password: the privacy sweep
# greps every recorded argv, every emitted line and the whole runtime dir for
# all three.
PASSWORD = "s3cr3t-pw"
TOKEN = "secret-token-XYZ"
PLAYLIST = """#EXTM3U
#EXTINF:-1 tvg-id="bbc1.uk" group-title="UK",BBC One HD
http://user:%s@provider.test/live/%s/bbc1.m3u8
#EXTINF:-1 tvg-id="espn.us" group-title="Sport",ESPN
#EXTVLCOPT:http-user-agent=VLC/3.0.20
#EXTVLCOPT:http-referrer=http://ref.test/
http://provider.test/live/espn.m3u8
""" % (PASSWORD, TOKEN)

# A stub mpv: records its own argv, then binds the socket and answers like
# mpv 0.41 (including the playlist_entry_id of a loadfile and the events that
# follow it). STUB_MPV_MODE picks the failure being tested.
STUB_MPV = '''#!/usr/bin/env python3
import json, os, socket, sys, threading, time

argv = sys.argv[1:]
record = os.environ.get("STUB_MPV_RECORD", "")
if record:
    with open(record, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(argv) + "\\n")
mode = os.environ.get("STUB_MPV_MODE", "serve")
load = os.environ.get("STUB_MPV_LOAD", "ok")
if mode == "nosocket":
    time.sleep(30)
    sys.exit(0)
path = ""
for arg in argv:
    if arg.startswith("--input-ipc-server="):
        path = arg.split("=", 1)[1]
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(path)
os.chmod(path, 0o600)
server.listen(8)
state = {"entry": 0, "url": "", "user_data": {}}


def handle(conn):
    buffer = b""
    while True:
        try:
            chunk = conn.recv(65536)
        except OSError:
            return
        if not chunk:
            return
        buffer += chunk
        while b"\\n" in buffer:
            line, buffer = buffer.split(b"\\n", 1)
            if not line.strip():
                continue
            message = json.loads(line.decode("utf-8"))
            if mode == "wedge":
                continue
            command = message.get("command") or [""]
            rid = message.get("request_id")
            name = command[0]
            events = []
            if name == "quit":
                os._exit(0)
            if name == "get_property":
                prop = command[1]
                if prop == "mpv-version":
                    reply = {"error": "success", "data": "mpv 0.41.0-stub", "request_id": rid}
                elif prop == "idle-active":
                    reply = {"error": "success", "data": state["entry"] == 0, "request_id": rid}
                elif prop == "pid":
                    reply = {"error": "success", "data": os.getpid(), "request_id": rid}
                elif prop.startswith("user-data/") and prop.split("/", 1)[1] in state["user_data"]:
                    reply = {"error": "success", "data": state["user_data"][prop.split("/", 1)[1]], "request_id": rid}
                else:
                    reply = {"error": "property not found", "request_id": rid}
            elif name == "set_property" and command[1].startswith("user-data/"):
                state["user_data"][command[1].split("/", 1)[1]] = command[2]
                reply = {"error": "success", "request_id": rid}
            elif name == "loadfile":
                state["entry"] += 1
                state["url"] = command[1]
                reply = {"error": "success", "data": {"playlist_entry_id": state["entry"]}, "request_id": rid}
                events.append({"event": "start-file", "playlist_entry_id": state["entry"]})
                if load == "ok":
                    events.append({"event": "file-loaded"})
                else:
                    events.append({"event": "log-message", "prefix": "stream", "level": "error",
                                   "text": "Failed to open %s.\\n" % state["url"]})
                    events.append({"event": "end-file", "reason": "error", "file_error": "loading failed",
                                   "playlist_entry_id": state["entry"]})
            else:
                reply = {"error": "success", "data": None, "request_id": rid}
            conn.sendall((json.dumps(reply) + "\\n").encode("utf-8"))
            for event in events:
                conn.sendall((json.dumps(event) + "\\n").encode("utf-8"))
            if load == "fail" and name == "loadfile":
                time.sleep(0.05)
                os._exit(2)          # --idle=once exits when the playlist ends


while True:
    try:
        conn, _ = server.accept()
    except OSError:
        break
    threading.Thread(target=handle, args=(conn,), daemon=True).start()
'''


def run(*args):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(args))
    lines = out.getvalue().strip().splitlines()
    payload = json.loads(lines[-1]) if lines else None
    return code, payload, out.getvalue(), err.getvalue()


def sleeper(token, ignore_term=False):
    """A real process carrying our --input-ipc-server token, so find_player
    and the ladder's pid re-verification have something true to work on."""
    code = "import signal, time\n"
    if ignore_term:
        code += "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    code += "time.sleep(30)\n"
    return subprocess.Popen(["python3", "-c", code, token],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wait_gone(process, timeout=6.0):
    """A killed child of this test process stays a zombie until it is reaped,
    and os.kill(pid, 0) succeeds on a zombie - so liveness is Popen.poll()
    here, and /proc/<pid>/cmdline (which a zombie no longer has) inside the
    helper. `process` may also be a bare pid we did not spawn."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if isinstance(process, int):
            try:
                os.kill(process, 0)
            except OSError:
                return True
        else:
            if process.poll() is not None:
                return True
        time.sleep(0.02)
    return False


class PlayerTestCase(unittest.TestCase):
    def setUp(self):
        # AF_UNIX paths are limited to ~108 bytes: keep the socket under /tmp.
        # (mpv fails completely silently when the path is too long or its
        # parent is missing - no socket, no message, not even at trace level.)
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-player-", dir="/tmp")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.runtime = os.path.join(self.dir, "run")
        self.sock = os.path.join(self.runtime, "mpv.sock")
        self.cache = os.path.join(self.dir, "cache")
        self.record = os.path.join(self.dir, "spawn-argv.jsonl")
        playlist = os.path.join(self.dir, "list.m3u")
        pathlib.Path(playlist).write_text(PLAYLIST, encoding="utf-8")
        code, _, _, stderr = run("playlist", "--url", playlist, "--cache-dir", self.cache)
        self.assertEqual(code, 0, stderr)
        self.bin = os.path.join(self.dir, "bin")
        os.makedirs(self.bin, 0o700)
        stub = os.path.join(self.bin, "mpv")
        pathlib.Path(stub).write_text(STUB_MPV, encoding="utf-8")
        os.chmod(stub, 0o755)
        self.env(PATH=self.bin + os.pathsep + os.environ.get("PATH", ""), STUB_MPV_RECORD=self.record)
        self.addCleanup(self.reap)
        self.server = None

    def env(self, **values):
        for name, value in values.items():
            old = os.environ.get(name)
            os.environ[name] = value
            self.addCleanup(self.restore_env, name, old)

    @staticmethod
    def restore_env(name, old):
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old

    def reap(self):
        for record in helper.find_player(self.sock):
            try:
                os.kill(record["pid"], signal.SIGKILL)
            except OSError:
                pass

    def sleeper(self, ignore_term=False):
        process = sleeper("--input-ipc-server=%s" % self.sock, ignore_term=ignore_term)
        self.addCleanup(self.reap_process, process)
        return process

    @staticmethod
    def reap_process(process):
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
        try:
            process.wait(timeout=5)
        except Exception:
            pass

    def start(self, **kwargs):
        self.server = FakeMpv(self.sock, **kwargs)
        self.addCleanup(self.server.close)
        return self.server

    def spawned_argv(self):
        if not os.path.exists(self.record):
            return []
        return [json.loads(line) for line in pathlib.Path(self.record).read_text(encoding="utf-8").splitlines() if line.strip()]

    def player_start(self, *args):
        return run("player", "start", "--socket", self.sock, "--cache-dir", self.cache,
                   "--id", "t:bbc1.uk", "--seq", "1", "--ipc-timeout", "1",
                   "--lock-timeout", "1", "--spawn-timeout", "4", "--first-load-timeout", "1", *args)


class StartTest(PlayerTestCase):
    def test_spawns_once_and_sends_the_whole_wire_sequence_in_order(self):
        os.makedirs(self.runtime, 0o755)      # the helper must tighten this to 0700
        code, payload, stdout, stderr = self.player_start("--scope", "g:uk", "--since", "1758000123", "--owner-pid", str(os.getpid()))
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stat.S_IMODE(os.stat(self.runtime).st_mode), 0o700)
        self.assertEqual(len(self.spawned_argv()), 1)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["kind"], "player.start")
        self.assertTrue(payload["spawned"])
        self.assertEqual(payload["id"], "t:bbc1.uk")
        self.assertEqual(payload["name"], "BBC One HD")
        self.assertEqual(payload["entryId"], 1)
        self.assertEqual(payload["seq"], 1)
        self.assertEqual(payload["firstLoad"]["state"], "playing")
        self.assertEqual(payload["warnings"], [])
        found = helper.find_player(self.sock)
        self.assertEqual(len(found), 1)
        self.assertEqual(payload["pid"], found[0]["pid"])
        # The order of the wire sequence is the contract (requirement 2/7):
        # title, force-media-title, all three header properties, the stash,
        # loadfile, the stash again with the entry id, the owner claim.
        client = helper.MpvIpc(self.sock, 1)
        client.connect()
        self.addCleanup(client.close)
        stash = client.command("get_property", helper.USER_DATA_STASH)
        owner = client.command("get_property", helper.USER_DATA_OWNER)
        self.assertEqual(stash["id"], "t:bbc1.uk")
        self.assertEqual(stash["name"], "BBC One HD")
        self.assertEqual(stash["group"], "UK")
        self.assertEqual(stash["launchedFrom"], "g:uk")
        self.assertEqual(stash["since"], 1758000123)
        self.assertEqual(stash["entryId"], 1)
        self.assertEqual(stash["seq"], 1)
        self.assertTrue(stash["playing"])
        self.assertEqual(owner["pid"], os.getpid())
        self.assertEqual(owner["startTime"], helper.proc_start_time(os.getpid()))

    def test_spawn_argv_carries_no_url_no_header_and_no_channel_name(self):
        # The S-03 regression net. This is the whole point of M2-02.
        code, payload, stdout, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        argv = self.spawned_argv()[0]
        joined = " ".join(argv)
        for secret in (PASSWORD, TOKEN, "user:", "provider.test", "://", "/live/", "VLC/3.0.20", "ref.test", "BBC One HD"):
            self.assertNotIn(secret, joined, secret)
        self.assertNotIn("--", argv, "the URL separator is gone with the URL")
        self.assertIn("--idle=once", argv)
        self.assertIn("--wayland-app-id=omarchy-iptv", argv)
        self.assertIn("--ytdl=no", argv)
        self.assertIn("--title=$>IPTV", argv)
        self.assertIn("--force-media-title=IPTV", argv)
        self.assertEqual(argv, helper.mpv_launch_argv(self.sock, [])[1:])

    def test_first_load_failure_is_reported_by_start_itself(self):
        # F3: a first channel that dies before any QML subscriber could exist
        # (an expired subscription, the commonest real failure) is not silent.
        self.env(STUB_MPV_LOAD="fail")
        code, payload, stdout, stderr = self.player_start("--first-load-timeout", "3")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["firstLoad"]["state"], "failed")
        self.assertIn("provider.test", payload["firstLoad"]["reason"])
        for secret in (PASSWORD, TOKEN, "/live/"):
            self.assertNotIn(secret, json.dumps(payload), secret)

    def test_user_mpv_args_are_filtered_and_reported(self):
        code, payload, _, stderr = self.player_start(
            "--mpv-arg=--profile=low-latency", "--mpv-arg=--log-file=/tmp/mpv.log",
            "--mpv-arg=--input-ipc-server=/tmp/evil.sock", "--mpv-arg=; rm -rf")
        self.assertEqual(code, 0, stderr)
        argv = self.spawned_argv()[0]
        self.assertIn("--profile=low-latency", argv)
        self.assertNotIn("--log-file=/tmp/mpv.log", argv)
        self.assertNotIn("--input-ipc-server=/tmp/evil.sock", argv)
        self.assertEqual(argv.count("--input-ipc-server=%s" % self.sock), 1)
        self.assertEqual(payload["warnings"], ["dropped mpvArg --log-file", "dropped mpvArg --input-ipc-server", "dropped mpvArg ; rm -rf"])

    def test_stash_carries_the_source_key_of_the_cache_directory(self):
        key = "a1b2c3d4"
        per_source = os.path.join(self.cache, "sources", key)
        os.makedirs(per_source, 0o700)
        shutil.copy(os.path.join(self.cache, "channels.json"), per_source)
        code, payload, _, stderr = run("player", "start", "--socket", self.sock, "--cache-dir", per_source,
                                       "--id", "t:bbc1.uk", "--seq", "2", "--ipc-timeout", "1",
                                       "--spawn-timeout", "4", "--first-load-timeout", "0.5")
        self.assertEqual(code, 0, stderr)
        client = helper.MpvIpc(self.sock, 1)
        client.connect()
        self.addCleanup(client.close)
        self.assertEqual(client.command("get_property", helper.USER_DATA_STASH)["sourceKey"], key)

    def test_unknown_channel_and_missing_cache_never_spawn(self):
        code, payload, _, _ = run("player", "start", "--socket", self.sock, "--cache-dir", self.cache,
                                  "--id", "t:nope", "--seq", "1")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "unknown_channel")
        code, payload, _, _ = run("player", "start", "--socket", self.sock,
                                  "--cache-dir", os.path.join(self.dir, "nowhere"), "--id", "t:bbc1.uk", "--seq", "1")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "no_cache")
        self.assertEqual(self.spawned_argv(), [])
        self.assertFalse(os.path.exists(self.sock))


class IdempotenceTest(PlayerTestCase):
    def test_a_live_player_is_adopted_and_zapped_never_duplicated(self):
        os.makedirs(self.runtime, 0o700)
        idle = self.sleeper()
        server = self.start(props={"mpv-version": "mpv 0.41.0"})
        code, payload, _, stderr = self.player_start("--scope", "g:uk")
        self.assertEqual(code, 0, stderr)
        self.assertFalse(payload["spawned"])
        self.assertEqual(payload["pid"], idle.pid)
        self.assertEqual(self.spawned_argv(), [], "a live player must never be duplicated")
        names = [command[:2] for command in server.commands]
        # The adoption check comes first, then the subscription - and the
        # subscription is before any load, which is F3's whole point.
        self.assertEqual(names[0], ["get_property", "mpv-version"])
        self.assertEqual(names[1], ["request_log_messages", "error"])
        order = [command[0] for command in server.commands]
        self.assertLess(order.index("request_log_messages"), order.index("loadfile"))
        self.assertEqual([command[:2] for command in server.commands if command[0] == "set_property"][:2],
                         [["set_property", "title"], ["set_property", "force-media-title"]])
        self.assertEqual(server.user_data["omarchy-iptv"]["entryId"], 1)

    def test_two_starts_in_a_row_spawn_once(self):
        for seq in ("1", "2"):
            code, payload, _, stderr = self.player_start("--seq", seq)
            self.assertEqual(code, 0, stderr)
        self.assertEqual(len(self.spawned_argv()), 1)
        self.assertEqual(len(helper.find_player(self.sock)), 1)


class SocketPathTest(PlayerTestCase):
    def test_stale_socket_is_unlinked_before_the_spawn(self):
        os.makedirs(self.runtime, 0o700)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(self.sock)
        listener.close()                      # the file stays, nobody listens
        before = os.stat(self.sock).st_ino
        code, payload, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["spawned"])
        self.assertNotEqual(os.stat(self.sock).st_ino, before)

    def test_a_regular_file_at_the_socket_path_blocks_and_never_spawns(self):
        os.makedirs(self.runtime, 0o700)
        pathlib.Path(self.sock).write_text("not a socket", encoding="utf-8")
        code, payload, _, _ = self.player_start()
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "socket_path_blocked")
        self.assertEqual(self.spawned_argv(), [])
        self.assertTrue(os.path.exists(self.sock))
        self.assertEqual(pathlib.Path(self.sock).read_text(encoding="utf-8"), "not a socket")


class LockTest(PlayerTestCase):
    def test_a_second_concurrent_start_reports_busy_and_never_spawns(self):
        os.makedirs(self.runtime, 0o700)
        held = helper.acquire_lock(helper.player_lock_path(self.sock), 1.0)
        self.addCleanup(helper.release_lock, held)
        code, payload, _, _ = self.player_start("--lock-timeout", "0.3")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "busy")
        self.assertEqual(self.spawned_argv(), [])

    def test_the_lock_file_being_replaced_mid_wait_is_detected_and_retried(self):
        os.makedirs(self.runtime, 0o700)
        path = helper.player_lock_path(self.sock)
        first = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        self.addCleanup(os.close, first)
        import fcntl
        fcntl.flock(first, fcntl.LOCK_EX)

        def replace():
            time.sleep(0.15)
            os.unlink(path)                   # defeats a plain flock
            os.close(os.open(path, os.O_CREAT | os.O_RDWR, 0o600))
            time.sleep(0.05)
            fcntl.flock(first, fcntl.LOCK_UN)

        thread = threading.Thread(target=replace, daemon=True)
        thread.start()
        fd = helper.acquire_lock(path, 3.0)
        self.addCleanup(helper.release_lock, fd)
        thread.join(3)
        self.assertEqual(os.fstat(fd).st_ino, os.stat(path).st_ino,
                         "the granted lock must protect the file that is at the path, not an orphaned inode")

    def test_an_older_intent_is_superseded_and_touches_nothing(self):
        os.makedirs(self.runtime, 0o700)
        fd = helper.acquire_lock(helper.player_lock_path(self.sock), 1.0)
        helper.write_lock_record(fd, 9, "start")
        helper.release_lock(fd)
        code, payload, _, _ = self.player_start("--seq", "3")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "superseded")
        self.assertEqual(self.spawned_argv(), [])
        self.assertFalse(helper.find_player(self.sock))
        self.assertEqual(helper.record_seq(helper.read_lock_file(self.sock)), 9)

    def test_the_lock_record_survives_for_the_probe_to_resume_the_sequence(self):
        code, _, _, stderr = self.player_start("--seq", "41")
        self.assertEqual(code, 0, stderr)
        code, payload, _, _ = run("player", "probe", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0)
        self.assertEqual(payload["seq"], 41)


class SpawnFailureTest(PlayerTestCase):
    def test_a_player_that_never_binds_is_reaped_by_the_helper_that_created_it(self):
        self.env(STUB_MPV_MODE="nosocket")
        code, payload, _, stderr = self.player_start("--spawn-timeout", "0.6")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "no_socket")
        self.assertEqual(len(self.spawned_argv()), 1)
        # Nothing windowed and uncontrollable may be left behind, or the next
        # start would multiply it.
        self.assertFalse(helper.find_player(self.sock))
        self.assertFalse(os.path.exists(self.sock))

    def test_a_missing_mpv_is_reported_through_the_errno_pipe(self):
        self.env(PATH=os.path.join(self.dir, "empty-bin"))
        os.makedirs(os.path.join(self.dir, "empty-bin"), 0o700)
        code, payload, _, _ = self.player_start("--spawn-timeout", "0.5")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "mpv_missing")


class LadderTest(PlayerTestCase):
    """The ladder with an injected clock: quit at 0, SIGTERM at 2 s, SIGKILL
    at 4 s, and never a signal to a pid that is no longer the player."""

    def clock(self):
        marks = []
        state = {"now": 1000.0}

        def monotonic():
            return state["now"]

        def sleep(seconds):
            if seconds > 0:
                state["now"] += seconds
                time.sleep(0.005)             # let the real process actually die

        original_monotonic, original_sleep = helper._monotonic, helper._sleep
        original_signal, original_quit = helper.signal_targets, helper.quit_over_ipc

        def record_signal(targets, path, number):
            marks.append((round(state["now"] - 1000.0, 2), number))
            return original_signal(targets, path, number)

        def record_quit(path, timeout):
            marks.append((round(state["now"] - 1000.0, 2), "quit"))
            return original_quit(path, timeout)

        helper._monotonic, helper._sleep = monotonic, sleep
        helper.signal_targets, helper.quit_over_ipc = record_signal, record_quit
        self.addCleanup(setattr, helper, "_monotonic", original_monotonic)
        self.addCleanup(setattr, helper, "_sleep", original_sleep)
        self.addCleanup(setattr, helper, "signal_targets", original_signal)
        self.addCleanup(setattr, helper, "quit_over_ipc", original_quit)
        return marks

    def test_quit_then_sigterm_at_2s_then_sigkill_at_4s(self):
        os.makedirs(self.runtime, 0o700)
        stubborn = self.sleeper(ignore_term=True)
        marks = self.clock()
        code, payload, _, stderr = run("player", "stop", "--socket", self.sock, "--seq", "5", "--ipc-timeout", "0.2")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["kind"], "player.stop")
        self.assertEqual(payload["rung"], "kill")
        self.assertFalse(payload["running"])
        self.assertEqual(payload["pid"], stubborn.pid)
        self.assertEqual([mark[1] for mark in marks], ["quit", signal.SIGTERM, signal.SIGKILL])
        self.assertEqual(marks[0][0], 0.0)
        self.assertAlmostEqual(marks[1][0], 2.0, delta=0.3)
        self.assertAlmostEqual(marks[2][0], 4.0, delta=0.3)
        self.assertTrue(wait_gone(stubborn))

    def test_from_term_skips_the_quit_rung(self):
        os.makedirs(self.runtime, 0o700)
        victim = self.sleeper()
        marks = self.clock()
        code, payload, _, stderr = run("player", "stop", "--socket", self.sock, "--seq", "6", "--from", "term", "--ipc-timeout", "0.2")
        self.assertEqual(code, 0, stderr)
        self.assertEqual([mark[1] for mark in marks], [signal.SIGTERM])
        self.assertEqual(payload["rung"], "term")
        self.assertTrue(wait_gone(victim))

    def test_nothing_running_is_a_clean_stop_that_unlinks_a_stale_socket(self):
        os.makedirs(self.runtime, 0o700)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(self.sock)
        listener.close()
        code, payload, _, stderr = run("player", "stop", "--socket", self.sock, "--seq", "7")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload, {"ok": True, "kind": "player.stop", "running": False, "rung": "", "pid": None})
        self.assertFalse(os.path.exists(self.sock))

    def test_a_recycled_pid_is_never_signalled(self):
        victim = self.sleeper()
        record = {"pid": victim.pid, "startTime": "999999999"}
        self.assertFalse(helper.still_the_player(record, self.sock))
        self.assertFalse(helper.signal_targets([record], self.sock, signal.SIGTERM))
        self.assertIsNone(victim.poll())
        # The same pid with its real start time is the player, and a process
        # without our socket token never is.
        real = {"pid": victim.pid, "startTime": helper.proc_start_time(victim.pid)}
        self.assertTrue(helper.still_the_player(real, self.sock))
        self.assertFalse(helper.still_the_player({"pid": os.getpid(), "startTime": ""}, self.sock))

    def test_stop_after_a_start_leaves_nothing_behind(self):
        code, _, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        pid = helper.find_player(self.sock)[0]["pid"]
        code, payload, _, stderr = run("player", "stop", "--socket", self.sock, "--seq", "2", "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertFalse(payload["running"])
        self.assertEqual(payload["rung"], "quit")
        self.assertTrue(wait_gone(pid))
        self.assertFalse(os.path.exists(self.sock))


class RestartTest(PlayerTestCase):
    def test_restart_ladders_the_old_player_down_and_spawns_under_one_lock(self):
        # The health verdict (two failed status polls). One lock acquisition,
        # ladder then spawn, so the stop/start race two detached calls would
        # have cannot happen.
        code, _, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        old = helper.find_player(self.sock)[0]["pid"]
        code, payload, _, stderr = run("player", "restart", "--socket", self.sock, "--cache-dir", self.cache,
                                       "--id", "t:espn.us", "--seq", "9", "--from", "term", "--ipc-timeout", "1",
                                       "--spawn-timeout", "4", "--first-load-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["kind"], "player.restart")
        self.assertTrue(payload["spawned"])
        self.assertEqual(payload["name"], "ESPN")
        self.assertEqual(payload["firstLoad"]["state"], "playing")
        self.assertTrue(wait_gone(old))
        found = helper.find_player(self.sock)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["pid"], payload["pid"])
        self.assertEqual(len(self.spawned_argv()), 2)

    def test_restart_sends_the_channel_headers_so_nothing_leaks_between_channels(self):
        os.makedirs(self.runtime, 0o700)
        idle = self.sleeper()
        server = self.start(props={"mpv-version": "mpv 0.41.0"})
        code, _, _, stderr = run("player", "start", "--socket", self.sock, "--cache-dir", self.cache,
                                 "--id", "t:espn.us", "--seq", "1", "--ipc-timeout", "1", "--first-load-timeout", "0.2")
        self.assertEqual(code, 0, stderr)
        sent = [command for command in server.commands if command[0] == "set_property"]
        self.assertIn(["set_property", "user-agent", "VLC/3.0.20"], sent)
        self.assertIn(["set_property", "referrer", "http://ref.test/"], sent)
        server.commands.clear()
        # A channel without headers actively resets the previous channel's:
        # requirement 7's clearing mechanism, now applied to the FIRST channel
        # too because it no longer gets its headers from argv.
        code, _, _, stderr = run("player", "start", "--socket", self.sock, "--cache-dir", self.cache,
                                 "--id", "t:bbc1.uk", "--seq", "2", "--ipc-timeout", "1", "--first-load-timeout", "0.2")
        self.assertEqual(code, 0, stderr)
        sent = [command for command in server.commands if command[0] == "set_property"]
        self.assertIn(["set_property", "user-agent", helper.MPV_DEFAULT_USER_AGENT], sent)
        self.assertIn(["set_property", "referrer", ""], sent)
        self.assertIn(["set_property", "http-header-fields", []], sent)
        self.assertIsNone(idle.poll())


class WedgedTest(PlayerTestCase):
    def test_a_socket_that_accepts_and_never_answers_is_not_responsive(self):
        os.makedirs(self.runtime, 0o700)
        idle = self.sleeper()
        self.start(silent=True)
        code, payload, _, stderr = run("player", "probe", "--socket", self.sock, "--ipc-timeout", "0.3")
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["running"])
        self.assertFalse(payload["responsive"])
        self.assertEqual(payload["pid"], idle.pid)

    def test_start_ladders_a_wedged_player_down_before_spawning(self):
        self.env(STUB_MPV_MODE="wedge")
        code, payload, _, stderr = self.player_start("--ipc-timeout", "0.3", "--spawn-timeout", "1")
        self.assertEqual(code, 1)          # the wedged stub never answers
        wedged = helper.find_player(self.sock)
        self.env(STUB_MPV_MODE="serve")
        code, payload, _, stderr = self.player_start("--seq", "2", "--ipc-timeout", "0.5", "--spawn-timeout", "4")
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["spawned"])
        self.assertEqual(len(helper.find_player(self.sock)), 1)
        for record in wedged:
            self.assertTrue(wait_gone(record["pid"]))


class ProbeTest(PlayerTestCase):
    def stash(self):
        return {"schema": 1, "playing": True, "id": "t:bbc1.uk", "name": "BBC One HD", "group": "UK",
                "launchedFrom": "g:uk", "sourceKey": "a1b2c3d4", "since": 1758000123, "entryId": 2, "seq": 41}

    def test_merges_the_proc_half_and_the_socket_half_and_never_reads_path(self):
        os.makedirs(self.runtime, 0o700)
        idle = self.sleeper()
        server = self.start(props={"mpv-version": "mpv 0.41.0", "idle-active": False,
                                   "path": "http://user:%s@provider.test/live/%s/bbc1.m3u8" % (PASSWORD, TOKEN),
                                   "media-title": "stale title"},
                            user_data={"omarchy-iptv": self.stash()})
        code, payload, stdout, stderr = run("player", "probe", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["running"])
        self.assertTrue(payload["responsive"])
        self.assertEqual(payload["pid"], idle.pid)
        self.assertIs(payload["idle"], False)
        self.assertEqual(payload["stash"], self.stash())
        self.assertIsNone(payload["owner"])
        self.assertFalse(payload["claimed"])
        asked = [command[1] for command in server.commands if command[0] == "get_property"]
        self.assertNotIn("path", asked)
        self.assertNotIn("media-title", asked)
        for secret in (PASSWORD, TOKEN, "/live/", "stale title"):
            self.assertNotIn(secret, stdout + stderr, secret)

    def test_the_owner_claim_is_written_only_with_owner_pid(self):
        os.makedirs(self.runtime, 0o700)
        idle = self.sleeper()
        server = self.start(props={"mpv-version": "mpv 0.41.0"})
        run("player", "probe", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertNotIn("omarchy-iptv-owner", server.user_data)
        code, payload, _, _ = run("player", "probe", "--socket", self.sock, "--ipc-timeout", "1", "--owner-pid", str(os.getpid()))
        self.assertEqual(code, 0)
        self.assertTrue(payload["claimed"])
        self.assertEqual(server.user_data["omarchy-iptv-owner"]["pid"], os.getpid())
        self.assertEqual(payload["owner"]["pid"], os.getpid())

    def test_nothing_running_is_reported_and_a_stale_socket_cleaned(self):
        os.makedirs(self.runtime, 0o700)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(self.sock)
        listener.close()
        code, payload, _, stderr = run("player", "probe", "--socket", self.sock)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["running"], False)
        self.assertEqual(payload["responsive"], False)
        self.assertIsNone(payload["pid"])
        self.assertIsNone(payload["stash"])
        self.assertFalse(os.path.exists(self.sock))


class OrphanCheckTest(PlayerTestCase):
    def setUpPlayer(self, claim_pid):
        os.makedirs(self.runtime, 0o700)
        idle = self.sleeper()
        user_data = {}
        if claim_pid is not None:
            user_data["omarchy-iptv-owner"] = {"schema": 1, "pid": claim_pid,
                                               "startTime": helper.proc_start_time(claim_pid), "at": 1758000100}
        self.start(props={"mpv-version": "mpv 0.41.0"}, user_data=user_data)
        return idle

    def test_a_claim_reassigned_to_a_successor_shell_is_a_no_op(self):
        idle = self.setUpPlayer(claim_pid=os.getpid())
        code, payload, _, stderr = run("player", "orphan-check", "--socket", self.sock,
                                       "--owner-pid", "424242", "--grace", "0", "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertFalse(payload["stopped"])
        self.assertEqual(payload["reason"], "reassigned")
        self.assertIsNone(idle.poll())

    def test_the_claim_still_ours_and_the_shell_alive_means_the_plugin_was_removed(self):
        idle = self.setUpPlayer(claim_pid=os.getpid())
        code, payload, _, stderr = run("player", "orphan-check", "--socket", self.sock,
                                       "--owner-pid", str(os.getpid()), "--grace", "0", "--ipc-timeout", "0.5")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["reason"], "owner_alive")
        self.assertTrue(payload["stopped"])
        self.assertTrue(wait_gone(idle))

    def test_the_claim_still_ours_and_the_shell_dead_never_kills_playback(self):
        dead = subprocess.Popen(["python3", "-c", "pass"])
        dead.wait()
        idle = self.setUpPlayer(claim_pid=None)
        self.server.user_data["omarchy-iptv-owner"] = {"schema": 1, "pid": dead.pid, "startTime": "1", "at": 1}
        code, payload, _, stderr = run("player", "orphan-check", "--socket", self.sock,
                                       "--owner-pid", str(dead.pid), "--grace", "0", "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertFalse(payload["stopped"])
        self.assertEqual(payload["reason"], "owner_dead")
        self.assertIsNone(idle.poll())


class PrivacyTest(PlayerTestCase):
    def test_nothing_in_the_runtime_dir_or_any_argv_or_any_line_carries_the_credential(self):
        self.env(STUB_MPV_LOAD="fail")
        code, start_payload, start_out, start_err = self.player_start("--scope", "g:uk", "--first-load-timeout", "2",
                                                                      "--owner-pid", str(os.getpid()))
        self.assertEqual(code, 0, start_err)
        self.assertEqual(start_payload["firstLoad"]["state"], "failed")
        code, _, stop_out, stop_err = run("player", "stop", "--socket", self.sock, "--seq", "2", "--ipc-timeout", "1")
        self.assertEqual(code, 0, stop_err)
        blob = start_out + start_err + stop_out + stop_err
        for argv in self.spawned_argv():
            blob += " ".join(argv)
        for path in pathlib.Path(self.runtime).rglob("*"):
            if path.is_file():
                blob += path.read_text(encoding="utf-8", errors="replace")
        for secret in (PASSWORD, TOKEN, "user:", "/live/", "bbc1.m3u8"):
            self.assertNotIn(secret, blob, secret)
        self.assertIn("provider.test", start_payload["firstLoad"]["reason"])
        self.assertTrue(re.fullmatch(r"[^/]*https?://provider\.test\.?", start_payload["firstLoad"]["reason"]) is not None
                        or "provider.test" in start_payload["firstLoad"]["reason"])


class ParityTest(unittest.TestCase):
    """The JS and Python mirrors, pinned by tests/fixtures/player-argv.json."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.model = (ROOT / "Model.js").read_text(encoding="utf-8")

    def test_mpv_reserved_matches_model_js(self):
        block = re.search(r"var MPV_RESERVED = \{(.*?)\n\}", self.model, re.S)
        self.assertIsNotNone(block)
        names = set(re.findall(r'"(--[a-z0-9-]+)":\s*true', block.group(1)))
        self.assertEqual(names, set(helper.MPV_RESERVED))
        self.assertEqual(names, set(self.fixture["mpvReserved"]))
        self.assertEqual(len(names), 19)
        self.assertNotIn("--ytdl", names)          # PO-5

    def test_generic_failure_text_matches(self):
        self.assertEqual(helper.PLAYER_GENERIC_FAILURE, self.fixture["genericFailure"])
        self.assertIn('var PLAYER_GENERIC_FAILURE = "%s"' % self.fixture["genericFailure"], self.model)

    def test_mpv_launch_argv_matches_every_shared_vector(self):
        for vector in self.fixture["mpvArgv"]:
            args, rejected = helper.filter_mpv_args(vector["mpvArgs"])
            self.assertEqual(helper.mpv_launch_argv(vector["socketPath"], args), vector["argv"], vector["name"])
            if "rejected" in vector:
                self.assertEqual(rejected, vector["rejected"], vector["name"])

    def test_the_launch_argv_never_carries_a_channel(self):
        argv = helper.mpv_launch_argv("/run/user/1000/omarchy-iptv/mpv.sock", [])
        self.assertNotIn("--", argv)
        self.assertEqual([token for token in argv if "://" in token], [])
        self.assertTrue(all(token.startswith("--") for token in argv[1:]))

    def test_stop_escalation_matches_every_shared_vector(self):
        for vector in self.fixture["stopLadder"]:
            self.assertEqual(helper.stop_escalation(vector["stage"]),
                             {"action": vector["action"], "signal": vector["signal"], "waitMs": vector["waitMs"]},
                             vector["name"])

    def test_ended_verdict_matches_every_shared_vector(self):
        for vector in self.fixture["endedVerdict"]:
            expected = vector.get("verdictPython", vector["verdict"])
            self.assertEqual(helper.ended_verdict(vector["endFile"], vector["userStopped"], vector["stopping"]),
                             expected, vector["name"])

    def test_the_four_tables_are_all_present_and_non_trivial(self):
        self.assertGreaterEqual(len(self.fixture["mpvArgv"]), 3)
        self.assertEqual(len(self.fixture["stopLadder"]), 5)
        self.assertGreaterEqual(len(self.fixture["endedVerdict"]), 12)
        # The session table is run by tests/test_state.py (normalize_state) and
        # by tests/Model.test.js (Model.parseState); this only guards the file.
        self.assertGreaterEqual(len(self.fixture["session"]), 10)


class IpcEventTest(unittest.TestCase):
    """The contained MpvIpc change: events a request steps over are kept."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-ipc-", dir="/tmp")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.sock = os.path.join(self.dir, "mpv.sock")
        self.server = FakeMpv(self.sock, props={"mpv-version": "mpv 0.41.0"}, event_first=True)
        self.addCleanup(self.server.close)

    def test_request_keeps_the_events_it_steps_over(self):
        client = helper.MpvIpc(self.sock, 1)
        client.connect()
        self.addCleanup(client.close)
        self.assertEqual(client.command("get_property", "mpv-version"), "mpv 0.41.0")
        self.assertEqual(client.events, [{"event": "start-file"}])
        drained = client.drain_events(time.monotonic() + 0.2)
        self.assertEqual(drained, [{"event": "start-file"}])
        self.assertEqual(client.events, [])

    def test_drain_events_waits_returns_empty_and_reports_a_close(self):
        client = helper.MpvIpc(self.sock, 1)
        client.connect()
        self.addCleanup(client.close)
        client.command("get_property", "mpv-version")
        client.drain_events(time.monotonic() + 0.2)
        self.assertEqual(client.drain_events(time.monotonic() + 0.1), [])
        self.server.inject({"event": "end-file", "reason": "error", "playlist_entry_id": 2, "file_error": "loading failed"})
        self.assertEqual(client.drain_events(time.monotonic() + 1.0),
                         [{"event": "end-file", "reason": "error", "playlist_entry_id": 2, "file_error": "loading failed"}])
        self.server.close()
        self.assertIsNone(client.drain_events(time.monotonic() + 1.0))
        self.assertTrue(client.closed)


if __name__ == "__main__":
    unittest.main()
