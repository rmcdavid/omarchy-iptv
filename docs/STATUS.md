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
| M1.1-06 | Regression re-test | QA | done (harness) | docs/QA-RESULTS.md "Regression on 2ce0b52": 23/23 fixes verified, 137 cases re-run with 0 regressions, gates green (271 node, 144 python, 18 qml, validate 0); new P3s D-LIVE-16/17/18; live-shell block (12 cases) unchanged |
| M1.1-07 | Docs polish + known limitations | FE+UX | done | README (limits, disable note, third-party bar, behavior notes, D-LIVE-18), UX 6.3/6.4 wording, ARCHITECTURE 12.1, CHANGELOG.md |
| M1.1-08 | Dead-stream hardening | FE | doing | D-LIVE-16/17/18 fix lane started 2026-09-13 |

### Release

| Task ID | Title | Owner | State | Evidence / Notes |
|---|---|---|---|---|
| REL-01 | Clean install via git clone | QA | todo | Deps: M1.1-06 |
| REL-02 | Uninstall leaves only cache + state | QA | todo | Deps: REL-01 |
| REL-03 | Version 0.1.0 + CHANGELOG + final check.sh | FE | todo | Deps: REL-02 |
| REL-04 | PO acceptance vs PRODUCT.md | PO | todo | Deps: REL-03 |
| REL-05 | Tag v0.1.0 + push + re-install at tag | PO | todo | Deps: REL-04 |

### M2 Backlog (unscheduled)

| Task ID | Title | Owner | State | Evidence / Notes |
|---|---|---|---|---|
| M2-01 | Xtream Codes URL helper | - | todo | After v0.1.0 |
| M2-02 | Multiple playlists | - | todo | |
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
| D-LIVE-19 | P3 | M1-09 | TC-CFG-12 / TC-UI-01: clearing `playlistUrl` at runtime (the `omarchy bar set ... playlistUrl ""` path) while a list is loaded flips `emptyKind` to `unconfigured` but the service keeps its channels, so the `No playlist configured` body and command box are drawn over the still-rendered channel list and group column (rows 10, showColumn true) until a new URL loads; survives close/reopen. Starting unconfigured is correct. Reproduced identically on 2ce0b52 (pre-existing, not a regression). shots/run5f-cleared.png, run5f-old-cleared.png (QA-RESULTS RR6) | open |

Found by QA in the dev-harness pass on f03fef2 (2026-09-12/13); full steps, expected-vs-actual quotes and evidence paths per defect are in `docs/QA-RESULTS.md` section 8, results per test case in sections 3-7. Severity per PLAN.md section 6: D-LIVE-01 and D-LIVE-02 degrade US2 and US6; the rest are cosmetic, wording, docs or hardening.

Regression re-test on 2ce0b52 (QA, 2026-09-13, `docs/QA-RESULTS.md` section "Regression on 2ce0b52"): D-LIVE-01..15 and S-01..S-08 all verified fixed with the original repros (23/23, none reopened); 137-case regression sample with no regression; D-LIVE-16..18 are new P3s found in that pass (0 open P1/P2).

Release regression on 502f4b3 (QA, 2026-09-13, `docs/QA-RESULTS.md` section "Release regression on 502f4b3"): D-LIVE-16, D-LIVE-17 and D-LIVE-18 verified fixed with the original repros (45-group and 50,500-entry generated playlists, SIGSTOPped mpv over the harness); 120-case regression sample with no regression, PERF-01..07 within budget, gates green (299 node, 144 python, 21 qml, validate 0); one new P3, D-LIVE-19, pre-existing on 2ce0b52 (0 open P1/P2).

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

## Blockers

- none (live-shell verification completed 2026-09-13 with the user's permission)

| Since | Task | Blocker | Owner | Unblock action |
|---|---|---|---|---|
| - | - | none | - | - |

## Next up

1. Live-shell verification on the reference machine (12 blocked cases): install by git clone into ~/.config/omarchy/plugins, rescan, enable, `omarchy bar set` playlistUrl, keybinding and menu row from contrib/, theme switch, restart shell; commands in docs/QA-RESULTS.md section 7. Needs the user's go-ahead.
2. Tag v0.1.0 once the live-shell cases pass (v0.1.0-rc1 is tagged on the harness-verified build).
3. M1.1-08: D-LIVE-16 column scroll on reopen, D-LIVE-17 SIGKILL escalation, and rendering playlist warnings in the guide (D-LIVE-18).
4. M2 backlog per docs/PLAN.md section 10 (detached/idle mpv first: removes S-03 and the restart-shell limitation).

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
