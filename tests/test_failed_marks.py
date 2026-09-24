"""Dead-channel memory: the marks live in the SOURCE CACHE, not state.json.

PO ruling 2026-09-24 amending R8, R11 and UX ruling 9. The store was chosen
against two blockers a design review found in the state.json version:

1. Channel ids are global across sources (ARCHITECTURE-SOURCES D14), so a
   state-level map would mark a DIFFERENT provider's working channel with a
   failure earned on this one.
2. A map keyed by channel id falls inside D-ID-1's id-rotation blast radius,
   and that defect's row records the failed map as excluded precisely BECAUSE
   it was session-only. Per source, that exclusion stays true.

The self-healing drop -- a mark whose id the current playlist does not have --
is what replaces the migration nobody would have maintained.
"""
import json
import os
import pathlib
import tempfile
import unittest

from helper_loader import load_helper

helper = load_helper()
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


def cache_with(ids, marks=None):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, helper.CHANNELS_FILE), "w") as fh:
        json.dump({"channels": [{"id": i, "name": i, "group": "G",
                                 "url": "http://127.0.0.1/%s" % i} for i in ids]}, fh)
    if marks is not None:
        with open(os.path.join(d, helper.FAILED_FILE), "w") as fh:
            json.dump({"version": 1, "failed": marks}, fh)
    return d


class SharedFixtureTest(unittest.TestCase):
    def test_every_case_matches_the_agreed_answer(self):
        """The same file tests/Model.test.js runs against Model.normalizeFailed."""
        with open(FIXTURES / "failed-marks.json") as fh:
            cases = json.load(fh)["cases"]
        self.assertGreaterEqual(len(cases), 3)
        for case in cases:
            self.assertEqual(helper.normalize_failed(case["failed"]), case["expect"], case["name"])


class SelfHealingTest(unittest.TestCase):
    def test_a_mark_whose_channel_left_the_playlist_is_dropped(self):
        d = cache_with(["t:here"], [{"id": "t:here", "at": 1790300000},
                                    {"id": "t:gone", "at": 1790300000}])
        args = type("A", (), {"cache_dir": d, "action": "list", "id": None, "now": 1790300100})()
        import contextlib, io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            helper.cmd_failed(args)
        got = json.loads(out.getvalue())
        self.assertEqual([r["id"] for r in got["failed"]], ["t:here"])

    def test_no_channels_json_means_cannot_tell_and_must_not_wipe(self):
        """A source whose cache has not loaded yet must not lose its marks."""
        d = tempfile.mkdtemp()
        with open(os.path.join(d, helper.FAILED_FILE), "w") as fh:
            json.dump({"version": 1, "failed": [{"id": "t:a", "at": 1790300000}]}, fh)
        self.assertIsNone(helper.known_channel_ids(d))
        self.assertEqual(len(helper.prune_failed(helper.read_failed(d), 1790300100, None)), 1)

    def test_a_mark_ages_out_and_the_boundary_is_not_off_by_one(self):
        now = 1790300000
        ttl = helper.FAILED_TTL_SEC
        rows = [{"id": "t:fresh", "at": now - 60},
                {"id": "t:edge", "at": now - ttl},
                {"id": "t:old", "at": now - ttl - 1}]
        self.assertEqual([r["id"] for r in helper.prune_failed(rows, now, None)],
                         ["t:fresh", "t:edge"])
        # no clock means do not age
        self.assertEqual(len(helper.prune_failed(rows, 0, None)), 3)


class WriteTest(unittest.TestCase):
    def run_verb(self, d, action, cid=None, now=1790300000):
        import contextlib, io
        args = type("A", (), {"cache_dir": d, "action": action, "id": cid, "now": now})()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            helper.cmd_failed(args)
        return json.loads(out.getvalue())

    def test_mark_then_clear_round_trips_on_disk(self):
        d = cache_with(["t:a", "t:b"])
        self.run_verb(d, "mark", "t:a")
        self.run_verb(d, "mark", "t:b", now=1790300100)
        on_disk = json.load(open(os.path.join(d, helper.FAILED_FILE)))
        self.assertEqual([r["id"] for r in on_disk["failed"]], ["t:b", "t:a"],
                         "newest first, because eviction order must be deterministic")
        self.run_verb(d, "clear", "t:a")
        self.assertEqual([r["id"] for r in json.load(open(os.path.join(d, helper.FAILED_FILE)))["failed"]],
                         ["t:b"])

    def test_the_file_is_0600_inside_a_0700_directory(self):
        import stat
        d = cache_with(["t:a"])
        self.run_verb(d, "mark", "t:a")
        path = os.path.join(d, helper.FAILED_FILE)
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_clear_with_no_id_clears_everything(self):
        d = cache_with(["t:a", "t:b"])
        self.run_verb(d, "mark", "t:a")
        self.run_verb(d, "mark", "t:b")
        self.assertEqual(self.run_verb(d, "clear")["failed"], [])

    def test_a_re_mark_moves_it_to_the_front_rather_than_duplicating(self):
        d = cache_with(["t:a", "t:b"])
        self.run_verb(d, "mark", "t:a", now=1790300000)
        self.run_verb(d, "mark", "t:b", now=1790300100)
        got = self.run_verb(d, "mark", "t:a", now=1790300200)
        self.assertEqual([r["id"] for r in got["failed"]], ["t:a", "t:b"])
        self.assertEqual(len(got["failed"]), 2)


class RemovalTest(unittest.TestCase):
    def test_removing_the_source_takes_the_marks_with_it(self):
        """D-LOGO-4's lesson applied before the defect rather than after it."""
        self.assertIn(helper.FAILED_FILE, helper.CACHE_FILES)
        d = cache_with(["t:a"], [{"id": "t:a", "at": 1790300000}])
        removed, kept = helper.clear_source_dir(d)
        self.assertIn(helper.FAILED_FILE, removed)
        self.assertFalse(os.path.exists(d))


if __name__ == "__main__":
    unittest.main()
