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
"""
import json
import os
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
        self.assertGreaterEqual(len(vectors), 77)
        # Each half of the rule is there: broken marks that now redact,
        # tokens, the residuals and the accepted false positives.
        self.assertGreaterEqual(len([v for v in vectors if v["why"].startswith("D-SINK-95")]), 25)
        self.assertGreaterEqual(len([v for v in vectors if v["why"].startswith("D-SINK-96")]), 9)
        self.assertGreaterEqual(len([v for v in vectors if "residual" in v["why"]]), 8)
        self.assertGreaterEqual(len([v for v in vectors if v["why"].startswith("false positive")]), 10)
        self.assertEqual(FIXTURE["fuzz"]["totals"], {"plain": 567, "deleting": 442, "fold": 557})
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
    plain inputs; this tree, 567."""

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
    controls, STAND_INs, look-alikes and composite tokens, by a fixed
    generator, so both runs read the same 40,000 strings."""
    alpha = list("ahHt1.+-:/@ ?#&=;,)'\"[]_qz") + [chr(c) for c in (
        0x09, 0x0A, 0x01, 0x7F, 0x85, 0x9B, 0xA0, 0x200B, 0x34F, 0x338, 0xFEFF, 0x2028, 0x3000, 0xE9, 0x65E5,
        0xFF1A, 0xFE55, 0x2215, 0xFF0F, 0x2044, 0x3164, 0xFFFD)]
    composites = ["http://", "http:" + chr(0x200B) + "//", "http" + chr(0xFF1A) + "//", "http:" + chr(0x2215) * 2,
                  "a:b@", "1://", ":" + chr(1) + "//", "qqqqqq:zzzzzz@cdn.test/x", "http" + chr(0x2215) + "://"]
    out = []
    for i in range(count):
        x, text = i + 1, []
        while len(text) < 4 + i % 60:
            x = (x * 1103515245 + 12345) & 0x7FFFFFFF
            text.append(composites[(x >> 8) % len(composites)] if x % 7 == 0 else alpha[(x >> 4) % len(alpha)])
        out.append("".join(text))
    return out


def helper_spans(text):
    """The helper's reading in the model's terms (an empty run is a URL):
    every URL's (start, mark start, mark end, run end), and the token arm's
    output for each piece of free text between them."""
    urls, pieces, low = [], [], 0
    while True:
        url = helper.next_url(text, low, low, False)
        if url is None:
            break
        urls.append(list(url))
        pieces.append(helper.redact_tokens(text[low:url[0]]))
        low = url[3]
    pieces.append(helper.redact_tokens(text[low:]))
    return [urls, pieces]


MODEL_SPANS = """
const M = require("./Model.mjs")
const texts = JSON.parse(require("fs").readFileSync(0, "utf8"))
process.stdout.write(JSON.stringify(texts.map(function (s) {
  const urls = [], pieces = []
  let low = 0
  for (;;) {
    const u = M.urlAt(s, low)
    if (u === null) break
    urls.push([u.start, u.markStart, u.markEnd, u.runEnd])
    pieces.push(M.redactTokens(s.substring(low, u.start)))
    low = u.runEnd
  }
  pieces.push(M.redactTokens(s.substring(low)))
  return [urls, pieces]
})))
"""


class SpanTest(unittest.TestCase):
    def test_both_mirrors_read_the_same_urls_and_tokens(self):
        """Over 40,000 generated strings (BMP only, so a code point and a
        code unit index alike): the helper's next_url and the model's
        Model.urlAt find the same URLs at the same places, and the helper's
        redact_tokens and Model.redactTokens withhold the same tokens in the
        free text between them; and tests/url_reading_rule.py, which keeps no
        dead bound, reads the same URLs, so that bound changes no answer."""
        texts = corpus()
        done = subprocess.run(["node", "-e", MODEL_SPANS], input=json.dumps(texts), capture_output=True,
                              text=True, cwd=ROOT, timeout=600)
        self.assertEqual(done.returncode, 0, done.stderr[-800:])
        model = json.loads(done.stdout)
        differ = [ascii(t) for t, m in zip(texts, model) if helper_spans(t) != m]
        self.assertEqual((len(model), differ[:4]), (40000, []))
        rule_differ = [ascii(t) for t in texts if [list(u) for u in rule.urls(t)] != helper_spans(t)[0]]
        self.assertEqual(rule_differ[:4], [])
        # Not vacuous: the corpus reaches marks a look-alike or a STAND_IN
        # makes, and tokens.
        found = [helper_spans(t) for t in texts[:4000]]
        self.assertGreater(sum(len(f[0]) for f in found), 1000)
        self.assertGreater(sum(p.count(helper.HOST_WITHHELD) for f in found for p in f[1]), 500)

    def test_the_printable_ascii_path_is_the_general_one(self):
        """next_url answers printable ASCII by str.find over `://` and a
        walk back over its colons; the general path, asked of the same text,
        gives the same URLs, with a run needed and without."""
        alpha = list("ahHt1.+-:/@ ?#&=;,)'\"[]_qz") + ["http://", "a:b@", "1://", ":://", "::", "x:/", "//"]
        checked = 0
        for i in range(20000):
            x, text = i + 7, []
            while len(text) < 3 + i % 40:
                x = (x * 1103515245 + 12345) & 0x7FFFFFFF
                text.append(alpha[(x >> 4) % len(alpha)])
            text = "".join(text)
            self.assertTrue(text.isascii() and text.isprintable())
            for need_body in (False, True):
                walks = []
                for plain in (True, False):
                    urls, low = [], 0
                    while True:
                        url = helper.next_url(text, low, low, need_body, plain)
                        if url is None:
                            break
                        urls.append(url)
                        low = url[3]
                    walks.append(urls)
                self.assertEqual(walks[0], walks[1], (ascii(text), need_body))
                checked += len(walks[0])
        self.assertGreater(checked, 5000)


if __name__ == "__main__":
    unittest.main()
