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
| M1.1-01 | Live-shell functional QA (docs/QA.md matrix) | QA | doing | started 2026-09-12 on main f03fef2 |
| M1.1-02 | Theme-switch check | QA | doing | part of the live pass |
| M1.1-03 | Performance check (10k playlist, large EPG) | QA | doing | part of the live pass |
| M1.1-04 | Security review (G4) | ARCH | doing | started 2026-09-12 on main f03fef2, report in docs/SECURITY-REVIEW.md |
| M1.1-05 | Fix round 1 (P1/P2) | FE | todo | Deps: M1.1-01..04 |
| M1.1-06 | Regression re-test | QA | todo | Deps: M1.1-05 |
| M1.1-07 | Docs polish + known limitations | FE+UX | todo | Deps: M1.1-06 |
| M1.1-08 | Dead-stream hardening | FE | todo | Deps: M1.1-01 |

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
| - | - | - | none yet | - |

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

## Blockers

| Since | Task | Blocker | Owner | Unblock action |
|---|---|---|---|---|
| - | - | none | - | - |

## Next up

First three tasks for the FE dev once M0 is complete (M0-06 and M0-07 `done`):

1. M1-01 Helper skeleton (S): argparse subcommands, XDG paths, atomic JSON writes,
   `status.json` with a readable error field, redacted logging. Unlocks all of Lane A.
2. M1-07 Model.js + Model.test.js (M): search, grouping with Favorites/Recent pinned,
   group filter, bounded display window, prev/next in group. Pure logic; unlocks Lane B.
3. M1-02 M3U parser + tests (M): `#EXTINF` attributes, `#EXTGRP`, `#EXTVLCOPT`,
   `#KODIPROP`, stable ids; must parse the 10k fixture from M0-08 in under 1 s.

Then M1-08 (overlay shell, verifies keyboard focus early, risk R2) and M1-03 (fetch/cache).

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
