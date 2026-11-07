"""D-SINK-79 (2026-11-05): the guide's whitespace fold never folds inside a
URL's run.

clean_title, clean_detail and clean_field folded every run of _CONTROL_WS
(Python's whitespace, C0 and DEL) to one space BEFORE any redactor saw the
text. A redactor ends a URL's run at the six ASCII delimiters alone (R32a'''),
so a password holding U+00A0, U+2028, U+3000, U+0085, DEL or any of the 20
code points XML allows that the fold took is URL text to both redactors, and
redacts to the host. The fold turned it into a space first, which ends a run
at every sink: `http://qqqqqq:zz<U+00A0>zz@cdn.test/x` was stored as
`http://qqqqqq:zz zz@cdn.test/x`, and every sink printed the username, and
the password's tail with no scheme in front of it. fold_space keeps a URL's
run whole: its `://` written plainly, the controls the fold turns into a
space and the line separators replaced by U+FFFD after it (the review's F9
and F11: deleting one could turn a port into digits), every other character
kept -- and only for a `://` a redactor reads as a URL's, with an ASCII
letter in the scheme-legal run before it.

tests/fixtures/epg-fold.json holds the cases, and tests/Model.test.js runs it
too: there, every stored text through each shell sink a guide text reaches,
and the panel over a raw record, whose shell fold ran before its redaction
(Model.epgEpisodeText). Here: the shipping parse stores what the fixture
says, no helper sink shows a letter of the credential, fold_space against
the rule over random texts, the record format's separators, and linear time.
"""
import calendar
import contextlib
import io
import json
import os
import random
import tempfile
import time
import unittest

from helper_loader import load_helper

helper = load_helper()
HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "fixtures", "epg-fold.json"), "rb") as fh:
    FIXTURE_BYTES = fh.read()
FIXTURE = json.loads(FIXTURE_BYTES.decode("ascii"))
CASES = FIXTURE["cases"]
NOW = calendar.timegm((2026, 9, 12, 21, 0, 0, 0, 0, 0))
DELIMITERS = "\t\n\x0b\x0c\r "
NB = chr(0xa0)
DEL = chr(0x7f)
NEL = chr(0x85)
CSI = chr(0x9b)
LS = chr(0x2028)
PS = chr(0x2029)
REPL = chr(0xfffd)


def leaked(text):
    return [c for c in FIXTURE["secret"] if c in text]


def is_control(c):
    return ord(c) < 0x20 or 0x7f <= ord(c) <= 0x9f


def folds(c):
    """The plain fold's class (_CONTROL_WS), as stated: whitespace, C0, DEL."""
    return c.isspace() or ord(c) < 0x20 or c == DEL


def mark_end(text, i):
    """The end of a `://` at `i`, controls allowed between its three
    characters, or -1."""
    if text[i] != ":":
        return -1
    j = i + 1
    for _ in range(2):
        while j < len(text) and is_control(text[j]):
            j += 1
        if j >= len(text) or text[j] != "/":
            return -1
        j += 1
    return j


def scheme_letter(text, i):
    """An ASCII letter in the scheme-legal run (letters, digits, `+`, `.`,
    `-`) that ends at `i`: where a redactor starts a scheme."""
    j = i - 1
    while j >= 0 and text[j].isascii() and (text[j].isalnum() or text[j] in "+.-"):
        if text[j].isalpha():
            return True
        j -= 1
    return False


def fold_reference(text):
    """The rule, as stated, one character at a time: a URL's run runs from a
    mark with an ASCII letter in the scheme-legal run before it to the first
    of the six delimiters; its mark is written `://`, and after it the
    controls the plain fold folds and the line and paragraph separators
    become U+FFFD and everything else is kept. Outside a run, every run of
    the plain fold's class is one space."""
    out, i, n = [], 0, len(text)
    while i < n:
        end = mark_end(text, i)
        if end > 0 and scheme_letter(text, i):
            j = end
            while j < n and text[j] not in DELIMITERS:
                j += 1
            out.append("://" + "".join(REPL if (is_control(c) and folds(c)) or c in (LS, PS) else c
                                       for c in text[end:j]))
            i = j
        elif folds(text[i]):
            while i < n and folds(text[i]):
                i += 1
            out.append(" ")
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def xml_legal(cp):
    return cp in (0x9, 0xa, 0xd) or 0x20 <= cp <= 0xd7ff or 0xe000 <= cp <= 0xfffd or cp >= 0x10000


def stored_fields(cases):
    """What the shipping parse stores for each case's field: one programme
    per case, its text as the title, or as the description, the category or
    the on-screen episode under a plain title, a minute apart, 300 to a
    channel; "" for a programme not kept."""
    programmes = []
    for i, case in enumerate(cases):
        start = time.strftime("%Y%m%d%H%M%S +0000", time.gmtime(NOW + i % 300 * 60))
        stop = time.strftime("%Y%m%d%H%M%S +0000", time.gmtime(NOW + i % 300 * 60 + 60))
        text = case["raw"].replace("&", "&amp;").replace("<", "&lt;")
        field = case["field"]
        if field == "title":
            body = "<title>%s</title>" % text
        elif field == "episode":
            body = '<title>T</title><episode-num system="onscreen">%s</episode-num>' % text
        else:
            body = "<title>T</title><%s>%s</%s>" % (field, text, field)
        programmes.append('<programme start="%s" stop="%s" channel="a%d.tv">%s</programme>'
                          % (start, stop, i // 300, body))
    channels = "".join('<channel id="a%d.tv"><display-name>A%d</display-name></channel>' % (n, n)
                       for n in range(len(cases) // 300 + 1))
    document = ('<?xml version="1.0" encoding="UTF-8"?><tv>' + channels + "".join(programmes)
                + "</tv>").encode("utf-8")
    parsed = helper.parse_xmltv(helper.open_xml_stream(document), NOW, None)
    out = [""] * len(cases)
    for key, records in parsed["channels"].items():
        for record in records.split(helper.EPG_RECORD_SEP):
            d = helper.record_to_dict(record)
            i = int(key[1:-3]) * 300 + (d["start"] - NOW) // 60
            out[i] = d.get(cases[i]["field"], "")
    return out


class FixtureTest(unittest.TestCase):
    def test_the_fixture_is_ascii_and_whole(self):
        self.assertTrue(all(b < 0x80 for b in FIXTURE_BYTES))
        # The 20 code points are the plain fold's class less the six
        # delimiters, where XML allows them: read from the helper's own
        # pattern, so the list is joined to it by a call (rule 13).
        computed = ["U+%04X" % cp for cp in range(0x110000)
                    if not 0xd800 <= cp <= 0xdfff and xml_legal(cp) and chr(cp) not in DELIMITERS
                    and helper._CONTROL_WS.fullmatch(chr(cp))]
        self.assertEqual(computed, FIXTURE["codePoints"])
        self.assertEqual(len(computed), 20)
        sweep = [c for c in CASES if c["kind"] == "sweep"]
        self.assertEqual(len(sweep), 20 * 3 * 4)
        self.assertGreaterEqual(len(CASES) - len(sweep), 40)
        self.assertGreaterEqual(len(FIXTURE["fold"]), 26)

    def test_the_parse_stores_what_the_fixture_says(self):
        bad = [(c["why"], c["stored"], got) for c, got in zip(CASES, stored_fields(CASES)) if got != c["stored"]]
        self.assertEqual(bad[:6], [])
        self.assertEqual(len(bad), 0)

    def test_no_helper_sink_shows_a_credential(self):
        # A title is stored as written and redacted at its sinks; a detail is
        # stored redacted, and its redaction changes nothing more. The
        # player's title, which deletes controls first, is held as well.
        bad = []
        for c, stored in zip(CASES, stored_fields(CASES)):
            shown = helper.redact_urls(stored)
            if shown != c["helper"]:
                bad.append((c["why"], "redact_urls", shown))
            # D-EPG-18: a withheld host is stored as `http://[host withheld]`,
            # which a second redaction reads as a bracketed host.
            if c["field"] != "title" and stored != c["helper"] and helper.HOST_WITHHELD not in stored:
                bad.append((c["why"], "stored unredacted", stored))
            for sink, out in (("redact_urls", shown), ("player_title_text", helper.player_title_text(stored))):
                if leaked(out):
                    bad.append((c["why"], sink, out))
        self.assertEqual(bad[:6], [])

    def test_each_url_redacts_to_exactly_its_host(self):
        # The other direction, so a fold that dropped every URL could not
        # pass: each case whose stored text keeps a URL shows its host, as
        # the parse stores it and the helper redacts it.
        kept = [(c, s) for c, s in zip(CASES, stored_fields(CASES))
                if "://" in c["stored"] and "http ://" not in c["stored"]
                and "withheld" not in c["helper"] and "cdn.test" in c["raw"]]
        self.assertGreaterEqual(len(kept), 180)
        self.assertEqual([c["why"] for c, s in kept if "http://" + FIXTURE["host"] not in helper.redact_urls(s)], [])
        self.assertEqual([c["why"] for c, _ in kept if FIXTURE["host"] not in c["shell"]], [])

    def test_the_old_fold_is_what_leaked(self):
        # The counterfactual, measured each run: the same raw text through
        # the plain fold before the cut leaks in every sweep title, and
        # through no fold at all leaks in none.
        sweep = [c for c in CASES if c["kind"] == "sweep" and c["field"] == "title"]
        old = [helper.redact_urls(helper.cut_free_text(helper._CONTROL_WS.sub(" ", c["raw"]).strip(),
                                                       helper.EPG_MAX_TITLE)) for c in sweep]
        self.assertEqual(len([t for t in old if leaked(t)]), len(sweep))
        self.assertEqual([c["why"] for c in sweep if leaked(helper.redact_urls(c["raw"]))], [])


class FoldSpaceTest(unittest.TestCase):
    def test_every_fold_vector(self):
        bad = [(v["why"], helper.fold_space(v["text"])) for v in FIXTURE["fold"]
               if helper.fold_space(v["text"]) != v["folded"]]
        self.assertEqual(bad, [])

    def test_the_vectors_are_the_rule(self):
        self.assertEqual([v["why"] for v in FIXTURE["fold"] if fold_reference(v["text"]) != v["folded"]], [])

    def test_the_cleaners_fold_with_it(self):
        text = "  A" + NB + " x://b" + NB + "c" + DEL + "d\t" + NB + " "
        self.assertEqual(helper.clean_title(text), "A x://b" + NB + "c" + REPL + "d")
        # The redaction keeps the host, U+00A0 and all, and the plain fold
        # after it makes that a space: no credential is left for it to split.
        self.assertEqual(helper.clean_detail(text, 400), "A x://b c" + REPL + "d")

    def test_clean_field_keeps_the_plain_fold_for_text_already_redacted(self):
        # clean_detail's last step and the xmltv_ns episode: no credential
        # is left in either for a fold to split.
        self.assertEqual(helper.clean_field("x://b" + NB + "c" + DEL + "d", 400), "x://b c d")


class RuleTest(unittest.TestCase):
    """fold_space against the rule as stated, over random texts built from
    the characters it tells apart."""

    # A non-ASCII letter and digit, `.`, `-` and an upper-case letter: the
    # scheme-letter test is ASCII, as both redactors' scheme is (the
    # recheck: a mutation to str.isalpha survived without them).
    ALPHABET = ["a", "h", "H", "1", "+", ".", "-", "_", ":", "/", " ", "\t", "\n", "\x00", "\x0b", "\x1f", DEL, NEL,
                CSI, NB, LS, PS, chr(0x3000), chr(0xfeff), chr(0xe9), chr(0x430), chr(0x661), "@", "://", ":/",
                "http://", "1://", ":" + DEL + "//", "/" + NEL + "/", "x:/\t/"]

    def test_the_fold_is_the_rule(self):
        rng = random.Random(79)
        for _ in range(40000):
            text = "".join(rng.choice(self.ALPHABET) for _ in range(rng.randint(0, 16)))
            self.assertEqual(helper.fold_space(text), fold_reference(text), repr(text))


class RecordTest(unittest.TestCase):
    """The guide's records separate fields with NUL and U+001F and records
    with DEL, and json.dumps escapes none of DEL: so no cleaned text may hold
    one, and fold_space replaces them inside a URL rather than keeping them;
    nor a line or paragraph separator, which breaks a guide row's line."""

    def test_a_control_inside_a_url_leaves_the_record_whole(self):
        cases = []
        for c in (DEL, NEL):
            for field in ("title", "desc", "category"):
                cases.append({"field": field, "raw": "News http://qqqqqq:zz%szz@cdn.test/x tail" % c})
        stored = stored_fields(cases)
        self.assertEqual(stored, ["News http://qqqqqq:zz" + REPL + "zz@cdn.test/x tail", "News http://cdn.test tail",
                                  "News http://cdn.test tail"] * 2)

    def test_the_other_fields_stay_where_they_are(self):
        title = "News http://qqqqqq:zz" + DEL + "zz@cdn.test/x tail"
        document = ('<?xml version="1.0" encoding="UTF-8"?><tv><channel id="a.tv"><display-name>A</display-name>'
                    '</channel><programme start="%s" stop="%s" channel="a.tv"><title>%s</title><desc>D</desc>'
                    '<category>C</category><episode-num system="onscreen">E</episode-num></programme>'
                    '<programme start="%s" stop="%s" channel="a.tv"><title>Next</title></programme></tv>'
                    % (time.strftime("%Y%m%d%H%M%S +0000", time.gmtime(NOW + 60)),
                       time.strftime("%Y%m%d%H%M%S +0000", time.gmtime(NOW + 120)), title,
                       time.strftime("%Y%m%d%H%M%S +0000", time.gmtime(NOW + 120)),
                       time.strftime("%Y%m%d%H%M%S +0000", time.gmtime(NOW + 180)))).encode("utf-8")
        records = helper.parse_xmltv(helper.open_xml_stream(document), NOW, None)["channels"]["a.tv"]
        got = [helper.record_to_dict(r) for r in records.split(helper.EPG_RECORD_SEP)]
        self.assertEqual([(d["title"], d.get("desc"), d.get("category"), d.get("episode")) for d in got],
                         [("News http://qqqqqq:zz" + REPL + "zz@cdn.test/x tail", "D", "C", "E"),
                          ("Next", None, None, None)])

    def test_retain_folds_a_separator_without_splitting_a_url(self):
        # No cleaner lets one through (below); retain_programme folds one
        # all the same, and now the same way, so the URL stays whole.
        item = helper.retain_programme(NOW, NOW + 60, "News http://qqqqqq:zz\x1fzz@cdn.test/x tail",
                                       {"desc": "A\x00B http://qqqqqq:zz\x00zz@cdn.test/x"})
        blob, _ = helper.encode_retained([item])
        d = helper.record_to_dict(blob)
        self.assertEqual((d["title"], d["desc"]),
                         ("News http://qqqqqq:zz" + REPL + "zz@cdn.test/x tail",
                          "A B http://qqqqqq:zz" + REPL + "zz@cdn.test/x"))

    def test_no_cleaner_lets_a_separator_through(self):
        controls = [chr(cp) for cp in range(0x110000) if not 0xd800 <= cp <= 0xdfff
                    and (folds(chr(cp)) or is_control(chr(cp)))]
        self.assertIn(LS, controls)
        self.assertGreater(len(controls), 80)
        bad = []
        for c in controls:
            # Outside a URL, inside its `://`, after it, and at its end; and
            # with the mark intact, since a code point that is no mark filler
            # (U+2028, U+2029) breaks the mark in the first text, so no run
            # starts there for the run's rule to be seen (the recheck).
            for text in ("A" + c + "B http:" + c + "//qqqqqq:zz" + c + "zz@cdn.test/x" + c + "tail",
                         "A" + c + "B http://qqqqqq:zz" + c + "zz@cdn.test/x" + c + "tail"):
                for name, out in (("clean_title", helper.clean_title(text)),
                                  ("clean_detail", helper.clean_detail(text, helper.EPG_MAX_DESC)),
                                  ("fold_space", helper.fold_space(text))):
                    if "\x00" in out or "\x1f" in out or DEL in out or LS in out or PS in out:
                        bad.append((hex(ord(c)), name, repr(out)))
        self.assertEqual(bad, [])


class LinearTest(unittest.TestCase):
    """fold_space runs on every programme's title and details. Four times
    the text may cost at most eight times the time plus 2 ms, best of five,
    in this thread's CPU time; a search restarted from the start of the text,
    or from the start of a run, costs sixteen times."""

    SHAPES = [lambda n: "a://b " * (n // 6),
              lambda n: "a://" + (DEL + NEL + "b") * (n // 3),
              lambda n: NB * n + "a://b",
              lambda n: ":/" * (n // 2),
              lambda n: ":" * n + "/",
              lambda n: (":" + DEL) * (n // 2) + "/",
              lambda n: "a://" + NB * n,
              lambda n: ("x:" + DEL + "/" + CSI + "/y ") * (n // 8),
              lambda n: "1" * n + "://x",
              lambda n: "1://" * (n // 4),
              lambda n: ("1" * 7 + ":/" + DEL + "/") * (n // 11)]

    def best(self, text):
        times = []
        for _ in range(5):
            t0 = time.thread_time()
            helper.fold_space(text)
            times.append(time.thread_time() - t0)
        return min(times)

    def test_the_fold_is_linear_on_every_shape(self):
        for shape in self.SHAPES:
            small, large = self.best(shape(8000)), self.best(shape(32000))
            self.assertLess(large, 8 * small + 0.002, repr(shape(16)[:16]))



class GuideRulesTest(unittest.TestCase):
    """A window the old fold wrote is refetched once. The window records the
    rules it was written under (`guideRules`, GUIDE_RULES), and the fetch run
    refetches one written under older rules, or under none, whatever its
    age. The playlist's own stamp (DESTINATION_RULES) refetches the playlist
    when its source is active, and the guide run beside it read the old
    window as fresh until the next refresh, up to refreshMinutes later."""

    def run_verb(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = helper.main(list(args))
        return code, json.loads(out.getvalue().strip().splitlines()[-1]), err.getvalue()

    def test_a_window_written_before_the_fold_is_refetched_once(self):
        with tempfile.TemporaryDirectory() as cache:
            playlist = os.path.join(HERE, "fixtures", "epg-channels.m3u")
            self.assertEqual(self.run_verb("playlist", "--url", playlist, "--cache-dir", cache)[0], 0)
            epg = ("epg", "--url", os.path.join(HERE, "fixtures", "epg-basic.xml"), "--cache-dir", cache,
                   "--now", str(NOW))
            seen = [self.run_verb(*epg)[1]["fromCache"], self.run_verb(*epg)[1]["fromCache"]]
            window = os.path.join(cache, helper.EPG_WINDOW_FILE)
            with open(window, encoding="utf-8") as fh:
                head, _, body = fh.read().partition("\n")
            meta = json.loads(head)
            # As a helper before the fold wrote it.
            seen.append(meta.pop("guideRules", None))
            with open(window, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(meta) + "\n" + body)
            seen += [self.run_verb(*epg)[1]["fromCache"], self.run_verb(*epg)[1]["fromCache"]]
            self.assertEqual(seen, [False, True, helper.GUIDE_RULES, False, True])

    def test_a_window_stamped_under_older_or_damaged_rules_is_refetched_once(self):
        # The review's F19: the comparison, not only the key's presence. The
        # next bump of GUIDE_RULES leaves every window stamped with the one
        # before it; a stamp coerce_int reads as no whole number of the
        # current rules (a word, null, a list) is read as older rules. (A
        # number-like "1" or true reads as 1, current; 1e400 is no stamp at
        # all -- load_window refuses its Infinity meta line, so that window
        # is refetched as damaged, not by this comparison.)
        for stamp in (helper.GUIDE_RULES - 1, 0, -1, "x", None, [helper.GUIDE_RULES], 1e400):
            with self.subTest(stamp=stamp), tempfile.TemporaryDirectory() as cache:
                playlist = os.path.join(HERE, "fixtures", "epg-channels.m3u")
                self.assertEqual(self.run_verb("playlist", "--url", playlist, "--cache-dir", cache)[0], 0)
                epg = ("epg", "--url", os.path.join(HERE, "fixtures", "epg-basic.xml"), "--cache-dir", cache,
                       "--now", str(NOW))
                self.assertEqual(self.run_verb(*epg)[1]["fromCache"], False)
                window = os.path.join(cache, helper.EPG_WINDOW_FILE)
                with open(window, encoding="utf-8") as fh:
                    head, _, body = fh.read().partition("\n")
                meta = json.loads(head)
                meta["guideRules"] = stamp
                with open(window, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(meta) + "\n" + body)
                self.assertEqual([self.run_verb(*epg)[1]["fromCache"], self.run_verb(*epg)[1]["fromCache"]],
                                 [False, True])


if __name__ == "__main__":
    unittest.main()
