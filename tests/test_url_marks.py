"""D-SINK-95 and D-SINK-96 (2026-11-11): one reading of a URL and of a
credential token in free text, in both mirrors.

Both redactors found a credential only behind an unbroken `scheme://`. Any
character that is not a scheme character between the scheme and its `:`, or
inside the `://` -- a control, a character drawn with no width, a combining
mark, a fullwidth colon, a slash look-alike -- hid the whole URL from both,
so a provider's channel name, group or programme text showed the username
and the password in the guide row, the channel wall, the bar, the accessible
names, the IPC replies and the helper's stderr; the window title and the
notification, which delete controls before they redact, read a URL where
the row did not (D-SINK-95). And a `user:pass@host` with no scheme at all
was never redacted (D-SINK-96).

tests/fixtures/url-mark.json is the one fixture both suites run; here, the
helper: every vector through redact_urls, player_title_text and fold_space,
the slash look-alike list and the three classes over every code point (by
what next_url reads, not by a pattern), the position fuzz against the
fixture's exact leak sets, and the two mirrors' URL and token spans over a
generated corpus, with node computing the model's.

The review of cbd6679 (2026-11-12) restated three parts, each red there: a
credential is read across the URLs in its token, with at most one counted
code point between its `:` and its `@` (TokenSweepTest, CapsTest); each
stretch the mark's reading crosses holds one WIDE code point (CapsTest); and
an empty run is a URL to both mirrors, so the plain, deleting and folded
sinks agree over several insertions (MultiInsertTest). The helper prints a
scheme only from NAMED_SCHEMES (the fixture's vectors).
"""
import json
import os
import re
import subprocess
import unittest

import url_reading_rule as rule
from helper_loader import load_helper

helper = load_helper()
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
with open(os.path.join(HERE, "fixtures", "url-mark.json"), "rb") as fh:
    FIXTURE_BYTES = fh.read()
FIXTURE = json.loads(FIXTURE_BYTES.decode("ascii"))
with open(os.path.join(HERE, "fixtures", "url-whitespace.json"), encoding="utf-8") as fh:
    WHITESPACE = json.load(fh)
SLASH_ALIKE = {int(u[2:], 16) for u in FIXTURE["slashAlike"]}
SPACES_ABOVE_C1 = {int(e["code"][2:], 16) for e in WHITESPACE["codePoints"]} - set(range(0xA0))
SCHEME = set(map(ord, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+.-"))


def crossable(c):
    return c < 0x20 or c > 0x7E


def filler(c):
    return crossable(c) and c not in SLASH_ALIKE


def stand_in(c):
    return filler(c) and c > 0x9F and c not in SPACES_ABOVE_C1


def leaks(text):
    return "q" in text or "z" in text


def fold_redact(text):
    return helper.redact_urls(helper.fold_space(text))


class FixtureTest(unittest.TestCase):
    def test_the_fixture_is_ascii_and_whole(self):
        self.assertTrue(all(b < 0x80 for b in FIXTURE_BYTES))
        vectors = FIXTURE["vectors"]
        self.assertGreaterEqual(len(vectors), 122)
        # Each half of the rule is there: broken marks that now redact,
        # tokens, the residuals, the accepted false positives, and the lines
        # the review of cbd6679 found changed that the caps keep.
        self.assertGreaterEqual(len([v for v in vectors if v["why"].startswith("D-SINK-95")]), 32)
        self.assertGreaterEqual(len([v for v in vectors if v["why"].startswith("D-SINK-96")]), 23)
        self.assertGreaterEqual(len([v for v in vectors if "residual" in v["why"]]), 17)
        self.assertGreaterEqual(len([v for v in vectors if v["why"].startswith("false positive")]), 10)
        self.assertGreaterEqual(len([v for v in vectors if "hand-written guide text" in v["why"]]), 19)
        self.assertEqual(FIXTURE["fuzz"]["totals"], {"plain": 557, "deleting": 442, "fold": 557})
        self.assertEqual(len(FIXTURE["fuzz"]["leaks"]), 54)

    def test_every_vector_reads_as_the_fixture_says_at_every_helper_sink(self):
        bad = []
        for v in FIXTURE["vectors"]:
            text = v["text"]
            for sink, got, want in (("redact_urls", helper.redact_urls(text), v["py"]),
                                    ("player_title_text", helper.player_title_text(text), v.get("pyDeleting", v["py"])),
                                    ("fold_space", fold_redact(text), v.get("pyFold", v["py"]))):
                if got != want:
                    bad.append((v["why"], sink, ascii(got)))
        self.assertEqual(bad, [])

    def test_the_slash_look_alikes_are_the_fixtures(self):
        self.assertEqual(sorted(map(ord, helper.SLASH_ALIKE_CHARS)), sorted(SLASH_ALIKE))
        self.assertEqual(len(SLASH_ALIKE), 11)
        # And redaction_can_change holds on a text of one code point exactly
        # when it is a SLASH.
        wrong = [hex(c) for c in range(0x110000)
                 if helper.redaction_can_change(chr(c)) != (c == 0x2F or c in SLASH_ALIKE)]
        self.assertEqual(wrong[:6], [])

    def test_the_three_classes_over_every_code_point(self):
        """FILLER, STAND_IN and CROSSABLE as next_url reads them, against
        the rule recomputed from the fixture and url-whitespace.json. FILLER
        between a mark's slashes; a STAND_IN in place of its colon; a
        CROSSABLE character between a scheme and a letterless segment
        before its `:`."""
        wrong = []
        for c in range(0x110000):
            ch = chr(c)
            url = helper.next_url("a:/" + ch + "/b", 0, 0, False)
            if (url is not None and url[2] == 5) != filler(c):
                wrong.append(("FILLER", hex(c)))
            if (helper.next_url("a" + ch + "//b", 0, 0, False) is not None) != (stand_in(c) or ch == ":"):
                wrong.append(("STAND_IN", hex(c)))
            url = helper.next_url("http" + ch + "1://b", 0, 0, False)
            if (url is not None and url[0] == 0 and c not in SCHEME) != crossable(c):
                wrong.append(("CROSSABLE", hex(c)))
        self.assertEqual(wrong[:6], [])
        self.assertEqual(sum(1 for c in range(0x110000) if stand_in(c)), 0x110000 - 0xA0 - len(SPACES_ABOVE_C1) - 11)


class FuzzTest(unittest.TestCase):
    """Every code point the fuzz names, inserted at each of 54 positions of
    four credentialed texts, through the plain sinks, the deleting sinks and
    fold-then-redact. The fixture holds the exact leak sets over the whole
    BMP; here every 7th code point and all of ASCII are run (the node suite
    runs every BMP code unit against the same sets), so the two mirrors'
    leak sets are the fixture's. 0.18.0 leaked 1,142,679 of the 3,428,136
    plain inputs; cbd6679, 567; this tree, 557."""

    @classmethod
    def setUpClass(cls):
        fuzz = FIXTURE["fuzz"]
        head, tail = fuzz["wrap"]
        cls.sample = [c for c in range(0x10000) if (c < 0x80 or c % 7 == 0)
                      and not 0xD800 <= c <= 0xDFFF and chr(c) not in fuzz["skip"]]
        cls.got = {}
        for name, (url, positions) in fuzz["urls"].items():
            for pos in positions:
                sets = {"plain": [], "deleting": [], "fold": []}
                for c in cls.sample:
                    text = head + url[:pos] + chr(c) + url[pos:] + tail
                    for sink, f in (("plain", helper.redact_urls), ("deleting", helper.player_title_text),
                                    ("fold", fold_redact)):
                        if leaks(f(text)):
                            sets[sink].append(c)
                cls.got["%s@%d" % (name, pos)] = sets

    def test_the_leak_sets_are_the_fixtures(self):
        sample = set(self.sample)
        bad = [(key, sink) for key, want in FIXTURE["fuzz"]["leaks"].items() for sink in ("plain", "deleting", "fold")
               if self.got[key][sink] != [c for c in want[sink] if c in sample]]
        self.assertEqual(bad, [])

    def test_the_fixtures_sets_are_the_rule(self):
        # No code point above U+007E leaks anywhere; the deleting sinks and
        # the fold leak only where the plain sinks do; and the plain sinks
        # leak where the deleting ones do not only for U+0009..U+000D, the
        # delimiters a deleting sink deletes (R32a''', D-SINK-34).
        leaks_ = FIXTURE["fuzz"]["leaks"]
        above = [(k, s) for k, v in leaks_.items() for s in v if any(c > 0x7E for c in v[s])]
        self.assertEqual(above, [])
        for key, v in leaks_.items():
            plain, deleting, fold = set(v["plain"]), set(v["deleting"]), set(v["fold"])
            self.assertLessEqual(deleting, plain, key)
            self.assertLessEqual(fold, plain, key)
            self.assertLessEqual(plain - deleting, set(range(0x09, 0x0E)), key)
        # The pinned residuals, as the rule names them: before the colon, the
        # 29 printable non-scheme ASCII characters but `:` (a second colon
        # joins P); inside the mark, printable ASCII but the four skipped
        # letters, `/` and `@` (a token then) and, before the slashes, `:`;
        # inside the run, the six delimiters; inside a token, U+0020.
        printable = set(range(0x20, 0x7F)) - set(map(ord, FIXTURE["fuzz"]["skip"]))
        non_scheme = printable - SCHEME
        for key in ("path@4", "query@4"):
            for sink in ("plain", "deleting", "fold"):
                self.assertEqual(set(leaks_[key][sink]), non_scheme - {0x3A}, (key, sink))
        for key, kept in (("path@5", ":/@"), ("path@6", "/@"), ("query@5", ":/@"), ("query@6", "/@")):
            self.assertEqual(set(leaks_[key]["plain"]), printable - set(map(ord, kept)), key)
        self.assertEqual(len(non_scheme - {0x3A}), 29)
        self.assertEqual(set(leaks_["path@11"]["plain"]), set(map(ord, "\t\n\x0b\x0c\r ")))
        self.assertEqual([leaks_["token@%d" % p]["plain"] for p in (3, 6, 7, 10, 13)], [[0x20]] * 5)


def corpus(count=40000):
    """The span test's strings: scheme characters, `:`, `/`, `@`, spaces,
    controls, STAND_INs, look-alikes, astral characters and composite tokens,
    by a fixed generator, so both runs read the same strings. The review of
    cbd6679 added the astral characters, two odd characters side by side (the
    caps), an empty-run mark before a delimiter and a mark inside a password."""
    alpha = list("ahHt1.+-:/@ ?#&=;,)'\"[]_qz") + [chr(c) for c in (
        0x09, 0x0A, 0x01, 0x7F, 0x85, 0x9B, 0xA0, 0x200B, 0x34F, 0x338, 0xFEFF, 0x2028, 0x3000, 0xE9, 0x65E5,
        0xFF1A, 0xFE55, 0x2215, 0xFF0F, 0x2044, 0x3164, 0xFFFD, 0x1F600, 0xE0001, 0x10FFFF)]
    composites = ["http://", "http:" + chr(0x200B) + "//", "http" + chr(0xFF1A) + "//", "http:" + chr(0x2215) * 2,
                  "a:b@", "1://", ":" + chr(1) + "//", "qqqqqq:zzzzzz@cdn.test/x", "http" + chr(0x2215) + "://",
                  chr(0x4E2D) * 2, "x" + chr(0x200B) + chr(0x2215) * 2 + "\t", chr(0xE9) + "//",
                  ":" + chr(0xE9) + "/" + chr(0xE9) + "/"]
    out = []
    for i in range(count):
        x, text = i + 1, []
        while len(text) < 4 + i % 60:
            x = (x * 1103515245 + 12345) & 0x7FFFFFFF
            text.append(composites[(x >> 8) % len(composites)] if x % 7 == 0 else alpha[(x >> 4) % len(alpha)])
        out.append("".join(text))
    return out


def utf16(text):
    """Each code point index of `text` as a UTF-16 index, and the end."""
    out = [0]
    for ch in text:
        out.append(out[-1] + (2 if ord(ch) > 0xFFFF else 1))
    return out


def helper_spans(text):
    """The helper's URLs (scheme start, mark start, mark end, run end) and
    credential spans (start, end, token end), in UTF-16 indices."""
    reading = helper.UrlReading(text, 0, None, True)
    held = helper.credential_spans(text, reading)
    at = utf16(text)
    return [[[at[x] for x in url] for url in reading.urls], [[at[x] for x in span] for span in held]]


def rule_spans(text):
    at = utf16(text)
    return [[[at[x] for x in url] for url in rule.urls(text)], [[at[x] for x in span] for span in rule.credentials(text)]]


MODEL_SPANS = """
const M = require("./Model.mjs")
const texts = JSON.parse(require("fs").readFileSync(0, "utf8"))
process.stdout.write(JSON.stringify(texts.map(function (s) {
  const urls = M.urlList(s)
  return [urls.map(function (u) { return [u.start, u.markStart, u.markEnd, u.runEnd] }),
          M.credentialSpans(s, urls).map(function (h) { return [h.start, h.end, h.tokenEnd] })]
})))
"""

MODEL_SINKS = """
const M = require("./Model.mjs")
const texts = JSON.parse(require("fs").readFileSync(0, "utf8"))
process.stdout.write(JSON.stringify(texts.map(function (s) {
  const a = M.notifyArgv("streamFailed", { name: s, reason: s })
  return [M.sinkText(s), a[a.length - 1]]
})))
"""


def node(script, texts):
    done = subprocess.run(["node", "-e", script], input=json.dumps(texts), capture_output=True, text=True, cwd=ROOT,
                          timeout=600)
    if done.returncode != 0:
        raise AssertionError(done.stderr[-800:])
    return json.loads(done.stdout)


class SpanTest(unittest.TestCase):
    def test_both_mirrors_read_the_same_urls_and_credentials(self):
        """Over 40,000 generated strings, astral characters among them: the
        helper's reading (next_url through UrlReading) and the model's
        (Model.urlList) find the same URLs at the same places, and the helper's
        credential_spans and Model.credentialSpans withhold the same spans,
        compared in UTF-16 indices; and tests/url_reading_rule.py, which keeps
        no dead bound and takes no shortcut, reads the same, so neither changes
        an answer."""
        texts = corpus()
        model = node(MODEL_SPANS, texts)
        differ = [ascii(t) for t, m in zip(texts, model) if helper_spans(t) != m]
        self.assertEqual((len(model), differ[:4]), (40000, []))
        rule_differ = [ascii(t) for t in texts[:20000] if rule_spans(t) != helper_spans(t)]
        self.assertEqual(rule_differ[:4], [])
        # Not vacuous: the corpus reaches marks a look-alike or a STAND_IN
        # makes, credentials, and astral characters inside both.
        found = [helper_spans(t) for t in texts[:4000]]
        self.assertGreater(sum(len(f[0]) for f in found), 1000)
        self.assertGreater(sum(len(f[1]) for f in found), 500)
        self.assertGreater(sum(1 for t in texts if any(ord(c) > 0xFFFF for c in t)), 10000)

    def test_the_printable_ascii_path_is_the_general_one(self):
        """next_url answers printable ASCII by str.find over `://` and a
        walk back over its colons; the general path, asked of the same text,
        gives the same URLs."""
        alpha = list("ahHt1.+-:/@ ?#&=;,)'\"[]_qz") + ["http://", "a:b@", "1://", ":://", "::", "x:/", "//"]
        checked = 0
        for i in range(20000):
            x, text = i + 7, []
            while len(text) < 3 + i % 40:
                x = (x * 1103515245 + 12345) & 0x7FFFFFFF
                text.append(alpha[(x >> 4) % len(alpha)])
            text = "".join(text)
            self.assertTrue(text.isascii() and text.isprintable())
            walks = []
            for plain in (True, False):
                urls, low = [], 0
                while True:
                    url = helper.next_url(text, low, low, plain)
                    if url is None:
                        break
                    urls.append(url)
                    low = url[3]
                walks.append(urls)
            self.assertEqual(walks[0], walks[1], ascii(text))
            checked += len(walks[0])
        self.assertGreater(checked, 5000)


class CapsTest(unittest.TestCase):
    """The review of cbd6679 (its changes-too-much findings 1 and 2): with no
    limit on the mark's reading, a space-less Chinese, Japanese, Korean or
    Cyrillic line with one ASCII word before a slash-separated list printed
    only its last item, and a description holding a time and, later, a
    handle or an address was withheld whole. Each stretch the reading crosses
    holds one WIDE code point now, and a credential's `:` and `@` at most one
    counted one between them. Red on cbd6679: every hand-written line below
    changed there."""

    LINES = [
        chr(0x4E2D) + "CCTV5" + "".join(map(chr, (0x8F6C, 0x64AD, 0xFF0C))) + "2024" + chr(0x5E74) + chr(0xFF1A)
        + chr(0x6E38) + chr(0x6CF3) + "/" + chr(0x8DF3) + chr(0x6C34) + "/" + chr(0x4E52) + chr(0x4E53),
        "MV" + chr(0x7CBE) + chr(0x9009) + chr(0xFF1A) + chr(0x5468) + chr(0x6770) + "/" + chr(0x6797) + chr(0x4FCA)
        + "/" + chr(0x9093) + chr(0x7D2B) + " " + chr(0x91D1),
        "NHK" + chr(0x30B9) + chr(0x30DA) + chr(0x3002) + chr(0x51FA) + chr(0xFF1A) + chr(0x5C71) + chr(0x7530)
        + chr(0xFF0F) + chr(0x9234) + chr(0x6728) + chr(0xFF0F) + chr(0x4F50) + chr(0x85E4),
        "tvN" + chr(0xB4DC) + chr(0xB77C) + "/" + chr(0xC608) + chr(0xB2A5) + "/HD",
        "RU:" + chr(0x041A) + chr(0x0438) + "/" + chr(0x0424) + chr(0x0438) + "/" + chr(0x0421) + chr(0x0435),
        chr(0x6BCF) + chr(0x665A) + "19:30" + chr(0x64AD) + chr(0x51FA) + chr(0xFF0C) + chr(0x6295) + chr(0x7A3F)
        + "cctv@cctv.test",
        chr(0x653E) + chr(0x9001) + " 21:00" + chr(0x3000) + chr(0x516C) + chr(0x5F0F) + chr(0x3000) + "@nhk_pr",
        "NHK" + chr(0x7DCF) + chr(0x5408) + "//BS",
    ]

    def test_cjk_and_cyrillic_lines_keep_their_text_in_both_mirrors(self):
        model = node(MODEL_SINKS, self.LINES)
        got = [(ascii(t), helper.redact_urls(t), helper.player_title_text(t), fold_redact(t), m[0])
               for t, m in zip(self.LINES, model)]
        # The fold is the plain fold here: a line holding no URL and no
        # credential has its whitespace runs folded to a space, U+3000 among
        # them.
        self.assertEqual(got, [(ascii(t), t, t, re.sub(r"[\s\x00-\x1f\x7f]+", " ", t), t) for t in self.LINES])

    def test_one_odd_code_point_a_stretch_still_marks_a_url_and_two_do_not(self):
        cred = "qqqqqq:zzzzzz@cdn.test/x"
        path = "cdn.test/live/qqqqqq/zzzzzz/1.ts"
        z, e = chr(0x200B), chr(0xE9)
        cases = [
            # P: one odd code point beside the colon, on either side, or one in each stretch.
            ("http" + z + ":" + z + "//" + path, "http://cdn.test"),
            ("http" + e + e + "://" + path, "http" + e + e + "://" + path),
            ("http" + z + chr(1) + z + "://" + path, "http" + z + chr(1) + z + "://" + path),
            # Between the slashes.
            ("http:/" + e + "/" + path, "http://cdn.test"),
            ("http:/" + e + e + "/" + path, "http:/" + e + e + "/" + path),
            ("http:/" + e + chr(1) + chr(0x85) + "/" + path, "http://cdn.test"),
            # A crossed run.
            ("http" + e + "1://" + path, "cdn.test"),
            ("http" + e + e + "1://" + path, "http" + e + e + "1://" + path),
            # An astral character is one code point to both mirrors.
            ("http" + chr(0x1F600) + "://" + path, "http://cdn.test"),
            ("http" + chr(0x1F600) * 2 + "://" + path, "http" + chr(0x1F600) * 2 + "://" + path),
            # A userinfo behind a mark too wide is a credential token.
            ("http" + e + e + "://" + cred, "http" + e + e + HOST_WITHHELD),
        ]
        self.assertEqual([(ascii(t), helper.redact_urls(t)) for t, _ in cases], [(ascii(t), w) for t, w in cases])
        model = node(MODEL_SINKS, [t for t, _ in cases])
        leaks_ = [(ascii(t), helper.redact_urls(t) != w, leaks(m[0]) != leaks(w)) for (t, w), m in zip(cases, model)]
        self.assertEqual([x for x in leaks_ if x[1] or x[2]], [])


HOST_WITHHELD = helper.HOST_WITHHELD


class TokenSweepTest(unittest.TestCase):
    """The review of cbd6679 (its still-shows findings 1 and 2): `X//` with X
    any code point, inserted at every position of a scheme-less credential,
    started a URL inside it, so the token arm, which read only the text
    between URLs, saw the username with no `@`, and every sink of both
    mirrors printed it (63,300 of 63,484 code points at each password
    position); the helper also printed a username as the scheme. With the
    credential read across URLs and the scheme printed from a list, the only
    leak left is U+0020 inside the credential (`qqqqqq:z //zz@...`): a space
    ends a token as it ends a URL's run, the accepted residual. Also the
    `:` X `/` X `/` and X `:/` X `/` forms. node runs every BMP code unit;
    here every 31st BMP code point and all of ASCII, the slash look-alikes and
    the reader's spaces."""

    TOKEN = "qqqqqq:zzzzzz@cdn.test/live/1.ts"
    FORMS = {"X//": lambda c: c + "//", ":X/X/": lambda c: ":" + c + "/" + c + "/",
             "X:/X/": lambda c: c + ":/" + c + "/"}

    def test_no_insertion_but_a_space_inside_the_credential_leaks(self):
        codes = sorted({c for c in range(0x10000) if not 0xD800 <= c <= 0xDFFF and chr(c) not in "qzQZ"
                        and (c < 0x80 or c % 31 == 0)} | set(map(ord, helper.SLASH_ALIKE_CHARS))
                       | set(map(ord, helper.URL_SPACE_CHARS)))
        got = {}
        for name, form in self.FORMS.items():
            for pos in range(len(self.TOKEN) + 1):
                for c in codes:
                    text = "News " + self.TOKEN[:pos] + form(chr(c)) + self.TOKEN[pos:] + " HD"
                    for sink, f in (("redact_urls", helper.redact_urls), ("player_title_text", helper.player_title_text),
                                    ("fold", fold_redact)):
                        if leaks(f(text)):
                            got.setdefault((name, sink, c), []).append(pos)
        want = {(name, sink, 0x20): list(range(1, 14)) for name in self.FORMS
                for sink in ("redact_urls", "player_title_text", "fold")}
        self.assertEqual(got, want)


def credential_holds_a_delimited_run(text):
    """Whether the text holds the residual the multi-insert sweep pins by
    name: a URL inside a credential's span whose run a TAB, LF, VT, FF or CR
    ends, as tests/url_reading_rule.py reads them (an empty run, most often).
    The sinks that delete controls join that run to the password, so the URL
    takes the credential's `:`, and the username's text before the URL's
    scheme, or the URL's own run as a host, prints there while the plain
    sinks withhold the credential: the six delimiters inside a URL's run
    (R32a''', D-SINK-34), seen from the deleting side."""
    urls = rule.urls(text)
    for start, end, _ in rule.credentials(text, urls):
        for url in urls:
            if start <= url[0] < end and url[3] < len(text) and text[url[3]] in "\t\n\x0b\x0c\r":
                return True
    return False


MULTI_BASES = ["http://qqqqqq:zzzzzz@cdn.test/live/1.ts", "http://cdn.test/live/qqqqqq/zzzzzz/1.ts",
               "http://cdn.test/get.php?username=qqqqqq&password=zzzzzz", "qqqqqq:zzzzzz@cdn.test/live/1.ts"]
MULTI_PIECES = [chr(c) for c in (0x200B, 0x34F, 0x338, 0xA0, 0x3000, 0x2028, 1, 0x7F, 0x85, 9, 10, 13, 11, 12, 0xFFFD,
                                 0xFF1A, 0x1F600, 0xE0001, 0x9F, 0xA1, 0x2060, 0xFEFF, 0xFF20, 0x2215, 0xFF0F, 0x2044,
                                 0x1735)] + [
    ":", "/", "//", "://", "@", " ", "a", "1", "http", "a://", "1://", ":/", ".", ",", ")", "]", "[", "'", '"', "<",
    ">", "!", "?", ";", "=", "&", "#", "%", "x" + chr(0x200B) + chr(0x2215) * 2, chr(0x200B) + chr(0x2215) * 2 + "\t",
    "a:" + chr(0x2215) * 2 + "\t", "a" + chr(0x2215) + "://\t", chr(0xE9) + "//", ":" + chr(0xE9) + "/" + chr(0xE9) + "/"]


def multi_inputs(count, seed):
    """`count` strings: one to three pieces inserted into one of the four
    credentialed texts, wrapped `News ... HD`, by a seeded generator both
    suites share in spirit (the review of cbd6679's multi-insert fuzz)."""
    x = seed
    out = []
    for _ in range(count):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        text = MULTI_BASES[(x >> 8) % 4]
        for _ in range(1 + (x >> 4) % 3):
            x = (x * 1103515245 + 12345) & 0x7FFFFFFF
            at = (x >> 8) % (len(text) + 1)
            text = text[:at] + MULTI_PIECES[(x >> 3) % len(MULTI_PIECES)] + text[at:]
        out.append("News " + text + " HD")
    return out


class MultiInsertTest(unittest.TestCase):
    """The review of cbd6679 (its still-shows finding 3 and cost-parity
    finding 2): the invariants held on single insertions only. Two or three
    pieces -- marks, fillers, stand-ins, look-alikes, the six delimiters, `@`,
    `:` and astral characters -- in the four credentialed texts broke all
    three: the model printed what the helper withheld around an empty run,
    and the deleting sinks and fold-then-redact printed what the plain ones
    did not (1,133, 1,594 and 1,683 of 200,000 on cbd6679). Over 50,000 such
    strings: the helper's and the model's plain sinks leak at exactly the
    same inputs, the sinks that delete controls (player_title_text, the
    notification) only where the plain ones do but for the residual
    credential_holds_a_delimited_run names, and fold-then-redact only where
    the plain sinks do."""

    def test_the_invariants_hold_over_several_insertions(self):
        # The residual's own shapes, so its name is reached on every run.
        residual = ["News qqqqq%qa:" + chr(0x2215) * 2 + "\t:zzzzzz@cdn.test/live/1.ts HD",
                    "News qqq;qqqa" + chr(0x2215) + "://\t:z.zzzzz@cdn.test/live/1.ts HD",
                    "News qqqqq" + chr(0x1735) + "q" + chr(0x200b) + chr(0x2215) * 2 + "\t:zzzzzz@cdn.test/live/1.ts HD"]
        texts = multi_inputs(50000, 2026) + residual
        model = node(MODEL_SINKS, texts)
        bad = {}
        pinned = 0
        for text, (model_plain, model_body) in zip(texts, model):
            plain = leaks(helper.redact_urls(text))
            checks = {"helper plain != model plain": plain != leaks(model_plain),
                      "fold beyond plain": leaks(fold_redact(text)) and not plain}
            deleting = leaks(helper.player_title_text(text)) or leaks(model_body)
            if deleting and not plain:
                if credential_holds_a_delimited_run(text):
                    pinned += 1
                else:
                    checks["deleting beyond plain"] = True
            for name, failed in checks.items():
                if failed:
                    bad.setdefault(name, []).append(ascii(text))
        self.assertEqual({k: v[:3] for k, v in bad.items()}, {})
        # Not vacuous: the plain sinks leak on some (the stated residuals),
        # and the pinned residual is reached.
        self.assertGreater(sum(1 for t in texts if leaks(helper.redact_urls(t))), 1000)
        self.assertGreaterEqual(pinned, len(residual))


if __name__ == "__main__":
    unittest.main()
