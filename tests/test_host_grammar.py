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
        self.assertTrue({"fold_host", "fold_userinfo", "bracket", "literal", "host", "port_text", "port_range",
                         "case_fold"} <= kinds)
        self.assertEqual((len(TABLES["caseFoldRanges"]), len(expand(TABLES["caseFoldRanges"])), len(FIXTURE["streams"])),
                         (14, 67, 6))
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

    def test_the_nfkc_table_is_unicodedatas_and_the_one_code_point_beyond_it(self):
        """D-SINK-119: HOST_NFKC_RANGES is the fixture's table, every code
        point whose NFKC form is not itself in Python's Unicode, and U+A7F1
        beyond it (node's Unicode 17 folds it to `S`; the node suite holds
        the table to node's NFKC exactly). The table is the rule."""
        py = {c for c in range(0x110000) if not 0xD800 <= c <= 0xDFFF
              and unicodedata.normalize("NFKC", chr(c)) != chr(c)}
        shipped = helper_ranges(getattr(helper, "HOST_NFKC_RANGES", ()))
        self.assertEqual(shipped, expand(TABLES["nfkcRanges"]))
        self.assertEqual((sorted(hex(c) for c in shipped - py), sorted(hex(c) for c in py - shipped)), (["0xa7f1"], []))
        self.assertEqual(codes(TABLES["nfkcBeyondPython"]), {0xA7F1})
        refused = [hex(c) for c in sorted(shipped) if not helper.host_name_refused("a" + chr(c) + "b.test")]
        self.assertEqual(refused, [])

    def test_the_case_fold_table_is_nameprep_recomputed_over_every_code_point(self):
        """D-SINK-119, the owner's decision of 2026-11-17: HOST_CASE_FOLD_RANGES
        is the fixture's table, and here it is recomputed from the codec
        itself (encodings.idna.nameprep, a local computation; nothing is
        looked up) over every code point: each one the other host rules
        accept -- host_name_refused with this table emptied -- whose nameprep
        form differs from its form as lower_host writes it. Compared as the
        lowered form stands and as its NFC form, the same 67 either way, so
        nameprep's composition adds none. A tripwire for a Python upgrade
        that moves stringprep, its Unicode 3.2 tables or str.lower; and every
        code point of it is refused."""
        from encodings.idna import nameprep
        from unittest import mock
        shipped = helper_ranges(getattr(helper, "HOST_CASE_FOLD_RANGES", ()))
        raw, composed = set(), set()
        with mock.patch.object(helper, "_HOST_CASE_FOLDS", frozenset(), create=True):
            for c in range(0x80, 0x110000):
                if 0xD800 <= c <= 0xDFFF:
                    continue
                low = helper.lower_host(chr(c))
                try:
                    prepped = nameprep(low)
                except UnicodeError:
                    continue
                as_nfc = unicodedata.normalize("NFC", low)
                if prepped == low and prepped == as_nfc:
                    continue
                if helper.host_name_refused("a" + chr(c) + "b.test"):
                    continue
                if prepped != low:
                    raw.add(c)
                if prepped != as_nfc:
                    composed.add(c)
        self.assertEqual((sorted(hex(c) for c in raw ^ shipped), raw == composed, len(raw)), ([], True, 67))
        self.assertEqual(shipped, expand(TABLES["caseFoldRanges"]))
        self.assertEqual([hex(c) for c in sorted(shipped) if not helper.host_name_refused("a" + chr(c) + "b.test")], [])

    def test_the_fold_makes_no_case_fold_code_point_of_one_no_table_refuses(self):
        """D-SINK-119: host_name_refused asks HOST_CASE_FOLD_RANGES of the
        name as written and not of its NFKD fold, because the fold produces
        none of them from a code point neither table holds: U+0345 is in the
        NFKD of the 63 iota letters, each in the table itself, and of U+037A;
        the final sigma in that of U+03F2 and five mathematical letters; and
        those seven are look-alikes (HOST_NFKC_RANGES). Over every code
        point; a Unicode upgrade that adds another goes red."""
        folds = helper_ranges(getattr(helper, "HOST_CASE_FOLD_RANGES", ()))
        nfkc = helper_ranges(getattr(helper, "HOST_NFKC_RANGES", ()))
        made = {}
        for c in range(0x80, 0x110000):
            if 0xD800 <= c <= 0xDFFF:
                continue
            hit = folds.intersection(map(ord, unicodedata.normalize("NFKD", chr(c))))
            if hit and c not in folds:
                made[c] = hit
        self.assertEqual(sorted(hex(c) for c in made if c not in nfkc), [])
        self.assertEqual(sorted(made), [0x37A, 0x3F2, 0x1D6D3, 0x1D70D, 0x1D747, 0x1D781, 0x1D7BB])

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


NFKC_V4_BODY = r"""
    var listed = {}
    var ranges = Model.HOST_NFKC_RANGES
    for (var r = 0; r < ranges.length; r++) for (var c = ranges[r][0]; c <= ranges[r][1]; c++) listed[c] = true
    var extra = [], missing = []
    for (var cp = 0; cp < 0x110000; cp++) {
      if (cp >= 0xd800 && cp <= 0xdfff) continue
      var s = cp > 0xffff ? String.fromCharCode(0xd800 + ((cp - 0x10000) >> 10), 0xdc00 + ((cp - 0x10000) & 0x3ff))
                          : String.fromCharCode(cp)
      var changes = s.normalize("NFKC") !== s
      if (changes && listed[cp] !== true) extra.push(cp.toString(16))
      if (!changes && listed[cp] === true) missing.push(cp.toString(16))
    }
    var odd = String.fromCharCode(0xa7f1)
    console.log("RESULT " + JSON.stringify({ ranges: ranges.length, extra: extra.slice(0, 20), missing: missing,
      refused: [Model.hostNameRefused("a" + odd + ".test"), Model.validateSourceUrl("http://a" + odd + ".test/").code] }))
"""


class EngineTableTest(unittest.TestCase):
    """D-SINK-119 in the shell's own engine: the table, not the engine, is
    the rule. Measured on Qt 6.12: its NFKC leaves alone every code point the
    table leaves out but three, U+16126, U+16127 and U+16128 (Gurung Khema
    vowel signs, Unicode 16, whose decompositions nest two deep and which
    Qt does not compose back; node and Python do), so Qt's normalize would
    read them as look-alikes where neither of the other engines does. Pinned
    here as a tripwire. A code point the table lists and the engine leaves
    alone (U+A7F1 when the engine's Unicode is older than 17) is refused all
    the same."""

    @unittest.skipUnless(os.access(proto_v4.QML_BIN, os.X_OK), "Qt's qml runtime is not installed")
    def test_qts_engine_folds_nothing_the_table_leaves_out(self):
        result = proto_v4.run_qml(self, NFKC_V4_BODY)
        self.assertNotIn("probeError", result)
        self.assertEqual((result["ranges"], result["extra"], set(result["missing"]) <= {"a7f1"}, result["refused"]),
                         (256, ["16126", "16127", "16128"], True, [True, "invalid"]), result)


CASE_FOLD_V4_BODY = r"""
    var hex4 = function (n) { var h = n.toString(16).toUpperCase(); while (h.length < 4) h = "0" + h; return h }
    var unit = function (c) {
      return c > 0xffff ? String.fromCharCode(0xd800 + ((c - 0x10000) >> 10), 0xdc00 + ((c - 0x10000) & 0x3ff))
                        : String.fromCharCode(c)
    }
    var ranges = Model.HOST_CASE_FOLD_RANGES || []
    var listed = {}, nfkc = {}
    for (var r = 0; r < ranges.length; r++) for (var c = ranges[r][0]; c <= ranges[r][1]; c++) listed[c] = true
    var nr = Model.HOST_NFKC_RANGES
    for (var q = 0; q < nr.length; q++) for (var k = nr[q][0]; k <= nr[q][1]; k++) nfkc[k] = true
    var kept = []
    for (var t = 0; t < FIXTURE_CODES.length; t++) {
      if (!Model.hostNameRefused("a" + unit(FIXTURE_CODES[t]) + "b.test")) kept.push(hex4(FIXTURE_CODES[t]))
    }
    var made = []
    for (var cp = 0x80; cp < 0x110000; cp++) {
      if ((cp >= 0xd800 && cp <= 0xdfff) || listed[cp] === true || nfkc[cp] === true) continue
      var s = unit(cp), d = s.normalize("NFKD")
      if (d === s) continue
      for (var i = 0; i < d.length; i++) if (FIXTURE_SET[d.charCodeAt(i)] === true) { made.push(hex4(cp)); break }
    }
    var fold = Model.sourceErrorMessage("url_fold_host")
    var vectors = VECTORS.map(function (u) {
      var f = Model.validateSourceUrl(u), e = Model.validateSourceUrl(u, { kind: "epg" })
      return [f.ok, f.code, f.host, f.ok ? "" : (f.message === fold ? "fold" : f.message),
              e.ok ? "" : (e.message === Model.sourceErrorMessage("url_fold_host", { field: "epg" }) ? "fold" : e.message)]
    })
    var records = STATE.map(function (c, n) {
      return { key: (0xa0000000 + n).toString(16), url: c.url, epgUrl: c.epgUrl || "", kind: "http", label: "S" + n,
               labelCustom: true, origin: "cli", addedAt: 1, lastUsed: 1, fetchedAt: 0, channelCount: 0, groupCount: 0 }
    })
    var st = Model.parseState(JSON.stringify({ version: 2, cacheLayout: "sources", favorites: [], recents: [],
                                               savedSearches: [], hiddenGroups: [], sources: records }))
    var byKey = {}
    for (var m = 0; m < st.sources.length; m++) byKey[st.sources[m].key] = st.sources[m]
    var state = STATE.map(function (c, n) {
      var x = byKey[(0xa0000000 + n).toString(16)]
      return [x !== undefined, x ? x.url === c.url : null, x ? x.epgUrl !== "" : null]
    })
    console.log("RESULT " + JSON.stringify({ ranges: ranges.map(function (p) { return [hex4(p[0]), hex4(p[1])] }),
      kept: kept, made: made.slice(0, 8), madeCount: made.length, vectors: vectors, state: state }))
"""


def case_fold_rows():
    """The fixture's rows for the owner's decision of 2026-11-17: the
    vectors whose reason is case_fold or whose note names the decision, and
    the stateReaders rows whose url or guide url holds a code point of the
    table or is the plain name the codec wrote."""
    table = expand(TABLES["caseFoldRanges"])
    vectors = [c for c in FIXTURE["vectors"] if c.get("why") == "case_fold" or "2026-11-17" in c.get("note", "")]
    state = [c for c in FIXTURE["stateReaders"]
             if any(ord(ch) in table for ch in c["url"] + c.get("epgUrl", "")) or "strasse" in c["url"]
             or c["url"].startswith("http://" + chr(0x3C3))]
    return vectors, state


class CaseFoldEngineTest(unittest.TestCase):
    """D-SINK-119, the owner's decision of 2026-11-17, in the shell's own
    engine, where the Sources form and the state reader run: the model's
    HOST_CASE_FOLD_RANGES is the fixture's table, hostNameRefused refuses
    each of its 67 code points, the engine's own NFKD makes none of them
    from a code point neither table holds (so asking the table as written is
    enough there too), every vector of the decision reads as the fixture
    says with fold_host's sentence on the playlist and the EPG field, and
    Model.parseState drops, clears and keeps the decision's stored rows as
    the fixture says."""

    @unittest.skipUnless(os.access(proto_v4.QML_BIN, os.X_OK), "Qt's qml runtime is not installed")
    def test_qts_engine_holds_the_table_and_refuses_drops_and_keeps_as_the_fixture_says(self):
        vectors, state = case_fold_rows()
        codes_ = sorted(expand(TABLES["caseFoldRanges"]))
        body = "    var FIXTURE_CODES = %s\n    var FIXTURE_SET = {}\n    FIXTURE_CODES.forEach(function (c) { FIXTURE_SET[c] = true })\n" \
               "    var VECTORS = %s\n    var STATE = %s\n%s" % (
                   json.dumps(codes_), json.dumps([c["input"] for c in vectors], ensure_ascii=True),
                   json.dumps(state, ensure_ascii=True), CASE_FOLD_V4_BODY)
        result = proto_v4.run_qml(self, body)
        self.assertNotIn("probeError", result)
        want_vectors = [[c["ok"], "ok" if c["ok"] else c["code"], c.get("host", ""), "" if c["ok"] else "fold",
                         "" if c["ok"] else "fold"] for c in vectors]
        want_state = [[c["kept"], True if c["kept"] else None, c.get("epgKept", False) if c["kept"] else None]
                      for c in state]
        self.assertEqual((result["ranges"], result["kept"], result["made"], result["vectors"], result["state"]),
                         (TABLES["caseFoldRanges"], [], [], want_vectors, want_state))
        self.assertGreaterEqual((len(vectors), len(state)), (10, 6))


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
    'return [v(f),v(c),f.ok?v(M.validateSourceUrl(f.url)):null,f.ok?M.hostOf(f.url):null]})))')


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

    def test_every_address_both_accept_is_sent_as_its_a_label_or_refused(self):
        """D-SINK-119, invariant (a) with the codec: for every address both
        validators accept, the target the fetch builds (a_label_target over
        split_userinfo's) writes the host as the idna codec writes it -- the
        name CPython's socket hands the resolver -- so the request's host,
        and its Host header, are ASCII; or the fetch refuses it, exactly
        where the codec refuses the host or it holds a dot the codec reads
        that is not `.`. The oracle is the codec, called."""
        dots = (chr(0x3002), chr(0xFF0E), chr(0xFF61))
        wrong, refused, rewritten = [], 0, 0
        for url, h, n in zip(self.urls, self.helper, self.node):
            if not (h[0][0] and n[0][0]):
                continue
            target, _ = helper.split_userinfo(h[0][2])
            netloc = urllib.parse.urlsplit(target).netloc
            written = netloc if netloc.startswith("[") else (netloc.rpartition(":")[0] if ":" in netloc else netloc)
            if written.startswith("["):
                oracle = written
            elif any(dot in written for dot in dots):
                oracle = None
            else:
                try:
                    oracle = written.encode("idna").decode("ascii")
                except UnicodeError:
                    oracle = None
            got = helper.a_label_target(target)
            if oracle is None or got is None:
                refused += got is None
                if got is not oracle:
                    wrong.append((ascii(url[:70]), oracle, got and ascii(got[:70])))
                continue
            rewritten += got != target
            request = urllib.request.Request(got)
            # The request's host is percent-decoded by urllib (a zone's `%25`).
            if request.host != urllib.parse.unquote(oracle + netloc[len(written):]) or not request.host.isascii():
                wrong.append((ascii(url[:70]), ascii(request.host)))
        self.assertGreater(refused, 10)
        self.assertGreater(rewritten, 100)
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

    def test_the_status_names_the_host_the_sources_row_names(self):
        """D-SINK-118: for every address both validators accept, the host
        the helper's statuses and sentences name (source_host over the
        stored url) is the one Model.hostOf names: an IPv6 literal with its
        brackets, the port and the user information gone."""
        wrong, literals = [], 0
        for url, h, n in zip(self.urls, self.helper, self.node):
            if not (h[0][0] and n[0][0]) or lowering_differs(url):
                continue
            mine = helper.source_host(h[0][2])
            literals += mine.startswith("[")
            if mine != n[3]:
                wrong.append((ascii(url[:70]), ascii(mine), ascii(n[3])))
        self.assertGreater(literals, 100)
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
    three; then, per seed, 400 more whose host is one of the long hosts at
    and past DNS's length (`longHosts`, the review of the column fix,
    2026-11-17); then every fixture logo. Deterministic."""
    atoms = FIXTURE["atoms"]
    out = []
    for seed in FIXTURE["seeds"]:
        rnd = random.Random(seed * 1000 + 112)
        share = FIXTURE["corpusSize"] // len(FIXTURE["seeds"]) // 2
        for n in range(share + 400):
            parts = {"userinfo": "" if rnd.random() < 0.8 else rnd.choice(atoms["userinfo"]),
                     "port": "" if rnd.random() < 0.6 else rnd.choice(atoms["ports"]),
                     "target": rnd.choice(atoms["targets"])}
            if n >= share:
                parts["host"] = rnd.choice(atoms["longHosts"])
            elif rnd.random() < 0.2:
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


def fetch_asks(url, hosts=None):
    """-> (code, [(host, port)] the connection was asked for, [names
    looked up]) of one fetch_logo, with the connection and the resolver
    replaced by stand-ins that record and refuse; the Host header's values
    are appended to `hosts` when one is given."""
    import http.client
    import socket
    from unittest import mock
    connect, lookup = ConnectRecorder(), NoLookup()
    seen = [] if hosts is None else hosts
    real = http.client.HTTPConnection.putheader

    def putheader(self, header, *values):
        if str(header).lower() == "host":
            seen.append(values[0] if len(values) == 1 else values)
        return real(self, header, *values)

    with mock.patch.object(helper, "bounded_create_connection", connect), \
            mock.patch.object(socket, "getaddrinfo", lookup), \
            mock.patch.object(http.client.HTTPConnection, "putheader", putheader), \
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
        self.assertTrue(len(self.urls) // 25 < counted < len(self.urls) * 4 // 5, (counted, len(self.urls)))

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
        port, its Host header is that host as written, in ASCII (D-SINK-119:
        a host outside Latin-1 could not be written there and a Latin-1 one
        was written as raw bytes), and nothing is looked up. Every counted
        logo."""
        helper.prepare_tls_context()
        fixture = set(fixture_logos())
        counted = [(u, h) for u, (_, h) in zip(self.urls, self.helper) if h]
        chosen = [(u, h) for u, h in counted]
        wrong = []
        for url, host in chosen:
            hosts = []
            code, asked, looked_up = fetch_asks(url, hosts)
            want = [(host[1:-1] if host.startswith("[") else host, urllib.parse.urlsplit(url).port or 443)]
            got = [(h.lower(), p) for h, p in asked]
            header = [h.lower()[:h.index("]") + 1] if h.startswith("[") else h.lower().partition(":")[0] for h in hosts]
            if (code, got, looked_up, header) != ("logo_fetch", want, [], [host]) or not all(h.isascii() for h in hosts):
                wrong.append((ascii(url[:70]), code, got, looked_up, ascii(hosts)))
        self.assertGreater(len(chosen), 400)
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
# D-SINK-119, the owner's decision of 2026-11-17: the shared fixture's
# channel addresses whose host holds a code point the idna codec's case
# folding writes as another name, a udp source entry among them.
STREAMS += [(url, "D-SINK-119") for url in FIXTURE["streams"]]
STREAM_CONTROL = "http://cdn_x.test/live/1.ts"


CYRILLIC = "".join(chr(c) for c in (0x43F, 0x440, 0x438, 0x43C, 0x435, 0x440)) + "." + chr(0x440) + chr(0x444)
IDN_FETCHED = ["http://b" + chr(0xFC) + "cher.test/get.php", "http://" + CYRILLIC + "/get.php?username=a&password=b",
               "https://" + chr(0x4F8B) + chr(0x3048) + ".test/get.php", "http://qqqqqq:zzzzzz@b" + chr(0xFC) + "cher.test:8080/get.php",
               "http://CDN.test/get.php", "http://xn--bcher-kva.test/x", "https://[2606:4700::1111]:8443/x"]
IDN_REFUSED = ["http://" + chr(0x5D0) + "a.test/get.php", "http://" + chr(0xE000) + "x.test/get.php",
               "http://" + chr(0xFDD0) + "x.test/get.php", "http://" + chr(0xE9) * 60 + ".test/get.php",
               "http://" + "q" * 64 + ".test/get.php", "http://a.cdn" + chr(0x3002) + "test/get.php",
               "http://cdn..test/get.php", "http://" + chr(0xFFFC) + "x.test/get.php"]


def fetch_handed(url, label="playlist"):
    """-> (code, message, [(host, port)] the connection was asked for,
    [names looked up], [Host header values]) of one read_http_source, with
    the connection, the resolver and http.client's header writer replaced
    by stand-ins that record (the first two refuse), and no proxy."""
    import http.client
    import socket
    from unittest import mock
    connect, lookup, hosts = ConnectRecorder(), NoLookup(), []
    real = http.client.HTTPConnection.putheader

    def putheader(self, header, *values):
        if str(header).lower() == "host":
            hosts.append(values[0] if len(values) == 1 else values)
        return real(self, header, *values)

    helper.prepare_tls_context()
    with mock.patch.object(helper, "bounded_create_connection", connect), \
            mock.patch.object(socket, "getaddrinfo", lookup), \
            mock.patch.object(http.client.HTTPConnection, "putheader", putheader), \
            mock.patch.dict(os.environ, {}, clear=False):
        for name in ("http_proxy", "https_proxy", "all_proxy", "no_proxy",
                     "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
            os.environ.pop(name, None)
        try:
            helper.read_http_source(url, 1.0, label, helper.DestinationPolicy(label, "user"))
            code, message = "ok", ""
        except helper.HelperError as error:
            code, message = error.code, error.message
    return code, message, connect.asked, lookup.asked, hosts


def written_host(url):
    netloc = urllib.parse.urlsplit(url).netloc.rpartition("@")[2]
    if netloc.startswith("["):
        return netloc[:netloc.index("]") + 1], netloc[netloc.index("]") + 1:]
    host, sep, port = netloc.partition(":")
    return host, sep + port


class IdnFetchTest(unittest.TestCase):
    """D-SINK-119 (2026-11-16): the first hop of the playlist, guide and
    probe fetches sends the host's A-label, the name the idna codec writes
    it as and CPython's socket already hands the resolver, so the request's
    host and its Host header are ASCII; a host the codec refuses is refused
    before any lookup with one fixed sentence. Nothing resolves: the
    connection and the resolver are stand-ins that record what they are
    handed."""

    def test_each_is_handed_to_the_connection_and_the_host_header_as_its_a_label(self):
        got, want = [], []
        for url in IDN_FETCHED:
            code, _, asked, looked_up, hosts = fetch_handed(url)
            host, port_text = written_host(url)
            ace = host if host.startswith("[") else host.encode("idna").decode("ascii")
            port = int(port_text[1:]) if port_text else (443 if url.startswith("https") else 80)
            got.append((ascii(url), code, asked, looked_up, hosts))
            want.append((ascii(url), "network", [(ace.strip("[]"), port)], [], [ace + port_text]))
        self.assertEqual(got, want)

    def test_a_host_the_codec_refuses_is_refused_before_any_lookup_naming_nothing(self):
        got = []
        for url in IDN_REFUSED:
            self.assertTrue(helper.validate_source_url(url)["ok"], ascii(url))
            code, message, asked, looked_up, hosts = fetch_handed(url, "EPG")
            got.append((ascii(url), code, message, asked, looked_up, hosts))
        sentence = "EPG " + getattr(helper, "HOST_IDNA_REFUSAL", "<none>")
        self.assertEqual(got, [(ascii(url), "bad_url", sentence, [], [], []) for url in IDN_REFUSED])

    def test_the_playlists_own_host_is_its_a_label_on_both_sides(self):
        """The policy's home, the playlist's host the shell sets, is written
        as its A-label too, so a hop the connection is asked for by its
        A-label is still the playlist's own host: a one-label IDN home is
        not refused as a name the provider chose, and another is."""
        from unittest import mock
        env = {helper.ORIGIN_ENV: "playlist", helper.HOME_HOST_ENV: chr(0xFC)}
        with mock.patch.dict(os.environ, env):
            policy = helper.DestinationPolicy.from_environment("EPG")
        self.assertEqual((policy.home, policy.refuses_name("xn--tda"), policy.refuses_name("xn--other")),
                         ("xn--tda", False, True))


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


# ------------------------------------------------------------- D-SINK-118

ENGINE = FIXTURE.get("engine", {"lowerHost": [], "hostKey": [], "labelKey": [], "sourceHost": []})
# A capital sigma, which the Final_Sigma rule reads as final before the
# hyphen or the colon each use puts after it, a final sigma written as one,
# and the small sigma, each after an alpha.
SIGMAS = (chr(0x391) + chr(0x3A3), chr(0x3B1) + chr(0x3C2), chr(0x3B1) + chr(0x3C3))


class EngineReadingTest(unittest.TestCase):
    """D-SINK-118 (2026-11-16, round 5 of the security review): how a host is
    lowered, compared and named. str.lower and node's toLowerCase apply
    Unicode's Final_Sigma rule and Qt's engine, which runs the Sources form
    and the state reader, does not; so every lowerer folds a capital sigma to
    the small one first (lower_host, Model.lowerHost), and no comparison
    folds a final sigma written as one (the critique's finding 3). The shared
    fixture's `engine` section is run here through the helper, in
    tests/Model.test.js through the model, and in EngineLoweringTest below
    through Qt's engine."""

    def test_each_host_is_lowered_compared_and_named_as_the_fixture_says(self):
        lower = getattr(helper, "lower_host", lambda text: "MISSING lower_host")
        got = ([lower(a) for a, _ in ENGINE["lowerHost"]],
               [helper.host_key(a) == helper.host_key(b) for a, b, _ in ENGINE["hostKey"]],
               [helper.label_key(a) == helper.label_key(b) for a, b, _ in ENGINE["labelKey"]],
               [helper.source_host(url) for url, _ in ENGINE["sourceHost"]])
        want = ([b for _, b in ENGINE["lowerHost"]], [same for _, _, same in ENGINE["hostKey"]],
                [same for _, _, same in ENGINE["labelKey"]], [host for _, host in ENGINE["sourceHost"]])
        self.assertEqual(got, want)
        self.assertGreaterEqual((len(ENGINE["lowerHost"]), len(ENGINE["hostKey"]), len(ENGINE["labelKey"]),
                                 len(ENGINE["sourceHost"])), (6, 5, 3, 6))

    def test_a_final_sigma_written_as_one_is_never_the_playlists_own_host(self):
        """The critique's finding 3: the own-host exceptions compare by
        host_key, which lowers a capital sigma to the small one and leaves a
        final sigma written as one alone, because the player asks the two as
        other bytes. Since the owner's decision of 2026-11-17 (D-SINK-119) no
        host either validator accepts holds a final sigma, and no channel the
        parse keeps; this holds the comparison itself."""
        home = {"host": helper.host_key(SIGMAS[2] + "-1.test"), "port": 554, "loopback": False}
        self.assertEqual([helper.own_host_match(h + "-1.test", 554, home) for h in SIGMAS], [True, False, True])

    def test_a_channel_written_as_its_playlist_was_typed_is_its_own_host(self):
        """A channel's host is lowered as the typed playlist's was, at the
        parse (the one-label exception, stream_entry_refusal) and at play (a
        proxied source's own host whose lookup answers nothing,
        stream_lookup), and the lookup asks each name as the player writes
        it. A final sigma written as one was another host there; since the
        owner's decision of 2026-11-17 (D-SINK-119) it is refused at the
        parse as a name no host may take (`name`, asked before the one-label
        rule) and at play before anything is looked up
        (stream_host_name_refused, which player_target asks first), since
        the idna codec writes it as the small sigma."""
        from unittest import mock
        typed = helper.validate_source_url("http://" + SIGMAS[0] + ":554/get.php")["url"]
        source = helper.playlist_source("http", typed, "global", "global")
        parse = [helper.stream_entry_refusal("rtsp://%s:554/live" % h, source)[0] for h in SIGMAS]
        typed = helper.validate_source_url("http://" + SIGMAS[0] + "-1.test:554/get.php")["url"]
        cached = helper.cached_source({"sourceHost": helper.source_host(typed), "sourceClass": "unresolved",
                                       "sourceLocal": False, "sourcePort": 554})
        asked = []

        def unanswered(name, port):
            asked.append((name, port))
            return []

        gate = [helper.stream_host_name_refused("rtsp://%s-1.test:554/live" % h) for h in SIGMAS]
        looked = (SIGMAS[0], SIGMAS[2])
        with mock.patch.object(helper, "stream_resolve", unanswered):
            play = [helper.stream_lookup("rtsp://%s-1.test:554/live" % h, cached)[0] for h in looked]
        self.assertEqual((parse, gate, play), (["", "name", ""], [False, True, False], ["", ""]))
        self.assertEqual(asked, [((h + "-1.test").encode("utf-8"), 554) for h in looked])

    def test_a_status_names_a_literal_with_its_brackets_and_decides_alike(self):
        """The status line named `::1` where the Sources row names `[::1]`;
        nothing that decides by channels.json's sourceHost reads the
        brackets."""
        url = "http://[::1]:8080/list.m3u"
        self.assertEqual((helper.source_host(url), helper.shown_source_host(url)), ("[::1]", "[::1]"))
        self.assertEqual(helper.cached_source({"sourceHost": "[::1]", "sourcePort": 8080}),
                         helper.cached_source({"sourceHost": "::1", "sourcePort": 8080}))


LOWER_V4_BODY = r"""
    var name = function (cp) { var h = cp.toString(16).toUpperCase(); while (h.length < 4) h = "0" + h; return "U+" + h }
    var table = {}
    for (var cp = 0; cp < 0x110000; cp++) {
      if (cp >= 0xd800 && cp <= 0xdfff) continue
      var ch = cp > 0xffff ? String.fromCharCode(0xd800 + ((cp - 0x10000) >> 10), 0xdc00 + ((cp - 0x10000) & 0x3ff))
                           : String.fromCharCode(cp)
      var low = ch.toLowerCase()
      if (low === ch) continue
      var parts = []
      for (var i = 0; i < low.length; i++) {
        var c = low.charCodeAt(i)
        if (c >= 0xd800 && c <= 0xdbff && i + 1 < low.length) {
          c = 0x10000 + ((c - 0xd800) << 10) + (low.charCodeAt(i + 1) - 0xdc00)
          i++
        }
        parts.push(name(c))
      }
      table[name(cp)] = parts.join(" ")
    }
    var S = String.fromCharCode
    var lower = typeof Model.lowerHost === "function" ? Model.lowerHost : function () { return "MISSING lowerHost" }
    console.log("RESULT " + JSON.stringify({ table: table, plain: (S(0x391) + S(0x3a3)).toLowerCase(),
      lowerHost: ENGINE.lowerHost.map(function (p) { return lower(p[0]) }),
      hostKey: ENGINE.hostKey.map(function (p) { return Model.hostKey(p[0]) === Model.hostKey(p[1]) }),
      labelKey: ENGINE.labelKey.map(function (p) { return Model.labelTaken(p[0], [p[1]], "") }),
      sourceHost: ENGINE.sourceHost.map(function (p) { return Model.hostOf(p[0]) }) }))
"""


class EngineLoweringTest(unittest.TestCase):
    """D-SINK-118 in the shell's own engine. Its per-code-point lowering
    table is node's, the half of tests/fixtures/casefold-diff.json that
    D-SRC-12 pins (measured 2026-11-16 on Qt 6.12: 1,488 entries, none
    different), so the 28 code points D-SRC-12 accepts split the shell from
    the helper as they split node from it, and nothing more; a tripwire for
    the next Qt. The engine applies no Final_Sigma rule (a capital sigma the
    rule reads as final lowers to the small sigma, `plain`, recorded rather than
    asserted: the fold makes the answer the same either way), and the
    model's lowering, comparisons and named host read the shared fixture's
    `engine` section as the helper and node do."""

    @unittest.skipUnless(os.access(proto_v4.QML_BIN, os.X_OK), "Qt's qml runtime is not installed")
    def test_qts_engine_lowers_as_node_does_and_reads_each_host_as_the_fixture_says(self):
        body = "    var ENGINE = %s\n%s" % (json.dumps(ENGINE, ensure_ascii=True), LOWER_V4_BODY)
        result = proto_v4.run_qml(self, body)
        self.assertNotIn("probeError", result)
        node = CASEFOLD["node"]["lower"]
        differs = sorted(set(node) ^ set(result["table"]) | {k for k in node if result["table"].get(k) != node[k]})
        self.assertEqual((len(result["table"]), differs[:8]), (len(node), []), result.get("plain"))
        got = (result["lowerHost"], result["hostKey"], result["labelKey"], result["sourceHost"])
        want = ([b for _, b in ENGINE["lowerHost"]], [same for _, _, same in ENGINE["hostKey"]],
                [same for _, _, same in ENGINE["labelKey"]], [host for _, host in ENGINE["sourceHost"]])
        self.assertEqual(got, want)


if __name__ == "__main__":
    unittest.main()
