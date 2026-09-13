// Model.js -- pure logic for io.github.rmcdavid.iptv.
//
// Rules (see docs/ARCHITECTURE.md, "Coding standards"):
//   - No QML, no I/O, no timers, no Quickshell APIs. Inputs in, values out.
//   - ES5-style functions and `var`: this file is loaded by the QML engine
//     (`import "Model.js" as Model`) and by node (`require("./Model.js")`).
//     No ES module syntax, no top-level `const`/`let` exports.
//   - Every function must be safe on null/undefined input.
//   - Text normalization here MUST stay byte-for-byte compatible with
//     `normalize_text` / `search_key` / `fnv1a32` in bin/omarchy-iptv; the
//     helper writes searchKey/id into channels.json and the guide only
//     normalizes the query. tests/Model.test.js and tests/test_playlist.py
//     pin the shared vectors.

var MAX_ROWS_DEFAULT = 300
var FAVORITES_GROUP = "Favorites"
var RECENT_GROUP = "Recent"
var UNGROUPED = "Ungrouped"
var STATE_VERSION = 1

// mpv options the user may not override through the mpvArgs setting because
// the service depends on them (socket, window identity, exit semantics).
var MPV_RESERVED = {
  "--input-ipc-server": true,
  "--wayland-app-id": true,
  "--title": true,
  "--force-media-title": true,
  "--idle": true,
  "--input-ipc-client": true,
  "--script": true,
  "--scripts": true,
  "--config-dir": true
}

// ------------------------------------------------------------ normalization

// Latin diacritics folded to ASCII. Kept as (chars, replacement) groups so the
// Python helper can carry the identical table.
var FOLD_GROUPS = [
  ["\u00e0\u00e1\u00e2\u00e3\u00e4\u00e5\u0101\u0103\u0105", "a"],
  ["\u00e7\u0107\u010d", "c"],
  ["\u010f\u0111", "d"],
  ["\u00e8\u00e9\u00ea\u00eb\u0113\u0117\u0119\u011b", "e"],
  ["\u00ec\u00ed\u00ee\u00ef\u012b\u0131", "i"],
  ["\u0142\u013e", "l"],
  ["\u00f1\u0144\u0148", "n"],
  ["\u00f2\u00f3\u00f4\u00f5\u00f6\u00f8\u014d\u0151", "o"],
  ["\u0159", "r"],
  ["\u015b\u0161\u015f", "s"],
  ["\u0165\u0163", "t"],
  ["\u00f9\u00fa\u00fb\u00fc\u016b\u016f\u0171", "u"],
  ["\u00fd\u00ff", "y"],
  ["\u017a\u017c\u017e", "z"],
  ["\u00df", "ss"],
  ["\u00e6", "ae"],
  ["\u0153", "oe"]
]

var FOLD = (function() {
  var map = {}
  for (var g = 0; g < FOLD_GROUPS.length; g++) {
    var chars = FOLD_GROUPS[g][0]
    for (var i = 0; i < chars.length; i++) map[chars.charAt(i)] = FOLD_GROUPS[g][1]
  }
  return map
})()

// ASCII whitespace and punctuation collapse to one space; every other
// character (any script) is kept, so Cyrillic/Greek/Arabic names stay
// searchable. Mirrors _PUNCT in bin/omarchy-iptv.
var PUNCT_RE = /[\s!-\/:-@\[-`{-~]+/g

function normalizeText(value) {
  var text = String(value === undefined || value === null ? "" : value).toLowerCase()
  var out = ""
  for (var i = 0; i < text.length; i++) {
    var ch = text.charAt(i)
    out += FOLD[ch] !== undefined ? FOLD[ch] : ch
  }
  return out.replace(PUNCT_RE, " ").replace(/^ | $/g, "")
}

function searchKey(name, group) {
  var key = normalizeText(name)
  var grp = normalizeText(group)
  if (grp !== "") key = key === "" ? grp : key + " " + grp
  return key
}

function tokenize(query) {
  var text = normalizeText(query)
  if (text === "") return []
  return text.split(" ")
}

// ------------------------------------------------------------ ids

// FNV-1a 32-bit over UTF-8 bytes, as 8 lowercase hex digits. Standard test
// vectors: "" -> 811c9dc5, "a" -> e40c292c, "foobar" -> bf9cf968.
function fnv1a32(value) {
  var text = String(value === undefined || value === null ? "" : value)
  var hash = 0x811c9dc5
  function mix(byte) {
    hash ^= byte
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  for (var i = 0; i < text.length; i++) {
    var code = text.charCodeAt(i)
    if (code >= 0xd800 && code <= 0xdbff && i + 1 < text.length) {
      var low = text.charCodeAt(i + 1)
      if (low >= 0xdc00 && low <= 0xdfff) {
        code = 0x10000 + ((code - 0xd800) << 10) + (low - 0xdc00)
        i++
      }
    }
    if (code < 0x80) {
      mix(code)
    } else if (code < 0x800) {
      mix(0xc0 | (code >> 6))
      mix(0x80 | (code & 0x3f))
    } else if (code < 0x10000) {
      mix(0xe0 | (code >> 12))
      mix(0x80 | ((code >> 6) & 0x3f))
      mix(0x80 | (code & 0x3f))
    } else {
      mix(0xf0 | (code >> 18))
      mix(0x80 | ((code >> 12) & 0x3f))
      mix(0x80 | ((code >> 6) & 0x3f))
      mix(0x80 | (code & 0x3f))
    }
  }
  var hex = (hash >>> 0).toString(16)
  while (hex.length < 8) hex = "0" + hex
  return hex
}

// The helper assigns `id` when it writes channels.json (tvg-id when unique
// in the playlist, else a URL hash; see ARCHITECTURE.md decision 6). This
// mirrors the per-channel rule for callers that build channels in memory.
function channelId(channel) {
  if (!channel) return ""
  if (typeof channel.id === "string" && channel.id !== "") return channel.id
  var tvg = String(channel.tvgId || "")
  if (tvg !== "") return "t:" + tvg
  return "u:" + fnv1a32(String(channel.url || ""))
}

function indexById(channels) {
  var index = {}
  var list = Array.isArray(channels) ? channels : []
  for (var i = 0; i < list.length; i++) {
    var id = channelId(list[i])
    if (id !== "" && index[id] === undefined) index[id] = list[i]
  }
  return index
}

// ------------------------------------------------------------ search

// -1 no match; 0 name starts with the first token; 1 a word in the key
// starts with the first token; 2 plain substring match. Every token must
// occur somewhere in the key (AND semantics).
function matchRank(key, tokens) {
  var text = String(key || "")
  for (var i = 0; i < tokens.length; i++) {
    if (text.indexOf(tokens[i]) === -1) return -1
  }
  var first = tokens[0]
  if (text.indexOf(first) === 0) return 0
  if (text.indexOf(" " + first) !== -1) return 1
  return 2
}

// Bounded filter: scans every candidate (10k short strings is a few ms) but
// only materializes `limit` rows, best ranks first, stable within a rank.
function filterChannels(channels, query, limit) {
  var list = Array.isArray(channels) ? channels : []
  var max = limit > 0 ? Math.floor(limit) : MAX_ROWS_DEFAULT
  var tokens = tokenize(query)
  if (tokens.length === 0) {
    return { rows: list.slice(0, max), total: list.length, truncated: list.length > max }
  }
  var buckets = [[], [], []]
  var total = 0
  for (var i = 0; i < list.length; i++) {
    var channel = list[i]
    if (!channel) continue
    var key = typeof channel.searchKey === "string" ? channel.searchKey : searchKey(channel.name, channel.group)
    var rank = matchRank(key, tokens)
    if (rank < 0) continue
    total++
    if (buckets[rank].length < max) buckets[rank].push(channel)
  }
  var rows = buckets[0].concat(buckets[1], buckets[2]).slice(0, max)
  return { rows: rows, total: total, truncated: total > max }
}

// ------------------------------------------------------------ groups

// Ordered group list for the guide's group filter. Favorites and Recent
// are pinned first (when non-empty), then playlist groups in first-seen order.
function groupChannels(channels, state) {
  var list = Array.isArray(channels) ? channels : []
  var st = state || emptyState()
  var out = []
  var index = indexById(list)
  var favorites = 0
  for (var f = 0; f < st.favorites.length; f++) if (index[st.favorites[f]]) favorites++
  var recents = 0
  for (var r = 0; r < st.recents.length; r++) if (st.recents[r] && index[st.recents[r].id]) recents++
  if (favorites > 0) out.push({ name: FAVORITES_GROUP, kind: "favorites", count: favorites })
  if (recents > 0) out.push({ name: RECENT_GROUP, kind: "recent", count: recents })
  var seen = {}
  var order = []
  for (var i = 0; i < list.length; i++) {
    var name = String(list[i] && list[i].group ? list[i].group : UNGROUPED)
    if (seen[name] === undefined) {
      seen[name] = { name: name, kind: "group", count: 0 }
      order.push(seen[name])
    }
    seen[name].count++
  }
  return out.concat(order)
}

// Candidate rows for a group. "" means every channel. Favorites/Recent are
// virtual groups resolved through the state file.
function channelsInGroup(channels, group, state) {
  var list = Array.isArray(channels) ? channels : []
  var name = String(group || "")
  if (name === "") return list
  var st = state || emptyState()
  var index, out = [], i
  if (name === FAVORITES_GROUP) {
    index = indexById(list)
    for (i = 0; i < st.favorites.length; i++) if (index[st.favorites[i]]) out.push(index[st.favorites[i]])
    return out
  }
  if (name === RECENT_GROUP) {
    index = indexById(list)
    for (i = 0; i < st.recents.length; i++) {
      var entry = st.recents[i]
      if (entry && index[entry.id]) out.push(index[entry.id])
    }
    return out
  }
  for (i = 0; i < list.length; i++) {
    var channelGroup = String(list[i] && list[i].group ? list[i].group : UNGROUPED)
    if (channelGroup === name) out.push(list[i])
  }
  return out
}

// Wrap-around neighbour inside an ordered list (bar scroll zapping).
function nextInGroup(list, currentId, delta) {
  var rows = Array.isArray(list) ? list : []
  if (rows.length === 0) return null
  var step = delta < 0 ? -1 : 1
  var at = -1
  for (var i = 0; i < rows.length; i++) if (channelId(rows[i]) === currentId) { at = i; break }
  if (at === -1) return rows[0]
  return rows[(at + step + rows.length) % rows.length]
}

// ------------------------------------------------------------ state

function emptyState() {
  return { version: STATE_VERSION, favorites: [], recents: [], lastPlayed: null }
}

function parseState(text) {
  var state = emptyState()
  var parsed = parseJsonObject(text)
  if (!parsed) return state
  if (Array.isArray(parsed.favorites)) {
    for (var i = 0; i < parsed.favorites.length; i++) {
      var id = String(parsed.favorites[i] || "")
      if (id !== "" && state.favorites.indexOf(id) === -1) state.favorites.push(id)
    }
  }
  if (Array.isArray(parsed.recents)) {
    for (var r = 0; r < parsed.recents.length; r++) {
      var entry = parsed.recents[r]
      if (!entry || typeof entry !== "object" || !entry.id) continue
      state.recents.push({ id: String(entry.id), name: String(entry.name || ""), at: Number(entry.at) || 0 })
    }
  }
  if (parsed.lastPlayed && typeof parsed.lastPlayed === "object" && parsed.lastPlayed.id) {
    state.lastPlayed = { id: String(parsed.lastPlayed.id), name: String(parsed.lastPlayed.name || ""), at: Number(parsed.lastPlayed.at) || 0 }
  }
  return state
}

function isFavorite(state, id) {
  return !!(state && Array.isArray(state.favorites) && state.favorites.indexOf(String(id || "")) !== -1)
}

// Returns a new favorites array; never mutates the input.
function toggleFavorite(favorites, id) {
  var key = String(id || "")
  var list = Array.isArray(favorites) ? favorites.slice() : []
  if (key === "") return list
  var at = list.indexOf(key)
  if (at === -1) list.push(key)
  else list.splice(at, 1)
  return list
}

// Newest first, de-duplicated by id, capped at `max`. Returns a new array.
function pushRecent(recents, channel, max, nowSec) {
  var id = channelId(channel)
  var cap = max > 0 ? Math.floor(max) : 10
  var out = []
  if (id !== "") out.push({ id: id, name: String(channel.name || ""), at: Math.floor(Number(nowSec) || 0) })
  var list = Array.isArray(recents) ? recents : []
  for (var i = 0; i < list.length && out.length < cap; i++) {
    if (list[i] && list[i].id !== id) out.push(list[i])
  }
  return out
}

// New state object after a channel starts playing (recents + lastPlayed).
function recordPlayed(state, channel, max, nowSec) {
  var st = state || emptyState()
  var id = channelId(channel)
  return {
    version: STATE_VERSION,
    favorites: Array.isArray(st.favorites) ? st.favorites.slice() : [],
    recents: pushRecent(st.recents, channel, max, nowSec),
    lastPlayed: id === "" ? st.lastPlayed : { id: id, name: String(channel.name || ""), at: Math.floor(Number(nowSec) || 0) }
  }
}

function withFavorites(state, favorites) {
  var st = state || emptyState()
  return {
    version: STATE_VERSION,
    favorites: Array.isArray(favorites) ? favorites.slice() : [],
    recents: Array.isArray(st.recents) ? st.recents.slice() : [],
    lastPlayed: st.lastPlayed || null
  }
}

// ------------------------------------------------------------ caches

function parseJsonObject(text) {
  var raw = String(text === undefined || text === null ? "" : text).replace(/^\s+|\s+$/g, "")
  if (raw === "") return null
  try {
    var parsed = JSON.parse(raw)
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null
  } catch (e) {
    return null
  }
}

// channels.json -> { ok, channels, meta, error }
function parseChannels(text) {
  var doc = parseJsonObject(text)
  if (!doc) return { ok: false, channels: [], meta: {}, error: "channels cache is empty or not JSON" }
  if (!Array.isArray(doc.channels)) return { ok: false, channels: [], meta: {}, error: "channels cache has no channels array" }
  var meta = {}
  for (var key in doc) if (key !== "channels") meta[key] = doc[key]
  return { ok: true, channels: doc.channels, meta: meta, error: "" }
}

// Helper status JSON -> normalized object the UI can render directly.
function parseHelperStatus(text, kind) {
  var doc = parseJsonObject(text)
  if (!doc) return { ok: false, kind: kind || "", stale: false, error: { code: "no_output", message: "helper produced no JSON" } }
  if (doc.error && typeof doc.error === "string") doc.error = { code: "error", message: doc.error }
  if (doc.ok !== true && !doc.error) doc.error = { code: "error", message: "helper reported failure" }
  return doc
}

// ------------------------------------------------------------ settings

// Our inline settings live on the bar layout entry (shell.json bar.layout.*).
// Returns the entry object or {} so callers can read keys with fallbacks.
function findBarEntry(barConfig, pluginId) {
  var id = String(pluginId || "")
  if (!barConfig || typeof barConfig !== "object" || !barConfig.layout || typeof barConfig.layout !== "object") return {}
  var sections = ["left", "center", "right"]
  for (var s = 0; s < sections.length; s++) {
    var entries = barConfig.layout[sections[s]]
    if (!Array.isArray(entries)) continue
    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i]
      if (typeof entry === "string" && entry === id) return { id: id }
      if (entry && typeof entry === "object" && String(entry.id || "") === id) return entry
    }
  }
  return {}
}

function settingOf(entry, key, fallback) {
  var value = entry && typeof entry === "object" ? entry[key] : undefined
  return value === undefined || value === null ? fallback : value
}

function clampInt(value, fallback, min, max) {
  var n = parseInt(String(value), 10)
  if (!isFinite(n)) n = fallback
  if (n < min) n = min
  if (n > max) n = max
  return n
}

// ------------------------------------------------------------ mpv

// mpvArgs is one string of whitespace-separated `--key[=value]` tokens.
// Anything else (including reserved options) is rejected, never guessed.
function splitMpvArgs(text) {
  var args = []
  var rejected = []
  var parts = String(text || "").split(/\s+/)
  for (var i = 0; i < parts.length; i++) {
    var token = parts[i]
    if (token === "") continue
    var ok = /^--[a-z0-9][a-z0-9-]*(=.*)?$/i.test(token)
    var name = token.indexOf("=") === -1 ? token : token.substring(0, token.indexOf("="))
    if (!ok || MPV_RESERVED[name] === true || name.indexOf("--no-") === 0 && MPV_RESERVED["--" + name.substring(5)] === true) rejected.push(token)
    else args.push(token)
  }
  return { args: args, rejected: rejected }
}

// Per-channel HTTP headers as mpv argv items. `-append` list form so header
// values may contain commas without escaping.
function headerArgs(headers) {
  var out = []
  if (!headers || typeof headers !== "object") return out
  for (var name in headers) {
    var value = String(headers[name] === undefined || headers[name] === null ? "" : headers[name])
    if (!/^[A-Za-z0-9-]+$/.test(name) || /[\r\n]/.test(value)) continue
    var lower = name.toLowerCase()
    if (lower === "user-agent") out.push("--user-agent=" + value)
    else if (lower === "referer" || lower === "referrer") out.push("--referrer=" + value)
    else out.push("--http-header-fields-append=" + name + ": " + value)
  }
  return out
}

// Full argv for the first launch. The URL always follows "--" so a playlist
// entry can never be parsed as an mpv option.
function buildMpvArgv(params) {
  var p = params || {}
  var name = String(p.name || "IPTV")
  var argv = [
    "mpv",
    "--input-ipc-server=" + String(p.socketPath || ""),
    "--wayland-app-id=omarchy-iptv",
    "--force-window=immediate",
    "--idle=no",
    "--keep-open=no",
    "--title=" + name,
    "--force-media-title=" + name,
    "--msg-level=all=error"
  ]
  argv = argv.concat(headerArgs(p.headers))
  if (Array.isArray(p.extraArgs)) argv = argv.concat(p.extraArgs)
  argv.push("--")
  argv.push(String(p.url || ""))
  return argv
}

// ------------------------------------------------------------ formatting

function pad2(n) {
  return (n < 10 ? "0" : "") + n
}

function formatClock(epochSec) {
  var ms = Number(epochSec) * 1000
  if (!isFinite(ms) || ms <= 0) return ""
  var d = new Date(ms)
  return pad2(d.getHours()) + ":" + pad2(d.getMinutes())
}

// epg-now entry { now: {title,start,stop}, next: {...} } -> display strings.
// Expired `now` entries yield "" so the row never shows a stale programme.
function formatEpgLine(entry, nowSec) {
  var out = { now: "", next: "" }
  if (!entry || typeof entry !== "object") return out
  var t = Number(nowSec) || 0
  var current = entry.now
  if (current && current.title && (!t || !(Number(current.stop) > 0) || Number(current.stop) > t)) {
    out.now = "Now: " + String(current.title)
    if (Number(current.stop) > 0) out.now += " until " + formatClock(current.stop)
  }
  var next = entry.next
  if (next && next.title) {
    out.next = "Next: " + String(next.title)
    if (Number(next.start) > 0) out.next += " at " + formatClock(next.start)
  }
  return out
}

function elide(text, max) {
  var value = String(text === undefined || text === null ? "" : text)
  var limit = max > 3 ? Math.floor(max) : 3
  return value.length > limit ? value.substring(0, limit - 1) + "\u2026" : value
}

if (typeof module !== "undefined") {
  module.exports = {
    MAX_ROWS_DEFAULT: MAX_ROWS_DEFAULT,
    FAVORITES_GROUP: FAVORITES_GROUP,
    RECENT_GROUP: RECENT_GROUP,
    UNGROUPED: UNGROUPED,
    FOLD_GROUPS: FOLD_GROUPS,
    normalizeText: normalizeText,
    searchKey: searchKey,
    tokenize: tokenize,
    fnv1a32: fnv1a32,
    channelId: channelId,
    indexById: indexById,
    matchRank: matchRank,
    filterChannels: filterChannels,
    groupChannels: groupChannels,
    channelsInGroup: channelsInGroup,
    nextInGroup: nextInGroup,
    emptyState: emptyState,
    parseState: parseState,
    isFavorite: isFavorite,
    toggleFavorite: toggleFavorite,
    pushRecent: pushRecent,
    recordPlayed: recordPlayed,
    withFavorites: withFavorites,
    parseJsonObject: parseJsonObject,
    parseChannels: parseChannels,
    parseHelperStatus: parseHelperStatus,
    findBarEntry: findBarEntry,
    settingOf: settingOf,
    clampInt: clampInt,
    splitMpvArgs: splitMpvArgs,
    headerArgs: headerArgs,
    buildMpvArgv: buildMpvArgv,
    formatClock: formatClock,
    formatEpgLine: formatEpgLine,
    elide: elide
  }
}
