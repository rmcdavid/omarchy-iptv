// Unit tests for Model.js. Run: node tests/Model.test.js
// Console PASS/FAIL runner, nonzero exit on any failure (same style as the
// installed dell-power plugin, so QA can read either without a framework).
const Model = require("../Model.js")

let failures = 0

function check(name, actual, expected) {
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  if (a === e) {
    console.log("ok   " + name)
  } else {
    failures++
    console.log("FAIL " + name + "\n     got:  " + a + "\n     want: " + e)
  }
}

// ---- normalization (shared vectors with tests/test_playlist.py) ----
check("searchKey folds punctuation and case", Model.searchKey("BBC-One HD", "UK: News"), "bbc one hd uk news")
check("searchKey folds diacritics", Model.searchKey("T\u00e9l\u00e9 Qu\u00e9bec", ""), "tele quebec")
check("searchKey keeps non-Latin scripts", Model.searchKey("\u041f\u0435\u0440\u0432\u044b\u0439 \u043a\u0430\u043d\u0430\u043b", "RU"), "\u043f\u0435\u0440\u0432\u044b\u0439 \u043a\u0430\u043d\u0430\u043b ru")
check("searchKey empty group", Model.searchKey("CNN", null), "cnn")
check("tokenize", Model.tokenize("  BBC   one "), ["bbc", "one"])

// ---- ids ----
check("fnv1a32 empty", Model.fnv1a32(""), "811c9dc5")
check("fnv1a32 a", Model.fnv1a32("a"), "e40c292c")
check("fnv1a32 foobar", Model.fnv1a32("foobar"), "bf9cf968")
check("channelId prefers explicit id", Model.channelId({ id: "t:x", tvgId: "y", url: "u" }), "t:x")
check("channelId tvg", Model.channelId({ tvgId: "bbc1.uk", url: "http://a" }), "t:bbc1.uk")
check("channelId url hash", Model.channelId({ url: "foobar" }), "u:bf9cf968")
check("channelId null", Model.channelId(null), "")

// ---- search ----
const channels = [
  { id: "1", name: "BBC One HD", group: "UK", searchKey: "bbc one hd uk" },
  { id: "2", name: "CBBC", group: "Kids", searchKey: "cbbc kids" },
  { id: "3", name: "One America", group: "US", searchKey: "one america us" },
  { id: "4", name: "Sky News", group: "News", searchKey: "sky news news" },
  { id: "5", name: "BBC Two", group: "UK", searchKey: "bbc two uk" }
]
check("filterChannels empty query keeps order", Model.filterChannels(channels, "", 2).rows.map(c => c.id), ["1", "2"])
check("filterChannels empty query total/truncated", (() => { const r = Model.filterChannels(channels, "", 2); return [r.total, r.truncated] })(), [5, true])
check("filterChannels ranks prefix > word > substring", Model.filterChannels(channels, "one", 10).rows.map(c => c.id), ["3", "1"])
check("filterChannels AND tokens", Model.filterChannels(channels, "bbc uk", 10).rows.map(c => c.id), ["1", "5"])
check("filterChannels group matches", Model.filterChannels(channels, "kids", 10).rows.map(c => c.id), ["2"])
check("filterChannels no match", Model.filterChannels(channels, "zzz", 10), { rows: [], total: 0, truncated: false })
check("filterChannels bounded", Model.filterChannels(channels, "b", 1).rows.length, 1)
check("filterChannels null input", Model.filterChannels(null, "x", 5), { rows: [], total: 0, truncated: false })

// ---- groups ----
const state = { version: 1, favorites: ["5", "missing"], recents: [{ id: "4", name: "Sky News", at: 1 }], lastPlayed: null }
check("groupChannels pins favorites/recent then playlist order", Model.groupChannels(channels, state).map(g => g.name + ":" + g.count), ["Favorites:1", "Recent:1", "UK:2", "Kids:1", "US:1", "News:1"])
check("groupChannels without state", Model.groupChannels(channels, null).map(g => g.name), ["UK", "Kids", "US", "News"])
check("channelsInGroup all", Model.channelsInGroup(channels, "", state).length, 5)
check("channelsInGroup favorites skips missing", Model.channelsInGroup(channels, "Favorites", state).map(c => c.id), ["5"])
check("channelsInGroup recent", Model.channelsInGroup(channels, "Recent", state).map(c => c.id), ["4"])
check("channelsInGroup named", Model.channelsInGroup(channels, "UK", state).map(c => c.id), ["1", "5"])
check("nextInGroup wraps forward", Model.nextInGroup(channels, "5", 1).id, "1")
check("nextInGroup wraps backward", Model.nextInGroup(channels, "1", -1).id, "5")
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
check("parseState tolerates garbage", Model.parseState("not json"), Model.emptyState())
check("parseState sanitizes", Model.parseState('{"favorites":["a","a",""],"recents":[{"id":"x","name":"X","at":"7"},{"bad":1}],"lastPlayed":{"id":"x"}}'),
  { version: 1, favorites: ["a"], recents: [{ id: "x", name: "X", at: 7 }], lastPlayed: { id: "x", name: "", at: 0 } })
check("isFavorite", Model.isFavorite(state, "5"), true)

// ---- caches ----
check("parseChannels ok", Model.parseChannels('{"version":1,"count":1,"channels":[{"id":"a"}]}'), { ok: true, channels: [{ id: "a" }], meta: { version: 1, count: 1 }, error: "" })
check("parseChannels empty", Model.parseChannels("").ok, false)
check("parseHelperStatus string error upgraded", Model.parseHelperStatus('{"ok":false,"error":"boom"}', "playlist").error, { code: "error", message: "boom" })
check("parseHelperStatus no output", Model.parseHelperStatus("", "epg").error.code, "no_output")

// ---- settings ----
const barConfig = { layout: { left: [{ id: "omarchy.menu" }], right: [{ id: "io.github.rmcdavid.iptv", playlistUrl: "http://x/y.m3u", refreshMinutes: "15" }] } }
check("findBarEntry finds own entry", Model.findBarEntry(barConfig, "io.github.rmcdavid.iptv").playlistUrl, "http://x/y.m3u")
check("findBarEntry missing", Model.findBarEntry(barConfig, "nope"), {})
check("findBarEntry null config", Model.findBarEntry(null, "x"), {})
check("settingOf fallback", Model.settingOf({ a: null }, "a", 3), 3)
check("clampInt parses and clamps", [Model.clampInt("15", 60, 5, 1440), Model.clampInt("x", 60, 5, 1440), Model.clampInt(2, 60, 5, 1440)], [15, 60, 5])

// ---- mpv ----
check("splitMpvArgs accepts options", Model.splitMpvArgs(" --profile=low-latency --hwdec=auto-safe --no-osc "), { args: ["--profile=low-latency", "--hwdec=auto-safe", "--no-osc"], rejected: [] })
check("splitMpvArgs rejects reserved and junk", Model.splitMpvArgs("--input-ipc-server=/x --title=y ; rm -rf --no-idle --cache=yes"), { args: ["--cache=yes"], rejected: ["--input-ipc-server=/x", "--title=y", ";", "rm", "-rf", "--no-idle"] })
check("headerArgs maps UA/referer and appends others", Model.headerArgs({ "User-Agent": "VLC", Referer: "http://r", "X-Token": "a,b" }), ["--user-agent=VLC", "--referrer=http://r", "--http-header-fields-append=X-Token: a,b"])
check("headerArgs drops unsafe", Model.headerArgs({ "Bad Name": "x", Ok: "line\nbreak" }), [])
const argv = Model.buildMpvArgv({ socketPath: "/run/user/1000/omarchy-iptv/mpv.sock", name: "BBC One", url: "--not-an-option", headers: {}, extraArgs: ["--profile=low-latency"] })
check("buildMpvArgv starts with mpv and ipc socket", argv.slice(0, 2), ["mpv", "--input-ipc-server=/run/user/1000/omarchy-iptv/mpv.sock"])
check("buildMpvArgv has app id and title", [argv.indexOf("--wayland-app-id=omarchy-iptv") > 0, argv.indexOf("--title=BBC One") > 0, argv.indexOf("--force-media-title=BBC One") > 0], [true, true, true])
check("buildMpvArgv url after --", argv.slice(-2), ["--", "--not-an-option"])
check("buildMpvArgv extra args before --", argv.indexOf("--profile=low-latency") < argv.indexOf("--"), true)

// ---- formatting ----
check("formatEpgLine now+next", (() => {
  const line = Model.formatEpgLine({ now: { title: "News", start: 1000, stop: 4102444800 }, next: { title: "Weather", start: 4102444800 } }, 2000)
  return [line.now.indexOf("Now: News until ") === 0, line.next.indexOf("Next: Weather at ") === 0]
})(), [true, true])
check("formatEpgLine expired now", Model.formatEpgLine({ now: { title: "Old", stop: 10 } }, 20), { now: "", next: "" })
check("formatEpgLine null", Model.formatEpgLine(null, 0), { now: "", next: "" })
check("elide", Model.elide("abcdefgh", 5), "abcd\u2026")
check("elide short", Model.elide("abc", 5), "abc")

if (failures > 0) {
  console.log("\n" + failures + " failure(s)")
  process.exit(1)
}
console.log("\nAll Model.js tests passed.")
