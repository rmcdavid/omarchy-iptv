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
        for bad in ("ftp://h.test/x.m3u", "relative/path.m3u", "javascript:alert(1)", ""):
            with self.assertRaises(helper.HelperError):
                helper.resolve_source(bad)

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
        self.assertEqual(names, ["only.id", "h.test", "Named"])
        for name in names:
            self.assertNotIn("secret", name)
            self.assertNotIn("pw", name)

    def test_duplicate_attribute_keys_last_non_empty_wins(self):
        attrs, title = helper.parse_extinf('#EXTINF:-1 tvg-id="" tvg-id="real" tvg-name="A" tvg-name="" tvg-logo="http://a" tvg-logo="http://b",X')
        self.assertEqual(attrs, {"tvg-id": "real", "tvg-name": "A", "tvg-logo": "http://b"})
        self.assertEqual(title, "X")

    def test_unquoted_values_and_mixed_case_keys(self):
        attrs, title = helper.parse_extinf("#EXTINF:-1 TVG-ID=abc.de Group-Title=Sports,Name")
        self.assertEqual(attrs, {"tvg-id": "abc.de", "group-title": "Sports"})
        self.assertEqual(title, "Name")

    def test_stray_lines_do_not_consume_the_pending_extinf(self):
        result = self.parse("#EXTM3U\n#EXTINF:-1,A\nNote: this is not a url\n   \n\t\nhttp://x.test/a\n")
        self.assertEqual([c["name"] for c in result["channels"]], ["A"])
        self.assertIn("1 stray lines ignored", result["warnings"])

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
        self.assertIn("3 entries skipped: unsupported URL scheme", result["warnings"])
        self.assertIn("1 stray lines ignored", result["warnings"])
        self.assertIn("1 #EXTINF entries without a URL skipped", result["warnings"])

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


if __name__ == "__main__":
    unittest.main()
