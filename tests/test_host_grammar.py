"""D-SINK-115, D-SINK-116, D-SINK-117 (2026-11-16, round 5 of the security
review): how a source address's authority and host name are read.

Three rules, one reading per mirror (read_authority / Model.readAuthority),
both validators through it:

* D-SINK-115. Both validators accepted an address the helper's URL library
  refuses to read -- a code point whose compatibility form holds `/`, `?`,
  `#`, `@` or `:` anywhere in the authority, a `[` or `]` in the user
  information when the host is not a bracketed literal, a bracketed host
  that is no IPv6 address -- and every fetch then ended as an internal error
  quoting the authority. And the stored url is held to the length cap as
  well as the typed text, because lowering lengthens a host.
* D-SINK-116. A host name holding an invisible character beyond Cf: Unicode's
  default-ignorable code points and stringprep's B.1.
* D-SINK-117. A host name holding ASCII other than a letter, a digit, `-`, `.`
  or `_`, written or folded; and at the connection, a port that is not one to
  five ASCII digits up to 65535.

How this module observes it. tests/fixtures/host-grammar.json is the one
file both suites read: its tables are held here to Python's own Unicode data
and to urlsplit itself, and in tests/Model.test.js to node's; its vectors run
through both validators. DifferentialTest builds one corpus from the
fixture's atoms (the generator lives here only, so nothing is mirrored), runs
the helper in process, the model in node by one subprocess and a subset in
Qt's own engine (tests/test_proto_v4.run_qml), and holds them equal, and
holds every address both accept to what urllib reads. Nothing here looks a
name up: no fetch is made, and urllib.request.Request is only built.
"""
import json
import os
import pathlib
import random
import stringprep
import subprocess
import sys
import unicodedata
import unittest
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper
import test_proto_v4 as proto_v4

helper = load_helper()

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "host-grammar.json").read_text(encoding="ascii"))
CASEFOLD = json.loads((ROOT / "tests" / "fixtures" / "casefold-diff.json").read_text(encoding="utf-8"))
# D-SRC-12's code points, whose lowering node and CPython disagree on: an
# address holding one is compared by its verdict, not its spelling.
LOWERING_DIFF = frozenset(int(code[2:], 16) for code in CASEFOLD["diff"])
TABLES = FIXTURE["tables"]


def codes(hex_list):
    return {int(code, 16) for code in hex_list}


def expand(ranges):
    return {code for first, last in ranges for code in range(int(first, 16), int(last, 16) + 1)}


def helper_ranges(ranges):
    return {code for first, last in ranges for code in range(first, last + 1)}


class TablesTest(unittest.TestCase):
    """The fixture's tables, the helper's shipped copies, and Python's own
    Unicode data and urlsplit, held to one another."""

    def test_the_fixture_is_whole_and_ascii(self):
        raw = (ROOT / "tests" / "fixtures" / "host-grammar.json").read_bytes()
        self.assertTrue(raw.isascii())
        self.assertEqual((len(TABLES["delimiterFolds"]), len(TABLES["invisibleRanges"]), len(TABLES["asciiFolds"]),
                          len(TABLES["b1"])), (19, 26, 301, 27))
        kinds = {c.get("why") for c in FIXTURE["vectors"] if not c["ok"]}
        self.assertTrue({"fold_host", "fold_userinfo", "bracket", "literal", "host", "port_text", "port_range"} <= kinds)
        self.assertGreaterEqual(sum(1 for c in FIXTURE["vectors"] if c["ok"]), 10)
        self.assertGreaterEqual(sum(1 for c in FIXTURE["stateReaders"] if c["kept"]), 5)
        self.assertGreaterEqual(sum(1 for c in FIXTURE["stateReaders"] if not c["kept"]), 5)

    def test_the_invisible_table_is_cf_b1_and_the_default_ignorables(self):
        cf = {c for c in range(0x110000) if unicodedata.category(chr(c)) == "Cf"}
        b1 = {c for c in range(0x110000) if not 0xD800 <= c <= 0xDFFF and stringprep.in_table_b1(chr(c))}
        shipped = helper_ranges(getattr(helper, "HOST_INVISIBLE_RANGES", ()))
        self.assertEqual(codes(TABLES["b1"]), b1, "the fixture's B.1 is stringprep's")
        want = cf | b1 | expand(TABLES["defaultIgnorable"])
        self.assertEqual(([hex(c) for c in sorted(shipped ^ want)][:8], len(want)), ([], 4207))
        self.assertEqual(shipped, expand(TABLES["invisibleRanges"]))

    def test_the_delimiter_folds_are_what_urlsplit_refuses(self):
        """Over every code point: urlsplit refuses `http://a<X>b.test/`
        exactly when X is one of the fixture's folds or a bracket, and the
        folds are the code points whose NFKD holds `/`, `?`, `#`, `@` or `:`
        -- CPython's own check, normalized. The helper's shipped table is the
        fixture's."""
        folds = codes(TABLES["delimiterFolds"])
        refused = set()
        for c in range(0x110000):
            if 0xD800 <= c <= 0xDFFF:
                continue
            try:
                urllib.parse.urlsplit("http://a" + chr(c) + "b.test/")
            except ValueError:
                refused.add(c)
        nfkd = {c for c in range(0x80, 0x110000) if not 0xD800 <= c <= 0xDFFF
                and any(d in unicodedata.normalize("NFKD", chr(c)) for d in "/?#@:")}
        self.assertEqual((refused, nfkd), (folds | {0x5B, 0x5D}, folds))
        self.assertEqual({ord(ch) for ch in getattr(helper, "DELIMITER_FOLDS", ())}, folds)

    def test_the_ascii_a_host_name_may_hold_is_the_allowlist(self):
        allowed = set(TABLES["hostAscii"])
        got = [(chr(c), helper.host_name_refused("a%sb.test" % chr(c))) for c in range(0x80)]
        self.assertEqual([ch for ch, refused in got if not refused], sorted(allowed, key=ord))
        self.assertEqual(set(getattr(helper, "HOST_NAME_ASCII", ())), allowed)

    def test_every_ascii_fold_is_the_runtimes_and_is_refused(self):
        allowed = set(TABLES["hostAscii"])
        mine = {c for c in range(0x80, 0x110000) if not 0xD800 <= c <= 0xDFFF
                and any(ord(ch) < 0x80 and ch not in allowed for ch in unicodedata.normalize("NFKD", chr(c)))}
        self.assertEqual(mine, codes(TABLES["asciiFolds"]))
        accepted = [hex(c) for c in sorted(mine) if helper.validate_source_url("http://a%sb.test/" % chr(c))["ok"]]
        self.assertEqual(accepted, [])


class VectorTest(unittest.TestCase):
    """The fixture's vectors through the shipping validator and reader."""

    def test_every_vector_reads_as_the_fixture_says(self):
        wrong = []
        for case in FIXTURE["vectors"]:
            got = helper.validate_source_url(case["input"], case.get("origin", "form"))
            seen = (got["ok"], got["url"], got["host"]) if case["ok"] else (got["ok"], got["code"])
            want = (True, case["url"], case["host"]) if case["ok"] else (False, case["code"])
            if seen != want:
                wrong.append((ascii(case["input"][:60]), seen))
        self.assertEqual(wrong, [], "%d of %d vectors disagree" % (len(wrong), len(FIXTURE["vectors"])))

    def test_every_refusal_says_why_as_the_fixture_says(self):
        reader = getattr(helper, "read_authority", None)
        self.assertIsNotNone(reader)
        got = [(ascii(c["input"][:60]), reader(c["input"].split("://", 1)[1])["why"])
               for c in FIXTURE["vectors"] if "why" in c]
        self.assertEqual(got, [(ascii(c["input"][:60]), c["why"]) for c in FIXTURE["vectors"] if "why" in c])

    def test_no_refusal_names_the_address(self):
        for case in FIXTURE["vectors"]:
            if case["ok"]:
                continue
            message = helper.validate_source_url(case["input"])["message"]
            for leak in ("qqqqqq", "zzzzzz", "cdn", "epg", "://"):
                self.assertNotIn(leak, message, ascii(case["input"][:60]))

    def test_the_connection_layer_judges_a_host_and_its_port(self):
        """The critique's finding 2: the port after a bracketed literal, and
        after a name's colon, is one to five ASCII digits up to 65535."""
        got = [(ascii(c["host"]), c["withPort"], helper.host_name_refused(c["host"], c["withPort"]))
               for c in FIXTURE["connection"]]
        self.assertEqual(got, [(ascii(c["host"]), c["withPort"], c["refused"]) for c in FIXTURE["connection"]])

    def test_a_password_holding_a_fold_is_sent_as_that_character_when_escaped(self):
        """The critique's finding 4: the refusal's advice. Written as its own
        UTF-8 escape, the fullwidth colon is accepted and sent back as that
        character; `%3A` would send a plain colon, another password."""
        ok = helper.validate_source_url("http://u:p%EF%BC%9Aw@cdn.test/get.php")
        target, auth = helper.split_userinfo(ok["url"])
        self.assertEqual((ok["ok"], target, auth), (True, "http://cdn.test/get.php", "u:p" + chr(0xFF1A) + "w"))
        self.assertEqual(helper.split_userinfo("http://u:p%3Aw@cdn.test/get.php")[1], "u:p:w")
        self.assertFalse(helper.validate_source_url("http://u:p" + chr(0xFF1A) + "w@cdn.test/get.php")["ok"])


class StateReaderTest(unittest.TestCase):
    """The owner's decision of 2026-11-16: on the first load after the
    update, normalize_state drops a stored source whose address holds a
    newly refused shape and clears a kept source's guide URL holding one;
    every other source is kept as it was stored."""

    def test_each_stored_shape_is_dropped_or_kept_as_the_fixture_says(self):
        records = []
        for index, case in enumerate(FIXTURE["stateReaders"]):
            records.append({"key": "%08x" % (0xA0000000 + index), "url": case["url"], "epgUrl": case.get("epgUrl", ""),
                            "kind": "http", "label": "S%d" % index, "labelCustom": True, "origin": "cli",
                            "addedAt": 1, "lastUsed": 1, "fetchedAt": 0, "channelCount": 0, "groupCount": 0})
        state = helper.normalize_state({"version": 2, "cacheLayout": "sources", "sources": records})
        kept = {s["key"]: s for s in state["sources"]}
        got, want = [], []
        for index, case in enumerate(FIXTURE["stateReaders"]):
            record = kept.get("%08x" % (0xA0000000 + index))
            got.append((ascii(case["url"]), record is not None, record["url"] if record else "",
                        (record["epgUrl"] != "") if record else None))
            want.append((ascii(case["url"]), case["kept"], case["url"] if case["kept"] else "",
                         case.get("epgKept", False) if case["kept"] else None))
        self.assertEqual(got, want)


def corpus():
    """The differential's addresses: each seed's share of corpusSize built
    from the atoms (one optional insert, in the user information, the host,
    the port or the target), then every hand vector. Deterministic."""
    atoms = FIXTURE["atoms"]
    out = []
    for seed in FIXTURE["seeds"]:
        rnd = random.Random(seed)
        for _ in range(FIXTURE["corpusSize"] // len(FIXTURE["seeds"])):
            parts = {"userinfo": rnd.choice(atoms["userinfo"]), "port": rnd.choice(atoms["ports"]),
                     "target": rnd.choice(atoms["targets"])}
            if rnd.random() < 0.3:
                parts["host"] = rnd.choice(atoms["literals"])
            else:
                labels = [rnd.choice(atoms["labels"]) for _ in range(rnd.randint(1, 2))]
                parts["host"] = ".".join(labels) + "." + rnd.choice(atoms["tlds"])
            if rnd.random() < 0.7:
                where = rnd.choice(("userinfo", "host", "host", "port", "target"))
                text = parts[where]
                at = rnd.randint(0, len(text))
                parts[where] = text[:at] + rnd.choice(atoms["inserts"]) + text[at:]
            out.append(rnd.choice(atoms["schemes"]) + "://" + parts["userinfo"] + parts["host"] + parts["port"]
                       + parts["target"])
    out += [case["input"] for case in FIXTURE["vectors"]]
    return list(dict.fromkeys(out))


def verdict(result):
    return [result["ok"], result["code"], result["url"], result["host"]]


def helper_readings(urls):
    """[[form, cli, form of the stored url]] per address, each [ok, code,
    url, host], from the shipping validator."""
    out = []
    for url in urls:
        form = helper.validate_source_url(url, "form")
        cli = helper.validate_source_url(url, "cli")
        again = helper.validate_source_url(form["url"], "form") if form["ok"] else None
        out.append([verdict(form), verdict(cli), verdict(again) if again else None])
    return out


NODE_SCRIPT = (
    'const M=require(process.env.HOST_GRAMMAR_MODEL);'
    'const urls=JSON.parse(require("fs").readFileSync(0,"utf8"));'
    'const v=r=>[r.ok,r.code,r.url,r.host];'
    'process.stdout.write(JSON.stringify(urls.map(u=>{'
    'const f=M.validateSourceUrl(u),c=M.validateSourceUrl(u,{origin:"cli"});'
    'return [v(f),v(c),f.ok?v(M.validateSourceUrl(f.url)):null]})))')


def node_readings(urls):
    model = os.environ.get("HOST_GRAMMAR_MODEL") or str(ROOT / "Model.mjs")
    done = subprocess.run(["node", "-e", NODE_SCRIPT], input=json.dumps(urls), capture_output=True, text=True,
                          cwd=ROOT, timeout=300, env=dict(os.environ, HOST_GRAMMAR_MODEL=model))
    if done.returncode != 0:
        raise AssertionError(done.stderr[-800:])
    return json.loads(done.stdout)


V4_BODY = r"""
    var v = function (r) { return [r.ok, r.code, r.url, r.host] }
    var out = []
    for (var i = 0; i < URLS.length; i++) {
      var f = Model.validateSourceUrl(URLS[i])
      out.push([v(f), f.ok ? v(Model.validateSourceUrl(f.url)) : null])
    }
    console.log("RESULT " + JSON.stringify(out))
"""


def lowering_differs(url):
    return any(ord(ch) in LOWERING_DIFF for ch in url)


class DifferentialTest(unittest.TestCase):
    """The helper, the model in node and the model in Qt's engine, over one
    corpus, held equal; and every address both accept held to what urllib
    reads, and to itself once stored."""

    @classmethod
    def setUpClass(cls):
        cls.urls = corpus()
        cls.helper = helper_readings(cls.urls)
        cls.node = node_readings(cls.urls)

    def test_the_corpus_is_the_size_it_says(self):
        self.assertGreaterEqual(len(self.urls), FIXTURE["corpusSize"] * 9 // 10)
        accepted = sum(1 for h in self.helper if h[0][0])
        self.assertTrue(len(self.urls) // 10 < accepted < len(self.urls) * 9 // 10, accepted)

    def test_both_validators_answer_alike(self):
        wrong = []
        for url, h, n in zip(self.urls, self.helper, self.node):
            for origin, mine, theirs in (("form", h[0], n[0]), ("cli", h[1], n[1])):
                if lowering_differs(url):
                    mine, theirs = mine[:2], theirs[:2]
                if mine != theirs:
                    wrong.append((ascii(url[:70]), origin, mine, theirs))
        self.assertEqual((len(wrong), wrong[:6]), (0, []))

    def test_every_address_both_accept_is_read_by_the_url_library(self):
        """Invariant (a): urlsplit, split_userinfo and urllib.request.Request
        read the stored url without a ValueError, and the request's host and
        port pass the connection layer's rule."""
        wrong = []
        for url, h, n in zip(self.urls, self.helper, self.node):
            if not (h[0][0] and n[0][0]):
                continue
            stored = h[0][2]
            try:
                urllib.parse.urlsplit(stored)
                target, _ = helper.split_userinfo(stored)
                request = urllib.request.Request(target)
            except ValueError as error:
                wrong.append((ascii(url[:70]), type(error).__name__))
                continue
            if helper.host_name_refused(request.host, True):
                wrong.append((ascii(url[:70]), "host_name_refused"))
        self.assertEqual((len(wrong), wrong[:6]), (0, []))

    def test_a_stored_url_reads_as_itself_in_both_mirrors(self):
        """The critique's finding 8: validate(validate(x).url) is
        validate(x), so nothing stored is dropped at the next load."""
        wrong = []
        for url, h, n in zip(self.urls, self.helper, self.node):
            if h[0][0] and h[2] != h[0]:
                wrong.append((ascii(url[:70]), "helper", h[2][:2]))
            if n[0][0] and n[2] != n[0]:
                wrong.append((ascii(url[:70]), "node", n[2][:2]))
        self.assertEqual((len(wrong), wrong[:6]), (0, []))

    @unittest.skipUnless(os.access(proto_v4.QML_BIN, os.X_OK), "Qt's qml runtime is not installed")
    def test_qts_engine_answers_as_node_does_and_reads_a_stored_url_as_itself(self):
        """A subset in the shell's own engine: every hand vector and every
        tenth generated address, no more than 2,000."""
        chosen = [i for i, url in enumerate(self.urls) if i % 10 == 0 or i >= len(self.urls) - len(FIXTURE["vectors"])]
        chosen = chosen[-2000:]
        urls = [self.urls[i] for i in chosen]
        body = "    var URLS = %s\n%s" % (json.dumps(urls, ensure_ascii=True), V4_BODY)
        result = proto_v4.run_qml(self, body)
        self.assertNotIn("probeError", result if isinstance(result, dict) else {})
        wrong = []
        for i, (form, again) in zip(chosen, result):
            theirs = self.node[i][0]
            if lowering_differs(self.urls[i]):
                form, theirs = form[:2], theirs[:2]
            if form != theirs:
                wrong.append((ascii(self.urls[i][:70]), "node", form, theirs))
            if form[0] and again != form:
                wrong.append((ascii(self.urls[i][:70]), "stored", again))
        self.assertEqual((len(chosen) >= 1000, len(wrong), wrong[:6]), (True, 0, []))


PROVIDER = json.loads((ROOT / "tests" / "fixtures" / "provider-hosts.json").read_text(encoding="ascii"))
LOGO_SURVEY = json.loads((ROOT / "tests" / "fixtures" / "logo-survey.json").read_text(encoding="ascii"))


def fixture_logos():
    """Every logo of the shared logo fixtures (provider-hosts' logoHosts and
    the logo-survey cases)."""
    out = [case["url"] for case in PROVIDER["logoHosts"]]
    for case in LOGO_SURVEY["cases"]:
        out += [row["logo"] for row in case["channels"]
                if isinstance(row, dict) and isinstance(row.get("logo"), str) and row["logo"]]
    return out


def logo_corpus():
    """The differential's logos (D-SINK-112), from host-grammar.json's atoms
    and seeds as corpus() builds addresses, but shaped as logos are: most are
    https, most carry no user information and no port, and one insert in
    three; then every fixture logo. Deterministic."""
    atoms = FIXTURE["atoms"]
    out = []
    for seed in FIXTURE["seeds"]:
        rnd = random.Random(seed * 1000 + 112)
        for _ in range(FIXTURE["corpusSize"] // len(FIXTURE["seeds"]) // 2):
            parts = {"userinfo": "" if rnd.random() < 0.8 else rnd.choice(atoms["userinfo"]),
                     "port": "" if rnd.random() < 0.6 else rnd.choice(atoms["ports"]),
                     "target": rnd.choice(atoms["targets"])}
            if rnd.random() < 0.2:
                parts["host"] = rnd.choice(atoms["literals"])
            else:
                labels = [rnd.choice(atoms["labels"]) for _ in range(rnd.randint(1, 2))]
                parts["host"] = ".".join(labels) + "." + rnd.choice(atoms["tlds"])
            if rnd.random() < 0.35:
                where = rnd.choice(("userinfo", "host", "host", "port", "target"))
                text = parts[where]
                at = rnd.randint(0, len(text))
                parts[where] = text[:at] + rnd.choice(atoms["inserts"]) + text[at:]
            scheme = "https" if rnd.random() < 0.85 else rnd.choice(atoms["schemes"])
            out.append(scheme + "://" + parts["userinfo"] + parts["host"] + parts["port"] + parts["target"])
    out += fixture_logos()
    return list(dict.fromkeys(out))


LOGO_NODE_SCRIPT = (
    'const M=require(process.env.HOST_GRAMMAR_MODEL);'
    'const req=JSON.parse(require("fs").readFileSync(0,"utf8"));'
    'process.stdout.write(JSON.stringify({each:req.urls.map(u=>{const s=M.splitLogoUrl(u);return [s.scheme,s.host]}),'
    'survey:M.logoSurvey(req.surveyed.map(u=>({logo:u})))}))')

LOGO_V4_BODY = r"""
    var out = []
    for (var i = 0; i < URLS.length; i++) {
      var s = Model.splitLogoUrl(URLS[i])
      out.push([s.scheme, s.host])
    }
    console.log("RESULT " + JSON.stringify(out))
"""


class ConnectRecorder:
    """bounded_create_connection's stand-in for the logo fetch: records the
    (host, port) http.client asks for and refuses the connection, so no
    socket is opened and nothing is looked up."""

    def __init__(self):
        self.asked = []

    def __call__(self, address, *args, **kwargs):
        import errno
        self.asked.append(tuple(address))
        raise ConnectionRefusedError(errno.ECONNREFUSED, "refused by the test")


def fetch_asks(url):
    """-> (code, [(host, port)] the connection was asked for, [names
    looked up]) of one fetch_logo, with the connection and the resolver
    replaced by stand-ins that record and refuse."""
    import socket
    from unittest import mock
    connect, lookup = ConnectRecorder(), NoLookup()
    with mock.patch.object(helper, "bounded_create_connection", connect), \
            mock.patch.object(socket, "getaddrinfo", lookup), \
            mock.patch.dict(os.environ, {}, clear=False):
        for name in ("http_proxy", "https_proxy", "all_proxy", "no_proxy",
                     "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
            os.environ.pop(name, None)
        try:
            helper.fetch_logo(url, 1.0, 2.0)
            code = "ok"
        except helper.HelperError as error:
            code = error.code
    return code, connect.asked, lookup.asked


class LogoDifferentialTest(unittest.TestCase):
    """D-SINK-112: the one reading of a logo's address, in the helper
    (logo_contact_host, logo_scheme, logo_survey), in node and in Qt's
    engine (Model.splitLogoUrl, Model.logoSurvey), held equal over the
    corpus; and every logo the survey counts held to what the fetch then
    asks the connection for."""

    @classmethod
    def setUpClass(cls):
        cls.urls = logo_corpus()
        cls.helper = [[helper.logo_scheme(u), helper.logo_contact_host(u)] for u in cls.urls]
        cls.surveyed = [u for u in cls.urls if not lowering_differs(u)]
        model = os.environ.get("HOST_GRAMMAR_MODEL") or str(ROOT / "Model.mjs")
        done = subprocess.run(["node", "-e", LOGO_NODE_SCRIPT],
                              input=json.dumps({"urls": cls.urls, "surveyed": cls.surveyed}),
                              capture_output=True, text=True, cwd=ROOT, timeout=300,
                              env=dict(os.environ, HOST_GRAMMAR_MODEL=model))
        if done.returncode != 0:
            raise AssertionError(done.stderr[-800:])
        cls.node = json.loads(done.stdout)

    def test_the_logo_corpus_counts_some_and_refuses_some(self):
        counted = sum(1 for _, host in self.helper if host)
        self.assertTrue(len(self.urls) // 5 < counted < len(self.urls) * 4 // 5, (counted, len(self.urls)))

    def test_both_readings_answer_alike_for_every_logo(self):
        wrong = []
        for url, mine, theirs in zip(self.urls, self.helper, self.node["each"]):
            if lowering_differs(url):
                mine, theirs = [mine[0], mine[1] == ""], [theirs[0], theirs[1] == ""]
            if mine != theirs:
                wrong.append((ascii(url[:70]), mine, theirs))
        self.assertEqual((len(wrong), wrong[:6]), (0, []))

    def test_both_surveys_answer_alike_over_the_whole_corpus(self):
        mine = helper.logo_survey([{"logo": u} for u in self.surveyed])
        for key in ("allowedSchemes", "allowedTypes"):
            mine.pop(key)
        theirs = self.node["survey"]
        self.assertEqual(sorted(mine), sorted(theirs))
        for key in sorted(mine):
            self.assertEqual(mine[key], theirs[key], key)

    def test_every_logo_the_survey_counts_is_asked_of_the_connection_at_its_host_and_port(self):
        """Invariant (b): fetch_logo hands each counted logo to the opener,
        and its connection is asked for the survey's host (an IPv6 literal
        without its brackets, as http.client hands it over) on http.client's
        port, and nothing is looked up. Every second counted logo and every
        fixture logo. A host that is not Latin-1 is D-SINK-119's: http.client
        cannot write its Host header, and the next commit sends its A-label."""
        helper.prepare_tls_context()
        fixture = set(fixture_logos())
        counted = [(u, h) for u, (_, h) in zip(self.urls, self.helper) if h]
        chosen = [(u, h) for i, (u, h) in enumerate(counted) if i % 2 == 0 or u in fixture]
        wrong, skipped = [], 0
        for url, host in chosen:
            try:
                host.encode("latin-1")
            except UnicodeEncodeError:
                skipped += 1
                continue
            code, asked, looked_up = fetch_asks(url)
            want = [(host[1:-1] if host.startswith("[") else host, urllib.parse.urlsplit(url).port or 443)]
            got = [(h.lower(), p) for h, p in asked]
            if (code, got, looked_up) != ("logo_fetch", want, []):
                wrong.append((ascii(url[:70]), code, got, looked_up))
        self.assertGreater(len(chosen) - skipped, 500)
        self.assertEqual((len(wrong), wrong[:6]), (0, []))

    def test_every_logo_the_survey_refuses_is_refused_before_the_connection(self):
        """And the other half: each logo the survey counts refused is refused
        by fetch_logo as a policy refusal, with the connection never asked
        and nothing looked up (every fourth, and every fixture logo)."""
        fixture = set(fixture_logos())
        refused = [u for i, (u, (_, h)) in enumerate(zip(self.urls, self.helper)) if not h and (i % 4 == 0 or u in fixture)]
        wrong = []
        for url in refused:
            code, asked, looked_up = fetch_asks(url)
            if code not in ("logo_scheme", "logo_host") or asked or looked_up:
                wrong.append((ascii(url[:70]), code, asked, looked_up))
        self.assertGreater(len(refused), 500)
        self.assertEqual((len(wrong), wrong[:6]), (0, []))

    @unittest.skipUnless(os.access(proto_v4.QML_BIN, os.X_OK), "Qt's qml runtime is not installed")
    def test_qts_engine_reads_every_chosen_logo_as_node_does(self):
        fixture = set(fixture_logos())
        chosen = [i for i, url in enumerate(self.urls) if i % 4 == 0 or url in fixture][-2000:]
        urls = [self.urls[i] for i in chosen]
        body = "    var URLS = %s\n%s" % (json.dumps(urls, ensure_ascii=True), LOGO_V4_BODY)
        result = proto_v4.run_qml(self, body)
        self.assertNotIn("probeError", result if isinstance(result, dict) else {})
        wrong = [(ascii(self.urls[i][:70]), got, self.node["each"][i]) for i, got in zip(chosen, result)
                 if got != self.node["each"][i] and not lowering_differs(self.urls[i])]
        self.assertEqual((len(chosen) >= 1000, len(wrong), wrong[:6]), (True, 0, []))


UNREADABLE = ["http://qqqqqq" + chr(0xFF1A) + "zzzzzz@cdn.test/get.php", "http://qqqqqq:zz[zz]@cdn.test/get.php",
              "http://[::1:]/get.php", "http://cdn" + chr(0xFF0F) + ".test/get.php"]


class NoLookup:
    """socket.getaddrinfo's stand-in for the fetch-path tests: records the
    host and raises, so nothing is ever resolved."""

    def __init__(self):
        self.asked = []

    def __call__(self, host, *args, **kwargs):
        import socket
        self.asked.append(host)
        raise socket.gaierror(socket.EAI_NONAME, "refused by the test")


def run_main(argv, env):
    import contextlib
    import io
    from unittest import mock
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(argv)
    lines = out.getvalue().strip().splitlines()
    return code, (json.loads(lines[-1]) if lines else None), err.getvalue()


class FetchPathTest(unittest.TestCase):
    """D-SINK-115's defence behind the validators: an address the URL
    library refuses to read is a named refusal that names nothing, not an
    internal error quoting the authority. Nothing is looked up."""

    def test_read_http_source_refuses_an_unreadable_address_as_bad_url(self):
        import socket
        from unittest import mock
        got = []
        for url in UNREADABLE:
            stand_in = NoLookup()
            with mock.patch.object(socket, "getaddrinfo", stand_in):
                try:
                    helper.read_http_source(url, 1.0, "playlist", helper.DestinationPolicy("playlist", "user"))
                    got.append((ascii(url), "ok", [], stand_in.asked))
                except helper.HelperError as error:
                    got.append((ascii(url), error.code, [w for w in ("qqqqqq", "zzzzzz", "cdn") if w in error.message],
                                stand_in.asked))
                except ValueError as error:
                    got.append((ascii(url), type(error).__name__, [], stand_in.asked))
        self.assertEqual(got, [(ascii(url), "bad_url", [], []) for url in UNREADABLE])

    def test_the_playlist_verb_refuses_one_naming_nothing(self):
        import socket
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as cache:
            got = []
            for url in UNREADABLE:
                stand_in = NoLookup()
                with mock.patch.object(socket, "getaddrinfo", stand_in):
                    code, reply, err = run_main(["playlist", "--cache-dir", cache, "--timeout", "1"],
                                                {helper.URL_ENV: url, helper.ORIGIN_ENV: "user"})
                text = json.dumps(reply) + err
                got.append((ascii(url), code, reply["error"]["code"],
                            [w for w in ("qqqqqq", "zzzzzz", "cdn", "netloc") if w in text], stand_in.asked))
        self.assertEqual(got, [(ascii(url), 1, "bad_url", [], []) for url in UNREADABLE])


STREAMS = [
    ("http://cdn!.test/1.ts", "D-SINK-117"),
    ("http://cdn" + chr(0x2474) + ".test/1.ts", "D-SINK-117"),
    ("http://cdn" + chr(0x034F) + ".test/1.ts", "D-SINK-116"),
    ("http://cdn" + chr(0xFE0F) + ".test/1.ts", "D-SINK-116"),
    ("http://cdn" + chr(0xFF0F) + ".test/1.ts", "D-SINK-115"),
    ("http://u" + chr(0xFF1A) + "p@cdn.test/1.ts", "D-SINK-115"),
    ("http://u:p[x]@cdn.test/1.ts", "D-SINK-115"),
]
STREAM_CONTROL = "http://cdn_x.test/live/1.ts"


class StreamTest(unittest.TestCase):
    """A channel whose address holds a newly refused shape: skipped at the
    parse as a host no host name may take (`name`), and refused at play from
    a cache written before the rule, as D-SINK-86's were."""

    def test_the_parse_skips_each_as_a_name(self):
        lines = ["#EXTM3U"]
        for index, (url, _) in enumerate(STREAMS):
            lines += ["#EXTINF:-1,R%d" % index, url]
        lines += ["#EXTINF:-1,C", STREAM_CONTROL]
        result = helper.parse_m3u("\n".join(lines) + "\n", {"host": "", "local": True})
        reasons = [helper.stream_entry_refusal(url, {"host": "", "local": True})[0] for url, _ in STREAMS]
        self.assertEqual(([c["url"] for c in result["channels"]], reasons),
                         ([STREAM_CONTROL], ["name"] * len(STREAMS)))

    def test_play_refuses_each_from_an_older_cache(self):
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as root:
            cache = os.path.join(root, "cache")
            os.mkdir(cache, 0o700)
            rows = [{"id": "r%d" % i, "name": "R%d" % i, "url": url} for i, (url, _) in enumerate(STREAMS)]
            rows.append({"id": "c", "name": "C", "url": STREAM_CONTROL})
            with open(os.path.join(cache, "channels.json"), "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "sourceHost": "local file", "channels": rows}, handle)
            got = []
            with mock.patch.object(helper, "cache_dir", lambda d: d):
                for row in rows:
                    try:
                        got.append(helper.player_target(row["id"], "", cache)["url"])
                    except helper.HelperError as error:
                        got.append((error.code, error.message))
        refusal = (getattr(helper, "STREAM_HOST_NAME_REFUSAL", ""))
        self.assertEqual(got, [("unsupported_scheme", refusal)] * len(STREAMS) + [STREAM_CONTROL])


if __name__ == "__main__":
    unittest.main()
