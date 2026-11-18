"""F-HARNESS-73: the 10,000-channel parse's margin, recovered without moving
one answer.

Three pieces of repeated work in the per-channel path are done once, and each
is held here to the work it stands in front of:

  logo_is_web   make_channel's logo test, `stream_scheme(logo) in ("http",
                "https")`, answered from the text's head where urlsplit can
                read it no other way (an ASCII logo opening above U+0020
                with no TAB, CR, LF, `[` or `]`). Held equal to the urlsplit
                reading over every ASCII character at every place the
                reading turns on, every ASCII pair at the head, every code
                point in the authority, and random texts of the characters
                the reading tells apart.
  entry memo    stream_entry_refusal's rules after the listening one, kept
                within one parse by (scheme, netloc) for every scheme but udp
                and rtp, whose query names hosts. Held equal to the answer
                with no memo over every line of a pool that repeats each
                netloc under other schemes, paths and queries, for every
                kind of playlist; and each input the answer reads is shown
                to move it within one memo.
  group memo    make_channel's reading of a group text (group_reading: the
                groups, what bound_groups counted, their search fold), kept
                within one parse by the text. Held equal to the reading with
                no memo, counts included, over every group-split fixture
                text and the cut, capped and empty shapes.

Each memo is shown TAKEN, so the gate sees it if it is lost (its cost is held
by test_playlist's PerformanceTest), and bounded. The byte identity of the
`playlist` verb's output against fdba6be over the fixtures' address vectors,
every playlist file under tests/ and a seeded corpus is recorded in
docs/QA-RESULTS.md ("F-HARNESS-73: the parse margin (2026-11-18)"), not
re-run here.
"""
import json
import os
import random
import unittest

from helper_loader import load_helper

helper = load_helper()
HERE = os.path.dirname(os.path.abspath(__file__))


def urlsplit_reading(logo):
    return helper.stream_scheme(logo) in ("http", "https")


# The characters urlsplit's scheme reading and its refusals turn on, and
# the ones beside them (built with chr: these sources are ASCII).
TURNING = ["h", "t", "p", "s", "H", "T", "P", "S", "x", ":", "/", "[", "]", "\t", "\n", "\r", "\x00", "\x01",
           "\x1f", " ", "\x7f", "a", "1", "+", "-", ".", "@", "?", "#", "%",
           chr(0x85), chr(0xa0), chr(0x130), chr(0x131), chr(0x212a), chr(0x17f), chr(0xff0f), chr(0xff1a),
           chr(0xff03), chr(0xff1f), chr(0x2100), chr(0xfe6b), chr(0x3002),
           "http", "https", "http:", "https:", "://", "//", "[::1]"]
TEMPLATES = ["http://l.test/a.png", "https://l.test:8080/a.png", "HTTP:", "Https://x", "http:/x", "http",
             "ftp://l.test/a.png", "http://[::1]/a.png", "http://u:p@l.test/a.png", "//l.test/a"]


class LogoSchemeShortcutTest(unittest.TestCase):
    def check(self, logo):
        self.assertEqual(helper.logo_is_web(logo), urlsplit_reading(logo), ascii(logo))

    def test_every_ascii_character_at_every_place(self):
        for template in TEMPLATES:
            for i in range(len(template) + 1):
                for code in range(128):
                    c = chr(code)
                    self.check(template[:i] + c + template[i:])
                    self.check(template[:i] + c + template[i + 1:])

    def test_every_ascii_pair_at_the_head(self):
        for a in range(128):
            for b in range(128):
                head = chr(a) + chr(b)
                for tail in ("", "ttp://l.test/x", "tps://x", "://x", "p:", ":"):
                    self.check(head + tail)

    def test_every_code_point_in_the_authority_and_at_the_head(self):
        # Every BMP code point (as the D-PERF-13 sweeps take them) and one in
        # 61 above it; the authority is where urlsplit's NFKC refusal reads.
        for code in list(range(0x10000)) + list(range(0x10000, 0x110000, 61)):
            if 0xD800 <= code <= 0xDFFF:
                continue
            c = chr(code)
            self.check("http://l" + c + ".test/a.png")
            if code < 0x3400 or code % 61 == 0:
                self.check(c + "http://l.test")
                self.check("http" + c + "://l.test")

    def test_random_texts(self):
        rng = random.Random(73)
        for _ in range(60000):
            self.check("".join(rng.choice(TURNING) for _ in range(rng.randint(0, 12))))

    def test_the_shortcut_is_taken_where_it_can_answer(self):
        calls = []
        slow = helper.stream_scheme

        def counting(url):
            calls.append(url)
            return slow(url)

        helper.stream_scheme = counting
        try:
            for logo, asked in (("http://l.test/a.png", False), ("HTTPS://l.test/a.png", False),
                                ("ftp://l.test/a.png", False), ("http://[::1]/a.png", True),
                                ("ht\ttp://l.test/a.png", True), ("\x01http://l.test", True),
                                ("http://l" + chr(0xff0f) + "x.test/a.png", True)):
                calls.clear()
                helper.logo_is_web(logo)
                self.assertEqual(bool(calls), asked, ascii(logo))
        finally:
            helper.stream_scheme = slow


# Every kind of playlist the parse is handed (playlist_source's), and none.
SOURCES = [
    {"host": "", "local": False},
    helper.playlist_source("file", ""),
    helper.playlist_source("http", "http://provider.example.test/list.m3u", "global", "global"),
    helper.playlist_source("http", "http://cdn.test:8080/list.m3u", "global", "global"),
    helper.playlist_source("http", "http://127.0.0.1/list.m3u", "loopback", "loopback"),
    helper.playlist_source("http", "http://127.0.0.1:8080/list.m3u", "loopback", "loopback"),
    helper.playlist_source("http", "http://10.0.0.5/list.m3u", "private", "private"),
    helper.playlist_source("http", "http://cdn/list.m3u", "unresolved", ""),
]
NETLOCS = ["cdn.test", "cdn.test:8080", "u:p@cdn.test", "CDN.TEST", "cdn", "cdn:80", "localhost", "a.localhost",
           "127.0.0.1", "127.0.0.1:8080", "127.0.0.1:8081", "127.1", "0.0.0.0", "0.0.0.0:8080", "10.0.0.5",
           "192.168.1.1", "239.1.1.1", "@239.1.1.1:1234", "[::1]", "[::1]:8080", "[fe80::1%25eth0]",
           "[fe80::1%251]", "[ff0e::1]:1234", "8.8.8.8", "cdn.test:80:81", "cdn.test:0080", "cdn.test:65536",
           "user;sid.test", "a%40b.test", "q@q@cdn.test", "provider.example.test", "provider.example.test:443",
           "stra" + chr(0xdf) + "e.test", "c" + chr(0xad) + "dn.test", chr(0xff43) + "dn.test"]
SCHEMES = ["http", "https", "HTTP", "rtmp", "rtmps", "rtsp", "srt", "mms", "mmsh", "udp", "rtp", "UDP"]
TAILS = ["/live/1.ts", "/x", "", "?sources=a.test", "?sources=a%25b.test", "?sources=cdn", "?mode=listener",
         "?localport=1", "/a?block=10.0.0.1,10.0.0.2", "#f", "?sources=%5B::1%5Dx"]


def pool(seed, count):
    rng = random.Random(seed)
    return [rng.choice(SCHEMES) + "://" + rng.choice(NETLOCS) + rng.choice(TAILS) for _ in range(count)]


class EntryMemoTest(unittest.TestCase):
    def test_the_memo_answers_as_no_memo_for_every_kind_of_playlist(self):
        lines = pool(5, 6000)
        for source in SOURCES:
            memo = {}
            for url in lines:
                self.assertEqual(helper.stream_entry_refusal(url, source, memo),
                                 helper.stream_entry_refusal(url, source), (url, source))
            self.assertTrue(memo)

    def assert_moves(self, source, first, second):
        """Within ONE memo, `second` (which differs from `first` in one input
        the answer reads) gets its own answer, and the two differ."""
        memo = {}
        a = helper.stream_entry_refusal(first, source, memo)
        b = helper.stream_entry_refusal(second, source, memo)
        self.assertEqual((a, b), (helper.stream_entry_refusal(first, source), helper.stream_entry_refusal(second, source)))
        self.assertNotEqual(a[0], b[0], (first, second))

    def test_its_key_holds_every_input_the_answer_reads(self):
        relay_80 = helper.playlist_source("http", "http://127.0.0.1/list.m3u", "loopback", "loopback")
        relay_8080 = helper.playlist_source("http", "http://127.0.0.1:8080/list.m3u", "loopback", "loopback")
        remote = helper.playlist_source("http", "http://provider.example.test/list.m3u", "global", "global")
        # The scheme: its default port is the relay's own, or not.
        self.assert_moves(relay_80, "http://127.0.0.1/a", "https://127.0.0.1/a")
        # The netloc's port, its host, and a host of one label.
        self.assert_moves(relay_8080, "http://127.0.0.1:8080/a", "http://127.0.0.1:8081/a")
        self.assert_moves(remote, "http://cdn.test/a", "http://10.0.0.5/a")
        self.assert_moves(remote, "http://cdn.test/a", "http://cdn/a")
        self.assert_moves(remote, "http://cdn.test/a", "http://user;sid.test/a")
        # udp's and rtp's query names hosts: two lines on one netloc.
        for scheme in ("udp", "rtp"):
            self.assert_moves(remote, scheme + "://@239.1.1.1:1234?sources=a.test",
                              scheme + "://@239.1.1.1:1234?sources=a%25b.test")
            self.assert_moves(remote, scheme + "://@239.1.1.1:1234?sources=a.test",
                              scheme + "://@239.1.1.1:1234?sources=cdn")

    def test_the_memos_never_outlive_a_parse(self):
        text = "#EXTM3U\n#EXTINF:-1,L\nhttp://10.0.0.5/x\n"
        remote = helper.playlist_source("http", "http://provider.example.test/list.m3u", "global", "global")
        lan = helper.playlist_source("http", "http://10.0.0.9/list.m3u", "private", "private")
        # Each parse is handed memos of its own, empty: the answer reads the
        # playlist, which the key does not hold.
        handed = []
        entry, channel = helper.stream_entry_refusal, helper.make_channel

        def entry_seen(url, source, memo=None):
            handed.append(("entry", len(memo)))
            return entry(url, source, memo)

        def channel_seen(*args):
            handed.append(("group", len(args[-1])))
            return channel(*args)

        helper.stream_entry_refusal, helper.make_channel = entry_seen, channel_seen
        try:
            self.assertEqual(helper.parse_m3u(text, remote)["channels"], [])
            self.assertEqual([c["url"] for c in helper.parse_m3u(text, lan)["channels"]], ["http://10.0.0.5/x"])
            self.assertEqual(helper.parse_m3u(text, remote)["channels"], [])
            self.assertEqual([c["url"] for c in helper.parse_m3u(text, lan)["channels"]], ["http://10.0.0.5/x"])
        finally:
            helper.stream_entry_refusal, helper.make_channel = entry, channel
        entries = [h for h in handed if h[0] == "entry"]
        groups = [h for h in handed if h[0] == "group"]
        self.assertEqual((len(entries), len(groups)), (4, 2))
        self.assertEqual([size for _, size in entries + groups], [0] * 6)

    def counted(self, lines):
        calls = []
        rules = helper._authority_refusal

        def counting(*args):
            calls.append(args[0])
            return rules(*args)

        helper._authority_refusal = counting
        try:
            parsed = helper.parse_m3u(["#EXTM3U"] + lines, SOURCES[2])
        finally:
            helper._authority_refusal = rules
        return parsed, calls

    def test_the_memo_is_taken_and_not_for_udp_or_rtp(self):
        lines = []
        for i in range(200):
            lines += ["#EXTINF:-1,N%d" % i, "http://cdn.test/live/%d.ts" % i]
        parsed, calls = self.counted(lines)
        self.assertEqual((len(parsed["channels"]), len(calls)), (200, 1))
        lines = []
        for i in range(200):
            lines += ["#EXTINF:-1,N%d" % i, "udp://@239.1.1.1:1234?sources=s%d.test" % i]
        parsed, calls = self.counted(lines)
        self.assertEqual((len(parsed["channels"]), len(calls)), (200, 200))

    def test_the_memo_is_bounded(self):
        seen = []
        entry = helper.stream_entry_refusal

        def keeping(url, source, memo=None):
            seen.append(memo)
            return entry(url, source, memo)

        lines = []
        for i in range(helper.PARSE_MEMO_ENTRIES + 50):
            lines += ["#EXTINF:-1,N%d" % i, "http://h%d.test/x" % i, "#EXTINF:-1,M%d" % i, "http://h%d.test/y" % i]
        helper.stream_entry_refusal = keeping
        try:
            parsed = helper.parse_m3u(["#EXTM3U"] + lines, SOURCES[2])
        finally:
            helper.stream_entry_refusal = entry
        self.assertEqual(len(parsed["channels"]), 2 * (helper.PARSE_MEMO_ENTRIES + 50))
        self.assertIs(seen[0], seen[-1])
        self.assertEqual(len(seen[0]), helper.PARSE_MEMO_ENTRIES)


def group_texts():
    with open(os.path.join(HERE, "fixtures", "group-split.json"), encoding="utf-8") as handle:
        texts = [case["text"] for case in json.load(handle)["cases"]]
    texts += ["", ";;;", "News", "News;Sports", "Sports ;News", "A;B;C", "A;C",
              ";".join("g%d" % k for k in range(20)), ";".join("g%d" % k for k in range(16)) + ";g0",
              ";".join(["y" * 200, "z"]), "a;" + "b" * 130, "x" * 600, "UK: News;UK: Sports;UK: News",
              "Group 1;Extra", chr(0xe9) + "t" + chr(0xe9) + ";Caf" + chr(0xe9)]
    return texts


class GroupMemoTest(unittest.TestCase):
    def channel(self, text, extgrp, bounds, memo):
        attrs = {"group-title": text} if text is not None else {}
        return helper.make_channel(attrs, "Name", "http://cdn.test/1", extgrp, {}, {}, [], 1, bounds, memo)

    def test_the_memo_answers_as_no_memo_counts_included(self):
        texts = group_texts()
        rng = random.Random(11)
        memo = {}
        alone, kept = {}, {}
        for _ in range(4000):
            text = rng.choice(texts)
            if rng.random() < 0.3:
                # An #EXTGRP the entry inherits: parse_m3u cuts it once.
                extgrp = helper.cut_text(text, helper.M3U_MAX_GROUP_TEXT, "groupText", None, helper.GROUP_SEPARATOR)
                text = None
            else:
                extgrp = rng.choice(texts)
            self.assertEqual(self.channel(text, extgrp, kept, memo), self.channel(text, extgrp, alone, None),
                             ascii((text, extgrp)))
            self.assertEqual(kept, alone)
        self.assertTrue(alone.get("groupCount") and alone.get("group") and alone.get("groupText"), alone)

    def test_its_key_is_the_group_text_the_entry_reads(self):
        # One memo; entries that differ only in the text they read, whether
        # their own group-title or the #EXTGRP they inherit.
        memo = {}
        self.assertEqual(self.channel("A;B", "", {}, memo)["groups"], ["A", "B"])
        self.assertEqual(self.channel("A;C", "", {}, memo)["groups"], ["A", "C"])
        self.assertEqual(self.channel(None, "X", {}, memo)["group"], "X")
        self.assertEqual(self.channel(None, "Y", {}, memo)["group"], "Y")
        self.assertEqual(self.channel("", "Y", {}, memo)["group"], "Y")
        self.assertEqual(self.channel(None, "", {}, memo)["group"], helper.UNGROUPED)

    def test_the_memo_is_taken_and_bounded(self):
        calls = []
        reading = helper.group_reading

        def counting(text):
            calls.append(text)
            return reading(text)

        lines = ["#EXTM3U"]
        for i in range(300):
            lines += ['#EXTINF:-1 group-title="G%d;Extra",N%d' % (i % 3, i), "http://cdn.test/%d" % i]
        many = ["#EXTM3U"]
        for i in range(helper.PARSE_MEMO_ENTRIES + 20):
            many += ['#EXTINF:-1 group-title="G%d",N%d' % (i, i), "http://cdn.test/%d" % i]
        many += ['#EXTINF:-1 group-title="G%d",again' % (helper.PARSE_MEMO_ENTRIES + 5), "http://cdn.test/again",
                 '#EXTINF:-1 group-title="G5",again', "http://cdn.test/again5"]
        helper.group_reading = counting
        try:
            parsed = helper.parse_m3u(lines, SOURCES[1])
            self.assertEqual((len(parsed["channels"]), len(calls)), (300, 3))
            calls.clear()
            parsed = helper.parse_m3u(many, SOURCES[1])
        finally:
            helper.group_reading = reading
        # Past the bound a text is read again; one kept is not.
        self.assertEqual(len(calls), helper.PARSE_MEMO_ENTRIES + 20 + 1)
        self.assertEqual(parsed["channels"][-2]["group"], "G%d" % (helper.PARSE_MEMO_ENTRIES + 5))


if __name__ == "__main__":
    unittest.main()
