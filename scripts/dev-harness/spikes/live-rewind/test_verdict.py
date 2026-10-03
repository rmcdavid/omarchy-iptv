#!/usr/bin/env python3
"""Tests for verdict.py. Run: python3 -m unittest -v test_verdict (in this dir).

Every assertion here was seen RED against a deliberate mutation of the
function it covers before it was kept; the mutations and both counts are
recorded in docs/SPIKE-LIVE-REWIND.md.
"""

import sys
import unittest

sys.dont_write_bytecode = True

import verdict


class BackWindow(unittest.TestCase):
    def test_bytes_over_bitrate(self):
        # 50 MiB at 3.8 Mbps, the bitrate M2-11 measured its pause length on.
        window = verdict.back_window_seconds(50 * 1024 * 1024, 3_800_000)
        self.assertAlmostEqual(window, 110.37, places=1)

    def test_fatter_stream_is_a_shorter_window(self):
        thin = verdict.back_window_seconds(50 * 1024 * 1024, 2_000_000)
        fat = verdict.back_window_seconds(50 * 1024 * 1024, 8_000_000)
        self.assertGreater(thin, fat)

    def test_raising_the_cap_lengthens_it_proportionally(self):
        small = verdict.back_window_seconds(50 * 1024 * 1024, 4_000_000)
        big = verdict.back_window_seconds(400 * 1024 * 1024, 4_000_000)
        self.assertAlmostEqual(big / small, 8.0, places=6)

    def test_unknown_is_none_not_zero(self):
        self.assertIsNone(verdict.back_window_seconds(50 * 1024 * 1024, None))
        self.assertIsNone(verdict.back_window_seconds(None, 3_800_000))
        self.assertIsNone(verdict.back_window_seconds(50 * 1024 * 1024, 0))
        self.assertIsNone(verdict.back_window_seconds(0, 3_800_000))


class SeekableRanges(unittest.TestCase):
    def test_widest_range(self):
        state = {"seekable-ranges": [
            {"start": 10.0, "end": 25.0},
            {"start": 100.0, "end": 160.0},
        ]}
        self.assertAlmostEqual(verdict.seekable_range_span(state), 60.0)

    def test_absent_key_is_none(self):
        self.assertIsNone(verdict.seekable_range_span({}))
        self.assertIsNone(verdict.seekable_range_span(None))

    def test_empty_list_is_zero_not_none(self):
        self.assertEqual(verdict.seekable_range_span({"seekable-ranges": []}), 0.0)

    def test_junk_entries_are_skipped_not_fatal(self):
        state = {"seekable-ranges": [
            {"start": None, "end": 5.0},
            "nonsense",
            {"start": 3.0, "end": 9.0},
            {"start": 9.0, "end": 9.0},
        ]}
        self.assertAlmostEqual(verdict.seekable_range_span(state), 6.0)


class BackSpan(unittest.TestCase):
    def test_history_behind_the_reader_not_the_whole_range(self):
        # Measured shape: for HLS the forward cache runs whole segments ahead,
        # so the range is wider than the history a rewind can use.
        state = {"reader-pts": 100.0,
                 "seekable-ranges": [{"start": 88.0, "end": 116.0}]}
        self.assertAlmostEqual(verdict.back_span_seconds(state), 12.0)
        self.assertAlmostEqual(verdict.seekable_range_span(state), 28.0)

    def test_range_that_does_not_contain_the_reader_is_ignored(self):
        state = {"reader-pts": 100.0,
                 "seekable-ranges": [{"start": 10.0, "end": 40.0},
                                     {"start": 95.0, "end": 110.0}]}
        self.assertAlmostEqual(verdict.back_span_seconds(state), 5.0)

    def test_no_range_holds_the_reader(self):
        state = {"reader-pts": 100.0,
                 "seekable-ranges": [{"start": 10.0, "end": 40.0}]}
        self.assertIsNone(verdict.back_span_seconds(state))

    def test_missing_reader_or_ranges(self):
        self.assertIsNone(verdict.back_span_seconds({"seekable-ranges": []}))
        self.assertIsNone(verdict.back_span_seconds({"reader-pts": 100.0}))
        self.assertIsNone(verdict.back_span_seconds(None))


class SeekVerdict(unittest.TestCase):
    def test_moved_back_and_kept_playing(self):
        self.assertEqual(verdict.seek_verdict(120.0, 100.0, 103.0, -20.0), "rewound")

    def test_did_not_move(self):
        self.assertEqual(verdict.seek_verdict(120.0, 120.0, 123.0, -20.0), "refused")

    def test_forward_jump_is_not_a_rewind(self):
        # A live stream that snaps back to the live edge reads as refused,
        # never as a rewind, however far the number moved.
        self.assertEqual(verdict.seek_verdict(120.0, 140.0, 143.0, -20.0), "refused")

    def test_moved_back_but_frozen(self):
        self.assertEqual(verdict.seek_verdict(120.0, 100.0, 100.0, -20.0), "stalled")

    def test_player_stopped_answering(self):
        self.assertEqual(verdict.seek_verdict(120.0, None, None, -20.0), "lost")
        self.assertEqual(verdict.seek_verdict(None, 100.0, 103.0, -20.0), "lost")

    def test_moved_back_then_died(self):
        self.assertEqual(verdict.seek_verdict(120.0, 100.0, None, -20.0), "stalled")

    def test_sub_second_wobble_is_not_a_rewind(self):
        self.assertEqual(verdict.seek_verdict(120.0, 119.4, 122.0, -20.0), "refused")

    def test_achieved(self):
        self.assertAlmostEqual(verdict.achieved_seconds(120.0, 100.5), 19.5)
        self.assertIsNone(verdict.achieved_seconds(120.0, None))


class PropertyClaim(unittest.TestCase):
    def test_fully_seekable_wins(self):
        self.assertEqual(verdict.property_claim(True, False, 0.0), "seekable")

    def test_partially_seekable_is_its_own_answer(self):
        # The whole reason this spike exists: M2-11 read only the first flag.
        self.assertEqual(verdict.property_claim(False, True, 30.0), "partially-seekable")

    def test_ranges_without_either_flag(self):
        self.assertEqual(verdict.property_claim(False, False, 30.0), "cache-range-only")

    def test_nothing_at_all(self):
        self.assertEqual(verdict.property_claim(False, False, 0.0), "unseekable")
        self.assertEqual(verdict.property_claim(False, False, None), "unseekable")
        self.assertEqual(verdict.property_claim(None, None, None), "unseekable")


class Summarise(unittest.TestCase):
    def test_counts(self):
        rows = [
            {"played": True, "claim": "partially-seekable", "seek": "rewound"},
            {"played": True, "claim": "partially-seekable", "seek": "rewound"},
            {"played": True, "claim": "unseekable", "seek": "refused"},
            {"played": False},
        ]
        counts = verdict.summarise(rows)
        self.assertEqual(counts["measured"], 4)
        self.assertEqual(counts["played"], 3)
        self.assertEqual(counts["failed"], 1)
        self.assertEqual(counts["partially-seekable"], 2)
        self.assertEqual(counts["rewound"], 2)
        self.assertEqual(counts["refused"], 1)

    def test_a_channel_that_never_played_contributes_no_claim(self):
        counts = verdict.summarise([{"played": False, "claim": "seekable", "seek": "rewound"}])
        self.assertEqual(counts["seekable"], 0)
        self.assertEqual(counts["rewound"], 0)
        self.assertEqual(counts["failed"], 1)


if __name__ == "__main__":
    unittest.main()


# --- Second pass, 2026-10-03 -------------------------------------------------

class BehindLive(unittest.TestCase):
    def test_cache_end_minus_time_pos(self):
        self.assertAlmostEqual(verdict.behind_live_seconds({"cache-end": 107.99}, 90.83), 17.16, places=2)

    def test_missing_side_is_none(self):
        self.assertIsNone(verdict.behind_live_seconds({"cache-end": 107.99}, None))
        self.assertIsNone(verdict.behind_live_seconds({}, 90.83))
        self.assertIsNone(verdict.behind_live_seconds(None, 90.83))


class HistorySurvives(unittest.TestCase):
    # Measured 2026-10-03: a loadfile restarts the timeline at 0, so the old
    # range and the fresh one OVERLAP by construction. The first version of
    # this rule was an overlap test and said True about a history that was
    # gone. A fresh demuxer cannot show a range wider than its own age plus
    # the forward lead.
    def test_fresh_timeline_overlapping_at_zero_is_not_survival(self):
        self.assertFalse(verdict.history_survives([[-0.0, 105.983]], [[0.0, 1.988]], 5.034))

    def test_a_range_wider_than_the_demuxer_is_old_is_survival(self):
        self.assertTrue(verdict.history_survives([[0.0, 105.983]], [[0.0, 100.0]], 5.0))

    def test_unknown_is_none(self):
        self.assertIsNone(verdict.history_survives(None, [[0.0, 1.0]], 5.0))
        self.assertIsNone(verdict.history_survives([[0.0, 1.0]], [[0.0, 1.0]], None))


class ResumedFrom(unittest.TestCase):
    def test_continues_from_the_paused_point(self):
        self.assertTrue(verdict.resumed_from(240.785, 242.787, 245.790))

    def test_a_jump_to_live_is_not_a_resume(self):
        self.assertFalse(verdict.resumed_from(240.785, 519.9, 522.9))

    def test_not_moving_is_not_a_resume(self):
        self.assertFalse(verdict.resumed_from(240.785, 240.785, 240.785))

    def test_missing_reading_is_none(self):
        self.assertIsNone(verdict.resumed_from(240.785, None, 245.79))


class FloorSeek(unittest.TestCase):
    def test_landed_near_the_target(self):
        self.assertEqual(verdict.floor_seek_verdict(149.0, 400.0, 149.9, 152.9, 148.0), "landed")

    def test_clamped_to_the_floor_when_asked_below_it(self):
        self.assertEqual(verdict.floor_seek_verdict(147.0, 400.0, 148.2, 151.2, 148.0), "clamped")

    def test_refused_when_it_did_not_move(self):
        self.assertEqual(verdict.floor_seek_verdict(147.0, 400.0, 400.3, 403.3, 148.0), "refused")

    def test_an_ignored_seek_read_a_second_later_is_refused_not_elsewhere(self):
        # Measured 2026-10-03: seek absolute 43.028 with the floor at 44.028
        # answered "success"; time-pos read 48.03 before, 49.03 one second
        # after, 52.04 three seconds later. The player just kept playing.
        self.assertEqual(verdict.floor_seek_verdict(43.028, 48.03, 49.03, 52.04, 44.028), "refused")

    def test_stalled_when_it_moved_but_did_not_play(self):
        self.assertEqual(verdict.floor_seek_verdict(149.0, 400.0, 149.9, 149.9, 148.0), "stalled")

    def test_elsewhere_when_it_landed_somewhere_else(self):
        self.assertEqual(verdict.floor_seek_verdict(149.0, 400.0, 300.0, 303.0, 148.0), "elsewhere")


class Plateau(unittest.TestCase):
    CAP = 200 * 1024 * 1024

    def test_flat_span_at_the_cap_is_a_plateau(self):
        snaps = [{"totalBytes": self.CAP * 0.995, "backSpan": 357.1},
                 {"totalBytes": self.CAP * 0.996, "backSpan": 357.0},
                 {"totalBytes": self.CAP * 0.998, "backSpan": 355.1}]
        self.assertTrue(verdict.at_plateau(snaps, self.CAP))

    def test_still_growing_is_not_a_plateau_even_at_the_cap(self):
        snaps = [{"totalBytes": self.CAP * 0.99, "backSpan": 300.0},
                 {"totalBytes": self.CAP * 0.99, "backSpan": 320.0},
                 {"totalBytes": self.CAP * 0.99, "backSpan": 340.0}]
        self.assertFalse(verdict.at_plateau(snaps, self.CAP))

    def test_flat_below_the_cap_is_an_underrun_not_a_plateau(self):
        snaps = [{"totalBytes": self.CAP * 0.5, "backSpan": 100.0},
                 {"totalBytes": self.CAP * 0.5, "backSpan": 100.0},
                 {"totalBytes": self.CAP * 0.5, "backSpan": 100.0}]
        self.assertFalse(verdict.at_plateau(snaps, self.CAP))

    def test_needs_three_samples(self):
        self.assertFalse(verdict.at_plateau([{"totalBytes": self.CAP, "backSpan": 1.0}] * 2, self.CAP))


class TickRate(unittest.TestCase):
    def test_one_second_per_second(self):
        rate = verdict.tick_rate([(0.0, 10.0), (1.0, 11.0), (2.0, 12.0), (3.0, 13.0)])
        self.assertEqual(rate["ticks"], 3)
        self.assertAlmostEqual(rate["median"], 1.0)
        self.assertAlmostEqual(rate["min"], 1.0)

    def test_a_stall_shows_as_a_zero_minimum(self):
        rate = verdict.tick_rate([(0.0, 10.0), (1.0, 11.0), (2.0, 11.0), (3.0, 12.0)])
        self.assertAlmostEqual(rate["min"], 0.0)
        self.assertAlmostEqual(rate["median"], 1.0)

    def test_a_missing_reading_breaks_the_pair_rather_than_inventing_a_rate(self):
        rate = verdict.tick_rate([(0.0, 10.0), (1.0, None), (2.0, 12.0)])
        self.assertIsNone(rate)


class Trend(unittest.TestCase):
    def test_down(self):
        self.assertEqual(verdict.trend([300.0, 290.0, 280.0])["direction"], "down")

    def test_flat_within_two_seconds(self):
        self.assertEqual(verdict.trend([300.0, 301.0, 301.5])["direction"], "flat")

    def test_up_skipping_none(self):
        t = verdict.trend([None, 10.0, None, 20.0])
        self.assertEqual(t["direction"], "up")
        self.assertEqual(t["n"], 2)


# --- Pre-build measurements, 2026-10-03 (section 12) --------------------

class EnumerateFields(unittest.TestCase):
    STATE = {"cache-end": 418.0, "eof": False, "fw-bytes": 1000,
             "seekable-ranges": [{"start": 44.0, "end": 418.0}, {"start": 500.0, "end": 501.0}],
             "ts-per-stream": [{"type": "video", "cache-duration": 10.0}]}

    def test_every_leaf_once_through_the_first_list_element(self):
        paths = [p for p, _, _ in verdict.enumerate_fields(self.STATE)]
        self.assertEqual(paths, ["cache-end", "eof", "fw-bytes",
                                 "seekable-ranges[].end", "seekable-ranges[].start",
                                 "ts-per-stream[].cache-duration", "ts-per-stream[].type"])

    def test_types_and_samples(self):
        rows = dict((p, (k, v)) for p, k, v in verdict.enumerate_fields(self.STATE))
        self.assertEqual(rows["eof"], ("bool", False))
        self.assertEqual(rows["fw-bytes"], ("int", 1000))
        self.assertEqual(rows["cache-end"], ("float", 418.0))
        self.assertEqual(rows["ts-per-stream[].type"], ("str", "video"))

    def test_an_empty_list_is_a_visible_leaf(self):
        rows = verdict.enumerate_fields({"seekable-ranges": []})
        self.assertEqual(rows, [("seekable-ranges", "list", [])])

    def test_string_fields_are_the_privacy_question(self):
        self.assertEqual(verdict.string_fields(self.STATE), ["ts-per-stream[].type"])
        self.assertEqual(verdict.string_fields({"a": 1, "b": [{"c": 2.0}]}), [])


class NotMoved(unittest.TestCase):
    def test_a_refused_seek_reads_the_same_position(self):
        self.assertTrue(verdict.not_moved(48.03, 48.04, 0.5))

    def test_a_landed_seek_is_not_a_refusal(self):
        self.assertFalse(verdict.not_moved(400.617, 100.617, 0.5))

    def test_the_threshold_is_strict(self):
        self.assertFalse(verdict.not_moved(10.0, 10.5, 0.5))

    def test_a_missing_reading_is_none(self):
        self.assertIsNone(verdict.not_moved(None, 10.0, 0.5))
        self.assertIsNone(verdict.not_moved(10.0, None, 0.5))


class Distributions(unittest.TestCase):
    def test_abs_deltas_skip_broken_rows(self):
        rows = [{"before": 10.0, "after": 7.0}, {"before": None, "after": 3.0},
                {"before": 5.0, "after": 5.25}, {"after": 1.0}]
        self.assertEqual(verdict.abs_deltas(rows), [0.25, 3.0])

    def test_distribution(self):
        self.assertEqual(verdict.distribution([3.0, 1.0, 2.0]),
                         {"n": 3, "min": 1.0, "median": 2.0, "max": 3.0})
        self.assertEqual(verdict.distribution([4.0, 1.0])["median"], 2.5)
        self.assertIsNone(verdict.distribution([]))

    def test_threshold_margin_separates(self):
        m = verdict.threshold_margin(landed_min=1.9, refused_max=0.02, threshold=0.5)
        self.assertTrue(m["separates"])
        self.assertAlmostEqual(m["aboveRefused"], 0.48)
        self.assertAlmostEqual(m["belowLanded"], 1.4)

    def test_threshold_margin_fails_when_a_landed_seek_sits_below_it(self):
        self.assertFalse(verdict.threshold_margin(0.3, 0.02, 0.5)["separates"])
        self.assertFalse(verdict.threshold_margin(1.9, 0.6, 0.5)["separates"])

    def test_threshold_margin_with_an_empty_side(self):
        m = verdict.threshold_margin(None, 0.02, 0.5)
        self.assertIsNone(m["belowLanded"])
        self.assertTrue(m["separates"])


class ZeroPoint(unittest.TestCase):
    def test_the_q3_reading(self):
        # section 11.3: a 300 s seek plus 0.6 s of zero-point lateness.
        self.assertAlmostEqual(verdict.zero_point_error(0.0, 0.0, 1.12, -299.48), 300.60, places=2)

    def test_perfect_playback_is_zero(self):
        self.assertAlmostEqual(verdict.zero_point_error(100.0, 5.0, 160.0, 65.0), 0.0)

    def test_a_stall_counts_as_behind(self):
        self.assertAlmostEqual(verdict.zero_point_error(100.0, 5.0, 160.0, 63.0), 2.0)

    def test_missing_is_none(self):
        self.assertIsNone(verdict.zero_point_error(None, 5.0, 160.0, 63.0))

