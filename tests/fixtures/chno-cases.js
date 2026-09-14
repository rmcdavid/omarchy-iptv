// Shared vectors for Model.parseChno (M2-03 1.2, frozen interface 9.7 item 5).
//
// ONE file, run by both JavaScript engines: node requires it
// (tests/Model.test.js) and the Qt engine imports it as a QML script library
// (tests/Model.spec.qml). It is a .js rather than the .json the design named
// because a QML TestCase cannot read a local file -- XMLHttpRequest on a
// file:// URL is refused unless QML_XHR_ALLOW_FILE_READ=1 is set in the
// environment, and that is scripts/check.sh's to set, not this lane's. A
// second copy of the vectors in the spec would be exactly the mirrored logic
// CLAUDE.md 12 forbids, so the fixture moved to a form both engines can load.
// See the lane A report, request 4.
//
// Each case: { why, input, ok } and, when ok, { key, label, sort }.
// ASCII only: non-ASCII inputs are written as \uXXXX escapes.
//
// No `.pragma library`: that directive is QML-only and node's parser rejects
// it, and this file has to load in both.

var CASES = [
  { why: "bare digits", input: "1", ok: true, key: "1", label: "1", sort: 1000 },
  { why: "two digits", input: "12", ok: true, key: "12", label: "12", sort: 12000 },
  { why: "CN7 leading zeros are dropped", input: "007", ok: true, key: "7", label: "7", sort: 7000 },
  { why: "channel zero is a real channel", input: "0", ok: true, key: "0", label: "0", sort: 0 },
  { why: "all zeros collapse to one", input: "00000", ok: true, key: "0", label: "0", sort: 0 },
  { why: "surrounding spaces", input: "  12  ", ok: true, key: "12", label: "12", sort: 12000 },
  { why: "tabs", input: "\t12\t", ok: true, key: "12", label: "12", sort: 12000 },
  { why: "non-breaking space", input: "\u00a012\u00a0", ok: true, key: "12", label: "12", sort: 12000 },
  { why: "byte order mark, a paste artefact", input: "\ufeff12", ok: true, key: "12", label: "12", sort: 12000 },
  { why: "some providers write #12", input: "#12", ok: true, key: "12", label: "12", sort: 12000 },
  { why: "ATSC subchannel", input: "7.1", ok: true, key: "7.1", label: "7.1", sort: 7001 },
  { why: "CN8 hyphen is a separator on parse", input: "8-1", ok: true, key: "8.1", label: "8.1", sort: 8001 },
  { why: "leading zeros on both parts", input: "07.01", ok: true, key: "7.1", label: "7.1", sort: 7001 },
  { why: "a subchannel sorts below the next major", input: "7.999", ok: true, key: "7.999", label: "7.999", sort: 7999 },
  { why: "minor zero is not the same as no minor, but ties on sort", input: "7.0", ok: true, key: "7.0", label: "7.0", sort: 7000 },
  { why: "largest major", input: "99999", ok: true, key: "99999", label: "99999", sort: 99999000 },
  { why: "largest label the grammar admits, 9 characters", input: "99999.999", ok: true, key: "99999.999", label: "99999.999", sort: 99999999 },
  { why: "six major digits", input: "123456", ok: false },
  { why: "over the major cap", input: "100000", ok: false },
  { why: "four minor digits", input: "7.1000", ok: false },
  { why: "empty", input: "", ok: false },
  { why: "whitespace only", input: " ", ok: false },
  { why: "a lazy provider", input: "HD", ok: false },
  { why: "a hostile provider", input: "N/A", ok: false },
  { why: "a bare separator", input: "-", ok: false },
  { why: "trailing letters", input: "12a", ok: false },
  { why: "two separators", input: "1.2.3", ok: false },
  { why: "exponent notation is not a channel number", input: "1e3", ok: false },
  { why: "a separator with no minor", input: "7.", ok: false },
  { why: "a hyphen with no minor", input: "7-", ok: false },
  { why: "a minor with no major", input: ".1", ok: false },
  { why: "an inner space", input: "12 34", ok: false },
  { why: "only one leading hash is stripped", input: "##12", ok: false },
  { why: "a hash alone", input: "#", ok: false },
  { why: "a plus sign is not a digit", input: "+12", ok: false },
  { why: "1.2 step 3: Arabic-Indic digits cannot be typed on the keys we bind", input: "\u0661\u0662", ok: false },
  { why: "1.2 step 3: full-width digits likewise", input: "\uff11\uff12", ok: false },
  { why: "a full-width digit after an ASCII one still fails", input: "1\uff12", ok: false }
]

if (typeof module !== "undefined") module.exports = CASES
