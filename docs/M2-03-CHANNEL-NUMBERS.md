# Omarchy IPTV -- Channel numbers and numeric zap (M2-03)

Owner: Software Architect + UI/UX Designer (one document; the feature is too
small to split). Status: v0.1, governs M2-03, rank 2 of the M2 scope decision
(`docs/PRODUCT.md`), shipping in v0.3.0.

Companions, all still authoritative where this document is silent:
`docs/PRODUCT.md` (locked M1 decisions, M2 ranking), `docs/UX.md` (the shipped
guide: IA in 2, keyboard model in 3, wireframes in 4, token spec in 5,
microcopy in 6, a11y in 7), `docs/UX-SOURCES.md` (how a feature extends that:
mode machine in 1.9, keymap in 2, microcopy in 5, decisions in 8),
`docs/ARCHITECTURE.md` (JSON contracts in 5, settings in 6, rulings R1-R13 in
12), `docs/ARCHITECTURE-SOURCES.md` (Model.js contract style in 3, lanes and
tests in 8, reconciliation rulings SR1-SR32).

Conventions are UX.md's and UX-SOURCES.md's:

- Only `Color.*` / `Style.*` tokens. Every number is a `Style.space(n)`
  argument or a `Style.font.<token>` name.
- ASCII everywhere except Nerd Font glyphs, written glyph + codepoint on first
  use. Every glyph below was verified present in the installed
  `/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf` by parsing its
  `cmap` (format 12) and `post` tables; the verified glyph name from the font
  is quoted, not the name the Nerd Font project publishes (section 4.6).
- In running copy `...`, `"x"` and ` - ` are the ASCII stand-ins for the
  strings the code actually emits: `ELLIPSIS` U+2026, `QUOTE_OPEN`/
  `QUOTE_CLOSE` U+201C/U+201D and `SEP` U+00B7 (`Model.js:51-54`).
- "As the guide does" always means the shipped `Guide.qml` / `Model.js` /
  `Service.qml` at v0.2.0, never a proposal.
- `[ASSUMPTION]` marks something that could not be verified without running
  the UI. Section 12 lists every one of them.

The shipped code this design extends (read before implementing):

| Seam | Site | State today |
|---|---|---|
| `tvg-chno` parse | `bin/omarchy-iptv:684-686` | done; `.strip()` only, stored as a string, key omitted when empty |
| Record shape | `bin/omarchy-iptv:669-718` | `chno` optional, not part of `id` |
| Carry into QML | `Model.js:313-314` (`for (var key in src) row[key] = src[key]`) | automatic; `chno` already reaches prepared rows |
| Normalization | -- | **none anywhere** |
| Index | `Service.qml:651` (`Model.indexById`) | id-only |
| Order | `Model.js:481-503`, `bin/omarchy-iptv:802` | playlist order end to end |
| Digit keys | `Guide.qml:749`, `:760` | reserved, explicitly ignored |
| Reserved by UX | `docs/UX.md:274`, `:894` | `0`-`9` reserved for M2, literal in search mode |

---

## 0. Decisions at a glance

| Topic | Decision |
|---|---|
| Normalization | `Model.parseChno` -> `{key, label, sort}`. Leading zeros dropped (`007` == `7`), `.` and `-` both accepted as the subchannel separator and canonicalized to `.`, major 0-99999, minor 0-999, label capped at 7 characters. Anything else is "no number". |
| Where it is computed | `Model.prepareChannels` writes `chnoKey`/`chnoLabel`/`chnoSort` per row (one pass, load time). `Model.buildChnoIndex` builds the lookup + the numeric permutation, called from `Service.applyChannels` beside `Model.indexById` and cached in the same prepared-LRU entry. |
| Duplicates | Within a playlist: the lowest playlist index wins; re-typing the same number while sitting on a match steps to the next one. Across sources: impossible -- only the active source is ever in memory. |
| No numbers at all | `chnoIndex.hasNumbers === false`: no number column, no `0-9 channel` hint, digits answer with one transient (`No channel numbers in this playlist`). Nothing else changes. |
| Entry key set | `0`-`9` start and extend the buffer; `.` (and `,`, the numpad decimal on non-English layouts) adds the subchannel separator; `Backspace` removes one character; `Esc` cancels; `Enter` / `Space` commit and play / preview; any other key commits silently and then does its own job. All in **list mode only**. |
| Commit | A `numberEntryMs` timer (default 1500 ms, restarted on every key) or an unambiguous exact match commits; `Enter`/`Space` commit early **and play**. A commit never plays on its own. |
| Selection semantics | Digits *select*: the cursor follows the buffer live (exact match, else the lowest number with that prefix). This is what makes `101` + `Enter` a one-gesture zap without giving digits a new play meaning. |
| Scope | Lookup is source-global. If the target is outside the current list, the scope moves to `All` (and an active query is cleared) exactly as a search jumps the column to All. `Esc` restores scope, query and cursor. |
| Unknown number | The cursor returns to where entry started and the footer says `No channel 205`. Nothing plays, no notification. |
| Search mode | Digits stay literal (UX.md 8 #17, unchanged). One addition: an all-digit query floats the exact number match to the top of the results. |
| Display | A new right-aligned number slot at the left edge of a channel row, before the favorite slot. Group column entries get no number. The bar prefixes the label with the number. |
| Feedback while typing | A number chip at the top right of the channel list (dialpad glyph + buffer), plus the footer status and a mode-specific hint line. |
| Sorting | New setting `channelOrder` (`playlist` default, `number`). When `number`, the whole channel array is ordered once at load; groups, All, search tie-breaks and the zap ring follow for free. Favorites and Recent keep their own orders. |
| Outside the guide | One new IPC verb `channel(n)` that tunes by number. `play`, `next`, `previous` are unchanged. `status` gains `chno` and `hasNumbers`. No new default keybinding. |
| New settings | `channelOrder` (string), `numberEntryMs` (integer), `barShowChannelNumber` (boolean). |
| Helper | **Unchanged.** `bin/omarchy-iptv` already emits `chno`; no Python lane in this feature. |
| Lanes | Lane A: `Model.js` + `Guide.qml`. Lane B: `Service.qml` + `BarWidget.qml` + `manifest.json` + harness. No shared file. |

---

## 1. Data

### 1.1 What arrives

`bin/omarchy-iptv:684-686`, verbatim:

```python
    chno = attrs.get("tvg-chno", "").strip()
    if chno:
        channel["chno"] = chno
```

So `chno` is `String | undefined`, whitespace-trimmed, otherwise verbatim. The
attribute name is matched case-insensitively (`parse_attrs` lower-cases keys,
`bin/omarchy-iptv:595`) and both quoted and bare forms are accepted
(`_ATTR_QUOTED` / `_ATTR_BARE`, `:578-579`). Only `tvg-chno` is read; no alias.
`Model.prepareChannels` copies it through untouched (`Model.js:313-314`).

Real-world shapes this design must survive, in the order they were observed in
the assets of `docs/QA-ASSETS.md`, `tests/fixtures/` and
`scripts/gen-playlist.py`:

| Input | Source | Decision |
|---|---|---|
| `12` (bare) | `tests/fixtures/attributes.m3u:3`, `qa-attrs.m3u:10` | number 12 |
| `"12"` (quoted) | `scripts/gen-playlist.py:166`, `tests/test_playlist.py:295` | number 12 |
| missing entirely | every iptv-org list (`QA-ASSETS.md`), `gen-playlist.py --profile realistic` | no number |
| `007` | Tvheadend / provider lists | number 7 |
| `7.1`, `2.2` | ATSC-style over-the-air remaps | number 7.1 |
| `8-1` | some Plex / HDHomeRun bridges | number 8.1 |
| duplicate `12` on two rows | `gen-playlist.py:141-145` (the HD/SD twin copies `chno`) | both numbered; the first wins the jump |
| `HD`, `N/A`, `-`, `` | hostile or lazy providers | no number |
| `123456`, `7.1234` | out of range | no number |

### 1.2 `Model.parseChno(raw)`

Pure, ES5, null-safe, no regular expression (a character-code scanner is
cheaper in V4 and the pattern is trivial). Returns a frozen-shape object; it
never throws.

```
parseChno(raw) -> { ok, key, label, sort, major, minor }
```

Algorithm:

1. `s = str(raw)`; strip leading/trailing ASCII space, tab, `\u00a0` and
   `\ufeff` (the same set `Model.sanitizeInput` strips, `Model.js:1549`).
   Strip one leading `#` (a few providers write `#12`).
2. Empty -> `{ ok: false, key: "", label: "", sort: -1, major: -1, minor: -1 }`.
   Every failure returns exactly that object.
3. Scan digits into `major` while `c >= 0x30 && c <= 0x39`. **ASCII digits
   only**: Arabic-Indic `\u0660`-`\u0669`, full-width `\uff10`-`\uff19` and every
   other Unicode decimal are rejected, because the user cannot type them on the
   keys we bind and a channel the user cannot reach must not claim a number.
4. Zero digits consumed, or more than 5 digits consumed, -> failure.
   `major > MAX_CHNO_MAJOR` (99999) -> failure.
5. End of string -> `minor = -1`.
6. Otherwise the next character must be `.` or `-`; anything else -> failure.
   Then 1 to 3 ASCII digits -> `minor`; `minor > MAX_CHNO_MINOR` (999) or a
   trailing character -> failure.
7. `key` = `label` = `String(major)` when `minor < 0`, else
   `String(major) + "." + String(minor)`. **Leading zeros are dropped in both**:
   `007` renders as `7`, because the number the user sees must be the number the
   user types. `07.01` renders as `7.1`.
8. `sort` = `major * 1000 + (minor < 0 ? 0 : minor)`. Maximum 99,999,999, well
   inside the exact-integer range. A bare `7` and a `7.0` collide on `sort`;
   the tie is broken by playlist index, which is deterministic.
9. `label.length > MAX_CHNO_LABEL` (7) is unreachable given 4 and 6; the
   constant exists so the column width formula has a hard bound.

Constants (`Model.js`, next to `SETTING_RANGES`):

```
var MAX_CHNO_MAJOR = 99999
var MAX_CHNO_MINOR = 999
var MAX_CHNO_LABEL = 7
var CHNO_SEPARATORS = ".-"          // accepted on parse
var CHNO_ENTRY_SEP = "."            // canonical, and what the user types
```

Vectors (the shared fixture of section 10.1, `tests/fixtures/chno-cases.json`):

```
"1"        -> 1     sort 1000        "12"    -> 12    sort 12000
"007"      -> 7     sort 7000        "0"     -> 0     sort 0
"  12  "   -> 12                     "#12"   -> 12
"7.1"      -> 7.1   sort 7001        "8-1"   -> 8.1   sort 8001
"07.01"    -> 7.1                    "99999" -> 99999 sort 99999000
"7.999"    -> 7.999 sort 7999        "123456" -> no number (6 digits)
"7.1000"   -> no number              "100000" -> no number (over major cap)
""         -> no number              "HD"     -> no number
"N/A"      -> no number              "-"      -> no number
"12a"      -> no number              "1.2.3"  -> no number
"1e3"      -> no number              "\u0661\u0662"  -> no number (Arabic-Indic)
"\uff11\uff12"  -> no number       " " / null / undefined -> no number
```

### 1.3 Fields on a prepared channel

`Model.prepareChannels` (`Model.js:306-333`) gains three writes inside its
existing single pass, after `row.primaryGroup`:

```
row.chnoKey    String   ""  when the channel has no usable number
row.chnoLabel  String   ""  (today always === chnoKey; a separate field so a
                             future "keep the provider's formatting" ruling is
                             a one-line change, OQ 7)
row.chnoSort   Number   -1  when the channel has no usable number
```

The raw `chno` string stays on the row untouched. Nothing renders it.

Cost: one `parseChno` per channel that *has* a `chno` key; rows without one
short-circuit on the `undefined` check before the scanner runs. See 1.6.

### 1.4 `Model.buildChnoIndex(channels)`

The first persistent non-id index in the project; it is modelled on
`Model.indexById` (`Model.js:253-261`) and lives beside it.

```
buildChnoIndex(channels) -> {
  byKey:       { "101": [i, j, ...] },   // playlist indices, ascending
  order:       [i, ...],                 // every numbered channel, sorted by
                                         // (chnoSort asc, playlist index asc)
  labels:      [ "1", "2", "7.1", ... ], // parallel to `order`, for the prefix scan
  count:       Number,                   // numbered channels
  duplicates:  Number,                   // numbered channels whose key is shared
  maxLabelLen: Number,                   // 0 when there are none
  hasNumbers:  Boolean                   // count > 0
}
```

- One pass to fill `byKey` and collect the numbered indices, then one sort of
  the numbered subset with an integer comparator falling back to the playlist
  index (so the sort is stable without relying on the engine's stability).
- `byKey` values are arrays, in playlist order, so duplicate cycling (2.7) and
  the `1 of 2` copy (6) need no second structure.
- **Empty input, `null`, a non-array**: returns the same object with
  `hasNumbers: false`. Every consumer must tolerate it.

Where it is built (`Service.qml:646-661`): inside the existing `prepared`
object literal, one line after `channelIndex: Model.indexById(channels)`.

```qml
      prepared = { text: text, channels: channels,
                   channelIndex: Model.indexById(channels),
                   chnoIndex: Model.buildChnoIndex(channels),
                   channelsMeta: parsed.meta }
```

That places it inside the 2-entry prepared-LRU keyed on the raw cache text
(`Service.qml:645-657`), so a switch back to a source already seen this session
costs nothing. The assignment block (`Service.qml:659-661`) gains
`root.chnoIndex = prepared.chnoIndex`, `clearSourceData()`
(`Service.qml:1309-1323`) gains `root.chnoIndex = Model.buildChnoIndex(null)`,
and the data block (`Service.qml:145-149`) gains
`property var chnoIndex: Model.buildChnoIndex(null)`.

Every path into `root.channels` funnels through `applyChannels`, reached only
from `channelsFile.onLoaded` (`:1434`) and `onLoadFailed` (`:1438`), so first
load, source switch, timed refresh, manual refresh and an external file change
are all covered with no extra wiring.

**No helper change.** The index is 10-15 ms of JS at 10k channels, paid once per
load, off the guide-open path. Moving it into `channels.json` would change a
frozen contract (ARCHITECTURE.md 5) and add a schema version for no measured
win. Section 10.4 keeps it as the named mitigation if the measurement disagrees.

### 1.5 Duplicates, gaps, and playlists with no numbers

- **Duplicates inside a playlist.** Two channels may legitimately claim `12`
  (an HD/SD pair, or a provider that numbers per group). Both keep their number
  and both render it. `byKey["12"]` is `[i, j]` in playlist order. A jump lands
  on `i`; re-typing `12` while the cursor is already on `i` lands on `j`, and
  again wraps to `i` (2.7). The footer says `Channel 12 - ESPN HD (1 of 2)`.
- **Duplicates across sources.** Not possible. Only one source's
  `channels.json` is loaded at a time (ARCHITECTURE-SOURCES.md D7); the index
  is rebuilt on every `activeCacheDir` change. There is no cross-source number
  space and none is wanted.
- **Gaps** (1, 2, 5, 900) are normal and need no handling: exact lookup is a
  map hit, prefix lookup walks `order`.
- **Partly numbered playlists.** `hasNumbers` is true as soon as one channel
  has a number. Unnumbered rows render an empty number slot (4.2) and are
  unreachable by digits, which is correct: they have no number.
- **No numbers at all** (every iptv-org list, and `gen-playlist.py --profile
  realistic`): `hasNumbers` is false. The number slot collapses to zero width,
  `0-9 channel` is dropped from the footer hints, `channelOrder: number` is
  inert, and the first digit answers with the transient
  `No channel numbers in this playlist` (6.2). Silence would be worse: UX.md
  already advertises the keys.

### 1.6 The 10,000 channel budget

Standing constraint (PRODUCT.md): the overlay opens in under 150 ms with a 10k
cache, and a warm source switch stays inside the same budget
(ARCHITECTURE-SOURCES.md 7; measured 100-130 ms today).

| Work | When | Budget | Note |
|---|---|---|---|
| `parseChno` inside `prepareChannels` | load / switch | <= 5 ms | only rows that have a `chno` key; character scanner, no regex, no allocation on the failure path |
| `buildChnoIndex` | load / switch | <= 15 ms | one pass + one integer sort of the numbered subset; compare with the measured `indexById` 3-6 ms and `prepareChannels` 10-32 ms (ARCHITECTURE-SOURCES.md appendix B) |
| `orderChannels` | load / switch, **only** when `channelOrder === "number"` | <= 5 ms | an O(n) gather over `chnoIndex.order`, never a second sort (5.2) |
| `resolveChno` exact | per digit | <= 0.1 ms | one map hit |
| `resolveChno` prefix | per digit | <= 3 ms | linear scan over `labels` with an early exit on the first hit; the common case (`1` in a 1..1204 plan) exits on the first element |
| cursor move + `positionViewAtIndex` | per digit | <= 2 ms | uniform row heights, so the view computes the position arithmetically; the model is already an integer (`Guide.qml:1855`) |
| guide open | unchanged | < 150 ms | nothing new runs on open; the index is built at load and LRU-cached |

Digit entry deliberately does **not** re-filter: it moves the cursor. The 40 ms
filter debounce (`Guide.qml:174`, threshold 2000 channels) is not on this path.

Worst case is bounded by the shipped `MAX_CHANNELS = 50000` (`Model.js:25`,
mirrored in the helper) exactly as every other per-channel pass is.

---

## 2. Interaction

### 2.1 Where digits are live

**List mode only.** The two-mode model of UX.md 3 is unchanged: the guide opens
in search mode, `Tab` or `/` reaches list mode, and in search mode digits stay
literal query text (UX.md 8 #17). `sources`, `sourceEdit`, `sourceXtream` and
`confirmRemove` ignore digits exactly as today (UX-SOURCES.md 8 #27).

Amendment to UX.md 3.1, replacing the `0`-`9` row:

| Key | Action |
|---|---|
| `0`-`9` | Start or extend the channel-number entry buffer; the cursor follows it live (2.3). |
| `.` / `,` | Subchannel separator, only while the buffer is non-empty and has none yet (`7` `.` `1` -> `7.1`). `,` is accepted because the numpad decimal key emits `,` on several European layouts. |
| `Backspace` | Remove the last character of the buffer. On the last character, cancels entry and restores the cursor. Unbound when no buffer is live (unchanged). |
| `Esc` (buffer live) | Cancel entry: restore scope, query and cursor. Does **not** clear the query and does **not** close the guide. |
| `Enter` (buffer live) | Commit, then the shipped Enter: play the resolved row, close, focus mpv. |
| `Space` (buffer live) | Commit, then the shipped Space: play and keep the guide open. |
| any other key (buffer live) | Commit silently (the cursor stays where the preview put it), then the key does its normal job. |

Everything else in UX.md 3.1 and UX-SOURCES.md 2.1 is untouched.

### 2.2 Conflict audit

Every key this feature claims, checked against `docs/UX.md` 3.1 and 3.2,
`docs/UX-SOURCES.md` 2.1-2.5, `/usr/share/omarchy/shell/Ui/PanelKeyCatcher.qml`
and the exhaustive binding table of `Guide.qml`:

| Key | PanelKeyCatcher | UX.md 3.1 (list) | UX.md 3.2 (search) | UX-SOURCES 2.2 | Verdict |
|---|---|---|---|---|---|
| `0`-`9` | fallback `textKey` only, **event not accepted** (`PanelKeyCatcher.qml:81-83`) | reserved for M2, ignored (`Guide.qml:749`) | literal query text | ignored | free; this is the reservation being cashed in |
| `.` | fallback `textKey`, not accepted | unbound | literal query text | ignored | free |
| `,` | fallback `textKey`, not accepted | unbound | literal query text | ignored | free |
| `Backspace` | not handled at all | unbound | `Util.editsFilter` owns it (search only) | forms only | free in list mode |
| `Enter` / `Space` | `returnRequested` + `activateRequested` (accepted) | play / preview | play | switch / switch-and-stay | **reused, not re-bound**: the buffer commits first, then the shipped action runs unchanged |
| `Esc` | `closeRequested` (accepted) | clear query, else close | clear query, else close | back | **extended**, one step in front of the shipped chain (2.6) |

Nothing is taken from `j/k/h/l`, arrows, `Tab`, `x/X/Delete`, `f`, `s`, `r`,
`o`, `/`, `PgUp/PgDn`, `Home/End`, or any Ctrl/Alt/Meta chord (list mode has
none and R1 forbids adding any). `p` stays free for M2-05 picture in picture,
and `Shift+Enter` stays reserved for it (UX.md 3.1).

**Implementation note that decides correctness, not style.** Match on
`event.text`, never on `Qt.Key_0`..`Qt.Key_9`. The numeric keypad emits the
same key codes with `Qt.KeypadModifier`, and on AZERTY the top-row digits
require Shift. `event.text` is `"1"` in all three cases, so a text match is the
only one that works for every keyboard the plugin will meet. Reject the event
when `Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier` is set; do **not**
reject on `Qt.ShiftModifier`. [ASSUMPTION: verified by reading Qt's key
handling and PanelKeyCatcher, not by typing on a live AZERTY layout -- QA item
N15.]

### 2.3 The entry buffer and the live preview

State (root-local in `Guide.qml`, like `cursorIndex`, `transientText` and
`swallowKey`; **not** inside `root.guide`, whose `cursorIndex` field is already
dead and unread):

```
property var numberEntry: Model.numberEntry()
// { active: false, buffer: "", scopeId: "", query: "", cursorIndex: 0 }
```

`scopeId`, `query` and `cursorIndex` are the snapshot taken when the buffer
went from empty to one character; they are what `Esc` restores.

On every buffer change the guide resolves and moves the cursor:

```
resolveChno(index, buffer, currentChannelIndex) -> {
  kind: "exact" | "prefix" | "none",
  channelIndex: Number,       // -1 for "none"
  key: String, label: String,
  matches: Number,            // channels sharing the resolved key
  ordinal: Number             // 1-based position of channelIndex inside them
}
```

1. `byKey[buffer]` hit -> `exact`. When the set has more than one member and
   `currentChannelIndex` is already one of them, return the **next** member
   (wrapping); otherwise the first.
2. Else the first entry of `labels` (which is in ascending numeric order) whose
   label starts with `buffer` -> `prefix`.
3. Else `none`.

The guide then:

- `exact` / `prefix`: if the channel is in the current list, `selectAbsolute`
  to it. If it is not, `setScope(Model.SCOPE_ALL)` first (clearing an active
  query if one is in the way), then `selectAbsolute`. The column highlight
  moving is the visible feedback, exactly as a search from Favorites jumps the
  column to All (UX.md 2.7).
- `none`: the cursor does not move (it stays on the last successful preview, or
  on the entry snapshot if there never was one). The chip and the footer say so
  immediately; the user can `Backspace` out of the mistake without committing.

Why `All` and not the target channel's own group: in a numbered playlist the
neighbours of channel 101 are 100 and 102, and in `All` they are the adjacent
rows, so `j`/`k` right after a jump behave like channel up/down. Jumping into a
group would scatter them.

**Why a live preview at all.** It is what turns three keystrokes into a
verified selection: by the time the user has typed `101` they have already
*seen* channel 101 highlighted with its name, so `Enter` is a confirmation
rather than a leap. It also makes the prefix rule self-explaining without any
copy.

### 2.4 Buffer limits

- Maximum buffer length is `MAX_CHNO_LABEL` (7). A digit that would exceed it
  is dropped and the timer is **not** restarted (the buffer is already as long
  as any number can be).
- `.` / `,` are rejected when the buffer is empty or already contains a
  separator, and when the separator would push the buffer over the cap.
- `0` is a legal first character: `0` `7` gives `07`, which normalizes to `7`.
  A real channel 0 is reachable by typing `0` and letting the timer commit.
- A digit whose resolution is `none` is still accepted into the buffer (the
  user sees what they typed). Rejecting it silently would make a typo feel like
  a dropped keystroke.

### 2.5 Commit

Four ways, one result:

| Trigger | Behaviour |
|---|---|
| `numberEntryMs` elapses since the last key (default 1500 ms, restarted on every accepted key) | commit, do not play |
| the buffer is an exact match **and** no other label has it as a proper prefix | commit immediately, do not play; this is what makes a 3-digit plan feel instant (`199` in a 1..200 list commits on the last digit) |
| `Enter` | commit, then `activate(false)`: play, close, focus mpv |
| `Space` | commit, then `activate(true)`: play, guide stays open |

A commit, in all four cases:

1. stops the timer and sets `active: false`, `buffer: ""`;
2. leaves the cursor, the scope and the query where the preview put them;
3. shows the transient of 6.2 for `transientMs` (3 s, shipped);
4. on `kind === "none"`: restores the entry snapshot (scope, query, cursor)
   first, shows `No channel <buffer>`, and -- for `Enter` and `Space` --
   **does not play**. Playing whatever happened to be under the cursor after a
   mistyped number is the one genuinely destructive outcome this feature could
   have; it is refused.

A commit never plays by itself. `Enter` and `Space` keep exactly the meanings
UX.md 3.1 gives them, which is why this feature adds no new play semantics
anywhere in the guide. OQ 1 records the alternative.

### 2.6 Cancel, and the Esc chain

`Esc` while the buffer is live cancels: the timer stops, the snapshot is
restored (`setScope`, `setQuery`, `selectAbsolute`), and the guide stays
exactly where entry began. It does **not** fall through.

The list-mode `Esc` chain becomes, in order:

1. number buffer live -> cancel it;
2. committed query active -> clear it (shipped);
3. otherwise -> close the guide (shipped).

`Model.onEscape` (`Model.js:682`) is **not** changed: the buffer is root-local,
so `Guide.handleEscape()` checks it and returns before delegating. One fewer
frozen interface to touch.

`Backspace` on the last buffer character is the same cancel (it leaves an empty
buffer, which is by definition inactive).

Closing the guide (`Esc` at step 3, the scrim, `shell.hide`) clears the buffer
and stops the timer, as `close()` already does for `transientTimer`
(`Guide.qml:437`).

### 2.7 Duplicate cycling, worked

Playlist has `ESPN HD` (chno 12, index 40) and `ESPN SD` (chno 12, index 41).

```
type 1, 2      -> preview: exact, matches 2, ordinal 1 -> cursor on ESPN HD
timeout        -> commit; footer: Channel 12 - ESPN HD (1 of 2)
type 1, 2      -> currentChannelIndex is 40, which is in the set
                  -> exact, ordinal 2 -> cursor on ESPN SD
timeout        -> commit; footer: Channel 12 - ESPN SD (2 of 2)
type 1, 2      -> wraps back to ESPN HD
```

Stateless: the cycle is derived from where the cursor already is, so nothing has
to remember a previous press and nothing expires.

### 2.8 Coexistence with search mode

Unchanged: digits typed in search mode are appended to the query
(`Guide.qml:731-734`). A user who wants numeric zap presses `Tab` first, and the
footer hint tells them the keys exist.

One addition, so the feature is reachable from the mode the guide opens in:
**when the query is entirely digits and separators, the exact number match is
floated to the top of the results.** `Model.filterChannels` gains an optional
fifth argument:

```
filterChannels(channels, query, limit, favorites, chnoIndex)
```

When `chnoIndex` is supplied, `Model.isNumericQuery(query)` is true, and
`chnoIndex.byKey[query]` exists, the first matching channel is moved to the head
of `rows` (de-duplicated if the name ranker already produced it); `total` and
`truncated` are unaffected. The four ranking tiers of R4 / UX.md 2.5, the
bucket arithmetic and every existing test are untouched -- this is a head
insertion after the buckets are joined, not a new tier.

`isNumericQuery(text)`: true for `^[0-9]{1,5}([.,][0-9]{1,3})?$` after
trimming, with `,` folded to `.`. Typing `101` in search mode therefore puts
channel 101 first and the name matches (`101 Barz`, `Channel 101 News`) below
it. Typing `4` puts channel 4 first and leaves every `Channel 4` name where the
ranker put it.

### 2.9 Key routing (exact, because the order is not obvious)

`PanelKeyCatcher` is a child of `keyHost` and sees keys first, but its printable
fallback (`PanelKeyCatcher.qml:81-83`) emits `textKey(text)` **without setting
`event.accepted`**, so the event also reaches `keyHost.Keys.onPressed` ->
`handleSharedKey`. Digits therefore arrive twice today. The routing must be:

1. `Guide.qml` `onTextKey` (`:1504-1507`) returns early for keys this feature
   owns, so it neither swallows them nor commits the buffer before
   `handleSharedKey` can extend it:

   ```
   onTextKey: function(text) {
     if (root.inSources) { root.handleSourcesLetter(text); return }
     if (text.charCodeAt(0) < 32 || text.charCodeAt(0) === 127) return
     if (Model.isNumberEntryKey(text)) return   // 0-9 . , handled in handleSharedKey
     root.endNumberEntry(true)
     root.handleListLetter(text)
   }
   ```

   The control-character guard matters: `Backspace` and `Delete` both have a
   one-character `event.text` (`\b`, `\u007f`), so they reach `textKey` today
   and would otherwise commit the buffer before `handleSharedKey` sees them.

2. `handleSharedKey(event)` (`Guide.qml:695`) gains two lines at the top of its
   non-Sources half:

   ```
   if (root.listMode && root.handleNumberKey(event)) return true
   if (root.listMode && root.numberEntryActive) root.endNumberEntry(true)
   ```

   The `root.listMode` guard is what keeps digits literal in search mode;
   `handleSharedKey` is also called from `handleSearchKey` (`Guide.qml:729`),
   and the shipped `Qt.Key_Delete && root.listMode` branch is the precedent.

3. `handleNumberKey(event)` accepts, in order: `Backspace` while active;
   `0`-`9`; `.` / `,` while active. It refuses anything carrying Ctrl, Alt or
   Meta. It returns `false` otherwise.

4. The other five `PanelKeyCatcher` handlers commit first, then do their job:
   `onMoveRequested` and `onTabRequested` and `onDeleteRequested` call
   `root.endNumberEntry(true)`; `onActivateRequested` calls
   `root.commitNumberEntry({ play: true, keepOpen: !enter })` and returns early
   when it resolved to `none`; `onCloseRequested` calls
   `root.handleEscape()`, which cancels (2.6).

That is seven call sites, all within one screen of `Guide.qml:1479-1508` and
`:695-717`.

---

## 3. Zapping by number from outside the guide

### 3.1 What gets a numeric surface, and what does not

| Surface | Decision | Why |
|---|---|---|
| Guide overlay | full digit entry (2) | it has exclusive keyboard focus and a cursor |
| IPC | one new verb `channel(n)` (3.2) | scriptable, bindable, no new UI |
| Bar widget | **no** numeric entry; gestures unchanged | the bar has no keyboard focus and no key handlers at all (`BarWidget.qml` has no `Keys`), and UX.md 3.3 defines its keyboard story as "the global binding plus IPC verbs" |
| A global numeric submap / a new overlay | **no** | it would be a second input surface for a guide that is one keystroke away, and Hyprland submaps are a user's `bindings.lua` concern, not a plugin's |
| Default keybindings for digits | **no** | ten default binds would collide with workspace switching on every Omarchy install; `contrib/bindings.lua` gains commented examples only (3.4) |

### 3.2 The `channel` verb

`IpcHandler` (`Service.qml:1830-1854`) gains one function. The existing seven
verbs (`toggle`, `play`, `stop`, `next`, `previous`, `refresh`, `status`) are
untouched.

```qml
    function channel(n: string): string {
      var found = root.channelByNumber(n)
      if (!found) return JSON.stringify({ ok: false, kind: "channel",
        error: { code: "unknown_chno", message: "no channel " + Model.sanitizeInput(n, Model.MAX_CHNO_LABEL) } })
      root.play(Model.channelId(found), true, "")
      return JSON.stringify({ ok: true, kind: "channel", id: Model.channelId(found),
        chno: found.chnoLabel, name: String(found.name || "") })
    }
```

- Argument is a **string**, matching every other verb's typed signature. It is
  run through `Model.parseChno` first, so `007`, `7-1` and `  12  ` all work
  from a shell.
- Resolution is `Model.channelByNumber(channels, chnoIndex, text)` -> channel or
  `null`, which is `resolveChno` with `currentChannelIndex = -1` (no cycling
  from IPC: a script asking for 12 must get the same channel every time).
  `exact` and `prefix` both tune; `none` is the error.
- Outside the guide there is no cursor, so `channel` **tunes** -- that is the
  numeric zap. It is `play(id, true, "")`, identical to the shipped `play`
  verb's call, so the zap ring falls back to the channel's own group
  (`Model.launchScope`) exactly as it does today.
- Failure is an error object, no notification and no toast: a mistyped
  keybinding must not raise a desktop popup. This follows `play`, whose unknown
  id returns `"unknown"` silently.
- The error message contains only the sanitized number. No URL, no host
  (R12). The whole handler is URL-free by construction, like the rest of the
  block.

Why a new verb rather than teaching `play` to take a number: `play` already has
a two-step resolution (id, then URL, `Service.qml:1841-1846`) and channel ids
are opaque strings. A third step would make `play 101` ambiguous the day a
provider ships `tvg-id="101"`. A separate verb is one line and cannot be
misread.

### 3.3 `status` additions

`Service.statusSummary()` (`:452-472`) emits `nowPlaying` verbatim, so adding
one field to the `nowPlaying` literal (`Service.qml:292-298`) is enough:

```
nowPlaying: { id, name, group, chno, launchedFrom, since }
```

`chno` is `channel.chnoLabel` (`""` when the channel has none). `statusSummary`
also gains one top-level key:

```
hasNumbers: root.chnoIndex.hasNumbers
```

so a script can tell "this playlist is not numbered" from "you asked for a
number that does not exist". README's IPC block gains the verb and one example.

### 3.4 Keybinding guidance

`contrib/bindings.lua` gains commented lines only, in the style of the existing
`next`/`previous` examples:

```lua
-- Numeric zap: pick keys that are free on your machine.
-- o.bind("SUPER + ALT + 1", "IPTV channel 1", "omarchy-shell io.github.rmcdavid.iptv channel 1")
-- Favourites on a numpad, for example, or drive it from a script:
--   omarchy-shell io.github.rmcdavid.iptv channel 101
```

README documents `channel <n>` next to `play <id>` and states that a number is
resolved against the **active source only**.

---

## 4. Display

### 4.1 Where a number appears, and where it does not

| Surface | Decision |
|---|---|
| Channel row | a new right-aligned number slot at the left edge, **before** the favorite slot (4.2) |
| Group column entry | **no number**; the right-aligned channel count stays (4.4) |
| Bar widget, horizontal | prefixes the channel name, protected from elision (4.5) |
| Bar widget, vertical | glyph only, unchanged; the number joins the tooltip |
| Header scope label | unchanged |
| Footer status | carries the buffer while typing and the result after a commit (4.6) |
| Sources rows | unchanged; a source is not a number |

### 4.2 The number slot in a channel row

`[num][fav][name ............................][trail] [until HH:MM]`

Number first is the television and EPG-grid convention, and it puts the digits
flush against the card's left content margin so the column scans as a column.
It is also the smallest diff in `Guide.qml`: only `lead.anchors.left` moves
(from `parent.left` to `numberText.right`), while `nameText`, `detailText` and
`track` keep anchoring to `lead.right`, which is still the name's left edge.

| Property | Value |
|---|---|
| element | a `Text` inside `rowContent`, `anchors.left: parent.left`, `anchors.top: parent.top`, `height: lead.height` |
| width | `root.numberWidth` = `hasNumbers ? Style.space(Model.chnoColumnUnits(chnoIndex.maxLabelLen)) : 0` |
| gap to the favorite slot | `Style.spacing.labelGap`, and `0` when `numberWidth === 0` |
| text | `row.chnoLabel` (empty string when the channel has no number) |
| alignment | `horizontalAlignment: Text.AlignRight`, `verticalAlignment: Text.AlignVCenter` |
| font | `Style.font.body`, `font.family: root.fontFamily` |
| color / opacity | `Color.menu.text` at opacity 0.52; on the cursor row `Color.menu.selectedText` at opacity 0.8 |
| weight | `Font.Normal` always, including the playing row -- the name already carries `Font.Bold` and two bold elements in one row is noise |
| elide | none; `Model.parseChno` caps the label at 7 characters, so it cannot overflow the widest slot |
| `textFormat` | `Text.PlainText` (provider data) |

`Model.chnoColumnUnits(maxLabelLen)`:

```
clamp(maxLabelLen, 1, MAX_CHNO_LABEL) -> n
return Math.max(24, Math.min(56, 8 * n + 8))
```

giving `Style.space(24)` for 1-2 characters, 32 for 3, 40 for 4, 48 for 5 and
56 for 6-7. The width is derived from the **whole source**, not the current
list, so the column does not jump when the scope changes. The name column loses
at most `Style.space(56)` of a `Style.space(960)` card, and only on a playlist
that actually has 5-plus-digit numbers.

Right alignment on the whole label means `7.1` and `12` line up on their last
character rather than on the units digit. That is what every printed TV listing
does and it keeps the mixed case readable.

**No number, numbered playlist**: the slot renders an empty string. Not `-`,
not a dot, not a dimmed `0`: a placeholder in a numeric column reads as a value.
The absence is the information, and 7.2 keeps it out of the accessible name too.

**Favorite hit target.** `Guide.qml:2029-2036`'s lead `MouseArea`
(`width: Math.max(Style.space(28), Style.space(12) + root.leadWidth)`) currently
anchors to the row's left edge. It must re-anchor to `lead` (left edge
`lead.left - Style.space(12)`), or a click on the number would toggle the
favorite. UX.md 7.3's minimum stays satisfied.

Zoomed:

```
 num(32)  lead(24)  name (title, elide) ............ trail(20)  right meta
 |        |         |                                 |          |
 v        v         v                                 v          v
    101   󰓎       Sky Sports Main Event              󰐊         until 21:30
                    Now: Premier League - Next: Match Replay        <- bodySmall, 0.52
                    =========================------------------      <- Style.space(2)

 same list, a channel with no number:
          󰓎       Al Jazeera English                            until 20:30
```

### 4.3 The number chip (digit entry in progress)

A single `Rectangle` + `Row`, child of `listHost`, `z: 5`, visible only while
`numberEntryActive`.

| Property | Value |
|---|---|
| anchors | `top: parent.top`, `right: parent.right`, margins `Style.spacing.md` |
| fill | `Style.normalFillFor(Color.menu.text, Color.accent)` -- the neutral banner fill of UX.md 5.7, not `Color.urgent` |
| radius | `Style.cornerRadius` |
| padding | `Style.spacing.controlPaddingX` / `Style.spacing.controlPaddingY` |
| height | `Math.max(Style.space(34), Style.font.heading + Style.spacing.controlPaddingY * 2)` (the header height token of UX.md 5.2) |
| glyph | dialpad `󰘜` U+F061C, `Style.font.icon`, `Color.menu.text`, opacity 1 |
| gap | `Style.spacing.labelGap` |
| buffer text | `Style.font.heading`, `Color.menu.text`, opacity 1, `Text.PlainText` |
| no-match suffix | ` - no match` in `Style.font.caption` at opacity 0.52, appended inside the same `Row`, shown only when `kind === "none"` |
| animation | none (UX.md 5.8: mode changes flip `visible`) |
| a11y | `Accessible.role: Accessible.AlertMessage`, name `Entering channel number 101` |

It sits over the first row's `until HH:MM` by design; the guide gets it back the
instant entry ends. Top right is where a television puts it, and the bottom
right is occupied by the footer.

### 4.4 The group column

Group entries show their name and a right-aligned channel count today
(`Guide.qml:1706-1746`) and gain **nothing**. A number range (`101-148`) would
be wrong the moment a provider interleaves two groups in one number block, a
first-number prefix would be meaningless on an unnumbered group, and the count
is the more useful number in the same space. The pinned `Sources` row is
likewise unchanged.

The only number-related change to the column is indirect: with
`channelOrder: number` the groups appear in the order of their lowest-numbered
channel, because `Model.groupChannels` walks the array in order (5.2).

### 4.5 The bar widget

Horizontal bar, `showChannelName` on, `barShowChannelNumber` on, playing a
numbered channel:

```
 [ 󰕧 101 Sky Sports Main Ev.. ]
      |<------ Style.space(barLabelMaxWidth) ------>|
```

- The number is a separate `Text` at its natural width, inserted between `icon`
  and `labelHolder`; `labelHolder.anchors.left` re-anchors to it and
  `implicitWidth` (`BarWidget.qml:100`) gains its width. The name `Text` keeps
  `elide: Text.ElideRight` inside the remaining budget, so **the name elides and
  the number never does**.
- `barShowChannelNumber` false, or the playing channel has no number: the
  element is zero-width and the bar is byte-identical to v0.2.0.
- `showChannelName` false and `barShowChannelNumber` true: the bar shows
  `[ 󰕧 101 ]`. This is the useful case on a crowded bar and the reason the two
  settings are independent rather than one.
- Vertical bar: glyph only, unchanged (UX.md 8 #12). The tooltip carries the
  number.

```
idle / not configured / error:   [ 󰔂 ]      (unchanged)
playing, no number:              [ 󰕧 Arte HD ]
playing, number only:            [ 󰕧 101 ]
vertical:                        [ 󰕧 ]     tooltip: Playing 101 - Sky Sports Main Event
```

### 4.6 Glyphs

| Meaning | Glyph | Codepoint | Name in the installed font | Where |
|---|---|---|---|---|
| Channel number entry | 󰘜 | U+F061C | `md-dialpad` | the chip (4.3) |
| Unknown number / alert | 󰀦 | U+F0026 | `md-alert` | shipped (`GLYPHS.alert`) |

`Model.GLYPHS` gains one line, in the shipped style:

```js
  // Channel numbers (M2-03)
  dialpad: "\udb81\ude1c",   // U+F061C nf-md-dialpad   number entry chip
```

The surrogate pair is written as an escape because `Model.js` is ASCII-only
(`scripts/check.sh` gate 6). Verified with
`node -e 'console.log("\udb81\ude1c".codePointAt(0).toString(16))'` -> `f061c`.

No colour carries meaning on its own: the chip is a glyph plus digits, the
no-match state is the word `no match`, the row number is text.

**Honest note on the shipped table.** Parsing the installed font's `post` table
shows that two codepoints in UX.md 5.5 carry different names than documented:
U+F0567 is `md-video` (documented as `nf-md-television_play`) and U+F0503 is
`md-television_guide` (documented as `nf-md-television_off`). Both codepoints
exist and render; only the *names* in the table are wrong. That is a v0.2.0
documentation defect outside this lane -- flagged here, not fixed here.

### 4.7 Wireframes

Proportions as UX.md 4: 96 characters for a `Style.space(960)` card, 20 for the
`Style.space(200)` column, `>` marks the cursor row.

#### 4.7.1 Digit entry in progress (typed `10`, started from `UK | SPORTS`, scope hopped to All)

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Search channels...                                                       All - 1,204 channels |
|                                                                                                |
|  Recent           3 |                                                    +-----------------+   |
|  Favorites        6 |     9  󰓎  BBC Two HD                               |  󰘜  10          |   |
|  All          1,204 |                                                    +-----------------+   |
|                     |>   10  󰓎  BBC Four HD                                        until 21:00 |
|  GROUPS             |>          Now: Storyville - Next: Timeshift                              |
|  UK | SPORTS    142 |>          =================-------------------------------               |
|  UK | ENTERTAIN  96 |                                                                          |
|  UK | NEWS       38 |    11     BBC News                                           until 20:30 |
|  UK | KIDS       24 |           Now: Newscast - Next: The Papers                               |
|  UK | MOVIES     57 |                                                                          |
|  US | NEWS       41 |    12     ESPN HD                                                        |
|  PL | INFORMAC.  19 |                                                                          |
|  ...                |    12     ESPN SD                                                        |
|  ------------------ |                                                                          |
|  󰐑 Sources        3 |                                                                          |
|                                                                                                |
|  󰘜 Channel 10       0-9 digits - . sub - Enter play - Backspace undo - Esc cancel              |
+------------------------------------------------------------------------------------------------+
```

Notes: the column highlight already moved to `All` (the target was outside
`UK | SPORTS`); rows 11 and 12 show the numeric column with the two duplicate
`12` entries visible; the chip overlays the first row's right meta.

#### 4.7.2 A successful jump (committed `101`, transient on screen)

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Search channels...                                                       All - 1,204 channels |
|                                                                                                |
|  Recent           3 |                                                                          |
|  Favorites        6 |   100     Sky Sports News                                    until 21:00 |
|  All          1,204 |           Now: Sky Sports News - Next: Transfer Talk                     |
|                     |                                                                          |
|  GROUPS             |>  101  󰓎  Sky Sports Main Event                         󰐊    until 21:30 |
|  UK | SPORTS    142 |>          Now: Premier League: Arsenal v Spurs - Next: Match Replay      |
|  UK | ENTERTAIN  96 |>          ===============================-------------------------       |
|  UK | NEWS       38 |                                                                          |
|  UK | KIDS       24 |   102     Sky Sports Football                                until 22:00 |
|  UK | MOVIES     57 |           Now: EFL Highlights - Next: Sky Sports News                    |
|  US | NEWS       41 |                                                                          |
|  PL | INFORMAC.  19 |   103     Sky Sports Cricket                                             |
|  ...                |                                                                          |
|  ------------------ |                                                                          |
|  󰐑 Sources        3 |                                                                          |
|                                                                                                |
|  Channel 101 - Sky Sports Main Event   j/k move - Enter play - 0-9 channel - o sources         |
+------------------------------------------------------------------------------------------------+
```

Notes: the chip is gone, the cursor sits on 101 with its numeric neighbours
above and below, the footer shows the commit transient for `transientMs` and
then reverts to the shipped status line. Nothing is playing yet; `Enter` plays.

#### 4.7.3 Unknown number (committed `205`, no channel and no prefix)

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Search channels...                                                 UK | SPORTS - 142 channels |
|                                                                                                |
|  Recent           3 |                                                                          |
|  Favorites        6 |>  101  󰓎  Sky Sports Main Event                         󰐊    until 21:30 |
|  All          1,204 |>          Now: Premier League: Arsenal v Spurs - Next: Match Replay      |
|                     |>          ===============================-------------------------       |
|  GROUPS             |                                                                          |
|  UK | SPORTS    142 |   102     Sky Sports Football                                until 22:00 |
|  UK | ENTERTAIN  96 |           Now: EFL Highlights - Next: Sky Sports News                    |
|  UK | NEWS       38 |                                                                          |
|  UK | KIDS       24 |   103     Sky Sports Cricket                                             |
|  UK | MOVIES     57 |                                                                          |
|  US | NEWS       41 |   104     Sky Sports F1                                                  |
|  PL | INFORMAC.  19 |                                                                          |
|  ...                |                                                                          |
|  ------------------ |                                                                          |
|  󰐑 Sources        3 |                                                                          |
|                                                                                                |
|  No channel 205             j/k move - Enter play - 0-9 channel - o sources                    |
+------------------------------------------------------------------------------------------------+
```

Notes: the scope, the query and the cursor are exactly where entry began -- the
preview never moved, because `205` never resolved. The footer carries the whole
report; no banner, no notification.

While the buffer was still live the chip read `󰘜  205 - no match` and the
footer status read `Channel 205 - no match`.

#### 4.7.4 A playlist with no numbers (any digit pressed)

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Search channels...                                                       All - 1,475 channels |
|                                                                                                |
|  Recent           3 |                                                                          |
|  Favorites        6 |> 󰓎  00s Replay                                               until 21:00 |
|  All          1,475 |>    Movies - Now: Rush Hour - Next: The Italian Job                      |
|  GROUPS             |>    =====================------------------------                        |
|  Animation       62 |                                                                          |
|  Classic         44 |  󰓎  Antenna TV                                               until 20:30 |
|  Comedy          98 |     Classic - Now: The Jeffersons - Next: Good Times                     |
|  Documentary     71 |                                                                          |
|  Entertainment  210 |     Ava Movie                                                            |
|  Kids            55 |     Movies                                                               |
|  ...                |                                                                          |
|  ------------------ |                                                                          |
|  󰐑 Sources        3 |                                                                          |
|                                                                                                |
|  No channel numbers in this playlist   j/k move - Enter play - / search - o sources            |
+------------------------------------------------------------------------------------------------+
```

Notes: no number slot at all (the rows start at the favorite slot, exactly as
v0.2.0 draws them), and the list-mode hint line has no `0-9 channel` pair. The
transient is the only sign the key did anything, and it expires in 3 s.

#### 4.7.5 Narrow card (under `Style.space(720)`, column hidden, entry in progress)

```
+------------------------------------------------------------+
|                                                            |
|  Search channels...                     All - 1,204 chan.. |
|                                                            |
|                                       +-----------------+  |
|   100     Sky Sports News             |  󰘜  10          |  |
|           Now: Sky Sports News        +-----------------+  |
|                                                            |
|>  101  󰓎  Sky Sports Main Event                   󰐊  21:30 |
|>          Now: Premier League: Arsenal v Spurs             |
|>          ==========================------------           |
|                                                            |
|   102     Sky Sports Football                        22:00 |
|           Now: EFL Highlights                              |
|                                                            |
|   103     Sky Sports Cricket                               |
|                                                            |
|  󰘜 Channel 10   ..Enter play - Backspace - Esc cancel      |
+------------------------------------------------------------+
```

Notes: the number slot survives the narrow breakpoint -- it is at most
`Style.space(56)` and it is the whole point of the feature; the group column,
which costs `Style.space(200)`, is what gets hidden (`showColumn`,
`Guide.qml:221`, unchanged). The chip keeps its size and margins. The footer
hints elide left as shipped, so `Esc cancel` is the last thing to go.

---

## 5. Sorting and filtering

### 5.1 The question

UX.md 2.5 and R5 lock playlist order and say, in the same row: *"providers and
Tvheadend order channels deliberately (channel numbers, M2, will follow the
same order)"*. In practice most providers already emit the playlist in number
order, so for them the two orders are identical. Tvheadend and several
Plex/Jellyfin bridges do not: they emit alphabetically with numbers attached,
and there number order is the only order the user wants.

### 5.2 Decision: a setting, defaulting to the shipped behaviour

`channelOrder` (7.1), `"playlist"` (default) or `"number"`.

When `"number"` **and** `chnoIndex.hasNumbers`:

```
orderChannels(channels, order, chnoIndex) -> Array
```

is an O(n) gather, not a sort: `chnoIndex.order` is already the numbered
channels sorted by `(chnoSort, playlist index)`, so the result is
`order.map(i => channels[i])` followed by every unnumbered channel in playlist
order. **Unnumbered channels always come last, never interleaved and never
treated as 0.** When `order !== "number"` or `hasNumbers` is false, the input
array is returned unchanged (identity, no copy), so the default path costs
nothing.

It is applied **once**, in `Service.applyChannels`, to the array assigned to
`root.channels`. The prepared-LRU entry keeps the playlist-order array, so
flipping the setting re-derives without re-parsing:

```qml
    root.channels = Model.orderChannels(prepared.channels, root.channelOrder, prepared.chnoIndex)
```

plus `onChannelOrderChanged: root.applyOrder()`, which re-runs that one line.
`chnoIndex.byKey` holds **playlist** indices, so `resolveChno` returns a
playlist index; the guide maps it to a row through the channel's `id`
(`Model.channelId`), which is order-independent.

Consequences, all deliberate:

| Surface | Effect of `channelOrder: number` |
|---|---|
| `All` | numeric order, then the unnumbered tail |
| A group | numeric order within the group |
| Group column order | groups appear in the order of their lowest-numbered channel, because `Model.groupChannels` walks the array first-seen (`Model.js:407-424`). `Ungrouped` stays forced last. |
| Favorites | **unchanged**: order favorited, oldest first (R5, UX.md 2.5). The user built that order by hand; a setting about the provider's numbering must not rewrite it. OQ 4. |
| Recent | **unchanged**: most recent first, always |
| Search ranking | tiers unchanged (R4); "playlist order inside a tier" becomes "the active order inside a tier" for free, because `filterChannels` walks `channels` |
| Zap ring | follows, because `Model.zapRing` -> `channelsForScope` walks the same array. Bar scroll and IPC `next`/`previous` become true channel-up / channel-down. **This is the strongest reason the setting exists.** |
| `chnoIndex` | unaffected; it is keyed by number, not position |
| Resolution (2.3) | unaffected; the prefix scan always walks `chnoIndex.order`, i.e. numeric order, whatever the display order is |

Default `"playlist"` because an upgrade from v0.2.0 must not silently reorder a
working guide, and because most providers make the setting a no-op anyway.

### 5.3 Filtering

Search filtering is unchanged apart from the numeric head-insertion of 2.8.
Digit entry never filters -- it moves the cursor -- so nothing on the number
path touches `filterChannels`, the 200-row cap (R3) or the 40 ms debounce.

---

## 6. Microcopy

Tone as UX.md 6: sentence case, terse, verbs first, no exclamation marks, no
"please". Every string below belongs in the guide's single `copy` block
(UX.md 5.9) or, for the hint pairs, in `Model.footerHints`.

### 6.1 New labels

| Where | String |
|---|---|
| Number chip, entering | the buffer only, e.g. `101` (with the dialpad glyph) |
| Number chip, no match | `101 - no match` |
| Row number slot | the label, e.g. `101`, `7.1`; empty string when the channel has none |
| Settings label, `channelOrder` | `Channel list order (playlist or number)` |
| Settings label, `numberEntryMs` | `Channel number entry timeout (ms)` |
| Settings label, `barShowChannelNumber` | `Show the channel number in the bar` |

### 6.2 Footer status (left slot)

Inserted at the **top** of the shipped precedence ladder of `Model.footerStatus`
(`Model.js:1428`), above `transient`:

| State | String |
|---|---|
| entry live, resolved | `Channel 10` |
| entry live, resolved, duplicates | `Channel 12 - ESPN HD (1 of 2)` |
| entry live, no match | `Channel 205 - no match` |
| committed, resolved (transient, 3 s) | `Channel 101 - Sky Sports Main Event` |
| committed, resolved, duplicates (transient) | `Channel 12 - ESPN HD (1 of 2)` |
| committed, no match (transient) | `No channel 205` |
| digit pressed, playlist has no numbers (transient) | `No channel numbers in this playlist` |

The `(n of m)` suffix appears only when `m > 1`. The name is the shipped
`row.name`, which `Model.cleanName` has already made safe.

### 6.3 Footer hints (right slot)

`Model.footerHints` gains one branch and one conditional pair.

| Mode / state | Hint line |
|---|---|
| list mode, `hasNumbers` false | unchanged: `j/k move - h/l group - Enter play - Space preview - f favorite - s stop - r refresh - / search - o sources` |
| list mode, `hasNumbers` true | the same, with `0-9 channel` inserted between `/ search` and `o sources` |
| number entry live | `0-9 digits - . sub - Enter play - Backspace undo - Esc cancel` |
| search mode, sources, forms, confirm, empty states | unchanged |

Two things this buys: the always-on hint is gated on the playlist actually
having numbers, so an unnumbered source gains no clutter; and the entry line is
short, so the elide-left footer (`Guide.qml:2770`) keeps `Esc cancel` visible on
the narrowest card. `. sub` is the shortest honest label for the subchannel
separator.

Key names render at opacity 0.7 and verbs at 0.45, as shipped.

### 6.4 Bar tooltip and IPC strings

| Where | String |
|---|---|
| Bar tooltip, playing a numbered channel | `Playing 101 - Sky Sports Main Event` |
| Bar tooltip, playing an unnumbered channel | `Playing Sky Sports Main Event` (unchanged) |
| IPC `channel`, success | `{"ok":true,"kind":"channel","id":"t:sky.uk","chno":"101","name":"Sky Sports Main Event"}` |
| IPC `channel`, failure | `{"ok":false,"kind":"channel","error":{"code":"unknown_chno","message":"no channel 205"}}` |

### 6.5 Notifications

**None.** No event in this feature raises a desktop notification.
`Model.notifyArgv` (`Model.js:1207-1226`) is not touched. An unknown number is a
typo made with the guide open, or a mis-bound key; both are reported where the
user is looking. This follows UX-SOURCES.md 8 #23.

---

## 7. Settings

### 7.1 New manifest keys

Declared in `manifest.json` under `barWidget.defaults` and `barWidget.schema`,
in the shipped order and style; edited with
`omarchy bar set io.github.rmcdavid.iptv <key> <value>`.

| Key | Type | Default | Min / max / step | Validation (`Model.js`, service side) |
|---|---|---|---|---|
| `channelOrder` | string | `"playlist"` | -- | `Model.channelOrderOf(v)`: trim, lower-case; returns `"number"` for exactly `number`, `"playlist"` for everything else including empty, unknown strings and non-strings. Never an error, never a warning -- an unreadable value silently means the safe default. |
| `numberEntryMs` | integer | `1500` | 400 / 5000 / 100 | `Model.clampSetting("numberEntryMs", v)` via the shipped `SETTING_RANGES` + `clampInt` pattern (`Model.js:79-83`, `:1090-1100`) |
| `barShowChannelNumber` | boolean | `true` | -- | `settingOf(entry, k, true) !== false && str(...) !== "false"`, the exact idiom `showChannelName` uses (`Model.js:1108`) |

Schema entries:

```json
      { "key": "channelOrder", "type": "string",
        "label": "Channel list order: playlist or number" },
      { "key": "numberEntryMs", "type": "integer",
        "label": "Channel number entry timeout (ms)",
        "min": 400, "max": 5000, "step": 100, "defaultValue": 1500 },
      { "key": "barShowChannelNumber", "type": "boolean",
        "label": "Show the channel number in the bar", "defaultValue": true }
```

`channelOrder` is a string rather than a boolean `sortByNumber` for the same
reason `mpvArgs` is a string (ARCHITECTURE.md 6): `omarchy bar set` writes
strings by default, users copy examples from the README, and the plugin
contract's schema has only `string | integer | boolean` -- there is no enum
type. A string also leaves room for a future `"name"` without another key.
OQ 3 records the alternative.

### 7.2 Wiring

Each key touches exactly four places, the shipped pattern:

1. `Model.SETTING_RANGES` (`Model.js:79`) -- `numberEntryMs` only.
2. `Model.settingsFrom` (`Model.js:1103-1113`) -- all three.
3. `Service.qml:56-63` -- three `readonly property` lines
   (`channelOrder`, `numberEntryMs`, `barShowChannelNumber`).
4. `manifest.json` -- `defaults` and `schema`.

`Guide.qml` reads `service.numberEntryMs` (with a `1500` fallback when the
service is not ready, matching how it already falls back elsewhere);
`BarWidget.qml` reads its own injected `settings` through
`Model.clampSetting` / `settingOf`, as it already does for `barLabelMaxWidth`
(`BarWidget.qml:35`).

`Service.onChannelOrderChanged` re-runs `applyOrder()` (5.2). The other two need
no handler: `numberEntryMs` is read when the timer is armed, and
`barShowChannelNumber` is a binding.

### 7.3 What is **not** a setting

- The number column's visibility: it follows `chnoIndex.hasNumbers`. A source
  with numbers wants them; a source without them has no column to hide.
- The subchannel separator, the buffer cap, the chip's position, the
  `transientMs` reuse, the auto-commit-on-unambiguous-match rule: named
  constants in one place (UX.md 5.9), unit-tested, not user surface.

---

## 8. Accessibility

### 8.1 Roles and names

Extends UX.md 7.1; every other row of that table is unchanged.

| Surface | `Accessible.role` | `Accessible.name` |
|---|---|---|
| Channel row, numbered | `Accessible.ListItem` | `Channel 101, Sky Sports Main Event` + `, favorite` + `, playing` + `, now <programme> until 21:30` + `, failed` as applicable |
| Channel row, unnumbered | `Accessible.ListItem` | unchanged (no `Channel ,` prefix, no empty slot announced) |
| Number chip | `Accessible.AlertMessage` | `Entering channel number 101`; `Entering channel number 205, no match` |
| Footer status | `Accessible.StaticText` | unchanged binding to `root.footerStatusText`, which now carries the entry and commit strings of 6.2 -- so the commit result is announced through the wiring that already exists |
| Bar widget | `Accessible.Button` | `IPTV, playing channel 101, Sky Sports Main Event`; unchanged when the channel has no number |

`Model.rowAccessibleName(opts)` (`Model.js:1370`) gains one field, `chno`, and
prepends `"Channel " + chno + ", "` when it is non-empty. `Model.barAccessibleName`
(`Model.js:1413-1418`) gains the same treatment. Both stay pure and testable,
which is why the strings live there and not in QML.

The footer **hints** `Text` has no `Accessible.*` today and gains none: it is
`Text.StyledText` full of `<font>` markup, and the accessible channel for
transient information is the footer status, which is already bound.

### 8.2 No colour-only status

Every new state carries a glyph or a word:

- entry in progress: the dialpad glyph + the digits themselves (the chip's
  accent-derived fill is decoration on top of a filled shape that is already
  visible by position and content);
- no match: the words `no match` in the chip and `no match` / `No channel 205`
  in the footer, never a red tint alone;
- a channel's number: plain text in its own column, never a badge whose colour
  means anything;
- a channel with no number: an empty slot plus an accessible name that simply
  omits the number -- the absence is not signalled by colour, dimming or a
  placeholder glyph;
- the playing row keeps its three shipped cues (bold name, play glyph, footer
  text); the number is not one of them and is not bolded.

### 8.3 Ergonomics

- `numberEntryMs` is user-configurable (7.1) with a 5,000 ms ceiling precisely
  so a slower typist is not forced into a 1.5 s window. This is the main reason
  it is a setting rather than a constant.
- Entry is fully reversible with one key (`Backspace`) and abandonable with one
  key (`Esc`), and a commit never plays, so a mistyped number costs nothing.
- Hit targets: the number slot is display-only and has no `MouseArea`; the
  favorite hit target keeps its `Style.space(28)` minimum (4.2).
- Wheel and mouse behaviour in the guide and on the bar are unchanged.

---

## 9. Technical design

### 9.1 `Model.js` (Lane A provides, Lane B consumes; frozen)

All pure, ES5, `var`-only, null-safe, ASCII-only, each preceded by a two-to-four
line `//` comment citing `M2-03` and the governing section, listed in
`module.exports` (`Model.js:2864-3094`) under one new banner
`// ---- channel numbers (M2-03)`.

Constants: `MAX_CHNO_MAJOR = 99999`, `MAX_CHNO_MINOR = 999`,
`MAX_CHNO_LABEL = 7`, `CHNO_SEPARATORS = ".-"`, `CHNO_ENTRY_SEP = "."`,
`CHANNEL_ORDERS = ["playlist", "number"]`, `GLYPHS.dialpad`,
`SETTING_RANGES.numberEntryMs = { def: 1500, min: 400, max: 5000 }`.

| Function | Returns |
|---|---|
| `parseChno(raw)` | `{ ok, key, label, sort, major, minor }` (1.2) |
| `buildChnoIndex(channels)` | `{ byKey, order, labels, count, duplicates, maxLabelLen, hasNumbers }` (1.4) |
| `resolveChno(index, buffer, currentChannelIndex)` | `{ kind, channelIndex, key, label, matches, ordinal }` (2.3) |
| `channelByNumber(channels, index, text)` | channel or `null`; `resolveChno` with no cycling, after `parseChno` on the argument (3.2) |
| `orderChannels(channels, order, index)` | array; identity unless `order === "number" && index.hasNumbers` (5.2) |
| `channelOrderOf(value)` | `"playlist"` \| `"number"` (7.1) |
| `isNumericQuery(text)` | Boolean (2.8) |
| `isNumberEntryKey(text)` | Boolean; true for `0`-`9`, `.`, `,` (2.9) |
| `numberEntry()` | `{ active: false, buffer: "", scopeId: "", query: "", cursorIndex: 0 }` |
| `pushNumberKey(entry, text, ctx)` | `{ entry, changed }`; appends a digit or the separator under the rules of 2.4; `ctx` carries `{ scopeId, query, cursorIndex }` for the snapshot taken on the first key |
| `popNumberKey(entry)` | new entry; inactive when the buffer empties |
| `cancelNumberEntry(entry)` | a fresh inactive entry |
| `chnoColumnUnits(maxLabelLen)` | Number of `Style.space` units (4.2) |
| `chnoStatus(kind, label, name, matches, ordinal)` | the footer strings of 6.2 |
| `filterChannels(channels, query, limit, favorites, chnoIndex)` | **existing function, optional 5th argument** (2.8) |
| `rowAccessibleName(opts)` | **existing**, `opts.chno` added (8.1) |
| `barAccessibleName(opts)` | **existing**, `opts.chno` added (8.1) |
| `barTooltip(opts)` | **existing**, `opts.chno` added (6.4) |
| `footerHints(opts)` | **existing**, `opts.numberEntry` + `opts.hasNumbers` added (6.3) |
| `footerStatus(opts)` | **existing**, `opts.numberEntry` added at the top of the ladder (6.2) |
| `settingsFrom(entry)` | **existing**, three keys added (7.1) |
| `prepareChannels(channels)` | **existing**, writes `chnoKey` / `chnoLabel` / `chnoSort` (1.3) |

### 9.2 `Guide.qml` owns

- `property var numberEntry` and the derived `numberEntryActive`,
  `numberBuffer`, `numberResolution` (2.3);
- `Timer { id: numberTimer; interval: root.numberEntryMs; repeat: false }`,
  a third timer beside `rebuildTimer` and `transientTimer`, armed with
  `restart()` on every accepted key;
- `handleNumberKey(event)`, `pushNumberKey(text)`, `popNumberKey()`,
  `previewNumber()`, `commitNumberEntry(opts)`, `cancelNumberEntry()`,
  `endNumberEntry(commit)`;
- the seven routing edits of 2.9 and the `Esc` chain of 2.6;
- the number slot in the row delegate and the re-anchored favorite `MouseArea`
  (4.2);
- the number chip (4.3);
- feeding `numberEntry` and `hasNumbers` into `footerStatus` / `footerHints`,
  and `chno` into `rowAccessibleName`.

It owns **no** number logic: every decision above is a `Model.js` call.

### 9.3 `Service.qml` owns

- `property var chnoIndex`, built in the `prepared` literal
  (`:646-661`), assigned at `:659-661`, reset in `clearSourceData()`
  (`:1310-1312`) (1.4);
- `Model.orderChannels` on assignment plus `onChannelOrderChanged: applyOrder()`
  (5.2);
- the three settings properties (7.2);
- `channelByNumber(text)`, a three-line wrapper over `Model.channelByNumber`;
- `chno` on the `nowPlaying` literal (`:292-298`) and `hasNumbers` on
  `statusSummary()` (`:452-472`) (3.3);
- the IPC `channel(n)` verb (3.2).

No change to `play`, `stop`, `zap`, the mpv path, the helper queue, the probe
path or the cache layout.

### 9.4 `BarWidget.qml` owns

The number `Text` between `icon` and `labelHolder`, the `implicitWidth` term,
`barShowChannelNumber`, and the `chno` field passed into `Model.barTooltip` /
`Model.barAccessibleName` (4.5, 6.4).

### 9.5 The helper does not change

`bin/omarchy-iptv` already parses `tvg-chno` into `chno` and omits the key when
absent (1.1). `channels.json` keeps `version: 1` and its documented shape
(ARCHITECTURE.md 5). No new subcommand, no new flag, no Python edit.

Two things deliberately **not** done, recorded so the next lane does not
re-litigate them: reading alias attributes (`tvg-channel-number`, `channel-number`,
`tvg-num`) and reading XMLTV `<lcn>` (OQ 11), and building the index in Python
(1.4, kept as the mitigation in 10.4).

### 9.6 Lanes and file ownership

Two lanes, zero shared files.

| Lane | Owns | Must not touch |
|---|---|---|
| **A: Model + Guide** | `Model.js` (9.1), `Guide.qml` (9.2), `tests/Model.test.js`, `tests/Model.spec.qml`, `tests/fixtures/chno-cases.json` (author) | `Service.qml`, `BarWidget.qml`, `manifest.json`, `bin/omarchy-iptv`, python tests, harness |
| **B: Service + bar + harness** | `Service.qml` (9.3), `BarWidget.qml` (9.4), `manifest.json`, `tests/test_playlist.py` (one added assertion), `tests/fixtures/qa-chno.m3u` (author), `scripts/dev-harness/shell.qml`, `scripts/dev-harness/run.sh`, `contrib/bindings.lua`, `README.md` + `CHANGELOG.md` at release | `Model.js`, `Guide.qml`, `bin/omarchy-iptv` |

Order, mirroring SR10: Lane A lands `Model.js` + `chno-cases.json` first (a
day-one PR `feat(model): channel number logic`), because Lane B's `Service.qml`
calls it. Lane B lands next. Lane A's `Guide.qml` lands last, against the real
service.

**Cross-lane risk that is not internal to M2-03.** M2-02 (detached player,
rank 1) is being built in parallel and rewrites `Service.qml`'s playback path,
including `play()` and therefore the `nowPlaying` literal this feature extends.
M2-03 Lane B must land **after** M2-02 merges, or rebase onto it; the three
lines involved (`chno:` in `nowPlaying`, `hasNumbers:` in `statusSummary`, the
`channel` verb) are outside the mpv/process rework, so the rebase is mechanical.
Everything else in M2-03 Lane B (`chnoIndex`, settings, ordering) is in the data
block, which M2-02 does not touch. Raised as OQ 12.

### 9.7 Frozen interfaces

1. The section 9.1 function names, argument order and result keys.
2. `service.chnoIndex`, `service.channelOrder`, `service.numberEntryMs`,
   `service.barShowChannelNumber`, `service.channelByNumber(text)`.
3. `nowPlaying.chno` and `statusSummary().hasNumbers`.
4. The IPC `channel(n)` request and both response shapes (3.2).
5. `tests/fixtures/chno-cases.json` case format:
   `[{ "input": "007", "ok": true, "key": "7", "label": "7", "sort": 7000 },
   { "input": "HD", "ok": false }]`.

A change to any of these needs a note in this file and a message to the other
lane before the code lands.

---

## 10. Test plan

### 10.1 Model (node) -- Lane A

`node tests/Model.test.js`

Added to the shipped flat `check(name, actual, expected)` runner (555 checks
today), each name prefixed with the ruling id as the file already does:

- `parseChno` over every vector of 1.2, driven from
  `tests/fixtures/chno-cases.json` in a loop, plus `null` / `undefined` /
  a number / an object / an array.
- `buildChnoIndex`: empty and `null` input; a dense 1..20 plan; gaps; a
  duplicate pair (`byKey` array, `duplicates` count); subchannels sorting
  between their major and the next (`7`, `7.1`, `7.2`, `8`); `maxLabelLen` with
  a mixed plan; `hasNumbers` false when every value is junk.
- `resolveChno`: exact; exact with duplicates and each `currentChannelIndex`
  (including the wrap); prefix picking the **lowest** number (`1` -> 1 not 10;
  `13` with no 13 -> 130 not 139); subchannel prefix (`7` -> 7, then `7.` ->
  7.1); `none`; empty buffer; an index with `hasNumbers` false.
- The auto-commit predicate: `199` in 1..200 is unambiguous, `1` is not,
  `7` is not when `7.1` exists.
- Entry reducers: `pushNumberKey` cap at 7, separator rejected when empty /
  duplicated / over cap, snapshot taken exactly once; `popNumberKey` to empty
  deactivates; `cancelNumberEntry` idempotent.
- `orderChannels`: identity for `"playlist"`; identity when `hasNumbers` false;
  numeric order with the unnumbered tail in playlist order; a duplicate pair
  keeping playlist order between them; input array never mutated.
- `channelOrderOf`: `"number"`, `"Number"`, `" number "`, `"playlist"`, `""`,
  `"alpha"`, `null`, `7`.
- `isNumericQuery` and `isNumberEntryKey` truth tables, including `","`,
  `"7.1"`, `"7,1"`, `"7."`, `"a"`, `""`, `"\b"`.
- `chnoColumnUnits`: 0, 1, 2, 3, 4, 5, 7, 99, `null`.
- `filterChannels` with and without `chnoIndex`: the four shipped tiers
  unchanged; an all-digit query floats the exact match to the head; no
  duplicate row when the ranker already produced it; `total` and `truncated`
  unchanged; the 4-argument call still behaves exactly as today (regression).
- `footerHints`: list mode with and without `hasNumbers`; the entry branch;
  every other mode byte-identical to today.
- `footerStatus`: the entry string beats a transient; the commit transient; the
  `(n of m)` suffix only when `m > 1`; `No channel 205`; the no-numbers string.
- `rowAccessibleName` / `barAccessibleName` / `barTooltip` with and without
  `chno`.
- `settingsFrom`: the three new keys, defaults, clamps at both ends, garbage
  input, and the seven shipped keys unchanged.
- `prepareChannels`: `chnoKey` / `chnoLabel` / `chnoSort` on a mixed fixture;
  a row with no `chno` key gets `""` / `""` / `-1`; the raw `chno` survives; the
  six shipped fields unchanged; input rows not mutated.

### 10.2 Model (Qt engine) -- Lane A

`QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml`

The same `chno-cases.json` vectors plus `buildChnoIndex`, `resolveChno`,
`orderChannels` and `chnoColumnUnits`, to prove the character scanner, the
integer comparator and the numeric coercions behave identically in V4. The
spec's 7-channel fixture (`Model.spec.qml:12-21`) gains `chno` values covering a
duplicate, a subchannel and a missing number.

### 10.3 Helper (python) -- Lane B

`python3 -m unittest discover -s tests`

The helper does not change, so this is a **regression fence**, not new
behaviour. One added test in `tests/test_playlist.py`, parsing the new
`tests/fixtures/qa-chno.m3u`, asserting that every form (bare, quoted,
upper-case attribute, leading zeros, `7.1`, `8-1`, duplicate, non-numeric,
empty, absent) arrives in `channels.json` exactly as written after `.strip()`,
and that the empty and absent cases produce **no `chno` key at all**. The
existing assertions at `tests/test_playlist.py:64,65,102,294-296,438` stay
green untouched.

### 10.4 Performance -- both lanes

```
scripts/gen-playlist.py --channels 10000 --groups 400 --seed 1 \
  --out $SCRATCH/gen-10k.m3u                      # synthetic: every channel numbered 1..N,
                                                  # HD/SD twins share a chno (duplicates)
scripts/gen-playlist.py --profile realistic --channels 10000 --groups 120 --seed 7 \
  --out $SCRATCH/gen-10k-nochno.m3u               # no tvg-chno anywhere (hasNumbers false)
```

A node micro-benchmark in the Lane A PR description (not in the test file)
reporting median of 5 for `prepareChannels`, `buildChnoIndex`, `orderChannels`
and 1,000 `resolveChno` calls against the 10k synthetic cache, compared with the
budgets of 1.6. If `buildChnoIndex` exceeds 15 ms or the switch median exceeds
150 ms, the named mitigation is to emit the sorted index from the helper as a
new top-level key in `channels.json` (which `Model.parseChannels` already
forwards into `channelsMeta` for free, `Model.js:907-914`) -- a Lane B change,
no contract break, no schema bump for readers that ignore unknown keys.

### 10.5 Gate

`scripts/check.sh` -- `omarchy plugin validate`, qmllint at baseline (0 errors),
node, python, the QML spec, and the ASCII check (glyphs in `.qml` only, so
`GLYPHS.dialpad`'s surrogate pair must stay a `\uXXXX` escape in `Model.js`).

### 10.6 Harness scenarios (Lane B adds the verbs, QA runs them)

New verbs on `IpcHandler { target: "harness" }`:

- `number(keys: string)` -- feeds a string one character at a time
  (`0`-`9`, `.`, `,`, `<` meaning Backspace) through the guide's
  `pushNumberKey` / `popNumberKey`;
- `numberState()` -- JSON `{ active, buffer, kind, label, targetName, matches,
  ordinal, scopeId, cursorIndex, query }`;
- `commitNumber(play: bool, keepOpen: bool)`, `cancelNumber()`;
- `chnoIndex()` -- JSON `{ hasNumbers, count, duplicates, maxLabelLen }`,
  URL-free;
- `channel(n: string)` -- passthrough to the service's IPC verb;
- `state()` extended with `numberEntry`, `channelOrder`, `hasNumbers`.

`run.sh` gains `--order number|playlist` (writes `channelOrder` before start)
and `--entry-ms N`.

| # | Scenario | Steps | Expect |
|---|---|---|---|
| N1 | Live preview | 10k numbered fixture, `--open`, `mode` to list, `number 1`, `number 0`, `number 1` | `numberState()` after each: buffers `1`, `10`, `101`, cursor on the lowest match each time; screenshot `chno-entry` |
| N2 | Timeout commit | N1 then wait `entry-ms + 200` | `active false`, cursor still on 101, footer `Channel 101 - <name>`; screenshot `chno-jump` |
| N3 | Enter commits and plays | `number 101`, `commitNumber true false` | the guide closes, `state()` shows `nowPlaying.chno === "101"`, mpv loaded once |
| N4 | Space commits and previews | `number 101`, `commitNumber true true` | guide open, playing cues on row 101 |
| N5 | Backspace | `number 10<` then `numberState()` | buffer `1`, cursor back on channel 1 |
| N6 | Backspace to empty cancels | `number 1<` | `active false`, scope / query / cursor equal to the pre-entry snapshot |
| N7 | Esc cancels | from a group with a query active, `number 101`, `cancelNumber` | scope, query and cursor restored exactly; the guide is still open |
| N8 | Unknown number | `number 20509`, wait | `kind "none"`, cursor unmoved, footer `No channel 20509`, nothing playing |
| N9 | Enter on an unknown number does not play | `number 20509`, `commitNumber true false` | guide stays open, `nowPlaying` unchanged, footer `No channel 20509` |
| N10 | Scope hop | scope `g:Group 003`, `number 1` | `scopeId` becomes `all`, cursor on channel 1 |
| N11 | Subchannel | fixture with `7`, `7.1`, `7.2`; `number 7.1` | exact match on 7.1; `number 7,1` gives the same; `number 7` then timeout gives 7 |
| N12 | Duplicate cycling | `number 12`, commit, `number 12`, commit, `number 12`, commit | ordinals 1, 2, 1; footers `(1 of 2)`, `(2 of 2)`, `(1 of 2)` |
| N13 | Unambiguous auto-commit | 1..200 plan, `number 199` | `active false` before the timer fires |
| N14 | No numbers | `--playlist gen-10k-nochno.m3u`, `number 5` | `chnoIndex().hasNumbers false`, transient `No channel numbers in this playlist`, no number column in the screenshot, `0-9 channel` absent from the hints; screenshot `chno-none` |
| N15 | Keypad and shifted digits | `run.sh key -k KP_1 KP_0 KP_1`, then a shifted top-row digit | buffer `101` both ways (the `event.text` rule of 2.2) |
| N16 | Digits stay literal in search | search mode, `query 101` | the query is `101`, no entry state, exact number match first in the rows |
| N17 | Sort by number | `--order number` on a shuffled numbered fixture | `All` is numerically ordered, unnumbered channels last, group column order follows, `zap(1)` from 101 lands on 102 |
| N18 | Sort flip at runtime | `set channelOrder number` while open | list re-orders without a helper run (journal has no `playlist:` line) |
| N19 | IPC verb | `channel 101`, `channel 20509`, `channel 007` | ok / `unknown_chno` / ok (same channel as `channel 7`); `status` carries `chno` and `hasNumbers`; `omarchy-shell ... status \| grep -c '://'` -> 0 |
| N20 | Bar | playing 101, `widget()` and `tooltip()` | label `101 <name>`, tooltip `Playing 101 - <name>`; with `barShowChannelNumber false` the label is the name alone |
| N21 | Narrow card | resize under `Style.space(720)` during entry | column hidden, number slot and chip still drawn; screenshot `chno-narrow` |
| N22 | Switch keeps it straight | two sources, one numbered one not, `switchSource` both ways | `chnoIndex()` follows the active source; no stale numbers after the swap (the `FileView` R1 rule) |
| N23 | 10k budget | `OMARCHY_IPTV_DEBUG=1`, 5 switches each way with `--order number` | median switch under 150 ms; report median and max |
| N24 | Theme | `omarchy theme set` while the chip is visible | chip, number column and footer re-skin with no restart and no console warning |

### 10.7 What only a live pass on the machine of record can prove

Honest list; none of it is reachable from node, the QML spec or the harness
without a real compositor, a real font and a real keyboard:

1. That the number column is **optically** aligned at real JetBrains Mono
   metrics -- the `8 * n + 8` formula is arithmetic, not measurement, and
   `Style.space()` scaling on this display is the only ground truth (4.2).
2. That the dialpad glyph U+F061C renders as a dialpad rather than a tofu box
   at `Style.font.icon` in the guide's font stack. The cmap says the glyph
   exists; only a screenshot says it *looks* right.
3. That 1500 ms is the right default. It is a judgement calibrated against
   television convention and the fact that a commit is harmless here; only a
   person typing 3- and 4-digit numbers on this keyboard can confirm it.
4. That digit keys survive the real `PanelKeyCatcher` -> `keyHost` chain on a
   live layer-shell surface with exclusive keyboard focus, including the numpad
   and a shifted AZERTY digit (N15 approximates it with `wtype`; a real layout
   switch is the proof).
5. That the chip covering the first row's `until HH:MM` is acceptable in
   practice rather than merely defensible on paper (4.3).
6. That `positionViewAtIndex` per digit does not visibly stutter at 10k rows on
   this GPU.
7. That a real numbered provider exists to test against: **every asset in
   `docs/QA-ASSETS.md` is unnumbered.** The iptv-org lists carry no `tvg-chno`
   at all, so live QA needs either `scripts/gen-playlist.py --profile synthetic`
   served over `file://`, or a real Tvheadend / Jellyfin / Channels DVR M3U the
   product owner supplies. `docs/QA-ASSETS.md` should gain a numbered row.
8. That the bar's number element does not fight `barLabelMaxWidth` on a
   crowded real bar with several widgets (4.5).

---

## 11. Open questions for the product owner

Each with a recommendation, so they can be ruled on in one pass and folded into
this file as `CN1`, `CN2`, ... the way SR1-SR32 were.

| # | Question | Recommendation |
|---|---|---|
| 1 | Does a committed number also **play**, or only select? The PO gate says "digits select, a timeout commits"; this spec reads that as select-only, with `Enter`/`Space` playing. | **Select only.** It keeps `Enter` and `Space` meaning exactly what UX.md 3.1 says, makes a mistyped number free, and still gives one-gesture zap (`101` + `Enter`). If the PO wants TV tuning, add `numberJumpPlays` (boolean, default false) later rather than changing the default. |
| 2 | Is `numberEntryMs` a setting or a named constant? | **A setting** (400-5000, default 1500). The timeout is the one number that decides whether a slow typist gets channel 101 or channels 1, 0 and 1, and that is an accessibility concern, not a style constant. |
| 3 | `channelOrder` as a string, or a boolean `sortByNumber`? | **String.** The schema has no enum type, `omarchy bar set` writes strings, and a string leaves room for `"name"` without another key. |
| 4 | Should **Favorites** follow number order when `channelOrder: number`? | **No.** R5 and UX.md 2.5 make Favorites a hand-built list; a provider-numbering setting must not rewrite the user's own order. Manual reordering is still the backlog item. |
| 5 | The all-digit search-mode ranking tier (2.8) -- keep or cut? | **Keep.** The guide opens in search mode; without it the feature is invisible from the default mode. It is a head insertion, not a new tier, so R4 is untouched. |
| 6 | How should a non-numeric `tvg-chno` (`HD`, `N/A`) render? | **Not at all.** A numeric column that sometimes contains `N/A` reads as a value and is unreachable by digits. The absence is the honest signal. |
| 7 | Leading zeros: display `007` or `7`? | **`7`.** The number you see must be the number you type. `chnoLabel` is kept as a separate field so "preserve the provider's formatting" is a one-line change if the PO disagrees. |
| 8 | Subchannel separator on **input**: `.` only, or `.` and `,`? | **Both**, folded to `.`. The numpad decimal key emits `,` on several European layouts, and a user should not have to know which. On **parse**, both `.` and `-` are accepted (providers use both). |
| 9 | Duplicate numbers: cycle on re-typing (2.7), or always the first match? | **Cycle.** It is stateless (derived from the cursor), it is the only way to reach an HD/SD twin by number, and it costs one argument on `resolveChno`. |
| 10 | Should the IPC `play` verb also accept a number, instead of the new `channel` verb? | **New verb.** `play` already falls back from id to URL; a third numeric step becomes ambiguous the day a provider ships `tvg-id="101"`. |
| 11 | Alias attributes (`tvg-channel-number`, `channel-number`, `tvg-num`) and XMLTV `<lcn>`? | **Defer.** `tvg-chno` is what every asset and every fixture uses; aliases are a one-line helper change whenever a real playlist demands one, and `<lcn>` needs an EPG-to-channel join that is a feature of its own. |
| 12 | Sequencing against M2-02 (detached player), which rewrites `Service.qml`'s `play()` and `nowPlaying`. | **M2-03 Lane B lands after M2-02 merges.** Lane A (`Model.js`, `Guide.qml`) can start immediately and conflicts with nothing. The rebase is three lines (9.6). |
| 13 | `docs/QA-ASSETS.md` has no numbered playlist. Should the PO supply a real one (Tvheadend / Jellyfin / Channels DVR export), or is the synthetic generator enough for the live pass? | **Supply one if it exists**, otherwise accept `gen-playlist.py --profile synthetic` over `file://` and record the gap. A synthetic plan (dense 1..N) cannot show what real provider numbering looks like: gaps, 4-digit blocks per category, and subchannels. |
| 14 | Should the guide expose "jump to the next/previous **number**" keys (channel up/down inside the guide, independent of the list order)? | **No.** With `channelOrder: number` that is exactly `j`/`k`, and with `playlist` the user asked for playlist order. Adding a second pair of movement keys for one setting's sake is surface for nothing. |

---

## 12. Every `[ASSUMPTION]` in this document

Collected so QA can convert each one into a pass or a defect rather than
hunting for them.

| # | Assumption | How it gets settled |
|---|---|---|
| A1 | Matching digits on `event.text` (not `Qt.Key_0`..`Qt.Key_9`) makes the numpad and shifted AZERTY digits work. Derived from reading `PanelKeyCatcher.qml:48-84` and Qt's key handling, not from typing on a live layout. | N15, then live item 4 |
| A2 | `buildChnoIndex` costs 10-15 ms at 10k. Extrapolated from the measured `indexById` 3-6 ms and `prepareChannels` 10-32 ms (ARCHITECTURE-SOURCES.md appendix B), not measured for this code, which does not exist yet. | 10.4 |
| A3 | `positionViewAtIndex` is O(1) on this `ListView` because row heights are uniform. Read from the delegate's `height: root.rowHeight` binding; not profiled. | N23, live item 6 |
| A4 | The chip at `Style.space(34)` tall with `Style.font.heading` digits is legible over the list without a border. Token arithmetic, not a screenshot. | N1 screenshot, live item 2 |
| A5 | `8 * n + 8` design units is the right number-column width for JetBrains Mono digits at `Style.font.body`. Arithmetic on a monospace assumption. | live item 1 |
| A6 | 1500 ms is a comfortable inter-digit timeout. Judgement against television convention plus the fact that a commit here is harmless. | live item 3 |
| A7 | No real playlist in the project's asset list is numbered, so the live pass needs a supplied or generated one. Verified against `docs/QA-ASSETS.md` and every fixture (only two bare `tvg-chno=12` lines exist in the whole tree), but not against the PO's own provider. | OQ 13 |
