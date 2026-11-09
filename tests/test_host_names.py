"""D-SINK-86 (the owner, 2026-11-08): what no host NAME may hold.

A host name that holds `@`, `%`, `;`, `=`, `&`, a second `:` (one port is
fine), whitespace, or an invisible format character (Unicode category Cf)
is refused. Two layers carry the rule:

1. The source validator, in both mirrors (validate_source_url,
   Model.validateSourceUrl), over the shared source-urls fixture, which
   tests/test_source.py and tests/Model.test.js both run.
2. The helper's connection layer, before any name lookup, on every hop:
   resolve_within (the one call into the resolver), bounded_create_connection
   (every connection's socket), check_proxied (a proxied request's target),
   bounded_handlers' per-request connection class and both redirect
   handlers' redirect_request, which judge the host AS THE REQUEST OBJECT
   HOLDS IT: urllib.request.Request percent-decodes its host, so
   `http://u%40evil.test/` is a request for `u@evil.test`, and http.client
   then splits the port off at the LAST colon, so `user:pass@host` is a
   lookup of `user:pass@host` -- the userinfo, sent to the resolver.

How this module observes it: the resolver is the sink, so every lookup here
runs under SocketResolver, test_provider_hosts' Resolver recording each host
as CPython's socket hands it to the C resolver -- a str host through the
idna codec (D-SINK-88: nameprep folds `user<U+FF1B>sid.test` to
`user;sid.test`, so recording the str the helper passed was more forgiving
than the real thing, rule 10) -- which answers a numeric one and refuses
every name. "Never looked up" means the recorder saw no call. Nothing leaves
the machine. An IPv6 literal keeps its colons and its zone's `%`; the
controls below are looked up exactly as before.

D-SINK-88 (2026-11-08): a name that is not ASCII is judged again in its NFKC
form, the fold the socket's idna codec applies; PredicateTest holds every
code point to the codec itself, and the shared source-urls fixture carries
every code point the fold is for.
"""
import functools
import io
import json
import pathlib
import stringprep
import unicodedata
import unittest
import urllib.parse
import urllib.request
from encodings import idna as idna_codec

from helper_loader import load_helper
# Helpers alone, no test case: nothing of that module runs here.
from test_provider_hosts import Resolver, RedirectingServer, provenance

helper = load_helper()

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "source-urls.json"
SECRET = "qqqqqq"
FORMAT = frozenset(c for c in range(0x110000) if unicodedata.category(chr(c)) == "Cf")
REFUSED_CHARS = frozenset(map(ord, "@%;=&:")) | frozenset(map(ord, helper.URL_SPACE_CHARS)) | FORMAT

# Hosts as a connection is handed them (http.client has split the port off
# at the last colon and taken a literal's brackets off), each holding one
# thing the rule refuses. The last is an IPv6 literal whose zone is no zone:
# the literal's exemption is not a way past the rule.
NAMES = [
    "u@evil.test", SECRET + "@evil.test", "u:" + SECRET + "@evil.test",
    "evil.test;sid=" + SECRET, "evil.test=" + SECRET, "evil.test&p=" + SECRET, "h%40evil.test",
    "evil.test:80", "h" + chr(0x20) + "evil.test", "h" + chr(0x09) + "evil.test", "h" + chr(0x3000) + "evil.test",
    "h" + chr(0xAD) + "evil.test", "h" + chr(0x200E) + "evil.test", "h" + chr(0x202E) + "evil.test",
    "h" + chr(0xFEFF) + "evil.test", "h" + chr(0xE0041) + "evil.test", "fe80::1%a@evil.test",
    # One label as well: the rule is asked before D-SINK-83's one-label
    # test, so the refusal is this rule's whatever the policy.
    "u:" + SECRET + "@evil",
    # D-SINK-88: names whose code points pass and whose NFKC form, which the
    # socket's idna codec hands the resolver, does not: `;`, `%40`, a space,
    # `@` and `:`.
    "evil" + chr(0xFE54) + SECRET + ".test", "evil" + chr(0xFF05) + "40" + SECRET + ".test",
    "evil" + chr(0xA8) + SECRET + ".test", "u" + chr(0xFF20) + "evil.test", "u" + chr(0xFF1A) + SECRET + ".evil.test",
]


class SocketResolver(Resolver):
    """Resolver, recording the host as CPython's socket hands it on: a str
    host is encoded with the idna codec before the C resolver sees it
    (socketmodule.c's getaddrinfo), raising UnicodeError as the real call
    does when the codec refuses it, so a name nameprep folds is recorded as
    the name looked up, not as the str the helper passed."""

    def getaddrinfo(self, host, port, *args, **kwargs):
        if isinstance(host, str):
            host = host.encode("idna")
        return super().getaddrinfo(host, port, *args, **kwargs)


def socket_form(name):
    """What the socket would hand the resolver for `name`, or None when the
    idna codec refuses it (then nothing is looked up)."""
    try:
        return name.encode("idna").decode("ascii")
    except UnicodeError:
        return None


def kept_by_nameprep(ch):
    """Does nameprep leave this one code point as it is? nameprep is B.1
    (mapped to nothing), B.2 (case folding) and NFKC under Unicode 3.2
    (encodings/idna.py); when B.1 does not hold it and B.3 and NFKC leave
    it, B.2 leaves it too (B.2 is B.3 then NFKC, then B.3 and NFKC again
    where those differ). Read through the codec module's own tables. A code
    point it keeps reaches the encoding as itself and punycode adds only
    letters, digits and `-`, so only the others need the codec's answer."""
    return (not stringprep.in_table_b1(ch) and stringprep.map_table_b3(ch) == ch
            and idna_codec.unicodedata.normalize("NFKC", ch) == ch)


@functools.lru_cache(maxsize=None)
def codec_survey():
    """One pass over every code point X, with the name `user<X>sid.test`:
    -> (folds, missed). `folds` maps each X outside REFUSED_CHARS whose name
    the socket's idna codec hands the resolver holding one of REFUSED_CHARS
    to that name: what D-SINK-88 is for. `missed` lists each X whose name
    host_name_refused lets through while the codec hands it on holding one:
    what D-SINK-88 must leave empty. An ASCII name is asked of the codec
    like any other; a code point nameprep keeps (kept_by_nameprep) adds no
    ASCII, so it alone is not."""
    folds, missed = {}, []
    for c in range(0x110000):
        ch = chr(c)
        if c >= 0x80 and kept_by_nameprep(ch):
            continue
        name = "user" + ch + "sid.test"
        sent = socket_form(name)
        if sent is None or not REFUSED_CHARS.intersection(map(ord, sent)):
            continue
        if c not in REFUSED_CHARS:
            folds[c] = sent
        if not helper.host_name_refused(name):
            missed.append("U+%04X -> %s" % (c, ascii(sent)))
    return folds, missed


def urlsplit_accepts(url):
    try:
        return urllib.parse.urlsplit(url).hostname is not None
    except ValueError:
        return False


def attempt(fn):
    """-> (code, message) of the HelperError fn raises, (class name, text)
    of any other exception, ("ok", "") when it returns. Never raises, so a
    tree without the rule fails these tests rather than erroring out of them."""
    try:
        fn()
    except helper.HelperError as error:
        return error.code, error.message
    except Exception as error:      # the old tree's gaierror, URLError, InvalidURL
        return type(error).__name__, str(error)
    return "ok", ""


def refusal():
    return getattr(helper, "HOST_NAME_REFUSAL", "<no HOST_NAME_REFUSAL>")


def policies():
    """A fresh policy of each kind (a policy counts its hops), and none."""
    P = helper.DestinationPolicy
    return [None, P("playlist", "user"), P("EPG", "playlist", "prov.test"), P.for_logos()]


class PredicateTest(unittest.TestCase):
    """host_name_refused, the one predicate both layers call."""

    def test_the_format_table_is_unicodes_format_category(self):
        """HOST_FORMAT_RANGES is Cf, code point by code point, as the
        installed Python's unicodedata has it (Unicode 16.0 on 3.14; node 26's
        17.0 has the same 170). The table is explicit because the model
        mirrors it and V4 is not node: if a Python update moves Cf, this goes
        red, and both mirrors' tables change together."""
        ranges = getattr(helper, "HOST_FORMAT_RANGES", ())
        table = {c for lo, hi in ranges for c in range(lo, hi + 1)}
        self.assertEqual(([hex(c) for c in sorted(table ^ FORMAT)][:8], len(ranges)), ([], 21),
                         "update HOST_FORMAT_RANGES in bin/helper/02-sources.py and model/sources.mjs together")

    def test_every_code_point_is_refused_in_a_name_exactly_when_the_rule_says(self):
        """Every code point of the whole range, inside a name and inside a
        name with its port: refused exactly for the five characters, a colon
        past the port's, the reader's whitespace (URL_SPACE_CHARS) and Cf --
        or, D-SINK-88, for a code point whose NFKC form holds one of them."""
        predicate = getattr(helper, "host_name_refused", None)
        self.assertIsNotNone(predicate)
        folds = {c for c in range(0x80, 0x110000)
                 if REFUSED_CHARS.intersection(map(ord, unicodedata.normalize("NFKC", chr(c))))}
        for with_port, form in ((False, "h%s.test"), (True, "h%s.test:8080")):
            wrong = [hex(c) for c in range(0x110000)
                     if predicate(form % chr(c), with_port) != (c in REFUSED_CHARS or c in folds)]
            self.assertEqual(wrong[:8], [], "with_port=%s" % with_port)

    def test_no_name_it_lets_through_reaches_the_resolver_as_one_it_refuses(self):
        """D-SINK-88, against the codec itself: for every code point X, if
        host_name_refused lets `user<X>sid.test` through, the name the
        socket's idna codec hands the resolver holds none of REFUSED_CHARS.
        Red before the fold: 68 code points (63 that urlsplit also accepts,
        and the five that fold to `@` or `:`)."""
        folds, missed = codec_survey()
        self.assertGreaterEqual(len(folds), 68, "the codec's folds were not found")
        self.assertEqual((len(missed), missed[:8]), (0, []))

    def test_the_shared_fixture_holds_every_code_point_the_fold_is_for(self):
        """Both validators run tests/fixtures/source-urls.json, so the fold's
        vectors there are the node suite's oracle too: one refused vector
        for each code point codec_survey finds, so the fixture cannot be
        trimmed to green."""
        cases = [c for c in json.loads(FIXTURE.read_text(encoding="utf-8"))
                 if str(c.get("note", "")).startswith("D-SINK-88")]
        listed = sorted(ord(c["input"][len("http://user")]) for c in cases if not c["ok"] and c["code"] == "invalid")
        targets = codec_survey()[0]
        accepted = [hex(c) for c in targets if urlsplit_accepts("http://user" + chr(c) + "sid.test/x")]
        self.assertEqual((listed, len(accepted)), (sorted(targets), 63))

    def test_one_port_is_fine_and_a_literal_keeps_its_colons(self):
        predicate = getattr(helper, "host_name_refused", lambda *_: "<missing>")
        allowed = [("h.test", False), ("h.test:8080", True), ("h.test:", True), ("127.0.0.1", False),
                   ("127.1", False), ("::1", False), ("2001:db8::1", False), ("fe80::1%eth0", False),
                   ("fe80::1%25eth0", False), ("::ffff:192.0.2.1", False), ("[::1]", False), ("[::1]", True),
                   ("[::1]:8080", True), ("[fe80::1%eth0]:8080", True), ("[fe80::1%25eth0]:443", True),
                   ("b" + chr(0xFC) + "cher.test", False), ("xn--bcher-kva.test:80", True), ("", False)]
        refused = [("h.test:8080", False), ("a:b:8080", True), ("[::1]:80:90", True),
                   ("[::1]:8080@evil.test", True), ("[evil.test]:80@x", True),
                   # A bare IPv6 address has no port to tell from its colons.
                   ("::1", True),
                   ("fe80::1%a@b", False), ("fe80::1%", False), ("fe80::1%a;b", False), ("[fe80::1%a;b]:80", True),
                   ("[fe80::1%" + chr(0xAD) + "]", False), ("[zz::1]:80:81", True),
                   # D-SINK-88: a colon the fold makes is the name's, never
                   # the port's one: http.client splits at an ASCII colon.
                   ("h" + chr(0xFF1A) + "8080", True), ("h.test" + chr(0xFE55) + "80", True),
                   ("h" + chr(0xFF1B) + "x.test:8080", True)]
        self.assertEqual([(ascii(t), p, predicate(t, p)) for t, p in allowed + refused],
                         [(ascii(t), p, False) for t, p in allowed] + [(ascii(t), p, True) for t, p in refused])


class ConnectionTest(unittest.TestCase):
    """The places the helper turns a host into a lookup, each called."""

    def check_refused(self, got):
        """got: [(label, code, message, lookups)] -> all the fixed refusal,
        none looked up, none naming the host."""
        want = [(label, "bad_url", refusal(), []) for label, *_ in got]
        self.assertEqual(got, want, "%d of %d differ" % (sum(1 for g, w in zip(got, want) if g != w), len(got)))
        for label, _, message, _ in got:
            for leak in ("evil", SECRET):
                self.assertNotIn(leak, message, label)

    def test_resolve_within_never_asks_the_resolver_about_such_a_name(self):
        got = []
        for name in NAMES:
            with SocketResolver() as resolver:
                code, message = attempt(lambda: helper.resolve_within(name, 80, 1.0))
            got.append((ascii(name), code, message, resolver.lookups))
        self.check_refused(got)

    def test_bounded_create_connection_refuses_before_its_lookup_on_every_hop(self):
        """Any policy or none, the first hop or a later one, a direct
        connection or one to the user's proxy: the rule is asked first."""
        got = []
        for name in NAMES:
            for proxied in (False, True):
                for first in (True, False):
                    for policy in policies():
                        with SocketResolver() as resolver:
                            code, message = attempt(lambda: helper.bounded_create_connection(
                                (name, 80), 1.0, policy=policy, first=first, proxied=proxied))
                        label = (ascii(name), proxied, first, policy.label if policy else None,
                                 policy.origin if policy else None)
                        got.append((label, code, message, resolver.lookups))
        self.check_refused(got)

    def test_check_proxied_refuses_the_target_before_its_lookup(self):
        got = []
        for name in NAMES:
            for first in (True, False):
                for policy in policies()[1:]:
                    with SocketResolver() as resolver:
                        code, message = attempt(lambda: policy.check_proxied(name, 80, 1.0, first))
                    got.append(((ascii(name), first, policy.label, policy.origin), code, message, resolver.lookups))
        self.check_refused(got)

    def test_every_hops_request_is_judged_as_it_holds_its_host(self):
        """bounded_handlers' handlers, called with a request whose host
        urllib percent-decoded: refused before the connection object exists,
        so neither the resolver nor http.client's own host check (whose
        InvalidURL quotes the host, and for `user:pass@host` the password as
        a port) ever sees it."""
        got = []
        for scheme, handler in zip(("http", "https"), helper.bounded_handlers(None, helper.DestinationPolicy("playlist", "user"))):
            for authority in ("u%40evil.test", "u%3A" + SECRET + "%40evil.test", "h%20evil.test",
                              "evil.test%3A80%3A80", "evil.test%3Bsid=" + SECRET, "h%C2%ADevil.test",
                              "evil%EF%BC%9B" + SECRET + ".test", "evil%C2%A8" + SECRET + ".test"):
                request = urllib.request.Request("%s://%s/x" % (scheme, authority))
                request.timeout = 1.0
                opener = getattr(handler, scheme + "_open")
                with SocketResolver() as resolver:
                    code, message = attempt(lambda: opener(request))
                got.append(((scheme, authority), code, message, resolver.lookups))
        self.check_refused(got)

    def test_both_redirect_handlers_judge_the_new_request_as_it_holds_its_host(self):
        """make_opener's handler (playlist, guide, probe) and logo_opener's,
        each called with a Location whose decoded host the rule refuses: the
        new request is never handed back to be opened. The logo handler's
        own `@` test reads the raw netloc, so `%40` passed it."""
        got = []
        openers = (("make_opener", helper.make_opener("playlist", "h.test", helper.DestinationPolicy("playlist", "user"))),
                   ("logo_opener", helper.logo_opener("cdn.test")))
        for which, opener in openers:
            handler = [h for h in opener.handlers if isinstance(h, urllib.request.HTTPRedirectHandler)][0]
            for newurl in ("https://u%40evil.test/x", "https://evil.test%3A80%3A80/x", "https://h%C2%ADevil.test/x",
                           "https://evil.test;sid=" + SECRET + "/x", "https://u%3A" + SECRET + "%40evil.test/x",
                           "https://evil%EF%BC%9B" + SECRET + ".test/x", "https://evil%EF%BC%85" + "40" + SECRET + ".test/x"):
                request = urllib.request.Request("https://cdn.test/a.png")
                with SocketResolver() as resolver:
                    code, message = attempt(lambda: handler.redirect_request(request, io.BytesIO(), 302, "Found", {}, newurl))
                got.append(((which, newurl), code, message, resolver.lookups))
        self.check_refused(got)

    def test_the_controls_are_still_looked_up(self):
        """A dotted name, a name that is not ASCII (looked up as its `xn--`
        form, which is what the socket hands on), one whose fold is a full
        stop and a letter, a numeric IPv4 and IPv6 literal, and a scoped
        one: each reaches the resolver as before (the stand-in answers the
        numeric ones and refuses the names)."""
        cases = (("h.test", "h.test"), ("b" + chr(0xFC) + "cher.test", "xn--bcher-kva.test"),
                 ("xn--bcher-kva.test", "xn--bcher-kva.test"), ("h" + chr(0xFF0E) + "test", "h.test"),
                 ("h" + chr(0xFF21) + ".test", "ha.test"), ("127.0.0.1", "127.0.0.1"), ("::1", "::1"),
                 ("fe80::1%1", "fe80::1%1"))
        got = []
        for name, _ in cases:
            with SocketResolver() as resolver:
                code, _ = attempt(lambda: helper.resolve_within(name, 80, 1.0))
            got.append((ascii(name), code != "bad_url", resolver.lookups))
        self.assertEqual(got, [(ascii(n), True, [sent]) for n, sent in cases])


class RedirectTest(unittest.TestCase):
    """The shipping fetch end to end: a source the user typed on this
    machine (whose first hop may be local), answered 302. The first hop is
    made; the second, whose host the rule refuses, is never looked up, and
    the refusal is the fixed sentence."""

    LOCATIONS = [
        "http://u%40evil.test/x",
        "http://" + SECRET + "@evil.test/x",
        "http://u%3A" + SECRET + "%40evil.test/x",
        "http://evil.test%3Bsid=" + SECRET + "/x",
        "http://evil.test;sid=" + SECRET + "/x",
        "http://evil.test=" + SECRET + "/x",
        "http://evil.test&p=" + SECRET + "/x",
        "http://evil.test:80:80/x",
        "http://evil.test%3A80%3A80/x",
        "http://h%20evil.test/x",
        "http://h%C2%ADevil.test/x",
        "http://h%E2%80%AEevil.test/x",
        # D-SINK-88: folded to `;` by the socket's idna codec.
        "http://evil%EF%BC%9B" + SECRET + ".test/x",
    ]

    def follow(self, location):
        server = RedirectingServer(location)
        self.addCleanup(server.close)
        patch = provenance("user")
        try:
            with SocketResolver() as resolver:
                code, message = attempt(lambda: helper.fetch_bytes("http://127.0.0.1:%d/list.m3u" % server.port, 2.0, "playlist"))
        finally:
            patch.stop()
        return code, message, server.seen, resolver.lookups

    def test_a_refused_target_is_never_looked_up_and_never_named(self):
        got = [(location,) + self.follow(location) for location in self.LOCATIONS]
        want = [(location, "bad_url", refusal(), ["/list.m3u"], ["127.0.0.1"]) for location in self.LOCATIONS]
        self.assertEqual(got, want, "%d of %d differ" % (sum(1 for g, w in zip(got, want) if g != w), len(got)))
        for location, _, message, _, _ in got:
            for leak in ("evil", SECRET):
                self.assertNotIn(leak, message, location)

    def test_one_port_an_ipv6_literal_and_a_name_that_is_not_ascii_are_still_followed(self):
        cases = (("http://ctl.test:8080/x", "ctl.test", "network"),
                 ("http://[::1]:1/x", "::1", "local_address"),
                 ("http://b%C3%BCcher.test/x", "xn--bcher-kva.test", "network"))
        got = []
        for location, _, _ in cases:
            code, _, _, lookups = self.follow(location)
            got.append((location, code, lookups))
        self.assertEqual(got, [(location, code, ["127.0.0.1", lookup]) for location, lookup, code in cases])


class LogoTest(unittest.TestCase):
    """A logo's first hop: fetch_logo's own checks read the raw netloc, so a
    host that holds `%40` or a raw `;` passed them and reached the lookup."""

    def test_a_logo_whose_host_the_rule_refuses_is_never_looked_up(self):
        got = []
        for url in ("https://u%40evil.test/a.png", "https://evil.test;sid=" + SECRET + "/a.png",
                    "https://evil.test%3Bsid=" + SECRET + "/a.png", "https://h%C2%ADevil.test/a.png",
                    "https://evil.test%3A443%3A443/a.png", "https://evil%EF%BC%9B" + SECRET + ".test/a.png"):
            patch = provenance("")
            try:
                with SocketResolver() as resolver:
                    code, message = attempt(lambda: helper.fetch_logo(url, 1.0, 2.0))
            finally:
                patch.stop()
            got.append((url, code, message, resolver.lookups))
        want = [(url, "bad_url", refusal(), []) for url, *_ in got]
        self.assertEqual(got, want, "%d of %d differ" % (sum(1 for g, w in zip(got, want) if g != w), len(got)))


if __name__ == "__main__":
    unittest.main()
