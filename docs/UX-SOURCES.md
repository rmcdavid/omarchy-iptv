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
| Sources cursor | The same 2 px left mark the channel list uses (UX.md 5.4), on every row including the two action rows. Added 2026-09-21: until then the only thing marking the cursor here was the selected fill, which measures 1.12-1.23:1 against the card on 23 of 23 themes against a 3:1 bar, beside a border the theme ships 0 px wide. The cursor-only edit and remove buttons appear on SOURCE rows alone, so on the action rows -- and on any non-active source row, which has neither the bold label nor the check glyph -- nothing at all showed where the cursor was, on the surface that carries `x remove`. |
| Masking | Userinfo, every query value and the fragment become `****`; scheme, host, port, path and query keys stay. Paths never masked. A masked field behaves as fully selected (typing, paste, Backspace replace it); `Ctrl+R` (or the eye button) reveals it for caret editing; re-masked on blur, save, cancel. |
| Esc | Forms from Sources: one press cancels (network-prompt precedent). First-run: clear the focused field first, then close (search-line precedent); never closes while any field still has text. |
| Save | Add and playlist-URL edits probe first and commit only on success (S8); label-only and EPG-only edits commit at once. Fetch progress and errors live on a form-local result line (banner treatment). |
| Switch | `Enter` switches and returns to the guide; `Space` switches and stays. Cached source: instant redraw, silent background refresh when stale. Uncached: commit, then the shipped loading state. |
| Remove | `x` / `X` / `Delete` -> `ConfirmDialog` -> cache deleted. Active removed: settings cleared, guide behind is first-run; Sources stays open while other sources remain. |
| Xtream | `c` in Sources, the `Add Xtream login` row, or the link row in the add / first-run forms. Four fields, password echo-masked, never re-shown. |
| Editing (added 2026-10-11, D-CLIP-1) | Every form field is read-only to Qt, always. The plugin applies typing, `Backspace`, `Delete`, their `Ctrl` word variants and cut to the model value itself and puts the caret back; navigation, selection, `Ctrl+A`, `Ctrl+C` and mouse selection stay native. Paste is `Ctrl+V` / `Shift+Insert` only, through the helper's `clipboard` verb, which bounds a `wl-paste` child to 32 KiB and 5 s and hands the shell at most 8,192 characters (R8). `Ctrl+X` on the password field does nothing, as it does natively (`Model.cutApplies`). Lost, and said so: input-method composition in the label field (a dead key then a letter types the plain letter), native undo, middle-click paste. Rows below that say Qt edits the field are overturned where they stand, not rewritten. |

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
(`emptyKind === "unconfigured"`), the active source was removed, or the
active playlist URL was cleared at runtime, for example by
`omarchy bar set io.github.rmcdavid.iptv playlistUrl ""`. In the cleared
case the source record and its cache survive, so this surface shows the
`Saved sources (n)` link and setting a URL again reloads from cache.
**[Amended 2026-10-11, D-SINK-19: `configured` is "the plugin's own
`state.json` names a source it holds", and `omarchy bar set ... playlistUrl
""` no longer clears anything -- an empty input is a no-op (R1/R4), because
the plugin itself empties that key on every write. The surface is reached
by removing the active source (here, or `state source remove`), by a state
file whose pointer names no record, and -- the case worth knowing about --
by an OLDER build run over a migrated install, which looks for a URL on the
entry and finds none; the `Saved sources (n)` link is the recovery in all
three.]**
**[Amended 2026-10-13, D-SINK-19 round 11 (R21, the owner's decision to drop
the `omarchy bar set` URL route): after the one migration a URL set on the
bar entry is refused, so no command-line value can reach or leave this
surface; and the caption line with the terminal command in step 1 is GONE --
`firstRunTerminal` and `copyCommand` are deleted from `Guide.qml` on
lane-key-m1, and the form offers nothing to type anywhere else. 3.1.1 carries
the shipped wireframe.]**

1. The guide opens straight into `sourceEdit` with `origin: "firstRun"`.
   The empty-state column keeps its glyph and title (`No playlist
   configured`), the prose becomes one line, and the command box is replaced
   by the `Playlist` field (focused, caret visible, `PanelKeyCatcher`
   blocked), the `EPG` field, the link row `Use Xtream login instead`, a
   `Load` button, and one caption line with the terminal command (S5 parity;
   clicking it still copies, as shipped). [Round 11, R21: the caption line is
   deleted; the form ends at `Load`.]
2. The user pastes (`Ctrl+V`, `Shift+Insert`, middle click) or types. Every
   arrival is sanitized (2.3): trimmed, newlines and control characters
   removed, capped at `LIMITS.url`. A pasted value that has a query string or
   userinfo is shown masked immediately (4.4); text the user types is never
   masked while they type it. **[Amended 2026-10-11, D-CLIP-1: `Ctrl+V` and
   `Shift+Insert` only, through the plugin's `wl-paste` process; middle click
   pastes nothing, because the primary-selection paste was Qt's and the field
   is read-only to Qt. Sanitize on arrival and mask at once stand.]**
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
   `playlistUrl` / `epgUrl` **[since D-SINK-19, 2026-10-11: `state.json`
   gets the source's key as `activeKey`, and shell.json gets that key as
   `sourceKey` and no URL]**, the service points at its cache directory, the
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
5. No cache yet (added by CLI, never fetched; or cache deleted) [round 11:
   "added by CLI" now means moved in by the migration of a 0.13.x install,
   R21a]: the switch
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

**A guide URL waiting on the bar entry meets the `EPG` field (round 8,
2026-10-12; D-SINK-19 R18d, the lead's ruling on OQ-W3).** When the user
set `epgUrl` from a terminal while no source was active, that value waits
on the entry for the next source to become active (5.5). If the source
becoming active is this add and its `EPG` field is NOT empty, the field
wins: it is the user's later, explicit input for the same slot. The new
record keeps the field's guide URL, and the waiting value is superseded
-- the same commit takes it off the entry, and the shell's journal reads
`the guide URL in the add form supersedes a pending input (epgUrl); the
bar entry drops it`, the key name and never a URL. If the field is empty,
the waiting value is attached to the new record, as on every other route.
Nothing on screen changes in either case: the form never shows the
waiting value (`Guide.qml` reads no entry input) and the transient is the
usual `Added ...`. Round 7 did the opposite (the waiting
value replaced the field's), so a guide URL set long ago from a terminal
silently beat the one just typed. One case is open (lane A's OQ-X3, for
the lead and UX): if the same playlist was added from the terminal while
this add was being probed (S5's duplicate branch), the commit keeps that
record, the field's guide URL is not on it, and the waiting value is
attached as before. Observed through the harness by key-scenario A1 (empty
field) and A2 (a field with its own guide URL; red on `--baseline
lane-key-w2`), lane A on lane-key-x1, with two saved sources and none
active; the add into an empty list is node only. [Round 9: the form-wins
rule above is OVERTURNED, and the open case is ruled; the next paragraph.]

**A guide URL held for the next source meets the `EPG` field (round 9,
2026-10-12; D-SINK-19 R19b and R19c, overturning R18d).** A guide URL set
from a terminal while no source was active no longer waits on the bar
entry: it is held in `state.json` and taken off the entry (5.5). When this
add makes a source active, the guide URL the user set LAST wins. The `EPG`
field counts from the moment the form is SUBMITTED (`Enter`), not from the
moment the probe finishes: so a terminal value set before the submit loses
to a non-empty field, and one set while `Fetching` is on screen -- after
the submit -- wins over it. With the field empty the held value is attached
to the new record, as before. The held value is dropped either way, and the
shell's journal says which happened, naming the setting and the source's
short code and never a URL: `a pending guide URL (epgUrl) lands on source
<key>` or `a pending guide URL (epgUrl) is superseded: source <key> keeps
the one set later`. Nothing on screen changes in any case: the form never
shows the held value and the transient is the usual `Added ...`.
S5's duplicate branch is ruled the same way (lane A's OQ-X3): if the same
playlist was added from the terminal while this add was probed, the commit
keeps that record, and the field's guide URL lands on it if it was set
later than the guide URL that record already holds. Round 8 let the field
win whatever the order, so the later terminal value ended on no record and
off the entry (the eighth review's P1-B, live). Observed through the
harness by key-scenario Q1 (the terminal value set during the probe wins;
red on `--baseline lane-key-y0`), Q2 (set before the submit, the field
wins) and A1/A2 as re-read (lane A, lane-key-y1, two saved sources and none
active); the duplicate branch and the add into an empty list are node only.

**The `EPG` field is the source's guide URL, and nothing else meets it
(round 11, 2026-10-13; D-SINK-19 R21, OVERTURNING R18d, R19b and R19c).**
The two paragraphs above are the record of the route the product owner
withdrew. After the one migration of a 0.13.x install no guide URL waits
anywhere for a source to become active: a guide URL on the bar entry with no
source to attach it to is reported and removed at the migration (R21c), and
one set on the entry after it is refused (R21b). So the add form's `EPG`
field, typed or filled in by an Xtream login, is simply the new record's
guide URL; an empty field leaves the record without one; there is no
supersede, no set time and no journal line about a pending value. A terminal
`epgUrl` set while `Fetching` is on screen changes nothing on the record and
shows one `Bar setting ignored` notification (5.9); the field's guide
URL lands with the record and survives a restart (node `R21e (lag host)` /
`(echo host) the add form's race ...`; key-scenario Q moved to the new
contract on lane-key-m1). S5's duplicate branch cannot arise from a terminal
value after the migration, because none is adopted.

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
- [Round 11, 2026-10-13: OVERTURNED by R21 -- nothing is held, no edit is
  stamped, and the edit form's guide URL is the record's; key-scenario V moved
  to the new contract. The bullet stands as the round-9 record.] A changed `EPG` field and a guide URL held for the next source (round 9,
  R19c). Saving an edit that CHANGES the guide URL stamps it with that
  moment; an edit that sends the same guide URL back (a label-only edit,
  or re-typing the same URL) stamps nothing. If a guide URL set from a
  terminal is held while no source is active, and the user then edits a
  saved source's guide URL and switches to it, the edit is the later input
  and stands; the held value is dropped. A terminal value set AFTER the edit
  wins at the switch instead. Round 8 and earlier let any held value
  replace the edited one at the switch (the eighth review's P2). Nothing on
  this screen changes either way: the transient is `Saved`. Observed
  through the harness by key-scenario V1 (red on `--baseline
  lane-key-y0`); the other order is node only.

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

The built `xmltv.php` URL counts as the form's own guide URL (round 8,
R18d): a guide URL waiting on the bar entry is superseded by it exactly as
by a typed `EPG` field (1.5), because the user's login is the later
explicit input. Pinned in node (`R18d (lag host) OQ-W3, the Xtream add`
and its echo-host twin); no live segment drives the Xtream form with a
value waiting. [Round 9, R19c: the built URL is stamped at the login's
SUBMIT, and it wins over a held terminal value only when that value was set
before the submit, exactly as a typed field does (1.5). The node pins are
renamed `R18d / R19c (... host) OQ-W3, the Xtream add: the xmltv.php URL
the form derived, submitted after the CLI value, ...`; still no live
segment.] [Round 11, R21: OVERTURNED with R18d and R19c. The built
`xmltv.php` URL is the record's guide URL and nothing competes with it; the
round-8/9 node pins are deleted (R21d).]

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
  **[Amended 2026-10-11, D-CLIP-1: the field is `readOnly: true` always, so
  "Qt's native editing" is now caret, selection, Home / End, `Ctrl+A`,
  `Ctrl+C` and mouse click / drag selection only. The form handler (`handleFormKey`) also does printable
  insertion, `Backspace`, `Delete`, `Ctrl+Backspace`, `Ctrl+Delete`, cut and
  paste, over the model value, with the caret and selection the read-only
  control still keeps. The word boundary is Qt's own, measured on a real
  `TextInput` into `tests/fixtures/form-edit.js`.]**
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
| `Enter` | Source row: switch and return to the guide (1.4). `Add source` row: add. `Add Xtream login` row: Xtream form. [Round 14, R24f: the no-write mode draws no Add rows (3.2.6).] |
| `Space` | Source row: switch and stay. Action rows: same as `Enter`. |
| `a` / `A` | Add source (URL form). [Round 14, R24f: in the no-write mode (5.10) no form opens; the footer says `state.json could not be read · nothing is saved until it can be`.] |
| `c` / `C` | Add Xtream login (credentials form). [The same in the no-write mode.] |
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

**Amended 2026-10-11 (D-CLIP-1): the cells above that say "(Qt)" for an EDIT
are overturned where they stand; the behaviour the user sees is the same and
the hand that does it is not.** Every field is `readOnly: true`, always,
because an editable `TextInput` makes the shell read the whole clipboard on
every change (`docs/ARCHITECTURE.md` section 6). So: printable -> inserted
over the selection by the plugin (`Model.editInsert`), an insert past the
field's capacity refused rather than cut, and the masked-field replacement
unchanged; `Backspace` / `Delete` -> one UTF-16 unit, a surrogate pair whole
(`Model.editDelete`); `Ctrl+Backspace` / `Ctrl+Delete` -> to the previous /
next word boundary, Qt's own boundary measured and pinned; `Ctrl+X` /
`Shift+Delete` -> native copy of the selection, then the plugin deletes it,
on every field but the password: there `Ctrl+X` does nothing at all, as
Qt's own `cut()` does nothing under `echoMode` Password (`Model.cutApplies`;
at lane commit 44b250b it deleted the selection with nothing copied, which
the review caught); `Ctrl+V` / `Shift+Insert` -> `Service.requestClipboard`,
which runs the helper's `clipboard` verb: a `wl-paste` child the HELPER
bounds to 32 KiB and a 5 s deadline, one JSON reply of at most
`LIMITS.url * 4` characters, the shell's 8 s watchdog the outer bound (R8;
the shell holds the reply and never the clipboard's size), sanitized at the
field's capacity, inserted over the selection or over the whole of a masked
value (`Model.editRangeFor`) and re-masked; a failed or timed-out paste
changes nothing. Middle click pastes nothing. `Ctrl+A`, `Ctrl+C`, `Left` /
`Right` / `Home` / `End`, `Shift`-selection and mouse selection stay native
and unchanged -- including the one thing every Qt field does on a mouse
selection, writing it to the PRIMARY selection, so a drag across a REVEALED
URL publishes it there as before (recorded in `ARCHITECTURE.md` section 6;
pre-existing, user-initiated, not changed). Lost with `readOnly`: native
undo (`Ctrl+Z`), and input-method composition, so dead keys and CJK input
cannot type into the label field -- a dead key followed by a letter inserts
the plain letter, measured (paste carries any Unicode). Two deliberate divergences from Qt, pinned on both sides in the
QML spec: `Ctrl+Delete` over a selection deletes the selection alone (Qt
also eats to the next boundary), and `Delete` over a combining sequence
removes one unit (Qt removes the grapheme). The caret on a read-only control
is the plugin's own drawing (4.2).

Sanitize (Model.js `sanitizeInput(text, limit)`, applied in
`onTextChanged` so it covers every paste path, including primary selection
**[overturned 2026-10-11, D-CLIP-1: there is no `onTextChanged` and no
native paste path; sanitize runs in `pasteFromProcess` on the `wl-paste`
text, and typed text goes through `Model.typedText` and `editInsert`]**):
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

Amended 2026-10-11 (D-SINK-19). The terminal caption in this wireframe and
the next is the pre-D-SINK-19 text. The shipped string now ends
` (converted; not kept in shell.json)` -- the exact string is in the table in
section 5.1 -- because the command is an INPUT: the URL is moved into the
plugin's private state and taken back out of shell.json by the plugin's next
write, and a user who looks for it there afterwards should have been told.
The caption is `elide: Text.ElideMiddle` over the card width; whether the
longer string elides at the shipped width, and what it looks like when it
does, is UNVERIFIED (the docs lane holds no display). Two strings on the
OLDER empty state (the one with the command box, UX.md 4.4) still presented the
URL settings as stored in that round -- `Settings live in ~/.config/omarchy/shell.json
(entry ...)` and `Optional EPG:  omarchy bar set ... epgUrl <url>`. **Moved
2026-10-12 (round 3, lead ruling):** they now read `Optional EPG:  omarchy bar
set io.github.rmcdavid.iptv epgUrl <url>  (converted; not kept in shell.json)`
and `Both are inputs: the URL moves to ~/.local/state/omarchy-iptv/state.json;
other settings live in ~/.config/omarchy/shell.json (entry
io.github.rmcdavid.iptv)` -- `Guide.qml` `unconfiguredEpg` and
`unconfiguredWhere` on lane-key-s1, the same parenthetical as the first-run
caption so one phrase means one thing; UX.md 4.4 and 6.3 carry them. In round
2 they were an open UX item for the lead, recorded
here and in the lane report rather than given an id this lane cannot board.
**A conflict this document raises rather than resolves (round 7, 2026-10-12,
lane C).** The `Optional EPG` line ends `(converted; not kept in
shell.json)`, and it belongs to the unconfigured empty state -- no active
source (whether that state is still on screen behind the first-run form was
not read for this note) -- which is exactly the state in which R12 -- enforced at the sink since round 7 (R17a) -- KEEPS
a guide URL set from a terminal on the bar entry in `shell.json` until a
source becomes active. "Converted" is true eventually; "not kept" is false
until then, and the README now says it waits on the entry. Whether the
caption should say so (for example "kept on the entry until a source is
active") is a copy decision for the lead and the Guide's owner
(`Guide.qml` `unconfiguredEpg`); nothing here changes it. [Round 9, R19b:
the conflict is resolved by the code rather than the copy. A guide URL set
in this state is now held in the plugin's own `state.json` and taken off
the entry once that write lands, so `not kept in shell.json` is true after
one write, not only once a source is active. It is still on the entry for
that one write's span, and for longer only when the state write fails
(the value is then left on the entry as its only copy, R13). No copy
change is requested.]

**Amended 2026-10-13 (D-SINK-19 round 11, R21; the owner dropped the
`omarchy bar set` URL route).** The terminal caption is DELETED, in this
wireframe and the next: a URL set that way is refused once the migration has
landed, so the form must not offer it. `firstRunTerminal`, the older empty
state's command box (`unconfiguredCommand`), its `Optional EPG` line
(`unconfiguredEpg`), `copyCommand` and the `Copied` transient are gone from
`Guide.qml` on lane-key-m1, which closes the round-7 conflict above by
removing the line it was about. The first run as shipped:

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
|                                 Enter load - Tab next field - Ctrl+V paste - Esc close         |
+------------------------------------------------------------------------------------------------+
```

The older empty state (UX.md 4.4) keeps its title and reads, as shipped,
`Add your M3U URL or path in Sources, with its EPG URL if you have one`
(`unconfiguredProse`) and `Sources and their URLs are kept in
~/.local/state/omarchy-iptv/state.json; other settings live in
~/.config/omarchy/shell.json (entry io.github.rmcdavid.iptv)`
(`unconfiguredWhere`). The text-format guard went from 61 blocks to 58 with
the three deleted `Text`s. The rendered layout without the caption is
UNVERIFIED on a display (this lane holds none); the strings are read off
`Guide.qml`.

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

#### 3.2.6 The no-write mode (D-SINK-19 round 14, R24f, D-SRC-28; round 15, D-SRC-38; 2026-10-14)

At a no-write START nothing loaded, so memory holds no source; the header's
right slot is the notice's TITLE (`Model.sourcesHeaderRight`, one source of
copy with the notification and the guide body, 5.10) where 3.2.3 reads `No
sources`, and there are NO Add rows. Wireframe (UNVERIFIED on a display:
key-scenario B15 reads the header, the rows and the footer through the
harness, and no screenshot was taken):

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Sources                                                             Saved sources not loaded  |
|                                                                                                |
|                                                                                                |
|                                                                                       Esc back  |
+------------------------------------------------------------------------------------------------+
```

Mid-session (the mode begun under a running shell) memory still holds the
records it had, so their rows stay, switchable to nothing (a switch is
refused, 5.10 item 3); still no Add rows, and the footer drops `a add` and
`c Xtream`: `j/k move - Enter switch - e edit - x remove - g logos on - Esc
back` (5.3). [Round 15, 2026-10-14, D-SRC-38: the header there is NOT the
notice's title any more. `Saved sources not loaded` read as false above rows
that were loaded and still play; what stopped is saving, so the right slot
reads `Saving has stopped` (`Model.stateBlockedHeader(reason, path,
midSession)`, the notice copy family; `Guide.qml` passes
`service.stateLoaded`). At a no-write START it is still the notice's title,
above. Observed by key-scenario B22 (`header:Saving has stopped rows:2`),
red on dev (`header:Saved sources not loaded rows:2`); the wireframe is
UNVERIFIED on a display:]

```
+------------------------------------------------------------------------------------------------+
|                                                                                                |
|  Sources                                                                   Saving has stopped  |
|                                                                                                |
|> 󰄬 Provider                                              used 21:30                           |
|>         active - tv.example.net - Xtream - 1,475 channels in 28 groups - EPG                  |
|                                                                                                |
|          NAS Tvheadend                                                        used yesterday   |
|          nas.local:9981 - 84 channels in 6 groups - EPG                                        |
|                                                                                                |
|                           j/k move - Enter switch - e edit - x remove - g logos on - Esc back  |
+------------------------------------------------------------------------------------------------+
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
| cursor row | `Color.menu.selectedBackground`, `selectedBorderSpec`, and the 2 px cursor mark (see the Sources cursor row above); label and lead glyph stay `Color.menu.text` -- the accent means ACTIVE, not CURSOR (PO ruling 2026-09-21); meta and detail stay `Color.menu.text` at their opacity (shipped convention) |
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
| field | `Ui.TextField { foreground: Color.menu.text; accent: Color.accent; font.family: Style.font.menuFamily; font.pixelSize: Style.font.body; horizontalPadding: Style.spacing.controlPaddingX; verticalPadding: Style.spacing.inputPaddingY }`; height is its `implicitHeight`, never set; `readOnly: true` always (D-CLIP-1, added 2026-10-11) |
| caret (added 2026-10-11, D-CLIP-1) | Qt draws no caret on a read-only input and never instantiates its `cursorDelegate` there (measured in the QML spec), so the field draws its own: a `Rectangle` on the control's `cursorRectangle`, `Style.spacing.hairline` wide, `field.color`, blinking every half `Application.styleHints.cursorFlashTime` (steady when the hint is 0), lit again on every caret move, hidden while the field is masked or unfocused |
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
  masked:  http://****@tv.example.net:8080/get.php?username=****&password=****&type=m3u_plus&output=ts#****
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
  end. **[Overturned 2026-10-11, D-CLIP-1: `readOnly` stays `true` on
  reveal and everywhere else; reveal changes only what the control renders,
  and the caret goes to the end as before.]** Re-mask on: focus leaving the field, `Enter`, `Esc`, the form closing,
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
| First-run terminal caption | `Or from a terminal:  omarchy bar set io.github.rmcdavid.iptv playlistUrl <url>  (converted; not kept in shell.json)` (D-SINK-19, 2026-10-11; two spaces before the parenthesis, as shipped; it was `Or from a terminal:  omarchy bar set io.github.rmcdavid.iptv playlistUrl <url>` before) **DELETED 2026-10-13 (D-SINK-19 round 11, R21): the caption, its click-to-copy and the `Copied` transient are gone from `Guide.qml` (lane-key-m1), because a URL set that way is refused after the migration. The bar-setting notifications are 5.9.** |
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

List order (SR32): the active source first, then by `lastUsedAt` descending,
then never-used sources in the order they were added.
| detail, narrow | `active` (if any), `used ...` / `never used`, then the segments above |

### 5.3 Footer

| Mode / state | Status (left) | Hints (right) |
|---|---|---|
| guide, list mode | shipped | shipped + ` - o sources` |
| guide, 2+ sources | `<label> - 1,475 channels - updated 12:40` (label prefix on the shipped status, cached form included) | shipped |
| guide, error state, sources exist | shipped | `r retry - o sources - Esc close` |
| sources | the guide's status (active source) | `j/k move - Enter switch - a add - c Xtream - e edit - x remove - Esc back` |
| sources, cursor on an action row | same | `j/k move - Enter open - Esc back` |
| sources in the no-write mode, a source row (round 14, R24f) | same | `j/k move - Enter switch - e edit - x remove - g logos on - Esc back` (no `a add`, no `c Xtream`) |
| sources in the no-write mode, no source row (a no-write start) | same | `Esc back` |
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
| failed, path | `<reason>` alone: `File not found`, `Path not allowed`, `Not an M3U playlist`, `Playlist has no channels` |
| refused at the commit: another program took the last of the 50 places while the probe ran (round 17, R27c, D-SRC-41) | `Sources is full (50) · remove one first` (the `too_many` sentence through `Model.probeFailureLine`); nothing is recorded and the probe's cache directory is removed. Until R27 the 51st record was committed and the next start's parse dropped it silently. [Round 18, 2026-10-20, R28e: no host. Until R28e the line read `Sources is full (50) · remove one first from <host>`, as if the user should remove one from the provider (round 1's review: `... from 127.0.0.1`). The probe result now carries the refusal's `code`, and a result whose code is one the plugin refuses itself -- `too_many`, `state_unreadable`, `unknown_source` (`PROBE_LOCAL_REFUSALS` in model/sources.mjs) -- reads its sentence alone, so the sibling refusal from the same commit reads `state.json could not be read · nothing is saved until it can be`. A fetch failure keeps `from <host>` (the row above)] |
| cancelled | no line; the form thaws |
| success | never shown on the form (it closes); the footer transient carries `1,475 channels in 28 groups` |

`<host>` is `Model.hostOf(url)`: never a path, query or userinfo.

**Save failures (asynchronous, same line; D-SINK-19 round 4, R13,
2026-10-12; the Guide half round 5, R16, the same day).** The state write is
the switch, so the one failure a switch, a remove or an adoption can have is
`state.json` not being written:
`sourcesPersistFailed("state_write_failed")` -> `Could not write state.json -
check ~/.local/state/omarchy-iptv` (`Model.sourceErrorMessage`; a directory,
never a URL and never `omarchy bar set`, which would put the credential in
the shell history). It arrives after the call that issued the write has
already returned `ok`. A host that refuses the KEY mirror is not an error on
this screen: logged, repaired at the next start (SR25 as amended in
`ARCHITECTURE-SOURCES.md`); `config_unsafe` keeps its own sentence
(D-SINK-18). The guide renders the sentence for THE reason the signal
carried: `Guide.showPersistFailed(reason)` hands it to
`Model.persistFailureMessage` [since round 13 (R23f) through
`Model.refusalMessage(reason, stateWriteBlocked, "persist")`, which answers
the `state_unreadable` sentence instead while the no-write mode holds] (the three reasons are
`Model.PERSIST_FAILURE_REASONS`, and an unknown one falls back to
`persist_failed`'s sentence), on the form's result line while a form is open
and in the footer otherwise. Until round 5 the guide rendered
`persist_failed`'s sentence for every code, so a write that failed in
`~/.local/state` told the user to try `omarchy bar set` -- the opposite
advice, and the durable sink rule 5 forbids advising (lane A's DQ-T1, the
round-4 review's P2; closed on lane-key-u1 b42b5ab). OBSERVED at the code by
two node checks on lane-key-u1, both red over an export of lane-key-t2:
the routing read off `Guide.qml` (the reason handed through, the message
composed by `Model.persistFailureMessage` on both surfaces, never
`persist_failed`'s sentence by name), and the copy for every reason
`Service.qml` emits -- derived from the service source, none naming a URL,
only `persist_failed`'s naming `omarchy bar set`, the fallback for an unknown
reason. The rendered line on a display is UNVERIFIED: no scenario reads the
result line or the footer for it (key-scenario's L reads the bar entry and
the guide's `showLogos`), and the docs lane holds no display. **[Round 7,
2026-10-12 (OQ-C3): narrowed to the pixels. The TEXT the guide binds to both
surfaces is OBSERVED through the harness: the round-5 live lens drove the
signal with `state_write_failed` on lane-key-u3 (its `guide-copy.sh`, no
screenshot) and read the footer's transient with the guide in Sources, and
the add form's result line with the form open, each equal to
`Model.persistFailureMessage` of that reason, with no URL, no `omarchy bar
set` and no fixture path. What it looks like on a display -- wrapping,
elision, contrast -- is still UNVERIFIED, and no committed scenario carries
the text read yet.]**

**A second save sentence, refused before anything is written (D-SINK-19
round 12, R22a, 2026-10-13).** While `state.json` exists but could not be
read or parsed, an add, an edit, a switch and a remove are refused at once,
with code `state_unreadable` and `state.json could not be read · nothing is
saved until it can be` on the same line (`Model.sourceErrorMessage`; the
middle dot is `Model.SEP`). Unlike `state_write_failed` it arrives as the
call's own answer, not afterwards: nothing was issued. 5.10 is the whole
behaviour. [Round 13 (R23f): in that mode the logo toggle and a persist
failure read this sentence too (`Model.refusalMessage`), never
`persist_failed`'s `try omarchy bar set`.]

**Once per episode, a decision with its consequence (round 4, kept in round
5).** The failure is signalled on the FIRST `saveFailed` of an episode and
not again until a later write LANDS (`stateSaveFailed` is sticky, cleared by
content). So one switch -- two `setText`s -- shows one line, and that is the
reason for the rule. The consequence, measured: a SECOND switch on the still
failed disk reports `ok`, lands in memory only, holds no mirror, and shows
NOTHING on this screen (key-scenario F5 on lane-key-u2 wants `signalled:0`
counted from the switch's own mark, and reads it; lane B's transcript,
2026-10-12); the journal line `state.json could not be written` is per
failure, so the shell's log still says each time. A user who saw the line
once and switches again is not told again until a save succeeds. The lead
kept this over "once per call" on 2026-10-12 (round 5); a retry that is
silent on screen is the stated cost.

**The logo toggle on a failed disk (round 5, R16).** `g` and the consent's
confirm behave as they always do -- `Logos on` / `Logos off` in the footer,
no sentence about the save -- because that write carries no source and
raises nothing on this channel. What changed is beneath the screen: while a
state write is parked, in flight or failed -- and, since round 6, in the
first moments of a shell start before the plugin has read its own state --
the toggle writes the logo setting ALONE and leaves the entry's source keys
as the host publishes them (round 5 wrote "holds"; on the host that
publishes one write behind, the copy it carries can be one write old, which
is D-SINK-20 and changes nothing on this screen),
where before round 5 it mirrored the in-memory key and stripped the URL the
failed write had left on the entry as its only copy (the round-4 review's P1,
measured live; `ARCHITECTURE-SOURCES.md` 4.3 and SRC-MIG-22). Observed at the
sink by key-scenario L1/L2 on lane-key-u2 (64 / 0; 60 / 4 on `--baseline
lane-key-t2` with L1 reading `stored:<C> playlistUrl:no` -- lane B,
2026-10-12). One sentence of this screen's copy keeps `omarchy bar set`
honestly: a LOGO write the host refuses outright (no writable bar entry;
`setShowLogos` returns false) renders `Could not save settings - try omarchy
bar set` through the return value, and that advice is sound there because
the write it describes carries no credential (DQ-U5); nothing observes that
line on a display either.

**A guide URL waiting for a source (round 7, R17).** Nothing on this screen
changes, and that is the point: an `epgUrl` the user set from a terminal
while no source was active -- the unconfigured state, or right after
removing the active source -- stays on the bar entry until a source becomes
active, and pressing `g` meanwhile no longer takes it away. Until round 7
the toggle's write, with nothing outstanding, healed the entry and dropped
the value with no copy anywhere (observed live on the lagging host by the
sixth review); and on the echoing host simply picking a saved source here
(`Enter` / `Space`), or adding the first source with the form, did the same
through the key mirror's write. Now every write the plugin makes leaves an
input no source has consumed where it is, and the pick or the add that
makes a source active attaches the waiting guide URL to it in the same turn
-- replacing that source's own guide URL, or the EPG typed into the add
form, when they differ (the second is open as lane A's OQ-W3) [round 8,
R18d: ruled the other way -- a guide URL the add form carries wins and the
waiting value is superseded, 1.5 and 1.8; with the field empty the waiting
value is attached as described here] [round 9, R19b and R19c: the value no
longer waits on the bar entry but in `state.json`, off the entry, and at
the move the guide URL the user set LAST wins -- the held value, or the
record's own as set by the add form at submit or by the edit form; 1.5 and
1.6]. The only
trace is the shell's journal: `the bar entry keeps an input no source has
adopted yet (epgUrl)`, the key name and never the value. Observed through
the harness by key-scenario U1-U7 (lane A, lane-key-w1, 2026-10-12; red on
`--baseline lane-key-v2`); the form route is node only [round 8: observed
through the harness too, key-scenario A1 and A2 on lane-key-x1, the add
into an empty list still node only]. Round 8 also makes the waiting value
indifferent to spacing: a value pasted with a trailing space or newline
(`omarchy bar set` stores it as typed) is the same value as without, and a
value of spaces alone is no value (R18a). A mistyped `playlistUrl` set
beside a waiting guide URL is reported and removed once, and nothing
repeats -- on the round-7 build the plugin handed the lagging host the same
entry about 3,000 times a second in that state, with nothing on screen to
say so
(R18b; key-scenario K).

**Setting the same value again (round 9, R19a).** `g` after an `omarchy
bar set ... showLogos true` turns logos off, every time; a mistyped
credentialed `playlistUrl` set again from a terminal is removed again; a
guide URL set again is taken off the entry again. On the round-8 build,
on today's Omarchy (the host that publishes one write behind), an `omarchy
bar set` that put the entry back exactly as the plugin had last seen it
made the plugin skip its next write: the footer said `Logos off` while
logos stayed on and were fetched, also after a restart, and a re-set
credential stayed in `shell.json` for the rest of the session (the eighth
review, both lenses, live). Nothing new is on screen; the screen is now
true. Observed through the harness by key-scenario Y1 (logos), Y2 (the
refused credential) and Y3 (a guide URL set twice, then edited in the app,
the edit standing after a restart), each red on `--baseline lane-key-y0`
(lane A, lane-key-y1).

**A guide URL whose save failed, then an edit (round 9, R19d; D-SRC-18).**
When the state write that would adopt a terminal guide URL fails, the
value is left on the bar entry (R13) and the shell's journal says
`state.json could not be written`. If the user then changes that source's
guide URL in the edit form and that save lands, the older terminal value is
taken off the entry once it has, so the next shell start does not put it
back over the edit; before round 9 it did. Nothing on screen changes. Observed through
the harness by key-scenario H1 (red on `--baseline lane-key-y0`). [Round
10, R20b: also when the shell stops in the instant between that save
landing and the older value being taken off. The plugin's own file now
records, as a fingerprint and never the URL, which values it has already
read from the entry, so a value it has read is not read again as new at
the next start; before round 10 it was, in that instant, and replaced the
edit (D-SRC-18's last window). Nothing on screen changes. Observed in node
through the service's own functions and by the round-9 lens's own driver
under lane A's cage, not by a key-scenario segment.]

**The logo toggle no longer puts a removed value back (round 10, R20c;
D-SINK-20).** `g` behaves as it always has. Beneath the screen, on today's
Omarchy (the host that publishes one write behind), the toggle's
logo-only write while a save is outstanding used to copy back whatever the
host still published, including a guide URL or a mistyped credential the
plugin had just removed from `shell.json`; the credential then stayed there
for the rest of the session, and a guide URL put back that way replaced a
later edit at the next start. The write now carries back only a value the
plugin's own file does not yet hold -- the one copy of an input whose save
failed, which the round-4 review showed must never be dropped -- and
nothing it has already stored or refused. Nothing on screen changes; the
footer's `Logos on` / `Logos off` is the same. Observed in node and by the
round-9 lens's driver under lane A's cage (`stored epgUrl=no` after the
toggle on lane-key-z1, `yes` for the session on lane-key-y2); key-scenario
Y4 observes the toggle itself twice in a row, and L1/L2 that the only copy
is kept.

**After the migration, none of the four paragraphs above describes a
terminal value any more (round 11, 2026-10-13; R21).** They are the record of
rounds 7-10 and stand as written. What the screen does now: a `playlistUrl`
or `epgUrl` set from a terminal once the migration has landed is refused --
the active source, the list and the footer do not change -- and shows one
desktop notification (5.9); the plugin's next write, usually at once, takes
it off the bar entry. `g` meanwhile carries no retired key at all, so it can
neither keep nor put back a terminal value (D-SINK-20 ends at the marker).
Inside the migration window (a 0.13.x install's first start, until the state
write carrying the marker lands) the old protections stand: a migration
input whose save failed stays on the entry as its only copy, and `g` leaves
it there (node `R21e (...) round 4's P1 at the migration`; key-scenario F
and H through a state directory that loses its write bit after `state
init`). Observed at the sink by key-scenario X1-X6 and by U, K, Z, A, Y2,
Y3, Q and V moved to the new contract (lane A, lane-key-m1: 98 / 0 forward,
68 / 30 on `--baseline lane-key-z2`).

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

### 5.9 Bar-setting notifications (D-SINK-19 round 11, R21b and R21c; 2026-10-13)

The product owner dropped the `omarchy bar set` URL route on 2026-10-13: the
Sources screen is the only way to add or change a source. A value the plugin
takes off the bar entry without adopting it is reported ONCE, as a desktop
notification and the same sentence on the shell's console
(`omarchy-iptv: <body>`), and the guide shows nothing -- the active source,
the list and the footer are untouched, because nothing changed. The text is
`Model.entryInputNotice(name, reason)` as shipped on lane-key-m1, composed from
the setting's NAME and the reason and never from the value (rule 5: the value
can be a credentialed URL); `<setting>` is `playlistUrl` or `epgUrl`, and any
other name reads `A URL setting`. The notification is `omarchy-notification-send
--app-name IPTV -u normal -g <alert glyph> -r 74016 <title> <body>`, one replace
id for every such report, so a user who set both URLs sees one card, the
last.

| When | Title | Body |
|---|---|---|
| After the migration: a `playlistUrl` or `epgUrl` found on the entry (`retired`) | `Bar setting ignored` | `<setting> is no longer read from the bar settings and was removed. Add or switch sources in the guide's Sources screen.` |
| At the migration: a guide URL with no source to attach it to (`no-source`, R21c) | `Bar setting removed` | `epgUrl was removed from the bar settings: no source was set up for it to guide. Add the source with its EPG URL in the guide's Sources screen.` |
| At the migration: a value that does not validate (`invalid`) | `Bar setting removed` | `<setting> in the bar settings was not a usable URL and was removed. Add or edit sources in the guide's Sources screen.` |
| At the migration: the `playlistUrl` does not validate AND an `epgUrl` is set beside it (`invalid-pair`, round 19, R29d, 2026-10-20; reported once, as `playlistUrl:invalid-pair`, in place of the two reports it used to make) | `Bar setting removed` | `playlistUrl in the bar settings was not a usable URL and was removed, with the epgUrl beside it. Add or edit sources in the guide's Sources screen.` |
| The same pair, when the unusable playlist was reported before (seen, so not adopted again) and a fresh guide URL arrives beside it before the migration's write has landed (`invalid-pair` from the guide URL's side, R29d's rule-15 sibling; `epgUrl:invalid-pair`) | `Bar setting removed` | `epgUrl in the bar settings came with a playlistUrl that was not a usable URL, and was removed with it. Add or edit sources in the guide's Sources screen.` |
| At the migration: Sources already holds 50 sources and the entry's playlist is not among them, so the migration does not run (`full`, round 17, R27d, D-SRC-44; reported once a session as `playlistUrl:full`, and again at each start while it holds; round 18, R28b: the body names the guide URL held with it; round 19, R29e: and says which source is active once one is removed) | `Sources is full` | `The playlist set on the bar, and its guide URL if one is set, were not moved into Sources: Sources already holds 50 sources, the most it can. Remove one in the guide's Sources screen and the bar's playlist and its guide move in together; the bar's playlist then becomes the active source.` |

"Once" is per value per session: the same value set again is not reported
again (the plugin keeps an in-memory list of what it has handled, nothing on
disk), a different value is, and a value still on the entry at the next start
is reported once more. An `invalid` migration value with no source to fall
back on still reaches the guide's error state through D16, as before. The
wording, the notification as the only channel, and the absence of anything in
the guide are the code lane's reading of R21b and are raised to the lead as
open (lane-key-m1's report); this section records what ships and changes
nothing. Pinned in node (`R21b / rule 5: entryInputNotice -- one sentence per
reason ...`, `R21b: the refusal notification is entryInputNotice's sentence,
with its own replace id, and carries no value`) and observed at the sink by
key-scenario X5 (one notification per report through a stand-in
`omarchy-notification-send` in front of PATH, each naming the Sources screen,
none carrying a URL or the credential). The rendered card is UNVERIFIED on a
display.

[Round 17, 2026-10-20, R27d (D-SRC-44): THE MIGRATION NEVER EVICTS. The
`full` row is not a removal: the playlist URL STAYS on the entry (the
migration marker is not set, so the entry funnel keeps the retired keys;
`shell.json` is 0600 under the D-SINK-18 shield), no record is added or
evicted, and the report `playlistUrl:full` is what keeps round 11's oracle
-- an entry URL ends in a record or is reported -- true. It shares replace
id 74016, so on screen it replaces a refusal card shown just before it.
The next reconcile after a removal migrates the URL and makes it the
ACTIVE source: an in-app removal asks for one (`Service.retryHeldMigration`,
folded by `Qt.callLater`), and a hand-run `state source remove` is picked
up by the reconcile its load runs. Pinned in node through the shipping
`Service.qml` on both hosts and both own-echo modes (`R27d (<tag>): D-SRC-44
-- ...`, three pins) and live by key-scenario B35 and B36. [2026-10-20, F1
(round 3's dataloss review, P2): when another program fills the freed
place before the retry's save has read the file, the merge drops the
migrated record at the cap, and until F1 the marker landed anyway: both
URLs left the entry for no record, told only as `1 source added here ...
was not kept`. Now the migration stays HELD -- no marker, both URLs on the
entry, this same card and no new one, the next removal tries again
(`Model.mergeForeignState`'s `migrationHeld`); and when the other program
added the same playlist itself, the migration runs again over its record
at once, the bar's guide URL with it. Pinned: `F1 (<tag>): held full, a
HAND-RUN ...` and `F1 (<tag>), rule 15: ...`, red on lane-sweep-c3.] Until R27 the
least recently used source was evicted to make room, its URL the only copy,
with a journal line only. What the code does around it that no pin
covers, measured by the documents lane through `tests/service-harness.js`
on lane-sweep-a1 (both hosts): an install updated from 0.13.6 has no
`activeKey`, so while the migration is held NO source is active and the
guide is unconfigured; a guide URL on the entry beside the playlist is
reported `no-source` (`Bar setting removed`, which says it was removed) but
stays on the entry, and is NOT attached when the playlist moves in (the
new record's guide URL is empty and the entry is stripped of both); and a
source picked in Sources meanwhile receives that guide URL at the next
start, in place of its own (`A` with its own guide URL, picked, restart:
`A`'s guide URL is the bar's). Raised to the lead; the README states it as
not covered.]

[Round 18, 2026-10-20, R28b: A HELD MIGRATION HOLDS BOTH URLS. The
paragraph above is history. With the migration held at the cap, a guide URL
on the entry beside the held playlist is held WITH it: it is not attached
to any source, not reported as `no-source`, and not stripped, so the only
card is `Sources is full`, whose body now names it (the row above), and
nothing on 74016 replaces it in the same turn. A source picked meanwhile
keeps its own guide URL across a restart. The removal that lets the
playlist in adds it WITH the bar's guide URL, and the entry is stripped of
both. Driven by this lane through the shipping `Service.qml` on
lane-sweep-a2 (both hosts): `reports:["playlistUrl:full"]`, `notes:["Sources
is full"]`, A's guide URL its own before and after a restart, and after one
removal the new record's guide URL is the bar's and the entry holds
neither. Pinned in node (`R28b ...`, both hosts and both echo modes) and
live by key-scenario B38 and B39, both red on lane-sweep-c1 (`a-epg:bar`,
`d-epg:empty`). Still true and unchanged: an install updated from 0.13.6
has no active source while the migration is held, so the guide opens
unconfigured over the 50 saved sources, and when one is removed the bar's
playlist becomes the ACTIVE source over whatever was picked.]

[Round 19, 2026-10-20, R29e: THE CARD SAYS WHICH SOURCE ENDS ACTIVE. The
`full` body now ends `; the bar's playlist then becomes the active
source.` (the row above), because a user who picked a source while the
migration was held finds the bar's playlist active after removing an
unrelated one (round 2's live review, HM2: `active=D`). The behaviour is
unchanged; R28b's service pin already holds NEW active over A after the
removal. The guide opens unconfigured only until a source is picked: a
picked source is the one it opens on across restarts (round 2's review,
`mid:{active:"A",Aepg:"OWN"}`).]

[Round 19, 2026-10-20, R29d: A GUIDE URL THAT CAME WITH AN UNUSABLE
PLAYLIST IS NEVER ADOPTED ONTO ANOTHER SOURCE. Until R29d the `invalid`
row's playlist was refused at step 1 while the R4 block still ran the
entry's guide URL onto the record steps 2-4 named -- the active source --
replacing that source's own guide URL, often its only copy, with only the
playlist's card to say anything had happened (round 2's review, `Aepg:
"BAR"`, the same on 6f1d176, 0.14.2 and lane-sweep-c2); with no active
source it was reported `no-source` beside the playlist's `invalid`, two
cards. Now `Model.adoptActiveSource` skips the R4 block when the playlist
beside the guide URL is unusable (`epgWithInvalid`), the service tells the
pair in ONE card (`invalid-pair`, the two rows above, no URL), and the
owned write takes both off the entry once the marker has landed. The same
holds for the rule-15 sibling: a playlist already reported (seen) that
still does not validate when a fresh guide URL arrives beside it before
the marker lands. Pinned in node through the shipping `Service.qml` on
both hosts and both own-echo modes (`R29d (<tag>): ...`, three pins, each
red on lane-sweep-c2) and in `tests/fixtures/active-key.json`, and live by
key-scenario B40 (A keeps its own, one card, the guide URL in no file) and
K1..K3, which read `playlistUrl:invalid-pair` where they read
`epgUrl:no-source,playlistUrl:invalid` (lane A3, transcripts
`key-20261020-184353-2546836` forward and `key-20261020-190233-2645772`
red on lane-sweep-c2). The `no-source` row now covers only a guide URL
with no playlist at all.]

### 5.10 Saved sources not loaded, and Saving has stopped (D-SINK-19 round 12, R22a; round 13, R23; 2026-10-13; round 14, R24; round 15, R25; 2026-10-14; round 16, R26; 2026-10-16; round 17, R27; 2026-10-20)

`~/.local/state/omarchy-iptv/state.json` is the only copy of the user's
sources and provider URLs. When it exists but cannot be read -- permission
denied, not a regular file, a symbolic link that leads nowhere or to
something that is not a regular file, a file where its FOLDER should be
(round 14), a symbolic link AT its folder that leads nowhere or to
something that is not a folder (round 15), an I/O error -- or does not parse as a state (an empty file
included, settled by the lead on 2026-10-13), or when the start-up check of
it does not answer (round 13), or, mid-session, the read before a save
does not answer twice (round 17, R27a; withdrawn by round 18, R28a, and
kept withdrawn by round 19, R29a: a read that does not answer is NOT this
mode -- its save goes ahead without it after 2 s, item 9), the plugin WRITES NOTHING to it for the rest
of the session [round 16 and 17: until a read finds it readable again, item 5] -- and since round 14 (R24e) neither does the helper the
service starts, because the playlist fetch is handed no state directory. Until round 12 it read such a file as an
empty state and saved that over it at the start, which erased every source,
credential and favourite (the round-11 data-loss lens, live). What the user
sees, as built on lane-key-n1 and amended on lane-key-p1 (round 13),
lane-key-q1 (round 14) and lane-key-k1 (round 15):

1. Once per episode, a desktop notification: `omarchy-notification-send
   --app-name IPTV -u critical -g <alert glyph> -r 74017 <title> <body>`, and
   the same words on the shell's console. The text
   is `Model.stateUnreadableNotice(reason, path, midSession)`, composed from the reason
   and the file's path and never from anything in the file.
   **[Round 17, 2026-10-20, R27e (D-SRC-42, D-SRC-50, D-SRC-51): the copy
   below is the shipping model's, and `tests/fixtures/state-notices.json`
   holds every sentence of it verbatim for one path, pinned both ways by
   node (`R27e: every body is the fixture's sentence, word for word`).]**
   The title is `Saved sources not loaded` when the block begins at a start
   (`Model.STATE_BLOCK_TITLE_START`) and `Saving has stopped` when it begins
   after a state has loaded (`Model.STATE_BLOCK_TITLE_MID`; `midSession` is
   the service's `stateLoaded` when the block begins) -- in the notification,
   on the console and in the guide's own notice alike (until R27e only the
   Sources header said `Saving has stopped`, D-SRC-38, and the notification
   called a mid-session block `Saved sources not loaded` over sources that
   had loaded, D-SRC-42). The console line is
   `Model.stateUnreadableJournal`: `omarchy-iptv: <title>: <body>`. The body
   is `<path> <what>. <unsaved> <fix>`, with `<path>` the full path of
   `state.json` (`Service.stateFilePath`) and `<unsaved>` one of two
   sentences (round 18, R28e, 2026-10-20). At a START it is `Sources,
   favorites and settings changed now are not kept.`
   (`Model.STATE_BLOCK_UNSAVED_START`): nothing has loaded, so whatever load
   lifts the block is the first and is applied over such a change. In a
   block that begins MID-session it is `Favorites and other changes made
   now are held in this session only: the next such change made here saves
   them if it finds the file again, but they are dropped if the file comes
   back by itself first, if a source change is what finds it, or if the
   shell is stopped.` (`Model.STATE_BLOCK_UNSAVED`), which names the four
   ways back item 5 describes. It said `Nothing is saved until it can be
   read, so sources, favorites and settings changed now are not kept.` until
   R27e, which is false on the one way back where the next change's own read
   finds the file first and saves it (D-SRC-51); from R27e until R28e it said
   `Sources, favorites and settings changed now are not saved until the file
   can be read again.` in both, which is literally true and promised what
   happens on one way back only -- on the road the notice itself advises
   (restore a backup, point a link back and make a source change) the change
   was dropped (round 1's live review, segments H5 and H2). The
   `tests/fixtures/state-notices.json` fixture holds `bodies.start` for
   every reason a start can carry and `bodies.midSession` for the five a
   load can:

   | Reason | `<what>` | `<fix>` |
   |---|---|---|
   | the file is not readable (`permission`) | `is not readable (permission denied)` | `Make it readable with chmod 600 on that file, then run omarchy restart shell.` |
   | something other than a file is at the path (`not-a-file`: a directory or a FIFO, both measured live; a socket is refused by the helper, but what the FileView reports for one is unmeasured, so its row is not known) | `is not a regular file` | `Move whatever is at that path aside, then run omarchy restart shell.` |
   | the file does not parse (`unparsed`) | `is not a valid state file` | `Restore it from a backup, or move it aside to start with no sources, then run omarchy restart shell.` |
   | at a start, the folder cannot be read: the file reads as missing, but the helper found something there (`absent-unconfirmed`) | `could not be found, or its folder could not be read` | `Make the folder readable with chmod 700, then run omarchy restart shell.` |
   | mid-session, the file reads as missing (`absent`; round 14, R24b: its own `<fix>`, because the helper is not asked mid-session and a broken symbolic link and an unreadable folder look the same to the FileView; round 17, R27e, D-SRC-50: the link case first, and pointed BACK, `Model.STATE_BLOCK_LINK_FIRST`) | `could not be found, or its folder could not be read` | `If it is a symbolic link, point it back at the folder or file that holds your state; otherwise make the folder readable with chmod 700. Then run omarchy restart shell.` |
   | a symbolic link at the path whose target is missing or is not a regular file, as the helper's start-up check found it (`link`, round 14, R24b; round 17, R27e: point it back) | `is a symbolic link whose target is missing or is not a regular file` | `Point it back at the file that holds your state, or move the link aside, then run omarchy restart shell.` |
   | something that is not a folder where the state FOLDER, or one above it, should be (`not-a-dir`, round 14, R24b; `<path>` is then the folder's, `/home/you/.local/state/omarchy-iptv`) | `is not a folder (a file is at that path, or at one above it)` | `Move whatever is at that path aside, then run omarchy restart shell.` |
   | a symbolic link at the state FOLDER, or at one above it, that leads nowhere or to something that is not a folder (`folder-link`, round 15, R25c, D-SRC-32; `<path>` is the folder's; round 17, R27e: point it back) | `is a symbolic link whose target is missing or is not a folder (or a folder above it is)` | `Point it back at the folder that holds your state, or move the link aside, then run omarchy restart shell.` |
   | the start-up check -- since round 14 the `mkdir` before it too (R24d) -- did not answer within 15 s and was stopped (`init-timeout`, round 13, R23c) | `could not be checked: the start-up check did not answer and was stopped` | `Make sure a regular file, or nothing, is at that path, then run omarchy restart shell.` |
   | ~~mid-session, the read before a save did not answer within 2 s, was asked once more, and did not answer again (`read-timeout`, round 17, R27a, D-SINK-22 window c)~~ **WITHDRAWN 2026-10-20 (round 18, R28a, and kept withdrawn by round 19, R29a): a read that does not answer is not this mode (item 9); the reason is gone from the model, and a load failure a read answers with blocks under that load's own row** | ~~`did not answer when it was read before a save (twice, 2 seconds each)`~~ | ~~`The next change made here reads it again, and saving resumes if it answers. If it keeps stopping, check the disk or folder that holds it, then run omarchy restart shell.`~~ |
   | any other failure (`io-error`) | `could not be read` | `Check the file and its folder, then run omarchy restart shell.` |

   For example, for a file that does not parse at a start, verbatim from the
   model with the user's home spelled out: `Saved sources not loaded` /
   `/home/you/.local/state/omarchy-iptv/state.json is not a valid state file.
   Sources, favorites and settings changed now are not kept. Restore it from
   a backup, or move it aside to start with no sources, then run omarchy
   restart shell.` The same file emptied under a running shell reads `Saving
   has stopped` over `/home/you/.local/state/omarchy-iptv/state.json is not
   a valid state file. Favorites and other changes made now are held in this
   session only: the next such change made here saves them if it finds the
   file again, but they are dropped if the file comes back by itself first,
   if a source change is what finds it, or if the shell is stopped. Restore
   it from a backup, or move it aside to start with no sources, then run
   omarchy restart shell.`

2. **At a start, the guide draws the no-write surface, never the first-run
   form (round 13, R23e; this closes the open question round 12 left
   here).** Nothing has loaded, so the guide is unconfigured, and
   `Model.guideSurface` answers `stateUnreadable` instead of `unconfigured`;
   `Model.firstRunAllowed` is false, so the guide does not open into the
   first-run form -- not on open, not when the mode begins while the guide is
   open, and not on the Esc / `o` return from Sources. The body is the empty
   state with the alert glyph, and its title and prose are
   `Model.stateUnreadableNotice` for the current reason and path: the SAME
   words as the notification, one source of copy. Wireframe (UNVERIFIED on a
   display; the wrap is the card's):

   ```
   +-----------------------------------------------------------------+
   |                                                                 |
   |                        <alert glyph>                            |
   |                   Saved sources not loaded                      |
   |   /home/you/.local/state/omarchy-iptv/state.json is not a       |
   |   valid state file. Sources, favorites and settings changed     |
   |   now are not kept. Restore it from a backup, or move it aside  |
   |   to start with no sources, then run omarchy restart shell.     |
   |                                                                 |
   +-----------------------------------------------------------------+
   | Esc close                                                       |
   +-----------------------------------------------------------------+
   ```

   - No editable field exists while it shows (D-CLIP-1): there is no form,
     and the harness's census of editable text inputs reads 0 there
     (key-scenario B11 `editable:0`).
   - The footer is `Model.footerHints` for an empty guide with no retry:
     `Esc close`, plus `o sources` only when sources are in memory -- which at
     a no-write start they are not, because nothing loaded. `r retry` is not
     offered: a refresh cannot make the file readable.
   - The Sources screen stays reachable (R23e): the `o` key is not gated on
     the source count (`Guide.qml` `handleListLetter`), though the footer
     does not name it here; the round-13 live lens drove `o` from this
     surface and it opened Sources (the lead's ruling (5), 2026-10-14). What
     Sources draws in the mode is round 14's (R24f, D-SRC-28; 3.2.6): its
     header's right slot is the notice's title, `Saved sources not loaded`,
     where it read `No sources` over a file holding records; NO `Add source`
     or `Add Xtream login` rows; `a`, `c` and Enter on an Add row open no
     form and answer `state.json could not be read · nothing is saved until
     it can be` in the footer; the footer hints are `Esc back` (5.3).
     Observed by key-scenario B15 at a no-write start (`mode:sources
     header:notice rows:0 addhint:no after-a:sources says:no-write
     editable:0`), red on dev (`header:[No sources] rows:2 after-a:sourceEdit
     says:other`). Its `addhint` token does not discriminate at row 0 (dev's
     hints on an Add row carry no ` add` either); the other tokens do.
   - The bar entry is left exactly as it is.

3. **Every refusal says the no-write reason (round 13, R23f).** In the mode,
   an add, an edit, a switch and a remove are refused on the result line (a
   form) or in the footer with the service's own code, `state_unreadable`:
   `state.json could not be read · nothing is saved until it can be` (5.5;
   the middle dot is `Model.SEP`). The logo toggle (`g` in Sources, on and
   off) and a persist failure signalled while the mode holds now go through
   `Model.refusalMessage(code, stateWriteBlocked, kind)` and read the same
   sentence. Round 12's live lens read `Could not save settings · try omarchy
   bar set` there -- the wrong reason and the wrong advice; that sentence is
   still what `persist_failed` reads OUTSIDE the mode. Observed by
   key-scenario B12 (`says:no-write advice:none writes:0`).

4. **Mid-session** (the file made unreadable, emptied or overwritten in
   place under a running shell, so the guide's file watch reloads it): the
   guide keeps the channels, the active source and the favourites it already
   had -- it never switches to the surface in 2 while it holds channels
   (the lead's ruling (3), 2026-10-14). Source changes, Add and the logo
   toggle are refused with the sentence in 3, and Sources keeps the rows of
   what memory holds under the header `Saving has stopped` (3.2.6; round
   15, D-SRC-38 -- under the notice's title until then). A favourite, a hidden
   group, a saved or forgotten search or a removed recent still changes on
   screen with its usual confirmation, for this session only: it is not
   kept, which only the notification's "changed now are not kept" says (the
   lead's ruling (4), 2026-10-14: the transients keep their own copy).
   [Round 17, 2026-10-20, R27e (D-SRC-51): the notification now says such a
   change is "not saved until the file can be read again", and whether it is
   kept depends on the way back (item 5): kept when the next change's own
   read finds the file first, dropped when a load of the file arrives on its
   own first.] [Round 18, 2026-10-20, R28e: the notification now names the
   ways back themselves -- `held in this session only: the next such change
   made here saves them if it finds the file again, but they are dropped if
   the file comes back by itself first, if a source change is what finds
   it, or if the shell is stopped` (item 1). Each way is pinned through
   `Service.qml` on both hosts and both echo modes to that sentence: the next
   favourite saved; the file back by itself, dropped; a source change,
   dropped; a restart, dropped. The behaviour is R22's and unchanged, the
   same on 6f1d176.]
   **The condition, as measured (corrected 2026-10-14, D-DOC-8: this item
   used to make the session's own saves the variable).** The mode begins
   when the FileView delivers the reload, and whether it does depended on
   one thing: whether the state DIRECTORY existed when the view first loaded
   (the round-13 live lens, on lane-key-p2 and on a 0.13.6 export). With it
   present -- every session but one -- every external change is reloaded,
   before or after the session's own saves. With it absent -- the FIRST
   session after a fresh install, `omarchy-iptv/` not yet under the state
   home -- the view saw nothing all session, so garbage written in place was
   never noticed and a hand-run `state source add` was written over by the
   next in-app save. Since round 14 the service reloads the view once after
   its start-up check (R24c) and that session sees changes too. What
   observes it: key-scenario B5-B7 and B9 (an existing directory, no own
   save before the damage), B16 (the fresh-install session: a hand-run
   `state source add` seen and kept through an in-app add's save, then
   garbage written in place noticed and told once, `seen:1 file:C,D
   blocked:unparsed told:1`; on dev `seen:0 file:D blocked: told:0`). An
   existing directory with the damage AFTER an own save is observed by the
   committed FileView spike (`scripts/dev-harness/spikes/filewatch/`,
   `RESULT-2026-10-13.txt`, every sequence) and by the round-13 live lens's
   rig, and by no key-scenario segment [round 15, R25d: key-scenario B21
   observes it -- a migrated install starts, an in-app change's save lands,
   garbage is written in place, and the mode begins and is told once
   (`blocked:unparsed told:1 file:garbage{`); it is green on dev, which
   watched already, and red with `stateFile`'s `onFileChanged: reload()`
   deleted (`spikes/key-mutations/r25d-no-reload-on-change.patch`)]. This
   is for a regular `state.json`; for a symbolic link the watch has a limit
   (item 6). The Sources header in that block is observed by B22; the
   notification and the guide body keep the notice's title there (a copy
   question raised to the lead, `ARCHITECTURE-SOURCES.md` round 15).
   [Round 16, 2026-10-16, R26a: the mode can also begin at a SAVE. Every
   save the session makes now reloads `state.json` first and is decided by
   what that load finds, so a path the watch lost without a signal -- a
   `state.json` link or the state-folder link re-pointed at a place with no
   `state.json` -- begins the mode at the next save instead of that save
   creating a file there (D-SINK-21). Observed by key-scenario B28 (the
   folder link re-pointed at an empty folder, then an in-app label edit:
   `edit:true created:none holds:[] blocked:absent told:1
   next:state_unreadable`); the file-link twin is pinned in node only. The
   reason is `absent` and the copy is that row's: nothing new is drawn. The
   change that asked for the save shows on screen and its source call
   answered `ok` -- the call answers when its write is ISSUED (R13), and
   the read that refuses it comes after (R26e, stated, not changed) -- so
   the notification is what tells the user it was not kept, and the next
   source call answers `state_unreadable`.]

5. It ends by itself when a load that IS a state arrives: the file put back
   in place (the guide's file watch reloads it, key-scenario B7) or fixed and
   `omarchy restart shell` run. [Round 15, D-SRC-35: "put back in place" is
   measured for a regular `state.json` whose contents or mode were wrong. A
   symbolic link whose target went missing mid-session blocks as `absent`,
   and its target coming back is NEVER seen -- the round-14 lenses, `mv`
   aside and back (`blocked:[absent]` with no reload counted), and the
   FileView alone (`fileChanged+0 loaded+0` on the restore and for every
   write after it) -- so that session stays in the mode until a restart,
   which reads the restored file. Nothing is lost, and the `absent` sentence
   already ends with the restart. The README no longer says a good copy is
   enough on its own for that case.] [Round 16, 2026-10-16, R26a
   (D-SRC-35): it also ends at the next SAVE, and that is how a returned
   link target is noticed. A save asked for in the mode (a favourite, a
   hidden group, a saved or forgotten search, a removed recent: each calls
   `saveState`) reloads the file first unless the reason is `init-timeout`
   (`Model.stateSavePlan` answers `verify`), and a load that is a state
   lifts the mode; a source call (switch, edit, retry, remove:
   `sourcesReady` and `removeSource`) meeting the mode is refused as before
   and asks for one reload (`Model.stateBlockRecheck`), so the FIRST source
   call after the file comes back is refused and the SECOND lands
   (key-scenario B29 `away:absent told:1 first:state_unreadable lifted:[]
   second:true`). Accepted and stated by the lead. `a` and `c` are refused
   by the guide itself (`Model.sourcesAddAllowed`) and ask for no reload.
   What a favourite made at that moment keeps, by calling the shipping
   `Service.qml` through `tests/service-harness.js` (the documents lane's
   probe, every block shape here, the path repaired with no signal): in a
   block that began MID-session it is kept and written; at a no-write
   START it lifts the mode but is not kept -- the file's state is applied
   over it -- which the notification's "changed now are not kept" already
   says. The restart stays the way out for every reason. For
   `init-timeout` no save and no source verb re-reads, but a watched load
   of a good state lifts it like any other reason (`liftStateBlock` does
   not look at the reason; the claims lens's probe, re-run on
   lane-clean-f1: `before:init-timeout ... afterForeignEdit:[] switch:ok`
   on both hosts).] Writes resume at once, and a later episode in
   the same session is told again -- pinned since round 13 (R23a: node `R23a
   (<mode> host, mid-session, <between> between): TWO no-write episodes ...`
   and key-scenario B9 `told:1/2`, both seen red with the re-arm deleted).
   [Round 18, 2026-10-20, R28e and R28a: the bracket below is history.
   Item 1 has the two sentences that replaced R27e's (`not kept` at a start,
   the four ways back mid-session), and `read-timeout` is withdrawn -- a read
   that does not answer is item 9 (round 19, R29a, keeps it withdrawn: the
   save goes ahead without the read after 2 s).]
   [Round 17, 2026-10-20, R27a and R27e. Where this item and item 4 quote
   the notification's "changed now are not kept", it now reads "are not
   saved until the file can be read again" (item 1). The new reason,
   `read-timeout`, ends the same way as any liftable one: a save asked for
   in it reads the file first (`Model.stateSavePlan` answers `verify`), and
   a source call is refused once and asks for one reload
   (`Model.stateBlockRecheck`); a read that answers lifts it. Pinned through
   `tests/service-harness.js` on both hosts and both own-echo modes: the
   next in-app change reads, the mode lifts, and the change made in the block
   and this one are both written, told once in all (`R27a (<tag>): window c
   -- the read-timeout mode is lifted by a later read that ANSWERS ...`);
   through a source verb, the first call answers `state_unreadable` and the
   second lands (`R27a / R26e (<tag>): window c through a SOURCE verb ...`).
   No live segment: no way was found to stall a FileView read for 2 s in the
   cage without FUSE or root (lane-sweep-a1's report).]

6. **Something other than a file at the path, or a start-up check that
   hangs (round 13, R23b-R23d).** A directory or a FIFO at `state.json` is
   the `not-a-file` row of 1 (a socket too as far as the helper goes, which
   refuses it the same way; the FileView's report for a socket is
   unmeasured): the helper opens the path
   without blocking, refuses it on the descriptor's own `fstat`, and leaves
   it exactly as it was -- a directory is no longer chmod-ed to 0600 (round
   12's live lens saw one made unsearchable), and a FIFO no longer hangs the
   start (key-scenario B14 `blocked:not-a-file ... left:none fifo:600`). If
   the helper's start-up check does not answer within 15 s for any other
   reason, the service stops it (TERM, then KILL 2 s later), leaves no
   process behind (B10 `left:none`), and enters the mode with the
   `init-timeout` row. A hand-run `state` command over a non-regular file
   answers `state.json is not a regular file; nothing was written`, exit 1.
   [Round 14, R24b and R24d.] A **symbolic link** at the path is followed
   when it leads to a regular file -- the helper's `state` commands read and
   write THROUGH it and the link stays a link (the FileView's own save was
   measured doing the same, spike set `r24` sequence V; until round 14 the
   helper replaced the link with a plain file and the running view then saw
   none of its later writes, V and W) -- and refused when it leads nowhere
   or to anything else: the start blocks with the `link` row, and every
   `state` command answers `state.json is a symbolic link whose target is
   missing; nothing was written` (or `... is not a regular file ...` for a
   link to a directory or a FIFO), exit 1, the link untouched. A **file where
   the state folder should be** blocks with the `not-a-dir` row; `state init`
   answers `found: not-a-dir` with no traceback, and every other `state`
   command `the state folder is not a folder (a file is at its path, or above
   it); nothing was written`. Neither fault is driven by a key-scenario
   segment: the copy and the decision are pinned in node, the helper's
   answers in python.
   [Round 15, 2026-10-14, R25e (D-SRC-29): what a running shell NOTICES
   through a link at `state.json` is narrower than "every change". It sees a
   change made THROUGH the link -- the helper's `state` commands, an
   in-place write of the path or of the target, a `cp` of a backup onto
   the path, and an edit of the target at its OWN path, in place or by a
   rename onto it (the round-14 lenses' Z1-Z3, C10). It does NOT see a tool
   that REPLACES the link, or puts a file over it, at the state path -- `mv`
   of an edited copy or a backup onto it, GNU `sed -i` on it, `rm` and `cp`,
   `ln -sfn` to another target -- and after one of those it sees nothing more
   that session, so the next save (an in-app change, a play, a refresh that
   updates a source's counts) writes memory over the change, and in the
   `ln -sfn` case into the NEW target (C1, C8, C9, C11, Z4, Z6; the real
   `Service.qml` live, `probe14.sh`). 0.13.6 loses the same edits. One
   explicit `reload()` re-arms the view (Z7); that lever is filed for a later
   release and not built. What the user is told to do, in the README: edit
   the target in place, put a backup back with `cp`, or run `omarchy restart
   shell` straight after such a tool and before using the guide. No
   key-scenario segment drives a link; the measurements are the lenses' rigs
   (session scratch), recorded in `ARCHITECTURE-SOURCES.md`'s round-15
   rulings and the contract's fact seven.]
   [Round 16, 2026-10-16, R26a (D-SRC-29 closed): such a replacement is
   still not seen WHEN it happens -- the watch loses the path without a
   signal, and R26d refuses a periodic reload -- but it is seen at the next
   save, which reloads the file first, merges it with the change being
   saved through R24a's rules (item 8), and re-arms the watch. key-scenario
   B23-B25 (`mv`, `sed -i`, `rm` + `cp` over a linked `state.json`, each
   carrying a hand edit, then an in-app label edit): the file and memory
   hold both edits and the old target is untouched; B26 (`ln -sfn` to
   another state): THAT file keeps its own label and favourite, takes the
   in-app edit, and becomes what the session holds. A link re-pointed at a
   file that does not exist yet creates nothing and begins the mode (item 4;
   node only) -- outside the three windows of milliseconds the folder-link
   bracket below names, in which the save still creates it at 0644. Until that next save the guide shows what it had and
   nothing is written (FRESH, stated: node `R26d (...): FRESH, stated --
   ...`), so nothing is lost; the README says to restart to see the change
   at once. The README's advice changes from "restart straight after such
   a tool" to "it is noticed at the next save".]
   [Round 15, R25c (D-SRC-32): the state FOLDER gets the file's rule. A link
   at `~/.local/state/omarchy-iptv` that leads to a folder is followed, and
   the start-up `state init` and every writing `state` command make the
   folder it leads to 0700, as they make the plugin's own folder (measured,
   `spikes/folder-link/RESULT-2026-10-14.txt`; the README says so). One that
   dangles or leads to something that is not a folder (or a link above it
   that does) blocks the start with the `folder-link` row of 1, naming the
   FOLDER; `state init` answers `found: folder-link` and creates nothing;
   every other `state` command answers `the state folder is a symbolic link
   whose target is missing or is not a folder; nothing was written`, exit 1
   -- `show` and `source list` included, which printed an empty listing with
   exit 0 until round 15. The helper's other verbs answer a plugin folder in
   that shape with `<folder> is a symbolic link whose target is missing or is
   not a folder; nothing was written` (code `folder_unusable`). The watch
   when the FOLDER is a link: measured since by both round-15 data-loss and claims lenses, 2026-10-14: through a valid folder link the service sees a helper write, a temp-and-rename edit and an in-place edit, and keeps all three; re-pointing the folder link (`ln -sfn`) raises nothing, nor does a later edit in the new folder, and the next own save writes the session's state into the new folder's `state.json` (D-SRC-40, the folder twin of D-SRC-29). No key-scenario segment drives a
   folder link.] [Round 16, 2026-10-16, R26a (D-SRC-40 and D-SINK-21
   closed): the re-point still raises nothing, and the next save now READS
   the new folder's `state.json` first: one that is there is merged with
   the change and becomes what the session holds, the old folder untouched
   (key-scenario B27 `new:A=f2-own,C=app-fl,favs=t:f2.uk
   old:A=seed,C=c-seven,favs=t:seed.uk`); none there begins the mode with
   nothing created (item 4, B28) -- where up to and including 0.14.1 the
   save created a 0644 `state.json` holding every source URL, unnoticed.
   Three windows still create it, each milliseconds long unless the disk
   stalls (the README's link bullet names them; lane-clean-f1's node
   probe over the shipping `Service.qml`): a save asked while the previous
   write is in flight skips its read; a re-point landing between the
   read's load and the write it allows; and the 2 s watchdog firing.
   [Round 19, 2026-10-20, R29a: two of the three remain. The first is
   closed (R27a window a, kept: a save asked while our write is out waits
   for it, at most 2 s, then reads); the second is unchanged; the third, the
   2 s watchdog firing, is open again exactly as here -- R27a and R28a
   closed it and R29a withdrew both (item 9).] B23-B31 drive the
   links now; the README says that after re-pointing and restarting, the
   NEW folder is what loads.]
   [Round 15, D-SRC-34: a `state.json` link into a folder the user cannot
   write is a sentence, `state.json is a symbolic link into a folder that
   cannot be written (Permission denied); nothing was written`, exit 1, the
   folder's mode left alone -- it was a traceback with `code: internal`.] The **bound** now covers the start-up `mkdir` too: one
   15 s watchdog from the moment `mkdir` starts, TERM then KILL to whichever
   of the two is running (the KILL observed, B17 `helper:yes left:none
   killed:1`); and the helper's init ends ITSELF 30 s after it starts, so a
   shell restarted while the check hangs leaves nothing behind past that
   (B18 `at-stop:alive after-deadline:gone left:none`). What no bound
   reaches: a process in uninterruptible sleep on a hung filesystem.

7. NOT this mode, and told nothing: a `state.json`, or its folder, left at
   mode 0000 by the user's own chmod while the shell was down (settled by the
   lead on 2026-10-13). The helper's start-up `state init` restores 0600 and
   0700, the start reads the file, and every source is there (key-scenario
   B1-B4). A file that does not exist at all is a fresh install, as before,
   and draws the first-run form (B13 reads its drawn copy, `Paste or type
   your M3U URL or path, then press Enter`).

8. NOT this mode either (round 14, R24a, D-SRC-22): **another program's
   write that parses.** A hand-run `state` command, or a backup put back,
   while the session holds a change of its own not yet on disk (a save
   parked at the start, under way, or failed). Until round 14 the service
   IGNORED that reload and its next save wrote over the other program's
   change, which had answered `ok: true`; 0.13.6 applied it and lost the
   in-app change instead. Now the two are merged (`Model.mergeForeignState`)
   and nothing is shown: both sides' favourites, hidden groups and saved
   searches; both sides' new, removed and changed sources; a setting changed
   by one side only. Where BOTH changed the same source, or the same
   setting, the other program's version is kept -- it is the later write, and
   an in-app change that is still unsaved because its save FAILED was
   already told so (`Could not write state.json · check
   ~/.local/state/omarchy-iptv`) -- and the shell's console gets one line per
   such case, `omarchy-iptv: state.json was changed by another program while
   a change made here was not yet saved; kept the other program's version of
   the source 1a2b3c4d (label, url)`, or `... kept the other program's
   version of activeKey`: field NAMES and a source's short key, never a URL
   or a value [round 15, D-SRC-36: `version of` added in the model and here;
   the line read `kept the other program's the source ...` until then].
   Nothing on screen says a conflict happened; the guide simply shows the
   merged state. (A conflict lost while the in-app save was in flight or
   parked, not failed, is told by that journal line alone, D-SRC-33; and a
   merge can leave the active source naming one the other program removed or
   re-keyed, with no line, after which the guide falls back as it does at a
   start, D-SRC-37. Both are filed and not this round's.)
   [Round 15, R25b (D-SRC-31): **unless together they pass a limit.** Both
   sides' additions are kept up to 50 sources, 20 saved searches and 200
   hidden groups; past a limit the other program's version keeps its place
   and the in-app additions past it are dropped, and the user is TOLD, once
   per merge, by a notification (`omarchy-notification-send --app-name IPTV
   -u normal -g <alert glyph> -r 74018 <title> <body>`, `Model.mergeDropNotice`):
   `Not every change was kept` / `Another program changed state.json while a
   change made here was not yet saved, and together they went past a limit.
   The other program's version was kept, and 1 source added here (the limit
   is 50 sources) was not kept. Make room, then add it again.` -- counts and
   limits, joined with `and` for more than one kind, never a URL, a label, a
   query or a group name; and the journal gets one line per dropped element,
   `... the source <key> added here was not kept (the limit is 50 sources)`,
   `... a saved search made here was not kept (the limit is 20 saved
   searches)`, `... a group hidden here was not kept (the limit is 200 hidden
   groups)` (`Model.mergeDropLines`). Until round 15 the merge cut them at the
   cap silently. Pinned in node (`R25b: ...`, both hosts and echo modes); not
   driven live. One reachable case is outside the merge and still silent: an
   in-app ADD whose probe is running when a hand-run `state source add` takes
   the 50th place -- the foreign write is applied (nothing is held yet), the
   probe's commit then makes 51 in memory and in the file, and the next
   start keeps 50 and drops the in-app source (lane-key-k1's finding, raised
   to the lead; the README states it).]
   [Round 15, R25a (D-SRC-30): **a backup put back wins, even a copy of the
   plugin's own file.** A reload is the service's own echo only while its
   text is still in flight (the burst since the last save that landed); a
   copy of an earlier own save, put back after a later in-app change landed,
   is another program's write -- applied whole when nothing is held, merged
   when something is -- where until round 15 it was ignored as `own-write`
   and the next save wrote over it (the round-14 data-loss lens's FAV, BAK,
   DEL, RSTB, FAV). Observed by key-scenario B20 (`restored:2 records:2
   label:after-restore restart:2`; on dev `restored:1 records:1 ...
   restart:1`). One case where a restore has no effect, stated in the
   README: a copy equal to what the file ALREADY holds, because the in-app
   change after it was not saved yet (its save failed, parked or in
   flight), is indistinguishable from nothing happening -- it is ignored for
   the held reason, and the held change is saved over it. The disk never
   moved, so nothing the user wrote is lost, but the restore does nothing.
   One measured exception (the round-15 data-loss lens, D-SRC-39): in a
   burst of saves whose first lands and a later one fails, within one
   event-loop turn, the base stays at the file before the burst while the
   disk holds the first save, so a copy of that earlier file put back is
   ignored and written over. The README's same-instant limit does not cover
   it: only the burst is sub-millisecond, and the restore is ignored
   whenever it comes, for as long as the failed save is held. The README's
   restore exception is stated to include it (the plugin's last save
   failed and the backup matches the file as the plugin last knew it).]

9. NOT this mode either (round 16, R26a; round 18, R28a; round 19, R29a,
   2026-10-20): **a read before a save that does not answer.** Every save
   reads `state.json` first (round 16, R26a). When that read has no load
   within 2 s (`stateVerifyWatchdog`, `interval: 2000`), the save goes
   ahead WITHOUT it, as it did before R26: it is counted
   (`stateVerifyNoLoad`) and logged once, `omarchy-iptv: state.json was not
   read back within <ms> ms of a save; saving without the read`, and nothing
   is refused and nothing is told -- the guide draws nothing for it, the
   Sources header keeps its count, the Add rows stay, and `a` and `c` open
   the form. A save asked while our previous write is still out waits for
   that write first (R27a window a, kept), at most 2 s
   (`stateWriteWaitWatchdog`), and then reads under the same 2 s bound, so
   a save is never held longer than 4 s and never blocked. This is
   D-SINK-22's window c, OPEN by the lead's ruling and the same as on
   0.14.2: a write without its read lands over whatever the file holds, so
   another program's change made while the read was stalled can be lost,
   and a re-pointed link or an empty linked folder can get a `state.json`
   created at the umask's mode (`ARCHITECTURE.md` section 5). Measured live
   on lane-sweep-a3 with round 2's slow-file rig (a FUSE passthrough that
   stalls only quickshell's read of `state.json`; transcript
   `key-20261020-184229-2540898`): an edit and a second asked while the
   first's write was out were written at +2.0 s and +4.0 s without their
   reads, no 74019 and no 74017, both kept across a restart; a hand-run
   helper `state source add` during the stall was kept beside an in-app
   add; and an atomic replace adding a favourite during the stall was lost
   beside a label edit -- each exactly as on 6f1d176. Pinned in node
   through the shipping `Service.qml` on both hosts and both own-echo modes
   (`R26a / R29a (<tag>): the read is BOUNDED ...`, `... the read's bound
   is 2 s, from the Timer the tree declares ...`, `R27a / R29a (<tag>): the
   write wait is BOUNDED at 2 s ...`), each red on lane-sweep-c2, where the
   save stayed parked (`noLoad:2`).
   [History, withdrawn by R29a (2026-10-20). Round 17's R27a put the
   session in this mode (`read-timeout`, item 1's withdrawn row) after a
   second silent read, and the load that lifted it dropped the held change
   (round 1's two reviews). Round 18's R28a instead held the save past the
   bound, re-reading at 2, 4, 8, 16, 32 and 62 s and then every 30 s, and
   told the user once at 8 s on its own id, 74019 (`Saving is waiting`,
   whose body promised the change "saved when the file answers"). Round 2's
   reviews measured two new losses on it: a stalled read that finally
   answered with a load failure turned the held change into an R22 change,
   dropped on three of the four ways back; and, live with a slow FUSE file,
   a read that had been stalled for seconds returned the file as it was
   when the read was ASKED, so the save then wrote over another program's
   write made during the stall (4 of 4 runs; 6f1d176 kept it in the same
   shapes, 2 of 2). Each attempt to hold a change across a read that does
   not answer made a new silent loss, so the lead withdrew both: no
   schedule, no 74019 (retired, not reused), no notice, no
   `read-timeout`.]

Pinned in node (`R22a: stateUnreadableNotice -- one sentence per reason,
each naming the file and what to do (restart included), none carrying a URL;
the notification and the console line are that sentence (74017)`, `R23c:
stateUnreadableNotice("init-timeout") is its own sentence ...`, `R23e:
guideSurface ...`, `R23e: firstRunAllowed ...`, `R23e: the Esc / o return
from Sources ...`, `R23f: refusalMessage ...`, and the `R22a`, `R23a` and
`R23c` harness pins that drive each fault through the real handlers; since
round 14 `R24a mergeForeignState: <case>` over the 34 cases of
`tests/fixtures/state-merge.json` and the `R24a (...)` harness pins in 16
modes, `R24b: the link sentence names the file and the link, the not-a-dir
sentence names the FOLDER's path, ...`, `R24f: sourcesHeaderRight ...`,
`R24f: sourcesRowCount / sourcesRowKind ...`, `R24f: sourcesAddAllowed ...`,
`R24f: footerHints in Sources ...`) and observed at the sink by
key-scenario: B5-B7 on lane-key-n1 (lane A,
transcript `key-20261013-161816-835970`: B5 `file:same blocked:unparsed
add:state_unreadable switch:state_unreadable told:1 path:1 urls:0` -- one
notification, naming `state.json`, no `://` -- B6 the entry's keys and mirror
unchanged with `writes:0`, B7 the mode lifted by restoring the file and a
switch then landing), and B9-B14 on lane-key-p1 (lane A, transcript
`key-20261014-043943-514380`, 112 / 0; B10-B14 red on `--baseline
lane-key-n2`, `key-20261014-044420-538071`, 107 / 5), and B15-B18 on
lane-key-q1 (lane A, `key-20261014-095236-969838`, 116 / 0; B15, B16 and
B18 red on `--baseline dev`, `key-20261014-095838-996891`, 113 / 3; B17 red
with the KILL deleted, `key-20261014-100528-1027361`, 115 / 1), and B19-B22 on
lane-key-k1 (lane A, `key-20261014-153026-1723779`, 120 / 0; B20 and B22
red on `--baseline dev`, `key-20261014-144201-1513141`, 118 / 2; B19 red
with `r25d-a5-base-not-moved.patch`, 119 / 1; B21 red with
`r25d-no-reload-on-change.patch`, 110 / 10). Round 15's node pins: `R25a
(...)`, `R25b: ...` and `R25b (...)`, `R25c: ...` and `R25c (...)`, `R25d
(...)`, `D-SRC-38: sourcesHeaderRight / stateBlockedHeader ...`. B11 reads the surface's
title and prose as the notice's (`title:notice prose:notice`) through the
harness's drawn-copy fields, which since R23h report what is DRAWN. The
rendered surface and the notification card are UNVERIFIED on a display: no
screenshot of either was taken this round, nor of the round-14 Sources
screen (3.2.6), nor in round 15 of the `Saving has stopped` header or the
`Not every change was kept` notification.

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
   **Added 2026-10-11 (D-CLIP-1): and the clipboard is read ONLY when the
   user pastes, by a `wl-paste` child of the plugin's HELPER, which bounds
   it in bytes (32 KiB) and time (5 s) and answers the shell with at most
   8,192 characters, never by the shell process and never on a clipboard
   change (R8: the shell holds the reply, not the clipboard).** An editable `TextInput` would
   make the shell read the whole offer on every change by any application,
   so no form field is editable to Qt.
7. `Accessible.description` of a URL field is the masked rendering even while
   revealed. **That sentence used to end "a screen reader never gets the
   query", which was false and is corrected here.** The description is masked;
   the accessible VALUE is not, because Qt derives it from the control's own
   display text. So a revealed URL publishes its credentials in full, and the
   Xtream server and username, which have no mask and no eye button, publish
   theirs always. Filed as D-A11Y-1 and unfixed: see ruling AX2 for why the
   obvious remedy was refused.
   The password field previously set `Accessible.passwordEdit: true`. On
   Qt 6.11.2 that property is **inert in both directions**, measured twice by
   different toolchains, so it promised protection it never gave and left the
   field with no label at all. It is removed; the password now carries its
   label explicitly. Nothing published here reaches the accessibility bus
   today at all, because no Quickshell window publishes a tree (D-GS-3).
8. Console: the guide logs mode changes at most, never field values (shipped
   rule R12 extended to the new input surface).
9. `Space` / `Enter` on a source, `x` remove, and the CLI path all go through
   the same service actions; there is no UI-only copy of a URL anywhere in
   `Guide.qml` beyond the form state, which is dropped on close.

---

## 7. Accessibility

**The delivery statement, plainly.** On this desktop today, **nothing this
section declares reaches assistive technology** -- no role, no name, no state,
for any user of the shipping plugin. No window Quickshell creates publishes an
accessibility tree at all (D-GS-3, cause settled, filed upstream as quickshell
issue 1144, `docs/ACCESSIBILITY-INVESTIGATION.md` section 6). Two claims live
here and must not be blurred: *our markup is correct*, which is testable and is
now partly tested at the real sink by the accessibility harness (`tests/a11y/`)
running the guide's content in a plain hidden Qt window where the bridge works;
and *a user can hear it*, which is false for every row and untestable until
1144 lands. An OBSERVED marker below means the first, never the second.

### 7.1 Roles and names

Markers per CLAUDE.md rule 14, defined in `docs/UX.md` 7.1 and used the same
way here: **OBSERVED** (a landed harness scenario walks the tree and asserts
this node), **OBSERVED-ONCE** (seen becoming a node by the prototype run that
established the approach, not carried into a landed scenario -- evidence with
no standing assertion behind it, so it decays), **COMPOSED** (only the string
builder is asserted from node; proves the text, never that the text becomes a
node), **UNVERIFIED** (nothing observes it at all). Scenario names are the
harness's own: `bar`, `firstrun`, `banner`, `query`, `scale`, `xtream`.

| Surface | `Accessible.role` | `Accessible.name` / notes | Verified |
|---|---|---|---|
| Header title (sources, forms) | `Accessible.Heading` | the title; the search line's `EditableText` role applies only in search / list | **UNVERIFIED.** No scenario asserts the heading node |
| Pinned Sources row | `Accessible.Button` | `Sources, 3 saved` | **OBSERVED-ONCE** (prototype, as `Sources, 1 saved`); text also **COMPOSED** (`Model.sourcesRowAccessibleName`, SRC-A11Y-06 neighbours) |
| Sources list | `Accessible.List` | `Sources` | **OBSERVED-ONCE** (prototype) |
| Source row | `Accessible.ListItem` | `<label>, <host>, <n> channels in <m> groups` + `, active` + `, EPG` + `, last used <x>` / `, never used` / `, not loaded yet`; `Accessible.focused` = hasCursor; `Accessible.selected` = active | **COMPOSED only** (`Model.sourceAccessibleName`, SRC-A11Y-06). The prototype asserted the rows around it and never this one, so the richest name the Sources screen composes has never been seen becoming a node. `focused` and `selected` are **UNVERIFIED** |
| Action rows | `Accessible.ListItem` | `Add source`, `Add Xtream login` | **OBSERVED-ONCE** (prototype, both rows) |
| Action buttons | `Accessible.Button` | `Edit <label>`, `Remove <label>` | **OBSERVED-ONCE** (prototype, `Edit Provider` / `Remove Provider`) |
| Form column | `Accessible.Dialog` | `Add source` / `Edit source` / `Add Xtream login` / `Set up a playlist` (first run) | **OBSERVED** for `Set up a playlist` (firstrun) and `Add Xtream login` (xtream); **OBSERVED-ONCE** for `Add source` (prototype); **UNVERIFIED** for `Edit source`, which no scenario opens |
| Label field | `Accessible.EditableText` | `Label, optional` | **OBSERVED-ONCE** (prototype) |
| Playlist field | `Accessible.EditableText` | `Playlist URL or path`; `Accessible.description` = masked rendering (always) | Name **OBSERVED** (firstrun asserts the field and that it starts empty). The `description` = masked-rendering-always claim is **UNVERIFIED**: the only run that touched it asked whether a secret was *absent*, which passes whether the description is masked, empty, or the field has been silently emptied. Asserting the revealed case at all is blocked on PLAN-NEXT decision 8 |
| EPG field | `Accessible.EditableText` | `EPG URL, optional`; description masked | **UNVERIFIED.** No scenario names this field |
| Server field | `Accessible.EditableText` | `Server URL` | **OBSERVED** (xtream), name and **value**: this is one of the two fields that publish a credential with no user action and no affordance to stop it (D-A11Y-1, PLAN-NEXT decision 7) |
| Username field | `Accessible.EditableText` | `Username` | **OBSERVED** (xtream), name and **value**: the other unconsented sink |
| Password field | `Accessible.EditableText` | `Password`, set through `Accessible.description`. **Not** `passwordEdit`: inert on Qt 6.11.2, see 6.7 item 7 | **OBSERVED** (xtream): the label arrives through `Accessible.description`, which is what replaced the deleted `passwordEdit` |
| Eye button | `Accessible.Button` | `Show query` / `Hide query`; `Accessible.checked` = revealed | **UNVERIFIED.** No scenario asserts the eye button or its `checked` state, so the one control that tells a screen-reader user whether the field beside it is masked is ungraded |
| Link rows | `Accessible.Button` | `Use Xtream login instead`, `Saved sources, 3` | **UNVERIFIED** |
| Buttons | `Accessible.Button` | `Load`, `Save`, `Cancel` | `Load` **OBSERVED** (firstrun); `Save` / `Cancel` **OBSERVED-ONCE** (prototype) |
| Result / error line | `Accessible.AlertMessage` | the line's text | **UNVERIFIED.** The guide's banner `AlertMessage` is observed; this is a different node and no scenario reaches it |
| Confirm dialog | `Accessible.Dialog` | the message; its buttons `Accessible.Button` `Cancel` / `Remove` | **UNVERIFIED**, dialog and both buttons |
| Footer status | `Accessible.StaticText` | shipped | **OBSERVED** (banner scenario); text **COMPOSED** (`Model.footerStatus`) |

Since 2026-10-11 (D-CLIP-1) every form field above is `readOnly: true` to Qt
while keeping `Accessible.EditableText`. What the bridge publishes for a
read-only editable -- the `readOnly` state flag, and whether the role
survives -- is **UNVERIFIED**, and moot until D-GS-3 lands.

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

**UNVERIFIED**, all of it. Hit targets are geometry, and the accessibility
harness reads an AT-SPI tree, not a layout: it can say a node exists and what
it is called, and it cannot say the node is 38 pixels tall. SRC-A11Y-04's
`grep` is not retired here because it is not the same failure -- a token name
in the source is weak evidence about geometry, but it is evidence about
something the source actually decides, where a grep for `Accessible.` was
evidence about nothing. Verifying it properly needs a rendered measurement
(the class of evidence `docs/QA-RESULTS.md` C6 takes off screenshots), which
nothing schedules today.

### 7.5 What is not delivered, and by whom

Neither this section nor `docs/UX.md` 7 is delivered to any user, and the
reason is not in either document. Ownership, so it is not re-litigated:
D-GS-3 is upstream (quickshell 1144) and this project's part of it is to keep
its own markup correct and observable, which 7.1's markers now account for.
D-A11Y-1 is ours and open: the Xtream server and username publish provider
credentials as their accessible Value with no user action, which
PLAN-NEXT decision 7 recommends ruling as the defect, and 6.7 item 7 records.
What a *deliberately revealed* field may publish is PLAN-NEXT decision 8 and
is unanswered; until it is answered, no document here states a rule about it
and no test asserts one, because a test written first would settle the ruling
by accident.

---

## 8. Open questions, decided here

| # | Question | Decision |
|---|---|---|
| 1 | Entry key from list mode | `o` (`o sources`). Free in UX.md 3.1, not a PanelKeyCatcher key, no M2 claim on it (`p` is left free for a possible picture-in-picture binding). `o` inside Sources goes back. |
| 2 | Xtream entry key | `c` (credentials) in Sources; `Add Xtream login` row for the mouse; a link row inside the URL forms so first run reaches it without a printable key. |
| 3 | `r` rename? | No. `e` opens the form with `Label` focused; rename is `e`, type, `Enter`. `r` stays refresh in the guide and is ignored in Sources. |
| 4 | Masking scope | Userinfo, all query values, fragment -> `****`. Path stays visible (some providers put credentials in the path; the user must still be able to edit it; the PO rule names the query string). Fixed length, never per-character. |
| 5 | How does one edit a masked value? | Masked = fully selected: typing, paste, Backspace, Ctrl+U replace it; `Ctrl+R` / eye reveals for caret editing; re-masked on blur, save, cancel, paste. **[Amended 2026-10-11, D-CLIP-1: the behaviour stands; the hand is the plugin's, since the field is read-only to Qt in both states. The "fully selected" range is `Model.editRangeFor`'s, reached from node: at lane commit 44b250b it was decided in `Guide.qml` at two sites and no check in the gate could see it go wrong (rule 12), which the review found by deleting the branch under a green gate.]** |
| 6 | Reveal: hold or toggle? | Toggle, scoped to the focused field, reset on blur. A hold gesture cannot be typed into. |
| 7 | Esc in forms | One press cancels in forms opened from Sources (network precedent; `Ctrl+U` clears). First run keeps the search-line "clear first, then close" rule and never closes while any field has text. |
| 8 | Paste semantics | Plain / revealed fields: insert at caret (Qt default, as the uptime monitor). Masked fields: replace. Always sanitized in `onTextChanged`. **[Overturned 2026-10-11, D-CLIP-1: not Qt's paste and not `onTextChanged`. `Ctrl+V` / `Shift+Insert` ask the service for a `wl-paste` read, capped and bounded, and the plugin inserts the sanitized text over the selection (plain / revealed) or over the whole value (masked, then re-masked). Middle click is gone with the native path.]** |
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
