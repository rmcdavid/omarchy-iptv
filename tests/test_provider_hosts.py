"""D-SINK-82 and D-SINK-83 (the owner, 2026-11-05): two rules about a host
the PLAYLIST chose.

1. A guide hint that is a comma-joined list is read as its FIRST entry.
   `url-tvg="https://epg.test/guide.xml.gz,http://prov.test/xmltv.php?
   username=U&password=P"` is several guides to Kodi's pvr.iptvsimple, and it
   was one URL to the shell: the first URL's host, `,http://prov.test/...` in
   its path, so the second URL's credential went to the first URL's host on
   every guide refresh, with no click. The shell now adopts the first entry
   alone (Model.hintFirstEntry, Model.epgHintVerdict) and the helper's guide
   fetch refuses a URL the playlist chose that is not its own first entry
   (fetch_bytes), so a shell loaded before the rule sends nothing.
2. A host of ONE DNS label that the playlist chose for a guide hint or a
   logo is refused before any lookup -- the guide hint's playlist host
   excepted, a logo never -- because a URL cut at a space in its userinfo
   (D-SINK-34's class) leaves `http://USER:...`, whose host is the username.
3. (The review's F1, 2026-11-06.) A guide hint or a logo whose URL's run
   took a glued or listed attribute holding another URL -- a raw `"`, or a
   `,` opening `key=scheme://` (absorbed_attribute) -- is never fetched: the
   attribute grammar keeps a URL value whole to its run's end (D-SINK-80),
   and the fetches sent the second URL's credential to the first's host.

How this module observes it: tests/fixtures/provider-hosts.json is run here
against the helper and in tests/Model.test.js against the model; the
resolver is the sink, so every fetch here runs with socket.getaddrinfo
replaced by a recorder that answers numeric hosts and refuses every name --
"no lookup" means the recorder saw no call, and a refused name is never
connected to because it is never resolved.
Nothing leaves the machine.
"""
import contextlib
import http.server
import io
import ipaddress
import json
import os
import pathlib
import socket
import socketserver
import tempfile
import threading
import time
import unittest
import urllib.parse
from unittest import mock

from helper_loader import load_helper, loopback_reads_public

helper = load_helper()
ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "provider-hosts.json").read_text(encoding="ascii"))
PROXY_NAMES = ("http_proxy", "https_proxy", "all_proxy", "no_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
SECRETS = ("qqqqqq", "zzzzzz")


class Resolver:
    """socket.getaddrinfo's stand-in: every host asked for is recorded; a
    numeric one is answered by the real resolver (which parses it and sends
    nothing), a name in `names` as the numeric address it maps to, and every
    other name is refused as unknown, so no name ever leaves."""

    def __init__(self, names=None):
        self.lookups = []
        self.names = dict(names or {})
        self.real = socket.getaddrinfo

    def getaddrinfo(self, host, port, *args, **kwargs):
        text = host.decode("ascii", "replace") if isinstance(host, bytes) else str(host)
        self.lookups.append(text)
        if text in self.names:
            return self.real(self.names[text], port, *args, **kwargs)
        try:
            ipaddress.ip_address(text.split("%", 1)[0])
        except ValueError:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known (refused by the test)") from None
        return self.real(host, port, *args, **kwargs)

    def __enter__(self):
        self.patches = [mock.patch.object(socket, "getaddrinfo", self.getaddrinfo)]
        for patch in self.patches:
            patch.start()
        return self

    def __exit__(self, *_):
        for patch in self.patches:
            patch.stop()
        return False


def provenance(origin, home="", port=""):
    """The fetch environment a shell sets beside the URL (fetchEnvironmentFor),
    every proxy variable removed."""
    env = {helper.ORIGIN_ENV: origin, helper.HOME_HOST_ENV: home, helper.HOME_PORT_ENV: port}
    patch = mock.patch.dict(os.environ, env)
    patch.start()
    for name in PROXY_NAMES:
        os.environ.pop(name, None)
    if origin == "":
        os.environ.pop(helper.ORIGIN_ENV, None)
    if home == "":
        os.environ.pop(helper.HOME_HOST_ENV, None)
    if port == "":
        os.environ.pop(helper.HOME_PORT_ENV, None)
    return patch


def run(fn):
    """-> (code, message) of the HelperError fn raises, or ("ok", "")."""
    try:
        fn()
    except helper.HelperError as error:
        return error.code, error.message
    return "ok", ""


def netloc_of(url):
    """A logo URL's authority as Model.splitLogoUrl reads it: after `://` up
    to the first `/`, `?` or `#`. Not urlsplit, which raises on a bracketed
    name (`https://[qqqqqq]/`, the fixture's one such case)."""
    rest = url[url.find("://") + 3:]
    ends = [i for i in (rest.find("/"), rest.find("?"), rest.find("#")) if i != -1]
    return rest[:min(ends)] if ends else rest


class FixtureTest(unittest.TestCase):
    """The shared fixture, helper side. Every expected value in it was written
    by hand; the model answers the same file in tests/Model.test.js."""

    def test_the_fixture_is_whole_and_ascii(self):
        raw = (ROOT / "tests" / "fixtures" / "provider-hosts.json").read_bytes()
        self.assertTrue(all(b < 0x80 for b in raw))
        self.assertEqual([len(FIXTURE[k]) >= 10 for k in ("firstEntry", "noDot", "hintVerdicts", "handOffs", "logoHosts", "absorbed")],
                         [True] * 6)

    def test_the_first_entry_of_every_hint(self):
        got = [(c["hint"], helper.hint_first_entry(c["hint"])) for c in FIXTURE["firstEntry"]]
        self.assertEqual(got, [(c["hint"], c["first"]) for c in FIXTURE["firstEntry"]])

    def test_every_address_absorbed_or_not_as_the_fixture_says(self):
        got = [(c["text"], helper.absorbed_attribute(c["text"])) for c in FIXTURE["absorbed"]]
        self.assertEqual(got, [(c["text"], c["absorbed"]) for c in FIXTURE["absorbed"]])

    def test_every_host_is_one_label_or_not_as_the_fixture_says(self):
        got = [(c["host"], helper.dotless_host(c["host"])) for c in FIXTURE["noDot"]]
        self.assertEqual(got, [(c["host"], c["refused"]) for c in FIXTURE["noDot"]])

    def test_every_hand_off_is_a_list_and_one_label_as_the_fixture_says(self):
        got = [(c["url"], helper.hint_first_entry(c["url"]) != c["url"],
                helper.dotless_host(urllib.parse.urlsplit(c["url"]).hostname)) for c in FIXTURE["handOffs"]]
        self.assertEqual(got, [(c["url"], c["listed"], c["oneLabel"]) for c in FIXTURE["handOffs"]])

    def test_the_policy_says_of_each_hint_host_what_the_verdict_says(self):
        """The model's `no hint` for a one-label host and the helper's
        refusal of the same host are one rule in two places: for every hint
        whose first entry is an http URL, the policy built from the
        environment the shell would set (origin `playlist`, the playlist's
        host) refuses that host's name exactly when the fixture says -- and
        the fixture says so only where the verdict is no hint at all."""
        got, want = [], []
        for c in FIXTURE["hintVerdicts"]:
            if c["helperRefusesName"] is None:
                continue
            host = urllib.parse.urlsplit(helper.hint_first_entry(c["hint"])).hostname or ""
            patch = provenance("playlist", c["playlistHost"])
            try:
                got.append((c["hint"], helper.DestinationPolicy.from_environment("EPG").refuses_name(host)))
            finally:
                patch.stop()
            want.append((c["hint"], c["helperRefusesName"]))
        self.assertEqual(got, want)
        none = {"url": "", "refused": "", "host": "", "plainHttp": False}
        self.assertEqual([c["hint"] for c in FIXTURE["hintVerdicts"] if c["helperRefusesName"] and c["expected"] != none], [])

    def test_the_logo_host_of_every_case(self):
        got = [(c["url"], helper.logo_survey_host(c["url"], netloc_of(c["url"]))) for c in FIXTURE["logoHosts"]]
        self.assertEqual(got, [(c["url"], c["host"]) for c in FIXTURE["logoHosts"]])


class HandOffTest(unittest.TestCase):
    """What the guide fetch does with the URL a shell hands it, observed at
    the resolver."""

    def hand_off(self, case):
        patch = provenance(case["origin"], case["playlistHost"])
        try:
            with Resolver() as resolver:
                code, message = run(lambda: helper.fetch_bytes(case["url"], 1.0, "EPG"))
        finally:
            patch.stop()
        return code, message, resolver.lookups

    def test_every_hand_off_asks_the_resolver_only_what_the_fixture_says(self):
        got, want = [], []
        for case in FIXTURE["handOffs"]:
            code, _, lookups = self.hand_off(case)
            got.append((case["url"], case["origin"], code, lookups))
            want.append((case["url"], case["origin"], case["code"], case["lookups"]))
        self.assertEqual(got, want)

    def test_a_refusal_names_no_host_and_no_url(self):
        for case in FIXTURE["handOffs"]:
            if case["code"] not in ("bad_url", "local_address") or case["lookups"]:
                continue
            code, message, _ = self.hand_off(case)
            with self.subTest(url=case["url"]):
                for leak in SECRETS + ("epg.test", "prov.test", "other", "tvbox", "2130706433", "://"):
                    self.assertNotIn(leak, message.lower(), message)

    def test_the_measured_list_is_refused_before_anything_and_the_users_is_not(self):
        """The critic's M3, at the helper: a shell loaded before the rule
        hands the whole list with origin `playlist`; the same text typed by
        the user is theirs and is looked up, its first host only."""
        url = FIXTURE["firstEntry"][0]["hint"]
        code, message, lookups = self.hand_off({"url": url, "origin": "playlist", "playlistHost": "prov.test"})
        self.assertEqual((code, lookups), ("bad_url", []))
        self.assertEqual(message, "EPG address the playlist chose lists more than one URL; not used")
        code, _, lookups = self.hand_off({"url": url, "origin": "user", "playlistHost": ""})
        self.assertEqual((code, lookups), ("network", ["epg.test"]))


class PolicyTest(unittest.TestCase):
    """DestinationPolicy.refuses_name and where it is asked, called."""

    def test_who_is_refused_a_one_label_name(self):
        P = helper.DestinationPolicy
        cases = [
            (P("EPG", "playlist", "prov.test"), "qqqqqq", True),
            (P("EPG", "playlist", "prov.test"), "QQQQQQ.", True),
            (P("EPG", "playlist", "prov.test"), "epg.test", False),
            (P("EPG", "playlist", "prov.test"), "::1", False),
            (P("EPG", "playlist"), "qqqqqq", True),
            # A host whose key is empty (whitespace only) against an empty
            # home: the home clause keeps it refused.
            (P("EPG", "playlist"), " ", True),
            (P("EPG", "playlist", "tvbox"), "tvbox", False),
            (P("EPG", "playlist", "tvbox"), "TVBOX.", False),
            (P("EPG", "playlist", "TVBox."), "tvbox", False),
            (P("EPG", "playlist", "tvbox"), "other", True),
            (P("EPG", "user"), "tvbox", False),
            (P("playlist", "user", "tvbox"), "other", False),
            (P.for_logos(), "qqqqqq", True),
            (P.for_logos(), "cdn.test", False),
            # A logo is never excepted, not even on a home it was given.
            (P("logo", "playlist", "cdn", logos=True), "cdn", True),
            (P("logo", "user", "cdn", logos=True), "cdn", True),
        ]
        self.assertEqual([(p.origin, p.home, p.logos, h, p.refuses_name(h)) for p, h, _ in cases],
                         [(p.origin, p.home, p.logos, h, w) for p, h, w in cases])

    def test_a_refused_name_is_never_looked_up_on_any_hop(self):
        for first in (True, False):
            for policy in (helper.DestinationPolicy("EPG", "playlist", "prov.test"), helper.DestinationPolicy.for_logos()):
                with self.subTest(first=first, logos=policy.logos), Resolver() as resolver:
                    code, message = run(lambda: helper.bounded_create_connection(("qqqqqq", 80), 1.0, policy=policy, first=first))
                self.assertEqual((code, resolver.lookups), ("local_address", []))
                self.assertNotIn("qqqqqq", message)
                self.assertIn("a redirect" if not first else "the playlist", message)

    def test_a_name_the_user_typed_is_looked_up_on_every_hop(self):
        for first in (True, False):
            policy = helper.DestinationPolicy("playlist", "user")
            if not first:
                policy.connected("p.example.test", "global", True)
            with self.subTest(first=first), Resolver() as resolver:
                with self.assertRaises(OSError):
                    helper.bounded_create_connection(("tvbox", 80), 1.0, policy=policy, first=first)
            self.assertEqual(resolver.lookups, ["tvbox"])

    def test_a_dotted_name_the_playlist_chose_still_reaches_the_lookup(self):
        for policy in (helper.DestinationPolicy("EPG", "playlist", "prov.test"), helper.DestinationPolicy.for_logos()):
            with self.subTest(logos=policy.logos), Resolver() as resolver:
                with self.assertRaises(OSError):
                    helper.bounded_create_connection(("cdn.test", 80), 1.0, policy=policy, first=True)
            self.assertEqual(resolver.lookups, ["cdn.test"])

    def test_through_a_proxy_the_name_is_refused_before_the_target_is_looked_up(self):
        for policy in (helper.DestinationPolicy("EPG", "playlist", "prov.test"), helper.DestinationPolicy.for_logos()):
            with self.subTest(logos=policy.logos), Resolver() as resolver:
                code, message = run(lambda: policy.check_proxied("qqqqqq", 80, 1.0, True))
            self.assertEqual((code, resolver.lookups), ("local_address", []))
            self.assertNotIn("qqqqqq", message)
        own = helper.DestinationPolicy("EPG", "playlist", "tvbox")
        with Resolver() as resolver:
            code, message = run(lambda: own.check_proxied("tvbox", 80, 1.0, True))
        self.assertEqual((code, resolver.lookups), ("network", ["tvbox"]), "the playlist's own name is checked as before")
        typed = helper.DestinationPolicy("playlist", "user")
        with Resolver() as resolver:
            typed.check_proxied("tvbox", 80, 1.0, typed.begin_hop())
        self.assertEqual((resolver.lookups, typed.first_class), (["tvbox"], "unresolved"))


class QuietHTTPServer(http.server.ThreadingHTTPServer):
    """ThreadingHTTPServer without HTTPServer.server_bind's getfqdn, which
    asks the system resolver for the bound address's name, outside the
    Resolver stand-in: so a test server here looks nothing up either."""

    def server_bind(self):
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


class RecordingProxy:
    """An HTTP proxy on 127.0.0.1 that records each request line's target and
    answers 200 with two bytes: what a refused target must never reach."""

    def __init__(self):
        seen = self.seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                seen.append(self.path)
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(b"ok")

        self.httpd = QuietHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


class RedirectingServer:
    """HTTP on 127.0.0.1: every GET is answered 302 to `location`."""

    def __init__(self, location):
        seen = self.seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                seen.append(self.path)
                self.send_response(302)
                self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.send_header("Connection", "close")
                self.end_headers()

        self.httpd = QuietHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


class FetchTest(unittest.TestCase):
    """The shipping fetches end to end, a proxy and a redirect included."""

    def test_a_one_label_guide_host_through_a_proxy_reaches_neither_the_resolver_nor_the_proxy(self):
        proxy = RecordingProxy()
        self.addCleanup(proxy.close)
        patch = provenance("playlist", "prov.test")
        try:
            os.environ["http_proxy"] = "http://127.0.0.1:%d" % proxy.port
            with Resolver() as resolver:
                code, message = run(lambda: helper.fetch_bytes("http://qqqqqq:12/x", 1.0, "EPG"))
        finally:
            patch.stop()
        self.assertEqual((code, proxy.seen, [h for h in resolver.lookups if h != "127.0.0.1"]), ("local_address", [], []))
        self.assertNotIn("qqqqqq", message)

    def test_the_users_proxy_may_be_a_name_of_one_label(self):
        """The review's F6: the one-label rule is asked of the TARGET, never
        of the user's own proxy. A proxy named `proxy` (answered with
        127.0.0.1) carries a hinted guide on a dotted host (answered with
        127.0.0.2, which the test seam alone reads as global, so a fetch
        that skipped the proxy would be refused on this machine and reach
        nothing beyond it): the request reaches the proxy. Not on 127.0.0.1,
        or the proxy would read as global too and a policy that classified
        the proxy would pass."""
        proxy = RecordingProxy()
        self.addCleanup(proxy.close)
        patch = provenance("playlist", "prov.test")
        try:
            os.environ["http_proxy"] = "http://proxy:%d" % proxy.port
            with loopback_reads_public(helper, "127.0.0.2"), \
                    Resolver({"proxy": "127.0.0.1", "epg.test": "127.0.0.2"}) as resolver:
                code, message = run(lambda: helper.fetch_bytes("http://epg.test/guide.xml", 2.0, "EPG"))
        finally:
            patch.stop()
        self.assertEqual((code, message, proxy.seen), ("ok", "", ["http://epg.test/guide.xml"]))
        self.assertIn("proxy", resolver.lookups)

    def test_a_dotted_host_the_user_typed_reaches_the_proxy_after_its_check(self):
        """The control: the proxy path is reached (the test above is not a
        proxy that never answers), and the target is still looked up first."""
        proxy = RecordingProxy()
        self.addCleanup(proxy.close)
        patch = provenance("user")
        try:
            os.environ["http_proxy"] = "http://127.0.0.1:%d" % proxy.port
            with Resolver() as resolver:
                code, _ = run(lambda: helper.fetch_bytes("http://epg.test/x", 1.0, "EPG"))
        finally:
            patch.stop()
        self.assertEqual((code, proxy.seen, resolver.lookups[0]), ("ok", ["http://epg.test/x"], "epg.test"))

    def test_a_redirect_to_a_one_label_host_is_refused_before_its_lookup(self):
        """A hinted guide on the playlist's own loopback host and port (the
        one place a provider-chosen first hop may be local) that redirects
        to a one-label name: the first hop is made, the second is never
        looked up, and the refusal names no host."""
        server = RedirectingServer("http://qqqqqq/xmltv.php?username=qqqqqq&password=zzzzzz")
        self.addCleanup(server.close)
        patch = provenance("playlist", "127.0.0.1", str(server.port))
        os.environ[helper.HOME_CLASS_ENV] = "loopback"
        try:
            with Resolver() as resolver:
                code, message = run(lambda: helper.fetch_bytes("http://127.0.0.1:%d/epg.xml" % server.port, 2.0, "EPG"))
        finally:
            os.environ.pop(helper.HOME_CLASS_ENV, None)
            patch.stop()
        self.assertEqual((code, server.seen, resolver.lookups), ("local_address", ["/epg.xml"], ["127.0.0.1"]))
        self.assertIn("a redirect", message)
        for leak in SECRETS:
            self.assertNotIn(leak, message)

    def test_every_logo_asks_the_resolver_only_what_the_fixture_says(self):
        got, want = [], []
        for case in FIXTURE["logoHosts"]:
            if case["fetch"] is None:
                continue
            patch = provenance("")
            try:
                with Resolver() as resolver:
                    code, message = run(lambda: helper.fetch_logo(case["url"], 1.0, 2.0))
            finally:
                patch.stop()
            got.append((case["url"], code, resolver.lookups))
            want.append((case["url"], case["fetch"]["code"], case["fetch"]["lookups"]))
            if case["fetch"]["code"] == "logo_host":
                self.assertNotIn("qq", message.lower(), message)
        self.assertEqual(got, want)

    def test_the_cut_logo_is_counted_refused_and_never_named(self):
        """The critic's grid: `https://qqqqqq:` was counted as a host to
        contact and named as the busiest in the survey the consent dialog is
        composed from."""
        survey = helper.logo_survey([{"logo": "https://qqqqqq:"}, {"logo": "https://qqqqqq:443/a.png"},
                                     {"logo": "https://cdn.test/a.png"}])
        self.assertEqual((survey["refused"], survey["wouldContact"], survey["hosts"]),
                         (2, 1, [{"host": "cdn.test", "channels": 1}]))
        self.assertNotIn("qqqqqq", json.dumps(survey))


class RecordingServer:
    """HTTP on 127.0.0.1: every GET is recorded and answered 200 with a
    tiny guide."""

    def __init__(self):
        seen = self.seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                seen.append(self.path)
                body = b"<tv></tv>"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)

        self.httpd = QuietHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


class AbsorbedTest(unittest.TestCase):
    """The review's F1 end to end, and its recheck: the attribute grammar
    keeps a URL value whole to its run's end, so a playlist header holding
    two guide URLs glued or listed across a `"`, or a bare value with any
    text glued after its comma, stored them as ONE hint, and the guide fetch
    sent the second URL's credential to the first URL's host in the request
    line. Now the shipping parse stores no hint and no logo from a value
    that ran past where every earlier release ended it, beyond its own
    piece (own_value): a hint keeps its first entry when a comma-joined
    list opens at that end, and a value that ran past by its trailing comma
    alone keeps what 0.17.0 kept; and the fetches
    still refuse such an address handed over raw, as a cache or a shell
    from before the rule would (absorbed_attribute), on the playlist's own
    loopback host and port (the one place a provider-chosen guide may be
    local), reaching neither the resolver nor the server. The controls --
    the first URL alone, and a bare list -- are fetched."""

    SECOND = "http://prov.test/xmltv.php?username=qqqqqq&password=zzzzzz"
    QUOTED = ('","', '";"', '"|"', '"x-tvg-url="', '"tvg-url="')
    # The recheck's bare shapes: whatever a bare value took past its comma.
    BARE = (",x-tvg-url=%s", ",x-tvg-url='%s'", ",x-tvg-url=<%s>", ",=%s", ",x:tvg=%s",
            ",x-tvg-url=//prov.test/xmltv.php?username=qqqqqq&password=zzzzzz",
            ",username=qqqqqq,password=zzzzzz")
    # (A bare `A,http://B` is a comma-joined list, D-SINK-82's: kept, and
    # read as its first entry; a logo has no list reading, below.)

    def hint_of(self, header):
        return helper.parse_m3u(header + "\n#EXTINF:-1,A\nhttp://cdn.test/a.ts\n")["epgUrlHint"]

    def fetch(self, server, url):
        patch = provenance("playlist", "127.0.0.1", str(server.port))
        os.environ[helper.HOME_CLASS_ENV] = "loopback"
        try:
            with Resolver() as resolver:
                code, message = run(lambda: helper.fetch_bytes(url, 2.0, "EPG"))
        finally:
            os.environ.pop(helper.HOME_CLASS_ENV, None)
            patch.stop()
        return code, message, resolver.lookups

    def test_the_parse_stores_no_absorbed_hint(self):
        first = "http://127.0.0.1:1/guide.xml"
        headers = ['#EXTM3U url-tvg="%s%s%s"' % (first, sep, self.SECOND) for sep in self.QUOTED]
        headers += ["#EXTM3U url-tvg=" + first + (shape % self.SECOND if "%s" in shape else shape) for shape in self.BARE]
        # A list that opens only AFTER the comma the bare value ran past is
        # absorbed text all the same.
        headers.append("#EXTM3U url-tvg=" + first + "?a=1,b," + self.SECOND)
        # A quoted value never takes the list exception: its old end is its
        # `"`, whatever whitespace leads the value (the final check: the
        # offset was taken before the strip, so one or two leading spaces
        # landed it on the comma after the quote).
        for lead in (" ", "\t", "  "):
            headers.append('#EXTM3U url-tvg="%s%s",%s"' % (lead, first, self.SECOND))
        headers.append('#EXTM3U url-tvg="  %s",,%s"' % (first, self.SECOND))
        # Counted from the stored value, the old end of `" A","` is its `"`,
        # not the `,` after it, so no trailing-comma piece (`A"`) is kept.
        headers.append('#EXTM3U url-tvg=" %s","' % first)
        # The list opening is the attribute's own: a bare value before it
        # that opens a list lends none to a quoted hint that ran past its
        # quote, whose own first piece is the username of the URL a `"` cut.
        headers.append('#EXTM3U tvg-shift=x://a,https://b.test url-tvg="http://qqqqqq:12"zzzz@epg.test/e.xml"')
        got = [(h, self.hint_of(h)) for h in headers]
        self.assertEqual(got, [(h, "") for h in headers])
        # The controls: a list opening at the bare value's old end keeps its
        # FIRST entry alone, so no shell, however old, sees a later one --
        # with or without delimiters after the comma, as hint_first_entry
        # reads one; a bare value that ran past by its trailing comma alone
        # keeps what 0.17.0 kept; a quoted list is stored as its first entry
        # too; and a quoted value's own comma is its own.
        for sep in (",", ", ", ",\t", ",  "):
            self.assertEqual(self.hint_of("#EXTM3U url-tvg=%s%shttps://epg.test/b.xml" % (first, sep)), first)
        self.assertEqual(self.hint_of("#EXTM3U url-tvg=%s," % first), first)
        self.assertEqual(self.hint_of("#EXTM3U url-tvg=%s, username=qqqqqq,password=zzzzzz" % first), first)
        self.assertEqual(self.hint_of('#EXTM3U url-tvg="%s,%s"' % (first, self.SECOND)), first)
        self.assertEqual(self.hint_of('#EXTM3U url-tvg="https://epg.test/g.xml?ids=1,2"'), "https://epg.test/g.xml?ids=1,2")
        # A non-ASCII space after a quoted URL's closing quote ends nothing.
        self.assertEqual(self.hint_of('#EXTM3U url-tvg="https://epg.test/g.xml"' + chr(0xa0) + ' tvg-shift="0"'),
                         "https://epg.test/g.xml")
        # A quoted value that absorbed the next one leaves the other key.
        self.assertEqual(self.hint_of('#EXTM3U url-tvg=" %s",%s" x-tvg-url="https://epg2.test/g.xml"' % (first, self.SECOND)),
                         "https://epg2.test/g.xml")
        # A later clean value of the same key is the hint.
        self.assertEqual(self.hint_of("#EXTM3U url-tvg=%s,junk url-tvg=https://epg.test/g.xml" % first), "https://epg.test/g.xml")
        # And a dropped key leaves the other one to name the hint.
        self.assertEqual(self.hint_of("#EXTM3U url-tvg=https://epg.test/g,junk x-tvg-url=https://epg2.test/g.xml"),
                         "https://epg2.test/g.xml")

    def test_no_absorbed_hint_handed_over_raw_reaches_the_resolver_or_the_server(self):
        server = RecordingServer()
        self.addCleanup(server.close)
        first = "http://127.0.0.1:%d/guide.xml" % server.port
        raw = [first + sep + self.SECOND for sep in self.QUOTED] + [first + ",x-tvg-url=" + self.SECOND]
        got = []
        for url in raw:
            code, message, lookups = self.fetch(server, url)
            got.append((url, helper.absorbed_attribute(url), code, lookups))
            for leak in SECRETS + ("prov.test", "://"):
                self.assertNotIn(leak, message)
        self.assertEqual(got, [(url, True, "bad_url", []) for url in raw])
        self.assertEqual(server.seen, [])
        # The controls: the first URL alone is fetched, and so is the first
        # entry of a bare list, so the server and the parse above are not
        # what kept the requests away.
        self.assertEqual(self.fetch(server, self.hint_of('#EXTM3U url-tvg="%s"' % first))[:2], ("ok", ""))
        listed = self.hint_of("#EXTM3U url-tvg=%s,%s" % (first, first.replace("guide", "other")))
        self.assertEqual(listed, first)
        self.assertEqual(self.fetch(server, listed)[:2], ("ok", ""))
        self.assertEqual(server.seen, ["/guide.xml", "/guide.xml"])

    def test_no_absorbed_logo_is_stored_counted_or_fetched(self):
        lines = ['#EXTINF:-1 tvg-logo="https://logos.test/news.png"catchup-source="http://prov.test/timeshift/'
                 'qqqqqq/zzzzzz/{duration}/{start}/1.ts" tvg-id="N.1",News',
                 "#EXTINF:-1 tvg-logo=https://logos.test/a.png,catchup-source=http://prov.test/timeshift/"
                 'qqqqqq/zzzzzz/1.ts tvg-id="B.1",B',
                 "#EXTINF:-1 tvg-logo=https://logos.test/a.png,http://prov.test/timeshift/qqqqqq/zzzzzz/1.ts"
                 ' tvg-id="C.1",C',
                 "#EXTINF:-1 tvg-logo=https://logos.test/a.png,catchup-source='http://prov.test/qqqqqq/zzzzzz'"
                 ' tvg-id="D.1",D']
        text = "#EXTM3U\n" + "".join(line + "\nhttp://cdn.test/%d.ts\n" % i for i, line in enumerate(lines))
        channels = helper.parse_m3u(text)["channels"]
        self.assertEqual([c.get("logo") for c in channels], [None] * 4)
        self.assertEqual(helper.logo_survey(channels)["withLogo"], 0)
        # The backstop, for a logo stored before the rule: refused before
        # any lookup, naming no host and no credential.
        for logo in ('https://logos.test/news.png"catchup-source="http://prov.test/timeshift/qqqqqq/zzzzzz/1.ts',
                     "https://logos.test/a.png,catchup-source=http://prov.test/timeshift/qqqqqq/zzzzzz/1.ts"):
            with Resolver() as resolver:
                code, message = run(lambda: helper.fetch_logo(logo, 1.0, 2.0))
            self.assertEqual((code, resolver.lookups), ("logo_url", []))
            for leak in SECRETS + ("logos.test", "prov.test", "://"):
                self.assertNotIn(leak, message)
        # A later clean value of the same key is the logo.
        again = helper.parse_m3u("#EXTM3U\n#EXTINF:-1 tvg-logo=https://logos.test/a.png,junk tvg-logo=https://logos.test/b.png tvg-id=\"N.1\",N"
                                 "\nhttp://cdn.test/n.ts\n")
        self.assertEqual(again["channels"][0].get("logo"), "https://logos.test/b.png")
        # A bare logo that ran past by its trailing comma alone keeps what
        # 0.17.0 kept, and a non-ASCII space after a quoted logo's closing
        # quote ends nothing.
        own = helper.parse_m3u("#EXTM3U\n#EXTINF:-1 tvg-logo=https://logos.test/a.png, News\nhttp://cdn.test/n.ts\n"
                               '#EXTINF:-1 tvg-logo="https://logos.test/b.png"' + chr(0xa0) + ' group-title="G" tvg-id="b.1",B'
                               "\nhttp://cdn.test/b.ts\n")["channels"]
        self.assertEqual([(c.get("logo"), c["name"], c["group"]) for c in own],
                         [("https://logos.test/a.png", "News", "Ungrouped"), ("https://logos.test/b.png", "B", "G")])
        # The control: a logo the parse keeps whole is a logo.
        kept = helper.parse_m3u('#EXTM3U\n#EXTINF:-1 tvg-logo="https://logos.test/w_1,h_1/a.png",N\nhttp://cdn.test/n.ts\n')
        self.assertEqual(kept["channels"][0].get("logo"), "https://logos.test/w_1,h_1/a.png")


class LinearTimeTest(unittest.TestCase):
    """hint_first_entry is one native search: linear on every shape that
    could make its pattern back off (each run is ended by a character it
    cannot hold, and each attempt starts at a `,`). A hint is dropped at
    parse past 2,048 characters, so this bounds far more than any cache."""

    SHAPES = [lambda n: "," * n, lambda n: ",a" * (n // 2), lambda n: "," + "a" * n, lambda n: ", " * (n // 2),
              lambda n: "," + " " * n, lambda n: ",a:" + "\x00" * n, lambda n: ",a:/" + "\x1f" * n,
              lambda n: ",a:" * (n // 3), lambda n: "http://a.test/x?" + "1," * (n // 2)]

    def best(self, text):
        times = []
        for _ in range(5):
            t0 = time.thread_time()
            helper.hint_first_entry(text)
            times.append(time.thread_time() - t0)
        return min(times)

    def test_the_cut_is_linear_on_every_shape(self):
        for shape in self.SHAPES:
            small, large = self.best(shape(8000)), self.best(shape(32000))
            self.assertLess(large, 8 * small + 0.002, shape(16)[:16])

    ABSORBED_SHAPES = [lambda n: "," * n, lambda n: ",a" * (n // 2), lambda n: ",a=" * (n // 3),
                       lambda n: ",a=b" * (n // 4), lambda n: "," + "a" * n, lambda n: ",a=" + "b" * n,
                       lambda n: ",a=b:" + "\x00" * n, lambda n: ",a=b:/" + "\x1f" * n, lambda n: ",a=b:" * (n // 5)]

    def test_the_absorbed_test_is_linear_on_every_shape(self):
        def best(text):
            times = []
            for _ in range(5):
                t0 = time.thread_time()
                helper.absorbed_attribute(text)
                times.append(time.thread_time() - t0)
            return min(times)
        for shape in self.ABSORBED_SHAPES:
            small, large = best(shape(8000)), best(shape(32000))
            self.assertLess(large, 8 * small + 0.002, shape(16)[:16])



class EpgStatusTest(unittest.TestCase):
    """What the shipping `epg` verb answers and writes when a shell loaded
    before the one-label rule hands it such a host with origin `playlist`:
    refused before any lookup, and the status -- the reply and the 0600
    epg-status.json -- names the host no more than the refusal does. Its
    `sourceHost` was the username of a URL a space in its userinfo cut
    (D-SINK-34's class). The playlist's own host keeps its name."""

    def test_a_refused_host_of_one_label_is_not_the_status_host(self):
        got = []
        for url, home in (("http://qqqqqq:/", "prov.test"), ("http://qqqqqq:12/x.xml", "prov.test"),
                          ("http://tvbox:9981/xmltv", "tvbox")):
            with tempfile.TemporaryDirectory() as cache:
                patch = provenance("playlist", home)
                out, err = io.StringIO(), io.StringIO()
                try:
                    with Resolver() as resolver, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        helper.main(["epg", "--url", url, "--cache-dir", cache, "--timeout", "1"])
                finally:
                    patch.stop()
                reply = json.loads(out.getvalue().strip().splitlines()[-1])
                status = json.loads(pathlib.Path(cache, "epg-status.json").read_text(encoding="utf-8"))
                got.append((reply["error"]["code"], reply["sourceHost"], status["sourceHost"], resolver.lookups,
                            [s for s in SECRETS if s in json.dumps(reply) + json.dumps(status) + err.getvalue()]))
        self.assertEqual(got, [("local_address", "", "", [], []), ("local_address", "", "", [], []),
                               ("network", "tvbox", "tvbox", ["tvbox"], [])])


if __name__ == "__main__":
    unittest.main()
