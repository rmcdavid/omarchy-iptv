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
// Helper-side cap on channels.json (bin/omarchy-iptv MAX_CHANNELS, S-07);
// prepareChannels re-applies it so a hand-edited cache stays bounded too.
var MAX_CHANNELS = 50000
// Player shutdown ladder (D-LIVE-17): `quit` over IPC, SIGTERM once
// STOP_QUIT_GRACE_MS pass without an exit, SIGKILL after another
// STOP_KILL_GRACE_MS. An mpv that never answers IPC and ignores SIGTERM
// (wedged, or SIGSTOPped) is gone within about 4 s of a stop and its
// Process exit is always observed, so nowPlaying and the bar never go stale.
var STOP_QUIT_GRACE_MS = 2000
var STOP_KILL_GRACE_MS = 2000
// Health ticks that find a helper call in flight are skipped; this many in
// a row count as a failed check, so a player whose every call runs to its
// deadline cannot starve the check forever (D-LIVE-17).
var HEALTH_SKIPS_BEFORE_RESTART = 3
// Detached player (ARCHITECTURE-PLAYER.md 4.6, 4.14): the schema of both
// `user-data` nodes mpv carries for us, the orphan-check grace, and the
// reason shown when the player died without telling us why (a crash, a
// SIGKILL, or no `end-file` at all).
var PLAYER_STASH_SCHEMA = 1
var PLAYER_ORPHAN_GRACE_SEC = 6
var PLAYER_GENERIC_FAILURE = "Playback stopped unexpectedly"
// The event router's two bounds (4.8): how many mpv log lines are kept for
// the failure text, and how deep the playlist_entry_id -> channel ring goes.
// Both are memory only and both are what Service.qml has always used.
var PLAYER_LOG_TAIL = 5
var PLAYER_ENTRY_OWNERS = 4
var FAVORITES_GROUP = "Favorites"
var RECENT_GROUP = "Recent"
var UNGROUPED = "Ungrouped"
// state.json schema (docs/ARCHITECTURE-SOURCES.md 2.1): version 2 adds the
// `sources` history and `cacheLayout`; parseState still reads version 1.
// The optional nullable `session` key (docs/ARCHITECTURE-PLAYER.md 8) is
// additive and does NOT bump this: both readers whitelist the keys they
// know, so an older build drops it and a newer one reads its absence.
var STATE_VERSION = 2

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
  history: "\udb80\udeda",   // U+F02DA nf-md-history           recent
  // Sources screens (UX-SOURCES.md 4.6)
  sources: "\udb81\udc11",   // U+F0411 nf-md-playlist_play     pinned Sources row
  check: "\udb80\udd2c",     // U+F012C nf-md-check             active source marker
  eye: "\udb80\ude08",       // U+F0208 nf-md-eye               reveal a masked URL
  eyeOff: "\udb80\ude09",    // U+F0209 nf-md-eye_off           hide it again
  plus: "\udb81\udc15",      // U+F0415 nf-md-plus              Add source row
  key: "\udb80\udf06",       // U+F0306 nf-md-key               Add Xtream login row
  pencil: "\udb80\udfeb",    // U+F03EB nf-md-pencil            edit action button
  closeCircle: "\udb80\udd59" // U+F0159 nf-md-close_circle     remove action button
}

// Settings clamps (R2). `showChannelName` is `!== false`; strings are trimmed.
var SETTING_RANGES = {
  refreshMinutes: { def: 360, min: 15, max: 1440 },
  maxRecents: { def: 10, min: 1, max: 50 },
  barLabelMaxWidth: { def: 180, min: 60, max: 600 }
}

// mpv options the user may not override through the mpvArgs setting because
// the service depends on them (socket, window identity, exit semantics).
// The ten additions below (ARCHITECTURE-PLAYER.md 4.12) are not invariants of
// the service: each one writes the credentialed stream URL somewhere durable
// or on screen, which is the very exposure M2-02 closes (S-03). `--ytdl` is
// deliberately NOT reserved (PO-5): re-enabling yt-dlp is the documented
// escape hatch for non-direct URLs.
var MPV_RESERVED = {
  "--input-ipc-server": true,
  "--wayland-app-id": true,
  "--title": true,
  "--force-media-title": true,
  "--idle": true,
  "--input-ipc-client": true,
  "--script": true,
  "--scripts": true,
  "--config-dir": true,
  "--log-file": true,             // 0644, forced -v -v, writes the URL per failed load
  "--dump-stats": true,           // on-disk file carrying the command line
  "--stream-record": true,        // writes the stream itself to disk
  "--save-position-on-quit": true, // watch-later file whose header is the stream path
  "--watch-later-dir": true,
  "--osd-msg1": true,             // property-expanding: ${path} on screen and in screenshots
  "--osd-msg2": true,
  "--osd-msg3": true,
  "--term-status-msg": true,      // property-expanding into a terminal
  "--screenshot-template": true   // property-expanding into file names
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

// A rendered name never starts with "-" (S-04): it is handed to
// omarchy-notification-send as an argv item, and a body such as
// "--urgency=x did not play" would be parsed as an option and suppress the
// toast. Leading dashes and whitespace are dropped; an all-dash name falls
// through to the next candidate. Mirrors clean_name in bin/omarchy-iptv.
function cleanName(text) {
  return str(text).replace(/^[\s-]+/, "").replace(/\s+$/, "")
}

function displayName(channel, position) {
  var name = cleanName(channel && channel.name)
  if (name !== "" && !looksLikeUrl(name)) return name
  var tvg = cleanName(channel && channel.tvgName)
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
  for (var i = 0; i < list.length && out.length < MAX_CHANNELS; i++) {
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
// The cap applies to SEARCH results only (R3, UX 2.6): with no query every
// channel of the scope is returned (the same array, never a copy) so the
// guide can browse all of them; its ListView instantiates visible rows only
// (D-LIVE-01). Callers must not mutate the returned rows.
function filterChannels(channels, query, limit, favorites) {
  var list = asList(channels)
  var max = limit > 0 ? Math.floor(limit) : MAX_ROWS_DEFAULT
  var tokens = tokenize(query)
  if (tokens.length === 0) {
    return { rows: list, total: list.length, truncated: false }
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
// The synthetic `Ungrouped` bucket is always the last group, wherever its
// first channel sits in the playlist (UX 2.2 item 4, D-LIVE-06).
function groupChannels(channels) {
  var list = asList(channels)
  var seen = {}
  var order = []
  var ungrouped = null
  for (var i = 0; i < list.length; i++) {
    if (!list[i]) continue
    var name = primaryGroup(list[i])
    if (seen[name] === undefined) {
      seen[name] = { name: name, kind: "group", count: 0 }
      if (name === UNGROUPED) ungrouped = seen[name]
      else order.push(seen[name])
    }
    seen[name].count++
  }
  if (ungrouped !== null) order.push(ungrouped)
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

// Where the group column sits for the selected scope (UX 2.2 / 2.3,
// D-LIVE-16): a pinned entry (Recent, Favorites, All) shows the column from
// the top so every pinned entry is visible; a group is brought into view
// (ListView.Contain). index is -1 when the scope is not in the column.
function columnAnchor(entries, scopeId) {
  var index = scopeIndex(entries, scopeId)
  return { index: index, top: index >= 0 && isPinnedScope(scopeId) }
}

// A scope that is no longer in the column (the last Recent entry removed, a
// group gone after a refresh) must not keep the cursor on a hidden entry:
// fall back to Favorites when it has channels, else All (UX 2.2, D-LIVE-07).
// A scope that is still listed is returned unchanged.
function fallbackScope(entries, scopeId) {
  var list = asList(entries)
  var id = str(scopeId) || SCOPE_ALL
  if (list.length === 0) return id
  var favorites = 0
  for (var i = 0; i < list.length; i++) {
    var entry = list[i]
    if (!entry || entry.kind === "header" || str(entry.id) === "") continue
    if (entry.id === id) return id
    if (entry.id === SCOPE_FAVORITES) favorites = Number(entry.count) || 0
  }
  return favorites > 0 ? SCOPE_FAVORITES : SCOPE_ALL
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

// Pure reducer for the keyboard modes (UX 3, R1; UX-SOURCES 1.9). Guide.qml
// keeps one object and replaces it on every transition so bindings notice.
// `search` and `list` are the shipped guide modes; `sources`, `sourceEdit`,
// `sourceXtream` and `confirmRemove` are the Sources screens. `returnMode`
// remembers where Sources was opened from, `form` holds the open form
// (section "sources" below), `sourceCursor` is the Sources list cursor.
var GUIDE_MODES = ["search", "list", "sources", "sourceEdit", "sourceXtream", "confirmRemove"]

function guideMode(mode) {
  var m = str(mode)
  return GUIDE_MODES.indexOf(m) === -1 ? "search" : m
}

function guideState(scopeId) {
  return { mode: "search", query: "", scopeId: str(scopeId) || SCOPE_ALL, restoreScopeId: "", cursorIndex: 0, returnMode: "", form: null, sourceCursor: 0 }
}

function copyGuide(st) {
  var src = st || guideState()
  return {
    mode: guideMode(src.mode),
    query: str(src.query),
    scopeId: str(src.scopeId) || SCOPE_ALL,
    restoreScopeId: str(src.restoreScopeId),
    cursorIndex: Number(src.cursorIndex) || 0,
    returnMode: str(src.returnMode),
    form: src.form ? copyForm(src.form) : null,
    sourceCursor: Math.max(0, Math.floor(Number(src.sourceCursor) || 0))
  }
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
  next.mode = guideMode(mode)
  return next
}

function withCursor(st, index) {
  var next = copyGuide(st)
  next.cursorIndex = Math.max(0, Math.floor(Number(index) || 0))
  return next
}

// Tab / Shift+Tab / "/" toggle between the guide modes (UX 3.1, 3.2). No-op
// on the Sources screens (UX-SOURCES 2.2: Tab is ignored there).
function toggleMode(st) {
  var cur = copyGuide(st)
  if (cur.mode !== "list" && cur.mode !== "search") return cur
  return withMode(cur, cur.mode === "list" ? "search" : "list")
}

// Esc, per mode (UX 3 and UX-SOURCES 2.3): the guide clears a non-empty
// query, else closes; Sources returns to `returnMode`; the confirm dialog
// returns to Sources; a form opened from Sources cancels in one press; a
// first-run form clears the focused field first, then moves to another
// field that still has text, and only closes (or returns to its parent
// form) when every field is empty. While a probe runs, Esc cancels it and
// thaws the form (`cancelProbe` tells the caller to ask the service).
// `opts` reaches closeSources (`configured`, UX 1.7).
function onEscape(st, opts) {
  var cur = copyGuide(st)
  var out = { state: cur, close: false, cancelProbe: false }
  if (cur.mode === "confirmRemove") { out.state = withMode(cur, "sources"); return out }
  if (cur.mode === "sources") { out.state = closeSources(cur, opts); return out }
  if (cur.mode === "sourceEdit" || cur.mode === "sourceXtream") {
    var f = cur.form
    if (!f) { out.state = withMode(cur, "search"); return out }
    if (f.probing) { out.state = withFormProbing(cur, false); out.cancelProbe = true; return out }
    if (f.origin !== "firstRun") return closeForm(cur, "cancel")
    if (isFormField(f, f.focus) && str(f.values[f.focus]) !== "") { out.state = withFormValue(cur, f.focus, ""); return out }
    var other = firstFieldWithText(f)
    if (other !== "") { out.state = withFormFocus(cur, other); return out }
    if (f.parent) return closeForm(cur, "cancel")
    out.close = true
    return out
  }
  if (cur.query !== "") { out.state = withQuery(cur, ""); return out }
  out.close = true
  return out
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
  return { version: STATE_VERSION, cacheLayout: 0, favorites: [], recents: [], lastPlayed: null, session: null, sources: [] }
}

// One `{id, name, at}` record: the shape a `recents` entry, `lastPlayed`
// and `session` all share (python mirror: `normalize_played`). A value
// without an `id` is dropped, which is also how a state file written
// before the key existed reads its missing `session` as null.
function playedRecord(entry) {
  if (!entry || typeof entry !== "object" || !entry.id) return null
  // Math.trunc, not Math.floor: python's int() truncates toward zero, and the
  // shared fixture pins the two readers to the same answer on the same bytes.
  return { id: String(entry.id), name: str(entry.name), at: Math.trunc(Number(entry.at)) || 0 }
}

// Every reducer builds its result here so `sources` and `cacheLayout` are
// carried through favorites / recents changes (ARCHITECTURE-SOURCES 2.1).
function cloneState(state, patch) {
  var st = state || emptyState()
  var out = {
    version: STATE_VERSION,
    cacheLayout: Number(st.cacheLayout) === CACHE_LAYOUT ? CACHE_LAYOUT : 0,
    favorites: asList(st.favorites).slice(),
    recents: asList(st.recents).slice(),
    lastPlayed: st.lastPlayed || null,
    session: st.session || null,
    sources: asList(st.sources).slice()
  }
  var p = patch || {}
  for (var key in p) if (key !== "version") out[key] = p[key]
  return out
}

function withCacheLayout(state, layout) {
  return cloneState(state, { cacheLayout: Number(layout) === CACHE_LAYOUT ? CACHE_LAYOUT : 0 })
}

// v1 (no `sources`) and v2 text both yield a v2 object (ARCHITECTURE-SOURCES
// 2.2); records failing the field rules are dropped, duplicate `url` or
// `key` keeps the first, the array is capped at MAX_SOURCES.
function parseState(text) {
  var state = emptyState()
  var parsed = parseJsonObject(text)
  if (!parsed) return state
  state.cacheLayout = Number(parsed.cacheLayout) === CACHE_LAYOUT ? CACHE_LAYOUT : 0
  var srcs = asList(parsed.sources)
  var seenUrl = {}
  var seenKey = {}
  for (var s = 0; s < srcs.length && state.sources.length < MAX_SOURCES; s++) {
    var rec = normalizeSourceRecord(srcs[s])
    if (!rec) {
      // Logged by key (D-SRC-09); a record without a usable key is silent.
      var badKey = srcs[s] && typeof srcs[s] === "object" ? str(srcs[s].key) : ""
      if (isSourceKey(badKey)) warnState("dropped source " + badKey + " (invalid url)")
      continue
    }
    if (seenUrl[rec.url] || seenKey[rec.key]) continue
    seenUrl[rec.url] = true
    seenKey[rec.key] = true
    state.sources.push(rec)
  }
  var favs = asList(parsed.favorites)
  if (favs.length > 0) {
    for (var i = 0; i < favs.length; i++) {
      var id = str(favs[i])
      if (id !== "" && state.favorites.indexOf(id) === -1) state.favorites.push(id)
    }
  }
  var recs = asList(parsed.recents)
  for (var r = 0; r < recs.length; r++) {
    var entry = playedRecord(recs[r])
    if (entry) state.recents.push(entry)
  }
  state.lastPlayed = playedRecord(parsed.lastPlayed)
  // The detached player's session record (ARCHITECTURE-PLAYER.md 4.6 and
  // section 8): optional, nullable, and no version bump - STATE_VERSION
  // stays 2 because both readers whitelist the keys they know, so a file
  // without it reads as null and a v0.2.0 build simply drops it.
  state.session = playedRecord(parsed.session)
  return state
}

// pushRecent()'s `{id, name, at}` form, for replaying a play that was
// recorded before state.json landed (stateOnLoad).
function pushPlayedRecord(recents, played, max) {
  var rec = playedRecord(played)
  var cap = max > 0 ? Math.floor(max) : 10
  var out = []
  if (rec) out.push(rec)
  var list = asList(recents)
  for (var i = 0; i < list.length && out.length < cap; i++) {
    if (list[i] && (!rec || list[i].id !== rec.id)) out.push(list[i])
  }
  return out
}

// ARCHITECTURE-PLAYER.md section 15's startup race, measured at 14 losses in
// 30 trials, and the other half of the consumption rule above.
//
// state.json is read asynchronously while a play can be issued immediately,
// so the text that arrives is a snapshot of the file from BEFORE anything
// this shell did. Applying it wholesale is the whole race: the session
// record the play had just written is gone, and with it the only evidence
// PO-3 has that the channel died unattended.
//
// The file is the base - it carries favorites, sources and the recents of
// every previous login, none of which this shell can reconstruct. What is
// replayed on top is exactly one thing, the play this shell recorded while
// the read was in flight, because before the first load `userState` IS the
// empty default plus that write, so a `session` there can only be ours.
// `savePending` extends the same reasoning past the first load: a save this
// shell has queued but not yet been allowed to make (saveState()'s dirsReady
// gate) means the file on disk is again older than memory.
//
// Whether a replayed record then SURVIVES is not decided here: it goes to
// sessionAfterOutcome() like every other answer about the record, so there
// stays exactly one place that retires one.
function stateOnLoad(loaded, current, context) {
  var base = loaded || emptyState()
  var ctx = context || {}
  var newer = ctx.loadedBefore !== true || ctx.savePending === true
  var mine = newer ? playedRecord(current && current.session) : null
  if (!mine) return { state: base, replayed: false, write: false }
  var next = cloneState(base, {
    recents: pushPlayedRecord(base.recents, mine, ctx.maxRecents),
    lastPlayed: mine,
    session: mine
  })
  return { state: next, replayed: true, write: next !== base }
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
// on playback success). `lastPlayed` and `session` are the same record
// under two different lifetimes: `lastPlayed` is the Recents memory and
// survives everything, `session` is "what the player was last asked to
// play" and is cleared the moment the player stops or ends cleanly
// (ARCHITECTURE-PLAYER.md section 8). A record left behind therefore means
// the player died with no shell attached to notice, which is the one thing
// a reattach needs in order to mark that channel failed in the guide
// instead of raising a toast minutes late (ruling PO-3). It carries a
// channel id, a display name and a clock - never a URL, because a display
// name is never a URL (prepareChannels) and the id is a tvg-id or a hash.
function recordPlayed(state, channel, max, nowSec) {
  var st = state || emptyState()
  var id = channelId(channel)
  var played = id === "" ? null : { id: id, name: str(channel.name), at: Math.floor(Number(nowSec) || 0) }
  return cloneState(st, {
    recents: pushRecent(st.recents, channel, max, nowSec),
    lastPlayed: played || st.lastPlayed || null,
    session: played || st.session || null
  })
}

// The player stopped, ended cleanly, or its channel has just been marked
// failed on reattach: the session record has done its job. Returns the SAME
// object when there is nothing to clear, so a caller can skip the write.
function clearSession(state) {
  var st = state || emptyState()
  if (!st.session) return st
  return cloneState(st, { session: null })
}

// What the player was last asked to play, or null. Normalizing on the way
// out means a hand-edited or truncated record can never reach the guide as
// half a channel.
function stateSession(state) {
  return state ? playedRecord(state.session) : null
}

// Ruling PO-3, the whole decision. A `player probe` that found nothing
// running, paired with a session record still in state.json, is the evidence
// that the channel the record names died with no shell attached to notice:
// mark it failed in the guide, silently, and clear the record. A toast for
// something that stopped minutes ago, possibly on another login, is noise.
//
// The answer depends on whether the state file has landed yet, because the
// two arrive in either order: the probe fires from Component.onCompleted and
// answers in about 130 ms, while state.json arrives whenever its FileView
// loads. Deciding on a state that has not loaded would read the empty
// default - losing the mark, and, if the caller wrote that result back,
// putting an empty state over the user's file. So an unloaded state yields
// `pending`, which the caller re-runs from its state handler, and never a
// write.
//
// `state` is returned unchanged (the same object) whenever there is nothing
// to clear, so `write` is also "the state actually changed".
function deadSessionVerdict(state, stateLoaded, failed, clock) {
  var marks = failed && typeof failed === "object" ? failed : {}
  if (stateLoaded !== true) return { pending: true, mark: false, id: "", name: "", failed: marks, state: state, write: false }
  var session = stateSession(state)
  if (!session) return { pending: false, mark: false, id: "", name: "", failed: marks, state: state, write: false }
  var cleared = clearSession(state)
  return {
    pending: false,
    mark: true,
    id: session.id,
    name: session.name,
    failed: withFailed(marks, session.id, clock),
    state: cleared,
    write: cleared !== state
  }
}

// ------------------------------------------- the session record's lifetime
//
// The other half of PO-3, and the half that decides whether the mark above is
// ever raised twice for the same event.
//
// recordPlayed() writes the record on the play command; deadSessionVerdict()
// is its ONLY reader, and it reads a SURVIVING record as proof that the
// channel died with no shell attached to notice. So the rule is about the
// witness, not about the failure: a record must never outlive the shell that
// saw how the play ended. Whether the user got a toast and a red row, "mpv
// not found", a clean end that PO-4 keeps silent, or their own stop makes no
// difference - they have had whatever they were going to get, and a mark on
// the next reattach would be a second verdict on an event they already dealt
// with. A record therefore survives exactly one thing: a player that is still
// running or still on its way.
//
// This lives here rather than as a condition per branch in Service.qml
// because that is how the reported defect happened: three of the terminal
// branches wrote the clear and three did not, and nothing outside a running
// shell could call the rule to find out (CLAUDE.md 11, 12).

// Every answer Service.qml can get about the player it asked for, and whether
// the player survives it. `false` is "gone, and nothing is bringing it back".
var PLAYER_OUTCOME_SURVIVES = {
  superseded: true,     // a later intent won the lock; that intent owns the record
  retrying: true,       // busy / no_socket / ipc_error, the backoff is armed
  relaunching: true,    // the health verdict's one automatic relaunch (4.8)
  respawning: true,     // the helper is mid ladder-and-respawn for this very intent (4.9)
  attached: true,       // the first load failed but the socket is live: its EOF is next
  loaded: true,         // not a player answer: state.json arriving (see `consumed` below)
  stopped: false,       // the user stopped it, or a detached stop was confirmed (4.9)
  ended: false,         // socket EOF with no relaunch coming (4.8 signal 3)
  foreign: false,       // a player this shell could not identify, laddered down (4.5)
  failed: false,        // `player start` / `restart` / the first load failed for good
  mpvMissing: false,    // the player program is not installed
  marked: false,        // PO-3's red row has been raised on this record: it is spent
  abandoned: false      // the channel left the playlist before the relaunch could run
}

// The vocabulary, so a test can pin the set instead of trusting a call site's
// spelling: an outcome this does not name is inert (see sessionAfterOutcome).
var PLAYER_OUTCOMES = Object.keys(PLAYER_OUTCOME_SURVIVES)

// The session record after one player outcome. Returns the SAME state object
// whenever nothing changed, so a caller can skip the write - the contract
// clearSession() and deadSessionVerdict() already keep.
//
// `deadPending` is the caller's deferred-PO-3 flag (deadSessionVerdict's
// `pending`: a probe found no player before state.json had landed, so the
// mark is owed once it does). A terminal outcome drops it, because the user
// has now seen the end of this play and the deferred mark would be the
// second word on the same event; a NON-terminal one must leave it alone, or
// a `busy` retry racing the startup probe silently eats a red row that a
// genuine unattended death had earned. It is answered here rather than in
// the component so that something can call the rule.
//
// An outcome this does not know is inert rather than clearing: a misspelled
// call site then costs at worst one stale mark on the next reattach, never a
// silently dropped one, and the vocabulary check in the tests catches it
// before either happens.
function sessionAfterOutcome(state, outcome, deadPending, consumed) {
  var st = state || emptyState()
  var key = str(outcome)
  var known = PLAYER_OUTCOME_SURVIVES.hasOwnProperty(key)
  var terminal = known && PLAYER_OUTCOME_SURVIVES[key] !== true
  // Consumption is one-way, and it is the half the twelve routed branches
  // left open. They retire the record in MEMORY; whether that reaches disk
  // depends on `dirsReady` and on which of state.json's own loads wins the
  // race. When the write loses, the file still carries the record, the next
  // load puts it straight back into memory, and the following shell start
  // marks the same channel red a second time for a failure the user has
  // already been shown - the reported defect, 2 runs in 3. So the answer is
  // not "clear it once" but "a consumed record never comes back": every
  // later call over the same in-memory state, `loaded` included, clears it
  // again until a write finally lands. Only a new play (recordPlayed) opens
  // a fresh record, and the caller drops the flag there.
  var spent = consumed === true || terminal
  var next = spent ? clearSession(st) : st
  return {
    outcome: key,
    known: known,
    terminal: terminal,
    consumed: spent,
    pending: terminal ? false : deadPending === true,
    state: next,
    write: next !== st
  }
}

function withFavorites(state, favorites) {
  return cloneState(state, { favorites: asList(favorites).slice() })
}

function removeRecent(state, id) {
  var st = state || emptyState()
  var key = str(id)
  var recents = []
  var list = asList(st.recents)
  for (var i = 0; i < list.length; i++) if (list[i] && list[i].id !== key) recents.push(list[i])
  return cloneState(st, { recents: recents })
}

// Trim recents to the configured cap (settings can shrink after the fact).
function trimRecents(state, max) {
  var st = state || emptyState()
  var cap = max > 0 ? Math.floor(max) : 10
  var list = asList(st.recents)
  if (list.length <= cap) return st
  return cloneState(st, { recents: list.slice(0, cap) })
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
    timeout: "Timed out",
    helper_timeout: "Helper timed out",
    unsafe_redirect: "Unsafe redirect",
    too_large: "Source too large",
    bad_gzip: "Bad gzip data",
    empty_playlist: "Playlist has no channels",
    not_a_playlist: "Not an M3U playlist",
    not_m3u: "Not an M3U playlist",
    not_xmltv: "Not an XMLTV file",
    no_source: "No playlist configured",
    not_implemented: "Helper command not implemented",
    no_output: "Helper produced no output",
    not_running: "mpv is not running",
    unknown_channel: "Unknown channel",
    ipc_error: "mpv did not answer",
    // Source validation and cache verbs (ARCHITECTURE-SOURCES 2.3, 3.1, 4.3)
    empty: "No playlist configured",
    too_long: "URL too long",
    bad_url: "Invalid URL",
    invalid: "Invalid URL",
    scheme: "Unsupported URL",
    relative_path: "Relative path not allowed",
    bad_key: "Invalid cache key",
    duplicate: "Source already listed",
    too_many: "Too many sources",
    busy: "Another fetch is running",
    unknown_source: "Unknown source",
    not_ready: "Sources not loaded yet",
    persist_failed: "Could not save settings",
    cancelled: "Cancelled"
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

// Warnings of a successful helper run (D-LIVE-18): strings only, every URL
// reduced to its host (R12), empty for a failed run so the caller keeps the
// warnings of the load whose cache is still in use.
function statusWarnings(status) {
  if (!status || status.ok !== true) return []
  var list = asList(status.warnings)
  var out = []
  for (var i = 0; i < list.length; i++) {
    var text = redactUrls(str(list[i])).replace(/^\s+|\s+$/g, "")
    if (text !== "") out.push(text)
  }
  return out
}

// Wording per helper kind; both warning paths share one shape so they can
// never drift apart (UX 6.3 calls the EPG "Guide data", as the banner does).
// `player` is PO-10's: it does not come from a helper run at all, it comes
// from a setting that is in force right now.
var WARNING_PREFIX = { playlist: "Playlist warning: ", epg: "Guide data warning: ", player: "Player warning: " }

// Which kind a warning already declares, "" when it declares none. The
// footer holds ONE line for the whole service and the guide passes it two
// lists, so a third source (the player's own options) would otherwise need a
// third parameter in Guide.qml. Instead an entry may carry its own prefix
// and is then shown as it stands - `labelWarnings` is the only thing that
// puts one on, so a helper's text can never accidentally look labelled
// unless a helper starts emitting our own footer wording verbatim.
function warningLabel(text) {
  var body = str(text)
  for (var kind in WARNING_PREFIX) {
    if (body.indexOf(WARNING_PREFIX[kind]) === 0) return kind
  }
  return ""
}

function labelWarning(text, kind) {
  var body = str(text)
  if (body === "" || warningLabel(body) !== "") return body
  return (WARNING_PREFIX[str(kind)] || WARNING_PREFIX.playlist) + body
}

// Stamp a whole list with its kind so it can travel in another kind's list.
function labelWarnings(warnings, kind) {
  var list = statusWarnings({ ok: true, warnings: warnings })
  var out = []
  for (var i = 0; i < list.length; i++) out.push(labelWarning(list[i], kind))
  return out
}

// Footer line for the warnings of one helper (UX 6 tone, D-LIVE-18): the
// first warning and, when there are several, how many more; "" without
// warnings. `kind` is "playlist" (default), "epg" or "player", and is only
// consulted for an entry that does not already name its own kind.
function warningLine(warnings, kind) {
  var list = statusWarnings({ ok: true, warnings: warnings })
  if (list.length === 0) return ""
  return labelWarning(list[0], kind) + (list.length > 1 ? " (+" + (list.length - 1) + " more)" : "")
}

// The one warning line the footer's status slot can hold. The playlist's
// warnings describe the channel list itself and win; the EPG's follow with
// their own wording. Each is cleared by the next clean load of its own
// helper, so an EPG warning can outlive a playlist refresh and vice versa.
function footerWarning(playlistWarnings, epgWarnings) {
  var line = warningLine(playlistWarnings, "playlist")
  if (line !== "") return line
  return warningLine(epgWarnings, "epg")
}

// ------------------------------------------------------------ player shutdown

// Next rung of the shutdown ladder (D-LIVE-17). `stage` is the rung already
// taken: "" -> `quit` over IPC, "quit" -> SIGTERM, "term" -> SIGKILL, after
// which only the exit is awaited (nothing to send, no wait to arm).
function stopEscalation(stage) {
  var s = str(stage)
  if (s === "") return { action: "quit", signal: 0, waitMs: STOP_QUIT_GRACE_MS }
  if (s === "quit") return { action: "term", signal: 15, waitMs: STOP_KILL_GRACE_MS }
  if (s === "term") return { action: "kill", signal: 9, waitMs: 0 }
  return { action: "kill", signal: 0, waitMs: 0 }
}

// One health-timer tick (D-LIVE-17). `skips` counts the ticks skipped in a
// row because a helper call was in flight, `busy` says whether one is in
// flight now: check = run the status probe, restart = treat the player as
// unresponsive without probing (HEALTH_SKIPS_BEFORE_RESTART busy ticks).
function healthTick(skips, busy) {
  var n = busy ? Math.max(0, Math.floor(Number(skips) || 0)) + 1 : 0
  var restart = !!busy && n >= HEALTH_SKIPS_BEFORE_RESTART
  return { check: !busy, restart: restart, skips: restart ? 0 : n }
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

// ---- our own settings write, applied locally (D-LIVE-20 / D-LIVE-21)
//
// The host publishes `barConfig` to a plugin from a `shellConfig` change
// handler (shell.qml:66 -> pluginsChanged -> syncPluginApis -> publicBarConfig),
// and a QML change handler runs before the bindings that depend on the same
// property are re-evaluated. So `shell.barConfig` reaches a plugin one
// shellConfig write late: an external write is flushed by the next one (the
// FileView re-reads the foreign change), but a plugin's own write is the
// last one there is and never comes back. A plugin must therefore apply its
// own successful write itself and never wait for the echo.
//
// `ownWrite` = { base, value }: `base` is the host settings the write was
// made against, `value` the playlist / EPG URLs written. The override is in
// force only while the host still reports `base`; the moment the host
// reports anything else -- our echo, or somebody else's write -- it lapses
// and the host wins again. That makes the echo idempotent (our own value
// arrives identical to what is already applied, so nothing changes and
// nothing is applied twice) and keeps an external change authoritative.

// Does a plugin's own write still stand in for the host's value?
function ownWriteInForce(hostSettings, ownWrite) {
  if (!ownWrite || typeof ownWrite !== "object") return false
  var base = ownWrite.base
  var value = ownWrite.value
  if (!base || typeof base !== "object" || !value || typeof value !== "object") return false
  var host = hostSettings || {}
  return str(host.playlistUrl) === str(base.playlistUrl) && str(host.epgUrl) === str(base.epgUrl)
}

// The settings the plugin acts on: the host's, with our own pending write
// laid over the two URL keys while it is still in force. Every other key
// always comes from the host (only the URLs are ours to write).
function settingsWithOwnWrite(hostSettings, ownWrite) {
  var host = hostSettings || {}
  if (!ownWriteInForce(host, ownWrite)) return host
  var out = {}
  for (var k in host) out[k] = host[k]
  out.playlistUrl = str(ownWrite.value.playlistUrl)
  out.epgUrl = str(ownWrite.value.epgUrl)
  return out
}

// The record of a write just made against `hostSettings`.
function ownWriteFor(hostSettings, playlistUrl, epgUrl) {
  var host = hostSettings || {}
  return {
    base: { playlistUrl: str(host.playlistUrl), epgUrl: str(host.epgUrl) },
    value: { playlistUrl: str(playlistUrl), epgUrl: str(epgUrl) }
  }
}

// Can `updateEntryInline` carry our settings at all? It rewrites a layout
// entry in place, so it needs an object entry with our id: a bare-string
// entry (`"io.github.rmcdavid.iptv"`) and an absent entry both make it
// return false without persisting, and that is a real persist failure. A
// false return with a writable entry means "nothing to change" instead,
// which is success (the host already stores what we asked for).
function barEntryWritable(barConfig, pluginId) {
  var id = str(pluginId)
  if (!barConfig || typeof barConfig !== "object" || !barConfig.layout || typeof barConfig.layout !== "object") return false
  var sections = ["left", "center", "right"]
  for (var s = 0; s < sections.length; s++) {
    var entries = barConfig.layout[sections[s]]
    if (!Array.isArray(entries)) continue
    for (var i = 0; i < entries.length; i++) {
      var entry = entries[i]
      if (entry && typeof entry === "object" && str(entry.id) === id) return true
    }
  }
  return false
}

// ------------------------------------------------------------ mpv

// Options that are allowed through but hand the stream address to a SECOND
// program (PO-10, D-PLY-5). None of these is reserved and none is refused:
// PO-5 keeps `--ytdl` available on purpose, because it is the documented way
// to play a link that is not a direct stream. What the plugin owes the user
// is that the cost is said out loud at the moment the option is in force,
// not once in a README they read when they installed it.
//
// With `--ytdl=yes`, mpv's builtin `ytdl_hook` runs `yt-dlp ... -- <URL>` on
// every open, putting the full credentialed URL on another process's 0444
// command line for seconds (measured in QA-RESULTS M8 / D-PLY-5). The
// `--ytdl-*` options exist only to configure that handoff, and `--script-opts`
// reaches the same hook - `ytdl_hook-ytdl_path` even chooses which program
// receives the address. `--script` / `--scripts` are reserved, so mpv's own
// builtin scripts are the only ones these options can reach.
//
// Mirrored by `mpv_arg_warnings()` in bin/omarchy-iptv and pinned by the
// `mpvHandoff` vectors in tests/fixtures/player-argv.json.
var MPV_HANDOFF = {
  "--ytdl-format": true,
  "--ytdl-raw-options": true
}
// The same hook, reached through a script option: warned on only when the
// value actually names it, so `--script-opts=osc-scalewindowed=2` is silent.
var MPV_HANDOFF_SCRIPT_OPTS = { "--script-opts": true, "--script-opt": true }
// `--ytdl` is a flag: only a value that turns it ON is a handoff, so a user
// who writes the default out in full (`--ytdl=no`) is never warned at all.
var MPV_YTDL_OFF = { "no": true, "0": true, "false": true }
var MPV_HANDOFF_TEXT = " hands the stream address to another program"

// mpv spells the list-option variants `--opt-append`, `--opt-set` and so on;
// every one of them sets the same option, so the base name is what decides.
function mpvOptionBase(name) {
  return str(name).replace(/-(add|append|set|pre|clr|del|remove|toggle)$/, "")
}

// "" when the token is harmless, else the option NAME to name in the warning.
// The value is never returned: it can itself carry a credentialed URL (a
// proxy in `--ytdl-raw-options`, say) and a warning line is a sink (R12).
function mpvHandoffName(token) {
  var text = str(token)
  var eq = text.indexOf("=")
  var name = eq === -1 ? text : text.substring(0, eq)
  var value = eq === -1 ? "" : text.substring(eq + 1)
  // `--no-ytdl` turns the handoff off; there is nothing to warn about.
  if (name.indexOf("--no-") === 0) return ""
  var base = mpvOptionBase(name)
  if (base === "--ytdl") return MPV_YTDL_OFF[value.toLowerCase()] === true ? "" : name
  if (MPV_HANDOFF[base] === true) return name
  if (MPV_HANDOFF_SCRIPT_OPTS[base] === true) return value.indexOf("ytdl") === -1 ? "" : name
  return ""
}

// One line per distinct option, in the order the user wrote them.
function mpvArgWarnings(tokens) {
  var list = asList(tokens)
  var seen = {}
  var out = []
  for (var i = 0; i < list.length; i++) {
    var name = mpvHandoffName(list[i])
    if (name === "" || seen[name] === true) continue
    seen[name] = true
    out.push("mpvArg " + name + MPV_HANDOFF_TEXT)
  }
  return out
}

// mpvArgs is one string of whitespace-separated `--key[=value]` tokens.
// Anything else (including reserved options) is rejected, never guessed.
// `warnings` covers the tokens that are KEPT: a rejected token never reaches
// mpv, so it has nothing to warn about beyond the existing `rejected` list.
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
  return { args: args, rejected: rejected, warnings: mpvArgWarnings(args) }
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

// Full argv for the mpv launch (ARCHITECTURE-PLAYER.md section 6). Nothing
// channel-specific is here any more: no URL, no trailing "--", no header
// options and no per-channel title, because all of them travel over the 0600
// socket instead (S-03 closed). `--idle=once` is PO-1: mpv idles at startup
// so the first channel arrives by `loadfile` like every later one, and still
// exits when the playlist ends, which keeps today's "the window vanishes on
// a failure" behaviour and the degraded 10 s status-poll fallback.
// The neutral `--title=$>IPTV` / `--force-media-title=IPTV` keep mpv from
// flashing its own "No file - mpv"; the channel title follows over IPC.
// Mirrored by `mpv_launch_argv()` in bin/omarchy-iptv, pinned by the shared
// vectors in tests/fixtures/player-argv.json.
function buildMpvArgv(params) {
  var p = params || {}
  var argv = [
    "mpv",
    "--input-ipc-server=" + str(p.socketPath),
    "--wayland-app-id=omarchy-iptv",
    "--force-window=immediate",
    "--idle=once",
    "--keep-open=no",
    "--title=" + mpvWindowTitle("IPTV"),
    "--force-media-title=IPTV",
    "--msg-level=all=error",
    // Live streams never need yt-dlp; without this mpv shells out to it on
    // every dead URL (seconds of delay and noise per failed zap). User
    // mpvArgs come later, so `--ytdl=yes` can re-enable it (PO-5).
    "--ytdl=no"
  ]
  return argv.concat(asList(p.extraArgs))
}

// ------------------------------------------------------------ player verbs
//
// argv for the helper's `player` verb group (ARCHITECTURE-PLAYER.md 4.3).
// These are the helper's own arguments; the caller prefixes the interpreter
// and the helper path, which `helperArgv()` does. Every value is a separate
// argv member: no joining, no quoting, no shell (hard requirement 9). User
// mpv tokens travel as repeated `--mpv-arg TOKEN` so argparse can never
// swallow an option-looking token and no token is ever split or merged.

function helperArgv(helperPath, args) {
  return ["python3", str(helperPath)].concat(asList(args))
}

function seqArg(seq) {
  var n = Math.floor(Number(seq))
  return String(isFinite(n) && n > 0 ? n : 0)
}

// One `--mpv-arg=<token>` member per user token. The attached form is not
// cosmetic: argparse refuses an option-looking VALUE, so the separated form
// `--mpv-arg --profile=low-latency` dies with "expected one argument" - which
// is every realistic token, since mpv options all start with "--" (verified
// against python 3.14's argparse). Attached, each token is still exactly one
// argv member, never joined with another and never split.
function mpvArgArgv(mpvArgs) {
  var list = asList(mpvArgs)
  var out = []
  for (var i = 0; i < list.length; i++) {
    var token = str(list[i])
    if (token === "") continue
    out.push("--mpv-arg=" + token)
  }
  return out
}

function playerSessionArgv(socket, cacheDir, id, seq, scope, since, mpvArgs, ownerPid) {
  var argv = ["--socket", str(socket), "--cache-dir", str(cacheDir), "--id", str(id), "--seq", seqArg(seq)]
  if (str(scope) !== "") argv = argv.concat(["--scope", str(scope)])
  var when = Math.floor(Number(since))
  if (isFinite(when) && when > 0) argv = argv.concat(["--since", String(when)])
  var pid = Math.floor(Number(ownerPid))
  if (isFinite(pid) && pid > 0) argv = argv.concat(["--owner-pid", String(pid)])
  return argv.concat(mpvArgArgv(mpvArgs))
}

// `ownerPid` is optional and additive: passing Quickshell.processId here
// claims the player for this shell at the same moment it starts playing, so
// the plugin-removal case (PO-2 / PLAYER-LIVE-04) has a claim to check even
// when the service never ran a probe that found anything.
function playerStartArgv(socket, cacheDir, id, seq, scope, since, mpvArgs, ownerPid) {
  return ["player", "start"].concat(playerSessionArgv(socket, cacheDir, id, seq, scope, since, mpvArgs, ownerPid))
}

// `from` picks the first rung: "" or "quit" starts at `quit` over IPC,
// "term" skips straight to SIGTERM (the health verdict, where IPC is by
// definition not answering), "kill" to SIGKILL.
function playerStopArgv(socket, seq, from) {
  var argv = ["player", "stop", "--socket", str(socket), "--seq", seqArg(seq)]
  var rung = str(from)
  if (rung === "quit" || rung === "term" || rung === "kill") argv = argv.concat(["--from", rung])
  return argv
}

function playerRestartArgv(socket, cacheDir, id, seq, scope, since, mpvArgs, from, ownerPid) {
  var argv = ["player", "restart"].concat(playerSessionArgv(socket, cacheDir, id, seq, scope, since, mpvArgs, ownerPid))
  var rung = str(from)
  if (rung === "quit" || rung === "term" || rung === "kill") argv = argv.concat(["--from", rung])
  return argv
}

// `ownerPid` claims the surviving player for this shell (4.14). Omitted, the
// probe is read-only.
function playerProbeArgv(socket, ownerPid) {
  var argv = ["player", "probe", "--socket", str(socket)]
  var pid = Math.floor(Number(ownerPid))
  if (isFinite(pid) && pid > 0) argv = argv.concat(["--owner-pid", String(pid)])
  return argv
}

function playerOrphanCheckArgv(socket, ownerPid, graceSec) {
  var pid = Math.floor(Number(ownerPid))
  var grace = Number(graceSec)
  if (!isFinite(grace) || grace <= 0) grace = PLAYER_ORPHAN_GRACE_SEC
  return ["player", "orphan-check", "--socket", str(socket),
          "--owner-pid", String(isFinite(pid) && pid > 0 ? pid : 0),
          "--grace", String(grace)]
}

// The now-playing record that lives inside the mpv process, never on disk
// (4.6). `launchedFrom` is the zap-ring scope: pure UI intent that no mpv
// property could report, which is why the shell's own value is stashed and
// echoed back on reattach. Written by the helper, read back by
// `parsePlayerProbe`; this function is the shape of record for both sides.
function playerStash(params) {
  var p = params || {}
  var id = str(p.id)
  if (id === "") return null
  var entry = Math.floor(Number(p.entryId))
  var since = Math.floor(Number(p.since))
  return {
    schema: PLAYER_STASH_SCHEMA,
    playing: p.playing !== false,
    id: id,
    name: str(p.name),
    group: str(p.group),
    launchedFrom: str(p.launchedFrom),
    sourceKey: str(p.sourceKey),
    since: isFinite(since) && since > 0 ? since : 0,
    entryId: isFinite(entry) && entry > 0 ? entry : null,
    seq: Math.max(0, Math.floor(Number(p.seq)) || 0)
  }
}

function playerOwner(raw) {
  if (!raw || typeof raw !== "object") return null
  var pid = Math.floor(Number(raw.pid))
  if (!isFinite(pid) || pid <= 0) return null
  return { schema: PLAYER_STASH_SCHEMA, pid: pid, startTime: str(raw.startTime), at: Math.max(0, Math.floor(Number(raw.at)) || 0) }
}

// `player probe` stdout -> a shape the service can bind. Garbage, a truncated
// line, a foreign JSON document or an error reply all return valid:false
// rather than throwing, so a probe can never break the reattach path.
function parsePlayerProbe(text) {
  var empty = { valid: false, running: false, responsive: false, pid: null, idle: null, stash: null, owner: null, seq: 0 }
  var doc = parseJsonObject(text)
  if (!doc || doc.ok !== true || str(doc.kind) !== "player.probe") return empty
  var pid = Math.floor(Number(doc.pid))
  return {
    valid: true,
    running: doc.running === true,
    responsive: doc.responsive === true,
    pid: isFinite(pid) && pid > 0 ? pid : null,
    idle: doc.idle === null || doc.idle === undefined ? null : doc.idle === true,
    stash: playerStash(doc.stash),
    owner: playerOwner(doc.owner),
    seq: Math.max(0, Math.floor(Number(doc.seq)) || 0)
  }
}

// One newline-delimited line from mpv's own JSON IPC socket (4.8). Only the
// four event kinds the service acts on are recognised; a command reply, an
// unknown event, junk and a truncated line are all `{kind:"ignored"}`.
// `log-message` text is redacted a second time here: the helper redacts it
// on its own path, but this line comes straight off the socket.
function parsePlayerEvent(line) {
  var ignored = { kind: "ignored" }
  var doc = parseJsonObject(line)
  if (!doc) return ignored
  var event = str(doc.event)
  if (event === "start-file") {
    return { kind: "start-file", entryId: playerEntryId(doc.playlist_entry_id) }
  }
  if (event === "end-file") {
    return { kind: "end-file", entryId: playerEntryId(doc.playlist_entry_id), reason: str(doc.reason), fileError: str(doc.file_error) }
  }
  if (event === "log-message") {
    return { kind: "log-message", level: str(doc.level), prefix: str(doc.prefix), text: redactUrls(str(doc.text)).replace(/\s+$/, "") }
  }
  if (event === "property-change" && str(doc.name) === "idle-active") {
    return { kind: "property-change", name: "idle-active", value: doc.data === true }
  }
  return ignored
}

function playerEntryId(value) {
  var n = Math.floor(Number(value))
  return isFinite(n) && n > 0 ? n : null
}

// Why the player ended (4.8), replacing the exit code `mpvProc.onExited` gave.
// The entry gate FAILS OPEN (F4): the entry id decides which channel the
// toast names, never whether there is a toast, so a `playlist_entry_id` that
// is missing or unknown can never suppress a failure the user can see.
function endedVerdict(lastEndFile, userStopped, stopping) {
  if (userStopped === true || stopping === true) return { notify: false, reason: "", kind: "silent" }
  var end = lastEndFile && typeof lastEndFile === "object" ? lastEndFile : null
  if (!end) return { notify: true, reason: PLAYER_GENERIC_FAILURE, kind: "failed" }
  var reason = str(end.reason)
  // An intermediate .m3u8 master resolution: never terminal, never a verdict.
  if (reason === "redirect") return { notify: false, reason: "", kind: "ignored" }
  if (reason === "quit" || reason === "eof") return { notify: false, reason: "", kind: "silent" }
  var detail = redactUrls(str(end.fileError || end.file_error)).replace(/^\s+|\s+$/g, "")
  return { notify: true, reason: detail !== "" ? detail : PLAYER_GENERIC_FAILURE, kind: "failed" }
}

// What survives a `player probe` reply (4.10, and section 15's race).
//
// A probe answers about the world it was ISSUED into. The startup probe goes
// out from Component.onCompleted and answers about 130 ms later, and a play
// can arrive inside that window - from the guide, or over IPC one frame
// after the shell came back. Its "nothing is running" then cleared
// nowPlaying and playerWanted, and drainPendingPlay(), which needs a
// nowPlaying, dropped the queued play on the floor.
//
// The sequence resync is the one part of a stale reply that is still true,
// and it MOVES the counter staleness is measured against - so both answers
// come from one call rather than from two lines a caller can order wrongly.
// (They were: reading staleness after the resync makes every startup probe
// look stale, which silently disables PO-3's mark.)
function probeVerdict(recordedSeq, issuedAt, currentSeq) {
  var recorded = Math.floor(Number(recordedSeq)) || 0
  var current = Math.floor(Number(currentSeq)) || 0
  return { seq: Math.max(current, recorded + 1), stale: current !== (Math.floor(Number(issuedAt)) || 0) }
}

// What a socket EOF means, which is not always "the player ended" (4.8
// signal 3). `player start` and `player restart` ladder a player DOWN and
// spawn its replacement inside one helper call, so the death of the player
// they are replacing arrives here while that very call is still in flight -
// a rung of our own respawn, not an unattended end.
//
// Reading it as an end is the reported P1: the shell cleared `nowPlaying`
// and `playerWanted`, the helper's success reply then read the cleared
// `nowPlaying` as "a stop overtook this start" and declined to re-arm the
// observer, and with `wanted` false the 250 ms retry timer was off - so the
// interface sat idle forever while the freshly spawned player kept playing.
//
// Order matters: a stop we issued outranks everything (it is why the player
// is dying), then our own in-flight respawn, then the health verdict's
// queued relaunch, then the ending.
function playerDeathKind(context) {
  var ctx = context || {}
  if (ctx.userStopped === true || ctx.stopping === true) return "ended"
  if (ctx.nowPlaying !== true) return "ended"
  if (ctx.sessionInFlight === true) return "respawn"
  if (ctx.relaunchPending === true && ctx.hasChannel === true) return "relaunch"
  return "ended"
}

// What to do with the observer when `player start` / `player restart` answers
// ok. The helper has just reported a live player of this shell's making, so
// the one answer that is never right is to do nothing - that is the second
// half of the P1 above.
//
//   attached  the observer is already on it; only the birth edge to drop
//   abandoned a stop really did overtake this start; nothing to hunt
//   hunt      the player is up, the observer is not on it yet: arm and wait
//   recover   the same, and we no longer know WHAT is playing, so read it
//             back out of the player's own stash - the identical path a
//             shell restart takes (4.5), which is why it needs no new rule
function playerSessionFollowUp(context) {
  var ctx = context || {}
  if (ctx.attached === true) return "attached"
  if (ctx.stopping === true || ctx.userStopped === true) return "abandoned"
  return ctx.nowPlaying === true ? "hunt" : "recover"
}

// ---------------------------------------------------------------------
// The event router as pure logic (4.8).
//
// Service.qml owns the socket, the timers, the properties and the toast.
// What it must not own is the DECISION, because a decision that lives in a
// QML method can only be pinned by a copy of itself in the spec file, and a
// copy passes just as happily when the shipping path is broken - the same
// trap as a test double more forgiving than the real thing (CLAUDE.md 10).
// So handlePlayerLine(), rememberEntry(), channelForEnd() and the terminal
// half of handlePlayerGone() are these four functions plus assignments.

// The router's state between lines: which entry is loading, the last
// terminal end-file (null once a new load supersedes it), observed
// idle-active, and the five-line log tail.
function playerRouterState(state) {
  var st = state && typeof state === "object" ? state : {}
  return {
    entryId: playerEntryId(st.entryId) || 0,
    lastEndFile: st.lastEndFile || null,
    idle: st.idle === true,
    tail: asList(st.tail)
  }
}

// The log / stderr tail: error and fatal only, redacted (again - the helper
// redacts its own path, this line came straight off the socket), trailing
// whitespace stripped, five lines deep, memory only. Returns the SAME array
// when the line adds nothing, so a caller can skip the property write.
function pushPlayerLog(tail, line) {
  var rows = asList(tail)
  var clean = redactUrls(str(line).replace(/\s+$/, ""))
  if (clean === "") return rows
  var out = rows.slice()
  out.push(clean)
  while (out.length > PLAYER_LOG_TAIL) out.shift()
  return out
}

// One newline-delimited line from mpv's socket applied to the router state.
// Always returns a full state object; unchanged fields keep their exact
// references (`tail`, `lastEndFile`), so the caller writes only what moved.
function routePlayerEvent(state, line) {
  var st = playerRouterState(state)
  var event = parsePlayerEvent(line)
  if (event.kind === "start-file") {
    // A new load supersedes the previous end: this is what makes a zap
    // (end-file{stop} then start-file) silent.
    return { entryId: event.entryId ? event.entryId : st.entryId, lastEndFile: null, idle: st.idle, tail: st.tail }
  }
  if (event.kind === "end-file") {
    return { entryId: st.entryId, lastEndFile: event, idle: st.idle, tail: st.tail }
  }
  if (event.kind === "log-message") {
    if (event.level !== "error" && event.level !== "fatal") return st
    var text = (event.prefix !== "" ? "[" + event.prefix + "] " : "") + event.text
    return { entryId: st.entryId, lastEndFile: st.lastEndFile, idle: st.idle, tail: pushPlayerLog(st.tail, text) }
  }
  if (event.kind === "property-change") {
    return { entryId: st.entryId, lastEndFile: st.lastEndFile, idle: event.value === true, tail: st.tail }
  }
  return st
}

// The entry-ownership ring: mpv's own playlist_entry_id -> the channel that
// load was for, so a failure that arrives after the user has zapped away
// still names the right row. At most four entries, oldest dropped. Returns
// the SAME map when there is nothing to record.
function rememberEntryOwner(owners, entryId, target) {
  var map = owners && typeof owners === "object" ? owners : {}
  var id = playerEntryId(entryId)
  if (id === null || !target) return map
  var out = {}
  var keys = Object.keys(map)
  for (var i = Math.max(0, keys.length - (PLAYER_ENTRY_OWNERS - 1)); i < keys.length; i++) out[keys[i]] = map[keys[i]]
  out[String(id)] = { id: str(target.id), name: str(target.name) }
  return out
}

// Which channel a load belonged to. The gate FAILS OPEN (F4): an unknown,
// missing or non-numeric entry id degrades to whatever is playing now and
// can never suppress a failure the user must see.
function channelForEnd(owners, end, current) {
  var map = owners && typeof owners === "object" ? owners : {}
  if (end && end.entryId) {
    var owner = map[String(end.entryId)]
    if (owner) return owner
  }
  return current ? { id: str(current.id), name: str(current.name) } : null
}

// The terminal decision at socket EOF (4.8 signal 3): whether the user hears
// about this death, which channel it names, and with what text. The log tail
// outranks mpv's own generic `file_error` ("loading failed" says nothing;
// "[stream] Failed to open provider.test" says what happened).
function endedReport(context) {
  var ctx = context && typeof context === "object" ? context : {}
  var verdict = endedVerdict(ctx.lastEndFile, ctx.userStopped === true, ctx.stopping === true)
  var tail = asList(ctx.tail)
  return {
    notify: verdict.notify === true,
    kind: verdict.kind,
    target: channelForEnd(ctx.owners, ctx.lastEndFile, ctx.nowPlaying),
    reason: tail.length > 0 ? str(tail[tail.length - 1]) : str(verdict.reason)
  }
}

// argv for `hyprctl dispatch focuswindow class:omarchy-iptv` (R9).
function focusPlayerArgv() {
  return ["hyprctl", "dispatch", "focuswindow", "class:omarchy-iptv"]
}

// ------------------------------------------------------------ notifications

// argv for omarchy-notification-send per UX 6.4. Bodies never carry a URL.
// Options come first, then the constant headline, then the body. The
// wrapper (busctl-based) takes the body positionally unless it looks like
// one of its own flags (`--urgency=...`, `-g`, ...), so the body is built to
// never start with "-": the playlist-controlled name is quoted with the
// typographic quotes and cleaned of leading dashes (S-04).
function notifyArgv(event, params) {
  var p = params || {}
  var spec = null
  var name = cleanName(p.name) || "Channel"
  var reason = scrubUrls(str(p.reason))
  if (event === "streamFailed") {
    spec = { title: "Stream failed", body: QUOTE_OPEN + name + QUOTE_CLOSE + " did not play" + (reason !== "" ? SEP + reason : ""), glyph: GLYPHS.tvOff, urgency: "normal", id: NOTIFY_IDS.streamFailed }
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

// epg-now.json is stale once its `validUntil` (the next programme boundary
// the helper computed) has passed; missing or malformed meta counts as stale
// so a fresh fetch is always preferred over no data (D-LIVE-02).
function epgNowStale(meta, nowSec) {
  var until = meta && typeof meta === "object" ? Number(meta.validUntil) : NaN
  if (!isFinite(until) || until <= 0) return true
  return until <= (Number(nowSec) || 0)
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

// ------------------------------------------------------------ guide body

// Which single surface the guide body renders (UX 4.4 - 4.6 / 6.3 and
// UX-SOURCES 1.2) and, with it, whether rows, the group column and the
// footer counts exist at all. One decision instead of three independent
// bindings, so an empty state can never be drawn on top of a channel list
// (D-LIVE-19: `omarchy bar set ... playlistUrl ""` at runtime flipped the
// body to `No playlist configured` while the service still held the
// previous source's channels, and the title, prose and command box were
// painted over 10 live rows and an 11-entry group column).
//
// The unconfigured rule is the fix: a guide without a configured playlist
// has no channels, no groups and no counts whatever the service still holds
// in memory, so the setup surface stands alone. `savedSources` carries the
// history size into that surface, because since v0.2.0 the source record
// outlives the cleared setting and the first-run screen must offer the
// `Saved sources (n)` path rather than pretend nothing was ever configured.
//
// opts: serviceReady, configured, channelCount (what the service holds),
// status (R8 vocabulary), rowCount (rows left after query and scope),
// query, scopeId, narrow, sources (records in the history).
function guideSurface(opts) {
  var o = opts || {}
  var ready = o.serviceReady !== false
  var configured = ready && o.configured === true
  var count = configured ? Math.max(0, Math.floor(Number(o.channelCount) || 0)) : 0
  var has = count > 0
  var empty = ""
  if (!ready) empty = "service"
  else if (!configured) empty = "unconfigured"
  else if (!has) empty = str(o.status) === "error" ? "error" : "loading"
  else if (Math.floor(Number(o.rowCount) || 0) > 0) empty = ""
  else if (tokenize(o.query).length > 0) empty = "noMatches"
  else if (effectiveScope(o.scopeId, o.query) === SCOPE_FAVORITES) empty = "noFavorites"
  else empty = "emptyScope"
  return {
    empty: empty,
    channelCount: count,
    hasChannels: has,
    showList: has,
    showColumn: has && o.narrow !== true,
    setup: empty === "unconfigured",
    savedSources: empty === "unconfigured" ? Math.max(0, Math.floor(Number(o.sources) || 0)) : 0
  }
}

// ------------------------------------------------------------ footer

// The counts line of the footer (UX 6.1): how many channels are listed and
// how fresh the copy in use is. When the copy is stale it reads
// `cached HH:MM - offline`, which is the footer's only cue that a refresh
// failed and the guide is serving a cache (D-LIVE-22), so this line carries
// a state, not only a number.
function footerCounts(o) {
  var out = pluralChannels(o.count)
  if (str(o.lastUpdated) !== "") out += SEP + (o.stale ? "cached " + str(o.lastUpdated) + SEP + "offline" : "updated " + str(o.lastUpdated))
  else if (o.stale) out += SEP + "cached" + SEP + "offline"
  // UX-SOURCES 5.3: with two or more saved sources the counts line carries
  // the active source's label so a switch is visible at a glance.
  if (str(o.activeLabel) !== "" && Number(o.sourceCount) > 1) out = str(o.activeLabel) + SEP + out
  return out
}

// Is the guide serving a degraded copy? Today that is exactly the stale
// cache behind a failed or skipped refresh (Service `status === "cached"`);
// the name is the concept so a future degraded state joins this rung rather
// than sinking below the warnings.
function footerDegraded(o) {
  return !!(o && o.stale)
}

// Footer status (UX 6.1, precedence note in UX 6.3). Priority, highest
// first: transient > bounded search > playing > refreshing > degraded (the
// `cached HH:MM - offline` counts line) > EPG pending > helper warning
// (`o.warning`, from footerWarning: playlist first, then EPG; D-LIVE-18,
// until that helper's next clean load) > the plain counts line.
//
// D-LIVE-22: warnings are informational and must never hide a failure, and a
// stale cache is the failure side of that rule, not decoration. UX 6.3 ranks
// an error above both warning kinds; an error with no cache has no footer
// line at all (it speaks in the body), so the rung the degraded counts line
// takes here is that error rung - above EPG pending and above both warnings.
//
// The empty states (not configured, loading, error without a cache;
// UX 4.4 - 4.6) carry their message in the body and leave the status slot
// blank, so `0 channels` or `Refreshing...` never shows there (D-LIVE-09);
// only a transient may.
function footerStatus(opts) {
  var o = opts || {}
  if (str(o.transient) !== "") return str(o.transient)
  if (o.configured === false || !(Number(o.count) > 0)) return ""
  if (o.truncated) return "First " + formatCount(o.cap || MAX_ROWS_DEFAULT) + " of " + formatCount(o.resultTotal) + SEP + "keep typing"
  if (str(o.playingName) !== "") return GLYPHS.play + " " + str(o.playingName) + SEP + "s stop"
  if (o.refreshing) return "Refreshing" + ELLIPSIS
  if (footerDegraded(o)) return footerCounts(o)
  if (o.epgPending) return "Guide data loading" + ELLIPSIS
  if (str(o.warning) !== "") return str(o.warning)
  return footerCounts(o)
}

// Footer hint pairs [key, verb] (UX 6.2, UX-SOURCES 5.3); the guide styles
// keys and verbs at different opacities. `o.form` is the open form (its
// focused element decides the set), `o.cursorKind` the Sources row kind,
// `o.sourcesExist` adds `o sources` to the error empty state.
function footerHints(opts) {
  var o = opts || {}
  var mode = str(o.mode)
  if (mode === "confirmRemove") return [["Left/Right", "choose"], ["Enter", "confirm"], ["Esc", "cancel"]]
  if (mode === "sourceEdit" || mode === "sourceXtream") return formHints(o.form)
  if (mode === "sources") {
    if (o.cursorKind === "add" || o.cursorKind === "xtream") return [["j/k", "move"], ["Enter", "open"], ["Esc", "back"]]
    return [["j/k", "move"], ["Enter", "switch"], [SOURCE_KEYS.add, "add"], [SOURCE_KEYS.xtream, "Xtream"], [SOURCE_KEYS.edit, "edit"], [SOURCE_KEYS.remove, "remove"], ["Esc", "back"]]
  }
  if (o.empty === "loading") return [["Esc", "close"]]
  if (o.empty) {
    // UX-SOURCES 5.3: `r retry`; `o.retry === false` drops it when nothing
    // can be retried (the configured value is invalid, D-SRC-06).
    var pairs = []
    if (o.retry !== false) pairs.push(["r", "retry"])
    if (o.sourcesExist) pairs.push([SOURCE_KEYS.open, "sources"])
    pairs.push(["Esc", "close"])
    return pairs
  }
  if (mode === "list") {
    return [["j/k", "move"], ["h/l", "group"], ["Enter", "play"], ["Space", "preview"], ["f", "favorite"], ["s", "stop"], ["r", "refresh"], ["/", "search"], [SOURCE_KEYS.open, "sources"]]
  }
  if (str(o.query) !== "") {
    return [["Enter", "play"], ["Up/Down", "move"], ["Left/Right", "narrow"], ["Tab", "keys"], ["Esc", "clear"]]
  }
  return [["Enter", "play"], ["Up/Down", "move"], ["Left/Right", "group"], ["Tab", "keys"], ["Esc", "close"]]
}

// Hints for an open form (UX-SOURCES 2.3 / 5.3): the submit verb is `load`
// on the first-run URL form, `save` elsewhere; Esc reads `cancel` for forms
// from Sources and `clear` / `back` / `close` for the first-run rule.
function formHints(form) {
  var f = form || {}
  if (f.probing) return [["Esc", "cancel"]]
  var firstRun = f.origin === "firstRun"
  var submit = firstRun && f.kind !== "xtream" ? "load" : "save"
  var esc = "cancel"
  if (firstRun) {
    if (formHasText(f)) esc = "clear"
    else esc = f.parent ? "back" : "close"
  }
  var focus = str(f.focus)
  if (!isFormField(f, focus)) return [["Enter", "activate"], ["Tab", "next field"], ["Esc", esc]]
  if (f.kind === "xtream") return [["Enter", submit], ["Tab", "next field"], ["Esc", esc]]
  var value = f.values ? str(f.values[focus]) : ""
  var maskable = isUrlField(focus) && maskUrl(value) !== value
  var revealed = maskable && !!(f.revealed && f.revealed[focus])
  if (maskable && !revealed) return [["Enter", submit], ["Tab", "next field"], [SOURCE_KEYS.reveal, "reveal"], [SOURCE_KEYS.paste, "replace"], ["Esc", esc]]
  if (revealed) return [["Enter", submit], ["Tab", "next field"], [SOURCE_KEYS.reveal, "hide"], ["Esc", esc]]
  return [["Enter", submit], ["Tab", "next field"], [SOURCE_KEYS.paste, "paste"], ["Esc", esc]]
}

// ------------------------------------------------------------ sources (M2-01)
//
// docs/ARCHITECTURE-SOURCES.md section 3 (state records, keys, validation,
// masking, Xtream, reducers) and docs/UX-SOURCES.md 5.4-5.8 / 8.1 (codes,
// copy, view objects, form state) under the reconciliation rulings SR1-SR10:
// the state file keeps the architecture's field names (`key`, `url`,
// `epgUrl`, `lastUsed`, `fetchedAt`), the guide only ever sees `sourceView`
// objects with the UX names (`id`, `hasEpg`, `cachedAt`, `lastUsedAt`), the
// user-facing validation codes are the UX 5.4 list, every cap lives in
// LIMITS (SR5), and `maskUrl` keeps `type` / `output` readable (SR4).
// Nothing here logs, renders or touches I/O; no function ever returns a URL
// except `validateSourceUrl`, `xtreamUrls`, `sourceForEdit` and the state
// reducers, which the service alone consumes.

var CACHE_LAYOUT = 2
var MAX_SOURCES = 50
var MAX_SOURCE_URL = 2048
var MAX_LABEL = 64
var MAX_XTREAM_SERVER = 512
var MAX_XTREAM_FIELD = 256
var SOURCES_DIR = "sources"
var MASK = "****"
var MASK_CLEAR_PARAMS = ["type", "output"]
var LIMITS = { url: MAX_SOURCE_URL, label: MAX_LABEL, server: MAX_XTREAM_SERVER, user: MAX_XTREAM_FIELD, pass: MAX_XTREAM_FIELD, sources: MAX_SOURCES }
// The keys of the Sources screens, next to the hint table so the two cannot
// drift (UX-SOURCES 4.8). Guide.qml never spells a key.
var SOURCE_KEYS = { open: "o", add: "a", xtream: "c", edit: "e", remove: "x", reveal: "Ctrl+R", clear: "Ctrl+U", paste: "Ctrl+V" }
var SOURCE_KEY_RE = /^[0-9a-f]{8}(-[0-9]{1,3})?$/
var SOURCE_ORIGINS = ["guide", "xtream", "cli", "migrated"]
var URL_FIELDS = ["playlist", "epg"]
var FORM_LIMITS = { label: MAX_LABEL, playlist: MAX_SOURCE_URL, epg: MAX_SOURCE_URL, server: MAX_XTREAM_SERVER, username: MAX_XTREAM_FIELD, password: MAX_XTREAM_FIELD }
var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

// ---- input hygiene (ARCHITECTURE-SOURCES 3.1 / 6.1)

var CONTROL_RE = /[\u0000-\u001f\u007f-\u009f]/g
var EDGE_SPACE_RE = /^[ \u00a0]+|[ \u00a0]+$/g

function capLength(text, limit) {
  var max = Number(limit) > 0 ? Math.floor(Number(limit)) : MAX_SOURCE_URL
  return text.length > max ? text.substring(0, max) : text
}

// Field boundary rule: control characters (CR, LF, TAB, the C1 range)
// removed so a multi-line paste collapses to one line, ASCII space and NBSP
// trimmed, then capped at `limit` UTF-16 units. Applied to every paste, on
// submit, and again inside the validators.
function sanitizeInput(text, limit) {
  // SR15: a leading byte-order mark (a common paste artefact) is dropped.
  return capLength(str(text).replace(/^\ufeff/, "").replace(CONTROL_RE, "").replace(EDGE_SPACE_RE, ""), limit)
}

// Unicode code points, not UTF-16 units (SR22: the label cap counts code
// points in both languages).
function codePoints(text) {
  return Array.from(str(text))
}

function codePointLength(text) {
  return codePoints(text).length
}

function capCodePoints(text, limit) {
  var cps = codePoints(text)
  return cps.length > limit ? cps.slice(0, limit).join("") : str(text)
}

// While typing (UX-SOURCES 2.3): controls removed and capped, edges kept so
// a label can be typed with spaces; the trim happens on paste and submit.
function sanitizeTyping(text, limit) {
  return capLength(str(text).replace(CONTROL_RE, ""), limit)
}

function lowerFirst(text) {
  var t = str(text)
  return t === "" ? t : t.charAt(0).toLowerCase() + t.substring(1)
}

// User-facing sentence per result code (UX-SOURCES 5.4, numbers from
// LIMITS per SR5). Service / helper code names (`bad_url`, `bad_server`,
// ...) map onto the same sentences so any action result can be shown.
// `opts.field === "epg"` yields the `EPG: ...` variant; `opts.label` fills
// the duplicate / label_taken sentences.
function sourceErrorMessage(code, opts) {
  var o = opts || {}
  var c = str(code)
  var quoted = QUOTE_OPEN + str(o.label) + QUOTE_CLOSE
  var schemeText = "Start with http://, https://, or / for a local file"
  var invalidText = "Invalid URL" + SEP + "check the host"
  var serverText = "Server must start with http:// or https://"
  var table = {
    empty: "Enter a playlist URL or path",
    scheme: schemeText,
    unsupported_scheme: schemeText,
    invalid: invalidText,
    bad_url: invalidText,
    relative_path: "Use an absolute path (starts with /, not ~)",
    unsafe_path: "Path not allowed",
    too_long: "Too long" + SEP + "max " + formatCount(MAX_SOURCE_URL) + " characters",
    duplicate: str(o.label) !== "" ? "Already in Sources as " + quoted : "Already in Sources",
    label_too_long: "Label too long" + SEP + "max " + formatCount(MAX_LABEL) + " characters",
    label_taken: "A source named " + quoted + " already exists",
    server_empty: "Enter the server URL",
    server_scheme: serverText,
    bad_server: serverText,
    server_path: "Server is just http://host:port" + SEP + "no path",
    server_userinfo: "Server must not contain a username or password" + SEP + "enter them below",
    server_too_long: "Server too long" + SEP + "max " + formatCount(MAX_XTREAM_SERVER) + " characters",
    user_empty: "Enter the username",
    pass_empty: "Enter the password",
    bad_credentials: "Enter the username and password",
    user_too_long: "Username too long" + SEP + "max " + formatCount(MAX_XTREAM_FIELD) + " characters",
    pass_too_long: "Password too long" + SEP + "max " + formatCount(MAX_XTREAM_FIELD) + " characters",
    too_many: "Sources is full (" + formatCount(MAX_SOURCES) + ")" + SEP + "remove one first",
    busy: "Busy" + SEP + "wait for the current fetch to finish",
    unknown_source: "Source not found",
    not_ready: "Not ready yet" + SEP + "try again in a moment",
    persist_failed: "Could not save settings" + SEP + "try omarchy bar set",
    cancelled: "Cancelled"
  }
  var text = table[c] || ""
  if (text === "") return c === "" || c === "ok" ? "" : "Could not save the source (" + c + ")"
  if (o.field === "epg") return "EPG: " + lowerFirst(text)
  return text
}

// Older name from the architecture: same sentences.
function sourceReason(code) {
  return sourceErrorMessage(code)
}

// ---- URL validation (ARCHITECTURE-SOURCES 3.1 with the UX 5.4 codes, SR6)
//
// Accepted: absolute paths, `file://` URLs (normalized to the path) and
// `http(s)://` URLs with a host. The normalized `url` is the source's
// identity: scheme and host lowercased, numeric port normalized (leading
// zeros stripped, the scheme default dropped), empty path `/`, query
// verbatim (provider tokens are case-sensitive), fragment dropped, userinfo
// kept. `./` and `../` paths are refused (`relative_path`, UX 5.4); `~`
// paths are refused from the forms and accepted verbatim from the CLI
// (`opts.origin === "cli"`, SR11); `/proc`, `/sys`, `/dev` are refused
// (`unsafe_path`, SR13). Text without a scheme is `scheme` when it looks
// like a host and `relative_path` otherwise (SR12). The authority refuses
// backslashes, zero-width characters, ports above 65535 and bracket
// literals that are not IPv6 (SR15). `opts.kind === "epg"` makes an empty
// value ok (the EPG is optional) and prefixes the messages with `EPG:`.
var ZERO_WIDTH_RE = /[\u200b-\u200d\u2060\ufeff]/
var IPV6_LITERAL_RE = /^\[[0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*(?:%25[A-Za-z0-9._~-]+)?\]$/

// SR12: a "." or ":" before the first "/" reads as a host.
function looksLikeHost(text) {
  return /[.:]/.test(str(text).split("/")[0])
}

function validateSourceUrl(text, opts) {
  var o = opts || {}
  var field = o.kind === "epg" ? "epg" : "playlist"
  var cli = o.origin === "cli"
  function fail(code) {
    return { ok: false, code: code, message: sourceErrorMessage(code, { field: field }), field: field, kind: "", url: "", host: "" }
  }
  function pass(kind, url, host) {
    return { ok: true, code: "ok", message: "", field: field, kind: kind, url: url, host: host }
  }
  function filePath(path) {
    if (/^\/(proc|sys|dev)(\/|$)/.test(path)) return fail("unsafe_path")
    return pass("file", path, "")
  }
  var s = sanitizeInput(text, MAX_SOURCE_URL + 1)
  if (s === "") return field === "epg" ? pass("", "", "") : fail("empty")
  if (s.length > MAX_SOURCE_URL) return fail("too_long")
  if (s.indexOf("//") === 0) return fail("scheme")
  if (s.charAt(0) === "/") return filePath(s)
  if (s.charAt(0) === "~") return cli ? pass("file", s, "") : fail("relative_path")
  if (s === "." || s === ".." || s.indexOf("./") === 0 || s.indexOf("../") === 0) return fail("relative_path")
  // [\s\S] rather than `.`: a line separator (U+2028 / U+2029) inside an
  // http URL is whitespace (`invalid`), not a missing scheme (D-SRC-06).
  var m = s.match(/^([A-Za-z][A-Za-z0-9+.-]*):([\s\S]*)$/)
  if (!m) return fail(looksLikeHost(s) ? "scheme" : "relative_path")
  var scheme = m[1].toLowerCase()
  var rest = m[2]
  if (scheme === "file") {
    if (rest.indexOf("//") !== 0) return fail("invalid")
    var after = rest.substring(2).replace(/[?#].*$/, "")
    var slash = after.indexOf("/")
    if (slash === -1) return fail("invalid")
    var decoded
    try { decoded = decodeURIComponent(after.substring(slash)) } catch (e) { return fail("invalid") }
    if (decoded.charAt(0) !== "/") return fail("invalid")
    return filePath(decoded)
  }
  if (scheme !== "http" && scheme !== "https") return fail("scheme")
  if (rest.indexOf("//") !== 0) return fail("invalid")
  if (/\s/.test(rest)) return fail("invalid")
  var body = rest.substring(2)
  var cut = body.search(/[\/?#]/)
  var authority = cut === -1 ? body : body.substring(0, cut)
  var tail = cut === -1 ? "" : body.substring(cut)
  if (authority.indexOf("\\") !== -1 || ZERO_WIDTH_RE.test(authority)) return fail("invalid")
  var userinfo = ""
  var hostport = authority
  var at = authority.lastIndexOf("@")
  if (at !== -1) {
    userinfo = authority.substring(0, at)
    hostport = authority.substring(at + 1)
  }
  var host = ""
  var port = ""
  if (hostport.charAt(0) === "[") {
    var close = hostport.indexOf("]")
    if (close === -1) return fail("invalid")
    host = hostport.substring(0, close + 1)
    if (!IPV6_LITERAL_RE.test(host)) return fail("invalid")
    var afterHost = hostport.substring(close + 1)
    if (afterHost !== "") {
      if (afterHost.charAt(0) !== ":") return fail("invalid")
      port = afterHost.substring(1)
    }
  } else {
    var colon = hostport.lastIndexOf(":")
    host = colon === -1 ? hostport : hostport.substring(0, colon)
    port = colon === -1 ? "" : hostport.substring(colon + 1)
    if (/[:\[\]]/.test(host)) return fail("invalid")
  }
  if (host === "") return fail("invalid")
  host = host.toLowerCase()
  if (port !== "") {
    if (!/^[0-9]+$/.test(port)) return fail("invalid")
    port = port.replace(/^0+(?=[0-9])/, "")
    if (Number(port) > 65535) return fail("invalid")
  }
  if ((scheme === "http" && port === "80") || (scheme === "https" && port === "443")) port = ""
  var hash = tail.indexOf("#")
  if (hash !== -1) tail = tail.substring(0, hash)
  var q = tail.indexOf("?")
  var path = q === -1 ? tail : tail.substring(0, q)
  var query = q === -1 ? "" : tail.substring(q + 1)
  if (path === "") path = "/"
  var url = scheme + "://" + (userinfo !== "" ? userinfo + "@" : "") + host + (port !== "" ? ":" + port : "") + path + (query !== "" ? "?" + query : "")
  return pass("http", url, host)
}

// Normalized identity of an accepted URL, "" when it does not validate.
// `opts` reaches validateSourceUrl (the settings path passes origin `cli`).
function normalizeSourceUrl(text, opts) {
  var v = validateSourceUrl(text, opts)
  return v.ok ? v.url : ""
}

function isUrlField(field) {
  return URL_FIELDS.indexOf(str(field)) !== -1
}

// ---- keys and lookups (ARCHITECTURE-SOURCES 3.2, D4)

function sourceKey(url) {
  return fnv1a32(url)
}

function isSourceKey(key) {
  return SOURCE_KEY_RE.test(str(key))
}

function findSource(sources, key) {
  var k = str(key)
  if (k === "") return null
  var list = asList(sources)
  for (var i = 0; i < list.length; i++) if (list[i] && str(list[i].key) === k) return list[i]
  return null
}

function findSourceByUrl(sources, url) {
  var u = str(url)
  if (u === "") return null
  var list = asList(sources)
  for (var i = 0; i < list.length; i++) if (list[i] && str(list[i].url) === u) return list[i]
  return null
}

// The record with this url keeps its key; otherwise fnv1a32(url), suffixed
// `-2`, `-3`, ... while another record already uses it (harmless collision).
function allocateSourceKey(sources, url) {
  var existing = findSourceByUrl(sources, url)
  if (existing) return str(existing.key)
  var base = sourceKey(url)
  var key = base
  for (var n = 2; findSource(sources, key) !== null; n++) key = base + "-" + n
  return key
}

// `<cacheDir>/sources/<key>`; "" when either input is empty or the key is
// not a key (the helper validates again before it touches the path).
function sourceCacheDir(cacheDir, key) {
  var dir = str(cacheDir).replace(/\/+$/, "")
  if (dir === "" || !isSourceKey(key)) return ""
  return dir + "/" + SOURCES_DIR + "/" + str(key)
}

// ---- labels (UX-SOURCES 5.6)

function hostPortOf(url) {
  var m = str(url).match(/^[a-z][a-z0-9+.-]*:\/\/(?:[^@\/?#]*@)?([^\/?#]+)/i)
  return m ? m[1].toLowerCase() : ""
}

// Default label: the host (lowercase, leading `www.` dropped, `:port` kept
// when present) for URLs and the Xtream server; the file name for paths.
function deriveLabel(url, kind) {
  var text = str(url)
  var k = str(kind)
  var v = validateSourceUrl(text, { origin: "cli" })
  if (k === "file" || v.kind === "file") {
    var path = v.ok ? v.url : text
    var name = path.replace(/\/+$/, "").split("/").pop()
    return capCodePoints(sanitizeInput(name), MAX_LABEL) || "local file"
  }
  var hostport = hostPortOf(v.ok ? v.url : text)
  if (hostport === "") return capCodePoints(sanitizeInput(text), MAX_LABEL)
  return capCodePoints(sanitizeInput(hostport.replace(/^www\./, "")), MAX_LABEL)
}

function labelKey(text) {
  return sanitizeInput(text).toLowerCase()
}

// `existing` is a list of labels or of records / views ({ label, id | key }).
// `selfId` excludes the record being edited.
function labelTaken(label, existing, selfId) {
  var want = labelKey(label)
  if (want === "") return false
  var list = asList(existing)
  var self = str(selfId)
  for (var i = 0; i < list.length; i++) {
    var item = list[i]
    if (item === null || item === undefined) continue
    var key, id
    if (typeof item === "object") {
      key = labelKey(item.label)
      id = str(item.id !== undefined ? item.id : item.key)
    } else {
      key = labelKey(item)
      id = ""
    }
    if (self !== "" && id === self) continue
    if (key === want) return true
  }
  return false
}

// Appends ` 2`, ` 3`, ... while the label is taken (case-insensitive);
// derived labels only, a typed label is rejected with `label_taken` instead.
function uniqueLabel(label, existing, selfId) {
  var base = capCodePoints(sanitizeInput(label), MAX_LABEL)
  if (base === "") base = "source"
  if (!labelTaken(base, existing, selfId)) return base
  for (var n = 2; n < 1000; n++) {
    var suffix = " " + n
    var candidate = capCodePoints(base, MAX_LABEL - suffix.length) + suffix
    if (!labelTaken(candidate, existing, selfId)) return candidate
  }
  return base
}

// Architecture name: derived + unique in one call.
function defaultSourceLabel(url, kind, existingLabels) {
  return uniqueLabel(deriveLabel(url, kind), existingLabels)
}

// SR22: the cap counts code points; over-cap labels are refused, never cut.
function validateLabel(label, existing, selfId) {
  var text = sanitizeInput(label)
  if (codePointLength(text) > MAX_LABEL) return { ok: false, code: "label_too_long", field: "label", message: sourceErrorMessage("label_too_long"), label: text }
  if (labelTaken(text, existing, selfId)) return { ok: false, code: "label_taken", field: "label", message: sourceErrorMessage("label_taken", { label: text }), label: text }
  return { ok: true, code: "ok", field: "", message: "", label: text }
}

// ---- masking (SR4, UX-SOURCES 4.4)

function maskQuery(query) {
  var parts = str(query).split("&")
  var out = []
  for (var i = 0; i < parts.length; i++) {
    var part = parts[i]
    var eq = part.indexOf("=")
    if (eq === -1) { out.push(part); continue }
    var name = part.substring(0, eq)
    out.push(MASK_CLEAR_PARAMS.indexOf(name.toLowerCase()) !== -1 ? part : name + "=" + MASK)
  }
  return out.join("&")
}

// Fixed token `****` for the userinfo, every query value (except `type` and
// `output`, never secrets) and the fragment; scheme, host, port, path and
// query keys stay. Paths and anything that is not a URL come back unchanged,
// so `maskUrl(v) === v` means "nothing to mask" (no eye button, Ctrl+R no-op).
function maskUrl(url) {
  var text = str(url)
  var m = text.match(/^([A-Za-z][A-Za-z0-9+.-]*):\/\/([^\/?#]*)([^?#]*)(\?[^#]*)?(#.*)?$/)
  if (!m) return text
  if (m[1].toLowerCase() === "file") return text
  var authority = m[2]
  var at = authority.lastIndexOf("@")
  if (at !== -1) authority = MASK + "@" + authority.substring(at + 1)
  var query = m[4] !== undefined ? "?" + maskQuery(m[4].substring(1)) : ""
  var fragment = m[5] !== undefined ? "#" + MASK : ""
  return m[1] + "://" + authority + m[3] + query + fragment
}

// ---- Xtream Codes (ARCHITECTURE-SOURCES 3.4 / D10, UX-SOURCES 1.8, 5.4)

// RFC 3986 unreserved set only (A-Za-z0-9-._~), identical to Python
// quote(v, safe="") so node, the Qt engine and the helper agree.
function encodeQueryValue(value) {
  return encodeURIComponent(str(value)).replace(/[!'()*]/g, function(ch) {
    return "%" + ch.charCodeAt(0).toString(16).toUpperCase()
  })
}

// Builds the get.php / xmltv.php URLs from server, username and password.
// Accepts positional arguments or one object. The server must carry its
// scheme (no guessing, UX 8 #9) and nothing after host[:port] (UX 8 #10);
// a trailing slash is tolerated. Codes are the UX 5.4 Xtream set.
function xtreamUrls(server, username, password) {
  var o = server !== null && typeof server === "object" ? server : { server: server, username: username, password: password }
  function fail(code, field) {
    return { ok: false, code: code, field: field, message: sourceErrorMessage(code), playlistUrl: "", epgUrl: "", host: "", base: "" }
  }
  var srv = sanitizeInput(o.server, MAX_XTREAM_SERVER + 1)
  if (srv === "") return fail("server_empty", "server")
  if (srv.length > MAX_XTREAM_SERVER) return fail("server_too_long", "server")
  if (!/^[A-Za-z][A-Za-z0-9+.-]*:\/\//.test(srv)) return fail("server_scheme", "server")
  var v = validateSourceUrl(srv)
  if (!v.ok) return fail(v.code === "scheme" ? "server_scheme" : "invalid", "server")
  if (v.kind !== "http") return fail("server_scheme", "server")
  var m = v.url.match(/^(https?:\/\/[^\/?#@]+)\/?$/)
  // The validator drops a fragment from the normalized URL; on a server it
  // is refused like a path or a query (ARCH 3.4, D-SRC-08).
  if (!m || srv.indexOf("#") !== -1) {
    // SR17: credentials belong in the fields below, never in the server URL.
    var authorityEnd = v.url.indexOf("/", 8)
    var hasUserinfo = v.url.indexOf("@") !== -1 && (authorityEnd === -1 || v.url.indexOf("@") < authorityEnd)
    return fail(hasUserinfo ? "server_userinfo" : "server_path", "server")
  }
  var base = m[1]
  var user = sanitizeInput(o.username, MAX_XTREAM_FIELD + 1)
  if (user === "") return fail("user_empty", "username")
  if (user.length > MAX_XTREAM_FIELD) return fail("user_too_long", "username")
  var pass = sanitizeInput(o.password, MAX_XTREAM_FIELD + 1)
  if (pass === "") return fail("pass_empty", "password")
  if (pass.length > MAX_XTREAM_FIELD) return fail("pass_too_long", "password")
  var creds = "username=" + encodeQueryValue(user) + "&password=" + encodeQueryValue(pass)
  return {
    ok: true, code: "ok", field: "", message: "",
    playlistUrl: base + "/get.php?" + creds + "&type=m3u_plus&output=ts",
    epgUrl: base + "/xmltv.php?" + creds,
    host: v.host,
    base: base
  }
}

// UX 8.1 name: `{ ok, code, field, message }` (plus the built URLs on ok).
function validateXtream(fields) {
  return xtreamUrls(fields || {})
}

// ---- view objects (SR1, UX-SOURCES 5.2, 7.1)

function pluralGroups(n) {
  var v = Math.floor(Number(n) || 0)
  return formatCount(v) + (v === 1 ? " group" : " groups")
}

// `1,475 channels in 28 groups`
function countsLine(channelCount, groupCount) {
  return pluralChannels(channelCount) + " in " + pluralGroups(groupCount)
}

function sameDay(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
}

// `used 21:30` (today), `used yesterday`, `used 3 Sep` (this year), `used 3
// Sep 2025` (older), `never used` (0). Local time, 24-hour clock.
function formatLastUsed(atSec, nowSec) {
  var at = Number(atSec) || 0
  if (at <= 0) return "never used"
  var d = new Date(at * 1000)
  var now = Number(nowSec) > 0 ? new Date(Number(nowSec) * 1000) : new Date()
  if (sameDay(d, now)) return "used " + formatClock(at)
  var yesterday = new Date(now.getTime())
  yesterday.setDate(yesterday.getDate() - 1)
  if (sameDay(d, yesterday)) return "used yesterday"
  var text = "used " + d.getDate() + " " + MONTHS[d.getMonth()]
  if (d.getFullYear() !== now.getFullYear()) text += " " + d.getFullYear()
  return text
}

// Architecture wording, kept for callers that want an interval.
function formatAgo(nowSec, atSec) {
  var at = Number(atSec) || 0
  if (at <= 0) return ""
  var diff = Math.max(0, Math.floor((Number(nowSec) || 0) - at))
  if (diff < 60) return "just now"
  if (diff < 3600) return Math.floor(diff / 60) + " min ago"
  if (diff < 86400) return Math.floor(diff / 3600) + " h ago"
  return Math.floor(diff / 86400) + " d ago"
}

// One state record -> the view object the guide binds (SR1). `kind` is the
// UX kind (`url` | `file` | `xtream`), `host` never a URL, `channelCount`
// -1 until the first successful fetch. `errorReason` is the session-only
// probe failure (already redacted) the service may attach.
function sourceView(source, activeKey, nowSec, errorReason) {
  var s = source || {}
  var key = str(s.key)
  var kind = str(s.kind) === "file" ? "file" : (str(s.origin) === "xtream" ? "xtream" : "url")
  var fetched = Number(s.fetchedAt) > 0
  return {
    id: key,
    label: str(s.label),
    kind: kind,
    host: kind === "file" ? "local file" : hostPortOf(s.url),
    hasEpg: str(s.epgUrl) !== "",
    channelCount: fetched ? Math.max(0, Math.floor(Number(s.channelCount) || 0)) : -1,
    groupCount: fetched ? Math.max(0, Math.floor(Number(s.groupCount) || 0)) : 0,
    cachedAt: fetched ? Math.floor(Number(s.fetchedAt)) : 0,
    lastUsedAt: Math.max(0, Math.floor(Number(s.lastUsed) || 0)),
    lastUsedText: formatLastUsed(s.lastUsed, nowSec),
    active: key !== "" && key === str(activeKey),
    origin: str(s.origin),
    errorReason: str(errorReason)
  }
}

// Every record as a view, active first, then last used (newest first),
// then added (newest first). `errors` is the service's { key: reason } map.
function sourceViews(state, activeKey, nowSec, errors) {
  var st = state || emptyState()
  var errs = errors && typeof errors === "object" ? errors : {}
  var list = asList(st.sources)
  var out = []
  for (var i = 0; i < list.length; i++) {
    if (!list[i]) continue
    var view = sourceView(list[i], activeKey, nowSec, errs[str(list[i].key)])
    view.addedAt = Math.floor(Number(list[i].addedAt) || 0)
    out.push(view)
  }
  // SR32: active first, then last used (newest first), then the never-used
  // records in the order they were added.
  out.sort(function(a, b) {
    if (a.active !== b.active) return a.active ? -1 : 1
    var au = a.lastUsedAt > 0
    var bu = b.lastUsedAt > 0
    if (au !== bu) return au ? -1 : 1
    if (au && a.lastUsedAt !== b.lastUsedAt) return b.lastUsedAt - a.lastUsedAt
    if (a.addedAt !== b.addedAt) return au ? b.addedAt - a.addedAt : a.addedAt - b.addedAt
    return a.label < b.label ? -1 : (a.label > b.label ? 1 : 0)
  })
  for (var j = 0; j < out.length; j++) delete out[j].addedAt
  return out
}

// Architecture name.
function sourceRows(state, activeKey, nowSec, errors) {
  return sourceViews(state, activeKey, nowSec, errors)
}

// Row detail (UX-SOURCES 5.2): `active` (active source only), `used ...` on
// narrow cards, host, `Xtream`, counts or `not loaded yet`, `EPG`. Rows
// never carry error text (SR26); a failed retry's reason goes to the
// form's result line.
function sourceDetail(view, narrow) {
  var v = view || {}
  var parts = []
  if (v.active) parts.push("active")
  if (narrow) parts.push(str(v.lastUsedText) || formatLastUsed(v.lastUsedAt))
  parts.push(str(v.host))
  if (v.kind === "xtream") parts.push("Xtream")
  parts.push(Number(v.channelCount) >= 0 ? countsLine(v.channelCount, v.groupCount) : "not loaded yet")
  if (v.hasEpg) parts.push("EPG")
  return joinParts(parts)
}

// UX-SOURCES 7.1 row name.
function sourceAccessibleName(view) {
  var v = view || {}
  var out = str(v.label) + ", " + str(v.host)
  out += ", " + (Number(v.channelCount) >= 0 ? countsLine(v.channelCount, v.groupCount) : "not loaded yet")
  if (v.active) out += ", active"
  if (v.hasEpg) out += ", EPG"
  var used = str(v.lastUsedText) || formatLastUsed(v.lastUsedAt)
  out += ", " + (used === "never used" ? used : "last " + used)
  return out
}

// Header right slot: `3 sources`, `1 source`, `No sources`.
function sourcesHeaderCount(n) {
  var v = Math.floor(Number(n) || 0)
  if (v <= 0) return "No sources"
  return formatCount(v) + (v === 1 ? " source" : " sources")
}

// Pinned column row name (UX-SOURCES 7.1).
function sourcesRowAccessibleName(n) {
  return "Sources, " + formatCount(n) + " saved"
}

// Confirm dialog message (UX-SOURCES 5.7).
function confirmRemoveMessage(label, active) {
  var quoted = QUOTE_OPEN + str(label) + QUOTE_CLOSE
  if (active) return "Remove " + quoted + "? It is the active source; the guide returns to setup."
  return "Remove " + quoted + "? Its cache is deleted too."
}

// Result-line strings (UX-SOURCES 5.5). Hosts only, never a URL.
function fetchingLine(host, kind) {
  if (kind === "file") return "Reading the file" + ELLIPSIS
  return "Fetching from " + str(host) + ELLIPSIS
}

function probeFailureLine(reason, host, kind) {
  var text = redactUrls(str(reason)) || "Unknown error"
  if (kind === "file" || str(host) === "") return text
  return text + " from " + str(host)
}

// Footer transients (UX-SOURCES 5.3). `added` names the new source by its
// label (`Added list.m3u`, `Added tv.example.net`), never `local file`;
// `host` is the fallback when the caller has no label.
function sourceTransient(event, opts) {
  var o = opts || {}
  var counts = Number(o.channelCount) >= 0 ? countsLine(o.channelCount, o.groupCount) : ""
  if (event === "loaded") return counts
  if (event === "added") return "Added " + (str(o.label) !== "" ? str(o.label) : str(o.host)) + (counts !== "" ? SEP + counts : "")
  if (event === "saved") return "Saved" + (counts !== "" ? SEP + counts : "")
  if (event === "switched") return "Switched to " + str(o.label) + (Number(o.channelCount) >= 0 ? SEP + pluralChannels(o.channelCount) : "")
  if (event === "removed") return "Removed " + str(o.label) + (o.wasActive ? SEP + "no active source" : "")
  return ""
}

// ---- state records and reducers (ARCHITECTURE-SOURCES 2.1, 3.5)

// `search` rather than `test`: CONTROL_RE is global (stateful lastIndex).
function hasControlChars(text) {
  return str(text).search(CONTROL_RE) !== -1
}

// Console line for a record the reader drops (D-SRC-09): the key only,
// never the URL. Model.js is otherwise silent; node has a console too.
function warnState(message) {
  if (typeof console !== "undefined" && console && typeof console.warn === "function") console.warn("omarchy-iptv: state: " + message)
}

// A record whose `url` carries a control character (NUL, CR, ...) is
// dropped: it would reach the helper's argv and can never match a key
// (D-SRC-09). A control character in `epgUrl` clears that field only.
function normalizeSourceRecord(raw) {
  if (!raw || typeof raw !== "object") return null
  var key = str(raw.key)
  var url = str(raw.url)
  if (!isSourceKey(key) || url === "" || url.length > MAX_SOURCE_URL || hasControlChars(url)) return null
  var kind = str(raw.kind)
  if (kind !== "http" && kind !== "file") kind = url.charAt(0) === "/" ? "file" : "http"
  var epg = str(raw.epgUrl)
  if (epg.length > MAX_SOURCE_URL || hasControlChars(epg)) epg = ""
  var origin = str(raw.origin)
  if (SOURCE_ORIGINS.indexOf(origin) === -1) origin = "guide"
  var label = capCodePoints(sanitizeInput(raw.label), MAX_LABEL)
  if (label === "") label = deriveLabel(url, kind)
  return {
    key: key,
    url: url,
    epgUrl: epg,
    kind: kind,
    label: label,
    labelCustom: raw.labelCustom === true,
    origin: origin,
    addedAt: Math.max(0, Math.floor(Number(raw.addedAt) || 0)),
    lastUsed: Math.max(0, Math.floor(Number(raw.lastUsed) || 0)),
    fetchedAt: Math.max(0, Math.floor(Number(raw.fetchedAt) || 0)),
    channelCount: Math.max(0, Math.floor(Number(raw.channelCount) || 0)),
    groupCount: Math.max(0, Math.floor(Number(raw.groupCount) || 0))
  }
}

function copySourceRecord(rec, patch) {
  var out = {}
  for (var k in rec) out[k] = rec[k]
  var p = patch || {}
  for (var q in p) out[q] = p[q]
  return out
}

function replaceSource(state, key, patch) {
  var st = state || emptyState()
  var list = asList(st.sources)
  var out = []
  for (var i = 0; i < list.length; i++) out.push(list[i] && str(list[i].key) === str(key) ? copySourceRecord(list[i], patch) : list[i])
  return cloneState(st, { sources: out })
}

function nowInt(nowSec) {
  return Math.max(0, Math.floor(Number(nowSec) || 0))
}

function sourceLabels(state) {
  return asList(state ? state.sources : []).map(function(s) { return { id: str(s.key), label: str(s.label) } })
}

function reducerFail(state, code, key, opts) {
  return { ok: false, code: code, message: sourceErrorMessage(code, opts), state: state, key: str(key) }
}

// fields = { playlistUrl, epgUrl, label, origin }. Codes: the UX 5.4 URL
// codes, `label_too_long`, `label_taken` (a typed label that collides),
// `duplicate` (with the existing key), `too_many`. An empty label derives
// one from the URL and keeps `labelCustom: false`.
function addSource(state, fields, nowSec) {
  var st = cloneState(state)
  var f = fields || {}
  var pv = validateSourceUrl(f.playlistUrl)
  if (!pv.ok) return reducerFail(st, pv.code, "")
  var ev = validateSourceUrl(f.epgUrl, { kind: "epg" })
  if (!ev.ok) return reducerFail(st, ev.code, "", { field: "epg" })
  var dup = findSourceByUrl(st.sources, pv.url)
  if (dup) return reducerFail(st, "duplicate", dup.key, { label: dup.label })
  if (st.sources.length >= MAX_SOURCES) return reducerFail(st, "too_many", "")
  var lv = validateLabel(f.label, sourceLabels(st), "")
  if (!lv.ok) return reducerFail(st, lv.code, "", { label: lv.label })
  var origin = SOURCE_ORIGINS.indexOf(str(f.origin)) === -1 ? "guide" : str(f.origin)
  var label = lv.label !== "" ? lv.label : uniqueLabel(deriveLabel(pv.url, pv.kind), sourceLabels(st))
  var now = nowInt(nowSec)
  var key = allocateSourceKey(st.sources, pv.url)
  var rec = {
    key: key, url: pv.url, epgUrl: ev.url, kind: pv.kind, label: label, labelCustom: lv.label !== "",
    origin: origin, addedAt: now, lastUsed: now, fetchedAt: 0, channelCount: 0, groupCount: 0
  }
  return { ok: true, code: "ok", message: "", state: cloneState(st, { sources: st.sources.concat([rec]) }), key: key }
}

// fields = { label, playlistUrl, epgUrl } (each optional). A label change
// sets `labelCustom` (an empty label re-derives it). A changed playlist URL
// yields a NEW record (new key, `fetchedAt: 0`, label / addedAt copied) and
// leaves the old one in place until the service confirms the probe;
// `replacedKey` names the old record. An edit never counts against
// MAX_SOURCES: the replacement takes the old record's place, so the
// transient 51st entry is not a `too_many` (the service keeps it in memory
// and drops the old record before the new one lands in the history).
function updateSource(state, key, fields, nowSec) {
  var st = cloneState(state)
  var rec = findSource(st.sources, key)
  if (!rec) return { ok: false, code: "unknown_source", message: sourceErrorMessage("unknown_source"), state: st, key: str(key), urlChanged: false, replacedKey: "" }
  var f = fields || {}
  var patch = {}
  if (f.label !== undefined) {
    var lv = validateLabel(f.label, sourceLabels(st), rec.key)
    if (!lv.ok) return { ok: false, code: lv.code, message: lv.message, state: st, key: rec.key, urlChanged: false, replacedKey: "" }
    patch.label = lv.label !== "" ? lv.label : uniqueLabel(deriveLabel(rec.url, rec.kind), sourceLabels(st), rec.key)
    patch.labelCustom = lv.label !== ""
  }
  if (f.epgUrl !== undefined) {
    var ev = validateSourceUrl(f.epgUrl, { kind: "epg" })
    if (!ev.ok) return { ok: false, code: ev.code, message: ev.message, state: st, key: rec.key, urlChanged: false, replacedKey: "" }
    patch.epgUrl = ev.url
  }
  var urlChanged = false
  var newKey = rec.key
  if (f.playlistUrl !== undefined) {
    var pv = validateSourceUrl(f.playlistUrl)
    if (!pv.ok) return { ok: false, code: pv.code, message: pv.message, state: st, key: rec.key, urlChanged: false, replacedKey: "" }
    if (pv.url !== rec.url) {
      var dup = findSourceByUrl(st.sources, pv.url)
      if (dup) return { ok: false, code: "duplicate", message: sourceErrorMessage("duplicate", { label: dup.label }), state: st, key: str(dup.key), urlChanged: false, replacedKey: "" }
      urlChanged = true
      newKey = allocateSourceKey(st.sources, pv.url)
      var replacement = copySourceRecord(rec, patch)
      replacement.key = newKey
      replacement.url = pv.url
      replacement.kind = pv.kind
      replacement.fetchedAt = 0
      replacement.channelCount = 0
      replacement.groupCount = 0
      replacement.lastUsed = nowInt(nowSec)
      if (!replacement.labelCustom) replacement.label = uniqueLabel(deriveLabel(pv.url, pv.kind), sourceLabels(st))
      return { ok: true, code: "ok", message: "", state: cloneState(st, { sources: st.sources.concat([replacement]) }), key: newKey, urlChanged: true, replacedKey: rec.key }
    }
  }
  return { ok: true, code: "ok", message: "", state: replaceSource(st, rec.key, patch), key: rec.key, urlChanged: urlChanged, replacedKey: "" }
}

function removeSource(state, key) {
  var st = cloneState(state)
  var removed = findSource(st.sources, key)
  if (!removed) return { state: st, removed: null }
  var out = []
  for (var i = 0; i < st.sources.length; i++) if (st.sources[i] !== removed) out.push(st.sources[i])
  return { state: cloneState(st, { sources: out }), removed: removed }
}

function touchSource(state, key, nowSec) {
  var st = cloneState(state)
  if (!findSource(st.sources, key)) return st
  return replaceSource(st, key, { lastUsed: nowInt(nowSec) })
}

// The timestamp a status carries (fetchedAt, else generatedAt), 0 for none.
function statusFetchedAt(status) {
  var fetched = Math.floor(Number(status && status.fetchedAt) || 0)
  if (fetched <= 0) fetched = Math.floor(Number(status && status.generatedAt) || 0)
  return fetched > 0 ? fetched : 0
}

// True when a successful status carries counts or a timestamp the record
// does not have yet, so the service adopts them when the active source's
// playlist-status.json loads (the migrated cache, a CLI-reconciled record
// fetched by the startup refresh: D-SRC-01) without rewriting state.json
// on every load.
function sourceStatsDiffer(rec, status) {
  if (!rec || !status || status.ok !== true) return false
  var fetched = statusFetchedAt(status)
  var recFetched = Math.max(0, Math.floor(Number(rec.fetchedAt) || 0))
  if (fetched > 0 ? fetched !== recFetched : recFetched === 0) return true
  return Math.max(0, Math.floor(Number(status.channelCount) || 0)) !== Math.max(0, Math.floor(Number(rec.channelCount) || 0))
    || Math.max(0, Math.floor(Number(status.groupCount) || 0)) !== Math.max(0, Math.floor(Number(rec.groupCount) || 0))
}

// Copies the counts of a successful `playlist` status onto the record so
// the list shows them without opening N status files. `nowSec` is the
// fallback when the status carries no fetchedAt.
function withSourceStats(state, key, status, nowSec) {
  var st = cloneState(state)
  if (!status || status.ok !== true || !findSource(st.sources, key)) return st
  var fetched = statusFetchedAt(status)
  if (fetched <= 0) fetched = Math.max(1, nowInt(nowSec))
  return replaceSource(st, key, {
    fetchedAt: fetched,
    channelCount: Math.max(0, Math.floor(Number(status.channelCount) || 0)),
    groupCount: Math.max(0, Math.floor(Number(status.groupCount) || 0))
  })
}

// The settings value is a CLI-origin value (SR11): a `~` path set through
// `omarchy bar set` must resolve to its record like any other.
function activeSourceKey(state, playlistUrl) {
  var url = normalizeSourceUrl(playlistUrl, { origin: "cli" })
  if (url === "") return ""
  var rec = findSourceByUrl(state ? state.sources : [], url)
  return rec ? str(rec.key) : ""
}

// D3 / SR8: the settings are the source of truth for the active source; the
// history follows. A known URL bumps `lastUsed` only when the active key
// actually changed and adopts a changed (valid) EPG URL; an unknown URL is
// added with a derived label and `origin` "migrated" on the very first v2
// run (no history, legacy cache layout) or "cli" afterwards. Beyond
// MAX_SOURCES the least recently used non-active records are evicted.
// `invalid` carries the validation result for a set but invalid URL (D16).
// `opts.adoptEpg === false` (D-SRC-10): the settings' epgUrl was written
// for the previous source (it did not change in the settings write that
// changed the playlist), so a known record keeps its own epgUrl and a new
// record starts without one; the default adopts it (a CLI `epgUrl` change,
// D-SRC-02, or the first reconcile after a state load).
function reconcileSources(state, playlistUrl, epgUrl, previousActiveKey, nowSec, origin, opts) {
  var st = cloneState(state)
  var out = { state: st, changed: false, activeKey: "", added: "", evicted: [], invalid: null }
  var raw = sanitizeInput(playlistUrl, MAX_SOURCE_URL + 1)
  if (raw === "") return out
  // The settings are the CLI path: `~` paths stay accepted here (SR11,
  // no 0.1.0 regression) while the forms keep refusing them.
  var pv = validateSourceUrl(raw, { origin: "cli" })
  if (!pv.ok) { out.invalid = pv; return out }
  var adoptEpg = !(opts && opts.adoptEpg === false)
  var ev = validateSourceUrl(epgUrl, { kind: "epg", origin: "cli" })
  var epg = adoptEpg && ev.ok ? ev.url : ""
  var now = nowInt(nowSec)
  var rec = findSourceByUrl(st.sources, pv.url)
  if (rec) {
    var patch = {}
    if (str(rec.key) !== str(previousActiveKey)) patch.lastUsed = now
    if (adoptEpg && ev.ok && epg !== str(rec.epgUrl)) patch.epgUrl = epg
    var keys = 0
    for (var k in patch) keys++
    if (keys > 0) { out.state = replaceSource(st, rec.key, patch); out.changed = true }
    out.activeKey = str(rec.key)
    return out
  }
  var kind = str(origin) !== "" && SOURCE_ORIGINS.indexOf(str(origin)) !== -1 ? str(origin) : (st.sources.length === 0 && st.cacheLayout !== CACHE_LAYOUT ? "migrated" : "cli")
  var key = allocateSourceKey(st.sources, pv.url)
  var record = {
    key: key, url: pv.url, epgUrl: epg, kind: pv.kind,
    label: uniqueLabel(deriveLabel(pv.url, pv.kind), sourceLabels(st)), labelCustom: false,
    origin: kind, addedAt: now, lastUsed: now, fetchedAt: 0, channelCount: 0, groupCount: 0
  }
  var sources = st.sources.concat([record])
  while (sources.length > MAX_SOURCES) {
    var victim = -1
    for (var i = 0; i < sources.length; i++) {
      if (sources[i].key === key) continue
      if (victim === -1 || Number(sources[i].lastUsed) < Number(sources[victim].lastUsed)) victim = i
    }
    if (victim === -1) break
    out.evicted.push(str(sources[victim].key))
    sources.splice(victim, 1)
  }
  out.state = cloneState(st, { sources: sources })
  out.changed = true
  out.activeKey = key
  out.added = key
  return out
}

// The only function that hands a URL to the guide: the edit form's values.
function sourceForEdit(state, key) {
  var rec = findSource(state ? state.sources : [], key)
  if (!rec) return null
  var view = sourceView(rec, "", 0, "")
  return {
    id: str(rec.key), key: str(rec.key), label: str(rec.label), labelCustom: rec.labelCustom === true,
    kind: view.kind, host: view.host, origin: str(rec.origin),
    playlistUrl: str(rec.url), epgUrl: str(rec.epgUrl),
    playlistMasked: maskUrl(rec.url), epgMasked: maskUrl(rec.epgUrl)
  }
}

// IPC `status` list: label / host / counts, never a URL.
function sourcesSummary(state, activeKey) {
  var views = sourceViews(state, activeKey, 0, null)
  var out = []
  for (var i = 0; i < views.length; i++) {
    out.push({ id: views[i].id, key: views[i].id, label: views[i].label, host: views[i].host, active: views[i].active, channelCount: views[i].channelCount, lastUsed: views[i].lastUsedAt })
  }
  return out
}

// Full bar entry for `shell.updateEntryInline`: every own key of `entry`
// copied (keys we do not own must survive the wholesale replace), `patch`
// applied, `id` forced.
function entryWith(entry, patch) {
  var out = {}
  var src = entry && typeof entry === "object" ? entry : {}
  for (var k in src) out[k] = src[k]
  var p = patch || {}
  for (var q in p) out[q] = p[q]
  if (str(out.id) === "" && str(src.id) !== "") out.id = str(src.id)
  return out
}

// A cache is stale when its status is not ok, has no fetchedAt, or is older
// than refreshMinutes.
function cacheStale(status, refreshMinutes, nowSec) {
  if (!status || status.ok !== true) return true
  var fetched = Number(status.fetchedAt) || 0
  if (fetched <= 0) return true
  var minutes = clampSetting("refreshMinutes", refreshMinutes)
  return (Number(nowSec) || 0) - fetched >= minutes * 60
}

// ---- form state and the Sources transitions (UX-SOURCES 1.9, 2.3, 7.3)
//
// form = { kind: "url" | "xtream", origin: "firstRun" | "sources", sourceId,
//          values: { label, playlist, epg } | { label, server, username, password },
//          original: the values the edit form opened with, focus: element id,
//          revealed: { playlist, epg } (true = raw value shown / typed),
//          error: null | { code, field, message }, probing, probeHost,
//          probeKind, parent: the form to return to (Xtream from a URL form) }

function formFields(form) {
  var f = form || {}
  if (f.kind === "xtream") return ["label", "server", "username", "password"]
  return f.origin === "firstRun" ? ["playlist", "epg"] : ["label", "playlist", "epg"]
}

function isFormField(form, id) {
  return formFields(form).indexOf(str(id)) !== -1
}

// The validation cap of a field (LIMITS, SR5).
function formLimit(field) {
  return FORM_LIMITS[str(field)] || MAX_SOURCE_URL
}

// What a field may hold: the cap plus slack, so an over-cap paste is kept
// long enough to be refused with `too_long` / `label_too_long` /
// `user_too_long` instead of being cut silently (SR18, SR22).
var FORM_SLACK = 64

function formCapacity(field) {
  return formLimit(field) + FORM_SLACK
}

function emptyValues(kind) {
  if (kind === "xtream") return { label: "", server: "", username: "", password: "" }
  return { label: "", playlist: "", epg: "" }
}

function copyValues(kind, values) {
  var out = emptyValues(kind)
  var src = values || {}
  for (var k in out) out[k] = str(src[k])
  return out
}

function copyForm(form) {
  var f = form || {}
  var kind = f.kind === "xtream" ? "xtream" : "url"
  return {
    kind: kind,
    origin: f.origin === "firstRun" ? "firstRun" : "sources",
    sourceId: str(f.sourceId),
    values: copyValues(kind, f.values),
    original: copyValues(kind, f.original),
    focus: str(f.focus),
    revealed: { playlist: !!(f.revealed && f.revealed.playlist), epg: !!(f.revealed && f.revealed.epg) },
    error: f.error && str(f.error.code) !== "" ? { code: str(f.error.code), field: str(f.error.field), message: str(f.error.message) } : null,
    probing: f.probing === true,
    probeHost: str(f.probeHost),
    probeKind: str(f.probeKind),
    parent: f.parent ? copyForm(f.parent) : null
  }
}

// A fresh form. Initial focus (UX 8 #25): `Label` when editing, `Playlist`
// when adding (first run included), `Server` on the Xtream form.
function formState(kind, origin, sourceId, values) {
  var k = kind === "xtream" ? "xtream" : "url"
  var id = str(sourceId)
  var f = copyForm({ kind: k, origin: origin, sourceId: id, values: values, original: values })
  f.focus = k === "xtream" ? "server" : (id !== "" ? "label" : "playlist")
  return f
}

// Tab order (UX-SOURCES 7.3): fields, then link rows, then buttons.
// `opts.savedSources` (> 0) adds the `Saved sources (n)` link on first run.
function formFocusOrder(form, opts) {
  var f = form || {}
  var o = opts || {}
  var order = formFields(f).slice()
  if (f.kind === "xtream") return order.concat(["save", "cancel"])
  if (f.origin === "firstRun") {
    if (Number(o.savedSources) > 0) order.push("savedSources")
    order.push("xtream")
    order.push("load")
    return order
  }
  if (str(f.sourceId) === "") order.push("xtream")
  return order.concat(["save", "cancel"])
}

function formHasText(form) {
  var f = form || {}
  var fields = formFields(f)
  for (var i = 0; i < fields.length; i++) if (f.values && str(f.values[fields[i]]) !== "") return true
  return false
}

function firstFieldWithText(form) {
  var f = form || {}
  var fields = formFields(f)
  for (var i = 0; i < fields.length; i++) if (f.values && str(f.values[fields[i]]) !== "") return fields[i]
  return ""
}

function guideWithForm(st, form) {
  var next = copyGuide(st)
  next.form = form
  return next
}

// Open a form. `kind` "url" | "xtream"; `origin` "firstRun" | "sources";
// `sourceId` for edits; `values` pre-fill (from `sourceForEdit`). A URL form
// that is open becomes the Xtream form's `parent` (values kept, UX 1.2).
function openForm(st, kind, origin, sourceId, values) {
  var cur = copyGuide(st)
  var form = formState(kind, origin, sourceId, values)
  if (kind === "xtream" && cur.form && cur.form.kind === "url" && (cur.mode === "sourceEdit" || cur.mode === "sources")) {
    form.parent = copyForm(cur.form)
    form.origin = form.parent.origin
  }
  var next = guideWithForm(cur, form)
  next.mode = kind === "xtream" ? "sourceXtream" : "sourceEdit"
  return next
}

// The first-run form: the unconfigured empty state contains the input. The
// query is cleared so the header above the form reads `Search channels...`
// again (UX 3.1.1; D-SRC-05 after the active source was removed).
function openFirstRun(st) {
  var next = withQuery(st, "")
  next.returnMode = ""
  return openForm(next, "url", "firstRun", "", null)
}

function openAddForm(st) {
  return openForm(st, "url", "sources", "", null)
}

function openEditForm(st, sourceId, values) {
  return openForm(st, "url", "sources", sourceId, values)
}

function openXtreamForm(st, origin) {
  var cur = copyGuide(st)
  var from = str(origin) || (cur.form ? cur.form.origin : "sources")
  return openForm(cur, "xtream", from, "", null)
}

// Leave a form. "cancel" returns to the parent form (values kept), to
// Sources, or asks the caller to close the guide (first run, every field
// empty); "saved" lands in `search` (first run) or `sources`.
function closeForm(st, outcome) {
  var cur = copyGuide(st)
  var f = cur.form
  var out = { state: cur, close: false, cancelProbe: false }
  if (!f) { out.state = withMode(cur, "search"); return out }
  if (outcome === "cancel" && f.parent) {
    var back = guideWithForm(cur, copyForm(f.parent))
    back.mode = back.form.kind === "xtream" ? "sourceXtream" : "sourceEdit"
    out.state = back
    return out
  }
  var next = guideWithForm(cur, null)
  if (f.origin === "firstRun") {
    if (outcome === "cancel") { out.state = cur; out.close = true; return out }
    next.mode = "search"
    next.returnMode = ""
    out.state = next
    return out
  }
  // Back to Sources; `returnMode` survives so Esc there still lands where
  // Sources was opened from.
  next.mode = "sources"
  out.state = next
  return out
}

function withFormPatch(st, patch) {
  var cur = copyGuide(st)
  if (!cur.form) return cur
  var f = cur.form
  for (var k in patch) f[k] = patch[k]
  return cur
}

// Set a field value (already sanitized by the caller for typing; capped
// here). Typing reveals the field (`opts.typed`), a paste re-masks it; an
// error on that field clears.
function withFormValue(st, field, value, opts) {
  var cur = copyGuide(st)
  if (!cur.form || !isFormField(cur.form, field)) return cur
  var o = opts || {}
  var id = str(field)
  var f = cur.form
  f.values[id] = capLength(str(value), formCapacity(id))
  if (isUrlField(id)) f.revealed[id] = o.typed === true && f.values[id] !== ""
  if (f.error && f.error.field === id) f.error = null
  return cur
}

function withFormFocus(st, id) {
  var cur = copyGuide(st)
  if (!cur.form) return cur
  var f = cur.form
  var target = str(id)
  if (f.focus === target) return cur
  if (isUrlField(f.focus)) f.revealed[f.focus] = false
  f.focus = target
  return cur
}

function moveFormFocus(st, delta, opts) {
  var cur = copyGuide(st)
  if (!cur.form) return cur
  var order = formFocusOrder(cur.form, opts)
  var at = order.indexOf(cur.form.focus)
  var step = Number(delta) < 0 ? -1 : 1
  var next = at === -1 ? (step < 0 ? order.length - 1 : 0) : (at + step + order.length) % order.length
  return withFormFocus(cur, order[next])
}

function fieldMaskable(form, field) {
  var f = form || {}
  var id = str(field)
  if (!isUrlField(id) || !f.values) return false
  var value = str(f.values[id])
  return maskUrl(value) !== value
}

function fieldRevealed(form, field) {
  var f = form || {}
  return !!(f.revealed && f.revealed[str(field)])
}

function fieldMasked(form, field) {
  return fieldMaskable(form, field) && !fieldRevealed(form, field)
}

// Ctrl+R / eye: toggles only when the value has something to mask.
function toggleReveal(st, field) {
  var cur = copyGuide(st)
  if (!cur.form || !fieldMaskable(cur.form, field)) return cur
  cur.form.revealed[str(field)] = !cur.form.revealed[str(field)]
  return cur
}

function withFormReveal(st, field, revealed) {
  var cur = copyGuide(st)
  if (!cur.form || !isUrlField(field)) return cur
  cur.form.revealed[str(field)] = revealed === true
  return cur
}

// Error line + focus on the offending field (UX 5.4: one error at a time).
function withFormError(st, error) {
  var cur = copyGuide(st)
  if (!cur.form) return cur
  var e = error && str(error.code) !== "" ? { code: str(error.code), field: str(error.field), message: str(error.message) } : null
  cur.form.error = e
  cur.form.probing = false
  if (e && isFormField(cur.form, e.field)) return withFormFocus(cur, e.field)
  return cur
}

// Freeze / thaw the form around a probe. Every URL field re-masks on
// submit (UX 4.4); `opts.host` / `opts.kind` feed the fetching line.
function withFormProbing(st, probing, opts) {
  var cur = copyGuide(st)
  if (!cur.form) return cur
  var o = opts || {}
  cur.form.probing = probing === true
  if (probing) {
    cur.form.error = null
    cur.form.revealed = { playlist: false, epg: false }
    cur.form.probeHost = str(o.host)
    cur.form.probeKind = str(o.kind)
  }
  return cur
}

// Values as submitted: every field trimmed (UX 2.3).
function formSubmitValues(form) {
  var f = copyForm(form)
  var out = {}
  for (var k in f.values) out[k] = sanitizeInput(f.values[k], formCapacity(k))
  return out
}

// Synchronous validation of the URL form (UX 5.4): first failing field in
// form order. `existing` is the source view list (labels + ids), `selfId`
// the source being edited. Returns the normalized URLs and the label to
// send to the service (empty label = let the service derive it).
function validateUrlForm(values, existing, selfId) {
  var v = values || {}
  var lv = validateLabel(v.label, existing, selfId)
  if (!lv.ok) return { ok: false, error: { code: lv.code, field: "label", message: lv.message } }
  var pv = validateSourceUrl(v.playlist)
  if (!pv.ok) return { ok: false, error: { code: pv.code, field: "playlist", message: pv.message } }
  var ev = validateSourceUrl(v.epg, { kind: "epg" })
  if (!ev.ok) return { ok: false, error: { code: ev.code, field: "epg", message: ev.message } }
  var dup = null
  var list = asList(existing)
  for (var i = 0; i < list.length; i++) {
    var item = list[i]
    if (item && typeof item === "object" && str(item.url) !== "" && normalizeSourceUrl(item.url) === pv.url && str(item.id !== undefined ? item.id : item.key) !== str(selfId)) dup = item
  }
  if (dup) return { ok: false, error: { code: "duplicate", field: "playlist", message: sourceErrorMessage("duplicate", { label: dup.label }) } }
  return { ok: true, error: null, label: lv.label, playlistUrl: pv.url, epgUrl: ev.url, kind: pv.kind === "file" ? "file" : "url", host: pv.host }
}

// Sources list rows: every source, then `Add source`, then `Add Xtream login`.
function sourcesRowCount(sourceCount) {
  return Math.max(0, Math.floor(Number(sourceCount) || 0)) + 2
}

function sourcesRowKind(index, sourceCount) {
  var n = Math.max(0, Math.floor(Number(sourceCount) || 0))
  var i = Math.floor(Number(index))
  if (!isFinite(i) || i < 0) return ""
  if (i < n) return "source"
  if (i === n) return "add"
  if (i === n + 1) return "xtream"
  return ""
}

// Cursor on entry: the active source, else row 0 (the Add row when empty).
function sourcesInitialCursor(views) {
  var list = asList(views)
  for (var i = 0; i < list.length; i++) if (list[i] && list[i].active) return i
  return 0
}

// After a removal the cursor keeps its index, clamped to the sources left
// (never parked on an action row while sources remain).
function cursorAfterRemove(index, remaining) {
  var n = Math.max(0, Math.floor(Number(remaining) || 0))
  if (n === 0) return 0
  return Math.max(0, Math.min(Math.floor(Number(index) || 0), n - 1))
}

function openSources(st, views) {
  var cur = copyGuide(st)
  if (cur.mode === "sources" || cur.mode === "confirmRemove") return cur
  cur.returnMode = cur.mode === "sourceEdit" || cur.mode === "sourceXtream" ? "sourceEdit" : cur.mode
  cur.mode = "sources"
  cur.sourceCursor = sourcesInitialCursor(views)
  return cur
}

// Esc / `o` in Sources: back to where it was opened from, nothing else
// changes. The first-run form (returnMode `sourceEdit`) survives in `form`.
// `opts.configured === false` (the active source was removed while Sources
// stayed open, or the CLI cleared the playlist meanwhile, UX 1.7 / SR8):
// the guide behind Sources is first run now, so the return lands in the
// first-run form (with its `Saved sources (n)` link) instead of a guide mode.
function closeSources(st, opts) {
  var cur = copyGuide(st)
  var o = opts || {}
  var back = cur.returnMode
  cur.returnMode = ""
  if (back === "sourceEdit" || back === "sourceXtream") {
    if (cur.form) { cur.mode = cur.form.kind === "xtream" ? "sourceXtream" : "sourceEdit"; return cur }
    return openFirstRun(cur)
  }
  if (o.configured === false) {
    cur.form = null
    return openFirstRun(cur)
  }
  cur.mode = back === "list" ? "list" : "search"
  return cur
}

function withSourceCursor(st, index) {
  var cur = copyGuide(st)
  cur.sourceCursor = Math.max(0, Math.floor(Number(index) || 0))
  return cur
}

function startRemove(st, sourceCount) {
  var cur = copyGuide(st)
  if (cur.mode !== "sources" || sourcesRowKind(cur.sourceCursor, sourceCount) !== "source") return cur
  cur.mode = "confirmRemove"
  return cur
}

// After a confirmed removal: Sources stays open while sources remain, the
// first-run form shows when the list is empty (UX 1.7).
function afterRemove(st, remaining) {
  var cur = copyGuide(st)
  if (Number(remaining) > 0) {
    cur.mode = "sources"
    cur.sourceCursor = cursorAfterRemove(cur.sourceCursor, remaining)
    return cur
  }
  cur.form = null
  return openFirstRun(cur)
}

// Guide state after a switch that leaves Sources: a fresh search-mode state
// on the initial scope (query cleared, UX 1.4 step 3).
function afterSwitch(scopeId) {
  return guideState(scopeId)
}

if (typeof module !== "undefined") {
  module.exports = {
    MAX_ROWS_DEFAULT: MAX_ROWS_DEFAULT,
    MAX_CHANNELS: MAX_CHANNELS,
    STOP_QUIT_GRACE_MS: STOP_QUIT_GRACE_MS,
    STOP_KILL_GRACE_MS: STOP_KILL_GRACE_MS,
    HEALTH_SKIPS_BEFORE_RESTART: HEALTH_SKIPS_BEFORE_RESTART,
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
    favoriteSet: favoriteSet,
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
    columnAnchor: columnAnchor,
    fallbackScope: fallbackScope,
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
    pushPlayedRecord: pushPlayedRecord,
    stateOnLoad: stateOnLoad,
    recordPlayed: recordPlayed,
    clearSession: clearSession,
    stateSession: stateSession,
    deadSessionVerdict: deadSessionVerdict,
    sessionAfterOutcome: sessionAfterOutcome,
    PLAYER_OUTCOMES: PLAYER_OUTCOMES,
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
    statusWarnings: statusWarnings,
    WARNING_PREFIX: WARNING_PREFIX,
    warningLabel: warningLabel,
    labelWarning: labelWarning,
    labelWarnings: labelWarnings,
    warningLine: warningLine,
    footerWarning: footerWarning,
    stopEscalation: stopEscalation,
    healthTick: healthTick,
    findBarEntry: findBarEntry,
    settingOf: settingOf,
    clampInt: clampInt,
    clampSetting: clampSetting,
    settingsFrom: settingsFrom,
    ownWriteInForce: ownWriteInForce,
    settingsWithOwnWrite: settingsWithOwnWrite,
    ownWriteFor: ownWriteFor,
    barEntryWritable: barEntryWritable,
    splitMpvArgs: splitMpvArgs,
    mpvOptionBase: mpvOptionBase,
    mpvHandoffName: mpvHandoffName,
    mpvArgWarnings: mpvArgWarnings,
    MPV_HANDOFF_TEXT: MPV_HANDOFF_TEXT,
    headerArgs: headerArgs,
    MPV_RAW_PREFIX: MPV_RAW_PREFIX,
    mpvWindowTitle: mpvWindowTitle,
    buildMpvArgv: buildMpvArgv,
    MPV_RESERVED: MPV_RESERVED,
    // ---- detached player (M2-02)
    PLAYER_STASH_SCHEMA: PLAYER_STASH_SCHEMA,
    PLAYER_ORPHAN_GRACE_SEC: PLAYER_ORPHAN_GRACE_SEC,
    PLAYER_GENERIC_FAILURE: PLAYER_GENERIC_FAILURE,
    helperArgv: helperArgv,
    playerStartArgv: playerStartArgv,
    playerStopArgv: playerStopArgv,
    playerRestartArgv: playerRestartArgv,
    playerProbeArgv: playerProbeArgv,
    playerOrphanCheckArgv: playerOrphanCheckArgv,
    playerStash: playerStash,
    parsePlayerProbe: parsePlayerProbe,
    parsePlayerEvent: parsePlayerEvent,
    endedVerdict: endedVerdict,
    probeVerdict: probeVerdict,
    playerDeathKind: playerDeathKind,
    playerSessionFollowUp: playerSessionFollowUp,
    PLAYER_LOG_TAIL: PLAYER_LOG_TAIL,
    PLAYER_ENTRY_OWNERS: PLAYER_ENTRY_OWNERS,
    playerRouterState: playerRouterState,
    pushPlayerLog: pushPlayerLog,
    routePlayerEvent: routePlayerEvent,
    rememberEntryOwner: rememberEntryOwner,
    channelForEnd: channelForEnd,
    endedReport: endedReport,
    focusPlayerArgv: focusPlayerArgv,
    notifyArgv: notifyArgv,
    sourceLabel: sourceLabel,
    hostOf: hostOf,
    redactUrls: redactUrls,
    scrubUrls: scrubUrls,
    cleanName: cleanName,
    displayName: displayName,
    looksLikeUrl: looksLikeUrl,
    formatClock: formatClock,
    formatCount: formatCount,
    pluralChannels: pluralChannels,
    epgFraction: epgFraction,
    epgNowStale: epgNowStale,
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
    guideSurface: guideSurface,
    footerStatus: footerStatus,
    footerHints: footerHints,
    formHints: formHints,
    // ---- sources (M2-01)
    STATE_VERSION: STATE_VERSION,
    CACHE_LAYOUT: CACHE_LAYOUT,
    MAX_SOURCES: MAX_SOURCES,
    MAX_SOURCE_URL: MAX_SOURCE_URL,
    MAX_LABEL: MAX_LABEL,
    MAX_XTREAM_SERVER: MAX_XTREAM_SERVER,
    MAX_XTREAM_FIELD: MAX_XTREAM_FIELD,
    SOURCES_DIR: SOURCES_DIR,
    MASK: MASK,
    MASK_CLEAR_PARAMS: MASK_CLEAR_PARAMS,
    LIMITS: LIMITS,
    SOURCE_KEYS: SOURCE_KEYS,
    SOURCE_KEY_RE: SOURCE_KEY_RE,
    GUIDE_MODES: GUIDE_MODES,
    sanitizeInput: sanitizeInput,
    sanitizeTyping: sanitizeTyping,
    codePointLength: codePointLength,
    capCodePoints: capCodePoints,
    looksLikeHost: looksLikeHost,
    formCapacity: formCapacity,
    sourceErrorMessage: sourceErrorMessage,
    sourceReason: sourceReason,
    validateSourceUrl: validateSourceUrl,
    normalizeSourceUrl: normalizeSourceUrl,
    isUrlField: isUrlField,
    sourceKey: sourceKey,
    isSourceKey: isSourceKey,
    findSource: findSource,
    findSourceByUrl: findSourceByUrl,
    allocateSourceKey: allocateSourceKey,
    sourceCacheDir: sourceCacheDir,
    deriveLabel: deriveLabel,
    labelTaken: labelTaken,
    uniqueLabel: uniqueLabel,
    defaultSourceLabel: defaultSourceLabel,
    validateLabel: validateLabel,
    maskUrl: maskUrl,
    encodeQueryValue: encodeQueryValue,
    xtreamUrls: xtreamUrls,
    validateXtream: validateXtream,
    pluralGroups: pluralGroups,
    countsLine: countsLine,
    formatLastUsed: formatLastUsed,
    formatAgo: formatAgo,
    sourceView: sourceView,
    sourceViews: sourceViews,
    sourceRows: sourceRows,
    sourceDetail: sourceDetail,
    sourceAccessibleName: sourceAccessibleName,
    sourcesHeaderCount: sourcesHeaderCount,
    sourcesRowAccessibleName: sourcesRowAccessibleName,
    confirmRemoveMessage: confirmRemoveMessage,
    fetchingLine: fetchingLine,
    probeFailureLine: probeFailureLine,
    sourceTransient: sourceTransient,
    cloneState: cloneState,
    withCacheLayout: withCacheLayout,
    normalizeSourceRecord: normalizeSourceRecord,
    hasControlChars: hasControlChars,
    addSource: addSource,
    updateSource: updateSource,
    removeSource: removeSource,
    touchSource: touchSource,
    withSourceStats: withSourceStats,
    sourceStatsDiffer: sourceStatsDiffer,
    statusFetchedAt: statusFetchedAt,
    activeSourceKey: activeSourceKey,
    reconcileSources: reconcileSources,
    sourceForEdit: sourceForEdit,
    sourcesSummary: sourcesSummary,
    entryWith: entryWith,
    cacheStale: cacheStale,
    formFields: formFields,
    isFormField: isFormField,
    formLimit: formLimit,
    copyForm: copyForm,
    formState: formState,
    formFocusOrder: formFocusOrder,
    formHasText: formHasText,
    openForm: openForm,
    openFirstRun: openFirstRun,
    openAddForm: openAddForm,
    openEditForm: openEditForm,
    openXtreamForm: openXtreamForm,
    closeForm: closeForm,
    withFormValue: withFormValue,
    withFormFocus: withFormFocus,
    moveFormFocus: moveFormFocus,
    fieldMaskable: fieldMaskable,
    fieldRevealed: fieldRevealed,
    fieldMasked: fieldMasked,
    toggleReveal: toggleReveal,
    withFormReveal: withFormReveal,
    withFormError: withFormError,
    withFormProbing: withFormProbing,
    formSubmitValues: formSubmitValues,
    validateUrlForm: validateUrlForm,
    sourcesRowCount: sourcesRowCount,
    sourcesRowKind: sourcesRowKind,
    sourcesInitialCursor: sourcesInitialCursor,
    cursorAfterRemove: cursorAfterRemove,
    openSources: openSources,
    closeSources: closeSources,
    withSourceCursor: withSourceCursor,
    startRemove: startRemove,
    afterRemove: afterRemove,
    afterSwitch: afterSwitch
  }
}
