"""D-EPG-7: what parse_xmltv keeps of a programme until the parse ends.

The row: every in-window programme of every matched channel was held in
`pending` as a 4-tuple (start, stop, title, detail dict) until the parse
ended, about 1 KiB a programme at process level, so a guide at the 64 MiB
input cap made of very small programmes was reasoned to approach the 512 MiB
parse limit. It stays UNVERIFIED at size on purpose: nothing here is large.

What changed, and what this module holds it to:

* A programme is retained as ONE bytes object (retain_programme) and encoded
  by encode_retained. The decisions are unchanged, so the output must be
  IDENTICAL to f55a32f's -- not "equivalent": the same window file and the
  same epg-now.json, byte for byte. `RetentionDifferentialTest` runs the
  f55a32f helper (taken from git, never a copy kept in this tree, which would
  be a mirror -- rule 12) and this tree's on the same small ordinary inputs:
  shuffled document order, programmes listed twice, missing stops, stops that
  are not after their start, twelve-digit stops, shared start times, quotes,
  backslashes, astral characters, descriptions on some programmes and not
  others, and the per-channel cap lowered so the cap meets the duplicate
  check. In process for parse_xmltv's whole result; as subprocesses for the
  files `epg` writes.
* What one retained programme COSTS is pinned by measurement on an ordinary
  small guide (tracemalloc over parse_xmltv, 2,000 vs 4,000 programmes):
  f55a32f measured 724 bytes a programme on a guide with descriptions and
  144 on a title-only one; this tree 213 and 58. The ceilings below sit
  between the two, so the pin is red on f55a32f and green here, and it reads
  a measurement rather than the code (rule 14).
* The time memo is bounded (EPG_TIME_CACHE_MAX, lowered to 3 here): a memo
  changes no answer, and the test asserts both halves.
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import pathlib
import random
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tracemalloc
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper

helper = load_helper()

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = "f55a32f"
NOW = 1792000000


def load_baseline(case):
    """The f55a32f helper, extracted from git into a temp directory and loaded
    with bytecode writing off. -> (module, path to its stub)."""
    if shutil.which("git") is None:
        case.skipTest("git is needed to read the baseline helper")
    probe = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", BASELINE + "^{commit}"],
                           capture_output=True, timeout=30)
    if probe.returncode != 0:
        case.skipTest("the baseline commit %s is not in this checkout" % BASELINE)
    work = tempfile.mkdtemp()
    case.addCleanup(shutil.rmtree, work, True)
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", BASELINE, "bin"],
                             capture_output=True, timeout=60)
    case.assertEqual(archive.returncode, 0, archive.stderr)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(work, filter="data")
    stub = os.path.join(work, "bin", "omarchy-iptv")
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        loader = importlib.machinery.SourceFileLoader("omarchy_iptv_baseline", stub)
        spec = importlib.util.spec_from_loader("omarchy_iptv_baseline", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module, stub


def xmltv_time(epoch):
    return time.strftime("%Y%m%d%H%M%S +0000", time.gmtime(epoch))


TITLES = ["News", "News", "Film: \"Quoted\"", "Back\\slash", "Caf\u00e9", "Rocket \U0001F680 Hour",
          "Late Show", "  spaced   out  ", ""]
DESCS = ["", "", "A short synopsis.", "Says \"hi\" \\ bye", "Stars \u2605 and \U0001F31F", "See https://x.test/p?q=1"]


def random_guide(seed, channels=5):
    """A small ordinary guide built from a seed: a few channels, some dozen
    programmes each over a two-day spread around NOW, shuffled."""
    rng = random.Random(seed)
    ids = ["ch%d.tv" % i for i in range(channels)]
    starts = [NOW + offset for offset in range(-4 * 3600, 14 * 3600, 900)]
    programmes = []
    for cid in ids + ["stray.tv"]:
        for _ in range(rng.randint(0, 14)):
            start = rng.choice(starts)
            roll = rng.random()
            if roll < 0.35:
                stop = None
            elif roll < 0.45:
                stop = start - rng.choice((0, 600))          # not after its start
            elif roll < 0.5:
                stop = 253402300799                          # 9999-12-31, twelve digits
            else:
                stop = start + rng.choice((900, 1800, 3600))
            title = rng.choice(TITLES)
            desc = rng.choice(DESCS)
            category = rng.choice(["", "News", "Drama"])
            episode = rng.choice(["", "2.14.", "S1 E2"])
            programmes.append((cid, start, stop, title, desc, category, episode))
    # Listed twice: an exact repeat, and the same programme without its detail.
    for item in list(programmes)[: rng.randint(0, 6)]:
        programmes.append(item)
    for item in list(programmes)[: rng.randint(0, 3)]:
        programmes.append(item[:4] + ("", "", ""))
    rng.shuffle(programmes)
    out = ['<?xml version="1.0" encoding="UTF-8"?>', "<tv>"]
    for i, cid in enumerate(ids):
        out.append('<channel id="%s"><display-name>Channel %d</display-name></channel>' % (cid, i))
    for cid, start, stop, title, desc, category, episode in programmes:
        attrs = 'start="%s" channel="%s"' % (xmltv_time(start), cid)
        if stop is not None:
            attrs += ' stop="%s"' % (xmltv_time(stop) if stop < 253402300799 else "99991231235959 +0000")
        body = "<title>%s</title>" % escape(title) if title or rng.random() < 0.5 else ""
        if desc:
            body += "<desc>%s</desc>" % escape(desc)
        if category:
            body += "<category>%s</category>" % category
        if episode:
            system = "xmltv_ns" if "." in episode else "onscreen"
            body += '<episode-num system="%s">%s</episode-num>' % (system, episode)
        out.append("<programme %s>%s</programme>" % (attrs, body))
    out.append("</tv>")
    return "\n".join(out).encode("utf-8"), ids


def escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def playlist_doc(ids):
    """Half the guide channels matched by id, the rest by name, one not at all."""
    rows = []
    for i, cid in enumerate(ids):
        if i == len(ids) - 1:
            continue
        tvg = cid if i % 2 == 0 else "Other%d.us" % i
        rows.append({"id": "p%d" % i, "tvgId": tvg, "name": "Channel %d" % i, "group": "G",
                     "url": "http://h.test/%d" % i})
    return {"version": 1, "count": len(rows), "channels": rows}


def baseline_wording(text):
    """This tree's counted sentences as f55a32f worded them, for a count of
    one (H4, the D-M3U-4 sibling: "1 programmes ..." became "1 programme
    ..."). The ONLY difference allowed between the two trees' output, and
    applied to this tree's side only; any other difference still fails."""
    for _, one, many in helper.epg_parse_warnings():
        text = text.replace(one % 1, many % 1)
    return text


def comparable(result, reword=False):
    out = dict(result)
    if reword:
        out["warnings"] = [baseline_wording(line) for line in result["warnings"]]
    out["channels"] = list(result["channels"].items())      # order matters: it is the file's order
    out["seenIds"] = sorted(result["seenIds"])
    return out


class RetentionDifferentialTest(unittest.TestCase):
    """This tree's retention against f55a32f's, same inputs, same answers."""

    SEEDS = range(60)

    def setUp(self):
        self.old, self.old_stub = load_baseline(self)

    def parse_both(self, data, index_doc, cap=None):
        results = []
        for module in (self.old, helper):
            saved = module.EPG_MAX_PER_CHANNEL
            if cap is not None:
                module.EPG_MAX_PER_CHANNEL = cap
            try:
                index = module.build_alias(json.loads(json.dumps(index_doc)))[0] if index_doc else None
                results.append(comparable(module.parse_xmltv(module.open_xml_stream(data), NOW, index),
                                          reword=module is helper))
            finally:
                module.EPG_MAX_PER_CHANNEL = saved
        return results

    def test_parse_results_are_identical_on_shuffled_guides_with_duplicates_and_missing_stops(self):
        checked = programmes = 0
        for seed in self.SEEDS:
            data, ids = random_guide(seed)
            for index_doc in (None, playlist_doc(ids)):
                for cap in (None, 3):
                    old, new = self.parse_both(data, index_doc, cap)
                    self.assertEqual(new, old, "seed %d, index %s, cap %s" % (seed, bool(index_doc), cap))
                    checked += 1
                    programmes += new["programmeCount"]
        # The inputs must actually exercise what they claim to: a run that
        # kept nothing would compare equal and prove nothing.
        self.assertEqual(checked, len(self.SEEDS) * 4)
        self.assertGreater(programmes, 1000)

    def test_one_channel_of_shared_starts_without_stops_is_identical(self):
        """The stop derivation's own shape: many programmes sharing a few
        starts, no stops, repeats in between -- what the forward pointer in
        encode_retained replaces a rescan for."""
        rows = []
        for i in range(60):
            start = NOW + (i % 4) * 600
            rows.append('<programme start="%s" channel="a.tv"><title>T%d</title></programme>'
                        % (xmltv_time(start), i % 7))
        data = ("<tv>%s</tv>" % "".join(rows)).encode()
        for cap in (None, 2, 5):
            old, new = self.parse_both(data, None, cap)
            self.assertEqual(new, old, cap)

    def test_the_files_epg_writes_are_byte_identical(self):
        """The whole verb, both helpers as subprocesses: epg-window.txt and
        epg-now.json byte for byte, and the status line but for its clock."""
        for seed in (1, 7, 23, 42):
            data, ids = random_guide(seed, channels=6)
            # One guide file for both, because the window records a key of
            # its URL; and one playlist mtime, because it records that too.
            shared = tempfile.mkdtemp()
            self.addCleanup(shutil.rmtree, shared, True)
            guide = os.path.join(shared, "guide.xml")
            with open(guide, "wb") as handle:
                handle.write(data)
            outputs = []
            for stub in (self.old_stub, str(ROOT / "bin" / "omarchy-iptv")):
                cache = tempfile.mkdtemp()
                self.addCleanup(shutil.rmtree, cache, True)
                playlist = os.path.join(cache, "channels.json")
                with open(playlist, "w", encoding="utf-8") as handle:
                    json.dump(playlist_doc(ids), handle)
                os.utime(playlist, ns=(1792000000 * 10**9, 1792000000 * 10**9))
                done = subprocess.run([sys.executable, stub, "epg", "--url", guide, "--cache-dir", cache,
                                       "--now", str(NOW), "--force"],
                                      capture_output=True, text=True, timeout=60,
                                      env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                mine = stub != self.old_stub
                status = json.loads(done.stdout.strip().splitlines()[-1])
                status.pop("durationMs")
                if mine:
                    status["warnings"] = [baseline_wording(line) for line in status["warnings"]]
                with open(os.path.join(cache, "epg-window.txt"), "rb") as handle:
                    window = handle.read()
                if mine:
                    window = baseline_wording(window.decode("utf-8")).encode("utf-8")
                with open(os.path.join(cache, "epg-now.json"), "rb") as handle:
                    now_doc = handle.read()
                outputs.append((window, now_doc, status))
            self.assertEqual(outputs[1][0], outputs[0][0], "epg-window.txt, seed %d" % seed)
            # epg-now.json is the same DOCUMENT, no longer the same bytes:
            # D-EPG-11 (R31b) writes one channel fragment per line so the
            # shell can index it without parsing it whole. The window file
            # above is still byte for byte; this one is compared as JSON,
            # which is the equality the ruling promises every other reader.
            self.assertEqual(json.loads(outputs[1][1]), json.loads(outputs[0][1]), "epg-now.json, seed %d" % seed)
            self.assertEqual(outputs[1][2], outputs[0][2], "status, seed %d" % seed)
            self.assertGreater(outputs[1][2]["programmeCount"], 0)


def ordinary_guide(count, rich):
    """`count` ordinary programmes over 50 channels, one a minute."""
    out = ['<?xml version="1.0" encoding="UTF-8"?>', "<tv>"]
    for c in range(50):
        out.append('<channel id="ch%d.tv"><display-name>Channel %d</display-name></channel>' % (c, c))
    for c in range(50):
        for p in range(count // 50):
            start = NOW - 7000 + p * 60
            if rich:
                out.append('<programme start="%s" stop="%s" channel="ch%d.tv"><title>Evening News %04d</title>'
                           '<desc>%s</desc><category>News</category>'
                           '<episode-num system="xmltv_ns">2.14.</episode-num></programme>'
                           % (xmltv_time(start), xmltv_time(start + 60), c, p,
                              ("A calm summary of the day's events, %d. " % p) * 3))
            else:
                out.append('<programme start="%s" channel="ch%d.tv"><title>t</title></programme>'
                           % (xmltv_time(start), c))
    out.append("</tv>")
    return "\n".join(out).encode()


def traced_peak(module, data):
    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        base = tracemalloc.get_traced_memory()[0]
        module.parse_xmltv(module.open_xml_stream(data), NOW, None)
        return tracemalloc.get_traced_memory()[1] - base
    finally:
        tracemalloc.stop()


class RetainedCostTest(unittest.TestCase):
    """One programme's cost, measured on ordinary small guides."""

    # Measured 2026-10-21 (bytes per programme, marginal traced peak):
    #                    f55a32f   this tree
    #   with detail         724        213
    #   title only          144         58
    CEILING = {True: 400, False: 100}

    def marginal(self, rich):
        helper.parse_xmltv(helper.open_xml_stream(ordinary_guide(100, rich)), NOW, None)   # warm
        small, large = ordinary_guide(2000, rich), ordinary_guide(4000, rich)
        return (traced_peak(helper, large) - traced_peak(helper, small)) / 2000.0

    def test_a_programme_with_detail_costs_under_the_ceiling(self):
        cost = self.marginal(True)
        self.assertLess(cost, self.CEILING[True], "%.0f bytes per retained programme" % cost)

    def test_a_title_only_programme_costs_under_the_ceiling(self):
        cost = self.marginal(False)
        self.assertLess(cost, self.CEILING[False], "%.0f bytes per retained programme" % cost)

    def test_one_retained_programme_is_one_bytes_object_and_round_trips(self):
        detail = {"desc": 'Says "hi" \\ \U0001F31F', "category": "News", "episode": "S3 E15"}
        item = helper.retain_programme(NOW, None, "Caf\u00e9 \"Live\"", detail)
        self.assertIsInstance(item, bytes)
        # 33 bytes of header and the payload, nothing else hanging off it.
        self.assertEqual(sys.getsizeof(item), 33 + len(item))
        blob, count = helper.encode_retained([item])
        self.assertEqual(count, 1)
        self.assertEqual(blob, helper.encode_record(NOW, NOW + helper.EPG_DEFAULT_DURATION,
                                                    "Caf\u00e9 \"Live\"", detail))

    def test_a_separator_in_a_text_cannot_move_a_field_boundary(self):
        """Every cleaner folds control characters, so this cannot arrive from
        a guide; the encoder folds it anyway rather than trust that."""
        item = helper.retain_programme(NOW, NOW + 60, "a\x1fb", {"desc": "c\x00d"})
        blob, _ = helper.encode_retained([item])
        self.assertEqual(helper.record_to_dict(blob)["title"], "a b")
        self.assertEqual(helper.record_to_dict(blob)["desc"], "c d")


class TimeMemoBoundTest(unittest.TestCase):
    """parse_xmltv_time's memo holds at most EPG_TIME_CACHE_MAX keys, none
    longer than EPG_TIME_CACHE_KEY_MAX, and answers exactly as without it."""

    def test_the_memo_never_outgrows_its_cap_and_changes_no_answer(self):
        raws = [xmltv_time(NOW + 60 * i) for i in range(12)] + ["junk", "20261021"] * 3
        saved = helper.EPG_TIME_CACHE_MAX
        helper.EPG_TIME_CACHE_MAX = 3
        try:
            memo = {}
            sizes, answers = [], []
            for raw in raws:
                answers.append(helper.parse_xmltv_time(raw, memo))
                sizes.append(len(memo))
        finally:
            helper.EPG_TIME_CACHE_MAX = saved
        self.assertLessEqual(max(sizes), 3, sizes)
        self.assertEqual(answers, [helper.parse_xmltv_time(raw, {}) for raw in raws])
        self.assertEqual(answers[0], NOW)

    def test_a_long_value_is_answered_and_not_kept(self):
        memo = {}
        raw = "20261021190000" + " " * 100 + "+0000"
        self.assertEqual(helper.parse_xmltv_time(raw, memo), helper.parse_xmltv_time(raw, {}))
        self.assertIsNotNone(helper.parse_xmltv_time(raw, memo))
        self.assertEqual(memo, {})
        helper.parse_xmltv_time("x" * 500, memo)
        self.assertEqual(memo, {})


if __name__ == "__main__":
    unittest.main()
