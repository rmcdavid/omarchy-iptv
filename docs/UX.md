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
  gesture to move past.
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
  the list.
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
| trail (`Style.space(20)` wide) | Playing glyph, or failed glyph | Playing: `󰐊` U+F040A. Failed this session: `󰀦` U+F0026. Otherwise empty. |
| right meta | `until HH:MM` when EPG has a current programme | `Style.font.caption`, opacity 0.52, right aligned. Hidden without EPG. |
| detail line | `Group - Now: X - Next: Y` | `Style.font.bodySmall`, opacity 0.52, elide right. Group segment is omitted when the selected column entry is that group. `Now:`/`Next:` segments are omitted without EPG data. A failed channel shows `Failed HH:MM - Space to retry` in place of the EPG segments. |
| progress | Thin bar, fraction of current programme elapsed | Only with EPG and a current programme. See 5.6. |

Row height: two-line ("detail") rows whenever the detail line has content
for this list (EPG configured, or a mixed list such as Recent / Favorites /
All / search results where the group name is meaningful). Inside a single
group with no EPG configured, rows are single-line. Row heights are in 5.2.

### 2.5 Sort rules

| List | Order |
|---|---|
| A group / All | Playlist order. Never alphabetize by default: providers and Tvheadend order channels deliberately (channel numbers, M2, will follow the same order). |
| Favorites | Order favorited, oldest first. (Manual reordering is M2.) |
| Recent | Most recently played first; a replay moves the entry to the top. |
| Search results | Rank tiers, then playlist order within a tier: (1) name starts with the query, (2) a word in the name starts with the query, (3) name contains the query, (4) group name contains the query. Favorites sort first inside each tier. |

### 2.6 Search semantics

- Case-insensitive, diacritics folded (`e` matches `e` with any accent),
  whitespace-separated terms are ANDed, each term matched against
  `name + " " + group`.
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
- **List mode** -- vim keys and single-letter commands are live.

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
| `Space` | Play the cursor row and keep the guide open (preview / zapping). The row gains the playing glyph and bold name; the footer updates. |
| `f` / `F` | Toggle favorite on the cursor row. In Favorites the row leaves the list; the cursor stays at the same index (clamped). |
| `x` / `X` / `Delete` | Remove the cursor row from Recent (in Recent) or unfavorite it (in Favorites). No-op elsewhere. Parity with the clipboard's delete. |
| `s` / `S` | Stop playback. No confirmation. Footer shows `Stopped`. |
| `r` / `R` | Refresh playlist and EPG now. Footer shows `Refreshing...` then the result; a desktop notification reports the outcome (6.4). |
| `/` | Enter search mode (query preserved). |
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
| `Down` / `Up` | Move the channel cursor; wraps. |
| `Right` / `Left` | Next / previous group column entry (search facet, 2.7). |
| `PgDn` / `PgUp` / `Home` / `End` | Same as list mode (there is no caret, so these are free). |
| `Enter` | Play the cursor row (result 0 by default), close the guide, focus mpv. |
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
|  Favorites        6 |> 󰓎  Sky Sports Main Event                              󰐊     until 21:30 |
|  All          1,204 |>     Now: Premier League: Arsenal v Spurs - Next: Match Replay           |
|                     |>     ===============================-----------------------------------  |
|  GROUPS             |                                                                          |
|  UK | SPORTS    142 |  󰓎  BBC One HD                                                until 20:00 |
|  UK | ENTERTAIN  96 |      Now: EastEnders - Next: The One Show                                |
|  UK | NEWS       38 |      ============---------------------------------------------------      |
|  UK | KIDS       24 |                                                                          |
|  UK | MOVIES     57 |  󰓎  Al Jazeera English                                        until 20:30 |
|  US | NEWS       41 |      Now: Newshour - Next: Inside Story                                  |
|  PL | INFORMAC.  19 |      ===========================--------------------------------------    |
|  DE | SPORT      33 |                                                                          |
|  ...                |  󰓎  Arte HD                                                   until 21:15 |
|                     |      Now: Karambolage - Next: Tracks                                     |
|                     |      ====----------------------------------------------------------      |
|                     |                                                                          |
|  󰐊 Sky Sports Main Event - s stop          Enter play - Up/Down move - Left/Right group - Tab keys - Esc close |
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
|  Favorites        6 |> 󰓎  Sky Sports Main Event                              󰐊     until 21:30 |
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
|  󰐊 Sky Sports Main Event - s stop                Enter play - Up/Down move - Left/Right narrow - Tab keys |
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
 󰓎         Sky Sports Main Event                     󰐊          until 21:30
           Now: Premier League: Arsenal v Spurs - Next: Match Replay          <- bodySmall, 0.52
           ===============================-----------------------------------   <- Style.space(2) tall
           ^ fill = Util.alpha(Color.accent, 0.55)    ^ track = Util.alpha(fg, 0.12)
```

Same row, no EPG configured, inside its own group (single-line row):

```
 󰓎         Sky Sports Main Event                     󰐊
```

Same row after a failed play this session:

```
           Sky Sports Main Event                     󰀦
           Failed 21:12 - Space to retry
```

### 4.4 Empty state: no playlist configured

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Search channels...                                                                            |
|                                                                                                |
|                                                                                                |
|                                                                                                |
|                                             󰔂                                                  |
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
|                                                                        r reload - Esc close    |
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
|                                             󰇘                                                  |
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
|  󰀦  Playlist refresh failed (HTTP 503) - showing cached copy from 12:40 - r retry              |
|                                                                                                |
|  Recent           3 |                                                                          |
|  Favorites        6 |> 󰓎  Sky Sports Main Event                                    until 21:30 |
|  All          1,204 |>     Now: Premier League: Arsenal v Spurs - Next: Match Replay           |
|                     |>     ===============================-----------------------------------  |
|  GROUPS             |                                                                          |
|  ...                |  ...                                                                     |
|                     |                                                                          |
|  1,204 channels - cached 12:40 - offline               Enter play - Up/Down move - Tab keys - Esc close |
+------------------------------------------------------------------------------------------------+
```

Banner spec: height `Style.space(28)`, radius `Style.cornerRadius`, fill
`Util.alpha(Color.urgent, 0.10)`, glyph `󰀦` in `Color.urgent`, text in
`Color.menu.text` at `Style.font.bodySmall`. The word "failed" carries the
meaning; the tint is decoration. The banner appears with a 140 ms opacity
fade and stays until the next successful refresh. The footer's
`cached HH:MM - offline` is the persistent US7 hint.

Error, no cache at all (empty state, column hidden):

```
                                             󰔃

                                   Playlist failed to load

                     HTTP 403 Forbidden from tv.example.net - check playlistUrl

                                    r retry - Esc close
```

### 4.7 "Now playing" affordance inside the guide

Three coordinated cues, all present at once:

```
  row:     󰓎  Sky Sports Main Event                              󰐊     until 21:30
           ^ name is Font.Bold                                   ^ playing glyph in the trail slot

  footer:  󰐊 Sky Sports Main Event - s stop          (left side of the footer, Style.font.caption)

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
idle, ready (dimmed glyph, no label):          [ 󰔂 ]

not configured (dimmed glyph, tooltip):        [ 󰔂 ]      tooltip: "IPTV - no playlist configured"

playing (glyph + label, elided at max width):  [ 󰕧 Sky Sports Main Ev.. ]
                                                  |<-- Style.space(180) -->|

playing, short name:                           [ 󰕧 Arte HD ]

error, not playing (television-off glyph):     [ 󰔃 ]      tooltip: "IPTV - playlist error, open the guide"

refreshing (any state; tooltip only):          [ 󰔂 ]      tooltip: "IPTV - refreshing playlist..."
```

Vertical bar (`Style.bar.sizeVertical` wide): icon only, label never shown,
the channel name lives in the tooltip. Same three glyphs.

```
 +----+
 | 󰕧 |   tooltip: "Playing Sky Sports Main Event"
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
| Group entry count | `Style.font.caption` | opacity 0.45, right aligned |
| GROUPS section label | `PanelSectionHeader` defaults | -- |
| Channel name | `Style.font.title` | `Font.Normal`; `Font.Bold` only when playing |
| Detail line | `Style.font.bodySmall` | opacity 0.52 (menu detail) |
| Right meta `until HH:MM` | `Style.font.caption` | opacity 0.52 |
| Lead / trail glyphs | `Style.font.icon` | favorite star opacity 1; failed glyph opacity 0.8 |
| Footer status and hints | `Style.font.caption` | opacity 0.45; key names at opacity 0.7 |
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
- Cursor row: background `Color.menu.selectedBackground`, radius
  `Style.cornerRadius`; name, lead glyph, and trail glyph in
  `Color.menu.selectedText`; the detail line and right meta stay
  `Color.menu.text` at their reduced opacity (menu convention).
- Optional theme border: `Border.surfaceSpec("menu", "selected-border", Color.menu.selectedBorder, 0)` on the cursor row, `Border.none()` otherwise (menu convention; zero width unless the theme asks).
- Group column selected entry: same fill and text tokens.
- Row `MouseArea`: `hoverEnabled: true`, `cursorShape: Qt.PointingHandCursor`; click = play and close (Enter); click on the lead slot = toggle favorite only.
- No color animation on the cursor; the clipboard has none, and 10k-row lists must stay cheap.

### 5.5 Glyphs (JetBrains Mono Nerd Font, `Style.font.menuFamily` / `bar.fontFamily`)

| Meaning | Glyph | Codepoint | Nerd Font name |
|---|---|---|---|
| IPTV idle / not configured (bar), empty-state icon | 󰔂 | U+F0502 | nf-md-television |
| Playing (bar) | 󰕧 | U+F0567 | nf-md-television_play (also the menu-entry icon in the contract) |
| Playlist error, no cache (bar + empty state) | 󰔃 | U+F0503 | nf-md-television_off |
| Favorite (row lead) | 󰓎 | U+F04CE | nf-md-star |
| Playing (row trail, footer) | 󰐊 | U+F040A | nf-md-play |
| Failed this session (row trail), banner, notifications | 󰀦 | U+F0026 | nf-md-alert |
| Loading (empty state) | 󰇘 | U+F01D8 | nf-md-dots_horizontal |
| Refresh (notification glyph) | 󰑐 | U+F0450 | nf-md-refresh |
| Recent (notification / future use) | 󰋚 | U+F02DA | nf-md-history |

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
| Footer status, playing | `󰐊 Sky Sports Main Event - s stop` |
| Footer status, transient | `Refreshing...`, `Refreshed - 1,204 channels`, `Stopped`, `Added to Favorites`, `Removed from Favorites`, `Removed from Recent` |
| Footer status, bounded search | `First 200 of 1,240 - keep typing` |
| Footer status, EPG pending | `Guide data loading...` |

### 6.2 Footer hints

| Mode | Hint line (right side) |
|---|---|
| Search mode | `Enter play - Up/Down move - Left/Right group - Tab keys - Esc close` |
| Search mode, query non-empty | `Enter play - Up/Down move - Left/Right narrow - Tab keys - Esc clear` |
| List mode | `j/k move - h/l group - Enter play - Space preview - f favorite - s stop - r refresh - / search` |
| Empty states | `r reload - Esc close` (not configured, error); `Esc close` (loading) |

Only the key names render at the higher opacity (0.7); the verbs stay at
0.45.

### 6.3 Empty, loading, and error states

| State | Title | Body |
|---|---|---|
| Not configured | `No playlist configured` | `Set your M3U URL or path, then press r to load it:` / command box `omarchy bar set io.github.rmcdavid.iptv playlistUrl <url>` / `Optional EPG:  omarchy bar set io.github.rmcdavid.iptv epgUrl <url>` / `Settings live in ~/.config/omarchy/shell.json (entry io.github.rmcdavid.iptv)` |
| Loading, no cache | `Loading playlist...` | `Fetching from <host>` |
| Fetch failed, no cache | `Playlist failed to load` | `<reason> from <host> - check playlistUrl` where reason is one of `HTTP 403 Forbidden`, `HTTP 404 Not Found`, `HTTP 5xx`, `Could not resolve host`, `Connection refused`, `Timed out after 30 s`, `Not an M3U file`, `File not found` (local path) |
| Fetch failed, cache present (banner) | -- | `󰀦  Playlist refresh failed (<reason>) - showing cached copy from 12:40 - r retry` |
| EPG failed (banner, low emphasis) | -- | `Guide data unavailable (<reason>) - channels still work - r retry` |
| Playlist parsed but empty | `Playlist has no channels` | `Parsed 0 channels from <host> - check the URL points at an M3U` |
| No favorites yet (Favorites list empty) | `No favorites yet` | `Press f on any channel to pin it here` |
| Recent empty | (entry hidden) | -- |
| No search matches, scope All | `No matches for "sky"` | `Esc clears the search` |
| No search matches, scope a group | `No matches for "sky" in UK | SPORTS` | `h/l other groups - Home for All` (Home = the column's All entry; implement as: Home in list mode with a query active jumps the column to All) |
| Group column, narrow screen | -- | header scope label only |

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
| Stream failed | `Stream failed` | `Sky Sports Main Event did not play` (append ` - <mpv reason>` when mpv gives one, e.g. `HTTP 403`) | `󰔃` U+F0503 | normal |
| Playlist refreshed (manual `r` / middle click only) | `Playlist refreshed` | `1,204 channels in 38 groups` | `󰑐` U+F0450 | low |
| Playlist error, cache used | `Playlist error` | `Could not fetch the playlist (<reason>). Using cached copy from 12:40.` | `󰀦` U+F0026 | normal |
| Playlist error, no cache | `Playlist error` | `Could not fetch the playlist (<reason>). Open the guide for details.` | `󰀦` | normal |
| EPG error | `Guide data error` | `Could not fetch the EPG (<reason>). Channels still work.` | `󰀦` | low |
| mpv missing | `mpv not found` | `Install mpv to play channels.` | `󰔃` | critical |

Rules: never include the playlist URL or query string in any notification
(credentials). Timer-driven refreshes are silent on success. Use
`--app-name IPTV`. Pass `-r <id>` so a repeated failure replaces the
previous toast rather than stacking.

---

## 7. Accessibility and ergonomics

Omarchy's shell sets no `Accessible.*` properties today; the guide sets a
minimal, cheap set so screen readers and `qmllint` see a coherent surface.

### 7.1 Accessible roles and names

| Surface | `Accessible.role` | `Accessible.name` |
|---|---|---|
| Guide card | `Accessible.Dialog` | `IPTV guide` |
| Search line | `Accessible.EditableText` | `Search channels`; `Accessible.description` = current query |
| Group column | `Accessible.List` | `Groups` |
| Group entry | `Accessible.ListItem` | `<name>, <n> channels`; `Accessible.selected` = is the selected entry |
| Channel list | `Accessible.List` | `Channels in <scope>` |
| Channel row | `Accessible.ListItem` | `<name>` + `, favorite` + `, playing` + `, now <programme> until <HH:MM>` + `, failed` as applicable; `Accessible.focused` = hasCursor |
| Banner | `Accessible.AlertMessage` | banner text |
| Footer status | `Accessible.StaticText` | status text |
| Bar widget | `Accessible.Button` | `IPTV, idle` / `IPTV, playing <name>` / `IPTV, playlist error` |

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
| 9 | Dead-stream memory | Session-only: a failed channel shows the alert glyph and `Failed HH:MM` until the next successful play of that channel or shell restart. Nothing persisted. |
| 10 | Zap ring for bar scroll | The list the channel was launched from (Favorites, a group, All, or the result's group). Recent is never a ring. |
| 11 | Bar label: marquee or elide? | Elide right at `Style.space(barLabelMaxWidth)`, default 180; full name in the tooltip. A marquee under live TV is distracting. |
| 12 | Vertical bar | Icon only; tooltip carries the name. (First-class vertical layout is M2 per PRODUCT.md.) |
| 13 | Open/close animation | None, matching clipboard/menu/emojis and the 150 ms budget. |
| 14 | Which glyphs | 󰔂 idle, 󰕧 playing, 󰔃 error, 󰓎 favorite, 󰐊 playing row, 󰀦 failed/alert, 󰇘 loading, 󰑐 refresh (all verified in the installed font). |
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
