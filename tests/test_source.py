"""Source history tests for bin/omarchy-iptv (M2-01 Sources, Lane 2).

Covers the Python mirror of Model.validateSourceUrl / sanitizeInput /
sourceKey / deriveLabel, state.json version 2 (migration from v1, record
validation, URL redaction on stdout) and the `state source` verbs.

The shared vectors live in tests/fixtures/source-urls.json (authored by
Lane 1, ARCHITECTURE-SOURCES.md 8.2 item 4). Until that file lands the
inline VECTORS below (the architecture's section 3.1 list with the codes of
UX-SOURCES.md 5.4, SR6) pin the behaviour; when the fixture exists it runs
as well.

Run: python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest

from helper_loader import load_helper

helper = load_helper()
ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "source-urls.json"

# (input, ok, code-or-kind, url, host)
VECTORS = [
    (" HTTP://Provider.Example.TEST:80/get.php?username=u&password=p ", True, "http", "http://provider.example.test/get.php?username=u&password=p", "provider.example.test"),
    ("https://iptv-org.github.io:443/iptv/countries/us.m3u#x", True, "http", "https://iptv-org.github.io/iptv/countries/us.m3u", "iptv-org.github.io"),
    ("http://h.test", True, "http", "http://h.test/", "h.test"),
    ("http://u:p@h.test:8080/x?y=1", True, "http", "http://u:p@h.test:8080/x?y=1", "h.test"),
    ("http://[::1]:8080/list.m3u", True, "http", "http://[::1]:8080/list.m3u", "[::1]"),
    ("http://h.test:/x", True, "http", "http://h.test/x", "h.test"),
    ("http://h.test?a=1&B=2", True, "http", "http://h.test/?a=1&B=2", "h.test"),
    ("FILE:///srv/tv/local.m3u", True, "file", "/srv/tv/local.m3u", ""),
    ("file://host/srv/tv/a%20b.m3u", True, "file", "/srv/tv/a b.m3u", ""),
    ("/srv/tv/local.m3u\n", True, "file", "/srv/tv/local.m3u", ""),
    ("http://h.test/a\x00b", True, "http", "http://h.test/ab", "h.test"),
    ("", False, "empty", "", ""),
    ("   ", False, "empty", "", ""),
    ("\u00a0\t", False, "empty", "", ""),
    ("~/tv/list.m3u", False, "relative_path", "", ""),
    ("./list.m3u", False, "relative_path", "", ""),
    ("provider.test/list.m3u", False, "scheme", "", ""),
    ("ftp://h.test/x", False, "scheme", "", ""),
    ("javascript:alert(1)", False, "scheme", "", ""),
    ("data:text/plain,x", False, "scheme", "", ""),
    ("rtsp://h.test/x", False, "scheme", "", ""),
    ("http:///x", False, "invalid", "", ""),
    ("http://h .test/", False, "invalid", "", ""),
    ("http://:80/", False, "invalid", "", ""),
    ("http://h.test:abc/", False, "invalid", "", ""),
    ("http:h.test/x", False, "invalid", "", ""),
    ("file:relative.m3u", False, "invalid", "", ""),
    ("file:///%zz", False, "invalid", "", ""),
    ("/proc/self/environ", False, "unsafe_path", "", ""),
    ("file:///dev/zero", False, "unsafe_path", "", ""),
    ("/sys", False, "unsafe_path", "", ""),
    ("http://h.test/" + "a" * 2048, False, "too_long", "", ""),
]


def run(*args):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(args))
    lines = out.getvalue().strip().splitlines()
    return code, json.loads(lines[-1]) if lines else None, err.getvalue()


class SanitizeTest(unittest.TestCase):
    def test_strips_controls_trims_and_caps(self):
        self.assertEqual(helper.sanitize_input("\t  a\r\nb\x7f\x85c \u00a0", 10), "abc")
        self.assertEqual(helper.sanitize_input("x" * 20, 5), "xxxxx")
        self.assertEqual(helper.sanitize_input(None, 5), "")
        self.assertEqual(helper.sanitize_input(" \u00a0 ", 5), "")

    def test_cap_counts_utf16_units(self):
        # One astral character is two UTF-16 units, as in the QML engine.
        self.assertEqual(helper.utf16_length("a\U0001F4FA"), 3)
        self.assertEqual(helper.sanitize_input("a\U0001F4FAb", 2), "a")
        self.assertEqual(helper.sanitize_input("a\U0001F4FAb", 3), "a\U0001F4FA")

    def test_leading_bom_is_dropped_once(self):
        # SR15: one leading byte-order mark goes (a paste artefact); a BOM
        # that is not leading before the control strip stays, as in Model.js.
        self.assertEqual(helper.sanitize_input("\ufeffx", 5), "x")
        self.assertEqual(helper.sanitize_input("\ufeff\ufeffx", 5), "\ufeffx")
        self.assertEqual(helper.sanitize_input("\t\ufeffx", 5), "\ufeffx")


class ValidateSourceUrlTest(unittest.TestCase):
    def check(self, text, ok, code_or_kind, url, host, origin="form"):
        result = helper.validate_source_url(text, origin=origin)
        label = repr(text[:60]) + " origin=" + origin
        self.assertEqual(result["ok"], ok, label)
        if ok:
            self.assertEqual(result["code"], "ok", label)
            self.assertEqual(result["kind"], code_or_kind, label)
            self.assertEqual(result["url"], url, label)
            self.assertEqual(result["host"], host, label)
        else:
            self.assertEqual(result["code"], code_or_kind, label)
            self.assertEqual(result["url"], "", label)
            self.assertNotIn("://", result["message"], label)

    def test_inline_vectors(self):
        for text, ok, code_or_kind, url, host in VECTORS:
            self.check(text, ok, code_or_kind, url, host)

    def test_shared_fixture_when_present(self):
        if not FIXTURE.exists():
            self.skipTest("tests/fixtures/source-urls.json not authored yet (Lane 1)")
        cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertGreater(len(cases), 0)
        origins = set()
        for case in cases:
            # SR11: the fixture pins both contexts through its `origin` field.
            origin = case.get("origin", "form")
            origins.add(origin)
            if case["ok"]:
                self.check(case["input"], True, case["kind"], case["url"], case.get("host", ""), origin)
                if "key" in case:
                    self.assertEqual(helper.source_cache_key(case["url"]), case["key"], repr(case["input"][:60]))
            else:
                self.check(case["input"], False, case["code"], "", "", origin)
        self.assertEqual(origins, {"form", "cli"})

    def test_tilde_depends_on_origin(self):
        # SR11: the CLI path keeps accepting ~ (verbatim; the reader expands
        # it), the forms refuse it.
        self.assertEqual(helper.validate_source_url("~/tv/list.m3u")["code"], "relative_path")
        self.assertEqual(helper.validate_source_url("~/tv/list.m3u", origin="form")["code"], "relative_path")
        for text in ("~/tv/list.m3u", "~"):
            result = helper.validate_source_url(text, origin="cli")
            self.assertEqual((result["ok"], result["kind"], result["url"], result["host"]), (True, "file", text, ""), text)
        self.assertEqual(helper.validate_source_url("./x.m3u", origin="cli")["code"], "relative_path")

    def test_scheme_versus_relative_path_heuristic(self):
        # SR12: leading // and host-like text (a . or : before any /) are
        # `scheme`; anything else without a scheme is `relative_path`.
        for text, code in (("//h.test/list.m3u", "scheme"), ("provider.test/list.m3u", "scheme"), ("localhost:8080/list.m3u", "scheme"),
                           ("list.m3u/", "scheme"), ("list.m3u", "scheme"), ("C:\\tv\\list.m3u", "scheme"),
                           ("playlist", "relative_path"), ("Videos/list.m3u", "relative_path"), (".", "relative_path"),
                           ("..", "relative_path"), ("./list.m3u", "relative_path"), ("../tv/list.m3u", "relative_path")):
            self.assertEqual(helper.validate_source_url(text)["code"], code, text)

    def test_line_separator_inside_a_url_is_invalid_not_scheme(self):
        # D-SRC-06: U+2028 / U+2029 after `http://` are whitespace for the
        # validator (parity with Model.js [\s\S]* + the \s rule), so the
        # message is `invalid`, never "Start with http://...".
        for sep in (" ", " "):
            result = helper.validate_source_url("http://h.test/a%sb" % sep)
            self.assertEqual(result["code"], "invalid", repr(sep))
            self.assertEqual(helper.validate_source_url("http://h.test/a%sb" % sep, origin="cli")["code"], "invalid", repr(sep))
        self.assertEqual(helper.validate_source_url("http://h.test/a b")["url"], "")

    def test_authority_parity_rules(self):
        # SR15: the checks QA listed, mirrored from Model.validateSourceUrl.
        for text in ("http://h.test:65536/x", "http://[1.2.3.4]/x", "http://[zz::1]/x", "http://[::1]x/", "http://[::1/x",
                     "http://h\u200b.test/x", "http://h.test\u2060:8080/x", "http://h.test\ufeff/x", "http://h\\.test/x",
                     "http://a:b:c/x", "http://h.test:\u0661\u0662/x", "http://h.test/x\u2028y", "http://h.test/x\u00a0y"):
            self.assertFalse(helper.validate_source_url(text)["ok"], repr(text))
        self.assertEqual(helper.validate_source_url("http://h.test:0080/x")["url"], "http://h.test/x")
        self.assertEqual(helper.validate_source_url("https://h.test:08080/x")["url"], "https://h.test:8080/x")
        self.assertEqual(helper.validate_source_url("http://h.test:65535/x")["url"], "http://h.test:65535/x")
        self.assertEqual(helper.validate_source_url("http://h.test:0/x")["url"], "http://h.test:0/x")
        self.assertEqual(helper.validate_source_url("http://[::1%25eth0]/x")["host"], "[::1%25eth0]")
        self.assertEqual(helper.validate_source_url("http://[2001:DB8::1]/x")["url"], "http://[2001:db8::1]/x")
        self.assertEqual(helper.validate_source_url("\ufeffhttp://h.test/x")["url"], "http://h.test/x")
        self.assertEqual(helper.validate_source_url("file:///srv/tv/a.m3u?x=1#f")["url"], "/srv/tv/a.m3u")

    def test_query_is_kept_verbatim_and_fragment_dropped(self):
        result = helper.validate_source_url("HTTPS://H.Test/get.php?Token=AbC%2f&x#frag")
        self.assertEqual(result["url"], "https://h.test/get.php?Token=AbC%2f&x")

    def test_messages_never_echo_the_input(self):
        secret = "http://user:secretpw@h .test/get.php?password=p"
        result = helper.validate_source_url(secret)
        self.assertFalse(result["ok"])
        self.assertNotIn("secretpw", json.dumps(result))
        self.assertNotIn("password", json.dumps(result))


class ResolveSourceTest(unittest.TestCase):
    """resolve_source now runs validate_source_url (D11) and keeps the 0.1
    runtime codes for its refusals."""

    def test_normalizes_http_and_keeps_paths(self):
        self.assertEqual(helper.resolve_source("HTTP://H.Test:80/list.m3u#x"), ("http", "http://h.test/list.m3u"))
        self.assertEqual(helper.resolve_source("/srv/tv/list.m3u"), ("file", "/srv/tv/list.m3u"))
        self.assertEqual(helper.resolve_source("file:///srv/tv/a%20b.m3u"), ("file", "/srv/tv/a b.m3u"))

    def test_tilde_is_still_expanded_for_the_command_line(self):
        kind, path = helper.resolve_source("~/tv/list.m3u")
        self.assertEqual(kind, "file")
        self.assertEqual(path, os.path.join(os.path.expanduser("~"), "tv", "list.m3u"))

    def test_caps_and_control_characters(self):
        with self.assertRaises(helper.HelperError) as caught:
            helper.resolve_source("http://h.test/" + "a" * 2048)
        self.assertEqual(caught.exception.code, "too_long")
        self.assertNotIn("aaaa", caught.exception.message)
        self.assertEqual(helper.resolve_source("http://h.test/a\x00b\n"), ("http", "http://h.test/ab"))

    def test_code_mapping(self):
        # SR12: `provider.test/x` reads as a host without a scheme, `relative/x.m3u` as a relative path.
        for value, code in (("", "no_source"), ("ftp://h.test/x", "unsupported_scheme"), ("provider.test/x.m3u", "unsupported_scheme"),
                            ("relative/x.m3u", "bad_url"), ("http://:80/", "bad_url"), ("./x.m3u", "bad_url"), ("/proc/self/environ", "unsafe_path")):
            with self.assertRaises(helper.HelperError) as caught:
                helper.resolve_source(value)
            self.assertEqual(caught.exception.code, code, value)

    def test_playlist_command_refuses_too_long_without_echo(self):
        with tempfile.TemporaryDirectory() as tmp:
            url = "http://h.test/" + "z" * 2048
            code, status, stderr = run("playlist", "--url", url, "--cache-dir", tmp)
            self.assertEqual(code, 1)
            self.assertEqual(status["error"]["code"], "too_long")
            self.assertNotIn("zzzz", json.dumps(status) + stderr)


class KeysAndLabelsTest(unittest.TestCase):
    def test_source_key_vectors(self):
        self.assertEqual(helper.source_cache_key("https://iptv-org.github.io/iptv/countries/us.m3u"), "d5977d8a")
        self.assertEqual(helper.source_cache_key("http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts"), "d990c2e4")
        self.assertEqual(helper.source_cache_key("http://provider.example.test:8080/get.php?username=u&password=p&type=m3u_plus&output=ts"), "85ac744a")
        self.assertEqual(helper.source_cache_key("/srv/tv/local.m3u"), "b0eed9fb")

    def test_allocate_key_suffixes_on_collision_and_reuses_known_urls(self):
        url = "/srv/tv/local.m3u"
        other = {"key": "b0eed9fb", "url": "http://other.test/x"}
        self.assertEqual(helper.allocate_source_key([], url), "b0eed9fb")
        self.assertEqual(helper.allocate_source_key([other], url), "b0eed9fb-2")
        self.assertEqual(helper.allocate_source_key([other, {"key": "b0eed9fb-2", "url": "http://x.test/"}], url), "b0eed9fb-3")
        self.assertEqual(helper.allocate_source_key([other, {"key": "b0eed9fb-2", "url": url}], url), "b0eed9fb-2")

    def test_derive_label(self):
        self.assertEqual(helper.derive_label("http://www.tv.example.net/x.m3u", "http"), "tv.example.net")
        self.assertEqual(helper.derive_label("http://u:p@nas.local:9981/x", "http"), "nas.local:9981")
        self.assertEqual(helper.derive_label("http://192.168.1.10:9981/playlist", "http"), "192.168.1.10:9981")
        self.assertEqual(helper.derive_label("/srv/tv/channels.m3u", "file"), "channels.m3u")
        self.assertEqual(helper.derive_label("/", "file"), "local file")
        self.assertEqual(len(helper.derive_label("http://" + "h" * 100 + ".test/", "http")), helper.MAX_LABEL)

    def test_unique_label(self):
        self.assertEqual(helper.unique_label("tv.example.net", []), "tv.example.net")
        self.assertEqual(helper.unique_label("tv.example.net", ["TV.Example.NET"]), "tv.example.net 2")
        self.assertEqual(helper.unique_label("tv.example.net", ["tv.example.net", "tv.example.net 2"]), "tv.example.net 3")
        long = "x" * helper.MAX_LABEL
        self.assertEqual(len(helper.unique_label(long, [long])), helper.MAX_LABEL)
        self.assertEqual(helper.unique_label("", []), "source")

    def test_derive_label_normalizes_first(self):
        # SR19 / SR20 on un-normalized input: default port dropped, leading
        # zeros stripped, host lower-cased, www. removed; ~ from the CLI.
        self.assertEqual(helper.derive_label("HTTP://WWW.H.Test:0080/x", "http"), "h.test")
        self.assertEqual(helper.derive_label("https://h.test:08080/x", "http"), "h.test:8080")
        self.assertEqual(helper.derive_label("~/tv/list.m3u", "file"), "list.m3u")
        self.assertEqual(helper.derive_label("~", "file"), "~")

    def test_label_cap_counts_code_points(self):
        # SR22: 64 code points, whatever their UTF-16 width; over-cap typed
        # labels are refused, over-cap stored labels are cut on read.
        astral = "\U0001F4FA" * helper.MAX_LABEL
        self.assertEqual(helper.derive_label("/srv/tv/" + astral + "x.m3u", "file"), astral)
        self.assertEqual(helper.unique_label(astral, [astral]), astral[:helper.MAX_LABEL - 2] + " 2")
        self.assertEqual(helper.check_custom_label(astral, []), astral)
        with self.assertRaises(helper.HelperError) as caught:
            helper.check_custom_label(astral + "x", [])
        self.assertEqual(caught.exception.code, "label_too_long")
        with self.assertRaises(helper.HelperError) as taken:
            helper.check_custom_label("Provider", ["PROVIDER"])
        self.assertEqual(taken.exception.code, "label_taken")
        record = helper.normalize_source(dict(SOURCE, label=astral + "x"))
        self.assertEqual(record["label"], astral)

    def test_cli_tilde_record_survives_a_reload(self):
        # SR11: a record written for `omarchy bar set ... ~/list.m3u` keeps
        # its verbatim path through the helper's own state rewrites.
        record = helper.normalize_source(dict(SOURCE, key="dc327328", url="~/tv/list.m3u", kind="file", epgUrl="~/tv/guide.xml"))
        self.assertEqual((record["url"], record["kind"], record["epgUrl"]), ("~/tv/list.m3u", "file", "~/tv/guide.xml"))
        self.assertEqual(helper.public_source(record)["host"], "local file")


SOURCE = {
    "key": "d5977d8a", "url": "https://iptv-org.github.io/iptv/countries/us.m3u", "epgUrl": "", "kind": "http",
    "label": "iptv-org.github.io", "labelCustom": False, "origin": "migrated",
    "addedAt": 1757700000, "lastUsed": 1757790000, "fetchedAt": 1757789500, "channelCount": 1475, "groupCount": 28,
}
XTREAM = {
    "key": "d990c2e4", "url": "http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts",
    "epgUrl": "http://provider.example.test/xmltv.php?username=u&password=p", "kind": "http",
    "label": "Provider", "labelCustom": True, "origin": "xtream",
    "addedAt": 1757750000, "lastUsed": 1757750000, "fetchedAt": 1757750004, "channelCount": 10234, "groupCount": 88,
}


class StateV2Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = os.path.join(self.tmp.name, "state")
        self.path = pathlib.Path(self.dir) / "state.json"

    def write(self, payload):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def state(self, *args):
        return run("state", "--state-dir", self.dir, *args)

    def test_v1_file_migrates_to_v2_keeping_favorites_and_recents(self):
        self.write({"version": 1, "favorites": ["t:bbc1.uk", "u:3f2a9c11"],
                    "recents": [{"id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000}],
                    "lastPlayed": {"id": "t:bbc1.uk", "name": "BBC One HD", "at": 1757700000}})
        code, payload, _ = self.state("show")
        self.assertEqual(code, 0)
        self.assertEqual(payload["state"]["version"], 2)
        self.assertEqual(payload["state"]["cacheLayout"], 0)
        self.assertEqual(payload["state"]["sources"], [])
        self.assertEqual(payload["state"]["favorites"], ["t:bbc1.uk", "u:3f2a9c11"])
        self.assertEqual(payload["state"]["recents"][0]["name"], "BBC One HD")
        # show never rewrites; favorite add writes v2 with everything carried.
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["version"], 1)
        code, payload, _ = self.state("favorite", "add", "t:new")
        written = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(written["version"], 2)
        self.assertEqual(written["favorites"], ["t:bbc1.uk", "u:3f2a9c11", "t:new"])
        self.assertEqual(written["recents"][0]["id"], "t:bbc1.uk")
        self.assertEqual(written["sources"], [])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_favorite_and_clear_recents_carry_sources_and_cache_layout(self):
        self.write({"version": 2, "cacheLayout": 2, "favorites": [], "recents": [{"id": "t:a", "name": "A", "at": 1}],
                    "lastPlayed": None, "sources": [SOURCE, XTREAM]})
        code, _, _ = self.state("favorite", "add", "t:x")
        self.assertEqual(code, 0)
        code, _, _ = self.state("clear-recents")
        self.assertEqual(code, 0)
        written = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(written["cacheLayout"], 2)
        self.assertEqual(written["favorites"], ["t:x"])
        self.assertEqual(written["recents"], [])
        self.assertEqual(written["sources"], [SOURCE, XTREAM])   # URLs intact on disk

    def test_show_output_is_redacted(self):
        self.write({"version": 2, "cacheLayout": 2, "favorites": [], "recents": [], "lastPlayed": None, "sources": [SOURCE, XTREAM,
                    dict(SOURCE, key="b0eed9fb", url="/srv/tv/local.m3u", kind="file", label="local.m3u", epgUrl="/srv/tv/guide.xml")]})
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = helper.main(["state", "--state-dir", self.dir, "show"])
        self.assertEqual(code, 0)
        text = out.getvalue() + err.getvalue()
        self.assertNotIn("://", text)
        self.assertNotIn("password", text)
        self.assertNotIn("get.php", text)
        self.assertNotIn("/srv/tv", text)
        payload = json.loads(out.getvalue())
        sources = payload["state"]["sources"]
        self.assertEqual([s.get("url") for s in sources], [None, None, None])
        self.assertEqual([s.get("epgUrl") for s in sources], [None, None, None])
        self.assertEqual(sources[0]["host"], "iptv-org.github.io")
        self.assertEqual(sources[0]["epgHost"], "")
        self.assertEqual(sources[1]["host"], "provider.example.test")
        self.assertEqual(sources[1]["epgHost"], "provider.example.test")
        self.assertEqual(sources[1]["label"], "Provider")
        self.assertEqual(sources[1]["channelCount"], 10234)
        self.assertEqual(sources[2]["host"], "local file")
        self.assertEqual(sources[2]["epgHost"], "local file")

    def test_invalid_records_are_dropped_and_duplicates_keep_the_first(self):
        self.write({"version": 2, "cacheLayout": 5, "favorites": [], "recents": [], "lastPlayed": None, "sources": [
            SOURCE,
            dict(SOURCE, key="../etc"),                              # bad key
            dict(SOURCE, key="0badc0de", url="ftp://h.test/x"),      # bad url
            dict(SOURCE, key="0badc0de"),                            # duplicate url
            dict(SOURCE, key="d5977d8a", url="http://dup.test/"),    # duplicate key
            dict(XTREAM, label="", origin="weird", channelCount="12", fetchedAt=-4, labelCustom="yes", epgUrl="not a url"),
            "junk", None,
        ]})
        code, payload, _ = self.state("show")
        self.assertEqual(code, 0)
        state = payload["state"]
        self.assertEqual(state["cacheLayout"], 0)
        self.assertEqual([s["key"] for s in state["sources"]], ["d5977d8a", "d990c2e4"])
        repaired = state["sources"][1]
        self.assertEqual(repaired["label"], "provider.example.test")
        self.assertEqual(repaired["origin"], "guide")
        self.assertEqual(repaired["channelCount"], 12)
        self.assertEqual(repaired["fetchedAt"], 0)
        self.assertFalse(repaired["labelCustom"])
        self.assertEqual(repaired["epgHost"], "")

    def test_init_creates_a_v2_file(self):
        code, payload, _ = self.state("init")
        self.assertEqual(code, 0)
        self.assertTrue(payload["created"])
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), helper.default_state())
        self.assertEqual(helper.default_state()["version"], 2)

    def test_normalize_state_caps_the_history(self):
        sources = [dict(SOURCE, key="%08x" % n, url="http://h%d.test/" % n) for n in range(60)]
        state = helper.normalize_state({"version": 2, "sources": sources})
        self.assertEqual(len(state["sources"]), helper.MAX_SOURCES)

    def test_control_characters_in_urls_drop_or_clear_with_a_redacted_log_line(self):
        # D-SRC-09 (SRC-SEC-21): a NUL inside `url` drops the record (the
        # validator would strip it and keep a record whose key no longer
        # matches), one inside `epgUrl` clears that field; stderr names the
        # key only, never the URL.
        self.write({"version": 2, "cacheLayout": 2, "favorites": [], "recents": [], "lastPlayed": None, "sources": [
            dict(SOURCE, key="deadbeef", url="http://127.0.0.1:9/c\x00d.m3u"),
            dict(SOURCE, key="deadbee1", url="/srv/tv/a\rb.m3u"),
            dict(SOURCE, key="deadbee2", url="http://h.test/ok.m3u", epgUrl="http://e.test/\x00x.xml"),
            SOURCE,
        ]})
        code, payload, stderr = self.state("show")
        self.assertEqual(code, 0)
        self.assertEqual([s["key"] for s in payload["state"]["sources"]], ["deadbee2", "d5977d8a"])
        self.assertEqual(payload["state"]["sources"][0]["epgHost"], "")
        self.assertIn("dropped source deadbeef (control characters in url)", stderr)
        self.assertIn("dropped source deadbee1 (control characters in url)", stderr)
        self.assertIn("cleared the epgUrl of source deadbee2", stderr)
        for needle in ("127.0.0.1:9", "d.m3u", "e.test", "/srv/tv", "\x00"):
            self.assertNotIn(needle, stderr)
        self.assertNotIn("\x00", json.dumps(payload))
        # Pure function, same verdict without the CLI (its log line captured).
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            state = helper.normalize_state({"version": 2, "sources": [dict(SOURCE, key="deadbeef", url="http://h.test/a\x00b")]})
        self.assertEqual(state["sources"], [])
        self.assertIn("dropped source deadbeef", err.getvalue())
        self.assertNotIn("h.test", err.getvalue())


class StateSourceCommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = os.path.join(self.tmp.name, "state")
        self.path = pathlib.Path(self.dir) / "state.json"

    def source(self, *args):
        return run("state", "--state-dir", self.dir, "source", *args)

    def disk(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_add_list_update_remove_round_trip(self):
        code, payload, err = self.source("add", "--url", " HTTP://Provider.Example.TEST:80/get.php?username=u&password=p ", "--now", "100")
        self.assertEqual(code, 0, err)
        self.assertEqual(payload["op"], "add")
        self.assertEqual(payload["key"], helper.source_cache_key("http://provider.example.test/get.php?username=u&password=p"))
        record = self.disk()["sources"][0]
        self.assertEqual(record["url"], "http://provider.example.test/get.php?username=u&password=p")
        self.assertEqual(record["label"], "provider.example.test")
        self.assertEqual(record["origin"], "cli")
        self.assertEqual((record["addedAt"], record["lastUsed"], record["fetchedAt"]), (100, 100, 0))
        self.assertFalse(record["labelCustom"])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        # stdout is redacted
        self.assertNotIn("password", json.dumps(payload) + err)
        self.assertEqual(payload["state"]["sources"][0]["host"], "provider.example.test")

        code, payload, _ = self.source("add", "--url", "/srv/tv/local.m3u", "--epg-url", "file:///srv/tv/guide.xml", "--label", "  NAS  ", "--origin", "guide")
        self.assertEqual(code, 0)
        second = self.disk()["sources"][1]
        self.assertEqual((second["kind"], second["label"], second["labelCustom"], second["origin"]), ("file", "NAS", True, "guide"))
        self.assertEqual(second["epgUrl"], "/srv/tv/guide.xml")

        code, payload, _ = self.source("list")
        self.assertEqual(code, 0)
        self.assertEqual([s["label"] for s in payload["state"]["sources"]], ["provider.example.test", "NAS"])
        self.assertNotIn("/srv/tv", json.dumps(payload))

        code, payload, _ = self.source("update", second["key"], "--label", "Home", "--epg-url", "")
        self.assertEqual(code, 0)
        self.assertEqual(payload["key"], second["key"])
        self.assertEqual(payload["replacedKey"], "")
        updated = self.disk()["sources"][1]
        self.assertEqual((updated["label"], updated["labelCustom"], updated["epgUrl"]), ("Home", True, ""))

        code, payload, _ = self.source("update", second["key"], "--label", "")
        self.assertEqual(self.disk()["sources"][1]["label"], "local.m3u")
        self.assertFalse(self.disk()["sources"][1]["labelCustom"])

        code, payload, _ = self.source("remove", second["key"])
        self.assertEqual(code, 0)
        self.assertEqual(payload["removed"], second["key"])
        self.assertEqual(len(self.disk()["sources"]), 1)

    def test_add_errors(self):
        for url, code in (("", "empty"), ("ftp://h.test/x", "scheme"), ("http://:80/", "invalid"), ("~/x.m3u", "relative_path"),
                          ("/proc/self/environ", "unsafe_path"), ("http://h.test/" + "a" * 2048, "too_long")):
            status, payload, _ = self.source("add", "--url", url)
            self.assertEqual(status, 1, url)
            self.assertEqual(payload["error"]["code"], code, url)
            self.assertEqual(payload["op"], "add")
        self.assertFalse(self.path.exists())
        status, payload, _ = self.source("add", "--url", "http://h.test/x", "--epg-url", "ftp://h.test/e")
        self.assertEqual(payload["error"]["code"], "scheme")
        self.assertEqual(payload["field"], "epgUrl")
        status, payload, _ = self.source("add", "--url", "http://h.test/x", "--label", "Mine")
        self.assertEqual(status, 0)
        status, payload, _ = self.source("add", "--url", "HTTP://H.TEST:80/x")
        self.assertEqual(payload["error"]["code"], "duplicate")
        self.assertEqual(payload["key"], helper.source_cache_key("http://h.test/x"))
        self.assertIn("Mine", payload["error"]["message"])
        status, payload, _ = self.source("add", "--url", "http://h2.test/x", "--label", "mine")
        self.assertEqual(payload["error"]["code"], "label_taken")
        status, payload, _ = self.source("add", "--url", "http://h2.test/x", "--label", "L" * 65)
        self.assertEqual(payload["error"]["code"], "label_too_long")
        status, payload, _ = self.source("add", "--url", "http://h2.test/x", "--label", "\u00a0\t")   # whitespace only = derived
        self.assertEqual(status, 0)
        self.assertEqual(self.disk()["sources"][1]["label"], "h2.test")

    def test_derived_labels_are_unique(self):
        self.source("add", "--url", "http://tv.example.net/a.m3u")
        self.source("add", "--url", "http://tv.example.net/b.m3u")
        self.source("add", "--url", "http://www.tv.example.net/c.m3u")
        self.assertEqual([s["label"] for s in self.disk()["sources"]], ["tv.example.net", "tv.example.net 2", "tv.example.net 3"])

    def test_cap_at_fifty(self):
        for n in range(helper.MAX_SOURCES):
            status, _, _ = self.source("add", "--url", "http://h%d.test/" % n)
            self.assertEqual(status, 0)
        status, payload, _ = self.source("add", "--url", "http://overflow.test/")
        self.assertEqual(status, 1)
        self.assertEqual(payload["error"]["code"], "too_many")
        self.assertEqual(len(self.disk()["sources"]), helper.MAX_SOURCES)

    def test_update_url_rekeys_and_resets_counts(self):
        self.source("add", "--url", "http://a.test/list.m3u", "--now", "5")
        key = self.disk()["sources"][0]["key"]
        self.source("add", "--url", "http://b.test/list.m3u")
        status, payload, _ = self.source("update", key, "--url", "http://b.test/list.m3u")
        self.assertEqual(payload["error"]["code"], "duplicate")
        status, payload, _ = self.source("update", key, "--url", "http://c.test/list.m3u")
        self.assertEqual(status, 0)
        self.assertEqual(payload["replacedKey"], key)
        self.assertEqual(payload["key"], helper.source_cache_key("http://c.test/list.m3u"))
        record = self.disk()["sources"][0]
        self.assertEqual(record["label"], "c.test")            # derived label follows the host
        self.assertEqual((record["fetchedAt"], record["channelCount"], record["addedAt"]), (0, 0, 5))
        status, payload, _ = self.source("update", "0badc0de", "--label", "x")
        self.assertEqual(payload["error"]["code"], "unknown_source")
        status, payload, _ = self.source("update", "../x", "--label", "x")
        self.assertEqual(payload["error"]["code"], "bad_key")
        status, payload, _ = self.source("remove", "0badc0de")
        self.assertEqual(payload["error"]["code"], "unknown_source")

    def test_stdout_never_carries_the_url(self):
        secret = "http://user:secretpw@h.test/get.php?username=u&password=p&type=m3u_plus"
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            helper.main(["state", "--state-dir", self.dir, "source", "add", "--url", secret, "--epg-url", secret])
            helper.main(["state", "--state-dir", self.dir, "source", "add", "--url", secret])   # duplicate error path
            helper.main(["state", "--state-dir", self.dir, "source", "list"])
        text = out.getvalue() + err.getvalue()
        for needle in ("secretpw", "password=p", "get.php", "://"):
            self.assertNotIn(needle, text)
        self.assertIn("h.test", text)
        self.assertIn("secretpw", self.path.read_text(encoding="utf-8"))   # the file is the 0600 store


if __name__ == "__main__":
    unittest.main()
