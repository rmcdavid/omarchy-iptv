"""F-SINK-11: the helper's redaction is linear, and says what it used to say.

Two things have to be true at once and only one of them is about speed.

`redact_urls` guards every sink the helper has -- its log lines, its error
payloads, the mpv track fields, the EPG detail text -- and the strings it is
handed are written by the provider. The pattern it used to run,
`\\b([A-Za-z][A-Za-z0-9+.-]*)://[^\\s'"<>]+`, re-read the scheme run from every
word boundary, so its cost was quadratic in a run of scheme-legal characters.
The `\\b` hid the simplest shape of that -- a run of plain letters offers one
word boundary -- which is why the Model.js mirror was measured first and this
side read as cheap. It was not: `.`, `+` and `-` are scheme-legal and are NOT
word characters, so "aaaa." repeated hands the engine a fresh start position
every five characters for a run that reaches the end of the text.

So the first class of test here runs a pattern as an oracle and asserts the
two agree character for character. A redactor that got fast by redacting less
would pass any budget, and "the output is unchanged" is the claim that
actually matters for rule 5. The oracle is a copy of a pattern rather than an
import, because the helper must not carry a second redactor for a test's
benefit; a copy that drifts is caught the moment a vector disagrees. It is
the pattern as ruled today (`_AS_RULED` below: the tail of R32a''', the host
of R32a'), not the one quoted above, and since D-SINK-74 (2026-11-04) it has
no `\\b`. It used to: the copy of the shipped pattern held the scan to the
old answer, and the old answer let a scheme through whole when nothing in its
run could start a match (`1http`, `_http`).

The second class is the budget, best of three against a ceiling many times the
measured cost, in the house style: a wall-clock assertion on a shared machine
has to be loose to be useful, and the margin here is four orders of magnitude.
"""
import json
import os
import re
import time
import unittest

from helper_loader import load_helper

helper = load_helper()

# The pattern as ruled -- the shipped one without its `\b` (D-SINK-74) -- kept
# here and ONLY here. The HOST it prints is
# R32a' (2026-10-22, D-SINK-29), stated independently of the helper so a
# drift in run_host_parts is caught: the RFC authority (up to the first '/',
# '?', '#' or whitespace), its userinfo to the LAST '@' within it, the host
# cut at ':', ';', '=' or '&', a bracketed literal to its ']'; and WITHHELD as
# the one token when that host has no dot and an '@' follows the authority.
# It was helper.url_host (urllib's RFC reading) until R32a, which printed the
# username for a password holding an unencoded '/', '?' or '#' (D-SINK-28);
# R32a's last-'@'-of-the-run scan (round 3, never shipped) printed a password
# TAIL for an '@' inside a path credential (D-SINK-29). R32a'' (D-SINK-32,
# D-SINK-33): `'"<>` are sentence punctuation put back after the host, and a
# NON-NUMERIC port followed by a later '@' withholds too (the second arm,
# D-SINK-35). R32a''' (D-SINK-36): the run and the authority end at the SIX
# ASCII delimiters -- space, tab, LF, CR, FF, VT, spelt out here as a class
# literal independently of the helper's URL_DELIMITER_CHARS -- and at
# nothing else: U+FEFF, NBSP, U+2028, U+0085 and the information separators
# are URL text, and a password holding one redacts to the host (the union
# of JS \\s, Python \\s and U+FEFF is what a READER refuses, not what a
# redactor delimits at; under R32a'' it ended the run here and the helper
# printed the username and the tail for U+FEFF where 0.14.3 printed the
# host).
# D-SINK-74 (2026-11-04): no `\b` in front of the scheme. The shipped pattern
# had one, and this oracle copied it, so `1http://u:p@h/x`, `_http://...` and a
# scheme right after an accented or CJK letter were no URL to either and the
# suite pinned the leak; Model.redactUrls never had it and printed the host.
_WS = "\t\n\x0b\x0c\r "
_AS_RULED = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*)://[^" + _WS + "]+")
_AUTHORITY_END_AS_RULED = re.compile("[/?#" + _WS + "]")
_HOST_END_AS_RULED = re.compile(r"[:;=&]")
_PORT_AS_RULED = re.compile(r"^[^:;=&]*:([^;=&]*)")
HOST_WITHHELD = "[host withheld]"


def host_as_ruled(raw):
    body = raw[raw.find("://") + 3:]
    cut = _AUTHORITY_END_AS_RULED.search(body)
    authority = body if cut is None else body[:cut.start()]
    rest = "" if cut is None else body[cut.start():]
    # The rest up to the first DELIMITER (not str.split, whose class is
    # Python's own whitespace: R32a''').
    rest = re.split("[" + _WS + "]", rest, 1)[0]
    hostport = authority[authority.rfind("@") + 1:]
    if hostport.startswith("["):
        close = hostport.find("]")
        return hostport[:close + 1].lower() if close != -1 else ""
    end = _HOST_END_AS_RULED.search(hostport)
    host = hostport if end is None else hostport[:end.start()]
    port = _PORT_AS_RULED.match(hostport)
    port = port.group(1) if port else ""
    if "@" in rest and ((host and "." not in host) or (port and not port.isdigit())):
        return HOST_WITHHELD
    return host.lower()


def redact_urls_as_ruled(text):
    def replace(match):
        raw = match.group(0)
        bracket = "[" in raw
        trailing = ""
        while raw and raw[-1] in ".,;:!?)]'\"<>" and not (bracket and raw[-1] == "]"):
            trailing = raw[-1] + trailing
            raw = raw[:-1]
        host = host_as_ruled(raw)
        return "%s://%s%s" % (match.group(1).lower(), host or "[redacted]", trailing)

    return _AS_RULED.sub(replace, "" if text is None else str(text))


# D-PERF-6 (R32e): the scheme-run search as it shipped before, kept as the
# oracle for the anchored match that replaced it. `search(s, lo, j)` with
# `\Z` at j: the leftmost start whose run reaches j. Quadratic in a window
# (no literal prefix), which is why it is only ever run here, on short
# ordinary strings.
_SCHEME_RUN_BEFORE = re.compile(r"[A-Za-z0-9+.\-]*\Z")


# Reaches every branch of the scan: scheme characters, the authority
# delimiters, the `@` D-SINK-1 is about, the quotes and angle brackets that are
# trailing punctuation (R32a''), several kinds of whitespace, and non-ASCII.
# Every class the scan asks the engine is ASCII-only -- no `\w` or `\s` is
# left in it -- so non-ASCII is plain text to it.
ALPHABET = "ahHt p:/@?#.+-_019\t\n\xa0\u2028\ufeff\x85\x1cx[]%&=,;'\"<>"


def generated(length, seed):
    out = []
    x = seed
    for _ in range(length):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        out.append(ALPHABET[x % len(ALPHABET)])
    return "".join(out)


# Hand-picked edges the generator will not reach often enough to rely on.
EDGES = [
    "", "a://", "a://h", "://h", ".://h", "-a://h", "123http://h",
    # `_` is a word character and is not scheme-legal, so the old `\b` refused
    # the run's first position behind it; inside a run it took a letter only
    # after `+`, `.` or `-`. Each of these offers neither, and is a URL since
    # D-SINK-74.
    "_aaa://h", "\xe9aaa://h", "0aaa://h", "_http://u:p@h.test/x", "1http://u:p@h.test/x",
    "x 2024http://u:p@h.test/x", "see http://a.test/x 1http://u:p@h.test/x",
    "_HTTP://u:p@h.test/x", "\xe9HTTP://u:p@h.test/x", "1HTTP://u:p@h.test/x",
    "http://u:p@h/x", "http://u:p@q@h/x", "aaahttp://h/x", "a://://b",
    "://://x", "HTTP://H.TEST/A", "ht+tp://h", "ht.tp://h", "1.2.3://h.test",
    "a.b-c+d://h.test/x", "http://h:8080/a?b#c", "http://@h/x", "http://h@/x",
    "http://a@b@c.test/x", "x http://a.test/1 y http://b.test/2 z",
    "a://b c://d", "file:///etc/x", "see http://h.test, then https://i.test.",
    "\xa0http://h.test\xa0y", "aaa://\u2028x", "no urls here", "http://",
    "http://?x",
    # Quotes and angle brackets around a URL: trailing punctuation since
    # R32a'' (they ended the run until then), and inside a password.
    "'http://h.test'", "<http://h.test>", "\"http://h.test\"", "http://myuser:pa'ss@prov.test/x",
    "http://myuser:pa<ss@prov.test/x", "http://myuser:pa\x85ss@h.test/x", "http://myuser:pa\x1css@h.test/x",
    "http://myuser:pa\ufeffss@h.test/x", "http://user.name:pa/ss@h.test/x", "http://me@mail.test:pa&x=1/ss@h.test/x",
    "http://user.name:2024/ab@host/x", "http://h.test:/me@x.test/y", "see 'http://u:p@h.test/x', <http://a.test> and \"http://b.test\".",
    "http://.", "x http://. y", "http://[::1]].", "http://[::1]:pa/me@x", "http://h.test:80x/a@b", "http://:pa/me@x", "http://h.test:;=&/a@b",
    # A "://" the pattern cannot match followed by one it can: the scan has to
    # keep looking past the first, and stopping there leaves a live credential.
    "://x http://u:p@h.test/a", "1://x http://u:p@h.test/a",
    "://h http://a.test/b ://c https://u:p@d.test/e",
    # An `@` in the PATH is not userinfo: the authority ends at the first `/`,
    # so the host is `h.test` and not `b`.
    "http://h.test/a@b/c", "http://u:p@h.test/a@b/c", "http://h.test?a@b",
    # R32a': the withheld shapes, and the dotless hosts that are not.
    "http://myuser:pa#ss@cdn.test/x", "http://myuser:pa/ss@cdn.test/x", "http://nas:8000/me@h/x",
    "http://nas:8080?u=me@b", "http://u:p@nas/x", "http://nas", "http://nas/x", "http://[::1]/me@x",
    "http://h.test=p&x=1/y", "http://h.test;s=p", "x http://nas/a@b. y", "http://nas/a@b\u2028c",
]


def run_of(n):
    return "a" * n


def dotted(n):
    return "aaaa." * (n // 5)


CRED = "http://u5er:p4ss@prov.example.test/live/1.ts"
DOUBLED = "http://u5er:p4@ss@prov.example.test/live/1.ts"


class RedactionIsUnchangedTests(unittest.TestCase):
    def test_the_shared_fixture_still_reads_the_same(self):
        """The D-SINK-1 vectors both languages run, through the oracle."""
        path = os.path.join(os.path.dirname(__file__), "fixtures", "redaction-vectors.json")
        with open(path, encoding="utf-8") as handle:
            doc = json.load(handle)
        self.assertGreaterEqual(len(doc["vectors"]), 8)
        for vector in doc["vectors"]:
            out = helper.redact_urls(vector["text"])
            self.assertEqual(out, redact_urls_as_ruled(vector["text"]), vector["why"])
            self.assertIn(vector["host"], out, vector["why"])
            for fragment in vector["mustNotAppear"]:
                self.assertNotIn(fragment, out, vector["why"])

    def test_every_edge_and_thousands_of_generated_strings_agree(self):
        corpus = list(EDGES)
        for seed in range(1, 3001):
            for length in range(0, 41, 7):
                corpus.append(generated(length, seed))
        # Long strings as well as short, because a BOUNDED scheme run (the
        # `{0,30}` shape that was once proposed as the fix) passes every
        # 40-character vector and fails here.
        for seed in range(1, 201):
            corpus.append(generated(200, seed))
            corpus.append(generated(2000, seed))
            corpus.append("a" * 200 + generated(60, seed))
            corpus.append(generated(60, seed) + "a" * 200 + "http://u:p@h.test/x")
        # A corpus that silently became empty would make this pass by testing
        # nothing, which is the shape rule 14 exists to stop.
        self.assertGreater(len(corpus), 18000)
        mismatches = [text for text in corpus
                      if helper.redact_urls(text) != redact_urls_as_ruled(text)]
        self.assertEqual([repr(t) for t in mismatches[:4]], [])

    def test_d_perf_6_the_anchored_scheme_run_match_starts_where_the_old_search_did(self):
        """R32e: on every window of every ordinary string here, the match's
        end is the old search's start -- the run's first character, or lo
        when the window is all scheme characters."""
        texts = ["http://h.test/x", "aaa!aaa://x", "a.b+c-d://h", "!://", "://", "ab cd://x",
                 "x\ny://h", "aa!aa!aa://h", "\u00e9://h", "+.-://h", "a" * 70 + "://h"]
        for seed in range(1, 300):
            texts.append(generated(40, seed))
            texts.append(generated(24, seed) + "://" + generated(8, seed + 1))
            texts.append(generated(9, seed) + "://" + generated(9, seed + 2) + "://x")
        checked = 0
        for text in texts:
            j = text.find("://")
            while j >= 0:
                for lo in range(0, j + 1):
                    before = _SCHEME_RUN_BEFORE.search(text, lo, j).start()
                    after = helper._SCHEME_RUN_RE.match(text, lo, j).end()
                    self.assertEqual(after, before, (repr(text), lo, j))
                    checked += 1
                j = text.find("://", j + 1)
        self.assertGreater(checked, 2000)

    def test_r32a_the_free_text_host_is_the_rfc_host_or_withheld(self):
        """R32a' (D-SINK-29, D-SINK-28, D-SINK-23): the P1's path and query
        credentials print the HOST (round 3 printed `ssw0rd`); the typo
        shapes withhold it (round 2 printed the username, round 3 the host
        after the later '@'); a pathless query stops at the authority; a
        LAN name with a path '@' is withheld (the stated cost, `localhost`
        too); an unclosed '[' prints nothing."""
        cases = [
            ("Failed to open http://prov.test/live/U5ER/P4@SSW0RD/1.ts.", "Failed to open http://prov.test."),
            ("see http://host.test:25461/get.php?username=me@mail.test&password=p@ssw0rd now.", "see http://host.test now."),
            ("Failed to open http://myuser:pa#ss@cdn.test/live/1.ts.", "Failed to open http://[host withheld]."),
            ("Failed to open http://myuser:pa?ss@cdn.test/live/1.ts.", "Failed to open http://[host withheld]."),
            ("Failed to open http://myuser:pa/ss@cdn.test/live/1.ts.", "Failed to open http://[host withheld]."),
            ("http://user:2024/ab@host.test/list.m3u", "http://[host withheld]"),
            ("http://host?password=x", "http://host"),
            ("http://h.test?u=me@b.test&p=SECRET", "http://h.test"),
            ("http://h.test;sid=SECRET", "http://h.test"),
            ("http://host.test:25461/playlist/me@mail.test/pw/m3u_plus", "http://host.test"),
            ("http://nas:8000/files/me@home/x", "http://[host withheld]"),
            ("http://localhost:8080/me@mail.test/x", "http://[host withheld]"),
            ("http://u:p@nas/x", "http://nas"),
            ("open http://[2001:db8::5 now", "open http://[redacted] now"),
            ("x http://[2001:db8::5]. y", "x http://[2001:db8::5]. y"),
            ("http://[2001:db8::7]/live/me@mail.test/1.ts", "http://[2001:db8::7]"),
            ("http://a@b@c@h.test/me@x", "http://h.test"),
        ]
        for text, want in cases:
            self.assertEqual(helper.redact_urls(text), want, text)
        # The display sinks keep the RFC reading unconditionally: that is the
        # two-rule shape R32a' decides, not a drift.
        self.assertEqual(helper.url_host("http://myuser:pa#ss@cdn.test/live/1.ts"), "myuser")
        self.assertEqual(helper.run_host("http://myuser:pa#ss@cdn.test/live/1.ts"), helper.HOST_WITHHELD)
        self.assertEqual(helper.HOST_WITHHELD, HOST_WITHHELD)

    def test_r32a_host_withheld_is_the_one_predicate_and_the_token_is_fixed(self):
        """R32a': the predicate the form warns with (Model.urlHostWithheld),
        mirrored, over the shapes the node suite pins; the shared source-urls
        fixture runs it in tests/test_source.py."""
        for url, want in [("http://myuser:pa#ss@cdn.test/x", True), ("http://user:2024/ab@host.test/list.m3u", True),
                          ("http://nas:8000/files/me@home/x", True), ("http://localhost/me@x", True), ("http://nas:8080?u=me@b.test", True),
                          ("http://u:p@nas:8080/me@x", True), ("see http://nas/me@x now", True),
                          # R32a'': a dotted host with a NON-NUMERIC port and a later '@' is the second arm
                          ("http://h.test:pa/me@x.test/y", True), ("http://[2001:db8::1]:8080/me@mail.test", False),
                          ("http://[2001:db8::1:x/me@mail.test", False), ("http://u:p@nas", False), ("http://u:p@nas/x?a=1#f", False),
                          ("http://host.test:25461/playlist/me@mail.test/pw/m3u_plus", False), ("http://nas", False),
                          ("nas/me@x", False), ("", False), ("http://h .test/me@x", False), ("http:///me@x", False), ("http://:8080/me@x", False)]:
            self.assertEqual(helper.host_withheld(url), want, url)
        self.assertEqual(helper.run_host_parts("myuser:pa#ss@cdn.test/x"), ("myuser", True))
        self.assertEqual(helper.run_host_parts("u:p@h.test:8080/x"), ("h.test", False))
        self.assertEqual(helper.run_host_parts("[2001:db8::7]:8080/me@x"), ("[2001:db8::7]", False))

    def test_none_and_non_strings_are_unchanged_too(self):
        for value in (None, 42, True, 1.5, [], {}):
            self.assertEqual(helper.redact_urls(value),
                             redact_urls_as_ruled(value), repr(value))


class GluedSchemeTests(unittest.TestCase):
    """D-SINK-74 (2026-11-04): a scheme glued to a word character is a URL,
    whatever stands before its first letter.

    redact_urls asked `\\b` of a scheme's start, as the pattern it replaced
    did. So it found a start only at a letter that was the run's first
    character with no word character before the run, or that followed a `+`,
    `.` or `-` inside the run. A run with neither was no URL to it and went
    out whole: `1http`, or `http` right after `_` or any non-ASCII character
    Python counts as a word character (letters, digits and other numerals
    such as U+00BD). The schemes IPTV uses hold no `+`, `.` or `-` to offer
    a later start. The helper's own outputs carried it, the player's window
    title among them. Model.redactUrls never asked it and printed the host.
    Red on dev 9cce189: every shape below printed the username and the
    password except four. The `a1` control and the two whose first letter
    starts their 300-character run were redacted then too (those two pin the
    run search's window), and `1A.HTTP` printed `1A.http://prov.test`."""

    CRED = "http://u5er:p4ss@prov.test/live/1.ts"
    # Scheme-legal non-letters, more of them than a scan that gives up after
    # a few would cross.
    LONG = "0123456789+-.0123456789"
    # An earlier URL, so the glued one is scanned with `resume` past 0.
    EARLIER = "see http://a.test/x "

    def test_each_glued_shape_prints_the_scheme_and_the_host(self):
        cases = [
            ("1" + self.CRED, "1http://prov.test"),
            ("12" + self.CRED, "12http://prov.test"),
            ("x 2024" + self.CRED, "x 2024http://prov.test"),
            ("1.2-3+4567890" + self.CRED, "1.2-3+4567890http://prov.test"),
            # Long letterless runs: the forward walk crosses all of them.
            ("9" * 70 + self.CRED, "9" * 70 + "http://prov.test"),
            ("9" * 200 + self.CRED, "9" * 200 + "http://prov.test"),
            # The first letter far before `://`: the run search has to look
            # back past its 64-, 128- and 256-character windows to find it.
            ("A" + "0" * 300 + self.CRED[4:], "a" + "0" * 300 + "://prov.test"),
            ("x A" + "9" * 300 + "HTTP" + self.CRED[4:], "x a" + "9" * 300 + "http://prov.test"),
            # Digits or `+.-` inside the scheme, after its first letter.
            ("1s3" + self.CRED[4:], "1s3://prov.test"),
            ("_1A2HTTP" + self.CRED[4:], "_1a2http://prov.test"),
            ("1A.HTTP" + self.CRED[4:], "1a.http://prov.test"),
            # An ASCII name before the glue character: the run starts after it.
            ("ESPN" + chr(0x9891) + chr(0x9053) + "HTTP" + self.CRED[4:], "ESPN" + chr(0x9891) + chr(0x9053) + "http://prov.test"),
            ("CANAL" + chr(0xc9) + self.CRED, "CANAL" + chr(0xc9) + "http://prov.test"),
            ("_" + self.CRED, "_http://prov.test"),
            ("Sports_" + self.CRED, "Sports_http://prov.test"),
            (chr(0xe9) + self.CRED, chr(0xe9) + "http://prov.test"),
            (chr(0x9891) + chr(0x9053) + self.CRED, chr(0x9891) + chr(0x9053) + "http://prov.test"),
            (chr(0x663) + self.CRED, chr(0x663) + "http://prov.test"),
            (chr(0xbd) + self.CRED, chr(0xbd) + "http://prov.test"),
            ("x 1" + self.CRED + ".", "x 1http://prov.test."),
            (self.EARLIER + "1" + self.CRED, "see http://a.test 1http://prov.test"),
            (self.EARLIER + "Sports_" + self.CRED, "see http://a.test Sports_http://prov.test"),
            # A letter at the run's start was always a URL, and still is.
            ("a1" + self.CRED, "a1http://prov.test"),
            # The scheme is lowercased from where it starts, so a scan that
            # started at a LATER letter would print `_Http`.
            ("Sports_HTTP" + self.CRED[4:], "Sports_http://prov.test"),
        ]
        got = [(text, helper.redact_urls(text)) for text, _ in cases]
        self.assertEqual(got, [(text, want) for text, want in cases])

    def test_no_code_point_before_the_scheme_keeps_the_credential(self):
        """Every BMP code point, and a sample past it, in front of the scheme,
        in front of a digit in front of it, in front of LONG in front of it,
        and after an upper-case ASCII name in front of the scheme; each alone
        and behind an earlier URL. The credential never survives, and the
        output is the scheme from the run's first ASCII letter. The scheme is
        upper case on purpose: this side lowercases it from where it starts,
        so a scan that started at a later letter, or an earlier one, shows
        here."""
        letters = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
        legal = letters | set("0123456789+.-")
        points = list(range(0x10000)) + [0x10000, 0x1d400, 0x1d7ce, 0x20000, 0x1f600, 0x10ffff]
        upper = "HTTP" + self.CRED[4:]
        bad = []
        for c in points:
            # Each prefix, and whether the scheme starts at its first character:
            # behind `ESPN` it does whenever the code point is scheme-legal.
            forms = ((chr(c), chr(c) in letters), (chr(c) + "1", chr(c) in letters),
                     (chr(c) + self.LONG, chr(c) in letters), ("ESPN" + chr(c), chr(c) in legal))
            for prefix, whole in forms:
                if whole:
                    shown = (prefix + "HTTP").lower() + "://prov.test"
                else:
                    shown = prefix + "http://prov.test"
                for before, kept in (("", ""), (self.EARLIER, "see http://a.test ")):
                    out = helper.redact_urls(before + prefix + upper)
                    if out != kept + shown or "u5er" in out or "p4ss" in out:
                        bad.append("U+%04X %r -> %r" % (c, before + prefix, out))
        self.assertEqual(bad[:6], [])
        self.assertEqual(len(points), 65542)


class PathologicalOutputTests(unittest.TestCase):
    """The output on the slow inputs, pinned. A fix that got fast by dropping a
    redaction would sail through the budget below."""

    def test_a_long_run_with_no_url_is_returned_verbatim(self):
        self.assertEqual(helper.redact_urls(run_of(20000)), run_of(20000))
        self.assertEqual(helper.redact_urls(dotted(20000)), dotted(20000))

    def test_a_long_run_is_swallowed_as_the_scheme_exactly_as_before(self):
        # Surprising rather than desirable: the old pattern read the run plus
        # `http` as one scheme and kept it, because this renderer emits
        # `scheme://host` and the scheme here is 20,004 characters long. Pinned
        # because changing it is a behaviour change and belongs in its own
        # finding. (The Model.js mirror emits the bare host, so the same input
        # collapses to `prov.example.test` there -- the two renderings differ
        # on purpose and the shared fixture pins the property, not the text.)
        out = helper.redact_urls(run_of(20000) + CRED)
        self.assertEqual(out, run_of(20000) + "http://prov.example.test")
        for fragment in ("u5er", "p4ss", "1.ts"):
            self.assertNotIn(fragment, out)

    def test_a_run_after_a_url_keeps_the_run_and_loses_the_credentials(self):
        out = helper.redact_urls(CRED + " " + run_of(20000))
        self.assertEqual(out, "http://prov.example.test " + run_of(20000))
        for fragment in ("u5er", "p4ss", "1.ts"):
            self.assertNotIn(fragment, out)

    def test_the_dotted_run_is_the_shape_this_side_was_slow_on(self):
        out = helper.redact_urls(dotted(20000) + " " + CRED)
        self.assertEqual(out, dotted(20000) + " http://prov.example.test")

    def test_d_sink_1_holds_when_the_credential_sits_inside_a_long_run(self):
        out = helper.redact_urls(run_of(20000) + " " + DOUBLED)
        self.assertEqual(out, run_of(20000) + " http://prov.example.test")
        for fragment in ("u5er", "p4@ss", "1.ts"):
            self.assertNotIn(fragment, out)

    def test_d_sink_74_a_long_run_with_no_letter_before_the_scheme_is_crossed(self):
        # 20,000 digits before the scheme's only letters: the forward walk
        # crosses them all, so no bound on it under 20,000 survives.
        out = helper.redact_urls("9" * 20000 + CRED)
        self.assertEqual(out, "9" * 20000 + "http://prov.example.test")

    def test_d_sink_74_the_first_letter_20000_characters_back_starts_the_scheme(self):
        # The run's only letter is its first character: the run search has to
        # look back across all 20,000 digits to find it, so no cap on the
        # window it doubles below 32,768 (the doubling that reaches 20,000)
        # survives. A cap leaves a run with no letter, which is no URL, and the
        # credential goes out whole.
        out = helper.redact_urls("A" + "0" * 20000 + CRED[4:])
        self.assertEqual(out, "a" + "0" * 20000 + "://prov.example.test")


class RedactionBudgetTests(unittest.TestCase):
    def test_four_pathological_shapes_at_40000_characters_each_under_100ms(self):
        """Best of three against a ceiling the code clears by four orders of
        magnitude. The pattern this replaced spent 2826.2 ms on the dotted
        shape at this size, so this goes red on it even on a machine twenty
        times slower than the one it was written on."""
        shapes = {
            "letters, no URL": run_of(40000),
            "letters then a URL": run_of(40000) + CRED,
            "a URL then letters": CRED + " " + run_of(40000),
            "dotted, no URL": dotted(40000),
        }
        slow = {}
        for name, text in shapes.items():
            best = float("inf")
            for _ in range(3):
                started = time.perf_counter()
                helper.redact_urls(text)
                best = min(best, time.perf_counter() - started)
            if best >= 0.100:
                slow[name] = round(best * 1000, 1)
        self.assertEqual(slow, {})

    def test_the_cost_does_not_square_when_the_input_doubles(self):
        """The property, not one number. Quadratic means four times the cost
        for twice the input; this asserts well under that, with a floor so a
        measurement in the noise cannot fail it. The old pattern measured
        174.5 ms at 10,000 and 705.5 at 20,000, a ratio of 4.04."""
        def best_of(text):
            best = float("inf")
            for _ in range(5):
                started = time.perf_counter()
                helper.redact_urls(text)
                best = min(best, time.perf_counter() - started)
            return best
        small = best_of(dotted(10000))
        large = best_of(dotted(40000))
        # Four times the input. Linear predicts 4x, quadratic predicts 16x.
        self.assertLess(large, max(8.0 * small, 0.050),
                        "%.4f ms at 10,000 -> %.4f ms at 40,000" % (small * 1000, large * 1000))


if __name__ == "__main__":
    unittest.main()
