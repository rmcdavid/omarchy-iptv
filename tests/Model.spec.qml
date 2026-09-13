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

  function test_stopLadder() {
    // D-LIVE-17: quit -> SIGTERM -> SIGKILL, each after its grace period.
    compare(Model.STOP_QUIT_GRACE_MS, 2000)
    compare(Model.STOP_KILL_GRACE_MS, 2000)
    var step = Model.stopEscalation("")
    compare(step.action, "quit")
    compare(step.waitMs, 2000)
    step = Model.stopEscalation(step.action)
    compare(step.signal, 15)
    step = Model.stopEscalation(step.action)
    compare(step.signal, 9)
    compare(step.waitMs, 0)
    compare(Model.stopEscalation("kill").signal, 0)
    compare(Model.healthTick(0, true).skips, 1)
    compare(Model.healthTick(2, true).restart, true)
    compare(Model.healthTick(2, false).check, true)
  }

  function test_playlistWarnings() {
    // D-LIVE-18: one footer line, URL-free, empty without warnings.
    var status = Model.parseHelperStatus('{"ok": true, "kind": "playlist", "warnings": ["truncated to 50000 channels (500 entries skipped)", "see http://u:p@h.test/x"]}', "playlist")
    compare(Model.statusWarnings(status), ["truncated to 50000 channels (500 entries skipped)", "see h.test"])
    compare(Model.warningLine(Model.statusWarnings(status)), "Playlist warning: truncated to 50000 channels (500 entries skipped) (+1 more)")
    compare(Model.warningLine([]), "")
    compare(Model.statusWarnings({ ok: false, warnings: ["x"] }), [])
    compare(Model.footerStatus({ count: 50000, lastUpdated: "01:53", warning: "Playlist warning: x" }), "Playlist warning: x")
    compare(Model.footerStatus({ count: 5, playingName: "Arte", warning: "Playlist warning: x" }), Model.GLYPHS.play + " Arte" + Model.SEP + "s stop")
  }

  // ---- Sources (M2-01): the same vectors as tests/Model.test.js, proving
  // decodeURIComponent, encodeURIComponent, toLowerCase on IDN hosts, Date
  // arithmetic and object copies behave in the V4 engine.
  function test_sourceLimitsAndGlyphs() {
    compare(Model.LIMITS.url, 2048)
    compare(Model.LIMITS.label, 64)
    compare(Model.LIMITS.sources, 50)
    compare(Model.MASK, "****")
    compare(Model.STATE_VERSION, 2)
    compare(Model.SOURCE_KEYS.open, "o")
    compare(Model.GLYPHS.sources, "󰐑")
    compare(Model.GLYPHS.eye, "󰈈")
    compare(Model.GLYPHS.eyeOff, "󰈉")
    compare(Model.GLYPHS.check, "󰄬")
  }

  function test_validateSourceUrl() {
    var ok = Model.validateSourceUrl(" HTTP://Provider.Example.TEST:80/get.php?username=u&password=p ")
    compare(ok.ok, true)
    compare(ok.url, "http://provider.example.test/get.php?username=u&password=p")
    compare(ok.host, "provider.example.test")
    compare(Model.validateSourceUrl("https://iptv-org.github.io:443/iptv/countries/us.m3u#x").url, "https://iptv-org.github.io/iptv/countries/us.m3u")
    compare(Model.validateSourceUrl("http://u:p@h.test:8080/x?y=1").url, "http://u:p@h.test:8080/x?y=1")
    compare(Model.validateSourceUrl("http://[::1]:8080/list.m3u").host, "[::1]")
    compare(Model.validateSourceUrl("http://Bücher.EXAMPLE/list.m3u").url, "http://bücher.example/list.m3u")
    compare(Model.validateSourceUrl("file://host/srv/tv/a%20b.m3u").url, "/srv/tv/a b.m3u")
    compare(Model.validateSourceUrl("FILE:///srv/tv/local.m3u").kind, "file")
    compare(Model.validateSourceUrl("/srv/tv/local.m3u\n").url, "/srv/tv/local.m3u")
    compare(Model.validateSourceUrl("http://h.test/a b").url, "http://h.test/ab")
    compare(Model.validateSourceUrl("").code, "empty")
    compare(Model.validateSourceUrl("provider.test/list.m3u").code, "scheme")
    compare(Model.validateSourceUrl("javascript:alert(1)").code, "scheme")
    compare(Model.validateSourceUrl("http://h .test/").code, "invalid")
    compare(Model.validateSourceUrl("file:///%zz").code, "invalid")
    compare(Model.validateSourceUrl("~/tv/list.m3u").code, "relative_path")
    compare(Model.validateSourceUrl("/proc/self/environ").code, "unsafe_path")
    compare(Model.validateSourceUrl("http://h.test/" + new Array(2050).join("a")).code, "too_long")
    compare(Model.validateSourceUrl("", { kind: "epg" }).ok, true)
    compare(Model.validateSourceUrl("ftp://x", { kind: "epg" }).message, "EPG: start with http://, https://, or / for a local file")
    compare(Model.validateSourceUrl("ftp://x").message, "Start with http://, https://, or / for a local file")
    compare(Model.validateSourceUrl("/" + new Array(2100).join("x")).message, "Too long · max 2,048 characters")
  }

  function test_sourceKeysAndLabels() {
    compare(Model.sourceKey("https://iptv-org.github.io/iptv/countries/us.m3u"), "d5977d8a")
    compare(Model.sourceKey("http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts"), "d990c2e4")
    compare(Model.sourceKey("/srv/tv/local.m3u"), "b0eed9fb")
    compare(Model.allocateSourceKey([{ key: "d5977d8a", url: "http://other.test/" }], "https://iptv-org.github.io/iptv/countries/us.m3u"), "d5977d8a-2")
    compare(Model.sourceCacheDir("/c", "d5977d8a"), "/c/sources/d5977d8a")
    compare(Model.sourceCacheDir("/c", "../x"), "")
    compare(Model.deriveLabel("http://www.NAS.local:9981/x"), "nas.local:9981")
    compare(Model.deriveLabel("/home/dag/tv/channels.m3u"), "channels.m3u")
    compare(Model.uniqueLabel("tv.example.net", ["TV.example.net"]), "tv.example.net 2")
    compare(Model.validateLabel("provider", [{ id: "1", label: "Provider" }], "").code, "label_taken")
    compare(Model.validateLabel("provider", [{ id: "1", label: "Provider" }], "1").ok, true)
    compare(Model.validateLabel(new Array(66).join("x"), [], "").message, "Label too long · max 64 characters")
  }

  function test_maskUrl() {
    compare(Model.maskUrl("http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts"), "http://provider.example.test/get.php?username=****&password=****&type=m3u_plus&output=ts")
    compare(Model.maskUrl("http://u:p@h.test:8080/x?token=abc&flag"), "http://****@h.test:8080/x?token=****&flag")
    compare(Model.maskUrl("http://h.test/x?a=1#frag"), "http://h.test/x?a=****#****")
    compare(Model.maskUrl("https://iptv-org.github.io/iptv/countries/us.m3u"), "https://iptv-org.github.io/iptv/countries/us.m3u")
    compare(Model.maskUrl("/home/dag/tv/channels.m3u"), "/home/dag/tv/channels.m3u")
  }

  function test_xtreamUrls() {
    var x = Model.xtreamUrls("http://Provider.Example.TEST:8080/", "u", "p")
    compare(x.ok, true)
    compare(x.playlistUrl, "http://provider.example.test:8080/get.php?username=u&password=p&type=m3u_plus&output=ts")
    compare(x.epgUrl, "http://provider.example.test:8080/xmltv.php?username=u&password=p")
    compare(Model.xtreamUrls("https://h.test", "a b", "p&q").playlistUrl, "https://h.test/get.php?username=a%20b&password=p%26q&type=m3u_plus&output=ts")
    compare(Model.encodeQueryValue("a b!*'()~-._/@:+"), "a%20b%21%2A%27%28%29~-._%2F%40%3A%2B")
    compare(Model.xtreamUrls("h.test:8080", "u", "p").code, "server_scheme")
    compare(Model.xtreamUrls("http://h.test/get.php?x=1", "u", "p").code, "server_path")
    compare(Model.xtreamUrls("http://h.test", "u", "").code, "pass_empty")
    compare(Model.xtreamUrls({ server: "http://h.test", username: "u", password: "p" }).host, "h.test")
    compare(Model.validateXtream({ server: "", username: "u", password: "p" }).field, "server")
  }

  function test_sourceViewsAndCopy() {
    var now = Math.floor(new Date(2026, 8, 13, 21, 40).getTime() / 1000)
    var rec = { key: "d990c2e4", url: "http://tv.example.net:8080/get.php?username=u&password=p", epgUrl: "http://tv.example.net:8080/xmltv.php?username=u&password=p", kind: "http", label: "Provider", labelCustom: true, origin: "xtream", addedAt: 1, lastUsed: now - 600, fetchedAt: 2, channelCount: 1475, groupCount: 28 }
    var view = Model.sourceView(rec, "d990c2e4", now)
    compare(view.id, "d990c2e4")
    compare(view.kind, "xtream")
    compare(view.host, "tv.example.net:8080")
    compare(view.hasEpg, true)
    compare(view.active, true)
    compare(view.lastUsedText, "used 21:30")
    compare(view.url, undefined)
    compare(Model.sourceDetail(view, false), "active · tv.example.net:8080 · Xtream · 1,475 channels in 28 groups · EPG")
    compare(Model.sourceDetail(view, true), "active · used 21:30 · tv.example.net:8080 · Xtream · 1,475 channels in 28 groups · EPG")
    compare(Model.sourceAccessibleName(view), "Provider, tv.example.net:8080, 1,475 channels in 28 groups, active, EPG, last used 21:30")
    compare(Model.sourceView({ key: "b0eed9fb", url: "/srv/tv/local.m3u", kind: "file", lastUsed: 0, fetchedAt: 0 }, "", now).channelCount, -1)
    compare(Model.formatLastUsed(now - 86400, now), "used yesterday")
    compare(Model.formatLastUsed(Math.floor(new Date(2025, 8, 3, 10, 0).getTime() / 1000), now), "used 3 Sep 2025")
    compare(Model.formatLastUsed(0, now), "never used")
    compare(Model.sourcesHeaderCount(3), "3 sources")
    compare(Model.confirmRemoveMessage("NAS Tvheadend", false), "Remove “NAS Tvheadend”? Its cache is deleted too.")
    compare(Model.sourceErrorMessage("duplicate", { label: "Provider" }), "Already in Sources as “Provider”")
    compare(Model.fetchingLine("tv.example.net", "url"), "Fetching from tv.example.net…")
    compare(Model.sourceTransient("switched", { label: "NAS Tvheadend", channelCount: 84 }), "Switched to NAS Tvheadend · 84 channels")
    var views = Model.sourceViews({ sources: [rec, { key: "b0eed9fb", url: "/srv/tv/local.m3u", kind: "file", lastUsed: now, fetchedAt: 0 }] }, "b0eed9fb", now, {})
    compare(views[0].id, "b0eed9fb")
    compare(JSON.stringify(views).indexOf("://"), -1)
  }

  function test_stateV2AndReducers() {
    compare(Model.emptyState(), { version: 2, cacheLayout: 0, favorites: [], recents: [], lastPlayed: null, sources: [] })
    var v1 = Model.parseState('{"version":1,"favorites":["t:bbc1.uk"],"recents":[],"lastPlayed":null}')
    compare(v1.version, 2)
    compare(v1.favorites, ["t:bbc1.uk"])
    compare(v1.sources, [])
    var added = Model.addSource(Model.emptyState(), { playlistUrl: "HTTP://Provider.Example.TEST:80/get.php?username=u&password=p&type=m3u_plus&output=ts", label: "", origin: "xtream" }, 1000)
    compare(added.ok, true)
    compare(added.key, "d990c2e4")
    compare(added.state.sources[0].label, "provider.example.test")
    compare(Model.addSource(added.state, { playlistUrl: "http://provider.example.test/get.php?username=u&password=p&type=m3u_plus&output=ts" }).code, "duplicate")
    var round = Model.parseState(JSON.stringify(added.state))
    compare(round.sources.length, 1)
    compare(round.sources[0].key, "d990c2e4")
    compare(Model.recordPlayed(added.state, { id: "c1", name: "C" }, 10, 5).sources.length, 1)
    compare(Model.withFavorites(added.state, ["c1"]).sources.length, 1)
    var upd = Model.updateSource(added.state, "d990c2e4", { playlistUrl: "http://provider.example.test:8080/get.php?username=u&password=p&type=m3u_plus&output=ts" }, 2000)
    compare(upd.urlChanged, true)
    compare(upd.replacedKey, "d990c2e4")
    compare(upd.key, "85ac744a")
    compare(upd.state.sources.length, 2)
    compare(Model.removeSource(upd.state, "d990c2e4").state.sources.length, 1)
    var rec = Model.reconcileSources(Model.emptyState(), "https://iptv-org.github.io/iptv/countries/us.m3u", "", "", 5)
    compare(rec.added, "d5977d8a")
    compare(rec.state.sources[0].origin, "migrated")
    compare(Model.activeSourceKey(rec.state, "HTTPS://iptv-org.github.io:443/iptv/countries/us.m3u"), "d5977d8a")
    compare(Model.sourceForEdit(added.state, "d990c2e4").playlistMasked, "http://provider.example.test/get.php?username=****&password=****&type=m3u_plus&output=ts")
    compare(JSON.stringify(Model.sourcesSummary(added.state, "d990c2e4")).indexOf("://"), -1)
    compare(Model.entryWith({ id: "x", refreshMinutes: 30 }, { playlistUrl: "u" }), { id: "x", refreshMinutes: 30, playlistUrl: "u" })
    compare(Model.cacheStale({ ok: true, fetchedAt: 1000 }, 15, 1000 + 900), true)
    compare(Model.cacheStale({ ok: true, fetchedAt: 1000 }, 15, 1000 + 899), false)
  }

  function test_sourcesModesAndForms() {
    var g = Model.openFirstRun(Model.guideState("all"))
    compare(g.mode, "sourceEdit")
    compare(g.form.origin, "firstRun")
    compare(g.form.focus, "playlist")
    compare(Model.formFocusOrder(g.form, { savedSources: 2 }), ["playlist", "epg", "savedSources", "xtream", "load"])
    // paste masks at once, typing never masks mid-flight
    var pasted = Model.withFormValue(g, "playlist", "http://h.test/x?token=1")
    compare(Model.fieldMasked(pasted.form, "playlist"), true)
    var typed = Model.withFormValue(g, "playlist", "http://h.test/x?token=1", { typed: true })
    compare(Model.fieldMasked(typed.form, "playlist"), false)
    compare(Model.footerHints({ mode: "sourceEdit", form: pasted.form })[2], ["Ctrl+R", "reveal"])
    var revealed = Model.toggleReveal(pasted, "playlist")
    compare(revealed.form.revealed.playlist, true)
    compare(Model.footerHints({ mode: "sourceEdit", form: revealed.form })[2], ["Ctrl+R", "hide"])
    compare(Model.moveFormFocus(revealed, 1, {}).form.revealed.playlist, false)
    compare(Model.moveFormFocus(revealed, 1, {}).form.focus, "epg")
    compare(Model.toggleReveal(Model.withFormValue(g, "playlist", "http://h.test/x"), "playlist").form.revealed.playlist, false)
    // Esc: clear first, then close
    var esc = Model.onEscape(pasted)
    compare(esc.close, false)
    compare(esc.state.form.values.playlist, "")
    compare(Model.onEscape(esc.state).close, true)
    compare(Model.onEscape(Model.withFormProbing(pasted, true, { host: "h.test" })).cancelProbe, true)
    // Xtream from first run keeps the parent
    var x = Model.openXtreamForm(pasted)
    compare(x.mode, "sourceXtream")
    compare(x.form.parent.values.playlist, "http://h.test/x?token=1")
    compare(Model.onEscape(x).state.form.values.playlist, "http://h.test/x?token=1")
    // Sources from list mode and back
    var views = [{ id: "a", active: false }, { id: "b", active: true }]
    var s = Model.openSources(Model.withMode(Model.guideState("g:UK"), "list"), views)
    compare(s.mode, "sources")
    compare(s.returnMode, "list")
    compare(s.sourceCursor, 1)
    compare(Model.sourcesRowKind(2, 2), "add")
    compare(Model.sourcesRowKind(3, 2), "xtream")
    compare(Model.footerHints({ mode: "sources", cursorKind: "source" }).length, 7)
    var back = Model.onEscape(s).state
    compare(back.mode, "list")
    compare(back.scopeId, "g:UK")
    var add = Model.openAddForm(s)
    compare(add.form.focus, "playlist")
    compare(Model.closeForm(add, "saved").state.mode, "sources")
    compare(Model.closeForm(add, "saved").state.returnMode, "list")
    var rm = Model.startRemove(s, 2)
    compare(rm.mode, "confirmRemove")
    compare(Model.afterRemove(rm, 1).sourceCursor, 0)
    compare(Model.afterRemove(rm, 0).form.origin, "firstRun")
    // UX 1.7: the active source removed while Sources stays open, then Esc
    // -> the first-run form (Saved sources link), not the M1 empty state.
    var stayed = Model.afterRemove(rm, 1)
    compare(stayed.mode, "sources")
    var escUnconfigured = Model.onEscape(stayed, { configured: false })
    compare(escUnconfigured.close, false)
    compare(escUnconfigured.state.mode, "sourceEdit")
    compare(escUnconfigured.state.form.origin, "firstRun")
    compare(escUnconfigured.state.form.focus, "playlist")
    compare(escUnconfigured.state.returnMode, "")
    compare(Model.onEscape(stayed, { configured: true }).state.mode, "list")
    // SR11: a CLI `~` path reconciles and resolves as the active source.
    var tilde = Model.reconcileSources(Model.withCacheLayout(Model.emptyState(), 2), "~/list.m3u", "", "", 1)
    compare(tilde.invalid, null)
    compare(tilde.state.sources[0].kind, "file")
    compare(Model.activeSourceKey(tilde.state, "~/list.m3u"), tilde.added)
    compare(Model.addSource(tilde.state, { playlistUrl: "~/x.m3u" }).code, "relative_path")
    compare(Model.sourceTransient("added", { label: "list.m3u", host: "local file", channelCount: 20, groupCount: 9 }), "Added list.m3u · 20 channels in 9 groups")
    compare(Model.validateUrlForm({ label: "", playlist: "x.test/a", epg: "" }, [], "").error.code, "scheme")
    compare(Model.footerStatus({ configured: true, count: 84, lastUpdated: "09:12", activeLabel: "NAS", sourceCount: 2 }), "NAS · 84 channels · updated 09:12")
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
