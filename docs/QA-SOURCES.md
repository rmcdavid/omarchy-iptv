# Omarchy IPTV - QA test plan for Sources (M2-01)

Owner: QA. Status: v0.3 (2026-09-13), executed against `7e13053` (results in
`docs/QA-RESULTS.md`, section "M2-01 Sources pass on 7e13053") and re-executed
against `d50e364` after the fix round (section "M2-01 regression on d50e364";
v0.3 corrects SRC-SW-06, SRC-CLI-01 and SRC-XT-02, marked `[v0.3]`). v0.1 was
written while Lane 1 (Model.js + Guide.qml) and Lane 2 (Service.qml + helper +
harness) built M2-01 in parallel; v0.2 folds in the round-2 rulings SR11-SR32
of `docs/ARCHITECTURE-SOURCES.md` (they answer every `SRC-DEC` row of section
10) and the expectation corrections found during the pass (marked `[v0.2]`). Extends `docs/QA.md` (v0.2: ids, methods,
harness techniques, severities); everything there still applies to the shipped
guide and is re-run as the regression subset (section 9.6).

Documents of record this plan verifies against: `docs/M2-SOURCES.md` (locked
decisions 1-7, stories S1-S8), `docs/ARCHITECTURE-SOURCES.md` (ARCH: decisions
D1-D16, sections 2-7, harness scenarios H1-H12 in 8.4, live steps in 8.5, rulings
SR1-SR10 at the end), `docs/UX-SOURCES.md` (UX: flows 1.2-1.9, keys 2.1-2.5,
wireframes 3.1-3.7, visuals 4.x, microcopy 5.1-5.7, privacy rules 6.1-6.9,
accessibility 7.1-7.4, decisions 8.1-8.30), `docs/SECURITY-REVIEW.md` (the bar
for the new input surface), `docs/PLAN.md` (gates G0-G5, severities). Where UX
and ARCH disagree and SR1-SR10 do not settle it, the case cites a `SRC-DEC-nn`
row of section 10, which the lead decides before the pass.

This file is ASCII. As in QA.md, `...`, `"x"` and ` - ` in quoted microcopy
stand for U+2026, U+201C/U+201D and U+00B7 on screen; glyphs are written as
codepoints (U+F0411 etc., UX 4.6). Caps follow SR5: URL 2048, label 64, server
512, username and password 256, 50 sources. Where UX-SOURCES.md 5.4 still
quotes 40 or 128, the implementation and the copy must say 64 / 256.

Machine of record: unchanged from QA.md (Omarchy 4.0.3, Quickshell 0.3.1,
Hyprland 0.56.2, mpv 0.41.0, Python 3.14.7, node 26.8.1, one 1366x768 output,
theme retropc). Verified 2026-09-13 for this plan: v0.1.0 is installed and live
at `~/.config/omarchy/plugins/io.github.rmcdavid.iptv` (a git clone whose
`origin` is the local repository, not GitHub); its `shell.json` entry carries
only `id` and `playlistUrl` (iptv-org `us.m3u`); `state.json` is version 1 with
0 favorites and 5 recents; the cache is the legacy top-level layout
(`channels.json`, `playlist-status.json`, 0600 in a 0700 dir). Tools present:
node, python3, jq, wl-copy, wl-paste, wtype, grim, curl.

## 0. How to read and execute this plan

- Test case ids are `SRC-<AREA>-<nn>`. Areas: FR (first run, S1), LST (sources
  list, S2), SW (switch, S3), LBL (labels, S4), CLI (parity, S5), XT (Xtream,
  S6), RM (remove, S7), ERR (errors, S8), KEY (keyboard and mouse), UI
  (wireframe states, microcopy, tokens), A11Y, PRIV (UX 6 privacy rules), SEC
  (security of the input surface), MIG (migration), PERF, MODEL (Model.js
  automated), HELP (helper automated), SVC (service contract).
- "How" column: `A` = automated (exact command and file), `H` = harness
  scenario `SRC-Hnn` of section 8 (exact commands there; QA runs them), `L` =
  live shell (section 9). A case may list several. `A*` = an automated test the
  lanes are expected to add per ARCH 8.3; until it lands QA runs the command by
  hand.
- Results are recorded in `docs/QA-RESULTS.md` (a new "Sources pass" section
  in the format of the M1 passes) as `pass` / `fail D-SRC-<n>` / `blocked:
  needs harness verb <x>` / `blocked: needs live shell` / `not run <reason>`.
- A case fails if any expected string, glyph, count, file mode, code, path or
  timing is off. Microcopy is compared verbatim against UX-SOURCES.md 5.
- Severities (PLAN.md 6): P1 blocks a story (cannot add/switch/remove a source,
  credentials leak to a third party or a world-readable file), P2 degrades one
  (wrong key, URL rendered on screen or in a sink, wrong cache swapped, a
  failed add displaces the working source), P3 cosmetic or hardening. Release
  of v0.2.0 needs zero open P1/P2.
- Fixtures: `tests/fixtures/qa-sources/` (section 7). Nothing in this plan
  touches `~/.config`, `/usr/share/omarchy`, `~/.cache/omarchy-iptv` or
  `~/.local/state/omarchy-iptv` except the live-shell runbook (section 9),
  which the lead runs on purpose. The harness scenarios live entirely under
  `$OMARCHY_IPTV_HARNESS_DIR`, and `scripts/qa-sources-scenarios.sh` refuses to
  run when that directory resolves into any of the real plugin locations.

## 1. Traceability matrix

### 1.1 Test cases

#### First run (S1; UX 1.2, 3.1.x)

| ID | Verifies | How | Expected |
|---|---|---|---|
| SRC-FR-01 | unconfigured guide opens straight into `sourceEdit[firstRun]` | H SRC-H02 | empty-state glyph U+F0502 and title `No playlist configured` kept; prose `Paste or type your M3U URL or path, then press Enter`; `Playlist` field focused with a visible caret, `EPG` field, link row `Use Xtream login instead`, `Load` button, caption `Or from a terminal:  omarchy bar set io.github.rmcdavid.iptv playlistUrl <url>` (click copies, footer `Copied`); footer `Enter load - Tab next field - Ctrl+V paste - Esc close`; header keeps the dimmed `Search channels...`; the key catcher is blocked: typing `o`, `r`, `f`, `x`, `s` inserts text and nothing else happens (D-LIVE-09 `Set a playlist first` never shows here) |
| SRC-FR-02 | type a served URL, Enter (probe then commit) | H SRC-H02 | form freezes (fields, link row, button disabled), result line U+F01D8 `Fetching from 127.0.0.1...`, footer `Esc cancel`; then the guide is in search mode with `8 channels` (`qa-src-a.m3u`), footer transient `8 channels in 3 groups` for `transientMs`, pinned Sources row shows `1`; `updateEntryInline` logged once with keys `id,playlistUrl,epgUrl,...` and the harness `barConfig` entry carries the URL (fake must APPLY it, section 8.0) |
| SRC-FR-03 | type an absolute path, Enter | H SRC-H02 | result line `Reading the file...`; success as FR-02; the record's `kind` is `file`, host `local file`, label = file name |
| SRC-FR-04 | Tab / Down to EPG; Enter in EPG or on `Load` submits | H SRC-H02 | focus order `Playlist` -> `EPG` -> (`Saved sources (n)` when present) -> `Use Xtream login instead` -> `Load` -> wrap; Enter in either field submits; Enter on the focused `Load` submits |
| SRC-FR-05 | probe failure keeps the setup state (S8) | H SRC-H05 | form thaws, result line U+F0026 `Connection refused from 127.0.0.1` (never the URL), focus back on `Playlist`, values kept; no `updateEntryInline` call, `barConfig` unchanged, `configured` stays false; no record is saved and no `sources/<key>` directory remains (SR23 `[v0.2]`) |
| SRC-FR-06 | Esc rules on first run (UX 2.3) | H SRC-H02 | focused field with text -> cleared, footer `Esc clear`; focused empty and the other field has text -> focus moves there; every field empty -> the guide closes (`Esc close`); the overlay never closes while any field has text |
| SRC-FR-07 | Esc while fetching cancels the probe | H SRC-H14 | `cancelProbe()`: helper process gone within 1 s, form thaws with the typed values, no result line; `sources/<key>/` for the cancelled add is absent or empty and no `.tmp-*` file exists anywhere under the scratch cache (SRC-SEC-11) |
| SRC-FR-08 | `Saved sources (n)` link (3.1.6) | H SRC-H07 | shown only when sources exist and none is active; Tab-reachable before the Xtream link; Enter/click opens Sources with `returnMode = sourceEdit`; Esc in Sources returns to the form with its values |
| SRC-FR-09 | `Use Xtream login instead` from first run | H SRC-H10 | opens `sourceXtream[firstRun]`; Esc there (fields empty) returns to the first-run form with its values intact; a successful Xtream probe lands in search mode |
| SRC-FR-10 | EPG URL on first run loads in the background | H SRC-H02 (`qa-src-a.xml` served) | after the commit the EPG helper runs into `sources/<key>/` (epg-* files there, none at the top level); rows for `qa.a.news1`/`qa.a.news2` show `Now: Alpha Evergreen`; a bad EPG URL gives the shipped banner, never a blocked guide |
| SRC-FR-11 | CLI sets an invalid `playlistUrl` (D16, SR8) | H SRC-H09 | `ipc set playlistUrl ftp://x` -> empty error state with the UX 5.4 `scheme` reason and no host, `settingsInvalid` set, no helper process, no history record; `ipc set playlistUrl ''` -> first-run form, history untouched (no eviction, D-LIVE-19 regression: no rows drawn under the form) |
| SRC-FR-12 | paste into the first-run field (D9) | H SRC-H04 | `Ctrl+V` and `Shift+Insert` both insert the clipboard; a pasted URL with a query or userinfo is masked at once with the eye glyph U+F0208; typed text is never masked while typing; if both chords paste nothing, Lane 1 flips `pasteViaProcess` and the run is repeated |

#### Sources list (S2; UX 1.3, 2.2, 3.2.x, 3.7, 4.1, 4.5)

| ID | Verifies | How | Expected |
|---|---|---|---|
| SRC-LST-01 | entry from the guide | H SRC-H06 | list mode `o`/`O` (search mode: `Tab` then `o`); header `Sources` left in `Style.font.heading`, `3 sources` right; column and channel list replaced by the sources list; cursor on the active row (row 0 when none active; `Add source` row when empty); `returnMode` remembers `search`/`list` |
| SRC-LST-02 | pinned `Sources` row under the group column (UX 3.7, 4.5) | H SRC-H06; L 9.4 (click) | separator (`Style.normalBorderWidth`, `Util.alpha(Color.menu.border, 0.28)`), glyph U+F0411 in `Style.font.iconSmall`, text `Sources`, count = saved sources at opacity 0.45; never scrolls with the group list; `h`/`l` never land on it; wheel over the column never reaches it; hover paints the hover fill with a pointing cursor; hidden with the column on narrow cards while `o` keeps working |
| SRC-LST-03 | source rows (UX 3.2.5, 5.2) | H SRC-H06 | two-line rows: lead check U+F012C + `Font.Bold` label + detail starting with `active` only on the active source; right meta `used 21:30` (today) / `used yesterday` / `used 3 Sep` (this year) / `used 3 Sep 2025` / `never used`; detail segments joined with ` - `: `<host>` (`local file` for paths), `Xtream` (kind xtream only), `8 channels in 3 groups` / `1 channel in 1 group` / `not loaded yet`, `EPG` only when an EPG URL is set (`qa-src-b` has none) |
| SRC-LST-04 | action rows | H SRC-H06 | separator then `Add source` (U+F0415) and `Add Xtream login` (U+F0306) at opacity 0.7, single-row height, they scroll with the list; cursor treatment identical to source rows; footer on them `j/k move - Enter open - Esc back` |
| SRC-LST-05 | action buttons on the cursor row | L 9.4 (mouse); H (screenshot) | pencil U+F03EB and close-circle U+F0159 only on the cursor row, right meta shifts left, remove button hover `Color.urgent`; tooltips `Edit` / `Remove`; hovering a button does not move the cursor |
| SRC-LST-06 | return to the guide | H SRC-H06 | Esc or `o` -> `returnMode`; cursor, scope and query exactly as before; nothing reloads |
| SRC-LST-07 | header counts and empty list (3.2.2, 3.2.3) | H SRC-H06, SRC-H07 | `1 source`, `3 sources`, `No sources`; with an empty list the cursor is on `Add source` and the footer reads `j/k move - Enter open - Esc back` |
| SRC-LST-08 | row order | H SRC-H06 | active first, then `lastUsedAt` descending, then never-used sources in the order added (SR32 `[v0.2]`); a Space switch re-sorts the list at once (the new active row moves to the top, the cursor follows) |
| SRC-LST-09 | narrow card (3.2.4) | L 9.5 (optional, `hyprctl keyword monitor`) | right meta hidden; `used ...` / `never used` moves into the detail right after `active`; action buttons stay; footer hints elide left |
| SRC-LST-10 | ignored keys in `sources` | H SRC-H06 | `h`, `l`, Left, Right, Tab, `/`, `r`, `s`, `f`, digits do nothing: no refresh (no helper process), no stop (mpv untouched), no favorite change, no search |
| SRC-LST-11 | rows carry no URL (SR1, PRIV 6.1) | H SRC-H13; A | `sources()` JSON has keys `id,label,kind,host,hasEpg,channelCount,groupCount,cachedAt,lastUsedAt,active` and no `url`, `epgUrl`, `://`, `?`, `@`; `channelCount` is `-1` when never fetched (SR1) |
| SRC-LST-12 | footer status in `sources` mode and the label prefix | H SRC-H06 | status = the guide's status of the active source; with 2+ sources the guide footer reads `<label> - 8 channels - updated HH:MM` (cached form included); with one source no prefix |

#### Switching (S3; UX 1.4, 3.6; ARCH 4.5)

| ID | Verifies | How | Expected |
|---|---|---|---|
| SRC-SW-01 | Enter on an inactive cached row | H SRC-H06 | `switchSource(id)`: `updateEntryInline` logged once (keys only) and the fake `barConfig` entry now carries that source's `playlistUrl`/`epgUrl` with every other key (`refreshMinutes`, `mpvArgs`, ...) preserved (`entryWith`); `activeCache()` = `.../sources/<key>`; `state()` shows `activeSourceKey` = that key; channels replaced at once (`8` -> `5` for A -> B); guide in search mode with an empty query, scope by `initialScope`, cursor by `cursorFor`; transient `Switched to <label> - 5 channels` |
| SRC-SW-02 | Enter on the active row | H SRC-H06 | returns to the guide, no reload: no helper process, no `updateEntryInline`, `channelsFile` not re-read (same `generatedAt`), `lastUsed` unchanged |
| SRC-SW-03 | Space switches and stays | H SRC-H06 | mode stays `sources`; check glyph, bold label and the word `active` move to the new row at once; transient in the footer; a second Space on the other row switches back |
| SRC-SW-04 | stale cache refreshes in the background | H SRC-H06 (stamps older than `refreshMinutes`) | after the redraw the footer shows `Refreshing...` through `service.refreshing`; success is silent (no notification, timer rules); failure shows the shipped banner `Playlist refresh failed (...) - showing cached copy from HH:MM - r retry` |
| SRC-SW-05 | fresh cache means no helper run (D7, R9 of ARCH) | H SRC-H06 (stamps = now) | no `python3 ... playlist` process during 3 s after the switch; harness console has no `playlist:` line; `refreshTimer.triggeredOnStart` is false: a restart with `--keep` and a fresh cache does not re-download |
| SRC-SW-06 | never-fetched source (added by CLI, or cache deleted) | H SRC-H09 | `[v0.3]` Enter or Space probes first (SR7, D-SRC-04): the footer status slot reads `Fetching from <host>...` (`sourcesProbeText`) while the probe runs; on failure the Sources result line reads `<reason> from <host>` (`sourcesNotice`, SR26), the previous source stays active, no `Switched to ...` transient and no settings write; on success `Switched to <label> - N channels`, Enter leaves Sources and Space stays with the cursor on the re-sorted row. The shipped error state with `r retry - o sources - Esc close` (UX 5.3) is the CLI path (a never-fetched source made active by `omarchy bar set`) |
| SRC-SW-07 | favorites and recents across a switch (SR9, D14) | H SRC-H06 (`state-v1.json` seeds `t:qa.a.news1`, `t:qa.shared`, `u:502142db`) | under A: Favorites lists 3; after the switch to B: Favorites lists only `Shared Channel` (`t:qa.shared`), `Favorites - 1 channel`; `state.json` still holds the three ids (invisible, not deleted); Recent filtered the same way; back to A: 3 again |
| SRC-SW-08 | playback across a switch (ARCH 4.5) | H SRC-H06 with `--serve` | mpv untouched (same pid, `time-pos` advancing), `nowPlaying` kept, bar label kept; `zap 1` yields `no` when the playing group is absent from the new source; Enter on another channel replaces as today |
| SRC-SW-09 | one switch at a time | H SRC-H06 | `switchSource` while `switching` is true -> `busy`; after `sourceSwitched` a second switch works |
| SRC-SW-10 | switch from a sources list opened from list mode | H SRC-H06 | returns to search mode with an empty query (UX 1.4 step 3), not to `returnMode`; Esc without a switch returns to list mode with the old query |

#### Labels and editing (S4; UX 1.5, 1.6, 5.6, 3.3.x)

| ID | Verifies | How | Expected |
|---|---|---|---|
| SRC-LBL-01 | derived label | A `node` over `qa-source-labels.json` `derive` (section 2); H SRC-H02 | host for URLs and Xtream servers (`127.0.0.1` or `127.0.0.1:8765` per SRC-DEC-09; `www.` per SRC-DEC-10), file name for paths, `local file` fallback, never userinfo/path/query, capped at 64 |
| SRC-LBL-02 | derived duplicates | A (same); H SRC-H11 | second source on the same host gets the suffix ` 2`, third ` 3` (SR21 `[v0.2]`); comparison case-insensitive per UX 5.6; fixture records V11/V12 carry this expectation, their `archExpect` is obsolete |
| SRC-LBL-03 | edit form pre-fill (3.3.1) | H SRC-H12 | header `Edit source`; `Label` focused with the caret at the end; `Playlist` masked; `EPG` masked or empty; no Xtream link row; buttons `Cancel` / `Save`; footer `Enter save - Tab next field - Ctrl+V paste - Esc cancel` |
| SRC-LBL-04 | label-only edit commits at once | H SRC-H12 | no probe, no helper process, no `updateEntryInline`; `state.json` record `label` changed and `labelCustom: true`; return to `sources` with the cursor on the row, transient `Saved`; a later CLI `set playlistUrl <same url>` never overwrites the custom label (D3) |
| SRC-LBL-05 | typed duplicate label | H SRC-H11; A `validate` T03/T04 | `A source named "Provider" already exists` (curly quotes), focus on `Label`; keeping a source's own label while editing is fine |
| SRC-LBL-06 | label length cap | A T13/T14; H SRC-H11 | 64 characters accepted, 65 -> `Label too long - max 64 characters`; the cap counts Unicode code points (SR22 `[v0.2]`: 33 emoji = 33 code points are accepted; fixture T17's `label_too_long` expectation is obsolete); the field's `maximumLength` is 64 so a longer paste is cut at the field boundary |
| SRC-LBL-07 | empty label means derive again | A T05/T06; H SRC-H12 | saving an empty or whitespace-only label restores the derived default and `labelCustom: false` |
| SRC-LBL-08 | `Label` placeholder | H SRC-H02, SRC-H10 | `optional` until the `Playlist` / `Server` value parses, then the label 5.6 would derive, live while typing |
| SRC-LBL-09 | adversarial labels render literally | A T07-T12, T15, T17; H SRC-H06 (screenshot) | `-u critical`, `--urgency=critical ${path}`, backticks / `$(id)` / pipes, `<b>` markup, bidi controls: stored as typed (control characters stripped), painted as `Text.PlainText`, never in a notification or an mpv title; the row's host segment stays readable next to an RTL label |

#### CLI parity (S5; ARCH D3, D16, SR8)

| ID | Verifies | How | Expected |
|---|---|---|---|
| SRC-CLI-01 | `omarchy bar set ... playlistUrl <new>` adds a record | H SRC-H09; L 9.3 | `ipc set playlistUrl http://127.0.0.1:8765/qa-src-b.m3u` with Sources open: a row appears without reopening, `origin: "cli"`, label derived, active, first fetch runs (no cache yet) then `5 channels`; no `updateEntryInline` unless the settings still carried the previous source's `epgUrl`: then exactly one write-back `playlist (set) epg (none)` follows and the new record never adopts that EPG (`[v0.3]`, D-SRC-10) |
| SRC-CLI-02 | known URL through the CLI | H SRC-H09 | no new record; `lastUsed` bumped only because the active key changed; a changed `epgUrl` is adopted into the record; custom label untouched |
| SRC-CLI-03 | invalid CLI value | H SRC-H09 | `ftp://x`, `javascript:alert(1)`, `/proc/self/environ`, a 3,000-character string: `settingsInvalid` set, empty error state with the reason and no host, no helper process, no record, `activeCacheDir` empty |
| SRC-CLI-04 | empty CLI value | H SRC-H09 | first-run state; history untouched; no `cache remove`; D-LIVE-19 regression (no rows drawn under the form) |
| SRC-CLI-05 | eviction at the cap | H SRC-H11 | 50 records, CLI sets a 51st unknown URL: the least recently used non-active record is evicted, its directory removed (`cache remove` in the queue), console line names the key only; the active source is never evicted |
| SRC-CLI-06 | IPC `status` gains sources, no new verbs (R9) | H SRC-H13; L 9.3 | `status` JSON has `activeSource {key,label,host}` and `sources[] {key,label,host,active,channelCount,lastUsed}`; `grep -c '://'` = 0; `qs ipc ... show` lists the M1 verbs only |
| SRC-CLI-07 | helper `state` in v2 | A* `tests/test_state.py`; H SRC-H16 | `state show` prints `sources[]` with `host`/`epgHost` and no `url`/`epgUrl` key; `favorite add` on a v1 file writes v2 and keeps a pre-existing `sources` list; `clear-recents` keeps `sources` and `cacheLayout`; `state init` creates v2 |
| SRC-CLI-08 | CLI `epgUrl` change while a source is active | H SRC-H09 | adopted into the record, EPG helper runs within 300 ms into the active source's directory (D-LIVE-02 regression) |

#### Xtream form (S6; UX 1.8, 3.4, 5.4; ARCH 3.4, D10)

| ID | Verifies | How | Expected |
|---|---|---|---|
| SRC-XT-01 | entry and layout | H SRC-H10 | `c`/`C` in Sources, the `Add Xtream login` row, or the link row in the add / first-run forms; header `Add Xtream login`; fields `Label` (placeholder = server host), `Server` (focused, placeholder `http://host:port`), `Username`, `Password` (`password: true`, Qt echo character); prose `Builds the get.php (m3u_plus, ts) and xmltv.php URLs. The password is stored in those URLs and never shown again.`; buttons `Cancel` / `Save`; footer `Enter save - Tab next field - Esc cancel` |
| SRC-XT-02 | URL building vectors | A `node` over `xtream-expect.json` V01-V14 (section 2); H SRC-H10 `xtream(...)` | `playlistUrl`, `epgUrl`, `host` and `key` exactly as the fixture; percent-encoding of ` `, `&`, `=`, `+`, `/`, `?`, `#`, `%`, `@`, `:`, `!*'()` and UTF-8; parameter order fixed; a trailing slash is stripped; any path (`/get.php`, `/player_api.php`, `/c`, `/xtream/`) is `server_path` per UX 5.4 and UX 8 decision 10 (the ARCH 3.4 "stripped once" rule is not implemented; fixture records V03/V04/V06/V07/V08 carry the ARCH expectation and are obsolete `[v0.2]`); a `#fragment` on the server is refused as `server_path` like a path or a query (fixture E05 `code: server_path`, `archCode: bad_server`; `[v0.3]` after D-SRC-08) |
| SRC-XT-03 | validation errors | A E01-E09; H SRC-H10 | one error at a time in form order, focus moves: `Enter the server URL`, `Server must start with http:// or https://` (also for a schemeless server: no auto-prefix, SR16), `Server is just http://host:port - no path`, `Server must not contain a username or password - enter them below` (`server_userinfo`, SR17), `Invalid URL - check the host`, `Enter the username`, `Enter the password`; over-cap fields are refused, never truncated: `Server too long - max 512 characters`, `Username too long - max 256 characters`, `Password too long - max 256 characters` (SR18 `[v0.2]`) |
| SRC-XT-04 | probe through the served routes | H SRC-H10 | `xtream/get.php` and `xtream/xmltv.php` copied into the served directory: `Fetching from 127.0.0.1...` then `4 channels in 2 groups`; the record has `kind: "xtream"` (row detail segment `Xtream`), `hasEpg` true, `origin: "xtream"`; the EPG loads from `xmltv.php` into `sources/6e90a03e/` and rows show `Now: Xtream Evergreen One` |
| SRC-XT-05 | edit after save shows masked URLs, no password field | H SRC-H10 (`editMasked(id)`) | `http://127.0.0.1:8765/get.php?username=****&password=****&type=m3u_plus&output=ts` and `http://127.0.0.1:8765/xmltv.php?username=****&password=****` (SR4: `type` and `output` stay visible); Ctrl+R reveals the raw URL; the form has no Password row |
| SRC-XT-06 | the password reaches no sink | H SRC-H13 | needles `pa ss`, `pa%20ss`, `username=user`, `password=`: 0 hits in `sources()`, `state()`, the harness console, `notifications.log`, IPC `status`, `state show`, the widget JSON, screenshots; the only argv that carries the built URL is the helper `playlist --url` probe for its own lifetime (documented, as M1's first mpv launch) |
| SRC-XT-07 | password lifetime in the form | H SRC-H10 | after `Save` the password field is empty when the form is reopened; `state()` (which dumps the guide's form state) never contains it; cancelling with Esc discards it |
| SRC-XT-08 | Xtream from first run | H SRC-H10 | success lands in search mode with the transient `4 channels in 2 groups`; Esc with empty fields returns to the first-run form |
| SRC-XT-09 | duplicate Xtream login | H SRC-H11 | the same server/user/pass a second time -> `Already in Sources as "<label>"` (same key `6e90a03e`); `http://127.0.0.1:8765/` with the trailing slash is the same login |
| SRC-XT-10 | Xtream probe failure | H SRC-H05 | server `http://127.0.0.1:9`: `Connection refused from 127.0.0.1`, form thaws with server and username kept (password per UX 1.8: dropped once the URLs were built; the user retypes it), nothing saved |

#### Removal (S7; UX 1.7, 2.4, 3.5, 5.7)

| ID | Verifies | How | Expected |
|---|---|---|---|
| SRC-RM-01 | confirm dialog | H SRC-H07; L 9.4 (scrim, buttons) | `x`, `X`, Delete or the close-circle button -> `Ui.ConfirmDialog` with `Remove "NAS Tvheadend"? Its cache is deleted too.` (curly quotes), buttons `Cancel` / `Remove`, `Remove` preselected with the urgent border; footer `Left/Right choose - Enter confirm - Esc cancel`; Left/Right/Tab/Shift+Tab toggle, Enter activates, Esc cancels; the dialog's own scrim cancels only the dialog |
| SRC-RM-02 | remove a non-active source | H SRC-H07 | record gone from `state.json`; `sources/<key>/` gone (its five files, nothing else touched); other directories intact (`ls sources/` before/after differs by exactly that key); cursor stays at the same index, clamped; transient `Removed <label>` |
| SRC-RM-03 | remove the active source with others left | H SRC-H07 | message `Remove "Provider"? It is the active source; the guide returns to setup.`; `updateEntryInline` logged with `playlist (none) epg (none)`; `barConfig` entry has empty `playlistUrl`/`epgUrl`, other keys kept; transient `Removed Provider - no active source`; Sources stays open; behind it the guide is first-run with `Saved sources (n)`; playback, if any, continues |
| SRC-RM-04 | remove the last source | H SRC-H07 | Sources closes, the first-run form shows with focus in `Playlist`, header count would be `No sources`; pinned row count 0 |
| SRC-RM-05 | cancel paths | H SRC-H07 | `Cancel`, Esc, dialog scrim: back to `sources`, cursor unchanged, key focus restored (`j` moves the cursor right away, `Qt.callLater(keyCatcher.forceActiveFocus)`) |
| SRC-RM-06 | remove while that source is probing | H SRC-H14 | `removeSource` -> `busy`; no dialog or the dialog's confirm is refused with the same code (record how the guide reports it) |
| SRC-RM-07 | helper `cache remove` semantics | A* `tests/test_helper.py`; H SRC-H15 | deletes exactly `channels.json`, `playlist-status.json`, `epg-now.json`, `epg-status.json`, `epg-window.txt` and `.tmp-*`, then `rmdir`; an unknown file (`foo.bin`) is kept and reported under `kept`, the directory left in place; a missing directory -> `ok: true, removed: []`; exactly one JSON line on stdout |
| SRC-RM-08 | `x` on action rows | H SRC-H07 | no-op, no dialog |
| SRC-RM-09 | remove the source that is playing | H SRC-H07 with `--serve` | playback continues (mpv untouched), bar label kept, the guide behind is first-run; documented, no notification |

#### Errors (S8; UX 1.2 steps 4-8, 5.4, 5.5; ARCH D8, 4.3, 4.6)

| ID | Verifies | How | Expected |
|---|---|---|---|
| SRC-ERR-01 | synchronous validation strings (UX 5.4) | H SRC-H03; A section 2 vectors | per code, verbatim, on the result line, with focus on the offending field and its `accent` urgent until the next edit: `empty` `Enter a playlist URL or path`; `scheme` `Start with http://, https://, or / for a local file`; `invalid` `Invalid URL - check the host`; `relative_path` `Use an absolute path (starts with /, not ~)` for `./x`, `~/x` and bare names in the forms (SR11, SR12 `[v0.2]`; `//host/x` and `host/x` are `scheme`); `too_long` `Too long - max 2,048 characters`; `duplicate` `Already in Sources as "Provider"`; `label_too_long` `Label too long - max 64 characters`; `label_taken` `A source named "Provider" already exists`; EPG variants prefixed `EPG: ...` with a lowercase first letter after the prefix; `/proc`, `/sys`, `/dev` paths -> synchronous `unsafe_path` `Path not allowed` (SR13 `[v0.2]`) |
| SRC-ERR-02 | fetch failure strings (UX 5.5) | H SRC-H05 | `<reason> from <host>` for URLs with `reason` from the shipped `Model.statusReason`: `HTTP 403 Forbidden`, `HTTP 404 Not Found`, `Could not resolve host`, `Connection refused`, `Timed out`, `Not an M3U playlist`, `Playlist has no channels`, `Source too large`, `Unsafe redirect`; for paths the reason alone: `File not found`, `Path not allowed`, `Playlist has no channels`; `Not an M3U file` (UX) vs `Not an M3U playlist` (shipped) per SRC-DEC-18; `<host>` is `Model.hostOf`, never a path, query or userinfo |
| SRC-ERR-03 | a failed add never displaces the active source | H SRC-H05 | `activeSourceKey` unchanged, `channels` count unchanged, guide list populated behind the form, playback intact, `updateEntryInline` not called, `barConfig` unchanged; `sourceProbeFinished({ok:false, id, reason, host})` emitted with a redacted reason; whether the failed record stays listed with an error marker is SRC-DEC-13/16 |
| SRC-ERR-04 | invalid input never runs the helper | H SRC-H03 | for every 5.4 code: no `python3 ... playlist` process in a 3 s watch, no `playlist:` console line, no directory created under `sources/` |
| SRC-ERR-05 | the 51st source (`too_many`) | H SRC-H11 | `addSource` returns `too_many`; message `Sources is full (50) - remove one first`; at the cap `a`, `c`, the `Add source` and `Add Xtream login` rows show that message in the footer instead of opening a form, `e` still opens the edit form (SR24 `[v0.2]`); `canAddSource` false |
| SRC-ERR-06 | `busy` and `not_ready` | H SRC-H14 | a second `addSource` / `switchSource` / `xtream` while a probe runs -> `busy`; an action before `stateLoaded` -> `not_ready`; the guide never shows either code as raw text |
| SRC-ERR-07 | persist failure (risk R2) | H SRC-H14 (harness verb `failPersist`) | `updateEntryInline` returning false while a change was needed -> `sourcesPersistFailed`; result-line copy `Could not save settings - try omarchy bar set`; no argv CLI fallback in M2-01 (signal only), so the harness stubs nothing and no `omarchy bar` argv appears in the console (SR25 `[v0.2]`) |
| SRC-ERR-08 | retry after a failed add | H SRC-H05 | Enter again in the same form re-probes the same record (no duplicate record, same key); `retrySource(id)` exists per SR2 (SRC-DEC-16 on the UI affordance) |
| SRC-ERR-09 | slow probe ends on the helper deadline | H SRC-H14 (silent loopback server) | `Timed out from 127.0.0.1` after ~20 s (the helper's `--timeout` default since D-LIVE-11, not 60 s `[v0.2]`), form thaws; the 180 s service watchdog is the backstop (not exercised) |

#### Keyboard and mouse (UX 2.1-2.5, 8.1-8.8)

| ID | Verifies | How | Expected |
|---|---|---|---|
| SRC-KEY-01 | guide list mode `o`/`O` (2.1) | H SRC-H06 | opens Sources; the list-mode footer hint ends with ` - o sources`; in search mode `o` is typed into the query |
| SRC-KEY-02 | `sources` mode keys (2.2) | H SRC-H06, SRC-H07 | `j`/Down, `k`/Up wrap over source rows and action rows; PgDn/PgUp/Home/End as the guide; Enter/Space semantics of SRC-SW-01/03 and on action rows open the forms; `a`/`A` add; `c`/`C` Xtream; `e`/`E` edit (no-op on action rows); `x`/`X`/Delete remove (no-op on action rows); `o`/`O`/Esc back |
| SRC-KEY-03 | plain / revealed field keys (2.3) | H SRC-H04, SRC-H12 (wtype) | printable inserts at the caret; Backspace one char; `Ctrl+Backspace` previous word; `Ctrl+U` clears; `Ctrl+V` / `Shift+Insert` paste at the caret then sanitize; `Ctrl+A` selects all; Left/Right/Home/End move the caret; Tab/Down next field then link rows and buttons then wrap (leaving a revealed field re-masks it); Shift+Tab/Up previous; Enter submits (or activates a focused button / link) |
| SRC-KEY-04 | masked field keys (2.3, 4.4) | H SRC-H12 | printable replaces the whole value (field now plain); Backspace / `Ctrl+Backspace` / `Ctrl+U` clear the whole value; paste replaces and re-masks; `Ctrl+A` no-op; arrows no-op with the footer `Ctrl+R reveal`; `Ctrl+R` reveals with the caret at the end, `Ctrl+R` again re-masks; re-mask on blur, Enter, Esc, form close, paste; the eye button toggles the same |
| SRC-KEY-05 | Esc by origin (2.3) | H SRC-H02, SRC-H12 | forms from Sources: one press cancels, nothing typed is kept, footer `Esc cancel`; first-run forms: clear-first rules (SRC-FR-06); while fetching: cancels the probe in any origin |
| SRC-KEY-06 | `confirmRemove` keys (2.4) | H SRC-H07 | exactly `ConfirmDialog.handleKey`: Left/Right/Tab/Shift+Tab toggle, Enter activates, Esc cancels; `y`/`n` do nothing |
| SRC-KEY-07 | key catcher blocked while a field has focus | H SRC-H02 | `PanelKeyCatcher { blocked: root.searchMode || root.formActive || root.confirmOpen }`: in every form `o`, `x`, `r`, `s`, `f`, `a`, `c`, `e`, digits become text; in `confirmRemove` letters do nothing |
| SRC-KEY-08 | `Ctrl+R` outside forms | H SRC-H06 | no-op in the guide and in `sources` (only `r` refreshes, and only in the guide) |
| SRC-KEY-09 | eye button is mouse-only | L 9.4; A grep | not a Tab stop (`activeFocusOnTab` false); click toggles reveal; tooltips `Show query - Ctrl+R` / `Hide query - Ctrl+R` |
| SRC-KEY-10 | focus on mode change (7.3) | H SRC-H06, SRC-H07 | key catcher regains focus on every mode change (`j` works immediately after Esc from a form or a dialog); the first-run `Playlist` field gets focus when the form appears |
| SRC-KEY-11 | mouse (2.5) | L 9.4 | pinned row click opens; row hover moves the cursor only through `PointerMoveGate`; row click switches; pencil / close-circle act; action rows click; wheel scrolls the list; field click focuses (masked stays masked); eye click; link rows; `Load` / `Save` / `Cancel`; terminal caption copies with `wl-copy` (`Copied`); overlay scrim click closes the guide from any mode and discards the form; the dialog scrim cancels only the dialog; middle click pastes the primary selection |
| SRC-KEY-12 | keys and hints live in Model.js (4.8) | A `grep -n 'SOURCE_KEYS\|footerHints' Model.js Guide.qml` | one `SOURCE_KEYS` table next to `footerHints`; Guide.qml spells no key name |

#### States, microcopy, visual tokens (UX 3.x, 4.x, 5.x)

| ID | Verifies | How | Expected |
|---|---|---|---|
| SRC-UI-01 | 3.1.1 first run before paste | H SRC-H02 (`sources-first-run.png`) | as SRC-FR-01; fields sit where the command box was; eye slot reserved but empty |
| SRC-UI-02 | 3.1.2 after paste, both URLs masked | H SRC-H04 (`sources-first-run-masked.png`) | values masked on arrival, eye U+F0208 at the end of each field that has something to mask, caret hidden while masked, footer `Enter load - Tab next field - Ctrl+R reveal - Ctrl+V replace - Esc clear`; the field is scrolled to the start so scheme and host are readable |
| SRC-UI-03 | 3.1.3 validation error line | H SRC-H03 (`sources-invalid.png`) | U+F0026 + text in the banner's urgent treatment (`Util.alpha(Color.urgent, 0.10)` fill, glyph `Color.urgent`), `Style.space(28)` tall, aligned with the fields; focused field `accent: Color.urgent`; clears on the next edit; the line's space is reserved so fields never jump |
| SRC-UI-04 | 3.1.4 fetching then failed | H SRC-H05 (`sources-add-failed.png`) | fetching: U+F01D8, neutral fill `Style.normalFillFor(...)`, controls disabled and dimmed, only hint `Esc cancel`; failed: same line turns urgent with `HTTP 404 Not Found from 127.0.0.1` (served missing file) or `Connection refused from 127.0.0.1` |
| SRC-UI-05 | 3.1.5 success | H SRC-H02 | form gone, footer transient `8 channels in 3 groups` then the normal status; pinned row count `1` |
| SRC-UI-06 | 3.1.6 saved sources, none active | H SRC-H07 | `Saved sources (3)` before `Use Xtream login instead`; footer `Enter load - Tab next field - Ctrl+V paste - Esc close` |
| SRC-UI-07 | 3.2.1-3.2.3 list states | H SRC-H06, SRC-H07 (`sources-list.png`, `sources-one.png`, `sources-empty.png`) | three sources with the active first (`active - 127.0.0.1 - 8 channels in 3 groups - EPG`), a never-loaded CLI source (`not loaded yet`, `never used`), a local file (`local file`); one source: `1 source`, `never used`, no footer label prefix; none: `No sources`, cursor on `Add source` |
| SRC-UI-08 | 3.3.1-3.3.2 edit form masked / revealed | H SRC-H12 (`sources-edit.png`, `sources-edit-revealed.png`) | masked: `http://127.0.0.1:8765/get.php?username=****&password=****&type=m3u_plus&output=ts`, eye U+F0208, footer `... Ctrl+R reveal - Ctrl+V replace - Esc cancel`; revealed: raw value scrolled to keep the caret visible, eye-off U+F0209, footer `Enter save - Tab next field - Ctrl+R hide - Esc cancel`; `EPG` stays masked independently |
| SRC-UI-09 | 3.4 Xtream form, empty and fetching | H SRC-H10 (`sources-xtream.png`, `sources-xtream-fetching.png`) | as SRC-XT-01; filled: username plain, password echo-masked by the kit (not `****`), then the fetching line |
| SRC-UI-10 | 3.5 confirm dialog | H SRC-H07 (`sources-confirm.png`) | dialog with the guide's menu tokens, message per 5.7, `[[ Remove ]]` preselected with the urgent border |
| SRC-UI-11 | 3.6 switching transient sequence | H SRC-H06 | `Switched to <label> - 5 channels` -> after `transientMs` `<label> - 5 channels - cached HH:MM` -> `Refreshing...` while the background refresh runs -> `<label> - 5 channels - updated HH:MM`; failure banner as shipped |
| SRC-UI-12 | 3.7 / 4.5 pinned row tokens | A grep Guide.qml; H screenshot | separator `Style.normalBorderWidth` / `Util.alpha(Color.menu.border, 0.28)` with `Style.space(6)` above and below; row `groupEntryHeight`; glyph `Style.font.iconSmall` at `Style.space(10)` padding, `Style.spacing.labelGap` gap; count `Style.font.caption` opacity 0.45 right at `Style.space(10)`; hover `Style.hoverFillFor(Color.menu.text, Color.accent)`, `Qt.PointingHandCursor`, 60 ms `Behavior on color`; never `selectedBackground` |
| SRC-UI-13 | microcopy 5.1 | A `grep` of the `copy` block in Guide.qml / Model.js; H screenshots | every string of UX 5.1 verbatim: headers, `3 sources` / `1 source` / `No sources`, form titles, field labels, placeholders (`https://host/playlist.m3u or /path/to/list.m3u`, `optional - XMLTV URL, .xml or .xml.gz`, `http://host:port`, `optional`), link rows, buttons (`Load` on first run only), Xtream prose, action rows, eye and button tooltips, column row `Sources` |
| SRC-UI-14 | footer table 5.3 | H every scenario | list mode hint + ` - o sources`; 2+ sources label prefix; error state with sources `r retry - o sources - Esc close`; `sources` `j/k move - Enter switch - a add - c Xtream - e edit - x remove - Esc back`; action row `j/k move - Enter open - Esc back`; form plain / masked / revealed / button-focused variants; Xtream `Enter save - Tab next field - Esc cancel`; first run `Enter load ...` with `Esc clear` / `Esc close`; fetching `Esc cancel`; confirm `Left/Right choose - Enter confirm - Esc cancel`; transients `1,475 channels in 28 groups`, `Added tv.example.net - 1,475 channels in 28 groups`, `Saved`, `Saved - 1,475 channels in 28 groups`, `Switched to NAS Tvheadend - 84 channels`, `Removed NAS Tvheadend`, `Removed Provider - no active source` (counts from the fixtures) |
| SRC-UI-15 | nothing hardcoded (4.8) | A `grep -nE '#[0-9a-fA-F]{3,8}\b|"white"|"black"|Qt\.rgba\(' *.qml`; `grep -n '\*\*\*\*\|2048\|get.php' Guide.qml` | no hex colors; `MASK`, `LIMITS`, the Xtream template, the label rule and the last-used formatter exist only in Model.js; field heights are `implicitHeight`; `Style.space(640)` / `space(96)` / `space(22)` tokens |
| SRC-UI-16 | animation (4.7) | H screenshots taken right after a mode flip | no fade on mode changes; `bannerFadeMs` on the result line; `transientMs` on footer transients; 60 ms color behavior on the pinned row and action buttons |
| SRC-UI-17 | last-used formatter (5.2, 8.19) | A `node` (`formatLastUsed(at, now)`) | with `now` fixed: same day `used 21:30` (24 h local), previous day `used yesterday`, this year `used 3 Sep`, older `used 3 Sep 2025`, 0 `never used` |
| SRC-UI-18 | counts and plurals | A `node` (`sourceDetail`, `pluralGroups`); H | `1 channel in 1 group`, `1,475 channels in 28 groups`, `not loaded yet` for `channelCount -1`; header `1 source` / `3 sources` / `No sources` |
| SRC-UI-19 | theme switch with Sources and forms open | L 9.6 | `omarchy theme set nord` with the list, a form and the dialog open: tokens re-skin live, no restart, no new journal warnings |
| SRC-UI-20 | card geometry and the form column (4.2) | A grep; H | card unchanged (`space(960)` / `space(620)`); form column `Math.min(body.width, Style.space(640))` centred; label column `Style.space(96)`; eye slot `Style.space(22) + controlGap` reserved on every row; narrow: labels above fields |

#### Accessibility (UX 7)

| ID | Verifies | How | Expected |
|---|---|---|---|
| SRC-A11Y-01 | roles and names (7.1) | A `grep -n 'Accessible\.' Guide.qml` | Heading (titles), Button `Sources, 3 saved`, List `Sources`, ListItem `<label>, <host>, <n> channels in <m> groups` + `, active` + `, EPG` + `, last used <x>` / `, never used` / `, not loaded yet` with `focused` = cursor and `selected` = active, ListItem action rows, Button `Edit <label>` / `Remove <label>`, Dialog `Add source` / `Edit source` / `Add Xtream login` / `Set up a playlist`, EditableText `Label, optional` / `Playlist URL or path` / `EPG URL, optional` / `Server URL` / `Username` / `Password`, Button eye `Show query` / `Hide query` with `checked`, Button link rows `Use Xtream login instead` / `Saved sources, 3`, Button `Load` / `Save` / `Cancel`, AlertMessage result line, Dialog confirm with its two Buttons |
| SRC-A11Y-02 | no color-only state (7.2) | H review of every screenshot | active = glyph + bold + `active`; error = glyph + words; fetching = glyph + words + disabled; revealed vs masked = the text + eye/eye-off; destructive = urgent border + `Remove` |
| SRC-A11Y-03 | focus order (7.3) | H SRC-H02, SRC-H10, SRC-H12 (Tab x n via wtype, `state()` reports the focused field) | first run `Playlist` -> `EPG` -> `Saved sources (n)` -> `Use Xtream login instead` -> `Load` -> wrap; add `Label` -> `Playlist` (initial) -> `EPG` -> link -> `Save` -> `Cancel`; edit `Label` (initial) -> `Playlist` -> `EPG` -> `Save` -> `Cancel`; Xtream `Label` -> `Server` (initial) -> `Username` -> `Password` -> `Save` -> `Cancel`; the eye button is skipped |
| SRC-A11Y-04 | hit targets (7.4) | A grep; L 9.4 | rows full width by `detailRowHeight` / `singleRowHeight`; action buttons >= `Style.space(22)` square; pinned row full column width by `groupEntryHeight` |
| SRC-A11Y-05 | screen readers never get a secret (6.7) | A grep | URL fields: `Accessible.description` bound to the masked rendering even while revealed; password field `Accessible.passwordEdit: true` |
| SRC-A11Y-06 | source row accessible name composition | A `node` (`sourceAccessibleName`) | fixture rows -> `Alpha, 127.0.0.1, 8 channels in 3 groups, active, EPG, last used 21:30`; never a URL |

#### Privacy rules as UI behaviour (UX 6.1-6.9, decision 4, R12)

| ID | Rule | How | Expected |
|---|---|---|---|
| SRC-PRIV-01 | 6.1 the list never renders a URL | H SRC-H13 | rows: label, host (`local file` for paths), kind, counts, last used; no tooltips on rows; `sources()` has no URL key |
| SRC-PRIV-02 | 6.2 the URL exists on screen only in a field the user opened, masked by default | H SRC-H12, SRC-H13 | masked until `Ctrl+R` / eye; reveal never survives leaving the field, saving, cancelling or closing the guide |
| SRC-PRIV-03 | 6.3 mask scope (SR4) | A `node` (`maskUrl`) | userinfo -> `****@`, every query value -> `****` except `type` and `output`, fragment -> `#****`; scheme, host, port, path, query keys kept; local paths unchanged; `maskUrl(v) === v` means no eye and `Ctrl+R` no-op; vectors of ARCH 3.3 plus UX 4.4 with the SR4 exception (SRC-DEC-17 note) |
| SRC-PRIV-04 | 6.4 transients, footer, header, banners, result lines carry label and host at most; no new notification | H SRC-H13 | every transient of 5.3 checked against the needles; `notifications.log` gains no line from any Sources operation (add, switch, edit, remove, Xtream, cancel, failure) |
| SRC-PRIV-05 | 6.5 the Xtream password is echo-masked and dropped | H SRC-H10, SRC-H13 | `password: true`; cleared from form state after the URLs are built; the edit form shows only masked URLs |
| SRC-PRIV-06 | 6.6 clipboard content is data | H SRC-H04, SRC-H13 | sanitized on arrival, never executed, never echoed anywhere but the field (console has no line with the pasted text); a paste into a masked field replaces and re-masks before the next frame (screenshot right after the chord shows `****`) |
| SRC-PRIV-07 | 6.7 accessibility never exposes the query | A grep (SRC-A11Y-05) | as stated |
| SRC-PRIV-08 | 6.8 console logs mode changes at most | H all scenarios | `grep -E 'omarchy-iptv' console.log` shows keys, labels, hosts, codes, modes; never a field value; `grep -cE '://|password=|username=|@' ` on the plugin's lines = 0 |
| SRC-PRIV-09 | 6.9 one path for every mutation | A code review; H SRC-H09 | Space/Enter, `x`, and the CLI all go through `service.switchSource` / `removeSource` / reconcile; `grep -n 'playlistUrl' Guide.qml` shows only the form state and `sourceForEdit` binding, no other copy |

#### Security of the input surface (SECURITY-REVIEW bar; ARCH 6; PLAN G4)

| ID | Standard | How | Expected |
|---|---|---|---|
| SRC-SEC-01 | clipboard content as data: control characters | H SRC-H04 (`paste/paste-multiline.txt`) | `wl-copy < file` then `Ctrl+V`: every control character (CR, LF, TAB) is removed and the edges trimmed per ARCH 3.1 `sanitizeInput`, so the two lines concatenate into one value (`http://127.0.0.1:8765/qa-src-a.m3usecond line must vanish`, 57 characters) that the validator refuses on Enter (`[v0.2]`: the v0.1 expectation "second line gone" was QA's reading, not the ARCH rule); nothing runs; the console never shows the pasted text |
| SRC-SEC-02 | 100 KB paste | H SRC-H04 (`python3 -c "print('http://h.test/' + 'a'*102400, end='')" \| wl-copy`) | the field holds `LIMITS.url + 64` = 2,112 characters (`Model.formCapacity`: a margin above the cap so a 2,049+ character paste reaches the validator as `too_long` instead of being silently truncated, SR18 `[v0.2]`), the UI stays responsive (a screenshot within 1 s), validator `too_long` on Enter without a helper run, `state()` dump under 4 KB for the field, no 100 KB string in any log |
| SRC-SEC-03 | RTL and zero-width characters | H SRC-H04 (`nonascii/paste-rtl.txt`); A vectors SRC-URL-027/033/093/110 | U+202E/U+202C are kept as data, U+200B in the host per SRC-DEC-05, U+FEFF trailing is trimmed only if the lead adds it to sanitize (SRC-DEC-05), NBSP trimmed; the masked rendering and the list row keep `127.0.0.1` readable left-to-right; no crash in the Qt text layout |
| SRC-SEC-04 | scheme allow-list | A vectors SRC-URL-080..093; H SRC-H03 | `javascript:`, `data:`, `vbscript:`, `ftp:`, `rtsp:`, `mailto:`, `about:` refused inline with the `scheme` message and no process; `file:///etc/passwd` is accepted as the user's own file and fails at fetch with `Not an M3U playlist` / `Playlist has no channels` (QA.md SEC-10) |
| SRC-SEC-05 | path traversal and symlinks | A vectors SRC-URL-041..043, 046, 052, 053; H SRC-H03 | `/srv/tv/../../etc/passwd`, `/../proc/self/environ`, `//proc/self/environ` pass the synchronous check and are refused by the helper at fetch (`Path not allowed`) - allowed by ARCH 3.1; `~` per SRC-DEC-01; a symlink `$SCRATCH/fixtures/link.m3u -> /proc/self/environ` added as a source -> `Path not allowed`, no bytes read; a symlink to `qa-src-a.m3u` works and the label is the link's file name; retargeting the symlink after the add makes the next refresh follow the new target (documented) |
| SRC-SEC-06 | hostile label | A `qa-source-labels.json` T07-T09, T15; H SRC-H06 | `-u critical`, `--urgency=critical ${path}`, backticks / `$(id)` / `\|` / `>`, `<b>` markup: stored as typed, painted as `Text.PlainText`, JSON-escaped in `state.json`, never passed to `omarchy-notification-send` (no notification exists for sources) or to mpv (`--title` is a channel name); `state show` prints it inside JSON only |
| SRC-SEC-07 | credentials never appear in any sink | H SRC-H13 | sources: `qa-src-userinfo.m3u` at `http://qa-user:qa-secret@127.0.0.1:8765/...` and the Xtream login; needles `qa-user`, `qa-secret`, `pa ss`, `pa%20ss`, `username=user`, `password=`, `cu:cs`, `/live/`; 0 hits in: `sources()`, the list screenshot, footer transients, `notifications.log`, IPC `status`, `state show`, the harness `state()` dump, the widget JSON, the harness console, `run.sh` output (`--source2` prints `scheme://host`), the journal on the live shell; expected hits: `state.json` (0600, by design), `channels.json` (by design), the helper probe argv for its lifetime |
| SRC-SEC-08 | cache key path traversal in `cache remove` / `prune` | H SRC-H15; A* `tests/test_helper.py` | keys `../x`, `../../x`, `abc`, `d5977d8a/..`, `d5977d8a/../../x`, `%2e%2e`, `` (empty), `D5977D8A` (uppercase), `d5977d8a-1000` (suffix over 3 digits): every one -> `{"ok":false,"kind":"cache","error":{"code":"bad_key","message":"invalid cache key"}}` exit 1 (`d5977d8a-0` is a VALID key by the shared `SOURCE_KEY_RE` `^[0-9a-f]{8}(-[0-9]{1,3})?$` and answers `ok, removed: []` `[v0.2]`) and a canary file placed next to `sources/` untouched; a symlink `sources/deadbeef -> $SCRATCH/canary` -> the realpath guard refuses (`bad_key` or `skipped`), the canary intact; `--keep` with a bad key -> `bad_key`; no argv path echoed in any message |
| SRC-SEC-09 | `state.json` 0600 after the v2 migration and every save | H SRC-H01, SRC-H16 | `stat -c %a` = `600` after migration, after five saves (add, label edit, switch, remove, favorite), after a restart with `--keep`; dir `700`; `cache/omarchy-iptv/sources` `700`, every `sources/<key>` `700`, every file inside `600`; the FileView never creates a new file (`state init` runs first) |
| SRC-SEC-10 | 50-source cap | H SRC-H11, SRC-H16 | 51st add -> `too_many`; CLI 51st -> LRU eviction never of the active; `state.json` size recorded (section 6); `cache prune` argv carries at most 50 keys (`ps -o args=` during the start, or the harness log) |
| SRC-SEC-11 | probe cancel leaves no temp dir | H SRC-H14 | during a slow probe (`http://10.255.255.1/x.m3u` or the trickle server) press Esc: helper gone within 1 s (SIGTERM), `find $SCRATCH/cache -name '.tmp-*'` empty, the cancelled key's directory absent or empty and removed by the startup prune next time; an add's record dropped, an edit's original intact |
| SRC-SEC-12 | no shell, argv only (8.1) | A `grep -rnE 'bash -c\|sh -c\|shell=True\|os\.system\|subprocess\.(call\|run\|Popen)\([^\[]\|execDetached\("\|command: "\|\beval\(' --include='*.qml' --include='*.js' --include='*.py' --include='omarchy-iptv' . \| grep -v '^./tests/' \| grep -v '^./docs/'` | nothing; every new `Process` (`sourceProbeProc`, `cacheProc`, `wl-paste`, the CLI fallback) is an argv array; the URL follows `--url`, keys follow `--key` / `--keep` |
| SRC-SEC-13 | no markup rendering of user strings | A `grep -n 'StyledText\|RichText' Guide.qml` | only the plugin's own hint strings; every label / host / reason / transient is `Text.PlainText` |
| SRC-SEC-14 | helper `state` stdout never carries a URL | A* `tests/test_state.py`; H SRC-H16 | `state show \| grep -c '://'` = 0; no `url` / `epgUrl` key; `kind: "file"` records print `host: "local file"`, never the path |
| SRC-SEC-15 | probe stderr and console redaction | H SRC-H05, SRC-H13 | probe stderr goes through `Model.redactUrls` before `console.warn`; console lines of this feature name keys, labels, hosts and codes only |
| SRC-SEC-16 | Xtream password lifetime and process exposure | H SRC-H10, SRC-H13 | not a QML property after `buildXtreamSource` returns (`state()` dump); present in the helper `playlist --url` argv for the probe only (`ps -o args=` during the probe: expected, documented like M1's first mpv launch, SECURITY-REVIEW S-03); never in mpv argv, notifications, IPC |
| SRC-SEC-17 | IPC surface unchanged (8.6) | H SRC-H13; L 9.3 | `qs ipc -n -p /usr/share/omarchy/shell show` (live) / harness `show`: the M1 verbs only; `status` URL-free; no verb takes a URL or a path |
| SRC-SEC-18 | hostile playlist vs the Sources screen (8.7) | H SRC-H06 with `fixtures/sec.m3u` from the M1 pass as a source | channel names `${path}`, `-u critical` never reach the rows (counts only); a playlist `url-tvg` hint never becomes an EPG URL (no epg helper run, `hasEpg` false) |
| SRC-SEC-19 | credentials at rest (8.8) | H SRC-H07, SRC-H16; L 9.2 | `state.json` holds every URL (0600 in 0700); removing deletes the record and the directory; the shell.json entry is cleared when the active source is removed; README settings sentence present |
| SRC-SEC-20 | concurrency bounds (8.9) | H SRC-H14 | one probe (`busy`), one playlist refresh, one EPG run, one cache job (FIFO: three removals in a row all complete); each helper under the 180 s watchdog; at most 50 sources |
| SRC-SEC-21 | tampered `state.json` v2 | A `node` (`parseState`); H SRC-H16 | records with a bad `key` (`../x`, `abc`), a URL with control characters, a 3,000-character URL, a 500-character label, duplicate `url` or `key` (first wins), non-object entries, `sources` not an array, `cacheLayout` `"x"`: dropped or coerced, no crash, no directory ever built from a bad key (the `cache prune --keep` argv contains valid keys only) |
| SRC-SEC-22 | migration runs once | H SRC-H01 | second start with `--keep`: no `cache migrate` process, no `cacheLayout` rewrite (state.json mtime unchanged); `cacheLayout: 2` with stray legacy files: left alone (documented) |
| SRC-SEC-23 | prune never touches non-key names | H SRC-H15 | `sources/evil`, `sources/..x`, `sources/link -> elsewhere`: reported under `skipped`, never deleted or followed |
| SRC-SEC-24 | dev harness hygiene (S-08) | A `grep -n 'source2\|updateEntryInline' scripts/dev-harness/run.sh scripts/dev-harness/shell.qml` | `--source2` echoed as `scheme://host`; `updateEntryInline` logs keys and `(set)`/`(none)` only while applying the entry |

#### Migration (ARCH 2.2, 2.3, 4.4, 8.5 item 1)

| ID | Verifies | How | Expected |
|---|---|---|---|
| SRC-MIG-01 | v1 state + legacy cache -> v2 records | H SRC-H01 (`state-v1.json`, `legacy-cache/`) | after start: `version: 2`, `cacheLayout: 2`, `favorites` exactly `["t:qa.a.news1","t:qa.shared","u:502142db"]`, `recents` the three entries in order with their `at`, `lastPlayed` intact; `sources[0]` = `{key: <fnv1a32 of the settings playlistUrl>, url: <that URL>, epgUrl: "", kind, label: derived, labelCustom: false, origin: "migrated", addedAt/lastUsed set, fetchedAt: 1789244100, channelCount: 8, groupCount: 3}` (counts copied from the migrated status) |
| SRC-MIG-02 | files moved, not copied | H SRC-H01 | `sources/<key>/channels.json` and `playlist-status.json` byte-identical to the fixtures (sha256) when the stamps are fresh (no refresh); top-level `channels.json` / `playlist-status.json` gone; no `.tmp-*`; modes `700` / `600`; `cache migrate` output `{"ok":true,"kind":"cache","action":"migrate","key":"<key>","moved":["channels.json","playlist-status.json"],"removed":[]}` |
| SRC-MIG-03 | the guide shows the migrated cache at once | H SRC-H01 | 8 channels within ~1.5 s of start, favorites 3, Recent 3; with fresh stamps no helper run; with the fixture's old stamp (T0) a background refresh follows and the count stays 8 |
| SRC-MIG-04 | idempotent | H SRC-H01 (restart `--keep`) | no second migrate, nothing moved, state unchanged |
| SRC-MIG-05 | legacy files with no `playlistUrl` | H SRC-H01 variant (`--playlist none`) | `cache migrate` without `--key` deletes the legacy files (`removed: [...]`), `sources: []`, first-run form |
| SRC-MIG-06 | attribution when the legacy status host differs from the settings URL | H SRC-H01 (fixture `sourceHost: "local file"`, settings = the served URL) | the files are attributed to the settings URL's key regardless (the only fact available); recorded |
| SRC-MIG-07 | downgrade tolerance | A `git show v0.1.0:Model.js > $S/Model-v010.js && node -e '...parseState(v2 text)...'` | the v0.1.0 `parseState` and the v0.1.0 helper `normalize_state` (`git show v0.1.0:bin/omarchy-iptv`) read a v2 file: favorites and recents intact, unknown keys ignored, no crash |
| SRC-MIG-08 | corrupt state + legacy cache | H SRC-H01 variant (`garbage{{{`) | empty v2 state, migration still runs (`cacheLayout` 0 -> 2), no crash, one warning at most |
| SRC-MIG-09 | helper `cache migrate` semantics | A* `tests/test_helper.py`; H SRC-H15 | moves the five names when the target does not exist; deletes the legacy file when the target exists; leftover `.tmp-*` in the cache root deleted; without `--key` legacy files deleted; creates `sources/<key>` 0700; idempotent |
| SRC-MIG-10 | live machine upgrade in place | L 9.2 | `python3 -c '...'` prints `2 2 [('d5977d8a', 'iptv-org.github.io', 1475)]`; recents still 5; `find ~/.cache/omarchy-iptv -maxdepth 2 -exec stat -c '%a %n' {} +` shows `700` dirs, `600` files, no legacy files at the top level; the guide shows the US list as before without a re-download (journal: no `playlist:` line at start when the cache is younger than `refreshMinutes`) |

#### Performance (ARCH 7; PLAN G3)

| ID | Budget | How | Record |
|---|---|---|---|
| SRC-PERF-01 | switch redraw < 150 ms at 10k (warm cache) | H SRC-H08 | median and max of 5 switches each way between `gen-10k.m3u` and `qa-src-a.m3u`, from the `OMARCHY_IPTV_DEBUG=1` lines `omarchy-iptv switch <ms>` (Lane 2 adds them at `switchSource` and after the guide rebuild); also `gen-real.m3u` (1,500) for the typical number; over budget -> the prepared-LRU of ARCH 4.5 is the ready fix |
| SRC-PERF-02 | no helper run on opening Sources; Sources open < 10 ms | H SRC-H06, SRC-H16 (50 records) | 3 s process watch after `o`: no `python3` child; console: no helper line; with 50 records the `o` -> rendered time from a debug line or the layer poll under 10 ms |
| SRC-PERF-03 | `state.json` size with 50 sources | H SRC-H16 | typical (fixture-length URLs): under ~35 KB (ARCH 7); worst case (2,048-character playlist and EPG URLs, 64-character labels): ~215 KB - recorded, plus `parseState` time on it (node) and the save latency |
| SRC-PERF-04 | guide open budget unchanged with sources | H (QA.md PERF-02 method) on the 10k cache with 50 records | IPC open median minus baseline < 150 ms; the group column gains one pinned row only |
| SRC-PERF-05 | startup extras | H SRC-H01 | one `cache migrate` (first v2 run) + one `cache prune` per start, serialized (`cacheProc` FIFO), each ~40 ms; the guide is usable before they finish |
| SRC-PERF-06 | probe plus refresh at once (R6) | H SRC-H14 | a 10k probe while the active 10k source refreshes: both finish, one `sourceProbeFinished`, one refresh notification at most; typing in the guide after Esc registers every key |
| SRC-PERF-07 | disk and prune ageing (R5) | H SRC-H15 | 5 sources x sizes recorded; `touch -d '2 days ago'` on an inactive source's `epg-*` files then a restart: `cache prune` output `agedEpg: [<key>]`, the files gone, `channels.json` kept; the active source's EPG files untouched |

#### Model.js (automated; ARCH 8.3 row 1-2, 3.x)

| ID | Verifies | How | Expected |
|---|---|---|---|
| SRC-MODEL-01 | the ARCH 8.3 node list | A `node tests/Model.test.js` | `sanitizeInput`, every `source-urls.json` case, `sourceKey` vectors, `allocateSourceKey` with a forced collision, `defaultSourceLabel` dedupe and caps, `maskUrl`, `xtreamUrls` + the percent-encoding vector, `parseState` v1 -> v2, every reducer carrying `sources`, `reconcileSources` (known, unknown, invalid, eviction never the active), `addSource` codes, `updateSource` replacement, `removeSource`, `withSourceStats`, `sourceRows`/`sourceView` without `url`, `sourcesSummary` without `://`, `entryWith` keeps foreign keys, `cacheStale`; a missing item is a P3 coverage defect |
| SRC-MODEL-02 | QA vectors agree with Lane 1's fixture | A section 2 command | every `qa-source-urls.json` record (skipping `skip: true`, honouring `padTo`, `field`, `existing`) gives the expected verdict through `Model.validateSourceUrl`; every vector present in both files carries the same verdict; disagreements are reconciled before the pass (a `decision` record is reported, not failed) |
| SRC-MODEL-03 | Xtream vectors | A section 2 command | `xtream-expect.json` V and E cases through `Model.xtreamUrls` / `validateXtream`; D cases reported |
| SRC-MODEL-04 | label vectors | A section 2 command | `qa-source-labels.json` through `deriveLabel` / `uniqueLabel` / `validateLabel` |
| SRC-MODEL-05 | key vectors | A `node -e` | `584a58e5` (`http://127.0.0.1:8765/qa-src-a.m3u`), `733cf68c` (`.../qa-src-b.m3u`), `25b70358` (`http://qa-user:qa-secret@127.0.0.1:8765/qa-src-userinfo.m3u`), `6e90a03e` (the Xtream get.php URL), `d5977d8a` (iptv-org us), `f0441ae2` (iptv-org ca); a trailing space changes the key (`c209be1f`) so sanitizing must happen first |
| SRC-MODEL-06 | mask vectors | A `node -e` | ARCH 3.3 vectors; UX 4.4 with the SR4 exception: `http://user:pw@tv.example.net:8080/get.php?username=tomasz&password=s3cret&type=m3u_plus&output=ts#x` -> `http://****@tv.example.net:8080/get.php?username=****&password=****&type=m3u_plus&output=ts#****`; paths unchanged; `https://iptv-org.github.io/iptv/index.m3u` unchanged |
| SRC-MODEL-07 | state parsing and tampering | A `node -e` with `state-v1.json` and the SRC-SEC-21 shapes | v1 -> v2 keeps favorites/recents/lastPlayed, `sources: []`, `cacheLayout: 0`; bad records dropped; first duplicate wins |
| SRC-MODEL-08 | `reconcileSources` | A* `Model.test.js` | known URL: no add, `lastUsed` only on key change, `epgUrl` adopted, custom label kept; unknown: add with `origin: "cli"` and a derived unique label; invalid -> `invalid` result and no add; 51st -> `evicted` never the active key |
| SRC-MODEL-09 | view objects (SR1) | A* `Model.test.js`; `node -e` | `sourceView` keys exactly `id,label,kind,host,hasEpg,channelCount,groupCount,cachedAt,lastUsedAt,active`; `kind` in `url,file,xtream`; `channelCount -1` when never fetched |
| SRC-MODEL-10 | the Qt engine agrees (V4) | A `QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml` | the same vectors for `validateSourceUrl`, `sourceKey`, `maskUrl`, `xtreamUrls`, `parseState` (proves `decodeURIComponent` / `encodeURIComponent` / `toLowerCase` in V4) |
| SRC-MODEL-11 | formatters | A `node -e` | `formatLastUsed`, `pluralGroups`, `sourceDetail(source, narrow)`, `sourceAccessibleName`, `footerHints` for the four new modes, `SOURCE_KEYS` |

#### Helper (automated; ARCH 8.3 row 3, 2.3, 2.4)

| ID | Verifies | How | Expected |
|---|---|---|---|
| SRC-HELP-01 | `validate_source_url` over both fixtures | A* `tests/test_source.py`; QA: section 2 python command | identical verdicts to node (`SRC-MODEL-02`); the parity vectors of SRC-DEC-05 pinned one way or the other |
| SRC-HELP-02 | `resolve_source` refuses `too_long` and control characters without echoing | A* `tests/test_source.py` | codes `too_long`, `bad_url`; stdout/stderr never contain the input |
| SRC-HELP-03 | per-source cache writes | A* `tests/test_helper.py`; QA by hand (section 7 commands) | `playlist --cache-dir <tmp>/sources/k` creates `k` 0700 and 0600 files; `epg` the same for `epg-*` |
| SRC-HELP-04 | `state` v2 | A* `tests/test_state.py` | `default_state()` v2 with `cacheLayout 0`, `sources []`; `state init` writes it 0600; `favorite add`/`remove`, `clear-recents` on v1 and v2 files keep `sources` and `cacheLayout`; `public_state()` redaction (host / epgHost); `EMPTY` updated |
| SRC-HELP-05 | `cache migrate` | A* `tests/test_helper.py` | SRC-MIG-09 |
| SRC-HELP-06 | `cache remove` | A* | SRC-RM-07 and the `bad_key` set of SRC-SEC-08 |
| SRC-HELP-07 | `cache prune` | A* | keeps listed keys, removes other valid-key dirs file by file, reports dirs with unknown files, ages `epg-*` of kept non-active keys older than `--epg-max-age`, skips non-key names, `bad_key` for a bad `--keep` or `--active` |
| SRC-HELP-08 | CLI contract | A* `tests/test_helper.py` (`CliContractTest.SUBCOMMANDS` gains `cache`) | `--help` lists `cache`; usage errors exit 2 without JSON; exactly one JSON line on stdout |
| SRC-HELP-09 | `normalize_state` on tampered input | A* | SRC-SEC-21 shapes; never raises |
| SRC-HELP-10 | EPG into a per-source directory with the fixture pair | QA by hand: `python3 bin/omarchy-iptv playlist --url tests/fixtures/qa-sources/qa-src-a.m3u --cache-dir $S/sources/584a58e5 && python3 bin/omarchy-iptv epg --url tests/fixtures/qa-sources/qa-src-a.xml --cache-dir $S/sources/584a58e5 --force --now 1789244100` | `epg-now.json` in that directory with `qa.shared` now `Shared Now` / next `Shared Next`, `qa.a.news1` now `Alpha Evergreen`; warning `1 programmes for channels not in the playlist dropped`; without `--now` the evergreen rows remain and `qa.shared` has none (verified on the shipped helper 2026-09-13) |

#### Service contract (ARCH 4.1-4.8, SR1-SR3)

| ID | Verifies | How | Expected |
|---|---|---|---|
| SRC-SVC-01 | properties (4.1, SR1) | H `state()` | `sources` (view objects), `activeSourceId` / `activeSourceKey`, `activeSourceLabel`, `activeCacheDir` (`""` until `stateLoaded && cacheReady`), `sourceCount`, `canAddSource`, `stateLoaded`, `cacheReady`, `probing`, `probingKey`, `switching`, `sourceErrors` (URL-free), `settingsInvalid` |
| SRC-SVC-02 | actions and result shape (4.3, SR2) | H verbs | `addSource`, `updateSource`, `removeSource`, `switchSource`, `buildXtreamSource`, `sourceForEdit`, `retrySource`, `cancelProbe` all return `{ok, code, message, id}` synchronously; codes from the SR6 list plus `duplicate`, `too_many`, `busy`, `unknown_source`, `not_ready`, `persist_failed` |
| SRC-SVC-03 | signals (4.2, SR3) | H (the harness logs signal payloads with `id`, `ok`, `reason`, `host`, counts) | `sourceProbeFinished({ok, id, channelCount, groupCount, reason, host})`, `sourcesChanged()`, `sourceSwitched(id)`, `sourceRemoved(id)`, `sourcesPersistFailed(reason)`; reasons already redacted |
| SRC-SVC-04 | startup sequence (4.4) | H SRC-H01 console order | `mkdir` (four dirs incl. `sources`) -> `state init` -> `dirsReady` -> state loaded -> reconcile -> migrate (once) -> `cacheReady` -> FileViews rebind -> freshness -> optional refresh -> prune |
| SRC-SVC-05 | `activeCacheDir` becomes `""` | H SRC-H07 | clears channels, index, meta, playlist status, warnings, EPG state, `lastError` in memory; no stale reason survives a switch (D-LIVE-10 regression) |
| SRC-SVC-06 | probe process isolation (4.6) | H SRC-H14 | a probe never blocks a refresh of the active source and vice versa; both have the 180 s watchdog and stderr redaction |
| SRC-SVC-07 | cache queue (4.7) | H SRC-H07 (three removals) | one `cacheProc` at a time, FIFO, failures `console.warn`ed with code and action only |
| SRC-SVC-08 | `persistActive` compares first (R2) | H SRC-H06 | switching to the active source or re-setting the same values never calls `updateEntryInline` (harness log count) |

### 1.2 Stories S1-S8 -> test cases

| Story | Test cases |
|---|---|
| S1 First run | SRC-FR-01..12, SRC-UI-01..06, SRC-KEY-05, SRC-KEY-07, SRC-A11Y-03, SRC-SEC-01..05 |
| S2 Sources screen | SRC-LST-01..12, SRC-KEY-01, SRC-KEY-02, SRC-KEY-11, SRC-UI-07, SRC-UI-12, SRC-UI-14, SRC-A11Y-01, SRC-A11Y-06, SRC-PRIV-01 |
| S3 Switching | SRC-SW-01..10, SRC-UI-11, SRC-PERF-01, SRC-PERF-02, SRC-SVC-05, SRC-SVC-08 |
| S4 Labels | SRC-LBL-01..09, SRC-UI-08, SRC-KEY-03, SRC-KEY-04, SRC-MODEL-04 |
| S5 CLI parity | SRC-CLI-01..08, SRC-FR-11, SRC-MODEL-08, SRC-SEC-17 |
| S6 Xtream | SRC-XT-01..10, SRC-UI-09, SRC-PRIV-05, SRC-SEC-16, SRC-MODEL-03 |
| S7 Removal | SRC-RM-01..09, SRC-UI-06, SRC-UI-10, SRC-KEY-06, SRC-SEC-19, SRC-SVC-07 |
| S8 Errors | SRC-ERR-01..09, SRC-UI-03, SRC-UI-04, SRC-SEC-04, SRC-SEC-11, SRC-MODEL-02 |

### 1.3 Rulings SR1-SR10 -> test cases

| Ruling | Test cases |
|---|---|
| SR1 identifiers: state field names kept, `sourceView` names for the guide, `activeSourceId` | SRC-LST-11, SRC-MODEL-09, SRC-SVC-01, SRC-MIG-01 |
| SR2 service actions incl. `cancelProbe`, result `{ok, code, message, id}` | SRC-SVC-02, SRC-FR-07, SRC-ERR-06, SRC-ERR-08, SRC-RM-06 |
| SR3 signals with redacted `reason` | SRC-SVC-03, SRC-ERR-03, SRC-SEC-15 |
| SR4 mask rule `****`, `type`/`output` visible, reveal `Ctrl+R` / eye, re-mask on blur/save/cancel/paste | SRC-PRIV-02, SRC-PRIV-03, SRC-MODEL-06, SRC-KEY-04, SRC-UI-02, SRC-UI-08, SRC-XT-05 |
| SR5 limits 2048 / 64 / 512 / 256 / 50 | SRC-LBL-06, SRC-ERR-01, SRC-ERR-05, SRC-SEC-02, SRC-SEC-10, SRC-XT-03, SRC-UI-13 (copy quotes 64 / 256 / 2,048) |
| SR6 UX 5.4 codes canonical, one fixture for both validators | SRC-ERR-01, SRC-MODEL-02, SRC-HELP-01, SRC-XT-03 |
| SR7 probe semantics: add / URL edit / never-fetched switch probe then commit; label and EPG edits commit at once; cancel discards the new dir | SRC-FR-02, SRC-FR-05, SRC-FR-07, SRC-LBL-04, SRC-SW-06, SRC-ERR-03, SRC-SEC-11, SRC-CLI-08 |
| SR8 CLI parity, invalid values synthesize an error and never run the helper | SRC-CLI-01..05, SRC-FR-11 |
| SR9 favorites and recents global by channel id | SRC-SW-07, SRC-MIG-01 |
| SR10 lanes and merge order | SRC-MODEL-01 (Lane 1 lands first), section 8.0 (harness verbs are Lane 2's) |

### 1.4 UX-SOURCES.md flows -> test cases

| UX section | Flow | Test cases |
|---|---|---|
| 1.2 | first run, steps 1-8 and the exits | SRC-FR-01..10, SRC-FR-12 |
| 1.3 | opening Sources, entry points, returning | SRC-LST-01, SRC-LST-02, SRC-LST-06, SRC-KEY-01 |
| 1.4 | switching, Enter vs Space, stale, uncached | SRC-SW-01..06, SRC-SW-10, SRC-UI-11 |
| 1.5 | adding from Sources | SRC-LBL-08, SRC-FR-02 (from `sources`: return to `sources` with the cursor on the new row, transient `Added 127.0.0.1 - 8 channels in 3 groups`, the new source active), SRC-UI-14 |
| 1.6 | editing: label-only, EPG-only, playlist URL, Xtream-built | SRC-LBL-03..07, SRC-XT-05, SRC-CLI-08, SRC-H12 |
| 1.7 | removing, confirm, active removed, last removed | SRC-RM-01..09 |
| 1.8 | Xtream form | SRC-XT-01..10 |
| 1.9 | modes and transitions table | SRC-KEY-02, SRC-KEY-05, SRC-KEY-10, SRC-FR-08, SRC-FR-09, SRC-RM-04 (each row of the table exercised at least once across SRC-H02, H06, H07, H10, H12) |

### 1.5 Keys (UX 2.1-2.5) -> test cases

| Key / gesture | Test cases |
|---|---|
| 2.1 `o`/`O` in list mode | SRC-KEY-01 |
| 2.2 `j`/`k`/arrows, PgDn/PgUp/Home/End, Enter, Space, `a`, `c`, `e`, `x`/`X`/Delete, `o`/Esc, ignored keys | SRC-KEY-02, SRC-LST-10, SRC-SW-01, SRC-SW-03 |
| 2.3 printable, Backspace, Ctrl+Backspace, Ctrl+U, Ctrl+V / Shift+Insert / middle click, Ctrl+A, arrows, Ctrl+R, Tab/Down, Shift+Tab/Up, Enter, Esc (plain and masked columns) | SRC-KEY-03, SRC-KEY-04, SRC-KEY-05, SRC-FR-06, SRC-FR-12, SRC-SEC-01..03 |
| 2.4 `confirmRemove` | SRC-KEY-06, SRC-RM-01, SRC-RM-05 |
| 2.5 mouse table | SRC-KEY-11, SRC-LST-02, SRC-LST-05, SRC-KEY-09 |

### 1.6 Wireframe states (UX 3) -> test cases and screenshot names

| Wireframe | Test case | Screenshot |
|---|---|---|
| 3.1.1 first run before paste | SRC-UI-01 | `sources-first-run` |
| 3.1.2 after paste, masked | SRC-UI-02 | `sources-first-run-masked` |
| 3.1.3 validation error | SRC-UI-03 | `sources-invalid` |
| 3.1.4 fetching / failed | SRC-UI-04 | `sources-fetching`, `sources-add-failed` |
| 3.1.5 success footer | SRC-UI-05 | `sources-first-run-done` |
| 3.1.6 saved sources, none active | SRC-UI-06 | `sources-none-active` |
| 3.2.1 three sources | SRC-UI-07 | `sources-list` |
| 3.2.2 one source | SRC-UI-07 | `sources-one` |
| 3.2.3 no sources | SRC-UI-07 | `sources-empty` |
| 3.2.4 narrow | SRC-LST-09 | `sources-narrow` (live, optional) |
| 3.2.5 row anatomy | SRC-LST-03 | crop of `sources-list` |
| 3.3.1 edit masked | SRC-UI-08 | `sources-edit` |
| 3.3.2 edit revealed | SRC-UI-08 | `sources-edit-revealed` |
| 3.3.3 edit narrow | SRC-UI-20 | `sources-edit-narrow` (live, optional) |
| 3.4 Xtream form / filled | SRC-UI-09 | `sources-xtream`, `sources-xtream-fetching` |
| 3.5 confirm dialog | SRC-UI-10 | `sources-confirm` |
| 3.6 switching transient | SRC-UI-11 | `sources-switched`, `sources-refreshing` |
| 3.7 pinned row | SRC-UI-12 | crop of `sources-guide-pinned` |

### 1.7 Microcopy (UX 5) -> test cases

| UX table | Test cases |
|---|---|
| 5.1 titles, labels, placeholders, link rows, buttons, prose, tooltips | SRC-UI-13 (grep) plus the screenshot of the state that shows each string |
| 5.2 source rows (right meta, detail segments) | SRC-LST-03, SRC-UI-17, SRC-UI-18 |
| 5.3 footer per mode and the transients | SRC-UI-14 |
| 5.4 validation errors | SRC-ERR-01, SRC-XT-03, SRC-LBL-05, SRC-LBL-06 |
| 5.5 fetch results | SRC-ERR-02, SRC-UI-04 |
| 5.6 default label and duplicates | SRC-LBL-01, SRC-LBL-02, SRC-MODEL-04 |
| 5.7 confirm dialog | SRC-RM-01, SRC-RM-03, SRC-UI-10 |
| 5.8 accessible names | SRC-A11Y-01, SRC-A11Y-06 |

### 1.8 Privacy rules (UX 6) -> test cases: SRC-PRIV-01..09 map one-to-one to 6.1-6.9 (table above); the sinks are swept in SRC-SEC-07 and SRC-H13.

### 1.9 Accessibility (UX 7) -> SRC-A11Y-01 (7.1), SRC-A11Y-02 (7.2), SRC-A11Y-03 (7.3), SRC-A11Y-04 (7.4); 7.4's multi-monitor note stays `not run` on this machine (QA.md TC-A11Y-04).

## 2. Automated inventory and the QA vector commands

Gate commands are QA.md section 2 plus, after the merge, the coverage greps:

```
scripts/check.sh
grep -c 'def test_' tests/test_*.py
node tests/Model.test.js | tail -3
grep -o 'qa-sources/[a-z0-9./-]*' tests/*.js tests/*.py tests/*.qml | sort | uniq -c   # QA fixtures the lanes chose to load
```

QA runs its own vectors against the merged Model.js with one-off node
commands (no test file is added to the lanes' suites; the fixtures are QA-owned):

```
# SRC-MODEL-02: every qa-source-urls.json record through validateSourceUrl (skip: true skipped; padTo honoured; field epg; existing for duplicates)
node -e '
const M=require("./Model.js");const cases=require("./tests/fixtures/qa-sources/qa-source-urls.json");let bad=0,dec=0;
for(const c of cases){if(c.skip)continue;let input=c.input;if(c.padTo)while(input.length<c.padTo)input+="a";
const r=c.existing?M.addSource(M.cloneState(M.emptyState(),{sources:c.existing.map(u=>({key:M.sourceKey(u),url:u,epgUrl:"",kind:"http",label:"x",labelCustom:false,origin:"guide",addedAt:1,lastUsed:1,fetchedAt:0,channelCount:0,groupCount:0}))}),{playlistUrl:input,epgUrl:"",label:"",origin:"guide"},2):M.validateSourceUrl(input,{kind:c.field||"playlist"});
const ok=c.ok?(r.ok&&(c.url===undefined||r.url===c.url)&&(c.host===undefined||r.host===c.host)):(!r.ok&&(r.code===c.code||r.code===c.archCode));
if(!ok){if(c.decision){dec++;console.log("DECISION",c.id,c.decision,JSON.stringify(r));}else{bad++;console.log("FAIL",c.id,JSON.stringify(r));}}}
console.log("failures",bad,"decision-flagged",dec);'

# SRC-MODEL-03: xtream-expect.json (V and E cases; D cases reported)
node -e '
const M=require("./Model.js");const f=require("./tests/fixtures/qa-sources/xtream-expect.json");let bad=0;
for(const c of f.cases){let s=c.server,u=c.username,p=c.password;if(c.padTo){if(c.padTo.username)while(u.length<c.padTo.username)u+="u";if(c.padTo.password)while(p.length<c.padTo.password)p+="p";if(c.padTo.server)while(s.length<c.padTo.server)s+="a";}
const r=M.xtreamUrls({server:s,username:u,password:p});const e=c.expect;
const ok=e.ok?(r.ok&&r.playlistUrl===e.playlistUrl&&r.epgUrl===e.epgUrl&&r.host===e.host&&M.sourceKey(r.playlistUrl)===e.key):(!r.ok&&(r.code===e.code||r.code===e.archCode));
if(!ok)console.log(c.decision?"DECISION":"FAIL",c.id,c.decision||"",JSON.stringify(r)),bad+=c.decision?0:1;}
console.log("failures",bad);'

# SRC-MODEL-04: qa-source-labels.json derive / validate (adjust function names to Lane 1's exports)
node -e '
const M=require("./Model.js");const f=require("./tests/fixtures/qa-sources/qa-source-labels.json");
for(const c of f.derive){const got=(M.deriveLabel||M.defaultSourceLabel)(c.url,c.kind,c.existing||[]);const want=c.expect;console.log(got===want?"ok":(got===c.archExpect?"ARCH":"FAIL"),c.id,JSON.stringify(got));}
for(const c of f.validate){let l=c.label;if(c.padTo)while(l.length<c.padTo)l+="a";if(c.repeat)l=c.repeat.char.repeat(c.repeat.count);const r=M.validateLabel(l,c.existing||[],c.selfLabel||"");console.log((r.ok===c.expect.ok&&(!c.expect.code||r.code===c.expect.code))?"ok":"FAIL",c.id,JSON.stringify(r));}'

# SRC-HELP-01: the same URL vectors through the helper mirror
python3 -c '
import json,sys;sys.path.insert(0,"tests");from helper_loader import load_helper;h=load_helper()
cases=json.load(open("tests/fixtures/qa-sources/qa-source-urls.json"));bad=0
for c in cases:
    if c.get("skip") or c.get("existing"): continue
    i=c["input"]
    if c.get("padTo"): i=i+"a"*(c["padTo"]-len(i))
    ok,code,msg,kind,url=h.validate_source_url(i)
    good=(ok and (c.get("url") is None or url==c["url"])) if c["ok"] else ((not ok) and code in (c.get("code"),c.get("archCode")))
    if not good: print("DECISION" if c.get("decision") else "FAIL",c["id"],ok,code,repr(url)); bad+=0 if c.get("decision") else 1
print("failures",bad)'
```

What QA expects the lanes' suites to contain is ARCH 8.3 verbatim; a missing
item is a P3 coverage defect unless it guards a P1/P2 behaviour (the
`bad_key` set, the `state show` redaction, `entryWith` keeping foreign keys,
`reconcileSources` never evicting the active source, `parseState` on tampered
records, and the `maskUrl` userinfo/fragment rules guard P2 behaviours).

## 3. Security section (SRC-SEC-01..24, summary of the method)

The bar is docs/SECURITY-REVIEW.md: argv only, playlist and clipboard data is
data, scheme allow-lists, private files, redaction at every sink, minimal
IPC. The new input surface adds three trust boundaries: the clipboard and the
keyboard (arbitrary text into three forms), the state file (URLs with
credentials at rest, keys that become directory names) and two helper verbs
that delete files. Section 1.1 SEC rows give the expected result per item;
this is the method:

1. Clipboard content: `wl-copy < tests/fixtures/qa-sources/paste/paste-multiline.txt`,
   `wl-copy < tests/fixtures/qa-sources/nonascii/paste-rtl.txt`, and
   `python3 -c "print('http://h.test/' + 'a'*102400, end='')" | wl-copy`, each
   followed by `run.sh key -M ctrl v -m ctrl` and again by
   `run.sh key -M shift -k Insert -m shift`; read the field back through
   `state()` (the harness dumps the guide's form values masked: Lane 2 must
   make `state()` print `maskUrl(value)` and the length, never the raw value)
   and compare with the vectors SRC-URL-002..008, 027, 033, 093, 110.
2. Schemes and paths: `run.sh key` types each vector of SRC-URL-041..056 and
   080..112 followed by Return; per vector record the result line, the absence
   of a helper process (`pgrep -f 'omarchy-iptv playlist'` in a 3 s loop) and
   the absence of a new directory under `cache/omarchy-iptv/sources/`.
3. Symlinked local playlists: `ln -s /proc/self/environ $SCRATCH/fixtures/env.m3u`,
   `ln -s $SCRATCH/fixtures/qa-src-a.m3u $SCRATCH/fixtures/link.m3u`; add both
   as paths; then `ln -sfn $SCRATCH/fixtures/qa-src-b.m3u $SCRATCH/fixtures/link.m3u`
   and press `r`.
4. Labels: type each `qa-source-labels.json` validate vector as the label of
   an add; screenshot the row; `notifications.log` unchanged; `jq .sources[].label state.json`.
5. Sinks: the SRC-H13 sweep (section 8) greps every sink for the needles;
   the expected-hit list is `state.json`, `channels.json` and the helper
   probe argv.
6. Cache keys: SRC-H15 runs the helper by hand with the `bad_key` set and a
   canary; every call must leave the canary and every other directory intact.
7. Files: `stat -c '%a %n'` over the scratch cache and state trees after
   every scenario (`find $SCRATCH/cache $SCRATCH/state -exec stat -c '%a %n' {} +`).
8. Cap and cancel: SRC-H11 and SRC-H14.
9. Static greps of SRC-SEC-12, 13, 24 and QA.md SEC-01/02/18 on the merged tree.

## 4. Migration section (SRC-MIG-01..10, summary)

Fixtures: `state-v1.json` (3 favorites, 3 recents, `lastPlayed`; ids from
`qa-src-a.m3u`) and `legacy-cache/` (`channels.json` + `playlist-status.json`
produced by the shipped v0.1.0 helper from `qa-src-a.m3u`, `generatedAt` /
`fetchedAt` pinned to T0 = 1789244100, `durationMs` 12, `sourceHost: "local
file"`). The seed (SRC-H01) copies both into the scratch XDG tree with the
v0.1.0 modes (dirs 700, files 600) and optionally re-stamps them to `now` so
no refresh runs and the moved bytes can be compared. Expected after the first
start with `--playlist <A>`: everything in SRC-MIG-01..03; the second start
proves SRC-MIG-04; the `--playlist none` and `garbage{{{` variants prove
SRC-MIG-05 and 08; SRC-MIG-07 is a node/python check against the v0.1.0 tag;
SRC-MIG-10 is the live machine (section 9.2), whose state (v1, 5 recents,
legacy cache of `us.m3u`) is exactly the fixture shape at scale.

## 5. Performance section (SRC-PERF-01..07, summary)

Method as QA.md section 4 (harness, `date +%s%N`, `hyprctl layers -j` poll,
node micro-benchmarks) plus the `OMARCHY_IPTV_DEBUG=1` switch lines Lane 2
adds. Inputs: `scripts/gen-playlist.py --channels 10000 --groups 400 --seed 1
--out $SCRATCH/fixtures/gen-10k.m3u` as source 2, `qa-src-a.m3u` as source 1,
`gen-real.m3u` (1,500) for the typical number; 50 records generated by the
scenario helper (`scripts/qa-sources-scenarios.sh print SRC-H16` shows the
python that writes them, all `127.0.0.1:9` URLs so nothing is fetched).
Record median/max of 5 switches each way (budget 150 ms), the open time with
50 records, the state file sizes (typical and worst case), the prune argv
length, and the RSS before/after 20 switches (informational).

## 6. Harness verbs and the fake host (Lane 2, precondition)

The scenarios need the verbs ARCH 8.4 assigns to Lane 2 on the harness
`IpcHandler` (target `harness`): `addSource(playlistUrl, epgUrl, label)`,
`updateSource(id, json)`, `removeSource(id)`, `switchSource(id)`,
`xtream(server, username, password)`, `sources()` (JSON of `service.sources`),
`activeCache()` (path), and `state()` extended with `activeSourceKey`,
`probing`, `switching`, `sourceErrors`, the guide `mode`, `returnMode`, the
focused field and the form values in masked form with their lengths; plus
`run.sh --source2 SRC` printing `scheme://host` only. QA additionally asks for
(section 10, SRC-DEC-21): `cancelProbe()`, `editMasked(id)` (returns
`sourceForEdit(id)` with both URLs already passed through `maskUrl`, never the
raw strings), `signals()` (the last 20 signal payloads), and
`failPersist(bool)`. **[v0.5]** `failPersist true` no longer makes
`updateEntryInline` return `false`; it takes the function **off the fake shell
api** entirely, the way a host that cannot rewrite our bar entry leaves it,
because a `false` return from a writable entry is the host's `!dirty` branch
and means "already stored", i.e. success. Two verbs were added with the
D-LIVE-20 fix: `setStored(key, value)` stores a setting without the user-config
re-read (the window in which the host holds a value the plugin has not been
handed), and `hostEntry()` returns `{"stored": "<key>", "published": "<key>"}`
- what the host has stored for our entry versus what it has published to the
plugin, as 8-hex source keys, never URLs (S-08).

**[v0.5] The fake host must NOT feed a plugin's own write back to the plugin.**
The instruction that used to stand here - that the fake `updateEntryInline`
apply the entry to `fakeShell.barConfig` and `barLoader.item.settings` so the
service observes its own writes - is what masked D-LIVE-20 and D-LIVE-21
through two full QA passes. The real host does not do that. Corrected at
`1c29a4c`; `scripts/dev-harness/shell.qml` now reproduces
`/usr/share/omarchy/shell/shell.qml` in its **shape and its declaration
order**:

```
  shellConfig                      (a QtObject property, host truth)
  onShellConfigChanged             -> syncPluginApis() -> fakeShell.barConfig
  readonly property barConfig      : shellConfig.bar          (read by the above)
```

A QML change handler runs **before** the bindings that depend on the same
property re-evaluate, so `syncPluginApis()` publishes the bar of the
*previous* `shellConfig`: a plugin is handed `shell.json` one write late. An
external write is flushed by the assignment after it (the user-config
`FileView` re-reads the foreign change, modelled by `hostReloadTimer` ->
`applyShellConfig()`); a plugin's **own** write is the last assignment there
is, so its echo never arrives at all. The fake `updateEntryInline` therefore
rewrites the entry in a clone, compares with `JSON.stringify`, returns
`false` **without persisting** when nothing changed (the host's `!dirty`
branch) and otherwise calls `persistShellConfig` - and nothing anywhere hands
the plugin its own write. The keys-only log line (S-08) stays.

A plugin must consequently apply its own successful write itself and never
wait for the echo (`Service.qml` `ownWrite` / `Model.settingsWithOwnWrite`).
Any case that asserts on the effect of a plugin-initiated settings write is
only meaningful against this ordering - keep it intact. `ipc hostEntry` shows
the two sides, and the scenario's `== D-LIVE-20` block asserts that a switch
takes effect **while** the published bar still names the previous source.
Measured by QA on 2026-09-13 by checking the pre-fix `Service.qml`
(`d153fe9`) into a scratch copy of `845d445`: `run.sh scenario` is 61 pass /
0 fail against the fixed service and **44 pass / 23 fail** against the
pre-fix one (H2, H6/H8, the whole `D-LIVE-20` block, H7 / D-LIVE-21 and the
SR25 block), where the old fake passed everything.
`scripts/qa-sources-scenarios.sh check-harness` greps for the verbs; the
apply it used to demand is gone.

The notification shim of the M1 pass (a PATH directory with an executable
`omarchy-notification-send` that appends its argv as a JSON line to
`logs/notifications.log`) is reused unchanged; `Model.notifyArgv` resolves the
command by name.

## 7. Fixture catalogue (`tests/fixtures/qa-sources/`)

All files are small, deterministic and ASCII except `nonascii/paste-rtl.txt`
(raw UTF-8, kept in a subdirectory like `tests/fixtures/qa-nonascii/`;
`scripts/check.sh` greps only regular files directly under `tests/fixtures/`).
Nothing is generated by hand at run time except the 100 KB paste, the 50-record
state and the 10k playlist, whose commands are in the scenarios.

| File | Purpose | Expected |
|---|---|---|
| `qa-src-a.m3u` | source A: 8 channels in 3 groups (`Alpha News`, `Alpha Sports`, `Alpha Kids`), all streams at `127.0.0.1:9`; `t:qa.shared` shared with B; `u:502142db` only here; `url-tvg` hint at the discard port | served as `http://127.0.0.1:8765/qa-src-a.m3u` -> key `584a58e5`; probe line `8 channels in 3 groups`; ids `t:qa.a.news1`, `t:qa.a.news2`, `t:qa.shared`, `t:qa.a.sport1`, `t:qa.a.sport2`, `t:qa.a.kids1`, `u:502142db`, `t:qa.a.kids3` (verified through the shipped helper) |
| `qa-src-b.m3u` | source B: 5 channels in 2 groups (`Bravo Movies`, `Bravo Docs`); `t:qa.shared` under another group; `u:3338d912` only here; no EPG | served -> key `733cf68c`; `5 channels in 2 groups`; after a switch from A the Favorites scope shows `Shared Channel` only |
| `qa-src-userinfo.m3u` | source C reached through a URL with userinfo; one credentialed stream URL; one empty title with a credentialed URL | add as `http://qa-user:qa-secret@127.0.0.1:8765/qa-src-userinfo.m3u` -> key `25b70358`; `python3 -m http.server` ignores the `Authorization` header the helper derives, so the probe succeeds: `3 channels in 1 group`; row host `127.0.0.1`; edit field `http://****@127.0.0.1:8765/qa-src-userinfo.m3u`; needles `qa-user`, `qa-secret`, `cu:cs` absent from every sink; third channel named `Channel 3` |
| `qa-src-a.xml` | XMLTV pair for A: evergreen programmes (2026-01-01Z..2030-01-01Z) on `qa.a.news1` / `qa.a.news2`, a T0-pinned now/next pair on `qa.shared`, one programme for a B-only id | at the real clock: `Now: Alpha Evergreen` (no `Next:`) on the two news rows, nothing on `qa.shared`; with `--now 1789244100`: `qa.shared` now `Shared Now` / next `Shared Next`; warning `1 programmes for channels not in the playlist dropped`; files land in `sources/<key>/` |
| `xtream/get.php`, `xtream/xmltv.php` | the Xtream probe routes: the fixture server drops the query string, so `/get.php?username=user&password=pa%20ss&type=m3u_plus&output=ts` serves the M3U (4 channels in 2 groups, `Xtream Live`, `Xtream VOD`) and `/xmltv.php?...` the XMLTV (two evergreen rows) | server `http://127.0.0.1:8765`, username `user`, password `pa ss` -> key `6e90a03e`; row detail `active - 127.0.0.1 - Xtream - 4 channels in 2 groups - EPG` |
| `state-v1.json` | v1 state with 3 favorites, 3 recents, `lastPlayed`, all ids from A | migrates to v2 with the lists intact (SRC-MIG-01) |
| `legacy-cache/channels.json`, `legacy-cache/playlist-status.json` | the v0.1.0 single-cache layout for A (helper output, stamps pinned to T0, `durationMs` 12) | moved into `sources/<key>/` by `cache migrate`; counts 8 / 3 copied into the migrated record |
| `xtream-expect.json` | Xtream building vectors V01-V14, errors E01-E09, decisions D01-D05 (see the file header for the field meanings; `padTo` pads a field) | SRC-XT-02, SRC-XT-03, SRC-MODEL-03 |
| `qa-source-urls.json` | 100+ adversarial validation vectors beyond ARCH appendix A: control characters, NBSP, BOM, zero-width and bidi, IDN, IPv6 literals, ports (leading zeros, 65536), userinfo forms, traversal, `~`, `file:` forms, refused schemes, whitespace, length caps with `padTo`, EPG field, duplicates with `existing` | SRC-MODEL-02, SRC-HELP-01, SRC-ERR-01, SRC-SEC-03..05; must agree with `tests/fixtures/source-urls.json` once Lane 1 lands it (every vector in both files carries the same verdict; the `decision` records are reconciled by the lead first) |
| `qa-source-labels.json` | label derivation (`derive`), typed-label validation (`validate`) incl. hostile labels and the 64 cap | SRC-LBL-01/02/05/06/09, SRC-SEC-06, SRC-MODEL-04 |
| `paste/paste-multiline.txt` | clipboard content: two lines, leading spaces, a TAB before the newline | one line `http://127.0.0.1:8765/qa-src-a.m3u` in the field (SRC-SEC-01) |
| `nonascii/paste-rtl.txt` | clipboard content: a leading NBSP, the URL with a U+202E / U+202C reversed segment in the path, a U+200B before the file name, then U+FEFF, NBSP, a space and a newline (written byte-exactly by a script; 55 characters) | SRC-SEC-03; NBSP and the newline are trimmed, the bidi and zero-width characters and the trailing U+FEFF depend on SRC-DEC-05 (record what the merged code does) |

Run any M3U or XMLTV through the shipped helper into a scratch per-source
directory (never the real cache):

```
S=/tmp/claude-1000/omarchy-iptv-qa4/cache          # any scratch path
python3 bin/omarchy-iptv playlist --url "file://$PWD/tests/fixtures/qa-sources/qa-src-a.m3u" --cache-dir "$S/sources/584a58e5"
python3 bin/omarchy-iptv epg --url "$PWD/tests/fixtures/qa-sources/qa-src-a.xml" --cache-dir "$S/sources/584a58e5" --force --now 1789244100
jq -c '.channels[] | {id, name, group}' "$S/sources/584a58e5/channels.json"
jq -c .channels "$S/sources/584a58e5/epg-now.json"
scripts/qa-sources-scenarios.sh fixtures --apply             # the same, for every fixture, plus JSON/XML parsing
scripts/qa-sources-scenarios.sh key http://127.0.0.1:8765/qa-src-a.m3u   # -> 584a58e5
```

## 8. Harness runbook per scenario

Conventions from the M1 passes (QA-RESULTS.md section 1): `H=scripts/dev-harness/run.sh`,
`export OMARCHY_IPTV_HARNESS_DIR=/tmp/claude-1000/omarchy-iptv-qa4/harness`
(short, the AF_UNIX path limit), the notification shim first on `PATH`, the
harness started in the background with `--timeout 0` and killed by PID
between runs (`start.sh` / `stop.sh` of the M1 pass, or `run.sh --timeout N`
for short runs), screenshots with `$H shot <name>` (grim), keys with `$H key`
(wtype; `-k space`, `-M ctrl v -m ctrl` for chords, `-d 1` not `-d 0`),
state through `$H ipc state | jq`. `scripts/qa-sources-scenarios.sh print
SRC-Hnn` prints exactly the commands below with the paths filled in;
`run SRC-Hnn --apply` executes the deterministic ones and prints the
EXPECT lines; it refuses to run when the scratch directory resolves into a
real plugin location and it never calls `omarchy plugin|bar|theme`,
`hyprctl dispatch|reload|keyword` or sudo.

**[corrected, cleanup round] What a green run of this script used to mean.**
Three things in it could not fail, so a transcript full of EXPECT lines was
not evidence:

- `harness_start` has returned 1 after 30 s since it was written, and all 19
  call sites invoked it bare in a file with no `set -e`. All sixteen SRC-H*
  scenarios then executed every remaining step against a **dead harness**,
  printing empty output under each EXPECT line exactly as a good run prints
  its answers. Fixed: every call site is guarded, a `SETUP FAILED` banner is
  printed, and the scenario exits non-zero instead of being reported.
- `check-harness) cmd_check_harness; exit 0` - the capability gate printed
  `MISSING` lines and exited green. It counts now and exits 1.
- Two of its gates were satisfied by a **comment**: a bare grep for
  `validateSourceUrl|sourceView|xtreamUrls` in `Model.js` and for
  `switchSource|activeCacheDir` in `Service.qml`. The Model.js gate loads the
  module in node and requires the three to be callable; the Service.qml gate
  anchors on the definition. (`have_verb` was never comment-satisfiable and is
  unchanged.)

**[corrected, cleanup round's last wave] No SRC-H scenario has ever been run
against another tree, and this script cannot do it.** `qa-sources-scenarios.sh`
has no `baseline` verb - its player sibling does - and its `HELPER` is pinned
to the repository root, so even if one were added every helper step would keep
running today's helper. CLAUDE.md rule 11 evidence for this plan therefore
rests **entirely** on `tests/` and on the mutations recorded there; the SRC-H
transcripts are procedure, not before/after. Say so when quoting them. The
player script's `HELPER` was unpinned this wave (`OMARCHY_IPTV_PLUGIN_ROOT`)
and the same one-line change is what this one needs first.

**The shared predicate library gained one more three-way answer.**
`scripts/qa-lib.sh` now carries `qa_delta <before> <after>`, with the sentinel
`NODELTA`, for every check shaped as "this counter moved by exactly N".
`$(( $(counter) - before ))` dies as an arithmetic **expansion** the moment
the counter answers `NOFIELD`, `NOSTATE` or `""`, and a failed expansion stops
bash from running the assertion the substitution belonged to - no pass, no
fail, exit 0. That is D-PLY-9's shape, and anything read over the IPC has far
more ways to answer non-numerically than a grep has. Use it for any
before/after pair in a sources scenario, and treat `NODELTA` the way
`qa_value` already treats the others: never a pass.

The same round fixed the privacy sweep at the end of
`scripts/dev-harness/sources-scenario.sh`, which is the machine half of the
SRC-H13 / SRC-PRIV evidence. `! grep -E <labels> "$LOG" | grep -qE "://"`
passed on an **empty log** and on a log leaking a credentialed URL on a line
carrying none of the three labels; its sibling, "IPC status carries no URL",
passed outright when the IPC was dead, because an empty answer contains no
`://`. Both are three-way now (clean / leak / **vacuous**, and vacuous is a
failure), the harness is asserted alive before the sweep runs, and its
`--timeout` was raised from 120 s - less than the scenario's own waits sum to,
which is exactly how the sweep came to run against a killed harness.

Common seed (every scenario starts here unless it says otherwise):

```
export OMARCHY_IPTV_HARNESS_DIR=/tmp/claude-1000/omarchy-iptv-qa4/harness; S=$OMARCHY_IPTV_HARNESS_DIR
H=scripts/dev-harness/run.sh; F=tests/fixtures/qa-sources
$H clean
mkdir -p "$S/fixtures" && cp "$F"/qa-src-*.m3u "$F"/qa-src-a.xml "$F"/xtream/get.php "$F"/xtream/xmltv.php "$S/fixtures/"
A=http://127.0.0.1:8765/qa-src-a.m3u  B=http://127.0.0.1:8765/qa-src-b.m3u  C="http://qa-user:qa-secret@127.0.0.1:8765/qa-src-userinfo.m3u"
KA=584a58e5 KB=733cf68c KC=25b70358 KX=6e90a03e
# start (background, --serve hosts $S/fixtures on 127.0.0.1:8765 and generates test.ts once):
$H --open --serve --keep --timeout 0 --playlist "$A" > "$S/logs/run.log" 2>&1 &   # note the pid; poll `$H ipc state` until it answers
```

| # | Scenario | Steps (exact) | Expect (cases) |
|---|---|---|---|
| SRC-H01 | Migration from a v1 install | seed without starting; `mkdir -p $S/cache/omarchy-iptv $S/state/omarchy-iptv; cp $F/legacy-cache/*.json $S/cache/omarchy-iptv/; cp $F/state-v1.json $S/state/omarchy-iptv/state.json; chmod 700 $S/cache/omarchy-iptv $S/state/omarchy-iptv; chmod 600 $S/cache/omarchy-iptv/*.json $S/state/omarchy-iptv/state.json; sha256sum $S/cache/omarchy-iptv/*.json > $S/logs/legacy.sha`; optional fresh stamps: `python3 - <<'PY'` (the helper prints it: `run SRC-H01 --apply --fresh`) sets `fetchedAt`/`generatedAt` to now; start with `--playlist "$A"`; wait 3 s; `jq '{version,cacheLayout,favorites,recents,lastPlayed,sources}' $S/state/omarchy-iptv/state.json`; `ls -la $S/cache/omarchy-iptv $S/cache/omarchy-iptv/sources/$KA`; `find $S/cache $S/state -exec stat -c '%a %n' {} +`; `(cd $S/cache/omarchy-iptv/sources/$KA && sha256sum channels.json playlist-status.json)` vs `legacy.sha`; `grep -E 'cache migrate|cache prune|playlist:' $S/logs/run.log`; `$H ipc state | jq '.guide.rows, .service'`; `$H shot sources-migrated`; stop; start again with `--keep` and the same URL; `grep -c 'cache migrate' $S/logs/run2.log`; variants: `--playlist none` (legacy deleted, `sources: []`), `printf 'garbage{{{' > state.json` | SRC-MIG-01..06, 08, SRC-SEC-09, SRC-SEC-22, SRC-SVC-04, SRC-PERF-05 |
| SRC-H02 | First run (S1) | start with `--playlist none`; `$H shot sources-first-run`; `$H ipc state | jq '.guide.mode, .guide.form'`; `$H key o r f x s` (text appears, nothing acts); `$H key -M ctrl u -m ctrl`; `$H key "$S/fixtures/qa-src-a.m3u"`; `$H key -k Return`; poll `state` every 250 ms: `Reading the file...` then mode `search`, `rows 8`, footer `8 channels in 3 groups`; `$H shot sources-first-run-done`; `grep updateEntryInline $S/logs/run.log` (once, keys only); `$H ipc sources | jq`; `$H ipc activeCache`; `jq .sources $S/state/omarchy-iptv/state.json`; repeat from `--playlist none` with `$H key "$A"` then `-k Tab`, `http://127.0.0.1:8765/qa-src-a.xml`, `-k Return` (served URL + EPG: `Fetching from 127.0.0.1...`, then `Now: Alpha Evergreen` rows, epg files under `sources/$KA/`); Esc rules: type text, `-k Escape` (cleared), `-k Tab`, type in EPG, `-k Escape` x2 (focus moves, clears), `-k Escape` (closes); focus order with `-k Tab` x5 reading `state().guide.form.focus` | SRC-FR-01..04, 06, 10, 12, SRC-LBL-08, SRC-UI-01, 05, SRC-KEY-07, SRC-A11Y-03 |
| SRC-H03 | Invalid input (S8) | in the first-run form, for each of `ftp://x`, `javascript:alert(1)`, `data:text/plain,x`, `provider.test/list`, `./list.m3u`, `~/tv/list.m3u`, `/proc/self/environ`, `http://h .test/`, `http://`, `python3 -c "print('http://h.test/'+'a'*3000)"` output, `""`: `$H key -M ctrl u -m ctrl`, `$H key "<vector>"`, `$H key -k Return`, `$H ipc state | jq .guide.form.error`, `pgrep -fc 'omarchy-iptv playlist'` (0), `ls $S/cache/omarchy-iptv/sources` (unchanged); `$H shot sources-invalid` on the `scheme` case; then type one more character and confirm the error clears; EPG variants with `-k Tab` first | SRC-ERR-01, SRC-ERR-04, SRC-UI-03, SRC-SEC-04, SRC-SEC-05 |
| SRC-H04 | Paste (D9) | `wl-copy -- "$A"`; `$H key -M ctrl v -m ctrl`; `$H ipc state | jq .guide.form.values` (masked rendering + length); `$H key -M ctrl u -m ctrl`; `wl-copy -- "$A"`; `$H key -M shift -k Insert -m shift`; same check; `wl-copy < $F/paste/paste-multiline.txt` + Ctrl+V -> one line, length 34; `wl-copy < $F/nonascii/paste-rtl.txt` + Ctrl+V -> per SRC-DEC-05, `$H shot sources-paste-rtl`; `python3 -c "print('http://h.test/' + 'a'*102400, end='')" \| wl-copy` + Ctrl+V -> length 2048, `$H shot sources-paste-100k` within 1 s, `-k Return` -> `Too long - max 2,048 characters`, no helper; `wl-copy -- "$C"` + Ctrl+V -> masked at once `http://****@127.0.0.1:8765/qa-src-userinfo.m3u`, eye shown, `$H shot sources-first-run-masked`; paste over a masked field replaces and re-masks; if both chords paste nothing -> Lane 1 flips `pasteViaProcess`, rerun | SRC-FR-12, SRC-KEY-03, SRC-KEY-04, SRC-UI-02, SRC-PRIV-06, SRC-SEC-01..03 |
| SRC-H05 | Add + fetch failure keeps the active source (S8) | start with `--playlist "$A"`; `$H ipc addSource http://127.0.0.1:9/x.m3u "" ""` -> `{ok:true,...}`; poll `state` (`probing` true then false); `$H ipc signals` -> `sourceProbeFinished {ok:false, reason:"Connection refused", host:"127.0.0.1"}`; `$H ipc state | jq '.service.activeSourceKey, .guide.rows'` (KA, 8); `grep -c updateEntryInline $S/logs/run.log` unchanged; `$H ipc sources | jq` (per SRC-DEC-13: a `not loaded yet` row or none); from the guide: `$H key -k Tab a`, type `http://127.0.0.1:8765/missing.m3u`, Return -> `HTTP 404 Not Found from 127.0.0.1`, `$H shot sources-add-failed`; Return again -> re-probe, same key, no duplicate; Xtream: `$H ipc xtream http://127.0.0.1:9 u p` -> `Connection refused from 127.0.0.1`; served `qa-not-m3u.html` -> `Not an M3U playlist from 127.0.0.1`; `qa-empty.m3u` -> `Playlist has no channels from 127.0.0.1` | SRC-FR-05, SRC-ERR-02, 03, 08, SRC-UI-04, SRC-XT-10, SRC-SEC-15, SRC-SVC-03 |
| SRC-H06 | Switch (S3) and the list (S2) | start with `--playlist "$A"` and `--keep` over the SRC-H01 seed (favorites present); `$H ipc addSource "$B" "" ""` (probe, becomes active); `$H ipc addSource "$S/fixtures/qa-src-userinfo.m3u" "" "Charlie"` (a path source); `$H ipc set playlistUrl "$A"`; `$H ipc open '{}'`; `$H key -k Tab o`; `$H shot sources-list`; `$H ipc state | jq '.guide.mode, .guide.cursorIndex'`; `$H ipc sources | jq`; keys: `j j k`, `-k Home`, `-k End`, `h l r s f / 4` (nothing), `-k Tab` (nothing); `$H key j` then `-k Return` -> switched to B: `state` (`activeSourceKey` KB, rows 5, mode `search`, footer `Switched to 127.0.0.1 2 - 5 channels` or per SRC-DEC-11), `$H ipc activeCache` (`.../sources/$KB`), `grep updateEntryInline` (+1, keys only), `$H shot sources-switched`; favorites scope: `$H ipc setScope favorites` -> 1 row `Shared Channel`; `jq .favorites state.json` still 3; `o`, `-k space` on A -> stays in `sources`, glyph moves, `$H shot sources-space`; Enter on the active row -> no helper, no `updateEntryInline`; stale stamps (`touch -d '10 hours ago'` on `sources/$KB/playlist-status.json` is not enough: edit `fetchedAt`) -> `Refreshing...` then silent success; fresh stamps -> no helper (3 s `pgrep` loop); with `--serve`: play `Harness Live` from a served fixture source, switch, `hyprctl clients -j` same pid, `$H ipc zap 1` -> `no`; timing lines from `OMARCHY_IPTV_DEBUG=1` | SRC-LST-01..04, 06..08, 10..12, SRC-SW-01..05, 07..10, SRC-KEY-01, 02, 08, 10, SRC-UI-07, 11, 14, SRC-LBL-09, SRC-SEC-18, SRC-SVC-08 |
| SRC-H07 | Remove (S7) | with three sources (H06 state), cursor on B (inactive): `$H key x`, `$H shot sources-confirm`, `-k Escape` (cancel, `j` moves), `x`, `-k Left`, `-k Right`, `-k Return` -> removed: `ls $S/cache/omarchy-iptv/sources` (KB gone, others intact), `jq .sources state.json`, footer `Removed <label>`; cursor on the active A: `x` -> message variant, Return -> `updateEntryInline ... playlist (none) epg (none)`, `state` mode still `sources`, `$H ipc state | jq .service.configured` false, behind: `-k Escape` -> first-run form with `Saved sources (1)`, `$H shot sources-none-active`; `-k Tab` x2, Return -> Sources again; remove the last: Sources closes, first-run form focused; `$H shot sources-empty` (before the last removal, with an empty list reachable by removing all: header `No sources`); three quick removals in a row (queue); `x` on an action row; with `--serve` remove the playing source -> mpv untouched | SRC-RM-01..05, 07..09, SRC-FR-08, SRC-UI-06, 07, 10, SRC-KEY-06, 10, SRC-SEC-19, SRC-SVC-05, 07 |
| SRC-H08 | Switch timing (PERF) | `scripts/gen-playlist.py --channels 10000 --groups 400 --seed 1 --out $S/fixtures/gen-10k.m3u`; sources A and `http://127.0.0.1:8765/gen-10k.m3u` both fetched (fresh stamps); `OMARCHY_IPTV_DEBUG=1` in the harness environment; `for i in 1 2 3 4 5; do $H ipc switchSource $K10; sleep 2; $H ipc switchSource $KA; sleep 2; done`; `grep 'omarchy-iptv switch' $S/logs/run.log`; report median/max each way; repeat with `gen-real.m3u`; `ps -o rss= -p <harness pid>` before/after | SRC-PERF-01, SRC-PERF-04 (with the QA.md PERF-02 method and 50 records from H16) |
| SRC-H09 | CLI parity (S5) | Sources open on A: `$H ipc set playlistUrl "$B"` -> row appears (`origin cli` in state.json, label derived, `not loaded yet` then `5 channels`), active, first fetch (`playlist:` line once); `$H ipc set playlistUrl "$A"` -> no new record, active back; `$H ipc set epgUrl http://127.0.0.1:8765/qa-src-a.xml` -> epg helper within 300 ms, `epgUrl` adopted in the record; invalid: `$H ipc set playlistUrl ftp://x`, `javascript:alert(1)`, `/proc/self/environ`, a 3,000-character string -> `settingsInvalid`, empty error state (`emptyKind error`, reason, host `""`), `pgrep` 0, no record; `$H ipc set playlistUrl ''` -> first-run, `jq '.sources|length'` unchanged; `$H ipc state | jq .service` (`activeSource`, `sources[]`), `grep -c '://'` = 0 | SRC-CLI-01..04, 06, 08, SRC-FR-11, SRC-SW-06, SRC-SEC-17 |
| SRC-H10 | Xtream (S6) | `$H ipc xtream http://127.0.0.1:8765 user "pa ss"` -> `{ok:true,id:"6e90a03e"}`, probe, `4 channels in 2 groups`, row `active - 127.0.0.1 - Xtream - 4 channels in 2 groups - EPG`, epg from `xmltv.php` (`Now: Xtream Evergreen One`); `$H ipc editMasked 6e90a03e` -> both masked strings of SRC-XT-05; from the guide: `o`, `c`, `$H shot sources-xtream`, `-k Tab` order `Label -> Server -> Username -> Password -> Save -> Cancel`, type server/user/password, `$H shot sources-xtream-filled` (echo characters), Return, `$H shot sources-xtream-fetching`; reopen `c`: fields empty; duplicate login -> `Already in Sources as "127.0.0.1"`; errors: `$H ipc xtream "" u p`, `ftp://h.test`, `http://h.test/get.php?username=a`, `http://h.test "" p`, `http://h.test u ""`; from first run: `--playlist none`, `-k Tab` x2 (`Use Xtream login instead`), Return, fill, Return -> search mode with `4 channels in 2 groups`; Esc semantics; needles per H13 | SRC-XT-01..09, SRC-FR-09, SRC-LBL-08, SRC-UI-09, SRC-PRIV-05, SRC-SEC-16 |
| SRC-H11 | Duplicate, label, cap | `$H ipc addSource "HTTP://127.0.0.1:8765/qa-src-a.m3u" "" ""` -> `duplicate` with `id` KA; `.../qa-src-a.m3u#x`, `.../qa-src-a.m3u?` -> `duplicate` (SRC-DEC-04); `$H ipc addSource "$B" "" "Alpha"` where A's label is `Alpha` -> `label_taken`; a second source on host `127.0.0.1` -> derived label suffix per SRC-DEC-11; 65-character label -> `label_too_long`; cap: `scripts/qa-sources-scenarios.sh print SRC-H16` writes 49 records, start with `--keep`, `$H ipc addSource http://127.0.0.1:9/50.m3u "" ""` (50th ok, probe fails), `.../51.m3u` -> `too_many`, `canAddSource` false, `a` in Sources per SRC-DEC-14; CLI 51st -> eviction of the LRU non-active (`ls sources` before/after, console line with the key only) | SRC-LBL-02, 05, 06, SRC-ERR-05, SRC-CLI-05, SRC-XT-09, SRC-SEC-10 |
| SRC-H12 | Edit (S4) | `$H ipc updateSource $KB '{"label":"Bravo"}'` -> immediate (`Saved`, no helper, `labelCustom true`); `$H ipc updateSource $KB '{"epgUrl":"http://127.0.0.1:8765/qa-src-a.xml"}'` -> immediate, epg helper if B is active; `$H ipc updateSource $KB '{"playlistUrl":"http://127.0.0.1:8765/qa-src-userinfo.m3u"}'` -> probe, success: new id, `sources/$KB` removed, label `Bravo` kept, `addedAt` kept; failure variant (`http://127.0.0.1:8765/missing.m3u`) -> old record and directory intact, error shown; from the guide: `o`, `e` on the Xtream source: `$H shot sources-edit` (masked, `Label` focused), `-k Tab`, `-M ctrl r -m ctrl` -> `$H shot sources-edit-revealed` (raw, eye-off, footer `Ctrl+R hide`), `-k Tab` re-masks, back `-M shift -k Tab -m shift`, masked-field keys: `-k Right` (no-op, footer `Ctrl+R reveal`), `-k BackSpace` (cleared), `-M ctrl u -m ctrl`, type `x` (replaces), `-M ctrl a -m ctrl` no-op while masked; `-k Escape` -> back to `sources`, nothing kept; `e` then Return with the same values -> `Saved`, no helper | SRC-LBL-03, 04, 07, SRC-KEY-03..05, SRC-UI-08, SRC-PRIV-02, SRC-CLI-02 |
| SRC-H13 | Privacy and security sweep (all sinks) | with sources A, C (`$C`, userinfo) and the Xtream login present and each probed at least once, and a failed add of `http://qa-user:qa-secret@127.0.0.1:9/x.m3u`: collect `$H ipc sources > logs/sources.json`, `$H ipc state > logs/state.json`, `$H ipc widget > logs/widget.json`, `$H ipc tooltip`, the service `status` through the harness (`state().service`), `python3 bin/omarchy-iptv state --state-dir $S/state/omarchy-iptv show > logs/state-show.json`, `cp $S/logs/run.log logs/console.log`, `logs/notifications.log`, screenshots of the list, the guide footer after each transient, the edit form masked; `grep -nE 'qa-user|qa-secret|pa ss|pa%20ss|username=user|password=|cu:cs|/live/' logs/*.json logs/console.log logs/notifications.log` -> 0 lines; `grep -c '://' logs/sources.json logs/state-show.json` -> 0; expected hits only in `$S/state/omarchy-iptv/state.json` and `sources/*/channels.json`; during a probe `ps -o args= -p $(pgrep -f 'omarchy-iptv playlist')` shows the URL (expected, record) | SRC-LST-11, SRC-PRIV-01..08, SRC-SEC-07, 14, 15, 16, 17, SRC-CLI-06 |
| SRC-H14 | Cancel, busy, deadlines | `$H ipc addSource http://10.255.255.1/x.m3u "" ""` (blackhole, 20 s timeout) then within 2 s `$H ipc addSource "$B" "" ""` -> `busy`, `$H ipc switchSource $KA` -> `busy`, `$H ipc removeSource <probing id>` -> `busy`; `$H ipc cancelProbe` (or `-k Escape` in the form) -> `pgrep -fc 'omarchy-iptv playlist'` 0 within 1 s, `find $S/cache -name '.tmp-*'` empty, `ls $S/cache/omarchy-iptv/sources` (no new key or an empty dir), `$H ipc state | jq .guide.form` (thawed, values kept); edit-URL cancel -> original intact; trickle server (M1 pass `s05`) as a source -> `Timed out from 127.0.0.1` at ~60 s; action before `stateLoaded` (call `addSource` immediately after start) -> `not_ready`; optional `$H ipc failPersist true` then `switchSource` -> `sourcesPersistFailed`, harness log of the fallback argv keys only | SRC-FR-07, SRC-ERR-06, 07, 09, SRC-RM-06, SRC-SEC-11, 20, SRC-SVC-02, 06, SRC-PERF-06 |
| SRC-H15 | Cache verbs and key safety (helper CLI) | no harness needed: `C=$S/cli-cache; mkdir -p $C/sources/584a58e5 $C/sources/evil $C/sources/..x; echo canary > $C/canary; ln -s $C/canary $C/sources/deadbeef; python3 bin/omarchy-iptv playlist --url "file://$PWD/$F/qa-src-a.m3u" --cache-dir $C/sources/584a58e5; touch $C/sources/584a58e5/foo.bin`; for K in `../x ../../x abc d5977d8a/.. 'd5977d8a/../../x' %2e%2e '' D5977D8A d5977d8a-1000 d5977d8a-0 deadbeef`: `python3 bin/omarchy-iptv cache remove --cache-dir $C --key "$K"; echo exit $?` -> `bad_key` (or `skipped` for the symlink), `cat $C/canary` intact, `ls $C/sources`; `cache remove --key 584a58e5` -> `kept: ["foo.bin"]`, dir left; `rm foo.bin`, again -> dir gone; `cache remove --key 584a58e5` on the missing dir -> `ok, removed: []`; migrate: `cp $F/legacy-cache/*.json $C/; touch $C/.tmp-abc; cache migrate --cache-dir $C --key 584a58e5` -> `moved` both, `.tmp-abc` gone, twice -> idempotent, without `--key` on fresh legacy copies -> `removed`; prune: three key dirs + `evil` + the symlink, `--keep k1 --active k1 --epg-max-age 86400` after `touch -d '2 days ago' k2/epg-*` -> `removed [k3]`, `agedEpg [k2]`, `skipped [evil, ..x, deadbeef]`; `--keep ../x` -> `bad_key`; every stdout line is one JSON object with no path | SRC-SEC-08, 23, SRC-RM-07, SRC-MIG-09, SRC-HELP-05..08, SRC-PERF-07 |
| SRC-H16 | State file hygiene and size | `scripts/qa-sources-scenarios.sh print SRC-H16` gives the python that writes a v2 `state.json` with N records (typical URLs, and `--worst` with 2,048-character URLs and 64-character labels) into `$S/state/omarchy-iptv/` 0600; start with `--keep`; `stat -c '%a %s' state.json` after start, after add, label edit, switch, remove, favorite (`$H ipc favorite`); `ls -l`; `python3 bin/omarchy-iptv state --state-dir $S/state/omarchy-iptv show | grep -cE 'url|://'` -> 0; `ps -o args= -p $(pgrep -f 'cache prune')` during a start (or the console) -> at most 50 keys; tampered file (SRC-SEC-21 shapes, the helper prints them) -> guide opens, `jq '.sources|length'` = valid records only, prune argv valid keys only; Sources open time with 50 rows | SRC-SEC-09, 10, 21, SRC-PERF-02, 03, SRC-CLI-07, SRC-HELP-04, SRC-MODEL-07 |

Screenshots go to `$S/shots/` and the evidence copies to
`/tmp/claude-1000/omarchy-iptv-qa4/{logs,shots}` as in the M1 passes; every
failed step gets the SRC id, the screenshot, the console excerpt and the exact
command in the defect row (section 11).

## 9. Live-shell runbook (after the lead updates the installed plugin)

The installed plugin is the user's working v0.1.0 with one source (iptv-org
`us.m3u`), a v1 state with 5 recents, and the legacy cache. A first-run input
on a fresh profile is not possible without wiping that state (and the lead
does not wipe it), so the live pass exercises add / switch / edit / remove
from the existing source, CLI parity, and the update round trip. Everything
below changes the user's desktop; the lead runs it, in this order, with the
snapshot first. Undo is the last block.

### 9.1 Snapshot (read-only)

```
E=/tmp/claude-1000/omarchy-iptv-qa4/live; mkdir -p $E
cp ~/.config/omarchy/shell.json $E/shell.json.before; cp ~/.local/state/omarchy-iptv/state.json $E/state.json.before
ls -la ~/.cache/omarchy-iptv > $E/cache.before; sha256sum ~/.cache/omarchy-iptv/*.json > $E/cache.sha.before
jq '.version, (.recents|length), (.favorites|length)' ~/.local/state/omarchy-iptv/state.json      # 1, 5, 0 on 2026-09-13
git -C ~/.config/omarchy/plugins/io.github.rmcdavid.iptv rev-parse --short HEAD; git -C ~/.config/omarchy/plugins/io.github.rmcdavid.iptv remote get-url origin
date +%FT%T > $E/started-at
```

### 9.2 Update in place and the migration (SRC-MIG-10; TC-INST-08 semantics)

The clone's `origin` is `/home/ricky/Projects/omarchy-iptv` (verified), so
`omarchy plugin update` fast-forwards from the local `main`; it fetches,
shows the diff, asks (or `--yes`), `merge --ff-only`, validates (rolls back on
failure) and runs `omarchy-shell shell rescanPlugins`, but a `keepLoaded`
service does not hot-reload (README), so the shell is restarted afterwards.
"From GitHub" (task wording) needs the release pushed first and the remote
re-pointed (SRC-DEC-20):

```
omarchy plugin update io.github.rmcdavid.iptv                                    # local origin; or first:
#   git -C ~/.config/omarchy/plugins/io.github.rmcdavid.iptv remote set-url origin https://github.com/rmcdavid/omarchy-iptv.git
git -C ~/.config/omarchy/plugins/io.github.rmcdavid.iptv rev-parse --short HEAD   # the merge commit under test
omarchy plugin validate ~/.config/omarchy/plugins/io.github.rmcdavid.iptv         # exit 0
omarchy restart shell
sleep 5; python3 -c 'import json,os;d=json.load(open(os.path.expanduser("~/.local/state/omarchy-iptv/state.json")));print(d["version"],d["cacheLayout"],[(s["key"],s["label"],s["channelCount"]) for s in d["sources"]],len(d["recents"]))'
#   -> 2 2 [('d5977d8a', 'iptv-org.github.io', 1475)] 5          (count as of the live list; it drifts)
find ~/.cache/omarchy-iptv -maxdepth 2 -exec stat -c '%a %n' {} +                  # 700 dirs, 600 files, no top-level channels.json
stat -c '%a %n' ~/.local/state/omarchy-iptv/state.json                             # 600
journalctl --user -t omarchy-shell --since "$(cat $E/started-at)" | grep omarchy-iptv   # cache migrate / prune lines with keys only; no playlist: line if the cache was fresh
```

Open the guide (`SUPER + SHIFT + T`): the US list as before; `Tab`, `o`: one
row `iptv-org.github.io`, `active - iptv-org.github.io - 1,475 channels in 28
groups`, header `1 source`; footer without a label prefix.

### 9.3 Add, switch, edit, remove from the existing source; CLI parity

**[v0.5] D-LIVE-20 and D-LIVE-21 are fixed at `845d445` and both were
re-verified live with their original repros** (QA-RESULTS "P1 fix
verification on 845d445"), so every step below is an expectation again. The
[v0.4] warning that switching and add-activation fail on a real shell is
withdrawn. Keep the timings in mind when you script it: add makes the new
source active in ~0.5-0.8 s, an `Enter` switch lands in ~150 ms on a small
list and ~240 ms at 1,474 channels, and removing the active source reaches
`configured false` in ~0.8 s - poll `status` rather than sleeping.

```
wl-copy -- https://iptv-org.github.io/iptv/countries/ca.m3u        # QA-ASSETS style second list (HEAD 200 on 2026-09-13; key f0441ae2)
# in Sources: a, Ctrl+V (unmasked: nothing to mask), Enter -> Fetching from iptv-org.github.io... -> Added iptv-org.github.io 2 - N channels in M groups (suffix per SRC-DEC-11); the new source is active
# o: two rows; Enter on the US row -> Switched to iptv-org.github.io - 1,475 channels; footer prefixed with the label from now on
# o, Space on the CA row: switches in place; Space back
omarchy-shell io.github.rmcdavid.iptv status | jq '.activeSource, .sources'; omarchy-shell io.github.rmcdavid.iptv status | grep -c '://'   # 0
# e on the CA row: Label -> Canada, Enter -> Saved; e again: Tab to EPG, paste https://i.mjh.nz/PlutoTV/us.xml.gz, Enter -> Saved, background EPG (banner on failure only); e, Tab, Ctrl+R reveals, Tab re-masks, Esc
omarchy bar set io.github.rmcdavid.iptv playlistUrl https://iptv-org.github.io/iptv/countries/uk.m3u   # with Sources open: a third row appears (origin cli), active, loading
omarchy bar set io.github.rmcdavid.iptv playlistUrl https://iptv-org.github.io/iptv/countries/us.m3u   # back: no new row, US active
omarchy bar set io.github.rmcdavid.iptv playlistUrl ftp://nope   # error state with the scheme reason, no host, no helper run (journal); then set the US URL again
# x on the UK row -> dialog -> Remove: ls ~/.cache/omarchy-iptv/sources (its key gone); x on the active Canada row while it is active (switch to it first with Space): variant message, Remove -> Sources stays open, Saved sources (1) behind; Enter on US -> back
```

### 9.4 Mouse (the cases the harness cannot drive)

Pinned `Sources` row click; row hover and click; pencil and close-circle on
the cursor row; `Add source` / `Add Xtream login` rows; eye button toggle;
link rows; `Load` / `Save` / `Cancel`; middle-click paste of a primary
selection into a field; overlay scrim click discards a form; the dialog scrim
cancels the dialog only; wheel over the sources list. Record each as
`SRC-KEY-11` sub-steps.

**[v0.4] Not executable on the reference machine.** It carries no
pointer-injection tool (`ydotool`, `wlrctl`, `dotool`, `xdotool` are all
absent and there is no ydotool socket) and Hyprland exposes no click
dispatcher, so 9.4 cannot be driven from a script; installing a tool needs
`sudo`, which the live pass forbids. Either provision one of those tools
before the next live pass or hand 9.4 to a human tester - do not record it as
`pass` from a keyboard run.

### 9.5 Narrow and theme (optional)

`hyprctl keyword monitor eDP-1,1366x768@60,0x0,2` then `hyprctl reload` to
restore (SRC-LST-09, SRC-UI-20, screenshots `sources-narrow`,
`sources-edit-narrow`); `omarchy theme set nord` with the list, a form and
the dialog open, then `omarchy theme set retropc` (SRC-UI-19); journal grep
for new warnings.

**[v0.4] The narrow half does not work on this install**: `hyprctl keyword`
is refused with `keyword can't work with non-legacy parsers. Use eval.`
because Omarchy drives Hyprland from a Lua config, and the only other lever
is editing `~/.config/hypr/*`, which the live pass forbids. At 1366x768 @
scale 1 the card measures ~959 px, above the `Style.space(720)` threshold, so
the narrow variant is unreachable and SRC-LST-09 / SRC-UI-20 stay blocked.
The theme half ran clean (tokyo-night and back to retropc, re-skinning the
open Sources screen live, no new warning).

### 9.6 Security and regression on the live shell (ARCH 8.5 items 4-6)

```
# control-character and 16 KB pastes into the add form; javascript:, data:, ftp:, /dev/zero, /proc/self/environ refused inline (no journal playlist: line)
# a label `--urgency=critical ${path}` on the CA source: literal in the row; omarchy-shell notifications showHistory unchanged
# Xtream form: http://127.0.0.1:9, u, p -> Connection refused from 127.0.0.1; then:
journalctl --user -t omarchy-shell --since "$(cat $E/started-at)" | grep -cE 'password=|username=|qa-secret'   # 0
omarchy-shell io.github.rmcdavid.iptv status | grep -cE 'password=|://'                                       # 0
python3 ~/.config/omarchy/plugins/io.github.rmcdavid.iptv/bin/omarchy-iptv state show | grep -cE '"url"|://'   # 0
python3 ~/.config/omarchy/plugins/io.github.rmcdavid.iptv/bin/omarchy-iptv cache remove --cache-dir ~/.cache/omarchy-iptv --key ../../x   # bad_key, exit 1, nothing deleted
stat -c '%a' ~/.local/state/omarchy-iptv/state.json                                                          # 600 after all the saves above
journalctl --user -t omarchy-shell --since "$(cat $E/started-at)" | grep omarchy-iptv | grep -c '://'          # 0
# regression subset: QA.md 5.4 US2-US7 with the US list, PERF-02 with index.m3u added as a source (10k open budget), PERF-03
```

### 9.7 End state and undo

Leave the plugin updated with the US source active and the test sources
removed through the screen (the user keeps the working setup). Undo, only if
the lead wants v0.1.0 back: `git -C ~/.config/omarchy/plugins/io.github.rmcdavid.iptv checkout v0.1.0`,
`cp $E/state.json.before ~/.local/state/omarchy-iptv/state.json`, restore the
legacy cache files from `sources/d5977d8a/` to the top level, `cp $E/shell.json.before ~/.config/omarchy/shell.json`,
`omarchy restart shell`.

### 9.8 [v0.4] Corrections from the first live run (2026-09-13, ec4f702)

Recorded after executing section 9 end to end on the reference machine
(`docs/QA-RESULTS.md` section "Live-shell Sources verification on ec4f702").

1. **The shipped plugin has no Sources IPC verbs.** `qs -p
   /usr/share/omarchy/shell ipc show` lists only `toggle`, `previous`,
   `next`, `refresh`, `stop`, `play(id)` and `status` for
   `io.github.rmcdavid.iptv`. The `ipc set`, `ipc sources`, `ipc
   switchSource`, `ipc removeSource` and `editMasked` verbs used throughout
   sections 6 and 8 exist only in the dev harness. Every live Sources
   interaction must be driven through real keyboard or mouse input, or
   through `omarchy bar set` / `omarchy-shell io.github.rmcdavid.iptv status`.
2. **The harness's fake `updateEntryInline` hid a whole defect class.**
   The real host writes `shell.json` and updates its own `shellConfig`, but
   publishes `barConfig` from a change handler that runs before the binding
   it reads, so a plugin is handed the bar one write late and its own write
   never echoes at all (D-LIVE-20, D-LIVE-21). **[v0.5] Resolved**: the fake
   stopped feeding the value back at `1c29a4c` (section 6), and QA measured
   that the corrected scenario fails 23 of its checks against the pre-fix
   service while passing all 61 against the fixed one. A case that asserts on
   the effect of a plugin-initiated settings write is now meaningful in the
   harness - but confirm it live once per release all the same.
3. **`wtype` cannot exercise Hyprland global binds.** Modifier+key reaches
   the focused surface fine (`Ctrl+R`, `Ctrl+A`, `Tab` all worked inside the
   guide) but three spellings of `SUPER + SHIFT + T` left the bind unfired,
   while `hyprctl binds` shows it registered (`modmask=65 key=T`) and its
   command (`omarchy-shell shell toggle io.github.rmcdavid.iptv`) works when
   run directly. Verify the keybinding by hand; script the guide open through
   that command instead.
4. **Keystroke safety.** A closed guide sends keys to whatever window is
   focused. Guard every injection with `pgrep -x hyprlock` *and* a check that
   the `omarchy-iptv` layer is present
   (`hyprctl layers -j | jq ... | grep -c omarchy-iptv`); the guide takes
   exclusive keyboard focus while open, so keys cannot leak to the desktop.
   Note that `omarchy-shell notifications showHistory` steals focus and
   resets the Sources cursor - do not interleave it with a keyboard sequence.
5. **`pkill -f` is unsafe here**: the pattern matches the QA shell's own
   argv. Kill helper servers by recorded PID.
6. 9.2's expected line held (`2 2 [('d5977d8a', 'iptv-org.github.io', 1475)]
   5`), and the upstream count drifts as warned - a refetch during the run
   returned 1,474.

## 10. Decisions the lead made before the pass (SRC-DEC -> SR11-SR32)

Found while cross-reading UX-SOURCES.md, ARCHITECTURE-SOURCES.md and SR1-SR10
for v0.1 of this plan. Every row was answered on 2026-09-13 by the round-2
rulings of `docs/ARCHITECTURE-SOURCES.md`: SRC-DEC-nn -> SR(10+nn), i.e.
SRC-DEC-01 = SR11 ... SRC-DEC-22 = SR32. The rows below are kept for
traceability only; the expectations in section 1 were rewritten against the
rulings (`[v0.2]`). Fixture records that still carry a pre-ruling `archExpect`
or `decision` field (`qa-source-urls.json` 017/018/025/033/043/052/053/055/
090/093/111, `xtream-expect.json` V03/V04/V06/V07/V08/E05/D01/D02/D05,
`qa-source-labels.json` V08/V11/V12/T17) are reported as `decision` records by
the section 2 commands, never as failures; the rulings are the expectation.

| # | Topic | UX-SOURCES.md | ARCHITECTURE-SOURCES.md | QA recommendation |
|---|---|---|---|---|
| SRC-DEC-01 | `~` paths | 5.4 `relative_path`: `Use an absolute path (starts with /, not ~)` | 3.1 step 2 accepts `~/x` as `kind file` (the helper expands it; the CLI accepts it today) | accept in the CLI (D16 must not reject a working v0.1.0 setting), refuse in the forms with the UX message; pin both in the fixture |
| SRC-DEC-02 | relative names, bare hosts, `//host` | `relative_path` for `./x` and names, `scheme` for a bare host | everything without a scheme is `unsupported_scheme`; `//host/x` starts with `/` and is a path | one heuristic in Model.js: leading `//` -> `scheme`; contains `/` or `.` before any `/` -> `scheme`; else `relative_path`; SR6 says the UX codes are what both validators emit |
| SRC-DEC-03 | `/proc`, `/sys`, `/dev` inline | no synchronous code (`Path not allowed` is a fetch result) | `unsafe_path` synchronous | keep `unsafe_path` with the 5.5 message `Path not allowed` on the result line |
| SRC-DEC-04 | duplicate comparison | 5.4: same URL "exact after trim" | `findSourceByUrl` on the normalized URL (case, default port, fragment) | normalized (a case-changed host is the same provider); the fixture says so |
| SRC-DEC-05 | validator parity vectors | - | 3.1 rules leave gaps: port > 65535 and `[not-an-ip]` (JS accepts, Python refuses), U+FEFF in the host (JS refuses, Python accepts), U+200B in the host and a backslash in the authority (both accept), leading-zero ports (two keys for one server), a leading BOM (valid URL fails with the scheme message) | reject ports over 65535, bracket literals that are not `[hex:.%25]`, U+200B-U+200D / U+2060 / U+FEFF / `\` in the authority; normalize numeric ports; strip a leading U+FEFF in `sanitizeInput`; add the vectors to `source-urls.json` |
| SRC-DEC-06 | Xtream server without a scheme | 5.4 `server_scheme`, 8.9 no auto-prefix | D10 / 3.4 prefixes `http://` | one rule; QA has no preference; the fixture D01 carries the ARCH expectation |
| SRC-DEC-07 | Xtream server with userinfo | no code | `bad_server` | a code and a message (`server_path` text does not fit) |
| SRC-DEC-08 | over-cap Xtream fields | `user_too_long` / `pass_too_long` errors | `sanitizeInput` truncates silently to 512 / 256 | errors: a silently truncated credential builds a login that fails for no visible reason |
| SRC-DEC-09 | derived label and the port | 5.6 host `:port` (`nas.local:9981`) | 3.2 host only | UX (`127.0.0.1:8765` vs `127.0.0.1:8766` are different providers) |
| SRC-DEC-10 | `www.` stripping | 5.6 strips it | 3.2 "no www. stripping" | either; pin one |
| SRC-DEC-11 | derived duplicate suffix | 5.6 ` 2`, ` 3`, case-insensitive | 3.2 ` (2)`, ` (3)` | UX wording; case-insensitive as UX |
| SRC-DEC-12 | label cap unit | - | 3.1 UTF-16 units | document; the helper's `normalize_state` must count the same way or not enforce the cap on read |
| SRC-DEC-13 | failed first-run / add probe | 1.2 step 7 "nothing was saved" | D8: the record stays with `fetchedAt: 0` and a session error so the user can retry | either; H05's expectation depends on it (row with `not loaded yet` or no row) |
| SRC-DEC-14 | the 51st source | no `too_many` copy | `too_many` code | a message (`Sources is full - remove one first` or similar) and `Add source` / `a` disabled at the cap |
| SRC-DEC-15 | persist failure copy and the CLI fallback | no copy | R2: `sourcesPersistFailed`, fallback argv `omarchy bar put` / `set` | a result-line message; the fallback must be off in the harness (a stub `omarchy` on PATH) |
| SRC-DEC-16 | retry affordance and error marker in rows | 5.2 rows have no error segment; retry = Enter again | `retrySource(id)`, `errorReason` in rows | Enter again is the retry; rows show `not loaded yet` only (no session error text) unless UX adds a segment |
| SRC-DEC-17 | mask of `type` / `output` | 4.4 example masks them | SR4 keeps them visible | SR4 stands; the UX wireframes 3.1.2 / 3.3.1 need the two values un-masked (docs fix) |
| SRC-DEC-18 | `Not an M3U file` vs `Not an M3U playlist` | 5.5 both spellings (URL / path rows) | shipped `statusReason` says `Not an M3U playlist` | one spelling |
| SRC-DEC-19 | `Model.LIMITS` vs ARCH constant names | SR5 `Model.LIMITS` | 3 `MAX_SOURCE_URL` etc. | both may exist; QA greps for `LIMITS` |
| SRC-DEC-20 | live update path | - | 8.5 item 1 `git pull` | the clone's origin is the local repo; decide local `omarchy plugin update` or re-point to GitHub after the push |
| SRC-DEC-21 | extra harness verbs | - | 8.4 list | add `cancelProbe`, `editMasked(id)`, `signals()`, and `state()` fields for the guide form (masked values + lengths, focus, mode, returnMode); optional `failPersist` |
| SRC-DEC-22 | list order | wireframe 3.2.1 (no stated rule) | `sourceRows`: active first, then `lastUsed` desc [UX-ASSUMPTION] | state the rule in UX 5.2 |

## 11. Defect template

One row in `docs/STATUS.md` "Defects" and the details in `docs/QA-RESULTS.md`
(Sources pass section), as in QA.md section 6, with the Sources ids:

```
D-SRC-<n> | P1/P2/P3 | M2-01 | <SRC id>: <one-line repro> | open
### D-SRC-<n> (<SRC id>, <area>)  P<sev>  found <date> at <commit>
Steps: 1. ... (scenario SRC-Hnn step, or the live 9.x step) 2. ...
Expected (doc + section, or the SRC-DEC ruling): ...
Actual: ...
Evidence: /tmp/claude-1000/omarchy-iptv-qa4/{shots,logs}/..., console lines, jq output
Notes: suspected file:line, lane (1 = Model.js/Guide.qml, 2 = Service.qml/helper/harness), workaround
```

Severity for this feature: P1 = cannot add, switch or remove a source; a
credential reaches a third party, a world-readable file, a notification or
the journal; a bad key deletes outside `sources/`. P2 = a URL rendered
beyond scheme+host anywhere but the revealed field; a failed add displaces the
active source; the wrong cache is swapped in; favorites or recents lost by the
migration; `state.json` not 0600. P3 = wording, order, cosmetic, a hardening
item with no user-visible effect today.
