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

D-SINK-88 (2026-11-08): a name that is not ASCII is judged again in its NFKD
form. The socket's idna codec runs nameprep -- stringprep's B.1 removed, B.2
case folding, then NFKC under Unicode 3.2 -- and NFKC alone, which this
judged first, misses names where B.2 keeps a `=` from composing away
(`<U+FF1D><U+0345><U+0338>`: B.2 maps U+0345 to the letter U+03B9). NFKD
never composes. PredicateTest holds the argument over every code point (B.1,
B.2 and Unicode 3.2 add no refused character the current NFKD lacks, and `=`
is the one refused character a composition can take), holds every
one-code-point name and every sequence of the class the review found to the
codec itself, and holds the shared source-urls fixture to a vector for every
code point the codec folds.

D-SINK-92 (2026-11-09): and `[` and `]` are refused in a name, which no DNS
name holds. A bracketed IPv6 literal is set aside only in a host[:port] as a
request holds it, and only when nothing or a port's colon follows its `]`;
a host a connection is handed has had a literal's brackets taken off, so a
bracket there is refused whatever surrounds it. Before, `[::1]x.test` -- a
redirect to `http://%5B::1%5Dx.test/`, which urllib percent-decodes and
http.client keeps whole -- passed every layer and reached the resolver
holding brackets and colons, and a fullwidth bracket passed the fold, which
the codec hands on as `[` (the review of 6371c67). REFUSED_CHARS holds both,
so every survey below counts the bracket folds too.
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
REFUSED_CHARS = frozenset(map(ord, "@%;=&:[]")) | frozenset(map(ord, helper.URL_SPACE_CHARS)) | FORMAT

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
    # D-SINK-88: names whose code points pass and whose form as the socket's
    # idna codec hands it to the resolver does not: `;`, `%40`, a space, `@`
    # and `:`.
    "evil" + chr(0xFE54) + SECRET + ".test", "evil" + chr(0xFF05) + "40" + SECRET + ".test",
    "evil" + chr(0xA8) + SECRET + ".test", "u" + chr(0xFF20) + "evil.test", "u" + chr(0xFF1A) + SECRET + ".evil.test",
    # And a sequence the codec hands on holding `=` while NFKC alone does
    # not (the review of 95f1bb9): the socket would look up `u=...`.
    "u" + chr(0xFF1D) + chr(0x345) + chr(0x338) + SECRET + ".evil.test",
    # D-SINK-92: a bracket, which a connection is never handed in a literal
    # (http.client takes a literal's off), so the provider's: text after a
    # literal's `]` (a request for `http://%5B::1%5Dx.test/` is a connection
    # to `[::1]x.test`, brackets and colons and all), a zone carrying a
    # name, a bracket elsewhere, a literal still in its brackets, and a
    # fullwidth bracket the codec hands on as `[`.
    "[::1]" + SECRET + ".evil.test", "[fe80::1%eth0]" + SECRET + ".evil.test", "[fe80::1%" + SECRET + "]evil.test",
    "evil.test[" + SECRET + "]", SECRET + "].evil.test", "[::1]", "u" + chr(0xFF3B) + SECRET + ".evil.test",
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


# The two one-code-point names the survey asks of the codec: inside a
# left-to-right label, and as a label of its own, which is the only form a
# right-to-left code point passes nameprep's bidi check in (U+FDFA and U+FDFB
# fold to Arabic words separated by spaces).
SURVEY_FORMS = ("user%ssid.test", "%s.test")


@functools.lru_cache(maxsize=None)
def codec_survey():
    """One pass over every code point X, with each of SURVEY_FORMS:
    -> (folds, missed). `folds` maps each X outside REFUSED_CHARS whose name,
    in either form, the socket's idna codec hands the resolver holding one
    of REFUSED_CHARS to the first such (form, name sent): what D-SINK-88 is
    for. `missed` lists each X and form whose name host_name_refused lets
    through while the codec hands it on holding one: what D-SINK-88 must
    leave empty. An ASCII name is asked of the codec like any other; a code
    point nameprep keeps (kept_by_nameprep) adds no ASCII, so it alone is
    not."""
    folds, missed = {}, []
    for c in range(0x110000):
        ch = chr(c)
        if c >= 0x80 and kept_by_nameprep(ch):
            continue
        for form in SURVEY_FORMS:
            name = form % ch
            sent = socket_form(name)
            if sent is None or not REFUSED_CHARS.intersection(map(ord, sent)):
                continue
            if c not in REFUSED_CHARS:
                folds.setdefault(c, (form, sent))
            if not helper.host_name_refused(name):
                missed.append("U+%04X %s -> %s" % (c, form, ascii(sent)))
    return folds, missed


def nameprep_map(ch):
    """nameprep's mapping of one code point: nothing for B.1, map_table_b2
    otherwise. map_table_b2 is B.3, then NFKC and B.3 again where they
    change it, so a code point B.3 and Unicode 3.2's NFKC both leave is its
    own mapping, and the slow table is asked only of the others."""
    if stringprep.in_table_b1(ch):
        return ""
    if stringprep.map_table_b3(ch) == ch and idna_codec.unicodedata.normalize("NFKC", ch) == ch:
        return ch
    return stringprep.map_table_b2(ch)


@functools.lru_cache(maxsize=None)
def sequence_survey():
    """The class the review of 95f1bb9 found, widened: every code point the
    codec reads as `=` (or `=` and more), each followed by U+0338, with every
    combining mark and every code point nameprep maps (MARKS) placed before
    it, after it, before U+0345, or after U+0345 -- the orders in which B.2's
    letter for U+0345, or a B.1 removal, decides whether `=` composes away.
    `=` is the one refused character a composition can take (PredicateTest
    holds that), so it is the one this class needs. -> (equals, marks,
    hidden, missed): `hidden` counts the names the codec hands on holding a
    refused character while their NFKC holds none -- the names an NFKC fold
    lets through, so the class is real -- and `missed` lists those of any
    kind host_name_refused lets through. The codec is asked only of a name
    one of the two folds lets through: one both refuse is no question."""
    u32 = idna_codec.unicodedata
    equals, marks = [], []
    for c in range(0x80, 0x110000):
        if 0xD800 <= c <= 0xDFFF:
            continue
        ch = chr(c)
        mapped = nameprep_map(ch)
        if "=" in u32.normalize("NFKC", mapped):
            equals.append(ch)
        if mapped != ch or unicodedata.combining(ch):
            marks.append(ch)
    over, iota = chr(0x338), chr(0x345)
    hidden, missed = 0, []
    for e in equals:
        for m in marks:
            for middle in (m + over, over + m, m + iota + over, iota + m + over):
                name = "h" + e + middle + ".test"
                clean = REFUSED_CHARS.isdisjoint(map(ord, unicodedata.normalize("NFKC", name)))
                refused = helper.host_name_refused(name)
                if refused and not clean:
                    continue
                form = socket_form(name)
                if form is None or REFUSED_CHARS.isdisjoint(map(ord, form)):
                    continue
                hidden += clean
                if not refused:
                    missed.append(ascii(name) + " -> " + form)
    return len(equals), len(marks), hidden, missed


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
        or, D-SINK-88, for a code point whose NFKD form holds one of them.
        D-SINK-92 adds the two brackets, and with them four folds: U+FF3B
        and U+FF3D, which the codec folds, and U+FE47 and U+FE48, which only
        the running Unicode does."""
        predicate = getattr(helper, "host_name_refused", None)
        self.assertIsNotNone(predicate)
        folds = {c for c in range(0x80, 0x110000)
                 if REFUSED_CHARS.intersection(map(ord, unicodedata.normalize("NFKD", chr(c))))}
        self.assertEqual(len(folds - REFUSED_CHARS), 77)
        for with_port, form in ((False, "h%s.test"), (True, "h%s.test:8080")):
            wrong = [hex(c) for c in range(0x110000)
                     if predicate(form % chr(c), with_port) != (c in REFUSED_CHARS or c in folds)]
            self.assertEqual(wrong[:8], [], "with_port=%s" % with_port)

    def test_nameprep_adds_no_refused_character_the_decomposed_form_lacks(self):
        """Why NFKD is enough, held over every code point rather than
        assumed. nameprep's output is NFKC (Unicode 3.2) of each code point's
        mapping -- nothing for B.1, map_table_b2 otherwise -- and an NFKC
        holds no refused character its NFKD lacks, because composition makes
        only primary composites and no refused character is one (U+2000 and
        U+2001 decompose to one code point, which composition never undoes).
        So it is enough that, for every code point, the refused characters of
        its mapping's Unicode 3.2 NFKD are among those of the code point and
        of its current NFKD. And `=` is the only refused character that is
        the first half of a pair a composition joins (U+2260), which is why
        sequence_survey needs `=` alone."""
        u32 = idna_codec.unicodedata
        bad = []
        for c in range(0x110000):
            ch = chr(c)
            if 0xD800 <= c <= 0xDFFF or stringprep.in_table_b1(ch):
                continue
            if u32.normalize("NFKD", ch) == ch and stringprep.map_table_b3(ch) == ch:
                continue        # B.2 leaves it, and it decomposes to itself
            sent = REFUSED_CHARS.intersection(map(ord, u32.normalize("NFKD", stringprep.map_table_b2(ch))))
            if not sent <= REFUSED_CHARS.intersection(map(ord, ch + unicodedata.normalize("NFKD", ch))):
                bad.append(hex(c))
        composites, pairs = [], []
        for db in (unicodedata, u32):
            for c in range(0x110000):
                mapping = db.decomposition(chr(c)) if not 0xD800 <= c <= 0xDFFF else ""
                if not mapping or mapping.startswith("<"):
                    continue
                parts = [int(x, 16) for x in mapping.split()]
                if c in REFUSED_CHARS and len(parts) > 1:
                    composites.append(hex(c))
                if len(parts) == 2 and parts[0] in REFUSED_CHARS:
                    pairs.append((hex(c), chr(parts[0])))
        self.assertEqual((bad[:8], composites, sorted(set(pairs))), ([], [], [("0x2260", "=")]))

    def test_no_one_code_point_name_it_lets_through_reaches_the_resolver_as_one_it_refuses(self):
        """D-SINK-88, against the codec itself: for every code point X, if
        host_name_refused lets `user<X>sid.test` or `<X>.test` through, the
        name the socket's idna codec hands the resolver holds none of
        REFUSED_CHARS. Red before the fold: 68 code points in the first form
        (63 that urlsplit also accepts, and the five that fold to `@` or
        `:`), and U+FDFA and U+FDFB in the second, 70 in all; and since
        D-SINK-92, U+FF3B and U+FF3D, which fold to a bracket, 72."""
        folds, missed = codec_survey()
        self.assertEqual(len(folds), 72, "the codec's folds were not found")
        self.assertEqual((len(missed), missed[:8]), (0, []))

    def test_no_sequence_of_the_reviews_class_reaches_the_resolver_holding_a_refused_character(self):
        """D-SINK-88's sequences, against the codec itself: a code point the
        codec reads as `=`, U+0338, and a mark or a mapped code point around
        it (sequence_survey). Red on the NFKC fold: the four
        `h<X><U+0345><U+0338>.test` the review found, and longer ones built on
        U+0345."""
        equals, marks, hidden, missed = sequence_survey()
        self.assertEqual((equals, marks >= 2000), (7, True), "the survey's inputs were not found")
        self.assertGreaterEqual(hidden, 4, "the class NFKC alone lets through was not found")
        self.assertEqual((len(missed), missed[:8]), (0, []))

    def test_the_shared_fixture_holds_every_code_point_the_fold_is_for(self):
        """Both validators run tests/fixtures/source-urls.json, so the fold's
        vectors there are the node suite's oracle too: one refused vector
        for each code point codec_survey finds, in the form it found it in,
        so the fixture cannot be trimmed to green; and the sequence and
        U+2260 vectors besides."""
        cases = [c for c in json.loads(FIXTURE.read_text(encoding="utf-8"))
                 if str(c.get("note", "")).startswith("D-SINK-88") and not c["ok"] and c["code"] == "invalid"]
        listed = set(c["input"] for c in cases)
        targets = codec_survey()[0]
        wanted = {c: "http://" + (form % chr(c)) + "/x" for c, (form, _) in targets.items()}
        accepted = [hex(c) for c, url in wanted.items() if urlsplit_accepts(url)]
        extra = ["http://user" + chr(0xFF1D) + chr(0x345) + chr(0x338) + "sid.test/x",
                 "http://user" + chr(0x2260) + "sid.test/x", "http://user" + chr(0xFE13) + "sid.test/x",
                 "http://user" + chr(0xFE14) + "sid.test/x", "http://user" + chr(0xFE47) + "sid.test/x",
                 "http://user" + chr(0xFE48) + "sid.test/x"]
        self.assertEqual(([hex(c) for c, url in sorted(wanted.items()) if url not in listed],
                          [ascii(u) for u in extra if u not in listed], len(accepted)), ([], [], 67))

    def test_one_port_is_fine_and_a_literal_keeps_its_colons(self):
        predicate = getattr(helper, "host_name_refused", lambda *_: "<missing>")
        allowed = [("h.test", False), ("h.test:8080", True), ("h.test:", True), ("127.0.0.1", False),
                   ("127.1", False), ("::1", False), ("2001:db8::1", False), ("fe80::1%eth0", False),
                   ("fe80::1%25eth0", False), ("::ffff:192.0.2.1", False), ("[::1]", True),
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
                   ("h" + chr(0xFF1B) + "x.test:8080", True),
                   # The review of 95f1bb9: a sequence B.2 keeps `=` in, and
                   # U+2260, which NFKD reads as `=` and U+0338.
                   ("h" + chr(0xFF1D) + chr(0x345) + chr(0x338) + ".test", False),
                   ("h" + chr(0x207C) + chr(0x345) + chr(0x338) + ".test:80", True),
                   ("h" + chr(0x2260) + ".test", False),
                   # D-SINK-92: a bracket, except a leading literal's pair in
                   # a host[:port] followed by nothing or a port; with no
                   # port, any bracket (a connection is handed no literal's).
                   ("[::1]", False), ("[::1]x.test", True), ("[::1]x.test", False), ("[::1]x.test:80", True),
                   ("[fe80::1%eth0]x.test", True), ("[::1]:80]", True), ("h.test[x]", False), ("x].test", True),
                   ("[ab]x.test", True), ("[::1", True), ("h" + chr(0xFF3B) + "x.test", False),
                   ("h" + chr(0xFE48) + "x.test:80", True)]
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
                              "evil%EF%BC%9B" + SECRET + ".test", "evil%C2%A8" + SECRET + ".test",
                              # D-SINK-92: the decoded host holds brackets.
                              "%5B::1%5D" + SECRET + ".evil.test", "%5B%3A%3A1%5D" + SECRET + ".evil.test:8080",
                              "evil.test%5B" + SECRET + "%5D", "evil%EF%BC%BB" + SECRET + ".test"):
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
                           "https://evil%EF%BC%9B" + SECRET + ".test/x", "https://evil%EF%BC%85" + "40" + SECRET + ".test/x",
                           # D-SINK-92: the review of 6371c67's Locations.
                           "https://%5B::1%5D" + SECRET + ".evil.test/x",
                           "https://%5Bfe80::1%25" + SECRET + "%5Devil.test/x", "https://" + SECRET + "%5D.evil.test/x"):
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
        # D-SINK-92: brackets in the decoded host, which http.client keeps
        # whole unless the host both opens and ends with one (the review of
        # 6371c67), and a fullwidth bracket the codec folds to `[`.
        "http://%5B::1%5D" + SECRET + ".evil.test/x",
        "http://%5Bfe80::1%25" + SECRET + "%5Devil.test/x",
        "http://%5B::1%5D" + SECRET + ".evil.test:8080/x",
        "http://evil.test%5B" + SECRET + "%5D/x",
        "http://evil%EF%BC%BB" + SECRET + ".test/x",
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
                    "https://evil.test%3A443%3A443/a.png", "https://evil%EF%BC%9B" + SECRET + ".test/a.png",
                    # D-SINK-92: a decoded host holding brackets, which
                    # fetch_logo's own checks read past (they read the raw
                    # netloc, where `%5B` is no bracket and the name has a
                    # dot).
                    "https://%5B%3A%3A1%5D" + SECRET + ".evil.test/a.png",
                    "https://evil%EF%BC%BB" + SECRET + ".test/a.png"):
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
