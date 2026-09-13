# Omarchy IPTV -- UX specification: Sources (M2 lane 1)

Owner: UI/UX Designer. Status: v0.1, governs M2-01 (`docs/M2-SOURCES.md`:
locked decisions 1-7, stories S1-S8). Companion to `docs/UX.md` (the shipped
guide; everything there still applies unless amended here) and, in parallel,
`docs/ARCHITECTURE-SOURCES.md` (data, processes, security; owns the fields
listed in 8.1).

Conventions are UX.md's: only `Color.*` / `Style.*` tokens, numbers are
`Style.space(n)` arguments or `Style.font.<token>` names, ASCII everywhere
except Nerd Font glyphs (written glyph + codepoint on first use, all verified
present in `JetBrainsMonoNerdFont-Regular.ttf`, range U+F0001-U+F1AF0).
`...`, `"x"` and ` - ` map to U+2026, U+201C/U+201D and U+00B7 as in UX.md's
table. "As the guide does" always means the shipped `Guide.qml` (v0.1.0),
never a proposal.

Omarchy precedents this design maps onto (read them before implementing):

| Precedent | File | What we borrow |
|---|---|---|
| Inline passphrase entry | `/usr/share/omarchy/shell/plugins/panels/network/Panel.qml` | `PanelKeyCatcher { blocked: root.passwordSsid !== "" }`; `Ui.TextField` with `Keys.onEscapePressed` cancel, `onAccepted` submit, `Qt.callLater(forceActiveFocus)` when shown; `PanelActionButton` check glyph at the row's right edge; status pill `Connecting...` / `Wrong password` replacing the fields while busy |
| URL editing persisted from QML | `~/.config/omarchy/plugins/no.koka.uptime-monitor/Panel.qml` | `Ui.TextField { placeholderText; onAccepted: commit() }`, caption-bold labels, `persist()` -> `shell.updateEntryInline(id, settings)`, urgent-tinted `accent` on an invalid field, `Needs 5 cron fields` inline error line |
| Confirmation | `/usr/share/omarchy/shell/Ui/ConfirmDialog.qml` via `clipboard/Clipboard.qml` | `z: 10` dialog above the key host, `handleKey()` routed first, destructive button preselected (`selectedIndex = 1`), `Esc` / scrim click cancel, `Delete entire clipboard history?` / `Delete` copy shape |
| Text input kit | `/usr/share/omarchy/shell/Ui/TextField.qml` | kit focus/hover/selection styling, `password: true` echo mode, default `verticalPadding: Style.spacing.inputPaddingY`, `placeholderTextColor: Qt.darker(foreground, 1.6)` |

## 0. Decisions at a glance

| Topic | Decision |
|---|---|
| Entry key | `o` / `O` in list mode (`o sources`). Unbound in UX.md 3.1, not consumed by `PanelKeyCatcher`, not reserved by any M2 item (digits, Shift+Enter). Inside Sources, `o` returns to the guide. |
| Mouse entry | A pinned `Sources` row under the group column (separator + glyph + count); the `Saved sources (n)` link row in the first-run form. |
| New modes | `sources`, `sourceEdit` (origin `firstRun` or `sources`), `sourceXtream` (same origins), `confirmRemove`. `search` and `list` unchanged. |
| Sources list | Two-line rows like channel rows: lead check glyph + bold label when active, right meta = last used, detail = `active - host - kind - N channels in M groups - EPG`. Two action rows (`Add source`, `Add Xtream login`) close the list. No group column in this mode. |
| Masking | Userinfo, every query value and the fragment become `****`; scheme, host, port, path and query keys stay. Paths never masked. A masked field behaves as fully selected (typing, paste, Backspace replace it); `Ctrl+R` (or the eye button) reveals it for caret editing; re-masked on blur, save, cancel. |
| Esc | Forms from Sources: one press cancels (network-prompt precedent). First-run: clear the focused field first, then close (search-line precedent); never closes while any field still has text. |
| Save | Add and playlist-URL edits probe first and commit only on success (S8); label-only and EPG-only edits commit at once. Fetch progress and errors live on a form-local result line (banner treatment). |
| Switch | `Enter` switches and returns to the guide; `Space` switches and stays. Cached source: instant redraw, silent background refresh when stale. Uncached: commit, then the shipped loading state. |
| Remove | `x` / `X` / `Delete` -> `ConfirmDialog` -> cache deleted. Active removed: settings cleared, guide behind is first-run; Sources stays open while other sources remain. |
| Xtream | `c` in Sources, the `Add Xtream login` row, or the link row in the add / first-run forms. Four fields, password echo-masked, never re-shown. |

---

## 1. Flows

### 1.1 Surfaces

```
Guide overlay (card, scrim, header, banner, footer unchanged)
  Header ........ search line (search / list)  |  screen title (sources, forms)
  Banner ........ unchanged and visible in every mode (a playlist error is a reason to switch)
  Body
    search, list  group column (+ pinned Sources row)  |  channel list      <- shipped
    first run     shipped empty-state column with the Playlist / EPG fields inside it
    sources       sources list (rows + separator + two action rows); column hidden
    sourceEdit    centered form column: Label / Playlist / EPG (+ Xtream link row when adding)
    sourceXtream  centered form column: Label / Server / Username / Password
    confirmRemove ConfirmDialog over the sources list
  Footer ........ status (left) + mode-aware hints (right)                  <- shipped structure
```

### 1.2 First run (S1)

Trigger: the guide opens while `service.configured` is false
(`emptyKind === "unconfigured"`), or the active source was removed.

1. The guide opens straight into `sourceEdit` with `origin: "firstRun"`.
   The empty-state column keeps its glyph and title (`No playlist
   configured`), the prose becomes one line, and the command box is replaced
   by the `Playlist` field (focused, caret visible, `PanelKeyCatcher`
   blocked), the `EPG` field, the link row `Use Xtream login instead`, a
   `Load` button, and one caption line with the terminal command (S5 parity;
   clicking it still copies, as shipped).
2. The user pastes (`Ctrl+V`, `Shift+Insert`, middle click) or types. Every
   arrival is sanitized (2.3): trimmed, newlines and control characters
   removed, capped at `LIMITS.url`. A pasted value that has a query string or
   userinfo is shown masked immediately (4.4); text the user types is never
   masked while they type it.
3. `Tab` / `Down` moves to `EPG` (optional). `Enter` in either field submits;
   `Enter` on the `Load` button too.
4. Validation is synchronous (5.4). On failure the error line appears under
   the fields, focus moves to the offending field, nothing else changes.
5. On success the form freezes (`enabled: false` on fields, link row and
   buttons) and the result line reads `Fetching from tv.example.net...`
   (`Reading the file...` for a path). Footer hint: `Esc cancel`. The probe
   fetches into the new source's own cache directory and does not touch the
   current settings or the current cache.
6. Success: the source is recorded (label derived per 5.6), `playlistUrl` /
   `epgUrl` are written through `shell.updateEntryInline`, the source is
   active, the guide leaves `sourceEdit` for `search` mode and renders the
   channels; the footer status shows the transient `1,475 channels in 28
   groups` for `transientMs`. An EPG URL loads in the background exactly as a
   refresh does today (banner on failure, never blocking).
7. Failure: the form thaws, the result line becomes the error line
   `HTTP 403 Forbidden from tv.example.net` (reason and host only, never the
   URL), focus returns to `Playlist`, nothing was saved and no setting
   changed (S8).
8. `Esc` while fetching cancels the probe (`service.cancelProbe()`), thaws
   the form and keeps the typed values.

Exits: `Esc` per 2.3 (clear first, then close the guide). `Use Xtream login
instead` (Tab to it, `Enter`; or click) opens `sourceXtream` with the same
origin; `Esc` there returns to this form with its values intact.

Saved sources but none active (after S7): the same screen, plus the link row
`Saved sources (3)` before the Xtream link. It is Tab-reachable and
clickable (a printable key cannot open Sources here because it would type
into the field). See wireframe 3.1.6.

### 1.3 Opening Sources (S2)

- List mode: `o`. Search mode: `Tab` then `o`, or the mouse.
- Mouse: click the pinned `Sources` row under the group column (present
  whenever the column is; `h` / `l` never land on it, it is not a scope).
- First run: the `Saved sources (n)` link row.

On entry: `mode = "sources"`, `returnMode` remembers `search` or `list`,
the column and channel list are replaced by the sources list, the header
shows `Sources` left and `3 sources` right, the cursor sits on the active
source (row 0 when none is active; the `Add source` row when the list is
empty), `PointerMoveGate.reset()`. Query and scope are kept on the guide
state so a plain return restores the exact view.

Returning: `Esc` or `o` -> `returnMode`, nothing else changes (cursor,
scope, query survive) unless the active source changed (1.4).

### 1.4 Switching (S3)

`Enter` on a source row, or a click:

1. Already active: return to the guide, no reload (parity with `Enter` on the
   playing row).
2. Otherwise `service.switchSource(id)`: shell.json gets that source's
   `playlistUrl` / `epgUrl`, the service points at its cache directory, the
   in-memory channels are replaced from its `channels.json`, `lastUsedAt` is
   stamped.
3. The guide returns to `search` mode with an empty query, scope by the
   shipped `initialScope` rule (Favorites when it has entries, else All),
   cursor by `cursorFor`. Footer transient: `Switched to NAS Tvheadend - 84
   channels`. From now on, whenever two or more sources exist, the footer
   status is prefixed with the active label: `NAS Tvheadend - 84 channels -
   updated 09:12`.
4. Cache older than `refreshMinutes`: the service refreshes in the background
   and the footer shows `Refreshing...` through the shipped
   `service.refreshing` path; success is silent (timer-refresh rules, R12),
   failure shows the shipped banner.
5. No cache yet (added by CLI, never fetched; or cache deleted): the switch
   still commits and the shipped `Loading playlist... / Fetching from <host>`
   state shows. On failure the shipped error state appears; its footer hint
   gains `o sources` so the previous source is two keystrokes away.

`Space` on a row: steps 2 and 4 only, the guide stays in `sources`; the
check glyph and bold label move to that row at once and the transient shows
in the footer. This lets a user try two providers without leaving the list.

### 1.5 Adding (S2, S4)

`a` in `sources`, or `Enter` / click on the `Add source` row ->
`sourceEdit` with `origin: "sources"`, empty fields, focus on `Playlist`,
header title `Add source`. Fields in order: `Label` (optional; its
placeholder live-updates to the label 5.6 would derive from the current
`Playlist` value), `Playlist`, `EPG`, then the link row `Use Xtream login
instead`, then `Cancel` / `Save`.

Submit is the first-run flow (validate -> probe -> commit), except the return
goes to `sources` with the cursor on the new row and the transient `Added
tv.example.net - 1,475 channels in 28 groups`. The new source becomes
active: the user pasted it to use it, and switching back is two keystrokes.

### 1.6 Editing (S4, S6)

`e` / `E` in `sources`, or the pencil action button on the cursor row ->
`sourceEdit` with `sourceId`, header title `Edit source`, fields pre-filled:
`Label` (focused, caret at the end), `Playlist` masked, `EPG` masked (empty
when none). No Xtream link row when editing.

- Label-only or EPG-only change: `Enter` validates and commits at once. If
  the source is active, an EPG change triggers the background EPG refresh as
  today. Return to `sources`, cursor on the row, transient `Saved`.
- Playlist URL changed: validate, probe into the new hash's cache directory;
  on success the record moves to the new hash, the old cache directory is
  deleted, settings are updated when the source is active and the guide
  redraws from the new cache. Return with `Saved - 1,475 channels in 28
  groups`.
- Xtream-built sources are edited through this same form: the built URLs
  show masked; there is no password field any more (S6). To change
  credentials, reveal and edit the URL, or add a new Xtream login.

### 1.7 Removing (S7)

`x`, `X` or `Delete` in `sources`, or the close-circle action button ->
`confirmRemove`: a `Ui.ConfirmDialog` above the list, message `Remove "NAS
Tvheadend"? Its cache is deleted too.` (active source: `Remove "Provider"?
It is the active source; the guide returns to setup.`), buttons `Cancel` /
`Remove`, `Remove` preselected exactly as the clipboard preselects `Delete`.

- Confirm: the record and its cache directory are deleted; the cursor stays
  at the same index, clamped, as removing from Favorites does; transient
  `Removed NAS Tvheadend`. Active source removed: `playlistUrl` / `epgUrl`
  are cleared, the guide behind Sources is now first-run, the transient reads
  `Removed Provider - no active source`; Sources stays open while other
  sources remain (one `Enter` picks another); when the list is now empty,
  Sources closes and the first-run form shows with focus in `Playlist`.
- `Cancel`, `Esc`, dialog-scrim click: back to `sources`, cursor unchanged,
  key focus restored with `Qt.callLater(keyCatcher.forceActiveFocus)`.

### 1.8 Xtream form (S6)

`c` / `C` in `sources`, `Enter` / click on the `Add Xtream login` row, or
the link row in the first-run / add forms -> `sourceXtream`, header title
`Add Xtream login`. Fields: `Label` (optional, placeholder = server host),
`Server` (focused), `Username`, `Password` (`password: true`). `Enter`
validates (5.4), builds

```
<server>/get.php?username=<u>&password=<p>&type=m3u_plus&output=ts
<server>/xmltv.php?username=<u>&password=<p>
```

with `<u>` / `<p>` percent-encoded, then runs the add flow (probe -> commit
-> return to `sources`, or to the guide when the origin is first run). The
saved record is an ordinary source with `kind: "xtream"` (used only for the
default label and the `Xtream` segment in the row detail). The password
value is dropped from memory as soon as the URLs are built; the form is
never shown pre-filled.

### 1.9 Modes and transitions

```
                open(), not configured                 Saved sources link
  closed --------------------------------> sourceEdit[firstRun] -----------------> sources
    ^                                        |  ^   ^                                ^  |
    |  Esc with every field empty            |  |   |  Esc (values kept)             |  |
    +----------------------------------------+  |   +------- sourceXtream[firstRun]  |  |
                                                |             ^  Xtream link row     |  |
                                                +-------------+                      |  |
                          probe ok: every form lands in search mode -------------+   |  |
                                                                                 |   |  |
                open(), configured           Tab, /                   o, Sources row |  |
  closed ---------------------------> search <----------> list --------------------------+
    ^    Esc, empty query               ^  |     Tab       ^                Esc, o,      |
    +-----------------------------------+  +---------------+                Enter/switch |
                                                                                         |
  sources --a, Add row------------> sourceEdit[sources]   --Esc, save ok--------------> sources
  sources --c, Xtream row---------> sourceXtream[sources] --Esc, save ok--------------> sources
  sourceEdit[sources, adding] --Xtream link row--> sourceXtream[sources] --Esc--> sourceEdit (values kept)
  sources --x, X, Delete----------> confirmRemove --Esc, Cancel, Remove--------------> sources
                                                  --Remove, list now empty-----------> sourceEdit[firstRun]
```

| From | Key / gesture | To | Notes |
|---|---|---|---|
| closed | `open()` unconfigured | `sourceEdit[firstRun]` | shipped `emptyKind === "unconfigured"` |
| closed | `open()` configured | `search` | shipped |
| `list` | `o` | `sources` | `returnMode = "list"` |
| `search` | Sources row click | `sources` | `returnMode = "search"` |
| `sourceEdit[firstRun]` | `Saved sources (n)` | `sources` | `returnMode = "sourceEdit"`; `Esc` in Sources returns to the form |
| `sources` | `Esc`, `o` | `returnMode` | view restored |
| `sources` | `Enter`, click | `search` | switched; query cleared; transient |
| `sources` | `Space` | `sources` | switched in place |
| `sources` | `a`, Add row | `sourceEdit[sources]` | |
| `sources` | `e`, pencil | `sourceEdit[sources]` with `sourceId` | |
| `sources` | `c`, Xtream row | `sourceXtream[sources]` | |
| `sources` | `x`, `X`, `Delete`, close-circle | `confirmRemove` | |
| `confirmRemove` | `Esc`, `Cancel`, scrim | `sources` | |
| `confirmRemove` | `Remove` | `sources` or `sourceEdit[firstRun]` | the latter only when no source is left |
| any form | `Esc` (2.3) | origin (`sources`) / clears / closes (`firstRun`) | |
| any form | probe ok | `search` (`firstRun`) or `sources` | transient per 5.3 |
| any form | `Esc` while fetching | same form, thawed | `cancelProbe()` |
| `sourceXtream` (from a form) | `Esc` | that form | values kept |
| any mode | scrim click | closed | as the clipboard; only the ConfirmDialog's own scrim cancels the dialog instead |

---

## 2. Keyboard map

Model: the shipped two-layer handler, extended.

- `PanelKeyCatcher { blocked: root.searchMode || root.formActive || root.confirmOpen }`.
- `sources` is a list mode: the catcher is live; `j`/`k`/arrows arrive as
  `moveRequested`, `Enter`/`Space` as `activateRequested` (distinguished with
  the shipped `enterPending` trick), `x`/`X` as `deleteRequested`, `Esc` as
  `closeRequested`, letters as `textKey`.
- `sourceEdit` / `sourceXtream` are text modes: the focused `Ui.TextField`
  owns keys (network precedent). The form root has `Keys.priority:
  Keys.BeforeItem` and handles only `Tab`, `Shift+Tab`, `Up`, `Down`,
  `Enter`, `Esc`, `Ctrl+U`, `Ctrl+R`, and the masked-field replacement
  rules before the field sees the event; everything else falls through to
  Qt's native editing (caret, selection, `Ctrl+Backspace` word delete,
  `Ctrl+V` and `Shift+Insert` paste, `Ctrl+A` select all).
- `confirmRemove` routes every key to `ConfirmDialog.handleKey` first, as
  the clipboard does.

### 2.1 Guide, list mode (amendment to UX.md 3.1)

| Key | Action |
|---|---|
| `o` / `O` | Open Sources. |

Everything else is unchanged. Footer hint line gains a trailing `o sources`
(the shipped `ElideLeft` keeps it visible on narrow cards).

### 2.2 `sources` mode

| Key | Action |
|---|---|
| `j` / `Down` | Next row; wraps. Action rows are rows. |
| `k` / `Up` | Previous row; wraps. |
| `PgDn` / `PgUp` / `Home` / `End` | As in the guide (page, first, last). |
| `Enter` | Source row: switch and return to the guide (1.4). `Add source` row: add. `Add Xtream login` row: Xtream form. |
| `Space` | Source row: switch and stay. Action rows: same as `Enter`. |
| `a` / `A` | Add source (URL form). |
| `c` / `C` | Add Xtream login (credentials form). |
| `e` / `E` | Edit the cursor source. No-op on action rows. |
| `x` / `X` / `Delete` | Remove the cursor source, with confirmation. No-op on action rows. |
| `o` / `O`, `Esc` | Back to the guide (`returnMode`). |
| `h` / `l` / `Left` / `Right`, `Tab`, `/`, `r`, `s`, `f`, digits | Ignored (no column, no search, no refresh here; documented in 8). |

No `r` rename: `e` opens the form with `Label` focused, so renaming is
`e`, type, `Enter`.

### 2.3 Text fields (`sourceEdit`, `sourceXtream`, first run)

| Key | Plain or revealed field | Masked field (4.4) |
|---|---|---|
| printable | Insert at the caret (Qt). | Replace the whole value with the character; the field is now plain (the user is typing). |
| `Backspace` | Delete one character (Qt). | Clear the whole value. |
| `Ctrl+Backspace` | Delete the previous word (Qt `DeleteStartOfWord`). | Clear the whole value. |
| `Ctrl+U` | Clear the field (form handler; kit convention from `Util.editsFilter`). | Clear the whole value. |
| `Ctrl+V`, `Shift+Insert`, middle click | Paste at the caret (Qt), then sanitize. | Replace the whole value with the sanitized paste; re-mask if it has anything to mask. |
| `Ctrl+A` | Select all (Qt). | No-op. |
| `Left` / `Right` / `Home` / `End` | Caret (Qt). | No-op; the footer shows `Ctrl+R reveal`. |
| `Ctrl+R` | Re-mask (only when the value has something to mask; otherwise no-op). | Reveal: the real value appears, caret at the end, normal editing. |
| `Tab` / `Down` | Next field, then the link rows and buttons, then wrap (7.3 order). Leaving a revealed field re-masks it. | Same. |
| `Shift+Tab` / `Up` | Previous field; wraps. | Same. |
| `Enter` | Submit the form (`onAccepted` precedent). On a focused button or link row: activate it. | Same. |
| `Esc` | See below. | Same. |

Sanitize (Model.js `sanitizeInput(text, limit)`, applied in
`onTextChanged` so it covers every paste path, including primary selection):
strip `\r`, `\n` and other C0/C1 control characters; cap at the field's
limit (`LIMITS.url` 2048, `LIMITS.label` 40, `LIMITS.server` 256,
`LIMITS.user` / `LIMITS.pass` 128). URL fields are also trimmed on paste;
every field is trimmed on submit (so a label can be typed with spaces).

Esc, by origin:

- `sourceEdit[sources]`, `sourceXtream[sources]`: one press cancels to
  `sources` (network passphrase precedent: `Keys.onEscapePressed:
  cancelPasswordPrompt()`). Nothing typed is kept; nothing was saved.
  Footer says `Esc cancel`. The clear gesture inside a form is `Ctrl+U`.
- `sourceEdit[firstRun]`, `sourceXtream[firstRun]`: the search-line rule
  ("clear first, then leave"), because closing the whole overlay on a stray
  `Esc` while a pasted URL sits on screen is the worse outcome:
  1. focused field has text -> clear it (footer `Esc clear`);
  2. focused field empty, another field has text -> focus moves to that
     field (footer `Esc clear`); nothing closes while text is on screen;
  3. every field empty -> `sourceXtream[firstRun]` returns to the first-run
     form; `sourceEdit[firstRun]` closes the guide (footer `Esc close`).
- While fetching: `Esc` cancels the probe and thaws the form (any origin).

### 2.4 `confirmRemove`

Exactly `ConfirmDialog.handleKey`: `Left` / `Right` / `Tab` / `Shift+Tab`
toggle the selected button, `Enter` activates it, `Esc` cancels. No `y` /
`n` (the kit has none).

### 2.5 Mouse

| Where | Gesture | Action |
|---|---|---|
| Group column, pinned `Sources` row | click | Open Sources. Hover paints the kit hover fill (it is a button, not a scope). Wheel over the column still moves the scope selection and never reaches this row. |
| Sources row | hover | Cursor follows through `PointerMoveGate` (single highlight rule). |
| Sources row | click | Switch (as `Enter`). |
| Cursor row, pencil / close-circle buttons | click | Edit / remove. Buttons exist only on the cursor row; hovering a button does not move the cursor (PanelActionButton contract). |
| `Add source` / `Add Xtream login` rows | click | As `Enter`. |
| Sources list | wheel | Scrolls the list (Flickable default). |
| Form field | click | Focus it (caret at click point in plain / revealed fields; a masked field gains focus but stays masked). |
| Eye button | click | Toggle reveal for that field (as `Ctrl+R`). |
| Link rows (`Use Xtream login instead`, `Saved sources (n)`) | click | Follow. |
| `Load` / `Save` / `Cancel` | click | Submit / cancel. |
| Terminal command caption (first run) | click | Copies with `wl-copy`, transient `Copied` (shipped). |
| ConfirmDialog | click button / click its scrim | As the kit. |
| Overlay scrim | click | Close the guide, any mode (clipboard behavior); the form is discarded. |

---

## 3. Wireframes

Proportions as UX.md 4: 96 characters for a `Style.space(960)` card, 20 for
the `Style.space(200)` column, `>` marks the cursor row. `[ ... ]` is a
`Ui.TextField`; `|` inside a field is the caret; `..` stands for the elision
glyph. Glyphs are real Nerd Font glyphs (table in 4.6). The character grid
is coarser than the real caption font, so footer lines that fit at
`Style.space(960)` are drawn elided here the way the shipped footer elides
them: the status shrinks (`ElideRight`), the hints keep their width up to
70% of the card and elide left only below that.

### 3.1 First run

#### 3.1.1 Before paste (Playlist focused)

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Search channels...                                                                            |
|                                                                                                |
|                                                                                                |
|                                             󰔂                                                  |
|                                                                                                |
|                                    No playlist configured                                      |
|                                                                                                |
|                     Paste or type your M3U URL or path, then press Enter                       |
|                                                                                                |
|            Playlist   [ |https://host/playlist.m3u or /path/to/list.m3u                 ]      |
|            EPG        [ optional - XMLTV URL, .xml or .xml.gz                           ]      |
|                                                                                                |
|                       Use Xtream login instead                                 [ Load ]        |
|                                                                                                |
|               Or from a terminal:  omarchy bar set io.github.rmcdavid.iptv playlistUrl <url>   |
|                                                                                                |
|                                 Enter load - Tab next field - Ctrl+V paste - Esc close         |
+------------------------------------------------------------------------------------------------+
```

Notes: the shipped empty-state column (`Math.min(body.width, Style.space(640))`
wide, centered) hosts the form. The fields sit where the command box was.
The terminal line is `Style.font.caption` at opacity 0.7 and keeps the
shipped click-to-copy. Placeholder text in the field uses the kit's
`placeholderTextColor`. The eye slot after each URL field is reserved but
empty (nothing to mask).

#### 3.1.2 After paste (both URLs masked)

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Search channels...                                                                            |
|                                                                                                |
|                                                                                                |
|                                             󰔂                                                  |
|                                                                                                |
|                                    No playlist configured                                      |
|                                                                                                |
|                     Paste or type your M3U URL or path, then press Enter                       |
|                                                                                                |
|            Playlist   [ http://tv.example.net:8080/get.php?username=****&passwor..      ] 󰈈    |
|            EPG        [ http://tv.example.net:8080/xmltv.php?username=****&pass..       ] 󰈈    |
|                                                                                                |
|                       Use Xtream login instead                                 [ Load ]        |
|                                                                                                |
|               Or from a terminal:  omarchy bar set io.github.rmcdavid.iptv playlistUrl <url>   |
|                                                                                                |
|                    Enter load - Tab next field - Ctrl+R reveal - Ctrl+V replace - Esc clear    |
+------------------------------------------------------------------------------------------------+
```

Notes: the pasted values were sanitized and masked on arrival (4.4). The eye
button appears at the end of each field that has something to mask. Footer
hints switched to the masked-field set. The caret is hidden while masked.

#### 3.1.3 Validation error

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Search channels...                                                                            |
|                                                                                                |
|                                                                                                |
|                                             󰔂                                                  |
|                                                                                                |
|                                    No playlist configured                                      |
|                                                                                                |
|                     Paste or type your M3U URL or path, then press Enter                       |
|                                                                                                |
|            Playlist   [ tv.example.net/list.m3u|                                        ]      |
|            EPG        [ optional - XMLTV URL, .xml or .xml.gz                           ]      |
|                                                                                                |
|                       󰀦  Start with http://, https://, or / for a local file                   |
|                                                                                                |
|                       Use Xtream login instead                                 [ Load ]        |
|                                                                                                |
|                                 Enter load - Tab next field - Ctrl+V paste - Esc clear         |
+------------------------------------------------------------------------------------------------+
```

Notes: the error line uses the banner's urgent treatment (4.3) and sits in
the field column under the last field. The focused field's `accent` is
`Color.urgent` while it carries the error (uptime-monitor cron precedent);
the words carry the meaning. The error clears on the next edit of that
field.

#### 3.1.4 Fetching, then the fetch failed

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|            Playlist   [ http://tv.example.net:8080/get.php?username=****&passwor..      ] 󰈈    |
|            EPG        [ http://tv.example.net:8080/xmltv.php?username=****&pass..       ] 󰈈    |
|                                                                                                |
|                       󰇘  Fetching from tv.example.net...                                       |
|                                                                                                |
|                       Use Xtream login instead                                 [ Load ]        |
|                                                                                                |
|                                                                                   Esc cancel   |
+------------------------------------------------------------------------------------------------+
```

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|            Playlist   [ http://tv.example.net:8080/get.php?username=****&passwor..      ] 󰈈    |
|            EPG        [ http://tv.example.net:8080/xmltv.php?username=****&pass..       ] 󰈈    |
|                                                                                                |
|                       󰀦  HTTP 403 Forbidden from tv.example.net                                |
|                                                                                                |
|                       Use Xtream login instead                                 [ Load ]        |
|                                                                                                |
|                    Enter load - Tab next field - Ctrl+R reveal - Ctrl+V replace - Esc clear    |
+------------------------------------------------------------------------------------------------+
```

Notes: while fetching the fields, link row and button are disabled (kit
disabled dimming), the result line uses the neutral banner fill with the
loading glyph, and the only hint is `Esc cancel`. On failure the same line
turns urgent with the reason and host; the previous configuration was never
touched (S8).

#### 3.1.5 Success: the guide, with the result in the footer

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Search channels...                                                        All - 1,475 channels|
|                                                                                                |
|  Recent           3 |                                                                          |
|  Favorites        6 |> 󰓎  Sky Sports Main Event                                     until 21:30|
|  All          1,475 |>     Now: Premier League: Arsenal v Spurs - Next: Match Replay           |
|                     |>     ===============================-----------------------------------  |
|  GROUPS             |                                                                          |
|  UK | SPORTS    142 |  󰓎  BBC One HD                                                until 20:00|
|  ...                |      Now: EastEnders - Next: The One Show                                |
|  ------------------ |                                                                          |
|  󰐑 Sources     1 |                                                                             |
|                                                                                                |
|  1,475 channels in 28 g..  Enter play - Up/Down move - Left/Right group - Tab keys - Esc close |
+------------------------------------------------------------------------------------------------+
```

Notes: the form is gone; the footer status shows `1,475 channels in 28
groups` for `transientMs`, then the normal status. The pinned `Sources` row
is now visible under the column with count `1`.

#### 3.1.6 Saved sources exist, none active (after removing the active one)

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|                                             󰔂                                                  |
|                                                                                                |
|                                    No playlist configured                                      |
|                                                                                                |
|                     Paste or type your M3U URL or path, then press Enter                       |
|                                                                                                |
|            Playlist   [ |https://host/playlist.m3u or /path/to/list.m3u                 ]      |
|            EPG        [ optional - XMLTV URL, .xml or .xml.gz                           ]      |
|                                                                                                |
|                       Saved sources (3)     Use Xtream login instead           [ Load ]        |
|                                                                                                |
|                                 Enter load - Tab next field - Ctrl+V paste - Esc close         |
+------------------------------------------------------------------------------------------------+
```

### 3.2 Sources list

#### 3.2.1 Three sources, cursor on the active one (action buttons visible)

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Sources                                                                            3 sources  |
|                                                                                                |
|> 󰄬 Provider                                              used 21:30   󰏫  󰅙                     |
|>         active - tv.example.net - Xtream - 1,475 channels in 28 groups - EPG                  |
|                                                                                                |
|          NAS Tvheadend                                                        used yesterday   |
|          nas.local:9981 - 84 channels in 6 groups - EPG                                        |
|                                                                                                |
|          iptv-org                                                                 never used   |
|          iptv-org.github.io - not loaded yet                                                   |
|                                                                                                |
|          channels.m3u                                                             used 3 Sep   |
|          local file - 12 channels in 1 group                                                   |
|                                                                                                |
|  --------------------------------------------------------------------------------------------  |
|  󰐕   Add source                                                                                |
|  󰌆   Add Xtream login                                                                          |
|                                                                                                |
|  Provider - 1,475..   j/k move - Enter switch - a add - c Xtream - e edit - x remove - Esc back|
+------------------------------------------------------------------------------------------------+
```

Notes: rows are the guide's two-line rows. The active source has the check
glyph in the lead slot, a bold label and the word `active` opening its
detail line. The cursor row shows the two `PanelActionButton`s at its right
edge; the right meta shifts left to make room. `iptv-org` was added by CLI
and never loaded: `not loaded yet`, `never used`. The local file shows
`local file` as its host (Model.hostOf) and the file name as its label. The
separator and the two action rows close the list; they scroll with it.

#### 3.2.2 One source, no history yet

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Sources                                                                             1 source  |
|                                                                                                |
|> 󰄬 tv.example.net                                                          never used          |
|>         active - tv.example.net - 1,475 channels in 28 groups                                 |
|                                                                                                |
|  --------------------------------------------------------------------------------------------  |
|  󰐕   Add source                                                                                |
|  󰌆   Add Xtream login                                                                          |
|                                                                                                |
|  1,475 channels -..   j/k move - Enter switch - a add - c Xtream - e edit - x remove - Esc back|
+------------------------------------------------------------------------------------------------+
```

Notes: a source that was configured but never switched to has `never used`
(`lastUsedAt` 0). With a single source the footer status carries no label
prefix.

#### 3.2.3 No sources at all (only reachable through external edits of state.json)

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Sources                                                                           No sources  |
|                                                                                                |
|> 󰐕   Add source                                                                                |
|  󰌆   Add Xtream login                                                                          |
|                                                                                                |
|                                                            j/k move - Enter open - Esc back    |
+------------------------------------------------------------------------------------------------+
```

#### 3.2.4 Narrow screen (card under `Style.space(720)`)

```
+------------------------------------------------------------+
|                                                            |
|  Sources                                      3 sources    |
|                                                            |
|> 󰄬 Provider                                 󰏫  󰅙           |
|>         active - used 21:30 - tv.example.net - Xtre..     |
|                                                            |
|          NAS Tvheadend                                     |
|          used yesterday - nas.local:9981 - 84 channe..     |
|                                                            |
|          iptv-org                                          |
|          never used - iptv-org.github.io - not loade..     |
|                                                            |
|  ------------------------------------------------------    |
|  󰐕   Add source                                            |
|  󰌆   Add Xtream login                                      |
|                                                            |
|  Provider - 1..   ..c Xtream - e edit - x remove - Esc back|
+------------------------------------------------------------+
```

Notes: the right meta is hidden; `used ...` moves to the detail line right
after `active`, before the host, so the most useful words survive the
right elision. Action buttons stay. The footer hints elide left as shipped.

#### 3.2.5 A row, zoomed

```
 lead(24)  label (title; Font.Bold when active) ......... right meta (caption, 0.52)  actions (cursor row only)
 |         |                                               |                           |
 v         v                                               v                           v
 󰄬         Provider                                        used 21:30                 󰏫  󰅙
           active - tv.example.net - Xtream - 1,475 channels in 28 groups - EPG        <- bodySmall, 0.52
           ^ first segment is the word "active" only on the active source

 same row, not active, never loaded:
           iptv-org                                        never used
           iptv-org.github.io - not loaded yet
```

### 3.3 Edit form

#### 3.3.1 Editing an Xtream-built source (URLs masked, Label focused)

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Edit source                                                                                   |
|                                                                                                |
|                                                                                                |
|            Label      [ Provider|                                                       ]      |
|            Playlist   [ http://tv.example.net:8080/get.php?username=****&passwor..      ] 󰈈    |
|            EPG        [ http://tv.example.net:8080/xmltv.php?username=****&pass..       ] 󰈈    |
|                                                                                                |
|                                                                    [ Cancel ]  [ Save ]        |
|                                                                                                |
|                                     Enter save - Tab next field - Ctrl+V paste - Esc cancel    |
+------------------------------------------------------------------------------------------------+
```

#### 3.3.2 After `Ctrl+R` on Playlist (revealed, caret at the end)

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Edit source                                                                                   |
|                                                                                                |
|                                                                                                |
|            Label      [ Provider                                                        ]      |
|            Playlist   [ ..get.php?username=tomasz&password=s3cret&type=m3u_plus&output=ts| ] 󰈉 |
|            EPG        [ http://tv.example.net:8080/xmltv.php?username=****&pass..       ] 󰈈    |
|                                                                                                |
|                                                                    [ Cancel ]  [ Save ]        |
|                                                                                                |
|                                        Enter save - Tab next field - Ctrl+R hide - Esc cancel  |
+------------------------------------------------------------------------------------------------+
```

Notes: revealed, the field is an ordinary `Ui.TextField` scrolled to keep
the caret visible; the eye button flips to eye-off and the footer offers
`Ctrl+R hide`. `Tab` away re-masks. `EPG` stays masked independently.

#### 3.3.3 Narrow screen (labels above fields)

```
+------------------------------------------------------------+
|                                                            |
|  Edit source                                               |
|                                                            |
|    Label                                                   |
|    [ Provider|                                          ]  |
|    Playlist                                                |
|    [ http://tv.example.net:8080/get.php?username=**.. ] 󰈈  |
|    EPG                                                     |
|    [ http://tv.example.net:8080/xmltv.php?username=.. ] 󰈈  |
|                                                            |
|                                     [ Cancel ]  [ Save ]   |
|                                                            |
|     Enter save - Tab next field - Ctrl+V paste - Esc cancel|
+------------------------------------------------------------+
```

### 3.4 Xtream form

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Add Xtream login                                                                              |
|                                                                                                |
|                                                                                                |
|            Label      [ tv.example.net                                                  ]      |
|            Server     [ http://tv.example.net:8080|                                     ]      |
|            Username   [                                                                 ]      |
|            Password   [                                                                 ]      |
|                                                                                                |
|                       Builds the get.php (m3u_plus, ts) and xmltv.php URLs. The password       |
|                       is stored in those URLs and never shown again.                           |
|                                                                                                |
|                                                                    [ Cancel ]  [ Save ]        |
|                                                                                                |
|                                              Enter save - Tab next field - Esc cancel          |
+------------------------------------------------------------------------------------------------+
```

Filled in and submitted (password echo-masked by the kit, then fetching):

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|            Label      [ tv.example.net                                                  ]      |
|            Server     [ http://tv.example.net:8080                                      ]      |
|            Username   [ tomasz                                                          ]      |
|            Password   [ ******|                                                         ]      |
|                                                                                                |
|                       󰇘  Fetching from tv.example.net...                                       |
+------------------------------------------------------------------------------------------------+
```

Notes: the `Label` placeholder shows the host derived from `Server` as it is
typed. The password field uses `password: true` (Qt's echo character, not
our `****` mask). After `Save` the built URLs are probed like any add; on
success the row detail carries the `Xtream` segment.

### 3.5 Remove confirmation

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Sources                                                                            3 sources  |
|                                                                                                |
|> 󰄬 Provider                                                                used 21:30          |
|>         active - tv.example.net - Xtream - 1,475 channels in 28 groups - EPG                  |
|                                                                                                |
|          NAS Tvhe   +--------------------------------------------------------+   ed yesterday  |
|          nas.loca   |                                                        |                 |
|                     |  Remove "NAS Tvheadend"? Its cache is deleted too.     |                 |
|          iptv-org   |                                                        |   never used    |
|          iptv-org   |                              [ Cancel ]   [[ Remove ]] |                 |
|                     +--------------------------------------------------------+                 |
|          channels.m3u                                                             used 3 Sep   |
|          local file - 12 channels in 1 group                                                   |
|                                                                                                |
|  Provider - 1,475 channels - updated 12:40       Left/Right choose - Enter confirm - Esc cancel|
+------------------------------------------------------------------------------------------------+
```

Notes: `ConfirmDialog` with the guide's menu tokens (`background`,
`foreground`, `scrim`, `selectedBackground`, `selectedText`, `fontFamily`,
`cornerRadius` bound as the clipboard binds them). `[[ Remove ]]` marks the
preselected destructive button (urgent border and tint from the kit).

### 3.6 Switching transient (cache swap, then background refresh)

Right after `Enter` on `NAS Tvheadend` (cached 09:12, older than
`refreshMinutes`):

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Search channels...                                                      Favorites - 2 channels|
|                                                                                                |
|  Recent           1 |                                                                          |
|  Favorites        2 |> 󰓎  Arte HD                                                   until 21:15|
|  All             84 |>     Now: Karambolage - Next: Tracks                                     |
|                     |>     ====----------------------------------------------------------      |
|  GROUPS             |                                                                          |
|  Nachrichten     12 |  󰓎  ZDF HD                                                    until 20:15|
|  Sport            9 |      Now: heute journal - Next: Sportstudio                              |
|  ...                |                                                                          |
|  ------------------ |                                                                          |
|  󰐑 Sources     3 |                                                                             |
|                                                                                                |
|  Switched to NAS Tvheade..  Enter play - Up/Down move - Left/Right group - Tab keys - Esc close|
+------------------------------------------------------------------------------------------------+
```

Then, in order: after `transientMs` the status becomes `NAS Tvheadend - 84
channels - cached 09:12`; while the background refresh runs it reads
`Refreshing...` (shipped `service.refreshing`); when it lands, `NAS
Tvheadend - 84 channels - updated 21:32`. Success is silent (no
notification, timer-refresh rules); failure shows the shipped banner
`Playlist refresh failed (...) - showing cached copy from 09:12 - r retry`.

### 3.7 The pinned Sources row under the group column

```
  Recent           3 |
  Favorites        6 |
  All          1,204 |
                     |
  GROUPS             |
  UK | SPORTS    142 |
  UK | ENTERTAIN  96 |
  UK | NEWS       38 |
  ...                |     <- the group ListView scrolls; everything above this line is inside it
  DE | SPORT      33 |
  ------------------ |     <- separator: Style.normalBorderWidth tall, Util.alpha(Color.menu.border, 0.28)
  󰐑 Sources     3 |     <- pinned row, never scrolls; count = number of saved sources
```

---

## 4. Visual spec (tokens only)

### 4.1 Sources list

| Element | Value |
|---|---|
| list | `ListView` in the body, full body width (column hidden), `clip`, `cacheBuffer: rowHeight * 4`, the shipped edge fades |
| source row height | `detailRowHeight` (shipped: `Math.max(Style.space(52), Style.font.title + Style.font.bodySmall + Style.space(2) + Style.spacing.rowPaddingX * 2)`) |
| action row height | `singleRowHeight` (shipped) |
| row spacing, inner margins, radius | as channel rows: `Style.space(4)`; left/right `Style.space(12)`, top/bottom `Style.space(8)`; `Style.cornerRadius` |
| lead slot | `leadWidth` (`Style.space(24)`), glyph centered, `Style.font.icon` |
| label | `Style.font.title`, `Font.Bold` only on the active source, elide right |
| right meta (last used) | `Style.font.caption`, opacity 0.52, right aligned; hidden when `narrow` |
| detail line | `Style.font.bodySmall`, opacity 0.52, elide right |
| cursor row | `Color.menu.selectedBackground`, `selectedBorderSpec`, label and lead glyph in `Color.menu.selectedText`; meta and detail stay `Color.menu.text` at their opacity (shipped convention) |
| action buttons | two `PanelActionButton`s on the cursor row only, default `size` (`Math.max(Style.space(22), Style.font.icon + Style.spacing.sm * 2)`), `foreground: Color.menu.text`, `fontFamily: Style.font.menuFamily`; remove button `hoverColor: Color.urgent` (kit's urgent flavor); anchored right with `Style.space(6)` between them, vertically centered on the first text line; the right meta anchors to their left with `Style.space(8)` gap |
| separator before the action rows | `Style.normalBorderWidth` tall, `Util.alpha(Color.menu.border, 0.28)` (the shipped column-divider tint), `Style.space(6)` above and below, inset `Style.space(12)` each side |
| action rows | lead glyph + text in `Style.font.title` at opacity 0.7 (they are not sources); cursor treatment identical to source rows |
| header | left `Sources` in `Style.font.heading`, opacity 1 (the search line's slot and font); right `3 sources` in `Style.font.caption`, opacity 0.52 |

### 4.2 Form column (`sourceEdit`, `sourceXtream`, first run)

| Element | Value |
|---|---|
| column | `Math.min(body.width, Style.space(640))`, `anchors.centerIn: body` (the shipped empty-state column) |
| title (forms from Sources) | in the header slot: `Add source` / `Edit source` / `Add Xtream login`, `Style.font.heading`; first run keeps the shipped empty-state title in the column |
| label column | `Style.space(96)` wide, labels left-aligned, vertically centered on their field; a `PanelSectionHeader` (`Style.font.caption`, bold, `Qt.darker(Color.menu.text, 1.4)`) with `fontFamily: Style.font.menuFamily` |
| label -> field gap | `Style.spacing.controlGap` |
| field | `Ui.TextField { foreground: Color.menu.text; accent: Color.accent; font.family: Style.font.menuFamily; font.pixelSize: Style.font.body; horizontalPadding: Style.spacing.controlPaddingX; verticalPadding: Style.spacing.inputPaddingY }`; height is its `implicitHeight`, never set |
| field width | column width - label column - `controlGap` - eye slot (`Style.space(22) + Style.spacing.controlGap`), reserved on every row so all fields align |
| error state on a field | `accent: Color.urgent` while the field carries the current error (focus border and fill follow the kit tokens); reset on the next edit |
| eye button | `PanelActionButton` default size, in the reserved slot, `foreground: Color.menu.text`, visible only when `maskUrl(value) !== value` |
| row gap | `Style.spacing.rowGap` |
| result / error line | `Style.space(28)` tall, radius `Style.cornerRadius`, width = field column (aligned with the fields), `Style.spacing.rowGap` under the last field; fill `Util.alpha(Color.urgent, 0.10)` + glyph in `Color.urgent` for errors, `Style.normalFillFor(Color.menu.text, Color.accent)` + glyph in `Color.menu.text` for fetching and success; text `Style.font.bodySmall`, `Color.menu.text`, elide right; appears with `bannerFadeMs` opacity fade; the line's space is reserved (height kept, opacity 0) so fields never jump |
| link rows | borderless `Ui.Button { focusable: true; bordered: false; fontSize: Style.font.bodySmall; foreground: Color.menu.text; accent: Color.accent }`, left-aligned in the field column, `Style.space(10)` apart |
| buttons | `Ui.Button { focusable: true; bordered: true }` `Cancel` then `Save` / `Load`, right-aligned in the field column, spacing `Style.space(10)` (ConfirmDialog spacing), `Style.spacing.rowGap` under the link rows |
| prose under the Xtream fields | `Style.font.caption`, opacity 0.7, `Text.WordWrap`, in the field column |
| narrow (`narrow` true) | labels move above their field with `Style.spacing.labelGap`; field width = column width - eye slot; buttons stay right-aligned |
| disabled while fetching | `enabled: false` on fields, link rows and buttons; the kit dims them |

### 4.3 Error line vs banner

The form's result line is the shipped banner's inner row (glyph +
`bodySmall` text) with the shipped fills; it is local to the form and never
promoted to the guide banner. The guide banner stays reserved for the
active source's refresh / EPG problems.

### 4.4 Masked URL rendering

```
  value:   http://user:pw@tv.example.net:8080/get.php?username=tomasz&password=s3cret&type=m3u_plus&output=ts#x
  masked:  http://****@tv.example.net:8080/get.php?username=****&password=****&type=****&output=****#****
           ^scheme  ^userinfo ^host:port         ^path    ^every query value  ^key stays       ^fragment

  value:   https://iptv-org.github.io/iptv/index.m3u
  masked:  https://iptv-org.github.io/iptv/index.m3u          (nothing to mask: no eye button, no Ctrl+R)

  value:   /home/dag/tv/channels.m3u
  masked:  /home/dag/tv/channels.m3u                         (paths are never masked)
```

Rules (Model.js `maskUrl(url)`, `MASK = "****"`, unit-tested):

- Mask, in this order: the userinfo before `@` (whole thing -> `****`),
  every `=value` in the query (`key=****`; a key without `=` is kept as is),
  the fragment (`#****`). Fixed four asterisks whatever the length: the
  length of a secret is also a secret.
- Keep: scheme, host, port, path, query keys, separators.
- Never mask local paths or values with nothing to mask (`maskUrl(v) === v`
  means no eye button, `Ctrl+R` no-op).
- Rendering: the `Ui.TextField` shows `masked ? maskUrl(value) : value` and
  is `readOnly` with `cursorVisible: false` while masked; the form state
  holds the real value. The masked string is painted in the field's normal
  color and opacity (the asterisks are the meaning; no tint), `elide:
  Text.ElideRight` style scrolling is not used: the field is scrolled to the
  start so scheme and host are always readable.
- Reveal toggles on `Ctrl+R` or the eye button while the field has focus;
  on reveal the field gets the real value, `readOnly: false`, caret at the
  end. Re-mask on: focus leaving the field, `Enter`, `Esc`, the form closing,
  a paste (new value, masked again), `Ctrl+R` again.
- Eye glyphs: masked -> eye (`Show query - Ctrl+R` tooltip), revealed ->
  eye-off (`Hide query - Ctrl+R`).

### 4.5 Pinned Sources row (group column)

| Property | Value |
|---|---|
| placement | below the group `ListView`, outside it, so it never scrolls: the column becomes `ListView` (fills) + separator + row |
| separator | `Style.normalBorderWidth` tall, `Util.alpha(Color.menu.border, 0.28)`, `Style.space(6)` above and below, full column width |
| row height | `groupEntryHeight` (shipped) |
| glyph | playlist glyph (4.6) in `Style.font.iconSmall`, at the shipped `Style.space(10)` left padding, `Style.spacing.labelGap` before the text |
| text | `Sources`, `Style.font.body`, `Color.menu.text` |
| count | number of saved sources, `Style.font.caption`, opacity 0.45, right aligned at `Style.space(10)` (as group counts) |
| hover | `Style.hoverFillFor(Color.menu.text, Color.accent)`, `Qt.PointingHandCursor`; never `selectedBackground` (it is not a scope); `Behavior on color` 60 ms as `CursorSurface` |
| visibility | with the column (`showColumn`); hidden on narrow cards like the column itself; the `o` key always works |

### 4.6 Glyphs (all present in the installed JetBrains Mono Nerd Font)

| Meaning | Glyph | Codepoint | Nerd Font name | Where |
|---|---|---|---|---|
| Sources (column row, Sources empty state) | 󰐑 | U+F0411 | nf-md-playlist_play | 4.5 |
| Active source marker; success result line | 󰄬 | U+F012C | nf-md-check | row lead slot (Omarchy uses it for Connect) |
| Reveal (masked) | 󰈈 | U+F0208 | nf-md-eye | eye button |
| Hide (revealed) | 󰈉 | U+F0209 | nf-md-eye_off | eye button |
| Add source row | 󰐕 | U+F0415 | nf-md-plus | action row |
| Add Xtream login row | 󰌆 | U+F0306 | nf-md-key | action row |
| Edit (cursor row button) | 󰏫 | U+F03EB | nf-md-pencil | action button |
| Remove (cursor row button) | 󰅙 | U+F0159 | nf-md-close_circle | action button (Omarchy's Forget glyph) |
| Error line | 󰀦 | U+F0026 | nf-md-alert | shipped |
| Fetching line | 󰇘 | U+F01D8 | nf-md-dots_horizontal | shipped |
| First-run icon | 󰔂 | U+F0502 | nf-md-television | shipped |

No color carries meaning on its own: active = glyph + bold + the word
`active`; error = glyph + words; fetching = glyph + words.

### 4.7 Animation

As UX.md 5.8: none for mode changes (`sources` and the forms flip
`visible`), `bannerFadeMs` for the result line, `transientMs` for footer
transients, 60 ms color behavior on the hover-painted pinned row and action
buttons (kit components own it).

### 4.8 What must not be hardcoded

- Everything in UX.md 5.9 (colors, font families, pixel sizes, radius, gaps,
  border widths, timing constants, strings in one `copy` block).
- `MASK` (`"****"`), `LIMITS` (url 2048, label 40, server 256, user 128,
  pass 128), the Xtream URL template, the label derivation rule and the
  last-used formatter: Model.js, unit-tested, shared with the service.
- Field heights: `Ui.TextField.implicitHeight` only. Form width
  `Style.space(640)`, label column `Style.space(96)`, eye slot `Style.space(22)`.
- Key names in hints: the `footerHints` table in Model.js grows the new
  modes; Guide.qml never spells a key.
- The entry key `o`, `a`, `c`, `e`, `x` live in one `SOURCE_KEYS` table in
  Model.js next to the hint table so the two cannot drift.

---

## 5. Microcopy

Tone as UX.md 6: sentence case, terse, verbs first, no exclamation marks,
no "please".

### 5.1 Titles, labels, placeholders

| Where | String |
|---|---|
| Header, Sources | `Sources` |
| Header right, Sources | `3 sources`, `1 source`, `No sources` |
| Header, forms | `Add source`, `Edit source`, `Add Xtream login` |
| First-run title (shipped) | `No playlist configured` |
| First-run prose | `Paste or type your M3U URL or path, then press Enter` |
| First-run terminal caption | `Or from a terminal:  omarchy bar set io.github.rmcdavid.iptv playlistUrl <url>` |
| Field labels, URL form | `Label`, `Playlist`, `EPG` |
| Field labels, Xtream form | `Label`, `Server`, `Username`, `Password` |
| Placeholder, Label | the derived label (5.6) once a URL / server parses, otherwise `optional` |
| Placeholder, Playlist | `https://host/playlist.m3u or /path/to/list.m3u` |
| Placeholder, EPG | `optional - XMLTV URL, .xml or .xml.gz` |
| Placeholder, Server | `http://host:port` |
| Placeholder, Username / Password | empty |
| Link rows | `Use Xtream login instead`, `Saved sources (3)` |
| Buttons | `Load` (first run), `Save`, `Cancel` |
| Xtream prose | `Builds the get.php (m3u_plus, ts) and xmltv.php URLs. The password is stored in those URLs and never shown again.` |
| Action rows | `Add source`, `Add Xtream login` |
| Eye tooltips | `Show query - Ctrl+R`, `Hide query - Ctrl+R` |
| Action button tooltips | `Edit`, `Remove` |
| Column row | `Sources` |

### 5.2 Source rows

| Slot | String |
|---|---|
| label | the source label |
| right meta | `used 21:30` (today), `used yesterday`, `used 3 Sep` (this year), `used 3 Sep 2025` (older), `never used` |
| detail | segments joined with ` - `: `active` (active source only), `<host>` (`local file` for paths), `Xtream` (`kind === "xtream"` only), `1,475 channels in 28 groups` / `1 channel in 1 group` / `not loaded yet` (no cache), `EPG` (when `epgUrl` is set) |
| detail, narrow | `active` (if any), `used ...` / `never used`, then the segments above |

### 5.3 Footer

| Mode / state | Status (left) | Hints (right) |
|---|---|---|
| guide, list mode | shipped | shipped + ` - o sources` |
| guide, 2+ sources | `<label> - 1,475 channels - updated 12:40` (label prefix on the shipped status, cached form included) | shipped |
| guide, error state, sources exist | shipped | `r retry - o sources - Esc close` |
| sources | the guide's status (active source) | `j/k move - Enter switch - a add - c Xtream - e edit - x remove - Esc back` |
| sources, cursor on an action row | same | `j/k move - Enter open - Esc back` |
| form, plain field | same | `Enter save - Tab next field - Ctrl+V paste - Esc cancel` |
| form, masked field | same | `Enter save - Tab next field - Ctrl+R reveal - Ctrl+V replace - Esc cancel` |
| form, revealed field | same | `Enter save - Tab next field - Ctrl+R hide - Esc cancel` |
| form, button or link focused | same | `Enter activate - Tab next field - Esc cancel` |
| Xtream form | same | `Enter save - Tab next field - Esc cancel` |
| first run | shipped (empty) | as the form rows, with `Enter load` instead of `Enter save` and `Esc clear` / `Esc close` per 2.3 |
| fetching | same | `Esc cancel` |
| confirmRemove | same | `Left/Right choose - Enter confirm - Esc cancel` |
| transients | `1,475 channels in 28 groups` (first run), `Added tv.example.net - 1,475 channels in 28 groups`, `Saved`, `Saved - 1,475 channels in 28 groups`, `Switched to NAS Tvheadend - 84 channels`, `Removed NAS Tvheadend`, `Removed Provider - no active source`, `Copied` (shipped) | -- |

Key names at opacity 0.7, verbs at 0.45, as shipped.

### 5.4 Validation errors (synchronous, shown on the result line)

| Code | Trigger | Playlist / Server field | EPG field |
|---|---|---|---|
| `empty` | nothing after trim | `Enter a playlist URL or path` | (EPG is optional; no error) |
| `scheme` | `ftp://`, `rtmp://`, `mailto:`, `javascript:`, a bare host, anything not `http(s)://` or `/` | `Start with http://, https://, or / for a local file` | `EPG: start with http://, https://, or / for a local file` |
| `invalid` | scheme present but no host, spaces or illegal characters, unparsable | `Invalid URL - check the host` | `EPG: invalid URL - check the host` |
| `relative_path` | starts with `~`, `./` or a name | `Use an absolute path (starts with /, not ~)` | `EPG: use an absolute path (starts with /, not ~)` |
| `too_long` | over `LIMITS.url` | `Too long - max 2,048 characters` | `EPG: too long - max 2,048 characters` |
| `duplicate` | same playlist URL as another source (exact after trim) | `Already in Sources as "Provider"` | -- |
| `label_too_long` | over `LIMITS.label` | `Label too long - max 40 characters` | |
| `label_taken` | another source has this label (case-insensitive, trimmed) | `A source named "Provider" already exists` | |
| `server_empty` | | `Enter the server URL` | |
| `server_scheme` | not `http(s)://` | `Server must start with http:// or https://` | |
| `server_path` | anything after `host[:port]` (a `get.php?...` paste) | `Server is just http://host:port - no path` | |
| `user_empty` / `pass_empty` | | `Enter the username` / `Enter the password` | |
| `user_too_long` / `pass_too_long` | over 128 | `Username too long - max 128 characters` / `Password too long - max 128 characters` | |

One error at a time, first failing field in form order; focus moves to it.
No `https://` auto-prefix and no Xtream URL auto-parse (8).

### 5.5 Fetch results (asynchronous, same line)

| State | String |
|---|---|
| fetching, URL | `Fetching from tv.example.net...` |
| fetching, path | `Reading the file...` |
| failed, URL | `<reason> from <host>` with `<reason>` from the shipped `Model.statusReason`: `HTTP 403 Forbidden`, `HTTP 404 Not Found`, `HTTP 503 Service Unavailable`, `Could not resolve host`, `Connection refused`, `Timed out`, `TLS error`, `Network error`, `Not an M3U playlist`, `Playlist has no channels`, `Source too large`, `Unsafe redirect` |
| failed, path | `<reason>` alone: `File not found`, `Path not allowed`, `Not an M3U file`, `Playlist has no channels` |
| cancelled | no line; the form thaws |
| success | never shown on the form (it closes); the footer transient carries `1,475 channels in 28 groups` |

`<host>` is `Model.hostOf(url)`: never a path, query or userinfo.

### 5.6 Default label and duplicates (S4, S5)

`Model.deriveLabel(url, kind)`:

- `http(s)` URL and Xtream server: the host, lower-cased, with a leading
  `www.` removed, plus `:port` when a port is present (`nas.local:9981`,
  `tv.example.net`, an IP literal stays `192.168.1.10:9981`).
- Local path or `file://`: the file name with its extension (`channels.m3u`).
- Unparsable input never reaches this function (validation first).

`Model.uniqueLabel(label, existingLabels)`: if `label` (case-insensitive,
trimmed) is already used by another source, append ` 2`, then ` 3`, ...
(`tv.example.net 2`). Applied to derived labels on add and to CLI upserts
(S5). A label the user typed is not rewritten: the form rejects it with
`label_taken` instead. Renaming to the derived default is allowed (empty
label -> derived again).

### 5.7 Confirm dialog

| Case | Message | Buttons |
|---|---|---|
| not active | `Remove "NAS Tvheadend"? Its cache is deleted too.` | `Cancel` / `Remove` (preselected) |
| active | `Remove "Provider"? It is the active source; the guide returns to setup.` | same |

The label is wrapped in the curly quotes UX.md uses (`"x"` -> U+201C/U+201D).

### 5.8 Accessible names

See 7.1; they reuse the strings above.

---

## 6. Privacy behaviors as UI rules (R12, decision 4)

1. The list never renders a URL: label, host (`Model.hostOf`), kind, counts,
   last used. `local file` stands in for paths. Tooltips on rows: none.
2. The full URL exists on screen only inside the `Playlist` / `EPG` field
   of a form the user opened, and only after `Ctrl+R` / eye; by default it is
   masked (4.4). Reveal is a toggle that never survives leaving the field,
   saving, cancelling or closing.
3. Masking covers userinfo, every query value and the fragment; the path is
   visible because the user must be able to edit it (open question 8.4).
4. Transients, footer status, header labels, banners, result lines and
   notifications carry the label and `Model.hostOf(url)` at most; error
   reasons pass through `Model.redactUrls` as shipped. No new notification is
   introduced by this feature.
5. The Xtream password field is `password: true` (echo-masked while typing)
   and is cleared from the form state the moment the URLs are built; the
   form is never re-opened pre-filled, and the edit form shows only the built
   URLs, masked (S6).
6. Clipboard content is data: sanitized on arrival, never executed, never
   echoed anywhere but the field it landed in. Paste into a masked field
   replaces the value and the result is masked again before the next frame.
7. `Accessible.description` of a URL field is the masked rendering even
   while revealed (a screen reader never gets the query); the password
   field sets `Accessible.passwordEdit: true` so its text is never exposed.
8. Console: the guide logs mode changes at most, never field values (shipped
   rule R12 extended to the new input surface).
9. `Space` / `Enter` on a source, `x` remove, and the CLI path all go through
   the same service actions; there is no UI-only copy of a URL anywhere in
   `Guide.qml` beyond the form state, which is dropped on close.

---

## 7. Accessibility

### 7.1 Roles and names

| Surface | `Accessible.role` | `Accessible.name` / notes |
|---|---|---|
| Header title (sources, forms) | `Accessible.Heading` | the title; the search line's `EditableText` role applies only in search / list |
| Pinned Sources row | `Accessible.Button` | `Sources, 3 saved` |
| Sources list | `Accessible.List` | `Sources` |
| Source row | `Accessible.ListItem` | `<label>, <host>, <n> channels in <m> groups` + `, active` + `, EPG` + `, last used <x>` / `, never used` / `, not loaded yet`; `Accessible.focused` = hasCursor; `Accessible.selected` = active |
| Action rows | `Accessible.ListItem` | `Add source`, `Add Xtream login` |
| Action buttons | `Accessible.Button` | `Edit <label>`, `Remove <label>` |
| Form column | `Accessible.Dialog` | `Add source` / `Edit source` / `Add Xtream login` / `Set up a playlist` (first run) |
| Label field | `Accessible.EditableText` | `Label, optional` |
| Playlist field | `Accessible.EditableText` | `Playlist URL or path`; `Accessible.description` = masked rendering (always) |
| EPG field | `Accessible.EditableText` | `EPG URL, optional`; description masked |
| Server field | `Accessible.EditableText` | `Server URL` |
| Username field | `Accessible.EditableText` | `Username` |
| Password field | `Accessible.EditableText` | `Password`; `Accessible.passwordEdit: true` |
| Eye button | `Accessible.Button` | `Show query` / `Hide query`; `Accessible.checked` = revealed |
| Link rows | `Accessible.Button` | `Use Xtream login instead`, `Saved sources, 3` |
| Buttons | `Accessible.Button` | `Load`, `Save`, `Cancel` |
| Result / error line | `Accessible.AlertMessage` | the line's text |
| Confirm dialog | `Accessible.Dialog` | the message; its buttons `Accessible.Button` `Cancel` / `Remove` |
| Footer status | `Accessible.StaticText` | shipped |

### 7.2 No color-only state

Active: check glyph + bold + `active`. Error: alert glyph + words + the
field's urgent border is decoration. Fetching: loading glyph + words +
disabled controls. Revealed vs masked: the text itself and the eye / eye-off
glyph. Cursor: the shipped selected fill plus `Accessible.focused`.
Destructive button: the kit's urgent border plus the word `Remove`.

### 7.3 Focus order

- First run: `Playlist` -> `EPG` -> `Saved sources (n)` (when present) ->
  `Use Xtream login instead` -> `Load` -> wrap.
- Add: `Label` -> `Playlist` (initial focus) -> `EPG` -> `Use Xtream login
  instead` -> `Save` -> `Cancel` -> wrap.
- Edit: `Label` (initial) -> `Playlist` -> `EPG` -> `Save` -> `Cancel` -> wrap.
- Xtream: `Label` -> `Server` (initial) -> `Username` -> `Password` ->
  `Save` -> `Cancel` -> wrap.
- Tab, Shift+Tab, Down, Up follow this order (`activeFocusOnTab` on the kit
  buttons; the form handler drives fields). The eye button is not a Tab
  stop (`Ctrl+R` is its keyboard form); it is mouse-only.
- Sources list: a single cursor, keyboard and mouse share it (PointerMoveGate).
- Focus returns to the key catcher on every mode change
  (`Qt.callLater(keyCatcher.forceActiveFocus)`), and to the first-run
  `Playlist` field when the first-run form appears.

### 7.4 Hit targets

Rows: full width, `detailRowHeight` / `singleRowHeight`. Action buttons:
`PanelActionButton` default size (at least `Style.space(22)` square).
Fields: full field width by their implicit height. Pinned Sources row: full
column width by `groupEntryHeight`. Link rows and buttons: kit padding.

---

## 8. Open questions, decided here

| # | Question | Decision |
|---|---|---|
| 1 | Entry key from list mode | `o` (`o sources`). Free in UX.md 3.1, not a PanelKeyCatcher key, no M2 claim on it (`p` is left free for a possible picture-in-picture binding). `o` inside Sources goes back. |
| 2 | Xtream entry key | `c` (credentials) in Sources; `Add Xtream login` row for the mouse; a link row inside the URL forms so first run reaches it without a printable key. |
| 3 | `r` rename? | No. `e` opens the form with `Label` focused; rename is `e`, type, `Enter`. `r` stays refresh in the guide and is ignored in Sources. |
| 4 | Masking scope | Userinfo, all query values, fragment -> `****`. Path stays visible (some providers put credentials in the path; the user must still be able to edit it; the PO rule names the query string). Fixed length, never per-character. |
| 5 | How does one edit a masked value? | Masked = fully selected: typing, paste, Backspace, Ctrl+U replace it; `Ctrl+R` / eye reveals for caret editing; re-masked on blur, save, cancel, paste. |
| 6 | Reveal: hold or toggle? | Toggle, scoped to the focused field, reset on blur. A hold gesture cannot be typed into. |
| 7 | Esc in forms | One press cancels in forms opened from Sources (network precedent; `Ctrl+U` clears). First run keeps the search-line "clear first, then close" rule and never closes while any field has text. |
| 8 | Paste semantics | Plain / revealed fields: insert at caret (Qt default, as the uptime monitor). Masked fields: replace. Always sanitized in `onTextChanged`. |
| 9 | Auto-prefix `https://` on a bare host? | No. Xtream servers are commonly plain `http` on a port; guessing would produce silent TLS failures. Error `scheme` says what to type. |
| 10 | Auto-parse a pasted `get.php?username=...` into the Xtream fields? | No (v0.2). `server_path` error tells the user to paste just the server; the URL form accepts the full `get.php` URL anyway. |
| 11 | Probe before commit, or commit and let the refresh fail? | Probe first for add and playlist-URL edits (S8: a bad source never replaces a working one). Switching to an already-saved but uncached source commits and uses the shipped loading state. |
| 12 | Does adding make the new source active? | Yes (first run per S1; from Sources for consistency: the user pasted it to use it, and switching back is two keystrokes). |
| 13 | Enter vs Space in Sources | `Enter` switches and returns to the guide; `Space` switches and stays (mirrors play-and-close vs preview). |
| 14 | Removal of the active source with other sources left | Settings cleared and the guide behind is first-run (S7), but Sources stays open so the next `Enter` picks a replacement; only an empty list drops to the first-run form. |
| 15 | Confirm dialog preselection | `Remove` preselected, as the clipboard preselects `Delete` (kit precedent). `Esc` always cancels. |
| 16 | Label uniqueness | Enforced case-insensitively; derived labels get ` 2`, ` 3`; typed labels get `label_taken`. |
| 17 | Duplicate playlist URL | Rejected with `Already in Sources as "<label>"`; the CLI path upserts instead (S5). |
| 18 | Where do the per-source channel and group counts come from? | The source's own cache (architect: per-source meta with `channelCount`, `groupCount`, `cachedAt`); `not loaded yet` when absent. |
| 19 | Last-used format | `used 21:30` / `used yesterday` / `used 3 Sep` / `used 3 Sep 2025` / `never used`; 24-hour local time like `until HH:MM`. |
| 20 | Group column in Sources mode | Hidden; the screen owns the body. `h`/`l` ignored. |
| 21 | Where does the Sources row live in the column? | Pinned under the ListView with a separator, never scrolled, never a scope, count = saved sources. Hidden with the column on narrow cards (the key remains). |
| 22 | Active-source cue in the guide | Footer status prefixed with the label when 2+ sources exist; no header change; bar tooltip unchanged. |
| 23 | Notifications for source operations | None. The guide is open and the footer transient carries the result; refresh notifications keep their shipped rules. |
| 24 | EPG changes | Never probed; committed at once and refreshed in the background with the shipped banner on failure. |
| 25 | Field order | `Label`, `Playlist`, `EPG` everywhere (first run has no `Label`); initial focus is `Playlist` when adding, `Label` when editing. Xtream: `Label`, `Server`, `Username`, `Password`, focus on `Server`. |
| 26 | Buttons on keyboard-first forms? | Yes, `Cancel` / `Save` (`Load`) as kit `Ui.Button`s, Tab-reachable after the fields, for mouse users and screen readers; `Enter` in any field submits so keyboard users never need them. |
| 27 | Search inside Sources? | No. A source list has a handful of rows; `/`, `Tab` and letters other than the commands are ignored. |
| 28 | Uncached source switch failing | Shipped error state with `o sources` added to its hint so the previous source is two keystrokes away. |
| 29 | Scrim click while a form is open | Closes the guide and discards the form (clipboard behavior); the ConfirmDialog's own scrim cancels only the dialog. |
| 30 | First-run header | Keeps the shipped dimmed `Search channels...` placeholder; the form lives in the empty-state column. Forms from Sources put their title in the header slot. |

### 8.1 What the architect and front-end developer must provide

Sources model the guide binds (`service.sources`, array; `service.activeSourceId`):

- per source: `id` (stable hash of the playlist URL), `label`, `kind`
  (`url` | `file` | `xtream`), `host` (`Model.hostOf`, `local file` for
  paths), `hasEpg` (bool), `channelCount` (-1 when never loaded),
  `groupCount`, `cachedAt` (epoch s, 0 none), `lastUsedAt` (epoch s, 0
  never), `active` (bool, at most one true).

Service actions and signals:

- `addSource({label, playlistUrl, epgUrl, kind})` -> starts a probe into
  the new hash's cache dir; `probeFinished({ok, sourceId, channelCount,
  groupCount, reason, host})`; on `ok` the service records, persists
  (`shell.updateEntryInline`), switches.
- `updateSource(id, {label, playlistUrl, epgUrl})` -> immediate commit when
  `playlistUrl` is unchanged, otherwise the probe path above with cache
  migration.
- `cancelProbe()`; `removeSource(id)` (deletes the cache dir; clears
  settings when active); `switchSource(id)` (settings, cache swap, model
  swap, `lastUsedAt`, background refresh when stale); `sourcesChanged`,
  `sourceSwitched(id)` signals; `service.probing` (bool) for the frozen form.

Pure functions in Model.js (unit-tested; the service uses the same ones for
the CLI path, S5):

- `validateSourceUrl(text, {kind: "playlist" | "epg"})` -> `{ok, code}` with
  the codes of 5.4; `validateXtream({server, username, password})` ->
  `{ok, code, field}`; `validateLabel(label, existingLabels, selfId)`.
- `sanitizeInput(text, limit)`, `LIMITS`, `MASK`, `maskUrl(url)`,
  `deriveLabel(url, kind)`, `uniqueLabel(label, existing)`,
  `xtreamUrls(server, username, password)` -> `{playlistUrl, epgUrl}`,
  `formatLastUsed(epochSec, nowSec)`, `sourceDetail(source, narrow)`,
  `sourceAccessibleName(source)`, `pluralGroups(n)`.
- `footerHints` and `footerStatus` extended for the new modes and the
  active-label prefix; `SOURCE_KEYS`.
- `guideState` gains `mode` values `sources` | `sourceEdit` |
  `sourceXtream` | `confirmRemove`, `returnMode`, `form` (`{kind, origin,
  sourceId, values, focus, revealed, error, probing}`), `sourceCursor`; the
  transitions of 1.9 as pure functions (`onEscape` extended).

Settings: unchanged keys (`playlistUrl`, `epgUrl` on the bar entry, R2);
the state file gains the sources history (schema v2, 0600, decision 2).
