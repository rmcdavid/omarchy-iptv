"""D-M3U-1: the playlist parser's per-channel bounds, and the fetch verbs'
memory limit.

The marketplace maintainer on omacom/omarchy-plugin-marketplace#11935,
against 0.14.2 (85206f2): `#EXTGRP` persists until the next one, and the
parser copied its value into the `group`, `groups` and `searchKey` of every
entry after it, with no bound on its length -- so a few-MiB playlist asked
for gigabytes of strings under the 64 MiB input cap, and nothing bounded the
helper's memory, only its time. Every case here was run against the helper
at 85206f2 and seen red there (the counts are in the lane's write-up); the
inputs are deliberately ORDINARY AND SMALL. A cap is proved by what each
channel comes out as, never by building the payload the maintainer
described, and the memory limit by its refusing an ordinary input when it is
set very low, never by exhausting anything.

The memory cases run the helper as a SUBPROCESS, the way the service does:
the limit is a property of the process, and a helper loaded as a module
sets none (limit_memory), so an in-process call could not observe it.

Run: python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from helper_loader import load_helper          # redirects HOME and $XDG_* first
from test_helper import LocalHttp

helper = load_helper()
ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER = ROOT / "bin" / "omarchy-iptv"
FIXTURES = ROOT / "tests" / "fixtures"
HARNESS_FIXTURES = ROOT / "scripts" / "dev-harness" / "fixtures"
LIMIT_ENV = "OMARCHY_IPTV_MEMORY_LIMIT_MB"
SECRET = "SYNTH3TIC"

# A few KB: long enough to cross every cap, three orders of magnitude short
# of anything that costs memory to build.
LONG = 4096


def entries(count, start=0, extra=""):
    return "".join("#EXTINF:-1%s,Channel %d\nhttp://x.test/%d\n" % (extra, i, i)
                   for i in range(start, start + count))


def parse(text):
    return helper.parse_m3u(text)


class ExtgrpBoundTest(unittest.TestCase):
    """The finding itself: one long #EXTGRP, then several short entries."""

    def test_long_extgrp_is_cut_and_bounds_every_following_entry(self):
        group = "".join("Group%04d " % i for i in range(LONG // 10))      # ~4 KB, words
        result = parse("#EXTM3U\n#EXTGRP:%s\n%s" % (group, entries(6)))
        channels = result["channels"]
        self.assertEqual(len(channels), 6)
        for channel in channels:
            # The bound in absolute terms first, so the check reads the same
            # against a helper that has no constants to name.
            self.assertLessEqual(len(channel["group"]), 128)
            self.assertLessEqual(len(channel["searchKey"]), 700)
            self.assertLessEqual(len(channel["group"]), helper.M3U_MAX_GROUP)
            self.assertLessEqual(len(channel["searchKey"]),
                                 helper.M3U_MAX_NAME + 1 + helper.M3U_MAX_GROUP_TEXT)
            # A prefix of what the provider wrote, nothing appended.
            self.assertTrue(group.startswith(channel["group"]))
            self.assertNotIn("groups", channel)
        # Cut ONCE, at its own line, and said once.
        self.assertIn("1 group value cut to %d characters" % helper.M3U_MAX_GROUP_TEXT, result["warnings"])

    def test_extgrp_still_persists_until_the_next_one(self):
        # The semantics are kept: the tag opens a group for what follows.
        text = "#EXTM3U\n#EXTGRP:News\n%s#EXTGRP:Sport\n%s" % (entries(2), entries(2, 2))
        groups = [channel["group"] for channel in parse(text)["channels"]]
        self.assertEqual(groups, ["News", "News", "Sport", "Sport"])

    def test_a_short_extgrp_is_untouched(self):
        result = parse("#EXTM3U\n#EXTGRP:Sports;HD\n%s" % entries(2))
        self.assertEqual(result["channels"][1]["groups"], ["Sports", "HD"])
        self.assertEqual(result["warnings"], [])


class GroupTitleBoundTest(unittest.TestCase):
    def test_long_group_title_is_cut(self):
        title = "G" * LONG
        result = parse('#EXTM3U\n%s' % entries(3, extra=' group-title="%s"' % title))
        for channel in result["channels"]:
            self.assertLessEqual(len(channel["group"]), 128)
            self.assertLessEqual(len(channel["searchKey"]), 700)
            self.assertEqual(channel["group"], "G" * helper.M3U_MAX_GROUP)
        self.assertIn("3 group values cut to %d characters" % helper.M3U_MAX_GROUP_TEXT, result["warnings"])

    def test_many_short_groups_keep_the_first_sixteen(self):
        title = ";".join("g%d" % i for i in range(60))                 # 60 groups, 239 characters
        channel = parse('#EXTM3U\n%s' % entries(1, extra=' group-title="%s"' % title))["channels"][0]
        self.assertLessEqual(len(channel["groups"]), 16)
        self.assertEqual(channel["groups"], ["g%d" % i for i in range(helper.M3U_MAX_GROUPS_PER_CHANNEL)])
        self.assertEqual(channel["group"], "g0")


class NameBoundTest(unittest.TestCase):
    def test_long_name_is_cut(self):
        name = "Name " * (LONG // 5)
        result = parse("#EXTM3U\n#EXTINF:-1,%s\nhttp://x.test/a\n" % name)
        channel = result["channels"][0]
        self.assertLessEqual(len(channel["name"]), 512)
        self.assertLessEqual(len(channel["nameKey"]), 512)
        self.assertLessEqual(len(channel["searchKey"]), 600)
        self.assertEqual(channel["name"], name[:helper.M3U_MAX_NAME].rstrip())
        self.assertIn("1 channel name cut to %d characters" % helper.M3U_MAX_NAME, result["warnings"])

    def test_long_tvg_name_is_cut(self):
        channel = parse('#EXTM3U\n#EXTINF:-1 tvg-name="%s",Short\nhttp://x.test/a\n' % ("T" * LONG))["channels"][0]
        self.assertLessEqual(len(channel["tvgName"]), 512)

    def test_long_tvg_id_is_dropped_not_cut(self):
        # An identifier cut short is a different identifier: an EPG key that
        # matches the wrong guide channel. Dropped, the row keys by its name.
        channel = parse('#EXTM3U\n#EXTINF:-1 tvg-id="%s",Short\nhttp://x.test/a\n' % ("i" * LONG))["channels"][0]
        self.assertNotIn("tvgId", channel)
        self.assertLessEqual(len(channel["id"]), 64)


class OptionBoundTest(unittest.TestCase):
    def test_long_extvlcopt_is_dropped_and_does_not_persist(self):
        # The persistence half has held since the parser's first version; it
        # is pinned here beside the length half, which is the new bound.
        text = ("#EXTM3U\n#EXTINF:-1,First\n#EXTVLCOPT:http-user-agent=%s\n"
                "#EXTVLCOPT:http-referrer=http://ref.test/\nhttp://x.test/0\n%s") % ("U" * LONG, entries(4, 1))
        result = parse(text)
        first = result["channels"][0]
        self.assertNotIn("User-Agent", first.get("headers", {}))
        self.assertLessEqual(len(json.dumps(first)), 2000)
        self.assertEqual(first["headers"], {"Referer": "http://ref.test/"})   # the ordinary one stays
        for channel in result["channels"][1:]:
            self.assertNotIn("headers", channel)
            self.assertNotIn("options", channel)
        self.assertTrue(any(w.startswith("1 option or header dropped") for w in result["warnings"]), result["warnings"])

    def test_long_kodiprop_header_value_is_dropped(self):
        text = ("#EXTM3U\n#EXTINF:-1,A\n#KODIPROP:inputstream.adaptive.stream_headers=Cookie=%s&X-Ok=1\n"
                "http://x.test/a\n") % ("c" * LONG)
        channel = parse(text)["channels"][0]
        self.assertEqual(channel["headers"], {"X-Ok": "1"})

    def test_option_count_is_capped(self):
        options = "".join("#EXTVLCOPT:opt%d=v\n" % i for i in range(40))
        channel = parse("#EXTM3U\n#EXTINF:-1,A\n%shttp://x.test/a\n" % options)["channels"][0]
        self.assertLessEqual(len(channel["options"]), 16)
        self.assertEqual(len(channel["options"]), helper.M3U_MAX_OPTIONS)


class UrlFieldBoundTest(unittest.TestCase):
    def test_long_stream_url_skips_the_entry(self):
        long_url = "http://x.test/" + "p" * LONG
        result = parse("#EXTM3U\n#EXTINF:-1,Long\n%s\n%s" % (long_url, entries(1)))
        self.assertEqual([c["name"] for c in result["channels"]], ["Channel 0"])
        self.assertIn("1 entry skipped: stream URL longer than %d characters" % helper.M3U_MAX_URL, result["warnings"])

    def test_long_logo_and_channel_number_are_dropped(self):
        text = '#EXTM3U\n#EXTINF:-1 tvg-logo="https://l.test/%s" tvg-chno="%s",A\nhttp://x.test/a\n' % ("l" * LONG, "9" * 64)
        channel = parse(text)["channels"][0]
        self.assertNotIn("logo", channel)
        self.assertNotIn("chno", channel)

    def test_long_epg_hint_is_dropped(self):
        result = parse('#EXTM3U url-tvg="http://e.test/%s"\n%s' % ("e" * LONG, entries(1)))
        self.assertEqual(result["epgUrlHint"], "")
        ordinary = parse('#EXTM3U url-tvg="http://e.test/guide.xml"\n%s' % entries(1))
        self.assertEqual(ordinary["epgUrlHint"], "http://e.test/guide.xml")


class WarningBoundTest(unittest.TestCase):
    def test_per_channel_warnings_are_capped_with_a_count(self):
        # One per channel used to mean one per channel, up to 50,000, on the
        # single status line the service collects (lane A's OQ-6, D-CLIP-1).
        text = "#EXTM3U\n" + "".join("#EXTINF:-1,C%d\n#EXTVLCOPT:--bad=1\nhttp://x.test/%d\n" % (i, i) for i in range(60))
        warnings = parse(text)["warnings"]
        self.assertLessEqual(len(warnings), 25)
        listed = [w for w in warnings if w.startswith("dropped option-looking key")]
        self.assertEqual(len(listed), helper.M3U_MAX_CHANNEL_WARNINGS)
        self.assertIn("%d more warnings like the ones above not listed" % (60 - helper.M3U_MAX_CHANNEL_WARNINGS), warnings)


class ChannelBoundTest(unittest.TestCase):
    def test_every_field_long_at_once_is_bounded_by_a_constant(self):
        long = "z" * LONG
        options = "".join("#EXTVLCOPT:o%d=%s\n" % (i, "v" * 1000) for i in range(30))
        text = ('#EXTM3U\n#EXTGRP:%s\n#EXTINF:-1 tvg-id="%s" tvg-name="%s" group-title="%s" tvg-logo="https://l.test/%s" '
                'tvg-chno="%s",%s\n#EXTVLCOPT:http-user-agent=%s\n%shttp://x.test/a\n') % (
                    long, long, long, ";".join([long] * 20), long, long, long, long, options)
        channel = parse(text)["channels"][0]
        self.assertLess(len(json.dumps(channel)), 50000)
        # Every cap summed, with room for the JSON punctuation: the figure a
        # channel can never exceed, however long its input lines are.
        ceiling = (4 * helper.M3U_MAX_NAME + helper.M3U_MAX_GROUP + helper.M3U_MAX_GROUP_TEXT * 2
                   + helper.M3U_MAX_TVG_ID * 2 + helper.M3U_MAX_URL + helper.M3U_MAX_LOGO_URL + helper.M3U_MAX_CHNO
                   + 2 * helper.M3U_MAX_OPTIONS * (helper.M3U_MAX_OPTION_KEY + helper.M3U_MAX_OPTION_VALUE + 8) + 1024)
        self.assertLess(len(json.dumps(channel)), ceiling)


class FixturesUntouchedTest(unittest.TestCase):
    """The caps were chosen above every fixture; this keeps them there. A
    cap that fired on a fixture would change that fixture's output."""

    def test_no_cap_fires_on_any_playlist_fixture(self):
        cut = tuple(sentence.split("%d ", 1)[1] for entry in helper.M3U_CUT_WARNINGS for sentence in entry[1:])
        files = sorted(p for base in (FIXTURES, HARNESS_FIXTURES) for p in base.rglob("*") if p.is_file() and ".m3u" in p.name)
        self.assertGreaterEqual(len(files), 20)
        for path in files:
            warnings = parse(path.read_text(encoding="utf-8", errors="replace"))["warnings"]
            for warning in warnings:
                self.assertFalse(warning.split(" ", 1)[-1] in cut, "%s: %s" % (path.name, warning))


def run_helper(*args, limit=None, url=None, timeout=60):
    env = dict(os.environ)
    env.pop(LIMIT_ENV, None)
    env.pop("OMARCHY_IPTV_URL", None)
    if limit is not None:
        env[LIMIT_ENV] = str(limit)
    if url is not None:
        env["OMARCHY_IPTV_URL"] = url
    done = subprocess.run([sys.executable, str(HELPER), *args], capture_output=True, text=True, env=env, timeout=timeout)
    lines = done.stdout.strip().splitlines()
    return done.returncode, (json.loads(lines[-1]) if lines else None), done.stdout, done.stderr


class MemoryLimitTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = tmp.name

    def assert_refused(self, code, status, stdout, stderr, kind):
        self.assertEqual(code, 1, stdout + stderr)
        self.assertEqual(len(stdout.strip().splitlines()), 1, stdout)
        self.assertFalse(status["ok"])
        self.assertEqual(status["kind"], kind)
        self.assertEqual(status["error"]["code"], "too_large", status)
        self.assertIn("memory", status["error"]["message"])
        self.assertNotIn("Traceback", stderr)
        self.assertNotIn(SECRET, stdout + stderr)

    def test_very_low_limit_refuses_an_ordinary_playlist_in_one_sentence(self):
        server = LocalHttp()
        self.addCleanup(server.httpd.shutdown)
        url = server.url("/playlist", userinfo="user:" + SECRET)
        code, status, stdout, stderr = run_helper("playlist", "--cache-dir", self.cache, limit=8, url=url)
        self.assert_refused(code, status, stdout, stderr, "playlist")
        self.assertEqual(status["sourceHost"], "127.0.0.1")
        self.assertFalse(os.path.exists(os.path.join(self.cache, helper.CHANNELS_FILE)))
        on_disk = json.loads(pathlib.Path(self.cache, helper.PLAYLIST_STATUS_FILE).read_text(encoding="utf-8"))
        self.assertEqual(on_disk["error"]["code"], "too_large")

    def test_a_limit_below_the_parse_refuses_a_10000_channel_playlist(self):
        # Ordinary, not amplifying: 10,000 entries of the fixtures' shape,
        # about 0.9 MB, parsed under a 24 MiB data limit.
        path = pathlib.Path(self.cache, "ten-thousand.m3u")
        path.write_text("#EXTM3U\n" + entries(10000, extra=' tvg-id="c.test" group-title="News"'), encoding="utf-8")
        cache = os.path.join(self.cache, "c")
        code, status, stdout, stderr = run_helper("playlist", "--url", str(path), "--cache-dir", cache, limit=24)
        self.assert_refused(code, status, stdout, stderr, "playlist")
        # And the default admits it.
        code, status, stdout, stderr = run_helper("playlist", "--url", str(path), "--cache-dir", cache)
        self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(status["channelCount"], 10000)

    def test_very_low_limit_refuses_an_ordinary_epg(self):
        code, status, stdout, stderr = run_helper("epg", "--url", str(FIXTURES / "epg-basic.xml"),
                                                  "--cache-dir", self.cache, "--force", limit=8)
        self.assert_refused(code, status, stdout, stderr, "epg")
        self.assertFalse(os.path.exists(os.path.join(self.cache, helper.EPG_WINDOW_FILE)))

    def test_the_verb_holds_the_limit_while_it_parses_and_lifts_it_after(self):
        # Run as the program (runpy, run_name __main__). The limit is read
        # when the verb opens channels.json's temporary file -- the parse's
        # own output, written under it -- and again once the verb returned.
        # This case used to assert the limit was still SET after the verb;
        # D-M3U-3 lifts it on every way out (test_reply_bounds.py holds the
        # rule at each status write and each printed line).
        probe = ("import os, resource, runpy, sys\n"
                 "seen = []\n"
                 "def hook(event, args):\n"
                 "    if event == 'open' and isinstance(args[0], str) and os.path.basename(args[0]).startswith('.tmp-channels.json'):\n"
                 "        seen.append(resource.getrlimit(resource.RLIMIT_DATA)[0])\n"
                 "sys.addaudithook(hook)\n"
                 "before = resource.getrlimit(resource.RLIMIT_DATA)[0]\n"
                 "sys.argv = ['omarchy-iptv', 'playlist', '--url', sys.argv[1], '--cache-dir', sys.argv[2]]\n"
                 "try:\n    runpy.run_path(%r, run_name='__main__')\n"
                 "except SystemExit:\n    pass\n"
                 "after = resource.getrlimit(resource.RLIMIT_DATA)[0]\n"
                 "sys.stderr.write('HELD %%s LIFTED %%s\\n' %% (seen, after == before))\n") % str(HELPER)
        env = dict(os.environ)
        env.pop(LIMIT_ENV, None)
        done = subprocess.run([sys.executable, "-c", probe, str(FIXTURES / "basic.m3u"), self.cache],
                              capture_output=True, text=True, env=env, timeout=60)
        line = [l for l in done.stderr.splitlines() if l.startswith("HELD ")]
        self.assertEqual(line, ["HELD [%d] LIFTED True" % (512 * 1024 * 1024)], done.stderr)

    def test_the_variable_can_only_lower_the_limit(self):
        with mock.patch.dict(os.environ, {LIMIT_ENV: "100000"}):
            self.assertEqual(helper.memory_limit_bytes(), helper.MEMORY_LIMIT_MIB * 1024 * 1024)
        for value in ("nonsense", "1e400", "-5", "0", "12.5", ""):
            with mock.patch.dict(os.environ, {LIMIT_ENV: value}):
                self.assertEqual(helper.memory_limit_bytes(), helper.MEMORY_LIMIT_MIB * 1024 * 1024, value)
        with mock.patch.dict(os.environ, {LIMIT_ENV: "64"}):
            self.assertEqual(helper.memory_limit_bytes(), 64 * 1024 * 1024)

    def test_a_memory_error_in_the_parse_is_one_sentence(self):
        # In process, so the shipping path is called with the error placed
        # exactly where an over-limit parse raises it.
        for verb, target, args in (
                ("playlist", "parse_m3u", ["--url", str(FIXTURES / "basic.m3u")]),
                ("epg", "parse_xmltv", ["--url", str(FIXTURES / "epg-basic.xml"), "--force"])):
            cache = tempfile.mkdtemp(dir=self.cache)
            out, err = io.StringIO(), io.StringIO()
            with mock.patch.object(helper, target, side_effect=MemoryError()), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = helper.main([verb, "--cache-dir", cache] + args)
            status = json.loads(out.getvalue().strip().splitlines()[-1])
            self.assert_refused(code, status, out.getvalue(), err.getvalue(), verb)

    def test_a_local_source_does_not_reserve_the_input_cap(self):
        # read(MAX_SOURCE_BYTES + 1) allocated 64 MiB before reading a byte,
        # which was the floor of every run. Measured under an outside limit,
        # so the case reads the same against a helper with no limit of its own.
        import resource
        def cap():
            resource.setrlimit(resource.RLIMIT_AS, (75 << 20, 75 << 20))
        done = subprocess.run([sys.executable, str(HELPER), "playlist", "--url", str(FIXTURES / "basic.m3u"),
                               "--cache-dir", self.cache], capture_output=True, text=True, preexec_fn=cap, timeout=60)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


class PrebuiltTlsContextTest(unittest.TestCase):
    """limit_memory builds the TLS context before the limit (so OpenSSL is
    never refused an allocation as an SSLError) and the opener uses it. It
    must be urllib's own context: verifying, by hostname. Proved both ways:
    the object's settings, and a subprocess fetch from a self-signed server,
    which has to be refused exactly as urllib's default refuses it."""

    def test_the_context_verifies_certificates_and_names(self):
        import ssl
        helper.prepare_tls_context()
        self.addCleanup(helper.TLS_CONTEXT.clear)
        context = helper.TLS_CONTEXT["https"]
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertGreater(len(context.get_ca_certs()) + context.cert_store_stats()["x509_ca"], 0)

    @unittest.skipUnless(shutil.which("openssl"), "openssl is needed to make a certificate")
    def test_a_self_signed_server_is_refused_by_the_running_helper(self):
        import http.server
        import ssl
        import threading
        work = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, work, True)
        key, cert = os.path.join(work, "k.pem"), os.path.join(work, "c.pem")
        made = subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                               "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
                               "-keyout", key, "-out", cert], capture_output=True, timeout=60)
        self.assertEqual(made.returncode, 0, made.stderr)
        seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                seen.append(self.path)
                body = b"#EXTM3U\n#EXTINF:-1,A\nhttp://x.test/a\n"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        url = "https://u:%s@127.0.0.1:%d/list.m3u" % (SECRET, server.server_address[1])
        cache = os.path.join(work, "cache")
        code, status, stdout, stderr = run_helper("playlist", "--cache-dir", cache, url=url)
        self.assertEqual(code, 1, stdout + stderr)
        self.assertEqual(status["error"]["code"], "network")
        self.assertRegex(status["error"]["message"], "(?i)certificate")
        self.assertEqual(seen, [])                     # no request was ever sent
        self.assertNotIn(SECRET, stdout + stderr)


class LineByLineTest(unittest.TestCase):
    """The `playlist` verb parses playlist_lines(bytes), never one str of
    the whole document (D-M3U-1's measurement: a flag emoji widens a str to
    four bytes per character). The two must give the same result, invalid
    UTF-8, a BOM, CRLF and gzip included."""

    VECTORS = [
        b"\xef\xbb\xbf#EXTM3U\r\n#EXTINF:-1 group-title=\"A\",One\r\nhttp://x.test/1\r\n",
        b"#EXTM3U\n#EXTINF:-1,Bad \xe2\x82\n#EXTINF:-1,Cut \xf0\x9f\x87\nhttp://x.test/2\n",
        b"#EXTM3U\n#EXTINF:-1,\xf0\x9f\x87\xba\xf0\x9f\x87\xb8 Flag\nhttp://x.test/3\n\xff\xfe\n",
        b"#EXTINF:-1,No header\nhttp://x.test/4",
        b"",
    ]

    def test_lines_and_whole_text_parse_the_same(self):
        import gzip
        files = sorted(p for base in (FIXTURES, HARNESS_FIXTURES) for p in base.rglob("*") if p.is_file() and ".m3u" in p.name)
        cases = [p.read_bytes() for p in files] + self.VECTORS
        for data in cases + [gzip.compress(data, mtime=0) for data in self.VECTORS[:3]]:
            whole = helper.parse_m3u(helper.decode_text(data))
            lines = helper.parse_m3u(helper.playlist_lines(data))
            self.assertEqual(lines, whole, data[:60])

    def test_the_verb_parses_line_by_line(self):
        seen = []
        real = helper.parse_m3u

        def spy(text):
            seen.append(type(text).__name__)
            return real(text)
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as cache, mock.patch.object(helper, "parse_m3u", side_effect=spy), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(helper.main(["playlist", "--url", str(FIXTURES / "basic.m3u"), "--cache-dir", cache]), 0)
        self.assertEqual(seen, ["generator"])


if __name__ == "__main__":
    unittest.main()
