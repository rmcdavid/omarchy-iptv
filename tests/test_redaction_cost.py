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
# D-SINK-95 and D-SINK-96 (2026-11-11): the reading as ONE leftmost pattern,
# its classes spelt here and nowhere else -- X (CROSSABLE) everything outside
# U+0020..U+007E; F (FILLER) X but the slash look-alikes; K (STAND_IN) F above
# U+009F but the reader's space union; S (SLASH) `/` or a look-alike; and,
# since the review of cbd6679 (2026-11-12), D the deleted controls and W a
# WIDE code point (above U+009F), at most one of which any stretch the
# reading crosses may hold:
#   scheme  a letter and scheme characters, then crossable runs of at most
#           one W, each followed by letterless scheme characters, the last
#           possibly by the mark (the walk crosses only out of a letterless
#           segment);
#   mark    the whole run of `:` and F before the first S (nothing of it
#           before it), whose stretches between colons hold at most one W,
#           holding a `:` or being one K; then S, F holding at most one W, S;
#   run     to the first of the six delimiters, possibly empty.
# Matched left to right without overlap. A credential is a run of characters
# other than U+0020 that holds a `:` outside every match with an `@` after it,
# with at most one counted character (W but no look-alike) outside the
# matches between them (credentials_as_ruled); it is withheld from the run's
# start, or after the last counted character before that `:` when there are
# two or more, and a match inside it prints nothing. A match prints its scheme
# and `://` only when the scheme is a NAMED one, then its host.
_WS = "\t\n\x0b\x0c\r "
_SA_AS_RULED = "".join(map(chr, (0x1735, 0x2041, 0x2044, 0x2215, 0x2571, 0x27CB, 0x29F8, 0x2F03, 0x3033, 0x31D3,
                                 0xFF0F)))
_D = "[\x00-\x1f\x7f-\x9f]"
_W = "[^\x00-\x9f]"
_WF = "[^\x00-\x9f" + _SA_AS_RULED + "]"
_K = ("[^\x00-\x9f" + "".join(map(chr, (0xA0, 0x1680, *range(0x2000, 0x200B), 0x2028, 0x2029, 0x202F, 0x205F,
                                          0x3000, 0xFEFF))) + _SA_AS_RULED + "]")
_S = "[/" + _SA_AS_RULED + "]"
_CROSS = "(?:" + _D + "*" + _W + _D + "*|" + _D + "+)"
_STRETCH = "(?:" + _D + "*(?:" + _WF + _D + "*)?)"
_AS_RULED = re.compile("([A-Za-z][A-Za-z0-9+.\\-]*(?:" + _CROSS + "[0-9+.\\-]+)*" + _CROSS + "?)"
                       "(?<![^ -9;-~" + _SA_AS_RULED + "])"
                       "(" + _STRETCH + "(?::" + _STRETCH + ")+|" + _D + "*" + _K + _D + "*)"
                       + _S + _STRETCH + _S + "([^" + _WS + "]*)")
_NAMED_AS_RULED = {"http", "https", "rtmp", "rtmps", "rtsp", "udp", "rtp", "mms", "mmsh", "srt", "file", "ftp", "ftps",
                   "sftp", "data", "smb", "rtmpe", "rtmpt", "mmst", "tcp", "tls", "magnet", "acestream"}
_AUTHORITY_END_AS_RULED = re.compile("[/?#" + _WS + "]")
_HOST_END_AS_RULED = re.compile(r"[:;=&]")
_PORT_AS_RULED = re.compile(r"^[^:;=&]*:([^;=&]*)")
HOST_WITHHELD = "[host withheld]"


def host_as_ruled(body):
    cut = _AUTHORITY_END_AS_RULED.search(body)
    authority = body if cut is None else body[:cut.start()]
    rest = "" if cut is None else body[cut.start():]
    # The rest up to the first DELIMITER (not str.split, whose class is
    # Python's own whitespace: R32a''').
    rest = re.split("[" + _WS + "]", rest, 1)[0]
    hostport = authority[authority.rfind("@") + 1:]
    if hostport.startswith("["):
        close = hostport.find("]")
        return look_alike_cut(hostport[:close + 1].lower() if close != -1 else "")
    end = _HOST_END_AS_RULED.search(hostport)
    host = hostport if end is None else hostport[:end.start()]
    port = _PORT_AS_RULED.match(hostport)
    port = port.group(1) if port else ""
    bad_port = port and not port.isdigit()
    if "@" in rest and ((host and "." not in host) or bad_port):
        return HOST_WITHHELD
    # The review of cbd6679: a non-numeric port behind a userinfo is withheld
    # too, at a redactor's print.
    if bad_port and "@" in authority:
        return HOST_WITHHELD
    return look_alike_cut(host.lower())


def look_alike_cut(host):
    """D-SINK-95: the printed host stops at its first slash look-alike."""
    for i, c in enumerate(host):
        if c in _SA_AS_RULED:
            return host[:i]
    return host


def trailing_as_ruled(raw):
    bracket = "[" in raw
    trailing = ""
    while raw and raw[-1] in ".,;:!?)]'\"<>" and not (bracket and raw[-1] == "]"):
        trailing = raw[-1] + trailing
        raw = raw[:-1]
    return raw, trailing


def credentials_as_ruled(s, matches):
    """(start, end) of every withheld span: the rule above, a character at a
    time."""
    spans = [m.span() for m in matches]

    def outside(i):
        return not any(a <= i < b for a, b in spans)

    def counted(i):
        return ord(s[i]) > 0x9F and s[i] not in _SA_AS_RULED and outside(i)

    out = []
    for token in re.finditer("[^ ]+", s):
        i, j = token.span()
        for c in range(i, j):
            if s[c] != ":" or not outside(c):
                continue
            at = s.find("@", c + 1, j)
            if at < 0:
                break
            if sum(1 for x in range(c + 1, at) if counted(x)) > 1:
                continue
            before = [x for x in range(i, c) if counted(x)]
            start = i if len(before) <= 1 else before[-1] + 1
            out.append((start, start + len(trailing_as_ruled(s[start:j])[0]), j))
            break
    return out


def redact_urls_as_ruled(text):
    s = "" if text is None else str(text)
    matches = list(_AS_RULED.finditer(s))
    held = credentials_as_ruled(s, matches)
    out, pos = [], 0
    for match in matches:
        if any(a <= match.start() < t for a, _, t in held):
            continue
        for a, b, _ in held:
            if pos <= a < match.start():
                out.append(s[pos:a] + HOST_WITHHELD)
                pos = b
        run, trailing = trailing_as_ruled(match.group(3))
        scheme = re.sub("[^ -~]", "", match.group(1)).lower()
        shown = host_as_ruled(run) or "[redacted]"
        out.append(s[pos:match.start()] + (scheme + "://" if scheme in _NAMED_AS_RULED else "") + shown + trailing)
        pos = match.end()
    for a, b, _ in held:
        if a >= pos:
            out.append(s[pos:a] + HOST_WITHHELD)
            pos = b
    out.append(s[pos:])
    return "".join(out)


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
ALPHABET = list("ahHt p:/@?#.+-_019\t\n\xa0\u2028\ufeff\x85\x1cx[]%&=,;'\"<>") + [
    # D-SINK-95 and D-SINK-96 (2026-11-11): a STAND_IN, a look-alike colon and
    # slashes, a crossed control and an astral character before a mark, a
    # control inside one, a token, a letterless mark and a token whose line
    # separator stands before a `//`.
    "http:" + chr(0x200B) + "//", "http" + chr(0xFF1A) + "//", "http:" + chr(0x2215) * 2, "http" + chr(0x2215) + "://",
    "http" + chr(0xE0001) + "://", ":" + chr(1) + "//", "a:b@", "1://", "qqqqqq:zz" + chr(0x2028) + "//zz@",
    chr(0x200B), chr(0xFF1A), chr(0x2215), chr(0x7F),
    # The review of cbd6679 (2026-11-12): a mark with an empty run before a
    # delimiter, two odd characters in one stretch (P, between the slashes,
    # a crossed run), a mark inside a password, and a colon and an at-sign
    # around a delimiter.
    "a" + chr(0x200B) + chr(0x2215) * 2 + "\t", ":" + chr(0xE9) + "/" + chr(0xE9) + "/", chr(0x4E2D) * 2,
    "qqqqqq:zz" + chr(0xE9) + "//zz@", "\t:@", chr(0xE9) * 2 + "//", "http" + chr(0xE9) * 2 + "://"]


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
    # D-SINK-95 and D-SINK-96 (2026-11-11): the composites, alone and before a
    # credential.
    "http:" + chr(0x200B) + "//qqqqqq:zzzzzz@cdn.test/x", "http" + chr(0xFF1A) + "//cdn.test/live/qqqqqq/zzzzzz/1.ts",
    "http:" + chr(0x2215) * 2 + "cdn.test/live/qqqqqq/zzzzzz/1.ts", "http" + chr(0x2215) + "://cdn.test/live/q/z/1.ts",
    "http" + chr(0xE0001) + "://cdn.test/live/q/z/1.ts", ":" + chr(1) + "//cdn.test/x", "a:b@", "1://", "x a:b@c y",
    "qqqqqq:zz" + chr(0x2028) + "//zz@cdn.test/x", "http://cdn.test" + chr(0xFF0F) + "live" + chr(0xFF0F) + "q",
    "http:/" + chr(0x2215) + "/cdn.test/x", "abc:http://u:p@h.test/x", "http@://u:p@h.test/x", "(u:p@h.test).",
    # The review of cbd6679 (2026-11-12): every input its findings quote.
    "News qqqqqq:zz" + chr(0xE9) + "//zz@cdn.test/x HD", "News qqqqqq:zz" + chr(0x200B) + "//zz@cdn.test/x HD",
    "News qqqqqq:zz://zz@cdn.test/x HD", "News qqqqqq:zz" + chr(0xE9) + chr(0x2215) * 2 + "zz@cdn.test/x HD",
    "News qqqqqq:zz" + chr(0xE9) + ":/" + chr(0xE9) + "/zz@cdn.test/x HD",
    "News qqqqqq:" + chr(0x200B) + "//zzzzzz@cdn.test HD", "qqqqqq:" + chr(0x2215) * 2 + "zzzzzz@cdn.test",
    "News qqqqqq:http://\tzzzzzz@cdn.test HD", "News http://\t:@qqqqqq:zzzzzz HD",
    "News http://\t@cdn.test/live/qqqqqq/zzzzzz/1.ts HD",
    "News a" + chr(0x200B) + chr(0x2215) * 2 + "\t:" + chr(0x200B) + "//cdn.test/live/qqqqqq/zzzzzz/1.ts HD",
    "News qqqqqq:zzzzzz" + chr(0x2215) + "://\t@cdn.test/live/1.ts HD", "Featuring:\n// The Band",
    "NHK" + chr(0x7DCF) + chr(0x5408) + "//BS", "a" + chr(0x4E2D) * 300 + ":b@c", "http://me@h.test:pa x",
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

    def test_a_non_numeric_port_behind_a_userinfo_is_withheld_where_a_redactor_prints_only(self):
        """The review of cbd6679 (its still-shows finding 3): the sinks that
        delete controls read `http://<TAB>:@qqqqqq:zzzzzz` as the run
        `:@qqqqqq:zzzzzz`, host `qqqqqq` and port `zzzzzz`, and printed the
        username. A redactor's print withholds a non-numeric port behind a
        userinfo now; the predicate the Sources form warns with, and the host
        a stored record shows, do not move. Red on cbd6679: the print gave
        `qqqqqq`."""
        self.assertEqual(helper.run_host_parts(":@qqqqqq:zzzzzz", True), ("qqqqqq", True))
        self.assertEqual(helper.run_host_parts(":@qqqqqq:zzzzzz"), ("qqqqqq", False))
        self.assertEqual(helper.host_withheld("http://:@qqqqqq:zzzzzz"), False)
        self.assertEqual(helper.host_withheld("http://me@h.test:pa"), False)
        self.assertEqual(helper.run_host("http://me@h.test:pa"), HOST_WITHHELD)
        self.assertEqual(helper.redact_urls("News http://:@qqqqqq:zzzzzz HD"), "News http://[host withheld] HD")
        self.assertEqual(helper.player_title_text("News http://\t:@qqqqqq:zzzzzz HD"), "News http://[host withheld] HD")
        # A numeric port, or none, behind a userinfo prints as it did.
        self.assertEqual(helper.redact_urls("http://u:p@h.test:8080/x"), "http://h.test")
        self.assertEqual(helper.redact_urls("http://u:p@nas"), "http://nas")

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
    run search's window), and `1A.HTTP` printed `1A.http://prov.test`.

    Since the review of cbd6679 (D-SINK-94's sibling, rule 15) the scheme
    prints only when NAMED_SCHEMES lists it, so a scheme that took in the
    letters glued before it (`a1http`, `s3`, `a2http`, `a.http`, `a000...`)
    prints the host alone, as the model does, where it printed itself; and a
    `:` right before the scheme makes the whole token a credential
    (D-SINK-96 across the URL, `abc:http://u:p@h` withheld whole), which the
    sweep below expects."""

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
            ("A" + "0" * 300 + self.CRED[4:], "prov.test"),
            ("x A" + "9" * 300 + "HTTP" + self.CRED[4:], "x prov.test"),
            # Digits or `+.-` inside the scheme, after its first letter.
            ("1s3" + self.CRED[4:], "1prov.test"),
            ("_1A2HTTP" + self.CRED[4:], "_1prov.test"),
            ("1A.HTTP" + self.CRED[4:], "1prov.test"),
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
            ("a1" + self.CRED, "prov.test"),
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
                if c == 0x3A:
                    # `:` and then the scheme: one credential token, the
                    # URL's userinfo its `@` (the review of cbd6679).
                    shown = HOST_WITHHELD
                elif whole:
                    # The scheme took in the prefix and is no named one.
                    shown = "prov.test"
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
        # Since the review of cbd6679 a scheme prints only from NAMED_SCHEMES,
        # so the two renderings now agree on this one.
        self.assertEqual(out, "prov.example.test")
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
        self.assertEqual(out, "prov.example.test")


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



class MarkBudgetTests(unittest.TestCase):
    """D-SINK-95 and D-SINK-96 (2026-11-11): the wide reading and the token
    arm are linear too, through redact_urls and fold_space. Each shape at
    40,000 characters under 100 ms, best of three, and four times the input
    costs under eight times the time (plus a 5 ms floor), best of five.
    `1://` repeated was quadratic in the shipped redactor, which read each
    URL's run before its scheme: 2.2 s at 40,000 characters. The look-alike
    shape is quadratic without the dead bound on the scheme walk: 842 ms at
    10,000 characters in the prototype.

    The review of cbd6679 added five. `a` and then `<U+200B><U+2215><U+2215>`
    and a delimiter repeated (and its LF, digit-led and delimiter-led units)
    was quadratic in redact_urls, whose reading needed a run: a walk that
    found a scheme for an empty run moved no bound, so every later walk
    crossed back to the `a` (13 s at 40,001 characters; 785 ms at 10,000
    under the heavy lock); red on cbd6679 here. `<U+200B><U+2215>` repeated
    was linear but the slowest unit, a regex call per candidate (60 ms at
    40,000, and 1.5 s at 1M on the guide's path, EpgPathBudgetTests). The
    candidate with no letter before it is not walked now, and no candidate
    before the next letter is asked."""

    Z, D, DEL = chr(0x200B), chr(0x2215), chr(0x7F)
    SHAPES = {
        "1:// repeated": lambda n: ("1://" * (n // 4 + 1))[:n],
        "1111111:/DEL/ repeated": lambda n: ("1111111:/" + chr(0x7F) + "/") * (n // 11),
        "a:b@ repeated": lambda n: "a:b@ " * (n // 5),
        "ZW 1 repeated, then ://x": lambda n: (chr(0x200B) + "1") * (n // 2) + "://x",
        "http:/ and a run of ZW": lambda n: "http:/" + chr(0x200B) * n,
        "1 ZW division slash twice, repeated": lambda n: ("1" + chr(0x200B) + chr(0x2215) * 2) * (n // 4),
        "token TAB url TAB repeated": lambda n: "a:b@c\thttp://x\t" * (n // 15),
        "ZW //a TAB repeated, then :": lambda n: (chr(0x200B) + "//a\t") * (n // 5) + ":",
        "a, then ZW division slash twice TAB repeated": lambda n: "a" + (chr(0x200B) + chr(0x2215) * 2 + "\t") * (n // 4),
        "a, then ZW fullwidth solidus twice LF repeated": lambda n: "a" + (chr(0x200B) + chr(0xFF0F) * 2 + "\n") * (n // 4),
        "a, then 1 ZW division slash twice TAB repeated": lambda n: "a" + ("1" + chr(0x200B) + chr(0x2215) * 2 + "\t") * (n // 5),
        "a, then TAB ZW division slash twice repeated": lambda n: "a" + ("\t" + chr(0x200B) + chr(0x2215) * 2) * (n // 4),
        "ZW division slash repeated": lambda n: (chr(0x200B) + chr(0x2215)) * (n // 2),
        # One credential whose `@` ends the text, across one URL every six
        # characters: the cut reads it only in a window past its limit.
        "one credential across many URLs": lambda n: "q:" + ("a" + chr(0x200B) + "//b\t") * (n // 6) + "@h",
        "credential across URLs repeated": lambda n: ("q:z" + chr(0xE9) + "//z@h ") * (n // 9),
    }

    def best(self, f, text, k):
        best = float("inf")
        for _ in range(k):
            started = time.perf_counter()
            f(text)
            best = min(best, time.perf_counter() - started)
        return best

    def test_every_shape_at_40000_characters_under_100ms(self):
        slow = {}
        for name, shape in self.SHAPES.items():
            for fname, f in (("redact_urls", helper.redact_urls), ("fold_space", helper.fold_space)):
                cost = self.best(f, shape(40000), 3)
                if cost >= 0.100:
                    slow[(name, fname)] = round(cost * 1000, 1)
        self.assertEqual(slow, {})

    def test_the_cost_does_not_square_when_the_input_doubles(self):
        bad = {}
        for name, shape in self.SHAPES.items():
            for fname, f in (("redact_urls", helper.redact_urls), ("fold_space", helper.fold_space)):
                small, large = self.best(f, shape(10000), 5), self.best(f, shape(40000), 5)
                if large >= max(8.0 * small, 0.005):
                    bad[(name, fname)] = "%.2f ms -> %.2f ms" % (small * 1000, large * 1000)
        self.assertEqual(bad, {})


class LetterlessBudgetTests(unittest.TestCase):
    """The review of cbd6679 (its cost finding 3): every look-alike pair is a
    candidate mark, and each was walked for a scheme, so `<U+200B><U+2215>`
    repeated cost about 1.5 us a character in redact_urls (1.5 s at 1M). A
    walk with no ASCII letter between its bound and its P finds no scheme,
    so it is not taken now, and the search goes on from the next letter: a
    million characters of the look-alike shapes with no letter in them cost
    at most 150 ms, best of three. Red on cbd6679, and on this tree without
    the shortcut."""

    def test_a_text_with_no_letter_costs_no_walk(self):
        z, d = chr(0x200B), chr(0x2215)
        shapes = {"ZW division slash repeated": (z + d) * 500000,
                  "1 ZW division slash twice repeated": ("1" + z + d + d) * 250000,
                  "TAB ZW division slash twice repeated, after one letter": "a" + ("\t" + z + d + d) * 250000}
        slow = {}
        for name, text in shapes.items():
            for fname, f in (("redact_urls", helper.redact_urls), ("fold_space", helper.fold_space)):
                cost = MarkBudgetTests.best(None, f, text, 3)
                if cost >= 0.150:
                    slow[(name, fname)] = round(cost * 1000, 1)
        self.assertEqual(slow, {})


class EpgPathBudgetTests(unittest.TestCase):
    """The review of cbd6679 (its cost finding 3): the guide's cleaners ran
    fold_space over a whole <title> or <desc> before their cut, and
    element_text caps nothing, so `<U+200B><U+2215>` repeated cost 1,551 ms
    at 1M characters through clean_detail and 6,263 ms at 4M, where 0.18.0
    took 31 and 123. They cut the raw text first now (EPG_RAW_FACTOR, by
    cut_free_text, which drops no more than the item it would cut), so every
    budget shape stays at most 150 ms at 1M characters and 600 ms at 4M,
    best of three, through clean_detail at the description's cap and
    clean_title. Red on cbd6679 on the look-alike shapes."""

    def test_every_budget_shape_through_the_guides_cleaners(self):
        slow = {}
        for name, shape in MarkBudgetTests.SHAPES.items():
            for size, ceiling in ((1000000, 0.150), (4000000, 0.600)):
                text = shape(size)
                for fname, f in (("clean_detail", lambda t: helper.clean_detail(t, helper.EPG_MAX_DESC)),
                                 ("clean_title", helper.clean_title)):
                    cost = MarkBudgetTests.best(None, f, text, 3)
                    if cost >= ceiling:
                        slow[(name, size, fname)] = round(cost * 1000, 1)
        self.assertEqual(slow, {})


if __name__ == "__main__":
    unittest.main()
