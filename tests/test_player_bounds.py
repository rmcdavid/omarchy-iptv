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
    # D-PLY-39: a loop that turns over without the time moving -- a wait cut
    # to nothing by a deadline and asked again -- would never end on this
    # clock, where on a real one it spins until its own bound. So the clock
    # counts its reads and fails the walk past a million, which no walk here
    # comes near (the longest reads it a few thousand times).
    READS_MAX = 1000000

    def __init__(self):
        self.t = 0.0
        self.reads = 0

    def monotonic(self):
        self.reads += 1
        if self.reads > self.READS_MAX:
            raise AssertionError("the clock was read %d times with the time at %.3f s: a loop that turns over "
                                 "without the time moving" % (self.reads, self.t))
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
                     vanish_at=None, slow=False, mpv_args=None, unsafe=False, slow_load=False):
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
    player leaves it (D-PLY-8); None for never.

    D-PLY-39, mpv answering EVERY request just inside its bound: `slow` --
    the player this verb spawns, the one `play` reaches and the one the
    control verbs (`status`, `pause`, `tracks`, `seek`) find answer every
    connect and every request just inside the bound the code hands it, with
    the answers a player of this build gives (the pin block's readings, the
    handshake's version, the carry's values), so the verb gets as far as
    mpv's time lets it; the player a spawn launched is then also one the
    finder sees, so a start that stops what it spawned really ladders it
    (stop_fresh_spawn). `survivor_answers` None: the found player does the
    same. `mpv_args`: the user's tokens, so the spawn writes its 0600
    include file (D-SINK-47) and must remove it on every way out. `unsafe`:
    every player reads `tls-verify` false (a probe migrates it). `slow_load`:
    the spawned player answers its loadfile just inside the bound too.
    `learned` then holds the commands sent (`sent`, name and first argument,
    in order, across every connection), how many relay listeners were closed
    (`closed`) and what the runtime folder held when the verb returned
    (`leftover`)."""
    clock = _Clock()
    state = {"phase": "play" if verb == "play" else "found", "bind_at": None, "pipes": 0}
    learned = {"lock_last": None, "bind_last": None}
    survivor = {"pid": 777, "startTime": "1"}
    spawned = {"pid": 4242, "startTime": "1"}
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
        if not gone():
            return [dict(survivor)]
        return [dict(spawned)] if slow and state["phase"] == "spawned" else []

    def still_the_player(record, _sock):
        if record.get("pid") == survivor["pid"]:
            return not gone()
        return slow and state["phase"] == "spawned" and record.get("pid") == spawned["pid"]

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
            learned["closed"] = learned.get("closed", 0) + 1

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
        def __init__(self, answers, then_all=False, slow_all=False):
            self.answers = answers          # requests answered just inside the bound; None: all, at once
            self.then_all = then_all        # after those: quiet (False) or answering at once (True)
            self.slow_all = slow_all        # D-PLY-39: "at once" becomes "just inside the bound"
            self.timeout = None
            self.pending = []
            self.loaded = False

        def settimeout(self, value):
            self.timeout = value

        def sendall(self, data):
            request = json.loads(data.decode("utf-8"))
            learned.setdefault("sent", []).append(" ".join(str(part) for part in request["command"][:2]))
            self.pending.append(request)

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
                           "http-proxy": "http://127.0.0.1:%d" % walk_port,
                           # D-PLY-39: the handshake's version and the
                           # carry's values, so a player that answers every
                           # request slowly answers them as one of this build.
                           "mpv-version": "mpv 0.41.0"}
                answers.update({prop: value for (verb_, prop), value in _CARRY_ANSWERS.items()})
                if unsafe:
                    answers[helper.MPV_TLS_VERIFY_PROP] = False
                for option in helper.PER_FILE_TLS_OPTIONS:
                    answers["option-info/%s/set-from-commandline" % option] = True
                data = answers.get(command[1])
                if data is None:
                    error = "property unavailable"
            elif command[0] == "loadfile":
                data = {"playlist_entry_id": 1}
                self.loaded = True
                if slow_load:
                    clock.t += self.timeout - _JUST_INSIDE
            if self.slow_all:
                clock.t += self.timeout - _JUST_INSIDE
            if command[0] == "loadfile":
                learned["loaded_at"] = clock.t
            return self.line(request, error, data)

        @staticmethod
        def line(request, error, data):
            return (json.dumps({"request_id": request["request_id"], "error": error, "data": data}) + "\n").encode("utf-8")

    class Ipc(_REAL_IPC):
        def connect(self):
            # D-PLY-39: the shipping check of the verb's mpv deadline runs
            # first, as it does in MpvIpc.connect (a tree before it has none).
            if hasattr(helper, "ipc_wait_bound"):
                helper.ipc_wait_bound(self.timeout)
            if state["phase"] == "play":
                if slow:
                    clock.t += self.timeout - _JUST_INSIDE
                self.sock = Sock(None, slow_all=slow)
                return
            if state["phase"] == "bind":
                learned["bind_last"] = clock.t - state["bind_at"]
                if bind_after is None or clock.t < state["bind_at"] + bind_after:
                    self.refused = True
                    raise helper.HelperError("not_running", "refused")
            clock.t += self.timeout - _JUST_INSIDE
            if state["phase"] in ("found", "gone"):
                self.sock = Sock(None, slow_all=True) if survivor_answers is None else Sock(survivor_answers)
            else:
                # The new player: answers its handshake just inside the
                # bound, then everything at once but the one request after
                # the loadfile whose timeout the verb survives.
                state["phase"] = "spawned"
                self.sock = Sock(None, slow_all=True) if slow else Sock(1 + spawned_slow, then_all=True)

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
        elif verb == "status":
            helper.cmd_status(parser.parse_args(["status", "--socket", sock]))
        elif verb == "pause":
            helper.player_pause(parser.parse_args(["player", "pause", "--socket", sock, "--state", "off"]))
        elif verb == "tracks":
            helper.player_tracks(parser.parse_args(["player", "tracks", "--socket", sock, "--audio", "2"]))
        elif verb == "seek":
            helper.player_seek(parser.parse_args(["player", "seek", "--socket", sock, "--by", "-10"]))
        else:
            extra = ["--from", "term"] if verb == "restart" else []
            for token in mpv_args or []:
                extra += ["--mpv-arg=" + token]
            helper.player_start(parser.parse_args(["player", verb] + session + extra), verb)
    finally:
        for patch in reversed(patches):
            patch.stop()
        learned["leftover"] = sorted(os.listdir(folder))
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
        # D-PLY-39: held against play's BOUND, the watchdog less the margin,
        # which the helper now runs it inside -- the share left there for
        # mpv's round trips is controlIpcMs, the 5 s the 8 s left them.
        left = _bound_s("play") - spent
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



# ---- D-PLY-39 (2026-11-18): each watched verb ends inside its own bound ----
#
# Every wait on mpv was bounded and no verb was: an mpv answering each of a
# start's twenty-odd requests just inside 2 s ran it to about 80 s against
# its watchdog. Now the helper runs each watched verb under a deadline -- its
# bound (the fixture's watchdogMs less marginMs, which the helper derives
# from its own constants: player_verb_bound_ms) less its reserve -- and a
# wait on mpv that cannot have its whole bound before it is refused unsent
# as `ipc_error`. Below: the join of the helper's bounds to the fixture; the
# walk of every watched verb with mpv answering EVERY request just inside
# its bound, held inside the bound; where the deadline lands and what each
# verb leaves there (the lock, the spawn, the relay's listeners, the include
# file, the migration mark); and the client's own rule. Red on 71700f4,
# which has no deadline: the walks run to 79-100 s for a start.

def _bound_s(verb):
    return (BOUNDS["watchdogMs"][verb] - BOUNDS["marginMs"]) / 1000.0


def _open_fds():
    return len(os.listdir("/proc/self/fd"))


def walk_locked(verb, **more):
    """walk_long_path's first two steps for a verb that spawns nothing: the
    lock refused throughout (its last poll learned), then granted there."""
    _, refused, _, learned = walk_player_verb(verb, **more)
    assert (refused or {}).get("error", {}).get("code") == "busy", refused
    return walk_player_verb(verb, lock_at=learned["lock_last"], **more)


class VerbBoundJoinTest(unittest.TestCase):

    def test_each_watched_verbs_bound_is_the_fixtures_watchdog_less_the_margin(self):
        for verb in ("start", "restart", "probe", "play", "stop"):
            with self.subTest(verb=verb):
                self.assertEqual(helper.player_verb_bound_ms(verb), BOUNDS["watchdogMs"][verb] - BOUNDS["marginMs"])

    def test_the_control_slots_verbs_share_its_one_bound(self):
        # One Timer watches the control slot (Service.qml controlWatchdog,
        # Model.playerWatchdogMs("play")), so every verb it runs has play's.
        for verb in ("status", "pause", "tracks", "seek"):
            with self.subTest(verb=verb):
                self.assertEqual(helper.player_verb_bound_ms(verb), helper.player_verb_bound_ms("play"))
        with self.assertRaises(ValueError):
            helper.player_verb_bound_ms("relay")

    def test_the_control_share_is_what_the_8_s_left_mpv(self):
        h = BOUNDS["helper"]
        self.assertEqual(h["controlIpcMs"], BOUNDS["controlMs"] - h["lookupMs"])

    def test_each_reserve_is_what_the_verb_may_spend_after_its_last_wait_on_mpv(self):
        h = BOUNDS["helper"]
        ladder_term = h["killGraceMs"] + 2 * h["settleMs"]
        start = max(h["firstLoadMs"] + h["relayIpcMs"], ladder_term + h["settleConnectMs"])
        want = {"start": start, "restart": start, "status": h["relayIpcMs"], "probe": 0, "play": 0,
                "pause": 0, "tracks": 0, "seek": 0}
        for verb, reserve in want.items():
            with self.subTest(verb=verb):
                self.assertEqual(helper.player_verb_reserve_ms(verb), reserve)
                self.assertEqual(helper.player_verb_ipc_span_ms(verb), helper.player_verb_bound_ms(verb) - reserve)
                self.assertGreater(helper.player_verb_ipc_span_ms(verb), 0)


class VerbDeadlineWalkTest(unittest.TestCase):
    """The walks with mpv answering every request just inside its bound."""

    def assert_inside_its_bound(self, verb, spent, bound_of=None):
        bound = _bound_s(bound_of or verb)
        self.assertLessEqual(spent, bound, "%s walked %.3f s with mpv answering every request just inside its "
                             "bound, past its own %.3f s" % (verb, spent, bound))

    def assert_refused_in_time(self, reply, kind):
        self.assertIsNotNone(reply)
        self.assertFalse(reply.get("ok"), reply)
        self.assertEqual(reply.get("kind"), kind)
        self.assertEqual(reply["error"]["code"], "ipc_error")
        self.assertEqual(reply["error"]["message"], helper.IPC_DEADLINE_REFUSAL)

    def test_a_start_over_an_adopted_player_that_answers_everything_slowly(self):
        """The current player is adopted, pinned and fed: the deadline lands in
        its pins or the load's TLS assertion, the start answers ipc_error, and
        that player -- the one the shell already plays on -- is neither fed a
        load nor signalled."""
        fds = _open_fds()
        spent, reply, signals, learned = walk_locked("start", survivor_answers=None)
        self.assert_refused_in_time(reply, "player.start")
        self.assertEqual(signals, [])
        self.assertNotIn("loadfile", " ".join(learned.get("sent", [])))
        # ended within one request's bound of its mpv deadline: it was reached
        self.assertGreater(spent, helper.player_verb_ipc_span_ms("start") / 1000.0 - helper.DEFAULT_IPC_TIMEOUT)
        self.assert_inside_its_bound("start", spent)
        self.assertEqual(_open_fds(), fds)

    def test_a_start_whose_spawn_answers_everything_slowly_stops_the_spawn(self):
        """A wedged player laddered, a spawn that answers every request just
        inside: the deadline lands before the load, so the spawn this start
        fed nothing is laddered down from term (stop_fresh_spawn, D-PLY-57),
        the lock released, both relay listeners closed and the include file
        removed -- what any refusal before the load leaves (D-PLY-39 (d))."""
        fds = _open_fds()
        spent, reply, signals, learned = walk_long_path("start", slow=True, mpv_args=["--volume=50"])
        self.assert_refused_in_time(reply, "player.start")
        self.assertEqual(signals, [15, 9, 15, 9])     # the wedged player's ladder, then the spawn's
        self.assertNotIn("loadfile", " ".join(learned.get("sent", [])))
        self.assertEqual(learned.get("closed"), 2)
        self.assertEqual(learned.get("leftover"), ["player.lock"])
        self.assertEqual(_open_fds(), fds)
        self.assert_inside_its_bound("start", spent)

    def test_a_start_that_replaces_an_older_player_answering_everything_slowly(self):
        spent, reply, signals, learned = walk_long_path("start", survivor_answers=None, older=True, slow=True)
        self.assert_refused_in_time(reply, "player.start")
        self.assertEqual(signals, [15, 9, 15, 9])     # the older player's ladder, then the spawn's
        self.assertNotIn("loadfile", " ".join(learned.get("sent", [])))
        self.assert_inside_its_bound("start", spent)

    def test_a_restart_whose_spawn_answers_everything_slowly(self):
        spent, reply, signals, _ = walk_long_path("restart", slow=True)
        self.assert_refused_in_time(reply, "player.restart")
        self.assertEqual(signals, [15, 9, 15, 9, 15, 9])
        self.assert_inside_its_bound("restart", spent)

    def test_a_start_whose_deadline_lands_after_its_load_keeps_its_window(self):
        """The load sent with its whole bound, the bookkeeping after it
        refused unsent (its failure is caught there, as a closed connection's
        is), and the first-load window run to its end, uncut: the reply is
        the ok of a start that loaded, and the walk ends inside the bound."""
        spent, reply, signals, learned = walk_long_path("start", spawned_slow=LANDS_AFTER_THE_LOAD, slow_load=True)
        self.assertTrue(reply and reply.get("ok"), reply)
        sent = learned.get("sent", [])
        self.assertIn("loadfile", " ".join(sent))
        after = sent[[s.split(" ")[0] for s in sent].index("loadfile") + 1:]
        self.assertEqual(after, [], "a request after the load was sent past the deadline: %r" % after)
        self.assertEqual(reply["firstLoad"]["state"], "unknown")
        # the window ran its whole bound after the load, uncut by the deadline
        self.assertAlmostEqual(spent - learned["loaded_at"], helper.DEFAULT_FIRST_LOAD_TIMEOUT, places=3)
        self.assertGreater(learned["loaded_at"] + helper.DEFAULT_IPC_TIMEOUT,
                           _bound_s("start") - helper.player_verb_reserve_ms("start") / 1000.0)
        self.assert_inside_its_bound("start", spent)

    def test_a_probe_that_answers_everything_slowly(self):
        spent, reply, signals, learned = walk_player_verb("probe", survivor_answers=None)
        self.assert_refused_in_time(reply, "player.probe")
        self.assertFalse(reply.get("running"))
        self.assertEqual(signals, [])
        self.assertEqual([s for s in learned.get("sent", []) if s.startswith("set_property")], [])
        self.assert_inside_its_bound("probe", spent)

    def test_a_play_whose_player_answers_everything_slowly(self):
        spent, reply, signals, learned = walk_player_verb("play", slow=True)
        self.assert_refused_in_time(reply, "play")
        self.assertNotIn("loadfile", " ".join(learned.get("sent", [])))
        self.assert_inside_its_bound("play", spent)

    def test_the_control_verbs_whose_player_answers_everything_slowly(self):
        for verb, kind in (("status", "status"), ("pause", "player.pause"), ("seek", "seek"), ("tracks", "player.tracks")):
            with self.subTest(verb=verb):
                spent, reply, signals, _ = walk_player_verb(verb, survivor_answers=None, slow=True)
                self.assertIsNotNone(reply)
                if verb == "tracks":
                    # Four requests, 8 s: inside the deadline, so it answers.
                    self.assertTrue(reply.get("ok"), reply)
                else:
                    self.assert_refused_in_time(reply, kind)
                self.assertEqual(signals, [])
                self.assert_inside_its_bound(verb, spent, "play")


# The spawn's slow requests after its handshake (its loadfile slow too) that
# put the start's load across its mpv deadline on the wedged path -- begun
# with its whole bound left, answered with less than a request's left -- held
# by the companion below, which fails if the number stops landing it there.
LANDS_AFTER_THE_LOAD = 2


class DeadlineLandingTest(unittest.TestCase):

    def test_the_after_the_load_walk_really_lands_its_deadline_between_the_load_and_the_bookkeeping(self):
        spent, reply, _, learned = walk_long_path("start", spawned_slow=LANDS_AFTER_THE_LOAD, slow_load=True)
        sent = learned.get("sent", [])
        names = [s.split(" ")[0] for s in sent]
        self.assertIn("loadfile", names)
        self.assertEqual(names[-1], "loadfile")          # nothing after it went out
        # and with one slow request fewer the bookkeeping does go out, so the
        # number is the one that lands it there
        _, _, _, earlier = walk_long_path("start", spawned_slow=LANDS_AFTER_THE_LOAD - 1, slow_load=True)
        self.assertNotEqual([s.split(" ")[0] for s in earlier.get("sent", [])][-1], "loadfile")


class IpcDeadlineRuleTest(unittest.TestCase):
    """MpvIpc under a verb's deadline, on a double that answers as mpv does."""

    def setUp(self):
        self.clock = _Clock()
        self.patch = mock.patch.object(helper, "time", types.SimpleNamespace(
            monotonic=self.clock.monotonic, sleep=self.clock.sleep, time=self.clock.time))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(lambda: helper.IPC_DEADLINE.__setitem__(0, None))

    def client(self, delays=None, events=None):
        clock = self.clock
        sent = []
        unasked = list(events or [])

        class FakeSock:
            def __init__(self):
                self.timeout = None
                self.pending = []

            def settimeout(self, value):
                self.timeout = value

            def sendall(self, data):
                request = json.loads(data.decode("utf-8"))
                sent.append(request["command"])
                self.pending.append(request)

            def recv(self, _size):
                if not self.pending and unasked:
                    # an event mpv sends unasked, a moment into the wait
                    clock.t += 0.5
                    return (json.dumps(unasked.pop(0)) + "\n").encode()
                if not self.pending:
                    clock.t += self.timeout
                    raise TimeoutError()
                request = self.pending.pop(0)
                clock.t += (delays or {}).get(tuple(request["command"][:2]), 0.0)
                return (json.dumps({"request_id": request["request_id"], "error": "success", "data": None}) + "\n").encode()

            def close(self):
                pass

        ipc = helper.MpvIpc("/nonexistent-ply39/mpv.sock", helper.DEFAULT_IPC_TIMEOUT)
        ipc.sock = FakeSock()
        return ipc, sent

    def test_a_request_that_cannot_have_its_whole_bound_is_refused_unsent(self):
        ipc, sent = self.client()
        helper.IPC_DEADLINE[0] = self.clock.t + helper.DEFAULT_IPC_TIMEOUT - 0.01
        with self.assertRaises(helper.HelperError) as caught:
            ipc.request(["loadfile", "x", "replace"])
        self.assertEqual((caught.exception.code, caught.exception.message), ("ipc_error", helper.IPC_DEADLINE_REFUSAL))
        self.assertEqual(sent, [])
        self.assertEqual(self.clock.t, 0.0)

    def test_one_that_can_is_sent_and_waited_its_whole_bound(self):
        ipc, sent = self.client(delays={("get_property", "x"): helper.DEFAULT_IPC_TIMEOUT - 0.001})
        helper.IPC_DEADLINE[0] = self.clock.t + helper.DEFAULT_IPC_TIMEOUT
        self.assertEqual(ipc.request(["get_property", "x"]).get("error"), "success")
        self.assertEqual(sent, [["get_property", "x"]])
        with self.assertRaises(helper.HelperError):
            ipc.request(["get_property", "y"])
        self.assertEqual(sent, [["get_property", "x"]])

    def test_a_connect_that_cannot_have_its_bound_is_not_begun(self):
        ipc = helper.MpvIpc("/nonexistent-ply39/mpv.sock", helper.DEFAULT_IPC_TIMEOUT)
        helper.IPC_DEADLINE[0] = self.clock.t + 0.5
        with self.assertRaises(helper.HelperError) as caught:
            ipc.connect()
        self.assertEqual(caught.exception.code, "ipc_error")
        self.assertIsNone(ipc.sock)

    def test_an_event_wait_ends_at_the_deadline_and_the_first_load_window_does_not(self):
        """drain_events ends at the deadline; the first-load window, lifted,
        still reads the socket after it and sees the load's file-loaded. (A
        window held to the deadline would read nothing past it and turn over
        until its own end -- three seconds of a spinning loop -- so the clock
        here moves a millisecond each time it is read, and that window ends
        "unknown" rather than never.)"""
        ipc, _ = self.client()
        helper.IPC_DEADLINE[0] = self.clock.t + 0.5
        self.assertEqual(ipc.drain_events(self.clock.t + 3.0), [])
        self.assertAlmostEqual(self.clock.t, 0.5)
        ipc, _ = self.client(events=[{"event": "file-loaded"}])
        clock = self.clock

        def ticking():
            clock.t += 0.001
            return clock.t

        with mock.patch.object(helper, "time", types.SimpleNamespace(monotonic=ticking, sleep=clock.sleep, time=clock.time)):
            result = helper.observe_first_load(ipc, 1, 3.0)
        self.assertEqual(result["state"], "playing")
        self.assertLess(clock.t, 1.1)
        self.assertEqual(helper.IPC_DEADLINE[0], 0.5)    # put back after the window

    def test_the_seeks_event_wait_ends_at_the_deadline(self):
        """await_seek_outcome loops until its own bound (SEEK_EVENT_BOUND_S)
        over drain_events, which returns at once past the verb's deadline;
        the loop's own deadline is capped too, so it ends there rather than
        turning over until its bound. A clock that moves a millisecond each
        time it is read, so an uncapped loop ends at its bound, not never."""
        ipc, _ = self.client()
        clock = self.clock

        def ticking():
            clock.t += 0.001
            return clock.t

        with mock.patch.object(helper, "time", types.SimpleNamespace(monotonic=ticking, sleep=clock.sleep, time=clock.time)):
            helper.IPC_DEADLINE[0] = clock.t + 0.05
            outcome = helper.await_seek_outcome(ipc, clock.t + helper.SEEK_EVENT_BOUND_S)
        self.assertEqual(outcome, (None, False))
        self.assertLess(clock.t, 0.06)

    def test_outside_a_verb_nothing_changes(self):
        ipc, sent = self.client(delays={("get_property", "x"): 1.9})
        self.assertIsNone(helper.IPC_DEADLINE[0])
        ipc.request(["get_property", "x"])
        ipc.request(["get_property", "x"])
        self.assertEqual(len(sent), 2)
        self.assertAlmostEqual(self.clock.t, 3.8)

    def test_the_verb_sets_its_deadline_and_puts_it_back_whatever_it_does(self):
        seen = []

        @helper.verb_deadline("probe")
        def returns(args):
            seen.append(helper.IPC_DEADLINE[0])
            return 7

        @helper.verb_deadline(None)
        def raises(args, verb="start"):
            seen.append(helper.IPC_DEADLINE[0])
            raise helper.HelperError("x", "y")

        self.assertEqual(returns(None), 7)
        with self.assertRaises(helper.HelperError):
            raises(None, "restart")
        self.assertIsNone(helper.IPC_DEADLINE[0])
        self.assertEqual(seen, [helper.player_verb_ipc_span_ms("probe") / 1000.0,
                                helper.player_verb_ipc_span_ms("restart") / 1000.0])
        helper.IPC_DEADLINE[0] = 1.0
        returns(None)
        self.assertEqual(seen[-1], 1.0)                  # never moved later
        self.assertEqual(helper.IPC_DEADLINE[0], 1.0)

    def test_a_probe_never_writes_a_migration_without_its_mark(self):
        """D-SINK-72 under the deadline: the probe marks a player it must
        migrate BEFORE it writes, and a request refused for the deadline is
        refused unsent, so wherever the deadline lands no write goes out
        without a mark mpv answered. Two landings: the last reading slow
        enough that the mark cannot have its bound (nothing written, no
        mark), and the mark slow enough that no write can (marked, nothing
        written)."""
        unsafe = {helper.MPV_TLS_VERIFY_PROP: False}
        for slow_one, marked in ((("get_property", helper.MPV_HTTP_PROXY_PROP), False),
                                 (("set_property", helper.USER_DATA_TLS), True)):
            with self.subTest(slow=slow_one):
                self.clock.t = 0.0
                ipc, sent = self.client(delays={slow_one: helper.DEFAULT_IPC_TIMEOUT - 0.05})
                original = ipc.request

                def request(command, allow_close=False, original=original):
                    reply = original(command, allow_close)
                    if command[0] == "get_property":
                        reply["data"] = unsafe.get(command[1])
                        if reply["data"] is None:
                            reply["error"] = "property unavailable"
                    return reply

                ipc.request = request
                helper.IPC_DEADLINE[0] = self.clock.t + 2 * helper.DEFAULT_IPC_TIMEOUT - 0.1
                with self.assertRaises(helper.HelperError):
                    helper.migrate_tls(ipc, 40000)
                writes = [c for c in sent if c[0] in ("set_property", "change-list") and c[1] != helper.USER_DATA_TLS]
                marks = [c for c in sent if c[:2] == ["set_property", helper.USER_DATA_TLS]]
                self.assertEqual(writes, [])
                self.assertEqual(bool(marks), marked)


if __name__ == "__main__":
    unittest.main()
