"""The guide parse's bounds, round 2 of the bounds sweep (lane-bounds-h).

What each class holds, and what it was seen red against (rule 11):

* GuideChannelCapTest -- D-EPG-10, ruling R30d. Without a playlist index the
  parse kept every guide channel under its own id, so the channels it held
  and the entries it wrote into epg-now.json were bounded only by the input.
  It now admits at most MAX_CHANNELS distinct guide channels and no id longer
  than EPG_MAX_GUIDE_ID, counting what it refuses. Pinned with both caps
  LOWERED and small ordinary guides; red on lane-bounds-int (17a2407).
* EpgCountedSentenceTest -- the D-M3U-4 sibling in parse_xmltv: every counted
  sentence reads right for one and for many. Red on lane-bounds-int.
* QualifierEquivalenceTest and DisplayNameKeyTest -- D-EPG-8, R30g. The
  trailing-qualifier strip is no longer a regex (it was quadratic in a
  whitespace run); its answer is held EQUAL to the old pattern, run here as
  an oracle, on ordinary names; and a display-name is folded and cut before
  either key is made, pinned with the cap lowered (red on lane-bounds-int).
* Ipv6LiteralEquivalenceTest -- R30g's rule 15 over every helper regex: the
  one other super-linear pattern on user text, rewritten, held equal to the
  old pattern.
* EncodeLinearityTest, EncodeDifferentialTest, DuplicateKeyStopTest -- D-EPG-9,
  R30h: the stop derivation is one backward pass after the sort, each start
  read twice whatever the input (counted, never timed), the output equal to
  lane-bounds-int's on ordinary inputs, and the STOP half of the duplicate key
  pinned (the round-1 recheck of lane-bounds-l mutated it away and all 145
  EPG tests stayed green).
* LinearSiblingsTest -- rule 15 over D-EPG-9's shape: three more membership
  scans per item on provider text, each now one pass, held to
  lane-bounds-int's answer.
* TimeMemoAsciiTest -- that recheck's P3 (d): the memo keeps ASCII keys only,
  so its stated bound is true.

Round 3 (lane-bounds-h2, ruling R32d, D-EPG-12):

* NoiseEquivalenceTest -- _EPG_NAME_NOISE's `[not 24/7]` alternative had two
  unbounded `\\s*` runs with only an optional atom between them (quadratic in
  a whitespace run; the round-2 guard had graded it linear for a false
  reason). Rewritten with the second run behind the separator; held EQUAL to
  the old pattern, run as the oracle, on generated spellings of the marker
  and on ordinary names. Green on the base by construction (the oracle IS
  the base's pattern), so it was seen red on mutations of the new one.
* OneFoldTest -- the recheck's P3 (c): the guide side folded a display-name
  (DEL and C0 controls to a space) before keying and the playlist side keyed
  the raw name, so the same name with a DEL on both sides did not match.
  One fold, epg_name_text, inside the key functions. Red on the base.
* GuideIdCapBoundaryTest -- the recheck's P3 (b): exactly EPG_MAX_GUIDE_ID
  accepted and one more refused; exactly MAX_CHANNELS admitted with nothing
  refused and the next refused. Red on the off-by-one mutations.

Nothing here is large, and nothing is timed: under the sweep's input rule a
bound is shown by arithmetic, by one ordinary record, by lowered caps and by
equivalence, never by an input built to cost.
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import pathlib
import random
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper
from test_epg_retention import baseline_wording, comparable, playlist_doc, random_guide

helper = load_helper()

ROOT = pathlib.Path(__file__).resolve().parent.parent
# The integration branch this round started from: lane-bounds-l's forward
# pointer and lane-bounds-p's reply caps, before this lane.
INT_BASE = "17a2407"
NOW = 1792000000


def load_ref(case, ref):
    """The helper at `ref`, extracted from git into a temp directory and
    loaded with bytecode writing off. Skips when the commit is absent."""
    if shutil.which("git") is None:
        case.skipTest("git is needed to read the baseline helper")
    probe = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", ref + "^{commit}"],
                           capture_output=True, timeout=30)
    if probe.returncode != 0:
        case.skipTest("the baseline commit %s is not in this checkout" % ref)
    work = tempfile.mkdtemp()
    case.addCleanup(shutil.rmtree, work, True)
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", ref, "bin"],
                             capture_output=True, timeout=60)
    case.assertEqual(archive.returncode, 0, archive.stderr)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(work, filter="data")
    stub = os.path.join(work, "bin", "omarchy-iptv")
    name = "omarchy_iptv_ref_" + ref
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        loader = importlib.machinery.SourceFileLoader(name, stub)
        spec = importlib.util.spec_from_loader(name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


def xmltv_time(epoch):
    return time.strftime("%Y%m%d%H%M%S +0000", time.gmtime(epoch))


def guide(channels, per_channel=2, extra=""):
    """An ordinary small guide: `channels` ids in document order, each with
    `per_channel` in-window programmes."""
    out = ["<tv>"]
    for cid in channels:
        out.append('<channel id="%s"><display-name>%s</display-name></channel>' % (cid, cid))
    for cid in channels:
        for p in range(per_channel):
            start = NOW - 1800 + p * 1800
            out.append('<programme start="%s" stop="%s" channel="%s"><title>Show %d</title></programme>'
                       % (xmltv_time(start), xmltv_time(start + 1800), cid, p))
    out.append(extra)
    out.append("</tv>")
    return "".join(out).encode("utf-8")


def parse(data, index=None):
    return helper.parse_xmltv(helper.open_xml_stream(data), NOW, index)


class GuideChannelCapTest(unittest.TestCase):
    """D-EPG-10, R30d: without a playlist index, at most MAX_CHANNELS guide
    channels, the rest counted in one sentence."""

    IDS = ["a.tv", "b.tv", "c.tv", "d.tv", "e.tv"]

    def test_without_an_index_the_first_channels_are_kept_and_the_rest_counted(self):
        with mock.patch.object(helper, "MAX_CHANNELS", 3):
            result = parse(guide(self.IDS))
        self.assertEqual(list(result["channels"]), ["a.tv", "b.tv", "c.tv"])
        self.assertEqual(sorted(result["seenIds"]), ["a.tv", "b.tv", "c.tv"])
        self.assertEqual(result["epgChannels"], 3)
        self.assertEqual(result["programmeCount"], 6)
        self.assertEqual(result["warnings"], [
            "4 programmes dropped: the guide lists more than 3 channels"
            " and no playlist was loaded to choose among them"])

    def test_one_refused_programme_reads_as_one(self):
        data = guide(self.IDS[:3]).replace(b"</tv>", b"") + (
            '<programme start="%s" channel="d.tv"><title>Late</title></programme></tv>'
            % xmltv_time(NOW)).encode()
        with mock.patch.object(helper, "MAX_CHANNELS", 3):
            result = parse(data)
        self.assertEqual(result["warnings"], [
            "1 programme dropped: the guide lists more than 3 channels"
            " and no playlist was loaded to choose among them"])

    def test_a_channel_already_admitted_keeps_its_later_programmes(self):
        """The cap counts CHANNELS: a fourth programme for an admitted
        channel, after the cap is reached, is kept."""
        data = guide(self.IDS[:4], per_channel=1).replace(b"</tv>", b"") + (
            '<programme start="%s" stop="%s" channel="a.tv"><title>Again</title></programme></tv>'
            % (xmltv_time(NOW + 1800), xmltv_time(NOW + 3600))).encode()
        with mock.patch.object(helper, "MAX_CHANNELS", 3):
            result = parse(data)
        self.assertEqual(list(result["channels"]), ["a.tv", "b.tv", "c.tv"])
        self.assertEqual(result["programmeCount"], 4)
        self.assertEqual(len(result["warnings"]), 1)
        self.assertTrue(result["warnings"][0].startswith("1 programme dropped"), result["warnings"])

    def test_an_id_no_playlist_could_carry_is_not_admitted(self):
        with mock.patch.object(helper, "EPG_MAX_GUIDE_ID", 4):
            result = parse(guide(["a.tv", "long.tv", "b.tv"]))
        self.assertEqual(list(result["channels"]), ["a.tv", "b.tv"])
        self.assertEqual(result["warnings"], [
            "2 programmes dropped: their channel id is longer than 4 characters"])
        with mock.patch.object(helper, "EPG_MAX_GUIDE_ID", 4):
            result = parse(guide(["long.tv"], per_channel=1))
        self.assertEqual(result["warnings"], [
            "1 programme dropped: its channel id is longer than 4 characters"])

    def test_with_an_index_neither_cap_applies(self):
        """Every key is then a playlist tvg-id, already bounded by the
        playlist; the guide-side caps must not cut a matched row."""
        doc = {"version": 1, "count": 5, "channels": [
            {"id": "p%d" % i, "tvgId": cid, "name": "Row %d" % i, "group": "G", "url": "http://h.test/%d" % i}
            for i, cid in enumerate(self.IDS)]}
        index = helper.build_alias(doc)[0]
        with mock.patch.object(helper, "MAX_CHANNELS", 3), mock.patch.object(helper, "EPG_MAX_GUIDE_ID", 2):
            result = parse(guide(self.IDS), index)
        self.assertEqual(sorted(result["channels"]), self.IDS)
        self.assertEqual(result["warnings"], [])

    def test_the_verb_writes_at_most_the_cap_into_epg_now(self):
        """Through `epg` with no channels.json, which is the no-index path:
        what the shell reads holds the admitted channels and no more."""
        work = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, work, True)
        path = os.path.join(work, "guide.xml")
        with open(path, "wb") as handle:
            handle.write(guide(self.IDS))
        cache = os.path.join(work, "cache")
        os.mkdir(cache, 0o700)
        out = io.StringIO()
        with mock.patch.object(helper, "MAX_CHANNELS", 2), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(io.StringIO()):
            code = helper.main(["epg", "--url", path, "--cache-dir", cache, "--now", str(NOW), "--force"])
        self.assertEqual(code, 0, out.getvalue())
        status = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertEqual(status["epgChannels"], 2)
        self.assertEqual(status["warnings"], [
            "6 programmes dropped: the guide lists more than 2 channels"
            " and no playlist was loaded to choose among them"])
        with open(os.path.join(cache, "epg-now.json"), encoding="utf-8") as handle:
            now_doc = json.load(handle)
        self.assertEqual(sorted(now_doc["channels"]), ["a.tv", "b.tv"])


class EpgCountedSentenceTest(unittest.TestCase):
    """Every sentence parse_xmltv counts, for one and for many."""

    # Written out, not derived from the table: a copy of the table would
    # agree with the table whatever it said (rule 12).
    EXPECTED = {
        "badTime": ("1 programme with an unreadable time skipped",
                    "3 programmes with unreadable times skipped"),
        "noTitle": ("1 programme without a title skipped",
                    "3 programmes without a title skipped"),
        "unknown": ("1 programme for a channel not in the playlist dropped",
                    "3 programmes for channels not in the playlist dropped"),
        "contested": ("1 programme dropped: another guide channel already matched that playlist channel",
                      "3 programmes dropped: another guide channel already matched that playlist channel"),
        "beyond": ("1 programme dropped: the guide lists more than 50000 channels and no playlist was loaded to choose among them",
                   "3 programmes dropped: the guide lists more than 50000 channels and no playlist was loaded to choose among them"),
        "longId": ("1 programme dropped: its channel id is longer than 256 characters",
                   "3 programmes dropped: their channel id is longer than 256 characters"),
    }

    def test_every_kind_reads_right_at_one_and_at_three(self):
        kinds = [kind for kind, _, _ in helper.epg_parse_warnings()]
        self.assertEqual(kinds, list(self.EXPECTED))
        for kind, one, many in helper.epg_parse_warnings():
            self.assertEqual(helper.counted_sentence(1, one, many), self.EXPECTED[kind][0])
            self.assertEqual(helper.counted_sentence(3, one, many), self.EXPECTED[kind][1])

    def programmes(self, count):
        """`count` of each of the four ordinary refusals, against a playlist
        that names a.tv and b.tv: an unreadable start, no title, a channel
        not in the playlist, and b.tv claimed by name after a.tv took it by
        id (the contested case)."""
        rows = []
        for i in range(count):
            rows.append('<programme start="never" channel="a.tv"><title>x</title></programme>')
            rows.append('<programme start="%s" channel="a.tv"><title></title></programme>' % xmltv_time(NOW + i))
            rows.append('<programme start="%s" channel="zz.tv"><title>x</title></programme>' % xmltv_time(NOW + i))
            rows.append('<programme start="%s" channel="dup.tv"><title>x</title></programme>' % xmltv_time(NOW + i))
        return ('<tv><channel id="a.tv"><display-name>Primary</display-name></channel>'
                '<channel id="dup.tv"><display-name>Alpha</display-name></channel>'
                '<programme start="%s" channel="a.tv"><title>ok</title></programme>%s</tv>'
                % (xmltv_time(NOW), "".join(rows))).encode()

    def test_through_the_parse_one_and_many(self):
        doc = {"version": 1, "count": 1, "channels": [
            {"id": "p0", "tvgId": "a.tv", "name": "Alpha", "group": "G", "url": "http://h.test/0"}]}
        for count, form in ((1, 0), (3, 1)):
            index = helper.build_alias(json.loads(json.dumps(doc)))[0]
            result = parse(self.programmes(count), index)
            expected = [self.EXPECTED[kind][form] for kind in ("badTime", "noTitle", "unknown", "contested")]
            self.assertEqual(result["warnings"], expected)


OLD_QUALIFIER = re.compile(r"\s*\([^()]*\)\s*$")


def ordinary_names(seed, count):
    """Short names over the characters the strip decides on: letters, the
    two parentheses, ordinary whitespace (short runs) and the line breaks a
    provider leaves in, a non-breaking and an em space."""
    rng = random.Random(seed)
    pieces = ["Pluto", "TV", "Reality", "ESPN", "(", ")", "(United States)", "(HD)", " ", "  ", "\t",
              "\n", "\u00a0", "\u2003", "x", "1", "[Not 24/7]", "()", ")(", "( )"]
    for _ in range(count):
        yield "".join(rng.choice(pieces) for _ in range(rng.randint(0, 9)))


class QualifierEquivalenceTest(unittest.TestCase):
    """strip_trailing_qualifier answers exactly what the regex it replaced
    answered (D-EPG-8), on ordinary inputs, the old pattern run as the
    oracle. Seen red on mutations of its decisions (find for rfind, the final
    rstrip dropped, the inner `)` check dropped)."""

    def test_rstrip_and_backslash_s_test_the_same_predicate_on_every_code_point(self):
        space = re.compile(r"\s")
        differ = [cp for cp in range(0x110000)
                  if bool(space.fullmatch(chr(cp))) != chr(cp).isspace()]
        self.assertEqual(differ, [])

    def test_equal_to_the_old_pattern_on_generated_and_named_inputs(self):
        named = ["Pluto TV Reality (United States)", "Pluto TV Reality (United States) ",
                 "Pluto TV Reality (United States)\t", "Alpha (US)\n", "ESPN (Deportes) Live",
                 "A (b) (c)", "A (b (c))", "A ((c)", "A (c))", "(only)", "  (x)  ", "no paren",
                 "", ")", "(", "x )", "a\n(b)", "a (b\nc)", "a  \u00a0 (b) \u2003"]
        checked = 0
        for text in named + list(ordinary_names(7, 20000)):
            self.assertEqual(helper.strip_trailing_qualifier(text), OLD_QUALIFIER.sub("", text), repr(text))
            self.assertEqual(helper.bare_name_key(text), helper.epg_name_key(OLD_QUALIFIER.sub("", text)),
                             repr(text))
            checked += 1
        self.assertGreater(checked, 20000)

    def test_bare_name_key_still_takes_any_value(self):
        self.assertEqual(helper.bare_name_key(None), "")
        self.assertEqual(helper.bare_name_key(101), helper.epg_name_key("101"))


class DisplayNameKeyTest(unittest.TestCase):
    """A <display-name> is folded and cut BEFORE either key is made."""

    def keyed(self, cap, display):
        seen = []
        real = helper.epg_name_key

        def record(value):
            seen.append(value)
            return real(value)

        data = ('<tv><channel id="g.tv"><display-name>%s</display-name></channel>'
                '<programme start="%s" channel="g.tv"><title>x</title></programme></tv>'
                % (display, xmltv_time(NOW))).encode()
        doc = {"version": 1, "count": 1, "channels": [
            {"id": "p0", "tvgId": "other.us", "name": "Alpha (US)", "group": "G", "url": "http://h.test/0"}]}
        index = helper.build_alias(doc)[0]
        with mock.patch.object(helper, "EPG_MAX_DISPLAY_NAME", cap), \
                mock.patch.object(helper, "epg_name_key", side_effect=record):
            result = parse(data, index)
        return seen, result

    def test_the_keys_are_made_from_the_folded_and_cut_text(self):
        seen, _ = self.keyed(12, "Alpha   \t (Somewhere quite long)")
        self.assertTrue(seen)
        for value in seen:
            self.assertLessEqual(len(value), 12, seen)
            self.assertNotIn("  ", value, seen)
            self.assertNotIn("\t", value, seen)

    def test_a_name_cut_to_the_cap_matches_the_playlist_name_it_starts_with(self):
        _, result = self.keyed(10, "Alpha (US) and a great deal more")
        self.assertEqual(result["seenIds"], {"other.us"})
        _, result = self.keyed(512, "Alpha (US) and a great deal more")
        self.assertEqual(result["seenIds"], set())


# _EPG_NAME_NOISE as it stood before D-EPG-12 (lane-bounds-h, 8a3a0de): the
# oracle the rewritten pattern is held equal to.
OLD_NOISE = re.compile(
    r"\((?:\d{3,4}p|sd|hd|fhd|uhd|4k|h\.?26[45])\)"
    r"|\[\s*not\s*24\s*[-/]?\s*7\s*\]"
    r"|\[\s*geo[\s-]*blocked\s*\]", re.IGNORECASE)


def marker_spellings(seed, count):
    """Short strings over the characters the `[not 24/7]` alternative
    decides on: the bracket, the words, the two separators, short whitespace
    runs (a tab, an NBSP) and a few letters, so every way of splitting a
    whitespace run across the optional separator is generated."""
    rng = random.Random(seed)
    pieces = ["[", "]", "not", "NOT", "24", "7", "-", "/", " ", "  ", "\t", "\u00a0", "x", "Alpha",
              "(1080p)", "(HD)", "geo", "blocked", "[not 24/7]", "[Not 24-7]", "[geo-blocked]"]
    for _ in range(count):
        yield "".join(rng.choice(pieces) for _ in range(rng.randint(0, 9)))


class NoiseEquivalenceTest(unittest.TestCase):
    """D-EPG-12 (R32d): the rewritten `[not 24/7]` alternative of
    _EPG_NAME_NOISE matches exactly what the old one matched, so every name
    keys as before. Seen red on mutations of the new alternative (the run
    inside the separator group dropped; the group made mandatory)."""

    NAMED = ["[not 24/7]", "[Not 24-7]", "[NOT 24 / 7]", "[ not 24 / 7 ]", "[not 24 7]", "[not 24- 7]",
             "[not 24 -7]", "[not 24  /  7]", "[not 24 x]", "[not 24   ]", "[not 247]", "[not24/7]",
             "[not 24//7]", "[not 24 / /7]", "[not 24/-7]", "[not\t24/7]", "[not 24\u00a07]",
             "[NOT 24/7] Alpha", "Alpha [not 24/7] (1080p)", "Alpha (1080p) [geo-blocked]",
             "[geo blocked]", "[geo--blocked]", "[[not 24/7]]", "[not 24/7", "not 24/7]", ""]

    def test_equal_to_the_old_pattern_on_generated_and_named_inputs(self):
        matched = 0
        for text in self.NAMED + list(marker_spellings(5, 20000)):
            self.assertEqual(helper._EPG_NAME_NOISE.sub(" ", text), OLD_NOISE.sub(" ", text), repr(text))
            matched += OLD_NOISE.search(text) is not None
        self.assertGreater(matched, 1000)

    def test_the_name_key_is_unchanged_on_ordinary_names(self):
        """The whole key, old pattern against new, over names that carry no
        control character (those are the D-EPG-12 fold's own change, pinned
        by OneFoldTest)."""
        for text in self.NAMED + list(marker_spellings(6, 5000)) + list(ordinary_names(8, 5000)):
            self.assertEqual(helper.epg_name_key(text),
                             helper.normalize_id_text(OLD_NOISE.sub(" ", helper.epg_name_text(text))), repr(text))


class OneFoldTest(unittest.TestCase):
    """D-EPG-12 (R32d), the round-2 recheck's P3 (c): the playlist side and
    the guide side of the name key take ONE fold, epg_name_text, so a name
    carrying a DEL, a tab or a C0 control keys the same from either side.
    Red on the base: build_alias keyed the raw name ("alpha\\x7fone") while
    parse_xmltv keyed the folded one ("alpha one")."""

    # A DEL and a tab are legal XML 1.0 characters, so a guide can carry
    # them; the other C0 controls are not (expat refuses them), so only a
    # playlist can, and those are keyed below without a parse.
    XML_NAMES = ["Alpha\x7fOne", "Beta\tTwo", "Delta \x7f Four", "Eps\x7f\x7f  ilon", "Eta\x7f(US)"]
    NAMES = XML_NAMES + ["Gamma\x01Three", "Zeta\x1fSix"]

    def test_a_name_with_a_control_character_keys_the_same_from_either_side(self):
        for name in self.NAMES:
            playlist_side = helper.epg_name_key(name)
            guide_side = helper.epg_name_key(helper.epg_name_text(name))
            self.assertEqual(playlist_side, guide_side, repr(name))
            self.assertNotIn("\x7f", playlist_side, repr(name))
            self.assertNotIn("\x01", playlist_side, repr(name))
            self.assertEqual(helper.bare_name_key(name + " (US)"),
                             helper.bare_name_key(helper.epg_name_text(name + " (US)")), repr(name))
        # The fold comes BEFORE the strip, as the guide side has always
        # ordered it: a DEL after the closing parenthesis is a space the
        # strip then removes, from the playlist side too.
        self.assertEqual(helper.bare_name_key("Eta (US)\x7f"), helper.epg_name_key("Eta"))
        self.assertEqual(helper.bare_name_key("Eta (US)\x7f"), helper.bare_name_key(helper.epg_name_text("Eta (US)\x7f")))

    def test_the_fold_is_the_same_text_both_sides_see(self):
        self.assertEqual(helper.epg_name_text("  Alpha\x7f\x7f One\t"), "Alpha One")
        self.assertEqual(helper.epg_name_text(None), "")
        self.assertEqual(helper.epg_name_text(101), "101")
        self.assertEqual(helper.epg_name_text(helper.epg_name_text("A\x01 \x7fB")), helper.epg_name_text("A\x01 \x7fB"))
        with mock.patch.object(helper, "EPG_MAX_DISPLAY_NAME", 5):
            self.assertEqual(helper.epg_name_text("Alphabet"), "Alpha")

    def test_the_same_name_on_both_sides_matches_through_the_real_parse(self):
        names = self.XML_NAMES
        doc = {"version": 1, "count": len(names), "channels": [
            {"id": "p%d" % i, "tvgId": "row%d" % i, "name": name, "group": "G", "url": "http://h.test/%d" % i}
            for i, name in enumerate(names)]}
        index = helper.build_alias(doc)[0]
        xml = ["<tv>"]
        for i, name in enumerate(names):
            xml.append('<channel id="g%d"><display-name>%s</display-name></channel>' % (i, name))
        for i in range(len(names)):
            xml.append('<programme start="%s" stop="%s" channel="g%d"><title>Show</title></programme>'
                       % (xmltv_time(NOW - 600), xmltv_time(NOW + 600), i))
        xml.append("</tv>")
        result = parse("".join(xml).encode("utf-8"), index)
        self.assertEqual(sorted(result["seenIds"]), sorted("row%d" % i for i in range(len(names))))
        self.assertEqual(result["warnings"], [])

    def test_a_control_character_reads_as_the_space_it_is_folded_to_on_either_side(self):
        """The guide has always read a DEL as a space; now the playlist does
        too, so "Alpha One" on one side pairs with "Alpha\\x7fOne" on the
        other whichever side carries the DEL."""
        self.assertEqual(helper.epg_name_key("Alpha\x7fOne"), helper.epg_name_key("Alpha One"))
        self.assertNotEqual(helper.epg_name_key("Alpha\x7fOne"), helper.epg_name_key("AlphaOne"))


class GuideIdCapBoundaryTest(unittest.TestCase):
    """D-EPG-10's two caps at their boundary (the round-2 recheck's P3 (b)):
    `len(key) > EPG_MAX_GUIDE_ID + 1` and `len(claim) > MAX_CHANNELS` each
    passed every earlier case. Red on both."""

    def test_an_id_of_exactly_the_cap_is_admitted_and_one_more_is_not(self):
        with mock.patch.object(helper, "EPG_MAX_GUIDE_ID", 4):
            result = parse(guide(["abcd", "abcde"]))
        self.assertEqual(list(result["channels"]), ["abcd"])
        self.assertEqual(result["warnings"], [
            "2 programmes dropped: their channel id is longer than 4 characters"])
        with mock.patch.object(helper, "EPG_MAX_GUIDE_ID", 5):
            result = parse(guide(["abcd", "abcde"]))
        self.assertEqual(list(result["channels"]), ["abcd", "abcde"])
        self.assertEqual(result["warnings"], [])

    def test_exactly_the_cap_of_channels_is_admitted_with_nothing_refused_and_the_next_is(self):
        with mock.patch.object(helper, "MAX_CHANNELS", 3):
            result = parse(guide(["a.tv", "b.tv", "c.tv"]))
        self.assertEqual(list(result["channels"]), ["a.tv", "b.tv", "c.tv"])
        self.assertEqual(result["warnings"], [])
        with mock.patch.object(helper, "MAX_CHANNELS", 3):
            result = parse(guide(["a.tv", "b.tv", "c.tv", "d.tv"]))
        self.assertEqual(list(result["channels"]), ["a.tv", "b.tv", "c.tv"])
        self.assertEqual(result["warnings"], [
            "2 programmes dropped: the guide lists more than 3 channels"
            " and no playlist was loaded to choose among them"])

    def test_the_channels_kept_are_the_first_the_programmes_name_not_the_declarations(self):
        """What the README says: a <channel> declaration plays no part
        without an index; the first MAX_CHANNELS distinct ids the PROGRAMMES
        name, in document order, are the ones kept."""
        data = guide(["a.tv", "b.tv", "c.tv"], per_channel=0).replace(b"</tv>", b"") + "".join(
            '<programme start="%s" stop="%s" channel="%s"><title>S</title></programme>'
            % (xmltv_time(NOW - 600), xmltv_time(NOW + 600), cid)
            for cid in ["c.tv", "z.tv", "a.tv", "b.tv"]).encode() + b"</tv>"
        with mock.patch.object(helper, "MAX_CHANNELS", 2):
            result = parse(data)
        self.assertEqual(list(result["channels"]), ["c.tv", "z.tv"])
        self.assertEqual(result["warnings"], [
            "2 programmes dropped: the guide lists more than 2 channels"
            " and no playlist was loaded to choose among them"])


OLD_IPV6 = re.compile(r"^\[[0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*(?:%25[A-Za-z0-9._~\-]+)?\]$")


class Ipv6LiteralEquivalenceTest(unittest.TestCase):
    """_IPV6_LITERAL accepts exactly what the two-run pattern accepted."""

    def test_equal_to_the_old_pattern(self):
        rng = random.Random(11)
        pieces = ["[", "]", ":", "::", ".", "1", "f", "F", "g", "%25", "%2", "eth0", "~", "\n", "-", "%"]
        named = ["[::1]", "[fe80::1%25eth0]", "[1.2.3.4]", "[::]", "[]", "[:]", "[::1]\n", "[::1]x",
                 "[1234]", "[12:34", "::1]", "[::1%25]", "[g::1]", "[1:2:3:4:5:6:7:8]"]
        middle = [":", ":", "::", ".", "1", "f", "F", "0db8", "%25eth0", "%25", "g", "~", "%", "]", "\n"]
        texts = list(named)
        for _ in range(20000):
            if rng.random() < 0.3:
                texts.append("".join(rng.choice(pieces) for _ in range(rng.randint(0, 10))))
            else:
                body = "".join(rng.choice(middle) for _ in range(rng.randint(0, 8)))
                texts.append("[" + body + rng.choice(["]", "]", "]", "]\n", "", "]x"]))
        accepted = 0
        for text in texts:
            old = OLD_IPV6.match(text) is not None
            self.assertEqual(helper._IPV6_LITERAL.match(text) is not None, old, repr(text))
            accepted += old
        self.assertGreater(accepted, 500)
        self.assertLess(accepted, len(texts) - 2000)


def stopless_run(n, start=NOW, title="News"):
    return [helper.retain_programme(start, None, title, {}) for _ in range(n)]


class EncodeLinearityTest(unittest.TestCase):
    """D-EPG-9, R30h: _retained_start runs at most twice a programme, for the
    sort and for the backward pass, whatever the input. Counted by wrapping the one
    function that reads a start, never timed. The shape the finding named --
    n identical stopless programmes sharing one start -- cost n*(n-1)/2
    reads of a later start in f55a32f's rescan; seen red here on that rescan
    restored as a mutation."""

    def reads(self, items):
        calls = [0]
        real = helper._retained_start

        def counting(item):
            calls[0] += 1
            return real(item)

        with mock.patch.object(helper, "_retained_start", side_effect=counting):
            blob, kept = helper.encode_retained(items)
        return calls[0], blob, kept

    def test_shared_starts_without_stops_are_read_twice_each(self):
        for n in (1, 2, 10, 60):
            calls, _, kept = self.reads(stopless_run(n))
            self.assertEqual(kept, 1)
            self.assertLessEqual(calls, 2 * n, n)

    def test_a_mixed_channel_is_read_twice_each_with_the_cap_lowered(self):
        items = (stopless_run(20) + stopless_run(20, NOW + 600, "Film")
                 + [helper.retain_programme(NOW + 60 * i, NOW + 60 * i + 30, "T%d" % i, {}) for i in range(20)])
        random.Random(3).shuffle(items)
        with mock.patch.object(helper, "EPG_MAX_PER_CHANNEL", 3):
            calls, _, kept = self.reads(list(items))
        self.assertEqual(kept, 3)
        self.assertLessEqual(calls, 2 * len(items))


def random_tuples(rng):
    """A small ordinary channel as encode_records takes it: shared starts,
    missing stops, repeats with and without detail, stops not after their
    start, the twelve-digit sentinels, a negative start now and then."""
    starts = [NOW + 600 * rng.randint(-3, 6) for _ in range(rng.randint(1, 5))]
    items = []
    for _ in range(rng.randint(0, 40)):
        start = rng.choice(starts + [-600])
        roll = rng.random()
        if roll < 0.45:
            stop = None
        elif roll < 0.55:
            stop = start - rng.choice((0, 60))
        elif roll < 0.62:
            stop = rng.choice((10 ** 11, 10 ** 12))
        else:
            stop = start + rng.choice((300, 600, 900))
        title = rng.choice(["News", "News", "Film \"Q\"", "Caf\u00e9", "Rocket \U0001F680"])
        detail = rng.choice([{}, {}, {"desc": "Synopsis."}, {"category": "Drama", "episode": "S1 E2"}])
        items.append((start, stop, title, detail))
    for item in list(items)[: rng.randint(0, 8)]:
        items.append(item)
    rng.shuffle(items)
    return items


class EncodeDifferentialTest(unittest.TestCase):
    """The backward pass against lane-bounds-int's forward pointer, the same
    ordinary inputs, the same output, byte for byte."""

    def setUp(self):
        self.base = load_ref(self, INT_BASE)

    def test_encode_records_is_identical(self):
        rng = random.Random(5)
        compared = kept = 0
        for _ in range(3000):
            items = random_tuples(rng)
            for cap in (None, 2, 3):
                results = []
                for module in (self.base, helper):
                    saved = module.EPG_MAX_PER_CHANNEL
                    if cap is not None:
                        module.EPG_MAX_PER_CHANNEL = cap
                    try:
                        results.append(module.encode_records([(s, e, t, dict(d)) for s, e, t, d in items]))
                    finally:
                        module.EPG_MAX_PER_CHANNEL = saved
                self.assertEqual(results[1], results[0], (items, cap))
                compared += 1
                kept += results[1][1]
        self.assertEqual(compared, 9000)
        self.assertGreater(kept, 20000)

    def test_parse_results_are_identical_on_seeded_guides(self):
        checked = 0
        for seed in range(40):
            data, ids = random_guide(seed)
            for index_doc in (None, playlist_doc(ids)):
                results = []
                for module in (self.base, helper):
                    index = module.build_alias(json.loads(json.dumps(index_doc)))[0] if index_doc else None
                    results.append(comparable(module.parse_xmltv(module.open_xml_stream(data), NOW, index),
                                              reword=module is helper))
                self.assertEqual(results[1], results[0], (seed, bool(index_doc)))
                checked += 1
        self.assertEqual(checked, 80)


class LinearSiblingsTest(unittest.TestCase):
    """Rule 15 over D-EPG-9's shape, a membership scan per item: three more
    places did one, all on provider text (split_groups on a persistent
    #EXTGRP, build_alias's bare-name owner lists, addrNameConflicts' set
    difference per row). Each is now one pass; each is held to
    lane-bounds-int's answer on ordinary inputs. Seen red on mutations of
    the new decisions (the dedupe dropped, the holder test reduced to
    `len(declared) > 1`)."""

    def setUp(self):
        self.base = load_ref(self, INT_BASE)

    def test_split_groups_is_identical(self):
        rng = random.Random(9)
        pieces = ["News", "Sport", "news", " News ", "", " ", "Kids", "\u00e9t\u00e9", "A"]
        for _ in range(5000):
            text = ";".join(rng.choice(pieces) for _ in range(rng.randint(0, 12)))
            self.assertEqual(helper.split_groups(text), self.base.split_groups(text), repr(text))

    def playlist(self, rng, rows):
        names = ["Pluto TV Reality (United States)", "Pluto TV Reality (Canada)", "News (US)", "News",
                 "ESPN (Deportes) Live", "Alpha (HD)", "Alpha"]
        out = []
        for i in range(rows):
            tvg = rng.choice(["Pride.us", "Reality.us", "a.tv", "b.tv", "c.tv", "row%d.tv" % (i % 9)])
            token = rng.choice(["69fa3faab9c0f0d444e64de3", "5d8bf0b06d2d855ee15115e3", "short", "aaaaaaaaaaaa%d" % i])
            out.append({"id": "p%d" % i, "tvgId": tvg, "name": rng.choice(names), "group": "G",
                        "url": "http://h.test/live/%s/master.m3u8" % token})
        return {"version": 1, "count": len(out), "channels": out}

    def guide(self, rng):
        ids = ["69fa3faab9c0f0d444e64de3", "5d8bf0b06d2d855ee15115e3", "a.tv", "zz.tv", "aaaaaaaaaaaa3"]
        names = ["Pluto TV Pride", "Pluto TV Reality", "News", "Alpha", "Other (X)"]
        out = ["<tv>"]
        for cid in ids:
            out.append('<channel id="%s"><display-name>%s</display-name><display-name>%s</display-name></channel>'
                       % (cid, rng.choice(names), rng.choice(names)))
        for cid in ids:
            out.append('<programme start="%s" channel="%s"><title>T</title></programme>' % (xmltv_time(NOW), cid))
        out.append("</tv>")
        return "".join(out).encode()

    def test_the_bare_index_and_the_conflict_count_are_identical(self):
        rng = random.Random(13)
        conflicts = 0
        for _ in range(300):
            doc = self.playlist(rng, rng.randint(1, 30))
            data = self.guide(rng)
            results = []
            for module in (self.base, helper):
                index = module.build_alias(json.loads(json.dumps(doc)))[0]
                parsed = module.parse_xmltv(module.open_xml_stream(data), NOW, index)
                results.append((index["bare"], comparable(parsed, reword=module is helper)))
            self.assertEqual(results[1], results[0], doc)
            conflicts += results[1][1]["addrNameConflicts"]
        # The inputs must reach the counter, or equality proves nothing.
        self.assertGreater(conflicts, 30)


class DuplicateKeyStopTest(unittest.TestCase):
    """The duplicate check compares the DERIVED STOP as well as the start and
    the texts. The round-1 recheck of lane-bounds-l mutated the key to
    (start, payload) and every EPG test stayed green; these go red on it."""

    def test_same_start_and_texts_with_different_stops_are_two_programmes(self):
        blob, kept = helper.encode_records([(NOW, NOW + 60, "A", {}), (NOW, NOW + 120, "A", {})])
        self.assertEqual(kept, 2)
        records = blob.split(helper.EPG_RECORD_SEP)
        self.assertEqual([helper.record_to_dict(r)["stop"] for r in records], [NOW + 60, NOW + 120])

    def test_raw_stops_that_clamp_alike_are_still_two_programmes(self):
        """10**11 and 10**12 both clamp to the ten-digit ceiling, so the two
        records are identical text; the decision is on the raw stop."""
        blob, kept = helper.encode_records([(NOW, 10 ** 11, "A", {}), (NOW, 10 ** 12, "A", {})])
        self.assertEqual(kept, 2)

    def test_an_exact_repeat_is_one(self):
        self.assertEqual(helper.encode_records([(NOW, NOW + 60, "A", {}), (NOW, NOW + 60, "A", {})])[1], 1)


class TimeMemoAsciiTest(unittest.TestCase):
    """The memo keeps an ASCII key only: a non-ASCII value is parsed and
    answered, and not remembered (the recheck's P3 (d))."""

    def test_a_non_ascii_time_is_answered_and_not_kept(self):
        wide = "\uff12\uff10\uff12\uff16\uff11\uff10\uff12\uff11\uff11\uff19\uff10\uff10\uff10\uff10 +0000"
        memo = {}
        answer = helper.parse_xmltv_time(wide, memo)
        self.assertEqual(answer, helper.parse_xmltv_time("20261021190000 +0000", {}))
        self.assertEqual(memo, {})
        self.assertEqual(helper.parse_xmltv_time("20261021190000 +0000", memo), answer)
        self.assertEqual(list(memo), ["20261021190000 +0000"])


if __name__ == "__main__":
    unittest.main()
