"""XMLTV / EPG tests for bin/omarchy-iptv. Fixtures only, never the network.

Run: python3 -m unittest discover -s tests
"""
import calendar
import contextlib
import gzip
import io
import json
import os
import pathlib
import tempfile
import time
import unittest

from helper_loader import load_helper

helper = load_helper()
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
XMLTV = str(FIXTURES / "epg-basic.xml")
PLAYLIST = str(FIXTURES / "epg-channels.m3u")
# 2026-09-12 21:00:00 UTC == 22:00 +0100 == 16:00 -0500 (see the fixture header).
NOW = calendar.timegm((2026, 9, 12, 21, 0, 0, 0, 0, 0))
H = 3600


def run(*args):
    """Run the helper in-process; -> (exit code, last JSON line, stderr)."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(args))
    text = out.getvalue().strip()
    payload = json.loads(text.splitlines()[-1]) if text else None
    return code, payload, err.getvalue()


def read(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


class TimeParsingTest(unittest.TestCase):
    def parse(self, raw):
        return helper.parse_xmltv_time(raw, {})

    def test_offsets_are_applied(self):
        self.assertEqual(self.parse("20260912220000 +0100"), NOW)
        self.assertEqual(self.parse("20260912160000 -0500"), NOW)
        self.assertEqual(self.parse("20260912210000 +0000"), NOW)
        self.assertEqual(self.parse("20260913023000 +0530"), NOW)
        self.assertEqual(self.parse("20260912213000 +0530"), NOW - 5 * H)

    def test_missing_offset_means_utc(self):
        self.assertEqual(self.parse("20260912210000"), NOW)
        self.assertEqual(self.parse("20260912210000Z"), NOW)

    def test_short_forms_are_padded(self):
        self.assertEqual(self.parse("20260912"), NOW - 21 * H)
        self.assertEqual(self.parse("2026091221"), NOW)
        self.assertEqual(self.parse("202609122100"), NOW)
        self.assertEqual(self.parse("202609122100 +0100"), NOW - H)

    def test_invalid_values_are_none(self):
        for raw in ("", None, "not-a-date", "2026-09-12T21:00:00Z", "20261312210000", "2026"):
            self.assertIsNone(self.parse(raw), raw)

    def test_cache_is_keyed_by_raw_string(self):
        cache = {}
        self.assertEqual(helper.parse_xmltv_time("20260912210000", cache), NOW)
        self.assertEqual(helper.parse_xmltv_time("junk", cache), None)
        self.assertEqual(cache, {"20260912210000": NOW, "junk": None})


class RecordEncodingTest(unittest.TestCase):
    def test_sorts_infers_stops_and_dedupes(self):
        blob, count = helper.encode_records([
            (NOW + 1800, None, "Last", {}),
            (NOW, None, "Second", {}),
            (NOW - 1800, NOW, "First", {}),
            (NOW - 1800, NOW, "First", {}),
            (NOW - 3600, NOW - 3600, "Zero length", {}),
        ])
        records = blob.split(helper.EPG_RECORD_SEP)
        self.assertEqual(count, 3)
        self.assertEqual([helper.record_to_dict(r) for r in records], [
            {"title": "First", "start": NOW - 1800, "stop": NOW},
            {"title": "Second", "start": NOW, "stop": NOW + 1800},
            {"title": "Last", "start": NOW + 1800, "stop": NOW + 1800 + helper.EPG_DEFAULT_DURATION},
        ])

    def test_per_channel_cap(self):
        items = [(NOW + i * 60, NOW + i * 60 + 60, "P%d" % i, {}) for i in range(helper.EPG_MAX_PER_CHANNEL + 50)]
        _, count = helper.encode_records(items)
        self.assertEqual(count, helper.EPG_MAX_PER_CHANNEL)


class EpgCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = self.tmp.name
        code, _, stderr = run("playlist", "--url", PLAYLIST, "--cache-dir", self.cache)
        self.assertEqual(code, 0, stderr)

    def epg(self, *extra, now=NOW, url=XMLTV, cache=None):
        return run("epg", "--url", url, "--cache-dir", cache or self.cache, "--now", str(now), *extra)

    def path(self, name):
        return os.path.join(self.cache, name)

    def test_plain_fixture_now_next(self):
        code, status, stderr = self.epg()
        self.assertEqual(code, 0, stderr)
        self.assertTrue(status["ok"])
        self.assertEqual(status["kind"], "epg")
        self.assertEqual(status["sourceHost"], "local file")
        self.assertEqual(status["fetchedAt"], NOW)
        self.assertEqual(status["generatedAt"], NOW)
        self.assertFalse(status["fromCache"])
        self.assertFalse(status["stale"])
        self.assertIsNone(status["error"])
        self.assertEqual(status["matched"], 8)
        self.assertEqual(status["channelTotal"], 11)
        self.assertEqual(status["epgChannels"], 7)
        self.assertEqual(status["programmeCount"], 14)
        self.assertEqual(status["nowCount"], 6)
        self.assertEqual(status["validUntil"], NOW + 300)
        self.assertEqual(sorted(status["warnings"]), sorted([
            "1 programme with an unreadable time skipped",
            "1 programme without a title skipped",
            "1 programme for a channel not in the playlist dropped",
        ]))
        self.assertEqual(read(self.path("epg-status.json")), status)

        doc = read(self.path("epg-now.json"))
        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["generatedAt"], NOW)
        self.assertEqual(doc["validUntil"], NOW + 300)
        self.assertEqual(doc["fetchedAt"], NOW)
        self.assertEqual(doc["sourceHost"], "local file")
        channels = doc["channels"]
        self.assertEqual(sorted(channels), ["baddate.tv", "bbc1.uk", "cnn.us", "dup.tv", "mixedcase.id", "nostop.tv", "overlap.tv"])
        # M4-02: this fixture has declared <desc> on this programme since
        # it was written (3c392a2, 2026-09-12) and the helper dropped it. It
        # is carried now, and every other row below shows the other half of
        # that rule -- a programme that declares nothing gains nothing.
        self.assertEqual(channels["bbc1.uk"], {
            "now": {"title": "News at Nine", "desc": "Headlines.", "start": NOW - 1800, "stop": NOW + 1800},
            "next": {"title": "Weather & Travel", "start": NOW + 1800, "stop": NOW + 3600},
        })
        # A programme ending exactly now is over; the gap leaves only `next`.
        self.assertEqual(channels["cnn.us"], {"next": {"title": "After The Gap", "start": NOW + 1800, "stop": NOW + 3600}})
        self.assertEqual(channels["overlap.tv"], {
            "now": {"title": "Overlapping Insert", "start": NOW - 900, "stop": NOW + 900},
            "next": {"title": "Later Show", "start": NOW + 1800, "stop": NOW + 5400},
        })
        self.assertEqual(channels["nostop.tv"], {
            "now": {"title": "No Stop Given", "start": NOW - 1800, "stop": NOW + 1800},
            "next": {"title": "Last Without Stop", "start": NOW + 1800, "stop": NOW + 5400},
        })
        self.assertEqual(channels["mixedcase.id"], {"now": {"title": "Case Folded", "start": NOW - H, "stop": NOW + H}})
        self.assertEqual(channels["baddate.tv"], {"now": {"title": "All Day (short form)", "start": NOW - 21 * H, "stop": NOW + 3 * H}})
        self.assertEqual(channels["dup.tv"], {"now": {"title": "Twice Listed", "start": NOW - 1800, "stop": NOW + 5400}})
        for name in ("epg-now.json", "epg-status.json", helper.EPG_WINDOW_FILE):
            self.assertEqual(pathlib.Path(self.path(name)).stat().st_mode & 0o777, 0o600, name)

    def test_window_keeps_only_the_window_and_unicode_titles(self):
        self.epg()
        window = helper.load_window(self.path(helper.EPG_WINDOW_FILE))
        self.assertEqual(window["windowStart"], NOW - 2 * H)
        self.assertEqual(window["windowEnd"], NOW + 12 * H)
        self.assertTrue(window["restricted"])
        channels = helper.window_channels(window)
        records = channels["bbc1.uk"].split(helper.EPG_RECORD_SEP)
        titles = [helper.record_to_dict(r)["title"] for r in records]
        self.assertEqual(titles, ["Earlier Show", "News at Nine", "Weather & Travel", "Late Film: Caf\u00e9 Society"])
        self.assertNotIn("unknown.tv", channels)
        self.assertNotIn("Empty.ch", channels)
        # Titles with JSON-significant characters still produce valid JSON.
        record = helper.encode_record(1, 2, 'He said "hi" \\ bye \u00e9')
        self.assertEqual(json.loads(helper.programme_json(record)), {"title": 'He said "hi" \\ bye \u00e9', "start": 1, "stop": 2})
        self.assertEqual(helper.record_to_dict(record), {"title": 'He said "hi" \\ bye \u00e9', "start": 1, "stop": 2})

    def test_valid_until_follows_the_earliest_boundary(self):
        code, status, _ = self.epg(now=NOW + 700)
        self.assertEqual(code, 0)
        # overlap.tv's insert ends at NOW+900, sooner than the 5-minute cap.
        self.assertEqual(status["validUntil"], NOW + 900)
        self.assertEqual(read(self.path("epg-now.json"))["validUntil"], NOW + 900)

    def test_overlap_falls_back_to_the_still_running_programme(self):
        self.epg(now=NOW + 1200)
        channels = read(self.path("epg-now.json"))["channels"]
        self.assertEqual(channels["overlap.tv"], {
            "now": {"title": "Long Show", "start": NOW - H, "stop": NOW + H},
            "next": {"title": "Later Show", "start": NOW + 1800, "stop": NOW + 5400},
        })

    def test_gzip_is_detected_by_magic_bytes_not_extension(self):
        raw = pathlib.Path(XMLTV).read_bytes()
        gz_named_xml = self.path("guide.xml")
        plain_named_gz = self.path("guide.xml.gz")
        pathlib.Path(gz_named_xml).write_bytes(gzip.compress(raw))
        pathlib.Path(plain_named_gz).write_bytes(raw)
        for source in (gz_named_xml, plain_named_gz):
            code, status, stderr = self.epg("--force", url=source)
            self.assertEqual(code, 0, stderr)
            self.assertEqual(status["matched"], 8, source)
            self.assertEqual(status["programmeCount"], 14, source)

    def test_unrestricted_without_channel_cache(self):
        with tempfile.TemporaryDirectory() as other:
            code, status, stderr = self.epg(cache=other)
            self.assertEqual(code, 0, stderr)
            self.assertIsNone(status["matched"])
            self.assertIsNone(status["channelTotal"])
            self.assertEqual(status["epgChannels"], 8)
            self.assertEqual(len(status["warnings"]), 2)
            channels = read(os.path.join(other, "epg-now.json"))["channels"]
            self.assertIn("MixedCase.ID", channels)
            self.assertIn("unknown.tv", channels)
            self.assertNotIn("mixedcase.id", channels)
            self.assertFalse(helper.load_window(os.path.join(other, helper.EPG_WINDOW_FILE))["restricted"])

    def test_ttl_reuses_the_cached_window(self):
        self.epg()
        first = pathlib.Path(self.path(helper.EPG_WINDOW_FILE)).stat().st_mtime_ns
        code, status, _ = self.epg(now=NOW + 60)
        self.assertEqual(code, 0)
        self.assertTrue(status["fromCache"])
        self.assertFalse(status["stale"])
        self.assertEqual(status["fetchedAt"], NOW)
        self.assertEqual(status["generatedAt"], NOW + 60)
        self.assertEqual(pathlib.Path(self.path(helper.EPG_WINDOW_FILE)).stat().st_mtime_ns, first)
        # --force always downloads.
        code, status, _ = self.epg("--force", now=NOW + 120)
        self.assertFalse(status["fromCache"])
        self.assertEqual(status["fetchedAt"], NOW + 120)

    def test_refetch_after_ttl_or_when_window_nearly_exhausted(self):
        self.epg()
        code, status, _ = self.epg(now=NOW + 7 * H)
        self.assertFalse(status["fromCache"], "6 h ttl expired")
        self.assertEqual(status["fetchedAt"], NOW + 7 * H)
        code, status, _ = self.epg("--ttl", "36000", now=NOW + 7 * H + 5 * H)
        self.assertTrue(status["fromCache"], "10 h ttl, 7 h left in the window")
        code, status, _ = self.epg("--ttl", "36000", now=NOW + 7 * H + 11 * H)
        self.assertFalse(status["fromCache"], "window ends within the 2 h margin")

    def test_playlist_change_triggers_refetch(self):
        self.epg()
        channels_path = self.path("channels.json")
        stamp = pathlib.Path(channels_path).stat().st_mtime_ns + 1_000_000_000
        os.utime(channels_path, ns=(stamp, stamp))
        code, status, _ = self.epg(now=NOW + 60)
        self.assertFalse(status["fromCache"])

    def test_source_change_triggers_refetch(self):
        self.epg()
        copy = self.path("other-guide.xml")
        pathlib.Path(copy).write_bytes(pathlib.Path(XMLTV).read_bytes())
        code, status, _ = self.epg(now=NOW + 60, url=copy)
        self.assertFalse(status["fromCache"])
        code, status, _ = self.epg(now=NOW + 120, url=copy)
        self.assertTrue(status["fromCache"])

    def test_now_only_recomputes_without_a_url(self):
        self.epg()
        code, status, stderr = run("epg", "--now-only", "--cache-dir", self.cache, "--now", str(NOW + 1200))
        self.assertEqual(code, 0, stderr)
        self.assertTrue(status["fromCache"])
        self.assertEqual(status["matched"], 8)
        doc = read(self.path("epg-now.json"))
        self.assertEqual(doc["generatedAt"], NOW + 1200)
        self.assertEqual(doc["channels"]["overlap.tv"]["now"]["title"], "Long Show")

    def test_now_only_without_cache_is_an_error(self):
        with tempfile.TemporaryDirectory() as empty:
            code, status, _ = run("epg", "--now-only", "--cache-dir", empty)
            self.assertEqual(code, 1)
            self.assertEqual(status["kind"], "epg")
            self.assertEqual(status["error"]["code"], "no_cache")
            self.assertFalse(status["stale"])

    def test_now_only_reports_stale_after_ttl(self):
        self.epg()
        code, status, _ = run("epg", "--now-only", "--cache-dir", self.cache, "--now", str(NOW + 7 * H))
        self.assertEqual(code, 0)
        self.assertTrue(status["stale"])

    def test_missing_url_is_no_source(self):
        code, status, _ = run("epg", "--cache-dir", self.cache)
        self.assertEqual(code, 1)
        self.assertEqual(status["error"]["code"], "no_source")

    def test_fetch_failure_keeps_stale_window_and_refreshes_now(self):
        self.epg()
        code, status, stderr = self.epg(now=NOW + 1200, url=self.path("missing.xml"))
        self.assertEqual(code, 1)
        self.assertFalse(status["ok"])
        self.assertEqual(status["error"]["code"], "not_found")
        self.assertTrue(status["stale"])
        self.assertEqual(status["fetchedAt"], NOW)
        self.assertEqual(status["matched"], 8)
        self.assertIn("not found", stderr)
        self.assertEqual(read(self.path("epg-status.json")), status)
        doc = read(self.path("epg-now.json"))
        self.assertEqual(doc["generatedAt"], NOW + 1200)
        self.assertEqual(doc["channels"]["overlap.tv"]["now"]["title"], "Long Show")

    def test_fetch_failure_without_window_is_not_stale(self):
        code, status, _ = self.epg(url="/nonexistent/guide.xml")
        self.assertEqual(code, 1)
        self.assertFalse(status["stale"])
        self.assertFalse(os.path.exists(self.path("epg-now.json")))

    def test_malformed_inputs(self):
        cases = {
            "bad_xml": b"<tv><programme start=\"20260912210000\" channel=\"x\"><title>Cut",
            "bad_gzip": b"\x1f\x8b\x08\x00garbage-not-a-gzip-stream",
            "empty_epg": b"<?xml version=\"1.0\"?><tv><channel id=\"x\"><display-name>X</display-name></channel></tv>",
        }
        for code_expected, payload in cases.items():
            source = self.path(code_expected + ".xml")
            pathlib.Path(source).write_bytes(payload)
            code, status, _ = self.epg(url=source)
            self.assertEqual(code, 1, code_expected)
            self.assertEqual(status["error"]["code"], code_expected)

    def test_unsupported_scheme_and_stderr_never_show_urls(self):
        code, status, stderr = self.epg(url="ftp://user:pw@h.test/guide.xml")
        self.assertEqual(code, 1)
        self.assertEqual(status["error"]["code"], "unsupported_scheme")
        self.assertNotIn("user:pw", stderr + json.dumps(status))


def generate_xmltv(path, channel_count, per_channel, first_start, detail=False):
    """A synthetic guide. `detail` fills <desc>, <category> and <episode-num>
    to exactly the caps the helper ships.

    The flag exists because the generator had no detail at all, so both
    budget tests ran only the path M4-02 widened -- a double more forgiving
    than any real detail-bearing guide, which is what CLAUDE.md rule 10
    forbids. Filled to the cap rather than to a realistic length on purpose:
    the budget is what the caps allow, and a guide that ships longer text
    reaches exactly this because clean_detail cuts it here."""
    fields = ""
    if detail:
        fields = ("<desc>%s</desc><category>%s</category>"
                  "<episode-num system=\"onscreen\">%s</episode-num>"
                  % ("d" * helper.EPG_MAX_DESC, "c" * helper.EPG_MAX_CATEGORY,
                     "e" * helper.EPG_MAX_EPISODE))
    with open(path, "w", encoding="ascii") as handle:
        handle.write("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<tv>\n")
        for c in range(channel_count):
            handle.write("<channel id=\"chan%d.tv\"><display-name>Channel %d</display-name></channel>\n" % (c, c))
        for c in range(channel_count):
            start = first_start
            for p in range(per_channel):
                stop = start + 1800
                handle.write("<programme start=\"%s +0000\" stop=\"%s +0000\" channel=\"chan%d.tv\"><title>Programme %d on channel %d</title>%s</programme>\n"
                             % (time.strftime("%Y%m%d%H%M%S", time.gmtime(start)), time.strftime("%Y%m%d%H%M%S", time.gmtime(stop)), c, p, c, fields))
                start = stop
        handle.write("</tv>\n")


class EntityDeclarationTest(unittest.TestCase):
    """D-EPG-6, the maintainer's ninth finding, on #11892 against 0.14.1: the
    parse expanded entities a feed declares for itself, and the byte cap
    bounds only the input. XMLTV never declares one, so a feed that does is
    refused before ElementTree sees a byte. Ordinary documents only: one
    small declaration, never referenced, is all the refusal needs."""

    BODY = ('<tv><channel id="a.tv"><display-name>A</display-name></channel>'
            '<programme start="20260912203000 +0000" stop="20260912213000 +0000" '
            'channel="a.tv"><title>News</title></programme></tv>')

    def parse(self, prolog):
        document = ('<?xml version="1.0" encoding="UTF-8"?>' + prolog + self.BODY).encode("ascii")
        return helper.parse_xmltv(helper.open_xml_stream(document), NOW, None)

    def test_a_feed_with_and_without_the_xmltv_doctype_parses_as_before(self):
        for prolog in ("", '<!DOCTYPE tv SYSTEM "xmltv.dtd">',
                       '<!DOCTYPE tv SYSTEM "xmltv.dtd">\n<!-- a comment -->\n'):
            parsed = self.parse(prolog)
            self.assertEqual(sorted(parsed["channels"]), ["a.tv"], prolog)
            self.assertEqual(parsed["warnings"], [], prolog)

    def test_one_small_entity_declaration_is_refused(self):
        for prolog in ('<!DOCTYPE tv [<!ENTITY x "y">]>',
                       '<!DOCTYPE tv SYSTEM "xmltv.dtd" [<!ENTITY x "y">]>',
                       '<!DOCTYPE tv [<!ENTITY % p "y">]>'):
            with self.assertRaises(helper.HelperError, msg=prolog) as caught:
                self.parse(prolog)
            self.assertEqual(caught.exception.code, "bad_xml", prolog)
            # D-EPG-15: refused at the DOCTYPE's start, for carrying an
            # internal subset at all, before the declaration inside it is
            # read; the entity refusal stays behind it as the second layer.
            self.assertIn("internal subset", caught.exception.message, prolog)

    def test_an_external_dtd_is_never_read(self):
        # What the guard rests on: a declaration can only reach ElementTree
        # through the prolog, because a DTD the DOCTYPE names is not loaded.
        with tempfile.TemporaryDirectory() as tmp:
            dtd = os.path.join(tmp, "ext.dtd")
            pathlib.Path(dtd).write_text('<!ENTITY x "y">\n', encoding="ascii")
            document = ('<!DOCTYPE tv SYSTEM "%s">' % dtd + self.BODY).replace("News", "&x;")
            with self.assertRaises(helper.HelperError) as caught:
                helper.parse_xmltv(helper.open_xml_stream(document.encode("ascii")), NOW, None)
            self.assertEqual(caught.exception.code, "bad_xml")
            self.assertIn("undefined entity", caught.exception.message)

    def test_a_declared_entity_is_refused_through_gzip_and_by_the_verb_without_a_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "guide.xml.gz")
            pathlib.Path(source).write_bytes(gzip.compress(
                ('<!DOCTYPE tv [<!ENTITY x "y">]>' + self.BODY).encode("ascii")))
            code, status, stderr = run("epg", "--url", source, "--cache-dir", tmp, "--now", str(NOW))
            self.assertEqual(code, 1)
            self.assertEqual(status["error"]["code"], "bad_xml")
            message = status["error"]["message"]
            self.assertIn("internal subset", message)   # D-EPG-15, as above
            self.assertNotIn(tmp, message + stderr)
            self.assertEqual(message.count(". "), 0, message)


T0 = 1789244100   # 2026-09-12T20:15:00Z, the reference instant of docs/QA.md TC-EPG-*
QA_XMLTV = str(FIXTURES / "qa-epg.xml")
QA_XMLTV_GZ = str(FIXTURES / "qa-nonascii" / "qa-epg.xml.gz")


def prog(title, start, stop):
    return {"title": title, "start": start, "stop": stop}


class QaEpgFixtureTest(unittest.TestCase):
    def epg(self, source, cache, *extra):
        return run("epg", "--url", source, "--cache-dir", cache, "--now", str(T0), *extra)

    def test_qa_epg_now_next_at_t0(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, status, stderr = self.epg(QA_XMLTV, tmp)
            self.assertEqual(code, 0, stderr)
            self.assertEqual(status["epgChannels"], 12)
            self.assertEqual(status["programmeCount"], 25)
            self.assertIsNone(status["matched"])
            self.assertEqual(status["validUntil"], T0 + 300)
            self.assertEqual(status["warnings"], [])
            channels = read(os.path.join(tmp, "epg-now.json"))["channels"]
            # M4-02 over the QA asset as committed: this programme has
            # carried <desc>, <category> and an xmltv_ns <episode-num> since
            # the fixture's first commit (c87354c, 2026-09-12), all three of
            # them dropped until now. "0.1.0/1" is season 0, episode 1,
            # counted from zero, so it reads S1 E2.
            self.assertEqual(channels["bbc1.uk"], {
                "now": dict(prog("Six O'Clock News", T0 - 4500, 1789245000),
                            desc="Now at T0.", category="News", episode="S1 E2"),
                "next": prog("Regional News", 1789245000, 1789248600)})
            self.assertEqual(channels["cnn.us"], {"now": prog("The Lead", T0 - 900, T0 + 2700), "next": prog("Situation Room", T0 + 2700, T0 + 6300)})
            self.assertEqual(channels["overlap.test"], {"now": prog("Overlap B", T0 - 900, T0 + 2700), "next": prog("After Overlap", T0 + 2700, T0 + 6300)})
            self.assertEqual(channels["gap.test"], {"next": prog("Starts Later", T0 + 2700, T0 + 6300)})
            self.assertEqual(channels["nostop.test"], {"now": prog("No Stop Attribute", T0 - 900, T0 + 2700), "next": prog("After No Stop", T0 + 2700, T0 + 6300)})
            self.assertEqual(channels["notz.test"], {"now": prog("No Offset Now", T0 - 900, T0 + 2700), "next": prog("No Offset Next", T0 + 2700, T0 + 6300)})
            self.assertEqual(channels["short.test"], {"now": prog("Short Format", T0 - 900, T0 + 1800), "next": prog("Short Format Next", T0 + 1800, T0 + 4500)})
            self.assertEqual(channels["unicode.test"]["now"]["title"], "T\u00e9l\u00e9journal \u2014 \u00c9dition sp\u00e9ciale")
            self.assertEqual(channels["unicode.test"]["next"]["title"], "\u0627\u0644\u062c\u0632\u064a\u0631\u0629")
            self.assertEqual(channels["00sReplay.us@SD"], {"now": prog("Replay Block 1", T0 - 2700, T0 + 900), "next": prog("Replay Block 2", T0 + 900, T0 + 4500)})
            self.assertEqual(channels["orphan.test"], {"now": prog("Orphan Programme", T0 - 900, T0 + 2700)})
            self.assertEqual(channels["halfhour.test"], {"now": prog("Half Hour Offset", T0 - 900, T0 + 2700), "next": prog("Half Hour Offset Next", T0 + 2700, T0 + 6300)})
            self.assertNotIn("far.test", channels)
            self.assertNotIn("nochannel.test", channels)
            self.assertEqual(len(channels), 11)

    def test_qa_gzip_twin_gives_identical_output(self):
        with tempfile.TemporaryDirectory() as plain, tempfile.TemporaryDirectory() as gz:
            code, _, stderr = self.epg(QA_XMLTV, plain)
            self.assertEqual(code, 0, stderr)
            code, status, stderr = self.epg(QA_XMLTV_GZ, gz)
            self.assertEqual(code, 0, stderr)
            self.assertEqual(status["programmeCount"], 25)
            self.assertEqual(pathlib.Path(plain, "epg-now.json").read_bytes(), pathlib.Path(gz, "epg-now.json").read_bytes())

    def test_qa_restricted_to_playlist_ids_with_at_sign_and_case_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            playlist = os.path.join(tmp, "list.m3u")
            pathlib.Path(playlist).write_text(
                "#EXTM3U\n"
                "#EXTINF:-1 tvg-id=\"00sReplay.us@SD\",00s Replay\nhttp://stream.example.test/replay.m3u8\n"
                "#EXTINF:-1 tvg-id=\"BBC1.UK\",BBC One (HD)\nhttp://stream.example.test/bbc1.m3u8\n"
                "#EXTINF:-1 tvg-id=\"nochannel.test\",Never Scheduled\nhttp://stream.example.test/never.m3u8\n"
                "#EXTINF:-1 tvg-id=\"missing.test\",Missing\nhttp://stream.example.test/missing.m3u8\n", encoding="utf-8")
            code, _, stderr = run("playlist", "--url", playlist, "--cache-dir", tmp)
            self.assertEqual(code, 0, stderr)
            code, status, stderr = self.epg(QA_XMLTV, tmp)
            self.assertEqual(code, 0, stderr)
            self.assertEqual(status["matched"], 2)
            self.assertEqual(status["channelTotal"], 4)
            self.assertEqual(status["epgChannels"], 2)
            channels = read(os.path.join(tmp, "epg-now.json"))["channels"]
            self.assertEqual(sorted(channels), ["00sReplay.us@SD", "BBC1.UK"])
            self.assertEqual(channels["BBC1.UK"]["now"]["title"], "Six O'Clock News")
            self.assertIn("dropped", " ".join(status["warnings"]))

    def test_inflated_gzip_bomb_is_too_large(self):
        with tempfile.TemporaryDirectory() as tmp:
            bomb = os.path.join(tmp, "bomb.xml.gz")
            pathlib.Path(bomb).write_bytes(gzip.compress(b"<tv><x>" + b"A" * (65 << 20) + b"</x></tv>", compresslevel=1))
            self.assertLess(os.path.getsize(bomb), 1 << 20)
            code, status, _ = self.epg(bomb, tmp)
            self.assertEqual(code, 1)
            self.assertEqual(status["error"]["code"], "too_large")

    def test_entity_expansion_bomb_is_refused_quickly(self):
        # SEC-19: bad_xml, and since D-EPG-6 at its first declaration, before anything expands.
        with tempfile.TemporaryDirectory() as tmp:
            entities = ["<!ENTITY a0 \"lol lol lol lol lol lol lol lol lol lol\">"]
            for level in range(1, 9):
                entities.append("<!ENTITY a%d \"%s\">" % (level, "&a%d;" % (level - 1) * 10))
            document = "<?xml version=\"1.0\"?><!DOCTYPE tv [%s]><tv><programme start=\"20260912200000\" channel=\"x\"><title>&a8;</title></programme></tv>" % "".join(entities)
            source = os.path.join(tmp, "bomb.xml")
            pathlib.Path(source).write_text(document, encoding="ascii")
            started = time.perf_counter()
            code, status, _ = self.epg(source, tmp)
            self.assertLess(time.perf_counter() - started, 5.0)
            self.assertEqual(code, 1)
            self.assertEqual(status["error"]["code"], "bad_xml")


class EpgPerformanceTest(unittest.TestCase):
    def test_now_only_10k_channels_is_fast(self):
        with tempfile.TemporaryDirectory() as tmp:
            sep = helper.EPG_RECORD_SEP
            channels = {}
            for c in range(10000):
                start = NOW - 2 * H
                records = []
                for p in range(28):
                    records.append(helper.encode_record(start, start + 1800, "Programme %d on channel %d" % (p, c)))
                    start += 1800
                channels["chan%d.tv" % c] = sep.join(records)
            meta = {
                "version": 1, "fetchedAt": NOW, "sourceHost": "epg.example.test", "sourceKey": "x",
                "channelsMtime": None, "windowStart": NOW - 2 * H, "windowEnd": NOW + 12 * H,
                "restricted": False, "channelTotal": None, "matched": None, "epgChannels": 10000,
                "programmeCount": 280000, "warnings": [],
            }
            helper.write_window(os.path.join(tmp, helper.EPG_WINDOW_FILE), meta, channels)
            elapsed = float("inf")
            for _ in range(3):
                started = time.perf_counter()
                code, status, stderr = run("epg", "--now-only", "--cache-dir", tmp, "--now", str(NOW + 1000))
                elapsed = min(elapsed, time.perf_counter() - started)
                self.assertEqual(code, 0, stderr)
            self.assertEqual(status["nowCount"], 10000)
            doc = read(os.path.join(tmp, "epg-now.json"))
            self.assertEqual(len(doc["channels"]), 10000)
            self.assertEqual(doc["channels"]["chan9999.tv"]["now"]["title"], "Programme 4 on channel 9999")
            self.assertEqual(doc["channels"]["chan9999.tv"]["next"]["start"], NOW + 1800)
            # Best of 3 against a generous ceiling. The budget this pins is
            # 100 ms, and the code lands near 35, but a wall-clock assertion
            # on a loaded machine measures the machine, not the code: this
            # read 112 ms once while other work ran, which is a false red.
            # The ceiling stays loose on purpose; a real regression here is a
            # multiple, not a few milliseconds.
            self.assertLess(elapsed, 0.5, "epg --now-only took %.0f ms (best of 3) for 10k channels" % (elapsed * 1000))

    def test_now_only_10k_detail_bearing_channels_is_fast(self):
        """The recompute budget against the biggest detail-bearing window a
        source can actually produce, which is NOT 10,000 x 28.

        MAX_SOURCE_BYTES is the bound that binds first, and it binds before
        EPG_MAX_DESC does. Measured with every field at its cap:
          10,000 x 28 -> 188.84 MiB of XML, REFUSED ("larger than 64 MB")
          10,000 x  9 ->  61.15 MiB of XML, accepted: 90,000 programmes,
                          epg-window.txt 48.96 MiB, epg-now.json 11.60 MiB
        so 9 per channel is the shape to pin, and the window built here is
        the same size as that fetch's. `epg --now-only` over it reads 176 ms
        best of 3 in-process against 84 ms for the same 10,000 channels
        detail-free -- OVER the 100 ms the case above names as its budget and
        under its 500 ms ceiling. That is the real cost of M4-02 on the
        recompute, it was never measured when the fields were added, and the
        number is recorded here rather than left to the reader of a comment.

        epg-now.json is bounded by CHANNELS, not programmes, so its 11.60 MiB
        is the ceiling at 10,000 channels whichever shape the guide takes.
        """
        with tempfile.TemporaryDirectory() as tmp:
            sep = helper.EPG_RECORD_SEP
            detail = {"desc": "d" * helper.EPG_MAX_DESC,
                      "category": "c" * helper.EPG_MAX_CATEGORY,
                      "episode": "e" * helper.EPG_MAX_EPISODE}
            channels = {}
            for c in range(10000):
                start = NOW - 2 * H
                records = []
                for p in range(9):
                    records.append(helper.encode_record(
                        start, start + 1800, "Programme %d on channel %d" % (p, c), detail))
                    start += 1800
                channels["chan%d.tv" % c] = sep.join(records)
            meta = {
                "version": 1, "fetchedAt": NOW, "sourceHost": "epg.example.test", "sourceKey": "x",
                "channelsMtime": None, "windowStart": NOW - 2 * H, "windowEnd": NOW + 12 * H,
                "restricted": False, "channelTotal": None, "matched": None, "epgChannels": 10000,
                "programmeCount": 90000, "warnings": [],
            }
            helper.write_window(os.path.join(tmp, helper.EPG_WINDOW_FILE), meta, channels)
            elapsed = float("inf")
            for _ in range(3):
                started = time.perf_counter()
                code, status, stderr = run("epg", "--now-only", "--cache-dir", tmp,
                                           "--now", str(NOW + 1000))
                elapsed = min(elapsed, time.perf_counter() - started)
                self.assertEqual(code, 0, stderr)
            self.assertEqual(status["nowCount"], 10000)
            doc = read(os.path.join(tmp, "epg-now.json"))
            self.assertEqual(len(doc["channels"]), 10000)
            self.assertEqual(doc["channels"]["chan9999.tv"]["now"]["desc"], detail["desc"])
            # Six times the 176 ms measurement, the same headroom the
            # detail-free case carries over its own 84 ms.
            self.assertLess(elapsed, 1.0,
                            "epg --now-only took %.0f ms (best of 3) for 10k detail-bearing channels"
                            % (elapsed * 1000))

    def test_fetch_2000_channels_streams_quickly(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "big.xml")
            generate_xmltv(source, 2000, 24, NOW - 2 * H)
            started = time.perf_counter()
            code, status, stderr = run("epg", "--url", source, "--cache-dir", tmp, "--now", str(NOW))
            elapsed = time.perf_counter() - started
            self.assertEqual(code, 0, stderr)
            self.assertEqual(status["programmeCount"], 48000)
            self.assertEqual(status["nowCount"], 2000)
            self.assertLess(elapsed, 2.0, "epg fetch took %.0f ms for 48k programmes" % (elapsed * 1000))

    def test_fetch_2000_detail_bearing_channels_streams_quickly(self):
        """The same guide with the M4-02 fields filled to the caps.

        The case above ran the detail-FREE path only, because the generator
        emitted no <desc>, <category> or <episode-num> at all, so M4-02
        widened the pipeline without either budget test ever seeing it. Patch
        detail into the generator and the committed 2.0 s ceiling goes red --
        which is how this case was found, and why its own ceiling is set from
        a measurement rather than inherited.

        Measured on this machine, in-process, same 2,000 x 24 guide:
          detail=False  source  6.76 MiB  fetch  805 ms  window  2.41 MiB
          detail=True   source 32.35 MiB  fetch 2375-2500 ms  window 26.07 MiB
        The ceiling is about 2.5 times the measurement, the same headroom the
        case above carries, because a wall-clock assertion on a loaded
        machine measures the machine. A real regression here is a multiple.
        """
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "big.xml")
            generate_xmltv(source, 2000, 24, NOW - 2 * H, detail=True)
            started = time.perf_counter()
            code, status, stderr = run("epg", "--url", source, "--cache-dir", tmp, "--now", str(NOW))
            elapsed = time.perf_counter() - started
            self.assertEqual(code, 0, stderr)
            self.assertEqual(status["programmeCount"], 48000)
            self.assertEqual(status["nowCount"], 2000)
            # The detail really is in the cache, so the timing above is not
            # measuring a guide whose fields were silently dropped.
            doc = read(os.path.join(tmp, "epg-now.json"))
            entry = doc["channels"]["chan1999.tv"]["now"]
            self.assertEqual(len(entry["desc"]), helper.EPG_MAX_DESC)
            self.assertEqual(len(entry["category"]), helper.EPG_MAX_CATEGORY)
            self.assertEqual(len(entry["episode"]), helper.EPG_MAX_EPISODE)
            self.assertLess(elapsed, 6.0,
                            "epg fetch took %.0f ms for 48k detail-bearing programmes"
                            % (elapsed * 1000))

    def test_a_runs_forever_stop_does_not_destroy_every_channels_guide(self):
        """One programme with a 12-digit stop made epg-now.json unparseable.

        `99991231235959` is a common "runs forever" sentinel for a 24/7 stream.
        It parses to 253402300799, which needs twelve digits, and the record
        format is fixed-width ten: the title was pushed into the number field,
        and because epg-now.json is written by concatenation, ONE such
        programme cost EVERY channel of the source its guide data -- silently,
        with the helper exiting 0 and reporting ok:true, so the guide showed no
        banner and `r` rewrote the same broken file.

        Run against the shipping code before the clamp this is asserting, the
        json.loads below raises JSONDecodeError (CLAUDE.md rule 11).
        """
        with tempfile.TemporaryDirectory() as tmp:
            xml = os.path.join(tmp, "farstop.xml")
            with open(xml, "w", encoding="utf-8") as fh:
                fh.write('<tv>\n'
                         '<programme channel="a" start="20260101000000 +0000" '
                         'stop="20260101060000 +0000"><title>Morning</title></programme>\n'
                         '<programme channel="a" start="20260101060000 +0000" '
                         'stop="99991231235959 +0000"><title>24/7 Stream</title></programme>\n'
                         '</tv>\n')
            code, status, stderr = run("epg", "--url", xml, "--cache-dir", tmp, "--now", "1767247200")
            self.assertEqual(code, 0, stderr)
            self.assertTrue(status["ok"], status)
            with open(os.path.join(tmp, "epg-now.json"), encoding="utf-8") as fh:
                now = json.load(fh)        # this is the line that used to raise
            entry = now["channels"]["a"]["now"]
            self.assertEqual(entry["title"], "24/7 Stream")
            # Clamped to the furthest instant the ten-digit format can hold,
            # which is the truthful reading of "runs forever" here.
            self.assertEqual(entry["stop"], 9999999999)

    def test_an_eleven_digit_stop_is_not_silently_truncated(self):
        """The quieter half: eleven digits produced VALID JSON with a stop of
        1000000000 -- September 2001 -- so the row rendered as having nothing
        on rather than as broken. Valid-but-wrong is worse than unparseable,
        because nothing anywhere reports it."""
        with tempfile.TemporaryDirectory() as tmp:
            xml = os.path.join(tmp, "eleven.xml")
            with open(xml, "w", encoding="utf-8") as fh:
                fh.write('<tv>\n'
                         '<programme channel="a" start="20260101060000 +0000" '
                         'stop="25000101000000 +0000"><title>Long Run</title></programme>\n'
                         '</tv>\n')
            code, status, stderr = run("epg", "--url", xml, "--cache-dir", tmp, "--now", "1767247200")
            self.assertEqual(code, 0, stderr)
            with open(os.path.join(tmp, "epg-now.json"), encoding="utf-8") as fh:
                now = json.load(fh)
            entry = now["channels"]["a"]["now"]
            self.assertEqual(entry["title"], "Long Run")
            self.assertGreater(entry["stop"], 1767247200,
                               "a stop in the future must not read as one in the past")


class EpgNowLineShapeTest(unittest.TestCase):
    """D-EPG-11 (R31b, R31c): the shape write_epg_now writes, and the one
    invariant the shell's coverage count relies on.

    The shell no longer parses epg-now.json whole: it indexes the file by
    LINE (Model.parseEpgNowStore) and counts a channel as covered when the
    index holds its id (Model.epgCoverage). Both are true only if the
    helper writes the header line, then one channel fragment per line, then
    `}}`, and never writes an entry without a titled now or next. Every
    other reader (json.load, jq, the old parse) sees the same document.
    """

    def write(self, tmp, channels, now=NOW):
        meta = {"version": 1, "fetchedAt": NOW, "sourceHost": "epg.example.test", "sourceKey": "x",
                "channelsMtime": None, "windowStart": NOW - 2 * H, "windowEnd": NOW + 12 * H,
                "restricted": False, "channelTotal": None, "matched": None, "epgChannels": len(channels),
                "programmeCount": 0, "warnings": []}
        helper.write_window(os.path.join(tmp, helper.EPG_WINDOW_FILE), meta, channels)
        valid_until, now_count, skipped = helper.write_epg_now(tmp, helper.load_window(os.path.join(tmp, helper.EPG_WINDOW_FILE)), now)
        self.assertEqual(skipped, 0, "a window this helper wrote has no unreadable line (D-EPG-14)")
        with open(os.path.join(tmp, "epg-now.json"), encoding="utf-8") as fh:
            return fh.read(), now_count

    def records(self, *items):
        return helper.EPG_RECORD_SEP.join(helper.encode_record(*item) for item in items)

    def test_one_channel_fragment_per_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            text, now_count = self.write(tmp, {
                "a.tv": self.records((NOW - 600, NOW + 600, "Now A", {"desc": "d"}), (NOW + 600, NOW + 1200, "Next A")),
                'q"uote': self.records((NOW - 600, NOW + 600, "Quoted")),
                "last\\one": self.records((NOW + 60, NOW + 660, "Only Next")),
            })
            lines = text.split("\n")
            self.assertTrue(lines[0].endswith(',"channels":{'), lines[0])
            self.assertEqual(lines[-2:], ["}}", ""], "the close on its own line, then the final newline")
            middle = lines[1:-2]
            self.assertEqual(len(middle), 3, "one line a channel")
            for i, line in enumerate(middle):
                self.assertTrue(line.startswith('"'), line)
                self.assertEqual(line.endswith(","), i < len(middle) - 1, "a trailing comma on every line but the last: %r" % line)
            doc = json.loads(text)
            self.assertEqual(sorted(doc["channels"]), ["a.tv", "last\\one", 'q"uote'])
            # Each line parses on its own as the one-entry object the shell
            # slices out of it, and the lines together ARE the document.
            rebuilt = {}
            for line in middle:
                rebuilt.update(json.loads("{" + line.rstrip(",") + "}"))
            self.assertEqual(rebuilt, doc["channels"])
            self.assertEqual(now_count, 2)

    def test_an_empty_channels_map_is_the_header_and_the_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            text, now_count = self.write(tmp, {})
            self.assertEqual(text.split("\n")[1:], ["}}", ""])
            self.assertEqual(json.loads(text)["channels"], {})
            self.assertEqual(now_count, 0)

    def test_an_untitled_programme_is_never_written(self):
        """R31c. The window format can hold a record whose title is "" (the
        parse skips those as noTitle, but encode_record does not refuse
        them), and the old writer passed it through as "title":"" -- an
        entry the shell's index would count as coverage and the row would
        draw as nothing. compute_now_next drops the untitled half, and the
        entry when both halves are gone."""
        with tempfile.TemporaryDirectory() as tmp:
            text, now_count = self.write(tmp, {
                "next-only": self.records((NOW - 600, NOW + 600, ""), (NOW + 600, NOW + 1200, "Titled Next")),
                "nothing": self.records((NOW - 600, NOW + 600, ""), (NOW + 600, NOW + 1200, "")),
                "now-only": self.records((NOW - 600, NOW + 600, "Titled Now", {"desc": "d"}), (NOW + 600, NOW + 1200, "")),
                "both": self.records((NOW - 600, NOW + 600, "N"), (NOW + 600, NOW + 1200, "X")),
                "quoted-empty": self.records((NOW - 600, NOW + 600, '""')),
            })
            channels = json.loads(text)["channels"]
            self.assertEqual(sorted(channels), ["both", "next-only", "now-only", "quoted-empty"])
            self.assertEqual(channels["next-only"], {"next": {"title": "Titled Next", "start": NOW + 600, "stop": NOW + 1200}})
            self.assertEqual(channels["now-only"], {"now": {"title": "Titled Now", "desc": "d", "start": NOW - 600, "stop": NOW + 600}})
            self.assertEqual(channels["quoted-empty"]["now"]["title"], '""', "a title that IS two quote characters is a title")
            for entry in channels.values():
                self.assertTrue(any(entry.get(k, {}).get("title") for k in ("now", "next")), entry)
            self.assertEqual(now_count, 3, "the untitled now is not a now")

    def test_a_legacy_single_line_file_is_rewritten_by_the_recompute(self):
        """R31b, the helper's half: 0.14.3's helper wrote the document on
        one line, and a shell updated under it reads that file once through
        its old path; the next `epg --now-only` (the 5-minute recompute,
        which reads the window and never the file) leaves the new shape."""
        with tempfile.TemporaryDirectory() as tmp:
            self.write(tmp, {"a.tv": self.records((NOW - 600, NOW + 600, "Now A"), (NOW + 600, NOW + 1200, "Next A"))})
            path = os.path.join(tmp, "epg-now.json")
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(doc, separators=(",", ":")) + "\n")
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(len(fh.read().split("\n")), 2, "the legacy shape: one line")
            code, status, stderr = run("epg", "--now-only", "--cache-dir", tmp, "--now", str(NOW + 30))
            self.assertEqual(code, 0, stderr)
            self.assertTrue(status["ok"], status)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            lines = text.split("\n")
            self.assertEqual(len(lines), 4, text)
            self.assertTrue(lines[0].endswith(',"channels":{'))
            self.assertTrue(lines[1].startswith('"a.tv":{'))
            self.assertEqual(lines[2:], ["}}", ""])
            self.assertEqual(json.loads(text)["channels"], doc["channels"])


if __name__ == "__main__":
    unittest.main()
