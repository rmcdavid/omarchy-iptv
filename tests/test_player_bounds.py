"""D-PLY-35 (2026-10-28): the helper's half of tests/fixtures/player-bounds.json.

The shell's player watchdog is derived from every bound a `player
start|restart|probe` can wait out (Model.playerWatchdogMs). Those bounds live
here, in the helper, and the model mirrors them; tests/Model.test.js pins the
mirrors and the arithmetic to the fixture, and this file pins the helper to
it: every number the fixture holds is read off the helper by the name the
fixture gives (red the moment either side moves alone), the verbs take those
numbers when the shell passes no timeout flag (it passes none), and the two
bounds that were literals until this change are observed being USED where the
arithmetic says they are, not merely declared.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import shutil
import tempfile
import types
import unittest
from unittest import mock

from helper_loader import load_helper

helper = load_helper()

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "player-bounds.json"
BOUNDS = json.loads(FIXTURE.read_text(encoding="utf-8"))


def as_ms(value, unit):
    return int(round(value * 1000)) if unit == "s" else int(value)


class PlayerBoundsFixtureTest(unittest.TestCase):

    def test_every_bound_the_fixture_holds_is_the_helpers(self):
        for key, (name, unit) in BOUNDS["names"].items():
            with self.subTest(bound=key, name=name):
                self.assertTrue(hasattr(helper, name), "the helper has no %s" % name)
                self.assertEqual(as_ms(getattr(helper, name), unit), BOUNDS["helper"][key])

    def test_the_fixture_names_every_bound_it_holds(self):
        # A number with no helper name beside it is a number nothing here can
        # pin (engineering rule 13): the two key sets are the same set.
        self.assertEqual(sorted(BOUNDS["names"]), sorted(BOUNDS["helper"]))

    def test_the_slot_verbs_run_with_those_bounds_when_the_shell_passes_no_timeout(self):
        parser = helper.build_parser()
        session = ["--socket", "/run/x/mpv.sock", "--cache-dir", "/x/cache", "--id", "t:x", "--seq", "3"]
        for verb in ("start", "restart"):
            with self.subTest(verb=verb):
                args = parser.parse_args(["player", verb] + session)
                self.assertEqual(as_ms(args.lock_timeout, "s"), BOUNDS["helper"]["lockMs"])
                self.assertEqual(as_ms(args.spawn_timeout, "s"), BOUNDS["helper"]["spawnMs"])
                self.assertEqual(as_ms(args.first_load_timeout, "s"), BOUNDS["helper"]["firstLoadMs"])
                self.assertEqual(as_ms(args.ipc_timeout, "s"), BOUNDS["helper"]["ipcMs"])
        args = parser.parse_args(["player", "probe", "--socket", "/run/x/mpv.sock"])
        self.assertEqual(as_ms(args.ipc_timeout, "s"), BOUNDS["helper"]["ipcMs"])
        # The restart the shell issues ladders from `term` (Service.qml,
        # restartPlayer: `--from term`), which is the ladder the restart's
        # bound counts; the verb's own default is the same rung.
        self.assertEqual(parser.parse_args(["player", "restart"] + session).from_rung, "term")

    def test_the_spawn_waits_its_named_bounds_for_the_pid_and_the_exec(self):
        # spawn_detached run for real up to the fork, which answers a child
        # that never reports: the two pipe reads are recorded with the bound
        # each was given, and the spawn refuses as it always has.
        seen = []

        def read_pipe(fd, timeout):
            seen.append(timeout)
            return b""

        with mock.patch.object(helper, "_read_pipe", side_effect=read_pipe), \
                mock.patch.object(helper.os, "fork", return_value=2 ** 22 + 7), \
                mock.patch.object(helper.os, "waitpid", side_effect=ChildProcessError()):
            with self.assertRaises(helper.HelperError) as caught:
                helper.spawn_detached(["--idle=once"], "/")
        self.assertEqual(caught.exception.code, "spawn_failed")
        self.assertEqual([as_ms(t, "s") for t in seen], [BOUNDS["helper"]["spawnPidMs"], BOUNDS["helper"]["spawnMs"]])

    def test_the_settle_connects_with_its_named_bound(self):
        timeouts = []
        real = helper.MpvIpc

        class Recording(real):
            def __init__(self, path, timeout):
                timeouts.append(timeout)
                super().__init__(path, timeout)

        with mock.patch.object(helper, "MpvIpc", Recording):
            helper.socket_is_dead(os.path.join("/nonexistent-ply35", "mpv.sock"))
        self.assertEqual([as_ms(t, "s") for t in timeouts], [BOUNDS["helper"]["settleConnectMs"]])


# ---- the recheck of lane-ply35 (2026-10-28): the composition, walked ----
#
# Everything above pins LEAVES -- each bound against its name. What the
# watchdog is derived from is how the verbs COMPOSE them, and that is where
# the first version went wrong: it gave `restart` its own ladder from term
# and then a spawn, but player_start(verb="restart") runs adopt_or_spawn
# after that ladder, and a player the ladder could not end (a process in
# uninterruptible sleep acts on neither signal) is found there, probed, and
# laddered again from quit, exactly as a start meets a wedged player. So the
# shipping verbs are run here, whole, under a virtual clock, every wait on
# the path taken at its bound, and each must finish inside its watchdog less
# the margin the fixture reserves for what no bound cuts (the interpreter, the
# cache read, the /proc scans). Nothing real is signalled, forked or
# connected: os.kill, os.fork and the IPC socket are doubles, the lock file is
# in a fresh temporary folder, and HOME is helper_loader's.
#
# The path each walk takes, and why it is the long one:
#   start   -- the lock granted on its last poll; a found player whose listen
#              backlog accepts a connect just inside the bound and that never
#              answers (probe, then the whole ladder from quit); the spawn's
#              pid and exec pipes at their bounds; the bind window refused
#              until its last poll, whose probe connects and answers just
#              inside its bounds; the first request after the loadfile at its
#              bound (caught); the first-load window to its end.
#   restart -- the same, after its own ladder from term over that player,
#              which survives it.
#   probe   -- a found player that answers mpv-version just inside the bound
#              and nothing after it (the next request ends the verb), and one
#              that answers nothing at all.
# "Its last poll" is LEARNED from the code, never assumed: a first walk is
# refused the lock throughout and records when the verb last asked for it, a
# second is granted it then and refused the socket throughout, recording the
# bind window's last poll, and the third is granted both at those moments. So
# a wait that grows in the code grows the walk. Every other wait is spent at
# the bound the code itself hands the double (the socket's timeout, the
# pipe's), so those are the code's numbers too.
# Red on the first version's fixture: the restart walk is 41.12 s against
# 35.45 - 5 = 30.45 s.

class _Clock:
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        if seconds > 0:
            self.t += seconds

    def time(self):
        return 1.7e9 + self.t


_JUST_INSIDE = 1e-6
_REAL_IPC = helper.MpvIpc


def walk_player_verb(verb, survivor_answers=0, lock_at=None, bind_after=None):
    """Run `player <verb>` through the shipping code, every wait on the path
    at its bound. `survivor_answers`: how many requests the found player
    answers (just inside the bound) before it goes quiet. `lock_at` /
    `bind_after`: when the lock is granted / the new player's socket accepts
    (seconds after the spawn), None for never. Returns (virtual seconds, the
    reply, the signals the found player was sent, what was learned)."""
    clock = _Clock()
    state = {"phase": "found", "bind_at": None, "pipes": 0}
    learned = {"lock_last": None, "bind_last": None}
    survivor = {"pid": 777, "startTime": "1"}
    signals = []
    replies = []
    folder = tempfile.mkdtemp(prefix="ply35-walk-")
    os.chmod(folder, 0o700)
    sock = os.path.join(folder, "mpv.sock")

    def flock(fd, op):
        learned["lock_last"] = clock.t
        if lock_at is None or clock.t < lock_at:
            raise BlockingIOError(11, "held")

    def find_player(_sock):
        return [dict(survivor)] if state["phase"] == "found" else []

    def read_pipe(fd, timeout):
        state["pipes"] += 1
        clock.t += timeout
        return b"4242" if state["pipes"] == 1 else b""

    real_spawn = helper.spawn_detached

    def spawn(argv, cwd="/"):
        launched = real_spawn(argv, cwd)
        state["phase"] = "bind"
        state["bind_at"] = clock.t
        return launched

    class Sock:
        def __init__(self, answers, then_all=False):
            self.answers = answers          # requests answered just inside the bound; None: all, at once
            self.then_all = then_all        # after those: quiet (False) or answering at once (True)
            self.timeout = None
            self.pending = []
            self.loaded = False

        def settimeout(self, value):
            self.timeout = value

        def sendall(self, data):
            self.pending.append(json.loads(data.decode("utf-8")))

        def close(self):
            pass

        def recv(self, _size):
            if not self.pending or self.answers == 0:
                clock.t += self.timeout
                raise TimeoutError()
            request = self.pending.pop(0)
            command = request["command"]
            if self.answers is not None:
                self.answers -= 1
                if self.answers == 0 and self.then_all:
                    self.answers = None
                clock.t += self.timeout - _JUST_INSIDE
                return self.line(request, "success", "mpv 0.41.0")
            if self.loaded and command[:2] == ["set_property", helper.USER_DATA_STASH]:
                clock.t += self.timeout
                self.loaded = False
                raise TimeoutError()
            data, error = None, "success"
            if command[0] == "get_property":
                # The spawned player is one THIS release launched, so it reads
                # what the pin block made it (2026-10-29): the demuxer map
                # holding the pinned tls_verify, auto-profiles off (mpv answers
                # that `no` as False), and every option a per-file profile
                # could undo set from the command line.
                # 2026-10-29 (lane-p1b): and the pinned protocol whitelist in
                # the demuxer map (D-SINK-55), reset-on-next-file emptied by
                # its -clr (D-SINK-60), drag-and-drop off and the OSC key set.
                answers = {helper.MPV_TLS_VERIFY_PROP: True, helper.MPV_STREAM_OPTS_PROP: {}, "playlist-count": 0,
                           helper.MPV_DEMUXER_OPTS_PROP: {"protocol_whitelist": helper.MPV_PROTOCOL_WHITELIST,
                                                          "tls_verify": "1"},
                           helper.MPV_AUTO_PROFILES_PROP: False, helper.MPV_RESET_PROP: [],
                           "drag-and-drop": False,
                           "script-opts": {helper.MPV_OSC_TITLE_KEY: helper.MPV_OSC_TITLE_VALUE}}
                for option in helper.PER_FILE_TLS_OPTIONS:
                    answers["option-info/%s/set-from-commandline" % option] = True
                data = answers.get(command[1])
                if data is None:
                    error = "property unavailable"
            elif command[0] == "loadfile":
                data = {"playlist_entry_id": 1}
                self.loaded = True
            return self.line(request, error, data)

        @staticmethod
        def line(request, error, data):
            return (json.dumps({"request_id": request["request_id"], "error": error, "data": data}) + "\n").encode("utf-8")

    class Ipc(_REAL_IPC):
        def connect(self):
            if state["phase"] == "bind":
                learned["bind_last"] = clock.t - state["bind_at"]
                if bind_after is None or clock.t < state["bind_at"] + bind_after:
                    self.refused = True
                    raise helper.HelperError("not_running", "refused")
            clock.t += self.timeout - _JUST_INSIDE
            if state["phase"] == "found":
                self.sock = Sock(survivor_answers)
            else:
                # The new player: answers its handshake just inside the
                # bound, then everything at once but the one request after
                # the loadfile whose timeout the verb survives.
                state["phase"] = "spawned"
                self.sock = Sock(1, then_all=True)

    patches = [
        mock.patch.object(helper, "time", types.SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep, time=clock.time)),
        mock.patch.object(helper, "fcntl", types.SimpleNamespace(flock=flock, LOCK_EX=2, LOCK_NB=4)),
        mock.patch.object(helper, "find_player", find_player),
        mock.patch.object(helper, "still_the_player", lambda record, _sock: record.get("pid") == survivor["pid"]),
        mock.patch.object(helper, "proc_start_time", lambda pid: "1"),
        mock.patch.object(helper, "limit_core_of", lambda pid: True),
        mock.patch.object(helper, "_read_pipe", read_pipe),
        mock.patch.object(helper, "spawn_detached", spawn),
        mock.patch.object(helper, "MpvIpc", Ipc),
        mock.patch.object(helper, "emit", replies.append),
        mock.patch.object(helper, "log", lambda message: None),
        mock.patch.object(helper, "player_target", lambda cid, raw, d: {
            "id": cid, "url": "http://s.example.test/x.ts", "name": "X", "headers": {"User-Agent": "u"}, "group": "G"}),
        mock.patch.object(helper, "player_dirs", lambda s, o=None: {
            "cwd": folder, "screenshots": folder, "watchLater": folder, "shaderCache": folder}),
        mock.patch.object(helper, "ensure_player_dirs", lambda dirs, warnings: None),
        mock.patch.object(helper.os, "kill", lambda pid, number: signals.append(number)),
        mock.patch.object(helper.os, "fork", lambda: 2 ** 22 + 7),
        mock.patch.object(helper.os, "waitpid", mock.Mock(side_effect=ChildProcessError())),
    ]
    for patch in patches:
        patch.start()
    try:
        parser = helper.build_parser()
        session = ["--socket", sock, "--cache-dir", folder, "--id", "t:x", "--seq", "3"]
        if verb == "probe":
            helper.player_probe(parser.parse_args(["player", "probe", "--socket", sock]))
        else:
            extra = ["--from", "term"] if verb == "restart" else []
            helper.player_start(parser.parse_args(["player", verb] + session + extra), verb)
    finally:
        for patch in reversed(patches):
            patch.stop()
        shutil.rmtree(folder, ignore_errors=True)
    return clock.t, (replies[-1] if replies else None), signals, learned


def walk_long_path(verb):
    """The three walks the comment above describes, for start or restart."""
    _, refused, _, learned = walk_player_verb(verb)
    assert (refused or {}).get("error", {}).get("code") == "busy", refused
    lock_at = learned["lock_last"]
    _, unbound, _, learned = walk_player_verb(verb, lock_at=lock_at)
    assert (unbound or {}).get("error", {}).get("code") == "no_socket", unbound
    return walk_player_verb(verb, lock_at=lock_at, bind_after=learned["bind_last"])


class PlayerWorstPathWalkTest(unittest.TestCase):

    def assert_inside_its_watchdog(self, verb, spent):
        budget = (BOUNDS["watchdogMs"][verb] - BOUNDS["marginMs"]) / 1000.0
        self.assertLessEqual(spent, budget, "player %s walked %.3f s, past its watchdog's %.3f s less the margin"
                             % (verb, spent, budget))

    def test_a_start_that_meets_a_wedged_player_fits_its_watchdog(self):
        spent, reply, signals, _ = walk_long_path("start")
        self.assertTrue(reply and reply.get("ok"), reply)
        self.assertEqual(signals, [15, 9])            # one ladder, from quit
        self.assertGreater(spent, 37.0)               # the long path really was walked
        self.assert_inside_its_watchdog("start", spent)

    def test_a_restart_whose_ladder_leaves_the_player_fits_its_watchdog(self):
        spent, reply, signals, _ = walk_long_path("restart")
        self.assertTrue(reply and reply.get("ok"), reply)
        self.assertEqual(signals, [15, 9, 15, 9])     # its own ladder, then adopt_or_spawn's
        self.assertGreater(spent, 40.0)
        self.assert_inside_its_watchdog("restart", spent)

    def test_a_probe_that_meets_a_player_gone_quiet_fits_its_watchdog(self):
        for answers, floor in ((1, 5.9), (0, 3.9)):
            with self.subTest(answers=answers):
                spent, reply, signals, _ = walk_player_verb("probe", survivor_answers=answers)
                self.assertTrue(reply is not None, reply)
                self.assertEqual(signals, [])
                self.assertGreater(spent, floor)
                self.assert_inside_its_watchdog("probe", spent)


if __name__ == "__main__":
    unittest.main()
