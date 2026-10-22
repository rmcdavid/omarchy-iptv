// tests/proto-paths.mjs -- D-SG-3 (ruling R30f), the probe both engines run.
//
// A playlist whose groups, names and tvg-ids are the names Object.prototype
// already answers to, and a state.json whose favourites, hidden groups,
// saved searches and source labels are the same names, driven through every
// browse and apply path the model has. `runProtoPaths(Model)` returns what
// came out; it does NOT assert, so the two callers judge the same object:
//   tests/Model.test.js runs it in a CHILD node process (tests/proto-run.mjs),
//     because a pollution it finds would otherwise poison every check after
//     it in the one process the suite shares;
//   tests/test_proto_v4.py runs it in Qt's own engine (tests/proto-v4.qml,
//     the qml runtime offscreen under an address-space limit), because node
//     is V8 and the shell is V4, and a test double more forgiving than the
//     real thing is rule 10's failure.
// Pure: no node API, no Qt API. ASCII only (CLAUDE.md rule 8).

export var PROTO_KEYS = ["__proto__", "constructor", "hasOwnProperty", "toString", "valueOf"]

function snapshot() {
  var names = Object.getOwnPropertyNames(Object.prototype).sort()
  var enumerable = []
  for (var k in {}) enumerable.push(k)
  return { names: names, enumerable: enumerable, keys: Object.keys(Object.prototype) }
}

function channelsFor(keys) {
  var out = [{ name: "News One", group: "News", tvgId: "news1", url: "http://cdn.example.test/news1.ts",
               logo: "https://logos.example.test/news1.png" }]
  for (var i = 0; i < keys.length; i++) {
    out.push({ name: keys[i], group: keys[i], tvgId: keys[i], url: "http://cdn.example.test/" + i + ".ts",
               logo: "https://" + keys[i] + "/" + i + ".png" })
  }
  return out
}

function stateFor(Model, keys) {
  var sources = []
  for (var i = 0; i < keys.length; i++) {
    var url = "http://p" + i + ".example.test/list.m3u"
    sources.push({ key: Model.sourceKey(url), url: url, epgUrl: "", kind: "http", label: keys[i],
                   labelCustom: true, origin: "guide", addedAt: 1, lastUsed: 1 + i, fetchedAt: 0,
                   channelCount: 0, groupCount: 0 })
  }
  var doc = {
    version: 2, cacheLayout: 2, sources: sources, activeKey: sources[0].key,
    // Each name as an id the state holds, and as the id the helper gives
    // the channel that carries it as its tvg-id.
    favorites: keys.concat(keys.map(function (k) { return "t:" + k })),
    recents: keys.concat(keys.map(function (k) { return "t:" + k })).map(function (k) { return { id: k, name: k, at: 1 } }),
    hiddenGroups: [],
    savedSearches: keys.map(function (k) { return { query: k, at: 1 } })
  }
  return Model.parseState(JSON.stringify(doc))
}

export function runProtoPaths(Model) {
  var before = snapshot()
  var keys = PROTO_KEYS
  var errors = []
  var out = {}
  function step(name, fn) {
    try { out[name] = fn() } catch (e) { errors.push(name + ": " + String(e && e.message || e)) }
  }
  // A channels.json the helper could have written, read the way the service
  // reads it.
  var raw = channelsFor(keys)
  var text = JSON.stringify({ version: 1, generatedAt: 1, channels: raw })
  var parsed = Model.parseChannels(text)
  var channels = Model.prepareChannels(parsed.channels)
  var st = stateFor(Model, keys)

  step("groups", function () { return Model.groupChannels(channels).map(function (g) { return [g.name, g.count] }) })
  step("surface", function () {
    var surface = Model.scopeSurface(channels, st)
    return [surface.axis.count, surface.entries.filter(function (r) { return r.kind === "group" })
      .map(function (r) { return [r.label, r.count] })]
  })
  step("scopes", function () {
    return keys.map(function (k) { return Model.channelsForScope(channels, Model.groupScopeId(k), st).length })
  })
  step("primaryGroups", function () { return channels.map(function (c) { return c.primaryGroup }) })
  step("names", function () { return channels.map(function (c) { return c.name }) })
  step("ids", function () { return Model.channelIds(raw) })
  step("schemeOneIds", function () { return Model.channelIds(raw, Model.CHANNEL_ID_SCHEME_LEGACY) })
  step("remap", function () { return Object.keys(Model.channelIdRemap(raw)).length })
  step("remapState", function () {
    var r = Model.remapStateIds(st, {})
    return [r.moved, r.state.favorites, r.state.recents.map(function (x) { return x.id })]
  })
  step("index", function () {
    var index = Model.indexById(channels)
    return keys.map(function (k) { return index[k] === undefined })
  })
  step("chno", function () { return Model.buildChnoIndex(channels).count })
  step("search", function () {
    return keys.map(function (k) { return Model.filterChannels(channels, k, 50, st.favorites).total })
  })
  step("saved", function () {
    return [st.savedSearches.length, Model.savedSearchChannels(channels, st.savedSearches).length,
            Model.channelsForScope(channels, Model.SCOPE_FAVORITES, st).length]
  })
  step("favorites", function () { return st.favorites })
  step("recentScope", function () { return Model.channelsForScope(channels, Model.SCOPE_RECENT, st).length })
  step("hide", function () {
    var s = st
    for (var i = 0; i < keys.length; i++) s = Model.toggleHiddenGroup(s, keys[i])
    var hidden = keys.map(function (k) { return Model.isGroupHidden(s, k) })
    var surface = Model.scopeSurface(channels, s)
    return [hidden, s.hiddenGroups, Model.browsableChannels(channels, s).length, surface.axis.count, surface.axis.hidden]
  })
  step("labels", function () { return Model.sourceViews(st, st.activeKey, 10, {}, false).map(function (v) { return v.label }) })
  step("uniqueLabel", function () { return keys.map(function (k) { return Model.uniqueLabel(k, st.sources) }) })
  step("logoSurvey", function () {
    var s = Model.logoSurvey(raw)
    return [s.withLogo, s.wouldContact, typeof s.wouldContact]
  })
  step("epg", function () {
    var map = Model.parseEpgNow(JSON.stringify({ version: 1, channels: { news1: { now: { title: "T", start: 1, stop: 2 } } } })).channels
    return [Model.epgCoverage(channels, map).matched, keys.map(function (k) { return Model.epgEntry(map, k) })]
  })
  step("failed", function () {
    var marks = Model.failedIndex(keys.map(function (k) { return { id: k, at: 100 } }))
    var plus = Model.withFailed(marks, "constructor", 5)
    var minus = Model.withoutFailed(plus, "__proto__")
    return [Object.keys(marks).length, Object.keys(plus).length, Object.keys(minus).length,
            Model.knownIdSet(channels)["constructor"] === undefined]
  })
  step("merge", function () {
    var m = Model.mergeForeignState(st, st, st, {})
    return [m.state.favorites.length, m.state.savedSearches.length, m.conflicts.length]
  })
  step("written", function () {
    // What the plugin writes: state.json through cloneState, the bar entry
    // through entryWith. Neither may carry a key it did not put there.
    return [Object.keys(JSON.parse(JSON.stringify(Model.cloneState(st, {})))).sort(),
            JSON.stringify(Model.entryWith({ id: "x" }, { sourceKey: "k" }))]
  })
  var after = snapshot()
  return {
    out: out,
    errors: errors,
    prototypeBefore: before,
    prototypeAfter: after,
    // The verdict both callers assert, computed here so they cannot disagree.
    prototypeUnchanged: JSON.stringify(before) === JSON.stringify(after) && after.enumerable.length === 0 && after.keys.length === 0
  }
}
