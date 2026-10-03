"""M4-01 the three-strategy EPG matcher, M4-02 the programme detail fields.

D-EPG-2: the shipped matcher renders 0 of 1,453 channels against the
project's own XMLTV asset, because the playlist carries iptv-org ids
(00sReplay.us@SD) and that guide carries Pluto's own
(673247127d5da5000817b4d6). docs/QA-RESULTS.md "D-EPG-2, 2026-10-02" holds
the measurements; docs/PLAN-M4.md M4-01 holds the repair.

Everything asserted here is asserted as a COUNT or as text the helper
actually wrote, never as "the feature is on" (CLAUDE.md rule 14), and every
expectation lives in tests/fixtures/epg-match.json so one fixture serves any
second implementation of the same rule.

Rule 11 proof, recorded, every run from this worktree with
`python3 -m unittest test_epg_match` in tests/:

  Against the helper as it shipped at 86cdca5 (bin/omarchy-iptv replaced by
  `git show HEAD:bin/omarchy-iptv`, this module and its fixtures unchanged):

      Ran 30 tests -- FAILED (failures=6, errors=20)
      Against the helper with the matcher and the detail fields: 30 tests, OK

  Twenty-six of the thirty go red on the code that shipped. The four that do
  not are proven by mutating the shipping function instead, one mutation at a
  time, with the helper restored in between -- including the two that pass
  before M4 only because the strategy they constrain did not exist yet:

    1. match_xmltv_channel, feed branch never taken     failures=6 errors=1
    2. build_alias, playlist-side name ambiguity indexed anyway   failures=5
         (reddens test_an_ambiguous_name_is_never_guessed)
    3. parse_xmltv, guide-side name ambiguity kept               failures=5
         (reddens test_an_ambiguous_name_is_never_guessed)
    4. claim_channel, every claim granted                       failures=10
         (reddens test_a_stronger_strategy_displaces_a_weaker_claim and the
          three direct claim tests)
    5. build_alias returns an index when there is no channel cache
                                                                 failures=1
         (reddens test_no_channel_cache_means_no_restriction)
    6. cmd_epg writes a status missing a count the emitted one carries
                                                                 failures=1
         (reddens test_the_status_is_also_what_is_written_to_disk)

  tests/test_epg.py was edited for M4-02 as well, and against the shipped
  helper that module reads: Ran 34 tests -- FAILED (failures=2, errors=2).
  The two failures are the detail fields now carried on fixtures that have
  declared them since M1; the two errors are encode_records' item arity.

Run: python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import os
import pathlib
import shutil
import tempfile
import unittest

from helper_loader import load_helper

helper = load_helper()
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
PLAYLIST = str(FIXTURES / "epg-match.m3u")
XMLTV = str(FIXTURES / "epg-match.xml")
EXPECTED = json.loads((FIXTURES / "epg-match.json").read_text(encoding="utf-8"))
NOW = EXPECTED["now"]


def run(*args):
    """Run the helper in-process; -> (exit code, last JSON line, stderr)."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(args))
    text = out.getvalue().strip()
    payload = json.loads(text.splitlines()[-1]) if text else None
    return code, payload, err.getvalue()


def read(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


class MatcherFixtureTest(unittest.TestCase):
    """The whole verb over the fixture pair, asserted against the fixture."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cache = cls.tmp.name
        code, _, stderr = run("playlist", "--url", PLAYLIST, "--cache-dir", cls.cache)
        assert code == 0, stderr
        code, cls.status, stderr = run("epg", "--url", XMLTV, "--cache-dir", cls.cache,
                                       "--now", str(NOW))
        assert code == 0, stderr
        cls.now_doc = read(os.path.join(cls.cache, "epg-now.json"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_status_counts_every_strategy_and_every_drop(self):
        """The acceptance of M4-01: counts, from the shipping verb.

        A count per strategy is the only thing that can tell the feed repair
        from the name repair -- docs/QA-RESULTS.md measured them as different
        repairs worth different channels, and the shipped status could not
        have distinguished them.
        """
        for key, value in EXPECTED["status"].items():
            self.assertEqual(self.status[key], value, key)
        # Nothing is counted twice and nothing is lost between the buckets.
        self.assertEqual(self.status["matchedById"] + self.status["matchedByFeed"]
                         + self.status["matchedByName"], self.status["matched"])

    def test_the_status_is_also_what_is_written_to_disk(self):
        self.assertEqual(read(os.path.join(self.cache, "epg-status.json")), self.status)

    def test_the_warnings_name_the_dropped_programmes(self):
        self.assertEqual(sorted(self.status["warnings"]), sorted(EXPECTED["warnings"]))

    def test_every_matched_channel_carries_the_right_programme(self):
        """Precision, which is the acceptance criterion and not recall.

        Each key below is a PLAYLIST tvg-id, because that is what the guide
        looks a row up by (Model.epgFields through row.tvgId), and each title
        is the one the guide declared for the channel it was matched to. A
        strategy that attached the wrong programme would show here as the
        wrong title, not as a missing row.
        """
        channels = self.now_doc["channels"]
        self.assertEqual(sorted(channels), sorted(EXPECTED["nowTitles"]))
        for key, title in EXPECTED["nowTitles"].items():
            self.assertEqual(channels[key]["now"]["title"], title, key)

    def test_an_ambiguous_name_is_never_guessed(self):
        """Both sides of the uniqueness rule, and the no-tvg-id limit.

        `ambi1.xx` and `ambi2.xx` share the name the guide's `pluto-twin`
        declares: ambiguous on our side. `guideambi.xx` is named by two guide
        declarations: ambiguous on the guide's side. The playlist's
        `Unkeyed Channel` row carries no tvg-id, so even though the guide
        names it exactly, there is no key to publish it under. All four stay
        blank, and the three guide channels that wanted them are counted as
        dropped rather than attached to something.
        """
        channels = self.now_doc["channels"]
        for key in EXPECTED["unmatched"]:
            self.assertNotIn(key, channels)
        titles = json.dumps(channels)
        for title in ("Twin Now", "Double Now", "Unkeyed Now"):
            self.assertNotIn(title, titles)

    def test_a_stronger_strategy_displaces_a_weaker_claim(self):
        """`pluto-clash` reaches Clash Channel by NAME earlier in the stream
        than `Clash.us` reaches it by id. The id must win anyway, and the
        programmes the name claim had already collected must be discarded --
        otherwise the answer depends on the order the guide streamed, and two
        schedules interleave into one that is wrong everywhere."""
        entry = self.now_doc["channels"]["Clash.us"]
        self.assertEqual(entry["now"]["title"], "Clash Id Now")
        self.assertNotIn("Clash Name Now", json.dumps(self.now_doc))

    def test_two_guide_channels_never_merge_into_one_row(self):
        """`Multi.us@SD` and `Multi.us@HD` both fold to the playlist's
        `Multi.us`. The first claims it; the second is refused and counted,
        never appended."""
        entry = self.now_doc["channels"]["Multi.us"]
        self.assertEqual(entry["now"]["title"], "Multi SD Now")
        self.assertNotIn("Multi HD Now", json.dumps(self.now_doc))

    def test_the_detail_fields_round_trip_through_the_record_format(self):
        """M4-02 end to end: desc, category and episode out of the XML, into
        the window's record string, out through compute_now_next's
        concatenation and into epg-now.json."""
        entry = self.now_doc["channels"]["Detail.us"]
        self.assertEqual(entry["now"], EXPECTED["detail"]["now"])
        self.assertEqual(entry["next"], EXPECTED["detail"]["next"])

    def test_only_declared_fields_appear(self):
        """A programme that declares nothing gains nothing, and a whitespace
        `<desc>` is nothing. Exact.us declares `<desc>   </desc>`."""
        self.assertEqual(set(self.now_doc["channels"]["Exact.us"]["now"]),
                         {"title", "start", "stop"})
        self.assertEqual(set(self.now_doc["channels"]["Detail.us"]["next"]),
                         {"title", "episode", "start", "stop"})

    def test_no_url_path_or_query_reaches_the_panel(self):
        """Rule 5 at the new sink. The fixture's description carries a URL
        with a path and a query, and the programme also declares an <icon
        src> and a <url>; the window file must hold none of it.

        What the description DOES still hold is the escaped `<img>` tag the
        XML parser decoded, with its URL cut back to scheme://host: redaction
        is not a closure over markup, and `Text.PlainText` in the guide is
        the only thing that stops it being fetched (D-TEXT-1).
        """
        window = pathlib.Path(self.cache, helper.EPG_WINDOW_FILE).read_text(encoding="utf-8")
        for forbidden in EXPECTED["descForbidden"]:
            self.assertNotIn(forbidden, window, forbidden)
        desc = self.now_doc["channels"]["Detail.us"]["now"]["desc"]
        self.assertIn('<img src="http://evil.example.test">', desc)
        self.assertLessEqual(len(desc), helper.EPG_MAX_DESC)

    def test_a_long_description_is_cut_at_the_cap(self):
        """The fixture's description is over EPG_MAX_DESC and comes back
        shorter than the cap, because the cut happens before redaction and
        the redaction then removes two URL paths. Nothing is appended, so it
        ends mid-word -- that is the documented behaviour, asserted."""
        desc = self.now_doc["channels"]["Detail.us"]["now"]["desc"]
        self.assertEqual(len(desc), 376)
        self.assertLess(len(desc), helper.EPG_MAX_DESC)
        self.assertTrue(desc.endswith("Filler twe"), desc[-20:])

    def test_the_counts_survive_a_now_only_recompute(self):
        """`--now-only` reports the fetch's numbers, because they live in the
        window. A recompute that answered 0 would read as a regression that
        did not happen."""
        # On a COPY of the cache: a recompute rewrites epg-status.json, and
        # one test must not decide what another one reads.
        with tempfile.TemporaryDirectory() as other:
            cache = os.path.join(other, "cache")
            shutil.copytree(self.cache, cache)
            code, status, stderr = run("epg", "--now-only", "--cache-dir", cache,
                                       "--now", str(NOW + 60))
        self.assertEqual(code, 0, stderr)
        self.assertTrue(status["fromCache"])
        for key, value in EXPECTED["status"].items():
            if key != "nowCount":
                self.assertEqual(status[key], value, key)


class EpisodeSystemTest(unittest.TestCase):
    """Only an EPISODE NUMBER goes under the label "Episode" (D-EPG-2 round).

    Found by opening the panel on the real guide, not by a fixture: the
    project's own XMLTV asset carries `original-air-date` 8,799 times against
    `onscreen` 4,273, and the date comes first in document order, so the panel
    showed `20080101000000 +0000` as the episode on 4,526 programmes. The same
    feed's `pluto` system is a 24-character hex id.
    """

    @staticmethod
    def _prog(*pairs):
        import xml.etree.ElementTree as ET
        elem = ET.Element("programme")
        for system, text in pairs:
            child = ET.SubElement(elem, "episode-num")
            if system is not None:
                child.set("system", system)
            child.text = text
        return elem

    def test_a_date_is_not_an_episode_number(self):
        e = self._prog(("original-air-date", "20080101000000 +0000"))
        self.assertEqual(helper.episode_text(e), "")

    def test_a_provider_id_is_not_either(self):
        e = self._prog(("pluto", "68c98f288376cad38dbef85b"), ("thetvdb.com", "series/1234"))
        self.assertEqual(helper.episode_text(e), "")

    def test_onscreen_wins_wherever_it_appears_in_the_order(self):
        e = self._prog(("original-air-date", "19920406000000 +0000"), ("onscreen", "S08E10"))
        self.assertEqual(helper.episode_text(e), "S08E10")

    def test_a_bare_episode_num_is_taken_as_onscreen(self):
        self.assertEqual(helper.episode_text(self._prog((None, "S2 E5"))), "S2 E5")

    def test_the_machine_form_is_still_translated_when_it_is_all_there_is(self):
        e = self._prog(("original-air-date", "20080101000000 +0000"), ("xmltv_ns", "0.1.0/1"))
        self.assertEqual(helper.episode_text(e), "S1 E2")


class NameNoiseTest(unittest.TestCase):
    """The matcher's name key, which is NOT the search key (D-EPG-2).

    Found by running the integrated milestone against the REAL guide rather
    than against this file's fixtures: matching on normalize_text alone
    reached 125 of the installed 1,453 channels and taking the distribution
    markers out first reached 224, because 1,155 of those names carry one.
    The fixtures could not see it because synthetic names never say
    "(1080p)" -- which is the hazard engineering rule 10 names, a double more
    forgiving than the real thing.

    These call the shipping function rather than re-stating its pattern.
    """

    def test_a_resolution_marker_is_not_part_of_a_channels_identity(self):
        same = helper.epg_name_key
        self.assertEqual(same("48 Hours (1080p)"), same("48 Hours"))
        self.assertEqual(same("Avang TV (720p)"), same("Avang TV"))
        self.assertEqual(same("Foo (2160p)"), same("Foo"))
        self.assertEqual(same("Foo (UHD)"), same("Foo"))

    def test_a_bracketed_annotation_is_not_either(self):
        same = helper.epg_name_key
        self.assertEqual(same("NBC Sports Philadelphia (1080p) [Geo-blocked]"),
                         same("NBC Sports Philadelphia"))
        self.assertEqual(same("Reuters [Not 24/7]"), same("Reuters"))

    def test_it_takes_out_the_markers_and_nothing_else(self):
        # A digit that is part of the name survives: "Channel 4" is not
        # "Channel", and a name that merely contains 1080p is not emptied
        # into something another row could collide with.
        same = helper.epg_name_key
        self.assertNotEqual(same("Channel 4"), same("Channel"))
        self.assertNotEqual(same("1080p TV"), same("TV"))
        self.assertEqual(same("Foo  (1080p)  Bar"), same("Foo Bar"))

    def test_the_search_key_is_left_alone(self):
        # normalize_text is the SEARCH key and the four ranking tiers are
        # calibrated on it: someone typing "1080" is looking for exactly
        # these markers. Doing this inside normalize_text would have been the
        # cheap way and it would have been wrong.
        self.assertIn("1080", helper.normalize_text("48 Hours (1080p)"))
        self.assertNotIn("1080", helper.epg_name_key("48 Hours (1080p)"))


class OldWindowTest(unittest.TestCase):
    def test_a_window_written_before_m4_reports_none_not_zero(self):
        """An epg-window.txt from an older helper has no match counts. The
        status must say so rather than claim zero matches by strategy, which
        would read as a matcher that stopped working."""
        with tempfile.TemporaryDirectory() as tmp:
            meta = {
                "version": 1, "fetchedAt": NOW, "sourceHost": "epg.example.test",
                "sourceKey": "x", "channelsMtime": None, "windowStart": NOW - 7200,
                "windowEnd": NOW + 43200, "restricted": True, "channelTotal": 3,
                "matched": 1, "epgChannels": 1, "programmeCount": 1, "warnings": [],
            }
            helper.write_window(os.path.join(tmp, helper.EPG_WINDOW_FILE), meta,
                                {"a.tv": helper.encode_record(NOW - 60, NOW + 60, "Old")})
            code, status, stderr = run("epg", "--now-only", "--cache-dir", tmp, "--now", str(NOW))
            self.assertEqual(code, 0, stderr)
            self.assertEqual(status["matched"], 1)
            for key in ("matchedById", "matchedByFeed", "matchedByName",
                        "nameIndexed", "nameDroppedPlaylist", "nameDroppedGuide"):
                self.assertIsNone(status[key], key)
            self.assertEqual(status["nowCount"], 1)


class IndexTest(unittest.TestCase):
    """build_alias and match_xmltv_channel called directly."""

    def index(self, channels):
        return helper.build_alias({"channels": channels})

    def test_no_channel_cache_means_no_restriction(self):
        self.assertEqual(helper.build_alias(None), (None, 0))
        self.assertEqual(helper.build_alias({}), (None, 0))

    def test_the_strategies_are_tried_in_order(self):
        index, total = self.index([
            {"tvgId": "A.us@SD", "name": "Alpha", "nameKey": "alpha"},
            {"tvgId": "B.us", "name": "Beta", "nameKey": "beta"},
        ])
        self.assertEqual(total, 2)
        self.assertEqual(helper.match_xmltv_channel(index, "A.us@SD", {}),
                         ("A.us@SD", helper.EPG_MATCH_ID))
        self.assertEqual(helper.match_xmltv_channel(index, "a.us@sd", {}),
                         ("A.us@SD", helper.EPG_MATCH_ID))
        # The feed form, both directions.
        self.assertEqual(helper.match_xmltv_channel(index, "A.us", {}),
                         ("A.us@SD", helper.EPG_MATCH_FEED))
        self.assertEqual(helper.match_xmltv_channel(index, "B.us@HD", {}),
                         ("B.us", helper.EPG_MATCH_FEED))
        # The name, only through a guide name that is not blanked.
        self.assertEqual(helper.match_xmltv_channel(index, "x1", {"x1": "beta"}),
                         ("B.us", helper.EPG_MATCH_NAME))
        self.assertEqual(helper.match_xmltv_channel(index, "x1", {"x1": ""}), ("", -1))
        self.assertEqual(helper.match_xmltv_channel(index, "x1", {}), ("", -1))

    def test_rows_sharing_one_tvg_id_are_not_an_ambiguous_name(self):
        """One channel listed twice is not two channels: both rows share the
        key, so pointing the name at it attaches a programme to both."""
        index, total = self.index([
            {"tvgId": "dup.tv", "name": "Dup", "nameKey": "dup"},
            {"tvgId": "dup.tv", "name": "Dup", "nameKey": "dup"},
        ])
        self.assertEqual(total, 2)
        self.assertEqual(index["nameIndexed"], 1)
        self.assertEqual(index["nameDroppedPlaylist"], 0)
        self.assertEqual(helper.match_xmltv_channel(index, "g1", {"g1": "dup"}),
                         ("dup.tv", helper.EPG_MATCH_NAME))

    def test_an_older_cache_without_name_keys_still_matches_by_name(self):
        """`nameKey` has only been in channels.json since F-PERF-1. Without
        it the name is folded here, so a name match does not have to wait for
        the next playlist refresh."""
        index, _ = self.index([{"tvgId": "c.tv", "name": "The Cafe"}])
        self.assertEqual(helper.match_xmltv_channel(index, "g1", {"g1": helper.normalize_text("The Caf" + "\u00e9")}),
                         ("c.tv", helper.EPG_MATCH_NAME))

    def test_a_channel_without_a_tvg_id_is_in_no_map(self):
        index, total = self.index([{"name": "Nameless Key"}])
        self.assertEqual((total, index["nameIndexed"], index["nameDroppedPlaylist"]), (1, 0, 0))
        self.assertEqual(index["exact"], {})
        self.assertEqual(helper.match_xmltv_channel(index, "g1", {"g1": "nameless key"}), ("", -1))

    def test_the_first_playlist_row_wins_a_shared_feed_base(self):
        index, _ = self.index([
            {"tvgId": "T.us@SD", "name": "T SD", "nameKey": "t sd"},
            {"tvgId": "T.us@HD", "name": "T HD", "nameKey": "t hd"},
        ])
        self.assertEqual(helper.match_xmltv_channel(index, "T.us", {}),
                         ("T.us@SD", helper.EPG_MATCH_FEED))


class ClaimTest(unittest.TestCase):
    """claim_channel, the rule that keeps two guide channels off one row."""

    def test_first_claim_is_granted_and_repeats_are_idempotent(self):
        claim, pending = {}, {}
        self.assertEqual(helper.claim_channel(claim, pending, "k", helper.EPG_MATCH_NAME, "g1"), 1)
        self.assertEqual(helper.claim_channel(claim, pending, "k", helper.EPG_MATCH_NAME, "g1"), 0)

    def test_a_stronger_rank_displaces_and_discards(self):
        claim, pending = {}, {"k": ["collected by the name claim"]}
        helper.claim_channel(claim, pending, "k", helper.EPG_MATCH_NAME, "g1")
        self.assertEqual(helper.claim_channel(claim, pending, "k", helper.EPG_MATCH_ID, "g2"), 1)
        self.assertEqual(pending, {}, "the weaker claim's programmes must not survive")
        self.assertEqual(claim["k"], (helper.EPG_MATCH_ID, "g2"))

    def test_a_weaker_rank_is_refused_and_keeps_its_hands_off(self):
        claim, pending = {}, {"k": ["collected by the id claim"]}
        helper.claim_channel(claim, pending, "k", helper.EPG_MATCH_ID, "g1")
        self.assertEqual(helper.claim_channel(claim, pending, "k", helper.EPG_MATCH_NAME, "g2"), -1)
        self.assertEqual(pending, {"k": ["collected by the id claim"]})
        self.assertEqual(claim["k"], (helper.EPG_MATCH_ID, "g1"))

    def test_equal_ranks_are_first_come(self):
        claim, pending = {}, {}
        helper.claim_channel(claim, pending, "k", helper.EPG_MATCH_FEED, "g1")
        self.assertEqual(helper.claim_channel(claim, pending, "k", helper.EPG_MATCH_FEED, "g2"), -1)


class DetailFieldTest(unittest.TestCase):
    """The M4-02 fields where they are built and where they are encoded."""

    def test_the_episode_systems(self):
        """xmltv_ns is zero-based `season.episode.part`, optionally with a
        `/total`; onscreen is already human-readable. An unparseable field is
        dropped rather than guessed, so the panel shows no episode at all."""
        self.assertEqual(helper.episode_ns_text("0.1.0/1"), "S1 E2")
        self.assertEqual(helper.episode_ns_text("1.4"), "S2 E5")
        self.assertEqual(helper.episode_ns_text("3/12.0/24"), "S4 E1")
        self.assertEqual(helper.episode_ns_text(".2"), "E3")
        self.assertEqual(helper.episode_ns_text("5"), "S6")
        for raw in ("", ".", "x.y", "series two"):
            self.assertEqual(helper.episode_ns_text(raw), "", raw)

    def test_a_detail_free_record_is_byte_identical_to_the_old_format(self):
        """The record format is the reason the 10k budget holds, so M4-02 may
        not cost a programme that declares nothing. This is the shape the
        helper has written since M1: ten digits, a space, ten digits, a
        space, the JSON title."""
        self.assertEqual(helper.encode_record(1, 2, "Plain"), '0000000001 0000000002 "Plain"')
        self.assertEqual(helper.encode_record(1, 2, "Plain", {}), '0000000001 0000000002 "Plain"')
        self.assertEqual(helper.encode_record(1, 2, "Plain", {"desc": ""}),
                         '0000000001 0000000002 "Plain"')

    def test_a_record_with_detail_keeps_the_fixed_width_prefix(self):
        record = helper.encode_record(1789245000, 1789248600, 'He said "hi"',
                                      {"desc": "Back\\slash", "category": "News", "episode": "S1 E2"})
        self.assertEqual(record[:10], "1789245000")
        self.assertEqual(record[10], " ")
        self.assertEqual(record[11:21], "1789248600")
        self.assertEqual(record[21], " ")
        # Both readers agree, and both produce valid JSON.
        self.assertEqual(json.loads(helper.programme_json(record)), {
            "title": 'He said "hi"', "desc": "Back\\slash", "category": "News",
            "episode": "S1 E2", "start": 1789245000, "stop": 1789248600,
        })
        self.assertEqual(helper.record_to_dict(record), {
            "title": 'He said "hi"', "desc": "Back\\slash", "category": "News",
            "episode": "S1 E2", "start": 1789245000, "stop": 1789248600,
        })

    def test_detail_cannot_move_the_bisect(self):
        """What the record format's comment claims, asserted: compute_now_next
        finds the same now and next whether or not the records carry detail,
        because every comparison it makes is decided at or before index 10."""
        start = NOW - 3600
        plain, rich = [], []
        for step in range(4):
            first, last = start + step * 1800, start + (step + 1) * 1800
            plain.append(helper.encode_record(first, last, "P%d" % step))
            rich.append(helper.encode_record(first, last, "P%d" % step, {
                "desc": "~" * 300, "category": "9999999999 0000000000", "episode": "S1 E%d" % step}))
        sep = helper.EPG_RECORD_SEP
        for records in (plain, rich):
            window = {"lines": ['"a.tv"\t' + sep.join(records)]}
            fragments, valid_until, now_count = helper.compute_now_next(window, NOW)
            entry = json.loads("{" + fragments[0] + "}")["a.tv"]
            self.assertEqual(entry["now"]["title"], "P2")
            self.assertEqual(entry["next"]["title"], "P3")
            # EPG_VALID_MAX caps the answer: both boundaries here are
            # further out than five minutes.
            self.assertEqual((valid_until, now_count), (NOW + helper.EPG_VALID_MAX, 1))

    def test_the_record_separator_cannot_be_injected(self):
        """DEL separates records and a provider controls the description, so
        a description containing DEL would otherwise split one programme into
        two unparseable ones. clean_field folds it to a space with every
        other control character, before anything is encoded."""
        poisoned = "one" + helper.EPG_RECORD_SEP + '0000000001 0000000002 "fake"'
        detail = {"desc": helper.clean_detail(poisoned, helper.EPG_MAX_DESC)}
        blob, count = helper.encode_records([(1, 2, helper.clean_title(poisoned), detail)])
        self.assertEqual(count, 1)
        self.assertEqual(len(blob.split(helper.EPG_RECORD_SEP)), 1, "one programme, one record")
        self.assertEqual(helper.record_to_dict(blob)["desc"],
                         'one 0000000001 0000000002 "fake"')

    def test_a_detail_field_is_capped_and_url_redacted(self):
        """Called directly, at the cap each field actually ships with."""
        self.assertEqual(len(helper.clean_detail("d" * 900, helper.EPG_MAX_DESC)),
                         helper.EPG_MAX_DESC)
        self.assertEqual(len(helper.clean_detail("c" * 900, helper.EPG_MAX_CATEGORY)),
                         helper.EPG_MAX_CATEGORY)
        self.assertEqual(len(helper.clean_detail("e" * 900, helper.EPG_MAX_EPISODE)),
                         helper.EPG_MAX_EPISODE)
        self.assertEqual(helper.clean_detail("see http://u:p@host.test/a?b=c now", helper.EPG_MAX_DESC),
                         "see http://host.test now")
        self.assertEqual(helper.clean_detail("  spaced\n\tout  ", helper.EPG_MAX_DESC), "spaced out")


class OldFixtureTest(unittest.TestCase):
    def test_exact_id_still_wins_on_the_old_fixtures(self):
        """The regression guard for M4-01: on tests/fixtures/epg-channels.m3u
        every match is still an id match, which is the measured truth for a
        playlist and guide that agree on ids. A matcher whose name fallback
        reached rows the id strategy already owned would show up here as a
        matchedById that moved."""
        with tempfile.TemporaryDirectory() as tmp:
            code, _, stderr = run("playlist", "--url", str(FIXTURES / "epg-channels.m3u"),
                                  "--cache-dir", tmp)
            self.assertEqual(code, 0, stderr)
            code, status, stderr = run("epg", "--url", str(FIXTURES / "epg-basic.xml"),
                                       "--cache-dir", tmp, "--now", "1789246800")
            self.assertEqual(code, 0, stderr)
            self.assertEqual(status["matched"], 8)
            self.assertEqual(status["matchedById"], 8)
            self.assertEqual(status["matchedByFeed"], 0)
            self.assertEqual(status["matchedByName"], 0)
            self.assertEqual(status["nameIndexed"], 10)
            self.assertEqual(status["nameDroppedPlaylist"], 0)


if __name__ == "__main__":
    unittest.main()
