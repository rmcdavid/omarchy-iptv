# Omarchy IPTV - M2 Plan (rest of M2: v0.3.0 and v0.4.0)

Owner: Project Manager. Status: v0.1 (2026-09-13). Governs everything after
the v0.2.0 tag. Companion to `docs/PLAN.md` (M0/M1 plan: effort bands, gates
G0-G5, severity scale, handoff protocol - all carried forward unchanged) and
`docs/STATUS.md` (the board). Scope and ranking come from `docs/PRODUCT.md`
section "M2 scope decision".

SLOT: `docs/ARCHITECTURE-PLAYER.md` is being written now. M2-02 is a black
box in this plan: lane boundaries, dependencies and gates only. Every line
tagged `[PLAYER-SLOT]` is owned by that document; do not duplicate it here.

## 0. How to read

- Effort is agent work, not calendar time. S = 0.5-2 h, M = 2-5 h, L = 5-10 h.
  One agent-session is about 3 h.
- Roles: PO, PM, ARCH, UX, FE, QA (PLAN.md section 0).
- Gates G0 static, G1 unit, G2 live shell, G3 performance, G4 security,
  G5 release. Definitions: PLAN.md section 6. They are unchanged.
- Severity: P1 blocks a story, P2 degrades one, P3 cosmetic. Release needs
  zero open P1/P2.
- Handoff protocol: PLAN.md section 7 (STATUS.md row + handoff block with
  files, commands, numbers, deviations). Unchanged.

## 1. What shipped (orientation for a reader who never saw M1)

| Release | Scope | Gate evidence at the release commit | QA evidence |
|---|---|---|---|
| v0.1.0 (502f4b3) | M1 MVP: US1-US8, bar widget + guide overlay + service, stdlib Python helper, one mpv over JSON IPC | validate exit 0; 299 node checks, 144 python tests, 21 qml spec; qmllint 0 errors | 174 cases, harness 140 pass / 7 fail / 12 blocked-live / 15 not-run; live-shell pass on the reference machine; security review 8 findings (1 P2, 7 P3) all fixed; D-LIVE-01..19 filed, 2 P2 |
| v0.2.0 (d50e364) | M2-01 Sources: in-guide playlist entry, source history, per-source caches, Xtream form, state schema v2 + migration | validate exit 0; 653 node checks, 199 python tests, 29 qml spec; qmllint 0 errors | 196 `SRC-` cases; first pass 181/196 (D-SRC-01..10, 3 P2); regression 190/196, 0 fail, 10/10 verified fixed, 0 regressions; privacy sweep clean |

Performance now (all inside budget): helper parses 11,041 channels in 530 ms;
guide opens on the 10k cache in 71 ms median (budget 150 ms); warm source
switch 17 ms median, first cold switch to a source 352 ms; filter on 11k rows
6.7 ms worst; 41 MB gz EPG in 2.9 s at 60 MB RSS.

Open defects: **1**, `D-LIVE-19` (P3: clearing `playlistUrl` at runtime draws
the old list under the "No playlist configured" text). Zero open P1/P2.

Not yet closed from v0.2.0: the installed copy on the reference machine is
still v0.1.0 pointing at the local repo, and the live-shell runbook
(`docs/QA-SOURCES.md` section 9) has not been executed. See phase P0.

Observed phase costs, for sizing: a full feature QA pass of ~190 cases takes
about one agent-session (48 min for M2-01, 58 min for M1); a regression pass
takes about half (27-36 min). Design + UX + reconciliation for M2-01 cost 32
product-owner rulings (SR1-SR32) across two rounds.

## 2. Phases

| # | Phase | Entry criteria | Exit criteria | Sessions |
|---|---|---|---|---|
| P0 | Close v0.2.0 on the live machine | v0.2.0 tagged; user grants display time | Installed copy on v0.2.0; `origin` re-pointed to GitHub (SR30); QA-SOURCES section 9 runbook executed with evidence in QA-RESULTS.md; D-LIVE-19 fixed or accepted in README | 1 |
| P1 | M2-02 detached player | `docs/ARCHITECTURE-PLAYER.md` accepted by PO; P0 not required | `omarchy restart shell` leaves playback running; no stream URL in `ps` for any channel; S-03 closed; QA-PLAYER pass with 0 open P1/P2; G1+G2+G4 green | 4-6 |
| P2 | M2-03 channel numbers and numeric zap | P1 merged (Model.js/Guide.qml free); UX spec + PO ruling batch accepted | Digits select, timeout commits, unknown number reports it; NUM- matrix executed; 0 open P1/P2; G1+G2+G3 green | 3-4 |
| P3 | M2-05 picture in picture | P1 done (detached window exists); P2 merged (Guide.qml/Model.js free) | PiP toggles float+pin+geometry on the player window and restores; still exactly one window; PIP- matrix executed on the live shell | 2 |
| P4 | Release v0.3.0 | P1+P2+P3 done; 0 open P1/P2 | Section 9 checklist complete; PO acceptance; tag pushed; GitHub release; `omarchy plugin update` verified on the installed copy | 1 |
| P5 | v0.4.0: M2-04 logos + M2-08 vertical bar | v0.3.0 tagged | Logos cached per source under a cap with the open budget intact; bar renders correctly in all four positions; 0 open P1/P2; tag v0.4.0 | 3-5 |

Deferred with no date: M2-06 recording, M2-07 catch-up (PRODUCT.md rank 6).

## 3. Assumptions (explicit; override via the STATUS.md decisions log)

- A1 `docs/ARCHITECTURE-PLAYER.md` fixes the player's process model, socket
  lifetime, reattach rules and file-by-file work split. This plan names only
  the lane boundary and the gate. `[PLAYER-SLOT]`
- A2 M2-02 changes `Model.buildMpvArgv` (Model.js:1169) and `Service.qml`
  `mpvProc`. That is why M2-02 and M2-03 cannot run concurrently by default
  (section 5).
- A3 The helper already parses `tvg-chno` into `channel.chno`
  (`bin/omarchy-iptv:684`) and `tvg-logo` into `channel.logo` (:681).
  Model.js uses neither yet. M2-03 and M2-04 consume what is already there;
  no schema shape change, so no new freeze gate.
- A4 Digits are reserved and currently ignored in list mode (UX.md 3.1 row
  `0`-`9`, Guide.qml:749). M2-03 claims them in list mode only; search mode
  keeps digits literal.
- A5 PiP is driven with `hyprctl dispatch ...` argv, the same shape as
  `Model.focusPlayerArgv()` (Model.js:1195). No new process class.
- A6 QA machine is unchanged: one output eDP-1 1366x768, Omarchy 4.0.3,
  Quickshell 0.3.1, Hyprland 0.56.2, mpv 0.41. Multi-monitor stays a
  documented limitation.
- A7 Lanes run in separate git worktrees. The PO merges. Merge order is
  fixed per wave in section 5.
- A8 One lane at a time holds the display. Every other lane is
  headless-only (section 10, rule 2).

## 4. Work breakdown

### M2-02 detached player (lane boundaries only; internals in ARCHITECTURE-PLAYER.md)

| ID | Title | Owner | Deps | Effort | Acceptance (user-visible) | Gate |
|---|---|---|---|---|---|---|
| M2-02-00 | `docs/ARCHITECTURE-PLAYER.md`: process model, socket lifetime, reattach, file-by-file plan, lane split | ARCH | - | L | Every `[PLAYER-SLOT]` here resolved; PO accepts | - |
| M2-02-01 | Lane PA: argv + helper player lifecycle | FE | 00 | L | Playing a channel puts no stream URL on any command line: `ps -ww -C mpv \| grep -c '://'` is 0 while playing, including the first channel | G1, G4 |
| M2-02-02 | Lane PB: Service reattach + harness verbs | FE | 00 | L | After `omarchy restart shell` the channel is still playing and the bar shows it again within 2 s; stop, zap and the health check still work | G1, G2 |
| M2-02-03 | Lane PC: `docs/QA-PLAYER.md` + fixtures | QA | 00 | M | Matrix covers restart, orphan reaping, double launch, stale socket, SIGTERM/SIGKILL ladder, S-03 | - |
| M2-02-04 | Integration: shims removed, contract proven | FE | 01, 02 | M | Repo grep finds 0 lane shims; `scripts/check.sh` green | G0, G1 |
| M2-02-05 | QA pass + fix round | QA + FE | 03, 04 | L | Every PLAYER- case pass or defect-linked; 0 open P1/P2; README/CHANGELOG limitation "playback dies with restart shell" deleted with evidence | G2, G3, G4 |

### M2-03 channel numbers and numeric zap

| ID | Title | Owner | Deps | Effort | Acceptance (user-visible) | Gate |
|---|---|---|---|---|---|---|
| M2-03-01 | UX spec: number-entry overlay, digit timeout, unknown-number copy, updated key map | UX | - | S | Every digit state has a screen and copy; no conflict with search mode or `PanelKeyCatcher` | - |
| M2-03-02 | PO ruling batch NR1..NRn (one round, not per question): chno source of truth, duplicate numbers, missing numbers, timeout in ms, digits in search mode, ordering by number, IPC verb name | PO | 01 | S | Rulings appended to this file and mirrored in the STATUS.md decisions log | - |
| M2-03-03 | Helper: normalize `chno`, duplicate and blank policy, number stats in `playlist-status.json` | FE, lane N2 | 02 | S | A playlist with `tvg-chno` shows its numbers in the guide; a playlist without them behaves exactly as today | G1 |
| M2-03-04 | Model.js: number index, `lookupChno`, digit-buffer reducer (append, backspace, timeout commit, cancel), `numberEntry` view fields, unknown reason | FE, lane N1 | 02 | M | `node tests/Model.test.js` covers 1-4 digits, leading zeros, duplicates, unknown, timeout commit, Esc cancel | G1 |
| M2-03-05 | Guide.qml: digit capture in list mode, entry overlay, commit/cancel, number column, footer hint | FE, lane N1 | 04 | M | In list mode typing `1 0 2` plays channel 102 when the timeout fires; Esc cancels; `9 9 9` shows "No channel 999" and plays nothing | G2 |
| M2-03-06 | Service.qml + IPC: `playNumber(n)`, IPC verb, harness verb | FE, lane N2 | 04 | S | `omarchy-shell io.github.rmcdavid.iptv number 102` plays channel 102 | G2 |
| M2-03-07 | QA: `docs/QA-NUMBERS.md`, harness pass, fix round | QA + FE | 05, 06 | M | NUM- matrix executed; open budget and 10k filter numbers unchanged; 0 open P1/P2 | G2, G3 |

### M2-05 picture in picture

| ID | Title | Owner | Deps | Effort | Acceptance (user-visible) | Gate |
|---|---|---|---|---|---|---|
| M2-05-01 | PO + UX ruling: corner, size, key, behaviour on stop/zap/guide-open, restore semantics | PO + UX | M2-02-05 | S | Geometry and copy fixed in writing before code | - |
| M2-05-02 | Service.qml: `togglePip()` over `hyprctl` argv, pip state, restore on stop | FE, lane V2 | 01 | S | The player window floats, pins and moves to the chosen corner at the chosen size; toggling again restores it; still exactly one window | G2, G4 |
| M2-05-03 | Guide.qml + BarWidget.qml + Model.js: `p` key, footer hint, bar action, glyph state | FE, lane V1 | 01 | S | `p` in the guide toggles PiP and the hint says so; the bar exposes the same action | G2 |
| M2-05-04 | `contrib/windows.lua` + README section | FE | 02 | S | The documented Hyprland rule pastes in verbatim and works | G0 |
| M2-05-05 | QA live pass (holds the display) | QA | 02, 03, 04 | M | PIP- cases pass on the live shell; theme switch and guide open unaffected; no second window at any point | G2 |

### v0.4.0 - M2-04 channel logos

| ID | Title | Owner | Deps | Effort | Acceptance (user-visible) | Gate |
|---|---|---|---|---|---|---|
| M2-04-01 | PO ruling: contacting third-party logo hosts at all, default value of the setting, byte cap, per-source directory, scheme/content-type allowlist | PO | - | S | Ruling written; README privacy sentence drafted | - |
| M2-04-02 | UX: row with logo, placeholder, vertical rhythm, vertical-bar interaction | UX | 01 | S | Each row state has a screen | - |
| M2-04-03 | Helper: `logos` fetch into `sources/<key>/logos/`, size cap, atomic 0600, no fetch without a configured playlist | FE, lane L2 | 01 | M | With the setting on, rows show logos after a refresh; with it off no request is ever made (`journalctl`/network check) | G1, G4 |
| M2-04-04 | Model.js: logo path resolution, setting clamp | FE, lane L1 | 01 | S | `node tests/Model.test.js` covers missing, oversized, non-image, and absent-logo channels | G1 |
| M2-04-05 | Guide.qml: async `Image` in rows, placeholder glyph, budget guard | FE, lane L1 | 04 | M | Guide still opens under 150 ms with the 10k cache and logos on | G2, G3 |
| M2-04-06 | Manifest schema key + README privacy section | FE | 03 | S | `omarchy plugin validate .` exit 0; README states which hosts are contacted | G0 |
| M2-04-07 | QA: LOGO- cases, open-budget re-check, privacy sweep | QA | 03-06 | M | Cap enforced, per-source directory, 0 credential leaks, budget held | G2, G3, G4 |

### v0.4.0 - M2-08 first-class vertical bar

| ID | Title | Owner | Deps | Effort | Acceptance (user-visible) | Gate |
|---|---|---|---|---|---|---|
| M2-08-01 | UX: vertical layout spec for all four bar positions | UX | - | S | Screens for idle, playing, error in each position | - |
| M2-08-02 | BarWidget.qml: vertical layout replaces the glyph-only fallback | FE, lane B1 | 01 | S | On a vertical bar the widget shows more than the glyph and does not clip | G0, G2 |
| M2-08-03 | QA: four positions on the live shell | QA | 02 | S | BAR-V cases pass in top/bottom/left/right; README limitation removed | G2 |

## 5. Lanes, file ownership, and what must serialize

The three contention files are `Model.js` (124 KB), `Guide.qml` (123 KB) and
`Service.qml` (80 KB). Each has exactly ONE owning lane per wave. A lane that
edits a file it does not own is rejected at merge, no exceptions.

| Wave | Lane | Owns (writes) | Must not touch | Lands |
|---|---|---|---|---|
| P1 M2-02 | PA (argv + helper) | `Model.js`, `bin/omarchy-iptv`, `tests/Model.test.js`, `tests/Model.spec.qml`, `tests/test_*.py`, `tests/fixtures/player-argv.json` (authored here) | `Service.qml`, `Guide.qml`, harness | 1st |
| P1 M2-02 | PB (service + harness) | `Service.qml`, `scripts/dev-harness/*` | `Model.js`, `Guide.qml`, `bin/omarchy-iptv` | 2nd |
| P1 M2-02 | PC (QA) | `docs/QA-PLAYER.md`, `tests/fixtures/qa-player/` | all code | anytime |
| P2 M2-03 | N1 (model + guide) | `Model.js`, `Guide.qml`, `tests/Model.test.js`, `tests/Model.spec.qml`, `tests/fixtures/chno.json` (authored here) | `Service.qml`, `bin/omarchy-iptv`, harness | 1st |
| P2 M2-03 | N2 (helper + service) | `bin/omarchy-iptv`, `Service.qml`, `tests/test_playlist.py`, `scripts/dev-harness/*` | `Model.js`, `Guide.qml` | 2nd |
| P2 M2-03 | N3 (QA) | `docs/QA-NUMBERS.md`, `tests/fixtures/qa-numbers/` | all code | anytime |
| P3 M2-05 | V1 (UI) | `Guide.qml`, `BarWidget.qml`, `Model.js`, `tests/Model.test.js` | `Service.qml`, helper, harness | 1st |
| P3 M2-05 | V2 (service + docs) | `Service.qml`, `scripts/dev-harness/*`, `contrib/windows.lua`, `README.md` | `Model.js`, `Guide.qml` | 2nd |
| P5 M2-04 | L1 (model + guide) | `Model.js`, `Guide.qml`, `tests/Model.test.js` | `BarWidget.qml`, helper, `Service.qml` | 1st |
| P5 M2-04 | L2 (helper + service) | `bin/omarchy-iptv`, `Service.qml`, `manifest.json`, `tests/test_*.py`, harness | `Model.js`, `Guide.qml`, `BarWidget.qml` | 2nd |
| P5 M2-08 | B1 (bar) | `BarWidget.qml`, `docs/UX.md` bar sections | everything else | anytime |

Concurrency rules:

- CONCURRENT, inside a wave: the two code lanes plus the QA/doc lane. They
  are file-disjoint. The first lane lands first because the second calls its
  functions (the M2-01 SR10 rule, which worked).
- CONCURRENT, across waves: `M2-04` (lanes L1/L2) and `M2-08` (lane B1) in
  v0.4.0. `BarWidget.qml` is disjoint from `Model.js`/`Guide.qml`/helper, so
  these two features are the only pair in the remaining M2 work that can run
  at the same time.
- SERIALIZE: `M2-02`, `M2-03` and `M2-05` waves, in that order. The forcing
  files are `Model.js` (M2-02 changes `buildMpvArgv`, M2-03 adds the number
  index, M2-05 adds the PiP argv), `Guide.qml` (M2-03 digit entry, M2-05 key
  and hint) and `Service.qml` (all three). M2-05 additionally has a real
  functional dependency on M2-02.
- ESCAPE HATCH, if the PO wants M2-03 in parallel with M2-02: M2-02 must
  give up `Model.js` entirely (player argv moves to a new `Player.js` owned
  by lane PA) and give up `Guide.qml` (no footer copy change in P1). Declare
  that in the lane brief or do not attempt it.
- QA holds the display for a live pass. No other lane runs while it does.

## 6. Critical path

```
P0 close v0.2.0 live (display)     [parallel with M2-02-00, different resource]

M2-02-00 ARCHITECTURE-PLAYER.md
  -> M2-02-01 lane PA (Model.js + helper)      [PC QA plan runs alongside]
  -> M2-02-02 lane PB (Service.qml + harness)
  -> M2-02-04 integration, shims removed
  -> M2-02-05 QA pass + fix round
  -> M2-03-04 Model.js number index -> M2-03-05 Guide.qml digit entry
     [M2-03-03 / M2-03-06 lane N2 concurrent]
  -> M2-03-07 QA pass + fix round
  -> M2-05-02 Service PiP -> M2-05-05 QA live pass
  -> REL3-01..09 v0.3.0 tag and release
  -> v0.4.0: M2-04 (L1 then L2) || M2-08 (B1) -> QA -> v0.4.0 tag
```

Longest chain: the design doc, then three serialized feature waves, then the
release. M2-02 is the only item whose slip moves everything: M2-05 needs it
functionally and M2-03 needs `Model.js` back. The two cheapest ways to pull
the path in are (a) run the escape hatch in section 5 so M2-03 overlaps
M2-02, and (b) start `docs/QA-PLAYER.md` and the UX spec for M2-03 on day
one, since neither touches code.

## 7. Risk register

L/I = likelihood/impact, 1-3. Every entry is drawn from something that
actually happened in M1 or M2-01.

| # | Risk | L | I | Mitigation | Owner |
|---|---|---|---|---|---|
| MR1 | A `keepLoaded` service does not hot-reload, so a `Service.qml` change looks like it landed but the running shell is still on the old code (README Troubleshooting; QA-SOURCES 9.2 had to restart the shell after `omarchy plugin update`) | 3 | 2 | Every lane brief that touches `Service.qml` states "verify only after `omarchy restart shell`"; the QA runbook restarts the shell before the first assertion; harness runs kill and restart quickshell by PID between scenarios | FE |
| MR2 | An agent starts a harness/QA run in the background and ends its turn waiting for it, leaving the task half done and the evidence unwritten | 3 | 2 | Section 10 rule 4: finish in the foreground. Harness runs use `run.sh --timeout N` or are polled to completion inside the same turn; no session ends with a pending background job | PM |
| MR3 | The idle lock (hyprlock) or a focus change swallows automated keystrokes, or worse, the keystrokes land in the wrong window (`h06` leaked `Tab o x Return` to the desktop before the key guard existed, QA-RESULTS R9/O13) | 2 | 3 | The `key()` helper refuses to type while `pgrep -x hyprlock` matches and while the target reports `opened: false` (already implemented in the qa5 scripts); that guard is a precondition for any new QA script | QA |
| MR4 | Validator/logic parity drift between `Model.js` and the Python helper (SRC-DEC-05 found port, BOM, zero-width and backslash disagreements; fixed by SR15 and commit 60a85dc) | 3 | 2 | One shared JSON fixture per shared rule, authored by the lane that lands first; both implementations run it in `scripts/check.sh`; parity is a gate, never a follow-up | ARCH |
| MR5 | Shims written so a lane can build before its dependency lands are still there at merge (M2-01 needed commits `cc40ee1` "shims swapped" and `f31c2f8` "0 lane-1 shims") | 2 | 3 | Integration task in every wave (M2-02-04 and equivalents) whose acceptance is a grep showing zero shims; PO does not merge a wave without it | PO |
| MR6 | Spec-versus-spec disagreements stall a lane waiting for a ruling (M2-01 needed 32 rulings, SR1-SR32, in two rounds) | 3 | 2 | Ruling batches are a named task before coding (M2-03-02, M2-05-01, M2-04-01); questions are raised in ONE numbered batch per wave, not one at a time; ARCH doc is authoritative for data/process, UX doc for interaction | PO |
| MR7 | Display contention: one monitor, one keyboard, one clipboard. Two agents driving `wtype`/`grim`/mpv at once produce garbage evidence and can type into the user's own windows | 3 | 3 | Exactly one lane holds the display at a time (section 5); every other lane brief forbids `wtype`, `grim`, `hyprctl dispatch/reload/keyword`, `omarchy theme set`, and opening any window; the harness runs on a scratch `XDG_RUNTIME_DIR` | PM |
| MR8 | A live pass damages the user's real state: `shell.json`, `state.json` with their favorites/recents, the keybinding and menu rows, the installed clone | 2 | 3 | QA-SOURCES 9.1/9.7 pattern is mandatory: snapshot block first (`shell.json`, `state.json`, cache listing + sha, plugin HEAD and origin), undo block last; the pass names its evidence directory before it starts | QA |
| MR9 | Cold-path performance on large playlists. The first switch to a 10k source cost 352 ms against a 17 ms warm median (O4); the number index and the logo path both add work to `prepareChannels` | 3 | 2 | PERF cases re-run in every wave's QA pass against the 10k fixture; the prepared-channels LRU already exists; a wave that adds per-channel work must show the open budget (150 ms) and the switch median unchanged | FE |
| MR10 | URL redaction regresses when a new sink appears. It has happened twice (D-LIVE-03 raw helper sentence, D-SRC-10 previous source's credentials attached to a new record) | 2 | 3 | Every new sink (number overlay, PiP notification, logo error, player reattach log) is added to the privacy sweep in the same commit; the sweep is `grep -c '://'` over IPC status, tooltip, notifications log, console and screenshots and must be 0 | ARCH |
| MR11 | A detached player becomes an orphan, or two players run at once, across shell restarts and crashes. M1 already saw a wedged mpv that ignored SIGTERM (D-LIVE-17) and a 6.6 s dead window after the health-check restart (D-LIVE-15) | 3 | 3 | `[PLAYER-SLOT]`: the design doc owns the lock/socket/reattach rules; QA-PLAYER must cover stale socket, double launch, orphan after a crash, and the SIGTERM-then-SIGKILL ladder; acceptance includes a process count of exactly 1 | ARCH |
| MR12 | Hyprland dispatch surface for PiP drifts or behaves differently per version; geometry cannot be verified on a second monitor here | 2 | 2 | argv only, verbs isolated in `Service.qml`; version pinned in README as for Quickshell; multi-monitor stays a documented limitation (PLAN.md A7) | FE |
| MR13 | Logos are the first feature that contacts third-party hosts, on the provider's CDN, with the user's IP | 2 | 3 | PO ruling M2-04-01 before any code; setting-gated; no request without a configured playlist; per-source directory with a byte cap; README names the behaviour | PO |
| MR14 | `Guide.qml` lint/complexity creep: qmllint warnings went 95 -> 197 during M2-01, and the file is now 123 KB | 3 | 1 | Warning counts recorded in every QA header as they are today; a wave that raises the count by more than 20 explains it in its handoff; extraction into a second QML file is an option the PO can call | FE |
| MR15 | Gate runtime creep: `check.sh` went 11.5 s -> 21.9 s -> about 30 s, dominated by the 199 python tests | 2 | 1 | Acceptable for now; if it passes 60 s, split into a fast gate (validate, node, ascii) and a full gate run before merge and release only | PM |
| MR16 | Public QA playlists change or go offline mid-pass | 3 | 1 | Unit tests never touch the network; generated fixtures (`scripts/gen-playlist.py`) and local `--serve` are the source of truth; public lists are for live runs only | QA |
| MR17 | Merge conflicts on the three big files despite lane ownership, because a lane "just fixed one line" outside its set | 3 | 2 | Ownership table in section 5 is quoted verbatim in each lane brief; PO rejects a diff that touches an unowned file and asks the owning lane to make the change | PO |
| MR18 | The 150 ms guide open budget breaks in v0.4.0: logos add image decoding to row delegates | 2 | 3 | Async `Image` with a placeholder, never blocking the delegate; G3 re-run on the 10k cache with logos on as M2-04-07 acceptance; setting default can be flipped if it fails | FE |

## 8. QA gates and definition of done per feature

Gates G0-G5 are PLAN.md section 6 verbatim. Per-feature DoD:

M2-02 detached player - done when:
- [ ] `scripts/check.sh` exit 0 (G0+G1) at the integration commit.
- [ ] Manual: play a channel, run `omarchy restart shell`, the channel is
      still playing and the bar re-shows it within 2 s.
- [ ] `ps -ww -C mpv | grep -c '://'` is 0 while playing the FIRST channel
      of a session (closes security finding S-03).
- [ ] `pgrep -c -f wayland-app-id=omarchy-iptv` is 1 while playing and 0
      after stop, including after a forced kill of the shell.
- [ ] `docs/QA-PLAYER.md` matrix executed; zero open P1/P2 in STATUS.md.
- [ ] README "Playback notes" and CHANGELOG "Known limitations" no longer
      claim playback dies with the shell.
- [ ] G4: `grep -rn "sudo\|shell=True\|bash -c\|eval(" .` clean outside
      tests/docs; privacy sweep over the new sinks returns 0.

M2-03 channel numbers - done when:
- [ ] `node tests/Model.test.js` and `python3 -m unittest discover -s tests`
      green with the new number cases.
- [ ] Manual, list mode on a playlist with `tvg-chno`: `1 0 2` plays
      channel 102 when the timeout fires; `Esc` during entry cancels;
      `9 9 9` shows the unknown-number message and plays nothing.
- [ ] Manual, search mode: digits still filter as text.
- [ ] `omarchy-shell io.github.rmcdavid.iptv number 102` plays it.
- [ ] G3 re-run: guide open under 150 ms on the 10k cache; filter times and
      switch median unchanged from the v0.2.0 numbers.
- [ ] `docs/QA-NUMBERS.md` matrix executed; zero open P1/P2.

M2-05 PiP - done when:
- [ ] Manual on the live shell: `p` floats, pins and moves the player to the
      agreed corner and size; `p` again restores; `hyprctl clients -j` shows
      exactly one `omarchy-iptv` client throughout.
- [ ] Stop while in PiP leaves no floating leftover window.
- [ ] `contrib/windows.lua` snippet pastes in verbatim and works.
- [ ] PIP- cases executed on the live shell; zero open P1/P2.

M2-04 logos - done when:
- [ ] With the setting off, a refresh makes zero logo requests (verified by
      process/journal check).
- [ ] With it on, `find ~/.cache/omarchy-iptv/sources/<key>/logos -type f`
      shows 0600 files inside a 0700 directory, total under the agreed cap.
- [ ] G3: guide opens under 150 ms on the 10k cache with logos on.
- [ ] Privacy sweep clean; README names the hosts contacted.

M2-08 vertical bar - done when:
- [ ] Manual: the widget renders correctly in top, bottom, left and right
      bar positions without clipping, in two themes.
- [ ] README known-limitation line "vertical bars show the glyph only"
      removed.

## 9. Release checklist v0.3.0 (modeled on what was actually done for v0.2.0)

- [ ] `omarchy plugin validate .` exit 0 at HEAD.
- [ ] `scripts/check.sh` exit 0 at HEAD; record the four counts (node checks,
      python tests, qml spec, qmllint errors) in STATUS.md as for d50e364.
- [ ] Harness QA pass on the release candidate commit: every PLAYER-, NUM-
      and PIP- case plus a regression sample of the M1/M2-01 matrices;
      results appended to `docs/QA-RESULTS.md` with an evidence root.
- [ ] Zero open P1/P2 in `docs/STATUS.md`; P3s listed in README as known
      issues.
- [ ] Performance recorded and within budget: guide open on the 10k cache,
      switch median, helper parse, EPG parse (G3).
- [ ] Privacy sweep clean: `omarchy-shell io.github.rmcdavid.iptv status |
      grep -c '://'` is 0 and `journalctl --user -t omarchy-shell --since
      -30min | grep omarchy-iptv | grep -c '://'` is 0 after the pass.
- [ ] Live-shell pass on the reference machine with the snapshot/undo blocks:
      install state backed up, the new player survives `omarchy restart
      shell`, numeric zap on a real provider list, PiP toggled, theme switch
      with the guide open, state restored or deliberately kept.
- [ ] `manifest.json` `version` = `0.3.0`.
- [ ] `CHANGELOG.md` 0.3.0 section: Added / Security and privacy / Fixed /
      Known limitations, same shape as 0.2.0.
- [ ] README updated: playback notes (restart survives), keyboard map
      (digits, `p`), limits, and the removed limitations.
- [ ] PO acceptance row in STATUS.md against `docs/PRODUCT.md` ranks 1-3.
- [ ] `git tag -a v0.3.0 -m "Omarchy IPTV 0.3.0"` and push.
- [ ] GitHub release created for the tag.
- [ ] Installed copy updated: back up `~/.local/state/omarchy-iptv` and
      `~/.cache/omarchy-iptv`, pull, `omarchy restart shell` (keepLoaded
      service does not hot-reload), verify the guide and playback.
- [ ] `omarchy plugin update io.github.rmcdavid.iptv` verified against the
      GitHub origin (SR30 re-point must already be done in phase P0), then
      `omarchy restart shell` and one zap.

## 10. Process improvements (enforceable rules, from this project's friction)

1. FILE OWNERSHIP UP FRONT. Every lane brief opens with three lists: files
   the lane owns and may write, files it may read, files it must not open.
   The PO rejects any diff touching an unowned file. Derived from: M2-01
   needed a dedicated ownership table (ARCHITECTURE-SOURCES 8.1) and it is
   the reason the two lanes merged cleanly.

2. ONE LANE HOLDS THE DISPLAY. A lane brief that does not hold the display
   must forbid, by name: `wtype`, `grim`, `hyprctl dispatch|reload|keyword`,
   `omarchy theme set`, `omarchy plugin add|enable|disable|remove`, `omarchy
   bar set`, starting mpv or quickshell against the real session, and any
   write under `~/.config` or `/usr/share/omarchy`. Derived from: a leaked
   `Tab o x Return` reached the desktop during the M2-01 pass.

3. SHARED FIXTURE, WRITTEN BY THE LANE THAT LANDS FIRST. Any rule
   implemented twice (JS and Python) gets one JSON fixture, authored by the
   first-landing lane, run by both implementations inside `scripts/check.sh`.
   Parity is a gate, not a follow-up. Derived from: `source-urls.json` plus
   SR15 and commit 60a85dc, which fixed real disagreements over ports, BOM,
   zero-width characters and backslashes.

4. FINISH IN THE FOREGROUND. No agent ends a turn waiting on a background
   run. Harness and test runs are bounded (`run.sh --timeout N`) or polled to
   completion in the same turn, and the handoff block is written before the
   turn ends. If a run cannot finish in the turn, the agent reports what is
   pending and why instead of stopping silently.

5. NO SHIMS AT MERGE. A lane may stub its dependency to build, but each wave
   has an integration task whose acceptance is a grep proving zero stubs and
   a green `check.sh`. Derived from: M2-01 needed two explicit commits to
   swap shims out.

6. RULINGS IN BATCHES. A lane that finds a spec conflict collects it as a
   numbered decision request and sends the whole batch at one point in the
   wave. The PO answers the batch in one document section, mirrored in the
   STATUS.md decisions log. Derived from: SR1-SR10 then SR11-SR32.

7. SNAPSHOT BEFORE, RESTORE AFTER, ALWAYS. Any live pass begins with a
   snapshot block (shell.json, state.json, cache listing and hashes, plugin
   HEAD and origin, a timestamp) and ends with an undo block, both written
   into the QA document before the pass starts. Derived from: QA-SOURCES 9.1
   and 9.7, which kept the user's real 5-recent state intact.

8. RESTART AFTER A SERVICE CHANGE. Any verification claim about
   `Service.qml` is invalid unless the evidence includes an `omarchy restart
   shell` (live) or a quickshell restart by PID (harness). Kept-loaded
   services do not hot-reload.

9. AUTOMATION GUARDS ARE A PRECONDITION. Keyboard automation refuses to type
   while `pgrep -x hyprlock` matches or while the target window reports
   closed. A QA script without both guards is not accepted.

10. NEW SINK, NEW SWEEP. When a wave adds a place where text reaches the
    user or the log (a notification, a status line, a tooltip, an overlay, a
    console relay), the privacy sweep for that sink lands in the same commit
    and the QA plan grows the case. Derived from: D-LIVE-03 and D-SRC-10.

11. PM RE-PLANS when a task doubles its effort band, a P1 stays open for two
    sessions, or a `[PLAYER-SLOT]` resolution changes a dependency.
    Unchanged from PLAN.md section 7.
