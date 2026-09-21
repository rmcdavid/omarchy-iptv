"""D-GS-2 fixture (ruling GS9): guide data configured, no tvg-id matches.

docs/STATUS.md row D-GS-2, fixed at 9d236d5 with follow-up ef6c307: with
guide data configured and NO tvg-id matches, every guide row went to two-line
height with a BLANK second line -- density spent on white space, three
visible rows lost. The fix asks the DATA, not the setting: Model.epgCoverage
counts the rows guide data can actually fill and Model.rowsHaveDetail takes
`epgCarries` (that count > 0) where it used to take `epgConfigured`.

Why the configured list could never show it: 28 groups, so rowShowsGroup is
already true in All scope and the EPG term never decides, and a tvg-id on
100% of rows, matched by its own guide. The repro needs ONE group and guide
ids DISJOINT from the playlist. Nothing committed has that shape, so it is
generated here on every run (docs/QA-PHASE3.md, "Fixtures that must be
written"):

  (a) NEGATIVE  one group, 60 rows, a tvg-id on every row, plus an XMLTV
                whose ids share NOTHING with the playlist: a second generator
                run in the realistic profile (ids CamelName.cc) against the
                synthetic profile's chNNNNN.test. The intersection is asserted
                empty in the test, case-insensitively, the way build_alias
                matches. Expect carries false, rowsHaveDetail false.
  (b) POSITIVE  the same playlist with its own matching XMLTV: carries true,
                rowsHaveDetail true.
  (c) BOUNDARY  an XMLTV holding exactly ONE of the 60 ids -- the original
                complaint at 1/N instead of 0/N. This RECORDS what the
                shipping code says (matched 1, carries true, rowsHaveDetail
                true, 1 filled line and 59 blank); it decides no policy.

Every list is generated into a mkdtemp() by scripts/gen-playlist.py with
--now set to the current time, so the guide window is always current (the
committed tests/fixtures/qa-epg.xml went stale exactly that way). The epgMap
is NOT hand-built: the real helper builds it (`playlist`, then `epg`, both
with --cache-dir under the scratch directory), because bin/omarchy-iptv's epg
verb is what writes the epg-now.json Service.qml loads into `epgNow`, and its
alias table already restricts the map to playlist ids, which gives a second
observable along the same data (status["matched"]). The verdict is then
taken from Model.js itself through tests/fixtures/qa-gs2/verify.js (CLAUDE.md
rule 12), never restated here.

Rule 11 proof, recorded. The pre-fix decision (9d236d5^ Model.js:4056) was

    return rowShowsGroup(o) || o.epgConfigured === true

With that line put back into Model.js in place and this module run:

    Ran 6 tests -- FAILED (failures=3)
      test_a_negative_no_match_means_single_line_rows:
        rowsHaveDetail True != False  (60 rows, 0 matched, carries False)
      test_hand_readable_list_has_the_same_shape:
        rowsHaveDetail True != False  (8 rows, 0 matched)
      test_prefix_decision_reproduces_the_defect:
        the shipping line was not found once in Model.js (count 0)

Against the shipping code: Ran 6 tests -- OK. The tracked file was restored
with `git checkout -- Model.js` afterwards. test_prefix_decision_reproduces_
the_defect keeps that reversion runnable in the gate, on a scratch COPY of
Model.js, so the fixture provably still shows the defect and not merely the
fix.

Run: python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import xml.etree.ElementTree as ET

# FIRST, before the helper is touched: this import redirects HOME and every
# XDG directory at a throwaway sandbox. Read its docstring -- a suite once
# rewrote the user's live state.json 124 times. Every helper call below also
# names an explicit --cache-dir under mkdtemp(), so nothing here depends on
# the redirect alone.
from helper_loader import load_helper

helper = load_helper()

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL = ROOT / "Model.js"
GENERATOR = ROOT / "scripts" / "gen-playlist.py"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "qa-gs2"
VERIFY = FIXTURE_DIR / "verify.js"
HAND_LIST = FIXTURE_DIR / "qa-gs2-one-group.m3u"

CHANNELS = 60       # >= 60 so the fold is visible on the day (docs/QA-PHASE3.md)
HOURS = 24          # XMLTV half-width; the helper keeps -2 h .. +12 h of it
NOW = int(time.time())
ONE_ID = "ch00001.test"   # the synthetic profile's id for channel index 1

# The one line 9d236d5 changed, both ways round. The pre-fix reproduction
# asserts the shipping spelling is found exactly once before it substitutes,
# so a refactor of that line fails loudly here instead of turning the
# reproduction into a no-op.
SHIPPED_LINE = "return rowShowsGroup(o) || o.epgCarries === true"
PREFIX_LINE = "return rowShowsGroup(o) || o.epgConfigured === true"
NO_MATCH_WARNING = "no EPG channel id matches a playlist tvg-id"


def run_helper(*args):
    """Run bin/omarchy-iptv in-process; -> (exit code, last JSON line, stderr)."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(args))
    text = out.getvalue().strip()
    payload = json.loads(text.splitlines()[-1]) if text else None
    return code, payload, err.getvalue()


def generate(out_m3u, out_xml, *flags):
    """scripts/gen-playlist.py for real, as an argv list (never a shell string)."""
    argv = [sys.executable, str(GENERATOR), "--out", str(out_m3u), "--xmltv", str(out_xml),
            "--now", str(NOW), "--hours", str(HOURS), *flags]
    subprocess.run(argv, check=True, capture_output=True, text=True, timeout=60)


def xmltv_ids(path):
    return [element.get("id", "") for element in ET.parse(str(path)).getroot().iter("channel")]


def playlist_ids(path):
    """tvg-ids through the helper's own parser, not a regex of our own."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    return [channel.get("tvgId", "") for channel in helper.parse_m3u(text)["channels"]]


class Gs2FixtureTest(unittest.TestCase):
    """The three cases, the fixture's own shape, and the pre-fix reproduction."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = pathlib.Path(tempfile.mkdtemp(prefix="omarchy-iptv-gs2-"))
        cls.addClassCleanup(shutil.rmtree, str(cls.tmp), True)
        cls.node = shutil.which("node")
        if not cls.node:
            # A hard failure, not a skip: the verdict is Model.js's, and a
            # suite that quietly stopped taking it would be green for nothing.
            # scripts/check.sh already refuses to run without node.
            raise RuntimeError("node is required to take the verdict from Model.js (see scripts/check.sh)")
        cls.playlist = cls.tmp / "one-group.m3u"
        cls.xml_match = cls.tmp / "match.xml"
        generate(cls.playlist, cls.xml_match, "--profile", "synthetic", "--channels", str(CHANNELS),
                 "--groups", "1", "--epg-ids", "1.0", "--dupes", "0", "--headers", "0",
                 "--multi-group", "0", "--seed", "1")
        cls.xml_disjoint = cls.tmp / "disjoint.xml"
        generate(cls.tmp / "disjoint-source.m3u", cls.xml_disjoint, "--profile", "realistic",
                 "--channels", str(CHANNELS), "--groups", "1", "--epg-ids", "1.0", "--dupes", "0",
                 "--headers", "0", "--multi-group", "0", "--seed", "2")
        cls.xml_one = cls.tmp / "one-match.xml"
        generate(cls.tmp / "one-source.m3u", cls.xml_one, "--profile", "synthetic", "--channels", "1",
                 "--groups", "1", "--epg-ids", "1.0", "--dupes", "0", "--seed", "1")

    def verdict(self, xml, playlist=None, model=MODEL):
        """The whole shipping pipeline on one (playlist, XMLTV) pair.

        A fresh cache directory each time; `playlist` then `epg` build
        channels.json and epg-now.json exactly as the plugin would, then
        verify.js takes the verdict from Model.js. -> (playlist status, epg
        status, verdict)."""
        cache = tempfile.mkdtemp(prefix="cache-", dir=str(self.tmp))
        code, playlist_status, stderr = run_helper("playlist", "--url", str(playlist or self.playlist),
                                                   "--cache-dir", cache)
        self.assertEqual(code, 0, stderr)
        self.assertTrue(playlist_status["ok"], playlist_status)
        code, epg_status, stderr = run_helper("epg", "--url", str(xml), "--cache-dir", cache, "--now", str(NOW))
        self.assertEqual(code, 0, stderr)
        self.assertTrue(epg_status["ok"], epg_status)
        argv = [self.node, str(VERIFY), str(model), os.path.join(cache, "channels.json"),
                os.path.join(cache, "epg-now.json"), str(NOW)]
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        verdict = json.loads(completed.stdout)
        self.assertTrue(verdict["channelsOk"], verdict)
        self.assertTrue(verdict["epgOk"], verdict)
        return playlist_status, epg_status, verdict

    def test_fixture_shape_is_the_repro_shape(self):
        """One group, a tvg-id on every row, and the three guides' id sets.

        The disjointness is asserted, not assumed: an XMLTV with no channels
        at all would be vacuously disjoint, so the disjoint guide must hold
        ids, and none of them may match a playlist id even case-insensitively
        (build_alias tries the lower-case form second)."""
        ids = playlist_ids(self.playlist)
        self.assertEqual(len(ids), CHANNELS)
        self.assertEqual(sum(1 for tvg in ids if tvg), CHANNELS, "a tvg-id on every row")
        self.assertEqual(len(set(ids)), CHANNELS, "60 distinct ids, no HD/SD twins")
        self.assertIn(ONE_ID, ids)
        code, status, stderr = run_helper("playlist", "--url", str(self.playlist),
                                          "--cache-dir", tempfile.mkdtemp(dir=str(self.tmp)))
        self.assertEqual(code, 0, stderr)
        self.assertEqual(status["channelCount"], CHANNELS)
        self.assertEqual(status["groupCount"], 1, "ONE group, so groupsNarrow is false and the EPG term decides")

        disjoint = xmltv_ids(self.xml_disjoint)
        self.assertGreaterEqual(len(disjoint), 1, "an empty guide would be disjoint for the wrong reason")
        self.assertEqual(set(ids) & set(disjoint), set())
        self.assertEqual({tvg.lower() for tvg in ids} & {tvg.lower() for tvg in disjoint}, set())

        self.assertEqual(set(ids) & set(xmltv_ids(self.xml_match)), set(ids), "the positive guide covers every id")
        self.assertEqual(xmltv_ids(self.xml_one), [ONE_ID])
        self.assertEqual(set(ids) & set(xmltv_ids(self.xml_one)), {ONE_ID}, "the boundary guide matches exactly one")

    def test_a_negative_no_match_means_single_line_rows(self):
        """(a) The defect's shape: guide configured, guide loaded, zero matches.

        Pre-fix, `epgConfigured` was true here and every row got a second
        line with nothing on it. Now `epgCoverage` says the data fills no row
        and `rowsHaveDetail` is false: single-line rows. The helper's own
        `matched` count and its warning say the same thing about the same
        data, one layer down."""
        _, epg, verdict = self.verdict(self.xml_disjoint)
        self.assertEqual(epg["matched"], 0)
        self.assertEqual(epg["channelTotal"], CHANNELS)
        self.assertIn(NO_MATCH_WARNING, epg["warnings"])
        self.assertEqual(verdict["total"], CHANNELS)
        self.assertEqual(verdict["axis"]["count"], 1)
        self.assertIs(verdict["axis"]["narrows"], False)
        self.assertIs(verdict["rowShowsGroup"], False)
        self.assertEqual(verdict["coverage"], {"total": CHANNELS, "withId": CHANNELS, "matched": 0, "carries": False})
        self.assertIs(verdict["rowsHaveDetail"], False, verdict)
        self.assertEqual((verdict["detailBlankRows"], verdict["detailFilledRows"]), (CHANNELS, 0),
                         "there is nothing the second line could print on any row")

    def test_b_positive_matching_guide_fills_the_line(self):
        """(b) Control: the same list, the guide it was generated with."""
        _, epg, verdict = self.verdict(self.xml_match)
        self.assertEqual(epg["matched"], CHANNELS)
        self.assertEqual(epg["nowCount"], CHANNELS, "the generator puts now inside a programme on every channel")
        self.assertNotIn(NO_MATCH_WARNING, epg["warnings"])
        self.assertEqual(verdict["coverage"], {"total": CHANNELS, "withId": CHANNELS, "matched": CHANNELS, "carries": True})
        self.assertIs(verdict["rowsHaveDetail"], True, verdict)
        self.assertEqual((verdict["detailBlankRows"], verdict["detailFilledRows"]), (0, CHANNELS))
        self.assertTrue(all(sample["detail"].startswith("Now: ") for sample in verdict["sample"]), verdict["sample"])

    def test_c_boundary_one_match_is_recorded(self):
        """(c) The original complaint at 1/N instead of 0/N -- a RECORD.

        One of sixty rows matches. The shipping rule is "carries when the
        count is above zero", so the line exists and 59 of the 60 rows print
        nothing on it. This asserts exactly that, with the numbers, so the
        behaviour is on record and a change to it is a red test rather than
        a surprise. It does not say whether that trade is right; a ruling
        would, and then these are the numbers to change."""
        _, epg, verdict = self.verdict(self.xml_one)
        self.assertEqual(epg["matched"], 1)
        self.assertEqual(epg["nowCount"], 1)
        self.assertNotIn(NO_MATCH_WARNING, epg["warnings"])
        self.assertEqual(verdict["coverage"], {"total": CHANNELS, "withId": CHANNELS, "matched": 1, "carries": True})
        # With one group the EPG term is the whole predicate, so the two
        # answers must agree whatever the threshold is.
        self.assertIs(verdict["axis"]["narrows"], False)
        self.assertEqual(verdict["rowsHaveDetail"], verdict["coverage"]["carries"])
        self.assertIs(verdict["rowsHaveDetail"], True, "recorded: 1 of 60 is enough for the shipping rule")
        self.assertEqual((verdict["detailBlankRows"], verdict["detailFilledRows"]), (CHANNELS - 1, 1))

    def test_prefix_decision_reproduces_the_defect(self):
        """The fixture shows the DEFECT, not only the fix (rule 11, kept runnable).

        A scratch copy of Model.js carries the one line 9d236d5 changed, put
        back the way it shipped before the fix. On case (a) every row then
        gets a second line and none of them has anything to print, which is
        D-GS-2 exactly. The tracked file is never touched. A no-op reversion
        cannot pass here: the shipping spelling must be found exactly once,
        and an unreverted copy answers rowsHaveDetail false."""
        source = MODEL.read_text(encoding="utf-8")
        self.assertEqual(source.count(SHIPPED_LINE), 1, "the shipping decision moved; update SHIPPED_LINE")
        self.assertEqual(source.count(PREFIX_LINE), 0)
        prefix = self.tmp / "Model.prefix.js"
        prefix.write_text(source.replace(SHIPPED_LINE, PREFIX_LINE), encoding="utf-8")
        _, epg, verdict = self.verdict(self.xml_disjoint, model=prefix)
        self.assertEqual(epg["matched"], 0)
        self.assertIs(verdict["coverage"]["carries"], False, "the data still fills no row")
        self.assertIs(verdict["rowsHaveDetail"], True, "pre-fix: the setting alone put a second line on every row")
        self.assertEqual((verdict["detailBlankRows"], verdict["detailFilledRows"]), (CHANNELS, 0),
                         "and there was nothing to print on any of them")

    def test_hand_readable_list_has_the_same_shape(self):
        """The committed eight-row list is verified, not trusted (rule 13).

        It carries the synthetic profile's ids by index, so the generator can
        produce its matching guide and the realistic-profile guide is
        disjoint from it; both cases are run through the whole pipeline."""
        ids = playlist_ids(HAND_LIST)
        self.assertEqual(ids, ["ch%05d.test" % (i + 1) for i in range(len(ids))])
        self.assertGreaterEqual(len(ids), 8)
        self.assertEqual(set(ids) & set(xmltv_ids(self.xml_disjoint)), set())
        hand_match = self.tmp / "hand-match.xml"
        generate(self.tmp / "hand-source.m3u", hand_match, "--profile", "synthetic", "--channels", str(len(ids)),
                 "--groups", "1", "--epg-ids", "1.0", "--dupes", "0", "--headers", "0", "--multi-group", "0",
                 "--seed", "1")
        self.assertEqual(set(xmltv_ids(hand_match)), set(ids))

        playlist_status, epg, verdict = self.verdict(self.xml_disjoint, playlist=HAND_LIST)
        self.assertEqual(playlist_status["groupCount"], 1)
        self.assertEqual(epg["matched"], 0)
        self.assertEqual(verdict["coverage"], {"total": len(ids), "withId": len(ids), "matched": 0, "carries": False})
        self.assertIs(verdict["rowsHaveDetail"], False, verdict)
        self.assertEqual(verdict["detailBlankRows"], len(ids))

        _, epg, verdict = self.verdict(hand_match, playlist=HAND_LIST)
        self.assertEqual(epg["matched"], len(ids))
        self.assertIs(verdict["rowsHaveDetail"], True, verdict)
        self.assertEqual(verdict["detailFilledRows"], len(ids))


if __name__ == "__main__":
    unittest.main()
