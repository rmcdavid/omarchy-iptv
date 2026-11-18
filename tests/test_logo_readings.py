"""D-LOGO-30: the parse keeps a channel's logo only where its reading of the
logo's scheme and the survey's both say http or https.

make_channel stored a `tvg-logo` when urlsplit read its scheme as http or
https (stream_scheme). urlsplit deletes a TAB, CR and LF anywhere and strips
C0 controls and spaces off the front before it reads a scheme; the logo
survey, its slot and the fetch read the scheme as written (logo_scheme,
Model.logoScheme, D-SINK-112). So `ht<TAB>tp://l.test/a.png` and
`<U+0001>http://l.test/a.png` were stored, counted refused by every survey
and never fetched. The lead's call under the owner's standing authority of
2026-11-09: a logo is kept only where both readings say web; nothing that
was not kept before is kept now. LogoSchemeShortcutTest
(tests/test_parse_margin.py) holds logo_is_web to the two readings over
every shape it sweeps; this file holds it to literals, and the parse to
which rows keep a logo and what it says about the rest.

Control characters are built with chr() or as escapes: these sources are
ASCII.
"""
import unittest

from helper_loader import load_helper

helper = load_helper()

TAB, CR, SOH = "\t", "\r", chr(1)
FULLWIDTH_SOLIDUS = chr(0xFF0F)


class LogoIsWebLiteralTest(unittest.TestCase):
    """The slow path's classes, each answer written down rather than
    computed: a test that asked the two readings for its expectation would
    pass whatever the readings said."""

    CASES = (
        # Both readings say http or https.
        ("http://l.test/a.png", True),
        ("HTTPS://l.test/a.png", True),
        ("Https://l.test/a.png", True),
        ("http://l.test/a" + TAB + "b.png", True),        # a TAB after the scheme
        ("http:" + CR + "//l.test/a.png", True),          # a CR after the scheme's colon
        ("http://[::1]/a.png", True),                     # a well-formed bracketed literal
        ("http://l" + chr(0xE9) + ".test/a.png", True),   # a netloc NFKC leaves alone
        # urlsplit reads http, the scheme as written is none (D-LOGO-30).
        ("ht" + TAB + "tp://l.test/a.png", False),
        ("ht" + CR + "tp://l.test/a.png", False),
        ("http" + TAB + "s://l.test/a.png", False),
        (SOH + "http://l.test/a.png", False),
        (SOH + " http://l.test/a.png", False),
        (" http://l.test/a.png", False),                  # parse_attrs strips it first ("Space Ahead")
        (chr(0) + "https://l.test/a.png", False),
        (chr(0x1B) + "http://l.test/a.png", False),
        # The scheme as written is http, and urlsplit refuses the netloc.
        ("http://[::1/a.png", False),
        ("http://::1]/a.png", False),
        ("http://x[::1]/a.png", False),
        ("http://l" + FULLWIDTH_SOLIDUS + "x.test/a.png", False),
        # Neither says web.
        ("ftp://l.test/a.png", False),
        ("//l.test/a.png", False),
        ("l.test/a.png", False),
        ("http", False),
        ("h" + chr(0x130) + "ttp://l.test/a.png", False),
        ("", False),
    )

    def test_each_logo_keeps_its_written_answer(self):
        for logo, web in self.CASES:
            self.assertEqual(helper.logo_is_web(logo), web, ascii(logo))
        # The refused cases read as web to ONE reading or the other, both
        # halves represented, so dropping either half of logo_is_web moves
        # an answer in this table.
        split_only = [logo for logo, web in self.CASES
                      if not web and helper.stream_scheme(logo) in ("http", "https")]
        written_only = [logo for logo, web in self.CASES
                        if not web and helper.logo_scheme(logo) in ("http", "https")]
        self.assertEqual((len(split_only), len(written_only)), (8, 4), (split_only, written_only))
        self.assertFalse(set(split_only) & set(written_only))


def entry(logo, name, n):
    return ['#EXTINF:-1 tvg-logo="%s",%s' % (logo, name), "http://s.test/%d.ts" % n]


class ParseKeepsWhatBothReadTest(unittest.TestCase):
    """parse_m3u over a local list: which rows keep a logo, exactly, and the
    over-length count, which only a logo the parse would keep enters."""

    LONG_TAIL = "x" * (helper.M3U_MAX_LOGO_URL + 10)
    ENTRIES = (
        ("ht" + TAB + "tp://l.test/a.png", "Tab In Scheme", None),
        (SOH + "http://l.test/a.png", "Control Ahead", None),
        (SOH + " http://l.test/a.png", "Control And Space Ahead", None),
        # What urlsplit strips past parse_attrs' own strip: a run of
        # characters at or below U+0020 that opens with a C0 control that is
        # not whitespace, whatever follows it in the run (the review of
        # 7c5b53a).
        (SOH + TAB + "http://l.test/a.png", "Control And Tab Ahead", None),
        (SOH + chr(0x0B) + "http://l.test/a.png", "Control And Vertical Tab Ahead", None),
        (SOH + chr(0x1C) + "http://l.test/a.png", "Control And Separator Ahead", None),
        (SOH + chr(0x02) + "http://l.test/a.png", "Two Controls Ahead", None),
        ("ht" + CR + "tp://l.test/a.png", "Return In Scheme", None),
        (" http://l.test/b.png", "Space Ahead", "http://l.test/b.png"),
        ("http://[::1/a.png", "Bracket Refused", None),
        ("http://l.test/c.png", "Plain Http", "http://l.test/c.png"),
        ("HTTP://l.test/c.png", "Upper Http", "HTTP://l.test/c.png"),
        ("https://l.test/d.png", "Plain Https", "https://l.test/d.png"),
        ("HTTPS://l.test/d.png", "Upper Https", "HTTPS://l.test/d.png"),
        ("http://l.test/e" + TAB + "f.png", "Tab In Path", "http://l.test/e" + TAB + "f.png"),
        ("ht" + TAB + "tp://l.test/" + LONG_TAIL, "Long Tab In Scheme", None),
        ("http://l.test/" + LONG_TAIL, "Long Plain", None),
    )

    def parse(self):
        lines = ["#EXTM3U"]
        for n, (logo, name, _) in enumerate(self.ENTRIES):
            lines += entry(logo, name, n)
        return helper.parse_m3u("\n".join(lines) + "\n", helper.playlist_source("file", ""))

    def test_a_row_keeps_its_logo_only_where_both_readings_say_web(self):
        result = self.parse()
        rows = {row["name"]: row for row in result["channels"]}
        self.assertEqual(len(rows), len(self.ENTRIES))
        for logo, name, kept in self.ENTRIES:
            self.assertEqual(rows[name].get("logo"), kept, "%s: %s" % (name, ascii(logo)))

    def test_only_a_logo_the_parse_would_keep_is_counted_over_length(self):
        result = self.parse()
        self.assertEqual(result["warnings"], ["1 logo URL longer than %d characters dropped" % helper.M3U_MAX_LOGO_URL])


if __name__ == "__main__":
    unittest.main()
