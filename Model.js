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
//   - ASCII only. Nerd Font glyphs and typographic characters are written
//     as \uXXXX escapes (surrogate pairs for the supplementary plane).
//
// Rulings applied (docs/ARCHITECTURE.md section 12): R2 settings clamps,
// R3 result cap 200, R4 search key + ranking tiers, R5 first-group placement
// and recents on the play command, R7 bar glyphs, R8 model fields, R9 zap
// ring, R11 session-only failedAt, R12 notification privacy.

var MAX_ROWS_DEFAULT = 200
var FAVORITES_GROUP = "Favorites"
var RECENT_GROUP = "Recent"
var UNGROUPED = "Ungrouped"
var STATE_VERSION = 1

// Column / scope ids (UX.md 2.2, 2.7). Real groups are "g:<group name>".
var SCOPE_RECENT = "recent"
var SCOPE_FAVORITES = "favorites"
var SCOPE_ALL = "all"
var GROUP_SCOPE_PREFIX = "g:"

// Typographic characters Omarchy uses (UX.md preamble table).
var ELLIPSIS = "\u2026"
var QUOTE_OPEN = "\u201c"
var QUOTE_CLOSE = "\u201d"
var SEP = " \u00b7 "

// Nerd Font glyphs (UX.md 5.5), as surrogate pairs so this file stays ASCII.
var GLYPHS = {
  tv: "\udb81\udd02",        // U+F0502 nf-md-television        idle / not configured
  tvPlay: "\udb81\udd67",    // U+F0567 nf-md-television_play   playing (bar)
  tvOff: "\udb81\udd03",     // U+F0503 nf-md-television_off    playlist error / stream failed
  star: "\udb81\udcce",      // U+F04CE nf-md-star              favorite
  play: "\udb81\udc0a",      // U+F040A nf-md-play              playing row / footer
  alert: "\udb80\udc26",     // U+F0026 nf-md-alert             failed / banner
  loading: "\udb80\uddd8",   // U+F01D8 nf-md-dots_horizontal   loading
  refresh: "\udb81\udc50",   // U+F0450 nf-md-refresh           refresh notification
  history: "\udb80\udeda"    // U+F02DA nf-md-history           recent
}

// Settings clamps (R2). `showChannelName` is `!== false`; strings are trimmed.
var SETTING_RANGES = {
  refreshMinutes: { def: 360, min: 15, max: 1440 },
  maxRecents: { def: 10, min: 1, max: 50 },
  barLabelMaxWidth: { def: 180, min: 60, max: 600 }
}

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

// Stable notification replace-ids so a repeated failure replaces its toast
// instead of stacking (UX.md 6.4).
var NOTIFY_IDS = {
  streamFailed: 74011,
  playlistRefreshed: 74012,
  playlistError: 74013,
  epgError: 74014,
  mpvMissing: 74015
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

function str(value) {
  return String(value === undefined || value === null ? "" : value)
}

// Always a real Array. Values that cross the QML boundary (a `property var`
// holding an object literal, a QVariantList) are array-like but fail
// Array.isArray in the Qt engine; copy them so every caller can use Array
// methods safely. Plain arrays are returned as-is (no copy on the hot path).
function asList(value) {
  if (Array.isArray(value)) return value
  if (value && typeof value === "object" && typeof value.length === "number") {
    var out = []
    for (var i = 0; i < value.length; i++) out.push(value[i])
    return out
  }
  return []
}

// Combining marks U+0300..U+036F are stripped after NFD, but only behind a
// Latin base letter, so every accented Latin letter folds (not only the
// FOLD_GROUPS table) while Cyrillic/Greek/Vietnamese-style marks on other
// scripts recompose unchanged (NFC), byte-identical to the helper's output.
var LATIN_COMBINING_RE = /([a-z])[\u0300-\u036f]+/g

function decompose(text) {
  if (typeof text.normalize !== "function") return text
  return text.normalize("NFD").replace(LATIN_COMBINING_RE, "$1").normalize("NFC")
}

function normalizeText(value) {
  var text = decompose(str(value).toLowerCase())
  var out = ""
  for (var i = 0; i < text.length; i++) {
    var ch = text.charAt(i)
    out += FOLD[ch] !== undefined ? FOLD[ch] : ch
  }
  return out.replace(PUNCT_RE, " ").replace(/^ | $/g, "")
}

// R4: searchKey = fold(name + " " + group). The whole multi-group string
// ("A;B;C") stays searchable; only column placement uses the first group.
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
  var text = str(value)
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
  var tvg = str(channel.tvgId)
  if (tvg !== "") return "t:" + tvg
  return "u:" + fnv1a32(str(channel.url))
}

function indexById(channels) {
  var index = {}
  var list = asList(channels)
  for (var i = 0; i < list.length; i++) {
    var id = channelId(list[i])
    if (id !== "" && index[id] === undefined) index[id] = list[i]
  }
  return index
}

function findByUrl(channels, url) {
  var target = str(url)
  if (target === "") return null
  var list = asList(channels)
  for (var i = 0; i < list.length; i++) if (list[i] && str(list[i].url) === target) return list[i]
  return null
}

// ------------------------------------------------------------ channels

// R5: a channel with `group-title="A;B;C"` is listed under its FIRST group.
function primaryGroup(channel) {
  var raw = channel && channel.group !== undefined && channel.group !== null ? str(channel.group) : ""
  var first = raw.split(";")[0].replace(/^\s+|\s+$/g, "")
  return first === "" ? UNGROUPED : first
}

// A channel name is never a URL (D-QA-02): an empty or URL-shaped name
// falls back to tvg-name, then to a positional label.
function looksLikeUrl(text) {
  return /^[a-z][a-z0-9+.-]*:\/\//i.test(str(text)) || /^(rtp|udp|rtsp|mms):/i.test(str(text))
}

function displayName(channel, position) {
  var name = str(channel && channel.name).replace(/^\s+|\s+$/g, "")
  if (name !== "" && !looksLikeUrl(name)) return name
  var tvg = str(channel && channel.tvgName).replace(/^\s+|\s+$/g, "")
  if (tvg !== "" && !looksLikeUrl(tvg)) return tvg
  return "Channel " + (Number(position) > 0 ? Math.floor(Number(position)) : "?")
}

// One pass at load time (off the open path): guarantees `id`, `searchKey`,
// `nameKey` and `primaryGroup` on every row so a keystroke never normalizes
// 10k strings. Returns new objects; never mutates the cache rows.
function prepareChannels(channels) {
  var list = asList(channels)
  var out = []
  var groupKeys = {}
  for (var i = 0; i < list.length; i++) {
    var src = list[i]
    if (!src || typeof src !== "object") continue
    var row = {}
    for (var key in src) row[key] = src[key]
    row.id = channelId(src)
    row.name = displayName(src, out.length + 1)
    row.group = str(src.group)
    row.primaryGroup = primaryGroup(src)
    var grp = row.group
    if (groupKeys[grp] === undefined) groupKeys[grp] = normalizeText(grp)
    var groupKey = groupKeys[grp]
    if (typeof row.searchKey !== "string" || row.searchKey === "" || row.name !== str(src.name)) row.searchKey = searchKey(row.name, grp)
    if (groupKey !== "" && row.searchKey.length > groupKey.length && row.searchKey.substring(row.searchKey.length - groupKey.length - 1) === " " + groupKey) {
      row.nameKey = row.searchKey.substring(0, row.searchKey.length - groupKey.length - 1)
    } else if (groupKey !== "" && row.searchKey === groupKey) {
      row.nameKey = ""
    } else {
      row.nameKey = normalizeText(row.name)
    }
    out.push(row)
  }
  return out
}

// ------------------------------------------------------------ search

function containsAll(text, tokens) {
  for (var i = 0; i < tokens.length; i++) if (text.indexOf(tokens[i]) === -1) return false
  return true
}

// Ranking tiers (R4 / UX 2.5). -1 no match; 0 name starts with the query;
// 1 a word in the name starts with the query; 2 name contains every term;
// 3 only the group carries some of the terms. Every term must occur in the
// search key (AND semantics).
function matchRank(key, tokens, nameKey) {
  var text = str(key)
  if (tokens.length === 0) return 2
  if (!containsAll(text, tokens)) return -1
  var phrase = tokens.join(" ")
  var name = typeof nameKey === "string" ? nameKey : text
  if (name.indexOf(phrase) === 0) return 0
  if ((" " + name).indexOf(" " + phrase) !== -1) return 1
  if (containsAll(name, tokens)) return 2
  return 3
}

function favoriteSet(favorites) {
  var set = {}
  var list = asList(favorites)
  if (list.length === 0 && favorites && typeof favorites === "object" && favorites.favorites) list = asList(favorites.favorites)
  for (var i = 0; i < list.length; i++) set[str(list[i])] = true
  return set
}

// Bounded filter: scans every candidate (10k short strings is a few ms) but
// only materializes `limit` rows: best tier first, favorites first inside a
// tier, playlist order inside that. `favorites` is an id array or a state.
function filterChannels(channels, query, limit, favorites) {
  var list = asList(channels)
  var max = limit > 0 ? Math.floor(limit) : MAX_ROWS_DEFAULT
  var tokens = tokenize(query)
  if (tokens.length === 0) {
    return { rows: list.slice(0, max), total: list.length, truncated: list.length > max }
  }
  var favs = favoriteSet(favorites)
  var buckets = []
  for (var b = 0; b < 8; b++) buckets.push([])
  var total = 0
  for (var i = 0; i < list.length; i++) {
    var channel = list[i]
    if (!channel) continue
    var key = typeof channel.searchKey === "string" ? channel.searchKey : searchKey(channel.name, channel.group)
    var nameKey = typeof channel.nameKey === "string" ? channel.nameKey : normalizeText(channel.name)
    var rank = matchRank(key, tokens, nameKey)
    if (rank < 0) continue
    total++
    var slot = rank * 2 + (favs[channelId(channel)] ? 0 : 1)
    if (buckets[slot].length < max) buckets[slot].push(channel)
  }
  var rows = []
  for (var s = 0; s < buckets.length && rows.length < max; s++) {
    for (var r = 0; r < buckets[s].length && rows.length < max; r++) rows.push(buckets[s][r])
  }
  return { rows: rows, total: total, truncated: total > max }
}

// ------------------------------------------------------------ groups / scopes

// Playlist groups in first-seen order (R5), each with its channel count.
function groupChannels(channels) {
  var list = asList(channels)
  var seen = {}
  var order = []
  for (var i = 0; i < list.length; i++) {
    if (!list[i]) continue
    var name = primaryGroup(list[i])
    if (seen[name] === undefined) {
      seen[name] = { name: name, kind: "group", count: 0 }
      order.push(seen[name])
    }
    seen[name].count++
  }
  return order
}

function groupScopeId(name) {
  return GROUP_SCOPE_PREFIX + str(name)
}

function isGroupScope(scopeId) {
  return str(scopeId).indexOf(GROUP_SCOPE_PREFIX) === 0
}

function isPinnedScope(scopeId) {
  var id = str(scopeId)
  return id === SCOPE_RECENT || id === SCOPE_FAVORITES || id === SCOPE_ALL
}

function scopeName(scopeId) {
  var id = str(scopeId)
  if (id === SCOPE_RECENT) return RECENT_GROUP
  if (id === SCOPE_FAVORITES) return FAVORITES_GROUP
  if (id === SCOPE_ALL) return "All"
  if (isGroupScope(id)) return id.substring(GROUP_SCOPE_PREFIX.length)
  return id
}

function countFavorites(list, st) {
  var index = indexById(list)
  var n = 0
  for (var f = 0; f < st.favorites.length; f++) if (index[st.favorites[f]]) n++
  return n
}

function countRecents(list, st) {
  var index = indexById(list)
  var n = 0
  for (var r = 0; r < st.recents.length; r++) if (st.recents[r] && index[st.recents[r].id]) n++
  return n
}

// Group column entries (UX 2.2): Recent (hidden while empty), Favorites
// (always), All, then a "GROUPS" header and one entry per playlist group.
function scopeEntries(channels, state) {
  var list = asList(channels)
  var st = state || emptyState()
  var out = []
  var recents = countRecents(list, st)
  if (recents > 0) out.push({ id: SCOPE_RECENT, label: RECENT_GROUP, kind: "recent", count: recents })
  out.push({ id: SCOPE_FAVORITES, label: FAVORITES_GROUP, kind: "favorites", count: countFavorites(list, st) })
  out.push({ id: SCOPE_ALL, label: "All", kind: "all", count: list.length })
  var groups = groupChannels(list)
  if (groups.length > 0) out.push({ id: "", label: "GROUPS", kind: "header", count: 0 })
  for (var i = 0; i < groups.length; i++) {
    out.push({ id: groupScopeId(groups[i].name), label: groups[i].name, kind: "group", count: groups[i].count })
  }
  return out
}

// Candidate rows for a scope id. Favorites/Recent resolve through the state.
function channelsForScope(channels, scopeId, state) {
  var list = asList(channels)
  var id = str(scopeId)
  if (id === SCOPE_ALL || id === "") return list
  var st = state || emptyState()
  var index, out = [], i
  if (id === SCOPE_FAVORITES) {
    index = indexById(list)
    for (i = 0; i < st.favorites.length; i++) if (index[st.favorites[i]]) out.push(index[st.favorites[i]])
    return out
  }
  if (id === SCOPE_RECENT) {
    index = indexById(list)
    for (i = 0; i < st.recents.length; i++) {
      var entry = st.recents[i]
      if (entry && index[entry.id]) out.push(index[entry.id])
    }
    return out
  }
  var name = scopeName(id)
  for (i = 0; i < list.length; i++) if (list[i] && primaryGroup(list[i]) === name) out.push(list[i])
  return out
}

// Legacy name kept for callers that think in group names ("" = all).
function channelsInGroup(channels, group, state) {
  var name = str(group)
  if (name === "") return channelsForScope(channels, SCOPE_ALL, state)
  if (name === FAVORITES_GROUP) return channelsForScope(channels, SCOPE_FAVORITES, state)
  if (name === RECENT_GROUP) return channelsForScope(channels, SCOPE_RECENT, state)
  return channelsForScope(channels, groupScopeId(name), state)
}

// UX 2.7: Recent and Favorites are never a search scope; a query searches
// All from there. Real groups and All keep their scope.
function effectiveScope(scopeId, query) {
  var id = str(scopeId)
  if (tokenize(query).length === 0) return id === "" ? SCOPE_ALL : id
  if (id === SCOPE_RECENT || id === SCOPE_FAVORITES || id === "") return SCOPE_ALL
  return id
}

// Next selectable column entry (skips the header row), wrapping (UX 2.3).
function moveScope(entries, scopeId, delta) {
  var list = asList(entries)
  var ids = []
  for (var i = 0; i < list.length; i++) if (list[i] && list[i].kind !== "header" && list[i].id !== "") ids.push(list[i].id)
  if (ids.length === 0) return str(scopeId)
  var at = ids.indexOf(str(scopeId))
  if (at === -1) return delta < 0 ? ids[ids.length - 1] : ids[0]
  var step = delta < 0 ? -1 : 1
  return ids[(at + step + ids.length) % ids.length]
}

function scopeIndex(entries, scopeId) {
  var list = asList(entries)
  for (var i = 0; i < list.length; i++) if (list[i] && list[i].id === str(scopeId) && list[i].kind !== "header") return i
  return -1
}

// Default entry on open (UX 2.2): Favorites when it has entries, else All.
function initialScope(channels, state) {
  var st = state || emptyState()
  return countFavorites(asList(channels), st) > 0 ? SCOPE_FAVORITES : SCOPE_ALL
}

// Cursor starts on the playing channel when it is in the list, else row 0.
function cursorFor(rows, playingId) {
  var list = asList(rows)
  var id = str(playingId)
  if (id === "") return 0
  for (var i = 0; i < list.length; i++) if (channelId(list[i]) === id) return i
  return 0
}

// Header scope label (UX 6.1).
function scopeLabel(scopeId, query, count) {
  var name = scopeName(effectiveScope(scopeId, query))
  var n = Number(count) || 0
  if (tokenize(query).length > 0) return "in " + name + SEP + formatCount(n) + (n === 1 ? " match" : " matches")
  return name + SEP + pluralChannels(n)
}

// ------------------------------------------------------------ guide state machine

// Pure reducer for the two keyboard modes (UX 3, R1). Guide.qml keeps one
// object and replaces it on every transition so bindings notice.
function guideState(scopeId) {
  return { mode: "search", query: "", scopeId: str(scopeId) || SCOPE_ALL, restoreScopeId: "", cursorIndex: 0 }
}

function copyGuide(st) {
  var src = st || guideState()
  return { mode: src.mode === "list" ? "list" : "search", query: str(src.query), scopeId: str(src.scopeId) || SCOPE_ALL, restoreScopeId: str(src.restoreScopeId), cursorIndex: Number(src.cursorIndex) || 0 }
}

function withQuery(st, query) {
  var next = copyGuide(st)
  var was = next.query
  var now = str(query)
  next.query = now
  next.cursorIndex = 0
  var hadTerms = tokenize(was).length > 0
  var hasTerms = tokenize(now).length > 0
  if (!hadTerms && hasTerms) {
    if (next.scopeId === SCOPE_RECENT || next.scopeId === SCOPE_FAVORITES) {
      next.restoreScopeId = next.scopeId
      next.scopeId = SCOPE_ALL
    }
  } else if (hadTerms && !hasTerms && next.restoreScopeId !== "") {
    next.scopeId = next.restoreScopeId
    next.restoreScopeId = ""
  }
  return next
}

// An explicit column move is a user choice: it is not undone when the
// query clears.
function withScope(st, scopeId) {
  var next = copyGuide(st)
  next.scopeId = str(scopeId) || SCOPE_ALL
  next.restoreScopeId = ""
  next.cursorIndex = 0
  return next
}

function withMode(st, mode) {
  var next = copyGuide(st)
  next.mode = mode === "list" ? "list" : "search"
  return next
}

function withCursor(st, index) {
  var next = copyGuide(st)
  next.cursorIndex = Math.max(0, Math.floor(Number(index) || 0))
  return next
}

// Tab / Shift+Tab / "/" toggle between the modes (UX 3.1, 3.2).
function toggleMode(st) {
  var cur = copyGuide(st)
  return withMode(cur, cur.mode === "list" ? "search" : "list")
}

// Esc: a non-empty query clears (mode unchanged); an empty one closes.
function onEscape(st) {
  var cur = copyGuide(st)
  if (cur.query !== "") return { state: withQuery(cur, ""), close: false }
  return { state: cur, close: true }
}

// Wrapping cursor move (j/k, Up/Down); clamped page move (PgUp/PgDn).
function moveCursor(index, delta, count, wrap) {
  var n = Math.max(0, Math.floor(Number(count) || 0))
  if (n === 0) return 0
  var at = Math.max(0, Math.min(n - 1, Math.floor(Number(index) || 0)))
  var d = Math.floor(Number(delta) || 0)
  if (wrap) return ((at + d) % n + n) % n
  return Math.max(0, Math.min(n - 1, at + d))
}

// ------------------------------------------------------------ zap ring

// UX 3.4: the list the playing channel was launched from. Favorites is a
// ring; every other launch (a group, All, Recent, a search hit) rings over
// the channel's own group.
function launchScope(scopeId, query, channel) {
  var scope = effectiveScope(scopeId, query)
  if (scope === SCOPE_FAVORITES && tokenize(query).length === 0) return SCOPE_FAVORITES
  return groupScopeId(primaryGroup(channel))
}

function zapRing(channels, state, nowPlaying) {
  if (!nowPlaying) return []
  var from = str(nowPlaying.launchedFrom)
  if (from === SCOPE_FAVORITES) return channelsForScope(channels, SCOPE_FAVORITES, state)
  if (isGroupScope(from)) return channelsForScope(channels, from, state)
  return channelsForScope(channels, groupScopeId(str(nowPlaying.group) || UNGROUPED), state)
}

// Wrap-around neighbour inside an ordered list.
function nextInGroup(list, currentId, delta) {
  var rows = asList(list)
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
  var favs = asList(parsed.favorites)
  if (favs.length > 0) {
    for (var i = 0; i < favs.length; i++) {
      var id = str(favs[i])
      if (id !== "" && state.favorites.indexOf(id) === -1) state.favorites.push(id)
    }
  }
  var recs = asList(parsed.recents)
  if (recs.length > 0) {
    for (var r = 0; r < recs.length; r++) {
      var entry = recs[r]
      if (!entry || typeof entry !== "object" || !entry.id) continue
      state.recents.push({ id: String(entry.id), name: str(entry.name), at: Number(entry.at) || 0 })
    }
  }
  if (parsed.lastPlayed && typeof parsed.lastPlayed === "object" && parsed.lastPlayed.id) {
    state.lastPlayed = { id: String(parsed.lastPlayed.id), name: str(parsed.lastPlayed.name), at: Number(parsed.lastPlayed.at) || 0 }
  }
  return state
}

function isFavorite(state, id) {
  return !!(state && asList(state.favorites).indexOf(str(id)) !== -1)
}

// Returns a new favorites array; never mutates the input.
function toggleFavorite(favorites, id) {
  var key = str(id)
  var list = asList(favorites).slice()
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
  if (id !== "") out.push({ id: id, name: str(channel.name), at: Math.floor(Number(nowSec) || 0) })
  var list = asList(recents)
  for (var i = 0; i < list.length && out.length < cap; i++) {
    if (list[i] && list[i].id !== id) out.push(list[i])
  }
  return out
}

// New state object after the play command (R5: recorded on the command, not
// on playback success).
function recordPlayed(state, channel, max, nowSec) {
  var st = state || emptyState()
  var id = channelId(channel)
  return {
    version: STATE_VERSION,
    favorites: asList(st.favorites).slice(),
    recents: pushRecent(st.recents, channel, max, nowSec),
    lastPlayed: id === "" ? st.lastPlayed : { id: id, name: str(channel.name), at: Math.floor(Number(nowSec) || 0) }
  }
}

function withFavorites(state, favorites) {
  var st = state || emptyState()
  return {
    version: STATE_VERSION,
    favorites: asList(favorites).slice(),
    recents: asList(st.recents).slice(),
    lastPlayed: st.lastPlayed || null
  }
}

function removeRecent(state, id) {
  var st = state || emptyState()
  var key = str(id)
  var recents = []
  var list = asList(st.recents)
  for (var i = 0; i < list.length; i++) if (list[i] && list[i].id !== key) recents.push(list[i])
  return {
    version: STATE_VERSION,
    favorites: asList(st.favorites).slice(),
    recents: recents,
    lastPlayed: st.lastPlayed || null
  }
}

// Trim recents to the configured cap (settings can shrink after the fact).
function trimRecents(state, max) {
  var st = state || emptyState()
  var cap = max > 0 ? Math.floor(max) : 10
  var list = asList(st.recents)
  if (list.length <= cap) return st
  return {
    version: STATE_VERSION,
    favorites: asList(st.favorites).slice(),
    recents: list.slice(0, cap),
    lastPlayed: st.lastPlayed || null
  }
}

// Session-only failure memory (R11): { id: "HH:MM" }. New objects every time.
function withFailed(failed, id, clock) {
  var out = {}
  var src = failed && typeof failed === "object" ? failed : {}
  for (var k in src) out[k] = src[k]
  if (str(id) !== "") out[str(id)] = str(clock)
  return out
}

function withoutFailed(failed, id) {
  var out = {}
  var src = failed && typeof failed === "object" ? failed : {}
  for (var k in src) if (k !== str(id)) out[k] = src[k]
  return out
}

// ------------------------------------------------------------ caches

function parseJsonObject(text) {
  var raw = str(text).replace(/^\s+|\s+$/g, "")
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

// epg-now.json -> { channels: {tvgId: {now, next}}, meta }
function parseEpgNow(text) {
  var doc = parseJsonObject(text)
  if (!doc || !doc.channels || typeof doc.channels !== "object" || Array.isArray(doc.channels)) return { ok: false, channels: {}, meta: {} }
  var meta = {}
  for (var key in doc) if (key !== "channels") meta[key] = doc[key]
  return { ok: true, channels: doc.channels, meta: meta }
}

// Helper status JSON -> normalized object the UI can render directly.
// Tolerates unknown keys; a bare string error is upgraded to the object
// form; numeric counters (`channelCount`, `groupCount`, `matched`) are
// coerced so bindings never see strings.
function parseHelperStatus(text, kind) {
  var doc = parseJsonObject(text)
  if (!doc) return { ok: false, kind: kind || "", stale: false, error: { code: "no_output", message: "helper produced no JSON" } }
  if (doc.error && typeof doc.error === "string") doc.error = { code: "error", message: doc.error }
  if (doc.error && typeof doc.error === "object") {
    doc.error = { code: str(doc.error.code) || "error", message: str(doc.error.message) || "helper reported failure" }
  }
  if (doc.ok !== true && !doc.error) doc.error = { code: "error", message: "helper reported failure" }
  if (doc.ok === true) doc.error = null
  if (!doc.kind) doc.kind = kind || ""
  doc.stale = doc.stale === true
  var counters = ["channelCount", "groupCount", "matched", "programmeCount", "fetchedAt", "durationMs"]
  for (var i = 0; i < counters.length; i++) {
    if (doc[counters[i]] !== undefined && doc[counters[i]] !== null) {
      var n = Number(doc[counters[i]])
      doc[counters[i]] = isFinite(n) ? n : 0
    }
  }
  if (doc.warnings !== undefined) doc.warnings = asList(doc.warnings)
  return doc
}

var HTTP_REASONS = { 401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 429: "Too Many Requests" }

// Short, credential-free reason per UX 6.3. Maps helper error codes first,
// then falls back to a scrubbed message.
function statusReason(status) {
  if (!status || status.ok === true || !status.error) return ""
  var code = str(status.error.code)
  var message = str(status.error.message)
  var http = code.match(/^http_(\d{3})$/)
  if (http) {
    var n = Number(http[1])
    return "HTTP " + n + (HTTP_REASONS[n] ? " " + HTTP_REASONS[n] : "")
  }
  if (code === "network") {
    if (/timed? ?out/i.test(message)) return "Timed out"
    if (/resolve|name or service|nodename|getaddrinfo|no address/i.test(message)) return "Could not resolve host"
    if (/refused/i.test(message)) return "Connection refused"
    if (/certificate|ssl|tls/i.test(message)) return "TLS error"
    return "Network error"
  }
  var table = {
    not_found: "File not found",
    unsafe_path: "Path not allowed",
    unsupported_scheme: "Unsupported URL",
    too_large: "Source too large",
    bad_gzip: "Bad gzip data",
    empty_playlist: "Playlist has no channels",
    not_m3u: "Not an M3U file",
    not_xmltv: "Not an XMLTV file",
    no_source: "No playlist configured",
    not_implemented: "Helper command not implemented",
    no_output: "Helper produced no output",
    not_running: "mpv is not running",
    unknown_channel: "Unknown channel",
    ipc_error: "mpv did not answer"
  }
  if (table[code]) return table[code]
  return scrubUrls(message) || "Unknown error"
}

function statusHost(status) {
  return status && status.sourceHost ? str(status.sourceHost) : ""
}

function statusHealthy(status) {
  return !!(status && status.ok === true && status.running !== false)
}

// ------------------------------------------------------------ settings

// Our inline settings live on the bar layout entry (shell.json bar.layout.*).
// Returns the entry object or {} so callers can read keys with fallbacks.
function findBarEntry(barConfig, pluginId) {
  var id = str(pluginId)
  if (!barConfig || typeof barConfig !== "object" || !barConfig.layout || typeof barConfig.layout !== "object") return {}
  var sections = ["left", "center", "right"]
  for (var s = 0; s < sections.length; s++) {
    var entries = barConfig.layout[sections[s]]
    if (!Array.isArray(entries)) continue
    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i]
      if (typeof entry === "string" && entry === id) return { id: id }
      if (entry && typeof entry === "object" && str(entry.id) === id) return entry
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

function clampSetting(key, value) {
  var range = SETTING_RANGES[key]
  if (!range) return value
  return clampInt(value, range.def, range.min, range.max)
}

// Every setting the plugin knows, clamped (R2). Unknown keys are ignored.
function settingsFrom(entry) {
  return {
    playlistUrl: str(settingOf(entry, "playlistUrl", "")).replace(/^\s+|\s+$/g, ""),
    epgUrl: str(settingOf(entry, "epgUrl", "")).replace(/^\s+|\s+$/g, ""),
    refreshMinutes: clampSetting("refreshMinutes", settingOf(entry, "refreshMinutes", SETTING_RANGES.refreshMinutes.def)),
    mpvArgs: str(settingOf(entry, "mpvArgs", "")),
    showChannelName: settingOf(entry, "showChannelName", true) !== false && str(settingOf(entry, "showChannelName", true)) !== "false",
    maxRecents: clampSetting("maxRecents", settingOf(entry, "maxRecents", SETTING_RANGES.maxRecents.def)),
    barLabelMaxWidth: clampSetting("barLabelMaxWidth", settingOf(entry, "barLabelMaxWidth", SETTING_RANGES.barLabelMaxWidth.def))
  }
}

// ------------------------------------------------------------ mpv

// mpvArgs is one string of whitespace-separated `--key[=value]` tokens.
// Anything else (including reserved options) is rejected, never guessed.
function splitMpvArgs(text) {
  var args = []
  var rejected = []
  var parts = str(text).split(/\s+/)
  for (var i = 0; i < parts.length; i++) {
    var token = parts[i]
    if (token === "") continue
    var ok = /^--[a-z0-9][a-z0-9-]*(=.*)?$/.test(token)
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
    var value = str(headers[name])
    if (!/^[A-Za-z0-9-]+$/.test(name) || /[\r\n]/.test(value)) continue
    var lower = name.toLowerCase()
    if (lower === "user-agent") out.push("--user-agent=" + value)
    else if (lower === "referer" || lower === "referrer") out.push("--referrer=" + value)
    else out.push("--http-header-fields-append=" + name + ": " + value)
  }
  return out
}

// mpv property-expands `--title` (man mpv: "Properties are expanded"), so a
// playlist entry named "${path}" would put the stream URL, credentials and
// all, into the window title (S-01, R12). "$>" turns expansion off for the
// rest of the string; verified on mpv 0.41 with `expand-text` over IPC:
// "$>${path}" stays literal. `force-media-title` is NOT expanded (verified:
// media-title returned "$>${path}" verbatim), so it carries the plain name;
// a prefix there would show up literally in the OSC and `media-title`.
// The helper's cmd_play applies the same prefix on the IPC path.
var MPV_RAW_PREFIX = "$>"

function mpvWindowTitle(name) {
  return MPV_RAW_PREFIX + str(name)
}

// Full argv for the first launch (ARCHITECTURE.md section 3). The URL always
// follows "--" so a playlist entry can never be parsed as an mpv option.
function buildMpvArgv(params) {
  var p = params || {}
  var name = str(p.name) || "IPTV"
  var argv = [
    "mpv",
    "--input-ipc-server=" + str(p.socketPath),
    "--wayland-app-id=omarchy-iptv",
    "--force-window=immediate",
    "--idle=no",
    "--keep-open=no",
    "--title=" + mpvWindowTitle(name),
    "--force-media-title=" + name,
    "--msg-level=all=error",
    // Live streams never need yt-dlp; without this mpv shells out to it on
    // every dead URL (seconds of delay and noise per failed zap). User
    // mpvArgs come later, so `--ytdl=yes` can re-enable it.
    "--ytdl=no"
  ]
  argv = argv.concat(headerArgs(p.headers))
  argv = argv.concat(asList(p.extraArgs))
  argv.push("--")
  argv.push(str(p.url))
  return argv
}

// argv for `hyprctl dispatch focuswindow class:omarchy-iptv` (R9).
function focusPlayerArgv() {
  return ["hyprctl", "dispatch", "focuswindow", "class:omarchy-iptv"]
}

// ------------------------------------------------------------ notifications

// argv for omarchy-notification-send per UX 6.4. Bodies never carry a URL.
function notifyArgv(event, params) {
  var p = params || {}
  var spec = null
  var name = str(p.name) || "Channel"
  var reason = scrubUrls(str(p.reason))
  if (event === "streamFailed") {
    spec = { title: "Stream failed", body: name + " did not play" + (reason !== "" ? SEP + reason : ""), glyph: GLYPHS.tvOff, urgency: "normal", id: NOTIFY_IDS.streamFailed }
  } else if (event === "playlistRefreshed") {
    spec = { title: "Playlist refreshed", body: pluralChannels(p.channelCount) + " in " + formatCount(p.groupCount) + (Number(p.groupCount) === 1 ? " group" : " groups"), glyph: GLYPHS.refresh, urgency: "low", id: NOTIFY_IDS.playlistRefreshed }
  } else if (event === "playlistError") {
    var tail = p.cachedAt ? "Using cached copy from " + str(p.cachedAt) + "." : "Open the guide for details."
    spec = { title: "Playlist error", body: "Could not fetch the playlist (" + (reason || "unknown error") + "). " + tail, glyph: GLYPHS.alert, urgency: "normal", id: NOTIFY_IDS.playlistError }
  } else if (event === "epgError") {
    spec = { title: "Guide data error", body: "Could not fetch the EPG (" + (reason || "unknown error") + "). Channels still work.", glyph: GLYPHS.alert, urgency: "low", id: NOTIFY_IDS.epgError }
  } else if (event === "mpvMissing") {
    spec = { title: "mpv not found", body: "Install mpv to play channels.", glyph: GLYPHS.tvOff, urgency: "critical", id: NOTIFY_IDS.mpvMissing }
  }
  if (!spec) return null
  return ["omarchy-notification-send", "--app-name", "IPTV", "-u", spec.urgency, "-g", spec.glyph, "-r", String(spec.id), spec.title, spec.body]
}

// ------------------------------------------------------------ privacy

// "scheme://host" for http(s) URLs, "local file" for paths, "" otherwise.
// Never returns path, query or userinfo (credentials live there).
function sourceLabel(url) {
  var text = str(url).replace(/^\s+|\s+$/g, "")
  if (text === "") return ""
  if (/^file:/i.test(text)) return "local file"
  var m = text.match(/^([a-z][a-z0-9+.-]*):\/\/(?:[^@\/\s]*@)?([^\/\s?#:]+)(?::\d+)?/i)
  if (m) {
    var scheme = m[1].toLowerCase()
    if (scheme === "file") return "local file"
    return scheme + "://" + m[2]
  }
  if (text.charAt(0) === "/" || text.charAt(0) === "~") return "local file"
  return "unknown source"
}

function hostOf(url) {
  var label = sourceLabel(url)
  var at = label.indexOf("://")
  return at === -1 ? label : label.substring(at + 3)
}

// Replace every `scheme://...` in free text by its host alone (R12, D-QA-01):
// userinfo, port, path and query are gone. Applied at every sink that can
// carry mpv or helper output (notifications, lastError, console, tooltips).
function redactUrls(text) {
  return str(text).replace(/[a-z][a-z0-9+.-]*:\/\/(?:[^@\/\s]*@)?([^\/\s?#:]*)[^\s]*/gi, function(all, host) {
    return host !== "" ? host : "[url]"
  })
}

// Older name kept for callers; same behaviour.
function scrubUrls(text) {
  return redactUrls(text)
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

function formatCount(n) {
  var v = Math.floor(Number(n) || 0)
  var s = String(Math.abs(v))
  var out = ""
  while (s.length > 3) {
    out = "," + s.substring(s.length - 3) + out
    s = s.substring(0, s.length - 3)
  }
  return (v < 0 ? "-" : "") + s + out
}

function pluralChannels(n) {
  var v = Math.floor(Number(n) || 0)
  return formatCount(v) + (v === 1 ? " channel" : " channels")
}

// Fraction of the current programme elapsed, clamped to 0..1 (UX 5.6).
function epgFraction(nowSec, start, stop) {
  var t = Number(nowSec), a = Number(start), b = Number(stop)
  if (!isFinite(t) || !isFinite(a) || !isFinite(b) || b <= a) return 0
  return Math.max(0, Math.min(1, (t - a) / (b - a)))
}

// epg-now entry -> flat row fields. An expired `now` (stop <= nowSec) yields
// no current programme so a row never shows a stale title; `next` is kept.
function epgFields(entry, nowSec) {
  var out = { nowTitle: "", nowStart: 0, nowStop: 0, nextTitle: "", nextStart: 0, until: "", fraction: 0 }
  if (!entry || typeof entry !== "object") return out
  var t = Number(nowSec) || 0
  var cur = entry.now
  if (cur && cur.title) {
    var stop = Number(cur.stop) || 0
    var start = Number(cur.start) || 0
    if (!t || stop <= 0 || stop > t) {
      out.nowTitle = str(cur.title)
      out.nowStart = start
      out.nowStop = stop
      out.until = stop > 0 ? formatClock(stop) : ""
      out.fraction = epgFraction(t, start, stop)
    }
  }
  var next = entry.next
  if (next && next.title) {
    out.nextTitle = str(next.title)
    out.nextStart = Number(next.start) || 0
  }
  return out
}

// Backwards-compatible strings for callers that only want text.
function formatEpgLine(entry, nowSec) {
  var f = epgFields(entry, nowSec)
  var out = { now: "", next: "" }
  if (f.nowTitle !== "") out.now = "Now: " + f.nowTitle + (f.until !== "" ? " until " + f.until : "")
  if (f.nextTitle !== "") out.next = "Next: " + f.nextTitle + (f.nextStart > 0 ? " at " + formatClock(f.nextStart) : "")
  return out
}

function joinParts(parts) {
  var out = []
  var list = asList(parts)
  for (var i = 0; i < list.length; i++) if (str(list[i]) !== "") out.push(str(list[i]))
  return out.join(SEP)
}

// Row detail line (UX 2.4): `Group - Now: X - Next: Y`, group omitted inside
// its own group, EPG segments replaced by the failure notice when set.
function rowDetail(opts) {
  var o = opts || {}
  var parts = []
  if (o.showGroup) parts.push(str(o.group))
  if (str(o.failedAt) !== "") {
    parts.push("Failed " + str(o.failedAt))
    parts.push("Space to retry")
    return joinParts(parts)
  }
  if (str(o.nowTitle) !== "") parts.push("Now: " + str(o.nowTitle))
  if (str(o.nextTitle) !== "") parts.push("Next: " + str(o.nextTitle))
  return joinParts(parts)
}

// Accessible name for a channel row (UX 7.1).
function rowAccessibleName(opts) {
  var o = opts || {}
  var out = str(o.name)
  if (o.favorite) out += ", favorite"
  if (o.playing) out += ", playing"
  if (str(o.nowTitle) !== "") out += ", now " + str(o.nowTitle) + (str(o.until) !== "" ? " until " + str(o.until) : "")
  if (str(o.failedAt) !== "") out += ", failed"
  return out
}

function elide(text, max) {
  var value = str(text)
  var limit = max > 3 ? Math.floor(max) : 3
  return value.length > limit ? value.substring(0, limit - 1) + ELLIPSIS : value
}

function noMatchesTitle(query, scopeId) {
  var name = scopeName(effectiveScope(scopeId, query))
  var base = "No matches for " + QUOTE_OPEN + str(query) + QUOTE_CLOSE
  return name === "All" ? base : base + " in " + name
}

// ------------------------------------------------------------ bar widget

// R7: glyph per state, never color-only.
function barGlyph(opts) {
  var o = opts || {}
  if (o.playing) return GLYPHS.tvPlay
  if (o.error) return GLYPHS.tvOff
  return GLYPHS.tv
}

// UX 6.3 tooltips. `serviceMissing` wins (ARCHITECTURE.md section 7).
function barTooltip(opts) {
  var o = opts || {}
  if (o.serviceMissing) return "IPTV" + SEP + "service not loaded, run omarchy restart shell"
  if (o.playing && str(o.name) !== "") return "Playing " + str(o.name)
  if (o.refreshing) return "IPTV" + SEP + "refreshing playlist" + ELLIPSIS
  if (!o.configured) return "IPTV" + SEP + "no playlist configured"
  if (o.error) return "IPTV" + SEP + "playlist error, open the guide"
  return "IPTV" + SEP + "click to open the guide"
}

function barAccessibleName(opts) {
  var o = opts || {}
  if (o.playing && str(o.name) !== "") return "IPTV, playing " + str(o.name)
  if (o.error) return "IPTV, playlist error"
  return "IPTV, idle"
}

// ------------------------------------------------------------ footer

// Footer status (UX 6.1). Priority: transient > bounded search > playing >
// EPG pending > counts.
function footerStatus(opts) {
  var o = opts || {}
  if (str(o.transient) !== "") return str(o.transient)
  if (o.truncated) return "First " + formatCount(o.cap || MAX_ROWS_DEFAULT) + " of " + formatCount(o.resultTotal) + SEP + "keep typing"
  if (str(o.playingName) !== "") return GLYPHS.play + " " + str(o.playingName) + SEP + "s stop"
  if (o.refreshing) return "Refreshing" + ELLIPSIS
  if (o.epgPending) return "Guide data loading" + ELLIPSIS
  var out = pluralChannels(o.count)
  if (str(o.lastUpdated) !== "") out += SEP + (o.stale ? "cached " + str(o.lastUpdated) + SEP + "offline" : "updated " + str(o.lastUpdated))
  else if (o.stale) out += SEP + "cached" + SEP + "offline"
  return out
}

// Footer hint pairs [key, verb] (UX 6.2); the guide styles keys and verbs at
// different opacities.
function footerHints(opts) {
  var o = opts || {}
  if (o.empty === "loading") return [["Esc", "close"]]
  if (o.empty) return [["r", "reload"], ["Esc", "close"]]
  if (o.mode === "list") {
    return [["j/k", "move"], ["h/l", "group"], ["Enter", "play"], ["Space", "preview"], ["f", "favorite"], ["s", "stop"], ["r", "refresh"], ["/", "search"]]
  }
  if (str(o.query) !== "") {
    return [["Enter", "play"], ["Up/Down", "move"], ["Left/Right", "narrow"], ["Tab", "keys"], ["Esc", "clear"]]
  }
  return [["Enter", "play"], ["Up/Down", "move"], ["Left/Right", "group"], ["Tab", "keys"], ["Esc", "close"]]
}

if (typeof module !== "undefined") {
  module.exports = {
    MAX_ROWS_DEFAULT: MAX_ROWS_DEFAULT,
    FAVORITES_GROUP: FAVORITES_GROUP,
    RECENT_GROUP: RECENT_GROUP,
    UNGROUPED: UNGROUPED,
    SCOPE_RECENT: SCOPE_RECENT,
    SCOPE_FAVORITES: SCOPE_FAVORITES,
    SCOPE_ALL: SCOPE_ALL,
    GROUP_SCOPE_PREFIX: GROUP_SCOPE_PREFIX,
    ELLIPSIS: ELLIPSIS,
    QUOTE_OPEN: QUOTE_OPEN,
    QUOTE_CLOSE: QUOTE_CLOSE,
    SEP: SEP,
    GLYPHS: GLYPHS,
    SETTING_RANGES: SETTING_RANGES,
    NOTIFY_IDS: NOTIFY_IDS,
    FOLD_GROUPS: FOLD_GROUPS,
    asList: asList,
    normalizeText: normalizeText,
    searchKey: searchKey,
    tokenize: tokenize,
    fnv1a32: fnv1a32,
    channelId: channelId,
    indexById: indexById,
    findByUrl: findByUrl,
    primaryGroup: primaryGroup,
    prepareChannels: prepareChannels,
    matchRank: matchRank,
    filterChannels: filterChannels,
    groupChannels: groupChannels,
    groupScopeId: groupScopeId,
    isGroupScope: isGroupScope,
    isPinnedScope: isPinnedScope,
    scopeName: scopeName,
    scopeEntries: scopeEntries,
    channelsForScope: channelsForScope,
    channelsInGroup: channelsInGroup,
    effectiveScope: effectiveScope,
    moveScope: moveScope,
    scopeIndex: scopeIndex,
    initialScope: initialScope,
    cursorFor: cursorFor,
    scopeLabel: scopeLabel,
    guideState: guideState,
    withQuery: withQuery,
    withScope: withScope,
    withMode: withMode,
    withCursor: withCursor,
    toggleMode: toggleMode,
    onEscape: onEscape,
    moveCursor: moveCursor,
    launchScope: launchScope,
    zapRing: zapRing,
    nextInGroup: nextInGroup,
    emptyState: emptyState,
    parseState: parseState,
    isFavorite: isFavorite,
    toggleFavorite: toggleFavorite,
    pushRecent: pushRecent,
    recordPlayed: recordPlayed,
    withFavorites: withFavorites,
    removeRecent: removeRecent,
    trimRecents: trimRecents,
    withFailed: withFailed,
    withoutFailed: withoutFailed,
    parseJsonObject: parseJsonObject,
    parseChannels: parseChannels,
    parseEpgNow: parseEpgNow,
    parseHelperStatus: parseHelperStatus,
    statusReason: statusReason,
    statusHost: statusHost,
    statusHealthy: statusHealthy,
    findBarEntry: findBarEntry,
    settingOf: settingOf,
    clampInt: clampInt,
    clampSetting: clampSetting,
    settingsFrom: settingsFrom,
    splitMpvArgs: splitMpvArgs,
    headerArgs: headerArgs,
    MPV_RAW_PREFIX: MPV_RAW_PREFIX,
    mpvWindowTitle: mpvWindowTitle,
    buildMpvArgv: buildMpvArgv,
    focusPlayerArgv: focusPlayerArgv,
    notifyArgv: notifyArgv,
    sourceLabel: sourceLabel,
    hostOf: hostOf,
    redactUrls: redactUrls,
    scrubUrls: scrubUrls,
    displayName: displayName,
    looksLikeUrl: looksLikeUrl,
    formatClock: formatClock,
    formatCount: formatCount,
    pluralChannels: pluralChannels,
    epgFraction: epgFraction,
    epgFields: epgFields,
    formatEpgLine: formatEpgLine,
    joinParts: joinParts,
    rowDetail: rowDetail,
    rowAccessibleName: rowAccessibleName,
    elide: elide,
    noMatchesTitle: noMatchesTitle,
    barGlyph: barGlyph,
    barTooltip: barTooltip,
    barAccessibleName: barAccessibleName,
    footerStatus: footerStatus,
    footerHints: footerHints
  }
}
