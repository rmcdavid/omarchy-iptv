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
mask = os.umask(0o022)
os.umask(mask)
record = os.environ.get("STUB_MPV_RECORD", "")
if record:
    with open(record, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"argv": argv, "cwd": os.getcwd(), "umask": mask}) + "\\n")
# PO-11: mpv's `s` key writes a screenshot with no explicit mode, into
# --screenshot-dir or, without one, the directory it was started in. Verified
# against real mpv 0.41; the stub must not be more forgiving (CLAUDE.md 10).
if os.environ.get("STUB_MPV_SHOT", ""):
    shot_dir = ""
    for arg in argv:
        if arg.startswith("--screenshot-dir="):
            shot_dir = arg.split("=", 1)[1]
    with open(os.path.join(shot_dir, "mpv-shot0001.jpg"), "wb") as handle:
        handle.write(b"\\xff\\xd8\\xff")
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
state = {"entry": 0, "url": "", "user_data": {}, "props": {}}


def orderly_exit(code):
    """Real mpv lets go of its IPC listener BEFORE the process goes away.

    Measured on mpv 0.41 on this machine, headless, 6/6: after a `quit` the
    connect is REFUSED 2.0-2.7 ms BEFORE /proc/<pid>/cmdline empties. After a
    SIGKILL it is the other way round - refused 2.7-4.9 ms AFTER the cmdline
    has already emptied (8/8), which is the D-PLY-8 window.

    This stub used to `os._exit()` with the listener still bound, which gave
    its quit path the kill path's asymmetry and only its tiny size kept that
    from showing. A double must never be more forgiving than the real thing
    (CLAUDE.md 10, audit F3). The linger makes the ordering observable
    instead of a race; real mpv's own is ~2 ms.
    """
    try:
        server.close()
    except OSError:
        pass
    time.sleep(float(os.environ.get("STUB_MPV_QUIT_LINGER", "0.01")))
    os._exit(code)


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
                orderly_exit(0)
            if name == "get_property":
                prop = command[1]
                if prop == "mpv-version":
                    # STUB_MPV_GATE withholds the handshake `player start`
                    # waits for, without withholding the socket - which is
                    # the one point where the two client slots really can be
                    # ordered against each other (D-PLY-11 T-B).
                    gate = os.environ.get("STUB_MPV_GATE", "")
                    while gate and not os.path.exists(gate):
                        time.sleep(0.005)
                    reply = {"error": "success", "data": "mpv 0.41.0-stub", "request_id": rid}
                elif prop == "idle-active":
                    reply = {"error": "success", "data": state["entry"] == 0, "request_id": rid}
                elif prop == "playlist-count":
                    # Real mpv 0.41, headless, confirmed: a newborn idle
                    # player answers 0, and `loadfile ... replace` leaves
                    # exactly one entry however many loads it has taken.
                    # `playlist/current/id` is NOT a property on this mpv
                    # (it answers "property not found"), so the stub does not
                    # grow one either - a double that answers what the real
                    # thing refuses is the forgiving kind CLAUDE.md 10 bans.
                    reply = {"error": "success", "data": 1 if state["entry"] else 0, "request_id": rid}
                elif prop == "pid":
                    reply = {"error": "success", "data": os.getpid(), "request_id": rid}
                elif prop == "path":
                    reply = {"error": "success", "data": state["url"], "request_id": rid}
                elif prop.startswith("user-data/") and prop.split("/", 1)[1] in state["user_data"]:
                    reply = {"error": "success", "data": state["user_data"][prop.split("/", 1)[1]], "request_id": rid}
                elif prop in state["props"]:
                    reply = {"error": "success", "data": state["props"][prop], "request_id": rid}
                else:
                    reply = {"error": "property not found", "request_id": rid}
            elif name == "set_property" and command[1].startswith("user-data/"):
                state["user_data"][command[1].split("/", 1)[1]] = command[2]
                reply = {"error": "success", "request_id": rid}
            elif name == "set_property":
                # Real mpv remembers what it was told; a double that forgets
                # cannot show which of two writers landed last.
                state["props"][command[1]] = command[2]
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
                orderly_exit(2)      # --idle=once exits when the playlist ends


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
    process = subprocess.Popen(["python3", "-c", code, token],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Installing SIG_IGN takes an interpreter start, and a rung that spends
    # none of its grace can deliver SIGTERM inside that window - which would
    # make the double DIE where the real wedged mpv it stands for survives
    # (CLAUDE.md 10). Wait for the mask rather than for a guessed delay.
    if ignore_term:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not ignores_term(process.pid):
            time.sleep(0.01)
    return process


# A double that owns BOTH identities the player is keyed on - the
# --input-ipc-server token on its own command line and the bound listening
# socket - and that can be held in the one state the shipping guards disagree
# about: blind to `find_player`, still answering `connect`.
#
# That state is what a SIGKILLed mpv leaves behind for a few milliseconds. The
# kernel's own version of it is measured, not modelled: on this machine, real
# headless mpv 0.41 empties its command line 0.13-0.31 ms after the SIGKILL
# and its socket is refused 2.7-4.9 ms later (8/8), while the shipping code
# asks both questions once, 4.5-7.5 ms in. A windowed player tears down
# slower still, which is why it reproduces in the field and not here.
#
# Reproducing the *duration* with a stand-in does not work on this box: with
# transparent huge pages on, a killed python process's window is 0.1-0.4 ms
# whatever its footprint (16 MB to 1024 MB), thread count (0 to 256) or
# descriptor count (0 to 65536) - measured, all flat. So the double sheds the
# /proc identity deliberately instead of waiting for the kernel: same pid,
# same bound socket, `exec` to a command line that no longer carries the
# token. The state is real and it lasts exactly as long as the test says.
#
# With SHED_ON_TERM it waits for a SIGTERM first, which is how a stop ladder
# reaches it: the rung reports the player gone the instant its command line
# stops matching, exactly as it does for a real signalled player, and the
# socket outlives that instant.
SHED_DOUBLE = '''#!/usr/bin/env python3
import os, signal, socket, sys, time

path = ""
for arg in sys.argv[1:]:
    if arg.startswith("--input-ipc-server="):
        path = arg.split("=", 1)[1]
server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(path)
os.chmod(path, 0o600)
server.listen(8)


def shed(*ignored):
    # Keep the descriptor across the exec: the socket stays bound to this
    # same pid while the command line the /proc scan keys on goes away.
    os.set_inheritable(server.fileno(), True)
    os.execv(sys.executable, [sys.executable, "-c",
                              "import os,sys,time; time.sleep(float(sys.argv[1])); os._exit(0)",
                              os.environ["SHED_HOLD"], "omarchy-iptv-test-socket-holder"])


if os.environ.get("SHED_ON_TERM") == "1":
    signal.signal(signal.SIGTERM, shed)
with open(os.environ["SHED_READY"], "w", encoding="utf-8") as handle:
    handle.write("1")
if os.environ.get("SHED_ON_TERM") == "1":
    time.sleep(60)
else:
    shed()
'''


def shed_double(token, hold_s, ready_path, on_term=False):
    """Start the double above. Returns once it has bound - and, unless it is
    waiting for a SIGTERM, once it has shed."""
    process = subprocess.Popen(["python3", "-c", SHED_DOUBLE, token],
                               env=dict(os.environ, SHED_READY=ready_path, SHED_HOLD=str(hold_s),
                                        SHED_ON_TERM="1" if on_term else "0"),
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline and not os.path.exists(ready_path):
        time.sleep(0.005)
    if on_term:
        return process
    # The exec is the last thing it does; wait for the command line to stop
    # carrying the token rather than for a guessed delay.
    while time.monotonic() < deadline:
        try:
            with open("/proc/%d/cmdline" % process.pid, "rb") as handle:
                if token.encode() not in handle.read().split(b"\0"):
                    break
        except OSError:
            break
        time.sleep(0.002)
    return process


def ignores_term(pid):
    """True once /proc/<pid>/status says SIGTERM is in the ignored mask."""
    try:
        for line in pathlib.Path("/proc/%d/status" % pid).read_text().splitlines():
            if line.startswith("SigIgn:"):
                return bool(int(line.split()[1], 16) & (1 << (signal.SIGTERM - 1)))
    except Exception:
        return False
    return False


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

    def shed_double(self, hold=0.4, on_term=False):
        """A process holding our socket bound with our token already gone
        from its command line - the state a just-SIGKILLed player leaves
        behind - for `hold` seconds. With `on_term` it carries the token
        until the ladder signals it, so a whole `player stop` can be driven
        through it."""
        os.makedirs(self.runtime, 0o700, exist_ok=True)
        process = shed_double("--input-ipc-server=%s" % self.sock, hold,
                              os.path.join(self.dir, "shed.ready"), on_term=on_term)
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

    def spawned_launches(self):
        """One record per exec: argv, the working directory it was given and
        the umask it inherited (PO-11)."""
        if not os.path.exists(self.record):
            return []
        return [json.loads(line) for line in pathlib.Path(self.record).read_text(encoding="utf-8").splitlines() if line.strip()]

    def spawned_argv(self):
        return [launch["argv"] for launch in self.spawned_launches()]

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

    def test_an_option_that_hands_the_url_to_another_program_is_kept_and_warned_about(self):
        # PO-10 / D-PLY-5. --ytdl is NOT reserved (PO-5): it reaches mpv, and
        # it also reaches the user as a warning on the line the guide shows.
        code, payload, _, stderr = self.player_start(
            "--mpv-arg=--ytdl=yes", "--mpv-arg=--ytdl-raw-options=proxy=http://u:pw@prox.test:8080",
            "--mpv-arg=--script-opts=ytdl_hook-ytdl_path=/tmp/mine", "--mpv-arg=--hwdec=auto-safe")
        self.assertEqual(code, 0, stderr)
        argv = self.spawned_argv()[0]
        self.assertIn("--ytdl=yes", argv)                       # kept, never refused
        self.assertLess(argv.index("--ytdl=no"), argv.index("--ytdl=yes"))
        self.assertEqual(payload["warnings"], [
            "mpvArg --ytdl" + helper.MPV_HANDOFF_TEXT,
            "mpvArg --ytdl-raw-options" + helper.MPV_HANDOFF_TEXT,
            "mpvArg --script-opts" + helper.MPV_HANDOFF_TEXT,
        ])
        # The warning is a sink: the value the user wrote may itself carry a
        # credentialed URL, and none of it may cross into the reply.
        blob = json.dumps(payload["warnings"])
        for secret in ("prox.test", "pw", "http://", "/tmp/mine"):
            self.assertNotIn(secret, blob, secret)

    def test_the_default_settings_warn_about_nothing(self):
        code, payload, _, stderr = self.player_start("--mpv-arg=--ytdl=no", "--mpv-arg=--profile=low-latency")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["warnings"], [])

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


class WorkingDirectoryTest(PlayerTestCase):
    """PO-11 / D-PLY-7: the player never inherits the shell's directory, and
    nothing it writes is world-readable.

    mpv's own key bindings are live on its window: `s` writes a screenshot and
    `Q` writes a resume record. Before this they landed in whatever directory
    the shell was started from - the user's home - at mode 0644.
    """

    def setUp(self):
        super().setUp()
        self.state = os.path.join(self.dir, "state")
        self.env(XDG_STATE_HOME=self.state)
        self.shots = os.path.join(self.state, "omarchy-iptv", "screenshots")
        self.later = os.path.join(self.runtime, "watch-later")
        self.shaders = os.path.join(self.runtime, "shader-cache")

    def test_the_player_is_given_a_directory_instead_of_inheriting_one(self):
        # The whole defect in one assertion: whatever the caller's directory
        # is, the player does not get it.
        self.assertNotEqual(os.getcwd(), self.runtime)
        code, _, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        launch = self.spawned_launches()[0]
        self.assertEqual(launch["cwd"], self.runtime)
        self.assertNotEqual(launch["cwd"], os.getcwd())
        self.assertNotEqual(launch["cwd"], os.path.expanduser("~"))
        # And the mode of anything it creates is settled before the exec.
        self.assertEqual(launch["umask"], 0o077)
        self.assertEqual(launch["umask"], helper.PLAYER_UMASK)

    def test_the_output_directories_are_named_on_argv_and_created_0700(self):
        self.assertFalse(os.path.exists(self.shots))
        code, payload, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        argv = self.spawned_argv()[0]
        self.assertIn("--screenshot-dir=%s" % self.shots, argv)
        self.assertIn("--watch-later-dir=%s" % self.later, argv)
        # mpv WOULD create a missing directory, but at 0755 - which is the
        # exposure being closed. The helper gets there first.
        for path in (self.shots, self.later):
            self.assertTrue(os.path.isdir(path), path)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o700, path)
        self.assertEqual(payload["warnings"], [])

    def test_the_shader_cache_is_contained_in_the_runtime_directory(self):
        """D-PLY-10 / CL2. mpv compiles its shaders into $XDG_CACHE_HOME/mpv/
        otherwise - two files at 0600 per containment cycle, outside every
        list of files this plugin says it writes. The cache is content-free
        and regenerable, so it goes in the runtime directory: 0700 already,
        documented already, gone at logout, and it adds no durable path and
        nothing to clean up at uninstall.

        What this proves is that the argv is built and the directory exists
        at the right mode. That mpv actually honours the option instead of
        writing to ~/.cache/mpv needs a GPU video output, which needs a
        window, which belongs to the display lane.
        """
        cache_home = os.path.join(self.dir, "xdg-cache")
        self.env(XDG_CACHE_HOME=cache_home)
        code, payload, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        argv = self.spawned_argv()[0]
        self.assertIn("--gpu-shader-cache-dir=%s" % self.shaders, argv)
        self.assertIn("--icc-cache-dir=%s" % self.shaders, argv)
        self.assertTrue(os.path.isdir(self.shaders))
        self.assertEqual(stat.S_IMODE(os.stat(self.shaders).st_mode), 0o700)
        self.assertEqual(payload["warnings"], [])
        # Ephemeral by ruling: under the runtime directory, never under the
        # state directory the plugin has to clean up, and never in the
        # user's cache.
        self.assertTrue(self.shaders.startswith(self.runtime + os.sep))
        self.assertFalse(self.shaders.startswith(self.state))
        self.assertFalse(os.path.exists(os.path.join(cache_home, "mpv")))

    def test_neither_cache_option_is_reserved_so_a_user_token_still_wins(self):
        # CL2: MPV_RESERVED is a privacy instrument - --watch-later-dir is on
        # it because a resume record names a stream path. A content-free
        # shader cache is not that, so containment here is a default, not a
        # guarantee, and the user's own token lands after ours.
        mine = os.path.join(self.dir, "my-shaders")
        code, payload, _, stderr = self.player_start("--mpv-arg=--gpu-shader-cache-dir=%s" % mine,
                                                     "--mpv-arg=--icc-cache-dir=%s" % mine)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["warnings"], [])
        argv = self.spawned_argv()[0]
        self.assertLess(argv.index("--gpu-shader-cache-dir=%s" % self.shaders),
                        argv.index("--gpu-shader-cache-dir=%s" % mine))
        self.assertLess(argv.index("--icc-cache-dir=%s" % self.shaders),
                        argv.index("--icc-cache-dir=%s" % mine))
        self.assertNotIn("--gpu-shader-cache-dir", helper.MPV_RESERVED)
        self.assertNotIn("--icc-cache-dir", helper.MPV_RESERVED)

    def test_a_screenshot_lands_in_the_documented_directory_at_0600(self):
        self.env(STUB_MPV_SHOT="1")
        code, _, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        shot = os.path.join(self.shots, "mpv-shot0001.jpg")
        self.assertTrue(os.path.exists(shot), "the screenshot is where the README says it is")
        self.assertEqual(stat.S_IMODE(os.stat(shot).st_mode), 0o600)
        self.assertEqual(os.listdir(self.runtime),
                         [name for name in os.listdir(self.runtime) if not name.startswith("mpv-shot")])
        self.assertEqual([name for name in os.listdir(self.dir) if name.startswith("mpv-shot")], [])

    def test_the_screenshot_directory_can_still_be_pointed_somewhere_else(self):
        # --screenshot-dir is deliberately NOT reserved: user tokens land
        # after the fixed options, so a deliberate choice still wins.
        mine = os.path.join(self.dir, "mine")
        os.makedirs(mine, 0o700)
        self.env(STUB_MPV_SHOT="1")
        code, _, _, stderr = self.player_start("--mpv-arg=--screenshot-dir=%s" % mine)
        self.assertEqual(code, 0, stderr)
        argv = self.spawned_argv()[0]
        self.assertLess(argv.index("--screenshot-dir=%s" % self.shots), argv.index("--screenshot-dir=%s" % mine))
        self.assertTrue(os.path.exists(os.path.join(mine, "mpv-shot0001.jpg")))

    def test_the_watch_later_directory_cannot_be_pointed_back_at_home(self):
        # A resume record names a stream path, so --watch-later-dir stays
        # reserved and the user's token is dropped with the existing warning.
        code, payload, _, stderr = self.player_start("--mpv-arg=--watch-later-dir=%s" % self.dir)
        self.assertEqual(code, 0, stderr)
        self.assertIn("dropped mpvArg --watch-later-dir", payload["warnings"])
        self.assertEqual([t for t in self.spawned_argv()[0] if t.startswith("--watch-later-dir=")],
                         ["--watch-later-dir=%s" % self.later])

    def test_a_directory_that_cannot_be_created_warns_and_still_plays(self):
        # "What happens when it does not exist" has a second half: what
        # happens when it cannot be made. Never a refused play.
        blocked = os.path.join(self.dir, "blocked")
        pathlib.Path(blocked).write_text("not a directory", encoding="utf-8")
        self.env(XDG_STATE_HOME=blocked)
        code, payload, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["warnings"]), 1)
        self.assertIn("could not create", payload["warnings"][0])
        self.assertIn("screenshots", payload["warnings"][0])


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


def token_gone(pid, token):
    """What find_player's predicate reduces to for one known pid, without the
    4-5 ms /proc scan - so a sampling loop can resolve tenths of a
    millisecond instead of tens."""
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as handle:
            return token.encode() not in handle.read().split(b"\0")
    except OSError:
        return True


def watch_teardown(pid, token, sock_path, budget=5.0):
    """When did each of the two guards change its mind? Returns the offsets
    in seconds from now, first for the /proc side and then for the socket."""
    start = time.monotonic()
    blind = unbound = None
    while time.monotonic() - start < budget and (blind is None or unbound is None):
        if blind is None and token_gone(pid, token):
            blind = time.monotonic() - start
        if unbound is None and helper.socket_is_dead(sock_path):
            unbound = time.monotonic() - start
    return blind, unbound


class DoubleTest(PlayerTestCase):
    """The doubles themselves (CLAUDE.md 10, audit F3).

    These do not test the product. They test that the stand-ins this file
    drives the product against are not more forgiving than mpv, because two
    of this round's items turn on exactly when a dying player stops being
    visible and when it stops being reachable.
    """

    def test_the_quit_path_lets_go_of_the_socket_before_the_command_line_empties(self):
        # Real mpv 0.41, headless, this machine: on `quit` the connect is
        # refused 2.0-2.7 ms BEFORE the cmdline empties, 6/6. On SIGKILL it
        # is refused 2.7-4.9 ms AFTER, 8/8. The stub used to _exit with its
        # listener still bound, giving its quit path the kill path's
        # ordering - the one asymmetry D-PLY-8 is about.
        self.env(STUB_MPV_QUIT_LINGER="0.25")
        code, _, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        pid = helper.find_player(self.sock)[0]["pid"]
        token = "--input-ipc-server=%s" % self.sock
        # Sent raw, not through quit_over_ipc: that one waits for the
        # connection to close, which is the very event being timed.
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(2.0)
        client.connect(self.sock)
        self.addCleanup(client.close)
        client.sendall(b'{"command":["quit"],"request_id":1}\n')
        blind, unbound = watch_teardown(pid, token, self.sock)
        self.assertIsNotNone(blind, "the double never went away")
        self.assertIsNotNone(unbound, "the double never let go of the socket")
        self.assertLess(unbound, blind,
                        "an orderly quit must drop the listener first: real mpv does")
        self.assertTrue(wait_gone(pid))
        # And mpv never unlinks its own socket on any exit path, so the file
        # is still there for the settle to deal with.
        self.assertTrue(os.path.exists(self.sock))

    def test_a_double_can_hold_the_state_a_killed_player_leaves_behind(self):
        # Blind to the /proc scan, still answering connect(), one pid, both
        # identities. Held for as long as the test needs instead of for as
        # long as the kernel happens to take - the duration is not
        # reproducible with a stand-in on this box (a killed python process's
        # window is 0.1-0.4 ms at 16 MB and at 1024 MB alike, transparent
        # huge pages being on), but the state is exactly the real one.
        process = self.shed_double(hold=0.35)
        self.assertEqual(helper.find_player(self.sock), [],
                         "the /proc scan must be blind to it")
        self.assertFalse(helper.socket_is_dead(self.sock),
                         "and its socket must still be bound")
        self.assertTrue(os.path.exists(self.sock))
        self.assertTrue(wait_gone(process, timeout=5.0))
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not helper.socket_is_dead(self.sock):
            time.sleep(0.005)
        self.assertTrue(helper.socket_is_dead(self.sock), "and then it lets go")
        self.assertTrue(os.path.exists(self.sock), "without unlinking the file")


class LadderTest(PlayerTestCase):
    """The ladder with an injected clock: quit at 0, SIGTERM at 2 s, SIGKILL
    at 4 s, and never a signal to a pid that is no longer the player."""

    def clock(self, quit_cost=0.0):
        """`quit_cost` is what the quit rung's own IPC attempt costs before
        the ladder waits for anything: 0 for a player that answers (or a
        socket that is not there at all), the full --ipc-timeout for a wedged
        one, which is the D-PLY-6 case."""
        marks = []
        state = {"now": 1000.0}
        self.clock_state = state

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
            result = original_quit(path, timeout)
            state["now"] += quit_cost         # an unresponsive player: no answer, no exception
            return result

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

    def test_a_wedged_players_quit_wait_does_not_push_the_ladder_past_its_budget(self):
        # D-PLY-6. Against a player that is not answering, `request(["quit"])`
        # spends the whole --ipc-timeout before the ladder waits for
        # anything, and that cost used to sit OUTSIDE the 2 s grace: SIGTERM
        # arrived at 4 s, SIGKILL at 6 s, and a wedged player took ~6.27 s to
        # reap (6258 / 6265 / 6269 / 6276 ms, live) against a 4.5 s budget.
        # Each rung's grace is measured from the rung's own start, so the
        # timeline is the one the README and section 4.9 describe.
        os.makedirs(self.runtime, 0o700)
        stubborn = self.sleeper(ignore_term=True)
        marks = self.clock(quit_cost=2.0)
        code, payload, _, stderr = run("player", "stop", "--socket", self.sock, "--seq", "5", "--ipc-timeout", "2")
        self.assertEqual(code, 0, stderr)
        self.assertEqual([mark[1] for mark in marks], ["quit", signal.SIGTERM, signal.SIGKILL])
        self.assertEqual(marks[0][0], 0.0)
        self.assertAlmostEqual(marks[1][0], 2.0, delta=0.3)     # was 4.0
        self.assertAlmostEqual(marks[2][0], 4.0, delta=0.3)     # was 6.0
        elapsed = self.clock_state["now"] - 1000.0
        self.assertLessEqual(elapsed, 4.5, "the ladder must finish inside its 4.5 s budget")
        self.assertEqual(payload["rung"], "kill")
        self.assertFalse(payload["running"])
        self.assertTrue(wait_gone(stubborn))

    def test_a_responsive_player_still_gets_a_clean_quit_and_the_whole_grace(self):
        # The other half of D-PLY-6: counting the IPC cost inside the grace
        # must not cost a player that answers. It is asked politely first and
        # still has the full two seconds to go, which is about six times what
        # one has ever needed (273-331 ms measured).
        os.makedirs(self.runtime, 0o700)
        victim = self.sleeper()
        marks = self.clock(quit_cost=0.01)
        code, payload, _, stderr = run("player", "stop", "--socket", self.sock, "--seq", "8", "--ipc-timeout", "2")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(marks[0][1], "quit")
        self.assertEqual(marks[0][0], 0.0)
        # The sleeper ignores `quit` (it has no socket), so SIGTERM follows -
        # and it follows at 2 s, with the grace spent waiting rather than
        # dialling.
        self.assertEqual(marks[1][1], signal.SIGTERM)
        self.assertAlmostEqual(marks[1][0], 2.0, delta=0.3)
        self.assertTrue(wait_gone(victim))

    def test_from_term_skips_the_quit_rung(self):
        os.makedirs(self.runtime, 0o700)
        victim = self.sleeper()
        marks = self.clock()
        code, payload, _, stderr = run("player", "stop", "--socket", self.sock, "--seq", "6", "--from", "term", "--ipc-timeout", "0.2")
        self.assertEqual(code, 0, stderr)
        self.assertEqual([mark[1] for mark in marks], [signal.SIGTERM])
        self.assertEqual(payload["rung"], "term")
        self.assertTrue(wait_gone(victim))

    def test_the_deadline_it_hands_on_is_the_kill_rungs_own_unspent_window(self):
        # D-PLY-8. The kill rung reserves 500 ms (stop_escalation("term")
        # gives waitMs 0, so grace falls back to STOP_SETTLE_MS) and spends
        # almost none of it: wait_for_exit checks before it sleeps and a
        # SIGKILLed process is gone at the first check. That unspent window
        # is what the settle gets - it is never a fresh budget on top.
        os.makedirs(self.runtime, 0o700)
        stubborn = self.sleeper(ignore_term=True)
        marks = self.clock()
        result = helper.stop_ladder(self.sock, helper.find_player(self.sock), "", 0.2)
        self.assertEqual(result["rung"], "kill")
        self.assertFalse(result["running"])
        killed_at = 1000.0 + marks[-1][0]
        self.assertIsNotNone(result["deadline"])
        self.assertGreater(result["deadline"], killed_at)
        self.assertLessEqual(result["deadline"], killed_at + helper.STOP_SETTLE_MS / 1000.0)
        # And nearly all of it is still ahead of the settle.
        self.assertGreaterEqual(result["deadline"] - self.clock_state["now"], 0.3)
        self.assertTrue(wait_gone(stubborn))

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


class SettleTest(PlayerTestCase):
    """D-PLY-8: the socket file left behind by a wedged stop.

    The blocking guard is socket_is_dead, not find_player. A SIGKILLed
    process runs exit_mm first, so its command line is empty at the first
    sample (0.13-0.31 ms, 8/8 on real headless mpv 0.41 here) while its
    listening socket stays bound for another 2.7-4.9 ms - longer for a
    windowed player. The stop path looks 4.5-7.5 ms after the kill: one
    /proc scan (3.7-4.9 ms for 225 pids here) after wait_for_exit returns.
    One look each, and "not yet" was final.

    These cases drive the two guards directly, so nothing here depends on
    what the kernel happens to do while they run.
    """

    def stale_socket(self):
        os.makedirs(self.runtime, 0o700, exist_ok=True)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(self.sock)
        listener.close()
        self.assertTrue(os.path.exists(self.sock))

    def guards(self, found, dead, connect_cost=0.0):
        """Successive answers for each guard (the last one repeats), on an
        injected clock - the LadderTest pattern. `connect_cost` is what one
        connect() costs the clock: 0 for a refused or accepted one, the full
        MpvIpc timeout for one that times out.
        """
        state = {"now": 1000.0, "finds": 0, "connects": 0}
        self.clock_state = state
        originals = {name: getattr(helper, name)
                     for name in ("_monotonic", "_sleep", "find_player", "socket_is_dead")}
        for name, value in originals.items():
            self.addCleanup(setattr, helper, name, value)

        def pick(script, index):
            return script[min(index, len(script) - 1)]

        def fake_find(path):
            answer = pick(found, state["finds"])
            state["finds"] += 1
            return [{"pid": 424242, "startTime": "1"}] if answer else []

        def fake_dead(path):
            answer = pick(dead, state["connects"])
            state["connects"] += 1
            state["now"] += connect_cost
            return answer

        def sleep(seconds):
            if seconds > 0:
                state["now"] += seconds

        helper._monotonic = lambda: state["now"]
        helper._sleep = sleep
        helper.find_player = fake_find
        helper.socket_is_dead = fake_dead
        return state

    def test_the_socket_is_unlinked_once_both_guards_agree_and_not_before(self):
        # Red before this change for a tautological reason - settle_socket
        # took no deadline at all and looked once by construction. It says
        # nothing about how wide the kernel's window is; that is measured,
        # not asserted here.
        self.stale_socket()
        state = self.guards(found=[False], dead=[False, False, True])
        self.assertTrue(helper.settle_socket(self.sock, deadline=1000.5))
        self.assertFalse(os.path.exists(self.sock))
        self.assertEqual(state["connects"], 3)
        # Both guards, every iteration: the finder is what aborts the loop
        # when a start races us, so it can never be asked less often.
        self.assertEqual(state["finds"], 3)
        self.assertLessEqual(state["now"], 1000.5)

    def test_a_successful_connect_keeps_blocking_it_for_the_whole_wait(self):
        # A wedged player answering through its listen backlog. The guard
        # gets this right today and must keep getting it right: the re-check
        # may never widen the conditions, only re-evaluate them.
        self.stale_socket()
        state = self.guards(found=[False], dead=[False])
        self.assertFalse(helper.settle_socket(self.sock, deadline=1000.5))
        self.assertTrue(os.path.exists(self.sock))
        self.assertGreater(state["connects"], 1, "it really did re-check")
        self.assertLessEqual(state["now"] - 1000.0, 0.5)

    def test_a_timed_out_connect_blocks_it_too_and_overruns_by_one_at_most(self):
        # socket_is_dead is False for a successful connect AND for one that
        # times out - only ECONNREFUSED or a missing path make it True. A
        # timed-out connect costs the 0.2 s MpvIpc timeout, which is the
        # whole worst-case latency argument: the loop can overrun its
        # deadline by one of those and by nothing more.
        self.stale_socket()
        state = self.guards(found=[False], dead=[False], connect_cost=0.2)
        self.assertFalse(helper.settle_socket(self.sock, deadline=1000.5))
        self.assertTrue(os.path.exists(self.sock))
        self.assertLessEqual(round(state["now"] - 1000.0, 6), 0.5 + 0.2)

    def test_a_player_the_finder_can_see_aborts_the_loop_at_once(self):
        # A racing start. Never a wait, never an unlink - the file belongs to
        # a live player and the lock we hold is what stops it appearing
        # between the check and the unlink.
        self.stale_socket()
        state = self.guards(found=[True], dead=[True])
        self.assertFalse(helper.settle_socket(self.sock, deadline=1000.5))
        self.assertTrue(os.path.exists(self.sock))
        self.assertEqual([state["finds"], state["connects"]], [1, 0])
        self.assertEqual(state["now"], 1000.0)

    def test_without_a_deadline_it_behaves_exactly_as_it_always_did(self):
        # The seven call sites that are not the post-ladder settle pass no
        # deadline, so this is what they get: one look at each guard, no
        # sleep, same answer as before.
        self.stale_socket()
        state = self.guards(found=[False], dead=[False])
        self.assertFalse(helper.settle_socket(self.sock))
        self.assertTrue(os.path.exists(self.sock))
        self.assertEqual([state["finds"], state["connects"]], [1, 1])
        self.assertEqual(state["now"], 1000.0)

    def test_a_socket_still_bound_by_a_process_the_finder_cannot_see(self):
        """The defect itself, with a real process and the shipping guards.

        The double holds the exact state a just-SIGKILLed player leaves
        behind - blind to the /proc scan, still accepting connections - so
        this is deterministic where the field case is a few milliseconds
        wide. What it does not claim is that the field window is this long:
        the kernel's own is measured (2.7-4.9 ms headless), not modelled.
        """
        self.shed_double(hold=0.35)
        self.assertEqual(helper.find_player(self.sock), [])
        self.assertFalse(helper.socket_is_dead(self.sock))
        # One look, which is what the code did: "not yet", and the file stays
        # until some later helper call happens to clean it up.
        self.assertFalse(helper.settle_socket(self.sock))
        self.assertTrue(os.path.exists(self.sock))
        # Look again inside the window the kill rung already owns and it is
        # gone, with time to spare.
        started = time.monotonic()
        budget = helper.STOP_SETTLE_MS / 1000.0
        self.assertTrue(helper.settle_socket(self.sock, deadline=started + budget))
        self.assertFalse(os.path.exists(self.sock))
        self.assertLess(time.monotonic() - started, budget)

    def test_a_stop_whose_player_outlives_its_own_command_line_still_settles(self):
        """The whole path, through the real `player stop` verb.

        The double carries the token until the ladder signals it, then sheds
        it while keeping the socket bound - which is what a signalled player
        does, in the order a signalled player does it. The ladder therefore
        reports the player gone (its command line no longer matches) while
        the socket is still listening, which is the D-PLY-8 instant, and the
        settle has to look again to get it right.
        """
        self.shed_double(hold=0.3, on_term=True)
        self.assertEqual(len(helper.find_player(self.sock)), 1)
        started = time.monotonic()
        code, payload, _, stderr = run("player", "stop", "--socket", self.sock, "--seq", "3",
                                       "--from", "term", "--ipc-timeout", "0.2")
        spent = time.monotonic() - started
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["rung"], "term")
        self.assertFalse(payload["running"])
        self.assertFalse(os.path.exists(self.sock), "the socket file must not be left behind")
        # Inside the rung's own window, not on top of it: the term rung
        # reserves 2 s and the wait for the socket came out of that.
        self.assertLess(spent, helper.STOP_KILL_GRACE_MS / 1000.0)

    def test_the_settle_that_holds_no_lock_of_its_own_takes_one(self):
        # X1/X2, ruling CL8. player_probe and player_orphan_check settle
        # outside any lock, so a start that binds a fresh socket between the
        # refused connect and the unlink would have the NEW socket deleted.
        self.stale_socket()
        self.assertTrue(helper.settle_under_lock(self.sock))
        self.assertFalse(os.path.exists(self.sock))
        self.assertTrue(os.path.exists(helper.player_lock_path(self.sock)))

    def hold_the_player_lock(self):
        """Stand in for another verb being mid-flight. flock is per open file
        description, so a second open in this same process really does
        contend - which is what the helper's own acquire_lock will meet."""
        os.makedirs(self.runtime, 0o700, exist_ok=True)
        held = helper.acquire_lock(helper.player_lock_path(self.sock), 1.0)
        self.addCleanup(helper.release_lock, held)
        return held

    def test_a_probe_will_not_unlink_a_socket_while_another_verb_holds_the_lock(self):
        # X2 / CL8, at the call site rather than in the function. The probe
        # is the reattach read and runs at every service start, so it is the
        # one most likely to be racing a start.
        self.stale_socket()
        self.hold_the_player_lock()
        code, payload, _, stderr = run("player", "probe", "--socket", self.sock, "--ipc-timeout", "0.2")
        self.assertEqual(code, 0, stderr)
        self.assertFalse(payload["running"])
        self.assertTrue(os.path.exists(self.sock),
                        "the unlink needs the lock, and somebody else has it")

    def test_a_probe_with_the_lock_free_still_cleans_a_stale_socket_up(self):
        # The other half: locking it must not turn the cleanup off.
        self.stale_socket()
        code, payload, _, stderr = run("player", "probe", "--socket", self.sock, "--ipc-timeout", "0.2")
        self.assertEqual(code, 0, stderr)
        self.assertFalse(payload["running"])
        self.assertFalse(os.path.exists(self.sock))

    def test_an_orphan_check_will_not_unlink_a_socket_while_another_verb_holds_the_lock(self):
        # X1 / CL8. This one reaps the player first, so by the time it
        # settles the socket really is stale - and unlinking it without the
        # lock is exactly how a start that bound a fresh socket in between
        # loses it.
        code, _, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        code, _, _, stderr = run("player", "probe", "--socket", self.sock,
                                 "--owner-pid", str(os.getpid()), "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.hold_the_player_lock()
        code, payload, _, stderr = run("player", "orphan-check", "--socket", self.sock,
                                       "--owner-pid", str(os.getpid()), "--grace", "0", "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["reason"], "owner_alive")
        self.assertTrue(payload["stopped"])
        self.assertTrue(os.path.exists(self.sock),
                        "the player is gone, but the unlink still needs the lock")

    def test_an_orphan_check_with_the_lock_free_leaves_nothing_behind(self):
        code, _, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        code, _, _, stderr = run("player", "probe", "--socket", self.sock,
                                 "--owner-pid", str(os.getpid()), "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        code, payload, _, stderr = run("player", "orphan-check", "--socket", self.sock,
                                       "--owner-pid", str(os.getpid()), "--grace", "0", "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["stopped"])
        self.assertFalse(os.path.exists(self.sock))

    def test_a_settle_that_cannot_take_the_lock_does_not_unlink(self):
        # Somebody else is mid-verb: their socket, their settle. A probe is
        # not worth failing over a leftover file either, so it just reports.
        self.stale_socket()
        held = helper.acquire_lock(helper.player_lock_path(self.sock), 1.0)
        self.addCleanup(helper.release_lock, held)
        self.assertFalse(helper.settle_under_lock(self.sock, lock_timeout=0.1))
        self.assertTrue(os.path.exists(self.sock))


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

    def test_the_probe_emits_the_pid_key_the_shell_addresses_the_window_by(self):
        # M2-05. The service takes the window-owning mpv pid from here and
        # refuses picture in picture without it, because addressing by class
        # alone would float, shrink, move and pin a stranger's
        # `mpv --wayland-app-id=omarchy-iptv` (PLY-RST-11). It reads the value
        # DEFENSIVELY - anything not a positive integer is ignored - so a
        # helper that dropped or renamed this key would raise nothing at all:
        # the pid would stay 0 and `p` would answer "Nothing playing" over a
        # channel that is plainly playing.
        #
        # The shared vector is what closes that: the key set asserted here is
        # the object tests/Model.test.js runs the parser over, so a rename on
        # either side of the JS/Python boundary turns both suites red.
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))["playerProbe"]
        os.makedirs(self.runtime, 0o700)
        idle = self.sleeper()
        self.start(props={"mpv-version": "mpv 0.41.0", "idle-active": False},
                   user_data={"omarchy-iptv": self.stash()})
        code, payload, _, stderr = run("player", "probe", "--socket", self.sock,
                                       "--ipc-timeout", "1", "--owner-pid", str(os.getpid()))
        self.assertEqual(code, 0, stderr)
        self.assertEqual(sorted(payload), sorted(fixture["keys"]))
        self.assertEqual(payload["pid"], idle.pid)
        self.assertIs(type(payload["pid"]), int)
        # And the vector the parser is fed is the same document, key for key.
        self.assertEqual(sorted(fixture["reply"]), sorted(fixture["keys"]))
        self.assertEqual(fixture["parsed"]["pid"], fixture["reply"]["pid"])

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


class OrderingTest(PlayerTestCase):
    """D-PLY-11. Written as characterisation, kept as the repair's evidence.

    The cause is no longer a hypothesis. Wave two measured it on a real shell
    (docs/QA-RESULTS.md D1, ruling CL9): ten user-visible divergences in
    twenty COLD concurrent bursts, none in ten warm bursts, none in six cold
    serial runs, and in every cold run exactly one `player start` carrying
    the burst's FIRST intent while a later change reached the socket ahead of
    it. Two orderings were on the table and they are no longer equal:

      T-A  an adopting `player start` re-applies its own channel over a zap
           that already landed. Did not fire in 30 bursts, and CANNOT fire in
           the warm case, which issues no `player start` at all. It stays
           UNFIXED and characterised: an adopted player's stash is evidence
           of nothing - it may be the user's last choice or minutes old - and
           ordering it would need the sequence number on `play` that ruling
           CL4 withholds until refusals are routed.
      T-B  a `play` reaches the socket and wins it before the `player start`
           that SPAWNED the player has finished its own handshake. This is
           the one that fires, 10 in 20. It is FIXED here: the spawn is what
           orders the two without a sequence number, because a player this
           helper just created was born idle and empty, so anything on it now
           arrived after the spawn and is therefore newer.

    Both are deterministic because they gate the race rather than racing it -
    the stub withholds the `mpv-version` reply `player start` waits for while
    `play` demands no handshake at all - and that is the only honest way to
    drive two client slots in a unit test.
    """

    def read(self, prop):
        client = helper.MpvIpc(self.sock, 2)
        client.connect()
        try:
            ok, data = client.try_command("get_property", prop)
            return data if ok else None
        finally:
            client.close()

    def test_an_older_player_start_re_applies_its_channel_over_a_newer_zap(self):
        # bbc1 is playing; the user zaps to espn; a `player start` for bbc1
        # arrives afterwards and adopts the running player.
        code, _, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        code, payload, _, stderr = run("play", "--id", "t:espn.us", "--socket", self.sock,
                                       "--cache-dir", self.cache, "--scope", "g:uk",
                                       "--since", "3000", "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.read("force-media-title"), "ESPN")
        self.assertEqual(self.read(helper.USER_DATA_STASH)["id"], "t:espn.us")
        # The start adopts rather than spawning a second player, which is
        # requirement 1 working exactly as designed...
        code, payload, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        self.assertFalse(payload["spawned"])
        self.assertEqual(len(self.spawned_argv()), 1)
        # ...and then it applies ITS channel, which is the older intent.
        self.assertEqual(self.read("force-media-title"), "BBC One HD")
        self.assertEqual(self.read(helper.USER_DATA_STASH)["id"], "t:bbc1.uk")
        self.assertIn("bbc1", self.read("path"))
        # Nothing in the verb could have known: `play` leaves no sequence
        # number anywhere, so the lock record still reads the start's.
        self.assertEqual(helper.record_seq(helper.read_lock_file(self.sock)), 1)

    def test_a_zap_that_lands_inside_a_cold_starts_handshake_is_left_playing(self):
        # THE DEFECT, driven directly. The cold-burst shape made deterministic
        # at the one point the two client slots can be ordered: the stub binds
        # its socket and then withholds the mpv-version reply that
        # `player start` waits for, while `play` demands no handshake at all.
        # Before the fix this case ended with the start's own channel applied
        # over the zap's, 1/1 - the field divergence with the race removed.
        gate = os.path.join(self.dir, "release-the-handshake")
        self.env(STUB_MPV_GATE=gate)
        os.makedirs(self.runtime, 0o700, exist_ok=True)
        start = subprocess.Popen(["python3", str(ROOT / "bin" / "omarchy-iptv"), "player", "start",
                                  "--socket", self.sock, "--cache-dir", self.cache, "--id", "t:bbc1.uk",
                                  "--seq", "1", "--ipc-timeout", "5", "--lock-timeout", "5",
                                  "--spawn-timeout", "8", "--first-load-timeout", "1",
                                  "--owner-pid", str(os.getpid())],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.reap_process, start)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and not os.path.exists(self.sock):
            time.sleep(0.005)
        self.assertTrue(os.path.exists(self.sock), "the player bound its socket")
        # The zap gets there first and completes, start to finish.
        code, _, _, stderr = run("play", "--id", "t:espn.us", "--socket", self.sock,
                                 "--cache-dir", self.cache, "--scope", "g:QA",
                                 "--since", "3000", "--ipc-timeout", "2")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.read("force-media-title"), "ESPN")
        pathlib.Path(gate).write_text("go", encoding="utf-8")
        out, err = start.communicate(timeout=20)
        self.assertEqual(start.returncode, 0, err.decode("utf-8", "replace"))
        payload = json.loads(out.decode("utf-8").strip().splitlines()[-1])
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["spawned"])
        # The start finishes its handshake, finds a channel on the player it
        # only just created, and stands down. Title, force-media-title, the
        # stash and the loaded stream all still name the newer intent.
        self.assertEqual(self.read("force-media-title"), "ESPN")
        self.assertEqual(self.read("title"), helper.MPV_RAW_PREFIX + "ESPN")
        self.assertEqual(self.read(helper.USER_DATA_STASH)["id"], "t:espn.us")
        self.assertIn("espn", self.read("path"))
        self.assertNotIn("bbc1", self.read("path"))
        # Exactly one load reached the player, where the defect took two.
        self.assertEqual(self.read("playlist-count"), 1)
        self.assertEqual(len(self.spawned_argv()), 1, "and still exactly one player")
        # And it SAYS so, which is what lets the shell re-apply its own
        # intent when the channel left playing is not the one it wants.
        self.assertFalse(payload["applied"])
        self.assertEqual(payload["playing"], {"id": "t:espn.us", "name": "ESPN"})
        self.assertEqual(payload["id"], "t:bbc1.uk")
        self.assertIn("a newer channel change reached the player first", payload["warnings"])
        # The owner claim is about which shell owns the player, not which
        # channel is on it, so standing down must not drop it.
        self.assertEqual(self.read(helper.USER_DATA_OWNER)["pid"], os.getpid())

    def test_a_start_that_stands_down_still_reports_a_player_and_an_entry(self):
        # The stand-down must not look like a failure to the shell: an ok
        # reply with a pid, the entry id of the load that IS on the player,
        # and a first-load verdict of "unknown" rather than a three second
        # wait for an event that already happened.
        gate = os.path.join(self.dir, "release-the-handshake")
        self.env(STUB_MPV_GATE=gate)
        os.makedirs(self.runtime, 0o700, exist_ok=True)
        start = subprocess.Popen(["python3", str(ROOT / "bin" / "omarchy-iptv"), "player", "start",
                                  "--socket", self.sock, "--cache-dir", self.cache, "--id", "t:bbc1.uk",
                                  "--seq", "4", "--ipc-timeout", "5", "--lock-timeout", "5",
                                  "--spawn-timeout", "8", "--first-load-timeout", "30"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.reap_process, start)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and not os.path.exists(self.sock):
            time.sleep(0.005)
        code, _, _, stderr = run("play", "--id", "t:espn.us", "--socket", self.sock,
                                 "--cache-dir", self.cache, "--scope", "g:QA",
                                 "--since", "3000", "--ipc-timeout", "2")
        self.assertEqual(code, 0, stderr)
        pathlib.Path(gate).write_text("go", encoding="utf-8")
        began = time.monotonic()
        out, err = start.communicate(timeout=20)
        self.assertEqual(start.returncode, 0, err.decode("utf-8", "replace"))
        payload = json.loads(out.decode("utf-8").strip().splitlines()[-1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["seq"], 4)
        self.assertGreater(payload["pid"], 0)
        self.assertEqual(payload["entryId"], 1)
        self.assertEqual(payload["firstLoad"], {"state": "unknown", "reason": ""})
        # A 30 s first-load window it never enters.
        self.assertLess(time.monotonic() - began, 10.0)

    def test_a_start_that_spawns_an_untouched_player_still_applies_its_channel(self):
        # The other side of the same decision, and the one that must not
        # regress: nothing else reached the player, so the start is still the
        # newest intent and applies its channel exactly as it always did.
        code, payload, _, stderr = self.player_start()
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["spawned"])
        self.assertTrue(payload["applied"])
        self.assertIsNone(payload["playing"])
        self.assertEqual(self.read("force-media-title"), "BBC One HD")
        self.assertEqual(self.read(helper.USER_DATA_STASH)["id"], "t:bbc1.uk")
        self.assertEqual(self.read(helper.USER_DATA_STASH)["verb"], "start")

    def test_a_zap_stamps_the_lock_records_seq_into_the_stash_not_a_zero(self):
        # The plan's step 2. The stash's seq was hardcoded 0, so the two sides
        # could be seen to differ and never compared. `play` still has no
        # --seq of its own (ruling CL4), so the number comes from the lock
        # record - a plain file read that cannot block and cannot say `busy`.
        code, _, _, stderr = self.player_start("--seq", "6")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.read(helper.USER_DATA_STASH)["seq"], 6)
        self.assertEqual(self.read(helper.USER_DATA_STASH)["verb"], "start")
        code, _, _, stderr = run("play", "--id", "t:espn.us", "--socket", self.sock,
                                 "--cache-dir", self.cache, "--scope", "g:QA",
                                 "--since", "3000", "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        stash = self.read(helper.USER_DATA_STASH)
        self.assertEqual(stash["id"], "t:espn.us")
        self.assertEqual(stash["seq"], 6)
        self.assertEqual(stash["verb"], "play")

    def stand_down(self, zap_id, seq="9"):
        """Drive one whole cold-start stand-down and return the reply and the
        helper's own stderr. Same gate as the defect test above: the stub
        binds its socket and then withholds the `mpv-version` reply
        `player start` waits for, so the zap provably reaches the player
        inside the start's handshake."""
        gate = os.path.join(self.dir, "release-the-handshake")
        self.env(STUB_MPV_GATE=gate)
        os.makedirs(self.runtime, 0o700, exist_ok=True)
        start = subprocess.Popen(["python3", str(ROOT / "bin" / "omarchy-iptv"), "player", "start",
                                  "--socket", self.sock, "--cache-dir", self.cache, "--id", "t:bbc1.uk",
                                  "--seq", seq, "--ipc-timeout", "5", "--lock-timeout", "5",
                                  "--spawn-timeout", "8", "--first-load-timeout", "1"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.reap_process, start)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and not os.path.exists(self.sock):
            time.sleep(0.005)
        self.assertTrue(os.path.exists(self.sock), "the player bound its socket")
        code, _, _, stderr = run("play", "--id", zap_id, "--socket", self.sock,
                                 "--cache-dir", self.cache, "--scope", "g:QA",
                                 "--since", "3000", "--ipc-timeout", "2")
        self.assertEqual(code, 0, stderr)
        pathlib.Path(gate).write_text("go", encoding="utf-8")
        out, err = start.communicate(timeout=20)
        err = err.decode("utf-8", "replace")
        self.assertEqual(start.returncode, 0, err)
        payload = json.loads(out.decode("utf-8").strip().splitlines()[-1])
        self.assertFalse(payload["applied"], err)
        return payload, err

    def test_the_stand_down_line_names_the_channel_given_up_and_the_one_left_playing(self):
        # D-CL-1. The line used to end `(intent %d over %d)` and those two
        # numbers are equal by construction, so it could never say what it was
        # added to say. THIS is the constructed case where the two values it
        # reports now do differ: the start carries bbc1, the zap that beat it
        # carries espn, and the line names both.
        payload, err = self.stand_down("t:espn.us")
        line = [text for text in err.splitlines()
                if "a newer channel change reached the player first" in text]
        self.assertEqual(len(line), 1, err)
        line = line[0]
        self.assertIn("intent 9 would have applied t:bbc1.uk", line)
        self.assertIn("the player is on t:espn.us, written by play as entry 1", line)
        self.assertIn("left it playing", line)
        # The half that makes it a diagnostic rather than decoration: the two
        # channels it reports are different strings, in a line whose predecessor
        # printed the same number twice.
        self.assertNotEqual(payload["id"], payload["playing"]["id"])
        self.assertIn(payload["id"], line)
        self.assertIn(payload["playing"]["id"], line)
        # And the number that could not vary is gone rather than relabelled.
        self.assertNotIn("over", line)
        self.assertEqual(len(re.findall(r"intent \d+", line)), 1, line)
        # Why it could not vary, pinned: `play` has no --seq of its own
        # (ruling CL4), so it stamps the stash with the lock record - which
        # inside a cold start is this start's own number, read back. If CL4 is
        # ever lifted and `play` gains an intent of its own, this goes red and
        # the line deserves revisiting.
        self.assertEqual(self.read(helper.USER_DATA_STASH)["seq"], payload["seq"])
        self.assertEqual(helper.record_seq(helper.read_lock_file(self.sock)), payload["seq"])

    def test_the_stand_down_line_says_so_when_the_newer_change_is_the_same_channel(self):
        # The other value the same field can take, driven the same way: a zap
        # to the channel the start was going to apply anyway still stands the
        # start down, and the line must not print one id twice as though it
        # were two. A human reading this one knows the user is watching what
        # they asked for.
        payload, err = self.stand_down("t:bbc1.uk")
        line = [text for text in err.splitlines()
                if "a newer channel change reached the player first" in text][0]
        self.assertIn("intent 9 would have applied t:bbc1.uk", line)
        self.assertIn("the player is on that same channel, written by play as entry 1", line)
        self.assertEqual(payload["id"], payload["playing"]["id"])
        self.assertEqual(line.count("t:bbc1.uk"), 1, line)


class StandDownNoteTest(unittest.TestCase):
    """D-CL-1, the formatting on its own. The end-to-end cases above prove the
    line the helper really emits; these pin what it says in the shapes a live
    player can present that a stubbed cold start cannot easily be driven into.
    """

    @staticmethod
    def note(seq=9, mine="t:bbc1.uk", **newer):
        record = {"id": "", "name": "", "entryId": None, "verb": "", "loaded": True}
        record.update(newer)
        return helper.stand_down_note(seq, {"id": mine}, record)

    def test_the_two_channels_are_what_varies(self):
        first = self.note(id="t:espn.us", entryId=1, verb="play")
        second = self.note(id="t:news.uk", entryId=1, verb="play")
        self.assertNotEqual(first, second)
        self.assertIn("would have applied t:bbc1.uk", first)
        self.assertIn("the player is on t:espn.us", first)
        self.assertIn("the player is on t:news.uk", second)

    def test_a_load_with_no_stash_is_reported_as_unlabelled_not_as_an_empty_id(self):
        line = self.note(loaded=True)
        self.assertIn("the player is on a load this helper did not label", line)
        self.assertNotIn("written by", line)
        self.assertNotIn("entry", line)

    def test_a_stash_with_no_entry_id_still_names_its_writer(self):
        line = self.note(id="t:espn.us", verb="play")
        self.assertIn("the player is on t:espn.us, written by play)", line)
        self.assertNotIn("as entry", line)

    def test_a_stash_from_an_older_schema_reports_the_entry_without_inventing_a_writer(self):
        line = self.note(id="t:espn.us", entryId=3)
        self.assertIn("the player is on t:espn.us, entry 3)", line)
        self.assertNotIn("written by", line)

    def test_a_zap_that_carried_a_url_and_no_channel_id_is_named_as_such(self):
        line = self.note(entryId=2, verb="play")
        self.assertIn("the player is on an unnamed stream, written by play as entry 2", line)

    def test_no_intent_number_is_printed_when_the_verb_was_given_none(self):
        # `player start` without --seq writes 0 to the lock record. Printing
        # "intent 0" would be the same defect in a smaller font.
        line = self.note(seq=0, id="t:espn.us", entryId=1, verb="play")
        self.assertIn("it would have applied t:bbc1.uk", line)
        self.assertNotIn("intent", line)


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
        # D-SINK-2 made it twenty: `--include` loads a config file, and a config
        # file can set every other option on this list, so reserving the others
        # and not it reserved nothing.
        self.assertEqual(len(names), 20)
        self.assertIn("--include", names)
        self.assertNotIn("--ytdl", names)          # PO-5
        # NOT reserved, deliberately: ruling PO-10 / D-PLY-5 keeps --script-opts
        # a HANDOFF option that warns. This line is what caught an attempt to
        # reserve it while fixing D-SINK-2.
        self.assertNotIn("--script-opts", names)

    def test_the_app_id_is_the_class_picture_in_picture_matches_on(self):
        # M2-05. The window class PiP addresses is the app-id the player is
        # launched with, and that string is written in three places: this
        # helper, Model.buildMpvArgv, and Model's PIP_CLASS. The first two
        # were pinned to each other by this fixture; the third was pinned to
        # neither, and the failure that produces is silent - a renamed app-id
        # leaves `p` answering "Cannot find the player window" for ever with
        # every suite green. Model.js now builds the flag from the constant;
        # this is the Python half of the same pin.
        flag = "--wayland-app-id=omarchy-iptv"
        argv = helper.mpv_launch_argv("/run/user/1000/omarchy-iptv/mpv.sock", [])
        self.assertIn(flag, argv)
        self.assertIn('var PIP_CLASS = "%s"' % flag.split("=")[1], self.model)
        self.assertIn('"--wayland-app-id=" + PIP_CLASS', self.model)
        for case in self.fixture["mpvArgv"]:
            self.assertIn(flag, case["argv"], case["name"])

    def test_generic_failure_text_matches(self):
        self.assertEqual(helper.PLAYER_GENERIC_FAILURE, self.fixture["genericFailure"])
        self.assertIn('var PLAYER_GENERIC_FAILURE = "%s"' % self.fixture["genericFailure"], self.model)

    def test_mpv_handoff_warnings_match_every_shared_vector(self):
        table = self.fixture["mpvHandoff"]
        self.assertEqual(helper.MPV_HANDOFF_TEXT, table["text"])
        self.assertIn('var MPV_HANDOFF_TEXT = "%s"' % table["text"], self.model)
        for vector in table["cases"]:
            self.assertEqual(helper.mpv_arg_warnings(vector["tokens"]), vector["warnings"], vector["name"])

    def test_the_handoff_sets_match_model_js(self):
        for name, js in (("MPV_HANDOFF", "MPV_HANDOFF"),
                         ("MPV_HANDOFF_SCRIPT_OPTS", "MPV_HANDOFF_SCRIPT_OPTS"),
                         ("MPV_YTDL_OFF", "MPV_YTDL_OFF")):
            block = re.search(r"var %s = \{(.*?)\}" % js, self.model, re.S)
            self.assertIsNotNone(block, js)
            keys = set(re.findall(r'"([^"]+)":\s*true', block.group(1)))
            self.assertEqual(keys, set(getattr(helper, name)), js)
        # PO-5: warned about, never reserved. The two lists must not overlap.
        self.assertEqual(helper.MPV_HANDOFF & helper.MPV_RESERVED, frozenset())
        self.assertNotIn("--ytdl", helper.MPV_RESERVED)

    def test_player_dirs_match_every_shared_vector(self):
        for vector in self.fixture["playerDirs"]["cases"]:
            self.assertEqual(helper.player_dirs(vector["socketPath"], vector["stateDir"]),
                             vector["dirs"], vector["name"])

    def test_mpv_launch_argv_matches_every_shared_vector(self):
        for vector in self.fixture["mpvArgv"]:
            args, rejected = helper.filter_mpv_args(vector["mpvArgs"])
            dirs = helper.player_dirs(vector["socketPath"], vector["stateDir"])
            self.assertEqual(helper.mpv_launch_argv(vector["socketPath"], args, dirs), vector["argv"], vector["name"])
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
        self.assertGreaterEqual(len(self.fixture["mpvHandoff"]["cases"]), 14)
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
