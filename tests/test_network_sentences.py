"""D-SINK-93 and D-SINK-94: what the helper's network and scheme refusals say.

D-SINK-93: a network refusal of `playlist`, the probe and `epg` read
`could not reach <host>: <the error's text>`. For a redirect to
`http://user:pass/x@host/` http.client reads `user` as the host and `pass`
as a port, and its InvalidURL quoted the password into the reply, both
status files and the stderr line the shell writes to the journal; no `://`
was left in it for the redactor to find. The detail is now a fixed sentence
chosen by the error's kind (network_detail): an OS error's strerror, "timed
out", a TLS failure's reason token, a refused proxy tunnel's status code,
and otherwise the error's class name -- the owner's rule of 2026-11-08 for
what reaches the journal: codes and fixed sentences only for anything built
from an error message.

D-SINK-94: the three scheme refusals quoted whatever came before a URL's
first `:`, which for an address typed without its `http://` is the
username. A scheme is named only from NAMED_SCHEMES.

The servers are tests/scripted_server.py's, on 127.0.0.1; no shape here is
looked up -- InvalidURL is raised before any connection is made, and a host
D-SINK-86's rule refuses is refused before its request is opened.
"""
import contextlib
import errno
import http.client
import io
import json
import os
import pathlib
import socket
import ssl
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper          # redirects HOME and $XDG_* first
from scripted_server import ScriptedServer, response

helper = load_helper()

SECRETS = ("qqqqqq", "zzzzzz")
PROXY_VARIABLES = ("http_proxy", "https_proxy", "all_proxy", "no_proxy",
                   "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(argv))
    lines = [line for line in out.getvalue().splitlines() if line.strip()]
    return code, out.getvalue(), json.loads(lines[-1]) if lines else None, err.getvalue()


class Fetches(unittest.TestCase):
    def setUp(self):
        clean = {name: value for name, value in os.environ.items() if name not in PROXY_VARIABLES}
        patcher = mock.patch.dict(os.environ, clean, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = tmp.name

    def redirect_to(self, location):
        server = ScriptedServer({"/list": (response("302 Found", (("Location", location),)),)})
        self.addCleanup(server.close)
        return server.url("/list")

    def written(self, name):
        path = pathlib.Path(self.cache) / name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def assert_nothing_private(self, *texts):
        for text in texts:
            for secret in SECRETS:
                self.assertNotIn(secret, text)


class RedirectSentenceTest(Fetches):
    # (Location, code, message after the verb's own words). The first two
    # are D-SINK-93's: http.client refuses them while it builds the
    # connection, before any lookup. The other three are D-SINK-86's,
    # refused by the redirect handler before the hop is opened; they are
    # here so the table holds every userinfo shape a Location can take.
    SHAPES = (
        ("http://qqqqqq:zzzzzz/x@cdn.test/list.m3u", "network", "could not reach 127.0.0.1: InvalidURL"),
        ("http://cdn.test:zzzzzz/list.m3u", "network", "could not reach 127.0.0.1: InvalidURL"),
        ("http://qqqqqq:zzzzzz@cdn.test/list.m3u", "bad_url", None),
        ("http://qqqqqq%3Azzzzzz%40cdn.test/list.m3u", "bad_url", None),
        ("http://qqqqqq:zzzzzz%40cdn.test:8080/list.m3u", "bad_url", None),
    )

    def check(self, verb, status_file):
        for location, code_expected, message in self.SHAPES:
            with self.subTest(verb=verb, location=location):
                url = self.redirect_to(location)
                code, stdout, status, stderr = run(verb, "--url", url, "--cache-dir", self.cache)
                self.assertEqual(code, 1, stderr)
                self.assertEqual(status["error"]["code"], code_expected, status)
                if message is not None:
                    self.assertEqual(status["error"]["message"], message)
                self.assert_nothing_private(stdout, stderr, self.written(status_file))

    def test_the_playlist_verb_names_the_error_by_kind(self):
        self.check("playlist", helper.PLAYLIST_STATUS_FILE)

    def test_the_guide_verb_names_the_error_by_kind(self):
        self.check("epg", helper.EPG_STATUS_FILE)


class FirstLineSentenceTest(Fetches):
    """D-SRC-59's server, whose first line is not a status line: the line
    is the provider's own text, and the refusal now names its kind only."""

    def test_a_first_line_that_is_not_a_status_line_is_named_by_kind(self):
        line = b"BAD http://qqqqqq:zzzzzz@h.test/pppp " + b"w" * 300 + b"\x1b\r\n\r\n"
        server = ScriptedServer({"/list": (line,)})
        self.addCleanup(server.close)
        code, stdout, status, stderr = run("playlist", "--url", server.url("/list"), "--cache-dir", self.cache)
        self.assertEqual(code, 1, stderr)
        self.assertEqual(status["error"], {"code": "network", "message": "could not reach 127.0.0.1: BadStatusLine"})
        for text in (stdout, stderr, self.written(helper.PLAYLIST_STATUS_FILE)):
            for piece in ("BAD", "pppp", "www", "h.test") + SECRETS:
                self.assertNotIn(piece, text)


class NetworkDetailTest(unittest.TestCase):
    """network_detail over the errors a fetch meets, built here."""

    def detail(self, error):
        return helper.network_detail(error)

    def test_an_os_error_gives_its_strerror_and_nothing_else(self):
        self.assertEqual(self.detail(ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused")),
                         "Connection refused")
        self.assertEqual(self.detail(socket.gaierror(socket.EAI_NONAME, "Name or service not known")),
                         "Name or service not known")
        self.assertEqual(self.detail(OSError(errno.ENOENT, "No such file", "/qqqqqq/zzzzzz")), "No such file")
        self.assertEqual(self.detail(OSError(errno.EIO, "a\x1bb\x85c")), "a b c")

    def test_a_timeout_is_timed_out_whatever_its_text(self):
        self.assertEqual(self.detail(TimeoutError("timed out")), "timed out")
        self.assertEqual(self.detail(socket.timeout("qqqqqq zzzzzz")), "timed out")

    def test_the_helpers_own_two_raises_keep_their_sentences(self):
        self.assertEqual(self.detail(TimeoutError(errno.ETIMEDOUT, "the host-name lookup took longer than 0.3 s")),
                         "the host-name lookup took longer than 0.3 s")
        with mock.patch.object(socket, "getaddrinfo", return_value=[]):
            with self.assertRaises(OSError) as caught:
                helper.bounded_create_connection(("cdn.test", 80), 1.0)
        self.assertEqual(self.detail(caught.exception), "getaddrinfo returned an empty list")

    def test_a_tls_failure_gives_its_reason_token_only(self):
        verify = ssl.SSLCertVerificationError(
            1, "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: Hostname mismatch, "
               "certificate is not valid for 'qqqqqq'. (_ssl.c:1000)")
        self.assertEqual(self.detail(verify), "certificate verify failed")
        other = ssl.SSLError(1, "[SSL: WRONG_VERSION_NUMBER] wrong version number (_ssl.c:1000)")
        other.reason = "WRONG_VERSION_NUMBER"
        self.assertEqual(self.detail(other), "TLS error (WRONG_VERSION_NUMBER)")
        other.reason = "qqqqqq zzzzzz"
        self.assertEqual(self.detail(other), "TLS error")
        other.reason = None
        self.assertEqual(self.detail(other), "TLS error")

    def test_a_refused_proxy_tunnel_gives_its_status_code_only(self):
        self.assertEqual(self.detail(OSError("Tunnel connection failed: 407 qqqqqq zzzzzz")),
                         "the proxy refused the tunnel (HTTP 407)")
        self.assertEqual(self.detail(OSError("Tunnel connection failed: 4070 qqqqqq")), "OSError")

    def test_anything_else_is_its_class_name(self):
        for error, name in (
                (http.client.InvalidURL("nonnumeric port: 'zzzzzz'"), "InvalidURL"),
                (http.client.BadStatusLine("BAD http://qqqqqq:zzzzzz@h.test/"), "BadStatusLine"),
                (http.client.LineTooLong("header line"), "LineTooLong"),
                (http.client.RemoteDisconnected("Remote end closed connection without response"), "RemoteDisconnected"),
                (ValueError("qqqqqq zzzzzz"), "ValueError"),
                (OSError("qqqqqq zzzzzz"), "OSError"),
                (urllib.error.URLError("qqqqqq zzzzzz"), "URLError")):
            with self.subTest(name=name):
                self.assertEqual(self.detail(error), name)

    def test_a_url_error_is_read_through_to_its_reason_when_that_is_an_error(self):
        sentence = None
        opener = mock.Mock()
        for wrapped, expected in (
                (urllib.error.URLError(ConnectionRefusedError(errno.ECONNREFUSED, "Connection refused")),
                 "could not reach h.test: Connection refused"),
                (urllib.error.URLError("qqqqqq zzzzzz"), "could not reach h.test: URLError")):
            opener.open.side_effect = wrapped
            with self.assertRaises(helper.HelperError) as caught:
                helper.read_http_response(opener, object(), 1.0, "playlist", "h.test", float("inf"))
            sentence = caught.exception.message
            self.assertEqual((caught.exception.code, sentence), ("network", expected))


class SchemeSentenceTest(Fetches):
    def test_a_scheme_is_named_only_from_the_list(self):
        self.assertEqual([helper.scheme_phrase(value) for value in ("ftp", "FTP", "rtmp", "data")],
                         [" 'ftp'", " 'ftp'", " 'rtmp'", " 'data'"])
        self.assertEqual([helper.scheme_phrase(value) for value in ("qqqqqq", "", None, "ftp2")], [""] * 4)

    def test_the_source_validator_names_no_username(self):
        typed = helper.validate_source_url("qqqqqq:zzzzzz@cdn.test:8080/get.php")
        self.assertEqual((typed["code"], typed["message"]),
                         ("scheme", "unsupported source scheme (use http, https or an absolute path)"))
        ftp = helper.validate_source_url("ftp://cdn.test/list.m3u")
        self.assertEqual(ftp["message"], "unsupported source scheme 'ftp' (use http, https or an absolute path)")

    def test_the_fetch_verbs_name_no_username(self):
        for verb, status_file in (("playlist", helper.PLAYLIST_STATUS_FILE), ("epg", helper.EPG_STATUS_FILE)):
            with self.subTest(verb=verb):
                code, stdout, status, stderr = run(verb, "--url", "qqqqqq:zzzzzz@cdn.test:8080/get.php",
                                                   "--cache-dir", self.cache)
                self.assertEqual((code, status["error"]["code"]), (1, "unsupported_scheme"))
                self.assert_nothing_private(stdout, stderr, self.written(status_file))

    def test_a_stream_to_play_names_no_username(self):
        for url, message in (("qqqqqq:zzzzzz@cdn.test/live/1.ts", "unsupported stream URL scheme"),
                             ("ftp://cdn.test/live/1.ts", "unsupported stream URL scheme 'ftp'")):
            with self.subTest(url=url):
                with self.assertRaises(helper.HelperError) as caught:
                    helper.player_target("", url, self.cache)
                self.assertEqual((caught.exception.code, caught.exception.message), ("unsupported_scheme", message))

    def test_a_redirect_to_another_scheme_names_it_only_from_the_list(self):
        for location, message in (("ftp://cdn.test/list.m3u", "playlist from 127.0.0.1 redirected to an unsupported scheme 'ftp'"),
                                  ("qqqqqq://zzzzzz@cdn.test/list.m3u", "playlist redirect from 127.0.0.1 not followed")):
            with self.subTest(location=location):
                url = self.redirect_to(location)
                code, stdout, status, stderr = run("playlist", "--url", url, "--cache-dir", self.cache)
                self.assertEqual((code, status["error"]["code"]), (1, "unsafe_redirect"))
                self.assertEqual(status["error"]["message"], message)
                self.assert_nothing_private(stdout, stderr, self.written(helper.PLAYLIST_STATUS_FILE))

    def test_a_refused_redirect_is_closed_not_left_to_the_collector(self):
        # urllib's HTTPError for a redirect it will not follow holds the
        # response, and its message is the target URL: left to the
        # collector, it is reported in a ResourceWarning that quotes it.
        import gc
        import warnings
        url = self.redirect_to("qqqqqq://zzzzzz@cdn.test/list.m3u")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            code, stdout, status, stderr = run("playlist", "--url", url, "--cache-dir", self.cache)
            gc.collect()
        self.assertEqual(code, 1, stderr)
        self.assert_nothing_private(*(str(warning.message) for warning in caught))


class LocalSocketSentenceTest(unittest.TestCase):
    """D-SINK-93's siblings by shape (rule 15): the player's socket and lock
    refusals gave an OSError's strerror, or, when it had none, the error's
    own text. Now its class name."""

    ERROR = OSError("qqqqqq zzzzzz")

    def refused(self, call):
        with self.assertRaises(helper.HelperError) as caught:
            call()
        return caught.exception.code, caught.exception.message

    def test_the_socket_refusals_name_an_error_without_strerror_by_kind(self):
        made = mock.Mock()
        made.connect.side_effect = self.ERROR
        with mock.patch.object(socket, "socket", return_value=made):
            client = helper.MpvIpc("/nonexistent/mpv.sock", 1.0)
            self.assertEqual(self.refused(client.connect), ("ipc_error", "could not connect to mpv: OSError"))
        with mock.patch.object(socket, "socket", side_effect=self.ERROR):
            client = helper.MpvIpc("/nonexistent/mpv.sock", 1.0)
            self.assertEqual(self.refused(client.connect), ("ipc_error", "could not connect to mpv: OSError"))
        client = helper.MpvIpc("/nonexistent/mpv.sock", 1.0)
        client.sock = mock.Mock()
        client.sock.recv.side_effect = self.ERROR
        self.assertEqual(self.refused(lambda: client.read_line(float("inf"))),
                         ("ipc_error", "could not read from mpv: OSError"))
        client.sock.sendall.side_effect = self.ERROR
        self.assertEqual(self.refused(lambda: client.command("get_property", "pid")),
                         ("ipc_error", "could not write to mpv: OSError"))

    def test_the_lock_refusal_names_an_error_without_strerror_by_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(helper.fcntl, "flock", side_effect=self.ERROR):
                code, message = self.refused(lambda: helper.acquire_lock(os.path.join(tmp, "lock"), 0.1))
        self.assertEqual((code, message), ("busy", "could not lock the player: OSError"))


if __name__ == "__main__":
    unittest.main()
