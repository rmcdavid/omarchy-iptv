"""M5-01 live rewind: `player seek` and the `rewind` object the `status`,
`pause` and `probe` replies carry (docs/M5-01-LIVE-REWIND.md 2.1 and 2.2),
against the FakeMpv that test_mpv.py taught the seek semantics
docs/SPIKE-LIVE-REWIND.md 11.4 and 12.2 measured -- `success` with no
movement below the floor or past the end, a negative absolute target counting
from the cache end -- and a real token-carrying process for find_player.

The two shared fixtures, tests/fixtures/rewind-clamp.json and
tests/fixtures/rewind-osd.json, are run here over the python mirrors and by
tests/Model.test.js over Model.clampSeek / Model.rewindOsdText: a rule written
twice gets one fixture (CLAUDE.md). Every test here was seen red by a named
mutation of the shipping function (rule 11); the commit message lists them.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import unittest

import helper_loader  # noqa: F401  (the sandboxed HOME, before the helper loads)
# The SAME module object test_player's `run` executes, not a second load:
# the zero-point clock is held still by patching that object, and a patch on
# a private copy would hold nothing the verb under test reads.
from test_player import PASSWORD, TOKEN, PlayerTestCase, helper, run

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLAMP_FIXTURE = ROOT / "tests" / "fixtures" / "rewind-clamp.json"
OSD_FIXTURE = ROOT / "tests" / "fixtures" / "rewind-osd.json"

# The ABC KAAL plateau (spike 11.3): range [44.028, 418.001], reader at 400.617.
PLATEAU_RANGE = [{"start": 44.028, "end": 418.001}]
# Every leaf of `demuxer-cache-state` as the real player sent it (12.1): the
# twelve forwarded ones, the eight dropped ones, and the one string.
REAL_CACHE_STATE = {
    "bof-cached": False, "cache-duration": 16.725, "cache-end": 377.984,
    "debug-byte-level-seeks": 0, "debug-low-level-seeks": 0, "debug-ts-last": 43872.554,
    "eof": False, "eof-cached": False, "fw-bytes": 9505744, "idle": False,
    "raw-input-rate": 1383913, "reader-pts": 361.259,
    "seekable-ranges": [{"start": 6.015, "end": 375.984}],
    "total-bytes": 208700576,
    "ts-per-stream": [
        {"cache-duration": 16.783, "cache-end": 43889.471, "reader-pts": 43872.688, "type": "video"},
        {"cache-duration": 16.7, "cache-end": 43889.4, "reader-pts": 43872.6, "type": "audio"},
    ],
    "underrun": False,
}
SCHEMA_KEYS = ["ok", "kind", "running", "mode", "requested", "applied", "clamped", "clampedTo",
               "refused", "atFloor", "atEdge", "rewind"]
REWIND_KEYS = ["position", "floor", "ceiling", "history", "ahead", "behindLive", "zeroed",
               "paused", "pausedForCache", "entryId"]


class ClampFixtureTest(unittest.TestCase):
    """The python half of the shared clamp vectors."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(CLAMP_FIXTURE.read_text(encoding="utf-8"))

    def test_the_constants_are_the_measured_ones_and_the_fixture_carries_them(self):
        self.assertEqual((helper.SEEK_FLOOR_MARGIN_S, helper.SEEK_EDGE_MARGIN_S, helper.SEEK_MOVED_THRESHOLD_S), (2.0, 0.5, 0.5))
        self.assertEqual((self.fixture["floorMargin"], self.fixture["edgeMargin"], self.fixture["movedThreshold"]), (2.0, 0.5, 0.5))
        self.assertEqual(helper.BEHIND_LIVE_SHOW_S, 2)

    def test_every_shared_vector(self):
        self.assertGreaterEqual(len(self.fixture["cases"]), 20)
        for case in self.fixture["cases"]:
            self.assertEqual(helper.clamp_seek(case["in"]), case["out"], case["name"])

    def test_requested_keeps_the_integer_it_was_asked_as(self):
        # -10, not -10.0: the JSON a reader sees is the number the design shows.
        plan = helper.clamp_seek({"position": 400.617, "floor": 44.028, "ceiling": 418.001, "mode": "by", "by": -10})
        self.assertIs(type(plan["requested"]), int)
        self.assertIn('"requested": -10,', json.dumps(plan))

    def test_no_vector_and_no_plan_ever_yields_a_negative_target(self):
        # F-RWD-7: a negative absolute target is an offset from the cache END.
        for case in self.fixture["cases"]:
            target = helper.clamp_seek(case["in"])["target"]
            self.assertTrue(target is None or target >= 0, case["name"])
        for position in (0.0, 0.5, 1.0, 1.9, 5.0):
            plan = helper.clamp_seek({"position": position, "floor": 0.0, "ceiling": 30.0, "mode": "by", "by": -1000})
            self.assertGreaterEqual(plan["target"], 0.0)
            self.assertLessEqual(plan["target"], position)

    def test_the_fixture_covers_both_refusals_and_both_unissued_edges(self):
        outs = [case["out"] for case in self.fixture["cases"]]
        self.assertGreaterEqual(sum(1 for o in outs if o["ok"] is False), 3)
        self.assertGreaterEqual(sum(1 for o in outs if o["ok"] and not o["issue"] and o["atFloor"]), 2)
        self.assertGreaterEqual(sum(1 for o in outs if o["ok"] and not o["issue"] and o["atEdge"]), 2)
        self.assertGreaterEqual(sum(1 for o in outs if o["mode"] == "live"), 3)


class OsdFixtureTest(unittest.TestCase):
    """The python half of the shared OSD vectors, and the no-`$` rule."""

    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(OSD_FIXTURE.read_text(encoding="utf-8"))

    def test_every_shared_vector(self):
        self.assertGreaterEqual(len(self.fixture["cases"]), 12)
        for case in self.fixture["cases"]:
            self.assertEqual(helper.rewind_osd_text(case["reply"]), case["text"], case["name"])

    def test_no_text_carries_a_dollar_and_the_fixture_tries(self):
        poisoned = 0
        for case in self.fixture["cases"]:
            self.assertNotIn("$", case["text"], case["name"])
            self.assertNotIn("$", helper.rewind_osd_text(case["reply"]), case["name"])
            if "$" in json.dumps(case["reply"]):
                poisoned += 1
        self.assertGreaterEqual(poisoned, 1)

    def test_a_reply_made_of_strings_puts_nothing_on_screen(self):
        reply = {"refused": False, "atFloor": "${path}", "atEdge": "$>", "note": "$$",
                 "rewind": {"behindLive": "${path}", "position": "$", "paused": "${path}", "floor": "${path}"}}
        self.assertEqual(helper.rewind_osd_text(reply), "")
        self.assertEqual(helper.rewind_osd_text({"refused": False, "rewind": {"behindLive": 92, "paused": False, "title": "${path}"}}),
                         "-1:32 behind live")
        self.assertEqual(helper.rewind_osd_text(None), "")
        self.assertEqual(helper.rewind_osd_text("x"), "")

    def test_clock_span(self):
        self.assertEqual([helper.clock_span(s) for s in (0, 7, 59, 60, 92, 412.9, 3599, 3600, 3723, 36000, -5, None, "x", True)],
                         ["0:00", "0:07", "0:59", "1:00", "1:32", "6:52", "59:59", "1:00:00", "1:02:03", "10:00:00", "0:00", "0:00", "0:00", "0:00"])


class CacheStateViewTest(unittest.TestCase):
    """The allowlist built from the enumerated reply (12.1)."""

    def test_forwards_the_twelve_and_drops_the_eight(self):
        view = helper.cache_state_view(REAL_CACHE_STATE)
        self.assertEqual(sorted(view), sorted(["seekableRanges", "cacheEnd", "readerPts", "cacheDuration", "fwBytes",
                                               "totalBytes", "underrun", "idle", "eof", "eofCached", "bofCached"]))
        self.assertEqual(view["seekableRanges"], [{"start": 6.015, "end": 375.984}])
        self.assertEqual(view["cacheEnd"], 377.984)
        self.assertEqual(view["fwBytes"], 9505744)
        self.assertIs(view["bofCached"], False)
        text = json.dumps(view)
        for dropped in ("debug", "raw-input-rate", "ts-per-stream", "43872", "43889", "video", "audio"):
            self.assertNotIn(dropped, text)

    def test_the_view_holds_no_string_at_all(self):
        def strings(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for inner in value.values():
                    yield from strings(inner)
            elif isinstance(value, list):
                for inner in value:
                    yield from strings(inner)
        self.assertEqual(list(strings(helper.cache_state_view(REAL_CACHE_STATE))), [])
        # And a reply that smuggles strings into numeric leaves loses them.
        tainted = dict(REAL_CACHE_STATE, **{"cache-end": "${path}", "fw-bytes": "9", "underrun": "no",
                                             "seekable-ranges": [{"start": "0", "end": 5.0}, {"start": 1.0, "end": 0.5}, "x", {"start": 2.0, "end": 9.0}]})
        view = helper.cache_state_view(tainted)
        self.assertEqual(list(strings(view)), [])
        self.assertNotIn("cacheEnd", view)
        self.assertNotIn("fwBytes", view)
        self.assertNotIn("underrun", view)
        self.assertEqual(view["seekableRanges"], [{"start": 2.0, "end": 9.0}])

    def test_not_a_dict_is_an_empty_view(self):
        for raw in (None, "x", 3, [], True):
            self.assertEqual(helper.cache_state_view(raw), {"seekableRanges": []})

    def test_range_for_picks_the_range_the_reader_sits_in(self):
        ranges = [{"start": 0.0, "end": 10.0}, {"start": 20.0, "end": 30.0}]
        self.assertEqual(helper.range_for(ranges, 5.0), ranges[0])
        self.assertEqual(helper.range_for(ranges, 25.0), ranges[1])
        self.assertEqual(helper.range_for(ranges, 15.0), ranges[0])   # the last range at or before
        self.assertEqual(helper.range_for(ranges, 35.0), ranges[1])
        self.assertEqual(helper.range_for(ranges, -1.0), ranges[0])
        self.assertEqual(helper.range_for(ranges, None), ranges[0])
        self.assertIsNone(helper.range_for([], 5.0))


class RewindPlayerTestCase(PlayerTestCase):
    """A real token-carrying process and a FakeMpv on the socket carrying the
    plateau cache state, with the zero-point clock held still."""

    def setUp(self):
        super().setUp()
        self.clock = 1000.0
        real = helper._boot_clock
        helper._boot_clock = lambda: self.clock
        self.addCleanup(setattr, helper, "_boot_clock", real)

    def props(self, position=400.617, ranges=None, paused=False, paused_for_cache=False):
        state = {"seekable-ranges": PLATEAU_RANGE if ranges is None else ranges, "cache-end": 419.99,
                 "reader-pts": 400.5, "cache-duration": 17.4, "fw-bytes": 9000000, "total-bytes": 208000000,
                 "underrun": False, "idle": False, "eof": False, "eof-cached": False, "bof-cached": False,
                 "debug-ts-last": 43542.5, "raw-input-rate": 1544205,
                 "ts-per-stream": [{"type": "video", "cache-end": 1.0, "reader-pts": 1.0, "cache-duration": 1.0}]}
        props = {"mpv-version": "mpv 0.41.0", "pause": paused, "paused-for-cache": paused_for_cache,
                 "idle-active": False, "media-title": "stale title",
                 "path": "http://user:%s@provider.test/live/%s/bbc1.m3u8" % (PASSWORD, TOKEN),
                 "demuxer-cache-state": state}
        if position is not None:
            props["time-pos"] = position
        return props

    def stash(self, entry_id=7):
        return helper.player_stash("t:bbc1.uk", "BBC One HD", "UK", "g:uk", "a1b2c3d4", 1758000123, 41,
                                   entry_id=entry_id, verb="play")

    def playing(self, entry_id=7, user_data=None, **kwargs):
        os.makedirs(self.runtime, 0o700, exist_ok=True)
        self.sleeper()
        data = {"omarchy-iptv": self.stash(entry_id)}
        data.update(user_data or {})
        seek_moves = kwargs.pop("seek_moves", True)
        # Lagged by default (F-RWD-15): the fake executes a seek 5 ms after
        # answering it, on another thread, as mpv's playloop does after the
        # IPC thread has replied. A helper that reads at once reads the old
        # position here, as it did once in twelve on the real player.
        seek_lag_s = kwargs.pop("seek_lag_s", 0.005)
        seek_silent = kwargs.pop("seek_silent", False)
        return self.start(props=self.props(**kwargs), user_data=data, seek_moves=seek_moves,
                          seek_lag_s=seek_lag_s, seek_silent=seek_silent)

    def read_after_seek_s(self):
        """Seconds between the `seek` command and the next `time-pos` read
        the fake received, from its own clock: the ordering F-RWD-15 is
        about, observed at the sink rather than inferred from the reply."""
        commands, times = self.server.commands, self.server.command_times
        for i, command in enumerate(commands):
            if command[0] == "seek":
                for j in range(i + 1, len(commands)):
                    if commands[j][:2] == ["get_property", "time-pos"]:
                        return times[j] - times[i]
        return None

    def seek(self, *args):
        return run("player", "seek", "--socket", self.sock, "--ipc-timeout", "1", *args)

    def seeks_sent(self):
        return [command for command in self.server.commands if command[0] == "seek"]


class SeekVerbTest(RewindPlayerTestCase):
    """`player seek` against FakeMpv's measured seek semantics."""

    def test_without_a_player_it_reports_not_running_refused_and_touches_nothing(self):
        code, payload, _, _ = self.seek("--by", "-10")
        self.assertEqual(code, 0)
        self.assertEqual(payload, {"ok": True, "kind": "seek", "running": False, "mode": "by", "requested": -10,
                                   "applied": 0, "clamped": False, "clampedTo": None, "refused": True,
                                   "atFloor": False, "atEdge": False, "rewind": None})
        self.assertFalse(os.path.exists(self.sock))

    def test_the_reply_is_the_design_schema_and_nothing_in_it_is_a_string_from_the_stream(self):
        server = self.playing()
        code, payload, stdout, stderr = self.seek("--by", "-10")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(sorted(payload), sorted(SCHEMA_KEYS))
        self.assertEqual(sorted(payload["rewind"]), sorted(REWIND_KEYS))
        for key, value in payload.items():
            if key not in ("kind", "mode", "rewind"):
                self.assertNotIsInstance(value, str, key)
        for key, value in payload["rewind"].items():
            self.assertNotIsInstance(value, str, key)
        asked = [command[1] for command in server.commands if command[0] == "get_property"]
        self.assertNotIn("path", asked)
        self.assertNotIn("media-title", asked)
        for secret in (PASSWORD, TOKEN, "/live/", "stale title", "provider.test"):
            self.assertNotIn(secret, stdout + stderr, secret)

    def test_a_ten_second_rewind_lands_and_the_reply_says_how_far(self):
        server = self.playing()
        code, payload, _, stderr = self.seek("--by", "-10")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.seeks_sent(), [["seek", 390.617, "absolute"]])
        self.assertEqual(server.seeks, [(390.617, True)])
        self.assertEqual((payload["requested"], payload["applied"], payload["clamped"], payload["refused"], payload["atFloor"]),
                         (-10, -10.0, False, False, False))
        rewind = payload["rewind"]
        self.assertEqual((rewind["position"], rewind["floor"], rewind["ceiling"]), (390.617, 44.028, 418.001))
        self.assertEqual((rewind["history"], rewind["ahead"]), (346.589, 27.384))
        self.assertEqual(rewind["behindLive"], 10.0)
        self.assertEqual((rewind["zeroed"], rewind["paused"], rewind["pausedForCache"], rewind["entryId"]), (True, False, False, 7))

    def test_an_over_long_rewind_is_clamped_to_the_floor_plus_two_and_said(self):
        # THE check the design says must be red against today's tree (4):
        # mpv alone drops a seek below the floor with `success`, so a helper
        # that forwarded the request would move nothing and say nothing.
        server = self.playing()
        code, payload, _, stderr = self.seek("--by", "-1000")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.seeks_sent(), [["seek", 46.028, "absolute"]])
        self.assertEqual(server.seeks, [(46.028, True)])
        self.assertEqual((payload["clamped"], payload["clampedTo"], payload["atFloor"], payload["refused"]), (True, 46.028, True, False))
        self.assertEqual(payload["applied"], -354.589)
        self.assertEqual(payload["rewind"]["history"], 2.0)
        self.assertEqual(payload["rewind"]["behindLive"], 354.589)
        self.assertEqual(server.osd, [["-5:54 behind live, as far back as it goes", 3000]])

    def test_the_deciding_read_waits_for_the_seek_event_so_a_lagged_landing_is_never_reported_refused(self):
        # F-RWD-15. The fake answers the seek at once and executes it 50 ms
        # later; a read sent at once would echo 400.617 and call the seek
        # refused, as the real player did on 1 of 12. The helper subscribes
        # to error-level log messages first, then waits for the `seek`
        # event, and its read is the landing.
        server = self.playing(seek_lag_s=0.05)
        code, payload, _, stderr = self.seek("--by", "-10")
        self.assertEqual(code, 0, stderr)
        self.assertEqual((payload["refused"], payload["applied"], payload["rewind"]["position"]), (False, -10.0, 390.617))
        self.assertEqual(server.osd, [["-0:10 behind live", 3000]])
        names = [c[0] for c in server.commands]
        self.assertIn("request_log_messages", names)
        self.assertLess(names.index("request_log_messages"), names.index("seek"))
        self.assertEqual([c for c in server.commands if c[0] == "request_log_messages"], [["request_log_messages", "error"]])
        gap = self.read_after_seek_s()
        self.assertIsNotNone(gap)
        self.assertGreaterEqual(gap, 0.05)
        self.assertLess(gap, helper.SEEK_EVENT_BOUND_S)

    def test_a_refusal_is_known_from_the_line_without_paying_the_bound(self):
        # The dropped seek's refusal line arrives after the lag; the helper
        # reads then, not 250 ms later -- a held key must not pay the bound
        # on every refusal.
        server = self.playing(seek_moves=False, seek_lag_s=0.01)
        code, payload, _, stderr = self.seek("--by", "-10")
        self.assertEqual(code, 0, stderr)
        self.assertEqual((payload["refused"], payload["applied"]), (True, 0))
        self.assertEqual(server.osd, [])
        gap = self.read_after_seek_s()
        self.assertIsNotNone(gap)
        self.assertGreaterEqual(gap, 0.01)
        self.assertLess(gap, helper.SEEK_EVENT_BOUND_S)

    def test_a_seek_that_neither_runs_nor_refuses_pays_the_bound_and_the_threshold_decides(self):
        # Neither event nor line: the helper waits the bound, then reads and
        # applies the 0.5 s threshold, which says refused.
        server = self.playing(seek_silent=True)
        code, payload, _, stderr = self.seek("--by", "-10")
        self.assertEqual(code, 0, stderr)
        self.assertEqual((payload["refused"], payload["applied"], payload["rewind"]["position"]), (True, 0, 400.617))
        gap = self.read_after_seek_s()
        self.assertIsNotNone(gap)
        self.assertGreaterEqual(gap, helper.SEEK_EVENT_BOUND_S)
        self.assertEqual(helper.SEEK_EVENT_BOUND_S, 0.25)

    def test_a_seek_mpv_drops_is_reported_refused_not_success(self):
        # The underrun case (12.2, F-RWD-9): a target inside the range that
        # moves nothing. mpv answered `success`; the immediate read says no.
        server = self.playing(seek_moves=False)
        code, payload, _, stderr = self.seek("--by", "-10")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(server.seeks, [(390.617, False)])
        self.assertEqual((payload["refused"], payload["applied"], payload["clamped"]), (True, 0, False))
        self.assertEqual(payload["rewind"]["position"], 400.617)
        self.assertEqual(server.osd, [])

    def test_at_the_floor_nothing_is_issued_and_the_floor_is_said(self):
        server = self.playing(position=45.0)
        code, payload, _, stderr = self.seek("--by", "-10")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.seeks_sent(), [])
        self.assertEqual((payload["atFloor"], payload["clamped"], payload["refused"], payload["applied"]), (True, True, False, 0))
        self.assertEqual(payload["rewind"]["position"], 45.0)
        # The zero point was just taken here, so "behind live" reads 0: the
        # line says live, and that it is as far back as it goes.
        self.assertEqual(server.osd, [["live, as far back as it goes", 3000]])

    def test_no_position_yet_is_refused_without_a_seek_and_without_a_zero_point(self):
        # The five seconds after a zap (11.1): time-pos None, ranges empty.
        server = self.playing(position=None, ranges=[])
        code, payload, _, stderr = self.seek("--by", "-10")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.seeks_sent(), [])
        self.assertEqual((payload["refused"], payload["rewind"]), (True, None))
        self.assertNotIn("omarchy-iptv-rewind", server.user_data)
        self.assertEqual(server.osd, [])

    def test_a_position_with_no_range_is_refused_without_a_seek(self):
        # F-RWD-7: `position + by` is never computed and sent when there is
        # nothing to clamp against; a negative target would go to the edge.
        server = self.playing(position=5.0, ranges=[])
        code, payload, _, stderr = self.seek("--by", "-20")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.seeks_sent(), [])
        self.assertTrue(payload["refused"])
        self.assertEqual(payload["rewind"]["position"], 5.0)
        self.assertIsNone(payload["rewind"]["floor"])
        self.assertIsNone(payload["rewind"]["history"])
        self.assertEqual(server.seeks, [])

    def test_a_target_below_the_position_is_clamped_up_and_never_sent_negative(self):
        server = self.playing(position=5.0, ranges=[{"start": 0.0, "end": 30.0}])
        code, payload, _, stderr = self.seek("--by", "-20")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.seeks_sent(), [["seek", 2.0, "absolute"]])
        self.assertEqual(server.seeks, [(2.0, True)])
        self.assertEqual((payload["clamped"], payload["atFloor"], payload["applied"]), (True, True, -3.0))

    def test_forward_past_the_end_is_clamped_to_the_edge(self):
        server = self.playing()
        code, payload, _, stderr = self.seek("--by", "30")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.seeks_sent(), [["seek", 417.501, "absolute"]])
        self.assertEqual((payload["clamped"], payload["clampedTo"], payload["atEdge"], payload["refused"]), (True, 417.501, True, False))
        self.assertEqual(payload["applied"], 16.884)
        self.assertEqual(server.osd, [["live", 3000]])

    def test_live_after_a_deep_rewind_seeks_to_the_frozen_edge_and_says_what_remains(self):
        # D8. The viewer sits at 100.617 with a zero point taken 331.2 s ago at
        # 100.0: 330.583 behind. The edge is 417.501, which closes all but 13.7.
        node = {"schema": 1, "entryId": 7, "wall0": 1000.0, "pos0": 100.0}
        server = self.playing(position=100.617, user_data={"omarchy-iptv-rewind": node})
        self.clock = 1331.2
        code, payload, _, stderr = self.seek("--live")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.seeks_sent(), [["seek", 417.501, "absolute"]])
        self.assertEqual((payload["mode"], payload["atEdge"], payload["clamped"], payload["refused"]), ("live", True, False, False))
        self.assertEqual(payload["requested"], 316.884)
        self.assertEqual(payload["applied"], 316.884)
        self.assertEqual(payload["rewind"]["behindLive"], 13.699)
        self.assertEqual(server.osd, [["-0:13 behind live, at the edge of the buffer", 3000]])
        # The zero point was valid and is untouched: no re-take on `live`.
        self.assertEqual(server.user_data["omarchy-iptv-rewind"], node)

    def test_a_reading_ahead_of_the_zero_point_re_bases_it_so_the_next_back_reads_what_was_asked(self):
        # F-RWD-11. The zero point was taken where the reader first sat,
        # 16.884 s behind the cache end (the HLS lead). `live` lands at the
        # end: by the stored point that reads -16.384, which is not "ahead
        # of live" but "the edge was further on than first observed". The
        # node moves to the landing and the reply reads 0.0 -- so the
        # `back 10` that follows reads 10, not -6.
        node = {"schema": 1, "entryId": 7, "wall0": 1000.0, "pos0": 400.617}
        server = self.playing(user_data={"omarchy-iptv-rewind": node})
        self.clock = 1000.5
        code, payload, _, stderr = self.seek("--live")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.seeks_sent(), [["seek", 417.501, "absolute"]])
        self.assertEqual(payload["rewind"]["behindLive"], 0.0)
        self.assertEqual(server.user_data["omarchy-iptv-rewind"], {"schema": 1, "entryId": 7, "wall0": 1000.5, "pos0": 417.501})
        self.assertEqual(server.osd, [["live", 3000]])
        # Ten seconds of play, then back 10: the number is the request.
        self.clock = 1010.5
        server.props["time-pos"] = 427.501
        server.props["demuxer-cache-state"]["seekable-ranges"] = [{"start": 54.0, "end": 428.0}]
        code, payload, _, _ = self.seek("--by", "-10")
        self.assertEqual(code, 0)
        self.assertEqual(payload["rewind"]["behindLive"], 10.0)
        self.assertEqual(server.user_data["omarchy-iptv-rewind"], {"schema": 1, "entryId": 7, "wall0": 1000.5, "pos0": 417.501})

    def test_no_range_means_no_zero_point_even_with_a_position(self):
        # F-RWD-16, from the live pass: a channel that never opened reported
        # time-pos 0 and no seekable range for 40 s, the zero point was taken
        # at that 0, and the bar counted "-0:40 behind live" on a stream that
        # had shown nothing. A position outside every range is read and
        # reported, but it is no zero point and it moves none.
        server = self.playing(position=0.0, ranges=[])
        code, payload, _, stderr = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual((payload["rewind"]["position"], payload["rewind"]["history"], payload["rewind"]["floor"]), (0.0, None, None))
        self.assertIsNone(payload["rewind"]["behindLive"])
        self.assertFalse(payload["rewind"]["zeroed"])
        self.assertNotIn("omarchy-iptv-rewind", server.user_data)
        # The seek verb neither: refused without a seek (F-RWD-7) and no node.
        code, payload, _, _ = self.seek("--by", "-10")
        self.assertEqual((payload["refused"], payload["rewind"]["zeroed"]), (True, False))
        self.assertEqual(self.seeks_sent(), [])
        self.assertNotIn("omarchy-iptv-rewind", server.user_data)
        # The stream opens: the first read INSIDE a range takes the point,
        # and it reads live, not forty seconds behind.
        self.clock = 1040.0
        server.props["time-pos"] = 12.4
        server.props["demuxer-cache-state"]["seekable-ranges"] = [{"start": 0.0, "end": 20.0}]
        code, payload, _, _ = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(payload["rewind"]["behindLive"], 0.0)
        self.assertEqual(server.user_data["omarchy-iptv-rewind"], {"schema": 1, "entryId": 7, "wall0": 1040.0, "pos0": 12.4})
        # A stale node from before is not re-based by a rangeless read either.
        server.props["time-pos"] = 50.0
        server.props["demuxer-cache-state"]["seekable-ranges"] = []
        self.clock = 1041.0
        code, payload, _, _ = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(server.user_data["omarchy-iptv-rewind"]["pos0"], 12.4)

    def test_status_re_bases_too_and_the_probe_never_does(self):
        # The same reading through `status` (which writes) moves the node;
        # through `probe` (which never writes, 2.2) the raw reading comes
        # back and the node is untouched -- the shell clamps for display.
        node = {"schema": 1, "entryId": 7, "wall0": 1000.0, "pos0": 420.0}
        server = self.playing(user_data={"omarchy-iptv-rewind": node})
        self.clock = 1001.0
        code, payload, _, _ = run("player", "probe", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0)
        self.assertEqual(payload["rewind"]["behindLive"], 20.383)
        self.assertEqual(server.user_data["omarchy-iptv-rewind"], node)
        server.props["time-pos"] = 440.0
        code, payload, _, _ = run("player", "probe", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(payload["rewind"]["behindLive"], -19.0)
        self.assertEqual(server.user_data["omarchy-iptv-rewind"], node)
        code, payload, _, _ = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0)
        self.assertEqual(payload["rewind"]["behindLive"], 0.0)
        self.assertEqual(server.user_data["omarchy-iptv-rewind"], {"schema": 1, "entryId": 7, "wall0": 1001.0, "pos0": 440.0})

    def test_live_at_the_edge_issues_nothing(self):
        server = self.playing(position=417.8)
        code, payload, _, stderr = self.seek("--live")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.seeks_sent(), [])
        self.assertEqual((payload["atEdge"], payload["refused"], payload["applied"]), (True, False, 0))
        self.assertEqual(server.osd, [["live", 3000]])

    def test_the_zero_point_is_taken_once_keyed_by_the_entry_and_replaced_when_the_entry_changes(self):
        server = self.playing()
        self.seek("--by", "-10")
        node = server.user_data["omarchy-iptv-rewind"]
        self.assertEqual(node, {"schema": 1, "entryId": 7, "wall0": 1000.0, "pos0": 400.617})
        # A second press 30 s later: the node is reused, not re-taken from
        # the rewound position (which would read the rewind as live).
        self.clock = 1030.0
        server.props["time-pos"] = 420.617
        code, payload, _, _ = self.seek("--by", "-10")
        self.assertEqual(code, 0)
        self.assertEqual(server.user_data["omarchy-iptv-rewind"], node)
        self.assertEqual(payload["rewind"]["behindLive"], 20.0)
        # A zap changes the entry id; the stale node is replaced.
        server.user_data["omarchy-iptv"] = self.stash(entry_id=8)
        server.props["time-pos"] = 30.0
        server.props["demuxer-cache-state"]["seekable-ranges"] = [{"start": 0.0, "end": 45.0}]
        self.clock = 2000.0
        code, payload, _, _ = self.seek("--by", "-10")
        self.assertEqual(code, 0)
        self.assertEqual(server.user_data["omarchy-iptv-rewind"], {"schema": 1, "entryId": 8, "wall0": 2000.0, "pos0": 30.0})
        self.assertEqual(payload["rewind"]["entryId"], 8)
        self.assertEqual(payload["rewind"]["behindLive"], 10.0)

    def test_without_an_entry_id_there_is_no_zero_point_and_no_osd_line(self):
        # D-DEAD-1: null, never 0. The seek itself still lands.
        server = self.playing(entry_id=None)
        code, payload, _, stderr = self.seek("--by", "-10")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(server.seeks, [(390.617, True)])
        self.assertEqual((payload["refused"], payload["applied"]), (False, -10.0))
        self.assertIsNone(payload["rewind"]["behindLive"])
        self.assertFalse(payload["rewind"]["zeroed"])
        self.assertIsNone(payload["rewind"]["entryId"])
        self.assertNotIn("omarchy-iptv-rewind", server.user_data)
        self.assertEqual(server.osd, [])

    def test_a_stale_or_malformed_node_is_not_a_zero_point(self):
        for node in ({"schema": 1, "entryId": 3, "wall0": 1.0, "pos0": 1.0},
                     {"schema": 2, "entryId": 7, "wall0": 1.0, "pos0": 1.0},
                     {"schema": 1, "entryId": 7, "wall0": "1", "pos0": 1.0},
                     {"schema": 1, "entryId": 7, "pos0": 1.0},
                     "x", None, 7):
            self.assertFalse(helper.rewind_node_valid(node, 7), repr(node))
        self.assertTrue(helper.rewind_node_valid({"schema": 1, "entryId": 7, "wall0": 1.0, "pos0": 0.0}, 7))
        self.assertFalse(helper.rewind_node_valid({"schema": 1, "entryId": 7, "wall0": 1.0, "pos0": 0.0}, None))

    def test_paused_and_paused_for_cache_are_read_from_the_player(self):
        self.playing(paused=True, paused_for_cache=True)
        code, payload, _, _ = self.seek("--by", "-10")
        self.assertEqual(code, 0)
        self.assertEqual((payload["rewind"]["paused"], payload["rewind"]["pausedForCache"]), (True, True))
        self.assertEqual(self.server.osd, [["paused, -0:10 behind live", 3000]])

    def test_by_zero_asks_nothing(self):
        server = self.playing()
        code, payload, _, _ = self.seek("--by", "0")
        self.assertEqual(code, 0)
        self.assertEqual(self.seeks_sent(), [])
        self.assertEqual((payload["refused"], payload["applied"], payload["requested"]), (False, 0, 0))
        self.assertEqual(server.osd, [["live", 3000]])

    def test_the_osd_line_is_the_composer_s_own_and_the_fixture_s(self):
        server = self.playing()
        _, payload, _, _ = self.seek("--by", "-92")
        self.assertEqual(server.osd, [[helper.rewind_osd_text(payload), 3000]])
        self.assertEqual(server.osd[0][0], "-1:32 behind live")
        self.assertNotIn("$", server.osd[0][0])

    def test_by_and_live_are_exclusive_and_one_is_required(self):
        # argparse exits 2 (EXIT_USAGE); in-process that is a SystemExit.
        for argv in (("--by", "-10", "--live"), (), ("--by", "ten"), ("--by", "-10.5")):
            with self.assertRaises(SystemExit) as raised:
                self.seek(*argv)
            self.assertEqual(raised.exception.code, 2, argv)
        self.assertEqual(self.seeks_sent() if self.server else [], [])


class RewindInOtherRepliesTest(RewindPlayerTestCase):
    """The same `rewind` object in `status`, `pause` and `probe`."""

    def test_status_carries_rewind_and_takes_the_zero_point(self):
        server = self.playing()
        code, payload, stdout, stderr = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(sorted(payload["rewind"]), sorted(REWIND_KEYS))
        self.assertEqual((payload["rewind"]["position"], payload["rewind"]["behindLive"], payload["rewind"]["zeroed"]), (400.617, 0.0, True))
        self.assertEqual(server.user_data["omarchy-iptv-rewind"], {"schema": 1, "entryId": 7, "wall0": 1000.0, "pos0": 400.617})
        self.assertEqual(self.seeks_sent(), [])
        for secret in (PASSWORD, TOKEN, "/live/"):
            self.assertNotIn(secret, stdout + stderr)

    def test_status_with_no_position_carries_null_not_zero(self):
        server = self.playing(position=None, ranges=[])
        code, payload, _, _ = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0)
        self.assertIsNone(payload["rewind"])
        self.assertNotIn("omarchy-iptv-rewind", server.user_data)

    def test_probe_carries_rewind_and_never_writes_the_zero_point(self):
        server = self.playing()
        code, payload, _, stderr = run("player", "probe", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["rewind"]["position"], 400.617)
        self.assertIsNone(payload["rewind"]["behindLive"])
        self.assertFalse(payload["rewind"]["zeroed"])
        self.assertNotIn("omarchy-iptv-rewind", server.user_data)
        # With a zero point on the player, the probe recovers it (2.2: a
        # shell restart reads the number back from the player).
        server.user_data["omarchy-iptv-rewind"] = {"schema": 1, "entryId": 7, "wall0": 700.0, "pos0": 100.0}
        code, payload, _, _ = run("player", "probe", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0)
        self.assertEqual(payload["rewind"]["behindLive"], -0.617)
        self.assertTrue(payload["rewind"]["zeroed"])

    def test_probe_without_a_player_carries_null(self):
        code, payload, _, _ = run("player", "probe", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0)
        self.assertIn("rewind", payload)
        self.assertIsNone(payload["rewind"])

    def test_pause_carries_rewind_with_the_state_it_set(self):
        server = self.playing(paused=False)
        code, payload, _, stderr = run("player", "pause", "--socket", self.sock, "--ipc-timeout", "1", "--state", "on")
        self.assertEqual(code, 0, stderr)
        self.assertEqual((payload["paused"], payload["changed"]), (True, True))
        self.assertTrue(payload["rewind"]["paused"])
        self.assertEqual(payload["rewind"]["position"], 400.617)
        self.assertEqual(server.user_data["omarchy-iptv-rewind"]["pos0"], 400.617)
        # FakeMpv's `pause` prop does not follow a set (it never has), so the
        # resume is driven by flipping the prop: a change back, then a no-op.
        server.props["pause"] = True
        code, payload, _, _ = run("player", "pause", "--socket", self.sock, "--ipc-timeout", "1", "--state", "off")
        self.assertEqual(code, 0)
        self.assertEqual((payload["paused"], payload["changed"]), (False, True))
        self.assertFalse(payload["rewind"]["paused"])
        # Already in the wanted state: still answered, still carrying it.
        code, payload, _, _ = run("player", "pause", "--socket", self.sock, "--ipc-timeout", "1", "--state", "on")
        self.assertEqual((payload["paused"], payload["changed"]), (True, False))
        self.assertTrue(payload["rewind"]["paused"])

    def test_pause_without_a_player_carries_null(self):
        code, payload, _, _ = run("player", "pause", "--socket", self.sock, "--ipc-timeout", "1", "--state", "on")
        self.assertEqual(code, 0)
        self.assertEqual(payload, {"ok": True, "kind": "player.pause", "running": False, "paused": None, "changed": False, "rewind": None})

    def test_the_pause_help_and_docstring_no_longer_deny_rewind(self):
        text = helper.player_pause.__doc__
        self.assertNotIn("there is no going back", text)
        self.assertNotIn("ONE reported itself seekable", text)
        self.assertIn("player seek", text)
        # argparse prints help to stdout and exits 0; read the parser directly.
        parser = helper.build_parser()
        help_text = parser.format_help()
        self.assertNotIn("not seekable", help_text)
        for sub in parser._subparsers._group_actions[0].choices["player"]._subparsers._group_actions[0].choices.values():
            self.assertNotIn("not seekable", sub.format_help())


class FakeMpvSeekSemanticsTest(RewindPlayerTestCase):
    """Rule 10: the double is no more forgiving than mpv 0.41. Driven over the
    socket directly, because the helper's clamp never lets an out-of-range
    target reach the player, so no verb test would notice a fake that moved
    on one."""

    def client(self):
        client = helper.MpvIpc(self.sock, 1.0)
        client.connect()
        self.addCleanup(client.close)
        return client

    def test_a_target_below_the_floor_answers_success_moves_nothing_and_logs_the_refusal(self):
        server = self.playing(seek_lag_s=0)
        client = self.client()
        client.command("request_log_messages", "error")
        reply = client.request(["seek", 43.028, "absolute"])
        self.assertEqual(reply["error"], "success")
        self.assertEqual(client.command("get_property", "time-pos"), 400.617)
        self.assertEqual(server.seeks, [(43.028, False)])
        events = client.drain_events(helper.time.monotonic() + 1.0)
        self.assertTrue(events and events[0]["event"] == "log-message" and "Cannot seek in this stream" in events[0]["text"], events)
        self.assertEqual(events[0]["level"], "error")

    def test_a_target_past_the_end_is_the_same_silent_refusal(self):
        server = self.playing(seek_lag_s=0)
        client = self.client()
        self.assertEqual(client.request(["seek", 489.977, "absolute"])["error"], "success")
        self.assertEqual(client.command("get_property", "time-pos"), 400.617)
        self.assertEqual(server.seeks, [(489.977, False)])

    def test_a_target_inside_the_range_echoes_exactly(self):
        # Synchronous fake (seek_lag_s 0): what the position reads once the
        # seek has executed. The lagged ordering is SeekVerbTest's.
        server = self.playing(seek_lag_s=0)
        client = self.client()
        client.command("seek", 100.617, "absolute")
        self.assertEqual(client.command("get_property", "time-pos"), 100.617)
        self.assertEqual(server.seeks, [(100.617, True)])

    def test_a_negative_absolute_target_counts_from_the_cache_end(self):
        # F-RWD-7, 5 of 5 on the real player.
        server = self.playing(seek_lag_s=0)
        client = self.client()
        client.command("seek", -6.462, "absolute")
        self.assertEqual(client.command("get_property", "time-pos"), 418.001 - 6.462)
        self.assertEqual(server.seeks, [(418.001 - 6.462, True)])

    def test_the_underrun_double_moves_nothing_inside_the_range(self):
        server = self.playing(seek_moves=False, seek_lag_s=0)
        client = self.client()
        client.command("seek", 100.617, "absolute")
        self.assertEqual(client.command("get_property", "time-pos"), 400.617)
        self.assertEqual(server.seeks, [(100.617, False)])


class DiskWarningTest(unittest.TestCase):
    """PO-10 through the handoff mechanism, for --cache-on-disk (design 2.6)."""

    def test_the_disk_text_and_set_match_the_fixture(self):
        fixture = json.loads((ROOT / "tests" / "fixtures" / "player-argv.json").read_text(encoding="utf-8"))["mpvHandoff"]
        self.assertEqual(helper.MPV_DISK_TEXT, fixture["diskText"])
        self.assertEqual(helper.MPV_DISK_WARN, frozenset(("--cache-on-disk",)))
        model = (ROOT / "Model.js").read_text(encoding="utf-8")
        self.assertIn('var MPV_DISK_TEXT = "%s"' % fixture["diskText"], model)
        self.assertIn('var MPV_DISK_WARN = { "--cache-on-disk": true }', model)
        disk_cases = [c for c in fixture["cases"] if any("cache-on-disk" in t for t in c["tokens"])]
        self.assertGreaterEqual(len(disk_cases), 4)

    def test_mpv_arg_writes_disk(self):
        self.assertEqual([helper.mpv_arg_writes_disk(t) for t in
                          ("--cache-on-disk", "--cache-on-disk=yes", "--cache-on-disk=1", "--cache-on-disk=no",
                           "--cache-on-disk=FALSE", "--no-cache-on-disk", "--demuxer-cache-dir=/x", "--ytdl")],
                         ["--cache-on-disk", "--cache-on-disk", "--cache-on-disk", "", "", "", "", ""])

    def test_the_unlink_switch_is_rejected_in_every_spelling_and_the_disk_cache_is_kept(self):
        args, rejected = helper.filter_mpv_args(["--demuxer-cache-unlink-files=no", "--no-demuxer-cache-unlink-files",
                                                 "--demuxer-cache-unlink-files=whendone", "--cache-on-disk"])
        self.assertEqual(args, ["--cache-on-disk"])
        self.assertEqual(rejected, ["--demuxer-cache-unlink-files=no", "--no-demuxer-cache-unlink-files",
                                    "--demuxer-cache-unlink-files=whendone"])
        self.assertEqual(helper.mpv_arg_warnings(args), ["mpvArg --cache-on-disk writes the stream to disk while it plays"])


if __name__ == "__main__":
    unittest.main()
