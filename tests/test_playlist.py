"""M3U parser tests for bin/omarchy-iptv. Run: python3 -m unittest discover -s tests"""
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
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class NormalizationTest(unittest.TestCase):
    # Shared vectors with tests/Model.test.js -- keep both in sync.
    def test_search_key_folds_punctuation_and_case(self):
        self.assertEqual(helper.search_key("BBC-One HD", "UK: News"), "bbc one hd uk news")

    def test_search_key_folds_diacritics(self):
        self.assertEqual(helper.search_key("T\u00e9l\u00e9 Qu\u00e9bec", ""), "tele quebec")

    def test_search_key_keeps_non_latin(self):
        self.assertEqual(helper.search_key("\u041f\u0435\u0440\u0432\u044b\u0439 \u043a\u0430\u043d\u0430\u043b", "RU"),
                         "\u043f\u0435\u0440\u0432\u044b\u0439 \u043a\u0430\u043d\u0430\u043b ru")

    def test_search_key_empty_group(self):
        self.assertEqual(helper.search_key("CNN", None), "cnn")

    def test_decomposed_latin_accents_fold_but_other_scripts_keep_their_marks(self):
        # D-QA-08: NFD, drop U+0300-U+036F after an ASCII letter, NFC -- same as Model.js decompose().
        self.assertEqual(helper.normalize_text("Cafe\u0301 NFD"), "cafe nfd")
        self.assertEqual(helper.normalize_text("\u0418\u0306 \u0439"), "\u0439 \u0439")      # Cyrillic short i keeps its breve
        self.assertEqual(helper.normalize_text("\u1ec7"), "e")                               # Vietnamese e with two marks
        self.assertEqual(helper.normalize_text("\ufb01lm"), "\ufb01lm")                      # NFD (not NFKD): ligatures untouched, like Model.js
        self.assertEqual(helper.normalize_text("\ud55c\uae00"), "\ud55c\uae00")              # Hangul recomposes
        self.assertEqual(helper.normalize_text("\u03ac"), "\u03ac")                          # Greek alpha with tonos kept

    def test_fnv1a32_vectors(self):
        self.assertEqual(helper.fnv1a32(""), "811c9dc5")
        self.assertEqual(helper.fnv1a32("a"), "e40c292c")
        self.assertEqual(helper.fnv1a32("foobar"), "bf9cf968")

    def test_fold_table_matches_model_js(self):
        model = (pathlib.Path(__file__).resolve().parent.parent / "Model.js").read_text(encoding="ascii")
        for chars, replacement in helper.FOLD_GROUPS:
            escaped = "".join("\\u%04x" % ord(ch) for ch in chars)
            self.assertIn('["%s", "%s"]' % (escaped, replacement), model)


class ExtinfTest(unittest.TestCase):
    def test_quoted_attributes_and_title_with_commas(self):
        attrs, title = helper.parse_extinf('#EXTINF:-1 tvg-id="a.b" group-title="News, World",CNN International, Europe feed')
        self.assertEqual(attrs, {"tvg-id": "a.b", "group-title": "News, World"})
        self.assertEqual(title, "CNN International, Europe feed")

    def test_bare_attributes(self):
        attrs, title = helper.parse_extinf("#EXTINF:0 tvg-id=espn.us tvg-chno=12,ESPN")
        self.assertEqual(attrs, {"tvg-id": "espn.us", "tvg-chno": "12"})
        self.assertEqual(title, "ESPN")

    def test_no_attributes(self):
        attrs, title = helper.parse_extinf("#EXTINF:-1,Plain Channel")
        self.assertEqual(attrs, {})
        self.assertEqual(title, "Plain Channel")

    def test_duration_float_and_missing_title(self):
        attrs, title = helper.parse_extinf('#EXTINF:12.5 tvg-name="X",')
        self.assertEqual(attrs, {"tvg-name": "X"})
        self.assertEqual(title, "")


class ParseM3uTest(unittest.TestCase):
    def test_basic_fixture(self):
        result = helper.parse_m3u(fixture("basic.m3u"))
        channels = result["channels"]
        self.assertEqual(result["epgUrlHint"], "http://epg.example.test/guide.xml.gz")
        self.assertEqual([c["name"] for c in channels], ["BBC One HD", "CNN International, Europe feed", "Plain Channel"])
        self.assertEqual([c["group"] for c in channels], ["UK", "News, World", "Ungrouped"])
        self.assertEqual(channels[0]["tvgId"], "bbc1.uk")
        self.assertEqual(channels[0]["tvgName"], "BBC One")
        self.assertEqual(channels[0]["logo"], "http://logos.example.test/bbc1.png")
        self.assertEqual(channels[0]["url"], "http://stream.example.test/live/bbc1.m3u8")
        self.assertEqual(channels[0]["searchKey"], "bbc one hd uk")
        self.assertEqual(channels[0]["id"], "t:bbc1.uk")
        self.assertEqual(channels[2]["id"], "u:" + helper.fnv1a32(channels[2]["url"]))
        self.assertEqual(result["warnings"], [])

    def test_attributes_fixture(self):
        result = helper.parse_m3u(fixture("attributes.m3u"))
        channels = result["channels"]
        names = [c["name"] for c in channels]
        self.assertEqual(names, ["ESPN", "Duplicate tvg id", "Still Sports via EXTGRP", "Same URL twice A", "Same URL twice B"])
        espn = channels[0]
        self.assertEqual(espn["group"], "Sports")
        self.assertEqual(espn["chno"], "12")
        self.assertEqual(espn["headers"], {"User-Agent": "VLC/3.0.20", "Referer": "http://ref.example.test/"})
        self.assertEqual(espn["options"], {"vlc:network-caching": "1000"})
        # group-title beats the persisting #EXTGRP
        self.assertEqual(channels[1]["group"], "Movies")
        # duplicate tvg-id falls back to URL hashes for both members
        self.assertEqual(espn["id"], "u:" + helper.fnv1a32(espn["url"]))
        self.assertEqual(channels[1]["id"], "u:" + helper.fnv1a32(channels[1]["url"]))
        # #EXTGRP persists until replaced
        self.assertEqual(channels[2]["group"], "Sports")
        self.assertEqual(channels[2]["headers"], {"User-Agent": "Kodi/20", "X-Forwarded-For": "1.2.3.4"})
        self.assertEqual(channels[2]["options"], {"kodi:inputstream.adaptive.manifest_type": "hls"})
        # identical URLs get distinct ids
        self.assertEqual(channels[3]["id"], "u:" + helper.fnv1a32(channels[3]["url"]))
        self.assertEqual(channels[4]["id"], channels[3]["id"] + "#2")
        self.assertIn("3 entries skipped: unsupported URL scheme", result["warnings"])
        self.assertIn("1 URL lines without #EXTINF skipped", result["warnings"])

    def test_crlf_and_bom(self):
        text = "\ufeff#EXTM3U\r\n#EXTINF:-1 group-title=\"A\",One\r\nhttp://x.test/1\r\n"
        result = helper.parse_m3u(text)
        self.assertEqual(len(result["channels"]), 1)
        self.assertEqual(result["channels"][0]["group"], "A")

    def test_vlcopt_does_not_leak_to_next_entry(self):
        text = "#EXTM3U\n#EXTINF:-1,A\n#EXTVLCOPT:http-user-agent=UA\nhttp://x.test/a\n#EXTINF:-1,B\nhttp://x.test/b\n"
        channels = helper.parse_m3u(text)["channels"]
        self.assertEqual(channels[0]["headers"], {"User-Agent": "UA"})
        self.assertNotIn("headers", channels[1])

    def test_header_values_strip_newlines(self):
        text = "#EXTM3U\n#EXTINF:-1,A\n#EXTVLCOPT:http-user-agent=bad\rvalue\nhttp://x.test/a\n"
        channels = helper.parse_m3u(text)["channels"]
        self.assertEqual(channels[0]["headers"]["User-Agent"], "bad value")

    def test_non_http_logo_dropped(self):
        text = '#EXTM3U\n#EXTINF:-1 tvg-logo="file:///etc/x.png",A\nhttp://x.test/a\n'
        self.assertNotIn("logo", helper.parse_m3u(text)["channels"][0])

    def test_empty_input(self):
        self.assertEqual(helper.parse_m3u("")["channels"], [])


class SourceTest(unittest.TestCase):
    def test_resolve_http(self):
        self.assertEqual(helper.resolve_source("https://h.test/get.php?u=a&p=b"), ("http", "https://h.test/get.php?u=a&p=b"))

    def test_resolve_absolute_path_and_file_url(self):
        self.assertEqual(helper.resolve_source("/tmp/list.m3u"), ("file", "/tmp/list.m3u"))
        self.assertEqual(helper.resolve_source("file:///tmp/a%20b.m3u"), ("file", "/tmp/a b.m3u"))

    def test_refuses_other_schemes(self):
        for bad in ("ftp://h.test/x.m3u", "relative/path.m3u", "javascript:alert(1)", "", "data:text/plain,x"):
            with self.assertRaises(helper.HelperError):
                helper.resolve_source(bad)
        # SR12: a protocol-relative URL is a scheme error, never a local path.
        with self.assertRaises(helper.HelperError) as caught:
            helper.resolve_source("//h.test/x.m3u")
        self.assertEqual(caught.exception.code, "unsupported_scheme")

    def test_http_source_without_host_is_bad_url(self):
        for bad in ("http://", "https:///list.m3u", "http://:8080/x"):
            with self.assertRaises(helper.HelperError) as caught:
                helper.resolve_source(bad)
            self.assertEqual(caught.exception.code, "bad_url", bad)

    def test_source_host_never_leaks_credentials(self):
        self.assertEqual(helper.source_host("http://user:pass@h.test/get.php?username=u&password=p"), "h.test")


class RulingsTest(unittest.TestCase):
    # R4: searchKey = fold(name + " " + group); R5: multi-group under the FIRST group.
    def test_multi_group_lists_under_first_group_and_keeps_all_searchable(self):
        text = '#EXTM3U\n#EXTINF:-1 tvg-id="a.us" group-title="Animation;Kids; Religious;Kids;",Toon Time\nhttp://x.test/a\n'
        channel = helper.parse_m3u(text)["channels"][0]
        self.assertEqual(channel["group"], "Animation")
        self.assertEqual(channel["groups"], ["Animation", "Kids", "Religious"])
        self.assertEqual(channel["searchKey"], "toon time animation kids religious")

    def test_single_group_has_no_groups_field(self):
        text = '#EXTM3U\n#EXTINF:-1 group-title="News",CNN\nhttp://x.test/a\n#EXTINF:-1,Plain\nhttp://x.test/b\n'
        channels = helper.parse_m3u(text)["channels"]
        self.assertNotIn("groups", channels[0])
        self.assertEqual(channels[0]["searchKey"], "cnn news")
        self.assertEqual(channels[1]["group"], "Ungrouped")
        self.assertEqual(channels[1]["searchKey"], "plain ungrouped")

    def test_extgrp_multi_group(self):
        text = "#EXTM3U\n#EXTGRP:Sports;HD\n#EXTINF:-1,Match\nhttp://x.test/a\n"
        channel = helper.parse_m3u(text)["channels"][0]
        self.assertEqual(channel["group"], "Sports")
        self.assertEqual(channel["groups"], ["Sports", "HD"])
        self.assertEqual(channel["searchKey"], "match sports hd")

    def test_search_key_folds_name_and_group(self):
        text = '#EXTM3U\n#EXTINF:-1 group-title="CA: Qu\u00e9bec",T\u00e9l\u00e9-Qu\u00e9bec HD\nhttp://x.test/a\n'
        channel = helper.parse_m3u(text)["channels"][0]
        self.assertEqual(channel["searchKey"], "tele quebec hd ca quebec")


class HardeningTest(unittest.TestCase):
    def parse(self, text):
        return helper.parse_m3u(text)

    def test_extinf_without_comma(self):
        result = self.parse('#EXTM3U\n#EXTINF:-1 tvg-id="x.tv" Channel X\nhttp://x.test/1\n#EXTINF:-1 Plain No Comma\nhttp://x.test/2\n')
        self.assertEqual([c["name"] for c in result["channels"]], ["Channel X", "Plain No Comma"])
        self.assertEqual(result["channels"][0]["tvgId"], "x.tv")

    def test_name_never_falls_back_to_the_url(self):
        text = '#EXTM3U\n#EXTINF:-1 tvg-id="only.id",\nhttp://user:pw@h.test/secret\n#EXTINF:-1,\nhttp://user:pw@h.test/secret2\n#EXTINF:-1 tvg-name="Named",\nhttp://h.test/3\n'
        names = [c["name"] for c in self.parse(text)["channels"]]
        self.assertEqual(names, ["only.id", "Channel 2", "Named"])
        for name in names:
            self.assertNotIn("secret", name)
            self.assertNotIn("pw", name)

    def test_names_never_start_with_a_dash(self):
        # S-04: the name becomes an argv item for omarchy-notification-send,
        # where "--urgency=x did not play" would be parsed as an option.
        text = ('#EXTM3U\n#EXTINF:-1,--urgency=critical\nhttp://x.test/1\n'
                '#EXTINF:-1 tvg-name="-Real Name",---\nhttp://x.test/2\n'
                '#EXTINF:-1 tvg-id="-dashed.id" tvg-name="--",- \nhttp://x.test/3\n'
                '#EXTINF:-1 tvg-id="--",--\nhttp://x.test/4\n'
                '#EXTINF:-1,-Minus TV\nhttp://x.test/5\n'
                '#EXTINF:-1,A-B Sports -\nhttp://x.test/6\n')
        channels = helper.parse_m3u(text)["channels"]
        names = [c["name"] for c in channels]
        self.assertEqual(names, ["urgency=critical", "Real Name", "dashed.id", "Channel 4", "Minus TV", "A-B Sports -"])
        for name in names:
            self.assertFalse(name.startswith("-"), name)
        self.assertEqual(channels[2]["tvgId"], "-dashed.id")      # ids stay raw for EPG matching
        self.assertEqual(channels[1]["tvgName"], "-Real Name")     # attribute kept verbatim
        self.assertEqual(channels[0]["searchKey"], "urgency critical ungrouped")
        self.assertEqual(helper.clean_name("  - x "), "x")
        self.assertEqual(helper.clean_name(None), "")

    def test_duplicate_attribute_keys_last_non_empty_wins(self):
        attrs, title = helper.parse_extinf('#EXTINF:-1 tvg-id="" tvg-id="real" tvg-name="A" tvg-name="" tvg-logo="http://a" tvg-logo="http://b",X')
        self.assertEqual(attrs, {"tvg-id": "real", "tvg-name": "A", "tvg-logo": "http://b"})
        self.assertEqual(title, "X")

    def test_unquoted_values_and_mixed_case_keys(self):
        attrs, title = helper.parse_extinf("#EXTINF:-1 TVG-ID=abc.de Group-Title=Sports,Name")
        self.assertEqual(attrs, {"tvg-id": "abc.de", "group-title": "Sports"})
        self.assertEqual(title, "Name")

    def test_free_text_after_extinf_is_an_unsupported_location(self):
        # VLC semantics: the first non-comment line is the entry's location.
        result = self.parse("#EXTM3U\n#EXTINF:-1,A\nNote: this is not a url\n   \n\t\nhttp://x.test/a\n#EXTINF:-1,B\nhttp://x.test/b\n")
        self.assertEqual([c["name"] for c in result["channels"]], ["B"])
        self.assertEqual(sorted(result["warnings"]), ["1 URL lines without #EXTINF skipped", "1 entries skipped: unsupported URL scheme"])

    def test_extinf_without_url_is_counted(self):
        result = self.parse("#EXTM3U\n#EXTINF:-1,A\n#EXTINF:-1,B\nhttp://x.test/b\n#EXTINF:-1,C\n")
        self.assertEqual([c["name"] for c in result["channels"]], ["B"])
        self.assertIn("2 #EXTINF entries without a URL skipped", result["warnings"])

    def test_non_stream_schemes_are_skipped_and_counted(self):
        text = ("#EXTM3U\n#EXTINF:-1,RTMP ok\nrtmp://x.test/live\n#EXTINF:-1,FTP no\nftp://x.test/a\n"
                "#EXTINF:-1,File no\nfile:///etc/passwd\n#EXTINF:-1,Option no\n--input-ipc-server=/tmp/x\n"
                "#EXTINF:-1,Data no\ndata:text/plain,hi\n#EXTINF:-1,HTTPS ok\nhttps://x.test/b\n")
        result = self.parse(text)
        self.assertEqual([c["name"] for c in result["channels"]], ["RTMP ok", "HTTPS ok"])
        self.assertEqual(result["warnings"], ["4 entries skipped: unsupported URL scheme"])

    def test_urls_without_a_host_are_skipped(self):
        result = self.parse("#EXTM3U\n#EXTINF:-1,No host\nhttp://\n#EXTINF:-1,Multicast\nudp://@239.0.0.1:1234\n#EXTINF:-1,Ok\nhttps://x.test/a\n")
        self.assertEqual([c["name"] for c in result["channels"]], ["Multicast", "Ok"])
        self.assertEqual(result["warnings"], ["1 entries skipped: unsupported URL scheme"])

    def test_hls_tags_and_unknown_comments_are_ignored(self):
        result = self.parse("#EXTM3U\n#EXT-X-VERSION:3\n#PLAYLIST:Mine\n#EXTINF:-1,A\n#EXT-X-DISCONTINUITY\nhttp://x.test/a\n")
        self.assertEqual(len(result["channels"]), 1)
        self.assertEqual(result["warnings"], [])

    def test_bom_crlf_blank_lines_and_trailing_whitespace(self):
        text = "\ufeff#EXTM3U \r\n\r\n#EXTINF:-1 group-title=\"A\" ,One  \r\n\r\n   http://x.test/1   \r\n\r\n"
        result = self.parse(text)
        self.assertEqual(len(result["channels"]), 1)
        self.assertEqual(result["channels"][0]["name"], "One")
        self.assertEqual(result["channels"][0]["url"], "http://x.test/1")

    def test_kodiprop_manifest_headers_and_unsafe_names(self):
        text = ("#EXTM3U\n#EXTINF:-1,A\n#KODIPROP:inputstream.adaptive.manifest_headers=Authorization=Bearer%20x&bad%20name=1\n"
                "#KODIPROP:inputstream.adaptive.license_key=http://lic.test/\nhttp://x.test/a\n")
        result = self.parse(text)
        channel = result["channels"][0]
        self.assertEqual(channel["headers"], {"Authorization": "Bearer x"})
        self.assertEqual(channel["options"], {"kodi:inputstream.adaptive.license_key": "http://lic.test/"})
        self.assertIn("dropped header with unsafe name for A", result["warnings"])

    def test_chno_and_logo(self):
        channel = self.parse('#EXTM3U\n#EXTINF:-1 tvg-chno="12" tvg-logo="https://l.test/a.png",A\nhttp://x.test/a\n')["channels"][0]
        self.assertEqual(channel["chno"], "12")
        self.assertEqual(channel["logo"], "https://l.test/a.png")


class CapTest(unittest.TestCase):
    """S-07: channels.json stays bounded whatever the source contains."""

    @staticmethod
    def playlist(count, group_of):
        lines = ["#EXTM3U"]
        for i in range(count):
            lines.append('#EXTINF:-1 group-title="%s",Ch %d' % (group_of(i), i))
            lines.append("http://x.test/%d" % i)
        return "\n".join(lines) + "\n"

    def test_channel_count_is_capped_with_a_warning(self):
        extra = 5
        started = time.perf_counter()
        result = helper.parse_m3u(self.playlist(helper.MAX_CHANNELS + extra, lambda i: "G%d" % (i % 10)))
        elapsed = time.perf_counter() - started
        channels = result["channels"]
        self.assertEqual(helper.MAX_CHANNELS, 50000)
        self.assertEqual(len(channels), helper.MAX_CHANNELS)
        self.assertEqual(channels[-1]["name"], "Ch %d" % (helper.MAX_CHANNELS - 1))
        self.assertIn("truncated to 50000 channels (%d entries skipped)" % extra, result["warnings"])
        self.assertEqual(len({c["id"] for c in channels}), helper.MAX_CHANNELS)
        self.assertLess(elapsed, 5.0, "parse of %d entries took %.1f s" % (helper.MAX_CHANNELS + extra, elapsed))

    def test_channel_count_at_the_cap_is_not_a_warning(self):
        result = helper.parse_m3u(self.playlist(helper.MAX_CHANNELS, lambda i: "G"))
        self.assertEqual(len(result["channels"]), helper.MAX_CHANNELS)
        self.assertEqual(result["warnings"], [])

    def test_group_count_is_capped_into_ungrouped_with_a_warning(self):
        extra = 100
        # One channel already Ungrouped, then one unique group per channel.
        result = helper.parse_m3u(self.playlist(helper.MAX_GROUPS + extra + 1, lambda i: "" if i == 0 else "Group %d" % i))
        channels = result["channels"]
        self.assertEqual(helper.MAX_GROUPS, 2000)
        groups = [c["group"] for c in channels]
        self.assertEqual(len(channels), helper.MAX_GROUPS + extra + 1)
        # Ungrouped seen first counts as one of the MAX_GROUPS buckets.
        self.assertEqual(len(set(groups)), helper.MAX_GROUPS)
        self.assertEqual(groups[0], "Ungrouped")
        self.assertEqual(groups[1], "Group 1")
        self.assertEqual(groups[helper.MAX_GROUPS - 1], "Group %d" % (helper.MAX_GROUPS - 1))   # 1999 named + Ungrouped
        self.assertEqual(set(groups[helper.MAX_GROUPS:]), {"Ungrouped"})
        self.assertIn("group count capped at 2000; %d channels listed under Ungrouped" % (extra + 1), result["warnings"])
        # The provider's group stays searchable.
        moved = channels[helper.MAX_GROUPS]
        self.assertEqual(moved["searchKey"], "ch %d group %d" % (helper.MAX_GROUPS, helper.MAX_GROUPS))

    def test_group_cap_allows_ungrouped_as_one_extra_bucket(self):
        # No Ungrouped channel before the cap: overflow creates it as bucket MAX_GROUPS + 1.
        result = helper.parse_m3u(self.playlist(helper.MAX_GROUPS + 3, lambda i: "Group %d" % i))
        groups = [c["group"] for c in result["channels"]]
        self.assertEqual(len(set(groups)), helper.MAX_GROUPS + 1)
        self.assertEqual(groups[-3:], ["Ungrouped"] * 3)
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "groups.m3u")
            with open(source, "w", encoding="ascii") as handle:
                handle.write(self.playlist(helper.MAX_GROUPS + 3, lambda i: "Group %d" % i))
            code, status = run_main("playlist", "--url", source, "--cache-dir", tmp)
            self.assertEqual(code, 0)
            self.assertEqual(status["channelCount"], helper.MAX_GROUPS + 3)
            self.assertEqual(status["groupCount"], helper.MAX_GROUPS + 1)
            self.assertTrue(any(w.startswith("group count capped") for w in status["warnings"]))


class RedactionTest(unittest.TestCase):
    def test_redact_urls_keeps_scheme_and_host_only(self):
        text = "HTTP 404 from http://user:pw@h.test/get.php?u=a&p=b and file:///etc/x and rtsp://cam.test:554/s"
        self.assertEqual(helper.redact_urls(text), "HTTP 404 from http://h.test and file://[redacted] and rtsp://cam.test")
        self.assertEqual(helper.redact_urls(None), "")
        self.assertEqual(helper.redact_urls("no urls here"), "no urls here")

    def test_error_payload_is_redacted(self):
        error = helper.HelperError("network", "could not reach https://user:pw@h.test/a/b?c=d: timed out")
        payload = helper.error_payload("playlist", error)
        self.assertEqual(payload["error"]["message"], "could not reach https://h.test: timed out")


def run_main(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = helper.main(list(args))
    return code, json.loads(out.getvalue().strip().splitlines()[-1])


class PerformanceTest(unittest.TestCase):
    def test_10k_entries_parse_and_write_under_one_second(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = ['#EXTM3U url-tvg="http://epg.example.test/guide.xml"']
            for i in range(10000):
                lines.append('#EXTINF:-1 tvg-id="ch%d.us" tvg-name="Channel %d" tvg-logo="http://logos.example.test/%d.png" group-title="Group %d;Extra",Channel %d HD'
                             % (i, i, i, i % 50, i))
                if i % 7 == 0:
                    lines.append("#EXTVLCOPT:http-user-agent=Agent/%d" % i)
                lines.append("http://stream.example.test/live/%d/index.m3u8" % i)
            source = os.path.join(tmp, "big.m3u")
            with open(source, "w", encoding="ascii") as handle:
                handle.write("\n".join(lines) + "\n")
            started = time.perf_counter()
            code, status = run_main("playlist", "--url", source, "--cache-dir", tmp)
            elapsed = time.perf_counter() - started
            self.assertEqual(code, 0)
            self.assertEqual(status["channelCount"], 10000)
            self.assertEqual(status["groupCount"], 50)
            with open(os.path.join(tmp, "channels.json"), encoding="utf-8") as handle:
                document = json.loads(handle.read())
            self.assertEqual(document["count"], 10000)
            self.assertEqual(document["channels"][7]["headers"], {"User-Agent": "Agent/7"})
            self.assertLess(elapsed, 1.0, "playlist parse+write took %.0f ms for 10k entries" % (elapsed * 1000))


class QaFixtureTest(unittest.TestCase):
    """Expected values from docs/QA.md section 7 (fixture catalogue), applied
    with rulings R5 and D-QA-02/03/07/08/09/10/13."""

    def parse(self, name):
        # Bytes, like the helper: text mode would turn the bare CR in
        # qa-headers.m3u into a line break.
        return helper.parse_m3u((FIXTURES / name).read_bytes().decode("utf-8"))

    def test_qa_groups(self):
        result = self.parse("qa-groups.m3u")
        channels = result["channels"]
        self.assertEqual(len(channels), 10)
        self.assertEqual([c["group"] for c in channels],
                         ["Animation", "UK | SPORTS", "Sports", "Sports", "Movies", "News", "Ungrouped", "Padded", "Leading Semicolon", "Ungrouped"])
        self.assertEqual(channels[0]["groups"], ["Animation", "Kids", "Religious"])
        self.assertEqual(channels[0]["searchKey"], "multi group channel animation kids religious")
        self.assertNotIn("groups", channels[8])
        self.assertEqual(result["warnings"], [])

    def test_qa_attrs(self):
        result = self.parse("qa-attrs.m3u")
        channels = result["channels"]
        self.assertEqual(len(channels), 22)
        self.assertEqual(result["epgUrlHint"], "http://epg.example.test/guide.xml.gz")
        ids = [c["id"] for c in channels]
        self.assertEqual(ids[0], "t:espn.us")
        self.assertEqual(channels[0]["chno"], "12")
        self.assertEqual(channels[0]["group"], "Sports")
        self.assertEqual(ids[1:5], ["u:a3d5424f", "u:8e5692d2", "u:cc5a0021", "u:cc5a0021#2"])
        self.assertEqual(ids[1], "u:" + helper.fnv1a32(channels[1]["url"]))
        self.assertEqual(channels[5]["name"], "Title, With, Commas")
        self.assertEqual(channels[5]["group"], "News, World")
        self.assertEqual(channels[8]["name"], "Broken EXTINF Without Comma")
        self.assertEqual(channels[8]["tvgId"], "nocomma.test")
        self.assertEqual(channels[9]["name"], "Name From tvg-name")
        self.assertEqual(channels[10]["name"], "Channel 11")   # D-QA-02: never the credentialed URL
        self.assertEqual(channels[11]["logo"], "https://logos.example.test/ok.png")
        self.assertNotIn("logo", channels[12])
        self.assertEqual(channels[13]["group"], "Upper")
        self.assertEqual(channels[13]["tvgId"], "upper.test")
        self.assertEqual(channels[14]["group"], "News")       # a bare value stops at the space
        self.assertEqual(channels[15]["group"], "Second")
        self.assertEqual(channels[16]["group"], "Ungrouped")
        self.assertEqual(channels[17]["id"], "t:spaced.id")
        self.assertEqual(channels[18]["name"], "Blank Lines Before URL")
        self.assertEqual(channels[19]["name"], "Second Of Two EXTINF Is Kept")
        self.assertEqual(channels[20]["group"], "Tabbed")
        self.assertTrue(channels[21]["name"].startswith("Long Title word00"))
        self.assertGreater(len(channels[21]["name"]), 250)
        self.assertEqual(result["warnings"], ["1 #EXTINF entries without a URL skipped"])

    def test_qa_headers(self):
        result = self.parse("qa-headers.m3u")
        channels = {c["tvgId"]: c for c in result["channels"]}
        self.assertEqual(len(channels), 11)
        self.assertEqual(sorted(result["warnings"]), sorted([
            "dropped header with unsafe name for KODIPROP Percent Encoded CRLF And Bad Name",
            "dropped option-looking key for Option Looking VLCOPT Key",
            "1 entries skipped: unsupported URL scheme",
        ]))
        self.assertEqual(channels["vlc.test"]["headers"], {"User-Agent": "Mozilla/5.0 (QA) VLC/3.0.20", "Referer": "https://ref.example.test/player"})
        self.assertEqual(channels["vlc.test"]["options"], {"vlc:network-caching": "1500"})
        self.assertNotIn("headers", channels["clean.test"])
        self.assertEqual(channels["before.test"]["headers"], {"User-Agent": "Before/1.0"})
        self.assertEqual(channels["cr.test"]["headers"], {"User-Agent": "Evil/1.0 X-Injected: yes"})
        self.assertEqual(channels["kodi.test"]["headers"], {"User-Agent": "Kodi/20.2", "Referer": "https://ref.example.test/", "X-Forwarded-For": "1.2.3.4"})
        self.assertEqual(channels["kodi.test"]["options"], {"kodi:inputstream.adaptive.manifest_type": "hls", "kodi:inputstreamaddon": "inputstream.adaptive"})
        self.assertEqual(channels["kodicrlf.test"]["headers"], {"X-Inject": "a  X-Evil: b", "X-Ok": "1"})
        self.assertEqual(channels["meta.test"]["headers"]["User-Agent"], "UA \"quoted\" 'single' $(id) `id` ; & | > /tmp/x")
        self.assertEqual(channels["optkey.test"]["headers"], {"User-Agent": "--script=/tmp/evil.lua"})
        self.assertNotIn("options", channels["optkey.test"])              # D-QA-09
        self.assertNotIn("headers", channels["emptyua.test"])             # D-QA-10
        self.assertEqual(channels["case.test"]["headers"], {"User-Agent": "Upper/1.0"})
        self.assertNotIn("headers", channels["afterskip.test"])
        self.assertNotIn("orphanopt.test", channels)

    def test_qa_schemes(self):
        result = self.parse("qa-schemes.m3u")
        self.assertEqual([c["tvgId"] for c in result["channels"]],
                         ["ok-http", "ok-https", "ok-rtsp", "ok-udp", "ok-rtp", "ok-rtmp", "ok-rtmps", "ok-mms", "ok-mmsh", "ok-srt",
                          "ok-upper", "ok-space", "ok-inner-space"])
        self.assertEqual(sorted(result["warnings"]), ["2 URL lines without #EXTINF skipped", "22 entries skipped: unsupported URL scheme"])
        self.assertEqual(result["channels"][11]["url"], "http://padded.example.test/ok.m3u8")

    def test_qa_empty_and_not_a_playlist(self):
        empty = self.parse("qa-empty.m3u")
        self.assertEqual(empty["channels"], [])
        self.assertTrue(empty["isPlaylist"])
        html = self.parse("qa-not-m3u.html")
        self.assertEqual(html["channels"], [])
        self.assertFalse(html["isPlaylist"])
        with tempfile.TemporaryDirectory() as tmp:
            code, status = run_main("playlist", "--url", str(FIXTURES / "qa-not-m3u.html"), "--cache-dir", tmp)
            self.assertEqual(code, 1)
            self.assertEqual(status["error"]["code"], "not_a_playlist")
            code, status = run_main("playlist", "--url", str(FIXTURES / "qa-empty.m3u"), "--cache-dir", tmp)
            self.assertEqual(code, 1)
            self.assertEqual(status["error"]["code"], "empty_playlist")

    def test_qa_unicode(self):
        result = self.parse("qa-nonascii/qa-unicode.m3u")
        channels = result["channels"]
        self.assertEqual(len(channels), 11)
        self.assertEqual([c["searchKey"] for c in channels], [
            "tele quebec quebec",
            "tvp lodz polska",
            "das erste \u2013 strasse deutschland",
            "\u043f\u0435\u0440\u0432\u044b\u0439 \u043a\u0430\u043d\u0430\u043b \u0440\u043e\u0441\u0441\u0438\u044f",
            "\u0627\u0644\u062c\u0632\u064a\u0631\u0629 \u0627\u0644\u0639\u0631\u0628\u064a\u0629",
            "nhk \u7dcf\u5408 \u65e5\u672c",
            "emoji \U0001f4fa channel fun",
            "cafe nfc normalisation",
            "cafe nfd normalisation",
            "ecole uppercase accent normalisation",
            "non ascii in url path normalisation",
        ])
        self.assertEqual([c["id"] for c in channels], ["t:" + c["tvgId"] for c in channels])
        self.assertEqual(channels[10]["url"], "http://stream.example.test/live/\u00e9t\u00e9.m3u8")
        self.assertEqual(result["warnings"], [])

    def test_qa_bom_crlf(self):
        result = self.parse("qa-nonascii/qa-bom-crlf.m3u")
        channels = result["channels"]
        self.assertEqual([c["name"] for c in channels], ["First CRLF Entry", "Second CRLF Entry", "Last Line Without Newline"])
        self.assertEqual([c["group"] for c in channels], ["CRLF", "Persisted", "Persisted"])
        for channel in channels:
            self.assertNotIn("\r", channel["url"])
            self.assertNotIn(" ", channel["url"])
        self.assertEqual(channels[1]["headers"], {"User-Agent": "CRLF/1.0"})
        self.assertEqual(result["warnings"], [])

    def test_generated_playlist_has_a_sane_group_count(self):
        # D-QA-03: 10 % multi-group entries must not create phantom groups.
        generator = FIXTURES.parent.parent / "scripts" / "gen-playlist.py"
        if not generator.is_file():
            self.skipTest("scripts/gen-playlist.py not present")
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "gen.m3u")
            import subprocess
            import sys
            subprocess.run([sys.executable, str(generator), "--channels", "2000", "--groups", "50", "--seed", "1", "--out", source],
                           check=True, capture_output=True, timeout=60)
            code, status = run_main("playlist", "--url", source, "--cache-dir", tmp)
            self.assertEqual(code, 0)
            self.assertEqual(status["channelCount"], 2000)
            self.assertEqual(status["groupCount"], 50)


if __name__ == "__main__":
    unittest.main()
