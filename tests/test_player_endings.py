"""How a player's ending reads: D-PLY-36 and D-PLY-37 (the owner, 2026-10-28).

The helper's half of tests/fixtures/player-endings.json; tests/Model.test.js
runs the model's half over the same file (Model.deathReport over every reply
the helper writes here, Model.outputFailure over the pinned mpv strings).

D-PLY-36. `player start`'s first-load window answered `{state: "failed"}`
both for an end-file error on its own entry and for mpv closing the
connection, so the shell could not tell a stream that failed to load from a
player that died, and marked both. The reply now says which ending it saw
(`ended`, and mpv's `file_error` as `fileError` for an end-file).

D-PLY-37. The join on mpv's prose is pinned with the version it was read
from, and the real mpv is run, windowless and silent, to read the audio
output's string again: a later mpv that rewords it turns this red rather
than a channel.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import shutil
import socket
import subprocess
import tempfile
import time
import unittest

from helper_loader import load_helper

helper = load_helper()

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "player-endings.json").read_text(encoding="ascii"))


class Batches:
    """The MpvIpc surface observe_first_load reads: drain_events hands back
    the fixture's batches in order, None being mpv closing the connection. A
    window that asks for more than the fixture gives is a test failure, never
    a silent `closed`."""

    def __init__(self, batches):
        self.batches = list(batches)
        self.asked = 0

    def drain_events(self, deadline):
        self.asked += 1
        if not self.batches:
            raise AssertionError("the window asked for more than the fixture gives")
        batch = self.batches.pop(0)
        return None if batch is None else [dict(event) for event in batch]


class FirstLoadReplyTest(unittest.TestCase):
    """observe_first_load writes exactly the fixture's reply for each case."""

    def test_every_case(self):
        cases = FIXTURE["firstLoad"]
        self.assertGreaterEqual(len(cases), 6)
        for case in cases:
            with self.subTest(case=case["name"]):
                client = Batches(case["batches"])
                reply = helper.observe_first_load(client, case["entryId"], 5.0)
                self.assertEqual(reply, case["reply"])
                self.assertEqual(client.batches, [], "the window stopped before the fixture's last batch")

    def test_a_failed_reply_always_says_which_ending(self):
        """Both endings are in the fixture, and nothing else is a "failed"."""
        endings = sorted({c["reply"].get("ended", "") for c in FIXTURE["firstLoad"] if c["reply"]["state"] == "failed"})
        self.assertEqual(endings, ["closed", "end-file"])
        for case in FIXTURE["firstLoad"]:
            with self.subTest(case=case["name"]):
                reply = case["reply"]
                if reply["state"] != "failed":
                    self.assertNotIn("ended", reply)
                    self.assertNotIn("fileError", reply)
                elif reply["ended"] == "end-file":
                    self.assertIn("fileError", reply)
                else:
                    self.assertNotIn("fileError", reply)

    def test_the_file_error_is_redacted_and_cut_like_the_reason(self):
        url = "http://user:secret@provider.test:8080/live/token/1.ts"
        client = Batches([[{"event": "end-file", "reason": "error", "playlist_entry_id": 3,
                            "file_error": "loading failed " + url + " " + "x" * 900}]])
        reply = helper.observe_first_load(client, 3, 5.0)
        self.assertEqual(reply["ended"], "end-file")
        self.assertNotIn("secret", reply["fileError"])
        self.assertNotIn("token", reply["fileError"])
        self.assertLessEqual(len(reply["fileError"]), helper.FIRST_LOAD_REASON_MAX)

    def test_a_window_that_runs_out_says_neither_ending(self):
        """A window that reaches its deadline having seen no ending answers
        exactly "unknown": neither an end-file nor a closed connection, so
        no `ended` and no `fileError`. Every fixture case ends before its
        deadline, so a mutant that wrote `closed` here survived them all
        (rc-host5); the real mpv behind a server that never answers gives
        this reply too."""

        class Quiet:
            def drain_events(self, deadline):
                time.sleep(max(0.0, min(0.01, deadline - time.monotonic())))
                return []

        reply = helper.observe_first_load(Quiet(), 3, 0.05)
        self.assertEqual(reply, {"state": "unknown", "reason": ""})


def short_dir():
    """A private folder whose socket path fits sun_path (108 bytes): the
    default temporary folder, or /tmp when TMPDIR is long."""
    base = tempfile.gettempdir()
    if len(base) > 60:
        base = "/tmp"
    return tempfile.mkdtemp(prefix="iptv-end-", dir=base)


@unittest.skipUnless(shutil.which("mpv"), "mpv is not installed")
class MpvStillSaysItTest(unittest.TestCase):
    """The canary: the real mpv, in the player's own launch shape, with an
    ALSA device that does not exist -- no window (--vo=null, and no display
    or compositor in its environment), no sound (the device is missing, so
    nothing reaches any server; the runtime folder is a private empty one).
    The pid it starts is the only one it ends."""

    def test_the_audio_output_failure_reads_as_pinned(self):
        canary = FIXTURE["mpv"]["canary"]
        work = short_dir()
        sock_path = os.path.join(work, "m.sock")
        home = os.path.join(work, "home")
        os.mkdir(home, 0o700)
        env = {"PATH": os.environ.get("PATH", "/usr/bin"), "HOME": home, "XDG_RUNTIME_DIR": work,
               "XDG_CONFIG_HOME": os.path.join(home, ".config"), "XDG_CACHE_HOME": os.path.join(home, ".cache"),
               "XDG_STATE_HOME": os.path.join(home, ".state"), "LANG": "C.UTF-8"}
        version = subprocess.run(["mpv", "--no-config", "--version"], capture_output=True, text=True, timeout=10, env=env).stdout.split("\n")[0]
        proc = subprocess.Popen(["mpv"] + canary["argv"] + ["--input-ipc-server=" + sock_path],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        ends = []
        try:
            client = socket.socket(socket.AF_UNIX)
            deadline = time.monotonic() + 10
            while True:
                try:
                    client.connect(sock_path)
                    break
                except OSError:
                    if time.monotonic() > deadline or proc.poll() is not None:
                        self.fail("mpv opened no socket (exit %r; %s)" % (proc.poll(), version))
                    time.sleep(0.05)
            client.settimeout(0.5)
            client.sendall((json.dumps({"command": ["loadfile", canary["url"], "replace"]}) + "\n").encode())
            buf = b""
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and not ends:
                try:
                    chunk = client.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get("event") == "end-file":
                        ends.append({k: event[k] for k in ("event", "reason", "playlist_entry_id", "file_error") if k in event})
            client.close()
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            shutil.rmtree(work, ignore_errors=True)
        self.assertEqual(ends[:1], [canary["endFile"]],
                         "the installed mpv (%s) no longer ends a file whose audio output cannot open the way "
                         "mpv %s did; Model.outputFailure joins on that string (D-PLY-37), so re-measure and "
                         "re-pin tests/fixtures/player-endings.json" % (version, FIXTURE["mpv"]["version"]))


    def test_a_nested_playlist_under_the_helpers_loadfile_reads_as_pinned(self):
        """D-PLY-44's canary (2026-10-29): the real mpv, given a plain M3U the
        way apply_channel gives it a channel -- the positional loadfile, its
        options a JSON object carrying demuxer=lavf -- answers the loadfile
        and ends the file with the string Model.unopenedFormatSentence joins
        on. A file on disk, so it contacts nothing; no window, no sound."""
        canary = FIXTURE["mpv"]["formatCanary"]
        work = short_dir()
        sock_path = os.path.join(work, "m.sock")
        home = os.path.join(work, "home")
        os.mkdir(home, 0o700)
        playlist = os.path.join(work, "nested.m3u")
        with open(playlist, "w", encoding="ascii") as fh:
            fh.write(canary["body"])
        env = {"PATH": os.environ.get("PATH", "/usr/bin"), "HOME": home, "XDG_RUNTIME_DIR": work,
               "XDG_CONFIG_HOME": os.path.join(home, ".config"), "XDG_CACHE_HOME": os.path.join(home, ".cache"),
               "XDG_STATE_HOME": os.path.join(home, ".state"), "LANG": "C.UTF-8"}
        proc = subprocess.Popen(["mpv"] + canary["argv"] + ["--input-ipc-server=" + sock_path],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
                                preexec_fn=lambda: __import__("resource").setrlimit(__import__("resource").RLIMIT_CORE, (0, 0)))
        ends, replies = [], []
        try:
            client = socket.socket(socket.AF_UNIX)
            deadline = time.monotonic() + 10
            while True:
                try:
                    client.connect(sock_path)
                    break
                except OSError:
                    if time.monotonic() > deadline or proc.poll() is not None:
                        self.fail("mpv opened no socket (exit %r)" % proc.poll())
                    time.sleep(0.05)
            client.settimeout(0.5)
            client.sendall((json.dumps({"command": ["loadfile", playlist, "replace", -1, canary["options"]],
                                        "request_id": 7}) + "\n").encode())
            buf = b""
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and not ends:
                try:
                    chunk = client.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get("request_id") == 7:
                        replies.append(event.get("error"))
                    if event.get("event") == "end-file":
                        ends.append({k: event[k] for k in ("event", "reason", "playlist_entry_id", "file_error") if k in event})
            client.close()
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            shutil.rmtree(work, ignore_errors=True)
        self.assertEqual(replies, ["success"], "mpv refused the loadfile's options object")
        self.assertEqual(ends[:1], [canary["endFile"]],
                         "the installed mpv no longer ends a nested plain playlist under demuxer=lavf the way mpv %s "
                         "did; Model.unopenedFormatSentence joins on that string (D-PLY-44), so re-measure and re-pin "
                         "tests/fixtures/player-endings.json" % FIXTURE["mpv"]["version"])
        self.assertEqual(canary["endFile"]["file_error"], FIXTURE["formatErrors"][0]["fileError"])


if __name__ == "__main__":
    unittest.main()
