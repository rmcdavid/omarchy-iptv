"""D-EPG-14 (2026-10-29): a playlist tvg-id carrying a control character
is written ENCODED into epg-window.txt and epg-now.json, and a window an
earlier helper wrote with one raw no longer breaks the recompute.

json_string skipped the encoder for an id with no quote and no backslash.
The guide's own ids are folded of control characters at the parse, but with
a playlist loaded the window is keyed by the playlist's tvg-ids, which
make_channel only strips, so a TAB, a CR or any other C0 control inside one
was written raw: a TAB moved the window line's first-TAB split and the fetch
ended in `internal`; any of them made epg-now.json invalid JSON and blanked
the guide of every channel of the source while `epg` answered ok:true.

The ids are tests/fixtures/epg-id-controls.json, which tests/Model.test.js
runs through the same verbs and then through Model.parseEpgNowStore (rule:
a rule implemented in both languages gets one shared fixture). Every check
here runs the SHIPPING verbs over files on disk and reads what they wrote.
"""
import contextlib
import io
import json
import os
import pathlib
import tempfile
import time
import unittest

from helper_loader import load_helper

helper = load_helper()
FIXTURE = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "epg-id-controls.json")
                     .read_text(encoding="ascii"))
IDS = [(row["case"], row["tvgId"]) for row in FIXTURE["ids"]]
NOW = FIXTURE["now"]


def run(*args):
    """The helper in-process -> (exit code, last JSON line, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(args))
    text = out.getvalue().strip()
    return code, (json.loads(text.splitlines()[-1]) if text else None), err.getvalue()


def stamp(sec):
    return time.strftime("%Y%m%d%H%M%S", time.gmtime(sec)) + " +0000"


def write_sources(directory):
    """The fixture's playlist and guide, as tests/Model.test.js writes them:
    channel i is `Fixture channel <case>` with the raw tvg-id, and guide
    channel g<i> declares the same name, so the NAME strategy matches it and
    the window is keyed by the playlist's id."""
    playlist = ["#EXTM3U"]
    guide = ['<?xml version="1.0" encoding="UTF-8"?>', "<tv>"]
    for i, (case, tvg) in enumerate(IDS):
        name = "Fixture channel %s" % case
        playlist += ['#EXTINF:-1 tvg-id="%s",%s' % (tvg, name), "http://127.0.0.1:9/%d.ts" % i]
        guide.append('<channel id="g%d"><display-name>%s</display-name></channel>' % (i, name))
    for i, (case, _) in enumerate(IDS):
        guide.append('<programme channel="g%d" start="%s" stop="%s"><title>Now %s</title></programme>'
                     % (i, stamp(FIXTURE["start"]), stamp(FIXTURE["stop"]), case))
        guide.append('<programme channel="g%d" start="%s" stop="%s"><title>Next %s</title></programme>'
                     % (i, stamp(FIXTURE["stop"]), stamp(FIXTURE["nextStop"]), case))
    guide.append("</tv>")
    m3u = os.path.join(directory, "playlist.m3u")
    xml = os.path.join(directory, "guide.xml")
    # newline="" keeps the CR inside its id: the playlist splits on LF only.
    with open(m3u, "w", encoding="utf-8", newline="") as handle:
        handle.write("\n".join(playlist) + "\n")
    with open(xml, "w", encoding="utf-8", newline="") as handle:
        handle.write("\n".join(guide) + "\n")
    return m3u, xml


def raw_controls(text):
    """The C0 controls in `text` other than the LF that ends a line."""
    return sorted({"%02x" % ord(ch) for ch in text if ord(ch) < 0x20 and ch != "\n"})


class FixtureIdsThroughTheVerbTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.cache = os.path.join(self.root, "cache")
        os.mkdir(self.cache, 0o700)
        self.m3u, self.xml = write_sources(self.root)
        code, _, stderr = run("playlist", "--url", self.m3u, "--cache-dir", self.cache)
        self.assertEqual(code, 0, stderr)

    def read_text(self, name):
        with open(os.path.join(self.cache, name), encoding="utf-8", newline="") as handle:
            return handle.read()

    def assert_now_file(self, label):
        text = self.read_text("epg-now.json")
        self.assertEqual(raw_controls(text), [], "%s: epg-now.json carries a raw control character" % label)
        channels = json.loads(text)["channels"]
        self.assertEqual(sorted(channels), sorted(tvg for _, tvg in IDS), label)
        for case, tvg in IDS:
            self.assertEqual(channels[tvg]["now"]["title"], "Now %s" % case, (label, case))
            self.assertEqual(channels[tvg]["next"]["title"], "Next %s" % case, (label, case))
        # R31b: one fragment a line, each line its own one-entry object.
        lines = text.split("\n")[1:-2]
        self.assertEqual(len(lines), len(IDS), label)
        for line in lines:
            self.assertEqual(len(json.loads("{" + line.rstrip(",") + "}")), 1, (label, line))

    def test_the_fetch_writes_every_id_encoded_and_the_file_parses(self):
        code, status, stderr = run("epg", "--url", self.xml, "--cache-dir", self.cache, "--now", str(NOW))
        self.assertEqual(code, 0, stderr)
        self.assertEqual((status["ok"], status["matched"], status["nowCount"]), (True, len(IDS), len(IDS)), status)
        self.assertNotIn("could not be read", " ".join(status["warnings"]))
        self.assert_now_file("fetch")
        window = self.read_text(helper.EPG_WINDOW_FILE)
        self.assertEqual(raw_controls(window.replace("\t", "")), [], "the window carries a raw control in an id")
        body = window.split("\n")[1:-1]
        self.assertEqual(len(body), len(IDS), "one window line a channel: no id split a line")
        self.assertEqual(sorted(json.loads(line.partition("\t")[0]) for line in body), sorted(tvg for _, tvg in IDS))

    def test_the_recompute_reads_the_window_back_and_writes_the_same(self):
        code, _, stderr = run("epg", "--url", self.xml, "--cache-dir", self.cache, "--now", str(NOW))
        self.assertEqual(code, 0, stderr)
        code, status, stderr = run("epg", "--now-only", "--cache-dir", self.cache, "--now", str(NOW + 60))
        self.assertEqual(code, 0, stderr)
        self.assertEqual((status["ok"], status["nowCount"]), (True, len(IDS)), status)
        self.assert_now_file("recompute")

    def test_json_string_is_the_encoder_for_every_fixture_id(self):
        for case, tvg in IDS:
            literal = helper.json_string(tvg)
            self.assertEqual(literal, json.dumps(tvg, ensure_ascii=False), case)
            self.assertEqual(json.loads(literal), tvg, case)
            self.assertEqual(raw_controls(literal), [], case)


class StaleWindowTest(unittest.TestCase):
    """A window an EARLIER helper wrote, with an id the old fast path left
    raw: the recompute skips that line, counts it, and writes a valid
    epg-now.json for the rest, never `internal`."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = tmp.name

    def write_window(self, lines):
        meta = {"version": 1, "fetchedAt": NOW, "sourceHost": "epg.example.test", "sourceKey": "x",
                "channelsMtime": None, "windowStart": NOW - 7200, "windowEnd": NOW + 43200,
                "restricted": True, "channelTotal": 3, "matched": 3, "epgChannels": 3,
                "programmeCount": 3, "warnings": []}
        helper.write_window_lines(os.path.join(self.cache, helper.EPG_WINDOW_FILE), meta, lines)

    def record(self, title):
        return helper.encode_record(FIXTURE["start"], FIXTURE["stop"], title)

    def old_line(self, tvg, title):
        """What 0.15.0's window_line wrote for an id with no quote and no
        backslash: the id between two quotes, raw."""
        return '"%s"\t%s' % (tvg, self.record(title))

    def recompute(self):
        return run("epg", "--now-only", "--cache-dir", self.cache, "--now", str(NOW))

    def test_each_raw_control_id_is_skipped_counted_and_the_rest_written(self):
        for case, tvg in IDS:
            if not raw_controls(tvg) or "\\" in tvg:
                continue          # the old writer encoded these already
            with self.subTest(case=case):
                self.write_window([helper.window_line("good.x", self.record("Good")), self.old_line(tvg, "Bad"),
                                   helper.window_line("after.x", self.record("After"))])
                code, status, stderr = self.recompute()
                self.assertEqual(code, 0, stderr)
                self.assertTrue(status["ok"], status)
                self.assertEqual(status["nowCount"], 2, status)
                self.assertIn("1 channel in the cached guide could not be read and was skipped", status["warnings"])
                self.assertIn("could not be read", stderr)
                with open(os.path.join(self.cache, "epg-now.json"), encoding="utf-8") as handle:
                    channels = json.load(handle)["channels"]
                self.assertEqual(sorted(channels), ["after.x", "good.x"])

    def test_a_record_without_its_fixed_width_head_is_skipped(self):
        bad_head = "x" + self.record("Shifted")[1:]
        self.write_window([helper.window_line("good.x", self.record("Good")),
                           '"shifted.x"\t' + bad_head, helper.window_line("wide.x", "\u0661" + self.record("Wide")[1:])])
        code, status, stderr = self.recompute()
        self.assertEqual(code, 0, stderr)
        self.assertEqual(status["nowCount"], 1, status)
        self.assertIn("2 channels in the cached guide could not be read and were skipped", status["warnings"])
        with open(os.path.join(self.cache, "epg-now.json"), encoding="utf-8") as handle:
            self.assertEqual(sorted(json.load(handle)["channels"]), ["good.x"])

    def test_a_window_that_is_not_utf8_is_no_cache_not_internal(self):
        with open(os.path.join(self.cache, helper.EPG_WINDOW_FILE), "wb") as handle:
            handle.write(b'{"version":1,"fetchedAt":%d}\n"a\xff"\t' % NOW + self.record("T").encode("ascii") + b"\n")
        code, status, _ = self.recompute()
        self.assertEqual(code, 1)
        self.assertEqual(status["error"]["code"], "no_cache", status)


if __name__ == "__main__":
    unittest.main()
