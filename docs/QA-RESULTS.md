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
| TC-BAR-11 | pass | `Accessible.name: Model.barAccessibleName(...)` at BarWidget.qml:104 |
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
| TC-A11Y-01 | pass | `Guide.qml` 594-1214: Dialog `IPTV guide`, EditableText `Search channels`, List `Groups` / `Channels in <scope>`, ListItem via `Model.rowAccessibleName`, AlertMessage banner, StaticText footer; BarWidget Button |
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

Not re-run (first-pass result kept): TC-CFG-07/09/10/11, TC-BRW-02/19/23/24, TC-PLAY-13, TC-BAR-05/06/07/08/10/11/12, TC-FAV-11, TC-RFR-02, TC-A11Y-01/02/03, SEC-10, TC-MODEL-08.

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

Not re-run this pass (previous result kept): TC-CFG-03/07/09/10/11, TC-BRW-08/16/18/20, TC-PLAY-03/07/08/13, TC-BAR-10/11, TC-FAV-09/10, TC-RFR-02/10, TC-UI-08/12, TC-A11Y-01/02, SEC-03/09/10/11/19/20 (S-05 trickle and S-06 redirect mocks: helper unchanged), TC-MODEL-08, plus the mouse and live-shell cases listed in R8 (the live-shell block passed in the live section above).

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
| SRC-A11Y-01 | pass | `logs/static-greps.txt` A11Y-01: Heading, Button `sourcesRowAccessibleName`, List `accessibleSources`, ListItem `sourceAccessibleName` with `focused` / `selected`, Buttons `Edit <label>` / `Remove <label>`, Dialog `formAccessibleName` / `Set up a playlist`, EditableText `fieldAccessibleName`, eye Button `Show query` / `Hide query` with `checked`, link Buttons `Saved sources, n` / `Use Xtream login instead`, `Load` / `Save` / `Cancel`, AlertMessage result line, confirm Dialog |
| SRC-A11Y-02 | pass | screenshots: active = glyph + bold + `active`; error = glyph + words; fetching = glyph + words + dimmed controls; revealed vs masked = text + eye/eye-off; destructive = urgent fill + `Remove` |
| SRC-A11Y-03 | pass | first run `playlist -> epg -> (savedSources) -> xtream -> load -> wrap` (`h02c`, `h06`); edit `label -> playlist -> epg -> save -> cancel -> label` (`h12`); Xtream `server -> username -> password -> save -> cancel -> label -> server` (`h10`); the eye is never a stop |
| SRC-A11Y-04 | pass | rows `detailRowHeight` / `singleRowHeight` (`Guide.qml:2178,2202`), pinned row `groupEntryHeight`; button size by tokens (grep); click targets are live-shell |
| SRC-A11Y-05 | pass | `Guide.qml:2464` `Accessible.description: fieldRow.maskable ? Model.maskUrl(...) : ""`, `:2465` `Accessible.passwordEdit: fieldRow.fieldId === "password"` |
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
| SRC-PRIV-07 | pass | SRC-A11Y-05 |
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
| `static` greps | SRC-UI-12/13/14/15, SRC-KEY-12, SRC-SEC-12/13, SRC-A11Y-01/05, SRC-PRIV-09 | identical apart from line-number shifts; **O11 is closed** (UX.md now says `r retry`) |
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
