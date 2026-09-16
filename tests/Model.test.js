// Unit tests for Model.js. Run: node tests/Model.test.js
// Console PASS/FAIL runner, nonzero exit on any failure (same style as the
// installed dell-power plugin, so QA can read either without a framework).
// ASCII only: non-ASCII expectations are written as \uXXXX escapes.
const Model = require("../Model.js")
// The shared vectors both languages run (CLAUDE.md: a rule written twice gets
// one fixture). tests/test_player.py reads the same file.
const playerFixture = JSON.parse(require("fs").readFileSync(require("path").join(__dirname, "fixtures/player-argv.json"), "utf8"))
// The picture-in-picture vectors, required here rather than beside the PiP
// section because the focus checks below run against the same clients list
// (D-PIP-5) and a second copy of it would be the mirrored data that lets
// two "identical" fixtures drift.
const pipFixture = require("./fixtures/pip-cases.js")

let failures = 0
let checks = 0

// How a value is rendered for comparison. NOT JSON.stringify on its own
// (audit F8): `JSON.stringify(undefined)` is the value `undefined`, so
// `check(name, Model.gone(), undefined)` compared undefined with undefined
// and passed whatever `gone()` did - including not existing. stringify also
// DROPS undefined object properties and renders NaN and Infinity as null, so
// `{a: undefined}` read equal to `{}` and `[undefined]` equal to `[null]`.
// Each of those is the difference between a check and a decoration, which is
// the whole class this round is closing. The tokens are spelled with angle
// brackets so they cannot be produced by JSON of a number, and a literal
// string that spells one is the one (documented) way to fool this.
function show(value) {
  if (value === undefined) return "<undefined>"
  return JSON.stringify(value, function (key, held) {
    if (held === undefined) return "<undefined>"
    if (typeof held === "number" && !isFinite(held)) return "<" + String(held) + ">"
    return held
  })
}

function check(name, actual, expected) {
  checks++
  // An undefined expectation is never an assertion: it is what you get from
  // a typo'd property, a renamed export or a helper that returns nothing.
  if (expected === undefined) {
    failures++
    console.log("FAIL " + name + "\n     the expectation is undefined - assert an explicit value"
      + "\n     got:  " + show(actual))
    return
  }
  const a = show(actual)
  const e = show(expected)
  if (a === e) {
    console.log("ok   " + name)
  } else {
    failures++
    console.log("FAIL " + name + "\n     got:  " + a + "\n     want: " + e)
  }
}

// A check whose *expression* may not exist yet. A missing Model export
// throws before check() is ever called, which aborts the whole run and hides
// every later count - so the before/after counts CLAUDE.md 11 asks for
// cannot be compared. This turns that into one ordinary failure.
function checkCall(name, produce, expected) {
  let actual
  try {
    actual = produce()
  } catch (error) {
    actual = "threw: " + error.message
  }
  check(name, actual, expected)
}

// ---- the runner's own comparison (audit F8) ----
// Every one of these passed against the JSON.stringify comparison this file
// shipped with, which is why they are here: a runner that cannot tell
// "absent" from "equal" makes every check below it worth less than it looks.
check("runner: undefined is not null and is rendered, not swallowed", [show(undefined) === show(null), show(undefined)], [false, "<undefined>"])
check("runner: an undefined property is not an absent one", show({ a: undefined }) === show({}), false)
check("runner: a hole in an array is not a null", show([undefined]) === show([null]), false)
check("runner: NaN and Infinity are not null", [show(NaN) === show(null), show(Infinity) === show(null)], [false, false])
check("runner: equal values still compare equal", [show({ a: 1, b: [null, "x"] }) === show({ a: 1, b: [null, "x"] }), show(0) === show(-0)], [true, true])
;(function () {
  // The guard itself: an undefined *expectation* must fail. Run one check
  // with its output swallowed, then put the counters back - that deliberate
  // failure is not a real one, and the swallowed check is not a real check.
  const wasFailures = failures
  const wasChecks = checks
  const log = console.log
  console.log = function () {}
  check("(swallowed)", undefined, undefined)
  console.log = log
  const verdict = failures - wasFailures
  failures = wasFailures
  checks = wasChecks
  check("runner: an undefined expectation is a failure, never a pass", verdict, 1)
})()

const SEP = " \u00b7 "

// ---- normalization (shared vectors with tests/test_playlist.py) ----
check("searchKey folds punctuation and case", Model.searchKey("BBC-One HD", "UK: News"), "bbc one hd uk news")
check("searchKey folds diacritics", Model.searchKey("T\u00e9l\u00e9 Qu\u00e9bec", ""), "tele quebec")
check("searchKey keeps non-Latin scripts", Model.searchKey("\u041f\u0435\u0440\u0432\u044b\u0439 \u043a\u0430\u043d\u0430\u043b", "RU"), "\u043f\u0435\u0440\u0432\u044b\u0439 \u043a\u0430\u043d\u0430\u043b ru")
check("searchKey empty group", Model.searchKey("CNN", null), "cnn")
check("searchKey multi-group string stays whole", Model.searchKey("Kids TV", "Animation;Kids;Religious"), "kids tv animation kids religious")
check("searchKey equals fold(name + ' ' + group)", Model.searchKey("A", "B"), Model.normalizeText("A" + " " + "B"))
check("normalizeText null", Model.normalizeText(null), "")
// D-QA-08 / docs/QA.md fold vectors (tests/fixtures/qa-nonascii/qa-unicode.m3u)
check("normalizeText NFD decomposed e-acute folds", Model.normalizeText("Cafe\u0301 NFD"), "cafe nfd")
check("normalizeText NFC and NFD agree", Model.normalizeText("Caf\u00e9"), Model.normalizeText("Cafe\u0301"))
check("normalizeText uppercase accents", Model.normalizeText("\u00c9COLE UPPERCASE ACCENT"), "ecole uppercase accent")
check("normalizeText Polish", Model.normalizeText("TVP \u0141\u00f3d\u017a"), "tvp lodz")
check("normalizeText letters outside the table fold via NFD", Model.normalizeText("\u01fa \u0151 \u1ebf \u00f8"), "a o e o")
check("normalizeText en dash is not ASCII punctuation, kept", Model.normalizeText("Das Erste \u2013 Stra\u00dfe"), "das erste \u2013 strasse")
check("normalizeText Cyrillic short i keeps its breve (recomposed)", Model.normalizeText("\u041f\u0435\u0440\u0432\u044b\u0439"), "\u043f\u0435\u0440\u0432\u044b\u0439")
check("normalizeText Vietnamese stacked marks fold", Model.normalizeText("Vi\u1ec7t"), "viet")
check("normalizeText Arabic / CJK kept", [Model.normalizeText("\u0627\u0644\u062c\u0632\u064a\u0631\u0629"), Model.normalizeText("NHK \u7dcf\u5408")], ["\u0627\u0644\u062c\u0632\u064a\u0631\u0629", "nhk \u7dcf\u5408"])
check("normalizeText emoji kept", Model.normalizeText("Emoji \ud83d\udcfa Channel"), "emoji \ud83d\udcfa channel")
check("normalizeText ss/ae/oe ligatures", Model.normalizeText("Stra\u00dfe \u00e6 \u0153"), "strasse ae oe")
check("tokenize", Model.tokenize("  BBC   one "), ["bbc", "one"])
check("tokenize empty", Model.tokenize("   "), [])
check("tokenize punctuation only", Model.tokenize("- / ;"), [])

// ---- ids ----
check("fnv1a32 empty", Model.fnv1a32(""), "811c9dc5")
check("fnv1a32 a", Model.fnv1a32("a"), "e40c292c")
check("fnv1a32 foobar", Model.fnv1a32("foobar"), "bf9cf968")
check("fnv1a32 utf-8 multibyte is stable", Model.fnv1a32("\u00e9\u20ac\ud83d\ude00"), Model.fnv1a32("\u00e9\u20ac\ud83d\ude00"))
check("channelId prefers explicit id", Model.channelId({ id: "t:x", tvgId: "y", url: "u" }), "t:x")
check("channelId tvg", Model.channelId({ tvgId: "bbc1.uk", url: "http://a" }), "t:bbc1.uk")
check("channelId url hash", Model.channelId({ url: "foobar" }), "u:bf9cf968")
check("channelId null", Model.channelId(null), "")
check("indexById first wins", Object.keys(Model.indexById([{ id: "a", name: 1 }, { id: "a", name: 2 }, { id: "b" }])), ["a", "b"])
check("findByUrl", Model.findByUrl([{ id: "a", url: "http://x" }, { id: "b", url: "http://y" }], "http://y").id, "b")
check("asList copies array-likes and passes arrays through", (() => { const a = [1]; const like = { length: 2, 0: "x", 1: "y" }; return [Model.asList(a) === a, Model.asList(like), Model.asList(null), Model.asList("str")] })(), [true, ["x", "y"], [], []])
check("favorites-first works with an array-like favorites list", Model.filterChannels([{ id: "1", name: "BBC One", group: "UK" }, { id: "5", name: "BBC Two", group: "UK" }], "bbc", 10, { favorites: { length: 1, 0: "5" } }).rows.map(c => c.id), ["5", "1"])
check("findByUrl miss", Model.findByUrl([{ id: "a", url: "http://x" }], "http://z"), null)

// ---- channels / groups ----
check("primaryGroup takes the first of A;B;C", Model.primaryGroup({ group: " Animation ; Kids " }), "Animation")
check("primaryGroup empty -> Ungrouped", Model.primaryGroup({ group: "" }), "Ungrouped")
check("primaryGroup null", Model.primaryGroup(null), "Ungrouped")

const prepared = Model.prepareChannels([
  { id: "1", name: "BBC One HD", group: "UK", url: "http://a", searchKey: "bbc one hd uk" },
  { tvgId: "x.uk", name: "T\u00e9l\u00e9 Qu\u00e9bec", group: "CA;FR", url: "http://b" },
  { name: "Plain", url: "http://c" },
  null,
  { id: "4", name: "UK", group: "UK", url: "http://d", searchKey: "uk uk" }
])
check("prepareChannels drops null rows", prepared.length, 4)
check("prepareChannels keeps helper searchKey and derives nameKey", [prepared[0].searchKey, prepared[0].nameKey], ["bbc one hd uk", "bbc one hd"])
check("prepareChannels computes searchKey when missing", prepared[1].searchKey, "tele quebec ca fr")
check("prepareChannels assigns id and primaryGroup", [prepared[1].id, prepared[1].primaryGroup], ["t:x.uk", "CA"])
check("prepareChannels ungrouped", [prepared[2].group, prepared[2].primaryGroup, prepared[2].searchKey, prepared[2].nameKey], ["", "Ungrouped", "plain", "plain"])
check("prepareChannels nameKey when name equals group", prepared[3].nameKey, "uk")
check("prepareChannels does not mutate input", (() => { const src = [{ name: "X", url: "u" }]; Model.prepareChannels(src); return Object.keys(src[0]) })(), ["name", "url"])
check("prepareChannels null", Model.prepareChannels(null), [])
check("prepareChannels caps a tampered cache at MAX_CHANNELS (S-07)", (() => {
  const many = []
  for (let i = 0; i < Model.MAX_CHANNELS + 7; i++) many.push({ id: "c" + i, name: "C " + i, group: "G", searchKey: "c " + i + " g" })
  const rows = Model.prepareChannels(many)
  return [Model.MAX_CHANNELS, rows.length, rows[rows.length - 1].id]
})(), [50000, 50000, "c49999"])
check("displayName never a URL (D-QA-02)", Model.prepareChannels([
  { name: "http://h.test/live/1.m3u8", tvgName: "Real Name", url: "http://h.test/live/1.m3u8" },
  { name: "", url: "http://h.test/2" },
  { name: "rtsp://cam/1", url: "rtsp://cam/1" },
  { name: "  Fine  ", url: "u" }
]).map(c => c.name), ["Real Name", "Channel 2", "Channel 3", "Fine"])
check("displayName recomputes searchKey when the name was replaced", Model.prepareChannels([{ name: "http://h.test/x", tvgName: "Arte", group: "DE", searchKey: "http h test x de" }])[0].searchKey, "arte de")
// S-04: a rendered name never starts with "-" (argv item for the notification wrapper).
check("cleanName strips leading dashes and whitespace", [Model.cleanName("--urgency=x"), Model.cleanName(" - Sports "), Model.cleanName("---"), Model.cleanName(null), Model.cleanName("A-B")], ["urgency=x", "Sports", "", "", "A-B"])
check("displayName never starts with a dash (S-04)", Model.prepareChannels([
  { name: "--urgency=critical", url: "u1" },
  { name: "---", tvgName: "-Real Name", url: "u2" },
  { name: "- ", tvgName: "--", url: "u3" },
  { name: "-Minus TV", url: "u4" }
]).map(c => c.name), ["urgency=critical", "Real Name", "Channel 3", "Minus TV"])
check("displayName cleaned name keeps a matching searchKey", Model.prepareChannels([{ name: "--Sports", group: "UK", searchKey: "sports uk" }])[0].searchKey, "sports uk")
check("looksLikeUrl", [Model.looksLikeUrl("http://x"), Model.looksLikeUrl("udp://@239.0.0.1:1234"), Model.looksLikeUrl("BBC One"), Model.looksLikeUrl("")], [true, true, false, false])

check("groupChannels playlist order with counts", Model.groupChannels(prepared).map(g => g.name + ":" + g.count), ["UK:2", "CA:1", "Ungrouped:1"])
// D-LIVE-06 / UX 2.2: Ungrouped is the last column entry wherever its first channel sits.
check("groupChannels keeps Ungrouped last", Model.groupChannels([
  { name: "A", url: "1" }, { name: "B", group: "News", url: "2" }, { name: "C", group: "", url: "3" }, { name: "D", group: "Padded", url: "4" }, { name: "E", group: "News", url: "5" }
]).map(g => g.name + ":" + g.count), ["News:2", "Padded:1", "Ungrouped:2"])
check("groupChannels only ungrouped", Model.groupChannels([{ name: "A", url: "1" }]).map(g => g.name), ["Ungrouped"])
check("groupChannels null", Model.groupChannels(null), [])
check("groupScopeId / scopeName round trip", Model.scopeName(Model.groupScopeId("UK | SPORTS")), "UK | SPORTS")
check("scopeName pinned", [Model.scopeName("recent"), Model.scopeName("favorites"), Model.scopeName("all")], ["Recent", "Favorites", "All"])
check("isPinnedScope", [Model.isPinnedScope("all"), Model.isPinnedScope("g:UK"), Model.isPinnedScope(null)], [true, false, false])

// ---- search ----
const channels = Model.prepareChannels([
  { id: "1", name: "BBC One HD", group: "UK", searchKey: "bbc one hd uk" },
  { id: "2", name: "CBBC", group: "Kids", searchKey: "cbbc kids" },
  { id: "3", name: "One America", group: "US", searchKey: "one america us" },
  { id: "4", name: "Sky News", group: "News", searchKey: "sky news news" },
  { id: "5", name: "BBC Two", group: "UK", searchKey: "bbc two uk" },
  { id: "6", name: "The One Show", group: "UK", searchKey: "the one show uk" },
  { id: "7", name: "Rai Uno", group: "One World", searchKey: "rai uno one world" }
])
// D-LIVE-01 / R3: the cap bounds search results only; an empty query browses the whole scope.
check("filterChannels empty query keeps order and is never capped", Model.filterChannels(channels, "", 2).rows.map(c => c.id), ["1", "2", "3", "4", "5", "6", "7"])
check("filterChannels empty query total/truncated", (() => { const r = Model.filterChannels(channels, "", 2); return [r.total, r.truncated] })(), [7, false])
check("filterChannels empty query returns the scope array itself (no copy)", Model.filterChannels(channels, "  ", 2).rows === channels, true)
check("filterChannels blank query on 11k rows is uncapped", (() => {
  const many = []
  for (let i = 0; i < 11041; i++) many.push({ id: "c" + i, name: "Chan " + i, group: "G", searchKey: "chan " + i + " g" })
  const r = Model.filterChannels(many, "", 200)
  return [r.rows.length, r.total, r.truncated]
})(), [11041, 11041, false])
check("filterChannels ranks name-start > word-start > name-contains > group", Model.filterChannels(channels, "one", 10).rows.map(c => c.id), ["3", "1", "6", "7"])
check("filterChannels favorites first inside a tier", Model.filterChannels(channels, "bbc", 10, ["5"]).rows.map(c => c.id), ["5", "1", "2"])
check("filterChannels favorites accepted as a state object", Model.filterChannels(channels, "bbc", 10, { favorites: ["5"] }).rows.map(c => c.id), ["5", "1", "2"])
check("filterChannels favorite never jumps a tier", Model.filterChannels(channels, "bbc", 10, ["2"]).rows.map(c => c.id), ["1", "5", "2"])
check("filterChannels AND tokens", Model.filterChannels(channels, "bbc uk", 10).rows.map(c => c.id), ["1", "5"])
check("filterChannels AND across name and group is tier 3", Model.filterChannels(channels, "world rai", 10).rows.map(c => c.id), ["7"])
check("filterChannels group matches", Model.filterChannels(channels, "kids", 10).rows.map(c => c.id), ["2"])
check("filterChannels diacritic query", Model.filterChannels(Model.prepareChannels([{ id: "q", name: "T\u00e9l\u00e9 Qu\u00e9bec", group: "CA" }]), "tele", 10).rows.map(c => c.id), ["q"])
check("filterChannels no match", Model.filterChannels(channels, "zzz", 10), { rows: [], total: 0, truncated: false })
check("filterChannels bounded with total", (() => { const r = Model.filterChannels(channels, "b", 1); return [r.rows.length, r.total, r.truncated] })(), [1, 3, true])
check("filterChannels default cap is 200", Model.MAX_ROWS_DEFAULT, 200)

// ---- D-SG-1: a group is reachable by its WORDS, never by fragments ----
// Every check below is red against the parent commit, where tier 3 accepted
// any substring of `name + " " + group`. The shape that matters is a ONE-GROUP
// list, which is what the subscriber's own 3,335-channel playlist is: there,
// every search key ends in the same words, so a fragment of the group name
// used to match every channel on the list.
const sgOne = Model.prepareChannels([
  { id: "s1", name: "USA STARZ", group: "United States" },
  { id: "s2", name: "CNN HD", group: "United States" },
  { id: "s3", name: "ESPN", group: "United States" },
  { id: "s4", name: "STATE TV", group: "United States" }
])
// RED before: each of these reported all four rows.
check("SG1 a fragment of the sole group name matches nothing by itself", Model.filterChannels(sgOne, "ted", 10).total, 0)
check("SG1 another fragment, the one QA measured", Model.filterChannels(sgOne, "ited", 10).total, 0)
check("SG1 a fragment that IS in some names keeps only those", Model.filterChannels(sgOne, "st", 10).rows.map(c => c.id), ["s4", "s1"])
check("SG1 the count is the number of real matches, not the list length", Model.filterChannels(sgOne, "sta", 10).total, 2)
// GREEN before and after: the tier still earns its place.
check("SG1 the whole group word still reaches every channel in it", Model.filterChannels(sgOne, "united", 10).total, 4)
check("SG1 the whole group phrase still works", Model.filterChannels(sgOne, "united states", 10).total, 4)
check("SG1 a name match is unaffected", Model.filterChannels(sgOne, "starz", 10).rows.map(c => c.id), ["s1"])
// A multi-group list must not lose its group tier: this is the case that
// refuted "just drop group matching" on the subscriber's other playlist.
const sgMany = Model.prepareChannels([
  { id: "m1", name: "Alpha", group: "UK | SPORTS" },
  { id: "m2", name: "Beta", group: "UK | SPORTS" },
  { id: "m3", name: "Gamma", group: "Kids" }
])
check("SG1 a whole group word still selects its group", Model.filterChannels(sgMany, "sports", 10).rows.map(c => c.id), ["m1", "m2"])
check("SG1 a fragment of a group word no longer does", Model.filterChannels(sgMany, "spor", 10).total, 0)
check("SG1 containsAllWords is whole-word, both edges", [
  Model.containsAllWords("usa starz united states", ["st"]),
  Model.containsAllWords("usa starz united states", ["united"]),
  Model.containsAllWords("usa starz united states", ["usa"]),
  Model.containsAllWords("usa starz united states", ["states"]),
  Model.containsAllWords("usa starz united states", ["united", "usa"]),
  Model.containsAllWords("usa starz united states", ["united", "nope"])
], [false, true, true, true, true, false])

// ---- D-A11Y-6: the empty state had no voice at all ----
// Found by the harness as L2-Q-05, measured on the real bus: with a query that
// matched nothing, zero rows and zero nodes named the query, so a screen-reader
// user heard silence. Ruling SG1 made that worse by design: whole-word matching
// creates a dead zone where the empty state is the ONLY thing explaining the
// screen.
check("A11Y6 title and prose are announced as one statement", Model.emptyStateAccessibleName("No matches for x", "Esc clears the search"), "No matches for x. Esc clears the search")
check("A11Y6 a title alone needs no trailing punctuation", Model.emptyStateAccessibleName("Loading", ""), "Loading")
check("A11Y6 prose alone is announced alone", Model.emptyStateAccessibleName("", "just prose"), "just prose")
check("A11Y6 nothing to say announces nothing", Model.emptyStateAccessibleName("", ""), "")
check("A11Y6 null and undefined are not the strings 'null' and 'undefined'", [
  Model.emptyStateAccessibleName(null, null),
  Model.emptyStateAccessibleName(undefined, "prose"),
  Model.emptyStateAccessibleName("title", undefined)
], ["", "prose", "title"])
check("A11Y6 the dead zone SG1 creates is the case that matters, end to end", Model.emptyStateAccessibleName(
  Model.noMatchesTitle("unit", "all"),
  "Keep typing for " + Model.groupWordHint("unit", ["United States"])),
  "No matches for \u201cunit\u201d. Keep typing for United States")

// ---- SG1: the dead zone whole-word matching creates, and what we say in it ----
// Typing toward the group name now passes through queries that match nothing
// while every visible row prints that group. A bare "No matches" there is a
// worse lie than the number it replaced, so the guide names the group instead.
check("SG1 hint fires while typing toward the sole group", Model.groupWordHint("unit", ["United States"]), "United States")
check("SG1 hint fires one keystroke later too", Model.groupWordHint("unite", ["United States"]), "United States")
check("SG1 hint is silent once the word is whole, because the query matches", Model.groupWordHint("united", ["United States"]), "")
check("SG1 hint is silent for a query going nowhere", Model.groupWordHint("zzz", ["United States"]), "")
check("SG1 hint is silent with no query", Model.groupWordHint("", ["United States"]), "")
check("SG1 hint is silent with no groups", Model.groupWordHint("unit", []), "")
check("SG1 hint needs earlier tokens to be whole words", [
  Model.groupWordHint("united stat", ["United States"]),
  Model.groupWordHint("unit stat", ["United States"])
], ["United States", ""])
check("SG1 hint picks a group on a multi-group list", Model.groupWordHint("spor", ["Kids", "UK | SPORTS"]), "UK | SPORTS")
check("SG1 hint folds case and diacritics like the search does", Model.groupWordHint("QUE", ["Qu\u00e9bec TV"]), "Qu\u00e9bec TV")

check("filterChannels default cap applied", (() => {
  const many = []
  for (let i = 0; i < 450; i++) many.push({ id: "c" + i, name: "Chan " + i, group: "G", searchKey: "chan " + i + " g" })
  const r = Model.filterChannels(many, "chan")
  return [r.rows.length, r.total, r.truncated]
})(), [200, 450, true])
check("filterChannels null input", Model.filterChannels(null, "x", 5), { rows: [], total: 0, truncated: false })
check("filterChannels raw rows without keys still match", Model.filterChannels([{ id: "r", name: "Arte HD", group: "DE" }], "arte", 5).rows.map(c => c.id), ["r"])
check("matchRank tiers", [Model.matchRank("bbc one uk", ["bbc"], "bbc one"), Model.matchRank("the bbc uk", ["bbc"], "the bbc"), Model.matchRank("cbbc uk", ["bbc"], "cbbc"), Model.matchRank("x uk", ["uk"], "x"), Model.matchRank("x uk", ["zz"], "x")], [0, 1, 2, 3, -1])
check("filterChannels 10k rows under budget", (() => {
  const many = []
  for (let i = 0; i < 10000; i++) many.push({ id: "c" + i, name: "Channel " + i + (i % 7 === 0 ? " Sports" : " News"), group: "Group " + (i % 300), url: "http://h/" + i, searchKey: "channel " + i + (i % 7 === 0 ? " sports" : " news") + " group " + (i % 300) })
  const rows = Model.prepareChannels(many)
  const t0 = Date.now()
  const r = Model.filterChannels(rows, "sports 1", 200, ["c105"])
  const ms = Date.now() - t0
  return [r.rows.length, r.rows[0].id, r.rows[1].id, r.truncated, ms < 100]
})(), [200, "c105", "c14", true, true])

// ---- scopes ----
const state = { version: 1, favorites: ["5", "missing", "1"], recents: [{ id: "4", name: "Sky News", at: 1 }, { id: "gone", name: "", at: 0 }], lastPlayed: null }
check("scopeEntries order and counts", Model.scopeEntries(channels, state).map(e => e.id + "=" + e.count), ["recent=1", "favorites=2", "all=7", "=0", "g:UK=3", "g:Kids=1", "g:US=1", "g:News=1", "g:One World=1"])
check("scopeEntries hides Recent when empty, keeps Favorites", Model.scopeEntries(channels, null).slice(0, 2).map(e => e.id), ["favorites", "all"])
check("scopeEntries header kind", Model.scopeEntries(channels, null)[2].kind, "header")
check("scopeEntries no channels -> no header", Model.scopeEntries([], null).map(e => e.id), ["favorites", "all"])
check("channelsForScope all", Model.channelsForScope(channels, "all", state).length, 7)
check("channelsForScope favorites in favorited order, skips missing", Model.channelsForScope(channels, "favorites", state).map(c => c.id), ["5", "1"])
check("channelsForScope recent", Model.channelsForScope(channels, "recent", state).map(c => c.id), ["4"])
check("channelsForScope group", Model.channelsForScope(channels, "g:UK", state).map(c => c.id), ["1", "5", "6"])
check("channelsForScope first group of multi-group", Model.channelsForScope(Model.prepareChannels([{ id: "m", name: "M", group: "A;B" }]), "g:B", null).length, 0)
check("channelsInGroup legacy names", [Model.channelsInGroup(channels, "", state).length, Model.channelsInGroup(channels, "Favorites", state).length, Model.channelsInGroup(channels, "Recent", state).length, Model.channelsInGroup(channels, "UK", state).length], [7, 2, 1, 3])
check("effectiveScope: query from Favorites/Recent searches All", [Model.effectiveScope("favorites", "sky"), Model.effectiveScope("recent", "sky"), Model.effectiveScope("all", "sky")], ["all", "all", "all"])
check("effectiveScope: group stays a scope", Model.effectiveScope("g:UK", "sky"), "g:UK")
check("effectiveScope: no query keeps pinned", Model.effectiveScope("favorites", "  "), "favorites")
const entries = Model.scopeEntries(channels, state)
check("moveScope wraps forward over the header", [Model.moveScope(entries, "all", 1), Model.moveScope(entries, "g:One World", 1)], ["g:UK", "recent"])
check("moveScope wraps backward", Model.moveScope(entries, "recent", -1), "g:One World")
check("moveScope unknown scope", Model.moveScope(entries, "nope", 1), "recent")
check("moveScope empty entries", Model.moveScope([], "x", 1), "x")
// D-LIVE-07: a hidden scope (Recent emptied, a group gone) falls back to Favorites, else All.
check("fallbackScope keeps a listed scope", [Model.fallbackScope(entries, "recent"), Model.fallbackScope(entries, "g:UK"), Model.fallbackScope(entries, "all")], ["recent", "g:UK", "all"])
check("fallbackScope hidden Recent -> Favorites when it has channels", Model.fallbackScope(Model.scopeEntries(channels, { version: 1, favorites: ["5"], recents: [], lastPlayed: null }), "recent"), "favorites")
check("fallbackScope hidden Recent -> All when Favorites is empty", Model.fallbackScope(Model.scopeEntries(channels, null), "recent"), "all")
check("fallbackScope vanished group -> All", Model.fallbackScope(Model.scopeEntries(channels, null), "g:Gone"), "all")
check("fallbackScope never lands on the header", Model.fallbackScope(Model.scopeEntries(channels, null), ""), "all")
check("fallbackScope no entries keeps the id", [Model.fallbackScope([], "g:UK"), Model.fallbackScope(null, "")], ["g:UK", "all"])
check("favoriteSet from ids or a state", [Model.favoriteSet(["a", "b"]).b, Model.favoriteSet({ favorites: ["c"] }).c, Model.favoriteSet(null).x], [true, true, undefined])
check("scopeIndex", [Model.scopeIndex(entries, "all"), Model.scopeIndex(entries, "g:UK"), Model.scopeIndex(entries, "zz")], [2, 4, -1])
// D-LIVE-16: pinned entries show the column from the top, a group is brought into view.
check("columnAnchor pinned scopes scroll to the top", [Model.columnAnchor(entries, "recent"), Model.columnAnchor(entries, "favorites"), Model.columnAnchor(entries, "all")], [{ index: 0, top: true }, { index: 1, top: true }, { index: 2, top: true }])
check("columnAnchor All is still top without Recent", Model.columnAnchor(Model.scopeEntries(channels, null), "all"), { index: 1, top: true })
check("columnAnchor group is contained, not topped", [Model.columnAnchor(entries, "g:UK"), Model.columnAnchor(entries, "g:One World")], [{ index: 4, top: false }, { index: 8, top: false }])
check("columnAnchor unknown scope or no column", [Model.columnAnchor(entries, "g:Gone"), Model.columnAnchor(entries, ""), Model.columnAnchor([], "all"), Model.columnAnchor(null, "all")], [{ index: -1, top: false }, { index: -1, top: false }, { index: -1, top: false }, { index: -1, top: false }])
check("initialScope favorites when present", Model.initialScope(channels, state), "favorites")
check("initialScope all when no favorites", Model.initialScope(channels, null), "all")
check("cursorFor playing row", Model.cursorFor(channels, "4"), 3)
check("cursorFor missing", Model.cursorFor(channels, "zz"), 0)
check("scopeLabel browsing", Model.scopeLabel("favorites", "", 6), "Favorites" + SEP + "6 channels")
check("scopeLabel one channel", Model.scopeLabel("g:UK | KIDS", "", 1), "UK | KIDS" + SEP + "1 channel")
check("scopeLabel searching moves to All", Model.scopeLabel("favorites", "sky", 14), "in All" + SEP + "14 matches")
check("scopeLabel searching in a group with thousands", Model.scopeLabel("g:UK | SPORTS", "sky", 1240), "in UK | SPORTS" + SEP + "1,240 matches")

// ---- M2-09: the guide at real provider scale ----
//
// The shapes below mirror the four real playlists this lane was measured
// against, at a size a test can hold: one group of many (the subscriber's
// 3,335 / 1), two groups (their sports list, 1,833 / 2), many small groups
// (the public list, 1,472 / 28) and a playlist with no group-title at all,
// which `groupChannels` collapses to one synthesised `Ungrouped`. The real
// caches are measured in the lane's benchmark, not asserted here: a test that
// reads a scratchpad artefact is a test that stops running.
//
// Every assertion in this section goes through `checkCall`, not `check`: most
// of these functions do not exist in v0.5.0, and a missing export throws
// before check() is reached, which aborts the run and destroys exactly the
// before/after counts CLAUDE.md rule 11 asks for. Run this file against the
// shipping Model.js and it reports 1,287 checks with the new ones red, rather
// than one stack trace.
function shapeList(spec) {
  const rows = []
  spec.forEach(function (pair) {
    for (let i = 0; i < pair[1]; i++) rows.push({ id: pair[0] + ":" + i, name: pair[0] + " Channel " + i, group: pair[0] })
  })
  return Model.prepareChannels(rows)
}
const oneGroup = shapeList([["United States", 6]])
const twoGroups = shapeList([["PPV Live Events", 4], ["US Sports", 3]])
const manyGroups = shapeList([["News", 3], ["Sports", 2], ["Movies", 4], ["Music", 1], ["Kids", 2]])
const noGroupTitle = Model.prepareChannels([{ id: "n1", name: "A" }, { id: "n2", name: "B" }])
const noFavs = { version: 1, favorites: [], recents: [], lastPlayed: null }
const oneFav = { version: 1, favorites: ["United States:0"], recents: [], lastPlayed: null }

// Several decisions in this lane are only half a decision until Guide.qml
// actually asks for them, and the source is the only place a unit gate can see
// that from -- the same pattern the player lane uses on Service.qml further
// down this file. `qmlBlock` takes an element from its `id:` to the next one.
const guideSource = require("fs").readFileSync(require("path").join(__dirname, "../Guide.qml"), "utf8")
const serviceSource = require("fs").readFileSync(require("path").join(__dirname, "../Service.qml"), "utf8")
const helperSource = require("fs").readFileSync(require("path").join(__dirname, "../bin/omarchy-iptv"), "utf8")
function qmlBlock(id) {
  const at = guideSource.indexOf("id: " + id + "\n")
  if (at === -1) return ""
  const next = guideSource.indexOf("id: ", at + 4)
  return guideSource.slice(at, next === -1 ? guideSource.length : next)
}
function qmlFunction(name) {
  const at = guideSource.indexOf("function " + name + "(")
  if (at === -1) return ""
  const next = guideSource.indexOf("\n  function ", at + 4)
  return guideSource.slice(at, next === -1 ? guideSource.length : next)
}

// D1: the axis is a property of the data -- a group is a narrowing step only
// when there is more than one, because groupChannels never emits an empty one.
checkCall("scopeSurface axis at every real shape", function () { return [oneGroup, twoGroups, manyGroups, noGroupTitle, []].map(function (list) {
  const a = Model.scopeSurface(list, noFavs).axis
  return a.count + "/" + a.narrows + "/" + a.soleGroup
}) }, ["1/false/United States", "2/true/", "5/true/", "1/false/Ungrouped", "0/false/"])
// The proof the axis stands on: the sole group returns All's own array.
checkCall("scopeSurface: the dropped entry returned an element-identical list to All", function () {
  const all = Model.channelsForScope(oneGroup, "all", noFavs)
  const group = Model.channelsForScope(oneGroup, "g:United States", noFavs)
  return [all.length, group.length, all.every(function (c, i) { return c === group[i] })]
}, [6, 6, true])
checkCall("scopeSurface drops the GROUPS header and the lone entry, keeps everything else", function () { return Model.scopeSurface(oneGroup, oneFav).entries.map(function (e) { return e.kind + "=" + e.count }) }, ["favorites=1", "all=6"])
checkCall("scopeSurface keeps the header and every entry when the axis narrows", function () { return Model.scopeSurface(twoGroups, noFavs).entries.map(function (e) { return e.id + "=" + e.count }) }, ["favorites=0", "all=7", "=0", "g:PPV Live Events=4", "g:US Sports=3"])
checkCall("scopeEntries is scopeSurface's entries, byte for byte, so its shipped callers are unmoved", function () {
  const wrapper = Model.scopeEntries(channels, state)
  return [JSON.stringify(wrapper) === JSON.stringify(Model.scopeSurface(channels, state).entries), wrapper.length]
}, [true, 9])
// P1 as an assertion, not a benchmark: ONE pass over the channel array, not
// two. groupChannels is the only thing in scopeSurface that reads `group` (the
// favourite and recent counters index by id), so counting reads of that
// property counts the passes through the module boundary -- which swapping the
// exported function cannot do, since the caller is inside the module.
function groupReadCounter(list) {
  let reads = 0
  const watched = list.map(function (row) {
    const copy = {}
    Object.keys(row).forEach(function (k) { if (k !== "group") copy[k] = row[k] })
    Object.defineProperty(copy, "group", { get: function () { reads++; return row.group }, enumerable: true })
    return copy
  })
  return { rows: watched, reads: function () { return reads } }
}
checkCall("scopeSurface walks the channel array exactly one groupChannels pass, and a second pass would double it", function () {
  const alone = groupReadCounter(manyGroups)
  Model.groupChannels(alone.rows)
  const onePass = alone.reads()
  const surface = groupReadCounter(manyGroups)
  const result = Model.scopeSurface(surface.rows, noFavs)
  const twice = groupReadCounter(manyGroups)
  Model.scopeSurface(twice.rows, noFavs)
  Model.groupChannels(twice.rows)
  return [onePass > 0, surface.reads() / onePass, twice.reads() / onePass, result.axis.count, result.entries.length]
}, [true, 1, 2, 5, 8])

// D2: a scope naming the sole group is a request for every channel, not a
// vanished scope. fallbackScope alone sends a subscriber with one favourite to
// a one-row Favorites when they asked for three thousand.
// Lazily, so a run against v0.5.0 reports every check red rather than
// throwing at module scope and printing no count at all.
function oneGroupEntries() { return Model.scopeSurface(oneGroup, oneFav).entries }
function oneGroupAxis() { return Model.scopeSurface(oneGroup, oneFav).axis }
checkCall("requestedScope: the sole group resolves to All even with a favourite listed", function () { return Model.requestedScope(oneGroupEntries(), "g:United States", oneGroupAxis()) }, "all")
checkCall("fallbackScope alone would have sent it to Favorites (the defect this repairs)", function () { return Model.fallbackScope(oneGroupEntries(), "g:United States") }, "favorites")
checkCall("requestedScope defers to fallbackScope everywhere else", function () { return [
  Model.requestedScope(oneGroupEntries(), "g:Elsewhere", oneGroupAxis()),
  Model.requestedScope(entries, "g:UK", Model.scopeSurface(channels, state).axis),
  Model.requestedScope(entries, "recent", Model.scopeSurface(channels, state).axis),
  Model.requestedScope(Model.scopeSurface(channels, null).entries, "g:Gone", Model.scopeSurface(channels, null).axis),
  Model.requestedScope(oneGroupEntries(), "", oneGroupAxis()),
  Model.requestedScope(oneGroupEntries(), "g:United States", null),
  Model.requestedScope([], "g:UK", oneGroupAxis())
] }, ["favorites", "g:UK", "recent", "all", "all", "favorites", "g:UK"])

// D3: row height is a pure function of scope kind, group axis and EPG.
checkCall("rowsHaveDetail truth table, all eight combinations", function () { return [true, false].map(function (g) {
  return [true, false].map(function (n) {
    return [true, false].map(function (e) {
      return Model.rowsHaveDetail({ scopeIsGroup: g, groupsNarrow: n, epgCarries: e })
    }).join(",")
  }).join(" | ")
}) }, ["true,false | true,false", "true,true | true,false"])
checkCall("rowShowsGroup truth table", function () { return [true, false].map(function (g) {
  return [true, false].map(function (n) { return Model.rowShowsGroup({ scopeIsGroup: g, groupsNarrow: n }) }).join(",")
}) }, ["false,false", "true,false"])
checkCall("rowsHaveDetail and rowShowsGroup default to the shipped behaviour on an absent flag", function () { return [
  Model.rowsHaveDetail({}), Model.rowsHaveDetail({ scopeIsGroup: true }), Model.rowShowsGroup({}), Model.rowShowsGroup({ scopeIsGroup: true })
] }, [true, false, true, false])
// The hazard this lane removed: a failure term here made row height depend on
// session state, so one dead stream re-heighted a whole scope under the cursor.
checkCall("rowsHaveDetail never reads a failure flag", function () {
  const answers = []
  const reads = {}
  ;[true, false].forEach(function (g) {
    [true, false].forEach(function (n) {
      [true, false].forEach(function (e) {
        const plain = { scopeIsGroup: g, groupsNarrow: n, epgCarries: e }
        const failing = { scopeIsGroup: g, groupsNarrow: n, epgCarries: e, failedAt: "07:12", anyFailed: true, failedMap: { x: "07:12" } }
        answers.push(Model.rowsHaveDetail(plain) === Model.rowsHaveDetail(failing))
        Model.rowsHaveDetail(new Proxy(plain, { get: function (t, k) { reads[String(k)] = true; return t[k] } }))
      })
    })
  })
  return [answers.every(Boolean), Object.keys(reads).sort()]
}, [true, ["epgCarries", "groupsNarrow", "scopeIsGroup"]])

// ---- GS9 / D-GS-2: the second line is decided by the data, not by a setting.
//
// The caveat this replaces said that configuring guide data correctly returns
// the second line and reverses the density win. On the subscriber's provider
// it returns it BLANK on every row: one of their 3,335 channels carries a
// `tvg-id` at all, and it matches nothing in the guide data. Three visible
// rows spent on white space is the defect D3 removed, wearing a different hat.
checkCall("GS9: a configured EPG does not height a row; guide data that reaches the rows does", function () { return [
  Model.rowsHaveDetail({ scopeIsGroup: false, groupsNarrow: false, epgConfigured: true }),
  Model.rowsHaveDetail({ scopeIsGroup: false, groupsNarrow: false, epgCarries: true }),
  Model.rowsHaveDetail({ scopeIsGroup: false, groupsNarrow: false, epgCarries: false }),
  Model.rowsHaveDetail({ scopeIsGroup: true, groupsNarrow: true, epgCarries: true })
] }, [false, true, false, true])

// The subscriber's shape at a size a test can hold: a list whose channels
// carry no usable identifier, and one that does.
const noTvgIds = Model.prepareChannels([
  { id: "u1", name: "USA FOX NEWS", group: "United States" },
  { id: "u2", name: "(PLUTO USA) Comedy Central", group: "United States" },
  { id: "u3", name: "US Escape", group: "United States", tvgId: "escape.us" }
])
const matchedIds = Model.prepareChannels([
  { id: "m1", name: "CNN", group: "News", tvgId: "cnn.us" },
  { id: "m2", name: "BBC One", group: "UK", tvgId: "bbc1.uk" },
  { id: "m3", name: "No Guide Data", group: "News" }
])
const epgWindow = { "cnn.us": { now: { title: "The Lead", start: 100, stop: 200 }, next: { title: "The Situation Room", start: 200 } } }
checkCall("GS9: epgCoverage counts the rows guide data can fill, not the rows that exist", function () { return [
  // the live pass's shape: an EPG is loaded, and it matches nothing here
  Model.epgCoverage(noTvgIds, { "cnn.us": { now: { title: "The Lead" } } }),
  // the same playlist with no guide data at all
  Model.epgCoverage(noTvgIds, {}),
  // one matching channel is enough: the line then carries something on a row
  Model.epgCoverage(matchedIds, epgWindow)
] }, [
  { total: 3, withId: 1, matched: 0, carries: false },
  { total: 3, withId: 1, matched: 0, carries: false },
  { total: 3, withId: 2, matched: 1, carries: true }
])
checkCall("GS9: an entry with no titled programme is not coverage, and a next-only entry is", function () { return [
  Model.epgCoverage(matchedIds, { "cnn.us": {} }).carries,
  Model.epgCoverage(matchedIds, { "cnn.us": { now: { title: "" }, next: { title: "" } } }).carries,
  Model.epgCoverage(matchedIds, { "cnn.us": { next: { title: "Newsnight", start: 200 } } }).carries,
  Model.epgCoverage(matchedIds, { "cnn.us": null }).carries,
  Model.epgCoverage(matchedIds, null).carries,
  Model.epgCoverage(null, epgWindow),
  Model.epgCoverage([], epgWindow).carries
] }, [false, false, true, false, false, { total: 0, withId: 0, matched: 0, carries: false }, false])
// The stability requirement, and the reason it is measured on the identifier:
// `epgFields` hides a `now` whose stop has passed, so a coverage rule that
// counted what is ON AIR would flip on the 30 s tick and re-height the list
// under the cursor. This function takes no clock at all.
checkCall("GS9: coverage does not expire -- the same window answers the same at any hour", function () {
  const expired = { "cnn.us": { now: { title: "The Lead", start: 100, stop: 200 } } }
  const later = Model.epgFields(expired["cnn.us"], 9999)
  return [Model.epgCoverage(matchedIds, expired).carries, later.nowTitle, later.until, Model.epgCoverage.length]
}, [true, "", "", 2])
// A tvg-id is provider text: `constructor` and `toString` are on every object
// and would count as coverage on a playlist that happens to use them.
checkCall("GS9: an inherited property name is not guide data", function () { return [
  Model.epgCoverage(Model.prepareChannels([{ id: "p1", name: "Proto", tvgId: "constructor" }, { id: "p2", name: "Str", tvgId: "toString" }]), {}),
  Model.epgCoverage(Model.prepareChannels([{ id: "p1", name: "Proto", tvgId: "constructor" }]), { constructor: { now: { title: "Real" } } }).carries
] }, [{ total: 2, withId: 2, matched: 0, carries: false }, true])
// R-C, and the trap an earlier round of this work named: the verdict is taken
// once, in open(), BEFORE the card is composed, and held while it is on screen.
// A binding on `epgMap` would re-height every row the moment an EPG fetch
// landed, mid-session, under the cursor -- which is exactly what deleting
// `anyFailedInScope` was for.
check("GS9: Guide.qml measures the coverage at open and holds it, rather than binding it", [
  /property bool rowsHaveDetail: Model\.rowsHaveDetail\(\{[\s\S]{0,200}?epgCarries: root\.epgCarriesRows/.test(guideSource),
  /\n  property bool epgCarriesRows: false\n/.test(guideSource),
  (guideSource.match(/Model\.epgCoverage\(/g) || []).length,
  (qmlFunction("measureEpgRows").match(/Model\.epgCoverage\(/g) || []).length,
  qmlFunction("open").indexOf("root.measureEpgRows()") !== -1
    && qmlFunction("open").indexOf("root.measureEpgRows()") < qmlFunction("open").indexOf("root.rebuildDisplay()"),
  /epgCarries: root\.epgConfigured/.test(guideSource),
  /readonly property bool epgCarriesRows/.test(guideSource),
  // and on the axis's own cadence: once per channel-set change, past the
  // groupsDirty guard, so a source switch cannot leave the previous source's
  // verdict standing over a different channel set
  /root\.groupsDirty = false\n[\s\S]{0,400}?root\.measureEpgRows\(\)/.test(qmlFunction("rebuildGroups")),
  (guideSource.match(/root\.measureEpgRows\(\)/g) || []).length
], [true, true, 1, 1, true, false, false, true, 2])

// ---- GS11 / D-GS-4: a setting the user cleared must not come back because a
// file outlived it.
//
// Clearing a source's guide URL left epg-now.json, epg-status.json and
// epg-window.txt in its cache, so the next start loaded them and the
// guide-data warning they carry was back in the footer for a guide source
// that is no longer configured. Removing a source already deletes its whole
// directory; this is the same rule for the part of it one setting owns.
// The handler's DECLARATION, not the first mention of its name: a comment
// elsewhere that points at it is not the thing being asserted about.
function qmlHandler(source, name) {
  const at = source.indexOf("\n  on" + name + "Changed")
  if (at === -1) return ""
  const next = source.indexOf("\n  on", at + 4)
  return source.slice(at, next === -1 ? source.length : next)
}
check("GS11: clearing the active guide URL queues the cache job in the handler that clears it in memory", [
  /root\.queueCacheJob\(\["epg-clear", "--key", root\.activeSourceKey\], null\)/.test(qmlHandler(serviceSource, "ActiveEpgUrl")),
  // inside the cleared branch, not after it: the handler returns there
  qmlHandler(serviceSource, "ActiveEpgUrl").indexOf("epg-clear") < qmlHandler(serviceSource, "ActiveEpgUrl").indexOf("return"),
  // and never for a source that does not exist, which would be a job with an
  // empty key for the helper to refuse
  /if \(root\.activeSourceKey !== ""\) root\.queueCacheJob\(\["epg-clear"/.test(serviceSource)
], [true, true, true])
check("GS11: an inactive source's cleared guide URL takes its cache too, where activeEpgUrl never moves", [
  /key !== root\.activeSourceKey && String\(rec\.epgUrl \|\| ""\) !== "" && next && String\(next\.epgUrl \|\| ""\) === ""/.test(serviceSource),
  (serviceSource.match(/"epg-clear"/g) || []).length
], [true, 2])
// The two implementations of one verb: the service names an action the helper
// has to have, and a rename on either side is how they drift.
check("GS11: the helper implements the action the service asks for, and it is not `remove` in disguise", [
  /cache_actions\.add_parser\("epg-clear"/.test(helperSource),
  /elif action == "epg-clear":\n\s+payload = cache_epg_clear\(directory, args\.key\)/.test(helperSource),
  /def cache_epg_clear\(directory: str, key: str\)/.test(helperSource),
  // it walks the EPG names only, and it does not rmdir the source's directory
  /def cache_epg_clear[\s\S]{0,1400}?for name in EPG_CACHE_FILES/.test(helperSource),
  /def cache_epg_clear[\s\S]{0,1400}?os\.rmdir/.test(helperSource)
], [true, true, true, true, false])

// D4: the mandated words come from one constant, so the two slots cannot drift.
checkCall("rowFailedMeta and rowDetail build the failure notice from the same words", function () { return [Model.rowFailedMeta("07:12"), Model.rowDetail({ failedAt: "07:12" }), Model.rowDetail({ showGroup: true, group: "US Sports", failedAt: "07:12" }), Model.rowFailedMeta("")] },
  ["Failed 07:12" + SEP + "Space to retry", "Failed 07:12" + SEP + "Space to retry", "US Sports" + SEP + "Failed 07:12" + SEP + "Space to retry", ""])
checkCall("the failure notice is 29 characters at the measured width", function () { return Model.rowFailedMeta("07:12").length }, 29)
// The meta slot's whole decision, lifted out of the QML ternary so it is
// asserted rather than only looked at (CLAUDE.md rule 12). The middle row of
// this table is the one that makes D4 safe: a failed row's meta slot was
// ALREADY blank, which is why the notice could move into it.
checkCall("rowMeta: the slot carries the notice exactly when the row has no detail line to carry it", function () {
  return [
    Model.rowMeta({ failedAt: "07:12", until: "", hasDetail: false }),
    Model.rowMeta({ failedAt: "07:12", until: "21:00", hasDetail: false }),
    Model.rowMeta({ failedAt: "07:12", until: "21:00", hasDetail: true }),
    Model.rowMeta({ failedAt: "", until: "21:00", hasDetail: true }),
    Model.rowMeta({ failedAt: "", until: "21:00", hasDetail: false }),
    Model.rowMeta({ failedAt: "", until: "", hasDetail: false }),
    Model.rowMeta(null)
  ]
}, ["Failed 07:12" + SEP + "Space to retry", "Failed 07:12" + SEP + "Space to retry", "", "until 21:00", "until 21:00", "", ""])

// ---- GS8 / D-GS-1: the string that names a key is not the faintest text on
// the row.
//
// The live pass measured `Failed HH:MM - Space to retry` at 3.78:1 on the
// CURSOR row against a 4.5:1 threshold, the only text on the card under it,
// because UX 5.3's dim rung was applied over the selected row's lighter fill.
// The rung is the whole fix, so the rung is what the shipping code decides and
// what is asserted here -- and then the consequence is COMPUTED, from the real
// menu tokens of every theme installed on this machine
// (tests/fixtures/menu-contrast.json), because a ratio measured on one theme
// is not evidence about the next one. WCAG 2.1 relative luminance; the row
// fills are the composites Color.qml builds from the same three tokens.
const menuTokens = JSON.parse(require("fs").readFileSync(require("path").join(__dirname, "fixtures/menu-contrast.json"), "utf8"))
function rgbOf(value) {
  const h = String(value).replace("#", "")
  return [0, 2, 4].map(function (i) { return parseInt(h.slice(i, i + 2), 16) })
}
// These CALL the shipping arithmetic rather than keeping a private copy
// (CLAUDE.md rule 12). They were local while nothing shipped a decision made
// with them; D-RUNG-4 and D-RUNG-5 both do now, so a second implementation
// here could agree with itself while the guide was wrong.
const composite = Model.colorOver
const luminance = Model.relativeLuminance
const contrast = Model.contrastRatio
// One theme -> the two row fills and the two text colours the delegate uses.
function menuSurface(theme) {
  const background = rgbOf(theme.background)
  const text = rgbOf(theme.foreground)
  return {
    rowFill: background,
    cursorFill: composite(text, background, menuTokens.selectedBackgroundAlpha),
    text: text,
    selectedText: rgbOf(theme.accent)
  }
}
// The notice as the row renders it: Color.menu.text at the rung the shipping
// code chooses, over whichever fill the row has.
function noticeRatio(theme, onCursor, alpha) {
  const s = menuSurface(theme)
  const fill = onCursor ? s.cursorFill : s.rowFill
  return contrast(composite(s.text, fill, alpha), fill)
}
function round2(n) { return Math.round(n * 100) / 100 }
const reference = menuTokens.themes[0]

checkCall("rowNoticeEmphasis: the failure notice carries no de-emphasis, ambient meta keeps the dim rung", function () { return [
  Model.rowNoticeEmphasis("07:12"), Model.rowNoticeEmphasis(""), Model.rowNoticeEmphasis(null), Model.rowNoticeEmphasis(undefined),
  Model.TEXT_DIM, Model.TEXT_FULL
] }, [1, 0.52, 0.52, 0.52, 0.52, 1])
// The defect, and the repair, on the exact theme docs/QA-RESULTS.md measured.
checkCall("GS8: the notice on the cursor row was under AA and is not any more (" + reference.name + ")", function () {
  const shipped = Model.rowNoticeEmphasis("07:12")
  return [
    round2(noticeRatio(reference, false, Model.TEXT_DIM)), round2(noticeRatio(reference, true, Model.TEXT_DIM)),
    round2(noticeRatio(reference, false, shipped)), round2(noticeRatio(reference, true, shipped)),
    noticeRatio(reference, true, Model.TEXT_DIM) < 4.5, noticeRatio(reference, true, shipped) >= 4.5
  ]
}, [3.54, 3.52, 10.82, 9.7, true, true])
// And on every other theme this machine has, because the fix is not allowed to
// be a property of one palette.
// ---- The contrast model, calibrated against real pixels ----
// A design was REFUSED on the belief that this arithmetic reads 1.25 ratio
// points low against reality. It does not. The old pass had measured the
// failure GLYPH, drawn at opacity 0.8, and compared it against a value
// computed for the 0.52 text rung; on retropc, 0.8 computes to 7.13, which is
// exactly the figure that pass reported as its peak.
//
// Measured properly on 2026-09-15 off screenshots of the running guide, on a
// dark theme and a light one, the model is accurate to within 0.14 and is
// always slightly OPTIMISTIC. That direction is the load-bearing part: a
// design that computes exactly 4.50 renders BELOW the threshold, which is why
// every contrast target on this project must sit above the line and never on
// it (see BAR_IDLE_DARKEN, chosen for a 4.71 floor).
const calib = JSON.parse(require("fs").readFileSync(require("path").join(__dirname, "fixtures/contrast-calibration.json"), "utf8"))
function calibPredicted(sample) {
  const theme = menuTokens.themes.filter(function (t) { return t.name === sample.theme })[0]
  const s = menuSurface(theme)
  const fill = sample.surface === "cursor" ? s.cursorFill : s.rowFill
  return contrast(composite(s.text, fill, sample.alpha), fill)
}
checkCall("calibration: every sample's theme is in the contrast fixture, so a rename cannot silently skip one", function () {
  return calib.samples.every(function (sm) { return menuTokens.themes.some(function (t) { return t.name === sm.theme }) })
}, true)
checkCall("calibration: the model predicts every rendered measurement within tolerance", function () {
  return calib.samples.map(function (sm) { return Math.abs(calibPredicted(sm) - sm.measured) <= calib.maxAbsError })
}, [true, true, true, true, true, true])
checkCall("calibration: the model is OPTIMISTIC in every sample, never pessimistic", function () {
  // If this ever goes red the sign of the error has flipped and every "target
  // above the line" decision on this project needs revisiting.
  return calib.samples.every(function (sm) { return calibPredicted(sm) >= sm.measured })
}, true)
checkCall("calibration: the refuted claim, restated as a number so it cannot come back", function () {
  const worst = calib.samples.reduce(function (w, sm) { return Math.max(w, Math.abs(calibPredicted(sm) - sm.measured)) }, 0)
  // The claim was 1.25. The truth is an order of magnitude smaller.
  return [round2(worst) < 0.2, round2(worst) < 1.25]
}, [true, true])
checkCall("calibration: on retropc, opacity 0.8 computes to the 7.13 the old pass reported as its peak", function () {
  // Within a hundredth; the claim is that the old pass measured the 0.8 glyph
  // and not the 0.52 rung, not a figure to the second decimal. The dim rung it
  // was compared against computes 3.53, nowhere near.
  const retro = menuTokens.themes.filter(function (t) { return t.name === "retropc" })[0]
  const s = menuSurface(retro)
  const atPointEight = contrast(composite(s.text, s.rowFill, 0.8), s.rowFill)
  const atDimRung = contrast(composite(s.text, s.rowFill, Model.TEXT_DIM), s.rowFill)
  return [Math.abs(atPointEight - 7.13) < 0.02, Math.abs(atDimRung - 7.13) > 3]
}, [true, true])

// ---- D-RUNG-4: the accent ink on the cursor row ----
// The accent is under 4.5:1 against its OWN selected fill in 8 of 23 themes at
// full opacity, worst 2.80. No opacity change reaches that; only the ink can.
// The menu fixture IS valid here, unlike for the bar (see D-RUNG-6): a capture
// of the running guide on rose-pine measured the channel name at 6.59:1 where
// this model says 6.66, and the detail line at 2.28 where it says 2.33.
function cursorSurface(theme) {
  const text = rgbOf(theme.foreground)
  const fill = composite(text, rgbOf(theme.background), menuTokens.selectedBackgroundAlpha)
  return { text: text, fill: fill, accent: rgbOf(theme.accent) }
}
checkCall("D-RUNG-4: the eight themes that fail, and by how far, before any change", function () {
  return menuTokens.themes.filter(function (t) {
    const s = cursorSurface(t)
    return contrast(s.accent, s.fill) < 4.5
  }).map(function (t) { return t.name }).sort()
}, ["catppuccin-latte", "lupine", "miasma", "nord", "osaka-jade", "rose-pine", "solitude", "white"])
checkCall("D-RUNG-4: fifteen themes keep their accent untouched, byte-identical on screen", function () {
  const untouched = menuTokens.themes.filter(function (t) {
    const s = cursorSurface(t)
    return Model.cursorInkMix(s.accent, s.text, s.fill) === 0
  })
  return untouched.length
}, 15)
checkCall("D-RUNG-4: the eight mix fractions, so the COST is a number and not an impression", function () {
  // Returned as PAIRS ordered by how far the ink had to travel, so the list
  // reads as the cost it is: rose-pine gives up 70 per cent of its accent
  // distance, white 7.
  return menuTokens.themes.map(function (t) {
    const s = cursorSurface(t)
    return [t.name, Model.cursorInkMix(s.accent, s.text, s.fill)]
  }).filter(function (p) { return p[1] > 0 }).sort(function (a, b) { return a[1] - b[1] })
}, [["white", 0.07], ["lupine", 0.11], ["solitude", 0.15], ["osaka-jade", 0.18], ["nord", 0.3], ["catppuccin-latte", 0.35], ["miasma", 0.42], ["rose-pine", 0.7]])
checkCall("D-RUNG-4: every theme clears the target after the change", function () {
  const under = menuTokens.themes.filter(function (t) {
    const s = cursorSurface(t)
    return contrast(Model.cursorInk(s.accent, s.text, s.fill), s.fill) < Model.CURSOR_INK_TARGET
  })
  const floor = menuTokens.themes.reduce(function (lo, t) {
    const s = cursorSurface(t)
    return Math.min(lo, contrast(Model.cursorInk(s.accent, s.text, s.fill), s.fill))
  }, Infinity)
  return [under.length, Math.round(floor * 10000) / 10000]
}, [0, 4.7025])
checkCall("D-RUNG-4: the target sits ABOVE the line by the measured loss at this text size", function () {
  // Rose-pine capture: this arithmetic is optimistic by about 1 per cent at
  // title size (the channel name) and 2 per cent at body size (the number).
  // 4.70 therefore renders near 4.62. The same target would NOT be safe for
  // caption-size text, which lost 7 to 9 per cent in the same capture.
  const floor = 4.7025
  return [Model.CURSOR_INK_TARGET > Model.WCAG_AA_TEXT, floor * 0.98 > Model.WCAG_AA_TEXT]
}, [true, true])
checkCall("D-RUNG-4: the QML seam returns a usable colour string", function () {
  const rp = menuTokens.themes.filter(function (t) { return t.name === "rose-pine" })[0]
  const s = cursorSurface(rp)
  const qml = function (rgb) { return { r: rgb[0] / 255, g: rgb[1] / 255, b: rgb[2] / 255 } }
  const hex = Model.cursorInkHex(qml(s.accent), qml(s.text), qml(s.fill))
  return [/^#[0-9a-f]{6}$/.test(hex), hex === Model.hexOf(Model.cursorInk(s.accent, s.text, s.fill))]
}, [true, true])
checkCall("D-RUNG-4: at the OLD 0.8 rung the number fails in 16 of 23 themes even with the corrected ink", function () {
  // Why the number had to go to full opacity rather than inherit the shared
  // ink alone. Floor 3.25 at 0.8; three themes cannot be rescued by any ink at
  // that rung. This is the arithmetic behind the decision, asserted so the
  // decision cannot be quietly undone.
  const under = menuTokens.themes.filter(function (t) {
    const s = cursorSurface(t)
    const ink = Model.cursorInk(s.accent, s.text, s.fill)
    return contrast(composite(ink, s.fill, 0.8), s.fill) < 4.5
  })
  const floor = menuTokens.themes.reduce(function (lo, t) {
    const s = cursorSurface(t)
    const ink = Model.cursorInk(s.accent, s.text, s.fill)
    return Math.min(lo, contrast(composite(ink, s.fill, 0.8), s.fill))
  }, Infinity)
  return [under.length, round2(floor)]
}, [16, 3.25])
checkCall("D-RUNG-4: and the shipping code actually asks for full opacity there", function () {
  // The mutant that survived the first time this was written: reverting the
  // rung to 0.8 left every other check green, because nothing read the rung.
  const src = require("fs").readFileSync(require("path").join(__dirname, "..", "Guide.qml"), "utf8")
  const code = src.split("\n").filter(function (l) { return !/^\s*\/\//.test(l) }).join("\n")
  return [
    (code.match(/hasCursor \? 0\.8 : 0\.52/g) || []).length,
    (code.match(/row\.hasCursor \? 1 : 0\.52/g) || []).length
  ]
}, [0, 1])

checkCall("D-RUNG-4: NO site inks with the raw accent over the selected fill", function () {
  // The design's own gate counted only `hasCursor ? root.selectedText` and
  // reported clean while a fifth site spelled it as a property assignment --
  // `selectedText: root.selectedText`, handed to the host's ConfirmDialog,
  // whose selected button draws that colour over that same fill, one keypress
  // from the remove-source dialog. Both forms are counted here. False
  // assurance from the one check whose job is to prove the guide asks is worse
  // than no check.
  const src = require("fs").readFileSync(require("path").join(__dirname, "..", "Guide.qml"), "utf8")
  const code = src.split("\n").filter(function (l) { return !/^\s*\/\//.test(l) }).join("\n")
  return [
    (code.match(/hasCursor \? root\.selectedText/g) || []).length,
    (code.match(/selectedText: root\.selectedText/g) || []).length,
    (code.match(/root\.cursorInk/g) || []).length >= 4
  ]
}, [0, 0, true])

// ---- D-RUNG-3 / D-RUNG-5: the bar's idle glyph, always on screen ----
//
// READ THIS BEFORE ADDING A THRESHOLD ASSERTION HERE. The fixture below is
// menu-contrast.json, and it models the MENU surface. D-RUNG-3 used it for the
// bar on the reasoning that no theme overrides `bar.text` or `bar.background`,
// so both fall back to the theme foreground and background. The tokens do fall
// back. THE RENDERED BAR DOES NOT MATCH THEM.
//
// Measured on the running shell on rose-pine, captured with grim:
//   bar background         #faf4ed   matches the theme, as modelled
//   bar text, full         #a8a3b3   2.25:1   -- the model says 6.66:1
//   our idle glyph         #a09ba7   2.48:1   -- BOLDER than full strength
// The bar draws its content at roughly half opacity, which the token chain
// does not express, so the ceiling on the real bar is about 2.25:1 and NO
// alpha applied to that ink can reach 4.5:1.
//
// So D-RUNG-3's claim that the idle glyph "clears 4.5:1 in all 23 themes",
// which shipped in 0.7.0, is FALSE on the running bar. It is filed as
// D-RUNG-6. The assertions here are confined to what the screen confirms:
// the ORDERING of idle against active, which is D-RUNG-5 and is real.
function qtDarker(rgb, factor) {
  const r = rgb[0] / 255, g = rgb[1] / 255, b = rgb[2] / 255
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn
  let h = 0
  if (d) {
    if (mx === r) h = ((g - b) / d) % 6
    else if (mx === g) h = (b - r) / d + 2
    else h = (r - g) / d + 4
    h *= 60
    if (h < 0) h += 360
  }
  const sat = mx === 0 ? 0 : d / mx
  let v = mx / factor
  if (v > 1) v = 1
  const c = v * sat, x = c * (1 - Math.abs((h / 60) % 2 - 1)), m = v - c
  let p
  if (h < 60) p = [c, x, 0]
  else if (h < 120) p = [x, c, 0]
  else if (h < 180) p = [0, c, x]
  else if (h < 240) p = [0, x, c]
  else if (h < 300) p = [x, 0, c]
  else p = [c, 0, x]
  return p.map(function (q) { return Math.round((q + m) * 255) })
}
// The ORDER of these two is what the bar's own opacity cannot change: a
// uniform factor applied to both ink and its comparison leaves which-is-dimmer
// untouched. That is why the ordering assertions survive the modelling error
// and the threshold assertions do not.
function barIdle(t) { return Model.colorOver(rgbOf(t.foreground), rgbOf(t.background), Model.BAR_IDLE_ALPHA) }
function barActive(t) { return rgbOf(t.foreground) }
function barBg(t) { return rgbOf(t.background) }
checkCall("D-RUNG-5: the idle glyph is no longer BOLDER than the active one anywhere", function () {
  // The defect, as a user would see it, and confirmed on a real screen:
  // rose-pine measured idle 2.48:1 against active 2.25:1 before this change.
  const now = menuTokens.themes.filter(function (t) { return contrast(barIdle(t), barBg(t)) >= contrast(barActive(t), barBg(t)) })
  const before = menuTokens.themes.filter(function (t) { return contrast(qtDarker(rgbOf(t.foreground), 1.25), barBg(t)) >= contrast(barActive(t), barBg(t)) })
  return [before.map(function (t) { return t.name }).sort(), now.length]
}, [["catppuccin-latte", "flexoki-light", "lupine", "rose-pine", "white"], 0])
checkCall("D-RUNG-5: `white` dims for the first time, where darkening pure black was a no-op", function () {
  const w = menuTokens.themes.filter(function (t) { return t.name === "white" })[0]
  const active = contrast(barActive(w), barBg(w))
  return [round2(contrast(qtDarker(rgbOf(w.foreground), 1.25), barBg(w))) === round2(active),
          contrast(barIdle(w), barBg(w)) < active]
}, [true, true])
checkCall("D-RUNG-5: idle is dimmer than active in EVERY theme, dark and light alike", function () {
  // Qt.darker could only ever satisfy this on dark themes. Alpha satisfies it
  // everywhere, and unlike a threshold this survives the bar's own opacity.
  return menuTokens.themes.every(function (t) { return contrast(barIdle(t), barBg(t)) < contrast(barActive(t), barBg(t)) })
}, true)
checkCall("D-RUNG-6: no threshold claim is made about the bar from this fixture", function () {
  // A guard, not a measurement. The fixture models the menu; the running bar
  // renders at roughly half this opacity, so a 4.5:1 assertion built on it is
  // green while the screen is at 2.25:1. If you want a threshold here, measure
  // the bar and build a bar fixture.
  const src = require("fs").readFileSync(__filename, "utf8")
  const block = src.slice(src.indexOf("D-RUNG-3 / D-RUNG-5: the bar's idle glyph"), src.indexOf("guide state machine"))
  return [/barIdle\([^)]*\)[^\n]*<\s*4\.5/.test(block), /4\.5\s*[<>]=?[^\n]*barIdle/.test(block)]
}, [false, false])

checkCall("GS8: the notice clears 4.5:1 on both row states in every installed theme, and the dim rung did not", function () {
  const shipped = Model.rowNoticeEmphasis("07:12")
  const under = function (alpha) {
    return menuTokens.themes.filter(function (t) { return noticeRatio(t, false, alpha) < 4.5 || noticeRatio(t, true, alpha) < 4.5 }).length
  }
  const floor = menuTokens.themes.reduce(function (lowest, t) { return Math.min(lowest, noticeRatio(t, false, shipped), noticeRatio(t, true, shipped)) }, Infinity)
  return [menuTokens.themes.length, under(Model.TEXT_DIM), under(shipped), round2(floor) >= 4.5]
}, [23, 20, 0, true])
// GS8 in the product owner's own words: the text that tells someone what to do
// must be the most legible thing on the row, not the least. The channel name is
// the row's own benchmark -- Color.menu.text on an ordinary row, and the
// theme's accent (`menu.selected-text`) on the cursor row.
checkCall("GS8: the notice is never less legible than the channel name beside it", function () {
  const shipped = Model.rowNoticeEmphasis("07:12")
  const weaker = menuTokens.themes.filter(function (t) {
    const s = menuSurface(t)
    return noticeRatio(t, false, shipped) < contrast(s.text, s.rowFill) - 1e-9
      || noticeRatio(t, true, shipped) < contrast(s.selectedText, s.cursorFill) - 1e-9
  })
  const wasWeaker = menuTokens.themes.filter(function (t) {
    const s = menuSurface(t)
    return noticeRatio(t, true, Model.TEXT_DIM) < contrast(s.selectedText, s.cursorFill) - 1e-9
  })
  return [weaker.map(function (t) { return t.name }), wasWeaker.length]
  // 22 of 23 and not all 23: `vantablack` is pure white text on pure black
  // with a grey accent, so its cursor-row name (5.53:1) was already fainter
  // than the dimmed notice (5.63:1). It is the one theme where the notice was
  // not the weakest text on the row, and it still clears the threshold after.
}, [[], 22])
// Both slots the notice can land in have to ask, or the ratios above are a
// property of a function nothing calls.
check("GS8: the meta slot and the detail line both take their rung from the shipping decision", [
  /opacity: Model\.rowNoticeEmphasis\(row\.failedAt\)/.test(qmlBlock("meta")),
  /opacity: Model\.rowNoticeEmphasis\(row\.failedAt\)/.test(qmlBlock("detailText")),
  /opacity: 0\.52/.test(qmlBlock("meta")),
  /opacity: 0\.52/.test(qmlBlock("detailText")),
  (guideSource.match(/Model\.rowNoticeEmphasis\(/g) || []).length
], [true, true, false, false, 2])

// D5: the header count becomes a position exactly when the list overflows.
checkCall("scopeLabel: the four forms", function () { return [
  Model.scopeLabel("favorites", "", 6),
  Model.scopeLabel("all", "", 3335, { index: 1203, rows: 3335, overflows: true }),
  Model.scopeLabel("all", "sky", 8),
  Model.scopeLabel("all", "sky", 2227, { index: 13, rows: 200, overflows: true })
] }, ["Favorites" + SEP + "6 channels", "All" + SEP + "1,204 of 3,335", "in All" + SEP + "8 matches", "in All" + SEP + "14 of 200"])
checkCall("scopeLabel: the boundary where the list stops overflowing", function () { return [
  Model.scopeLabel("all", "", 3335, { index: 0, rows: 3335, overflows: true }),
  Model.scopeLabel("all", "", 3335, { index: 0, rows: 3335, overflows: false }),
  Model.scopeLabel("all", "", 12, { index: 11, rows: 12, overflows: false })
] }, ["All" + SEP + "1 of 3,335", "All" + SEP + "3,335 channels", "All" + SEP + "12 channels"])
checkCall("scopeLabel: the position is clamped to the rows the list holds", function () { return [
  Model.scopeLabel("all", "", 5, { index: 99, rows: 5, overflows: true }),
  Model.scopeLabel("all", "", 5, { index: -4, rows: 5, overflows: true }),
  Model.scopeLabel("all", "", 0, { index: 0, rows: 0, overflows: true })
] }, ["All" + SEP + "5 of 5", "All" + SEP + "1 of 5", "All" + SEP + "1 of 0"])

// D5 / GS5: the screen reader is told what the eye is told, and hears it last.
checkCall("rowAccessibleName appends row N of M last, after the failure state", function () { return Model.rowAccessibleName({ name: "Comedy Central", favorite: true, playing: true, failedAt: "07:12", rowIndex: 1203, rowCount: 3335 }) },
  "Comedy Central, favorite, playing, failed, row 1,204 of 3,335")
checkCall("rowAccessibleName says nothing extra without a position", function () { return [
  Model.rowAccessibleName({ name: "Sky News" }),
  Model.rowAccessibleName({ name: "Sky News", rowCount: 0 }),
  Model.rowAccessibleName({ name: "Sky News", rowIndex: 9, rowCount: 9 })
] }, ["Sky News", "Sky News", "Sky News"])

// D6: the footer stops naming an axis that is not on screen. Same five
// characters, so the 684 px hint line does not move.
function hintLine(pairs) { return pairs.map(function (p) { return p[0] + " " + p[1] }).join(SEP) }
checkCall("footerHints: the h/l verb follows the axis, and the line is the same length", function () {
  const wide = Model.footerHints({ mode: "list", pipAvailable: false })
  const narrowed = Model.footerHints({ mode: "list", pipAvailable: false, groupsNarrow: false })
  const kept = Model.footerHints({ mode: "list", pipAvailable: false, groupsNarrow: true })
  return [wide[1].join(" "), narrowed[1].join(" "), kept[1].join(" "), hintLine(wide).length === hintLine(narrowed).length, narrowed.length === wide.length]
}, ["h/l group", "h/l scope", "h/l group", true, true])
checkCall("footerHints: the search-mode empty-query pair follows it too, and the narrow branch does not", function () {
  const empty = Model.footerHints({ mode: "search", query: "", groupsNarrow: false })
  const keptEmpty = Model.footerHints({ mode: "search", query: "" })
  const queried = Model.footerHints({ mode: "search", query: "sky", groupsNarrow: false })
  return [empty[2].join(" "), keptEmpty[2].join(" "), queried[2].join(" "), hintLine(empty).length === hintLine(keptEmpty).length]
}, ["Left/Right scope", "Left/Right group", "Left/Right narrow", true])

// D5: the ported fold affordance, as arithmetic. `peek` is the whole reach --
// the visible sliver plus the list's spacing, the way Menu.qml adds them.
function reveal(over) {
  const base = { itemY: 0, itemHeight: 38, contentY: 0, viewportHeight: 456, originY: 0, contentHeight: 3335 * 42, peek: 25, index: 5, count: 3335 }
  Object.keys(over).forEach(function (k) { base[k] = over[k] })
  return Model.revealOffset(base)
}
checkCall("revealOffset: a cursor parked flush at the bottom is pushed until the next row peeks", function () { return [reveal({ itemY: 456, contentY: 38 }), reveal({ itemY: 456, contentY: 63 })] }, [63, 63])
checkCall("revealOffset: a cursor parked flush at the top is pulled until the previous row peeks", function () { return [reveal({ itemY: 500, contentY: 500 }), reveal({ itemY: 500, contentY: 475 })] }, [475, 475])
checkCall("revealOffset: an already-revealed cursor does not move", function () { return reveal({ itemY: 200, contentY: 100 }) }, 100)
checkCall("revealOffset: the last row and the first row take no peek in the direction that has nothing", function () { return [reveal({ index: 3334, itemY: 456, contentY: 38 }), reveal({ index: 0, itemY: 0, contentY: 25 })] }, [38, 25])
checkCall("revealOffset: clamped to the flickable's own bounds, never past them", function () { return [
  // bottom: the peek would push past the last scrollable offset, so it stops there
  reveal({ count: 24, index: 22, itemY: 1400, contentY: 500, contentHeight: 1000, viewportHeight: 456 }),
  // top: the peek would pull above originY, so it stops there
  reveal({ count: 24, index: 1, itemY: 10, contentY: 5, originY: 0, contentHeight: 1000 }),
  // and originY is honoured when it is not zero
  reveal({ count: 24, index: 1, itemY: -90, contentY: -95, originY: -100, contentHeight: 1000 })
] }, [544, 0, -100])
checkCall("revealOffset: a viewport taller than its content never scrolls", function () { return [
  reveal({ count: 4, index: 1, itemY: 126, itemHeight: 38, contentY: 0, contentHeight: 164, viewportHeight: 456 }),
  reveal({ count: 4, index: 2, itemY: 84, contentY: 0, contentHeight: 164, viewportHeight: 456 })
] }, [0, 0])
checkCall("revealOffset: an empty or out-of-range call returns the offset it was given", function () { return [
  Model.revealOffset({ count: 0, contentY: 77 }), Model.revealOffset({ count: 5, index: 9, contentY: 77 }),
  Model.revealOffset({ count: 5, index: -1, contentY: 77 }), Model.revealOffset(null)
] }, [77, 77, 77, 0])

// ---- guide state machine ----
let g = Model.guideState("favorites")
check("guideState opens in search mode", [g.mode, g.query, g.scopeId, g.cursorIndex], ["search", "", "favorites", 0])
g = Model.withQuery(g, "s")
check("withQuery from Favorites jumps to All and remembers", [g.scopeId, g.restoreScopeId, g.cursorIndex], ["all", "favorites", 0])
g = Model.withQuery(Model.withCursor(g, 5), "sky")
check("withQuery keeps All while typing, cursor resets", [g.scopeId, g.restoreScopeId, g.cursorIndex], ["all", "favorites", 0])
g = Model.withQuery(g, "")
check("withQuery cleared restores Favorites", [g.scopeId, g.restoreScopeId], ["favorites", ""])
g = Model.withQuery(Model.withScope(Model.withQuery(Model.guideState("recent"), "a"), "g:UK"), "")
check("explicit column move survives clearing the query", g.scopeId, "g:UK")
check("withQuery from a group keeps the group", Model.withQuery(Model.guideState("g:UK"), "sky").scopeId, "g:UK")
check("withQuery whitespace-only does not move scope", Model.withQuery(Model.guideState("favorites"), " ").scopeId, "favorites")
check("withMode / toggleMode", [Model.withMode(g, "list").mode, Model.toggleMode(Model.withMode(g, "list")).mode, Model.toggleMode(g).mode], ["list", "search", "list"])
check("onEscape clears a query first", (() => { const r = Model.onEscape(Model.withQuery(Model.guideState("all"), "x")); return [r.close, r.state.query] })(), [false, ""])
check("onEscape in list mode with query stays in list mode", Model.onEscape(Model.withMode(Model.withQuery(Model.guideState("all"), "x"), "list")).state.mode, "list")
check("onEscape closes when empty", Model.onEscape(Model.guideState("all")).close, true)
check("onEscape null", Model.onEscape(null).close, true)
check("moveCursor wraps", [Model.moveCursor(0, -1, 5, true), Model.moveCursor(4, 1, 5, true), Model.moveCursor(2, 1, 5, true)], [4, 0, 3])
check("moveCursor page clamps", [Model.moveCursor(1, -10, 5, false), Model.moveCursor(1, 10, 5, false)], [0, 4])
check("moveCursor empty list", Model.moveCursor(3, 1, 0, true), 0)
check("copy is defensive on garbage state", Model.withMode({ mode: "weird", query: 5 }, "list"), { mode: "list", query: "5", scopeId: "all", restoreScopeId: "", cursorIndex: 0, returnMode: "", form: null, sourceCursor: 0 })

// ---- zap ring ----
check("launchScope from Favorites is Favorites", Model.launchScope("favorites", "", { group: "UK" }), "favorites")
check("launchScope from Favorites with a query is the result's group", Model.launchScope("favorites", "sky", { group: "UK | SPORTS" }), "g:UK | SPORTS")
check("launchScope from Recent uses the group", Model.launchScope("recent", "", { group: "UK" }), "g:UK")
check("launchScope from All uses the group", Model.launchScope("all", "", { group: "A;B" }), "g:A")
check("launchScope from a group", Model.launchScope("g:UK", "", { group: "UK" }), "g:UK")
check("zapRing favorites", Model.zapRing(channels, state, { id: "5", group: "UK", launchedFrom: "favorites" }).map(c => c.id), ["5", "1"])
check("zapRing group", Model.zapRing(channels, state, { id: "1", group: "UK", launchedFrom: "g:UK" }).map(c => c.id), ["1", "5", "6"])
check("zapRing recent falls back to the group", Model.zapRing(channels, state, { id: "4", group: "News", launchedFrom: "recent" }).map(c => c.id), ["4"])
check("zapRing nothing playing", Model.zapRing(channels, state, null), [])
check("nextInGroup wraps forward", Model.nextInGroup(channels, "7", 1).id, "1")
check("nextInGroup wraps backward", Model.nextInGroup(channels, "1", -1).id, "7")
check("nextInGroup unknown current", Model.nextInGroup(channels, "nope", 1).id, "1")
check("nextInGroup empty", Model.nextInGroup([], "1", 1), null)

// ---- state ----
check("toggleFavorite adds", Model.toggleFavorite(["a"], "b"), ["a", "b"])
check("toggleFavorite removes", Model.toggleFavorite(["a", "b"], "a"), ["b"])
check("toggleFavorite does not mutate", (() => { const f = ["a"]; Model.toggleFavorite(f, "b"); return f })(), ["a"])
check("toggleFavorite ignores empty id", Model.toggleFavorite(["a"], ""), ["a"])
check("pushRecent newest first, dedupe, cap",
  Model.pushRecent([{ id: "1", name: "A", at: 1 }, { id: "2", name: "B", at: 2 }, { id: "3", name: "C", at: 3 }], { id: "2", name: "B" }, 2, 99),
  [{ id: "2", name: "B", at: 99 }, { id: "1", name: "A", at: 1 }])
check("recordPlayed sets lastPlayed", Model.recordPlayed(Model.emptyState(), { id: "9", name: "Nine" }, 10, 5).lastPlayed, { id: "9", name: "Nine", at: 5 })
check("recordPlayed keeps favorites and does not mutate", (() => { const st = Model.withFavorites(Model.emptyState(), ["f"]); const next = Model.recordPlayed(st, { id: "9", name: "Nine" }, 10, 5); return [next.favorites, st.recents.length] })(), [["f"], 0])
check("removeRecent", Model.removeRecent({ version: 1, favorites: ["a"], recents: [{ id: "x", name: "X", at: 1 }, { id: "y", name: "Y", at: 2 }], lastPlayed: null }, "x").recents, [{ id: "y", name: "Y", at: 2 }])
check("removeRecent unknown id is a no-op copy", Model.removeRecent(state, "zz").recents.length, 2)
check("trimRecents", Model.trimRecents({ version: 1, favorites: [], recents: [{ id: "a" }, { id: "b" }, { id: "c" }], lastPlayed: null }, 2).recents.map(r => r.id), ["a", "b"])
check("trimRecents returns same object when within cap", (() => { const st = Model.emptyState(); return Model.trimRecents(st, 5) === st })(), true)
check("parseState tolerates garbage", Model.parseState("not json"), Model.emptyState())
check("parseState sanitizes", Model.parseState('{"favorites":["a","a",""],"recents":[{"id":"x","name":"X","at":"7"},{"bad":1}],"lastPlayed":{"id":"x"}}'),
  { version: 2, cacheLayout: 0, favorites: ["a"], recents: [{ id: "x", name: "X", at: 7 }], lastPlayed: { id: "x", name: "", at: 0 }, session: null, sources: [] })
check("parseState tolerates unknown keys", Model.parseState('{"version":9,"favorites":["a"],"future":true}').favorites, ["a"])
check("isFavorite", [Model.isFavorite(state, "5"), Model.isFavorite(state, "4"), Model.isFavorite(null, "5")], [true, false, false])
check("withFailed / withoutFailed are copies", (() => { const a = {}; const b = Model.withFailed(a, "x", "21:12"); const c = Model.withoutFailed(b, "x"); return [Object.keys(a).length, b.x, Object.keys(c).length] })(), [0, "21:12", 0])

// ---- caches ----
check("parseChannels ok", Model.parseChannels('{"version":1,"count":1,"channels":[{"id":"a"}]}'), { ok: true, channels: [{ id: "a" }], meta: { version: 1, count: 1 }, error: "" })
check("parseChannels empty", Model.parseChannels("").ok, false)
check("parseChannels no array", Model.parseChannels('{"channels":"x"}').ok, false)
check("parseEpgNow", Model.parseEpgNow('{"version":1,"generatedAt":5,"channels":{"a":{"now":{"title":"T"}}}}'), { ok: true, channels: { a: { now: { title: "T" } } }, meta: { version: 1, generatedAt: 5 } })
check("parseEpgNow garbage", Model.parseEpgNow("[]"), { ok: false, channels: {}, meta: {} })
check("parseHelperStatus string error upgraded", Model.parseHelperStatus('{"ok":false,"error":"boom"}', "playlist").error, { code: "error", message: "boom" })
check("parseHelperStatus no output", Model.parseHelperStatus("", "epg").error.code, "no_output")
check("parseHelperStatus coerces counters and keeps unknown keys", (() => {
  const s = Model.parseHelperStatus('{"ok":true,"kind":"epg","matched":"812","channelCount":"3","future":{"x":1},"stale":"no"}', "epg")
  return [s.matched, s.channelCount, s.future.x, s.stale, s.error]
})(), [812, 3, 1, false, null])
check("parseHelperStatus failure without error object", Model.parseHelperStatus('{"ok":false}', "play").error.code, "error")
check("parseHelperStatus fills kind", Model.parseHelperStatus('{"ok":true}', "status").kind, "status")
check("statusReason http codes", [Model.statusReason({ ok: false, error: { code: "http_403" } }), Model.statusReason({ ok: false, error: { code: "http_404" } }), Model.statusReason({ ok: false, error: { code: "http_503" } })], ["HTTP 403 Forbidden", "HTTP 404 Not Found", "HTTP 503"])
check("statusReason network flavours", [
  Model.statusReason({ ok: false, error: { code: "network", message: "could not reach h: timed out" } }),
  Model.statusReason({ ok: false, error: { code: "network", message: "could not reach h: [Errno -2] Name or service not known" } }),
  Model.statusReason({ ok: false, error: { code: "network", message: "could not reach h: Connection refused" } }),
  Model.statusReason({ ok: false, error: { code: "network", message: "weird" } })
], ["Timed out", "Could not resolve host", "Connection refused", "Network error"])
check("statusReason table", [Model.statusReason({ ok: false, error: { code: "not_found" } }), Model.statusReason({ ok: false, error: { code: "empty_playlist" } }), Model.statusReason({ ok: false, error: { code: "not_implemented" } })], ["File not found", "Playlist has no channels", "Helper command not implemented"])
// D-LIVE-03: the helper's HTML-body code maps to the terse reason, never its sentence (which names the host).
check("statusReason not_a_playlist is terse", Model.statusReason({ ok: false, error: { code: "not_a_playlist", message: "source from 127.0.0.1 is not an M3U playlist (no #EXTM3U or #EXTINF lines)" } }), "Not an M3U playlist")
// S-05: helper deadline and service watchdog codes never echo the message (which could carry a host).
check("statusReason timeout codes", [Model.statusReason({ ok: false, error: { code: "timeout", message: "playlist download from h.test exceeded 60 s" } }), Model.statusReason({ ok: false, error: { code: "helper_timeout", message: "helper timed out" } })], ["Timed out", "Helper timed out"])
check("statusReason unsafe redirect (S-06)", Model.statusReason({ ok: false, error: { code: "unsafe_redirect", message: "playlist from h.test redirected to an unsupported scheme 'ftp'" } }), "Unsafe redirect")
check("statusReason unknown code redacts URLs from the message", Model.statusReason({ ok: false, error: { code: "odd", message: "bad http://u:p@h.test/x?y" } }), "bad h.test")
check("statusReason ok", Model.statusReason({ ok: true }), "")
check("statusHost", [Model.statusHost({ sourceHost: "h.test" }), Model.statusHost(null)], ["h.test", ""])
check("statusHealthy", [Model.statusHealthy({ ok: true, running: true }), Model.statusHealthy({ ok: false, running: false }), Model.statusHealthy(null)], [true, false, false])

// ---- settings ----
const barConfig = { layout: { left: [{ id: "omarchy.menu" }], right: [{ id: "io.github.rmcdavid.iptv", playlistUrl: " http://x/y.m3u ", refreshMinutes: "15", barLabelMaxWidth: 9999, maxRecents: 0, showChannelName: "false" }] } }
check("findBarEntry finds own entry", Model.findBarEntry(barConfig, "io.github.rmcdavid.iptv").refreshMinutes, "15")
check("findBarEntry string entry", Model.findBarEntry({ layout: { center: ["io.github.rmcdavid.iptv"] } }, "io.github.rmcdavid.iptv"), { id: "io.github.rmcdavid.iptv" })
check("findBarEntry missing", Model.findBarEntry(barConfig, "nope"), {})
check("findBarEntry null config", Model.findBarEntry(null, "x"), {})
check("settingOf fallback", Model.settingOf({ a: null }, "a", 3), 3)
check("clampInt parses and clamps", [Model.clampInt("15", 60, 5, 1440), Model.clampInt("x", 60, 5, 1440), Model.clampInt(2, 60, 5, 1440)], [15, 60, 5])
// The whole settings object, pinned: a new key is only ever added here on
// purpose. M2-03 7.1 added three; M2-05 section 6 adds the last three.
check("settingsFrom applies R2 clamps and trims", Model.settingsFrom(Model.findBarEntry(barConfig, "io.github.rmcdavid.iptv")),
  { playlistUrl: "http://x/y.m3u", epgUrl: "", refreshMinutes: 15, mpvArgs: "", showChannelName: false, maxRecents: 1, barLabelMaxWidth: 600, channelOrder: "playlist", numberEntryMs: 2000, barShowChannelNumber: true, pipCorner: "top-right", pipSizePercent: 30, pipMargin: 16 })
check("settingsFrom defaults", Model.settingsFrom({}), { playlistUrl: "", epgUrl: "", refreshMinutes: 360, mpvArgs: "", showChannelName: true, maxRecents: 10, barLabelMaxWidth: 180, channelOrder: "playlist", numberEntryMs: 2000, barShowChannelNumber: true, pipCorner: "top-right", pipSizePercent: 30, pipMargin: 16 })
check("settingsFrom null", Model.settingsFrom(null).refreshMinutes, 360)
check("clampSetting refreshMinutes range", [Model.clampSetting("refreshMinutes", 5), Model.clampSetting("refreshMinutes", 99999), Model.clampSetting("refreshMinutes", "abc")], [15, 1440, 360])
check("clampSetting barLabelMaxWidth range", [Model.clampSetting("barLabelMaxWidth", 10), Model.clampSetting("barLabelMaxWidth", 601)], [60, 600])
check("clampSetting unknown key passthrough", Model.clampSetting("nope", "v"), "v")

// ---- mpv ----
check("splitMpvArgs accepts options", Model.splitMpvArgs(" --profile=low-latency --hwdec=auto-safe --no-osc "), { args: ["--profile=low-latency", "--hwdec=auto-safe", "--no-osc"], rejected: [], warnings: [] })
check("splitMpvArgs rejects reserved and junk", Model.splitMpvArgs("--input-ipc-server=/x --title=y ; rm -rf --no-idle --cache=yes"), { args: ["--cache=yes"], rejected: ["--input-ipc-server=/x", "--title=y", ";", "rm", "-rf", "--no-idle"], warnings: [] })
check("splitMpvArgs rejects --script and --config-dir", Model.splitMpvArgs("--script=/e.lua --config-dir=/x --scripts=/y --input-ipc-client=fd://3").args, [])
check("splitMpvArgs empty", Model.splitMpvArgs(null), { args: [], rejected: [], warnings: [] })
check("splitMpvArgs is case-sensitive (D-QA-11)", Model.splitMpvArgs("--Profile=fast --HWDEC=auto --profile=fast"), { args: ["--profile=fast"], rejected: ["--Profile=fast", "--HWDEC=auto"], warnings: [] })
check("splitMpvArgs rejects --no- forms of every reserved option", Model.splitMpvArgs("--no-input-ipc-server --no-wayland-app-id --no-title --no-force-media-title --no-idle --no-script --no-scripts --no-config-dir --no-input-ipc-client").args, [])
check("headerArgs maps UA/referer and appends others", Model.headerArgs({ "User-Agent": "VLC", Referer: "http://r", "X-Token": "a,b" }), ["--user-agent=VLC", "--referrer=http://r", "--http-header-fields-append=X-Token: a,b"])
check("headerArgs drops unsafe", Model.headerArgs({ "Bad Name": "x", Ok: "line\nbreak" }), [])
// ---- the detached launch argv (M2-02, ARCHITECTURE-PLAYER.md 6 / S-03) ----
// The channel no longer appears on any command line: no URL, no trailing
// "--", no header options, no per-channel title. Everything channel-specific
// travels over the 0600 socket instead. The vectors are shared with the
// Python mirror in tests/fixtures/player-argv.json.
const STATE_DIR = "/home/u/.local/state/omarchy-iptv"
const argv = Model.buildMpvArgv({ socketPath: "/run/user/1000/omarchy-iptv/mpv.sock", stateDir: STATE_DIR, extraArgs: ["--profile=low-latency"] })
check("buildMpvArgv starts with mpv and ipc socket", argv.slice(0, 2), ["mpv", "--input-ipc-server=/run/user/1000/omarchy-iptv/mpv.sock"])
check("buildMpvArgv fixed options in order", argv.slice(2, 10), ["--wayland-app-id=omarchy-iptv", "--force-window=immediate", "--idle=once", "--keep-open=no", "--title=$>IPTV", "--force-media-title=IPTV", "--msg-level=all=error", "--ytdl=no"])
check("buildMpvArgv idles at startup so the first channel arrives over IPC (PO-1)", [argv.indexOf("--idle=once") !== -1, argv.indexOf("--idle=no") !== -1, argv.indexOf("--idle=yes") !== -1], [true, false, false])
// S-03: no stream URL and no header value on any command line, on any
// channel including the first. These four are the structural replacement for
// the retired "buildMpvArgv url after --" invariant.
check("buildMpvArgv carries no URL, on any channel (S-03)", (() => {
  const a = Model.buildMpvArgv({ socketPath: "/s", name: "BBC One", url: "http://u:p@h.test/live/token/1.m3u8", headers: { "User-Agent": "VLC" }, extraArgs: [] })
  return [a.filter(t => /:\/\//.test(t)).length, a.indexOf("--") !== -1, a.join(" ").indexOf("u:p@") !== -1]
})(), [0, false, false])
check("buildMpvArgv sends no header options even for a channel with headers (S-03)", (() => {
  const a = Model.buildMpvArgv({ socketPath: "/s", headers: { "User-Agent": "VLC", Referer: "http://ref.test/", "X-Token": "secret" } })
  return a.filter(t => /^--(user-agent|referrer|http-header-fields)/.test(t))
})(), [])
check("buildMpvArgv carries no per-channel title, so a hostile name never reaches argv (S-01/S-03)", (() => {
  const a = Model.buildMpvArgv({ socketPath: "/s", name: "${path} ${options/input-ipc-server}", url: "http://u:p@h.test/x" })
  return [a.indexOf("--title=$>IPTV") !== -1, a.join(" ").indexOf("${path}") !== -1, a.filter(t => t.indexOf("--title=") === 0).length]
})(), [true, false, 1])
check("buildMpvArgv: every token after argv[0] is an option", argv.slice(1).every(t => t.indexOf("--") === 0), true)
// S-01 still holds on the IPC path: the raw marker is what the helper sends
// with `set_property title`, and it is still what the neutral launch title
// carries. force-media-title is not expanded by mpv, so it stays plain.
check("mpvWindowTitle prefixes the raw marker", [Model.MPV_RAW_PREFIX, Model.mpvWindowTitle("BBC One"), Model.mpvWindowTitle(null)], ["$>", "$>BBC One", "$>"])
check("buildMpvArgv neutral title keeps the raw marker and mpv's own default off screen", Model.buildMpvArgv({ socketPath: "/s" }).indexOf("--title=$>IPTV") !== -1, true)
check("buildMpvArgv user args can re-enable ytdl (last wins)", (() => { const a = Model.buildMpvArgv({ socketPath: "/s", extraArgs: ["--ytdl=yes"] }); return a.indexOf("--ytdl=no") < a.indexOf("--ytdl=yes") })(), true)
check("buildMpvArgv user args come last", argv[argv.length - 1], "--profile=low-latency")
check("buildMpvArgv null params", Model.buildMpvArgv(null), ["mpv", "--input-ipc-server=", "--wayland-app-id=omarchy-iptv", "--force-window=immediate", "--idle=once", "--keep-open=no", "--title=$>IPTV", "--force-media-title=IPTV", "--msg-level=all=error", "--ytdl=no", "--screenshot-dir=/screenshots", "--watch-later-dir=/watch-later", "--gpu-shader-cache-dir=/shader-cache", "--icc-cache-dir=/shader-cache"])

// ---- PO-11 / D-PLY-7: the player writes where it is told, not where it ----
// mpv's own keys are live on its window: `s` writes a screenshot and `Q` a
// resume record, and both used to land in whatever directory the shell was
// started from - $HOME - at mode 0644.
checkCall("the directory rule matches the shared fixture", () => playerFixture.playerDirs.cases.map(v => Model.playerDirs(v.socketPath, v.stateDir)),
  playerFixture.playerDirs.cases.map(v => v.dirs))
checkCall("the launch argv names both output directories", () => [argv.indexOf("--screenshot-dir=" + STATE_DIR + "/screenshots") !== -1, argv.indexOf("--watch-later-dir=/run/user/1000/omarchy-iptv/watch-later") !== -1], [true, true])
checkCall("a screenshot is durable, a resume record is not: one under state, one under the runtime dir", () => {
  const d = Model.playerDirs("/run/user/1000/omarchy-iptv/mpv.sock", STATE_DIR)
  return [d.screenshots.indexOf("/run/user/") === 0, d.watchLater.indexOf("/run/user/") === 0, d.cwd]
}, [false, true, "/run/user/1000/omarchy-iptv"])
checkCall("the working directory is never the home the shell runs in", () => {
  const d = Model.playerDirs("/run/user/1000/omarchy-iptv/mpv.sock", STATE_DIR)
  return [d.cwd === "/home/u", d.cwd === "", d.cwd === Model.dirnameOf("/run/user/1000/omarchy-iptv/mpv.sock")]
}, [false, false, true])
checkCall("dirnameOf behaves like os.path.dirname on the paths this plugin uses", () => [Model.dirnameOf("/a/b/c.sock"), Model.dirnameOf("/c.sock"), Model.dirnameOf("c.sock"), Model.dirnameOf("")], ["/a/b", "/", "", ""])
checkCall("--watch-later-dir stays reserved so a resume record cannot be aimed at $HOME", () => Model.splitMpvArgs("--watch-later-dir=/home/u --screenshot-dir=/home/u/Pictures"),
  { args: ["--screenshot-dir=/home/u/Pictures"], rejected: ["--watch-later-dir=/home/u"], warnings: [] })
checkCall("a user who wants their screenshots elsewhere still wins (last token wins)", () => {
  const a = Model.buildMpvArgv({ socketPath: "/run/user/1000/omarchy-iptv/mpv.sock", stateDir: STATE_DIR, extraArgs: ["--screenshot-dir=/home/u/Pictures"] })
  return a.indexOf("--screenshot-dir=" + STATE_DIR + "/screenshots") < a.lastIndexOf("--screenshot-dir=/home/u/Pictures")
}, true)
// ---- D-PIP-1: focus the player, and a check that can actually fail -------
//
// What was here was
//   check("focusPlayerArgv", Model.focusPlayerArgv(),
//         ["hyprctl", "dispatch", "focuswindow", "class:omarchy-iptv"])
// - the expectation transcribed from the constant the function returns. It
// passed for every one of the 1180 checks of v0.3.0 .. v0.4.0 while the
// command it describes did nothing at all: under a Lua config provider
// `hyprctl dispatch` wraps its argument as `return hl.dispatch(<arg>)`, so
// two bare tokens are a Lua SYNTAX error (rc 7, `')' expected near 'class'`)
// and focus never moved. Four call sites in Service.qml have been no-ops
// since v0.3.0, silently, because they go out through
// `Quickshell.execDetached`, which returns void.
//
// The shape of the old check is the point (CLAUDE.md 12). It did not merely
// miss the bug: it DEFENDED it. Fixing the code correctly turned the suite
// red, so a developer doing the right thing would have concluded they had
// broken something and reverted. Measured in this tree: shipped builder +
// old check = 1180 checks, 0 failures; fixed builder + old check = 1180
// checks, 1 failure, and the failing line was the fix.
//
// So the replacement does not describe the argv. It RUNS it, through a
// double of the one thing that decides whether the command works: hyprctl's
// Lua wrapping. Every branch below is a verdict the gate measured live on
// this machine (docs/QA-RESULTS.md, M2-05-00, G-1 and the D-PIP-1 A/B), and
// the double is held to those verdicts by its own check, because a double
// more forgiving than the real thing is the other half of this trap
// (CLAUDE.md 10).
const HYPR_DISPATCH_NAMESPACES = {
  // Proven present, live, against the player window: G-1 and the six-step
  // "enter" transcript. Independently confirmed by reading the installed
  // stubs: /usr/share/hypr/stubs/hl.meta.lua:908-931 declares
  // HL.DspWindowNamespace with exactly these six among its fields and NO
  // focus, while :870-889 declares HL.DspNamespace with `focus` at the top
  // level beside `window`. Two sources, one answer.
  "hl.dsp.window.float": true,
  "hl.dsp.window.pin": true,
  "hl.dsp.window.resize": true,
  "hl.dsp.window.move": true,
  "hl.dsp.window.alter_zorder": true,
  "hl.dsp.window.tag": true,
  // Focus sits one level UP. `hl.dsp.window.focus` is not a member:
  // `attempt to call a nil value (field 'focus')`.
  "hl.dsp.focus": true
}

// What this machine's hyprctl does with an argv vector. rc 7 is a Lua error
// (a bug in OUR string); rc 0 means the compositor accepted the call - which
// per PIP11 still says nothing about whether the window changed.
function hyprDispatch(argv, clients) {
  const parts = Array.isArray(argv) ? argv.map(String) : []
  if (parts[0] !== "hyprctl" || parts[1] !== "dispatch") return { rc: 2, error: "not a hyprctl dispatch" }
  // hyprctl joins everything after `dispatch` and evaluates
  // `return hl.dispatch(<joined>)`. The gate's own error text shows the
  // join: `[string "return hl.dispatch(tagwindow +iptv-probe2 add..."]`.
  const wrapped = parts.slice(2).join(" ")
  if (wrapped === "") return { rc: 7, error: "parse error: empty dispatch" }
  // A quoted string is syntactically fine and still refused at run time:
  // `hl.dispatch: expected a dispatcher (e.g. hl.dsp.window.close())`.
  if (/^"[^"]*"$/.test(wrapped)) return { rc: 7, error: "hl.dispatch: expected a dispatcher" }
  const call = /^([A-Za-z_][A-Za-z0-9_.]*)\(([\s\S]*)\)$/.exec(wrapped)
  // Anything that is not a call expression is a Lua parse error - which is
  // what EVERY legacy dispatcher spelling is here, space or comma.
  if (!call) return { rc: 7, error: "parse error near '" + wrapped.split(/[\s,]+/).slice(1).join(" ") + "'" }
  if (!Object.prototype.hasOwnProperty.call(HYPR_DISPATCH_NAMESPACES, call[1])) {
    return { rc: 7, error: "attempt to call a nil value (" + call[1] + ")" }
  }
  const table = /^\{ ([\s\S]*) \}$/.exec(call[2])
  if (!table) return { rc: 7, error: "parse error: expected a table" }
  const window = /window = "([^"]*)"/.exec(table[1])
  const selector = window ? window[1] : ""
  const hit = hyprResolve(selector, clients)
  return { rc: 0, ns: call[1], window: selector, matches: hit.matches, focused: hit.address }
}

// WHICH window a selector lands on, which is the half rc could never tell us
// and the half D-PIP-5 turns on. An `address:` names exactly one client. A
// `class:` names an APP ID, and the plugin does not get to choose among the
// windows carrying it: the live pass fired the class-only focus with a
// user's own `mpv --wayland-app-id=omarchy-iptv` open and watched it land on
// the stranger three times out of three. scripts/dev-harness/stub-hyprctl.py
// resolves a class the same way (`match_window`, first match wins), so the
// two doubles in this project answer this question identically.
//
// `matches` is the honest field: a selector that names more than one window
// is a command whose effect nobody can predict, which is the defect itself
// rather than a detail of how it came out on the day.
function hyprResolve(selector, clients) {
  const list = Array.isArray(clients) ? clients : []
  if (selector.indexOf("address:") === 0) {
    const hits = list.filter(function (c) { return String(c.address) === selector.substring(8) })
    return { matches: hits.length, address: hits.length === 1 ? String(hits[0].address) : "" }
  }
  if (selector.indexOf("class:") === 0) {
    const hits = list.filter(function (c) { return String(c["class"]) === selector.substring(6) })
    return { matches: hits.length, address: hits.length > 0 ? String(hits[0].address) : "" }
  }
  return { matches: 0, address: "" }
}

checkCall("D-PIP-1: the host double refuses exactly what the compositor refused in the gate, and accepts what it accepted", () => [
  // The command this plugin shipped from v0.3.0. rc 7, focus unchanged.
  hyprDispatch(["hyprctl", "dispatch", "focuswindow", "class:omarchy-iptv"]).rc,
  // The legacy comma spelling design 2.5 told lanes to copy. Also rc 7.
  hyprDispatch(["hyprctl", "dispatch", "tagwindow", "+iptv-probe3,address:0x559c6893d940"]).rc,
  // Quoting the legacy form does not rescue it.
  hyprDispatch(["hyprctl", "dispatch", "\"focuswindow class:zz-nonexistent-qa12\""]).rc,
  // The plausible wrong namespace - there is no hl.dsp.window.focus.
  hyprDispatch(["hyprctl", "dispatch", "hl.dsp.window.focus({ window = \"class:omarchy-iptv\" })"]).rc,
  // The spelling proven to move focus on this machine.
  hyprDispatch(["hyprctl", "dispatch", "hl.dsp.focus({ window = \"class:omarchy-iptv\" })"]).rc
], [7, 7, 7, 7, 0])

// ---- D-PIP-5: the second half of that defect, in the same function -----
//
// The D-PIP-1 repair fixed the SPELLING and kept the SELECTOR. `class:` names
// an app id, and PLY-RST-11 reproduced the case where two windows carry ours:
// a user's own `mpv --wayland-app-id=omarchy-iptv`. Design 4.2 had already
// ruled for every other verb that "narrowing by pid is not optional", because
// floating, shrinking and pinning a stranger's window is damage - and focus
// was simply the verb nobody applied it to. The live pass then measured it:
// focus landed on the stranger 3 times out of 3.
//
// So the evidence below is not the argv. It is WHICH WINDOW the command
// reaches, with the stranger present and listed first, exactly as the live
// pass met it.
const focusClients = [pipFixture.CLIENTS.foreign, pipFixture.CLIENTS.tiled]
checkCall("D-PIP-5: the class-only command the wave shipped cannot say which window it means, and reaches the stranger", () => {
  const out = hyprDispatch(["hyprctl", "dispatch", "hl.dsp.focus({ window = \"class:omarchy-iptv\" })"], focusClients)
  // rc 0: the compositor accepted it. PIP11 again - acceptance says nothing.
  return [out.rc, out.matches, out.focused === pipFixture.PLAYER_ADDRESS, out.focused]
}, [0, 2, false, "0x559c687e09a0"])

checkCall("D-PIP-5: the shipped command names the window the pid resolved, and lands on OURS", () => {
  const live = Model.pipFindWindow(focusClients, pipFixture.PLAYER_PID)
  const out = hyprDispatch(Model.focusPlayerArgv(live.address), focusClients)
  return [out.rc, out.ns, out.window, out.matches, out.focused]
}, [0, "hl.dsp.focus", "address:" + pipFixture.PLAYER_ADDRESS, 1, pipFixture.PLAYER_ADDRESS])

checkCall("D-PIP-5: 4.2's refusals reach focus too - no window, or two, means no command at all", () => {
  const clients = function (list) { return JSON.stringify(list) }
  return [
    // Only the stranger is up: our window has not mapped yet.
    Model.focusPlayerArgv(Model.pipFindWindow(clients([pipFixture.CLIENTS.foreign]), pipFixture.PLAYER_PID).address).length,
    // Two windows at our own pid: the lookup refuses, so focus does too.
    Model.focusPlayerArgv(Model.pipFindWindow(clients([pipFixture.CLIENTS.tiled, pipFixture.CLIENTS.twin]), pipFixture.PLAYER_PID).address).length,
    Model.focusPlayerArgv("").length,
    Model.focusPlayerArgv().length,
    Model.focusPlayerArgv(null).length,
    // And PIP7's boundary is the same one: a hostile address is refused, not
    // escaped, on this path as on every other.
    Model.focusPlayerArgv("0xdead\"); os.execute(\"touch /tmp/PWNED\"); --").length,
    Model.focusPlayerArgv("class:omarchy-iptv").length
  ]
}, [0, 0, 0, 0, 0, 0, 0])

checkCall("D-PIP-5: a class selector cannot be built at all any more, by focus or by anything else", () => [
  // Not merely unused: removed, so a future caller cannot route back to it.
  Model.pipExpression("focus", { window: "class:omarchy-iptv" }),
  Model.pipExpression("focus", { window: "class:not-ours" }),
  Model.pipExpression("float", { window: "class:omarchy-iptv" }),
  Model.pipDispatchArgv("focus", { window: "class:omarchy-iptv" }).length,
  typeof Model.PIP_CLASS_SELECTOR
], ["", "", "", 0, "undefined"])

checkCall("D-PIP-1: focus goes through the same validated builder every PiP step uses, so a hand-rolled string cannot come back", () => {
  const argv = Model.focusPlayerArgv(pipFixture.PLAYER_ADDRESS)
  return [
    // One argv item after `dispatch` - more than one is what broke it.
    argv.length,
    argv[0] + " " + argv[1],
    argv[2] === Model.pipExpression("focus", { window: "address:" + pipFixture.PLAYER_ADDRESS })
  ]
}, [3, "hyprctl dispatch", true])

// ---- D-PLY-11: the play fork, and the repair the evidence asked for ----
// The fork rows record the decision Service.qml.play() makes. The third row
// is the one D-PLY-11 turns on: with a start in flight and no socket bound
// yet, the fork answers "zap" - a channel change aimed at a socket nothing is
// listening on. Wave two measured what happens next (ruling CL9): ten
// user-visible divergences in twenty cold concurrent bursts. The fork itself
// is unchanged and stays that way; what changed is the far end.
checkCall("play fork: nothing running is a start", () => Model.playFork({ playerPending: false, socketAttached: false, stopping: false, controlBusy: false }), "start")
checkCall("play fork: an attached player is a zap", () => Model.playFork({ playerPending: false, socketAttached: true, stopping: false, controlBusy: false }), "zap")
checkCall("play fork: a start in flight with no socket yet is STILL a zap today, and that is the hazard", () => [Model.playFork({ playerPending: true, socketAttached: false, stopping: false, controlBusy: false }), Model.playForkBlind({ playerPending: true, socketAttached: false })], ["zap", true])
checkCall("play fork: a zap at an attached player is not blind", () => Model.playForkBlind({ playerPending: true, socketAttached: true }), false)
checkCall("play fork: stopping always goes back through a start", () => [Model.playFork({ playerPending: true, socketAttached: true, stopping: true }), Model.playFork({ playerPending: false, socketAttached: true, stopping: true })], ["start", "start"])
checkCall("play fork: one control helper at a time, so a second intent queues", () => [Model.playFork({ socketAttached: true, controlBusy: true }), Model.playForkBlind({ playerPending: true, controlBusy: true })], ["queue", false])
checkCall("play fork: no state at all is a start, never a zap into nothing", () => [Model.playFork(null), Model.playFork({}), Model.playForkBlind(null)], ["start", "start", false])

// zapArgs: Service.qml.playArgs, lifted. The additive flags decide whether
// the far end refreshes the player's own now-playing record at all
// (`cmd_play` computes `session = bool(scope or since)`), and this was the
// one argv builder in the file with no vectors anywhere (CLAUDE.md 12).
const np11 = { id: "t:bbc1.uk", name: "BBC One HD", group: "UK", launchedFrom: "g:uk", since: 1758000123 }
checkCall("zapArgs: the intent being zapped carries its scope and start time",
  () => Model.zapArgs("/run/x/mpv.sock", "/cache/s/a1b2c3d4", "t:bbc1.uk", np11),
  ["play", "--id", "t:bbc1.uk", "--socket", "/run/x/mpv.sock", "--cache-dir", "/cache/s/a1b2c3d4", "--scope", "g:uk", "--since", "1758000123"])
checkCall("zapArgs: a drained burst issuing an id that is no longer nowPlaying writes no stash",
  () => Model.zapArgs("/run/x/mpv.sock", "/cache/s/a1b2c3d4", "t:espn.us", np11),
  ["play", "--id", "t:espn.us", "--socket", "/run/x/mpv.sock", "--cache-dir", "/cache/s/a1b2c3d4"])
checkCall("zapArgs: no record, no scope and no since - and never the word undefined in an argv",
  () => [Model.zapArgs("/s", "/c", "t:x", null), Model.zapArgs("/s", "/c", "t:x", { id: "t:x" }), Model.zapArgs("/s", "/c", "t:x", { id: "t:x", launchedFrom: "g:uk", since: 0 })],
  [["play", "--id", "t:x", "--socket", "/s", "--cache-dir", "/c"],
   ["play", "--id", "t:x", "--socket", "/s", "--cache-dir", "/c"],
   ["play", "--id", "t:x", "--socket", "/s", "--cache-dir", "/c", "--scope", "g:uk"]])

// playFailureVerdict: the four answers a failed `play` reply can have. The
// rollback at the end of that branch WRITES nowPlaying with no load to match
// it, so every code that reaches it and should not is a mislabel.
const failed = (code, over) => Model.playFailureVerdict(code, Object.assign({ playerUp: true, nowPlaying: true, userStopped: false, retriesLeft: true }, over))
checkCall("play failure: the player is gone - one `player start` is right whether it is there or not", () => failed("not_running"), "start")
checkCall("play failure: `not_running` with nothing playing has no channel to start", () => failed("not_running", { nowPlaying: false }), "failed")
checkCall("play failure: mpv did not answer in time - back off, do not lose the zap", () => failed("ipc_error"), "retry")
checkCall("play failure: out of retries, a timeout really is a failed switch", () => failed("ipc_error", { retriesLeft: false }), "failed")
checkCall("play failure: a reply we could not READ is not evidence the switch failed", () => [failed("no_output"), failed("not_implemented")], ["unknown", "unknown"])
checkCall("play failure: a lookup that never reached the player is not a failed switch either", () => [failed("unknown_channel"), failed("no_cache")], ["unknown", "unknown"])
checkCall("play failure: `busy` routes to the backoff, which is CL4's precondition for ever giving `play` the lock", () => failed("busy"), "retry")
checkCall("play failure: a refusal out of retries is still a refusal, never a failed switch", () => failed("busy", { retriesLeft: false }), "unknown")
checkCall("play failure: a user stop stops the retrying", () => failed("ipc_error", { userStopped: true }), "failed")
checkCall("play failure: anything the table does not name is a failed switch, and the label goes back", () => [failed("unsupported_scheme"), failed(""), failed(null)], ["failed", "failed", "failed"])

// replyTarget: who the reply is ABOUT. Both rememberEntry call sites passed
// the shell's nowPlaying, which in a burst is the intent current when the
// REPLY landed - the exact case the entry ring exists for.
checkCall("replyTarget: a play reply names its own channel, not whatever is current now",
  () => Model.replyTarget({ ok: true, kind: "play", id: "t:qa.live", name: "QA Live Stream", entryId: 2 }, { id: "t:qa.plain", name: "QA Plain" }),
  { id: "t:qa.live", name: "QA Live Stream" })
checkCall("replyTarget: a start that STOOD DOWN names the channel it left playing, not the one it was asked for",
  () => Model.replyTarget({ ok: true, kind: "player.start", id: "t:bbc1.uk", name: "BBC One HD", applied: false, playing: { id: "t:espn.us", name: "ESPN" } }, { id: "t:espn.us", name: "ESPN" }),
  { id: "t:espn.us", name: "ESPN" })
checkCall("replyTarget: a reply with no channel of its own falls back to the shell's, never to nothing",
  () => [Model.replyTarget({ ok: true, kind: "play" }, { id: "t:x", name: "X" }), Model.replyTarget(null, { id: "t:x", name: "X" }), Model.replyTarget({ ok: true }, null)],
  [{ id: "t:x", name: "X" }, { id: "t:x", name: "X" }, null])

// reconcileVerdict: the health tick's new question, and ruling CL5's answer.
const stash11 = { schema: 1, playing: true, id: "t:espn.us", name: "ESPN", group: "Sport", launchedFrom: "g:QA", sourceKey: "a1b2c3d4", since: 3000, entryId: 2, seq: 7, verb: "play" }
checkCall("reconcile: the player is on the channel the guide names", () => Model.reconcileVerdict(stash11, { id: "t:espn.us" }, "a1b2c3d4").state, "agree")
checkCall("reconcile: they disagree, and the repair is the SHELL's id - never the player's (CL5)",
  () => Model.reconcileVerdict(stash11, { id: "t:bbc1.uk" }, "a1b2c3d4"),
  { state: "diverged", repair: "t:bbc1.uk", wanted: "t:bbc1.uk", playing: "t:espn.us" })
checkCall("reconcile: no record to compare is never a verdict - an old helper raises nothing",
  () => [Model.reconcileVerdict(null, { id: "t:bbc1.uk" }, "a1b2c3d4").state, Model.reconcileVerdict(undefined, { id: "t:bbc1.uk" }, "a1b2c3d4").state, Model.reconcileVerdict({}, { id: "t:bbc1.uk" }, "a1b2c3d4").state],
  ["unknown", "unknown", "unknown"])
checkCall("reconcile: nothing playing has no intent to compare against", () => Model.reconcileVerdict(stash11, null, "a1b2c3d4").state, "unknown")
checkCall("reconcile: a record from another playlist means something else by the same id",
  () => [Model.reconcileVerdict(stash11, { id: "t:bbc1.uk" }, "99999999").state, Model.reconcileVerdict(Object.assign({}, stash11, { sourceKey: "" }), { id: "t:bbc1.uk" }, "99999999").state],
  ["unknown", "diverged"])
checkCall("reconcile: a record the helper marked not playing is not a channel claim", () => Model.reconcileVerdict(Object.assign({}, stash11, { playing: false }), { id: "t:bbc1.uk" }, "a1b2c3d4").state, "unknown")

// sessionIntentRepair: the same question asked of a start/restart reply,
// which is where the measured divergence actually arrives.
checkCall("session repair: the cold burst - the start applied intent one, the shell holds intent eight",
  () => Model.sessionIntentRepair({ ok: true, kind: "player.start", id: "t:bbc1.uk", name: "BBC One HD", applied: true }, { id: "t:qa.eight" }),
  "t:qa.eight")
checkCall("session repair: the start stood down and left the shell's own intent playing - nothing to do",
  () => Model.sessionIntentRepair({ ok: true, kind: "player.start", id: "t:bbc1.uk", applied: false, playing: { id: "t:espn.us", name: "ESPN" } }, { id: "t:espn.us" }),
  "")
checkCall("session repair: the ordinary start, which is every start that is not in a burst",
  () => Model.sessionIntentRepair({ ok: true, kind: "player.start", id: "t:bbc1.uk", applied: true }, { id: "t:bbc1.uk" }),
  "")
checkCall("session repair: a stand-down for a channel the shell no longer wants is still repaired",
  () => Model.sessionIntentRepair({ ok: true, kind: "player.start", id: "t:bbc1.uk", applied: false, playing: { id: "t:espn.us", name: "ESPN" } }, { id: "t:qa.eight" }),
  "t:qa.eight")
checkCall("session repair: nothing playing, or a reply naming nothing, repairs nothing",
  () => [Model.sessionIntentRepair({ ok: true, id: "t:bbc1.uk" }, null), Model.sessionIntentRepair({ ok: true }, { id: "t:x" }), Model.sessionIntentRepair(null, { id: "t:x" })],
  ["", "", ""])


// ---- D-PLY-10 / CL2: mpv's own caches contained, ephemeral, unreserved ----
// Without these mpv compiles its shaders into $XDG_CACHE_HOME/mpv/, two
// files at 0600 per containment cycle, outside every list of files this
// plugin says it writes. The cache is content-free and regenerable, so it
// goes in the runtime directory and dies at logout: no durable path, nothing
// to clean up at uninstall.
checkCall("the shader cache is inside the runtime directory, never the user's cache", () => {
  const d = Model.playerDirs("/run/user/1000/omarchy-iptv/mpv.sock", STATE_DIR)
  return [d.shaderCache, d.shaderCache.indexOf("/run/user/1000/omarchy-iptv/") === 0, d.shaderCache.indexOf(STATE_DIR) === 0]
}, ["/run/user/1000/omarchy-iptv/shader-cache", true, false])
checkCall("the launch argv aims both of mpv's caches at it", () => {
  const a = Model.buildMpvArgv({ socketPath: "/run/user/1000/omarchy-iptv/mpv.sock", stateDir: STATE_DIR })
  return [a.indexOf("--gpu-shader-cache-dir=/run/user/1000/omarchy-iptv/shader-cache") !== -1, a.indexOf("--icc-cache-dir=/run/user/1000/omarchy-iptv/shader-cache") !== -1]
}, [true, true])
checkCall("neither cache option is reserved (CL2: the list is a privacy instrument) and a user token still wins", () => {
  const r = Model.splitMpvArgs("--gpu-shader-cache-dir=/home/u/.cache/shaders --icc-cache-dir=/home/u/.cache/icc")
  const a = Model.buildMpvArgv({ socketPath: "/s", extraArgs: r.args })
  return [r.rejected, a.indexOf("--gpu-shader-cache-dir=/shader-cache") < a.lastIndexOf("--gpu-shader-cache-dir=/home/u/.cache/shaders")]
}, [[], true])


// ---- MPV_RESERVED, ten additions (ARCHITECTURE-PLAYER.md 4.12) ----
const RESERVED_ADDED = ["--log-file", "--dump-stats", "--stream-record", "--save-position-on-quit", "--watch-later-dir", "--osd-msg1", "--osd-msg2", "--osd-msg3", "--term-status-msg", "--screenshot-template"]
check("MPV_RESERVED gained exactly ten entries", Object.keys(Model.MPV_RESERVED).length, 19)
check("splitMpvArgs rejects every addition and its --no- form", (() => {
  const tokens = RESERVED_ADDED.map(n => n + "=/tmp/x").concat(RESERVED_ADDED.map(n => "--no-" + n.slice(2)))
  const r = Model.splitMpvArgs(tokens.join(" "))
  return [r.args, r.rejected.length]
})(), [[], 20])
check("--ytdl stays unreserved (PO-5) and still sorts after the built-in --ytdl=no", (() => {
  const r = Model.splitMpvArgs("--ytdl=yes")
  const a = Model.buildMpvArgv({ socketPath: "/s", extraArgs: r.args })
  return [r.args, a.indexOf("--ytdl=no") < a.indexOf("--ytdl=yes")]
})(), [["--ytdl=yes"], true])

// ---- PO-10 / D-PLY-5: the options that hand the URL to another program ----
// Not refused (PO-5 keeps the escape hatch), but never silent. The vectors
// are the ones tests/test_player.py runs against the python mirror.
const HANDOFF = playerFixture.mpvHandoff
const HANDOFF_TEXT = HANDOFF.text
checkCall("the handoff wording is the one in the shared fixture", () => Model.MPV_HANDOFF_TEXT, HANDOFF_TEXT)
HANDOFF.cases.forEach(vector => {
  checkCall("mpvArgWarnings: " + vector.name, () => Model.mpvArgWarnings(vector.tokens), vector.warnings)
})
checkCall("splitMpvArgs carries the warning for the tokens it KEEPS", () => Model.splitMpvArgs("--ytdl=yes --hwdec=auto"),
  { args: ["--ytdl=yes", "--hwdec=auto"], rejected: [], warnings: ["mpvArg --ytdl" + HANDOFF_TEXT] })
checkCall("a REJECTED token never warns: it never reaches mpv (--script is reserved)",
  () => Model.splitMpvArgs("--script=/tmp/ytdl_hook.lua --script-opts=ytdl_hook-ytdl_path=/tmp/x").warnings,
  ["mpvArg --script-opts" + HANDOFF_TEXT])
checkCall("the warning names the option and never its value (a proxy URL stays out of the sink)", () => {
  const w = Model.splitMpvArgs("--ytdl-raw-options=proxy=http://u:pw@prox.test:8080").warnings
  return [w.length, w[0].indexOf("prox.test") !== -1, w[0].indexOf("pw") !== -1, w[0]]
}, [1, false, false, "mpvArg --ytdl-raw-options" + HANDOFF_TEXT])
checkCall("mpvOptionBase collapses mpv's list-option spellings onto one option", () => [Model.mpvOptionBase("--ytdl-raw-options-append"), Model.mpvOptionBase("--script-opts-set"), Model.mpvOptionBase("--ytdl"), Model.mpvOptionBase("--script-opt")], ["--ytdl-raw-options", "--script-opts", "--ytdl", "--script-opt"])

// The warning reaches the user through the ONE line the guide already shows
// (Guide.qml warningText -> Model.footerWarning), by naming its own kind.
checkCall("a labelled warning keeps its own wording inside the playlist list", () => Model.footerWarning(Model.labelWarnings(["mpvArg --ytdl" + HANDOFF_TEXT], "player"), []),
  "Player warning: mpvArg --ytdl hands the stream address to another program")
checkCall("an unlabelled playlist warning is unchanged (D-LIVE-18 wording holds)", () => [Model.footerWarning(["truncated to 50,000 channels"], []), Model.footerWarning([], ["1 programme dropped"])],
  ["Playlist warning: truncated to 50,000 channels", "Guide data warning: 1 programme dropped"])
checkCall("the player's line comes first and counts the playlist's as +1 more", () => Model.footerWarning(Model.labelWarnings(["mpvArg --ytdl" + HANDOFF_TEXT], "player").concat(["truncated to 50,000 channels"]), []),
  "Player warning: mpvArg --ytdl hands the stream address to another program (+1 more)")
checkCall("labelWarnings is idempotent and drops nothing", () => Model.labelWarnings(Model.labelWarnings(["a"], "player"), "player"), ["Player warning: a"])
checkCall("warningLabel names the kind an entry already declares", () => [Model.warningLabel("Player warning: x"), Model.warningLabel("Guide data warning: x"), Model.warningLabel("Playlist warning: x"), Model.warningLabel("plain")], ["player", "epg", "playlist", ""])

// ---- helper `player` verb argv (ARCHITECTURE-PLAYER.md 4.3) ----
check("playerStartArgv: every value its own argv member, user tokens repeated",
  Model.playerStartArgv("/run/user/1000/omarchy-iptv/mpv.sock", "/c/sources/a1b2c3d4", "t:bbc1.uk", 41, "g:uk", 1758000123, ["--profile=low-latency", "--cache=yes"]),
  ["player", "start", "--socket", "/run/user/1000/omarchy-iptv/mpv.sock", "--cache-dir", "/c/sources/a1b2c3d4", "--id", "t:bbc1.uk", "--seq", "41", "--scope", "g:uk", "--since", "1758000123", "--mpv-arg=--profile=low-latency", "--mpv-arg=--cache=yes"])
check("playerStartArgv: optional scope and since are omitted, --seq is always present",
  Model.playerStartArgv("/s", "/c", "t:x", 0, "", 0, null),
  ["player", "start", "--socket", "/s", "--cache-dir", "/c", "--id", "t:x", "--seq", "0"])
check("playerStartArgv: an option-looking user token stays one member and is attached, not separated", (() => {
  const a = Model.playerStartArgv("/s", "/c", "t:x", 1, "", 0, ["--vf=lavfi=[scale=2]", "--cache=yes", "--log-file=/tmp/x"])
  return [a.filter(t => t.indexOf("--mpv-arg=") === 0).length, a.indexOf("--mpv-arg") !== -1, a.slice(-3)]
})(), [3, false, ["--mpv-arg=--vf=lavfi=[scale=2]", "--mpv-arg=--cache=yes", "--mpv-arg=--log-file=/tmp/x"]])
check("playerStartArgv: the optional owner claim rides the same call", Model.playerStartArgv("/s", "/c", "t:x", 5, "", 0, [], 301706),
  ["player", "start", "--socket", "/s", "--cache-dir", "/c", "--id", "t:x", "--seq", "5", "--owner-pid", "301706"])
check("playerStopArgv", Model.playerStopArgv("/s", 42), ["player", "stop", "--socket", "/s", "--seq", "42"])
check("playerStopArgv --from picks the first rung", [Model.playerStopArgv("/s", 42, "term"), Model.playerStopArgv("/s", 42, "bogus")], [["player", "stop", "--socket", "/s", "--seq", "42", "--from", "term"], ["player", "stop", "--socket", "/s", "--seq", "42"]])
check("playerRestartArgv is start plus the rung, under one lock", Model.playerRestartArgv("/s", "/c", "t:x", 7, "g:uk", 0, ["--cache=yes"], "term"),
  ["player", "restart", "--socket", "/s", "--cache-dir", "/c", "--id", "t:x", "--seq", "7", "--scope", "g:uk", "--mpv-arg=--cache=yes", "--from", "term"])
check("playerProbeArgv with and without an owner claim", [Model.playerProbeArgv("/s", 301706), Model.playerProbeArgv("/s", 0)], [["player", "probe", "--socket", "/s", "--owner-pid", "301706"], ["player", "probe", "--socket", "/s"]])
check("playerOrphanCheckArgv", [Model.playerOrphanCheckArgv("/s", 301706, 6), Model.playerOrphanCheckArgv("/s", 301706, null)], [["player", "orphan-check", "--socket", "/s", "--owner-pid", "301706", "--grace", "6"], ["player", "orphan-check", "--socket", "/s", "--owner-pid", "301706", "--grace", "6"]])
check("helperArgv prefixes the interpreter and the helper path", Model.helperArgv("/p/bin/omarchy-iptv", Model.playerStopArgv("/s", 3)), ["python3", "/p/bin/omarchy-iptv", "player", "stop", "--socket", "/s", "--seq", "3"])
check("no player argv ever carries a URL or a header value", (() => {
  const all = [].concat(
    Model.playerStartArgv("/s", "/c", "t:x", 1, "g:uk", 12, ["--cache=yes"]),
    Model.playerStopArgv("/s", 2), Model.playerRestartArgv("/s", "/c", "t:x", 3, "", 0, [], "term"),
    Model.playerProbeArgv("/s", 9), Model.playerOrphanCheckArgv("/s", 9, 6))
  return all.filter(t => /:\/\//.test(t))
})(), [])

// ---- the now-playing stash and the probe reply (4.5, 4.6) ----
check("playerStash normalizes the record mpv carries for us", Model.playerStash({ id: "t:bbc1.uk", name: "BBC One HD", group: "UK", launchedFrom: "g:uk", sourceKey: "a1b2c3d4", since: 1758000123, entryId: 2, seq: 41, verb: "start" }),
  { schema: 1, playing: true, id: "t:bbc1.uk", name: "BBC One HD", group: "UK", launchedFrom: "g:uk", sourceKey: "a1b2c3d4", since: 1758000123, entryId: 2, seq: 41, verb: "start" })
check("playerStash without an id is not a record", [Model.playerStash(null), Model.playerStash({ name: "x" })], [null, null])
check("playerStash defaults are empty, never undefined", Model.playerStash({ id: "t:x" }), { schema: 1, playing: true, id: "t:x", name: "", group: "", launchedFrom: "", sourceKey: "", since: 0, entryId: null, seq: 0, verb: "" })
// A v0.3.0 player is still out there with a stash that predates the field.
check("playerStash reads a record written before the writer was named", Model.playerStash({ id: "t:x", seq: 3 }).verb, "")
// The probe reply is the SHARED vector now (fixtures/player-argv.json), not a
// copy written here: tests/test_player.py asserts a real `player probe` emits
// exactly these keys, so a helper that renamed `pid` turns both suites red.
// It matters beyond tidiness since M2-05 - the service takes the window-owning
// pid from here and reads it defensively, so a missing key would not throw,
// it would silently answer "Nothing playing" to the `p` of a playing channel.
const probeFixture = playerFixture.playerProbe
const probeBody = JSON.stringify(probeFixture.reply)
check("parsePlayerProbe: a live player, from the shared vector",
  (() => { const p = Model.parsePlayerProbe(probeBody); return { valid: p.valid, running: p.running, responsive: p.responsive, pid: p.pid, idle: p.idle, seq: p.seq, stashId: p.stash.id, ownerPid: p.owner.pid } })(),
  probeFixture.parsed)
check("parsePlayerProbe: the pid M2-05 addresses the window by survives every shape the helper can send it in", [
  Model.parsePlayerProbe(probeBody).pid,
  Model.parsePlayerProbe(JSON.stringify(Object.assign({}, probeFixture.reply, { pid: 0 }))).pid,
  Model.parsePlayerProbe(JSON.stringify(Object.assign({}, probeFixture.reply, { pid: null }))).pid,
  Model.parsePlayerProbe(JSON.stringify(Object.assign({}, probeFixture.reply, { pid: "301706" }))).pid,
  (() => { const bare = Object.assign({}, probeFixture.reply); delete bare.pid; return Model.parsePlayerProbe(JSON.stringify(bare)).pid })(),
  probeFixture.keys.indexOf("pid") >= 0
], [301706, null, null, 301706, null, true])
check("parsePlayerProbe: the fixture's own reply declares every key the helper emits",
  Object.keys(probeFixture.reply).slice().sort(), probeFixture.keys.slice().sort())
check("parsePlayerProbe: a live player", (() => { const p = Model.parsePlayerProbe(probeBody); return [p.valid, p.running, p.responsive, p.pid, p.idle, p.seq, p.stash.launchedFrom, p.stash.entryId, p.owner.pid] })(), [true, true, true, 301706, false, 41, "g:uk", 2, 301706])
check("parsePlayerProbe: nothing running", (() => { const p = Model.parsePlayerProbe(JSON.stringify({ ok: true, kind: "player.probe", running: false, responsive: false, pid: null, idle: null, stash: null, owner: null, seq: 3 })); return [p.valid, p.running, p.pid, p.idle, p.stash, p.seq] })(), [true, false, null, null, null, 3])
check("parsePlayerProbe never throws: garbage, truncated, wrong kind, error reply, empty", [
  Model.parsePlayerProbe("not json at all").valid,
  Model.parsePlayerProbe('{"ok":true,"kind":"player.probe","pid":').valid,
  Model.parsePlayerProbe('{"ok":true,"kind":"status","running":true}').valid,
  Model.parsePlayerProbe('{"ok":false,"kind":"player.probe","error":{"code":"ipc_error","message":"x"}}').valid,
  Model.parsePlayerProbe("").valid, Model.parsePlayerProbe(null).valid
], [false, false, false, false, false, false])
check("parsePlayerProbe: a foreign or pre-M2-02 player has no stash", (() => { const p = Model.parsePlayerProbe(JSON.stringify({ ok: true, kind: "player.probe", running: true, responsive: true, pid: 7, idle: true, stash: { schema: 1 }, owner: null, seq: 0 })); return [p.valid, p.running, p.idle, p.stash, p.owner] })(), [true, true, true, null, null])

// ---- the event router (4.8) ----
check("parsePlayerEvent: start-file", Model.parsePlayerEvent('{"event":"start-file","playlist_entry_id":2}'), { kind: "start-file", entryId: 2 })
check("parsePlayerEvent: end-file carries the reason and the file error", Model.parsePlayerEvent('{"event":"end-file","reason":"error","playlist_entry_id":2,"file_error":"loading failed"}'), { kind: "end-file", entryId: 2, reason: "error", fileError: "loading failed" })
check("parsePlayerEvent: log-message text is redacted to its host (S-01/D-QA-01)", Model.parsePlayerEvent('{"event":"log-message","prefix":"stream","level":"error","text":"Failed to open http://u:p@provider.test/live/tok/1.m3u8.\\n"}'), { kind: "log-message", level: "error", prefix: "stream", text: "Failed to open provider.test" })
check("parsePlayerEvent: idle-active property change", Model.parsePlayerEvent('{"event":"property-change","id":1,"name":"idle-active","data":true}'), { kind: "property-change", name: "idle-active", value: true })
check("parsePlayerEvent ignores replies, other events, other properties, junk and null", [
  Model.parsePlayerEvent('{"error":"success","data":{"playlist_entry_id":2},"request_id":3}').kind,
  Model.parsePlayerEvent('{"event":"audio-reconfig"}').kind,
  Model.parsePlayerEvent('{"event":"property-change","name":"pause","data":true}').kind,
  Model.parsePlayerEvent("not json").kind, Model.parsePlayerEvent("").kind, Model.parsePlayerEvent(null).kind
], ["ignored", "ignored", "ignored", "ignored", "ignored", "ignored"])
check("parsePlayerEvent: a missing entry id is null, never 0 (the gate fails open on it)", [Model.parsePlayerEvent('{"event":"start-file"}').entryId, Model.parsePlayerEvent('{"event":"end-file","reason":"eof","playlist_entry_id":0}').entryId], [null, null])

// The router state machine itself, lifted out of Service.qml so the spec can
// call the shipping function instead of a copy of it (M2-02-06 PR-4).
const routerStart = Model.playerRouterState(null)
check("playerRouterState: the rest position, and a hand-made one is normalized", [routerStart, Model.playerRouterState({ entryId: "3", lastEndFile: { reason: "eof" }, idle: 1, tail: "junk" })], [{ entryId: 0, lastEndFile: null, idle: false, tail: [] }, { entryId: 3, lastEndFile: { reason: "eof" }, idle: false, tail: [] }])
check("routePlayerEvent: start-file records the entry and supersedes the last end-file (this is what makes a zap silent)", (() => {
  const ended = Model.routePlayerEvent(routerStart, '{"event":"end-file","reason":"stop","playlist_entry_id":1}')
  const loaded = Model.routePlayerEvent(ended, '{"event":"start-file","playlist_entry_id":2}')
  return [ended.lastEndFile.reason, loaded.lastEndFile, loaded.entryId]
})(), ["stop", null, 2])
check("routePlayerEvent: a start-file with no usable id keeps the entry it had", Model.routePlayerEvent({ entryId: 7, lastEndFile: null, idle: false, tail: [] }, '{"event":"start-file"}').entryId, 7)
check("routePlayerEvent: only error and fatal join the tail, redacted and trimmed", (() => {
  const info = Model.routePlayerEvent(routerStart, '{"event":"log-message","level":"info","prefix":"cplayer","text":"Playing: http://u:p@h.test/x"}')
  const err = Model.routePlayerEvent(info, '{"event":"log-message","level":"error","prefix":"stream","text":"Failed to open http://u:p@h.test/tok/1.m3u8\\n"}')
  const fatal = Model.routePlayerEvent(err, '{"event":"log-message","level":"fatal","prefix":"","text":"out of memory  "}')
  return [info.tail, err.tail, fatal.tail]
})(), [[], ["[stream] Failed to open h.test"], ["[stream] Failed to open h.test", "out of memory"]])
check("routePlayerEvent: the tail is five deep, oldest dropped", (() => {
  let st = routerStart
  for (let i = 1; i <= 6; i++) st = Model.routePlayerEvent(st, '{"event":"log-message","level":"error","prefix":"ffmpeg","text":"line ' + i + '"}')
  return [st.tail.length, st.tail[0], st.tail[4], Model.PLAYER_LOG_TAIL]
})(), [5, "[ffmpeg] line 2", "[ffmpeg] line 6", 5])
check("routePlayerEvent: idle-active is carried; junk, replies and an info line change nothing", (() => {
  const idle = Model.routePlayerEvent(routerStart, '{"event":"property-change","name":"idle-active","data":true}')
  const seeded = { entryId: 2, lastEndFile: { entryId: 2, reason: "error" }, idle: true, tail: ["x"] }
  const same = (line) => { const n = Model.routePlayerEvent(seeded, line); return n.entryId === seeded.entryId && n.lastEndFile === seeded.lastEndFile && n.idle === seeded.idle && n.tail === seeded.tail }
  return [idle.idle, same("not json"), same('{"error":"success","request_id":1}'), same('{"event":"log-message","level":"info","text":"hello"}'), same('{"event":"audio-reconfig"}')]
})(), [true, true, true, true, true])
check("routePlayerEvent: an untouched tail and end-file keep their reference, so the caller writes nothing", (() => {
  const seeded = { entryId: 1, lastEndFile: { entryId: 1, reason: "error" }, idle: false, tail: ["a"] }
  const next = Model.routePlayerEvent(seeded, '{"event":"property-change","name":"idle-active","data":true}')
  return [next.tail === seeded.tail, next.lastEndFile === seeded.lastEndFile]
})(), [true, true])
check("rememberEntryOwner: four deep, oldest dropped, and the ring never mutates its input", (() => {
  let owners = {}
  for (let i = 1; i <= 5; i++) owners = Model.rememberEntryOwner(owners, i, { id: "t:" + i, name: "Channel " + i })
  return [Object.keys(owners), owners["5"], Model.PLAYER_ENTRY_OWNERS]
})(), [["2", "3", "4", "5"], { id: "t:5", name: "Channel 5" }, 4])
check("rememberEntryOwner: an unusable id or no target records nothing (the same map back)", (() => {
  const owners = Model.rememberEntryOwner({}, 1, { id: "t:a", name: "A" })
  return [Model.rememberEntryOwner(owners, 0, { id: "t:b" }) === owners, Model.rememberEntryOwner(owners, "junk", { id: "t:b" }) === owners, Model.rememberEntryOwner(owners, 2, null) === owners, Model.rememberEntryOwner(null, 2, { id: "t:b", name: "B" })["2"]]
})(), [true, true, true, { id: "t:b", name: "B" }])
check("channelForEnd: the owner of the entry that ended, not what is playing now", Model.channelForEnd({ "1": { id: "t:a", name: "A" }, "2": { id: "t:b", name: "B" } }, { entryId: 1, reason: "error" }, { id: "t:b", name: "B" }), { id: "t:a", name: "A" })
check("channelForEnd fails open: unknown, missing and no end at all degrade to now-playing, never to nothing", [
  Model.channelForEnd({ "1": { id: "t:a", name: "A" } }, { entryId: 99, reason: "error" }, { id: "t:b", name: "B" }),
  Model.channelForEnd({ "1": { id: "t:a", name: "A" } }, { reason: "error" }, { id: "t:b", name: "B" }),
  Model.channelForEnd(null, null, { id: "t:b", name: "B" }),
  Model.channelForEnd(null, null, null)
], [{ id: "t:b", name: "B" }, { id: "t:b", name: "B" }, { id: "t:b", name: "B" }, null])
check("endedReport: the log tail outranks mpv's generic file_error and names the entry's owner", Model.endedReport({ lastEndFile: { entryId: 1, reason: "error", fileError: "loading failed" }, owners: { "1": { id: "t:a", name: "A" } }, nowPlaying: { id: "t:b", name: "B" }, tail: ["[stream] Failed to open h.test"] }), { notify: true, kind: "failed", target: { id: "t:a", name: "A" }, reason: "[stream] Failed to open h.test" })
check("endedReport: with no tail it quotes the verdict; a stop, a clean eof and a redirect say nothing", [
  Model.endedReport({ lastEndFile: { entryId: 1, reason: "error", fileError: "loading failed" }, nowPlaying: { id: "t:a", name: "A" }, tail: [] }).reason,
  Model.endedReport({ lastEndFile: null, nowPlaying: { id: "t:a", name: "A" } }).reason,
  Model.endedReport({ lastEndFile: { reason: "error" }, nowPlaying: { id: "t:a", name: "A" }, userStopped: true }).notify,
  Model.endedReport({ lastEndFile: { reason: "error" }, nowPlaying: { id: "t:a", name: "A" }, stopping: true }).notify,
  Model.endedReport({ lastEndFile: { reason: "eof" }, nowPlaying: { id: "t:a", name: "A" } }).notify,
  Model.endedReport({ lastEndFile: { reason: "redirect" }, nowPlaying: { id: "t:a", name: "A" } }).kind
], ["loading failed", Model.PLAYER_GENERIC_FAILURE, false, false, false, "ignored"])

// ---- notifications ----
const tvOff = "\udb81\udd03", alert = "\udb80\udc26", refreshGlyph = "\udb81\udc50"
const Q = (s) => String.fromCharCode(0x201c) + s + String.fromCharCode(0x201d)   // typographic quotes, file stays ASCII
check("notifyArgv streamFailed", Model.notifyArgv("streamFailed", { name: "Sky Sports", reason: "HTTP 403" }),
  ["omarchy-notification-send", "--app-name", "IPTV", "-u", "normal", "-g", tvOff, "-r", "74011", "Stream failed", Q("Sky Sports") + " did not play" + SEP + "HTTP 403"])
check("notifyArgv streamFailed without reason", Model.notifyArgv("streamFailed", { name: "X" }).slice(-1), [Q("X") + " did not play"])
check("notifyArgv streamFailed redacts URLs from the reason", Model.notifyArgv("streamFailed", { name: "X", reason: "Failed to open https://u:p@h.test/live/x.m3u8?t=1." }).slice(-1), [Q("X") + " did not play" + SEP + "Failed to open h.test"])
// S-04: the wrapper reads a body matching --urgency=* / --icon=* / -g ... as an option.
check("notifyArgv body never starts with a dash (S-04)", (() => {
  const out = []
  for (const name of ["--urgency=critical", "-g", "--icon=x", "--exec", "-", "", null]) {
    const a = Model.notifyArgv("streamFailed", { name: name, reason: "-r 1" })
    out.push(a.slice(9).every(item => item.charAt(0) !== "-"))
  }
  return out
})(), [true, true, true, true, true, true, true])
check("notifyArgv streamFailed cleans and quotes a hostile name", Model.notifyArgv("streamFailed", { name: "--urgency=critical" }).slice(-1), [Q("urgency=critical") + " did not play"])
check("notifyArgv streamFailed falls back to Channel for an all-dash name", Model.notifyArgv("streamFailed", { name: "---" }).slice(-1), [Q("Channel") + " did not play"])
check("notifyArgv playlistRefreshed", Model.notifyArgv("playlistRefreshed", { channelCount: 1204, groupCount: 38 }).slice(3), ["-u", "low", "-g", refreshGlyph, "-r", "74012", "Playlist refreshed", "1,204 channels in 38 groups"])
check("notifyArgv playlistError with cache", Model.notifyArgv("playlistError", { reason: "HTTP 503", cachedAt: "12:40" }).slice(-2), ["Playlist error", "Could not fetch the playlist (HTTP 503). Using cached copy from 12:40."])
check("notifyArgv playlistError without cache", Model.notifyArgv("playlistError", { reason: "Timed out" }).slice(-1), ["Could not fetch the playlist (Timed out). Open the guide for details."])
check("notifyArgv epgError", Model.notifyArgv("epgError", { reason: "HTTP 404 Not Found" }).slice(3), ["-u", "low", "-g", alert, "-r", "74014", "Guide data error", "Could not fetch the EPG (HTTP 404 Not Found). Channels still work."])
check("notifyArgv mpvMissing", Model.notifyArgv("mpvMissing").slice(3), ["-u", "critical", "-g", tvOff, "-r", "74015", "mpv not found", "Install mpv to play channels."])
check("notifyArgv unknown", Model.notifyArgv("nope"), null)

// ---- privacy ----
check("sourceLabel http with credentials and port", Model.sourceLabel("http://user:pw@tv.example.net:8080/get.php?username=u&password=p"), "http://tv.example.net")
check("sourceLabel https", Model.sourceLabel("HTTPS://Host.Test/x.m3u"), "https://Host.Test")
check("sourceLabel local", [Model.sourceLabel("/home/x/list.m3u"), Model.sourceLabel("~/l.m3u"), Model.sourceLabel("file:///tmp/x.m3u")], ["local file", "local file", "local file"])
check("sourceLabel empty / junk", [Model.sourceLabel(""), Model.sourceLabel("ftp"), Model.sourceLabel(null)], ["", "unknown source", ""])
check("hostOf", [Model.hostOf("http://u:p@h.test/x"), Model.hostOf("/x"), Model.hostOf("")], ["h.test", "local file", ""])
check("redactUrls replaces every URL by its host (D-QA-01)", Model.redactUrls("Failed to open http://user:pass@tv.example.net:8080/get.php?u=1&p=2."), "Failed to open tv.example.net")
check("redactUrls several URLs", Model.redactUrls("open https://a.b/c/d?e=f and rtsp://u:p@h:554/x fine"), "open a.b and h fine")
check("redactUrls no urls", Model.redactUrls("plain text"), "plain text")
check("redactUrls empty host", Model.redactUrls("x file:///etc/passwd y"), "x [url] y")
check("scrubUrls is an alias of redactUrls", Model.scrubUrls("see http://h.test/p"), "see h.test")

// ---- formatting ----
check("formatCount", [Model.formatCount(0), Model.formatCount(999), Model.formatCount(1204), Model.formatCount(1234567), Model.formatCount("x")], ["0", "999", "1,204", "1,234,567", "0"])
check("pluralChannels", [Model.pluralChannels(1), Model.pluralChannels(2), Model.pluralChannels(1204)], ["1 channel", "2 channels", "1,204 channels"])
check("formatClock HH:MM", Model.formatClock(Math.floor(new Date(2026, 8, 12, 21, 5).getTime() / 1000)), "21:05")
check("formatClock invalid", [Model.formatClock(0), Model.formatClock("x"), Model.formatClock(null)], ["", "", ""])
check("epgFraction", [Model.epgFraction(150, 100, 200), Model.epgFraction(50, 100, 200), Model.epgFraction(300, 100, 200), Model.epgFraction(1, 5, 5), Model.epgFraction(null, 1, 2)], [0.5, 0, 1, 0, 0])
check("epgFields now+next", (() => {
  const f = Model.epgFields({ now: { title: "News", start: 1000, stop: 3000 }, next: { title: "Weather", start: 3000 } }, 2000)
  return [f.nowTitle, f.nowStart, f.nowStop, f.nextTitle, f.nextStart, f.until !== "", f.fraction]
})(), ["News", 1000, 3000, "Weather", 3000, true, 0.5])
check("epgFields expired now keeps next", Model.epgFields({ now: { title: "Old", start: 1, stop: 10 }, next: { title: "N" } }, 20), { nowTitle: "", nowStart: 0, nowStop: 0, nextTitle: "N", nextStart: 0, until: "", fraction: 0 })
check("epgFields null", Model.epgFields(null, 0).nowTitle, "")
check("formatEpgLine now+next", (() => {
  const line = Model.formatEpgLine({ now: { title: "News", start: 1000, stop: 4102444800 }, next: { title: "Weather", start: 4102444800 } }, 2000)
  return [line.now.indexOf("Now: News until ") === 0, line.next.indexOf("Next: Weather at ") === 0]
})(), [true, true])
check("formatEpgLine expired now", Model.formatEpgLine({ now: { title: "Old", stop: 10 } }, 20), { now: "", next: "" })
check("rowDetail full", Model.rowDetail({ showGroup: true, group: "UK | SPORTS", nowTitle: "Match", nextTitle: "Replay" }), "UK | SPORTS" + SEP + "Now: Match" + SEP + "Next: Replay")
check("rowDetail inside own group, no EPG", Model.rowDetail({ showGroup: false, group: "UK", nowTitle: "", nextTitle: "" }), "")
check("rowDetail failed replaces EPG segments", Model.rowDetail({ showGroup: true, group: "UK", failedAt: "21:12", nowTitle: "X" }), "UK" + SEP + "Failed 21:12" + SEP + "Space to retry")
check("rowAccessibleName", Model.rowAccessibleName({ name: "BBC", favorite: true, playing: true, nowTitle: "News", until: "21:30", failedAt: "" }), "BBC, favorite, playing, now News until 21:30")
check("rowAccessibleName failed", Model.rowAccessibleName({ name: "BBC", failedAt: "21:12" }), "BBC, failed")
check("elide", Model.elide("abcdefgh", 5), "abcd\u2026")
check("elide short", Model.elide("abc", 5), "abc")
check("noMatchesTitle All", Model.noMatchesTitle("sky", "favorites"), "No matches for \u201csky\u201d")
check("noMatchesTitle group", Model.noMatchesTitle("sky", "g:UK | SPORTS"), "No matches for \u201csky\u201d in UK | SPORTS")

// ---- bar widget ----
check("barGlyph states", [Model.barGlyph({ playing: true, error: true }), Model.barGlyph({ error: true }), Model.barGlyph({}), Model.barGlyph(null)], ["\udb81\udd67", "\udb81\udd03", "\udb81\udd02", "\udb81\udd02"])
check("barTooltip idle", Model.barTooltip({ configured: true }), "IPTV" + SEP + "click to open the guide")
check("barTooltip not configured", Model.barTooltip({ configured: false }), "IPTV" + SEP + "no playlist configured")
check("barTooltip playing full name", Model.barTooltip({ configured: true, playing: true, name: "Sky Sports Main Event" }), "Playing Sky Sports Main Event")
check("barTooltip error", Model.barTooltip({ configured: true, error: true }), "IPTV" + SEP + "playlist error, open the guide")
check("barTooltip refreshing", Model.barTooltip({ configured: true, refreshing: true }), "IPTV" + SEP + "refreshing playlist\u2026")
check("barTooltip service missing", Model.barTooltip({ serviceMissing: true }), "IPTV" + SEP + "service not loaded, run omarchy restart shell")
check("barAccessibleName", [Model.barAccessibleName({}), Model.barAccessibleName({ playing: true, name: "X" }), Model.barAccessibleName({ error: true })], ["IPTV, idle", "IPTV, playing X", "IPTV, playlist error"])

// ---- footer ----
check("footerStatus normal", Model.footerStatus({ count: 1204, lastUpdated: "12:40" }), "1,204 channels" + SEP + "updated 12:40")
check("footerStatus cached", Model.footerStatus({ count: 1204, lastUpdated: "12:40", stale: true }), "1,204 channels" + SEP + "cached 12:40" + SEP + "offline")
check("footerStatus playing", Model.footerStatus({ count: 5, playingName: "Arte HD" }), "\udb81\udc0a Arte HD" + SEP + "s stop")
check("footerStatus transient wins", Model.footerStatus({ count: 5, playingName: "Arte", transient: "Stopped" }), "Stopped")
check("footerStatus bounded search", Model.footerStatus({ count: 5, truncated: true, resultTotal: 1240, cap: 200 }), "First 200 of 1,240" + SEP + "keep typing")
check("footerStatus refreshing", Model.footerStatus({ count: 5, refreshing: true }), "Refreshing\u2026")
check("footerStatus epg pending", Model.footerStatus({ count: 5, epgPending: true }), "Guide data loading\u2026")
// D-LIVE-09 / UX 4.4-4.6: empty states leave the status slot blank; only a transient shows.
check("footerStatus blank when not configured", [Model.footerStatus({ configured: false, count: 0, refreshing: true }), Model.footerStatus({ configured: false, count: 0, transient: "Set a playlist first" })], ["", "Set a playlist first"])
check("footerStatus blank without channels (loading / error)", [Model.footerStatus({ configured: true, count: 0, refreshing: true }), Model.footerStatus({ configured: true, count: 0, lastUpdated: "12:40" })], ["", ""])
// D-LIVE-02: epg-now.json is stale once validUntil has passed or is missing.
check("epgNowStale", [Model.epgNowStale({ validUntil: 200 }, 100), Model.epgNowStale({ validUntil: 100 }, 100), Model.epgNowStale({}, 100), Model.epgNowStale(null, 100), Model.epgNowStale({ validUntil: "x" }, 1)], [false, true, true, true, true])
check("footerHints search", Model.footerHints({ mode: "search", query: "" }).map(h => h[0]), ["Enter", "Up/Down", "Left/Right", "Tab", "Esc"])
check("footerHints search with query says clear/narrow", Model.footerHints({ mode: "search", query: "x" }).slice(2), [["Left/Right", "narrow"], ["Tab", "keys"], ["Esc", "clear"]])
check("footerHints list", Model.footerHints({ mode: "list" }).map(h => h[0]).join(" "), "j/k h/l Enter Space f s p r / o")
check("footerHints empty states (UX-SOURCES 5.3: r retry)", [Model.footerHints({ empty: "error" }), Model.footerHints({ empty: "loading" })], [[["r", "retry"], ["Esc", "close"]], [["Esc", "close"]]])

// ---- player shutdown ladder (D-LIVE-17) ----
check("shutdown timing constants", [Model.STOP_QUIT_GRACE_MS, Model.STOP_KILL_GRACE_MS, Model.HEALTH_SKIPS_BEFORE_RESTART], [2000, 2000, 3])
check("stopEscalation: idle -> quit over IPC, then wait the quit grace", Model.stopEscalation(""), { action: "quit", signal: 0, waitMs: 2000 })
check("stopEscalation: quit ignored -> SIGTERM, then wait the kill grace", Model.stopEscalation("quit"), { action: "term", signal: 15, waitMs: 2000 })
check("stopEscalation: SIGTERM ignored -> SIGKILL, nothing left to arm", Model.stopEscalation("term"), { action: "kill", signal: 9, waitMs: 0 })
check("stopEscalation: after SIGKILL only the exit is awaited", Model.stopEscalation("kill"), { action: "kill", signal: 0, waitMs: 0 })
check("stopEscalation: null and unknown stages", [Model.stopEscalation(null), Model.stopEscalation("bogus")], [{ action: "quit", signal: 0, waitMs: 2000 }, { action: "kill", signal: 0, waitMs: 0 }])
check("stopEscalation: the full ladder ends in SIGKILL within two grace periods", (function() {
  var stage = "", waited = 0, sent = []
  for (var i = 0; i < 5; i++) {
    var step = Model.stopEscalation(stage)
    if (step.signal) sent.push(step.signal)
    stage = step.action
    if (step.waitMs === 0) break
    waited += step.waitMs
  }
  return { stage: stage, waited: waited, sent: sent }
})(), { stage: "kill", waited: 4000, sent: [15, 9] })
check("healthTick: a free tick probes and resets the skip run", [Model.healthTick(0, false), Model.healthTick(2, false)], [{ check: true, restart: false, skips: 0 }, { check: true, restart: false, skips: 0 }])
check("healthTick: busy ticks are skipped and counted", [Model.healthTick(0, true), Model.healthTick(1, true)], [{ check: false, restart: false, skips: 1 }, { check: false, restart: false, skips: 2 }])
check("healthTick: the third busy tick in a row restarts the player", Model.healthTick(2, true), { check: false, restart: true, skips: 0 })
check("healthTick: null / negative skips", [Model.healthTick(null, true), Model.healthTick(-5, true), Model.healthTick("x", false)], [{ check: false, restart: false, skips: 1 }, { check: false, restart: false, skips: 1 }, { check: true, restart: false, skips: 0 }])

// ---- why the player ended (ARCHITECTURE-PLAYER.md 4.8) ----
// The exit code is gone with the attached Process; the verdict now comes from
// mpv's own `end-file` reason. Vectors shared with the Python mirror.
check("endedVerdict: a dead stream notifies with mpv's file_error", Model.endedVerdict({ reason: "error", file_error: "loading failed", playlist_entry_id: 1 }, false, false), { notify: true, reason: "loading failed", kind: "failed" })
check("endedVerdict: parsePlayerEvent's own shape round-trips (fileError, not file_error)", Model.endedVerdict(Model.parsePlayerEvent('{"event":"end-file","reason":"error","playlist_entry_id":2,"file_error":"loading failed"}'), false, false), { notify: true, reason: "loading failed", kind: "failed" })
check("endedVerdict: we caused it, so it is silent whatever mpv says", [Model.endedVerdict({ reason: "error", file_error: "x" }, true, false).notify, Model.endedVerdict({ reason: "error", file_error: "x" }, false, true).notify], [false, false])
check("endedVerdict: a clean end and an mpv-side quit stay silent (PO-4)", [Model.endedVerdict({ reason: "eof" }, false, false).kind, Model.endedVerdict({ reason: "quit" }, false, false).kind], ["silent", "silent"])
check("endedVerdict: redirect is never terminal", Model.endedVerdict({ reason: "redirect" }, false, false), { notify: false, reason: "", kind: "ignored" })
check("endedVerdict: no end-file at all is a failure with a generic reason", Model.endedVerdict(null, false, false), { notify: true, reason: Model.PLAYER_GENERIC_FAILURE, kind: "failed" })
check("endedVerdict: the entry gate fails open (F4) - a null or unknown entry id never suppresses", [
  Model.endedVerdict({ reason: "error", file_error: "loading failed" }, false, false).notify,
  Model.endedVerdict({ reason: "error", file_error: "loading failed", playlist_entry_id: null }, false, false).notify,
  Model.endedVerdict({ reason: "error", file_error: "loading failed", playlist_entry_id: 4242 }, false, false).notify
], [true, true, true])
check("endedVerdict: a file_error carrying a URL is redacted", Model.endedVerdict({ reason: "error", file_error: "Failed to open http://u:p@provider.test/live/tok/1.m3u8" }, false, false).reason, "Failed to open provider.test")

// ---- shared vectors with the Python mirror (tests/fixtures/player-argv.json) ----
// (loaded at the top of this file; the same bytes tests/test_player.py reads)
check("player fixture has all four tables", [playerFixture.mpvArgv.length > 0, playerFixture.stopLadder.length, playerFixture.endedVerdict.length > 0, playerFixture.session.length > 0, playerFixture.genericFailure], [true, 5, true, true, Model.PLAYER_GENERIC_FAILURE])
check("player fixture pins the whole reserved set", playerFixture.mpvReserved.slice().sort(), Object.keys(Model.MPV_RESERVED).sort())
for (const v of playerFixture.mpvArgv) {
  const filtered = Model.splitMpvArgs((v.mpvArgs || []).join(" "))
  check("fixture mpvArgv: " + v.name, Model.buildMpvArgv({ socketPath: v.socketPath, stateDir: v.stateDir, extraArgs: filtered.args }), v.argv)
  if (v.rejected) check("fixture mpvArgv rejects: " + v.name, filtered.rejected, v.rejected)
}
for (const v of playerFixture.stopLadder) {
  check("fixture stopLadder: " + v.name, Model.stopEscalation(v.stage), { action: v.action, signal: v.signal, waitMs: v.waitMs })
}
for (const v of playerFixture.endedVerdict) {
  check("fixture endedVerdict: " + v.name, Model.endedVerdict(v.endFile, v.userStopped, v.stopping), v.verdict)
}
// The session record is read by Model.parseState here and by normalize_state
// in tests/test_state.py, from the same bytes (section 8, PO-3).
for (const v of playerFixture.session) {
  check("fixture session: " + v.name, Model.parseState(JSON.stringify(v.state)).session, v.record)
  check("fixture session via stateSession: " + v.name, Model.stateSession(Model.parseState(JSON.stringify(v.state))), v.record)
}

// ---- playlist warnings (D-LIVE-18) ----
const capWarnings = ["truncated to 50000 channels (500 entries skipped)", "group count capped at 2000; 2091 channels listed under Ungrouped"]
check("statusWarnings from a successful run", Model.statusWarnings({ ok: true, warnings: capWarnings }), capWarnings)
check("statusWarnings from helper JSON", Model.statusWarnings(Model.parseHelperStatus('{"ok": true, "kind": "playlist", "warnings": ["3 URL lines without #EXTINF skipped"]}', "playlist")), ["3 URL lines without #EXTINF skipped"])
check("statusWarnings never carries a URL", Model.statusWarnings({ ok: true, warnings: ["dropped header with unsafe name for http://u:p@h.test/x?y=1"] }), ["dropped header with unsafe name for h.test"])
check("statusWarnings drops blanks, keeps the rest as text", Model.statusWarnings({ ok: true, warnings: ["", "  ", null, 42, " trimmed "] }), ["42", "trimmed"])
check("statusWarnings is empty for a failed run (the previous load's warnings stay)", [Model.statusWarnings({ ok: false, warnings: ["x"] }), Model.statusWarnings({ ok: true }), Model.statusWarnings(null)], [[], [], []])
check("warningLine single", Model.warningLine([capWarnings[0]]), "Playlist warning: truncated to 50000 channels (500 entries skipped)")
check("warningLine counts the rest", [Model.warningLine(capWarnings), Model.warningLine(["a", "b", "c"])], ["Playlist warning: truncated to 50000 channels (500 entries skipped) (+1 more)", "Playlist warning: a (+2 more)"])
check("warningLine empty", [Model.warningLine([]), Model.warningLine(null), Model.warningLine([""])], ["", "", ""])
check("warningLine never carries a URL", Model.warningLine(["see http://user:pw@h.test/list.m3u?token=1 for details"]), "Playlist warning: see h.test for details")
check("footerStatus warning replaces the counts line", Model.footerStatus({ configured: true, count: 50000, lastUpdated: "01:53", warning: "Playlist warning: x" }), "Playlist warning: x")
check("footerStatus warning yields to transient, search cap, playing, refreshing and EPG pending", [
  Model.footerStatus({ count: 5, warning: "W", transient: "Stopped" }),
  Model.footerStatus({ count: 5, warning: "W", truncated: true, resultTotal: 300, cap: 200 }),
  Model.footerStatus({ count: 5, warning: "W", playingName: "Arte" }),
  Model.footerStatus({ count: 5, warning: "W", refreshing: true }),
  Model.footerStatus({ count: 5, warning: "W", epgPending: true })
], ["Stopped", "First 200 of 300" + SEP + "keep typing", "\udb81\udc0a Arte" + SEP + "s stop", "Refreshing\u2026", "Guide data loading\u2026"])
check("footerStatus warning needs a loaded playlist", [Model.footerStatus({ configured: false, count: 0, warning: "W" }), Model.footerStatus({ configured: true, count: 0, warning: "W" })], ["", ""])
check("footerStatus no warning keeps the counts line", Model.footerStatus({ count: 5, lastUpdated: "12:40", warning: "" }), "5 channels" + SEP + "updated 12:40")

// ---- footer precedence ladder (UX 6.3, D-LIVE-22) ----
// The whole ladder as a table, highest rung first, so the next edit to
// footerStatus cannot reorder it silently: the walk below proves every rung
// beats every rung under it, one pair at a time and all of them at once.
// Each row is [name, the options that raise the rung, the line it must
// produce] on top of `ladderBase`. `warning` is one slot shared by both
// warning kinds, so the playlist row and the guide-data row collide there on
// purpose: merging lower rungs first leaves the higher rung's value in place,
// which is exactly what footerWarning does when both helpers warn at once.
const ladderBase = { configured: true, count: 8, lastUpdated: "22:49" }
const epgWarnText = "1 programmes for channels not in the playlist dropped"
const warnBoth = Model.footerWarning(["truncated to 50,000 channels"], [epgWarnText])
const warnEpgOnly = Model.footerWarning([], [epgWarnText])
const cachedLine = "8 channels" + SEP + "cached 22:49" + SEP + "offline"
const ladder = [
  ["transient", { transient: "Refreshed" + SEP + "8 channels" }, "Refreshed" + SEP + "8 channels"],
  ["bounded search", { truncated: true, resultTotal: 1240, cap: 200 }, "First 200 of 1,240" + SEP + "keep typing"],
  ["playing", { playingName: "Arte" }, "\udb81\udc0a Arte" + SEP + "s stop"],
  ["refreshing", { refreshing: true }, "Refreshing\u2026"],
  ["degraded (cached, offline)", { stale: true }, cachedLine],
  ["guide data pending", { epgPending: true }, "Guide data loading\u2026"],
  ["playlist warning", { warning: warnBoth }, "Playlist warning: truncated to 50,000 channels"],
  ["guide data warning", { warning: warnEpgOnly }, "Guide data warning: " + epgWarnText],
  ["channel count", {}, "8 channels" + SEP + "updated 22:49"]
]
// Lower rungs applied first, the rung under test last, so a shared slot ends
// up holding the higher rung's value.
function ladderOpts(rungs) {
  const out = Object.assign({}, ladderBase)
  rungs.slice().sort((a, b) => b - a).forEach(i => Object.assign(out, ladder[i][1]))
  return out
}
for (let i = 0; i < ladder.length; i++) {
  check("footer ladder: " + ladder[i][0] + " on its own", Model.footerStatus(ladderOpts([i])), ladder[i][2])
  for (let j = i + 1; j < ladder.length; j++) {
    check("footer ladder: " + ladder[i][0] + " outranks " + ladder[j][0], Model.footerStatus(ladderOpts([i, j])), ladder[i][2])
  }
  const below = []
  for (let j = i; j < ladder.length; j++) below.push(j)
  check("footer ladder: " + ladder[i][0] + " outranks every rung below it at once", Model.footerStatus(ladderOpts(below)), ladder[i][2])
}

// The D-LIVE-22 pair itself, in the shape QA reproduced it (h21 / d19.sh):
// an EPG warning next to a cached copy after a failed refresh.
check("D-LIVE-22: a guide-data warning never displaces `cached HH:MM - offline`", Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", stale: true, warning: warnEpgOnly }), cachedLine)
check("D-LIVE-22: nor does a playlist warning, nor both kinds at once", [
  Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", stale: true, warning: Model.footerWarning(["truncated to 50,000 channels"], []) }),
  Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", stale: true, warning: warnBoth })
], [cachedLine, cachedLine])
check("D-LIVE-22: a cached copy with no timestamp keeps its offline marker over a warning", Model.footerStatus({ configured: true, count: 8, stale: true, warning: warnEpgOnly }), "8 channels" + SEP + "cached" + SEP + "offline")
check("D-LIVE-22: the active source label still rides the degraded line (UX-SOURCES 5.3)", Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", stale: true, warning: warnBoth, activeLabel: "NAS", sourceCount: 2 }), "NAS" + SEP + cachedLine)
check("D-LIVE-22: a guide-data load pending behind a cached copy still shows the cache", [
  Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", stale: true, epgPending: true }),
  Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", stale: true, epgPending: true, warning: warnBoth })
], [cachedLine, cachedLine])
check("D-LIVE-22: a warning arriving while playing or refreshing still loses, cached or not", [
  Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", playingName: "Arte", warning: warnBoth }),
  Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", stale: true, playingName: "Arte", warning: warnEpgOnly }),
  Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", refreshing: true, warning: warnBoth }),
  Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", stale: true, refreshing: true, warning: warnEpgOnly })
], ["\udb81\udc0a Arte" + SEP + "s stop", "\udb81\udc0a Arte" + SEP + "s stop", "Refreshing\u2026", "Refreshing\u2026"])
check("D-LIVE-22: with a fresh copy the warnings keep their rungs above the counts line", [
  Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", warning: warnBoth }),
  Model.footerStatus({ configured: true, count: 8, lastUpdated: "22:49", warning: warnEpgOnly })
], ["Playlist warning: truncated to 50,000 channels", "Guide data warning: " + epgWarnText])

// ============================================================ sources (M2-01)
// docs/ARCHITECTURE-SOURCES.md section 3 and docs/UX-SOURCES.md 5.4-5.8 /
// 8.1 under the rulings SR1-SR10. The shared validation vectors live in
// tests/fixtures/source-urls.json (also run by Lane 2's Python mirror).
const fs = require("fs")
const path = require("path")
const ELL = "\u2026"

// ---- constants (SR5) ----
check("LIMITS are the canonical caps", Model.LIMITS, { url: 2048, label: 64, server: 512, user: 256, pass: 256, sources: 50 })
check("architecture constant names agree with LIMITS", [Model.MAX_SOURCE_URL, Model.MAX_LABEL, Model.MAX_XTREAM_SERVER, Model.MAX_XTREAM_FIELD, Model.MAX_SOURCES, Model.STATE_VERSION, Model.CACHE_LAYOUT, Model.SOURCES_DIR], [2048, 64, 512, 256, 50, 2, 2, "sources"])
check("MASK and the clear params", [Model.MASK, Model.MASK_CLEAR_PARAMS], ["****", ["type", "output"]])
check("SOURCE_KEYS table", Model.SOURCE_KEYS, { open: "o", add: "a", xtream: "c", edit: "e", remove: "x", reveal: "Ctrl+R", clear: "Ctrl+U", paste: "Ctrl+V" })
check("Sources glyphs are supplementary-plane Nerd Font codepoints", ["sources", "check", "eye", "eyeOff", "plus", "key", "pencil", "closeCircle"].map(k => Model.GLYPHS[k].codePointAt(0).toString(16)), ["f0411", "f012c", "f0208", "f0209", "f0415", "f0306", "f03eb", "f0159"])
check("guide modes", Model.GUIDE_MODES, ["search", "list", "sources", "sourceEdit", "sourceXtream", "confirmRemove"])

// ---- sanitizeInput (ARCHITECTURE-SOURCES 3.1 / 6.1) ----
check("sanitizeInput strips CR LF TAB and C1, trims space and NBSP", Model.sanitizeInput("\u00a0 http://h.test/a\r\nb\tc\u0085 \u00a0", 100), "http://h.test/abc")
check("sanitizeInput caps at the limit in UTF-16 units", Model.sanitizeInput("abcdef", 3), "abc")
check("sanitizeInput null / number", [Model.sanitizeInput(null, 5), Model.sanitizeInput(42, 5)], ["", "42"])
check("sanitizeInput default cap is the URL cap", Model.sanitizeInput("x".repeat(3000)).length, 2048)
check("sanitizeTyping keeps edges (a label can be typed with spaces)", Model.sanitizeTyping(" NAS \n", 10), " NAS ")
check("sanitizeTyping still caps and strips controls", Model.sanitizeTyping("a\u0000bcdefgh", 4), "abcd")

// ---- validateSourceUrl: every case of the shared fixture (SR6) ----
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures/source-urls.json"), "utf8"))
check("fixture has every UX 5.4 URL code plus unsafe_path", [...new Set(fixture.filter(c => !c.ok).map(c => c.code))].sort(), ["empty", "invalid", "relative_path", "scheme", "too_long", "unsafe_path"])
check("fixture covers files, IDN, IPv6, userinfo, fragments, control characters and the cap", fixture.length >= 75, true)
for (const c of fixture) {
  const r = Model.validateSourceUrl(c.input, c.origin ? { origin: c.origin } : undefined)
  const name = "fixture " + JSON.stringify(c.input.length > 48 ? c.input.slice(0, 45) + "..." : c.input) + (c.origin ? " [" + c.origin + "]" : "") + (c.note ? " (" + c.note + ")" : "")
  if (c.ok) check(name, [r.ok, r.kind, r.url, r.host, Model.sourceKey(r.url)], [true, c.kind, c.url, c.host, c.key])
  else check(name, [r.ok, r.code], [false, c.code])
}
// JS-only vectors (kept out of the shared fixture until the Python mirror
// agrees; ARCHITECTURE-SOURCES 3.1 steps 4 and 5): a file URL's query and
// fragment are dropped like urlsplit().path, two ports are not a port, a
// bare "." is a relative path.
check("validateSourceUrl file URL query and fragment dropped", Model.validateSourceUrl("file:///srv/tv/list.m3u?x=1#f").url, "/srv/tv/list.m3u")
check("validateSourceUrl two ports are invalid", Model.validateSourceUrl("http://h.test:80:1/").code, "invalid")
check("validateSourceUrl bare dot is a relative path", Model.validateSourceUrl(".").code, "relative_path")
check("validateSourceUrl origin cli accepts ~ verbatim, forms refuse it (SR11)", [Model.validateSourceUrl("~/tv/list.m3u", { origin: "cli" }).url, Model.validateSourceUrl("~/tv/list.m3u", { origin: "cli" }).kind, Model.validateSourceUrl("~/tv/list.m3u").code, Model.validateSourceUrl("~/tv/list.m3u", { origin: "form" }).code], ["~/tv/list.m3u", "file", "relative_path", "relative_path"])
check("looksLikeHost heuristic (SR12)", ["list.m3u", "localhost:8080/x", "provider.test/list.m3u", "playlist", "Videos/list.m3u", ""].map(Model.looksLikeHost), [true, true, true, false, false, false])
check("validateSourceUrl port normalization and bounds (SR15)", [Model.validateSourceUrl("http://h.test:0080/x").url, Model.validateSourceUrl("http://h.test:0/x").url, Model.validateSourceUrl("http://h.test:65536/x").code, Model.validateSourceUrl("http://[::1]:00443/x").url], ["http://h.test/x", "http://h.test:0/x", "invalid", "http://[::1]:443/x"])
check("sanitizeInput strips a leading BOM only (SR15)", [Model.sanitizeInput("\ufeffhttp://h.test/x"), Model.sanitizeInput("a\ufeffb")], ["http://h.test/x", "a\ufeffb"])
check("statusReason: one spelling for a non-M3U source (SR28)", [Model.statusReason({ ok: false, error: { code: "not_m3u", message: "" } }), Model.statusReason({ ok: false, error: { code: "not_a_playlist", message: "" } })], ["Not an M3U playlist", "Not an M3U playlist"])
check("codePointLength / capCodePoints count code points, not UTF-16 units (SR22)", [Model.codePointLength("a\ud83d\udce1b"), Model.capCodePoints("a\ud83d\udce1b", 2), Model.validateLabel("\ud83d\udce1".repeat(64), [], "").ok, Model.validateLabel("\ud83d\udce1".repeat(65), [], "").code, Model.uniqueLabel("\ud83d\udce1".repeat(70), []).length], [3, "a\ud83d\udce1", true, "label_too_long", 128])
check("formCapacity is the cap plus slack so over-cap input is refused, not cut (SR18)", [Model.formCapacity("playlist") > Model.formLimit("playlist"), Model.withFormValue(Model.openFirstRun(Model.guideState("all")), "playlist", "http://h.test/" + "a".repeat(2100)).form.values.playlist.length > 2048, Model.validateUrlForm({ label: "", playlist: "http://h.test/" + "a".repeat(2100), epg: "" }, [], "").error.code], [true, true, "too_long"])
check("validateSourceUrl result shape", Object.keys(Model.validateSourceUrl("http://h.test/x")).sort(), ["code", "field", "host", "kind", "message", "ok", "url"])
check("validateSourceUrl message is the UX copy", Model.validateSourceUrl("provider.test/x").message, "Start with http://, https://, or / for a local file")
check("validateSourceUrl too_long quotes LIMITS.url", Model.validateSourceUrl("/" + "x".repeat(2100)).message, "Too long" + SEP + "max 2,048 characters")
check("validateSourceUrl epg: empty is fine (optional)", Model.validateSourceUrl("   ", { kind: "epg" }), { ok: true, code: "ok", message: "", field: "epg", kind: "", url: "", host: "" })
check("validateSourceUrl epg: errors carry the EPG prefix", [Model.validateSourceUrl("x.test/e.xml", { kind: "epg" }).message, Model.validateSourceUrl("http://h .test/", { kind: "epg" }).message, Model.validateSourceUrl("~/e.xml", { kind: "epg" }).message], ["EPG: start with http://, https://, or / for a local file", "EPG: invalid URL" + SEP + "check the host", "EPG: use an absolute path (starts with /, not ~)"])
check("validateSourceUrl null", Model.validateSourceUrl(null).code, "empty")
check("normalizeSourceUrl", [Model.normalizeSourceUrl(" HTTP://H.test:80/x#f "), Model.normalizeSourceUrl("ftp://x"), Model.normalizeSourceUrl("file:///a/b.m3u")], ["http://h.test/x", "", "/a/b.m3u"])
check("isUrlField", [Model.isUrlField("playlist"), Model.isUrlField("epg"), Model.isUrlField("label"), Model.isUrlField("server")], [true, true, false, false])

// ---- copy per code (UX 5.4) ----
check("sourceErrorMessage playlist codes", ["empty", "scheme", "invalid", "relative_path", "too_long", "unsafe_path"].map(Model.sourceErrorMessage), [
  "Enter a playlist URL or path",
  "Start with http://, https://, or / for a local file",
  "Invalid URL" + SEP + "check the host",
  "Use an absolute path (starts with /, not ~)",
  "Too long" + SEP + "max 2,048 characters",
  "Path not allowed"
])
check("sourceErrorMessage label and duplicate codes quote the label", [Model.sourceErrorMessage("duplicate", { label: "Provider" }), Model.sourceErrorMessage("duplicate"), Model.sourceErrorMessage("label_taken", { label: "Provider" }), Model.sourceErrorMessage("label_too_long")], ["Already in Sources as " + Q("Provider"), "Already in Sources", "A source named " + Q("Provider") + " already exists", "Label too long" + SEP + "max 64 characters"])
check("sourceErrorMessage Xtream codes", ["server_empty", "server_scheme", "server_path", "user_empty", "pass_empty", "user_too_long", "pass_too_long", "server_too_long"].map(Model.sourceErrorMessage), [
  "Enter the server URL", "Server must start with http:// or https://", "Server is just http://host:port" + SEP + "no path", "Enter the username", "Enter the password", "Username too long" + SEP + "max 256 characters", "Password too long" + SEP + "max 256 characters", "Server too long" + SEP + "max 512 characters"
])
check("sourceErrorMessage service codes (SR24, SR25)", [Model.sourceErrorMessage("too_many"), Model.sourceErrorMessage("persist_failed"), Model.sourceErrorMessage("busy") !== "", Model.sourceErrorMessage("unknown_source") !== "", Model.sourceErrorMessage("not_ready") !== ""], ["Sources is full (50)" + SEP + "remove one first", "Could not save settings" + SEP + "try omarchy bar set", true, true, true])
check("sourceErrorMessage architecture names map onto the UX sentences", [Model.sourceErrorMessage("bad_url"), Model.sourceErrorMessage("unsupported_scheme"), Model.sourceErrorMessage("bad_server")], [Model.sourceErrorMessage("invalid"), Model.sourceErrorMessage("scheme"), Model.sourceErrorMessage("server_scheme")])
check("sourceErrorMessage unknown / ok / empty", [Model.sourceErrorMessage("weird"), Model.sourceErrorMessage("ok"), Model.sourceErrorMessage("")], ["Could not save the source (weird)", "", ""])
check("sourceReason is the same table", Model.sourceReason("too_many"), Model.sourceErrorMessage("too_many"))
check("statusReason knows the new codes", [Model.statusReason({ ok: false, error: { code: "too_long", message: "x" } }), Model.statusReason({ ok: false, error: { code: "bad_key", message: "x" } }), Model.statusReason({ ok: false, error: { code: "invalid", message: "http://u:p@h.test/x" } })], ["URL too long", "Invalid cache key", "Invalid URL"])

// ---- keys (D4) ----
check("sourceKey vectors", [Model.sourceKey("https://iptv-org.github.io/iptv/countries/us.m3u"), Model.sourceKey("http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts"), Model.sourceKey("/srv/tv/local.m3u")], ["d5977d8a", "d990c2e4", "b0eed9fb"])
check("isSourceKey", ["d5977d8a", "d5977d8a-2", "d5977d8a-999", "D5977D8A", "d5977d8", "../x", "d5977d8a/..", "d5977d8a-1000"].map(Model.isSourceKey), [true, true, true, false, false, false, false, false])
const collided = [{ key: "d5977d8a", url: "http://other.test/x" }, { key: "d5977d8a-2", url: "http://other2.test/x" }]
check("allocateSourceKey suffixes on a collision", Model.allocateSourceKey(collided, "https://iptv-org.github.io/iptv/countries/us.m3u"), "d5977d8a-3")
check("allocateSourceKey returns the existing key for a known url", Model.allocateSourceKey(collided, "http://other2.test/x"), "d5977d8a-2")
check("allocateSourceKey on an empty list is the plain hash", Model.allocateSourceKey([], "/srv/tv/local.m3u"), "b0eed9fb")
check("findSource / findSourceByUrl with a forced collision", [Model.findSource(collided, "d5977d8a-2").url, Model.findSourceByUrl(collided, "http://other.test/x").key, Model.findSource(collided, "nope"), Model.findSourceByUrl(null, "x")], ["http://other2.test/x", "d5977d8a", null, null])
check("sourceCacheDir", [Model.sourceCacheDir("/c/omarchy-iptv/", "d5977d8a"), Model.sourceCacheDir("/c", "d5977d8a-2"), Model.sourceCacheDir("/c", "../x"), Model.sourceCacheDir("", "d5977d8a"), Model.sourceCacheDir("/c", "")], ["/c/omarchy-iptv/sources/d5977d8a", "/c/sources/d5977d8a-2", "", "", ""])

// ---- labels (UX 5.6) ----
check("deriveLabel host with port, www stripped, lowercased", [Model.deriveLabel("http://www.NAS.local:9981/playlist"), Model.deriveLabel("https://tv.example.net/get.php?u=1"), Model.deriveLabel("http://192.168.1.10:9981/x"), Model.deriveLabel("http://h.test:80/x")], ["nas.local:9981", "tv.example.net", "192.168.1.10:9981", "h.test"])
check("deriveLabel file name for paths and file URLs", [Model.deriveLabel("/home/dag/tv/channels.m3u"), Model.deriveLabel("file:///srv/tv/a%20b.m3u", "file"), Model.deriveLabel("/", "file")], ["channels.m3u", "a b.m3u", "local file"])
check("deriveLabel never exceeds LIMITS.label", Model.deriveLabel("http://" + "h".repeat(100) + ".test/x").length, 64)
check("deriveLabel on junk is the junk, capped", Model.deriveLabel("weird"), "weird")
check("uniqueLabel appends 2, 3 case-insensitively", [Model.uniqueLabel("tv.example.net", ["TV.example.net"]), Model.uniqueLabel("tv.example.net", ["tv.example.net", "tv.example.net 2"]), Model.uniqueLabel("fresh", ["other"])], ["tv.example.net 2", "tv.example.net 3", "fresh"])
check("uniqueLabel accepts records and skips selfId", [Model.uniqueLabel("A", [{ id: "1", label: "a" }], "1"), Model.uniqueLabel("A", [{ key: "1", label: "a" }], "2")], ["A", "A 2"])
check("uniqueLabel keeps the suffix inside the cap", Model.uniqueLabel("x".repeat(64), ["x".repeat(64)]).length, 64)
check("defaultSourceLabel = derive + unique", Model.defaultSourceLabel("http://h.test/x", "http", ["h.test"]), "h.test 2")
check("validateLabel ok / empty ok / too long / taken", [Model.validateLabel(" NAS ", ["Other"], "").label, Model.validateLabel("", [], "").ok, Model.validateLabel("x".repeat(65), [], "").code, Model.validateLabel("provider", [{ id: "1", label: "Provider" }], "").code, Model.validateLabel("provider", [{ id: "1", label: "Provider" }], "1").ok], ["NAS", true, "label_too_long", "label_taken", true])
check("validateLabel message quotes the typed label", Model.validateLabel("Provider", ["provider"], "").message, "A source named " + Q("Provider") + " already exists")
check("labelTaken null-safe", [Model.labelTaken("", ["x"]), Model.labelTaken("x", null), Model.labelTaken("x", [null, 5, "X"])], [false, false, true])

// ---- masking (SR4 / UX 4.4) ----
check("maskUrl masks every query value except type and output", Model.maskUrl("http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts"), "http://provider.example.test/get.php?username=****&password=****&type=m3u_plus&output=ts")
check("maskUrl masks userinfo, keeps a bare flag, keeps the port", Model.maskUrl("http://u:p@h.test:8080/x?token=abc&flag"), "http://****@h.test:8080/x?token=****&flag")
check("maskUrl masks the fragment", Model.maskUrl("http://user:pw@tv.example.net:8080/get.php?username=tomasz&password=s3cret&type=m3u_plus&output=ts#x"), "http://****@tv.example.net:8080/get.php?username=****&password=****&type=m3u_plus&output=ts#****")
check("maskUrl leaves a plain URL alone (nothing to mask)", Model.maskUrl("https://iptv-org.github.io/iptv/countries/us.m3u"), "https://iptv-org.github.io/iptv/countries/us.m3u")
check("maskUrl never masks paths, file URLs or non-URLs", [Model.maskUrl("/home/dag/tv/channels.m3u?x=1"), Model.maskUrl("file:///srv/a.m3u?x=1"), Model.maskUrl("tv.example?x=1"), Model.maskUrl(""), Model.maskUrl(null)], ["/home/dag/tv/channels.m3u?x=1", "file:///srv/a.m3u?x=1", "tv.example?x=1", "", ""])
check("maskUrl fixed length whatever the secret length", Model.maskUrl("http://h.test/x?k=" + "s".repeat(500)), "http://h.test/x?k=****")
check("maskUrl keeps a bare ? and an empty value", [Model.maskUrl("http://h.test/x?"), Model.maskUrl("http://h.test/x?a=")], ["http://h.test/x?", "http://h.test/x?a=****"])
check("maskUrl clear params are case-insensitive", Model.maskUrl("http://h.test/x?TYPE=m3u&Output=ts&Pw=1"), "http://h.test/x?TYPE=m3u&Output=ts&Pw=****")

// ---- Xtream (D10, UX 1.8 / 5.4) ----
check("encodeQueryValue equals Python quote(v, safe='')", Model.encodeQueryValue("a b!*'()~-._/@:+"), "a%20b%21%2A%27%28%29~-._%2F%40%3A%2B")
check("encodeQueryValue non-ASCII is UTF-8 percent-encoded uppercase", Model.encodeQueryValue("p\u00e4\u00df"), "p%C3%A4%C3%9F")
const xt = Model.xtreamUrls("http://Provider.Example.TEST:8080/", "u", "p")
check("xtreamUrls builds get.php and xmltv.php", [xt.ok, xt.playlistUrl, xt.epgUrl, xt.host, xt.base], [true, "http://provider.example.test:8080/get.php?username=u&password=p&type=m3u_plus&output=ts", "http://provider.example.test:8080/xmltv.php?username=u&password=p", "provider.example.test", "http://provider.example.test:8080"])
check("xtreamUrls percent-encodes the credentials", Model.xtreamUrls("https://h.test/", "a b", "p&q").playlistUrl, "https://h.test/get.php?username=a%20b&password=p%26q&type=m3u_plus&output=ts")
check("xtreamUrls accepts one object (service call shape)", Model.xtreamUrls({ server: "https://h.test", username: "u", password: "p" }).epgUrl, "https://h.test/xmltv.php?username=u&password=p")
check("xtreamUrls default ports are dropped so the key is stable", Model.xtreamUrls("http://H.test:80", "u", "p").base, "http://h.test")
check("xtreamUrls server_empty / server_scheme (no guessing) / server_path (UX 8 #9, #10)", [Model.xtreamUrls("", "u", "p").code, Model.xtreamUrls("h.test:8080", "u", "p").code, Model.xtreamUrls("ftp://h.test", "u", "p").code, Model.xtreamUrls("/srv/x", "u", "p").code, Model.xtreamUrls("http://h.test/get.php?username=x", "u", "p").code, Model.xtreamUrls("http://h.test/c", "u", "p").code, Model.xtreamUrls("http://h.test/?x=1", "u", "p").code], ["server_empty", "server_scheme", "server_scheme", "server_scheme", "server_path", "server_path", "server_path"])
check("xtreamUrls invalid host / server_userinfo (SR17)", [Model.xtreamUrls("http://h .test", "u", "p").code, Model.xtreamUrls("http://u:p@h.test", "u", "p").code, Model.xtreamUrls("http://u@h.test:8080/", "u", "p").message, Model.xtreamUrls("http://", "u", "p").code], ["invalid", "server_userinfo", "Server must not contain a username or password" + SEP + "enter them below", "invalid"])
check("xtreamUrls credential codes", [Model.xtreamUrls("http://h.test", "", "p").code, Model.xtreamUrls("http://h.test", "u", "  ").code, Model.xtreamUrls("http://h.test", "u".repeat(257), "p").code, Model.xtreamUrls("http://h.test", "u", "p".repeat(257)).code, Model.xtreamUrls("http://" + "h".repeat(520), "u", "p").code], ["user_empty", "pass_empty", "user_too_long", "pass_too_long", "server_too_long"])
check("xtreamUrls failure names the field and carries the copy", Model.xtreamUrls("http://h.test", "u", "").field + "|" + Model.xtreamUrls("http://h.test", "u", "").message, "password|Enter the password")
check("xtreamUrls failure carries no URL fields", (() => { const r = Model.xtreamUrls("http://h.test/x", "u", "p"); return [r.playlistUrl, r.epgUrl, r.base, r.host] })(), ["", "", "", ""])
check("xtreamUrls strips control characters from every field", Model.xtreamUrls("http://h.test\n", "u\ru", "p\tp").playlistUrl, "http://h.test/get.php?username=uu&password=pp&type=m3u_plus&output=ts")
check("validateXtream is the UX name for the same check", [Model.validateXtream({ server: "x", username: "u", password: "p" }).code, Model.validateXtream(null).code, Model.validateXtream({ server: "http://h.test", username: "u", password: "p" }).ok], ["server_scheme", "server_empty", true])

// ---- formatting (UX 5.2) ----
const local = (y, m, d, h, mi) => Math.floor(new Date(y, m - 1, d, h, mi).getTime() / 1000)
const nowSep = local(2026, 9, 13, 21, 40)
check("pluralGroups / countsLine", [Model.pluralGroups(1), Model.pluralGroups(28), Model.pluralGroups(null), Model.countsLine(1475, 28), Model.countsLine(1, 1)], ["1 group", "28 groups", "0 groups", "1,475 channels in 28 groups", "1 channel in 1 group"])
check("formatLastUsed today / yesterday / this year / older / never", [Model.formatLastUsed(local(2026, 9, 13, 21, 30), nowSep), Model.formatLastUsed(local(2026, 9, 12, 23, 59), nowSep), Model.formatLastUsed(local(2026, 9, 3, 10, 0), nowSep), Model.formatLastUsed(local(2025, 9, 3, 10, 0), nowSep), Model.formatLastUsed(0, nowSep), Model.formatLastUsed(null, nowSep)], ["used 21:30", "used yesterday", "used 3 Sep", "used 3 Sep 2025", "never used", "never used"])
check("formatLastUsed year boundary: 31 Dec seen on 1 Jan is yesterday", Model.formatLastUsed(local(2025, 12, 31, 12, 0), local(2026, 1, 1, 8, 0)), "used yesterday")
check("formatLastUsed without nowSec uses the clock (never used stays)", Model.formatLastUsed(0), "never used")
check("formatAgo (architecture wording)", [Model.formatAgo(1000, 990), Model.formatAgo(1000, 1000 - 720), Model.formatAgo(1000 + 3 * 3600, 1000), Model.formatAgo(1000 + 2 * 86400, 1000), Model.formatAgo(5, 0)], ["just now", "12 min ago", "3 h ago", "2 d ago", ""])
check("sourcesHeaderCount", [Model.sourcesHeaderCount(0), Model.sourcesHeaderCount(1), Model.sourcesHeaderCount(3), Model.sourcesHeaderCount(null)], ["No sources", "1 source", "3 sources", "No sources"])
check("sourcesRowAccessibleName", Model.sourcesRowAccessibleName(3), "Sources, 3 saved")
check("confirmRemoveMessage", [Model.confirmRemoveMessage("NAS Tvheadend", false), Model.confirmRemoveMessage("Provider", true)], ["Remove " + Q("NAS Tvheadend") + "? Its cache is deleted too.", "Remove " + Q("Provider") + "? It is the active source; the guide returns to setup."])
check("fetchingLine", [Model.fetchingLine("tv.example.net", "url"), Model.fetchingLine("", "file")], ["Fetching from tv.example.net" + ELL, "Reading the file" + ELL])
check("probeFailureLine url / path / redacted", [Model.probeFailureLine("HTTP 403 Forbidden", "tv.example.net", "url"), Model.probeFailureLine("File not found", "", "file"), Model.probeFailureLine("could not open http://u:p@h.test/x", "h.test", "url"), Model.probeFailureLine("", "h.test", "url")], ["HTTP 403 Forbidden from tv.example.net", "File not found", "could not open h.test from h.test", "Unknown error from h.test"])
check("sourceTransient strings (UX 5.3)", [
  Model.sourceTransient("loaded", { channelCount: 1475, groupCount: 28 }),
  Model.sourceTransient("added", { host: "tv.example.net", channelCount: 1475, groupCount: 28 }),
  Model.sourceTransient("saved", {}),
  Model.sourceTransient("saved", { channelCount: 1475, groupCount: 28 }),
  Model.sourceTransient("switched", { label: "NAS Tvheadend", channelCount: 84 }),
  Model.sourceTransient("switched", { label: "NAS", channelCount: -1 }),
  Model.sourceTransient("removed", { label: "NAS Tvheadend" }),
  Model.sourceTransient("removed", { label: "Provider", wasActive: true }),
  Model.sourceTransient("nope", {})
], ["1,475 channels in 28 groups", "Added tv.example.net" + SEP + "1,475 channels in 28 groups", "Saved", "Saved" + SEP + "1,475 channels in 28 groups", "Switched to NAS Tvheadend" + SEP + "84 channels", "Switched to NAS", "Removed NAS Tvheadend", "Removed Provider" + SEP + "no active source", ""])
check("sourceTransient added names the label (a path's file name, never `local file`), host is the fallback", [
  Model.sourceTransient("added", { label: "list.m3u", host: "local file", channelCount: 20, groupCount: 9 }),
  Model.sourceTransient("added", { label: "NAS Tvheadend", host: "nas.local", channelCount: -1 }),
  Model.sourceTransient("added", { label: "", host: "tv.example.net", channelCount: 3, groupCount: 1 })
], ["Added list.m3u" + SEP + "20 channels in 9 groups", "Added NAS Tvheadend", "Added tv.example.net" + SEP + "3 channels in 1 group"])

// ---- view objects (SR1, UX 5.2 / 7.1) ----
const recProvider = { key: "d990c2e4", url: "http://tv.example.net:8080/get.php?username=u&password=p&type=m3u_plus&output=ts", epgUrl: "http://tv.example.net:8080/xmltv.php?username=u&password=p", kind: "http", label: "Provider", labelCustom: true, origin: "xtream", addedAt: 100, lastUsed: local(2026, 9, 13, 21, 30), fetchedAt: 200, channelCount: 1475, groupCount: 28 }
const recNas = { key: "11111111", url: "http://nas.local:9981/playlist", epgUrl: "http://nas.local:9981/xmltv", kind: "http", label: "NAS Tvheadend", labelCustom: true, origin: "guide", addedAt: 50, lastUsed: local(2026, 9, 12, 9, 0), fetchedAt: 210, channelCount: 84, groupCount: 6 }
const recCli = { key: "d5977d8a", url: "https://iptv-org.github.io/iptv/countries/us.m3u", epgUrl: "", kind: "http", label: "iptv-org", labelCustom: true, origin: "cli", addedAt: 300, lastUsed: 0, fetchedAt: 0, channelCount: 0, groupCount: 0 }
const recFile = { key: "b0eed9fb", url: "/srv/tv/channels.m3u", epgUrl: "", kind: "file", label: "channels.m3u", labelCustom: false, origin: "guide", addedAt: 10, lastUsed: local(2026, 9, 3, 12, 0), fetchedAt: 220, channelCount: 12, groupCount: 1 }
const state4 = { version: 2, cacheLayout: 2, favorites: [], recents: [], lastPlayed: null, sources: [recFile, recNas, recProvider, recCli] }
const viewProvider = Model.sourceView(recProvider, "d990c2e4", nowSep)
check("sourceView carries the UX names and never the URL", viewProvider, { id: "d990c2e4", label: "Provider", kind: "xtream", host: "tv.example.net:8080", hasEpg: true, channelCount: 1475, groupCount: 28, cachedAt: 200, lastUsedAt: local(2026, 9, 13, 21, 30), lastUsedText: "used 21:30", active: true, origin: "xtream", errorReason: "" })
check("sourceView never fetched: channelCount -1, file host is 'local file'", [Model.sourceView(recCli, "", nowSep).channelCount, Model.sourceView(recCli, "", nowSep).cachedAt, Model.sourceView(recFile, "", nowSep).host, Model.sourceView(recFile, "", nowSep).kind, Model.sourceView(recNas, "", nowSep).kind], [-1, 0, "local file", "file", "url"])
check("sourceView null-safe", Model.sourceView(null, "", 0).id, "")
check("sourceView attaches the session error", Model.sourceView(recCli, "", nowSep, "Connection refused").errorReason, "Connection refused")
const views4 = Model.sourceViews(state4, "d990c2e4", nowSep, { d5977d8a: "Connection refused" })
check("sourceViews: active first, then last used desc, never used last", views4.map(v => v.id), ["d990c2e4", "11111111", "b0eed9fb", "d5977d8a"])
check("sourceViews rows carry no url key and no ://", [views4.some(v => "url" in v || "epgUrl" in v), JSON.stringify(views4).indexOf("://")], [false, -1])
check("sourceViews attaches per-key errors", views4[3].errorReason, "Connection refused")
check("sourceRows is the architecture name", Model.sourceRows(state4, "", 0).length, 4)
check("sourceViews null / empty", [Model.sourceViews(null, "", 0), Model.sourceViews({ sources: [null] }, "", 0)], [[], []])
check("sourceDetail wide", [Model.sourceDetail(views4[0], false), Model.sourceDetail(views4[1], false), Model.sourceDetail(views4[2], false), Model.sourceDetail(views4[3], false)], [
  "active" + SEP + "tv.example.net:8080" + SEP + "Xtream" + SEP + "1,475 channels in 28 groups" + SEP + "EPG",
  "nas.local:9981" + SEP + "84 channels in 6 groups" + SEP + "EPG",
  "local file" + SEP + "12 channels in 1 group",
  "iptv-org.github.io" + SEP + "not loaded yet"
])
check("sourceDetail narrow moves 'used' right after 'active'", [Model.sourceDetail(views4[0], true), Model.sourceDetail(views4[3], true)], ["active" + SEP + "used 21:30" + SEP + "tv.example.net:8080" + SEP + "Xtream" + SEP + "1,475 channels in 28 groups" + SEP + "EPG", "never used" + SEP + "iptv-org.github.io" + SEP + "not loaded yet"])
check("sourceDetail never carries error text (SR26): errorReason stays on the view for the result line", [Model.sourceDetail(Model.sourceView(recCli, "", nowSep), false), views4[3].errorReason], ["iptv-org.github.io" + SEP + "not loaded yet", "Connection refused"])
check("sourceAccessibleName", [Model.sourceAccessibleName(views4[0]), Model.sourceAccessibleName(Model.sourceView(recCli, "", nowSep))], ["Provider, tv.example.net:8080, 1,475 channels in 28 groups, active, EPG, last used 21:30", "iptv-org, iptv-org.github.io, not loaded yet, never used"])

// ---- state v2 and reducers (ARCHITECTURE-SOURCES 2.1, 2.2, 3.5) ----
check("emptyState is v2", Model.emptyState(), { version: 2, cacheLayout: 0, favorites: [], recents: [], lastPlayed: null, session: null, sources: [] })
check("cloneState carries sources and cacheLayout, applies the patch, forces the version", Model.cloneState({ version: 1, cacheLayout: 2, favorites: ["a"], sources: [recFile] }, { favorites: ["b"], version: 7 }), { version: 2, cacheLayout: 2, favorites: ["b"], recents: [], lastPlayed: null, session: null, sources: [recFile] })
check("cloneState copies the arrays", (() => { const src = { sources: [recFile] }; const out = Model.cloneState(src); out.sources.push(recNas); return src.sources.length })(), 1)
check("withCacheLayout", [Model.withCacheLayout(state4, 0).cacheLayout, Model.withCacheLayout(Model.emptyState(), 2).cacheLayout, Model.withCacheLayout(Model.emptyState(), 5).cacheLayout], [0, 2, 0])
check("parseState v1 -> v2 keeps favorites and recents, sources empty, cacheLayout 0", Model.parseState('{"version":1,"favorites":["t:bbc1.uk"],"recents":[{"id":"x","name":"X","at":1}],"lastPlayed":null}'), { version: 2, cacheLayout: 0, favorites: ["t:bbc1.uk"], recents: [{ id: "x", name: "X", at: 1 }], lastPlayed: null, session: null, sources: [] })
check("parseState v2 round-trips records", Model.parseState(JSON.stringify(state4)).sources, state4.sources)
check("parseState drops invalid records, duplicate urls and keys keep the first", Model.parseState(JSON.stringify({ version: 2, sources: [recNas, { key: "bad key", url: "http://x.test/" }, { key: "22222222", url: recNas.url }, { key: "11111111", url: "http://other.test/" }, { key: "33333333", url: "" }, "junk"] })).sources.map(s => s.key), ["11111111"])
check("parseState coerces and defaults a sparse record", Model.parseState(JSON.stringify({ version: 2, sources: [{ key: "abcdef12", url: "http://h.test/x", channelCount: "7", origin: "weird", labelCustom: "yes" }] })).sources[0], { key: "abcdef12", url: "http://h.test/x", epgUrl: "", kind: "http", label: "h.test", labelCustom: false, origin: "guide", addedAt: 0, lastUsed: 0, fetchedAt: 0, channelCount: 7, groupCount: 0 })
check("parseState caps sources at 50", Model.parseState(JSON.stringify({ version: 2, sources: Array.from({ length: 60 }, (_, i) => ({ key: (10000000 + i).toString(16).padStart(8, "0"), url: "http://h" + i + ".test/" })) })).sources.length, 50)
check("parseState cacheLayout 2 read, other values 0", [Model.parseState('{"version":2,"cacheLayout":2}').cacheLayout, Model.parseState('{"version":2,"cacheLayout":"x"}').cacheLayout], [2, 0])
check("recordPlayed carries sources", Model.recordPlayed(state4, { id: "c1", name: "C" }, 10, 5).sources.length, 4)
check("withFavorites carries sources", Model.withFavorites(state4, ["c1"]).sources.length, 4)
check("removeRecent carries sources", Model.removeRecent(state4, "x").sources.length, 4)
check("trimRecents carries sources", Model.trimRecents({ ...state4, recents: [{ id: "1" }, { id: "2" }] }, 1).sources.length, 4)
check("normalizeSourceRecord rejects junk", [Model.normalizeSourceRecord(null), Model.normalizeSourceRecord({ key: "abcdef12", url: "x".repeat(2049) })], [null, null])

// ---- the session record (ARCHITECTURE-PLAYER.md 4.6, section 8, ruling PO-3) ----
// What the player was last ASKED to play, so a shell that comes back to a dead
// player knows which row to mark failed in the guide without a toast minutes
// late. Additive and nullable: STATE_VERSION stays 2, a file without the key
// reads as null, and an older build drops it. Python mirror: normalize_state.
const sessionState = Model.recordPlayed(Model.emptyState(), { tvgId: "bbc1.uk", name: "BBC One HD", url: "http://u:p@h.test/s.m3u8" }, 10, 1758000123)
check("recordPlayed writes session beside lastPlayed", [sessionState.session, sessionState.lastPlayed], [{ id: "t:bbc1.uk", name: "BBC One HD", at: 1758000123 }, { id: "t:bbc1.uk", name: "BBC One HD", at: 1758000123 }])
check("the session record never carries a URL", JSON.stringify(sessionState.session).indexOf("://"), -1)
check("session survives the service's own write-then-read (JSON.stringify -> parseState)", Model.parseState(JSON.stringify(sessionState, null, 2)).session, { id: "t:bbc1.uk", name: "BBC One HD", at: 1758000123 })
check("a state file written before the key reads as a null session", [Model.emptyState().session, Model.parseState('{"version":2,"favorites":["a"],"lastPlayed":null}').session, Model.parseState("not json").session], [null, null, null])
check("parseState coerces a sparse session, drops one without an id and one that is not an object", [
  Model.parseState('{"session":{"id":"t:x"}}').session,
  Model.parseState('{"session":{"id":"t:y","name":7,"at":"1758000123"}}').session,
  Model.parseState('{"session":{"name":"no id","at":5}}').session,
  Model.parseState('{"session":"junk"}').session
], [{ id: "t:x", name: "", at: 0 }, { id: "t:y", name: "7", at: 1758000123 }, null, null])
check("clearSession empties the key and keeps the rest", (() => { const st = Model.clearSession(Model.withFavorites(sessionState, ["t:f"])); return [st.session, st.lastPlayed, st.favorites, st.recents.length] })(), [null, { id: "t:bbc1.uk", name: "BBC One HD", at: 1758000123 }, ["t:f"], 1])
check("clearSession returns the same object when there is nothing to clear (no needless write)", (() => { const st = Model.emptyState(); return [Model.clearSession(st) === st, Model.clearSession(sessionState) === sessionState] })(), [true, false])
check("clearSession does not mutate its input", (() => { Model.clearSession(sessionState); return sessionState.session.id })(), "t:bbc1.uk")
check("a zap moves the session on, a channel with no id at all leaves both records alone", (() => {
  const zapped = Model.recordPlayed(sessionState, { tvgId: "bbc2.uk", name: "BBC Two" }, 10, 1758000200)
  const nameless = Model.recordPlayed(sessionState, null, 10, 1758000300)
  return [zapped.session.id, nameless.session, nameless.lastPlayed.id]
})(), ["t:bbc2.uk", sessionState.session, "t:bbc1.uk"])
check("stateSession normalizes on the way out and never throws", [Model.stateSession(sessionState), Model.stateSession({ session: { id: "t:z", at: "9" } }), Model.stateSession({ session: { name: "no id" } }), Model.stateSession(Model.emptyState()), Model.stateSession(null)], [{ id: "t:bbc1.uk", name: "BBC One HD", at: 1758000123 }, { id: "t:z", name: "", at: 9 }, null, null, null])
// Ruling PO-3 itself. A `player probe` that found nothing running, plus a
// session record still in the file, is the evidence that the channel died
// with no shell attached: mark it failed in the guide, silently, clear the
// record. The catch is the order of arrival - the probe fires from
// Component.onCompleted and answers in about 130 ms, state.json lands
// whenever its FileView loads - so the verdict is gated on the state being
// loaded, and an unloaded state yields `pending` and NEVER a write, because
// writing there would put the empty default over the user's file.
// This drives it exactly as Service.qml markDeadSession() does: call, store
// the pending flag, apply the marks, write only when the state changed.
const probeFoundNoPlayer = (svc) => {
  const v = Model.deadSessionVerdict(svc.userState, svc.stateLoaded, svc.failedAt, "21:30")
  svc.pending = v.pending
  if (v.mark) svc.failedAt = v.failed
  if (v.write) { svc.userState = v.state; svc.writes += 1 }
  return svc
}
const freshService = (state, loaded) => ({ userState: state, stateLoaded: loaded, failedAt: {}, pending: false, writes: 0 })
check("PO-3, state first then the probe: the row goes red, the record is cleared, one write", (() => {
  const svc = probeFoundNoPlayer(freshService(sessionState, true))
  return [svc.failedAt, svc.userState.session, svc.userState.lastPlayed.id, svc.writes, svc.pending]
})(), [{ "t:bbc1.uk": "21:30" }, null, "t:bbc1.uk", 1, false])
check("PO-3, probe first then the state: the probe defers, writes nothing, and the state handler drains it", (() => {
  const svc = probeFoundNoPlayer(freshService(Model.emptyState(), false))
  const deferred = [svc.pending, svc.failedAt, svc.writes, svc.userState.session]
  svc.userState = sessionState        // the FileView finally loads
  svc.stateLoaded = true
  if (svc.pending) probeFoundNoPlayer(svc)
  return [deferred, svc.pending, svc.failedAt, svc.userState.session, svc.writes]
})(), [[true, {}, 0, null], false, { "t:bbc1.uk": "21:30" }, null, 1])
check("PO-3: an unloaded state is handed back untouched - the empty default can never be written over the file", (() => {
  const empty = Model.emptyState()
  const v = Model.deadSessionVerdict(empty, false, {}, "21:30")
  const missing = Model.deadSessionVerdict(null, false, null, "21:30")
  return [v.state === empty, v.write, v.mark, missing.state, missing.write, missing.failed]
})(), [true, false, false, null, false, {}])
check("PO-3: a loaded state with no record marks nothing (a clean stop cleared it, PR-2)", (() => {
  const svc = probeFoundNoPlayer(freshService(Model.clearSession(sessionState), true))
  return [svc.failedAt, svc.writes, svc.pending]
})(), [{}, 0, false])
check("PO-3: marking is idempotent - the second probe of the same startup finds nothing left to clear", (() => {
  const svc = probeFoundNoPlayer(freshService(sessionState, true))
  probeFoundNoPlayer(svc)
  return [svc.writes, Object.keys(svc.failedAt).length]
})(), [1, 1])
check("PO-3: existing red rows survive, the record's clock is the one passed in", Model.deadSessionVerdict(sessionState, true, { "t:other": "09:05" }, "21:30").failed, { "t:other": "09:05", "t:bbc1.uk": "21:30" })
check("PO-3: a half-written record still marks the row it names, and nothing here carries a URL", (() => {
  const half = Model.parseState('{"version":2,"session":{"id":"t:x"}}')
  const v = Model.deadSessionVerdict(half, true, {}, "21:30")
  return [v.id, v.name, v.failed, v.state.session, JSON.stringify(v).indexOf("://")]
})(), ["t:x", "", { "t:x": "21:30" }, null, -1])
check("PO-3 does not mutate the state it was given", (() => { Model.deadSessionVerdict(sessionState, true, {}, "21:30"); return sessionState.session.id })(), "t:bbc1.uk")

// ---- the record's lifetime: PO-3's other half (M2-02-06 PR-5) ----
// deadSessionVerdict() above only ever fires on a record it FINDS, so which
// endings leave one behind is the whole of whether a reattach marks a channel
// red for an event the user has already seen. The rule is about the witness,
// not the failure: a record must not outlive the shell that saw how the play
// ended - toast, red row, "mpv not found", a clean end or the user's own stop
// alike - and survives exactly one thing, a player still running or still on
// its way. The defect this closes: a failed `player start`, a missing mpv and
// an abandoned relaunch each kept the record, so the next reattach spent the
// same failure a second time.
//
// This drives it exactly as Service.qml noteSessionOutcome() does: call, take
// the deferred-mark flag from the verdict, write only when the state changed.
const noteOutcome = (svc, outcome) => {
  const v = Model.sessionAfterOutcome(svc.userState, outcome, svc.deadSessionPending)
  svc.deadSessionPending = v.pending
  if (v.write) { svc.userState = v.state; svc.writes += 1 }
  return svc
}
// The reattach after the shell this service was is gone: a fresh process runs
// the probe, finds no player, and asks PO-3 what to do with whatever is left.
const reattachMarks = (svc) => Model.deadSessionVerdict(svc.userState, true, {}, "21:30").failed
const playingService = () => ({ userState: sessionState, deadSessionPending: false, writes: 0 })

check("the outcome vocabulary is exactly the thirteen answers Service.qml can get", Model.PLAYER_OUTCOMES.slice().sort(), ["abandoned", "attached", "ended", "failed", "foreign", "loaded", "marked", "mpvMissing", "relaunching", "respawning", "retrying", "stopped", "superseded"])
check("a player that is still there or still coming keeps the record; every ending retires it", Model.PLAYER_OUTCOMES.map(o => Model.sessionAfterOutcome(sessionState, o).terminal), [false, false, false, false, false, false, true, true, true, true, true, true, true])

// The six endings, each on its own. Before this change three of them - a
// failed start, a missing mpv, an abandoned relaunch - left the record.
for (const ending of ["stopped", "ended", "foreign", "failed", "mpvMissing", "abandoned"]) {
  check("ending '" + ending + "' retires the record, so the next reattach marks nothing", (() => {
    const svc = noteOutcome(playingService(), ending)
    return [svc.userState.session, svc.writes, reattachMarks(svc)]
  })(), [null, 1, {}])
}
// ...and the four non-endings keep it, which is what makes the mark possible
// at all: kill the shell in any of these and nothing witnessed the outcome.
for (const alive of ["superseded", "retrying", "relaunching", "attached"]) {
  check("'" + alive + "' leaves the record for a reattach to find", (() => {
    const svc = noteOutcome(playingService(), alive)
    return [svc.userState.session, svc.writes, reattachMarks(svc)]
  })(), [sessionState.session, 0, { "t:bbc1.uk": "21:30" }])
}

check("the reported defect: mpv is missing, the user gets the critical toast, and no red row waits for them next login", (() => {
  const svc = noteOutcome(playingService(), "mpvMissing")
  return [svc.userState.session, reattachMarks(svc), Object.keys(reattachMarks(svc)).length]
})(), [null, {}, 0])
check("a start that failed for good is the same event as the toast it raised, not a second one", (() => {
  const svc = noteOutcome(playingService(), "failed")
  return [svc.userState.session, reattachMarks(svc)]
})(), [null, {}])
check("a first load that failed with a live socket defers to the EOF, which then retires it", (() => {
  const svc = noteOutcome(playingService(), "attached")
  const held = [svc.userState.session, svc.writes]
  noteOutcome(svc, "ended")
  return [held, svc.userState.session, svc.writes, reattachMarks(svc)]
})(), [[sessionState.session, 0], null, 1, {}])
check("a relaunch that is queued keeps the record; the channel vanishing from the playlist ends it", (() => {
  const svc = noteOutcome(playingService(), "relaunching")
  const queued = [svc.userState.session, reattachMarks(svc)]
  noteOutcome(svc, "abandoned")
  return [queued, svc.userState.session, svc.writes, reattachMarks(svc)]
})(), [[sessionState.session, { "t:bbc1.uk": "21:30" }], null, 1, {}])
check("a backoff keeps the record, and the play that finally lands and then ends retires it", (() => {
  const svc = noteOutcome(noteOutcome(playingService(), "retrying"), "retrying")
  const backoff = [svc.userState.session, svc.writes]
  noteOutcome(svc, "ended")
  return [backoff, svc.userState.session, svc.writes]
})(), [[sessionState.session, 0], null, 1])

check("an ending is idempotent: the second one writes nothing (clearSession hands back the same object)", (() => {
  const svc = noteOutcome(noteOutcome(playingService(), "failed"), "ended")
  const v = Model.sessionAfterOutcome(svc.userState, "stopped")
  return [svc.writes, v.terminal, v.write, v.state === svc.userState]
})(), [1, true, false, true])
check("an ending with no record at all never writes", (() => {
  const svc = noteOutcome({ userState: Model.emptyState(), deadSessionPending: false, writes: 0 }, "mpvMissing")
  return [svc.writes, svc.userState.session, Model.sessionAfterOutcome(null, "ended").write]
})(), [0, null, false])
check("an outcome the rule does not name is inert - a misspelled call site loses no mark", [
  Model.sessionAfterOutcome(sessionState, "mpv_missing", false),
  Model.sessionAfterOutcome(sessionState, "", false),
  Model.sessionAfterOutcome(sessionState, "hasOwnProperty").terminal,
  Model.sessionAfterOutcome(sessionState, "toString").known
], [
  { outcome: "mpv_missing", known: false, terminal: false, consumed: false, pending: false, state: sessionState, write: false },
  { outcome: "", known: false, terminal: false, consumed: false, pending: false, state: sessionState, write: false },
  false, false
])
// The deferred half of PO-3 rides on the same verdict: the startup probe can
// find no player before state.json has landed, and owes a mark once it does
// (deadSessionVerdict `pending`). An ending settles that event - the user has
// now seen how this play finished - but a `busy` retry racing the probe must
// not, or a genuine unattended death silently loses its red row.
check("an ending drops a deferred PO-3 mark; a player still coming leaves it owed", [
  Model.sessionAfterOutcome(sessionState, "mpvMissing", true).pending,
  Model.sessionAfterOutcome(sessionState, "ended", true).pending,
  Model.sessionAfterOutcome(Model.emptyState(), "stopped", true).pending,
  Model.sessionAfterOutcome(sessionState, "retrying", true).pending,
  Model.sessionAfterOutcome(sessionState, "superseded", true).pending,
  Model.sessionAfterOutcome(sessionState, "relaunching", true).pending,
  Model.sessionAfterOutcome(sessionState, "attached", true).pending,
  Model.sessionAfterOutcome(sessionState, "mpv_missing", true).pending,
  Model.sessionAfterOutcome(sessionState, "retrying", false).pending
], [false, false, false, true, true, true, true, true, false])
check("a backoff racing the startup probe still lets the deferred mark land", (() => {
  // The probe answered before the FileView: no player, nothing to decide on.
  const svc = { userState: Model.emptyState(), deadSessionPending: true, writes: 0 }
  noteOutcome(svc, "retrying")                       // a `busy` reply lands first
  const owed = svc.deadSessionPending
  svc.userState = sessionState                       // state.json finally loads
  const v = Model.deadSessionVerdict(svc.userState, true, {}, "21:30")
  return [owed, v.mark, v.failed]
})(), [true, true, { "t:bbc1.uk": "21:30" }])
check("the verdict does not mutate its input and carries no URL", (() => {
  Model.sessionAfterOutcome(sessionState, "ended")
  const v = Model.sessionAfterOutcome(sessionState, "ended")
  return [sessionState.session.id, v.state.lastPlayed.id, v.state.recents.length, JSON.stringify(v).indexOf("://")]
})(), ["t:bbc1.uk", "t:bbc1.uk", 1, -1])
check("retiring the record leaves Recents, favorites and sources alone", (() => {
  const rich = Model.withFavorites(Model.recordPlayed(state4, { tvgId: "bbc1.uk", name: "BBC One HD" }, 10, 1758000123), ["t:f"])
  const out = Model.sessionAfterOutcome(rich, "stopped").state
  return [out.session, out.favorites, out.lastPlayed.id, out.recents.length, out.sources.length]
})(), [null, ["t:f"], "t:bbc1.uk", 1, 4])

// ---- D-PLY-3: a consumed record never comes back ----
// The rule above retires the record in MEMORY. Whether that reaches disk
// depends on saveState()'s dirsReady gate and on which of state.json's own
// loads wins the race, and when the write loses, the next load puts the
// record straight back - so the following shell start marked the same
// channel red a second time, with the same HH:MM. Found live, 2 runs in 3.
// The fix is not a condition at the load site but one more thing the same
// decision answers: `consumed` is one-way until a new play opens a record.
const markedService = () => {
  // The PO-3 mark has just been raised, exactly as markDeadSession() does it.
  const svc = { userState: sessionState, deadSessionPending: false, consumed: false, writes: 0 }
  const v = Model.sessionAfterOutcome(svc.userState, "marked", svc.deadSessionPending, svc.consumed)
  svc.deadSessionPending = v.pending; svc.consumed = v.consumed
  if (v.write) { svc.userState = v.state; svc.writes += 1 }
  return svc
}
const stateFileLoads = (svc, text) => {
  const adopted = Model.stateOnLoad(Model.parseState(text), svc.userState,
                                    { loadedBefore: true, savePending: false, maxRecents: 10 })
  svc.userState = adopted.state
  const v = Model.sessionAfterOutcome(svc.userState, "loaded", svc.deadSessionPending, svc.consumed)
  svc.deadSessionPending = v.pending; svc.consumed = v.consumed
  if (v.write) { svc.userState = v.state; svc.writes += 1 }
  return svc
}
// The bytes still on disk after a clear that has not been written yet.
const unclearedFile = JSON.stringify({ version: 2, recents: [{ id: "t:bbc1.uk", name: "BBC One HD", at: 1758000123 }], lastPlayed: { id: "t:bbc1.uk", name: "BBC One HD", at: 1758000123 }, session: { id: "t:bbc1.uk", name: "BBC One HD", at: 1758000123 } })
check("D-PLY-3: the mark retires the record and marks it consumed", (() => {
  const svc = markedService()
  return [svc.userState.session, svc.consumed, svc.writes]
})(), [null, true, 1])
check("D-PLY-3: the state file that our clear had not reached yet does NOT bring the record back", (() => {
  const svc = stateFileLoads(markedService(), unclearedFile)
  return [svc.userState.session, svc.writes, reattachMarks(svc)]
})(), [null, 2, {}])
check("D-PLY-3: it stays cleared however many times that file arrives, and stops writing once it agrees", (() => {
  const svc = stateFileLoads(stateFileLoads(markedService(), unclearedFile), unclearedFile)
  const writesAfterTwo = svc.writes
  stateFileLoads(svc, JSON.stringify({ version: 2, session: null }))
  return [svc.userState.session, writesAfterTwo, svc.writes]
})(), [null, 3, 3])
check("D-PLY-3: an ordinary load of a record this shell has NOT consumed keeps it - that is the whole of PO-3", (() => {
  const svc = { userState: Model.emptyState(), deadSessionPending: false, consumed: false, writes: 0 }
  stateFileLoads(svc, unclearedFile)
  return [(svc.userState.session || {}).id, svc.writes, reattachMarks(svc)]
})(), ["t:bbc1.uk", 0, { "t:bbc1.uk": "21:30" }])
check("D-PLY-3: every ending consumes, every non-ending leaves the record open to a later load", [
  Model.sessionAfterOutcome(sessionState, "marked").consumed,
  Model.sessionAfterOutcome(sessionState, "ended").consumed,
  Model.sessionAfterOutcome(sessionState, "stopped").consumed,
  Model.sessionAfterOutcome(sessionState, "respawning").consumed,
  Model.sessionAfterOutcome(sessionState, "relaunching").consumed,
  Model.sessionAfterOutcome(sessionState, "loaded").consumed,
  Model.sessionAfterOutcome(sessionState, "loaded", false, true).consumed
], [true, true, true, false, false, false, true])
check("D-PLY-3: consuming touches nothing but the record", (() => {
  const rich = Model.withFavorites(Model.recordPlayed(state4, { tvgId: "bbc1.uk", name: "BBC One HD" }, 10, 1758000123), ["t:f"])
  const out = Model.sessionAfterOutcome(rich, "loaded", false, true).state
  return [out.session, out.favorites, out.lastPlayed.id, out.recents.length, out.sources.length]
})(), [null, ["t:f"], "t:bbc1.uk", 1, 4])

// ---- D-PLY-4: ARCHITECTURE-PLAYER.md section 15's startup race ----
// Measured, not assumed: 14 losses in 30 trials. state.json is read
// asynchronously while a play can be issued immediately, so the text that
// arrives is the file from BEFORE the play - and applying it wholesale threw
// away the session record the play had just written, which is the only
// evidence PO-3 has that a channel died unattended.
const fileFromBefore = JSON.stringify({
  version: 2, favorites: ["t:fav"],
  recents: [{ id: "t:old", name: "Old", at: 100 }],
  lastPlayed: { id: "t:old", name: "Old", at: 100 },
  sources: [{ key: "aaaaaaaa", url: "http://h.test/a.m3u", epgUrl: "", label: "A", addedAt: 1, origin: "form" }]
})
// What the service holds when a play beats the file: the empty default plus
// exactly that play.
const playedBeforeLoad = Model.recordPlayed(Model.emptyState(), { tvgId: "bbc1.uk", name: "BBC One HD" }, 10, 1758000123)
const raced = Model.stateOnLoad(Model.parseState(fileFromBefore), playedBeforeLoad, { loadedBefore: false, savePending: false, maxRecents: 10 })
check("D-PLY-4: the record the play wrote survives the file that was read before it", [raced.state.session, raced.replayed, raced.write], [{ id: "t:bbc1.uk", name: "BBC One HD", at: 1758000123 }, true, true])
check("D-PLY-4: and the file still supplies everything only it knows", [raced.state.favorites, raced.state.sources.length, raced.state.recents.map(r => r.id)], [["t:fav"], 1, ["t:bbc1.uk", "t:old"]])
check("D-PLY-4: the lost race, end to end - a reattach now marks the channel that died unattended", Model.deadSessionVerdict(raced.state, true, {}, "21:30").failed, { "t:bbc1.uk": "21:30" })
check("D-PLY-4: with no play in flight the file is adopted untouched, same object, no write", (() => {
  const base = Model.parseState(fileFromBefore)
  const out = Model.stateOnLoad(base, Model.emptyState(), { loadedBefore: false, maxRecents: 10 })
  return [out.state === base, out.replayed, out.write, out.state.session]
})(), [true, false, false, null])
check("D-PLY-4: a later reload is an external edit and wins - this is not a licence to ignore the file", (() => {
  const out = Model.stateOnLoad(Model.parseState('{"version":2,"favorites":["t:new"]}'), playedBeforeLoad, { loadedBefore: true, savePending: false, maxRecents: 10 })
  return [out.state.favorites, out.state.session, out.replayed]
})(), [["t:new"], null, false])
check("D-PLY-4: unless a save of ours is still queued behind dirsReady, when the file on disk is again the older one", (() => {
  const out = Model.stateOnLoad(Model.parseState('{"version":2,"favorites":["t:new"]}'), playedBeforeLoad, { loadedBefore: true, savePending: true, maxRecents: 10 })
  return [out.state.favorites, (out.state.session || {}).id, out.replayed]
})(), [["t:new"], "t:bbc1.uk", true])
check("D-PLY-4: the replayed play is deduplicated in Recents and respects the cap", (() => {
  const file = JSON.stringify({ version: 2, recents: [{ id: "t:bbc1.uk", name: "Stale name", at: 1 }, { id: "t:b", name: "B", at: 2 }, { id: "t:c", name: "C", at: 3 }] })
  const out = Model.stateOnLoad(Model.parseState(file), playedBeforeLoad, { loadedBefore: false, maxRecents: 2 })
  return [out.state.recents.map(r => r.id), (out.state.recents[0] || {}).name]
})(), [["t:bbc1.uk", "t:b"], "BBC One HD"])
check("D-PLY-4: nothing here mutates its inputs and nothing carries a URL", (() => {
  const base = Model.parseState(fileFromBefore)
  const out = Model.stateOnLoad(base, playedBeforeLoad, { loadedBefore: false, maxRecents: 10 })
  return [base.session, playedBeforeLoad.favorites.length, JSON.stringify({ s: out.state.session, r: out.state.recents }).indexOf("://")]
})(), [null, 0, -1])
check("D-PLY-4: a garbage or absent file is still a base, and a half-written record is dropped rather than replayed", [
  Model.stateOnLoad(null, null, {}).state.version,
  Model.stateOnLoad(Model.parseState("not json"), { session: { name: "no id" } }, { loadedBefore: false }).state.session,
  Model.stateOnLoad(Model.parseState("{}"), { session: { id: "t:x" } }, { loadedBefore: false }).state.session
], [2, null, { id: "t:x", name: "", at: 0 }])

// The other half of D-PLY-4, and the one the harness hits hardest: a play
// issued inside the startup probe's ~130 ms window was not merely stripped
// of its record, it was DROPPED - applyProbe()'s "nothing is running"
// cleared nowPlaying, and drainPendingPlay() needs a nowPlaying. 28 of 30
// trials at a 20 ms retry never started playing at all against 396a69a.
check("D-PLY-4: a probe an intent has overtaken keeps only its sequence resync", [
  Model.probeVerdict(5, 0, 0),          // the startup probe, nothing issued since
  Model.probeVerdict(5, 0, 3),          // a play went out after it
  Model.probeVerdict(0, 2, 2),          // a fresh lock file, both sides at 2
  Model.probeVerdict(9, 4, 4).seq       // the resync is one past the record
], [{ seq: 6, stale: false }, { seq: 6, stale: true }, { seq: 2, stale: false }, 10])
check("D-PLY-4: staleness is measured BEFORE the resync, or every startup probe looks stale", (() => {
  // Reading it after moving playSeq is the mistake that silently switches
  // PO-3's mark off: the lock file always names a higher sequence than a
  // shell that has just started.
  const v = Model.probeVerdict(7, 0, 0)
  return [v.stale, v.seq, Model.probeVerdict(7, v.seq, v.seq).stale]
})(), [false, 8, false])
check("D-PLY-4: the resync never goes backwards, and junk is 0", [
  Model.probeVerdict(1, 9, 9).seq, Model.probeVerdict(null, 0, 0), Model.probeVerdict("x", "y", "z")
], [9, { seq: 1, stale: false }, { seq: 1, stale: false }])

// ---- D-PLY-1: a death inside our own respawn is not an ending ----
// The P1. `player start` and `player restart` ladder a player DOWN and spawn
// its replacement inside one helper call, so the death of the player they
// replace arrives at the socket observer while that call is still running.
// Read as an ending it cleared nowPlaying and playerWanted; the helper's
// success reply then read the cleared nowPlaying as "a stop overtook this
// start" and declined to re-arm the observer; and with wanted false the
// 250 ms retry timer was off, so the interface sat idle - for good - while
// the freshly spawned player kept playing. Two triggers, both deterministic.
const death = (over) => Model.playerDeathKind(Object.assign({ sessionInFlight: false, relaunchPending: false, nowPlaying: true, hasChannel: true, userStopped: false, stopping: false }, over))
check("D-PLY-1: the helper is mid ladder-and-respawn, so this EOF is a rung of it, not an end", death({ sessionInFlight: true }), "respawn")
check("D-PLY-1: trigger A, the health verdict's `player restart --from term`, with the relaunch also queued", death({ sessionInFlight: true, relaunchPending: true }), "respawn")
check("D-PLY-1: trigger B, `player start` finding the old player unreachable and replacing it", death({ sessionInFlight: true, relaunchPending: false }), "respawn")
check("D-PLY-1: a stop we issued outranks everything - it is why the player is dying", [death({ sessionInFlight: true, userStopped: true }), death({ sessionInFlight: true, stopping: true }), death({ relaunchPending: true, userStopped: true })], ["ended", "ended", "ended"])
check("D-PLY-1: nothing playing is always an ending, whatever is in flight", [death({ sessionInFlight: true, nowPlaying: false }), death({ relaunchPending: true, nowPlaying: false })], ["ended", "ended"])
check("D-PLY-1: the queued relaunch still works, and still needs the channel to be in the playlist", [death({ relaunchPending: true }), death({ relaunchPending: true, hasChannel: false })], ["relaunch", "ended"])
check("D-PLY-1: a plain death with nothing in flight is an ending, as it always was", [death({}), Model.playerDeathKind({}), Model.playerDeathKind(null)], ["ended", "ended", "ended"])

const follow = (over) => Model.playerSessionFollowUp(Object.assign({ attached: false, stopping: false, userStopped: false, nowPlaying: true }, over))
check("D-PLY-1: the observer is already on the new player - only the birth edge to drop", follow({ attached: true }), "attached")
check("D-PLY-1: the helper reported a live player and we do not know what it is playing: read it back out of the stash", follow({ nowPlaying: false }), "recover")
check("D-PLY-1: the pre-fix answer to exactly that case was to do nothing, which is the defect", [follow({ nowPlaying: false }) === "abandoned", follow({ nowPlaying: false }) === "recover"], [false, true])
check("D-PLY-1: a stop really did overtake this start - do not hunt a socket being torn down", [follow({ nowPlaying: false, stopping: true }), follow({ userStopped: true }), follow({ nowPlaying: false, userStopped: true })], ["abandoned", "abandoned", "abandoned"])
check("D-PLY-1: an attached observer wins over a stop, because the EOF is what confirms it", follow({ attached: true, stopping: true }), "attached")
check("D-PLY-1: the ordinary cold start keeps hunting for the socket", [follow({}), Model.playerSessionFollowUp(null)], ["hunt", "recover"])
check("D-PLY-1: every answer arms the observer except the two that must not", ["attached", "abandoned", "hunt", "recover"].map(a => a === "hunt" || a === "recover"), [false, false, true, true])

// Service.qml is the only caller, and this pins that it stays the only route:
// a word the rule does not know, or a branch that reaches past the decision
// into the state, is exactly how the defect got in.
// (`serviceSource` is read once, at the top of the M2-09 section.)
const notedOutcomes = []
serviceSource.replace(/root\.noteSessionOutcome\("([^"]*)"\)/g, (m, word) => { notedOutcomes.push(word); return m })
check("Service.qml spells every outcome in the vocabulary", [notedOutcomes.length > 0, notedOutcomes.filter(o => Model.PLAYER_OUTCOMES.indexOf(o) === -1)], [true, []])
check("Service.qml routes all seven endings, not three of them", [...new Set(notedOutcomes)].filter(o => Model.sessionAfterOutcome(sessionState, o).terminal).sort(), ["abandoned", "ended", "failed", "foreign", "marked", "mpvMissing", "stopped"])
check("Service.qml reaches the session record through the one decision and nowhere else", [
  serviceSource.indexOf("Model.clearSession("),
  serviceSource.indexOf(".session ="),
  (serviceSource.match(/function noteSessionOutcome\(/g) || []).length
], [-1, -1, 1])

// Service.qml is where these two decisions have to be spelled, and the
// source is the only place a test can see that from here (the same pattern
// the outcome vocabulary above uses).
check("D-PLY-1: handlePlayerGone routes the EOF through the decision instead of reading relaunchPending itself", [
  serviceSource.indexOf("Model.playerDeathKind(") !== -1,
  /death === "respawn"/.test(serviceSource),
  /root\.relaunchPending && current !== null && !stopped/.test(serviceSource)
], [true, true, false])
check("D-PLY-1: the respawn branch keeps the intent alive - wanted true, the observer armed, no toast", (() => {
  const branch = serviceSource.slice(serviceSource.indexOf('if (death === "respawn")'), serviceSource.indexOf('if (death === "relaunch")'))
  return [/root\.playerWanted = true/.test(branch), /root\.armPlayerSocket\(\)/.test(branch), /root\.nowPlaying = null/.test(branch), /raiseStreamFailure/.test(branch), /noteSessionOutcome\("respawning"\)/.test(branch)]
})(), [true, true, false, false, true])
check("D-PLY-4: applyProbe asks the decision instead of resyncing and then comparing", [
  /var verdict = Model\.probeVerdict\(probe\.seq, root\.probeSeq, root\.playSeq\)/.test(serviceSource),
  /if \(verdict\.stale\) \{[\s\S]{0,400}?return\n\s+\}/.test(serviceSource),
  /root\.probeSeq = root\.playSeq[\s\S]{0,200}?playerProbeArgv/.test(serviceSource),
  /root\.playSeq = Math\.max\(root\.playSeq, probe\.seq \+ 1\)/.test(serviceSource)
], [true, true, true, false])
check("D-PLY-4: a play opens a new record and drops a PO-3 mark owed on the one it replaced", [
  /root\.sessionConsumed = false/.test(serviceSource),
  /root\.deadSessionPending = false\n\s+relaunchTimer\.stop\(\)|root\.deadSessionPending = false/.test(serviceSource),
  serviceSource.indexOf("Model.stateOnLoad(") !== -1
], [true, true, true])
check("D-PLY-1: a successful start or restart re-arms the observer and cancels the relaunch it just delivered", [
  serviceSource.indexOf("Model.playerSessionFollowUp(") !== -1,
  /root\.relaunchPending = false\n[\s\S]{0,600}?relaunchTimer\.stop\(\)/.test(serviceSource),
  /follow === "recover"[\s\S]{0,120}runPlayerProbe\(\)/.test(serviceSource),
  /root\.nowPlaying === null\) \{\n\s+\/\/ A stop overtook/.test(serviceSource)
], [true, true, true, false])

// ---- CL10: "exactly ONE relaunch, never a second one at the healthy player"
//
// This property is half of the P1 this project shipped, and until now the
// only thing asserting it counted a journal line. The line the fix added
// exists ONLY in the fixed tree, so an older tree has nothing to match and
// the comparison is a pass against nothing - which is the ruling, in the
// product owner's own words. The line stays, for a human reading a journal;
// the ASSERTION moves here, onto the intent counter, which both trees
// produce and produce differently. Wave two measured the fixed tree live
// three times: `status.player.seq` delta 1, `player.lock` seq delta 1
// (docs/QA-RESULTS.md D4).
//
// It is driven through each tree's OWN Service.qml, because that is the only
// artefact of the shell a unit gate can reach: the two decision sites are
// extracted as JavaScript and executed against fakes, so the numbers come
// from the shipping source rather than from a copy of it living here
// (CLAUDE.md 12). Point IPTV_SERVICE_QML at another tree's Service.qml to
// run the same assertion against it - which is how the discrimination was
// proved, `396a69a` reading 2 where this tree reads 1.

// The brace-matched block after `anchor`, ignoring braces inside strings and
// line comments.
function qmlBlockAfter(text, anchor) {
  const at = text.indexOf(anchor)
  if (at === -1) return ""
  let i = text.indexOf("{", at + anchor.length - 1)
  if (i === -1) return ""
  const start = i + 1
  let depth = 0
  for (; i < text.length; i++) {
    const c = text[i]
    if (c === "/" && text[i + 1] === "/") { i = text.indexOf("\n", i); if (i === -1) break; continue }
    if (c === '"' || c === "'" || c === "`") {
      const quote = c
      for (i++; i < text.length; i++) {
        if (text[i] === "\\") { i++; continue }
        if (text[i] === quote) break
      }
      continue
    }
    if (c === "{") depth++
    else if (c === "}") { depth--; if (depth === 0) return text.slice(start, i) }
  }
  return ""
}

// One wedge-and-respawn. The health verdict has already spent intent 1 on
// `player restart` and the dying player's EOF has armed the queued relaunch;
// both trees do all of that identically and it is not what is under test.
// What IS under test is what happens when that restart answers ok: a tree
// that leaves the queue armed fires a SECOND restart at the player it has
// just respawned, one tick later, because the timer's `playerUp` branch
// reads a healthy new player as "still not answering".
function wedgeAndRespawn(serviceText) {
  const handler = serviceText.slice(serviceText.indexOf("function handlePlayerResult("))
  const okBranch = qmlBlockAfter(handler, "if (status.ok === true) {")
  const timerBody = qmlBlockAfter(serviceText.slice(serviceText.indexOf("id: relaunchTimer")), "onTriggered: {")
  if (okBranch === "" || timerBody === "") return { intents: "<the source did not parse>", seqDelta: "<the source did not parse>" }
  const names = ["root", "relaunchTimer", "playerProc", "playerWatchdog", "console", "Model", "status"]
  const runOk = new Function(...names, okBranch)
  const runTick = new Function(...names, timerBody)
  const issued = []
  let armed = true                                   // the old player's EOF
  const relaunchTimer = { restart() { armed = true }, stop() { armed = false } }
  const playerProc = { running: false }              // the helper has answered
  const playerWatchdog = { restart() {}, stop() {} }
  const quiet = { log() {}, warn() {}, error() {} }
  const root = {
    playSeq: 1, relaunchPending: true, relaunched: true, playRetries: 0,
    playerUp: true, playerPending: true, playerWanted: true,
    stopping: false, userStopped: false, healthFailures: 0, healthSkips: 0, lastError: "",
    nowPlaying: { id: "t:bbc1.uk", name: "BBC One HD", group: "UK", launchedFrom: "g:uk", since: 3000 },
    channelIndex: { "t:bbc1.uk": { id: "t:bbc1.uk", name: "BBC One HD", url: "http://provider.test/x.m3u8" } },
    entryOwners: {},
    socketAttached() { return false },
    armPlayerSocket() {}, runPlayerProbe() {}, drainPendingPlay() {}, rememberEntry() {},
    reapplyIntent() {}, playerFirstLoadFailed() {}, noteSessionOutcome() {}, startPlayer() {},
    issuePlayerSession(verb) { issued.push(verb); playerProc.running = true }
  }
  const reply = {
    ok: true, kind: "player.restart", spawned: true, pid: 4242, id: "t:bbc1.uk", name: "BBC One HD",
    entryId: 1, seq: 1, firstLoad: { state: "playing", reason: "" }, warnings: [], applied: true, playing: null
  }
  runOk(root, relaunchTimer, playerProc, playerWatchdog, quiet, Model, reply)
  if (armed) runTick(root, relaunchTimer, playerProc, playerWatchdog, quiet, Model, reply)
  // The verdict's own restart counts as one; `issued` holds any that follow.
  return { intents: 1 + issued.length, seqDelta: root.playSeq }
}

const relaunchTree = process.env.IPTV_SERVICE_QML || path.join(__dirname, "../Service.qml")
check("CL10: one wedge, ONE relaunch and ONE intent - a second one at the healthy player reads 2 here",
  wedgeAndRespawn(fs.readFileSync(relaunchTree, "utf8")), { intents: 1, seqDelta: 1 })
// The witness stays for a human reading a journal. It is a forward
// regression guard for trees that already carry it and it can never be
// rule-11 evidence against the tree the defect was filed on - which is
// exactly what CL10 says, and it is written down here so the next person
// does not mistake it for the assertion again.
check("CL10: the journal witness is kept, and is NOT what proves the property",
  /console\.log\("omarchy-iptv: relaunching the unresponsive player, seq /.test(serviceSource), true)

// Every branch that drops the channel is a branch the record's fate hangs on,
// so pair them by position: the very next thing after each `root.nowPlaying =
// null` is the decision, in one of its two forms - noteSessionOutcome() for an
// outcome this shell watched, markDeadSession() for the reattach that found
// the player already gone. Nothing else may come between, so deleting a
// routing call turns its slot into NOTHING and adding a terminal branch
// without one shows up as a word that belongs to the branch after it. Three
// of these eight - "mpvMissing", "failed" and "abandoned" - read as NOTHING
// before this change: those are the branches that left the record behind.
const serviceTokens = []
serviceSource.replace(/root\.nowPlaying\s*=\s*null|root\.noteSessionOutcome\("([^"]*)"\)|root\.markDeadSession\(\)/g, (m, word) => {
  serviceTokens.push(m.indexOf("nowPlaying") !== -1 ? "drop" : (word !== undefined ? word : "markDeadSession"))
  return m
})
check("every Service.qml branch that drops the channel hands the record to the decision", serviceTokens
  .map((t, i) => t === "drop" ? (serviceTokens[i + 1] === undefined || serviceTokens[i + 1] === "drop" ? "NOTHING" : serviceTokens[i + 1]) : null)
  .filter(x => x !== null),
  ["stopped", "mpvMissing", "failed", "failed", "markDeadSession", "foreign", "ended", "abandoned"])

check("every reducer carries the session through (cloneState)", [
  Model.withFavorites(sessionState, ["a"]).session,
  Model.removeRecent(sessionState, "t:bbc1.uk").session,
  Model.trimRecents({ ...sessionState, recents: [{ id: "1" }, { id: "2" }] }, 1).session,
  Model.withCacheLayout(sessionState, 2).session
], [sessionState.session, sessionState.session, sessionState.session, sessionState.session])

const addOk = Model.addSource(Model.emptyState(), { playlistUrl: " HTTP://Provider.Example.TEST:80/get.php?username=u&password=p&type=m3u_plus&output=ts ", epgUrl: "http://provider.example.test/xmltv.php?username=u&password=p", label: "", origin: "xtream" }, 1000)
check("addSource normalizes, derives the label, allocates the key", [addOk.ok, addOk.key, addOk.state.sources[0]], [true, "d990c2e4", { key: "d990c2e4", url: "http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts", epgUrl: "http://provider.example.test/xmltv.php?username=u&password=p", kind: "http", label: "provider.example.test", labelCustom: false, origin: "xtream", addedAt: 1000, lastUsed: 1000, fetchedAt: 0, channelCount: 0, groupCount: 0 }])
check("addSource does not mutate the input state", Model.emptyState().sources.length, 0)
check("addSource typed label is custom; unknown origin is guide", (() => { const r = Model.addSource(addOk.state, { playlistUrl: "/srv/tv/local.m3u", label: " NAS ", origin: "junk" }, 2000); return [r.state.sources[1].label, r.state.sources[1].labelCustom, r.state.sources[1].origin, r.state.sources[1].kind, r.key] })(), ["NAS", true, "guide", "file", "b0eed9fb"])
check("addSource codes: empty, scheme, invalid, relative_path, unsafe_path, too_long", ["", "x.test/a", "http://h .test/", "~/a", "/proc/x", "/" + "x".repeat(2100)].map(u => Model.addSource(Model.emptyState(), { playlistUrl: u }).code), ["empty", "scheme", "invalid", "relative_path", "unsafe_path", "too_long"])
check("addSource bad EPG is rejected with the EPG copy", (() => { const r = Model.addSource(Model.emptyState(), { playlistUrl: "http://h.test/x", epgUrl: "ftp://e" }); return [r.code, r.message] })(), ["scheme", "EPG: start with http://, https://, or / for a local file"])
check("addSource duplicate returns the existing key (case-changed host, default port)", (() => { const r = Model.addSource(addOk.state, { playlistUrl: "http://PROVIDER.example.test:80/get.php?username=u&password=p&type=m3u_plus&output=ts" }); return [r.code, r.key, r.message] })(), ["duplicate", "d990c2e4", "Already in Sources as " + Q("provider.example.test")])
check("addSource label_taken for a typed collision; derived labels get a suffix", (() => { const taken = Model.addSource(addOk.state, { playlistUrl: "http://other.test/", label: "Provider.Example.TEST" }); const derived = Model.addSource(addOk.state, { playlistUrl: "http://provider.example.test/other.m3u" }); return [taken.code, derived.state.sources[1].label] })(), ["label_taken", "provider.example.test 2"])
check("addSource label_too_long", Model.addSource(Model.emptyState(), { playlistUrl: "http://h.test/", label: "x".repeat(65) }).code, "label_too_long")
const full50 = { version: 2, cacheLayout: 2, favorites: [], recents: [], lastPlayed: null, sources: Array.from({ length: 50 }, (_, i) => ({ key: (10000000 + i).toString(16).padStart(8, "0"), url: "http://h" + i + ".test/", epgUrl: "", kind: "http", label: "h" + i, labelCustom: false, origin: "cli", addedAt: i, lastUsed: i, fetchedAt: 0, channelCount: 0, groupCount: 0 })) }
check("addSource too_many at the cap", Model.addSource(full50, { playlistUrl: "http://new.test/" }).code, "too_many")
check("addSource result never carries a URL on failure", JSON.stringify(Model.addSource(full50, { playlistUrl: "http://new.test/" })).indexOf("new.test"), -1)

const twoState = Model.addSource(addOk.state, { playlistUrl: "/srv/tv/local.m3u" }, 2000).state
check("updateSource label only: labelCustom, state otherwise intact", (() => { const r = Model.updateSource(twoState, "d990c2e4", { label: "Provider" }, 3000); return [r.ok, r.urlChanged, r.replacedKey, r.state.sources[0].label, r.state.sources[0].labelCustom, r.state.sources.length] })(), [true, false, "", "Provider", true, 2])
check("updateSource empty label re-derives and clears labelCustom", (() => { const r = Model.updateSource(Model.updateSource(twoState, "d990c2e4", { label: "Custom" }).state, "d990c2e4", { label: "" }); return [r.state.sources[0].label, r.state.sources[0].labelCustom] })(), ["provider.example.test", false])
check("updateSource label_taken against another record, not itself", [Model.updateSource(twoState, "d990c2e4", { label: "LOCAL.m3u" }).code, Model.updateSource(twoState, "d990c2e4", { label: "provider.example.test" }).ok], ["label_taken", true])
check("updateSource epg only", (() => { const r = Model.updateSource(twoState, "b0eed9fb", { epgUrl: " http://E.test:80/x.xml " }); return [r.ok, r.urlChanged, r.state.sources[1].epgUrl] })(), [true, false, "http://e.test/x.xml"])
check("updateSource bad epg", Model.updateSource(twoState, "b0eed9fb", { epgUrl: "~/x" }).code, "relative_path")
check("updateSource same playlist url (normalized) is not a change", Model.updateSource(twoState, "d990c2e4", { playlistUrl: "HTTP://provider.example.test:80/get.php?username=u&password=p&type=m3u_plus&output=ts" }).urlChanged, false)
const moved = Model.updateSource(twoState, "d990c2e4", { playlistUrl: "http://provider.example.test:8080/get.php?username=u&password=p&type=m3u_plus&output=ts", label: "Provider" }, 4000)
check("updateSource changed url: new record with a new key, old kept until the probe confirms", [moved.ok, moved.urlChanged, moved.key, moved.replacedKey, moved.state.sources.length, moved.state.sources[2].fetchedAt, moved.state.sources[2].label, moved.state.sources[2].addedAt, moved.state.sources[2].lastUsed, moved.state.sources[0].url === twoState.sources[0].url], [true, true, "85ac744a", "d990c2e4", 3, 0, "Provider", 1000, 4000, true])
check("updateSource changed url with a derived label re-derives it", Model.updateSource(twoState, "d990c2e4", { playlistUrl: "http://new.test/x" }).state.sources[2].label, "new.test")
check("updateSource duplicate / unknown", [Model.updateSource(twoState, "d990c2e4", { playlistUrl: "/srv/tv/local.m3u" }).code, Model.updateSource(twoState, "nope", { label: "x" }).code], ["duplicate", "unknown_source"])
check("updateSource at the cap: a playlist-URL edit never counts against MAX_SOURCES (the replacement takes the old record's place)", (() => { const r = Model.updateSource(full50, "00989680", { playlistUrl: "http://new.test/" }, 5); return [r.ok, r.code, r.urlChanged, r.replacedKey, r.state.sources.length, r.state.sources.some(s => s.url === "http://new.test/"), Model.removeSource(r.state, r.replacedKey).state.sources.length] })(), [true, "ok", true, "00989680", 51, true, 50])
check("updateSource at the cap: label / EPG edits and a duplicate stay unaffected", [Model.updateSource(full50, "00989680", { label: "Renamed" }).ok, Model.updateSource(full50, "00989680", { epgUrl: "http://e.test/x.xml" }).ok, Model.updateSource(full50, "00989680", { playlistUrl: "http://h1.test/" }).code], [true, true, "duplicate"])
check("removeSource", (() => { const r = Model.removeSource(twoState, "b0eed9fb"); return [r.removed.key, r.state.sources.length, Model.removeSource(twoState, "nope").removed, twoState.sources.length] })(), ["b0eed9fb", 1, null, 2])
check("touchSource bumps lastUsed, unknown key is a no-op", [Model.touchSource(twoState, "b0eed9fb", 9000).sources[1].lastUsed, Model.touchSource(twoState, "nope", 9000).sources[1].lastUsed], [9000, 2000])
check("withSourceStats copies the counts of an ok status", Model.withSourceStats(twoState, "d990c2e4", { ok: true, fetchedAt: 5000, channelCount: "1475", groupCount: 28 }).sources[0], { ...twoState.sources[0], fetchedAt: 5000, channelCount: 1475, groupCount: 28 })
check("withSourceStats ignores a failed status, falls back to nowSec", [Model.withSourceStats(twoState, "d990c2e4", { ok: false }).sources[0].fetchedAt, Model.withSourceStats(twoState, "d990c2e4", { ok: true, channelCount: 3 }, 777).sources[0].fetchedAt], [0, 777])
check("activeSourceKey normalizes before matching", [Model.activeSourceKey(twoState, "HTTP://PROVIDER.example.test:80/get.php?username=u&password=p&type=m3u_plus&output=ts"), Model.activeSourceKey(twoState, "file:///srv/tv/local.m3u"), Model.activeSourceKey(twoState, "http://other.test/"), Model.activeSourceKey(twoState, ""), Model.activeSourceKey(null, "x")], ["d990c2e4", "b0eed9fb", "", "", ""])

// reconcile (D3 / SR8)
check("reconcileSources: empty playlistUrl is a no-op", Model.reconcileSources(twoState, "", "", "", 1), { state: twoState, changed: false, activeKey: "", added: "", evicted: [], invalid: null })
check("reconcileSources: invalid value synthesizes the validation result, never adds", (() => { const r = Model.reconcileSources(twoState, "ftp://x", "", "", 1); return [r.changed, r.activeKey, r.invalid.code, r.state.sources.length] })(), [false, "", "scheme", 2])
check("reconcileSources: known url, same active key -> unchanged", (() => { const r = Model.reconcileSources(twoState, "http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts", twoState.sources[0].epgUrl, "d990c2e4", 5000); return [r.changed, r.activeKey, r.state.sources[0].lastUsed] })(), [false, "d990c2e4", 1000])
check("reconcileSources: known url, key changed -> lastUsed bumped only", (() => { const r = Model.reconcileSources(twoState, "/srv/tv/local.m3u", "", "d990c2e4", 5000); return [r.changed, r.activeKey, r.added, r.state.sources[1].lastUsed, r.state.sources[0].lastUsed] })(), [true, "b0eed9fb", "", 5000, 1000])
check("reconcileSources: adopts a changed valid epgUrl, ignores an invalid one", [Model.reconcileSources(twoState, "/srv/tv/local.m3u", "http://e.test/x.xml", "b0eed9fb", 5000).state.sources[1].epgUrl, Model.reconcileSources(twoState, "/srv/tv/local.m3u", "ftp://e", "b0eed9fb", 5000).changed], ["http://e.test/x.xml", false])
check("reconcileSources: unknown url is added with origin cli and a derived label", (() => { const r = Model.reconcileSources(twoState, "https://iptv-org.github.io/iptv/countries/us.m3u", "", "d990c2e4", 6000); const s = r.state.sources[2]; return [r.changed, r.activeKey, r.added, s.origin, s.label, s.lastUsed, s.fetchedAt, s.labelCustom] })(), [true, "d5977d8a", "d5977d8a", "cli", "iptv-org.github.io", 6000, 0, false])
check("reconcileSources: first v2 run (no history, legacy layout) tags the record migrated", [Model.reconcileSources(Model.emptyState(), "https://iptv-org.github.io/iptv/countries/us.m3u", "", "", 1).state.sources[0].origin, Model.reconcileSources(Model.withCacheLayout(Model.emptyState(), 2), "https://iptv-org.github.io/iptv/countries/us.m3u", "", "", 1).state.sources[0].origin, Model.reconcileSources(Model.emptyState(), "http://x.test/", "", "", 1, "cli").state.sources[0].origin], ["migrated", "cli", "cli"])
check("reconcileSources: derived label is made unique", Model.reconcileSources(twoState, "http://provider.example.test/second.m3u", "", "", 1).state.sources[2].label, "provider.example.test 2")
check("reconcileSources: at the cap the least recently used non-active record is evicted", (() => { const r = Model.reconcileSources(full50, "http://new.test/", "", "00989680", 999); return [r.state.sources.length, r.evicted, r.state.sources.some(s => s.key === "00989680"), r.state.sources.some(s => s.url === "http://new.test/")] })(), [50, ["00989680"], false, true])
check("reconcileSources: eviction never drops the new active record", Model.reconcileSources(full50, "http://new.test/", "", "", 0).state.sources.some(s => s.url === "http://new.test/"), true)
check("reconcileSources does not mutate the input", twoState.sources.length, 2)
// SR11: the settings path is the CLI path. `omarchy bar set ... playlistUrl ~/list.m3u`
// reconciles into the history and becomes active; the forms keep refusing `~`.
const tildeRec = Model.reconcileSources(twoState, "~/list.m3u", "~/epg.xml", "d990c2e4", 7000)
check("reconcileSources: a CLI `~` path is accepted verbatim (kind file, label from the file name, origin cli), never settingsInvalid", (() => { const s = tildeRec.state.sources[2]; return [tildeRec.invalid, tildeRec.changed, tildeRec.added !== "", tildeRec.activeKey === tildeRec.added, s.url, s.epgUrl, s.kind, s.label, s.origin, s.fetchedAt] })(), [null, true, true, true, "~/list.m3u", "~/epg.xml", "file", "list.m3u", "cli", 0])
check("activeSourceKey resolves the CLI `~` record; a second reconcile of the same value is a no-op", [Model.activeSourceKey(tildeRec.state, "~/list.m3u"), Model.activeSourceKey(tildeRec.state, " ~/list.m3u "), Model.reconcileSources(tildeRec.state, "~/list.m3u", "~/epg.xml", tildeRec.activeKey, 8000).changed, Model.sourceView(tildeRec.state.sources[2], tildeRec.activeKey, 8000, "").host], [tildeRec.added, tildeRec.added, false, "local file"])
check("the forms still refuse `~` (SR11): addSource, updateSource, validateUrlForm", [Model.addSource(tildeRec.state, { playlistUrl: "~/other.m3u" }).code, Model.updateSource(tildeRec.state, "d990c2e4", { playlistUrl: "~/other.m3u" }).code, Model.validateUrlForm({ label: "", playlist: "~/list.m3u", epg: "" }, [], "").error.code, Model.activeSourceKey(tildeRec.state, "./list.m3u")], ["relative_path", "relative_path", "relative_path", ""])
check("reconcileSources: a `~` path that is a form-only refusal elsewhere still fails the CLI rules it shares (relative ./, unsafe /proc)", [Model.reconcileSources(twoState, "./list.m3u", "", "", 1).invalid.code, Model.reconcileSources(twoState, "/proc/x", "", "", 1).invalid.code], ["relative_path", "unsafe_path"])

check("sourceForEdit is the only URL carrier: masked and raw forms", Model.sourceForEdit(twoState, "d990c2e4"), { id: "d990c2e4", key: "d990c2e4", label: "provider.example.test", labelCustom: false, kind: "xtream", host: "provider.example.test", origin: "xtream", playlistUrl: "http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts", epgUrl: "http://provider.example.test/xmltv.php?username=u&password=p", playlistMasked: "http://provider.example.test/get.php?username=****&password=****&type=m3u_plus&output=ts", epgMasked: "http://provider.example.test/xmltv.php?username=****&password=****" })
check("sourceForEdit unknown", [Model.sourceForEdit(twoState, "nope"), Model.sourceForEdit(null, "x")], [null, null])
check("sourcesSummary carries no URL", (() => { const s = Model.sourcesSummary(twoState, "d990c2e4"); return [JSON.stringify(s).indexOf("://"), s[0], s.length] })(), [-1, { id: "d990c2e4", key: "d990c2e4", label: "provider.example.test", host: "provider.example.test", active: true, channelCount: -1, lastUsed: 1000 }, 2])
check("entryWith keeps foreign keys, applies the patch, forces id", Model.entryWith({ id: "io.github.rmcdavid.iptv", refreshMinutes: 30, mpvArgs: "--x", playlistUrl: "old" }, { playlistUrl: "new", epgUrl: "" }), { id: "io.github.rmcdavid.iptv", refreshMinutes: 30, mpvArgs: "--x", playlistUrl: "new", epgUrl: "" })
check("entryWith null-safe", Model.entryWith(null, { playlistUrl: "x" }), { playlistUrl: "x" })
check("cacheStale", [Model.cacheStale(null, 360, 1000), Model.cacheStale({ ok: false, fetchedAt: 900 }, 360, 1000), Model.cacheStale({ ok: true }, 360, 1000), Model.cacheStale({ ok: true, fetchedAt: 1000 }, 15, 1000 + 15 * 60), Model.cacheStale({ ok: true, fetchedAt: 1000 }, 15, 1000 + 15 * 60 - 1), Model.cacheStale({ ok: true, fetchedAt: 1000 }, 5, 1000 + 14 * 60)], [true, true, true, true, false, false])

// ---- guide state machine: forms and Sources (UX-SOURCES 1.9, 2.3, 7.3) ----
check("guideState gains returnMode, form, sourceCursor", Model.guideState("all"), { mode: "search", query: "", scopeId: "all", restoreScopeId: "", cursorIndex: 0, returnMode: "", form: null, sourceCursor: 0 })
check("withMode accepts the new modes and falls back to search", ["sources", "sourceEdit", "sourceXtream", "confirmRemove", "junk"].map(m => Model.withMode(Model.guideState("all"), m).mode), ["sources", "sourceEdit", "sourceXtream", "confirmRemove", "search"])
check("toggleMode is a no-op outside search / list", Model.toggleMode(Model.withMode(Model.guideState("all"), "sources")).mode, "sources")
const fr = Model.openFirstRun(Model.guideState("all"))
check("openFirstRun: sourceEdit, url form, origin firstRun, focus Playlist", [fr.mode, fr.form.kind, fr.form.origin, fr.form.sourceId, fr.form.focus, fr.form.values, fr.form.probing, fr.form.error, fr.form.parent], ["sourceEdit", "url", "firstRun", "", "playlist", { label: "", playlist: "", epg: "" }, false, null, null])
check("formFields per form", [Model.formFields(fr.form), Model.formFields({ kind: "url", origin: "sources" }), Model.formFields({ kind: "xtream" })], [["playlist", "epg"], ["label", "playlist", "epg"], ["label", "server", "username", "password"]])
check("formFocusOrder first run (with and without saved sources)", [Model.formFocusOrder(fr.form, { savedSources: 3 }), Model.formFocusOrder(fr.form, {})], [["playlist", "epg", "savedSources", "xtream", "load"], ["playlist", "epg", "xtream", "load"]])
check("formFocusOrder add / edit / xtream", [Model.formFocusOrder(Model.openAddForm(Model.guideState("all")).form), Model.formFocusOrder(Model.openEditForm(Model.guideState("all"), "k1", { label: "P" }).form), Model.formFocusOrder(Model.openXtreamForm(Model.guideState("all"), "sources").form)], [["label", "playlist", "epg", "xtream", "save", "cancel"], ["label", "playlist", "epg", "save", "cancel"], ["label", "server", "username", "password", "save", "cancel"]])
check("formLimit per field", ["label", "playlist", "epg", "server", "username", "password", "x"].map(Model.formLimit), [64, 2048, 2048, 512, 256, 256, 2048])
check("openAddForm focuses Playlist, openEditForm focuses Label with the values and original", (() => { const a = Model.openAddForm(Model.guideState("all")); const e = Model.openEditForm(Model.guideState("all"), "k1", { label: "P", playlist: "http://h.test/x?t=1", epg: "" }); return [a.form.focus, a.form.sourceId, e.form.focus, e.form.sourceId, e.form.values.playlist, e.form.original.playlist, e.form.revealed] })(), ["playlist", "", "label", "k1", "http://h.test/x?t=1", "http://h.test/x?t=1", { playlist: false, epg: false }])
check("edit form opens masked", Model.fieldMasked(Model.openEditForm(Model.guideState("all"), "k1", { playlist: "http://h.test/x?t=1" }).form, "playlist"), true)
check("openXtreamForm focuses Server, origin follows the argument", (() => { const x = Model.openXtreamForm(Model.withMode(Model.guideState("all"), "sources"), "sources"); return [x.mode, x.form.kind, x.form.origin, x.form.focus, x.form.parent, x.form.values] })(), ["sourceXtream", "xtream", "sources", "server", null, { label: "", server: "", username: "", password: "" }])
const typed = Model.withFormValue(fr, "playlist", "http://h.test/x?token=1", { typed: true })
check("withFormValue typed: value set, field revealed while typing (never masked mid-typing)", [typed.form.values.playlist, typed.form.revealed.playlist, Model.fieldMaskable(typed.form, "playlist"), Model.fieldMasked(typed.form, "playlist")], ["http://h.test/x?token=1", true, false === Model.fieldMasked(typed.form, "playlist") ? true : true, false])
const pasted = Model.withFormValue(fr, "playlist", "http://h.test/x?token=1")
check("withFormValue paste: masked immediately", [Model.fieldMasked(pasted.form, "playlist"), pasted.form.revealed.playlist], [true, false])
check("withFormValue caps at the field capacity (cap + slack) and ignores unknown fields", [Model.withFormValue(fr, "playlist", "x".repeat(3000)).form.values.playlist.length, Model.withFormValue(fr, "label", "x").form.values.label, Model.withFormValue(fr, "nope", "x").form.values], [Model.formCapacity("playlist"), "", { label: "", playlist: "", epg: "" }])
check("withFormValue clears an error on that field only", (() => { const e = Model.withFormError(pasted, { code: "invalid", field: "playlist", message: "m" }); return [Model.withFormValue(e, "playlist", "y").form.error, Model.withFormValue(e, "epg", "y").form.error.code] })(), [null, "invalid"])
check("fieldMaskable / fieldRevealed on a plain value", [Model.fieldMaskable(Model.withFormValue(fr, "playlist", "http://h.test/x").form, "playlist"), Model.fieldRevealed(fr.form, "playlist"), Model.fieldMasked(null, "playlist")], [false, false, false])
check("toggleReveal: reveal, hide, no-op when nothing to mask", [Model.toggleReveal(pasted, "playlist").form.revealed.playlist, Model.toggleReveal(Model.toggleReveal(pasted, "playlist"), "playlist").form.revealed.playlist, Model.toggleReveal(Model.withFormValue(fr, "playlist", "http://h.test/x"), "playlist").form.revealed.playlist, Model.toggleReveal(fr, "label").form.revealed], [true, false, false, { playlist: false, epg: false }])
check("withFormReveal explicit", Model.withFormReveal(pasted, "playlist", true).form.revealed.playlist, true)
const revealed = Model.toggleReveal(pasted, "playlist")
check("withFormFocus re-masks the field being left", (() => { const n = Model.withFormFocus(revealed, "epg"); return [n.form.focus, n.form.revealed.playlist] })(), ["epg", false])
check("withFormFocus same field keeps the reveal", Model.withFormFocus(revealed, "playlist").form.revealed.playlist, true)
check("moveFormFocus wraps both ways and re-masks", (() => { const a = Model.moveFormFocus(revealed, 1, { savedSources: 0 }); const b = Model.moveFormFocus(a, -1, {}); const w = Model.moveFormFocus(Model.withFormFocus(fr, "load"), 1, {}); const wb = Model.moveFormFocus(fr, -1, {}); return [a.form.focus, a.form.revealed.playlist, b.form.focus, w.form.focus, wb.form.focus] })(), ["epg", false, "playlist", "playlist", "load"])
check("moveFormFocus from an unknown focus lands on the first / last element", [Model.moveFormFocus(Model.withFormFocus(fr, "zzz"), 1, {}).form.focus, Model.moveFormFocus(Model.withFormFocus(fr, "zzz"), -1, {}).form.focus], ["playlist", "load"])
check("withFormError sets the line, thaws, and focuses the field", (() => { const e = Model.withFormError(Model.withFormProbing(Model.withFormFocus(pasted, "epg"), true), { code: "invalid", field: "playlist", message: "Invalid URL" }); return [e.form.error, e.form.probing, e.form.focus] })(), [{ code: "invalid", field: "playlist", message: "Invalid URL" }, false, "playlist"])
check("withFormError with a non-field keeps the focus; null clears", [Model.withFormError(pasted, { code: "probe", field: "", message: "x" }).form.focus, Model.withFormError(Model.withFormError(pasted, { code: "x", field: "playlist", message: "m" }), null).form.error], ["playlist", null])
check("withFormProbing freezes, clears the error, re-masks, records host / kind", (() => { const p = Model.withFormProbing(Model.withFormError(revealed, { code: "x", field: "playlist", message: "m" }), true, { host: "h.test", kind: "url" }); return [p.form.probing, p.form.error, p.form.revealed.playlist, p.form.probeHost, p.form.probeKind, Model.withFormProbing(p, false).form.probing] })(), [true, null, false, "h.test", "url", false])
check("formHasText / formSubmitValues trims every field", [Model.formHasText(fr.form), Model.formHasText(pasted.form), Model.formSubmitValues(Model.withFormValue(Model.openAddForm(Model.guideState("all")), "label", " NAS ", { typed: true }).form)], [false, true, { label: "NAS", playlist: "", epg: "" }])
check("copyForm deep-copies values, revealed, error and parent", (() => { const f = { kind: "xtream", origin: "firstRun", values: { label: "L", server: "S", username: "U", password: "P" }, parent: { kind: "url", origin: "firstRun", values: { playlist: "x" } } }; const c = Model.copyForm(f); c.values.server = "changed"; c.parent.values.playlist = "changed"; return [f.values.server, f.parent.values.playlist, c.kind, c.parent.kind, c.parent.parent, c.revealed] })(), ["S", "x", "xtream", "url", null, { playlist: false, epg: false }])

// Esc rules (UX 2.3)
check("onEscape first run: focused field with text clears it", (() => { const r = Model.onEscape(pasted); return [r.close, r.cancelProbe, r.state.form.values.playlist, r.state.mode] })(), [false, false, "", "sourceEdit"])
check("onEscape first run: focused field empty, another has text -> focus moves there, nothing closes", (() => { const r = Model.onEscape(Model.withFormFocus(pasted, "epg")); return [r.close, r.state.form.focus, r.state.form.values.playlist] })(), [false, "playlist", "http://h.test/x?token=1"])
check("onEscape first run: focus on a button with text elsewhere -> focus moves", Model.onEscape(Model.withFormFocus(pasted, "load")).state.form.focus, "playlist")
check("onEscape first run: every field empty -> close the guide", (() => { const r = Model.onEscape(fr); return [r.close, r.state.mode] })(), [true, "sourceEdit"])
check("onEscape while fetching cancels the probe and thaws, values kept", (() => { const r = Model.onEscape(Model.withFormProbing(pasted, true, { host: "h.test" })); return [r.close, r.cancelProbe, r.state.form.probing, r.state.form.values.playlist, r.state.mode] })(), [false, true, false, "http://h.test/x?token=1", "sourceEdit"])
const addForm = Model.withFormValue(Model.openAddForm(Model.openSources(Model.withMode(Model.guideState("all"), "list"), [])), "playlist", "http://h.test/x", { typed: true })
check("onEscape form from Sources: one press cancels to Sources, nothing kept", (() => { const r = Model.onEscape(addForm); return [r.close, r.state.mode, r.state.form, r.state.returnMode] })(), [false, "sources", null, "list"])
check("onEscape Xtream form from Sources cancels to Sources", Model.onEscape(Model.openXtreamForm(Model.openSources(Model.guideState("all"), []), "sources")).state.mode, "sources")
const xFromFirst = Model.openXtreamForm(pasted)
check("Xtream from the first-run form keeps the URL form as parent with its values", [xFromFirst.mode, xFromFirst.form.origin, xFromFirst.form.parent.kind, xFromFirst.form.parent.values.playlist, xFromFirst.form.focus], ["sourceXtream", "firstRun", "url", "http://h.test/x?token=1", "server"])
check("onEscape Xtream[firstRun] with a typed server clears it first", Model.onEscape(Model.withFormValue(xFromFirst, "server", "http://s", { typed: true })).state.form.values.server, "")
check("onEscape Xtream[firstRun], all empty -> back to the first-run form, values intact", (() => { const r = Model.onEscape(xFromFirst); return [r.close, r.state.mode, r.state.form.kind, r.state.form.values.playlist, r.state.form.parent] })(), [false, "sourceEdit", "url", "http://h.test/x?token=1", null])
check("Xtream from the add form returns to the add form on Esc (values kept)", (() => { const x = Model.openXtreamForm(addForm); const r = Model.onEscape(x); return [x.form.origin, x.form.parent.values.playlist, r.state.mode, r.state.form.values.playlist, r.state.form.sourceId] })(), ["sources", "http://h.test/x", "sourceEdit", "http://h.test/x", ""])
check("onEscape in Sources returns to returnMode with the view untouched", (() => { const g = Model.withCursor(Model.withQuery(Model.withMode(Model.guideState("g:UK"), "list"), "bbc"), 4); const s = Model.openSources(g, []); const r = Model.onEscape(s); return [s.mode, s.returnMode, r.state.mode, r.state.query, r.state.scopeId, r.state.cursorIndex, r.state.returnMode] })(), ["sources", "list", "list", "bbc", "g:UK", 4, ""])
check("onEscape in confirmRemove returns to Sources", Model.onEscape(Model.withMode(Model.guideState("all"), "confirmRemove")).state.mode, "sources")
check("onEscape guide modes unchanged", [Model.onEscape(Model.withQuery(Model.guideState("all"), "x")).state.query, Model.onEscape(Model.guideState("all")).close], ["", true])
check("onEscape on a form mode without a form recovers to search", Model.onEscape(Model.withMode(Model.guideState("all"), "sourceEdit")).state.mode, "search")

// closeForm outcomes
check("closeForm saved: first run -> search, Sources -> sources, form dropped", [Model.closeForm(pasted, "saved").state.mode, Model.closeForm(pasted, "saved").state.form, Model.closeForm(addForm, "saved").state.mode, Model.closeForm(Model.openXtreamForm(addForm), "saved").state.mode, Model.closeForm(Model.openXtreamForm(addForm), "saved").state.form], ["search", null, "sources", "sources", null])
check("closeForm cancel on first run asks to close; without a form recovers", [Model.closeForm(fr, "cancel").close, Model.closeForm(Model.guideState("all"), "cancel").state.mode], [true, "search"])

// Sources list transitions
check("sourcesRowCount / sourcesRowKind", [Model.sourcesRowCount(3), Model.sourcesRowCount(0), Model.sourcesRowKind(0, 3), Model.sourcesRowKind(2, 3), Model.sourcesRowKind(3, 3), Model.sourcesRowKind(4, 3), Model.sourcesRowKind(5, 3), Model.sourcesRowKind(0, 0), Model.sourcesRowKind(1, 0), Model.sourcesRowKind(-1, 3)], [5, 2, "source", "source", "add", "xtream", "", "add", "xtream", ""])
check("sourcesInitialCursor: active row, else 0", [Model.sourcesInitialCursor(views4), Model.sourcesInitialCursor([{ active: false }, { active: true }]), Model.sourcesInitialCursor([]), Model.sourcesInitialCursor(null)], [0, 1, 0, 0])
check("cursorAfterRemove clamps to the sources left", [Model.cursorAfterRemove(2, 2), Model.cursorAfterRemove(0, 2), Model.cursorAfterRemove(1, 0), Model.cursorAfterRemove(-3, 2)], [1, 0, 0, 0])
check("openSources from list / search / first run remembers returnMode", [Model.openSources(Model.withMode(Model.guideState("all"), "list"), views4).returnMode, Model.openSources(Model.guideState("all"), views4).returnMode, Model.openSources(fr, views4).returnMode, Model.openSources(xFromFirst, views4).returnMode], ["list", "search", "sourceEdit", "sourceEdit"])
check("openSources puts the cursor on the active source and is idempotent", [Model.openSources(Model.guideState("all"), views4).sourceCursor, Model.openSources(Model.guideState("all"), Model.sourceViews(state4, "d5977d8a", nowSep)).sourceCursor, Model.openSources(Model.openSources(Model.guideState("all"), views4), []).mode], [0, 0, "sources"])
check("closeSources returns to the first-run form with its values", (() => { const s = Model.openSources(pasted, views4); const b = Model.closeSources(s); return [b.mode, b.form.values.playlist, b.returnMode] })(), ["sourceEdit", "http://h.test/x?token=1", ""])
check("closeSources with a lost form reopens first run; unknown returnMode is search", [Model.closeSources({ mode: "sources", returnMode: "sourceEdit" }).form.origin, Model.closeSources({ mode: "sources", returnMode: "junk" }).mode], ["firstRun", "search"])
// UX 1.7 / QA SRC-H07: the active source was removed while Sources stayed
// open (other sources remain); Esc / `o` must land in the first-run form
// (with the `Saved sources (n)` link), not in the M1 empty state.
check("closeSources unconfigured: from list / search the return is the first-run form with focus in Playlist", (() => {
  const fromList = Model.closeSources(Model.openSources(Model.withMode(Model.guideState("g:UK"), "list"), views4), { configured: false })
  const fromSearch = Model.closeSources(Model.openSources(Model.guideState("all"), views4), { configured: false })
  return [fromList.mode, fromList.form.origin, fromList.form.focus, fromList.returnMode, fromList.scopeId, fromSearch.mode, fromSearch.form.origin]
})(), ["sourceEdit", "firstRun", "playlist", "", "g:UK", "sourceEdit", "firstRun"])
check("closeSources configured / no opts keep the shipped return; unconfigured with a first-run form keeps its values", [Model.closeSources(Model.openSources(Model.withMode(Model.guideState("all"), "list"), views4), { configured: true }).mode, Model.closeSources(Model.openSources(Model.withMode(Model.guideState("all"), "list"), views4), {}).mode, Model.closeSources(Model.openSources(pasted, views4), { configured: false }).form.values.playlist], ["list", "list", "http://h.test/x?token=1"])
check("onEscape in Sources after the active source was removed: the remove -> Esc path ends in the first-run form", (() => {
  const s = Model.withSourceCursor(Model.openSources(Model.withMode(Model.guideState("all"), "list"), views4), 0)
  const afterRm = Model.afterRemove(Model.startRemove(s, 4), 3)
  const esc = Model.onEscape(afterRm, { configured: false })
  return [afterRm.mode, esc.close, esc.cancelProbe, esc.state.mode, esc.state.form.origin, Model.onEscape(afterRm, { configured: true }).state.mode, Model.onEscape(afterRm).state.mode]
})(), ["sources", false, false, "sourceEdit", "firstRun", "list", "list"])
check("withSourceCursor", Model.withSourceCursor(Model.guideState("all"), 3).sourceCursor, 3)
const inSources = Model.withSourceCursor(Model.openSources(Model.guideState("all"), views4), 1)
check("startRemove only from a source row", [Model.startRemove(inSources, 4).mode, Model.startRemove(Model.withSourceCursor(inSources, 4), 4).mode, Model.startRemove(Model.guideState("all"), 4).mode], ["confirmRemove", "sources", "search"])
check("afterRemove: sources remain -> Sources with the cursor clamped; none -> first-run form", (() => { const a = Model.afterRemove(Model.withSourceCursor(Model.startRemove(inSources, 4), 3), 3); const b = Model.afterRemove(Model.startRemove(inSources, 4), 0); return [a.mode, a.sourceCursor, b.mode, b.form.origin, b.form.focus] })(), ["sources", 2, "sourceEdit", "firstRun", "playlist"])
check("afterSwitch is a fresh search state", Model.afterSwitch("favorites"), Model.guideState("favorites"))
check("openForm from Sources keeps returnMode so Esc after save / cancel still lands in the origin mode", [Model.openAddForm(Model.openSources(Model.withMode(Model.guideState("all"), "list"), [])).returnMode, Model.closeForm(Model.openAddForm(Model.openSources(Model.withMode(Model.guideState("all"), "list"), [])), "saved").state.returnMode], ["list", "list"])

// validateUrlForm (synchronous validation, first failing field in form order)
const existingViews = [{ id: "k1", label: "Provider", url: "http://h.test/x" }, { id: "k2", label: "NAS" }]
check("validateUrlForm ok returns normalized urls, label and view kind", Model.validateUrlForm({ label: " New ", playlist: " HTTP://H2.test:80/y ", epg: "" }, existingViews, ""), { ok: true, error: null, label: "New", playlistUrl: "http://h2.test/y", epgUrl: "", kind: "url", host: "h2.test" })
check("validateUrlForm file kind", Model.validateUrlForm({ label: "", playlist: "/srv/x.m3u", epg: "" }, [], "").kind, "file")
check("validateUrlForm order: label, playlist, epg", [Model.validateUrlForm({ label: "provider", playlist: "", epg: "" }, existingViews, "").error.code, Model.validateUrlForm({ label: "", playlist: "", epg: "ftp://x" }, existingViews, "").error.field, Model.validateUrlForm({ label: "", playlist: "http://h.test/", epg: "ftp://x" }, existingViews, "").error.message], ["label_taken", "playlist", "EPG: start with http://, https://, or / for a local file"])
check("validateUrlForm duplicate against the view list, not against itself", [Model.validateUrlForm({ label: "", playlist: "http://H.test/x", epg: "" }, existingViews, "").error, Model.validateUrlForm({ label: "Provider", playlist: "http://h.test/x", epg: "" }, existingViews, "k1").ok], [{ code: "duplicate", field: "playlist", message: "Already in Sources as " + Q("Provider") }, true])
check("validateUrlForm null-safe", Model.validateUrlForm(null, null, null).error.code, "empty")

// ---- footer (UX-SOURCES 5.3) ----
check("footerStatus prefixes the active label with 2+ sources only", [Model.footerStatus({ configured: true, count: 84, lastUpdated: "09:12", activeLabel: "NAS Tvheadend", sourceCount: 2 }), Model.footerStatus({ configured: true, count: 84, lastUpdated: "09:12", activeLabel: "NAS", sourceCount: 1 }), Model.footerStatus({ configured: true, count: 84, lastUpdated: "09:12", stale: true, activeLabel: "NAS", sourceCount: 3 })], ["NAS Tvheadend" + SEP + "84 channels" + SEP + "updated 09:12", "84 channels" + SEP + "updated 09:12", "NAS" + SEP + "84 channels" + SEP + "cached 09:12" + SEP + "offline"])
check("footerStatus transient and playing beat the prefix", [Model.footerStatus({ count: 5, transient: "Switched to NAS", activeLabel: "NAS", sourceCount: 2 }), Model.footerStatus({ count: 5, playingName: "Arte", activeLabel: "NAS", sourceCount: 2 })], ["Switched to NAS", Model.GLYPHS.play + " Arte" + SEP + "s stop"])
check("footerHints sources: source row / action row", [Model.footerHints({ mode: "sources", cursorKind: "source" }), Model.footerHints({ mode: "sources", cursorKind: "add" }), Model.footerHints({ mode: "sources", cursorKind: "xtream" }).length], [[["j/k", "move"], ["Enter", "switch"], ["a", "add"], ["c", "Xtream"], ["e", "edit"], ["x", "remove"], ["Esc", "back"]], [["j/k", "move"], ["Enter", "open"], ["Esc", "back"]], 3])
check("footerHints confirmRemove", Model.footerHints({ mode: "confirmRemove" }), [["Left/Right", "choose"], ["Enter", "confirm"], ["Esc", "cancel"]])
check("footerHints error empty state adds o sources when sources exist", [Model.footerHints({ empty: "error", sourcesExist: true }), Model.footerHints({ empty: "error", sourcesExist: false }), Model.footerHints({ empty: "loading", sourcesExist: true })], [[["r", "retry"], ["o", "sources"], ["Esc", "close"]], [["r", "retry"], ["Esc", "close"]], [["Esc", "close"]]])
check("footerHints form: plain / masked / revealed / button / xtream / fetching", [
  Model.footerHints({ mode: "sourceEdit", form: addForm.form }),
  Model.footerHints({ mode: "sourceEdit", form: Model.withFormValue(addForm, "playlist", "http://h.test/x?t=1").form }),
  Model.footerHints({ mode: "sourceEdit", form: Model.toggleReveal(Model.withFormValue(addForm, "playlist", "http://h.test/x?t=1"), "playlist").form }),
  Model.footerHints({ mode: "sourceEdit", form: Model.withFormFocus(addForm, "save").form }),
  Model.footerHints({ mode: "sourceXtream", form: Model.openXtreamForm(addForm).form }),
  Model.footerHints({ mode: "sourceEdit", form: Model.withFormProbing(addForm, true).form })
], [
  [["Enter", "save"], ["Tab", "next field"], ["Ctrl+V", "paste"], ["Esc", "cancel"]],
  [["Enter", "save"], ["Tab", "next field"], ["Ctrl+R", "reveal"], ["Ctrl+V", "replace"], ["Esc", "cancel"]],
  [["Enter", "save"], ["Tab", "next field"], ["Ctrl+R", "hide"], ["Esc", "cancel"]],
  [["Enter", "activate"], ["Tab", "next field"], ["Esc", "cancel"]],
  [["Enter", "save"], ["Tab", "next field"], ["Esc", "cancel"]],
  [["Esc", "cancel"]]
])
check("footerHints first run: Enter load, Esc close / clear / back", [Model.footerHints({ mode: "sourceEdit", form: fr.form }), Model.footerHints({ mode: "sourceEdit", form: pasted.form })[4], Model.footerHints({ mode: "sourceXtream", form: xFromFirst.form })[0], Model.footerHints({ mode: "sourceXtream", form: Model.openXtreamForm(fr).form })[2]], [[["Enter", "load"], ["Tab", "next field"], ["Ctrl+V", "paste"], ["Esc", "close"]], ["Esc", "clear"], ["Enter", "save"], ["Esc", "back"]])
check("footerHints form mode without a form is the fetching-free minimum", Model.footerHints({ mode: "sourceEdit", form: null }), [["Enter", "activate"], ["Tab", "next field"], ["Esc", "cancel"]])
check("footerHints list mode ends with o sources", Model.footerHints({ mode: "list" }).slice(-1), [["o", "sources"]])

// ---- M2-01 fix round (docs/STATUS.md D-SRC-01..10) ----
// Code points spelled out so the file stays ASCII and no editor touches them.
const LSEP = String.fromCharCode(0x2028)
const PSEP = String.fromCharCode(0x2029)
const NUL = String.fromCharCode(0)
const NEL = String.fromCharCode(0x85)
check("D-SRC-06: a line separator inside an http URL is `invalid`, never `scheme` (both fields)", [Model.validateSourceUrl("http://h.test/a" + LSEP + "b").code, Model.validateSourceUrl("http://h.test/a" + PSEP + "b", { kind: "epg" }).code, Model.validateSourceUrl("http://h.test/a" + PSEP + "b", { kind: "epg" }).message.indexOf("EPG: invalid URL")], ["invalid", "invalid", 0])
check("D-SRC-06: the error-state hint drops `r` when the configured value cannot be retried", [Model.footerHints({ empty: "error", sourcesExist: true, retry: false }), Model.footerHints({ empty: "error", sourcesExist: false, retry: false }), Model.footerHints({ empty: "error", sourcesExist: true, retry: true })], [[["o", "sources"], ["Esc", "close"]], [["Esc", "close"]], [["r", "retry"], ["o", "sources"], ["Esc", "close"]]])
check("D-SRC-08: an Xtream server with a fragment is server_path (xtream-expect E05), credentials still win", [Model.xtreamUrls("http://h.test/#frag", "u", "p").code, Model.xtreamUrls("http://h.test#frag", "u", "p").code, Model.xtreamUrls("http://h.test/?x=1#f", "u", "p").code, Model.xtreamUrls("http://u:p@h.test/#frag", "u", "p").code, Model.xtreamUrls("http://h.test/", "u", "p").ok], ["server_path", "server_path", "server_path", "server_userinfo", true])
check("D-SRC-08: a refused fragment carries no URL fields", (() => { const r = Model.xtreamUrls("http://h.test/#frag", "u", "p"); return [r.playlistUrl, r.epgUrl, r.base, r.host, r.field] })(), ["", "", "", "", "server"])
check("D-SRC-09: hasControlChars (search, not a stateful global test)", [Model.hasControlChars("http://h.test/a" + NUL + "b"), Model.hasControlChars("http://h.test/a" + NUL + "b"), Model.hasControlChars("http://h.test/ab"), Model.hasControlChars("a" + NEL + "b"), Model.hasControlChars("")], [true, true, false, true, false])
check("D-SRC-09: parseState drops a record whose url carries a control character, keeps the rest", Model.parseState(JSON.stringify({ version: 2, sources: [{ key: "deadbeef", url: "http://127.0.0.1:9/c" + NUL + "d.m3u" }, { key: "deadbee1", url: "/srv/tv/a" + String.fromCharCode(9) + "b.m3u" }, recNas] })).sources.map(s => s.key), ["11111111"])
check("D-SRC-09: a control character in epgUrl clears that field only", Model.parseState(JSON.stringify({ version: 2, sources: [{ key: "deadbee2", url: "http://h.test/ok.m3u", epgUrl: "http://e.test/" + NUL + "x.xml" }] })).sources.map(s => [s.key, s.url, s.epgUrl]), [["deadbee2", "http://h.test/ok.m3u", ""]])
check("D-SRC-09: normalizeSourceRecord returns null for a control character in url", Model.normalizeSourceRecord({ key: "deadbeef", url: "http://h.test/" + String.fromCharCode(13) + "x" }), null)
check("D-SRC-05: openFirstRun clears the query (header reads the placeholder again)", (() => { const st = Model.withQuery(Model.guideState("all"), "Harness Live"); const fr = Model.openFirstRun(st); return [fr.query, fr.mode, fr.form.origin, fr.cursorIndex] })(), ["", "sourceEdit", "firstRun", 0])
check("D-SRC-05: afterRemove of the last source and closeSources to an unconfigured guide both land with an empty query", (() => { const q = Model.withQuery(Model.guideState("all"), "Harness Live"); const src = Model.openSources(q, []); return [Model.afterRemove(src, 0).query, Model.closeSources(src, { configured: false }).query, Model.closeSources(src, { configured: true }).query] })(), ["", "", "Harness Live"])
check("D-SRC-10: adoptEpg false keeps a known record's own epgUrl (the settings' one belongs to the previous source)", (() => { const r = Model.reconcileSources(twoState, "/srv/tv/local.m3u", "http://prev.test/xmltv.php?username=u&password=p", "d990c2e4", 5000, "", { adoptEpg: false }); return [r.changed, r.activeKey, r.state.sources[1].epgUrl, r.state.sources[1].lastUsed] })(), [true, "b0eed9fb", "", 5000])
check("D-SRC-10: adoptEpg false starts a new CLI record without the carried-over epgUrl", (() => { const r = Model.reconcileSources(twoState, "https://iptv-org.github.io/iptv/countries/us.m3u", "http://prev.test/xmltv.php?username=u&password=p", "d990c2e4", 6000, "", { adoptEpg: false }); const s = r.state.sources[2]; return [r.added, s.epgUrl, s.origin, s.url] })(), ["d5977d8a", "", "cli", "https://iptv-org.github.io/iptv/countries/us.m3u"])
check("D-SRC-02: the default (and an explicit adoptEpg true) adopts a changed epgUrl into the known active record", [Model.reconcileSources(twoState, "/srv/tv/local.m3u", "http://e.test/x.xml", "b0eed9fb", 5000).state.sources[1].epgUrl, Model.reconcileSources(twoState, "/srv/tv/local.m3u", "http://e.test/x.xml", "b0eed9fb", 5000, "", { adoptEpg: true }).state.sources[1].epgUrl, Model.reconcileSources(twoState, "/srv/tv/local.m3u", "http://e.test/x.xml", "b0eed9fb", 5000, "", {}).changed], ["http://e.test/x.xml", "http://e.test/x.xml", true])
check("D-SRC-02: adopting an empty epgUrl clears the record's (omarchy bar set epgUrl '')", Model.reconcileSources(state4, recNas.url, "", "11111111", 5000).state.sources[1].epgUrl, "")
check("D-SRC-01: statusFetchedAt prefers fetchedAt, then generatedAt, else 0", [Model.statusFetchedAt({ fetchedAt: 1789244100, generatedAt: 5 }), Model.statusFetchedAt({ generatedAt: 7 }), Model.statusFetchedAt({ fetchedAt: "x" }), Model.statusFetchedAt(null)], [1789244100, 7, 0, 0])
check("D-SRC-01: sourceStatsDiffer is true for a never-fetched record and a loaded status, false once adopted", (() => { const status = { ok: true, kind: "playlist", fetchedAt: 1789244100, channelCount: 8, groupCount: 3 }; const rec = { key: "584a58e5", url: "http://127.0.0.1:8765/qa-src-a.m3u", fetchedAt: 0, channelCount: 0, groupCount: 0 }; const st = Model.withSourceStats({ version: 2, sources: [rec] }, "584a58e5", status, 9); return [Model.sourceStatsDiffer(rec, status), Model.sourceStatsDiffer(st.sources[0], status), st.sources[0].fetchedAt, st.sources[0].channelCount, st.sources[0].groupCount] })(), [true, false, 1789244100, 8, 3])
check("D-SRC-01: sourceStatsDiffer ignores failed statuses and missing records; a status without a timestamp only fills an empty record", [Model.sourceStatsDiffer(recNas, { ok: false, error: { code: "network" } }), Model.sourceStatsDiffer(null, { ok: true }), Model.sourceStatsDiffer(recNas, { ok: true, channelCount: 84, groupCount: 6 }), Model.sourceStatsDiffer({ key: "k", fetchedAt: 0 }, { ok: true, channelCount: 0, groupCount: 0 }), Model.sourceStatsDiffer(recNas, { ok: true, fetchedAt: 210, channelCount: 85, groupCount: 6 })], [false, false, false, true, true])

// ---- M1.2 cosmetics: D-LIVE-19 (docs/STATUS.md) ----
// The guide body is one surface at a time and Model.guideSurface is the whole
// decision (Guide.qml binds emptyKind, hasChannels, showColumn and the footer
// count to it). The repro: `omarchy bar set io.github.rmcdavid.iptv
// playlistUrl ""` with a list loaded flipped the body to `No playlist
// configured` while the service still held 10 channels, so the title, prose
// and command box were painted over 10 rows and an 11-entry group column.
const loadedBody = { serviceReady: true, configured: true, channelCount: 10, status: "ready", rowCount: 10, query: "", scopeId: "all", narrow: false, sources: 3 }
const clearedBody = { serviceReady: true, configured: false, channelCount: 10, status: "ready", rowCount: 10, query: "", scopeId: "all", narrow: false, sources: 3 }
check("D-LIVE-19: a configured guide with channels renders the list, the column and the counts", (() => { const s = Model.guideSurface(loadedBody); return [s.empty, s.hasChannels, s.showList, s.showColumn, s.channelCount, s.setup, s.savedSources] })(), ["", true, true, true, 10, false, 0])
check("D-LIVE-19: clearing playlistUrl takes the rows, the group column and the counts with it", (() => { const s = Model.guideSurface(clearedBody); return [s.empty, s.hasChannels, s.showList, s.showColumn, s.channelCount, s.setup] })(), ["unconfigured", false, false, false, 0, true])
check("D-LIVE-19: the setup surface offers the `Saved sources (n)` path (the record outlives the setting)", [Model.guideSurface(clearedBody).savedSources, Model.guideSurface(Object.assign({}, clearedBody, { sources: 0 })).savedSources, Model.guideSurface(loadedBody).savedSources], [3, 0, 0])
check("D-LIVE-19: no counts behind the setup surface, counts as shipped once configured", [Model.footerStatus({ configured: false, count: Model.guideSurface(clearedBody).channelCount, lastUpdated: "15:13" }), Model.footerStatus({ configured: true, count: Model.guideSurface(loadedBody).channelCount, lastUpdated: "15:13" })], ["", "10 channels" + SEP + "updated 15:13"])
check("D-LIVE-19: clearing the setting keeps the source record and leaves no active key (Sources still lists it)", (() => { const first = Model.reconcileSources(Model.withCacheLayout(Model.emptyState(), 2), "http://h.test/a.m3u", "", "", 1); const after = Model.reconcileSources(first.state, "", "", first.added, 2); return [first.state.sources.length, after.state.sources.length, after.activeKey, after.invalid, after.changed, Model.activeSourceKey(after.state, "")] })(), [1, 1, "", null, false, ""])
check("D-LIVE-19: every other empty kind is unchanged", [Model.guideSurface({ serviceReady: false }).empty, Model.guideSurface({ serviceReady: true, configured: true, channelCount: 0, status: "loading" }).empty, Model.guideSurface({ serviceReady: true, configured: true, channelCount: 0, status: "error" }).empty, Model.guideSurface({ serviceReady: true, configured: true, channelCount: 7, rowCount: 0, query: "sky", scopeId: "all" }).empty, Model.guideSurface({ serviceReady: true, configured: true, channelCount: 7, rowCount: 0, query: "", scopeId: "favorites" }).empty, Model.guideSurface({ serviceReady: true, configured: true, channelCount: 7, rowCount: 0, query: "", scopeId: "g:UK" }).empty], ["service", "loading", "error", "noMatches", "noFavorites", "emptyScope"])
check("D-LIVE-19: a narrow card still hides only the column (UX 2.2), and a service-less guide nothing but the message", [Model.guideSurface({ serviceReady: true, configured: true, channelCount: 7, rowCount: 7, narrow: true }).showList, Model.guideSurface({ serviceReady: true, configured: true, channelCount: 7, rowCount: 7, narrow: true }).showColumn, Model.guideSurface({ serviceReady: false, configured: true, channelCount: 7, rowCount: 7 }).showList], [true, false, false])
check("D-LIVE-19: garbage counts never become a body", [Model.guideSurface({ serviceReady: true, configured: true, channelCount: -5, status: "ready" }).empty, Model.guideSurface({ serviceReady: true, configured: true, channelCount: "10", status: "ready", rowCount: "10" }).empty, Model.guideSurface(null).empty, Model.guideSurface({}).empty], ["loading", "", "unconfigured", "unconfigured"])

// ---- M1.2 cosmetics: EPG helper warnings (docs/STATUS.md next steps 3) ----
// The EPG helper writes the same `warnings[]` shape into epg-status.json as
// the playlist helper does into playlist-status.json (bin/omarchy-iptv
// fetch_window); the guide renders them with their own wording and the same
// lifetime as the playlist line shipped for D-LIVE-18.
const epgStatusText = '{"ok": true, "kind": "epg", "sourceHost": "e.test", "warnings": ["no EPG channel id matches a playlist tvg-id", "12 programmes for channels not in the playlist dropped", "see http://u:p@e.test/xmltv.php?x=1"]}'
const epgWarn = Model.statusWarnings(Model.parseHelperStatus(epgStatusText, "epg"))
const epgWarnLine = Model.footerWarning([], epgWarn)
check("EPG warnings: statusWarnings redacts URLs and keeps the helper's order", epgWarn, ["no EPG channel id matches a playlist tvg-id", "12 programmes for channels not in the playlist dropped", "see e.test"])
check("EPG warnings: a failed EPG run contributes none (the window in use is still the last good run's)", [Model.statusWarnings({ ok: false, kind: "epg", warnings: ["x"] }), Model.statusWarnings(Model.parseHelperStatus('{"ok": false, "kind": "epg", "error": {"code": "network", "message": "could not reach e.test"}}', "epg"))], [[], []])
check("EPG warnings: `Guide data warning:` wording, with the same `(+N more)` tail as the playlist line", [Model.warningLine(["a", "b", "c"], "epg"), Model.warningLine(["only"], "epg"), Model.warningLine([], "epg"), Model.warningLine(["  ", "kept"], "epg")], ["Guide data warning: a (+2 more)", "Guide data warning: only", "", "Guide data warning: kept"])
check("EPG warnings: warningLine still defaults to the playlist wording (D-LIVE-18 callers)", [Model.warningLine(["a", "b"]), Model.warningLine(["a", "b"], "playlist"), Model.warningLine(["a"], "nonsense"), Model.WARNING_PREFIX.epg], ["Playlist warning: a (+1 more)", "Playlist warning: a (+1 more)", "Playlist warning: a", "Guide data warning: "])
check("EPG warnings: footerWarning puts the playlist first and falls back to the EPG", [Model.footerWarning(["p"], ["e"]), Model.footerWarning([], ["e"]), Model.footerWarning(["p"], []), Model.footerWarning([], []), Model.footerWarning(null, null)], ["Playlist warning: p", "Guide data warning: e", "Playlist warning: p", "", ""])
check("EPG warnings: the footer precedence is untouched - transient, bounded search, playing, refreshing and `Guide data loading` all win", [Model.footerStatus({ configured: true, count: 8, transient: "Refreshed" + SEP + "8 channels", warning: epgWarnLine }), Model.footerStatus({ configured: true, count: 8, truncated: true, resultTotal: 1240, cap: 200, warning: epgWarnLine }), Model.footerStatus({ configured: true, count: 8, playingName: "Arte", warning: epgWarnLine }), Model.footerStatus({ configured: true, count: 8, refreshing: true, warning: epgWarnLine }), Model.footerStatus({ configured: true, count: 8, epgPending: true, warning: epgWarnLine })], ["Refreshed" + SEP + "8 channels", "First 200 of 1,240" + SEP + "keep typing", Model.GLYPHS.play + " Arte" + SEP + "s stop", "Refreshing" + Model.ELLIPSIS, "Guide data loading" + Model.ELLIPSIS])
check("EPG warnings: the line replaces the counts, and the empty states keep the slot blank (D-LIVE-09)", [Model.footerStatus({ configured: true, count: 8, lastUpdated: "01:53", warning: epgWarnLine }), Model.footerStatus({ configured: false, count: 0, warning: epgWarnLine }), Model.footerStatus({ configured: true, count: 0, warning: epgWarnLine })], [epgWarnLine, "", ""])
check("EPG warnings: a playlist warning still outranks an EPG one in the same footer slot", Model.footerStatus({ configured: true, count: 8, lastUpdated: "01:53", warning: Model.footerWarning(["truncated to 50,000 channels"], epgWarn) }), "Playlist warning: truncated to 50,000 channels")

// ---- D-LIVE-20 / D-LIVE-21: a plugin's own settings write, applied locally ----
// The host hands a plugin `barConfig` from a `shellConfig` change handler
// (shell.qml:66) that runs before the `barConfig` binding it reads
// (shell.qml:109), so what a plugin sees is one shell.json write behind: a
// plugin's own write, being the last one, never comes back at all. The
// plugin lays its own successful write over the host's value until the host
// reports something else, so its UI is right at once and the echo, when it
// does arrive, changes nothing.
const hostA = Model.settingsFrom({ id: "x", playlistUrl: "http://h.test/a.m3u", epgUrl: "" })
const hostB = Model.settingsFrom({ id: "x", playlistUrl: "http://h.test/b.m3u", epgUrl: "http://h.test/b.xml" })
const writeB = Model.ownWriteFor(hostA, "http://h.test/b.m3u", "http://h.test/b.xml")
check("own write: recorded against the host value it was made on", writeB, { base: { playlistUrl: "http://h.test/a.m3u", epgUrl: "" }, value: { playlistUrl: "http://h.test/b.m3u", epgUrl: "http://h.test/b.xml" } })
check("own write: in force while the host still reports the base", [Model.ownWriteInForce(hostA, writeB), Model.settingsWithOwnWrite(hostA, writeB).playlistUrl, Model.settingsWithOwnWrite(hostA, writeB).epgUrl], [true, "http://h.test/b.m3u", "http://h.test/b.xml"])
check("own write: every other setting still comes from the host", [Model.settingsWithOwnWrite(Model.settingsFrom({ id: "x", playlistUrl: "http://h.test/a.m3u", refreshMinutes: 45, mpvArgs: "--mute" }), writeB).refreshMinutes, Model.settingsWithOwnWrite(Model.settingsFrom({ id: "x", playlistUrl: "http://h.test/a.m3u", refreshMinutes: 45, mpvArgs: "--mute" }), writeB).mpvArgs], [45, "--mute"])
check("own write: the host echoing our own value back lapses it, and the result is unchanged (idempotent)", [Model.ownWriteInForce(hostB, writeB), Model.settingsWithOwnWrite(hostB, writeB).playlistUrl, Model.settingsWithOwnWrite(hostB, writeB).epgUrl], [false, "http://h.test/b.m3u", "http://h.test/b.xml"])
check("own write: a foreign change (omarchy bar set) lapses it and wins", (() => { const hostC = Model.settingsFrom({ id: "x", playlistUrl: "http://h.test/c.m3u", epgUrl: "" }); return [Model.ownWriteInForce(hostC, writeB), Model.settingsWithOwnWrite(hostC, writeB).playlistUrl] })(), [false, "http://h.test/c.m3u"])
check("own write: clearing the active source is an ordinary write (D-LIVE-21)", (() => { const cleared = Model.ownWriteFor(hostB, "", ""); return [Model.settingsWithOwnWrite(hostB, cleared).playlistUrl, Model.settingsWithOwnWrite(hostB, cleared).epgUrl, Model.ownWriteInForce(hostB, cleared)] })(), ["", "", true])
check("own write: no record, or a malformed one, leaves the host untouched", [Model.settingsWithOwnWrite(hostA, null).playlistUrl, Model.settingsWithOwnWrite(hostA, {}).playlistUrl, Model.settingsWithOwnWrite(hostA, { base: null, value: { playlistUrl: "x" } }).playlistUrl, Model.ownWriteInForce(hostA, undefined)], ["http://h.test/a.m3u", "http://h.test/a.m3u", "http://h.test/a.m3u", false])
check("own write: reconcile treats the echo of our own value as no change at all", (() => { const st = Model.reconcileSources(Model.withCacheLayout(Model.emptyState(), 2), "http://h.test/b.m3u", "", "", 10); const again = Model.reconcileSources(st.state, "http://h.test/b.m3u", "", st.activeKey, 20); return [again.changed, again.activeKey === st.activeKey, again.added] })(), [false, true, ""])

// A `false` return from updateEntryInline is only a failure when the entry
// cannot be rewritten at all; with a writable entry it is the host's
// `!dirty` branch (shell.qml:1114), i.e. the value is already stored.
const layoutOf = (entry) => ({ layout: { left: [], center: [], right: [{ id: "omarchy.clock" }, entry] } })
check("persist: an object entry with our id is writable", Model.barEntryWritable(layoutOf({ id: "io.github.rmcdavid.iptv", playlistUrl: "http://h.test/a.m3u" }), "io.github.rmcdavid.iptv"), true)
check("persist: a bare-string entry is NOT writable (updateEntryInline cannot rewrite it)", [Model.barEntryWritable(layoutOf("io.github.rmcdavid.iptv"), "io.github.rmcdavid.iptv"), Model.findBarEntry(layoutOf("io.github.rmcdavid.iptv"), "io.github.rmcdavid.iptv")], [false, { id: "io.github.rmcdavid.iptv" }])
check("persist: an absent entry, an absent layout and rubbish are not writable", [Model.barEntryWritable(layoutOf({ id: "vm.netspeed" }), "io.github.rmcdavid.iptv"), Model.barEntryWritable({}, "io.github.rmcdavid.iptv"), Model.barEntryWritable(null, "io.github.rmcdavid.iptv"), Model.barEntryWritable({ layout: { right: "nope" } }, "io.github.rmcdavid.iptv")], [false, false, false, false])
check("persist: the entry may sit in any section", [Model.barEntryWritable({ layout: { left: [{ id: "io.github.rmcdavid.iptv" }], center: [], right: [] } }, "io.github.rmcdavid.iptv"), Model.barEntryWritable({ layout: { left: [], center: [{ id: "io.github.rmcdavid.iptv" }], right: [] } }, "io.github.rmcdavid.iptv")], [true, true])

// ---------------------------------------------------------------- channel
// numbers and numeric zap (M2-03, rulings CN1-CN14 in section 13 of
// docs/M2-03-CHANNEL-NUMBERS.md). Lane A owns every decision below as a pure
// function, so these cases exercise the shipping path rather than a copy of
// it (CLAUDE.md 12).

// The shared vectors, one file (CLAUDE.md: a rule written twice gets one
// fixture). tests/Model.spec.qml imports the same file as a QML script
// library, so both engines run these vectors and neither owns a copy.
const chnoCases = require("./fixtures/chno-cases.js")

// A fixture that silently lost its cases would make every loop below pass by
// running zero times.
check("CN1.2: the shared fixture carries both verdicts", [chnoCases.length >= 30, chnoCases.some(c => c.ok === true), chnoCases.some(c => c.ok === false)], [true, true, true])

for (const c of chnoCases) {
  const got = Model.parseChno(c.input)
  const want = c.ok
    ? { ok: true, key: c.key, label: c.label, sort: c.sort }
    : { ok: false, key: "", label: "", sort: -1 }
  check("CN1.2: parseChno(" + JSON.stringify(c.input) + ") " + c.why,
    { ok: got.ok, key: got.key, label: got.label, sort: got.sort }, want)
}

check("CN1.2: parseChno never throws on a non-string", [Model.parseChno(null).ok, Model.parseChno(undefined).ok, Model.parseChno(12).key, Model.parseChno({}).ok, Model.parseChno([]).ok, Model.parseChno(true).ok], [false, false, "12", false, false, false])
check("CN1.2: every failure returns the same shape", Model.parseChno("HD"), { ok: false, key: "", label: "", sort: -1, major: -1, minor: -1 })
check("CN1.2: major and minor are reported separately", [Model.parseChno("7.1").major, Model.parseChno("7.1").minor, Model.parseChno("7").minor], [7, 1, -1])

// CN11: the product owner's amendment. A playlist whose numbers live under an
// alias must not silently look unnumbered.
check("CN11: the alias attributes are read, tvg-chno first", [Model.chnoRawOf({ chno: "1", "tvg-channel-number": "2" }), Model.chnoRawOf({ "tvg-channel-number": "2" }), Model.chnoRawOf({ "channel-number": "3" }), Model.chnoRawOf({ tvgChno: "4" }), Model.chnoRawOf({}), Model.chnoRawOf(null)], ["1", "2", "3", "4", "", ""])
check("CN11: an empty alias falls through to the next one", Model.chnoRawOf({ chno: "", "channel-number": "9" }), "9")

const chan = (id, chno) => {
  const row = { id: id, name: "Ch " + id, group: "G", url: "http://h.test/" + id, searchKey: "ch " + id + " g" }
  if (chno !== null) row.chno = chno
  return row
}
// 7, 7.1, 7.2, 8, 10, a duplicate pair on 12, 130, 139, one junk value and
// one channel with no chno key at all -- deliberately NOT in number order.
const planRaw = [chan("a", "10"), chan("b", "7"), chan("c", "7.2"), chan("d", "7.1"), chan("e", "8"),
  chan("f", "139"), chan("g", "130"), chan("h", "12"), chan("i", "12"), chan("j", "HD"), chan("k", null)]
const plan = Model.prepareChannels(planRaw)
const planIdx = Model.buildChnoIndex(plan)

check("CN1.3: prepareChannels writes the three derived fields", [plan[1].chnoKey, plan[1].chnoLabel, plan[1].chnoSort], ["7", "7", 7000])
check("CN1.3: a hyphen separator is canonicalized on the row", (() => { const r = Model.prepareChannels([chan("x", "8-1")])[0]; return [r.chnoKey, r.chnoLabel, r.chnoSort] })(), ["8.1", "8.1", 8001])
check("CN6: a non-numeric chno renders as nothing, and the raw value survives", [plan[9].chnoKey, plan[9].chnoLabel, plan[9].chnoSort, plan[9].chno], ["", "", -1, "HD"])
check("CN1.3: a row with no chno key at all", [plan[10].chnoKey, plan[10].chnoLabel, plan[10].chnoSort, plan[10].chno], ["", "", -1, undefined])
check("CN1.3: the shipped prepareChannels fields are unchanged", [plan[0].id, plan[0].name, plan[0].group, plan[0].primaryGroup, plan[0].searchKey, plan[0].nameKey], ["a", "Ch a", "G", "G", "ch a g", "ch a"])
check("CN1.3: prepareChannels does not mutate its input rows", [planRaw[1].chnoKey, planRaw[1].chnoSort, planRaw[1].chno], [undefined, undefined, "7"])

check("CN1.4: byKey holds playlist indices in ascending order", [planIdx.byKey["7"], planIdx.byKey["12"], planIdx.byKey["130"]], [[1], [7, 8], [6]])
check("CN1.4: order is (chnoSort, playlist index), subchannels between their major and the next", planIdx.order, [1, 3, 2, 4, 0, 7, 8, 6, 5])
check("CN1.4: labels are parallel to order", planIdx.labels, ["7", "7.1", "7.2", "8", "10", "12", "12", "130", "139"])
check("CN1.4: counts", [planIdx.count, planIdx.duplicates, planIdx.maxLabelLen, planIdx.hasNumbers], [9, 2, 3, true])
check("CN1.4: empty, null and rubbish all return the same tolerable shape", [Model.buildChnoIndex([]), Model.buildChnoIndex(null), Model.buildChnoIndex(undefined), Model.buildChnoIndex(42)].map(i => [i.count, i.duplicates, i.maxLabelLen, i.hasNumbers, i.order.length, i.labels.length]), [[0, 0, 0, false, 0, 0], [0, 0, 0, false, 0, 0], [0, 0, 0, false, 0, 0], [0, 0, 0, false, 0, 0]])
check("CN1.4: hasNumbers is false when every value is junk", (() => { const i = Model.buildChnoIndex(Model.prepareChannels([chan("x", "HD"), chan("y", "N/A"), chan("z", null)])); return [i.hasNumbers, i.count, i.maxLabelLen] })(), [false, 0, 0])
check("CN1.4: a dense 1..20 plan indexes in playlist order", (() => { const rows = []; for (let i = 1; i <= 20; i++) rows.push(chan("d" + i, String(i))); const i2 = Model.buildChnoIndex(Model.prepareChannels(rows)); return [i2.count, i2.duplicates, i2.maxLabelLen, i2.order.slice(0, 4), i2.labels.slice(0, 4)] })(), [20, 0, 2, [0, 1, 2, 3], ["1", "2", "3", "4"]])
check("CN1.4: the index works on rows that never went through prepareChannels", (() => { const i3 = Model.buildChnoIndex([{ chno: "007" }, { chno: "3" }]); return [i3.labels, i3.order, i3.byKey["7"]] })(), [["3", "7"], [1, 0], [0]])
check("CN1.4: a hand-edited cache row cannot reach Object.prototype through byKey", (() => { const i4 = Model.buildChnoIndex([{ chnoKey: "constructor", chnoSort: 5, chnoLabel: "constructor" }, { chno: "4" }]); return [i4.count, i4.labels] })(), [2, ["constructor", "4"]])

check("CN2.3: an exact key resolves", (() => { const r = Model.resolveChno(planIdx, "7", -1); return [r.kind, r.channelIndex, r.label, r.matches, r.ordinal] })(), ["exact", 1, "7", 1, 1])
check("CN7/2.4: a leading zero is dropped before the lookup, so 07 is channel 7", (() => { const r = Model.resolveChno(planIdx, "07", -1); return [r.kind, r.channelIndex, r.label] })(), ["exact", 1, "7"])
check("CN8: a comma is folded to a dot on lookup", (() => { const r = Model.resolveChno(planIdx, "7,1", -1); return [r.kind, r.channelIndex, r.label] })(), ["exact", 3, "7.1"])
check("CN9: duplicates land on the first, then cycle, then wrap", [Model.resolveChno(planIdx, "12", -1), Model.resolveChno(planIdx, "12", 7), Model.resolveChno(planIdx, "12", 8)].map(r => [r.channelIndex, r.matches, r.ordinal]), [[7, 2, 1], [8, 2, 2], [7, 2, 1]])
check("CN9: a cursor outside the duplicate set starts at the first", (() => { const r = Model.resolveChno(planIdx, "12", 3); return [r.channelIndex, r.ordinal] })(), [7, 1])
check("CN2.3: a prefix picks the LOWEST number, not the first in the playlist", (() => { const r = Model.resolveChno(planIdx, "13", -1); return [r.kind, r.channelIndex, r.label] })(), ["prefix", 6, "130"])
check("CN2.3: a one-digit prefix picks the lowest too", (() => { const r = Model.resolveChno(planIdx, "1", -1); return [r.kind, r.channelIndex, r.label] })(), ["prefix", 0, "10"])
check("CN2.3: a half-typed subchannel prefixes to its first child", (() => { const r = Model.resolveChno(planIdx, "7.", -1); return [r.kind, r.channelIndex, r.label] })(), ["prefix", 3, "7.1"])
check("CN2.3: a prefix onto a duplicated key reports the whole set", (() => { const r = Model.resolveChno(planIdx, "12", -1); return [r.matches, r.ordinal] })(), [2, 1])
// 1.4 `ids` / 5.2: byKey holds playlist indices, but under channelOrder
// "number" the guide and the service hold a REORDERED array, so an index no
// longer names a row. Everything the guide needs must work off the id.
check("CN5.2: the index carries a channel id per numbered playlist index", [Model.chnoIdAt(planIdx, 1), Model.chnoIdAt(planIdx, 7), Model.chnoIdAt(planIdx, 9), Model.chnoIdAt(planIdx, 99), Model.chnoIdAt(planIdx, -1), Model.chnoIdAt(null, 1)], ["b", "h", "", "", "", ""])
check("CN9: the cycle works off a channel id, not only a playlist index", [Model.resolveChno(planIdx, "12", "h").channelIndex, Model.resolveChno(planIdx, "12", "i").channelIndex, Model.resolveChno(planIdx, "12", "b").channelIndex, Model.resolveChno(planIdx, "12", "").channelIndex], [8, 7, 7, 7])
check("CN5.2: the IPC lookup finds the same channel in a reordered array", (() => {
  const reordered = Model.orderChannels(plan, "number", planIdx)
  return [Model.channelByNumber(reordered, planIdx, "12").id, Model.channelByNumber(reordered, planIdx, "139").id, Model.channelByNumber(plan, planIdx, "139").id]
})(), ["h", "f", "f"])
check("CN2.3: no match, an empty buffer and an unnumbered playlist all resolve to none", [Model.resolveChno(planIdx, "205", -1), Model.resolveChno(planIdx, "", -1), Model.resolveChno(Model.buildChnoIndex([]), "1", -1), Model.resolveChno(null, "1", -1)].map(r => [r.kind, r.channelIndex, r.label, r.matches]), [["none", -1, "", 0], ["none", -1, "", 0], ["none", -1, "", 0], ["none", -1, "", 0]])

const plan200rows = Model.prepareChannels((() => { const rows = []; for (let i = 1; i <= 200; i++) rows.push(chan("p" + i, String(i))); return rows })())
const plan200 = Model.buildChnoIndex(plan200rows)
check("CN2.5: 199 in a 1..200 plan commits on the last digit; 1 does not", [Model.chnoUnambiguous(plan200, "199"), Model.chnoUnambiguous(plan200, "1"), Model.chnoUnambiguous(plan200, "20")], [true, false, false])
check("CN2.5: an exact major is ambiguous while a subchannel extends it", [Model.chnoUnambiguous(planIdx, "7"), Model.chnoUnambiguous(planIdx, "130"), Model.chnoUnambiguous(planIdx, "205")], [false, true, false])

check("CN2.4: pushNumberKey takes the snapshot exactly once, on the first key", (() => {
  let e = Model.numberEntry()
  let r = Model.pushNumberKey(e, "1", { scopeId: "g:UK", query: "sky", cursorIndex: 12 })
  const first = [r.entry.active, r.entry.buffer, r.entry.scopeId, r.entry.query, r.entry.cursorIndex, r.changed]
  r = Model.pushNumberKey(r.entry, "0", { scopeId: "all", query: "", cursorIndex: 999 })
  return [first, [r.entry.buffer, r.entry.scopeId, r.entry.query, r.entry.cursorIndex]]
})(), [[true, "1", "g:UK", "sky", 12, true], ["10", "g:UK", "sky", 12]])
check("CN2.4: the buffer is capped, and a refused key does NOT restart the timer", (() => {
  let e = Model.numberEntry()
  for (const t of "123456789") e = Model.pushNumberKey(e, t, {}).entry
  const r = Model.pushNumberKey(e, "0", {})
  return [e.buffer, r.entry.buffer, r.changed]
})(), ["123456789", "123456789", false])
check("CN8: the separator is rejected when the buffer is empty or already has one", (() => {
  const empty = Model.pushNumberKey(Model.numberEntry(), ".", {})
  const seven = Model.pushNumberKey(Model.numberEntry(), "7", {}).entry
  const dot = Model.pushNumberKey(seven, ".", {})
  const twice = Model.pushNumberKey(dot.entry, ".", {})
  const comma = Model.pushNumberKey(seven, ",", {})
  return [[empty.changed, empty.entry.buffer], [dot.changed, dot.entry.buffer], [twice.changed, twice.entry.buffer], [comma.changed, comma.entry.buffer]]
})(), [[false, ""], [true, "7."], [false, "7."], [true, "7."]])
check("CN2.4: a key this feature does not own changes nothing", (() => { const r = Model.pushNumberKey(Model.numberEntry(), "a", {}); const b = Model.pushNumberKey(Model.numberEntry(), "-", {}); return [r.changed, r.entry.active, b.changed] })(), [false, false, false])
check("CN2.4: a digit that resolves to nothing is still accepted, so a typo is visible", (() => { const r = Model.pushNumberKey(Model.pushNumberKey(Model.numberEntry(), "9", {}).entry, "9", {}); return [r.changed, r.entry.buffer] })(), [true, "99"])
check("CN2.6: popNumberKey to empty deactivates but KEEPS the snapshot to restore from", (() => {
  const one = Model.pushNumberKey(Model.numberEntry(), "1", { scopeId: "g:UK", query: "sky", cursorIndex: 12 }).entry
  const two = Model.pushNumberKey(one, "0", {}).entry
  const back = Model.popNumberKey(two)
  const gone = Model.popNumberKey(back)
  return [[back.active, back.buffer], [gone.active, gone.buffer, gone.scopeId, gone.query, gone.cursorIndex]]
})(), [[true, "1"], [false, "", "g:UK", "sky", 12]])
check("CN2.6: popNumberKey on an inactive entry is harmless", (() => { const r = Model.popNumberKey(Model.numberEntry()); const n = Model.popNumberKey(null); return [r.active, r.buffer, n.active, n.buffer] })(), [false, "", false, ""])
check("CN2.6: cancelNumberEntry is idempotent and forgets the snapshot", [Model.cancelNumberEntry(Model.pushNumberKey(Model.numberEntry(), "1", { scopeId: "g:UK", cursorIndex: 4 }).entry), Model.cancelNumberEntry(Model.cancelNumberEntry(null))], [{ active: false, buffer: "", scopeId: "", query: "", cursorIndex: 0, cursorId: "", resume: false }, { active: false, buffer: "", scopeId: "", query: "", cursorIndex: 0, cursorId: "", resume: false }])
check("CN2.3: numberEntry() is the documented zero value", Model.numberEntry(), { active: false, buffer: "", scopeId: "", query: "", cursorIndex: 0, cursorId: "", resume: false })

// ---- CN21 / D-CHNO-2: a number that does not exist must say so.
//
// The live pass typed 20509 on a 3,000-channel plan and landed on channel
// 900 with no error anywhere: the auto-commit fired on the proper prefix 205,
// and the leftover "09" opened a NEW entry that tuned somewhere of its own.
// 28.4% of absent five-digit numbers did that. The rule that fixes it is one
// sentence -- the machine may finish a number early only if it can take it
// back -- and these are its parts.
const { typer, measure } = require("../scripts/chno-entry-rate.js")
const missPlan = Model.prepareChannels([chan("t1", "100"), chan("t2", "205"), chan("t3", "300"), chan("t4", "900")])
const missIdx = Model.buildChnoIndex(missPlan)
const typeMiss = typer(missPlan, missIdx)
const miss20509 = typeMiss("20509", 0)
check("CN21: 205 auto-commits, and the digits after it are still the same number",
  [miss20509.said, miss20509.toldNoExactly, miss20509.moved, miss20509.commits],
  [["Channel 205" + Model.SEP + "Ch t2", "No channel 20509"], true, false, 2])
check("CN21: so the number that does not exist is never a silent landing somewhere else",
  [miss20509.silent, miss20509.landedOn], [false, "100"])
// The instant path is what the rule may not destroy: the commit still fires
// on the last digit, it just stops being the end of the number.
const instant205 = typeMiss("205", 0)
check("CN2.5: an unambiguous number still commits on its last digit, with no wait",
  [instant205.instant, instant205.commits, instant205.landedOn, instant205.said], [true, 1, "205", ["Channel 205" + Model.SEP + "Ch t2"]])
check("CN21: and the entry it leaves behind is inactive, so the chip and the hints are as they were",
  [instant205.armed, typeMiss("20509", 0).armed], [true, false])

const armed205 = Model.closeNumberEntry(
  Model.pushNumberKey(Model.pushNumberKey(Model.pushNumberKey(Model.numberEntry(), "2", { scopeId: "g:UK", query: "sky", cursorIndex: 12, cursorId: "z" }).entry, "0", {}).entry, "5", {}).entry, "auto")
check("CN21: only the auto-commit arms the buffer; every other reason ends the number for good",
  ["auto", "timeout", "enter", "key", "cancel", ""].map(r => [Model.closeNumberEntry(armed205, r).resume, Model.closeNumberEntry(armed205, r).buffer]),
  [[true, "205"], [false, ""], [false, ""], [false, ""], [false, ""], [false, ""]])
check("CN21: an armed buffer is inactive and keeps the pre-entry snapshot",
  [armed205.active, armed205.buffer, armed205.scopeId, armed205.query, armed205.cursorIndex, armed205.cursorId], [false, "205", "g:UK", "sky", 12, "z"])
check("CN21: a key inside the window continues that buffer instead of starting a new entry",
  (() => { const r = Model.pushNumberKey(armed205, "0", { scopeId: "all", query: "", cursorIndex: 99, cursorId: "q" }); return [r.resumed, r.entry.active, r.entry.buffer, r.entry.scopeId, r.entry.cursorIndex, r.entry.resume] })(),
  [true, true, "2050", "g:UK", 12, false])
check("CN21: a separator resumes too, and an unarmed entry still starts fresh",
  [Model.pushNumberKey(armed205, ".").entry.buffer, Model.pushNumberKey(Model.numberEntry(), "0", { cursorIndex: 99 }).entry.buffer,
    Model.pushNumberKey(Model.numberEntry(), "0", { cursorIndex: 99 }).resumed], ["205.", "0", false])
check("CN21: once the window expires the buffer is gone, so the next digit is a new number",
  (() => { const fresh = Model.pushNumberKey(Model.numberEntry(), "0", { cursorIndex: 4, cursorId: "n" }); return [fresh.resumed, fresh.entry.buffer, fresh.entry.cursorIndex] })(), [false, "0", 4])
check("CN21: the auto-commit leaves the digit window RUNNING - it is what disarms the buffer",
  (() => { const s = Model.numberKeyStep(Model.pushNumberKey(Model.numberEntry(), "2", { cursorId: "z" }).entry, missIdx, "0", {}); const t = Model.numberKeyStep(s.entry, missIdx, "5", {}); return [t.commit !== null, t.timer, t.entry.active, t.entry.resume, s.timer] })(),
  [true, "restart", false, true, "restart"])
check("CN21: a resumed buffer can only ever resolve to nothing, which is why saying so is safe",
  (() => {
    const out = []
    for (const key of Object.keys(missIdx.byKey)) {
      if (!Model.chnoUnambiguous(missIdx, key)) continue
      for (const d of "0123456789.") out.push(Model.resolveChno(missIdx, key + d, -1).kind)
    }
    return [out.length, out.every(k => k === "none")]
  })(), [44, true])

// ---- CN9 / D-CHNO-1: three commits of the same number reach both twins.
//
// resolveChno was never wrong; what reached it was. Every intermediate digit
// moves the cursor during the preview ("1" previews 10, "12" is the answer),
// so the live cursor is never on the previous match and the cycle restarted
// at ordinal 1 forever. The `plan` fixture carries the duplicate pair on 12.
const typePlan = typer(plan, planIdx)
const cycle = (() => {
  const out = []
  let at = 0                                  // parked on channel 10, not on either twin
  for (let i = 0; i < 3; i++) { const r = typePlan("12", at); out.push([r.landedOn, plan[r.cursor].id, r.said[0]]); at = r.cursor }
  return out
})()
check("CN9: re-typing a duplicated number walks to the twin and wraps", cycle,
  [["12", "h", "Channel 12" + Model.SEP + "Ch h (1 of 2)"],
   ["12", "i", "Channel 12" + Model.SEP + "Ch i (2 of 2)"],
   ["12", "h", "Channel 12" + Model.SEP + "Ch h (1 of 2)"]])
check("CN9: the cycle is derived from the cursor as it was BEFORE the first digit",
  (() => { const s = Model.numberKeyStep(Model.pushNumberKey(Model.numberEntry(), "1", { cursorId: "h", cursorIndex: 7 }).entry, planIdx, "2", {}); return [s.commit.ordinal, s.resolution.channelIndex, s.entry.buffer] })(),
  [2, 8, "12"])
check("CN9: a preview that moved the cursor cannot restart the cycle",
  (() => { const one = Model.numberKeyStep(Model.numberEntry(), planIdx, "1", { cursorId: "h", cursorIndex: 7 }); return [one.resolution.label, one.entry.cursorId] })(), ["10", "h"])
check("CN9: Backspace previews against the same snapshot cursor",
  (() => { const two = Model.pushNumberKey(Model.pushNumberKey(Model.numberEntry(), "1", { cursorId: "h", cursorIndex: 7 }).entry, "2", {}).entry; const back = Model.numberPopStep(Model.pushNumberKey(two, "9", {}).entry, planIdx); return [back.entry.buffer, back.resolution.channelIndex, back.resolution.ordinal] })(),
  ["12", 8, 2])
check("CN20: the command verb still never cycles, whatever the guide's cursor is doing",
  [Model.channelByNumber(plan, planIdx, "12").id, Model.channelByNumber(plan, planIdx, "12").id, Model.channelByNumber(plan, planIdx, "12").id], ["h", "h", "h"])

// The rate, on a whole sample rather than one number: every absent number in
// a range, typed at speed, on a 1..200 plan (where 200x is the trap 20509
// was). The measurement that reports the live-pass fixture is this same
// function; see scripts/chno-entry-rate.js.
const rate200 = measure(plan200rows, plan200, 2000, 2099, 0)
check("CN21: over a whole sample, nothing lands silently and everything absent is reported",
  [rate200.absentSample, rate200.silentMistunes, rate200.movedAtAll, rate200.toldNoChannel], [100, 0, 0, 100])
check("CN21: and the instant path over the same plan is untouched",
  [rate200.distinctNumbers, rate200.instantCommits, rate200.instantRate, rate200.autoCommittedEarly], [200, 180, "90.0%", 10])

// ---- CN23: the scenarios of section 10.6, by name.
//
// Twenty of them had no runner at all and had never executed. The half of
// each that is a DECISION runs here, against the same functions the guide
// calls; the half that needs a cursor, a scope hop, a timer or a window is
// driven by scripts/dev-harness/chno-entry-scenario.sh. N3, N4, N10, N15,
// N21, N22, N23 and N24 have no decision half and are not here - see that
// file's header for which of them were struck and why.
const typeIdx = typer(plan, planIdx)
check("N1: each digit extends the buffer and previews the lowest match", (() => {
  const seen = []
  let e = Model.numberEntry()
  for (const d of "13") { const s = Model.numberKeyStep(e, planIdx, d, { cursorId: "a", cursorIndex: 0 }); e = s.entry; seen.push([s.entry.buffer, s.resolution.kind, s.resolution.label]) }
  return seen
})(), [["1", "prefix", "10"], ["13", "prefix", "130"]])
check("N2: the window closes the entry and the footer names the channel", (() => {
  const s = Model.numberKeyStep(Model.pushNumberKey(Model.numberEntry(), "1", { cursorId: "a" }).entry, planIdx, "3", {})
  const done = Model.numberCommitStep(s.entry, s.resolution, "Ch g", { play: false, reason: "timeout" })
  return [done.plan.status, done.entry.active, done.entry.resume, done.plan.restore]
})(), ["Channel 130" + Model.SEP + "Ch g", false, false, false])
check("N5: Backspace drops one character and previews what is left", (() => {
  const two = Model.pushNumberKey(Model.pushNumberKey(Model.numberEntry(), "1", { cursorId: "a", cursorIndex: 3 }).entry, "3", {}).entry
  const back = Model.numberPopStep(two, planIdx)
  return [back.entry.buffer, back.entry.active, back.resolution.label, back.cancelled, back.timer]
})(), ["1", true, "10", false, "restart"])
check("N6: Backspace to empty ends the entry and hands back the snapshot to restore", (() => {
  const one = Model.pushNumberKey(Model.numberEntry(), "1", { scopeId: "g:UK", query: "sky", cursorIndex: 9, cursorId: "f" }).entry
  const back = Model.numberPopStep(one, planIdx)
  return [back.cancelled, back.entry.active, back.timer, back.snapshot.scopeId, back.snapshot.query, back.snapshot.cursorIndex]
})(), [true, false, "stop", "g:UK", "sky", 9])
check("N7: Esc is the same close, and it forgets the buffer rather than arming it", (() => {
  const one = Model.pushNumberKey(Model.numberEntry(), "1", { scopeId: "g:UK", cursorIndex: 9 }).entry
  const done = Model.numberCommitStep(one, Model.resolveChno(planIdx, "1", "f"), "Ch a", { play: false, reason: "cancel" })
  return [Model.closeNumberEntry(one, "cancel").buffer, Model.closeNumberEntry(one, "cancel").resume, done.snapshot.cursorIndex]
})(), ["", false, 9])
const miss205 = typeIdx("205", 0)
check("N8: an unknown number reports the digits that were typed, and moves nothing",
  [miss205.said, miss205.moved, miss205.toldNoExactly], [["No channel 205"], false, true])
check("N9: Enter on an unknown number refuses to play and restores",
  Model.chnoCommitPlan("none", "205", "", 0, 0, { play: true, keepOpen: true }), { restore: true, play: false, keepOpen: true, status: "No channel 205" })
check("N11: a subchannel resolves on either separator, and the major alone waits for the window",
  [typeIdx("7.1", 0).landedOn, typeIdx("7,1", 0).landedOn, typeIdx("7.1", 0).instant, typeIdx("7", 0).instant, typeIdx("7", 0).said],
  ["7.1", "7.1", true, false, ["Channel 7" + Model.SEP + "Ch b"]])
check("N12: three commits of a duplicated number give ordinals 1, 2, 1", cycle.map(c => c[1]), ["h", "i", "h"])
check("N13: an unambiguous number commits on the last digit, with no wait",
  [typeIdx("130", 0).instant, typeIdx("130", 0).commits, typeIdx("130", 0).landedOn], [true, 1, "130"])
check("N14: an unnumbered playlist answers a digit with one transient, and drops the hint",
  (() => {
    const none = Model.buildChnoIndex(Model.prepareChannels([chan("x", "HD"), chan("y", null)]))
    const hints = Model.footerHints({ mode: "list", hasNumbers: false }).map(h => h[0])
    return [Model.numberKeyAction({ text: "5", hasNumbers: false }), Model.chnoStatus("noNumbers", "", "", 0, 0, true),
      hints.indexOf("0-9"), Model.chnoColumnUnits(none.maxLabelLen), none.hasNumbers]
  })(), ["noNumbers", "No channel numbers in this playlist", -1, 24, false])
// N16's other half - that a digit in search mode never reaches the buffer at
// all - is the guide's listMode guard, and it is asserted in the scenario.
check("N16: an all-digit query stays a query, and floats the exact number match",
  (() => {
    const rows = Model.filterChannels(plan, "12", 20, [], planIdx)
    return [Model.isNumericQuery("12"), rows.rows[0].id, rows.rows[0].chnoLabel]
  })(), [true, "h", "12"])

check("CN5.2: orderChannels is identity for playlist order, and for an unnumbered playlist", [Model.orderChannels(plan, "playlist", planIdx) === plan, Model.orderChannels(plan, "number", Model.buildChnoIndex([])) === plan, Model.orderChannels(plan, "", planIdx) === plan], [true, true, true])
check("CN5.2: number order gathers by chnoSort, unnumbered channels last in playlist order", Model.orderChannels(plan, "number", planIdx).map(c => c.chnoLabel + "/" + c.id), ["7/b", "7.1/d", "7.2/c", "8/e", "10/a", "12/h", "12/i", "130/g", "139/f", "/j", "/k"])
check("CN5.2: a duplicate pair keeps playlist order between its members", Model.orderChannels(plan, "number", planIdx).map(c => c.id).join("").indexOf("hi") >= 0, true)
check("CN5.2: the input array is never mutated", plan.map(c => c.id).join(","), "a,b,c,d,e,f,g,h,i,j,k")
check("CN5.2: an index built from a different array cannot index out of range", Model.orderChannels([chan("only", "1")], "number", planIdx).length, 1)

check("CN3: channelOrderOf is total, and unreadable input means the safe default", [Model.channelOrderOf("number"), Model.channelOrderOf("Number"), Model.channelOrderOf(" number "), Model.channelOrderOf("playlist"), Model.channelOrderOf(""), Model.channelOrderOf("alpha"), Model.channelOrderOf(null), Model.channelOrderOf(7), Model.channelOrderOf(undefined)], ["number", "number", "number", "playlist", "playlist", "playlist", "playlist", "playlist", "playlist"])

check("CN5: isNumericQuery truth table", ["101", "7.1", "7,1", "99999", "0", " 101 ", "123456", "7.1234", "7.", "10a", "sky", "", null].map(Model.isNumericQuery), [true, true, true, true, true, true, false, false, false, false, false, false, false])
check("CN2.9: isNumberEntryKey truth table", ["0", "5", "9", ".", ",", "-", "a", "", "12", "\b", "\u007f", null, undefined].map(Model.isNumberEntryKey), [true, true, true, true, true, false, false, false, false, false, false, false, false])

// ---- gate A1: the key routing rule, lifted out of Guide.qml so a test can
// reach it (CLAUDE.md 12). These are the Qt::KeyboardModifier bits a real
// key event carries. The two that must NOT be rejected are Shift (AZERTY
// and bepo put the top-row digits at shift level 2) and Keypad (KP_0..KP_9
// carry it), both verified against libxkbcommon with real compiled keymaps.
const SHIFT = 0x02000000, CTRL = 0x04000000, ALT = 0x08000000, META = 0x10000000, KEYPAD = 0x20000000, ALTGR = 0x40000000
const numKey = (o) => Model.numberKeyAction(Object.assign({ hasNumbers: true, active: false, modifiers: 0 }, o))
check("A1: a plain digit starts entry", numKey({ text: "1" }), "digit")
check("A1: a SHIFTED digit is still a digit - AZERTY and bepo put 1 at shift level 2", numKey({ text: "1", modifiers: SHIFT }), "digit")
check("A1: a KEYPAD digit is still a digit - KP_1 has text \"1\" and carries KeypadModifier", numKey({ text: "1", modifiers: KEYPAD }), "digit")
check("A1: a keypad digit that is also shifted is still a digit", numKey({ text: "7", modifiers: SHIFT | KEYPAD }), "digit")
check("A1: AltGr (GroupSwitchModifier, Mod5) is not Alt and is not rejected", numKey({ text: "1", modifiers: ALTGR }), "digit")
check("A1: Ctrl, Alt and Meta are chords, not digits", [numKey({ text: "1", modifiers: CTRL }), numKey({ text: "1", modifiers: ALT }), numKey({ text: "1", modifiers: META }), numKey({ text: "1", modifiers: CTRL | SHIFT })], ["pass", "pass", "pass", "pass"])
check("CN8: both separators are entry keys, the parse-only hyphen is not", [numKey({ text: "." }), numKey({ text: "," }), numKey({ text: "-" }), numKey({ text: "j" })], ["digit", "digit", "pass", "pass"])
check("A1: the chord mask contains Ctrl, Alt and Meta and NOT Shift or Keypad", [(Model.CHNO_CHORD_MASK & CTRL) !== 0, (Model.CHNO_CHORD_MASK & ALT) !== 0, (Model.CHNO_CHORD_MASK & META) !== 0, (Model.CHNO_CHORD_MASK & SHIFT) !== 0, (Model.CHNO_CHORD_MASK & KEYPAD) !== 0], [true, true, true, false, false])
check("CN2.9: Backspace is the buffer's only while the buffer is live", [numKey({ backspace: true, active: true }), numKey({ backspace: true, active: false }), numKey({ backspace: true, active: true, modifiers: CTRL })], ["backspace", "pass", "pass"])
check("CN1.5: an unnumbered playlist answers once rather than staying silent", [numKey({ text: "5", hasNumbers: false }), numKey({ text: "j", hasNumbers: false }), numKey({ backspace: true, active: true, hasNumbers: false })], ["noNumbers", "pass", "backspace"])
check("CN2.9: a garbage event is passed through, never swallowed", [numKey({ text: "" }), numKey({ text: null }), numKey({ text: "12" }), Model.numberKeyAction(null), Model.numberKeyAction({})], ["pass", "pass", "pass", "pass", "pass"])

// CN1 / 2.5 step 4: a commit never plays a number that resolved to nothing.
check("CN1: a resolved commit plays only when Enter or Space asked it to", [Model.chnoCommitPlan("exact", "101", "Sky", 1, 1, {}), Model.chnoCommitPlan("exact", "101", "Sky", 1, 1, { play: true }), Model.chnoCommitPlan("exact", "101", "Sky", 1, 1, { play: true, keepOpen: true })].map(p => [p.restore, p.play, p.keepOpen]), [[false, false, false], [false, true, false], [false, true, true]])
check("CN1: Enter on an unknown number restores the snapshot and refuses to play", Model.chnoCommitPlan("none", "205", "", 0, 0, { play: true }), { restore: true, play: false, keepOpen: false, status: "No channel 205" })
check("CN1: a prefix commit is a real commit", Model.chnoCommitPlan("prefix", "130", "Some Channel", 1, 1, { play: true }), { restore: false, play: true, keepOpen: false, status: "Channel 130" + Model.SEP + "Some Channel" })

check("CN4.2: chnoColumnUnits clamps at both ends", [0, 1, 2, 3, 4, 5, 6, 7, 9, 99, null, undefined, -4].map(Model.chnoColumnUnits), [24, 24, 24, 32, 40, 48, 56, 56, 56, 56, 24, 24, 24])

check("CN3.2: channelByNumber tunes on exact and on prefix, and never cycles", [Model.channelByNumber(plan, planIdx, "007").id, Model.channelByNumber(plan, planIdx, "  12  ").id, Model.channelByNumber(plan, planIdx, "12").id, Model.channelByNumber(plan, planIdx, "7-1").id, Model.channelByNumber(plan, planIdx, "13").id], ["b", "h", "h", "d", "g"])
check("CN3.2: an unknown or unparsable number is null, never a wrong channel", [Model.channelByNumber(plan, planIdx, "205"), Model.channelByNumber(plan, planIdx, "HD"), Model.channelByNumber(plan, planIdx, ""), Model.channelByNumber(plan, null, "7"), Model.channelByNumber(null, planIdx, "7")], [null, null, null, null, null])
// CN9 does NOT apply to IPC (3.2): a script asking for 12 must get the same
// channel every time. The duplicate pair sits at playlist indices 0 and 1 on
// purpose, so a cursor leaking into the call -- the realistic regression,
// and 0 is where a cursor most often is -- changes the answer and is caught.
check("CN3.2: the IPC lookup never cycles, however often it is called", (() => {
  const dup = Model.prepareChannels([chan("first", "5"), chan("second", "5"), chan("third", "9")])
  const dupIdx = Model.buildChnoIndex(dup)
  return [dupIdx.byKey["5"], Model.channelByNumber(dup, dupIdx, "5").id, Model.channelByNumber(dup, dupIdx, "5").id, Model.channelByNumber(dup, dupIdx, "05").id]
})(), [[0, 1], "first", "first", "first"])

const searchRows = Model.prepareChannels([
  { id: "s1", name: "101 Barz", group: "Music", chno: "55" },
  { id: "s2", name: "Channel 101 News", group: "News", chno: "9" },
  { id: "s3", name: "Sky Sports Main Event", group: "Sports", chno: "101" },
  { id: "s4", name: "77 Rock", group: "Music", chno: "77" }
])
const searchIdx = Model.buildChnoIndex(searchRows)
check("CN5/2.8: the shipped 4-argument call is unchanged", (() => { const r = Model.filterChannels(searchRows, "101", 200, []); return [r.rows.map(c => c.id), r.total, r.truncated] })(), [["s1", "s2"], 2, false])
check("CN5/2.8: an all-digit query floats the exact number match to the head", (() => { const r = Model.filterChannels(searchRows, "101", 200, [], searchIdx); return [r.rows.map(c => c.id), r.total, r.truncated] })(), [["s3", "s1", "s2"], 2, false])
check("CN5/2.8: no duplicate row when the ranker already produced it", (() => { const r = Model.filterChannels(searchRows, "77", 200, [], searchIdx); return r.rows.map(c => c.id) })(), ["s4"])
check("CN5/2.8: a non-numeric query is untouched", (() => { const a = Model.filterChannels(searchRows, "sky", 200, [], searchIdx); const b = Model.filterChannels(searchRows, "sky", 200, []); return [a.rows.map(c => c.id), b.rows.map(c => c.id)] })(), [["s3"], ["s3"]])
check("CN5/2.8: an unnumbered playlist floats nothing", (() => { const r = Model.filterChannels(searchRows, "101", 200, [], Model.buildChnoIndex([])); return r.rows.map(c => c.id) })(), ["s1", "s2"])
check("CN5/2.8: leading zeros and a comma reach the same channel", [Model.filterChannels(searchRows, "0101", 200, [], searchIdx).rows[0].id, Model.filterChannels(searchRows, "077", 200, [], searchIdx).rows[0].id], ["s3", "s4"])
check("CN5/2.8: R3's cap still holds - the floated row displaces the last one", (() => {
  const rows = Model.prepareChannels([
    { id: "n1", name: "12 A", group: "G" }, { id: "n2", name: "12 B", group: "G" },
    { id: "n3", name: "12 C", group: "G" }, { id: "n4", name: "12 D", group: "G" },
    { id: "n5", name: "12 E", group: "G" }, { id: "espn", name: "ESPN", group: "Sports", chno: "12" }
  ])
  const idx = Model.buildChnoIndex(rows)
  const bare = Model.filterChannels(rows, "12", 3, [])
  const with5 = Model.filterChannels(rows, "12", 3, [], idx)
  return [bare.rows.map(c => c.id), with5.rows.map(c => c.id), with5.total, with5.truncated]
})(), [["n1", "n2", "n3"], ["espn", "n1", "n2"], 5, true])
check("CN5/2.8: the float is scope-relative, not a playlist index (a group search)", (() => {
  // byKey holds playlist indices; this scope array has different ones.
  const scope = [searchRows[3], searchRows[2]]
  const r = Model.filterChannels(scope, "101", 200, [], searchIdx)
  return r.rows.map(c => c.id)
})(), ["s3"])

const liveEntry = { active: true, buffer: "10", kind: "prefix", label: "10", name: "BBC Four HD", matches: 1, ordinal: 1 }
const dupEntry = { active: true, buffer: "12", kind: "exact", label: "12", name: "ESPN HD", matches: 2, ordinal: 1 }
const missEntry = { active: true, buffer: "205", kind: "none", label: "", name: "", matches: 0, ordinal: 0 }
const footBase = { configured: true, count: 1204, lastUpdated: "12:40" }
check("CN6.2: a live buffer outranks a transient at the top of the ladder", Model.footerStatus(Object.assign({}, footBase, { transient: "Refreshed" + Model.ELLIPSIS, numberEntry: liveEntry })), "Channel 10")
check("CN6.2: a live single match shows the number alone", Model.footerStatus(Object.assign({}, footBase, { numberEntry: liveEntry })), "Channel 10")
check("CN6.2: duplicates name the channel and count it, live", Model.footerStatus(Object.assign({}, footBase, { numberEntry: dupEntry })), "Channel 12" + Model.SEP + "ESPN HD (1 of 2)")
check("CN6.2: a live miss says so with the digits the user typed", Model.footerStatus(Object.assign({}, footBase, { numberEntry: missEntry })), "Channel 205" + Model.SEP + "no match")
check("CN6.2: an inactive entry leaves the shipped ladder alone", [Model.footerStatus(Object.assign({}, footBase, { numberEntry: Model.numberEntry(), transient: "Stopped" })), Model.footerStatus(Object.assign({}, footBase, { numberEntry: null }))], ["Stopped", "1,204 channels" + Model.SEP + "updated 12:40"])
check("CN6.2: the committed strings", [Model.chnoStatus("exact", "101", "Sky Sports Main Event", 1, 1, true), Model.chnoStatus("exact", "12", "ESPN SD", 2, 2, true), Model.chnoStatus("none", "205", "", 0, 0, true), Model.chnoStatus("noNumbers", "", "", 0, 0, true)], ["Channel 101" + Model.SEP + "Sky Sports Main Event", "Channel 12" + Model.SEP + "ESPN SD (2 of 2)", "No channel 205", "No channel numbers in this playlist"])
check("CN6.2: the (n of m) suffix appears only when m > 1", [Model.chnoStatus("exact", "101", "Sky", 1, 1, true), Model.chnoStatus("exact", "101", "Sky", 0, 0, true)], ["Channel 101" + Model.SEP + "Sky", "Channel 101" + Model.SEP + "Sky"])
check("CN6.2: a commit with no name still reads as a channel", Model.chnoStatus("prefix", "10", "", 1, 1, true), "Channel 10")

const hintsBase = { mode: "list", query: "" }
const shippedList = [["j/k", "move"], ["h/l", "group"], ["Enter", "play"], ["Space", "preview"], ["f", "favorite"], ["s", "stop"], ["p", "pip"], ["r", "refresh"], ["/", "search"], ["o", "sources"]]
check("CN6.3: an unnumbered playlist gains no hint at all", Model.footerHints(hintsBase), shippedList)
check("CN6.3: hasNumbers inserts 0-9 channel between / search and o sources", Model.footerHints(Object.assign({}, hintsBase, { hasNumbers: true })), [["j/k", "move"], ["h/l", "group"], ["Enter", "play"], ["Space", "preview"], ["f", "favorite"], ["s", "stop"], ["p", "pip"], ["r", "refresh"], ["/", "search"], ["0-9", "channel"], ["o", "sources"]])
check("CN6.3: while typing, the hint line is the entry line and nothing else", Model.footerHints(Object.assign({}, hintsBase, { hasNumbers: true, numberEntry: liveEntry })), [["0-9", "digits"], [".", "sub"], ["Enter", "play"], ["Backspace", "undo"], ["Esc", "cancel"]])
check("CN6.3: search mode, sources and the empty states are untouched", [Model.footerHints({ mode: "search", query: "", hasNumbers: true }), Model.footerHints({ mode: "search", query: "sky", hasNumbers: true }), Model.footerHints({ mode: "list", empty: "loading", hasNumbers: true })], [[["Enter", "play"], ["Up/Down", "move"], ["Left/Right", "group"], ["Tab", "keys"], ["Esc", "close"]], [["Enter", "play"], ["Up/Down", "move"], ["Left/Right", "narrow"], ["Tab", "keys"], ["Esc", "clear"]], [["Esc", "close"]]])

check("CN8.1: a numbered row announces its number first", [Model.rowAccessibleName({ name: "Sky Sports Main Event", chno: "101", favorite: true, playing: true }), Model.rowAccessibleName({ name: "Al Jazeera English", chno: "" }), Model.rowAccessibleName({ name: "Al Jazeera English" })], ["Channel 101, Sky Sports Main Event, favorite, playing", "Al Jazeera English", "Al Jazeera English"])
check("CN6.4: the bar tooltip and accessible name carry the number when there is one", [Model.barTooltip({ playing: true, name: "Sky Sports Main Event", chno: "101" }), Model.barTooltip({ playing: true, name: "Sky Sports Main Event" }), Model.barAccessibleName({ playing: true, name: "Sky Sports Main Event", chno: "101" }), Model.barAccessibleName({ playing: true, name: "Sky Sports Main Event" })], ["Playing 101" + Model.SEP + "Sky Sports Main Event", "Playing Sky Sports Main Event", "IPTV, playing channel 101, Sky Sports Main Event", "IPTV, playing Sky Sports Main Event"])

check("CN7.1: the three new settings default as documented", (() => { const s = Model.settingsFrom({ id: "x" }); return [s.channelOrder, s.numberEntryMs, s.barShowChannelNumber] })(), ["playlist", 2000, true])
check("CN2/7.1: numberEntryMs clamps at both ends and survives garbage", [Model.settingsFrom({ numberEntryMs: 100 }).numberEntryMs, Model.settingsFrom({ numberEntryMs: 99999 }).numberEntryMs, Model.settingsFrom({ numberEntryMs: "2000" }).numberEntryMs, Model.settingsFrom({ numberEntryMs: "soon" }).numberEntryMs, Model.settingsFrom({ numberEntryMs: null }).numberEntryMs], [400, 5000, 2000, 2000, 2000])
check("CN7.1: channelOrder and barShowChannelNumber read the same way the shipped keys do", [Model.settingsFrom({ channelOrder: "number" }).channelOrder, Model.settingsFrom({ channelOrder: "NUMBER" }).channelOrder, Model.settingsFrom({ channelOrder: "nonsense" }).channelOrder, Model.settingsFrom({ barShowChannelNumber: false }).barShowChannelNumber, Model.settingsFrom({ barShowChannelNumber: "false" }).barShowChannelNumber, Model.settingsFrom({ barShowChannelNumber: "true" }).barShowChannelNumber], ["number", "number", "playlist", false, false, true])
check("CN7.1: the seven shipped settings are unchanged by the three additions", (() => { const s = Model.settingsFrom({ playlistUrl: " http://h.test/a.m3u ", epgUrl: "", refreshMinutes: 45, mpvArgs: "--mute", showChannelName: false, maxRecents: 3, barLabelMaxWidth: 200 }); return [s.playlistUrl, s.epgUrl, s.refreshMinutes, s.mpvArgs, s.showChannelName, s.maxRecents, s.barLabelMaxWidth] })(), ["http://h.test/a.m3u", "", 45, "--mute", false, 3, 200])


// ================= cross-lane parity (M2-03 integration) =================
//
// Three rules in this feature are stated in two files, and the two files
// belong to two lanes that built in parallel. Nothing held the statements
// together: each side had its own tests, both were green, and a drift would
// have shown up only on a user's machine. Every check below reads the OTHER
// lane's artifact instead of a number retyped here.

// ---- 1. which attribute carries a channel number (CN11)
//
// The helper decides the ATTRIBUTE (bin/omarchy-iptv, CHNO_ATTRS); the model
// decides what the value MEANS (Model.js, CHNO_FIELDS). Both read this one
// fixture, and so does tests/test_playlist.py.
const chnoAttrs = JSON.parse(require("fs").readFileSync(require("path").join(__dirname, "fixtures/chno-attrs.json"), "utf8"))

check("CN11 parity: the fixture is the model's field list, cache spellings first",
  Model.CHNO_FIELDS, chnoAttrs.cacheFields.concat(chnoAttrs.m3uAttributes))
check("CN11 parity: every attribute the helper reads is read here too",
  chnoAttrs.m3uAttributes.map(function (key) { const row = {}; row[key] = "42"; return Model.chnoRawOf(row) }),
  chnoAttrs.m3uAttributes.map(function () { return "42" }))
check("CN11 parity: every cache spelling is read",
  chnoAttrs.cacheFields.map(function (key) { const row = {}; row[key] = "42"; return Model.chnoRawOf(row) }),
  chnoAttrs.cacheFields.map(function () { return "42" }))
// Precedence, pair by pair over the declared order: an earlier field always
// wins over every later one, which is the half a single-attribute test cannot
// see.
const chnoOrder = chnoAttrs.cacheFields.concat(chnoAttrs.m3uAttributes)
const chnoPairs = []
for (let i = 0; i < chnoOrder.length; i++) {
  for (let j = i + 1; j < chnoOrder.length; j++) {
    const row = {}
    row[chnoOrder[i]] = "earlier"
    row[chnoOrder[j]] = "later"
    chnoPairs.push(Model.chnoRawOf(row))
  }
}
check("CN11 parity: an earlier field wins over every later one",
  [chnoPairs.length, chnoPairs.filter(function (v) { return v === "earlier" }).length],
  [chnoOrder.length * (chnoOrder.length - 1) / 2, chnoOrder.length * (chnoOrder.length - 1) / 2])
// The grammar's ceiling is stated a third time, in scripts/gen-playlist.py:
// the generator must never emit a number this parser refuses, or the live
// pass measures a playlist whose channels are displayed blank and cannot be
// typed. tests/test_playlist.py asserts the generator's copy against the same
// fixture value.
check("CN1.2 parity: the fixture's maxMajor is the model's, and one past it is not a number",
  [Model.MAX_CHNO_MAJOR, Model.parseChno(String(chnoAttrs.maxMajor)).ok, Model.parseChno(String(chnoAttrs.maxMajor + 1)).ok],
  [chnoAttrs.maxMajor, true, false])
check("CN11 parity: an attribute nobody agreed to read stays unread",
  chnoAttrs.notRead.map(function (key) { const row = {}; row[key] = "42"; return Model.chnoRawOf(row) }),
  chnoAttrs.notRead.map(function () { return "" }))

// ---- 2. the settings contract: manifest.json (lane B) vs Model.js (lane A)
//
// The host reads manifest.json to decide what control to draw and what range
// to offer; the plugin reads SETTING_RANGES to decide what it will accept. A
// manifest offering 400..5000 against a model clamping 500..3000 is a slider
// that silently does nothing at both ends, and nothing here noticed. The
// manifest IS the shared artifact, so this reads it.
const manifest = JSON.parse(require("fs").readFileSync(require("path").join(__dirname, "..", "manifest.json"), "utf8"))
const manifestDefaults = manifest.barWidget.defaults
const manifestSchema = manifest.barWidget.schema
const defaulted = Model.settingsFrom(null)

check("settings parity: the model's defaults ARE the manifest's defaults",
  Object.keys(manifestDefaults).map(function (key) { return key + "=" + JSON.stringify(defaulted[key]) }),
  Object.keys(manifestDefaults).map(function (key) { return key + "=" + JSON.stringify(manifestDefaults[key]) }))
// M2-05 section 6's three PiP keys. The design gave `manifest.json` to lane
// V2 and this file to lane V1, so neither could declare them without turning
// the other's gate red (ruling PIP16: two files a test asserts about each
// other are one unit). They land together at integration, and the exception
// that stood in for that - a by-name exclusion list here - is gone with them:
// the equality below is total again, in both directions.
check("settings parity: the model knows every key the manifest declares, and no others",
  Object.keys(defaulted).slice().sort(), Object.keys(manifestDefaults).slice().sort())

const integerKeys = manifestSchema.filter(function (entry) { return entry.type === "integer" }).map(function (entry) { return entry.key })
// The count is stated AND the property it stands for: every integer control
// the host draws is one the model ranges. The bare count catches a key
// silently dropped from the schema (which the property below cannot see,
// because it only walks what the manifest still declares); the property
// catches a key declared with no clamp behind it.
check("settings parity: every integer setting the manifest declares is one the model ranges, all six of them",
  [integerKeys.filter(function (key) { return Model.SETTING_RANGES[key] === undefined }), integerKeys.indexOf("numberEntryMs") >= 0, integerKeys.length],
  [[], true, 6])
check("settings parity: SETTING_RANGES equals the manifest's own min/max/default",
  integerKeys.map(function (key) { return key + " " + JSON.stringify(Model.SETTING_RANGES[key]) }),
  manifestSchema.filter(function (entry) { return entry.type === "integer" })
    .map(function (entry) { return entry.key + " " + JSON.stringify({ def: entry.defaultValue, min: entry.min, max: entry.max }) }))
// And the behaviour, not just the constant: what the host lets a user pick is
// exactly what settingsFrom keeps, at both ends and one step outside them.
check("settings parity: settingsFrom keeps both ends of the manifest range and clamps outside it",
  manifestSchema.filter(function (entry) { return entry.type === "integer" }).map(function (entry) {
    const at = function (value) { const from = {}; from[entry.key] = value; return Model.settingsFrom(from)[entry.key] }
    return [at(entry.min), at(entry.max), at(entry.min - 1), at(entry.max + 1)].join("/")
  }),
  manifestSchema.filter(function (entry) { return entry.type === "integer" }).map(function (entry) {
    return [entry.min, entry.max, entry.min, entry.max].join("/")
  }))

// ---- 3. how a boolean setting is read
//
// The rule -- anything but `false` and the string "false" means on -- was
// written out four times: twice in settingsFrom and twice in BarWidget.qml,
// which reads its own injected entry instead of going through the service.
// All four agreed. M2-03 added the fourth by copying the third, which is how
// the next one would have arrived too, so there is one now.
const boolRaw = [true, false, "true", "false", "False", "0", "1", "", 0, 1, null, undefined, [], {}]
check("R2: boolSetting is the one reading of a boolean setting",
  boolRaw.map(function (v) { return Model.boolSetting(v) }),
  [true, false, true, false, true, true, true, true, true, true, true, true, true, true])
check("R2: settingsFrom and the bar read a boolean the same way",
  boolRaw.map(function (v) { return Model.settingsFrom({ barShowChannelNumber: v, showChannelName: v }) })
    .map(function (s) { return s.barShowChannelNumber === s.showChannelName ? s.showChannelName : "DISAGREE" }),
  // null and undefined never reach the reader: settingOf substitutes the
  // default first, so they are the default, true.
  boolRaw.map(function (v) { return Model.boolSetting(v === null || v === undefined ? true : v) }))

// ---- 4. the label cap is derived from the grammar, not guessed (CN18)
//
// The cap was 7 in the design and 7 in lane B's stand-in, and the grammar two
// steps above it admits "99999.999". At 7 a channel could be displayed and be
// untypable. This ties the constant to the grammar, so raising MAX_CHNO_MAJOR
// without raising the cap turns the gate red instead of rejecting numbers.
const widestChno = String(Model.MAX_CHNO_MAJOR) + Model.CHNO_ENTRY_SEP + String(Model.MAX_CHNO_MINOR)
check("CN18: MAX_CHNO_LABEL is the length of the widest label the grammar admits",
  [Model.parseChno(widestChno).ok, Model.parseChno(widestChno).label.length, Model.MAX_CHNO_LABEL],
  [true, widestChno.length, widestChno.length])
check("CN18: the entry buffer accepts a number that long, so nothing displayable is untypable",
  (function () {
    let entry = Model.numberEntry()
    for (let i = 0; i < widestChno.length; i++) entry = Model.pushNumberKey(entry, widestChno.charAt(i), {}).entry
    return entry.buffer
  })(), widestChno)

// ======================================================================
// Picture in picture (M2-05 section 10.1), lane V1
// ======================================================================
//
// The vectors live in tests/fixtures/pip-cases.js so the QML spec runs the
// same ones in the engine that actually executes Model.js. Every expected box
// there is derived by hand from design 4.4, and the first is the box the gate
// applied to a real window and read back.
//
// What these prove, and what they cannot (10.5): the arithmetic on monitors
// that do not exist on this machine, the plan's order and conditionals, the
// address pattern, every clamp, and that no value a user or a provider
// controls can reach a dispatch vector. Nothing here proves Hyprland does
// what it is told - only the live pass can, and after PIP11 only by reading
// the state back, which is what pipVerify is.
// ---- 1. the expression boundary (PIP7, design 4.11)

check("PIP7: the six window verbs and focus build the expressions the gate proved live", [
  Model.pipExpression("float", { window: "address:" + pipFixture.PLAYER_ADDRESS }),
  Model.pipExpression("resize", { window: "address:" + pipFixture.PLAYER_ADDRESS, x: 410, y: 230 }),
  Model.pipExpression("move", { window: "address:" + pipFixture.PLAYER_ADDRESS, x: 940, y: 42 }),
  Model.pipExpression("pin", { window: "address:" + pipFixture.PLAYER_ADDRESS }),
  Model.pipExpression("zorder", { window: "address:" + pipFixture.PLAYER_ADDRESS, mode: "top" }),
  Model.pipExpression("tag", { window: "address:" + pipFixture.PLAYER_ADDRESS, tag: "+iptv-pip" })
], [
  "hl.dsp.window.float({ window = \"address:0x559c6893d940\" })",
  "hl.dsp.window.resize({ window = \"address:0x559c6893d940\", x = 410, y = 230 })",
  "hl.dsp.window.move({ window = \"address:0x559c6893d940\", x = 940, y = 42 })",
  "hl.dsp.window.pin({ window = \"address:0x559c6893d940\" })",
  "hl.dsp.window.alter_zorder({ window = \"address:0x559c6893d940\", mode = \"top\" })",
  "hl.dsp.window.tag({ window = \"address:0x559c6893d940\", tag = \"+iptv-pip\" })"
])
// PIP10: no step carries `action`. The gate proved it is ignored - a `set`
// toggles, a second `set` toggles back, and an `unset` on a tiled window
// FLOATS it - so an argument the compositor throws away would be a lie about
// what the code does, and the next reader would trust it.
check("PIP10: no step carries the action argument the compositor ignores",
  Model.pipExpression("float", { window: "address:" + pipFixture.PLAYER_ADDRESS }).indexOf("action") >= 0, false)

// THE hostile-value test (PIP7: "prove a hostile value is REFUSED rather than
// escaped"). Two of these were fired at the live compositor during the gate's
// privacy sweep. One was a Lua parse error; the other was accepted in SILENCE
// with rc 0 and did nothing - which is why the pattern, and never the
// compositor's reply, is the defence. An empty string out means refused: the
// builder has no escaping function and never will, because a value that would
// need escaping is a value that must not be here.
check("PIP7: a hostile address is REFUSED, not escaped or quoted",
  pipFixture.HOSTILE_ADDRESSES.map(function (value) { return Model.pipExpression("tag", { window: "address:" + value, tag: "+iptv-pip" }) }),
  pipFixture.HOSTILE_ADDRESSES.map(function () { return "" }))
// The same values in the SELECTOR position. "address:0x1" is dropped here
// and only here: as a selector it is a perfectly good one, which is exactly
// why it must be refused as an ADDRESS above - double-prefixing is how a
// caller would smuggle a selector through the address check.
const hostileSelectors = pipFixture.HOSTILE_ADDRESSES.filter(function (value) { return value !== "address:0x1" })
check("PIP7: the same values refused as a bare selector, and as argv",
  hostileSelectors.map(function (value) { return Model.pipExpression("float", { window: value }) + "|" + Model.pipDispatchArgv("float", { window: value }).length }),
  hostileSelectors.map(function () { return "|0" }))
check("PIP7: a hostile or non-integer coordinate is refused, never coerced",
  pipFixture.HOSTILE_COORDS.map(function (value) { return Model.pipExpression("move", { window: "address:" + pipFixture.PLAYER_ADDRESS, x: value, y: 0 }) }),
  pipFixture.HOSTILE_COORDS.map(function () { return "" }))
check("PIP7: the only strings that pass are the compile-time constants", [
  Model.pipExpression("tag", { window: "address:" + pipFixture.PLAYER_ADDRESS, tag: "+default-opacity" }),
  Model.pipExpression("tag", { window: "address:" + pipFixture.PLAYER_ADDRESS, tag: "+iptv-pip\", x = os.time(), y = \"1" }),
  Model.pipExpression("zorder", { window: "address:" + pipFixture.PLAYER_ADDRESS, mode: "bottom" }),
  Model.pipExpression("nosuchverb", { window: "address:" + pipFixture.PLAYER_ADDRESS }),
  Model.pipExpression("constructor", { window: "address:" + pipFixture.PLAYER_ADDRESS }),
  // D-PIP-5: this row used to be the ONE selector that was not an address,
  // and it named an app id rather than a window. It is refused now, by the
  // same builder and for the same reason every other value here is.
  Model.pipExpression("focus", { window: "class:omarchy-iptv" }),
  Model.pipExpression("focus", { window: "address:" + pipFixture.PLAYER_ADDRESS })
], ["", "", "", "", "", "", "hl.dsp.focus({ window = \"address:0x559c6893d940\" })"])
// The one playlist-derived value with an obvious route in: a channel name. It
// has no parameter to arrive through, and this says so out loud.
check("PIP7: nothing playlist-derived can reach a dispatch vector",
  Model.pipDispatchArgv("tag", { window: "address:" + pipFixture.PLAYER_ADDRESS, tag: "+Sky Sports Main Event" }), [])
check("PIP7: the address pattern accepts the live address and nothing adjacent to it",
  [pipFixture.PLAYER_ADDRESS, "0x0", "0x1234567890abcdef", "0x1234567890abcdef0", "0X10", "0x10 ", " 0x10"].map(function (value) { return Model.pipAddressSelector(value) }),
  ["address:0x559c6893d940", "address:0x0", "address:0x1234567890abcdef", "", "", "", ""])

// ---- 2. settings (section 6)

check("pipOptions accepts all four corners and falls back for anything else",
  ["top-right", "top-left", "bottom-right", "bottom-left", "TOP-LEFT", "  bottom-right  ", "middle", "", null, 7].map(function (v) { return Model.pipOptions({ pipCorner: v }).corner }),
  ["top-right", "top-left", "bottom-right", "bottom-left", "top-left", "bottom-right", "top-right", "top-right", "top-right", "top-right"])
check("pipOptions clamps the width percentage to the manifest range",
  [0, 14, 15, 30, 60, 61, 1e9, "abc", null, undefined, -5, "45"].map(function (v) { return Model.pipOptions({ pipSizePercent: v }).sizePercent }),
  [15, 15, 15, 30, 60, 60, 60, 30, 30, 30, 15, 45])
check("pipOptions clamps the margin the same way",
  [-1, 0, 16, 200, 201, 1e9, "abc", null, undefined].map(function (v) { return Model.pipOptions({ pipMargin: v }).margin }),
  [0, 0, 16, 200, 200, 200, 16, 16, 16])
check("R2: pipOptions is the ONE reading of the three PiP settings, and settingsFrom goes through it", (function () {
  const raw = { pipCorner: "BOTTOM-LEFT", pipSizePercent: 1e9, pipMargin: -4 }
  const s = Model.settingsFrom(raw)
  const o = Model.pipOptions(raw)
  return [s.pipCorner === o.corner, s.pipSizePercent === o.sizePercent, s.pipMargin === o.margin, s.pipCorner, s.pipSizePercent, s.pipMargin]
})(), [true, true, true, "bottom-left", 60, 0])

// ---- 3. geometry (4.4). The only place multi-monitor correctness can come
// from on a machine with one monitor.

// The monitor lookup the service asked lane V1 for in the handover and the
// design never named: the box goes on the monitor the WINDOW is on (4.9),
// which means `hyprctl -j monitors` looked up by the id the client entry
// carries. The fixture's eight monitors are ids 0..7, so a lookup that
// ignored the id and answered the first entry would place every box on the
// laptop panel - which is exactly what a single-monitor lane cannot see.
const pipMonitorList = JSON.stringify([pipFixture.MONITORS.live, pipFixture.MONITORS.hidpi, pipFixture.MONITORS.offset])
check("pipFindMonitor: the monitor the window is on, by id, from raw stdout or a parsed array", [
  Model.pipFindMonitor(pipMonitorList, 0).name,
  Model.pipFindMonitor(pipMonitorList, 1).name,
  Model.pipFindMonitor(pipMonitorList, 4).name,
  Model.pipFindMonitor(JSON.parse(pipMonitorList), 4).name,
  Model.pipFindMonitor(pipMonitorList, "4").name
], ["eDP-1", "DP-1", "HDMI-A-1", "HDMI-A-1", "HDMI-A-1"])
// Refusing is the whole point: a fallback to the first monitor is always
// right on a one-monitor machine and silently wrong on a two-monitor desk.
check("pipFindMonitor refuses rather than guessing a screen", [
  Model.pipFindMonitor(pipMonitorList, 9),
  Model.pipFindMonitor(pipMonitorList, -1),
  Model.pipFindMonitor(pipMonitorList, null),
  Model.pipFindMonitor(pipMonitorList, "not a monitor"),
  Model.pipFindMonitor("[]", 0),
  Model.pipFindMonitor("{not json", 0),
  Model.pipFindMonitor(null, 0),
  Model.pipFindMonitor('{"id":0}', 0),
  Model.pipFindMonitor([null, undefined, 7], 0)
], [null, null, null, null, null, null, null, null, null])
// And the pair the service actually runs: a window on monitor 4 is placed
// with monitor 4's own scale, reserved strip and global origin.
check("pipFindMonitor feeds pipGeometry the monitor the window is on, not the first one",
  Model.pipGeometry(Model.pipFindMonitor(pipMonitorList, 4), { corner: "bottom-left", sizePercent: 25, margin: 10 }),
  { x: 1930, y: 440, w: 480, h: 270 })

check("pipGeometry: every fixture box, on monitors that mostly do not exist here",
  pipFixture.GEOMETRY.map(function (row) { return row.why + " -> " + JSON.stringify(Model.pipGeometry(pipFixture.MONITORS[row.monitor], row.opts)) }),
  pipFixture.GEOMETRY.map(function (row) { return row.why + " -> " + JSON.stringify(row.box) }))
// Not just the numbers: the invariants every box must satisfy whatever the
// monitor. A box outside the usable rectangle is one under the bar or off the
// screen edge, and neither is visible in a unit test's output.
check("pipGeometry: every box is integral, even-sided and inside the usable rectangle",
  pipFixture.GEOMETRY.filter(function (row) { return row.box !== null }).map(function (row) {
    const m = pipFixture.MONITORS[row.monitor]
    const g = Model.pipGeometry(m, row.opts)
    const lw = Math.abs(m.transform % 2) === 1 ? Math.round(m.height / m.scale) : Math.round(m.width / m.scale)
    const lh = Math.abs(m.transform % 2) === 1 ? Math.round(m.width / m.scale) : Math.round(m.height / m.scale)
    const x0 = m.x + m.reserved[0] + row.opts.margin
    const y0 = m.y + m.reserved[1] + row.opts.margin
    const x1 = m.x + lw - m.reserved[2] - row.opts.margin
    const y1 = m.y + lh - m.reserved[3] - row.opts.margin
    return [g.x, g.y, g.w, g.h].every(function (v) { return typeof v === "number" && v === Math.floor(v) })
      && g.w % 2 === 0 && g.h % 2 === 0
      && g.x >= x0 && g.y >= y0 && g.x + g.w <= x1 && g.y + g.h <= y1
  }),
  pipFixture.GEOMETRY.filter(function (row) { return row.box !== null }).map(function () { return true }))
check("pipGeometry refuses a monitor it cannot measure rather than guessing",
  [null, undefined, {}, { width: 0, height: 768, scale: 1 }, { width: "abc", height: "x", scale: 1 }, { width: 1366, height: 768, scale: 0 }].map(function (m) { return Model.pipGeometry(m, { corner: "top-right", sizePercent: 30, margin: 16 }) }),
  [null, null, null, null, null, { x: 940, y: 16, w: 410, h: 230 }])
// A geometry that reached the builder must still be four integers in range.
check("pipBox is the gate between computed and dispatchable",
  [Model.pipBox({ x: 1, y: 2, w: 3, h: 4 }), Model.pipBox({ x: 1, y: 2, w: 0, h: 4 }), Model.pipBox({ x: 1e9, y: 2, w: 3, h: 4 }), Model.pipBox({ x: "1", y: 2, w: 3, h: 4 }), Model.pipBox(null)],
  [{ x: 1, y: 2, w: 3, h: 4 }, null, null, { x: 1, y: 2, w: 3, h: 4 }, null])

// ---- 4. resolving the window (4.2)

const pipClients = function (list) { return JSON.stringify(list) }
check("pipFindWindow: one match carries the window's whole state",
  Model.pipFindWindow(pipClients([pipFixture.CLIENTS.otherApp, pipFixture.CLIENTS.tiled]), pipFixture.PLAYER_PID),
  { ok: true, reason: "", address: pipFixture.PLAYER_ADDRESS, at: [690, 38], size: [650, 718], floating: false, pinned: false, monitor: 0, workspaceId: 1, tags: ["default-opacity"], pip: false })
// PLY-RST-11, reproduced: a user's own mpv --wayland-app-id=omarchy-iptv
// makes the class match twice. Floating, shrinking, pinning and moving a
// stranger's window is damage, not a nuisance.
check("PLY-RST-11: with a foreign window of the same class, the pid picks ours",
  Model.pipFindWindow(pipClients([pipFixture.CLIENTS.foreign, pipFixture.CLIENTS.tiled]), pipFixture.PLAYER_PID).address,
  pipFixture.PLAYER_ADDRESS)
check("pipFindWindow refuses rather than guessing", [
  Model.pipFindWindow(pipClients([pipFixture.CLIENTS.foreign]), pipFixture.PLAYER_PID).reason,
  Model.pipFindWindow(pipClients([pipFixture.CLIENTS.tiled, pipFixture.CLIENTS.twin]), pipFixture.PLAYER_PID).reason,
  Model.pipFindWindow(pipClients([]), pipFixture.PLAYER_PID).reason,
  Model.pipFindWindow(pipClients([pipFixture.CLIENTS.otherApp]), pipFixture.PLAYER_PID).reason,
  Model.pipFindWindow("{not json", pipFixture.PLAYER_PID).reason,
  Model.pipFindWindow(null, pipFixture.PLAYER_PID).reason,
  Model.pipFindWindow(pipClients([pipFixture.CLIENTS.tiled]), 0).reason,
  Model.pipFindWindow(pipClients([pipFixture.CLIENTS.tiled]), "not a pid").reason,
  Model.pipFindWindow(pipClients([pipFixture.CLIENTS.badAddress]), pipFixture.PLAYER_PID).reason
], ["no_window", "ambiguous", "no_window", "no_window", "bad_clients", "bad_clients", "no_pid", "no_pid", "bad_address"])
check("pipFindWindow takes an already-parsed array too, because the service has one",
  Model.pipFindWindow([pipFixture.CLIENTS.tiled], pipFixture.PLAYER_PID).address, pipFixture.PLAYER_ADDRESS)
// G-11: a rule-applied tag reads back with a trailing asterisk, a dispatched
// one does not. Without the strip, `default-opacity*` and `iptv-pip` would
// compare as different kinds of thing and the PiP tag could be missed.
check("4.2 rule 5: a trailing asterisk on a rule-applied tag is stripped, and ours is found either way", [
  Model.pipFindWindow(pipClients([pipFixture.CLIENTS.inPip]), pipFixture.PLAYER_PID).tags.join(","),
  Model.pipFindWindow(pipClients([pipFixture.CLIENTS.inPip]), pipFixture.PLAYER_PID).pip,
  Model.pipActive({ ok: true, floating: true, tags: ["iptv-pip*"] }),
  Model.pipActive({ ok: true, floating: true, tags: ["iptv-pip"] })
], ["default-opacity,iptv-pip", true, true, true])
// 4.8: a window the user popped themselves carries no tag of ours, so `p`
// reads it as "enter", not "exit".
check("4.8: the tag is what says the PiP is ours", [
  Model.pipActive(Model.pipFindWindow(pipClients([pipFixture.CLIENTS.userPopped]), pipFixture.PLAYER_PID)),
  Model.pipActive(Model.pipFindWindow(pipClients([pipFixture.CLIENTS.inPip]), pipFixture.PLAYER_PID)),
  Model.pipActive(Model.pipFindWindow(pipClients([pipFixture.CLIENTS.tiled]), pipFixture.PLAYER_PID)),
  // SUPER+T while in PiP: the tag survives but the window is tiled again, so
  // the next `p` puts it back in the corner rather than only clearing a tag.
  Model.pipActive({ ok: true, floating: false, pinned: false, tags: ["iptv-pip"] }),
  Model.pipActive({ ok: false, reason: "no_window", tags: ["iptv-pip"], floating: true })
], [false, true, false, false, false])
check("pipResolveIntent: an explicit mode wins, a toggle reads the live state", [
  Model.pipResolveIntent("on", { ok: true, floating: true, tags: ["iptv-pip"] }),
  Model.pipResolveIntent("off", { ok: true, floating: false, tags: [] }),
  Model.pipResolveIntent("toggle", { ok: true, floating: true, tags: ["iptv-pip"] }),
  Model.pipResolveIntent("toggle", { ok: true, floating: true, tags: [] }),
  Model.pipResolveIntent("", null)
], ["on", "off", "off", "on", "on"])

// ---- 4b. what the plugin REPORTS after a shell restart (4.7 step 3) ----
//
// D-PIP-4. The live pass found the window perfect and the report wrong:
// `status.pip.on` answered false on all THIRTY one-second samples while the
// box was demonstrably floating, pinned and carrying `iptv-pip`, the bar
// tooltip never gained its line, and the next accepted request replied
// `"was":false`. The window half worked because a request re-reads the
// compositor before it plans; the reporting half was never implemented.
//
// The driver below is the whole of what Service.qml does with that answer -
// the gate, the read, and `if (decided) pipOn = on` - and every decision in
// it is a CALL into the shipping functions rather than a copy of them
// (CLAUDE.md 12). `pipOn` starts false the way a process that has just
// started starts: set by nobody, because nobody was here to set it.
const pipFreshShell = function (reported) {
  return {
    pipOn: reported === true,
    pid: 0,
    busy: false,
    reading: false,
    // What the reattach path does the moment it learns the pid, and what
    // onPlayerAttached does again a moment later.
    peek: function (clients, pid) {
      if (pid !== undefined) this.pid = pid
      const gate = Model.pipDeriveGate({ pid: this.pid, busy: this.busy, reading: this.reading })
      if (!gate.ok) return gate.code
      const derived = Model.pipDeriveState(clients, this.pid, Model.PIP_CLASS)
      if (derived.decided) this.pipOn = derived.on
      return derived.decided ? "decided" : derived.reason
    }
  }
}
// THE case. A shell that has just started has no snapshot, no flag and no
// history of its own; the window is still in the corner from before it died.
checkCall("D-PIP-4: a shell with no memory at all reports the window it finds, not the false it woke up with", () => {
  const shell = pipFreshShell()
  const code = shell.peek(pipClients([pipFixture.CLIENTS.foreign, pipFixture.CLIENTS.inPip]), pipFixture.PLAYER_PID)
  // And the one surface a user sees it on: PIP2's single tooltip line.
  return [shell.pipOn, code, Model.barTooltip({ playing: true, name: "BBC One", pip: shell.pipOn }).split("\n")[1]]
}, [true, "decided", Model.PIP_TOOLTIP_ON])
// The other direction, which a remembered boolean also gets wrong: the user
// tiled the box with SUPER+T while this shell was dead.
checkCall("D-PIP-4: and follows the window back down, rather than a remembered true", () => {
  const shell = pipFreshShell(true)
  const code = shell.peek(pipClients([pipFixture.CLIENTS.tiled]), pipFixture.PLAYER_PID)
  return [shell.pipOn, code, Model.barTooltip({ playing: true, name: "BBC One", pip: shell.pipOn }).indexOf("\n")]
}, [false, "decided", -1])
// The property that says "derived, not remembered" in one line: the same
// bytes answer the same thing whatever this process happened to be saying a
// moment earlier. A cache, a flag or a last-known-good would break exactly
// this check and nothing else.
checkCall("D-PIP-4: the same read answers the same thing whatever the plugin said before it", () => {
  const inPip = pipClients([pipFixture.CLIENTS.inPip])
  const tiled = pipClients([pipFixture.CLIENTS.tiled])
  const a = pipFreshShell(false), b = pipFreshShell(true), c = pipFreshShell(false), d = pipFreshShell(true)
  a.peek(inPip, pipFixture.PLAYER_PID); b.peek(inPip, pipFixture.PLAYER_PID)
  c.peek(tiled, pipFixture.PLAYER_PID); d.peek(tiled, pipFixture.PLAYER_PID)
  return [a.pipOn, b.pipOn, c.pipOn, d.pipOn]
}, [true, true, false, false])
// `decided` is the honest half. A read that cannot see OUR window must not
// be turned into "off": that is the same defect pointing the other way.
checkCall("D-PIP-4: a read that saw nothing changes nothing", () => {
  const shell = pipFreshShell(true)
  const codes = [
    shell.peek("{not json", pipFixture.PLAYER_PID),
    shell.peek(pipClients([pipFixture.CLIENTS.foreign])),
    shell.peek(pipClients([pipFixture.CLIENTS.tiled, pipFixture.CLIENTS.twin])),
    shell.peek(pipClients([pipFixture.CLIENTS.badAddress]))
  ]
  return [codes, shell.pipOn]
}, [["bad_clients", "no_window", "ambiguous", "bad_address"], true])
// 4.2 again, one layer up: without the pid there is no read at all, because
// a class-only lookup is the defect D-PIP-5 is about. And a request owns the
// answer while it runs - its read is fresher and it is about to verify it.
checkCall("D-PIP-4: the gate on the read - no pid, no guess; a request in flight wins", () => [
  Model.pipDeriveGate({ pid: 0 }).code,
  Model.pipDeriveGate({ pid: -1 }).code,
  Model.pipDeriveGate({ pid: "not a pid" }).code,
  Model.pipDeriveGate(null).code,
  Model.pipDeriveGate({ pid: pipFixture.PLAYER_PID, busy: true }).code,
  Model.pipDeriveGate({ pid: pipFixture.PLAYER_PID, reading: true }).code,
  Model.pipDeriveGate({ pid: pipFixture.PLAYER_PID }).ok
], ["no_pid", "no_pid", "no_pid", "no_pid", "busy", "reading", true])
// And the structural half: there is nowhere to PUT a remembered value. The
// compositor's own bytes, the pid and the class are the whole input.
checkCall("D-PIP-4: the derivation takes the compositor's bytes and nothing else", () => [
  Model.pipDeriveState.length,
  Model.pipDeriveState(pipClients([pipFixture.CLIENTS.inPip]), pipFixture.PLAYER_PID, Model.PIP_CLASS).on,
  Model.pipDeriveState(pipClients([pipFixture.CLIENTS.userPopped]), pipFixture.PLAYER_PID, Model.PIP_CLASS).on,
  Model.pipDeriveState(pipClients([pipFixture.CLIENTS.inPip]), pipFixture.PLAYER_PID, Model.PIP_CLASS).address
], [3, true, false, pipFixture.PLAYER_ADDRESS])

// ---- 5. the plan (4.3 as PIP10 corrects it)

const pipLive = function (patch) {
  const base = { ok: true, address: pipFixture.PLAYER_ADDRESS, at: [690, 38], size: [650, 718], floating: false, pinned: false, tags: [] }
  for (const key in patch) base[key] = patch[key]
  return base
}
// Steps are compared by verb + the integers, which is what the order rule is
// about; the full expression text is pinned in section 1 above.
const pipVerbs = function (steps) {
  return steps.map(function (argv) {
    const expr = argv[2] || ""
    const call = expr.substring(0, expr.indexOf("("))
    const args = expr.replace(/^[^,]*/, "").replace(/ \}\)$/, "").replace(/^, /, "")
    return args === "" ? call : call + " " + args
  }).join(" | ")
}
const pipGeo = { x: 940, y: 42, w: 410, h: 230 }

check("4.3 enter from a tiled window: float, resize, move, pin, raise, tag",
  pipVerbs(Model.pipPlan(pipLive({}), null, pipGeo, "on")),
  "hl.dsp.window.float | hl.dsp.window.resize x = 410, y = 230 | hl.dsp.window.move x = 940, y = 42 | hl.dsp.window.pin | hl.dsp.window.alter_zorder mode = \"top\" | hl.dsp.window.tag tag = \"+iptv-pip\"")
// PIP10 is the whole point of these two: `action` is ignored, so a float step
// issued at an already-floating window would UNFLOAT it and a pin step at an
// already-pinned one would unpin it. The condition is the feature.
check("PIP10 enter from an already floating window: no float step, or it would unfloat it",
  pipVerbs(Model.pipPlan(pipLive({ floating: true }), null, pipGeo, "on")),
  "hl.dsp.window.resize x = 410, y = 230 | hl.dsp.window.move x = 940, y = 42 | hl.dsp.window.pin | hl.dsp.window.alter_zorder mode = \"top\" | hl.dsp.window.tag tag = \"+iptv-pip\"")
check("PIP10 enter from the user's own SUPER+O (floating AND pinned): neither toggle is issued",
  pipVerbs(Model.pipPlan(pipLive({ floating: true, pinned: true }), null, pipGeo, "on")),
  "hl.dsp.window.resize x = 410, y = 230 | hl.dsp.window.move x = 940, y = 42 | hl.dsp.window.alter_zorder mode = \"top\" | hl.dsp.window.tag tag = \"+iptv-pip\"")

const pipSnapFloating = { active: true, at: [300, 300], size: [900, 500], floating: true, pinned: false, monitor: 0, workspace: 1, v: 1 }
const pipSnapTiled = { active: true, at: [690, 38], size: [650, 718], floating: false, pinned: false, monitor: 0, workspace: 1, v: 1 }
const pipInPip = pipLive({ floating: true, pinned: true, at: [940, 42], size: [410, 230], tags: ["iptv-pip"] })

check("4.3 exit to a window that was floating: untag, unpin, then put the rectangle back",
  pipVerbs(Model.pipPlan(pipInPip, pipSnapFloating, pipGeo, "off")),
  "hl.dsp.window.tag tag = \"-iptv-pip\" | hl.dsp.window.pin | hl.dsp.window.resize x = 900, y = 500 | hl.dsp.window.move x = 300, y = 300")
check("4.3 exit to a window that was tiled: untag, unpin, unfloat, and let the layout take it",
  pipVerbs(Model.pipPlan(pipInPip, pipSnapTiled, pipGeo, "off")),
  "hl.dsp.window.tag tag = \"-iptv-pip\" | hl.dsp.window.pin | hl.dsp.window.float")
check("4.5 exit with NO snapshot degrades to unpin and unfloat, never to stuck",
  [pipVerbs(Model.pipPlan(pipInPip, null, pipGeo, "off")),
   pipVerbs(Model.pipPlan(pipInPip, { active: false, v: 1 }, pipGeo, "off")),
   pipVerbs(Model.pipPlan(pipInPip, "{not json", pipGeo, "off"))],
  ["hl.dsp.window.tag tag = \"-iptv-pip\" | hl.dsp.window.pin | hl.dsp.window.float",
   "hl.dsp.window.tag tag = \"-iptv-pip\" | hl.dsp.window.pin | hl.dsp.window.float",
   "hl.dsp.window.tag tag = \"-iptv-pip\" | hl.dsp.window.pin | hl.dsp.window.float"])
check("4.8 exit after the user unfloated it themselves: no float toggle, or PiP would come back",
  pipVerbs(Model.pipPlan(pipLive({ floating: false, pinned: false, tags: ["iptv-pip"] }), pipSnapTiled, pipGeo, "off")),
  "hl.dsp.window.tag tag = \"-iptv-pip\"")
check("4.8 exit after the user unpinned it themselves: no unpin step",
  pipVerbs(Model.pipPlan(pipLive({ floating: true, pinned: false, tags: ["iptv-pip"] }), pipSnapTiled, pipGeo, "off")),
  "hl.dsp.window.tag tag = \"-iptv-pip\" | hl.dsp.window.float")
check("4.8 exit when the window was ALREADY pinned before PiP: we unpin only what we pinned",
  pipVerbs(Model.pipPlan(pipInPip, { active: true, at: [300, 300], size: [900, 500], floating: true, pinned: true, v: 1 }, pipGeo, "off")),
  "hl.dsp.window.tag tag = \"-iptv-pip\" | hl.dsp.window.resize x = 900, y = 500 | hl.dsp.window.move x = 300, y = 300")
// The ordering rule, stated as a rule rather than trusted to the five cases
// above: pin never comes after float in any exit plan, on any input.
check("4.3 order: unpin ALWAYS precedes unfloat, because unfloating a pinned window clears the pin itself",
  [pipSnapFloating, pipSnapTiled, null, { active: false }].map(function (snap) {
    return [true, false].map(function (floating) {
      return [true, false].map(function (pinned) {
        const steps = pipVerbs(Model.pipPlan(pipLive({ floating: floating, pinned: pinned, tags: ["iptv-pip"] }), snap, pipGeo, "off"))
        const pin = steps.indexOf("hl.dsp.window.pin")
        const unfloat = steps.indexOf("hl.dsp.window.float")
        return pin === -1 || unfloat === -1 || pin < unfloat
      }).join("")
    }).join("")
  }).join(" "),
  "truetruetruetrue truetruetruetrue truetruetruetrue truetruetruetrue")
check("pipPlan emits nothing at all rather than half a plan", [
  Model.pipPlan({ ok: false, reason: "no_window" }, null, pipGeo, "on").length,
  Model.pipPlan(pipLive({ address: "0xnope" }), null, pipGeo, "on").length,
  Model.pipPlan(pipLive({}), null, null, "on").length,
  Model.pipPlan(pipLive({}), null, { x: 1e9, y: 0, w: 10, h: 10 }, "on").length,
  Model.pipPlan(null, null, pipGeo, "on").length,
  // The bound design 4.10 sets: at most 8 steps, ever.
  Model.pipPlan(pipLive({}), null, pipGeo, "on").length <= 8
], [0, 0, 0, 0, 0, true])
// A snapshot arrives from the player over a socket. Every field is
// re-validated before any of it can reach an expression.
check("4.5 a snapshot with a hostile or unusable field degrades the exit instead of dispatching it",
  [{ active: true, at: ["0x1\"); os.execute(\"x", 0], size: [410, 230], floating: true },
   { active: true, at: [1.5, 2], size: [410, 230], floating: true },
   { active: true, at: [1, 2], size: [1e9, 230], floating: true },
   { active: true, at: [1, 2], size: [0, 0], floating: true },
   { active: true, at: [1], size: [410, 230], floating: true },
   { active: true, floating: true }].map(function (snap) { return pipVerbs(Model.pipPlan(pipInPip, snap, pipGeo, "off")) }),
  ["hl.dsp.window.tag tag = \"-iptv-pip\" | hl.dsp.window.pin | hl.dsp.window.float",
   "hl.dsp.window.tag tag = \"-iptv-pip\" | hl.dsp.window.pin | hl.dsp.window.float",
   "hl.dsp.window.tag tag = \"-iptv-pip\" | hl.dsp.window.pin | hl.dsp.window.float",
   "hl.dsp.window.tag tag = \"-iptv-pip\" | hl.dsp.window.pin | hl.dsp.window.float",
   "hl.dsp.window.tag tag = \"-iptv-pip\" | hl.dsp.window.pin | hl.dsp.window.float",
   "hl.dsp.window.tag tag = \"-iptv-pip\" | hl.dsp.window.pin | hl.dsp.window.float"])

// ---- 6. the snapshot (4.5)

check("pipSnapshotFor records what the window WAS, from a live read",
  Model.pipSnapshotFor(Model.pipFindWindow(pipClients([pipFixture.CLIENTS.tiled]), pipFixture.PLAYER_PID)),
  { active: true, at: [690, 38], size: [650, 718], floating: false, pinned: false, monitor: 0, workspace: 1, v: 1 })
check("pipSnapshotFor of a floating window keeps the rectangle to put back",
  Model.pipSnapshotFor(Model.pipFindWindow(pipClients([pipFixture.CLIENTS.userPopped]), pipFixture.PLAYER_PID)),
  { active: true, at: [300, 300], size: [900, 500], floating: true, pinned: true, monitor: 0, workspace: 1, v: 1 })
check("a window whose rectangle cannot be read is recorded as tiled, so the restore degrades instead of moving it to 0,0",
  Model.pipSnapshotFor({ ok: true, floating: true, pinned: false, at: null, size: null, monitor: 0, workspaceId: 1 }).floating, false)
check("pipSnapshotClear says off and nothing else", Model.pipSnapshotClear(), { active: false, v: 1 })
check("pipParseSnapshot: what comes back out of the player, re-validated", [
  Model.pipParseSnapshot(pipSnapFloating).at.join(","),
  Model.pipParseSnapshot(JSON.stringify(pipSnapFloating)).size.join(","),
  Model.pipParseSnapshot({ active: false, v: 1 }),
  Model.pipParseSnapshot(null),
  Model.pipParseSnapshot("not json"),
  Model.pipParseSnapshot([1, 2, 3]),
  Model.pipParseSnapshot({ active: true, at: [1, 2], size: [3, 4] }).floating
], ["300,300", "900,500", null, null, null, null, false])

// ---- 7. the mpv half (4.6)

check("pipMpvCommands on: stop mpv resizing the box, and write the snapshot",
  Model.pipMpvCommands("on", { live: Model.pipFindWindow(pipClients([pipFixture.CLIENTS.tiled]), pipFixture.PLAYER_PID) }),
  [["set_property", "auto-window-resize", false],
   ["set_property", "user-data/omarchy-iptv-pip", { active: true, at: [690, 38], size: [650, 718], floating: false, pinned: false, monitor: 0, workspace: 1, v: 1 }]])
check("pipMpvCommands off: restore the user's own value, and clear the snapshot",
  Model.pipMpvCommands("off", { mpvArgs: "--no-auto-window-resize --profile=low-latency" }),
  [["set_property", "auto-window-resize", false], ["set_property", "user-data/omarchy-iptv-pip", { active: false, v: 1 }]])
check("pipRestoreAutoResize derives the restore value from the user's own mpvArgs",
  ["", "--profile=low-latency", "--auto-window-resize=no", "--auto-window-resize=yes", "--auto-window-resize=false",
   "--auto-window-resize=true", "--auto-window-resize=0", "--auto-window-resize=1", "--no-auto-window-resize",
   "--auto-window-resize", "--auto-window-resize=no --auto-window-resize=yes", "--no-auto-window-resize --auto-window-resize=yes",
   "--auto-window-resize-nonsense=no", null, undefined].map(function (v) { return Model.pipRestoreAutoResize(v) }),
  [true, true, false, true, false, true, false, true, false, true, true, true, true, true, true])
check("pipRestoreAutoResize takes a token array too", Model.pipRestoreAutoResize(["--no-auto-window-resize"]), false)

// ---- 8. mpv replies (4.5)

check("parsePlayerReply tells a reply from an event, and never throws", [
  Model.parsePlayerReply("{\"error\":\"success\",\"data\":{\"active\":true},\"request_id\":42}"),
  Model.parsePlayerReply("{\"error\":\"property not found\",\"request_id\":7}"),
  Model.parsePlayerReply("{\"event\":\"start-file\",\"playlist_entry_id\":3}"),
  Model.parsePlayerReply("{\"event\":\"end-file\",\"error\":\"success\"}"),
  Model.parsePlayerReply("not json at all"),
  Model.parsePlayerReply(""),
  Model.parsePlayerReply(null),
  Model.parsePlayerReply("[1,2,3]"),
  Model.parsePlayerReply("{\"error\":\"success\"}")
], [
  { ok: true, requestId: 42, error: "success", data: { active: true } },
  { ok: false, requestId: 7, error: "property not found", data: null },
  null, null, null, null, null, null,
  { ok: true, requestId: null, error: "success", data: null }
])

// ---- 9. PIP11: the only definition of success in this feature
//
// The compositor answers rc 0 `ok` for a dispatch aimed at a window that does
// not exist - all four verbs, measured - and reports a real refusal as
// `warning:` text on stdout with rc 0. So nothing may conclude "it worked"
// from an exit status. These are the checks that make that concrete.

check("PIP11: a dispatch reply is read as a keyword, never as prose", [
  Model.pipDispatchAccepted("ok"), Model.pipDispatchAccepted("ok\n"), Model.pipDispatchAccepted(" ok "),
  Model.pipDispatchAccepted("warning: =[C]:-1: Window does not qualify to be pinned"),
  Model.pipDispatchAccepted("warning: =[C]:-1: hl.focus: window not found"),
  Model.pipDispatchAccepted("error: attempt to call a nil value"),
  // The reason it is an equality and not a search: a step whose output
  // carries BOTH is a refusal, and "does it contain ok" would call it a
  // success. It judges ONE step's output - the batched `ok\n\n\nok` of G-7
  // is deliberately not accepted, because this design dispatches one step at
  // a time and reads the state back afterwards either way.
  Model.pipDispatchAccepted("ok\nwarning: =[C]:-1: Window does not qualify to be pinned"),
  Model.pipDispatchAccepted("ok\n\n\nok"),
  Model.pipDispatchAccepted(""), Model.pipDispatchAccepted(null)
], [true, true, true, false, false, false, false, false, false, false])
check("PIP11: success means the window looks like what was asked for", [
  Model.pipVerify(Model.pipFindWindow(pipClients([pipFixture.CLIENTS.inPip]), pipFixture.PLAYER_PID), "on", pipGeo),
  // The stale-address case: every step answered `ok` and nothing moved.
  Model.pipVerify(Model.pipFindWindow(pipClients([]), pipFixture.PLAYER_PID), "on", pipGeo),
  Model.pipVerify(pipLive({ floating: true, pinned: true, at: [940, 42], size: [410, 230], tags: [] }), "on", pipGeo),
  Model.pipVerify(pipLive({ floating: false, pinned: false, tags: ["iptv-pip"] }), "on", pipGeo),
  Model.pipVerify(pipLive({ floating: true, pinned: false, tags: ["iptv-pip"] }), "on", pipGeo),
  Model.pipVerify(pipLive({ floating: true, pinned: true, at: [932, 42], size: [410, 230], tags: ["iptv-pip"] }), "on", pipGeo),
  Model.pipVerify(pipLive({ floating: true, pinned: true, at: [940, 42], size: [600, 338], tags: ["iptv-pip"] }), "on", pipGeo),
  Model.pipVerify(pipInPip, "on", null)
], [
  { ok: true, reason: "" }, { ok: false, reason: "no_window" }, { ok: false, reason: "not_tagged" },
  { ok: false, reason: "not_floating" }, { ok: false, reason: "not_pinned" },
  { ok: false, reason: "wrong_position" }, { ok: false, reason: "wrong_size" }, { ok: false, reason: "bad_geometry" }
])
check("PIP11: and on the way out, that it went back where it came from", [
  Model.pipVerify(pipLive({ floating: false, pinned: false, tags: ["default-opacity"] }), "off", pipSnapTiled),
  Model.pipVerify(pipLive({ floating: true, pinned: false, at: [300, 300], size: [900, 500], tags: [] }), "off", pipSnapFloating),
  Model.pipVerify(pipLive({ floating: true, pinned: true, at: [940, 42], size: [410, 230], tags: ["iptv-pip"] }), "off", pipSnapTiled),
  Model.pipVerify(pipLive({ floating: true, pinned: false, tags: [] }), "off", pipSnapTiled),
  Model.pipVerify(pipLive({ floating: false, pinned: false, tags: [] }), "off", pipSnapFloating),
  Model.pipVerify(pipLive({ floating: true, pinned: false, at: [1, 1], size: [900, 500], tags: [] }), "off", pipSnapFloating),
  Model.pipVerify(pipLive({ floating: false, pinned: true, tags: [] }), "off", null)
], [
  { ok: true, reason: "" }, { ok: true, reason: "" }, { ok: false, reason: "still_tagged" },
  { ok: false, reason: "still_floating" }, { ok: false, reason: "not_restored" },
  { ok: false, reason: "wrong_position" }, { ok: false, reason: "still_pinned" }
])

// ---- 10. copy and the key (section 5)

check("section 5: every footer line, and nothing invented for a code that is not one",
  ["on", "off", "nothing_playing", "no_compositor", "no_window", "dispatch_failed", "", "wrong_size", "constructor", "toString"].map(function (c) { return Model.pipStatusText(c) }),
  ["Picture in picture on", "Picture in picture off", "Nothing playing", "Picture in picture needs Hyprland",
   "Cannot find the player window", "Hyprland refused the window change", "", "", "", ""])
// PIP9: the honest description is a small window that follows you. No copy in
// this feature may say "on top", because the compositor has no such state.
check("PIP9: no line in this feature promises always-on-top",
  ["on", "off", "nothing_playing", "no_compositor", "no_window", "dispatch_failed"].map(function (c) { return Model.pipStatusText(c) })
    .concat([Model.PIP_TOOLTIP_ON])
    .filter(function (line) { return /on top|above|always/i.test(line) }), [])
check("a verdict becomes exactly one of the six codes",
  [Model.pipResultCode({ ok: true }, "on"), Model.pipResultCode({ ok: true }, "off"),
   Model.pipResultCode({ ok: false, reason: "no_window" }, "on"), Model.pipResultCode({ ok: false, reason: "ambiguous" }, "on"),
   Model.pipResultCode({ ok: false, reason: "bad_address" }, "on"), Model.pipResultCode({ ok: false, reason: "wrong_position" }, "on"),
   Model.pipResultCode({ ok: false, reason: "not_tagged" }, "off"), Model.pipResultCode(null, "on")].map(function (c) { return c + "=" + Model.pipStatusText(c) }),
  ["on=Picture in picture on", "off=Picture in picture off", "no_window=Cannot find the player window",
   "no_window=Cannot find the player window", "no_window=Cannot find the player window",
   "dispatch_failed=Hyprland refused the window change", "dispatch_failed=Hyprland refused the window change",
   "dispatch_failed=Hyprland refused the window change"])
check("4.10: the two refusals the guide answers by itself, before anything is dispatched", [
  Model.pipKeyRequest({ available: false, playing: true }),
  Model.pipKeyRequest({ available: true, playing: false }),
  Model.pipKeyRequest({ available: true, playing: true }),
  Model.pipKeyRequest(null),
  Model.pipKeyRequest({})
], [
  { ok: false, code: "no_compositor", text: "Picture in picture needs Hyprland" },
  { ok: false, code: "nothing_playing", text: "Nothing playing" },
  { ok: true, code: "", text: "" },
  { ok: false, code: "no_compositor", text: "Picture in picture needs Hyprland" },
  { ok: false, code: "no_compositor", text: "Picture in picture needs Hyprland" }
])
// CLAUDE.md 12: this mapping used to be a chain of comparisons inside
// Guide.qml, where no test could reach it. The guide now dispatches on the
// answer, so `p` is exercised for real here.
check("the list-mode letters, including the new one",
  ["f", "F", "s", "S", "r", "R", "p", "P", "/", "o", "O", "a", "x", "", "pp", "1", null, undefined].map(function (t) { return Model.listLetterAction(t) }),
  ["favorite", "favorite", "stop", "stop", "refresh", "refresh", "pip", "pip", "search", "sources", "sources", "", "", "", "", "", "", ""])
check("section 5: the bar tooltip gains ONE line when PiP is on, and the glyph is untouched", [
  Model.barTooltip({ configured: true, playing: true, name: "Sky Sports Main Event", pip: true }),
  Model.barTooltip({ configured: true, playing: true, name: "Sky Sports Main Event", pip: false }),
  Model.barTooltip({ configured: true, pip: true }),
  // serviceMissing wins: with no service there is no PiP truth to report.
  Model.barTooltip({ serviceMissing: true, pip: true }),
  Model.barGlyph({ playing: true, pip: true }) === Model.barGlyph({ playing: true })
], [
  "Playing Sky Sports Main Event\nPicture in picture: on",
  "Playing Sky Sports Main Event",
  "IPTV" + SEP + "click to open the guide\nPicture in picture: on",
  "IPTV" + SEP + "service not loaded, run omarchy restart shell",
  true
])
check("section 5: `p pip` joins the list-mode hints, and is hidden where PiP cannot work", [
  Model.footerHints({ mode: "list" }).map(function (h) { return h[0] }).join(" "),
  Model.footerHints({ mode: "list", pipAvailable: true }).map(function (h) { return h[0] }).join(" "),
  Model.footerHints({ mode: "list", pipAvailable: false }).map(function (h) { return h[0] }).join(" "),
  Model.footerHints({ mode: "search", pipAvailable: true }).map(function (h) { return h[0] }).join(" ")
], [
  "j/k h/l Enter Space f s p r / o",
  "j/k h/l Enter Space f s p r / o",
  "j/k h/l Enter Space f s r / o",
  "Enter Up/Down Left/Right Tab Esc"
])

// ---- 11. the whole round trip, as the service will run it
//
// Not a new rule: the same functions, wired in the order Service.qml wires
// them, so a change that keeps every unit green while breaking the seam
// between two of them still fails. Two toggles must return the window to
// exactly the state it started in, which is also what the harness scenario
// (10.3) and PIP-02 assert on real windows.
check("the round trip: tiled -> PiP -> tiled, ending byte-identical to the start", (function () {
  const started = pipFixture.CLIENTS.tiled
  const live = Model.pipFindWindow(pipClients([pipFixture.CLIENTS.otherApp, started]), pipFixture.PLAYER_PID)
  const geo = Model.pipGeometry(pipFixture.MONITORS.live, Model.pipOptions({}))
  const snapshot = Model.pipSnapshotFor(live)
  const enter = Model.pipPlan(live, null, geo, "on")
  // What the compositor then reports, per the gate's own transcript.
  const afterOn = { ok: true, address: live.address, at: [geo.x, geo.y], size: [geo.w, geo.h], floating: true, pinned: true, monitor: 0, workspaceId: 1, tags: ["default-opacity", "iptv-pip"] }
  const onVerdict = Model.pipVerify(afterOn, "on", geo)
  const exit = Model.pipPlan(afterOn, snapshot, geo, "off")
  const afterOff = { ok: true, address: live.address, at: started.at, size: started.size, floating: false, pinned: false, monitor: 0, workspaceId: 1, tags: ["default-opacity"] }
  const offVerdict = Model.pipVerify(afterOff, "off", snapshot)
  return {
    enter: enter.length,
    on: Model.pipResultCode(onVerdict, "on"),
    exit: exit.length,
    off: Model.pipResultCode(offVerdict, "off"),
    back: afterOff.at.join(",") + " " + afterOff.size.join(",") + " " + afterOff.floating + " " + afterOff.pinned,
    // Not one argv item in either plan carries anything but the address,
    // integers and the constants (PIP7 / MR10: no URL, no channel name).
    urls: enter.concat(exit).filter(function (argv) { return /:\/\//.test(argv.join(" ")) }).length,
    // One argv item after `dispatch` in every step - the shape the focus
    // defect got wrong.
    clean: enter.concat(exit).every(function (argv) { return argv.length === 3 && argv[0] === "hyprctl" && argv[1] === "dispatch" })
  }
})(), { enter: 6, on: "on", exit: 3, off: "off", back: "690,38 650,718 false false", urls: 0, clean: true })

// ---- 12. the far side of the interface (CLAUDE.md: one rule, one fixture)
//
// These vectors are BUILT here and PARSED by scripts/dev-harness/stub-hyprctl.py,
// which is the fake the whole harness scenario drives the service against.
// Two implementations of one expression grammar, in two languages, written by
// two lanes - and until this fixture, nothing compared them: the node suite
// asserted the builder against strings written in this file, the python suite
// asserted the fake against strings written in that one, and both would stay
// green with the two halves unable to speak to each other. Only the live
// harness half would have noticed, and it needs a display.
//
// tests/test_pip.py replays exactly these vectors through the stub and
// asserts the window lands on `after`.
const pipDispatch = JSON.parse(require("fs").readFileSync(require("path").join(__dirname, "fixtures/pip-dispatch.json"), "utf8"))
const pipDispatchLive = Model.pipFindWindow([pipDispatch.window], pipDispatch.playerPid)
check("the shared dispatch fixture: the geometry both suites run is the one pipGeometry computes",
  Model.pipGeometry(pipDispatch.monitor, Model.pipOptions({})), pipDispatch.enter.geometry)
check("the shared dispatch fixture: pipPlan emits the enter vectors the stub is replayed with",
  Model.pipPlan(pipDispatchLive, null, pipDispatch.enter.geometry, "on"), pipDispatch.enter.argv)
check("the shared dispatch fixture: and the exit vectors, tag then unpin then unfloat",
  Model.pipPlan(Model.pipFindWindow([Object.assign({}, pipDispatch.window, {
    at: pipDispatch.enter.after.at, size: pipDispatch.enter.after.size,
    floating: true, pinned: true, tags: pipDispatch.enter.after.tags
  })], pipDispatch.playerPid), pipDispatch.exit.snapshot, pipDispatch.enter.geometry, "off"),
  pipDispatch.exit.argv)
check("the shared dispatch fixture: the snapshot written at PiP-on is the one the exit is verified against",
  Model.pipSnapshotFor(pipDispatchLive), pipDispatch.exit.snapshot)

// The third copy of one string, and the one with teeth. The window class PiP
// matches on is the app-id the player is LAUNCHED with, and that flag is
// written in three places: here, in bin/omarchy-iptv's mirror, and in the
// finder. The first two are pinned to each other by player-argv.json; the
// finder was pinned to neither, so a renamed app-id would have left PiP
// answering "Cannot find the player window" for ever, silently, with every
// suite green. buildMpvArgv now builds the flag FROM the constant, and this
// is the assertion that says so.
check("one window class: the app-id the player is launched with is the class PiP looks for", (function () {
  const launched = Model.buildMpvArgv({ socketPath: "/run/user/1000/omarchy-iptv/mpv.sock", stateDir: "/state" })
  const flag = launched.filter(function (item) { return item.indexOf("--wayland-app-id=") === 0 })
  const fixtureFlags = playerFixture.mpvArgv.map(function (row) {
    return (row.argv || []).filter(function (item) { return item.indexOf("--wayland-app-id=") === 0 }).join("")
  })
  return {
    flag: flag.join(""),
    fromConstant: flag.join("") === "--wayland-app-id=" + Model.PIP_CLASS,
    // And the python mirror's own vectors carry the same value.
    fixture: fixtureFlags.filter(function (item) { return item !== "--wayland-app-id=" + Model.PIP_CLASS }),
    finds: Model.pipFindWindow([{ "class": Model.PIP_CLASS, pid: 7, address: "0x1", at: [0, 0], size: [2, 2], floating: false, pinned: false, monitor: 0, workspace: { id: 1 }, tags: [] }], 7).ok
  }
})(), { flag: "--wayland-app-id=omarchy-iptv", fromConstant: true, fixture: [], finds: true })

console.log("\n" + checks + " checks, " + failures + " failure(s)")
if (failures > 0) process.exit(1)
console.log("All Model.js tests passed.")
