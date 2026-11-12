"""D-SINK-75 (2026-11-04): no cap the helper puts on provider text cuts a URL.

The helper stores a channel's name, tvg-name and groups, and a programme's
title, AS WRITTEN, cut to a cap (D-M3U-1: 512, 512, 512 for the group text
and 128 for each group; EPG_MAX_TITLE: 200), and every sink redacts them
later: the window title through redact_urls, the guide, the bar, the bus and
the notifications through Model.sinkText. A cut that lands between a URL's
`//` and its `@` leaves `http://myuser:S3CRETpw` with no `@`, which both
redactors read as the host `myuser`, and print. clean_detail already dropped
such a cut token (F-M4-1); the caps in front of the other sinks did not.
cut_free_text is the one rule now.

The leak is a property of ONE cut offset, so these sweep every offset of the
cut across each URL shape, at every cap, through the shipping parsers, and
hold what they store to four sinks: the two redactors as they are, and the
two compositions that delete control characters before they redact (the
player's title, player_title_text, and the shell's notification body,
Model.notifyArgv), where a tab inside a URL does not end its run. The
credential is spelt in letters nothing else here holds (`q` and `z`), so ANY
fragment of it in an output is a leak, the username's first letter included.

D-SINK-95 and D-SINK-96 (2026-11-11): the run is also dropped when the part
the cut keeps holds a mark the redactors' reading finds behind a scheme, or
a scheme-less token's `:` without the `@` after it (CutSweepTest).

The review of cbd6679 (2026-11-12): the cut drops back no further than the
start of the item it would cut -- the run's first URL, when the cut keeps its
mark, or the run's credential (url_reading_rule), when the cut loses its
`@` -- with a space just before it, so a space-less Chinese or Japanese
description keeps the prose before a false positive where the first version
stored it empty (ProseCutTest), and the sinks that delete controls read the
start the cut drops to (DeletingStartTest).
"""
import calendar
import json
import os
import subprocess
import time
import unittest

import url_reading_rule as rule
from helper_loader import load_helper

helper = load_helper()
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = calendar.timegm((2026, 9, 12, 21, 0, 0, 0, 0, 0))

PLAIN = "http://qqqqqq:zzzzzz@cdn.test/live/1.ts"
# Every printable ASCII character that is neither a letter nor a digit, DEL,
# and eight that are not ASCII, inside the password. Only the six ASCII
# delimiters end a redactor's run (R32a'''), so each of these is URL text to
# both, and a cut that also ended a run at any of them shows. With `/`, `?` or
# `#` the authority ends early, and the URL is withheld whole (R32a') only
# while its later `@` is there.
PASSWORD_CHARS = ([c for c in map(chr, range(0x21, 0x7f)) if not c.isalnum()]
                  + [chr(x) for x in (0x7f, 0x85, 0x9b, 0xa0, 0xe9, 0x200b, 0x2028, 0x3000, 0xfeff)])
# A scheme as both redactors read one, a letter and then letters, digits, `+`,
# `.` or `-`, in either case: glued to a digit before it (D-SINK-74), in upper
# case, ending in a digit, holding a `+`, and one no stream uses.
SCHEMES = ["1http://qqqqqq:zzzzzz@cdn.test/x", "HTTP://qqqqqq:zzzzzz@cdn.test/x",
           "s3://qqqqqq:zzzzzz@bucket.test/x", "git+ssh://qqqqqq:zzzzzz@cdn.test/x",
           "smb://qqqqqq:zzzzzz@nas.test/x"]
# D-SINK-78: a `;` at every other place in a userinfo, and the credentials
# a provider writes into a URL's path or query (Xtream's /live/<user>/<pass>/
# and get.php?username=&password=), with a `;` and without. Every redactor
# reads a `;` as URL text, and the group text's split now does too.
PLACES = ["http://qq;qq:zzzzzz@cdn.test/x", "http://qqqqqq;:zzzzzz@cdn.test/x",
          "http://qqqqqq:;zzzzzz@cdn.test/x", "http://qqqqqq:zzzzzz;@cdn.test/x",
          "http://;qqqqqq:zzzzzz@cdn.test/x", "http://qqqqqq:z;z;z@cdn.test/x",
          "http://cdn.test/live/qqqqqq/zzzzzz/1.ts", "http://cdn.test/live/qqqqqq/zz;zz/1.ts",
          "http://cdn.test/get.php?username=qqqqqq&password=zzzzzz",
          "http://cdn.test/get.php?username=qqqqqq&password=zz;zz"]
SHAPES = [PLAIN] + SCHEMES + ["http://qqqqqq:zz%szz@cdn.test/x" % c for c in PASSWORD_CHARS] + PLACES
# A control character inside the URL: the player's title and the notification
# delete it and read one run, and there the cut is what decides. At the plain
# redactors a tab, VT, FF or CR inside a password ends the run whether or not
# anything is cut (D-SINK-34's accepted cost), and a URL with a control inside
# its `://` is no URL at all, so these are held to the two control-deleting
# sinks only. The last seven are `://` only once the control is deleted, one
# from each part of the class both mirrors delete: NUL, SOH, a tab and U+001F
# of C0, DEL, and two C1 controls.
JOINED_SHAPES = [
    "http://qqqqqq:zz\tzz@cdn.test/x",
    "http://qq\x0bqq\x0cqq:zz\rzz@cdn.test/x",
    "http:\x00//qqqqqq:zzzzzz@cdn.test/x",
    "http:/\x01/qqqqqq:zzzzzz@cdn.test/x",
    "http:/\t/qqqqqq:zzzzzz@cdn.test/x",
    "http:/\x1f/qqqqqq:zzzzzz@cdn.test/x",
    "http:\x7f//qqqqqq:zzzzzz@cdn.test/x",
    "http:/\x85/qqqqqq:zzzzzz@cdn.test/x",
    "http:/\x9b/qqqqqq:zzzzzz@cdn.test/x",
]
# What each field's own parse splits. A title, description, category or
# episode is cut after the guide's whitespace fold (fold_space's). The title
# sweeps left out every shape the old fold changed until D-SINK-79, because a
# title is cut after it, and that exclusion was the defect a third time: the
# old fold turned a non-ASCII space, DEL or U+0085 inside a URL into a space
# and split it before any redactor read it. The fold keeps a URL's run whole
# now, so they take every shape. The group
# sweeps left out every shape with a `;` until D-SINK-78, because the stored
# groups were split at every `;`, and that exclusion was the defect: a `;`
# after a `://` in its run splits nothing now (split_groups). The attribute
# sweeps (the tvg-name, the group-title) left out every shape with a `"`
# until D-SINK-80, "because an attribute ends at its `"`", and that exclusion
# was the defect again: the cut attribute's tail became the channel's NAME,
# which these sweeps never held to a sink. A `"` inside a URL's run ends no
# value now (parse_attrs), so they take every shape, and hold the name too:
# a value whose URL's run a space ends before any closing quote is
# unterminated, and the whole attribute text, URL whole, is the name
# (unterminated() below). 57 shapes through each of the four.
ATTR_SHAPES = SHAPES
GROUP_SHAPES = SHAPES
EXTGRP_SHAPES = SHAPES
TITLE_SHAPES = SHAPES
SECRET = "qz"


def leaked(text):
    return [c for c in SECRET if c in text]


def deleted(text):
    """`text` without the controls both mirrors delete before they redact:
    C0, DEL and C1."""
    return "".join(c for c in text if not (ord(c) < 0x20 or 0x7f <= ord(c) <= 0x9f))


def credential_before(source, cap):
    """What a cut at `cap` keeps of `source` when it loses the `@` of the
    credential in the run it cuts (url_reading_rule): the text before the
    credential's span, a space just before it taken; or None."""
    if len(source) <= cap or source[cap] == " ":
        return None
    start = source.rfind(" ", 0, cap) + 1
    end = source.find(" ", cap)
    end = len(source) if end < 0 else end
    found = rule.credential(source, start, end, rule.urls(source))
    if found is None or found[1] < cap or found[2] >= cap:
        return None
    return source[:found[2] - 1 if found[2] > 0 and source[found[2] - 1] == " " else found[2]]


def forms(cap, shapes, fold=False):
    """(text, kept) for every cut of each shape at `cap`. The URL comes after
    a space, after a space behind words joined by C1 controls (which no fold
    touches), after a tab, and glued to the text before it, so the cut is one
    run. The pad also starts a few characters early and ends a few late, so
    the cut lands just before the URL and just after it as well. It is never
    empty, since every field trims its text before the cut.

    `kept` is (a prefix, a URL) the stored value must hold, from where the cut
    lands: before the URL's `://` is whole, all the cut text; past the URL,
    that with the URL whole; in between, what comes before the URL's run --
    the text before its space, or nothing when no space comes before the URL.
    `fold` is a guide field's, which reads a tab before a URL as a space and
    writes U+FFFD for DEL, U+0085, U+2028 and U+2029 in the URL's run after
    its `://` (fold_space; the review's F9 and F11). The glued form's
    run never ends, so it keeps its cut text only while that holds no
    `://`."""
    joined = "N\x80N\x9b"
    out = []
    for url in shapes:
        # The guide's fold keeps a URL's run whole and writes U+FFFD for the
        # controls in it that it folds elsewhere, and for the line separators
        # (D-SINK-79; every shape here holds them after its `://`).
        kept_url = "".join(chr(0xfffd) if c in "\x7f\x85\u2028\u2029" else c for c in url) if fold else url
        for pad in range(max(1, cap - len(url) - 3), cap + 2):
            for head, sep in (("N" * pad, " "), ((joined * pad)[:pad], " "), ("N" * pad, "\t")):
                text = head + sep + url + " tail"
                cut = (head + " " + kept_url + " tail" if fold else text)[:cap]
                whole = kept_url if len(head) + 1 + len(kept_url) <= cap else ""
                if whole or "://" not in deleted(cut[len(head) + 1:]):
                    before = cut
                elif cut[len(head)] == " ":
                    before = head
                else:
                    before = ""
                held = None if whole else credential_before(head + " " + kept_url + " tail" if fold else text, cap)
                if held is not None:
                    before = held
                out.append((text, (before.rstrip(), whole)))
            text = "N" * pad + url + "tail"
            seen = "N" * pad + kept_url + "tail"
            held = credential_before(seen, cap)
            out.append((text, ("" if "://" in deleted(seen[:cap]) else (seen[:cap] if held is None else held).rstrip(), "")))
    return out


def kept_in(raw, at, url, cap):
    """forms()'s `kept` for a stored text `raw` that holds `url` at `at`,
    after a space or a tab, cut at `cap`: before the URL's `://` is whole,
    all the cut text; past the URL, that with the URL whole; in between,
    what comes before the URL's run -- the text before its space, or nothing
    when a tab comes before the URL and no space before that. Read off the
    raw text, never off a parse."""
    cut = raw[:cap]
    whole = url if at + len(url) <= cap else ""
    if whole or "://" not in deleted(cut[at:]):
        before = cut
    elif cut[at - 1] == " ":
        before = cut[:at - 1]
    else:
        before = ""
    return before.rstrip(), whole


# The shapes a quoted attribute can leave unterminated: those holding a `"`.
QUOTED_SHAPES = [s for s in SHAPES if '"' in s]


def unterminated(text):
    """(shape, where) when a quoted attribute holding a forms() `text` is
    unterminated (D-SINK-80, parse_attrs): its shape's `"` is inside the
    URL's run, which the space before " tail" ends with no `"` before it that
    a delimiter, a `,` or the end follows. A glued text's run reaches the
    attribute's own closing `",`, so it is not."""
    for url in QUOTED_SHAPES:
        at = text.find(url)
        if at > 0 and text[at - 1] in " \t":
            return url, at
    return None


def attribute_route(test, cases, rows, prefix, suffix, field, own):
    """Split a sweep's rows by where the attribute's text went: the field
    (`field(row)`, with forms()' `kept`), or for an unterminated value the
    name, which then holds `prefix + text + suffix` -- the attribute as
    written and the title after it -- cut at the name's cap, and the
    attribute's own stored value (`own(row)`) nothing.
    -> (field values, their kept, names, their kept)."""
    values, kept, names, names_kept = [], [], [], []
    for (text, k), row in zip(cases, rows):
        spot = unterminated(text)
        if spot is None:
            values.append(field(row))
            kept.append(k)
            continue
        url, at = spot
        test.assertIn(own(row), ("", helper.UNGROUPED), text[-60:])
        names.append(row["name"])
        names_kept.append(kept_in(prefix + text + suffix, len(prefix) + at, url, helper.M3U_MAX_NAME))
    return values, kept, names, names_kept


def shell_sinks(values):
    """Model.sinkText and the body Model.notifyArgv posts for a stream that
    did not play, over `values`, in node: the shell's own compositions."""
    script = ('const M=require("./Model.mjs");'
              'const v=JSON.parse(require("fs").readFileSync(0,"utf8"));'
              'process.stdout.write(JSON.stringify(v.map(x=>{'
              'const a=M.notifyArgv("streamFailed",{name:x,reason:"r"});'
              'return [M.sinkText(x),a[a.length-1]]})))')
    done = subprocess.run(["node", "-e", script], input=json.dumps(values), capture_output=True,
                          text=True, cwd=ROOT, timeout=120)
    if done.returncode != 0:
        raise AssertionError(done.stderr[-800:])
    return json.loads(done.stdout)


def held_to_every_sink(test, values, cap, kept=None, plain=True):
    """Each stored value is at most `cap` long, keeps what it must, and no
    sink prints any letter of the credential from it. `plain` False leaves
    out the two redactors that read controls as they are (JOINED_SHAPES)."""
    bad = []
    shell = shell_sinks(values)
    for i, (value, (shown, body)) in enumerate(zip(values, shell)):
        if len(value) > cap:
            bad.append(("over the cap", len(value), value[-60:]))
        sinks = [("player_title_text", helper.player_title_text(value)), ("notifyArgv", body)]
        if plain:
            sinks += [("redact_urls", helper.redact_urls(value)), ("sinkText", shown)]
        for sink, out in sinks:
            if leaked(out):
                bad.append((sink, repr(out[-60:])))
        if kept is not None:
            before, whole = kept[i]
            if not value.startswith(before) or whole not in value:
                bad.append(("dropped too much", repr(value[-60:])))
    test.assertEqual(bad[:4], [])


class CutFreeTextTest(unittest.TestCase):
    def test_a_text_within_the_cap_is_returned_as_it_is(self):
        text = "News " + PLAIN
        self.assertEqual(helper.cut_free_text(text, len(text)), text)

    def test_a_cut_at_a_space_keeps_every_run_whole(self):
        text = "News " + PLAIN + " more"
        self.assertEqual(helper.cut_free_text(text, len("News " + PLAIN)), "News " + PLAIN)

    def test_a_cut_just_after_the_space_that_ends_a_url_keeps_it(self):
        text = "News " + PLAIN + " tail"
        self.assertEqual(helper.cut_free_text(text, len("News " + PLAIN + " ")), "News " + PLAIN + " ")

    def test_a_cut_at_any_other_delimiter_is_a_cut_inside_the_run(self):
        # The window title and the notification delete it, joining the URL
        # to what follows, so only a space keeps the URL's run whole.
        for delim in "\t\n\x0b\x0c\r":
            text = "News " + PLAIN + delim + "more"
            self.assertEqual(helper.cut_free_text(text, len("News " + PLAIN)), "News", repr(delim))

    def test_a_cut_inside_a_url_drops_its_run_and_the_space_before_it(self):
        self.assertEqual(helper.cut_free_text("News " + PLAIN, len(PLAIN)), "News")
        for delim in "\t\n\x0b\x0c\r":
            # Not a run end, so the run reaches back to the text's start,
            # and the cut drops back to the URL's start, the delimiter kept
            # (the review of cbd6679: no further than the item it cuts; the
            # callers trim it).
            self.assertEqual(helper.cut_free_text("News" + delim + PLAIN, len(PLAIN)), "News" + delim, repr(delim))

    def test_the_run_reaches_back_past_a_no_break_space(self):
        # URL text to the redactors (R32a'''), so the run starts at the space,
        # and the cut drops back to the URL's start, which the no-break space
        # is no part of (the review of cbd6679: no further than the item it
        # cuts).
        text = "Live News" + chr(0xa0) + PLAIN
        self.assertEqual(helper.cut_free_text(text, len(text) - 20), "Live News" + chr(0xa0))

    def test_a_control_inside_the_colon_slash_slash_still_marks_a_url(self):
        # Any of the class both mirrors delete: C0, DEL and C1.
        for head in ("http:\x00//", "http:/\x01/", "http:/\t/", "http:/\x1f/", "http:\x7f//", "http:/\x80/",
                     "http:/\x85/", "http:/\x9b/", "http:/\x9f/"):
            text = "News " + head + "qqqqqq:zzzzzz@cdn.test/x"
            self.assertEqual(helper.cut_free_text(text, 20), "News", repr(head))

    def test_d_sink_95_a_character_no_mirror_deletes_still_marks_a_url(self):
        # A no-break space or a zero-width character between the slashes is
        # FILLER to the redactors' reading since D-SINK-95, so `http:/<c>/`
        # is a URL's mark to every sink and a cut inside the URL drops its
        # run; until then it was no URL to any sink, and the cut kept the run
        # (and the reading printed the username where it was cut). A
        # printable character there is still no mark, and the run is then a
        # D-SINK-96 token the cut loses the `@` of, so it is dropped too.
        for ch in (chr(0xa0), chr(0x200b), chr(0xfeff), "!"):
            text = "News http:/" + ch + "/qqqqqq:zzzzzz@cdn.test/x"
            self.assertEqual(helper.cut_free_text(text, 16), "News", repr(ch))

    def test_controls_before_the_run_do_not_move_it(self):
        # The run starts at the last space of the text as it is, and only the
        # run's own controls are deleted to look for its `://`.
        words = "\t".join("ABCDEF")
        self.assertEqual(helper.cut_free_text(words + " " + PLAIN, len(words) + 17), words)
        text = words + " News " + PLAIN + " " + PLAIN
        self.assertEqual(helper.cut_free_text(text, len(text) - 20), words + " News " + PLAIN)

    def test_a_cut_in_a_run_with_an_at_sign_or_a_colon_but_no_url_keeps_it(self):
        self.assertEqual(helper.cut_free_text("mail news@bbc.example:8080 now", 20), "mail news@bbc.exampl")

    def test_a_text_that_is_one_cut_url_comes_back_empty(self):
        self.assertEqual(helper.cut_free_text(PLAIN + "x" * 50, 30), "")

    def test_a_cut_before_the_double_slash_keeps_the_run(self):
        # `http:/` holds no credential, and no `://` to say it is a URL.
        self.assertEqual(helper.cut_free_text("News http://q@h.test/x", 10), "News http:")
        self.assertEqual(helper.cut_free_text("News http://q@h.test/x", 11), "News http:/")

    def test_a_double_slash_without_a_colon_is_not_a_url(self):
        self.assertEqual(helper.cut_free_text("Sky Sports 1//HD backup", 15), "Sky Sports 1//H")

    def test_a_cut_in_a_later_run_keeps_an_earlier_url(self):
        text = "see " + PLAIN + " and a long tail of words"
        self.assertEqual(helper.cut_free_text(text, len(text) - 3), text[:len(text) - 3])

    def test_a_group_text_run_also_ends_at_the_group_separator(self):
        # Each group reaches the sinks on its own (split_groups), so only the
        # last one is dropped, and the groups before it stay.
        text = "Sports;News;" + PLAIN
        self.assertEqual(helper.cut_free_text(text, len(text) - 20, helper.GROUP_SEPARATOR), "Sports;News")
        # With no separator a `;` is text, and the cut drops back to the
        # URL's start (the review of cbd6679: no further than the item it
        # cuts), which the run before it does not reach.
        self.assertEqual(helper.cut_free_text(text, len(text) - 20), "Sports;News;")

    def test_a_group_text_cut_at_a_semicolon_inside_a_url_drops_its_run(self):
        # D-SINK-78: the first version ended a run at every `;`, so a cut at
        # the password's kept `http://qqqqqq:zz`. Only a `;` before the run's
        # `://` separates, so the run goes back to that one, at every cut
        # inside the URL.
        text = "Sports;http://qqqqqq:zz;zz@cdn.test/x"
        for limit in range(len("Sports;http://"), len(text)):
            self.assertEqual(helper.cut_free_text(text, limit, helper.GROUP_SEPARATOR), "Sports", limit)

    def test_a_group_text_cut_at_a_semicolon_after_a_url_drops_the_url_group(self):
        # A `;` after a URL in its run is the URL's (split_groups keeps
        # `<URL>;News` as one group), so a cut there is a cut inside the
        # URL's group; with a space before the `;` it separates, and the cut
        # keeps the URL.
        text = "Sports;" + PLAIN + ";News"
        self.assertEqual(helper.cut_free_text(text, len("Sports;" + PLAIN), helper.GROUP_SEPARATOR), "Sports")
        text = "Sports;" + PLAIN + " ;News"
        for limit in (len("Sports;" + PLAIN), len("Sports;" + PLAIN + " ")):
            self.assertEqual(helper.cut_free_text(text, limit, helper.GROUP_SEPARATOR), text[:limit])

    def test_a_group_text_run_also_ends_at_a_space(self):
        # A cut in a word after a whole URL, or at the space after it, keeps
        # the URL's group.
        text = "News " + PLAIN + " more;Kids"
        for limit in (len("News " + PLAIN + " mo"), len("News " + PLAIN)):
            self.assertEqual(helper.cut_free_text(text, limit, helper.GROUP_SEPARATOR), text[:limit])


class CutSweepTest(unittest.TestCase):
    """D-SINK-95 and D-SINK-96 (2026-11-11): no cut hands a redactor half a
    URL whose mark an odd character breaks, or half a scheme-less token.
    Twelve shapes behind four prefixes, cut at every offset, with no
    separator and with the group text's `;`, then split as the group text
    is, then through the plain and the deleting redaction: no part shows a
    letter of the credential: 0 of 4,217 parts. Red on the shipped cut and
    split (dev a8e8174, with this tree's redactors): 696 of 4,684 parts
    leak, 1,392 part-and-sink pairs."""

    Z, FC, D = chr(0x200b), chr(0xff1a), chr(0x2215)
    SHAPES = ["http:" + Z + "//qqqqqq:zzzzzz@cdn.test/x", "qqqqqq:zzzzzz@cdn.test/live/1.ts",
              "http" + FC + "//cdn.test/live/qqqqqq/zzzzzz/1.ts", "xqqqqqq:zzzzzz@xhttp://cdn.test/x",
              "http:" + D + D + "cdn.test/live/qqqqqq/zzzzzz/1.ts", "qqqqqq:pa;ss@cdn.test/x",
              "http:" + Z + "//qqqqqq:pa;ss@cdn.test/x", "http" + chr(0x7f) + "://cdn.test/live/qq;qq/zz/1.ts",
              "qqqqqq:zz@zz@cdn.test/x", "http://qqqqqq:zzzzzz@cdn.test/x", "1" + Z + "://qqqqqq:zzzzzz@cdn.test/x",
              "http" + D + "://cdn.test/live/qqqqqq/zzzzzz/1.ts"]
    PREFIXES = ["", "Title ", "A;", "Sports;B "]

    def test_no_cut_part_shows_a_credential(self):
        parts, bad = 0, []
        for shape in self.SHAPES:
            for prefix in self.PREFIXES:
                text = prefix + shape + " tail"
                for limit in range(1, len(text)):
                    for separator in ("", helper.GROUP_SEPARATOR):
                        kept = helper.cut_free_text(text, limit, separator)
                        for group in (helper.split_groups(kept) if separator else [kept]):
                            parts += 1
                            for sink in (helper.redact_urls, helper.player_title_text):
                                out = sink(group)
                                if "q" in out or "z" in out:
                                    bad.append((ascii(text), limit, separator, ascii(out)))
        self.assertEqual((parts > 4000, bad[:4]), (True, []))


class PlaylistCutTest(unittest.TestCase):
    """The name, the tvg-name, the group text and each group, cut at every
    offset of each URL shape, through parse_m3u."""

    def parse(self, rows):
        lines = ["#EXTM3U"]
        for i, (attrs, title, extgrp) in enumerate(rows):
            if extgrp is not None:
                lines.append("#EXTGRP:" + extgrp)
            lines.append('#EXTINF:-1 tvg-id="c%d.test"%s,%s' % (i, attrs, title))
            lines.append("http://stream.example.test/live/%d.ts" % i)
        result = helper.parse_m3u("\n".join(lines) + "\n")
        channels = result["channels"]
        self.assertEqual(len(channels), len(rows))
        return channels

    def test_no_name_or_tvg_name_cut_keeps_a_credential(self):
        for shapes, plain in ((SHAPES, True), (JOINED_SHAPES, False)):
            cases = forms(helper.M3U_MAX_NAME, shapes)
            named = self.parse([("", t, None) for t, _ in cases])
            held_to_every_sink(self, [c["name"] for c in named], helper.M3U_MAX_NAME, [k for _, k in cases], plain)
        unterminated_names = 0
        for shapes, plain in ((ATTR_SHAPES, True), (JOINED_SHAPES, False)):
            cases = forms(helper.M3U_MAX_NAME, shapes)
            # The tvg-name; and with a title that cleans to nothing, the name
            # the cut tvg-name becomes.
            for title, field in (("Plain", lambda c: c.get("tvgName", "")), ("-", lambda c: c["name"])):
                rows = self.parse([(' tvg-name="%s"' % t, title, None) for t, _ in cases])
                values, kept, names, names_kept = attribute_route(self, cases, rows, 'tvg-name="', '",' + title, field,
                                                                  lambda c: c.get("tvgName", ""))
                held_to_every_sink(self, values, helper.M3U_MAX_NAME, kept, plain)
                held_to_every_sink(self, names, helper.M3U_MAX_NAME, names_kept, plain)
                # And every row's name, which the cut attribute's tail used
                # to become (D-SINK-80).
                held_to_every_sink(self, [c["name"] for c in rows], helper.M3U_MAX_NAME, None, plain)
                unterminated_names += len(names)
        self.assertEqual((len(SHAPES), len(ATTR_SHAPES), len(JOINED_SHAPES), unterminated_names), (57, 57, 9, 210))

    def parse_groups(self, rows):
        """parse() in batches, each under MAX_GROUPS distinct groups, past
        which a channel's group is Ungrouped whatever its text."""
        step = helper.MAX_GROUPS // 2
        return [c for i in range(0, len(rows), step) for c in self.parse(rows[i:i + step])]

    def test_no_group_cut_keeps_a_credential(self):
        # Through a group-title attribute, and through an #EXTGRP line, which
        # keeps a `"`.
        cases = forms(helper.M3U_MAX_GROUP, GROUP_SHAPES)
        rows = self.parse_groups([(' group-title="%s"' % t, "G", None) for t, _ in cases])
        values, kept, names, names_kept = attribute_route(self, cases, rows, 'group-title="', '",G',
                                                          lambda c: c["group"], lambda c: c["group"])
        held_to_every_sink(self, values, helper.M3U_MAX_GROUP, kept)
        held_to_every_sink(self, names, helper.M3U_MAX_NAME, names_kept)
        held_to_every_sink(self, [c["name"] for c in rows], helper.M3U_MAX_NAME)
        cases = forms(helper.M3U_MAX_GROUP, EXTGRP_SHAPES)
        rows = self.parse_groups([("", "G", t) for t, _ in cases])
        held_to_every_sink(self, [c["group"] for c in rows], helper.M3U_MAX_GROUP, [k for _, k in cases])
        self.assertEqual((len(GROUP_SHAPES), len(EXTGRP_SHAPES), len(names)), (57, 57, 105))

    def test_no_group_text_cut_keeps_a_credential(self):
        # Four groups of 100 first, so the 512 cut lands in a fifth group
        # short enough that its own 128 cut does not reach the URL. What the
        # cut must keep is held on that fifth group, "" when it was dropped.
        head = ";".join(ch * 100 for ch in "abcd") + ";"
        for shapes, row in ((GROUP_SHAPES, lambda t: (' group-title="%s"' % t, "G", None)),
                            (EXTGRP_SHAPES, lambda t: ("", "G", t))):
            cases = forms(helper.M3U_MAX_GROUP_TEXT - len(head), shapes)
            rows = self.parse_groups([row(head + t) for t, _ in cases])
            held_to_every_sink(self, [c["name"] for c in rows], helper.M3U_MAX_NAME)
            if row("")[0]:
                # An unterminated group-title is the name, whole but for the
                # name's own cut; the rest are held below.
                _, _, names, names_kept = attribute_route(self, [(head + t, k) for t, k in cases], rows,
                                                          'group-title="', '",G', lambda c: c["group"],
                                                          lambda c: c["group"])
                held_to_every_sink(self, names, helper.M3U_MAX_NAME, names_kept)
                self.assertEqual(len(names), 105)
                cases, rows = zip(*[(case, c) for case, c in zip(cases, rows) if unterminated(head + case[0]) is None])
            listed = [c.get("groups", [c["group"]]) for c in rows]
            self.assertTrue(all(gs[:4] == [ch * 100 for ch in "abcd"] for gs in listed))
            held_to_every_sink(self, [g for gs in listed for g in gs[4:]], helper.M3U_MAX_GROUP)
            held_to_every_sink(self, [gs[4] if len(gs) > 4 else "" for gs in listed], helper.M3U_MAX_GROUP,
                               [k for _, k in cases])

    def test_a_one_group_text_cut_after_a_url_keeps_its_group(self):
        text = "News http://cdn.test/live " + "W" * 600
        for row in ((' group-title="%s"' % text, "G", None), ("", "G", text)):
            self.assertEqual(self.parse([row])[0]["group"], "News http://cdn.test/live " + "W" * 102)

    def test_a_group_text_cut_at_a_separator_keeps_the_url_group_only_after_a_space(self):
        # The cut lands on a `;` after the URL. With a space before the `;`
        # the URL's run has ended there, so the `;` separates and the URL's
        # group is kept; without one the `;` is the URL's (D-SINK-78), so the
        # cut is inside that group and drops its run.
        head = ";".join(ch * 100 for ch in "abcd") + ";"
        words = "N" * (helper.M3U_MAX_GROUP_TEXT - len(head) - len(PLAIN) - 1)
        spaced_text, glued_text = head + words[:-1] + " " + PLAIN + " ;more", head + words + " " + PLAIN + ";more"
        self.assertEqual((spaced_text[helper.M3U_MAX_GROUP_TEXT], glued_text[helper.M3U_MAX_GROUP_TEXT]), (";", ";"))
        spaced, glued = self.parse([(' group-title="%s"' % spaced_text, "G", None), (' group-title="%s"' % glued_text, "G", None)])
        self.assertEqual((spaced["groups"][-1], glued["groups"][-1]), (words[:-1] + " " + PLAIN, words))

    def test_a_name_is_cleaned_before_it_is_cut(self):
        name = "N" * 492 + " BBC One HD extra"
        self.assertEqual(self.parse([("", "--  " + name, None)])[0]["name"], name)

    def test_a_cut_in_a_run_without_a_url_keeps_it(self):
        name = "N" * 500 + " mail news@bbc.example:8080 now"
        self.assertEqual(self.parse([("", name, None)])[0]["name"], name[:helper.M3U_MAX_NAME])

    def test_a_cut_just_after_a_space_stores_no_trailing_space(self):
        text = "N" * (helper.M3U_MAX_NAME - 1) + " Word more"
        name, tvg = self.parse([("", text, None), (' tvg-name="%s"' % text, "Plain", None)])
        self.assertEqual((name["name"], tvg["tvgName"]), ("N" * (helper.M3U_MAX_NAME - 1),) * 2)

    def test_a_url_the_cut_does_not_reach_keeps_its_host(self):
        """The other direction, so the sweep cannot be passed by a parser
        that simply deletes every URL."""
        name = "News " + PLAIN + " " + "N" * 600
        stored = self.parse([("", name, None)])[0]["name"]
        self.assertEqual(helper.redact_urls(stored), "News http://cdn.test " + "N" * (helper.M3U_MAX_NAME - 45))
        self.assertEqual(shell_sinks([stored])[0][0], "News cdn.test " + "N" * (helper.M3U_MAX_NAME - 45))


class TitleCutTest(unittest.TestCase):
    """A programme title cut at every offset of each URL shape, through
    parse_xmltv."""

    def titles(self, texts, field="title"):
        """The stored `field` of one programme per text, in order, "" for a
        programme not kept: the text as its title, or as its description,
        category or on-screen episode under a plain title. A channel takes
        300 of them a minute apart, inside the guide's window."""
        programmes = []
        for i, text in enumerate(texts):
            start = time.strftime("%Y%m%d%H%M%S +0000", time.gmtime(NOW + i % 300 * 60))
            stop = time.strftime("%Y%m%d%H%M%S +0000", time.gmtime(NOW + i % 300 * 60 + 60))
            text = text.replace("&", "&amp;").replace("<", "&lt;")
            if field == "title":
                body = "<title>%s</title>" % text
            elif field == "episode":
                body = '<title>T</title><episode-num system="onscreen">%s</episode-num>' % text
            else:
                body = "<title>T</title><%s>%s</%s>" % (field, text, field)
            programmes.append('<programme start="%s" stop="%s" channel="a%d.tv">%s</programme>'
                              % (start, stop, i // 300, body))
        channels = "".join('<channel id="a%d.tv"><display-name>A%d</display-name></channel>' % (n, n)
                           for n in range(len(texts) // 300 + 1))
        document = ('<?xml version="1.0" encoding="UTF-8"?><tv>' + channels + "".join(programmes)
                    + "</tv>").encode("utf-8")
        parsed = helper.parse_xmltv(helper.open_xml_stream(document), NOW, None)
        out = [""] * len(texts)
        for key, records in parsed["channels"].items():
            for r in records.split(helper.EPG_RECORD_SEP):
                d = helper.record_to_dict(r)
                out[int(key[1:-3]) * 300 + (d["start"] - NOW) // 60] = d.get(field, "")
        return out

    def test_no_title_cut_keeps_a_credential(self):
        cases = forms(helper.EPG_MAX_TITLE, TITLE_SHAPES, fold=True)
        titles = self.titles([t for t, _ in cases])
        # A title that is one cut URL is "", and a programme with no title is
        # not kept, so the glued forms whose cut lands in the URL are fewer.
        self.assertGreater(len([t for t in titles if t]), len(cases) * 2 // 3)
        held_to_every_sink(self, titles, helper.EPG_MAX_TITLE, [k for _, k in cases])
        self.assertEqual(len(TITLE_SHAPES), 57)

    def test_no_description_category_or_episode_cut_keeps_a_credential(self):
        """clean_detail's caps, through the same parse: it cuts by
        cut_free_text and redacts after, so what it stores is the helper's
        own redaction, and the shell shows it through sinkText again."""
        for field, cap in (("desc", helper.EPG_MAX_DESC), ("category", helper.EPG_MAX_CATEGORY),
                           ("episode", helper.EPG_MAX_EPISODE)):
            cases = forms(cap, TITLE_SHAPES, fold=True)
            stored = self.titles([t for t, _ in cases], field)
            self.assertGreater(len([v for v in stored if v]), len(cases) * 2 // 3, field)
            for value in stored:
                self.assertEqual(leaked(value), [], (field, value[-60:]))
            # What the cut keeps is stored as the helper redacts it.
            held_to_every_sink(self, stored, cap, [(helper.redact_urls(before), helper.redact_urls(whole))
                                                   for _, (before, whole) in cases])

    def test_a_detail_the_redaction_lengthens_is_cut_again(self):
        # Each `a://b/c@d` is withheld whole (R32a'), which is six characters
        # longer than it was (`a` is no named scheme, so no `a://` is
        # printed since the review of cbd6679), so the cut after the
        # redaction is what holds it.
        text = " ".join(["a://b/c@d"] * 40)
        for field, cap in (("desc", helper.EPG_MAX_DESC), ("category", helper.EPG_MAX_CATEGORY),
                           ("episode", helper.EPG_MAX_EPISODE)):
            stored = self.titles([text], field)[0]
            self.assertEqual((len(stored), stored[:19]), (cap, helper.HOST_WITHHELD + " [ho"), field)

    def test_a_title_is_folded_and_trimmed_before_it_is_cut(self):
        url_at_cap = "N" * (helper.EPG_MAX_TITLE - len(PLAIN) - 1) + " " + PLAIN
        self.assertEqual(self.titles(["  " + "T" * helper.EPG_MAX_TITLE, "\t " + url_at_cap + " more"]),
                         ["T" * helper.EPG_MAX_TITLE, url_at_cap])

    def test_a_detail_is_folded_before_it_is_cut(self):
        desc = "Live\tcoverage from " + "W" * 360 + " see\thttp://cdn.test/live/stream.m3u8 more"
        self.assertEqual(self.titles([desc], "desc"), ["Live coverage from " + "W" * 360 + " see"])

    def test_a_detail_drops_a_cut_url_with_a_c1_control_inside_its_colon_slash_slash(self):
        # The guide's fold keeps C1 but U+0085, so this reaches the cut as it is.
        desc = "N" * 380 + " http:\x80//qqqqqq:zzzzzz@cdn.test/x"
        self.assertEqual(self.titles([desc], "desc"), ["N" * 380])

    def test_a_title_url_the_cut_does_not_reach_keeps_its_host(self):
        titles = self.titles(["News " + PLAIN + " " + "N" * 300])
        self.assertEqual(helper.redact_urls(titles[0]), "News http://cdn.test " + "N" * (helper.EPG_MAX_TITLE - 45))
        self.assertEqual(shell_sinks(titles)[0][0], "News cdn.test " + "N" * (helper.EPG_MAX_TITLE - 45))


# The review of cbd6679's cut cases: a space-less description or title
# whose cut held a false positive was stored empty. Built from the review's
# own text: its prefixes, and the filler its probe wrote.
CJK_432 = 'HBO\u51fa\u54c1\u7684\u5947\u5e7b\u5267\u3002\u4e3b\u6f14\uff1a\u827e\u7c73\u8389\u4e9a\xb7\u514b\u62c9\u514b/\u57fa\u7279\xb7\u54c8\u7075\u987f/\u5f7c\u7279\xb7\u4e01\u62c9\u57fa\u3002\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c'
CJK_417 = '\u6bcf\u665a20:00\u64ad\u51fa\u3002\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u6b22\u8fce\u5173\u6ce8\u5fae\u535a@\u592e\u89c6\u65b0\u95fb'
CJK_248 = '20:00\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69\u7cbe\u5f69@\u592e\u89c6'
CJK_GOT = '\u300a\u6743\u529b\u7684\u6e38\u620f\u300b\uff08Game of Thrones\uff09\u662fHBO\u51fa\u54c1\u7684\u5947\u5e7b\u5267\u3002\u4e3b\u6f14\uff1a\u827e\u7c73\u8389\u4e9a\xb7\u514b\u62c9\u514b/\u57fa\u7279\xb7\u54c8\u7075\u987f/\u5f7c\u7279\xb7\u4e01\u62c9\u57fa\u3002\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c'
CJK_PROSE = '\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2\u8ff0\u4e86\u4e03\u5927\u738b\u56fd\u4e4b\u95f4\u7684\u4e89\u9738\uff0c\u5404\u5927\u5bb6\u65cf\u4e3a\u4e86\u94c1\u738b\u5ea7\u5c55\u5f00\u4e86\u6fc0\u70c8\u7684\u6597\u4e89\uff0c\u672c\u5b63\u8bb2'


class ProseCutTest(unittest.TestCase):
    """The review of cbd6679 (its changes-too-much finding 3): the cut
    dropped a run it cut back to the run's last space, so a space-less
    Chinese or Japanese description or title whose cut held a false
    positive -- a wide mark, or a `:` and an `@` far apart -- was stored
    EMPTY until the next fetch, and one with a single space before it kept
    its first words. The caps make the review's four texts no false positive
    at all, so each is stored to its cap; and a cut drops back no further
    than the start of the item it cuts, so the prose before a real one is
    kept. Red on cbd6679: each review text stored "" (the last, 15
    characters), and each item below dropped its prose."""

    def test_the_reviews_texts_are_stored_to_their_cap(self):
        cases = [(CJK_432, CJK_432[:400], CJK_432[:200]), (CJK_417, CJK_417[:400], CJK_417[:200]),
                 (CJK_248, CJK_248, CJK_248[:200]), (CJK_GOT, CJK_GOT[:400], CJK_GOT[:200])]
        got = [(helper.clean_detail(t, helper.EPG_MAX_DESC), helper.clean_title(t)) for t, _, _ in cases]
        self.assertEqual(got, [(d, t) for _, d, t in cases])

    def test_the_cut_keeps_the_prose_before_the_item_it_cuts(self):
        mark = "ESPN" + chr(0x200b) + "//" + chr(0x200b) + "HD"
        credential = "qqqqqq:zzzzzz" + "x" * 200 + "@cdn.test"
        kept = CJK_PROSE + "Sport:Live@HD" + CJK_PROSE
        self.assertEqual([helper.cut_free_text(CJK_PROSE + mark + CJK_PROSE, 400),
                          helper.cut_free_text(CJK_PROSE + credential, 400),
                          helper.cut_free_text(CJK_PROSE + "x" + chr(0x4e2d) * 2 + credential, 400),
                          helper.cut_free_text(kept, 400),
                          helper.clean_detail(CJK_PROSE + mark + CJK_PROSE, helper.EPG_MAX_DESC),
                          helper.clean_title(CJK_PROSE[:150] + mark + CJK_PROSE)],
                         [CJK_PROSE, CJK_PROSE, CJK_PROSE + "x" + chr(0x4e2d) * 2, kept[:400], CJK_PROSE, CJK_PROSE[:150]])
        # The credential the cut keeps whole is withheld at every sink, and
        # the prose before it shows.
        self.assertEqual(helper.redact_urls(kept[:400]), CJK_PROSE + helper.HOST_WITHHELD)


class DeletingStartTest(unittest.TestCase):
    """The review of cbd6679: the cut drops back to the start of the item it
    cuts as the plain reading finds it, and the sinks that delete controls
    first (the player's title, the notification) must read no item in what
    it keeps of that run either -- a deleted control is no WIDE code point
    and no STAND_IN, so it moves no mark, and the scheme a deleting sink
    reads starts no later -- or they would print half of one. Over prose
    holding controls before items holding them, cut at every offset inside
    the item: what the cut keeps of its run reads as plain text at the sinks
    that delete controls whenever it does at the plain ones, and no sink
    shows a letter of the credential the whole text does not."""

    def test_what_the_cut_keeps_of_its_run_reads_alike_at_every_sink(self):
        prefixes = ["", "News ", CJK_PROSE[:40], "ab" + chr(1) + "cd", "x" + chr(0x7f) + "y" + chr(0xa0),
                    "1" + chr(0x85), "Q\t", chr(0x4e2d) + "\t" + chr(0x4e2d), "N" + chr(0x9b) + "N"]
        items = [PLAIN, "ht" + chr(1) + "tp://qqqqqq:zzzzzz@cdn.test/x", "http" + chr(1) + "://cdn.test/live/qqqqqq/zzzzzz/1.ts",
                 "http:\t//qqqqqq:zzzzzz@cdn.test/x", "qqqqqq:zz\tzz@cdn.test/x", "qqqqqq:zz" + chr(1) + chr(0xe9) + "zz@cdn.test",
                 "1://qqqqqq:zzzzzz@cdn.test", "ab" + chr(1) + "cd://cdn.test/live/qqqqqq/zzzzzz/1.ts",
                 "x" + chr(0x200b) + "//qqqqqq:zzzzzz@cdn.test", "http://x/\tqqqqqq:zz@cdn.test",
                 "a" + chr(0x200b) + chr(0x2215) * 2 + "\t:zzzzzz@cdn.test",
                 # Two C1 controls beside the colon: no WIDE code point, so a
                 # mark to every sink.
                 "http:" + chr(0x85) + chr(0x9b) + "//cdn.test/live/qqqqqq/zzzzzz/1.ts"]
        tails = ["", " tail", CJK_PROSE[:20]]
        bad, checked = [], 0
        for prefix in prefixes:
            for item in items:
                for tail in tails:
                    text = prefix + item + tail
                    whole = {"plain": leaked(helper.redact_urls(text)), "deleting": leaked(helper.player_title_text(text))}
                    for limit in range(len(prefix), len(prefix) + len(item)):
                        stored = helper.cut_free_text(text, limit)
                        run = stored[stored.rfind(" ") + 1:]
                        if helper.redact_urls(run) == run and helper.player_title_text(run) != deleted(run):
                            bad.append(("deleting reads an item", ascii(text), limit))
                        for sink, out in (("plain", helper.redact_urls(stored)), ("deleting", helper.player_title_text(stored))):
                            if leaked(out) and not whole[sink]:
                                bad.append((sink, ascii(text), limit, ascii(out)))
                        checked += 1
        self.assertEqual(bad[:4], [])
        self.assertGreater(checked, 5000)


if __name__ == "__main__":
    unittest.main()
