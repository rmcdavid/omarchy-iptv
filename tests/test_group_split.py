"""D-SINK-78 (2026-11-05): a group text is never split inside a URL.

split_groups split a group-title or an #EXTGRP line at every `;`, before any
redactor saw it, and every redactor reads a `;` as URL text. So
`http://myuser:pa;ss@cdn.test/x` was listed under `http://myuser:pa`, which
both redactors print as the host `myuser`, with `ss@cdn.test/x` beside it as
a group no redactor could touch; and the shell cut the stored group at its
first `;` again. A `;` separates groups now only when no `://` (read as the
sinks that delete control characters read one) stands between it and the
last ASCII space before it, and the shell reads the stored group whole.

tests/fixtures/group-split.json holds the cases, and tests/Model.test.js runs
it too: there, the row the helper writes lists under that group whole, and
no sink the shell shows a group at shows a letter of the credential (for the
two cases with a control inside the `://`, the notification body alone, as
here the window title alone: to the other sinks that text is no URL, split
or not). Here: the
helper's split, its parse through a group-title and through an #EXTGRP line,
the helper's own sinks, and the rule itself against a definition of it over
random texts, for the split and for the group text's cut.

D-SINK-95 and D-SINK-96 (2026-11-11): a mark is also one the redactors'
reading finds behind a scheme, which any odd character may break
(tests/url_reading_rule.py), and a `;` after a run's first `:` and before
its last `@` stands inside the credential token a redactor withholds; the
split keeps both, and the cut drops a run cut inside either.
"""
import json
import os
import random
import time
import unittest

import url_reading_rule as rule
from helper_loader import load_helper

helper = load_helper()
HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "fixtures", "group-split.json"), encoding="utf-8") as fh:
    FIXTURE = json.load(fh)
CASES = FIXTURE["cases"]


def leaked(text):
    return [c for c in FIXTURE["secret"] if c in text]


def deleted(text):
    """`text` without the controls both mirrors delete: C0, DEL and C1."""
    return "".join(c for c in text if not (ord(c) < 0x20 or 0x7f <= ord(c) <= 0x9f))


def run_of(text, i):
    """The space-run around `i`: (its start, its end)."""
    end = text.find(" ", i)
    return text.rfind(" ", 0, i) + 1, len(text) if end < 0 else end


def separates(text, i):
    """The rule, as stated: the `;` at `i` separates unless, within its
    space-run, a mark either reading protects starts before it (a `://`
    with its controls deleted, or a D-SINK-95 mark behind a scheme), or it
    stands after the run's first `:` and before the run's last `@`
    (D-SINK-96)."""
    start, end = run_of(text, i)
    run, k = text[start:end], i - start
    if "://" in deleted(run[:k]):
        return False
    url = rule.first_url(run)
    if url is not None and url[1] < k:
        return False
    colon, at = run.find(":"), run.rfind("@")
    return not (0 <= colon < k < at)


def split_reference(text):
    parts, start = [], 0
    for i, c in enumerate(text):
        if c == ";" and separates(text, i):
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return list(dict.fromkeys(p.strip() for p in parts if p.strip()))


def cut_reference(text, limit):
    """cut_free_text's rule for a group text, as stated (D-SINK-75, as the
    review of cbd6679 restated it): a cut that lands inside a space-run is
    kept, unless the run's first URL (url_reading_rule, from the run's
    start) starts before it with its whole mark kept, or the run's
    credential has its `@` past where the cut would end and its span
    starting before it; then the cut drops back to that item's start, a
    space just before it taken -- or to the last `;` that stands before the
    run's first mark and its first `:` (when an `@` follows it), when that
    is later -- and never ends in a `;`."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if text[limit] == " ":
        return cut
    start = cut.rfind(" ")
    low = start + 1
    run_end = text.find(" ", limit)
    run_end = len(text) if run_end < 0 else run_end
    url = rule.first_url(text, low)
    bound = url[0] if url is not None and url[2] <= limit else limit
    found = rule.credential(text, low, run_end, rule.urls(text, low))
    if found is not None and found[1] >= bound and found[2] < bound:
        bound = found[2]
    if bound == limit:
        return cut
    end = bound - 1 if bound > 0 and text[bound - 1] == " " else bound
    mark = rule.mark_any(cut, low)
    keep = limit if mark < 0 else mark
    colon = text.find(":", low, run_end)
    if colon >= 0 and text.find("@", colon + 1, run_end) >= 0:
        keep = min(keep, colon)
    semis = [i for i in range(low, keep) if cut[i] == ";"]
    if semis:
        end = max(end, semis[-1])
    if end > low and cut[end - 1] == ";":
        end -= 1
    return cut[:max(end, 0)]


def parse(rows):
    """parse_m3u over (group-title or None, #EXTGRP or None) rows."""
    lines = ["#EXTM3U"]
    for i, (title, extgrp) in enumerate(rows):
        if extgrp is not None:
            lines.append("#EXTGRP:" + extgrp)
        attrs = ' group-title="%s"' % title if title is not None else ""
        lines.append('#EXTINF:-1 tvg-id="c%d.test"%s,Channel' % (i, attrs))
        lines.append("http://stream.example.test/live/%d.ts" % i)
    channels = helper.parse_m3u("\n".join(lines) + "\n")["channels"]
    assert len(channels) == len(rows)
    return channels


class FixtureTest(unittest.TestCase):
    def test_the_fixture_is_whole(self):
        # A shrunken fixture goes red: the credential shapes, the ordinary
        # texts and the stated costs are all there.
        self.assertGreaterEqual(len(CASES), 38)
        self.assertGreaterEqual(len([c for c in CASES if leaked(c["text"])]), 21)
        self.assertGreaterEqual(len([c for c in CASES if len(c["groups"]) > 1]), 11)
        self.assertEqual(FIXTURE["ungrouped"], helper.UNGROUPED)

    def test_the_fixture_is_the_rule(self):
        for c in CASES:
            self.assertEqual(split_reference(c["text"]), c["groups"], c["why"])

    def test_split_groups_answers_every_case(self):
        for c in CASES:
            self.assertEqual(helper.split_groups(c["text"]), c["groups"], c["why"])

    def test_the_parse_stores_the_first_group_and_the_list(self):
        # Through a group-title (whose value ends at its `"`, which no case
        # holds) and through an #EXTGRP line.
        for rows in ([(c["text"], None) for c in CASES], [(None, c["text"]) for c in CASES]):
            for c, channel in zip(CASES, parse(rows)):
                group = c["groups"][0] if c["groups"] else helper.UNGROUPED
                self.assertEqual(channel["group"], group, c["why"])
                self.assertEqual(channel.get("groups"), c["groups"] if len(c["groups"]) > 1 else None, c["why"])

    def test_the_split_memo_holds_one_text_and_hands_out_copies(self):
        # A persistent #EXTGRP is answered from it; a playlist of distinct
        # group texts may not grow it, and a caller changing its answer may
        # not change the next one.
        parse([(c["text"], None) for c in CASES])
        self.assertLessEqual(len(helper.SPLIT_GROUPS_LAST), 1)
        for _ in range(2):
            # The split's own answer, then the memo's.
            helper.split_groups("Sports;News").append("Kids")
        self.assertEqual((helper.split_groups("Sports;News"), list(helper.SPLIT_GROUPS_LAST)),
                         (["Sports", "News"], ["Sports;News"]))

    def test_a_repeated_text_is_answered_from_the_memo(self):
        # The memo's whole purpose: a persistent #EXTGRP is split once, not
        # once a channel. A memo written and never read passes the test
        # above; this counts the splits.
        split = helper.group_parts
        calls = []

        def counting(text):
            calls.append(text)
            return split(text)

        helper.SPLIT_GROUPS_LAST.clear()
        helper.group_parts = counting
        try:
            answers = [helper.split_groups("News http://cdn.test/x;y ;Kids") for _ in range(2)]
        finally:
            helper.group_parts = split
        self.assertEqual((answers, len(calls)), ([["News http://cdn.test/x;y", "Kids"]] * 2, 1))

    def test_no_stored_group_shows_a_credential_at_a_helper_sink(self):
        # The window title deletes control characters before it redacts;
        # redact_urls reads them as they are, so a control inside a `://`
        # (`plain` false) is no URL to it, split or not.
        bad = []
        for rows in ([(c["text"], None) for c in CASES], [(None, c["text"]) for c in CASES]):
            for c, channel in zip(CASES, parse(rows)):
                for group in channel.get("groups", [channel["group"]]):
                    sinks = [("player_title_text", helper.player_title_text(group))]
                    if c.get("plain", True):
                        sinks.append(("redact_urls", helper.redact_urls(group)))
                    bad += [(c["why"], sink, out) for sink, out in sinks if leaked(out)]
        self.assertEqual(bad, [])

    def test_each_url_is_redacted_whole(self):
        # The other direction, so the sinks cannot be passed by a split that
        # simply drops every group holding a URL.
        shown = {c["text"]: helper.redact_urls(c["groups"][0]) for c in CASES if c["groups"]}
        self.assertEqual(shown["http://qqqqqq:zz;zz@cdn.test/x"], "http://cdn.test")
        self.assertEqual(shown["http://cdn.test/live/qqqqqq/zz;zz/1.ts"], "http://cdn.test")
        self.assertEqual(shown["http://cdn.test/get.php?username=qqqqqq&password=zz;zz"], "http://cdn.test")
        self.assertEqual(shown["http://qqqqqq:zz/z;z@cdn.test/x"], "http://" + helper.HOST_WITHHELD)
        self.assertEqual(shown["Sports;http://qqqqqq:zz;zz@cdn.test/x;News"], "Sports")
        self.assertEqual(helper.redact_urls(helper.split_groups("Sports;http://qqqqqq:zz;zz@cdn.test/x;News")[1]),
                         "http://cdn.test")


class RuleTest(unittest.TestCase):
    """The split and the group text's cut against the rule as stated, over
    random texts built from the characters the rule reads."""

    # Every control a playlist line can carry is run text: a line ends only
    # at a line feed (playlist_lines), so the run's end and the cut are held
    # at each class the rule tells apart -- C0, DEL and C1, which a `://`
    # may hold, and U+00A0, U+2028 and U+3000, which it may not.
    ALPHABET = ["a", "h", ":", "/", ";", " ", "\t", "\x00", "\x0b", "\x0c", "\x1f", "\x7f", "\x85", "\x9f",
                "\xa0", "\u2028", "\u3000", "@", "://", ":/", "http://", ";;", " ;",
                # D-SINK-95 and D-SINK-96: a STAND_IN, a look-alike slash, the
                # marks they make, and a token.
                chr(0x200b), chr(0x2215), "http:" + chr(0x200b) + "//", "a:" + chr(0x2215) * 2, "a:b@"]

    def texts(self, seed, count):
        rng = random.Random(seed)
        for _ in range(count):
            yield "".join(rng.choice(self.ALPHABET) for _ in range(rng.randint(0, 16))), rng

    def test_the_split_is_the_rule(self):
        for text, _ in self.texts(78, 40000):
            self.assertEqual(helper.split_groups(text), split_reference(text), repr(text))

    def test_the_group_text_cut_is_the_rule(self):
        for text, rng in self.texts(780, 40000):
            if text:
                limit = rng.randint(0, len(text))
                self.assertEqual(helper.cut_free_text(text, limit, helper.GROUP_SEPARATOR),
                                 cut_reference(text, limit), (repr(text), limit))

    def test_a_cut_group_text_never_ends_inside_a_url(self):
        # The property itself, without the reference: when the run the kept
        # text ends with holds a URL, as the plain sinks read it or as the
        # sinks that delete controls do, the text went on from there with a
        # space, or not at all, so no redactor is handed a cut URL. (A `://`
        # with no scheme letter before it is no URL to any sink, and since
        # the review of cbd6679 the cut keeps the run up to the first item
        # it would cut.)
        checked = 0
        for text, rng in self.texts(7800, 40000):
            if text:
                kept = helper.cut_free_text(text, rng.randint(0, len(text)), helper.GROUP_SEPARATOR)
                run = kept[kept.rfind(" ") + 1:]
                if rule.urls(run) or rule.urls(deleted(run)):
                    checked += 1
                    self.assertTrue(len(kept) == len(text) or text[len(kept)] == " ", (repr(text), repr(kept)))
        self.assertGreater(checked, 1000)


class LinearTest(unittest.TestCase):
    """split_groups is split again for every channel after a persistent
    #EXTGRP (R30h), so its `://` test may not search back from each `;`,
    and its dedupe may not scan the list. Four times the text may cost at
    most eight times the time plus 2 ms, best of five, in this thread's CPU
    time, so a busy machine does not count; searching back or scanning
    costs sixteen times, far past the 2 ms at these lengths. The first two
    shapes are one match each and take microseconds, so the 2 ms is their
    whole bound."""

    SHAPES = [lambda n: "http://a" + ";" * n, lambda n: "a://b;" * (n // 6), lambda n: " a://b;c" * (n // 8),
              lambda n: "x;" * (n // 2) + "a://", lambda n: ":" * n + ";/", lambda n: ":\x00" * (n // 2) + ";/",
              lambda n: "/;" + ";".join("g%d" % i for i in range(n // 6))]

    def best(self, text):
        times = []
        for attempt in range(5):
            # A different text each time, so the split's memo never answers.
            text = text + " " * (attempt + 1)
            t0 = time.thread_time()
            helper.split_groups(text)
            times.append(time.thread_time() - t0)
        return min(times)

    def test_the_split_is_linear_on_every_shape(self):
        for shape in self.SHAPES:
            small, large = self.best(shape(8000)), self.best(shape(32000))
            self.assertLess(large, 8 * small + 0.002, shape(16)[:16])


if __name__ == "__main__":
    unittest.main()
