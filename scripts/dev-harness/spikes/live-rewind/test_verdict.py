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
