"""D-SINK-100 and D-SINK-108 (2026-11-16, round 2 of the security review).

D-SINK-100. Two sources could READ alike: the shell reads a label through
Model.labelSinkText (D-SINK-98), and `http://qqqqqq:zzzzzz@cdn.test/a.m3u`
and a derived `cdn.test` both read `cdn.test`. validateLabel refused a typed
label that reads like another since D-SINK-98; uniqueLabel, the helper's
unique_label and check_custom_label compared raw labels, and both state
readers placed a derived label against the labels listed BEFORE it only.
Now both mirrors read a label the same way (label_sink_text, a port of
labelSinkText), a derived label avoids every label that reads alike, a
typed one that reads like another source's is refused by the helper too
(unless it is the record's own label left unchanged on an edit), and on
load a derived label avoids every typed label wherever it is listed.

D-SINK-108. The state verbs printed a label as typed, and the duplicate and
label-taken sentences quoted it through the URL redactor alone: they now
print and quote it as the Sources list reads it. state.json keeps it.

tests/fixtures/label-readings.json holds the model's answers; the node
suite checks the model against it and this suite the helper.
"""
import contextlib
import hashlib
import io
import itertools
import json
import os
import pathlib
import shutil
import signal
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper          # redirects HOME and $XDG_* first

helper = load_helper()

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "label-readings.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="ascii"))
CRED = "http://qqqqqq:zzzzzz@cdn.test/a.m3u"
SECRETS = ("qqqqqq", "zzzzzz")


def sweep_labels(sweep):
    pieces = sweep["pieces"]
    for k in range(1, sweep["maxPieces"] + 1):
        for combo in itertools.product(pieces, repeat=k):
            yield "".join(combo)


def sweep_digests(sweep, reading):
    labels = list(sweep_labels(sweep))
    size = sweep["chunkSize"]
    digests = []
    for c in range(sweep["chunks"]):
        part = [reading(label) for label in labels[c * size:(c + 1) * size]]
        digests.append(hashlib.sha256("\n".join(part).encode("utf-8")).hexdigest())
    return len(labels), digests


def run(*args):
    out, err = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = helper.main(list(args))
    finally:
        # `state init` arms SIGALRM for its own process (F-HARNESS-27).
        signal.alarm(0)
    lines = [line for line in out.getvalue().splitlines() if line.strip()]
    return code, out.getvalue(), json.loads(lines[-1]) if lines else None, err.getvalue()


class FixtureTest(unittest.TestCase):
    """The helper answers every case of the shared fixture as the model
    does."""

    def test_the_fixture_is_whole_and_ascii(self):
        self.assertTrue(all(b < 0x80 for b in FIXTURE_PATH.read_bytes()))
        self.assertGreaterEqual(len(FIXTURE["vectors"]), 200)
        self.assertEqual(len(FIXTURE["sweep"]["digests"]), FIXTURE["sweep"]["chunks"])
        self.assertTrue(any(v["reads"] != v["label"] for v in FIXTURE["vectors"]))

    def test_every_vector_reads_as_the_model_reads_it(self):
        got = [(v["label"], helper.label_sink_text(v["label"])) for v in FIXTURE["vectors"]]
        self.assertEqual([g for g, v in zip(got, FIXTURE["vectors"]) if g[1] != v["reads"]], [])

    def test_the_digest_sweep_reads_every_label_as_the_model_reads_it(self):
        count, digests = sweep_digests(FIXTURE["sweep"], helper.label_sink_text)
        self.assertEqual(count, FIXTURE["sweep"]["count"])
        differing = [c for c, (got, want) in enumerate(zip(digests, FIXTURE["sweep"]["digests"])) if got != want]
        self.assertEqual(differing, [])

    def test_a_derived_label_avoids_every_label_that_reads_alike(self):
        got = [helper.unique_label(c["label"], c["existing"]) for c in FIXTURE["unique"]]
        self.assertEqual(got, [c["expect"] for c in FIXTURE["unique"]])

    def test_a_typed_label_is_refused_as_the_model_refuses_it(self):
        got = []
        for c in FIXTURE["validate"]:
            others = [s["label"] for s in c["sources"] if s["key"] != c["self"]]
            stored = next((s["label"] for s in c["sources"] if c["self"] and s["key"] == c["self"]), None)
            try:
                helper.check_custom_label(c["label"], others, stored)
                got.append("ok")
            except helper.HelperError as error:
                got.append(error.code)
        self.assertEqual(got, [c["expect"] for c in FIXTURE["validate"]])

    def test_a_stored_list_loads_with_the_labels_the_model_gives_it(self):
        got = [[s["label"] for s in helper.normalize_state({"version": 2, "cacheLayout": 2, "sources": c["sources"]})["sources"]]
               for c in FIXTURE["states"]]
        self.assertEqual(got, [c["labels"] for c in FIXTURE["states"]])


class CliTest(unittest.TestCase):
    """The state verbs, in-process, over a scratch state folder. Nothing is
    fetched: `state source` validates and records."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="label-readings-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def state(self, *argv):
        return run("state", "--state-dir", self.dir, *argv)

    def stored(self):
        return json.loads(pathlib.Path(self.dir, "state.json").read_text(encoding="utf-8"))

    def test_a_derived_label_after_a_typed_one_that_reads_alike_is_numbered(self):
        code, out, reply, err = self.state("source", "add", "--url", "http://cdn.test/b.m3u", "--label", CRED)
        self.assertEqual(code, 0, err)
        code, out, reply, err = self.state("source", "add", "--url", "http://cdn.test/c.m3u")
        self.assertEqual(code, 0, err)
        self.assertEqual([s["label"] for s in self.stored()["sources"]], [CRED, "cdn.test 2"])

    def test_a_typed_label_that_reads_like_another_is_refused_and_quoted_as_it_reads(self):
        self.assertEqual(self.state("source", "add", "--url", "http://cdn.test/b.m3u", "--label", CRED)[0], 0)
        for label in ("http://u2:p2@cdn.test/c.m3u", "http%3A%2F%2Fu2%3Ap2%40cdn.test%2Fc.m3u", "cdn.test"):
            with self.subTest(label=label):
                code, out, reply, err = self.state("source", "add", "--url", "http://cdn.test/c.m3u", "--label", label)
                self.assertEqual((code, reply["error"]["code"]), (1, "label_taken"), err)
                self.assertEqual(reply["error"]["message"], "a source named 'cdn.test' already exists")
                for text in (out, err):
                    self.assertNotIn("u2", text)
                    self.assertNotIn("p2", text)
        self.assertEqual(len(self.stored()["sources"]), 1)

    def test_an_edit_that_keeps_its_label_is_not_refused(self):
        self.assertEqual(self.state("source", "add", "--url", "http://cdn.test/a.m3u", "--label", CRED)[0], 0)
        self.assertEqual(self.state("source", "add", "--url", "http://cdn.test/b.m3u", "--label", "x")[0], 0)
        keys = [s["key"] for s in self.stored()["sources"]]
        # Two records stored alike (a 0.19 helper compared raw labels).
        state = self.stored()
        state["sources"][1]["label"] = CRED.replace("a.m3u", "b.m3u")
        pathlib.Path(self.dir, "state.json").write_text(json.dumps(state), encoding="utf-8")
        code, out, reply, err = self.state("source", "update", keys[1], "--label", CRED.replace("a.m3u", "b.m3u"),
                                           "--epg-url", "http://cdn.test/g.xml")
        self.assertEqual(code, 0, err)
        code, out, reply, err = self.state("source", "update", keys[1], "--label", "http://u3:p3@cdn.test/d.m3u")
        self.assertEqual((code, reply["error"]["code"]), (1, "label_taken"), err)

    def test_every_state_verb_prints_a_label_as_the_sources_list_reads_it(self):
        code, out, reply, err = self.state("source", "add", "--url", "http://cdn.test/b.m3u", "--label", CRED)
        self.assertEqual(code, 0, err)
        self.assertEqual(reply["state"]["sources"][0]["label"], "cdn.test")
        for verb in (["show"], ["init"], ["source", "list"], ["favorite", "add", "t:news.us"]):
            with self.subTest(verb=verb):
                code, out, reply, err = self.state(*verb)
                self.assertEqual(code, 0, err)
                self.assertEqual([s["label"] for s in reply["state"]["sources"]], ["cdn.test"])
                for secret in SECRETS:
                    self.assertNotIn(secret, out)
        self.assertEqual(self.stored()["sources"][0]["label"], CRED)

    def test_the_duplicate_sentence_quotes_the_label_as_it_reads(self):
        label = "http%3A%2F%2Fqqqqqq%3Azzzzzz%40cdn.test%2Fa.m3u"
        self.assertEqual(self.state("source", "add", "--url", "http://cdn.test/b.m3u", "--label", label)[0], 0)
        code, out, reply, err = self.state("source", "add", "--url", "http://cdn.test/b.m3u")
        self.assertEqual((code, reply["error"]["code"]), (1, "duplicate"), err)
        self.assertEqual(reply["error"]["message"], "already in the source history as 'cdn.test'")
        self.assertIn("already in the source history as 'cdn.test'", err)
        for secret in SECRETS:
            self.assertNotIn(secret, out + err)
        keys = [s["key"] for s in self.stored()["sources"]]
        self.assertEqual(self.state("source", "add", "--url", "http://cdn.test/c.m3u", "--label", "y")[0], 0)
        other = [s["key"] for s in self.stored()["sources"] if s["key"] not in keys][0]
        code, out, reply, err = self.state("source", "update", other, "--url", "http://cdn.test/b.m3u")
        self.assertEqual((code, reply["error"]["message"]), (1, "already in the source history as 'cdn.test'"), err)


class CostTest(unittest.TestCase):
    """The reading's cost, measured and bounded (the numbers are in
    QA-RESULTS): normalize_state over 50 sources, every other one typed
    as a credential address, stays far inside a load's budget."""

    def test_fifty_sources_load_in_a_few_milliseconds(self):
        sources = []
        for n in range(50):
            url = "http://cdn%d.test/a.m3u" % n
            label = ("http://qqqqqq:zzzzzz@cdn%d.test/x.m3u" % n) if n % 2 else ""
            sources.append({"key": "%08x" % (0x1000 + n), "url": url, "epgUrl": "", "kind": "http", "label": label or "x",
                            "labelCustom": bool(label), "origin": "cli", "addedAt": n, "lastUsed": 0, "fetchedAt": 0,
                            "channelCount": 0, "groupCount": 0})
        raw = {"version": 2, "cacheLayout": 2, "sources": sources}
        best = min(self._time(lambda: helper.normalize_state(raw)) for _ in range(5))
        self.assertEqual(len(helper.normalize_state(raw)["sources"]), 50)
        self.assertLess(best, 0.25)

    @staticmethod
    def _time(fn):
        start = time.perf_counter()
        fn()
        return time.perf_counter() - start


if __name__ == "__main__":
    unittest.main()
