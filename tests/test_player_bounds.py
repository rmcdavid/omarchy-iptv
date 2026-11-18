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

# D-SINK-101: without the suite's stand-in for the play-time lookup, so the
# walk below spends that lookup at the bound the shipping code hands
# resolve_within, which the walk replaces (no resolver is ever asked).
helper = load_helper(stream_lookup=None)

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

    def test_a_dead_answer_costs_the_relay_a_stagger_not_its_connect_bound(self):
        """D-SINK-102: the relay tries a name's answers
        RELAY_ATTEMPT_STAGGER_S apart, RELAY_ATTEMPTS_IN_FLIGHT at once, so
        answers that hang before a live one delay it by staggers -- all of
        them together well inside a start's first-load window -- and never by
        RELAY_CONNECT_S, which is past it. tests/test_relay.py observes the
        stagger on a real connect."""
        h = BOUNDS["helper"]
        dead = (helper.RELAY_ATTEMPTS_IN_FLIGHT - 1) * as_ms(helper.RELAY_ATTEMPT_STAGGER_S, "s")
        self.assertLess(dead, h["firstLoadMs"] // 2)
        self.assertGreater(as_ms(helper.RELAY_CONNECT_S, "s"), h["firstLoadMs"])

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
        # spawn_player (spawn_detached until D-SINK-102) run for real up to
        # the fork, which answers a child that never reports: the two pipe
        # reads are recorded with the bound each was given, and the spawn
        # refuses as it always has.
        seen = []

        def read_pipe(fd, timeout):
            seen.append(timeout)
            return b""

        with mock.patch.object(helper, "_read_pipe", side_effect=read_pipe), \
                mock.patch.object(helper.os, "fork", return_value=2 ** 22 + 7), \
                mock.patch.object(helper.os, "waitpid", side_effect=ChildProcessError()):
            with self.assertRaises(helper.HelperError) as caught:
                helper.spawn_player(["--idle=once"], "/", -1, -1)
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
#   play    -- (D-SINK-102) the play-time lookup and both of the relay's
#              questions, the gate's status and the load's registration, at
#              their bounds, and a player that answers everything at once:
#              `play`'s 8 s was never a sum of its bounds, so what this walk
#              holds is what those bounds leave of its watchdog for mpv's
#              round trips (PlayerWorstPathWalkTest says how much).
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
_CARRY_ANSWERS = {("get_property", "volume"): 37.0, ("get_property", "mute"): True,
                  ("get_property", "fullscreen"): True, ("get_property", "pause"): True}
_REAL_IPC = helper.MpvIpc


def walk_player_verb(verb, survivor_answers=0, lock_at=None, bind_after=None, older=False, spawned_slow=0,
                     vanish_at=None):
    """Run `player <verb>` through the shipping code, every wait on the path
    at its bound. `survivor_answers`: how many requests the found player
    answers (just inside the bound) before it goes quiet. `lock_at` /
    `bind_after`: when the lock is granted / the new player's socket accepts
    (seconds after the spawn), None for never. `older`: the found player
    answers as one ANOTHER build launched (restart on adoption), so the start
    replaces it -- reads its carry, ladders it from quit -- instead of
    adopting it. `spawned_slow`: how many requests after its handshake the
    new player answers just inside the bound (the carry's sets). Returns
    (virtual seconds, the reply, the signals the found player was sent, what
    was learned). `play` (D-SINK-102) reaches a running player of this
    build at once, which answers everything at once, so the time it spends
    is the lookup's and the relay's alone. `vanish_at` (D-PLY-40, `stop`):
    the moment the found player's process is gone -- the finder and the
    re-verification before each signal no longer see it -- while its socket
    still accepts a connect, just inside the bound, which is how a killed
    player leaves it (D-PLY-8); None for never."""
    clock = _Clock()
    state = {"phase": "play" if verb == "play" else "found", "bind_at": None, "pipes": 0}
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

    def gone():
        if vanish_at is not None and clock.t >= vanish_at and state["phase"] == "found":
            state["phase"] = "gone"
        return state["phase"] != "found"

    def find_player(_sock):
        return [] if gone() else [dict(survivor)]

    def still_the_player(record, _sock):
        return not gone() and record.get("pid") == survivor["pid"]

    real_ladder = helper.stop_ladder

    def stop_ladder(*args, **kwargs):
        result = real_ladder(*args, **kwargs)
        learned["ladder_end"] = clock.t
        return result

    def read_pipe(fd, timeout):
        state["pipes"] += 1
        clock.t += timeout
        return b"4242" if state["pipes"] == 1 else b""

    # D-SINK-101: the channel's host is a name from a playlist that is not
    # local, so the shipping lookup runs (stream_lookup_refusal, through
    # stream_resolve) and its answer -- a global address -- comes just inside
    # the bound the code hands resolve_within. A tree before the lookup (a
    # --baseline run) has none to spend.
    url = "http://s.example.test/x.ts"

    def target(cid, raw, d):
        if hasattr(helper, "stream_lookup_refusal"):
            assert helper.stream_lookup_refusal(url, {"host": "p.example.test", "port": 80, "loopback": False,
                                                      "local": False}) == ""
        # The shape player_target returns, `shown` included (D-SINK-104).
        return {"id": cid, "url": url, "name": "X", "shown": "X", "headers": {"User-Agent": "u"}, "group": "G"}

    def resolve(host, port, timeout, limit=None):
        clock.t += timeout - _JUST_INSIDE
        return [(2, 1, 6, "", ("93.184.216.34", port))]

    real_spawn = helper.spawn_player

    def spawn(argv, cwd, proxy_fd, control_fd, env=None):
        launched = real_spawn(argv, cwd, proxy_fd, control_fd, env)
        state["phase"] = "bind"
        state["bind_at"] = clock.t
        return launched

    # D-SINK-102: the relay, at its bounds. Its listeners are doubles (nothing
    # is bound), its port the one the found player's command line names; a
    # spawned relay refuses its status at once (as one not yet listening
    # again does) until RELAY_IPC_S before RELAY_START_S runs out, and from
    # then on answers just inside the bound the code hands each question, so
    # the wait spends RELAY_START_S whole with its last question at its own
    # bound (min(RELAY_IPC_S, the time left): the conformance
    # review; `learned["relay_tries"]` holds the bounds it was handed); and
    # every other question -- the adopted player's status, the load's
    # registration, the first-load count -- just inside the bound the code
    # hands relay_request.
    walk_port = 40000

    class Listener:
        def getsockname(self):
            return ("127.0.0.1", walk_port)

        def fileno(self):
            return -1

        def close(self):
            pass

    def relay_request(sock_path, request, peer, timeout=None, relay_pid=0):
        timeout = helper.RELAY_IPC_S if timeout is None else timeout
        op = request.get("op")
        if op == "status" and state["phase"] in ("bind", "spawned"):
            if state.get("relay_up_at") is None:
                state["relay_up_at"] = clock.t + helper.RELAY_START_S - helper.RELAY_IPC_S
            if clock.t < state["relay_up_at"]:
                return None
            learned.setdefault("relay_tries", []).append(timeout)
        clock.t += timeout - _JUST_INSIDE
        reply = {"ok": True, "port": walk_port, "build": helper.player_build(), "_pid": 4243}
        if op == "load":
            reply.update(token="a" * 32)
        if op == "count":
            reply.update(refused=0, upstream=1)
        return reply

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
                # what a player answers for the carry's reads (a volume, three
                # booleans), so the replace walk carries all four and sets
                # three; everything else it answers is the handshake's word
                return self.line(request, "success", _CARRY_ANSWERS.get(tuple(command[:2]), "mpv 0.41.0"))
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
                           # lane-p1c (2026-10-29): and the pinned format
                           # list (D-SINK-62), prefetch and the console off.
                           helper.MPV_DEMUXER_OPTS_PROP: {"protocol_whitelist": helper.MPV_PROTOCOL_WHITELIST,
                                                          "format_whitelist": helper.MPV_FORMAT_WHITELIST,
                                                          "tls_verify": "1"},
                           "prefetch-playlist": False, "load-console": False,
                           helper.MPV_AUTO_PROFILES_PROP: False, helper.MPV_RESET_PROP: [],
                           "drag-and-drop": False,
                           "script-opts": {helper.MPV_OSC_TITLE_KEY: helper.MPV_OSC_TITLE_VALUE},
                           # D-SINK-102: and the relay pin, at the walk's port.
                           "http-proxy": "http://127.0.0.1:%d" % walk_port}
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
            if state["phase"] == "play":
                self.sock = Sock(None)
                return
            if state["phase"] == "bind":
                learned["bind_last"] = clock.t - state["bind_at"]
                if bind_after is None or clock.t < state["bind_at"] + bind_after:
                    self.refused = True
                    raise helper.HelperError("not_running", "refused")
            clock.t += self.timeout - _JUST_INSIDE
            if state["phase"] in ("found", "gone"):
                self.sock = Sock(survivor_answers)
            else:
                # The new player: answers its handshake just inside the
                # bound, then everything at once but the one request after
                # the loadfile whose timeout the verb survives.
                state["phase"] = "spawned"
                self.sock = Sock(1 + spawned_slow, then_all=True)

    patches = [
        mock.patch.object(helper, "time", types.SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep, time=clock.time)),
        mock.patch.object(helper, "fcntl", types.SimpleNamespace(flock=flock, LOCK_EX=2, LOCK_NB=4)),
        mock.patch.object(helper, "find_player", find_player),
        mock.patch.object(helper, "still_the_player", still_the_player),
        mock.patch.object(helper, "stop_ladder", stop_ladder),
        mock.patch.object(helper, "proc_start_time", lambda pid: "1"),
        mock.patch.object(helper, "limit_core_of", lambda pid: True),

        mock.patch.object(helper, "_read_pipe", read_pipe),
        mock.patch.object(helper, "spawn_player", spawn),
        mock.patch.object(helper, "MpvIpc", Ipc),
        mock.patch.object(helper, "emit", replies.append),
        mock.patch.object(helper, "log", lambda message: None),
        mock.patch.object(helper, "player_target", target),
        mock.patch.object(helper, "resolve_within", resolve),
        mock.patch.object(helper, "player_dirs", lambda s, o=None: {
            "cwd": folder, "screenshots": folder, "watchLater": folder, "shaderCache": folder}),
        mock.patch.object(helper, "ensure_player_dirs", lambda dirs, warnings: None),
        mock.patch.object(helper.os, "kill", lambda pid, number: signals.append(number)),
        mock.patch.object(helper.os, "fork", lambda: 2 ** 22 + 7),
        mock.patch.object(helper.os, "waitpid", mock.Mock(side_effect=ChildProcessError())),
    ]
    # Restart on adoption: who each connection reaches. The found player is
    # 777, the spawned one the pid its pipe reported (4242), and the found one
    # reads as another build's when the walk says so -- the verdict is not
    # this walk's subject; the time it costs is.
    if hasattr(helper, "player_peer"):          # a tree before the gate (a --baseline run) has neither
        patches += [mock.patch.object(helper, "player_peer", lambda client: 777 if state["phase"] == "found" else 4242),
                    mock.patch.object(helper, "launch_verdict",
                                      lambda pid, sock: "older" if older and pid == 777 else "current")]
    if hasattr(helper, "relay_request"):        # a tree before the relay (a --baseline run) has none
        patches += [mock.patch.object(helper, "launch_reading",
                                      lambda pid, sock: ("older", None) if older and pid == 777 else ("current", walk_port)),
                    mock.patch.object(helper, "relay_request", relay_request),
                    mock.patch.object(helper, "bind_relay_listeners", lambda sock: (Listener(), Listener())),
                    mock.patch.object(helper, "proc_parent", lambda pid: 4243)]
    for patch in patches:
        patch.start()
    try:
        parser = helper.build_parser()
        session = ["--socket", sock, "--cache-dir", folder, "--id", "t:x", "--seq", "3"]
        if verb == "probe":
            helper.player_probe(parser.parse_args(["player", "probe", "--socket", sock]))
        elif verb == "play":
            helper.cmd_play(parser.parse_args(["play", "--socket", sock, "--cache-dir", folder, "--id", "t:x"]))
        elif verb == "stop":
            helper.player_stop(parser.parse_args(["player", "stop", "--socket", sock, "--seq", "3"]))
        else:
            extra = ["--from", "term"] if verb == "restart" else []
            helper.player_start(parser.parse_args(["player", verb] + session + extra), verb)
    finally:
        for patch in reversed(patches):
            patch.stop()
        shutil.rmtree(folder, ignore_errors=True)
    return clock.t, (replies[-1] if replies else None), signals, learned


def walk_long_path(verb, **more):
    """The three walks the comment above describes, for start or restart."""
    _, refused, _, learned = walk_player_verb(verb, **more)
    assert (refused or {}).get("error", {}).get("code") == "busy", refused
    lock_at = learned["lock_last"]
    _, unbound, _, learned = walk_player_verb(verb, lock_at=lock_at, **more)
    assert (unbound or {}).get("error", {}).get("code") == "no_socket", unbound
    return walk_player_verb(verb, lock_at=lock_at, bind_after=learned["bind_last"], **more)


def walk_stop_long_path():
    """D-PLY-40: the stop's three walks. The first is refused the lock
    throughout and learns its last poll; the second is granted it then and
    meets a player that accepts the quit rung's connect just inside the bound,
    never answers the quit, and outlives SIGTERM and SIGKILL, learning when
    the ladder ends; the third is the same with the player's process gone at
    that moment, its socket still accepting -- so the settle after the ladder
    makes its one connect too, at its bound. That is the longest path through
    player_stop: a player that stays is answered at once (the finder sees
    it), and one gone earlier is settled inside the rung that saw it go."""
    _, refused, _, learned = walk_player_verb("stop")
    assert (refused or {}).get("error", {}).get("code") == "busy", refused
    lock_at = learned["lock_last"]
    _, stayed, signals, learned = walk_player_verb("stop", lock_at=lock_at)
    assert stayed and stayed.get("ok") and stayed.get("running") is True and signals == [15, 9], (stayed, signals)
    return walk_player_verb("stop", lock_at=lock_at, vanish_at=learned["ladder_end"])


class PlayerWorstPathWalkTest(unittest.TestCase):

    def assert_inside_its_watchdog(self, verb, spent):
        budget = (BOUNDS["watchdogMs"][verb] - BOUNDS["marginMs"]) / 1000.0
        self.assertLessEqual(spent, budget, "player %s walked %.3f s, past its watchdog's %.3f s less the margin"
                             % (verb, spent, budget))

    def assert_the_relay_wait_spent_its_bound(self, learned):
        """The spawn's wait for its relay asked its last question with the
        bound a relay question has, RELAY_IPC_S less what the poll had
        already spent of it, and never more: each question had 10 ms before
        the conformance review, and the wait's walk then spent
        about RELAY_IPC_S less than RELAY_START_S."""
        tries = learned.get("relay_tries") or []
        self.assertTrue(tries, "the walk's spawn never asked its relay")
        self.assertLessEqual(max(tries), helper.RELAY_IPC_S)
        self.assertGreater(max(tries), helper.RELAY_IPC_S - 2 * helper.SPAWN_POLL_S, tries)

    def test_a_start_that_meets_a_wedged_player_fits_its_watchdog(self):
        spent, reply, signals, learned = walk_long_path("start")
        self.assertTrue(reply and reply.get("ok"), reply)
        self.assertEqual(signals, [15, 9])            # one ladder, from quit
        self.assertGreater(spent, 37.0)               # the long path really was walked
        self.assert_the_relay_wait_spent_its_bound(learned)
        self.assert_inside_its_watchdog("start", spent)

    def test_a_start_that_replaces_another_builds_player_fits_its_watchdog(self):
        """Restart on adoption (T9, the lane's M9): the replace branch. The
        found player answers EVERY request just inside the bound -- its
        handshake, each read of the carry, the quit -- and never dies, so the
        whole ladder runs; the new player answers its handshake and each set
        of the carry just inside the bound too. The carry is held to ONE
        ipcMs a side (bounded_requests), which is the 2 * ipcMs the start's
        bound gained over the wedged path (player-bounds.json)."""
        spent, reply, signals, _ = walk_long_path("start", survivor_answers=10 ** 6, older=True, spawned_slow=3)
        self.assertTrue(reply and reply.get("ok"), reply)
        self.assertEqual(reply.get("replaced"), 1)
        self.assertEqual(signals, [15, 9])            # one ladder, from quit
        self.assertGreater(spent, 41.0)               # the long path really was walked
        self.assert_inside_its_watchdog("start", spent)

    def test_a_restart_whose_ladder_leaves_the_player_fits_its_watchdog(self):
        spent, reply, signals, learned = walk_long_path("restart")
        self.assertTrue(reply and reply.get("ok"), reply)
        self.assertEqual(signals, [15, 9, 15, 9])     # its own ladder, then adopt_or_spawn's
        self.assertGreater(spent, 40.0)
        self.assert_the_relay_wait_spent_its_bound(learned)
        self.assert_inside_its_watchdog("restart", spent)

    def test_a_play_leaves_mpvs_round_trips_what_its_8_s_left_them(self):
        """D-SINK-102: `play` asks the relay two questions, the gate's
        status (feed_gate, player_verdict) and the load's registration
        (relay_register), each bounded by RELAY_IPC_S, beside the play-time
        lookup. Walked through the shipping cmd_play with those at their
        bounds and the player answering at once, what the walk leaves of
        Model.playerWatchdogMs("play") is what is left for mpv's round
        trips, and it may not be less than the 8 s left them before the
        relay (`controlMs` less the lookup, 5 s). Red when the watchdog
        summed one question (9 s, 4 s left: the review of 7c281d8), and red
        for a third question asked on the way."""
        spent, reply, signals, _ = walk_player_verb("play")
        self.assertTrue(reply and reply.get("ok"), reply)
        self.assertEqual(signals, [])
        h = BOUNDS["helper"]
        self.assertGreater(spent, (h["lookupMs"] + 2 * h["relayIpcMs"]) / 1000.0 - 0.01)   # both questions were asked
        left = BOUNDS["watchdogMs"]["play"] / 1000.0 - spent
        self.assertGreaterEqual(left, (BOUNDS["controlMs"] - h["lookupMs"]) / 1000.0,
                                "play's watchdog leaves mpv's round trips %.3f s, less than the %.3f s its 8 s left them"
                                % (left, (BOUNDS["controlMs"] - h["lookupMs"]) / 1000.0))

    def test_a_stop_that_waits_out_the_lock_and_the_whole_ladder_fits_its_backstop(self):
        """D-PLY-40: Service.qml's stopSettleTimer waits out the detached
        stop's own worst path (Model.playerWatchdogMs("stop"), the fixture's
        `stop`) before it reads the stop as one that did not take. Walked
        through the shipping player_stop: 13.25 s -- the lock's 6.05, the
        ladder's 7 and the settle's one connect -- inside 18.25 s less the
        margin, and past the 5 s the backstop was, which is the row."""
        spent, reply, signals, _ = walk_stop_long_path()
        self.assertTrue(reply and reply.get("ok") and reply.get("running") is False, reply)
        self.assertEqual(signals, [15, 9])            # one ladder, from quit
        self.assertGreater(spent, 13.2)               # the long path really was walked
        self.assertGreater(spent, 5.0)                # past the old backstop
        self.assert_inside_its_watchdog("stop", spent)

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
