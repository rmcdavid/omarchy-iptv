"""D-EPG-16 (2026-10-29): one programme's episode number cannot end the
guide fetch.

episode_ns_text took a field as a number when str.isdigit() said so, and
isdigit() is True for superscripts and circled digits, which int() refuses:
ONE `<episode-num system="xmltv_ns">` whose season was a superscript two
raised ValueError out of parse_xmltv, and every fetch of that guide ended in
main()'s `internal`, its guide never loaded. Found by D-LOGO-24's rule-15
sweep ("every per-item loop where one item's exception ends the run").

Now the field must be isdecimal(), exactly the characters int() reads: a
number that rendered before renders the same (ASCII and other decimal
digits alike), and the rest are dropped, as the docstring always said.
"""
import calendar
import contextlib
import io
import json
import os
import tempfile
import unittest
import unittest.mock

from helper_loader import load_helper

helper = load_helper()
NOW = calendar.timegm((2026, 9, 12, 21, 0, 0, 0, 0, 0))


def guide(episode):
    return ('<?xml version="1.0" encoding="UTF-8"?><tv>'
            '<programme channel="a.tv" start="20260912203000 +0000" stop="20260912213000 +0000">'
            '<title>Plain</title></programme>'
            '<programme channel="b.tv" start="20260912203000 +0000" stop="20260912213000 +0000">'
            '<title>Numbered</title><episode-num system="xmltv_ns">%s</episode-num></programme></tv>' % episode)


class EpisodeDigitsTest(unittest.TestCase):
    def test_a_number_int_cannot_read_is_dropped_not_raised(self):
        for raw, want in (("\u00b2.3.", "E4"), ("1.\u00b3.", "S2"), ("\u2460.1.", "E2"), ("\u00b9\u00b2.0.", "E1")):
            with self.subTest(raw=raw):
                self.assertEqual(helper.episode_ns_text(raw), want)

    def test_every_number_that_rendered_before_renders_the_same(self):
        self.assertEqual(helper.episode_ns_text("0.1."), "S1 E2")
        self.assertEqual(helper.episode_ns_text("2/5.9/10.0/1"), "S3 E10")
        # Other decimal digits: int() reads them, and so does this.
        self.assertEqual(helper.episode_ns_text("\u0661.\u0662."), "S2 E3")
        self.assertEqual(helper.episode_ns_text("\uff11.\uff12."), "S2 E3")
        self.assertEqual(helper.episode_ns_text("\u00b2.4."), "E5")

    def test_the_verb_loads_the_guide_and_keeps_the_rest_of_the_programme(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "guide.xml")
            with open(source, "w", encoding="utf-8") as handle:
                handle.write(guide("\u00b2.3."))
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = helper.main(["epg", "--url", source, "--cache-dir", tmp, "--now", str(NOW)])
            status = json.loads(out.getvalue().strip().splitlines()[-1])
            self.assertEqual(code, 0, err.getvalue())
            self.assertTrue(status["ok"], status)
            with open(os.path.join(tmp, "epg-now.json"), encoding="utf-8") as handle:
                channels = json.load(handle)["channels"]
            self.assertEqual(channels["b.tv"]["now"]["title"], "Numbered")
            self.assertEqual(channels["b.tv"]["now"].get("episode"), "E4")


class IsdigitShapeSiblingTest(unittest.TestCase):
    """Rule 15 over the shape (`isdigit()` then `int()`): the one other
    place in the parts this lane owns, the fetch policy's home port. The
    shell sets it from a URL it validated, so no provider reaches it; a
    value int() cannot read is no port, never a ValueError."""

    def test_a_home_port_int_cannot_read_is_no_port(self):
        for text, want in (("\u00b2", None), ("\u2460\u2461", None), ("8080", 8080), ("0", None), ("65536", None)):
            with self.subTest(text=text):
                with unittest.mock.patch.dict(os.environ, {helper.HOME_PORT_ENV: text}):
                    self.assertEqual(helper.DestinationPolicy.from_environment("playlist").home_port, want)


if __name__ == "__main__":
    unittest.main()
