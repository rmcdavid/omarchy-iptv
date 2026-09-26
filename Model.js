// Model.js -- pure logic for io.github.rmcdavid.iptv.
//
// Rules (see ARCHITECTURE.md (dev branch), "Coding standards"):
//   - No QML, no I/O, no timers, no Quickshell APIs. Inputs in, values out.
//   - ES5-style functions and `var`: this file is loaded by the QML engine
//     (`import "Model.js" as Model`) and by node (`require("./Model.js")`).
//     No ES module syntax, no top-level `const`/`let` exports.
//   - Every function must be safe on null/undefined input.
//   - Text normalization here MUST stay byte-for-byte compatible with
//     `normalize_text` / `search_key` / `fnv1a32` in bin/omarchy-iptv; the
//     helper writes searchKey/id into channels.json and the guide only
//     normalizes the query. Model.test.js (dev branch tests) and test_playlist.py (dev branch tests)
//     pin the shared vectors.
//   - ASCII only. Nerd Font glyphs and typographic characters are written
//     as \uXXXX escapes (surrogate pairs for the supplementary plane).
//
// Rulings applied (ARCHITECTURE.md (dev branch) section 12): R2 settings clamps,
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
// state.json schema (ARCHITECTURE-SOURCES.md (dev branch) 2.1): version 2 adds the
// `sources` history and `cacheLayout`; parseState still reads version 1.
// The optional nullable `session` key (ARCHITECTURE-PLAYER.md (dev branch) 8) is
// additive and does NOT bump this: both readers whitelist the keys they
// know, so an older build drops it and a newer one reads its absence.
var STATE_VERSION = 2

// ---- D-HOST-1: the build that is RUNNING, not the one on disk -------------
//
// `omarchy plugin update` fetches, fast-forwards and calls
// `omarchy-shell shell rescanPlugins`, which is a hot reload rather than a
// restart. This plugin sets `keepLoaded: true` so its overlay survives a
// reload -- and an already-mounted overlay keeps the component it was built
// from. So the files on disk update and the running interface does not, with
// nothing to tell the user.
//
// That is not a hypothetical: the 0.7.3 update landed at 14:58 inside a boot
// that had started two days earlier, and the shell rendered the pre-update
// Guide.qml for the rest of that boot's life. It cost a day of contrast work,
// because a verification pass measured a component the shell had never loaded
// (F-CAL-3, F-CAL-4). A user gets the quieter version of the same thing: they
// update, and keep the old interface.
//
// This constant travels WITH the loaded QML. The version in manifest.json
// travels with the directory. When they disagree, the running build is stale.
// The release gate proves the two agree when a version is cut (dev branch), so
// a disagreement at RUNTIME can only mean a reload that did not re-instantiate.
var PLUGIN_VERSION = "0.8.0"

// Both arguments are strings; anything unparseable answers false, because a
// notice nobody can act on is worse than no notice. Never throws: this runs in
// a QML binding, and a binding that raises leaves the footer undefined.
// Parse the version out of a manifest.json the runtime read from disk. Never
// throws and never returns undefined: this feeds a QML binding, and JSON that
// is mid-write during an update is a normal thing to see, not an error.
function manifestVersion(text) {
  try {
    var m = JSON.parse(str(text))
    return m && typeof m.version === "string" ? m.version : ""
  } catch (e) { return "" }
}

function staleBuild(loaded, onDisk) {
  var a = str(loaded), b = str(onDisk)
  if (a === "" || b === "") return false
  return a !== b
}

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
  tvPause: "\udb83\udfd1", // U+F0FD1 nf-md-television_pause  paused (bar); R7 forbids colour alone, and fc-query confirms this codepoint is in the installed font
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
  closeCircle: "\udb80\udd59", // U+F0159 nf-md-close_circle    remove action button
  // Channel numbers (M2-03 4.6)
  dialpad: "\udb81\ude1c"    // U+F061C nf-md-dialpad           number entry chip
}

// Settings clamps (R2). `showChannelName` is `!== false`; strings are trimmed.
var SETTING_RANGES = {
  refreshMinutes: { def: 360, min: 15, max: 1440 },
  maxRecents: { def: 10, min: 1, max: 50 },
  barLabelMaxWidth: { def: 180, min: 60, max: 600 },
  // M2-03 CN2: the inter-digit window is a setting, not a constant, because
  // the gap between a slow typist getting channel 101 and getting channels
  // 1, 0 and 1 is an accessibility matter.
  numberEntryMs: { def: 2000, min: 400, max: 5000 },
  // M2-05 section 6. The box is a PERCENTAGE of the monitor, not a pixel
  // constant (PIP4): Omarchy's own 600x338 would take 44 percent of this
  // 1366x768 display in both axes, and omarchy-hyprland-window-pop's
  // 1300x900 is taller than the screen.
  pipSizePercent: { def: 30, min: 15, max: 60 },
  pipMargin: { def: 16, min: 0, max: 200 }
}

// Channel numbers (M2-03 1.2 / 9.1). A number is at most 5 major digits and
// an optional 1-to-3 digit subchannel. MAX_CHNO_LABEL is the hard bound the
// row column's width formula is derived from (4.2) and the entry buffer's
// cap (2.4).
//
// It is 9, not the 7 of design 1.2 step 9. That step calls a 7-character
// label "unreachable given 4 and 6", which is wrong: the grammar it states
// two steps earlier admits "99999.999", which is nine. At 7 the parser would
// have had to reject a number its own grammar allows, and the buffer cap
// would have made a displayed channel untypable -- the exact failure CN6
// rejects for non-numeric values. The grammar is authoritative; the derived
// bound follows it. See the lane A report, request 2.
var MAX_CHNO_MAJOR = 99999
var MAX_CHNO_MINOR = 999
var MAX_CHNO_LABEL = 9
// CN8: providers write both "7.1" and "8-1", so both are accepted on PARSE;
// only "." is ever produced, and it is what the user types (plus ",", which
// is what the numpad decimal key emits on several layouts -- see the Gate A1
// evidence in the M2-03 lane A report).
var CHNO_SEPARATORS = ".-"
var CHNO_ENTRY_SEP = "."
var CHANNEL_ORDERS = ["playlist", "number"]
// CN11: the product owner's amendment to OQ 11. `tvg-chno` is what every
// asset uses, but a playlist that silently has no numbers is the worst
// failure this feature can have, so the aliases are read too. The helper's
// record whitelist decides which of these can actually arrive (see the lane
// A report, request 1); the model reads whichever is present.
var CHNO_FIELDS = ["chno", "tvgChno", "channelNumber", "tvg-chno", "tvg-channel-number", "channel-number"]

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
  // D-SINK-2. `--script` is not the option: mpv's own `--list-options` calls it
  // "alias for --scripts-append". So reserving it and not `--scripts-append`
  // reserved the alias and left the real option open, and a pasted
  // `--scripts-append=/tmp/x.lua` ran arbitrary Lua inside the player, which
  // can read `path` -- the credentialed stream URL. The reserved set is now
  // matched against the option's BASE name (mpvOptionBase strips -append,
  // -add, -set, -pre, -clr, -del, -remove, -toggle), so every spelling of a
  // list option is covered by naming it once.
  "--script": true,
  "--scripts": true,
  // D-SINK-4. Reserved, not merely defaulted off, and the distinction is the
  // whole fix. `--load-scripts=no` is in the base argv, but user mpvArgs are
  // concatenated AFTER it (buildMpvArgv's last line), so a pasted
  // `--load-scripts=yes` would win and silently put the credentialed stream
  // URL back on the session bus. That is the shape of D-SINK-2 again: an
  // option defaulted rather than reserved is an option the user can undo
  // without knowing what it was for.
  //
  // Unlike `--ytdl`, which is deliberately left re-enablable (PO-5) because
  // it trades speed for reach, this one guards a credential and has no
  // legitimate counter-position.
  "--load-scripts": true,
  // NOT --script-opts: ruling PO-10 / D-PLY-5 keeps it a HANDOFF option,
  // allowed with a warning, and the suite holds that line. Base-name matching
  // still covers its spellings, so --script-opts-append warns like --script-opts
  // rather than slipping through unwarned.
  "--include": true,              // loads a config file, which can set any of these
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

// The same class WITHOUT `*` (U+002A) and `+` (U+002B), for the id fold only.
// Folding is two jobs, not one. SEARCH wants punctuation gone: a user typing
// "amc" must reach "USA: AMC+", so normalizeText stays exactly as it is. An
// ID wants every character that tells two streams apart, and `+` and `*` are
// the two that do: measured over the user's four real playlists, dropping
// them merges "USA  AMC" with "USA: AMC+", "US: ESPN" with "US: ESPN*",
// "US NESN (A)" with "US NESN+ (A)" and four Fanduel regional pairs -- 9
// colliding groups and 20 rows that are different streams under one key.
// Keeping them takes the four lists from 75 colliding groups / 155 rows to
// 65 / 133 and raises surviving ids from 5,108 to 5,127 of 5,221. `&`, `#`
// and `@` were measured the same way and change nothing on any of the four,
// so they are not in the class. Mirrors _ID_PUNCT in bin/omarchy-iptv.
var ID_PUNCT_RE = /[\s!-\)\,-\/:-@\[-`{-~]+/g

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
  return foldText(value, PUNCT_RE)
}

// The id fold (python mirror: normalize_id_text). Identical to normalizeText
// except that `+` and `*` survive, because they are the difference between
// two channels rather than noise inside one. Never use it for search.
function normalizeIdText(value) {
  return foldText(value, ID_PUNCT_RE)
}

function foldText(value, punct) {
  var text = decompose(str(value).toLowerCase())
  var out = ""
  for (var i = 0; i < text.length; i++) {
    var ch = text.charAt(i)
    out += FOLD[ch] !== undefined ? FOLD[ch] : ch
  }
  return out.replace(punct, " ").replace(/^ | $/g, "")
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

// Channel id schemes (ARCHITECTURE.md decision 6; python mirror:
// CHANNEL_ID_SCHEME in bin/omarchy-iptv). Scheme 1 shipped from 0.1 to 0.7:
// `t:<tvg-id>` when unique in the playlist, else `u:<fnv1a32(url)>`. An
// Xtream stream URL carries the account password, so every `u:` id dies the
// day that password is rotated -- 1 id of 3,335 survived one on the user's
// own list, taking every favorite and recent with it. Scheme 2 tries the
// channel NAME in between: the one column a rotation cannot touch.
var CHANNEL_ID_SCHEME_LEGACY = 1
var CHANNEL_ID_SCHEME = 2
// The last-resort display name, `Channel <n>`, whose n is the row's POSITION.
// Both the word and the pattern that recognises one after normalizeText come
// from the same constant, and displayName() below builds the name from it --
// engineering rule 13 (dev branch), two things joined by a call rather than by a name. The
// python mirror does the same with GENERATED_NAME_WORD.
var GENERATED_NAME_WORD = "Channel"
var GENERATED_NAME_RE = new RegExp("^" + GENERATED_NAME_WORD.toLowerCase() + " [0-9]+$")

// The `n:` base of a channel name, or "" when the name cannot key one: a name
// that normalizes to nothing, or a generated `Channel <n>`, whose id would
// move the moment the provider inserts a row above it.
function nameIdKey(name) {
  var norm = normalizeIdText(name)
  if (norm === "" || GENERATED_NAME_RE.test(norm)) return ""
  return "n:" + fnv1a32(norm)
}

// `#2`, `#3`... on a repeated base so every row stays addressable.
function suffixIds(bases) {
  var seen = {}
  var out = []
  for (var i = 0; i < bases.length; i++) {
    var count = (seen[bases[i]] || 0) + 1
    seen[bases[i]] = count
    out.push(count === 1 ? bases[i] : bases[i] + "#" + count)
  }
  return out
}

// Every channel's id, in playlist order (python mirror: channel_ids).
//
// Scheme 2 is scheme 1 with ONE substitution: a row that would fall back to
// the URL hash uses its `n:` name key instead, and only when that key is
// unique across the whole playlist. Every other row keeps the exact id it
// already had.
//
// Doing it as a substitution rather than as a third branch of the base rule
// is what makes the upgrade safe, and it took a failing test to find that
// out. Recompute the suffixes over the new stream instead and a list with two
// rows on one URL re-uses one row's OLD id for the OTHER row -- the saved
// favorite still resolves, silently, to a different channel, the exact
// failure this change exists to stop. As a substitution, a scheme-2 id is
// either the row's own scheme-1 id or an `n:` id that has never existed
// before, so no id can change meaning.
//
// The uniqueness test on the name is the other half: a name two rows share
// cannot tell them apart, so an HD/SD twin pair keeps its URL ids rather than
// being merged into one favorite, and an fnv1a32 collision between two
// different names lands in the same branch. Names are counted over EVERY
// channel, including those taking a `t:` id, so the name pool depends on
// nothing but names.
//
// ACCEPTED LIMIT, UNRESOLVED (D-ID-1). The uniqueness test is answered from
// ONE snapshot, and uniqueness only exists across snapshots: refusing a
// colliding pair today DEFERS the collision rather than settling it. Remove
// one member later and the survivor becomes unique, takes the `n:` key, and
// inherits any favorite that meant the row which went away -- a silent WRONG
// channel. Measured with nameIdKey over the user's four real lists, 26
// colliding groups on USChannels (55 rows, largest 3) and 39 on SportsPPVAll
// (78 rows, largest 2), so at most 133 rows of 5,221 are exposed and only if
// the provider drops one of a pair. The rate is unknown: nobody has a second
// snapshot. The full note, and what would settle it, is in the python mirror
// (channel_ids in bin/omarchy-iptv).
function channelIds(channels, scheme) {
  var legacy = legacyChannelIds(channels)
  if ((scheme === undefined ? CHANNEL_ID_SCHEME : Number(scheme)) < CHANNEL_ID_SCHEME) return legacy
  return substituteNameIds(channels, legacy)
}

// Scheme 1, and the base every scheme-2 id is built from.
function legacyChannelIds(channels) {
  var list = asList(channels)
  var tvgCounts = {}
  var bases = []
  var i, tvg
  for (i = 0; i < list.length; i++) {
    tvg = str(list[i] && list[i].tvgId)
    if (tvg !== "") tvgCounts[tvg] = (tvgCounts[tvg] || 0) + 1
  }
  for (i = 0; i < list.length; i++) {
    tvg = str(list[i] && list[i].tvgId)
    bases.push(tvg !== "" && tvgCounts[tvg] === 1 ? "t:" + tvg : "u:" + fnv1a32(str(list[i] && list[i].url)))
  }
  return suffixIds(bases)
}

// The one substitution scheme 2 makes on top of scheme 1. Separate from
// channelIds so channelIdRemap hashes every URL once instead of twice.
function substituteNameIds(channels, legacy) {
  var list = asList(channels)
  var nameKeys = []
  var nameCounts = {}
  var i
  for (i = 0; i < list.length; i++) {
    var key = nameIdKey(list[i] && list[i].name)
    nameKeys.push(key)
    if (key !== "") nameCounts[key] = (nameCounts[key] || 0) + 1
  }
  var out = []
  for (i = 0; i < legacy.length; i++) {
    var substitute = legacy[i].indexOf("u:") === 0 && nameKeys[i] !== "" && nameCounts[nameKeys[i]] === 1
    out.push(substitute ? nameKeys[i] : legacy[i])
  }
  return out
}

// {scheme-1 id: scheme-2 id} for the rows the scheme change moves.
//
// Idempotent with no marker anywhere in state.json, and no schema change of
// any kind. Because scheme 2 is a substitution (channelIds), every key of
// this map is the scheme-1 id of a row that now answers to an `n:` id, and an
// `n:` id is never a key -- so after one pass nothing in the state holds a
// key and a second pass moves nothing. The node and python suites both pin
// that invariant rather than trusting this paragraph.
function channelIdRemap(channels) {
  var old = legacyChannelIds(channels)
  var fresh = substituteNameIds(channels, old)
  var remap = {}
  for (var i = 0; i < old.length; i++) if (old[i] !== fresh[i]) remap[old[i]] = fresh[i]
  return remap
}

// Move every channel reference state.json persists onto the current scheme.
// Returns a NEW state plus the number of references moved; 0 means the state
// was already current and the caller must not write. Favorites keep their
// order and one that lands on a favorite already in the list is merged rather
// than duplicated -- possible because favorites are global across sources
// (ARCHITECTURE-SOURCES.md D14) and another source may already hold the
// target id.
function remapStateIds(state, remap) {
  var st = cloneState(state, {})
  var moved = 0
  var i, target
  if (!remap) return { state: st, moved: 0 }
  var favorites = []
  for (i = 0; i < st.favorites.length; i++) {
    target = remap[st.favorites[i]] !== undefined ? remap[st.favorites[i]] : st.favorites[i]
    if (target !== st.favorites[i]) moved++
    if (favorites.indexOf(target) === -1) favorites.push(target)
  }
  st.favorites = favorites
  // Recents are keyed by id exactly as favorites are, so the remap has to
  // merge them the same way: two rows that moved onto one id are one entry,
  // most recent kept, or the list grows a duplicate the guide then renders
  // twice. This was the asymmetry review found -- favorites merged, recents
  // did not.
  var recents = []
  var seenRecent = {}
  for (i = 0; i < st.recents.length; i++) {
    var entry = st.recents[i]
    if (!entry) continue
    target = remap[str(entry.id)]
    if (target === undefined) target = str(entry.id)
    else moved++
    if (seenRecent[target] === true) continue
    seenRecent[target] = true
    recents.push({ id: target, name: str(entry.name), at: entry.at })
  }
  st.recents = recents
  var records = ["lastPlayed", "session"]
  for (i = 0; i < records.length; i++) {
    var played = st[records[i]]
    target = played ? remap[str(played.id)] : undefined
    if (target === undefined) continue
    moved++
    st[records[i]] = { id: target, name: str(played.name), at: played.at }
  }
  return { state: st, moved: moved }
}

// The service's call site: the loaded state and the loaded channel list.
// Write only when `moved` is non-zero -- after one pass it always is zero.
function remapChannelIds(state, channels) {
  return remapStateIds(state, channelIdRemap(channels))
}

// The helper assigns `id` when it writes channels.json (channelIdBases
// above). This mirrors the per-channel half of the rule for callers that
// build channels in memory: the playlist-wide uniqueness tests cannot be
// answered from one row, so a caller holding the whole list uses assignIds.
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
  return GENERATED_NAME_WORD + " " + (Number(position) > 0 ? Math.floor(Number(position)) : "?")
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
    // M2-03 1.3: three derived fields per row, inside the pass that is
    // already running. A row with no usable number short-circuits before
    // the scanner runs, so an unnumbered 10k playlist pays one property
    // read per channel. The raw `chno` string stays untouched; nothing
    // renders it (CN6/CN7: what the user sees is what the user types).
    var rawChno = chnoRawOf(src)
    if (rawChno === "") {
      row.chnoKey = ""
      row.chnoLabel = ""
      row.chnoSort = -1
    } else {
      var chno = parseChno(rawChno)
      row.chnoKey = chno.key
      row.chnoLabel = chno.label
      row.chnoSort = chno.sort
    }
    out.push(row)
  }
  return out
}

// ------------------------------------------------------------ channel numbers (M2-03)
//
// Rulings CN1-CN14 (M2-03-CHANNEL-NUMBERS.md (dev branch) section 13) and the
// technical contract in section 9.1. Everything here is pure: the guide owns
// the timer, the cursor and the chip, and owns no number logic at all.

// The single "this channel has no number" answer, so every failure path
// returns the same shape and no caller has to test for a partial one.
var CHNO_NONE = { ok: false, key: "", label: "", sort: -1, major: -1, minor: -1 }
var CHNO_NO_MATCH = { kind: "none", channelIndex: -1, key: "", label: "", matches: 0, ordinal: 0 }
var CHNO_NO_NUMBERS_TEXT = "No channel numbers in this playlist"

function chnoFail() {
  return { ok: false, key: "", label: "", sort: -1, major: -1, minor: -1 }
}

// CN11. The first alias that carries anything wins; the order is the
// product owner's preference order, `tvg-chno` first.
function chnoRawOf(channel) {
  if (!channel || typeof channel !== "object") return ""
  for (var i = 0; i < CHNO_FIELDS.length; i++) {
    var value = channel[CHNO_FIELDS[i]]
    if (value === undefined || value === null) continue
    var text = str(value)
    if (text !== "") return text
  }
  return ""
}

function isAsciiDigit(code) {
  return code >= 0x30 && code <= 0x39
}

// M2-03 1.2. A character scanner rather than a regular expression: this runs
// once per numbered channel at load time and the grammar is trivial.
//
// ASCII digits only. Arabic-Indic (U+0660..U+0669) and full-width
// (U+FF10..U+FF19) decimals are rejected on purpose: the user cannot type
// them on the keys this feature binds, and a channel that claims a number
// nobody can reach is worse than a channel with no number at all (CN6).
//
// Leading zeros are dropped in both `key` and `label` (CN7): "007" is 7,
// because the number you see must be the number you type.
function parseChno(raw) {
  var text = str(raw)
  var from = 0
  var to = text.length
  while (from < to && isChnoSpace(text.charCodeAt(from))) from++
  while (to > from && isChnoSpace(text.charCodeAt(to - 1))) to--
  // A few providers write "#12".
  if (from < to && text.charCodeAt(from) === 0x23) from++
  if (from >= to) return chnoFail()

  var major = 0
  var digits = 0
  var i = from
  for (; i < to && isAsciiDigit(text.charCodeAt(i)); i++) {
    major = major * 10 + (text.charCodeAt(i) - 0x30)
    digits++
  }
  if (digits === 0 || digits > 5 || major > MAX_CHNO_MAJOR) return chnoFail()

  var minor = -1
  if (i < to) {
    if (CHNO_SEPARATORS.indexOf(text.charAt(i)) === -1) return chnoFail()
    i++
    minor = 0
    var minorDigits = 0
    for (; i < to && isAsciiDigit(text.charCodeAt(i)); i++) {
      minor = minor * 10 + (text.charCodeAt(i) - 0x30)
      minorDigits++
    }
    if (minorDigits === 0 || minorDigits > 3 || minor > MAX_CHNO_MINOR) return chnoFail()
    if (i !== to) return chnoFail()
  }

  var label = minor < 0 ? String(major) : String(major) + CHNO_ENTRY_SEP + String(minor)
  if (label.length > MAX_CHNO_LABEL) return chnoFail()
  return {
    ok: true,
    key: label,
    label: label,
    // A bare "7" and "7.0" collide here; the tie is broken by playlist
    // index, which is deterministic (1.2 step 8).
    sort: major * 1000 + (minor < 0 ? 0 : minor),
    major: major,
    minor: minor
  }
}

// The whitespace sanitizeInput strips, plus tab: a value lifted out of an
// #EXTINF attribute can carry any of them.
function isChnoSpace(code) {
  return code === 0x20 || code === 0x09 || code === 0x0a || code === 0x0d || code === 0xa0 || code === 0xfeff
}

// A prepared row's number, trusting the fields prepareChannels wrote and
// falling back to a parse for any array that never went through it (a
// hand-edited cache, a test fixture, a caller that skipped preparation).
function chnoOf(channel) {
  if (!channel || typeof channel !== "object") return CHNO_NONE
  if (typeof channel.chnoKey === "string") {
    if (channel.chnoKey === "") return CHNO_NONE
    var sort = Number(channel.chnoSort)
    if (isFinite(sort) && sort >= 0) {
      var label = typeof channel.chnoLabel === "string" && channel.chnoLabel !== "" ? channel.chnoLabel : channel.chnoKey
      return { ok: true, key: channel.chnoKey, label: label, sort: Math.floor(sort), major: -1, minor: -1 }
    }
  }
  var parsed = parseChno(chnoRawOf(channel))
  return parsed.ok ? parsed : CHNO_NONE
}

// M2-03 1.4. The first persistent non-id index in the project, modelled on
// indexById. `byKey` values are arrays of PLAYLIST indices in ascending
// order, which is what makes duplicate cycling (CN9) and the "(1 of 2)" copy
// need no second structure. `order` is every numbered channel sorted by
// (chnoSort, playlist index) and `labels` is parallel to it, so the prefix
// scan walks numeric order whatever the display order is.
//
// Empty input, null and non-arrays all return the same shape with
// hasNumbers false; every consumer must tolerate it.
function buildChnoIndex(channels) {
  var list = asList(channels)
  var byKey = {}
  var ids = {}
  var numbered = []
  var maxLabelLen = 0
  for (var i = 0; i < list.length; i++) {
    var chno = chnoOf(list[i])
    if (!chno.ok) continue
    ids[i] = channelId(list[i])
    // hasOwnProperty, not `=== undefined`: a hand-edited cache row could
    // carry chnoKey "constructor", and `byKey.constructor` is a function.
    if (!Object.prototype.hasOwnProperty.call(byKey, chno.key)) byKey[chno.key] = []
    byKey[chno.key].push(i)
    numbered.push({ at: i, sort: chno.sort, label: chno.label })
    if (chno.label.length > maxLabelLen) maxLabelLen = chno.label.length
  }
  // An explicit playlist-index fallback rather than relying on the engine's
  // sort being stable: V4 and node must agree exactly.
  numbered.sort(function (a, b) {
    if (a.sort !== b.sort) return a.sort - b.sort
    return a.at - b.at
  })
  var order = []
  var labels = []
  for (var j = 0; j < numbered.length; j++) {
    order.push(numbered[j].at)
    labels.push(numbered[j].label)
  }
  var duplicates = 0
  for (var key in byKey) {
    if (!Object.prototype.hasOwnProperty.call(byKey, key)) continue
    if (byKey[key].length > 1) duplicates += byKey[key].length
  }
  return {
    byKey: byKey,
    order: order,
    labels: labels,
    // Channel id per numbered playlist index. Addition to the section 1.4
    // shape, and the thing that makes every consumer order-independent:
    // byKey holds PLAYLIST indices, but `channelOrder: number` hands the
    // guide and the service a reordered array (5.2), so an index alone
    // cannot name a row. 5.2 says to map "through the channel's id"; this
    // is what makes that possible without a second array. Numbered channels
    // only, so an unnumbered playlist pays nothing. See the lane A report,
    // request 5.
    ids: ids,
    count: order.length,
    duplicates: duplicates,
    maxLabelLen: order.length > 0 ? maxLabelLen : 0,
    hasNumbers: order.length > 0
  }
}

// The channel id at a playlist index, or "" when that index is not numbered.
function chnoIdAt(index, channelIndex) {
  var idx = index || {}
  var ids = idx.ids && typeof idx.ids === "object" ? idx.ids : {}
  var at = Math.floor(Number(channelIndex))
  if (!isFinite(at) || at < 0) return ""
  return Object.prototype.hasOwnProperty.call(ids, at) ? str(ids[at]) : ""
}

// What the user has typed, canonicalized far enough to look up: "," folded
// to "." (CN8) and leading zeros dropped from the major part (CN7, 2.4 --
// "0" then "7" is channel 7). The minor part is left exactly as typed,
// because mid-entry "7.0" may still become "7.05" and stripping there would
// guess at a number the user has not finished writing.
function chnoEntryKey(buffer) {
  var text = str(buffer).replace(/,/g, CHNO_ENTRY_SEP)
  var cut = text.indexOf(CHNO_ENTRY_SEP)
  var major = cut === -1 ? text : text.substring(0, cut)
  var rest = cut === -1 ? "" : text.substring(cut)
  var at = 0
  while (at < major.length - 1 && major.charAt(at) === "0") at++
  return major.substring(at) + rest
}

// M2-03 2.3. The buffer resolves to a channel on every keystroke, so the
// cursor can follow it live -- which is what turns three keystrokes into a
// verified selection rather than a leap.
//
// 1. exact: the normalized buffer is a key. With more than one channel on
//    that key and the cursor already on one of them, the NEXT one, wrapping
//    (CN9). Stateless: the cycle is derived from where the cursor already
//    is, so nothing has to remember a previous press and nothing expires.
// 2. prefix: the first label in numeric order that starts with the buffer.
// 3. none: nothing moves; the caller shows the miss and the user can
//    Backspace out of it without committing (CN1 -- a mistyped number costs
//    nothing).
function resolveChno(index, buffer, currentChannelIndex) {
  var idx = index || {}
  var byKey = idx.byKey && typeof idx.byKey === "object" ? idx.byKey : {}
  var typed = str(buffer)
  if (typed === "" || idx.hasNumbers !== true) return { kind: "none", channelIndex: -1, key: "", label: "", matches: 0, ordinal: 0 }

  var entry = chnoEntryKey(typed)
  // A complete number normalizes through the parser ("07.01" is "7.1");
  // a half-typed one ("7.") only ever reaches the prefix scan below.
  var parsed = parseChno(entry)
  var key = parsed.ok ? parsed.key : entry
  if (Object.prototype.hasOwnProperty.call(byKey, key)) {
    var bucket = asList(byKey[key])
    if (bucket.length > 0) {
      // `currentChannelIndex` is a playlist index, or a channel id: under
      // `channelOrder: number` the caller's array is reordered and an index
      // no longer names the cursor's row, so the id form is the one the
      // guide uses (1.4 `ids`).
      var pick = 0
      var byId = typeof currentChannelIndex === "string" && currentChannelIndex !== ""
      var current = byId ? -1 : Math.floor(Number(currentChannelIndex))
      if (bucket.length > 1 && (byId || isFinite(current))) {
        for (var b = 0; b < bucket.length; b++) {
          var same = byId ? chnoIdAt(idx, bucket[b]) === currentChannelIndex : bucket[b] === current
          if (same) { pick = (b + 1) % bucket.length; break }
        }
      }
      return { kind: "exact", channelIndex: bucket[pick], key: key, label: key, matches: bucket.length, ordinal: pick + 1 }
    }
  }

  var labels = asList(idx.labels)
  var order = asList(idx.order)
  for (var i = 0; i < labels.length; i++) {
    if (str(labels[i]).indexOf(entry) !== 0) continue
    var label = str(labels[i])
    var hits = Object.prototype.hasOwnProperty.call(byKey, label) ? asList(byKey[label]) : []
    var at = order[i]
    var ordinal = 1
    for (var h = 0; h < hits.length; h++) if (hits[h] === at) { ordinal = h + 1; break }
    return { kind: "prefix", channelIndex: at, key: label, label: label, matches: hits.length > 0 ? hits.length : 1, ordinal: ordinal }
  }
  return { kind: "none", channelIndex: -1, key: "", label: "", matches: 0, ordinal: 0 }
}

// M2-03 2.5, second commit trigger: an exact match that no longer label
// extends commits on the last digit, which is what makes a 3-digit plan feel
// instant ("199" in a 1..200 list). Not in the section 9.1 table; see the
// lane A report, request 3.
function chnoUnambiguous(index, buffer) {
  var hit = resolveChno(index, buffer, -1)
  if (hit.kind !== "exact") return false
  var labels = asList((index || {}).labels)
  for (var i = 0; i < labels.length; i++) {
    var label = str(labels[i])
    if (label.length > hit.key.length && label.indexOf(hit.key) === 0) return false
  }
  return true
}

// M2-03 3.2, for the IPC verb. resolveChno with no cycling: a script asking
// for 12 must get the same channel every time. `channels` must be the array
// the index was built from, because byKey holds playlist indices.
function channelByNumber(channels, index, text) {
  var parsed = parseChno(text)
  if (!parsed.ok) return null
  var hit = resolveChno(index, parsed.key, -1)
  if (hit.kind === "none") return null
  var list = asList(channels)
  // By id first, so the answer is the same whether the caller holds the
  // playlist-order array or the number-ordered one (5.2). The positional
  // fallback keeps an index built without ids working.
  var id = chnoIdAt(index, hit.channelIndex)
  if (id !== "") {
    for (var i = 0; i < list.length; i++) if (list[i] && channelId(list[i]) === id) return list[i]
    return null
  }
  if (hit.channelIndex < 0 || hit.channelIndex >= list.length) return null
  return list[hit.channelIndex] || null
}

// M2-03 7.1 / CN3. Never an error and never a warning: an unreadable value
// silently means the safe default, because this setting reorders the whole
// guide and a typo must not be able to do that.
function channelOrderOf(value) {
  return str(value).replace(/^\s+|\s+$/g, "").toLowerCase() === "number" ? "number" : "playlist"
}

// M2-03 5.2. An O(n) gather, never a second sort: chnoIndex.order is already
// the numbered channels in (chnoSort, playlist index) order. Unnumbered
// channels always come last, never interleaved and never treated as 0.
// Identity (the same array, no copy) for the default, so the shipped path
// costs nothing.
function orderChannels(channels, order, index) {
  if (channelOrderOf(order) !== "number") return channels
  var idx = index || {}
  if (idx.hasNumbers !== true) return channels
  var list = asList(channels)
  var seq = asList(idx.order)
  var out = []
  var taken = {}
  for (var i = 0; i < seq.length; i++) {
    var at = Math.floor(Number(seq[i]))
    if (!(at >= 0 && at < list.length) || taken[at] === true) continue
    taken[at] = true
    out.push(list[at])
  }
  for (var j = 0; j < list.length; j++) if (taken[j] !== true) out.push(list[j])
  return out
}

// M2-03 2.8 / CN5. The guide opens in search mode, so without the all-digit
// tier the feature is invisible from the default mode.
var NUMERIC_QUERY_RE = /^[0-9]{1,5}([.,][0-9]{1,3})?$/

function isNumericQuery(text) {
  return NUMERIC_QUERY_RE.test(str(text).replace(/^\s+|\s+$/g, ""))
}

// M2-03 2.9: which keys the entry buffer owns, so the guide's textKey
// handler can return early and let handleSharedKey extend the buffer
// instead of committing it.
function isNumberEntryKey(text) {
  var t = str(text)
  if (t.length !== 1) return false
  if (t === CHNO_ENTRY_SEP || t === ",") return true
  return isAsciiDigit(t.charCodeAt(0))
}

// ---- the entry buffer (M2-03 2.3 / 2.4), a plain reducer trio
//
// `scopeId`, `query` and `cursorIndex` are the snapshot taken when the
// buffer went from empty to one character; they are what Esc restores, and
// what Backspace on the last character restores (2.6).
//
// `cursorId` is the same snapshot's cursor as an ID rather than a row number.
// It is what the duplicate cycle of CN9 has to be derived from: every
// intermediate digit MOVES the cursor during the live preview, so by the time
// the last digit lands the live cursor is on whatever the prefix resolved to,
// never on the previous match (D-CHNO-1).
// `resume` is set on exactly one thing: a buffer the AUTO-commit closed
// early. See closeNumberEntry (CN21).
function numberEntry() {
  return { active: false, buffer: "", scopeId: "", query: "", cursorIndex: 0, cursorId: "", resume: false }
}

function normalizeNumberEntry(entry) {
  var e = entry && typeof entry === "object" ? entry : {}
  var at = Math.floor(Number(e.cursorIndex))
  return {
    active: e.active === true,
    buffer: str(e.buffer),
    scopeId: str(e.scopeId),
    query: str(e.query),
    cursorIndex: isFinite(at) && at > 0 ? at : 0,
    cursorId: str(e.cursorId),
    resume: e.resume === true
  }
}

// `changed` is false when the key was refused, and the caller must NOT
// restart the commit timer then: a buffer already at the cap is as long as
// any channel number can be, so restarting would hold entry open for a key
// that did nothing.
function pushNumberKey(entry, text, ctx) {
  var cur = normalizeNumberEntry(entry)
  var t = str(text)
  if (!isNumberEntryKey(t)) return { entry: cur, changed: false, resumed: false }
  if (cur.buffer.length >= MAX_CHNO_LABEL) return { entry: cur, changed: false, resumed: false }
  var buffer = cur.buffer
  if (t === CHNO_ENTRY_SEP || t === ",") {
    if (buffer === "" || buffer.indexOf(CHNO_ENTRY_SEP) !== -1) return { entry: cur, changed: false, resumed: false }
    buffer += CHNO_ENTRY_SEP
  } else {
    buffer += t
  }
  // CN21. A key arriving while a buffer is armed continues THAT number
  // instead of starting a new one. The auto-commit decided the number was
  // finished; this key is the user saying it was not, and the buffer it
  // re-opens can only resolve to nothing -- which is the whole point, because
  // nothing is what the user typed and nothing is what must be reported.
  var resumed = !cur.active && cur.resume === true && cur.buffer !== ""
  if (cur.active || resumed) {
    return {
      entry: { active: true, buffer: buffer, scopeId: cur.scopeId, query: cur.query, cursorIndex: cur.cursorIndex, cursorId: cur.cursorId, resume: false },
      changed: true,
      resumed: resumed
    }
  }
  var c = ctx && typeof ctx === "object" ? ctx : {}
  var at = Math.floor(Number(c.cursorIndex))
  return {
    entry: {
      active: true,
      buffer: buffer,
      scopeId: str(c.scopeId),
      query: str(c.query),
      cursorIndex: isFinite(at) && at > 0 ? at : 0,
      cursorId: str(c.cursorId),
      resume: false
    },
    changed: true,
    resumed: false
  }
}

// Backspace. Emptying the buffer deactivates entry but KEEPS the snapshot,
// because that is the same cancel as Esc (2.6) and the caller still has to
// restore scope, query and cursor from it.
function popNumberKey(entry) {
  var cur = normalizeNumberEntry(entry)
  if (!cur.active || cur.buffer === "") return { active: false, buffer: "", scopeId: cur.scopeId, query: cur.query, cursorIndex: cur.cursorIndex, cursorId: cur.cursorId, resume: false }
  var buffer = cur.buffer.substring(0, cur.buffer.length - 1)
  return { active: buffer !== "", buffer: buffer, scopeId: cur.scopeId, query: cur.query, cursorIndex: cur.cursorIndex, cursorId: cur.cursorId, resume: false }
}

// The Esc / Backspace-to-empty close, kept as its own name because the guide
// and both test suites call it that. One implementation, not two.
function cancelNumberEntry(entry) {
  return closeNumberEntry(entry, "cancel")
}

// What the entry becomes when a commit closes it. `reason` is one of "auto"
// (the unambiguous-match commit, which the user did not ask for), "timeout",
// "enter" (Enter or Space), "key" (any key the buffer does not own) or
// "cancel" (Esc, Backspace to empty).
//
// CN21, and the rule the whole defect turns on: THE MACHINE MAY FINISH A
// NUMBER EARLY ONLY IF IT CAN TAKE IT BACK. Every other reason is the user's
// own act and ends the number for good; "auto" is the one the user never
// asked for, so it closes the entry for display and ARMS the buffer for the
// rest of the same digit window (numberEntryMs, the one rule that says which
// digits are one number). A digit arriving inside that window re-opens this
// buffer instead of starting a new entry that would land somewhere of its own
// with no error -- which is exactly how 20509 became "you are now on channel
// 900, and nothing told you" (D-CHNO-2).
//
// Nothing else changes: the commit still fires on the last digit, the cursor
// is already on the target and the footer already names it, so the 93% of
// numbers that commit instantly still do. An armed entry is inactive, so the
// chip is gone and the hints are back exactly as before.
//
// By construction a resumed buffer can only resolve to nothing: "auto" fires
// only when NO label extends the buffer, so no label can extend it with one
// more digit either. The window's cost is therefore bounded and visible - a
// number retyped inside it reads as one longer number and is reported as the
// miss it is, rather than silently tuning somewhere.
function closeNumberEntry(entry, reason) {
  var cur = normalizeNumberEntry(entry)
  if (str(reason) !== "auto" || cur.buffer === "") return numberEntry()
  return {
    active: false,
    buffer: cur.buffer,
    scopeId: cur.scopeId,
    query: cur.query,
    cursorIndex: cur.cursorIndex,
    cursorId: cur.cursorId,
    resume: true
  }
}

// M2-03 2.5 / 2.9. ONE keystroke, every decision it makes, in order. This
// lives here rather than in Guide.qml because the ORDER is the thing both
// D-CHNO-1 and D-CHNO-2 are about, and an order stranded in a QML component
// is an order no test can reach (engineering rule 12 (dev branch)). The guide keeps exactly
// what only it can do: move the cursor, run the timer, draw the transient.
//
// `ctx` is the live guide state a NEW entry snapshots: cursorId, cursorIndex,
// scopeId, query. Returns:
//   changed     false when the key was refused (the cap, a second separator);
//               the caller must not restart the timer for a key that did
//               nothing
//   entry       the entry after this key, including after an auto-commit
//   resolution  what the buffer resolves to, for the live preview
//   commit      null, or the commit this key fired by itself -- the decision
//               only (restore / play / keepOpen / kind / label / matches /
//               ordinal), because the status line needs the name of the row
//               the caller is about to land on, which only the caller knows
//   timer       "restart" or "stop"
function numberKeyStep(entry, index, text, ctx) {
  var c = ctx && typeof ctx === "object" ? ctx : {}
  var result = pushNumberKey(entry, text, c)
  var idle = resolveChno(null, "", -1)
  if (!result.changed) return { changed: false, entry: result.entry, resolution: idle, snapshot: result.entry, commit: null, timer: "none", resumed: false }
  var next = result.entry
  // D-CHNO-1 / CN9: the cycle is resolved against the cursor as it was BEFORE
  // the first digit, never the live one. Every intermediate digit moves the
  // cursor during the preview -- "3" and "30" both resolve to some lower
  // number on the way to "301" -- so a live cursor is on the prefix's target
  // by the time the last digit lands, is never one of the duplicates, and the
  // cycle restarts at ordinal 1 every time. With a multi-digit plan that
  // means an HD twin could not be reached by number at all.
  var hit = resolveChno(index, next.buffer, next.cursorId)
  if (!chnoUnambiguous(index, next.buffer)) return { changed: true, entry: next, resolution: hit, snapshot: next, commit: null, timer: "restart", resumed: result.resumed === true }
  var plan = chnoCommitPlan(hit.kind, chnoCommitLabel(next, hit), "", hit.matches, hit.ordinal, { play: false })
  return {
    changed: true,
    entry: closeNumberEntry(next, "auto"),
    resolution: hit,
    // What a restoring commit restores from: the entry this key closed, snapshot and all.
    snapshot: next,
    resumed: result.resumed === true,
    commit: {
      reason: "auto",
      restore: plan.restore,
      play: plan.play,
      keepOpen: plan.keepOpen,
      kind: str(hit.kind),
      label: chnoCommitLabel(next, hit),
      matches: hit.matches,
      ordinal: hit.ordinal
    },
    // NOT "stop". The digit window that the auto-commit did not end keeps
    // running, and it is what disarms the buffer when it expires (CN21).
    timer: "restart"
  }
}

// Backspace, and what it resolves against. Returns `cancelled` when the
// buffer emptied: that is the same cancel as Esc, and `snapshot` is what the
// caller restores scope, query and cursor from (2.6).
function numberPopStep(entry, index) {
  var next = popNumberKey(entry)
  if (!next.active) return { entry: numberEntry(), resolution: resolveChno(null, "", -1), cancelled: true, snapshot: next, timer: "stop" }
  // The same snapshot cursor the push path resolves against (D-CHNO-1):
  // backspacing to "3" must preview what "3" meant when entry began.
  return { entry: next, resolution: resolveChno(index, next.buffer, next.cursorId), cancelled: false, snapshot: next, timer: "restart" }
}

// The label a commit reports: the resolved one, or the raw buffer when
// nothing resolved -- which is what puts the number the user actually typed
// into "No channel 20509".
function chnoCommitLabel(entry, resolution) {
  var kind = str((resolution || {}).kind)
  if (kind === "none" || kind === "") return normalizeNumberEntry(entry).buffer
  return str((resolution || {}).label)
}

// M2-03 2.5. A commit the caller asked for: the timeout, Enter or Space, or
// any key the buffer does not own. `name` is the row the preview landed on,
// so the status can name it. Returns the plan (including the status line),
// the entry afterwards, and the snapshot a restoring plan restores from.
function numberCommitStep(entry, resolution, name, opts) {
  var o = opts && typeof opts === "object" ? opts : {}
  var cur = normalizeNumberEntry(entry)
  var hit = resolution && typeof resolution === "object" ? resolution : { kind: "none", label: "", matches: 0, ordinal: 0 }
  return {
    plan: chnoCommitPlan(hit.kind, chnoCommitLabel(cur, hit), name, hit.matches, hit.ordinal, o),
    entry: closeNumberEntry(cur, str(o.reason) === "" ? "key" : str(o.reason)),
    snapshot: cur
  }
}

// M2-03 4.2. Style.space units for the row's number column, derived from the
// WHOLE source's widest label so the column does not jump when the scope
// changes. 24 for 1-2 characters, then 8 per character, capped at 56 -- the
// name column loses at most Style.space(56) of a Style.space(960) card.
function chnoColumnUnits(maxLabelLen) {
  var n = Math.floor(Number(maxLabelLen))
  if (!isFinite(n) || n < 1) n = 1
  if (n > MAX_CHNO_LABEL) n = MAX_CHNO_LABEL
  return Math.max(24, Math.min(56, 8 * n + 8))
}

// Qt keyboard modifier bits, as plain integers so this file stays free of
// QML imports (Qt::KeyboardModifier, stable across Qt 5 and 6).
var QT_SHIFT_MODIFIER = 0x02000000
var QT_CONTROL_MODIFIER = 0x04000000
var QT_ALT_MODIFIER = 0x08000000
var QT_META_MODIFIER = 0x10000000
var QT_KEYPAD_MODIFIER = 0x20000000
// M2-03 2.2 and gate A1. The mask deliberately contains Ctrl, Alt and Meta
// and NOT Shift or Keypad, and that omission is the whole gate:
//
//   - on AZERTY (fr) and bepo the top-row digits sit at shift level 2, so a
//     digit arrives with ShiftModifier SET. Rejecting Shift would break
//     numeric zap on every French layout, and no amount of testing on a US
//     keyboard would reveal it.
//   - the numeric keypad sends KP_0..KP_9, whose text is "0".."9", together
//     with KeypadModifier. Rejecting Keypad would break every numpad.
//
// Both were verified against libxkbcommon with real compiled keymaps rather
// than reasoned about; the evidence is in the M2-03 lane A report. Ctrl,
// Alt and Meta stay rejected because those are chords, not digits.
var CHNO_CHORD_MASK = QT_CONTROL_MODIFIER | QT_ALT_MODIFIER | QT_META_MODIFIER

// What a key event should do to the number buffer (2.9). Returns one of
// "backspace", "digit", "noNumbers" or "pass"; "pass" means the guide has
// not handled it and the shipped binding runs.
function numberKeyAction(opts) {
  var o = opts || {}
  var modifiers = Math.floor(Number(o.modifiers))
  if (isFinite(modifiers) && (modifiers & CHNO_CHORD_MASK) !== 0) return "pass"
  if (o.backspace === true) return o.active === true ? "backspace" : "pass"
  if (!isNumberEntryKey(o.text)) return "pass"
  // 1.5: an unnumbered playlist answers with one transient rather than
  // silence, because UX 3.1 advertises these keys.
  if (o.hasNumbers !== true) return "noNumbers"
  return "digit"
}

// M2-03 2.5, what a commit does. The "never play a number that resolved to
// nothing" rule is the one genuinely destructive outcome this feature could
// have, so it is a decision with a name and a test, not a line of QML.
function chnoCommitPlan(kind, label, name, matches, ordinal, opts) {
  var o = opts || {}
  var none = str(kind) === "none" || str(kind) === ""
  return {
    restore: none,
    play: o.play === true && !none,
    keepOpen: o.keepOpen === true,
    status: chnoStatus(kind, label, name, matches, ordinal, true)
  }
}

// M2-03 6.2, the footer's number strings. `label` is the resolved label, or
// the raw buffer when nothing resolved -- that is what puts the number the
// user actually typed into "No channel 205".
//
// `committed` is the sixth argument rather than a separate function because
// live and committed differ in exactly one decision: a live single match
// shows the number alone (the row under the cursor is already the answer),
// a committed one names the channel it landed on.
function chnoStatus(kind, label, name, matches, ordinal, committed) {
  var k = str(kind)
  if (k === "noNumbers") return CHNO_NO_NUMBERS_TEXT
  var text = str(label)
  if (k === "none" || k === "") return committed === true ? "No channel " + text : "Channel " + text + SEP + "no match"
  var m = Math.floor(Number(matches))
  if (!isFinite(m) || m < 1) m = 1
  var out = "Channel " + text
  if ((committed === true || m > 1) && str(name) !== "") out += SEP + str(name)
  if (m > 1) out += " (" + Math.floor(Number(ordinal) || 1) + " of " + m + ")"
  return out
}

// ------------------------------------------------------------ search

function containsAll(text, tokens) {
  for (var i = 0; i < tokens.length; i++) if (text.indexOf(tokens[i]) === -1) return false
  return true
}

// D-SG-1: every token present as a WHOLE WORD, not as a fragment. Tokens
// never contain spaces, so padding both sides is the whole test.
function containsAllWords(text, tokens) {
  var padded = " " + str(text) + " "
  for (var i = 0; i < tokens.length; i++) {
    if (padded.indexOf(" " + tokens[i] + " ") === -1) return false
  }
  return true
}

// Ranking tiers (R4 / UX 2.5). -1 no match; 0 name starts with the query;
// 1 a word in the name starts with the query; 2 name contains every term;
// 3 only the group carries every term, AS WHOLE WORDS. Every term must occur
// in the search key (AND semantics).
//
// D-SG-1. Tier 3 used to accept any substring of the search key, which is
// name + " " + group. On a one-group list every key therefore ends in the same
// words, so every FRAGMENT of the group name matched every channel: on the
// 3,335-channel US list `st`, `sta`, `ted` and 22 other queries each reported
// 3,335 matches against as few as 4 real ones, paged 1,533 junk rows into the
// first 200 and fired "keep typing" when every genuine match already fitted.
// Requiring whole words takes that list from 25 polluted queries to 0 and a
// multi-group list from 36 to 2, while keeping the tier itself, which is the
// only route to 1,000 event channels and 691 of 833 sports channels and so
// earns its place on data.
//
// Testing the WHOLE key for the whole word is deliberate, and is the same test
// as inspecting the group half: a token that is not a substring of the name
// cannot be a whole word of it, and a whole-word match cannot straddle the
// name/group junction because tokens contain no spaces. Confirmed over
// 78,248,154 rank decisions with zero disagreements. The half-splitting helper
// this replaces assumed the cached key is name-prefixed and silently dropped
// every group match where it is not.
function matchRank(key, tokens, nameKey) {
  var text = str(key)
  if (tokens.length === 0) return 2
  if (!containsAll(text, tokens)) return -1
  var phrase = tokens.join(" ")
  var name = typeof nameKey === "string" ? nameKey : text
  if (name.indexOf(phrase) === 0) return 0
  if ((" " + name).indexOf(" " + phrase) !== -1) return 1
  if (containsAll(name, tokens)) return 2
  if (containsAllWords(text, tokens)) return 3
  return -1
}

// D-SG-1 follow-through, PO ruling SG1. Requiring whole words removes the lie
// of "3,335 matches" but it creates a dead zone on the way to the group's own
// name: on the one-group US list `unit` and `unite` now match nothing, while
// every row on screen prints "United States". A bare "No matches" there is a
// worse lie than the wrong number it replaced, because the user can see the
// words they typed. So the guide says what is actually true: nothing is NAMED
// that, and the group they are heading for is one keystroke further on.
//
// Returns the group name worth naming, or "" when there is nothing useful to
// say. Earlier tokens must be whole words of the group; the LAST token must be
// a strict prefix of one of its words, which is exactly "typing toward it".
// Called only when a query matched nothing, so it never runs on a keystroke
// that produced rows.
// SG1 / D-SG-2. The names the empty-state hint may offer: the sole group off
// the axis first (a one-group list publishes no group ENTRIES, because
// scopeSurface only emits them when the axis narrows, and that is precisely
// the list D-SG-1 bites on), then every group entry in order. Guide.qml
// rebuildGroups and the qa-sg1 fixture (dev branch)/verify.js both CALL this; until
// D-SG-2 the fixture carried a copy of the loop and nothing kept them in step.
function groupNamesForHint(surface) {
  var s = surface && typeof surface === "object" ? surface : {}
  var axis = s.axis && typeof s.axis === "object" ? s.axis : {}
  var entries = asList(s.entries)
  var names = []
  if (str(axis.soleGroup) !== "") names.push(str(axis.soleGroup))
  for (var i = 0; i < entries.length; i++) {
    if (entries[i] && entries[i].kind === "group") names.push(str(entries[i].label))
  }
  return names
}
function groupWordHint(query, groupNames) {
  var tokens = tokenize(query)
  if (tokens.length === 0) return ""
  var names = asList(groupNames)
  for (var i = 0; i < names.length; i++) {
    var raw = str(names[i])
    if (raw === "") continue
    var words = normalizeText(raw).split(" ")
    var ok = true
    for (var t = 0; t < tokens.length && ok; t++) {
      var wantPrefix = t === tokens.length - 1
      var hit = false
      for (var w = 0; w < words.length; w++) {
        if (wantPrefix) {
          if (words[w].length > tokens[t].length && words[w].indexOf(tokens[t]) === 0) { hit = true; break }
        } else if (words[w] === tokens[t]) { hit = true; break }
      }
      ok = hit
    }
    if (ok) return raw
  }
  return ""
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
//
// M2-03 2.8 / CN5: with `chnoIndex` supplied and an all-digit query, the
// exact number match is floated to the head of `rows`. This is a head
// insertion AFTER the buckets are joined, not a fifth tier: the four ranking
// tiers of R4, the bucket arithmetic, `total` and `truncated` are untouched.
function filterChannels(channels, query, limit, favorites, chnoIndex) {
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
  rows = floatChnoMatch(rows, list, query, chnoIndex, max)
  return { rows: rows, total: total, truncated: total > max }
}

// The head insertion of 2.8, kept out of filterChannels' loop so the shipped
// 4-argument call runs byte-identical code. The channel is de-duplicated
// when the name ranker already produced it, and the R3 cap still holds: a
// channel the ranker did NOT produce displaces the last row rather than
// making the list one longer than the cap says it is.
//
// The match is found by scanning the SCOPE array, not through
// `chnoIndex.byKey`: byKey holds playlist indices and `channels` here is
// whatever channelsForScope returned, which for a group or for Favorites is
// a different array with different indices. Searching inside `UK | SPORTS`
// must float that group's channel 101, not the playlist's 101st row.
// `chnoIndex` still gates the feature, so a 4-argument call is unchanged.
function floatChnoMatch(rows, channels, query, chnoIndex, max) {
  if (!chnoIndex || chnoIndex.hasNumbers !== true || !isNumericQuery(query)) return rows
  var key = chnoEntryKey(str(query).replace(/^\s+|\s+$/g, ""))
  var parsed = parseChno(key)
  if (parsed.ok) key = parsed.key
  if (key === "") return rows
  var channel = null
  for (var i = 0; i < channels.length; i++) {
    if (channels[i] && chnoOf(channels[i]).key === key) { channel = channels[i]; break }
  }
  if (channel === null) return rows
  var out = [channel]
  for (var r = 0; r < rows.length && out.length < Math.max(1, max); r++) {
    if (rows[r] !== channel) out.push(rows[r])
  }
  return out
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

// D-SAVE-2: the COUNT is the length of the ROWS, by calling the same function.
//
// This counted `st.favorites` alone, while channelsForScope returns the stars
// PLUS every channel a saved search matched. So the scope ring read
// "Favorites 0" on a scope holding three channels -- a scope the user has no
// reason to open, because the label says there is nothing in it.
//
// Found by a live pass and not by the suite: rows and count were each tested,
// and nothing compared them. That is the third time today one divergence has
// been fixed by making two things one call instead of two implementations.
function countFavorites(list, st) {
  return channelsForScope(list, SCOPE_FAVORITES, st).length
}

function countRecents(list, st) {
  var index = indexById(list)
  var n = 0
  for (var r = 0; r < st.recents.length; r++) if (st.recents[r] && index[st.recents[r].id]) n++
  return n
}

// The group column and the one fact that decides its shape, in a single pass
// (M2-09 D1). `axis` is { count, narrows, soleGroup }:
//
//   narrows === (count >= 2)
//
// which is exactly "choosing a group narrows the list" (GS3), because
// `groupChannels` never emits an empty group: with one group that group holds
// every channel and `channelsForScope(ch, "g:<it>")` is element-for-element
// `channelsForScope(ch, "all")`, so the entry lies about being a step.
//
// One function, not two, because `groupChannels` is the most expensive thing
// on the guide's open path (node median: 0.7 ms at 3,335, 3.7 ms at 11,039,
// 17.7 ms at MAX_CHANNELS) and asking "how many groups" in a second pass
// would pay it twice. `Guide.qml`'s `rebuildGroups()` guards on `groupsDirty`,
// so this runs once per channel-set change and never on a keystroke.
function scopeSurface(channels, state) {
  var list = asList(channels)
  var st = state || emptyState()
  var out = []
  var recents = countRecents(list, st)
  if (recents > 0) out.push({ id: SCOPE_RECENT, label: RECENT_GROUP, kind: "recent", count: recents })
  out.push({ id: SCOPE_FAVORITES, label: FAVORITES_GROUP, kind: "favorites", count: countFavorites(list, st) })
  out.push({ id: SCOPE_ALL, label: "All", kind: "all", count: list.length })
  var groups = groupChannels(list)
  var narrows = groups.length >= 2
  var axis = { count: groups.length, narrows: narrows, soleGroup: groups.length === 1 ? groups[0].name : "" }
  if (narrows) {
    out.push({ id: "", label: "GROUPS", kind: "header", count: 0 })
    for (var i = 0; i < groups.length; i++) {
      out.push({ id: groupScopeId(groups[i].name), label: groups[i].name, kind: "group", count: groups[i].count })
    }
  }
  return { entries: out, axis: axis }
}

// Group column entries (UX 2.2): Recent (hidden while empty), Favorites
// (always), All, then a "GROUPS" header and one entry per playlist group --
// the last two only when a group is a narrowing step (GS3, above).
function scopeEntries(channels, state) {
  return scopeSurface(channels, state).entries
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
    // Saved searches land HERE rather than in a fifth scope. Favourites is
    // already in scopeSurface, launchScope and the zap ring, so none of the
    // three paths that fail silently on an unknown scope id is touched.
    //
    // Explicitly starred channels keep their exact order and come first: they
    // are the most deliberate thing the user did, and this must be
    // element-for-element what it was when nothing is saved. The saved rows
    // follow in playlist order, de-duplicated against the stars.
    var saved = savedSearchChannels(list, st.savedSearches)
    if (saved.length > 0) {
      var starred = {}
      for (i = 0; i < out.length; i++) starred[channelId(out[i])] = true
      for (i = 0; i < saved.length; i++) if (!starred[channelId(saved[i])]) out.push(saved[i])
    }
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

// M2-09 D2. A deep link, an IPC payload or a remembered scope naming the sole
// group of a one-group playlist asks for a list that still exists -- every
// channel -- but the entry is no longer in the column, so `fallbackScope`
// would treat it as vanished and send a user with one favourite to a one-row
// Favorites when they asked for three thousand. Answer All in exactly that
// case; defer to `fallbackScope` unchanged in every other.
function requestedScope(entries, scopeId, axis) {
  var id = str(scopeId) || SCOPE_ALL
  var a = axis || {}
  if (isGroupScope(id) && a.narrows === false && str(a.soleGroup) !== "" && scopeName(id) === str(a.soleGroup)) return SCOPE_ALL
  return fallbackScope(entries, id)
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

// M2-09 D5, the fold affordance. `ListView.Contain` alone parks the cursor
// row flush with the viewport edge, hiding the neighbour entirely and losing
// any sign that more exists -- the defect Omarchy's own picker names in the
// comment above `Menu.qml:640` and repairs there, and which this guide has in
// two places (`scrollToCursor` and the `Contain` branch of `positionColumn`).
//
// This is that algorithm as arithmetic rather than as fifteen copied lines of
// QML: the copy would be exactly the stranded interface logic the engineering rules (dev branch)
// 12 forbids, and as a function it is node-testable as data.
//
// `peek` is the whole reach the next row keeps -- the caller adds its list
// spacing to the visible sliver, as Menu.qml does. Returns the new contentY,
// clamped to the flickable's own bounds; an unmovable view returns what it
// was given, so the call site can assign unconditionally.
function revealOffset(opts) {
  var o = opts || {}
  var count = Math.floor(Number(o.count) || 0)
  var index = Math.floor(Number(o.index) || 0)
  var contentY = Number(o.contentY) || 0
  if (count <= 0 || index < 0 || index >= count) return contentY
  var height = Number(o.viewportHeight) || 0
  var originY = Number(o.originY) || 0
  var contentHeight = Number(o.contentHeight) || 0
  var itemY = Number(o.itemY) || 0
  var itemHeight = Number(o.itemHeight) || 0
  var reach = Number(o.peek) || 0
  if (index < count - 1) {
    var maxY = Math.max(originY, originY + contentHeight - height)
    var overhang = itemY + itemHeight + reach - (contentY + height)
    if (overhang > 0) contentY = Math.min(contentY + overhang, maxY)
  }
  if (index > 0) {
    var underhang = contentY - (itemY - reach)
    if (underhang > 0) contentY = Math.max(contentY - underhang, originY)
  }
  return contentY
}

// Header scope label (UX 6.1, amended by M2-09 D5 / GS4). When the list is
// longer than the viewport -- the scrollbar condition, which is exactly when
// the edge scrims are live -- the count becomes the cursor's position and the
// noun goes away, because the noun is what tells you which form you are
// reading. The total stays in the footer counts line, which already carries
// it, so the position costs nothing and removes a duplication.
//
//   no query, fits      Favorites - 6 channels
//   no query, overflows All - 1,204 of 3,335
//   query, fits         in All - 8 matches
//   query, overflows    in All - 14 of 200
//
// `position` is { index, rows, overflows }: `index` the 0-based cursor row,
// `rows` what the list actually holds (under a query that is the capped 200,
// which is what the header can honestly count against; the true match total
// stays in the footer). Absent or not overflowing gives the shipped strings
// byte for byte, so the eight existing callers and their tests are unmoved.
function scopeLabel(scopeId, query, count, position) {
  var name = scopeName(effectiveScope(scopeId, query))
  var n = Number(count) || 0
  var searching = tokenize(query).length > 0
  var pos = position || {}
  if (pos.overflows === true) {
    var rows = Number(pos.rows) || 0
    var at = Math.max(0, Math.min(Math.floor(Number(pos.index) || 0), rows > 0 ? rows - 1 : 0))
    var here = formatCount(at + 1) + " of " + formatCount(rows)
    return (searching ? "in " + name : name) + SEP + here
  }
  if (searching) return "in " + name + SEP + formatCount(n) + (n === 1 ? " match" : " matches")
  return name + SEP + pluralChannels(n)
}

// ------------------------------------------------------------ guide state machine

// Pure reducer for the keyboard modes (UX 3, R1; UX-SOURCES 1.9). Guide.qml
// keeps one object and replaces it on every transition so bindings notice.
// `search` and `list` are the shipped guide modes; `sources`, `sourceEdit`,
// `sourceXtream` and `confirmRemove` are the Sources screens. `returnMode`
// remembers where Sources was opened from, `form` holds the open form
// (section "sources" below), `sourceCursor` is the Sources list cursor.
var GUIDE_MODES = ["search", "list", "sources", "sourceEdit", "sourceXtream", "confirmRemove", "confirmLogos"]

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
  if (cur.mode === "confirmRemove" || cur.mode === "confirmLogos") { out.state = withMode(cur, "sources"); return out }
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
  return zapStep(list, currentId, delta, null).channel
}

// The zap walk, with the dead ones stepped over.
//
// One wheel flick calls zap up to three times (BarWidget handleWheel), and on
// a list where roughly one in eight channels is dead that flick can hand the
// user two black screens and two failure toasts. Stepping past a channel
// already KNOWN to be dead is the correctness half of the failure memory:
// there is no point tuning to something we watched fail an hour ago.
//
// Three rules, and each one is a refusal of an obvious mistake:
//
// 1. BOUNDED. At most `max` channels are skipped. A 14-day mark on a mostly
//    dead group would otherwise make that group unreachable by wheel for a
//    fortnight, which is a worse failure than the one being avoided.
// 2. NEVER EMPTY-HANDED. If every candidate is marked, the immediate
//    neighbour is returned anyway. Zap must always move.
// 3. IT REPORTS. `skipped` is returned so the caller can say so. Silently
//    walking past rows the user can see would be the guide lying about
//    state, which UX principle 4 forbids -- the point is to save a keypress,
//    not to hide the list.
//
// `failed` is the { id: at } map; absent or empty, this is the old behaviour
// exactly, which is also what a fresh source gets on day one.
// Where a channel sits in the rows on screen, or -1. Lifted here rather than
// looped in QML so it is unit-testable (engineering rule 12).
function rowIndexOfId(rows, id) {
  var list = asList(rows)
  var want = str(id)
  if (want === "") return -1
  for (var i = 0; i < list.length; i++) if (channelId(list[i]) === want) return i
  return -1
}

// ---- keep my place (UX.md 1.3: "a failed stream must not cost more than one
// gesture to move past", and failure "must not clear the user's place in the
// list"). Both were written at M0 and neither was implemented: `open()`
// rebuilds from `initialScope` every time, so a failed play cost the query,
// the scope AND the cursor. With no favourites that lands the user on All,
// row 0, empty search, in a 1,462-row list.
//
// The restore is deliberately NARROW. It applies only when the guide was
// closed by PLAYING something and that something then failed. A normal reopen
// -- hotkey, bar click, an hour later -- still starts fresh, because coming
// back to a stale search you have finished with is its own annoyance and the
// product's promise is "open, three keystrokes, watching".
function placeToRestore(mark, failedId, nowSec) {
  var m = mark && typeof mark === "object" ? mark : null
  if (!m) return null
  if (str(m.id) === "" || str(m.id) !== str(failedId)) return null
  // A mark older than the window is stale: the user has moved on, and
  // restoring a search from yesterday would be a surprise, not a courtesy.
  var at = Math.floor(Number(m.at) || 0)
  var now = Math.floor(Number(nowSec) || 0)
  if (at > 0 && now > 0 && now - at > PLACE_TTL_SEC) return null
  return { query: str(m.query), scopeId: str(m.scopeId), id: str(m.id) }
}

// Long enough to cover a first-load failure and the user's reaction, short
// enough that it is never a surprise.
var PLACE_TTL_SEC = 180

function placeMark(guideState, channelId, nowSec) {
  var g = guideState || {}
  return { query: str(g.query), scopeId: str(g.scopeId), id: str(channelId),
           at: Math.floor(Number(nowSec) || 0) }
}

// What the guide says after a zap stepped over something. Empty when nothing
// was skipped, so the ordinary zap stays silent.
function zapSkipNotice(skipped) {
  var n = Math.max(0, Math.floor(Number(skipped) || 0))
  if (n <= 0) return ""
  return "Skipped " + formatCount(n) + (n === 1 ? " dead channel" : " dead channels")
}

function zapStep(list, currentId, delta, failed, maxSkip) {
  var rows = asList(list)
  if (rows.length === 0) return { channel: null, skipped: 0 }
  var step = delta < 0 ? -1 : 1
  var at = -1
  for (var i = 0; i < rows.length; i++) if (channelId(rows[i]) === currentId) { at = i; break }
  if (at === -1) return { channel: rows[0], skipped: 0 }
  var marks = failed && typeof failed === "object" ? failed : {}
  var first = rows[(at + step + rows.length) % rows.length]
  var max = Math.max(0, Math.floor(Number(maxSkip)))
  if (!isFinite(max) || max <= 0) max = ZAP_MAX_SKIP
  var probe = at
  for (var n = 0; n <= max; n++) {
    probe = (probe + step + rows.length) % rows.length
    if (probe === at) break
    var candidate = rows[probe]
    if (marks[channelId(candidate)] === undefined) return { channel: candidate, skipped: n }
  }
  // Everything in reach is marked: go to the neighbour anyway (rule 2).
  return { channel: first, skipped: 0 }
}

var ZAP_MAX_SKIP = 20

// ------------------------------------------------------------ state

// ---- saved searches (roadmap phase 4) --------------------------------------
//
// A saved search is a QUERY, not a list of ids, and the reason is measured: on
// the provider list 1 of 3,335 channel ids survives a password rotation and
// 3,335 of 3,335 names do. A term also picks up channels the provider adds
// later and works across bouquets that spell the same brand differently.
//
// The saved rows land in FAVOURITES rather than in a fifth scope. Favourites is
// already in scopeSurface, launchScope and the zap ring, so none of the three
// silent-failure paths a new scope id would touch is touched here.
//
// Bounds exist because the whole performance argument for this feature was
// stated "for ten terms", and that bound did not exist in the design. These
// follow the MAX_SOURCES 50 / MAX_LABEL 64 precedent.
var MAX_SAVED_SEARCHES = 20
var MAX_SAVED_TERMS = 8
var MAX_SAVED_QUERY = 64

// The membership predicate, deliberately NOT filterChannels.
//
// filterChannels is the RANKED, CAPPED display function: `pluto` returns rows
// 200 against total 2227, so a saved set built on it would have rows and a
// count that disagree by an order of magnitude. Worse, its slot arithmetic is
// `rank * 2 + (fav ? 0 : 1)`, so a saved set would silently REORDER when you
// favourited something inside it -- and these rows land in Favourites, so that
// is not hypothetical.
//
// It shares matchRank, so a saved search contains exactly the rows the search
// showed. What it does not share is the cap and the ordering.
function savedSearchTerms(query) {
  var toks = tokenize(str(query).slice(0, MAX_SAVED_QUERY))
  return toks.slice(0, MAX_SAVED_TERMS)
}

function savedSearchHit(channel, tokens) {
  if (!channel || tokens.length === 0) return false
  var key = typeof channel.searchKey === "string" ? channel.searchKey : searchKey(channel.name, channel.group)
  var nameKey = typeof channel.nameKey === "string" ? channel.nameKey : normalizeText(channel.name)
  return matchRank(key, tokens, nameKey) >= 0
}

// How many rows the terms AS TYPED would save. Shown in the confirmation so a
// bad term is visible in the moment: `baton rouge` shows 4 and `no tv` shows 75,
// because `tv` matches nearly everything.
function savedSearchCount(channels, query) {
  var tokens = savedSearchTerms(query)
  if (tokens.length === 0) return 0
  // Counted the way the rows are COLLECTED, by unique id: a playlist that
  // lists the same channel twice would otherwise have the confirmation promise
  // one more row than Favourites actually gains. Found by putting a real
  // duplicate in the fixture.
  var list = asList(channels)
  var seen = {}
  var n = 0
  for (var i = 0; i < list.length; i++) {
    if (!savedSearchHit(list[i], tokens)) continue
    var id = channelId(list[i])
    if (seen[id]) continue
    seen[id] = true
    n++
  }
  return n
}

// Every channel matched by ANY saved search, de-duplicated, in PLAYLIST ORDER.
//
// Playlist order and not match order: the rows join the user's starred
// channels in Favourites, and a list whose order depends on which saved search
// happened to match first would reshuffle whenever one was added or removed.
// First occurrence wins.
function savedSearchChannels(channels, saved) {
  var list = asList(channels)
  var terms = []
  var records = asList(saved)
  for (var s = 0; s < records.length && terms.length < MAX_SAVED_SEARCHES; s++) {
    var t = savedSearchTerms(records[s] && records[s].query)
    if (t.length > 0) terms.push(t)
  }
  if (terms.length === 0) return []
  var out = []
  var seen = {}
  for (var i = 0; i < list.length; i++) {
    var channel = list[i]
    if (!channel) continue
    for (var k = 0; k < terms.length; k++) {
      if (!savedSearchHit(channel, terms[k])) continue
      var id = channelId(channel)
      if (seen[id]) break
      seen[id] = true
      out.push(channel)
      break
    }
  }
  return out
}

// What the confirmation says. Composed here rather than in QML so a test can
// call it (rule 12), and so the COUNT is never optional: the whole reason this
// feature shows a number is that a term can quietly save far more than the
// user meant.
function savedSearchNotice(result, query, count) {
  var r = result || {}
  var terms = savedSearchTerms(query)
  var shown = terms.join(" ")
  if (!r.added) {
    if (r.reason === "duplicate") return "Already saved: " + shown
    if (r.reason === "full") return "Saved searches full (" + MAX_SAVED_SEARCHES + ")"
    return "Nothing to save"
  }
  return "Saved " + shown + SEP + formatCount(count) + (Number(count) === 1 ? " channel" : " channels")
}

// Why is this channel in Favourites? Returns "star", the saved search that put
// it there, or null.
//
// This exists because 0.7.6 shipped saved rows into Favourites with no way to
// take them out. `x` there calls the favourite toggle, and a saved row is not
// starred -- so the one key that looks like "remove this" ADDED a star, and
// pressing it again removed the star and left the row, because the search still
// matched. A dead end in both directions (D-SAVE-1).
function favoriteOrigin(state, channel) {
  var st = state || emptyState()
  if (!channel) return null
  if (isFavorite(st, channelId(channel))) return { kind: "star", query: "" }
  var saved = asList(st.savedSearches)
  for (var i = 0; i < saved.length; i++) {
    var terms = savedSearchTerms(saved[i] && saved[i].query)
    if (terms.length > 0 && savedSearchHit(channel, terms)) {
      return { kind: "saved", query: str(saved[i].query) }
    }
  }
  return null
}

// What `x` should say it did. Starred first, deliberately: a row that is BOTH
// starred and saved loses the star first, because the star is the narrower and
// more deliberate of the two and removing the search would take other rows with
// it. A second `x` then removes the search.
function favoriteRemovalNotice(origin, count) {
  var o = origin || {}
  if (o.kind === "star") return "Removed from Favorites"
  if (o.kind === "saved") {
    return "Forgot " + savedSearchTerms(o.query).join(" ") + SEP +
      formatCount(count) + (Number(count) === 1 ? " channel" : " channels")
  }
  return ""
}

// How many Favourites rows come from saved searches rather than stars. Shown in
// the footer so the list is explicable: otherwise Favourites fills with
// channels the user never starred and nothing says why.
function savedSearchFooter(state, channels) {
  var st = state || emptyState()
  var saved = asList(st.savedSearches)
  if (saved.length === 0) return ""
  var rows = savedSearchChannels(asList(channels), saved).length
  return formatCount(saved.length) + (saved.length === 1 ? " saved search" : " saved searches") +
    SEP + formatCount(rows) + (rows === 1 ? " channel" : " channels")
}

// Add a saved search, or report why not. Pure: returns the next state and a
// verdict, never mutates. The verdict is what the confirmation says, so a
// refusal is visible in the moment rather than silently doing nothing.
function withSavedSearch(state, query, at) {
  var st = state || emptyState()
  var terms = savedSearchTerms(query)
  var list = asList(st.savedSearches).slice()
  if (terms.length === 0) return { state: st, added: false, reason: "empty" }
  var sig = terms.join(" ")
  for (var i = 0; i < list.length; i++) {
    if (savedSearchTerms(list[i] && list[i].query).join(" ") === sig) {
      return { state: st, added: false, reason: "duplicate" }
    }
  }
  if (list.length >= MAX_SAVED_SEARCHES) return { state: st, added: false, reason: "full" }
  var rec = savedSearchRecord({ query: query, at: at })
  if (!rec) return { state: st, added: false, reason: "empty" }
  list.push(rec)
  return { state: cloneState(st, { savedSearches: list }), added: true, reason: "" }
}

// Remove one, matched on the FOLDED terms so the caller does not have to know
// how the stored string was spelled.
function withoutSavedSearch(state, query) {
  var st = state || emptyState()
  var sig = savedSearchTerms(query).join(" ")
  if (sig === "") return st
  var kept = asList(st.savedSearches).filter(function (r) {
    return savedSearchTerms(r && r.query).join(" ") !== sig
  })
  return cloneState(st, { savedSearches: kept })
}

// One stored record. A query that tokenizes to nothing is not a saved search.
function savedSearchRecord(entry) {
  if (!entry || typeof entry !== "object") return null
  var query = str(entry.query).slice(0, MAX_SAVED_QUERY)
  if (savedSearchTerms(query).length === 0) return null
  return { query: query, at: Math.trunc(Number(entry.at)) || 0 }
}

function emptyState() {
  return { version: STATE_VERSION, cacheLayout: 0, favorites: [], recents: [], lastPlayed: null, session: null, sources: [], savedSearches: [] }
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
    sources: asList(st.sources).slice(),
    // A THIRD whitelist, and it erases exactly like the other two did. This
    // rebuilds the document field by field, so a key it does not name is gone
    // -- and Service.qml clones state to write a source record, which would
    // have wiped every saved search on the next source edit. The roadmap
    // warned about two whitelists; there are three.
    savedSearches: asList(st.savedSearches).slice()
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
  // Saved searches. Additive and optional, on the same precedent as `session`
  // below: both readers whitelist the keys they know, so a file without this
  // reads as [] and an older build drops it rather than failing. De-duplicated
  // on the folded terms, not on the raw string, so `BBC ` and `bbc` are one
  // saved search and not two.
  var saves = asList(parsed.savedSearches)
  var seenTerms = {}
  for (var v = 0; v < saves.length && state.savedSearches.length < MAX_SAVED_SEARCHES; v++) {
    var rec2 = savedSearchRecord(saves[v])
    if (!rec2) continue
    var sig = savedSearchTerms(rec2.query).join(" ")
    if (seenTerms[sig]) continue
    seenTerms[sig] = true
    state.savedSearches.push(rec2)
  }
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
// shell could call the rule to find out (engineering rule 11 (dev branch), 12).

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
// ---- dead-channel memory (PO 2026-09-24, amending R8 / R11 / UX ruling 9)
//
// A failure mark now SURVIVES a restart. Three decisions decide the rest, and
// each of them is the answer to something a design review broke:
//
// 1. IT IS NOT IN state.json. Channel ids are global across sources
//    (ARCHITECTURE-SOURCES D14), so a state-level map would mark a DIFFERENT
//    provider's working channel with a failure earned on this one. And a map
//    keyed by channel id falls inside D-ID-1's id-rotation blast radius --
//    which that defect's row records as excluded precisely BECAUSE this was
//    session-only. Storing it per source keeps that exclusion true, for a
//    better reason: the marks live with the cache whose ids they name.
//
// 2. IT IS AN ARRAY, newest first, not a map. The savedSearches precedent
//    chose an array for deterministic eviction order, and a `{id: at}` object
//    has no iteration contract to evict by across two languages.
//
// 3. THE VALUE IS AN EPOCH, not the "HH:MM" it used to be. A display string is
//    meaningless the day after it is written. Rendering is `failedNoticeAt`,
//    below, which says the clock for today and the date for anything older so
//    the row never implies a week-old observation is current.
//
// A mark is dropped four ways: the channel plays, it ages out, its id leaves
// the playlist, or its source is removed. `prunedFailed` does the middle two;
// the rest is the existing withoutFailed / failedAfterHealthy path.
var MAX_FAILED = 300
var FAILED_TTL_SEC = 14 * 24 * 3600

// Read a failed.json document into the in-memory list. Deliberately takes no
// clock: a parser that ages entries out is clock-dependent, which makes the
// shared fixtures untestable. Aging is `prunedFailed`, at a named call site.
function parseFailed(text) {
  var doc = parseJsonObject(text)
  if (!doc) return []
  return normalizeFailed(doc.failed)
}

function normalizeFailed(list) {
  var rows = asList(list)
  var out = []
  var seen = {}
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i]
    if (!r || typeof r !== "object") continue
    var id = str(r.id)
    var at = Math.floor(Number(r.at))
    if (id === "" || !isFinite(at) || at <= 0) continue
    if (seen[id] === true) continue
    seen[id] = true
    out.push({ id: id, at: at })
    if (out.length >= MAX_FAILED) break
  }
  return out
}

// The two drops that need context: too old, and no longer in the playlist.
//
// `knownIds` is the id set of the CURRENT channels.json. Dropping a mark whose
// channel is gone is what makes this self-healing: an id rotation, a provider
// reshuffle and a removed channel all produce marks that name nothing, and all
// three are cleaned up here rather than by a migration nobody would maintain.
// Passing no set at all skips that half, so a caller without channels loaded
// yet cannot wipe the file.
function prunedFailed(list, nowSec, knownIds) {
  var now = Math.floor(Number(nowSec) || 0)
  var rows = normalizeFailed(list)
  var out = []
  for (var i = 0; i < rows.length; i++) {
    if (now > 0 && rows[i].at < now - FAILED_TTL_SEC) continue
    if (knownIds && knownIds[rows[i].id] !== true) continue
    out.push(rows[i])
  }
  return out
}

// { id: true } for prunedFailed, from whatever channel list the caller holds.
function knownIdSet(channels) {
  var list = asList(channels)
  var out = {}
  for (var i = 0; i < list.length; i++) {
    var id = channelId(list[i])
    if (id !== "") out[id] = true
  }
  return out
}

// The list as the guide wants it: { id: at } for O(1) row lookup. The ROW
// still asks by id, so this is the shape the render path keeps.
function failedIndex(list) {
  var rows = normalizeFailed(list)
  var out = {}
  for (var i = 0; i < rows.length; i++) out[rows[i].id] = rows[i].at
  return out
}

function failedDocument(list) {
  return { version: 1, failed: normalizeFailed(list) }
}

// What the row says. `Failed 21:05` for today, `Failed 8 Sep` for older, and
// the year when it is not this one -- the formatLastUsed idiom, so the guide
// has one voice for "a time in the past".
//
// Never "Dead" or "Broken": the mark is a record of one observation, not a
// claim about the channel now, and a week-old failure said in the present
// tense would be a lie the user cannot check.
function failedWhen(atSec, nowSec) {
  var at = Math.floor(Number(atSec) || 0)
  if (at <= 0) return ""
  var d = new Date(at * 1000)
  var now = Number(nowSec) > 0 ? new Date(Number(nowSec) * 1000) : new Date()
  if (sameDay(d, now)) return formatClock(at)
  var yesterday = new Date(now.getTime())
  yesterday.setDate(yesterday.getDate() - 1)
  if (sameDay(d, yesterday)) return "yesterday"
  var text = d.getDate() + " " + MONTHS[d.getMonth()]
  if (d.getFullYear() !== now.getFullYear()) text += " " + d.getFullYear()
  return text
}

// PO 2026-09-24: the value is an EPOCH now, and it is stored as the NUMBER it
// is. It used to be str()'d, which was right while the value was the display
// string "HH:MM" and is wrong for a stamp -- `failedIndex` produces numbers
// from the file, so a str() here would make the same map hold numbers from
// disk and strings from this turn, and the two would format identically right
// up until something compared them.
function withFailed(failed, id, at) {
  var out = {}
  var src = failed && typeof failed === "object" ? failed : {}
  for (var k in src) out[k] = src[k]
  if (str(id) !== "") out[str(id)] = typeof at === "number" ? at : str(at)
  return out
}

// D-PLY-14. A failure mark says "this channel would not play". A healthy
// player whose OWN STASH says it is playing that channel is proof to the
// contrary, so the mark is dropped.
//
// Without this the mark outlives the failure, because the only other place
// that clears one runs when a play STARTS, not when one succeeds: a transient
// error during first load marked a channel, the stream then recovered, and the
// guide showed a channel the user was watching as "Failed HH:MM - Space to
// retry", with the alert glyph and WITHOUT the playing glyph, because the
// failure state displaces the playing state. Seen on the real display
// 2026-09-22 with mpv reporting h264 and 33.9 s of cache at the time.
//
// Only "agree" clears, and that is deliberately the strictest verdict
// reconcileVerdict gives: the player is up, on our source, and on the exact
// channel the guide names. "unknown" (stopping, nothing playing, or the
// player's record says playing false) and "diverged" both leave the mark
// alone, so a channel that really did fail keeps its mark.
function failedAfterHealthy(failed, verdictState, nowPlaying) {
  var src = failed && typeof failed === "object" ? failed : {}
  if (str(verdictState) !== "agree" || !nowPlaying) return src
  var id = str(nowPlaying.id)
  if (id === "" || src[id] === undefined) return src
  return withoutFailed(src, id)
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

// How a boolean setting is READ (R2), in one place. The host can hand back a
// real boolean, or the string "false" from a hand-edited shell.json, or a
// value that is simply absent -- and the rule has always been "anything but
// false and the string false means on".
//
// It was written out four times: twice here (showChannelName,
// barShowChannelNumber) and twice in BarWidget.qml, which reads its own
// injected entry rather than going through settingsFrom. The four agreed;
// nothing held them there, and M2-03 added the fourth by copying the third.
function boolSetting(value) {
  return value !== false && str(value) !== "false"
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
  // M2-05 section 6: the three PiP keys are read in ONE place
  // (Model.pipOptions), which the service and the guide also call directly,
  // so a clamp can never be written twice and drift (R2, engineering rule 12 (dev branch)).
  var pip = pipOptions(entry)
  return {
    playlistUrl: str(settingOf(entry, "playlistUrl", "")).replace(/^\s+|\s+$/g, ""),
    epgUrl: str(settingOf(entry, "epgUrl", "")).replace(/^\s+|\s+$/g, ""),
    refreshMinutes: clampSetting("refreshMinutes", settingOf(entry, "refreshMinutes", SETTING_RANGES.refreshMinutes.def)),
    mpvArgs: str(settingOf(entry, "mpvArgs", "")),
    showChannelName: boolSetting(settingOf(entry, "showChannelName", true)),
    maxRecents: clampSetting("maxRecents", settingOf(entry, "maxRecents", SETTING_RANGES.maxRecents.def)),
    barLabelMaxWidth: clampSetting("barLabelMaxWidth", settingOf(entry, "barLabelMaxWidth", SETTING_RANGES.barLabelMaxWidth.def)),
    // ---- channel numbers (M2-03 7.1)
    channelOrder: channelOrderOf(settingOf(entry, "channelOrder", "playlist")),
    numberEntryMs: clampSetting("numberEntryMs", settingOf(entry, "numberEntryMs", SETTING_RANGES.numberEntryMs.def)),
    barShowChannelNumber: boolSetting(settingOf(entry, "barShowChannelNumber", true)),
    // ---- logos (M2-04). optInSetting, not boolSetting: see the comment there.
    showLogos: optInSetting(settingOf(entry, "showLogos", false)),
    // ---- picture in picture (M2-05 section 6)
    pipCorner: pip.corner,
    pipSizePercent: pip.sizePercent,
    pipMargin: pip.margin
  }
}

// ------------------------------------------------------------ logos (M2-04)
//
// The ruling is RULING-LOGOS.md (dev branch) and its first line is the whole of it:
// off by default, because turning logos on tells sixty-three third parties
// which channels this user has and hands i.imgur.com alone a request pattern
// covering two thirds of the list. Everything here serves that line.

var LOGO_SCHEMES = ["https"]

// The one setting in this plugin that must FAIL CLOSED, and the reason it does
// not go through boolSetting.
//
// boolSetting is "anything but false and the string false means on", which is
// right for showChannelName: a junk value in a hand-edited shell.json leaves
// the name visible, and the worst case is a label the user did not ask for.
// Applied to this setting the same rule would let `showLogos: 0`,
// `showLogos: "no"` and `showLogos: null` each contact sixty-three hosts,
// because none of them is false or "false". A privacy switch whose unknown
// values mean ON is not off by default; it is off by default only for the
// people whose config file happens to be well formed.
//
// So: only a real true, or the string "true", turns this on. Everything else,
// including absence, is off.
function optInSetting(value) {
  return value === true || str(value) === "true"
}

// Who enabling logos would contact, counted from the cache and contacting
// nothing. The mirror of `logo_survey` in bin/omarchy-iptv; both run
// the shared logo-survey fixture (dev branch) so the two cannot drift, because the
// sentence the user consents to is composed from these numbers and a guide
// that disagrees with the helper is a guide that lies in the consent dialog.
function logoSurvey(channels) {
  var rows = asList(channels)
  var hosts = {}
  var schemes = {}
  var withLogo = 0
  var refused = 0
  for (var i = 0; i < rows.length; i++) {
    var channel = rows[i]
    if (!channel || typeof channel !== "object") continue
    var raw = channel.logo
    if (typeof raw !== "string" || raw === "") continue
    withLogo++
    var parsed = splitLogoUrl(raw)
    schemes[parsed.scheme] = (schemes[parsed.scheme] || 0) + 1
    if (LOGO_SCHEMES.indexOf(parsed.scheme) === -1 || parsed.host === "") {
      // Counted, never contacted. Three ways to land here: a scheme that is
      // not https (rule 3), no host at all, and userinfo -- fetch_logo
      // refuses a URL carrying userinfo rather than stripping it, so a survey
      // that counted one as contactable would promise a fetch that cannot
      // happen AND would print `user:pass@provider.test` into the consent
      // text the user is reading. The credential-sink rule (engineering rule 5): every sink redacts to
      // scheme and host, and the consent dialog is a sink.
      refused++
      continue
    }
    hosts[parsed.host] = (hosts[parsed.host] || 0) + 1
  }
  var names = []
  for (var host in hosts) if (Object.prototype.hasOwnProperty.call(hosts, host)) names.push(host)
  names.sort(function (a, b) {
    if (hosts[b] !== hosts[a]) return hosts[b] - hosts[a]
    return a < b ? -1 : (a > b ? 1 : 0)
  })
  var ordered = []
  var wouldContact = 0
  for (var n = 0; n < names.length; n++) {
    ordered.push({ host: names[n], channels: hosts[names[n]] })
    wouldContact += hosts[names[n]]
  }
  return {
    channels: rows.length,
    withLogo: withLogo,
    wouldContact: wouldContact,
    refused: refused,
    hostCount: ordered.length,
    hosts: ordered,
    schemes: schemes
  }
}

// scheme and host of a logo URL, lowercased, without pulling in a URL parser.
// Deliberately narrow: anything it cannot read confidently comes back with an
// empty host, which logoSurvey counts as refused and logoFile declines to
// name. Being wrong in the direction of "do not fetch this" is free.
function splitLogoUrl(raw) {
  var text = str(raw)
  var mark = text.indexOf("://")
  if (mark <= 0) return { scheme: "", host: "" }
  var scheme = text.substring(0, mark).toLowerCase()
  var rest = text.substring(mark + 3)
  var cut = rest.length
  var stops = ["/", "?", "#"]
  for (var i = 0; i < stops.length; i++) {
    var at = rest.indexOf(stops[i])
    if (at !== -1 && at < cut) cut = at
  }
  return { scheme: scheme, host: logoHost(rest.substring(0, cut)) }
}

// The host a logo URL would disclose to, or "" when it discloses to none.
// The mirror of `logo_host` in bin/omarchy-iptv.
//
// The PORT is not part of the answer: the question the survey exists to
// answer is how many parties learn which channels this user has, and
// `cdn.test` and `cdn.test:8443` are one party. Counting them separately
// inflates the only number in the consent sentence.
//
// Userinfo makes the answer "". fetch_logo refuses such a URL outright, so
// the host is never contacted, and naming it would print the credentials.
function logoHost(netloc) {
  var text = str(netloc).replace(/^\s+|\s+$/g, "").toLowerCase()
  if (text.indexOf("@") !== -1) return ""
  if (text.charAt(0) === "[") {
    var close = text.indexOf("]")
    return close === -1 ? "" : text.substring(0, close + 1)
  }
  var colon = text.indexOf(":")
  return colon === -1 ? text : text.substring(0, colon)
}

// The sentence the user consents to (ruling rule 6). A generic "logos may
// contact third parties" is not informed consent when the real answer is
// countable, and it is countable without making a single request.
//
// The busiest host is named because sixty-three is an abstraction and
// `i.imgur.com` is not: the number says how wide the disclosure is and the
// name says who actually receives most of it.
function logoConsentLines(survey) {
  var s = survey && typeof survey === "object" ? survey : {}
  var hostCount = Math.max(0, Math.floor(Number(s.hostCount) || 0))
  var contact = Math.max(0, Math.floor(Number(s.wouldContact) || 0))
  var withLogoEarly = Math.max(0, Math.floor(Number(s.withLogo) || 0))
  var refusedEarly = Math.max(0, Math.floor(Number(s.refused) || 0))
  if (hostCount === 0 || contact === 0) {
    // D-LOGO-6. These are two different answers and the dialog used to give
    // the first for both. A playlist whose logo URLs are ALL http has
    // withLogo > 0, refused > 0 and hostCount 0 -- every channel offers a
    // logo and the policy is declining every one of them. Telling that user
    // "no channel offers a logo" sends them away believing their provider
    // supplies none.
    if (withLogoEarly > 0) {
      return [formatCount(withLogoEarly) + (withLogoEarly === 1 ? " channel offers a logo" : " channels offer a logo")
              + ", and none of them can be used.",
              "Every one is either not https or has no host, so nothing would be fetched"
              + " and nothing would be contacted.",
              "No credentials are ever sent with a logo request."]
    }
    return ["No channel in this playlist offers a logo.",
            "Turning this on would contact nobody, and change nothing on screen."]
  }
  var top = asList(s.hosts)[0]
  var lead = "Turning logos on will contact " + formatCount(hostCount)
           + (hostCount === 1 ? " host" : " hosts")
  if (top && str(top.host) !== "") {
    lead += ", the busiest being " + str(top.host) + " (" + pluralChannels(top.channels) + ")"
  }
  var withLogo = Math.max(0, Math.floor(Number(s.withLogo) || 0))
  var lines = [lead + ".",
               formatCount(withLogo) + " of "
               + pluralChannels(Math.max(0, Math.floor(Number(s.channels) || 0)))
               + (withLogo === 1 ? " carries" : " carry")
               + " a logo. Each one is fetched once and cached."]
  var refused = Math.max(0, Math.floor(Number(s.refused) || 0))
  if (refused > 0) {
    lines.push(formatCount(refused) + (refused === 1 ? " logo is" : " logos are")
               + " not https and will be skipped.")
  }
  lines.push("No credentials are ever sent with a logo request.")
  return lines
}

// The cached file for a channel's logo, or "" when there is nothing to name.
//
// The name is the fnv1a32 of the URL and nothing else -- no extension. That is
// what lets this be a pure function of the channel and the directory: with an
// extension the guide would have to read an index to learn which one, and that
// index is a JSON parse inside the 150 ms open budget. Qt loads a local image
// by content rather than by name (measured on 6.11.2), so the extension bought
// nothing to begin with.
//
// Returns a path, NOT a url: the caller adds the scheme, because a QML Image
// wants `file://` and a test wants a path it can stat.
function logoFile(channel, logoDir) {
  var dir = str(logoDir)
  if (dir === "" || !channel || typeof channel !== "object") return ""
  var raw = channel.logo
  if (typeof raw !== "string" || raw === "") return ""
  var parsed = splitLogoUrl(raw)
  if (LOGO_SCHEMES.indexOf(parsed.scheme) === -1 || parsed.host === "") return ""
  return dir.replace(/\/+$/, "") + "/" + fnv1a32(raw)
}

// What the row draws in the logo slot. One function so the slot, its width and
// the accessible name cannot disagree about whether there is a picture there.
//
// `kind` is "image" when a file can be named, "blank" when the setting is on
// and this channel simply has none, and "off" when the column is not there at
// all.
function logoSlot(opts) {
  var o = opts || {}
  if (o.enabled !== true) return { kind: "off", path: "" }
  var path = logoFile(o.channel, o.logoDir)
  if (path === "") return { kind: "blank", path: "" }
  // `have` is the set of file names the last fetch reported ON DISK. Pointing
  // a QML Image at a file that is not there is not merely a blank slot: Qt
  // logs "Cannot open" for every attempt, so one dead logo host fills the
  // user's journal every time the row scrolls into view. Seen live before
  // this argument existed.
  //
  // Absent `have` means "do not know yet", and the slot stays blank rather
  // than guessing -- the fetch that populates it runs on every channel load,
  // so this is a few hundred milliseconds after the guide first opens and it
  // costs no requests when the files are already cached.
  if (!o.have || typeof o.have !== "object") return { kind: "blank", path: "" }
  var name = path.substring(path.lastIndexOf("/") + 1)
  return o.have[name] === true ? { kind: "image", path: path } : { kind: "blank", path: "" }
}

// ------------------------------------------------------------ channel wall
//
// M2-13. The wall presents the same rows as a grid of tiles. The arithmetic
// is here rather than in the view because it is pure, fiddly at the edges,
// and a node test can reach it (engineering rule 12 (dev branch)).
//
// COLUMNS ARE CAPPED, NOT DERIVED, and that is the whole design. Hiding the
// group column in the wall frees ~200 px of the 924 px card. Spending it on a
// fifth column costs +40 per cent realised delegates and measured 139 ms
// against a 150 ms budget; spending it on bigger tiles keeps the delegate
// count and the paint time where the list's already are, and takes the tile
// from ~170 px to ~225 px. Bigger is what the corpus needs: a contact sheet
// over the 1,380 real cached logos showed 32 runs of three or more adjacent
// channels sharing one logo file -- the largest 28 consecutive NBC affiliates,
// then Fox 14, PBS 11 -- where the CAPTION is the only thing that tells two
// tiles apart. The wall is navigated by name more often than by picture.
// The key that flips the two views. Modified by necessity: the guide opens in
// search mode, where a bare printable character is query text.
var WALL_KEY = "Ctrl+G"
var WALL_MAX_COLUMNS = 4
// 16:9 for the picture area. The corpus median aspect is 1.98 and the spread
// is 0.31 to 13.62, so no plate shape fits the logos; PreserveAspectFit
// inside a 16:9 plate letterboxes the tall ones and pillarboxes the wide ones
// without cropping either.
var WALL_PLATE_ASPECT = 16 / 9

// The grid's geometry for an available width. Returns zeros for a width that
// cannot hold a tile, so a view bound to this draws nothing rather than
// dividing by zero.
//
// `gridWidth` is returned, and the view MUST be given it, because GridView
// derives its own column count as floor(width / cellWidth) and
// floor(w / floor(w / n)) is not always n -- at w=10, n=4 it is 5. Handing it
// an exact multiple removes the disagreement instead of hoping about it.
function wallGeometry(opts) {
  var o = opts || {}
  var width = Math.floor(Number(o.width) || 0)
  var gap = Math.max(0, Math.floor(Number(o.gap) || 0))
  var caption = Math.max(0, Math.floor(Number(o.caption) || 0))
  var minCell = Math.max(1, Math.floor(Number(o.minCell) || 120))
  var maxColumns = Math.max(1, Math.floor(Number(o.maxColumns) || WALL_MAX_COLUMNS))
  var zero = { columns: 0, cellWidth: 0, cellHeight: 0, tileWidth: 0, plateHeight: 0, gridWidth: 0 }
  if (width < minCell) return zero
  var columns = Math.min(maxColumns, Math.max(1, Math.floor(width / minCell)))
  var cellWidth = Math.floor(width / columns)
  var tileWidth = Math.max(1, cellWidth - gap)
  var plateHeight = Math.max(1, Math.round(tileWidth / WALL_PLATE_ASPECT))
  return {
    columns: columns,
    cellWidth: cellWidth,
    cellHeight: plateHeight + caption + gap,
    tileWidth: tileWidth,
    plateHeight: plateHeight,
    gridWidth: columns * cellWidth
  }
}

// What a tile draws in its picture area: "image" with a path, or "mark" for
// the plugin's own television glyph.
//
// This INVERTS logoColumnShown's rule on purpose, and the inversion is the
// decision. In the 22 px row column a placeholder reads as a value, so the
// absence is the information -- correct there, because the name sits beside
// it and carries the row. On the wall the tile IS the row, so an empty tile
// does not read as "this channel has no picture", it reads as a missing
// channel. Measured on the configured list: 82 of 1,462 channels have no
// cached file, and on the provider list the roadmap measured, coverage is
// 27 per cent, so the empty-tile reading is the majority case there.
//
// The mark is the glyph the bar already shows when idle, not a shipped image.
// A font glyph takes the theme's foreground token, so it renders at the
// theme's own contrast on every theme -- which the logos themselves cannot
// do: 92 per cent of the real corpus carries transparency and its ink runs
// both ways, 42 per cent light and 22 per cent dark over a 199-file sample,
// so no plate colour makes all of them visible. The one thing on the tile
// that can never vanish is the one we draw ourselves.
function wallTile(opts) {
  var o = opts || {}
  var slot = logoSlot(o)
  if (slot.kind === "image") return { kind: "image", path: slot.path, glyph: "" }
  return { kind: "mark", path: "", glyph: GLYPHS.tv }
}

// What an arrow (or its hjkl twin) does, as a TABLE rather than as four
// branches repeated in three places.
//
// It exists because the 0.8.0 preflight blocked on those three places
// disagreeing. `handleSearchKey` routes the arrows itself rather than through
// PanelKeyCatcher's `onMoveRequested`, so a wall branch added to one of them
// did not reach the other, and the footer -- a third statement of the same
// fact -- was written against the intent rather than against either. Three
// statements joined by nothing but a name is the shape engineering rule 13 (dev branch)
// describes, and the first repair for it was a test that asserted the
// IDENTIFIERS appeared in each arm. That test went red when an arm was
// deleted and stayed green when the two arms were SWAPPED, which is rule 14's
// own definition of a criterion that cannot fail: it checked for the strings
// the implementation was written to contain.
//
// So the decision lives here, once, and every consumer dispatches on it.
// `target` is what moves: "cursor" is a place in the flat sequence (wrapping),
// "row" is a whole grid row (clamping, see wallStep), "scope" is the group
// facet. On the wall there is no facet -- the column is hidden -- so the
// horizontal axis moves the cursor instead, which is what hiding the column
// bought.
function arrowAction(opts) {
  var o = opts || {}
  var wall = o.wall === true
  var axis = str(o.axis)
  var delta = Math.floor(Number(o.delta) || 0)
  if (delta === 0 || (axis !== "v" && axis !== "h")) return { target: "none", delta: 0 }
  if (axis === "v") return { target: wall ? "row" : "cursor", delta: delta }
  return { target: wall ? "cursor" : "scope", delta: delta }
}

// One vertical step on the wall: down or up a whole row, keeping the column.
//
// `dir` is in ROWS, so a page is the same function with a bigger dir. The
// horizontal step is not here on purpose -- it is `moveCursor(index, +-1)`
// unchanged, because moving left and right across a grid laid out in reading
// order IS moving one place through the flat sequence, and giving it a second
// implementation is how two of them drift apart.
//
// The edges are the whole content of this function. A last row is usually
// PARTIAL, so the column under the cursor may not exist down there:
//   * down, and a row exists below: the nearest item in it, which is the last
//     item when the column is past the end of a partial row. "Down" always
//     moves down if there is anything below, which is what a person expects
//     and what leaving the cursor put would violate.
//   * down, already in the last row: stay. There is nothing below.
//   * up, past the top: the same column in the first row, so a page-up from
//     row 3 of 3 lands under the cursor rather than at index 0.
//   * up, already in the first row: stay.
function wallStep(index, dir, count, columns) {
  var n = Math.max(0, Math.floor(Number(count) || 0))
  if (n === 0) return 0
  var cols = Math.max(1, Math.floor(Number(columns) || 0))
  var at = Math.max(0, Math.min(n - 1, Math.floor(Number(index) || 0)))
  var d = Math.floor(Number(dir) || 0)
  if (d === 0) return at
  var target = at + d * cols
  if (target >= 0 && target < n) return target
  if (d > 0) {
    var lastRowStart = Math.floor((n - 1) / cols) * cols
    return at < lastRowStart ? n - 1 : at
  }
  return at < cols ? at : at % cols
}

// The lookup `logoSlot` wants, from the `names` array the helper prints.
function logoHaveSet(names) {
  var list = asList(names)
  var out = {}
  for (var i = 0; i < list.length; i++) {
    var name = str(list[i])
    if (name !== "") out[name] = true
  }
  return out
}

// Is the logo column present at all?
//
// The same rule the channel-number column follows (M2-03 4.2): zero width on a
// playlist that has none, so those rows are drawn exactly as they were before
// the feature existed. The test is over the rows ON SCREEN rather than the
// whole playlist, so a group holding no logos does not reserve a column for
// them -- and it reads the logo URL rather than the fetched file, so the
// column does not appear and disappear underneath the user while the fetch
// runs.
//
// A channel with no logo gets blank space inside the column, never a drawn
// placeholder. The codebase already settled this for the number column: a
// placeholder in a column reads as a value, and the absence is the
// information. At the 27 per cent coverage of the provider list that decision
// is the difference between a list and a list of empty boxes.
function logoColumnShown(rows, enabled, logoDir) {
  if (enabled !== true) return false
  var list = asList(rows)
  for (var i = 0; i < list.length; i++) {
    if (logoFile(list[i], logoDir) !== "") return true
  }
  return false
}

// D-LOGO-8. One name off the fetch's progress stream, or "" for any line that
// is not one -- including the summary object, which the caller handles
// separately. Defensive on purpose: this parses a line at a time from a
// long-running process, and a malformed one must cost that logo, not the run.
function logoStreamName(line) {
  var text = str(line).replace(/^\s+|\s+$/g, "")
  if (text === "") return ""
  try {
    var doc = JSON.parse(text)
    if (!doc || typeof doc !== "object") return ""
    if (str(doc.kind) !== "logo") return ""
    return str(doc.name)
  } catch (e) {
    return ""
  }
}

// What the helper's fetch reported, parsed defensively. Anything unreadable
// answers "no names", which leaves every slot blank -- the failure direction
// that draws nothing rather than the one that logs on every scroll.
function logoNamesFrom(stdoutText) {
  var text = str(stdoutText)
  if (text === "") return []
  try {
    var doc = JSON.parse(text)
    if (!doc || typeof doc !== "object") return []
    return asList(doc.names).filter(function (n) { return typeof n === "string" && n !== "" })
  } catch (e) {
    return []
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
  // Over the keys the write actually carries, rather than the two URL keys
  // by name. M2-04 made `showLogos` the third thing the plugin writes about
  // itself, and a rule spelled as two field comparisons would have silently
  // held a logo override in force while the host changed it underneath.
  // Comparison is by `str` so a boolean and the string "false" a hand-edited
  // shell.json can produce are the same value, which is what boolSetting and
  // optInSetting already assume everywhere else.
  for (var key in base) {
    if (!Object.prototype.hasOwnProperty.call(base, key)) continue
    if (str(host[key]) !== str(base[key])) return false
  }
  return true
}

// The settings the plugin acts on: the host's, with our own pending write
// laid over the keys that write carried, while it is still in force. Every
// other key always comes from the host.
function settingsWithOwnWrite(hostSettings, ownWrite) {
  var host = hostSettings || {}
  if (!ownWriteInForce(host, ownWrite)) return host
  var out = {}
  for (var k in host) out[k] = host[k]
  for (var w in ownWrite.value) {
    if (Object.prototype.hasOwnProperty.call(ownWrite.value, w)) out[w] = ownWrite.value[w]
  }
  return out
}

// The record of a write just made against `hostSettings`, over any set of
// keys. `base` is what the host said at the moment of the write, which is how
// the override knows to lapse when the host says anything else.
function ownWriteOf(hostSettings, values) {
  var host = hostSettings || {}
  var base = {}
  var value = {}
  for (var key in values) {
    if (!Object.prototype.hasOwnProperty.call(values, key)) continue
    base[key] = host[key]
    value[key] = values[key]
  }
  return { base: base, value: value }
}

// Every key this plugin owns inside the host's bar entry.
//
// D-LOGO-2, and the reason all of them are always stated. The entry handed to
// `updateEntryInline` is composed from `barConfig`, which the host publishes
// ONE WRITE BEHIND (see the last section of OMARCHY-PLUGIN-CONTRACT.md (dev
// branch)). A write that mentions only its own key therefore carries the
// PREVIOUS value of every other key back to disk -- so turning logos off and
// then editing a source URL wrote `showLogos: true` again, the setting came
// back on by itself, and the fetch resumed. The same hole existed in the
// other direction.
//
// Stating all three on every write makes both writers idempotent and makes
// neither able to revert the other. It is cheap because there are three.
var OWNED_SETTINGS = ["playlistUrl", "epgUrl", "showLogos"]

// The patch for a settings write: every owned key, at the value it should
// hold AFTER this write. `effective` is what the plugin currently acts on
// (settings, i.e. the host's values with any own-write already laid over
// them), and `overrides` is what this particular write is changing.
function ownedEntryPatch(effective, overrides) {
  var eff = effective || {}
  var ov = overrides || {}
  var out = {}
  for (var i = 0; i < OWNED_SETTINGS.length; i++) {
    var key = OWNED_SETTINGS[i]
    out[key] = Object.prototype.hasOwnProperty.call(ov, key) ? ov[key] : eff[key]
  }
  return out
}

// The URL pair, which is what every caller before M2-04 writes.
function ownWriteFor(hostSettings, playlistUrl, epgUrl) {
  return ownWriteOf(hostSettings, { playlistUrl: str(playlistUrl), epgUrl: str(epgUrl) })
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
// `mpvHandoff` vectors in the player-argv.json. fixture (dev branch)
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
    // The BASE name decides (D-SINK-2): `--scripts-append` sets the same
    // option `--scripts` does, and reserving one spelling reserved nothing.
    var base = mpvOptionBase(name)
    if (!ok || MPV_RESERVED[name] === true || MPV_RESERVED[base] === true
        || name.indexOf("--no-") === 0 && (MPV_RESERVED["--" + name.substring(5)] === true
                                           || MPV_RESERVED[mpvOptionBase("--" + name.substring(5))] === true)) rejected.push(token)
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

// Where the player is allowed to write (PO-11, D-PLY-7). mpv's own key
// bindings are live on its window and two of them write a durable file: `s`
// takes a screenshot and `Q` (quit-watch-later) writes a resume record.
// Before this they landed wherever the shell happened to be - the user's
// home for the screenshot, mpv's own ~/.local/state/mpv tree for the resume
// record - at mode 0644, outside every list of files this plugin says it
// writes.
//
//  - `cwd` is the runtime directory (0700, already there for the socket), so
//    anything still written relative to the process is private and gone at
//    logout rather than accumulating in $HOME.
//  - `screenshots` is durable on purpose: the user asked for that file, so
//    the runtime directory would be data loss at logout. It sits under the
//    state directory this plugin already owns and documents.
//  - `watchLater` is a resume position for a live stream, never worth
//    keeping: private and ephemeral.
//  - `shaderCache` is D-PLY-10, ruling CL2: without it mpv compiles its
//    shaders into $XDG_CACHE_HOME/mpv/, outside every list of files this
//    plugin says it writes. The cache is content-free and regenerable, so it
//    belongs in the runtime directory - already 0700, already documented,
//    gone at logout - and adds no durable path and nothing to clean up.
//
// Mirrored by `player_dirs()` in bin/omarchy-iptv.
function playerDirs(socketPath, stateDir) {
  var runtime = dirnameOf(socketPath)
  return {
    cwd: runtime,
    screenshots: str(stateDir) + "/screenshots",
    watchLater: runtime + "/watch-later",
    shaderCache: runtime + "/shader-cache"
  }
}

// os.path.dirname for the paths this plugin deals in.
function dirnameOf(path) {
  var text = str(path)
  var cut = text.lastIndexOf("/")
  if (cut < 0) return ""
  if (cut === 0) return "/"
  return text.substring(0, cut)
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
// vectors in the player-argv.json. fixture (dev branch)
function buildMpvArgv(params) {
  var p = params || {}
  var dirs = p.dirs || playerDirs(p.socketPath, p.stateDir)
  var argv = [
    "mpv",
    "--input-ipc-server=" + str(p.socketPath),
    // PIP_CLASS, not a third copy of the string. This flag is what makes the
    // window findable, and picture in picture matches `class === PIP_CLASS`
    // to decide which window it may float, shrink, move and pin. Two
    // literals that agree today can disagree tomorrow, and the failure is
    // silent: PiP would simply answer "Cannot find the player window" for
    // ever. The python mirror keeps its own literal and is pinned to this
    // one by the player-argv.json. fixture (dev branch)
    "--wayland-app-id=" + PIP_CLASS,
    "--force-window=immediate",
    "--idle=once",
    "--keep-open=no",
    "--title=" + mpvWindowTitle("IPTV"),
    "--force-media-title=IPTV",
    "--msg-level=all=error",
    // Live streams never need yt-dlp; without this mpv shells out to it on
    // every dead URL (seconds of delay and noise per failed zap). User
    // mpvArgs come later, so `--ytdl=yes` can re-enable it (PO-5).
    "--ytdl=no",
    // D-SINK-4. mpv autoloads every script in its system directory, and on
    // this distribution that includes mpv-mpris, which publishes `xesam:url`
    // -- the stream URL, credentials and all -- to every process on the
    // session bus for as long as a channel plays. Measured on the real bus
    // with a synthetic credential; `--force-media-title` guards the TITLE and
    // there is no equivalent option for the URL.
    //
    // mpv-mpris has no configuration surface at all (no script-opts; it reads
    // `path` and publishes it), so keeping it and not leaking is not
    // available. This plugin loads no script of its own, and `--script` /
    // `--scripts` / `--config-dir` are already reserved, so nothing here
    // depends on autoload.
    //
    // The cost, stated rather than hidden: Omarchy's own media widget reads
    // MPRIS and will stop showing the channel. That display is redundant --
    // this plugin's bar widget already shows the playing channel name -- and
    // a duplicate label is not worth a credential on the bus.
    "--load-scripts=no",
    // PO-11: the two directories mpv's own key bindings write into, named
    // rather than inherited. `--screenshot-dir` is deliberately NOT reserved
    // - user tokens land after these, so anyone who wants their screenshots
    // in ~/Pictures can still say so - while `--watch-later-dir` IS
    // reserved, because a resume record naming a stream path has no business
    // being pointed back at $HOME.
    "--screenshot-dir=" + str(dirs.screenshots),
    "--watch-later-dir=" + str(dirs.watchLater),
    // D-PLY-10 / CL2: mpv's shader and ICC caches default into
    // $XDG_CACHE_HOME/mpv/, outside this plugin's tree. Contained in the
    // runtime directory, ephemeral. Neither option is reserved - both caches
    // are content-free - so user tokens after these can still move them.
    "--gpu-shader-cache-dir=" + str(dirs.shaderCache),
    "--icc-cache-dir=" + str(dirs.shaderCache)
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

// D-ID-1. The two playlist invocations differ by ONE argument and the
// difference decides whether a user's favourites are rewritten. Building both
// here rather than inline in Service.qml is the point: nothing could see that
// argv before, so nothing could assert it, and the review that caught the
// missing flag caught it by reading rather than by a test.
//
// `--state-dir` is what makes the one-time id remap run, and the helper
// touches no state file without it. So the ACTIVE fetch carries it -- that is
// the one moment we know the user means this list -- and the PROBE must not,
// because a probe runs for every source add, edit, switch and re-check,
// including ones the user then cancels. Remapping global favourites against a
// playlist that never became active would be a loss caused by a fix.
function playlistFetchArgv(helperPath, url, cacheDir, stateDir) {
  var args = ["playlist", "--url", str(url), "--cache-dir", str(cacheDir)]
  if (str(stateDir) !== "") args = args.concat(["--state-dir", str(stateDir)])
  return helperArgv(helperPath, args)
}

function playlistProbeArgv(helperPath, url, cacheDir) {
  return helperArgv(helperPath, ["playlist", "--url", str(url), "--cache-dir", str(cacheDir)])
}

// M2-04. The fetch the consent screen authorizes, and the only place logos
// are downloaded. `--fetch` is what turns the helper's default survey into a
// download, so a command built without it contacts nobody -- the opt-in is
// spelled twice, once in the setting and once here.
// The dead-channel mark, written by the helper so the file lands 0600 inside
// the 0700 source directory -- the same reason logo writes go through it.
// argv items, never shell text: a channel id is playlist-derived.
function failedArgv(helperPath, action, id, cacheDir) {
  var verb = str(action) === "clear" ? "clear" : "mark"
  return helperArgv(helperPath, ["failed", verb, "--id", str(id), "--cache-dir", str(cacheDir)])
}

function logoFetchArgv(helperPath, cacheDir) {
  return helperArgv(helperPath, ["logos", "--fetch", "--cache-dir", str(cacheDir)])
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

// PAUSE LIVE TV (2026-09-24). Not rewind, and the naming matters: measured
// across 22 live channels from 21 providers, 21 paused and resumed correctly
// and exactly ONE reported itself seekable, so there is no going back to
// before the keypress. mpv keeps filling its cache while paused, so resuming
// continues from the moment it was pressed and the viewer is then behind
// live. The bound is mpv's default 150 MiB demuxer cache: 315 s measured on a
// ~3.8 Mbps stream, less on a fatter one.
//
// `state` is "on", "off" or "toggle"; anything else is a toggle, because a
// key that means "pause" must never be able to mean "start playing".
function playerPauseArgv(socket, state) {
  var want = str(state)
  if (want !== "on" && want !== "off") want = "toggle"
  return ["player", "pause", "--socket", str(socket), "--state", want]
}

// `ownerPid` claims the surviving player for this shell (4.14). Omitted, the
// probe is read-only.
function playerProbeArgv(socket, ownerPid) {
  var argv = ["player", "probe", "--socket", str(socket)]
  var pid = Math.floor(Number(ownerPid))
  if (isFinite(pid) && pid > 0) argv = argv.concat(["--owner-pid", String(pid)])
  return argv
}

// ---- D-PLY-11: the play fork ----
//
// What the shell decides when a channel is asked for, lifted here so it can
// be stated in vectors instead of living where no test can reach it
// (engineering rule 12 (dev branch)). Checked against Service.qml's play() by the lane that
// wired it; if the two ever disagree, the shipping fork is right.
//
//   start  spawn or adopt a player and play there (`player start`)
//   zap    a running player, switch it over the socket (`play`)
//   queue  a zap is already in flight; remember the intent instead
//
// The row that matters for D-PLY-11 is `playerPending && !socketAttached`:
// the player is starting and has not bound its socket, `playerUp` is already
// true because pending counts, and the fork therefore answers "zap" - a zap
// aimed at a socket nothing is listening on yet. That state is no longer a
// hypothesis: wave two measured it on a real shell (ruling CL9,
// QA-RESULTS.md (dev branch) D1) at TEN user-visible divergences in twenty cold
// concurrent bursts, none in ten warm and none in six cold serial, with the
// mechanism observed rather than inferred - a change wins the socket and the
// cold start's own `apply_channel` lands after it.
//
// The fork itself is NOT the defect and is deliberately left as it is. A zap
// aimed at a socket that is about to exist is how a burst stays responsive,
// and CL4 forbids the instrument that would order the two slots. What was
// wrong is what happened at the far end: the start applied its channel
// unconditionally. That is fixed in the helper (`player start` stands down
// when it finds a newer channel on a player it just spawned) and repaired
// here by `sessionIntentRepair` and `reconcileVerdict` below.
function playFork(state) {
  var s = state || {}
  var playerUp = !!s.socketAttached || !!s.playerPending
  if (!playerUp || s.stopping) return "start"
  if (s.controlBusy) return "queue"
  return "zap"
}

// True when the fork above sends a zap at a player that has not bound its
// socket yet. Reporting only - it changes nothing.
function playForkBlind(state) {
  var s = state || {}
  return playFork(s) === "zap" && !s.socketAttached
}

// `play --id ... --socket ... --cache-dir ...`, plus the additive session
// flags. Lifted out of Service.qml.playArgs (engineering rule 12 (dev branch)): the decision
// that SKIPS `--scope`/`--since` is the decision that skips the stash write
// at the far end (`cmd_play` computes `session = bool(scope or since)`), and
// it was the one argv builder in the file with no vectors anywhere.
//
// The flags go on only when the record being zapped is the one the shell
// currently wants. A drained burst can issue an id that is no longer
// `nowPlaying`, and stamping that record's scope and start time onto a
// different channel would be worse than leaving the stash alone.
function zapArgs(socket, cacheDir, key, nowPlaying) {
  var id = str(key)
  var argv = ["play", "--id", id, "--socket", str(socket), "--cache-dir", str(cacheDir)]
  var np = nowPlaying || null
  if (!np || str(np.id) !== id) return argv
  var scope = str(np.launchedFrom)
  if (scope !== "") argv = argv.concat(["--scope", scope])
  var since = Math.floor(Number(np.since))
  if (isFinite(since) && since > 0) argv = argv.concat(["--since", String(since)])
  return argv
}

// A reply the shell could not READ, as distinct from one that says the
// switch failed. The status branch has had this guard since the beginning -
// "neither healthy nor a strike, so a missing subcommand never reaps a
// working player" - and the play branch never grew it, so an empty stdout or
// a python traceback (both parse to `no_output`) took the rollback.
var PLAY_UNREADABLE = ["no_output", "not_implemented", "unknown_channel", "no_cache"]
// A refusal, not a verdict. `busy` cannot reach a zap today - `cmd_play`
// takes no lock - and routing it is the first half of ruling CL4's order:
// refusals first, THEN a sequence number and the lock. Without this it falls
// to the rollback, which is why CL4 says giving `play` the lock now would
// manufacture the failure it is meant to remove.
var PLAY_RETRYABLE = ["ipc_error", "busy"]

// What a failed `play` reply means for the shell.
//
//   start    the player is gone; `player start` adopts or spawns, so the
//            same call is right either way
//   retry    the player did not answer, or something else held the lock:
//            back off and re-issue rather than losing the zap
//   unknown  cannot tell. Record it, tell nobody, change nothing
//   failed   the switch really did not happen; the player still plays the
//            channel before it, so the label goes back with it
function playFailureVerdict(code, context) {
  var ctx = context || {}
  var word = str(code)
  if (word === "not_running" && ctx.nowPlaying === true) return "start"
  if (PLAY_RETRYABLE.indexOf(word) !== -1) {
    if (ctx.playerUp === true && ctx.nowPlaying === true && ctx.userStopped !== true
        && ctx.retriesLeft === true) return "retry"
    // Out of retries: a timeout really is a failed switch, a refusal never
    // was one.
    return word === "ipc_error" ? "failed" : "unknown"
  }
  if (PLAY_UNREADABLE.indexOf(word) !== -1) return "unknown"
  return "failed"
}

// Who a reply is about. Both `rememberEntry` call sites passed the shell's
// `nowPlaying`, which in a burst is the intent current when the REPLY
// landed, not the one the reply is for - which is precisely the case the
// entry-owner ring was built for (4.8). The consequence was a "Stream
// failed" toast naming a channel that never failed.
//
// `playing` is the `player start` stand-down's own field: when the helper
// leaves a newer channel alone, the entry on the player belongs to THAT
// channel, not to the one this verb was asked for.
function replyTarget(status, nowPlaying) {
  var doc = status && typeof status === "object" ? status : {}
  var left = doc.playing && typeof doc.playing === "object" ? doc.playing : null
  if (left && str(left.id) !== "") return { id: str(left.id), name: str(left.name) }
  if (str(doc.id) !== "") return { id: str(doc.id), name: str(doc.name) }
  if (nowPlaying && str(nowPlaying.id) !== "") return { id: str(nowPlaying.id), name: str(nowPlaying.name) }
  return null
}

// The shell's label against the player's own record, once a health tick can
// finally ask for it (`status` carries `stash`). Ruling CL5: the shell is
// authoritative and the repair is to RE-APPLY the user's intent, never to
// relabel from the player - relabelling would leave the user watching a
// channel they did not choose while the interface agreed with the mistake.
//
//   agree     the player's record names what the shell wants
//   unknown   nothing to compare: no record, no intent, or a record from a
//             different playlist whose ids mean something else. Never a
//             verdict, so an old helper or a foreign player raises nothing
//   diverged  they name different channels. `repair` is the id to re-apply
function reconcileVerdict(stash, nowPlaying, sourceKey) {
  var np = nowPlaying && str(nowPlaying.id) !== "" ? nowPlaying : null
  var record = playerStash(stash)
  var unknown = { state: "unknown", repair: "", wanted: np ? str(np.id) : "", playing: record ? record.id : "" }
  if (!np || !record || record.playing === false) return unknown
  var active = str(sourceKey)
  if (active !== "" && record.sourceKey !== "" && record.sourceKey !== active) return unknown
  if (record.id === str(np.id)) return { state: "agree", repair: "", wanted: str(np.id), playing: record.id }
  return { state: "diverged", repair: str(np.id), wanted: str(np.id), playing: record.id }
}

// The same question asked of a `player start` / `player restart` reply,
// which answers it directly: the helper says which channel it left on the
// player. "" means nothing to do; anything else is the id to re-apply.
function sessionIntentRepair(status, nowPlaying) {
  var left = replyTarget(status, null)
  var np = nowPlaying && str(nowPlaying.id) !== "" ? str(nowPlaying.id) : ""
  if (np === "" || !left || left.id === "") return ""
  return left.id === np ? "" : np
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
    seq: Math.max(0, Math.floor(Number(p.seq)) || 0),
    // Which slot wrote the record last. It exists because `seq` stopped
    // being able to say so: the zap used to hardcode 0, and "not zero"
    // therefore meant "a player verb wrote this". Both sides now carry a
    // real intent number, which is what makes them comparable, so the
    // writer is named instead of inferred.
    verb: str(p.verb)
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
// trap as a test double more forgiving than the real thing (engineering rule 10 (dev branch)).
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

// ------------------------------------------------- picture in picture (M2-05)
//
// Everything below is pure: it reads numbers and strings and returns argv
// vectors, plans and copy. Nothing here runs a process, and nothing here
// remembers anything. The compositor is the state of record (design 0 and
// 4.3): every decision takes a `live` read of `hyprctl -j clients` and acts
// on it, because the user has SUPER+T and SUPER+O bound and can change
// `floating` and `pinned` behind our back between any two steps.
//
// Three facts from the gate (QA-RESULTS.md (dev branch), M2-05-00) shape this code
// and override the design text where they disagree:
//
//   PIP10  The `action` argument is IGNORED. `float` and `pin` toggle
//          unconditionally, and asking to *unset* one on a tiled window
//          floats it instead. So no step here carries an action, and every
//          float/pin step is conditional on a fresh read. A lane that
//          "simplifies" a conditional back into a blind set reintroduces the
//          bug the gate's own probe nearly missed.
//   PIP11  Exit codes cannot detect failure. The compositor answers rc 0
//          `ok` for a dispatch aimed at a window that does not exist, and
//          reports a real refusal as `warning:` text on stdout with rc 0.
//          So success is defined in exactly one place, pipVerify(): read the
//          state back and compare it against what was asked for.
//   G-1    The legacy dispatcher spelling is a Lua SYNTAX ERROR here, not an
//          unknown dispatcher: `hyprctl dispatch` under a Lua config
//          provider wraps its argument as `return hl.dispatch(<arg>)`, so
//          `dispatch tagwindow +x address:0x..` cannot parse. There is no
//          legacy builder in this file for that reason - see the note on
//          focusPlayerArgv below, which is the defect that fact uncovered.

// The window class the player is launched with (buildMpvArgv's
// --wayland-app-id) and the tag this feature owns. Both are compile-time
// constants, which is what PIP7 requires of every value in a dispatch
// expression that is not an address or a clamped integer.
var PIP_CLASS = "omarchy-iptv"
var PIP_TAG = "iptv-pip"
// 4.2 rule 4 / 4.11 rule 1. Lower case only: the compositor prints
// addresses lower case, and accepting `0xDEAD` too would widen the pattern
// for nothing.
var PIP_ADDRESS_RE = /^0x[0-9a-f]{1,16}$/
// 4.11 rule 2. Coordinates are integers produced by pipGeometry or read back
// out of a snapshot we wrote; anything outside this range is refused rather
// than clamped, because a value that far out is a bug, not a preference.
var PIP_COORD_LIMIT = 100000
var PIP_MIN_WIDTH = 240
var PIP_CORNERS = ["top-right", "top-left", "bottom-right", "bottom-left"]
var PIP_SNAPSHOT_KEY = "user-data/omarchy-iptv-pip"
var PIP_SNAPSHOT_VERSION = 1
var PIP_MPV_RESIZE_PROP = "auto-window-resize"

// The only expressions this plugin may build. `call` is the namespace,
// `fields` the parameters beyond the window selector. Note `focus` sits at
// `hl.dsp.focus`, one level up from the window verbs: there is no
// `hl.dsp.window.focus` on this build (gate G-1, "attempt to call a nil
// value (field 'focus')"), so the namespace is part of what the tests pin.
// The installed stubs say the same thing independently:
// /usr/share/hypr/stubs/hl.meta.lua:908-931 lists these six window verbs and
// no focus, and :870-889 puts `focus` beside `window` at the top level.
var PIP_VERBS = {
  float: { call: "hl.dsp.window.float", fields: [] },
  pin: { call: "hl.dsp.window.pin", fields: [] },
  resize: { call: "hl.dsp.window.resize", fields: ["x", "y"] },
  move: { call: "hl.dsp.window.move", fields: ["x", "y"] },
  zorder: { call: "hl.dsp.window.alter_zorder", fields: ["mode"] },
  tag: { call: "hl.dsp.window.tag", fields: ["tag"] },
  focus: { call: "hl.dsp.focus", fields: [] }
}

// Every non-integer field value is drawn from one of these lists. There is
// no "pass a string through" branch anywhere in the builder.
var PIP_ENUMS = {
  mode: ["top"],
  tag: ["+" + PIP_TAG, "-" + PIP_TAG]
}

// The third belt (4.11): whatever the builder assembled must still look like
// one call with one brace pair and no Lua punctuation of its own. A value
// that reached this far carrying `(`, `)`, `;`, `\` or a quote would be
// refused here even if the field checks above had been loosened.
var PIP_EXPR_RE = /^hl\.dsp\.(window\.)?[a-z_]+\(\{ [A-Za-z0-9_ ."=+:,-]* \}\)$/

function pipAllows(list, value) {
  for (var i = 0; i < list.length; i++) if (list[i] === value) return true
  return false
}

// An address becomes a selector only by matching the pattern. Called at
// construction (pipFindWindow, pipPlan) and again at the call
// (pipExpression), so a future caller cannot route around it (PIP7).
function pipAddressSelector(address) {
  var value = str(address)
  return PIP_ADDRESS_RE.test(value) ? "address:" + value : ""
}

// The ONE window selector that exists: our own pid-matched address.
//
// It used to accept `class:omarchy-iptv` as well, for the focus command
// alone, and D-PIP-5 is what that cost: with a user's own
// `mpv --wayland-app-id=omarchy-iptv` present, focus landed on the
// STRANGER'S window three times out of three. 4.2 had already learned this
// for every other verb - "narrowing by pid is not optional" - and focus was
// simply the verb nobody applied it to. The class branch is gone rather than
// merely unused, so the selector cannot come back through a future caller:
// pipExpression refuses `class:` anything now, which is a property a test
// can assert (engineering rule 11 (dev branch)).
function pipSelector(window) {
  var value = str(window)
  if (value.indexOf("address:") !== 0) return ""
  return pipAddressSelector(value.substring(8))
}

// An integer, or null. NOT a coercion: a string, a float, a NaN, an object
// or a number past the limit is REFUSED, never parsed or clamped into
// range. PIP7 says only integers already clamped to their ranges may enter
// the expression, so the clamping belongs to pipGeometry and pipOptions and
// this is the gate that proves it happened.
function pipInt(value) {
  if (typeof value !== "number") return null
  if (!isFinite(value) || Math.floor(value) !== value) return null
  if (value < -PIP_COORD_LIMIT || value > PIP_COORD_LIMIT) return null
  return value
}

// The one place a compositor expression is built. Returns "" - never a
// partial or escaped string - for anything it will not vouch for. There is
// deliberately no escaping function in this file: a value that would need
// escaping is a value that must not be here (PIP7).
function pipExpression(verb, params) {
  var spec = PIP_VERBS[str(verb)]
  if (!spec || !Object.prototype.hasOwnProperty.call(PIP_VERBS, str(verb))) return ""
  var p = params && typeof params === "object" ? params : {}
  var window = pipSelector(p.window)
  if (window === "") return ""
  var parts = ["window = \"" + window + "\""]
  for (var i = 0; i < spec.fields.length; i++) {
    var field = spec.fields[i]
    if (field === "x" || field === "y") {
      var n = pipInt(p[field])
      if (n === null) return ""
      parts.push(field + " = " + String(n))
      continue
    }
    var text = str(p[field])
    if (!pipAllows(PIP_ENUMS[field] || [], text)) return ""
    parts.push(field + " = \"" + text + "\"")
  }
  var expr = spec.call + "({ " + parts.join(", ") + " })"
  return PIP_EXPR_RE.test(expr) ? expr : ""
}

// argv for one dispatch, or [] if the expression was refused. One argv
// vector, no shell (engineering rule 2 (dev branch)); the Lua string is one argv ITEM, which is
// the separate boundary 4.11 governs.
function pipDispatchArgv(verb, params) {
  var expr = pipExpression(verb, params)
  return expr === "" ? [] : ["hyprctl", "dispatch", expr]
}

// D-PIP-1: focus the player window.
//
// This emitted `["hyprctl", "dispatch", "focuswindow", "class:omarchy-iptv"]`
// from v0.3.0 until now. Under a Lua config provider `hyprctl dispatch`
// wraps its argument as `return hl.dispatch(<arg>)`, so those two bare
// tokens are a Lua syntax error - rc 7, `')' expected near 'class'`, focus
// unchanged - and every one of the four call sites has been a no-op. It
// failed silently because it goes out through `Quickshell.execDetached`,
// which returns void, so rc 7 never reached the plugin.
//
// It now goes through the same validated builder PiP uses, which is what
// keeps the shape right: one argv item after `dispatch`, a real namespace
// (`hl.dsp.focus`, not `hl.dsp.window.focus`, which does not exist), and a
// selector the builder vouched for.
//
// D-PIP-5, the second half of the same defect. That repair fixed the
// spelling and kept the SELECTOR, which was `class:omarchy-iptv` - and with
// a user's own `mpv --wayland-app-id=omarchy-iptv` open, the live pass
// watched it focus the stranger's window three times out of three. This is
// the lesson 4.2 already wrote down for every other verb and that focus was
// left out of: the plugin knows its player's pid, so it can resolve its own
// window, and a command that cannot say WHICH window it means must not be
// sent at all. `address` is the one pipFindWindow resolved; anything else -
// an empty string because the window has not mapped yet, a second match the
// lookup refused - yields [] and the caller dispatches nothing.
function focusPlayerArgv(address) {
  return pipDispatchArgv("focus", { window: pipAddressSelector(address) })
}

// Was this dispatch accepted? PIP11: rc cannot answer, because the
// compositor returns 0 for a dispatch that did nothing at all. It prints
// exactly `ok` on success and `warning: ...` / `error: ...` on a refusal,
// so this reads the reply as a keyword, never as text to show anyone. It is
// a cheap first filter only - pipVerify is the definition of success.
function pipDispatchAccepted(stdout) {
  return str(stdout).replace(/^\s+|\s+$/g, "") === "ok"
}

// ---- settings (section 6)

function pipCornerOf(value) {
  var v = str(value).toLowerCase().replace(/^\s+|\s+$/g, "")
  return pipAllows(PIP_CORNERS, v) ? v : PIP_CORNERS[0]
}

// The three PiP settings, clamped. Unknown corner falls back to the default
// exactly as channelOrder does; the two integers go through clampSetting so
// their ranges live in SETTING_RANGES with every other range.
function pipOptions(entry) {
  return {
    corner: pipCornerOf(settingOf(entry, "pipCorner", PIP_CORNERS[0])),
    sizePercent: clampSetting("pipSizePercent", settingOf(entry, "pipSizePercent", SETTING_RANGES.pipSizePercent.def)),
    margin: clampSetting("pipMargin", settingOf(entry, "pipMargin", SETTING_RANGES.pipMargin.def))
  }
}

// ---- resolving the window (4.2)

function pipWindowFail(reason) {
  return { ok: false, reason: reason, address: "", at: [0, 0], size: [0, 0], floating: false, pinned: false, monitor: -1, workspaceId: -1, tags: [], pip: false }
}

function pipInteger(value, fallback) {
  var n = Number(value)
  return isFinite(n) ? Math.floor(n) : fallback
}

// A two-integer pair inside the coordinate limit, or null. Used for `at`,
// `size` and every pair that comes back out of a snapshot - so it goes
// through pipInt, which REFUSES rather than coerces. A "690" or a 1.5 in a
// snapshot is corruption, not a preference, and flooring it would put the
// window somewhere nobody asked for.
function pipPair(value) {
  var list = asList(value)
  if (list.length !== 2) return null
  var a = pipInt(list[0])
  var b = pipInt(list[1])
  return a === null || b === null ? null : [a, b]
}

// 4.2 rule 5: a rule-applied tag reads back with a trailing `*`
// (`default-opacity*` on this machine), a dispatched one does not. Confirmed
// live by G-11.
function pipTagsOf(entry) {
  var raw = asList(entry ? entry.tags : null)
  var out = []
  for (var i = 0; i < raw.length; i++) out.push(str(raw[i]).replace(/\*+$/, ""))
  return out
}

function pipHasTag(live) {
  var tags = asList(live ? live.tags : null)
  for (var i = 0; i < tags.length; i++) if (str(tags[i]).replace(/\*+$/, "") === PIP_TAG) return true
  return false
}

// Find OUR player window in `hyprctl -j clients`. Narrowing by pid is not
// optional: PLY-RST-11 reproduced a user's own
// `mpv --wayland-app-id=omarchy-iptv` making the class match TWO windows.
// Focusing a stranger's window is a nuisance; floating, shrinking, pinning
// and moving it is damage. Zero matches and two matches both refuse.
// Never throws: garbage in, ok:false out.
function pipFindWindow(clients, pid, className) {
  var list = clients
  if (typeof list === "string") {
    try { list = JSON.parse(list) } catch (error) { return pipWindowFail("bad_clients") }
  }
  if (!Array.isArray(list)) return pipWindowFail("bad_clients")
  var want = pipInteger(pid, -1)
  if (want <= 0) return pipWindowFail("no_pid")
  var name = str(className) !== "" ? str(className) : PIP_CLASS
  var hits = []
  for (var i = 0; i < list.length; i++) {
    var c = list[i]
    if (!c || typeof c !== "object") continue
    if (str(c["class"]) !== name) continue
    if (pipInteger(c.pid, -1) !== want) continue
    hits.push(c)
  }
  if (hits.length === 0) return pipWindowFail("no_window")
  if (hits.length > 1) return pipWindowFail("ambiguous")
  var win = hits[0]
  var address = str(win.address)
  if (pipAddressSelector(address) === "") return pipWindowFail("bad_address")
  var at = pipPair(win.at)
  var size = pipPair(win.size)
  var workspace = win.workspace && typeof win.workspace === "object" ? win.workspace.id : win.workspace
  var out = {
    ok: true,
    reason: "",
    address: address,
    at: at || [0, 0],
    size: size || [0, 0],
    floating: win.floating === true,
    pinned: win.pinned === true,
    monitor: pipInteger(win.monitor, -1),
    workspaceId: pipInteger(workspace, -1),
    tags: pipTagsOf(win)
  }
  out.pip = pipActive(out)
  return out
}

// Is the window in OUR picture in picture right now?
//
// The tag is the marker, because it is the only part of the state that says
// "we did this": a window the user popped themselves with SUPER+O is
// floating and pinned and must still read as "not in PiP" (4.8), and a
// window we PiP'd keeps the tag through a shell restart (4.7). `floating`
// joins it so a box the user has since tiled with SUPER+T reads as off and
// the next `p` puts it back in the corner rather than only removing a tag.
// `pinned` is deliberately NOT required: the user may unpin a corner box and
// it is still theirs to toggle off.
function pipActive(live) {
  var l = live && typeof live === "object" ? live : {}
  if (l.ok === false) return false
  return l.floating === true && pipHasTag(l)
}

// "on" / "off" / "toggle" resolved against the live read (never a remembered
// boolean; 4.3).
function pipResolveIntent(mode, live) {
  var m = str(mode)
  if (m === "on" || m === "off") return m
  return pipActive(live) ? "off" : "on"
}

// ---- re-deriving the reported state (4.7 step 3, D-PIP-4)
//
// The state of record is the compositor. A request already re-reads it
// before it plans, which is why `p` kept working after `omarchy restart
// shell`; what was missing is the same read taken ONCE when a player becomes
// ours, so that what the plugin SAYS about itself follows the window too.
// Without it the live pass measured `status.pip.on` reading false on all 30
// one-second samples while the box was demonstrably floating, pinned and
// tagged, the bar tooltip never gained its line, and the next accepted
// request replied `"was":false` (D-PIP-4).
//
// Note what this function is NOT given: there is no parameter for a
// previously reported value, and none for a remembered flag, because after a
// shell restart this process has no memory at all and the window is still in
// the corner. A boolean would be wrong in exactly the case it exists for.
//
// `decided` is the honest half. A read that cannot see OUR window - garbage,
// no match, a pid we do not know yet, two matches - answers decided:false,
// and the caller must then leave what it reports alone. Announcing "off" on
// the strength of a read that saw nothing is the same lie in the other
// direction.
function pipDeriveState(clients, pid, className) {
  var live = pipFindWindow(clients, pid, className)
  if (live.ok !== true) {
    return { decided: false, on: false, address: "", reason: str(live.reason), live: live }
  }
  return { decided: true, on: pipActive(live), address: live.address, reason: "", live: live }
}

// May the out-of-band read run at all? Three clauses that would otherwise sit
// in QML where no test can reach them (engineering rule 12 (dev branch)):
//
//   no pid   - the window cannot be narrowed, and narrowing is not optional
//              (4.2); a class-only lookup is the D-PIP-5 defect.
//   busy     - a request owns the read pipeline and its verified answer wins;
//              a stray read landing mid-sequence must not overwrite it.
//   reading  - one read in flight at a time, so a retrying focus cannot fan
//              out into a queue of hyprctl calls.
//
// `available` is deliberately NOT here: reading `hyprctl -j clients` is
// harmless under any provider, and gating the READ on the dispatch spelling
// would tie two unrelated facts together. The caller that dispatches is the
// one that must care.
function pipDeriveGate(ctx) {
  var c = ctx && typeof ctx === "object" ? ctx : {}
  if (pipInteger(c.pid, 0) <= 0) return { ok: false, code: "no_pid" }
  if (c.busy === true) return { ok: false, code: "busy" }
  if (c.reading === true) return { ok: false, code: "reading" }
  return { ok: true, code: "" }
}

// ---- geometry (4.4)

// The monitor the window is on, out of `hyprctl -j monitors`, by the `id`
// the client entry reports (4.9). Takes the raw stdout or an already-parsed
// array, exactly as pipFindWindow does, and never throws: garbage, an empty
// list and an id no monitor claims all answer null, and null means the
// caller refuses instead of placing the box on a guessed screen.
//
// There is deliberately no "fall back to the first monitor" branch. On the
// single-monitor machine this was written on that fallback would always be
// right and would therefore never be exercised; on the two-monitor desk it
// exists for, it would silently throw the player onto the other screen.
function pipFindMonitor(monitors, id) {
  var list = monitors
  if (typeof list === "string") {
    try { list = JSON.parse(list) } catch (error) { return null }
  }
  if (!Array.isArray(list)) return null
  // `null` is not monitor 0. pipInteger coerces it there (Number(null) is 0),
  // which would turn "the service does not know which monitor" into "the
  // first one", so the absent cases are refused before it is consulted.
  if (id === null || id === undefined || id === "" || typeof id === "boolean") return null
  var want = pipInteger(id, -1)
  if (want < 0) return null
  for (var i = 0; i < list.length; i++) {
    var m = list[i]
    if (!m || typeof m !== "object") continue
    if (pipInteger(m.id, -1) === want) return m
  }
  return null
}

// Sizes are floored to EVEN integers so a 16:9 box never lands on an odd
// edge that chroma subsampling has to round.
function pipEven(value) {
  var v = Math.floor(value)
  return v - (v % 2)
}

// The corner box for one monitor entry of `hyprctl -j monitors`, in GLOBAL
// layout coordinates, because that is what the `move` dispatcher takes
// (proven live: `move {x=940, y=42}` landed at exactly [940, 42]). Returns
// null for a monitor it cannot make a valid box on, so the caller refuses
// rather than dispatching a guess.
//
// `hyprctl monitors` reports PHYSICAL pixels, so every step divides by
// scale first; an odd `transform` swaps the axes; `reserved` is subtracted
// explicitly rather than dodged with an inset, because Omarchy's own pip.lua
// clears this machine's 26 px bar by four pixels of luck.
function pipGeometry(monitor, opts) {
  var m = monitor && typeof monitor === "object" ? monitor : null
  if (!m) return null
  var width = Number(m.width)
  var height = Number(m.height)
  if (!isFinite(width) || !isFinite(height) || width <= 0 || height <= 0) return null
  var scale = Number(m.scale)
  if (!isFinite(scale) || scale <= 0) scale = 1
  var lw = Math.round(width / scale)
  var lh = Math.round(height / scale)
  var transform = pipInteger(m.transform, 0)
  if (Math.abs(transform % 2) === 1) {
    var swap = lw
    lw = lh
    lh = swap
  }
  var o = opts && typeof opts === "object" ? opts : {}
  var corner = pipCornerOf(o.corner)
  var percent = clampSetting("pipSizePercent", o.sizePercent)
  var margin = clampSetting("pipMargin", o.margin)
  var ox = pipInteger(m.x, 0)
  var oy = pipInteger(m.y, 0)
  var reserved = asList(m.reserved)
  var r0 = pipInteger(reserved[0], 0)
  var r1 = pipInteger(reserved[1], 0)
  var r2 = pipInteger(reserved[2], 0)
  var r3 = pipInteger(reserved[3], 0)
  var x0 = ox + r0 + margin
  var y0 = oy + r1 + margin
  var x1 = ox + lw - r2 - margin
  var y1 = oy + lh - r3 - margin
  var availW = x1 - x0
  var availH = y1 - y0
  if (availW < 2 || availH < 2) return null
  var w = Math.round(lw * percent / 100)
  if (w < PIP_MIN_WIDTH) w = PIP_MIN_WIDTH
  if (w > availW) w = availW
  var h = Math.round(w * 9 / 16)
  if (h > availH) {
    h = availH
    w = Math.round(h * 16 / 9)
    if (w > availW) w = availW
  }
  w = pipEven(w)
  h = pipEven(h)
  if (w < 2 || h < 2) return null
  var x = corner === "top-right" || corner === "bottom-right" ? x1 - w : x0
  var y = corner === "bottom-left" || corner === "bottom-right" ? y1 - h : y0
  return pipBox({ x: x, y: y, w: w, h: h })
}

// A {x, y, w, h} of four integers inside the dispatch limits, or null. The
// gate between "geometry was computed" and "geometry may be dispatched".
function pipBox(box) {
  var b = box && typeof box === "object" ? box : {}
  var x = pipInt(pipInteger(b.x, NaN))
  var y = pipInt(pipInteger(b.y, NaN))
  var w = pipInt(pipInteger(b.w, NaN))
  var h = pipInt(pipInteger(b.h, NaN))
  if (x === null || y === null || w === null || h === null) return null
  if (w < 1 || h < 1) return null
  return { x: x, y: y, w: w, h: h }
}

// ---- the previous state (4.5)

// What we write into the player at PiP-on, so that "what was it before?"
// has exactly the window's lifetime: it survives a shell restart and a
// channel change and dies with the window. A window whose rectangle we
// cannot read is recorded as NOT floating, so the restore degrades to
// "unfloat and let the layout take it" rather than moving it to 0,0.
function pipSnapshotFor(live) {
  var l = live && typeof live === "object" ? live : {}
  var at = pipPair(l.at)
  var size = pipPair(l.size)
  var usable = at !== null && size !== null && size[0] > 0 && size[1] > 0
  return {
    active: true,
    at: at || [0, 0],
    size: size || [0, 0],
    floating: l.floating === true && usable,
    pinned: l.pinned === true,
    monitor: pipInteger(l.monitor, -1),
    workspace: pipInteger(l.workspaceId !== undefined ? l.workspaceId : l.workspace, -1),
    v: PIP_SNAPSHOT_VERSION
  }
}

function pipSnapshotClear() {
  return { active: false, v: PIP_SNAPSHOT_VERSION }
}

// Read a snapshot back. It arrives from the player over a socket, so it is
// re-validated field by field before any of it can reach an expression: a
// string coordinate, a float, a huge number or a missing pair all answer
// null, and null means the degraded restore. Never throws.
function pipParseSnapshot(raw) {
  var s = raw
  if (typeof s === "string") {
    try { s = JSON.parse(s) } catch (error) { return null }
  }
  if (!s || typeof s !== "object" || Array.isArray(s)) return null
  if (s.active !== true) return null
  var at = pipPair(s.at)
  var size = pipPair(s.size)
  if (at === null || size === null || size[0] < 1 || size[1] < 1) return null
  return {
    active: true,
    at: at,
    size: size,
    floating: s.floating === true,
    pinned: s.pinned === true,
    monitor: pipInteger(s.monitor, -1),
    workspace: pipInteger(s.workspace, -1),
    v: PIP_SNAPSHOT_VERSION
  }
}

// ---- the plan (4.3)

// The ordered argv vectors for one transition. Every float and pin step is
// conditional on `live` (PIP10); order matters and is the order
// omarchy-hyprland-window-pop uses: unpin before unfloat, because pin
// applies to floating windows and unfloating a pinned window clears the pin
// by itself. Returns [] when anything it would need is missing or refused -
// a partial plan is worse than none, because half of it would land.
function pipPlan(live, snapshot, geometry, intent) {
  var l = live && typeof live === "object" ? live : {}
  if (l.ok === false) return []
  var selector = pipAddressSelector(l.address)
  if (selector === "") return []
  var want = str(intent) === "off" ? "off" : "on"
  var steps = []
  if (want === "on") {
    var box = pipBox(geometry)
    if (box === null) return []
    // No `action` anywhere below: PIP10 proved it is ignored, and a step
    // that carries an argument the compositor throws away is a lie about
    // what the code does.
    if (l.floating !== true) steps.push(pipDispatchArgv("float", { window: selector }))
    steps.push(pipDispatchArgv("resize", { window: selector, x: box.w, y: box.h }))
    steps.push(pipDispatchArgv("move", { window: selector, x: box.x, y: box.y }))
    // pin refuses a tiled window (rc 0 plus a warning), so it comes after
    // the float step, and only when the window is not already pinned.
    if (l.pinned !== true) steps.push(pipDispatchArgv("pin", { window: selector }))
    steps.push(pipDispatchArgv("zorder", { window: selector, mode: "top" }))
    steps.push(pipDispatchArgv("tag", { window: selector, tag: "+" + PIP_TAG }))
  } else {
    var snap = pipParseSnapshot(snapshot)
    steps.push(pipDispatchArgv("tag", { window: selector, tag: "-" + PIP_TAG }))
    // Unpin only what we pinned: a window the user had already pinned before
    // PiP stays pinned.
    if (l.pinned === true && !(snap && snap.pinned === true)) steps.push(pipDispatchArgv("pin", { window: selector }))
    if (snap && snap.floating === true && l.floating === true) {
      steps.push(pipDispatchArgv("resize", { window: selector, x: snap.size[0], y: snap.size[1] }))
      steps.push(pipDispatchArgv("move", { window: selector, x: snap.at[0], y: snap.at[1] }))
    } else if (l.floating === true) {
      // No snapshot, or it says the window was tiled: unfloat and let the
      // layout take it. Degraded, never stuck.
      steps.push(pipDispatchArgv("float", { window: selector }))
    }
  }
  for (var i = 0; i < steps.length; i++) if (steps[i].length === 0) return []
  return steps
}

// The mpv half (4.6): `auto-window-resize` off while in PiP so a zap to a
// different resolution cannot resize the box, and the snapshot beside it.
// The gate found the compositor already ignores a floating window's size
// request here, so this is portability insurance rather than the load-
// bearing job 4.6 claims - see the report's open item.
function pipMpvCommands(intent, opts) {
  var o = opts && typeof opts === "object" ? opts : {}
  if (str(intent) === "off") {
    return [
      ["set_property", PIP_MPV_RESIZE_PROP, pipRestoreAutoResize(o.mpvArgs)],
      ["set_property", PIP_SNAPSHOT_KEY, pipSnapshotClear()]
    ]
  }
  return [
    ["set_property", PIP_MPV_RESIZE_PROP, false],
    ["set_property", PIP_SNAPSHOT_KEY, pipSnapshotFor(o.live)]
  ]
}

// What `auto-window-resize` goes back to at PiP-off: the user's own value if
// their mpvArgs set one, otherwise mpv's default `yes`. Derived, not read
// back, because an mpv reply is never proof of anything about the window
// (2.5) - and because the value we must restore is the user's intent, not
// whatever we ourselves last wrote.
function pipRestoreAutoResize(mpvArgs) {
  var tokens = Array.isArray(mpvArgs) ? mpvArgs : str(mpvArgs).split(/\s+/)
  var flag = "--" + PIP_MPV_RESIZE_PROP
  var value = true
  for (var i = 0; i < tokens.length; i++) {
    var token = str(tokens[i])
    if (token === "") continue
    if (token === "--no-" + PIP_MPV_RESIZE_PROP) value = false
    else if (token === flag) value = true
    else if (token.indexOf(flag + "=") === 0) {
      var raw = token.substring(flag.length + 1).toLowerCase()
      value = !(raw === "no" || raw === "false" || raw === "0" || raw === "")
    }
  }
  return value
}

// One line of mpv's IPC, as a REPLY or nothing. An event line carries
// `event` and is not a reply however much it looks like one; a reply always
// carries `error`. Never throws. Routing a reply to the request that asked
// for it is the caller's job - this only says what the line is.
function parsePlayerReply(line) {
  var text = str(line).replace(/^\s+|\s+$/g, "")
  if (text === "") return null
  var obj
  try { obj = JSON.parse(text) } catch (error) { return null }
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return null
  if (obj.event !== undefined) return null
  if (obj.error === undefined) return null
  var id = obj.request_id
  return {
    ok: str(obj.error) === "success",
    requestId: typeof id === "number" && isFinite(id) ? Math.floor(id) : null,
    error: str(obj.error),
    data: obj.data === undefined ? null : obj.data
  }
}

// ---- did it work? (PIP11)

function pipSamePair(actual, expected) {
  var a = pipPair(actual)
  return a !== null && a[0] === expected[0] && a[1] === expected[1]
}

// THE definition of success in this feature. `live` is a FRESH
// pipFindWindow after the queue has run; `expected` is the geometry that was
// asked for (intent "on") or the snapshot that was being restored (intent
// "off"). Exit codes and stdout are not consulted here on purpose: the
// compositor reports success for a dispatch aimed at a window that does not
// exist, so the only honest question is what the window looks like now.
function pipVerify(live, intent, expected) {
  var l = live && typeof live === "object" ? live : {}
  if (l.ok === false) return { ok: false, reason: str(l.reason) !== "" ? str(l.reason) : "no_window" }
  var tagged = pipHasTag(l)
  if (str(intent) !== "off") {
    var box = pipBox(expected)
    if (box === null) return { ok: false, reason: "bad_geometry" }
    if (l.floating !== true) return { ok: false, reason: "not_floating" }
    if (l.pinned !== true) return { ok: false, reason: "not_pinned" }
    if (!tagged) return { ok: false, reason: "not_tagged" }
    if (!pipSamePair(l.at, [box.x, box.y])) return { ok: false, reason: "wrong_position" }
    if (!pipSamePair(l.size, [box.w, box.h])) return { ok: false, reason: "wrong_size" }
    return { ok: true, reason: "" }
  }
  if (tagged) return { ok: false, reason: "still_tagged" }
  var snap = pipParseSnapshot(expected)
  if (snap && snap.floating === true) {
    if (l.floating !== true) return { ok: false, reason: "not_restored" }
    if (!pipSamePair(l.at, snap.at) || !pipSamePair(l.size, snap.size)) return { ok: false, reason: "wrong_position" }
    return { ok: true, reason: "" }
  }
  if (l.floating === true) return { ok: false, reason: "still_floating" }
  if (l.pinned === true) return { ok: false, reason: "still_pinned" }
  return { ok: true, reason: "" }
}

// ---- copy (section 5) and the key

// Footer lines, section 5's table. Anything not listed answers "" rather
// than inventing a line; pipResultCode is what turns a verdict into one of
// these keys, so a new failure reason cannot leak a raw compositor word
// into the footer.
var PIP_TEXT = {
  on: "Picture in picture on",
  off: "Picture in picture off",
  nothing_playing: "Nothing playing",
  no_compositor: "Picture in picture needs Hyprland",
  no_window: "Cannot find the player window",
  dispatch_failed: "Hyprland refused the window change"
}
var PIP_TOOLTIP_ON = "Picture in picture: on"

function pipStatusText(code) {
  var key = str(code)
  return Object.prototype.hasOwnProperty.call(PIP_TEXT, key) ? PIP_TEXT[key] : ""
}

// A pipVerify verdict becomes one of the six codes above. Every "we asked
// and the window does not look like it" reason lands on dispatch_failed,
// which is the honest line: we cannot tell the user WHY the compositor
// declined, only that the window is not what we asked for.
function pipResultCode(verdict, intent) {
  var v = verdict && typeof verdict === "object" ? verdict : {}
  if (v.ok === true) return str(intent) === "off" ? "off" : "on"
  var reason = str(v.reason)
  if (reason === "no_window" || reason === "ambiguous" || reason === "bad_address" || reason === "bad_clients" || reason === "no_pid") return "no_window"
  return "dispatch_failed"
}

// What the toggle key answers before anything is dispatched: the two
// refusals the guide can decide by itself (4.10). Everything else needs the
// live read and comes back through pipResultCode.
function pipKeyRequest(ctx) {
  var c = ctx && typeof ctx === "object" ? ctx : {}
  if (c.available !== true) return { ok: false, code: "no_compositor", text: pipStatusText("no_compositor") }
  if (c.playing !== true) return { ok: false, code: "nothing_playing", text: pipStatusText("nothing_playing") }
  return { ok: true, code: "", text: "" }
}

// List-mode single-letter commands (UX 3.3, section 5). This used to be a
// chain of string comparisons inside Guide.qml, where no test could reach
// it - exactly the shape engineering rule 12 (dev branch) forbids - so the mapping lives here
// and the guide only dispatches on the answer. Digits, "." and "," never
// arrive: the number machine takes them first (M2-03 2.9).
function listLetterAction(text) {
  var t = str(text)
  if (t === "f" || t === "F") return "favorite"
  if (t === "s" || t === "S") return "stop"
  if (t === "r" || t === "R") return "refresh"
  if (t === "p" || t === "P") return "pip"
  // PAUSE LIVE TV. The action is offered unconditionally here and gated at
  // the call site on something playing, the same way `pip` is: the table says
  // what a letter MEANS, not whether it can act right now.
  if (t === PAUSE_KEY || t === PAUSE_KEY.toUpperCase()) return "pause"
  if (t === "/") return "search"
  if (t.toLowerCase() === SOURCE_KEYS.open) return "sources"
  return ""
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
// D-SINK-1. The userinfo group used to be `(?:[^@\/\s]*@)?`, which cannot span
// a SECOND `@` -- while the host group happily accepted one. A provider whose
// password contains an un-encoded `@` therefore had its password TAIL survive
// into the host position and out through a desktop notification. RFC 3986 puts
// userinfo before the LAST `@` of the authority, so the group now runs to it
// and the host excludes `@` entirely. Both changes are needed: either alone
// still leaks.
function redactUrls(text) {
  return str(text).replace(/[a-z][a-z0-9+.-]*:\/\/(?:[^\/\s]*@)?([^\/\s?#:@]*)[^\s]*/gi, function(all, host) {
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

// M2-09 GS9 / D-GS-2. Does guide data actually reach these rows?
//
// The rule this lane established for the second line is that it exists when it
// carries something that VARIES, and the shipped predicate asked the wrong
// question of the EPG: whether a URL is configured. On the subscriber's
// provider those are different facts. One of their 3,335 channels carries a
// `tvg-id` at all and it matches nothing in the guide data, so configuring an
// EPG did not trade the density for now/next -- it returned a BLANK second
// line on all 3,335 rows and took three visible rows to print white space.
// That is the original defect in a different costume. Configured is not
// present; this counts the rows the data can actually fill.
//
// Matched on the IDENTIFIER and on whether the entry holds a titled programme
// at all -- never on what is on air right now. `epgFields` hides a `now` whose
// stop has passed, so counting live titles would make this answer, and
// therefore the row height, change on the 30 s clock tick and re-height the
// list under the cursor. The trap the earlier round of this work named.
//
// One pass, one own-property lookup per row with a `tvg-id`, no clock.
function epgCoverage(channels, epgMap) {
  var list = asList(channels)
  var map = epgMap && typeof epgMap === "object" ? epgMap : {}
  var out = { total: list.length, withId: 0, matched: 0, carries: false }
  for (var i = 0; i < list.length; i++) {
    var row = list[i]
    var id = row ? str(row.tvgId) : ""
    if (id === "") continue
    out.withId++
    if (!Object.prototype.hasOwnProperty.call(map, id)) continue
    var entry = map[id]
    if (!entry || typeof entry !== "object") continue
    if ((entry.now && str(entry.now.title) !== "") || (entry.next && str(entry.next.title) !== "")) out.matched++
  }
  out.carries = out.matched > 0
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

// The failure notice, in one place (M2-09 D4). UX.md:181, UX.md:739, ruling 9
// and UX 7.2 all mandate these exact words paired with the alert glyph, and
// after D4 they are rendered from two different slots depending on the row's
// height -- so they are built here once and both callers use it, rather than
// two string literals that can drift.
function failedNotice(at) {
  return joinParts(["Failed " + str(at), "Space to retry"])
}

// The failure notice as the row's right meta slot carries it on a single-line
// row (M2-09 D4). That slot renders `until HH:MM` and is deliberately blank on
// a failed row already, so it is free exactly when it is needed -- which is
// what lets `rowsHaveDetail` stop depending on session-mutable state.
function rowFailedMeta(at) {
  return str(at) === "" ? "" : failedNotice(at)
}

// The whole of the meta slot's text, so the decision is asserted rather than
// stranded in a QML ternary (engineering rule 12 (dev branch)). `until HH:MM` while the row
// is healthy; the failure notice when the row has failed AND has no detail
// line to carry it; nothing otherwise -- which is the shipped behaviour of a
// failed row with a detail line, and the reason the slot was free to take it.
function rowMeta(opts) {
  var o = opts || {}
  var failedAt = str(o.failedAt)
  if (failedAt !== "") return o.hasDetail === true ? "" : failedNotice(failedAt)
  return str(o.until) === "" ? "" : "until " + str(o.until)
}

// M2-09 GS8. The opacity rung a row's secondary text carries, lifted out of
// the two QML bindings that render it (engineering rule 12 (dev branch)) so a test can call
// the shipping decision instead of mirroring it.
//
// UX 5.3's dim rung is de-emphasis and it is right for ambient text: `until
// HH:MM`, the group name, now/next are all there to be glanced at. The failure
// notice is not ambient. It is the one string in the guide that names a key
// the user is meant to press, and the live pass measured it as the LOWEST
// contrast text on the card -- 3.78:1 on the cursor row against a 4.5:1
// threshold -- because the dim rung is applied over the selected row's lighter
// fill. So the notice carries no de-emphasis at all: same colour token
// (Color.menu.text, no literal and no new token), full rung.
//
// It keeps the card's text colour rather than the row's selected colour, which
// is what makes this hold in EVERY theme rather than only in the one that was
// measured: `menu.selected-background` is `menu.text` at 0.08, so the card's
// text token is near-identical against both row fills, while `selected-text`
// is the theme's accent and is under 4.5:1 against its own row in eight of the
// twenty-three installed themes -- which is why the selected GROUP label now
// takes the calibrated ink (D-RUNG-15) and the channel name takes the plain
// text token (product-owner ruling 2026-09-21). The notice therefore reads the same whether or not the
// cursor is on the row, which is the right property for an alert.
// ------------------------------------------------------------ contrast
//
// One arithmetic, called by the shipping code AND by the tests. It lived only
// in Model.test.js (dev branch tests), which was fine while nothing SHIPPED a decision made
// with it. Two do now (D-RUNG-4 and D-RUNG-5), and a private copy in the test
// is precisely the shape engineering rule 12 (dev branch) forbids: a test that mirrors logic
// instead of calling it passes while the shipping path is broken.
//
// `colorOver` is the load-bearing one. `Color.menu.selectedBackground` is not
// a colour: it is `menu.text` carrying alpha 0.08 over the background, and an
// implementation that forgets that composite is measuring a surface the user
// never sees.

// WCAG 2.1 relative luminance. Input is [r, g, b] in 0-255.
function relativeLuminance(rgb) {
  var lin = []
  for (var i = 0; i < 3; i++) {
    var c = Number(rgb[i]) / 255
    lin.push(c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4))
  }
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
}

function contrastRatio(a, b) {
  var la = relativeLuminance(a), lb = relativeLuminance(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

// `fg` drawn at `alpha` over `bg`. Alpha compositing and "mix toward the
// background" are the SAME operation, which is why switching one for the other
// moves nothing: every opacity rung in this guide already dims toward the
// background. The bar was the only site dimming toward BLACK (Qt.darker), and
// that is exactly why it was the only site that could invert on a light theme.
function colorOver(fg, bg, alpha) {
  var a = Number(alpha)
  if (!(a >= 0)) a = 0
  if (a > 1) a = 1
  var out = []
  for (var i = 0; i < 3; i++) out.push(Number(fg[i]) * a + Number(bg[i]) * (1 - a))
  return out
}

function colorMix(a, b, t) { return colorOver(a, b, 1 - Number(t)) }

// The calibrated-target rule, as arithmetic rather than as advice.
//
// UX-GUIDE-AT-SCALE.md (dev branch) section 16 measured this model against real pixels:
// accurate to within a known tolerance and ALWAYS SLIGHTLY OPTIMISTIC, so a
// design computing exactly 4.50 renders at about 4.40. "Above the line, never
// on it" now has a number, and the margin is READ FROM THE CALIBRATION FIXTURE
// rather than restated here -- so widening that tolerance to hide a bad model
// breaks this decision too, instead of only its own check.
var WCAG_AA_TEXT = 4.5

// D-RUNG-15. The accent (`Color.menu.selectedText`) is under 4.5:1 against its
// own selected fill in 8 of 23 installed themes AT FULL OPACITY: rose-pine
// 2.80, miasma 3.26, nord 3.77, catppuccin-latte 3.87, solitude 4.05, lupine
// 4.15, osaka-jade 4.15, white 4.26. No opacity change can reach that; only
// the ink can.
//
// WHERE THIS APPLIES, since 2026-09-21: the accent means ACTIVE, never CURSOR.
// Its sites are the selected GROUP label and the confirm dialog's selected
// button. It was originally written for the channel name and number on the
// cursor row (D-RUNG-4), and that is no longer where it is used: a 2 px mark
// carries the cursor, and the row's text stays at the plain text token. Inking
// the cursor row instead costs contrast on 22 of 23 themes, median 31 per cent
// and up to 73, and leaves the selected name fainter than an unselected one on
// 23 of 23.
//
// Raising the FILL instead is counterproductive and monotonically so, because
// the fill moves toward the foreground and the accent sits between them: the
// failing count goes 8 at alpha 0.08 to 19 at 0.25 to 23 at 0.50.
//
// So: keep the accent wherever it already clears the target, and elsewhere mix
// it the least distance toward `Color.menu.text` that does. 15 of 23 themes are
// byte-identical; the other 8 keep between 30 and 93 per cent of their accent
// distance. ("On screen" was in that sentence for a long time and was false
// the whole time -- see D-RUNG-13: the fill reaching this arithmetic was
// uncomposited, so the mix fell through to the text token on every theme and
// none of these figures had ever painted.)
//
// THE TARGET IS 4.70, NOT 4.50, and the margin is not arbitrary. Measured off
// real screenshots (UX-GUIDE-AT-SCALE.md (dev branch) section 16 and the rose-pine pass
// that followed it), this arithmetic is optimistic by about 1 per cent at title
// size and 2 per cent at body size, so 4.70 renders near 4.62. The same target
// would NOT be safe for caption-size text, which loses 7 to 9 per cent; a
// 10-pixel string needs its own, higher target.
var CURSOR_INK_TARGET = 4.7

// Both inputs and the fill are [r, g, b] in 0-255. Returns [r, g, b].
// The mix-search sibling of alphaForContrast, and it carried the same defect
// in its FALLBACK (D-RUNG-17). Returns the LEAST mixed colour that clears
// `target` against `fill`; when nothing clears it, returns the mix that
// MAXIMISES contrast rather than the far endpoint.
//
// colorMix interpolates in gamma space and relativeLuminance is convex, so the
// contrast of a mix against a third colour is not monotonic in the mix
// fraction. Handing back `toward` on failure therefore picks an arbitrary
// point, not the best one: over a deterministic 20,000-pair sweep a better mix
// existed on 57.7 per cent of the fallbacks, worst case 1.0273 returned where
// 4.5722 was available one step in. No installed theme reaches the fallback,
// which is why it went unnoticed -- the same reason D-RUNG-16 did.
function mixForContrast(from, toward, fill, target) {
  var best = contrastRatio(from, fill), bestMix = from.slice ? from.slice(0) : from
  for (var step = 1; step <= 100; step++) {
    var mixed = colorMix(from, toward, step / 100)
    var c = contrastRatio(mixed, fill)
    if (c >= target) return mixed
    if (c > best) { best = c; bestMix = mixed }
  }
  return bestMix
}

function cursorInk(accent, text, fill) {
  if (contrastRatio(accent, fill) >= CURSOR_INK_TARGET) return accent.slice ? accent.slice(0) : accent
  return mixForContrast(accent, text, fill, CURSOR_INK_TARGET)
}

// The QML seam. A QML `color` exposes r, g and b as 0-1 floats, and a binding
// wants a string back. Kept here rather than in Guide.qml so the whole decision
// is one node-testable function and the QML side holds no arithmetic at all
// (engineering rule 12 (dev branch)).
function qmlRgb(c) {
  if (!c) return [0, 0, 0]
  if (typeof c.length === "number") return [Number(c[0]), Number(c[1]), Number(c[2])]
  return [Number(c.r) * 255, Number(c.g) * 255, Number(c.b) * 255]
}

function hexOf(rgb) {
  var out = "#"
  for (var i = 0; i < 3; i++) {
    var v = Math.round(Number(rgb[i]))
    if (v < 0) v = 0
    if (v > 255) v = 255
    var h = v.toString(16)
    out += h.length === 1 ? "0" + h : h
  }
  return out
}

// Resolve a QML colour that carries alpha over the surface it actually paints
// on. An opaque colour resolves to itself, so a caller that composited already
// is unaffected.
//
// D-RUNG-13. The sentence that stood here said the fill "is a real colour by
// the time it reaches here, not a token needing composition". That was false,
// and it was the defect stated in prose: the host defines
// `Color.menu.selectedBackground` as `Util.alpha(menu.text, 0.08)` -- a colour
// whose r, g and b are the TEXT'S and whose alpha is 0.08, never composited.
// `qmlRgb` reads three channels, so `cursorInk` was handed the text colour as
// its fill, `contrastRatio(accent, text)` never reached the target (the best
// any theme manages is white at 4.12), the mix walked toward the text and
// could not gain on it, and the loop fell through to `return text` on 23 of 23
// themes. The 100-step loop was dead code and every figure costed against that
// fill described a surface that has never painted.
//
// A MISSING background keeps the old, unsafe behaviour rather than throwing: a
// QML binding that raises leaves `color` undefined and paints something worse
// than a wrong colour, and this one is the guide's own cursor ink. The guard
// against forgetting the argument is therefore a test, not an exception: the
// suite on the dev branch asserts both paths and the binding's own text,
// because a silent fall back to "treat it as opaque" is precisely how this
// defect survived for the life of the feature.
function qmlFill(fill, background) {
  var a = fill && typeof fill.a === "number" ? Number(fill.a) : 1
  if (!(a < 1) || background === undefined || background === null) return qmlRgb(fill)
  // `background` is taken as OPAQUE and is not composited recursively. A theme
  // may set `menu.background-alpha` below 1, and then the real surface beneath
  // the card is the wallpaper, which is unknowable from here -- so treating the
  // card as opaque is the only defensible reading, not an oversight. No
  // installed theme does it today.
  return colorOver(qmlRgb(fill), qmlRgb(background), a)
}

// What Guide.qml binds. `background` is Color.menu.background, the surface the
// selected fill is painted over; it is required whenever `fill` carries alpha.
function cursorInkHex(accent, text, fill, background) {
  return hexOf(cursorInk(qmlRgb(accent), qmlRgb(text), qmlFill(fill, background)))
}

// How far the ink travelled, 0 meaning "the accent is untouched". Reported so
// the cost of this change is a number in a test rather than an impression.
function cursorInkMix(accent, text, fill) {
  if (contrastRatio(accent, fill) >= CURSOR_INK_TARGET) return 0
  for (var step = 1; step <= 100; step++) {
    if (contrastRatio(colorMix(accent, text, step / 100), fill) >= CURSOR_INK_TARGET) return step / 100
  }
  return 1
}

// D-RUNG-9. The host's section header dims with `Qt.darker(foreground, 1.4)`,
// which divides the ink's HSV value -- it dims toward BLACK. That is the exact
// operation D-RUNG-3 and D-RUNG-5 removed from the bar, and it fails the same
// two ways: on three themes the 10 px bold label lands under 4.5:1
// (everforest 3.8017, gruvbox 4.2533, tokyo-night 4.2788), and on five LIGHT
// themes it moves the ink AWAY from a pale background, so the "dimmed" header
// comes out bolder than the body text it is meant to sit under -- rose-pine
// 9.79 against 6.66, and on `white` an exact tie at 21.00 against 21.00,
// because darkening pure black is a no-op.
//
// So the guide overrides `color` at its two call sites and dims toward the
// BACKGROUND instead, which is ordinary alpha compositing and cannot invert.
//
// The alpha is not a constant, and that is the point. A single rung -- the
// bar's 0.86, say -- clears every threshold but lifts the 18 dark themes by
// 2.05 to 4.86 ratio points and collapses the header's separation from body
// text from about 1.94x to 1.32x: the header stops reading as dimmed on every
// theme this machine ships, to fix three. Spending a signal that works
// everywhere to buy one that works in a few places is the trade D-RUNG-13
// already refused on the cursor row.
//
// Instead: hold the SEPARATION roughly constant and let the alpha vary, with a
// hard floor so the fix cannot undo itself. Same shape as `cursorInk` -- walk
// until a target is met and stop at the first value that does.
var SECTION_HEADER_SEPARATION = 1.93
// 4.50 plus the calibration fixture's own `tolerance.abs`, because a 10 px
// BOLD caption renders at model accuracy (D-RUNG-14, measured) and so a target
// of 4.65 really does land above the line rather than on it.
var SECTION_HEADER_FLOOR = 4.65

// Both inputs are QML colours or [r, g, b]. Returns the opacity to draw the
// section header at, over `background`.
// ---- one alpha search, called by every rung that picks one ----------------
//
// D-RUNG-16. This exists because the search was written twice and the SECOND
// copy was audited while the first kept the bug both were born with.
//
// The bug is an assumption that looks free: that contrast rises with alpha, so
// "if full opacity cannot clear the target, nothing can". It does not rise
// monotonically. colorOver blends in GAMMA space and relativeLuminance's
// transfer is convex, so a blend's luminance sits below the straight line
// between its endpoints; when the channels move in opposite directions the
// contrast curve PEAKS IN THE INTERIOR. Measured on #c50236 over #20f91e:
// 0.70 -> 4.3973, 0.83 -> 4.7318, 1.00 -> 4.2580. A short circuit on the
// full-opacity value therefore returns a FAILING rung while a passing one sits
// two steps away, and the fallback "return 1" picks the WORST rung available
// rather than the best.
//
// Neither branch could bite the 23 installed themes -- the minimum
// full-opacity contrast across all 46 surfaces is 5.9384, 28 per cent above
// the floor, and a 10,000-step scan finds no non-monotonic surface among them.
// That is exactly why it survived: an unreachable branch is an untested one.
//
// Returns the LOWEST alpha in [fromStep/100, 1] whose composite clears
// `target`. When nothing clears it, returns the alpha that MAXIMISES contrast,
// which the counterexample above shows is not always 1.
function alphaForContrast(fg, bg, target, fromStep) {
  var best = -1, bestAt = 1
  for (var step = fromStep; step <= 100; step++) {
    var a = step / 100
    var c = contrastRatio(colorOver(fg, bg, a), bg)
    if (c >= target) return a
    if (c > best) { best = c; bestAt = a }
  }
  return bestAt
}

function sectionHeaderAlpha(foreground, background) {
  var fg = qmlRgb(foreground), bg = qmlRgb(background)
  // SECTION_HEADER_SEPARATION is a CEILING on dimming, not a guaranteed
  // minimum: dim as far as the separation allows, but never below the floor.
  var target = Math.max(SECTION_HEADER_FLOOR, contrastRatio(fg, bg) / SECTION_HEADER_SEPARATION)
  // A theme whose body text is at or under the target has no dimming to give,
  // and alphaForContrast says so by returning its most legible rung -- which
  // is 1 wherever contrast really is monotonic, so every installed theme gets
  // back byte-identically what the short circuit used to hand it.
  return alphaForContrast(fg, bg, target, 1)
}

// ---- D-RUNG-14, the caption rung, chosen per SURFACE ----------------------
//
// A caption is drawn at 0.7 so it reads as secondary. That rung was picked
// against the card, and the same rung on the SELECTED row is a different
// rendering: `Color.menu.selectedBackground` is the text colour at 0.08 over
// the card, so the fill moves TOWARD the ink and the caption loses contrast it
// never agreed to lose. Measured on tokyo-night, 4.6433 on the card and 4.2157
// on the selection -- one side of 4.5 each. No font weight recovers that; bold
// measures 4.1893 there, which is model accuracy and still a failure, because
// the ceiling is in the arithmetic and not in the glyph.
//
// So the rung is an OUTPUT, not a constant: hold the rendered contrast at the
// floor and let alpha be whatever that costs on the fill the element is
// actually on. The same shape as sectionHeaderAlpha above, for the same reason.
//
// This raises NOTHING on 16 of 23 themes -- they clear the floor at 0.7 on both
// surfaces and get 0.7 byte-identical. The other 7 rise to between 0.71 and
// 0.89, and the worst case is rose-pine, which was never close: 3.1402.
var CAPTION_BASE = 0.7
// 4.50 plus the calibration fixture's `tolerance.abs`, the same derivation as
// SECTION_HEADER_FLOOR and deliberately the same number. They are separate
// constants because they answer to separate evidence and either may move alone.
// This one is the floor for a BOLD caption, which renders at model accuracy.
var CAPTION_FLOOR = 4.65
// A REGULAR 10 px caption does not render at model accuracy: it lands 11 to 13
// per cent below the model, which is why the calibration fixture gives the
// caption class a RELATIVE tolerance instead of the absolute one (F-CAL-1,
// measured live on 15 rows). A model value of 4.65 therefore renders about
// 4.09 at regular weight -- under AA. So a regular caption needs its floor
// grossed up by that shortfall rather than sharing the bold one. Two of the
// five caption sites are deliberately regular (prose, not labels), and giving
// them the bold floor would have shipped a number that looks verified and is
// not.
var CAPTION_REGULAR_SHORTFALL = 0.15
var CAPTION_FLOOR_REGULAR = 4.5 / (1 - CAPTION_REGULAR_SHORTFALL)

// `fill` is the composited surface the caption lands on -- pass the result of
// qmlFill for an alpha-carrying QML colour, never the alpha colour itself.
// `floor` defaults to the bold floor; pass CAPTION_FLOOR_REGULAR for a site
// that ships at regular weight.
function captionAlpha(foreground, fill, floor) {
  var fg = qmlRgb(foreground), bg = qmlRgb(fill)
  var want = typeof floor === "number" ? floor : CAPTION_FLOOR
  // Never dim BELOW the base rung, and never raise where the base already
  // clears the floor: the rung is what keeps a caption secondary, and spending
  // hierarchy on a surface that did not need it is the cost this avoids.
  if (contrastRatio(colorOver(fg, bg, CAPTION_BASE), bg) >= want) return CAPTION_BASE
  // NO short circuit on the full-opacity value, and that is load-bearing.
  // Contrast is NOT monotonic in alpha: colorOver blends in gamma space and the
  // luminance transfer is convex, so when the channels move in opposite
  // directions the curve PEAKS in the interior. Measured on #c50236 over
  // #20f91e: 0.70 -> 4.3973, 0.83 -> 4.7318, 1.00 -> 4.2580. A guard that read
  // "if full opacity cannot clear the floor, return 1" therefore returned a
  // FAILING rung while a passing one existed two steps away. It also happened
  // to be dead against all 46 installed surfaces, so no test reached it -- an
  // untested branch that could only ever be wrong.
  // One search, shared with sectionHeaderAlpha (D-RUNG-16). A second copy of
  // this loop is how the non-monotonicity bug outlived its own discovery.
  return alphaForContrast(fg, bg, want, Math.round(CAPTION_BASE * 100) + 1)
}

var TEXT_DIM = 0.52
var TEXT_FULL = 1
// D-RUNG-3 and D-RUNG-5, the bar's idle glyph. It is the one element of this
// plugin on screen permanently, and it was BOTH too faint on dark themes and
// inverted on light ones.
//
// The old operation was Qt.darker, which reduces the ink's HSV value -- it dims
// toward BLACK. That is fine on a dark theme and backwards on a light one,
// where moving the ink away from a pale background RAISES its contrast: at the
// shipped factor catppuccin-latte measured 11.00 idle against 7.06 active, and
// on `white` the operation was an exact no-op because darkening pure black
// changes nothing. Five themes were inverted or tied.
//
// This dims toward the BACKGROUND instead, which is ordinary alpha
// compositing, and is the same operation every opacity rung in the guide
// already performs. That identity is why switching operations fixes the bar and
// moves nothing else: the bar was the only site in this plugin dimming toward
// black, which is precisely why it was the only site that could invert.
//
// 0.86 is chosen by the calibrated-target rule, not by eye. Across all 23
// installed themes it gives 0 under the threshold, 0 inverted, and a floor of
// 4.77 -- clear of the 4.65 that 4.5 plus the calibration tolerance demands
// (the contrast-calibration.json fixture (dev branch)). 0.84 would read 4.56 and fail
// that rule while still looking fine on paper, which is the whole point of
// having the rule as arithmetic instead of as advice.
//
// The cost, accepted: the 18 dark themes lose dimming range, separation from
// the active glyph falling from about 1.58x to 1.30x. Affordable here and
// nowhere else, because ruling R7 gives every state its own GLYPH, so the
// dimming is decorative and state is never carried by colour alone.
var BAR_IDLE_ALPHA = 0.86

function rowNoticeEmphasis(failedAt) {
  return str(failedAt) === "" ? TEXT_DIM : TEXT_FULL
}

// Row detail line (UX 2.4): `Group - Now: X - Next: Y`, group omitted inside
// its own group, EPG segments replaced by the failure notice when set.
function rowDetail(opts) {
  var o = opts || {}
  var parts = []
  if (o.showGroup) parts.push(str(o.group))
  if (str(o.failedAt) !== "") {
    return joinParts([o.showGroup ? str(o.group) : "", failedNotice(o.failedAt)])
  }
  if (str(o.nowTitle) !== "") parts.push("Now: " + str(o.nowTitle))
  if (str(o.nextTitle) !== "") parts.push("Next: " + str(o.nextTitle))
  return joinParts(parts)
}

// M2-09 D3, lifted out of a QML binding per engineering rule 12 (dev branch) so a test can
// call the shipping decision rather than reimplement it.
//
// Two-line rows wherever the detail line can carry something that varies:
// the group name (only when a group is a narrowing step -- on a playlist whose
// 3,335 rows all read `United States` it is a constant, and UX 2.4 already
// scopes the group line to lists "where the group name is meaningful"), or
// EPG now/next. The predicate strictly dominates the shipped `!scopeIsGroup`:
// exactly one cell of the truth table changes, and no shape loses a row.
//
// GS9: the EPG term is `epgCarries`, from `epgCoverage`, and NOT whether an
// EPG is configured. Both halves of this predicate now ask the same question
// -- does this line carry something that varies -- of the data rather than of
// a setting. A guide source whose ids match nothing gives every row a blank
// second line, which costs three visible rows and returns nothing.
//
// THREE parameters, and deliberately no fourth: a failure term here is what
// made row height depend on session state, so one dead stream re-heighted a
// whole scope mid-session under the cursor. The notice moved to the meta slot
// (D4) precisely so this function could stop reading failures.
function rowsHaveDetail(opts) {
  var o = opts || {}
  return rowShowsGroup(o) || o.epgCarries === true
}

// Whether a row prints its group on the detail line (M2-09 D3): not inside
// that group's own scope, and not when every row would print the same word.
function rowShowsGroup(opts) {
  var o = opts || {}
  return o.scopeIsGroup !== true && o.groupsNarrow !== false
}

// Accessible name for a channel row (UX 7.1, M2-03 8.1). An unnumbered row
// in a numbered playlist announces nothing extra: the empty slot is not read
// out, because the absence IS the information (CN6).
function rowAccessibleName(opts) {
  var o = opts || {}
  var out = str(o.name)
  if (str(o.chno) !== "") out = "Channel " + str(o.chno) + ", " + out
  if (o.favorite) out += ", favorite"
  if (o.playing) out += ", playing"
  if (str(o.nowTitle) !== "") out += ", now " + str(o.nowTitle) + (str(o.until) !== "" ? " until " + str(o.until) : "")
  if (str(o.failedAt) !== "") out += ", failed"
  // M2-09 D5 / GS5: the position, LAST -- after the failure state, so someone
  // stepping rows hears the name first and the index after. Today this
  // announces no index at all, which told a screen-reader user strictly less
  // about position than the eye once the header started carrying one (UX 7.2:
  // no fact by position alone). `rowCount` is what the list holds, so under a
  // query it is the capped 200 the header also counts against; the true match
  // total stays in the footer. Absent or out of range appends nothing.
  var total = Math.floor(Number(o.rowCount) || 0)
  var at = Math.floor(Number(o.rowIndex) || 0)
  if (total > 0 && at >= 0 && at < total) out += ", row " + formatCount(at + 1) + " of " + formatCount(total)
  return out
}

function elide(text, max) {
  var value = str(text)
  var limit = max > 3 ? Math.floor(max) : 3
  return value.length > limit ? value.substring(0, limit - 1) + ELLIPSIS : value
}

// D-A11Y-6. The whole empty state -- no matches, first run, loading, error,
// no favourites -- carried NO accessibility markup at all, so a screen-reader
// user got silence at the one moment the screen is nothing but an explanation.
// The harness found it as L2-Q-05: "when nothing matches, SOMETHING on the bus
// says so", measured with 0 rows and 0 nodes naming the query.
//
// Ruling SG1 sharpened this into a real defect rather than a latent one. Whole-
// word group matching creates a dead zone where a query legitimately matches
// nothing, and the empty state is then the ONLY thing on screen telling the
// user what happened. A hint was added there for the eye; this is the same
// sentence for the ear.
function emptyStateAccessibleName(title, prose) {
  var head = str(title)
  var body = str(prose)
  if (head === "") return body
  if (body === "") return head
  return head + ". " + body
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
  // PAUSE LIVE TV. R7 is that a bar state is never carried by colour alone,
  // so a paused stream gets its own glyph rather than the playing one dimmed.
  if (o.playing && o.paused) return GLYPHS.tvPause
  if (o.playing) return GLYPHS.tvPlay
  if (o.error) return GLYPHS.tvOff
  return GLYPHS.tv
}

// UX 6.3 tooltips. `serviceMissing` wins (ARCHITECTURE.md section 7).
//
// M2-05 section 5 / PIP2: when picture in picture is on the tooltip gains
// one LINE for it and nothing else changes - no new mouse gesture, and the
// glyph stays as it is, because PiP is a window state and the bar already
// carries playback truth. PIP9: the line says the window is in PiP, never
// that it is on top of anything.
function barTooltip(opts) {
  var o = opts || {}
  if (o.serviceMissing) return "IPTV" + SEP + "service not loaded, run omarchy restart shell"
  var line = ""
  // M2-03 6.4: the number joins the tooltip whenever the playing channel has
  // one, including on a vertical bar where the label itself is glyph-only.
  if (o.playing && str(o.name) !== "") line = (o.paused ? "Paused " : "Playing ") + (str(o.chno) !== "" ? str(o.chno) + SEP : "") + str(o.name)
  else if (o.refreshing) line = "IPTV" + SEP + "refreshing playlist" + ELLIPSIS
  else if (!o.configured) line = "IPTV" + SEP + "no playlist configured"
  else if (o.error) line = "IPTV" + SEP + "playlist error, open the guide"
  else line = "IPTV" + SEP + "click to open the guide"
  return o.pip === true ? line + "\n" + PIP_TOOLTIP_ON : line
}

function barAccessibleName(opts) {
  var o = opts || {}
  // PAUSE LIVE TV. The glyph and the tooltip both changed for paused; the
  // accessible name has to as well, or the one user who cannot see the glyph
  // is the one user not told. That asymmetry is exactly the D-GS-3 shape.
  if (o.playing && str(o.name) !== "") return "IPTV, " + (o.paused ? "paused" : "playing") + " " + (str(o.chno) !== "" ? "channel " + str(o.chno) + ", " : "") + str(o.name)
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
    // M2-13: the wall hides the group column, which is what frees the width
    // for bigger tiles and what lets h/l be horizontal cursor movement instead
    // of a group facet. Decided here so one function owns the answer.
    showColumn: has && o.narrow !== true && o.wall !== true,
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
  // M2-03 6.2: a live number buffer sits at the TOP of the ladder, above the
  // transient. While the user is typing digits the footer is the running
  // report of what those digits resolve to, and a three-second transient
  // from an earlier action must not cover it.
  var entry = o.numberEntry
  if (entry && entry.active === true) {
    return chnoStatus(str(entry.kind), str(entry.kind) === "none" || str(entry.kind) === "" ? str(entry.buffer) : str(entry.label),
      str(entry.name), entry.matches, entry.ordinal, false)
  }
  if (str(o.transient) !== "") return str(o.transient)
  if (o.configured === false || !(Number(o.count) > 0)) return ""
  if (o.truncated) return "First " + formatCount(o.cap || MAX_ROWS_DEFAULT) + " of " + formatCount(o.resultTotal) + SEP + "keep typing"
  if (str(o.playingName) !== "") return GLYPHS.play + " " + str(o.playingName) + SEP + "s stop"
  if (o.refreshing) return "Refreshing" + ELLIPSIS
  if (footerDegraded(o)) return footerCounts(o)
  if (o.epgPending) return "Guide data loading" + ELLIPSIS
  if (str(o.warning) !== "") return str(o.warning)
  // D-SAVE-1: below a warning, above the plain counts, and only in Favourites
  // (the caller passes "" everywhere else).
  if (str(o.savedSearches) !== "") return str(o.savedSearches)
  // D-HOST-1. Below a provider warning, which is more urgent, and above the
  // plain counts, which are what the footer shows most of the time -- so this
  // is seen without ever displacing something that needs acting on first.
  if (o.staleBuild === true) return "Updated" + SEP + "restart the shell to see the new version"
  return footerCounts(o)
}

// Footer hint pairs [key, verb] (UX 6.2, UX-SOURCES 5.3); the guide styles
// keys and verbs at different opacities. `o.form` is the open form (its
// focused element decides the set), `o.cursorKind` the Sources row kind,
// `o.sourcesExist` adds `o sources` to the error empty state.
// The word for what an arrow does, derived from arrowAction so the footer and
// the handler cannot disagree. "move" for a place in the sequence, "row" for
// a whole grid row, and the scope's own verb for the group facet.
function arrowVerb(o, axis) {
  var act = arrowAction({ axis: axis, delta: 1, wall: o && o.wall === true })
  if (act.target === "row") return "row"
  if (act.target === "cursor") return "move"
  return scopeVerb(o)
}

function footerHints(opts) {
  var o = opts || {}
  var mode = str(o.mode)
  if (mode === "confirmRemove" || mode === "confirmLogos") return [["Left/Right", "choose"], ["Enter", "confirm"], ["Esc", "cancel"]]
  if (mode === "sourceEdit" || mode === "sourceXtream") return formHints(o.form)
  if (mode === "sources") {
    if (o.cursorKind === "add" || o.cursorKind === "xtream") return [["j/k", "move"], ["Enter", "open"], ["Esc", "back"]]
    // M2-04: `g logos` reads the CURRENT state, so the key says what it will
    // do rather than what is on. A hint that always reads "logos" leaves the
    // user pressing it to find out, and finding out means contacting sixty-
    // three hosts.
    return [["j/k", "move"], ["Enter", "switch"], [SOURCE_KEYS.add, "add"], [SOURCE_KEYS.xtream, "Xtream"], [SOURCE_KEYS.edit, "edit"], [SOURCE_KEYS.remove, "remove"], [SOURCE_KEYS.logos, o.showLogos === true ? "logos off" : "logos on"], ["Esc", "back"]]
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
    // M2-03 6.3: while a number is being typed the hint line is the entry
    // line and nothing else. It is short on purpose, so the elide-left
    // footer keeps `Esc cancel` visible on the narrowest card.
    if (o.numberEntry && o.numberEntry.active === true) {
      return [["0-9", "digits"], [CHNO_ENTRY_SEP, "sub"], ["Enter", "play"], ["Backspace", "undo"], ["Esc", "cancel"]]
    }
    // M2-13: on the wall h/l move the cursor across a row instead of ringing
    // the scope, because the wall hides the group column. A hint that still
    // said "group" would name an axis the view does not have -- the same
    // mistake M2-09 D6 fixed for the list, in the other direction.
    // The verbs come from the SAME table the keys dispatch on, so the footer
    // cannot describe a movement the handler does not make. That drift is
    // what the 0.8.0 preflight blocked on.
    var list = [["j/k", arrowVerb(o, "v")], ["h/l", arrowVerb(o, "h")],
                ["Enter", "play"], ["Space", "preview"], ["f", "favorite"], ["s", "stop"]]
    // PAUSE LIVE TV. Only while something is playing -- a pause key on an
    // idle guide has nothing to act on and would be a hint that lies. Names
    // the direction, so nobody presses it to find out which way it goes.
    if (o.playing === true) list.push([PAUSE_KEY, o.paused === true ? "resume" : "pause"])
    // M2-05 section 5. Gated the way `0-9` is: a machine with no Hyprland
    // never advertises a key that can only answer "picture in picture needs
    // Hyprland". An absent flag shows it, so a service that predates PiP is
    // not silently stripped of the hint.
    if (o.pipAvailable !== false) list.push(["p", "pip"])
    list.push(["r", "refresh"], ["/", "search"])
    // M2-13: after the action verbs and beside `/ search`, because both keys
    // change what you are LOOKING at rather than acting on the cursor -- and
    // because the footer elides from the left on a narrow card, so Enter,
    // Space, f and s must not be pushed off by a view toggle. Names the view
    // it will go TO, not the one you are in, so the key need not be pressed
    // to find out: the same rule the logos hint follows on Sources.
    list.push([WALL_KEY, o.wall === true ? "list" : "wall"])
    // Gated on the playlist actually having numbers, so an unnumbered source
    // gains no clutter and never advertises a key that does nothing.
    if (o.hasNumbers === true) list.push(["0-9", "channel"])
    list.push([SOURCE_KEYS.open, "sources"])
    return list
  }
  // M2-13. Search mode gets the toggle too, and this is not symmetry for its
  // own sake: the guide OPENS in search mode, the key is handled there
  // (handleSharedKey serves both modes), and a key that works on the screen
  // the user starts on and is advertised only on the other one is a feature
  // nobody finds. It sits before Tab/Esc for the same elide reason as above.
  // On the wall Left/Right moves the cursor, so it stops naming an axis the
  // view does not have.
  var wall = o.wall === true
  if (str(o.query) !== "") {
    return [["Enter", "play"], ["Up/Down", arrowVerb(o, "v")],
            ["Left/Right", wall ? arrowVerb(o, "h") : "narrow"],
            [WALL_KEY, wall ? "list" : "wall"], ["Tab", "keys"], ["Esc", "clear"]]
  }
  return [["Enter", "play"], ["Up/Down", arrowVerb(o, "v")],
          ["Left/Right", arrowVerb(o, "h")],
          [WALL_KEY, wall ? "list" : "wall"], ["Tab", "keys"], ["Esc", "close"]]
}

// M2-09 D6. The h/l ring still does something real on a one-group playlist --
// it rings Recent / Favorites / All -- so the pair is never dropped, only its
// verb stops naming an axis that is not on screen. Gated the way `hasNumbers`
// and `pipAvailable` are: an absent flag reads as the shipped wording, so a
// caller that predates this never loses a hint (engineering rule 10 (dev branch)). `scope`
// and `group` are both five characters, so the hint line does not move by a
// pixel and its existing left-elision is neither fixed nor worsened.
function scopeVerb(opts) {
  return (opts || {}).groupsNarrow === false ? "scope" : "group"
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
// ARCHITECTURE-SOURCES.md (dev branch) section 3 (state records, keys, validation,
// masking, Xtream, reducers) and UX-SOURCES.md (dev branch) 5.4-5.8 / 8.1 (codes,
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
// PAUSE LIVE TV. `c` for "cease", because p is picture-in-picture, s is stop
// and Space is preview -- the three keys a pause would naturally want are all
// taken by things a viewer also does often.
var PAUSE_KEY = "c"

var SOURCE_KEYS = { open: "o", add: "a", xtream: "c", edit: "e", remove: "x", logos: "g", reveal: "Ctrl+R", clear: "Ctrl+U", paste: "Ctrl+V" }
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

// M2-04 / ruling rule 6. The message the logo switch is thrown against.
//
// Turning it ON is a disclosure to hosts the user did not choose, so it is
// confirmed and the confirmation states the count. Turning it OFF discloses
// nothing and is not confirmed at all: a dialog in front of the safe
// direction teaches people to dismiss dialogs.
function confirmLogosMessage(survey) {
  return logoConsentLines(survey).join("\n")
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
  if (cur.mode === "sources" || cur.mode === "confirmRemove" || cur.mode === "confirmLogos") return cur
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

// M2-04. Turning logos ON is confirmed, because it is a disclosure to hosts
// the user did not choose and the ruling requires the count to be stated
// first. Turning them OFF is not: it discloses nothing, and a dialog in front
// of the safe direction teaches people to dismiss dialogs. So this returns
// the state unchanged when `showLogos` is already true, and the caller writes
// the setting directly in that case.
function startLogosConsent(st, showLogos) {
  var cur = copyGuide(st)
  if (cur.mode !== "sources" || showLogos === true) return cur
  cur.mode = "confirmLogos"
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
    CHANNEL_ID_SCHEME: CHANNEL_ID_SCHEME,
    CHANNEL_ID_SCHEME_LEGACY: CHANNEL_ID_SCHEME_LEGACY,
    normalizeIdText: normalizeIdText,
    nameIdKey: nameIdKey,
    suffixIds: suffixIds,
    channelIds: channelIds,
    channelIdRemap: channelIdRemap,
    remapStateIds: remapStateIds,
    remapChannelIds: remapChannelIds,
    channelId: channelId,
    indexById: indexById,
    findByUrl: findByUrl,
    primaryGroup: primaryGroup,
    prepareChannels: prepareChannels,
    // ---- channel numbers (M2-03)
    MAX_CHNO_MAJOR: MAX_CHNO_MAJOR,
    MAX_CHNO_MINOR: MAX_CHNO_MINOR,
    MAX_CHNO_LABEL: MAX_CHNO_LABEL,
    CHNO_SEPARATORS: CHNO_SEPARATORS,
    CHNO_ENTRY_SEP: CHNO_ENTRY_SEP,
    CHANNEL_ORDERS: CHANNEL_ORDERS,
    CHNO_FIELDS: CHNO_FIELDS,
    chnoRawOf: chnoRawOf,
    parseChno: parseChno,
    chnoOf: chnoOf,
    buildChnoIndex: buildChnoIndex,
    chnoIdAt: chnoIdAt,
    chnoEntryKey: chnoEntryKey,
    resolveChno: resolveChno,
    chnoUnambiguous: chnoUnambiguous,
    channelByNumber: channelByNumber,
    channelOrderOf: channelOrderOf,
    orderChannels: orderChannels,
    isNumericQuery: isNumericQuery,
    isNumberEntryKey: isNumberEntryKey,
    numberEntry: numberEntry,
    pushNumberKey: pushNumberKey,
    popNumberKey: popNumberKey,
    closeNumberEntry: closeNumberEntry,
    numberKeyStep: numberKeyStep,
    numberPopStep: numberPopStep,
    numberCommitStep: numberCommitStep,
    chnoCommitLabel: chnoCommitLabel,
    cancelNumberEntry: cancelNumberEntry,
    chnoColumnUnits: chnoColumnUnits,
    chnoStatus: chnoStatus,
    CHNO_CHORD_MASK: CHNO_CHORD_MASK,
    numberKeyAction: numberKeyAction,
    chnoCommitPlan: chnoCommitPlan,
    matchRank: matchRank,
    favoriteSet: favoriteSet,
    filterChannels: filterChannels,
    groupChannels: groupChannels,
    groupScopeId: groupScopeId,
    isGroupScope: isGroupScope,
    isPinnedScope: isPinnedScope,
    scopeName: scopeName,
    scopeSurface: scopeSurface,
    scopeEntries: scopeEntries,
    channelsForScope: channelsForScope,
    channelsInGroup: channelsInGroup,
    effectiveScope: effectiveScope,
    moveScope: moveScope,
    scopeIndex: scopeIndex,
    columnAnchor: columnAnchor,
    fallbackScope: fallbackScope,
    requestedScope: requestedScope,
    initialScope: initialScope,
    cursorFor: cursorFor,
    scopeLabel: scopeLabel,
    revealOffset: revealOffset,
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
    zapStep: zapStep,
    zapSkipNotice: zapSkipNotice,
    rowIndexOfId: rowIndexOfId,
    placeMark: placeMark,
    placeToRestore: placeToRestore,
    PLACE_TTL_SEC: PLACE_TTL_SEC,
    ZAP_MAX_SKIP: ZAP_MAX_SKIP,
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
    failedAfterHealthy: failedAfterHealthy,
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
    boolSetting: boolSetting,
    clampInt: clampInt,
    clampSetting: clampSetting,
    settingsFrom: settingsFrom,
    parseFailed: parseFailed,
    normalizeFailed: normalizeFailed,
    prunedFailed: prunedFailed,
    knownIdSet: knownIdSet,
    failedIndex: failedIndex,
    failedDocument: failedDocument,
    failedWhen: failedWhen,
    MAX_FAILED: MAX_FAILED,
    FAILED_TTL_SEC: FAILED_TTL_SEC,
    ownWriteOf: ownWriteOf,
    ownedEntryPatch: ownedEntryPatch,
    OWNED_SETTINGS: OWNED_SETTINGS,
    confirmLogosMessage: confirmLogosMessage,
    logoFetchArgv: logoFetchArgv,
    failedArgv: failedArgv,
    optInSetting: optInSetting,
    logoSurvey: logoSurvey,
    logoConsentLines: logoConsentLines,
    logoFile: logoFile,
    logoSlot: logoSlot,
    logoHaveSet: logoHaveSet,
    logoNamesFrom: logoNamesFrom,
    logoStreamName: logoStreamName,
    wallGeometry: wallGeometry,
    wallStep: wallStep,
    arrowAction: arrowAction,
    wallTile: wallTile,
    WALL_KEY: WALL_KEY,
    WALL_MAX_COLUMNS: WALL_MAX_COLUMNS,
    WALL_PLATE_ASPECT: WALL_PLATE_ASPECT,
    logoColumnShown: logoColumnShown,
    splitLogoUrl: splitLogoUrl,
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
    dirnameOf: dirnameOf,
    playerDirs: playerDirs,
    buildMpvArgv: buildMpvArgv,
    MPV_RESERVED: MPV_RESERVED,
    // ---- detached player (M2-02)
    PLAYER_STASH_SCHEMA: PLAYER_STASH_SCHEMA,
    PLAYER_ORPHAN_GRACE_SEC: PLAYER_ORPHAN_GRACE_SEC,
    PLAYER_GENERIC_FAILURE: PLAYER_GENERIC_FAILURE,
    helperArgv: helperArgv,
    playlistFetchArgv: playlistFetchArgv,
    playlistProbeArgv: playlistProbeArgv,
    playerStartArgv: playerStartArgv,
    playerStopArgv: playerStopArgv,
    playerRestartArgv: playerRestartArgv,
    playerProbeArgv: playerProbeArgv,
    playerPauseArgv: playerPauseArgv,
    playerOrphanCheckArgv: playerOrphanCheckArgv,
    playFork: playFork,
    zapArgs: zapArgs,
    playFailureVerdict: playFailureVerdict,
    replyTarget: replyTarget,
    reconcileVerdict: reconcileVerdict,
    sessionIntentRepair: sessionIntentRepair,
    playForkBlind: playForkBlind,
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
    // ---- picture in picture (M2-05)
    PIP_CLASS: PIP_CLASS,
    PIP_TAG: PIP_TAG,
    PIP_ADDRESS_RE: PIP_ADDRESS_RE,
    PIP_COORD_LIMIT: PIP_COORD_LIMIT,
    PIP_MIN_WIDTH: PIP_MIN_WIDTH,
    PIP_CORNERS: PIP_CORNERS,
    PIP_SNAPSHOT_KEY: PIP_SNAPSHOT_KEY,
    PIP_SNAPSHOT_VERSION: PIP_SNAPSHOT_VERSION,
    PIP_MPV_RESIZE_PROP: PIP_MPV_RESIZE_PROP,
    PIP_TOOLTIP_ON: PIP_TOOLTIP_ON,
    pipExpression: pipExpression,
    pipDispatchArgv: pipDispatchArgv,
    pipDispatchAccepted: pipDispatchAccepted,
    pipAddressSelector: pipAddressSelector,
    pipOptions: pipOptions,
    pipCornerOf: pipCornerOf,
    pipFindWindow: pipFindWindow,
    pipHasTag: pipHasTag,
    pipActive: pipActive,
    pipResolveIntent: pipResolveIntent,
    pipDeriveState: pipDeriveState,
    pipDeriveGate: pipDeriveGate,
    pipFindMonitor: pipFindMonitor,
    pipGeometry: pipGeometry,
    pipBox: pipBox,
    pipSnapshotFor: pipSnapshotFor,
    pipSnapshotClear: pipSnapshotClear,
    pipParseSnapshot: pipParseSnapshot,
    pipPlan: pipPlan,
    pipMpvCommands: pipMpvCommands,
    pipRestoreAutoResize: pipRestoreAutoResize,
    parsePlayerReply: parsePlayerReply,
    pipVerify: pipVerify,
    pipStatusText: pipStatusText,
    pipResultCode: pipResultCode,
    pipKeyRequest: pipKeyRequest,
    listLetterAction: listLetterAction,
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
    epgCoverage: epgCoverage,
    formatEpgLine: formatEpgLine,
    joinParts: joinParts,
    rowDetail: rowDetail,
    rowFailedMeta: rowFailedMeta,
    rowMeta: rowMeta,
    rowNoticeEmphasis: rowNoticeEmphasis,
    TEXT_DIM: TEXT_DIM,
    WCAG_AA_TEXT: WCAG_AA_TEXT,
    CURSOR_INK_TARGET: CURSOR_INK_TARGET,
    cursorInk: cursorInk,
    cursorInkHex: cursorInkHex,
    qmlFill: qmlFill,
    qmlRgb: qmlRgb,
    hexOf: hexOf,
    cursorInkMix: cursorInkMix,
    sectionHeaderAlpha: sectionHeaderAlpha,
    SECTION_HEADER_SEPARATION: SECTION_HEADER_SEPARATION,
    SECTION_HEADER_FLOOR: SECTION_HEADER_FLOOR,
    CAPTION_BASE: CAPTION_BASE,
    CAPTION_FLOOR: CAPTION_FLOOR,
    CAPTION_FLOOR_REGULAR: CAPTION_FLOOR_REGULAR,
    CAPTION_REGULAR_SHORTFALL: CAPTION_REGULAR_SHORTFALL,
    captionAlpha: captionAlpha,
    savedSearchRecord: savedSearchRecord,
    // D-STATE-1: exported so the shared fixture can call the record rule
    // directly, not only through parseState.
    playedRecord: playedRecord,
    savedSearchNotice: savedSearchNotice,
    savedSearchFooter: savedSearchFooter,
    favoriteRemovalNotice: favoriteRemovalNotice,
    favoriteOrigin: favoriteOrigin,
    withoutSavedSearch: withoutSavedSearch,
    withSavedSearch: withSavedSearch,
    savedSearchChannels: savedSearchChannels,
    savedSearchCount: savedSearchCount,
    savedSearchHit: savedSearchHit,
    savedSearchTerms: savedSearchTerms,
    MAX_SAVED_QUERY: MAX_SAVED_QUERY,
    MAX_SAVED_TERMS: MAX_SAVED_TERMS,
    MAX_SAVED_SEARCHES: MAX_SAVED_SEARCHES,
    alphaForContrast: alphaForContrast,
    mixForContrast: mixForContrast,
    relativeLuminance: relativeLuminance,
    contrastRatio: contrastRatio,
    colorOver: colorOver,
    colorMix: colorMix,
    BAR_IDLE_ALPHA: BAR_IDLE_ALPHA,
    TEXT_FULL: TEXT_FULL,
    rowsHaveDetail: rowsHaveDetail,
    groupNamesForHint: groupNamesForHint,
    rowShowsGroup: rowShowsGroup,
    rowAccessibleName: rowAccessibleName,
    elide: elide,
    noMatchesTitle: noMatchesTitle,
    emptyStateAccessibleName: emptyStateAccessibleName,
    groupWordHint: groupWordHint,
    containsAllWords: containsAllWords,
    barGlyph: barGlyph,
    barTooltip: barTooltip,
    barAccessibleName: barAccessibleName,
    guideSurface: guideSurface,
    footerStatus: footerStatus,
    footerHints: footerHints,
    formHints: formHints,
    // ---- sources (M2-01)
    STATE_VERSION: STATE_VERSION,
    PLUGIN_VERSION: PLUGIN_VERSION,
    staleBuild: staleBuild,
    manifestVersion: manifestVersion,
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
    PAUSE_KEY: PAUSE_KEY,
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
    startLogosConsent: startLogosConsent,
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
