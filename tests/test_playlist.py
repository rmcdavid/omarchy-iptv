"""M3U parser tests for bin/omarchy-iptv. Run: python3 -m unittest discover -s tests"""
import pathlib
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


if __name__ == "__main__":
    unittest.main()
