"""D-SINK-110 (2026-11-16): the helper's sinks of free text read a control
character as the guide row reads it, and remove it after the redaction.

The player's window title and media title deleted every control BEFORE the
redaction (F-SINK-14, F-SINK-16), and so did the notification body in the
shell. A control inside the port of a typo-shaped address then made a port
of digits: `News http://my.user:12<U+0001>34/pw@cdn.test/x` printed
`News http://my.user`, the username, where the guide row, which redacts the
raw text, withholds the host. log() and main()'s traceback redacted the raw
text and wrote every control they held to the journal.

tests/fixtures/shown-text.json is the one fixture both mirrors run (the node
suite runs Model.shownText over it): its vectors through shown_text and
every sink that prints with it, and its sweep -- every source text of three
fixtures with one control at every position, and five credential shapes
with two at every pair of positions -- against three properties stated in
the fixture. Each test here calls the shipping function.
"""
import contextlib
import io
import json
import os
import re
import unittest
from unittest import mock

from helper_loader import load_helper

helper = load_helper()
HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "fixtures", "shown-text.json"), "rb") as fh:
    FIXTURE_BYTES = fh.read()
FIXTURE = json.loads(FIXTURE_BYTES.decode("ascii"))
SWEEP = FIXTURE["sweep"]
CONTROLS = re.compile("[\x00-\x1f\x7f-\x9f]")
QZ_RUNS = re.compile("q+|z+")


def clean(text):
    return CONTROLS.sub("", text).replace(helper.HOST_WITHHELD, "")


def pieces(out, must):
    """The pieces `out` shows: the mustNotAppear entries in it, or, for a
    source with none, its maximal runs of `q` or `z`."""
    seen = clean(out)
    if must:
        return {m for m in must if m and m in seen}
    return set(QZ_RUNS.findall(seen))


def beyond(out, reference, must):
    """The pieces `out` shows that `reference` does not."""
    shown = clean(reference)
    return {p for p in pieces(out, must) if p not in shown}


def sources():
    """(text, must) for every source text the sweep names."""
    out = []
    for source in SWEEP["sources"]:
        with open(os.path.join(HERE, "fixtures", source["file"]), encoding="utf-8") as fh:
            rows = json.load(fh)[source["list"]]
        for row in rows:
            must = next((row[key] for key in source["must"] if row.get(key)), [])
            out.append((row[source["text"]], must))
    return out


def transparent_spans(text):
    """Where a control is read as part of a URL's mark: from each URL's
    scheme start to its first run character, as the text without its
    controls reads its URLs (next_url), in `text`'s positions."""
    kept = [i for i, ch in enumerate(text) if not CONTROLS.match(ch)]
    bare = "".join(text[i] for i in kept)

    def place(j):
        return kept[j] if j < len(kept) else len(text)
    return [(place(start), place(mark_end)) for start, _, mark_end, _ in helper.UrlReading(bare, 0, None, True).urls]


def old_reading(text):
    """The sinks' reading until D-SINK-110: the controls deleted, then the
    plain redaction. The reference property (2) holds the sink to."""
    return helper.redact_urls(helper._CONTROL_CHARS.sub("", text))


class FixtureTest(unittest.TestCase):
    def test_the_fixture_is_ascii_and_whole(self):
        self.assertTrue(all(b < 0x80 for b in FIXTURE_BYTES))
        self.assertGreaterEqual(len(FIXTURE["vectors"]), 21)
        self.assertGreaterEqual(len([v for v in FIXTURE["vectors"] if "typo-shaped" in v["why"]]), 5)
        self.assertEqual(len(SWEEP["controls"]), 9)
        self.assertTrue(set(SWEEP["nonDelimiterControls"]) < set(SWEEP["controls"]))
        self.assertFalse(set(SWEEP["nonDelimiterControls"]) & set(helper.URL_DELIMITER_CHARS))

    def test_every_vector_reads_as_the_fixture_says(self):
        bad = []
        for v in FIXTURE["vectors"]:
            for sink, got in (("shown_text", helper.shown_text(v["text"])),
                              ("player_title_text", helper.player_title_text(v["text"]))):
                if got != v["py"]:
                    bad.append((v["why"], sink, ascii(got)))
                if [m for m in v["mustNotAppear"] if m in got] or CONTROLS.search(got):
                    bad.append((v["why"], sink, "shows", ascii(got)))
        self.assertEqual(bad, [])

    def test_a_text_with_no_control_is_the_plain_redaction(self):
        for text, _ in sources():
            if not CONTROLS.search(text):
                self.assertEqual(helper.shown_text(text), helper.redact_urls(text), ascii(text))

    def test_the_reading_is_idempotent_on_the_vectors(self):
        for v in FIXTURE["vectors"]:
            self.assertEqual(helper.shown_text(v["py"]), v["py"], v["why"])


class SweepTest(unittest.TestCase):
    """The fixture's sweep through the window title's shipping sink."""

    @classmethod
    def setUpClass(cls):
        cls.failures = {"1": [], "2": [], "3": []}
        cls.counts = {"one": 0, "pairs": 0, "property3": 0}
        delimiters = set(SWEEP["controls"]) - set(SWEEP["nonDelimiterControls"])
        for text, must in sources():
            plain_base = helper.redact_urls(text)
            for control in SWEEP["controls"]:
                for pos in range(len(text) + 1):
                    cls.judge(text[:pos] + control + text[pos:], must, plain_base, delimiters)
                    cls.counts["one"] += 1
        pairs = SWEEP["pairs"]
        for base in pairs["bases"]:
            for i in range(len(base) + 1):
                for j in range(i, len(base) + 1):
                    for first in pairs["controls"]:
                        for second in pairs["controls"]:
                            cls.judge(base[:i] + first + base[i:j] + second + base[j:], [], None, delimiters)
                            cls.counts["pairs"] += 1

    @classmethod
    def judge(cls, text, must, plain_base, delimiters):
        out = helper.player_title_text(text)
        if must and pieces(out, must) - pieces(plain_base, must):
            cls.failures["1"].append(text)
        if beyond(out, old_reading(text), must):
            cls.failures["2"].append(text)
        controls = [(i, ch) for i, ch in enumerate(text) if CONTROLS.match(ch)]
        if any(ch in delimiters for _, ch in controls):
            return
        spans = transparent_spans(text)
        if any(lo <= i < hi for i, _ in controls for lo, hi in spans):
            return
        cls.counts["property3"] += 1
        if beyond(out, helper.redact_urls(text), must):
            cls.failures["3"].append(text)

    def test_the_sweep_ran_whole(self):
        self.assertGreaterEqual(self.counts["one"], 100000)
        self.assertGreaterEqual(self.counts["pairs"], 37188)
        self.assertGreaterEqual(self.counts["property3"], 40000)

    def test_property_1_no_piece_the_plain_redaction_of_the_source_withholds(self):
        self.assertEqual([ascii(t) for t in self.failures["1"][:6]], [])

    def test_property_2_nothing_the_old_reading_withheld(self):
        self.assertEqual([ascii(t) for t in self.failures["2"][:6]], [])

    def test_property_3_a_non_delimiter_control_outside_every_mark_hides_what_the_row_hides(self):
        """The class D-SINK-110 closes: the control stood where the guide
        row reads it as part of the address, and the old reading deleted
        it and read another address."""
        self.assertEqual([ascii(t) for t in self.failures["3"][:6]], [])


class StderrTest(unittest.TestCase):
    """log() and main()'s traceback write what the reading prints, and no
    control reaches the journal."""

    def test_log_writes_one_line_with_no_control(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            helper.log("play: News\x1b[31m http://my.user:12\x0134/pw@cdn.test/x\x9b ended")
        line = err.getvalue()
        self.assertEqual(line, "omarchy-iptv: play: News[31m http://[host withheld] ended\n")

    def run_main(self, text):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(helper, "cmd_clipboard", side_effect=ValueError(text)), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = helper.main(["clipboard"])
        return code, json.loads(out.getvalue().strip().splitlines()[-1]), err.getvalue()

    def test_the_traceback_keeps_its_lines_and_loses_its_controls(self):
        code, payload, stderr = self.run_main("Ctl\x1b[2J News http://my.user:12\x0134/pw@cdn.test/x")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "internal")
        self.assertIn("Traceback (most recent call last):\n", stderr)
        self.assertTrue(stderr.endswith("ValueError: Ctl[2J News http://[host withheld]\n"), ascii(stderr[-120:]))
        self.assertIsNone(re.search("[\x00-\x09\x0b-\x1f\x7f-\x9f]", stderr), ascii(stderr[-120:]))
        self.assertNotIn("my.user", stderr)

    def test_the_traceback_is_read_whole_so_a_token_across_a_line_is_withheld(self):
        """A credential token ends only at a space, so the old whole-text
        redaction withheld `qqqqqq:zz<LF>zz@cdn.test`; reading the traceback
        one line at a time printed `qqqqqq:zz`."""
        _, _, stderr = self.run_main("x qqqqqq:zz\nzz@cdn.test y\x7f")
        self.assertTrue(stderr.endswith("ValueError: x [host withheld] y\n"), ascii(stderr[-120:]))
        self.assertNotIn("qqqqqq", stderr)

    def test_shown_lines_keeps_a_line_feed_and_drops_every_other_control(self):
        self.assertEqual(helper.shown_lines("a\x1b[1m\nb\tc\r\nd"), "a[1m\nbc\nd")
        self.assertEqual(helper.shown_lines("x\nhttp://qqqqqq:zzzzzz@cdn.test/y\x01\nz"), "x\nhttp://cdn.test\nz")


if __name__ == "__main__":
    unittest.main()
