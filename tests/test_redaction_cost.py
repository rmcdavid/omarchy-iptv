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

So the first class of test here runs the OLD pattern as an oracle and asserts
the two agree character for character. A redactor that got fast by redacting
less would pass any budget, and "the output is unchanged" is the claim that
actually matters for rule 5. The oracle is a copy of the shipped pattern rather
than an import, because the helper must not carry a second redactor for a
test's benefit; a copy that drifts is caught the moment a vector disagrees.

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

# The pattern as it shipped, kept here and ONLY here.
_AS_SHIPPED = re.compile(r"\b([A-Za-z][A-Za-z0-9+.\-]*)://[^\s'\"<>]+")


def redact_urls_as_shipped(text):
    def replace(match):
        raw = match.group(0)
        trailing = ""
        while raw and raw[-1] in ".,;:!?)]":
            trailing = raw[-1] + trailing
            raw = raw[:-1]
        host = helper.url_host(raw)
        return "%s://%s%s" % (match.group(1).lower(), host or "[redacted]", trailing)

    return _AS_SHIPPED.sub(replace, "" if text is None else str(text))


# Reaches every branch of the scan: scheme characters, the authority
# delimiters, the `@` D-SINK-1 is about, the quote and angle brackets the tail
# class excludes, several kinds of whitespace, and non-ASCII (`\w` and `\s` are
# both Unicode-aware here, which is why the scan asks the engine rather than
# guessing).
ALPHABET = "ahHt p:/@?#.+-_019\t\n\xa0\u2028\ufeffx[]%&=,;'\"<>"


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
    # `_` is a word character and is not scheme-legal, so it kills the `\b`
    # for every position in the run behind it. The only place the scan has to
    # ask python what a word character is.
    "_aaa://h", "\xe9aaa://h", "0aaa://h",
    "http://u:p@h/x", "http://u:p@q@h/x", "aaahttp://h/x", "a://://b",
    "://://x", "HTTP://H.TEST/A", "ht+tp://h", "ht.tp://h", "1.2.3://h.test",
    "a.b-c+d://h.test/x", "http://h:8080/a?b#c", "http://@h/x", "http://h@/x",
    "http://a@b@c.test/x", "x http://a.test/1 y http://b.test/2 z",
    "a://b c://d", "file:///etc/x", "see http://h.test, then https://i.test.",
    "\xa0http://h.test\xa0y", "aaa://\u2028x", "no urls here", "http://",
    "http://?x",
    # The tail class excludes these three, so the URL stops at them.
    "'http://h.test'", "<http://h.test>", "\"http://h.test\"",
    # A "://" the pattern cannot match followed by one it can: the scan has to
    # keep looking past the first, and stopping there leaves a live credential.
    "://x http://u:p@h.test/a", "1://x http://u:p@h.test/a",
    "://h http://a.test/b ://c https://u:p@d.test/e",
    # An `@` in the PATH is not userinfo: the authority ends at the first `/`,
    # so the host is `h.test` and not `b`.
    "http://h.test/a@b/c", "http://u:p@h.test/a@b/c", "http://h.test?a@b",
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
            self.assertEqual(out, redact_urls_as_shipped(vector["text"]), vector["why"])
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
                      if helper.redact_urls(text) != redact_urls_as_shipped(text)]
        self.assertEqual([repr(t) for t in mismatches[:4]], [])

    def test_none_and_non_strings_are_unchanged_too(self):
        for value in (None, 42, True, 1.5, [], {}):
            self.assertEqual(helper.redact_urls(value),
                             redact_urls_as_shipped(value), repr(value))


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
