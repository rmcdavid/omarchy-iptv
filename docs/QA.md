# Omarchy IPTV - QA test plan, fixtures and live-shell runbook

Owner: QA. Status: v0.2 (2026-09-13): v0.1 written during M0-08 while the FE
lanes build M1; v0.2 carries the corrections found during the harness pass
(docs/QA-RESULTS.md, defects D-LIVE-nn in docs/STATUS.md). Governs M1.1-01 (functional), M1.1-02 (theme), M1.1-03
(performance), the QA half of M1.1-04 (security evidence), M1.1-06
(regression), REL-01 and REL-02.

Documents of record this plan verifies against: `docs/PRODUCT.md` (US1-US8,
quality bar QB1-QB5), `docs/ARCHITECTURE.md` (sections 5-8, 10, 12 rulings
R1-R13), `docs/UX.md` (sections 3, 4, 6, 7), `docs/PLAN.md` (gates G0-G5,
severities), `docs/QA-ASSETS.md` (public sources). This file is ASCII; where
UX.md writes `...`, `"x"` and ` - ` the implementation must use the real
codepoints listed in UX.md's table (U+2026, U+201C/U+201D, U+00B7). Glyphs are
written as their codepoint (U+F0502 etc., see UX.md 5.5).

Machine of record (verified 2026-09-12): Omarchy 4.0.3, Quickshell 0.3.1,
Hyprland 0.56.2, mpv 0.41.0, Python 3.14.7, node 26.8.1 (mise, dev only),
one monitor `eDP-1` 1366x768 scale 1, current theme `retropc`, shell launched
by `omarchy-launch-shell` through `systemd-cat -t omarchy-shell` (so its
console is in the user journal), `SUPER SHIFT + T` free, `SUPER CTRL + T` =
Activity, no `omarchy-iptv` directories present, `~/.config/omarchy/shell.json`
mode 0600 with `bar.layout.{left,center,right}` entries and an empty
`plugins: []`.

## 0. How to read and execute this plan

- Test case ids are `TC-<AREA>-<nn>`. Areas: INST (install and lifecycle), CFG
  (settings), BRW (browse and keys), PLAY, BAR, FAV (favorites and recents),
  EPG, RFR (refresh and offline), UI (states, microcopy, theme), A11Y, SEC,
  PERF, PARSE (helper parsers), MODEL (Model.js). Security cases are numbered
  `SEC-nn`, performance cases `PERF-nn`.
- "How" column: `A` = automated, with the exact command and file; `M` = manual,
  with the runbook step in section 5 that executes it. `A*` = automated test
  that the FE lanes are expected to add (section 2 lists them); until it lands,
  QA runs the fixture through the helper by hand (section 7 commands). `X` =
  observed at the real sink by the accessibility harness (`tests/a11y/`), which
  is a lane tool and deliberately **not** part of `scripts/check.sh` (PLAN-NEXT
  decision 9); an `X` case is satisfied only by a dated run whose output is
  filed in `docs/QA-RESULTS.md`, never by the harness merely existing. The
  conditions under which the harness would join `scripts/check.sh` are
  proposed, and not implemented, in `docs/UX.md` 7.1a.
- **A criterion may not be a grep for the string the implementation was written
  to contain** (CLAUDE.md rule 14). Four criteria in this plan and in
  `docs/QA-SOURCES.md` were exactly that -- TC-A11Y-01, TC-BAR-11, SRC-A11Y-01,
  SRC-A11Y-05 -- and all four passed for months over a surface that publishes
  nothing to anybody. They are rewritten as `X` cases. Where neither calling
  the shipping logic nor observing the sink is possible, the rule the criterion
  covers is marked UNVERIFIED in the document that states it and stays marked.
- Every M case is executed on the live shell after the lanes merge, in the
  order of section 5. Results are recorded in `docs/STATUS.md` (handoff
  format, PLAN.md section 7) as `pass` / `fail D-<n>` / `not run <reason>`
  with the evidence file name from section 5.9.
- A case fails if any expected string, glyph, count, file mode or timing is
  off. Microcopy is compared verbatim against UX.md section 6.
- Severities (PLAN.md section 6): P1 blocks a user story, P2 degrades one,
  P3 cosmetic. Release needs zero open P1/P2.

## 1. Traceability matrix

### 1.1 Test cases

#### Install and lifecycle (US8, G0, G5)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-INST-01 | manifest schema, entry points, no symlinks, id not reserved | A `omarchy plugin validate .` (in `scripts/check.sh`) | exit 0 |
| TC-INST-02 | git clone install (no symlink), validate on the clone | M 5.2 | `omarchy plugin validate ~/.config/omarchy/plugins/io.github.rmcdavid.iptv` exit 0 |
| TC-INST-03 | rescan + enable | M 5.2 | `omarchy plugin list --json` shows `enabled: true`, kinds `bar-widget,overlay,service`; `shell.json` gains exactly `{"id":"io.github.rmcdavid.iptv"}` at the end of `bar.layout.right`; `plugins[]` unchanged |
| TC-INST-04 | console clean on load | M 5.2, 5.9 | no `WARN`/`ERROR` lines mentioning `io.github.rmcdavid.iptv`, `Guide.qml`, `Service.qml`, `BarWidget.qml` or `omarchy-iptv` in the journal after enable |
| TC-INST-05 | disable removes the widget and its settings; re-enable starts clean | M 5.10 (before remove) | after `omarchy plugin disable`, the bar entry (and inline `playlistUrl`) is gone from shell.json, widget gone, `omarchy-shell shell toggle io.github.rmcdavid.iptv` is a no-op, mpv (attached Process) exits; after `enable` the guide shows the not-configured state. Expected host behaviour; README must say settings are lost on disable |
| TC-INST-06 | `omarchy plugin remove --yes` leaves only cache, state, runtime dirs | M 5.10 | `find ~ -path '*omarchy-iptv*'` lists only `~/.cache/omarchy-iptv`, `~/.local/state/omarchy-iptv`, `/run/user/1000/omarchy-iptv`; shell.json identical to the pre-install snapshot |
| TC-INST-07 | nothing written inside the plugin directory at runtime | M 5.7 | `find <plugindir> -newer <plugindir>/manifest.json -not -path '*/.git/*'` prints nothing after a full session |
| TC-INST-08 | `omarchy restart shell` round trip | M 5.4 US5 step 6 | widget back, settings intact, favorites and recents intact, mpv gone (R10, documented) |
| TC-INST-09 | `keepLoaded` survives `rescanPlugins` | M 5.4 US3 step 7 | `omarchy-shell shell rescanPlugins` while playing: mpv keeps playing, bar label unchanged |
| TC-INST-10 | README uninstall section matches reality | M 5.10 | README commands produce TC-INST-06 result verbatim |

#### Configuration (US1, R2, section 6 of ARCHITECTURE.md)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-CFG-01 | `omarchy bar set ... playlistUrl <url>` fetches without restart | M 5.3, 5.4 US1 | helper runs within ~1 s (journal shows one run, 300 ms debounce); bar tooltip `IPTV - click to open the guide`; guide footer `1,475 channels - updated HH:MM` (count from the live list, thousands separator) |
| TC-CFG-02 | HTTP 404 with no cache | M 5.4 US1 step 4 | empty state `Playlist failed to load` / `HTTP 404 Not Found from iptv-org.github.io - check playlistUrl`; hint `r reload - Esc close`; bar glyph U+F0503, tooltip `IPTV - playlist error, open the guide`; notification `Playlist error` / `Could not fetch the playlist (HTTP 404 Not Found). Open the guide for details.` |
| TC-CFG-03 | unresolvable host | M 5.4 US1 step 5 | reason `Could not resolve host` |
| TC-CFG-04 | unsupported source scheme | A `python3 -m unittest discover -s tests` (`tests/test_helper.py::test_refuses_unsupported_scheme`); M optional | code `unsupported_scheme`, guide renders the message |
| TC-CFG-05 | absolute path and `file://` sources | A `tests/test_playlist.py::SourceTest`, `tests/test_helper.py`; M 5.4 US7 (local server) | both load; `sourceHost` = `local file` |
| TC-CFG-06 | `epgUrl` set later, plain and `.gz` | M 5.4 US6 | `epg-now.json` appears; rows get Now/Next; unmatched ids show no EPG line and no error |
| TC-CFG-07 | `refreshMinutes` typing and clamps (R2) | A `node tests/Model.test.js` (`clampInt`); M 5.4 US7 step 1 | `omarchy bar set ... refreshMinutes 30` (string) is parsed; `--json 5` clamps to 15; `--json 99999` to 1440; timer re-arms |
| TC-CFG-08 | `mpvArgs` tokens | A `Model.test.js` (`splitMpvArgs`); M 5.4 US3 step 8 | `--profile=fast --hwdec=auto-safe` appear in `ps -o args=` of mpv; `--input-ipc-server=/tmp/x --title=X --no-idle` are dropped with one console warning naming them |
| TC-CFG-09 | `showChannelName` false | M 5.4 US4 step 7 | glyph only while playing; tooltip keeps the name |
| TC-CFG-10 | `barLabelMaxWidth` 60 vs 600 (R7) | M 5.4 US4 step 8 | label elided at `Style.space(60)`, then almost never elided at 600 |
| TC-CFG-11 | `maxRecents` 3 | M 5.4 US5 step 5 | Recent shows the 3 newest |
| TC-CFG-12 | settings change while the guide is open | M 5.4 US1 step 6 | guide re-renders without restart |
| TC-CFG-13 | credentials never rendered (R12) | see SEC-07 | no URL beyond scheme+host in guide, tooltip, notification, journal |

#### Browse (US2, R1, R3, R4, R5, R6, UX 2.x, 3.1, 3.2)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-BRW-01 | open with `SUPER + SHIFT + T` | M 5.3 (binding added by hand), 5.4 US2 | guide opens on the focused monitor; second press closes |
| TC-BRW-02 | open with bar left click; click again closes | M 5.4 US2 | same |
| TC-BRW-03 | open with `omarchy-shell shell toggle io.github.rmcdavid.iptv` | M 5.4 US2 | same; `hide`/`summon` also work |
| TC-BRW-04 | menu entry (optional) | M 5.3 | `omarchy-menu.jsonc` snippet from README opens the guide |
| TC-BRW-05 | opens in search mode, empty query (UX 3, 4.1) | M 5.4 US2 step 2 | header `Search channels...` at placeholder opacity; footer hint `Enter play - Up/Down move - Left/Right group - Tab keys - Esc close`; cursor on row 0, or on the playing channel when it is in the list |
| TC-BRW-06 | default column entry (UX 2.2) | M 5.4 US2 step 2, US5 step 3 | Favorites when it has entries, else All; scope label `All - 1,475 channels` / `Favorites - 6 channels`; Recent hidden while empty; Favorites always present |
| TC-BRW-07 | type to filter (UX 2.6) | M 5.4 US2 step 3 | terms ANDed, case and diacritic insensitive (`TELE quebec` finds `Tele Quebec` spelled with accents), scope label `in All - N matches`, cursor to result 0 |
| TC-BRW-08 | ranking tiers and favorites first (R4, UX 2.5) | A* `Model.test.js` (`filterChannels` tiers 0-3, favorites first, playlist order inside a tier); M spot check with `news` | name-prefix rows first, then word-start, then name-contains, then group-contains |
| TC-BRW-09 | result cap 200 (R3) | M 5.4 US2 step 4 with `index.m3u` or `gen-10k.m3u` | footer `First 200 of N - keep typing`; list has 200 rows |
| TC-BRW-10 | Up/Down wrap, PgUp/PgDn clamp, Home/End (UX 3.1, 3.2) | M 5.4 US2 step 5 | Down on the last row wraps to row 0; PgDn moves visible-1 rows and stops at the end; End/Home jump |
| TC-BRW-11 | Left/Right move the column; query from Recent/Favorites jumps to All and restores on clear (UX 2.7) | M 5.4 US2 step 6 | column highlight moves and wraps; typing on Favorites highlights All; clearing restores Favorites |
| TC-BRW-12 | Esc semantics and host open-state (UX 3.2) | M 5.4 US2 step 7 | Esc with a query clears it (hint changes from `Esc clear` back to `Esc close`); Esc with an empty query closes; afterwards `omarchy-shell shell toggle` opens on the first call (state in sync) |
| TC-BRW-13 | Tab / `/` mode switch (UX 3.1) | M 5.4 US2 step 8 | Tab commits the query and shows `j/k move - h/l group - Enter play - Space preview - f favorite - s stop - r refresh - / search`; `/` returns to search mode with the query preserved |
| TC-BRW-14 | list mode ignores unbound letters | M 5.4 US2 step 9 | `q`, `w`, `e` do nothing; no search starts |
| TC-BRW-15 | digits: ignored in list mode, literal in search mode | M 5.4 US2 step 9 | `4` in list mode: nothing; `4k` in search mode filters |
| TC-BRW-16 | uppercase F/S/R/X act like lowercase | M 5.4 US2 step 9 | same actions |
| TC-BRW-17 | group-scoped search and zero results (UX 2.7, 6.3) | M 5.4 US2 step 10 | on a group: `in <group> - N matches`; no match: `No matches for "sky" in <group>` and `h/l other groups - Home for All`; Home jumps the column to All |
| TC-BRW-18 | zero results in All | M 5.4 US2 step 10 | `No matches for "zzzz"` / `Esc clears the search` |
| TC-BRW-19 | scrim click closes, card click swallowed, hover through PointerMoveGate (UX 5.4, 7.3) | M 5.4 US2 step 11 | one highlighted row at all times; keyboard move then stationary pointer does not steal the cursor |
| TC-BRW-20 | exclusive keyboard focus (PLAN risk R2) | M 5.4 US2 step 12 | with a terminal focused behind, typed letters go to the guide only |
| TC-BRW-21 | group order = playlist order, `Ungrouped` last (UX 2.2, 2.5) | A* `Model.test.js` (`groupChannels`); M | never alphabetised |
| TC-BRW-22 | multi-group `A;B;C` under the first group, searchable by any (R5) | A* `tests/test_playlist.py` with `qa-groups.m3u`; M with `us.m3u` (`Animation;Kids;...` entries) | listed once under `Animation`, found by `kids` |
| TC-BRW-23 | wheel: list scrolls, column moves one entry per tick (UX 7.3) | M 5.4 US2 step 11 | as stated |
| TC-BRW-24 | narrow screen hides the column (UX 5.1, R6), optional | M 5.6 | under `Style.space(720)` card width: column hidden, `h`/`l` still work, scope label is the indicator |
| TC-BRW-25 | summon payload `{"query":"bbc"}` (scaffold feature, optional) | M | query prefilled |

#### Watch (US3, R10, R11, UX 3.1 Enter/Space, 4.7, 6.4, 7.5)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-PLAY-01 | Enter plays, closes, focuses mpv | M 5.4 US3 step 1, 5.7 | exactly one `mpv` with `--wayland-app-id=omarchy-iptv`; `hyprctl clients` shows `class: omarchy-iptv`, `title: <channel name>`; guide hidden; mpv focused |
| TC-PLAY-02 | Enter on another channel reuses the window | M 5.4 US3 step 2, 5.7 | same mpv pid, title changes, no second window |
| TC-PLAY-03 | Enter on the playing row: no reload (UX 8 item 4) | M 5.4 US3 step 3 | stream not restarted (no black frame, `omarchy-shell io.github.rmcdavid.iptv status` unchanged apart from time), guide closes, mpv focused |
| TC-PLAY-04 | Space previews, guide stays open (UX 3.1, 4.7) | M 5.4 US3 step 4 | row name bold, trail glyph U+F040A, footer `U+F040A <name> - s stop`; cues move instantly on the next Space |
| TC-PLAY-05 | dead stream (R11, UX 6.4) | M 5.4 US3 step 5 | notification `Stream failed` / `<name> did not play` (plus ` - <mpv reason>` when known), glyph U+F0503, urgency normal, `-r` id reused; row trail U+F0026 and detail `Failed HH:MM - Space to retry`; cursor stays; bar back to idle glyph |
| TC-PLAY-06 | `s` stops (UX 3.1) | M 5.4 US3 step 6 | footer `Stopped` for 3 s then the count; mpv exits; no notification; bar idle |
| TC-PLAY-07 | user quits mpv (`q`) | M 5.4 US3 step 6 | bar idle, cues clear, no notification (exit 0) |
| TC-PLAY-08 | per-channel headers reach mpv as argv | M 5.4 US3 step 8 with `gen-dead.m3u` (2 % entries carry `#EXTVLCOPT`) or `qa-headers.m3u`; A `Model.test.js` (`headerArgs`, `buildMpvArgv`) | `ps -o args=` shows `--user-agent=...`, `--referrer=...`, URL after `--` |
| TC-PLAY-09 | hung mpv reaped by the health check (decision 12), optional | M 5.4 US3 step 9 | `kill -STOP <mpv>`: after two failed `status` polls (10 s each) the console logs `mpv unresponsive, restarting player` and mpv is SIGTERMed; the relaunch follows once mpv actually exits (send `kill -CONT` after a SIGSTOP test, mpv traps SIGTERM) |
| TC-PLAY-10 | zapping bursts (UX 1.2) | M 5.4 US3 step 4 | Space three times within 2 s ends on the third channel; no dropped zap, no second mpv |
| TC-PLAY-11 | mpv dies with the shell (R10) | M 5.4 US5 step 6 | documented limitation, README states it; recorded, not a defect |
| TC-PLAY-12 | zap in under two seconds of interaction (PRODUCT) | M 5.4 US3 step 1 | open + 3 letters + Enter to first frame under 2 s (stopwatch) |
| TC-PLAY-13 | mpv missing notification `mpv not found` / `Install mpv to play channels.` (critical) | M not runnable here (mpv is an Omarchy dependency); verify by code review of the exit-code path | recorded `not run` |
| TC-PLAY-14 | guide over fullscreen mpv (UX 7.5) | M 5.4 US3 step 10 | overlay draws above; Esc returns; mpv neither paused nor muted |

#### Bar widget (US4, R7, UX 3.3, 3.4, 4.8, 6.3)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-BAR-01 | idle | M 5.4 US4 step 1 | glyph U+F0502 dimmed (`Qt.darker(bar.barForeground, 1.55)`), no label; tooltip `IPTV - click to open the guide` |
| TC-BAR-02 | not configured | M 5.4 US1 step 1 | glyph U+F0502, tooltip `IPTV - no playlist configured` |
| TC-BAR-03 | playing | M 5.4 US4 step 2 | glyph U+F0567 + name elided at `Style.space(barLabelMaxWidth)`; tooltip `Playing <full name>` |
| TC-BAR-04 | error, not playing | M 5.4 US1 step 4 | glyph U+F0503; tooltip `IPTV - playlist error, open the guide` |
| TC-BAR-05 | refreshing | M 5.4 US4 step 5 | tooltip `IPTV - refreshing playlist...` |
| TC-BAR-06 | left click toggles the guide | M 5.4 US4 step 3 | open, click again closes |
| TC-BAR-07 | right click stops | M 5.4 US4 step 4 | mpv exits, idle glyph |
| TC-BAR-08 | middle click refreshes (R12: manual refresh notifies) | M 5.4 US4 step 5 | footer `Refreshing...` then `Refreshed - 1,475 channels`; notification `Playlist refreshed` / `1,475 channels in 38 groups` (counts from the live list), urgency low, glyph U+F0450 |
| TC-BAR-09 | wheel zaps one channel per tick in the zap ring, wraps (UX 3.4) | M 5.4 US4 step 6 | played from Favorites: scroll stays inside Favorites; from a group: inside the group; from Recent: the channel's group; touchpad swipes accumulate (`Util.wheelSteps`) |
| TC-BAR-10 | vertical bar: glyph only, name in tooltip (R7), optional | M 5.6 | `omarchy bar position left`, check, `omarchy bar position top` |
| TC-BAR-11 | accessible names (UX 7.1) | X bar scenarios of the accessibility harness, dated run filed in `docs/QA-RESULTS.md` "Accessibility harness runs". **Not** a grep: the old criterion was `grep -n 'Accessible' BarWidget.qml`, which is two lines the widget was written to contain and cannot go red (rule 14) | The harness instantiates `BarWidget.qml` in a plain hidden Qt window, walks the AT-SPI tree and reads back the node for each of the three states: exactly one `push button`, whose **name** is `IPTV, idle` / `IPTV, playing <name>` (`IPTV, playing channel <n>, <name>` when numbered, M2-03 section 11) / `IPTV, playlist error`, the three names distinct, and no Private-Use glyph codepoint inside any published name. **Markup only.** Delivery of these names to an assistive technology is UNVERIFIED and currently impossible (D-GS-3) |
| TC-BAR-12 | third-party replacement bar facade (ARCH risk 7) | not testable here | recorded `not run`, README mentions the limitation |

#### Favorites and recents (US5, R5, R8, UX 2.2, 3.1 f/x)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-FAV-01 | `f` toggles favorite | M 5.4 US5 step 1 | lead star U+F04CE appears; footer `Added to Favorites` / `Removed from Favorites` for 3 s |
| TC-FAV-02 | Favorites entry always present; empty state | M 5.4 US5 step 2 | `No favorites yet` / `Press f on any channel to pin it here` |
| TC-FAV-03 | Favorites order = order added; first after Recent | M 5.4 US5 step 3 | as stated |
| TC-FAV-04 | `f` inside Favorites removes the row, cursor clamps | M 5.4 US5 step 3 | as stated |
| TC-FAV-05 | `x` / `X` / Delete | M 5.4 US5 step 4 | in Recent removes (`Removed from Recent`); in Favorites unfavorites; elsewhere no-op |
| TC-FAV-06 | Recent list rules | A `Model.test.js` (`pushRecent`: newest first, de-duplicated, capped); M 5.4 US5 step 5 | hidden while empty; replay moves to top; cap `maxRecents` |
| TC-FAV-07 | recent recorded on the play command even when the stream fails (R5) | M 5.4 US3 step 5 | the dead channel is in Recent |
| TC-FAV-08 | persistence across shell restart; file modes | M 5.4 US5 step 6, 5.7 | favorites and recents survive `omarchy restart shell`; `~/.local/state/omarchy-iptv` 0700, `state.json` 0600 |
| TC-FAV-09 | corrupt `state.json` | A `Model.test.js` (`parseState`); M 5.4 US5 step 7 | empty state, no crash, file rewritten on next change |
| TC-FAV-10 | ids stable across refresh (decision 6) | A `tests/test_playlist.py` (`assign_ids`), `qa-attrs.m3u`; M 5.4 US7 | favorites still favorites after `r` |
| TC-FAV-11 | click on the lead slot toggles without playing (UX 2.4, 7.3) | M 5.4 US5 step 1 | star toggles, nothing plays |

#### EPG (US6, decision 5, UX 2.4, 5.6)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-EPG-01 | guide never blocks on EPG | M 5.4 US6 step 1 | guide opens instantly after `epgUrl` is set; footer `Guide data loading...` / neutral banner until `epg-now.json` lands |
| TC-EPG-02 | row content with EPG | M 5.4 US6 step 2 | detail `Now: X - Next: Y`, right meta `until HH:MM` (24 h local), progress hairline fraction = elapsed/duration |
| TC-EPG-03 | channel without EPG data | M 5.4 US6 step 3 | no `Now:`/`Next:` segments, no `until`; single-line rows inside a group when EPG is not configured |
| TC-EPG-04 | EPG failure is soft | M 5.4 US6 step 4 | banner `Guide data unavailable (<reason>) - channels still work - r retry`; notification `Guide data error` / `Could not fetch the EPG (<reason>). Channels still work.` low; playback unaffected |
| TC-EPG-05 | plain and gzip give identical output | A* `tests/test_epg.py` with `qa-epg.xml` and `qa-nonascii/qa-epg.xml.gz` | byte-identical `epg-now.json` (apart from `generatedAt`) |
| TC-EPG-06 | timezone offsets and formats | A* `tests/test_epg.py` (clock pinned to T0 = 1789244100) | per the fixture comment: `bbc1.uk` now `Six O'Clock News` stop 1789245000; `cnn.us` now `The Lead`; `halfhour.test` now `Half Hour Offset`; `notz.test` treated as UTC; `short.test` 12-digit accepted |
| TC-EPG-07 | overlap, gap, no-stop, far, orphan, no-programme channel | A* `tests/test_epg.py` | overlap: now = latest start <= T0 (`Overlap B`), next `After Overlap`; gap: no now, next `Starts Later`; nostop: now `No Stop Attribute` with stop = next start; `far.test` absent (outside +-24 h); `orphan.test` keyed or ignored, never a crash; `nochannel.test` absent |
| TC-EPG-08 | 30 s tick and 5 min recompute (R8, decision 5) | M 5.4 US6 step 5 | `until` and fraction advance; `epg --now-only` runs every 5 min (journal), no download before the TTL |
| TC-EPG-09 | unicode titles | A* `tests/test_epg.py` (`unicode.test`); M with `gen-real.xml` | character references decoded; rows render |
| TC-EPG-10 | `too_large`, `bad_gzip`, HTTP errors | A* `tests/test_epg.py` | error object with the code; `epg-status.json` written; old `epg-now.json` kept |
| TC-EPG-11 | matching restricted to playlist ids, `@SD` style ids | A* `tests/test_epg.py` (`00sReplay.us@SD`) | id with `@` matched verbatim |
| TC-EPG-12 | large EPG does not stall typing | PERF-04, PERF-03 | as in section 4 |

#### Refresh and offline (US7, R12, decision 7)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-RFR-01 | `r` refreshes playlist and EPG | M 5.4 US7 step 2 | footer `Refreshing...` then `Refreshed - N channels`; notification `Playlist refreshed` low |
| TC-RFR-02 | timer refresh is silent on success | M 5.4 US7 step 1 (15 min wait, optional) | helper run in the journal at +15 min, no notification |
| TC-RFR-03 | offline with cache (banner, footer, notification) | M 5.4 US7 steps 3-4 (local server stopped) | banner `U+F0026 Playlist refresh failed (Connection refused) - showing cached copy from HH:MM - r retry`; footer `N channels - cached HH:MM - offline`; notification `Playlist error` / `Could not fetch the playlist (Connection refused). Using cached copy from HH:MM.` normal |
| TC-RFR-04 | debounce: two triggers within 300 ms = one run | M 5.4 US7 step 5 | journal shows one helper invocation |
| TC-RFR-05 | refresh does not interrupt playback | M 5.4 US7 step 2 | mpv untouched |
| TC-RFR-06 | startup offline uses the cache | M 5.4 US7 step 6 | after `omarchy restart shell` with the server down the guide renders from cache immediately, then the banner appears |
| TC-RFR-07 | list changes while the guide is open | M 5.4 US7 step 7 | rows rebuild, cursor index clamped |
| TC-RFR-08 | playlist parsed but empty (`qa-empty.m3u` served) | M 5.4 US7 step 8 | `Playlist has no channels` / `Parsed 0 channels from <host> - check the URL points at an M3U`; previous cache kept and marked stale |
| TC-RFR-09 | not an M3U (`qa-not-m3u.html` served) | M 5.4 US7 step 8 | reason `Not an M3U file` (helper code `not_a_playlist`, D-QA-13; the guide must map that code, D-LIVE-03) |
| TC-RFR-10 | stale cache marked in bar tooltip | M 5.4 US7 step 3 | tooltip carries `(cached)` or the footer does (UX 6.3 puts it in the footer; either is acceptable, both is best) |

#### States, microcopy, theme (UX 4.x, 5.x, 6.x, QB1)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-UI-01 | not configured (UX 4.4, 6.3) | M 5.4 US1 step 1 | `No playlist configured`; `Set your M3U URL or path, then press r to load it:`; command box `omarchy bar set io.github.rmcdavid.iptv playlistUrl <url>`; `Optional EPG:  omarchy bar set io.github.rmcdavid.iptv epgUrl <url>`; `Settings live in ~/.config/omarchy/shell.json (entry io.github.rmcdavid.iptv)`; column hidden; hint `r reload - Esc close`; glyph U+F0502; click on the box copies (`wl-paste`) and footer `Copied` |
| TC-UI-02 | loading, no cache (UX 4.5) | M 5.4 US1 step 2 | glyph U+F01D8, `Loading playlist...`, `Fetching from iptv-org.github.io` (host only), hint `Esc close`; never shown when a cache exists |
| TC-UI-03 | error with cache (banner, UX 4.6) and without cache | M 5.4 US7 step 3, US1 step 4 | banner spec (height `Style.space(28)`, urgent tint, glyph U+F0026, 140 ms fade); empty error state with glyph U+F0503 |
| TC-UI-04 | now-playing cues (UX 4.7) | M 5.4 US3 step 4 | bold name + U+F040A + footer, column unchanged |
| TC-UI-05 | theme switch, guide closed and open (QB1, QB3) | M 5.5 | `omarchy theme set tokyo-night`, `catppuccin-latte`, back to `retropc`: overlay and bar re-skin live, no restart, no new journal warnings |
| TC-UI-06 | no hardcoded colors (UX 5.9) | A `grep -nE '#[0-9a-fA-F]{3,8}\b|"white"|"black"|Qt\.rgba\(' *.qml` | only lines with `CONVENTION-EXCEPTION` |
| TC-UI-07 | fonts from tokens | A `grep -n 'font.family' *.qml` | only `Style.font.menuFamily`, `bar.fontFamily`, `root.fontFamily` bound to those |
| TC-UI-08 | animations (UX 5.8) | M 5.4 US2 step 1 | no open/close fade; banner 140 ms; label width 180 ms |
| TC-UI-09 | footer hints per mode (UX 6.2) | M 5.4 US2 steps 2, 3, 8 | four exact strings |
| TC-UI-10 | scope labels (UX 6.1) | M 5.4 US2 | `Favorites - 6 channels`, `All - 1,475 channels`, `Recent - 3 channels`, `<group> - N channels`, `in All - 14 matches`, `in <group> - 9 matches` |
| TC-UI-11 | glyph codepoints (UX 5.5) | A `grep -nP '[\x{F0000}-\x{FFFFF}]' *.qml` and eyeball | U+F0502 idle, U+F0567 playing, U+F0503 error, U+F04CE favorite, U+F040A playing row, U+F0026 failed, U+F01D8 loading, U+F0450 refresh |
| TC-UI-12 | microcopy centralised (UX 5.9) | A `ls Copy.js` or `grep -n 'readonly property var copy' Guide.qml` | one place; strings match UX 6 |
| TC-UI-13 | qmllint clean, console clean | A `scripts/check.sh` (qmllint step); M 5.9 | 0 errors; only baseline warnings recorded in README |
| TC-UI-14 | card geometry (R6, UX 5.1) | M visual + `grep -n 'space(960)\|space(620)\|space(200)\|space(720)' Guide.qml` | tokens present, card centred, no resize while open |

#### Accessibility and ergonomics (UX 7)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-A11Y-01 | roles and names (UX 7.1) | X guide scenarios of the accessibility harness, dated run filed in `docs/QA-RESULTS.md` "Accessibility harness runs". **Not** a grep: the old criterion was `grep -n 'Accessible\.' Guide.qml BarWidget.qml`, 58 lines the two files were written to contain, and it passed for the whole life of the project while nothing the guide declares reached any screen reader (rule 14, D-GS-3) | Per row of UX 7.1, the node is present in the walked tree with the stated role and the stated name: Dialog `IPTV guide`, EditableText `Search channels` (with its **value** and description equal to the typed query), List `Groups` / `Channels in <scope>`, ListItem per row carrying the suffixes of UX 7.1 that the scenario's fixture populates, AlertMessage banner, StaticText footer, Button bar. A row of UX 7.1 that no scenario populates is marked UNVERIFIED there and is not claimed here. **Markup only.** Delivery is UNVERIFIED (D-GS-3) |
| TC-A11Y-02 | no colour-only status (UX 7.2) | M review during 5.4 | every state has a glyph or word |
| TC-A11Y-03 | hit targets (UX 7.3) | M 5.4 US2 step 11 | rows full width >= `Style.space(38)`, lead slot >= 28 px square |
| TC-A11Y-04 | multi-monitor (UX 7.4, PLAN A7/R12) | M 5.6 | not verifiable on this machine; procedure recorded for a two-monitor run |
| TC-A11Y-05 | focus and mpv (UX 7.5) | covered by TC-PLAY-01/03/14 | |
| TC-A11Y-06 | performance ergonomics (UX 7.6) | PERF-02, PERF-03 | |

#### Parsers and model (QB2)

| ID | Verifies | How | Expected |
|---|---|---|---|
| TC-PARSE-01 | `#EXTINF` quoted/bare attributes, commas in titles, durations | A `tests/test_playlist.py::ExtinfTest` (exists); A* with `qa-attrs.m3u` | see section 7 expected values |
| TC-PARSE-02 | `#EXTGRP` persistence and clearing, `group-title` wins | A `test_attributes_fixture` (exists); A* `qa-groups.m3u` | `Sports`, `Sports`, `Movies`, `News`, `Ungrouped` |
| TC-PARSE-03 | multi-group first segment for display, whole string in `searchKey` (R5) | A* `qa-groups.m3u` | `Animation` / `multi group channel animation kids religious` (D-QA-03 until fixed) |
| TC-PARSE-04 | `#EXTVLCOPT` / `#KODIPROP` mapping, scope, no leak | A `test_vlcopt_does_not_leak_to_next_entry` (exists); A* `qa-headers.m3u` | section 7 |
| TC-PARSE-05 | duplicate tvg-id, exact duplicate URL ids | A `test_attributes_fixture`; A* `qa-attrs.m3u` | `u:<hash>` for both HD/SD; `u:cc5a0021` and `u:cc5a0021#2` |
| TC-PARSE-06 | BOM + CRLF | A `test_crlf_and_bom` (exists); A* `qa-nonascii/qa-bom-crlf.m3u` | 3 channels, no `\r` in URLs, `#EXTGRP` persists across CRLF |
| TC-PARSE-07 | unicode names, folding, non-Latin kept | A `NormalizationTest` (exists); A* `qa-nonascii/qa-unicode.m3u` | section 7 |
| TC-PARSE-08 | scheme allow-list | A `test_attributes_fixture` (3 skipped); A* `qa-schemes.m3u` | 13 allowed (14 until D-QA-07), 21 skipped, 2 orphans |
| TC-PARSE-09 | empty playlist and HTML page | A `test_empty_playlist_is_an_error` (exists); A* `qa-empty.m3u`, `qa-not-m3u.html` | `empty_playlist`; `not_a_playlist` (lane A's code name for the D-QA-13 case; v0.1 wrote `not_m3u`) |
| TC-PARSE-10 | 10k parse time and cache size | PERF-01 | |
| TC-PARSE-11 | XMLTV plain/gz/offsets | TC-EPG-05..11 | |
| TC-MODEL-01 | normalisation and id vectors shared with the helper | A `node tests/Model.test.js`, `tests/Model.spec.qml`, `tests/test_playlist.py::test_fold_table_matches_model_js` (exist) | identical vectors |
| TC-MODEL-02 | filter ranking, cap, favorites-first (R3, R4) | A* `Model.test.js` | |
| TC-MODEL-03 | groups, zap ring, `nextInGroup` wrap (R9, UX 3.4) | A `Model.test.js` (exists, extend for ring by launch list) | |
| TC-MODEL-04 | state parse/toggle/recents, tolerant of garbage | A `Model.test.js` (exists) | |
| TC-MODEL-05 | settings lookup and clamps (R2) | A `Model.test.js` (`findBarEntry`, `clampInt`; extend for 360/15/1440 and `barLabelMaxWidth`) | |
| TC-MODEL-06 | mpv argv: reserved, `--no-` forms, case (D-QA-11), URL after `--`, headers | A `Model.test.js` (exists, extend) | |
| TC-MODEL-07 | Model.js loads in the Qt engine | A `QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml` (exists) | 8+ PASS |
| TC-MODEL-08 | Guide/BarWidget specs (PLAN M1-17) | A* `qmltestrunner -input tests/Guide.spec.qml`, `tests/BarWidget.spec.qml` | states render from fixture JSON, key routing |

### 1.2 User stories -> test cases

| Story | Test cases |
|---|---|
| US1 Configure | TC-CFG-01..13, TC-UI-01, TC-UI-02, TC-UI-03, TC-BAR-02, TC-BAR-04, SEC-07, SEC-08, SEC-12 |
| US2 Browse | TC-BRW-01..25, TC-UI-09, TC-UI-10, TC-BRW-22, PERF-02, PERF-03 |
| US3 Watch | TC-PLAY-01..14, TC-INST-09, SEC-03, SEC-05, SEC-06, SEC-13, SEC-17 |
| US4 Now playing | TC-BAR-01..12, TC-CFG-09, TC-CFG-10 |
| US5 Favorites and recents | TC-FAV-01..11, TC-INST-08, TC-CFG-11 |
| US6 EPG | TC-EPG-01..12, TC-CFG-06, PERF-04 |
| US7 Refresh | TC-RFR-01..10, TC-CFG-07, TC-BAR-05, TC-BAR-08 |
| US8 Install and uninstall | TC-INST-01..10, SEC-14, SEC-15, SEC-16 |

### 1.3 Rulings R1-R13 -> test cases

| Ruling | Test cases |
|---|---|
| R1 keyboard model (search mode on open, Tab or `/` to list mode, no Ctrl chords, Esc peels) | TC-BRW-05, 10, 12, 13, 14, 15, 16, TC-UI-09 |
| R2 settings schema (refreshMinutes 360/15/1440, barLabelMaxWidth 180/60/600) | TC-CFG-07, TC-CFG-10, TC-MODEL-05, D-QA-05 |
| R3 result cap 200 with `First 200 of N - keep typing` | TC-BRW-09, TC-MODEL-02 |
| R4 searchKey = fold(name + " " + group), AND terms, four tiers, favorites first | TC-BRW-07, TC-BRW-08, TC-MODEL-01, TC-MODEL-02, TC-PARSE-07 |
| R5 sort and recents; multi-group first segment | TC-BRW-21, TC-BRW-22, TC-FAV-03, TC-FAV-06, TC-FAV-07, TC-PARSE-03 |
| R6 card and layout | TC-UI-14, TC-BRW-24 |
| R7 bar glyphs per state, label elision, wheel steps | TC-BAR-01..05, TC-BAR-09, TC-BAR-10, TC-CFG-10 |
| R8 model fields the guide binds (`failedAt`, `epgFraction` 30 s tick, guide state) | TC-PLAY-05, TC-EPG-02, TC-EPG-08, TC-UI-03 |
| R9 service actions and IPC verbs (`toggle play stop next previous refresh status`) | 5.8 IPC checks, TC-BAR-09, D-QA-04 |
| R10 mpv attached to the service (dies with the shell) | TC-PLAY-11, TC-INST-08 |
| R11 stream failure: notification, **persisted** `failedAt` (amended 2026-09-24), alert glyph | TC-PLAY-05, TC-FAV-07 |
| R12 manual refresh notifies, timer only on failure; never render URLs beyond scheme+host | TC-BAR-08, TC-RFR-01, TC-RFR-02, TC-RFR-03, SEC-07, TC-CFG-13 |
| R13 no animation, no `screen` set (focused monitor) | TC-UI-08, TC-A11Y-04 |

### 1.4 UX.md sections 3, 4, 6, 7 -> test cases

| UX section | Item | Test cases |
|---|---|---|
| 3 (intro) | opens in search mode; footer shows mode | TC-BRW-05, TC-UI-09 |
| 3.1 | `j`/Down, `k`/Up wrap | TC-BRW-10, TC-BRW-13 |
| 3.1 | `l`/Right, `h`/Left column wrap | TC-BRW-11, TC-BRW-13 |
| 3.1 | PgDn/PgUp clamp, End/Home | TC-BRW-10 |
| 3.1 | Enter (play, close, focus; no reload on the playing row) | TC-PLAY-01, TC-PLAY-03 |
| 3.1 | Space (preview, stay open) | TC-PLAY-04, TC-PLAY-10 |
| 3.1 | `f`/`F` | TC-FAV-01, TC-FAV-04, TC-BRW-16 |
| 3.1 | `x`/`X`/Delete | TC-FAV-05 |
| 3.1 | `s`/`S` | TC-PLAY-06 |
| 3.1 | `r`/`R` | TC-RFR-01 |
| 3.1 | `/`, Tab, Shift+Tab | TC-BRW-13 |
| 3.1 | Esc (clear committed query, else close) | TC-BRW-12 |
| 3.1 | `0`-`9`, Shift+Enter reserved, other letters ignored | TC-BRW-14, TC-BRW-15 |
| 3.2 | printable appends, re-filter, cursor 0 | TC-BRW-07 |
| 3.2 | Backspace, Ctrl+Backspace, Ctrl+U | TC-BRW-07 (step 3 includes them) |
| 3.2 | Down/Up, Right/Left, PgDn/PgUp/Home/End | TC-BRW-10, TC-BRW-11 |
| 3.2 | Enter, Tab, Esc | TC-PLAY-01, TC-BRW-13, TC-BRW-12 |
| 3.3 | `SUPER + SHIFT + T`, left/right/middle click, scroll, hover | TC-BRW-01, TC-BAR-06, TC-BAR-07, TC-BAR-08, TC-BAR-09, TC-BAR-01..05 |
| 3.4 | zap ring by launch list | TC-BAR-09 |
| 4.1 | default guide | TC-BRW-05, TC-BRW-06, TC-EPG-02 |
| 4.2 | searching, scope jumped to All | TC-BRW-11, TC-UI-10 |
| 4.3 | row with EPG / without / failed | TC-EPG-02, TC-EPG-03, TC-PLAY-05 |
| 4.4 | not configured | TC-UI-01 |
| 4.5 | loading | TC-UI-02 |
| 4.6 | error with cache (banner) and without | TC-UI-03, TC-RFR-03, TC-CFG-02 |
| 4.7 | now playing cues | TC-UI-04 |
| 4.8 | bar states, vertical bar | TC-BAR-01..05, TC-BAR-10 |
| 6.1 | guide labels | TC-UI-10, TC-EPG-02, TC-PLAY-05, TC-PLAY-06, TC-RFR-01, TC-FAV-01, TC-FAV-05, TC-BRW-09, TC-EPG-01 |
| 6.2 | footer hints | TC-UI-09 |
| 6.3 | empty, loading, error states; bar tooltips | TC-UI-01, TC-UI-02, TC-UI-03, TC-RFR-08, TC-RFR-09, TC-FAV-02, TC-BRW-17, TC-BRW-18, TC-BRW-24, TC-BAR-01..05 |
| 6.4 | notifications | TC-PLAY-05, TC-BAR-08, TC-RFR-03, TC-CFG-02, TC-EPG-04, TC-PLAY-13, SEC-07 |
| 7.1 | accessible roles and names | TC-A11Y-01, TC-BAR-11 |
| 7.2 | no colour-only status | TC-A11Y-02 |
| 7.3 | hit targets, wheel behaviour | TC-A11Y-03, TC-BRW-23 |
| 7.4 | multi-monitor | TC-A11Y-04 |
| 7.5 | focus and the mpv window | TC-PLAY-01, TC-PLAY-03, TC-PLAY-07, TC-PLAY-14 |
| 7.6 | performance ergonomics | PERF-02, PERF-03 |

## 2. Automated test inventory expected from the FE lanes

Exact commands (all present on the machine of record; run from the repo root):

```
scripts/check.sh                                                     # everything below plus the ASCII gate
omarchy plugin validate .                                            # G0 manifest
mkdir -p /tmp/qmlroot/qs && ln -sfn /usr/share/omarchy/shell/Commons /tmp/qmlroot/qs/Commons \
  && ln -sfn /usr/share/omarchy/shell/Ui /tmp/qmlroot/qs/Ui \
  && /usr/lib/qt6/bin/qmllint -I /tmp/qmlroot -I /usr/lib/qt6/qml Service.qml BarWidget.qml Guide.qml tests/*.qml
node tests/Model.test.js                                             # G1 model (node 26 via mise, dev only)
python3 -m unittest discover -s tests                                # G1 helper
python3 -m unittest discover -s tests -v 2>&1 | tail -3              # count
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Guide.spec.qml      # M1-17
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/BarWidget.spec.qml  # M1-17
```

Scaffold baseline on 2026-09-12 (commit 7a26b6d): 61 node checks, 28 python
tests, 8 qml PASS, `check.sh: all green`. qmllint warnings accepted:
unqualified access / missing property on injected `bar`, `shell`, `service`.

What QA expects each suite to contain when M1 lands (a missing item is a
P3 "coverage" defect unless it guards a P1/P2 behaviour):

| Suite (owner) | Expected cases | Fixture |
|---|---|---|
| `tests/test_playlist.py` (lane A) | existing 20 + `qa_groups` (R5 first segment, EXTGRP persist/clear, empty EXTGRP, padded/leading-semicolon groups), `qa_attrs` (url-tvg beats x-tvg-url, bare and uppercase attributes, repeated attribute = last wins, duplicate tvg-id -> url hashes, `#2` suffix, empty title never uses the URL [D-QA-02], tvg-name fallback, broken EXTINF, blank line before URL, tab-separated attributes, lost first EXTINF), `qa_headers` (UA/referrer, VLCOPT before EXTINF, bare CR stripped, percent-encoded CRLF stripped, bad header name dropped + warning, metacharacters verbatim, option-looking key rejected [D-QA-09], empty value dropped [D-QA-10], uppercase key, no leak after a skipped URL), `qa_schemes` (allow-list incl. mpv pseudo-protocols, empty host [D-QA-07], orphans counted), `qa_empty`, `qa_not_m3u` [D-QA-13], `qa_unicode` (fold vectors incl. NFD [D-QA-08], non-Latin kept, emoji round trip), `qa_bom_crlf` | `tests/fixtures/qa-*.m3u`, `tests/fixtures/qa-nonascii/*.m3u` |
| `tests/test_helper.py` (lane A) | existing 7 + `too_large` on a sparse 65 MB file (`truncate -s 65M`), `unsafe_path` for `/proc/self/environ` and a symlink into `/proc`, `/dev/zero` refused, gzip bomb capped [D-QA-06], `--timeout` honoured against a listening-but-silent socket, status file written on every failure, `fetchedAt` carried over when stale | synthetic in tmp |
| `tests/test_epg.py` (lane A, new) | clock pinned to T0 (a `--now` flag or env var is the recommended seam): plain vs gz identical; offsets +0100/-0500/+0530/none/12-digit; overlap, gap, nostop, far (+-24 h window), orphan, nochannel; `@SD` ids; unicode; `epg-now.json` shape (`version`, `generatedAt`, `validUntil`, `channels.<id>.now/next`); `--now-only` recompute without fetch; `too_large` (64 MB cap on the compressed download AND on inflated bytes), `bad_gzip`, HTTP errors; XML entity expansion does not explode (SEC-19); restrict to playlist ids when `channels.json` exists | `tests/fixtures/qa-epg.xml`, `tests/fixtures/qa-nonascii/qa-epg.xml.gz`, generated `gen-*.xml.gz` |
| `tests/test_mpv_ipc.py` (lane A, new) | fake `AF_UNIX` server: `play` sends `set_property title`, `set_property force-media-title`, per-file header options, `loadfile <url> replace`; `stop` sends `quit`; `status` parses `media-title`, `paused`, `idle-active`; `not_running` unlinks a stale socket; `ipc_error` on garbage; `unknown_channel` when the id is not in `channels.json`; never prints the URL | synthetic |
| `tests/test_state.py` (lane A, only if the `state` subcommand ships) | dump/favorite/recent round trip, atomic write, corrupt file tolerated | synthetic |
| `tests/Model.test.js` (lane B) | existing 61 + tiers 0-3 with favorites first and playlist order inside a tier; cap 200 + `truncated`; `tokenize` folds the query; `groupChannels` order (Recent, Favorites always, All, groups in first-seen order, `Ungrouped` last); zap ring by launch list (Favorites/group/All, Recent -> channel's group, wrap); `pushRecent` cap/dedupe/replay-to-top; `parseState` garbage; `clampInt` 360/15/1440 and 180/60/600; `splitMpvArgs` reserved incl. `--no-` forms and case [D-QA-11]; `headerArgs` drops CR/LF and empty values; `buildMpvArgv` order (reserved first, headers, user args, `--`, url); `formatClock` 24 h; `formatEpgLine` expired now; `elide`; every UX 6 string present in `Copy.js` | none |
| `tests/Model.spec.qml` (exists) | keep the vectors in sync with node | none |
| `tests/Guide.spec.qml`, `tests/BarWidget.spec.qml` (lane B, M1-17) | states from fixture JSON (not configured, loading, error+cache, error no cache, empty favorites, no matches), footer hints per mode, key routing search vs list mode, `Accessible.name` composition, bar label elision at `barLabelMaxWidth`, glyph per state, click routing with a fake `bar` | `tests/fixtures/qa-*.json` may be added by lane B with the qa- prefix if needed (coordinate with QA) |

Coverage check QA runs after the merge:

```
grep -c 'def test_' tests/test_*.py
node tests/Model.test.js | grep -c '^ok'
grep -o 'qa-[a-z-]*\.\(m3u\|xml\|gz\|html\)' tests/test_*.py tests/*.js tests/*.qml | sort | uniq -c   # every fixture referenced
```

## 3. Security test cases (ARCHITECTURE.md section 8, PLAN gate G4)

Run from the repo root (static) and on the live shell (dynamic). Expected
output is empty unless stated.

| ID | Standard | How | Expected |
|---|---|---|---|
| SEC-01 | 8.1 argv only, no shell strings | A `grep -rnE 'bash -c|sh -c|shell=True|os\.system|subprocess\.(call|run|Popen)\([^\[]|execDetached\("|command: "|\beval\(' --include='*.qml' --include='*.js' --include='*.py' --include='omarchy-iptv' . \| grep -v '^./tests/' \| grep -v '^./docs/'` | nothing (the helper is invoked with `["python3", helperPath, ...]`, mpv with `Model.buildMpvArgv`, notifications with an array) |
| SEC-02 | 8.6 no sudo/pkexec | A `grep -rnE 'sudo|pkexec|doas' --include='*.qml' --include='*.js' --include='*.py' --include='omarchy-iptv' . \| grep -v '^./tests/' \| grep -v '^./docs/'` | nothing |
| SEC-03 | 8.2 header injection with CR/LF | A* `qa-headers.m3u` (`cr.test`, `kodicrlf.test`); A `Model.test.js` (`headerArgs` drops values containing `\r`/`\n`); M TC-PLAY-08 | `channels.json` values contain no CR/LF (bare CR -> space, `%0D%0A` -> spaces); mpv argv shows one `--user-agent=` item |
| SEC-04 | 8.2 header names validated | A* `qa-headers.m3u` (`Bad%0AName` dropped, warning `dropped header with unsafe name for ...`) | as stated |
| SEC-05 | 8.3 stream scheme allow-list | A* `qa-schemes.m3u` | allowed: http https rtsp udp rtp rtmp rtmps mms mmsh srt, uppercase scheme, padded line, option-looking suffix inside the line; dropped and counted: file, bare path, `~`, relative, ftp, plugin, javascript, data, `--script=`, `--`, edl, mf, av, lavf, fd, memory, ytdl, smb, dvd, null, protocol-relative; `http://` with no host must be dropped too (D-QA-07) |
| SEC-06 | 8.2 URL after `--`, option-looking lines never reach mpv | A `Model.test.js` (`buildMpvArgv url after --`); M `ps -o args= -p $(pgrep -f wayland-app-id=omarchy-iptv)` | last two argv items are `--` and the URL |
| SEC-07 | 8.7, R12 URL redaction at every sink | A: enumerate sinks with `grep -nE 'console\.(log|warn|error|info)|notify\(|showTooltip|tooltipText|statusLine|lastError|stderr|stdout|emit\(|sys\.stderr' Service.qml Guide.qml BarWidget.qml bin/omarchy-iptv` and check each argument cannot carry a URL (current sinks: `Service.qml` `notify()` body from `mpvStderrTail` [D-QA-01], `lastError` -> `Guide.statusLine` and IPC `status` [D-QA-01, D-QA-15], `console.warn("omarchy-iptv playlist:", stderr)` (helper stderr carries host only, but local paths [D-QA-12]), `BarWidget.tooltip` (`error.message`), channel `name` [D-QA-02]); M 5.9: `grep -nE '(https?|rtsp|rtmp)://[^ ]*[@?]|password=|username=' journal.txt qs-log.txt` and the notification history (`omarchy-shell notifications showHistory`) after TC-PLAY-05 with a credentialed dead URL from `qa-attrs.m3u` (`http://user:secret@stream.example.test/...`) | no match anywhere |
| SEC-08 | 8.4 local source path rules | A* `tests/test_helper.py`: `/proc/self/environ` -> `unsafe_path`, `/dev/zero` -> `too_large` (reads at most 64 MB + 1), `/sys/...` -> `unsafe_path`; M `omarchy bar set ... playlistUrl /proc/self/environ` | error rendered, no traceback, no hang |
| SEC-09 | 8.4 symlink to a forbidden path | A* `ln -s /proc/self/environ $tmp/list.m3u` -> `unsafe_path` (realpath check) | as stated |
| SEC-10 | 8.4 `file:///etc/passwd` as the *source* | A `qa-schemes.m3u` covers the *stream* case; as a source it is the user's own readable file: parses to 0 channels -> `empty_playlist` | not a defect; document |
| SEC-11 | 8.4 size caps | A* sparse 65 MB file -> `too_large` in well under a second (`truncate -s 65M`); gzip bomb: `python3 -c "import gzip,sys; sys.stdout.buffer.write(gzip.compress(b'#EXTM3U\n'+b'\0'*(100<<20)))" > bomb.m3u.gz` (about 100 KB) as playlist and as EPG source -> `too_large`, RSS stays under 300 MB (D-QA-06 until fixed) | as stated |
| SEC-12 | 8.4 source schemes | A `tests/test_playlist.py::SourceTest::test_refuses_other_schemes` (exists): ftp, relative, javascript, empty; add `data:`, `//host/x` (protocol-relative), `FILE:///etc/hosts` (uppercase scheme is accepted today; decide and pin) | refused or pinned |
| SEC-13 | 8.9, section 6 reserved `mpvArgs` | A `Model.test.js` (exists); extend: `--INPUT-IPC-SERVER=x` [D-QA-11], `--no-title`, `--script-opts=x` allowed, `--include=/path` (loads an mpv config that can override reserved options; user's own trust level, document as a known limitation or add to the reserved list) | reserved names dropped with one console warning |
| SEC-14 | 8.5 file modes and locations | M 5.7 `stat -c '%a %n'` | `~/.cache/omarchy-iptv` 700, files 600; `~/.local/state/omarchy-iptv` 700, `state.json` 600; `/run/user/1000/omarchy-iptv` 700, `mpv.sock` owned by the user; nothing under the plugin dir |
| SEC-15 | 8.5 no writes inside the plugin directory | M 5.7 `find` | nothing |
| SEC-16 | 8.6 no symlinks in the repo | A `omarchy plugin validate .`; `find . -name .git -prune -o -type l -print` | nothing |
| SEC-17 | 8.8 IPC acts only on cached ids | M 5.8: `omarchy-shell io.github.rmcdavid.iptv play 'http://evil.example.test/x'` and `play '--script=/tmp/x'` | reply `unknown`, nothing launched |
| SEC-18 | 8.6 no network from QML | A `grep -rnE 'XMLHttpRequest|fetch\(|Qt\.openUrlExternally|WebSocket' *.qml Model.js` | nothing |
| SEC-19 | XMLTV entity expansion / external entities | A* small XML with a 10x10 nested entity (`<!ENTITY a "aaaa..."><!ENTITY b "&a;&a;...">`) and an external entity `<!ENTITY x SYSTEM "file:///etc/passwd">` as EPG source | parse error or bounded memory; external entity never read (`xml.etree` does not resolve them); `bad_xml`/`network` style error surfaced |
| SEC-20 | 8.4 redirects | A* mock `http://` source that redirects to `file:///etc/passwd` and to `ftp://` | `urllib` refuses non-http redirects -> `network` error; https -> http downgrade is allowed by urllib (document) |
| SEC-21 | credentials in `channels.json` (section 6 caveat) | M 5.7 | file 0600 in a 0700 dir; README settings section warns that `shell.json` and the cache contain the provider credentials |

## 4. Performance gate (PLAN G3, ARCHITECTURE.md section 7, QB4)

Inputs: `https://iptv-org.github.io/iptv/index.m3u` (11,041 entries, 2.5 MB)
and, offline, `scripts/gen-playlist.py --channels 10000 --groups 120 --seed 1
--epg-ids 0.6 --out /tmp/omarchy-iptv-qa/gen-10k.m3u --xmltv
/tmp/omarchy-iptv-qa/gen-10k.xml.gz --hours 24` (deterministic: m3u sha256
`63061a85cd2183f67a0b009c6f8cb9891b59af2c54bdf0db5ad1fb8ff18c50fe`, 1,844,026
bytes, 10,000 channels, 120 group strings;
RE-PINNED 2026-09-23: the previous hash `0aa5acc2...` at 1,841,211 bytes predates
M2-03, which made the generator emit `tvg-chno` on every entry. Determinism was
re-verified rather than assumed -- two runs with the same flags are byte-identical
-- so the old hash was stale, not a regression, and anyone re-running this gate
against it would have started by chasing a fixture that was fine; XMLTV 41.3 MB inflated, 5,840
channels, 266,474 programmes). Never commit generated files.

Baseline measured on the scaffold helper (2026-09-12, this machine): `playlist`
on `gen-10k.m3u` -> `durationMs: 505`, wall 0.64 s, `channels.json` 2,579,498
bytes (over the ~2 MB budget because the synthetic profile fills `tvgName`,
`logo`, `chno`; re-measure with `index.m3u`). A pure `xml.etree.iterparse`
pass over the 41 MB gz takes 1.6 s in Python 3.14 here, so the 4 s EPG budget
leaves room for the now/next projection.

| ID | Budget | Procedure | Record |
|---|---|---|---|
| PERF-01 | helper `playlist` < 1.5 s for 10k (ARCH), < 1 s (PLAN G3) | `time python3 ~/.config/omarchy/plugins/io.github.rmcdavid.iptv/bin/omarchy-iptv playlist --url /tmp/omarchy-iptv-qa/gen-10k.m3u --cache-dir /tmp/omarchy-iptv-qa/cache`; read `durationMs`; repeat with a local copy of `index.m3u` (`curl -o /tmp/omarchy-iptv-qa/index.m3u https://iptv-org.github.io/iptv/index.m3u`) | both numbers, `channels.json` size, `groupCount` |
| PERF-02 | overlay open < 150 ms with the 10k cache | Method A (IPC round trip, includes the synchronous `open()` work but not the frame): with `playlistUrl` set to the 10k file and the guide closed, run `for i in 1 2 3 4 5; do t0=$(date +%s%N); omarchy-shell shell toggle io.github.rmcdavid.iptv '{}'; t1=$(date +%s%N); echo open $(( (t1-t0)/1000000 )) ms; sleep 1; t0=$(date +%s%N); omarchy-shell shell toggle io.github.rmcdavid.iptv '{}'; t1=$(date +%s%N); echo close $(( (t1-t0)/1000000 )) ms; sleep 1; done` and the baseline `for i in 1 2 3 4 5; do t0=$(date +%s%N); omarchy-shell shell ping; t1=$(date +%s%N); echo $(( (t1-t0)/1000000 )); done`; open time = median(open) - median(ping). Method B (frame): ask lane B for an opt-in debug line (`OMARCHY_IPTV_DEBUG=1` or a `debug` setting) that logs `console.info("omarchy-iptv guide open <ms since epoch>")` at the top of `open()` and once after the first frame (`Qt.callLater` chained twice after `visible = true`, or the window's `frameSwapped`); read both from `journalctl --user -t omarchy-shell`. Method C (perception): open the clipboard (`SUPER CTRL + V`) and the guide alternately; the guide must not feel slower | median and max of 5 opens, method used |
| PERF-03 | keystroke to redraw < 30 ms, no dropped keys, 40 ms coalescing allowed | with the guide open on the 10k cache: `wtype -d 20 'alpha news channel'` then `wtype -d 0 'zzzzzzzzzzzzzzzzzzzz'` (20 keys, no delay); every character must appear in the header in order and the scope label must settle on the right count; no `WARN` in the journal. Micro-benchmark of the pure filter: `node -e 'const M=require("./Model.js");const c=JSON.parse(require("fs").readFileSync(process.env.HOME+"/.cache/omarchy-iptv/channels.json")).channels;for(const q of ["a","news","alpha news","zz"]){const t=process.hrtime.bigint();for(let i=0;i<50;i++)M.filterChannels(c,q,200);console.log(q,Number(process.hrtime.bigint()-t)/50/1e6,"ms")}'` (run from the plugin dir after the merge; the node file must expose `filterChannels`) | ms per query, dropped keys yes/no |
| PERF-04 | helper `epg` < 4 s for a 50 MB XMLTV, RSS < 300 MB | `python3 - <<'EOF'` wrapper (GNU `time` is not installed): `import resource,subprocess,time;t=time.monotonic();p=subprocess.run(["python3","<plugindir>/bin/omarchy-iptv","epg","--url","/tmp/omarchy-iptv-qa/gen-10k.xml.gz","--cache-dir","/tmp/omarchy-iptv-qa/cache"]);print("exit",p.returncode,"wall %.2fs"%(time.monotonic()-t),"maxrss MB",resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss/1024)`; then `ls -l /tmp/omarchy-iptv-qa/cache/epg-now.json` (< 1 MB at 10k) and `time ... epg --now-only ...` (recompute, expected well under 1 s); repeat with the Pluto gz (955,717 bytes) | wall, RSS, file size |
| PERF-05 | shell memory | `ps -o rss= -p $(pgrep -f 'quickshell -n -p /usr/share/omarchy/shell')` before enabling, after the 10k cache loads, after 20 guide opens | three RSS values (informational, no budget) |
| PERF-06 | zap under 2 s of interaction | stopwatch from `SUPER + SHIFT + T` to the first mpv frame on a live channel (`us.m3u`) after typing three letters and Enter; try three channels | seconds, channel used |
| PERF-07 | refresh does not stall the shell | while the 10k helper runs (`r`), move the cursor and type; the bar clock keeps ticking | pass/fail |

Record all numbers in `docs/STATUS.md` (M1.1-03 evidence) with the commit id
of the plugin under test.

## 5. Live-shell runbook (this machine)

`scripts/qa-live.sh` prints every command of phases 5.1, 5.2, 5.3, 5.7, 5.9
and 5.10 and only executes them with `--apply`; it refuses `install` when the
plugin directory exists unless `--force`, and refuses a non-interactive
`uninstall --apply` unless `--force`. The steps below are the source of truth;
the script is a convenience.

### 5.0 Preconditions and what the pass changes on this machine

- The lead has merged both FE lanes and `scripts/check.sh` is green at the
  commit under test; note the commit id (`git -C <repo> rev-parse --short HEAD`).
- Files touched during the pass: `~/.config/omarchy/plugins/io.github.rmcdavid.iptv`
  (git clone), `~/.config/omarchy/shell.json` (one entry `{"id":
  "io.github.rmcdavid.iptv", ...settings}` appended to `bar.layout.right` by
  `omarchy plugin enable`, keys added by `omarchy bar set`), `~/.cache/omarchy-iptv`,
  `~/.local/state/omarchy-iptv`, `/run/user/1000/omarchy-iptv`, and the
  evidence directory `/tmp/omarchy-iptv-qa`. Optional, by hand and reverted
  in 5.10: one line in `~/.config/hypr/bindings.lua`, one entry in
  `~/.config/omarchy/extensions/omarchy-menu.jsonc`. Nothing under
  `/usr/share/omarchy` is touched.
- Restore path: `omarchy plugin remove io.github.rmcdavid.iptv --yes` removes
  the bar entry (PluginRegistry.setEnabled false splices it out) and the clone;
  the snapshot `shell.json.before` proves the file is back to its pre-install
  content; the three runtime directories are deleted by hand.
- Where the shell console goes on this machine: `journalctl --user -t
  omarchy-shell` (durable, timestamps; the shell is started with
  `systemd-cat -t omarchy-shell`), `qs log -p /usr/share/omarchy/shell --tail
  200` (same lines, coloured, from `/run/user/1000/quickshell/by-pid/<pid>/log.log`),
  `qs log -p /usr/share/omarchy/shell -f` to follow during a test. Our lines
  are prefixed `omarchy-iptv`. Helper stderr lands there through
  `console.warn("omarchy-iptv playlist:", ...)`.

### 5.1 Preflight (read-only)

```
scripts/qa-live.sh preflight
```

Expect: versions as in the header of this file; `SUPER SHIFT + T is free`;
no `omarchy-iptv` directories; `entries in bar.layout: 0`; playlist HEAD
`HTTP/2 200`; EPG resolves through two 302s to `raw.githubusercontent.com`
with `content-length: 955717` (the helper must follow redirects; `urllib`
does by default). Record the current theme (`retropc`).

### 5.2 Install (TC-INST-01..04)

```
export REPO=/home/ricky/Projects/omarchy-iptv           # or the git URL of the merge commit
scripts/qa-live.sh install --apply --repo "$REPO"
```

which runs: snapshot `shell.json` (0600) to `/tmp/omarchy-iptv-qa/shell.json.before`,
`git clone -- "$REPO" ~/.config/omarchy/plugins/io.github.rmcdavid.iptv`
(never a symlink; the validator rejects them), `omarchy plugin validate <dir>`,
`omarchy-shell shell rescanPlugins`, `omarchy plugin enable io.github.rmcdavid.iptv`
(bar widget lands in `right`, the manifest default), `omarchy plugin list --json`.

Expected: `Enabled io.github.rmcdavid.iptv`; the JSON row shows `"enabled":
true`, `"kinds": ["bar-widget","overlay","service"]`; `jq '.bar.layout.right[-1]'
~/.config/omarchy/shell.json` prints `{"id":"io.github.rmcdavid.iptv"}`; the
bar shows the idle glyph U+F0502 at the right; `journalctl --user -t
omarchy-shell --since "$(cat /tmp/omarchy-iptv-qa/started-at)"` has no WARN/ERROR
from our files (TC-INST-04). Also run `omarchy-shell shell listPlugins | jq
'.[] | select(.id=="io.github.rmcdavid.iptv")'`.

### 5.3 Configure (TC-CFG-01, TC-BRW-01, TC-BRW-04)

```
scripts/qa-live.sh configure --apply                       # us.m3u + Pluto EPG
# or by hand:
omarchy bar set io.github.rmcdavid.iptv playlistUrl https://iptv-org.github.io/iptv/countries/us.m3u
omarchy bar set io.github.rmcdavid.iptv epgUrl https://i.mjh.nz/PlutoTV/us.xml.gz
```

Then add, by hand, the README one-liners (they are user-side files; revert
them in 5.10):

```
# ~/.config/hypr/bindings.lua
o.bind("SUPER + SHIFT + T", "IPTV", "omarchy-shell shell toggle io.github.rmcdavid.iptv")
# ~/.config/omarchy/extensions/omarchy-menu.jsonc (hot reload)
"iptv": {"icon":"<U+F0567>","label":"IPTV","aliases":["tv","iptv"],"action":"omarchy-shell shell toggle io.github.rmcdavid.iptv"},
```

If the lead prefers not to touch `bindings.lua`, run TC-BRW-01 as
`omarchy-shell shell toggle io.github.rmcdavid.iptv` and mark the keybinding
row `not run (binding not installed)`.

Note the EPG: Pluto ids are 24-hex Pluto ids, iptv-org `tvg-id`s are
`Name.us`, so matching is partial by design (QA-ASSETS.md). For a fully
matched EPG use the generator: `playlistUrl /tmp/omarchy-iptv-qa/gen-real.m3u`
and `epgUrl /tmp/omarchy-iptv-qa/gen-real.xml` produced by
`scripts/gen-playlist.py --profile realistic --channels 1500 --groups 40 --seed 7
--multi-group 0.25 --out /tmp/omarchy-iptv-qa/gen-real.m3u --xmltv
/tmp/omarchy-iptv-qa/gen-real.xml` (omit `--now` so the window is centred on
the current hour; the URLs are `.test` hosts and will fail to play, which is
fine for EPG rows).

### 5.4 Story checklists

Record each numbered step as pass/fail with the TC ids in brackets.
Microcopy in backticks is verbatim from UX.md section 6 (with the real
codepoints for `...`, quotes and the middle dot).

#### US1 Configure (TC-CFG-*, TC-UI-01..03, TC-BAR-02/04)

1. Before setting `playlistUrl` (do this once, right after 5.2): hover the
   widget -> tooltip `IPTV - no playlist configured`; open the guide ->
   `No playlist configured`, body `Set your M3U URL or path, then press r to
   load it:`, command box `omarchy bar set io.github.rmcdavid.iptv playlistUrl
   <url>`, `Optional EPG:  omarchy bar set io.github.rmcdavid.iptv epgUrl <url>`,
   `Settings live in ~/.config/omarchy/shell.json (entry io.github.rmcdavid.iptv)`,
   no group column, hint `r reload - Esc close`, glyph U+F0502; click the box,
   `wl-paste` prints the command, footer `Copied` [TC-UI-01, TC-BAR-02].
2. Set `playlistUrl` (5.3) with the guide open: within a second the state
   becomes `Loading playlist...` / `Fetching from iptv-org.github.io` (host
   only) with hint `Esc close` [TC-UI-02], then the list renders; footer
   `1,475 channels - updated HH:MM` (count as of the live list; it drifts);
   tooltip `IPTV - click to open the guide` [TC-CFG-01, TC-CFG-12].
3. `journalctl --user -t omarchy-shell --since -2m | grep omarchy-iptv`: one
   helper run, no URL in any line [TC-CFG-13].
4. `omarchy bar set io.github.rmcdavid.iptv playlistUrl https://iptv-org.github.io/iptv/countries/nope.m3u`;
   with a cache present: banner `U+F0026 Playlist refresh failed (HTTP 404 Not
   Found) - showing cached copy from HH:MM - r retry`, footer `1,475 channels -
   cached HH:MM - offline`, notification `Playlist error` / `Could not fetch the
   playlist (HTTP 404 Not Found). Using cached copy from HH:MM.`; then
   `rm -rf ~/.cache/omarchy-iptv/*` and press `r`: empty state `Playlist failed
   to load` / `HTTP 404 Not Found from iptv-org.github.io - check playlistUrl`,
   hint `r reload - Esc close`, glyph U+F0503, bar glyph U+F0503 and tooltip
   `IPTV - playlist error, open the guide`, notification body `... Open the
   guide for details.` [TC-CFG-02, TC-UI-03, TC-BAR-04].
5. `omarchy bar set io.github.rmcdavid.iptv playlistUrl https://does-not-exist.invalid/x.m3u`
   -> reason `Could not resolve host` [TC-CFG-03].
6. Restore the US list (5.3); confirm the guide, still open, recovers without
   restart [TC-CFG-12].

#### US2 Browse (TC-BRW-*, TC-UI-08..10)

1. Open with `SUPER + SHIFT + T`; close with the same key. Open with a left
   click on the widget; close with a click. `omarchy-shell shell toggle
   io.github.rmcdavid.iptv` twice. No fade in or out [TC-BRW-01..03, TC-UI-08].
2. On open: header `Search channels...`, scope label `All - 1,475 channels`
   (or `Favorites - N channels` once favorites exist), column `Favorites`,
   `All`, `GROUPS`, groups in playlist order with counts, `Recent` absent
   until something played; footer hint `Enter play - Up/Down move -
   Left/Right group - Tab keys - Esc close`; cursor on row 0 [TC-BRW-05,
   TC-BRW-06, TC-BRW-21, TC-UI-09, TC-UI-10].
3. Type `news`: label `in All - N matches`, hint changes to `... Left/Right
   narrow - Tab keys - Esc clear`; type ` sp` (space, letters): fewer rows
   (AND); Backspace, Ctrl+Backspace (word), Ctrl+U (clear) behave; type `TELE`
   then a channel with an accented name should match its unaccented spelling
   (the US list has few; use `gen-real.m3u` or `qa-nonascii/qa-unicode.m3u`
   as a local playlist to prove `tele` finds `Tele Quebec` with accents)
   [TC-BRW-07].
4. With `index.m3u` or `gen-10k.m3u` as playlist, type `a`: footer `First 200
   of N - keep typing`, exactly 200 rows [TC-BRW-09].
5. Down from the last row wraps to the first; Up from the first wraps to the
   last; PgDn moves by visible rows minus one and stops at the end; End, Home
   [TC-BRW-10].
6. Right/Left move the column highlight (wraps at both ends); on Favorites,
   start typing -> highlight jumps to All; clear the query -> back to
   Favorites [TC-BRW-11].
7. With a query: Esc clears it, guide stays; Esc again closes. Then
   `omarchy-shell shell toggle io.github.rmcdavid.iptv` opens on the first
   call (host state in sync) [TC-BRW-12].
8. Type `spo`, press Tab: query committed, hint `j/k move - h/l group - Enter
   play - Space preview - f favorite - s stop - r refresh - / search`; j/k/h/l
   move; `/` returns to search mode with `spo` still in the header; Shift+Tab
   also enters search mode [TC-BRW-13].
9. In list mode press `q`, `w`, `e`, `4`: nothing happens; press `F`, `S`,
   `R`, `X`: same as lowercase. In search mode `4k` filters [TC-BRW-14..16].
10. Move the column to a real group, type `zzzz`: `No matches for "zzzz" in
    <group>` with `h/l other groups - Home for All`; press Home: column jumps
    to All; clear, on All type `zzzz`: `No matches for "zzzz"` / `Esc clears
    the search` [TC-BRW-17, TC-BRW-18].
11. Mouse: hover moves the cursor only after the pointer moves; move with keys,
    leave the pointer still over another row: the cursor stays; click the scrim:
    closes; click inside the card on empty space: nothing; wheel over the list
    scrolls, over the column moves the selection one per tick; the lead slot
    (star column) is clickable [TC-BRW-19, TC-BRW-23, TC-A11Y-03].
12. Focus a terminal, open the guide over it, type `ls` and Enter: the terminal
    receives nothing; the guide filtered and (if a match) played [TC-BRW-20].
13. Find a multi-group entry in the US list (`grep -c 'group-title="[^"]*;'
    /tmp/omarchy-iptv-qa/us.m3u` after `curl -o`), e.g. `Animation;Kids`: it
    is listed once under `Animation` and found by typing `kids` [TC-BRW-22].

#### US3 Watch (TC-PLAY-*, TC-INST-09)

1. Search a live channel (news channels on the US list usually work), Enter:
   guide closes, exactly one mpv window appears with the channel name as title,
   focused. Stopwatch from the key to the first frame [TC-PLAY-01, TC-PLAY-12].
   Verify in 5.7.
2. Reopen, Enter on a different live channel: same window (same pid in
   `hyprctl clients -j`), title changes [TC-PLAY-02].
3. Reopen, cursor is on the playing row (bold, glyph U+F040A); Enter: no
   reload (no black frame; `omarchy-shell io.github.rmcdavid.iptv status` shows
   the same channel), guide closes, mpv focused [TC-PLAY-03].
4. Reopen, Space on three different rows within two seconds: guide stays open,
   the cues (bold + U+F040A + footer `U+F040A <name> - s stop`) move each time,
   playback ends on the third; still one mpv [TC-PLAY-04, TC-PLAY-10, TC-UI-04].
5. Dead stream: use `gen-dead.m3u` (`scripts/gen-playlist.py --channels 200
   --groups 5 --seed 3 --dead 0.5 --out /tmp/omarchy-iptv-qa/gen-dead.m3u`; half
   the URLs point at `127.0.0.1:9`, connection refused) or a `qa-attrs.m3u`
   entry. Enter on a dead row: notification `Stream failed` / `<name> did not
   play` (plus ` - <reason>`), glyph U+F0503, urgency normal; a second failure
   replaces the toast (`-r`); guide row shows U+F0026 and `Failed HH:MM - Space
   to retry`; the cursor did not move; the channel is in Recent; bar back to
   U+F0502 [TC-PLAY-05, TC-FAV-07]. Check SEC-07 now: the notification and the
   journal contain no URL (`qa-attrs.m3u` has `http://user:secret@...`; the
   body must not show `user:secret`).
6. Play a live channel, press `s`: footer `Stopped` for 3 s, mpv gone, bar
   idle, no notification. Play again, press `q` inside mpv: bar idle, cues
   clear, no notification [TC-PLAY-06, TC-PLAY-07].
7. Play, then `omarchy-shell shell rescanPlugins`: playback continues, bar
   label unchanged (keepLoaded service) [TC-INST-09].
8. `omarchy bar set io.github.rmcdavid.iptv mpvArgs '--profile=fast --hwdec=auto-safe --input-ipc-server=/tmp/x --title=X --no-idle'`;
   stop and play again; `ps -o args= -p $(pgrep -f 'wayland-app-id=omarchy-iptv')`
   shows `--profile=fast --hwdec=auto-safe`, none of the reserved ones, the
   URL last after `--`; journal has one warning naming the three dropped tokens.
   With `gen-dead.m3u` entries that carry `#EXTVLCOPT`, argv shows
   `--user-agent=Mozilla/5.0 (X11; Linux x86_64) gen-playlist/1.0` as one item
   [TC-CFG-08, TC-PLAY-08, SEC-06]. Reset: `omarchy bar set io.github.rmcdavid.iptv mpvArgs ''`.
9. Optional: `kill -STOP $(pgrep -f wayland-app-id=omarchy-iptv)`; within ~30 s
   (two 10 s health polls) the console logs `mpv unresponsive, restarting
   player` and mpv gets SIGTERM. mpv installs a SIGTERM handler, so a
   SIGSTOPped mpv stays stopped with the signal pending (v0.1 wrongly said
   `kill -CONT` is not needed): run `kill -CONT <pid>` yourself, then check
   that mpv exits and the channel is relaunched once [TC-PLAY-09].
10. Make mpv fullscreen (`f` in mpv), open the guide: it draws above; Esc:
    mpv still fullscreen, not paused, not muted [TC-PLAY-14].

#### US4 Now playing (TC-BAR-*, TC-CFG-09/10)

1. Idle: glyph U+F0502 dimmed, no label, tooltip `IPTV - click to open the
   guide` [TC-BAR-01].
2. Playing: glyph U+F0567, name elided at the default width, tooltip `Playing
   <full name>`; the label width animates (180 ms) when the name changes
   [TC-BAR-03].
3. Left click opens, left click closes [TC-BAR-06].
4. Right click stops [TC-BAR-07].
5. Middle click: tooltip `IPTV - refreshing playlist...` while running, footer
   `Refreshing...` then `Refreshed - 1,475 channels`, notification `Playlist
   refreshed` / `1,475 channels in 38 groups` (live counts), low urgency,
   glyph U+F0450 [TC-BAR-05, TC-BAR-08].
6. Play from a group, scroll down/up over the widget: next/previous channel in
   that group, one per tick, wraps at both ends; play from Favorites (need 2+):
   scroll stays in Favorites; play from Recent: ring is the channel's group.
   On the touchpad a slow two-finger swipe changes one channel, not several
   [TC-BAR-09].
7. `omarchy bar set io.github.rmcdavid.iptv showChannelName false --json`:
   glyph only while playing, tooltip still has the name; set back `true --json`
   [TC-CFG-09].
8. `omarchy bar set io.github.rmcdavid.iptv barLabelMaxWidth 60 --json`: heavy
   elision; `600 --json`: full name; back to `180 --json` [TC-CFG-10].
9. Hover: tooltip text matches the state table in UX 6.3 for every state seen
   so far [TC-BAR-01..05].

#### US5 Favorites and recents (TC-FAV-*, TC-INST-08)

1. On a row press `f`: star U+F04CE in the lead slot, footer `Added to
   Favorites` (3 s); `f` again: star gone, `Removed from Favorites`. Click the
   lead slot of another row: star toggles, nothing plays [TC-FAV-01, TC-FAV-11].
2. Move the column to Favorites while empty: `No favorites yet` / `Press f on
   any channel to pin it here` [TC-FAV-02].
3. Favorite three channels in the order C, A, B: Favorites lists C, A, B;
   reopen the guide: it opens on Favorites (`Favorites - 3 channels`); press
   `f` on A: A leaves, cursor stays on the same index (B) [TC-FAV-03, TC-FAV-04,
   TC-BRW-06].
4. Play two channels; Recent appears first in the column with `Recent - 2
   channels`; on a Recent row press `x`: `Removed from Recent`; in Favorites
   press Delete: unfavorites; on All press `x`: nothing [TC-FAV-05].
5. Play channel A, then B, then A: Recent is A, B (A moved to the top, no
   duplicate). `omarchy bar set io.github.rmcdavid.iptv maxRecents 3 --json`,
   play four channels: Recent shows three; reset to `10 --json` [TC-FAV-06,
   TC-CFG-11].
6. `omarchy restart shell`: mpv exits (R10, expected), the widget comes back,
   favorites and recents are intact, `playlistUrl` intact [TC-FAV-08,
   TC-INST-08, TC-PLAY-11].
7. `omarchy-shell io.github.rmcdavid.iptv stop`; `printf 'garbage' >
   ~/.local/state/omarchy-iptv/state.json`; `omarchy restart shell`: guide opens
   with empty Favorites/Recent, no crash, one warning at most; favorite
   something: the file is valid JSON again [TC-FAV-09].
8. `stat -c '%a %n' ~/.local/state/omarchy-iptv ~/.local/state/omarchy-iptv/state.json`
   -> `700`, `600` [TC-FAV-08, SEC-14].

#### US6 EPG (TC-EPG-*)

1. With `epgUrl` empty, clear the cache dir, set `epgUrl` (Pluto) and open the
   guide immediately: it opens at once; footer `Guide data loading...` (or the
   neutral banner) until `epg-now.json` appears (`ls -l ~/.cache/omarchy-iptv`)
   [TC-EPG-01].
2. With the generator pair from 5.3 (`gen-real.m3u` + `gen-real.xml`): rows
   show `Now: <title> - Next: <title>`, right meta `until HH:MM` (local 24 h),
   the hairline fills proportionally; a group with EPG uses two-line rows
   [TC-EPG-02].
3. Back on `us.m3u` + Pluto: most rows have no `Now:`/`Next:` and no `until`
   (ids do not match by design); inside a group with no EPG the rows are
   single-line [TC-EPG-03].
4. `omarchy bar set io.github.rmcdavid.iptv epgUrl https://i.mjh.nz/PlutoTV/nope.xml.gz`
   then `r`: banner `Guide data unavailable (HTTP 404 Not Found) - channels
   still work - r retry`, notification `Guide data error` / `Could not fetch the
   EPG (HTTP 404 Not Found). Channels still work.` low; playing still works
   [TC-EPG-04]. Restore the EPG URL.
5. Leave the guide open on `gen-real` for 90 s: `until` stays, the hairline
   grows (30 s tick); `journalctl --user -t omarchy-shell -f` shows an
   `epg --now-only` run after 5 min and no download before the TTL
   [TC-EPG-08].
6. Automated checks TC-EPG-05..07, 09..11 run in `python3 -m unittest discover
   -s tests`; if `tests/test_epg.py` is missing, run the helper by hand with the
   clock pinned (whatever seam lane A provides) and compare with the expected
   values in the fixture comment.

#### US7 Refresh (TC-RFR-*, TC-CFG-07)

1. `omarchy bar set io.github.rmcdavid.iptv refreshMinutes 30` (string), then
   `--json 5` (clamps to 15), then `--json 99999` (1440): no error, the timer
   re-arms (journal, or the IPC `status` if it exposes the interval); leave it
   at `15 --json` and note the time; a silent helper run appears at +15 min
   [TC-CFG-07, TC-RFR-02].
2. Play a channel, press `r`: footer `Refreshing...` then `Refreshed - N
   channels`, notification `Playlist refreshed` low, playback untouched
   [TC-RFR-01, TC-RFR-05].
3. Offline simulation without touching the network settings: `cd
   /tmp/omarchy-iptv-qa && python3 -m http.server 8765 --bind 127.0.0.1` (serving
   `gen-10k.m3u`), `omarchy bar set io.github.rmcdavid.iptv playlistUrl
   http://127.0.0.1:8765/gen-10k.m3u`, wait for the load, stop the server
   (Ctrl+C), press `r`: banner `U+F0026 Playlist refresh failed (Connection
   refused) - showing cached copy from HH:MM - r retry`, footer `10,000 channels
   - cached HH:MM - offline`, notification `Playlist error` / `Could not fetch
   the playlist (Connection refused). Using cached copy from HH:MM.`, tooltip
   or footer says cached [TC-RFR-03, TC-RFR-10, TC-UI-03].
4. Restart the server, `r`: banner disappears (140 ms fade), footer back to
   `updated HH:MM` [TC-RFR-03].
5. Press `r` twice within 300 ms (or `r` then middle click): the journal shows
   one helper run [TC-RFR-04].
6. Stop the server, `omarchy restart shell`, open the guide immediately: the
   cached list renders at once, then the banner appears after the failed
   refresh [TC-RFR-06].
7. With the guide open and the cursor on row 50, serve a different file
   (`gen-real.m3u` renamed over `gen-10k.m3u`), press `r`: rows rebuild, the
   cursor is clamped, no crash [TC-RFR-07].
8. Serve `qa-empty.m3u` and `qa-not-m3u.html` in turn (copy them into the
   served directory, point `playlistUrl` at them): `Playlist has no channels`
   / `Parsed 0 channels from 127.0.0.1 - check the URL points at an M3U`, then
   the `Not an M3U file` reason (helper code `not_a_playlist`; at f03fef2 the
   guide shows the raw helper sentence instead, D-LIVE-03); the previous cache
   is kept and marked stale [TC-RFR-08, TC-RFR-09].
9. Restore `playlistUrl` to the US list.

#### US8 Install and uninstall

Covered by 5.2 (install) and 5.10 (uninstall); REL-01 repeats 5.2 from a clean
state with the README commands verbatim, REL-02 repeats 5.10.

### 5.5 Theme switch (TC-UI-05, M1.1-02)

```
current=$(cat ~/.local/state/omarchy/current/theme.name)      # retropc on this machine
omarchy theme set tokyo-night        # guide closed: bar re-skins; open the guide: menu tokens applied
omarchy theme set catppuccin-latte   # light theme, guide OPEN while switching: card, scrim, selected row, banner tint all change live
omarchy theme set "$current"
journalctl --user -t omarchy-shell --since -5m | grep -iE 'warn|error' | grep -v 'Qt.atob'
```

Expected: no restart needed, no new warnings (the `Qt.atob` deprecation lines
are pre-existing host noise, see the journal before install), the bar glyph
dimming tracks the new bar foreground, the empty-state glyph uses
`Color.menu.selectedText`. `omarchy theme set` accepts either `Tokyo Night`
or `tokyo-night` (it lowercases and dash-joins). Run at least three themes
(`omarchy theme list` has 23).

### 5.6 Multi-monitor, vertical bar, narrow screen (TC-A11Y-04, TC-BAR-10, TC-BRW-24)

- This machine has one monitor (`eDP-1`, PLAN A7), so TC-A11Y-04 is recorded
  `not run`. On a two-monitor machine: focus a window on monitor 2, press
  `SUPER + SHIFT + T`: the guide appears on monitor 2 only (no `screen` set,
  R13); each monitor shows one bar widget with the same state; scroll over
  either widget zaps once (ARCH risk 9); `pgrep -fc wayland-app-id=omarchy-iptv`
  is 1.
- Vertical bar (optional): `omarchy bar position left`; the widget shows the
  glyph only, name in the tooltip; `omarchy bar position top` restores.
- Narrow screen (optional): `hyprctl keyword monitor eDP-1,1366x768@60,0x0,2`
  halves the logical width to 683 px, under `Style.space(720)`: the column
  hides, `h`/`l` still change the scope label; `hyprctl reload` restores the
  configured mode.

### 5.7 mpv window and file checks (TC-PLAY-01/02, SEC-14, SEC-15)

```
scripts/qa-live.sh verify
# or by hand
hyprctl clients -j | jq '.[] | select(.class == "omarchy-iptv") | {class, title, pid, workspace: .workspace.name, floating, fullscreen}'
pgrep -af -- '--wayland-app-id=omarchy-iptv'                 # at most one line
ps -o args= -p "$(pgrep -f -- '--wayland-app-id=omarchy-iptv')" | tr ' ' '\n'   # argv items, URL last after --
stat -c '%a %n' ~/.cache/omarchy-iptv ~/.cache/omarchy-iptv/* ~/.local/state/omarchy-iptv ~/.local/state/omarchy-iptv/* /run/user/1000/omarchy-iptv /run/user/1000/omarchy-iptv/*
find ~/.config/omarchy/plugins/io.github.rmcdavid.iptv -newer ~/.config/omarchy/plugins/io.github.rmcdavid.iptv/manifest.json -not -path '*/.git/*'
find ~/.config/omarchy/plugins/io.github.rmcdavid.iptv -name .git -prune -o -type l -print
```

Expected: `class` `omarchy-iptv`, `title` = channel name (also visible in
`hyprctl activewindow`), one pid, dirs 700 and files 600, the two `find`s
print nothing.

### 5.8 IPC verbs (R9, TC-BAR-09, SEC-17)

```
omarchy-shell io.github.rmcdavid.iptv status | jq .          # JSON: configured, channels, playing, nowPlaying (name, group; no URL expected, see D-QA-15), playlist status
omarchy-shell io.github.rmcdavid.iptv toggle                  # guide open/close (R9; scaffold lacks it, D-QA-04)
omarchy-shell io.github.rmcdavid.iptv play t:CNN.us           # an id from ~/.cache/omarchy-iptv/channels.json -> "ok"
omarchy-shell io.github.rmcdavid.iptv next                    # zap ring +1
omarchy-shell io.github.rmcdavid.iptv previous                # zap ring -1 (R9 name; scaffold has prev, D-QA-04)
omarchy-shell io.github.rmcdavid.iptv refresh                 # manual refresh -> notification
omarchy-shell io.github.rmcdavid.iptv stop
omarchy-shell io.github.rmcdavid.iptv play 'http://evil.example.test/x'   # "unknown", nothing launched
omarchy-shell io.github.rmcdavid.iptv play '--script=/tmp/x'              # "unknown"
qs ipc -n -p /usr/share/omarchy/shell show | grep -A9 'target io.github.rmcdavid.iptv'   # the verb list
```

### 5.9 Evidence capture

```
scripts/qa-live.sh evidence --apply --label us3-play        # journal since install, qs log tail, status, plugins, clients, theme, redaction grep
grim -o eDP-1 /tmp/omarchy-iptv-qa/tc-brw-05.png             # screenshot of the guide (grim captures layer surfaces)
omarchy-shell notifications showHistory                     # notification texts for 6.4 checks
journalctl --user -t omarchy-shell -f | grep --line-buffered omarchy-iptv   # follow during a step
```

Every failed step gets: the TC id, the screenshot, the journal excerpt and
the exact command that reproduces it, in the defect row (section 6).

### 5.10 Cleanup and uninstall (TC-INST-05, TC-INST-06, TC-INST-10, REL-02)

```
omarchy plugin disable io.github.rmcdavid.iptv               # TC-INST-05: entry and inline settings leave shell.json; widget gone; mpv exits
omarchy plugin enable io.github.rmcdavid.iptv                # comes back unconfigured (host semantics; README must warn)
scripts/qa-live.sh uninstall --apply                         # asks for confirmation (gum); --force skips it
# or by hand
omarchy-shell -q io.github.rmcdavid.iptv stop
omarchy plugin remove io.github.rmcdavid.iptv --yes          # disables (removes the bar entry), deletes the clone, rescans
rm -rf ~/.cache/omarchy-iptv ~/.local/state/omarchy-iptv /run/user/1000/omarchy-iptv
diff <(jq -S . /tmp/omarchy-iptv-qa/shell.json.before) <(jq -S . ~/.config/omarchy/shell.json)   # no output
find ~ -path '*omarchy-iptv*' -not -path '*/omarchy-iptv-qa/*'                                   # no output
```

Then remove by hand the `bindings.lua` line and the `omarchy-menu.jsonc`
entry added in 5.3, and delete `/tmp/omarchy-iptv-qa` once the report is
filed. `omarchy plugin remove` on a git checkout deletes it outright (no
backup); a non-git folder would be moved to `.<id>.bak.<stamp>` instead.

## 6. Defect reporting

Template (one row in `docs/STATUS.md` "Defects", details in the handoff note):

```
D-<n> | P1/P2/P3 | <task id> | <TC id>: <one-line repro> | open
### D-<n> (<TC id>, <area>)  P<sev>  found <date> at <commit>
Steps: 1. ... 2. ...
Expected (doc + section): ...
Actual: ...
Evidence: /tmp/omarchy-iptv-qa/<label>/... , screenshot, journal lines
Notes: suspected file:line, workaround
```

Severity rule of thumb (PLAN.md section 6): P1 = a story cannot be completed
(guide will not open, nothing plays, settings not read, credentials leaked
to a third party); P2 = the story works but a documented behaviour is wrong
or degraded (wrong key, wrong grouping, a URL shown on screen, missing
notification); P3 = cosmetic or wording, or a hardening item with no
user-visible effect today.

### 6.1 Pre-filed defects from the scaffold review (commit 7a26b6d, 2026-09-12)

Found by reading the scaffold and running the qa- fixtures through it; not
fixed by QA (FE lanes own the code). Re-verify each after the merge; close
the ones the lanes already addressed.

| ID | Sev | Where | Finding | Suggested fix |
|---|---|---|---|---|
| D-QA-01 | P2 SEC | `Service.qml` `mpvProc.onExited` / `rememberStderr` / `notify()` | mpv's own error line contains the stream URL (verified: `mpv --msg-level=all=error -- 'http://user:secretpass@127.0.0.1:9/...'` prints `Failed to open http://user:secretpass@127.0.0.1:9/live/user/secretpass/123.ts.`); the last stderr line becomes the critical notification body and `lastError` (guide status line, IPC `status`). Violates R12 and UX 6.4 | body per UX 6.4 (`<name> did not play`), append a reason only after replacing every `scheme://[^ ]+` with the host; keep raw stderr out of `lastError` |
| D-QA-02 | P2 SEC | `bin/omarchy-iptv` `make_channel` (`name = title or tvg-name or url`) | an empty `#EXTINF` title makes the raw stream URL the channel name (fixture `qa-attrs.m3u`, entry `#EXTINF:-1,` + `http://user:secret@...`): rendered in the guide row, bar label, tooltip, notifications and persisted in `state.json` recents | fall back to `tvg-id`, then `Channel <n>` (or the URL host), never the URL |
| D-QA-03 | P2 FUNC | `bin/omarchy-iptv` `make_channel` | multi-group `group-title="Animation;Kids;Religious"` is kept whole as the display group; R5 requires the first segment (full string stays in `searchKey`, which already works). Effect: `gen-10k.m3u` with 10 % multi-group entries yields 1,068 groups instead of ~120; the US list gets phantom groups | split on `;`, take the first non-empty trimmed segment, `Ungrouped` if none |
| D-QA-04 | P2 FUNC | `Service.qml` `IpcHandler` | verbs are `play stop next prev refresh status`; R9 requires `toggle` and `previous`; README documents the same list | add `toggle`, rename `prev` to `previous` (keep `prev` as an alias if cheap) |
| D-QA-05 | P3 | `Service.qml` settings, `README.md` table | `refreshMinutes` default 60 / min 5 in code and README vs R2 and `manifest.json` (360 / 15 / 1440); `barLabelMaxWidth` not read | align clamps with R2; add `barLabelMaxWidth` to the widget |
| D-QA-06 | P3 SEC | `bin/omarchy-iptv` `decode_text` | `gzip.decompress` has no inflated-size cap: a 100 KB gzip bomb inflates to 100 MB+ in memory (64 MB cap applies to the compressed download only); same risk for the EPG path when implemented | stream through `gzip.GzipFile(...).read(MAX_SOURCE_BYTES + 1)` and raise `too_large` |
| D-QA-07 | P3 | `bin/omarchy-iptv` `parse_m3u` / `stream_scheme` | `http://` with no host passes the allow-list (`qa-schemes.m3u`, `bad-empty-host`); mpv fails at play time with a confusing notification | require a non-empty `netloc` for http/https/rtsp/rtmp/mms/srt |
| D-QA-08 | P3 | `bin/omarchy-iptv` `normalize_text`, `Model.js` `normalizeText` | decomposed accents (NFD, `Cafe` + U+0301) are not folded (`qa-nonascii/qa-unicode.m3u`, `nfd.test`), so `cafe` matches only by substring luck; playlists exported from macOS tools are NFD | NFKD-normalise then drop U+0300-U+036F in both implementations (shared vectors) |
| D-QA-09 | P3 | `bin/omarchy-iptv` `_SAFE_OPTION` | option-looking `#EXTVLCOPT` keys such as `--script` are stored as `options["vlc:--script"]` (`qa-headers.m3u`, `optkey.test`); stored only in M1, but M2 may apply options | reject keys starting with `-` with a warning |
| D-QA-10 | P3 | `bin/omarchy-iptv` `make_channel`, `Model.js` `headerArgs` | empty `#EXTVLCOPT:http-user-agent=` yields `headers.User-Agent: ""` and an empty `--user-agent=` argv item | drop empty header values |
| D-QA-11 | P3 | `Model.js` `splitMpvArgs` | the token regex is case-insensitive but the reserved lookup is not: `--INPUT-IPC-SERVER=x` is accepted; mpv then exits 1 (`option not found`), surfacing as a stream failure instead of the documented console warning | lowercase-only regex (mpv option names are lowercase) |
| D-QA-12 | P3 | `bin/omarchy-iptv` `read_local_source` | error messages embed the resolved local path (`playlist file not found: /home/...`, `refusing to read /proc/...`); UX 6.3 wants `File not found`; ARCH 9 says no URLs/paths in output | user-facing message without the path; path on stderr only |
| D-QA-13 | P3 | `bin/omarchy-iptv` `cmd_playlist` | an HTML login page (`qa-not-m3u.html`) is reported as `empty_playlist` / `no playable channels found`; UX 6.3 distinguishes `Not an M3U file` | new code when neither `#EXTM3U` nor any `#EXTINF` is present (shipped as `not_a_playlist` in f03fef2; `Model.statusReason` still only knows `not_m3u`, D-LIVE-03) |
| D-QA-14 | P3 | `BarWidget.qml` | label elided at 24 characters (`Model.elide`) instead of `Style.space(barLabelMaxWidth)`; single glyph for all states (R7 wants U+F0502 / U+F0567 / U+F0503); tooltips differ from UX 6.3 | lane B scope (M1-11); listed so the matrix has an owner |
| D-QA-15 | P3 | `Service.qml` IPC `status` | returns `nowPlaying.url` (full stream URL with provider credentials) on the console; R12 says never beyond scheme+host. ARCH section 5 lists `path` in the mpv status contract, so this needs a PO ruling | return `host` instead of `url`, or redact to scheme+host |
| D-QA-16 | P3 | `Service.qml` `notify()`, `mpvProc.onExited` | headline `Could not play <name>`, urgency `critical`, glyph U+F0567 for every notification; UX 6.4: `Stream failed` / `<name> did not play`, normal, glyph U+F0503, `-r <id>`; refresh/EPG notifications absent | lane B scope (M1-14) |
| D-QA-17 | P3 | `README.md` | keyboard map is the ARCH draft (Ctrl chords, Tab cycles groups), settings table wrong (see D-QA-05), no mention that `omarchy plugin disable` drops inline settings (TC-INST-05), no `previous`/`toggle` verbs | update with UX 3 and R2/R9 (M1-18) |
| D-QA-18 | P3 | `bin/omarchy-iptv` `read_http_source` | the `Content-Encoding: gzip` branch is dead code (both branches return `data`); harmless because `decode_text` sniffs the magic bytes | remove or make it meaningful |

Observations that are not defects (recorded so nobody re-files them):
`#EXTINF` without a comma yields the trailing text as the title; an unquoted
`group-title=News Sports` yields group `News` and a title starting with
`Sports,` (VLC does the same); the en dash U+2013 is kept in `searchKey`
because only ASCII punctuation collapses (`qa-unicode.m3u`, `ard.de`);
`file:///etc/passwd` as the *source* parses to `empty_playlist` (the user's
own file); `url-tvg` beats `x-tvg-url` on the `#EXTM3U` line; a second
`#EXTINF` before any URL replaces the first (the first is lost silently).

## 7. Fixture catalogue

All fixtures are synthetic, deterministic, and small (largest 7 KB). Unit
tests never touch the network (QA-ASSETS.md). ASCII-only files live in
`tests/fixtures/`; files that must contain UTF-8 or binary bytes live in
`tests/fixtures/qa-nonascii/` because `scripts/check.sh` greps every regular
file directly under `tests/fixtures/` for non-ASCII bytes and skips
subdirectories (`[[ -f $file ]] || continue`). Regenerate nothing by hand: the
files are the source of truth; `qa-epg.xml.gz` is the byte-exact gzip twin of
`qa-epg.xml` (no filename, mtime 0, level 9; `python3 -c "import
gzip;print(gzip.open('tests/fixtures/qa-nonascii/qa-epg.xml.gz').read()==open('tests/fixtures/qa-epg.xml','rb').read())"`
prints `True`).

Run any M3U through the helper without tests:

```
python3 bin/omarchy-iptv playlist --url "file://$PWD/tests/fixtures/qa-groups.m3u" --cache-dir /tmp/omarchy-iptv-qa/cache-qa
jq -c '.channels[] | {id, name, group, searchKey, headers}' /tmp/omarchy-iptv-qa/cache-qa/channels.json
```

| File | Purpose | Expected (scaffold behaviour today in brackets where it differs) |
|---|---|---|
| `qa-groups.m3u` | multi-group `A;B;C`, `#EXTGRP` persistence and clearing, `group-title` precedence, padding, leading semicolon, no group | 10 channels; groups per R5: `Animation` [`Animation;Kids;Religious`, D-QA-03], `UK \| SPORTS`, `Sports`, `Sports`, `Movies`, `News`, `Ungrouped`, `Padded`, `Leading Semicolon` [`;Leading Semicolon`], `Ungrouped`; `searchKey` of the first is `multi group channel animation kids religious` |
| `qa-attrs.m3u` | `#EXTM3U` hints, bare/uppercase/repeated/empty attributes, duplicate tvg-id HD/SD, exact duplicate URL, commas in titles, float/zero durations, broken `#EXTINF`, empty title with credentialed URL, logo schemes, tabs, blank line before URL, lost first `#EXTINF`, 300-char title | 22 channels; `epgUrlHint` = `http://epg.example.test/guide.xml.gz`; ids `t:espn.us`, `u:a3d5424f`, `u:8e5692d2` (HD/SD), `u:cc5a0021` and `u:cc5a0021#2`; `chno` `12`; `Broken EXTINF Without Comma` is the title; `Name From tvg-name`; the empty-title entry must not be named after the URL [it is, D-QA-02]; `Logo File Scheme Dropped` has no `logo`; `Upper` group; `Second` wins for the repeated attribute; empty `group-title` -> `Ungrouped`; `t:spaced.id`; `Second Of Two EXTINF Is Kept` |
| `qa-headers.m3u` | `#EXTVLCOPT` UA/referrer/other, `#KODIPROP` stream/manifest headers and options, option line before `#EXTINF`, bare CR (0x0D) inside a value, percent-encoded CRLF, unsafe header name, shell metacharacters, option-looking key, empty value, uppercase key, no leak past a skipped URL | 11 channels, warnings `dropped header with unsafe name for KODIPROP Percent Encoded CRLF And Bad Name` and `1 entries skipped: unsupported URL scheme`; `vlc.test` headers `User-Agent`/`Referer` + `options.vlc:network-caching`; `clean.test` no headers; `before.test` `Before/1.0`; `cr.test` `Evil/1.0 X-Injected: yes` (single line); `kodi.test` three headers + two `kodi:` options; `kodicrlf.test` `X-Inject: a  X-Evil: b`, `X-Ok: 1`, `Bad\nName` dropped; `meta.test` value verbatim; `optkey.test` UA `--script=/tmp/evil.lua` as a value only [and `options.vlc:--script`, D-QA-09]; `emptyua.test` no header [empty header, D-QA-10]; `case.test` `Upper/1.0`; `afterskip.test` no headers |
| `qa-schemes.m3u` | allow-listed schemes, case, whitespace, option-looking suffix inside the line, every dropped scheme including mpv pseudo-protocols, orphan URL lines | 13 allowed [14: `http://` accepted, D-QA-07]; warnings `21 entries skipped: unsupported URL scheme`, `2 URL lines without #EXTINF skipped` |
| `qa-empty.m3u` | valid header, no entries | exit 1, code `empty_playlist`, guide `Playlist has no channels` |
| `qa-not-m3u.html` | provider login page instead of a playlist | exit 1, code `not_a_playlist` (verified at f03fef2; v0.1 expected the name `not_m3u`); the fake `#EXTINF` inside `<p>` is not an entry |
| `qa-epg.xml` | XMLTV: +0100 / -0500 / +0530 / no offset / 12-digit timestamps, overlap, gap, missing stop, far-future/past, orphan programme, channel without programmes, `@SD` id, character references for non-ASCII, `&amp;`, `<desc>`/`<category>`/`<episode-num>`/`<icon>` ignored | 27 programmes, 12 channels; expected now/next at T0 = 1789244100 listed in the file header comment (TC-EPG-06/07) |
| `qa-nonascii/qa-epg.xml.gz` | gzip twin of `qa-epg.xml` (deterministic) | identical `epg-now.json` (TC-EPG-05) |
| `qa-nonascii/qa-unicode.m3u` | UTF-8 names and groups: French, Polish, German (en dash, sharp s), Russian, Arabic, Japanese, emoji, NFC vs NFD, uppercase accent, non-ASCII URL path | 11 channels; `searchKey`s `tele quebec quebec`, `tvp lodz polska`, `das erste <U+2013> strasse deutschland`, Cyrillic/Arabic/CJK lowercased and kept, `emoji <U+1F4FA> channel fun`, `cafe nfc normalisation`, `cafe nfd normalisation` [`cafe<U+0301> nfd ...`, D-QA-08], `ecole uppercase accent normalisation`; ids `t:<tvg-id>` |
| `qa-nonascii/qa-bom-crlf.m3u` | UTF-8 BOM, CRLF, trailing spaces, blank CRLF line, `#EXTGRP` across CRLF, `#EXTVLCOPT` across CRLF, no final newline | 3 channels, groups `CRLF`, `Persisted`, `Persisted`; no `\r` in any URL; `crlf2.test` UA `CRLF/1.0` |
| `basic.m3u`, `attributes.m3u` (ARCH, existing) | scaffold parser tests | unchanged |
| generated (never committed) | `scripts/gen-playlist.py` outputs for PERF-* and offline runs (`gen-10k.m3u`, `gen-10k.xml.gz`, `gen-real.m3u`, `gen-real.xml`, `gen-dead.m3u`) | see section 4 and 5.3 |

Out of scope on purpose: lone-CR (classic Mac) line endings, UTF-16
playlists, `#EXTINF` with `tvg-id` containing quotes, playlists larger than
64 MB (covered by a sparse file in SEC-11, not a fixture).

## 8. Open questions for the lead before the live pass

1. Merge state: both lanes merged into `main` with `scripts/check.sh` green;
   which commit id do I test? Is `Copy.js` (UX 5.9) present so the microcopy
   greps work?
2. Keybinding and menu lines: may QA add the two README one-liners to
   `~/.config/hypr/bindings.lua` and `omarchy-menu.jsonc` for TC-BRW-01/04 (and
   remove them in 5.10), or should those rows stay `not run`?
3. EPG-matched playlist: the public pairs in QA-ASSETS.md match only
   partially; the generator pair (`gen-real.m3u` + `gen-real.xml`) matches
   fully but its streams are dead. Is there a real playlist + XMLTV pair with
   matching ids for TC-EPG-02 on a live stream, or is the generator pair
   acceptable for the EPG rows and `us.m3u` for playback?
4. Clock seam for EPG tests: `tests/test_epg.py` needs the helper's notion of
   "now" pinned to T0 (a `--now <epoch>` flag on `epg`, or an env var).
   Which one did lane A implement?
5. D-QA-15 ruling: may the IPC `status` verb print the stream URL, or only
   the host?
6. Theme names for TC-UI-05: `tokyo-night` and `catppuccin-latte` (one dark,
   one light) plus `retropc` (current) unless you prefer others.
7. The optional destructive checks (TC-PLAY-09 `kill -STOP`, TC-BAR-10 bar
   position, TC-BRW-24 monitor scale): run them or skip?
