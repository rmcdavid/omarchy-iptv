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
"""
import calendar
import json
import os
import subprocess
import time
import unittest

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
SHAPES = [PLAIN] + SCHEMES + ["http://qqqqqq:zz%szz@cdn.test/x" % c for c in PASSWORD_CHARS]
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
# What each field's own parse splits: an attribute's value ends at its
# closing `"` (the tvg-name, the group-title; an #EXTGRP line is no attribute
# and keeps it), and the stored groups are split at `;` (split_groups), after
# the group text's cut and before each group's. A title, description,
# category or episode is cut after the guide's whitespace fold
# (clean_field's). Each sweep takes the shapes its field keeps as they are.
ATTR_SHAPES = [s for s in SHAPES if '"' not in s]
GROUP_SHAPES = [s for s in ATTR_SHAPES if ";" not in s]
EXTGRP_SHAPES = [s for s in SHAPES if ";" not in s]
TITLE_SHAPES = [s for s in SHAPES if helper.clean_field(s, len(s)) == s]
SECRET = "qz"


def leaked(text):
    return [c for c in SECRET if c in text]


def deleted(text):
    """`text` without the controls both mirrors delete before they redact:
    C0, DEL and C1."""
    return "".join(c for c in text if not (ord(c) < 0x20 or 0x7f <= ord(c) <= 0x9f))


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
    `fold` is a guide field's, which reads a tab as a space. The glued form's
    run never ends, so it keeps its cut text only while that holds no
    `://`."""
    joined = "N\x80N\x9b"
    out = []
    for url in shapes:
        for pad in range(max(1, cap - len(url) - 3), cap + 2):
            for head, sep in (("N" * pad, " "), ((joined * pad)[:pad], " "), ("N" * pad, "\t")):
                text = head + sep + url + " tail"
                cut = (text.replace("\t", " ") if fold else text)[:cap]
                whole = url if len(head) + 1 + len(url) <= cap else ""
                if whole or "://" not in deleted(cut[len(head) + 1:]):
                    before = cut
                elif cut[len(head)] == " ":
                    before = head
                else:
                    before = ""
                out.append((text, (before.rstrip(), whole)))
            text = "N" * pad + url + "tail"
            out.append((text, ("" if "://" in deleted(text[:cap]) else text[:cap].rstrip(), "")))
    return out


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
            # Not a run end, so the run reaches back to the text's start.
            self.assertEqual(helper.cut_free_text("News" + delim + PLAIN, len(PLAIN)), "", repr(delim))

    def test_the_run_reaches_back_past_a_no_break_space(self):
        # URL text to the redactors (R32a'''), so the run starts at the space.
        text = "Live News" + chr(0xa0) + PLAIN
        self.assertEqual(helper.cut_free_text(text, len(text) - 20), "Live")

    def test_a_control_inside_the_colon_slash_slash_still_marks_a_url(self):
        # Any of the class both mirrors delete: C0, DEL and C1.
        for head in ("http:\x00//", "http:/\x01/", "http:/\t/", "http:/\x1f/", "http:\x7f//", "http:/\x80/",
                     "http:/\x85/", "http:/\x9b/", "http:/\x9f/"):
            text = "News " + head + "qqqqqq:zzzzzz@cdn.test/x"
            self.assertEqual(helper.cut_free_text(text, 20), "News", repr(head))

    def test_a_character_no_mirror_deletes_does_not_join_a_url(self):
        # A no-break space or a zero-width character is URL text to both
        # redactors, so `http:/` and `/qqq` around it are no URL to any sink,
        # cut or not, and the cut keeps the run.
        for ch in (chr(0xa0), chr(0x200b), chr(0xfeff)):
            text = "News http:/" + ch + "/qqqqqq:zzzzzz@cdn.test/x"
            self.assertEqual(helper.cut_free_text(text, 16), text[:16], repr(ch))

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
        self.assertEqual(helper.cut_free_text(text, len(text) - 20, helper.GROUP_TEXT_ENDS), "Sports;News")
        self.assertEqual(helper.cut_free_text(text, len(text) - 20), "")

    def test_a_group_text_cut_at_a_separator_keeps_the_url_group_before_it(self):
        text = "Sports;" + PLAIN + ";News"
        self.assertEqual(helper.cut_free_text(text, len("Sports;" + PLAIN), helper.GROUP_TEXT_ENDS),
                         "Sports;" + PLAIN)

    def test_a_group_text_run_also_ends_at_a_space(self):
        # A cut in a word after a whole URL, or at the space after it, keeps
        # the URL's group.
        text = "News " + PLAIN + " more;Kids"
        for limit in (len("News " + PLAIN + " mo"), len("News " + PLAIN)):
            self.assertEqual(helper.cut_free_text(text, limit, helper.GROUP_TEXT_ENDS), text[:limit])


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
        for shapes, plain in ((ATTR_SHAPES, True), (JOINED_SHAPES, False)):
            cases = forms(helper.M3U_MAX_NAME, shapes)
            tvg = self.parse([(' tvg-name="%s"' % t, "Plain", None) for t, _ in cases])
            held_to_every_sink(self, [c.get("tvgName", "") for c in tvg], helper.M3U_MAX_NAME,
                               [k for _, k in cases], plain)
            # A title that cleans to nothing takes the cut tvg-name as the name.
            fallback = self.parse([(' tvg-name="%s"' % t, "-", None) for t, _ in cases])
            held_to_every_sink(self, [c["name"] for c in fallback], helper.M3U_MAX_NAME,
                               [k for _, k in cases], plain)
        self.assertEqual((len(SHAPES), len(ATTR_SHAPES), len(JOINED_SHAPES)), (47, 46, 9))

    def parse_groups(self, rows):
        """parse() in batches, each under MAX_GROUPS distinct groups, past
        which a channel's group is Ungrouped whatever its text."""
        step = helper.MAX_GROUPS // 2
        return [c for i in range(0, len(rows), step) for c in self.parse(rows[i:i + step])]

    def test_no_group_cut_keeps_a_credential(self):
        # Through a group-title attribute, and through an #EXTGRP line, which
        # keeps a `"`.
        for shapes, row in ((GROUP_SHAPES, lambda t: (' group-title="%s"' % t, "G", None)),
                            (EXTGRP_SHAPES, lambda t: ("", "G", t))):
            cases = forms(helper.M3U_MAX_GROUP, shapes)
            rows = self.parse_groups([row(t) for t, _ in cases])
            held_to_every_sink(self, [c["group"] for c in rows], helper.M3U_MAX_GROUP, [k for _, k in cases])
        self.assertEqual((len(GROUP_SHAPES), len(EXTGRP_SHAPES)), (45, 46))

    def test_no_group_text_cut_keeps_a_credential(self):
        # Four groups of 100 first, so the 512 cut lands in a fifth group
        # short enough that its own 128 cut does not reach the URL. What the
        # cut must keep is held on that fifth group, "" when it was dropped.
        head = ";".join(ch * 100 for ch in "abcd") + ";"
        for shapes, row in ((GROUP_SHAPES, lambda t: (' group-title="%s"' % t, "G", None)),
                            (EXTGRP_SHAPES, lambda t: ("", "G", t))):
            cases = forms(helper.M3U_MAX_GROUP_TEXT - len(head), shapes)
            rows = self.parse_groups([row(head + t) for t, _ in cases])
            listed = [c.get("groups", [c["group"]]) for c in rows]
            self.assertTrue(all(gs[:4] == [ch * 100 for ch in "abcd"] for gs in listed))
            held_to_every_sink(self, [g for gs in listed for g in gs[4:]], helper.M3U_MAX_GROUP)
            held_to_every_sink(self, [gs[4] if len(gs) > 4 else "" for gs in listed], helper.M3U_MAX_GROUP,
                               [k for _, k in cases])

    def test_a_one_group_text_cut_after_a_url_keeps_its_group(self):
        text = "News http://cdn.test/live " + "W" * 600
        for row in ((' group-title="%s"' % text, "G", None), ("", "G", text)):
            self.assertEqual(self.parse([row])[0]["group"], "News http://cdn.test/live " + "W" * 102)

    def test_a_group_text_cut_at_a_separator_keeps_the_url_group(self):
        head = ";".join(ch * 100 for ch in "abcd") + ";"
        tail = "N" * (helper.M3U_MAX_GROUP_TEXT - len(head) - len(PLAIN) - 1) + " " + PLAIN
        groups = self.parse([(' group-title="%s;more"' % (head + tail), "G", None)])[0]["groups"]
        self.assertEqual(groups[-1], tail)

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
        self.assertEqual(len(TITLE_SHAPES), 42)

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
        # Each `a://b/c@d` is withheld whole (R32a'), which is ten characters
        # longer than it was, so the cut after the redaction is what holds it.
        text = " ".join(["a://b/c@d"] * 40)
        for field, cap in (("desc", helper.EPG_MAX_DESC), ("category", helper.EPG_MAX_CATEGORY),
                           ("episode", helper.EPG_MAX_EPISODE)):
            stored = self.titles([text], field)[0]
            self.assertEqual((len(stored), stored[:19]), (cap, "a://" + helper.HOST_WITHHELD), field)

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


if __name__ == "__main__":
    unittest.main()
