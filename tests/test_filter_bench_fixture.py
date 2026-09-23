"""The perf bench's idea of a channel must be the helper's idea of a channel.

F-PERF-1 was measured twice on a channel list written by hand inside the
bench. The helper writes six fields unconditionally and that list carried four
of them; the missing one was `id`, which is exactly the field
`Model.channelId` looks for before falling back to hashing the URL. The filter
calls it once per matching row, so the bench hashed 6,877 URLs per keystroke
that the shipped code never hashes, and the residual it reported -- 64 ms on a
single character, over the 30 ms budget -- was 3.6x the truth. The remedy that
number argued for was a UX change: stop filtering until the second keystroke.

CLAUDE.md rule 10 says a double must never be more FORGIVING than the real
thing. That one was HARSHER, which the rule does not name and which is worse
for a measurement: a forgiving double hides a defect, a harsh one invents one,
and an invented defect gets paid for in product.

So the join between the bench and the helper is a CALL, not a description.
These tests import the bench's own field tuples and its own refusal predicate
and run them against a real parse.
"""
import importlib.util
import json
import os
import pathlib
import unittest

from helper_loader import load_helper

helper = load_helper()

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_bench():
    """scripts/qa-filter-bench.py, imported for its field tuples."""
    path = ROOT / "scripts" / "qa-filter-bench.py"
    spec = importlib.util.spec_from_file_location("qa_filter_bench", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bench = load_bench()

PLAYLIST = """#EXTM3U
#EXTINF:-1 tvg-id="one.test" tvg-name="One TV" tvg-logo="https://logo.test/1.png" tvg-chno="101" group-title="News",One HD
http://127.0.0.1/1
#EXTINF:-1 group-title="Sport;Extra",Two SD
http://127.0.0.1/2
#EXTINF:-1 tvg-id="three.test",Three
#EXTVLCOPT:http-user-agent=probe
http://127.0.0.1/3
#EXTINF:-1,Four
http://127.0.0.1/4
"""


class FilterBenchFixtureTest(unittest.TestCase):
    def parse(self):
        return helper.parse_m3u(PLAYLIST)["channels"]

    def test_every_always_field_is_on_every_parsed_channel(self):
        """The bench's ALWAYS_FIELDS is the helper's unconditional set, by call."""
        channels = self.parse()
        self.assertEqual(len(channels), 4)
        for field in bench.ALWAYS_FIELDS:
            absent = [c["name"] for c in channels if field not in c]
            self.assertEqual(absent, [], "%s is in ALWAYS_FIELDS but the helper "
                                         "left it off %s" % (field, absent))

    def test_the_parser_grew_no_field_the_bench_does_not_know(self):
        """A new channel field turns this red rather than the next bench unfaithful."""
        channels = self.parse()
        known = set(bench.ALWAYS_FIELDS) | set(bench.OPTIONAL_FIELDS)
        seen = set()
        for c in channels:
            seen.update(c.keys())
        self.assertEqual(sorted(seen - known), [],
                         "the parser writes fields the bench does not know about")
        # And the fixture must actually exercise the optional half, or this
        # test would pass on a playlist that never produces one.
        self.assertTrue({"chno", "groups", "headers", "logo", "tvgId", "tvgName"} <= seen,
                        "the fixture playlist no longer produces every optional field: %s"
                        % sorted(seen))

    def test_a_real_parse_is_faithful_by_the_benchs_own_predicate(self):
        """The bench would agree to measure what the helper actually writes."""
        self.assertEqual(bench.unfaithful(self.parse()), [])

    def test_the_predicate_catches_the_f_perf_1_fixture(self):
        """Strip `id` -- the omission that cost 3.6x -- and the bench refuses."""
        channels = self.parse()
        for c in channels:
            c.pop("id", None)
        complaints = bench.unfaithful(channels)
        self.assertEqual(len(complaints), 1, complaints)
        self.assertIn("id missing from 4 of 4 rows", complaints[0])

    def test_the_predicate_catches_an_unknown_field(self):
        channels = self.parse()
        channels[0]["invented"] = "x"
        self.assertTrue(any("invented" in c for c in bench.unfaithful(channels)))

    def test_channel_id_reads_the_field_rather_than_hashing(self):
        """Why `id` decided the measurement: with it, no hash runs.

        The mirror of Model.channelId. If the helper ever stopped writing `id`,
        both implementations would fall back to fnv1a32 over the URL on every
        matching row -- which is the 3.6x.
        """
        channels = self.parse()
        for c in channels:
            self.assertTrue(c["id"], "a channel with no id sends channelId to the hash")
        ids = [c["id"] for c in channels]
        self.assertEqual(len(set(ids)), len(ids), "ids must be unique or favourites collide")


if __name__ == "__main__":
    unittest.main()
