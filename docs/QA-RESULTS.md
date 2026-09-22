# Omarchy IPTV - QA results, harness pass on M1 (f03fef2)

Owner: QA. Written 2026-09-13 after the pass of 2026-09-12 23:33 - 2026-09-13 00:31.
Plan of record: `docs/QA.md` v0.2. Defects: `docs/STATUS.md` (D-LIVE-01..15, details below in section 8).

## 1. Header

| Item | Value |
|---|---|
| Code under test | `f03fef2` (merge: lane A helper). HEAD moved from `52ecb40` to `acd1723` during the pass through docs-only commits (`81f8723` security review, `acd1723` doc amendments); `git diff --stat f03fef2 -- bin Model.js Service.qml Guide.qml BarWidget.qml manifest.json scripts/check.sh` is empty, so every run below exercised f03fef2 code |
| Gates at start | `omarchy plugin validate .` exit 0; `scripts/check.sh` all green: 244 node checks, 127 python tests, 16 qml spec, ascii ok (11.5 s) |
| Mode | dev harness `scripts/dev-harness/run.sh` (standalone Quickshell 0.3.1, real `Service.qml` / `Guide.qml` / `BarWidget.qml` / `bin/omarchy-iptv` from the repo, fake `shell` / `bar` / `settings`, scratch XDG dirs). The plugin was NOT installed into `~/.config/omarchy/plugins`; nothing under `~/.config` or `~/.local/state` was touched; no `omarchy theme set`, `hyprctl dispatch/reload/keyword`, `omarchy plugin add/enable/disable/remove`, `omarchy bar set` or sudo was run |
| Harness location | `OMARCHY_IPTV_HARNESS_DIR=/tmp/claude-1000/omarchy-iptv-qa/harness` (wrapper `/tmp/claude-1000/omarchy-iptv-qa/h.sh`), timeout 0, quickshell killed by PID between runs |
| Notification capture | a PATH shim `/tmp/claude-1000/omarchy-iptv-qa/bin/omarchy-notification-send` records every argv (JSON line) to `logs/notifications.log` instead of toasting the desktop; `Model.notifyArgv` resolves the command by name, so the plugin code is unchanged |
| Machine | Omarchy 4.0.3-1, Quickshell 0.3.1, Hyprland 0.56.2, mpv 0.41.0, Python 3.14.7, node 26.8.1 (mise), one monitor `eDP-1` 1366x768 scale 1, theme `retropc`, tools wtype / grim / jq / curl / ffmpeg / ImageMagick present |
| Scratch / evidence | `/tmp/claude-1000/omarchy-iptv-qa/`: `downloads/` (us.m3u 326,083 B, index.m3u 2,501,355 B, pluto-us.xml.gz 955,717 B), `gen/` (gen-10k.m3u sha256 `0aa5acc2...156f7a`, gen-10k.xml.gz, gen-500.m3u/.xml, gen-real.m3u/.xml, gen-dead.m3u, live2.m3u), `harness/shots/` (43 grim screenshots `run*.png`), `shots/` (cropped evidence), `logs/` (`run1..run10*.log` harness consoles, `notifications.log`, `run7-*.json` privacy sinks), `cache-perf/` (helper timing caches) |
| Sources used | `tests/fixtures/qa-groups.m3u` (browse), `qa-attrs.m3u` (privacy), `qa-nonascii/qa-unicode.m3u`, `qa-empty.m3u` and `qa-not-m3u.html` served from `127.0.0.1:8766`, generated 500 / 1,500 / 10,000-channel files with matching XMLTV, iptv-org `us.m3u` (file and https) and `index.m3u` (11,041), Pluto `us.xml.gz` (file and https), `--serve` local MPEG-TS on `127.0.0.1:8765`, ABC News Live 1 for one real HLS play |

Conventions: microcopy is quoted with ` - ` for U+00B7 and `...` for U+2026; the UI renders the real codepoints (checked in the screenshots). `run<N>` refers to `logs/run<N>.log` and the `harness/shots/run<N>-*.png` files. Results are `pass`, `fail` (defect id in the note), `blocked: needs live shell`, `not run` (reason in the note).

Two harness pitfalls worth knowing for the next pass: `wtype space` types the letters s-p-a-c-e (use `wtype -k space`; in list mode the `s` stops playback), and `wtype -d 0` is rejected (`-d 1` works). `pgrep -f` with a pattern that also appears in your own shell's command line matches your shell.

## 2. Summary

| Category | Cases | pass | fail | blocked | not run |
|---|---|---|---|---|---|
| INST Install and lifecycle | 10 | 3 | 0 | 7 | 0 |
| CFG Configuration | 13 | 12 | 1 | 0 | 0 |
| BRW Browse | 25 | 18 | 1 | 2 | 4 |
| PLAY Watch | 14 | 11 | 0 | 1 | 2 |
| BAR Bar widget | 12 | 8 | 0 | 0 | 4 |
| FAV Favorites and recents | 11 | 9 | 1 | 0 | 1 |
| EPG EPG | 12 | 11 | 1 | 0 | 0 |
| RFR Refresh and offline | 10 | 7 | 2 | 0 | 1 |
| UI States, microcopy, theme | 14 | 13 | 0 | 1 | 0 |
| A11Y Accessibility | 6 | 5 | 0 | 1 | 0 |
| PARSE Parsers | 11 | 11 | 0 | 0 | 0 |
| MODEL Model.js | 8 | 7 | 0 | 0 | 1 |
| SEC Security | 21 | 18 | 1 | 0 | 2 |
| PERF Performance | 7 | 7 | 0 | 0 | 0 |
| **Total** | **174** | **140** | **7** | **12** | **15** |

Failures map to defects: TC-CFG-06 -> D-LIVE-02 (P2); TC-BRW-21 -> D-LIVE-06; TC-FAV-08 and SEC-14 -> D-LIVE-04; TC-EPG-04 -> D-LIVE-08; TC-RFR-01 -> D-LIVE-05; TC-RFR-09 -> D-LIVE-03. D-LIVE-01 (P2, browse cap) is reported through passing cases TC-BRW-09/10 and TC-RFR-10 because their own expectations hold; it is the first thing to fix. `not run` is dominated by mouse cases (no pointer automation was available; every underlying function was exercised through the harness IPC) and by tests the plan itself marks not runnable here.

## 3. Results by category

### INST - Install and lifecycle

| ID | Result | Evidence |
|---|---|---|
| TC-INST-01 | pass | `omarchy plugin validate .` exit 0; `scripts/check.sh` all green (244 node checks, 127 python tests, 16 qml, ascii ok) |
| TC-INST-02 | blocked: needs live shell | git clone into `~/.config/omarchy/plugins` and validate on the clone |
| TC-INST-03 | blocked: needs live shell | rescan + enable, `shell.json` entry |
| TC-INST-04 | pass | harness console clean on load in all 10 runs (`logs/run*.log`): only Quickshell's own `qt.qpa.services` portal WARN, nothing from our files; live journal re-check listed in section 7 |
| TC-INST-05 | blocked: needs live shell | disable/enable semantics; note: README has no 'settings are lost on disable' sentence (D-LIVE-13) |
| TC-INST-06 | blocked: needs live shell | `omarchy plugin remove` |
| TC-INST-07 | pass | after all runs `find . -newermt '2026-09-12 23:33' -not -path './.git/*' -not -path './.claude/*' -not -path './docs/*' -type f` lists only README.md (docs commit acd1723): no runtime write inside the plugin dir |
| TC-INST-08 | blocked: needs live shell | `omarchy restart shell` round trip |
| TC-INST-09 | blocked: needs live shell | `rescanPlugins` while playing |
| TC-INST-10 | blocked: needs live shell | README uninstall vs reality; note: README names two leftover dirs, `$XDG_RUNTIME_DIR/omarchy-iptv` is a third (D-LIVE-13) |

### CFG - Configuration

| ID | Result | Evidence |
|---|---|---|
| TC-CFG-01 | pass | harness `ipc set playlistUrl https://iptv-org.github.io/iptv/countries/us.m3u`: fetched in 1,257 ms with no restart, footer `1,475 channels - updated 00:00`, tooltip `IPTV - click to open the guide`; the real `omarchy bar set` -> `shell.barConfig` path is live-shell only (section 7) |
| TC-CFG-02 | pass | `shots/run2-404-nocache.png`: `Playlist failed to load` / `HTTP 404 Not Found from iptv-org.github.io - check playlistUrl`, hint `r reload - Esc close`, glyph U+F0503; widget `{glyph U+F0503, tooltip IPTV - playlist error, open the guide}`; no-cache notification body `Could not fetch the playlist (Timed out). Open the guide for details.` (run3) |
| TC-CFG-03 | pass | `shots/run2-resolve.png`; `playlistReason: Could not resolve host` |
| TC-CFG-04 | pass | `ftp://example.test/x.m3u` renders `Unsupported URL` in the empty state; helper code `unsupported_scheme` (`tests/test_helper.py::test_refuses_unsupported_scheme`) |
| TC-CFG-05 | pass | absolute path and `file:///.../qa-groups.m3u` both load, `sourceHost: local file` (run1 state dump) |
| TC-CFG-06 | fail | D-LIVE-02: `ipc set epgUrl <xml>` from an empty value leaves `epg.pending: true`, no helper process in a 4 s watch (run9b), no `epg-*.json` until `r`; changing a non-empty `epgUrl` fetches within 300 ms; Pluto `.gz` (local path and https) parses with 0 matched ids as expected, no error |
| TC-CFG-07 | pass | clamps automated (`Model.test.js` clampInt / clampSetting / settingsFrom 360/15/1440); timer re-arm not observable in the harness (section 7) |
| TC-CFG-08 | pass | `OMARCHY_IPTV_MPV_ARGS` (run5): argv carries `--profile=fast --hwdec=auto-safe`, none of `--input-ipc-server=/tmp/x --title=X --no-idle`; console `omarchy-iptv: ignoring mpvArgs tokens: --input-ipc-server=/tmp/x --title=X --no-idle`; URL last after `--` |
| TC-CFG-09 | pass | widget JSON while playing: label empty with `showChannelName=false`, tooltip `Playing Harness Live A` kept (`shots/run4-bar-noname-crop.png`) |
| TC-CFG-10 | pass | long name: label implicitWidth 95.5 px at 60, 215.5 at 180, 466.75 at 600 (`shots/run4-bar-60-crop.png`, `run4-bar-600-crop.png`) |
| TC-CFG-11 | pass | `maxRecents=3`, four plays -> `recents: 3` (run1 `state.json`) |
| TC-CFG-12 | pass | `playlistUrl` changed with the guide open: 10 -> 500 -> 10 channels re-rendered without restart (run1) |
| TC-CFG-13 | pass | section 6: zero hits in every sink |

### BRW - Browse

| ID | Result | Evidence |
|---|---|---|
| TC-BRW-01 | blocked: needs live shell | keybinding |
| TC-BRW-02 | not run | no pointer automation in this session; the click handler's function (toggle) verified through IPC |
| TC-BRW-03 | pass | harness `toggle`/`open`/`close` (fakeShell.summon/hide, the calls behind `omarchy-shell shell toggle|summon|hide`) and the service IPC verb `toggle` open and close; state in sync after Esc (run1) |
| TC-BRW-04 | blocked: needs live shell | menu row |
| TC-BRW-05 | pass | `shots/run1-open.png`: `Search channels...`, hint `Enter play - Up/Down move - Left/Right group - Tab keys - Esc close`, cursor row 0; `run4-cues.png`: reopens on the playing row |
| TC-BRW-06 | pass | opens on All while Favorites is empty, on Favorites once populated (`Favorites - 2 channels`, run1); Recent hidden until a play; Favorites always listed |
| TC-BRW-07 | pass | `kids` -> 1 match; `tele`/`TELE quebec` -> Tele Quebec with accents, `cafe` -> NFC and NFD rows (2), `ecole` -> the uppercase-accent row (`qa-unicode.m3u`, run4); label `in All - N matches`; Backspace, Ctrl+Backspace (word), Ctrl+U verified |
| TC-BRW-08 | pass | `Model.test.js` tier and favorites-first cases; spot check `kids` on us.m3u ranks name-start `Kids Movie Club` before group-only `3ABN Kids Network` |
| TC-BRW-09 | pass | index.m3u, `a`: `in All - 8,579 matches`, 200 rows, footer `First 200 of 8,579 - keep typing` (`shots/run6-cap.png`); the same cap applies with no query, D-LIVE-01 |
| TC-BRW-10 | pass | Up on row 0 -> row 9, Down on row 9 -> 0, End/Home, PgDn +8 (visible-1) then clamps (run1); on the 11k list End stops at row 199 because of D-LIVE-01 |
| TC-BRW-11 | pass | Right from All -> `g:Animation`; Left from the first entry wraps to `g:Leading Semicolon`; typing on Favorites jumps to All, Ctrl+U restores Favorites (run1) |
| TC-BRW-12 | pass | Esc with a query clears it (hint `... Esc clear` -> `... Esc close`), Esc again closes; `ipc toggle` then opens on the first call (run1) |
| TC-BRW-13 | pass | Tab commits `spo`, hint `j/k move - h/l group - Enter play - Space preview - f favorite - s stop - r refresh - / search` (`shots/run1-listmode-spo.png`); `/` returns to search mode with `spo` kept; Tab in list mode also returns to search mode |
| TC-BRW-14 | pass | `q w e` in list mode: query stays empty, cursor unchanged (run1) |
| TC-BRW-15 | pass | `4` in list mode ignored (run1); `4k` in search mode -> `in All - 1,218 matches` (run10) |
| TC-BRW-16 | pass | `F` toggles favorite, `X` no-op on All, `S` -> footer `Stopped`, `R` -> refresh + notification (run1) |
| TC-BRW-17 | pass | `shots/run1-nomatch-group.png`: `No matches for "zzzz" in Sports` / `h/l other groups - Home for All`; Home in list mode moves the column to All |
| TC-BRW-18 | pass | `shots/run1-nomatch-all.png`: `No matches for "zzzz"` / `Esc clears the search` |
| TC-BRW-19 | not run | pointer (scrim click, card click, hover gate) |
| TC-BRW-20 | pass | every wtype key in 10 runs landed in the guide and never in the window behind it (exclusive keyboard focus holds while open) |
| TC-BRW-21 | fail | D-LIVE-06: groups are in playlist order but `Ungrouped` sits between `News` and `Padded` (`shots/run1-open.png`); UX 2.2 wants it last |
| TC-BRW-22 | pass | us.m3u has 86 multi-group entries; `3ABN Kids Network` (`Animation;Kids;Religious`) listed once under Animation (22) and found by `kids` (run4) |
| TC-BRW-23 | not run | wheel events (pointer) |
| TC-BRW-24 | not run | needs `hyprctl keyword monitor` (not allowed in this session); `narrow: false` at 1366x768 |
| TC-BRW-25 | pass | `ipc open '{"query":"sky"}'` opens with `sky` prefilled in search mode (run10) |

### PLAY - Watch

| ID | Result | Evidence |
|---|---|---|
| TC-PLAY-01 | pass | Enter on `Harness Live A`: guide closed, window mapped 489 ms later; `hyprctl clients -j`: class `omarchy-iptv`, title `Harness Live A`; `hyprctl activewindow` = mpv; argv `--wayland-app-id=omarchy-iptv --title=<name> --force-media-title=<name>`; one mpv (`shots/run4-playing.png`) |
| TC-PLAY-02 | pass | Enter on B: same pid 810132, title `Harness Live B`, media-title B; over the network `ABC News Live 1 (720p)` titles the window (run4) |
| TC-PLAY-03 | pass | Enter on the playing row: mpv `time-pos` 7.3 -> 12.6 s across the call (no reload), same pid, guide closed |
| TC-PLAY-04 | pass | Space (keysym) on C: guide stays open, footer `U+F040A <name> - s stop`, trail glyph, bold name (`font.bold: row.playing`), `shots/run4-space-cues-card.png` |
| TC-PLAY-05 | pass | notification argv `--app-name IPTV -u normal -g U+F0503 -r 74011 'Stream failed' 'Multi Group Channel did not play - Failed to open stream.example.test'`; `-r 74011` reused on every failure; row `Failed 23:39 - Space to retry` with U+F0026 (`shots/run1-failed-row-card.png`); cursor unchanged; Recent gained the channel; bar back to U+F0502 |
| TC-PLAY-06 | pass | `s`: footer `Stopped`, mpv gone 245 ms after the stop, no notification, widget idle (run4) |
| TC-PLAY-07 | pass | `q` typed into the focused mpv: mpv exits, bar idle, cues clear, zero notifications (run4) |
| TC-PLAY-08 | pass | fresh launch on C: argv `--user-agent=QA-Agent/1.0`, `--referrer=http://referrer.example.test/`, then `--` and the URL last (run4) |
| TC-PLAY-09 | not run | detection verified: `kill -STOP` -> console `mpv unresponsive, restarting player` after two 10 s polls, SIGTERM sent; mpv traps SIGTERM so a stopped process cannot exit (QA.md step corrected); the relaunch was not observed |
| TC-PLAY-10 | pass | three Space presses within ~1.5 s end on the third row (`Harness Live B`), one mpv (run4) |
| TC-PLAY-11 | blocked: needs live shell | `omarchy restart shell`; README Playback notes document the limitation |
| TC-PLAY-12 | pass | open + 6-letter query + Enter -> window 594/673 ms, `time-pos` 1.9 s one second later (local stream); ABC News Live window 523 ms |
| TC-PLAY-13 | not run | mpv is an Omarchy dependency; code path reviewed (`whichProc` -> `notify("mpvMissing")`, `Model.notifyArgv` text = UX 6.4) |
| TC-PLAY-14 | pass | mpv fullscreen (Hyprland `fullscreen: 2`, mpv `fullscreen: true`), guide draws above it (`shots/run4-over-fullscreen.png`); after close still fullscreen, `pause: false`, time-pos advancing, mpv focused |

### BAR - Bar widget

| ID | Result | Evidence |
|---|---|---|
| TC-BAR-01 | pass | widget `{glyph U+F0502, label "", tooltip IPTV - click to open the guide}` (run1) |
| TC-BAR-02 | pass | `--playlist none`: tooltip `IPTV - no playlist configured`, glyph U+F0502 (run3) |
| TC-BAR-03 | pass | playing: glyph U+F0567, label `Harness Live A`, tooltip `Playing Harness Live A` (`shots/run4-playing.png`, top right) |
| TC-BAR-04 | pass | 404 / timeout with no cache: glyph U+F0503, tooltip `IPTV - playlist error, open the guide` (run2, run3) |
| TC-BAR-05 | pass | tooltip `IPTV - refreshing playlist...` while the helper runs (run3) |
| TC-BAR-06 | not run | pointer; toggle function verified by IPC |
| TC-BAR-07 | not run | pointer; `ipc stop` (same `service.stop`) verified: mpv gone, idle glyph |
| TC-BAR-08 | not run | pointer; refresh function via `r`/IPC `refresh`: notification `Playlist refreshed` / `10 channels in 8 groups` low U+F0450 correct, but the footer never shows `Refreshed - N channels` (D-LIVE-05) |
| TC-BAR-09 | pass | ring via `service.zap` (what the wheel calls): from All -> group ring A,B,C; from Favorites -> A,C with wrap; from Recent -> the channel's group (run4); wheel routing itself not run (pointer); re-selecting the playing channel from another list keeps the old ring (D-LIVE-12) |
| TC-BAR-10 | pass | `--vertical`: while playing label empty, tooltip `Playing Harness Live A`, width 28 (run8b) |
| TC-BAR-11 | pass (retracted) | `Accessible.name: Model.barAccessibleName(...)` at BarWidget.qml:104 **RETRACTED 2026-09-15, criterion, not observation.** The evidence quoted here is real and the conclusion drawn from it was not available: this is a grep over source the source was written to satisfy, so the case could not have failed whatever the plugin published. See "Accessibility harness runs" at the end of this file. Result stands as `not run`. |
| TC-BAR-12 | not run | third-party bar facade; README does not mention the limitation (D-LIVE-13) |

### FAV - Favorites and recents

| ID | Result | Evidence |
|---|---|---|
| TC-FAV-01 | pass | star U+F04CE in the lead slot, footer `Added to Favorites` / `Removed from Favorites` (`shots/run1-fav-added-card.png`) |
| TC-FAV-02 | pass | `shots/run1-fav-empty.png`: `No favorites yet` / `Press f on any channel to pin it here` |
| TC-FAV-03 | pass | favorited C, A, B -> Favorites lists C, A, B; first entry after Recent (run1) |
| TC-FAV-04 | pass | `f` on index 1 inside Favorites: row leaves, cursorIndex stays 1 (`shots/run1-fav-list-card.png`) |
| TC-FAV-05 | pass | `x` in Recent -> `Removed from Recent`, entry hidden; Delete in Favorites unfavorites; `x`/`X` on All no-op; cursor is left on the hidden Recent scope afterwards (D-LIVE-07) |
| TC-FAV-06 | pass | `Model.test.js` pushRecent; harness: Recent appears first after a play, replay moves to top, cap honoured |
| TC-FAV-07 | pass | dead channel recorded in Recent (`recents: 1`, `state.json`) although mpv failed (run1) |
| TC-FAV-08 | fail | favorites (`t:pipe.test`) and 3 recents survive a harness restart with `--keep` (run1b); dir `state/omarchy-iptv` is 700 but `state.json` is 644 where ARCH 8.5 requires 0600 - D-LIVE-04 |
| TC-FAV-09 | pass | `garbage{{{` in `state.json`: guide opens with empty Favorites/Recent, no crash, no console warning, `f` rewrites valid JSON (run1c) |
| TC-FAV-10 | pass | favorites count unchanged across `r`; ids stable (`tests/test_playlist.py` assign_ids) |
| TC-FAV-11 | not run | pointer (lead-slot click) |

### EPG - EPG

| ID | Result | Evidence |
|---|---|---|
| TC-EPG-01 | pass | guide opens ~500 ms after start while playlist and EPG load (run10); footer `Guide data loading...` observed while pending (run6); gen-500.xml lands in 94 ms |
| TC-EPG-02 | pass | `shots/run5-epg-t0-card.png`: `Lifestyle - Now: Evening Concert - Next: Magazine Daily`, right meta `until 01:00`, hairline; the 10k pair renders too (`shots/run10-epg-10k-card.png`) |
| TC-EPG-03 | pass | channels without `tvg-id` (237 of 500) show the group only, no `Now:`/`Next:`/`until` (same screenshot); Pluto vs us.m3u: 0 matches, no error |
| TC-EPG-04 | fail | 404 EPG: notification `Guide data error` / `Could not fetch the EPG (HTTP 404 Not Found). Channels still work.` low U+F0026, playback unaffected, old `epg-now.json` kept; but no banner because `Guide.qml:174` shows `epgError` only when `!epgLoaded` - D-LIVE-08 |
| TC-EPG-05 | pass | `tests/test_epg.py::test_qa_gzip_twin_gives_identical_output` |
| TC-EPG-06 | pass | `tests/test_epg.py::test_qa_epg_now_next_at_t0`, `test_offsets_are_applied`, `test_missing_offset_means_utc`, `test_short_forms_are_padded` |
| TC-EPG-07 | pass | `tests/test_epg.py::test_overlap_falls_back_to_the_still_running_programme`, `test_sorts_infers_stops_and_dedupes`, `test_window_keeps_only_the_window_and_unicode_titles` |
| TC-EPG-08 | pass | hairline advanced over 66 s on `Solar Live` (`shots/run5-tick-t0-row.png` vs `-t1`, 5.5 px AE diff), `until 02:00` unchanged; `--now-only` recompute at generatedAt +300 s with `fromCache: true`, no download |
| TC-EPG-09 | pass | `tests/test_epg.py::test_window_keeps_only_the_window_and_unicode_titles`; gen-real rows render |
| TC-EPG-10 | pass | `tests/test_epg.py::test_inflated_gzip_bomb_is_too_large`, `test_malformed_inputs`, `test_fetch_failure_keeps_stale_window_and_refreshes_now` |
| TC-EPG-11 | pass | `tests/test_epg.py::test_qa_restricted_to_playlist_ids_with_at_sign_and_case_fallback` |
| TC-EPG-12 | pass | run10: 10 keys typed during the 2.95 s gen-10k.xml.gz parse, query `sky sports` intact; PERF-04 |

### RFR - Refresh and offline

| ID | Result | Evidence |
|---|---|---|
| TC-RFR-01 | fail | `r`: footer `Refreshing...` for 3 s then straight to `10 channels - updated 23:41`; `Refreshed - N channels` never shown (250 ms polls, run1); notification `Playlist refreshed` / `10 channels in 8 groups` low U+F0450 correct - D-LIVE-05 |
| TC-RFR-02 | not run | 15 min wait not performed; a startup refresh with the server down notified on failure only (R12 allows) |
| TC-RFR-03 | pass | `shots/run3-banner.png`: `U+F0026 Playlist refresh failed (Connection refused) - showing cached copy from 23:47 - r retry`, status `cached`; notification `Playlist error` / `Could not fetch the playlist (Connection refused). Using cached copy from 23:47.` normal; banner gone after a successful `r` |
| TC-RFR-04 | pass | `r` twice within ~100 ms -> one `Playlist refreshed` notification (run2) |
| TC-RFR-05 | pass | IPC `refresh` while B played: still one mpv, playback untouched (run4) |
| TC-RFR-06 | pass | restart with `--keep` and the server down: 200 cached rows at +1.3 s with the banner (`shots/run3-cached-start.png`) |
| TC-RFR-07 | pass | cursor 150 on gen-500, switch to the 10-channel list -> cursorIndex 9, no crash (run1) |
| TC-RFR-08 | pass | `shots/run2-empty.png`: `Playlist has no channels` / `Parsed 0 channels from 127.0.0.1 - check the URL points at an M3U` |
| TC-RFR-09 | fail | `shots/run2-notm3u.png`: `source from 127.0.0.1 is not an M3U playlist (no #EXTM3U or #EXTINF lines) from 127.0.0.1 - check playlistUrl` instead of `Not an M3U file` - D-LIVE-03 |
| TC-RFR-10 | pass | footer `10 channels - cached 23:49 - offline` (`shots/run3-cached-footer.png`); tooltip has no cached marker (acceptable per the plan); on lists over 200 rows the footer is taken by `First 200 of N` (D-LIVE-01) |

### UI - States, microcopy, theme

| ID | Result | Evidence |
|---|---|---|
| TC-UI-01 | pass | `shots/run3-unconfigured.png`: title, prose, command box, `Optional EPG: ...`, `Settings live in ...`, column hidden, hint `r reload - Esc close`, glyph U+F0502; box click / `wl-copy` not run (pointer); `r` shows `Refreshing...` although nothing runs (D-LIVE-09) |
| TC-UI-02 | pass | `shots/run3-loading.png`: glyph U+F01D8, `Loading playlist...`, `Fetching from 10.255.255.1`, hint `Esc close`; never shown while a cache exists (run3b); from an error state the previous reason stays on screen during the new load (D-LIVE-10) |
| TC-UI-03 | pass | banner (`shots/run3-banner.png`: alert glyph, urgent tint, one line) and the no-cache empty error state with U+F0503 (`shots/run2-404-nocache.png`) |
| TC-UI-04 | pass | bold name (`font.bold: row.playing`), trail U+F040A, footer `U+F040A <name> - s stop`, column unchanged (`shots/run4-cues.png`) |
| TC-UI-05 | blocked: needs live shell | theme switch (`omarchy theme set` not allowed in this session) |
| TC-UI-06 | pass | grep for hex colors / `white` / `black` / `Qt.rgba(` in `*.qml`: no output |
| TC-UI-07 | pass | every `font.family` binds `root.fontFamily` -> `bar.fontFamily` / `Style.font.family` |
| TC-UI-08 | pass | overlay appears fully drawn 150-175 ms after the toggle call, no fade frames in shots taken right after; banner fade and label animation timings not measured |
| TC-UI-09 | pass | four hint strings verified verbatim (`run1-open`, `run1-search-kids`, `run1-listmode-spo`, `run3-unconfigured`/`run3-loading`) |
| TC-UI-10 | pass | `All - 1,475 channels`, `Favorites - 2 channels`, `Recent - 3 channels`, `Animation - 1 channel`, `in All - 8,579 matches`, `in Sports - 0 matches` (state dumps) |
| TC-UI-11 | pass | `Model.js` GLYPHS table has all nine codepoints; idle/playing/error/star/play/alert/loading/refresh glyphs seen rendered in the screenshots |
| TC-UI-12 | pass | `Guide.qml` `readonly property var copy` plus `Model.js` (footerStatus / footerHints / barTooltip / notifyArgv) |
| TC-UI-13 | pass | qmllint: 0 errors, 106 warnings (57 missing-property, 42 unqualified, 6 signal-handler-parameters, 1 uncreatable-type); harness console clean; README records no baseline (D-LIVE-14, D-LIVE-13) |
| TC-UI-14 | pass | `Guide.qml:130-141` `space(200)`, `space(960)`, `space(620)`, `space(720)`; card centred at 960x620 in every screenshot; `narrow: false` |

### A11Y - Accessibility

| ID | Result | Evidence |
|---|---|---|
| TC-A11Y-01 | pass (retracted) | `Guide.qml` 594-1214: Dialog `IPTV guide`, EditableText `Search channels`, List `Groups` / `Channels in <scope>`, ListItem via `Model.rowAccessibleName`, AlertMessage banner, StaticText footer; BarWidget Button **RETRACTED 2026-09-15, criterion, not observation.** The evidence quoted here is real and the conclusion drawn from it was not available: this is a grep over source the source was written to satisfy, so the case could not have failed whatever the plugin published. See "Accessibility harness runs" at the end of this file. Result stands as `not run`. |
| TC-A11Y-02 | pass | review: every state seen carries a glyph or a word (star, play glyph + footer, `Failed HH:MM`, `cached ... offline`, banner text) |
| TC-A11Y-03 | pass | `Guide.qml:131-137, 1026`: `space(38)` rows, `space(32)` entries, lead slot `space(24)` padded to `space(28)`; click targets not exercised (pointer) |
| TC-A11Y-04 | blocked: needs live shell | one monitor here; procedure in QA.md 5.6 |
| TC-A11Y-05 | pass | TC-PLAY-01/03/14 pass |
| TC-A11Y-06 | pass | PERF-02/03 pass |

### PARSE - Parsers

| ID | Result | Evidence |
|---|---|---|
| TC-PARSE-01 | pass | `tests/test_playlist.py` (50 tests) incl. `qa-attrs.m3u` |
| TC-PARSE-02 | pass | `tests/test_playlist.py` with `qa-groups.m3u`; harness column shows `Sports`, `Sports`, `Movies`, `News`, `Ungrouped` (`shots/run1-open.png`) |
| TC-PARSE-03 | pass | `Multi Group Channel` under `Animation`, `searchKey` keeps the whole string (found by `kids`) |
| TC-PARSE-04 | pass | `tests/test_playlist.py` with `qa-headers.m3u`; `#EXTVLCOPT` reached mpv argv (TC-PLAY-08) |
| TC-PARSE-05 | pass | `tests/test_playlist.py` with `qa-attrs.m3u` (duplicate tvg-id / URL ids); credentialed empty-title entry became `Channel 11` (`u:46b30f8f`) |
| TC-PARSE-06 | pass | `tests/test_playlist.py` with `qa-nonascii/qa-bom-crlf.m3u` |
| TC-PARSE-07 | pass | `tests/test_playlist.py` NormalizationTest + `qa-unicode.m3u`; TC-BRW-07 in the guide |
| TC-PARSE-08 | pass | `tests/test_playlist.py` with `qa-schemes.m3u` |
| TC-PARSE-09 | pass | CLI: `qa-empty.m3u` -> `empty_playlist`, `qa-not-m3u.html` -> `not_a_playlist` exit 1 (guide wording is D-LIVE-03) |
| TC-PARSE-10 | pass | PERF-01 |
| TC-PARSE-11 | pass | TC-EPG-05..11 |

### MODEL - Model.js

| ID | Result | Evidence |
|---|---|---|
| TC-MODEL-01 | pass | `node tests/Model.test.js` 244 checks; `tests/Model.spec.qml` 16 passed; `test_fold_table_matches_model_js` |
| TC-MODEL-02 | pass | `Model.test.js` filterChannels tiers / cap / favorites-first; pure filter <= 6.7 ms on 11k rows |
| TC-MODEL-03 | pass | `Model.test.js` groupChannels / zapRing / nextInGroup |
| TC-MODEL-04 | pass | `Model.test.js` parseState / pushRecent / trimRecents |
| TC-MODEL-05 | pass | `Model.test.js` findBarEntry / clampInt / clampSetting |
| TC-MODEL-06 | pass | `Model.test.js` splitMpvArgs (reserved, `--no-` forms, case) / headerArgs / buildMpvArgv |
| TC-MODEL-07 | pass | `qmltestrunner -input tests/Model.spec.qml`: 16 passed (check.sh) |
| TC-MODEL-08 | not run | no `Guide.spec.qml` / `BarWidget.spec.qml` (PanelWindow cannot run under qmltestrunner, STATUS M1-17); the harness runs covered the states |

### SEC - Security

| ID | Result | Evidence |
|---|---|---|
| SEC-01 | pass | grep for shell strings / `eval(` / string commands: no output |
| SEC-02 | pass | grep for sudo / pkexec / doas: no output |
| SEC-03 | pass | `tests/test_playlist.py` qa-headers `cr.test` / `kodicrlf.test`; one `--user-agent=` argv item (TC-PLAY-08) |
| SEC-04 | pass | `tests/test_playlist.py` qa-headers (unsafe header name dropped) |
| SEC-05 | pass | `tests/test_playlist.py` qa-schemes allow-list |
| SEC-06 | pass | argv tail is `--`, URL (run4, run5) |
| SEC-07 | pass | section 6 |
| SEC-08 | pass | CLI `/proc/self/environ` -> `unsafe_path` `refusing to read a playlist from /proc, /sys or /dev` (path not echoed); `tests/test_helper.py::test_unsafe_paths_are_refused_without_echoing_them` |
| SEC-09 | pass | `tests/test_helper.py::test_unsafe_paths_are_refused_without_echoing_them` (symlink case) |
| SEC-10 | not run | documented non-defect |
| SEC-11 | pass | `tests/test_helper.py::test_sparse_65mb_file_is_too_large_without_reading_it`, `test_gzip_bomb_playlist_is_too_large`; `tests/test_epg.py::test_inflated_gzip_bomb_is_too_large` |
| SEC-12 | pass | `tests/test_playlist.py` SourceTest, `tests/test_helper.py::test_refuses_unsupported_scheme`; `ftp://` in the guide -> `Unsupported URL` |
| SEC-13 | pass | `Model.test.js` splitMpvArgs cases + TC-CFG-08 console warning |
| SEC-14 | fail | dirs `cache/omarchy-iptv`, `state/omarchy-iptv`, `runtime/omarchy-iptv` 700; `channels.json`, `playlist-status.json`, `epg-*.json`, `epg-window.txt` 600; `mpv.sock` 600; `state.json` 644 - D-LIVE-04 |
| SEC-15 | pass | TC-INST-07 |
| SEC-16 | pass | `find . -name .git -prune -o -type l -print`: nothing; validate exit 0 |
| SEC-17 | pass | IPC `play 'http://evil.example.test/x'` -> `unknown`; `play -- '--script=/tmp/x'` -> `unknown`; `play u:deadbeef` -> `unknown`; nothing launched |
| SEC-18 | pass | grep for XMLHttpRequest / fetch( / openUrlExternally / WebSocket: nothing |
| SEC-19 | pass | `tests/test_epg.py::test_entity_expansion_bomb_is_refused_quickly` |
| SEC-20 | not run | no automated redirect test found under `tests/`; README Limits (acd1723) documents the refusal of non-http redirects |
| SEC-21 | pass | `channels.json` 600 inside a 700 dir; README Settings section carries the credential warning |

### PERF - Performance

| ID | Result | Evidence |
|---|---|---|
| PERF-01 | pass | helper `playlist`: gen-10k.m3u durationMs 464/479 (wall 0.59 s), 10,000 channels / 120 groups, `channels.json` 2,610,946 B; index.m3u 523/530 ms (wall 0.64 s), 11,041 / 30 groups, 3,209,652 B; us.m3u 67/76 ms, 1,475 / 28; maxrss 25-52 MB |
| PERF-02 | pass | IPC method on the 11k cache: open 111/118/121/117/140 ms (median 118) minus `ipc widget` baseline 53-55 ms = ~64 ms; layer-map method: 149/174/176 ms from before the toggle call incl. ~54 ms IPC transport and 9 ms poll granularity = ~90-120 ms to a mapped overlay |
| PERF-03 | pass | 38 keys (`wtype -d 20` x18 then `-d 1` x20) all present in order, state settled <= 117 ms after the last key; single key wtype -> state 154-194 ms incl. process spawn and the 54 ms IPC read; pure filter 6.7 ms (`a`), 2.3 ms (`news`), < 2 ms others on 11,041 rows |
| PERF-04 | pass | `epg` on gen-10k.xml.gz (3.4 MB gz, 264k programmes): wall 2.88 s, durationMs 2757, maxrss 60 MB, `epg-now.json` 908,876 B (5,840 channels), `epg-window.txt` 3.2 MB; `epg --now-only` 37 ms; Pluto gz 0.44-0.51 s; gen-real.xml 0.35 s |
| PERF-05 | pass | harness quickshell RSS: 305 MB after the 11k load, 383 MB after 20 opens, 438 MB before / 381 MB after 20 more (no monotonic growth); the live shell was not measured |
| PERF-06 | pass | local stream: open + query + Enter -> window 594/673 ms, `time-pos` 1.9 s one second later (first frame inside ~1 s); ABC News Live 1: window 523 ms, media-title at 1.1 s; one run failed right after the hung-mpv test (D-LIVE-15) |
| PERF-07 | pass | `r` on 11k then `/` + `abc news`: every key registered, 17 matches shown while the footer read `Refreshing...`; same during the 41 MB EPG parse (TC-EPG-12) |

## 4. Performance numbers and methods

| ID | Budget | Measured | Method |
|---|---|---|---|
| PERF-01 | `playlist` < 1 s (PLAN G3), < 1.5 s (ARCH) | gen-10k.m3u: durationMs 464 / 479, wall 0.59 s; index.m3u (11,041): 523 / 530 ms, wall 0.64 s; us.m3u: 67 / 76 ms | `python3` wrapper around `bin/omarchy-iptv playlist --url <file> --cache-dir /tmp/claude-1000/omarchy-iptv-qa/cache-perf/<name>`, two runs each, `durationMs` from the JSON, wall = `time.monotonic()`, RSS = `resource.getrusage(RUSAGE_CHILDREN)`. `channels.json` 2,610,946 B (gen-10k) / 3,209,652 B (index) - above the ~2 MB note in the plan, informational |
| PERF-02 | overlay open < 150 ms with the 10k cache | IPC: open 111 / 118 / 121 / 117 / 140 ms (median 118) against a 53-55 ms `ipc widget` baseline = ~64 ms of open work; layer map: 149 / 174 / 176 ms from before the `ipc toggle` call (includes the ~54 ms IPC transport and 9 ms poll granularity) = ~90-120 ms | harness on `index.m3u` (11,041 rows); `date +%s%N` around `h.sh ipc toggle`; frame proxy = polling `hyprctl layers -j` for the `omarchy-iptv` namespace every ~9 ms |
| PERF-03 | keystroke to redraw < 30 ms, no dropped keys | 38 keys, all present and in order, state settled within 117 ms (one poll) of the last key; single-key wtype -> state 154-194 ms (dominated by process spawn + the 54 ms IPC read, an upper bound); pure `Model.filterChannels` on 11,041 rows: `a` 6.72 ms, `news` 2.30, `alpha news` 1.93, `zz` 1.58, `abc news live` 1.89; `groupChannels` 4.64 ms | `wtype -d 20 'alpha news channel'` then `wtype -d 1 'zzzzzzzzzzzzzzzzzzzz'` and `h.sh ipc state` polling; node micro-benchmark (50 iterations per query) on `cache-perf/index/channels.json` after `Model.prepareChannels` |
| PERF-04 | `epg` < 4 s for a large gz, RSS < 300 MB | gen-10k.xml.gz: wall 2.88 s, durationMs 2757 / 2759, maxrss 60 MB, `epg-now.json` 908,876 B (5,840 channels, 82,000 programmes kept in the window), `epg-window.txt` 3,188,708 B; `epg --now-only` 37 ms (wall 0.15 s); Pluto us.xml.gz 322-393 ms (0 matches); gen-real.xml (plain, 3.3 MB) 229 ms | same wrapper with `--force`; the isolated child run gives the 60 MB peak |
| PERF-05 | informational | harness quickshell RSS 305,396 KB after loading 11k; 383,072 KB after 20 opens; 438,480 KB before and 381,264 KB after 20 more opens | `ps -o rss= -p <harness pid>`; the live shell process was not measured (not installed) |
| PERF-06 | zap under 2 s of interaction | local stream: open + `live a` + Enter -> window mapped 594 ms, `time-pos` 1.98 s one second later; `other` 673 ms / 1.85 s; ABC News Live 1 (real HLS): window 523 ms, media-title after 1.1 s | `date +%s%N` before `h.sh ipc open`, `hyprctl clients -j` polled every 50 ms for class `omarchy-iptv`, mpv `time-pos` read over the IPC socket (read-only helper `bin/mpvq.py`) |
| PERF-07 | refresh does not stall the shell | typing during the 11k refresh and during the 2.95 s EPG parse registered every key | `r` then `/` + text; `ipc set epgUrl gen-10k.xml.gz` then text |

## 5. Console and notification hygiene

- Harness console across all runs: no QML warning or error from `Service.qml`, `Guide.qml`, `BarWidget.qml` or `Model.js`. The only WARN lines are Quickshell's own `qt.qpa.services` portal registration message (harness-only, present before the plugin loads) and the plugin's intentional `omarchy-iptv playlist: ... could not reach 10.255.255.1: timed out` / `... [Errno 111] Connection refused` / `omarchy-iptv epg: ... HTTP 404 from i.mjh.nz` helper-stderr relays (host only), `omarchy-iptv: ignoring mpvArgs tokens: ...`, `omarchy-iptv: mpv unresponsive, restarting player` (TC-PLAY-09) and `omarchy-iptv: play failed: mpv did not answer` (D-LIVE-15).
- Notification argv observed (all with `--app-name IPTV` and a fixed `-r` id per event): `Stream failed` normal U+F0503 id 74011; `Playlist refreshed` low U+F0450 id 74012; `Playlist error` normal U+F0026 id 74013 (both the `Using cached copy from HH:MM.` and the `Open the guide for details.` bodies); `Guide data error` low U+F0026 id 74014. Texts match UX 6.4 verbatim.

## 6. Privacy sweep (SEC-07, TC-CFG-13)

Setup: run7, `--playlist tests/fixtures/qa-attrs.m3u`; the entry with an empty title and `http://user:secret@stream.example.test/live/user/secret/1.ts` parses to `{id: u:46b30f8f, name: Channel 11, group: Ungrouped}` (D-QA-02 fixed: the name is never the URL). Played it with Space; mpv failed on DNS.

| Sink | Content | Hits for `user:` / `secret` / `stream.example.test/` / `/live/` |
|---|---|---|
| harness console `logs/run7.log` | no warning at all | 0 |
| notification argv `logs/notifications.log` | `Stream failed` / `Channel 11 did not play - Failed to open stream.example.test` | 0 |
| IPC `status` verb `logs/run7-status.json` | `nowPlaying: null`, `lastError: Failed to open stream.example.test` | 0 |
| harness state dump `logs/run7-ipcstate.json` (guide + service, incl. `lastError`, `failedAt`) | host only | 0 |
| widget JSON / tooltip `logs/run7-widget.json` | `IPTV - click to open the guide` | 0 |
| `state.json` `logs/run7-state.json` | `recents: [{id: u:46b30f8f, name: Channel 11}]` | 0 |
| `playlist-status.json` | `sourceHost: local file` | 0 |
| guide screenshot `shots/run7-failed-card.png` | row `Channel 11` / `Ungrouped - Failed 00:23 - Space to retry`, footer `22 channels - updated 00:23` | none visible |
| `channels.json` (cache, mode 600 in a 700 dir) | holds the full URL by design (ARCH section 6 caveat) | 1, expected |
| mpv argv | the first launch passes the URL on the command line (SEC-06 shows `--` then the URL; README Playback notes document the `ps` exposure until M2) | expected |

Verdict: pass. No credential or URL beyond scheme+host reaches the console, notifications, IPC status, tooltip, guide, or state file. Helper stderr lines relayed to the console carry the host only (`could not reach 10.255.255.1`, `HTTP 404 from i.mjh.nz`).

## 7. Needs live shell

Cases: TC-INST-02/03/04(journal)/05/06/08/09/10, TC-CFG-01 (`omarchy bar set` -> `shell.barConfig`), TC-CFG-07 (timer re-arm), TC-BRW-01, TC-BRW-04, TC-PLAY-11, TC-UI-05, TC-A11Y-04 (needs a second monitor), plus the mouse cases (TC-BRW-02/19/23, TC-BAR-06/07/08, TC-FAV-11, TC-A11Y-03 clicks) which only need a hand on the mouse.

Commands for the lead, in order (each changes the user's desktop; all reversible by the last block):

```
cp ~/.config/omarchy/shell.json /tmp/claude-1000/omarchy-iptv-qa/shell.json.before        # snapshot, mode 0600
git clone /home/ricky/Projects/omarchy-iptv ~/.config/omarchy/plugins/io.github.rmcdavid.iptv   # TC-INST-02: a clone, never a symlink
omarchy plugin validate ~/.config/omarchy/plugins/io.github.rmcdavid.iptv                 # expect exit 0
omarchy-shell shell rescanPlugins
omarchy plugin enable io.github.rmcdavid.iptv                                             # TC-INST-03
omarchy plugin list --json | jq '.[] | select(.id=="io.github.rmcdavid.iptv")'             # enabled: true, kinds bar-widget,overlay,service
jq '.bar.layout.right[-1]' ~/.config/omarchy/shell.json                                   # {"id":"io.github.rmcdavid.iptv"}
journalctl --user -t omarchy-shell --since -5m | grep -iE 'warn|error' | grep -v Qt.atob     # TC-INST-04: nothing from our files
omarchy bar set io.github.rmcdavid.iptv playlistUrl https://iptv-org.github.io/iptv/countries/us.m3u   # TC-CFG-01: within ~1 s the bar tooltip is idle and the guide footer reads 1,475 channels - updated HH:MM
omarchy bar set io.github.rmcdavid.iptv epgUrl https://i.mjh.nz/PlutoTV/us.xml.gz          # TC-CFG-06 on the live path: with D-LIVE-02 open, expect the EPG to stay pending until r; confirm, then press r
# keybinding (contrib/bindings.lua line) -> ~/.config/hypr/bindings.lua, then reload Hyprland config:
o.bind("SUPER + SHIFT + T", "IPTV", "omarchy-shell shell toggle io.github.rmcdavid.iptv")
# TC-BRW-01: press SUPER+SHIFT+T twice (open, close). TC-BRW-02 / TC-BAR-06: left click the TV glyph twice.
# menu row (contrib/omarchy-menu.jsonc line) -> ~/.config/omarchy/extensions/omarchy-menu.jsonc; TC-BRW-04: open the menu, type tv, Enter
omarchy bar set io.github.rmcdavid.iptv refreshMinutes 15 --json && journalctl --user -t omarchy-shell -f   # TC-CFG-07: a silent helper run at +15 min
# TC-BAR-07/08/09: right click (stop), middle click (refresh -> notification), wheel over the glyph while playing (zap)
# TC-BRW-19/23, TC-FAV-11, TC-A11Y-03: scrim click closes, card click is swallowed, wheel over the list scrolls / over the column moves one entry, lead-slot click toggles the star
omarchy theme set tokyo-night; omarchy theme set catppuccin-latte; omarchy theme set retropc   # TC-UI-05, guide open during the second switch; then the journal grep above again
omarchy-shell shell rescanPlugins                                                          # TC-INST-09 while a channel plays: mpv keeps playing
omarchy restart shell                                                                     # TC-INST-08 / TC-PLAY-11 / TC-FAV-08: mpv exits, widget returns, favorites and playlistUrl intact
omarchy plugin disable io.github.rmcdavid.iptv; omarchy plugin enable io.github.rmcdavid.iptv   # TC-INST-05: settings gone after disable (README must say so, D-LIVE-13)
omarchy plugin remove io.github.rmcdavid.iptv --yes                                       # TC-INST-06 / TC-INST-10
rm -rf ~/.cache/omarchy-iptv ~/.local/state/omarchy-iptv /run/user/1000/omarchy-iptv
diff <(jq -S . /tmp/claude-1000/omarchy-iptv-qa/shell.json.before) <(jq -S . ~/.config/omarchy/shell.json)   # no output
# then remove the bindings.lua and omarchy-menu.jsonc lines by hand
```

What to look for is the Expected column of the corresponding `docs/QA.md` rows; the harness pass already verified every string and state those rows name, so the live pass is about the host integration (settings propagation, keybinding, menu, theme tokens re-skinning live, plugin lifecycle).

## 8. Defects found in this pass (details; rows in docs/STATUS.md)

### D-LIVE-01 (TC-BRW-09, TC-BRW-10, TC-RFR-10, TC-UI-10)  P2  found 2026-09-12/13 at f03fef2 - browse / Guide.qml, Model.js

Steps: 1. `h.sh --open --playlist gen/gen-500.m3u` (or any list with more than 200 channels, e.g. us.m3u). 2. Do not type; look at the All entry, press End.

Expected: UX 2.2: All is `every channel in playlist order`; UX 2.6 / R3 cap `the first 200 matches` of a *search* with the footer `First 200 of 1,240 - keep typing`; UX 3.1 End = `Last ... channel row`; UX 6.1 footer normal state `1,204 channels - updated 12:40`.

Actual: With an empty query All (and any group over 200) shows only 200 rows; the footer reads `First 200 of 500 - keep typing` while nothing was typed (`shots/run3-banner.png`, `run6-cap.png` state `rows: 200, resultTotal: 11041`); End/PgDn stop at row 199; channels 201+ are unreachable by browsing; the `N channels - updated/cached HH:MM - offline` footer (US7 hint) is never visible on such lists.

Evidence: `h.sh ipc state` dumps in `logs/` for run3/run6: `{"query":"","rows":200,"resultTotal":500,"footer":"First 200 of 500 - keep typing"}`; `shots/run3-banner.png`, `harness/shots/run6-cap.png`.

### D-LIVE-02 (TC-CFG-06, TC-EPG-01)  P2  found 2026-09-12/13 at f03fef2 - EPG / Service.qml `onEpgUrlChanged` -> `refreshEpg` -> `epgDebounce` -> `runEpgHelper`

Steps: 1. `h.sh --open --playlist gen/gen-500.m3u` (no `--epg`). 2. `h.sh ipc set epgUrl /tmp/.../gen/gen-500.xml` (what `omarchy bar set ... epgUrl` does). 3. Watch `h.sh ipc state | jq .service.epg` and the cache dir for 10 s.

Expected: US6 / TC-CFG-06: `epgUrl set later ... epg-now.json appears; rows get Now/Next`; UX 6.1 footer `Guide data loading...` only until the data lands.

Actual: `epg: {configured: true, loaded: false, pending: true}` indefinitely; no `python3 bin/omarchy-iptv epg` process is spawned (4 s process watch, run9b), no `epg-status.json` / `epg-now.json`; the footer stays `Guide data loading...` (run6). A manual `r` fetches it; changing a non-empty `epgUrl` to another value fetches within 300 ms; clearing and re-setting reproduces the hang (run8a). Reproduced 4 times (run6, run8a, run9, run9b).

Evidence: `logs/run8a.log`, `logs/run9b.log` command output (`epg helper seen in 4 s: NO`), state dumps quoted in this file. The live first-run flow in README (`playlistUrl` then `epgUrl`) hits exactly this path, so the default 360 min timer is the first time the EPG would load.

### D-LIVE-03 (TC-RFR-09, TC-PARSE-09)  P3  found 2026-09-12/13 at f03fef2 - refresh / Model.js `statusReason` table

Steps: Serve `tests/fixtures/qa-not-m3u.html` (`python3 -m http.server 8766`) and set `playlistUrl http://127.0.0.1:8766/qa-not-m3u.html` with no cache.

Expected: UX 6.3 reason `Not an M3U file`, rendered as `Not an M3U file from 127.0.0.1 - check playlistUrl`.

Actual: `source from 127.0.0.1 is not an M3U playlist (no #EXTM3U or #EXTINF lines) from 127.0.0.1 - check playlistUrl` (host twice); `Model.statusReason` maps `not_m3u` but the helper emits `not_a_playlist`, so the raw (redacted) helper sentence falls through.

Evidence: `harness/shots/run2-notm3u.png`; helper CLI output `{"error": {"code": "not_a_playlist", ...}}`.

### D-LIVE-04 (TC-FAV-08, SEC-14)  P3  found 2026-09-12/13 at f03fef2 - state / Service.qml `stateFile` FileView `setText`

Steps: Favorite any channel in the harness; `stat -c '%a' $OMARCHY_IPTV_HARNESS_DIR/state/omarchy-iptv/state.json`.

Expected: ARCHITECTURE.md section 6 / 8.5: state files `mode 0600, dir 0700`; QA.md TC-FAV-08 `state.json 0600`.

Actual: `644` (dir is 700; every helper-written cache file is 600). The FileView write uses the process umask. Contains channel ids and names only, no URLs, hence P3.

Evidence: `stat` output in the run1 and run1c command logs (`644 ricky .../state/omarchy-iptv/state.json`).

### D-LIVE-05 (TC-RFR-01, TC-BAR-08)  P3  found 2026-09-12/13 at f03fef2 - refresh / Guide.qml transient after a manual refresh

Steps: Guide open, list mode, press `r`; poll the footer every 250 ms.

Expected: UX 6.1: `Refreshing...` then `Refreshed - 1,204 channels` (transient), then the normal status; TC-RFR-01 / TC-BAR-08.

Actual: `Refreshing...` stays for the full 3 s transient (the helper finished after ~40 ms, the `Playlist refreshed` notification fired at once), then the footer goes straight to `10 channels - updated 23:41`; `Refreshed - N channels` never appears.

Evidence: run1 poll log: `06.067 Refreshing...` ... `08.707 Refreshing...` / `09.035 10 channels - updated 23:41`; `harness/shots/run1-refreshed.png`.

### D-LIVE-06 (TC-BRW-21)  P3  found 2026-09-12/13 at f03fef2 - browse / Model.js `groupChannels` first-seen order

Steps: `h.sh --open --playlist tests/fixtures/qa-groups.m3u`; read the GROUPS column.

Expected: UX 2.2 item 4: groups `in playlist order (first appearance). Channels with no group land in a synthetic last group named Ungrouped`; QA TC-BRW-21 `Ungrouped last`.

Actual: `Animation, UK | SPORTS, Sports, Movies, News, Ungrouped, Padded, Leading Semicolon` - Ungrouped takes the position of its first ungrouped channel. `Model.test.js` `groupChannels playlist order with counts` only passes because Ungrouped happens to be last in that fixture.

Evidence: `harness/shots/run1-open.png`; `h.sh ipc state` scopes list.

### D-LIVE-07 (TC-FAV-05)  P3  found 2026-09-12/13 at f03fef2 - favorites / Guide.qml scope handling when Recent empties

Steps: Play one channel, move the column to Recent, press `x` on the only row.

Expected: UX 2.2: Recent `Hidden while empty (no row, no gap)`; the column should land on a visible entry (Favorites or All).

Actual: The Recent entry disappears from the column but the cursor scope stays `recent`: the list shows `No channels in Recent`, the scope label `Recent - 0 channels`, and no column entry is highlighted until the user moves.

Evidence: `shots/run1-recent-removed-card.png`; state `{scopeId: recent, rows: 0, emptyKind: emptyScope}` with `recent` absent from `scopes`.

### D-LIVE-08 (TC-EPG-04)  P3  found 2026-09-12/13 at f03fef2 - EPG / Guide.qml `bannerKind` (`epgError` requires `!epgLoaded`)

Steps: With an EPG already loaded set `epgUrl https://i.mjh.nz/PlutoTV/nope.xml.gz`, press `r`.

Expected: UX 6.3: banner `Guide data unavailable (<reason>) - channels still work - r retry` (low emphasis); UX 4.6-style banner `stays until the next successful refresh`.

Actual: Notification `Guide data error` is sent and `epg.reason` is `HTTP 404 Not Found`, but the guide shows no banner (`bannerKind: none`) and keeps rendering the stale window silently; the banner only appears when no EPG was ever loaded.

Evidence: `harness/shots/run5-epg-404.png`; run5 state dump `{bannerKind: none, epg: {loaded: true, reason: HTTP 404 Not Found}}`.

### D-LIVE-09 (TC-UI-01)  P3  found 2026-09-12/13 at f03fef2 - states / Guide.qml `r` in the unconfigured state

Steps: `h.sh --open --playlist none`, press Tab then `r`.

Expected: UX 4.4 hint `r reload - Esc close`; nothing to reload, so no transient (UX 6.1 lists `Refreshing...` for an actual refresh).

Actual: Footer shows `Refreshing...` for 3 s although `refreshPlaylist` returns early (`!configured`) and nothing runs.

Evidence: run3 state dump `{emptyKind: unconfigured, footer: Refreshing...}`.

### D-LIVE-10 (TC-UI-02)  P3  found 2026-09-12/13 at f03fef2 - states / Guide.qml error -> loading transition

Steps: With no cache and an error shown (e.g. after the not-M3U case), set `playlistUrl` to a slow host (`http://10.255.255.1/x.m3u`).

Expected: UX 4.5: `Loading playlist...` / `Fetching from <host>` when no cache exists (shown correctly from the unconfigured state, `shots/run3-loading.png`).

Actual: The previous source's error stays on screen (`source from 127.0.0.1 is not an M3U ...`) with the footer `Refreshing...` and `sourceHost` already `10.255.255.1`, for the whole 20 s fetch; the old reason names a different host than the one being fetched.

Evidence: run2 state dumps: `{emptyKind: error, footer: Refreshing..., sourceHost: 10.255.255.1, playlistReason: source from 127.0.0.1 ...}`.

### D-LIVE-11 (TC-CFG-02)  P3  found 2026-09-12/13 at f03fef2 - docs + Model.js `statusReason` timeout wording

Steps: Set `playlistUrl http://10.255.255.1/x.m3u` with no cache and wait.

Expected: UX 6.3 reason `Timed out after 30 s`; README (acd1723) Limits: `Downloads ... must finish within 60 seconds`.

Actual: Helper `DEFAULT_TIMEOUT = 20` (the error arrives at +20 s), the guide renders `Timed out` (no duration), README says 60 s: three different numbers in three places.

Evidence: run3 log `t+20s status=error`, `playlistReason: Timed out`; `bin/omarchy-iptv:64`.

### D-LIVE-12 (TC-BAR-09)  P3  found 2026-09-12/13 at f03fef2 - bar / Service.qml `play` early return keeps `launchedFrom`

Steps: Play A from All (ring = its group). Open the guide on Favorites (A and C favorited), press Enter or Space on A (already playing). `h.sh ipc zap 1`.

Expected: UX 3.4: the ring is `the list the playing channel was launched from`: Favorites when played from Favorites; `next` should go to C.

Actual: The `already playing -> no reload` path returns before `launchedFrom` is updated, so the ring stays the group and `zap 1` goes to B. Re-selecting a channel from another list never moves the ring. Debatable by UX wording, hence P3.

Evidence: run4 IPC status `launchedFrom: g:Local` after the Favorites re-select; the keyboard-only rerun (fresh launch from Favorites) gives `launchedFrom: favorites` and A -> C -> A.

### D-LIVE-13 (TC-INST-05, TC-INST-10, TC-BAR-12, TC-UI-13)  P3  found 2026-09-12/13 at f03fef2 - docs / README.md

Steps: Read README sections Uninstall, Playback notes, Development.

Expected: QA.md TC-INST-05 `README must say settings are lost on disable`; TC-INST-06 three leftover dirs; TC-BAR-12 `README mentions the limitation` (third-party bar facade); TC-UI-13 baseline qmllint warnings `recorded in README`.

Actual: None of the four is in README: no disable warning, Uninstall lists two dirs (`$XDG_RUNTIME_DIR/omarchy-iptv` missing although `Files it writes` names it), no third-party-bar note, no qmllint baseline (only `scripts/check.sh` comments describe it).

Evidence: README.md at acd1723 (`grep -n -i 'disable\|third-party\|qmllint' README.md` -> only the Development command line).

### D-LIVE-14 (TC-UI-13)  P3  found 2026-09-12/13 at f03fef2 - lint / Guide.qml, BarWidget.qml, Service.qml

Steps: `/usr/lib/qt6/bin/qmllint -I /tmp/qmlroot -I /usr/lib/qt6/qml Service.qml BarWidget.qml Guide.qml`.

Expected: QA.md section 2: accepted baseline = `unqualified access / missing property on injected bar, shell, service`; PLAN G0 `only the baseline warnings`.

Actual: 106 warnings: 57 missing-property, 42 unqualified (baseline categories) plus 6 `signal-handler-parameters` and 1 `uncreatable-type`, which are outside the recorded baseline. 0 errors; check.sh passes because it only fails on errors.

Evidence: qmllint category counts in the TC-UI-13 command log.

### D-LIVE-15 (PERF-06, TC-PLAY-09)  P3  found 2026-09-12/13 at f03fef2 - playback / Service.qml health-check relaunch path

Steps: 1. Play a local stream. 2. `kill -STOP <mpv>`; wait for `mpv unresponsive, restarting player` (x2 within ~45 s). 3. `kill -CONT <mpv>`, `h.sh ipc stop`, wait 3 s. 4. Open the guide, query, Enter.

Expected: TC-PLAY-01: `exactly one mpv`, window with the channel title; PERF-06 under 2 s.

Actual: That play attempt logged `omarchy-iptv: play failed: mpv did not answer` and no window appeared for the 6.6 s poll (`query 'live b': window mapped 6635 ms; time-pos null; title empty`); the next attempt worked (673 ms). Plain stop -> play within 0.5 s does not reproduce it (mpv exits 245 ms after stop). Looks like a stale `mpvProc.running` / `relaunchPending` state after the SIGTERM-that-could-not-be-delivered sequence; needs an FE look rather than a QA verdict.

Evidence: run4 console lines `play failed: mpv did not answer` (x2) and the PERF-06 run-2 line in the command log.

## 9. Observations that are not defects

- The first channel of a session is passed to mpv on the command line (URL visible via `ps`); later channels travel over the IPC socket. README (acd1723) documents it as an M2 item.
- `s` with nothing playing shows `Stopped` (harmless). Playing a dead channel while another plays makes mpv exit (`--idle=no`), so a bad zap ends playback with the failure notification; the previous channel is not restored (design, R11).
- The startup refresh with the source down notifies once (`Using cached copy from HH:MM.`), which R12 allows for a timer-driven failure.
- `channels.json` for index.m3u is 3.2 MB (2.6 MB for the synthetic 10k), above the plan's ~2 MB note; open time is still inside budget.
- Pluto XMLTV ids do not match iptv-org `tvg-id`s (0 of 1,475), as QA-ASSETS.md predicts; the helper reports it in `warnings` and the guide shows plain rows.
- `bin/__pycache__` and `tests/__pycache__` exist in the working tree from test runs (`helper_loader.py` imports the helper), not from runtime; `.gitignore` covers them.
- QA.md corrections made in this pass (v0.2): helper code name `not_a_playlist` (was `not_m3u`) in TC-PARSE-09, TC-RFR-09, 5.4 US7 step 8, the fixture table and D-QA-13; TC-PLAY-09 / 5.4 US3 step 9 no longer claim `kill -CONT is not needed` (mpv traps SIGTERM).


# Regression on 2ce0b52 (M1.1-06)

Owner: QA. Written 2026-09-13 after the re-test of 2026-09-13 01:22 - 01:58. Code under test: `main` at `76ad317` (docs-only on top of `2ce0b52`, the merge of the security fix round S-01..S-08 at `134fbe1` and the QA-defect fix round D-LIVE-01..15 at `dc5e9a3`/`1acf232`/`c969871`); `git diff --stat 2ce0b52 76ad317 -- bin Model.js Service.qml Guide.qml BarWidget.qml manifest.json scripts` is empty. Same method as the first pass (section 1): dev harness with fake shell/bar/settings, scratch XDG dirs under `/tmp/claude-1000/omarchy-iptv-qa2/harness`, the notification shim, quickshell killed by PID between runs; nothing installed, nothing under `~/.config` or `~/.local/state` touched, no `omarchy theme set` / `hyprctl dispatch|reload` / `omarchy plugin ...` / `omarchy bar set` / sudo. Same machine (Omarchy 4.0.3-1, Quickshell 0.3.1, Hyprland 0.56.2, mpv 0.41.0, Python 3.14.7, node 26.8.1, one 1366x768 output). Evidence: `/tmp/claude-1000/omarchy-iptv-qa2/`: `logs/run<N>.log` harness consoles, `logs/run<N>-cmd.log` command transcripts, `logs/notifications.log`, `logs/s05-trickle.log`, `logs/s06-redirect.log`, `logs/qmllint.txt`, `logs/perf03-node.log`, `shots/*.png` (48 grim screenshots, inspected), `gen/gen-50500.m3u` (sha256 `4f944330...c212`, 50,500 entries / 7,152 group titles), `fixtures/sec.m3u`, `cache-perf/*`. No pointer automation was available again (no ydotool/dotool), so the mouse cases stay `not run`.

Harness pitfall added to the section 1 list: a `wtype` string sent while the guide is in list mode is read as commands (`r` refreshes, `s` stops, `f` favorites) and a later Tab keeps the old query, so one run-5 sequence went wrong and was redone as run5b; `ipc open '{}'` resets mode and query, and `ipc query <text>` / `ipc activate` avoid the ambiguity.

Conventions as in section 1: ` - ` stands for U+00B7 and `...` for U+2026 in quoted microcopy; the curly quotes of the S-04 body are written `"` here. Runs: run1 `index.m3u` (11,041), run2 `gen-500.m3u` + XMLTV, run3/3b/3c `qa-groups.m3u` (+ `qa-unicode.m3u` via a runtime `playlistUrl` change), run4/4b unconfigured and error states, run5/5b/5c/8/9 `--serve` with `fixtures/sec.m3u` (channels named `${path}`, `BBC ${options/input-ipc-server}`, `-u critical`, `--urgency=x`, Live A/B/C, Dead D, Live E), run6 `gen-50500.m3u`, run7 `qa-attrs.m3u` (privacy).

## R1. Gates

`omarchy plugin validate .` -> exit 0, no output. `scripts/check.sh` (21.9 s) tail:

```
271 checks, 0 failure(s)
All Model.js tests passed.
ok   node tests
== python3 -m unittest discover -s tests
Ran 144 tests in 20.097s
OK
ok   python tests
== qmltestrunner tests/Model.spec.qml
ok   qml spec (18 passed)
== ascii check (code files)
ok   ascii check
check.sh: all green
```

qmllint (D-LIVE-14): 0 errors; 57 `missing-property`, 51 `unqualified`, 1 `uncreatable-type` (PanelWindow, `Guide.qml:591`), 0 `signal-handler-parameters`; `Service.qml` 0 warnings, `BarWidget.qml` 14, `Guide.qml` 95. All three categories are the README baseline; `unqualified` went 42 -> 51 with the Guide rework (same category).

## R2. Defect verification

| Defect | Result | Repro re-run and evidence |
|---|---|---|
| D-LIVE-01 (P2) | verified fixed | run1 `index.m3u`: open state `rows 11041, resultTotal 11041, truncated false`, footer `11,041 channels - updated 01:27`, scope label `All - 11,041 channels`; End -> cursor 11040 (a Chinese-named channel, `shots/run1-end.png`), Home -> 0, PgDn +8 (visible-1) x3 -> 24, PgUp -> 16, Up on row 0 wraps to 11040, Down on the last row wraps to 0, PgDn at End and PgUp at Home clamp; query `a` -> 200 rows, `First 200 of 8,579 - keep typing`, End -> 199 (`shots/run1-cap.png`); Ctrl+U -> 11,041 again; `4k` -> 7 matches. Same on run6 (50,000 rows, End -> 49,999). Wheel: not run (no pointer) |
| D-LIVE-02 (P2) | verified fixed | run2 `gen-500.m3u` started with `epgUrl` empty (`epg: {configured false, loaded false, pending false}`): `ipc set epgUrl .../gen-500.xml` (the `omarchy bar set` path through `shell.barConfig`) -> `python3 bin/omarchy-iptv epg` seen in the process watch within 300 ms, `epg.loaded true` at +747 ms, `epg-now.json` 43,658 B, rows carry `Now:`/`Next:`/`until` (`shots/run2-epg-loaded.png`); clear to empty then set again (the run8a repro) -> loaded at +593 ms; Pluto `.gz` -> loaded, 0 matches, no banner |
| D-LIVE-03 (P3) | verified fixed | run4: `playlistUrl http://127.0.0.1:8766/qa-not-m3u.html` -> `playlistReason: Not an M3U playlist`, host `127.0.0.1` (`shots/run4-notm3u.png`); helper code still `not_a_playlist` |
| D-LIVE-04 (P3) / S-02 | verified fixed | run3: after the first `f`, `700 state/omarchy-iptv`, `600 state.json`; still 600 after a FileView write on restart (run3b) and after rewriting a garbage file (run3c) |
| D-LIVE-05 (P3) | verified fixed | keyboard `r` polled every ~60 ms: run2 `Refreshing...` +71..+490 ms then `Refreshed - 500 channels` at +604 ms; run3 `Refreshed - 10 channels` at +493 ms, `10 channels - updated 01:35` after the 3 s transient; IPC `refresh` on run1 -> `Refreshed - 11,041 channels`; notification `Playlist refreshed` / `10 channels in 8 groups` low unchanged |
| D-LIVE-06 (P3) | verified fixed | run3 scopes `favorites, all, Animation, UK \| SPORTS, Sports, Movies, News, Padded, Leading Semicolon, Ungrouped` (`shots/run3-open.png`); run6 last entries `Group 1780 One, Group 2051 Action, Ungrouped=2091` |
| D-LIVE-07 (P3) | verified fixed | run3: `x` on the only Recent row -> footer `Removed from Recent`, scope `favorites` (2 rows, cursor on `EXTGRP One`), `recent` gone from the column (`shots/run3-recent-removed.png`) |
| D-LIVE-08 (P3) | verified fixed | run2 with gen-500 EPG loaded: `epgUrl http://127.0.0.1:8766/nope.xml` -> `bannerKind epgError`, `Guide data unavailable (HTTP 404 Not Found) - channels still work - r retry` with the neutral fill (`shots/run2-epg-404b.png`), notification `Guide data error` / `Could not fetch the EPG (HTTP 404 Not Found). Channels still work.` low, rows keep the old window; the banner survives `r` (playlist refresh succeeds, EPG 404 again) and clears 400 ms after the good URL is restored |
| D-LIVE-09 (P3) | verified fixed | run4 `--playlist none`: Tab, `r` -> footer `Set a playlist first` (`shots/run4-set-first.png`), no helper process, status slot blank otherwise |
| D-LIVE-10 (P3) | verified fixed | run4 from the not-M3U error: `playlistUrl http://10.255.255.1/x.m3u` -> at +500 ms `emptyKind loading`, `sourceHost 10.255.255.1`, `playlistReason ""`, screen `Loading playlist...` / `Fetching from 10.255.255.1`, hint `Esc close` (`shots/run4-loading.png`) |
| D-LIVE-11 (P3) | verified fixed | guide `Timed out` after ~20 s (run4, `shots/run4-timeout.png`), notification `Could not fetch the playlist (Timed out). Open the guide for details.`; helper CLI message `playlist download from 127.0.0.1 exceeded its deadline` (no seconds, `logs/s05-trickle.log`); README `within 60 seconds`; UX 6.3 `Timed out` |
| D-LIVE-12 (P3) | verified fixed | run5b: A played from All -> `launchedFrom g:Local`; Space on A from Favorites (A, E) -> no reload (same pid), `launchedFrom favorites`; `zap 1` -> E, `zap 1` -> A, `zap -1` -> E |
| D-LIVE-13 (P3) | verified fixed (docs) | README: disable note (line 167), `$XDG_RUNTIME_DIR/omarchy-iptv` in Uninstall (161), third-party bars (172), qmllint baseline (179-182) |
| D-LIVE-14 (P3) | verified fixed | R1: only baseline categories remain; `Service.qml` clean |
| D-LIVE-15 (P3) | verified fixed | run5b faithful sequence: A playing, `kill -STOP`, two `mpv unresponsive, restarting player` lines in 32 s, `kill -CONT`, `ipc stop`, 3 s (mpv count 0) -> open, `live b`, Enter: window 426 ms, title `Harness Live B`, `time-pos 2.0` at +1 s, no new `play failed`; next play (E) reused the pid. run5 (one restart before CONT): 406 ms. See D-LIVE-17 for a related new observation |
| S-01 (P2) | verified fixed | run5: Enter on the channel named `${path}` -> `hyprctl clients -j` title `${path}` (literal), argv `--title=$>${path}`, `--force-media-title=${path}`, mpv `title` property `$>${path}`, bar label `${path}` (`shots/run5-s01.png`); the IPC path (`set_property title` on the next channel) shows `BBC ${options/input-ipc-server}` literally; run8 `play t:s01` over the service IPC -> title `${path}` |
| S-02 (P3) | verified fixed | = D-LIVE-04 |
| S-03 (P3) | verified (docs) | README Playback notes lines 121-124 and ARCHITECTURE 12.1 document the first-launch argv; behaviour unchanged by design (run5b argv tail `-- http://127.0.0.1:8765/...`) |
| S-04 (P3) | verified fixed | helper strips leading dashes at parse time (`-u critical` -> `u critical`, `--urgency=x` -> `urgency=x`, `cache-perf/sec/channels.json`); run5 Space on `u critical` -> notification argv `--app-name IPTV -u normal -g U+F0503 -r 74011 'Stream failed' '"u critical" did not play - Failed to open 127.0.0.1'` with U+201C/U+201D around the name, row `Failed 01:43 - Space to retry`; run3/run7 bodies `"Multi Group Channel" did not play - ...`, `"Channel 11" did not play - ...` |
| S-05 (P3) | verified fixed | trickle server (one M3U line every 2 s, never ends) on 127.0.0.1:8769: `playlist --url` exit 1, `{"code": "timeout", "message": "playlist download from 127.0.0.1 exceeded its deadline"}` at wall 60.19 s / `durationMs 60052`, maxrss 30 MB (`logs/s05-trickle.log`); service watchdog 180 s present (`Service.qml:759-767`), not exercised |
| S-06 (P3) | verified fixed | `logs/s06-redirect.log`, source `http://user:secretpw@127.0.0.1:8767/...`: 302 to another origin (8768) -> ok, origin B received no `Authorization`; same-origin 302 -> ok, header kept; 302 to `ftp://` -> `unsafe_redirect` `redirected to an unsupported scheme 'ftp'`; 302 to `file:///etc/passwd` -> `unsafe_redirect` `redirect from 127.0.0.1 not followed`; no `secretpw` in stdout/stderr (QA SEC-20 now covered) |
| S-07 (P3) | verified fixed | CLI on `gen-50500.m3u` (50,500 entries, 7,152 group titles): 50,000 channels, 2,001 groups, warnings `truncated to 50000 channels (500 entries skipped)` and `group count capped at 2000; 2091 channels listed under Ungrouped`, 2,644/2,721 ms, maxrss 109 MB, `channels.json` 12,406,541 B; run6 guide: `Loading playlist...` at +1.4 s, 50,000 rows at +6.4 s from harness start, 2,004 column entries, open 97-139 ms IPC / 120-153 ms layer (R4), End -> 49,999, `a` -> `First 200 of 41,021`, RSS 553 MB. The warnings are not shown in the guide: D-LIVE-18 |
| S-08 (P3) | verified fixed | every run prints `playlist=local file epg=(none)` only; `--serve` runs (5, 5b, 5c, 8, 9) end with the fixture server on 8765 reaped and no harness mpv/quickshell left (`stop.sh` output `leftovers: none`); SIGKILL of `run.sh` not tested |

Verification counts: 23 verified fixed (15 D-LIVE, 8 S), 0 still open, 0 partially fixed, 0 reopened.

## R3. Regression sample

137 cases re-run with the first-pass methods (results per case below; cases not listed keep their first-pass result). No regression: every case that passed on f03fef2 passes on 2ce0b52; the seven first-pass failures and SEC-20 now pass.

| Category | Re-run | Result | Notes |
|---|---|---|---|
| INST | 01, 04, 07 | pass | gates (R1); consoles carry only the portal WARN and the intentional helper-stderr relays (host only) and `ignoring mpvArgs tokens`; `find . -newermt '2026-09-13 01:22'` inside the plugin dir lists nothing before the docs edits |
| CFG | 02, 03, 04, 05, 06, 08, 12, 13 | pass | run4 `HTTP 404 Not Found`, `Could not resolve host`, `Unsupported URL`; run3 absolute path; CFG-06 = D-LIVE-02; run8 mpvArgs `--profile=fast --hwdec=auto-safe` kept, `--input-ipc-server=/tmp/x --title=X --no-idle` dropped with the console warning; run3 playlist switched 10 -> 11 -> 10 channels with the guide open; CFG-13 = R5 |
| BRW | 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 21, 22, 25 | pass | run3: opens on All while Favorites is empty and on Favorites once populated (run3b); `kids` -> 1, `tele`/`TELE quebec`/`cafe`/`ecole` on `qa-unicode.m3u` -> 1/1/2/1 with accents, Backspace / Ctrl+Backspace / Ctrl+U; typing on Favorites jumps to All and Ctrl+U restores Favorites; Right from All -> `g:Movies`, Left x3 wraps to `g:Interactive` (run1); Esc clears then closes; Tab commits `spo` (3 matches), `q w 4` in list mode ignored, `/` back to search; `x` no-op on All, `s` -> `Stopped`; `No matches for "zzzz" in Animation` / `h/l other groups - Home for All` (`shots/run3-nomatch-group.png`) and `No matches for "zzzz"`; `4k` -> 7 on index; `Multi Group Channel` under Animation, found by `kids`; `ipc open '{"query":"sky"}'` prefills; every wtype key landed in the guide; BRW-08 node spot check `kids` on us.m3u: `Kids Movie Club` first |
| PLAY | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 12, 14 | pass | run5b/8/9: fresh launch window 436/437/457 ms, class `omarchy-iptv`, one mpv, `--ytdl=no`, `--` then the URL last; B reuses the pid; Enter on the playing row: `time-pos 3.3 -> 5.5`, guide closed, same pid; Space keeps the guide open with the play glyph, bold name and footer `U+F040A <name> - s stop` (`shots/run5-space-cues.png`); dead channel: notification with the quoted body, row `Failed HH:MM - Space to retry` (`shots/run3-failed-row.png`), Recent gains it, bar idle; `s`: mpv gone 358 ms, footer `Stopped`, no notification, widget idle; `q` in mpv: exits, no notification; STOP detection: `mpv unresponsive, restarting player` and a relaunched pid after CONT (run5); three Space presses end on the third row with one mpv; headers `--user-agent=QA-Agent/1.0` / `--referrer=...` on a fresh launch; run9: `f` in mpv -> Hyprland `fullscreen: 2`, guide layer above, after Esc still fullscreen, `pause false`, `mute false`, time-pos advancing (`shots/run9-over-fullscreen.png`) |
| BAR | 01, 02, 03, 04, 09 | pass | idle `{U+F0502, "", IPTV - click to open the guide}`; `IPTV - no playlist configured`; playing `{U+F0567, Harness Live A, Playing Harness Live A}` width 136; error `{U+F0503, IPTV - playlist error, open the guide}`; ring via `service.zap`: from a group C -> B -> A, from Favorites A <-> E with wrap, from Recent the channel's group |
| FAV | 01-10 | pass | star + `Added to Favorites` / `Removed from Favorites`; `No favorites yet` (`shots/run3-fav-empty.png`); order C, A, B (`state.json` favorites `t:grp1.test, t:multi.test, t:pipe.test`); `f` at index 1 inside Favorites keeps cursor 1; FAV-05 = D-LIVE-07; Recent first after a play, replay moves B to the top (run8); dead channel recorded in Recent; favorites survive `--keep` restart with `state.json` 600; `garbage{{{` -> empty lists, no warning, `f` rewrites valid JSON; favorites count 2 across `r` |
| EPG | 01, 02, 03, 04, 05-11, 12 | pass | guide opens on the loading state while the playlist loads (run6); rows `Lifestyle - Now: Magazine Daily - Next: Movie Magazine`, `until 02:00`, hairline; rows without `tvg-id` show the group only (`shots/run2-epg-loaded.png`); EPG-04 = D-LIVE-08; 05-11 `tests/test_epg.py` in check.sh (144 python tests); hairline crop differs by 6.8 px after 66 s (`shots/run2-t0-row.png` vs `run2-t1-row.png`); 10 keys typed during the gen-10k.xml.gz parse, query `sky sports` intact |
| RFR | 01, 03, 04, 05, 06, 07, 08, 09, 10 | pass | RFR-01 = D-LIVE-05; banner `Playlist refresh failed (Connection refused) - showing cached copy from 01:37 - r retry`, notification `... Using cached copy from 01:37.` (`shots/run4-banner.png`); `r` twice in 100 ms -> one notification; refresh while A plays: same pid, `time-pos 0.8 -> 4.1`; `--keep` restart with the server down: 10 cached rows at +1.1 s with the banner and `10 channels - cached 01:37 - offline` (`shots/run4-cached-start.png`), banner gone after a successful `r`; cursor 49,999 on the 50k list -> 9 after switching to the 10-channel list; `Playlist has no channels`; RFR-09 = D-LIVE-03; the cached footer is now visible on every list size |
| UI | 01, 02, 03, 04, 06, 07, 08, 09, 10, 11, 12, 13, 14 | pass | `shots/run4-unconfigured.png` (footer blank, column hidden, `r reload - Esc close`), `run4-loading.png`, `run4-banner.png`, cues `run5-space-cues.png`; no hex/white/black/`Qt.rgba(` in `*.qml`; all 21 `font.family` bind the host font; layer mapped 75-99 ms after the toggle call; hint strings verbatim in the screenshots (`Esc clear` variant in `run3-nomatch-group.png`); labels `All - 11,041 channels`, `in All - 8,579 matches`, `Favorites - 0 channels`, `Interactive - 1 channel`; glyphs rendered; qmllint per R1; card 960x620 centred in every shot |
| A11Y | 05, 06 | pass | derived from PLAY-01/03/14 and PERF-02/03 |
| PARSE | 01-11 | pass | `tests/test_playlist.py` via check.sh; CLI `qa-not-m3u.html` -> `not_a_playlist`, `qa-empty.m3u` -> `empty_playlist`, exit 1 |
| MODEL | 01-07 | pass | 271 node checks, 18 QML spec cases, `test_fold_table_matches_model_js` |
| SEC | 01, 02, 03, 04, 05, 06, 07, 08, 09, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21 | pass | greps for shell strings / sudo / XMLHttpRequest empty; argv tail `--`, URL; R5 privacy; `/proc/self/environ` -> `unsafe_path`; `ftp://` -> `unsupported_scheme`; modes `700` cache/state/runtime dirs, `600` `channels.json` / `playlist-status.json` / `epg-*` / `state.json` / `mpv.sock` (owner ricky); no symlinks; service IPC `play` with `http://evil.example.test/x`, `u:deadbeef`, `file:///etc/passwd`, `-- --script=/tmp/x` -> `unknown`, nothing launched; SEC-20 by the S-06 mock (`file:` and `ftp:` both refused now) |
| PERF | 01-07 | pass | section R4 |

Not re-run (first-pass result kept): TC-CFG-07/09/10/11, TC-BRW-02/19/23/24, TC-PLAY-13, TC-BAR-05/06/07/08/10/11/12, TC-FAV-11, TC-RFR-02, TC-A11Y-01/02/03, SEC-10, TC-MODEL-08. **(2026-09-15: the kept result for TC-A11Y-01 and TC-BAR-11 is retracted -- it was a grep over source written to satisfy it. See "Accessibility harness runs" at the end of this file.)**

## R4. Performance, first pass vs now

| ID | Budget | f03fef2 (first pass) | 2ce0b52 (now) | Method (unchanged) |
|---|---|---|---|---|
| PERF-01 | `playlist` < 1 s | gen-10k 464 / 479 ms (wall 0.59 s); index 523 / 530 ms (wall 0.64 s); us 67 / 76 ms; maxrss 25-52 MB | gen-10k 484 / 475 ms (wall 0.60 s); index 552 / 548 ms (wall 0.67 s); us 74 / 71 ms; maxrss 25-51 MB; `channels.json` 2,610,946 / 3,209,652 B unchanged | `bin/timeit.py` wrapper, two runs each, `durationMs` from the JSON |
| PERF-02 | open < 150 ms with the 10k cache | IPC 111-140 ms (median 118) minus baseline 53-55 = ~64 ms; layer map 149 / 174 / 176 ms | IPC 65 / 72 / 67 / 69 / 75 ms (median 69) minus baseline 52-58 = ~12-17 ms; layer map 75 / 81 / 99 ms; 50k cache (new): IPC 97-139 ms, layer 120 / 120 / 153 ms | `date +%s%N` around `h.sh ipc toggle`; `hyprctl layers -j` poll for the `omarchy-iptv` namespace |
| PERF-03 | keystroke < 30 ms, no drops | 38 keys in order, settled <= 117 ms after the last key; single key 154-194 ms incl. spawn; filter `a` 6.72 ms, `news` 2.30, `alpha news` 1.93, `zz` 1.58, `abc news live` 1.89; groupChannels 4.64 ms | 38 keys in order, settled 95 ms after the last key (one poll); single key 126 ms incl. spawn; filter `a` 6.55 ms (best 5.06), `news` 2.15, `alpha news` 1.80, `zz` 1.50, `abc news live` 1.76, empty query 0.00 ms (same array); groupChannels 4.77 ms; prepareChannels 37 ms | `wtype -d 20` x18 + `-d 1` x20; node 50 iterations on `cache-perf/index/channels.json` |
| PERF-04 | `epg` < 4 s, RSS < 300 MB | gen-10k.xml.gz wall 2.88 s / 2757 ms, maxrss 60 MB, `epg-now.json` 908,876 B (5,840 channels); `--now-only` 37 ms; Pluto 322-393 ms; gen-real.xml 229 ms | wall 2.79 / 2.78 s, 2672 / 2663 ms, maxrss 52-60 MB, `epg-now.json` 908,939 B (5,840 channels), `epg-window.txt` 3,189,425 B; `--now-only` 35 ms; Pluto 317 / 319 ms (0 matches, warnings as before); gen-real.xml 238 ms | same wrapper, `--force` |
| PERF-05 | informational | 305 MB after the 11k load, 383 after 20 opens, 438 before / 381 after 20 more | 332 MB after the 11k load, 322 after 8 opens, 325 after 20, 323 after 40 (no growth); 553 MB after the 50k load (new) | `ps -o rss= -p <harness pid>` |
| PERF-06 | zap < 2 s | local: window 594 / 673 ms, `time-pos` 1.9 s one second later; ABC News Live 523 ms | local: window 436 / 437 / 457 ms after the last key, `time-pos` 0.6-2.0 s one second later; after the hung-mpv sequence 426 ms; no network channel played this pass | keys + `hyprctl clients -j` poll every 50 ms + `bin/mpvq.py` |
| PERF-07 | no stall | pass | pass: `abc news` typed during the 11k refresh (17 matches while `Refreshing...`), `sky sports` during the 41 MB EPG parse | as before |

## R5. Privacy sweep re-run (SEC-07, TC-CFG-13)

run7, `qa-attrs.m3u`, Space on `Channel 11` (`u:46b30f8f`, credentialed URL, DNS failure). Hits for `user:` / `secret` / `stream.example.test/` / `/live/`: harness console 0, `notifications.log` 0 (body `"Channel 11" did not play - Failed to open stream.example.test`), service IPC `status` 0 (`nowPlaying`, `lastError` host only; run8 dump), harness state dump 0, widget JSON 0, `state.json` 0 (`recents: [{id: u:46b30f8f, name: Channel 11}]`), `playlist-status.json` 0, `channels.json` 1 (by design). Screenshot `shots/run7-failed-card.png`. Verdict: pass, unchanged.

## R6. New defects (rows in docs/STATUS.md)

### D-LIVE-16  P3  found 2026-09-13 at 2ce0b52 - browse / Guide.qml group column position on reopen

Steps: 1. `h.sh --open --playlist downloads/index.m3u` (30 groups; `gen-500.m3u` with 20 groups reproduces too: the column must be taller than the card body). 2. Look at the column: correct, `Favorites` then `All` at the top (`shots/run1-open.png`). 3. Esc (or `ipc close`), then reopen with `ipc toggle` / `ipc open '{}'` while Favorites is empty (the guide lands on All).

Expected: UX 2.2 order with Recent/Favorites/All at the top; the column should open scrolled to the top, i.e. to the selected scope (All is the second entry).

Actual: the column starts at `All`; `Favorites` sits above the viewport and is invisible until the user presses Left/h (`shots/run1-reopen.png`, `run1-reopen2.png`, `run1-now.png`, `run2-reopen.png`). Every reopen that lands on All reproduces; a reopen that lands on Favorites (favorites non-empty) is correct (`run1-reopen-fav.png`); a column that fits the card (qa-groups, 8 groups) is correct (`run3-reopen.png`). Confirms the fix-round dev's observation. Severity P3 (PLAN 6: cosmetic; Favorites is one keypress away and no story is blocked), though it hides the entry that teaches `f`. Likely cause: `rebuildDisplay` positions the column with `groupList.positionViewAtIndex(at, ListView.Contain)` inside `Qt.callLater` (`Guide.qml:359-361`) before the column has its final height on reopen, so `Contain` for index 1 scrolls it to the top edge; FE to confirm.

### D-LIVE-17  P3  found 2026-09-13 at 2ce0b52 - playback / Service.qml stop and health paths never escalate past SIGTERM (intermittent trigger)

Steps (as observed, run5b, `--serve` with `fixtures/sec.m3u`): 1. Fresh launch A (Enter), `ipc stop`, wait 0.4 s; fresh launch E, stop, 0.4 s; fresh launch B. 2. The third mpv (pid 1343432) mapped its window in 457 ms but never answered on the IPC socket (`bin/mpvq.py` -> `timed out`, helper calls -> `mpv did not answer`). 3. `ipc stop`, then `s` in list mode.

Expected: TC-PLAY-06 `s`: mpv gone within a second, footer `Stopped`; ARCH: one player, the service always able to end it.

Actual: the process stayed alive for ~2 minutes across `ipc stop`, `s`, ~10 plays and zaps; `stopFallbackTimer` and the health check send only `signal(15)` (`Service.qml:421`, `:787`) and a wedged mpv ignores SIGTERM; the health timer skipped every poll because a control call (2 s deadline, retried with backoff per D-LIVE-15) was always in flight, so no `mpv unresponsive` line appeared in that phase; `nowPlaying`/bar tooltip moved to A, C, E while the window stayed on `Harness Live B` (`logs/run5b.log` lines 21-34: three `play failed: mpv did not answer`). It ended only after an external `kill -STOP` / `kill -CONT` (D-LIVE-15 step) let the pending SIGTERM through. Not reproduced on demand: 8 consecutive launch/stop cycles with the same timing (run5c: IPC answered every time, stops 230-263 ms) and the 16 launches of runs 5, 8 and 9 were clean; the same no-SIGKILL gap is deterministic for a `SIGSTOP`ped mpv (TC-PLAY-09: two SIGTERMs, never reaped until CONT). Root cause of the wedge unknown (first-launch IPC never came up). Suggested fix: escalate to `signal(9)` a few seconds after an ignored SIGTERM in both paths and do not let in-flight control calls starve the health timer indefinitely. Route: M1.1-08 dead-stream hardening. Evidence: `logs/run5b-cmd.log`, `logs/run5b.log`, `logs/run5c-cmd.log`.

### D-LIVE-18  P3  found 2026-09-13 at 76ad317 - docs / README Limits vs Guide.qml (helper warnings never rendered)

Steps: run6, `h.sh --open --playlist gen/gen-50500.m3u`; wait for the load; read the guide.

Expected: README Limits (76ad317): `extra channels are skipped and extra groups fold into Ungrouped, with a warning in the guide`.

Actual: `playlist-status.json` carries `warnings: ["truncated to 50000 channels (500 entries skipped)", "group count capped at 2000; 2091 channels listed under Ungrouped"]` but the guide shows `bannerKind none`, footer `50,000 channels - updated 01:53`, no warning text anywhere in the guide or service state (`shots/run6-open.png`); `Guide.qml`/`Service.qml` never read `warnings` (only `Model.js:848` normalises the field). Either render the helper warnings (banner or footer, also useful for the existing `dropped header` / `no EPG channel id matches` warnings) or reword the README sentence. Docs-only fix acceptable for v0.1.0.

## R7. Updated counts (174 cases)

| Category | Cases | pass | fail | blocked | not run |
|---|---|---|---|---|---|
| INST | 10 | 3 | 0 | 7 | 0 |
| CFG | 13 | 13 | 0 | 0 | 0 |
| BRW | 25 | 19 | 0 | 2 | 4 |
| PLAY | 14 | 11 | 0 | 1 | 2 |
| BAR | 12 | 8 | 0 | 0 | 4 |
| FAV | 11 | 10 | 0 | 0 | 1 |
| EPG | 12 | 12 | 0 | 0 | 0 |
| RFR | 10 | 9 | 0 | 0 | 1 |
| UI | 14 | 13 | 0 | 1 | 0 |
| A11Y | 6 | 5 | 0 | 1 | 0 |
| PARSE | 11 | 11 | 0 | 0 | 0 |
| MODEL | 8 | 7 | 0 | 0 | 1 |
| SEC | 21 | 19 | 0 | 0 | 2 |
| PERF | 7 | 7 | 0 | 0 | 0 |
| **Total** | **174** | **148** | **0** | **12** | **14** |

Changes against section 2: TC-CFG-06, TC-BRW-21, TC-FAV-08, TC-EPG-04, TC-RFR-01, TC-RFR-09 and SEC-14 fail -> pass; SEC-20 not run -> pass (S-06 mock). Open defects: 0 P1, 0 P2, 3 P3 (D-LIVE-16, 17, 18). D-LIVE-16 is reported through TC-BRW-05/06 (their own expectations still hold); D-LIVE-17 through TC-PLAY-06 (the deterministic re-run passes, the one intermittent instance is recorded above); D-LIVE-18 has no test-case row (README sentence added in 76ad317).

## R8. Still blocked: needs live shell

Unchanged from section 7: TC-INST-02/03/04 (journal)/05/06/08/09/10, TC-CFG-01 (`omarchy bar set` -> `shell.barConfig`), TC-CFG-07 (timer re-arm), TC-BRW-01, TC-BRW-04, TC-PLAY-11, TC-UI-05, TC-A11Y-04 (second monitor); the mouse cases TC-BRW-02/19/23, TC-BAR-06/07/08, TC-FAV-11 and the click part of TC-A11Y-03 need a hand on the mouse; TC-BRW-24 needs `hyprctl keyword monitor`. The command list in section 7 still applies; the D-LIVE-02 remark in it is obsolete (the EPG now loads on the first `omarchy bar set ... epgUrl`).

## R9. Release recommendation

All 23 fixes verified, no regression in a 137-case sample, gates green, 0 open P1/P2. The three new P3s are cosmetic (D-LIVE-16), an intermittent hardening gap already routed to M1.1-08 (D-LIVE-17) and a one-sentence README mismatch (D-LIVE-18; fix before tagging). QA verdict for a v0.1.0 release candidate: go, as an RC. The final v0.1.0 tag should wait for the live-shell block in R8 (G2/QB3: install, enable, keybinding, menu row, theme switch, `omarchy bar set` propagation, restart semantics), which needs the lead's or the user's desktop; the harness pass gives no evidence for those host integrations.

## Live-shell verification on the reference machine (2026-09-13, build e418a99 / v0.1.0-rc1)

Performed by the product owner with the user's explicit permission, on the
user's running Omarchy 4.0.3 shell (theme Retropc, single 1366x768 output).
Backups of `shell.json`, `bindings.lua`, and `omarchy-menu.jsonc` were taken
to the session scratchpad before any change.

| Case | Result | Evidence |
|---|---|---|
| INST: clone into `~/.config/omarchy/plugins/io.github.rmcdavid.iptv`, no symlinks, `omarchy plugin validate` | pass | validate exit 0; clone on branch main at e418a99 |
| INST: `omarchy-shell shell rescanPlugins` + `omarchy plugin enable` | pass | `plugin list --json` shows enabled, kinds bar-widget/overlay/service; entry added to shell.json right section |
| CFG: `omarchy bar set ... playlistUrl` (iptv-org US) propagates via shell.barConfig | pass | helper ran without a widget restart; status ready, 1,475 channels, 28 groups at 13:42 |
| CFG: cache and state files | pass | `~/.cache/omarchy-iptv/*` and `state.json` mode 0600 in 0700 dirs |
| BRW: guide opens via `omarchy-shell shell toggle`, renders group column, counts, footer hints | pass | guide-open.png |
| BRW: search `cnn` (no match), `Esc` clears, `Esc` closes | pass | guide-search.png (`No matches for "cnn"`), guide-closed.png |
| PLAY: IPC `play` on a dead stream | pass | mpv exited, no window left, `lastError` = `No video or audio streams selected.` (no URL), channel added to Recent |
| PLAY: IPC `play` on a live stream (Bloomberg Originals) | pass | `hyprctl clients` shows class `omarchy-iptv`, title = channel name; status playing with nowPlaying.launchedFrom `g:Business`; bar shows playing glyph + elided name (playing.png) |
| PLAY: IPC `stop` | pass | window gone within 3 s, playing false, no mpv process |
| BAR: widget renders in the right section, glyph only while idle | pass | bar.png |
| INST: keybinding line from contrib/bindings.lua appended to bindings.lua | pass | `hyprctl configerrors` empty; `omarchy menu keybindings --print` lists `SUPER SHIFT + T -> IPTV`; `hyprctl binds -j` shows modmask 65 key T. Not test-fired by automation (the user pressed it) |
| INST: menu row from contrib/omarchy-menu.jsonc inserted | pass | file parses after comment stripping; key `iptv` present |
| UI: theme switch with the guide open (`omarchy theme set nord`) | pass | overlay re-skinned live without restart (theme-nord.png); reopen consistent (theme-nord-reopen.png); Retropc restored |
| INST: `omarchy restart shell` | pass | shell ping ok; plugin enabled; status ready with a fresh fetch at 14:21; guide opens (after-restart.png); no plugin errors in the log |
| Shell log | pass | only pre-existing MPRIS/dbus warnings from omarchy.media about an unrelated mpv; nothing from io.github.rmcdavid.iptv |

Still not exercised on the live shell: multi-monitor placement (single output),
mouse gestures on the bar widget (verified via IPC equivalents in the
harness), `omarchy plugin update` round trip, third-party replacement bar.

End state left on the machine: plugin installed and enabled, playlistUrl set
to the iptv-org US list, `SUPER + SHIFT + T` bound, `iptv` menu row present,
theme Retropc. Undo: `omarchy plugin remove io.github.rmcdavid.iptv`, delete
the two appended lines, `rm -rf ~/.cache/omarchy-iptv ~/.local/state/omarchy-iptv`.

## Release regression on 502f4b3 (QA, 2026-09-13, 14:48 - 15:15)

Final pre-release regression on main after the M1.1-08 merge (D-LIVE-16 column position, D-LIVE-17 stop escalation, D-LIVE-18 playlist warnings). Same conventions as the sections above (` - ` for U+00B7, `...` for U+2026, `run<N>` = `logs/run<N>.log`).

| Item | Value |
|---|---|
| Code under test | `502f4b3` (merge of 3928e82, 4537384, 4b5e0d3 on 0c4afa8). HEAD moved to `73b700d` (docs: README and changelog for 0.1.0) at 14:49:06, during setup and before the first harness run; `git diff --stat 502f4b3..73b700d` lists CHANGELOG.md and README.md only and `git diff 502f4b3..HEAD -- bin Model.js Service.qml Guide.qml BarWidget.qml manifest.json scripts tests` is empty, so every run exercised 502f4b3 code. The merge itself changed Guide.qml, Model.js, Service.qml, the harness shell.qml and the tests; `bin/omarchy-iptv`, BarWidget.qml and manifest.json are byte-identical to 2ce0b52 |
| Gates | `omarchy plugin validate .` exit 0, no output; `scripts/check.sh` all green in 21.6 s (299 node checks, 144 python tests, 21 qml spec cases, ascii ok) - tails in RR1 |
| Mode | dev harness only (`scripts/dev-harness/run.sh` under `OMARCHY_IPTV_HARNESS_DIR=/tmp/claude-1000/omarchy-iptv-qa3/harness`, wrapper `h.sh`, notification shim, `start.sh`/`stop.sh` by PID as in the previous pass). The installed plugin in `~/.config/omarchy/plugins` and the live shell (quickshell pid 214634) were not touched: `find ~/.config/omarchy/plugins/io.github.rmcdavid.iptv ~/.config/omarchy/shell.json ~/.local/state/omarchy-iptv ~/.cache/omarchy-iptv -newermt '2026-09-13 14:48'` is empty; no `omarchy plugin/bar/theme` state command, no sudo |
| Machine | unchanged: Omarchy 4.0.3, Quickshell 0.3.1, Hyprland 0.56.2, mpv 0.41.0, Python 3.14.7, node 26.8.1, one output eDP-1 1366x768, theme retropc |
| Sources | generated `gen-45g.m3u` (900 channels / 45 groups, `--seed 16 --epg-ids 0.5`, helper reports 45 groups; multi-group strings list under their first group) and `gen-50500-2100g.m3u` (50,500 entries / 2,100 base groups, 7,084 distinct group-title strings, `--seed 18`, sha256 `bbd71aee...2a2b3d4`), `index.m3u` (11,041), `us.m3u`, `gen-10k.m3u` + `gen-10k.xml.gz`, `gen-real`, `gen-500` pair regenerated at 15:11 with `--hours 24` (the 09-12 copy had aged out of its window: `epg-now.json` 125 B), `fixtures/sec.m3u` with `--serve`, `tests/fixtures/qa-*`, Pluto `us.xml.gz`; local HTTP on 127.0.0.1:8766 (own `python3 -m http.server`, killed by PID) |
| Evidence | `/tmp/claude-1000/omarchy-iptv-qa3/`: `logs/run*.log` + `run*-cmd.log` (command transcripts), `logs/check.log`, `perf-cli.log`, `perf03-node.log`, `notifications.log`, `run7-*.json` privacy sinks; `shots/` 61 grim screenshots and `shots/crops/` 60 crops/montages inspected with the Read tool; `bin/run*.sh` reproduce every run |

### RR1. Gates

`omarchy plugin validate .` -> exit 0, no output. `scripts/check.sh` tail:

```
== omarchy plugin validate /home/ricky/Projects/omarchy-iptv
ok   manifest valid
== qmllint (imports: /tmp/qmlroot, /usr/lib/qt6/qml)
ok   BarWidget.qml: 0 errors, 14 warning(s)
ok   Guide.qml: 0 errors, 95 warning(s)
ok   Service.qml: 0 errors, 0 warning(s)
ok   Model.spec.qml: 0 errors, 0 warning(s)
...
299 checks, 0 failure(s)
All Model.js tests passed.
ok   node tests
== python3 -m unittest discover -s tests
Ran 144 tests in 19.662s
OK
ok   python tests
== qmltestrunner tests/Model.spec.qml
ok   qml spec (21 passed)
== ascii check (code files)
ok   ascii check
check.sh: all green
real    0m21.647s
```

qmllint categories (TC-UI-13, D-LIVE-14): `Service.qml` 0; `Guide.qml` 95 = 43 `missing-property` + 51 `unqualified` + 1 `uncreatable-type` (PanelWindow); `BarWidget.qml` 14 `missing-property`; 0 errors, 0 `signal-handler-parameters`. Identical to the 2ce0b52 baseline (57 / 51 / 1). Node checks 271 -> 299 and qml spec 18 -> 21 are the merge's new cases (`columnAnchor`, `statusWarnings`, `warningLine`, `stopEscalation`, `healthTick`).

### RR2. Defect verification

| Defect | Result | Repro re-run and evidence |
|---|---|---|
| D-LIVE-16 (P3) | verified fixed | run1/run1b `gen-45g.m3u` (48 column entries with Favorites, All and the GROUPS header; 49 with Recent; the column is ~2.5 cards tall) and run3 `index.m3u` (30 groups). First open lands on All with `Favorites` visible above it (`shots/run1-open.png`). Reopen while All is selected, by `ipc close` + `open '{}'` and by Esc + `toggle`: column at the top, Favorites visible, All highlighted (`run1-reopen.png`, `run1-reopen-kbd.png`); the same after 10 consecutive toggle cycles (`run1b-reopen-10.png`). h/l: Left from All -> Favorites (top), Left again wraps to `Group 044 World` shown at the bottom edge of a scrolled column (`run1b-h-wrap-last.png`), Right wraps to Favorites with the column back at the top (`run1b-l-wrap-fav.png`), Right -> All (`run1b-l-all.png`); 30 x Right from the first group brings `Group 019 Sports` into view at the bottom edge (`run1-l30.png`), 30 x Left back to `Group 020 Max` with the column at the top (`run1-h30-back.png`). Deep group: `Group 036 Auto` (entry 38) selected and in view (`run1-deep.png`), close, reopen -> All, column at the top with Favorites visible, both via IPC and via Esc + toggle (`run1-reopen-after-deep.png`, `run1-reopen-after-deep-kbd.png`). With one favorite the reopen lands on Favorites at the top (`run1-reopen-fav.png`, `run1-reopen-fav-kbd.png`); with Recent present the column shows Recent, Favorites, All from the top (`run1-reopen-recent.png`). index.m3u: Left x3 from Movies -> All -> Favorites -> `Interactive` (last group, in view at the bottom, `run3-last-group.png`), close, reopen -> All at the top with Favorites visible (`run3-reopen.png`). Column that fits (qa-groups, 8 groups): unchanged (`run6-open.png`). No console output from the new `onHeightChanged` paths |
| D-LIVE-17 (P3) | verified fixed | run4 (`--serve`, `sec.m3u`, service IPC `stop`/`play`). Baseline with a responsive player: `stop` -> mpv gone 261 / 219 / 238 ms, `stopStage` back to `""`, no SIGKILL line. (A) `Harness Live A` playing (pid 373406), `kill -STOP`, `stop` over the service IPC returned in 47 ms; immediately `status` -> `playing false, nowPlaying null`, harness `stopStage quit`, bar idle glyph; stage `term` at +2.45 s; process gone at +4.17 s (state `T` until then); console `omarchy-iptv: mpv ignored SIGTERM, sending SIGKILL`; count 0, stage `""`. (B) health path: A (pid 374124) SIGSTOPped, no stop: `mpv unresponsive, restarting player` at +21.2 s (two failed 2 s probes on the 10 s timer), stage `term`, SIGKILL line at +23.2 s, old pid gone, relaunch window pid 375996 mapped 211 ms after the exit (+23.5 s), IPC answers (`time-pos 1.9`, media-title A), `nowPlaying` A, bar playing, 0 `play failed`. (C) play during the ladder: the relaunched A SIGSTOPped, `stop`, +0.3 s `play t:live.b` -> `ok` with `nowPlaying` B and stage `quit`; B window pid 376778 at +4.64 s after the old pid was SIGKILLed, `time-pos 1.98`, title B, 0 `play failed`. (D) play during a normal shutdown: `stop` + `play t:live.a` back to back -> new pid 377054, window at +1.01 s, A playing, 0 `play failed`, no SIGKILL. (E) a second `stop` during the ladder cancels the queued play: gone 3.39 s after the second stop, count 0, `nowPlaying null`, no window. D-LIVE-15 tail: keyboard play of B afterwards -> window 384 ms, `play failed` 0, `did not answer` 0 in the whole run. Console for the run: exactly 4 SIGKILL lines (one per SIGSTOPped player) and 1 `mpv unresponsive` line; `stop.sh` leftovers none; `healthSkips` stayed 0 (the skip path needs a call in flight at three consecutive ticks and did not trigger; covered by 299 node checks incl. `healthTick`) |
| D-LIVE-18 (P3) | verified fixed | run2 `http://127.0.0.1:8766/gen-50500-2100g.m3u`: loaded at +6.3 s with footer `Playlist warning: truncated to 50000 channels (500 entries skipped) (+1 more)` (`shots/run2-warning.png`, crop `crops/m5.png`), state `warning` identical, service `warnings` = [`truncated to 50000 channels (500 entries skipped)`, `group count capped at 2000; 2026 channels listed under Ungrouped`], IPC `status` verb carries the same `warnings` array, `playlist-status.json` the same; 0 URL-ish strings (`http`, `8766`, `/gen/`) in the whole guide + service state dump; helper CLI on the file 2,475 ms, 50,000 / 2,001, maxrss 103 MB. Priority: `a` -> `First 200 of 41,242 - keep typing` over the warning, Ctrl+U -> warning back; `r` -> `Refreshing...` +254 ms, `Refreshed - 50,000 channels` +5.1 s, warning back at +8.2 s, notification `Playlist refreshed` / `50,000 channels in 2,001 groups`. Failed refresh of the same source (server killed, `r`): banner `Playlist refresh failed (Connection refused) - showing cached copy from 14:56 - r retry`, status `cached`, warnings kept (`run2-refresh-failed.png`). Clean load (`qa-groups.m3u`): footer `10 channels - updated 14:57`, `warning ""`, status `warnings []` (`run2-clean.png`); back to the big list over `file://` -> warning returns (+5.3 s); End -> 49,999, column tail `Ungrouped=2026` last. A real fixture warning renders too: `qa-attrs.m3u` -> `Playlist warning: 1 #EXTINF entries without a URL skipped` (run6, run7, `run7-failed-card.png`), URL-free. Redaction unit check: `Model.statusWarnings` turns `dropped header from http://user:pw@prov.example.test/live/x.m3u8?token=abc` into `dropped header from prov.example.test`; `warningLine([])` is `""`; a failed status yields `[]`. README Limits sentence now true |

Verification counts: 3 verified fixed, 0 still open, 0 reopened.

### RR3. Regression sample

120 cases re-run with the previous methods (harness IPC + wtype keys + grim, helper CLI wrapper, node micro-benchmark, static greps). No regression: every case that passed on 2ce0b52 passes on 502f4b3. Cases not listed keep their previous result.

| Category | Re-run | Result | Notes |
|---|---|---|---|
| INST | 01, 04, 07 | pass | gates (RR1); every harness console carries only the portal WARN, the intentional helper-stderr relays (host only), `ignoring mpvArgs tokens`, and the new ladder lines `mpv unresponsive, restarting player` (1) / `mpv ignored SIGTERM, sending SIGKILL` (4, each an intentional SIGSTOP); `find . -newermt '2026-09-13 14:49:07'` inside the plugin dir (after the 73b700d checkout) lists nothing |
| CFG | 02, 04, 05, 06, 08, 12, 13 | pass | `HTTP 404 Not Found` (with a cache: banner + `10 channels - cached 15:08 - offline`, run6), `Unsupported URL` for `ftp://`, absolute paths and `file://` sources (runs 1, 2, 6, 7), CFG-06 = D-LIVE-02 (EPG helper runs 712 ms / 528 ms after `epgUrl` is set from empty, twice), mpvArgs `--profile=fast --hwdec=auto-safe` kept and `--input-ipc-server=/tmp/x --title=X --no-idle` dropped with the console line (run4b), playlistUrl/epgUrl changed with the guide open (10 -> 22 -> 10 channels, run6; 50k -> 10 -> 50k, run2), CFG-13 = RR5 |
| BRW | 05, 06, 07, 09, 10, 11, 12, 13, 14, 15, 17, 21, 22, 25 | pass | every open in search mode with an empty query; default entry All when Favorites is empty, Favorites once populated (run1); `kids` -> 1, `sky` -> 25, `4k` -> 7, `abc news` -> 17 on index; cap `a` -> 200 rows / `First 200 of 8,579 - keep typing`, End -> 199, Ctrl+U -> 11,041 (`run3-cap.png`); End -> 11040 (`run3-end.png`), Home -> 0, PgDn x3 -> 24, PgUp -> 16, Up on 0 wraps to 11040, Down on the last row wraps to 0; Right from All -> `g:Movies`, Left x3 wraps to `g:Interactive`; typing on Favorites jumps to All and Ctrl+U restores Favorites (run6); Esc clears then closes; Tab commits `spo` (3 rows, list mode), `q w 4` ignored, `/` back to search; `4k` literal in search mode; `No matches for "zzzz" in Animation` / `h/l other groups - Home for All` (`run6-nomatch-group.png`), Home in list mode jumps the column to All (run5c; search-mode Home leaves the column, as before); scopes `favorites, all, Animation, UK | SPORTS, Sports, Movies, News, Padded, Leading Semicolon, Ungrouped`; `Multi Group Channel` under Animation, found by `kids`; `ipc open '{"query":"sky"}'` prefills |
| PLAY | 01, 02, 04, 05, 06, 09, 10, 12, 14 | pass | run4/run4b: fresh launches window 803 (cold, first of the run) / 378 / 387 / 438 ms after the keys, class `omarchy-iptv`, one mpv, `--ytdl=no`, `--` then the URL last, mpv focused after Enter (`active omarchy-iptv`); `play t:s01b` over the socket reuses the pid; Space keeps the guide open with the row marker and footer `U+25B6 Harness Live B - s stop` (`run4-space-cues.png`); dead channel: `Stream failed` / `"u critical" did not play - Failed to open 127.0.0.1` with U+201C/U+201D, row `Failed 14:59 - Space to retry` (`run4-failed-row.png`), Recent gains it, bar idle; `s`: gone 253 ms, footer `Stopped`, 0 notifications; PLAY-09 = D-LIVE-17 B; three Space presses within ~1.5 s end on the third row with one mpv; PLAY-12 = PERF-06; `f` in mpv -> Hyprland `fullscreen 2`, guide layer above it (`run4b-over-fullscreen.png`), after Esc mpv focused, still fullscreen, `pause false`, `mute false`, `time-pos 4.9 -> 7.0` |
| BAR | 01, 02, 03, 04, 05, 09 | pass | idle `{U+F0502, "", IPTV - click to open the guide}`; `IPTV - no playlist configured`; playing `{U+F0567, Harness Live B, Playing Harness Live B}` width 136; error `{U+F0503, IPTV - playlist error, open the guide}` (run5d); refreshing `IPTV - refreshing playlist...` (run5e); ring via `service.zap`: Favorites A <-> E with wrap, group Local C -> B -> A (run4) |
| FAV | 01, 02, 03, 04, 05, 06, 07, 08 | pass | `Added to Favorites` / `Removed from Favorites`; `No favorites yet` (`run6-fav-empty.png`); order = favorited order (`t:grp1.test, t:multi.test, t:pipe.test`), Favorites first after Recent; `f` at index 1 inside Favorites keeps cursor 1; FAV-05 = D-LIVE-07 (`x` on the only Recent -> `Removed from Recent`, scope falls back to Favorites, entry gone, `run6-recent-removed.png`); replay moves B to the top of Recent (run4); dead channel recorded in Recent (run6, run7); `state.json` 600 in a 700 dir (persistence across restart not re-run) |
| EPG | 01, 02, 03, 04, 05-11, 12 | pass | guide usable before the EPG loads (rows without detail, then detail); run5c with the regenerated `gen-500.xml`: `epg-now.json` 47,713 B, 306 channels with now and next, row `Group 017 Sports - Now: Tonight Evening - Next: Evening Weekend`, `until 17:00`, hairline (`crops/m12.png`); rows without a tvg-id show the group only; EPG-04 = D-LIVE-08 (`Guide data unavailable (HTTP 404 Not Found) - channels still work - r retry`, notification `Could not fetch the EPG (HTTP 404 Not Found). Channels still work.` low, rows keep the window, banner survives `r`, clears after the good URL is restored, `run5-epg-404.png`); 05-11 `tests/test_epg.py` via check.sh; `sky sports` typed during the gen-10k.xml.gz parse (8 matches), EPG loaded 2.63 s after `ipc set epgUrl` |
| RFR | 01, 03, 04, 05, 06, 07, 08, 09 | pass | RFR-01 = D-LIVE-05 (`Refreshing...` +99 ms, `Refreshed - 500 channels` +609 ms, `500 channels - updated 15:08` +3.6 s, notification `Playlist refreshed` / `500 channels in 20 groups`); server down + `r`: banner `Playlist refresh failed (Connection refused) - showing cached copy from 15:08 - r retry`, notification `Could not fetch the playlist (Connection refused). Using cached copy from 15:11.`, footer `500 channels - cached 15:08 - offline` (`run5-banner.png`); `r` twice within 100 ms -> one notification; refresh while B plays: same pid, `time-pos 3.2 -> 6.5`; `--keep` restart with the server down: 500 cached rows at +2.1 s with the banner and the offline footer, status `cached` (`run5b-cached-start.png`); list changes with the guide open (run2, run6); `Playlist has no channels`; `Not an M3U playlist` (`run6-notm3u.png`) |
| UI | 01, 02, 03, 04, 06, 07, 09, 10, 11, 13, 14 | pass | the fresh unconfigured start (previous pass, `qa2/shots/run4-unconfigured.png`) was not re-run; this pass: unconfigured tooltip + `r` -> `Set a playlist first` with no helper spawned (D-LIVE-09); loading with no cache `Loading playlist...` / `Fetching from 10.255.255.1`, hint `Esc close` (`run5e-loading.png`, D-LIVE-10) then `Playlist failed to load` / `Timed out from 10.255.255.1 - check playlistUrl` at +21.1 s with `r reload - Esc close` (`run5d-timeout.png`, D-LIVE-11) and notification `... (Timed out). Open the guide for details.`; banners in `crops/m8.png`; now-playing cues; no hex/white/black/`Qt.rgba(` in `*.qml`; all 21 `font.family` bind the host font; hints verbatim per mode (`crops/m7.png`: `Enter play - Up/Down move - Left/Right group - Tab keys - Esc close`, `... Left/Right narrow ... Esc clear`, `j/k move - h/l group - Enter play - Space preview - f favorite - s stop - r refresh - / search`, `r reload - Esc close`); labels `All - 11,041 channels`, `in All - 8,579 matches`, `Favorites - 0 channels`, `Interactive - 1 channel`, `Movies - 714 channels`; glyphs rendered; qmllint per RR1; card 960x620 centred (every crop at +203+74 lines up) |
| A11Y | 05, 06 | pass | derived from PLAY-01/14 (run4b) and PERF-02/03 |
| PARSE | 01-11 | pass | `tests/test_playlist.py` via check.sh; helper byte-identical to 2ce0b52; CLI `/proc/self/environ` -> `unsafe_path`, `ftp://` -> `unsupported_scheme` |
| MODEL | 01-07 | pass | 299 node checks, 21 QML spec cases |
| SEC | 01, 02, 04, 05, 06, 07, 08, 12, 13, 14, 15, 16, 17, 18, 21 | pass | greps for `bash -c`/`sh -c`, sudo, `shell=True`, `os.system`, XMLHttpRequest/eval all 0; S-04 quoted name; scheme allow-lists; argv tail `--hwdec=auto-safe -- http://127.0.0.1:8765`; RR5 privacy; local path rules; source schemes; mpvArgs; modes `700` cache/state/runtime dirs, `600` `channels.json` / `playlist-status.json` / `state.json` / `mpv.sock` (owner ricky), 0 symlinks; no writes in the plugin dir; service IPC `play` with `http://evil.example.test/x`, `u:deadbeef`, `file:///etc/passwd`, `-- --script=/tmp/x` -> `unknown`, nothing launched; `channels.json` holds the URL by design (1 hit) |
| PERF | 01-07 | pass | section RR4 |

Not re-run this pass (previous result kept): TC-CFG-03/07/09/10/11, TC-BRW-08/16/18/20, TC-PLAY-03/07/08/13, TC-BAR-10/11, TC-FAV-09/10, TC-RFR-02/10, TC-UI-08/12, TC-A11Y-01/02, SEC-03/09/10/11/19/20 (S-05 trickle and S-06 redirect mocks: helper unchanged), TC-MODEL-08, plus the mouse and live-shell cases listed in R8 (the live-shell block passed in the live section above). **(2026-09-15: the kept result for TC-A11Y-01 and TC-BAR-11 is retracted -- it was a grep over source written to satisfy it. See "Accessibility harness runs" at the end of this file.)**

### RR4. Performance, 2ce0b52 vs 502f4b3

| ID | Budget | 2ce0b52 (previous) | 502f4b3 (now) | Method (unchanged) |
|---|---|---|---|---|
| PERF-01 | `playlist` < 1 s | gen-10k 484 / 475 ms (wall 0.60 s); index 552 / 548 ms (wall 0.67 s); us 74 / 71 ms; maxrss 25-51 MB | gen-10k 488 / 473 ms (wall 0.61 / 0.59 s); index 542 / 536 ms (wall 0.66 s); us 71 / 73 ms; gen-real 77 / 73 ms; maxrss 23-51 MB; `channels.json` 2,610,946 / 3,209,652 B unchanged; the 50,500-entry file 2,475 ms, maxrss 103 MB | `bin/timeit.py` wrapper, two runs each, `durationMs` from the JSON |
| PERF-02 | open < 150 ms with the 10k cache | IPC 65 / 72 / 67 / 69 / 75 ms (median 69) minus baseline 52-58 = ~12-17 ms; layer map 75 / 81 / 99 ms; 50k cache IPC 97-139 ms, layer 120 / 120 / 153 ms | IPC 75 / 65 / 64 / 65 / 72 ms (median 65) minus baseline 52-54 = ~11-13 ms; layer map 79 / 73 / 81 ms; 50k cache IPC 154 / 154 / 152 / 181 / 118 ms minus 53 = ~65-128 ms, layer 135 / 145 / 158 ms (informational, above the previous 50k sample by 15-40 ms; the budget applies to the 10k cache) | `date +%s%N` around `h.sh ipc toggle`; `hyprctl layers -j` poll for the `omarchy-iptv` namespace |
| PERF-03 | keystroke < 30 ms, no drops | 38 keys in order, settled 95 ms after the last key; single key 126 ms incl. spawn; filter `a` 6.55 ms, `news` 2.15, `alpha news` 1.80, `zz` 1.50, `abc news live` 1.76, empty 0.00; groupChannels 4.77 ms; prepareChannels 37 ms | 38 keys typed in 602 ms, all present and in order, settled 85 ms after the last key (first poll); single key 120 / 122 ms incl. spawn (of which ~100 ms is the `ipc state` read); filter `a` 6.84 ms (best 5.57), `news` 2.30, `alpha news` 1.72, `zz` 1.43, `abc news live` 1.72, empty 0.00 (same array); groupChannels 4.70 ms; prepareChannels 35.3 ms | `wtype -d 20` x18 + `-d 1` x20; node 50 iterations on `cache-perf/index/channels.json` |
| PERF-04 | `epg` < 4 s, RSS < 300 MB | gen-10k.xml.gz wall 2.79 / 2.78 s, 2672 / 2663 ms, maxrss 52-60 MB, `epg-now.json` 908,939 B (5,840 channels), `epg-window.txt` 3,189,425 B; `--now-only` 35 ms; Pluto 317 / 319 ms; gen-real.xml 238 ms | wall 2.59 / 2.63 s, 2457 / 2507 ms, maxrss 50-53 MB, `epg-now.json` 909,124 B (5,840 channels), `epg-window.txt` 2,275,234 B with 57,844 programmes (the 09-12 file's window has aged 15 h, so fewer programmes fall inside it: data drift, not code); `--now-only` 35 ms (wall 0.15 s); Pluto 362 / 374 ms (0 matches, warnings as before); gen-real.xml 169 ms; in the harness the same gz loaded 2.63 s after `ipc set epgUrl` while typing | same wrapper, `--force` |
| PERF-05 | informational | 332 MB after the 11k load, 322 after 8 opens, 325 after 20, 323 after 40; 553 MB after the 50k load | 326 MB after the 11k load, 316 after 8 opens, 312 after 20, 313 after 40 (no growth); 559 MB after the 50k load, 711 MB at the end of run2 after two 50k loads, a 10-channel load and 16 more opens | `ps -o rss= -p <harness pid>` |
| PERF-06 | zap < 2 s | local: window 436 / 437 / 457 ms after the last key, `time-pos` 0.6-2.0 s one second later; after the hung-mpv sequence 426 ms | local: window 803 (cold first launch of the run) / 378 / 387 / 438 ms after the last key, `time-pos` 0.5-2.0 s one second later; after the hung-mpv sequences 384 ms; relaunch after the health-check kill 211 ms; play issued during a normal shutdown: new window 1.01 s after `stop` + `play`; no network channel played this pass | keys + `hyprctl clients -j` poll every 50 ms + `bin/mpvq.py` |
| PERF-07 | no stall | pass | pass: `abc news` typed during the 11k refresh (17 matches while it ran), `sky sports` (8 matches) during the gen-10k.xml.gz parse | as before |

### RR5. Privacy sweep re-run (SEC-07, TC-CFG-13)

run7, `qa-attrs.m3u`, Space on `Channel 11` (`u:46b30f8f`, credentialed URL, DNS failure). Hits for `user:` / `secret` / `stream.example.test/` / `/live/`: harness console 0, `notifications.log` 0 (`"Channel 11" did not play - Failed to open stream.example.test`), service IPC `status` 0 (`nowPlaying null`, `lastError` host only, `warnings` [`1 #EXTINF entries without a URL skipped`]), harness state dump 0, widget JSON 0, `state.json` 0 (`recents: [{id: u:46b30f8f, name: Channel 11}]`), `playlist-status.json` 0, `channels.json` 1 (by design). The D-LIVE-18 footer line is URL-free on this fixture (`shots/run7-failed-card.png`). Verdict: pass, unchanged.

### RR6. New defect (row in docs/STATUS.md)

#### D-LIVE-19  P3  found 2026-09-13 at 502f4b3 - states / Guide.qml `emptyKind` vs `hasChannels` when `playlistUrl` is cleared at runtime (pre-existing: identical on 2ce0b52)

Steps: 1. `h.sh --open --playlist tests/fixtures/qa-groups.m3u` (10 channels loaded). 2. `h.sh ipc set playlistUrl ''` (the `omarchy bar set io.github.rmcdavid.iptv playlistUrl ""` path through `shell.barConfig`). 3. Look at the card; close and reopen.

Expected: UX 4.4 / 6.3 `No playlist configured` empty state replacing the body (column hidden, list empty, footer blank, hint `r reload - Esc close`), as it is when the guide starts unconfigured (previous pass, `qa2/shots/run4-unconfigured.png`, TC-UI-01: column hidden, list empty).

Actual: `emptyKind unconfigured`, footer blank and the hint are correct, but the service keeps its 10 channels (`configured false, status ready, channels 10`), so `hasChannels` stays true: the channel list (10 rows, favorites stars) and the group column (11 entries with counts) stay rendered and the `No playlist configured` title, prose and command box are drawn over the rows (`shots/run5f-cleared.png`, `run6-unconfigured.png`); close + reopen shows the same (`run5f-cleared-reopen.png`); setting a URL again recovers (`restored: rows 10, footer 10 channels - updated 15:13`). The same steps on a detached worktree of 2ce0b52 give the identical state and screenshot (`run5f-old-cleared.png`), and the merge touches neither `emptyKind` nor `hasChannels`, so this is pre-existing, not a regression. Severity P3 (PLAN 6: cosmetic; an unusual runtime transition, `Esc` and a new URL both recover). Likely fix: clear `channels` (or treat `!configured` as no channels) in `Service.qml onPlaylistUrlChanged` when the new URL is empty, or hide the list/column while `emptyKind === "unconfigured"`.

### RR7. Observations that are not defects

- After a *failed* manual refresh the `Refreshing...` transient stays for its full 3 s window (+96 ms -> +3053 ms in run5, then `500 channels - cached 15:08 - offline`) while the banner and the notification are immediate; on success `Refreshed - N channels` replaces it (D-LIVE-05). The transient code path is not in the merge diff and UX 6.1 lists `Refreshing...` as a transient; noted for the UX owner, not filed.
- The helper's warning grammar (`1 #EXTINF entries without a URL skipped`) is now user-visible through the D-LIVE-18 footer line; helper wording unchanged since M1, cosmetic.
- `emptyKind` reads `service` for the first ~1 s after a harness start (service not settled); the real states follow (`loading` at +1.8 s in run5e). Harness timing only.
- The first fresh mpv launch of a run maps its window later (803 ms) than the following ones (378-438 ms): cold caches, same as earlier passes; the 2 s zap budget holds.
- After a Space launch (no focus call, UX 7.5) whose predecessor has already exited, Esc leaves no toplevel focused (`hyprctl activewindow` null, run4); with an Enter launch the focus returns to mpv as specified (run4b). Test-order artefact, same behaviour as the previous pass.
- The 50k-cache open numbers are 15-40 ms above the previous sample (RR4); the 10k-cache budget numbers are equal or better.
- HEAD moved to the docs-only 73b700d during setup (header); the tag should be cut on 73b700d or later.

### RR8. Console and notification hygiene

Deduplicated WARN lines across all 13 harness runs, all intentional: `could not reach 127.0.0.1: [Errno 111] Connection refused` (5), `mpv ignored SIGTERM, sending SIGKILL` (4, D-LIVE-17 SIGSTOP tests), `could not reach 10.255.255.1: timed out` (2), `ignoring mpvArgs tokens: --input-ipc-server=/tmp/x --title=X --no-idle` (2), `epg: HTTP 404 from 127.0.0.1` (2), `epg: could not reach 127.0.0.1: [Errno 111] Connection refused` (2), `unsupported source scheme 'ftp'` (1), `source from 127.0.0.1 is not an M3U playlist` (1), `no playable channels found in playlist from 127.0.0.1` (1), `HTTP 404 from 127.0.0.1` (1), `mpv unresponsive, restarting player` (1); plus Quickshell's own portal WARN once per run. No QML warning or error from `Service.qml`, `Guide.qml`, `BarWidget.qml` or `Model.js`; runs 1, 1b and 3 (D-LIVE-16 and PERF) have no plugin output at all. Notifications observed with the fixed `-r` ids and `--app-name IPTV`: `Playlist refreshed` (74012, low), `Playlist error` (74013, normal; both bodies), `Guide data error` (74014, low), `Stream failed` (74011, normal, curly quotes). Texts match UX 6.4 verbatim.

### RR9. Cleanup

At the end of the pass: no harness Quickshell, no mpv, no fixture HTTP server (8765 / 8766), no `omarchy-iptv` window or layer left (`hyprctl clients -j` / `layers -j` 0); the 2ce0b52 worktree removed (`git worktree list` clean); `git status` shows only the two doc edits of this section and STATUS.md; the live shell (pid 214634) and the installed plugin untouched.

### RR10. Release recommendation

All three M1.1-08 fixes verified with their original repros, a 120-case regression sample with no regression, PERF-01..07 within budget and level with the previous pass, gates green (299 node, 144 python, 21 qml, validate 0), 0 open P1/P2. The one new finding, D-LIVE-19, is a pre-existing P3 in an unusual runtime transition (clearing `playlistUrl` while a list is loaded), recoverable with a new URL or a restart, and can ship as a known limitation or be fixed in M1.2. Combined with the live-shell block already verified on this machine (section above), QA verdict: go for tagging v0.1.0 (on 73b700d or later).

## M2-01 Sources pass on 7e13053 (QA, 2026-09-13, 18:44 - 19:32)

Plan of record: `docs/QA-SOURCES.md` v0.2 (196 `SRC-` cases; the `[v0.2]` expectation corrections were made during this pass against the round-2 rulings SR11-SR32). Same conventions as the sections above: ` - ` stands for U+00B7 and `...` for U+2026 in quoted microcopy, `"x"` for U+201C/U+201D; the UI renders the real codepoints (checked in the screenshots). Evidence root `E=/tmp/claude-1000/omarchy-iptv-qa4/` (`shots/` 52 grim screenshots, `logs/` one harness console per run `h<nn>.log` plus the per-scenario transcripts `h<nn>.txt`, `logs/sweep/` the privacy sinks, `gen/` the generated playlists, `cli-cache/`, `help10/`, `mig07/`, `perf-cache/`).

### S1. Header

| Item | Value |
|---|---|
| Code under test | `7e13053` (merge: M2-01 follow-ups). HEAD did not move during the pass; `git status` shows only `docs/QA-SOURCES.md` (this pass's expectation update) |
| Gates | `omarchy plugin validate .` exit 0, no output; `scripts/check.sh` all green: manifest ok, qmllint 0 errors (BarWidget 14 / Guide 197 / Service 0 warnings), `node tests/Model.test.js` 635 checks 0 failures, python 196 tests (`test_cache` 18, `test_mpv` 23, `test_playlist` 55, `test_helper` 23, `test_epg` 32, `test_state` 11, `test_source` 34) OK, `qmltestrunner tests/Model.spec.qml` 29 passed, ascii ok |
| Mode | dev harness only (`scripts/dev-harness/run.sh` under `OMARCHY_IPTV_HARNESS_DIR=$E/harness`, wrapper `h.sh`, `start.sh`/`stop.sh` by PID, notification shim `$E/bin/omarchy-notification-send` first on PATH, `OMARCHY_IPTV_DEBUG=1` for the switch timings). The installed v0.1.0 plugin, `~/.config/omarchy/shell.json`, `~/.local/state/omarchy-iptv` and `~/.cache/omarchy-iptv` were not touched (`find ... -newermt '2026-09-13 18:40'` is empty at the end); no `omarchy plugin/bar/theme` state command, no `hyprctl dispatch/reload/keyword`, no sudo. `pgrep -x hyprlock` checked before every wtype batch (never locked). Everything started was reaped: 0 harness quickshell / fixture server / helper / mpv processes at the end |
| Machine | unchanged: Omarchy 4.0.3, Quickshell 0.3.1, Hyprland 0.56.2, mpv 0.41.0, Python 3.14.7, node 26.8.1, one output eDP-1 1366x768, theme retropc |
| Sources | `tests/fixtures/qa-sources/` served from `127.0.0.1:8765` (`qa-src-a.m3u` key `584a58e5`, `qa-src-b.m3u` `733cf68c`, `qa-src-userinfo.m3u` as `http://qa-user:qa-secret@127.0.0.1:8765/...` `25b70358` and as a path, `xtream/get.php` + `xmltv.php` with `user` / `pa ss` -> `6e90a03e`, `qa-src-a.xml`, `state-v1.json` + `legacy-cache/`), `qa-empty.m3u`, `qa-not-m3u.html`, `qa-attrs.m3u` (hostile names), the harness `harness.m3u` with `--serve` (one live MPEG-TS channel), generated `gen-10k.m3u` (10,000 channels, sha256 `3d360c15...`) and `gen-real.m3u` (1,500), a silent loopback server on `127.0.0.1:8799` (accepts, never answers) for cancel and deadline cases, 50-record generated `state.json` files (typical and 2,048-character URLs) |
| Not executed | the live-shell runbook (QA-SOURCES.md section 9: install/update in place, mouse, narrow card, theme switch, SRC-MIG-10) - marked `blocked: needs live shell` |

### S2. Summary (196 cases)

| Category | Cases | pass | fail | blocked | not run |
|---|---|---|---|---|---|
| FR First run | 12 | 11 | 1 | 0 | 0 |
| LST Sources list | 12 | 11 | 0 | 1 | 0 |
| SW Switching | 10 | 9 | 1 | 0 | 0 |
| LBL Labels and editing | 9 | 9 | 0 | 0 | 0 |
| CLI parity | 8 | 5 | 3 | 0 | 0 |
| XT Xtream | 10 | 9 | 1 | 0 | 0 |
| RM Removal | 9 | 9 | 0 | 0 | 0 |
| ERR Errors | 9 | 9 | 0 | 0 | 0 |
| KEY Keyboard and mouse | 12 | 11 | 0 | 1 | 0 |
| UI States, microcopy, tokens | 20 | 17 | 1 | 1 | 1 |
| A11Y | 6 | 6 | 0 | 0 | 0 |
| PRIV Privacy rules | 9 | 9 | 0 | 0 | 0 |
| SEC Security | 24 | 23 | 1 | 0 | 0 |
| MIG Migration | 10 | 8 | 1 | 1 | 0 |
| PERF | 7 | 7 | 0 | 0 | 0 |
| MODEL Model.js | 11 | 11 | 0 | 0 | 0 |
| HELP Helper | 10 | 9 | 1 | 0 | 0 |
| SVC Service contract | 8 | 8 | 0 | 0 | 0 |
| **Total** | **196** | **181** | **10** | **4** | **1** |

Failures map to defects (section S7): SRC-FR-11 and SRC-CLI-03 -> D-SRC-03 (P2) and D-SRC-06 (P3); SRC-SW-06 -> D-SRC-04 (P2); SRC-CLI-02 and SRC-CLI-08 -> D-SRC-02 (P2); SRC-XT-02 -> D-SRC-08 (P3); SRC-UI-14 -> D-SRC-06 (P3); SRC-SEC-21 -> D-SRC-09 (P3); SRC-MIG-01 -> D-SRC-01 (P3); SRC-HELP-07 -> D-SRC-07 (P3). D-SRC-05 and D-SRC-10 (P3) were found through passing cases. Blocked: SRC-LST-09 (narrow card), SRC-KEY-11 (mouse), SRC-UI-19 (theme switch), SRC-MIG-10 (live upgrade). Not run: SRC-UI-16 (animation timings are not measurable through the harness).

### S3. Results by category

Runs: `h01` migration (+ `h01-keep`, `h01-t0`, `h01-none`, `h01-garbage`), `h02a/b/c` first run, `h03` invalid input, `h04` paste, `h05` add failure, `h06` switch + list + remove (H06/H07), `h08` timing, `h09` + `h09b` CLI parity, `h10` + `h10b` Xtream, `h11` + `h11b` duplicates/cap, `h12` edit, `h13` privacy sweep, `h14` + `h14b/c/d` cancel/busy/persist/deadline, `h16` + `h16w` + `h16t` state hygiene, `h20` + `h21` M1 regression. Node/python vector outputs: `logs/model-*.txt`, `logs/help-01.txt`, `logs/static-greps.txt`.

#### FR - First run

| ID | Result | Evidence |
|---|---|---|
| SRC-FR-01 | pass | `shots/sources-first-run.png`: glyph U+F0502, `No playlist configured`, prose, `Playlist` focused with a caret, `EPG`, `Use Xtream login instead`, `Load`, terminal caption, footer `Enter load - Tab next field - Ctrl+V paste - Esc close`, header dimmed `Search channels...`; typing `o r f x s` inserted text only (`h02a`: value `o r f x s`, no refresh, mode `sourceEdit`) |
| SRC-FR-02 | pass | `h02b`: served URL + EPG -> search mode, `rows 8`, footer `8 channels in 3 groups`, `updateEntryInline` once with keys `id,playlistUrl,epgUrl,refreshMinutes,mpvArgs,showChannelName,maxRecents,barLabelMaxWidth playlist (set) epg (set)`, record `584a58e5` `channelCount 8 groupCount 3`; the fetch is too fast (< 250 ms) to catch the `Fetching from 127.0.0.1...` line, seen instead on `h05` / `h14` (`probeHost 127.0.0.1`, `shots/sources-fetching.png`) |
| SRC-FR-03 | pass | `h02a`: typed path -> record `kind file`, label `qa-src-a.m3u`, host `local file`, `activeCache .../sources/ca124de2`, `shots/sources-first-run-done.png` (pinned `Sources 1`) |
| SRC-FR-04 | pass | `h02c` Tab x6: `epg, xtream, load, playlist, epg, xtream`; Shift+Tab / Down / Up as expected; Enter on the focused `Load` submits (empty -> `Enter a playlist URL or path`, focus `playlist`); Enter in `EPG` submitted in `h02b` |
| SRC-FR-05 | pass | `h05`: `addSource http://127.0.0.1:9/x.m3u` -> `sourceProbeFinished {ok:false, reason:"Connection refused", host:"127.0.0.1"}`, `activeSourceKey 584a58e5`, `rows 8`, `updateEntryInline` count unchanged (0), no record, `sources/` unchanged (SR23); form path: `HTTP 404 Not Found from 127.0.0.1`, focus `playlist`, value kept (33 chars), `shots/sources-add-failed.png` |
| SRC-FR-06 | pass | `h02c`: text in Playlist + Esc -> cleared (guide open); text in EPG + Esc -> cleared, Esc again with everything empty -> closes; Playlist text + focus on empty EPG + Esc -> focus moves to Playlist, Esc clears it, Esc closes |
| SRC-FR-07 | pass | `h14`: Esc while fetching from the silent server -> `formProbing false`, values kept (27 chars), no result line, 0 helper processes, no new `sources/<key>`, `find -name '.tmp-*'` empty |
| SRC-FR-08 | pass | `h06`/H07: `Saved sources (1)` after the active source was removed (`shots/sources-none-active.png`), Tab x2 -> focus `savedSources`, Return -> `sources` with `returnMode sourceEdit`, Esc -> back to the form |
| SRC-FR-09 | pass | `h10b`: Tab x2 + Return -> `sourceXtream` origin `firstRun`; Esc with empty fields -> first-run form (focus on the link); `h14d`: filled and submitted -> search mode, `4 channels in 2 groups`, active `6e90a03e`, 0 password needles in the console |
| SRC-FR-10 | pass | `h02b`: `epg-now.json`, `epg-status.json`, `epg-window.txt` under `sources/584a58e5/` and nothing at the top level; `shots/sources-epg-rows.png` shows `Now: Alpha Evergreen` on the two news rows |
| SRC-FR-11 | fail | D-SRC-03, D-SRC-06: `ipc set playlistUrl ftp://x` -> `settingsInvalid {code:"scheme"}` but `emptyKind loading`, `Loading playlist... / Fetching from x` for good (`h09b`, `shots/sources-cli-ftp.png`; same for `ftp://example.test/x.m3u` in `h21`, `shots/m1-ftp-cli.png`); `javascript:` -> error `Unsupported URL from unknown source`, `/proc/self/environ` -> `Path not allowed` host `local file`, 3,000 chars -> `URL too long from h.test` (`shots/sources-cli-invalid.png`): M1 wording with a host, not the UX 5.4 messages. No helper ran, no record (pass parts); `set playlistUrl ''` -> first-run form, history untouched (3 records), 0 rows behind the form (D-LIVE-19 regression ok) |
| SRC-FR-12 | pass | `h04`: Ctrl+V and Shift+Insert both paste (34 chars); the userinfo URL is masked at once `http://****@127.0.0.1:8765/qa-src-userinfo.m3u` with the eye (`shots/sources-first-run-masked.png`); typed text is never masked (`revealed:true` while typing) |

#### LST - Sources list

| ID | Result | Evidence |
|---|---|---|
| SRC-LST-01 | pass | `h06`: list mode + `o` -> `mode sources`, `returnMode list`, cursor 0 on the active row, header `Sources` / `3 sources` (`shots/sources-list.png`); from search mode `o` types (`h06`, `h08` redo: query `oj`, `ojo`) |
| SRC-LST-02 | pass | `shots/sources-first-run-done.png`, `sources-switched.png`, `m1-nomatch-group.png`: separator, glyph U+F0411, `Sources`, count 1/3/4 at reduced opacity under the group column; `h`/`l` in `sources` never land on it (`h06` ignored keys); grep of the tokens under SRC-UI-12; click and hover are live-shell (SRC-KEY-11) |
| SRC-LST-03 | pass | `shots/sources-list.png`: check U+F012C + bold `127.0.0.1:8765` + `active - 127.0.0.1:8765 - 8 channels in 3 groups`, `used 19:07`; `Charlie` `local file - 3 channels in 1 group`; `shots/sources-sweep-list.png`: `active - 127.0.0.1:8765 - Xtream - 4 channels in 2 groups - EPG`; `not loaded yet` / `used yesterday` rows in `shots/sources-full.png`; `never used` / `used 3 Sep 2025` through `Model.formatLastUsed` (MODEL-11) |
| SRC-LST-04 | pass | `shots/sources-list.png`: separator then `+ Add source` (U+F0415) and U+F0306 `Add Xtream login`, single-row height; `h06`: End -> cursor 4 kind `xtream`; footer on them in `shots/sources-full.png` is the cap message (SR24) - the plain `j/k move - Enter open - Esc back` variant was seen in `h05` state dumps only through `sourceCursorKind` |
| SRC-LST-05 | pass | `shots/sources-list.png`, `sources-confirm.png`: pencil U+F03EB and close-circle U+F0159 only on the cursor row, right meta shifted left; hover/tooltips are live-shell |
| SRC-LST-06 | pass | `h06`: Esc from `sources` -> `returnMode` (`list` with query `alpha` kept, `h08` redo); `o` again -> back; no helper (3 s watch), no `updateEntryInline` |
| SRC-LST-07 | pass | `1 source` (`h05` `sourceCount 1`), `3 sources` (`shots/sources-list.png`), `50 sources` (`shots/sources-full.png`); `No sources` is unreachable: removing the last source closes Sources (SRC-RM-04), so wireframe 3.2.3 never renders (observation O5) |
| SRC-LST-08 | pass | `h06` `ipc sources`: `584a58e5` (active), `Charlie` (`lastUsedAt` 1789344468), `733cf68c` (1789344466) = active first then `lastUsedAt` desc (SR32); `shots/sources-confirm.png` shows the re-sorted order after B was used; never-used CLI records in added order in `shots/sources-full.png` |
| SRC-LST-09 | blocked: needs live shell | narrow card needs `hyprctl keyword monitor` (section 9.5) |
| SRC-LST-10 | pass | `h06`: `h l r s f / 4`, Tab, Left, Right in `sources` -> cursor 0, `refreshing null`, query empty, `helper-sightings=0`, `updateEntryInline` unchanged |
| SRC-LST-11 | pass | `logs/sweep/sources.json`: keys `id,label,kind,host,hasEpg,channelCount,groupCount,cachedAt,lastUsedAt,lastUsedText,active,origin,errorReason` (three extra non-URL keys, `errorReason` per SR26), 0 `://`, `channelCount -1` when never fetched (`shots/sources-full.png` rows, `h09` CLI row) |
| SRC-LST-12 | pass | `h06`: one source -> `8 channels - updated 18:51`; two or more -> `127.0.0.1:8765 - 8 channels - updated 19:07`, `Charlie - 3 channels - updated 19:07`, `127.0.0.1:8765 2 - 5 channels - updated 09:07` (cached form) |

#### SW - Switching

| ID | Result | Evidence |
|---|---|---|
| SRC-SW-01 | pass | `h06`: Enter on Charlie -> `updateEntryInline` +1 (keys only, `playlist (set)`), `activeCache .../sources/023a756e`, `activeSourceKey 023a756e`, rows 3 -> `Switched to Charlie - 3 channels` (`shots/sources-switched.png`), search mode, empty query, scope `all`; `entryWith` keeps foreign keys (MODEL-11 `refreshMinutes, mpvArgs, foreign`) |
| SRC-SW-02 | pass | `h06`: Enter on the active row -> `returnMode` (`list`), `helper-sightings=0`, `updateEntryInline delta 0` |
| SRC-SW-03 | pass | `h06`: Space -> stays in `sources`, active moves (`ipc sources` `active` flags), transient `Switched to 127.0.0.1:8765 - 8 channels` (`shots/sources-space.png`); second Space -> back to Charlie |
| SRC-SW-04 | pass | `h06`: `fetchedAt` set 10 h back on both caches, switch -> footer `127.0.0.1:8765 2 - 5 channels - updated 09:07` -> `Refreshing...` -> `... updated 19:08`, no banner, no notification |
| SRC-SW-05 | pass | `h08` redo: fresh stamps, switch to Real and back -> `helper-sightings=0` twice, 0 `playlist:` lines; `h01-keep`: restart with `--keep` over a fresh migrated cache -> no refresh |
| SRC-SW-06 | fail | D-SRC-04: `h09b` (c): Enter on the never-fetched CLI source -> footer `Switched to 127.0.0.1:9` while `probing true`, then `sourceErrors {"0a737469":"Connection refused"}` with no banner, no result line, transient unchanged; `activeSourceKey` stays `584a58e5` (correct, SR7) but nothing tells the user (`shots/sources-never-switch-failed.png`); the CLI path itself shows the shipped error state with `r reload - o sources - Esc close` (`shots/sources-never-fetched.png`) |
| SRC-SW-07 | pass | `h06`: favorites 3 under A; after the switch to Charlie `Favorites - 0 channels` and `state.json` still holds the three ids; Recent filtered the same way; 3 again under A (SR9) |
| SRC-SW-08 | pass | `h06`: `Harness Live` playing (mpv pid 72573, widget `Playing Harness Live`), switch to A -> same pid, `nowPlaying` kept, widget kept, `zap 1` -> `no` |
| SRC-SW-09 | pass | `h08` redo: two `switchSource` calls back to back -> second `{"ok":false,"code":"busy","message":"Busy - wait for the current fetch to finish"}`; the first completed |
| SRC-SW-10 | pass | `h08` redo: list mode with query `alpha` -> `o` -> switch -> search mode, query `` ; `o` then Esc -> `list` with query `alpha` |

#### LBL - Labels and editing

| ID | Result | Evidence |
|---|---|---|
| SRC-LBL-01 | pass | `logs/model-04.txt` 28/30 derive+validate ok (`V08` `/srv/tv/` -> `tv` instead of the ARCH `local file` fallback - a directory path is not a valid playlist anyway, observation O6; `T17` per SR22); harness: `127.0.0.1:8765` for URLs and the Xtream server, `qa-src-a.m3u` for a path, `local file` host |
| SRC-LBL-02 | pass | `h11`: second source on the host -> `127.0.0.1:8765 2`, third `... 3` (`shots/sources-sweep-list.png`); `label_taken` case-insensitive (`h11` upper-case variant) |
| SRC-LBL-03 | pass | `shots/sources-edit.png` / `h12`: `Edit source`, `Label` focused, Playlist masked, EPG masked, no Xtream link row, `Cancel` / `Save`, footer `Enter save - Tab next field - Ctrl+R reveal - Ctrl+V replace - Esc cancel` (masked variant) |
| SRC-LBL-04 | pass | `h12`: `updateSource {"label":"Bravo"}` -> `labelCustom true`, no helper, `updateEntryInline delta 0`, `state.json` 600; from the guide `Saved` transient; `h09`: `Custom A` survives `set playlistUrl B` then `A` |
| SRC-LBL-05 | pass | `h11`: `A source named "127.0.0.1:8765" already exists`; `h12`: typed `Bravo` in the edit form -> `label_taken`, focus `label`; keeping the own label -> `Saved` |
| SRC-LBL-06 | pass | `h11`: 65 -> `Label too long - max 64 characters`, 64 accepted (`map(.label|length)` `[64,16,14]`); SR22 code points (MODEL-04 T17: 33 emoji accepted) |
| SRC-LBL-07 | pass | `h12`: `{"label":"   "}` -> `127.0.0.1:8765 2`, `labelCustom false` |
| SRC-LBL-08 | pass | `shots/sources-add-failed.png` (`127.0.0.1:8765` placeholder from the typed URL), `shots/sources-xtream-filled.png` (from the server) |
| SRC-LBL-09 | pass | `h11`: `-u critical`, `--urgency=critical ${path}`, backticks / `$(id)` / pipe, `<b>bold</b>` stored as typed (`jq`), rendered literally (`shots/sources-hostile-label.png`), notifications log unchanged |

#### CLI - CLI parity

| ID | Result | Evidence |
|---|---|---|
| SRC-CLI-01 | pass | `h09`: `set playlistUrl B` with Sources open -> row appears at once (`n 2`, `origin cli`, label `127.0.0.1:8765 2`, active, `not loaded yet` then `5 channels in 2 groups`, `shots/sources-cli-added.png`), no `updateEntryInline` (the CLI path never writes back) |
| SRC-CLI-02 | fail | D-SRC-02: known URL -> no new record, `lastUsedAt` bumped, custom label kept (pass parts); a changed `epgUrl` is NOT adopted into the record (`h09b`: record `epgUrl` length 0, `hasEpg false` after `set epgUrl`) |
| SRC-CLI-03 | fail | D-SRC-03 / D-SRC-06 (as SRC-FR-11): `settingsInvalid` set, no helper (`helper-sightings=0`), no record, `activeCacheDir` empty for all four values (pass parts); `ftp://x` never reaches the error state; the error copy is M1's with a host |
| SRC-CLI-04 | pass | `h09`: `set playlistUrl ''` -> `sourceEdit` first-run, `emptyKind unconfigured`, `rows 0`, 3 records kept, no `cache remove` (`ls sources` unchanged), `shots/sources-cli-empty.png` |
| SRC-CLI-05 | pass | `h11b`: 49 generated + A = 50, `set playlistUrl B` -> `n 50`, `ls sources` diff = `+733cf68c` only, A still present, console `omarchy-iptv: source history full, evicting b48d8a1d` (key only), `state.json` 600 / 16,749 B |
| SRC-CLI-06 | pass | `h09`: `state().service` has `activeSource {id,label,host}` and `sources[] {id,key,label,host,active,channelCount,lastUsed}`, `grep -c '://'` 0; harness `show` unchanged (M1 verbs only, harness `IpcHandler`) |
| SRC-CLI-07 | pass | `logs/sweep/state-show.json`: `state.sources[]` with `host` / `epgHost`, no `url` / `epgUrl`, 0 `://`; `h16`: `state show | grep -cE 'url|://'` 0; `state init` created the v2 file 0600 on every fresh start |
| SRC-CLI-08 | fail | D-SRC-02: `set epgUrl` while A is active runs the EPG helper into `sources/584a58e5/` (`epg-now.json` after 572 ms incl. the IPC round trip; D-LIVE-02 regression ok) but the record keeps `epgUrl ""`; a switch to B and back writes `updateEntryInline ... epg (none)` and `service.epg.configured` turns false (`h09b`) |

#### XT - Xtream

| ID | Result | Evidence |
|---|---|---|
| SRC-XT-01 | pass | `h10`: `c` -> `sourceXtream`, focus `server`, values `label, server, username, password`; `shots/sources-xtream-filled.png`: title `Add Xtream login`, placeholders, prose verbatim, echo-masked password, `Cancel` / `Save`, footer `Enter save - Tab next field - Esc cancel` |
| SRC-XT-02 | fail | D-SRC-08 (P3): `logs/model-03.txt`: 22/28 vectors as the fixture; V03/V04/V06/V07/V08 return `server_path` for any path (UX 5.4 / UX 8 decision 10; the ARCH 3.4 strip rule is not implemented - expectation adjusted `[v0.2]`); E05 `http://h.test/#frag` is accepted (fragment dropped) where ARCH 3.4 says `bad_server`; percent-encoding vector `a b!*'()~-._/@:+` -> `a%20b%21%2A%27%28%29~-._%2F%40%3A%2B` ok; key `6e90a03e` ok |
| SRC-XT-03 | pass | `h10` ipc: `server_empty`, `server_scheme` (`ftp://`, schemeless `h.test` SR16), `server_path`, `server_userinfo` (SR17), `user_empty`, `pass_empty`, `server_too_long` / `user_too_long` / `pass_too_long` (SR18), messages verbatim |
| SRC-XT-04 | pass | `h10`: `4 channels in 2 groups`, record `origin xtream`, view `kind xtream`, `hasEpg true`, `sources/6e90a03e/` holds `epg-*`, rows `Xtream Live One` (`shots/sources-xtream-rows.png`), list detail `active - 127.0.0.1:8765 - Xtream - 4 channels in 2 groups - EPG` |
| SRC-XT-05 | pass | `editMasked 6e90a03e` -> `http://127.0.0.1:8765/get.php?username=****&password=****&type=m3u_plus&output=ts` and `.../xmltv.php?username=****&password=****`; Ctrl+R reveals the raw URL (`shots/sources-edit-revealed.png`); the edit form has no Password row |
| SRC-XT-06 | pass | section S5: 0 hits for `pa ss`, `pa%20ss`, `username=user` in every sink; `password=****` only in the masked strings; the helper `playlist --url` argv carries the URL for the probe only (`h14` `ps -o args=`, expected) |
| SRC-XT-07 | pass | `h10`: after the duplicate result the password field is empty (`p 0`); reopening `c` -> `s 0 u 0 p 0`; `state()` masks credentials as `****` |
| SRC-XT-08 | pass | `h14d` (see SRC-FR-09) |
| SRC-XT-09 | pass | `h10` form: `Already in Sources as "127.0.0.1:8765 2"` (`shots/sources-xtream-duplicate.png`); `h14b` ipc: `http://127.0.0.1:8765/` -> `duplicate` id `6e90a03e` |
| SRC-XT-10 | pass | `h10`: server `http://127.0.0.1:9` -> `Connection refused from 127.0.0.1`, focus `server`, server (18) and username (2) kept, password dropped, nothing saved |

#### RM - Removal

| ID | Result | Evidence |
|---|---|---|
| SRC-RM-01 | pass | `shots/sources-confirm.png`: `Remove "127.0.0.1:8765 2"? Its cache is deleted too.` (curly quotes), `Cancel` / `Remove` with `Remove` preselected in the urgent fill, footer `Left/Right choose - Enter confirm - Esc cancel`; `x`, Delete-key path via `startRemove` (grep); Left/Right toggled then Return confirmed (`h06`) |
| SRC-RM-02 | pass | `h06`: `Removed 127.0.0.1:8765 2`, `sources/733cf68c` gone, others intact, record gone, cursor stays 1, `sourceRemoved {"id":"733cf68c"}` |
| SRC-RM-03 | pass | `h06`: message variant confirmed by the mode (`confirmRemove`) and the outcome: `updateEntryInline ... playlist (none) epg (none)`, `configured false`, `Removed 127.0.0.1:8765 - no active source`, Sources stays open, Esc -> first-run form with `Saved sources (1)` (`shots/sources-none-active.png`); playback continued in the RM-09 run |
| SRC-RM-04 | pass | `h06`: last removal from the screen -> `sourceEdit` origin `firstRun`, focus `playlist`, `n 0`, `sources/` empty |
| SRC-RM-05 | pass | `h06`: Esc cancels, `j` moves at once; `y` / `n` do nothing; Cancel button / scrim are live-shell |
| SRC-RM-06 | pass | `h14`: `removeSource <probing id>` -> `busy` with the id; removing another source during a probe is allowed (observation O2) |
| SRC-RM-07 | pass | H15 (`cli-cache`): `removed: ["channels.json","playlist-status.json"], kept: ["foo.bin"]` with the dir left; after `rm foo.bin` the dir goes; missing dir -> `ok, removed: []`; one JSON line per call |
| SRC-RM-08 | pass | `h06`: `x` and `e` on the `Add Xtream login` row -> mode stays `sources` |
| SRC-RM-09 | pass | `h06`: removing the playing `Harness` source -> mpv pid 72573 unchanged, widget `Playing Harness Live`, no notification |

#### ERR - Errors

| ID | Result | Evidence |
|---|---|---|
| SRC-ERR-01 | pass | `h03` (23 vectors): `scheme` for `ftp:`, `javascript:`, `data:`, `vbscript:`, `rtsp:`, `mailto:`, `about:`, `provider.test/list`, `list.m3u`, `//h.test/x`; `relative_path` for `./list.m3u`, `~/tv/list.m3u`; `unsafe_path` `Path not allowed` for `/proc`, `/sys`, `/dev`; `invalid` for `http://h .test/`, `http://`, `[not-an-ip]`, port 65536 (SR15); `too_long`; `empty`; EPG variants `EPG: start with ...`, `EPG: use an absolute path ...`, `EPG: invalid URL - check the host`; focus on the field; the error clears on the next edit (`ftp://xa` -> `err null`) |
| SRC-ERR-02 | pass | `h05`: `Connection refused`, `HTTP 404 Not Found`, `Not an M3U playlist` (SR28), `Playlist has no channels`, `Could not resolve host` (host `no-such-host.invalid`), all `from 127.0.0.1` on the result line; paths: `Not an M3U playlist` alone for `file:///etc/passwd`; `Timed out` (`h14`); `File not found` (`h09` `~` path) |
| SRC-ERR-03 | pass | `h05`: nine failed adds, `activeSourceKey 584a58e5` throughout, rows 8 behind the form, `updateEntryInline` 0, one `sourceProbeFinished` per probe with a redacted reason and host, `sources/` unchanged, no `.tmp-*` |
| SRC-ERR-04 | pass | `h03`: `helper-sightings=0` over the vector loop, `sources/` untouched (only the two `file:`/traversal probes ran, by design) |
| SRC-ERR-05 | pass | `h11b`: `too_many` `Sources is full (50) - remove one first`, `canAddSource false`, `a` / `c` / Enter on the action rows show the message (`shots/sources-full.png`), `e` still edits |
| SRC-ERR-06 | pass | `h14`: `busy` for `addSource`, `switchSource`, `xtream`, `removeSource(probing)`; `not_ready` for `addSource` right after start; neither code appears as raw text in the guide (`Busy - wait for the current fetch to finish`, `Not ready yet - try again in a moment` are the messages) |
| SRC-ERR-07 | pass | `h14b`: `failPersist true` + switch -> `{"ok":false,"code":"persist_failed","message":"Could not save settings - try omarchy bar set"}`, signal `sourcesPersistFailed {"reason":"persist_failed"}`, footer transient and the add form's result line carry the copy (`shots/sources-persist-failed-form.png`), active unchanged, 0 `omarchy bar` argv lines (SR25) |
| SRC-ERR-08 | pass | `h05`: Return again -> second `sourceProbeFinished` for the same id `458f2bac`, 1 record, no duplicate; `retrySource` verb exists (harness) |
| SRC-ERR-09 | pass | `h14`: silent server probe ends after 20,725 ms with `Timed out` from `127.0.0.1` (helper `--timeout` 20 s, D-LIVE-11) |

#### KEY - Keyboard and mouse

| ID | Result | Evidence |
|---|---|---|
| SRC-KEY-01 | pass | `h06`: list mode `o` opens; search mode `o` types (`oj`); list-mode hint ends with ` - o sources` (`Model.footerHints` `[["r","reload"],["o","sources"],["Esc","close"]]` for the error state and the `o sources` pair in `shots/sources-cli-invalid.png`) |
| SRC-KEY-02 | pass | `h06`, H07: `j`/`k`, Home/End over source and action rows, Enter/Space semantics, `a`, `c`, `e`, `x`/Delete, `o`/Esc; `x`/`e` no-op on action rows |
| SRC-KEY-03 | pass | `h04`/`h02`: printable inserts, Backspace, Ctrl+U clears, Ctrl+V / Shift+Insert paste then sanitize, Tab/Down/Shift+Tab/Up order and wrap, Enter submits or activates the focused `Load`; Ctrl+Backspace and Ctrl+A select-all on plain fields not exercised individually |
| SRC-KEY-04 | pass | `h04`, `h12`: on a masked value Right and Ctrl+A are no-ops, Backspace and Ctrl+U clear the whole value, typed `x` replaces it (field now plain), paste replaces and re-masks, Ctrl+R reveals (footer `Ctrl+R hide`, `shots/sources-first-run-revealed.png`) and re-masks; Tab away re-masks |
| SRC-KEY-05 | pass | `h12`: Esc in an edit form from Sources -> `sources`, nothing kept; first run: clear-first rules (SRC-FR-06); while fetching Esc cancels in both origins (`h14`, `h14b`) |
| SRC-KEY-06 | pass | `h06`: Left/Right toggle, Return confirms, Esc cancels, `y` / `n` ignored |
| SRC-KEY-07 | pass | `h02`: `o r f x s`, `4 r s f` become text in the field; `h06`: letters in `confirmRemove` do nothing |
| SRC-KEY-08 | pass | `h06`: Ctrl+R in the guide and in `sources` -> `refreshing null`, mode unchanged |
| SRC-KEY-09 | pass | `Guide.qml:2459` `activeFocusOnTab: false` on the eye button, tooltips `Show query - Ctrl+R` / `Hide query - Ctrl+R` (`copy.tooltipShow/Hide`); click is live-shell |
| SRC-KEY-10 | pass | `j` moves right after Esc from the dialog (`h06`), `o` works right after Esc from a form (`h12`); the first-run `Playlist` field is focused when the form appears (`h02`, `h06` after the active removal) |
| SRC-KEY-11 | blocked: needs live shell | mouse table (section 9.4) |
| SRC-KEY-12 | pass | `logs/static-greps.txt`: one `SOURCE_KEYS` table at `Model.js:1517` next to `footerHints`; Guide.qml spells no key name (grep of `"Ctrl+R"` etc. empty) |

#### UI - States, microcopy, visual tokens

| ID | Result | Evidence |
|---|---|---|
| SRC-UI-01 | pass | `shots/sources-first-run.png` |
| SRC-UI-02 | pass | `shots/sources-first-run-masked.png`: masked on arrival, eye U+F0208, no caret, footer `Enter load - Tab next field - Ctrl+R reveal - Ctrl+V replace - Esc clear`, scheme and host readable |
| SRC-UI-03 | pass | `shots/sources-invalid.png`: U+F0026 + `Start with http://, https://, or / for a local file` in the urgent fill aligned with the fields, footer `Esc clear`; the line's space is reserved (fields do not move between `sources-first-run.png` and `sources-invalid.png`) |
| SRC-UI-04 | pass | `shots/sources-fetching.png` (U+F01D8 `Fetching from 127.0.0.1...`, controls dimmed, hint `Esc cancel`), `shots/sources-add-failed.png` (`HTTP 404 Not Found from 127.0.0.1` urgent) |
| SRC-UI-05 | pass | `shots/sources-first-run-done.png` |
| SRC-UI-06 | pass | `shots/sources-none-active.png`: `Saved sources (1)` before `Use Xtream login instead`, footer `Esc close` |
| SRC-UI-07 | pass | `shots/sources-list.png` (three), `sources-cli-added.png` (CLI source loaded), `sources-full.png` (`not loaded yet` / `used yesterday`), `sources-sweep-list.png` (Xtream + EPG segments); `1 source` and the label-free footer in `h05`; `No sources` unreachable (O5) |
| SRC-UI-08 | pass | `shots/sources-edit.png`, `sources-sweep-edit-playlist.png` (masked, eye), `sources-edit-revealed.png` (raw scrolled to the caret, eye-off U+F0209, footer `Enter save - Tab next field - Ctrl+R hide - Esc cancel`, EPG still masked) |
| SRC-UI-09 | pass | `shots/sources-xtream.png`, `sources-xtream-filled.png` (echo dots), `sources-xtream-fetching.png` |
| SRC-UI-10 | pass | `shots/sources-confirm.png` |
| SRC-UI-11 | pass | `h06`: `Switched to Charlie - 3 channels` -> `Charlie - 3 channels - updated 19:07`; stale: `... updated 09:07` -> `Refreshing...` -> `... updated 19:08` |
| SRC-UI-12 | pass | `logs/static-greps.txt` Guide.qml 1705-1774: `Style.normalBorderWidth`, `Util.alpha(..., 0.28)` separator, `groupEntryHeight`, `Style.font.iconSmall`, `Style.spacing.labelGap`, opacity 0.45 count, `Style.hoverFillFor`, `Qt.PointingHandCursor`, `Behavior on color { duration: 60 }` |
| SRC-UI-13 | pass | `logs/static-greps.txt` UI-13 block: every UX 5.1 string present in `Guide.qml` `copy` / `Model.js` (titles, placeholders, link rows, prose, action rows, tooltips, `Sources`); rendered strings checked in the screenshots above |
| SRC-UI-14 | fail | D-SRC-06 (P3): the error-state hint reads `r reload - o sources - Esc close` (`shots/sources-cli-invalid.png`, `sources-never-fetched.png`) where UX 5.3 says `r retry`; every other footer variant verified verbatim: `sources`, action-row (cap message), form plain / masked / revealed, Xtream, first run `Esc clear` / `Esc close`, fetching `Esc cancel`, confirm, transients `8 channels in 3 groups`, `Added ...` (Model), `Saved`, `Switched to Charlie - 3 channels`, `Removed 127.0.0.1:8765 2`, `Removed 127.0.0.1:8765 - no active source`, `Sources is full (50) - remove one first`, `Could not save settings - try omarchy bar set` |
| SRC-UI-15 | pass | no hex colors / `Qt.rgba` in any qml; `****`, `2048`, `get.php` in Guide.qml only inside the Xtream prose; `Style.space(640)`, `space(96)`, `space(22) + controlGap`, `space(960)` / `space(620)` present; `Model.LIMITS {url:2048,label:64,server:512,user:256,pass:256,sources:50}` |
| SRC-UI-16 | not run | mode flips are instant in every screenshot pair, but the `bannerFadeMs` / `transientMs` / 60 ms values cannot be timed through the harness |
| SRC-UI-17 | pass | `logs/model-vectors.txt`: `used 21:30`, `used yesterday`, `used 3 Sep`, `used 3 Sep 2025`, `never used` |
| SRC-UI-18 | pass | `1 group` / `28 groups`, `5 channels in 2 groups`, `not loaded yet` for -1, `1 source` / `3 sources` / `No sources` (`Model.sourcesHeaderCount`) |
| SRC-UI-19 | blocked: needs live shell | theme switch |
| SRC-UI-20 | pass | grep: card `space(960)` / `space(620)` unchanged, form column `Math.min(body.width, Style.space(640))` (two places), `labelWidth Style.space(96)`, `eyeSlot Style.space(22) + Style.spacing.controlGap`, narrow branch `fieldLabel` above the field (`Guide.qml:2424-2440`) |

#### A11Y

| ID | Result | Evidence |
|---|---|---|
| SRC-A11Y-01 | pass (retracted) | `logs/static-greps.txt` A11Y-01: Heading, Button `sourcesRowAccessibleName`, List `accessibleSources`, ListItem `sourceAccessibleName` with `focused` / `selected`, Buttons `Edit <label>` / `Remove <label>`, Dialog `formAccessibleName` / `Set up a playlist`, EditableText `fieldAccessibleName`, eye Button `Show query` / `Hide query` with `checked`, link Buttons `Saved sources, n` / `Use Xtream login instead`, `Load` / `Save` / `Cancel`, AlertMessage result line, confirm Dialog **RETRACTED 2026-09-15, criterion, not observation.** The evidence quoted here is real and the conclusion drawn from it was not available: this is a grep over source the source was written to satisfy, so the case could not have failed whatever the plugin published. See "Accessibility harness runs" at the end of this file. Result stands as `not run`. |
| SRC-A11Y-02 | pass | screenshots: active = glyph + bold + `active`; error = glyph + words; fetching = glyph + words + dimmed controls; revealed vs masked = text + eye/eye-off; destructive = urgent fill + `Remove` |
| SRC-A11Y-03 | pass | first run `playlist -> epg -> (savedSources) -> xtream -> load -> wrap` (`h02c`, `h06`); edit `label -> playlist -> epg -> save -> cancel -> label` (`h12`); Xtream `server -> username -> password -> save -> cancel -> label -> server` (`h10`); the eye is never a stop |
| SRC-A11Y-04 | pass | rows `detailRowHeight` / `singleRowHeight` (`Guide.qml:2178,2202`), pinned row `groupEntryHeight`; button size by tokens (grep); click targets are live-shell |
| SRC-A11Y-05 | pass (retracted) | `Guide.qml:2464` `Accessible.description: fieldRow.maskable ? Model.maskUrl(...) : ""`, `:2465` `Accessible.passwordEdit: fieldRow.fieldId === "password"` **RETRACTED 2026-09-15, and it was wrong on its own terms.** The case claims a screen reader never gets a secret; `Accessible.description` is not where Qt publishes an editable field's content, so the grep read the one property that was already masked and never the Value that was leaking (D-A11Y-1). `Accessible.passwordEdit` was additionally inert in both directions on Qt 6.11.2 and has since been deleted. Result stands as `not run`. |
| SRC-A11Y-06 | pass | `Bravo, 127.0.0.1:8765, 5 channels in 2 groups, active, last used 15:16`; `x.m3u, local file, not loaded yet, never used`; no URL |

#### PRIV - Privacy rules

| ID | Result | Evidence |
|---|---|---|
| SRC-PRIV-01 | pass | `shots/sources-sweep-list.png`, `logs/sweep/sources.json` (0 `://`) |
| SRC-PRIV-02 | pass | masked until Ctrl+R; re-masked on Tab (`h04`, `h12`), on Esc (`h12` `editMasked` after Esc still masked), on paste (`h04`), on Save (`h12`) |
| SRC-PRIV-03 | pass | `logs/model-vectors.txt` MODEL-06: 9/9 mask vectors incl. the SR4 exception and `maskUrl(path) === path` |
| SRC-PRIV-04 | pass | every transient of S3 checked; `notifications.log` gained no line from any Sources operation across all runs - the only lines are M1's `Playlist error` (a CLI-set active source failing with no cache, `h09`/`h09b`), `Stream failed`, `Playlist refreshed`, `Guide data error` from the M1 regression runs |
| SRC-PRIV-05 | pass | `password: true` echo (screenshot), field emptied after the URLs are built, edit form masked only |
| SRC-PRIV-06 | pass | `h04`: sanitized on arrival (multi-line, RTL, 100 KB), never executed, console has 0 lines with the pasted text (`grep -c aaaa...` 0, `qa-user` 0); paste over a masked field re-masks before the next dump |
| SRC-PRIV-07 | pass (retracted) | SRC-A11Y-05 **RETRACTED 2026-09-15** with SRC-A11Y-05, which it defers to entirely. Result stands as `not run`. |
| SRC-PRIV-08 | pass | `logs/sweep/console.log` plugin lines: keys, labels, hosts, codes, modes only; `grep -cE '://|password=|username=|@'` on plugin lines = 0 in every run log (`h05` count 0, `h08`/`h09` 0, `h13` 0) |
| SRC-PRIV-09 | pass | `grep -n 'playlistUrl' Guide.qml`: the copy strings, `openEditForm` pre-fill and the two service calls only; keys and the CLI go through `service.switchSource` / `removeSource` / reconcile (harness signals identical for both paths) |

#### SEC - Security of the input surface

| ID | Result | Evidence |
|---|---|---|
| SRC-SEC-01 | pass | `h04`: multi-line paste -> one value with CR/LF/TAB removed and the edges trimmed (`...qa-src-a.m3usecond line must vanish`, 57 chars) per ARCH 3.1, refused by the validator, nothing runs, console clean (expectation adjusted `[v0.2]`) |
| SRC-SEC-02 | pass | `h04`: field holds 2,112 characters (`Model.formCapacity` = cap + 64 so `too_long` fires, SR18), screenshot 575 ms after the chord (`shots/sources-paste-100k.png`), Enter -> `Too long - max 2,048 characters`, `helper-sightings=0`, `state()` 3,484 B, 0 log lines with the string |
| SRC-SEC-03 | pass | `h04`: U+202E/U+202C/U+200B kept, trailing U+FEFF kept (SR15 strips a leading BOM only), NBSP and newline trimmed (51 chars); the field draws the bidi segment reversed but `127.0.0.1:8765` stays readable (`shots/sources-paste-rtl.png`); Enter -> `Invalid URL - check the host`, no crash; MODEL-02 vectors 027/033/093/110 as ruled |
| SRC-SEC-04 | pass | `h03`: `javascript:`, `data:`, `vbscript:`, `ftp:`, `rtsp:`, `mailto:`, `about:` -> `scheme` inline, no process; `file:///etc/passwd` accepted and fails at fetch with `Not an M3U playlist` |
| SRC-SEC-05 | pass | `h03`: `/srv/tv/../../etc/passwd` passes the synchronous check and the helper reads the user's own `/etc/passwd` -> `Not an M3U playlist` (allowed by ARCH 3.1; the `/proc`, `/sys`, `/dev` prefixes are refused inline); `~` refused in the form, accepted by the CLI (`h09`: `kind file`, `File not found`); symlink cases not exercised (helper unchanged since M1 SEC-10/11) |
| SRC-SEC-06 | pass | SRC-LBL-09; `state show` prints the label inside JSON only; no notification path takes a label |
| SRC-SEC-07 | pass | section S5 |
| SRC-SEC-08 | pass | H15 (`cli-cache`): `../x`, `../../x`, `abc`, `d5977d8a/..`, `d5977d8a/../../x`, `%2e%2e`, ``, `D5977D8A`, `d5977d8a-1000` -> `bad_key` exit 1; `deadbeef` symlink to the canary -> `bad_key` `cache key escapes the sources directory`; canary intact; `--keep ../x` / `--active ../x` -> `bad_key`; `d5977d8a-0` is a valid key (`[v0.2]`); no path in any message |
| SRC-SEC-09 | pass | `h01`: `state.json` 600 in a 700 dir after migration; `h16`: 600 after label edit, add, switch, remove, favorite; `h12`: 600 after every save; every `sources/<key>` 700 and every file 600 (`find ... | grep -vE '^(700|600) '` = 0 in `h13`, `h12`); `state init` runs before the FileView (`Service.qml:1612`) |
| SRC-SEC-10 | pass | `h11b`: 51st add -> `too_many`; CLI 51st -> LRU non-active evicted, active kept; `state.json` 11,387 B (50 typical) / 217,637 B (worst) - section S4; the prune argv is built from the state keys only (`Service.qml:1167-1172`) |
| SRC-SEC-11 | pass | `h14`: `cancelProbe` -> helper gone in 30 ms, `find -name '.tmp-*'` empty, no `sources/<key>` for the cancelled add, record dropped (`["584a58e5"]`), `sourceProbeFinished {cancelled:true}`; `h14b`: an edit's original record and dir intact after cancel |
| SRC-SEC-12 | pass | `logs/static-greps.txt`: the shell/eval grep is empty; every `Process` `command:` is an argv array (`mkdir`, `state init`, `which mpv`, `wl-paste --no-newline --type text`) |
| SRC-SEC-13 | pass | one `Text.StyledText` (`Guide.qml:2694`, own hint strings), 31 `PlainText` |
| SRC-SEC-14 | pass | SRC-CLI-07 |
| SRC-SEC-15 | pass | `h05` console: `omarchy-iptv probe: omarchy-iptv: playlist: HTTP 404 from 127.0.0.1`, `could not reach 127.0.0.1: [Errno 111] Connection refused`, `... not an M3U playlist ...`, `no playable channels ...`, `could not reach no-such-host.invalid` - hosts and codes only, 0 lines with `://` or the path |
| SRC-SEC-16 | pass | `h10` / `h14d`: 0 `pa ss` / `pa%20ss` / `password=` hits in `state()` and the consoles; the built URL appears in the helper `playlist --url` argv for the probe only (`h14` `ps -o args=`) |
| SRC-SEC-17 | pass | harness `IpcHandler`: no new verb takes a URL in the plugin's own IPC (`status` shape URL-free, SRC-CLI-06); the live `qs ipc show` is section 9.3 |
| SRC-SEC-18 | pass | `h06`: `qa-attrs.m3u` as a source -> 22 channels, `hasEpg false`, no `epg-*` file, 0 `url-tvg` lines (`shots/sources-list-4.png` shows the literal group names as counts only) |
| SRC-SEC-19 | pass | `state.json` holds the URLs (600/700); removal deletes record + dir; the entry is cleared when the active source is removed (`playlist (none) epg (none)`); README lines 46-48, 147 |
| SRC-SEC-20 | pass | `h14`: one probe (`busy`), `h14` PERF-06: one probe + one refresh at once (2 helpers), `h09` queue: 5 removals in a row all completed, `h14` deadline 20.7 s; at most 50 sources; removal of a non-probing source during a probe is allowed (O2) |
| SRC-SEC-21 | fail | D-SRC-09 (P3): `logs/model-vectors.txt` + `h16t`: `../x` and `abc` keys dropped, 3,000-char URL dropped, 500-char label truncated to 64, `channelCount "x"` -> 0, `cacheLayout "x"` -> 0/2, non-objects dropped, first duplicate wins, `garbage{{{` / `[]` / `null` -> empty state, no crash, no directory from a bad key; but a record whose URL carries U+0000 is kept unchanged (`deadbeef`, url length 26) |
| SRC-SEC-22 | pass | `h01`: second start with `--keep` leaves `state.json` mtime unchanged (1789343503) and the layout untouched; `cacheLayout 2` |
| SRC-SEC-23 | pass | H15 prune: `skipped: ["..x","deadbeef","evil"]`, none deleted or followed |
| SRC-SEC-24 | pass | `run.sh` echoes `source2=scheme://host`; `shell.qml:135` logs keys and `(set)`/`(none)` only |

#### MIG - Migration

| ID | Result | Evidence |
|---|---|---|
| SRC-MIG-01 | fail | D-SRC-01 (P3): `h01` `--fresh`: `version 2`, `cacheLayout 2`, favorites `["t:qa.a.news1","t:qa.shared","u:502142db"]`, 3 recents with their `at`, `lastPlayed` intact, `sources[0]` `key 584a58e5`, `url` A, `kind http`, label `127.0.0.1:8765`, `labelCustom false`, `origin migrated`, `addedAt`/`lastUsed` set (pass parts); `fetchedAt 0`, `channelCount 0`, `groupCount 0` instead of the legacy status counts, so the Sources row reads `not loaded yet` until the first refresh |
| SRC-MIG-02 | pass | `h01`: top-level files gone, `sources/584a58e5/channels.json` (1,512 B) + `playlist-status.json` (167 B) = the seeded (stamped) files moved by rename, no `.tmp-*`, 700/600; `cache migrate` output on the CLI: `{"ok":true,"kind":"cache","action":"migrate","key":"584a58e5","moved":["channels.json","playlist-status.json"],"removed":[".tmp-abc"]}` (H15) |
| SRC-MIG-03 | pass | `h01`: `rows 8` / `Favorites - 3 channels` / Recent 3 within the 3 s poll; `--fresh` -> no helper; `h01-t0` -> background refresh, `updated 18:52`, counts 8/3 |
| SRC-MIG-04 | pass | `h01` second start: nothing moved, `state.json` unchanged |
| SRC-MIG-05 | pass | `h01-none`: legacy files deleted, `sources: []`, favorites/recents kept, first-run form |
| SRC-MIG-06 | pass | the legacy status says `sourceHost: "local file"`, the files were attributed to the settings URL's key `584a58e5` (`h01`) |
| SRC-MIG-07 | pass | `mig07/`: v0.1.0 `parseState` -> `version 1`, favorites 3, recents 2, `lastPlayed` kept, unknown keys ignored; v0.1.0 `normalize_state` the same (a downgrade rewrite would drop `sources`, documented) |
| SRC-MIG-08 | pass | `h01-garbage`: empty v2 state (favorites 0), `cacheLayout 2`, legacy files migrated into `sources/584a58e5`, 8 channels, 600, one WARN line (the Qt portal one) |
| SRC-MIG-09 | pass | H15: moves the two files, deletes leftover `.tmp-abc`, idempotent (`moved: []`), without `--key` deletes fresh legacy copies (`removed: [...]`), creates `sources/<key>` 700 |
| SRC-MIG-10 | blocked: needs live shell | section 9.2 |

#### PERF

| ID | Result | Evidence |
|---|---|---|
| SRC-PERF-01 | pass | section S4: 10k switch median 17 ms (warm), 1.5k 10 ms; the first switch to a 10k source in a process is 352 ms (`prepare 335 ms`, observation O4) |
| SRC-PERF-02 | pass | `h08`: `o` on the 10k source -> `mode sources` in 143 ms incl. wtype + the IPC poll, `helper-sightings=0`; `h16`: 50 rows -> 97 ms incl. wtype + poll; the pure guide time is below the IPC resolution |
| SRC-PERF-03 | pass | 50 typical records: 11,387 B generated / 16,736 B after the service rewrite; worst case (2,048-char playlist + EPG URLs, 64-char labels): 217,637 B / 218,797 B; `parseState` on the worst file 0.97 ms (node, 20 runs); saves land within the next 1 s stat tick |
| SRC-PERF-04 | pass | `h08`: open on the 10k cache with 3 sources: IPC round trip median 169 ms with a `state` poll inside the loop; `h20` M1 method (open only) median 71 ms / max 82 (M1: 65-69 ms) |
| SRC-PERF-05 | pass | `h01`: the console does not log the cache jobs; migration + prune had completed within the 3 s poll and the guide answered IPC 605-860 ms after start with 8 rows |
| SRC-PERF-06 | pass | `h14`: a 10k probe while the active 10k source refreshes: 2 helpers in flight, both finished (`Ten-k B - 10,000 channels`), one `sourceProbeFinished`, no new notification, typing afterwards registers |
| SRC-PERF-07 | pass | H15: `touch -d '2 days ago' 22222222/epg-*` -> `agedEpg: ["22222222"]`, its `channels.json` kept, the active key's files untouched; disk per source: 8-channel 1.5 KB + 0.5 KB EPG, 10k 2.6 MB |

#### MODEL - Model.js

| ID | Result | Evidence |
|---|---|---|
| SRC-MODEL-01 | pass | 635 node checks, 29 QML spec cases cover the ARCH 8.3 list (grep of `tests/Model.test.js` for each function name) |
| SRC-MODEL-02 | pass | `logs/model-02.txt`: 104 records, 9 `decision` records now settled (017/018/025/033/093 SR15, 052/053 SR11, 055/090 SR12); 043 `//proc/self/environ` -> `scheme` per SR12 (fixture obsolete); 143 (uppercase path = new source) passes with the reducer; 111 `http://h.test/a<U+2028>b` -> `scheme` with the "Start with http://..." message although the text starts with `http://` (wording nit, folded into D-SRC-06) |
| SRC-MODEL-03 | pass | `logs/model-03.txt`: 22/28 as the fixture, 5 path vectors per the UX rule, E05 -> D-SRC-08; D01/D02/D05 per SR16/17/18 |
| SRC-MODEL-04 | pass | `logs/model-04.txt`: 28/30 (V08 O6, T17 SR22) |
| SRC-MODEL-05 | pass | 7/7 keys incl. `c209be1f` for the trailing space |
| SRC-MODEL-06 | pass | 9/9 |
| SRC-MODEL-07 | pass | v1 -> v2 keeps favorites/recents/lastPlayed, `sources []`, `cacheLayout 0`; tampered shapes as SRC-SEC-21 |
| SRC-MODEL-08 | pass | `logs/model-reducers.txt`: known URL -> no add, `lastUsed` bumped only on key change, `epgUrl` adopted (Model level), custom label kept; unknown -> `origin cli`, derived label; `ftp://x` -> `scheme`, `/proc/self/environ` -> `unsafe_path`, `~/tv/list.m3u` accepted with `origin cli` (SR11); 51st -> `evicted` = the LRU that is not the new active key (observation O3) |
| SRC-MODEL-09 | pass | SRC-LST-11 |
| SRC-MODEL-10 | pass | `qmltestrunner tests/Model.spec.qml` 29 passed (check.sh) |
| SRC-MODEL-11 | pass | `logs/model-vectors.txt`: formatters, `sourceDetail` (wide and narrow), `sourceAccessibleName`, `footerHints` for `sources` / `sourceEdit` / `sourceXtream` / `confirmRemove`, `SOURCE_KEYS` |

#### HELP - Helper

| ID | Result | Evidence |
|---|---|---|
| SRC-HELP-01 | pass | `logs/help-01.txt`: 99 vectors, node and python verdicts identical (0 differences), decisions as SRC-MODEL-02 |
| SRC-HELP-02 | pass | `tests/test_source.py` (34 tests, check.sh); `h03` 3,000-char vector never echoed |
| SRC-HELP-03 | pass | `help10/`: `playlist --cache-dir .../sources/584a58e5` creates the dir 700 and `channels.json` / `playlist-status.json` 600; `epg` the same for `epg-*` |
| SRC-HELP-04 | pass | `state init` on every fresh start (600); `favorite` on the v2 file kept `sources` and `cacheLayout` (`h16`: 49 sources + `["t:qa.a.news1"]`); `public_state()` redaction (SRC-CLI-07) |
| SRC-HELP-05 | pass | SRC-MIG-09 |
| SRC-HELP-06 | pass | SRC-RM-07, SRC-SEC-08 |
| SRC-HELP-07 | fail | D-SRC-07 (P3): `prune --keep 22222222 33333333 --active 11111111` removed `11111111` (the active key is not implicitly kept; Service.qml always lists every key under `--keep`, so no user-visible effect); the rest as expected: keeps listed keys, removes other valid-key dirs, `agedEpg`, `skipped` for non-key names, `bad_key` for a bad `--keep` / `--active` |
| SRC-HELP-08 | pass | `--help` lists `cache`; `cache --help` shows `{migrate,remove,prune}`; every call printed exactly one JSON line on stdout, usage errors on stderr |
| SRC-HELP-09 | pass | `h16t`: the helper read the tampered file and `state show` printed the surviving records only |
| SRC-HELP-10 | pass | `help10/`: `--now 1789244100` -> `qa.shared` now `Shared Now` / next `Shared Next`, `qa.a.news1` now `Alpha Evergreen`, warning `1 programmes for channels not in the playlist dropped`; without `--now` the evergreen rows only |

#### SVC - Service contract

| ID | Result | Evidence |
|---|---|---|
| SRC-SVC-01 | pass | `h09` `state().service | keys`: `activeSource, activeSourceKey, cacheLayout, cacheReady, canAddSource, channels, configured, epg, ..., persistFails, probing, probingKey, settingsInvalid, sourceCount, sourceErrors, switching, ...`; `activeCacheDir` `null`/`""` until ready and after the active removal |
| SRC-SVC-02 | pass | every verb answered `{ok, code, message, id}` synchronously: `ok`, `duplicate`, `too_many`, `busy`, `unknown_source`, `not_ready`, `persist_failed`, `label_taken`, `label_too_long`, `server_*`, `user_*`, `pass_*` |
| SRC-SVC-03 | pass | `signals`: `sourceProbeFinished {ok,id,channelCount,groupCount,reason,host,cancelled,replacedId}`, `sourceSwitched {id,channels}`, `sourceRemoved {id}`, `sourcesPersistFailed {reason}`, `configuredChanged`; reasons already redacted (host only) |
| SRC-SVC-04 | pass | the console does not print the startup steps, but the observable order held in every start: dirs + `state init` -> state loaded (`stateLoaded true` before any action succeeds, `not_ready` before) -> reconcile (CLI record present) -> migrate -> `cacheReady true` -> rows -> optional refresh -> prune (H15 semantics) |
| SRC-SVC-05 | pass | `h06`: after the active removal `emptyKind unconfigured`, `activeSourceKey ""`, rows 0, no stale reason; `h06` switch after a failed CLI source: `emptyKind ""`, `reason ""` (D-LIVE-10 regression ok) |
| SRC-SVC-06 | pass | `h14` PERF-06: probe and refresh ran side by side; both deadlines are the helper's 20 s + the 180 s watchdog (not exercised) |
| SRC-SVC-07 | pass | `h09`: five `removeSource` calls back to back -> all five directories gone, 0 cache warnings |
| SRC-SVC-08 | pass | `h06`: Enter on the active row -> `updateEntryInline delta 0`; `h12`: `e` + Return with the same values -> `Saved`, delta 0 |

### S4. Performance table

| Item | Number | Method |
|---|---|---|
| Switch redraw, 10k warm (5 switches) | median 17 ms, max 352 ms (the first switch to that source: `read 17 ms, prepare 335 ms`; then `read 11 ms, prepare 4 ms`) | `OMARCHY_IPTV_DEBUG=1` lines `omarchy-iptv switch <ms>` (`logs/h08-10k.txt`) |
| Switch redraw, 10k -> 8 channels | median 10 ms, max 19 ms | same |
| Switch redraw, 1.5k | median 10 ms, max 59 ms (first) | `logs/h08-real.txt` |
| Switch wall clock, IPC `switchSource` -> rows updated (10k) | 238 / 250 / 243 ms including two IPC round trips (~50 ms each) | `date +%s%N` around `h.sh ipc` |
| Sources open (`o`) with the 10k source / with 50 records | 143 ms / 97 ms including wtype and the IPC poll; 0 helper processes | `h08`, `h16` |
| Guide open on the 10k cache, 3 sources | IPC round trip median 71 ms, max 82 (M1 on 502f4b3: 65 ms) | `h20` PERF-02 method |
| Helper `playlist` 10k | 482 / 467 ms (wall 0.62 / 0.60 s), maxrss 38 MB, `channels.json` 2,612,025 B (M1: 488/473 ms, 2,610,946 B) | python `resource` wrapper |
| `state.json`, 50 sources | typical 11,387 B (16,736 B after the service rewrite); worst 217,637 B (218,797 B); `parseState` 0.97 ms | `h16` |
| Quickshell RSS | 332 MB before, 382 MB after 10 switches (two 10k lists loaded), 394 MB after 30, 389 MB at the end of the M1 regression run | `ps -o rss=` |
| Probe deadline (silent server) | 20.7 s -> `Timed out` | `h14` |
| Cancel | helper gone 30 ms after `cancelProbe` | `h14` |
| Keystrokes on the 10k list | 20 keys with no delay all registered in order, 610 ms incl. wtype; typing during a 10k refresh intact | `h20`, `h21` |
| EPG helper after a CLI `epgUrl` change | `epg-now.json` 572 ms after the IPC call | `h09` |

### S5. Privacy verdict

Sinks swept in `h13` with sources A, the userinfo URL C (`qa-user:qa-secret@`), the Xtream login (`user` / `pa ss`) and a failed add of `http://qa-user:qa-secret@127.0.0.1:9/x.m3u`: `ipc sources`, `ipc state`, `ipc widget`, `ipc tooltip`, `ipc signals`, `editMasked` for C and the Xtream source, `state show`, the harness console, `notifications.log`, and three screenshots (list, edit form, edit form with the playlist field focused). Needles `qa-user`, `qa-secret`, `pa ss`, `pa%20ss`, `username=user`, `password=`, `cu:cs`, `/live/`: the only matches are `password=****` inside the masked strings returned by `editMasked` (by design, SR4 keeps the query keys); `://` appears only in those masked strings. Expected hits confirmed where they belong: `state.json` (600 in a 700 dir: `qa-user`, `qa-secret`, `pa%20ss` x3, `password=` x3), one `channels.json`, and the helper `playlist --url` argv for the lifetime of the probe. Every run log of the pass (`h01`..`h21`) has 0 plugin lines with `://`, `password=` or `username=`. The revealed-field screenshots (`sources-first-run-revealed.png`, `sources-edit-revealed.png`) carry the raw URL by design (the user opened them). No notification was raised by any Sources operation. Verdict: **clean** (no credential reached a third party, a world-readable file, a notification or the console).

### S6. M1 regression sample

50 M1 cases re-run with the M1 methods (harness IPC + wtype + grim, helper CLI, node) on the harness fixture playlist (`--serve`, one live channel), the qa-sources fixtures and `gen-10k.m3u` (`h20`, `h21`). No regression except the one noted under CFG-04 semantics (D-SRC-03, CLI `ftp://` now lands in the loading state instead of `Unsupported URL`).

| Category | Re-run | Result | Notes |
|---|---|---|---|
| BRW | 05, 06, 07, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 21, 22 | pass | opens in search mode on All (`All - 20 channels`); `tele quebec` finds `Tele-Quebec` (1 match), `sky sports` 2; cap `First 200 of 8,199 - keep typing`, End 199; Down/Up wrap, PgDn 8, Home/End; Left/Right wrap over the column incl. the last group; Esc clears then closes; Tab list mode ignores `q w e 4`, `F` favorites, `/` back; group-scoped zero results `No matches for "zzzzq" in Group 091 Business` / `h/l other groups - Home for All` (`shots/m1-nomatch-group.png`; Home-for-All is the list-mode rule, verified in M1); `Ungrouped` last; `Animation;Kids;Religious` under Animation, found by `religious` |
| PLAY | 01, 04, 05, 06, 10 | pass | mpv window 457 ms after Enter, class `omarchy-iptv`, title `Harness Live`, argv `--wayland-app-id=omarchy-iptv ... --ytdl=no`, widget `Playing Harness Live`; Space keeps the guide open; dead channel -> `Stream failed` / `"BBC One HD" did not play - Failed to open 127.0.0.1`; zap burst ends on the third channel with one mpv at most; `s` -> `Stopped`, bar idle. PLAY-02 not run (one live fixture channel) |
| FAV | 01, 02, 03, 04, 05, 06, 07 | pass | `Added to Favorites` / `Removed from Favorites`, `No favorites yet` (`shots/m1-fav-empty.png`), order = order added, `f` inside Favorites clamps the cursor, `x` unfavorites, recents newest first, the dead channel is in Recent |
| EPG | 01, 02, 03, 04 | pass | guide usable before the EPG (rows first, `Now:` detail after), `until 18:00` meta on `shots/sources-epg-rows.png`, rows without ids show the group only; server down -> `epg.reason Connection refused`, notification `Guide data error` / `Could not fetch the EPG (Connection refused). Channels still work.`, channels intact (the playlist banner has precedence on screen) |
| RFR | 01, 03, 07, 08, 09, 10 | pass | `Refreshing...` -> `Refreshed - 8 channels` -> `8 channels - updated 19:30`, notification `Playlist refreshed` / `8 channels in 3 groups` low; server down + `r` -> banner `Playlist refresh failed (Connection refused) - showing cached copy from 19:30 - r retry` (`shots/m1-offline-banner.png`), footer `8 channels - cached 19:30 - offline`; list change while open 8 -> 5 rows, cursor 7 -> 4; served not-M3U / empty via the CLI with no cache -> `Not an M3U playlist` (SR28 spelling) / `Playlist has no channels` from `127.0.0.1` (`shots/m1-not-m3u.png`). RFR-04 not run (successful helper runs leave no console line to count) |
| UI | 01, 02, 03, 06, 09, 10, 12, 13 | pass | unconfigured = the new first-run form; loading `Fetching from 10.255.255.1` (`shots/m1-loading.png`); error with cache = banner, without = empty error state; no hex colors; hints and scope labels verbatim; copy centralised in `Guide.qml` `copy` + `Model.js`; console carries only the portal WARN and the intentional helper relays |
| PERF | 01, 02, 03, 05, 07 | pass | section S4 |

Not re-run: the remaining M1 cases keep their 502f4b3 result (helper, BarWidget and the M1 paths of Service.qml are unchanged apart from the sources plumbing; `bin/omarchy-iptv` grew the `cache` and `state` verbs only).

### S7. Defects found in this pass (rows in docs/STATUS.md)

### D-SRC-01 (SRC-MIG-01)  P3  found 2026-09-13 at 7e13053 - migration / Service.qml migrate path
Steps: 1. seed `state-v1.json` + `legacy-cache/` with fresh stamps (`qa-sources-scenarios.sh run SRC-H01 --apply --fresh`) 2. start with `--playlist A` 3. `jq .sources[0] state.json`; `ipc sources`; open Sources.
Expected (ARCH 2.2, QA-SOURCES SRC-MIG-01): the migrated record carries `fetchedAt` and `channelCount`/`groupCount` from the migrated `playlist-status.json` (1789244100 / 8 / 3), the row reads `8 channels in 3 groups`.
Actual: `fetchedAt 0, channelCount 0, groupCount 0`; `ipc sources` `channelCount -1`; the active row reads `active - 127.0.0.1:8765 - not loaded yet` while the guide shows the 8 migrated channels (`h01-keep`). With stale stamps the background refresh fills the counts (`h01-t0`). On the live machine the row would read `not loaded yet` until the first timer refresh.
Evidence: `logs/h01.txt`, `logs/h01-variants.txt` section (0).
Notes: Lane 2; `withSourceStats` is not applied from the status file the migration moved (nor, in `h11b`, for the CLI-reconciled source at the cap - `shots/sources-full.png` - although `h14c` shows the normal startup fetch does fill the counts).

### D-SRC-02 (SRC-CLI-02, SRC-CLI-08)  P2  found 2026-09-13 at 7e13053 - CLI parity / Service.qml `onEpgUrlChanged` vs the history record
Steps: 1. sources A (active) and B 2. `ipc set epgUrl http://127.0.0.1:8765/qa-src-a.xml` (= `omarchy bar set ... epgUrl`) 3. `jq '.sources[]|{key,epgUrl}' state.json`; `ipc sources` 4. `ipc switchSource <B>`; `ipc switchSource <A>` 5. `ipc state | jq .service.epg`.
Expected (ARCH D3, SR8, QA-SOURCES SRC-CLI-02/08): the EPG helper runs into `sources/<A>/` AND the changed `epgUrl` is adopted into A's record (`hasEpg true`), so a later switch writes it back into the settings.
Actual: the helper runs (`epg-now.json` after 572 ms, rows show `Now:`), but the record keeps `epgUrl ""` and `hasEpg false`; after the switch away and back `updateEntryInline ... epg (none)` writes an empty `epgUrl` and `service.epg.configured` is false: the EPG the user set from the terminal is silently dropped by the next switch. The same edit through the guide (`updateSource {epgUrl}`) is adopted and survives.
Evidence: `logs/h09b.txt` section (a), `logs/h09.txt` CLI-08 block, `shots/sources-epg-after-switch.png`.
Notes: Lane 2; `reconcileSources` (Model) adopts the EPG URL when it is called with a playlistUrl, but the service does not reconcile on an `epgUrl`-only change. Related: D-SRC-10 (the reverse carry-over).

### D-SRC-03 (SRC-FR-11, SRC-CLI-03; regression of TC-CFG-04)  P2  found 2026-09-13 at 7e13053 - CLI parity / Service.qml synthesized status for `scheme`
Steps: 1. any configured state 2. `ipc set playlistUrl ftp://x` (or `ftp://example.test/x.m3u`) 3. watch `state` for 3 s; screenshot.
Expected (SR8, UX 5.4, M1 TC-CFG-04): the empty error state with the `scheme` reason (`Start with http://, https://, or / for a local file`), no host, no helper.
Actual: `settingsInvalid {code:"scheme"}` and no helper (correct), but `emptyKind loading`, `playlistReason ""`, `sourceHost "x"` / `"example.test"`: the guide shows `Loading playlist... / Fetching from x` indefinitely (`shots/sources-cli-ftp.png`, `shots/m1-ftp-cli.png`). `javascript:alert(1)`, `/proc/self/environ` and a 3,000-character value do reach the error state (with the M1 wording, D-SRC-06). On 502f4b3 `ftp://example.test/x.m3u` rendered `Unsupported URL` (RR3 CFG-04).
Evidence: `logs/h09b.txt` section (b), `logs/h21.txt`.
Notes: Lane 2; the synthesized status for the `scheme` code apparently carries no reason, so the guide's `emptyKind` resolves to `loading`.

### D-SRC-04 (SRC-SW-06)  P2  found 2026-09-13 at 7e13053 - switching / Guide.qml switch transient + no error path for a failed never-fetched switch
Steps: 1. `ipc set playlistUrl http://127.0.0.1:9/never.m3u` then `ipc set playlistUrl A` (a never-fetched record exists) 2. Tab, `o`, cursor on the `127.0.0.1:9` row, Enter 3. poll `state` every 200 ms.
Expected (UX 1.4 uncached row, SR7, SR26, QA-SOURCES SRC-SW-06): Enter probes; on failure the reason is shown (error state whose hint reads `r retry - o sources - Esc close`, or a result line) and the previous source stays active.
Actual: the footer shows `Switched to 127.0.0.1:9` at once (while `probing true`); the probe fails (`sourceErrors {"0a737469":"Connection refused"}`, `sourceProbeFinished ok:false`); no banner, no result line, no error state; the transient stays until it times out and the guide keeps showing A's channels. The user cannot tell the switch failed. The same through `ipc switchSource` (no transient, no visible error either).
Evidence: `logs/h09b.txt` section (c), `shots/sources-never-switch-failed.png`.
Notes: Lane 1 (transient fired before the probe result; no consumer of `sourceErrors` in the list/guide) with Lane 2 for the signal timing.

### D-SRC-05 (found through SRC-RM-03)  P3  found 2026-09-13 at 7e13053 - first run / Guide.qml header when the guide returns to setup
Steps: 1. search for `Harness Live` (query set), play or not 2. Tab, `o`, `x` on the active source, Return 3. Esc.
Expected (UX 1.7, 3.1.1): the first-run form with the dimmed `Search channels...` header.
Actual: the stale query `Harness Live` stays as the header text above the first-run form (`shots/sources-none-active.png`); the query is not cleared when the guide falls back to setup.
Evidence: `logs/h06.txt` H07 block.
Notes: Lane 1.

### D-SRC-06 (SRC-FR-11, SRC-CLI-03, SRC-UI-14, SRC-MODEL-02 vector 111)  P3  found 2026-09-13 at 7e13053 - copy / Model.js + Guide.qml
Steps: `ipc set playlistUrl javascript:alert(1)` / `/proc/self/environ` / a 3,000-character URL; screenshot the empty error state; also type `http://h.test/a<U+2028>b` in the form.
Expected (UX 5.4, 5.3, QA-SOURCES SRC-FR-11): the UX 5.4 message for the code, no host; the error-state hint `r retry - o sources - Esc close`; a URL that starts with `http://` never gets the `scheme` message.
Actual: `Unsupported URL from unknown source - check playlistUrl`, `Path not allowed` from `local file`, `URL too long from h.test - check playlistUrl` (M1 `statusReason` strings plus a host); the hint reads `r reload - o sources - Esc close`; U+2028 inside a URL yields `scheme` / `Start with http://, https://, or / for a local file` in both validators (parity holds, wording misleads).
Evidence: `shots/sources-cli-invalid.png`, `shots/sources-never-fetched.png`, `logs/h09.txt`, `logs/model-02.txt`.
Notes: Lane 1 + Lane 2 (the synthesized status uses the M1 code -> reason table).

### D-SRC-07 (SRC-HELP-07, SRC-SEC-20)  P3  found 2026-09-13 at 7e13053 - helper / `bin/omarchy-iptv` `cache prune`
Steps: three key directories; `cache prune --cache-dir $C --keep 22222222 33333333 --active 11111111`.
Expected (ARCH 2.4, QA-SOURCES SRC-HELP-07): the active source's directory is never removed.
Actual: `removed: ["11111111"]` - `--active` only protects the EPG ageing; a key that is not in `--keep` is deleted even when it is the active one. No user-visible effect today because `Service.qml:1167-1172` passes every state key under `--keep`, but the helper contract is the safety net for a future caller.
Evidence: H15 transcript in this pass's shell output (`cli-cache/`).
Notes: Lane 2; hardening: treat `--active` as implicitly kept.

### D-SRC-08 (SRC-XT-02, xtream-expect.json E05)  P3  found 2026-09-13 at 7e13053 - Xtream / Model.js `xtreamUrls`
Steps: `ipc xtream 'http://h.test/#frag' u p` or `node -e` with the E05 vector.
Expected (ARCH 3.4: a query or fragment on the server -> `bad_server`; UX 5.4: anything after `host[:port]` -> `server_path`): refused.
Actual: `{"ok":true,...}` - the fragment is dropped by `validateSourceUrl` normalization before the `server_path` check, so `http://h.test/#frag` builds `http://h.test/get.php?...` silently.
Evidence: `logs/model-03.txt`, `logs/h10.txt` validation block.
Notes: Lane 1.

### D-SRC-09 (SRC-SEC-21)  P3  found 2026-09-13 at 7e13053 - state / Model.js `normalizeSourceRecord` + helper `normalize_state`
Steps: write a v2 `state.json` whose record `deadbeef` has a `url` with a NUL (U+0000) between `c` and `d.m3u`; start; `ipc sources`.
Expected (QA-SOURCES SRC-SEC-21, ARCH 3.1 sanitize rule): a URL with control characters is dropped or coerced.
Actual: the record is kept with the NUL inside its URL (url length 26, listed as `127.0.0.1:9 - not loaded yet`); a switch to it would hand the NUL to the helper argv.
Evidence: `logs/model-vectors.txt` MODEL-07, `logs/h14.txt` H16 tampered block.
Notes: Lane 1 / Lane 2; run `sanitizeInput` (or the validator) over `url` / `epgUrl` on read.

### D-SRC-10 (found through SRC-H13)  P3  found 2026-09-13 at 7e13053 - CLI parity / Service.qml reconcile on `playlistUrl`
Steps: 1. Xtream source active (its `xmltv.php?username=...&password=...` URL is in the settings `epgUrl`) 2. `ipc set playlistUrl <another provider's URL>` 3. `editMasked <new id>`.
Expected (SR8, ARCH D3): the CLI-added record carries the settings' `playlistUrl`; an EPG URL belongs to the source it was set for.
Actual: the new record adopts the settings' current `epgUrl` - the previous active source's Xtream EPG URL, credentials included - as its own (`logs/sweep/editMasked-C.json`: `epgMasked: http://127.0.0.1:8765/xmltv.php?username=****&password=****` on the userinfo source; the row shows `EPG`). Not a leak to a third party (same file, 0600) but the wrong provider's credentials are attached to a record and would be sent to that record's EPG host on its refresh.
Evidence: `logs/sweep/`, `shots/sources-sweep-list.png`.
Notes: Lane 2; on a `playlistUrl`-only CLI change, reconcile should not carry an `epgUrl` that a switch wrote for a different source (or should clear the settings `epgUrl` when the playlist changes from the CLI). The mirror image of D-SRC-02.

### S8. Observations that are not defects

- O2 `removeSource` of a source that is not the one being probed succeeds during a probe (`h14`: `removeSource 733cf68c` -> ok while `4f7c56cf` probed); ARCH 4.7 only serializes the cache jobs, so this is consistent; recorded.
- O3 `reconcileSources` at the cap evicts the least-recently-used record that is not the NEW active key; when the CLI sets a 51st URL the previously active record is eligible if it is the LRU (`logs/model-reducers.txt`). "Never the active" holds for the key that is active after the change.
- O4 the first switch to a 10k source in a process costs 352 ms (`prepare 335 ms`, the search index); later switches to the same source 16 ms (prepared-LRU present). Budget 150 ms is met on the warm path only.
- O5 wireframe 3.2.3 (`No sources`, cursor on `Add source`) is unreachable: removing the last source closes Sources (SRC-RM-04); only `1 source` / `N sources` render.
- O6 `Model.deriveLabel("/srv/tv/", "file")` gives `tv` (last non-empty segment), the fixture expected the ARCH `local file` fallback; directories are not playlists, cosmetic.
- O7 after a source is removed through IPC while the first-run form shows `Saved sources (1)`, the form focus stays on the now-hidden link (`focus savedSources`, `n 0`); Tab moves on. Only reachable through the CLI/IPC path.
- O8 `--fake-epg` of the dev harness still drops `epg-now.json` at the legacy top level, so it no longer feeds the v2 layout (harness hygiene, not plugin code; the real EPG pair was used instead).
- O9 the migrated files keep the modes they had; the fixture copy in the H15 CLI run was 644 before `cache migrate` and stayed 644 after the rename (the harness seed chmods 600 first, the real v0.1.0 files are 600). A `chmod 600` inside `cache migrate` would be cheap hardening.

### S9. Live-shell cases (blocked, for the lead)

SRC-LST-09, SRC-KEY-11, SRC-UI-19, SRC-MIG-10 and the live steps of SRC-LST-02/05, SRC-RM-01/05, SRC-KEY-09, SRC-A11Y-04, SRC-CLI-01/06, SRC-SEC-07/17/19: QA-SOURCES.md section 9, after the update in place (SR30 re-points the clone's origin at the release).

### S10. Release recommendation

**No-go for v0.2.0 as of 7e13053**: three open P2 defects (D-SRC-02 CLI `epgUrl` lost on the next switch, D-SRC-03 `ftp://` via the CLI leaves the guide loading forever - a TC-CFG-04 regression, D-SRC-04 a failed never-fetched switch shows `Switched to ...` and no error). No P1: no credential reached any sink, `state.json` and every cache file are 0600/0700, the bad-key set is refused, a failed add never displaces the active source, cancel leaves no temp directory, the 50-cap and eviction hold, migration keeps favorites/recents/lastPlayed and moves the cache once. 181/196 pass, 10 fail (3 P2, 7 P3), 4 blocked (live shell), 1 not run; the 50-case M1 regression sample passes apart from the D-SRC-03 regression. After the three P2 fixes: re-run SRC-H09 + `h09b`, SRC-SW-06, TC-CFG-04, then the live runbook (section 9) on the reference machine.

## M2-01 regression on d50e364 (QA, 2026-09-13, 20:21 - 20:57)

Regression re-test after the M2-01 fix round (`f19fe8f` Model.js, `f05420d` helper, `840b6e6` Service/Guide, merged as `d50e364`). Plan of record: `docs/QA-SOURCES.md` v0.3 (this pass corrected three expectations, marked `[v0.3]`: SRC-SW-06 now describes the probe-first switch of SR7/D-SRC-04, SRC-CLI-01 the one write-back of D-SRC-10, SRC-XT-02 the `server_path` verdict of D-SRC-08). Same conventions as the sections above (` - ` stands for U+00B7, `...` for U+2026, `"x"` for the curly quotes; the UI renders the real code points, checked in the screenshots). Evidence root `E=/tmp/claude-1000/omarchy-iptv-qa5/` (`shots/` 63 grim screenshots, `logs/` one harness console per run `h<nn>.log` plus the per-scenario transcripts `h<nn>.txt`, `logs/sweep/` the privacy sinks, `logs/model*.txt`, `logs/help-01.txt`, `logs/nul-probe.txt`, `logs/static-greps.txt`, `logs/h15.txt`, `logs/check.txt`, `logs/validate.txt`; the scripts `h*.sh`, `model*.sh`, `h15.sh`, `static.sh` are the qa4 scripts re-pointed at this root plus `h09c`, `h07b`, `h07c`, `h01s`, `h16t`, `nul-probe.js`).

### R1. Header

| Item | Value |
|---|---|
| Code under test | `d50e364` (merge: M2-01 fix round). `main` gained `0250a7c` (README Sources section and 0.2.0 changelog draft, 20:20:52, README.md and CHANGELOG.md only) before the first harness start at 20:23; `git diff --stat d50e364..0250a7c -- Guide.qml Service.qml Model.js BarWidget.qml bin/omarchy-iptv manifest.json scripts/dev-harness` is empty, so every run below exercised the d50e364 plugin files. `git status` at the end: `docs/QA-SOURCES.md` (the `[v0.3]` rows) plus this section and the STATUS.md rows |
| Gates | `omarchy plugin validate .` exit 0, no output; `scripts/check.sh` all green: manifest ok, qmllint 0 errors (BarWidget 14 / Guide 197 / Service 0 / Model.spec 0 warnings), `node tests/Model.test.js` 653 checks 0 failures (7e13053: 635), python 199 tests OK (7e13053: 196; `test_source` +5 incl. the U+2028/U+2029 escapes, `test_cache` +3 for the implicit `--active`), `qmltestrunner tests/Model.spec.qml` 29 passed, ascii ok (`logs/check.txt`, `logs/validate.txt`) |
| Mode | dev harness only (`scripts/dev-harness/run.sh` under `OMARCHY_IPTV_HARNESS_DIR=$E/harness`, wrapper `h.sh`, `start.sh`/`stop.sh` by PID, notification shim `$E/bin/omarchy-notification-send` first on PATH, `OMARCHY_IPTV_DEBUG=1` for the switch timings). Every `key()` helper now refuses to send wtype while the harness guide reports `opened: false` (the qa4 scripts could leak keys to the focused window after a guide close; see R9). The installed v0.1.0 plugin, `~/.config/omarchy/shell.json`, `~/.local/state/omarchy-iptv` and `~/.cache/omarchy-iptv` were not touched (`find ... -newermt '2026-09-13 20:20'` empty at the end); no `omarchy plugin/bar/theme` state command, no `hyprctl dispatch/reload/keyword`, no sudo. `pgrep -x hyprlock` checked before every wtype batch (never locked). Everything started was reaped: 0 harness quickshell / fixture server / silent server / helper / mpv processes at the end (`pgrep -ax quickshell | grep omarchy-iptv-qa5` = 0) |
| Machine | unchanged: Omarchy 4.0.3, Quickshell 0.3.1, Hyprland 0.56.2, mpv 0.41.0, Python 3.14.7, node 26.8.1, one output eDP-1 1366x768, theme retropc |
| Sources | as the 7e13053 pass: `tests/fixtures/qa-sources/` served from `127.0.0.1:8765` (A `584a58e5`, B `733cf68c`, userinfo C `25b70358`, Xtream `user` / `pa ss` `6e90a03e`, `qa-src-a.xml`, `state-v1.json` + `legacy-cache/`), `qa-empty.m3u`, `qa-not-m3u.html`, `qa-attrs.m3u`, the harness `harness.m3u` with `--serve`, the same generated `gen-10k.m3u` (sha256 `3d360c15...`) and `gen-real.m3u`, the silent loopback server on `127.0.0.1:8799`, 50-record generated `state.json` files, tampered v2 states with NUL / CR LF / ESC / U+0085 / DEL inside `url` and `epgUrl` |
| Not executed | the live-shell runbook (QA-SOURCES.md section 9): SRC-LST-09, SRC-KEY-11, SRC-UI-19, SRC-MIG-10 and the live steps listed in S9 stay `blocked: needs live shell`; SRC-UI-16 stays `not run` (animation timings); SRC-MIG-07 was not re-run (the v0.1.0 parser it exercises did not change) and keeps its 7e13053 pass |

### R2. Defect verification (original repros, QA-RESULTS S7 steps)

| Defect | Sev | Repro re-run | Result on d50e364 | Evidence |
|---|---|---|---|---|
| D-SRC-01 migrated record without counts | P3 | `qa-sources-scenarios.sh run SRC-H01 --apply --fresh`, then `--keep` restart, T0-stamp variant, `--playlist none`, garbage state (`h01`, `h01-variants`, `h01s`) | **verified fixed**: `sources[0]` = `{origin migrated, fetchedAt <stamp>, channelCount 8, groupCount 3}` right after the migration with 0 `playlist:` helper lines (the counts come from the moved `playlist-status.json`, `Model.sourceStatsDiffer`); `ipc sources` `channelCount 8 groupCount 3 cachedAt <stamp>`; the Sources row reads `active - 127.0.0.1:8765 - 8 channels in 3 groups`; the `--keep` restart shows the same; T0 stamps still refresh and fill; the startup-fetched CLI record (`h14c`) and the CLI record after its first fetch (`h09`) carry counts too; migration itself unchanged (files moved by rename, sha256 equal to the stamped legacy files, 700/600, favorites/recents/lastPlayed intact, second start no migrate, `state.json` mtime unchanged) | `logs/h01.txt`, `logs/h01-variants.txt`, `logs/h01s.txt`, `shots/sources-migrated.png` |
| D-SRC-02 CLI `epgUrl` never adopted | P2 | `h09c` (a): A active, `ipc set epgUrl E`; switch to B and back; `set epgUrl ''`; guide path for comparison | **verified fixed**: record A `epgUrl` 34 chars, `hasEpg true`, the EPG helper wrote `epg-now.json` into `sources/584a58e5/` 570 ms after the IPC call (573 ms in `h09`), no write-back needed (`updateEntryInline` delta 0); after the switch away and back the record still carries it, `service.epg.configured true`, the write-back reads `playlist (set) epg (set)` and the rows show `Now: Alpha Evergreen`; `set epgUrl ''` clears the record's EPG (`adoptEpg` default); the guide edit path behaves the same | `logs/h09c.txt` (a), `logs/h08.txt` H09 block, `shots/sources-epg-after-switch.png` |
| D-SRC-03 CLI `ftp://x` stuck in the loading state | P2 | `h09c` (b): `ipc set playlistUrl ftp://x`, 6 polls over 3 s; `ftp://example.test/x.m3u` (TC-CFG-04); `h21` and `h20` UI-03 | **verified fixed**: `emptyKind error` from the first poll, `settingsInvalid {code:"scheme"}`, `invalidSettingsText` = `Start with http://, https://, or / for a local file`, `activeCacheDir null`, 0 helper processes, no record, no `updateEntryInline`; the screen shows `Playlist failed to load` + the UX 5.4 sentence with no host, hint `o sources - Esc close`; Esc + reopen keeps the state; `r` runs nothing; `set playlistUrl ''` -> first-run form with the history untouched; `set playlistUrl A` clears `invalidSettingsText` and `settingsInvalid` (`null`); TC-CFG-04 `ftp://example.test/x.m3u` -> the same error state (`h21`, `h20`) | `logs/h09c.txt` (b), `logs/h21.txt`, `shots/sources-cli-ftp.png`, `shots/m1-ftp-cli.png` |
| D-SRC-04 never-fetched switch reports `Switched to` and no error | P2 | `h09c` (c): CLI dead record `127.0.0.1:9`, A active, Tab/o/j/Enter with 12 polls at 200 ms; Space variant; Enter retry; `ipc switchSource` / `retrySource`; success variants with a served file that appears after the record was made (Enter and Space); `h07b` IPC switch while Sources is open | **verified fixed**: the first poll shows `probing true`, footer `Fetching from 127.0.0.1:9...` (`sourcesProbeText`), no `Switched to` transient; the second poll shows `sourcesNotice` = `Connection refused from 127.0.0.1` on the Sources result line, `activeSourceKey 584a58e5` (A still active, rows 8), `sourceErrors {"0a737469":"Connection refused"}`, `updateEntryInline` delta 0, one `sourceProbeFinished ok:false`; the notice survives j/k, goes with Esc and is absent when Sources reopens; Enter again re-probes the same key (3 records, no duplicate) and shows the notice again; Space keeps the cursor on the row with the notice; an IPC-started probe while Sources is open shows the same `Fetching from ...` then the notice (`h07b`); success: Enter -> `Fetching from 127.0.0.1:8765...` -> search mode with `Switched to 127.0.0.1:8765 3 - 5 channels`, one write-back `playlist (set) epg (none)`, `sourceProbeFinished ok:true` then `sourceSwitched`; Space -> stays in `sources`, `Switched to 127.0.0.1:8765 4 - 8 channels`, the re-sorted row is at the top with the cursor on it | `logs/h09c.txt` (c), `logs/h07b.txt`, `shots/sources-never-switch-failed.png`, `shots/sources-never-space-failed.png`, `shots/sources-never-switch-ok.png`, `shots/sources-never-space-ok.png` |
| D-SRC-05 stale query above the first-run form | P3 | `h07b`: query `Harness Live` (1 row), Tab, o, x on the active row, Return, Esc | **verified fixed**: after Esc `mode sourceEdit`, `origin firstRun`, `query ""`, the header reads `Search channels...`, `Saved sources (2)` link, footer `Removed Harness - no active source`, hint `Enter load - Tab next field - Ctrl+V paste - Esc close`; the confirm dialog for the active row reads `Remove "Harness"? It is the active source; the guide returns to setup.` (SRC-RM-03 message seen on screen for the first time); `Model.openFirstRun` returns an empty query (`logs/model.txt`) | `logs/h07b.txt`, `shots/sources-none-active.png`, `shots/sources-confirm-active.png` |
| D-SRC-06 M1 wording with a host, `r reload`, U+2028 -> `scheme` | P3 | `h09c` (b): `javascript:alert(1)`, `/proc/self/environ`, a 3,000-character URL, `ftp://x`; footer hints in every state; node + python vectors with U+2028 / U+2029 | **verified fixed**: the error state renders `Start with http://, https://, or / for a local file` / `Path not allowed` / `Too long - max 2,048 characters` with no host and the hint `o sources - Esc close` (no `r`: nothing to retry); a fetch failure keeps `r retry - o sources - Esc close` (the never-fetched CLI source, `shots/sources-never-fetched.png`, `Model.footerHints` `logs/model.txt`); `Model.js` and the helper both answer `invalid` / `Invalid URL - check the host` for `http://h.test/a<U+2028>b` and `<U+2029>` (CR / LF are still stripped by the sanitizer per ARCH 3.1, `http://h.test/ab` ok); `grep '"reload"' Model.js Guide.qml` is empty | `logs/h09c.txt` (b), `logs/model.txt`, `logs/model2.txt`, `logs/static-greps.txt`, `shots/sources-cli-js.png`, `shots/sources-cli-proc.png`, `shots/sources-cli-long.png`, `shots/sources-cli-invalid.png` |
| D-SRC-07 `cache prune` removes the `--active` key | P3 | `h15`: dirs `11111111 22222222 33333333`, `cache prune --keep 22222222 33333333 --active 11111111`; `--active` alone; bad `--active` | **verified fixed**: `removed` holds only the other valid-key dirs, `11111111` stays; `--active` alone keeps only the active key; `--active ../x` / `DEADBEEF` -> `bad_key` exit 1; the aged EPG of the active key is kept while a kept non-active key is aged (`agedEpg`); `keep_set.add(check_source_key(active))` at `bin/omarchy-iptv:1951`; `test_cache` +3 | `logs/h15.txt` |
| D-SRC-08 Xtream server with `#fragment` accepted | P3 | `ipc xtream 'http://h.test/#frag' u p` and node E05 (`h09c` (d), `model.sh`) | **verified fixed**: `{"ok":false,"code":"server_path","message":"Server is just http://host:port - no path","field":"server"}` for `http://h.test/#frag`, `http://h.test#frag`, `http://127.0.0.1:8765/#x` and `?q=1`; `http://127.0.0.1:8765/` still ok; fixture E05 now passes (`code: server_path`, `archCode: bad_server`), `xtream-expect.json` 28 cases: the five UX-rule path vectors remain the only non-fixture verdicts (`[v0.2]`) | `logs/h09c.txt` (d), `logs/model.txt` |
| D-SRC-09 record with a NUL in its URL kept | P3 | tampered v2 `state.json` on the harness (`h16t`, explicit `\x00`), node `nul-probe.js` (NUL, SOH, BEL, ESC, DEL, U+0085, CR, LF, TAB via `String.fromCharCode`), helper `state show` on the same file (`model2.sh`) | **verified fixed**: `deadbeef` (NUL in `url`) dropped by the service on load with the console line `omarchy-iptv: state: dropped source deadbeef (invalid url)` (key only), likewise CR LF (`deadbef4`) and ESC (`deadbef5`), the 3,000-character `deadbef0`; `deadbef3` (NUL in `epgUrl`) kept with `epgUrl ""`; `ipc sources` lists the four survivors, the rewritten `state.json` holds no control character, `switchSource deadbeef` -> `unknown_source`; `Model.normalizeSourceRecord` drops every control character listed above and `parseState` logs by key; the helper drops / clears the same records (`stderr`: `dropped source deadbeef (control characters in url)`, `cleared the epgUrl of source deadbef3`), its `state show` output carries no `url`; the `state init` run at start logs the same lines. Note: the qa4 `h14.sh` tampered vector lost its NUL byte when the script was copied (its `deadbeef` record has a plain URL and is legitimately kept in `logs/h14.txt`); `h16t.sh` writes the byte explicitly (`NUL bytes in file: 2`) and is the evidence | `logs/h16t.txt`, `logs/h16n.log`, `logs/nul-probe.txt`, `logs/model2.txt` |
| D-SRC-10 CLI playlist change carries the previous source's `epgUrl` | P3 | `h09c` (e) and the privacy sweep `h13`: Xtream source active (settings `epgUrl` = `xmltv.php?username=...&password=...`), `ipc set playlistUrl C`, `editMasked C`, `ipc sources`, switch back | **verified fixed**: the new record C has `epgUrl ""`, `editMasked` `epgMasked ""`, `hasEpg false`, no `EPG` segment on its row, `service.epg.configured false`; exactly one `updateEntryInline ... playlist (set) epg (none)` write-back follows the CLI change (the settings follow the record, `syncSettingsEpg`); switching back to the Xtream source restores its EPG (`epg (set)`, `epgMasked` `.../xmltv.php?username=****&password=****`); a CLI `set epgUrl E` in a separate write is still adopted (D-SRC-02); the record of the previous source keeps its own EPG throughout. SRC-CLI-01's "never writes back" holds when no EPG was carried (`h09`: 0 write-backs) - expectation updated `[v0.3]` | `logs/h09c.txt` (e), `logs/sweep/editMasked-C.json`, `logs/h13.log`, `shots/sources-sweep-list.png`, `shots/sources-sweep-edit-playlist.png` |

10/10 verified fixed, none reopened, no new defect filed (R9 lists the observations).

### R3. Summary (196 cases)

| Category | Cases | pass | fail | blocked | not run | Runs |
|---|---|---|---|---|---|---|
| FR First run | 12 | 12 | 0 | 0 | 0 | `h02a/b/c`, `h03`/`h04`, `h05`, `h07b`, `h09c`, `h10b`, `h14`, `h14d` |
| LST Sources list | 12 | 11 | 0 | 1 | 0 | `h06`, `h07c`, `h08`, `h09c`, `h11b`, `h13`, screenshots |
| SW Switching | 10 | 10 | 0 | 0 | 0 | `h06`, `h08`, `h09c`, `h01s` |
| LBL Labels and editing | 9 | 9 | 0 | 0 | 0 | `h10`/`h11`/`h12`, `model2` |
| CLI parity | 8 | 8 | 0 | 0 | 0 | `h09c`, `h08` (H09), `h11b`, `h16`, `model2` |
| XT Xtream | 10 | 10 | 0 | 0 | 0 | `h10`, `h10b`, `h14b`, `h14d`, `h09c` (d), `model` |
| RM Removal | 9 | 9 | 0 | 0 | 0 | `h06`, `h07b`, `h07c`, `h14`, `h15` |
| ERR Errors | 9 | 9 | 0 | 0 | 0 | `h03`, `h05`, `h11b`, `h14`, `h14b` |
| KEY Keyboard and mouse | 12 | 11 | 0 | 1 | 0 | `h02c`, `h04`, `h06`, `h07c`, `h12`, `static` |
| UI States, microcopy, tokens | 20 | 18 | 0 | 1 | 1 | screenshots of every run, `h09c` hints, `static`, `model` |
| A11Y | 6 | 6 | 0 | 0 | 0 | `static`, `h02c`/`h10`/`h12` focus orders, node vectors |
| PRIV Privacy rules | 9 | 9 | 0 | 0 | 0 | `h13` sweep, `h04`, `h12`, console greps |
| SEC Security | 24 | 24 | 0 | 0 | 0 | `h03`/`h04`, `h06`, `h10`/`h11b`, `h14`/`h14b`, `h15`, `h16`/`h16t`, `h01`, `static` |
| MIG Migration | 10 | 8 | 0 | 1 | 1 | `h01`, `h01-variants`, `h01s`, `h15` (MIG-07 not re-run, see R1) |
| PERF | 7 | 7 | 0 | 0 | 0 | `h08`, `h14`, `h16`, `h01s`, `h15`, `h20` |
| MODEL Model.js | 11 | 11 | 0 | 0 | 0 | `model.sh`, `model2.sh`, `nul-probe.js`, check.sh |
| HELP Helper | 10 | 10 | 0 | 0 | 0 | `help-01`, `h15`, `h16`, `model2`, check.sh |
| SVC Service contract | 8 | 8 | 0 | 0 | 0 | `h01`, `h06`, `h07b`, `h08`, `h09c`, `h14` |
| **Total** | **196** | **190** | **0** | **4** | **2** | |

The ten 7e13053 failures (SRC-FR-11, SRC-CLI-02, SRC-CLI-03, SRC-CLI-08, SRC-SW-06, SRC-XT-02, SRC-UI-14, SRC-SEC-21, SRC-MIG-01, SRC-HELP-07) all pass. Blocked (live shell): SRC-LST-09, SRC-KEY-11, SRC-UI-19, SRC-MIG-10. Not run: SRC-UI-16 (timings), SRC-MIG-07 (not re-run, unchanged v0.1.0 code). Every other case was re-run with the 7e13053 method; the notable evidence per category:

| Category | Re-run cases and what changed |
|---|---|
| FR | FR-01..04/06/10/12 as before (`h02`, `h04`: typed `o r f x s` becomes text, `8 channels in 3 groups`, `epg-*` under `sources/584a58e5/`, Tab/Shift+Tab/Down/Up order, Esc clear-first rules, masked-on-arrival paste); FR-05 (`h05`: nine failed adds, `updateEntryInline` 0, `sources/` unchanged); FR-07 (`h14`: Esc cancels, values kept, 0 helpers, no `.tmp-*`); FR-08 (`h07b`: `Saved sources (2)`, Tab x2, Return -> `returnMode sourceEdit`, Esc back); FR-09 (`h10b`, `h14d`); **FR-11 now passes** (R2 D-SRC-03/06) |
| LST | LST-01/03/04/05/06/08/10/11/12 as before (`h06`: `o` from list mode, order active-first then `lastUsedAt`, ignored keys with `helper-sightings=0`, footers `Charlie - 3 channels - updated 20:34`, `sources.json` URL-free); LST-07 now also seen with `1 source` on screen (`shots/sources-one.png`); LST-02 pinned row `Sources 1/2/4/5` in the screenshots |
| SW | SW-01/02/03/04/07/08 (`h06`: `updateEntryInline` +1 keys only, `Switched to Charlie - 3 channels`, Space in place, stale stamps -> `Refreshing...` -> `updated 20:35`, favorites `0` under Charlie and back to 3, mpv pid 145571 kept across the switch and the removal); SW-05/09/10 (`h08` redo: `helper-sightings=0` twice, `busy`, list-mode return with query `alpha`); **SW-06 now passes** (R2 D-SRC-04) |
| LBL | LBL-01 (`model2`: 28/30, V08 O6 and T17 SR22 as before; `logs/model2.txt` also confirms `uniqueLabel` ` 2` / ` 3` and `validateLabel` with the source's own id), LBL-02/05/06/09 (`h11`), LBL-03/04/07 (`h12`: `Bravo` `labelCustom true`, empty -> `127.0.0.1:8765 2`, `Saved` with delta 0), LBL-08 (`sources-xtream-filled.png`) |
| CLI | CLI-01 (`h09`: row appears with Sources open, `not loaded yet` -> `5 channels`, 0 write-backs; `h09c` (e): exactly one `epg (none)` write-back when an EPG was carried, `[v0.3]`), **CLI-02/03/08 now pass** (R2), CLI-04 (`h09c`, `h09`), CLI-05 (`h11b`: 51st CLI URL evicts the LRU `b48d8a1d`, key only in the console, `state.json` 600 / 16,758 B), CLI-06 (`h09`: `activeSource {id,label,host}`, `sources[]`, 0 `://`), CLI-07 (`h16`: `state show` 0 `url`/`://`) |
| XT | XT-01/03/04/05/07/09/10 (`h10`: form, 11 validation codes verbatim incl. `server_path` for `#frag` now, `Xtream Live One` rows, `editMasked` + Ctrl+R reveal, password emptied, duplicate `Already in Sources as "127.0.0.1:8765 2"`, `Connection refused from 127.0.0.1` with the password dropped), XT-06 (R7), XT-08 (`h14d`), **XT-02 now passes** (R2 D-SRC-08) |
| RM | RM-01/02/05/08/09 (`h06`), RM-03 (`h07b`: dialog text on screen, `Removed Harness - no active source`, `playlist (none) epg (none)`), RM-04 (`h07c`: last source from the screen -> first-run form, `sources/` empty, `state.json` `[]` 600), RM-06 (`h14`: `busy` for the probing id, O2 for another), RM-07 (`h15`) |
| ERR | ERR-01 (`h03`: 23 vectors, EPG variants, error clears on edit), ERR-02/03/08 (`h05`, `h03`: `Not an M3U playlist` for `file:///etc/passwd` and the traversal path, SR28 spelling), ERR-04 (`h03` `helper-sightings=0`), ERR-05 (`h11b` `Sources is full (50) - remove one first`), ERR-06 (`h14`: `not_ready`, four `busy`), ERR-07 (`h14b`: `persist_failed` code, signal, footer copy `Could not save settings - try omarchy bar set`, the add form's result line, 0 `omarchy bar` argv), ERR-09 (`h14`: 20,671 ms -> `Timed out`) |
| KEY | KEY-01 (`h06` + `h09c` hints: `o sources` pair, `r retry`), KEY-02/06/08 (`h06`), KEY-03/04 (`h02`, `h04`, `h12`: masked-value rules), KEY-05 (`h12`, `h14`, `h14b`), KEY-07 (`h02c` `4 r s f`), KEY-10 (`h07c`: typed text lands in the Playlist field right after the form appears), KEY-09/12 (`static`: `activeFocusOnTab: false` x2, one `SOURCE_KEYS` table, no key name spelled in Guide.qml) |
| UI | UI-01..11 through the screenshots of this pass (`sources-first-run`, `sources-first-run-masked`, `sources-invalid`, `sources-fetching`, `sources-add-failed`, `sources-first-run-done`, `sources-none-active`, `sources-list`, `sources-one`, `sources-full`, `sources-sweep-list`, `sources-edit`, `sources-edit-revealed`, `sources-xtream*`, `sources-confirm`, `sources-confirm-active`; transients in `h06`), UI-12/13/15/20 (`static`: tokens, copy strings incl. the new `sourcesNotice` / `sourcesProbeText` / `invalidSettingsText`, no hex colours, `Style.space(960)/(620)/(640)/(96)/(22)` intact), **UI-14 now passes** (`r retry - o sources - Esc close` for a fetch failure, `o sources - Esc close` for an invalid configured value, every other variant verbatim in the transcripts), UI-17/18 (`model.sh` formatters) |
| A11Y | A11Y-01/05 (`static`: 54 `Accessible.` lines, `passwordEdit`, masked description), A11Y-02 (screenshots), A11Y-03 (`h02c` / `h10` / `h12` focus orders identical to 7e13053), A11Y-04 (`detailRowHeight` / `singleRowHeight` tokens), A11Y-06 (`sourceAccessibleName` `Bravo, 127.0.0.1:8765, 5 channels in 2 groups, active, EPG, last used 18:59` / `x.m3u, local file, not loaded yet, never used`) |
| PRIV | PRIV-01/04/08 (R7 and the console greps: 0 plugin lines with `://`, `password=` or `username=` in `h05`, `h08`, `h09`, `h09c`, `h10`, `h13`, `h16n`), PRIV-02 (`h04`, `h12`: re-masked on Tab, Esc, paste, Save), PRIV-03 (`model.sh` 9/9), PRIV-05 (`h10`), PRIV-06 (`h04`), PRIV-07/09 (`static`) |
| SEC | SEC-01/02/03 (`h04`: 57-character single line, 2,112-character field -> `too_long`, RTL segment kept, `Invalid URL - check the host`), SEC-04/05 (`h03`), SEC-06 (`h11`), SEC-07 (R7), SEC-08/23 (`h15`: 10 bad keys -> `bad_key`, symlink `deadbeef` `cache key escapes the sources directory`, canary intact, `skipped: ["..x","deadbeef","evil"]`), SEC-09 (`h01`: 7/7 plugin paths 700/600; `h16`: 600 after every save; `h13` final modes 0 deviations), SEC-10 (`h11b`, `h16`), SEC-11 (`h14`: helper gone 30 ms after `cancelProbe`, no dir, no `.tmp-*`; `h14b`: an edit's original intact after cancel and after a 404), SEC-12/13/24 (`static`), SEC-14 (CLI-07), SEC-15 (`h05` console: hosts and codes only), SEC-16 (`h10`, `h14d`: 0 needles), SEC-17 (`h09`), SEC-18 (`h06`: `qa-attrs.m3u` 22 channels, `hasEpg false`, 0 `url-tvg` lines), SEC-19 (`h07b`, `h07c`), SEC-20 (`h14`, `h15`, `h08` H09 queue), **SEC-21 now passes** (R2 D-SRC-09), SEC-22 (`h01`) |
| MIG | **MIG-01 now passes** (R2 D-SRC-01), MIG-02/03/04/06 (`h01`, `h01s`: moved by rename with equal sha256, `rows 3` on Favorites / 8 on All / 3 Recent, second start untouched, attribution to the settings key), MIG-05 (`h01-none`), MIG-08 (`h01-garbage`: 1 WARN, the Qt portal one), MIG-09 (`h15`) |
| PERF | R6 |
| MODEL | MODEL-01 (653 checks, 29 spec), MODEL-02 (`model.sh`: 104 records, the same 2 fixture-obsolete verdicts 043 / 143 and 9 settled decisions as on 7e13053; vector 111 now `invalid`), MODEL-03 (28 cases, E05 passes), MODEL-04 (28/30), MODEL-05 (keys `584a58e5` / `733cf68c` / `25b70358` / `6e90a03e` / `a6514da5` reproduced by the harness), MODEL-06 (9/9), MODEL-07 (`nul-probe`, `model.sh`: garbage / `[]` / `null` / non-array -> empty state, v1 -> v2 keeps favorites 3 / recents 3 / lastPlayed), MODEL-08 (`reconcileSources` with `adoptEpg:false` keeps a known record's EPG and starts a CLI record without one; default adopts and clears; `statusFetchedAt`, `sourceStatsDiffer`), MODEL-09, MODEL-10, MODEL-11 (footerHints incl. `retry:false`, `openFirstRun` query, `fetchingLine`, `probeFailureLine`, `sourceDetail`, `sourceAccessibleName`, formatters) |
| HELP | HELP-01 (`help-01.txt`: 99 records, the same fixture-obsolete 043; the only node/python difference is SRC-URL-124, an empty EPG field that only Model.js validates with `kind: "epg"` - not a product difference), HELP-02 (199 tests), HELP-03/10 (`h15` help10 block: 700/600, `--now` `Shared Now`), HELP-04 (`h16` favorite keeps 49 sources + `cacheLayout`), HELP-05/06/08 (`h15`), **HELP-07 now passes** (R2 D-SRC-07), HELP-09 (`model2`: survivors only, `epgHost` cleared for `deadbef3`, keys only on stderr) |
| SVC | SVC-01 (`h09` keys incl. `settingsInvalid`, `probing`, `probingKey`, `switching`, `canAddSource`), SVC-02 (every code seen synchronously: `ok`, `duplicate`, `too_many`, `busy`, `unknown_source`, `not_ready`, `persist_failed`, `label_taken`, `label_too_long`, `server_*`, `user_*`, `pass_*`), SVC-03 (signals URL-free in `h09c`, `h14`, `h14b`), SVC-04 (`h01` order held), SVC-05 (`h07b`: `emptyKind unconfigured`, `activeSourceKey ""`; `h09c`: no stale reason after a failed CLI source), SVC-06 (`h14` PERF-06), SVC-07 (`h08` H09: five removals back to back, 0 cache warnings), SVC-08 (`h06`, `h12`: delta 0) |

### R4. M1 regression sample (55 cases, `h20` + `h21`, harness fixture with `--serve`, the qa-sources fixtures and `gen-10k.m3u`)

| Category | Re-run | Result | Notes |
|---|---|---|---|
| BRW | 05, 06, 07, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 21, 22 | pass | `All - 20 channels`; `tele quebec` 1 match, `sky sports` 2; cap `First 200 of 8,199 - keep typing`, End 199; Down/Up wrap, PgDn 8; Left/Right wrap; Esc clears then closes; list mode ignores `q w e 4`, `F` favorites, `/` back; `No matches for "zzzzq" in Group 091 Business` (`shots/m1-nomatch-group.png`); `Ungrouped` last; multi-group under Animation, found by `religious` |
| PLAY | 01, 02, 04, 05, 06, 10 | pass | mpv window 439 ms after Enter, class `omarchy-iptv`, title `Harness Live`, argv `--wayland-app-id=omarchy-iptv ... --ytdl=no`, widget `Playing Harness Live`; Enter on another channel reuses the window (same pid); Space keeps the guide open; zap burst ends on `Sky Sports Main Event` with one mpv; `s` -> `Stopped`, bar idle. Once in this run the stop needed the SIGKILL escalation (O10) |
| FAV | 01, 02, 03, 04, 05, 06, 07 | pass | `Added to Favorites` / `Removed from Favorites`, `No favorites yet` (`shots/m1-fav-empty.png`), order = order added, `f` inside Favorites clamps the cursor, `x` unfavorites, recents `["BBC One HD","Harness Live"]` |
| EPG | 01, 02, 03, 04 | pass | `h21` with the real pair: rows first, `Now: Alpha Evergreen` detail after; EPG server down -> `epg.reason Connection refused`, notification `Guide data error` / `Could not fetch the EPG (Connection refused). Channels still work.`, channels intact |
| RFR | 01, 03, 07, 08, 09, 10 | pass | `Refreshing...` -> `Refreshed - 8 channels` -> `8 channels - updated 20:55`, notification `Playlist refreshed` / `8 channels in 3 groups` low; server down + `r` -> banner `Playlist refresh failed (Connection refused) - showing cached copy from 20:55 - r retry` (`shots/m1-offline-banner.png`), footer `8 channels - cached 20:55 - offline`; list change while open 8 -> 5 rows, cursor 7 -> 4; served not-M3U / empty via the CLI with no cache -> `Not an M3U playlist` / `Playlist has no channels` from `127.0.0.1` (`shots/m1-not-m3u.png`). RFR-04 stays inconclusive (successful helper runs leave no console line to count) |
| UI / CFG | UI-01, 02, 03, 09, 10, 13; TC-CFG-04 | pass | unconfigured = the first-run form; loading `Fetching from 10.255.255.1` (`shots/m1-loading.png`); **TC-CFG-04 `ftp://example.test/x.m3u` renders the error state again** (D-SRC-03 regression closed); error with cache = banner, without = empty error state; hints and scope labels verbatim; console: portal WARN, the intentional helper relays and one `mpv ignored SIGTERM, sending SIGKILL` (O10) |
| PERF | 01, 02, 03, 05, 07 | pass | R6 |

No M1 regression. The `h20` RFR/EPG/PERF-07 blocks are polluted by the 20 s black-hole fetch of `10.255.255.1` exactly as on 7e13053 (`h21` is the clean re-run, same as then).

### R5. Regression counts

SRC: 190 pass / 0 fail / 4 blocked / 2 not run of 196 (7e13053: 181 / 10 / 4 / 1). M1 sample: 55 pass / 0 fail. Defects: 10 verified fixed, 0 reopened, 0 new. The `[v0.3]` expectation corrections in `docs/QA-SOURCES.md`: SRC-SW-06, SRC-CLI-01, SRC-XT-02.

### R6. Performance, 7e13053 vs d50e364

| Item | 7e13053 | d50e364 | Method |
|---|---|---|---|
| Switch redraw, 10k warm (5 switches) | median 17 ms, max 352 (first: prepare 335) | median 19 ms, max 329 (first: `read 11 ms, prepare 317 ms`; then 19 ms) | `OMARCHY_IPTV_DEBUG=1` `omarchy-iptv switch <ms>` lines (`logs/h08-10k.txt`) |
| Switch redraw, 10k -> 8 channels | median 10, max 19 | median 14, max 16 | same |
| Switch redraw, 1.5k | median 10, max 59 | median 9, max 63 (first) | `logs/h08-real.txt` |
| Switch wall clock, IPC `switchSource` -> rows updated (10k) | 238 / 250 / 243 ms | 272 / 286 / 213 ms (two IPC round trips included) | `date +%s%N` around `h.sh ipc` |
| Sources open (`o`) with the 10k source / with 50 records | 143 / 97 ms | 117 / 99 ms (wtype + IPC poll included); 0 helper processes | `h08`, `h16` |
| Guide open on the 10k cache (M1 method, IPC round trip x5) | median 71, max 82 ms | median 73, max 77 ms (`state` baseline 81 / 89) | `h20` PERF-02 |
| Guide open, 3 sources, close/open x5 with a `state` poll in the loop | median 169 ms | median 156, max 176 ms | `h08` PERF-04 |
| Helper `playlist` 10k | 482 / 467 ms, wall 0.62 / 0.60 s, maxrss 38 MB, `channels.json` 2,612,025 B | 483 / 482 ms, wall 0.62 / 0.62 s, maxrss 38 MB, 2,612,025 B | python `resource` wrapper (`logs/h21.txt` head) |
| `state.json`, 50 sources | typical 11,387 B (16,736 after the rewrite); worst 217,637 (218,797); `parseState` 0.97 ms | typical 11,387 B (16,736); worst 217,637 (218,797); `parseState` 1.23 ms (20 runs) | `h16` |
| Quickshell RSS | 332 MB before, 382 after 10 switches, 394 after 30, 389 at the end of M1 | 329 MB before, 381 after 10, 370 after 30, 397 at the end of `h20` | `ps -o rss=` |
| Probe deadline (silent server) | 20.7 s -> `Timed out` | 20.67 s -> `Timed out` | `h14` |
| Cancel | helper gone 30 ms after `cancelProbe` | 30 ms | `h14` |
| Keystrokes on the 10k list | 20 keys in 610 ms incl. wtype, all registered | 20 keys in 681 ms, all registered; `sky sports` intact during a 10k refresh | `h20`, `h21` |
| EPG helper after a CLI `epgUrl` change | `epg-now.json` after 572 ms | 570 / 573 ms | `h09c`, `h09` |
| First IPC answer after a start with migration + prune | 605-860 ms | 863 ms (`up` after 830 ms) with 8 rows | `h01s` PERF-05 |

Every budget of QA-SOURCES.md section 5 holds as before (150 ms switch on the warm path; the first switch to a 10k source in a process stays at ~330 ms, observation O4). No measurable cost from the fix round.

### R7. Privacy verdict

`h13` repeated with sources A, the userinfo URL C (`qa-user:qa-secret@`), the Xtream login (`user` / `pa ss`), a failed add of `http://qa-user:qa-secret@127.0.0.1:9/x.m3u`, a CLI `set playlistUrl C` while the Xtream source was active (the D-SRC-10 path) and a label edit. Sinks: `ipc sources`, `ipc state`, `ipc widget`, `ipc tooltip`, `ipc signals`, `editMasked` for C and the Xtream source, helper `state show`, the harness console, `notifications.log`, three screenshots (list, edit form, edit form with the Playlist field focused). Needles `qa-user`, `qa-secret`, `pa ss`, `pa%20ss`, `username=user`, `password=`, `cu:cs`, `/live/`: the only match is `password=****` inside the masked Xtream strings returned by `editMasked` (SR4 keeps the query keys); `://` appears only in those masked strings. Expected hits confirmed where they belong: `state.json` (600 in a 700 dir, 3 hits) and one `channels.json`; the helper `playlist --url` argv carries the URL for the lifetime of the probe (`h14`, `ps -o args=`). `notifications.log` gained no line from any Sources operation across the pass (its 6 lines are M1's `Playlist error` for CLI-set sources without a cache, `Stream failed`, `Playlist refreshed` and `Guide data error`); every run console has 0 plugin lines with `://`, `password=` or `username=`; the new console lines of the fix round name keys only (`state: dropped source <key>`, `source history full, evicting <key>`). Final modes: 0 deviations from 700/600. Verdict: **clean**.

### R8. Gate tails

```
== python3 -m unittest discover -s tests
Ran 199 tests in 23.014s
OK
ok   python tests
== qmltestrunner tests/Model.spec.qml
ok   qml spec (29 passed)
== ascii check (code files)
ok   ascii check
check.sh: all green
```
`node tests/Model.test.js`: `653 checks, 0 failure(s)` / `All Model.js tests passed.`; qmllint `BarWidget.qml: 0 errors, 14 warning(s)`, `Guide.qml: 0 errors, 197 warning(s)`, `Service.qml: 0 errors, 0 warning(s)`, `Model.spec.qml: 0 errors, 0 warning(s)`; `omarchy plugin validate .` exit 0 with no output (`ok   manifest valid` in check.sh).

### R9. Observations that are not defects

- O10 (M1, intermittent): in `h20` PLAY-06 the `s` stop after the zap burst logged `omarchy-iptv: mpv ignored SIGTERM, sending SIGKILL` and the mpv process was still alive 1.5 s after `Stopped` (0 by the end of the run); on 7e13053 the same step killed mpv within 1.5 s. The escalation is the D-LIVE-17 fix doing its job and the user-visible result was correct (`Stopped`, bar idle); not Sources code. Worth a second look only if it recurs on the live shell.
- O11 (docs): `docs/UX.md` 441 / 748 still spell the M1 empty-state hint as `r reload - Esc close` while `docs/UX-SOURCES.md` 5.3 and the code now say `r retry`; README and the code agree with UX-SOURCES.
- O12: `service.playlistReason` / `sourceHost` keep the M1 synthesized values (`Unsupported URL` / `x`) for an invalid CLI value; only the guide's `invalidSettingsText` is rendered, and the IPC `status` shape (SRC-CLI-06) is unaffected.
- O13 (harness scripts): the qa4 `h14.sh` tampered-state vector lost its NUL byte in the copy (see D-SRC-09); the qa4 key sequences of `h06` (D-SRC-05 block) and `h14b` (persist-failed guide step) toggle list/search mode blindly and typed letters into the query - reproduced identically on 7e13053, so the cases they meant were verified through `h07b` / `h07c` and the IPC path; every `key()` of this pass refuses to type while the guide is closed (one leaked `Tab o x Return` in `h06` reached the desktop before the guard existed; nothing outside the harness was changed).
- O2..O9 of the 7e13053 pass reproduce unchanged (O2 removal of another source during a probe, O3 LRU eviction, O4 first cold 10k switch, O5 `No sources` unreachable, O6 `/srv/tv/` -> `tv`, O7 focus on the hidden `Saved sources` link after an IPC removal, O8 `--fake-epg` legacy layout, O9 modes of migrated files).

### R10. Live-shell cases (blocked, for the lead)

Unchanged from S9: SRC-LST-09, SRC-KEY-11, SRC-UI-19, SRC-MIG-10 and the live steps of SRC-LST-02/05, SRC-RM-01/05, SRC-KEY-09, SRC-A11Y-04, SRC-CLI-01/06, SRC-SEC-07/17/19 per QA-SOURCES.md section 9, after the update in place. The runbook should also confirm on the live shell: the D-SRC-10 write-back (`omarchy bar set ... playlistUrl` while an Xtream source is active leaves `epgUrl` empty in `shell.json` and one `updateEntryInline`), the D-SRC-04 result line with the real `qs ipc`, and O10 (a stop after a dead stream).

### R11. Release recommendation

**Go for v0.2.0 from the dev harness as of d50e364**: D-SRC-01..10 verified fixed with their original repros, 0 open P1/P2, 0 new defects, 190/196 SRC cases pass with the remaining 6 blocked or not runnable outside the live shell, the 55-case M1 sample shows no regression (TC-CFG-04 back to its 502f4b3 behaviour), performance unchanged within noise, privacy sweep clean, gates green. What remains before the tag is the live-shell runbook (R10) on the reference machine with the updated plugin, then the `docs/STATUS.md` release row.

## Live-shell Sources verification on ec4f702 (QA, 2026-09-13, 21:20 - 21:47)

The section 9 runbook executed on the user's real machine (Hyprland 0.56.2,
eDP-1 1366x768 @ scale 1, quickshell `/usr/share/omarchy/shell`, plugin
`~/.config/omarchy/plugins/io.github.rmcdavid.iptv` at `ec4f702` / v0.2.0,
state already migrated to schema v2). Evidence root
`E=/tmp/claude-1000/omarchy-iptv-live/` (`shots/` 30 grim screenshots each
inspected, `logs/`, `shell.json.bak`, `state-omarchy-iptv.bak`,
`status.before.json`, `status.final.json`). Conventions as the sections above
(` - ` stands for U+00B7, `...` for U+2026, `"x"` for the curly quotes).

Method notes that bound the results below:

- Keystrokes were injected with `wtype`, guarded by `pgrep -x hyprlock`
  before every call **and** by a check that the `omarchy-iptv` layer is
  present, because a closed guide sends keys to the focused window.
- `wtype` modifier+key combinations reach the *application* (`Ctrl+R`,
  `Ctrl+A` all worked) but do **not** trigger Hyprland global binds: three
  spellings of `SUPER + SHIFT + T` were ignored while the same bind is
  registered (`hyprctl binds` -> `modmask=65 key=T`). L1 below is therefore
  a method limitation, not a plugin result.
- The installed plugin's IPC surface is only
  `toggle / previous / next / refresh / stop / play / status`. There is no
  `sources`, `switchSource`, `addSource`, `removeSource`, `set` or
  `editMasked` verb on the shipped build, so every Sources interaction had to
  be driven through real input; the harness verbs of sections 6 and 8 do not
  exist here.

### L1. Results by case

| Case | Verdict | Evidence / note |
|---|---|---|
| A upgrade + migration (SRC-MIG-10) | **pass** | `state.json` `version 2` / `cacheLayout 2`, favorites `[]`, 5 recents and `lastPlayed` preserved, mode `600`; cache is per-source (`sources/d5977d8a/{channels,playlist-status}.json`, dirs `700`, files `600`), no top-level `channels.json`; the migrated row renders `active - iptv-org.github.io - 1,475 channels in 28 groups`, **not** `not loaded yet` (D-SRC-01 stays fixed live); `omarchy plugin update io.github.rmcdavid.iptv --yes` -> `io.github.rmcdavid.iptv is up to date.` from `https://github.com/rmcdavid/omarchy-iptv.git` (SR30 re-point confirmed, HEAD unchanged at `ec4f702`), `omarchy plugin validate` exit 0 |
| B guide + bar after the upgrade | **pass (1 sub-step blocked)** | guide opens via `omarchy-shell shell toggle io.github.rmcdavid.iptv` (the exact string the keybinding and the `omarchy menu` row run) and closes on the same call; search `bloomberg` -> `in All - 5 matches`, footer flips to `Esc clear`; group column with 28 groups and the pinned `Sources 1` row; Enter played `Bloomberg Originals (1080p)` with window `class=omarchy-iptv`, `title=Bloomberg Originals (1080p)`; `stop` reaped mpv in under 0.5 s. **SUPER+SHIFT+T itself is blocked** (see the method note) |
| C Sources screen live | **pass** | `Tab`, `o` from list mode; header `Sources` / `1 source`; row = check glyph + bold label + `used 21:16` + pencil/remove on the cursor row; detail `active - iptv-org.github.io - 1,475 channels in 28 groups`; action rows `+ Add source` / `Add Xtream login`; footer hints exactly `j/k move - Enter switch - a add - c Xtream - e edit - x remove - Esc back`; single-source footer status carries no label prefix, the 2+ source footer does (`qa-src-a.m3u - 8 channels - updated 21:28`). SR32 order (active first, then `lastUsed` desc) held at 2, 3 and 4 sources |
| D add a source live | **fail - D-LIVE-20** | probe copy is right (`Reading the file...` with footer `Esc cancel`, then `Added qa-src-a.m3u - 8 channels in 3 groups`), the label placeholder live-derives `qa-src-a.m3u`, the cache dir `22636a7e` appears - but **the new source does not become active**, contrary to UX-SOURCES 1.5 ("The new source becomes active"). `activeSource` stayed `iptv-org.github.io` and the guide kept 1,475 channels |
| E switch back and forth | **fail - D-LIVE-20 (P1)** | Enter on a source row writes `shell.json` correctly but the running plugin never applies it: footer said `Switched to iptv-org.github.io - 1,475 channels` while the guide still rendered qa-src-a's 8 channels / 3 Alpha groups and `status` reported `qa-src-a.m3u` for 20+ s. A second Enter on the same row produced `Could not save settings - try omarchy bar set`. Per-source caches and "no refetch" could not be measured because no switch ever completed |
| F edit label, mask, reveal | **pass** | `e` on the cursor row -> `Edit source`; label changed to `QA Alpha`, footer transient `Saved`, `labelCustom true`; a userinfo URL added as `127.0.0.1:8791` renders `127.0.0.1:8791 - 5 channels in 2 groups`; the edit form masks it as `http://****@127.0.0.1:8791/qa-src-b.m3u` with the eye button; `Ctrl+R` reveals and flips the hints to `Enter save - Tab next field - Ctrl+R hide - Esc cancel`; `Tab` re-masks |
| G D-SRC-04 live | **pass** | a failed add shows `Connection refused from 127.0.0.1` on the result line, keeps the form open and never displaces the active source; Enter on a never-fetched `127.0.0.1:9` record shows the reason `Connection refused from 127.0.0.1` on the footer, leaves `iptv-org.github.io` active with its check glyph, and leaves `shell.json` untouched. D-SRC-04 verified fixed on the live shell |
| H D-SRC-10 live | **pass** | `omarchy bar set io.github.rmcdavid.iptv playlistUrl <abs path>` while another source was active wrote `{"id":"io.github.rmcdavid.iptv","playlistUrl":"<path>","epgUrl":""}` - the new CLI record did **not** inherit any previous `epgUrl`, and `shell.json` stayed consistent and `0600`. D-SRC-10 verified fixed live |
| I remove sources | **partial - D-LIVE-21 (P1)** | `x` -> `Remove "127.0.0.1:9"? Its cache is deleted too.` with `Left/Right choose - Enter confirm - Esc cancel`; confirm -> transient `Removed 127.0.0.1:9`, the row and its cache dir `4bf03775` both gone. The active-source variant reads `Remove "iptv-org.github.io"? It is the active source; the guide returns to setup.`, confirms to `Removed iptv-org.github.io - no active source`, Sources stays open with no check glyph - **but the guide behind never returns to setup**: it sat on `Loading playlist... / Fetching from iptv-org.github.io` (the source just removed) for 18+ s with `configured true`, `activeSource null` and an empty `playlistUrl` in `shell.json` |
| J mouse | **blocked** | no pointer-injection tool exists on this machine (`ydotool`, `wlrctl`, `dotool`, `xdotool` all absent, no ydotool socket) and Hyprland exposes no click dispatcher; installing one needs `sudo`, which the pass forbids. Every SRC-KEY-11 sub-step stays unverified |
| K theme with Sources open | **pass** | `omarchy theme set tokyo-night` re-skinned the open Sources screen live (card, rows, check glyph, footer) with no reopen, no glitch and no content loss; `omarchy theme set retropc` restored it. No new warning in `qs log` |
| L restart with a non-default source | **pass** | with `QA Alpha` (local file) active, `omarchy restart shell` came back `status ready`, `activeSource QA Alpha`, 8 channels / 3 groups, 5 recents, 3 sources; `qs log -p /usr/share/omarchy/shell --tail 200` contains no `omarchy-iptv` line at all (only the pre-existing `qt.qpa.services` portal warning that is also present at baseline) |
| M narrow card | **blocked** | the card measures ~959 px at the only reachable scale (1366x768 @ 1), above the `Style.space(720)` threshold. `hyprctl keyword monitor eDP-1,1366x768@60,0x0,2` is refused by this install - `keyword can't work with non-legacy parsers. Use eval.` - and the only other lever is editing `~/.config/hypr/*`, which the pass forbids. SRC-LST-09 / SRC-UI-20 stay blocked |

Counts: **7 pass, 2 fail, 1 partial, 3 blocked** over the 13 cases A-M
(J, M and the SUPER+SHIFT+T sub-step of B are the blocked items).

### L2. Root cause shared by D-LIVE-20 and D-LIVE-21

`Service.qml:persistActive` writes the active source through
`shell.updateEntryInline(pluginId, entry)`. On the live host that call
reaches `shell.qml:1078`, which rewrites the bar entry and calls
`persistShellConfig` - the file on disk is always correct. What never
happens is the trip back: the plugin's `settings` property is not re-emitted
for its own write, so `root.playlistUrl` (a `readonly property` bound to
`settings.playlistUrl`, with `onSettingsChanged: root.reconcile()`) keeps the
previous value and `reconcile()` never runs. Proven three ways:

1. after an Enter-switch, `shell.json` held the new URL while `status` served
   the old source for 20+ s (`shots/E-back-t1.png`);
2. an **external** write of the *same* value already on disk
   (`omarchy bar set ... playlistUrl <the URL shell.json already had>`) made
   the plugin reconcile instantly - the FileView sees a foreign write;
3. `qs log` carries `omarchy-iptv: switch did not observe a cache load within
   5000 ms`.

The second-Enter error (`Could not save settings - try omarchy bar set`) is
downstream of the same staleness: `persistActive`'s guard
`if (root.playlistUrl === playlistUrl && root.epgUrl === epgUrl) return true`
compares against the stale in-memory value, so it re-sends values that are
already on disk; `shell.qml` finds nothing to change, takes its
`if (!dirty) return false` branch, and the plugin reports a persist failure
for a write that had in fact already succeeded.

This is why the dev harness never caught it: QA-SOURCES.md section 6 supplies
a **fake `updateEntryInline`** that feeds the change back into the fake
settings object, which the real host does not do. Every Sources switch case
that passed in the 7e13053 and d50e364 passes passed against that fake.

### L3. Performance

Not measurable this pass. The switch redraw budget (SRC-PERF-02/03) needs a
switch that completes; under D-LIVE-20 none did. Guide open and search
redraws were subjectively immediate on the 1,475-channel list and no case
exceeded a visible delay, but no timing is recorded because the grim round
trip (~130 ms) dominates any measurement this harness can take.

### L4. Privacy verdict on the live machine

**Clean.** With a `http://qa-user:***@127.0.0.1:8791/qa-src-b.m3u` source
configured, the test credential appears in exactly the two files that store
it by design, both `0600`: `~/.local/state/omarchy-iptv/state.json` and
`~/.config/omarchy/shell.json`. It appears in **no** other sink:

| Sink | Credential hits |
|---|---|
| `omarchy-shell io.github.rmcdavid.iptv status` | 0 (and 0 occurrences of `://` at all) |
| `qs log -p /usr/share/omarchy/shell --tail 600` | 0 |
| `journalctl --user` over the whole pass | 0 |
| `omarchy-shell notifications` history | 0 |
| helper `bin/omarchy-iptv state show` | 0 (no `"url"`, no `://`) |
| Sources list row, detail, footer transient | 0 - label and detail both render `127.0.0.1:8791` |
| the 30 screenshots | 1, and only `shots/F3-revealed.png`, which is the deliberate `Ctrl+R` reveal |

The `Playlist error` desktop notification for the dead port reads `Could not
fetch the playlist (Connection refused). Open the guide for details.` with no
URL and no host userinfo. `shell.json` kept mode `600` across every plugin
write, and all cache dirs stayed `700` / files `600`. One incidental
hardening confirmed: mpv is launched with
`--title=$>` + the channel name, and `$>` is mpv's "stop property expansion"
escape, so a channel name containing `${...}` cannot be expanded.

### L5. O10

**Did not reproduce.** Two stop paths were exercised: a clean stop of a live
HLS stream (mpv reaped in under 0.5 s) and a stop after a dead stream (the
QA fixture's `127.0.0.1:9` URLs, where mpv exited on its own before the stop).
Neither produced `omarchy-iptv: mpv ignored SIGTERM, sending SIGKILL`, and no
mpv process outlived its stop. O10 was recorded as intermittent, so this is
evidence of absence in two runs rather than a refutation.

### L6. New defects (rows in docs/STATUS.md)

### D-LIVE-20 (SRC-SW-01/02/06, SRC-ADD-*, live-only)  P1  found 2026-09-13 at ec4f702 - switching / Service.qml `persistActive` + host settings round trip
Steps: 1. two or more sources configured, A active 2. Sources, cursor on B, `Enter` 3. poll `omarchy-shell io.github.rmcdavid.iptv status` and `jq` the bar entry in `~/.config/omarchy/shell.json`.
Expected (UX-SOURCES 1.4, 1.5, SR7): B becomes the active source, the guide redraws with B's channels, the footer transient names B.
Actual: `shell.json` is updated to B, the footer claims `Switched to B - N channels`, and the running plugin keeps serving A indefinitely (20+ s, no timeout, no error). Adding a source has the same shape: the add commits and caches but the new source never becomes active. A second `Enter` on the same row reports `Could not save settings - try omarchy bar set` although the value is already persisted. Recovery only through an external write (`omarchy bar set ...`, even of the identical value) or `omarchy restart shell`.
Evidence: `shots/E-back-t1.png` (footer vs content), `shots/D-after-add.png`, `shots/E-after-switch.png`, `qs log`: `switch did not observe a cache load within 5000 ms` + `updateEntryInline refused the settings change`.
Notes: root cause in L2. Masked by the harness's fake `updateEntryInline`. Fix options: apply the value optimistically in `persistActive` on a `true` return instead of waiting for a settings round trip, and treat `updateEntryInline`'s `false` (`!dirty`, i.e. "already persisted") as success rather than `persist_failed`.

### D-LIVE-21 (SRC-RM-01/03/05, live-only)  P1  found 2026-09-13 at ec4f702 - removal / the guide never leaves the loading state
Steps: 1. two or more sources, A active 2. Sources, `x` on A, confirm `Remove` 3. `Esc` back to the guide.
Expected (UX-SOURCES 1.7 and the dialog's own sentence "the guide returns to setup"): the first-run form.
Actual: `shell.json` `playlistUrl` is cleared and `activeSource` becomes `null`, but the guide shows `Loading playlist... / Fetching from <the removed source's host>` and stays there (18+ s, `status loading`, `configured true`). The removed source's cache dir is correctly deleted, so the fetch it is waiting on can never be served from cache. Only an external write or a shell restart recovers.
Evidence: `shots/I-return-to-setup.png`, `shots/I-stuck-loading.png`, poll transcript in `logs/`.
Notes: same root cause as D-LIVE-20 (the cleared `playlistUrl` is the plugin's own write, so `configured` never flips). This is the live recurrence of the D-SRC-03 / TC-CFG-04 "stuck in loading" family, reached through the Sources screen instead of the CLI.

### L7. Observations that are not defects

- O14: `omarchy plugin list --json` reports `version: null` for **all 41**
  installed plugins, first-party ones included, so the null on
  `io.github.rmcdavid.iptv` is an Omarchy CLI trait and not a manifest
  problem (`manifest.json` carries `"version": "0.2.0"`).
- O15: `Model.hostOf` drops the port (`Connection refused from 127.0.0.1`)
  while `Model.deriveLabel` keeps it (`127.0.0.1:9`), so the same source is
  named two ways one line apart. Both match their own spec (UX 5.5 vs 5.6);
  flagged only because it reads oddly on the error line.
- O16: the upstream `iptv-org` US list served 1,474 channels on the refetch
  at 21:41 against 1,475 at 17:52, i.e. the count drifts upstream exactly as
  QA-SOURCES 9.2 warns. Nothing in the plugin changed.
- O17: `omarchy theme set retropc` prints `Ignored in
  /home/ricky/.config/omarchy/themes/retropc: alacritty.toml ghostty.conf
  neovim.lua` - a pre-existing property of the user's own theme clone, not
  related to this plugin.
- O10..O13 of the earlier passes were not re-checked except O10 (L5).

### L8. Restore

The machine was returned to its exact pre-pass state and verified:

- `diff <(jq -S . shell.json.bak) <(jq -S . ~/.config/omarchy/shell.json)` -> **identical**;
- `state.json` `version`, `cacheLayout`, `favorites`, `recents` and the source
  records (`key`, `url`, `label`, `origin`) -> **identical** to the backup;
- one source (`d5977d8a` `iptv-org.github.io`, active), 5 recents, 0
  favorites, `~/.cache/omarchy-iptv/sources/` holds only `d5977d8a`;
- modes back to `600` (`shell.json`, `state.json`) and `700` (cache dirs);
- no mpv, no test HTTP server, port 8791 closed, guide closed, monitor
  untouched (1366x768 @ 1), theme `retropc`.

One value legitimately differs: the source record's `channelCount` is 1,474
against the backup's 1,475, because removing and re-adding the active source
during case I forced a refetch and the upstream list had drifted (O16). The
backups are left in place at `/tmp/claude-1000/omarchy-iptv-live/`.

### L9. The previously live-blocked cases, resolved

The set carried as `blocked` since S9 and R10, with the verdict this pass
gives each one:

| Case | Was | Now | Basis |
|---|---|---|---|
| SRC-MIG-10 | blocked | **pass** | case A - v2 / cacheLayout 2, favorites + 5 recents + `lastPlayed` preserved, 0600/0700, per-source cache, real counts on the migrated row, `plugin update` up to date from GitHub, `validate` exit 0 |
| SRC-CLI-01 | blocked | **pass** | case H - the one write-back: the CLI record takes the new `playlistUrl` and does not inherit the previous source's `epgUrl`; `shell.json` stays consistent and 0600 |
| SRC-CLI-06 | blocked | **pass** | the `status` IPC shape is unchanged live and contains no URL (`grep -c '://'` = 0) across 1, 2, 3 and 4 configured sources |
| SRC-SEC-07 | blocked | **pass** | case F sink sweep - 0 credential hits in `status`, `qs log`, journal, notifications, helper `state show`, and in every row/footer/notification rendered |
| SRC-SEC-17 | blocked | **pass** | `shell.json` kept mode 600 across every plugin write; `state.json` 600; cache dirs 700 / files 600 after adds, edits, removals and a restart |
| SRC-SEC-19 | blocked | **pass** | the `Playlist error` notification carries no URL or userinfo (`Could not fetch the playlist (Connection refused). Open the guide for details.`) |
| SRC-LST-02 | blocked | **pass** | live row layout, active marker, counts, `used HH:MM` and the `not loaded yet` variant all render per UX 5.2 |
| SRC-LST-05 | blocked | **pass** | SR32 order (active first, then `lastUsed` desc) held at 2, 3 and 4 sources |
| SRC-RM-01 | blocked | **pass** | non-active removal: dialog copy, `Removed <label>` transient, row and cache dir both gone |
| SRC-RM-05 | blocked | **fail - D-LIVE-21** | active-source removal reaches `Removed <label> - no active source` but the guide never returns to setup |
| SRC-UI-19 | blocked | **pass** | case K - live re-skin of the open Sources screen in both directions |
| SRC-KEY-09 | blocked | **pass** | `o`, `j`/`k`, `a`, `e`, `x`, `Enter`, `Esc`, `Tab` and `Ctrl+R`/`Ctrl+A` all behave per UX 2.2/2.3 inside the guide |
| SRC-KEY-11 | blocked | **still blocked** | no pointer-injection tool on the machine (case J) |
| SRC-LST-09, SRC-UI-20 | blocked | **still blocked** | the card cannot go under the 720 threshold on this display (case M) |
| SRC-A11Y-04 | blocked | **not run** | single display; the multi-monitor note stays `not run` as in QA.md TC-A11Y-04 |

Net: 11 of the 15 previously-blocked items now pass, 1 fails (SRC-RM-05,
D-LIVE-21), 3 remain blocked or not run for machine reasons. Two cases that
were passing in the harness regress on the live shell: the switch cases
SRC-SW-01/02 (D-LIVE-20).

### L10. Release recommendation

**No-go for v0.2.0 as of ec4f702.** Two open P1 defects, both live-only and
both invisible to the dev harness because it fakes the one host API involved:
D-LIVE-20 makes switching and add-activation non-functional on a real shell
while reporting success, and D-LIVE-21 leaves the guide loading forever after
the active source is removed. Story S3 (switching) and the recovery half of
S7 (removing) are blocked, and `docs/PLAN.md` 222 requires zero open P1/P2 to
release. Everything else on the live shell is sound: migration, the Sources
screen, add/edit/mask/reveal, the failure paths (D-SRC-04 and D-SRC-10 both
verified fixed live), theme re-skin, restart persistence, and a clean privacy
sweep. After the fix, re-run cases D, E and I here, plus SRC-PERF-02/03 which
this pass could not measure; J and M need a pointer-injection tool and a
second display mode respectively and should be dropped from the live runbook
or moved to a machine that has them.

## P1 fix verification on 845d445 (QA, 2026-09-13, 22:39 - 23:06)

Verification of the D-LIVE-20 / D-LIVE-21 fix round (`9525890` Service/Model,
`1c29a4c` harness, merged as `845d445`) before the v0.2.1 hotfix. Both defects
were re-tested with their **original repros** on the user's real machine, the
harness-fidelity claim of the fix lane was measured independently, and the
regression sample was re-run through the dev harness. Same conventions as the
sections above (` - ` stands for U+00B7, `...` for U+2026, `"x"` for the curly
quotes; the UI renders the real code points, checked in the screenshots).
Evidence root `E=/tmp/claude-1000/omarchy-iptv-qa6/` (`snapshot/` the
pre-pass machine state plus `status.before.json`, `restore-proof.json`,
`shots/` 66 grim screenshots (54 from the live pass), the decisive ones
inspected individually, `logs/` the harness consoles and
transcripts, `logs/sweep/` the privacy sinks, `live/` the fixtures and
`UNDO.txt`, `prefix-tree/` the scratch pre-fix checkout, the scripts
`k.sh`, `g.sh`, `sw.sh`, `h20.sh`, `h21.sh`, `h15.sh`, `static.sh`,
`play2.sh`, `dead.sh`, `d19.sh`).

### P1. Header

| Item | Value |
|---|---|
| Code under test | `845d445` (merge: fix D-LIVE-20/21). `origin/main` on GitHub had already moved to `210cfa3` when the installed clone fetched; `git diff --stat 845d445 origin/main` is `CHANGELOG.md`, `CLAUDE.md`, `docs/ARCHITECTURE-SOURCES.md`, `docs/OMARCHY-PLUGIN-CONTRACT.md` only, so the code under test is the same either way |
| Scope beyond the P1 fix | `main` gained a **cosmetics lane** since the last QA pass (`3550693`: `c75dce2` D-LIVE-19, `cf22c3f` EPG helper warnings in the footer) and `48dd054` (UX.md `r reload` -> `r retry`, observation O11). Those are re-tested here as well; the P1 fix itself is confined to `Service.qml` (`hostSettings` / `ownWrite` / `settings`, `persistActive`, `applyOwnWrite`, `onHostSettingsChanged`) and four new `Model.js` functions |
| Live machine | Hyprland, eDP-1 1366x768 @ scale 1, quickshell `/usr/share/omarchy/shell`, plugin `~/.config/omarchy/plugins/io.github.rmcdavid.iptv`, theme Retropc. Baseline: one source `iptv-org.github.io` (`d5977d8a`), active, 1,474 channels in 28 groups, 5 recents, 0 favorites, state schema v2 / cacheLayout 2 |
| Keystroke safety | every `wtype` call went through `E/k.sh`, which refuses unless `pgrep -x hyprlock` is empty **and** `hyprctl layers` shows an `omarchy-iptv` layer; the guide was opened with `omarchy-shell shell toggle io.github.rmcdavid.iptv` (the string the keybinding runs) |
| Switch timings | measurable live for the first time: the shell was relaunched once through `hyprctl dispatch exec_cmd("env OMARCHY_IPTV_DEBUG=1 omarchy-launch-shell")`, which only gates a `console.info` with millisecond counts and channel counts (`Service.qml:99`, `:1059`) and changes no behaviour and no file. The closing `omarchy restart shell` put the canonical launch back |
| Gates | `./scripts/check.sh` all green, `omarchy plugin validate .` exit 0 (P8) |

### P2. D-LIVE-20, original repro

Repro as filed: two or more sources configured, A active; Sources, cursor on
B, `Enter`; poll `omarchy-shell io.github.rmcdavid.iptv status` and `jq` the
bar entry in `~/.config/omarchy/shell.json`.

| Step | Was (ec4f702) | Now (845d445) | Evidence |
|---|---|---|---|
| Add a source | commits and caches, **never becomes active**; the guide keeps the previous channels | **active in 723 ms** (`qa-src-a.m3u`, 8 channels in 3 groups); a second add active in 516 ms; the row renders `active - local file - 8 channels in 3 groups` with the check glyph and the transient `Added qa-src-a.m3u - 8 channels in 3 groups` | `shots/L1c-add-done.png`, `shots/L2-three-sources.png` |
| Switch, both ways | `shell.json` correct, the running plugin serves the old source for 20+ s, footer and content disagree | **4 switches A <-> B all arrived**, wall clock 145 / 158 / 147 / 161 ms (keystroke to `status`, including one 48 ms IPC round trip); the guide redraws to the new source's channels, groups and counts, and the footer transient names the same source the list shows | `shots/L3a..L3d`, `shots/L3d-switch-to-B2.png` (content `Bravo Movies 2` / `Bravo Docs 3`, footer `Switched to qa-src-b.m3u - 5 channels`) |
| Switch to the 1,474-channel source and back | not reachable | arrived in 240 ms / 168 ms; **no refetch**: `sources/d5977d8a/channels.json` sha and `fetchedAt` unchanged across the round trip, `pgrep omarchy-iptv playlist` 0 | `shots/L4a`, `L4b` |
| The retry that said `Could not save settings` | second `Enter` on the same row reported `Could not save settings - try omarchy bar set` although the value was already persisted | **no error at any repetition.** `Enter` on a non-active row switches; reopening Sources and pressing `Enter` on that row (now active, row 1) returns to the channel list with the plain count footer, twice in a row; `lastError` stays `""` and `qs log` carries no `persist`, `refused`, `writable` or `Could not save` line | `shots/L6b-retry-before-2nd.png` (cursor on the active row), `L6c`, `L6d` |

`switchSource` on the source that is already active answers `ok` rather than
`busy` (harness `D-LIVE-20` block), and `Model.barEntryWritable` keeps a real
persist failure real: with `updateEntryInline` off the shell api the harness
still gets `persist_failed` and the SR25 copy (P6).

**D-LIVE-20: verified fixed.**

### P3. D-LIVE-21, original repro

Repro as filed: two or more sources, A active; Sources, `x` on A, confirm
`Remove`; `Esc` back to the guide.

| | Was (ec4f702) | Now (845d445) |
|---|---|---|
| after confirming | `Removed <label> - no active source`, then `Loading playlist... / Fetching from <the removed source's host>` for 18+ s with `configured true` and `status loading` | `configured` **false after 821 ms**, `status ready`, `channels 0`, `activeSource null`; the removed source's cache dir is gone and the other two are intact |
| `Esc` behind the screen | never left the loading state | the **first-run setup surface**: `No playlist configured`, the `Playlist` / `EPG` fields, the `Saved sources (1)` link, `Use Xtream login instead`, `Load`, the `omarchy bar set ...` hint, footer transient `Removed qa-src-a.m3u - no active source` and hints `Enter load - Tab next field - Ctrl+V paste - Esc close` |

Evidence `shots/L8a-before-remove-active.png`, `L8b-confirm-active.png`
(dialog `Remove "qa-src-a.m3u"? It is the active source...`),
`L8c-after-confirm.png`, `L8d-setup-surface.png`. The header shows the
`Search channels...` placeholder, not a stale query (D-SRC-05 still fixed).

Removal of a **non-active** source (SRC-RM-01) also passes: dialog
`Remove "qa-src-b.m3u"? Its cache is deleted too.` with
`Left/Right choose - Enter confirm - Esc cancel`, `Enter` removes the row and
its cache dir `3574b78e`, the active source and the other two records are
untouched. Method note: `Remove` is the dialog's default choice, so one
`Right` from it selects `Cancel`; the previous pass's `Left`, `Right`,
`Return` sequence happens to land back on `Remove`, a bare `Right`, `Return`
cancels (`shots/L7b-confirm-dialog.png`).

**D-LIVE-21: verified fixed.**

### P4. Echo idempotence and external writes (the fix's own risk surface)

The fix lays the plugin's own write over the host's value until the host
reports anything else. The three ways that can go wrong were driven live.

| Case | Method | Result |
|---|---|---|
| External write reconciles with the guide open | Sources open, `omarchy bar set io.github.rmcdavid.iptv playlistUrl <local fixture>` from a terminal | reconciled in **636 ms**; the history gained a record with `origin: "cli"`, label derived `qa-src-a.m3u`, 8 channels; `epgUrl` stayed `""` (D-SRC-10 still fixed); `shell.json` stayed `0600` |
| A plugin-side switch still wins afterwards | `Enter` on the `iptv-org` row right after that CLI write | switched in **224 ms**, `shell.json` rewritten to the US URL |
| Override dropped too late | external write 50 ms / 300 ms / ~0 ms after a plugin-side switch keystroke | in all three the **external value wins** and the guide settles on it; `qs log` shows the plugin's own switch really happened first (the 8-channel `switch` lines 12, 13, 14), so the override is dropped by the foreign publish rather than outliving it. No stuck state, no error, `shell.json` consistent each time |
| Override dropped too early / double apply | `omarchy bar set` of **the identical value the plugin had just written** (the host catching up with our own write) | **0** extra `switch` events, **0** helper runs, no state change, no duplicate history record: the echo is a no-op |

`shots/L9a-cli-reconciled.png`, `L9b`, `L10a..L10d`.

### P5. Regression sample on 845d445

All through the dev harness with the qa5 methods re-pointed at this root
(`h20`, `h21`, `h15`, `static`, plus the scripted `run.sh scenario`), and a
live sample on the real shell.

| Block | Cases | Result |
|---|---|---|
| `run.sh scenario` (Sources end to end) | 61 checks: H1 migration, H5 add failure, H2 add + probe, H6/H8 switch + 10k timing, the D-LIVE-20 block, external writes, probe cancel, H9 CLI parity, H11 duplicate, H12 label/EPG edits, H7 remove active + D-LIVE-21, SR25 `failPersist`, privacy greps | **61 pass / 0 fail** |
| `h20` M1 sample | BRW 05, 06, 07, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 21, 22; FAV 01-07; EPG 01-03; PLAY 01, 02, 04, 05, 06, 10; RFR 01, 03, 04, 07, 08, 09; UI 01, 02, 03, 09, 10, 13 + TC-CFG-04; PERF 01, 02, 03, 07 | pass. `diff` against the d50e364 transcript is timestamps and PIDs only, except the two items below |
| `h21` clean re-run | EPG 01-04, RFR 01, 03, 04, 07, 08, 09, 10, BRW-17, PERF-07 | pass; the only content difference from d50e364 is the new EPG warning footer (O18) |
| `h15` helper key safety | SRC-SEC-08, SRC-SEC-23, SRC-RM-07, SRC-MIG-09, SRC-HELP-05..08, SRC-PERF-07 | identical to the d50e364 transcript apart from paths and stamps |
| `static` greps | SRC-UI-12/13/14/15, SRC-KEY-12, SRC-SEC-12/13, SRC-A11Y-01/05, SRC-PRIV-09 | identical apart from line-number shifts; **O11 is closed** (UX.md now says `r retry`) **(2026-09-15: SRC-A11Y-01 and SRC-A11Y-05 are retracted from this row. "Identical apart from line-number shifts" is true and was never evidence about accessibility: both greps matched source written to contain the strings. The remaining ids in this row are unaffected.)** |
| live sample | guide open/close, search `bloomberg` -> `in All - 5 matches`, `Esc` clears, `Tab` list mode, group column, `f` / `f` favourite and unfavourite (`state.json` `[]` again), `r` refresh (`lastUpdated` 21:41 -> 23:03, 1,474 channels), theme `tokyo-night` and back with Sources open (SRC-UI-19), restart with a non-default source active | pass, `shots/L13*`, `L14*`, `L15a` |

Two `h20` lines needed a follow-up rather than reading as regressions:

- **PLAY-02 window reuse** printed `same: no` because the step activates a
  channel whose stream URL is the fixture's dead `127.0.0.1:9`, and mpv had
  already exited by the 2.5 s check (on d50e364 the same sample caught it
  still alive). Re-run in isolation against the served channel
  (`play2.sh`): the second activate **reuses the same mpv pid**, PLAY-02
  passes. The dead-stream path itself is correct - `lastError` `Failed to
  open 127.0.0.1`, mpv reaped, `playing false`, and the notification
  `Stream failed` / `"BBC One HD" did not play - Failed to open 127.0.0.1`
  fires (it landed in the qa5 log until the shim's hardcoded path was
  fixed mid-pass).
- **`epg.warnings` and the `Guide data warning:` footer** are new since
  d50e364 (`cf22c3f`), not a regression: see O18.

**D-LIVE-19 verified fixed** as a by-product (`d19.sh`): `omarchy bar set
... playlistUrl ""` at runtime now clears the list with the setting (`rows 0`,
`showColumn false`, `mode sourceEdit`, `emptyKind unconfigured`,
`form.origin firstRun`), survives close/reopen, and setting the URL again
reloads from cache with the same `updated` stamp (no refetch).

Counts: **61 / 61** scenario checks and **69** re-run SRC and M1 cases across
browse, play, favorites, EPG, refresh, UI, security and the Sources flows
(`h20` 48, `h21` 2 more, `h15` 9, `static` 10), plus the live blocks of P2, P3,
P4, P7 and P9 - add, six switches, the retry path, both removals, four
external-write cases, the privacy sweep, the theme re-skin, a restart and the
live browse / favourites / refresh sample. **0 regressions**, 0 reopened
defects, 1 new P3-class observation (O18, from the cosmetics lane, not from
the P1 fix).

### P6. Harness fidelity, measured independently

The fix lane claims the corrected fake host catches the defect. Measured by
checking the **pre-fix** `Service.qml` (`d153fe9`) into a scratch copy of
`845d445` (`E/prefix-tree/`, everything else - `Model.js`, `Guide.qml`,
`shell.qml`, `sources-scenario.sh` - identical to `845d445`) and running the
same scenario in both trees. `main` was not touched.

| Tree | `Service.qml` | Result |
|---|---|---|
| `/home/ricky/Projects/omarchy-iptv` | `845d445` (fixed) | **61 passed, 0 failed** |
| `E/prefix-tree` | `d153fe9` (pre-fix), corrected harness | **44 passed, 23 failed** |

The 23 failures are 17 named `check` lines and 6 `bad` lines from timed-out waits;
they cluster exactly where the live defects were: H2 (`new source active,
channels loaded`, `activeCache() switched`), H6/H8 (`median 10k switch under
150 ms (no samples)`), the whole `D-LIVE-20` block including
`the host has published only the PREVIOUS bar (the defect shape)`,
`no sourcesPersistFailed anywhere in the switch sequence` and
`the host echoing our own value back changes nothing (idempotent)`, H7
(`the guide left the loading state at once (D-LIVE-21)`,
`settings were not cleared`) and the SR25 block. One line in that list,
`the switch took effect at once, with no echo from the host`, passes in the
pre-fix run only because the earlier failures had left that source active
already - a scenario artefact, not a pre-fix success.

The claim holds: the corrected fake reproduces the host's one-write-behind
plumbing and fails against the code that was broken in the field.

### P7. Performance

Harness numbers with the qa5 method; live numbers from the `omarchy-iptv
switch <ms>` lines in `qs log` (first time these are measurable on a real
shell - the previous pass had no completed switch to time).

| Item | d50e364 (harness) | ec4f702 (live) | 845d445 | Method |
|---|---|---|---|---|
| Switch redraw, 10k warm (5 switches) | median 19 ms, max 329 | -- | **median 10 ms, max 14** (harness) | scenario `omarchy-iptv switch` lines |
| Switch redraw, 10k -> 20 channels | median 14, max 16 | -- | **median 4, max 7** (harness) | same |
| Switch redraw, live, 5-8 channel source | -- | **not measurable** (no switch completed) | **median 59 ms, max 87** (n=11) | `qs log`, `OMARCHY_IPTV_DEBUG=1` |
| Switch redraw, live, 1,474 channels | -- | not measurable | **73 / 116 / 147 ms** (read 65-94, prepare 51-52) | same |
| Switch wall clock, live (keystroke -> `status`) | -- | never arrived (20+ s, no error) | **145-168 ms** small, **224-240 ms** at 1,474 | `date +%s%N` around the `wtype` Return, 48 ms IPC round trip included |
| Add -> the new source is active (live) | -- | never | **723 / 516 ms** | same |
| Remove the active source -> `configured false` (live) | -- | 18+ s, never | **821 ms** | same |
| External `omarchy bar set` -> reconciled (live) | -- | the only recovery path | **636 ms** | same |
| Guide open, live, 1,474 channels | -- | not recorded (grim round trip dominated) | **toggle 52-59 ms** against a 48 ms `shell ping` baseline; **layer visible 69-75 ms** | `omarchy-shell shell toggle` wall time; `hyprctl layers` busy-poll |
| Guide open, harness 10k cache (PERF-02) | median 73, max 77 | -- | **median 67, max 79** (`state` baseline 75 / 91) | `h20` |
| Helper `playlist` 10k | 483 / 482 ms, wall 0.62 s, maxrss 38 MB, `channels.json` 2,612,025 B | -- | **457-468 ms, wall 0.58-0.60 s, 38 MB, 2,612,025 B** | python `resource` wrapper (`/usr/bin/time` is absent on this machine) |
| Helper `playlist`, live 1,474-channel URL | -- | -- | **312 / 356 ms, wall 0.45 / 0.53 s**, 437,554 B | same, shipped helper from the installed clone |
| 20 keystrokes on the 10k list (PERF-03) | 681 ms | -- | **671 ms**, all registered | `h20` |
| Quickshell RSS after the `h20` run | 397 MB | -- | **396 MB** | `ps -o rss=` |

Every budget of QA-SOURCES.md section 5 holds, on the harness and now on the
live shell: the 150 ms switch budget is met at 1,474 channels (147 ms worst
case, median 116) and the guide open budget with room to spare. No measurable
cost from the fix: the `ownWrite` override is one object comparison per
settings change.

### P8. Gate tails

```
== python3 -m unittest discover -s tests
Ran 199 tests in 22.768s
OK
ok   python tests
== qmltestrunner tests/Model.spec.qml
ok   qml spec (33 passed)
== ascii check (code files)
ok   ascii check
check.sh: all green
```
`node tests/Model.test.js`: `681 checks, 0 failure(s)` / `All Model.js tests
passed.` (653 on d50e364; the 28 new ones are the `ownWrite` / `barEntryWritable`
vectors, including `a bare-string entry is NOT writable` and
`an object entry with our id is writable`). `omarchy plugin validate .` exit 0
with no output, and `omarchy plugin validate` on the **installed** clone at
`845d445` also exit 0.

### P9. Privacy verdict

`h13` repeated on the live machine with a credentialed source
(`http://qa-user:qa-secret@127.0.0.1:8791/qa-src-b.m3u`, served from a
loopback `python3 -m http.server` started and killed by recorded PID), made
active, switched away from and back to through the Sources screen (so the
credential goes through the new `persistActive` / `ownWrite` path), plus a
failed add of `http://qa-user:qa-secret@127.0.0.1:9/x.m3u` and an edit-form
reveal.

| Sink | `qa-user` / `qa-secret` / `cu:cs` hits | `://` |
|---|---|---|
| `omarchy-shell io.github.rmcdavid.iptv status` | 0 | 0 |
| `qs log -p /usr/share/omarchy/shell --tail 800` | 0 | 0 on any `omarchy-iptv` line |
| `journalctl --user` over the whole pass | 0 | 0 on any `omarchy-iptv` line |
| `omarchy-shell notifications showHistory` | 0 | -- |
| helper `bin/omarchy-iptv state show` | 0 | 0 |
| `omarchy bar get io.github.rmcdavid.iptv` | 0 | -- |
| Sources row, detail, footer transient, label | 0 (all render `127.0.0.1:8791`) | -- |
| the screenshots taken while the credentialed source was configured | 1, and only `shots/L12e-edit-revealed.png`, the deliberate `Ctrl+R` reveal | -- |

Expected hits only where the design stores them: `state.json` (1) and
`shell.json` (1), both `0600`; no `channels.json` hit at all for this
fixture. The add form masks at paste time
(`http://****@127.0.0.1:8791/qa-src-b.m3u` with the eye button,
`shots/L11a-cred-masked.png`) and `Ctrl+R` flips the hints to `Ctrl+R hide`.
All cache dirs `700`, all cache files `600`, across adds, switches, removals
and two restarts. The new `ownWrite` record holds raw URLs in memory only and
reaches no sink. Verdict: **clean**.

### P10. Observations

- **O18 (new, P3, from the cosmetics lane not the P1 fix).** When the EPG
  helper reports a warning and the playlist is also serving a stale cached
  copy after a failed refresh, the footer shows
  `Guide data warning: 1 programmes for channels not in the playlist dropped`
  **instead of** `8 channels - cached 22:49 - offline`:
  `Model.footerStatus` ranks `warning` above the count line, and the
  `cached HH:MM - offline` marker lives in that count line. UX.md's new
  precedence note says warnings "must never hide a failure"; the failure is
  still visible - the banner reads `Playlist refresh failed (Connection
  refused) - showing cached copy from 22:49 - r retry` and `bannerKind` is
  `playlistError` - so this is a footer-detail loss, not a hidden failure.
  Reproduced in `h21` and `d19.sh` (`logs/d19.txt`), pre-dates the P1 fix.
- **O19.** A bar entry the host cannot rewrite (a bare string
  `"io.github.rmcdavid.iptv"` in the layout) leaves the plugin with no
  settings at all, so it renders the first-run surface and the Sources switch
  path is not reachable from there. That is pre-existing M1 behaviour
  (settings come from the entry) and needs a hand-edited `shell.json`; the
  plugin wrote nothing and left `shell.json` untouched. The persist-failure
  signalling itself (`Could not save settings - try omarchy bar set`, SR25)
  is covered by the harness `failPersist` block, which passes.
- **O16 does not recur this pass**: no refetch of the upstream list was
  forced, `channelCount` stayed 1,474 and the cache is byte-identical to the
  snapshot.
- **O10** (mpv ignoring SIGTERM) did not appear: `h20` logged no
  `mpv ignored SIGTERM, sending SIGKILL` line this run (d50e364 logged one),
  and every live stop reaped mpv.
- **O11 is closed** by `48dd054`: `docs/UX.md` now says `r retry - o sources
  - Esc close`.
- O2..O9 and O12..O15 were not re-checked except through the transcripts
  above, which reproduce them unchanged.
- One mpv process unrelated to this plugin
  (`mpv --no-config --idle=yes ... --input-ipc-server=/tmp/pk-missing-306717/nodir/mpv.sock`,
  pid 306721, started 22:38:34, parent `systemd --user`) was **already
  running at snapshot time** and is recorded in
  `snapshot/status.before.json` under `preexistingMpv`. It is not the
  plugin's (the plugin's socket is `$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock`),
  nothing in this repo spawns that path, and this pass left it alone.

### P11. Still blocked on this machine

Unchanged from the ec4f702 pass and not re-attempted: SRC-KEY-11 (mouse - no
pointer-injection tool, `sudo` forbidden), SRC-LST-09 / SRC-UI-20 (the card
cannot go under the 720 px threshold at 1366x768 @ 1 and `hyprctl keyword` is
refused by the Lua config parser), SRC-A11Y-04 (single display), and the
`SUPER + SHIFT + T` keybinding itself (`wtype` cannot fire Hyprland global
binds; the bind is registered and its command works).

### P12. Restore

The machine was returned to its exact pre-pass state and proved
(`E/restore-proof.json` against `E/snapshot/status.before.json`):

- `~/.config/omarchy/shell.json` - **identical bytes** (sha
  `9a704ac6...68e6`), mode `600`;
- `~/.local/state/omarchy-iptv/state.json` - **identical bytes** (sha
  `a0f2506c...ff5`), mode `600`, and still identical 10 s after the restart
  (the service re-stamped `lastUsed` once on start; the snapshot file was
  written back and stayed);
- `~/.cache/omarchy-iptv/` - `diff -r` against the snapshot is empty; dirs
  `700`, files `600`;
- `omarchy-shell io.github.rmcdavid.iptv status` **diffs clean** against
  `status.before.json`: one source `d5977d8a` active, 1,474 channels in 28
  groups, `lastUpdated 21:41`, 5 recents, 0 favorites;
- installed clone back on `main` at `ec4f702` tracking `origin/main`, clean
  tree, `git status -sb` -> `## main...origin/main` with no ahead/behind
  (the sanctioned `git fetch origin` had advanced the remote-tracking ref to
  `210cfa3`; it was set back to `ec4f702` with `git update-ref`, which is what
  the snapshot held);
- shell relaunched through `omarchy restart shell`, so
  `OMARCHY_IPTV_DEBUG` is gone from its environment;
- guide closed (0 `omarchy-iptv` layers), no plugin mpv, port 8791 closed,
  clipboard restored, theme `Retropc`, harness scratch dirs wiped.

Everything this pass changed is listed in `E/live/UNDO.txt`.

### P13. Release recommendation

**Go for v0.2.1 at 845d445.** D-LIVE-20 and D-LIVE-21 are both verified fixed
on the live shell with their original repros; the fix's own risk surface
(echo idempotence, an external write racing a plugin-side switch, a real
persist failure) behaves correctly in all four variants driven; 0 open P1/P2;
0 regressions over 61 scenario checks, 69 re-run SRC and M1 cases and the live
blocks above; D-LIVE-19 closes as a by-product; performance is within every budget
and the switch path is measurably fast on a real shell for the first time;
the privacy sweep is clean with a credentialed source; gates green. The
corrected harness is now load-bearing - it fails 23 checks against the
pre-fix service that the old fake passed. One new P3-class observation (O18,
a footer-precedence detail from the cosmetics lane) does not block the
hotfix and belongs in the M1.2 cosmetics queue with D-LIVE-19's neighbours.

## M2-02 player pass on 8f9447e (QA, 2026-09-14, 01:53 - 02:57)

`docs/QA-PLAYER.md` v0.2 executed against `main` at `8f9447e` (fix lane
`c458ebf` plus three doc commits), on the reference machine, with the display
held by this lane for the whole pass. Evidence root
`/tmp/claude-1000/omarchy-iptv-qa7/`. The lead's explicit go-ahead covered
`pkill -KILL` of the shell and the player, `omarchy plugin disable` /
`remove` with a reinstall, and a logout; the logout was **skipped on the
lead's own condition** (it would end the terminal session this pass is
running inside, which is work that is not mine) and PLY-RST-10 is recorded on
its static half.

### M1. Gates at `8f9447e` (section 1.8, re-measured)

| Gate | `363ce9c` | `8f9447e` |
|---|---|---|
| `node tests/Model.test.js` | 857 checks | **885 checks, 0 failures** |
| `python3 -m unittest discover -s tests` | 247 | **247 tests, OK** |
| `tests/test_player.py` alone | 41 | **41** |
| `qmltestrunner -input tests/Model.spec.qml` | - | **42 passed, 0 failed** |
| `omarchy plugin validate .` | - | **exit 0** |

All 26 named automated tests the plan depends on exist and pass. The fix
lane's evidence is the 28 new node checks over `sessionAfterOutcome` and its
twelve call sites.

**Harness, CLAUDE.md rule 11.** `player-scenario.sh` (PLY-H01..H10):
**49 pass / 0 fail at `8f9447e`**, and **33 pass / 16 fail** against the last
pre-M2-02 commit `5e90283`. Every check the script's header names as
must-fail (P2, P3, P4, P5, P6, P8, P10) fails there. The scenarios are
evidence for this milestone, not regression guards.

### M2. Counts

129 `PLY-*` cases (section 1.1 plus `PLY-FIX-01`).

| Result | Count |
|---|---|
| pass | 96 |
| **fail** | **5** (3 defects: D-PLY-1 accounts for 3 rows) |
| pass with a corrected expectation (section 14) | 6 |
| blocked (no pointer tool; logout would end this session) | 6 |
| not run (time, or section 10) | 16 |

By area: RST 15 pass / 2 fail / 3 not run; LIFE 9 / 1 / 4; STOP 11 / 0 / 0;
FAIL 9 / 0 / 3; SOCK 10 / 1 / 0; WEAK 8 / 1 / 1; SEC 17 / 1 / 0; PERF 6 / 1 /
0; MIG 1 / 0 / 2; MODEL 6 / 0 / 0; HELP 8 / 0 / 0; SVC 8 / 0 / 0; FIX 1 / 0 / 0.

### M3. The central case: playback survives a shell restart

**PLY-RST-01 passes, six clean runs.** Every run: the **same mpv pid and the
same `/proc/<pid>/stat` field 22 start time**, `hyprctl clients` sampled every
100 ms showing exactly `1` at every sample, `time-pos` advancing monotonically
across the restart (no reload), and `status.nowPlaying` identical before and
after including **`launchedFrom`**, the pure-UI field no mpv property knows.

A seventh run is recorded as void, not failed: the 120 s fixture reached its
natural end mid-restart. That accident produced clean **PO-4 evidence**
(PLY-FAIL-06): a real end-of-stream left `playing false`, `nowPlaying null`,
`failedAt {}`, `session` cleared and **zero notifications**. The fixture is
now 900 s.

| Variant | Result |
|---|---|
| PLY-RST-02 mid-zap at 0 / 100 / 300 / 600 ms | **pass**, four runs: one player, one window at every sample, `nowPlaying` always equal to the window title, never a third state |
| PLY-RST-03 restart while failing | **pass** on the notification half (exactly one toast in total, **zero** added by the restart); `failedAt` clause corrected, see section 14 item 5 |
| PLY-RST-05 the shell is SIGKILLed | **pass**, and the strongest result in the pass: no `onDestruction`, no orphan-check, no graceful anything; `time-pos` still advancing 3 s later, one window, and the supervisor's relaunch reattached to the same pid with identical identity |
| PLY-RST-06 socket removed underneath | **FAIL** - the live observer survives the unlink as the spike says, and exactly one player exists at all 40 samples, but the shell ends **idle while the respawned player plays**. D-PLY-1 |
| PLY-RST-07 wedged across a restart | **pass**, laddered down, interface correct |
| PLY-RST-11 hand-started foreign player | **pass**: `player probe` reports only ours, our stop leaves the foreign pid alive, our start spawns exactly one. Focus consequence **not run** (section 14 item 7) |
| PLY-RST-15 different active source | **pass**: same pid, bar keeps the stashed name, and the zap ring is **empty rather than wrong** (`next` was a no-op) |
| PLY-RST-17 the dying shell's orphan-check | **pass**, no-op, player alive at t+12 s |
| PLY-RST-19 theme change and rescan | **pass**, same pid through `tokyo-night`, back to `Retropc`, and `rescanPlugins` |
| PLY-RST-20 ten restarts in a row | **pass**: same pid and start time for all ten, one window at every sample, `launchedFrom` intact |

### M4. The two weakened behaviours

**PO-2.** PLY-WEAK-01, the PO's named acceptance gate, **passes**:
`omarchy plugin disable` with a channel playing stopped the player in
**6676 ms** (6 s grace plus the quit rung), window gone, socket unlinked.
PLY-WEAK-02, `omarchy plugin remove --yes`, **fails**: the player was still
alive and windowed at 45 s (D-PLY-2). PLY-WEAK-04's disclosed residual
reproduces and is **recorded, not filed**. PLY-WEAK-05 **passes**: the
README's command, run verbatim with **no shell running at all**, stopped an
orphan in **220 ms** on the quit rung.

**PO-3.** PLY-WEAK-06, the full procedure, run three times end to end
(play -> `kill -KILL` the shell and its supervisor -> `kill -9` mpv with
nobody listening -> relaunch): the channel is marked in `failedAt` with an
`HH:MM` value, **zero** notifications are raised, `state.json` stays `0600`.
The guide half is proven by screenshot (`shots/guide-failed-row.png`): the row
carries the **alert glyph U+F0026** in the trail slot and the detail line
`QA - Failed 02:44 - Space to retry` - **not a red row**, settling section 11
item 6. Two of the three runs left `session` on disk instead of clearing it,
so the mark is re-applied once on the following start (D-PLY-3). PLY-WEAK-07
and 08 pass: a restart with `session` null marks nothing and leaves
`state.json` byte-identical.

### M5. The startup state race (ARCH-P section 15)

**It reproduces. 14 losses in 30 trials - 47%.**

Method (`race-trial.sh`): with nothing playing and no session record, restart
the shell and fire `play` into the successor's IPC from the earliest instant
it will accept one, then ask whether `state.json.session` still names the
channel that is demonstrably playing. The play landed on the 3rd or 4th
attempt in all 30 trials, so the window being probed is the real one.

| Verdict | Trials |
|---|---|
| WON (record survived) | 16 |
| **LOST (record overwritten by the arriving state file)** | **14** |

Every loss has the same shape: `playing true`, `nowPlaying` correct, window
mapped - and `session` **null**. The consequence was then proven end to end:
after a lost race, the stream was killed with no shell attached and the
reattaching shell marked **nothing** (`failedAt {}`) and raised no toast. PO-3
is silently unavailable for roughly half of the plays issued at shell start.
Not fixed here, per the lead's instruction. D-PLY-4.

### M6. Security and privacy

**The narrowed `ps` claim holds, verified rather than assumed.**

- **PLY-SEC-01/02 pass.** The launch argv is `mpv --input-ipc-server=... --wayland-app-id=omarchy-iptv --force-window=immediate --idle=once --keep-open=no --title=$>IPTV --force-media-title=IPTV --msg-level=all=error --ytdl=no` - 0 needles, no `://`, **no trailing `--`**, every token after index 0 begins with `--`, and **byte-identical after ten zaps** across channels with and without headers.
- **PLY-SEC-04 pass.** The sentinel's `qa-ua-SENTINEL` and referrer reached mpv **only over the socket** (read back live off the IPC) and were **cleared** on the headerless channel (`user-agent` back to `libmpv`) and re-applied on the next. Requirement 7 confirmed on a live player for the first time.
- **PLY-SEC-03 pass.** 241,675 process samples over 300 s (~1,064 full `/proc` sweeps, ~282 ms per sweep). Raw needle count 149; **every one was the QA driver's own `bash -c` carrying the needles inside its grep pattern**. Plugin-originated needles: **0**. Helper argv seen carries only `--socket --cache-dir --id --seq --scope --since --owner-pid`.
- **PLY-SEC-05, the measurement.** The `--id t:<tvg-id>` exposure was caught **2 times in ~1,064 sweeps**. `omarchy-notification-send`'s argv was caught **0 times in ~1,424 targeted samples** across two real failures - so the channel name's window is narrower still; it is confirmed by construction in `Model.notifyArgv`. The **window title**, which also names the channel and is readable from `hyprctl clients -j` for the entire play, is by far the larger exposure of the three. Both README-named residuals are real and nothing else joins them.
- **PLY-SEC-07 pass.** `700` dir, `600` socket, `600` lock, `600` state; lock content is one line of schema/seq/verb/at with no URL; no `player.json`, no log file, no watch-later file, no unit.
- **PLY-SEC-09/10/11/12 pass.** 0 needles in the journal, the console, `status` or any notification body; `grep -c 'mpv\['` in the journal is **0**. Failure bodies read `"QA Dead Channel" did not play - [stream] Failed to open 127.0.0.1` - host only, typographic quotes, U+00B7, `-r 74011`, urgency normal, glyph U+F0503, all read off the session bus.
- **PLY-SEC-13/15/16/17 pass.** Ten reserved additions present in both Model.js and the helper; no sudo, no `shell=True`, no `bash -c`, no `eval(`; stdlib only with `fcntl`, `signal`, `errno` added; `git status` in the plugin dir is empty after the pass.
- **PLY-SEC-18 pass.** `title` stores `$>${path}` byte-identically, the window shows the literal `${path}`, `force-media-title` carries the plain name without the prefix, the leading dash is stripped (`-u critical ${path}` -> `u critical ${path}`), and a non-ASCII name round-trips through `user-data` intact.
- **PLY-SEC-14 FAILS.** D-PLY-5.

### M7. Performance

| Budget | Measured | Verdict |
|---|---|---|
| reattach `nowPlaying` <= 2000 ms after the shell answers | median **491**, max **1726** (n=8) | pass |
| `player.attached` <= 3000 ms | median **648**, max **1930** | pass |
| `player probe` <= 400 ms | median **160**, max **161** | pass |
| helper verb <= 300 ms | probe 156-161, status 149-158 | pass |
| stop clears the interface <= 150 ms | 113 / 115 / 116 / 118 / 118 (keyboard `s`: 393 ms to the process end) | pass |
| responsive player gone <= 500 ms | 273 / 327 / 329 / 331 / 331 | pass |
| **wedged player gone <= 4500 ms** | **6258 / 6265 / 6269 / 6276** | **fail, D-PLY-6** |
| zap to first frame < 2000 ms | cold **630**, warm 241-397 (median 270) | pass |
| journal <= 12 socket WARN per player death | **~3** per death; 33 over eleven deaths plus a 30 s dead window | pass |
| guide open < 150 ms | **68-77 ms** on the user's 1,474-channel list (ping baseline 52-54) | pass |
| no leak over ten restarts | mpv fds 65/65/65, mpv RSS +320 KB, shell RSS 314 -> 307 MB, runtime dir unchanged | pass |
| PLY-SOCK-11 socket churn | shell fds **104 -> 104** over ten player deaths, +17 CPU ticks over a 30 s dead window, RSS flat, `player.wanted` correctly false | pass |

The 30-minute idle journal row is **not run**; it is substituted by the direct
measurement that `playerWanted` goes false on a player death and that an idle
restart adds **0** socket WARN lines.

### M8. Defects (rows in docs/STATUS.md)

#### D-PLY-1 (PLY-LIFE-12, PLY-RST-06, PLY-SOCK-01)  P1  found 2026-09-14 at 8f9447e

**The interface goes idle while the player keeps playing, after any
helper-driven ladder-and-respawn.**

Steps, trigger A (the health check), 3/3 reproductions:
1. Play a channel. 2. `kill -STOP <mpv pid>`. 3. Wait ~21 s for the two-strike
verdict; the journal logs `omarchy-iptv: mpv unresponsive, restarting player`
and `player restart --from term` runs.

Steps, trigger B (the socket-unlink recovery, PLY-RST-06), 2/2:
1. Play a channel. 2. `rm "$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock"`.
3. Play another channel; the helper finds the old player unreachable, ladders
it down and spawns a new one.

Expected (ARCH-P 4.5, requirement 11, PLY-LIFE-12): exactly one relaunch and
the bar and guide keep accurate now-playing state.

Actual, both triggers: the relaunched player **is playing** - `idle-active`
false, `path` the real stream, window mapped and titled with the channel, its
`user-data/omarchy-iptv` stash reading `playing:true` with the right id - and
the shell reports `playing false`, `nowPlaying null`, `player.up false`,
`player.attached false`, **`player.wanted false`**. Because `wanted` is false
the 250 ms retry timer is off, so it never reattaches: measured unchanged at
15 s and at 30 s. Exactly one player exists throughout (40-48 samples at
100-250 ms), so this is not a two-window defect.

Recovery: `stop` still reaches it (the helper connects by path) and a shell
restart reattaches to the same pid and restores the correct state - but the
user has no reason to press stop, because the interface already says stopped.

Severity: the plan's own P1 list, verbatim - "the interface goes idle while
the player keeps playing".

Evidence: `logs/`, and the journal lines above.
Notes: suspected `applyProbe` / the `player restart --from term` reply path in
`Service.qml` not re-arming `playerWanted` after a relaunch it issued itself.

#### D-PLY-2 (PLY-WEAK-02)  P2  found 2026-09-14 at 8f9447e

**`omarchy plugin remove` while playing leaves the player running and deletes
the only non-destructive way to stop it.**

Steps: play a channel, `omarchy plugin remove io.github.rmcdavid.iptv --yes`.

Expected (PO-2, ARCH-P section 12 and 3.1's claim table): the claim still
names a live shell pid, so `player orphan-check` runs `player stop`; window
gone within ~7 s, as `disable` does (measured 6676 ms).

Actual: the player is alive and windowed at **21 s and still at 45 s**.
`remove` deletes the plugin directory, and the orphan-check is
`python3 <plugindir>/bin/omarchy-iptv player orphan-check ...` launched at
`Component.onDestruction`, so there is nothing left to exec. Worse, the
README's escape hatch -
`~/.config/omarchy/plugins/io.github.rmcdavid.iptv/bin/omarchy-iptv player stop` -
**lives in the directory that was just deleted** and cannot be run either; the
sentence naming it is in the same bullet that names removal. Restoring the
directory from a backup made the command work again and it reaped the orphan
at once.

Severity: P2 by the letter of the plan's table, because logging out remains a
documented means. **The lead may reasonably call this P1**: both halves of
PO-2's compensating control fail together, in one of the two cases PO-2 names,
and the only remedy that does not end the user's session is destroyed by the
action that creates the problem.

#### D-PLY-3 (PLY-WEAK-06 step 6, PLY-FIX-01)  P2  found 2026-09-14 at 8f9447e

**The PO-3 record is not always retired when it is consumed, so the mark is
raised twice.**

Steps: the PLY-WEAK-06 procedure. Observed in 2 of 3 runs.

Expected (section 3.2 step 6, `deadSessionVerdict`'s `write` gate):
`jq .session state.json` is `null` after the mark.

Actual: the mark lands correctly and silently, but `session` is still on disk
afterwards. The following shell start consumes it again - the same channel is
re-marked with the **same** `HH:MM` - and only then is it cleared; a third
start is clean. This is exactly the second-verdict-on-an-event-already-dealt-with
that the fix lane's own comment says it closed, surviving in the deferred
drain path (`applyUserState` -> `markDeadSession`) rather than in the twelve
branches `c458ebf` routed.

Notes: suspected the write racing `stateFile`'s own load, the same handler as
D-PLY-4; `saveState()`'s `dirsReady` deferral is the other candidate.

#### D-PLY-4 (ARCH-P section 15 gate)  P2  found 2026-09-14 at 8f9447e

**The known startup race reproduces, 14 losses in 30 trials (47%).** Full
method and consequence in M5. Filed as a defect row so it is tracked; the lead
owns the fix decision and asked QA not to fix it.

#### D-PLY-5 (PLY-SEC-14, PO-5)  P2  found 2026-09-14 at 8f9447e

**PO-5's required README sentence is absent, and the cost it was meant to name
is real and reproducible.**

`ytdl`, `yt-dlp` and `youtube` appear **0 times** in `README.md` and 0 times
in `CHANGELOG.md` (verified with `/usr/bin/grep` and python; see section 14
item 4). With `omarchy bar set io.github.rmcdavid.iptv mpvArgs '--ytdl=yes'`
- a documented setting - and a stream that fails to open, mpv's `ytdl_hook`
spawned, caught live in a `/proc` sweep:

```
/usr/bin/python /usr/bin/yt-dlp --no-warnings -J --flat-playlist ... -- http://qa-user:qa-secret@127.0.0.1:9/live/qa-token-XYZ/dead.ts
```

The **full credentialed URL**, on another process's `0444` command line, for
seconds rather than milliseconds (99 sweep samples caught it). The default is
`--ytdl=no` and `ps aux` is clean there, so this is opt-in - but the README's
headline sentence, "No stream address, credential or header value ever
reaches any command line", has an unstated exception the README itself
documents how to enable. Suggested: one sentence next to the `mpvArgs` row and
in the 0.3.0 `Known limitations`.

#### D-PLY-6 (PLY-PERF-02, PLY-STOP-03)  P3  found 2026-09-14 at 8f9447e

**A wedged player takes ~6.27 s to reap, not the budgeted 4.5 s.** Measured
6258 / 6265 / 6269 / 6276 ms across four runs, deterministic. The ladder is
quit@0, TERM@2.0, KILL@4.0, settle@4.5, but against an unresponsive player the
quit rung first spends the full `--ipc-timeout` 2.0 s, which the budget does
not account for. The player **is** reaped and the interface clears in 52-59 ms.
README says "within about four seconds". Either the budget and the prose move
to about six and a half seconds, or the quit rung skips the wait when the
probe already said `responsive:false`.

#### D-PLY-7 (PLY-SEC-07)  P3  found 2026-09-14 at 8f9447e

**The player can write a durable file outside the documented list, into
`$HOME`.** mpv inherits the shell's working directory (`/home/ricky`) and its
default key bindings are live on the focused window, so `s` on the player
writes `~/mpv-shot0001.jpg` (mode 0644) - a durable image of what was being
watched, in a directory README `Files it writes` says nothing about. Found by
accident when a keystroke intended for the guide reached the player. The
milestone already reserves `--screenshot-template` against durable exposure;
the default template is not covered. Suggested: spawn with `--screenshot-dir`
under the runtime directory, or name it in `Files it writes`.

### M9. Observations, recorded not filed

1. **PLY-WEAK-04's residual reproduces**: a SIGKILLed shell that never returns leaves the player running (held 30 s, window up). Named and accepted in PO-2; `KillMode=control-group` reaps it at session end.
2. **A zap onto a dead channel closes the window.** Under `--idle=once` a failed `loadfile` leaves mpv nothing to play and it exits; the next play spawns a fresh one. Correct by design, not stated anywhere outright. Section 14 item 8.
3. **mpv's fd 2 is an orphaned pipe** (PO-6's launch-window stderr). mpv ignores SIGPIPE, so writes return EPIPE harmlessly, and the journal carries 0 mpv lines.
4. **`failedAt` does not survive a restart.** README P3b's "the guide marks it until the channel plays again" is true within a shell's life only. Not filed; it is one sentence away from accurate and the user has already had the toast.
5. **A brief (<250 ms) overlap is possible during the socket-unlink respawn.** One one-shot check caught 2 pids on the socket token; two subsequent runs sampled at 250 ms (48 samples) and 100 ms (40 samples) saw `1` throughout, and no second **window** was ever observed.
6. **`omarchy-launch-shell` stops supervising after a plain SIGTERM** but relaunches immediately after a SIGKILL. Section 14 item 10.
7. **PO-7 confirmed**: `docs/STATUS.md` carries `M2-02x | Multiple playlists | superseded by M2-01 (PO-7)` and there is no `M2-09` row.
8. **The `stopSettleTimer` line is real**: the journal carries `omarchy-iptv: the player outlived a stop, re-reading its sequence`, ARCH-P section 14's own mechanism, observed firing.

### M10. Blocked and not run

- **PLY-RST-10 logout**: static half **passes** and is captured - `ExitType=main`, `KillMode=control-group`, `TimeoutStopUSec=10s`, `Linger=no`, and the mpv cgroup is byte-identical to the shell's `wayland-wm@hyprland.desktop.service`. The exercised half is **skipped on the lead's own condition**: a logout ends the terminal session this pass runs inside.
- **PLY-RST-09 suspend**: not run (section 10 item 4).
- **TC-BAR-07 right-click stop, TC-BAR-09 wheel zap, and the behavioural `launchedFrom` ring test**: **blocked**, no pointer-injection tool (section 10 item 2).
- **PLY-RST-11's focus consequence**: not run, section 14 item 7.
- **PLY-MIG-01**: not run (time).
- **PLY-H11, H12, H14, H15, H16**: authored and dry-verified; **PLY-H13 executed** and its first run exposed a fixture-port bug in the new script, now fixed (the harness serves on 8765, the committed fixture targets 8791) and re-run clean.

### M11. Deliverables authored by QA this pass

- `tests/fixtures/qa-player/` - `qa-player.m3u` (nine channels covering every section 8.0 requirement), `make-media.sh`, `README.md`, `.gitignore`. Media is generated, not committed.
- `scripts/qa-player-scenarios.sh` - PLY-H11..H16, **dry by default**, `--apply` to execute, `baseline <ref>` for rule 11, and a `refuse_real_dirs` guard plus a `scratch_player_pids` signal guard. Verified to refuse `~/.config/omarchy/plugins`, `$XDG_RUNTIME_DIR/omarchy-iptv` and `$HOME`.
- `docs/QA-PLAYER.md` corrected in place and section 14 added (twelve corrections).

### M12. Restore

Proved at 02:57:

- `~/.config/omarchy/shell.json` - **identical bytes**, sha `9a704ac6...68e6`;
- `~/.local/state/omarchy-iptv/state.json` - **identical bytes**, sha `a0f2506c...ff5`, mode `600`, still identical after a further restart and 25 s (the service re-added the QA source record on the first restart; the snapshot was written back a second time, as the M2-01 pass did);
- `~/.cache/omarchy-iptv/` - `diff -r` empty, modes identical;
- `status` **diffs clean** against `status.before.json` apart from `lastUpdated`: 1,474 channels, one source `d5977d8a` active on `iptv-org.github.io`, 5 recents, 0 favorites;
- installed clone back on **`main` at `a6bae85`**, `## main...origin/main`, 0 modified files. `origin/main` was never moved: the RC was fetched from the local repository into `FETCH_HEAD` instead of `git fetch origin`, which is less invasive than section 9.2 prescribes;
- theme **Retropc**; `$XDG_RUNTIME_DIR/omarchy-iptv` back to `700` and **empty**; 0 mpv, 0 `omarchy-iptv` windows, 0 guide layers; fixture server stopped and port 8791 closed; harness scratch trees wiped; `~/mpv-shot0001.jpg` (D-PLY-7's artifact, caused by this pass) removed.
- One pre-existing stray recorded and cleared at the **start** of the pass: an idle `mpv --no-config` from the 2026-09-13 harness run, 3 h 15 m old, socket directory already gone (`logs/pre-existing-stray.txt`).

### M13. Release recommendation

**No-go for v0.3.0.**

D-PLY-1 is a P1 by the milestone's own definition and it reproduces
deterministically from two independent triggers, one of them the automatic
health path that needs no user action at all. D-PLY-2 breaks PO-2's second
named acceptance case and takes the documented remedy with it. Both are in the
weakened-behaviour surface the PO accepted on the strength of exactly those
compensating controls.

Everything the milestone exists to do is otherwise proven and is worth saying
plainly: playback survives a shell restart with the same pid, the same start
time, one window and its full identity through ten consecutive restarts and
through a SIGKILLed shell; S-03 is closed on the first channel and stays
closed after ten zaps; the socket caveats C1-C10 are implemented exactly as
the spike prescribed and the reattach-after-death trap is unreproducible;
the superseded-stop regression is closed and the stop ladder completes with no
shell alive at all; every performance budget but one is met.

Re-run before the tag: PLY-LIFE-12, PLY-RST-06 and PLY-SOCK-01 for D-PLY-1;
PLY-WEAK-02 and PLY-WEAK-05 for D-PLY-2; PLY-SEC-14 for D-PLY-5; then
PLY-RST-01's six runs and the PO-3 procedure as the regression sample. The
ARCH-P 15 race (D-PLY-4) is the lead's call: it reproduces at 47%, so the
"fix only if it reproduces" gate is met.

## M2-02 fix verification on b16b479 (QA, 2026-09-14, 05:22 - 06:15)

Re-verification of the seven `D-PLY-*` defects filed by the pass on `8f9447e`,
against `main` at `b16b479` (`9941dce` for D-PLY-1/3/4/6, `5ea3d54` for
D-PLY-5/7, plus the ruling docs). Reference machine, display held by this lane
throughout. Evidence root `/tmp/claude-1000/omarchy-iptv-qa8/`. The lead's
go-ahead covered `pkill`, `omarchy plugin disable` / `remove` and a reinstall;
**no logout** (PLY-RST-10 stays on its static half, as at `8f9447e`).
`pgrep -x hyprlock` was checked before every keystroke and returned 0 every
time; the pass never ran with the screen locked.

Every number below is QA's own measurement. Where the fixing lane reported a
figure, it is named only to say whether QA's independent number agrees.

### V1. Gates at `b16b479`

| Gate | `8f9447e` | `b16b479` |
|---|---|---|
| `node tests/Model.test.js` | 885 checks | **954 checks, 0 failures** |
| `python3 -m unittest discover -s tests` | 247 | **260 tests, OK** |
| `test_player.py` alone | 41 | **54, OK** |
| `qmltestrunner -input tests/Model.spec.qml` | 42 | **47 passed, 0 failed** |
| `omarchy plugin validate .` | exit 0 | **exit 0** |

`qmltestrunner` is not on `PATH` on this machine; the runnable form is
`/usr/lib/qt6/bin/qmltestrunner`. `python3 -m unittest tests.test_player`
fails to import (`helper_loader` is not on `sys.path`); the runnable form is
`python3 -m unittest discover -s tests -p 'test_player.py'`. Neither is a
product defect; both are recorded so the next pass does not re-discover them.

**Harness, CLAUDE.md rule 11.** `player-scenario.sh` (P1..P14):
**75 pass / 0 fail at `b16b479`**, and **60 pass / 20 fail** against `396a69a`,
the tree the defects were filed against. Every check the header names as
must-fail for P11, P12, P13 and P14 fails there and passes here, so the four
new scenarios are evidence for these fixes and not merely green. One check
never ran at either ref - see **D-PLY-9**.

### V2. Verification per defect

| Defect | Verdict | QA's own evidence |
|---|---|---|
| **D-PLY-1** P1 | **FIXED** | Both original triggers, neither reproduces. Trigger A (`kill -STOP`, two-strike verdict) **3/3**: the wedged player is laddered down and replaced in 22.6 / 22.8 / 22.8 s, and the shell ends `playing true`, `nowPlaying t:qa.live`, `player.up/attached/wanted` **all true**, one player, one window, still true at t+30 s. Trigger B (socket unlink then zap) **2/2**: same end state on the channel asked for, one window at every 100 ms sample (60 samples; the count dips to 0 across the replacement, which PLY-RST-06 allows), socket re-created `600` in a `700` directory, old pid reaped. **The second half of the fix - "a delivered relaunch cancels its timer" - QA measured directly** by counting `omarchy-iptv: mpv unresponsive, restarting player` in the journal across each trigger-A run: **delta exactly 1 every time**, never 2. This is the check the harness silently skips (D-PLY-9), so it rests on QA's measurement alone. |
| **D-PLY-2** P2 | **CLOSED AS ACCEPTED (PO-8) - recovery verified** | The stranding reproduces and is accepted: `omarchy plugin remove --yes` with a channel playing leaves it alive and windowed at t+12 s and t+32 s, plugin directory gone. The README's recovery then works **exactly as written**. `disable` first stops the player in **6801 ms** ("about seven seconds"). For a stranded player, `pgrep -af -- '^mpv .*--wayland-app-id=omarchy-iptv'` returns **exactly one** line, ours; `pkill -f -- '^mpv .*--wayland-app-id=omarchy-iptv'` reaped it in **145 ms** and this session survived. **The anchor warning is literally true**: without the leading `^mpv `, the same pattern matches **3** processes including QA's own shell (pid confirmed by `$$`), i.e. the session pasting the command. Incidentally confirms the README's "Note on disabling": after `disable`/`enable` the widget's `playlistUrl` was gone and had to be re-set. |
| **D-PLY-3** P2 | **FIXED** | The full PLY-WEAK-06 procedure end to end **3 times** (play, confirm `session`, kill the supervisor and the shell, `kill -9` mpv with 0 quickshell running, relaunch). All three: `failedAt {"t:qa.live":"HH:MM"}`, `nowPlaying null`, `playing false`, **`jq .session state.json` is `null`**, `state.json` still `0600`, and **0 notifications** on the session bus for the whole procedure. The next shell start re-marks nothing (`failedAt {}`, `session null`). Was 2 of 3 failing; now **0 of 3**. Guide half proven by screenshot (`shots/guide-warning.png`): the row carries the alert glyph in the trail slot and the detail line `QA - Failed 05:53 - Space to retry`, not a red row. |
| **D-PLY-4** P2 | **FIXED - 30 won, 0 lost, measured by QA** | Re-measured with **QA's own `race-trial.sh` from the `8f9447e` pass**, not the fixing lane's harness scenario. The script was reconstructed and diffed against `qa7/race-trial.sh`: the logic is identical, the differences are comments, a variable for the state path, and one wait loop lengthened from 40 to 60 iterations. **30 trials: 30 WON, 0 LOST, 0 VOID.** The play landed on attempt 3 in 29 trials and attempt 4 in one, the same window as the losing pass, so the narrow point being probed is the same one. At `8f9447e` the same script returned 16 won / **14 lost (47%)**. The lane's "30 of 30" is confirmed independently. |
| **D-PLY-5** P2 | **FIXED** | With `omarchy bar set io.github.rmcdavid.iptv mpvArgs '--ytdl=yes'`, `status.warnings` carries exactly `Player warning: mpvArg --ytdl hands the stream address to another program` (plain ASCII `--`, verified by codepoint), and the guide renders it **on its existing single warning line** in the footer, left of the key hints - screenshot `shots/guide-warning.png`. **The option is not refused**: `--ytdl=yes` is the last token on mpv's argv, after the built-in `--ytdl=no`, and mpv's own `ytdl` property reads `true`. The cost is still real and was re-caught live: `yt-dlp ... -- http://qa-user:qa-secret@127.0.0.1:9/live/qa-token-XYZ/dead.ts` on another process's argv, **206 samples**. `README.md` now carries the sentence (PO-5 discharged) and `CHANGELOG.md` 0.3.0 names it under Security. |
| **D-PLY-6** P3 | **FIXED** | Wedged reap **4236 / 4244 / 4255 / 4262 / 4263 ms** across five live runs against the **4500 ms** budget; interface clears in 114-132 ms. QA also ran a controlled A/B on an identical hand-built rig, same wedged player, only the helper swapped: **6187 / 6187 ms at `8f9447e` vs 4177 / 4178 ms at `b16b479`**, so the ~2.0 s the defect attributed to the quit rung's `--ipc-timeout` is exactly what was recovered. The lane's "about 4.2 s" agrees. Responsive path unchanged and inside budget: interface 117-125 ms, process gone 274-305 ms, no SIGKILL. **One divergence found on this path - D-PLY-8.** |
| **D-PLY-7** P3 | **FIXED, both halves, at the documented paths and modes** | The player's **cwd is `/run/user/1000/omarchy-iptv`**, not `$HOME`, and its argv now carries `--screenshot-dir=/home/ricky/.local/state/omarchy-iptv/screenshots` and `--watch-later-dir=/run/user/1000/omarchy-iptv/watch-later`. Pressing `s` on the focused player (focus asserted as `omarchy-iptv` before each keystroke) wrote `~/.local/state/omarchy-iptv/screenshots/mpv-shot0001.jpg` and `0002.jpg`, **mode `600`**, directory `700`. `Shift+Q` wrote `$XDG_RUNTIME_DIR/omarchy-iptv/watch-later/<md5>`, **mode `600`**, directory `700`; the name is a hash, the content carries no address. **Nothing landed in `$HOME`**: `find $HOME -maxdepth 1` shows no new entry across the whole pass, and `find $HOME -name 'mpv-shot*'` returns only the two files inside the documented directory. |

### V3. The startup race, QA's own number

**30 trials, 30 won, 0 lost, 0 void.** Method and provenance in the D-PLY-4 row
above; per-trial log in `logs/race.txt`. Prior pass, identical script: 14 lost
in 30. The end-to-end consequence that made the race matter was separately
re-proven closed by the three PO-3 runs in V2, which all marked correctly.

### V4. The six corrected expectations, re-confirmed

| Case | Still behaves as corrected |
|---|---|
| PLY-RST-03 | **yes**, 2 runs. `nowPlaying null`, `playing false`, **`failedAt {}`** after the restart (session-only, as corrected), and **0 notifications added by the restart** in both runs - one run had raised one toast before the restart, the other none. |
| PLY-RST-06 | **yes.** The live observer survives the unlink (`player.attached` stays `true`); the next zap takes the wedged branch, ladders the unreachable player down and respawns into a re-created `700` directory with a `600` socket. Window count never exceeds 1, dips to 0 across the replacement. |
| PLY-RST-11 | **yes, and its focus consequence is now RUN rather than skipped.** Run **windowed** as corrected (no `--vo=null`), the foreign player maps a real window: `hyprctl clients` reads **2** `omarchy-iptv` clients and `pgrep` reads **2**, while `player probe` reports only ours (pid match asserted), our `stop` leaves the foreign pid alive, and our next start spawns exactly one. This closes section 14 item 7. |
| PLY-LIFE-14 | **yes.** `ppid` is `831` (`systemd --user`), never quickshell; fd 0 and fd 1 are `/dev/null` and **fd 2 is a pipe**, with `SigIgn` bit 13 set (SIGPIPE ignored); the mpv cgroup is byte-identical to the shell's `wayland-wm@hyprland.desktop.service`; `grep -c 'mpv\['` in the journal is **0**. |
| PLY-SEC-05 | **yes**, and the narrowed claim is re-verified in V6. |
| PLY-SEC-07 | **yes, with the list grown by the two new directories.** Complete artifact set, nothing else: `700` on `$XDG_RUNTIME_DIR/omarchy-iptv`, `.../watch-later`, `~/.local/state/omarchy-iptv` and `.../screenshots`; `600` on `mpv.sock`, `player.lock`, `state.json` and every screenshot. `find ... \| grep -vE '^(700\|600) '` returns nothing. Lock content is one line, `{"schema": 1, "seq": N, "verb": "start", "at": <epoch>}`, no URL. No `player.json`, no log file, no systemd unit. |

### V5. File containment

Every file created anywhere reachable during a full exercise cycle (play, four
zaps, a failure, a screenshot, a stop), swept with `find -newer` against a
marker and excluding QA's own evidence tree:

| Path | Mode | Documented? |
|---|---|---|
| `~/.local/state/omarchy-iptv/state.json` | 600 | yes |
| `~/.local/state/omarchy-iptv/screenshots/mpv-shot000N.jpg` | 600 | yes |
| `$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock` | 600 | yes |
| `$XDG_RUNTIME_DIR/omarchy-iptv/player.lock` | 600 | yes |
| `$XDG_RUNTIME_DIR/omarchy-iptv/watch-later/<md5>` | 600 | yes (Playback notes) |
| `~/.cache/mpv/shader_*` (2 files) | 600 | **no - D-PLY-10** |
| `~/.local/state/omarchy/notifications/history/*.json` | 644 | host-owned, see O2 |
| `~/.cache/quickshell/...`, `/run/user/1000/quickshell/...`, `/run/user/1000/hypr/...` | host | host-owned, written for every plugin |

**Nothing in `$HOME` top level.** The plugin directory is unwritten at runtime
(`git status` in the installed clone is empty after the pass).

### V6. Privacy verdict against the narrowed claim

**The narrowed claim holds. Verdict: pass.**

- **20,602 full `/proc` sweeps, 2,199,888 process samples** over 90 s of
  continuous play, zapping and failures, counting **only processes the plugin
  starts** (the helper, mpv, `omarchy-notification-send`) so the driver's own
  argv cannot contaminate the count - correction 3's trap, which bit the first
  attempt here too and produced a meaningless 39,738. Filtered result:
  **0 needles on any plugin-started command line.**
- The three disclosed residuals and nothing else. `--id t:<tvg-id>` on the
  helper's argv: **1,027 catches**. `omarchy-notification-send`'s argv:
  **0 catches**, as at `8f9447e`. The **window title**, which names the channel
  for the whole play and is readable from `hyprctl clients -j`, remains by far
  the largest of the three.
- **The new surface adds nothing.** The option warning is a fixed English
  sentence naming only the option (`--ytdl`), no value, no address. The two new
  directories contain a `600` JPEG and a `600` resume file whose name is an MD5
  and whose content is empty; `grep -rlE '://|qa-secret|qa-token-XYZ'` over the
  whole runtime directory returns nothing.
- Sinks: **0** needles in the journal and **0** `mpv[` lines; **0** needles and
  **0** `://` across every Quickshell shell log; **0** needles in `status`; **0**
  in the notification history. `state.json` carries source playlist URLs only,
  which `Files it writes` documents explicitly.
- Headers (PLY-SEC-04) reach mpv **only over the socket**: `qa-ua-SENTINEL` and
  the referrer read back live off the IPC, **0** occurrences on argv, cleared to
  `libmpv` / empty on the headerless channel and re-applied on the next.
- Hostile names (PLY-SEC-18): `${path}` renders literally in both the window
  title and `force-media-title`, the leading dash is stripped
  (`-u critical ${path}` -> `u critical ${path}`), and a non-ASCII name
  round-trips through `user-data/omarchy-iptv` intact.

The one qualification is the opt-in `--ytdl` path, which is now warned about at
the moment of use and documented beside the setting - see O1.

### V7. Performance against budgets

| Budget | `8f9447e` | **`b16b479` (QA measured)** | Verdict |
|---|---|---|---|
| reattach `nowPlaying` <= 2000 ms | median 491, max 1726 | median **497**, max **1576** (n=6) | pass |
| `player.attached` <= 3000 ms | median 648, max 1930 | median **677**, max **1764** | pass |
| `player probe` <= 400 ms | 160-161 | **148-150** | pass |
| helper verb <= 300 ms | 149-161 | probe **148-150**, status **144-149** | pass |
| stop clears the interface <= 150 ms | 113-118 | **114-132** wedged, **117-125** responsive | pass |
| responsive player gone <= 500 ms | 273-331 | **274-305**, no SIGKILL | pass |
| **wedged player gone <= 4500 ms** | **6258-6276 (fail)** | **4236-4263** | **pass** |
| zap to first frame < 2000 ms | cold 630, warm 241-397 | cold **711-781**, warm **277-338** | pass |
| journal <= 12 socket WARN per player death | ~3 | **1** per death, 3 deaths | pass |
| guide open < 150 ms | 68-77 | **61-69** on the user's 1,474-channel list (ping baseline 56-58) | pass |
| identity over ten restarts | same pid | **same pid and `launchedFrom` through 10 restarts**, one window | pass |

The earlier warm-zap figure is a correction to method, not a regression: timing
"time-pos is non-null" measures the IPC round trip (67-81 ms), because a
`loadfile replace` reuses the player and the old `time-pos` is still readable.
The honest signal is `media-title` reaching the new channel **and** `time-pos`
back under 2 s, which gives 277-338 ms.

### V8. Regression surface

- **Automated:** 954 node checks, 260 python tests, 47 qml cases, `validate`
  exit 0 - all green, all re-run at `b16b479` (V1).
- **Harness:** 75 checks pass, 0 fail; 20 of them fail at `396a69a`, satisfying
  rule 11 for the four new scenarios.
- **Live, re-run from `docs/QA-PLAYER.md` section 7 and the defect rows:**
  PLY-RST-01 (**6/6**, same pid, same `/proc` field-22 start time, one window at
  every one of 120 samples per run, `time-pos` advancing, identity including
  `launchedFrom` identical), PLY-RST-03, PLY-RST-06, PLY-RST-11, PLY-LIFE-12,
  PLY-LIFE-14, PLY-SOCK-01 (C1 shape plus the behavioural reattach: **585 and
  613 ms** after a kill and restart), PLY-SOCK-11, PLY-STOP-03, PLY-PERF-02,
  PLY-SEC-01/02/04/05/07/14/15/18, PLY-WEAK-01/02/05/06, TC-PLAY-07 (`q` in mpv
  is a clean quit: player gone, interface clears, `wanted false`, **0**
  notifications) and TC-PLAY-10 (zap burst).
- **Counts: 29 live cases re-run, 27 pass, 2 findings** - D-PLY-8 on
  PLY-STOP-03's socket clause and D-PLY-11 on TC-PLAY-10. Plus 6 PLY-RST-01
  runs, 3 PO-3 procedures, 5 wedged and 5 responsive stop runs, 30 race trials
  and 10 consecutive restarts as repetition.

### V9. New defects

#### D-PLY-8 (PLY-STOP-03) P3 found 2026-09-14 at `b16b479`, **pre-existing**

**A wedged stop leaves the socket file behind; only the next helper call
removes it.** After `kill -STOP` then `stop`, the player is reaped at ~4.25 s
but `$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock` survives, measured still present at
**t+66 s** with the shell idle and untouched. PLY-STOP-03 says "the socket is
unlinked only after the final connect is refused", and `connect()` **does**
return `ECONNREFUSED`, so `settle_socket()`'s guard should fire; it does not,
it does not. CORRECTED 2026-09-14 by measurement, and this paragraph's
original guess was wrong: the blocking guard is `socket_is_dead()`, not
`find_player()`. A killed player clears its command line in about 0.2 ms, so
`find_player()` goes blind FIRST, while its listening socket stays bound for
another 2.7 to 4.9 ms; the shipping guards ask at 4.5 to 7.5 ms and the
single-shot check simply looked too early. On the `quit` path the order
reverses, the socket is refused about 2 ms BEFORE the command line empties,
which is exactly why the responsive stop path unlinks correctly (5/5).

**Not a regression**: QA's A/B on an identical rig left the socket behind at
**both** `8f9447e` and `b16b479`, so it predates these fixes and the prior pass
recorded PLY-STOP-03 as pass without asserting the clause. Harmless in
practice: the residue is `600` inside a `700` directory so PLY-SEC-07 still
passes, `player probe` reports `running:false` correctly through it and removes
it, and the next play succeeded normally in **665 ms**. Either implement the
clause or drop it from the plan.

#### D-PLY-9 (test tooling) P3 found 2026-09-14 at `b16b479`

**`player-scenario.sh` silently drops its own most important D-PLY-1 check.**
`log_count()` at line 149 is `grep -acE ... || echo 0`; `grep -c` prints `0`
**and** exits 1 when there is no match, so the `|| echo 0` appends a second
line and the function returns `"0\n0"`. Line 374 then evaluates
`$(( $(log_count ...) - before11 ))` and dies with
`arithmetic syntax error (error token is "0")`. The check that dies is
**"P11 exactly ONE relaunch, not a second one at the healthy player"** - the
assertion for the half of the D-PLY-1 fix that cancels the delivered relaunch's
timer. It aborts at both `b16b479` and the `396a69a` baseline and is absent
from both summaries, so the 75/0 and 60/20 counts are each one check short.
QA measured the property directly instead (V2, delta exactly 1, 3/3). Fix:
`grep -acE ... || true` with a `head -1`, or `| wc -l`. The same trap is worth
sweeping for elsewhere in the script.

#### D-PLY-10 (PLY-SEC-07, `Files it writes`) P3 found 2026-09-14 at `b16b479`

**The player writes mpv's shader cache into `~/.cache/mpv/`, outside the
documented list.** Two files (`shader_2a337003854863bf`,
`shader_94d4454b832de9f8`, mode `600`) appeared there during the containment
cycle. The containment fix gave the player a working directory and redirected
screenshots and resume positions, but mpv still inherits `HOME`/`XDG_CACHE_HOME`
and caches compiled shaders. **Privacy impact: none** - the files carry no
needle, no URL and nothing keyed to content, they are `600`, and the directory
predates the plugin (created 2026-09-12, shared with any other mpv use on the
machine). It is a completeness gap in README `Files it writes`, which the lead's
"no file outside the documented list" check is entitled to flag. Suggested: one
line under `Files it writes`, or `--no-config` plus a cache redirect if the
intent is total containment.

#### D-PLY-11 (TC-PLAY-10) P3 found 2026-09-14 at `b16b479`, **weak repro**

**Eight truly-concurrent `play` calls left `nowPlaying` naming a different
channel than the player was on.** Observed **once**: `nowPlaying t:qa.live`
while both the window title and mpv's `media-title` read `QA Plain No Headers`,
and it did **not** self-correct at t+5 s, t+20 s or t+40 s (past two health
ticks). Filed because it is the plan's own P2 shape ("the interface loses the
channel identity"), but deliberately P3 because it is barely reachable:
**1 of 8** parallel-burst runs, **0 of 6** in targeted re-attempts, and
**0 of 4** with the same eight zaps issued serially - which is all the guide can
produce, being single-threaded QML. One player and one window at all 80 samples
in every run, so it is a state-reporting divergence, not a two-player defect.
Worth a look at the last-intent-wins path under simultaneous IPC; not worth
blocking a tag.

### V10. Observations, recorded not filed

1. **The README's headline privacy claim is still unqualified.** "No stream
   address, credential or header value ever reaches any command line"
   (`Playback notes`) sits ~100 lines below the `mpvArgs` paragraph that
   documents the one option which breaks it. PO-5 is discharged - the cost is
   named beside the setting, the product now warns at the moment of use, and
   CHANGELOG 0.3.0 carries it - so this is not a re-open of D-PLY-5. One
   subordinate clause on the headline bullet would close the tension.
2. **The notification history durably stores the channel name.** Omarchy's own
   `~/.local/state/omarchy/notifications/history/*.json` (mode 644) kept
   `"QA Dead Channel" did not play - [stream] Failed to open 127.0.0.1`. Host
   behaviour for every notification, not the plugin's file, and it carries the
   host only - no credential, no token, no path. But the residual README calls
   "brief" is durable once it lands there.
3. **README `Files it writes` attaches `(mode 0600)` to the screenshots
   *directory*.** The directory is `700` and the files are `600`, which is the
   only workable arrangement; the sentence reads correctly if `0600` is taken to
   qualify the screenshots. Recorded so it is not mistaken for a defect.
4. **`omarchy plugin disable` drops the widget's settings**, as the README's
   "Note on disabling" says; `playlistUrl` had to be re-set after re-enabling.
   Confirmed incidentally, working as documented.
5. **`omarchy plugin remove` also drops the bar entry** from `shell.json`
   entirely, so a reinstall needs `omarchy bar set` again. It returned to its
   original position in the layout.

### V11. Restore

Proved at 06:15.

- `~/.config/omarchy/shell.json` - **byte-identical**, sha
  `9a704ac6...1768e6`, mode `600`.
- `~/.local/state/omarchy-iptv/state.json` - restored, mode `600`, and
  **semantically identical**: the only difference from the snapshot is the
  service's own `fetchedAt` on the user's source. **No QA residue** - `grep -c
  '8791\|qa-player'` is `0` and the only source is `d5977d8a`
  (`iptv-org.github.io`). As at `8f9447e`, the service re-added the QA source
  record on the first restart after the restore, so the snapshot was written
  back a second time and confirmed to stick.
- `~/.cache/omarchy-iptv/` - one source directory, `channels.json` identical
  apart from `generatedAt`, `playlist-status.json` identical apart from
  `fetchedAt`/`durationMs`.
- **The mode/size/owner manifest over all three trees `diff`s empty against the
  pre-pass manifest.**
- `status` **diffs clean** against `status.before.json` apart from
  `lastUpdated`: 1,474 channels, source `d5977d8a` on `iptv-org.github.io`,
  5 recents, 0 favorites.
- Installed clone back on **`main` at `a6bae85`, tracking `origin/main`**,
  0 modified and 0 untracked files, and `diff -r` against the pre-pass backup is
  **empty**. `origin/main` was never moved: the RC was fetched from the local
  repository into `FETCH_HEAD`, as at `8f9447e`.
- Plugin re-registered and **enabled**, bar entry back in its original slot;
  shell restarted onto the restored config.
- `$XDG_RUNTIME_DIR/omarchy-iptv` back to `700` and **empty**; harness scratch
  tree removed; fixture server stopped and port 8791 closed; 7 stray
  `dbus-monitor` captures from this pass killed; 0 mpv, 0 `omarchy-iptv`
  windows, 0 guide layers, 1 quickshell.
- The working repository at `/home/ricky/Projects/omarchy-iptv` is clean at
  `b16b479` with no untracked files. **Nothing was committed.**
- Not restored, deliberately: the two `~/.cache/mpv/shader_*` files (D-PLY-10's
  evidence, in a directory that predates the plugin).

### V12. Release recommendation

**Go for v0.3.0.**

All seven defects are discharged: five fixed and verified by their original
reproductions, one (D-PLY-4) re-measured by QA's own unchanged instrument at
**30 won / 0 lost** against 14 lost in 30, and one (D-PLY-2) closed as accepted
under PO-8 with its documented recovery tested verbatim, including the proof
that the pattern's leading anchor is load-bearing. The P1 is gone from both of
its independent triggers, and the relaunch-count half of that fix is confirmed
by QA's own journal measurement because the harness check for it never runs.
Every performance budget is met, including the one that failed last time. The
narrowed privacy claim survives 2.2 million process samples with zero
plugin-originated needles, and the containment change puts both of the player's
own writes at `600` under the documented paths with nothing in `$HOME`.

Four new defects are filed and **none blocks the tag**: D-PLY-8 is pre-existing
and self-healing, D-PLY-9 is test tooling, D-PLY-10 is a documentation
completeness gap over a content-free cache, and D-PLY-11 is a state-reporting
divergence seen once under a trigger the guide cannot produce.

Suggested before the tag, none of it gating: fix D-PLY-9 so the relaunch check
actually runs in CI, add the `~/.cache/mpv` line to `Files it writes`
(D-PLY-10), and add one clause to the headline privacy bullet (O1).

## M1.2/M2 cleanup round - Lane D live pass on a939fd7 (QA, 2026-09-14, 10:05 - 10:57)

Wave two of the cleanup round: the live half of `docs/CLEANUP-PLAN.md`
section 6, run against `main` at `a939fd7` with the installed clone moved to
that commit and back. **This is a measuring lane**: it owns this file and
nothing else, and every fix it names below is a finding handed to wave three,
not a diff. Reference machine, display held exclusively by this lane; no other
lane ran. Evidence root `/tmp/claude-1000/omarchy-iptv-qa9/`. `pgrep -x
hyprlock` was checked before every keystroke batch and returned empty every
time. No logout. Rulings CL1 (the stop budget measures "the player process is
gone") and CL2/CL3 are applied as written.

Setup: the installed plugin at `~/.config/omarchy/plugins/io.github.rmcdavid.iptv`
was fetched from the local repository into `FETCH_HEAD` and checked out
detached at `a939fd7` (`origin/main` was never moved); `omarchy plugin validate`
exit 0; `playlistUrl` pointed at `http://127.0.0.1:8791/qa-player.m3u`
(`tests/fixtures/qa-player/qa-player.m3u`, served on loopback from the repo
fixture directory). Baseline captured first: 1,474 channels, one source
`d5977d8a` (`iptv-org.github.io`), **7** recents (the runbook's "five" is
stale), 0 favorites, theme `Retropc`, `session` null, runtime directory
holding `player.lock` and an empty `watch-later`.

### D1. The D-PLY-11 discriminator - TC-PLAY-10 extended, and PLY-LIFE-03

The extended capture the plan asks for was taken at t+6 s, and again at t+20 s
and t+40 s whenever anything disagreed: `ipc status` (`nowPlaying`,
`player.seq`, `player.entryId`), the window title, and over `socat` to the live
player `media-title`, `force-media-title`, `path`, the whole `playlist`
property (its current entry **id** is the count of `loadfile`s that player has
ever taken) and `user-data/omarchy-iptv`; plus `player.lock`, the recents ring
(every `play()` calls `recordPlayed`, so it records the order the shell saw the
burst) and the shell journal.

**Two facts make the capture decisive.** `apply_channel` writes the stash's
`seq` from its caller, and `cmd_play` hardcodes `0` (`bin/omarchy-iptv:1808-1810`)
while `player start` carries a real one - so **`stash.seq != 0` means a
`player start` was the last thing to write that player, and `0` means a zap
was**. And the current playlist entry id counts `loadfile`s, so it says how
many `apply_channel` calls reached the player at all.

| Case | Runs | Result |
|---|---|---|
| Cold concurrent burst (8 `play` calls fired simultaneously from nothing playing) | 20 | **10 user-visible divergences** (the shell's channel name differs from `media-title` **and** the window title), 3 further stash-only divergences, 7 clean |
| Warm concurrent burst (same 8 calls, player already up and attached) | 10 | **0 divergences of any kind** |
| Cold **serial** hammer (the same 8 intents, one at a time) | 6 | **0 divergences**, `stash.seq` 0 every time |
| PLY-LIFE-03, cold Enter hammer through the guide, 20 alternating Enters | 3 | **pass 3/3** |

What the 20 cold bursts show, without exception:

- **Every one of them was cold** (`player.up` and `player.attached` both false
  before the burst) and **every one issued exactly one `player start`**, whose
  lock record reads `verb:"start"` with `seq == pre.seq + 1` - the **first**
  intent of the burst - while `status.player.seq` ends at `pre.seq + 8`.
- **The player took two or more `loadfile`s**: the current playlist entry id is
  `2` in 18 runs and `3` in 2. Only one `player start` ever ran, so a **zap
  reached the socket first** and the start's own `apply_channel` came after it.
- In 8 of the 10 visible divergences `stash.seq` is the start's own seq: the
  cold `player start` overwrote title, force-media-title and stash with the
  **first** intent after a later zap had already landed. In the other 2
  (trials 11 and 19) `stash.seq` is `0` while `force-media-title` names a
  different channel again - the two `apply_channel` sequences **interleaved**
  on the one socket, the title from one and the stash from the other.
- **`omarchy-iptv: play failed:` appears 0 times in all 30 bursts**, and
  `not_running` 0 times. The rollback at `Service.qml:1000` never executed.
- **Nothing self-corrected**: all 13 divergences still read the same at t+20 s
  and t+40 s, past two health ticks.
- One player and one window at every sample of every run.

The warm control is the other half of the discrimination: a warm burst takes
the zap branch at `Service.qml:419-425` for all eight calls and **issues no
`player start` at all** - the lock sequence never advanced in any of the ten -
so the adopting-start family has no trigger in this case and produced nothing.

> **Verdict: the ordering family that fires is the cold one.** A change wins
> the socket during a cold start and is then overwritten by, or interleaved
> with, that start's own `apply_channel`. This is the skeptic's replacement
> hypothesis and the plan's **T-B**, now reproduced 10 times in 20 on a real
> shell with the mechanism visible in the stash seq and the entry id. The
> plan's **T-A** (an adopting start re-applying its own channel) did not fire
> in 30 bursts and cannot fire in the warm case, because no `player start` is
> issued there. **O1 is excluded** in every run by the journal.
>
> It is also **much more reachable than the `1 of 8` on record**: 10 of 20
> cold bursts, against 0 of 10 warm and 0 of 6 cold-serial. What made it rare
> before was not the code but the arrangement - the prior pass did not
> guarantee a cold player before each burst.

**PLY-LIFE-03** (never re-run since `8f9447e`) passes at `a939fd7`, 3 runs:
`hyprctl` sampled every 100 ms across the whole hammer yields only `0` and `1`
(249 / 249 / 250 samples, **0 samples reading 2 or more**); `playSeq` advances
by exactly 20 in each run, so every Enter landed and none was dropped; the run
ends on the last channel pressed 3/3; one player and one window at the end;
and `nowPlaying`, `media-title` and the stash all agree 3/3. Recorded, not
filed: at the current code the guide's Enter **dismisses the guide**
(`Guide.qml:634`), so a hammer is necessarily one press per guide reopen
(~0.9 s) and only the first press or two fall inside the cold start. The
runbook's "as fast as the guide accepts" predates that and should say so.
It is also the plainest demonstration of why CL6 is the right severity: the
guide cannot produce the concurrency D-PLY-11 needs.

### D2. D-PLY-8 - the windowed player's teardown, and the socket residue

**The assumption the plan could not test is now a measurement.** Five SIGKILLs
on the real windowed player (RSS 140-217 MB, one window mapped, GPU context and
Wayland connection live), sampling `/proc/<pid>/cmdline` and `connect()` in a
tight loop from the instant of the kill:

| Run | RSS | cmdline empty | socket refused | blind-to-unbound window |
|---|---|---|---|---|
| 1 | 146 MB | 0.417 ms | 37.362 ms | **36.946 ms** |
| 2 | 143 MB | 0.312 ms | 16.797 ms | **16.484 ms** |
| 3 | 217 MB | 0.421 ms | 22.578 ms | **22.157 ms** |
| 4 | 140 MB | 0.340 ms | 24.882 ms | **24.542 ms** |
| 5 | 146 MB | 0.223 ms | 15.008 ms | **14.785 ms** |

- `find_player()` goes blind first, at **0.22-0.42 ms**, 5/5 - the independent
  re-measurement holds on a windowed player, and the hypothesis corrected in
  `X4` stays corrected.
- The window is **14.8-36.9 ms**, and every one of the five is **above the
  4-8 ms observation point** the shipping single-shot settle used. **A real
  windowed mpv does clear the bar**; the inference was right.
- **The teardown-proportionality claim does not survive on the real thing.**
  146 MB gave 36.9 ms and 14.8 ms while 217 MB gave 22.2 ms - a 2.5x spread at
  constant RSS and no ordering by size. Lane A's allocation-scaling series
  (1.6-3.4 ms at 256 MB) under-predicts a windowed player by an order of
  magnitude. Neither party's proportionality should be written down as a fact
  for the windowed case; what is established is the **ordering** and the
  **magnitude**, and both say the same thing: 500 ms of already-reserved kill-rung
  deadline is ample and a single shot at 4-8 ms never was.

**PLY-STOP-03, 5 wedged and 5 responsive.** In **10 of 10** the socket is
already gone at **t+0.2 s** and still gone at t+1 s, t+5 s and t+30 s, with no
helper call of QA's own in between and with the `stopSettleTimer` backstop line
(`the player outlived a stop`) absent from the journal in all ten. The
runtime directory after each stop holds `player.lock`, `watch-later` and
`shader-cache` and nothing else. **D-PLY-8 does not reproduce at `a939fd7`**,
where it reproduced 5/5 at both `8f9447e` and `b16b479`.

### D3. D-PLY-10 - the shader cache

- `$XDG_RUNTIME_DIR/omarchy-iptv/shader-cache` exists at **0700** inside a
  **0700** parent, created by `ensure_player_dirs` rather than by mpv, and
  holds 26 files **all at 0600**.
- The player's argv carries `--gpu-shader-cache-dir=` and `--icc-cache-dir=`
  pointing there, ahead of any user token.
- `~/.cache/mpv` is **unchanged**: the same 46 file names before and after, and
  **0 files newer than the start of the pass** after roughly fifty minutes of
  windowed playback and about 120 player starts. The two names D-PLY-10 filed
  (`shader_2a337003854863bf`, `shader_94d4454b832de9f8`) are now written into
  the redirected directory instead.
- No new top-level entry in `$HOME` across the pass.

**D-PLY-10 is closed by measurement**, and this is the only evidence that could
close it: a `--vo=null` player compiles no shaders.

### D4. D-PLY-9 - the repaired harness check does NOT discriminate

`scripts/dev-harness/player-scenario.sh`, both halves, on this display:

| Tree | Summary | Exit |
|---|---|---|
| `a939fd7` (HEAD) | **83 passed, 0 failed, 83 assertions executed** | 0 |
| `--baseline 396a69a` | **67 passed, 21 failed, 83 assertions executed** | 1 |

The repair itself works. `log_count` returns one line, the arithmetic no longer
dies, and the unguarded floor (`the harness ran every check it has`) passes on
both trees - so the class D-PLY-9 belonged to, a check that stops executing and
merely shortens the summary, is closed. The 21 baseline failures are P11 (5),
P12 (4), P13 (7) and P14 (5), which is the rule-11 evidence the four new
scenarios were written for.

**But the assertion at the centre of it passes on both trees.**
`PASS P11 exactly ONE relaunch, not a second one at the healthy player` appears
in **both** summaries. The witness line added under CL3 does not change that,
for two independent reasons, both confirmed here:

1. **Nothing counts it.** `player-scenario.sh:402` and `:416` still count
   `mpv unresponsive, restarting player` - the `console.warn` at
   `Service.qml:510` that both trees emit exactly once. A grep of the whole
   repository for the new string returns **one** hit, `Service.qml:2491`;
   there is no reference to it anywhere under `scripts/` or `tests/`.
2. **Repointing it would not help against `396a69a`.** A `--baseline` run
   exports the baseline's own `Service.qml`, and that tree's `relaunchTimer`
   `playerUp` branch is byte-identical apart from the missing line. The count
   would therefore be **0 on both trees**. The line can only ever be a forward
   regression guard for trees that already carry it; it cannot be rule-11
   evidence against the tree the defect was filed on.

Confirmed live at `a939fd7`: a `kill -STOP`ped player produces the two-strike
verdict and a correct relaunch (new pid, one player, one window,
`playing`/`attached`/`wanted` all true, right channel - D-PLY-1 trigger A
re-verified 4/4), and the journal carries `mpv unresponsive, restarting player`
**1** and `relaunching the unresponsive player` **0**. Zero is the right answer
for a fixed tree - the branch the line sits in is exactly the second relaunch
the fix cancels - and it is also what the baseline would print, because the
line is not in it.

**A witness that does discriminate, measured here so wave three need not guess.**
The intent counter, which is candidate 1 of the plan's section 2(c):

| Wedge-and-respawn at `a939fd7` | run 1 | run 2 | run 3 |
|---|---|---|---|
| `status.player.seq` delta | 1 | 1 | 1 |
| `player.lock` seq delta | 1 | 1 | 1 |

Both are already reachable from the harness (`svc "d['player']['seq']"` and
`$SCRATCH/runtime/omarchy-iptv/player.lock`), both exist unchanged on the
baseline tree, and the broken path increments `playSeq` a second time in the
`relaunchTimer` branch, so the baseline must read **2**. Candidate 2 (counting
`player restart` helper processes) is **not** usable: `spawn_detached` double
forks, and a `/proc` sweep across three single relaunches saw 1, 2 and 2
distinct pids for one logical restart.

### D5. PLY-PERF-02 re-measured under CL1

CL1: the budget is met when the **player process is gone**, not when the
command returned. Measured by polling `kill -0` in a tight loop from the
instant `stop` was issued.

| Path | Runs | Player gone | Budget | Verdict |
|---|---|---|---|---|
| Wedged (`kill -STOP` first) | 5 | **4268 / 4269 / 4277 / 4286 / 4299 ms** | 4500 ms | **met 5/5** |
| Responsive | 5 | **304 / 324 / 335 / 337 / 345 ms** | 500 ms | **met 5/5** |

- The stop command itself returned in **60-81 ms** in all ten; under CL1 that
  number is not the budget, and it is recorded only to show the two readings
  are nowhere near each other.
- No SIGKILL is reachable on the responsive path: the player is gone about
  1.65 s before the TERM rung is due.
- `Service.qml:64`'s 5000 ms `stopSettleTimer` backstop **never fired** (0/10).
- The wedged figures are ~30 ms above `b16b479`'s 4236-4263 ms, which is the
  settle now spending a little of the kill rung's own reserved 500 ms. Still
  200 ms inside the budget.
- **Interface clear is resolution-limited and is recorded as a bound, not a
  verdict**: 61-167 ms, on a poller whose own cost is **57 ms per sample**
  (each sample is an `omarchy-shell ... status` process spawn). The floor
  observations, 61-64 ms, agree with the prior pass's 52-59 ms. The 150 ms
  budget cannot be decided at this resolution and this is **not** recorded as
  a regression; a tighter instrument is wave-three work if the budget is to be
  asserted rather than observed.

### D6. Findings handed to wave three

1. **The D-PLY-11 cause is established and it is the cold one.** Wave three may
   build the cause-directed successor for that family. The evidence is D1 above:
   one `player start` carrying the burst's **first** intent, a zap's `loadfile`
   ahead of it, and the start's `apply_channel` last. Note CL4 still stands -
   giving `play` the seq and the lock is the wrong instrument here, and the
   plan says why. What the evidence actually indicts is that `player start`'s
   `apply_channel` has no way to learn that a newer intent already landed on
   the player it is adopting or has just spawned; the stash it overwrites
   already carries the answer.
2. **The rate is 10 of 20, not 1 of 8.** The `weak repro` wording on
   `docs/STATUS.md:146` under-states it and should be corrected when D-PLY-11
   is dispositioned. The severity is still bounded by CL6.
3. **CL3 is half-landed.** The witness exists; nothing asserts on it, and it
   cannot discriminate against `396a69a` by construction. Wave three should
   point `player-scenario.sh:402`/`:416` at the intent counter measured in D4,
   and correct the sentence in `docs/STATUS.md:144` that implies the repaired
   check now covers the property.
4. **Do not write teardown-proportionality down as a fact.** The windowed
   measurement in D2 contradicts it. The plan's own instruction to trust only
   the ordering and the magnitude is the right one.
5. The interface-clear budget in PLY-PERF-02 has no instrument fine enough to
   assert it. Either measure it from inside the shell or state it as an
   observation.

Recorded, not filed: four entries appeared in Omarchy's own notification
history (`~/.local/state/omarchy/notifications/history/*.json`, mode 644),
naming the channel and a host-only reason; **0 needles** in them
(`qa-user`, `qa-secret`, `qa-token-XYZ`, `://` all absent). Host behaviour, as
at `b16b479` (V10 item 2). The rendered name of `t:qa.rawdash` reads
`u critical ${path}` on both sides of every comparison - that is S-04 stripping
a leading dash by design, not a divergence.

### D7. Restore

Proved at 10:57.

- `~/.config/omarchy/shell.json` - **byte-identical**, `sha256sum -c` OK.
- `~/.local/state/omarchy-iptv/` - `diff -r` against the snapshot is **empty**
  and `sha256sum -c` OK. As at `8f9447e` and `b16b479`, the outgoing shell
  wrote its in-memory source list back after the first restore, re-adding the
  QA source record; the snapshot was written back a second time, held for
  12 s, and held again across a further `omarchy restart shell`.
- `~/.cache/omarchy-iptv/` - `diff -r` **empty**; the QA source directory is
  gone.
- The mode/owner manifest over both trees `diff`s **empty** against the
  pre-pass manifest.
- `status` **diffs clean** against `status.before.json` apart from
  `lastUpdated` and `player.seq`: 1,474 channels, source `d5977d8a` on
  `iptv-org.github.io`, 7 recents, 0 favorites, `nowPlaying` null.
  `player.seq` is the live intent counter recovered from the runtime lock
  record and is not durable state.
- Installed clone back on **`main` at `d44dc6e`, tracking `origin/main`**,
  0 modified and 0 untracked, and `diff -r` against the pre-pass backup is
  **empty**. `origin/main` was never moved; `a939fd7` was fetched from the
  local repository into `FETCH_HEAD`.
- Theme `Retropc`, unchanged. `$HOME` has no new top-level entry.
- `$XDG_RUNTIME_DIR/omarchy-iptv` back to `700` holding `player.lock` and an
  empty `watch-later`, exactly the shape found at 10:05; the socket and the
  `shader-cache` directory this pass created were removed.
- Nothing left running: **0** mpv, **0** `omarchy-iptv` windows, **1**
  quickshell (the user's, on `/usr/share/omarchy/shell`), the harness scratch
  tree removed, the fixture server stopped and port 8791 closed, and the two
  QA poller loops this pass started killed.
- The working repository at `/home/ricky/Projects/omarchy-iptv` is clean at
  `a939fd7` with no untracked files. **Nothing was committed.**
- Not restored, deliberately: the four notification-history files above, which
  are Omarchy's own and predate no plugin state; and `~/.cache/mpv`, which was
  never written to.

## M1.2/M2 cleanup round - final live confirmation on d76b649 (QA, 2026-09-14, 12:22 - 13:05)

The confirmation pass for the cleanup round: the live half of
`docs/CLEANUP-PLAN.md` sections 10 and 11, run against `main` at **`d76b649`**
with the installed clone moved to that commit and back. **This is a measuring
lane**: it owns this file and nothing else, and every fix it names below is a
finding, not a diff. Reference machine, display held exclusively; no other lane
ran. Evidence root `/tmp/claude-1000/omarchy-iptv-qa10/`. `pgrep -x hyprlock`
was checked before every keystroke batch and every burst run and returned empty
every time. No logout. Rulings CL1, CL2, CL4, CL5, CL6, CL10, CL12, CL13 and
CL14 are applied as written.

Setup: the installed plugin at
`~/.config/omarchy/plugins/io.github.rmcdavid.iptv` was fetched from the local
repository into `FETCH_HEAD` and checked out detached at `d76b649`
(`origin/main` was never moved and stayed at `d44dc6e`);
`omarchy plugin validate` exit 0; `playlistUrl` was pointed at
`http://127.0.0.1:8791/qa-player.m3u` (`tests/fixtures/qa-player/qa-player.m3u`,
served on loopback from the repository fixture directory). **Those two are the
only things changed on the machine**, and both are restored in L7. Baseline
captured first: 1,474 channels, one source `d5977d8a` (`iptv-org.github.io`),
**7** recents (the runbook's "five" is still stale), 0 favorites, theme
`Retropc`, `session` null, runtime directory holding `player.lock` and an empty
`watch-later`.

Gates at `d76b649` before anything live, `scripts/check.sh` exit **0**: node
**1000 checks / 0 failures**, python **284 tests OK**, qml spec **49 passed**,
harness predicates **117 checks**, ascii scan **56 files**. This is the claimed
green baseline and it reproduces exactly.

### L1. The defect itself - the cold concurrent burst, re-measured

Same procedure as wave two (QA-RESULTS D1), same instrument, same counts: eight
`play` calls fired simultaneously at a guaranteed-cold player, captured at t+6 s
with `ipc status`, the window title, and over `socat` the player's
`media-title`, `force-media-title`, `path`, the whole `playlist` property and
`user-data/omarchy-iptv`, plus `player.lock`, the recents ring and the shell
journal.

| Case | Runs | Wave two at `a939fd7` | **This pass at `d76b649`** |
|---|---|---|---|
| Cold concurrent burst | 20 | 10 user-visible divergences, 3 further stash-only, 7 clean | **0 divergences of any kind** |
| Warm concurrent burst | 10 | 0 | **0** |
| Cold **serial** hammer | 6 | 0 | **0** |

**Zero of twenty.** Every one of the twenty was genuinely cold (`player.up` and
`player.attached` both false before the burst, 20/20). At t+6 s,
`status.nowPlaying.id == stash.id` in **20/20**, the shell's channel name equals
`media-title` in **20/20** and equals the window title in **20/20**. One player
and one window at every sample. `omarchy-iptv: play failed:` appears **0** times
and `not_running` **0** times across all thirty-six burst and hammer runs; the
rollback at `Service.qml:1000` never executed.

**The stand-down, observed live.** The mechanism fired in **5 of the 20** cold
bursts, each time writing two journal lines - the helper's own and the shell's
warning raised from the reply's `warnings`:

```
WARN qml: omarchy-iptv player: omarchy-iptv: player start: a newer channel
          change reached the player first (intent 662 over 662); left it playing
WARN qml: omarchy-iptv: player start: a newer channel change reached the
          player first
```

In 4 of those 5 the player's current playlist entry id is **1** - the start
applied nothing at all, so the zap's own `loadfile` is the only one that ever
happened. That is the fix working at the helper layer, and it is the half wave
two predicted but could not witness.

**The shell-side repair, observed live.** The CL5 re-apply
(`omarchy-iptv: the player start settled on another channel; re-applying the
intent`) fired in **12 of the 20**, which is the other half: where the start won
the handshake race and applied the burst's first intent, the shell sent its own
intent again rather than relabelling. The cost is visible and worth recording:
the entry-id histogram over the twenty reads **1 in 4 runs, 2 in 4, 3 in 12**,
against wave two's 2 in 18 and 3 in 2. The repair buys correctness with one
extra `loadfile`.

**The warm control still discriminates.** In all ten warm bursts the lock record
stayed frozen at `seq 687, verb "start"` - written by the seeding play, never
advanced - so the burst issued **no `player start` at all** and the cold-start
family had no trigger. Exactly as at `a939fd7`.

**The cold-serial control, with one change worth noting.** 0 of 6, one player
and one window each; but `stash.seq` now reads a real intent number
(762, 771, 780, 789, 798, 807) where wave two recorded a hardcoded **0** every
time. That is D-PLY-11's detection half landed and it is what lets the two sides
be compared rather than merely differed.

**Recorded honestly, not counted:** the rig's shakedown run, fired immediately
after the shell restart and before the counted twenty, **did** diverge at t+6 s
(the shell on `t:qa.raw`, the player on `t:qa.live`). The re-apply line was
already in the journal at that sample, and the run had converged by t+20 s and
held at t+40 s. It is the one observation in twenty-one where the repair was
still in flight at the six-second mark, and the plausible reason is that it was
the first cold spawn after a shell restart - the slowest one, with the shader
cache and the GPU context cold. Wave two's thirteen divergences, by contrast,
were all still there two health ticks later. Nothing self-corrected then;
everything self-corrects now.

### L2. The health-tick convergence (CL6), which had no outcome test

The invariant CL6 sets is that the interface's label and the player's channel
agree within one health tick. `healthTimer` is **10 000 ms**
(`Service.qml:55`), so that is the ceiling. A divergence was injected directly
into the live player over `socat`, behind the shell's back, four times: a
`loadfile` of a different stream, a `user-data/omarchy-iptv` stash naming
`t:qa.plain`, and - in runs 2, 3 and 4 - `force-media-title` and `title` as
well, so the window the user actually reads named the impostor too. The shell
was holding `t:qa.live` throughout. Sampled once a second for 30 s, every
sample recorded.

| Run | Injection | Converged | Ceiling | `nowPlaying` ever relabelled? |
|---|---|---|---|---|
| 1 | stash only | **4 491 ms** | 10 000 ms | **no** |
| 2 | stash + title + force-media-title | **4 533 ms** | 10 000 ms | **no** |
| 3 | stash + title + force-media-title | **4 481 ms** | 10 000 ms | **no** |
| 4 | stash + title + force-media-title | **4 489 ms** | 10 000 ms | **no** |

- **It converges inside one tick, 4/4**, with better than 2x margin.
- **It re-applies; it does not relabel.** `status.nowPlaying.id` read
  `t:qa.live` at **all 120 samples across the four runs** and never once read
  the impostor. The player came back to `t:qa.live` - stash, `media-title` and
  the window title together - rather than the label moving to meet the player.
  That is the distinction ruling CL5 exists for, and it is the one that
  separates a visible reporting bug from a user watching a channel they did not
  choose with the interface agreeing.
- The journal carries `omarchy-iptv: the player is not on the channel the guide
  names; re-applying it` exactly **once per run, 4/4** - the health-tick branch
  at `Service.qml:1102-1108`, distinct from the start-reply branch of L1.
- Repairs are capped at `channelRepairMax: 2` per intent, so a player that will
  not take the channel is reported rather than re-zapped forever. Not reached in
  any of the four.

**Live guide confirmation.** The guide was opened over IPC, screenshotted, and
confirmed to hold keyboard focus before any keystroke (full-screen overlay layer
`omarchy-iptv` at level 3, search prompt focused, footer reading
`Enter play / Up/Down move / Esc close`). Typing `Plain` filtered the list to
one match - proof the keystrokes reached the guide and not another surface -
and `Return` played it. `nowPlaying`, `media-title`, the stash and the window
title all read `QA Plain No Headers`. Shots in
`/tmp/claude-1000/omarchy-iptv-qa10/shots/`.

### L3. The scenario suite, both ways

| Suite | At `d76b649` | Against the named baseline | Discriminates? |
|---|---|---|---|
| `dev-harness/player-scenario.sh` (P1-P14) | **85 passed, 0 failed, 85 executed** | `396a69a`: **68 passed, 22 failed, 85 executed** | yes |
| `qa-player-scenarios.sh run cold` (H17 + H18 A) | **20 passed, 0 failed** | - | - |
| `qa-player-scenarios.sh PLY-H17` | (11 assertions, all green) | `a939fd7`: **6 passed, 6 failed** | yes |
| `qa-player-scenarios.sh PLY-H18` phase A | (7 assertions, all green) | `a939fd7`: **4 passed, 4 failed** | yes |
| `qa-player-scenarios.sh PLY-H18` A+B `--with-display` | **12 passed, 0 failed** | `a939fd7`: **7 passed, 5 failed** | yes |

**The repointed one-relaunch assertion discriminates. This is the headline of
CL10 and it is now settled by measurement.**

```
d76b649   PASS P11 exactly ONE relaunch, not a second one at the healthy player
          PASS P11 and the player lock recorded exactly one intent for it
396a69a   FAIL P11 exactly ONE relaunch, not a second one at the healthy player (got '2', want '1')
          FAIL P11 and the player lock recorded exactly one intent for it (got '2', want '1')
```

Compare wave two (QA-RESULTS D4), where `PASS P11 exactly ONE relaunch` appeared
in **both** summaries. The assertion has moved off a string only the fixed tree
emits and onto the intent counter, both sides of the lock, and it reads 1 here
and 2 there - exactly the prediction wave two made from three live
wedge-and-respawn runs. The assertion floor
(`the harness ran every check it has`) holds on both trees, 85 executed either
way, so D-PLY-9's class stays closed.

The 22 baseline failures are P11 (6), P12 (4), P13 (7) and P14 (5), which is the
rule-11 evidence those four scenarios were written for.

**PLY-H17 and PLY-H18 fail on behaviour, not on a broken setup.** On `a939fd7`
every positive control still passes - the cold start completed, it really did
spawn rather than adopt, the channel change landed while the start was parked,
the start carried the first intent, `status` answered, the player really is
running - while the behavioural checks read the old tree's answers: the player
took **2** loads where it must take 1, the channel left playing is
`t:qa.plain` where it must be `t:qa.live`, and the title the user reads names it
too. The three `(forward guard only)` checks read `NOFIELD` and are labelled in
the output as guards rather than as evidence, which is the right treatment.

**PLY-H18 phase B against `a939fd7` is a new measurement** - the display half
had never been run against another tree. Its result is the CL6 contract made
visible: `FAIL PLY-H18 the player is back on the channel the user chose (CL6)
(got 't:qa.plain', want 't:qa.live')`. The old tree leaves the player on the
impostor forever, which is precisely what wave two measured by hand.

**Finding F2, in the same family this round exists to catch.** In that same run,
`PASS PLY-H18 the shell never relabelled itself from the player (CL5)` appears
in **both** summaries. It is true on both trees for different reasons - the
fixed tree repairs, the old tree simply never looked - so it is a regression
guard and not evidence, and the runner's own rule (`cmd_list`: "A scenario that
passes on both trees is a regression guard, not evidence - label it as one")
says it must be labelled. PLY-H17's three such checks carry
`(forward guard only)`; this one carries nothing. One string, same defect class
as CL10.

Also confirmed live: the CL14 fix is doing its job. The baseline runs really did
execute the exported tree's helper - the transcript shows
`env OMARCHY_IPTV_PLUGIN_ROOT=/run/user/1000/omarchy-iptv-qa-player/baseline-a939fd7`
and the replies come back missing fields only today's helper emits. A run that
had silently used today's helper could not have produced `NOFIELD`.

### L4. The claims that went through the broken baseline, re-run (CL14)

Re-run through the corrected path, with the control each one needed.

| Claim, as recorded | Path it took | Re-run result |
|---|---|---|
| `baseline PLY-H17 a939fd7` = 6 pass / 6 fail (51e0f39) | the scenario runner, **after** the fix | **HOLDS.** 6 / 6, identical |
| `baseline PLY-H18 a939fd7` = 4 pass / 4 fail (51e0f39) | the scenario runner, **after** the fix | **HOLDS.** 4 / 4, identical |
| `run cold --apply` = 20 pass / 0 fail (51e0f39) | the scenario runner | **HOLDS.** 20 / 0, identical |
| node gate: this tree `{"intents":1,"seqDelta":1}` 1000/0; `Service.qml` from `396a69a` `{"intents":2,"seqDelta":2}` 1000/1 (78418c9) | never the runner - `IPTV_SERVICE_QML` reads the other tree's own source | **HOLDS.** Reproduced verbatim, and the one failure at `396a69a` is that check and nothing else |
| python: `test_player.py` 77 tests 4 red, `test_mpv.py` 24 tests 2 red against the pre-change helper (c2a197d) | never the runner - today's tests loaded against the older `bin/omarchy-iptv` | **HOLDS.** 77 tests / 4 red and 24 tests / 2 red, and the assertion texts are the ones the commit quoted: `'BBC One HD' != 'ESPN'` and `2 != 1` |
| `player-scenario.sh --baseline` evidence, all rounds | never helper-pinned | **UNAFFECTED**, verified in source at `396a69a`, `a939fd7` and `d76b649`: all three spell the helper `$PLUGIN_ROOT/bin/omarchy-iptv` |

**The control that makes the python re-run mean something:** the same mixed tree
(today's `tests/`, the older `bin/`) with today's helper dropped back in is
**green on both suites, 77/77 and 24/24**. The six reds are the helper, not the
arrangement.

**Nothing in this round was an artefact of the pinning, and there is a
searchable reason.** The pinned `HELPER` lived only in
`scripts/qa-player-scenarios.sh`; `player-scenario.sh` has always used
`$PLUGIN_ROOT`. The only asserting scenarios that runner has ever had are
PLY-H17 and PLY-H18, and both were written in `51e0f39` - **the same commit that
fixed the pinning**. PLY-H11 to PLY-H16 assert nothing at all (the plan's own
item B1), so they could never have produced a claim. The blast radius CL14
feared is empty. That is not an argument against the ruling: the check was
cheap, and "empty" is only knowable by running it.

### L5. What else a real shell settled

**D-PLY-8, the socket case.** PLY-STOP-03, 5 wedged and 5 responsive: in
**10 of 10** the socket is already gone at **t+0.2 s** and still gone at t+1 s,
t+5 s and t+30 s, with no helper call of QA's own in between. The
`stopSettleTimer` backstop line (`the player outlived a stop`) is absent from
the journal in all ten. The runtime directory after each stop holds
`player.lock`, `shader-cache` and `watch-later` and nothing else.
**D-PLY-8 does not reproduce at `d76b649`**, as at `a939fd7`.

**The teardown window on a real windowed mpv**, five SIGKILLs with
`/proc/<pid>/cmdline` and `connect()` sampled in a tight loop from the instant
of the kill:

| Run | RSS | cmdline empty | socket refused | blind-to-unbound window |
|---|---|---|---|---|
| 1 | 146 MB | 0.231 ms | 12.923 ms | **12.693 ms** |
| 2 | 146 MB | 0.180 ms | 23.353 ms | **23.173 ms** |
| 3 | 144 MB | 0.323 ms | 18.199 ms | **17.876 ms** |
| 4 | 144 MB | 0.274 ms | 24.970 ms | **24.696 ms** |
| 5 | 146 MB | 0.301 ms | 9.912 ms | **9.611 ms** |

- `find_player()` goes blind first at **0.18-0.32 ms**, 5/5. The hypothesis
  corrected in wave two's X4 stays corrected on a second independent run.
- Every window is still **above** the 4-8 ms observation point the shipping
  single-shot settle used, 5/5, so the premise the fix rests on holds.
- **Finding F3:** CL12 records the residue as "fifteen to thirty-seven
  milliseconds". This pass measured **9.6 to 24.7 ms**. The floor is lower than
  recorded - 9.6 ms clears 8 ms by 1.2x, not by the 2x the recorded range
  implies. The conclusion does not change; the recorded bound should.
- CL12's refusal to write proportionality down survives again: 144-146 MB
  produced 9.6 ms and 24.7 ms in the same series, no ordering by size.

**PLY-PERF-02 under CL1** (the budget is met when the player process is gone,
measured by polling `kill -0` from the instant `stop` was issued):

| Path | Runs | Player gone | Budget | Verdict |
|---|---|---|---|---|
| Wedged (`kill -STOP` first) | 5 | **4248 / 4260 / 4270 / 4274 / 4279 ms** | 4500 ms | **met 5/5** |
| Responsive | 5 | **293 / 305 / 334 / 361 / 372 ms** | 500 ms | **met 5/5** |

The stop command itself returned in **59-81 ms** in all ten; under CL1 that is
not the budget. The wedged figures sit inside `a939fd7`'s 4268-4299 ms and
~200 ms clear of the ceiling. **Interface clear is recorded as a bound, not a
verdict** (CL13): 62-168 ms on a poller whose own sample costs ~57 ms. The
150 ms budget still cannot be decided at this resolution and is still not
recorded as a regression.

**D-PLY-10, the contained cache.** `~/.cache/mpv` is **unchanged**: the same 46
file names before and after, and **0 files newer than the start of the pass**
after roughly forty minutes of windowed playback and about seventy player
starts. `$XDG_RUNTIME_DIR/omarchy-iptv/shader-cache` exists at **0700** inside a
**0700** parent and holds **26 files, all at 0600**, including both names
D-PLY-10 originally filed (`shader_2a337003854863bf`,
`shader_94d4454b832de9f8`), written during this pass. The player's argv carries
`--gpu-shader-cache-dir=` and `--icc-cache-dir=` pointing there, ahead of any
user token. No new top-level entry in `$HOME`. **D-PLY-10 stays closed.**

**S-03 and the privacy sweep.** The live player's full command line is fourteen
tokens and carries **no URL, no credential, no token, no header value and no
channel name** - `qa-user`, `qa-secret`, `qa-token-XYZ`, `qa-ua-SENTINEL`,
`qa-ref-SENTINEL` and `://` all return 0 against it, with the sentinel channel
playing. The shell journal across the whole pass is 397 lines with **0 needles
and 0 URLs of any kind**. Omarchy's own notification history holds 10 files with
**0 needles**.

**CL15 confirmed still open, as ruled.** Neither `scripts/qa-sources-scenarios.sh`
nor `scripts/dev-harness/sources-scenario.sh` contains the word `baseline`. No
scenario in that suite has been shown capable of failing. Next round, per the
ruling.

### L6. Findings handed on

1. **D-CL-1 (new, P4, cosmetic-diagnostic).** The stand-down journal line
   `a newer channel change reached the player first (intent %d over %d)` can
   **never** print two different numbers on the only path that reaches it.
   `cmd_play` takes its seq from the lock record
   (`record_seq(read_lock_file(sock))`, `bin/omarchy-iptv:1819`) because CL4
   withholds a `--seq` of its own; during a cold start the lock record is the
   start's, so the zap borrows the start's number. All five live stand-downs
   printed `(intent 662 over 662)`, `(intent 654 over 654)`, and so on. Commit
   3ea61b7 added those two numbers as "the one thing a person reading a journal
   needs to tell a stand-down from a crash"; as written they tell the reader
   nothing. Either print something that does differ (the entry id, or the
   stash's `verb`) or drop the parenthetical. Not a functional defect - the
   stand-down itself works, 5/5.
2. **F2 (new, minor, same class as CL10).**
   `PLY-H18 the shell never relabelled itself from the player (CL5)` passes on
   both trees and is not labelled a regression guard, contrary to the runner's
   own stated rule and contrary to how PLY-H17's three such checks are handled.
   One string in `scripts/qa-player-scenarios.sh`.
3. **F3.** CL12's recorded socket-residue range (15-37 ms) has an optimistic
   floor; this pass measured 9.6-24.7 ms on the same class of player. Record the
   wider range. The ordering and the conclusion are unaffected.
4. **F4, recorded not filed.** The CL5 repair costs one extra `loadfile` on the
   cold burst path: entry id 3 in 12 of 20 runs where wave two read 2 in 18.
   That is the correct trade and it is cheap, but it is a real behaviour change
   and the design document should say so where it describes the repair.
5. **F5, recorded not filed.** The repair can still be in flight six seconds
   after a cold burst - seen once, in the rig's shakedown run, converged by
   t+20 s. Wave two's divergences never converged at all. If anyone wants the
   invariant stated as a latency rather than as "within one health tick", that
   is the measurement to take.
6. The runbook's "five recents" is still stale; the machine has seven. Third
   pass in a row this has been recorded.

### L7. Restore

Proved at 13:05. The machine was touched in exactly two ways and both are
undone: `playlistUrl` pointed at the loopback fixture, and the installed clone
checked out detached at `d76b649`.

- `~/.config/omarchy/shell.json` - **byte-identical**, `sha256sum -c` OK, and
  `playlistUrl` reads `https://iptv-org.github.io/iptv/countries/us.m3u` again.
- `~/.local/state/omarchy-iptv/` and `~/.cache/omarchy-iptv/` - `diff -r`
  **empty** and **every file checksum identical** to the pre-pass manifest,
  held 25 s with the shell running.
- The mode/owner manifest over both trees plus `shell.json` **diffs empty**.
- Installed clone back on **`main` at `d44dc6e`, tracking `origin/main`**, 0
  modified and 0 untracked, and `diff -r` against the pre-pass backup is
  **empty**. `origin/main` was never moved; `d76b649` was fetched from the local
  repository into `FETCH_HEAD`.
- `status` **diffs clean** against `status.before.json` apart from
  `lastUpdated` and `player.seq`: 1,474 channels, source `d5977d8a` on
  `iptv-org.github.io`, 7 recents, 0 favorites, `nowPlaying` null, `playing`
  false. `player.seq` is the live intent counter and is not durable state.
- `$XDG_RUNTIME_DIR/omarchy-iptv` back to `700` holding `player.lock` and an
  empty `watch-later` - the mode manifest **diffs empty** against the pre-pass
  one; the socket and the `shader-cache` directory this pass created were
  removed.
- Theme `Retropc`, unchanged. `$HOME` has no new top-level entry.
- Nothing left running: **0** mpv, **0** `omarchy-iptv` windows, **1**
  quickshell (the user's, on `/usr/share/omarchy/shell`, restarted and
  screenshotted healthy with the bar and the plugin glyph back), port 8791
  closed, the fixture server stopped, and both harness scratch trees this pass
  created (`omarchy-iptv-qa-player`, `omarchy-iptv-harness`) removed. **0**
  `hyprlock`. No logout.
- The working repository at `/home/ricky/Projects/omarchy-iptv` is clean at
  `d76b649` with no untracked files. **Nothing was committed.**
- **Worth knowing, not damage:** every shell start refetched the user's own
  source, because the restored cache had aged past its TTL, and that bumps
  three timestamp fields (`fetchedAt`, `generatedAt`, `durationMs`). The
  refetched channel set was proved identical - same 437,554 bytes, same 1,474
  channels, identical id set - and the snapshot was written back as the final
  on-disk act and verified holding. The same refresh would happen on the user's
  next login with or without this pass.
- Not restored, deliberately: `~/.cache/mpv`, which was never written to; the
  ten Omarchy notification-history files, which are the host's own; and
  `$XDG_RUNTIME_DIR/omarchy-iptv-qa-sources`, which predates this pass
  (2026-09-13).

### L8. Release recommendation for this round

**Go.** Every claim the round rests on was re-measured on real hardware and
every one held.

- The defect the round exists for is **0 of 20** where it was 10 of 20, with
  both halves of the fix witnessed in the journal - the helper standing down 5
  times and the shell re-applying 12 times - and the two controls unchanged at
  0 of 10 warm and 0 of 6 cold-serial.
- CL6's invariant now has an outcome test and passes it: convergence in
  **4.5 s against a 10 s tick, 4/4**, with `nowPlaying` never once relabelled
  across 120 samples. That is the ruling honoured in the direction CL5 asked
  for.
- The repointed assertion **discriminates**: `PASS` here, `FAIL (got '2', want
  '1')` at `396a69a`, where wave two found it passing on both trees.
- Every downgraded claim **holds**; none was an artefact, and the reason is
  structural rather than lucky.
- Every budget met, with the same margins as the last two passes, and the two
  closed defects (D-PLY-8, D-PLY-10) stay closed.

The two new findings (D-CL-1, F2) are both diagnostics rather than behaviour -
a journal line that cannot say what it was written to say, and a check that
needs a label - and neither gates a release. F3 asks for a recorded range to be
widened, not for a conclusion to change.

## M2-03 channel numbers live pass, and a real-provider exploratory pass on 0ef73ed (QA, 2026-09-14, 17:04 - 17:34)

Owner: QA. Live pass on the machine of record against the **installed** plugin, not
the harness. Two halves: the M2-03 live items of `docs/M2-03-CHANNEL-NUMBERS.md`
section 10.7 that only a real compositor, font and keyboard can settle, and an
exploratory pass against the product owner's own IPTV provider lists.

### C1. Header

| Item | Value |
|---|---|
| Code under test | `0ef73ed` (docs: document channel numbers in the README). The installed clone at `~/.config/omarchy/plugins/io.github.rmcdavid.iptv` was moved from `main` at `5d1a27e` (v0.3.1) to a **detached HEAD at `0ef73ed`**, fetched from the local repository into `FETCH_HEAD`. `origin/main` was never moved. `diff -r --exclude=.git` between the installed clone and the working tree was empty apart from untracked build artefacts |
| Gates at start | `omarchy plugin validate .` exit 0. `scripts/check.sh` **all green**: 1150 node checks, 318 python tests, 56 qml cases, 121 harness predicate checks, ascii ok (61 files), control-byte ok (44 files) |
| Mode | live Omarchy shell (`quickshell -n -p /usr/share/omarchy/shell`), driven with `wtype` for keys, `grim` for evidence and `omarchy-shell <id> <verb>` for IPC. `pgrep -x hyprlock` was checked before every keystroke batch and was 0 throughout. No logout |
| Machine | Omarchy, Hyprland, one monitor `eDP-1` 1366x768 scale 1, theme **Retropc**, JetBrains Mono, mpv present, node 26.8.1, Python 3.14.7 |
| Evidence | `/tmp/claude-1000/omarchy-iptv-qa11/`: `before/` (pre-pass snapshot of `shell.json`, the whole state directory, the whole cache directory, the whole installed plugin clone, plugin HEAD and mode manifest), `shots/` (60+ `grim` captures and ImageMagick crops), `check.out`, `CHANGED.txt` (the running list of every machine change and its undo), `status.before.json` / `status.after.json` |
| Numbered fixtures | `gen-playlist.py --profile realistic --numbering blocks --channels 3000 --groups 120 --seed 7 --epg-ids 0.6`, sha256 `de376228478d76d7...f7ca2`, generator line: `numbering=blocks numbered=3000 block=100 gaps=408 subchannels=88 duplicates=58 highest=12029`. Plus a hand-built 17-row `edge-labels.m3u` covering every label width 1 to 9 and every non-numeric form, and a 3-row `bar-num.m3u` served over `127.0.0.1:8799` so the bar could be tested with a stream that actually plays |
| Ruling CN13, recorded as asked | The product owner's real provider lists **carry no channel numbers at all: 0 of 5,221 channels across all four lists** (`USChannels.m3u` 3,335, `SportsPPVAll.m3u` 1,833, `Kids.m3u` 48, `Default.m3u` 5); no `tvg-chno`, no `tvg-channel-number`, no `channel-number`. The only attributes present are `tvg-id`, `tvg-name`, `tvg-logo`, `group-title`. So every numbering result below rests on the generator, exactly as CN13 anticipated, and `docs/QA-ASSETS.md` still has no numbered row |

**Credential handling.** The provider lists embed account credentials as two
path segments in every stream URL. Everything in this pass was driven from the
**local 0600 copies by file path**; the credentialed playlist URL was never
configured, never typed, never screenshotted and never written to any file.
The real URL is **not recorded anywhere in the scratch copy**, so the
"configure the real URL once to prove the fetch path" check was **skipped and
is reported as skipped** - the fetch path over https remains covered by the
user's own iptv-org source, which is fetched on every shell start. One real
channel was played from the real list (section C9), which contacts the
provider with the credentials in the URL as it must; the redaction result is
recorded there. The credential sweep is section C11.

### C2. What only a live pass can prove - section 10.7, item by item

| # | 10.7 item | Result | Evidence |
|---|---|---|---|
| 1 | Number column optically aligned at real JetBrains Mono metrics | **pass** | `shots/07-col-zoom.png`, `28-zoom.png`, `29-zoom.png`. Right-aligned on a single edge at every width. Verified across labels of 1, 2, 3, 4, 5, 7, 8 and 9 characters in one list (`edge-labels.m3u`): `1`, `7`, `7.1`, `8.1`, `12`, `42`, `123`, `1234`, `12345`, `99999`, `99999.9`, `99999.99`, `99999.999` all share one right edge and every name starts at the same x. Dimmer than the name (secondary token), never bold |
| 1a | ...and truncates sanely | **pass, with a cosmetic note** | Nothing truncates. `chnoColumnUnits` clamps to 56 units, so the 9-character maximum label overflows **leftward** out of its box rather than eliding - which is the right choice, because a truncated channel number is an unusable channel number. At 9 characters the label sits flush against the group-column divider with roughly 20 px of clearance left; at the 3-to-5 characters a real provider uses there is ample inset. Recorded as cosmetic, not a defect |
| 2 | U+F061C renders as a dialpad, not tofu | **pass** | `shots/09-chip-zoom.png` at 700%: a 3x3 grid of dots with a single dot below - a keypad, correctly shaped, at `Style.font.icon` in the live guide's font stack. No tofu box |
| 3 | 1500 ms is the right default | **pass as shipped; a change is recommended** | See C4 |
| 4 | Digit keys survive the real `PanelKeyCatcher` chain on a layer-shell surface with exclusive keyboard focus, numpad included | **pass** | Top-row digits: `shots/09-entry-101.png`. **Numpad**: `wtype -k KP_1 KP_2 KP_3` produced buffer `12` then an auto-commit on `123` (`shots/11-crop.png`, `12-crop.png`) - the keypad path works through the live key chain. A real AZERTY layout switch was **not** performed, so ruling CN16's shifted-digit case remains proven by the gate A1 demonstration rather than by this pass |
| 5 | The chip covering the first row's `until HH:MM` is acceptable in practice | **not proven** | No EPG was configured on the numbered fixtures, so the chip covered empty space. The chip is top-right anchored over the first row and is opaque; with an EPG loaded it would sit on that row's time. Still open |
| 6 | `positionViewAtIndex` per digit does not stutter at scale | **pass** | Per-digit re-positioning over a 3,000-row list was visually instant in every capture; see also C8 for 3,335 rows at 25 ms per paged move |
| 7 | A real numbered provider exists | **fails, as predicted** | 0 of 5,221 channels numbered. Recorded under CN13 above |
| 8 | The bar's number does not fight `barLabelMaxWidth` on a crowded real bar | **pass** | `shots/34-bar-long-zoom.png`. On the user's real bar (tray, iptv, netspeed, agents, bluetooth, network, audio, monitor, dell-power) the widget rendered `12345 A Very Long Channel Name...`: the **number is never elided, the name is**, which is the correct precedence since the number is the addressable part |

### C3. Scenario results driven on the live surface

Scenarios N1-N16 and N21-N24 have no runner. `docs/M2-03-CHANNEL-NUMBERS.md`
section 10.6 specifies harness verbs `number`, `numberState`, `commitNumber`
and `cancelNumber` on `IpcHandler { target: "harness" }`; **none of the four was
ever implemented**, and `state()` was not extended with `numberEntry` /
`hasNumbers` on the guide side. That gap is F-CHNO-3 below. Everything here was
therefore driven with real keystrokes and read off the footer and the chip.

| # | Scenario | Result | Evidence |
|---|---|---|---|
| N1 | Live preview per digit | pass | `1`, `10`, `101`: chip tracks the buffer, cursor moves to the lowest match each time (`shots/08-*`, `09-entry-101.png`) |
| N2 | Timeout commit | pass | after 1.5 s: chip gone, cursor still on 101, footer `Channel 101 - Delta Food [Not 24/7]` (`shots/10-after-timeout.png`) |
| N5 | Backspace | pass | `10` then Backspace leaves buffer `1` (`shots/16b-chip.png`) |
| N6 | Backspace to empty cancels and restores | pass | parked on 900, typed `10`, two Backspaces: entry off, cursor **restored to 800 Quantum Cinema**, footer restored (`shots/21b-bs-empty-f.png`) |
| N7 | Esc cancels, guide stays open | pass | parked on 900, typed `10`, Esc: entry off, **guide still open**, cursor exactly back on 900, list-mode hints back (`shots/20c-esc-f.png`) |
| N8 | Unknown number | **partial - see D-CHNO-2** | `10003` (whose every prefix stays ambiguous) gives live `Channel 10003 - no match` in the chip and footer, then committed `No channel 10003` (`shots/24b`, `24c-f.png`). But a number whose prefix is an unambiguous channel never reaches that message |
| N10 | Scope hop | pass | scoped to `Series`, typed `123`: scope became `All`, cursor on 123 in `UK \| Shop` (`shots/25a-full.png`, `25b-full.png`) |
| N11 | Subchannel, both separators | pass | `100` `.` `1` committed to `Channel 100.1 - Frost Comedy`; `100` `,` `2` committed to `Channel 100.2 - Metro Cinema`. The comma folds to `.` on a live surface, as CN8/CN17 require (`shots/14-crop.png`, `15-footer.png`) |
| N12 | Duplicate cycling | **fail - D-CHNO-1** | three consecutive commits of `301` all report `(1 of 2)` and all land on Metro Cinema (`shots/22a/22b/22c`) |
| N13 | Unambiguous auto-commit | pass | `123` committed at roughly 450 ms, well before the 1.5 s timer (`shots/12-crop.png`) |
| N14 | No numbers | pass | proven on the **user's real list**, section C5 |
| N15 | Keypad digits | pass | see 10.7 item 4 |
| N17 | Sort by number | pass | `100, 100.1, 100.2, 101, 102, 103, 104, 104.1, 106` - subchannels sort between their major and the next major, gaps visible (`shots/26-full.png`) |
| N18 | Sort flip at runtime | pass | `omarchy bar set ... channelOrder number` re-ordered the live list with **no helper run**: `channels.json` mtime unchanged at 17:10:45 |
| N19 | IPC verb | pass | `channel 123` -> `{"ok":true,...,"chno":"123","name":"Dusk Action [Not 24/7]"}`; `channel 0123` -> the same id; `channel 20509` -> `{"ok":false,...,"code":"unknown_chno","message":"no channel 20509"}`. `status \| grep -c '://'` -> **0** |
| N20 | Bar | pass | `501 Bar Number One` with the setting on; the name alone with `barShowChannelNumber false`; both applied live with no restart (`shots/33b-bar2.png`, `35-zoom.png`) |
| CN20 | The verb must never cycle | pass | `channel 301` three times returned the **same** id `u:c10dfe30` every time |
| - | `numberEntryMs` clamp | pass | set to `99` (below the 400 minimum): a 300 ms inter-digit gap still held one buffer, so the value was clamped up rather than taken literally (`shots/38-chip.png`) |
| - | Non-numeric / empty / absent `tvg-chno` | pass | `N/A` and `HD` render as **nothing**, the slot stays blank and the name stays aligned (CN6). `00042` displays as `42` (CN7), `8-1` as `8.1` (CN8) (`shots/29-zoom.png`) |

### C4. The digit timeout, and what I would change it to

The timer was measured on the live surface, not read off the setting. At the
1500 ms default an inter-digit gap of **1.20 s holds one buffer** (chip `50`)
and a gap of **1.80 s splits it** (the `5` commits alone, the `0` opens a new
entry reading `0 - no match`): `shots/36a-chip.png`, `36b-chip.png`. Raising
the setting to 2000 ms made the 1.80 s gap hold (`shots/37-chip.png`), so the
setting is live and effective across its range.

The decisive measurement is how often the wait applies at all. Against the
3,000-channel provider-shaped plan, **2,739 of 2,942 distinct numbers (93.1%)
auto-commit the instant the final digit lands**, because no longer number
extends them. Only 203 numbers (6.9%) wait out the timer - 97 three-digit, 90
four-digit, 16 five-digit - and those are exactly the numbers that are a strict
prefix of a longer one (`101` while `1010`-`1019` exist). Even then nothing is
blocked: the cursor has **already** moved to the target during the live
preview, and Enter or Space commits immediately. The timeout gates only the
chip disappearing and the footer gaining the channel name.

**Judgement: 1500 ms is not too slow and not too fast; it is defensible as
shipped and nothing here blocks a release. I would still change the default to
2000 ms.** The two failure modes are not symmetric. Too long costs a stale chip
in 7% of tunes, on a target the user can already see and can commit instantly.
Too short splits a number and silently tunes the user to a wrong channel, which
is a hard failure and the exact accessibility concern ruling CN2 names. 2000 ms
is also the television convention the design cites, and it buys a slow or
motor-impaired typist real headroom on four- and five-digit numbers at no
perceptible cost. **Recommended default: `numberEntryMs` 2000**, range
unchanged at 400-5000.

### C5. The no-numbers message, confirmed on the real list

With the user's own `USChannels.m3u` active (3,335 channels, `hasNumbers false`),
pressing a digit in list mode shows, in the footer's left slot:

`No channel numbers in this playlist`

and the hint line correctly **omits** `0-9 channel`, reading
`j/k move - h/l group - Enter play - Space preview - f favorite - s stop - r refresh - / search - o sources`.
No number column is drawn and the row lead slot collapses so names stay
aligned. `shots/42-f.png`, `41-full.png`. This is what the product owner will
actually see on their own provider, and it is correct and quiet.

### C6. Exploratory pass - a 3,335-channel list in ONE group

`USChannels.m3u`: 3,335 channels, **one** `group-title`, `United States`, for all
of them. Helper parse 186 ms, 0 warnings, 0 duplicate ids, names containing
commas parsed correctly (12 of them, e.g. `US CBS (KYES) Anchorage, Alaska (A)`),
no attribute bleed into any name. Nothing about the parse is wrong. What breaks
is the browsing model.

**Defect**

| id | Severity | Finding |
|---|---|---|
| D-SG-1 | P3 | **On a single-group list the group name pollutes every search.** `searchKey` is `name + " " + group`, so for this list every key ends `... united states`. Any query that is a substring of `united states` therefore matches **all 3,335 channels**: `st`, `sta`, `stat`, `ni`, `es`, `tes`, `ited`, `unit` each report `total=3335`. The ranking tiers save the user - typing `st` still puts `USA STARZ ENCORE WESTERNS`, `USA STARZ`, `USA STARZ ENCORE ACTION` at the top - so this is not a correctness failure. What fails is the reporting: the header says `in All - 3,335 matches` and the footer says `First 200 of 3,335 - keep typing` when only 19 channels genuinely match `starz`. The count and the hint actively mislead, and 3,316 irrelevant rows sit one arrow-key below the real answers |

**Usability findings - things that work correctly and are still bad at this size**

1. **The group column is dead weight.** It shows `Favorites 0`, `All 3,335`, a
   `GROUPS` heading and a single entry `United States 3,335`, then roughly 340 px
   of blank column down to the pinned `Sources` row. That column is about 200 px
   of a 960 px card - **21% of the guide's width doing nothing** - on the one
   list shape where horizontal room for long provider names matters most.
2. **`All` and the only group are the same list, offered as two controls.**
   Identical contents, identical counts (`3,335` twice, stacked six rows apart),
   and selecting either changes nothing. The hint still advertises `h/l group`
   when there is nowhere to go.
3. **Every row's second line reads `United States`.** 3,335 identical group
   labels, zero information, consuming the second line of every row. Rows are
   about 56 px; without that line they would be about 36 px and the viewport
   would hold roughly 14 channels instead of 9 - **a ~50% density loss** paid
   for a word the user already knows.
4. **There is no position indicator.** No scrollbar, no `row N of 3,335`, no
   letter rail. After 40 paged moves into the list (`shots/58-full.png`) the
   header still says `All - 3,335 channels`, the column still says
   `United States 3,335`, and every row still says `United States`. The user
   has no way to know where they are or how far is left. With dozens of groups
   the group column is the landmark; with one group there is none.
5. **A number jump lands the target flush on the bottom edge** of the viewport
   every time (`shots/09`, `12`, `18b`, `25b`). The scroll is minimal-effort
   `Contain` behaviour, which is correct in the small but means the eye must
   hunt at the very edge after every jump. Centring the target, or leaving one
   row of margin, would read far better.
6. **The footer status elides early.** `USChannels.m3u - 3,335 channels - updated 17:...`
   and `Added edge-labels.m3u - 17 channels in 1 gr...`: the left slot loses its
   tail to the hint line at this card width.

**What held up well at this size, and is worth recording**

- **Guide open time: median 69 ms against a 59 ms `shell ping` baseline, so
  about 10 ms of real open cost** over six open/close pairs - an order of
  magnitude inside the 150 ms budget, with 3,335 channels in one scope.
- **Search stays responsive.** Worst measured `filterChannels` was **3.8 ms**
  (`es`, 3,335 matches); `espn` 0.4 ms / 8 matches, `pluto` 0.9 ms / 2,227,
  `usa` 0.5 ms / 902. `prepareChannels` 6.7 ms for the whole list.
- **Ranking quality against prefixed, repetitive provider names is good.** The
  list is dominated by `(PLUTO ...)` (2,217 channels) and `USA  ` (484) prefixes
  and 3,324 of 3,335 names are unique. `espn` returns 8 rows in a sensible
  order - `USA ESPN`, `ESPN 2`, `ESPN NEWS`, `ESPN U`, `ESPN DEPORTES`, then the
  odd-prefix variants. The shared prefixes do **not** dominate the ranking.
- **The 200-row cap is handled honestly**: `First 200 of 2,227 - keep typing`,
  with the true total in the header. In list mode with no query the full 3,335
  rows scroll uncapped, at 25 ms per paged move with no stutter and no blank rows.
- **Favourites and recents work.** Three channels favourited (`f`), star drawn
  in the row lead slot, `Favorites 3` in the column, footer `Added to Favorites`,
  and the `Favorites - 3 channels` scope lists exactly those three
  (`shots/59-full.png`, `60-full.png`). After one play a `Recent 1` scope
  appeared - recents are correctly filtered to the active source, so the seven
  recents belonging to the user's iptv-org source stayed hidden
  (`shots/62-full.png`).
- **Playback from the real provider works end to end.** `USA  FOX NEWS` played,
  video rendered, `playing true`, `lastError` empty (section C9).

### C7. New defects (rows for docs/STATUS.md)

| id | Severity | Title and detail |
|---|---|---|
| D-CHNO-1 | **P2** | **Duplicate cycling never advances from the guide, so an HD twin is unreachable by number.** Ruling CN9 and scenario N12 are not met. Three consecutive commits of `301` all report `Channel 301 - Metro Cinema (1 of 2)`. `Model.resolveChno` is **correct**: given the first match's index it returns the second - `resolveChno(idx,"301",34)` -> `{ci:35, ord:2, matches:2}`, and from 35 it returns 34. The fault is which index the guide hands it. Each intermediate digit resolves and **moves the cursor**: buffer `3` -> channel 300 at index 2, `30` -> index 2, so when the final `301` resolves the live cursor is on index 2, not on the previous match, and the cycle restarts at ordinal 1. Because every prefix of a duplicate number resolves to some *lower* number, this can essentially never work for a multi-digit plan. Finding, not a diff: resolve the committed buffer against the entry's **pre-entry snapshot** `cursorIndex` (which `pushNumberKey` already captures) rather than the live cursor |
| D-CHNO-2 | **P2** | **A number that does not exist can silently tune to a different channel instead of saying so.** Typing `20509` on the 3k fixture landed the cursor on **channel 900**, with the footer reading `Channel 900 - Terra Comedy [Not 24/7]` and no error anywhere. Mechanism: `chnoUnambiguous` fires the auto-commit on the proper prefix `205` (a real channel that no longer number extends), the entry closes, and the remaining `09` opens a **new** entry which resolves to 900. The design is self-consistent - auto-commit can only fire when no existing longer number is being typed - but the user asked for 20509, was moved twice, and never saw `No channel 20509`. Measured incidence on this fixture: **2,690 of 9,484 absent five-digit numbers in 10000-19999, 28.4%**, auto-commit early. Note the IPC verb is **not** affected: `channel 20509` correctly returns `unknown_chno`. Candidate fix for the owner to rule on: suppress the unambiguous auto-commit while the buffer is still shorter than the index's `maxLabelLen`, or restart the timer instead of committing when a digit arrives immediately after an auto-commit |
| D-SG-1 | P3 | Single-group search pollution and misleading counts. Detail in C6 |
| F-CHNO-3 | P3 | **The four harness verbs specified for M2-03 were never implemented.** `docs/M2-03-CHANNEL-NUMBERS.md` section 10.6 specifies `number`, `numberState`, `commitNumber` and `cancelNumber` on `IpcHandler { target: "harness" }`, and an extension of `state()` with `numberEntry` / `hasNumbers` on the guide side. None exists in `scripts/dev-harness/shell.qml`. Consequence: **scenarios N1-N16 and N21-N24 have no automated runner at all** and can only be driven by hand with `wtype`, as this pass did. Not a product defect; it is a hole in the regression net for the most intricate interaction M2 has shipped |
| F-CHNO-4 | P3 | `docs/STATUS.md:91` still records `M2-03 | Channel numbers + numeric zap | - | todo |` with no owner and no evidence, although M2-03 merged at `cc1d73e`. The board is stale |

Not defects, recorded as observations: a `git checkout` inside the installed
plugin directory makes the host emit about twenty
`Local plugin changed, reloading` DEBUG lines as files land one by one - host
file-watcher behaviour, harmless; and the helper **refuses `file://` stream
URLs** as unplayable (`empty_playlist`), which is a deliberate scheme filter
and was worked around here with a local HTTP server.

### C8. Performance

| Measure | Result | Budget |
|---|---|---|
| Guide open, 3,335 channels in one group | median **69 ms** vs `shell ping` median 59 ms -> about **10 ms** of open cost; 6 pairs, open range 67-72 ms | < 150 ms |
| Helper parse, 3,335-channel real list | **186 ms** (`durationMs`), 706,343 byte `channels.json` | < 1 s for 10,000 |
| `prepareChannels`, 3,335 rows | 6.7 ms median of 7 | - |
| `filterChannels`, worst case | 3.8 ms (`es`, 3,335 matches) | typing stays responsive |
| Paged scroll, 3,335 rows | 25 ms per `Page_Down`, 40 presses, no stutter | - |
| `buildChnoIndex`, 3,000 numbered | `hasNumbers true, count 3000, duplicates 116, maxLabelLen 7` | - |

### C9. Privacy at the sinks, with a real credentialed stream

One channel (`USA  FOX NEWS`) was played from the user's real provider, which
necessarily sends the credentialed URL to the provider. Every sink was then
checked:

- mpv window: class `omarchy-iptv`, **title `USA  FOX NEWS`** - the channel name
  only, no URL, no credentials.
- `omarchy-shell io.github.rmcdavid.iptv status | grep -c '://'` -> **0**, both
  while playing and after.
- `nowPlaying` carried `id`, `name`, `group`, `chno`, `launchedFrom`, `since` -
  no URL field.
- The one error surfaced during the pass was redacted to scheme and host:
  `Failed to open https://streams.example.test.` (a dead fixture host), which is
  the `Model.redactUrls` shape constraint 5 requires.
- The evidence screenshot of the playing window was reduced to a 12% thumbnail,
  inspected only to confirm a picture was rendering, and then **deleted**; no
  broadcast frame was retained.

### C10. Restore, proved

Changes made and undone are listed in `CHANGED.txt`: the installed clone moved
to `0ef73ed`; four temporary sources added through the guide's own Sources form
(`gen-num.m3u`, `edge-labels.m3u`, `bar-num.m3u`, `USChannels.m3u`); and
`omarchy bar set` writes of `channelOrder`, `numberEntryMs` and
`barShowChannelNumber`.

- `shell.json` **diffs empty** against the pre-pass snapshot; mode still `600`.
- The whole state directory **diffs empty**, mode manifest identical, mode `700`.
  State had to be written back a second time: the outgoing shell re-persisted
  its active source after the first restore, so the snapshot was re-applied as
  the **final on-disk act** and then **held for 25 s with the shell running**.
- The whole cache directory **diffs empty** and every file checksum matches;
  only `sources/d5977d8a` remains, the four temporary source caches are gone.
- The installed clone is back on **`main` at `5d1a27e`, tracking `origin/main`**,
  0 modified and 0 untracked; `diff -r --exclude=.git` against the pre-pass
  clone is **empty** and the mode/size manifest is identical. **`origin/main`
  was never moved**; `0ef73ed` was fetched from the local repository into
  `FETCH_HEAD` only.
- `status` matches the pre-pass snapshot: **1,474 channels, 28 groups**, source
  `iptv-org.github.io`, **7 recents, 0 favorites**, `nowPlaying` null, `playing`
  false, `lastUpdated 13:24`. The source was **not** refetched (its cache was
  still inside the 6 hour TTL), so not even a timestamp moved. `hasNumbers` and
  `channelOrder` are absent from `status` again, which is itself proof the
  installed code is back on the pre-M2-03 release.
- `$XDG_RUNTIME_DIR/omarchy-iptv` is back to `700` holding `player.lock` and an
  empty `watch-later`; the `shader-cache` directory mpv created during this pass
  was removed.
- Theme **Retropc**, unchanged. `$HOME` has no new top-level entry.
- Nothing left running: **0** mpv, **0** hyprlock, **1** quickshell (the user's
  own, restarted healthy on `/usr/share/omarchy/shell`), and the local fixture
  server on port 8799 was stopped **by pid** - 0 listeners.
- The working repository is clean at `0ef73ed`. **Nothing was committed.**
- One cosmetic side effect, disclosed: two stray keystrokes landed in the host
  application after the guide closed under me, opening its own navigation
  popup. Nothing was activated and no state was changed; there is no pointer
  automation on this machine to dismiss it, and it clears on the user's next
  click.

### C11. Credential sweep

Method: the two account path segments (10 characters each) were extracted from
the local playlist copy into shell variables inside a single command, never
printed, never written to disk, and passed to `grep -rIF -e` directly. The
provider host was swept for separately.

| Target | Account fragments | Provider host |
|---|---|---|
| `docs/QA-RESULTS.md` (the file this pass wrote) | **0** | **0** |
| Whole repo working tree, excluding `.git` | **0** | **0 files** |
| Evidence dir `/tmp/claude-1000/omarchy-iptv-qa11` | **0** | **0 files** |
| Session scratch dir `qa11` (fixtures, caches) | **0** | **0 files** |
| Restored user state dir | **0** | - |
| Restored user cache dir | **0** | - |
| `~/.config/omarchy/shell.json` | **0** | - |
| `$XDG_RUNTIME_DIR/omarchy-iptv` | **0** | - |
| **Filenames** of all 329 files created, 142 of them screenshots | **0** | **0** |
| **Raw bytes of every screenshot** | **0** | - |

**Zero hits everywhere.** Two further precautions: the only scratch artefact
that legitimately held the credentialed URLs - the `channels.json` produced by
parsing the user's list with the helper - was **deleted** at the end of the
pass; and the provider host is deliberately **not named** anywhere in this
document even though naming it would have been permitted. The credentialed
playlist URL was never configured in the plugin, never typed into any form,
never opened through the source edit form's reveal control, and never printed
to a terminal that a screenshot could capture. The one-time "configure the real
URL to prove the fetch path" check was **skipped**, because the URL is not
recorded in the scratch copy; this is recorded as skipped rather than passed.

### C12. Release recommendation for channel numbers

**Go, with two P2 defects filed against the numbering feature and neither of
them a release blocker.**

Everything the feature rests on was proven on real hardware: the column aligns
at real font metrics across every label width the grammar allows, the dialpad
glyph renders as a dialpad, digits and the numpad survive the live key chain,
both decimal separators work, Backspace and Esc restore the pre-entry state
exactly, scope hop works, number ordering places subchannels correctly, the
settings apply live and clamp, the IPC verb tunes and refuses correctly and
never cycles, the bar shows the number and never elides it, and the no-numbers
message is exactly right on the product owner's own list.

The two P2s are real and both are worth fixing before the feature is
advertised, but neither corrupts data, crashes, or blocks the primary gesture
of "type a number, land on it", which works. **D-CHNO-1** makes one documented
ruling (CN9, reach an HD twin by number) inert, and the model is already
correct so the fix is small. **D-CHNO-2** means a mistyped long number can move
you somewhere unexpected without an error; the same request through the IPC
verb reports the miss correctly, so the gap is in the guide's commit timing
rather than in the resolver.

The single-group exploratory half produced **no blocker at all** - one P3
search-reporting defect and six usability findings. The feature set is correct
at that shape; it is the browsing affordances that stop paying rent when a
provider ships 3,335 channels under one heading. That is a design conversation
for the product owner, not a release gate, and it is worth having because this
is the shape of the owner's own list.

## M2-05 picture-in-picture GATE pass on c4d4075 (QA, 2026-09-14, 20:46 - 21:12)

Task M2-05-00. Every row of `docs/M2-05-PICTURE-IN-PICTURE.md` section 3 was
run on this machine against a player **started through the plugin** on a channel
chosen for the pass. Nothing in the repo or in the installed plugin was
modified; this lane wrote only this file.

**Bottom line.** The mechanism is real and it works: eleven of thirteen rows
proven, one disproven in a way that costs the design nothing but removes an
optimisation and invalidates the gate's own probe, one unsettled for a reason
that cannot be removed by this lane. Two findings matter more than the score.
The legacy dispatcher spelling is not merely a fallback that never runs here -
it is **syntactically unparseable** under this compositor, which confirms open
question 8: **`Model.focusPlayerArgv()` is dead code in released software**, and
its test is green *because* the code is broken. Separately, **`hyprctl` reports
success for a dispatch that did nothing at all**, which breaks the failure
detection section 4.10 specifies.

### Environment

| Fact | Value |
|---|---|
| Hyprland | 0.56.2, commit `efb50993...`, tag v0.56.2, `dirty: false` |
| Config provider | `configProvider: lua` (from `hyprctl systeminfo`; **not** in `hyprctl -j version`) |
| `ecosystem:enforce_permissions` | `{"option":"ecosystem:enforce_permissions","bool":false,"set":false}` |
| `hyprctl configerrors` | empty |
| `binds:allow_pin_fullscreen` | `{"bool":false,"set":false}` |
| Monitor | `eDP-1`, 1366x768, scale 1, transform 0, reserved `[0, 26, 0, 0]`, x 0, y 0 |
| mpv | v0.41.0 |
| Shell | quickshell pid 1800527 (1943634 after the restart) |
| Plugin | installed copy `5d1a27e` (v0.3.1) on `main`, tracking `origin/main`, clean. Untouched. |
| Source | iptv-org.github.io, 1474 channels, 28 groups, theme Retropc |
| Channels used | `t:ReutersTV.us@SD` (decodes 1920x1080), `t:CookingPanda.us@SD` (decodes 1280x720) |
| Player window | class `omarchy-iptv`, pid 1937373, address `0x559c6893d940` |

### Gate results

| # | Verdict | Evidence |
|---|---|---|
| G-1 | **Lua form PROVEN. Legacy form DISPROVEN.** | See below - the headline result |
| G-2 | **PROVEN** | `player probe` -> `"pid": 1937373`; `hyprctl -j clients` -> `omarchy-iptv pid 1937373 0x559c6893d940`. Identical. No wrapper. `ps -o ppid= -p 1937373` -> 831 (user systemd), i.e. the window belongs to a process that is **not** a child of the shell. Correction to the gate command: `status` carries **no** `pid` key; the pid comes from `player probe` |
| G-3 | **DISPROVEN** | `action` is ignored; `float` and `pin` are toggle-only. Detail below |
| G-4 | **PROVEN, but not by the mechanism the design credits** | Detail below |
| G-5 | **UNSETTLED** | Cannot be run by this lane. Reason below |
| G-6 | **PROVEN** | Detail below |
| G-7 | **PROVEN** | `hyprctl --batch "dispatch hl.dsp.window.tag({...+b1}) ; dispatch hl.dsp.window.tag({...+b2})"` -> rc 0, `ok\n\n\nok`; tags read back `['b1', 'b2', 'default-opacity*', 'iptv-pip']`. Both applied |
| G-8 | **PROVEN** | `/usr/bin/hyprctl`; `HYPRLAND_INSTANCE_SIGNATURE=efb50993780079460b0cbed1363e2166a2de1d9f_1789339912_1242840277`; `$XDG_RUNTIME_DIR/hypr/` holds that one instance directory, mode 0700 |
| G-9 | **PROVEN (the negative holds)** | `strings -a /usr/bin/mpv \| grep -cE '^zwlr_layer_shell_v1$'` -> **0**; same grep over `/usr/bin/Hyprland` -> **1**. mpv 0.41.0 cannot reach the overlay layer |
| G-10 | **PROVEN** | `reserved [0, 26, 0, 0]`, 26 in slot 2 = top. `hyprctl -j layers`: `eDP-1 level 2 omarchy-bar 0 0 1366 26`. Confirmed visually: the box at y 42 sits clear of the bar |
| G-11 | **PROVEN - the translucency is real, not an inference** | Detail below |
| G-12 | **PROVEN** | Detail below |
| G-13 | **PROVEN (already-failed as expected)** | `PanelKeyCatcher.qml` signals at `:38-44` carry no modifier; `:71` is `if (event.key === Qt.Key_Return \|\| event.key === Qt.Key_Enter) { returnRequested(); activateRequested(); event.accepted = true; return }`. `Shift+Enter` is undeliverable. PIP1 stands, now with a citation |

### G-1 - the dispatch spelling. The design is right about the mechanism and right about the defect

Against the live player window, address `0x559c6893d940`:

```
# Lua form
$ hyprctl dispatch 'hl.dsp.window.tag({ window = "address:0x559c6893d940", tag = "+iptv-probe" })'
rc=0  ok
$ hyprctl -j clients | grep -c iptv-probe
1
  tags now: ['default-opacity*', 'iptv-probe']

# Legacy form, space spelling (the shipped one)
$ hyprctl dispatch tagwindow +iptv-probe2 address:0x559c6893d940
rc=7  error: [string "return hl.dispatch(tagwindow +iptv-probe2 add..."]:1: ')' expected near 'address'
      -> Note: dispatch in lua is a shorthand for hl.dispatch(...), your syntax might need to be updated.
$ hyprctl -j clients | grep -c iptv-probe2
0

# Legacy form, comma spelling (the one 2.5 tells lanes to copy from omarchy-capture-webcam-resize)
$ hyprctl dispatch tagwindow "+iptv-probe3,address:0x559c6893d940"
rc=7  error: [string "return hl.dispatch(tagwindow +iptv-probe3,add..."]:1: <name> expected near '0x559c6893d940'
$ hyprctl -j clients | grep -c iptv-probe3
0

# Removal, to prove the state is ours to undo
$ hyprctl dispatch 'hl.dsp.window.tag({ window = "address:0x559c6893d940", tag = "-iptv-probe" })'
rc=0  ok
  tags now: ['default-opacity*']
```

The mechanism is confirmed: `hyprctl dispatch` under a Lua provider wraps its
argument as `return hl.dispatch(<arg>)`, so a bare legacy dispatcher name is a
**Lua syntax error**, not an unknown-dispatcher error. Passing the legacy
command as a quoted *string* does not rescue it either:

```
$ hyprctl dispatch '"focuswindow class:zz-nonexistent-qa12"'
rc=7  error: return hl.dispatch("focuswindow class:zz-nonexistent-qa12"):1:
      hl.dispatch: expected a dispatcher (e.g. hl.dsp.window.close())
```

**There is no spelling of the legacy form that reaches this compositor.** The
design's plan - Lua primary, legacy fallback shipped for other people's
hyprlang Hyprlands - is correct and unchanged. The fallback must never be
expected to run here, and the service must not treat "the Lua step failed, try
legacy" as a recovery path on this host: it is a second guaranteed failure.

**One correction the lanes need.** Section 4.3's table and the decision row both
spell focus-adjacent verbs under `hl.dsp.window.*`. That namespace is right for
`float`, `pin`, `resize`, `move`, `tag` and `alter_zorder` - all present in
`/usr/share/hypr/stubs/hl.meta.lua:908-931` (`HL.DspWindowNamespace`) and all
verified live below. But there is **no `hl.dsp.window.focus`**:

```
$ hyprctl dispatch 'hl.dsp.focus({ window = "class:zz-nonexistent-qa12" })'    # correct
rc=0  warning: =[C]:-1: hl.focus: window not found
$ hyprctl dispatch 'hl.dsp.window.focus({ window = "class:zz-nonexistent-qa12" })'  # wrong
rc=7  error: ... attempt to call a nil value (field 'focus')
```

Focus lives at `hl.dsp.focus({ window = ... })`, one level up. That is the
spelling the PIP8 fix must use.

### The focus defect - D-PIP-1, confirmed by direct A/B on the live window

Open question 8 and ruling PIP8 are **confirmed**. `Model.js:2945-2947` returns
`["hyprctl", "dispatch", "focuswindow", "class:omarchy-iptv"]`. Run exactly as
shipped, with focus starting on another window and the player window present:

```
focus BEFORE: com.anthropic.Claude 0x559c687e09a0

$ hyprctl dispatch focuswindow class:omarchy-iptv
rc=7
error: [string "return hl.dispatch(focuswindow class:omarchy-..."]:1: ')' expected near 'class'
focus AFTER : com.anthropic.Claude 0x559c687e09a0      <- unchanged: the shipped command is a no-op

$ hyprctl dispatch 'hl.dsp.focus({ window = "class:omarchy-iptv" })'
rc=0  ok
focus AFTER : omarchy-iptv 0x559c6893d940              <- the fix works
```

The failure is silent in the product because `Service.qml:578` fires it through
`Quickshell.execDetached(Model.focusPlayerArgv())`, which returns void: rc 7
never reaches the plugin. Four call sites in the shipped copy depend on it -
`Service.qml:400` (play with `keepOpen` false), `:460` (`wantFocus`), `:577`
(the function) and `:2651`. Every one of them has been a no-op since v0.3.0.

**And the test cannot see it, exactly as `CLAUDE.md` 12 predicts.**
`tests/Model.test.js:455` is
`check("focusPlayerArgv", Model.focusPlayerArgv(), ["hyprctl", "dispatch", "focuswindow", "class:omarchy-iptv"])`
- the expectation is a transcription of the constant. Measured in a scratch copy
of the tree (no repo file touched):

```
repo as shipped, broken command:   1180 checks, 0 failure(s)   All Model.js tests passed.
command replaced with the spelling PROVEN to work on this host:
  FAIL focusPlayerArgv
       got:  ["hyprctl","dispatch","hl.dsp.focus({ window = \"class:omarchy-iptv\" })"]
       want: ["hyprctl","dispatch","focuswindow","class:omarchy-iptv"]
                                   1180 checks, 1 failure(s)
```

The suite is **green on the broken code and red on the fix**. Its polarity is
inverted: it pins the defect in place and would reject the repair. This is the
`CLAUDE.md` 12 trap found in released software, and it is worth more than the
feature that uncovered it.

> **D-PIP-1, P2.** `Model.focusPlayerArgv()` emits a legacy Hyprland dispatcher
> that cannot parse under a Lua config provider. Focus-the-player has never
> worked on this machine since v0.3.0 and fails silently through
> `execDetached`. Fix: emit `hl.dsp.focus({ window = "class:omarchy-iptv" })`
> through the same validated builder PiP uses. **Replace** the mirrored
> assertion at `tests/Model.test.js:455` with one that asserts the Lua
> *shape* - there is no `hl.dsp.window.focus`, so the test must also pin the
> namespace. Per PIP8, lane V1, this wave.

### G-3 - DISPROVEN. `action` is ignored; `float` and `pin` toggle unconditionally

The gate row says "either result is acceptable; we need to know which", and
notes that a pass would let `Model.pipPlan` emit fewer steps. It is a fail, and
the gate's own command would have reported a false pass: it only applies
`action = "set"` **once, from tiled**, where a toggle and a set are
indistinguishable. Applying it twice separates them:

```
baseline                                    float False
float action="set"                 rc=0 ok  float True    <- looks correct
float action="set"   (again)       rc=0 ok  float False   <- a set is not idempotent: it toggled
float action="unset" (from tiled)  rc=0 ok  float True    <- an unset from tiled FLOATED the window
float action="toggle"              rc=0 ok  float False
```

`pin` behaves identically: no `action` key toggles, `action = "set"` toggles,
and a second `action = "set"` toggles back off. An unrecognised value is
accepted in silence - `float({ ..., action = "zzz" })` returns rc 0 `ok`.

Consequences:

- **The design survives intact.** 4.3 already emits `action = "toggle"` behind a
  read of `live.floating` / `live.pinned`, and 4.5's "never a remembered
  boolean" is exactly the discipline that makes this harmless. Verified end to
  end below.
- **The optimisation in the G-3 failure branch is withdrawn.** `pipPlan` cannot
  emit unconditional set/unset steps. Every float and pin step stays
  conditional on a fresh read. A lane that "simplifies" this reintroduces the
  bug.
- Two further live facts for `pipPlan`'s fixtures: **unfloating a pinned window
  clears the pin by itself** (float toggle from floating+pinned landed at
  `float False pin False`), and **pin refuses a tiled window** -
  `warning: =[C]:-1: Window does not qualify to be pinned`, **rc 0**. 4.3's
  "unpin before unfloat" ordering is right and must not be reordered.

### Does the state apply to a window the plugin did not spawn? Yes - all six steps

This is the assumption the feature rests on. The target was started by the
helper and reparented to systemd (ppid 831), so it is not a child of the shell;
the dispatches were issued from an unrelated shell, so not a child of the
dispatcher either. Design 4.3 "enter", in order, with a read after each step:

```
baseline                                       iptv: at [690, 38]  size [650, 718] float False pin False
1 float  (toggle)                    rc=0 ok   iptv: at [404, 127] size [960, 540] float True  pin False
2 resize {x=410, y=230}              rc=0 ok   iptv: at [679, 282] size [410, 230] float True  pin False
3 move   {x=940, y=42}               rc=0 ok   iptv: at [940, 42]  size [410, 230] float True  pin False
4 pin                                rc=0 ok   iptv: at [940, 42]  size [410, 230] float True  pin True
5 alter_zorder {mode="top"}          rc=0 ok   iptv: at [940, 42]  size [410, 230] float True  pin True
6 tag {tag="+iptv-pip"}              rc=0 ok   tags ['default-opacity*', 'iptv-pip']
```

`at` and `size` land **exactly** on the requested integers. `resize {x,y}` is
absolute pixels, `move {x,y}` is absolute global layout coordinates - 4.4's
choice of global over per-monitor coordinates is correct. The user's other
window reflowed to full width `[12, 38] 1342x718` the moment the player left
the layout, which is the promise in section 1.

The pin promise was exercised directly. Switching the active workspace to 2,
then 3, then back to 1, the client's `workspace.id` followed each time with
`at [940, 42] size [410, 230] pin True` unchanged. It really does follow you.

Screenshot evidence at `/tmp/claude-1000/omarchy-iptv-qa12/12-pip-onscreen.png`:
the box renders video in the top-right corner, clear of the 26 px bar.

Design 4.3 "exit", from `{floating:false, pinned:false}`:

```
1 tag {tag="-iptv-pip"}     rc=0 ok   tags ['default-opacity*']
2 pin  (unpin)              rc=0 ok   float True  pin False
3' float (toggle)           rc=0 ok   iptv: at [690, 38] size [650, 718] float False pin False
```

Compared field by field against the pre-PiP capture, **both windows are
identical**: `SAME com.anthropic.Claude`, `SAME omarchy-iptv`.

### A new defect the gate was not looking for - D-PIP-2

Section 4.10 says "a dispatch step exits non-zero after the fallback -> stop the
queue ... report `dispatch_failed`". **Exit code cannot carry that signal.**
Against an address that does not exist:

```
$ hyprctl dispatch 'hl.dsp.window.tag({ window = "address:0xdeadbeef", tag = "+zz" })'    rc=0  ok
$ hyprctl dispatch 'hl.dsp.window.move({ window = "address:0xdeadbeef", x = 10, y = 10 })' rc=0  ok
$ hyprctl dispatch 'hl.dsp.window.float({ window = "address:0xdeadbeef", action = "toggle" })' rc=0  ok
$ hyprctl dispatch 'hl.dsp.window.pin({ window = "address:0xdeadbeef" })'                 rc=0  ok
```

All four did nothing and all four reported success. A refusal that *is* reported
arrives as `warning:` text on **stdout with rc 0** (`Window does not qualify to
be pinned`, `hl.focus: window not found`). rc is non-zero only for a Lua parse
or nil-call error - that is, only for a bug in our own string, never for a
failed effect. A stale address is the routine case here: the window dies
whenever playback stops.

> **D-PIP-2, P2 (design defect, pre-implementation).** `Service.qml` must not
> decide `dispatch_failed` from `Process` exit status. Detect failure by
> (a) scanning the step's stdout for `warning:` / `error:` and (b) re-reading
> `hyprctl -j clients` after the queue and comparing against the intent.
> Section 4.10 needs rewriting before lane V2 codes against it.

### G-4 - PROVEN, and the mpv-side job turns out not to be load-bearing here

In PiP at `at [940, 42] size [410, 230]`, with `auto-window-resize` left at its
default:

```
$ get_property auto-window-resize   ->  True     (never set to false in this run)
before zap: video 1280x720   win at [940, 42] size [410, 230]
zap to the 1080p entry, polled once a second for 10 s:
  t+1s ... t+10s   win at [940, 42] size [410, 230]   (every sample)
after zap:  video 1920x1080  win at [940, 42] size [410, 230]
```

The gate's assertion holds - `at` and `size` unchanged across a real
1280x720 -> 1920x1080 change. But it held **with `auto-window-resize` still
`true`**, which is not what 4.6 predicts. On Wayland a client can only *request*
a size, and Hyprland ignores the request for a floating window whose geometry a
dispatcher set explicitly. `auto-window-resize` is inert here for the same
reason `ontop` is inert: the same class of player-side control the design
already proved powerless in 2.1.

This does not break anything - it removes a justification. 4.6 presents the mpv
write as "the one job the compositor cannot do for us"; on this host the
compositor does it anyway. Keeping the write is defensible as portability
insurance for other compositors, but the design should stop claiming it is
required, and the product owner should decide whether
`Model.pipRestoreAutoResize(mpvArgs)` - a pure function, its own test matrix and
a restore path - is worth carrying for an effect never observed. **A new open
question for M2-05-01.**

### G-6 - PROVEN. The snapshot can live in the player

Headless mpv (`--no-config --idle=yes --vo=null --ao=null --force-window=no`),
no window opened, killed by pid afterwards:

```
set  user-data/omarchy-iptv-pip {...}                      error: success
get  (same client)    {'active': True, 'at': [1, 2], 'size': [410, 230], 'floating': False,
                       'pinned': False, 'monitor': 0, 'workspace': 1, 'v': 1}
loadfile <local wav> replace                               error: success  {'playlist_entry_id': 1}
get  (a NEW client connected AFTER the load)
                      {'active': True, 'at': [1, 2], 'size': [410, 230], 'floating': False,
                       'pinned': False, 'monitor': 0, 'workspace': 1, 'v': 1}
get  user-data        {'osc': {...}, 'omarchy-iptv-pip': {...}}     <- our key sits beside mpv's own
```

Byte-identical after the load, from a client that connected afterwards. 4.5's
storage choice stands: no new file, no `state.json` schema change.

Three reply-shape facts confirmed in the same run, all supporting 2.5's
corrections: `auto-window-resize` defaults to `True`; `osd-width` returns
`success` with **0** when there is no VO (a readback check written against the
original description fails open); `ontop` accepts `True` and reads back `True`
on a platform where it does nothing; an unknown property returns
`property not found`. **Never verify window state from an mpv reply.**

### G-11 - PROVEN. The player is being rendered translucent

```
tags on the player window: ['default-opacity*']
/usr/share/omarchy/default/hypr/windows.lua:6   o.window(".*", { tag = "+default-opacity" })
/usr/share/omarchy/default/hypr/windows.lua:25  o.window({ tag = "default-opacity" }, { opacity = "0.985 0.96" })
/usr/share/omarchy/default/hypr/apps/system.lua:40-51
    o.window("^(zoom|vlc|mpv|org.kde.kdenlive|com.obsproject.Studio|...)$", { tag = "-default-opacity" })
    o.window("^(zoom|vlc|mpv|...)$", { opacity = "1 1" })
$ hyprctl getprop address:0x559c6893d940 opaque   ->  false
```

The anchored media-opacity exemption matches on **class**, and our class is
`omarchy-iptv`, not `mpv` - the app-id that gives the plugin its window identity
is the same one that costs it the exemption. Confirmed, not inferred. Per PIP5
this is its own small defect, not PiP's to carry:

> **D-PIP-3, P3.** The player window is rendered at `0.985 / 0.96` because
> `--wayland-app-id=omarchy-iptv` misses Omarchy's `^(...|mpv|...)$` media-opacity
> exemption. `contrib/windows.lua` already ships the `-default-opacity` line;
> the README should point at it. Fix on its own terms (PIP5).

Also confirmed here: a rule-applied tag reads back as `default-opacity*` with a
trailing asterisk, a dispatched one (`iptv-pip`, `b1`, `b2`) does not.
`Model.pipFindWindow` rule 5 is correct and necessary.

### G-12 - PROVEN. A theme switch cannot un-PiP the user

```
theme Retropc, in PiP:  at [940, 42] size [410, 230] float True pin True tags ['default-opacity*', 'iptv-pip']
$ omarchy theme set Nord      rc=0      at [940, 42] size [410, 230] float True pin True tags [... 'iptv-pip']
$ omarchy theme set Retropc   rc=0      at [940, 42] size [410, 230] float True pin True tags [... 'iptv-pip']
```

Geometry, both booleans **and the dispatched tag** survived in both directions.
2.5's correction is confirmed live: dispatched window state is not Lua state, so
`reinitLuaState()` cannot touch it.

### G-5 - UNSETTLED, and this lane cannot settle it

The row requires the contrib float rule "pasted into `~/.config/hypr` **by the
user on a scratch config**". `CLAUDE.md` "Never touch" makes that directory
read-only for this lane and the brief did not authorise a change there. The only
runtime alternative is `hyprctl eval` + `hl.window_rule(...)`, which the design
itself rejects in 2.2 and which would register a rule in the user's live
compositor session that could match windows this lane does not own.

Not papered over, and not cost-free: G-5 is the one input to **PIP-03** and to
the README caveat in section 7. It bites only users who paste the optional
float line, so it does not block the lanes. **It must be settled by the user, or
by an explicitly authorised pass, before section 7's contrib text claims the
float rule is compatible with PiP.** One partial observation, worth exactly what
it is worth: ~30 s of playing video plus two zaps produced no positional drift
at all, but no static float/size rule matched our window during this pass, so
this says nothing about the rule re-applying on a commit.

### Arithmetic correction for lane V1 - section 4.4's worked example is wrong

4.4's formula, applied to this monitor (`1366x768`, scale 1, transform 0,
reserved `[0,26,0,0]`, x 0 y 0) with the defaults (top-right, 30 %, 16 px):

```
x0,y0,x1,y1 = 16 42 1350 752
w,h         = 410 230
top-right   = (940, 42)
```

The document states **"410x230 box at `(932, 42)`"** in 4.4 and again in open
question 4 / PIP4. `1350 - 410 = 940`, not 932. The formula is right and the
worked number is wrong by 8 px. This matters because 10.1 makes that example the
`pipGeometry` fixture. `(940, 42)` was applied live and is the value that clears
both the right edge at a 16 px margin and the 26 px bar. **Correct the prose to
(940, 42) before the fixture is written.**

### Privacy and safety sweep

| Check | Result |
|---|---|
| `status \| grep -c '://'` | 0, before and after |
| `journalctl --user -t omarchy-shell \| grep omarchy-iptv \| grep -c '://'` | 0 |
| Hostile address, `0xdead"); os.execute("touch ...PWNED"); --` | rc 7, Lua parse error, **no file created**; would also be refused by 4.11's regex before construction |
| Hostile address, `0x1 end os.time()` | rc 0 `ok`, no effect, no execution |
| Stray marker file | absent |

4.11 and PIP7 hold. Note that the second hostile value was *silently accepted*,
which is one more reason the regex, not the compositor's reply, is the only
defence - enforce it at construction and at the call, as PIP7 requires.

### Machine restored

| Item | Proof |
|---|---|
| `~/.config/omarchy/shell.json` | sha256 identical to the opening snapshot |
| `~/.local/state/omarchy-iptv/` | every file sha256 identical; tree and modes identical (`700` dir, `600` state.json) |
| `~/.cache/omarchy-iptv/` | every file sha256 identical; tree and modes identical |
| Installed plugin | `5d1a27e`, `* main 5d1a27e [origin/main]`, `git status --porcelain` empty. Never modified |
| Repo | `git status --short` empty, branch `main` |
| Shell | restarted (`omarchy restart shell`), quickshell pid 1800527 -> 1943634, plugin answers `status` with `"status":"ready"`, 1474 channels, 28 groups, 7 recents, 0 favorites - matching the opening capture |
| Player | `pgrep -x mpv` empty; `omarchy-iptv` client count 0 |
| Theme | `omarchy theme current` -> `Retropc` |
| Windows | opening capture 1 client, closing capture 1 client, compared on class/at/size/floating/pinned/workspace/monitor/tags: **SAME** |
| Workspaces | one, `ws 1 windows 1`, as at the start |
| Probe tags | `grep -cE 'iptv-pip\|iptv-probe\|"b1"\|"b2"'` over all clients -> 0 |

One honest note on the restore. The shell restart triggered the plugin's own
overdue playlist refresh (`refreshMinutes` 360, last fetch 13:24, restart
~21:05), which rewrote the cache to 1472 channels - upstream iptv-org had
dropped 4 entries and added 2. That refresh was due and would have happened
without this pass. The user's original bytes were put back afterwards and
verified, so disk is exactly as found; the running shell holds the fresher list
in memory and will rewrite it on its next scheduled refresh. Favorites, recents
and `lastPlayed` were never altered by anything but the two channels this pass
played, and those were restored.

Evidence root: `/tmp/claude-1000/omarchy-iptv-qa12/` (opening and closing
clients/monitors/layers/status JSON, the snapshot tree and its sha256 manifest,
the in-PiP capture, the screenshot).

### Verdict for the lanes

**The build lanes can start**, with four written corrections carried into the
design first:

1. **G-3 is a fail.** Delete the "a pass lets `Model.pipPlan` emit fewer steps"
   branch. Every float/pin step stays conditional on a fresh read. Add the two
   live facts: unfloat clears pin, and pin refuses a tiled window with rc 0.
2. **Section 4.10 is unimplementable as written** (D-PIP-2). Rewrite failure
   detection to scan stdout and re-read `clients`. Lane V2 blocks on this.
3. **Section 4.4's worked example is off by 8 px** - `(940, 42)`, not
   `(932, 42)`. Fix before the `pipGeometry` fixture is written.
4. **The focus fix is `hl.dsp.focus({ window = ... })`**, not
   `hl.dsp.window.focus` - that namespace member does not exist.

Two items go to the product owner as M2-05-01 additions: whether
`auto-window-resize` and `pipRestoreAutoResize` are worth carrying now that the
effect they defend against is unobservable here (G-4), and who runs G-5, which
this lane may not.

Two defects are filed against released software: **D-PIP-1 (P2)**, the dead
focus command and its inverted test, which PIP8 already assigns to lane V1 this
wave; and **D-PIP-3 (P3)**, the translucent player, which PIP5 keeps separate.

## M2-05 picture-in-picture LIVE pass on 5e3a374 (QA, 2026-09-14, 22:30 - 23:00)

Task M2-05-06. The whole PIP- matrix of
`docs/M2-05-PICTURE-IN-PICTURE.md` 10.4 was run against a player **started
through the plugin**, plus the four questions the brief added: restore from
both starting states, the three warned-about cases, what the user actually
sees on a failure, and the released-software defect this wave repaired. This
lane wrote only this file. Every dispatch in this pass named either the
plugin's own player window or a window this lane started itself; the user's
window was never sent a state-changing instruction until the closing focus
restore, which put focus back where it began.

**Bottom line.** The feature works, and it works for the reason the design
says it does: read-then-act. The three restore paths - from tiled, from
user-floated, from user-popped float+pin - all put the window back byte for
byte, which is the case the gate's G-3 failure predicted would break a blind
implementation. The channel change, the theme switch, the user-dragged box,
the foreign same-class window and the stop-while-in-PiP cases all pass. Three
new defects, none of them in the dispatch path: one P2 reporting defect after
a shell restart, one P3 left behind by the focus repair, and one P3 coverage
gap in the harness the work plan counts as lane V2's acceptance. Two
documented limitations came out different from expected, both in the honest
direction.

### Environment

| Fact | Value |
|---|---|
| Repo under test | `5e3a374`, branch `main`, tree clean |
| Installed copy during the pass | detached at `5e3a374`, fetched from the local repo; `omarchy plugin validate .` rc 0 |
| Installed copy before and after | `5d1a27e` (v0.3.1), `* main 5d1a27e [origin/main]`, porcelain empty |
| Hyprland | 0.56.2, `configProvider: lua` (line 68 of `hyprctl systeminfo`), signature `efb50993..._1789339912_1242840277` |
| Monitor | `eDP-1`, 1366x768, scale 1, transform 0, reserved `[0, 26, 0, 0]`, x 0 y 0, id 0 |
| mpv | v0.41.0 |
| Shell | quickshell 1943634 -> 2043920 -> 2047679 -> 2065245 -> 2066537 -> 2071249 (five restarts: one to install the code under test, one as PIP-05, three during the restore) |
| Source | iptv-org.github.io, 1474 channels on disk, 28 groups, theme Retropc |
| Channels used | `t:CookingPanda.us@SD` (decodes 1024x576), `t:ReutersTV.us@SD` (decodes 1920x1080) |
| Player window | class `omarchy-iptv`, pid 2045335, address `0x559c6713d0b0` (later 2055289) |
| Evidence root | `/tmp/claude-1000/omarchy-iptv-qa13/` - opening/closing clients, monitors, workspaces, layers, status, the snapshot tree and its sha256 manifests, twelve screenshots, two harness logs |

### 1. The feature does what section 1 promises

| Case | Verdict | Evidence |
|---|---|---|
| PIP-01 `pip on` from a tiled player | **PASS** | `at [940, 42] size [410, 230] float True pin True tags ['default-opacity*', 'iptv-pip']` - exactly `Model.pipGeometry`'s computed `(940, 42) 410x230`, the value the gate corrected from the document's `(932, 42)`. The user's other window reflowed to full width `[12, 38] 1342x718`, identical to the opening capture: the box really is out of the layout |
| It follows you across workspaces | **PASS** | Active workspace driven 1 -> 2 -> 3 -> 1 with `hl.dsp.focus({ workspace = ... })`; the client's `workspace.id` followed each time with `at [940, 42] size [410, 230] pin True` unchanged. `shot-02-pip-on-ws2.png` shows the box rendering video on an otherwise empty workspace 2 |
| PIP-02 `pip off` from a tiled origin | **PASS** | Both windows compared field by field against the pre-PiP capture: `SAME com.anthropic.Claude`, `SAME omarchy-iptv` (`[690, 38] 650x718 float False pin False`), tag gone |
| PIP-10 guide over the PiP box | **PASS** | The guide is a level-3 layer (`eDP-1 level 3 omarchy-iptv 0 0 1366 768`) and draws above the box (`shot-05-after-p.png`); `Esc` closed it and the box was untouched, `pip.on` still true |
| PIP-14 one window throughout | **PASS** | The plugin's own `omarchy-iptv` client count was 1 at every step of every case; the only time it read 2 was PIP-11, where the second was the foreign window this lane started |

**The key itself, pressed for real.** `wtype p` into the guide's list mode
(`pgrep -x hyprlock` checked clear before every keystroke, guide layer
confirmed present each time). First press: footer reads
**`Picture in picture on`**, window shrinks to the corner. Second press:
footer reads **`Picture in picture off`**, window returns to the layout.
The list-mode hint line carries `p pip` in the shipped rhythm
(`... f favorite · s stop · p pip · r refresh · / search · o sources`,
`shot-04-list-mode.png`). Note the hint line is elided on the left on this
1366 px display - `j/k move` is cut off - which is pre-existing narrow-display
behaviour, not PiP's.

### 2. Restore from BOTH starting states, and a third

This is the case ruling PIP10 exists for: the compositor ignores the `action`
argument, so an implementation that issued a blind unset would float a tiled
window instead of restoring it. Three starting states were set up by
dispatching against the player's own address only, then entered and exited
through the product:

| Started as | Snapshot the plugin wrote into the player | After `pip off` |
|---|---|---|
| Tiled `[690, 38] 650x718` | `{"active":true,"at":[690,38],"size":[650,718],"floating":false,"pinned":false,"monitor":0,"workspace":1,"v":1}` | `[690, 38] 650x718 float False pin False` - **SAME**, and the other window retiled with it |
| Floating, user-placed `[120, 300] 700x400`, unpinned | `floating:true, pinned:false` | `[120, 300] 700x400 float True pin False` - **SAME**. It did **not** unfloat into the layout |
| User-popped float+pin `[713, 227] 600x340` | `floating:true, pinned:true` | `[713, 227] 600x340 float True pin True` - **SAME**, tag removed, **pin kept** because the snapshot said it was already pinned |

All three restored the tag to `['default-opacity*']` alone. The snapshot is
read out of `user-data/omarchy-iptv-pip` in the player, confirmed live over
the socket at each step, and `pip off` leaves it `{"active": false, "v": 1}`.

### 3. The three cases the gate and integration warned about

**PIP-04, change channel while in PiP - PASS.** In PiP at `[940, 42]
410x230`, zapped from a 1024x576 stream to a 1920x1080 one and sampled once a
second for twelve seconds: `at [940, 42] size [410, 230]` on **every** sample,
tags intact. `video-params/w,h` confirmed `1024x576 -> 1920x1080` and
`media-title` confirmed `Reuters (1080p)`. Ruling PIP14's property is really
written: `auto-window-resize` read back `False` while in PiP and `True` again
after `pip off`, with no `mpvArgs` set. The snapshot survived the
`loadfile ... replace` byte-identical - G-6 proven on the live player, not
only headless.

**PIP-05, restart the shell while in PiP - PART PASS, one new P2.** The
window half is perfect: `omarchy restart shell` with the box in the corner
left both windows **SAME** on class, at, size, floating, pinned, tags, pid and
address, and the snapshot inside the player survived
(`{"active":true,"at":[690,38],...}`) along with `auto-window-resize:false`.
The next `p` correctly **exited** and restored `[690, 38] 650x718` tiled. But
the plugin never re-derives the state: `status.pip.on` read `false` on all
**30** one-second samples after the restart while the window was demonstrably
in PiP, and the accepted request's reply said `"was":false`. Design 4.7 step 3
("read `hyprctl -j clients` and look for `floating && pinned && tag`") is not
implemented, and PIP-05's own acceptance - "within 2 s the guide reports PiP
on" - is unmet. Filed as D-PIP-4 below.

**PIP-06, move or resize the box yourself - PASS, and it does not fight you.**
Two sub-cases, both sensible:

```
in PiP at [940, 42] 410x230
user drags/resizes to [180, 420] 520x300
`pip on` again      -> [940, 42] 410x230, and the snapshot is UNCHANGED
                       ({"at":[690,38],"size":[650,718]}) - a second `on`
                       re-snaps the box and does not overwrite the restore point
user drags again to [-35, 425] 600x340 (deliberately off the left edge)
`p` (toggle)        -> EXIT to [690, 38] 650x718 tiled, the true original,
                       not the stale box and not the dragged rectangle
```

**PIP-07 in both orders - PASS.** Enter PiP, then the user unfloats and
unpins it themselves, then `pip off`: ends `[690, 38] 650x718 float False pin
False`, tag removed, no inverted state. And the reverse - a window the user
popped with float+pin and that carries no `iptv-pip` tag - is read as
**enter**, not exit, exactly as 4.8 says.

**PIP-09 theme switch while in PiP - PASS.** `omarchy theme set Nord` then
back to `Retropc`: `at [940, 42] size [410, 230] float True pin True tags
[..., 'iptv-pip']` identical through both switches. G-12 holds against the
product, not only against hand-dispatched state.

**PIP-11 foreign same-app-id window - PASS.** A second
`mpv --wayland-app-id=omarchy-iptv` (started by this lane, pid 2053730) made
the `omarchy-iptv` client count 2, the PLY-RST-11 shape. A full `pip off` /
`pip on` cycle left it **byte-identical** on at, size, floating, pinned and
tags, as it did the user's own window. Pid narrowing works.

**PIP-08 stop while in PiP - PASS.** `stop` -> the plugin's player window
count 1 -> 0 within 0.5 s, `playing/up/pipOn` all false, no floating leftover.

**Multi-monitor - NOT ESTABLISHED.** One output, `eDP-1`. `card1-DP-1`,
`card1-HDMI-A-1` and `card1-HDMI-A-2` exist but nothing is attached and this
lane has no second display to attach honestly. Documented limitation 3 stands
unchanged.

**G-5 (a pasted static float rule) - STILL UNSETTLED.** Unchanged from the
gate: settling it needs a write under `~/.config/hypr`, which `CLAUDE.md`
"Never touch" forbids this lane and which the brief did not authorise. Ruling
PIP17 already covers it.

### 4. What the user sees when it cannot do what was asked

The compositor still reports success for instructions aimed at windows that
do not exist. Re-confirmed read-only against the address of a player killed a
moment earlier:

```
hl.dsp.window.tag({ window = "address:0x559c6713d0b0", tag = "+zz-qa13" })   rc=0  ok
hl.dsp.window.move({ window = "address:0x559c6713d0b0", x = 10, y = 10 })    rc=0  ok
hl.dsp.window.float({ window = "address:0x559c6713d0b0", action="toggle" })  rc=0  ok
stray zz-qa13 tag anywhere afterwards: 0
```

D-PIP-2's premise holds and the implementation is right to verify by readback.
What the user actually meets:

| Situation | What the user sees | Recovers? |
|---|---|---|
| Player dies mid-PiP, `p` pressed at once | Desktop toast `Stream failed - "Reuters (1080p)" did not play - Playback stopped unexpectedly`; the row marks `Failed 22:47 - Space to retry`; no PiP footer line (`shot-10-failure.png`) | Yes |
| `p` with nothing playing | Footer `Nothing playing` (`shot-11-nothing-playing.png`); IPC `{"ok":false,...,"code":"nothing_playing","error":{"code":"nothing_playing"}}` | Yes - the next press is clean, nothing compounds |
| `pip zzz` | IPC `{"ok":false,...,"code":"bad_mode"}`; no footer line, deliberately - `bad_mode` has no entry in `Model.pipStatusText` | Yes |
| `pip on` in the gap between play and the window mapping | `nothing_playing` - the pid gate answers before the window question is asked | Yes |

`no_window` and `dispatch_failed` were **not reachable from outside**. Both a
timed race at play and a bounded burst of twenty `pip toggle` calls fired
immediately after `kill -9` on the player were answered `nothing_playing` on
the **first** attempt: the plugin's own liveness gate closes those codes off
faster than a user could press a key. Recorded as unsettled by observation
rather than claimed - forcing a refused dispatch would need a source change,
which this lane may not make. `status.pip.reason` was `""` in every state
observed, including after the kill.

### 5. D-PIP-1, the released defect, confirmed fixed on a real window

`Model.focusPlayerArgv()` in the installed copy under test emits
`["hyprctl","dispatch","hl.dsp.focus({ window = \"class:omarchy-iptv\" })"]`.
A/B with focus parked on a window this lane started, the player window
present:

```
focus BEFORE: qa13-probe 0x559c68918460

$ hyprctl dispatch focuswindow class:omarchy-iptv          # as shipped in v0.3.0/v0.3.1
rc=7  error: [string "return hl.dispatch(focuswindow class:omarchy-..."]:1: ')' expected near 'class'
focus AFTER : qa13-probe 0x559c68918460                    <- still a no-op

$ hyprctl dispatch 'hl.dsp.focus({ window = "class:omarchy-iptv" })'   # what the fix emits
rc=0  ok
focus AFTER : omarchy-iptv 0x559c6713d0b0                  <- focus moved
```

And through the product, not only the command: with focus on this lane's own
window, the guide was opened and `Enter` pressed on the playing row - the
`play(key, keepOpen=false)` path at `Service.qml:525` - the guide closed and
`hyprctl -j activewindow` reported `omarchy-iptv 0x559c6713d0b0`. **The focus
command moves focus again.** The PiP box was untouched by it.

### 6. The two documented limitations

**Limitation 2, "another floating window you focus afterwards can cover it" -
could NOT be reproduced, in the honest direction.** Three attempts against a
floating window this lane started and placed over the box at `[860, 20]
500x320`:

| Attempt | Result |
|---|---|
| `hl.dsp.focus` onto the covering floating window | PiP box still drawn on top (`shot-07-covered.png`) |
| `hl.dsp.window.alter_zorder({ mode = "top" })` on the covering window | PiP box still on top (`shot-08-raised.png`) |
| Fullscreen the covering window (`fullscreen: 2`, with `binds:allow_pin_fullscreen` `{"bool":false,"set":false}`) | PiP box still on top, over a full-screen window that had hidden the bar (`shot-09-fullscreen.png`) |

On this compositor a **pinned** floating window sits above the rest of the
floating stack and above a fullscreen window. The README's limitation is
therefore more pessimistic than what this machine does, which is the safe
direction to be wrong in - it promises less than it delivers. It should not be
rewritten to promise always-on-top (PIP9 forbids that, and Hyprland still has
no such state), but it is worth recording that no covering could be provoked
here. This also answers PIP-12, which the design left as observation only.

**Limitation 1, "reports itself unavailable rather than half working" -
PARTLY SETTLED, the compositor half honestly unsettled.** The positive arm is
proven live: `hyprctl systeminfo` line 68 reads `configProvider: lua`, the
service's one probe answers `available: true`, and everything above worked.
The negative arm cannot be settled against a real compositor without
reconfiguring the user's - which the brief forbids - so it was settled as far
as it can be, at the service level, by running the existing harness scenario
with its documented provider override
(`OMARCHY_IPTV_PIP_PROVIDER=hyprlang scripts/dev-harness/pip-scenario.sh live`,
a stub `hyprctl` on PATH and its own `XDG_RUNTIME_DIR`, so it cannot reach the
real compositor):

```
FAIL the service never decided PiP was available    <- available stayed false, as intended
PASS P2: the answer is a refusal
FAIL P2: named nothing_playing                      <- it refused for the EARLIER reason, no_compositor
PASS P2: and it issued no dispatch at all
```

So on a provider whose dispatch language the plugin does not speak, the
feature is taken off the offer, the verb refuses, and **no dispatch is issued
at all** - it does not half-work. That a real hyprlang Hyprland behaves the
same way remains untested and stays a documented limitation.

### 7. Usability, on this 1366x768 display

| Question | Finding |
|---|---|
| The defaults | 30 % of width, top-right, 16 px margin -> `410x230` at `(940, 42)`. That is 9 % of the screen area. `shot-01-pip-on.png`: the video is comfortably legible, on-screen station text ("FOLLOW THE SHOW @localbrewtv") is readable, and the box clears the 26 px bar with 16 px to spare. **Recommend keeping PIP4's proportional defaults unchanged.** Omarchy's own 600x338 would be 44 % of this screen in both axes and would sit on top of half the working area |
| The corner | Top-right is the right default here: the bar's right cluster is clock and tray, not content, and the tiling layout's newest window enters from the right, so the box lands where the eye already is. No change recommended |
| Is the transition jarring? | No. Sampled every ~120 ms through an enter, the compositor reports exactly **two** states: the tiled baseline at t+0.06 s and the final `[940, 42] 410x230 float True pin True` tagged box at t+0.19 s. No intermediate "floating at the default 960x540, centred" state is observable in the product - the gate saw one only because it stepped the six dispatches by hand with a read between each. Whole-request wall clock including the IPC round trip: **0.81 s** |
| Does the footer tell you what happened? | Yes, and in the user's words: `Picture in picture on` / `Picture in picture off` / `Nothing playing`, each for 3 s (`Guide.transientMs`). No toast, per UX 6.4 - correct, the effect is on screen already |
| Anything missing | After a shell restart the bar tooltip does not say `Picture in picture: on` even when it is - see D-PIP-4. And for roughly the first second after a shell restart `pip.available` reads `false` while the two availability probes are still in flight, so a `p` pressed immediately would answer `Picture in picture needs Hyprland` rather than "not ready yet". Both were observed; the second is cosmetic |

### 8. Privacy and hygiene

| Check | Result |
|---|---|
| `status \| grep -c '://'` | **0** |
| `pip toggle` reply `\| grep -c '://'` | **0** |
| `journalctl --user -t omarchy-shell --since -60min \| grep iptv \| grep '://'`, excluding QML `file:///` paths | **0** |
| Any `hl.dsp` string in the journal | **0** - no dispatch string is logged at all |
| Console hygiene | 58 repeats of `WARN scene: QML MouseArea at .../Guide.qml[2437:19]: Cannot anchor to an item that isn't a parent or sibling.` This is **not** PiP's: `git log -L 2420,2445:Guide.qml` puts that MouseArea in `22996f4` (M2-03 numeric zap). Pre-existing noise, recorded here because this pass is the first to count it |

### 9. New defects

> **D-PIP-4, P2.** After a shell restart while in picture in picture, the
> plugin never re-derives the state from the compositor. `status.pip.on` read
> `false` on all 30 one-second samples while the window was demonstrably
> floating, pinned and carrying `iptv-pip`; the bar tooltip's
> `Picture in picture: on` line therefore never appears; and the next
> accepted request replies `"was":false`. Design 4.7 step 3 specifies the
> read and PIP-05 makes "within 2 s the guide reports PiP on" an acceptance
> criterion - neither holds. **Behaviour is not affected**: the request path
> takes a fresh read before planning, so `p` still exits correctly and
> restores the true rectangle. This is a reporting defect: what the plugin
> *says* about its own state is wrong until the user acts. Fix: run the same
> `pipReadClients` + `Model.pipActive` pair once on `onPlayerAttached`, which
> is where 4.7 already puts the snapshot read.

> **D-PIP-5, P3.** The D-PIP-1 repair fixed the spelling and left the
> selector. `Model.focusPlayerArgv()` still emits
> `hl.dsp.focus({ window = "class:omarchy-iptv" })` - class only - while PiP
> itself refuses to act on anything but a pid-narrowed address (4.2, and
> `docs/QA-PLAYER.md:124` records the reproduced two-client case). With a
> foreign `mpv --wayland-app-id=omarchy-iptv` present, the focus command
> focused the **stranger's** window 3 times out of 3. Focusing a stranger's
> window is a nuisance rather than damage, which is why this is P3 and not
> P2, but it is the same shape of bug the wave was opened to fix, in the same
> function. Fix: focus by the address `Model.pipFindWindow` already resolves,
> and refuse when the match is ambiguous.

> **D-PIP-6, P3 (coverage).** The live half of
> `scripts/dev-harness/pip-scenario.sh` does not pass on this machine: 63
> PASS, 11 FAIL, every failure cascading from `FAIL P3: the service learned
> the player pid from the player itself` - the harness's fake player never
> yields a non-zero pid, so the geometry, ordering, address, readback and
> key-path assertions (P4, P5, P6, P8) all assert about nothing.
> `scripts/check.sh:212` runs only `pip-scenario.sh check-tree`, the
> preflight, so this is invisible to the gates, and the file's own header
> already says the live half had never been run. The work plan makes
> "Harness scenario passes headless against a stub `hyprctl`" M2-05-04's
> acceptance criterion, so that criterion is currently unmet. Everything the
> eleven checks would have proven **was** proven for real in sections 1-3
> above, which is why this is P3 and not a release blocker.

### 10. Machine and desktop restored

| Item | Proof |
|---|---|
| `~/.config/omarchy/shell.json` | sha256 identical to the opening snapshot |
| `~/.local/state/omarchy-iptv/` | every file sha256 identical; tree and modes identical (`700` dir, `600` state.json); watched for 20 s afterwards and not rewritten |
| `~/.cache/omarchy-iptv/` | every file sha256 identical; tree and modes identical |
| Installed plugin | back on `5d1a27e`, `* main 5d1a27e [origin/main]`, porcelain empty, the temporary `refs/qa13/under-test` deleted (0 refs left), and **all 93 files sha256-identical** to the opening manifest |
| Repo | `git status --porcelain` empty, branch `main`, `5e3a374` |
| Shell | restarted; plugin answers `status` `"ready"`, 1474 channels, 28 groups, 7 recents, 0 favorites, `lastUpdated 13:24` - matching the opening capture field by field. `pip` verb answers `Function not found.`, which is itself proof the pre-PiP v0.3.1 copy is what is installed |
| Player | `pgrep -x mpv` empty; every window this lane started killed **by pid** |
| Theme | `omarchy theme current` -> `Retropc` |
| Windows | opening capture 1 client, closing capture 1 client, compared on class/at/size/floating/pinned/workspace/monitor/tags: **SAME** (`com.anthropic.Claude [12, 38] 1342x718 float False pin False ws 1`) |
| Focused workspace | opening ws 1 -> closing ws 1, **SAME**; workspace list `[(1, 1)] -> [(1, 1)]`, **SAME** |
| Focused window | `0x559c687e09a0` -> `0x559c687e09a0`, **SAME** |
| Probe tags | `grep -cE 'iptv-pip\|iptv-probe\|zz-qa13\|"b1"\|"b2"'` over all clients -> **0** |

Two honest notes on the restore, both worth writing down because the next
live lane will hit them.

*The refresh.* Three of this pass's five shell restarts triggered the
plugin's overdue playlist refresh (`refreshMinutes` 360, last fetch 13:24),
which each time rewrote the cache to 1472 channels - upstream had dropped two
entries - and bumped the source's `channelCount` and `fetchedAt` inside
`state.json`. That refresh was due and would have happened without this pass.
It was resolved by letting the last refresh finish, *then* writing the user's
bytes back, then watching for 25 s to confirm nothing rewrote them. Disk and
the running shell now both report the opening numbers: `ready`, 1474
channels, 28 groups, 7 recents, 0 favorites, `lastUpdated 13:24`.

*The swap.* Restoring the cache by `rm -rf` on the directory and copying the
tree back put the running plugin into `loading` with 0 channels and it stayed
there for 40 s of polling: the `FileView` was watching an inode that no
longer existed and never recovered. Restarting the shell fixed it, and the
final restore was done by overwriting the three files **in place**, which the
plugin picked up without complaint. A live lane that swaps a watched
directory under a running shell and then walks away leaves the user with an
empty guide. Overwrite the files; do not replace the directory.

### Verdict

**GO for release, with D-PIP-4 fixed first.**

The feature is sound where it is hardest to be sound. Every restore path was
exercised from a real starting state rather than assumed, and the one the
gate warned about - already floating - is the one that would have broken a
blind implementation and does not break this one. The channel change, the
theme switch, the dragged box, the foreign window and stop-while-in-PiP all
hold. The defect the wave repaired in released software now demonstrably
moves focus on a real window, through the real product path.

D-PIP-4 is small and it is not in the dispatch path, but it falsifies a
promise the design makes in writing (4.7) and an acceptance criterion the
matrix states (PIP-05), and the wrong answer is the one a script polling
`status` would act on. It is an hour of work in the place 4.7 already
specifies. D-PIP-5 and D-PIP-6 can follow the release; neither risks a
user's windows.

Zero P1. One P2 (D-PIP-4). Two P3 (D-PIP-5, D-PIP-6). D-PIP-3, the
translucent player, remains open on its own terms per PIP5 and was visible
throughout this pass without ever mattering to PiP.

## M2-09 the guide at real provider scale, live pass on 030ba9b (QA, 2026-09-15, 08:03 - 08:30)

The judgement pass for `docs/UX-GUIDE-AT-SCALE.md` section 9.2, run on the
user's machine against the subscriber's real 3,335-channel list and the
public 1,472/28 cache, with a direct A/B against the installed v0.5.0. This
lane wrote only this file. Every measured claim in section 5 was checked on
screen; where the code does exactly what the design says and the result is
still not better, that is said here rather than scored as a pass.

**Bottom line.** The five changes do what they claim, and four of them are an
improvement you can see without being told to look. The density win is real
and large, the fold peek fixes a defect that is obvious once seen side by
side, and the many-small-groups shape is not merely unregressed - it gets the
better of the two column fixes. Two things are worse than the design
predicts. The failure notice on the **selected** row measures 3.8:1 against
its own background, under the 4.5:1 the rest of the card clears. And the
guide-data caveat in section 12 is understated: on a one-group playlist whose
channels carry no `tvg-id`, configuring an EPG does not trade the density for
now/next - it trades it for **3,335 rows with an empty second line**. Zero
P1. One P2, two P3, all named below.

### Environment

| Fact | Value |
|---|---|
| Repo under test | `030ba9b`, branch `main`, tree clean |
| Installed copy during the pass | detached at `030ba9b` via `refs/qa14/under-test`, fetched from the local repo; `omarchy plugin validate` rc 0 |
| Installed copy before and after | `db47c37` (v0.5.0), `* main db47c37 [origin/main]`, porcelain empty |
| Hyprland / mpv / shell | 0.56.2 (`efb50993`), mpv running once through the plugin, quickshell 0.3.1, six shell restarts |
| Monitor | `eDP-1` 1366x768 scale 1, reserved `[0, 26, 0, 0]`, theme `Retropc`, `repeat_rate 40` / `repeat_delay 250` |
| Shape A | subscriber `USChannels.m3u`, **3,335 channels, 1 group** (`United States`), added as a **local file path**; the credentialed URL was never used, typed, or written |
| Shape C | live install's own cache, iptv-org.github.io, 1,472 channels / 28 groups |
| Shape A EPG | `tests/fixtures/qa-epg.xml` by absolute path; **1 of 3,335** playlist entries carries a `tvg-id` at all |
| Evidence root | `/tmp/claude-1000/omarchy-iptv-qa14/` - snapshot tree with sha256 manifests, opening/closing `hyprctl` captures, 40 screenshots and crops |

### 1. The measured claims, confirmed on screen (shape A)

Every figure below is read off a screenshot, not off a test.

| Claim (design 3.5 / 5.1) | On screen | Evidence |
|---|---|---|
| 12 visible rows rather than 9 | **12** single-line rows at the top of the list (`USA FOX NEWS` ... `USA USA NETWORK`), against **9** two-line rows on v0.5.0 with the same list | `12-subscriber-all.png` vs `50-v050-subscriber-all.png` |
| `pageSize()` 8 -> 11 | header stepped `1 of 3,335` -> `12 of 3,335` -> `23 of 3,335` on two `PgDn`. **11** | `14-sub-pgdn1.png`, `15-sub-pgdn2.png` |
| Group column keeps its pinned entries, loses the entry that lies | column is `Favorites 0 / All 3,335` + pinned `Sources`, **no `GROUPS` header, no `United States 3,335`**. v0.5.0 shows both. `Recent` reappears the moment a recent resolves | `12-subscriber-all.png` vs `50-v050-subscriber-all.png` |
| Header carries a position, not a bare total | `All - 1 of 3,335`, `All - 23 of 3,335`, `All - 3,335 of 3,335` at `End`; v0.5.0 reads `All - 3,335 channels` at every cursor row | `22-sub-end.png`, `50-v050-...png` |
| The cursor no longer parks flush | after `PgDn` the cursor row sits **one clipped row above the edge**, with a second clipped row at the top. On v0.5.0 the cursor row is itself clipped by the footer and nothing below it is visible | `15-sub-pgdn2.png` vs `52-v050-sub-pgdn2.png` |
| Footer verb | `h/l scope` on shape A, `h/l group` on shape C; `Left/Right scope` in search mode | `12-`, `02-`, `13-open-frame2.png` |
| No row-height pop, no column pop on open | the **first painted frame** of a fresh open already carries 12 single-line rows and no `GROUPS` section | `13-open-frame2.png` (caught mid fade-in) |
| Header label width | left edge at 1,048 px (1 digit), 1,042 (2), 1,036 (3), **1,024 (4)** - and v0.5.0's `All - 3,335 channels` also starts at **1,024**. The widest new form is exactly as wide as the form it replaces; total travel 24 px, as predicted | luminance scan of `12-`, `16-`, `17-`, `22-`, `50-` |
| `searchLine` reflow invisible | no visible movement of the placeholder or the query at any cursor position | all shape A shots |

Search at this scale is as good as the design says: `espn` returns **8
matches** in one screen (`in All - 8 matches`), `usa` overflows to
`in All - 1 of 200` with `First 200 of 982 - keep typing` in the footer.

### 2. Judgement: is it actually better

**Yes on the list, unambiguously, and the A/B is what makes it obvious.**
Nine rows of `United States` stacked under nine channel names is not a
neutral loss - on v0.5.0 the eye has to skip a line of identical grey text
between every pair of channels. At 38 px the names form a single column the
eye can run down. Twelve names against nine, with no line of noise between
them, is a bigger difference to use than +33% suggests.

**The peek is the change I would keep if I could only keep one.**
`52-v050-sub-pgdn2.png` is the whole argument: the v0.5.0 cursor row is
parked so hard against the bottom that its own second line is cut off by the
footer, and there is nothing at all to say 3,318 rows follow. The new
behaviour puts a clipped row under the cursor and one above the top. It is
the difference between a list that ends and a list that continues.

**Does the moving position number distract while holding a key?** Measured
honestly: with `repeat_rate 40` a held `j` moves 40 rows a second, and the
header ticked `103 -> 154` over a 1.5 s hold. At that speed the number is not
readable and cannot inform - but it did not pull my eye either. It is
caption-10 at opacity 0.52, in the far top-right corner, roughly 250 px from
the nearest row text, and the digits share an envelope; the only visible
motion is a 6 px shift of the whole label when the digit count changes, which
happens four times across 3,335 rows. **Not distracting.** What it is good
for is the moment you stop: you let go and the number tells you where you
landed. Keep it.

**Where it is not better.** Three things, none fatal:

1. The header's `in All - 1 of 200` sits diagonally opposite the footer's
   `First 200 of 982 - keep typing`. Both are true, both are on screen at
   once, and the smaller number is a **cap** while the larger is a **count**.
   I read the header first and briefly believed the query had 200 matches.
   The design chose this split deliberately (3.2 D5) and I would not reverse
   it, but it is the one place where two numbers on one card fight.
2. With two sources configured the footer counts line elides in list mode:
   `USChannels.m3u - 3,335 channels - updated 0...`. Pre-existing to this
   lane (the source label is M2-01's), but this lane's own headline claim -
   that the total lives in the footer now - is the thing being cut off.
3. Nothing in this lane helps the actual work of finding a channel **by
   browsing** 3,335 names. It gives you three more of them and tells you
   where you are. Search is still the only thing that makes this list
   tractable, exactly as GS7 says.

### 3. The shape that must not regress: many small groups

Public cache, 1,472 channels / 28 groups, compared frame to frame against
v0.5.0 on the same cache.

| Check | Result |
|---|---|
| Group column | identical: `Recent 6 / Favorites 0 / All 1,472`, `GROUPS`, the same ten visible groups with the same counts, the pinned `Sources` row, same 219 px | `01b-public-all.png` vs `54-v050-public-all.png` |
| `h`/`l` ring | walked 12 stops out and 12 back; every scope reached, silent wrap intact, `Comedy 39` selected and returned to `All` | `04-`, `05-` |
| Two-line rows where the second line varies | present and correct - `Movies`, `Religious`, `Animation`, `Music` down one screen. Inside a group rows are single-line, as they already were | `01b-`, `04-` |
| `pageSize()` | 8, unchanged (`1 -> 9 -> 17 -> 25` on three `PgDn`) | `06-` |
| Failure notice | still on the detail line in `All` (two-line rows), unchanged | section 4 |
| What changed at all | the header form, and the peek | - |
| **Did anything get worse** | **No.** And the column peek is a real gain here: on v0.5.0 `Comedy` is the last thing in the column with the separator directly under it, and nothing says sixteen more groups exist. Under test, `Shop 13` is clipped beneath it | `crop-55-v050-col.png` vs `crop-04-new-col.png` |

### 4. The failure notice, in the slot it moved to

Provoked for real: played `US (MAX) ESPN UNLIMITED (FEED)` from the
subscriber list; the stream failed on its own within 3 s and the channel was
marked (`failedAt {"u:74eadab4": "08:13"}`).

- **Unselected row:** `! Failed 08:13 - Space to retry` in the right meta
  slot, glyph and words adjacent and paired, name slot untouched
  (`crop-26-failed-unselected.png`).
- **Selected row:** same string, same place, legible (`crop-27-failed-selected.png`).
- **The design was right that the selected row is the hard case, and it is
  worse than "needs an eye".** Measured off the screenshots (sRGB relative
  luminance, modal background vs the text):

| Row state | Notice, glyph-body | Notice, peak stroke | Channel name, same row |
|---|---|---|---|
| Unselected | **4.79:1** | 7.13:1 | 9.52:1 |
| Selected (cursor) | **3.78:1** | 4.86:1 | 6.20:1 |

  Repeated on a second capture: identical to two decimals. The notice on the
  cursor row is the lowest-contrast text on the card and the only text that
  falls below 4.5:1, and it is the one string in the guide that tells the user
  what key to press. Filed as **D-GS-1 (P2)**.
- With a guide source configured the notice moves back to the detail line and
  the glyph to the trail slot, still paired (`crop-35-epg-failed.png`). Both
  row heights carry it, which is what GS2 asked for.

### 5. The guide-data caveat, and why it reads as broken

Set `tests/fixtures/qa-epg.xml` as the EPG for the subscriber source. It
fetched and parsed cleanly (`epg.loaded true`).

- Rows returned to two lines, visible rows **12 -> 9**, `pageSize()` **11 ->
  8** (`1 -> 9` on one `PgDn`). The reversal is exactly as section 12 states.
- **But the returned line is empty.** 1 of 3,335 entries in this playlist
  carries a `tvg-id`, so `rowDetail` has no now/next to print, and
  `rowShowsGroup` is false because the group does not narrow. Every row on
  screen is 52 px tall with a **blank** second line (`33-epg-configured-rows.png`).
  The user pays a third of the list for white space.
- This does **not** read as correct. It reads as a rendering fault. On v0.5.0
  the same configuration at least printed `United States`, which was useless
  but looked deliberate.
- The one signal that something is off is the footer, and it is elided
  mid-phrase: `Guide data warning: 27 programmes for chann...`. The second
  warning - `no EPG channel id matches a playlist tvg-id`, which is the one
  that explains the blank lines - is hidden behind a `(+1 more)`.
- Clearing the EPG field restored 12 single-line rows immediately, no
  restart (`41-epg-removed-rows.png`).

Filed as **D-GS-2 (P3)**: a two-line row whose detail line resolves to empty
for the whole scope. Any fix has to respect R-C (row height must not depend
on session-mutable state), so the honest options are a documentation change,
or making `epgConfigured` mean "this source's guide data matched something"
computed once per channel-set change rather than per session. That is a
design decision, not a diff, and it belongs to the owner of section 12.

### 6. Accessibility: unsettled, and for a bigger reason than GS5 expected

**No screen reader is installed on this machine** (`orca` absent, no
`pyatspi`), so the Orca pass of 9.2.8 could not be run. Rather than guess, I
probed AT-SPI directly:

- `at-spi2-core 2.60.6` is installed and `org.a11y.Bus` is running. With
  `toolkit-accessibility` off, `IsEnabled` is false.
- Enabled it; the shell connected to the accessibility bus within a second
  without a restart, and again after a restart with it enabled from startup.
- **Both times the shell's accessible root (`quickshell`, role
  `application`) reports `ChildCount 0` and `GetChildren` returns an empty
  array, with the guide open on 3,335 rows.** The registry lists it as an
  application; it publishes no objects. A GTK client on the same bus in the
  same moment (`xdg-desktop-portal-gtk`) reports a child, so the probe works.

So on this machine a screen reader would find nothing in the guide to
announce - not the row name, not the failure state, not `row N of M`. GS5's
question cannot double-announce here because nothing is announced at all.
**Marked unsettled, not passed and not failed.** The appended string costs
nothing where nothing is read, so I would leave it in place and keep GS5
open. The larger question - whether any of the guide's `Accessible.*` work
reaches AT-SPI on Quickshell layer-shell surfaces at all - is worth its own
scoped investigation and is not this lane's to answer. Filed as
**D-GS-3 (P3, investigation)**.

### 7. What the design did not anticipate

- **Removing an EPG URL leaves its cache behind.** After clearing the field,
  `epg.configured` goes false but `epg-now.json`, `epg-status.json` and
  `epg-window.txt` stay in the source's cache dir, and after the next shell
  restart the footer shows `Guide data warning: ...` again for a guide source
  the user has removed (`43-mode-check.png`, `epg.configured false` +
  `epg.loaded true` + two warnings in the same `status` reply). Pre-existing
  to this lane (EPG/Sources lifecycle). Filed as **D-GS-4 (P3)**.
- **Clearing the EPG field writes `"epgUrl": ""` into `shell.json`** rather
  than removing the key. Harmless, but it is a visible change to the user's
  config file produced by an action that removes a setting. Noted, not filed.
- **`Enter` closes the guide when it starts playback**, so the failure notice
  is only ever seen on the *next* opening. That is shipped behaviour and not
  this lane's, but it means the new meta-slot string is first read in a list
  the user has just re-entered, with the cursor elsewhere - which is why the
  unselected-row rendering matters more than the selected one, and the
  selected one is still the one that falls under 4.5:1.
- **Process note for the next live lane.** A layer-namespace check is not a
  focus check. `hyprctl layers` still lists `omarchy-iptv` for a moment after
  the guide closes, and one batch of keystrokes aimed at the Sources screen
  landed in the user's focused application instead, which typed two
  characters into a text box and eventually raised a file-chooser dialog. The
  dialog was cancelled (`hl.dsp.window.close`, nothing selected) and the
  desktop compares clean against the opening capture (section 10). **Two
  stray characters are left in that application's input box and were
  deliberately not removed**: clearing them means typing into the user's own
  window, which is not this lane's to do. The guard has to be re-run
  *between* keystrokes, not once per batch, and any step that can close the
  guide has to be re-verified before the next key.

### 8. Defects

| ID | Sev | Where | What |
|---|---|---|---|
| D-GS-1 | P2 | `Guide.qml` meta slot, D4 | `Failed HH:MM - Space to retry` on the **cursor** row measures 3.78:1 glyph-body / 4.86:1 peak against `Color.menu.selectedBackground`, below 4.5:1, while the same string off-cursor measures 4.79:1 / 7.13:1. It is the only text on the card under the threshold and it is the one that names a key. The design flagged the row state as needing an eye (9.2.5) and accepted whatever the eye said; the eye says legible-but-weakest, and the number says under AA |
| D-GS-2 | P3 | `Model.rowsHaveDetail` / `rowDetail`, D3 | On a one-group playlist with an EPG configured but no `tvg-id` matches, every row is 52 px with an **empty** detail line: the density is spent and nothing is printed. Section 12's caveat describes the trade as density-for-now/next; on this playlist it is density-for-nothing |
| D-GS-3 | P3 | host / plugin a11y | The shell publishes an empty AT-SPI tree (`ChildCount 0`) with the guide open, so no screen reader on this machine can read any of the guide - including everything UX 7.2 mandates. Not caused by this lane; it makes GS5 unanswerable here |
| D-GS-4 | P3 | EPG/Sources lifecycle | Clearing a source's EPG URL leaves `epg-*.json` in its cache, and the guide-data warning returns in the footer after the next shell restart for a guide source that is no longer configured |

Nothing in D1-D6 behaved differently from its specification. All four are
findings about what the specification produces, which is what this pass was
for.

### 9. Credential sweep

The subscriber list was added **as a local absolute path**; the provider's
credentialed playlist URL was never typed, never stored, never fetched.

| Sink | Result |
|---|---|
| `status` JSON | `sourceHost: "local file"`, no path, no URL |
| Sources screen and rows | `USChannels.m3u - local file - 3,335 channels in 1 group`; no path on the row |
| Guide header, footer, row text | label only |
| This file and the evidence tree | **0 byte-exact hits** for the provider's host across `docs/` and `/tmp/claude-1000/omarchy-iptv-qa14/`, and no stream URL in any screenshot (the Sources row reads `local file`, the form fields held the local path). The only URLs in the tree are inside the untouched snapshot copies of the user's own `state.json` and `shell.json`, which carry the public iptv-org playlist address and no credential; every URL written into this file is redacted to scheme and host |
| `state.json`, `shell.json` | 0600, and both restored byte for byte |
| Playback | one channel played and one failed through the product path; the stream URL reached mpv over the private socket, never a command line (`ps` showed the channel id only) |

### 10. Machine restored, proved

| Item | Proof |
|---|---|
| `~/.config/omarchy/shell.json` | `sha256sum -c` **OK** against the opening snapshot, mode 0600. It had gained `"epgUrl": ""`; restored with the shell stopped, and still OK after 25 s of the shell running |
| `~/.local/state/omarchy-iptv/` | every file sha256-identical, tree and modes identical (`700` dir, `600` state.json), unchanged after 25 s |
| `~/.cache/omarchy-iptv/` | every file sha256-identical, tree and modes identical; the test source's whole cache dir removed through the product's own `x` confirm (`Remove "USChannels.m3u"? Its cache is deleted too.`) |
| Test source | gone: `sources` back to one entry, `activeSource iptv-org.github.io` |
| EPG setting | removed, `epg.configured false`, `warnings []` |
| Installed plugin | back on `db47c37`, `* main db47c37 [origin/main]`, porcelain empty, `refs/qa14/under-test` deleted (0 refs left), **all 106 files sha256-identical** to the opening manifest, `validate` rc 0 |
| Running plugin | `ready`, 1,472 channels, 28 groups, 0 favorites, **7 recents**, `lastUpdated 05:41`, `failedAt {}` - the opening capture field for field |
| Player | `pgrep -x mpv` empty; playback stopped through the plugin's own `stop` verb |
| Accessibility setting | `toolkit-accessibility` back to `false`, `IsEnabled false` |
| Windows | opening 1 client, closing 1 client, **SAME** on class/at/size/floating/pinned/workspace/monitor/tags; focused window **SAME** (`0x559c687e09a0`); workspaces `[(1, 1)] -> [(1, 1)]` **SAME** |
| Theme | `Retropc` |
| Repo | `main`, `030ba9b`, porcelain empty apart from this file |

One honest note, and it cost twenty minutes: **the plugin wins any edit to
`state.json` made under a running shell.** Writing the snapshot bytes while
the shell was up was undone within 1-2 s by the plugin's own `FileView` write
(watched: restored hash at t=0, plugin's hash at t=1, stable from t=2), and a
restart immediately afterwards made it worse - the new process read a file
the dying one had already rewritten, found no sources, re-migrated
`playlistUrl` from `shell.json` and dropped all seven recents. The fix, and
the recipe for the next lane: stop the shell with
`quickshell kill -p /usr/share/omarchy/shell --any-display` until it exits,
overwrite the files **in place** with nothing running, then relaunch with
`hyprctl dispatch 'hl.dsp.exec_cmd("omarchy-launch-shell")'`. Restore before
relaunch, never after.

### Verdict

**GO**, with D-GS-1 fixed first.

Four of the five changes are a plain improvement on the surface the user
looks at daily, and the two the design was least sure about - the column
losing a row on a one-group playlist, and a number moving in the header -
are both fine in practice. The many-small-groups shape did not pay for it.

D-GS-1 is small and worth doing before release: the string that tells a user
which key retries a dead channel is the least legible text on the card
exactly when the cursor is on that channel, which is exactly when they are
about to press it. A rung of opacity, or the selected-row foreground, fixes
it inside the existing tokens.

D-GS-2 is not a release blocker but section 12's caveat should be rewritten
before it reaches the README: on a playlist with no `tvg-id` the EPG trade is
not "density for now/next", it is density for a blank line, and a user who
configures guide data and gets that will file it as a bug.

D-GS-3 leaves GS5 open. Per the ruling's own terms, the addition stays until
a real screen-reader pass can be run; it is announced to nobody today.

---

## Accessibility harness runs (TC-A11Y-01, TC-BAR-11, SRC-A11Y-01, SRC-A11Y-05)

**Runs filed as of 2026-09-15: none. All four cases are therefore UNSATISFIED,
and that is the honest state, not a regression.** Until this pass they read
`pass` on the strength of a `grep` for strings the implementation was written
to contain -- a criterion that cannot go red (CLAUDE.md rule 14). They now read
`not run` until a run is filed here, which is a worse-looking board and a truer
one. SRC-A11Y-05 is the sharpest example: it claimed to prove that no secret
reaches a screen reader, and a secret was reaching that sink the whole time it
passed (D-A11Y-1).

### What a filed run must contain

One subsection per run, headed `### <date> <time>, <commit>, <host summary>`,
carrying:

1. **The invocation**, verbatim, and the harness commit. A run is evidence
   about the harness that produced it, not about a harness in general.
2. **The full check list**, one line per check id, `pass` / `fail`, with the
   observed value on any failure. Totals: checks run, failures. A run that
   reports fewer checks than the previous filed run is a regression in the
   harness and is called out as one.
3. **The fidelity result.** The harness grades a generated copy of `Guide.qml`
   and a copied host UI kit, not the shipping files. Every claim a run makes is
   void if the copy has drifted, so the fidelity guard's result is part of the
   run, not a separate concern (`tests/a11y/test_fidelity.py`).
4. **The mutation evidence** required by CLAUDE.md rule 11: which assertions
   were mutated, and that each went red. A check nobody has seen fail is
   decoration, and this whole area is what that rule was written about.
5. **The markup/delivery split, restated.** A green run means the plugin's
   accessibility markup becomes correct nodes in a plain Qt window. It does
   **not** mean a screen reader can use the shipping guide: no window
   Quickshell creates publishes a tree at all (D-GS-3, quickshell issue 1144).
   A run that is quoted without this sentence is being misquoted.

### What a green run does not mean

A remedy for D-A11Y-1 was once reported by a checker as "19 checks, 0
failures", and the remedy silently replaced the user's stored credentials with
the mask and saved clean. The check asked only whether a secret was absent, and
absence was achieved by destroying the data. **Absence of a secret is not a
pass.** SRC-A11Y-05 accordingly requires the field to be undamaged as well as
the bus to be clean, and a run that reports only the absence half is not a run
of SRC-A11Y-05.

### Status of the four cases

| Case | Was | Is | Satisfied by |
|---|---|---|---|
| TC-A11Y-01 | `A grep -n 'Accessible\.' Guide.qml BarWidget.qml` | `X` harness, guide scenarios | a run filed above; markers in `docs/UX.md` 7.1 say which rows it covers |
| TC-BAR-11 | `A grep -n 'Accessible' BarWidget.qml` | `X` harness, bar scenarios | as above |
| SRC-A11Y-01 | `A grep -n 'Accessible\.' Guide.qml` | `X` harness, Sources and form scenarios | a run filed above; markers in `docs/UX-SOURCES.md` 7.1 |
| SRC-A11Y-05 | `A grep` | `X` harness, Xtream and form scenarios, asserting the **Value** and the field's integrity | a run filed above, containing both halves |

## Live pass 2026-09-21, segment A: contrast and accessibility

Display lane, on the user's live session, with written authorization for
exactly: opening the guide and typing into it, three theme switches restored
to Catppuccin, cropped local captures, a local served stream, and the AT-SPI
probe. Code under test: the INSTALLED plugin 0.7.2 at
`~/.config/omarchy/plugins/io.github.rmcdavid.iptv` (never written).
Measured 15:48:24-16:00:07, about 12 min of display time (14 min from the
15:45:54 snapshot). Evidence root
`E=/tmp/claude-1000/live-A/`: `shots/` (38 crops, PPM + PNG, card 960x620 at
203,74 and bar strip 1366x26; every full frame was deleted in the same script
step that cropped it, `full/` is empty), `logs/` (phase transcripts,
`shell-<slug>.toml` copies of the generated theme tokens, `a11y-probe.log`,
`nodes-<scenario>.json` bus dumps), `snapshot/` (pre-pass copies), `px.py`
(stdlib PPM crop / measure / histogram), `sites.py` (the site boxes),
`predict.js` (calls `Model.js` for every prediction; nothing recomputed by
hand), `restore.sh` (the EXIT/INT/TERM trap of every phase script).

Method: the ruling's own. `grim -t ppm` of the running shell, a tight box per
site, the modal colour of the box as the background, the single
most-contrasting pixel as the fully-covered stroke, WCAG 2.1 ratio. Every
prediction is `Model.relativeLuminance` / `contrastRatio` / `colorOver` /
`cursorInk` / `BAR_IDLE_ALPHA` from the dev-branch `Model.js` (the installed
`Model.js` returns the same `cursorInkHex`), fed the tokens read from the
generated `~/.local/state/omarchy/current/theme/shell.toml` after each switch
(copies in `E/logs/shell-*.toml`; `[menu]` text / background /
selected-background 0.08 / selected-text are identical to the theme's
`colors.toml` on all three themes). Captures were taken 2.5 s or more after a
switch; the settled Catppuccin frame was 11 s after. `pgrep -x hyprlock` was
empty before every `wtype`, and every keystroke was gated on the
`omarchy-iptv` layer being up and `status` reporting `ready`.

**One correction to the protocol as written**: the guide opens in SEARCH
mode, so the first sources attempt typed `o`, `a` and the path into the query
(`E/shots/src-add-typed.png`; harmless, 0 matches, Esc). `Tab` first, then
`o`, works (`E/shots/src2-*.png`).

### 1. Calibration top-up (CONTRAST-RULING Step 2)

Measured ratio, model prediction, delta (measured minus model). Sites in
`E/shots/<slug>-A-card.ppm` unless stated. Box coordinates: the card sites are
in `E/sites.py`; the boxes that file does not hold are recorded here so every
figure below reproduces without re-locating them (card coordinates; the
empty-state title and prose boxes were on file nowhere and are the audit's,
which reproduce 3.31 / 3.21, 4.62 / 4.49 and 6.17 / 5.98 exactly): `leftRule2`
235,66 6x40 (the cursor mark over the card, section 4); `emptyGlyph` 455,278
50x26, `emptyTitle` 380,318 200x18 and `emptyProse` 400,345 160x16 on the
`*-B-card` crops; the bar glyph runs x 923-932 (playing) and x 1039-1050
(idle), y 3-23, on the `*-bar-{playing,idle}` strips; and the closed-bar
boxes, clock 641,4 85x18 and glyph 1036,4 18x18, on `catppuccin-closed-bar`
(section 3).

| Site (size, alpha, surface) | rose-pine | tokyo-night | catppuccin |
|---|---|---|---|
| cursor-row name (14 px, 1.0, cursor fill) - rendered ink | `#59537e` **5.83** | `#a7b0cf` **6.86** | `#c5d5f2` **9.13** |
| ... model `cursorInk` says | `#576684` 4.72 (+1.11) | `#7aa2f7` 5.87 (+0.99) | `#89b4fa` 6.44 (+2.69) |
| ... text over the cursor fill says | 5.94 (-0.11) | 7.00 (-0.14) | 9.38 (-0.25) |
| cursor mark, left rule (2 px, on the card) | `#575279` 6.66 | `#a9b1d6` 8.10 | `#cdd6f4` 11.34 |
| ... model (`cursorInk` on the card) | 5.30 (+1.36) | 6.79 (+1.31) | 7.79 (+3.55) |
| non-cursor name (14 px, 1.0, card) | 6.59 / 6.66 (-0.07) | 8.03 / 8.10 (-0.07) | 11.25 / 11.34 (-0.09) |
| detail line (11 px, 0.52, card) | 2.28 / 2.33 (-0.05) | 3.08 / 3.16 (-0.08) | 3.97 / 4.07 (-0.10) |
| detail line (11 px, 0.52, cursor fill) | 2.15 / 2.24 (-0.09) | 2.81 / 2.98 (**-0.17**) | 3.48 / 3.71 (**-0.23**) |
| header scope label (10 px, 0.52, card) | 2.16 / 2.33 (**-0.17**) | 2.87 / 3.16 (**-0.29**) | 3.67 / 4.07 (**-0.40**) |
| group entry count (10 px, 0.7) | 2.96 / 3.34 (**-0.38**) | 4.12 / 4.64 (**-0.52**) | 5.45 / 6.24 (**-0.79**) |
| footer status line (10 px, 0.7) | 3.05 / 3.34 (**-0.29**) | 4.25 / 4.64 (**-0.39**) | 5.70 / 6.24 (**-0.54**) |
| footer verbs (10 px, 0.7) | 3.15 / 3.34 (**-0.19**) | 4.30 / 4.64 (**-0.34**) | 5.70 / 6.24 (**-0.54**) |
| Sources pinned count (10 px, 0.7) | 2.96 / 3.34 (**-0.38**) | 4.12 / 4.64 (**-0.52**) | 5.46 / 6.24 (**-0.78**) |
| empty-state title (14 px, 0.7) `*-B` | 3.31 / 3.34 (-0.03) | 4.62 / 4.64 (-0.02) | 6.17 / 6.24 (-0.07) |
| empty-state prose (12 px, 0.7) `*-B` | 3.21 / 3.34 (-0.13) | 4.49 / 4.64 (-0.15) | 5.98 / 6.24 (**-0.26**) |
| empty-state glyph (28 px, accent 0.8) `*-B` | `#77a7af` 2.42 / 2.42 (0.00) | `#6787cd` 4.82 / 4.82 (0.00) | `#7496d1` 5.49 / 5.48 (+0.01) |
| bar idle glyph (text 0.86, bar) `*-bar-idle` | `#6e6989` 4.75 / 4.77 (-0.02) | not captured | `#b4bcd8` 8.69 / 8.72 (-0.03) |
| bar playing glyph (text 1.0, bar) `*-bar-playing` | `#575279` 6.66 / 6.66 (0.00) | not captured | `#cdd6f4` 11.34 / 11.34 (0.00) |
| GROUPS header (10 px bold, `Qt.darker` 1.4) | `#3e3b57` 9.77 / 9.82 (-0.05) | `#797e98` 4.27 / 4.29 (-0.02) | `#9299ad` 5.77 / 5.77 (0.00) |

Catppuccin was captured twice (`catppuccin-A`, `catppuccin-settled`, 11 s
apart); every site agrees to two decimals. Read across the rows:

- **The model is accurate to 0.10 for 11-14 px text at 1.0 and 0.52 on the
  card, and to 0.03 for the 28 px glyph and the bar glyph.** The one
  requested sample between alpha 0.6 and 0.9 exists twice in shipping code:
  the empty-state glyph at 0.8 (delta 0.00 to +0.01 on all three themes) and
  the bar idle glyph at 0.86 (delta -0.02, -0.03). No adjustment is warranted
  there.
- **Every 10 px regular-weight caption reads 0.17 to 0.79 below the model**,
  which is 11 to 13 per cent of the ratio (catppuccin group count 5.45 / 6.24
  = 0.873; rose-pine 0.886; tokyo-night 0.888), worse than the 7 to 9 per
  cent the D-RUNG-4 row recorded. The 10 px BOLD host header does not lose
  it (delta 0.00 to -0.05): the loss is stroke coverage, not size. **Finding
  F-CAL-1**: `maxAbsError` 0.15 does not hold for caption text at 0.7; it
  is reported here, not adjusted by the pass. (Applied afterwards under the
  lead's F-CAL-1 ruling: every fixture row carries a `sizeClass`, a caption
  row is allowed 15 per cent of its measured value, every other class keeps
  `maxAbsError` 0.15, and the calibration block of `tests/Model.test.js`
  derives its expectations from the rows.)
- **The rows were appended to `tests/fixtures/contrast-calibration.json`**
  (17 rows: cursor 1.0 / cursor 0.52 / row 1.0 / row 0.52 / row 0.7 for each
  theme, and bar 0.86 for rose-pine and catppuccin; existing rows and
  `maxAbsError` untouched). Consequence, measured: `node tests/Model.test.js`
  goes from **1434 checks, 0 failures** to **1434 checks, 2 failures**, both
  at the calibration checks. The tolerance check fails on VALUE for the six
  caption / cursor-fill samples above 0.15 (rose-pine row 0.7, tokyo-night
  cursor 0.52 and row 0.7, catppuccin cursor 1.0, cursor 0.52 and row 0.7)
  and would fail on SHAPE regardless, because its expected value is a
  hard-coded `[true x 6]`; and "the refuted claim restated" fails because the
  worst delta is now 0.79, not under 0.2. The optimism check stays green: all
  23 samples are still below their prediction. Not committed by the pass;
  the lead's ruling is F-CAL-1, above. Note that three of the six samples
  over 0.15 are not captions: they are the 11 px detail line and the 14 px
  name ON THE CURSOR FILL (tokyo-night cursor 0.52, catppuccin cursor 1.0
  and 0.52), off by 0.17, 0.25 and 0.23 against the text class's 0.15. The
  model's arithmetic is not at fault there (section 4: the fill measures as
  modelled and the rendered ink is the text token less a few units of
  coverage). **Finding F-CAL-2**: the cursor-fill side loses more than the
  card on five of the six themes in the fixture, and the same on retropc
  (0.12 on both), but this pass, like the one before it, measured a
  DIFFERENT string on each surface (`cursorName` is row 1 and `rowName` is
  row 2 in `E/sites.py`, on every theme), so a surface effect is not
  separated from the peak coverage of those particular glyphs; the row
  delegate carries no transform, Behavior or animation that would move its
  text off the pixel grid (`Guide.qml:2480-2600`). Ruling: the three rows
  are pinned by name in the fixture (`knownDeviation: "F-CAL-2"`) and the
  test holds them strictly, red the day one of them holds, so no tolerance
  widens; the next live pass measures ONE string on both surfaces by moving
  the cursor one row.
- The consumer maps surface `bar` to the row fill; that is only valid because
  the generated `shell.toml` sets `[bar] background = [menu] background` and
  `[bar] text = [menu] text` on all three themes (`E/logs/shell-*.toml`),
  which the pass confirmed by reading the file, not by assuming it.

### 2. D-RUNG-5, the bar glyph, playing against idle

Local stream: `E/serve/test.ts` (the qa-player fixture, 900 s) served by
`python3 -m http.server 8765 --bind 127.0.0.1`, added as a file-path source
through the guide's own Add form (`E/shots/src2-typed.png`,
`src2-after-load.png`: `local file`, 1 channel, active), played by
`omarchy-shell io.github.rmcdavid.iptv play http://127.0.0.1:8765/test.ts`
(`ok`; mpv pids 1136680 and 1137651; an `omarchy-iptv` client appeared next to
the user's two windows and was gone after `stop`). The bar strip was captured
with the guide CLOSED, 1.5 s after `status` reported `playing:true, up:true`,
and again 1.5 s after `playing:false` with no mpv. Nothing left the machine.

| Theme | glyph run | playing | idle | model active / idle |
|---|---|---|---|---|
| rose-pine | x 923-932 playing, x 1039-1050 idle | `#575279` **6.66** | `#6e6989` **4.75** | 6.66 / 4.77 |
| catppuccin | same | `#cdd6f4` **11.34** | `#b4bcd8` **8.69** | 11.34 / 8.72 |

D-RUNG-5's fix is **live-confirmed**: the idle glyph is dimmer than the
active one on a light theme and a dark one, and on rose-pine, the binding
theme, the idle glyph renders at 4.75 against the 4.77 floor
`Model.BAR_IDLE_ALPHA` was chosen for - 0.25 above 4.5, so the calibrated
margin held with 0.10 to spare. Evidence `E/shots/{rose-pine,catppuccin}-bar-{playing,idle}.{ppm,png}`.

### 3. D-RUNG-6 is a METHOD defect, settled

`E/shots/catppuccin-closed-bar.ppm`: guide closed, no theme switch for over
two minutes, no typing. Histogram of the ratio of every pixel in each glyph's
bounding box against the bar background `#1e1e2e`:

| Glyph | box | ink px | distribution | peak |
|---|---|---|---|---|
| host clock `Monday 15:53` (12 px digits) | 641,4 85x18 | 320 of 1530 (21%) | spread evenly from 1.5 to 11.5, 8 to 31 px per half-ratio bin | `#cdd6f4` **11.34** = the full text token |
| our TV glyph U+F0502 | 1036,4 18x18 | 64 of 324 (20%) | 27 px at 8.0-8.5 (fully covered strokes), 20 px at 1.5-2.0 (edges), 11 px at 6.0 | `#b4bcd8` **8.69** = `colorOver(text, bg, 0.86)` 8.72 |

**Neither glyph shows the deficit.** The host's thick clock reaches its full
token and our thin glyph reaches its 0.86 rung, both within 0.03. So it is
not stroke weight. The half-opacity observation reproduces exactly and has a
cause: **the bar was captured with the guide open, and the guide's own
full-screen PanelWindow paints `Color.menu.scrim` (background at alpha 0.5)
over the bar** (`Guide.qml:1912-1926` in the INSTALLED 0.7.2 file; on the dev
branch the same PanelWindow is at `Guide.qml:1946-1984`; anchored to all four
edges, `ExclusionMode.Ignore`). Proof by arithmetic on this pass's own frames: the
bar crop taken through the open guide (`E/shots/catppuccin-A-bar.ppm`, same
minute, same theme) peaks at `#757a91` **3.87**, and
`Model.colorOver(#cdd6f4, #1e1e2e, 0.5)` gives `[117.5, 122, 145]`, `#767a91`
rounded (3.87 unrounded, 3.88 as the hex), one unit off the measured
`#757a91` in red and the same 3.87 to two decimals. And D-RUNG-6's own rose-pine
figure, `#a8a3b3` at 2.25: `Model.colorOver(#575279, #faf4ed, 0.5)` gives
`#a9a3b3` (2.24) against the measured `#a8a3b3` (2.25). The P2 evaporates; Omarchy's bar text is fine
and there is nothing to report upstream. Recommend closing D-RUNG-6 as a
capture through the scrim and lifting the "UNASSERTED" on D-RUNG-3's
threshold claim, which the table in section 1 now asserts on two themes.

### 4. D-RUNG-7, the cursor ink, settled with the mechanism

The three resolved tokens, read from the generated `shell.toml` after each
switch (`E/logs/shell-*.toml`), and what `Model.cursorInk` computes from them
against what rendered:

| Theme | accent (`selected-text`) | text | fill (`selected-background` 0.08 over background) | model ink | rendered name ink | rendered left rule |
|---|---|---|---|---|---|---|
| rose-pine | `#56949f` | `#575279` | `#ede7e4` (measured modal `#ede8e4`) | `#576684` (mix 0.70) | `#59537e` | `#575279` |
| tokyo-night | `#7aa2f7` | `#a9b1d6` | `#252734` (measured `#262734`) | `#7aa2f7` (mix 0) | `#a7b0cf` | `#a9b1d6` |
| catppuccin | `#89b4fa` | `#cdd6f4` | `#2c2d3e` (measured `#2c2d3e`) | `#89b4fa` (mix 0) | `#c5d5f2` | `#cdd6f4` |

The rendered left rule is the menu TEXT token to the byte on all three
themes, including the two where the model says the accent survives
untouched. The runtime ink is `Color.menu.text` everywhere, never the
accent. The cause is in the host kit, read not guessed:
`/usr/share/omarchy/shell/Commons/Color.qml:99` defines
`menu.selectedBackground` as `Util.alpha(flatColor(...), 0.08)`, a QColor
whose r, g, b are the FOREGROUND's and whose alpha is 0.08 - it is never
composited. `Model.qmlRgb` (`Model.js:4465-4469`, dev and installed alike)
reads `c.r, c.g, c.b` and
ignores `c.a`, so `cursorInk` receives the text colour as its "fill",
`contrastRatio(accent, text)` is far under 4.70, the mix walks toward the
text and can never reach 4.70 against the text itself, and the loop falls
through to `return text`. **Finding D-RUNG-13 (P3)**: the cursor
row has lost its accent on every theme, not the eight the design costed; the
direction is safe (5.83 / 6.86 / 9.13 against the fill), the D-RUNG-4 defect
is still fixed, but the "15 of 23 byte-identical" claim is false on screen.
Fix shape: composite in `qmlRgb`/`cursorInkHex` when `c.a < 1` (over
`Color.menu.background`), or hand `cursorInkHex` the alpha and the
background; then the model's `#576684` on rose-pine can be checked against
the screen. The model's own contrast arithmetic is not at fault: text over
the fill predicts 5.94 / 7.00 / 9.38 and the screen reads 5.83 / 6.86 / 9.13.

#### Settled 2026-09-21, after the costing and the UX panel

The mechanism above was fixed (`Model.qmlFill` composites the alpha-carrying
fill over `Color.menu.background` before the comparison; `cursorInkHex` takes
the surface as a fourth argument), but the corrected ink was NOT given to the
cursor row. Costed across all 23 themes by calling the shipping code: inking
the cursor-row name would lose contrast on **22 of 23 themes, median 31 per
cent, worst white 17.55 -> 4.78 (-73%)**, and on **23 of 23** it would leave
the selected row's name FAINTER than an unselected row's. On `white`,
`vantablack` and `solitude` the accent is achromatic (HSV saturation 0.00,
0.00, 0.10), so those three pay 73, 70 and 53 per cent of the row's contrast
for no hue at all. A UX panel recommended inking it anyway; a refuter
overturned that on these numbers, which the panel's floor figure
(5.94 -> 4.70) had hidden entirely, since the floor theme is among the
smallest movers.

**PO ruling 2026-09-21: the 2 px mark means CURSOR, the accent means ACTIVE.**
The cursor row keeps the plain text token on every element and the mark
carries selection; `Color.menu.selectedText` marks which group is filtering
and which dialog button is chosen. Consequences, all shipped together:

- The mark is **pinned** to `Color.menu.text` (`Guide.qml`, channel delegate).
  Measured on this pass's own frames, rose-pine x238 card / x239-240 mark /
  x241 fill: its right edge and both rounded ends abut the FILL, so the fill
  governs it. As the text token it measures 5.94 at the floor; as the raw
  accent it would measure 2.80. The comment claiming it "sits on the card" was
  wrong and is corrected. Without the pin the seam fix alone would have
  silently inked it, because the mark and the name read the same property.
- **Finding D-RUNG-15**: the selected GROUP label inked with the RAW accent and
  sits on the fill, so it was under 4.5:1 on **8 of 23** themes, floor 2.7969
  (rose-pine). No gate reported it -- the gate matched one spelling. Fixed by
  pointing it at `Model.cursorInkHex`: 0 of 23 under 4.5, floor 4.7025, accent
  untouched on 15 themes. This is the site `cursorInk` was written for and had
  never been aimed at.
- The **Sources list gained the mark** (F-RUNG-8's carve-out was that defect
  stated in passing): its cursor had only the 1.12-1.23 fill and a 0 px
  border, and its cursor-only buttons appear on source rows alone.
- The four informational 10 px captions are **bold** (D-RUNG-14).

Test discipline: the `cursorInkHex` double now carries the host's real alpha,
three inventories pin the accent sites, the cursor-ink consumers and the
cursor marks themselves, and each was proven by a mutation that turns exactly
it red -- including one that caught the Sources mark shipping with no test at
all.

### 5. D-RUNG-1, D-RUNG-9, D-RUNG-11; D-RUNG-10 and D-RUNG-12 blocked

- **D-RUNG-1** (the 0.7 caption sites, table in section 1): catppuccin
  5.45-5.70 (clear), rose-pine 2.96-3.15 (under, as the model says), and
  **tokyo-night 4.12-4.30, UNDER 4.5 where the model says 4.64 and counts the
  theme as passing.** With an 11-13 per cent caption loss, any theme whose
  model value is under about 5.1 fails on screen, so SG2's "6 of 23 under" is
  understated. Finding D-RUNG-14.
- **D-RUNG-9**: the GROUPS host header renders at model accuracy (bold):
  rose-pine 9.77, catppuccin 5.77, **tokyo-night 4.27 under 4.5**, confirming
  the ruling's 4.28 on screen.
- **D-RUNG-11**: the 28 px empty-state glyph (`Model.GLYPHS.tvOff`, accent at
  0.8) after typing `/zzqxv` (`E/shots/*-B-card.png`): **rose-pine 2.42**,
  under the 3:1 large-text floor exactly as modelled; tokyo-night 4.82,
  catppuccin 5.49. Confirmed on screen; the raise-the-rung remedy is safe to
  size from the model, which is exact at this size.
- **D-RUNG-10** (EPG hairline) and **D-RUNG-12** (non-cursor channel number):
  **BLOCKED** on this install: the cached iptv-org US list
  (`~/.cache/omarchy-iptv/sources/d5977d8a/channels.json`) holds 1471
  channels, 0 of them with a `chno` or `number` field, and the only source
  record in `~/.local/state/omarchy-iptv/state.json` has `epgUrl` `""`, so
  neither site renders and nothing was measured. Not faked. (Both facts are
  read from those files; the phase scripts' gate grepped `status` only for
  `ready` and kept no output, so no log under `E/logs` records `hasNumbers`
  or `epg`.)
- Also captured, unmeasured for time: the remove-source ConfirmDialog with
  `Remove` preselected (`E/shots/src2c-confirm.png`), the fifth D-RUNG-4
  site.

### 6. D-A11Y-4: all eight declared roles on the real bus

`./scripts/a11y-probe.sh` (`E/logs/a11y-probe.log`): no drift, **64 checks,
4 failures**. Three are the recorded baseline (L2-XT-05, L2-XT-06, L2-XT-11).
The fourth, **L2-SC-02** (`10,000 channels: the group entry counts in words,
thousands separated`, expected `All, 10,000 channels`), is NEW against the
baseline in `docs/QA-A11Y.md` and is reported as observed; whether it is a
regression on dev or a scenario timing issue was not investigated in this
segment. Then `tests/a11y/walk.py` was run directly on the same tree for the
`query`, `querynomatch`, `xtream`, `firstrun`, `banner` and bar `idle`
scenarios (`E/logs/nodes-*.json`, 24-33 nodes each, all settled in 3 walks),
and every node was tabulated by role, extending the three-row table at
`docs/QA-A11Y.md:417`:

| Declared role | AT-SPI role | `Accessible.name` reaches the bus | Text interface | What the text body carries |
|---|---|---|---|---|
| `Button` | push button | yes (7-11 per scenario, all named) | none | - |
| `List` | list | yes (3 of 3: Groups, Channels in All, Sources) | none | - |
| `Dialog` | dialog | yes (IPTV guide, the confirm message, the form title); the unnamed dialog is the sources form, named only when `headerTitle` is set (`Set up a playlist`, `Add Xtream login`); the ConfirmDialog is always named | none | - |
| `AlertMessage` | alert message | yes when non-empty (the banner; `Entering channel number ...`); empty ones publish `''` | none | - |
| `StaticText` | label | yes | Text | **the name**, verbatim (`No channels in All`, `3 channels - updated 0`, the first-run prose); the element's own `text` never appears |
| `ListItem` | list item | yes (`BBC One HD, row 1 of 1`; the source row with its counts) | none | - |
| `EditableText` | text | yes (`Search channels`; `Playlist URL or path`; `Server URL`; `Username`; the password field has name `''` and description `Password`) | Text, plus EditableText on real fields | **the element's own displayed text**: the search line publishes `bbc` with an active query and its PLACEHOLDER `Search channels...` when empty; the fields publish their values, including `USERTOKEN2` and the Server URL with the login in its query string (the D-A11Y-1 exposure, seen at the sink again); the password field publishes bullets |
| `Heading` | heading | yes when `headerTitle` is set (`Add Xtream login`, `Add source`); `''` in list mode | Text | **the name** (equal to it in every sample; `''` when unnamed) |

New against the three-row table: `Heading` behaves like `StaticText` (a Text
interface carrying the name), `AlertMessage`, `List`, `ListItem` and `Dialog`
carry no text interface at all, and the search line's placeholder reaches
the bus as its value. No role was unreachable; the bar scenario publishes
exactly one push button and nothing else. All of this is on a hidden Qt
window; nothing Quickshell shows publishes a tree (D-GS-3), unchanged.

### 7. Machine restored, proved at 16:00:08

`sha256` of `shell.json` `af7ef4195973f031...` and of `state.json`
`79bd045f401bed91...` equal the snapshot (the lead's own values); `diff -r`
of the cache directory and of the state directory against the snapshot:
identical; modes 700/600 intact; theme `Catppuccin`; no `omarchy-iptv`
layer; no mpv, no cage, no `http.server`, nothing listening on 8765; the only
quickshell is pid 1058; `E/full/` empty and no PPM outside `E/shots/`; the
user's two clients (`com.anthropic.Claude` on workspace 1, `chromium` on 2)
present; hyprlock never ran. The temporary source was removed through the
guide's own confirm dialog before the file restore, and the running shell's
in-memory state agrees with the restored file (`status`: 1 source, 7
recents). Residuals: none known. Nothing left the machine.

## Live pass 2026-09-22: 0.7.3 in actual use, on the real display

The maintainer asked for 0.7.3 to be given real use while away from the
machine. Driven through the plugin's own IPC (`toggle`, `play`, `stop`,
`status`) rather than keystrokes, with one `wtype` to type a query. Snapshot
first, state restored on exit and verified identical. The source is
`iptv-org.github.io`, the free public playlist, so no credentials and no paid
subscription were involved.

**What worked.** The guide opens and renders correctly; the 2 px cursor mark is
visible and measures `#cdd6f4` at **9.3561** against the fill -- the text token
byte-exact, identical to the headless figure. The cursor-row name renders the
text token (`#c5d5f2`, 9.1326), not the accent, so the 2026-09-21 ruling is in
force on screen. The selected group label renders the calibrated active ink
(`#83adf4`, 5.9593), D-RUNG-15's fix, matching headless exactly. Playback
started, the bar widget showed the channel name with live throughput, a zap
worked, and `stop` left no mpv behind.

**D-PLY-14, found by using it.** A transient error during first load marks a
channel failed, and nothing clears that mark when the stream recovers. The end
state was self-contradictory and user-visible: status reported `playing: true`
with `nowPlaying` set to the same id that appeared in `failedAt`; mpv reported
`video-format: h264`, 33.9 s of demuxer cache and `eof-reached: false`; the bar
showed the channel and its throughput -- and the guide row read
`Music - Failed 15:07 - Space to retry` with the alert glyph and neither the
playing glyph nor the bold name, because the failure state displaces the
playing state. `raiseStreamFailure` sets the mark; the only clear runs when a
play STARTS, not when one succeeds. The hook for the fix already exists and
already runs every 10 s: the healthy branch of the status check.

**F-CAL-3, and it undoes a claim made yesterday.** The four bold caption sites
measured 6.2377 under headless cage -- model accuracy, which is what D-RUNG-14
rested on. On the live display, same day, same theme, same code, they read
5.4475, 5.4590, 5.6956 and 5.8559. **5.45 is exactly what the REGULAR weight
measured on this display on 2026-09-21**, so bold changed nothing the user can
see. The bold is applied (four `font.bold: true` on the right elements in the
installed file) and a real Bold face resolves (`fc-match monospace:bold`), so
this is glyph rasterisation differing between the two environments.

The control makes that conclusive: the 2 px cursor mark, a SOLID shape,
measured **9.3561 in both environments** -- identical. Colour and compositing
agree; only text differs. So `contrast-calibration.json` currently mixes
environments -- its 2026-09-21 rows are live, its 2026-09-22 rows headless --
and does not describe one rendering.

**Process note, recorded because it nearly went wrong.** One capture was taken
while the guide was in fact closed, and the fixed crop coordinates caught the
desktop instead of the card. It was deleted immediately and not examined. The
cause was using hardcoded coordinates instead of the card-detection guard
written earlier the same day; every capture after that point goes through a
wrapper that refuses to write a crop unless the card fill dominates its own
centre line, and the two retained images were verified to be plugin surfaces
only. Full frames are deleted as soon as a crop is taken.

## Defect hunt 2026-09-22: four areas, adversarially verified

The board had reached zero open rows, so rather than wait for defects to be
reported, four lanes went looking -- the helper, the service and its state, the
player path, and CLAUDE.md rule 5's credential sinks. Every finding had to be
DEMONSTRATED by running the shipping code, and each lane's output was handed to
an independent lane told to refute it. One P3 was refuted outright and is not
filed (see the end).

### Fixed in this pass

**D-EPG-1 (P2), and it is the one that mattered.** `99991231235959` is a common
provider sentinel for a 24/7 stream. It parses to 253402300799 -- twelve digits
-- and the EPG record format is fixed-width TEN by contract: the readers slice
`[0:10]`, `[11:21]` and `[22:]` rather than splitting, because bisect over
fixed prefixes is what buys the 10,000-channel budget. `%010d` sets a minimum
width, not a maximum, so the title was pushed into the number field. Because
`epg-now.json` is written by concatenation, ONE such programme cost EVERY
channel of that source its guide data.

Silently: the helper exits 0 with `ok:true` and `nowCount` set, so the guide
shows no banner, no warning and no notification -- it reads exactly like a
provider shipping an EPG with no programmes -- and pressing `r` re-runs the
helper, which reports success again and rewrites the same broken file. The only
escape was removing the EPG URL.

An ELEVEN-digit stop was quieter and worse: valid JSON carrying a truncated
stop of 1000000000, September 2001, so the row rendered as having nothing on.
Valid-but-wrong beats unparseable, because nothing anywhere reports it.

Fixed by clamping at `encode_record`, the single place records are made, so the
invariant lives with the format rather than in three readers defending against
input their own format forbids. Two tests, proven red against the shipped code.

**D-SINK-1 (P3).** `Model.redactUrls`'s userinfo group could not span a second
`@` while its host group accepted one, so a password containing an un-encoded
`@` kept its TAIL in the host position -- and that string reached a desktop
notification through `raiseStreamFailure`. The helper's python implementation
was correct, because it hands the match to `urllib` rather than a regex.

The deeper fix is the test. The two implementations of one rule were pinned by
two DISJOINT hand-written vector lists, and every vector in both carried
exactly one `@`, so the defect was invisible to both suites at once. CLAUDE.md
says one rule implemented twice gets ONE fixture;
`tests/fixtures/redaction-vectors.json` now exists and both suites run it. It
pins the PROPERTY -- the host survives, no credential fragment does -- not the
formatting, which differs on purpose (the helper emits `scheme://host`, Model
emits the bare host).

**D-SINK-2 (P3).** mpv's own `--list-options` says `--script` is "alias for
--scripts-append". The reserved set named the alias, so the real option was
open, along with `--scripts-add` and `--include`. Demonstrated against real mpv
0.41 headless: a Lua script loaded through `--scripts-append` read `path` --
the credentialed stream URL -- and wrote it to its own file, and `--include`
pointing at a one-line config containing `log-file=` produced a 20 KB log
carrying the stream address three times.

The helper already DEFINED the normaliser that would have caught this,
`mpv_option_base`, fifteen lines below the filter that ignored it. Both mirrors
now match on the base option name, so naming a list option once covers every
spelling.

Worth recording: fixing this, `--script-opts` was also reserved, and **the
suite caught it** -- ruling PO-10 keeps it a handoff option that warns rather
than a rejected one. The parity test a lane had called "two copies of the same
wrong list" could not catch the original omission, but it did catch an
incorrect addition, which is more than it was credited with.

### Fixed after the hunt, once the instrument was fixed first

**F-MPV-1, then D-PLY-12 and D-PLY-13.** The order was forced: D-PLY-12's
triggering input could not be written down until the double stopped being more
forgiving than real mpv.

F-MPV-1 is narrower than it was filed. Only `STUB_MPV` was wrong; `FakeMpv`'s
`inject` already broadcast to every connection and its `loadfile` emits no
events at all, so it was never mis-delivering anything. Two things were needed:
the stub now broadcasts events to every client while keeping command REPLIES
point-to-point, and it emits `end-file reason="stop"` for the previous entry on
a `loadfile ... replace`, which it did not before. Without the second half a
zap still looked like nothing had ended.

Both player defects then turned out to be the same four lines.
`observe_first_load` was asking `ended_verdict` -- the POST-MORTEM reducer --
about a connection that is still open. Two of its answers mean something
different while live:

- `reason="stop"` after the fact can only mean "a load we issued was replaced
  AND THEN the process died", so the reducer calls it failed. Live, it means
  another IPC client replaced our entry: a zap. **D-PLY-12.**
- `reason="redirect"` is already classified non-terminal, but the site returned
  on any end-file for its own entry, so the watch ended while an .m3u8 master
  was still resolving -- and the resolved stream's failure, the very thing the
  watch exists for, was never seen. **D-PLY-13.**

Both tests were proven red against the shipped code by removing the live/
post-mortem distinction, which turns exactly those two red and nothing else.

### Filed, not yet fixed

**D-PLY-12 (P2).** A zap inside the first-load window reports the channel you
just LEFT as a failed stream. Real mpv broadcasts to every IPC client, so
`player start`'s observer receives `end-file reason="stop"` for its own entry
id when the zap replaces it, and `observe_first_load` hands that live
mid-stream event to the POST-MORTEM reducer, which reads "stop" as "a load we
issued was replaced AND THEN THE PROCESS DIED".

**F-MPV-1 (P3)** is why D-PLY-12 was never found: both mpv test doubles deliver
a loadfile's events only to the connection that issued them, where real mpv
broadcasts. That is CLAUDE.md rule 10 exactly -- a double more forgiving than
the real thing -- and it makes D-PLY-12's triggering input inexpressible in the
suite. Fix F-MPV-1 first; D-PLY-12's fix is untestable until it is.

**D-ID-4 (P3), reproduced and pinned rather than fixed.** Run through the
shipping functions:

| step | favourites on disk | Favorites shows |
|---|---|---|
| star "Sports One" while the big list is active | `["u:4bc351f3"]` | Sports One |
| open the filtered list (remap moves 1) | `["n:ceb9a086"]` | Sports One |
| go back to the big list | `["n:ceb9a086"]` | **nothing** |
| re-apply the big list (its remap moves 0) | `["n:ceb9a086"]` | **nothing** |

`u:` is fnv1a32 of the STREAM URL, so two lists from one provider share that id
space exactly; whether a row is keyed `u:` or `n:` depends on whether its NAME
is unique IN THAT LIST. One channel therefore has two ids, and favourites are
global (D14). `channelIdRemap`'s idempotence argument is sound within one list
and silent about two.

**Why the obvious fix is wrong, which is the part worth keeping.** Matching a
favourite against any of a channel's alias ids does not work. Once the remap
has rewritten the favourite to the name key, the URL that told the HD/SD twins
apart is GONE FROM STATE, so a tolerant matcher accepts BOTH twins and one star
renders as two rows. That is demonstrated and pinned as a check. The fix cannot
be a matching change: the state has to stop discarding what distinguishes them,
which is a schema change and the owner's call. It was not made here, at the end
of a long session, in the area that has already produced D-ID-1, D-ID-2 and
D-ID-3 -- the last of which shipped a changelog claim that was false twice.

Its verifier also corrected the lane on two points now on the board: nothing is
DELETED (the favourite is relocated and still shows on the other source), and
the same move is made by the helper's `remap_state_file`, not only by
`Service.adoptIdScheme`, so any fix lands in both.

**Measured before ruling on it.** The id scheme only reaches `u:`/`n:` when a
row's tvg-id is absent or duplicated. On the maintainer's own cached list --
1471 channels -- all 1471 tvg-ids are present and DISTINCT, so the shipping
`channelIds` assigns `t:` to every row and `channelIdRemap` returns an empty
map. This defect cannot occur on that list at all. It needs a playlist without
unique tvg-ids, AND two sources from one provider, AND a name whose uniqueness
differs between the two lists.

Ruled 2026-09-22: **accepted**, to be fixed when channel identity is next
opened deliberately, with a README caveat in the Sources section meanwhile.
The fix, recorded so it is not re-derived: stop storing ONE key. A favourite
should carry the name-key AND the url-key, matching url-key first (it tells
HD/SD twins apart) and falling back to the name-key (it survives a credential
rotation). There is no single list-independent key -- url-derived ids break on
rotation, name-derived ids break on duplicates, and choosing between them by
LIST-LOCAL uniqueness is the entire cause.

**D-SINK-3 (P3)** is a documentation defect, not a new leak, and its verifier
corrected the hunter for implying otherwise: argv exposure is a knowingly
accepted residual named at `docs/ARCHITECTURE.md:259-264`. What is genuinely
wrong is that rule 5's sink list omits argv while instructing the reader to add
sinks to it, and that the README tells the user to set a credentialed URL with
`omarchy bar set`, which puts it in their shell history DURABLY -- a worse
exposure than the one the architecture accepted.

### Refuted, and deliberately not filed

A lane reported as P3 that a `state.json` the shell cannot read is treated as
absent and then overwritten empty, losing favourites. Its verifier showed this
is the specified tolerant-reader contract, that it was specified before it was
built, and that two existing test cases already grade it PASS at the sink. The
hunter's own status line conceded the trigger was unmeasured. It is not a
defect and it is not on the board.

### What held

Recorded because it is as useful as a finding. Redaction held on every other
sink the helper reaches. The 200 MB playlist is refused in 161 ms before any
read; a billion-laughs XMLTV is refused by expat's amplification limit. Rule 7
is met with headroom: three 10,000-channel runs at 546, 628 and 567 ms against
a 1 s budget. Rule 6 held -- 0700 directories, 0600 files, no temp residue
after success or after a mid-parse failure. Forty concurrent `state` writers
produced a valid 0600 single-line document with no corruption, only a lost
update. Cache path safety held: the source key is validated before it becomes a
path component, and neither `remove_regular` nor `cache_prune` follows a
symlink.

## Recalibration 2026-09-22: the longest-string ruling, applied

Five themes attempted, four measured, under headless cage. Per theme the
harness was pointed at its palette through a scratch `HOME`, the list filtered
to the two channels containing "Channel" so the fixture's 89-character name is
row 1, and the same row measured twice -- once under the cursor and once with
the cursor moved off it. One string, both surfaces, every theme.

### What it showed

All 16 text rows land inside the text class's 0.15 absolute:

| Theme | cursor name | cursor detail | card name | card detail |
|---|---|---|---|---|
| catppuccin | -0.062 | -0.129 | -0.041 | **-0.136** |
| rose-pine | **+0.009** | -0.059 | -0.034 | -0.074 |
| tokyo-night | -0.017 | -0.091 | -0.026 | -0.107 |
| catppuccin-latte | -0.030 | -0.058 | -0.033 | -0.078 |

Worst 0.1359. Every `knownDeviation` pin is gone and the fixture now asserts
that none remains. For comparison, the same catppuccin card name measured
-0.208 on "BBC One HD" and -0.304 on "Harness Live": the ruling is doing real
work, not relabelling.

### Two things it turned up

**retropc could not be re-measured, and its rows stand unverified.**
`~/.config/omarchy/themes/retropc` ships `alacritty.toml`, `btop.theme`,
`waybar.css` and the rest, but **no `colors.toml`** -- nothing the shell reads.
Pointed at it, the shell falls back to `#cacccc` on `#101315` and renders a
palette that is not retropc at all. The attempt produced those fallback values,
which were discarded rather than written down as retropc. The `/usr/share`
themes carry `colors.toml`, which is why the other four worked.

**The optimism invariant broke, honestly.** rose-pine's cursor name measures
**5.9471** against a model of **5.9384** -- 0.0087 ABOVE it. With a long string
the coverage bias nearly vanishes, and what remains is the model's one-unit
rounding in the composite step, which rounds either way: Qt paints that fill
`#ede8e4` where `colorOver` computes `#ede7e4`.

The invariant was **restated, not widened**. It now asserts two things: no
sample may exceed its model by more than 0.05 (the measured rounding bound,
observed on four surfaces across two passes), and the mean error must stay
negative so the model is still optimistic overall. Both are stricter than the
single check they replace -- a genuine sign flip now trips four checks instead
of one, proven by mutation.

The load-bearing consequence is unchanged and in fact stronger: a contrast
target must sit above the line and never on it, because the error is now known
to be a BAND around the model rather than a one-sided bias.

## Headless pass 2026-09-21, segment C: the two captures 0.7.3 was owed

Run entirely inside a nested headless `cage` compositor with the dev harness in
`--window floating` mode. **Nothing on the user's session was touched**: no
theme change, no shell restart, no keystroke into the live display, no window
of the user's in any frame. Proven on exit -- `shell.json`, the state directory,
the cache and `theme.name` all hash-identical to the 22:15 snapshot, the live
`quickshell` still pid 1152526 (never restarted), the installed plugin still at
53ad47e. The light-theme capture used a scratch `HOME` whose
`.local/state/omarchy/current/theme` symlinks to rose-pine, because
`Color.qml:17` derives the theme path from `$HOME` and not from
`XDG_STATE_HOME`; the user's own theme stayed catppuccin throughout.

### 1. D-RUNG-14: the bold captions, measured on our own sites

Model for catppuccin at the 0.7 rung on the card: **6.2384**.

| Site | measured | error |
|---|---|---|
| group entry count | 6.2377 | **-0.0007** |
| footer status line | 6.2377 | **-0.0007** |
| UK-ENTERTAINMENT count | 6.1841 | -0.0543 |
| Sources pinned count | 6.1841 | -0.0543 |
| *the same sites at REGULAR weight, 2026-09-21 earlier* | *5.45* | *-0.79* |

The `bold-caption` class had zero rows of ours and now has four. The
UNVERIFIED mark on UX.md 5.4 is lifted.

One site is recorded but deliberately NOT added as a fixture row: the footer
hints measured **6.2594**, which is 0.021 ABOVE the model and would break the
fixture's "the model is optimistic in every sample" invariant. It is not a
0.7 opacity rung -- it is dimmed by `<font color>` inside `StyledText`
(`verbColor`, `Util.alpha(foreground, 0.7).toString()`), a different operation
from the scene-graph opacity every other row models. Modelling it as a 0.7 row
would assert something false.

### 2. The Sources cursor mark, on a non-active source

The state that had nothing: no bold label, no check glyph, and before this
change no mark.

| Theme | the mark | the fill alone, which was the only signal |
|---|---|---|
| catppuccin (dark) | `#cdd6f4`, the text token byte-exact, **9.3561** | **1.2122** against the card |
| rose-pine (light, the worst case of 23) | `#575279` byte-exact, **5.9772** | **1.1138** against the card |

WCAG 1.4.11 asks 3:1 of a state indicator. The fill was under it on both; the
mark clears it by a factor of two at its worst theme. The label is the text
token on both, so the ruling is in effect on screen.

### 3. F-CAL-2, resolved: it was never the surface

The hypothesis was that text loses more on the cursor fill than on the card.
Measured with the SAME STRING on both surfaces for the first time, by moving
the cursor one row between two frames:

| String | on the card | on the fill | difference |
|---|---|---|---|
| BBC One HD | 11.1336 (model 11.3411, **-0.2075**) | 9.1849 (model 9.3840, **-0.1991**) | **0.008** |
| Harness Live | 11.0372 (**-0.3039**) | 9.1130 (**-0.2710**) | 0.033 |

There is no surface effect. The error tracks the **string**. Eight 14 px names
on one surface, one theme, one model value of 11.3411:

`Sky Sports Main Event` 11.3001 | `Sky Sports Football` 11.3001 | `Sky News`
11.3001 | `GB News` 11.2538 | `BBC One HD` 11.1336 | `BBC News` 11.0820 |
`Harness Live` 11.0372 | `ITV1 HD` 11.0372

A spread of **0.041 to 0.304** at one size, one surface, one theme. The
peak-pixel method under-reads until some pixel is fully covered, and a longer
string reaches that sooner. That one mechanism explains the whole of F-CAL-1's
"size dependence" too: bold and glyphs have thick strokes and reach the token;
10 px regular has the thinnest strokes and falls 11 to 13 per cent short.

**And the model itself is exact.** Its only arithmetic error is a one-unit
rounding in the composite: rose-pine's fill computes to `#ede7e4` (236.96,
231.04, 227.72) where Qt paints `#ede8e4`; catppuccin's `#2c2d3e` matches
byte-for-byte. Given the fill Qt really paints, the mark measured 5.9772 and
9.3561 where the model says 5.9772 and 9.3561 -- equal to four decimals.

So what is left open is a ruling about the METHOD, not the arithmetic: record
the string on every calibration row, always measure the longest available
string, or widen the text class. A card row misses the 0.15 text tolerance
exactly as a cursor row does, and both are now in the fixture, pinned, to show
it.

### 4. Harness notes

- F-HARNESS-1 reproduced: the first keystroke after the window maps is
  dropped. Every move in this pass was therefore sent in a bounded retry that
  verified the result from the pixels before continuing, and reported giving up.
- The guide opens in **search** mode (`Model.guideState` defaults there), so a
  printable key types rather than acting. `run.sh ipc mode` (`switchMode`)
  reaches list mode deterministically; `o` only then opens Sources.
- `cage` must be stopped by killing its CHILD, and the child must trap TERM:
  bash defers a signal while a foreground `sleep` runs, so the first teardown
  left cage alive and a stale `wayland-0` behind.

## Headless pass 2026-09-21, segment D: the three rows that were "blocked on a screen"

Same recipe as segment C, same proof of non-interference: `shell.json`, the
state directory, the cache and `theme.name` hash-identical to the snapshot, the
live shell still pid 1152526 and never restarted, the plugin still 53ad47e,
theme still catppuccin. Three board rows carried the words "never rendered" or
"blocked"; the harness renders all three.

### 1. D-RUNG-10, the EPG progress hairline -- rendered for the first time

`run.sh --fake-epg` supplies the EPG rows this install's own data cannot: its
`epgUrl` is empty and 0 of 1471 channels carry a number. The hairline draws at
y=446-447, 2 px tall, as a track with a filled portion inside it.

| Surface | filled | track | measured | model | error |
|---|---|---|---|---|---|
| ordinary row | `#627aa8` | `#333445` | **2.8340** | 2.8468 | -0.013 |
| cursor row | `#7392c8` | `#404253` | **3.1451** | 3.1677 | -0.023 |

The ordinary row is **under** the 3:1 bar of WCAG 1.4.11; the cursor row clears
it. With the model validated to 0.013 and 0.023 on this surface, its 23-theme
figures can be trusted -- and they are WORSE than the board recorded, because
the board's "15 of 23, floor 1.7980" is the CURSOR variant:

- **ordinary row: 19 of 23 under 3:1, floor rose-pine 1.6551**
- cursor row: 15 of 23 under 3:1, floor rose-pine 1.7980
- worst five ordinary: rose-pine 1.66, miasma 1.85, white 1.95,
  catppuccin-latte 2.02, lupine 2.04

D-RUNG-10 is no longer an evidence gap. It is a product decision.

### 2. D-RUNG-11, the 28 px empty-state glyph -- model byte-exact

Rendered by querying a string that matches nothing. The glyph draws `#7496d1`
where the model computes `#7496d1` -- byte-exact -- measuring **5.4874**
against a model of 5.4846, an error of +0.003. The glyph class is exact, so the
row's "2 of 23 under 3:1" (rose-pine 2.42, miasma 2.97) stands without needing
a capture of either failing theme.

On the same frame, consistent with the stroke-coverage mechanism of segment C:
the 14 px title measured -0.074 and the 12 px prose -0.256 against the same
model value of 6.2384.

### 1b. D-RUNG-10's fix, verified on screen the same day

The re-ink was measured before it was called fixed. Same headless recipe,
catppuccin, ordinary row:

| | filled | track | ratio |
|---|---|---|---|
| before (accent @0.55) | `#627aa8` | `#333445` | **2.8340** -- under the 3:1 bar |
| after (text token @0.73) | `#a4aac5` | `#333445` | **5.3174** -- clears it by 77 per cent |

Model for the fix: `#a3aac5`, 5.3120. Error +0.005, with the same one-unit
composite rounding seen on every other surface. The machine was hash-identical
before and after, the live shell never restarted.

### 2b. D-RUNG-12, the dimmed channel number -- and a warning about the method

From the same `--order number` frame. Non-cursor numbers at the 0.52 rung on
catppuccin measured **4.0245** ("7.1") and **3.8348** ("300") against a model
of 4.0728 -- both under 4.5:1, confirming the defect on screen.

The cursor-row number at full opacity measured 7.8080 against a model of
9.3840, and that sample is **discarded rather than reported as an error**. Its
string is the single digit "7", and its peak pixel came back `#b9c9b9` -- a
green-tinted colour lying on no path between the text token `#cdd6f4` and the
fill `#2c2d3e`. That is the signature of subpixel antialiasing fringing, not of
ink. A one-glyph sample can put the peak-pixel method on a fringe pixel and
produce a number that means nothing, which is the sharpest argument yet for the
ruling that calibration samples the LONGEST available string.

### 3. The composite rounding, now seen four times

Every surface measured across segments C and D shows the model's only
arithmetic error to be a one-unit rounding in the composite step:

| Surface | model | Qt paints |
|---|---|---|
| rose-pine cursor fill | `#ede7e4` | `#ede8e4` |
| catppuccin cursor fill | `#2c2d3e` | `#2c2d3e` (match) |
| hairline track | `#333446` | `#333445` |
| hairline fill | `#627aa9` | `#627aa8` |

Worth at most 0.039 ratio points. Given the colour Qt actually paints, every
measurement in both segments equals the model to within the stroke-coverage
bias and nothing else.

### 4. F-CAL-2's method, ruled

The product owner ruled: **measure the longest available string at each site,
and record the string on the row.** The text class keeps its 0.15 absolute and
the pins come off as rows are re-measured under that rule. The fixture note
carries it. Rows that carry a `site` but were measured before the ruling are
owed a re-measure; that is a fixture-wide sweep of its own, one harness run per
theme, and it is not done here.

## Live pass 2026-09-21, segment B: PiP on the real compositor, and the harness on the real display

Owner: QA (display lane, segment B). Machine: the user's live session, WAYLAND_DISPLAY
wayland-1, Hyprland 0.56.2, one monitor eDP-1 1366x768 scale 1 transform 0 reserved
[0, 26, 0, 0], theme Catppuccin throughout (no theme switch was needed in this
segment). Installed plugin 0.7.2 (main 53ad47e) for part 1; the dev tree (branch
dev, this checkout) for part 2. Evidence root: /tmp/claude-1000/live-B/ (logs/,
shots/ crops only, snapshot/; two crops were removed and the window-title fields
of the clients dumps stripped after the audit, for privacy, see section 3). The
user was not at the machine; the user's two
windows (com.anthropic.Claude 0x5d8ed65f0d70 pid 3789 on workspace 1, chromium
0x5d8ed66ef2b0 pid 21260 on workspace 2) were present before and after. Nothing
left the machine: the stream, the playlist and every fixture were served from
127.0.0.1:8765 or read from a local path. The sg1 and gs2 fixture copies, like
the repo's single-group.m3u, carry no url-tvg; the harness.m3u copies keep the
template's url-tvg, which points at 127.0.0.1 port 9 (nothing listens there), so
no .test host was ever resolved.

Protocol as run. Snapshot first (shell.json sha256 af7ef4195973f031..., state.json
79bd045f401bed91..., cache tree, theme, hyprctl clients and monitors); every
keystroke gated on `pgrep -x hyprlock` empty AND the guide's own layer surface
(namespace omarchy-iptv) mapped per `hyprctl -j layers` (the host has no
`isPluginOpen` IPC verb and `status` carries no opened flag, so the compositor
was the witness); every wait bounded; every kill by recorded pid; captures taken
with `grim -g <geometry>` so no full frame was ever written (the card at
203,74 960x620, the PiP corner, the bar). One correction to the protocol as
written: a bash trap cannot outlive one tool invocation, so each phase script
installed an EXIT trap that runs a standalone restore script unless the phase
reached its end marker, and the same script was run explicitly at the end.

### 1. Picture in picture on the installed plugin against real Hyprland (D-PIP-4/5/6, live half)

Local stream: tests/fixtures/qa-player/test.ts (MPEG-TS, h264+aac, 120 s) and a
copy of scripts/dev-harness/fixtures/harness.m3u.in with the live slot pointed at
http://127.0.0.1:8765/test.ts, served by `python3 -m http.server 8765 --bind
127.0.0.1` from scratch. The playlist was added to the LIVE plugin as a source
through the plugin's own helper, `omarchy-iptv state source add --url ... --label
"QA local" --origin cli` (key 7dc750f0); the running service picked the record up
through its state FileView within 2 s (status listed it as never loaded). The
switch was made on the Sources screen (`Tab`, `o`, `j`, `Enter`): active
7dc750f0, status ready, 20 channels, 200 ms after Enter. The guide was hidden
over IPC before playback. `play http://127.0.0.1:8765/test.ts` resolved the
channel by URL: player up and attached 300 ms later, nowPlaying `Harness Live`
(chno 300), one client of class omarchy-iptv (pid 1152118) tiled at [690, 38]
size [650, 718] on workspace 1 next to the Claude window.

Predicted box, computed by `node` against the INSTALLED Model.js with the
monitor record from `hyprctl -j monitors` and the plugin defaults `pipOptions`
returns for an entry with no pip keys (top-right, 30 per cent, 16 px margin):
`{x: 940, y: 42, w: 410, h: 230}`.

| Step | Command | Reply / settle | mpv client record after | Foreign records |
|---|---|---|---|---|
| pip on | `pip toggle` | `{"ok":true,"kind":"pip","requested":"toggle","was":false,"state":"applying"}`; status pip.on true, applying false after 359 ms | at [940, 42] size [410, 230] floating true pinned true tags default-opacity*, iptv-pip; equals the prediction on all four numbers | Chromium: identical, all 32 fields. Claude: at/size changed [25, 38] [651, 718] -> [12, 38] [1342, 718], which is the tiling layout re-filling workspace 1 when the mpv window left it (PIP-02 "the other windows retile"); no other field changed |
| pip off | `pip toggle` | `was:true`, settled in 244 ms | at [690, 38] size [650, 718] floating false pinned false, tag gone: identical to the record before PiP | Chromium identical; Claude identical to its pre-PiP record (all 32 fields) |
| pip on again | `pip toggle` | settled in about 300 ms | as row 1, all fields identical to row 1 | both identical to row 1 |
| shell restart with PiP on | `omarchy restart shell` (the one authorized restart) | rc 0 in 1495 ms; `shell ping` ok 2.8 s after the command; quickshell pid 1058 -> 1152526 | FIRST status sample after ping, 4925 ms after the restart command: pip.available true, pip.on true, applying false, reason "", player up true attached true. The client record is identical to the pre-restart one in all 32 fields: the window was not touched (D-PIP-4) | both identical, all 32 fields |
| pip off after restart | `pip off` | `was:true`, settled in about 480 ms | at [690, 38] size [650, 718] floating false pinned false: restored | Chromium identical; Claude retiled to [25, 38] [651, 718] as before |
| stop | `stop` | ok; no omarchy-iptv client 300 ms later; `pgrep -x mpv` empty | - | both identical to the records taken before playback (all 32 fields) |

Verdicts. D-PIP-4 (state after a shell restart): PASS on the real compositor,
the new shell derived pip.on true from the readback within its first status
sample and the window was untouched. Evidence: logs/phase1.log
16:12:40-16:12:45, logs/clients-04-pip-on-2.json against
logs/clients-05-after-restart.json, shots/p1-pip-region.png (the exact 940,42
410x230 box) and shots/p1-bar-after-restart.png; the wider after-restart corner
crop was removed for privacy (section 3). D-PIP-5 (foreign windows): PASS with
two real strangers. The Chromium record is identical in all 32 fields across the
five PiP transitions (01->02, 02->03, 03->04, 04->05, 05->06) and in the 00 vs
07 comparison; its focusHistoryID changed at play (00->01, 1 -> 2) and at stop
(06->07, 2 -> 1), as did the Claude record's (0 -> 1, 1 -> 0), which is focus
history moving when a window appears and disappears, not PiP. The Claude record
changed at/size on every retile step, 00->01, 01->02, 02->03, 03->04, 05->06 and
06->07 (the tiling layout re-filling workspace 1 as the mpv window entered or
left it, floated or unfloated), and on nothing else; 04->05, the restart with
mpv floating, changed no field of either record. D-PIP-6 (the geometry, ordering and readback assertions
asserting about a real pid): the service learned the player pid from the player
(status player.attached true, client pid 1152118) and every geometry above is a
readback, not a plan. The window rendered translucent as D-PIP-3 says it does
(unchanged, open on its own terms). Note for the restore proof: the authorized
restart replaced quickshell pid 1058 with 1152526; "no quickshell but 1058"
cannot hold after that step by construction, and the proof below shows exactly
one quickshell, the one the restart started.

### 2. The dev harness on the real display (a second quickshell from the dev tree)

`OMARCHY_IPTV_HARNESS_DIR=/tmp/claude-1000/live-B/harness scripts/dev-harness/run.sh
--open --fake-epg --detach --timeout 0`, window mode `layer` (the production
PanelWindow path), pid 1154435, the installed guide closed throughout.

(a) Mapping and focus. `hyprctl -j layers` 2.6 s after start (16:13:57.165 ->
16:13:59.758): `omarchy-iptv`
0,0 1366x768 at level 3 (Overlay) owned by pid 1154435, plus the harness's fake
bar `omarchy-iptv-harness` 0,0 1366x26 at level 2 (it overlaps the real
omarchy-bar surface at the same geometry while the harness runs; cosmetic,
harness-only). `hyprctl -j activewindow` stayed com.anthropic.Claude before and
after typing, and no character reached it: the FIRST keystrokes on the fresh
shell, one `wtype sky` call, read back over `ipc state` as query `sky`, 3 rows
of 20. A second sample after `ipc query ""`, typed key by key, read back `bbc`.
F-HARNESS-1 (first keystroke lost) did NOT reproduce under real layer-shell
exclusive keyboard focus: 1 of 1 fresh shell arrived whole. That is one sample;
the floating-window mode where it was seen was not run here.

(b) D-CHNO-6. Every `Cannot anchor` line in the harness log is the same
message, `QML MouseArea at Guide.qml[2730:19]: Cannot anchor to an item that
isn't a parent or sibling`. The log survives at
/tmp/claude-1000/live-B/harness/harness.log (361 lines, 341 of them this
warning; `run.sh clean` removes cache, state, runtime and shots, not the log).
The counts on file, all in logs/phase2.log: 47 lines after the open and the
`sky` and `bbc` samples (3 rows in the model); 60 after clearing the query to
the 20-row list (+13); 76 after the SG1 switch, a 50-row list (+16, not 50);
+27, +23 and +18 for the queries `st`, `sta` and `unit` typed key by key (11, 7
and 2 rows); 287 at the end of phase 2b; 341 at the end of the session. The
reading that it fires once per row DELEGATE INSTANTIATED and not on delegate
reuse is consistent with those numbers (a 50-row render adding 16, about the
visible rows plus the cacheBuffer) but is not proven by them; an earlier draft's
per-query series on the 60-row list is in no file and is withdrawn. The only
other warning in the log is Qt's portal app-id registration
notice, once.

(c) D-SG-1 display residue. Source: a copy of tests/fixtures/qa-sg1/single-group.m3u
(50 rows, one group "United States") added over `ipc addSource` and switched
to by the probe (SG1, ready, 50). Queries typed with wtype; strings read over
`ipc state` and checked against the card crops (shots/sg1-*.png):

| Query | Header (top right) | Rows | Footer (bottom left) | Empty state |
|---|---|---|---|---|
| (empty) | `All - 1 of 50` | 50 | `SG1 - 50 channels - updated 16:15` | - |
| `st` | `in All - 11 matches` | 11: STATE TV, STATE NEWS NETWORK, STARZ KIDS AND FAMILY, USA STARZ, USA STARZ ENCORE WESTERNS, USA STARZ ENCORE ACTION, USA STARZ EDGE, FIRST LOOK TV, HISTORY, TASTEMADE, PLUTO TV WESTERNS | same | - |
| `sta` | `in All - 7 matches` | 7 | same | - |
| `unit` | `in All - 2 matches` | 2, cursor on UNITED SPORTS | same | - |
| `united stat` | `in All - 0 matches` | 0, emptyKind noMatches | same | icon, then `No matches for "united stat"`, then the hint `Keep typing for United States - Esc clears the search` |

On screen the separator in every header, footer and hint string is U+00B7
(middle dot) and the query in the empty state is wrapped in U+201C/U+201D; both
are written as `-` and `"` here for the ASCII rule, everything else verbatim.
The footer hint line in search mode with a query reads `Enter play - Up/Down
move - Left/Right narrow - Tab keys - Esc clear`, and `... Left/Right scope ...
Esc close` with the query empty. The counts are the fixture's own expected
numbers (11, 7, 2), so the shipping whole-word rule is what the screen shows.
No `First 200 of 3,335 - keep typing` shape can appear on a 50-row list; the
3,335-row shape remains a terminal-only measurement.

(d) D-GS-2 display residue. Source: a generated 60-row one-group list with a
tvg-id on every row (the shape tests/fixtures/qa-gs2/README.md describes; the
committed 8-row file is too short to overflow the card), added over `ipc
addSource`, list mode, cursor at row 0. Pixel method: the cursor row's highlight
band in the card crop (modal colour per pixel row across the list column differs
from the card background) gives the row height directly, and its top edge after
`ipc move 1` gives the pitch; ink runs in the name column count the text lines.

| EPG state | rowsHaveDetail | highlight band | band top at cursor 0 -> 1 | pitch | rows fully visible |
|---|---|---|---|---|---|
| fake EPG disjoint (the harness's ids are bbc1.uk etc., no ch0000N.test entry) | false | 38 px tall | 60 -> 102 | 42 px (38 + 4 spacing) | 12 (text lines at 70, 112, ..., 532) |
| matching epg-now.json written into the source's cache dir (60 entries with now and next titles) | true, after a guide close and reopen | 52 px tall | 60 -> 116 | 56 px (52 + 4) | 9 (name 14 px + detail 10 px + 2 px progress bar per row) |

So the screen shows 38 versus 52 px rows and 12 versus 9 visible rows, the
numbers D-GS-2 was filed on, and the disjoint guide leaves every row single-line
(the fix). One observation for the row, not a defect against it: `epgCarriesRows`
is measured, not bound (Guide.qml:446, by design), so an epg-now.json that lands
while the guide is open does not re-skin the rows until the next open; the
matching file had been loaded by the service (status epg.loaded true by
16:16:15) about 90 s before the guide re-measured on reopen at 16:17:45 (the
15 s in the log is the bound of the wait_for that gave up on rowsHaveDetail
while the guide stayed open). Removing the file and reopening returned to 38 px.

(e) chno-entry-scenario.sh N15 / N21 / N24. The scenario's header keeps all three
live-only and exposes no way to run them: N15 needs real key events, N21 a
window resize the overlay cannot take over IPC, N24 a theme re-skin. The keypad
half of N15 was run by hand on the harness: list mode, `wtype -k KP_1 -k KP_0
-k KP_1`, `ipc numberState` answered buffer `101`, hasNumbers true, transient
`Channel 101 - BBC One HD`, cursor on BBC One HD (chno 101). The shifted half
cannot be produced on this keyboard: the active keymap is English (US), where
Shift+1 is `!` by design; the AZERTY case stays unrun. N21 and N24 were not
attempted (N24 would have needed a theme switch this segment did not otherwise
need, and the user's other windows would have been re-skinned with it).

Teardown: the harness shell was stopped by its recorded pid (exited within 100
ms of SIGTERM), `run.sh clean` wiped the scratch cache, state, runtime and
shots (the harness log at /tmp/claude-1000/live-B/harness/harness.log survives
it),
`hyprctl -j layers` then listed only the real omarchy-background and omarchy-bar
surfaces, both owned by the restarted shell.

### 3. Restore proof

All checks taken at 16:21:35-16:22:18 after the restore script (shell.json first,
a 3 s settle, then state.json with a re-check, then the cache), by the same reads
the snapshot used.

| Item | Snapshot | End state |
|---|---|---|
| ~/.config/omarchy/shell.json sha256 | af7ef4195973f0316f648329dba76acdc9ed5e74f63b46ffdae6c70a51646562 | identical; mode 600 |
| ~/.local/state/omarchy-iptv/state.json sha256 | 79bd045f401bed91bb0b9f2050cf11f0c7c2074deaa65d31ecffc6990fd7102e | identical, re-checked 45 s later still identical; mode 600 |
| ~/.cache/omarchy-iptv | tree copied | `diff -rq` clean; every mode under cache and state identical to the snapshot listing; the temporary source's cache dir 7dc750f0 was removed by the plugin's own `x` (confirm) before the copy |
| theme | Catppuccin | Catppuccin (never switched in this segment) |
| guide | closed | closed: `hyprctl -j layers` lists only omarchy-background (level 0) and omarchy-bar (level 2), both pid 1152526 |
| mpv | none | none (`pgrep -x mpv` empty) |
| quickshell | pid 1058 | exactly one, pid 1152526: the shell `omarchy restart shell` started in step 1 (the authorized restart necessarily replaced 1058) |
| http.server | none | none, port 8765 has no listener (see the slip below) |
| cage | none | none |
| hyprlock | none | none at every gate |
| full-frame captures | - | zero written at any point (every capture was `grim -g` of the card, the PiP corner or the bar); 31 crops were written under /tmp/claude-1000/live-B/shots, none committed, and 29 are kept: two, p1-pip-after-restart.png and p1-pip-region-wide.png (466x270 at 900,26, whose 40 px left margin lay over the user's Claude window and, in the first, showed readable text fragments), were removed for privacy after the audit; p1-pip-region.png, the exact 940,42 410x230 PiP box, is kept. The eight logs/clients-*.json dumps and snapshot/clients.before.json had their title and initialTitle fields stripped for the same reason (a browser tab title carried the user's mail address) |
| user windows | com.anthropic.Claude 0x5d8ed65f0d70 pid 3789, chromium 0x5d8ed66ef2b0 pid 21260 | both present, both tiled at [12, 38] size [1342, 718] on their workspaces, as at the start |
| installed plugin dir | 53ad47e, clean | 53ad47e, `git status --porcelain` empty |
| plugin status | iptv-org.github.io, ready, 1471, one source | the same: one source d5977d8a, playing false, pip off |

A slip the proof caught, and fixed before the end: the fixture server was
started as `setsid python3 -m http.server ... &` and its pid recorded from `$!`;
setsid forked, so the recorded pid (1146775) was the wrapper and the server
itself ran as 1146777. The restore script's kill-by-pid therefore hit nothing at
16:11, and the second server started afterwards failed with `Address already in
use` (its log says so) while the original kept serving; the final proof found
the listener by `ss -ltnp`, matched its cwd and command line to this segment's
scratch directory, and killed it by that pid (exited at once; 0 listeners on
8765 afterwards). Rule for the next pass: record a detached server's pid from
the listener (`ss -ltnp`) or start it without setsid, never from `$!` behind
setsid.

### 4. Defects and observations to file

- OBS-B1 (protocol, restore ordering): restoring state.json by file copy while
  the shell runs is undone if shell.json is restored AFTER it: the playlistUrl
  change makes the service touch the source record and save its in-memory state
  over the copy (seen once at 16:11: the re-read state.json no longer matched
  the snapshot's sha; the value read then was recorded only in the transcript,
  not in any log, so it is not cited here). Restore shell.json first, let the switch settle, then state.json,
  then re-check the sha. The restore script used from then on does exactly that.
- OBS-B2 (harness, cosmetic): in layer mode the harness maps its fake bar as a
  real layer surface `omarchy-iptv-harness` at level 2 over the real bar's
  geometry for the life of the run.
- D-CHNO-6 stands, on the real layer surface: 341 of the warning by the end of
  the session, +16 for a 50-row render and +13 for a 20-row one (section 2(b),
  file-backed); the per-delegate reading is consistent with those counts, not
  proven by them.
- OBS-B3 (protocol): `$!` behind `setsid` records the wrapper's pid, not the
  server's; see the restore proof. Kill by the listener's pid.
- OBS-B4 (Sources screen), downgraded after the audit: not a plugin defect on
  this evidence. The source added with `state source add --label "QA local"`
  showed its custom label before it was fetched (shots/p1-sources.png, 16:09),
  and shots/p1-sources-2.png (16:12:34, taken BEFORE the second switch) already
  shows the derived label `127.0.0.1:8765`, `used 16:11`, `not loaded yet`, so
  the probe-and-switch path is exonerated. The audit's real calls on the
  installed Model.js: `reconcileSources` on a known URL and `touchSource` both
  preserve label `QA local` and labelCustom true; a state restored from the
  snapshot (record absent) with the URL still arriving from settings recreates
  the record with the derived label and labelCustom false; and the helper's
  `add` refuses an existing URL as a duplicate and derives the label when
  --label is absent. The likeliest path is therefore the 16:11:09 external
  restore of state.json under a shell.json still pointing at the URL (OBS-B1);
  how 7dc750f0 was recreated between 16:11:10 and 16:12:34 is to be established
  from the transcript before anything is filed against the plugin.
- F-HARNESS-1 did not reproduce in layer mode (1 fresh shell); no change to the
  row, which is filed against the floating-window mode.

## F-CAL-3 fixed 2026-09-22: the fixture now says which screen it describes

Repo-only pass. The display was never touched: no capture, no theme change, no
keystroke, no shell restart. Every figure below was already measured -- this
change moves figures out of prose and into rows, and changes how the rows are
read. Nothing was re-measured, and nothing needed to be.

### Why neither option in the defect was taken on its own

F-CAL-3 offered two: re-measure everything live, or record the environment per
row and stop comparing across them. Each is wrong by itself.

**Re-measuring everything live destroys the evidence.** The cage rows are not
noise to be replaced. They are the only reason we know the divergence is glyph
rasterisation and not a broken model: the same four sites, same theme, same
build, read 6.2377 under cage and 5.4475 to 5.6956 live. Delete the cage half
and that becomes an unexplained live shortfall again -- which is precisely the
state that produced the withdrawn 1.25 claim years of this document ago.

**Recording the environment without changing how tolerance is DRAWN fixes
nothing.** A comment saying "these rows are cage" does not stop `bold-caption`
drawing the absolute tolerance on cage evidence and then being cited about the
user's screen. That is the whole defect, and it is a naming join, not a call
(CLAUDE.md rule 13).

So the fix is both, plus the part neither option named: the tolerance table is
keyed by the PAIR.

### What changed in the fixture

| | before | after |
|---|---|---|
| rows | 40 | 46 |
| rows stating their environment | 0 | 46 |
| tolerance keyed by | `sizeClass` | `(sizeClass, env)` |
| `bold-caption` live rows | 0 | 3 |
| control rows (solid rule, both environments) | 0 | 3 |
| optimism mean | one pooled -0.199 | live **-0.376**, cage **-0.048** |

The pooled mean is the clearest single symptom: **-0.199 described no rendering
that exists.** It was the average of a live population losing 0.376 and a cage
population losing 0.048, and it moved whenever rows were added to either side.

### The rows that were prose

The live bold measurements that refuted D-RUNG-14 lived only in a paragraph.
Three are now rows on catppuccin at the 0.7 rung: group count 5.4475, Sources
count 5.4590, footer status 5.6956.

The live footer hints (5.8559) is deliberately **not** a row, for the same
reason its cage twin was left out on 2026-09-21: it is dimmed by `<font color>`
inside `StyledText`, not by scene-graph opacity, so predicting it as a 0.7 row
would assert something false about how it is drawn. An exclusion that is right
under one environment is right under both; taking the live figure because it
happened to suit the argument would have been the same error in the other
direction.

### The control, which is the load-bearing part

The conclusion is not "cage differs somehow" -- it is "colour and compositing
agree, glyph coverage does not", and only the pair licenses the split. A solid
2 px rule at the text token has no partial coverage to lose:

| | live | cage |
|---|---|---|
| catppuccin cursor mark, 2 px solid rule | **9.3561** | **9.3561** |
| the four bold captions, same theme, same build | 5.4475 - 5.6956 | 6.1841 - 6.2377 |

Both halves are asserted. The control check returns the number of pairs it
compared alongside its result, so it cannot pass by comparing nothing --
deleting the live control row turns it red on the count, not silently green.

### The second finding, which is worse than the first

The live bold pass ran on **catppuccin**, whose 0.7 caption rung already
measured **5.45** -- above 4.5 before any change. It measured the one theme
that never failed.

| theme, 0.7 caption rung, live | regular | bold |
|---|---|---|
| rose-pine | 2.96 - 3.15 | never measured |
| tokyo-night | 4.12 - 4.30 | never measured |
| catppuccin | 5.45 - 5.70 | 5.4475 - 5.6956 |

So even a perfect measurement there proved nothing about the failing case.
**D-RUNG-14 is reopened.** The set of themes owed a live bold measurement is
derived from the fixture by a check, not written down, so it goes red the
moment one is taken.

### Proof the checks catch something (CLAUDE.md rule 11)

Six new checks, node **1464 -> 1470**. Run against the fixture exactly as it
shipped at `d4e0552`, **ten checks go red**, including all six new ones. Each
was also mutated individually:

| mutation | red |
|---|---|
| the fixture as it shipped | 10, incl. all 6 new |
| a row loses its `env` | 4 |
| a caption row claims an environment its class never had | 3 |
| the live bold rows removed -- the state D-RUNG-14 was certified in | 5 |
| the control diverges between environments | 2 |
| the control has nothing left to compare | 3 |
| pretend bold DID work live | 4 |
| someone measures tokyo-night live at bold | 3 |

The fixture was restored from backup after the battery and the suite verified
back to 1470 / 0.

### Corrections to earlier text

- F-CAL-3's own board row said the cage bold pass was 2026-09-22. It was
  **2026-09-21, segment C**. The fixture's dates were right and the prose was
  wrong, which is itself the argument for reading `env` and never the date --
  2026-09-21 ran a live segment *and* a cage segment.
- `docs/UX.md` 5.4 claimed bold "buys the shortfall back". Withdrawn.
- `docs/CONTRAST-RULING.md`'s calibrated-target derivation gains a clause: a
  target may not be set against rows from an environment the user does not
  have.
