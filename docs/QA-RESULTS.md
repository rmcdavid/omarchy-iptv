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
