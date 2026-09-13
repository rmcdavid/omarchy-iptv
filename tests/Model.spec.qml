import QtQuick
import QtTest
import "../Model.js" as Model

// Proves Model.js loads inside the Qt QML engine (no ES module syntax, no
// node-only globals) and that the QML-side results match the node tests:
// normalization vectors, ranking tiers, the two-mode keyboard state machine,
// scope transitions, the zap ring, settings clamps and mpv argv.
// Run: QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml
TestCase {
  name: "IptvModel"

  readonly property var channels: Model.prepareChannels([
    { id: "1", name: "BBC One HD", group: "UK", searchKey: "bbc one hd uk" },
    { id: "2", name: "CBBC", group: "Kids", searchKey: "cbbc kids" },
    { id: "3", name: "One America", group: "US", searchKey: "one america us" },
    { id: "4", name: "Sky News", group: "News", searchKey: "sky news news" },
    { id: "5", name: "BBC Two", group: "UK", searchKey: "bbc two uk" },
    { id: "6", name: "The One Show", group: "UK", searchKey: "the one show uk" },
    { id: "7", name: "Rai Uno", group: "One World", searchKey: "rai uno one world" }
  ])
  readonly property var userState: ({ version: 1, favorites: ["5", "1"], recents: [{ id: "4", name: "Sky News", at: 1 }], lastPlayed: null })

  function ids(rows) {
    var out = []
    for (var i = 0; i < rows.length; i++) out.push(rows[i].id)
    return out
  }

  function test_searchKey() {
    compare(Model.searchKey("BBC-One HD", "UK: News"), "bbc one hd uk news")
    compare(Model.searchKey("Télé Québec", ""), "tele quebec")
    compare(Model.searchKey("Kids TV", "Animation;Kids;Religious"), "kids tv animation kids religious")
  }

  function test_normalizeNfdAndScripts() {
    // String.prototype.normalize must exist in the Qt engine for NFD folding.
    compare(Model.normalizeText("Café NFD"), "cafe nfd")
    compare(Model.normalizeText("ÉCOLE"), "ecole")
    compare(Model.normalizeText("Первый канал"), "первый канал")
    compare(Model.normalizeText("NHK 総合"), "nhk 総合")
  }

  function test_fnv1a32() {
    compare(Model.fnv1a32(""), "811c9dc5")
    compare(Model.fnv1a32("a"), "e40c292c")
    compare(Model.fnv1a32("foobar"), "bf9cf968")
  }

  function test_channelId() {
    compare(Model.channelId({ tvgId: "bbc1.uk", url: "http://a" }), "t:bbc1.uk")
    compare(Model.channelId({ url: "foobar" }), "u:bf9cf968")
  }

  function test_displayNameNeverUrl() {
    var rows = Model.prepareChannels([{ name: "http://h.test/x", tvgName: "Arte", url: "http://h.test/x" }, { name: "", url: "u2" }])
    compare(rows[0].name, "Arte")
    compare(rows[1].name, "Channel 2")
  }

  function test_rankingTiers() {
    compare(ids(Model.filterChannels(channels, "one", 10).rows), ["3", "1", "6", "7"])
    // both BBC rows are favorites in userState: playlist order inside the tier
    compare(ids(Model.filterChannels(channels, "bbc", 10, userState).rows), ["1", "5", "2"])
    // a single favorite sorts first inside its tier, never above a better tier
    compare(ids(Model.filterChannels(channels, "bbc", 10, { favorites: ["5"] }).rows), ["5", "1", "2"])
    compare(ids(Model.filterChannels(channels, "bbc", 10, { favorites: ["2"] }).rows), ["1", "5", "2"])
    compare(ids(Model.filterChannels(channels, "bbc uk", 10).rows), ["1", "5"])
    // D-LIVE-01: the cap is for search results; an empty query browses every row.
    var browse = Model.filterChannels(channels, "", 2)
    compare(browse.total, 7)
    compare(browse.rows.length, 7)
    compare(browse.truncated, false)
    var capped = Model.filterChannels(channels, "b", 1)
    compare(capped.rows.length, 1)
    compare(capped.truncated, true)
    compare(Model.MAX_ROWS_DEFAULT, 200)
  }

  function test_ungroupedLastAndFallbackScope() {
    // D-LIVE-06: Ungrouped closes the column even when it appears first.
    var rows = Model.prepareChannels([{ name: "A", url: "1" }, { name: "B", group: "News", url: "2" }, { name: "C", group: "Kids", url: "3" }])
    var names = Model.groupChannels(rows).map(function(g) { return g.name })
    compare(names, ["News", "Kids", "Ungrouped"])
    // D-LIVE-07: an emptied Recent falls back to Favorites, else All.
    compare(Model.fallbackScope(Model.scopeEntries(channels, userState), "recent"), "recent")
    compare(Model.fallbackScope(Model.scopeEntries(channels, { version: 1, favorites: ["5"], recents: [], lastPlayed: null }), "recent"), "favorites")
    compare(Model.fallbackScope(Model.scopeEntries(channels, null), "recent"), "all")
  }

  function test_statusReasonTable() {
    // D-LIVE-03 / D-LIVE-11: terse reasons, no helper sentence, no seconds.
    compare(Model.statusReason({ ok: false, error: { code: "not_a_playlist", message: "source from h is not an M3U playlist" } }), "Not an M3U playlist")
    compare(Model.statusReason({ ok: false, error: { code: "timeout", message: "playlist download from h exceeded its deadline" } }), "Timed out")
    compare(Model.statusReason({ ok: false, error: { code: "network", message: "could not reach h: timed out" } }), "Timed out")
  }

  function test_scopeEntriesAndLists() {
    var entries = Model.scopeEntries(channels, userState)
    compare(entries[0].id, "recent")
    compare(entries[1].id, "favorites")
    compare(entries[1].count, 2)
    compare(entries[2].id, "all")
    compare(entries[3].kind, "header")
    compare(entries[4].id, "g:UK")
    compare(ids(Model.channelsForScope(channels, "favorites", userState)), ["5", "1"])
    compare(ids(Model.channelsForScope(channels, "g:UK", userState)), ["1", "5", "6"])
    compare(Model.moveScope(entries, "all", 1), "g:UK")
    compare(Model.moveScope(entries, "recent", -1), "g:One World")
    compare(Model.initialScope(channels, userState), "favorites")
    compare(Model.initialScope(channels, null), "all")
  }

  function test_keyboardStateMachine() {
    var g = Model.guideState("favorites")
    compare(g.mode, "search")
    g = Model.withQuery(g, "s")
    compare(g.scopeId, "all")
    compare(g.restoreScopeId, "favorites")
    g = Model.withQuery(g, "")
    compare(g.scopeId, "favorites")
    g = Model.toggleMode(g)
    compare(g.mode, "list")
    g = Model.withQuery(g, "bbc")
    var esc = Model.onEscape(g)
    compare(esc.close, false)
    compare(esc.state.query, "")
    compare(esc.state.mode, "list")
    esc = Model.onEscape(esc.state)
    compare(esc.close, true)
    compare(Model.withQuery(Model.guideState("g:UK"), "sky").scopeId, "g:UK")
    compare(Model.effectiveScope("recent", "x"), "all")
    compare(Model.moveCursor(0, -1, 5, true), 4)
    compare(Model.moveCursor(4, 10, 5, false), 4)
  }

  function test_zapRing() {
    compare(Model.launchScope("favorites", "", { group: "UK" }), "favorites")
    compare(Model.launchScope("recent", "", { group: "UK" }), "g:UK")
    compare(Model.launchScope("favorites", "sky", { group: "UK | SPORTS" }), "g:UK | SPORTS")
    compare(ids(Model.zapRing(channels, userState, { id: "5", group: "UK", launchedFrom: "favorites" })), ["5", "1"])
    compare(Model.nextInGroup(channels, "7", 1).id, "1")
    compare(Model.nextInGroup(channels, "1", -1).id, "7")
  }

  function test_state() {
    compare(Model.toggleFavorite(["a"], "b"), ["a", "b"])
    compare(Model.pushRecent([], { id: "x", name: "X" }, 10, 5), [{ id: "x", name: "X", at: 5 }])
    compare(Model.removeRecent({ version: 1, favorites: [], recents: [{ id: "x", name: "X", at: 1 }], lastPlayed: null }, "x").recents, [])
    compare(Model.parseState("garbage"), Model.emptyState())
  }

  function test_settingsClamps() {
    var s = Model.settingsFrom({ refreshMinutes: "5", barLabelMaxWidth: 9999, maxRecents: 0, playlistUrl: " http://x " })
    compare(s.refreshMinutes, 15)
    compare(s.barLabelMaxWidth, 600)
    compare(s.maxRecents, 1)
    compare(s.playlistUrl, "http://x")
    compare(Model.settingsFrom({}).refreshMinutes, 360)
    compare(Model.settingsFrom({}).barLabelMaxWidth, 180)
  }

  function test_mpvArgv() {
    var argv = Model.buildMpvArgv({ socketPath: "/tmp/s", name: "N", url: "http://u", extraArgs: [] })
    compare(argv[0], "mpv")
    compare(argv[argv.length - 2], "--")
    compare(argv[argv.length - 1], "http://u")
    compare(argv.indexOf("--title=$>N") !== -1, true)   // S-01: raw marker, never property-expanded
    compare(argv.indexOf("--force-media-title=N") !== -1, true)
    compare(Model.splitMpvArgs("--Profile=x --no-idle --cache=yes").args, ["--cache=yes"])
  }

  function test_privacy() {
    compare(Model.redactUrls("Failed to open http://u:p@h.test/x?y."), "Failed to open h.test")
    compare(Model.sourceLabel("http://u:p@tv.example.net:8080/get.php?u=1"), "http://tv.example.net")
    compare(Model.hostOf("/home/x/list.m3u"), "local file")
  }

  function test_columnAnchor() {
    // D-LIVE-16: pinned entries show the column from the top; groups are contained.
    var entries = Model.scopeEntries(channels, userState)
    var all = Model.columnAnchor(entries, "all")
    compare(all.index, 2)
    compare(all.top, true)
    var group = Model.columnAnchor(entries, "g:UK")
    compare(group.index, 4)
    compare(group.top, false)
    compare(Model.columnAnchor(entries, "g:Gone").index, -1)
    compare(Model.columnAnchor(null, "all").index, -1)
  }

  function test_formatting() {
    compare(Model.formatCount(1204), "1,204")
    compare(Model.epgFraction(150, 100, 200), 0.5)
    compare(Model.epgFields({ now: { title: "Old", start: 1, stop: 10 } }, 20).nowTitle, "")
    compare(Model.rowDetail({ showGroup: true, group: "UK", nowTitle: "X", nextTitle: "Y" }), "UK · Now: X · Next: Y")
    compare(Model.footerStatus({ count: 5, truncated: true, resultTotal: 1240, cap: 200 }), "First 200 of 1,240 · keep typing")
    compare(Model.barGlyph({ playing: true }), Model.GLYPHS.tvPlay)
  }
}
