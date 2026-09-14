# Omarchy IPTV - Status Board

Owner: Project Manager. Living document; every role updates its own rows.
Task definitions, dependencies, gates: docs/PLAN.md. Last PM update: 2026-09-12.

States: todo | doing | blocked | review | done.
`done` requires evidence in the row or in Handoff notes (PLAN.md section 7).
Rule: FE does not start a task whose Deps (PLAN.md) are not all `done` here.

## Board

### M0 Foundations

| Task ID | Title | Owner | State | Evidence / Notes |
|---|---|---|---|---|
| M0-01 | PRODUCT.md | PO | done | docs/PRODUCT.md v0.1, 2026-09-12 |
| M0-02 | Plugin contract digest | PO | done | docs/OMARCHY-PLUGIN-CONTRACT.md, facts verified on this machine |
| M0-03 | PLAN.md + STATUS.md | PM | done | docs/PLAN.md (273 lines), docs/STATUS.md; ASCII-only checked |
| M0-04 | ARCHITECTURE.md | ARCH | done | docs/ARCHITECTURE.md, commit 42015dc; PO rulings R1-R13 appended as section 12 |
| M0-05 | UX.md | UX | done | docs/UX.md (918 lines), commit d9a1916 |
| M0-06 | Scaffold passing validate + check.sh | ARCH | done | commit 42015dc; validate exit 0; check.sh all green (61 node checks, 28 python tests, 8 qml) |
| M0-07 | Schema freeze / interface review | PM+ARCH+UX | done | PO reconciled ARCH vs UX: ARCHITECTURE.md section 12 (R1-R13); manifest updated (refreshMinutes 360, barLabelMaxWidth) |
| M0-08 | QA test plan + fixtures (docs/QA.md, tests/fixtures/) | QA | done | merged c0d5f42: docs/QA.md (174 cases), qa- fixtures, scripts/gen-playlist.py, scripts/qa-live.sh; 18 scaffold defects pre-filed (4 P2) and routed to the lanes |
| M0-09 | QA-ASSETS.md (public playlists, EPG sources) | PO | done | docs/QA-ASSETS.md, committed 0157fd6 |

### M1 MVP - Lane A (helper)

| Task ID | Title | Owner | State | Evidence / Notes |
|---|---|---|---|---|
| M1-01 | Helper skeleton, paths, atomic writes, status.json | FE | review | merged f03fef2 (lane A); structured errors, redaction, atomic 0600 writes |
| M1-02 | M3U parser + tests | FE | review | merged f03fef2; 61 parser tests incl. QA fixtures; 10k parse 467 ms |
| M1-03 | Playlist fetch + cache + stale handling | FE | review | merged f03fef2; codes bad_url, not_a_playlist added |
| M1-04 | XMLTV EPG streaming parse + now/next | FE | review | merged f03fef2; --now seam, --now-only 75 ms for 10k, private window cache |
| M1-05 | mpv control over IPC socket | FE | review | merged f03fef2; play/stop/status with fake-mpv tests (23) |
| M1-06 | State file (favorites, recents) | FE | review | merged f03fef2; helper `state` subcommand + Service.qml FileView |

### M1 MVP - Lane B (Model.js + QML)

| Task ID | Title | Owner | State | Evidence / Notes |
|---|---|---|---|---|
| M1-07 | Model.js + Model.test.js | FE | review | merged 514acef (lane B): 244 node checks; awaiting QA |
| M1-08 | Overlay shell (window, focus, open/close) | FE | review | merged 514acef; harness verified focus and Esc semantics |
| M1-09 | Overlay guide (search, groups, list, states) | FE | review | merged 514acef; two-mode keys, group column, all states in harness |
| M1-10 | Overlay EPG rows + favorites/recents | FE | review | merged 514acef; fake-EPG rows verified in harness |
| M1-11 | Bar widget (glyph, label, clicks, scroll) | FE | review | merged 514acef; wheel zap not exercised live yet |
| M1-12 | Settings propagation | FE | review | merged 514acef; shell.barConfig path, needs live check |

### M1 MVP - Join

| Task ID | Title | Owner | State | Evidence / Notes |
|---|---|---|---|---|
| M1-13 | Refresh scheduler + cached hint | FE | review | merged 514acef (Service.qml timers, cached banner) |
| M1-14 | Notifications | FE | review | merged 514acef; URL-redacted per D-QA-01 |
| M1-15 | Playback wiring end to end | FE | review | both lanes merged f03fef2; live verification pending |
| M1-16 | IpcHandler commands | FE | review | merged 514acef: toggle play stop next previous refresh status |
| M1-17 | QML unit tests (spec.qml) | FE | review | Model.spec.qml 16 passed; Guide/BarWidget specs not possible under qmltestrunner (PanelWindow), harness covers them |
| M1-18 | README | FE (UX review) | review | PO rewrote README e03f2f8 + contrib/ snippets |
| M1-19 | scripts/check.sh green | FE | done | f03fef2: validate ok, 244 node, 127 python, 16 qml, ascii ok |
| M1-20 | FE smoke on live shell (US1-US8 once) | FE | todo | Deps: M1-13..M1-19 |

### M1.1 Hardening

| Task ID | Title | Owner | State | Evidence / Notes |
|---|---|---|---|---|
| M1.1-01 | Live-shell functional QA (docs/QA.md matrix) | QA | done | harness: 148 pass / 0 fail; live shell 2026-09-13: install, enable, bar set, guide, IPC play/stop, dead stream, keybinding, menu row, restart shell all pass (QA-RESULTS.md live section) |
| M1.1-02 | Theme-switch check | QA | done | live: Retropc -> Nord with the guide open re-skinned without restart; restored |
| M1.1-03 | Performance check (10k playlist, large EPG) | QA | done | all within budget: playlist 11k parse 530 ms, overlay open ~64 ms net on 11k cache, filter <= 6.7 ms, EPG 41 MB gz 2.9 s, --now-only 37 ms |
| M1.1-04 | Security review (G4) | ARCH | done | docs/SECURITY-REVIEW.md: pass with findings (S-01 P2, 7 P3); all eight fixed and merged 134fbe1 (256 node, 144 python) |
| M1.1-05 | Fix round 1 (P1/P2) | FE | done | security round merged 134fbe1; QA-defect round merged 2ce0b52; all 23 items verified by M1.1-06 |
| M1.1-06 | Regression re-test | QA | done | QA-RESULTS.md: regression on 2ce0b52 (23/23 fixes, 0 regressions) and release regression on 502f4b3 (D-LIVE-16..18 verified, 120 cases, 0 regressions) |
| M1.1-07 | Docs polish + known limitations | FE+UX | done | README (limits, disable note, third-party bar, behavior notes, D-LIVE-18), UX 6.3/6.4 wording, ARCHITECTURE 12.1, CHANGELOG.md |
| M1.1-08 | Dead-stream hardening | FE | done | merged 502f4b3: column positioning, SIGTERM->SIGKILL stop ladder, playlist warnings in footer; verified by QA |

### Release

| Task ID | Title | Owner | State | Evidence / Notes |
|---|---|---|---|---|
| REL-01 | Clean install via git clone | QA | done | live machine 2026-09-13: clone, validate, rescan, enable, bar set; then fast-forwarded to the release build and shell restarted (QA-RESULTS.md live section) |
| REL-02 | Uninstall leaves only cache + state | QA | done (by inspection) | not executed on the live machine to keep the delivered install; runtime writes verified limited to cache, state, runtime dirs (harness + code review); README Uninstall documents all three |
| REL-03 | Version 0.1.0 + CHANGELOG + final check.sh | FE | done | manifest 0.1.0; CHANGELOG.md 0.1.0 section; check.sh all green on 502f4b3 (299 node, 144 python, 21 qml) |
| REL-04 | PO acceptance vs PRODUCT.md | PO | done | US1-US8 verified (harness + live shell); quality bar met except multi-monitor (single output available); 0 open P1/P2; accepted 2026-09-13 |
| REL-05 | Tag v0.1.0 + push + re-install at tag | PO | done | tag v0.1.0 created; no remote configured (gh not logged in), push deferred to the user; installed clone fast-forwarded to the tag |

### M2 Backlog (unscheduled)

| Task ID | Title | Owner | State | Evidence / Notes |
|---|---|---|---|---|
| M2-01 | Sources screen: in-guide playlist entry, source history, per-source cache, Xtream form (docs/M2-SOURCES.md) | PO+UX+ARCH -> FE -> QA | done | fix round merged d50e364 (QA regression 10/10, 190/196 pass); released as v0.2.0; the live-shell runbook on ec4f702 found two P1s (D-LIVE-20/21), fixed at 845d445 and both verified fixed on the live shell with their original repros (QA-RESULTS "P1 fix verification on 845d445"). 0 open P1/P2; awaiting the v0.2.1 tag |
| M2-02 | Detached player: survives `omarchy restart shell`, no stream URL on any command line (docs/ARCHITECTURE-PLAYER.md) | ARCH -> FE -> QA | doing (QA pass done, **no-go**) | design accepted with PO-1..PO-7; gate PA-0 passed on real mpv and gate PB-0 (docs/SPIKE-QUICKSHELL-SOCKET.md) withdrew the prescribed socket shape, amended in section 13; lanes PA (5fc9927) and PB (10eac45) and the fix lane (c458ebf) all merged. **Live QA pass on 8f9447e (QA-RESULTS "M2-02 player pass on 8f9447e"): 96/129 pass, 7 defects, 1 P1.** The headline case is proven - same mpv pid, same start time, one window and full identity including `launchedFrom` across ten consecutive restarts and across a SIGKILLed shell - and S-03 is closed on the first channel and after ten zaps. Blocked on **D-PLY-1** (P1: the interface goes idle while a respawned player keeps playing) and **D-PLY-2** (PO-2's `remove` acceptance case). The ARCH-P section 15 startup race was gated and **reproduces at 47%** (D-PLY-4); the lead owns that fix decision |
| M2-02x | Multiple playlists | - | superseded by M2-01 (PO-7) | the source history is the multi-playlist model; the M2-02 id now means the detached player |
| M2-03 | Channel numbers + numeric zap | - | todo | |
| M2-04 | Channel logos | - | todo | |
| M2-05 | PiP via hyprctl float + pin | - | todo | |
| M2-06 | Recording via ffmpeg | - | todo | |
| M2-07 | Catch-up / timeshift | - | todo | |
| M2-08 | First-class vertical bar layout | - | todo | |

## Defects

Format: D-<n> | severity P1/P2/P3 | task | repro | state (open/fixed/verified).

| ID | Sev | Task | Repro | State |
|---|---|---|---|---|
| D-LIVE-01 | P2 | M1.1-01 | TC-BRW-09/10, TC-RFR-10: with no query, All and any group over 200 channels show only 200 rows and the footer `First 200 of N - keep typing`; End/PgDn stop at row 199, channels 201+ unreachable by browsing, the `cached HH:MM - offline` footer never visible on such lists (UX 2.2 says All = every channel; R3 caps search results only). Evidence shots/run3-banner.png, harness/shots/run6-cap.png | verified fixed |
| D-LIVE-02 | P2 | M1.1-01 | TC-CFG-06: setting `epgUrl` from empty at runtime (the `omarchy bar set ... epgUrl` first-run path) never spawns the epg helper; `epg.pending` stays true, footer `Guide data loading...` until a manual `r`; non-empty -> non-empty changes fetch within 300 ms. Reproduced 4x (run6, run8a, run9, run9b), 4 s process watch shows no helper | verified fixed |
| D-LIVE-03 | P3 | M1.1-01 | TC-RFR-09: HTML body renders the raw helper sentence `source from 127.0.0.1 is not an M3U playlist (...) from 127.0.0.1 - check playlistUrl`; `Model.statusReason` knows `not_m3u`, the helper emits `not_a_playlist`. Expected UX 6.3 `Not an M3U file`. harness/shots/run2-notm3u.png | verified fixed |
| D-LIVE-04 | P3 | M1.1-01 | TC-FAV-08, SEC-14: `state.json` written by the Service FileView is mode 644 (ARCH: 0600; dir is 700, every helper file is 600). Names and ids only, no URLs | verified fixed |
| D-LIVE-05 | P3 | M1.1-01 | TC-RFR-01, TC-BAR-08: after `r` the footer holds `Refreshing...` for the whole 3 s transient then jumps to `N channels - updated HH:MM`; `Refreshed - N channels` (UX 6.1) never shows although the helper finished in ~40 ms and the notification fired | verified fixed |
| D-LIVE-06 | P3 | M1.1-01 | TC-BRW-21: `Ungrouped` appears at its first-seen position (between News and Padded on qa-groups.m3u) instead of last (UX 2.2). harness/shots/run1-open.png | verified fixed |
| D-LIVE-07 | P3 | M1.1-01 | TC-FAV-05: removing the last Recent entry hides the column entry but leaves the cursor scope on `recent` (`No channels in Recent`, `Recent - 0 channels`, no highlighted entry). shots/run1-recent-removed-card.png | verified fixed |
| D-LIVE-08 | P3 | M1.1-01 | TC-EPG-04: EPG fetch failure with an earlier window loaded sends the `Guide data error` notification but shows no `Guide data unavailable (...)` banner (`bannerKind` requires `!epgLoaded`). harness/shots/run5-epg-404.png | verified fixed |
| D-LIVE-09 | P3 | M1.1-01 | TC-UI-01: `r` in the not-configured state shows the `Refreshing...` transient for 3 s although nothing runs | verified fixed |
| D-LIVE-10 | P3 | M1.1-01 | TC-UI-02: with no cache, switching from a failed source to a new URL keeps the old source's error text (naming the old host) on screen with footer `Refreshing...` for the whole fetch instead of `Loading playlist... / Fetching from <new host>` | verified fixed |
| D-LIVE-11 | P3 | M1.1-01 | TC-CFG-02: timeout wording disagrees: helper default 20 s, guide reason `Timed out`, UX 6.3 `Timed out after 30 s`, README Limits `60 seconds` | verified fixed |
| D-LIVE-12 | P3 | M1.1-01 | TC-BAR-09: Enter/Space on the already-playing channel from another list (e.g. Favorites) keeps the previous `launchedFrom`, so the zap ring does not follow the list the user is on | verified fixed |
| D-LIVE-13 | P3 | M1-18 | TC-INST-05/10, TC-BAR-12, TC-UI-13: README lacks the `settings are lost on disable` note, lists two leftover dirs (runtime dir missing from Uninstall), no third-party-bar limitation, no qmllint warning baseline | verified fixed (docs) |
| D-LIVE-14 | P3 | M1-19 | TC-UI-13: qmllint reports 6 `signal-handler-parameters` and 1 `uncreatable-type` warnings on top of the recorded baseline categories (57 missing-property, 42 unqualified); 0 errors | verified fixed |
| D-LIVE-15 | P3 | M1.1-08 | PERF-06 run 2 / TC-PLAY-09: after the hung-mpv health-check sequence (SIGSTOP, two `mpv unresponsive` restarts, SIGCONT, stop) the next play logged `play failed: mpv did not answer` and opened no window for 6.6 s; the following play worked; plain stop -> play does not reproduce | verified fixed |
| D-LIVE-16 | P3 | M1.1-05 | TC-BRW-05/06 (UX 2.2): with a group column taller than the card (20+ groups), every reopen that lands on All starts the column scrolled one entry down, so `Favorites` is hidden above `All` until Left/h; first open and a reopen on Favorites are correct; a column that fits is correct. shots/run1-reopen.png, run2-reopen.png (QA-RESULTS R6) | verified fixed |
| D-LIVE-17 | P3 | M1.1-08 | TC-PLAY-06/09: once in 24 fresh launches (run5b) mpv mapped its window but never answered on the IPC socket; `stop`/`s` and the health check only send SIGTERM (Service.qml:421, :787), a wedged (or SIGSTOPped) mpv ignores it and is never reaped; in-flight control calls starved the health timer; `nowPlaying` moved on while the window stayed on the old channel. Not reproducible on demand (run5c 8/8 clean). Fix: escalate to SIGKILL after an ignored SIGTERM (QA-RESULTS R6) | verified fixed |
| D-LIVE-18 | P3 | M1.1-07 | README Limits says capped playlists show `a warning in the guide`; the guide renders no helper warning (run6, 50,500-entry list: `bannerKind none`, footer `50,000 channels - updated 01:53`; warnings only in playlist-status.json). Render them or reword the README (QA-RESULTS R6) | verified fixed |
| D-LIVE-19 | P3 | M1-09 | TC-CFG-12 / TC-UI-01: clearing `playlistUrl` at runtime (the `omarchy bar set ... playlistUrl ""` path) while a list is loaded flips `emptyKind` to `unconfigured` but the service keeps its channels, so the `No playlist configured` body and command box are drawn over the still-rendered channel list and group column (rows 10, showColumn true) until a new URL loads; survives close/reopen. Starting unconfigured is correct. Reproduced identically on 2ce0b52 (pre-existing, not a regression). shots/run5f-cleared.png, run5f-old-cleared.png (QA-RESULTS RR6) | verified fixed |
| D-SRC-01 | P3 | M2-01 | SRC-MIG-01: the migrated record keeps `fetchedAt 0` / `channelCount 0` (counts not copied from the migrated `playlist-status.json`), so the active row reads `not loaded yet` until the first refresh although the guide shows the migrated channels. QA-RESULTS.md S7 | verified fixed |
| D-SRC-02 | P2 | M2-01 | SRC-CLI-02/08: `omarchy bar set ... epgUrl` runs the EPG helper but the URL is never adopted into the history record; the next switch away and back writes `epgUrl (none)` into the settings and the EPG is silently lost (the guide edit path adopts it fine). QA-RESULTS.md S7 | verified fixed |
| D-SRC-03 | P2 | M2-01 | SRC-FR-11/CLI-03 (regression of TC-CFG-04): `omarchy bar set ... playlistUrl ftp://x` sets `settingsInvalid` but leaves the guide in `Loading playlist... / Fetching from x` for good instead of the error state (no helper runs). `shots/sources-cli-ftp.png` | verified fixed |
| D-SRC-04 | P2 | M2-01 | SRC-SW-06: Enter on a never-fetched source whose probe fails shows the `Switched to <label>` transient before the probe and then no error at all (`sourceErrors` only); the previous source silently stays active. `shots/sources-never-switch-failed.png` | verified fixed |
| D-SRC-05 | P3 | M2-01 | SRC-RM-03: when the active source is removed and the guide returns to setup, the stale search query stays as the header above the first-run form instead of `Search channels...`. `shots/sources-none-active.png` | verified fixed |
| D-SRC-06 | P3 | M2-01 | SRC-FR-11/CLI-03/UI-14: CLI-invalid values render the M1 reasons with a host (`Unsupported URL from unknown source`, `URL too long from h.test`) instead of the UX 5.4 messages; the error-state hint says `r reload` where UX 5.3 says `r retry`; a U+2028 inside an `http://` URL gets the `scheme` message | verified fixed |
| D-SRC-07 | P3 | M2-01 | SRC-HELP-07: helper `cache prune` deletes the `--active` key's directory when it is not also listed under `--keep` (Service.qml always lists every key, so no user impact today; hardening) | verified fixed |
| D-SRC-08 | P3 | M2-01 | SRC-XT-02: an Xtream server URL with a `#fragment` (`http://h.test/#frag`) is accepted, the fragment dropped silently, where ARCH 3.4 says `bad_server` / UX 5.4 `server_path` | verified fixed |
| D-SRC-09 | P3 | M2-01 | SRC-SEC-21: `parseState` / `normalize_state` keep a history record whose URL contains a NUL (control character) instead of dropping or sanitizing it | verified fixed |
| D-SRC-10 | P3 | M2-01 | SRC-H13: `omarchy bar set ... playlistUrl <new>` while another source is active attaches the settings' current `epgUrl` (the previous source's, Xtream credentials included) to the new CLI record (`editMasked` shows it, row shows `EPG`) | verified fixed |
| D-LIVE-20 | P1 | M2-01 | SRC-SW-01/02/06 + add, live shell only: `Service.qml persistActive` writes the new active source through `shell.updateEntryInline` and `shell.json` is updated correctly, but the host never re-emits the plugin's `settings` for its own write, so `root.playlistUrl` stays stale and `reconcile()` never runs. Enter on a source row shows `Switched to <label> - N channels` while the guide keeps rendering the previous source (20+ s, no timeout, no error); a successful add never becomes active (UX-SOURCES 1.5); a second Enter reports `Could not save settings - try omarchy bar set` because `shell.qml` takes its `if (!dirty) return false` branch for a value already persisted. Recovers only on an external write (`omarchy bar set`, even of the identical value) or `omarchy restart shell`. Invisible to the dev harness, which supplies a fake `updateEntryInline` (QA-SOURCES section 6). `shots/E-back-t1.png`, `qs log`: `switch did not observe a cache load within 5000 ms` (QA-RESULTS L2, L6). Fixed at `845d445`: the service applies its own settings write locally (`Model.settingsWithOwnWrite` over `hostSettings`) and drops the override as soon as the host reports anything else; a `false` return from a writable entry is the host's `!dirty` branch and counts as success (`Model.barEntryWritable` separates a real persist failure). QA re-ran the original repro on the live shell: add is active in 723 ms, four Enter switches arrive in 145-161 ms with the guide, footer and `shell.json` all agreeing, and the second and third Enter on the same row report nothing (QA-RESULTS P2) | verified fixed |
| D-LIVE-21 | P1 | M2-01 | SRC-RM-01/03/05, live shell only: removing the active source clears `playlistUrl` in `shell.json` and sets `activeSource null`, but the guide never returns to setup - it sits on `Loading playlist... / Fetching from <the removed source's host>` with `configured true` / `status loading` for 18+ s, waiting on a fetch whose cache dir the removal just deleted. Same root cause as D-LIVE-20 (the cleared value is the plugin's own write); the live recurrence of the D-SRC-03 / TC-CFG-04 stuck-loading family through the Sources screen. `shots/I-return-to-setup.png`, `shots/I-stuck-loading.png` (QA-RESULTS L6). Fixed at `845d445` with D-LIVE-20 (same root cause): `configured` goes false 821 ms after the confirm, `status ready`, `channels 0`, and Esc lands on the first-run surface with the `Saved sources (1)` link (QA-RESULTS P3) | verified fixed |
| D-LIVE-22 | P3 | M1.2 | QA-RESULTS P10/O18, found 2026-09-13 at 845d445 (pre-dates the P1 fix; introduced by `cf22c3f`, the cosmetics lane): when the EPG helper reports a warning **and** the playlist is serving a stale cached copy after a failed refresh, the footer shows `Guide data warning: 1 programmes for channels not in the playlist dropped` instead of `8 channels - cached 22:49 - offline`. `Model.footerStatus` ranks `warning` above the count line and the `cached HH:MM - offline` marker lives in that count line, so it is the footer's only staleness cue that the warning displaces. This matches the letter of the UX.md precedence list (warning > plain channel count) and the failure itself stays visible in the banner (`Playlist refresh failed (Connection refused) - showing cached copy from 22:49 - r retry`, `bannerKind playlistError`), so it is filed as cosmetic, not as a hidden failure. Repro: `d19.sh` / `h21` (`logs/d19.txt`) | open |
| D-PLY-1 | P1 | M2-02 | PLY-LIFE-12 / PLY-RST-06 / PLY-SOCK-01, live shell, found 2026-09-14 at 8f9447e: after any helper-driven ladder-and-respawn the shell goes idle while the new player keeps playing. Two independent triggers, both deterministic: (a) `kill -STOP` the player and wait ~21 s for the health check's two-strike verdict (journal: `omarchy-iptv: mpv unresponsive, restarting player`), 3/3; (b) `rm "$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock"` then play another channel, 2/2. The relaunched mpv is genuinely playing (`idle-active` false, real `path`, window mapped and titled, its `user-data/omarchy-iptv` stash reading `playing:true` with the right id) while `status` reports `playing false`, `nowPlaying null`, `player.up/attached/wanted` all false. Because `wanted` is false the 250 ms retry timer is off, so it never reattaches (unchanged at 15 s and 30 s). Exactly one player exists throughout, so this is not a second-window defect. `stop` still reaches it and a shell restart reattaches to the same pid and restores the right state - but the interface already says stopped, so the user has no reason to try. The plan's P1 list verbatim: "the interface goes idle while the player keeps playing". Suspected: the `player restart --from term` reply path in `Service.qml` not re-arming `playerWanted` after a relaunch it issued itself. QA-RESULTS.md M8 | open |
| D-PLY-2 | P2 | M2-02 | PLY-WEAK-02, live shell, found 2026-09-14 at 8f9447e: `omarchy plugin remove io.github.rmcdavid.iptv --yes` with a channel playing leaves the player alive and windowed at 21 s and still at 45 s, where `disable` stops it in 6676 ms. `remove` deletes the plugin directory, and `Component.onDestruction`'s orphan-check is `python3 <plugindir>/bin/omarchy-iptv player orphan-check`, so there is nothing left to exec. The README's escape hatch lives in the same deleted directory and cannot be run either - the sentence naming it is in the bullet that names removal. Restoring the directory from a backup made the command work and it reaped the orphan at once. PO-2's second named acceptance case, with both halves of its compensating control failing together. P2 by the letter (logging out remains documented); **the lead may reasonably raise it to P1**. QA-RESULTS.md M8 | open |
| D-PLY-3 | P2 | M2-02 | PLY-WEAK-06 step 6 / PLY-FIX-01, live shell, found 2026-09-14 at 8f9447e, 2 of 3 runs: the PO-3 mark lands correctly and silently, but `state.json.session` is still on disk afterwards instead of cleared. The next shell start consumes the record again and re-marks the same channel with the same `HH:MM`; a third start is clean. This is the second-verdict-on-an-event-already-dealt-with the fix lane `c458ebf` says it closed, surviving in the deferred drain path (`applyUserState` -> `markDeadSession`) rather than in the twelve branches that lane routed. Suspected the write racing `stateFile`'s own load (same handler as D-PLY-4), or `saveState()`'s `dirsReady` deferral. QA-RESULTS.md M8 | open |
| D-PLY-4 | P2 | M2-02 | ARCH-P section 15's known startup race, gated and measured on 2026-09-14 at 8f9447e: **it reproduces, 14 losses in 30 trials (47%)**. Restart the shell and issue `play` from the earliest instant the successor's IPC accepts one (landed on the 3rd or 4th attempt in all 30 trials); the arriving state file then replaces `userState` wholesale and the session record the play just wrote is gone. Every loss reads `playing true`, `nowPlaying` correct, window mapped, `session` null. Consequence proven end to end: after a lost race the stream was killed with no shell attached and the reattaching shell marked nothing (`failedAt {}`) and raised no toast, so PO-3 is silently unavailable for roughly half the plays issued at shell start. Not fixed by QA on the lead's instruction; the "fix only if it reproduces" gate is met. QA-RESULTS.md M5 | open |
| D-PLY-5 | P2 | M2-02 | PLY-SEC-14 / PO-5, found 2026-09-14 at 8f9447e: PO-5's required README sentence naming the `--ytdl` cost is absent - `ytdl`, `yt-dlp` and `youtube` appear 0 times in `README.md` and 0 times in `CHANGELOG.md`. The cost is real and was reproduced live: with the documented setting `mpvArgs '--ytdl=yes'` and a stream that fails to open, mpv's `ytdl_hook` spawned `/usr/bin/python /usr/bin/yt-dlp --no-warnings -J --flat-playlist ... -- http://qa-user:qa-secret@127.0.0.1:9/live/qa-token-XYZ/dead.ts`, putting the full credentialed URL on another process's 0444 command line for seconds (99 sweep samples caught it). The default `--ytdl=no` is clean. The README's headline claim "No stream address, credential or header value ever reaches any command line" therefore has an unstated exception the README itself documents how to enable. Suggested: one sentence beside the `mpvArgs` row and in the 0.3.0 `Known limitations`. QA-RESULTS.md M8 | open |
| D-PLY-6 | P3 | M2-02 | PLY-PERF-02 / PLY-STOP-03, found 2026-09-14 at 8f9447e: a wedged (SIGSTOPped) player takes ~6.27 s to reap, not the budgeted 4.5 s - 6258 / 6265 / 6269 / 6276 ms across four runs, deterministic. The ladder is quit@0, TERM@2.0, KILL@4.0, settle@4.5, but against an unresponsive player the quit rung first spends the full `--ipc-timeout` 2.0 s, which the budget does not account for. The player is reaped and the interface clears in 52-59 ms. README says "within about four seconds". Either move the budget and the prose to about six and a half seconds, or skip the quit wait when the probe already said `responsive:false`. QA-RESULTS.md M8 | open |
| D-PLY-7 | P3 | M2-02 | PLY-SEC-07, found 2026-09-14 at 8f9447e: the player can write a durable file outside the documented list, into `$HOME`. mpv inherits the shell's working directory (`/home/ricky`) and its default key bindings are live on the focused window, so `s` on the player writes `~/mpv-shot0001.jpg` (mode 0644) - a durable image of what was being watched, in a directory README `Files it writes` does not mention. The milestone already reserves `--screenshot-template` against durable exposure; the default template is not covered. Suggested: spawn with `--screenshot-dir` under the runtime directory, or name it in `Files it writes`. QA-RESULTS.md M8 | open |

Found by QA in the dev-harness pass on f03fef2 (2026-09-12/13); full steps, expected-vs-actual quotes and evidence paths per defect are in `docs/QA-RESULTS.md` section 8, results per test case in sections 3-7. Severity per PLAN.md section 6: D-LIVE-01 and D-LIVE-02 degrade US2 and US6; the rest are cosmetic, wording, docs or hardening.

Regression re-test on 2ce0b52 (QA, 2026-09-13, `docs/QA-RESULTS.md` section "Regression on 2ce0b52"): D-LIVE-01..15 and S-01..S-08 all verified fixed with the original repros (23/23, none reopened); 137-case regression sample with no regression; D-LIVE-16..18 are new P3s found in that pass (0 open P1/P2).

Release regression on 502f4b3 (QA, 2026-09-13, `docs/QA-RESULTS.md` section "Release regression on 502f4b3"): D-LIVE-16, D-LIVE-17 and D-LIVE-18 verified fixed with the original repros (45-group and 50,500-entry generated playlists, SIGSTOPped mpv over the harness); 120-case regression sample with no regression, PERF-01..07 within budget, gates green (299 node, 144 python, 21 qml, validate 0); one new P3, D-LIVE-19, pre-existing on 2ce0b52 (0 open P1/P2).

M2-01 Sources pass on 7e13053 (QA, 2026-09-13, `docs/QA-RESULTS.md` section "M2-01 Sources pass on 7e13053"): 196 `SRC-` cases through the dev harness, 181 pass / 10 fail / 4 blocked (live shell) / 1 not run; D-SRC-01..10 filed (3 P2: D-SRC-02 CLI `epgUrl` lost on the next switch, D-SRC-03 CLI `ftp://` stuck in the loading state - a TC-CFG-04 regression, D-SRC-04 a failed never-fetched switch reports `Switched to ...` and no error; 7 P3). Privacy sweep clean (no credential in any sink but `state.json` 0600 and the probe argv); 50-case M1 regression sample passes apart from D-SRC-03; switch redraw at 10k median 17 ms (first cold switch 352 ms). No-go for v0.2.0 until the three P2 defects are fixed and the live runbook (QA-SOURCES.md section 9) has run.

M2-01 regression on d50e364 (QA, 2026-09-13, `docs/QA-RESULTS.md` section "M2-01 regression on d50e364"): D-SRC-01..10 verified fixed with their original repros (10/10, none reopened, no new defect); 190/196 `SRC-` cases pass (0 fail, 4 blocked: live shell, SRC-UI-16 not run, SRC-MIG-07 not re-run), 55-case M1 sample with no regression (TC-CFG-04 renders the error state again); performance unchanged (10k switch median 19 ms warm, guide open 73 ms, helper 10k 483 ms, `state.json` 50 sources 11,387 B); privacy sweep clean; gates green (653 node, 199 python, 29 qml, validate 0). 0 open P1/P2: go for v0.2.0 from the dev harness; the live-shell runbook (QA-SOURCES.md section 9, plus the D-SRC-04/D-SRC-10 live checks listed in R10) remains before the tag.

Live-shell Sources verification on ec4f702 (QA, 2026-09-13, `docs/QA-RESULTS.md` section "Live-shell Sources verification on ec4f702"): the section 9 runbook on the user's machine with the installed v0.2.0 plugin. 13 cases A-M: 7 pass, 2 fail, 1 partial, 3 blocked. Migration (SRC-MIG-10) is clean - v2 / cacheLayout 2, favorites and 5 recents preserved, 0600/0700 throughout, per-source cache, the migrated row shows real counts - and `omarchy plugin update --yes` reports up to date from GitHub. D-SRC-04 and D-SRC-10 are both **verified fixed on the live shell**. The Sources screen, add, edit, label rename, URL masking with `Ctrl+R` reveal, the theme re-skin and restart persistence all match UX-SOURCES. Privacy sweep clean: a userinfo URL reached no sink but `state.json` and `shell.json` (both 0600) - 0 hits in `status`, `qs log`, the journal, notifications, the helper and every row, footer and tooltip. Two new **P1** defects, both live-only: D-LIVE-20 (switching and add-activation never take effect while the footer reports success) and D-LIVE-21 (the guide never leaves the loading state after the active source is removed). Both were masked by the harness's fake `updateEntryInline`. SRC-KEY-11 (mouse) and SRC-LST-09/SRC-UI-20 (narrow card) are blocked on this machine - no pointer-injection tool, and `hyprctl keyword` is unavailable on the Lua config parser - and SUPER+SHIFT+T cannot be driven by `wtype` (the bind is registered and its command works). **No-go for v0.2.0 until D-LIVE-20 and D-LIVE-21 are fixed**, then re-run live cases D, E, I plus SRC-PERF-02/03, which no completed switch existed to measure.

P1 fix verification on 845d445 (QA, 2026-09-13, `docs/QA-RESULTS.md` section "P1 fix verification on 845d445"): the installed clone was moved to `845d445`, the shell restarted, and **D-LIVE-20 and D-LIVE-21 were both re-tested with their original repros on the live shell and verified fixed** - add makes the new source active in 723 ms, four Enter switches arrive in 145-161 ms with guide content, footer transient and `shell.json` all agreeing, a switch to the 1,474-channel source and back needs no refetch, the second and third Enter on the same row report nothing (the `Could not save settings` path is gone), and removing the active source reaches `configured false` in 821 ms with the first-run surface behind it. The fix's own risk surface was driven too: an external `omarchy bar set` reconciles in 636 ms and still wins when it races a plugin-side switch (0 ms / 50 ms / 300 ms after the keystroke), a plugin-side switch still wins after a CLI write, and the host echoing our own value back produces 0 extra switch events and 0 helper runs. Harness fidelity measured independently by checking the pre-fix `Service.qml` (`d153fe9`) into a scratch copy: the corrected scenario is **61 pass / 0 fail** on `845d445` and **44 pass / 23 fail** on the pre-fix service. Regression: 61/61 scenario checks, 69 re-run SRC and M1 cases and the live blocks above, **0 regressions**; D-LIVE-19 verified fixed as a by-product and O11 closed; one new P3, D-LIVE-22 (footer precedence, from the cosmetics lane). Switch redraw is measurable on a real shell for the first time: median 59 ms on a small source, 116 ms median / 147 ms worst at 1,474 channels, guide open 69-75 ms - every budget met. Privacy sweep with a credentialed source clean (0 hits in status, `qs log`, journal, notifications, helper and every rendered string; the only screenshot hit is the deliberate `Ctrl+R` reveal). Gates green (681 node, 199 python, 33 qml, validate 0 on the repo and on the installed clone). The machine was restored byte for byte and proved. **0 open P1/P2: go for v0.2.1.**

M2-02 player pass on 8f9447e (QA, 2026-09-14, `docs/QA-RESULTS.md` section "M2-02 player pass on 8f9447e"): the `docs/QA-PLAYER.md` runbook executed on the reference machine with the installed clone moved to the RC and back. **96 of 129 `PLY-` cases pass, 5 fail, 6 pass with a corrected expectation, 6 blocked, 16 not run**; seven defects filed, **one P1**. The milestone's whole reason to exist is proven: `omarchy restart shell` with a channel playing keeps the **same mpv pid and the same `/proc` start time**, exactly one window at every 100 ms sample, `time-pos` advancing with no reload, and the full identity including `launchedFrom` recovered from the player's own stash - six clean runs, ten consecutive restarts, and a `pkill -KILL`ed shell that ran no teardown at all. S-03 is closed on the first channel and byte-identically after ten zaps; headers reach mpv only over the socket and are cleared between channels; 241,675 `/proc` samples carry 0 plugin-originated needles; the journal carries 0 mpv lines. Spike caveats C1-C10 are implemented as prescribed and the reattach-after-death trap is unreproducible (750 ms). PO-2's `disable` gate passes at 6676 ms and the README's escape hatch stops an orphan in 220 ms with no shell running. PO-3's full procedure marks silently with **zero** toasts and the guide draws the alert glyph U+F0026 and `Failed HH:MM - Space to retry`, not a red row. The superseded-stop regression is closed and the stop ladder completes with **no shell alive**. Every performance budget is met except the wedged-stop one. Blocking: **D-PLY-1** (P1, the interface goes idle while a respawned player keeps playing, from two independent triggers) and **D-PLY-2** (PO-2's `remove` case, which also deletes the documented remedy). The ARCH-P section 15 race was gated as instructed and **reproduces at 47% (14/30)** - D-PLY-4. Harness rule-11 evidence: 49/49 at `8f9447e`, 33/49 against pre-M2-02 `5e90283`. Gates green (885 node, 247 python, 42 qml, validate 0). The machine was restored byte for byte and proved. **No-go for v0.3.0.**

## Decisions log

| Date | Decision | By |
|---|---|---|
| 2026-09-12 | Delivery form: native Omarchy shell plugin, id `io.github.rmcdavid.iptv`, name "IPTV", installed via `omarchy plugin add <git-url> --enable` | PO |
| 2026-09-12 | Kinds: `bar-widget` + `overlay`; `service` only if the Architect needs a persistent state owner | PO |
| 2026-09-12 | Playback: exactly one mpv instance driven over JSON IPC; never a second player window | PO |
| 2026-09-12 | Sources: one M3U/M3U8 URL or local path + optional XMLTV URL (plain or gz), via manifest settings schema in shell.json (0600); Xtream URL helper deferred to M2 | PO |
| 2026-09-12 | Data pipeline: stdlib-only Python 3 helper does fetch/parse; QML reads compact JSON caches; 10k channels must not stall the shell | PO |
| 2026-09-12 | Locations: config in shell.json; cache `~/.cache/omarchy-iptv/`; favorites/recents `~/.local/state/omarchy-iptv/`; nothing written inside the plugin dir at runtime | PO |
| 2026-09-12 | Theme: all colors from `Color.*` / `Style.*`; no hardcoded colors without a `CONVENTION-EXCEPTION` comment | PO |
| 2026-09-12 | Security: no sudo; never execute playlist content; never interpolate playlist strings into `bash -c`; URLs/headers reach mpv or curl as argv items only | PO |
| 2026-09-12 | Install flow: `omarchy plugin add`, set `playlistUrl`, press the key; keybinding and menu entry are documented one-liners the user adds | PO |
| 2026-09-12 | Keybinding: `SUPER + SHIFT + T` (verified free); `SUPER + CTRL + T` is taken by Activity | PO |
| 2026-09-12 | Multi-group `group-title` (`A;B;C`): channel is listed under its FIRST group; the full string stays searchable | PO |
| 2026-09-12 | QA sources: iptv-org `us.m3u` for live QA, `index.m3u` (11,041) for the 10k gate, Pluto/Samsung XMLTV gz for EPG; unit tests never touch the network | PO |
| 2026-09-12 | Effort unit: S 0.5-2 h, M 2-5 h, L 5-10 h; one agent-session ~= 3 h. Sequencing is by phase/dependency, not calendar | PM |
| 2026-09-12 | Interim assumptions A1-A9 in PLAN.md section 2 stand until ARCHITECTURE.md / UX.md override them; overrides are logged here | PM |
| 2026-09-12 | Test runners: `python3 -m unittest`, `node Model.test.js` (dev-only node), `qmltestrunner` for `*.spec.qml`; all wired into `scripts/check.sh` | PM |
| 2026-09-12 | Schema freeze gate M0-07: after it, any schema/interface change needs a log entry here before code changes | PM |
| 2026-09-12 | Defect severity: P1 blocks a story, P2 degrades, P3 cosmetic; release needs zero open P1/P2 | PM |
| 2026-09-12 | Reconciliation rulings R1-R13 in ARCHITECTURE.md section 12: UX keyboard model (search mode on open, Tab or / to list mode, no Ctrl chords) supersedes ARCH decision 9; result cap 200; searchKey = fold(name + " " + group) with UX 2.5 ranking; card per UX 5.1; bar glyphs per state, name elided at barLabelMaxWidth | PO |
| 2026-09-12 | Settings frozen: playlistUrl, epgUrl, refreshMinutes (default 360, min 15), mpvArgs, showChannelName, maxRecents, barLabelMaxWidth (default 180); read from the bar-layout entry via shell.barConfig | PO |
| 2026-09-12 | mpv stays an attached Process in M1 (ARCH decision 2); PM risk R3 detached-mpv mitigation deferred to M2 | PO |
| 2026-09-12 | IPC verbs: toggle, play, stop, next, previous, refresh, status. Service actions add removeRecent, focusPlayer, zap over the launch-list ring | PO |
| 2026-09-12 | M1 runs as three parallel worktree lanes: FE lane A (bin/omarchy-iptv + python tests), FE lane B (Model.js, Service.qml, Guide.qml, BarWidget.qml, JS/QML tests), QA (docs/QA.md, qa- fixtures, generator script). PO merges, then QA runs the live-shell pass | PO |
| 2026-09-12 | Privacy rulings from QA defects: a channel name never falls back to a URL (title, tvg-name, tvg-id, then Channel <n>); every notification, status line, tooltip, console line and IPC status output is URL-redacted to the host (Model.redactUrls); IPC status carries no stream URL | PO |
| 2026-09-12 | Helper epg gets a --now <epoch> clock seam for deterministic tests; HTML bodies are not_a_playlist; local-path errors show the basename only | PO |
| 2026-09-12 | Live QA pass on this machine: plugin installed by git clone into ~/.config/omarchy/plugins, keybinding and menu row added with backups and restored afterwards unless the pass succeeds (then left in place as the delivered state), theme check retropc -> tokyo-night -> retropc, EPG-matched checks use the generator pair (file://) plus the Pluto XMLTV for real gzip | PO |
| 2026-09-13 | D-LIVE-01 ruling: the 200-row cap applies to search results only; browsing with an empty query must reach every channel in the scope while keeping the 150 ms open budget (virtualized or windowed list) | PO |
| 2026-09-13 | D-LIVE-02 ruling: any epgUrl change, including from empty, triggers the EPG helper; also at service start and after a playlist load when epg-now.json is missing or stale | PO |
| 2026-09-13 | Wording: timeout reason is `Timed out` (no seconds), README states the 60 s download deadline; `not_a_playlist` renders as `Not an M3U playlist`; `Ungrouped` is always last | PO |
| 2026-09-13 | S-01: raw-title prefix applied to mpv `title` only (force-media-title is not property-expanded by mpv, verified live) | FE, accepted by PO |
| 2026-09-13 | v0.1.0 released and published: github.com/rmcdavid/omarchy-iptv made PUBLIC at the user's request; GitHub release created | PO |
| 2026-09-13 | M2 starts with the Sources lane (user request); Xtream helper and multiple playlists fold into it; detached/idle mpv is lane 2 | PO |
| 2026-09-13 | Sources reconciliation SR1-SR10 (ARCHITECTURE-SOURCES.md): UX names for the view model over state-file names via Model.sourceView; cancelProbe added; mask token **** with type/output visible; architecture caps canonical (label 64, credentials 256); UX 5.4 codes canonical; lane 1 merges first | PO |

## Blockers

- none (live-shell verification completed 2026-09-13 with the user's permission)

| Since | Task | Blocker | Owner | Unblock action |
|---|---|---|---|---|
| - | - | none | - | - |

## Next up

1. Tag v0.2.1 at 845d445 (or at the current origin/main, which is docs-only ahead of it), push, and update the user's installed clone; QA's pass is green and the machine is back on ec4f702.
2. M2 lane 2: detached/idle mpv (survives `omarchy restart shell`, no URL on the command line).
3. M1.2 cosmetics: D-LIVE-22 (footer precedence vs the `cached - offline` marker). D-LIVE-19, O11 and the EPG helper warnings all landed in the cosmetics lane and are verified.
4. Remaining M2 backlog per docs/PLAN.md section 10.

## Handoff notes

Append newest first. Template:

```
### <Task ID> -> <state>  (<role>, <date>)
Files: ...
Commands: <cmd> -> exit <n>, <key output / numbers>
Open issues / deviations / assumptions: ...
```

### M0-03 -> done  (PM, 2026-09-12)
Files: docs/PLAN.md, docs/STATUS.md (docs/QA-ASSETS.md incorporated: A8, M0-08, M0-09, M1-02, M1-04, M1-07, M1.1-03, R14, G3)
Commands: `LC_ALL=C grep -nP '[^\x00-\x7F]' docs/PLAN.md docs/STATUS.md` -> no output (ASCII-only)
Open issues: ARCHITECTURE.md and UX.md absent at write time; PLAN.md carries
`[ARCH-SLOT]` / `[UX-SLOT]` markers and interim assumptions A1-A9 for the
Architect and UX Designer to confirm or override (log overrides above).
