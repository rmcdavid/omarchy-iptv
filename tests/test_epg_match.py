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

Rule 11 proof, recorded, every run in an isolated copy of this worktree with
the helper replaced or mutated and nothing else changed. Re-levelled on
2026-10-03 for the review of the M4 round: the counts below used to be this
module's own 30-test counts from before integration, and 18 cases have been
added since.

  Against the helper as it shipped at e83e4a6, the commit before the matcher
  (`git show e83e4a6:bin/omarchy-iptv`), from tests/ with
  `python3 -m unittest test_epg_match`:

      Ran 48 tests -- FAILED (failures=7, errors=37)
      Against the helper on the tree: 48 tests, OK

  Forty-four of the forty-eight go red on the code that shipped. The four
  that do not are test_no_channel_cache_means_no_restriction,
  test_the_status_is_also_what_is_written_to_disk,
  test_an_ambiguous_name_is_never_guessed and
  test_a_stronger_strategy_displaces_a_weaker_claim -- the last two pass
  before M4 only because the strategy they constrain did not exist yet -- so
  they are proven by mutating the shipping function instead, one mutation at
  a time, same command, with the helper restored in between:

    1. match_xmltv_channel, feed branch never taken     failures=6 errors=1
    2. build_alias, playlist-side name ambiguity indexed anyway   failures=5
         (reddens test_an_ambiguous_name_is_never_guessed)
    3. parse_xmltv, guide-side name ambiguity kept                failures=8
         (reddens test_an_ambiguous_name_is_never_guessed and all three
          GuideOrderTest cases)
    4. claim_channel, every claim granted                        failures=10
         (reddens test_a_stronger_strategy_displaces_a_weaker_claim and the
          FOUR direct claim tests -- ClaimTest holds four and all four go)
    5. build_alias returns an index when there is no channel cache
                                                                 failures=1
         (reddens test_no_channel_cache_means_no_restriction)
    6. the status written to disk misses a count the emitted one carries
                                                                 failures=1
         (reddens test_the_status_is_also_what_is_written_to_disk)

  The review of the M4 round found two decisions nothing observed and seven
  more that no fixture could see. Each mutation below is one of those, run on
  its own against the WHOLE suite -- `python3 -m unittest discover -s tests`,
  which is 740 tests OK on the tree -- because "the gate stays green while
  the repair is reverted" was the finding:

    M1. epg_name_key -> normalize_text at the PLAYLIST call site failures=5
    M2. the same at the GUIDE call site                          failures=5
    M3. both call sites                                          failures=5
         Before the `noise.xx` and `gnoise.xx` fixture rows, ALL THREE of
         these were 729 tests OK: the milestone's headline repair was
         revertible whole with the gate green, because NameNoiseTest calls
         epg_name_key directly and no fixture pair needed the strip in order
         to match. It takes both rows -- the markers on our side, then on the
         guide's -- because either one alone leaves the other site green.
    M4. clean_detail cuts before redacting (the shipped order)   failures=2
         (reddens the two sink cases; this is the blocker)
    M5. the first NON-EMPTY display-name (the shipped rule)      failures=5
    M6. the LAST non-empty display-name                          failures=5
    M7. the guide-side collision blanks the lookup and revokes nothing
         (the shipped rule)                                      failures=2
         (reddens the two GuideOrderTest cases that are not DTD-ordered)
    M8. element_text reads elem.text only (the shipped rule)     failures=1
    M9. episode_text takes the first accepted system, no onscreen preference
                                                                 failures=1
         (test_onscreen_wins_wherever_it_appears_in_the_order, which could
          not be reddened by any mutation of the rule it names until its
          competing element became xmltv_ns)

  tests/test_epg.py carries the same round's budget cases, and the two
  committed ones were green only because the generator emitted no detail:
    M10. generate_xmltv(detail=True) under the committed 2.0 s fetch ceiling
         -> FAILED (failures=1), "epg fetch took 2515 ms for 48k programmes"
    M11. a detail dict in the committed 10k x 28 now-only case
         -> FAILED (failures=1), "epg --now-only took 549 ms (best of 3)"
         against its 500 ms ceiling
  Against e83e4a6's helper that module reads: Ran 36 tests -- FAILED
  (failures=2, errors=4), six of the thirty-six.

F-EPG-11, the ADDRESS strategy, 2026-10-04. Rule 11 again, same method: each
run is the WHOLE suite in an isolated copy of this worktree with one thing
changed and nothing else, helper restored in between. Copying the tree out of
git costs 5 errors in test_marketplace_capabilities on every run below,
before and after, and they are not counted as reddening anything.

  Baseline in the worktree: Ran 825 tests, OK. With this round:
  Ran 843 tests, OK.

  Against the helper at 9ae43cf, the commit before this strategy, with this
  round's tests and fixtures in place:

      Ran 842 tests -- FAILED (failures=8, errors=20, skipped=2)

  Twenty-three of the twenty-eight are this round's: the whole of
  AddressStrategyTest and AddressIndexTest, the fixture count cases, and the
  precision cases F-EPG-11 re-levelled. The decisions INSIDE the strategy
  cannot be reddened by removing it, so each one is a named mutation of the
  shipping function, one at a time:

    M-F1. EPG_ADDR_MIN_TOKEN 12 -> 1 (the collision guard removed)
                                                      failures=11
         (reddens test_a_guide_id_shorter_than_the_floor_claims_nothing,
          and the loosened floor also makes two real addresses collide)
    M-F2. build_alias indexes the LOGO as well as the stream URL
                                                       failures=6
         (reddens test_a_guide_id_in_the_artwork_is_not_a_stream_identity)
    M-F3. the address lookup moved BELOW the name lookup
                                             failures=7, errors=2
         (reddens both ranking cases and the strategy case)
    M-F4. the address lookup moved ABOVE the exact tvg-id lookup
                                             failures=4, errors=1
         (reddens test_a_declared_tvg_id_is_consulted_before_an_address.
          THIS MUTATION SURVIVED THE FIRST VERSION OF THIS MODULE: the rank
          case passed under it, because there the two strategies resolved two
          DIFFERENT guide channels onto one row and claim_channel settled it
          either way. It takes one guide id that the two maps resolve to two
          different ROWS to see the order at all, which is what the
          `aaaaaaaaaaaaaaaaaaaa0009` pair in the fixture is for)
    M-F5. the address lookup moved BELOW the feed lookup
                                             failures=5, errors=1
         (reddens test_the_address_outranks_the_feed_base)
    M-F6. build_alias keeps the first claim on a token two rows share
                                                       failures=6
         (reddens test_an_address_two_rows_share_is_dropped_rather_than_guessed)
    M-F7. the address token folded to lower case when indexed
                                                       failures=6
         (reddens test_the_address_match_is_case_sensitive)

Run: python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import os
import pathlib
import re
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
        # Summed over EPG_MATCH_KEYS and not over three names spelled out
        # here: a strategy added to that tuple and forgotten in the status
        # would have left this sum green, which is how F-EPG-11's counter
        # could have shipped unreported.
        self.assertEqual(sum(self.status[key] for key in helper.EPG_MATCH_KEYS),
                         self.status["matched"])
        for key in helper.EPG_MATCH_KEYS:
            self.assertIn(key, EXPECTED["status"],
                          "%s has no expectation in the fixture" % key)

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

    def test_the_matcher_joins_on_the_name_key_and_not_the_search_key(self):
        """M4-01's headline repair, observed at the sink rather than on the
        function that performs it.

        `noise.xx` and `gnoise.xx` are the two rows whose playlist name and
        guide display-name are DIFFERENT strings under normalize_text, the
        search key, and the same string under epg_name_key, the matcher's.
        They are mirror images -- `noise.xx` carries the distribution markers
        on OUR side, `gnoise.xx` on the GUIDE's -- and it takes both, because
        the key is called at two sites and one row leaves the other site
        revertible with the suite green. Both keys are computed here by the
        shipping functions over the names the two fixtures actually carry
        (CLAUDE.md rule 14: the decision is observed where it lands, not
        where it is implemented).
        """
        import xml.etree.ElementTree as ET
        declared = [child.text for channel in ET.parse(XMLTV).getroot().iterfind("channel")
                    for child in channel.iterfind("display-name")]
        for key in EXPECTED["noiseOnlyNames"]:
            ours = next(c["name"] for c in
                        read(os.path.join(self.cache, "channels.json"))["channels"]
                        if c.get("tvgId") == key)
            theirs = next((name for name in declared
                           if helper.epg_name_key(name) == helper.epg_name_key(ours)), None)
            self.assertIsNotNone(theirs, "no guide declaration folds to %r" % ours)
            self.assertNotEqual(helper.normalize_text(ours), helper.normalize_text(theirs), key)
            self.assertEqual(helper.epg_name_key(ours), helper.epg_name_key(theirs), key)
            self.assertIn(key, self.now_doc["channels"],
                          "%r is declared by the guide as %r and still has no row" % (ours, theirs))
            self.assertEqual(self.now_doc["channels"][key]["now"]["title"],
                             EXPECTED["nowTitles"][key], key)

    def test_the_display_name_taken_is_the_one_the_playlist_claims(self):
        """XMLTV allows several <display-name>s and ranks none of them.
        `pluto-numfirst` declares a channel number first, the matching name
        second and a foreign-language variant third; `pluto-lang` declares a
        language we do not have first. Taking "the first non-empty one" lost
        both, and so does taking the last -- the playlist is the only thing
        on the machine that can choose, and these rows are blank unless it
        does."""
        channels = self.now_doc["channels"]
        for key, title in EXPECTED["displayNameChoice"].items():
            self.assertIn(key, channels, key)
            self.assertEqual(channels[key]["now"]["title"], title, key)

    def test_a_description_keeps_the_text_after_a_child_element(self):
        """`elem.text` is only the text before the first child, so a <desc>
        carrying markup lost its body at the first tag: `Hello <b>world</b>
        and more` arrived as "Hello". The whole run of text survives, and is
        still folded and capped by the same sink."""
        self.assertEqual(self.now_doc["channels"]["Markup.us"]["now"]["desc"],
                         EXPECTED["markupDesc"])

    def test_a_cut_inside_a_url_never_publishes_the_userinfo(self):
        """Rule 5, at the offset that broke it.

        `Sink.us` declares a description whose EPG_MAX_DESC cut falls inside
        the password of `http://u5er:5ecretpw@host.example/live/x.m3u8?t=abc`.
        Cut first, that is `http://u5er:5e` -- no `@` left, so urlparse reads
        `u5er` as the host and the redactor PUBLISHED THE USERNAME, into the
        window file, into epg-now.json and from there onto the accessibility
        bus. Asserted at the sink: the credential appears in neither file,
        and what is left is the pad alone.
        """
        sink = EXPECTED["sink"]
        window = pathlib.Path(self.cache, helper.EPG_WINDOW_FILE).read_text(encoding="utf-8")
        published = json.dumps(self.now_doc) + window
        for forbidden in sink["forbidden"]:
            self.assertNotIn(forbidden, published, forbidden)
        desc = self.now_doc["channels"]["Sink.us"]["now"]["desc"]
        self.assertEqual(desc, sink["padChar"] * sink["nowDescLength"])

    def test_a_long_description_is_cut_at_the_cap(self):
        """The fixture's description is over EPG_MAX_DESC and comes back
        shorter than the cap, because the two URLs inside the first 400 code
        points lose their paths. Nothing is appended, so it ends mid-word --
        that is the documented behaviour, asserted. The cut that produced
        this one falls in prose; the cut that falls inside a URL is
        test_a_cut_inside_a_url_never_publishes_the_userinfo."""
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


ADDR = EXPECTED["addr"]
_ROW_URL = re.compile(r'^#EXTINF:[^\n]*tvg-id="([^"]*)"[^\n]*\n([^#\n][^\n]*)$',
                      re.MULTILINE)
_ROW_LOGO = re.compile(r'^#EXTINF:[^\n]*tvg-id="([^"]*)"[^\n]*tvg-logo="([^"]*)"',
                       re.MULTILINE)


def playlist_rows(path):
    """tvg-id -> stream URL, read out of the m3u itself.

    The fixture's own side of every address assertion is read from the
    FIXTURE and not from the helper's parse, so a test cannot be satisfied by
    the same code it is testing (CLAUDE.md rule 14).
    """
    text = pathlib.Path(path).read_text(encoding="utf-8")
    return {tvg: url.strip() for tvg, url in _ROW_URL.findall(text)}


def playlist_logos(path):
    text = pathlib.Path(path).read_text(encoding="utf-8")
    return dict(_ROW_LOGO.findall(text))


def guide_names(path):
    """guide channel id -> its first <display-name>, read out of the xml."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    return dict(re.findall(r'<channel id="([^"]+)"><display-name>([^<]*)</display-name>',
                           text))


class AddressStrategyTest(unittest.TestCase):
    """F-EPG-11: the guide channel id that the playlist row's own ADDRESS names.

    The M4-01 precision audit (docs/QA-EPG-PRECISION.md) graded the name
    matcher with an identifier the matcher never read: the guide's channel id,
    sitting in the stream URL of the row that streams that channel. Measured
    on the frozen 1,453-channel list against the frozen 427-declaration
    guide: 193 rows carry such an id, the name matcher already paired 153 of
    them with THAT SAME guide channel, paired 0 of them with a different one,
    and left 40 unmatched. So the identifier was never in disagreement with
    the matcher -- it was simply unread, and reading it takes `matched` from
    226 to 265.

    Each case below pins one decision, and every case first proves the join
    was AVAILABLE -- the id really is in that row's address and the guide
    really declares it with a programme in the window -- before asserting
    what the matcher did with it. Without that half, "it did not match" is
    satisfied by a fixture that never offered the match.

    Rule 11, counts recorded in the module docstring: all nine cases go red
    against the helper at 9ae43cf, where the strategy does not exist, and the
    decisions INSIDE the strategy are proven by the named mutations listed
    there -- the token floor, the artwork exclusion, the three rank
    positions, the playlist-side uniqueness rule and the case fold.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cache = cls.tmp.name
        code, _, stderr = run("playlist", "--url", PLAYLIST, "--cache-dir", cls.cache)
        assert code == 0, stderr
        code, cls.status, stderr = run("epg", "--url", XMLTV, "--cache-dir", cls.cache,
                                       "--force", "--now", str(NOW))
        assert code == 0, stderr
        cls.now = read(os.path.join(cls.cache, "epg-now.json"))
        cls.rows = playlist_rows(PLAYLIST)
        cls.logos = playlist_logos(PLAYLIST)
        cls.declared = guide_names(XMLTV)
        cls.guide_text = pathlib.Path(XMLTV).read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def assert_offered(self, guide_id):
        """The guide declares it AND gives it a programme, so a refusal below
        is the rule refusing and not the fixture withholding."""
        self.assertIn(guide_id, self.declared, guide_id)
        self.assertIn('channel="%s">' % guide_id, self.guide_text, guide_id)

    def test_a_guide_id_in_the_stream_address_reaches_its_row(self):
        """The strategy itself, at the sink the guide reads.

        For each row the fixture declares matched by address: the id is a
        token of that row's URL, the guide declares it, and the title that
        landed is the title the guide carries for it. The name is excluded as
        the cause in the same breath -- the guide's display-name does not fold
        to this row's own name -- so the address is the only strategy that
        could have produced the pair.
        """
        for tvg, entry in ADDR["matchedByAddress"].items():
            guide_id = entry["guideId"]
            self.assert_offered(guide_id)
            self.assertIn(guide_id, re.findall(r"[A-Za-z0-9]+", self.rows[tvg]), tvg)
            record = self.now["channels"].get(tvg)
            self.assertIsNotNone(record, tvg)
            self.assertEqual(record["now"]["title"], entry["nowTitle"], tvg)
            self.assertNotEqual(helper.epg_name_key(self.declared[guide_id]),
                                helper.epg_name_key(self.row_name(tvg)),
                                "%s could have matched by name" % tvg)

    def row_name(self, tvg):
        text = pathlib.Path(PLAYLIST).read_text(encoding="utf-8")
        found = re.search(r'^#EXTINF:[^\n]*tvg-id="%s"[^\n]*,(.*)$' % re.escape(tvg),
                          text, re.MULTILINE)
        self.assertIsNotNone(found, tvg)
        return found.group(1)

    def test_a_guide_id_that_is_not_hex_matches_too(self):
        """The strategy must be provider-general, not Pluto-shaped.

        `globalfashionchannel` is a real 20-character token of the installed
        list and nothing about it is hex. A 24-hex regex would have been the
        easy implementation and would have matched this provider only.
        """
        entry = ADDR["matchedByAddress"]["AddrSlug.us"]
        self.assertFalse(re.fullmatch(r"[0-9a-f]+", entry["guideId"]))
        self.assertEqual(self.now["channels"]["AddrSlug.us"]["now"]["title"],
                         entry["nowTitle"])

    def test_a_guide_id_in_the_artwork_is_not_a_stream_identity(self):
        """Artwork provenance is not stream identity.

        Indexing the logo URL as well reaches 8 more rows of the installed
        list and costs nothing in recall, because all 8 match by name anyway
        -- and 7 of the 8 stream from a DIFFERENT distributor than the
        artwork (Pluto artwork on Amagi, CloudFront and Google DAI
        addresses). Claiming a stream identity on the strength of a hotlinked
        picture is the F-EPG-9 failure, so the logo is not indexed.
        """
        entry = ADDR["refused"]["AddrLogo.us"]
        guide_id = entry["guideId"]
        self.assert_offered(guide_id)
        self.assertIn(guide_id, self.logos["AddrLogo.us"])
        self.assertNotIn(guide_id, self.rows["AddrLogo.us"])
        self.assertNotIn("AddrLogo.us", self.now["channels"])

    def test_a_guide_id_shorter_than_the_floor_claims_nothing(self):
        """The collision guard, and the whole of it.

        A guide declaring id="playlist" would otherwise claim a row for every
        address containing that word -- 583 of the 1,453 installed rows do.
        Measured over those addresses: every alphanumeric token shared by two
        or more of them that is not a 24-hex id is URL vocabulary, and the
        longest is eight characters.
        """
        entry = ADDR["refused"]["AddrShort.us"]
        guide_id = entry["guideId"]
        self.assert_offered(guide_id)
        self.assertLess(len(guide_id), helper.EPG_ADDR_MIN_TOKEN)
        self.assertIn(guide_id, self.rows["AddrShort.us"])
        self.assertNotIn("AddrShort.us", self.now["channels"])

    def test_an_address_two_rows_share_is_dropped_rather_than_guessed(self):
        """The name strategy's uniqueness discipline, kept for addresses.

        A token two rows stream says nothing about which of them the guide
        channel is, and a programme on the wrong channel is worse than a
        blank row. Both rows are refused and both are counted.
        """
        first, second = "AddrDupA.us", "AddrDupB.us"
        guide_id = ADDR["refused"][first]["guideId"]
        self.assert_offered(guide_id)
        self.assertEqual(self.rows[first], self.rows[second])
        self.assertIn(guide_id, self.rows[first])
        self.assertNotIn(first, self.now["channels"])
        self.assertNotIn(second, self.now["channels"])
        self.assertEqual(self.status["addrDroppedPlaylist"], 2)

    def test_the_address_match_is_case_sensitive(self):
        """A URL path is case-sensitive by the URL spec, so folding case
        would read an identity the address does not assert. It costs nothing:
        0 of the 193 real rows need the fold."""
        entry = ADDR["refused"]["AddrCase.us"]
        guide_id = entry["guideId"]
        self.assert_offered(guide_id)
        url = self.rows["AddrCase.us"]
        self.assertNotIn(guide_id, url)
        self.assertIn(guide_id, url.lower())
        self.assertNotIn("AddrCase.us", self.now["channels"])

    def test_one_address_naming_two_guide_channels_is_not_merged(self):
        """claim_channel's rule, reached through the new strategy.

        Equal ranks are first-come, so the declaration that streams a
        programme first takes the row; the second is contested and its
        programmes are dropped, never interleaved into the first's schedule.
        """
        entry = ADDR["matchedByAddress"]["AddrTwo.us"]
        self.assertEqual(self.now["channels"]["AddrTwo.us"]["now"]["title"],
                         entry["nowTitle"])
        self.assertNotIn("Two Second Now", json.dumps(self.now))

    def test_the_address_outranks_the_name_because_it_names_the_playout(self):
        """The ranking, set by the one real row where the two strategies
        compete.

        On the installed list the guide's `Heartland` is the provider's own
        playout of that brand. `Heartland.us@Web` streams exactly that
        playout and carries its id; `Heartland.us@Eastern` streams the
        broadcaster's own feed and matched the guide by NAME. The name says
        the brand, the address says the playout, and the schedule belongs to
        the playout. This fixture is that shape: the Eastern row's name is
        what the guide declares, and the Web row still wins.
        """
        won = ADDR["matchedByAddress"]["AddrRank.us@Web"]
        lost = "AddrRank.us@Eastern"
        guide_id = won["guideId"]
        # The name path really was offering the channel to the other row.
        self.assertEqual(helper.epg_name_key(self.declared[guide_id]),
                         helper.epg_name_key(self.row_name(lost)))
        self.assertNotIn(guide_id, self.rows[lost])
        self.assertEqual(self.now["channels"]["AddrRank.us@Web"]["now"]["title"],
                         won["nowTitle"])
        self.assertNotIn(lost, self.now["channels"])

    def test_the_address_outranks_the_feed_base(self):
        """ADDR before FEED, which the frozen data cannot rank.

        FEED matched 0 rows of the installed list, so nothing there decides
        this order and it is pinned here rather than left to a comment
        (CLAUDE.md rule 14). The argument it encodes: FEED compares a
        TRUNCATION of two ids and its own docstring records that it picks
        arbitrarily between @SD/@HD twins, while ADDR compares a whole id for
        equality.
        """
        won = ADDR["matchedByAddress"]["AddrFeed.us"]
        lost = "feedbasetoken1@SD"
        guide_id = won["guideId"]
        self.assertEqual(lost.split("@", 1)[0].lower(), guide_id,
                         "the loser's FEED base must be the contested id")
        self.assertIn(guide_id, self.rows["AddrFeed.us"])
        self.assertEqual(self.now["channels"]["AddrFeed.us"]["now"]["title"],
                         won["nowTitle"])
        self.assertNotIn(lost, self.now["channels"])

    def test_a_declared_tvg_id_outranks_an_address(self):
        """ID before ADDR: a join the playlist author DECLARED beats one the
        helper deduced.

        The weaker claim arrives first in the stream and starts later, so if
        it ever stopped being displaced it would become the row's "now" and
        not merely an extra record -- the same construction the M4-01 clash
        row uses.
        """
        key, entry = next(iter(ADDR["displacedRank"].items()))
        self.assertIn(key, self.declared, "the row's own tvg-id must be a guide id")
        self.assertIn(entry["loserGuideId"], self.rows[key])
        self.assertEqual(self.now["channels"][key]["now"]["title"], entry["nowTitle"])
        self.assertNotIn(entry["loserTitle"], json.dumps(self.now))

    def test_a_declared_tvg_id_is_consulted_before_an_address(self):
        """The ORDER of the two id maps, which the RANKS cannot pin.

        `test_a_declared_tvg_id_outranks_an_address` above proves the rank:
        an address claim is displaced by an id claim on the same row. It does
        NOT prove the order the maps are consulted in, because there the two
        strategies resolved two DIFFERENT guide channels onto one row. This
        case is the other shape: ONE guide id that the exact map and the
        address map resolve to two different rows. Swapping the two lookups
        survives every other case in this module and fails here.

        UNVERIFIED on the frozen data: 0 of its 1,453 rows carry a tvg-id the
        guide declares, so nothing measured ranks these two and the fixture
        says `verified: false` on the entry (CLAUDE.md rule 14).
        """
        order = ADDR["lookupOrder"]
        self.assertFalse(order["verified"])
        guide_id = order["guideId"]
        self.assert_offered(guide_id)
        # Available to BOTH maps, to two different rows.
        self.assertEqual(order["declaredBy"], guide_id)
        self.assertIn(guide_id, self.rows[order["streamedBy"]])
        self.assertNotEqual(order["declaredBy"], order["streamedBy"])
        # And the declaring row is the one that gets it.
        self.assertEqual(self.now["channels"][order["declaredBy"]]["now"]["title"],
                         order["nowTitle"])
        self.assertNotIn(order["streamedBy"], self.now["channels"])

    def test_nothing_the_strategy_refused_reaches_the_guide_at_all(self):
        """One assertion over every refused title, so a refusal cannot be
        satisfied by the programme landing on some OTHER row."""
        rendered = json.dumps(self.now)
        for title in ADDR["neverRendered"]:
            self.assertNotIn(title, rendered, title)
        for tvg in list(ADDR["refused"]) + list(ADDR["displacedByAddress"]):
            self.assertNotIn(tvg, self.now["channels"], tvg)


class AddressIndexTest(unittest.TestCase):
    """build_alias and match_xmltv_channel called directly for F-EPG-11."""

    def index(self, channels):
        return helper.build_alias({"channels": channels})

    def test_the_index_answers_with_the_rank_and_counts_what_it_held(self):
        index, total = self.index([
            {"tvgId": "A.us", "name": "Alpha",
             "url": "http://h.example.test/plu-aaaaaaaaaaaaaaaaaaaa0001.m3u8"},
            {"tvgId": "B.us", "name": "Beta", "url": "http://h.example.test/short.m3u8"},
        ])
        self.assertEqual(total, 2)
        self.assertEqual(index["addrIndexed"], 1)
        self.assertEqual(index["addrDroppedPlaylist"], 0)
        self.assertEqual(index["addr"], {"aaaaaaaaaaaaaaaaaaaa0001": "A.us"})
        self.assertEqual(
            helper.match_xmltv_channel(index, "aaaaaaaaaaaaaaaaaaaa0001", {}),
            ("A.us", helper.EPG_MATCH_ADDR))

    def test_a_row_naming_one_token_twice_is_one_claim(self):
        """addrDroppedPlaylist counts ROWS, as nameDroppedPlaylist does, so a
        token repeated inside ONE address must not look like two rows
        claiming it."""
        token = "aaaaaaaaaaaaaaaaaaaa0001"
        index, _ = self.index([
            {"tvgId": "A.us", "name": "Alpha",
             "url": "http://h.example.test/%s/%s.m3u8" % (token, token)},
        ])
        self.assertEqual(index["addr"], {token: "A.us"})
        self.assertEqual(index["addrDroppedPlaylist"], 0)

    def test_a_row_without_a_url_is_in_no_address_map(self):
        index, _ = self.index([{"tvgId": "A.us", "name": "Alpha"}])
        self.assertEqual(index["addr"], {})
        self.assertEqual(index["addrIndexed"], 0)

    def test_the_strategies_stay_in_their_declared_order(self):
        """The ranks are an ORDER and claim_channel compares them with `<`, so
        they must be the distinct ascending run that EPG_MATCH_KEYS names."""
        ranks = (helper.EPG_MATCH_ID, helper.EPG_MATCH_ADDR,
                 helper.EPG_MATCH_FEED, helper.EPG_MATCH_NAME)
        self.assertEqual(ranks, tuple(range(len(helper.EPG_MATCH_KEYS))))

    def test_building_the_address_map_over_ten_thousand_rows_is_cheap(self):
        """Rule 7's budget, for the work this strategy added to build_alias.

        The helper parses 10,000 channels in under a second, and the address
        index is new per-row work in build_alias. Measured on this machine
        over exactly the rows below, best of five: 47.6 ms before this
        strategy and 70.3 ms after, so it costs about 23 ms per 10,000 rows
        on a path that is not the budgeted one -- `parse_m3u` over the same
        10,000 channels reads 511.9 ms before and 507.3 ms after, unchanged.
        The ceiling here is five times the measurement on purpose: it is a
        tripwire for an accidental quadratic, not a stopwatch.
        """
        import time
        channels = [
            {"tvgId": "ch%d.us" % i, "name": "Channel %d" % i,
             "url": "https://jmp.example.test/plu-%024x.m3u8" % i,
             "logo": "https://img.example.test/channels/%024x/colorLogoPNG.png" % i}
            for i in range(10000)
        ]
        best = None
        for _ in range(3):
            started = time.monotonic()
            index, total = helper.build_alias({"channels": channels})
            elapsed = (time.monotonic() - started) * 1000
            best = elapsed if best is None else min(best, elapsed)
        self.assertEqual(total, 10000)
        self.assertEqual(index["addrIndexed"], 10000)
        self.assertLess(best, 400.0, "build_alias took %d ms for 10,000 rows" % best)


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
        """The competing element has to be one that could actually win.

        This case used to pit `onscreen` against `original-air-date`, and
        after the narrowing that system is ignored outright, so no mutation
        of the preference could redden it: the test named a decision nothing
        observed. `xmltv_ns` is the only other system episode_text accepts,
        so it is the only one that can compete, and it is placed FIRST --
        a first-wins implementation returns "S1 E2" here.
        """
        e = self._prog(("xmltv_ns", "0.1.0/1"), ("onscreen", "S08E10"))
        self.assertEqual(helper.episode_text(e), "S08E10")
        # And the date still loses to it from either side.
        self.assertEqual(helper.episode_text(
            self._prog(("original-air-date", "19920406000000 +0000"),
                       ("onscreen", "S08E10"))), "S08E10")

    def test_a_bare_episode_num_is_taken_as_onscreen(self):
        self.assertEqual(helper.episode_text(self._prog((None, "S2 E5"))), "S2 E5")

    def test_the_machine_form_is_still_translated_when_it_is_all_there_is(self):
        e = self._prog(("original-air-date", "20080101000000 +0000"), ("xmltv_ns", "0.1.0/1"))
        self.assertEqual(helper.episode_text(e), "S1 E2")


class GuideOrderTest(unittest.TestCase):
    """The guide-side uniqueness rule, against a guide that is not DTD-ordered.

    tests/fixtures/epg-match.xml declares every <channel> before the first
    <programme>, the order the XMLTV DTD gives, so `pluto-a` and `pluto-b`
    are both known ambiguous before any programme is read and
    test_an_ambiguous_name_is_never_guessed only ever exercised the easy half
    of the rule. A guide that emits each channel beside its own programmes
    has already banked the first declaration's claim when the second arrives:
    blanking the lookup is then not enough, and the shipped helper reported
    `nameDroppedGuide: 2` -- both dropped -- while writing one of the two
    schedules onto the row. Which one depended on the order the guide
    streamed, which is the failure docs/PLAN-M4.md calls worse than a blank.
    """

    PLAYLIST = ("#EXTM3U\n"
                "#EXTINF:-1 tvg-id=\"T1\",Alpha\nhttp://stream.example.test/a.m3u8\n")

    def guide(self, interleaved):
        decl = "<channel id=\"%s\"><display-name>Alpha</display-name></channel>"
        prog = ("<programme start=\"20260912203000 +0000\" stop=\"20260912213000 +0000\" "
                "channel=\"%s\"><title>FROM-%s</title></programme>")
        parts = ["<?xml version=\"1.0\" encoding=\"UTF-8\"?><tv>"]
        if interleaved:
            for cid in ("g1", "g2"):
                parts.append(decl % cid)
                parts.append(prog % (cid, cid.upper()))
        else:
            parts.extend(decl % cid for cid in ("g1", "g2"))
            parts.extend(prog % (cid, cid.upper()) for cid in ("g1", "g2"))
        parts.append("</tv>")
        return "".join(parts)

    def epg(self, interleaved):
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, "list.m3u").write_text(self.PLAYLIST, encoding="utf-8")
            pathlib.Path(tmp, "guide.xml").write_text(self.guide(interleaved), encoding="utf-8")
            code, _, stderr = run("playlist", "--url", os.path.join(tmp, "list.m3u"),
                                  "--cache-dir", tmp)
            self.assertEqual(code, 0, stderr)
            code, status, stderr = run("epg", "--url", os.path.join(tmp, "guide.xml"),
                                       "--cache-dir", tmp, "--now", str(NOW))
            self.assertEqual(code, 0, stderr)
            return status, read(os.path.join(tmp, "epg-now.json"))["channels"]

    def test_a_dtd_ordered_guide_drops_both_declarations(self):
        status, channels = self.epg(interleaved=False)
        self.assertEqual((status["nameDroppedGuide"], status["matched"]), (2, 0))
        self.assertEqual(channels, {})

    def test_an_interleaved_guide_drops_both_declarations_too(self):
        """The same guide, the same content, one reordering: the answer must
        not move. The count and the row have to agree -- a status saying both
        declarations were dropped while one of them is on the row is worse
        than either failure alone, because the count is what the acceptance
        reads."""
        status, channels = self.epg(interleaved=True)
        self.assertEqual(status["nameDroppedGuide"], 2)
        self.assertEqual(channels, {}, "a dropped declaration may not keep the row")
        self.assertEqual(status["matched"], 0)
        self.assertEqual(status["epgChannels"], 0)

    def test_both_orderings_give_the_same_answer(self):
        first, rows_a = self.epg(interleaved=False)
        second, rows_b = self.epg(interleaved=True)
        self.assertEqual(rows_a, rows_b)
        for key in ("matched", "matchedByName", "nameDroppedGuide", "epgChannels",
                    "programmeCount", "nowCount"):
            self.assertEqual(first[key], second[key], key)


class LaunchStderrSinkTest(unittest.TestCase):
    """D-SINK-12: redaction is not distributive over a split.

    `drain_launch_stderr` redacted each 4096-byte `os.read` on its own, so a
    URL that straddled a read boundary was redacted in halves and the
    survivors reached `launch_reason`, which is the text of a desktop
    notification. The same defect class as the clean_detail blocker this
    round opened with, at a different sink.

    The sweep is the test: one offset proves nothing, because the leak only
    happens when the boundary lands inside the URL. Repairing it naively --
    carrying the partial line but FLUSHING one longer than the budget -- still
    leaked at 33 of 48 offsets, because the flush is itself a cut; an
    over-long newline-free line is dropped instead.
    """

    URL = "http://u5er:5ecretpw@host.example/live/x.m3u8?t=abc"
    FORBIDDEN = ("5ecretpw", "u5er", "x.m3u8", "t=abc", "/live")

    def _drain(self, payload):
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, payload.encode("utf-8"))
            os.set_blocking(read_fd, False)
            buffer = []
            for _ in range(4):
                helper.drain_launch_stderr(read_fd, buffer)
            return "".join(buffer)
        finally:
            os.close(read_fd)
            os.close(write_fd)

    def test_no_boundary_offset_lets_any_part_of_a_url_through(self):
        leaked = []
        for pad in range(64):
            head = "mpv: failed to open " + "a" * pad
            filler = "b" * max(0, 4096 - len(head) - pad)
            text = self._drain(filler + head + self.URL + "\n")
            if any(bad in text for bad in self.FORBIDDEN):
                leaked.append(pad)
        self.assertEqual([], leaked,
                         "a URL survived the read boundary at these offsets")

    def test_an_ordinary_line_is_still_reduced_to_scheme_and_host(self):
        text = self._drain("mpv: cannot open " + self.URL + "\n")
        self.assertIn("http://host.example", text)
        for bad in self.FORBIDDEN:
            self.assertNotIn(bad, text)

    def test_the_last_line_still_reaches_the_notification(self):
        self._drain("")
        read_fd, write_fd = os.pipe()
        try:
            os.write(write_fd, b"first\nsecond\nthird\n")
            os.set_blocking(read_fd, False)
            buffer = []
            helper.drain_launch_stderr(read_fd, buffer)
            self.assertEqual(helper.launch_reason(buffer), "third")
        finally:
            os.close(read_fd)
            os.close(write_fd)

    def test_a_line_longer_than_the_budget_is_dropped_rather_than_cut(self):
        text = self._drain("c" * (helper.LAUNCH_STDERR_MAX + 200) + self.URL)
        for bad in self.FORBIDDEN:
            self.assertNotIn(bad, text)


class NameNoiseTest(unittest.TestCase):
    """The matcher's name key, which is NOT the search key (D-EPG-2).

    Found by running the integrated milestone against the REAL guide rather
    than against this file's fixtures: matching on normalize_text alone
    reaches 126 of the installed 1,453 channels and taking the distribution
    markers out first reaches 227, because 1,155 of those names carry one.
    (125 and 224 were the first write-up's numbers and are wrong; re-measured
    through build_alias -> parse_xmltv -> match_counts on the frozen inputs,
    2026-10-03.) The fixtures could not see it because synthetic names never
    say "(1080p)" -- which is the hazard engineering rule 10 names, a double
    more forgiving than the real thing.

    These call the shipping function rather than re-stating its pattern. What
    they CANNOT see is whether the matcher calls it: that is the fixture's
    job, in test_the_matcher_joins_on_the_name_key_and_not_the_search_key.
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
            for key in helper.EPG_MATCH_KEYS + (
                    "nameIndexed", "nameDroppedPlaylist", "nameDroppedGuide",
                    "addrIndexed", "addrDroppedPlaylist"):
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

    def test_no_cut_offset_of_any_cap_can_publish_a_credential(self):
        """The whole offset space, at every cap the helper ships, because the
        leak was a property of ONE offset and a fixture picks one offset.

        The vectors live in tests/fixtures/epg-match.json so the JS mirror of
        this sink (Model.epgDetailText) can run the same ones. Both forms are
        swept: the URL preceded by a space, where the fix drops the truncated
        token, and the URL inside one enormous token, where there is nothing
        to keep. The length assertion is in the loop on purpose -- redaction
        can GROW the text ("[redacted]"), and "never longer than the cap" is
        the other half of what this function promises.
        """
        sink = EXPECTED["sink"]
        url, forbidden = sink["url"], sink["forbidden"]
        caps = (helper.EPG_MAX_DESC, helper.EPG_MAX_CATEGORY, helper.EPG_MAX_EPISODE)
        self.assertIn("@", url, "the vector has to carry userinfo to be a vector")
        for cap in caps:
            for pad in range(cap + 60):
                for text in ("a" * pad + " " + url + " tail words here",
                             "a" * pad + url + "tail"):
                    out = helper.clean_detail(text, cap)
                    self.assertLessEqual(len(out), cap, (cap, pad))
                    for bad in forbidden:
                        if bad == "host.example":
                            continue        # the host is what redaction KEEPS
                        self.assertNotIn(bad, out, (cap, pad, out))

    def test_a_url_that_fits_keeps_its_scheme_and_host(self):
        """The other direction, so the sweep above cannot be passed by a
        function that simply deletes every URL: a URL the cut never touches
        is reduced to scheme://host and keeps both."""
        sink = EXPECTED["sink"]
        out = helper.clean_detail("see " + sink["url"] + " now", helper.EPG_MAX_DESC)
        self.assertEqual(out, "see http://host.example now")


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


PRECISION_PLAYLIST = str(FIXTURES / "epg-precision.m3u")
PRECISION_XMLTV = str(FIXTURES / "epg-precision.xml")
PRECISION = json.loads((FIXTURES / "epg-precision.json").read_text(encoding="utf-8"))

_PLUTO_ID = re.compile(r"[0-9a-f]{24}")


class EpgPrecisionTest(unittest.TestCase):
    """M4-01's OTHER half: are the pairs the matcher accepts the right pairs?

    docs/PLAN-M4.md M4-01 repair 2 says "Precision is the acceptance
    criterion, not recall: a wrong programme on a channel is worse than a
    blank row." The M4 round moved `matched` from 0 to 227 on the frozen real
    inputs and graded nothing about the 227. docs/QA-EPG-PRECISION.md is the
    audit; this class is the part of it a gate can run.

    THE ORACLE THIS CLASS WAS BUILT ON COLLAPSED ON 2026-10-04 (F-EPG-11).

    It used to read: the installed iptv-org list streams its Pluto channels
    from an address carrying Pluto's own channel id, the guide declares that
    same id, and THE MATCHER READS NEITHER -- it joins on the display name --
    so "the programme on this row is the programme of the channel this row's
    URL names" was two independent identifiers agreeing.

    F-EPG-11 makes the matcher read that identifier, because the audit that
    used it as an oracle also measured that it reached 193 rows the matcher
    was leaving on the table. Eight of this fixture's nine pairs are now
    matched BY the oracle, so for those eight the agreement proves only that
    the lookup is wired up. That is not a reason to delete the assertions --
    a wiring check is worth keeping -- but it IS a reason to stop calling
    them precision evidence, and `test_the_oracle_is_now_also_the_matcher`
    asserts the collapse so that nobody has to remember it.

    What still grades precision here is one pair, `News12LongIsland.us@SD`,
    matched by NAME and judged by reading. A grader that does not depend on
    the stream URL is owed to this fixture, and until there is one the
    precision question is OPEN rather than answered.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cache = cls.tmp.name
        code, _, stderr = run("playlist", "--url", PRECISION_PLAYLIST, "--cache-dir", cls.cache)
        assert code == 0, stderr
        code, cls.status, stderr = run("epg", "--url", PRECISION_XMLTV,
                                       "--cache-dir", cls.cache, "--force",
                                       "--now", str(PRECISION["now"]))
        assert code == 0, stderr
        cls.now = read(os.path.join(cls.cache, "epg-now.json"))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_oracle_is_now_also_the_matcher(self):
        """F-EPG-11: the collapse, asserted rather than remembered.

        Every oracle entry's plutoId is now a key of build_alias's address
        map pointing at that entry's own tvgId -- which is exactly what
        match_xmltv_channel looks a guide channel up by. So the grader and
        the thing being graded are the same identifier, and the five pairs
        below are matched BY their own oracle.

        This test is the tripwire on the DOCUMENTATION claim: if the two ever
        become independent again -- the strategy removed, the floor raised
        past 24, the stream URL no longer indexed -- this goes red and the
        fixture's comment stops being a lie. It calls build_alias for real
        rather than grepping the helper for a constant (CLAUDE.md rule 14).
        """
        self.assertTrue(PRECISION["oracleIsNowTheMatcher"]["matchedByAddrRank"])
        channels = read(os.path.join(self.cache, "channels.json"))
        index, _ = helper.build_alias(channels)
        for entry in PRECISION["oracle"]:
            self.assertEqual(index["addr"].get(entry["plutoId"]), entry["tvgId"],
                             entry["tvgId"])
            self.assertEqual(
                helper.match_xmltv_channel(index, entry["plutoId"], {}),
                (entry["tvgId"], helper.EPG_MATCH_ADDR), entry["tvgId"])
        # And the one pair that is still judged by something the matcher did
        # not read is matched by the NAME strategy, not by the address.
        for entry in PRECISION["returnedByRepair"]:
            self.assertNotIn(entry["tvgId"], index["addr"].values(), entry["tvgId"])
        self.assertEqual(self.status["matchedByName"],
                         len(PRECISION["returnedByRepair"]))

    def test_the_oracle_is_in_the_fixture(self):
        """The fixture's own invariant, so a doctored fixture cannot pass.

        Every oracle row's stream URL must carry the Pluto id that the guide
        uses as that channel's id, the guide must declare it under the name
        the fixture names, and every expected title must be unique so that a
        title identifies one guide channel. Read from the two fixture files
        directly, never from the helper's output.
        """
        playlist = pathlib.Path(PRECISION_PLAYLIST).read_text(encoding="utf-8")
        guide = pathlib.Path(PRECISION_XMLTV).read_text(encoding="utf-8")
        rows = {}
        pending = None
        for line in playlist.splitlines():
            if line.startswith("#EXTINF:"):
                match = re.search(r'tvg-id="([^"]*)"', line)
                pending = match.group(1) if match else None
            elif pending is not None and line and not line.startswith("#"):
                rows[pending] = line
                pending = None
        declared = dict(re.findall(
            r'<channel id="([^"]+)">\s*<display-name>([^<]*)</display-name>', guide))
        self.assertEqual(len(declared), guide.count("<channel id="))
        titles = []
        for entry in PRECISION["oracle"]:
            url = rows[entry["tvgId"]]
            found = _PLUTO_ID.search(url)
            self.assertIsNotNone(found, entry["tvgId"])
            self.assertEqual(found.group(0), entry["plutoId"], entry["tvgId"])
            self.assertEqual(declared.get(entry["plutoId"]), entry["guideName"],
                             entry["tvgId"])
            self.assertNotIn(entry["plutoId"], helper.epg_name_key(entry["playlistName"]))
            titles.append(entry["nowTitle"])
        self.assertEqual(len(set(titles)), len(titles))

    def test_each_match_lands_the_programme_of_the_channel_its_url_names(self):
        """CIRCULAR SINCE F-EPG-11: a wiring check, no longer evidence.

        For every oracle pair, the title in epg-now.json is the title the
        guide carries for the channel whose id that row's URL names. That
        used to mean the NAME join had married two channels an identifier the
        matcher never saw says are the same one. The matcher now joins on
        that identifier, so the equality is a tautology and what it still
        buys is end-to-end wiring: index -> match -> claim -> window ->
        epg-now.json.
        """
        for entry in PRECISION["oracle"]:
            record = self.now["channels"].get(entry["tvgId"])
            self.assertIsNotNone(record, entry["tvgId"])
            self.assertEqual(record["now"]["title"], entry["nowTitle"], entry["tvgId"])

    def test_nothing_matched_beyond_the_oracle(self):
        """The matched SET, not just its size: a wrong pair is an extra key.

        Before D-EPG-5 was repaired this set also had to carry the wrong
        Bloomberg pair, and the repair's whole shape is visible here: that
        key leaves and `News12LongIsland` arrives, because the fold that
        married two channels was the same one that denied two rows a guide
        offering one of them. The size did not move; the membership did.
        """
        expected = {entry["tvgId"] for entry in PRECISION["oracle"]}
        # The rows the D-EPG-5 repair returned are right by reading rather
        # than by an identifier, so the fixture keeps them in their own block:
        # a pair the oracle CANNOT confirm must not be able to hide among the
        # ones it can.
        expected |= {entry["tvgId"] for entry in PRECISION["returnedByRepair"]}
        # And the three F-EPG-11 settled rows, in a block of their own for
        # the same reason: they are right because the address names them, and
        # the findings they close stay readable on the row that closed them.
        expected |= {entry["tvgId"] for entry in PRECISION["settledByAddress"]}
        self.assertEqual(set(self.now["channels"]), expected)
        for entry in PRECISION["unmatched"]:
            self.assertNotIn(entry["tvgId"], self.now["channels"],
                             "%s (%s)" % (entry["tvgId"], entry["finding"]))

    def test_the_counts_the_fixture_declares(self):
        for key, value in PRECISION["status"].items():
            self.assertEqual(self.status[key], value, key)
        self.assertEqual(self.status["warnings"], PRECISION["warnings"])

    def test_the_plus_that_separates_two_channels_is_kept(self):
        """D-EPG-5, REPAIRED 2026-10-03, asserted as the repair behaves.

        This is the one wrong pair the audit of the real 227 found. The
        matcher's key folds `+` to a space, so iptv-org's Bloomberg Television
        and the guide's "Bloomberg TV+" become one name and the guide's
        schedule lands on the other channel's row. The project already owns
        the rule that separates them -- normalize_id_text keeps `+` and `*`
        "because they are the difference between two channels rather than
        noise inside one" -- and the matcher does not use it.

        WHEN D-EPG-5 IS REPAIRED THIS TEST GOES RED, and that is its job: the
        repair must come here, flip the assertions, move the fixture's
        `crossChannel` block into `unmatched` and re-level status.matched from
        6 to 5. docs/QA-EPG-PRECISION.md measures the cost of the repair on
        the real inputs at one pair, and that pair is this one.
        """
        cross = PRECISION["crossChannel"]
        self.assertNotIn(cross["tvgId"], self.now["channels"],
                         "the wrong pair formed again: D-EPG-5 has regressed")
        first, second = PRECISION["plusPair"]["playlistNames"]
        # The repair IS this inequality: the two names are one under the
        # search fold and two under the id fold, and the matcher now uses
        # the second. Asserting both folds keeps the reason in the test.
        self.assertEqual(helper.normalize_text(helper._EPG_NAME_NOISE.sub(" ", first)),
                         helper.normalize_text(helper._EPG_NAME_NOISE.sub(" ", second)))
        self.assertNotEqual(helper.epg_name_key(first), helper.epg_name_key(second))

    def test_the_repair_returns_the_rows_the_fold_was_denying(self):
        """D-EPG-5's recall half: what the defect cost, now returned.

        News12 and News12+ Long Island are two channels. The fold makes their
        names one, the uniqueness rule then drops BOTH rather than guess, and
        the guide's "News12 Long Island" declaration reaches neither. On the
        installed list this is four News 12 regions plus Tennis Channel 2 /
        Tennis Channel +2: ten channels of nameDroppedPlaylist, every one of
        them a `+`.
        """
        # Nothing is dropped for ambiguity any more on this fixture, and the
        # row the collision used to deny now carries its guide's programme.
        self.assertEqual(self.status["nameDroppedPlaylist"], 0)
        self.assertEqual(self.status["nameDroppedGuide"], 0)
        self.assertIn("News12LongIsland.us@SD", self.now["channels"])

    def settled(self, finding):
        return [entry for entry in PRECISION["settledByAddress"]
                if entry["finding"] == finding]

    def test_a_country_qualifier_still_defeats_the_name_key(self):
        """F-EPG-7, both halves, after F-EPG-11.

        The key still keeps "(United States)" and still cannot join these two
        rows to their guide channels: that is asserted here on the two raw
        names, through the shipping key. 87 of the 1,453 installed names carry
        the qualifier and 30 of those carry a Pluto id this guide declares.

        What changed is the PRICE. The address reaches all 30 of those rows,
        so the loosening F-EPG-7 proposed -- strip any parenthetical -- is
        worth 29 rows and one CONTRADICTED pair before F-EPG-11 and 1 row and
        zero contradicted pairs after it, measured end to end on the frozen
        inputs. The contradiction it used to create was
        `Pluto TV Reality (United States)`, whose address names the guide's
        `Pluto TV Pride`; the address now holds that row at a stronger rank,
        so the name claim is refused instead of winning.
        """
        guide = pathlib.Path(PRECISION_XMLTV).read_text(encoding="utf-8")
        entries = self.settled("F-EPG-7")
        self.assertTrue(entries)
        for entry in entries:
            self.assertIn('<channel id="%s"' % entry["guideId"], guide)
            playlist_name = self.row_name(entry["tvgId"])
            guide_name = re.search(
                r'<channel id="%s">\s*<display-name>([^<]*)</display-name>'
                % entry["guideId"], guide).group(1)
            # The name path is still defeated: these are two different keys.
            self.assertIn("(United States)", playlist_name)
            self.assertNotEqual(helper.epg_name_key(playlist_name),
                                helper.epg_name_key(guide_name))
            # And the row is matched anyway, by the address, at its own rank.
            self.assertEqual(self.now["channels"][entry["tvgId"]]["now"]["title"],
                             entry["nowTitle"])
            self.assertIn(entry["guideId"], self.row_url(entry["tvgId"]))

    def test_a_missing_space_is_not_a_distribution_marker(self):
        """F-EPG-8 SETTLED by F-EPG-11, with the reason it was open intact.

        The guide writes "TennisChannel 2" where the playlist writes
        "Tennis Channel +2 (720p)". No rule in the matcher closes a missing
        space -- not the shipping key, not the normalize_id_text repair of
        D-EPG-5 -- and both of those are still asserted, because the finding
        was that NO KEY CAN JOIN THEM and that remains true. The address
        joins them without reading either name.
        """
        entry, = self.settled("F-EPG-8")
        self.assertNotEqual(helper.epg_name_key("Tennis Channel +2 (720p)"),
                            helper.epg_name_key("TennisChannel 2"))
        self.assertNotEqual(
            helper.normalize_id_text(helper._EPG_NAME_NOISE.sub(" ", "Tennis Channel +2 (720p)")),
            helper.normalize_id_text(helper._EPG_NAME_NOISE.sub(" ", "TennisChannel 2")))
        self.assertIn(entry["guideId"], self.row_url(entry["tvgId"]))
        self.assertEqual(self.now["channels"][entry["tvgId"]]["now"]["title"],
                         entry["nowTitle"])

    def row_name(self, tvg):
        text = pathlib.Path(PRECISION_PLAYLIST).read_text(encoding="utf-8")
        found = re.search(r'^#EXTINF:[^\n]*tvg-id="%s"[^\n]*,(.*)$' % re.escape(tvg),
                          text, re.MULTILINE)
        self.assertIsNotNone(found, tvg)
        return found.group(1)

    def row_url(self, tvg):
        return playlist_rows(PRECISION_PLAYLIST)[tvg]


if __name__ == "__main__":
    unittest.main()
