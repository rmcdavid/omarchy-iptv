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


if __name__ == "__main__":
    unittest.main()
