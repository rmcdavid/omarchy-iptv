# Omarchy IPTV - Project Plan

Owner: Project Manager. Status: v0.1 (2026-09-12). Governs M0 -> M1 -> M1.1 -> Release -> M2.
Companion: docs/STATUS.md (living board). Inputs: docs/PRODUCT.md (vision, US1-US8,
quality bar), docs/OMARCHY-PLUGIN-CONTRACT.md (host facts), docs/QA-ASSETS.md (public
test sources and the multi-group product call).

SLOTS: docs/ARCHITECTURE.md and docs/UX.md did not exist when this plan was written.
Lines tagged `[ARCH-SLOT]` / `[UX-SLOT]` must be reconciled by the Architect / UX
Designer when their docs land; record any change in the STATUS.md decisions log.

## 0. How to read this plan

- Effort is agent work, not calendar time. S = 0.5-2 h, M = 2-5 h, L = 5-10 h.
  One agent-session ~= 3 h of focused work with tool access on this machine.
- Owner roles: PO (Product Owner), PM, ARCH (Architect), UX, FE (Front-end Dev), QA.
- QB1-QB5 = the five quality-bar items from PRODUCT.md, numbered in section 6.
- G0-G5 = QA gates, defined in section 6. Every task names the gate it must pass.
- A task is "done" only when STATUS.md says so with evidence (section 7).

## 1. Phases, sequencing, exit criteria

| Phase | Goal | Exit criteria | Sessions |
|---|---|---|---|
| M0 Foundations | Vision, contract digest, architecture, UX spec, scaffold | `omarchy plugin validate .` passes on scaffold; `scripts/check.sh` runs green (may be mostly stubs); schemas frozen (M0-07) | 3-4 |
| M1 MVP | US1-US8 working on this machine | All M1 tasks done; FE smoke pass (M1-20); check.sh green | 8-12 |
| M1.1 Hardening | QA findings, perf, security, docs | G2 + G3 + G4 passed; zero open P1/P2 defects; QB1-QB5 all verifiable | 4-6 |
| Release | Tag v0.1.0 | Release checklist (section 9) complete; PO acceptance | 1 |
| M2 Backlog | Post-release features | Not planned in detail; section 10 | n/a |

Dependency chain: M0 -> M1 -> M1.1 -> Release. M2 starts only after the tag.

## 2. Assumptions (explicit; override via decisions log)

- A1 Helper interface. Until ARCHITECTURE.md fixes it, tasks assume one stdlib-only
  script `helper.py` with subcommands `fetch`, `epg`, `play <channelId>`, `stop`,
  `next`, `prev`, `status`, writing `~/.cache/omarchy-iptv/{channels.json,epg.json,status.json}`
  and `~/.local/state/omarchy-iptv/state.json` (favorites, recents). `[ARCH-SLOT]`
- A2 mpv lifetime. mpv is spawned by the helper detached from the shell process
  (new session, own process group), with `--input-ipc-server=$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock`
  and `--wayland-app-id=omarchy-iptv`, so a shell hot-reload never kills it. `[ARCH-SLOT]`
- A3 Plugin kinds: `bar-widget` + `overlay`, both `keepLoaded: true`; a `service`
  kind is added only if ARCHITECTURE.md needs a persistent state owner. `[ARCH-SLOT]`
- A4 Settings keys (manifest schema): `playlistUrl` (string), `epgUrl` (string),
  `refreshMinutes` (integer, default 360), `mpvProfile` (string, default "low-latency").
  Extra keys are an ARCH decision. `[ARCH-SLOT]`
- A5 Tests: python `unittest` (no pytest), `node Model.test.js`, `qmltestrunner` for
  `*.spec.qml`. node is dev-only (mise), never a runtime dependency.
- A6 Bar glyph is a Nerd Font television glyph (`U+F0378`, nf-md-television) unless
  UX.md picks another. `[UX-SLOT]`
- A7 QA machine = this machine (Omarchy 4.0.3, Quickshell 0.3.1, one 1366x768 monitor).
  Multi-monitor behaviour cannot be verified here and ships as a documented limitation.
- A8 QA sources per docs/QA-ASSETS.md: iptv-org `countries/us.m3u` (1,475) for live
  QA, `categories/news.m3u` for smoke, `index.m3u` (11,041 entries) for the 10k gate,
  Pluto/Samsung XMLTV gz for EPG. Unit tests use only local files under `tests/fixtures/`.
  A synthetic generator (`tests/fixtures/gen_playlist.py`, `gen_epg.py`) exists for
  offline determinism and for a large-gz EPG the public sources do not provide.
- A9 One FE session works at a time by default. Lanes in section 4 are file-disjoint
  so the PO may spawn a second FE session per lane without merge conflicts.

## 3. Work breakdown structure

### M0 Foundations

| ID | Title | Owner | Deps | Effort | Acceptance criteria | Gate |
|---|---|---|---|---|---|---|
| M0-01 | PRODUCT.md (vision, US1-US8, quality bar) | PO | - | M | File exists, decisions locked, stories enumerated | - |
| M0-02 | OMARCHY-PLUGIN-CONTRACT.md digest | PO | - | M | Facts verified on machine; commands and paths cited | - |
| M0-03 | PLAN.md + STATUS.md | PM | M0-01, M0-02 | M | This file + board; every WBS task in STATUS.md | - |
| M0-04 | ARCHITECTURE.md: file layout, JSON schemas (channels, epg, status, state), helper CLI, mpv IPC contract, threading model, security standards | ARCH | M0-01, M0-02 | L | Each `[ARCH-SLOT]` in this plan resolved or confirmed; schemas have example documents; security standards list is testable (G4 checklist) | - |
| M0-05 | UX.md: overlay layout, key map, all states (loading/empty/error/cached/no-EPG), bar widget states, glyph, vertical-bar fallback | UX | M0-01, M0-02 | M | Every US1-US8 interaction has a screen/state; key map has no conflict with PanelKeyCatcher defaults; `[UX-SLOT]`s resolved | - |
| M0-06 | Scaffold: manifest.json, BarWidget.qml + Overlay.qml stubs, helper.py stub, Model.js stub, tests dirs, scripts/check.sh, LICENSE, README skeleton | ARCH | M0-04 | M | `omarchy plugin validate .` passes; `scripts/check.sh` exits 0; stub overlay opens/closes on this machine via `omarchy-shell shell toggle io.github.rmcdavid.iptv '{}'` | G0 |
| M0-07 | Schema freeze / interface review | PM + ARCH + UX | M0-04, M0-05, M0-06 | S | Decisions-log entry "schemas frozen v1"; changes after this need a log entry and a STATUS note on affected tasks | - |
| M0-08 | QA test plan + fixtures: US->test-case matrix, sample M3U (EXTINF attrs, EXTGRP, semicolon multi-group, synthetic EXTVLCOPT/KODIPROP since iptv-org lacks them), XMLTV plain+gz with tz offsets and unmatched ids, `gen_playlist.py` + `gen_epg.py` (large gz), public sources per docs/QA-ASSETS.md | QA | M0-04 | M | Fixtures under `tests/fixtures/`, no network in unit tests; matrix in `docs/QA.md` (QA-owned file) covers every US with steps and expected result | - |
| M0-09 | QA-ASSETS.md: verified public playlists and EPG sources, multi-group product call | PO | - | S | File exists; URLs verified from this machine | - |

### M1 MVP - Lane A: Python helper (files: helper.py, tests/test_*.py)

| ID | Title | Owner | Deps | Effort | Acceptance criteria | Gate |
|---|---|---|---|---|---|---|
| M1-01 | Helper skeleton: argparse subcommands, XDG paths, atomic JSON writes, `status.json` with error field, stderr logging with URL query redaction | FE | M0-07 | S | `python3 helper.py status` prints JSON per schema; writes are tmp+rename; no traceback on missing config (US1 error state) | G0, G1 |
| M1-02 | M3U parser: `#EXTINF` attributes (tvg-id, tvg-name, tvg-logo, group-title), `#EXTGRP`, `#EXTVLCOPT`, `#KODIPROP`, stable channel ids, group index; `group-title` with `;` -> first group is the display group, full string kept searchable (QA-ASSETS product call) | FE | M1-01 | M | Unit tests pass on fixtures incl. malformed lines and multi-group titles; 11k-entry index fixture parses < 1 s; headers/agent captured as data only (decision 8) | G1 |
| M1-03 | Playlist fetch + cache: URL (http/https, curl or urllib with timeout) or local path; ETag/mtime skip; stale cache kept on failure with `cached: true` + `fetchedAt` | FE | M1-02 | M | US1, US7: offline run leaves old channels.json and sets cached flag; failure reason lands in status.json; never writes inside plugin dir | G1 |
| M1-04 | XMLTV EPG: streaming parse (iterparse) of plain and gzip, tz offsets, restrict to playlist tvg-ids, project now/next window into epg.json; channels without a matching id get no EPG and no error | FE | M1-02 | L | US6: tests for plain, gz, +0000/-0500 offsets, and unmatched ids (Pluto fixture vs iptv-org ids is partial by design); synthetic 200 MB gz stays under ~300 MB RSS and never blocks the shell (separate process); epg.json bounded (now + next N h) | G1 |
| M1-05 | mpv control: spawn exactly one detached mpv with IPC socket, wait-for-socket with backoff, `loadfile ... replace`, `stop`, `quit`, title/media-title set to channel name, `#EXTVLCOPT`/`#KODIPROP` -> mpv argv only, observe `idle-active`/end-file and write playing state to status.json | FE | M1-01 | L | US3, decision 3: two consecutive `play` calls reuse the window; `stop` ends playback; a dead URL sets `lastError` with channel name in status.json within timeout; no `shell=True`, no string interpolation of playlist data | G1, G4 |
| M1-06 | State file: favorites toggle, recents (last 10, de-duplicated, most recent first), atomic write, tolerant of corrupt file | FE | M1-01 | S | US5 unit tests; corrupt state.json -> empty state + warning, not crash | G1 |

### M1 MVP - Lane B: Model.js + QML UI (files: Model.js, Model.test.js, Overlay.qml, BarWidget.qml, *.spec.qml)

| ID | Title | Owner | Deps | Effort | Acceptance criteria | Gate |
|---|---|---|---|---|---|---|
| M1-07 | Model.js: search (name + full group string, case-insensitive, token AND), group list with Favorites pinned first then Recent, filter by display group, bounded display window, prev/next within current group, favorite/recent merge | FE | M0-07 | M | `node Model.test.js` green: search, grouping (multi-group channel listed once under its first group, found by any group token), favorites, recents, prev/next wrap; no ES module syntax; `module.exports` guarded as in dell-power | G1 |
| M1-08 | Overlay shell: PanelWindow recipe, theme tokens only, `open/close/toggle`, `shell.hide(manifest.id)` on Esc/scrim click, PanelKeyCatcher focus on open, `keepLoaded` | FE | M0-06, M0-07 | M | US2: opens via `omarchy-shell shell toggle`, Esc closes, host open-state stays in sync; zero console warnings on open; no hardcoded colors (grep) | G0, G2 |
| M1-09 | Overlay guide: search field, group filter (Tab cycles or sidebar per UX.md), ListView over display window, j/k/arrows/PgUp/PgDn, states loading/empty/error/cached | FE | M1-07, M1-08, M0-08 fixtures | L | US1, US2, US7 visible states match UX.md; with 10k fixture cache open < 150 ms and typing has no visible lag (QB4) | G2, G3 |
| M1-10 | Overlay EPG rows + favorites/recents: "Now: ... until HH:MM" / "Next: ...", `f` toggles favorite, Favorites and Recent groups rendered | FE | M1-09, M1-06 | M | US5, US6: missing EPG shows no row text and never delays open; `f` persists across shell restart | G2 |
| M1-11 | Bar widget: glyph, now-playing label on horizontal bars (hidden when vertical), left = toggle guide, right = stop, scroll = prev/next in current group, middle = refresh, tooltip via `bar.showTooltip` | FE | M0-06, M0-07 | M | US4 all five gestures verified on live bar; label elides at a UX.md width; uses `bar.foreground/barForeground` tokens only | G2 |
| M1-12 | Settings propagation: manifest `barWidget.schema` + defaults, read via `setting()`, pass playlistUrl/epgUrl/refreshMinutes/mpvProfile to helper (env or argv), react to `omarchy bar set` without restart | FE | M0-06 | M | US1: `omarchy bar set io.github.rmcdavid.iptv playlistUrl <url>` triggers a fetch; credentials never printed to console or logs | G2, G4 |
| M1-13 | Refresh scheduler: Timer every `refreshMinutes`, `r` key, middle click, single in-flight fetch (lock), cached hint when stale | FE | M1-03, M1-09, M1-11 | S | US7: two refresh triggers within 1 s produce one helper run; hint appears when status.cached is true | G2 |
| M1-14 | Notifications: stream failure ("IPTV: <channel> failed: <reason>"), fetch failure, via `omarchy-notification-send` argv | FE | M1-05, M1-03 | S | US3, US1: dead-URL fixture raises a notification naming the channel within the helper timeout | G2 |
| M1-15 | Playback wiring end to end: Enter -> helper play -> mpv; FileView on status.json -> bar label; right click -> stop; scroll -> next/prev | FE | M1-05, M1-09, M1-11 | M | US3, US4 on a real public playlist: zap in < 2 s of interaction; switching channel reuses window; only one mpv process (`pgrep -c -f wayland-app-id=omarchy-iptv` == 1) | G2 |
| M1-16 | IpcHandler: `play <id>`, `stop`, `next`, `prev`, `refresh`, `toggle` on target `io.github.rmcdavid.iptv` | FE | M1-15 | S | `omarchy-shell io.github.rmcdavid.iptv stop` works; enables QA scripting | G2 |
| M1-17 | QML unit tests: `BarWidget.spec.qml` (label/elide/click routing with a fake `bar`), `Overlay.spec.qml` (state rendering from fixture JSON) | FE | M1-11, M1-09 | M | `/usr/lib/qt6/bin/qmltestrunner -input <spec>` green; wired into check.sh | G1 |
| M1-18 | README: install (`omarchy plugin add`), settings, keybinding + menu snippets, keyboard map, troubleshooting, uninstall (leaves only cache/state), test commands | FE (UX reviews) | M1-12, M1-15 | M | QB5 every section present; snippets copy-paste verbatim; commands match check.sh | G0 |
| M1-19 | scripts/check.sh green: validate + qmllint (qs modules mapped) + `python3 -m unittest` + `node Model.test.js` + qmltestrunner + hardcoded-color grep | FE | M1-17, M1-18 | S | QB1, QB2: exit 0 on this machine; documented in README | G0, G1 |
| M1-20 | FE smoke on live shell: clone into `~/.config/omarchy/plugins/`, enable, walk US1-US8 once, record evidence in STATUS.md | FE | M1-13 .. M1-19 | S | All eight stories pass once; evidence lines in STATUS.md; hands off to QA | G2 |

### M1.1 Hardening

| ID | Title | Owner | Deps | Effort | Acceptance criteria | Gate |
|---|---|---|---|---|---|---|
| M1.1-01 | Live-shell functional QA: docs/QA.md matrix, real public playlist, every US1-US8 step, defects filed in STATUS.md with severity | QA | M1-20 | L | Matrix fully executed; each row pass/fail with evidence; P1 = story blocked, P2 = degraded, P3 = cosmetic | G2 |
| M1.1-02 | Theme-switch check: `omarchy theme set <x>` across 3+ themes with guide open and closed; console clean | QA | M1-20 | S | QB1, QB3: overlay and bar re-skin without restart; `qs log -p /usr/share/omarchy/shell --tail 100` shows no new warnings | G2 |
| M1.1-03 | Performance check: iptv-org `index.m3u` (11,041 entries) as playlist, open time, typing latency, helper parse time, EPG memory with a synthetic large gz | QA | M1-20, M0-08 | M | QB4: open < 150 ms (measured with timestamps in console or `time` on toggle); no dropped keystrokes; numbers recorded in STATUS.md | G3 |
| M1.1-04 | Security review against ARCHITECTURE.md standards: argv-only execution, no sudo, no eval, no writes in plugin dir, redaction, socket perms in XDG_RUNTIME_DIR, file modes | ARCH | M1-20 | M | G4 checklist all ticked with grep/command evidence; findings filed as defects | G4 |
| M1.1-05 | Fix round 1: all P1/P2 defects from M1.1-01..04 | FE | M1.1-01..04 | L | Each defect closed with commit id and re-test note | G0, G1 |
| M1.1-06 | Regression re-test of failed rows + check.sh | QA | M1.1-05 | M | Zero open P1/P2; P3s listed as known issues in README | G2 |
| M1.1-07 | Docs polish: troubleshooting from real QA failures, known limitations (multi-monitor, vertical bars) | FE + UX | M1.1-06 | S | QB5; README reviewed by UX | G0 |
| M1.1-08 | Dead-stream hardening: `--network-timeout`, reconnect policy, clear bar state after failure | FE | M1.1-01 | S | Failure -> notification + bar returns to idle within timeout; no zombie mpv | G2 |

### Release

| ID | Title | Owner | Deps | Effort | Acceptance criteria | Gate |
|---|---|---|---|---|---|---|
| REL-01 | Clean install test: remove plugin, `git clone` into `~/.config/omarchy/plugins/io.github.rmcdavid.iptv`, enable, set URL, press key, watch | QA | M1.1-06 | S | README path works verbatim from a clean state; US8 | G5 |
| REL-02 | Uninstall test: `omarchy plugin remove <id> --yes` leaves only `~/.cache/omarchy-iptv` and `~/.local/state/omarchy-iptv` | QA | REL-01 | S | `find ~ -path '*omarchy-iptv*'` shows only those two dirs; US8 | G5 |
| REL-03 | Version 0.1.0 in manifest, CHANGELOG entry, final check.sh | FE | REL-02 | S | check.sh green at the release commit | G0 |
| REL-04 | PO acceptance against PRODUCT.md | PO | REL-03 | S | Every US and QB ticked in STATUS.md by PO | - |
| REL-05 | `git tag v0.1.0` and push | PO | REL-04 | S | Tag exists; `omarchy plugin add <url> --enable` at the tag works (re-run REL-01 quickly) | G5 |

### M2 Backlog (not scheduled; sized for planning only)

| ID | Title | Effort | Notes |
|---|---|---|---|
| M2-01 | Xtream Codes URL helper (server/user/pass -> get.php + xmltv.php) | M | Settings schema grows by 3 keys; secrets stay in shell.json |
| M2-02 | Multiple playlists | L | Cache per playlist; group prefix |
| M2-03 | Channel numbers and numeric zap | M | Model.js + key catcher digits |
| M2-04 | Channel logos | M | Download cache with size cap; Image in rows |
| M2-05 | Picture-in-picture via hyprctl float + pin | S | Window rule on `omarchy-iptv` app id |
| M2-06 | Recording via ffmpeg | L | Argv only; disk quota |
| M2-07 | Catch-up / timeshift | L | Provider-specific |
| M2-08 | First-class vertical bar layout | S | UX.md fallback becomes full design |

## 4. Critical path and parallelism

Critical path (each item blocks the next):

```
M0-04 ARCHITECTURE -> M0-06 scaffold -> M0-07 schema freeze
  -> M1-02 M3U parser -> M1-03 fetch/cache -> M1-05 mpv control
  -> M1-15 end-to-end wiring -> M1-20 FE smoke
  -> M1.1-01 QA pass -> M1.1-05 fix round -> M1.1-06 regression
  -> REL-01 clean install -> REL-05 tag
```

Parallel lanes after M0-07 (file-disjoint, see A9):

- Lane A (helper): M1-01 -> M1-02 -> M1-03 / M1-04 / M1-05 / M1-06.
- Lane B (UI): M1-07 -> M1-08 -> M1-09 -> M1-10; M1-11 and M1-12 any time after M0-06.
  Lane B develops against fixture JSON from M0-08, so it never waits on Lane A.
- Lane C (QA prep): M0-08 during M0; docs/QA.md matrix ready before M1-20.
- Join points: M1-13, M1-14, M1-15 need both lanes. M1-17/18/19 follow the join.

During M0: M0-03 (PM), M0-04 (ARCH), M0-05 (UX) run in parallel; M0-06 waits on
M0-04; M0-08 waits on M0-04 for schemas.

During M1.1: M1.1-01, -02, -03 (QA) and M1.1-04 (ARCH) run in parallel, then FE fixes.

## 5. Risk register

L/I = likelihood/impact, 1-3. Owner watches the trigger and updates STATUS.md.

| # | Risk | L | I | Mitigation | Owner |
|---|---|---|---|---|---|
| R1 | Third-party facades (PluginBarApi/PluginShellApi) limit what the widget can reach (no direct Hyprland, no other plugins' state) | 2 | 2 | Use only documented facade calls; M0-06 spike proves toggle/summon/updateEntryInline/showTooltip; anything else goes through the helper or `bar.run` | ARCH |
| R2 | Keyboard focus on layer-shell overlay not delivered (typing goes to the app behind) | 2 | 3 | Copy clipboard/emoji recipe exactly (`WlrKeyboardFocus.Exclusive`, `forceActiveFocus()` on open, `blocked: editor.activeFocus`); verify in M1-08 before building the list | FE |
| R3 | Plugin hot-reload destroys the QML object that owns mpv, killing playback on every save | 3 | 3 | mpv is spawned detached by the helper (A2); QML never owns the mpv process; `keepLoaded: true`; on load, reconnect via socket path and status.json | ARCH |
| R4 | mpv IPC socket races: connect before socket exists, stale socket from a dead mpv, concurrent commands | 3 | 2 | Helper waits for socket with backoff (<= 5 s), probes with `get_property pid` and deletes stale sockets, uses one connection per command with `request_id`, lock file for spawn | FE |
| R5 | 10k-channel playlist stalls the shell (QB4) | 3 | 3 | Parse only in helper; cache pre-sorted with lowercase search keys; QML shows a bounded window (e.g. 200 rows); search debounced; measured in M1.1-03 with fixture from M0-08 | FE |
| R6 | EPG files of hundreds of MB gz blow memory or time | 3 | 2 | Streaming iterparse with element clearing, gzip streamed, filter to playlist tvg-ids, project only now + next N h; EPG never gates guide open (US6); size/time cap with a status.json warning | FE |
| R7 | python3 missing or older on another Omarchy machine | 1 | 3 | python3 is an Omarchy dependency (first-party dropbox `status.py`); target 3.11+ stdlib only; helper checks version and writes a readable error to status.json; README lists the requirement | PM |
| R8 | Dead streams / provider timeouts hang mpv or leave a wrong now-playing label | 3 | 2 | `--network-timeout`, observe `idle-active`/end-file in helper, notification with channel name, bar returns to idle; M1.1-08 | FE |
| R9 | Credentials in shell.json / playlist URLs leak via logs, argv, or notifications | 2 | 3 | shell.json is 0600 (verified); helper redacts query strings in all logs; never echo URLs in notifications; G4 grep for `print(` of URLs; document that argv is visible to the same user | ARCH |
| R10 | Quickshell / qs.Ui API drift between Omarchy versions breaks the plugin | 2 | 2 | Pin tested versions in README; isolate host calls in the two entry files; check.sh runs qmllint against the installed shell; `omarchy plugin update` re-test on each Omarchy release | ARCH |
| R11 | Nerd Font glyph missing or renders as tofu on other setups | 1 | 1 | JetBrains Mono Nerd is a hard Omarchy dependency and present here; use `Style.font.family`; fallback text "TV" behind a `CONVENTION-EXCEPTION` comment | UX |
| R12 | Multi-monitor: overlay opens on the wrong screen or on all screens | 2 | 2 | Follow the clipboard plugin's screen choice; cannot verify here (A7); ship as documented limitation with an M1.1 best-effort fix; ask a multi-monitor user to test before M2 | FE |
| R13 | Schema churn after parallel lanes start causes rework | 2 | 2 | M0-07 freeze gate; changes require a decisions-log entry plus a STATUS note on affected tasks | PM |
| R14 | Public playlist used for QA changes or goes offline, making QA flaky | 3 | 1 | Fixtures are the source of truth for unit tests; public lists (docs/QA-ASSETS.md) are for G2/G3 human runs; `news.m3u` and the synthetic generator are the fallbacks; many iptv-org streams are dead by design, which is useful for R8 testing, not a defect | QA |
| R15 | Duplicate timers/fetches after hot-reload or multiple bar instances | 2 | 2 | `allowMultiple: false`; helper lock file for fetch; Timer lives in one keepLoaded object | FE |
| R16 | `#EXTVLCOPT`/`#KODIPROP` headers not honoured by mpv, so some streams fail | 2 | 2 | Map http-user-agent, http-referrer, http-header-fields to mpv argv; unsupported keys logged and ignored; documented in troubleshooting | FE |

## 6. QA gates and Definition of Done

Quality bar from PRODUCT.md, numbered:

- QB1 `omarchy plugin validate .` passes; qmllint clean with qs modules mapped; no console warnings on load or theme switch.
- QB2 Unit tests cover parsers (M3U attrs, EXTGRP, EXTVLCOPT, KODIPROP; XMLTV plain/gz/tz) and model logic (search, grouping, favorites, recents); README documents the commands; all green.
- QB3 Manual QA on the live shell on this machine: install, enable, every story with a real public playlist; `omarchy theme set <x>` re-skins without restart.
- QB4 Overlay opens < 150 ms with a 10k-channel cache; typing stays responsive.
- QB5 README covers install, settings, keybinding and menu snippets, keyboard map, troubleshooting, uninstall.

Gates (a task passes its gate when every listed check succeeds):

| Gate | Name | Checks (command or manual step) |
|---|---|---|
| G0 | Static | `omarchy plugin validate .` exit 0; `mkdir -p /tmp/qmlroot/qs && ln -sfn /usr/share/omarchy/shell/Commons /tmp/qmlroot/qs/Commons && ln -sfn /usr/share/omarchy/shell/Ui /tmp/qmlroot/qs/Ui && /usr/lib/qt6/bin/qmllint -I /tmp/qmlroot -I /usr/lib/qt6/qml *.qml` shows only the baseline warnings recorded in README; `grep -nE '#[0-9a-fA-F]{6}' *.qml` returns only lines with `CONVENTION-EXCEPTION`; `scripts/check.sh` exit 0 |
| G1 | Unit | `python3 -m unittest discover -s tests` green; `node Model.test.js` green; `/usr/lib/qt6/bin/qmltestrunner -input <spec>` green for each spec |
| G2 | Live shell | Plugin cloned (no symlink) into `~/.config/omarchy/plugins/io.github.rmcdavid.iptv`, `omarchy plugin enable io.github.rmcdavid.iptv`, `omarchy-shell shell rescanPlugins`; the docs/QA.md rows for the task pass; `qs log -p /usr/share/omarchy/shell --tail 100` has no new warnings; `omarchy theme set <x>` re-skins |
| G3 | Performance | iptv-org `index.m3u` (11,041 entries) set as `playlistUrl`, or the synthetic 10k fixture when offline; open time < 150 ms (console timestamp on `open()` vs first frame, or `time omarchy-shell shell toggle ...` minus baseline); typing 20 chars shows no visible lag; helper parse < 1 s; EPG large-gz run stays under the memory cap in ARCHITECTURE.md `[ARCH-SLOT]` |
| G4 | Security | `grep -rn "sudo\|shell=True\|bash -c\|eval(" .` returns nothing outside tests/docs; every `Process`/`execDetached`/`subprocess` call uses an argv list; no runtime writes inside the plugin dir (`find <plugindir> -newer manifest.json` after a session is empty); logs show redacted URLs; socket under `$XDG_RUNTIME_DIR` (0700 dir) |
| G5 | Release | Clean `git clone` install per README; uninstall leaves only cache and state dirs; tag installs with `omarchy plugin add <url> --enable` |

Definition of Done for M1 (all verifiable):

- [ ] QB1: G0 checks pass on the release commit; theme switch produces no warnings (G2 step).
- [ ] QB2: G1 checks pass; README "Testing" section lists the three commands verbatim.
- [ ] QB3: docs/QA.md matrix for US1-US8 executed on this machine with a public playlist, all rows pass; theme-switch row passes.
- [ ] QB4: G3 numbers recorded in STATUS.md and within limits.
- [ ] QB5: README sections present: Install, Settings, Keybinding, Menu entry, Keyboard map, Troubleshooting, Uninstall, Testing, Known limitations.
- [ ] G4 checklist ticked by ARCH with command output pasted in STATUS.md.
- [ ] US8: REL-01 and REL-02 pass.

Defect severity: P1 blocks a user story; P2 degrades one; P3 cosmetic. Release needs zero open P1/P2.

## 7. Handoff protocol (STATUS.md is the contract)

When a role finishes a task it must update its STATUS.md row and append under
"Handoff notes" a block with:

1. Task ID and new state (`review` for FE work needing QA; `done` only after the gate passed).
2. Files changed (paths, absolute or repo-relative).
3. Commands run and their result (exit code, key output line, numbers for perf).
4. Open issues, deviations from ARCHITECTURE.md/UX.md, and any assumption made.
5. For QA: defects as `D-<n>` rows with severity, repro steps, and the task they belong to.

Rules:

- The FE dev does not start a task whose `Deps` are not all `done` in STATUS.md.
  If a dependency is `review`, the FE dev may prepare but must not mark the new task `doing`.
- `blocked` rows must name the blocker in the Blockers section with an owner.
- Schema or interface changes after M0-07 need a decisions-log entry before code changes.
- PM re-plans when: a task doubles its effort band, a P1 defect stays open for two sessions,
  or an `[ARCH-SLOT]`/`[UX-SLOT]` resolution changes a dependency.
- Nobody edits files under `/usr/share/omarchy` or `~/.config` except the QA install
  steps in G2/G5 (plugin dir clone/remove, `omarchy bar set`, `omarchy plugin enable/disable`).

## 8. Session plan (ordered, with dependencies)

| Session | Work | Needs |
|---|---|---|
| S1 (now) | M0-03 PM, M0-04 ARCH, M0-05 UX in parallel | M0-01, M0-02 done |
| S2 | M0-06 scaffold, M0-08 fixtures, M0-07 freeze | M0-04, M0-05 |
| S3-S4 | Lane A: M1-01, M1-02, M1-03, M1-06 | M0-07 |
| S3-S5 | Lane B: M1-07, M1-08, M1-09, M1-11, M1-12 (second FE session if spawned) | M0-07, M0-08 |
| S5-S6 | M1-04 EPG, M1-05 mpv, M1-10 | Lanes A/B progress |
| S7-S8 | Join: M1-13, M1-14, M1-15, M1-16 | M1-05, M1-09, M1-11 |
| S9-S10 | M1-17, M1-18, M1-19, M1-20 | Join done |
| S11-S13 | M1.1-01..04 in parallel (QA x3, ARCH x1) | M1-20 |
| S14-S15 | M1.1-05 fixes, M1.1-08, M1.1-06 regression, M1.1-07 docs | QA findings |
| S16 | REL-01..05 | M1.1-06 |

## 9. Release checklist (v0.1.0)

- [ ] `omarchy plugin validate .` exit 0 at HEAD.
- [ ] `scripts/check.sh` exit 0 at HEAD (G0 + G1).
- [ ] `omarchy plugin remove io.github.rmcdavid.iptv --yes`; `git clone <url> ~/.config/omarchy/plugins/io.github.rmcdavid.iptv`; `omarchy plugin enable io.github.rmcdavid.iptv`; `omarchy bar set io.github.rmcdavid.iptv playlistUrl <url>`; press SUPER+SHIFT+T; play a channel (REL-01).
- [ ] Uninstall leaves only `~/.cache/omarchy-iptv` and `~/.local/state/omarchy-iptv` (REL-02).
- [ ] README snippets (keybinding, menu) copied verbatim into the user files and working.
- [ ] manifest.json `version` = `0.1.0`; CHANGELOG has a 0.1.0 entry.
- [ ] STATUS.md: all M1/M1.1 rows `done`, zero open P1/P2, G3 numbers recorded, G4 ticked.
- [ ] PO acceptance row REL-04 `done`.
- [ ] `git tag -a v0.1.0 -m "Omarchy IPTV 0.1.0"` and push; re-run `omarchy plugin add <url> --enable` at the tag.

## 10. M2 backlog ordering (proposal for the PO)

1. M2-01 Xtream helper (most requested by paid-provider users; small).
2. M2-03 channel numbers / numeric zap (keyboard-first value).
3. M2-05 PiP (one window rule).
4. M2-04 logos, M2-08 vertical bar, M2-02 multi-playlist, M2-06 recording, M2-07 catch-up.
