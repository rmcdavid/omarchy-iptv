"""D-EPG-17: a record whose tail is not what the helper writes makes no
entry, and is counted.

compute_now_next pasted a record's tail (the title's JSON and the detail
members) into epg-now.json unchecked, so a tail that is not JSON -- only a
hand edit or a damaged disk makes one -- wrote a fragment line no reader
can parse; the shell indexes a line by its key alone, so the channel
counted as covered and showed no programme. The channel is now skipped and
counted, as a damaged start or stop has been since D-EPG-14.

Two halves, and the second matters as much: every damaged tail is refused,
and NO tail record_body can write is (a check that refused a real title
would blank that channel's programme on every recompute).
"""
import json
import unittest

from helper_loader import load_helper

helper = load_helper()
NOW = 1790400000
SEP = helper.EPG_RECORD_SEP

DAMAGED = [
    "abc",                      # the row's own case: `"title":abc`
    "",                         # cut at the head
    '"',                        # an unterminated title
    '"a',
    '"a",',
    '"a","desc"',
    '"a","desc":',
    '"a","desc":1',             # a member that is not a string
    '"a","desc":"d"x',
    '"a" ',                     # JSON, but not what record_body writes
    '"a\tb"',                   # a raw control character
    '"a\\qb"',                  # an escape JSON does not have
    '"a"},"x":{"y":"z"',        # a tail that closes the object early
    '{"a":1}',
    "null",
]

TITLES = ["News", "", 'He said "hi"', "back\\slash", "tab\there", "line\nbreak", "caf\u00e9", "\u2028sep", "\U0001f4fa TV",
          "\ud800", "a,b:c", '","desc":"x', "\x7f", "{}[]", " lead and trail "]


def record(start, stop, tail):
    return "%010d %010d %s" % (start, stop, tail)


def window(*tails_now_next):
    """One channel per (now tail, next tail) pair."""
    lines = []
    for index, (now_tail, next_tail) in enumerate(tails_now_next):
        records = [record(NOW - 600, NOW + 600, now_tail), record(NOW + 600, NOW + 1800, next_tail)]
        lines.append(json.dumps("ch%d.tv" % index) + "\t" + SEP.join(records))
    return {"lines": lines}


class RecordTailTest(unittest.TestCase):
    def test_a_damaged_now_or_next_makes_no_entry_and_is_counted(self):
        good = '"Good"'
        for tail in DAMAGED:
            for pair in ((tail, good), (good, tail)):
                with self.subTest(tail=tail, damaged="now" if pair[0] == tail else "next"):
                    fragments, _valid, now_count, skipped = helper.compute_now_next(window((good, good), pair), NOW)
                    self.assertEqual((len(fragments), now_count, skipped), (1, 1, 1))
                    self.assertEqual(list(json.loads("{" + fragments[0] + "}")), ["ch0.tv"])

    def test_every_line_the_recompute_writes_parses_whatever_the_window_holds(self):
        pairs = [('"Good"', '"Good"')] + [(tail, '"Good"') for tail in DAMAGED] + [('"Good"', tail) for tail in DAMAGED]
        fragments, _valid, _now_count, skipped = helper.compute_now_next(window(*pairs), NOW)
        self.assertEqual(skipped, 2 * len(DAMAGED))
        for fragment in fragments:
            entry = json.loads("{" + fragment + "}")
            for half in next(iter(entry.values())).values():
                self.assertIsInstance(half["title"], str)

    def test_no_record_the_helper_writes_is_refused(self):
        details = [None, {"desc": "d"}, {"desc": 'q"uote', "category": "c\\at", "episode": "S1 E2"},
                   {"category": "\u2028", "episode": "\ud800"}, {"desc": "", "episode": "e"}]
        for title in TITLES:
            for detail in details:
                with self.subTest(title=title, detail=detail):
                    made = helper.encode_record(NOW - 600, NOW + 600, title, detail)
                    self.assertTrue(helper._record_tail_ok(made), made)
                    self.assertEqual(helper.record_to_dict(made)["title"], title)
        for detail in details:
            for title in ("Now", 'N"ow'):
                made = helper.encode_record(NOW - 600, NOW + 600, title, detail)
                later = helper.encode_record(NOW + 600, NOW + 1800, title, detail)
                fragments, _valid, now_count, skipped = helper.compute_now_next(
                    {"lines": ['"a.tv"\t' + SEP.join([made, later])]}, NOW)
                self.assertEqual((len(fragments), now_count, skipped), (1, 1, 0))
                entry = json.loads("{" + fragments[0] + "}")["a.tv"]
                self.assertEqual((entry["now"]["title"], entry["next"]["title"]), (title, title))

    def test_the_skip_is_told_in_the_status_the_way_a_damaged_head_is(self):
        self.assertEqual(len(helper.epg_skipped_warnings(1)), 1)


if __name__ == "__main__":
    unittest.main()
