# Omarchy IPTV -- UX specification

Owner: UI/UX Designer. Status: v0.1, governs milestone M1. Companion to
`docs/PRODUCT.md` (locked decisions, US1-US8) and
`docs/OMARCHY-PLUGIN-CONTRACT.md` (plugin facts).

Everything visual in this document is expressed in Omarchy tokens
(`Color.*`, `Style.*`) and Nerd Font glyphs. Where a number appears it is a
`Style.space(n)` argument or a `Style.font.<token>` name, never a raw pixel
value. All measurements were taken from the shell code on this machine
(`/usr/share/omarchy/shell/`, Omarchy 4.0.3).

Typography in this file is ASCII. Omarchy's own strings use a few non-ASCII
characters; when a string below is marked with `...`, `"x"`, or ` - ` between
fragments, the implementation must use the real codepoints Omarchy uses:

| Written here | Use this codepoint | Where Omarchy uses it |
|---|---|---|
| `...` (three dots) | U+2026 HORIZONTAL ELLIPSIS | "Search clipboard..." placeholder |
| `"x"` (straight quotes around a query) | U+201C / U+201D | "No matches for "x"" |
| ` - ` between fragments | U+00B7 MIDDLE DOT, padded with spaces | media widget "title  -  artist" |
| `>` submenu chevron | U+203A SINGLE RIGHT-POINTING ANGLE QUOTATION | menu rows |

Nerd Font glyphs are written as the glyph plus its codepoint the first time.
All codepoints below were verified present in
`/usr/share/fonts/TTF/JetBrainsMonoNerdFont-Regular.ttf` via `fc-query`.

---

## 1. User research

### 1.1 Personas

**P1 -- "Dag", the self-hoster.** Runs Tvheadend on a NAS; the M3U has 60-90
channels in 5-8 groups and Tvheadend's XMLTV export gives full EPG. Omarchy
is his daily driver; he lives in the terminal and Neovim. Top tasks, in
order: (1) zap between the same 8 channels with the fewest keystrokes,
(2) glance at "what is on now / until when" before switching, (3) stop
playback from the bar without reaching for the mpv window. He never uses
the mouse in the guide. Failure mode he cares about: the guide must not
freeze while Tvheadend restarts.

**P2 -- "Mira", the free-list browser.** Uses iptv-org or a Pluto/Samsung
style public list: 3k-12k channels in 100-300 groups (countries, then
categories), no EPG or a partial one, and a meaningful share of dead
streams. Top tasks: (1) browse by country group, (2) search a partial name
("bbc", "rai"), (3) try a channel, discover it is dead, try the next one
without friction, (4) accumulate a Favorites list that becomes her actual
guide. Failure mode: a 10k-row list that stutters when she types.

**P3 -- "Tomasz", the paid-provider user.** Xtream-style `get.php` M3U with
~8k channels, `xmltv.php` EPG. Group names are provider-shaped
(`UK | SPORTS`, `PL | INFORMACYJNE`). Top tasks: (1) type three letters and
be watching, (2) read now/next and the progress before committing to a
switch, (3) come back to what he watched last night (Recent), (4) later:
type a channel number (M2). Failure mode: an EPG fetch of 40 MB that blocks
the guide from opening.

### 1.2 Observed IPTV behaviors to design for

- **Zapping.** Users switch channels in bursts: 3-6 switches in 30 seconds
  until something sticks. Each switch must be one gesture (Enter, Space, or
  a bar scroll tick), and a failed stream must not cost more than one
  gesture to move past. **Implemented 2026-09-24** (M2-12): zapping steps
  past channels already known dead, bounded and reported.
- **Browsing by group.** Provider lists are only navigable by group; nobody
  scrolls 8k rows. The group context must stay visible while browsing, and
  switching group must not require leaving the list.
- **"What's on now" glance.** With EPG, the decision to switch is made on
  the now/next line and the progress into the current programme, not on the
  channel name.
- **Partial-name search.** Users type the distinctive fragment ("sports",
  "hbo", "4k"), rarely the exact name. Search must be substring based,
  case and diacritic insensitive, and rank prefix matches first.
- **Favorites are the real home screen.** After the first week, 90% of
  sessions start and end in Favorites. The guide opens there.
- **Recents.** "The thing I watched last night" is a distinct task from
  favorites; the last 10 played channels is enough.
- **Dead streams are normal.** Public lists rot. Failure must be reported
  in-context (which channel, when) and must not clear the user's place in
  the list. **Implemented 2026-09-24** (M2-12): the guide is handed back
  with the same query and scope, cursor on the row after the dead one.
  Narrow by design -- only when that channel is the one that failed, and
  only within three minutes, so an ordinary reopen still starts fresh.
- **Huge lists.** 10k channels and 300 groups are the M3U norm, not the
  exception. Every list is virtualized and search results are bounded.

### 1.3 Design principles

1. **Zap in one breath.** Open, three keystrokes, watching: under two
   seconds, never blocked on network. Nothing in the guide waits for a
   fetch; caches render first, refreshes land later.
2. **Favorites are home; everything else is a search away.** The guide
   opens on Favorites when it has entries, with the search line ready.
3. **The column is the map.** The group column is always visible and is the
   only group gesture (h/l). The channel cursor never leaves the list.
4. **Never lie about state, never by color alone.** Loading, cached,
   offline, playing, failed, and favorite are each carried by a glyph or a
   word in addition to any tint.
5. **Theme-native or nothing.** Same card, scrim, radius, border, and
   selected-row treatment as the clipboard manager; only `Color.*` and
   `Style.*` tokens; re-skins live on `omarchy theme set`.

### 1.4 Competitive notes

| Product | Borrow | Avoid |
|---|---|---|
| Hypnotix (Linux Mint, GTK) | Provider/group sidebar with counts; plain channel list. | Mouse-first, no search-as-you-type, embedded player that fights the WM. |
| iptvnator (Electron) | Now/next EPG text inline in the channel row; Favorites and Recent as first-class lists. | Settings sprawl, Electron weight, modal dialogs for everything. |
| TiviMate (Android TV) | The zapping gold standard: preview while browsing, fast group switching, channel numbers (our M2), progress bar under the programme. | D-pad-only interaction model, 10-foot chrome, remote-shaped menus. |
| Kodi PVR | Channel groups as the primary navigation unit; "recently played". | Nested menu depth; nothing is one keystroke away. |
| Jellyfin Live TV | Quiet programme progress bars; clear "until HH:MM" phrasing. | Web grid guide is heavy and not keyboard-first; opens slowly on big lineups. |

---

## 2. Information architecture of the guide

### 2.1 Surfaces

```
Guide overlay (fullscreen scrim + centered card)
  Header ........ search line (placeholder / query) + scope label
  Banner ........ optional one-line status (refresh failed / cached / EPG failed)
  Body
    Group column  Recent, Favorites, All, GROUPS header, one entry per group
    Channel list  rows for the selected column entry, filtered by the query
  Footer ........ left: status (count / updated / now playing); right: key hints
```

### 2.2 Sections in the group column

Order, top to bottom:

1. **Recent** -- last 10 played channels, most recent first, de-duplicated by
   channel URL. Hidden while empty (no row, no gap).
2. **Favorites** -- always present, even when empty (its empty state teaches
   `f`). Order = order the channels were favorited (stable, oldest first).
3. **All** -- every channel in playlist order.
4. **GROUPS** section header (PanelSectionHeader style), then one entry per
   `group-title` in playlist order (first appearance). Channels with no
   group land in a synthetic last group named `Ungrouped`.

Each entry shows its name (elided) and a right-aligned count.

**Default entry on open:** Favorites when it has at least one channel,
otherwise All. The channel cursor starts on the currently playing channel if
it is in the opened list, otherwise on row 0.

### 2.3 How the user moves between groups: the left column with h/l

Chosen: **a persistent left group column; `h` / `Left` moves the column
selection up, `l` / `Right` moves it down.** The channel cursor stays in the
channel list; the column has no independent cursor.

Why this and not the alternatives:

- **Tab cycling** through 100-300 groups is unusable at P2/P3 scale and
  gives no overview. Tab is also reserved by PanelKeyCatcher for a different
  idiom (focus hopping), which we use to hop between the list and search.
- **A `group:` search prefix** is invisible, undiscoverable, and demands
  that the user already know the provider's group naming (`UK | SPORTS`).
- The column costs `Style.space(200)` of a `Style.space(960)` card, keeps
  the user's location visible at all times, maps onto keys PanelKeyCatcher
  already emits as `moveRequested(dx, 0)`, and doubles as the search scope
  facet (2.7). It collapses automatically on narrow screens (5.1).

Wrap-around: `h` on the first entry wraps to the last and vice versa, like
`j`/`k` in the clipboard manager. Changing the group resets the channel
cursor to row 0 (or to the playing channel if it is in the new list).

### 2.4 What a row shows

```
 [lead]  Channel name (title)                   [trail]   until HH:MM
         Group - Now: Programme title - Next: Programme title
         ==========================-------------------------------
```

| Slot | Content | Rules |
|---|---|---|
| lead (`Style.space(24)` wide) | Favorite star, filled | Empty for non-favorites. Clicking the lead slot toggles favorite without playing. |
| name | `tvg-name` or `#EXTINF` title | `Style.font.title`, elide right. Bold (`Font.Bold`) only on the channel that is currently playing. |
| trail (`Style.space(20)` wide) | Playing glyph, or failed glyph | Playing: `ó°` U+F040A. Failed this session: `ó°¦` U+F0026. Otherwise empty. |
| right meta | `until HH:MM` when EPG has a current programme | `Style.font.caption`, opacity 0.52, right aligned. Hidden without EPG. |
| detail line | `Group - Now: X - Next: Y` | `Style.font.bodySmall`, opacity 0.52, elide right. Group segment is omitted when the selected column entry is that group. `Now:`/`Next:` segments are omitted without EPG data. A failed channel shows `Failed HH:MM - Space to retry` in place of the EPG segments. |
| progress | Thin bar, fraction of current programme elapsed | Only with EPG and a current programme. See 5.6. |

Row height: two-line ("detail") rows whenever the detail line has content
for this list (EPG configured, or a mixed list such as Recent / Favorites /
All / search results where the group name is meaningful). Inside a single
group with no EPG configured, rows are single-line. Row heights are in 5.2.

### 2.4b What a tile shows (the channel wall)

`Ctrl+G` presents the same rows as a grid of tiles. It is a **presentation of
the list, not a mode**: same rows, same cursor, same scope, same actions, and
search filters it live. It is not a member of `GUIDE_MODES`.

| Part | Rule |
|---|---|
| Columns | **Capped at four**, never derived from width. Hiding the group column frees ~200 px of the 924 px card and that width is spent on BIGGER TILES, not a fifth column: five columns measured 139 ms against the 150 ms open budget where four is 25 realised delegates at 106 ms. The tile goes from ~170 px to ~225 px. Below four columns' worth of width the count drops rather than the tile shrinking past its floor. |
| Picture | The channel's cached logo, `PreserveAspectFit` inside a 16:9 plate. The corpus median aspect is 1.98 with a spread of 0.31 to 13.62, so no plate shape fits the logos; fitting inside letterboxes the tall ones and pillarboxes the wide ones without cropping either. |
| No picture | The plugin's own television mark (`GLYPHS.tv`), dimmed. **This inverts 2.4's rule for the row deliberately.** In the 22 px row column a placeholder reads as a value, so the absence is the information -- correct there, because the name sits beside it. On a tile the tile IS the row, so an empty tile reads as a missing channel rather than as a channel with no picture. 82 of 1,462 channels on the reference list have no cached file, and on a 27-per-cent-coverage playlist the empty reading is the majority case. With logos OFF every tile is the mark, which is what makes the wall usable on a default install. |
| Name | Always, under the plate, elided right. **The caption is not decoration.** A contact sheet over the 1,380 real cached logos found 32 runs of three or more adjacent channels sharing one logo file -- the largest 28 consecutive NBC affiliates, then Fox 14 and PBS 11, with 148 channels inside a run of four or more. In those runs the name is the only thing that tells two tiles apart; with captions hidden they carry no information at all. |
| Cursor | The selected plate takes the selection fill and border, AND carries the cursor mark of the 2026-09-21 ruling. The mark is not optional here: the selection fill is 8 per cent alpha, which reads on a 52 px row and disappears over a 230 px tile. Measured by looking at the first build of this view. |
| Decorations | The playing glyph and the favourite star top-right of the plate, the failed-alert glyph top-left, in the theme's foreground. Same glyphs and meanings as the row (5.5). All `Accessible.ignored`: the tile's NAME carries them, composed by the row's own `Model.rowAccessibleName`, so a reader hears what the eye sees and hears it once. The wall diverges from the row in one way, deliberately: the row's single trail slot shows play OR alert and suppresses the alert while playing, where the tile has two corners and can show both. |
| Group column | **Hidden.** That is what frees the width, and it is also what lets `h`/`l` be horizontal cursor movement: `PanelKeyCatcher` matches `Key_Left` without checking modifiers and collapses the arrows onto `hjkl`, so a view needing both a cursor axis and a facet axis has no key left to express the second. Changing group means flipping back to the list; search works in both views and is the primary narrowing verb. |

Keys on the wall: `j`/`k` move a whole row keeping the column, `h`/`l` move one
tile through the flat sequence with wrap, `PgUp`/`PgDn` move a page of rows.
**This amends 3.2's arrow rows as well as 3.1's**, and they say so in place --
search mode routes the arrows through its own handler, which is what the 0.8.0
preflight blocked on. All of it is one table, `Model.arrowAction`, which the
two key paths and the footer all dispatch on, so the three cannot drift.
Down from a column the partial last row does not have lands on the last item;
up past the top keeps the column. Everything else is 3.1 unchanged.

**Not a plate colour the theme picks.** 92 per cent of the real corpus carries
transparency and its ink runs both ways -- 42 per cent light and 22 per cent
dark over a 199-file sample -- so no single plate makes every logo visible. The
tile uses the guide's own normal fill, the surface a resting row already sits
on. Per-logo ink classification at fetch time is the real answer and is
deferred, not solved. **MEASURED-ONCE**, 2026-09-25, against the reference
cache.

### 2.5 Sort rules

| List | Order |
|---|---|
| A group / All | Playlist order. Never alphabetize by default: providers and Tvheadend order channels deliberately (channel numbers, M2, will follow the same order). |
| Favorites | Order favorited, oldest first. (Manual reordering is M2.) |
| Recent | Most recently played first; a replay moves the entry to the top. |
| Search results | Rank tiers, then playlist order within a tier: (1) name starts with the query, (2) a word in the name starts with the query, (3) name contains the query, (4) the group carries every term **as whole words**. Favorites sort first inside each tier. Tier 4 changed in ruling SG1; 2.6 says what that costs. |

### 2.6 Search semantics

- Case-insensitive, diacritics folded (`e` matches `e` with any accent),
  whitespace-separated terms are ANDed, each term matched against
  `name + " " + group`.
- **A group is reachable by its WORDS, never by a fragment of one (SG1).** A
  term that appears only in the group half must match a whole word there.
  Without this, a list whose channels all sit in one group had every fragment
  of that group's name match every channel: on a real 3,335-channel list, 25
  queries reported 3,335 matches against as few as 4 real ones, paged 1,533
  irrelevant rows onto the first page, and told the user to keep typing when
  every genuine match already fitted on screen.
  Three costs were measured and accepted rather than discovered later:
  1. **Typing toward a group name passes through a dead zone.** On a one-group
     `United States` list, `unit` and `unite` now match nothing while every row
     on screen prints those words. A bare `No matches` there would be a worse
     lie than the wrong number it replaced, so the empty state names the group
     the user is heading for instead of shrugging.
  2. **A count can grow as you type.** `sport` may report fewer rows than
     `sports`, because the longer query completes a group word. The footer's
     `keep typing` hint no longer implies the number only falls.
  3. **A multi-group list loses some rows it used to show.** Measured at 44
     queries on a real 1,833-channel list. The group column still reaches those
     channels, and one more keystroke restores them.
- Results are bounded to the first 200 matches (the clipboard shows 50, the
  emoji picker 1000). When more exist, the footer says
  `First 200 of 1,240 - keep typing`.
- Filtering runs against the compact JSON cache in memory, in `Model.js`,
  and must stay under one frame for 10k rows; if it cannot, debounce the
  filter by 40 ms, never block typing.

### 2.7 How search interacts with groups

**Rule: typing searches the selected group, or all channels when the
selected entry is Recent, Favorites, or All.**

- Recent and Favorites are pinned lists, small enough to see; they are
  never a search scope. Starting a query while on either moves the column
  highlight to **All** (visible feedback), and clearing the query returns
  the highlight to where it was.
- A real group is a scope: on `UK | SPORTS`, typing `sky` filters that group
  ("find the Sky channels in this long group").
- While a query is active, `h` / `l` still move the column: the column acts
  as a facet over the results. The header's scope label always states the
  scope: `in Sports - 12 matches` or `in All - 87 matches`.
- Zero results inside a group show `No matches for "sky" in Sports` with the
  hint `h/l other groups - Home for All`. (`Home` here is the column, see
  3.1.)

---

## 3. Keyboard map

Two modes, one visible at a time in the header and the footer:

- **Search mode** -- the header shows the query with a caret-less style
  exactly like the clipboard manager. Printable keys edit the query.
- **List mode** -- vim keys and single-letter commands are live. `c` pauses
  or resumes the live stream (2026-09-24). It is offered only while something
  is playing, and the footer names the direction so nobody presses it to find
  out. It is **not rewind**: live streams are not seekable -- measured, 1 of
  22 channels across 21 providers reported itself so -- and the pause is
  bounded by mpv's buffer at roughly five minutes on a typical stream. The
  same action is on the plugin's IPC as `pause`, because it is the first
  thing in this product you want while WATCHING rather than browsing, and the
  guide is closed then; `contrib/bindings.lua` carries the global example.

**The guide opens in search mode with an empty query.** This is the
behavior every other Omarchy overlay has (menu, clipboard, emojis): open,
type, Enter. Arrow keys, PgUp/PgDn, Home/End, Enter, and Esc work from
search mode, so an arrow-key user never needs list mode. A vim user presses
`Tab` once (or `Esc` with an empty query does not leave search mode -- it
closes; use `Tab`). The footer always shows which mode is active and how to
switch.

Implementation note: the search line is a synthetic filter like the
clipboard's (a `Text` showing `filterText`, edited with
`Util.editsFilter` / `Util.editedFilter`), not a focused `Ui.TextField`.
That keeps one key handler, no caret, no focus juggling. Wrap the guide's
content in `PanelKeyCatcher` with `blocked: root.searchMode`; a sibling
`Keys.onPressed` handles search mode. Nothing below conflicts with the keys
PanelKeyCatcher reserves (j/k/h/l, arrows, Enter, Space, Esc, Tab/Shift+Tab,
x).

### 3.1 Guide -- list mode

| Key | Action |
|---|---|
| `j` / `Down` | Next channel; wraps at the end. |
| `k` / `Up` | Previous channel; wraps at the top. |
| `l` / `Right` | Next group column entry (down the column); wraps. |
| `h` / `Left` | Previous group column entry (up); wraps. |
| `PgDn` / `PgUp` | Move the cursor by (visible rows - 1); clamped, no wrap. |
| `End` / `Home` | Last / first channel row. |
| `Enter` | Play the cursor row, close the guide, focus mpv. If the row is already playing: do not reload; just close and focus mpv. |
| `Ctrl+S` (search mode) | Save the current query into Favorites. A MODIFIED key by necessity: `handleSearchKey` routes every bare printable character into the query, so a letter cannot be a command here without breaking typing. The transient carries the ROW COUNT for the terms as typed (`Saved baton rouge - 4 channels`), because the failure mode is a term that matches far more than the user meant; `no tv` saves 75 rows on the list this was designed against. Refusals are spoken too -- already saved, at the cap, nothing to save -- so the keystroke never silently does nothing. |
| `Space` | Play the cursor row and keep the guide open (preview / zapping). The row gains the playing glyph and bold name; the footer updates. |
| `f` / `F` | Toggle favorite on the cursor row. In Favorites the row leaves the list; the cursor stays at the same index (clamped). |
| `x` / `X` / `Delete` | Remove the cursor row from Recent (in Recent) or unfavorite it (in Favorites). No-op elsewhere. Parity with the clipboard's delete. |
| `s` / `S` | Stop playback. No confirmation. Footer shows `Stopped`. |
| `r` / `R` | Refresh playlist and EPG now. Footer shows `Refreshing...` then the result; a desktop notification reports the outcome (6.4). |
| `/` | Enter search mode (query preserved). |
| `Ctrl+G` | Flip between the channel list and the **channel wall** (2.4b). A MODIFIED key by necessity, for the same reason `Ctrl+S` is: it is handled in `handleSharedKey`, which serves search mode too, and the guide OPENS in search mode where every bare printable character is query text. A bare letter would be unreachable on the screen the user starts on. The cursor is shared, so the place survives the flip. **The view persists for the life of the shell session, not per open**: `keepLoaded: true` means the guide item is never destroyed between summons, and `open()` does not reset `wallView`. That is deliberate as of 2026-09-25 -- a view the user chose should be there when they come back, and resetting it every open would make the key feel broken -- but it was DOCUMENTED as the opposite first, and a preflight caught the shipped CHANGELOG saying so. It is not written to disk: a fresh shell starts in the list, so an existing user sees no change until they press the key. |
| `Tab` / `Shift+Tab` | Enter search mode (same as `/`; PanelKeyCatcher emits `tabRequested`). |
| `Esc` | If a committed query is active: clear it and stay in list mode. Otherwise close the guide. |
| `0`-`9` | Reserved for channel numbers (M2). Ignored in M1. |
| `Shift+Enter` | Reserved (M2: play in a floating picture-in-picture window). Ignored in M1. |
| anything else | Ignored. Unbound letters do **not** start a search; only `/` and `Tab` do, so `s`/`f`/`k` never surprise a user mid-word. |

### 3.2 Guide -- search mode

| Key | Action |
|---|---|
| printable (incl. space, `/`, digits, `j`,`k`,`h`,`l`,`f`,`r`,`s`,`x`) | Append to the query; re-filter; cursor to result 0. |
| `Backspace` | Delete one character. `Ctrl+Backspace` deletes a word. `Ctrl+U` clears (all via `Util.editsFilter`). |
| `Down` / `Up` | **In the list**: move the channel cursor; wraps. **On the wall**: move a whole row, keeping the column, and CLAMP at the edges rather than wrapping (`Model.wallStep`). Both are `Model.arrowAction({axis: "v"})`. |
| `Right` / `Left` | **In the list**: next / previous group column entry (search facet, 2.7). **On the wall**: move the cursor one tile through the flat sequence, wrapping -- there is no group column to ring. Both are `Model.arrowAction({axis: "h"})`. |
| `PgDn` / `PgUp` / `Home` / `End` | Same as list mode (there is no caret, so these are free). |
| `Enter` | Play the cursor row (result 0 by default), close the guide, focus mpv. |
| `Ctrl+G` | Flip between the list and the wall, exactly as in list mode (3.1). Listed in BOTH tables on purpose: a key that exists in only one of them is the bug, and this is the table for the screen the guide actually opens on. |
| `Tab` / `Shift+Tab` | Commit the query and switch to list mode; the filtered list stays. |
| `Esc` | If the query is non-empty: clear it (stay in search mode). If empty: close the guide. Identical to the clipboard. |

### 3.3 Bar widget (mouse) and global keys

The bar has no keyboard focus; its keyboard story is the global binding plus
IPC verbs the user may bind.

| Gesture | Action |
|---|---|
| `SUPER + SHIFT + T` (user adds to `bindings.lua`) | Toggle the guide: `omarchy-shell shell toggle io.github.rmcdavid.iptv`. |
| Left click | Open the guide overlay (never a small popup). If it is open, close it. |
| Right click | Stop playback. |
| Middle click | Refresh playlist and EPG. |
| Scroll up / down | Previous / next channel in the zap ring (3.4). One channel per wheel tick; use `Util.wheelSteps` to accumulate. |
| Hover | Tooltip via `bar.showTooltip` (6.3). |

IPC verbs the architect should expose on `IpcHandler { target: "io.github.rmcdavid.iptv" }`
so users can bind them: `toggle`, `stop`, `next`, `previous`, `refresh`,
`play(url)`. No default bindings beyond `SUPER + SHIFT + T`.

### 3.4 The zap ring

Scroll on the bar and `next`/`previous` move within the list the playing
channel was launched from: Favorites if it was played from Favorites, its
group if it was played from a group or from All, the group of the result if
played from a search. Recent is not a zap ring (playing from Recent uses the
channel's group). Wraps at both ends. This is what makes Favorites behave
like a TV's channel-up/down.

---

## 4. ASCII wireframes

Proportions: the card is drawn 96 characters wide for a `Style.space(960)`
card; the group column is 20 characters for `Style.space(200)`. `>` in the
left margin marks the cursor row (painted with
`Color.menu.selectedBackground`, text in `Color.menu.selectedText`). Rows
are two lines tall plus the progress hairline. Glyphs are real Nerd Font
glyphs.

### 4.1 Guide, default (opens on Favorites, search mode, EPG configured)

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Search channels...                                                     Favorites - 6 channels |
|                                                                                                |
|  Recent           3 |                                                                          |
|  Favorites        6 |> ó°  Sky Sports Main Event                              ó°     until 21:30 |
|  All          1,204 |>     Now: Premier League: Arsenal v Spurs - Next: Match Replay           |
|                     |>     ===============================-----------------------------------  |
|  GROUPS             |                                                                          |
|  UK | SPORTS    142 |  ó°  BBC One HD                                                until 20:00 |
|  UK | ENTERTAIN  96 |      Now: EastEnders - Next: The One Show                                |
|  UK | NEWS       38 |      ============---------------------------------------------------      |
|  UK | KIDS       24 |                                                                          |
|  UK | MOVIES     57 |  ó°  Al Jazeera English                                        until 20:30 |
|  US | NEWS       41 |      Now: Newshour - Next: Inside Story                                  |
|  PL | INFORMAC.  19 |      ===========================--------------------------------------    |
|  DE | SPORT      33 |                                                                          |
|  ...                |  ó°  Arte HD                                                   until 21:15 |
|                     |      Now: Karambolage - Next: Tracks                                     |
|                     |      ====----------------------------------------------------------      |
|                     |                                                                          |
|  ó° Sky Sports Main Event - s stop          Enter play - Up/Down move - Left/Right group - Tab keys - Esc close |
+------------------------------------------------------------------------------------------------+
```

Notes: the scrim (`Color.menu.scrim`) fills the screen behind the card; the
card is centered. The top-right scope label and the footer are
`Style.font.caption`. The "GROUPS" label is a `PanelSectionHeader`.

### 4.2 Guide while searching (typed `sky` from Favorites -> scope jumped to All)

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  sky                                                                        in All - 14 matches |
|                                                                                                |
|  Recent           3 |                                                                          |
|  Favorites        6 |> ó°  Sky Sports Main Event                              ó°     until 21:30 |
|  All          1,204 |>     UK | SPORTS - Now: Premier League: Arsenal v Spurs - Next: Match Re |
|                     |>     ===============================-----------------------------------  |
|  GROUPS             |                                                                          |
|  UK | SPORTS    142 |      Sky Sports Football                                      until 22:00 |
|  UK | ENTERTAIN  96 |      UK | SPORTS - Now: EFL Highlights - Next: Sky Sports News           |
|  UK | NEWS       38 |      ==========================================-------------------------  |
|  UK | KIDS       24 |                                                                          |
|  UK | MOVIES     57 |      Sky News                                                 until 21:00 |
|  US | NEWS       41 |      UK | NEWS - Now: Sky News Tonight - Next: The News Hour             |
|  PL | INFORMAC.  19 |      ====================----------------------------------------------   |
|  DE | SPORT      33 |                                                                          |
|  ...                |      Sky Arts                                                  until 21:30 |
|                     |      UK | ENTERTAINMENT - Now: Portrait Artist of the Year - Next: Tate  |
|                     |      ==============================-----------------------------------    |
|                     |                                                                          |
|  ó° Sky Sports Main Event - s stop                Enter play - Up/Down move - Left/Right narrow - Tab keys |
+------------------------------------------------------------------------------------------------+
```

Notes: the group segment now leads the detail line because the list is
mixed. Pressing `Right` twice would highlight `UK | SPORTS` and the scope
label would read `in UK | SPORTS - 9 matches`.

### 4.3 A single row with EPG now/next, zoomed

```
 lead(24)  name (title, elide) ..................... trail(20)  right meta (caption)
 |         |                                          |          |
 v         v                                          v          v
 ó°         Sky Sports Main Event                     ó°          until 21:30
           Now: Premier League: Arsenal v Spurs - Next: Match Replay          <- bodySmall, 0.52
           ===============================-----------------------------------   <- Style.space(2) tall
           ^ fill = Util.alpha(Color.accent, 0.55)    ^ track = Util.alpha(fg, 0.12)
```

Same row, no EPG configured, inside its own group (single-line row):

```
 ó°         Sky Sports Main Event                     ó°
```

Same row after a failed play this session:

```
           Sky Sports Main Event                     ó°¦
           Failed 21:12 - Space to retry
```

### 4.4 Empty state: no playlist configured

Triggers: no playlist has ever been configured, or the active playlist URL
was cleared at runtime, for example `omarchy bar set io.github.rmcdavid.iptv
playlistUrl ""`. Clearing the URL clears the channel list and the group column
with it, so this surface is never drawn over a stale list. Since v0.2.0 this
state is the Sources first-run form, see `UX-SOURCES.md` 1.2.

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Search channels...                                                                            |
|                                                                                                |
|                                                                                                |
|                                                                                                |
|                                             ó°                                                  |
|                                                                                                |
|                                    No playlist configured                                      |
|                                                                                                |
|                       Set your M3U URL or path, then press r to load it:                       |
|                                                                                                |
|              +----------------------------------------------------------------+                |
|              |  omarchy bar set io.github.rmcdavid.iptv playlistUrl <url>     |                |
|              +----------------------------------------------------------------+                |
|                                                                                                |
|                  Optional EPG:  omarchy bar set io.github.rmcdavid.iptv epgUrl <url>           |
|                  Settings live in ~/.config/omarchy/shell.json (entry io.github.rmcdavid.iptv) |
|                                                                                                |
|                                                                                                |
|                                                             r retry - o sources - Esc close    |
+------------------------------------------------------------------------------------------------+
```

Notes: the group column is hidden in this state. The command box is a
`Rectangle` with `Style.normalFillFor(foreground, accent)` fill,
`Style.cornerRadius`, `Style.space(8)` padding, text in `Style.font.body`
at full opacity. The glyph is `Style.font.displayLarge` in
`Color.menu.selectedText` at opacity 0.8 (the clipboard's empty-state
treatment). Clicking the command box copies it with `wl-copy` (mouse
convenience; not required for keyboard users).

### 4.5 Loading (first fetch, no cache yet)

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Search channels...                                                                            |
|                                                                                                |
|                                                                                                |
|                                                                                                |
|                                             ó°                                                  |
|                                                                                                |
|                                     Loading playlist...                                        |
|                                                                                                |
|                                 Fetching from tv.example.net                                   |
|                                                                                                |
|                                                                                                |
|                                                                                                |
|                                                                             Esc close          |
+------------------------------------------------------------------------------------------------+
```

Notes: show host only, never the full URL (Xtream URLs carry credentials in
the query string). No spinner animation; Omarchy has none. When a cache
exists, this screen is never shown: the cached guide renders immediately
and the footer says `Refreshing...`.

### 4.6 Error: fetch failed, cached data available (banner)

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Search channels...                                                     Favorites - 6 channels |
|                                                                                                |
|  ó°¦  Playlist refresh failed (HTTP 503) - showing cached copy from 12:40 - r retry              |
|                                                                                                |
|  Recent           3 |                                                                          |
|  Favorites        6 |> ó°  Sky Sports Main Event                                    until 21:30 |
|  All          1,204 |>     Now: Premier League: Arsenal v Spurs - Next: Match Replay           |
|                     |>     ===============================-----------------------------------  |
|  GROUPS             |                                                                          |
|  ...                |  ...                                                                     |
|                     |                                                                          |
|  1,204 channels - cached 12:40 - offline               Enter play - Up/Down move - Tab keys - Esc close |
+------------------------------------------------------------------------------------------------+
```

Banner spec: height `Style.space(28)`, radius `Style.cornerRadius`, fill
`Util.alpha(Color.urgent, 0.10)`, glyph `ó°¦` in `Color.urgent`, text in
`Color.menu.text` at `Style.font.bodySmall`. The word "failed" carries the
meaning; the tint is decoration. The banner appears with a 140 ms opacity
fade and stays until the next successful refresh. The footer's
`cached HH:MM - offline` is the persistent US7 hint.

Error, no cache at all (empty state, column hidden):

```
                                             ó°

                                   Playlist failed to load

                     HTTP 403 Forbidden from tv.example.net - check playlistUrl

                                    r retry - Esc close
```

### 4.7 "Now playing" affordance inside the guide

Three coordinated cues, all present at once:

```
  row:     ó°  Sky Sports Main Event                              ó°     until 21:30
           ^ name is Font.Bold                                   ^ playing glyph in the trail slot

  footer:  ó° Sky Sports Main Event - s stop          (left side of the footer, Style.font.caption)

  column:  no change (the column never highlights on playback)
```

- `Enter` on this row closes the guide and focuses mpv without reloading.
- `s` stops; the row loses bold + glyph, the footer reads `Stopped` for 3 s
  then returns to the channel count.
- After `Space` on another row, the cues move to that row instantly.

### 4.8 Bar widget

Horizontal bar (`Style.bar.sizeHorizontal` tall). The icon sits in a
`BarIconButton` (slot `Style.bar.iconSlot`, glyph `Style.bar.iconFont`);
the label is a `Text` in `Style.font.body` clipped to a max width.

```
idle, ready (dimmed glyph, no label):          [ ó° ]

not configured (dimmed glyph, tooltip):        [ ó° ]      tooltip: "IPTV - no playlist configured"

playing (glyph + label, elided at max width):  [ ó°§ Sky Sports Main Ev.. ]
                                                  |<-- Style.space(180) -->|

playing, short name:                           [ ó°§ Arte HD ]

error, not playing (television-off glyph):     [ ó° ]      tooltip: "IPTV - playlist error, open the guide"

refreshing (any state; tooltip only):          [ ó° ]      tooltip: "IPTV - refreshing playlist..."
```

Vertical bar (`Style.bar.sizeVertical` wide): icon only, label never shown,
the channel name lives in the tooltip. Same three glyphs.

```
 +----+
 | ó°§ |   tooltip: "Playing Sky Sports Main Event"
 +----+
```

---

## 5. Visual spec (tokens only)

### 5.1 Card

| Property | Value |
|---|---|
| width | `Math.min(Style.space(960), panel.width - Style.gapsOut * 2)` |
| height | `Math.min(Style.space(620), panel.height - Style.gapsOut * 2)` |
| position | `anchors.centerIn: parent` (the clipboard's centering; no frozen-top behavior, the card never resizes while open) |
| background | `Color.menu.background` |
| border | `Border.surfaceSpec("menu", "border", Color.menu.border, Math.max(1, Style.space(2)))` -- identical to clipboard |
| radius | `Style.cornerRadius` |
| padding | `Style.spacing.panelPadding` |
| scrim | full-screen `Rectangle` in `Color.menu.scrim`; click on the scrim closes |
| layer | `WlrLayer.Overlay`, `WlrKeyboardFocus.Exclusive`, `ExclusionMode.Ignore`, namespace `omarchy-iptv` |
| narrow screens | when the card width would be under `Style.space(720)`, hide the group column; the header scope label becomes the only group indicator and `h`/`l` still work |

### 5.2 Layout metrics

| Element | Value |
|---|---|
| header height | `Math.max(Style.space(34), Style.font.title + Style.spacing.controlPaddingY * 2)` (clipboard) |
| content spacing (header -> banner -> body -> footer) | `Style.spacing.md` |
| banner height | `Style.space(28)` |
| group column width | `Style.space(200)`, plus a `Style.normalBorderWidth` divider in `Util.alpha(Color.menu.border, 0.28)` (the clipboard's preview divider) and `Style.spacing.panelPadding` gap before the list |
| group entry height | `Math.max(Style.space(32), Style.font.body + Style.spacing.controlPaddingY * 2)` |
| group entry padding | left/right `Style.space(10)` |
| GROUPS header | `PanelSectionHeader` (caption, bold, `Qt.darker(fg, 1.4)`), `Style.space(10)` above |
| detail row height | `Math.max(Style.space(52), Style.font.title + Style.font.bodySmall + Style.space(2) + Style.spacing.rowPaddingX * 2)` |
| single-line row height | `Math.max(Style.space(38), Style.font.title + Style.spacing.rowPaddingX * 2)` |
| row spacing | `Style.space(4)` (clipboard) |
| row inner margins | left `Style.space(12)`, right `Style.space(12)`, top/bottom `Style.space(8)` (clipboard) |
| lead slot | `Style.space(24)` wide, glyph centered |
| trail slot | `Style.space(20)` wide, glyph centered, `Style.space(8)` gap to the right meta |
| footer height | `Math.max(Style.space(20), Style.font.caption + Style.space(6))` |
| scroll edge fades | the menu's top/bottom gradient scrims, `Style.space(28)` tall, `Color.menu.background` to transparent, opacity tracking hidden distance |

### 5.3 Typography (font family is always `Style.font.menuFamily`)

| Element | Token | Weight / opacity |
|---|---|---|
| Search line (query or placeholder) | `Style.font.heading` | opacity 1 with a query, 0.58 for the placeholder (clipboard) |
| Header scope label (right) | `Style.font.caption` | opacity 0.52 |
| Banner text | `Style.font.bodySmall` | opacity 1 |
| Group entry name | `Style.font.body` | selected entry: `Color.menu.selectedText`, others `Color.menu.text` |
| Group entry count | `Style.font.caption` | opacity 0.7, right aligned (was 0.45, ruling SG2) |
| GROUPS section label | `PanelSectionHeader` defaults | -- |
| Channel name | `Style.font.title` | `Font.Normal`; `Font.Bold` only when playing |
| Detail line | `Style.font.bodySmall` | opacity 0.52 (menu detail) |
| Right meta `until HH:MM` | `Style.font.caption` | opacity 0.52 |
| Lead / trail glyphs | `Style.font.icon` | favorite star opacity 1; failed glyph opacity 0.8 |
| Footer status and hints | `Style.font.caption` | opacity 0.7 throughout (was 0.45 with key names at 0.7, ruling SG2) |
| Empty-state glyph | `Style.font.displayLarge` | `Color.menu.selectedText`, opacity 0.8 |
| Empty-state title | `Style.font.title` | opacity 0.7 |
| Empty-state body / command | `Style.font.body` | opacity 1 for the command, 0.7 for prose |
| Bar label | `Style.font.body` | opacity 1 |
| Bar glyph | `Style.bar.iconFont` via `BarIconButton` | -- |

### 5.4 Selected row (cursor) and hover

- Exactly one highlighted row on screen at any time, whatever the input
  device. Mouse hover moves the cursor only through `PointerMoveGate`
  (`referenceItem: card`, `reset()` after every keyboard move or list
  rebuild), exactly as the clipboard and menu do. There is no separate hover
  color.
- **The cursor is carried by a MARK, not by ink** (PO ruling 2026-09-21,
  amending the clause below and ruling SG4). A 2 px rounded vertical mark sits
  in the row's left gutter, `Style.space(2)` wide, 62 per cent of the row
  height, `Color.menu.text`, visible only on the cursor row. It is defined by
  luminance rather than hue, so it survives greyscale and every colour vision
  deficiency, and it is one size in one position on every row, so a moving eye
  can track it. It measures 5.94:1 at the floor against the fill it abuts.
  Every list with a cursor has one: the channel list and the Sources list.
  This paragraph exists because the mark shipped in 0.7.0 while this section
  did not mention it, which made 5.4 a criterion nothing could observe.
- **The accent means ACTIVE, never CURSOR.** `Color.menu.selectedText` marks
  which group is filtering the list and which button a dialog has chosen. It
  never inks the cursor row, with no exceptions. The EPG progress fill (5.6)
  was the last one and lost the accent on 2026-09-22 under D-RUNG-10, because
  the accent could not clear the 3:1 non-text bar against its own track at any
  alpha. This REPLACES the previous clause, "name, lead
  glyph, and trail glyph in `Color.menu.selectedText`": on screen that clause
  had never once been true (D-RUNG-13 -- the arithmetic was handed an
  uncomposited fill and fell through to the text token on 23 of 23 themes),
  and making it true would cost contrast on 22 of 23 themes, median 31 per
  cent and up to 73 (white 17.55 -> 4.78), leave the selected row's name
  fainter than an unselected row's on 23 of 23, and buy nothing at all on
  white, vantablack and solitude, whose accents are grey.
- Cursor row: background `Color.menu.selectedBackground`, radius
  `Style.cornerRadius`; name, number, lead glyph and trail glyph stay
  `Color.menu.text`; the detail line and right meta stay `Color.menu.text` at
  their reduced opacity (menu convention).
- Optional theme border: `Border.surfaceSpec("menu", "selected-border", Color.menu.selectedBorder, 0)` on the cursor row, `Border.none()` otherwise (menu convention; zero width unless the theme asks). Note it ships **0 px wide on every installed theme**, so it is not a selection signal and the mark above is not optional.
- Group column selected entry: same fill, and the label inked with the
  calibrated active ink (`Model.cursorInkHex`), not the raw accent -- raw, it
  was under 4.5:1 on 8 of 23 themes against the fill it sits on, floor 2.80.
- Captions at 10 px (`Style.font.caption`) that carry information -- the group
  entry count, the Sources pinned count, the footer status line and the footer
  hints -- are **bold**, and their opacity rung is an **output of the surface
  they land on**, not the constant 0.7 it used to be (D-RUNG-14,
  `Model.captionAlpha`). Both halves are needed and neither is sufficient:
  - Bold answers the RENDERING shortfall. 10 px regular lands 11 to 13 per cent
    below the contrast model; bold renders at model accuracy, confirmed on the
    real display once the measurement was no longer taken against a stale build
    (F-CAL-4). Prose captions ship regular on purpose and draw a floor grossed
    up by that shortfall instead (`CAPTION_FLOOR_REGULAR`, 5.2941).
  - The per-surface rung answers the ARITHMETIC one. `selectedBackground` is
    `Util.alpha(menu.text, 0.08)` over the card, so the selected row's fill
    moves toward the ink: tokyo-night models 4.6433 on the card and 4.2157 on
    the selection. No weight recovers that -- bold measures 4.1893 there, model
    accuracy and a failure -- because the ceiling is in the arithmetic.
  The rung is raised **only** where 0.7 does not clear the floor, so 16 of 23
  themes render byte-identically to before; 11 of 46 theme surfaces rise, worst
  0.89. Result: 0 of 46 under the 4.65 floor, against 6 of 23 under 4.5 on the
  selection before. On the card the function returns byte-identically what
  `sectionHeaderAlpha` already shipped, which is also what closed the old
  inconsistency where that floor graded the caption rung's own value a fail.
- **The accepted cost, on the selected group row only.** Raising the count to
  clear AA puts it level with its own label, since the label is `cursorInk`
  clamped to 4.7 on that same fill. The CIE L* step between them falls from
  10.20 to 0.15 on catppuccin-latte and 11.36 to 0.38 on rose-pine. Hierarchy
  there is then carried by size (10 px against 12 px), weight, position and hue
  rather than by lightness. Ruled acceptable by the product owner: a 4.55 floor
  was priced and moves the worst step only to 0.63, so the collision is
  structural; and 9 of 23 themes already read the count louder than the label at
  the old flat rung, so the separation being spent was largely notional. No
  theme is newly inverted, and that is asserted rather than assumed.
- Row `MouseArea`: `hoverEnabled: true`, `cursorShape: Qt.PointingHandCursor`; click = play and close (Enter); click on the lead slot = toggle favorite only.
- No color animation on the cursor; the clipboard has none, and 10k-row lists must stay cheap.

### 5.5 Glyphs (JetBrains Mono Nerd Font, `Style.font.menuFamily` / `bar.fontFamily`)

| Meaning | Glyph | Codepoint | Nerd Font name |
|---|---|---|---|
| IPTV idle / not configured (bar), empty-state icon | ó° | U+F0502 | nf-md-television |
| Playing (bar) | ó°§ | U+F0567 | nf-md-television_play (also the menu-entry icon in the contract) |
| Playlist error, no cache (bar + empty state) | ó° | U+F0503 | nf-md-television_off |
| Favorite (row lead) | ó° | U+F04CE | nf-md-star |
| Playing (row trail, footer) | ó° | U+F040A | nf-md-play |
| Failed this session (row trail), banner, notifications | ó°¦ | U+F0026 | nf-md-alert |
| Loading (empty state) | ó° | U+F01D8 | nf-md-dots_horizontal |
| Refresh (notification glyph) | ó° | U+F0450 | nf-md-refresh |
| Recent (notification / future use) | ó° | U+F02DA | nf-md-history |

Do not use color to distinguish these; each carries meaning by shape. Bar
glyph dimming for idle uses `Qt.darker(bar.barForeground, 1.55)` (tailscale
inactive), never `Color.muted` directly, so it tracks the bar's foreground.

### 5.6 EPG progress indicator

- A `Rectangle` at the bottom of the row content area, aligned with the
  text (starts at the lead-slot right edge, ends at the right meta's left
  edge), height `Style.space(2)`, radius `Math.min(Style.cornerRadius, Style.space(1))`.
- Track: `Util.alpha(Color.menu.text, 0.12)`. Fill: `Util.alpha(Color.accent, 0.55)`,
  width = track width * fraction, fraction = clamp((now - start) / (stop - start), 0, 1).
- On the cursor row the fill uses `Util.alpha(Color.menu.selectedText, 0.7)`.
- Not color-only: the `until HH:MM` meta and the `Now:` text carry the same
  information.
- Fractions update from a 30 s `Timer` while the guide is open; no per-row
  animation.

### 5.7 Banner and footer

- Banner: `Util.alpha(Color.urgent, 0.10)` fill for errors; for the neutral
  "EPG still loading" notice use `Style.normalFillFor(Color.menu.text, Color.accent)`.
  Glyph in `Color.urgent` (error) or `Color.menu.text` (neutral).
- Footer: no fill, no border; a single `Row` with the status text on the
  left and hints on the right, both `Style.font.caption`. The hint text
  changes with mode (6.2).

### 5.8 Animation

Omarchy's overlays (clipboard, emojis, menu) flip `visible` with no fade;
only `KeyboardPanel` bar popups fade 140 ms `Easing.OutCubic`. The guide
follows the overlays:

| What | Animation |
|---|---|
| Guide open / close | none (instant; also keeps the 150 ms open budget) |
| Cursor move | none |
| Banner appear / disappear | `Behavior on opacity`, `NumberAnimation { duration: 140; easing.type: Easing.OutCubic }` |
| Bar label width change (name changes / appears) | `Behavior on implicitWidth`, 180 ms `Easing.OutCubic` (ActiveWindow widget) |
| Bar glyph color (dim <-> normal) | `ColorAnimation { duration: 160 }`, `enabled: bar.foregroundAnimationEnabled` (media widget) |
| Footer "Stopped" / "Refreshed" transient | text swap, 3 s `Timer`, no animation |

### 5.9 What must NOT be hardcoded

- Any hex color, `"white"`, `"black"`, or `Qt.rgba(...)` literal. Every
  color is `Color.menu.*`, `Color.accent`, `Color.urgent`, `bar.barForeground`,
  or an `Util.alpha` / `Qt.darker` of one of those.
- Any font family string. Use `Style.font.menuFamily` in the guide and
  `bar.fontFamily` in the bar widget.
- Any pixel size. Use `Style.space(n)`, `Style.spacing.*`, `Style.font.*`,
  `Style.bar.*`.
- Corner radius (`Style.cornerRadius`), gaps (`Style.gapsOut`), border width
  (`Border.surfaceSpec` as above), scrim alpha (already in `Color.menu.scrim`).
- The bar label max width: a manifest setting `barLabelMaxWidth`
  (integer, default 180, min 60, max 600), applied as `Style.space(setting)`.
- Timing constants (140 / 160 / 180 ms, 30 s EPG tick, 3 s footer transient)
  live as named `readonly property int` values on the root item, in one place.
- Strings: all microcopy in section 6 goes in one `Copy.js` (or a `readonly
  property var copy` block) so the README and the code cannot drift.

---

## 6. Microcopy

Tone: Omarchy's. Sentence case, terse, no exclamation marks, no "please",
verbs first, the object named ("Delete entire clipboard history?", "No
matches for "x"", "Invalid reminder / Enter the number of minutes").

### 6.1 Guide labels

| Where | String |
|---|---|
| Search placeholder | `Search channels...` |
| Scope label, browsing | `Favorites - 6 channels`, `All - 1,204 channels`, `Recent - 3 channels`, `UK | SPORTS - 142 channels` |
| Scope label, searching | `in All - 14 matches`, `in UK | SPORTS - 9 matches` |
| Column entries | `Recent`, `Favorites`, `All`, section header `GROUPS`, synthetic group `Ungrouped` |
| Row detail prefixes | `Now: `, `Next: ` |
| Row right meta | `until 21:30` (24-hour, local time, no seconds) |
| Row failed detail | `Failed 21:12 - Space to retry` |
| Footer status, normal | `1,204 channels - updated 12:40` |
| Footer status, cached | `1,204 channels - cached 12:40 - offline` |
| Footer status, playing | `ó° Sky Sports Main Event - s stop` |
| Footer status, transient | `Refreshing...`, `Refreshed - 1,204 channels`, `Stopped`, `Added to Favorites`, `Removed from Favorites`, `Removed from Recent` |
| Footer status, bounded search | `First 200 of 1,240 - keep typing` |
| Footer status, EPG pending | `Guide data loading...` |

### 6.2 Footer hints

| Mode | Hint line (right side) |
|---|---|
| Search mode | `Enter play - Up/Down move - Left/Right group - Tab keys - Esc close` |
| Search mode, query non-empty | `Enter play - Up/Down move - Left/Right narrow - Tab keys - Esc clear` |
| List mode | `j/k move - h/l group - Enter play - Space preview - f favorite - s stop - c pause - r refresh - / search - o sources` |
| Empty states | `r retry - o sources - Esc close` (not configured, error; `r retry` is dropped when the configured value is invalid and `o sources` only when a source history exists); `Esc close` (loading). Since v0.2.0 the not-configured state is the Sources first-run form, see `UX-SOURCES.md` 1.2 and 5.3, which is authoritative for these hints |

Key names and verbs both render at opacity 0.7 (ruling SG2). **They used to
differ, keys at 0.7 and verbs at 0.45, and that distinction is deliberately
gone:** measured across all 23 installed theme token sets, 0.45 falls under the
4.5:1 contrast threshold in every single one, worst 1.98:1. Losing the
key/verb contrast is the accepted cost of the footer being readable at all.

### 6.3 Empty, loading, and error states

| State | Title | Body |
|---|---|---|
| Not configured | `No playlist configured` | `Set your M3U URL or path, then press r to load it:` / command box `omarchy bar set io.github.rmcdavid.iptv playlistUrl <url>` / `Optional EPG:  omarchy bar set io.github.rmcdavid.iptv epgUrl <url>` / `Settings live in ~/.config/omarchy/shell.json (entry io.github.rmcdavid.iptv)` |
| Loading, no cache | `Loading playlist...` | `Fetching from <host>` |
| Fetch failed, no cache | `Playlist failed to load` | `<reason> from <host> - check playlistUrl` where reason is one of `HTTP 403 Forbidden`, `HTTP 404 Not Found`, `HTTP 5xx`, `Could not resolve host`, `Connection refused`, `Timed out`, `Not an M3U playlist`, `File not found` (local path) |
| Fetch failed, cache present (banner) | -- | `ó°¦  Playlist refresh failed (<reason>) - showing cached copy from 12:40 - r retry` |
| EPG failed (banner, low emphasis) | -- | `Guide data unavailable (<reason>) - channels still work - r retry` |
| Playlist loaded with warnings (footer line) | -- | `Playlist warning: <first warning> (+N more)` when more than one. Shown after a load that produced warnings, such as the 50,000 channel or 2,000 group caps, and cleared by the next clean load. It never displaces a playing, refreshing or error state; see the precedence note below |
| Guide data loaded with warnings (footer line) | -- | `Guide data warning: <first warning> (+N more)`. Same rules as the playlist warning, and the playlist warning wins when both are present |
| Playlist parsed but empty | `Playlist has no channels` | `Parsed 0 channels from <host> - check the URL points at an M3U` |
| No favorites yet (Favorites list empty) | `No favorites yet` | `Press f on any channel to pin it here` |
| Recent empty | (entry hidden) | -- |
| No search matches, scope All | `No matches for "sky"` | `Esc clears the search` |
| No search matches, scope a group | `No matches for "sky" in UK | SPORTS` | `h/l other groups - Home for All` (Home = the column's All entry; implement as: Home in list mode with a query active jumps the column to All) |
| Group column, narrow screen | -- | header scope label only |

Footer precedence, highest first: a transient such as `Refreshed - N channels`, then a bounded search result, then playing, then refreshing, then a degraded state, then a pending guide-data load, then a playlist warning, then a guide-data warning, then the plain channel count. A degraded state means an error or a cached and offline copy, and it renders as the `N channels - cached HH:MM - offline` counts line. A failure with no cache at all leaves this slot blank, because the body carries the message instead. Warnings are informational and must never hide a failure or a degraded state. Every warning string is passed through URL redaction before it is drawn.

Bar tooltips (`bar.showTooltip`):

| State | Tooltip |
|---|---|
| Idle, ready | `IPTV - click to open the guide` |
| Not configured | `IPTV - no playlist configured` |
| Playing | `Playing Sky Sports Main Event` (full name, untruncated) |
| Error, not playing | `IPTV - playlist error, open the guide` |
| Refreshing | `IPTV - refreshing playlist...` |

### 6.4 Desktop notifications (`omarchy-notification-send "<headline>" "<body>" -g <glyph> -u <urgency>`)

| Event | Headline | Body | Glyph | Urgency |
|---|---|---|---|---|
| Stream failed | `Stream failed` | `“Sky Sports Main Event” did not play` (the name is wrapped in curly quotes so a name starting with `-` can never be read as a flag, security finding S-04; append ` - <mpv reason>` when mpv gives one, e.g. `HTTP 403`) | `ó°` U+F0503 | normal |
| Playlist refreshed (manual `r` / middle click only) | `Playlist refreshed` | `1,204 channels in 38 groups` | `ó°` U+F0450 | low |
| Playlist error, cache used | `Playlist error` | `Could not fetch the playlist (<reason>). Using cached copy from 12:40.` | `ó°¦` U+F0026 | normal |
| Playlist error, no cache | `Playlist error` | `Could not fetch the playlist (<reason>). Open the guide for details.` | `ó°¦` | normal |
| EPG error | `Guide data error` | `Could not fetch the EPG (<reason>). Channels still work.` | `ó°¦` | low |
| mpv missing | `mpv not found` | `Install mpv to play channels.` | `ó°` | critical |

Rules: never include the playlist URL or query string in any notification
(credentials). Timer-driven refreshes are silent on success. Use
`--app-name IPTV`. Pass `-r <id>` so a repeated failure replaces the
previous toast rather than stacking.

---

## 7. Accessibility and ergonomics

Omarchy's shell sets no `Accessible.*` properties today. The guide sets a
minimal, cheap set, and `qmllint` sees a coherent surface.

**This section used to end "so screen readers and `qmllint` see a coherent
surface". Half of that was false for the life of the project and is corrected
here.** No screen reader has ever seen any of it. Not because the properties
are wrong -- they are right, and 7.1 now says which of them have been observed
becoming real nodes -- but because no window Quickshell creates publishes an
accessibility tree at all. A `PanelWindow` reports `ChildCount 0`; so does a
plain `FloatingWindow`; a plain Qt window in the same session, on the same bus,
with the same bridge, reports a real child. That is D-GS-3, the cause is
settled, it is not layer-shell and it is not ours, and it is filed upstream as
quickshell issue 1144 (`docs/ACCESSIBILITY-INVESTIGATION.md` section 6).

### 7.1 Accessible roles and names

**The delivery statement, plainly.** On this desktop today, **nothing this
table declares reaches assistive technology.** Not one role, not one name, not
one state, in the shipping plugin, for any user. That is true of every row
below without exception and it is not a property of the rows; it is the
upstream defect above. These are two different claims and this document must
not blur them:

1. *Our markup is correct.* Testable, and increasingly tested. The guide's
   content is ordinary QtQuick, so the accessibility harness (`tests/a11y/`)
   instantiates it in a plain hidden Qt window where the bridge does work,
   walks the real AT-SPI tree and asserts the nodes. A row marked OBSERVED has
   been seen becoming a node with the right role and the right name.
2. *A user can hear it.* **Not true of any row, and not testable here.** It
   becomes testable when quickshell 1144 lands, and not before. Every OBSERVED
   below means "our side would be correct if the host were", which is worth
   having and is not the same as delivered.

**Marker column.** Per CLAUDE.md rule 14, a rule nothing observes carries the
marker until something observes it.

- **OBSERVED** -- the harness instantiates this surface, walks the tree, and
  asserts this row's role and name at the node. Evidence is the dated run filed
  in `docs/QA-RESULTS.md` under "Accessibility harness runs"; a marker with no
  filed run behind it is a coverage claim, not evidence, and the QA case
  (TC-A11Y-01, TC-BAR-11) is the thing that goes red.
- **COMPOSED** -- only the string builder is asserted, from node, against
  `Model.js`. It proves the text is right. **It has never proved that the text
  becomes a node**, which is exactly the gap that let this whole area pass for
  months: all 17 executable assertions that existed were of this kind.
- **OBSERVED-ONCE** -- seen becoming a real node by the prototype run that
  established this approach (19 checks, re-run and reproduced by a second
  lane), but **not** covered by a scenario in the landed harness at the time
  this marker was written. It is evidence that the markup is right and it is
  not a standing assertion: nothing re-checks it, so it decays. Treat it as a
  coverage gap with a receipt, not as coverage.
- **UNVERIFIED** -- nothing observes it and no builder covers it. The promise
  stands as a promise.

| Surface | `Accessible.role` | `Accessible.name` | Verified |
|---|---|---|---|
| Guide card | `Accessible.Dialog` | `IPTV guide` | **OBSERVED-ONCE.** The prototype asserted this node; no landed scenario does. Every scenario instantiates the card, so this is the cheapest gap in the table to close |
| Search line | `Accessible.EditableText` | `Search channels`; `Accessible.description` = current query | **OBSERVED** (query scenario): name, description **and value**. The value is asserted because Qt publishes an editable node's value from its `text` and that is the sink D-A11Y-1 leaks from; a role-and-name check passes cleanly over a leak |
| Group column | `Accessible.List` | `Groups` | **OBSERVED-ONCE.** Prototype only; no landed scenario asserts the group column |
| Group entry | `Accessible.ListItem` | `<name>, <n> channels` | **OBSERVED** (scale scenario); the count text also **COMPOSED** (`Model.pluralChannels`) |
| Group entry | `Accessible.selected` = is the selected entry | -- | **OBSERVED-ONCE.** The prototype asserted the `selected` state on exactly the selected entry. No landed scenario does, so nothing today would notice the binding being lost |
| Channel list | `Accessible.List` | `Channels in <scope>` | **OBSERVED** (scale scenario, as `Channels in All`); scope text **COMPOSED** (`Model.scopeName`). No scenario yet walks the tree with a group or Favorites scope, so the `<scope>` substitution itself is COMPOSED, not OBSERVED |
| Channel row | `Accessible.ListItem` | `<name>` (+ `Channel <n>, ` prefix when numbered, M2-03 section 11) | **OBSERVED** (query, scale scenarios) |
| Channel wall (2.4b) | `Accessible.List` | `Channels in <scope>` | **DECLARED, NOT OBSERVED.** The same role and name the list carries, so an AT is told the same thing about the same rows in either view. No landed scenario walks the tree with the wall presenting; `tests/a11y/host_guide.qml` instantiates the guide in its default view |
| Wall tile | `Accessible.ListItem` | `<name>, row N of M` (`Model.rowAccessibleName`, the row's own composer) | **COMPOSED, NOT OBSERVED.** Deliberately identical to the row's name rather than a tile-specific one: the wall is a presentation of the same rows, and an AT that is told "row N of M" in one view and something else in the other has been told the cursor moved when it did not. Qt Quick exposes no table or position interface for `GridView` (investigation 4.6(d)), so `row N of M` in the NAME is the only carrier available and the reading it gives is a flat sequence, not a grid position -- which is exactly what `h`/`l` traverse |
| Wall tile picture | -- | -- | `Accessible.ignored`, both the image and the mark. Same reasoning as the row's logo slot (7.2): the name already carries the channel, and announcing "image" before every tile is noise. Not a security control -- the investigation measured that an unannotated `Image` does not reach the tree at all |
| Channel row | -- | suffixes `, favorite`, `, playing`, `, now <programme> until <HH:MM>`, `, failed` | `, favorite` **OBSERVED-ONCE** (the prototype asked `Model.rowAccessibleName` for a favourite row's name and then required that exact string on the bus). `, playing`, `, now ... until <HH:MM>` and `, failed` are **COMPOSED only** (`Model.rowAccessibleName`, 5 node assertions): no scenario fixture sets a playing, a now/next or a failed row, so three of the four states a user most needs to hear are string builders with a promise attached. A suffix becomes OBSERVED when a filed run populates it, and not before |
| Channel row | `Accessible.focused` = hasCursor | -- | **OBSERVED-ONCE.** Prototype only. No landed scenario asserts the `focused` state, and it is the one state a screen-reader user navigating rows depends on most |
| Channel row | -- | `, row N of M` appended last, after `, failed` | **PROMISED AND DELIVERED.** This row previously read "never promised here and never delivered" and both clauses were false, which is rule 13 drift inside the table written to end rule 13 drift. Promised at `docs/UX-GUIDE-AT-SCALE.md:768` and `:865` (ruling D5); delivered at `Model.js:4213-4215` (`rowAccessibleName({name:'Channel 7', rowIndex:7, rowCount:10000})` returns `Channel 7, row 8 of 10,000`); wired at `Guide.qml:2452`; asserted in `tests/Model.test.js`. The real caveat, which survives: `rowCount` is what the LIST holds, so under a query it is the capped 200 the header counts against, not the true match total, which stays in the footer |
| Banner | `Accessible.AlertMessage` | banner text | **OBSERVED** (banner scenario: the node exists and its name equals the banner text on screen, redacted as the screen is) |
| Banner | -- | *the transition is announced* | **UNVERIFIED.** Nothing calls `Accessible.announce()`; a client that is not already watching the node never learns the banner changed. The double-announce question (GS5) has to be settled first -- investigation section 8 item 4 |
| Footer status | `Accessible.StaticText` | status text | **OBSERVED** (banner scenario, including the degraded `cached ... offline` wording); text **COMPOSED** (`Model.footerStatus`) |
| Footer hints | -- | *the key hints beside the status* | **UNVERIFIED**, and deliberately: the hints `Text` carries no `Accessible.*` and M2-03 section 11 declines to give it any. A keyboard-only user hears the status and not the keys that act on it. Recorded as a known gap, not a defect |
| Bar widget | `Accessible.Button` | `IPTV, idle` / `IPTV, playing <name>` / `IPTV, playlist error` (`IPTV, playing channel <n>, <name>` when numbered) | **OBSERVED** (bar scenarios: exactly one button node per state, the three names distinct, no Private-Use codepoint inside a published name); text **COMPOSED** (`Model.barAccessibleName`) |

**Declared in the code and absent from this table.** These publish today and
this document never promised them, which is the same failure in the other
direction -- an undocumented promise nobody grades. Listed so they are visible;
adding them as rows is the UX owner's call, not a test lane's:
`Guide.qml:2053` confirm `Dialog`, `:2107` header `Heading`, `:2319` the
pinned Sources `Button`, `:2658` the numeric-zap `AlertMessage` (documented
instead in `docs/M2-03-CHANNEL-NUMBERS.md` section 11), and the whole Sources
surface (documented in `docs/UX-SOURCES.md` 7.1).

**Empty, loading and error surfaces have nothing to say.** Each is a `Dialog`
containing no named node. **UNVERIFIED**, and there is nothing to verify:
no name is composed for them anywhere. Investigation section 8 item 3.

**Scenario names** above are the harness's own: `bar`, `firstrun`, `banner`,
`query`, `scale`, `xtream`. The set is the harness lane's to extend; a row here
marked OBSERVED against a scenario that is renamed or dropped becomes wrong
silently, which is the next paragraph.

**The markers above are joined to the harness by a name, not by a call**, which
is the drift CLAUDE.md rule 13 is about. Until a check reads this table and the
filed run together, an OBSERVED marker survives the assertion behind it being
renamed, weakened or deleted. Proposed with the gate conditions in 7.1a.

### 7.1a When this stops being a lane tool

The harness is a tool the accessibility lane runs, **not** a commit gate, ruled
so by the product owner (`docs/PLAN-NEXT.md` decision 9) for two reasons that
are both about `scripts/check.sh` and neither about the harness: its baseline
on shipping code is deliberately red -- D-A11Y-1 is open and unfixed, so a run
that went green would mean the check stopped asking -- and CLAUDE.md forbids
committing a red gate; and it would be the first hard dependency on a live
graphical session in a gate that is headless today.

It moves into `scripts/check.sh` when **all three** hold, and the third is the
one this section adds:

1. **A green baseline.** D-A11Y-1 is closed under a ruling (decision 7 for the
   unconsented sinks, decision 8 for the consented reveal), so a green run
   means "no leak" rather than "no ruling yet".
2. **A headless route.** Today only the `wayland` platform publishes a tree on
   this machine: `offscreen` has no bridge, and there is no Xvfb and no
   headless compositor installed. A gate that needs somebody's session is a
   gate that fails on a machine that is fine. Either a headless compositor
   becomes a declared build dependency, or the tree is dumped through
   `QAccessible` in-process where `tests/Model.spec.qml` already runs.
3. **The markers are joined by a call.** A check that fails when a row here
   says OBSERVED and no filed run asserts it, and when a filed run asserts a
   row this table does not carry. It needs no display and could gate today;
   it belongs with `scripts/check-defect-ledger.py`, whose job is the same.

Until then, `scripts/check.sh` stays green and headless, and these markers are
re-earned by running the harness and filing the output.

### 7.2 No color-only status

Every state has a glyph or word: favorite (star), playing (play glyph +
bold + footer text), failed (alert glyph + `Failed HH:MM`), cached/offline
(footer words), error (banner words), progress (`until HH:MM`). Tints
(`Color.accent`, `Color.urgent` at reduced alpha) are decoration on top.

### 7.3 Hit targets (mouse users)

- Channel rows: full list width, at least `Style.space(38)` tall.
- Group entries: full column width, at least `Style.space(32)` tall.
- Lead slot (favorite toggle by click): `Style.space(24)` wide by full row
  height; padded to at least `Style.space(28)` square by extending the
  `MouseArea` over the row's left margin.
- Bar widget: full bar height, at least `Style.bar.iconSlot` wide; the label
  extends the same `MouseArea`.
- Scrim click closes; card click does nothing (swallowed), as in the
  clipboard.
- Wheel over the channel list scrolls the list (Flickable default); wheel
  over the group column moves the column selection one entry per tick.

### 7.4 Multi-monitor

Follow the clipboard and menu exactly: one `PanelWindow` with no `screen`
set. Hyprland maps an overlay layer surface without an output preference
on the currently focused monitor, which is where the user's attention is.
Do not enumerate `Quickshell.screens` and do not use `KeyboardPanel`'s
per-output dismiss twins (that is a bar-popup concern; the exclusive
keyboard focus of an overlay already ends on Esc).

### 7.5 Focus and the mpv window

- `Enter`: the plugin sends `loadfile <url> replace` over the IPC socket
  (or launches mpv with `--wayland-app-id=omarchy-iptv --title=<name>
  --force-media-title=<name>` if not running), hides the guide via
  `shell.hide(manifest.id)`, then focuses mpv with
  `hyprctl dispatch focuswindow class:omarchy-iptv` (argv, no shell). If
  mpv is on another workspace Hyprland switches to it; this is desired.
- `Space`: same load, guide stays open and keeps exclusive keyboard focus;
  no focus call.
- If the user closes mpv, the helper observes the socket going away and the
  bar returns to idle; the guide's playing cues clear.
- If the user opens the guide while mpv is fullscreen, the overlay layer
  draws above it (Overlay layer); Esc returns to mpv unchanged.
- Opening the guide never pauses or mutes mpv.

### 7.6 Performance ergonomics

- Guide open renders from the in-memory model; the first frame must not
  wait on file reads. Keep the overlay `keepLoaded: true` in the manifest so
  the model survives between summons.
- Search results are capped at 200 rows; the `ListView` is virtualized with
  `cacheBuffer` no larger than four rows.
- Typing must never drop keystrokes: if a filter pass exceeds one frame,
  coalesce with a 40 ms timer.

---

## 8. Open questions, decided here

| # | Question | Decision |
|---|---|---|
| 1 | Mode on open: list (vim) or search? | Search mode with empty query, cursor on row 0 (or the playing channel). Matches every Omarchy overlay; `Tab` reaches vim keys in one press. |
| 2 | Does typing an unbound letter start a search in list mode? | No. Only `/` and `Tab` enter search mode; avoids `s`/`f`/`k` firing mid-word. |
| 3 | Is Space a literal in search mode? | Yes (channel names contain spaces). Preview-with-Space is list-mode only. |
| 4 | Enter on the already-playing row | Closes the guide and focuses mpv; no reload (no stream restart). |
| 5 | Search scope | Selected group; All when on Recent/Favorites/All. Column moves to All when a query starts from Recent/Favorites; restores on clear. |
| 6 | Default sort | Playlist order everywhere except Favorites (order added) and Recent (most recent first). No alphabetizing. |
| 7 | Result cap | 200 rows with a footer hint. |
| 8 | Recent size and timing | 10 entries; added on the play command, not on playback success, so a retry is one keystroke away. |
| 9 | Dead-stream memory | **AMENDED 2026-09-24 by the product owner: the mark now survives a restart.** A failed channel shows the alert glyph and the time it failed -- `Failed HH:MM` for a failure today, a date for an older one, so the row never implies a week-old observation is current. It is dropped when the channel next plays, when it ages out, when its id leaves the playlist, and when its source is removed. Stored in that source's cache, never in `state.json`. Original ruling: Session-only ... Nothing persisted. |
| 10 | Zap ring for bar scroll | The list the channel was launched from (Favorites, a group, All, or the result's group). Recent is never a ring. |
| 11 | Bar label: marquee or elide? | Elide right at `Style.space(barLabelMaxWidth)`, default 180; full name in the tooltip. A marquee under live TV is distracting. |
| 12 | Vertical bar | Icon only; tooltip carries the name. (First-class vertical layout is M2 per PRODUCT.md.) |
| 13 | Open/close animation | None, matching clipboard/menu/emojis and the 150 ms budget. |
| 14 | Which glyphs | ó° idle, ó°§ playing, ó° error, ó° favorite, ó° playing row, ó°¦ failed/alert, ó° loading, ó° refresh (all verified in the installed font). |
| 15 | Refresh notifications | Only for manual refresh (`r`, middle click). Timer refreshes are silent unless they fail. |
| 16 | Where do settings live for a plugin that is both bar-widget and overlay? | The empty state names the command (`omarchy bar set ...`) and the file (`~/.config/omarchy/shell.json`); the architect decides whether the overlay reads the bar-layout entry or a `plugins[]` entry, and the README states which. Copy does not change either way. |
| 17 | Digits | Ignored in list mode (reserved for M2 channel numbers); literal in search mode. |
| 18 | Uppercase command letters | `F`, `S`, `R`, `X` behave like lowercase (tailscale precedent). |
| 19 | Narrow screens | Hide the group column under a `Style.space(720)` card width; `h`/`l` keep working with the header scope label as feedback. |
| 20 | Credentials in UI | Never render the playlist or EPG URL beyond scheme + host anywhere (guide, tooltip, notification, console). |
| 21 | Clicking the command box in the not-configured state | Copies the command with `wl-copy` and shows `Copied` in the footer for 3 s. Optional; keyboard users have the README. |
| 22 | Home with a query active in list mode | Jumps the column to All (the "Home for All" hint). Without a query, Home is first row as usual. |

### 8.1 What the architect and front-end developer must provide

- Per-channel model fields the guide reads: `id`, `name`, `group`, `url`,
  `favorite` (bool), `playing` (bool, exactly one true), `failedAt`
  (HH:MM string or empty, session-only), `epgNow` `{title, start, stop}`,
  `epgNext` `{title}`, `epgFraction` (0..1, computed by the model on the 30 s
  tick).
- Guide state the UI binds: `mode` (`search` | `list`), `query`,
  `scopeId` (`recent` | `favorites` | `all` | `<group>`), `cursorIndex`,
  `status` (`ready` | `loading` | `refreshing` | `cached` | `error`),
  `statusReason`, `statusHost`, `lastUpdated` (HH:MM), `bannerKind`
  (`none` | `playlistError` | `epgError` | `epgPending`), `resultTotal`
  (for the 200 cap hint), `nowPlaying` `{name, group, launchedFrom}`.
- Actions: `play(id, keepOpen)`, `stop()`, `toggleFavorite(id)`,
  `removeRecent(id)`, `refresh()`, `zap(+1|-1)`, `focusPlayer()`.
- Manifest settings: `playlistUrl`, `epgUrl`, `refreshMinutes`
  (default 360), `barLabelMaxWidth` (default 180).
- IPC verbs: `toggle`, `stop`, `next`, `previous`, `refresh`, `play(url)`.
