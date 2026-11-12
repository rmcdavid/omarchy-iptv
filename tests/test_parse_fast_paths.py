"""D-PERF-13: the parse's native shortcuts give the answers of the code they
stand in front of, and are taken.

Each shortcut is an early exit or a native form of one step of the playlist
parse, for a text that holds none of what the slower step looks for: the
`://` search on a text with no control character (url_mark_start), the ASCII
fold (fold_text's translate table), the native group split where no `;`
can stand in a URL's run or a credential token (group_split_protects,
D-SINK-95 and D-SINK-96), bound_groups' slice, and the
id substitution's exit for a list with no `u:` row. Every test here calls the
shipping function and holds it to the pattern or the loop it replaced, over
texts built from the characters each step reads; the last class proves the
split's shortcut is TAKEN, so the gate sees it if it is lost (its cost is
held by test_playlist's GroupTextPerformanceTest). The byte identity of
channels.json against 8ff582f over the D-PERF-13 shapes, every fixture and
generated playlists is recorded in the lane's write-up, not re-run here.
"""
import random
import re
import unittest

from helper_loader import load_helper

helper = load_helper()

# The characters the mark, the split and the fold tell apart, and the ones
# beside them: C0 (a mark's filler and a fold's whitespace), DEL and C1 (a
# mark's filler, no whitespace), the non-ASCII whitespace the fold folds, and
# letters, `+` and `*` (the two folds differ only there).
ALPHABET = ["a", "Z", "0", ":", "/", ";", " ", "\t", "\x00", "\x0b", "\x1c", "\x1f", "\x7f", "\x85", "\x9f",
            "\xa0", "\u2028", "\u3000", "+", "*", "-", "@", "://", ":/", "//", ";;", " ;", "\u00df", "\u00e9",
            "http://", "a:// ;"]
ASCII = [t for t in ALPHABET if t.isascii()]


def texts(seed, count, longest=40):
    rng = random.Random(seed)
    for i in range(count):
        pool = ALPHABET if i % 2 else ASCII
        yield "".join(rng.choice(pool) for _ in range(rng.randint(0, longest))), rng


def mark_start(text, pos=0):
    found = helper._URL_MARK.search(text, pos)
    return -1 if found is None else found.start()


class UrlMarkStartTest(unittest.TestCase):
    def test_every_code_point_where_a_mark_can_stand(self):
        # Each code point before, inside and after a `://`, and as a mark's
        # filler, at each start the callers pass.
        for code in range(0x10000):
            if 0xD800 <= code <= 0xDFFF:
                continue
            c = chr(code)
            for text in (c + "://", ":" + c + "//", ":/" + c + "/", "a" + c + ":" + c + "/" + c + "/x", c * 3 + " a://"):
                for pos in (0, 1, 2):
                    self.assertEqual(helper.url_mark_start(text, pos), mark_start(text, pos), (code, text, pos))

    def test_random_texts_at_every_start(self):
        for text, rng in texts(7, 20000):
            for pos in {0, rng.randint(0, len(text) + 1), len(text)}:
                self.assertEqual(helper.url_mark_start(text, pos), mark_start(text, pos), (repr(text), pos))


class AsciiFoldTest(unittest.TestCase):
    """fold_text's ASCII path against the pattern it replaced on ASCII text:
    punct.sub(" ", text.lower()).strip(" "), FOLD having no ASCII key."""

    PUNCTS = (helper._PUNCT, helper._ID_PUNCT)

    def old(self, text, punct):
        return punct.sub(" ", text.lower()).strip(" ")

    def test_every_ascii_pair(self):
        for punct in self.PUNCTS:
            for a in range(128):
                for b in range(128):
                    text = chr(a) + chr(b) + " " + chr(b) + chr(a)
                    self.assertEqual(helper.fold_text(text, punct), self.old(text, punct), (a, b, punct.pattern[:8]))

    def test_random_ascii_texts(self):
        rng = random.Random(13)
        for _ in range(20000):
            text = "".join(chr(rng.randrange(128)) for _ in range(rng.randint(0, 60)))
            for punct in self.PUNCTS:
                self.assertEqual(helper.fold_text(text, punct), self.old(text, punct), repr(text))

    def test_the_table_is_the_class_and_refuses_one_that_leaves_whitespace_out(self):
        for punct in self.PUNCTS:
            table = helper._ascii_space_table(punct)
            self.assertEqual(sorted(table), [c for c in range(128) if punct.fullmatch(chr(c))])
            self.assertEqual(set(table.values()), {" "})
        # A class without the ASCII whitespace str.split() splits at would
        # give another answer than its sub: no table, so the pattern runs.
        self.assertIsNone(helper._ascii_space_table(re.compile("[!-/]+")))
        self.assertEqual(helper.fold_text("a!\tb", re.compile("[!-/]+")), "a \tb")

    def test_a_fold_with_an_ascii_key_takes_the_whole_fold(self):
        # Were FOLD ever to gain an ASCII key, the builder gives no table,
        # and an ASCII text must then take FOLD as well as the pattern, as
        # every text did at 8ff582f. The first version's fallback ran the
        # pattern alone and dropped FOLD (the D-PERF-13 judge's owed fix).
        saved = helper.FOLD, helper.FOLD_TABLE, helper._ASCII_SPACE_TABLES
        try:
            helper.FOLD = dict(saved[0], q="k")
            helper.FOLD_TABLE = str.maketrans(helper.FOLD)
            helper._ASCII_SPACE_TABLES = {punct: helper._ascii_space_table(punct) for punct in self.PUNCTS}
            self.assertEqual(list(helper._ASCII_SPACE_TABLES.values()), [None, None])
            for punct in self.PUNCTS:
                self.assertEqual(helper.fold_text("Quiz  Show", punct), "kuiz show", punct.pattern[:8])
        finally:
            helper.FOLD, helper.FOLD_TABLE, helper._ASCII_SPACE_TABLES = saved

    def test_the_other_scripts_still_take_fold(self):
        # Every FOLD key, alone and between letters, reaches its replacement.
        for key, to in helper.FOLD.items():
            self.assertEqual(helper.normalize_text("x" + key + "y"), "x" + to + "y", repr(key))
            self.assertEqual(helper.normalize_text(key.upper() + " Z"), helper.normalize_text(key.upper()) + " z")


class SplitAndBoundTest(unittest.TestCase):
    def test_the_split_takes_the_native_path_only_where_no_semicolon_can_be_kept(self):
        # group_parts runs only where group_split_protects says a `;` could
        # stand in a mark's run or a token, and the answer is the rule's
        # either way (test_group_split holds that).
        split = helper.group_parts
        calls = []

        def counting(text):
            calls.append(text)
            return split(text)

        cases = [
            ("News http://cdn.test/g1 ;Kids ;http://h.test/x", False),   # every `;` opens its run
            ("<1>" + ":" * 40 + ";/", False),                            # a `/` and a `;`, no mark
            ("Sports;News", False),
            ("a:// ;" * 80, False),                                      # D-PERF-13's shape
            ("x;a:// y;b", True),                                        # asked: a `;` that opens no run
            ("http://qqqqqq:zz;zz@cdn.test/x", True),
            ("News ; http://u:p;w@h.test/x ;Kids", True),
            ("a://b;c", True),
            ("Sports;http://h.test/a;b", True),
            ("qqqqqq:zz;zz@cdn.test/x", True),                           # D-SINK-96: a token
            ("http:" + chr(0x200b) + "//cdn.test/a;b", True),            # D-SINK-95: a broken mark
            ("Kino;Filme:" + chr(0x2215) + "x", False),                  # a look-alike, no mark
        ]
        helper.group_parts = counting
        try:
            for text, asked in cases:
                calls.clear()
                helper.SPLIT_GROUPS_LAST.clear()
                helper.split_groups(text)
                self.assertEqual(bool(calls), asked, ascii(text))
        finally:
            helper.group_parts = split

    def test_the_native_split_is_taken_only_where_every_semicolon_separates(self):
        # Where group_split_protects says no `;` can be kept, the native
        # split is the rule's answer: every `;` separates, as the rule
        # (tests/url_reading_rule.py, as test_group_split states it) reads.
        import test_group_split as rule

        def native(text):
            return list(dict.fromkeys(p.strip() for p in text.split(";") if p.strip()))

        native_taken = 0
        for text, _ in texts(78, 30000, 24):
            if not helper.group_split_protects(text):
                native_taken += 1
                self.assertEqual(rule.split_reference(text), native(text), repr(text))
        self.assertGreater(native_taken, 10000)

    def old_bound(self, groups, bounds):
        """bound_groups' loop as it stood at 8ff582f, the oracle."""
        out = []
        for name in groups:
            if len(out) >= helper.M3U_MAX_GROUPS_PER_CHANNEL:
                helper.bound_count(bounds, "groupCount")
                break
            name = helper.cut_text(name, helper.M3U_MAX_GROUP, "group", bounds)
            if name and name not in out:
                out.append(name)
        return out

    def test_bound_groups_is_the_loop(self):
        rng = random.Random(5)
        names = ["", "A", "A ", "B", "x" * 127, "x" * 128, "x" * 129, "News http://u:p@h.test/" + "y" * 120,
                 "C", "D", "E"]
        for trial in range(20000):
            groups = [rng.choice(names) if rng.random() < 0.5 else "g%d" % rng.randrange(40)
                      for _ in range(rng.randint(0, 24))]
            got, want = {}, {}
            self.assertEqual((helper.bound_groups(list(groups), got), got),
                             (self.old_bound(list(groups), want), want), groups)
            self.assertEqual(helper.bound_groups(list(groups), None), self.old_bound(list(groups), None), groups)


class IdSubstitutionTest(unittest.TestCase):
    def test_a_list_with_no_url_row_is_its_own_scheme_two(self):
        channels = [{"name": "A", "url": "http://h.test/1", "tvgId": "a.tv"},
                    {"name": "B", "url": "http://h.test/2", "tvgId": "b.tv"}]
        legacy = helper.legacy_channel_ids(channels)
        self.assertEqual(helper.substitute_name_ids(channels, legacy), ["t:a.tv", "t:b.tv"])
        # A copy, as before: the caller may change its answer.
        self.assertIsNot(helper.substitute_name_ids(channels, legacy), legacy)

    def test_one_url_row_still_takes_its_name(self):
        channels = [{"name": "A", "url": "http://h.test/1", "tvgId": "a.tv"},
                    {"name": "Bravo", "url": "http://h.test/2"}]
        legacy = helper.legacy_channel_ids(channels)
        self.assertEqual(helper.substitute_name_ids(channels, legacy),
                         ["t:a.tv", helper.name_id_key("Bravo")])


if __name__ == "__main__":
    unittest.main()
