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
check("filterChannels empty query keeps order", Model.filterChannels(channels, "", 2).rows.map(c => c.id), ["1", "2"])
check("filterChannels empty query total/truncated", (() => { const r = Model.filterChannels(channels, "", 2); return [r.total, r.truncated] })(), [7, true])
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
check("scopeIndex", [Model.scopeIndex(entries, "all"), Model.scopeIndex(entries, "g:UK"), Model.scopeIndex(entries, "zz")], [2, 4, -1])
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
check("copy is defensive on garbage state", Model.withMode({ mode: "weird", query: 5 }, "list"), { mode: "list", query: "5", scopeId: "all", restoreScopeId: "", cursorIndex: 0 })

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
  { version: 1, favorites: ["a"], recents: [{ id: "x", name: "X", at: 7 }], lastPlayed: { id: "x", name: "", at: 0 } })
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
const Q = (s) => "“" + s + "”"
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
check("footerHints search", Model.footerHints({ mode: "search", query: "" }).map(h => h[0]), ["Enter", "Up/Down", "Left/Right", "Tab", "Esc"])
check("footerHints search with query says clear/narrow", Model.footerHints({ mode: "search", query: "x" }).slice(2), [["Left/Right", "narrow"], ["Tab", "keys"], ["Esc", "clear"]])
check("footerHints list", Model.footerHints({ mode: "list" }).map(h => h[0]).join(" "), "j/k h/l Enter Space f s r /")
check("footerHints empty states", [Model.footerHints({ empty: "error" }), Model.footerHints({ empty: "loading" })], [[["r", "reload"], ["Esc", "close"]], [["Esc", "close"]]])

console.log("\n" + checks + " checks, " + failures + " failure(s)")
if (failures > 0) process.exit(1)
console.log("All Model.js tests passed.")
