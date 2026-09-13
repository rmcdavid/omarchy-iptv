// Unit tests for Model.js. Run: node tests/Model.test.js
// Console PASS/FAIL runner, nonzero exit on any failure (same style as the
// installed dell-power plugin, so QA can read either without a framework).
// ASCII only: non-ASCII expectations are written as \uXXXX escapes.
const Model = require("../Model.js")

let failures = 0
let checks = 0

function check(name, actual, expected) {
  checks++
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  if (a === e) {
    console.log("ok   " + name)
  } else {
    failures++
    console.log("FAIL " + name + "\n     got:  " + a + "\n     want: " + e)
  }
}

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
  { version: 2, cacheLayout: 0, favorites: ["a"], recents: [{ id: "x", name: "X", at: 7 }], lastPlayed: { id: "x", name: "", at: 0 }, sources: [] })
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
check("settingsFrom applies R2 clamps and trims", Model.settingsFrom(Model.findBarEntry(barConfig, "io.github.rmcdavid.iptv")),
  { playlistUrl: "http://x/y.m3u", epgUrl: "", refreshMinutes: 15, mpvArgs: "", showChannelName: false, maxRecents: 1, barLabelMaxWidth: 600 })
check("settingsFrom defaults", Model.settingsFrom({}), { playlistUrl: "", epgUrl: "", refreshMinutes: 360, mpvArgs: "", showChannelName: true, maxRecents: 10, barLabelMaxWidth: 180 })
check("settingsFrom null", Model.settingsFrom(null).refreshMinutes, 360)
check("clampSetting refreshMinutes range", [Model.clampSetting("refreshMinutes", 5), Model.clampSetting("refreshMinutes", 99999), Model.clampSetting("refreshMinutes", "abc")], [15, 1440, 360])
check("clampSetting barLabelMaxWidth range", [Model.clampSetting("barLabelMaxWidth", 10), Model.clampSetting("barLabelMaxWidth", 601)], [60, 600])
check("clampSetting unknown key passthrough", Model.clampSetting("nope", "v"), "v")

// ---- mpv ----
check("splitMpvArgs accepts options", Model.splitMpvArgs(" --profile=low-latency --hwdec=auto-safe --no-osc "), { args: ["--profile=low-latency", "--hwdec=auto-safe", "--no-osc"], rejected: [] })
check("splitMpvArgs rejects reserved and junk", Model.splitMpvArgs("--input-ipc-server=/x --title=y ; rm -rf --no-idle --cache=yes"), { args: ["--cache=yes"], rejected: ["--input-ipc-server=/x", "--title=y", ";", "rm", "-rf", "--no-idle"] })
check("splitMpvArgs rejects --script and --config-dir", Model.splitMpvArgs("--script=/e.lua --config-dir=/x --scripts=/y --input-ipc-client=fd://3").args, [])
check("splitMpvArgs empty", Model.splitMpvArgs(null), { args: [], rejected: [] })
check("splitMpvArgs is case-sensitive (D-QA-11)", Model.splitMpvArgs("--Profile=fast --HWDEC=auto --profile=fast"), { args: ["--profile=fast"], rejected: ["--Profile=fast", "--HWDEC=auto"] })
check("splitMpvArgs rejects --no- forms of every reserved option", Model.splitMpvArgs("--no-input-ipc-server --no-wayland-app-id --no-title --no-force-media-title --no-idle --no-script --no-scripts --no-config-dir --no-input-ipc-client").args, [])
check("headerArgs maps UA/referer and appends others", Model.headerArgs({ "User-Agent": "VLC", Referer: "http://r", "X-Token": "a,b" }), ["--user-agent=VLC", "--referrer=http://r", "--http-header-fields-append=X-Token: a,b"])
check("headerArgs drops unsafe", Model.headerArgs({ "Bad Name": "x", Ok: "line\nbreak" }), [])
const argv = Model.buildMpvArgv({ socketPath: "/run/user/1000/omarchy-iptv/mpv.sock", name: "BBC One", url: "--not-an-option", headers: {}, extraArgs: ["--profile=low-latency"] })
check("buildMpvArgv starts with mpv and ipc socket", argv.slice(0, 2), ["mpv", "--input-ipc-server=/run/user/1000/omarchy-iptv/mpv.sock"])
check("buildMpvArgv fixed options in order", argv.slice(2, 10), ["--wayland-app-id=omarchy-iptv", "--force-window=immediate", "--idle=no", "--keep-open=no", "--title=$>BBC One", "--force-media-title=BBC One", "--msg-level=all=error", "--ytdl=no"])
// S-01: mpv expands ${property} in --title; the "$>" raw marker keeps a
// playlist-controlled name literal. force-media-title is not expanded by mpv.
check("mpvWindowTitle prefixes the raw marker", [Model.MPV_RAW_PREFIX, Model.mpvWindowTitle("BBC One"), Model.mpvWindowTitle(null)], ["$>", "$>BBC One", "$>"])
check("buildMpvArgv title is never property-expanded (S-01)", (() => {
  const a = Model.buildMpvArgv({ socketPath: "/s", name: "${path} ${options/input-ipc-server}", url: "http://u:p@h.test/x" })
  return [a.indexOf("--title=$>${path} ${options/input-ipc-server}") !== -1, a.indexOf("--force-media-title=${path} ${options/input-ipc-server}") !== -1, a.filter(t => t.indexOf("--title=") === 0).length]
})(), [true, true, 1])
check("buildMpvArgv default name is prefixed too", Model.buildMpvArgv({ socketPath: "/s", url: "u" }).indexOf("--title=$>IPTV") !== -1, true)
check("buildMpvArgv user args can re-enable ytdl (last wins)", (() => { const a = Model.buildMpvArgv({ socketPath: "/s", name: "N", url: "u", extraArgs: ["--ytdl=yes"] }); return a.indexOf("--ytdl=no") < a.indexOf("--ytdl=yes") })(), true)
check("buildMpvArgv url after --", argv.slice(-2), ["--", "--not-an-option"])
check("buildMpvArgv extra args before --", argv.indexOf("--profile=low-latency") < argv.indexOf("--"), true)
check("buildMpvArgv headers before user args", (() => { const a = Model.buildMpvArgv({ socketPath: "/s", name: "N", url: "u", headers: { "User-Agent": "X" }, extraArgs: ["--cache=yes"] }); return a.indexOf("--user-agent=X") < a.indexOf("--cache=yes") })(), true)
check("buildMpvArgv null params", Model.buildMpvArgv(null).slice(-2), ["--", ""])
check("focusPlayerArgv", Model.focusPlayerArgv(), ["hyprctl", "dispatch", "focuswindow", "class:omarchy-iptv"])

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
check("footerHints list", Model.footerHints({ mode: "list" }).map(h => h[0]).join(" "), "j/k h/l Enter Space f s r / o")
check("footerHints empty states", [Model.footerHints({ empty: "error" }), Model.footerHints({ empty: "loading" })], [[["r", "reload"], ["Esc", "close"]], [["Esc", "close"]]])

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
check("sanitizeTyping still caps and strips controls", Model.sanitizeTyping("a bcdefgh", 4), "abcd")

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
check("emptyState is v2", Model.emptyState(), { version: 2, cacheLayout: 0, favorites: [], recents: [], lastPlayed: null, sources: [] })
check("cloneState carries sources and cacheLayout, applies the patch, forces the version", Model.cloneState({ version: 1, cacheLayout: 2, favorites: ["a"], sources: [recFile] }, { favorites: ["b"], version: 7 }), { version: 2, cacheLayout: 2, favorites: ["b"], recents: [], lastPlayed: null, sources: [recFile] })
check("cloneState copies the arrays", (() => { const src = { sources: [recFile] }; const out = Model.cloneState(src); out.sources.push(recNas); return src.sources.length })(), 1)
check("withCacheLayout", [Model.withCacheLayout(state4, 0).cacheLayout, Model.withCacheLayout(Model.emptyState(), 2).cacheLayout, Model.withCacheLayout(Model.emptyState(), 5).cacheLayout], [0, 2, 0])
check("parseState v1 -> v2 keeps favorites and recents, sources empty, cacheLayout 0", Model.parseState('{"version":1,"favorites":["t:bbc1.uk"],"recents":[{"id":"x","name":"X","at":1}],"lastPlayed":null}'), { version: 2, cacheLayout: 0, favorites: ["t:bbc1.uk"], recents: [{ id: "x", name: "X", at: 1 }], lastPlayed: null, sources: [] })
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
check("footerHints error empty state adds o sources when sources exist", [Model.footerHints({ empty: "error", sourcesExist: true }), Model.footerHints({ empty: "error", sourcesExist: false }), Model.footerHints({ empty: "loading", sourcesExist: true })], [[["r", "reload"], ["o", "sources"], ["Esc", "close"]], [["r", "reload"], ["Esc", "close"]], [["Esc", "close"]]])
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

console.log("\n" + checks + " checks, " + failures + " failure(s)")
if (failures > 0) process.exit(1)
console.log("All Model.js tests passed.")
