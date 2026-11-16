"""D-SINK-109: every line that names a source's host withholds it where the
Sources form does.

For a source whose host the form withholds -- R32a's typo shapes, a
password holding an unencoded `/`, `?` or `#` whose RFC host is the
username, and since D-SINK-99 any `@` after the authority -- the helper's
download failure sentences, both status files' `sourceHost` and the guide
window's meta named the username. The predicate is source_host_withheld,
shared with Model.sourceHostWithheld through one fixture; the printer is
shown_source_host. channels.json keeps the RFC host (cached_source reads it
at play time), and D-SINK-83's one-label rule judges the REAL host.

Nothing here is looked up. The servers are tests/scripted_server.py's on
127.0.0.1, a literal; the one dotless shape is refused at a stand-in for
the connection seam, with the resolver replaced by a refusal that records
every call, and the shapes the destination rules refuse are refused before
any lookup or answered by a stand-in that knows literals only.
"""
import contextlib
import errno
import io
import json
import os
import pathlib
import socket
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper          # redirects HOME and $XDG_* first
from scripted_server import ScriptedServer, response

helper = load_helper()

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "source-host-withheld.json").read_text(encoding="utf-8"))
SECRETS = ("qqqqqq", "zzzzzz")
WITHHELD = "[host withheld]"
PATH = "/zzzz@cdn.test/get.php"
PROXY_VARIABLES = ("http_proxy", "https_proxy", "all_proxy", "no_proxy",
                   "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
PLAYLIST = b"#EXTM3U\n#EXTINF:-1 tvg-id=\"a.tv\" group-title=\"News\",A\nhttp://s.example.test/a.ts\n"


def stamp(seconds):
    return time.strftime("%Y%m%d%H%M%S +0000", time.gmtime(seconds))


def guide_body():
    now = int(time.time())
    return ('<?xml version="1.0" encoding="UTF-8"?><tv><channel id="a.tv"><display-name>A</display-name></channel>'
            '<programme start="%s" stop="%s" channel="a.tv"><title>News</title></programme></tv>'
            % (stamp(now - 1800), stamp(now + 1800))).encode("ascii")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(argv))
    lines = [line for line in out.getvalue().splitlines() if line.strip()]
    return code, out.getvalue(), json.loads(lines[-1]) if lines else None, err.getvalue()


class LiteralsOnly:
    """socket.getaddrinfo replaced: a literal is answered with itself, any
    name is refused, and every call is recorded. Nothing reaches a
    resolver."""

    def __init__(self):
        self.lookups = []

    def getaddrinfo(self, host, port, family=0, type=0, proto=0, flags=0):
        text = host.decode("ascii", "replace") if isinstance(host, bytes) else str(host)
        self.lookups.append(text)
        if text == "127.0.0.1":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (text, int(port or 0)))]
        raise socket.gaierror(socket.EAI_NONAME, "refused by the test")

    def __enter__(self):
        self.patch = mock.patch.object(socket, "getaddrinfo", self.getaddrinfo)
        self.patch.start()
        return self

    def __exit__(self, *_):
        self.patch.stop()
        return False


class FixtureTest(unittest.TestCase):
    """The shared fixture, helper side; tests/Model.test.js answers the same
    file through Model.sourceHostWithheld."""

    def test_the_fixture_is_whole_and_ascii(self):
        raw = (ROOT / "tests" / "fixtures" / "source-host-withheld.json").read_bytes()
        self.assertTrue(all(b < 0x80 for b in raw))
        self.assertGreaterEqual(len(FIXTURE["vectors"]), 20)
        self.assertEqual({v["withheld"] for v in FIXTURE["vectors"]}, {True, False})

    def test_every_vector_is_withheld_as_the_fixture_says(self):
        got = [(v["url"], helper.source_host_withheld(v["url"])) for v in FIXTURE["vectors"]]
        self.assertEqual(got, [(v["url"], v["withheld"]) for v in FIXTURE["vectors"]])

    def test_each_arm_holds_where_the_fixture_says(self):
        def arms(url):
            return " ".join(name for name, held in (("rfc", helper.host_withheld(url)),
                                                    ("at", helper.at_after_authority(url))) if held)
        got = [(v["url"], arms(v["url"])) for v in FIXTURE["vectors"]]
        self.assertEqual(got, [(v["url"], v["arms"]) for v in FIXTURE["vectors"]])

    def test_the_printer_says_local_file_then_withheld_then_the_rfc_host(self):
        for v in FIXTURE["vectors"]:
            url = v["url"]
            with self.subTest(url=url):
                shown = helper.shown_source_host(url)
                if helper.source_host(url) == "local file":
                    self.assertEqual(shown, "local file")
                elif v["withheld"]:
                    self.assertEqual(shown, WITHHELD)
                else:
                    self.assertEqual(shown, helper.source_host(url))
                for secret in SECRETS:
                    if v["withheld"]:
                        self.assertNotIn(secret, shown)


class Fetches(unittest.TestCase):
    def setUp(self):
        clean = {name: value for name, value in os.environ.items() if name not in PROXY_VARIABLES}
        for name in (helper.ORIGIN_ENV, helper.HOME_HOST_ENV, helper.HOME_PORT_ENV):
            clean.pop(name, None)
        patcher = mock.patch.dict(os.environ, clean, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = tmp.name

    def serve(self, *steps):
        server = ScriptedServer({PATH: steps})
        self.addCleanup(server.close)
        return server.url(PATH)

    def written(self, name):
        path = pathlib.Path(self.cache) / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def status(self, name):
        return json.loads(self.written(name))

    def assert_nothing_private(self, *texts):
        for text in texts:
            for secret in SECRETS:
                self.assertNotIn(secret, text)


class FailureSentenceTest(Fetches):
    """The sentences a failed download composes from the host, and the
    statuses that carry it. On the commit before D-SINK-109 each said
    `127.0.0.1` (and the dotless shape `qqqqqq`)."""

    def check_failure(self, verb, status_file, url, code, message):
        rc, stdout, reply, stderr = run(verb, "--url", url, "--cache-dir", self.cache, "--timeout", "5")
        self.assertEqual(rc, 1, stderr)
        self.assertEqual((reply["error"]["code"], reply["error"]["message"], reply["sourceHost"]),
                         (code, message, WITHHELD))
        status = self.status(status_file)
        self.assertEqual((status["error"]["message"], status["sourceHost"]), (message, WITHHELD))
        self.assertIn(message, stderr)
        self.assertNotIn("127.0.0.1", stdout + stderr + self.written(status_file))
        self.assert_nothing_private(stdout, stderr, self.written(status_file))

    def test_an_http_failure_names_the_withheld_host_in_the_playlist_verb(self):
        url = self.serve(response("404 Not Found"))
        self.check_failure("playlist", helper.PLAYLIST_STATUS_FILE, url, "http_404", "HTTP 404 from " + WITHHELD)

    def test_an_http_failure_names_the_withheld_host_in_the_guide_verb(self):
        url = self.serve(response("404 Not Found"))
        self.check_failure("epg", helper.EPG_STATUS_FILE, url, "http_404", "HTTP 404 from " + WITHHELD)

    def test_a_body_that_is_not_a_playlist_names_the_withheld_host(self):
        url = self.serve(response("200 OK", (("Content-Type", "text/plain"),), b"hello\n"))
        self.check_failure("playlist", helper.PLAYLIST_STATUS_FILE, url, "not_a_playlist",
                           "source from %s is not an M3U playlist (no #EXTM3U or #EXTINF lines)" % WITHHELD)

    def test_a_playlist_with_no_channel_names_the_withheld_host(self):
        url = self.serve(response("200 OK", (), b"#EXTM3U\n"))
        self.check_failure("playlist", helper.PLAYLIST_STATUS_FILE, url, "empty_playlist",
                           "no playable channels found in playlist from " + WITHHELD)

    def test_the_memory_refusal_names_the_withheld_host_in_both_verbs(self):
        url = "http://127.0.0.1:9" + PATH
        for verb, status_file, label in (("playlist", helper.PLAYLIST_STATUS_FILE, "playlist"),
                                         ("epg", helper.EPG_STATUS_FILE, "EPG")):
            with self.subTest(verb=verb), mock.patch.object(helper, "fetch_bytes", side_effect=MemoryError):
                rc, stdout, reply, stderr = run(verb, "--url", url, "--cache-dir", self.cache)
                self.assertEqual(rc, 1, stderr)
                self.assertEqual(reply["error"]["code"], "too_large")
                self.assertTrue(reply["error"]["message"].startswith("%s from %s needs more than" % (label, WITHHELD)),
                                reply["error"]["message"])
                self.assertEqual((reply["sourceHost"], self.status(status_file)["sourceHost"]), (WITHHELD, WITHHELD))
                self.assertNotIn("127.0.0.1", stdout + stderr)

    def test_a_refused_connection_to_a_dotless_typo_host_names_it_withheld_and_looks_nothing_up(self):
        url = "http://qqqqqq:1234" + PATH
        refusal = ConnectionRefusedError(errno.ECONNREFUSED, os.strerror(errno.ECONNREFUSED))
        for verb, status_file in (("playlist", helper.PLAYLIST_STATUS_FILE), ("epg", helper.EPG_STATUS_FILE)):
            with self.subTest(verb=verb), LiteralsOnly() as resolver, \
                    mock.patch.object(helper, "bounded_create_connection", side_effect=refusal) as seam:
                rc, stdout, reply, stderr = run(verb, "--url", url, "--cache-dir", self.cache, "--timeout", "5")
                self.assertEqual(rc, 1, stderr)
                self.assertEqual(seam.call_count, 1)
                self.assertEqual(resolver.lookups, [])
                self.assertEqual(reply["error"]["code"], "network")
                self.assertTrue(reply["error"]["message"].startswith("could not reach %s: " % WITHHELD),
                                reply["error"]["message"])
                self.assertEqual((reply["sourceHost"], self.status(status_file)["sourceHost"]), (WITHHELD, WITHHELD))
                self.assert_nothing_private(stdout, stderr, self.written(status_file))


class SuccessStatusTest(Fetches):
    """A download that works prints the shown host in the reply and the
    status file, and channels.json -- data cached_source reads at play
    time -- keeps the RFC host."""

    def test_a_playlist_that_loads_prints_the_withheld_host_and_caches_the_real_one(self):
        url = self.serve(response("200 OK", (), PLAYLIST))
        rc, stdout, reply, stderr = run("playlist", "--url", url, "--cache-dir", self.cache)
        self.assertEqual(rc, 0, stderr)
        self.assertEqual((reply["ok"], reply["sourceHost"], self.status(helper.PLAYLIST_STATUS_FILE)["sourceHost"]),
                         (True, WITHHELD, WITHHELD))
        self.assertEqual(self.status(helper.CHANNELS_FILE)["sourceHost"], "127.0.0.1")
        self.assertNotIn("127.0.0.1", stdout + self.written(helper.PLAYLIST_STATUS_FILE))

    def test_a_guide_that_loads_prints_the_withheld_host_in_every_file_that_prints_it(self):
        url = self.serve(response("200 OK", (("Content-Type", "application/xml"),), guide_body()))
        rc, stdout, reply, stderr = run("epg", "--url", url, "--cache-dir", self.cache)
        self.assertEqual(rc, 0, stderr)
        self.assertEqual((reply["ok"], reply["sourceHost"], self.status(helper.EPG_STATUS_FILE)["sourceHost"]),
                         (True, WITHHELD, WITHHELD))
        now_head = json.loads(self.written(helper.EPG_NOW_FILE).split("\n", 1)[0].rsplit(',"channels"', 1)[0] + "}")
        window_meta = json.loads(self.written(helper.EPG_WINDOW_FILE).split("\n", 1)[0])
        self.assertEqual((now_head["sourceHost"], window_meta["sourceHost"]), (WITHHELD, WITHHELD))
        for name in (helper.EPG_STATUS_FILE, helper.EPG_NOW_FILE, helper.EPG_WINDOW_FILE):
            self.assertNotIn("127.0.0.1", self.written(name), name)
        # The cached window answers the next run with the host it holds.
        rc, stdout, reply, stderr = run("epg", "--url", url, "--cache-dir", self.cache, "--now-only")
        self.assertEqual((rc, reply["sourceHost"]), (0, WITHHELD), stderr)


class OneLabelRuleTest(Fetches):
    """D-SINK-83's rule empties the guide status's host for a one-label host
    the playlist chose. It judges the REAL host: a typo whose username is
    one label is still emptied, and a withheld address whose real host is
    not one label is named `[host withheld]`, where a rule judging the
    printed token -- itself one label -- would empty it."""

    def test_the_one_label_rule_judges_the_real_host(self):
        listener = self.serve(response("404 Not Found"))
        port = listener.split("://", 1)[1].split("/", 1)[0].rsplit(":", 1)[1]
        got = []
        for url in ("http://qqqqqq:1234/zzzz@cdn.test/g.xml", "http://127.0.0.1:%s/zzzz@cdn.test/g.xml" % port):
            env = {helper.ORIGIN_ENV: "playlist", helper.HOME_HOST_ENV: "prov.test"}
            with LiteralsOnly() as resolver, mock.patch.dict(os.environ, env):
                rc, stdout, reply, stderr = run("epg", "--url", url, "--cache-dir", self.cache, "--timeout", "5")
            got.append((rc, reply["error"]["code"], reply["sourceHost"], self.status(helper.EPG_STATUS_FILE)["sourceHost"],
                        [name for name in resolver.lookups if name != "127.0.0.1"]))
            self.assert_nothing_private(stdout, stderr, self.written(helper.EPG_STATUS_FILE))
        self.assertEqual(got, [(1, "local_address", "", "", []), (1, "local_address", WITHHELD, WITHHELD, [])])


if __name__ == "__main__":
    unittest.main()
