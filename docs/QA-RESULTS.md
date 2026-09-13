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

