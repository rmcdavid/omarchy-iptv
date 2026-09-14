# Omarchy IPTV - QA test plan for the detached player (M2-02)

Owner: QA. Status: v0.3 (2026-09-14), **executed twice**: against `main` at
`8f9447e` (the pass that filed D-PLY-1..7) and again against `main` at
`b16b479` (the fix verification, which discharged all seven and filed
D-PLY-8..11). Corrections from the first run are indexed in section 14 and
marked `[corrected 8f9447e]`; corrections from the second are in **section 15**
and marked `[corrected b16b479]`. Written at `363ce9c` (lane PA `M2-02-01`, lane PB `M2-02-02` and
the PO-3 follow-up all merged); the fix lane merged as `c458ebf` and section
1.8 records it. Everything the pass found to be wrong in this plan is
corrected in place and marked `[corrected 8f9447e]`, and section 14 lists the
corrections in one place with the evidence. Results are in
`docs/QA-RESULTS.md`, sections "M2-02 player pass on 8f9447e" and
"M2-02 fix verification on b16b479".
Extends `docs/QA.md` (v0.2: ids, methods, harness techniques, severities) and
`docs/QA-SOURCES.md` (v0.3: the `A`/`H`/`L` method codes, the snapshot and
restore shape); everything in both still applies and the re-run subset is
section 7.

Documents of record this plan verifies against: `docs/ARCHITECTURE-PLAYER.md`
(ARCH-P: decision 2, sections 4.1-4.14, hard requirements 1-11 in section 5,
security by enumeration in 6, failure modes in 7, migration in 8, the test
plan in 10, **section 12 rulings PO-1 to PO-7**, **section 13 amendment after
gate PB-0**, **section 14 amendment after lane PB**),
`docs/SPIKE-QUICKSHELL-SOCKET.md` (SPIKE: verdict, the two traps in section 2,
the six answers in 3, **caveats C1-C10 in section 5**, the reference snippet in
6), `README.md` (the user-facing promise: `Playback notes`, `Limits`,
`Files it writes`, `Uninstall`), `docs/PLAN-M2.md` (gates G0-G5 by reference to
`docs/PLAN.md` section 6, the M2-02 DoD in section 8, severities in section 0),
`docs/SECURITY-REVIEW.md` (S-03, the finding this milestone closes),
`CLAUDE.md` (engineering constraints 2, 5, 6, 10, 11, 12; the display rule).
Where ARCH-P and SPIKE disagree, section 13 settles it: the spike wins on
implementation shape, the rulings win on behaviour.

This file is ASCII. As in QA.md and QA-SOURCES.md, `...`, `"x"` and ` - ` in
quoted microcopy stand for U+2026, U+201C/U+201D and U+00B7 on screen; glyphs
are written as codepoints (U+F0503 etc.). Byte counts and ms figures quoted as
"recorded" come from `docs/QA-RESULTS.md`; figures quoted as "designed" come
from ARCH-P and have never been measured on this machine - the difference is
marked in every budget in section 6.

Machine of record: unchanged from QA.md and QA-SOURCES.md (Omarchy 4.x,
Quickshell 0.3.1, Hyprland 0.56.2, mpv 0.41.0, Python 3.14.7, node, one
1366x768 output, theme retropc). Verified read-only on 2026-09-14 for this
plan: the live shell is `quickshell -n -p /usr/share/omarchy/shell`; the
plugin is installed at `~/.config/omarchy/plugins/io.github.rmcdavid.iptv`;
`manifest.json` says `0.2.1`; `/run/user/1000/omarchy-iptv` exists, is `700`
and is **empty** - the leftover `srw------- mpv.sock` that ARCH-P 4.2 and 7
describe as "the live state right now" is gone, so the stale-socket cases must
create their own; `mpv --version` is `v0.41.0`; **`omarchy-iptv` is not on
`PATH`** (see PLY-WEAK-05 and section 10 item 3). Gate baselines at `363ce9c`:
`node tests/Model.test.js` 857 checks 0 failures, `python3 -m unittest
discover -s tests` 247 tests OK (41 of them `tests/test_player.py`).

## 0. How to read and execute this plan

- Test case ids are `PLY-<AREA>-<nn>`. Areas: RST (restart and reattach - the
  central case, section 2), LIFE (singleton, spawn, adoption, health), STOP
  (the stop ladder), FAIL (crash and end-of-stream detection, notifications),
  SOCK (the QML socket observer and the spike caveats), WEAK (the two
  knowingly weakened behaviours, PO-2 and PO-3, section 3), SEC (security and
  privacy, section 5), PERF (section 6), MIG (migration), MODEL (Model.js
  automated), HELP (helper automated), SVC (Service contract). `PLY-FIX-*` is
  reserved for the in-flight fix lane (section 1.8).
- "How" column: `A` = automated (exact command and file), `H` = harness
  scenario `PLY-Hnn` of section 8 (exact commands there; QA runs them), `L` =
  live shell (section 9). A case may list several. `A*` = an automated test
  this plan asks a lane to add; until it lands QA runs the command by hand.
  A cell with no token is a pointer (`see PLY-SEC-07`, `not testable here`).
- Results are recorded in `docs/QA-RESULTS.md` (a new
  "M2-02 detached player pass on `<commit>`" section, in the format of the M1
  and M2-01 passes) as `pass` / `fail D-PLY-<n>` / `blocked: needs harness
  verb <x>` / `blocked: needs live shell` / `not run <reason>`.
- A case fails if any expected string, glyph, count, pid, file mode, path,
  exit code, error code or timing is off. Microcopy is compared verbatim
  against `README.md` and `docs/UX.md` section 6.
- Severities (PLAN.md section 6). For this feature: **P1** = playback does not
  survive a shell restart; a second player window exists at any instant; the
  player cannot be stopped by any documented means; a stream URL, a
  credential or a header value reaches a command line, a file outside
  `channels.json`/`shell.json`, the journal, a notification or the IPC
  `status` output. **P2** = the reattach loses the channel identity or the zap
  ring; a stop is a silent no-op; a failure raises no notification or raises
  two; the guide is not marked on reattach (PO-3); the retry loop floods the
  journal; the orphan-check stops a player on a plain restart. **P3** =
  wording, ordering, a diagnostic regression, or a hardening item with no
  user-visible effect today.
- **CLAUDE.md rule 11 applies with the PO's double force** (ARCH-P section 12,
  second addition): every harness scenario added for this milestone must be
  shown to FAIL against pre-M2-02 code before it counts as evidence.
  `scripts/dev-harness/player-scenario.sh --baseline <ref>` exists for exactly
  this; its header already records which of its checks must fail against the
  last pre-M2-02 commit. Any new `PLY-Hnn` gets the same treatment, and the
  pass records both counts.
- Fixtures: `tests/fixtures/qa-player/` (section 8.0). It does **not exist at
  `363ce9c`** - it is lane PC's to author and is a precondition of the pass
  (section 10 item 7). Nothing in this plan touches `~/.config`,
  `/usr/share/omarchy`, `~/.cache/omarchy-iptv` or `~/.local/state/omarchy-iptv`
  except the live-shell runbook (section 9), which the lead runs on purpose,
  with the snapshot first and the byte-for-byte restore proof last.
- One lane holds the display. Sections 8 and 9 need it; sections 1, 4, 5, 6
  (the static half) and 7 do not.

## 1. Traceability matrix

### 1.1 Test cases

#### Restart and reattach (ARCH-P 4.5, 4.6, 7 rows 1-3 and 6-8, requirement 11; the milestone's whole reason to exist)

Depth for this area is in section 2; the rows below are the contract.

| ID | Verifies | How | Expected |
|---|---|---|---|
| PLY-RST-01 | `omarchy restart shell` while playing - the headline case | H PLY-H04; L 9.4 | the mpv pid before and after is **identical** and its `/proc/<pid>/stat` field 22 start time is unchanged; `hyprctl clients -j` shows exactly one `omarchy-iptv` client throughout (sampled every 100 ms across the restart, min 1 max 1); no audio or video glitch; `status` after the shell answers reports the same `nowPlaying.id`, `.name`, `.group` and `launchedFrom` as before; `player.attached` true; scroll-to-zap rings the same list it was launched from |
| PLY-RST-02 | restart during a channel change | L 9.5 step 1; H PLY-H11 | `omarchy restart shell` issued 0, 100, 300 and 600 ms after an Enter on a second channel, four runs: every run ends with exactly one player and a `nowPlaying` that is either the old or the new channel and matches what the window title shows; never a third state, never two windows, never a `nowPlaying` the player is not on. If the `loadfile` never landed mpv exited under `--idle=once`: the probe reports `running:false` and `state.json.session` drives the PO-3 mark (PLY-WEAK-06) |
| PLY-RST-03 | restart while a stream is failing | L 9.5 step 2; H PLY-H12 | play the dead credentialed fixture channel, restart the shell inside the 3 s first-load window: after the restart `status` reports `nowPlaying null`, `playing false`; **zero** `Stream failed` notifications are added by the restart itself (at most the one raised before it), counted on the session bus - see section 14 item 1. **[corrected 8f9447e]** `failedAt` is `{}` after the restart, **not** the channel id: `failedAt` is session-only (`Service.qml:230`) and only the PO-3 path (PLY-WEAK-06) carries a mark across a shell boundary. A live shell that saw and toasted the failure has already cleared `session`, so PLY-WEAK-09 applies and the successor correctly marks nothing. The original clause here contradicted PLY-FAIL-12's own "session-only" sentence |
| PLY-RST-04 | two shells briefly overlapping | H PLY-H08; L 9.5 step 3 | a second service against the same `XDG_RUNTIME_DIR` (harness `--instance`) adopts the running player and never spawns: the stub `mpv` recorder shows 0 new execs, `spawned:false` in the `player.start` reply, one window at every sample; both shells report the same `nowPlaying`; the loser's `orphan-check` is a no-op because the claim names the other shell; last intent wins by `--seq` |
| PLY-RST-05 | the shell is killed, not asked to stop | L 9.5 step 4 | `pkill -KILL -f 'quickshell -n -p /usr/share/omarchy/shell'`: the player keeps playing (same pid, `time-pos` still advancing 3 s later); `omarchy-launch-shell` brings the shell back and the reattach is PLY-RST-01's; exactly one mpv survives; the dead shell's `Component.onDestruction` never ran, so no `orphan-check` was even issued - this is the case that proves the feature does not depend on a graceful teardown |
| PLY-RST-06 | the socket file is removed underneath a live player | H PLY-H13; L 9.5 step 5 | `rm /run/user/1000/omarchy-iptv/mpv.sock` while attached and playing: SPIKE Q4 row 3 says the live QML connection **survives**, and it does - playback continues and `player.attached` stays true. **[corrected 8f9447e]** "zap and stop over the existing connection keep working" is **wrong**: the QML socket is a read-only *observer*; every zap and stop goes through the helper, which connects **by path**. So the next zap gets ENOENT, takes the wedged branch of ARCH-P 4.5, ladders the unreachable player down and respawns into a re-created 0700 directory with a 0600 socket. A `player probe` run before that zap reports `running:true, responsive:false`. End state: exactly one player, on the newly selected channel, no orphan; **no second window at any sample** (the count may dip to 0 across the replacement, which is not a violation) |
| PLY-RST-07 | a wedged, unresponsive player across a restart | H PLY-H05; L 9.6 step 3 | `kill -STOP` the player, then `omarchy restart shell`: the new service's `player probe` reports `running:true, responsive:false` (the `get_property mpv-version` read times out at `--ipc-timeout` 2.0 s), `applyProbe` takes the wedged row - `player stop` from rung 1 with the pid from `/proc`, UI shows idle - and the window is gone within 4.5 s of the probe answering. `connect()` succeeding through the listen backlog must **not** be read as alive anywhere in the trace |
| PLY-RST-08 | `XDG_RUNTIME_DIR` cleared while playing | H PLY-H14 | `rm -rf $XDG_RUNTIME_DIR/omarchy-iptv` (harness scratch only; never the live dir) while playing: the `/proc` scan still finds the player by the `--input-ipc-server=<abspath>` token, `connect()` gives ENOENT so `responsive:false`, it is laddered down by pid and respawned into a freshly created **0700** directory with a **0600** socket and a **0600** `player.lock`; `playSeq` resets on both sides together (`status.player.seq` and the new lock record agree); the inode re-check catches the recreate and no `busy` storm follows |
| PLY-RST-09 | suspend and resume | L 9.9 step 1 | `systemctl suspend`, wake, then within 10 s: the same mpv pid is alive, the QML socket is still attached (`player.attached` true) or reattaches within one 250 ms tick, `status` reports the same `nowPlaying`. A stalled stream after resume is **not** detected and `status` reports healthy - that is ARCH-P 7 row "Suspend / resume" as designed, unchanged from v0.2.0, and is recorded, not filed. See section 10 item 5: run or record `not run` |
| PLY-RST-10 | logout is the one thing that reaps the player | L 9.9 step 2 (last act of the pass) | with a channel playing, log out and log back in: `pgrep -f 'omarchy-iptv/mpv.sock'` is empty on the next login, `/run/user/1000/omarchy-iptv` is gone or empty. Static half, runnable any time: `systemctl --user show wayland-wm@hyprland.desktop.service -p ExitType -p KillMode -p TimeoutStopUSec` reports `main` / `control-group` / `10s`, `loginctl show-user 1000 -p Linger` reports `Linger=no`, and `cat /proc/<mpv pid>/cgroup` equals the shell's cgroup |
| PLY-RST-11 | a player started by hand with the same window identity | L 9.5 step 6 | `mpv --wayland-app-id=omarchy-iptv --input-ipc-server=/tmp/qa-player-foreign.sock --idle=yes --force-window=immediate` (a **different** socket): our `/proc` scan matches on the exact `--input-ipc-server=<our abspath>` token plus uid, so the foreign player is **never adopted, never signalled and never counted** - `player probe` reports only ours, a `player stop` leaves the foreign pid alive, and our own start still spawns exactly one. Documented consequences to record, not file: `hyprctl dispatch focuswindow class:omarchy-iptv` may focus theirs, and `pgrep -af -- '--wayland-app-id=omarchy-iptv' \| wc -l` reads 2. **[corrected 8f9447e]** do **not** add `--vo=null --ao=null` to the foreign player as 9.5 step 6 did: with no video output it maps no window, `hyprctl clients` shows one client and the focus consequence cannot be reproduced. Run it windowed, or record the focus half as `not run`. **[corrected b16b479]** run windowed, the consequence **reproduces and is now recorded rather than skipped**: `hyprctl clients` reads **2** `omarchy-iptv` clients and `pgrep` reads **2**, while `player probe` reports only ours, our `stop` leaves the foreign pid alive and our next start spawns exactly one. Section 14 item 7 is closed |
| PLY-RST-12 | two players on the **same** socket | H PLY-H03 | a second `player start` run by hand against the same socket path while one is live: the scan finds both, the one that answers is kept, the others are laddered down, one redacted warning is logged once, and `hyprctl clients -j \| jq '[.[]\|select(.class=="omarchy-iptv")]\|length'` returns to exactly 1 |
| PLY-RST-13 | restart with nothing playing | L 9.4 step 0 | `player probe` reports `running:false`; `playerWanted` goes false so the 250 ms retry timer stops (no journal noise, see PLY-PERF-04); the bar shows idle; `status` has `nowPlaying null`, `player.up false`, `player.wanted false`; **no** spurious `failedAt` entry when `state.json.session` is null |
| PLY-RST-14 | restart during a cold start, before the socket binds | H PLY-H15 | kill the shell between the `player start` issue and the socket bind (designed bind latency 0.114-0.151 s): either the helper completes the spawn as a reparented grandchild and the next shell adopts it, or the helper dies with it and the spawn it created is reaped by its own 5 s `--spawn-timeout` path. Both outcomes are pass; **a windowed player that nothing can reach is a P1 fail**. Ten runs, `hyprctl clients` sampled at 100 ms throughout, max 1 |
| PLY-RST-15 | reattach into a different active source | L 9.5 step 7 | switch the active source while the player is running, then restart: the stash's `sourceKey` does not match `Service.sourceKey`, so `reconcileNowPlaying()` resolves as "not in this playlist" - the bar keeps the name from the stash, the guide marks no row as playing, the zap ring does not ring a wrong list. Never a match on the wrong row |
| PLY-RST-16 | the playlist changed while the shell was down | H PLY-H16 | the channel's id disappears from `channels.json` between the stop of the old shell and the start of the new: `nowPlaying` is restored from the stash **before** `channelIndex` exists (bar correct immediately), and `reconcileNowPlaying()` on `channelsLoaded` degrades to name-only rather than resolving to a different channel; `status.nowPlaying.name` is right, `playing` is true, the zap ring is empty rather than wrong |
| PLY-RST-17 | the dying shell's orphan-check is a no-op | H PLY-H04; L 9.4 | across a normal restart the pending `player orphan-check --owner-pid <old> --grace 6` finds `user-data/omarchy-iptv-owner` reassigned to the successor at t+6 s and does nothing: the player is still alive at t+10 s. `omarchy-restart-shell` polls `omarchy-shell shell ping` every 100 ms for up to 2 s, so the successor claims well inside the grace - measure the actual claim time and record it against the 6 s budget |
| PLY-RST-18 | `playSeq` survives the restart | H PLY-H04; A `tests/test_player.py::test_the_lock_record_survives_for_the_probe_to_resume_the_sequence` | `player probe` returns the recorded `seq` and `applyProbe` sets `playSeq = max(probe.seq, 0) + 1`; `status.player.seq` after the restart is strictly greater than before it; a subsequent stop is not `superseded` by the old record |
| PLY-RST-19 | a theme change and a plugin rescan leave playback alone | L 9.4 step 5 | `omarchy theme set tokyo-night` and back, and `omarchy-shell shell rescanPlugins`: same mpv pid throughout, `nowPlaying` unchanged, bar label unchanged, no `orphan-check` stop (the service object is not destroyed on the hot-reload path - `serviceKeepLoaded`). This is README `Playback notes` bullet 2's "a theme change or installing another plugin" clause |
| PLY-RST-20 | ten restarts in a row | L 9.10 step 3 | `for i in $(seq 10); do omarchy restart shell; ...; done` while one channel plays: the same mpv pid for all ten, one window at every sample, `status.nowPlaying` stable, shell RSS and the mpv fd count flat within noise (see PLY-PERF-06), and no growth in `player.lock` or the runtime directory contents |

#### Singleton, spawn, adoption and health (ARCH-P 4.4, 4.9, 4.13, 5 requirements 1 and 5, 7 rows 4, 5, 9, 10)

| ID | Verifies | How | Expected |
|---|---|---|---|
| PLY-LIFE-01 | cold start spawns exactly one player | H PLY-H01; A `tests/test_player.py::test_spawns_once_and_sends_the_whole_wire_sequence_in_order` | one `mpv`, class `omarchy-iptv`, window title = channel name; the wire sequence in order: `title` -> `force-media-title` -> the three `header_properties()` pairs -> `user-data/omarchy-iptv` with `entryId:null` -> `loadfile <url> replace` -> `user-data/omarchy-iptv` with the entry id -> `user-data/omarchy-iptv-owner`; reply `spawned:true` with a `pid` |
| PLY-LIFE-02 | `player start` is idempotent | H PLY-H03; A `test_a_live_player_is_adopted_and_zapped_never_duplicated`, `test_two_starts_in_a_row_spawn_once` | a live answering player is adopted and zapped: `spawned:false`, the stub `mpv` was never executed, one window |
| PLY-LIFE-03 | Enter hammered on two channels during a cold start | L 9.6 step 1 | alternate Enter on two channels as fast as the guide accepts, 20 times, starting from nothing playing: `hyprctl clients -j` sampled every 100 ms shows **at most one** `omarchy-iptv` client at every instant and never two; the run ends on the last channel pressed; `pendingPlayId` burst coalescing is intact |
| PLY-LIFE-04 | a stale socket is unlinked before the spawn | H PLY-H06; A `test_stale_socket_is_unlinked_before_the_spawn` | `find_player()` empty, `connect()` ECONNREFUSED, `unlink_stale_socket()` removes it (S_ISSOCK only), spawn proceeds, one window. mpv never unlinks its own socket on any exit path, so this must happen on every cold start after a kill |
| PLY-LIFE-05 | a regular file at the socket path blocks the spawn | H PLY-H06; A `test_a_regular_file_at_the_socket_path_blocks_and_never_spawns` | `socket_path_blocked`, the file is **not** unlinked, nothing is spawned, no window; the existing `test_regular_file_at_socket_path_is_left_alone` still passes |
| PLY-LIFE-06 | a spawn that never binds is reaped by its creator | H PLY-H15; A `test_a_player_that_never_binds_is_reaped_by_the_helper_that_created_it` | after `--spawn-timeout` 5.0 s the helper ladders down the pid it read over the pid pipe, unlinks the socket and reports `no_socket`; the stub's pid is dead afterwards; **no window is left behind and the next start cannot multiply one**; the service takes the `playRetryTimer` backoff (300 / 600 / 900 ms, max 3) |
| PLY-LIFE-07 | mpv cannot be exec'd | A `test_a_missing_mpv_is_reported_through_the_errno_pipe`; H PLY-H15 (PATH-shadowed stub) | the CLOEXEC errno pipe reports it synchronously as `mpv_missing` (ENOENT) or `spawn_failed`; the service sets `mpvAvailable = false` and raises `mpv not found` / `Install mpv to play channels.`, urgency critical, glyph U+F0567. Not runnable live: mpv is an Omarchy dependency and removing it needs sudo (section 10) |
| PLY-LIFE-08 | several players found, one answers | A `test_start_ladders_a_wedged_player_down_before_spawning`; H PLY-H03 | the answerer is adopted, the rest laddered down, one redacted warning logged once, one window at the end |
| PLY-LIFE-09 | the lock serialises launchers | A `test_a_second_concurrent_start_reports_busy_and_never_spawns` | a second concurrent `player start` reports `busy` inside `--lock-timeout` 6.0 s and never spawns; the service retries with the existing backoff and the user sees one window, one channel |
| PLY-LIFE-10 | an older intent is superseded | A `test_an_older_intent_is_superseded_and_touches_nothing` | a verb whose `--seq` is lower than the lock record aborts as `superseded` and does nothing - no spawn, no signal, no socket write, no lock record rewrite; the service does nothing on `superseded`. **Read with ARCH-P section 14: a detached `stop` cannot observe this, which is PLY-STOP-07** |
| PLY-LIFE-11 | the lock file replaced mid-wait | A `test_the_lock_file_being_replaced_mid_wait_is_detected_and_retried` | `os.fstat(fd)` vs `os.stat(path)` mismatch or ENOENT is detected, the lock released, reopened and retried up to 5 times inside the same deadline; exhaustion is `busy`, never a second spawn |
| PLY-LIFE-12 | the health check's two-strike verdict | H PLY-H05; L 9.6 step 3 | `kill -STOP` the player: `status` reports `ok:false` with `process.found:true`; after two consecutive failures (10 s timer, 2 s probe deadline, so ~21 s) the console logs the unresponsive line and `player restart --from term` runs the ladder and the spawn under **one** lock acquisition; the SIGKILL lands; exactly **one** relaunch per player. **[corrected, cleanup round]** the one-relaunch half is asserted on the **intent counter** and never on the journal line (ruling **CL10**): `status.player.seq` and the `player.lock` record each advance by **exactly 1** across the wedge and respawn, where a tree that leaves the delivered relaunch queued advances both by **2**. Both readings exist on every M2-02 tree, which is what lets them tell two trees apart; the line `mpv unresponsive, restarting player` sits at one place in the shell, is emitted once by both trees, and is printed as an observation only. Measured 1/1/1 live at `a939fd7`, and read back from `396a69a`'s own source as `{"intents":2,"seqDelta":2}` |
| PLY-LIFE-13 | the health timer can never be gated off by a stale flag | A `tests/Model.test.js` `healthTick` block; H PLY-H05 | `healthTimer.running` is `playerUp \|\| nowPlaying !== null`, so a false `playerUp` during a reconnect window does not switch off its own reconciler; `healthSkips` respects `HEALTH_SKIPS_BEFORE_RESTART = 3` and an in-flight control call can no longer starve it indefinitely (D-LIVE-17's second half) |
| PLY-LIFE-14 | the player is not a child of the shell | H PLY-H03; L 9.4 step 2 | `ps -o ppid= -p <mpv pid>` is `1` or the `systemd --user` pid, never the quickshell pid; `cat /proc/<mpv>/cgroup` equals the shell's cgroup (same `wayland-wm@hyprland.desktop.service`). **[corrected 8f9447e]** fd 0 and fd 1 point at `/dev/null`; **fd 2 is a pipe, by design** - PO-6's launch-window stderr pipe. The helper exits after the window, so the read end is closed and the pipe is orphaned; mpv sets SIGPIPE to ignored (`SigIgn` bit 13), so writes return EPIPE and it carries on. The property the row is really asserting still holds: no Quickshell `StdioCollector` is attached, the shell holds no end of it, and **nothing of mpv's reaches the journal** (PLY-SEC-09 measured `grep -c 'mpv\['` = 0) |

| PLY-LIFE-16 | a cold start that is no longer the newest intent stands down | H PLY-H17 (no display); A `tests/test_player.py` T-B family | a `player start` whose own spawn is still inside its handshake when a channel change reaches the socket **leaves the newer channel playing**: the player takes **one** `loadfile` and not two, `user-data/omarchy-iptv` and `force-media-title` both name the **zap's** channel, and the reply carries `applied:false` with `playing:{id,name}` naming what it left up so the shell can re-apply its own intent. The ordering comes from the **spawn**, not from a sequence number - a player this helper just spawned was born idle with `playlist-count` 0 and no `user-data` node of ours - which is what keeps it inside **CL4**: `play` gains no `--seq`, takes no lock, and no channel change during a cold start is ever delayed or refused. An **adopted** player is never asked, because there a stash orders nothing. Deterministic 1/1 through the stub's handshake gate; against `a939fd7` the same checks read 2 loads and the start's own channel |
| PLY-LIFE-17 | a divergence is visible to the health tick, and the label converges within one tick | H PLY-H18 phase A (no display) + phase B (display); A `Model.reconcileVerdict`, `Model.sessionIntentRepair` | **CL6**, written out. Phase A: `status` carries the player's own now-playing record (`stash`) naming the channel actually loaded, with `verb` saying which side wrote it and a **real** intent number rather than the hardcoded `0`, so the two sides can be **compared** and not merely differed. Phase B: with a divergence forced on a live player, within **one health tick** (10 s timer, 2 s probe deadline) the player is back on the channel the user chose and `nowPlaying` is **unchanged** - the shell re-applies its intent and never relabels itself from the player (**CL5**), because relabelling would leave the user watching something they did not choose with the interface agreeing. Repairs are bounded per intent, so a player that will not take the channel is reported rather than re-zapped forever. Phase A fails against `a939fd7`, where `status` carries no such field and the divergence is undetectable |

#### Stop ladder (ARCH-P 4.9, 4.10, 5 requirement 4, 14; README `Playback notes` bullet 4)

| ID | Verifies | How | Expected |
|---|---|---|---|
| PLY-STOP-01 | stop clears the interface on the keystroke | H PLY-H07; L 9.6 step 2 | `s` in list mode, right click on the bar, and `omarchy-shell io.github.rmcdavid.iptv stop` all clear `nowPlaying`, `pendingPlayId`, `wantFocus` and the timers **synchronously**: the next `status` (one IPC round trip) already reads `nowPlaying null`, `playing false`; footer `Stopped` for 3 s then the count; bar back to the idle glyph U+F0502; no notification |
| PLY-STOP-02 | the `quit` rung ends a responsive player | H PLY-H07 | `request(["quit"], allow_close=True)` on rung 1; the process is gone well inside `STOP_QUIT_GRACE_MS` = 2000; reply `rung:"quit"`, `running:false`; **no** SIGTERM and **no** SIGKILL line in the console |
| PLY-STOP-03 | the ladder reaches a wedged player | H PLY-H05; L 9.6 step 3 | `kill -STOP` then stop: `quit` at 0 (ignored), `SIGTERM` at 2.0 s, `SIGKILL` at 4.0 s, settle at 4.5 s; the window is gone and `hyprctl clients -j \| jq '[.[]\|select(.class=="omarchy-iptv")]\|length'` is 0; the socket is unlinked only after the final connect is refused. **[corrected b16b479]** on the **wedged** path it is **not** unlinked at all: the player is reaped at ~4.25 s and `mpv.sock` survives, measured still present at t+66 s with the shell idle, and only the next helper call (`probe`/`status`) removes it. Present at `8f9447e` too, so this row's clause has never held on this path - see D-PLY-8. The responsive path unlinks correctly (5/5). This is the D-LIVE-17 case, now reachable because the pid comes from `/proc` and not from `get_property pid` **[corrected, cleanup round]** the row now ASSERTS the file is gone, with a deadline and a control: `ls $XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock` **fails at t+0.5 s** after the stop returns and still fails at t+1 s, t+5 s and t+30 s, on the **wedged** path as well as the responsive one, **with no `probe`/`status`/`play` of the tester's own in between** - that last clause is the whole case, because any helper call unlinks it and a run that made one proves nothing. The journal carries no `the player outlived a stop` backstop line. Measured 10/10 at `a939fd7` (5 wedged, 5 responsive, QA-RESULTS D2) where it failed 5/5 at `8f9447e` and `b16b479`. The old wording - "unlinked only after the final connect is refused" - described a mechanism and asserted nothing a tester could read; a residue is only harmless while nothing else depends on the file being absent |
| PLY-STOP-04 | the ladder completes if the shell dies mid-ladder | L 9.6 step 4 | issue a stop against a SIGSTOPped player, then `pkill -KILL` the shell 200 ms later: the detached helper still SIGTERMs at 2 s and SIGKILLs at 4 s and the player is gone by 4.5 s, with no shell running. This is the property `escalateStop()` in QML could never have |
| PLY-STOP-05 | the socket is unlinked only when it is truly dead | A `test_nothing_running_is_a_clean_stop_that_unlinks_a_stale_socket`, `test_stop_after_a_start_leaves_nothing_behind` | settle unlinks only when `find_player()` is empty **and** `connect()` returns ENOENT/ECONNREFUSED, S_ISSOCK-guarded; a racing start's fresh socket is never deleted |
| PLY-STOP-06 | a recycled pid is never signalled | A `test_a_recycled_pid_is_never_signalled` | pid + `/proc/<pid>/stat` field 22 start time + the `--input-ipc-server` cmdline token are re-verified immediately before **each** signal; a pid whose start time no longer matches gets no signal at all |
| PLY-STOP-07 | a stop that loses the sequence race is not a silent no-op | L 9.6 step 5; H PLY-H10 | ARCH-P section 14's regression. Push the lock sequence ahead from a terminal (`player start` or `player stop` with a high `--seq`), then press `s`: the interface clears **and the player actually stops**. The `stopSettleTimer` (5 s) must fire, log `the player outlived a stop, re-reading its sequence`, run `player probe` and re-issue past the recorded sequence. **The interface going idle while the player keeps playing is a P1** |
| PLY-STOP-08 | play during a stop starts a fresh player | H PLY-H07 | while `stopping` is true, `play()` always takes the `startPlayer()` branch and never writes a zap to a dying socket; `player start` blocks on the lock behind the running ladder and wins on `--seq`; one window at the end, on the newly selected channel. README: "Playing a channel while the old player is still shutting down starts a fresh player once it has exited" |
| PLY-STOP-09 | stop with nothing running | A `test_nothing_running_is_a_clean_stop_that_unlinks_a_stale_socket`; H PLY-H07 | `{ok:true, running:false, rung:""}`; no error surfaces in the UI; `stop()` never gates on `playerUp`, so it is issued unconditionally and is simply a no-op |
| PLY-STOP-10 | `--from term` skips the quit rung | A `test_from_term_skips_the_quit_rung` | `player restart --from term` starts at rung 2; the timeline is TERM at 0, KILL at 2.0 s; used only by the health verdict |
| PLY-STOP-11 | every stop affordance takes the same path | H PLY-H07; L 9.6 step 2 | `s`, bar right click, `omarchy-shell ... stop`, and the guide's Esc-then-stop path all issue exactly one `Quickshell.execDetached(player stop --socket S --seq N)` with a fresh `playSeq`; console shows one issue per user action, never a ladder driven from QML (`escalateStop`, `stopTimer`, `stopStage` are gone: `grep -n 'escalateStop\|stopStage' Service.qml` is empty) |

#### Crash, end of stream and notifications (ARCH-P 4.8, 5 requirement 6, 7 row "Zap burst"; README `Playback notes` bullet 3)

| ID | Verifies | How | Expected |
|---|---|---|---|
| PLY-FAIL-01 | a first channel that fails before any subscriber exists | H PLY-H02; L 9.8 step 1 | the commonest real failure (an expired subscription). `player start` issues `request_log_messages "error"` **before** `loadfile` and observes for `--first-load-timeout` 3.0 s on its own connection; the reply carries `firstLoad:{state:"failed", reason:"<scheme://host only>"}`; the toast is raised from `handlePlayerResult()` at once, without waiting for the socket |
| PLY-FAIL-02 | a dead stream while attached | H PLY-H02 | `end-file{reason:"error", playlist_entry_id:N, file_error:"loading failed"}` over the QML socket -> one `Stream failed` / `"<name>" did not play - <reason>` notification, glyph U+F0503, urgency normal, `-r 74011`; `failedAt[id]` set; the guide row gains U+F0026 and `Failed HH:MM - Space to retry` |
| PLY-FAIL-03 | exactly one toast when both detectors fire | H PLY-H02; L 9.8 step 1 | `player start`'s first-load window and socket EOF are two independent detectors of the same dead stream; `notifiedFailureId` keeps the user's toast count at exactly **one** per play. `omarchy-shell notifications showHistory` gains one line, not two |
| PLY-FAIL-04 | a zap is not a failure | A `tests/Model.test.js` router block (`routePlayerEvent`, `endedVerdict`); H PLY-H09 | a zap emits `end-file{reason:"stop"}` immediately followed by `start-file` for the new entry, on one pid, window intact: **no** notification, no `failedAt` entry, `currentEntryId` moves, `lastEndFile` is cleared by the `start-file` |
| PLY-FAIL-05 | `redirect` is never terminal | A `endedVerdict` vectors in `tests/fixtures/player-argv.json` | an intermediate `.m3u8` master resolution gives `reason:"redirect"` and is ignored; this fires on the masters IPTV uses most, so a false toast here would be constant |
| PLY-FAIL-06 | a clean end stays silent (PO-4) | A `endedVerdict` vectors; H PLY-H09 | `end-file{reason:"eof"}` -> silent stop, bar idle, cues cleared, **no** notification, `state.json.session` cleared so no PO-3 mark follows. Zero behaviour change from v0.2.0's exit-0 silence. **Note the README contradiction in section 11 item 1** |
| PLY-FAIL-07 | the user presses `q` in mpv | A `endedVerdict` vectors; L 9.8 step 2 | `reason:"quit"` -> silent; bar idle; cues clear; no notification |
| PLY-FAIL-08 | a crash or SIGKILL with no `end-file` | H PLY-H09; L 9.8 step 3 | `kill -9` the player while attached: socket EOF within 2-3 ms (SPIKE Q4), no `end-file` at all (SPIKE C9: a trailing partial line is dropped at EOF), verdict = stream failure with the generic reason `Model.PLAYER_GENERIC_FAILURE`; one toast naming the channel; `failedAt` set |
| PLY-FAIL-09 | a failure that arrives after the user zapped away | A router vectors; H PLY-H09 | `end-file{error}` for entry 1 arriving after a zap to entry 2: `entryOwners[1]` names the **right** channel in the toast and marks the right row in `failedAt`; `start-file` for entry 2 has already cleared `lastEndFile` |
| PLY-FAIL-10 | the entry gate fails open | A `channelForEnd` / `endedVerdict` vectors | a null or unrecognised `playlist_entry_id` **never** suppresses a notification - it only degrades which channel is named, falling back to `nowPlaying`. `entryOwners` holds at most `PLAYER_ENTRY_OWNERS` entries |
| PLY-FAIL-11 | the failure reason is host-only at every hop | A `test_nothing_in_the_runtime_dir_or_any_argv_or_any_line_carries_the_credential`; H PLY-H02; L 9.8 | `log-message` text is reduced to `scheme://host` by `redact_urls()` **inside python** before it enters QML, then again by `rememberStderr`'s `Model.redactUrls`; the 5-line tail is memory-only; the notification body, `lastError`, the guide status line and `status` all carry at most `http://127.0.0.1` |
| PLY-FAIL-12 | the mark clears when the channel plays again | H PLY-H02 | a successful play of a previously failed channel removes it from `failedAt` (`Model.withoutFailed`); the row loses U+F0026 and the `Failed HH:MM` detail; `failedAt` is session-only and does not survive a restart **except** through the PO-3 path (PLY-WEAK-06) |

#### The QML socket observer (SPIKE caveats C1-C10, ARCH-P section 13)

Every row here is a caveat the spike proved the hard way; C1 and C2 are the
difference between a working reattach and a plugin that shows idle forever.

| ID | Verifies | How | Expected |
|---|---|---|---|
| PLY-SOCK-01 | C1: never reuse a `Socket` after a failed connect | A `grep -n 'Socket {' Service.qml` and the shape check below; H PLY-H04 | `Service.qml` declares `Component { id: playerSocketComponent; Socket { ... } }` plus `property var playerSocket: null`, never a bare `Socket { id: playerSocket }`; `attachPlayerSocket()` constructs a fresh object per attempt and `destroy()`s a failed one. Behavioural proof: kill the player, let at least one retry land on an absent server, restart the player, and the shell must reattach on the next 250 ms tick (spike measured 246 ms). **A shell that shows idle forever after the first failed retry is a P1** |
| PLY-SOCK-02 | C2: never arm an already-connected socket | A `grep -n 'connected = true' Service.qml` - every site guarded by `if (root.playerSocket === null)`; H PLY-H04 | no defensive re-arm exists; the hidden zero-delay auto-reconnect of SPIKE 2.1 is never latched, so the object is not bricked the moment mpv dies. Run T9's trap must be unreproducible: after a peer `kill -9`, the reattach succeeds |
| PLY-SOCK-03 | C3: `playerUp` null-guards | A `grep -n 'readonly property bool playerUp' Service.qml`; A `tests/Model.spec.qml` | reads `(root.playerSocket !== null && root.playerSocket.connected) \|\| root.playerPending`; no TypeError in the console across a full kill/restart cycle |
| PLY-SOCK-04 | C4: the state handler reads `this.connected` | A code review of `onConnectionStateChanged` | the handler reads `this.connected`, never `root.playerUp` or `root.playerSocket` - it fires **synchronously inside** the `connected = true` assignment, before the caller stores the reference and before the binding re-evaluates |
| PLY-SOCK-05 | C5: a failed connect emits `error` only | A `tests/Model.spec.qml`; H PLY-H04 | no `connectionStateChanged` on a failed connect; the code tests `connected` immediately after the assignment (authoritative because the assignment is synchronous) and does not wait for a state change |
| PLY-SOCK-06 | C6: the retry burst is capped | A `grep -n 'playerSocketTries' Service.qml` (12); L 9.10 step 2 | 12 tries x 250 ms = 3 s, inside the 12 s `playerWatchdog`, then fall back to `player probe` / the 10 s poll rather than spinning. Journal volume is PLY-PERF-04 |
| PLY-SOCK-07 | C7: never write to an unconnected socket | A code review of every `playerSocket.write` call site | every write is gated on `connected`; a write to an unconnected socket returns normally, throws nothing and is silently discarded, so an ungated write is an invisible lost command |
| PLY-SOCK-08 | C8: never arm with an empty path | A code review; H PLY-H04 | arming with an empty `path` is a **total no-op** - no connect, no `error`, no state change. The service must not arm before `socketPath` is set; `Component.onCompleted` order proves it |
| PLY-SOCK-09 | C9: a trailing partial line is dropped at EOF | A `endedVerdict` "no end-file at all" vector; H PLY-H09 | covered by PLY-FAIL-08; the entry gate stays fail-open |
| PLY-SOCK-10 | C10: `destroy()` from inside the handler is safe | H PLY-H04 (repeat kill/restart x 25) | `releasePlayerSocket()` called from `onConnectionStateChanged` does not crash the shell; QML defers it; no fd growth |
| PLY-SOCK-11 | no fd leak, no CPU spin | L 9.10 step 4 | over 10 player deaths and reattaches plus 120 failed attempts: `ls /proc/<shell pid>/fd \| wc -l` flat within 2, `awk '{print $14+$15}' /proc/<shell pid>/stat` grows by single-digit ticks, RSS flat within noise. The spike measured fds 26 -> 27 and +4 ticks over 120 failed attempts |

#### The two weakened behaviours (PO-2, PO-3; ARCH-P 4.14, 5 requirements 4 and 6)

Tested as specified, not as regressions. Detail in section 3.

| ID | Verifies | How | Expected |
|---|---|---|---|
| PLY-WEAK-01 | PO-2: disabling the plugin while playing stops the player | L 9.7 step 1 | `omarchy plugin disable io.github.rmcdavid.iptv` with a channel playing: the service object is destroyed, `Component.onDestruction` fires `player orphan-check --owner-pid <shell pid> --grace 6`, the claim still names a **live** shell pid with a matching start time, so the check runs `player stop`. The window is gone within ~7 s (6 s grace + the quit rung). This is PO-2's stated acceptance gate |
| PLY-WEAK-02 | PO-2: removing the plugin while playing stops the player | L 9.7 step 2 | `omarchy plugin remove io.github.rmcdavid.iptv --yes`: same discriminator, same ~7 s, no leftover mpv, socket unlinked, runtime dir empty |
| PLY-WEAK-03 | PO-2: a shell restart is NOT a teardown | L 9.4; H PLY-H04 | the same `onDestruction` path fires on a graceful restart (`omarchy-restart-shell` uses `quickshell kill`, journal shows the IPC-request exit), and the check must be a **no-op**: the successor has overwritten the claim by t+6 s. **A restart that kills the player is a P1 - it defeats the entire feature.** PO-2 is explicit: do not stop on destruction |
| PLY-WEAK-04 | PO-2: the disclosed residual | L 9.7 step 3 | a shell that is SIGKILLed and never comes back leaves the player running until logout. Prove it and **record it, do not file it**: it is not a regression (`Process::~Process()` only runs on a clean teardown today, so v0.2.0 behaves the same) and `KillMode=control-group` reaps it at session end (PLY-RST-10) |
| PLY-WEAK-05 | PO-2: the documented escape hatch actually works | L 9.7 step 4 | README `Playback notes` bullet 6 tells the user to run `omarchy-iptv player stop`. Verified read-only on 2026-09-14: **`omarchy-iptv` is not on `PATH`** (`command -v omarchy-iptv` exits 1; nothing in `/usr/bin` or `~/.local/bin`). The runnable form is `python3 ~/.config/omarchy/plugins/io.github.rmcdavid.iptv/bin/omarchy-iptv player stop --socket "$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock"`. Expected: that form stops an orphan within 4.5 s. **The README form as written is a P2 documentation defect and PO-2's contract also puts it in the Uninstall section, where it is absent** (section 11 item 3) |
| PLY-WEAK-06 | PO-3: a failure with no shell attached is marked silently on reattach | L 9.8 step 4 | **The procedure, exactly.** 1. Play a channel; confirm `state.json` has a `session` record naming it (`jq .session`). 2. `omarchy-shell shell kill` / `pkill -f 'quickshell -n -p /usr/share/omarchy/shell'` so no shell is attached; confirm 0 quickshell, mpv still alive. 3. `kill -9 <mpv pid>` - the failure now happens with nobody listening. 4. Bring the shell back (`omarchy-launch-shell`). 5. Expect: `player probe` reports `running:false`; `deadSessionVerdict` marks that channel in `failedAt` and clears `session`; `status` shows `failedAt:{"<id>":"HH:MM"}`, `nowPlaying null`, `playing false`; the guide row carries U+F0026 and `Failed HH:MM - Space to retry`; **`omarchy-shell notifications showHistory` gains ZERO lines** - no `Stream failed` toast, at all. 6. `jq .session ~/.local/state/omarchy-iptv/state.json` is `null` and the file is still `0600` |
| PLY-WEAK-07 | PO-3: no session record, no mark | A `tests/Model.test.js` `deadSessionVerdict` block; L 9.8 step 5 | `probe running:false` with `session` null -> `mark:false`, `write:false`, the same state object returned; no spurious `failedAt` entry, no state write, no toast. Covers a shell start after a clean stop and a first-ever start |
| PLY-WEAK-08 | PO-3: the two arrivals race in either order | A `deadSessionVerdict` block | the probe answers in ~130 ms while `state.json` loads whenever its `FileView` does. With `stateLoaded !== true` the verdict is `pending`, with `write:false` and no mark, and the caller re-runs it from the state handler. **Deciding on an unloaded state would read the empty default, lose the mark, and could put an empty state over the user's file** - prove the file is byte-identical after a start where the probe won the race |
| PLY-WEAK-09 | PO-3: a clean stop clears the record so no false mark follows | H PLY-H07; L 9.8 step 5 | stop, then restart the shell: `session` is null, no channel is marked, `failedAt` stays empty. Same for a clean `eof` (PO-4 path). A false red row on every restart would be a P2 |
| PLY-WEAK-10 | both weakenings are stated to the user in plain language | A read of `README.md` and `CHANGELOG.md` | README `Playback notes` bullet 6 states both, in the same plain language as the existing limitations (present at `363ce9c`); the 0.3.0 CHANGELOG section states both under `Known limitations`. **At `363ce9c` there is no 0.3.0 section, so the release-notes half is open** (section 11 item 10). This is the PO's own non-optional addition in ARCH-P section 12 |

#### Security and privacy (ARCH-P section 6, SECURITY-REVIEW S-03, PLAN gate G4, CLAUDE.md rules 2 and 5)

Method and the full sweep are section 5. Expected output is empty or `0`
unless stated.

| ID | Standard | How | Expected |
|---|---|---|---|
| PLY-SEC-01 | S-03 closed on the FIRST channel | L 9.3 step 2; A `test_spawn_argv_carries_no_url_no_header_and_no_channel_name` | `tr '\0' ' ' < /proc/$(pgrep -f -- '--input-ipc-server=/run/user/1000/omarchy-iptv/mpv.sock')/cmdline` contains no `://`, no `qa-user`, no `qa-secret`, no `qa-token-XYZ`, no `qa-ua-SENTINEL`; it **does** contain `--idle=once`, `--wayland-app-id=omarchy-iptv`, `--ytdl=no`, `--title=$>IPTV`, `--force-media-title=IPTV`, `--force-window=immediate`, `--keep-open=no`, `--msg-level=all=error`; there is **no** trailing `--` |
| PLY-SEC-02 | S-03 holds after ten zaps | L 9.3 step 3 | the same command after ten zaps across channels with and without headers: byte-identical argv to step 2 (the launch argv is per-process, not per-channel); `ps -ww -C mpv \| grep -c '://'` is 0 |
| PLY-SEC-03 | the helper's own argv is URL-free | L 9.3 step 4 (the `/proc` sampler) | across a whole session the sampler catches `player start`, `play`, `player stop`, `player probe`, `player orphan-check` and `status`; none carries `://`, a credential, a token or a header value. `--id` carries `t:<tvg-id>` or `u:<fnv1a32(url)>`, `--cache-dir`, `--socket`, `--seq`, `--scope`, `--since`, `--owner-pid`, `--mpv-arg` only |
| PLY-SEC-04 | no header value on any command line | L 9.3 step 4; A `headerArgs` tests | the sentinel `#EXTVLCOPT:http-user-agent=qa-ua-SENTINEL` and `#EXTVLCOPT:http-referrer=http://qa-ref-SENTINEL.test/` reach mpv **only** over the socket; `qa-ua-SENTINEL` and `qa-ref-SENTINEL` appear 0 times in the whole cmdline sweep. TC-PLAY-08 is inverted by this row |
| PLY-SEC-05 | the disclosed residual: what a command line DOES say | L 9.3 step 5 | Record, do not file. `--id t:<tvg-id>` on the helper's argv is a per-zap record of *what* is being watched, readable through `/proc/<pid>/cmdline` (0444, `/proc` mounted without `hidepid`), for the ~130 ms the helper lives. Separately, `Model.notifyArgv` puts the **channel name** on `omarchy-notification-send`'s argv on every failure. **[corrected 8f9447e]** README `Playback notes` bullet 5 no longer claims "`ps` shows nothing about what you are watching"; it now names **exactly these two** and says neither exposes credentials. So this row became a **verification of a narrowed claim**, not a contradiction: prove the two named exposures are the only ones, and that no address, credential or header value joins them. Measure: how many sweep samples catch an `--id`, how many catch the notifier, and whether the window title (which names the channel for the whole play, not for milliseconds) is the larger exposure. **The sweep must exclude the QA driver's own shell processes**, whose argv carries the needles in the grep patterns themselves |
| PLY-SEC-06 | the sweep holds with a hand-started player present | L 9.5 step 6 then 9.3 step 4 | with the foreign `--wayland-app-id=omarchy-iptv` player of PLY-RST-11 running, our sweep is unchanged; the foreign player's own argv is the user's business and is excluded from the count by socket path, not by app-id |
| PLY-SEC-07 | every new artifact on disk: mode and content | L 9.3 step 6 | complete list, nothing else may appear. `$XDG_RUNTIME_DIR/omarchy-iptv/` `700`; `mpv.sock` `600` (srw-------, created 0600 by mpv itself under `umask 0022`); `player.lock` `600`, contents exactly one line `{"schema": 1, "seq": N, "verb": "start\|stop\|restart", "at": <epoch>}` with no URL (**[corrected 8f9447e]** the helper's `json.dumps` default puts a space after each `:` and `,`; compare the fields, not the byte spelling); `~/.local/state/omarchy-iptv/state.json` `600` with `session` = `{id,name,at}` and no URL. Command: `find "$XDG_RUNTIME_DIR/omarchy-iptv" ~/.local/state/omarchy-iptv -exec stat -c '%a %n' {} + \| grep -vE '^(700\|600) '` returns nothing, and `grep -rlE '://\|qa-secret\|qa-token-XYZ' "$XDG_RUNTIME_DIR/omarchy-iptv"` returns nothing. **[corrected b16b479]** the list grew by two documented directories when D-PLY-7 was fixed: `$XDG_RUNTIME_DIR/omarchy-iptv/watch-later/` `700` holding resume files at `600` (the name is an MD5, the content carries no address), and `~/.local/state/omarchy-iptv/screenshots/` `700` holding screenshots at `600`. Both verified. **No `player.json`, no log file outside those, no systemd unit, no drop-in.** A `mpv.sock` left behind by a wedged stop is D-PLY-8, and is still `600`, so this row's `find` check passes either way. One artifact the player creates is **outside** this list entirely: `~/.cache/mpv/shader_*` (`600`, content-free) - D-PLY-10 |
| PLY-SEC-08 | `player.lock` is documented | A read of `README.md` `Files it writes` | the section lists `$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock` but **not** `player.lock` at `363ce9c` (section 11 item 5). P3 documentation |
| PLY-SEC-09 | the journal | L 9.3 step 7 | `journalctl --user -t omarchy-shell --since "$(cat $E/started-at)" \| grep omarchy-iptv \| grep -cE '://\|password=\|username=\|qa-secret\|qa-token-XYZ\|qa-ua-SENTINEL'` is `0`. This matters here because `omarchy-launch-shell` runs `systemd-cat -t omarchy-shell -- quickshell`, making the shell's stdout and stderr a persistent, group-readable stream. mpv's own stdio is `/dev/null` from before `execvp`, so **nothing of mpv's reaches the journal at all** - prove it with `journalctl --user --since ... \| grep -c 'mpv\['` = 0 |
| PLY-SEC-10 | the shell console | L 9.3 step 7 | `qs log -p /usr/share/omarchy/shell --tail 800 \| grep -cE '://\|qa-secret\|qa-token-XYZ'` on `omarchy-iptv` lines is `0`; helper stderr reaches the console only through `console.warn(Model.redactUrls(...))` |
| PLY-SEC-11 | the IPC `status` output | L 9.3 step 7 | `omarchy-shell io.github.rmcdavid.iptv status \| grep -cE '://\|password=\|username='` is `0`. `statusSummary()` is URL-free by construction; the additive `player:{up,pending,attached,wanted,stopping,seq,entryId}` block is booleans and ints; `failedAt` is ids and `HH:MM` |
| PLY-SEC-12 | notifications | L 9.3 step 7; L 9.8 | `omarchy-shell notifications showHistory \| grep -cE '://\|qa-secret\|qa-token-XYZ'` is `0`; the failure body reads `"<name>" did not play - http://127.0.0.1` at most; S-04 rules hold (leading dashes stripped, typographic quotes, body never starts with `-`) |
| PLY-SEC-13 | `MPV_RESERVED` gained the ten durable-exposure options | A `tests/Model.test.js` `MPV_RESERVED` block; A `test_mpv_reserved_matches_model_js` | `--log-file`, `--dump-stats`, `--stream-record`, `--save-position-on-quit`, `--watch-later-dir`, `--osd-msg1`, `--osd-msg2`, `--osd-msg3`, `--term-status-msg`, `--screenshot-template` and their `--no-` forms are all rejected with one console warning naming them; the nine existing entries and the D-QA-11 lowercase-only rule are unchanged; the python mirror is pinned equal by the parity test |
| PLY-SEC-14 | PO-5: `--ytdl` stays unreserved and its cost is written down | A `splitMpvArgs` tests; L 9.3 step 8 | `--ytdl=yes` survives `splitMpvArgs` and still sorts after the built-in `--ytdl=no`. The cost, confirmed real by SPIKE Q3 **and reproduced live at `8f9447e`**: mpv's `ytdl_hook` fires on a failed HTTP open and spawns `yt-dlp ... -- <full URL>` on **another** process's argv. Live check with the default settings: `pgrep -c -x yt-dlp` stays `0` across a deliberately dead channel (use `pgrep -x`, not `ps aux | grep -c '[y]t-dlp'` - the latter matches the QA driver's own argv). **PO-5 requires one README sentence naming the cost - verify it is present.** At `8f9447e` it was **absent** (D-PLY-5). **[corrected b16b479]** it is present: `README.md` carries it beside the `mpvArgs` row and `CHANGELOG.md` 0.3.0 names it under Security, and the product now also raises `Player warning: mpvArg --ytdl hands the stream address to another program` on the guide's single warning line **without refusing the option** (`--ytdl=yes` is last on mpv's argv; mpv's `ytdl` property reads `true`). The cross-reference to "D-PLY-1" in the original row was a typo for D-PLY-5 |
| PLY-SEC-15 | argv only, no shell, no sudo, no writes in the plugin dir | A `grep -rn "sudo\|shell=True\|bash -c\|eval(" .` outside tests/docs; A the SEC-01 grep extended to the new call sites; L 9.3 step 9 | nothing. Four hops, four argv vectors: QML -> helper is `["python3", helperPath, ...]`; helper -> mpv is `os.execvp("mpv", argv)` with a **literal** argv[0], so `player start` is not an arbitrary-exec verb; `Quickshell.execDetached(list)` everywhere; no `systemd-run`, no `uwsm-app` (rejected for its `eval "$CMDLINE"`), no `hyprctl exec_cmd`. `find <plugindir> -newer <plugindir>/manifest.json -not -path '*/.git/*'` empty after the pass |
| PLY-SEC-16 | the environment does not reach a command line | A code review of `spawn_detached`; L 9.3 step 5 | `spawn_detached` passes the inherited environment unchanged - no `--setenv`, so nothing moves from the `0400 /proc/<pid>/environ` onto the `0444` cmdline. `grep -c setenv` on the mpv launch argv is 0 |
| PLY-SEC-17 | new stdlib imports only | A `grep -nE '^import \|^from ' bin/omarchy-iptv` | `fcntl`, `signal`, `errno` added; `socket`, `stat`, `os`, `time`, `json` already present; no third-party import (CLAUDE.md rule 3) |
| PLY-SEC-18 | S-01 raw prefix survives the move to IPC | A `mpvWindowTitle` / `MPV_RAW_PREFIX` tests; L 9.3 step 10 | a channel named `${path}` in the playlist: `set_property title "$>${path}"` stores the string byte-identically including the `$>` (expansion happens at render time), so `hyprctl clients -j` shows the literal name and **never** a credentialed URL in the window title; `force-media-title` is confirmed not expanded and carries the plain name without the prefix; `--title` stays in `MPV_RESERVED` |

#### Performance (PLAN G3, ARCH-P 4.4, 4.5, 4.9; section 6 has the method)

| ID | Budget | Procedure | Record |
|---|---|---|---|
| PLY-PERF-01 | recovery after a restart: `player probe` answers <= 400 ms after the shell answers IPC (designed ~130 ms); `status.nowPlaying` non-null <= **2000 ms** (PLAN-M2 DoD and ARCH-P 7's acceptance bar); `player.attached` true <= 3000 ms (12 x 250 ms burst cap) | section 9.4, five runs | three medians and maxima, and the mpv pid before/after |
| PLY-PERF-02 | stop: interface clear <= 150 ms (live IPC round trip is 67 ms median); responsive player gone <= 500 ms (recorded 219-263 ms in v0.2.0); wedged player gone <= 4500 ms (quit 0, TERM 2.0, KILL 4.0, settle 4.5) - **met at `b16b479`: 4236-4263 ms over five runs**, after D-PLY-6 stopped the quit rung spending the full `--ipc-timeout` against a player the probe already called unresponsive | section 9.6, five runs each | median and max for all three; whether any SIGKILL line appeared in the responsive case (it must not) |
| PLY-PERF-03 | channel change: zap on a live player to first frame < **2000 ms** (PRODUCT, PERF-06; recorded window map 378-457 ms warm, 803 ms cold); the IPC `play` reply <= 300 ms | section 9.10 step 1, three channels x three runs | ms per zap, warm and cold separated |
| PLY-PERF-04 | the retry loop cannot flood the journal: <= **12** `quickshell.io.socket` WARN lines per player death (C6's cap), and <= **60** over a 30-minute session with nothing playing | section 9.10 step 2 | count from `journalctl --user -t omarchy-shell --since ... \| grep -c 'quickshell.io.socket'` and from `/run/user/1000/quickshell/by-id/*/log.qslog`. **The spike measured one WARN per failed attempt with no deduplication: a free-running 250 ms retry is 4 lines/second, ~14,000/hour. Anything approaching that is a P2** |
| PLY-PERF-05 | one helper verb costs <= 300 ms (designed ~125-130 ms; recorded analog 120-126 ms including spawn) | `for i in 1 2 3 4 5; do t0=$(date +%s%N); python3 <plugindir>/bin/omarchy-iptv player probe --socket "$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock" >/dev/null; t1=$(date +%s%N); echo $(( (t1-t0)/1000000 )); done` | median and max for `probe`, `status`, `stop` |
| PLY-PERF-06 | no leak across ten restarts: shell fd count flat within 2, RSS within noise of the 396 MB recorded baseline, mpv fd count flat | section 9.10 step 3, sampling `/proc/<pid>/fd` and `ps -o rss=` before, midway and after | three triples |
| PLY-PERF-07 | the guide still opens in < 150 ms with the 10k cache (G3, unchanged by this milestone) | QA.md PERF-02 Method A, verbatim | median of 5, against the `shell ping` baseline |

#### Migration and compatibility (ARCH-P section 8)

| ID | Verifies | How | Expected |
|---|---|---|---|
| PLY-MIG-01 | upgrade over a v0.2.0 player that survived a SIGKILLed shell | L 9.9 step 3 | start a v0.2.0-shaped player by hand (URL on argv, `--idle=no`) on our socket path, then start the new service: the probe finds it by the socket token, it answers, but `user-data/omarchy-iptv` is absent -> "unknown player" -> re-probe once after 500 ms -> still ambiguous -> `player stop` -> idle. One Enter restores service. This is ARCH-P 8's `PLAYER-MIG-01` |
| PLY-MIG-02 | `state.json` stays version 2 | A `tests/test_state.py`; A `parseState` tests | `STATE_VERSION` is still `2`; `session` is one optional nullable key beside `lastPlayed`; both `parseState` and `normalize_state` whitelist known keys, so a v0.2.0 build reading a v0.3.0 file simply drops it; favorites and recents survive a downgrade round trip |
| PLY-MIG-03 | an older `Service.qml` against a newer helper still works | A CLI contract tests in `tests/test_mpv.py` | `play`, `stop` and `status` keep their spelling, exit codes and reply shape; `play`'s new `--scope`/`--since` and returned `entryId`, and `status`'s new `process` and `stash`, are additive; **all 23 existing `tests/test_mpv.py` cases pass unmodified** - if one needs editing, `cmd_play` or `header_properties` changed and requirement 2 or 7 is at risk |

#### Model.js, automated (`node tests/Model.test.js`)

| ID | Verifies | How | Expected |
|---|---|---|---|
| PLY-MODEL-01 | the launch argv carries no channel | A `buildMpvArgv` block | contains `--idle=once`; **no** token matching `/:\/\//`; no `--user-agent=`, `--referrer=` or `--http-header-fields` even for a channel **with** headers; no trailing `--`; every token after index 0 begins with `--` |
| PLY-MODEL-02 | the player argv builders | A `playerStartArgv`, `playerStopArgv`, `playerRestartArgv`, `playerProbeArgv`, `playerOrphanCheckArgv` | every element a separate argv member; user tokens as repeated `--mpv-arg`, never joined; `--seq` always present; `--owner-pid` only where the frozen interface says |
| PLY-MODEL-03 | `parsePlayerProbe` never throws | A | a valid body, an unknown schema, truncated JSON and garbage all return `valid:false` |
| PLY-MODEL-04 | `endedVerdict` truth table | A, from `tests/fixtures/player-argv.json` | error / eof / stop / quit / redirect x userStopped / stopping / neither, plus "no end-file at all" -> failure, plus the fail-open entry-id rule |
| PLY-MODEL-05 | `deadSessionVerdict` (PO-3's decision) | A | the four branches of PLY-WEAK-06..09, including `pending` on an unloaded state and the same-object return when nothing changed |
| PLY-MODEL-06 | the unchanged reducers stay unchanged | A | `stopEscalation` (7 existing checks), `healthTick` (4), `statusHealthy`, `splitMpvArgs`, `headerArgs`, `mpvWindowTitle`, `MPV_RAW_PREFIX`, `notifyArgv`, `focusPlayerArgv`, `redactUrls`, `withFailed` all green unmodified. Check count must not fall below the `363ce9c` baseline of **857** |

#### Helper, automated (`python3 -m unittest discover -s tests`)

| ID | Verifies | How | Expected |
|---|---|---|---|
| PLY-HELP-01 | the whole wire sequence and order | A `test_spawns_once_and_sends_the_whole_wire_sequence_in_order` | as PLY-LIFE-01 |
| PLY-HELP-02 | the S-03 regression net | A `test_spawn_argv_carries_no_url_no_header_and_no_channel_name`, `test_the_launch_argv_never_carries_a_channel` | as PLY-SEC-01 |
| PLY-HELP-03 | the privacy sweep in-process | A `test_nothing_in_the_runtime_dir_or_any_argv_or_any_line_carries_the_credential` | play -> failure -> stop against a URL embedding `user:pw@` and a token, then grep the whole runtime dir, every recorded argv and every emitted line: nothing; `firstLoad.reason` reads `scheme://host` only |
| PLY-HELP-04 | the lock protocol | A `test_a_second_concurrent_start_reports_busy_and_never_spawns`, `test_the_lock_file_being_replaced_mid_wait_is_detected_and_retried`, `test_an_older_intent_is_superseded_and_touches_nothing` | as PLY-LIFE-09/10/11 |
| PLY-HELP-05 | the ladder with an injected clock | A `test_quit_then_sigterm_at_2s_then_sigkill_at_4s`, `test_from_term_skips_the_quit_rung`, `test_a_recycled_pid_is_never_signalled` | as PLY-STOP-02/03/06/10 |
| PLY-HELP-06 | probe and orphan-check | A `test_merges_the_proc_half_and_the_socket_half_and_never_reads_path`, the three `orphan-check` tests | probe merges `/proc` and socket halves and **never reads `path`**; the three claim branches are no-op / stop / no-op |
| PLY-HELP-07 | cross-language parity | A `test_mpv_reserved_matches_model_js`, `test_stop_escalation_matches_every_shared_vector`, `test_ended_verdict_matches_every_shared_vector`, `test_the_four_tables_are_all_present_and_non_trivial` | the shared `tests/fixtures/player-argv.json` vectors are read by **both** `tests/Model.test.js` and `tests/test_player.py` and agree (CLAUDE.md: one shared JSON fixture for a rule implemented twice) |
| PLY-HELP-08 | `MpvIpc` keeps the events it steps over | A `test_request_keeps_the_events_it_steps_over`, `test_drain_events_waits_returns_empty_and_reports_a_close` | `request()` appends unsolicited event lines to `self.events` instead of dropping them with `continue`; `drain_events(deadline)` reads them, so `request_log_messages` output and `end-file` are not discarded |

#### Service contract (ARCH-P 4.7, 4.8, 4.10; `tests/Model.spec.qml` and code review)

| ID | Verifies | How | Expected |
|---|---|---|---|
| PLY-SVC-01 | the twenty `mpvProc.running` read sites were rewired per the 4.7 table | A code review against ARCH-P 4.7 row by row | every row's new expression is present; `stop()`'s early return is **deleted**; the `escalateStop` ladder lines are **deleted**; `healthTimer.running` is `playerUp \|\| nowPlaying !== null`, not `playerUp` alone |
| PLY-SVC-02 | the deleted objects are actually gone | A `grep -n 'mpvProc\|launchMpv\|handleMpvExit\|escalateStop\|stopTimer\|stopStage' Service.qml` | nothing. No shim survives the integration (PLAN-M2 M2-02-04) |
| PLY-SVC-03 | the router is pure and lifted out of QML | A `tests/Model.test.js` router block | `routePlayerEvent` / `playerRouterState` / `endedReport` are called for real by the tests, not reimplemented in them (CLAUDE.md rule 12); the spec covers a zap sequence raising no notification, an `end-file{error}` naming the channel from `entryOwners`, and a `log-message` with a credentialed URL yielding a host-only tail |
| PLY-SVC-04 | `playerUp`'s truth table | A `tests/Model.spec.qml` | over (`socket === null`, `socket.connected`, `playerPending`); the synchronous birth edge is preserved so the bar lights up on the same frame as v0.2.0 |
| PLY-SVC-05 | the reattach read is side-effect-free except one unlink | A code review of `player probe`; A `test_merges_the_proc_half_and_the_socket_half_and_never_reads_path` | `probe` is lock-free; it reads `idle-active`, `mpv-version`, `user-data/omarchy-iptv`, `user-data/omarchy-iptv-owner` and **never** `path` (a credentialed URL) or `media-title` (verified stale after playback ends) |
| PLY-SVC-06 | the four event kinds and nothing else | A `parsePlayerEvent` tests | `start-file`, `end-file`, `log-message`, `property-change` for `idle-active` are handled; anything else is ignored without a warning storm |
| PLY-SVC-07 | `playSeq` has exactly one issuer | A `grep -n 'playSeq' Service.qml bin/omarchy-iptv` | Service.qml increments it on every `play()` and every `stop()`; the helper only compares and records |
| PLY-SVC-08 | `statusSummary()` gained the observer's own view | A `grep -n 'player: {' Service.qml`; L 9.3 step 7 | `player:{up,pending,attached,wanted,stopping,seq,entryId}` and `failedAt` are present and URL-free - the acceptance gates need them because the detached player can only be verified from outside the shell now, and `playing` alone cannot distinguish a birth edge from an attached socket |

### 1.2 Hard requirements 1-11 (ARCH-P section 5) -> test cases

| # | Requirement (status in ARCH-P 5) | Test cases |
|---|---|---|
| 1 | exactly ONE player instance, never a second window (kept, strengthened) | PLY-LIFE-01, 02, 03, 04, 05, 06, 08, 09, 10, 11, PLY-RST-04, 12, 14, 20, PLY-HELP-04 |
| 2 | zapping reuses the window via `play --id` -> properties -> `loadfile replace` (kept) | PLY-LIFE-01, PLY-FAIL-04, PLY-PERF-03, PLY-MIG-03, TC-PLAY-02 (re-run), TC-PLAY-03 (re-run) |
| 3 | window class `omarchy-iptv`, title = channel name, `$>` raw prefix (kept) | PLY-SEC-18, PLY-LIFE-01, PLY-RST-11, TC-PLAY-01 (re-run) |
| 4 | stop immediate, quit -> TERM@2 s -> KILL@4 s, never an orphan (**weakened -> PO-2**) | PLY-STOP-01..11, PLY-WEAK-01..05, PLY-PERF-02 |
| 5 | health check every 10 s, two failures relaunch once, stale sockets unlinked (kept) | PLY-LIFE-12, 13, PLY-STOP-05, PLY-LIFE-04, PLY-RST-07 |
| 6 | failure raises a notification naming the channel, stderr redacted, channel marked (**weakened -> PO-3**) | PLY-FAIL-01..12, PLY-WEAK-06..09, PLY-SEC-12 |
| 7 | per-channel headers applied and CLEARED between channels (kept, strengthened) | PLY-SEC-04, PLY-LIFE-01, PLY-HELP-01, `test_restart_sends_the_channel_headers_so_nothing_leaks_between_channels`, TC-PLAY-08 (re-run, inverted) |
| 8 | user `mpvArgs` still apply, reserved filter intact (kept, strengthened) | PLY-SEC-13, 14, PLY-MODEL-02, PLY-HELP-07, TC-CFG-08 (re-run) |
| 9 | argv-only, no shell interpolation, no sudo, stdlib-only python3 | PLY-SEC-15, 16, 17 |
| 10 | socket under `$XDG_RUNTIME_DIR/omarchy-iptv/` with 0700/0600 modes | PLY-SEC-07, PLY-RST-08, PLY-LIFE-04, 05 |
| 11 | bar and guide keep accurate now-playing state, RECOVERABLE after a restart | PLY-RST-01, 13, 15, 16, 17, 18, PLY-SVC-04, 08, PLY-PERF-01, TC-BAR-01/03 (re-run) |

### 1.3 Rulings PO-1 to PO-7 (ARCH-P section 12) -> test cases

| # | Ruling | Test cases |
|---|---|---|
| PO-1 | `--idle=once`, gated on probe PA-0(a) | PLY-SEC-01 (the token is on argv), PLY-FAIL-06 (exit on clean end), PLY-FAIL-02 (exit on error end - SPIKE T7 saw real mpv exit 1 ms after an error `end-file`), PLY-FAIL-04 (a `loadfile ... replace` during playback must **not** exit mpv - PA-0(a), lane PA's half of the gate, re-proven here end to end), PLY-LIFE-01 |
| PO-2 | accept best-effort teardown; do NOT stop on service destruction; the owner-claim check plus a documented `player stop` is the contract; PLY-WEAK-01 is the acceptance gate | PLY-WEAK-01, 02, **03**, 04, 05, PLY-HELP-06, PLY-RST-17 |
| PO-3 | mark the channel failed silently on reattach and show it in the guide; no stale toast | PLY-WEAK-06, 07, 08, 09, PLY-RST-03, PLY-MODEL-05, PLY-SEC-12 |
| PO-4 | keep a clean end silent, zero behaviour change | PLY-FAIL-06, PLY-FAIL-07, PLY-WEAK-09. **See section 11 item 1: the README contradicts this ruling** |
| PO-5 | keep `--ytdl` unreserved, add the README sentence naming the cost; the ten reserved additions land regardless | PLY-SEC-13, PLY-SEC-14 |
| PO-6 | implement the stderr pipe for the launch window | PLY-LIFE-06, PLY-LIFE-07, PLY-FAIL-01. Specifically: a bad user `mpvArg` that kills mpv before it binds must produce **redacted text**, not a bare generic "player did not start" - verify `warnings` / the reported reason names the option |
| PO-7 | `M2-02` means the detached player everywhere; no `M2-09` row | A read of `docs/STATUS.md`: the stale `M2-02 Multiple playlists` row is retired as superseded by M2-01, the `PLAN-M2.md` task ids `M2-02-00..05` are untouched, and no `M2-09` exists. Recorded in the pass, not a test case |

Plus the PO's two non-optional additions: both weakenings stated in the README
and the release notes (PLY-WEAK-10), and every harness scenario shown to fail
against pre-fix code (section 0, section 8.0).

### 1.4 Spike caveats C1-C10 (SPIKE section 5) -> test cases

| Caveat | Test case |
|---|---|
| C1 (blocking) never reuse a `Socket` after a failed `connected = true` | PLY-SOCK-01 |
| C2 (blocking) never write `connected = true` on an already-connected socket | PLY-SOCK-02 |
| C3 `playerUp` must null-guard | PLY-SOCK-03 |
| C4 `onConnectionStateChanged` fires synchronously inside the assignment | PLY-SOCK-04 |
| C5 a failed connect emits `error` only, no state change | PLY-SOCK-05 |
| C6 bound the retry loop (~14k journal lines/hour unbounded) | PLY-SOCK-06, PLY-PERF-04 |
| C7 never `write()` unless `connected` | PLY-SOCK-07 |
| C8 never arm with an empty `path` | PLY-SOCK-08 |
| C9 a trailing partial line is dropped at EOF | PLY-SOCK-09, PLY-FAIL-08 |
| C10 `destroy()` from inside the state handler is safe | PLY-SOCK-10 |

The spike's non-caveat findings are pinned too: Q2 framing (`SplitParser`
strips the marker, 200 KB and 2000-message boundary cases) by PLY-SVC-06 and
PLY-FAIL-09; Q4's "unlinking the socket file does not disturb an attached
connection" by PLY-RST-06; Q6's no-leak result by PLY-SOCK-11.

### 1.5 README, sentence by sentence -> test cases

The user-facing promise. Every sentence of `Playback notes` and `Limits`, in
order, at `363ce9c`.

| Sentence | Test case |
|---|---|
| P1 "One mpv window, class `omarchy-iptv`, titled with the channel name." | PLY-LIFE-01, PLY-SEC-18, PLY-RST-11 |
| P1b "Switching channels reuses it." | PLY-FAIL-04, PLY-PERF-03, TC-PLAY-02 (re-run) |
| P2 "Playback survives `omarchy restart shell`." | **PLY-RST-01** |
| P2b "The player runs on its own and the guide reattaches to it, so a restart, a theme change or installing another plugin all leave what you are watching alone." | PLY-RST-01, PLY-RST-19, PLY-LIFE-14 |
| P3 "A stream that fails **or ends** shows a desktop notification naming the channel" | PLY-FAIL-02 (fails: toast), PLY-FAIL-06 (ends: **silent**, per PO-4). **Contradiction, section 11 item 1** |
| P3b "the guide marks the row until the channel plays again." | PLY-FAIL-02, PLY-FAIL-12 |
| P4 "Stop clears the bar and guide immediately." | PLY-STOP-01, PLY-PERF-02 |
| P4b "If mpv ignores the quit request it is terminated, and if it ignores that too it is killed, within about four seconds." | PLY-STOP-03, PLY-PERF-02. **The ladder settles at 4.5 s, section 11 item 4** |
| P4c "Playing a channel while the old player is still shutting down starts a fresh player once it has exited." | PLY-STOP-08 |
| P5 "No stream URL ever reaches the player's command line." | PLY-SEC-01, PLY-SEC-02 |
| P5b "It starts empty and every channel, header and title travels over a private socket that only you can read" | PLY-SEC-01, PLY-SEC-04, PLY-SEC-07, PLY-SEC-18 |
| P5c "so `ps` shows nothing about what you are watching." | PLY-SEC-05. **Contradicted by ARCH-P 6's own disclosed residual and by `notifyArgv`; section 11 item 2** |
| P6 "If you remove or disable the plugin while something is playing, the player is no longer guaranteed to stop with it" | PLY-WEAK-01, 02, 04 |
| P6b "run `omarchy-iptv player stop`, or log out, if one is left behind." | PLY-WEAK-05 (**not on PATH**), PLY-RST-10 |
| P6c "a stream that fails while the shell is down cannot raise a notification, because the notification service is the shell itself" | PLY-WEAK-06. Static half: `busctl --user tree org.freedesktop.Notifications` is owned by quickshell and there is no activation file under `/usr/share/dbus-1/services/`, so `busctl` returns "The name is not activatable" |
| P6d "the channel is marked as failed in the guide instead, the next time you open it." | **PLY-WEAK-06** |
| P7 "Channel names are shown verbatim except that leading dashes are stripped and mpv property expansion is disabled for the window title." | PLY-SEC-18, PLY-SEC-12 (S-04 leading-dash rule in `notifyArgv`) |
| L1 "Playlists are capped at 50,000 channels and 2,000 groups ..." | not touched by this milestone; re-run TC-RFR/TC-BRW cap rows only if the fix lane touches parsing (section 7) |
| L2 "Downloads (playlist and EPG) must finish within 60 seconds; redirects ..." | not touched by this milestone; skip (section 7) |
| F1 `Files it writes`: "`$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock` : mpv IPC socket while playing" | PLY-SEC-07. **`player.lock` is missing from this list; PLY-SEC-08, section 11 item 5** |
| U1 `Uninstall` block | PLY-WEAK-05. **PO-2's contract puts `player stop` here and it is absent; section 11 item 3** |

### 1.6 Failure modes (ARCH-P section 7) -> test cases

| ARCH-P 7 row | Test case |
|---|---|
| Restart while playing | PLY-RST-01 |
| Crash mid-zap | PLY-RST-02 |
| Overlapping shells | PLY-RST-04 |
| Stale socket | PLY-LIFE-04, PLY-LIFE-05 |
| Wedged process | PLY-RST-07, PLY-LIFE-12, PLY-STOP-03 |
| Suspend / resume | PLY-RST-09 |
| Logout | PLY-RST-10 |
| `XDG_RUNTIME_DIR` cleared while playing | PLY-RST-08 |
| User-launched mpv with the same app-id | PLY-RST-11 |
| `player start` cannot exec mpv | PLY-LIFE-07 |
| mpv starts but never binds the socket | PLY-LIFE-06, PLY-RST-14 |
| Zap burst across a slow failure | PLY-FAIL-09, PLY-FAIL-10 |
| Two players somehow exist | PLY-RST-12, PLY-LIFE-08 |

### 1.7 ARCH-P section 14 (the corrections lane PB found live) -> test cases

Sections 4.9 and 4.10 must **not** be read as correct as written.

| Correction | Test case |
|---|---|
| A detached stop cannot observe a `superseded` refusal; the stop-settle timer probes and re-issues past the recorded sequence | **PLY-STOP-07** |
| The `session` key of 4.6 and 8 was built by a follow-up lane, not PA or PB | PLY-WEAK-06..09, PLY-MODEL-05, PLY-MIG-02 |
| A lane that owns implementation and no tests leaves its own paths uncovered | PLY-SVC-03 (the router is called for real), and the coverage audit in section 8.0 |

### 1.8 Fix lane: `c458ebf` (filled 2026-09-14, gate satisfied)

The fix lane merged as **`c458ebf`**, "one rule for when the session record
survives". The code under test for the whole pass is `main` at **`8f9447e`**,
which is `c458ebf` plus the three documentation commits `e2b7aa0`, `24c347a`
and `8f9447e` itself.

**Behaviour changes.**

| Change | Serves | Rows affected |
|---|---|---|
| `Model.sessionAfterOutcome()` added: one rule for whether the `session` record survives a player outcome, replacing a per-branch condition in `Service.qml` | PO-3, ARCH-P 4.6 and section 14 | PLY-WEAK-06..09, PLY-MODEL-05 |
| Twelve branches in `Service.qml` routed through `noteSessionOutcome()` so every ending retires the record | PO-3 | PLY-WEAK-09 |
| Three sibling paths fixed beyond the one reported: a failed start, a missing mpv and an abandoned relaunch each used to leave the record behind, so the next reattach marked that channel a second time for a failure the user had already dealt with | PO-3 | PLY-WEAK-09, and the new `PLY-FIX-01` below |

**`PLY-FIX-01`** | the record does not outlive the shell that saw how the play
ended | A `tests/Model.test.js` `sessionAfterOutcome` block; L 9.8 step 5 | a
failed start, `mpv_missing` and an abandoned relaunch all clear `session`, so
a later reattach raises no second mark. The rule lives in `Model.js`, not as a
condition per branch, and is called for real by the tests (CLAUDE.md 12).

**Rule 11 evidence and the re-measured gate baselines** (2026-09-14, this
machine):

| Gate | `363ce9c` | `8f9447e` |
|---|---|---|
| `node tests/Model.test.js` | 857 checks, 0 failures | **885 checks, 0 failures** |
| `python3 -m unittest discover -s tests` | 247 tests, OK | **247 tests, OK** |
| `tests/test_player.py` alone | 41 | **41** |
| `qmltestrunner -input tests/Model.spec.qml` | - | **42 passed, 0 failed** |
| `omarchy plugin validate .` | - | **exit 0** |

The fix lane's own evidence is the 28 new node checks: they exercise
`sessionAfterOutcome` and its twelve call sites, and section 7's regression
numbers below are measured against `8f9447e`, not `363ce9c`.

## 2. The central case in depth: playback survives a shell restart

This is the whole feature. Everything else in M2-02 exists to make this safe.
The nine variants below are the ones that can plausibly break it; each is a
row in section 1.1 and a step in section 9.

**The invariant, stated once and asserted in every variant.** Across the
event, at every 100 ms sample:

- `pgrep -f -- '--input-ipc-server=<socket>' | wc -l` is exactly `1` before
  and after, with the **same pid and the same `/proc/<pid>/stat` field 22
  start time** (the start time is what makes the pid claim honest - a recycled
  pid would otherwise read as success);
- `hyprctl clients -j | jq '[.[]|select(.class=="omarchy-iptv")]|length'` is
  never `2` and never `0` while the stream is meant to be running;
- the stream does not glitch: mpv's `time-pos` read over the socket by a
  read-only helper advances monotonically across the restart, with no reset
  to 0 (a reset means a reload, which means the "same pid" check was passing
  for the wrong reason);
- afterwards `omarchy-shell io.github.rmcdavid.iptv status` reports the same
  `nowPlaying.id`, `.name`, `.group` and `launchedFrom`.

The last field is the one a naive implementation loses. `launchedFrom` is pure
UI intent - the zap-ring scope - that no built-in mpv property could ever
report, which is exactly why the shell stashes its own value inside the
player's `user-data`. **The acceptance test for it is behavioural, not
textual: after the restart, scroll the bar wheel and confirm the ring is the
list the channel was launched from**, not All and not the channel's group.
`sourceKey` is the same class of field and PLY-RST-15 is its case.

**Ordinary (PLY-RST-01).** `omarchy restart shell` with a channel playing.
`quickshell kill -p ... --any-display` kills only the quickshell process; mpv
is a `setsid`'d grandchild of `systemd --user`, in the same cgroup, so it is
untouched. The new service's `player probe` runs from
`Component.onCompleted`, finds the player by the `/proc` token, reads the
stash, restores `nowPlaying` **before `channelIndex` exists**, and claims
ownership. The socket subscriber reconnects on the retry tick.
Budget: PLY-PERF-01.

**Restart during a channel change (PLY-RST-02).** The window between `play`'s
helper call and its reply. The stash is written **before** the `loadfile` with
the new identity and rewritten **after** with the entry id, so the stash is
the truth in either outcome: if the `loadfile` landed, `idle-active` is false
and the new channel shows; if it did not, mpv exited under `--idle=once`, the
probe reports `running:false`, and `state.json.session` names the channel for
the silent PO-3 mark. Four offsets (0, 100, 300, 600 ms) because the failure
this looks for is an ordering one, and one offset proves nothing.

**Restart while a stream is failing (PLY-RST-03).** The restart lands inside
the 3 s first-load window on a dead channel. The trap is a **double toast**:
the old shell may have raised one before dying, and the new shell must not
raise a second for the same event. It must not, because PO-3 says a failure
observed with no shell attached is marked silently, and because
`notifiedFailureId` guards the live path. Count notification-history lines
before and after; a second line is a P2.

**Two shells briefly overlapping (PLY-RST-04).** The runtime directory is the
ownership domain. Two services sharing one `XDG_RUNTIME_DIR` both adopt the
same player, both zap it and both can stop it - last intent wins by `--seq` -
and **no second window is possible** because the `/proc` scan sees the
existing process. The loser's `orphan-check` is a no-op because the claim
names the other shell. The dev harness exports its own `XDG_RUNTIME_DIR`, so
it can never signal the live player; the harness `--instance NAME` flag gives
two services one runtime directory, which is how this is driven without
touching the live session.

**Killed, not asked to stop (PLY-RST-05).** `pkill -KILL` the shell. Nothing
graceful runs: no `Component.onDestruction`, no `orphan-check`, no `quit`.
The player must be completely indifferent. This is the variant that proves the
design does not secretly depend on a clean teardown, and it is also the
variant that produces PLY-WEAK-04's residual if the shell never comes back.

**The socket file removed underneath a live player (PLY-RST-06).** Two
opposite truths, both from the spike: an **already attached** connection
survives the unlink and stays fully usable (SPIKE Q4 row 3), while a
**future** connect gets `ServerNotFoundError` instead of
`ConnectionRefusedError`. So the case has two halves: the live half must keep
working (play, zap, stop over the existing connection), and the recovery half
must classify the player as unresponsive and ladder it down rather than
leaving an unreachable window. This is also why `player probe`'s one
stale-socket unlink is safe next to a live QML observer.

**A wedged, unresponsive player (PLY-RST-07).** `connect()` succeeds through
the listen backlog and then never replies - which is exactly why `connect()`
is never the existence check anywhere in this design. `find_player()` sees the
process, the `get_property mpv-version` probe times out at 2 s, and the
wedged branch ladders it down by the pid from `/proc`. An IPC-only design
could not obtain a pid at all. `kill -STOP` is the deterministic stand-in; the
original D-LIVE-17 trigger (an mpv that mapped a window and never came up on
IPC) is not reproducible on demand (section 10).

**The runtime directory cleared (PLY-RST-08).** The socket file and the lock
vanish; mpv holds a listening socket nobody can reach. The `/proc` scan still
finds it by cmdline token. Both sides reset `playSeq` to 0 together, and the
lock inode re-check catches the recreate. Harness only - never `rm -rf` the
live `/run/user/1000/omarchy-iptv`.

**Suspend and resume (PLY-RST-09), logout (PLY-RST-10), a hand-started player
(PLY-RST-11).** Suspend is the one variant this machine cannot provoke
cleanly from a script (section 10 item 5). Logout is the **one thing that
should reap the player**, and it is provable only as the last act of the pass;
its static half (`ExitType=main`, `KillMode=control-group`,
`TimeoutStopUSec=10s`, `Linger=no`, and the mpv pid's cgroup) can be read at
any time and is what turns "no unit file is needed" from an assertion into
evidence. The hand-started player matters because the scan matches on the
exact `--input-ipc-server=<abspath>` token **plus uid**, never on `app_id`:
a user's own `mpv --wayland-app-id=omarchy-iptv` on a different socket must be
invisible to us in both directions.

## 3. The two weakened behaviours, tested as specified

ARCH-P section 5 marks requirements 4 and 6 weakened. They are **not**
regressions and must not be filed as such. The pass proves the weakened
contract, exactly as ruled, and records the residuals.

### 3.1 PO-2: the player may outlive plugin removal

What weakens: disabling or removing the plugin no longer kills the player
through `~Process()`. What replaces it is the **owner claim**, not the
destruction event, because `Component.onDestruction` fires on a graceful shell
exit too and cannot tell a restart from a removal.

`player orphan-check --owner-pid P --grace 6` sleeps 6 s, then reads
`user-data/omarchy-iptv-owner`:

| Claim state | Meaning | Action | Case |
|---|---|---|---|
| the claim's `pid` is no longer `P` | a successor service adopted the player | do nothing | PLY-WEAK-03, PLY-RST-17 |
| the claim is still `P` and pid `P` is alive with a matching start time | the service object died while its shell lives: the plugin was disabled or removed | **`player stop`** | PLY-WEAK-01, PLY-WEAK-02 |
| the claim is still `P` and pid `P` is dead | the shell exited and nothing claimed within 6 s | do nothing (`omarchy-launch-shell` supervises; a slow restart must not kill playback) | PLY-WEAK-04 |

PLY-WEAK-01 is PO-2's named acceptance gate. PLY-WEAK-03 is its mirror image
and is the more dangerous of the two: an orphan-check that stops on a plain
restart defeats the entire milestone, so both directions are asserted in the
same pass and on the same machine.

The residual is stated plainly and recorded, not filed: **a shell that is
SIGKILLed and never comes back leaves the player running until logout.** That
is not a regression - `Process::~Process()` only runs on a clean teardown
today, so a SIGKILLed quickshell leaves mpv alive in v0.2.0 as well - but it
is a longer window, and it is why the manual verb exists.

And the manual verb is the half that needs checking, not assuming.
PLY-WEAK-05 exists because the README tells the user to run
`omarchy-iptv player stop` and, verified read-only on this machine on
2026-09-14, **there is no `omarchy-iptv` on `PATH`**. The escape hatch that
makes PO-2's weakening acceptable has to be a command the user can actually
type. Run both forms, record both results.

### 3.2 PO-3: a failure while the shell is down is marked silently

What weakens: a failure that happens while no shell is attached cannot be
toasted at all. The proof that this is a platform fact and not a design choice
is worth re-running once as a static check:
`org.freedesktop.Notifications` is owned by quickshell itself and has no
activation file under `/usr/share/dbus-1/services/`, so `busctl` answers
"The name is not activatable" - **nothing on this machine can notify while the
shell is down**.

PO-3 rules option (a): mark the channel failed silently on reattach, using
`state.json.session` for the name, and show it in the guide. The red row
carries the information, and the guide is where the user goes next anyway.

**The procedure (PLY-WEAK-06), executable step by step.** Run it on the live
shell, from section 9.8 step 4. `$H` is the installed helper path,
`$S="$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock"`.

```
# 1. play a channel and confirm the session record exists
omarchy-shell io.github.rmcdavid.iptv play <id>
sleep 2
jq -c '.session' ~/.local/state/omarchy-iptv/state.json     # {"id":"<id>","name":"<name>","at":<epoch>}
MPV=$(pgrep -f -- "--input-ipc-server=$S"); echo "player $MPV"
NBEFORE=$(omarchy-shell notifications showHistory | wc -l); echo "notifications before: $NBEFORE"

# 2. take the shell down so nothing is attached
pkill -f 'quickshell -n -p /usr/share/omarchy/shell'
until ! pgrep -f 'quickshell -n -p /usr/share/omarchy/shell' >/dev/null; do :; done
kill -0 "$MPV" && echo "player still alive with no shell: correct"

# 3. the failure happens with nobody listening
kill -9 "$MPV"
until ! kill -0 "$MPV" 2>/dev/null; do :; done

# 4. bring the shell back
setsid omarchy-launch-shell >/dev/null 2>&1 &
until omarchy-shell shell ping >/dev/null 2>&1; do :; done

# 5. the assertions
omarchy-shell io.github.rmcdavid.iptv status | jq '{playing, nowPlaying, failedAt, player}'
#    expect: playing false, nowPlaying null, failedAt {"<id>":"HH:MM"}, player.up false
NAFTER=$(omarchy-shell notifications showHistory | wc -l)
[ "$NBEFORE" = "$NAFTER" ] && echo "no toast: correct"   # ZERO new lines is the ruling
jq -c '.session' ~/.local/state/omarchy-iptv/state.json   # null
stat -c '%a' ~/.local/state/omarchy-iptv/state.json       # 600

# 6. the guide half
omarchy-shell shell toggle io.github.rmcdavid.iptv
#    the channel's row carries U+F0026 in the trail slot and the detail line
#    reads `Failed HH:MM - Space to retry`; Space on it retries and clears the mark
```

Two notes on what "marked in the guide" means in the shipped build, so the
pass does not record a fail against the wrong expectation. `Model.rowDetail`
emits `Failed HH:MM` + `Space to retry`, and `Guide.qml` draws the alert glyph
U+F0026 in the trail slot at the row's own `primaryColor` with opacity 0.8 -
**it is not a red row**. The brief and the ruling both say "red"; the
implementation marks with a glyph and a detail line, consistent with every
other failed-row case since TC-PLAY-05. Settle the wording before the pass
(section 10 item 6) rather than filing a cosmetic defect against a ruling.

The ordering half (PLY-WEAK-08) is the part most likely to be wrong and
invisible. The probe answers in ~130 ms; `state.json` arrives whenever its
`FileView` loads. `deadSessionVerdict` returns `pending` on an unloaded state,
with `write:false`, precisely so that a caller can never write the empty
default over the user's file. Assert it directly: sha256 `state.json` before
the restart and after, on a restart with nothing playing, and require
identity apart from an intended `session` clear.

## 4. Automated inventory (what already exists at `363ce9c`)

Gate commands, verbatim from `CLAUDE.md`:

```
./scripts/check.sh          # validate + qmllint + node + python + qml spec
node tests/Model.test.js
python3 -m unittest discover -s tests
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/Model.spec.qml
omarchy plugin validate .
```

Baselines measured at `363ce9c` on 2026-09-14: **857 node checks, 0 failures**
(ARCH-P 10 expected the count to rise above 583 - it did); **247 python
tests, OK**, of which `tests/test_player.py` contributes **41**. Re-measure
against the fix lane's commit (section 1.8 item 5) and record both.

`tests/test_player.py`'s 41 cases already discharge PLY-HELP-01..08 and much
of PLY-LIFE and PLY-STOP. The named ones this plan depends on:
`test_spawns_once_and_sends_the_whole_wire_sequence_in_order`,
`test_spawn_argv_carries_no_url_no_header_and_no_channel_name`,
`test_first_load_failure_is_reported_by_start_itself`,
`test_a_live_player_is_adopted_and_zapped_never_duplicated`,
`test_stale_socket_is_unlinked_before_the_spawn`,
`test_a_regular_file_at_the_socket_path_blocks_and_never_spawns`,
`test_a_second_concurrent_start_reports_busy_and_never_spawns`,
`test_the_lock_file_being_replaced_mid_wait_is_detected_and_retried`,
`test_an_older_intent_is_superseded_and_touches_nothing`,
`test_the_lock_record_survives_for_the_probe_to_resume_the_sequence`,
`test_a_player_that_never_binds_is_reaped_by_the_helper_that_created_it`,
`test_a_missing_mpv_is_reported_through_the_errno_pipe`,
`test_quit_then_sigterm_at_2s_then_sigkill_at_4s`,
`test_from_term_skips_the_quit_rung`,
`test_a_recycled_pid_is_never_signalled`,
`test_a_socket_that_accepts_and_never_answers_is_not_responsive`,
`test_start_ladders_a_wedged_player_down_before_spawning`,
`test_merges_the_proc_half_and_the_socket_half_and_never_reads_path`,
the three `orphan-check` claim tests,
`test_nothing_in_the_runtime_dir_or_any_argv_or_any_line_carries_the_credential`,
the four parity tests against `tests/fixtures/player-argv.json`, and the two
`MpvIpc` event tests.

Two gaps this plan asks a lane to close (`A*` rows above depend on them):

1. **`tests/fixtures/qa-player/`** does not exist. Section 8.0 lists what it
   must hold.
2. `tests/Model.spec.qml` is the natural home for PLY-SVC-04's `playerUp`
   truth table under the real Qt/V4 engine, and for PLY-SOCK-03's null-guard.
   ARCH-P section 14 names this exact coverage gap: lane PB owned
   implementation and no test file. Confirm at the fix lane's commit whether
   it landed there or in `tests/Model.test.js`.

## 5. Security and privacy for this milestone

The claim under test, from ARCH-P section 6: **after M2-02 no stream URL and
no header value reaches any command line, any file, any unit name, any
environment variable or any log, on any channel, including the first.** The
proof is by enumeration of every sink, and the enumeration is what this
section runs.

**The sentinels.** One fixture channel carries every needle, so a single grep
answers every sink. Served from a loopback `python3 -m http.server` started
and killed by recorded PID, exactly as the M2-01 pass did - never a real
provider list for the sweep.

```
#EXTINF:-1 tvg-id="qa.sentinel" group-title="QA",QA Sentinel Channel
#EXTVLCOPT:http-user-agent=qa-ua-SENTINEL
#EXTVLCOPT:http-referrer=http://qa-ref-SENTINEL.test/
http://qa-user:qa-secret@127.0.0.1:8791/live/qa-token-XYZ/stream.m3u8
```

Needle set, used verbatim in every grep below:
`qa-user`, `qa-secret`, `qa-token-XYZ`, `qa-ua-SENTINEL`, `qa-ref-SENTINEL`,
`password=`, `username=`, `://`.

**The sinks, complete.** Anything not in this table that turns out to carry a
needle is a P1 by definition, because the design's claim is exhaustive.

| Sink | Command | Expected |
|---|---|---|
| mpv's command line, first channel | `tr '\0' ' ' < /proc/$MPV/cmdline` | 0 needles; `--idle=once` present; no trailing `--` |
| mpv's command line, after ten zaps | same | byte-identical to the above |
| every command line on the machine, sampled | section 9.3 step 4 sampler | 0 needles across the whole session |
| the helper's own argv | caught by the sampler | `--id`, `--socket`, `--cache-dir`, `--seq`, `--scope`, `--since`, `--owner-pid`, `--mpv-arg` only |
| a hand-started player present | sampler with PLY-RST-11 running | unchanged |
| `$XDG_RUNTIME_DIR/omarchy-iptv/*` | `grep -rlE '<needles>'` + `stat -c '%a %n'` | nothing; `700` dir, `600` socket, `600` lock |
| `~/.local/state/omarchy-iptv/state.json` | `jq . ` + `stat -c '%a'` | `session` = `{id,name,at}`, no URL, `600` |
| the journal | `journalctl --user -t omarchy-shell --since "$(cat $E/started-at)"` | 0 needles on `omarchy-iptv` lines; 0 lines from mpv at all |
| the shell console | `qs log -p /usr/share/omarchy/shell --tail 800` | 0 needles |
| IPC `status` | `omarchy-shell io.github.rmcdavid.iptv status` | 0 needles |
| notifications | `omarchy-shell notifications showHistory` | 0 needles; body is host-only |
| the window title | `hyprctl clients -j` | the channel name, literal; never a URL (PLY-SEC-18) |
| screenshots taken during the pass | `grim` output reviewed | no needle visible |
| `yt-dlp` | `ps aux \| grep -c '[y]t-dlp'` | `0` with default settings (PO-5) |

**The sampler (PLY-SEC-03, PLY-SEC-04, PLY-SEC-05).** The helper verbs live
about 130 ms, so a single `ps` proves nothing. Sample continuously across a
whole session - first channel, ten zaps, a failure, a stop, a restart, a
hand-started player:

```
E=/tmp/claude-1000/omarchy-iptv-qa5/live
( end=$((SECONDS+180)); while [ $SECONDS -lt $end ]; do
    for p in /proc/[0-9]*; do
      [ -r "$p/cmdline" ] || continue
      { tr '\0' ' ' < "$p/cmdline"; printf '\n'; } 2>/dev/null
    done
  done ) > $E/logs/cmdline-sweep.txt
wc -l $E/logs/cmdline-sweep.txt
grep -cE 'qa-user|qa-secret|qa-token-XYZ|qa-ua-SENTINEL|qa-ref-SENTINEL|password=|username=' $E/logs/cmdline-sweep.txt   # 0
grep -c 'omarchy-iptv player ' $E/logs/cmdline-sweep.txt        # > 0, proves the sampler saw the helper verbs
grep -oE 'omarchy-iptv (player [a-z-]+|play|stop|status)[^\n]*' $E/logs/cmdline-sweep.txt | sort -u | head -40
```

The second grep is the honesty check: a sweep that catches zero helper
invocations proves nothing about the helper, and a sampler too slow to see a
130 ms process would pass this table for the wrong reason. Record the sample
count and the number of distinct helper argv seen.

**What the sweep is expected to find, and must be recorded rather than
filed (PLY-SEC-05).** `--id t:qa.sentinel` on the helper's argv, and the
channel name on `omarchy-notification-send`'s argv when a stream fails. Both
are a per-event record of *what* is being watched, readable by another local
account through `/proc/<pid>/cmdline` (`0444`, `/proc` mounted without
`hidepid` here). Neither is a credential; both are unchanged from v0.2.0;
ARCH-P section 6 discloses the first explicitly. They are recorded in the
results with a count, and they are the evidence behind section 11 item 2.

**Two notes on why these sinks and not others.** `--log-file` and
`StandardError=append:` were rejected as the stderr replacement precisely
because they would write the full credentialed URL, seven times per failed
load, into a mode-0644 file at a forced `-v -v` level that `--msg-level`
cannot lower - a durable, world-readable version of the bug being fixed. That
is why `--log-file` is now in `MPV_RESERVED` (PLY-SEC-13) and why
PLY-SEC-07's file list is closed rather than illustrative. And mpv's stdio is
`/dev/null` from before `execvp`, which is load-bearing here because
`omarchy-launch-shell` runs `systemd-cat -t omarchy-shell -- quickshell`,
making the shell's stdout and stderr a persistent, group-readable journal
stream (PLY-SEC-09).

## 6. Performance

Method as QA.md section 4 and the M2-01 pass: `date +%s%N` around the IPC
call, with the `omarchy-shell shell ping` round trip subtracted as the
baseline; `hyprctl clients -j` polled every 50 ms for the window; mpv
`time-pos` read over the socket by a read-only helper. Every budget below
names its source, and says whether the number it is derived from was
**measured** on this machine or is **designed** (ARCH-P), because three of
the four have never been measured here.

| Budget | Source | Derived from |
|---|---|---|
| reattach: `nowPlaying` non-null <= 2000 ms | PLAN-M2 section 8 DoD ("the bar re-shows it within 2 s"), ARCH-P 7 | designed. Components: helper start ~125-130 ms (designed; measured analog 120-126 ms including spawn), probe IPC 2 s ceiling, socket attach one 250 ms tick (spike measured 132 ms first attach, 246 ms reattach) |
| probe answers <= 400 ms | ARCH-P 4.5 ("about 130 ms, the measured helper start cost") | designed, with 3x headroom |
| socket attached <= 3000 ms | SPIKE C6 cap: 12 tries x 250 ms | designed |
| stop clears the interface <= 150 ms | live IPC round trip median 67 ms, max 79 (QA-RESULTS P7) | measured |
| responsive player gone <= 500 ms | 219 / 238 / 261 ms and 230-263 ms across 8 cycles in v0.2.0 (QA-RESULTS D-LIVE-17 baseline) | measured |
| wedged player gone <= 4500 ms | ARCH-P 4.9 ladder (quit 0, TERM 2.0, KILL 4.0, settle 4.5); v0.2.0 recorded `term` at +2.45 s and gone at +4.17 s | measured + designed. **README says "about four seconds"; the settle is 4.5 s** (section 11 item 4) |
| zap to first frame < 2000 ms | PRODUCT / PERF-06 | measured: window mapped 378-457 ms warm, 803 ms on the first cold launch of a run |
| helper verb <= 300 ms | ARCH-P `(controlProc, ~125 ms)` | designed; measured analog 120-126 ms |
| journal <= 12 socket WARN lines per player death | SPIKE C6 and section 3's measurement (one WARN per failed attempt, no dedup, 120 lines for 120 attempts) | measured in the spike |
| guide open < 150 ms on the 10k cache | PLAN G3 / QB4 | measured: 69-75 ms live, 73 ms harness |
| shell RSS | informational, no budget | measured: 396 MB at the M2-01 pass |

The journal budget deserves its own sentence because it is the one new
performance risk this milestone introduces. A free-running 250 ms reattach
retry writes one `WARN quickshell.io.socket: Socket error for Socket(0x...)`
line per attempt to `/run/user/1000/quickshell/by-id/*/log.qslog` **and** the
journal, with no deduplication: four lines a second, roughly fourteen thousand
an hour. The C6 cap turns that into at most twelve lines per episode, and
PLY-PERF-04 is the case that proves the cap is real rather than intended.
Measure it three ways: after a single player death, across the PLY-RST-20 ten
restarts, and over a 30-minute idle session with nothing playing (where
`playerWanted` should be false and the count should be **zero**).

## 7. Regression surface

This milestone rewrote the playback path: the attached `Process`, `launchMpv`,
`handleMpvExit`, the QML stop ladder and the exit-code failure model are all
gone, replaced by a detached grandchild, a socket observer and an `end-file`
reason taxonomy. Everything downstream of that is re-run. Everything else is
skipped with a reason, so the skip list is auditable rather than implied.

### 7.1 Re-run from `docs/QA.md`

| Case | Why it must be re-run |
|---|---|
| TC-PLAY-01 | the launch path is entirely new; window, class and title now arrive over IPC, not argv |
| TC-PLAY-02 | zapping now goes through `apply_channel()` shared by `play` and `player start` |
| TC-PLAY-03 | the same-row re-select gate moved from `mpvProc.running` to `playerUp`; a false negative now costs one redundant idempotent start |
| TC-PLAY-04 | Space preview drives the same new path |
| TC-PLAY-05 | the failure model changed from exit code to `end-file.reason` + `file_error` + `log-message` |
| TC-PLAY-06 | `stop()` lost its early return and its QML ladder |
| TC-PLAY-07 | `q` in mpv is now `reason:"quit"` over the socket, not exit 0 |
| **TC-PLAY-08** | **inverted.** Headers must now be ABSENT from `ps -o args=`; the old expectation asserts the bug being fixed. Superseded by PLY-SEC-04 |
| TC-PLAY-09 | the health verdict now issues `player restart --from term`; the SIGKILL escalation that closed D-LIVE-17 moved into the helper |
| TC-PLAY-10 | zap bursts now race a lock and a sequence number |
| **TC-PLAY-11** | **inverted.** mpv must now SURVIVE the shell. Superseded by PLY-RST-01 |
| TC-PLAY-12, PERF-06 | the cold path gained a lock, a spawn poll and a first-load window; re-measure against the 2 s budget |
| TC-PLAY-14 | the overlay over a fullscreen player, now owned by a different process tree |
| TC-BAR-01, TC-BAR-03 | the bar reads `playing`, whose definition changed to `playerUp && nowPlaying !== null` |
| TC-BAR-07 | right click stop takes the new detached ladder |
| TC-BAR-09 | the wheel zap rings `launchedFrom`, which is now recovered from the stash |
| TC-CFG-08 | `MPV_RESERVED` gained ten entries and the tokens now travel as repeated `--mpv-arg` |
| TC-CFG-09, TC-CFG-10 | both render only while `playing` is true |
| TC-FAV-07 | "Recent recorded even when the stream fails" runs through the rewritten failure path |
| **TC-INST-05** | disabling the plugin now has a defined effect on the player (PO-2); the old expectation "mpv exits" is now the orphan-check's ~7 s, not `~Process()` |
| **TC-INST-08** | **inverted.** The restart round trip must now leave mpv alive |
| TC-INST-09 | `keepLoaded` across `rescanPlugins`, now also exercising the no-op orphan-check |
| TC-RFR-05 | refresh must still not interrupt playback, across a process boundary now |
| TC-UI-04 | now-playing cues driven by the new liveness |
| TC-A11Y-05 | focus and mpv; `focusPlayerArgv` is unchanged but the client's parent is not |
| TC-MODEL-06 | the mpv argv unit tests were deliberately rewritten, not restored |
| SEC-03 | header CR/LF validation still applies, now on the IPC path |
| SEC-05 | the stream scheme allow-list still gates what can be loaded |
| **SEC-06** | **rewritten.** "URL after `--`" is retired; the structural replacement is "every token after index 0 begins with `--`". Superseded by PLY-SEC-01 |
| SEC-07 | the sink set changed: `end-file`, `log-message`, `firstLoad.reason` and the `player` block in `status` are new sinks |
| SEC-13 | reserved `mpvArgs` names, with ten additions |
| SEC-14 | file modes, with `player.lock` added |
| SEC-17 | IPC acts only on cached ids; `--id` is now the only channel reference that crosses a process boundary |
| SEC-01 | the argv-only grep, extended to every new `Process` and `execDetached` call site |
| PERF-02, PERF-05 | cheap sanity: the service gained a socket object, two timers and a per-attempt dynamic object; prove the guide open budget and shell RSS are unmoved |
| PERF-07 | refresh must still not stall the shell |
| D-LIVE-15 original repro | "after the hung-mpv sequence the next play opened no window for 6.6 s" lived in exactly the code that was replaced |
| D-LIVE-17 original repro | "stop and health only send SIGTERM; a wedged mpv is never reaped" is the case the new ladder exists to close |

### 7.2 Re-run from `docs/QA-SOURCES.md`

| Case | Why |
|---|---|
| SRC-SW-08 | playback across a source switch: mpv untouched, same pid, `time-pos` advancing, `nowPlaying` kept - now also the `sourceKey` in the stash (PLY-RST-15) |
| SRC-RM-03, SRC-RM-09 | removing a source while it is playing; playback must continue |
| SRC-ERR-03 | a failed add must not displace the active source or the playback |
| SRC-LST-10, SRC-KEY-07 | `s` and `r` must not reach the player from the Sources screen or a focused field |
| SRC-SVC-05 | `activeCacheDir` becoming `""` must not confuse the reattach |
| SRC-LBL-09, SRC-SEC-06 | a hostile label must never reach a notification or an mpv title - the title now travels over IPC (PLY-SEC-18) |
| SRC-SEC-16 | an Xtream password must never reach mpv argv, notifications or IPC - the argv surface changed |
| SRC-SEC-18 | a hostile playlist (`${path}`, `-u critical` channel names) against the rendered rows and the new title path |
| SRC-H06, SRC-H07 | the two `--serve` harness scenarios; they are the only Sources scenarios that run a real player |

### 7.3 Skipped, with reasons

| Skipped | Reason |
|---|---|
| TC-BRW-01..25, TC-UI-01..03, 05..14, TC-A11Y-01..04, 06 | browse, keys, states, microcopy and theme are untouched: `Guide.qml` is unchanged at `363ce9c` except for rendering `failedAt`, which PLY-FAIL-12 and PLY-WEAK-06 exercise directly |
| TC-CFG-01..07, 11..13 | the settings schema is unchanged: ARCH-P 8 records **no new key** in `shell.json`, `manifest.json` unchanged, `keepLoaded: true` still required |
| TC-EPG-01..12 | the EPG path shares no code with playback |
| TC-RFR-01..04, 06..10 | refresh and offline behaviour is unchanged; only TC-RFR-05 (non-interference with playback) is affected |
| TC-FAV-01..06, 08..11 | favorites and recents are unchanged; `state.json` gains one optional nullable key covered by PLY-MIG-02 and the automated state tests. TC-FAV-07 is re-run because it is a failure-path case |
| TC-INST-01..04, 06, 07, 10 | install, validate, enable, update and remove mechanics are unchanged; TC-INST-05, 08 and 09 are re-run because the player's lifetime is what changed |
| TC-PARSE-01..11, TC-MODEL-01..05, 07, 08 | parsers and the non-player model functions are untouched and are covered by the 857-check node run and the 247-test python run every commit |
| SEC-02, 04, 08..12, 15, 16, 18..21 | no sudo, header names, local path rules, size caps, source schemes, plugin-dir writes, symlinks, QML network, XML entities, redirects, credentials at rest - none of these surfaces changed. SEC-15's plugin-dir `find` is folded into PLY-SEC-15 as a cheap by-product |
| PERF-01, PERF-03, PERF-04 | helper parse, keystroke latency and EPG parse are untouched by this milestone and were within budget at the last pass |
| SRC-* other than 7.2 | the Sources feature is untouched: `Model.js`'s source functions and `Guide.qml`'s Sources screens are outside the player path. If the in-flight fix lane touches source code in `Model.js`, promote the affected rows out of this skip list (section 1.8) |
| README `Limits` L1, L2 | playlist caps and the download deadline are unchanged by this milestone |

## 8. Harness runbook

Everything here lives entirely under `$OMARCHY_IPTV_HARNESS_DIR` (default
`$XDG_RUNTIME_DIR/omarchy-iptv-harness`). The harness exports its own
`XDG_RUNTIME_DIR`, so it **cannot** reach the live player, and its EXIT trap
reaps the detached grandchild by cmdline pattern.

### 8.0 Preconditions

- `tests/fixtures/qa-player/` must exist before the pass. It must hold: the
  sentinel channel of section 5; a dead-on-purpose channel
  (`http://127.0.0.1:9/nope.ts`) for the fast-failure cases; a channel with
  **no** headers, to prove header clearing between channels (requirement 7); a
  channel named `${path}` and one named `-u critical ${path}` for PLY-SEC-18
  and the S-04 rules; a channel with a non-ASCII name for the `user-data`
  round trip; a locally served MPEG-TS that plays and then ends cleanly, for
  PO-4's `eof`. Owner: lane PC (`PLAN-M2.md` section 5).
- `scripts/dev-harness/player-scenario.sh` exists at `363ce9c` with scenarios
  P1-P10 and a `--baseline <git-ref>` mode. Its header already records which
  checks must fail against the last pre-M2-02 commit (P2, P3, P4, P5, P6, P8)
  and that P10 is evidence against the first detached-player commit.
- `run.sh restart-shell`, `shell-stop`, `reap`, `--detach` and `--instance`
  exist at `363ce9c`.

### 8.1 Scenario map

`PLY-H01..H10` are the shipped `player-scenario.sh` scenarios; `PLY-H11..H18`
are new and must be added with the rule-11 evidence before the pass.
`PLY-H17` and `PLY-H18` phase A are the only two that need **no display and
no shell** - a stub mpv, the helper, and a gate at the handshake - so they are
the two a lane that does not hold the display can run and can point at another
tree itself: `qa-player-scenarios.sh run cold --apply`.

| # | Scenario | Maps to | Cases |
|---|---|---|---|
| PLY-H01 | cold start: one player, one window, class `omarchy-iptv`, title = channel (script P1) | shipped | PLY-LIFE-01 |
| PLY-H02 | S-03 argv + dead stream: no URL, credential, token, header value or channel name on mpv's command line; failure detected, channel marked, reason host-only (script P2, P7) | shipped | PLY-SEC-01, 02, 04, PLY-FAIL-01, 02, 03, 11, 12 |
| PLY-H03 | detachment and double start: the player is not a child of the shell; two starts spawn once (script P3) | shipped | PLY-LIFE-02, 08, 14, PLY-RST-12 |
| PLY-H04 | `restart-shell`: same pid, now-playing and zap ring recovered from the stash (script P4) | shipped | PLY-RST-01, 17, 18, PLY-SOCK-01, 02, 05, 08, 10 |
| PLY-H05 | SIGSTOP: two failed `status` polls, `player restart --from term`, SIGKILL lands, one relaunch (script P5 + the scenario's stop half) | shipped | PLY-LIFE-12, PLY-STOP-03, PLY-RST-07 |
| PLY-H06 | stale socket, regular file at the socket path (script P6 + additions) | shipped, extend | PLY-LIFE-04, 05, PLY-STOP-05 |
| PLY-H07 | stop: now-playing clears at once, nothing survives, socket unlinked (script P6) | shipped | PLY-STOP-01, 02, 08, 09, 11, PLY-WEAK-09 |
| PLY-H08 | two services, one runtime dir: adopt, never spawn (script P8, `--instance`) | shipped | PLY-RST-04 |
| PLY-H09 | zap, clean end and hard kill: `stop`+`start-file` raises nothing, `eof` is silent, `kill -9` with no `end-file` gives the generic failure (script P5 zap half, extend) | shipped, extend | PLY-FAIL-04, 05, 06, 08, 09, 10, PLY-SOCK-09 |
| PLY-H10 | superseded stop: a lock sequence pushed ahead does not turn every later stop into a silent no-op (script P10) | shipped | PLY-STOP-07 |
| PLY-H11 | **new.** restart at 0/100/300/600 ms after a zap | to add | PLY-RST-02 |
| PLY-H12 | **new.** restart inside the 3 s first-load window on a dead channel; count notifications before and after | to add | PLY-RST-03 |
| PLY-H13 | **new.** unlink the socket file under a live attached player; prove the connection survives, then prove the recovery path | to add | PLY-RST-06 |
| PLY-H14 | **new.** `rm -rf` the scratch runtime dir while playing; prove respawn into a fresh 0700 dir and the `playSeq` reset | to add | PLY-RST-08 |
| PLY-H15 | **new.** a stub mpv that never binds, and a PATH-shadowed missing mpv; plus a shell killed mid-cold-start | to add | PLY-LIFE-06, 07, PLY-RST-14 |
| PLY-H16 | **new.** the channel id disappears from `channels.json` between shells | to add | PLY-RST-16 |
| PLY-H17 | **new, written and run.** a cold start that is no longer the newest intent stands down. No display: a stub mpv holds the start at the handshake `probe_client` already waits on, the channel change lands, the start is released. **11 assertions, 11/11 here, 6 fail against `a939fd7`** | in `scripts/qa-player-scenarios.sh` | PLY-LIFE-16 |
| PLY-H18 | **new, written and run.** phase A (no display): `status` carries the player's own record, so the health tick has something to compare. Phase B (`--with-display`): the divergence converges within one health tick and `nowPlaying` is never relabelled. **Phase A 7 assertions, 7/7 here, 4 fail against `a939fd7`**; phase B is the display lane's | in `scripts/qa-player-scenarios.sh` | PLY-LIFE-17 |

### 8.2 Common invocation

```
H=scripts/dev-harness/run.sh
$H clean
$H --detach --serve --playlist tests/fixtures/qa-player/qa-player.m3u --timeout 0
$H player-scenario                      # PLY-H01..H10, one PASS/FAIL line per check
$H player-scenario --baseline <last pre-M2-02 ref>   # rule 11: the same checks must fail there
$H restart-shell                        # PLY-H04
$H reap
```

Every new `PLY-Hnn` follows the same pattern and records **both** counts. A
scenario that passes on both trees is not evidence for this milestone; it is a
regression guard and is labelled as one.

## 9. Live-shell runbook (this machine; the lead holds the display)

Every acceptance gate for M2-02 is a live-shell gate - the PO's words, and the
reason is in the feature itself: no fake can simulate a shell restart. This
section is written to be executed step by step. `$E` is the evidence root,
`$H` the installed helper, `$S` the live socket.

### 9.0 Preconditions and what the pass changes on this machine

- Files touched: `~/.config/omarchy/plugins/io.github.rmcdavid.iptv` (checked
  out to the RC commit and back), `~/.config/omarchy/shell.json` (via
  `omarchy bar set` and `omarchy plugin disable/enable`),
  `~/.cache/omarchy-iptv`, `~/.local/state/omarchy-iptv`,
  `$XDG_RUNTIME_DIR/omarchy-iptv`, and `$E`. Nothing under
  `/usr/share/omarchy` is touched. No sudo.
- Destructive steps that need the lead's explicit go-ahead before the pass
  (section 10 item 3): `pkill -KILL` of the shell (9.5 step 4), plugin
  disable and remove (9.7), and logout (9.9 step 2).
- `pgrep -x hyprlock` must be empty before any keystroke (CLAUDE.md rule 6).
- `wtype` cannot drive `SUPER + SHIFT + T` (a Hyprland global bind); open the
  guide with `omarchy-shell shell toggle io.github.rmcdavid.iptv`, which is
  the string the keybinding runs.
- `pkill -f` patterns must not match the QA shell's own argv - a known trap
  from the M2-01 live pass. Prefer `pkill -f 'quickshell -n -p /usr/share/omarchy/shell'`
  and verify the match set with `pgrep -af` first.

### 9.1 Snapshot (read-only)

```
E=/tmp/claude-1000/omarchy-iptv-qa5/live; mkdir -p $E/{snapshot,logs,shots}
S="$XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock"
P=~/.config/omarchy/plugins/io.github.rmcdavid.iptv
H="python3 $P/bin/omarchy-iptv"
date +%FT%T > $E/started-at
cp ~/.config/omarchy/shell.json $E/snapshot/shell.json.before
cp ~/.local/state/omarchy-iptv/state.json $E/snapshot/state.json.before
cp -a ~/.cache/omarchy-iptv $E/snapshot/cache.before
sha256sum ~/.config/omarchy/shell.json ~/.local/state/omarchy-iptv/state.json > $E/snapshot/sha.before
find ~/.cache/omarchy-iptv ~/.local/state/omarchy-iptv -exec stat -c '%a %n' {} + > $E/snapshot/modes.before
ls -la "$XDG_RUNTIME_DIR/omarchy-iptv" > $E/snapshot/runtime.before 2>&1
omarchy-shell io.github.rmcdavid.iptv status > $E/snapshot/status.before.json
jq '.version, (.recents|length), (.favorites|length), .session' ~/.local/state/omarchy-iptv/state.json
git -C $P rev-parse HEAD > $E/snapshot/plugin-head.before
git -C $P status -sb >> $E/snapshot/plugin-head.before
omarchy theme current > $E/snapshot/theme.before
systemctl --user show wayland-wm@hyprland.desktop.service -p ExitType -p KillMode -p TimeoutStopUSec > $E/snapshot/unit.txt
loginctl show-user 1000 -p Linger >> $E/snapshot/unit.txt
```

Expected at the start: `/run/user/1000/omarchy-iptv` is `700` and **empty**
(verified 2026-09-14), no mpv, `session` is absent or null.

### 9.2 Move the installed clone to the release candidate

```
git -C $P fetch origin
git -C $P checkout <RC commit>
omarchy plugin validate $P            # exit 0
omarchy restart shell
until omarchy-shell shell ping >/dev/null 2>&1; do :; done
omarchy-shell io.github.rmcdavid.iptv status | jq '{configured, channels, player}'
```

Expect: the widget is back, `player.up false`, `player.wanted false`,
`nowPlaying null`, and the runtime directory is still empty (a probe that
finds nothing must not create a socket or a lock).

### 9.3 Baseline play and the S-03 sweep (PLY-SEC-01..18)

Serve the sentinel fixture on loopback, add it as a source, and start the
180 s sampler of section 5 in the background **before** the first play.

```
# step 1: serve and configure (record the server PID for the teardown)
( cd $E/fixtures && python3 -m http.server 8791 >/dev/null 2>&1 & echo $! > $E/httpd.pid )
omarchy bar set io.github.rmcdavid.iptv playlistUrl http://127.0.0.1:8791/qa-player.m3u

# step 2: the FIRST channel of the session
omarchy-shell io.github.rmcdavid.iptv play t:qa.sentinel
MPV=$(pgrep -f -- "--input-ipc-server=$S"); echo "$MPV" > $E/logs/mpv.pid
tr '\0' ' ' < /proc/$MPV/cmdline | tee $E/logs/mpv-cmdline.txt
grep -cE 'qa-user|qa-secret|qa-token-XYZ|qa-ua-SENTINEL|qa-ref-SENTINEL|://' $E/logs/mpv-cmdline.txt   # 0
grep -c -- '--idle=once' $E/logs/mpv-cmdline.txt                                                       # 1
ps -ww -C mpv | grep -c '://'                                                                          # 0  (PLAN-M2 DoD)
pgrep -c -f wayland-app-id=omarchy-iptv                                                                # 1  (PLAN-M2 DoD)

# step 3: ten zaps, then the same argv
for i in $(seq 10); do omarchy-shell io.github.rmcdavid.iptv next; sleep 1; done
tr '\0' ' ' < /proc/$MPV/cmdline > $E/logs/mpv-cmdline-after.txt
diff $E/logs/mpv-cmdline.txt $E/logs/mpv-cmdline-after.txt      # no output

# step 4: the sampler (section 5), run across steps 2-5 and the 9.4 restart
# step 5: environment and the disclosed residual
grep -c setenv $E/logs/mpv-cmdline.txt                          # 0
grep -oE '\-\-id [^ ]+' $E/logs/cmdline-sweep.txt | sort | uniq -c

# step 6: every artifact on disk
find "$XDG_RUNTIME_DIR/omarchy-iptv" ~/.local/state/omarchy-iptv -exec stat -c '%a %n' {} + | tee $E/logs/modes.txt
grep -vE '^(700|600) ' $E/logs/modes.txt                        # no output
cat "$XDG_RUNTIME_DIR/omarchy-iptv/player.lock"                 # one line, seq only, no URL
grep -rlE 'qa-user|qa-secret|qa-token-XYZ|://' "$XDG_RUNTIME_DIR/omarchy-iptv"   # no output
ls -la "$XDG_RUNTIME_DIR/omarchy-iptv"                          # mpv.sock + player.lock, nothing else

# step 7: every other sink
omarchy-shell io.github.rmcdavid.iptv status | tee $E/logs/status.json | grep -cE '://|password=|username='   # 0
qs log -p /usr/share/omarchy/shell --tail 800 > $E/logs/qslog.txt
grep omarchy-iptv $E/logs/qslog.txt | grep -cE 'qa-secret|qa-token-XYZ|://'                                   # 0
journalctl --user -t omarchy-shell --since "$(cat $E/started-at)" > $E/logs/journal.txt
grep omarchy-iptv $E/logs/journal.txt | grep -cE 'qa-secret|qa-token-XYZ|://'                                 # 0
grep -c 'mpv\[' $E/logs/journal.txt                                                                           # 0
omarchy-shell notifications showHistory > $E/logs/notifications.txt
grep -cE 'qa-secret|qa-token-XYZ|://' $E/logs/notifications.txt                                               # 0

# step 8: PO-5
ps aux | grep -c '[y]t-dlp'                                                                                   # 0
grep -n 'ytdl' $P/README.md                                                                                   # the PO-5 cost sentence must be there

# step 9: argv only, no writes in the plugin dir
grep -rn "sudo\|shell=True\|bash -c\|eval(" $P --include='*.qml' --include='*.js' --include='omarchy-iptv' | grep -v '/tests/\|/docs/'   # nothing
find $P -newer $P/manifest.json -not -path '*/.git/*'                                                         # nothing

# step 10: S-01 on the IPC path
omarchy-shell io.github.rmcdavid.iptv play 'u:<id of the ${path} channel>'
hyprctl clients -j | jq -r '.[] | select(.class=="omarchy-iptv") | .title'    # literal ${path}, never a URL
```

### 9.4 The headline restart (PLY-RST-01, 13, 17, 18, 19; PLY-PERF-01)

```
# step 0: with nothing playing
omarchy-shell io.github.rmcdavid.iptv stop; sleep 1
omarchy restart shell; until omarchy-shell shell ping >/dev/null 2>&1; do :; done
omarchy-shell io.github.rmcdavid.iptv status | jq '{nowPlaying, failedAt, player}'
#   expect nowPlaying null, failedAt {}, player.up false, player.wanted false
grep -c 'quickshell.io.socket' $E/logs/journal.txt   # unchanged: no retry storm with nothing wanted

# step 1: play and capture the before-state
omarchy-shell io.github.rmcdavid.iptv play <live channel id>
MPV=$(pgrep -f -- "--input-ipc-server=$S")
ST=$(awk '{print $22}' /proc/$MPV/stat)
omarchy-shell io.github.rmcdavid.iptv status | jq -c '{id:.nowPlaying.id,name:.nowPlaying.name,from:.nowPlaying.launchedFrom}' > $E/logs/np.before

# step 2: prove detachment before touching anything
ps -o ppid= -p $MPV; ls -l /proc/$MPV/fd/0 /proc/$MPV/fd/1 /proc/$MPV/fd/2
diff <(cat /proc/$MPV/cgroup) <(cat /proc/$(pgrep -f 'quickshell -n -p /usr/share/omarchy/shell')/cgroup)

# step 3: sample the window count across the restart, in the background
( for i in $(seq 200); do hyprctl clients -j | jq '[.[]|select(.class=="omarchy-iptv")]|length'; sleep 0.1; done ) > $E/logs/window-count.txt &

# step 4: the restart, timed
t0=$(date +%s%N); omarchy restart shell
until omarchy-shell shell ping >/dev/null 2>&1; do :; done; t1=$(date +%s%N)
while :; do n=$(omarchy-shell io.github.rmcdavid.iptv status 2>/dev/null | jq -r '.nowPlaying.id // empty'); [ -n "$n" ] && break; done
t2=$(date +%s%N)
while :; do a=$(omarchy-shell io.github.rmcdavid.iptv status 2>/dev/null | jq -r '.player.attached'); [ "$a" = "true" ] && break; done
t3=$(date +%s%N)
echo "shell $(( (t1-t0)/1000000 )) ms | nowPlaying $(( (t2-t1)/1000000 )) ms | attached $(( (t3-t1)/1000000 )) ms"

# step 5: the assertions
[ "$MPV" = "$(pgrep -f -- "--input-ipc-server=$S")" ] && echo "same pid"
[ "$ST" = "$(awk '{print $22}' /proc/$MPV/stat)" ] && echo "same start time"
sort -u $E/logs/window-count.txt        # only "1"
diff <(omarchy-shell io.github.rmcdavid.iptv status | jq -c '{id:.nowPlaying.id,name:.nowPlaying.name,from:.nowPlaying.launchedFrom}') $E/logs/np.before
sleep 10; kill -0 $MPV && echo "orphan-check was a no-op at t+10 s"   # PLY-RST-17
# zap ring: scroll the bar wheel once and confirm the next channel is from launchedFrom's list
# theme and rescan (PLY-RST-19)
omarchy theme set tokyo-night; sleep 2; omarchy theme set "$(cat $E/snapshot/theme.before)"
omarchy-shell shell rescanPlugins; sleep 2
[ "$MPV" = "$(pgrep -f -- "--input-ipc-server=$S")" ] && echo "same pid after theme + rescan"
```

Repeat steps 4-5 five times for PLY-PERF-01's medians.

### 9.5 The nasty restarts (PLY-RST-02..06, 11, 15)

1. **Mid-zap (PLY-RST-02).** Four runs. `omarchy-shell ... play <other id>`
   then `omarchy restart shell` after 0, 100, 300, 600 ms. Each run: assert
   one player, and that `status.nowPlaying` matches `hyprctl`'s window title.
2. **While failing (PLY-RST-03).** `play t:qa.sentinel-dead`, restart inside
   3 s. Count `omarchy-shell notifications showHistory | wc -l` before and
   after; assert `failedAt` has the id and the count grew by at most 1 total.
3. **Overlapping shells (PLY-RST-04).** Drive this on the harness
   (`$H --instance B`), not the live session - two live shells is not a state
   this machine can hold safely.
4. **Killed, not stopped (PLY-RST-05).** `pkill -KILL -f 'quickshell -n -p
   /usr/share/omarchy/shell'`; assert the player is alive and `time-pos` is
   advancing 3 s later; let `omarchy-launch-shell` bring it back (or start it
   by hand) and repeat 9.4 step 5.
5. **Socket removed (PLY-RST-06).** `rm "$S"` while attached and playing.
   Assert playback continues, a zap over the existing connection still works,
   then run `$H player probe --socket "$S"` and assert `responsive:false` and
   the ladder-and-respawn.
6. **Hand-started foreign player (PLY-RST-11).** Start
   `mpv --wayland-app-id=omarchy-iptv --input-ipc-server=/tmp/qa-player-foreign.sock
   --idle=yes --force-window=immediate --vo=null --ao=null`. Assert
   `player probe` reports only ours; run a stop and assert the foreign pid is
   still alive; run the 9.3 sampler again. Record the two documented
   consequences. Kill the foreign player by its recorded pid afterwards.
7. **Different active source (PLY-RST-15).** Switch to the other source, then
   restart. Assert the bar keeps the name, no row shows as playing, and the
   wheel does not ring a wrong list.

### 9.6 Stop ladder (PLY-STOP-01..11; PLY-LIFE-03, 12; PLY-PERF-02)

1. **Cold-start hammer (PLY-LIFE-03).** From nothing playing, alternate Enter
   on two channels 20 times as fast as the guide accepts, with the
   window-count sampler running. `sort -u` the samples: only `0` and `1`.
2. **The three affordances (PLY-STOP-01, 11).** `s` in list mode, right click
   on the bar, `omarchy-shell ... stop`. For each: time the interface clear
   and the process end; assert no notification; assert one `player stop` issue
   in the console.
3. **Wedged (PLY-STOP-03, PLY-LIFE-12, PLY-RST-07).** `kill -STOP $MPV`.
   First let the health check run (expect the unresponsive line at ~21 s and
   `player restart --from term`). Read the **intent counter** either side of
   it - `$H ipc status | jq '.player.seq'` before the wedge and after the
   respawn - and assert the delta is **exactly 1**. Do **not** count the
   journal string: it reads 1 on a fixed tree and 1 on a broken one alike
   (**CL10**, and section 14 item 5). Then, on a fresh SIGSTOPped player,
   press stop and time the rungs: TERM at ~2.0 s, KILL at ~4.0 s, window gone
   by 4.5 s, `hyprctl` count 0. **Assert the socket file is gone**, and assert
   it as a file rather than as a mechanism:

   ```
   sleep 0.5; ls "$S" ; echo "exit=$?"     # expect exit 2: No such file or directory
   sleep 30;  ls "$S" ; echo "exit=$?"     # expect exit 2 again
   ```

   Make **no** `probe`, `status` or `play` call of your own in between - any
   helper call unlinks it, and a run that made one proves nothing. Five wedged
   and five responsive; 10/10 at `a939fd7`, where it was 5/5 the other way at
   `8f9447e` and `b16b479` (**D-PLY-8**). Then, on a third SIGSTOPped player,
   `omarchy restart shell` and assert the probe's wedged branch.
4. **Shell dies mid-ladder (PLY-STOP-04).** Stop a SIGSTOPped player, then
   `pkill -KILL` the shell 200 ms later. Assert the player is gone by 4.5 s
   with no shell running.
5. **Superseded stop (PLY-STOP-07).** Push the lock sequence ahead from a
   terminal:
   `$H player stop --socket "$S" --seq 999999`. Play a channel, then press
   `s`. Assert the interface clears **and the player actually stops**; assert
   the `stopSettleTimer` line appears in the console within 5 s if the first
   stop was refused. **The interface idle with the player still playing is a
   P1.**

### 9.7 PO-2: disable and remove (PLY-WEAK-01..05)

Needs the lead's go-ahead. `omarchy plugin disable` removes the widget entry
from the bar **and the settings stored on it**, so `9.12` re-runs the
`omarchy bar set` lines afterwards.

```
# step 1: disable while playing
omarchy-shell io.github.rmcdavid.iptv play <id>; MPV=$(pgrep -f -- "--input-ipc-server=$S")
t0=$(date +%s%N); omarchy plugin disable io.github.rmcdavid.iptv
while kill -0 $MPV 2>/dev/null; do sleep 0.2; done; t1=$(date +%s%N)
echo "orphan-check stop $(( (t1-t0)/1000000 )) ms"     # expect ~6000-7000 ms
ls -la "$XDG_RUNTIME_DIR/omarchy-iptv"                 # socket unlinked

# step 2: re-enable, reconfigure, then remove while playing (same assertions)
# step 3: the residual - pkill -KILL the shell while playing and do NOT bring it back
#         for 30 s; assert the player is still alive; then bring the shell back. RECORD, do not file.
# step 4: the documented escape hatch
command -v omarchy-iptv; echo "exit=$?"                # verified 2026-09-14: exit 1, NOT on PATH
$H player stop --socket "$S"                           # the runnable form; player gone within 4.5 s
```

### 9.8 PO-3 and the failure paths (PLY-FAIL-01, 07, 11; PLY-WEAK-06..09)

1. **First-channel failure (PLY-FAIL-01).** From nothing playing, play the
   dead sentinel channel. Assert exactly one toast within ~3 s, body
   `"QA Sentinel Channel" did not play - http://127.0.0.1`, glyph U+F0503,
   urgency normal, `-r 74011`; the row marks; `failedAt` has the id.
2. **`q` in mpv (PLY-FAIL-07).** Focus the player, press `q`. Bar idle, cues
   clear, no notification.
3. **Hard kill while attached (PLY-FAIL-08).** `kill -9 $MPV`. One toast with
   the generic reason within ~1 s of the EOF.
4. **PO-3, the full procedure.** Section 3.2's block, verbatim.
5. **The negatives (PLY-WEAK-07, 09).** (a) Restart with `session` null:
   assert no mark, no toast, and `sha256sum` of `state.json` unchanged.
   (b) Stop cleanly, restart: assert `session` null and `failedAt` empty.
   (c) Let the locally served clean-EOF channel run to its end, restart:
   assert no mark (PO-4 + PLY-WEAK-09).

### 9.9 Suspend, logout, migration (PLY-RST-09, 10; PLY-MIG-01)

1. **Suspend (PLY-RST-09).** Only with the lead present at the machine:
   play, `systemctl suspend`, wake, and within 10 s assert the same pid, the
   socket attached or reattaching, and the same `nowPlaying`. Otherwise record
   `not run` with the reason.
2. **Logout (PLY-RST-10).** The **last act** of the pass, after 9.11 and
   9.12: play a channel, log out, log back in, and assert
   `pgrep -f 'omarchy-iptv/mpv.sock'` is empty. The static half
   (`$E/snapshot/unit.txt` plus the mpv cgroup) is already captured.
3. **Migration (PLY-MIG-01).** Start a v0.2.0-shaped player by hand against
   our socket path (URL on argv, `--idle=no`, no `user-data` stash), then
   restart the shell: assert "unknown player" -> one 500 ms re-probe ->
   `player stop` -> idle, and that one Enter restores service.

### 9.10 Performance and the journal (PLY-PERF-02..07; PLY-SOCK-11)

1. **Zap (PLY-PERF-03).** Three channels x three runs, `hyprctl clients -j`
   polled every 50 ms from the Enter; separate the cold first launch of the
   run from the warm ones, as previous passes did.
2. **Journal (PLY-PERF-04).** Three measurements: after one player death;
   across the ten restarts of step 3; and over a 30-minute idle session with
   nothing playing. `journalctl --user -t omarchy-shell --since <t> | grep -c
   'quickshell.io.socket'` and `grep -c 'Socket error'
   /run/user/1000/quickshell/by-id/*/log.qslog`.
3. **Ten restarts (PLY-RST-20, PLY-PERF-06).** `for i in $(seq 10)` around
   9.4 step 4, sampling `ls /proc/<shell>/fd | wc -l` and `ps -o rss=` before,
   at five and after.
4. **Socket churn (PLY-SOCK-11).** Ten player kill/restart cycles plus a
   deliberate 120-attempt failed-retry burst (kill the player and leave it
   dead for 30 s with `playerWanted` armed): fds flat within 2, CPU ticks
   single-digit, RSS flat.
5. **Guide open (PLY-PERF-07).** QA.md PERF-02 Method A, median of 5.

### 9.11 Evidence capture

```
cp $E/logs/*.txt $E/logs/*.json $E/
hyprctl clients -j > $E/logs/clients.json
omarchy-shell io.github.rmcdavid.iptv status > $E/logs/status.after.json
grim $E/shots/guide-failed-row.png        # the PO-3 marked row
grim $E/shots/playing.png
date +%FT%T > $E/finished-at
```

### 9.12 End state and undo (byte-for-byte)

```
# stop everything this pass started
$H player stop --socket "$S"
kill "$(cat $E/httpd.pid)" 2>/dev/null; rm -f $E/httpd.pid
pkill -f 'input-ipc-server=/tmp/qa-player-foreign.sock' 2>/dev/null

# restore the installed clone and the user's files
git -C $P checkout "$(cat $E/snapshot/plugin-head.before | head -1)"
cp $E/snapshot/shell.json.before ~/.config/omarchy/shell.json
cp $E/snapshot/state.json.before ~/.local/state/omarchy-iptv/state.json
rm -rf ~/.cache/omarchy-iptv && cp -a $E/snapshot/cache.before ~/.cache/omarchy-iptv
rm -f "$XDG_RUNTIME_DIR/omarchy-iptv/player.lock" "$S"
omarchy restart shell
until omarchy-shell shell ping >/dev/null 2>&1; do :; done

# prove it
sha256sum -c $E/snapshot/sha.before
diff <(jq -S . $E/snapshot/shell.json.before) <(jq -S . ~/.config/omarchy/shell.json)          # no output
diff -r $E/snapshot/cache.before ~/.cache/omarchy-iptv                                        # no output
diff <(find ~/.cache/omarchy-iptv ~/.local/state/omarchy-iptv -exec stat -c '%a %n' {} +) $E/snapshot/modes.before
diff <(omarchy-shell io.github.rmcdavid.iptv status | jq -S 'del(.lastUpdated)') <(jq -S 'del(.lastUpdated)' $E/snapshot/status.before.json)
git -C $P status -sb; git -C $P rev-parse HEAD
ls -la "$XDG_RUNTIME_DIR/omarchy-iptv"      # back to 700 and empty, as found on 2026-09-14
pgrep -af -- '--wayland-app-id=omarchy-iptv'   # nothing
omarchy theme current                           # matches theme.before
```

The service re-stamps `lastUsed` on start, so `state.json` may differ by that
one field after the restart; write the snapshot back a second time if so and
re-check 10 s later, as the M2-01 pass did. Anything else that differs is
recorded in `$E/UNDO.txt` with a reason. Two values may legitimately differ:
`lastUpdated` in `status` (time), and a source's `channelCount` if the pass
forced a refetch and the upstream list drifted.

## 10. What this plan cannot prove on this machine

Recorded so nobody mistakes silence for coverage.

1. **A second monitor.** One 1366x768 output. The player's placement and the
   guide over it on a second output are not exercised; TC-A11Y-04's standing
   `not run` carries over.
2. **Mouse.** This machine carries no pointer-injection tool (`ydotool`,
   `wlrctl`, `dotool`, `xdotool` all absent, no ydotool socket) and Hyprland
   exposes no click dispatcher, so the bar's right-click stop (TC-BAR-07) and
   wheel zap (TC-BAR-09) cannot be driven from a script. Installing a tool
   needs sudo, which the pass forbids. Either a human drives those two rows or
   they are recorded `blocked`, not `pass` from a keyboard run.
3. **`SUPER + SHIFT + T`.** `wtype` cannot exercise Hyprland global binds. The
   bind is registered and its command works; the runbook opens the guide with
   the IPC verb instead, so "the keybinding opens the guide" is inferred, not
   proven.
4. **Suspend and resume (PLY-RST-09).** `systemctl suspend` ends the session
   the QA run is inside and needs a physical wake, so it cannot be scripted to
   completion. Worse, the designed behaviour is *no stall detection* - so even
   a successful run only proves "unchanged from v0.2.0", never "the stream
   recovered". A stalled stream after resume is invisible to `status` by
   design.
5. **Logout (PLY-RST-10).** Proving it ends the session and therefore the
   pass; it can only be the last act, with the result read after the next
   login, and it cannot be repeated for a median. The static half (unit
   `ExitType`/`KillMode`/`TimeoutStopUSec`, `Linger=no`, the mpv cgroup) is
   read, not exercised.
6. **A genuinely wedged mpv.** D-LIVE-17's original trigger - an mpv that
   mapped its window and never came up on IPC - happened once in 24 launches
   and is not reproducible on demand. `kill -STOP` is the deterministic
   stand-in and is **not the same fault**: it is a stopped process, not a
   process with a broken IPC thread. A pass on PLY-STOP-03 does not prove the
   original defect cannot recur.
7. **mpv missing (PLY-LIFE-07).** mpv is an Omarchy dependency; removing it
   needs sudo. Only the harness's PATH-shadowed stub can exercise it, so the
   live half stays `not run`, as TC-PLAY-13 has since M1.
8. **Cross-account exposure.** PLY-SEC-05 proves what a command line *says*;
   it does not prove another local account can read it, because this machine
   has one human uid. `/proc` is mounted without `hidepid` here, which is the
   evidence for the claim, not a demonstration of it.
9. **A real provider failing.** An expiring subscription, a provider rotating
   a source mid-session (PO-4's motivating case) and a genuine mid-stream
   stall cannot be provoked. Loopback fixtures stand in for all three, and a
   fixture that 404s is not the same as a subscription that expires.
10. **Two real logins at once.** `Linger=no` is read from `loginctl`, never
    exercised; no cross-session orphan is demonstrated, only argued from the
    cgroup.
11. **The 250 ms reattach against a slow real player.** The spike measured
    132 ms and 246 ms against a python `FakeMpv` and a headless mpv with
    `--vo=null --ao=null`. A real player with a decoder, a window and a live
    stream has not been measured; PLY-PERF-01 is the first time it will be.
12. **Whatever the in-flight fix lane changes.** Section 1.8. Everything in
    this plan is written against `363ce9c`.
13. **Hyprland focus with a foreign player present.** PLY-RST-11 records that
    `hyprctl dispatch focuswindow class:omarchy-iptv` may focus the user's own
    mpv. Narrowing focus to `hyprctl clients -j` matched by pid is deferred by
    ARCH-P 7, so the case confirms the consequence rather than testing a fix.

## 11. Contradictions and gaps found while planning

Raised as numbered items rather than resolved locally (CLAUDE.md: collect
conflicts as numbered decision requests and raise the batch). Each is a
candidate `D-PLY-n`; the lead decides which are defects and which are plan
edits before the pass, so that QA does not file a defect against a ruling or
pass a case against stale copy.

1. **README `Playback notes` bullet 3 contradicts PO-4.** It reads "A stream
   that fails **or ends** shows a desktop notification naming the channel."
   PO-4 rules the opposite for the "ends" half: "Keep a clean end silent. Zero
   behavior change." Either the README sentence loses "or ends", or PO-4 is
   revisited. Until it is settled, PLY-FAIL-06 has two mutually exclusive
   expected results. Suggested: P3 documentation, fix the README.
2. **README `Playback notes` bullet 5 overstates the `ps` guarantee.** "so
   `ps` shows nothing about what you are watching" is contradicted by ARCH-P
   section 6's own disclosed residual (`--id` on the helper's argv is a
   per-zap record of what is being watched, readable through `/proc`) and by
   `Model.notifyArgv`, which puts the channel name on
   `omarchy-notification-send`'s command line on every failure. The URL claim
   in the same bullet is exactly right and is the milestone's achievement;
   the *nothing* claim is not. Suggested: P2 documentation, reword to "no
   stream URL, header or credential". (ARCH-P section 6 also names
   `--force-media-title` as part of that residual, which is stale: section
   4.11 fixes it to the constant `IPTV`.)
3. **PO-2's escape hatch is not a runnable command.** The README tells the
   user to run `omarchy-iptv player stop`; verified read-only on 2026-09-14,
   `omarchy-iptv` is not on `PATH` and there is no wrapper in `/usr/bin` or
   `~/.local/bin`. PO-2 also states the verb belongs "in the README's
   uninstall section", and the Uninstall block does not mention it. The whole
   acceptability of weakening requirement 4 rests on this command. Suggested:
   P2, either ship a wrapper or document the `python3 <plugindir>/bin/...`
   form, and add it to Uninstall.
4. **"within about four seconds" vs a 4.5 s settle.** README bullet 4 promises
   four seconds; the ladder is quit@0, TERM@2.0, KILL@4.0, settle@4.5, and
   ARCH-P 10's own `PLAYER-LIVE-05` says "within ~4.5 s". Harmless, but
   PLY-PERF-02's budget has to be one or the other. Suggested: P3, say "about
   four and a half seconds" or keep the budget at 4.5 s and leave the prose.
5. **`player.lock` is undocumented.** README `Files it writes` lists the
   socket but not the lock, although ARCH-P 6 lists it as one of exactly two
   new artifacts. Suggested: P3, one line.
6. **"A red row" is not what the guide draws.** PO-3, the brief and ARCH-P all
   say the channel is marked with a red row. `Model.rowDetail` emits
   `Failed HH:MM` + `Space to retry` and `Guide.qml` draws U+F0026 in the
   trail slot at the row's own `primaryColor`, opacity 0.8 - consistent with
   every failed-row case since TC-PLAY-05, and not red. Settle the wording so
   PLY-WEAK-06 is not recorded as a fail against a colour nobody implemented.
   Not a defect; a plan expectation to confirm.
7. **ARCH-P sections 4.9 and 4.10 are wrong as written.** Section 14 records
   the correction (a detached stop cannot observe a `superseded` refusal, and
   every stop became a silent no-op once any other launcher pushed the
   sequence ahead - including the `player stop` the README tells users to
   run). The document itself says so; this plan tests the corrected behaviour
   at PLY-STOP-07 and flags it here so nobody reads 4.9 as current.
8. **ARCH-P section 8's docs edits may not have landed.** It budgets
   inverting `QA.md` TC-PLAY-11 and rewriting TC-PLAY-08 and SEC-06 at
   `M2-02-04`. At `363ce9c` those rows still carry the pre-M2-02
   expectations, so the section 7.1 re-run will read three "failures" that are
   really stale expectations. This plan marks all three **inverted /
   rewritten**; confirm the QA.md edits land with the RC or the pass records
   them against this file instead.
9. **CHANGELOG has no 0.3.0 section.** The PO's non-optional addition requires
   both weakened requirements in the release notes, and `CHANGELOG.md` at
   `363ce9c` stops at 0.2.1. PLY-WEAK-10's second half cannot pass until it
   exists. Release-gate item, not a code defect.
10. **`tests/fixtures/qa-player/` does not exist**, although `PLAN-M2.md`
    section 5 assigns it to lane PC alongside this document and several `A*`
    rows depend on it. Section 10 item 7 of the questions below.

## 12. Defect template

One row in `docs/STATUS.md` "Defects" and the details in `docs/QA-RESULTS.md`
(the M2-02 pass section), as in QA.md section 6 and QA-SOURCES.md section 11,
with the player ids:

```
D-PLY-<n> | P1/P2/P3 | M2-02 | <PLY id>: <one-line repro> | open
### D-PLY-<n> (<PLY id>, <area>)  P<sev>  found <date> at <commit>
Steps: 1. ... (harness scenario PLY-Hnn step, or the live 9.x step) 2. ...
Expected (doc + section, or the PO ruling): ...
Actual: ...
Evidence: /tmp/claude-1000/omarchy-iptv-qa5/{logs,shots}/..., console lines, jq output, pids
Notes: suspected file:line, lane (PA = Model.js/helper, PB = Service.qml/harness, fix lane), workaround
```

Severity for this feature, restating section 0 for the filer:

**P1** = playback does not survive a shell restart; two player windows exist
at any instant; the player cannot be stopped by any documented means; a stream
URL, a credential or a header value reaches a command line, the journal, a
notification, the IPC `status` output or any file outside `channels.json` and
`shell.json`; the orphan-check kills the player on a plain restart; the
interface goes idle while the player keeps playing.

**P2** = the reattach loses the channel identity, `launchedFrom` or
`sourceKey`; a stop is a silent no-op that later recovers; a failure raises no
notification, or two; the guide is not marked on reattach; a stale toast is
raised for a failure that happened while the shell was down; the retry loop
writes materially more than twelve journal lines per episode; the documented
escape hatch does not work as documented.

**P3** = wording, ordering, a diagnostic regression (PO-6's territory), an
undocumented artifact, or a hardening item with no user-visible effect today.

Record a disclosed residual (PLY-SEC-05, PLY-WEAK-04, PLY-RST-09's absent
stall detection, PLY-RST-11's focus consequence) in the results as an
observation with a count, **not** as a defect - each is named and accepted in
ARCH-P or by a ruling.

## 13. Open questions for the lead before the pass

1. **Which commit?** Section 1.8 is a gate. I need the fix lane's merge
   commit, its behaviour changes, and its rule-11 evidence before the matrix
   is final. Everything here is written against `363ce9c`.
2. **May the installed clone be moved to the RC and back?** The M2-01 pass set
   the precedent (checkout, pass, `git update-ref` back, restore proof), but
   this is the user's live install and I will not move it on my own judgement.
3. **Explicit go-ahead for the destructive live steps**, by name:
   `pkill -KILL` of the shell (9.5 step 4, 9.6 step 4, 9.7 step 3),
   `omarchy plugin disable` and `remove` while playing (9.7 - note that
   disable also drops the settings stored on the bar entry and they must be
   re-set afterwards), and logout (9.9 step 2). Without these, PO-2 has no
   acceptance gate and PLY-RST-05/10 cannot run.
4. **Loopback fixture or a real provider list for the privacy sweep?** The
   M2-01 pass used a loopback server with sentinel credentials and I have
   planned for that. A real credentialed provider list would test the same
   sinks with real data; it also puts a real credential through every grep in
   this document.
5. **Suspend and logout: run, or record `not run`?** Section 10 items 4 and 5.
   Both need you at the machine and both end the session.
6. **The six contradictions in section 11** - particularly items 1, 2 and 3,
   which are the README against PO-4 and PO-2. I need a ruling on each before
   the pass so a case is not recorded as a fail against copy that is about to
   change, and item 6, which is an expectation wording rather than a defect.
7. **`tests/fixtures/qa-player/` owner and timing.** `PLAN-M2.md` gives it to
   lane PC with this document; my brief is this file only. Someone has to
   author it - section 8.0 lists exactly what it must contain - and the six
   new harness scenarios PLY-H11..H16, with their pre-fix failure evidence,
   before the harness half can run.
8. **Should `omarchy-iptv` be on `PATH`?** Item 3 above. If the answer is yes,
   it is a packaging change, not a doc change, and it belongs to a lane rather
   than to the QA pass.
9. **Sequencing.** ARCH-P 10 notes the live pass was expected to run on a
   shell still carrying D-LIVE-20 and D-LIVE-21; both are now verified fixed,
   so that note is discharged - but confirm there is no other open live defect
   that will make triage noisier.
```

## 14. Corrections from the pass on `8f9447e` (QA, 2026-09-14)

Everything below was found by running the plan, not by reading it. Each is
edited in place above and marked `[corrected 8f9447e]`; this section is the
index, so a later reader can see what the plan got wrong and why.

1. **`omarchy-shell notifications showHistory` cannot count notifications.**
   It returns the single string `ok` and opens the history panel on screen,
   so `| wc -l` is always `1` and the before/after comparison in section 3.2
   step 5, PLY-RST-03, PLY-FAIL-03 and PLY-WEAK-06 proves nothing. The
   runnable instrument is the session bus:

   ```
   dbus-monitor --session "interface='org.freedesktop.Notifications',member='Notify'" > $E/logs/notify.txt &
   NB=$(grep -c 'member=Notify' $E/logs/notify.txt)   # ... the event ...
   NA=$(grep -c 'member=Notify' $E/logs/notify.txt)
   ```

   It is strictly better than the original: it also yields the summary, the
   body, the urgency byte, the `omarchy-glyph` and the replace-id, so
   PLY-FAIL-02's whole expectation is read from one capture. Every
   notification assertion in this pass used it.

2. **`pgrep -f` self-matches the QA shell.** Section 9.0 warns about
   `pkill -f`; the same trap bites `pgrep -c -f wayland-app-id=omarchy-iptv`
   (PLY-SEC-01 step 2), `pgrep -f 'quickshell -n -p /usr/share/omarchy/shell'`
   (9.4 step 2) and `ps aux | grep -c '[y]t-dlp'` (PLY-SEC-14), because the
   QA driver's own `bash -c` argv contains the pattern. Both gave a wrong
   answer in this pass before being caught. Use `pgrep -x quickshell`,
   `pgrep -x mpv`, `pgrep -u "$(id -u)" -f -- '--input-ipc-server=<abspath>'`,
   and a bracketed self-excluding regex (`race[-]trial`) for anything else.

3. **The section 5 sampler needs to exclude its own driver.** The raw sweep
   reported 149 needle hits at `8f9447e`; every one was a QA `bash -c` whose
   argv carried the needles inside the grep pattern. Filter the driver's own
   shells out before counting, and state the filtered count.

4. **The plan's `grep` one-liners can silently return nothing.** On this
   machine the interactive shell's `grep` is shimmed and returned *no match*
   for strings that are demonstrably present in `tests/Model.test.js` (185 KB,
   427-character lines) and in `Service.qml`. Three static rows read as
   "missing" until re-run. Any static check in this plan must be run with
   `/usr/bin/grep` or a short python snippet, and a "0" from a static grep is
   not evidence until it has been confirmed twice by different tools.

5. **`failedAt` does not survive a shell restart** (PLY-RST-03 above). It is
   session-only by construction (`Service.qml:230`) and is not in
   `state.json`. Only the PO-3 path carries a mark across a shell boundary.

6. **Commands do not travel over the QML socket** (PLY-RST-06 above). It is a
   read-only observer; the helper carries every command and connects by path.

7. **mpv's fd 2 is a pipe, not `/dev/null`** (PLY-LIFE-14 above), by PO-6's
   design.

8. **A zap onto a dead channel closes the window.** Not in the plan at all,
   and it surprised the pass: under `--idle=once` a `loadfile` that fails
   leaves mpv with nothing to play and it exits, so zapping from a live
   channel onto a dead one ends the player. PO-1's gate PA-0(a) is about a
   *successful* `loadfile replace`, which does not exit mpv (re-proven here),
   and PLY-RST-02's own text already assumes the failed case exits. The next
   play spawns a fresh player. Correct, documented by implication, and worth
   stating outright.

9. **The fixture stream must outlast the test.** A 120 s fixture reached its
   natural end in the middle of restart run 4 and read as a player death. Use
   900 s (`tests/fixtures/qa-player/make-media.sh`) and keep the 3 s
   `short.ts` for PO-4's `eof` on purpose.

10. **`omarchy-launch-shell` stops supervising after a plain SIGTERM.** A
    `kill -TERM` of quickshell reads as a clean exit and the supervisor exits
    with it, so the shell does not come back; a `kill -KILL` does not, and
    the supervisor relaunches immediately (measured: back before the next
    poll). Any scripted loop that takes the shell down must use
    `omarchy restart shell`, or bring the shell back itself with
    `setsid omarchy-launch-shell`. One 40-trial run in this pass hung for
    four minutes on exactly this.

11. **Section 11's items 1-6 and 9 are discharged at `8f9447e`.** The README
    no longer says "or ends" (item 1), no longer claims `ps` shows nothing
    (item 2, now a narrowed claim this pass verified), names the real helper
    path inside the plugin directory for the escape hatch (item 3), lists
    `player.lock` under `Files it writes` (item 5), and `CHANGELOG.md` has a
    0.3.0 section carrying both weakenings (item 9). Item 4's "about four
    seconds" prose is unchanged and the budget stays 4.5 s. Item 6 is
    settled: the guide marks with U+F0026 and `Failed HH:MM`, not a red row,
    and the docs no longer say red. **Item 10 is closed by this pass:**
    `tests/fixtures/qa-player/` and `scripts/qa-player-scenarios.sh`
    (PLY-H11..H16) were authored by QA on the lead's instruction.

12. **The evidence root for this pass is
    `/tmp/claude-1000/omarchy-iptv-qa7/`**, not the `omarchy-iptv-qa5` path
    the section 9 snippets carry from the planning draft.

## 15. Corrections from the fix verification on `b16b479` (QA, 2026-09-14)

Second execution of this plan, against `main` at `b16b479`, re-verifying the
seven `D-PLY-*` defects. Results in `docs/QA-RESULTS.md`, section
"M2-02 fix verification on `b16b479`". As in section 14, everything below was
found by running the plan; each is edited in place above and marked
`[corrected b16b479]`, and this section is the index.

1. **PLY-STOP-03's socket clause has never held on the wedged path.** "The
   socket is unlinked only after the final connect is refused" is true of the
   responsive stop (5/5) and **false** of the wedged one: the player is reaped
   at ~4.25 s and `mpv.sock` survives, still present at t+66 s with the shell
   idle; only the next `probe`/`status` removes it. QA's A/B on an identical
   rig leaves it behind at **both** `8f9447e` and `b16b479`, so the pass at
   `8f9447e` recorded this row as pass without asserting the clause. Filed as
   **D-PLY-8**; harmless, because the residue is `600` inside a `700`
   directory and the next play succeeds through it.

   **[corrected, cleanup round]** The cause recorded here was wrong, and it
   was a trap: "most likely `find_player()` still sees the just-SIGKILLed
   process when the settle rung runs" is **measurably false**. A SIGKILLed
   process runs `exit_mm()` first, so its command line is already empty at the
   first post-SIGKILL sample (8/8 runs, 0.16-0.33 ms, in state **R**, not Z) -
   `find_player` goes blind EARLIER than everything else, not later. The
   blocking guard is `socket_is_dead()`: on SIGKILL the IPC listener is still
   bound for 2.71-5.75 ms after the command line empties, and that window is
   teardown-proportional (0.35 ms at ~10 MB, 113 ms at 1500 MB), while the
   settle's connect lands 4.2-8.3 ms after the kill. A future lane reading the
   old sentence would "fix" the finder with `os.kill(pid,0)` or bare
   `/proc/<pid>` existence, which makes the ladder report `running:true` after
   a successful SIGKILL and blocks the settle indefinitely. **Do not.** The
   same wrong cause is recorded at `docs/STATUS.md:143` and
   `docs/QA-RESULTS.md:2539-2541` and needs the same correction there.

2. **PLY-SEC-07's "complete list" grew by two directories.** The D-PLY-7 fix
   added `$XDG_RUNTIME_DIR/omarchy-iptv/watch-later/` and
   `~/.local/state/omarchy-iptv/screenshots/`, both `700` holding `600` files.
   Any pass that treats the old list as exhaustive will read the fix as a
   defect. Separately, one artifact the player creates is outside the list
   altogether - `~/.cache/mpv/shader_*`, mpv's own content-free shader cache,
   inherited via `HOME` (**D-PLY-10**).

3. **PLY-RST-11's focus consequence is runnable and is now run.** Section 14
   item 7 recorded it as `not run`. Run **windowed**, as section 14 item 7
   itself prescribes, the foreign player maps a real window and the documented
   consequence reproduces: `hyprctl clients` reads 2 and `pgrep` reads 2, while
   our probe, stop and start all stay correctly scoped to ours. Item 7 is
   closed.

4. **PLY-SEC-14's cross-reference was a typo.** The row ends "See D-PLY-1"; the
   defect it means is **D-PLY-5**. Corrected in place. The row's own
   expectation is now satisfied at `b16b479`.

5. **`pgrep -c` has the same two-line trap as `grep -c`.** Section 14 item 2
   warns that `pgrep -f` self-matches; this is a different bug in the same
   family. `pgrep -c <pat> || echo 0` prints `0` **and** exits 1 when nothing
   matches, so the substitution yields `"0\n0"`, every `[ "$(count)" = 0 ]`
   guard is false forever and every `$(( count - x ))` dies. It cost this pass
   two wasted runs, and it is live in the shipped harness at
   `scripts/dev-harness/player-scenario.sh:149`, where it silently kills the
   "exactly ONE relaunch" check (**D-PLY-9**). Use
   `pgrep -c ... 2>/dev/null | head -1 || true`, or `| wc -l`.

   **[fixed, cleanup round]** `log_count` goes through `qa_count` in
   `scripts/qa-lib.sh` now, and the scenario asserts how many assertions it
   executed (`EXPECTED_CHECKS`), so a check that stops running turns the run
   red instead of shortening the summary. Bash offers no way to turn a failed
   expansion into a failed test, so that floor is the only thing that closes
   the class. Expect **84** assertions and, on the `--baseline 396a69a` run,
   the same 84 with more of them failing. (The floor read 82 until the
   repointing below added a positive control and a second reading; wave two
   ran it at 83 on the tree it measured.)

   **The repaired check cannot tell the two trees apart, and that is the
   important part.** The string it counts,
   `omarchy-iptv: mpv unresponsive, restarting player`, exists at exactly one
   place - `Service.qml:510`, inside `restartPlayer()`. The second relaunch
   the D-PLY-1 fix prevents is issued by `relaunchTimer.onTriggered`'s
   `playerUp` branch, which logs nothing, and a second entry into
   `restartPlayer()` logs the *different* "mpv unresponsive again, stopping the
   player" line. So the restored assertion PASSES on both trees. If it goes
   red on the baseline, that is new information about `Service.qml`, not a
   confirmed expectation.

   **[confirmed live, then fixed, cleanup round]** Wave two ran the whole
   scenario both ways on a display and `PASS P11 exactly ONE relaunch` appears
   in **both** summaries (`docs/QA-RESULTS.md` D4) - the paragraph above was
   right, and a witness that only the fixed tree emits can never discriminate
   (**CL10**). The assertion at `player-scenario.sh:402`/`:416` now reads the
   **intent counter** on both sides of the lock instead: `svc d['playSeq']`
   and the `player.lock` record, each of which one logical relaunch advances
   by exactly **1** and a queued second relaunch by **2**. Both exist on every
   M2-02 tree, which is the property that makes a comparison possible at all.
   The numbers are not assumed: the node gate extracts each tree's own
   decision sites and reads `{"intents":1,"seqDelta":1}` here against
   `{"intents":2,"seqDelta":2}` for `396a69a`'s `Service.qml`, and the
   assertion itself - lifted verbatim out of the scenario - passes on 1 and
   fails on 2 in `scripts/qa-lib-test.sh`. It also **fails rather than
   vanishing** when the shell answers `NOFIELD`, which is what `qa_delta`
   exists for: `$(( $(counter) - before ))` dies as an arithmetic expansion on
   any non-numeric reading, and a counter read over IPC has far more ways to
   answer non-numerically than a grep has. The journal line is kept and
   **printed, never asserted**, and the output says so.

   **The same blind spot is in the manual procedure.** `docs/STATUS.md:136`,
   `docs/STATUS.md:164` and `docs/QA-RESULTS.md:2407` record that QA counted
   that same journal string by hand ("delta exactly 1, never 2"). That count
   measures the same non-discriminating string. **"Exactly one relaunch, never
   a second at the healthy player" - half of the P1 this project shipped - has
   no machine-checkable witness anywhere.** Ruling CL3: add the witness at
   `Service.qml:2486` and correct those three rows in the same change. That
   log line is owned by the shell lane; this round only records that the
   procedure written down here was never evidence.

   **[closed, cleanup round]** It has one now, and it is not the log line.
   The manual procedure in section 9.6 step 3 should read the intent counter
   the same way the harness does - `ipc status` before the wedge and after the
   respawn, delta exactly 1 - and should stop counting the journal string,
   which reads 1 on a fixed tree and 1 on a broken one alike.

8. **Every count this section cites is now asserted by the gate that prints
   it.** `scripts/check.sh` used to interpolate
   `$(grep -c '^PASS' /tmp/omarchy-iptv-qmltest.log)` into a message and
   assert nothing, so a `qmltestrunner` that exited 0 having executed zero
   test functions printed `ok   qml spec (0 passed)` and the gate stayed
   green - while the tables in section 12 cite "42 passed" and "47 passed" as
   evidence. The node runner and `unittest` have the same shape (`0 checks`,
   `Ran 0 tests ... OK`). All three now carry floors, as does the number of
   files qmllint examined, and `scripts/dev-harness/shell.qml` - the fake
   every scenario in this repo runs against - is linted for the first time.

6. **Two tools in section 0 are not invokable as written on this machine.**
   `qmltestrunner` is not on `PATH`; the runnable form is
   `/usr/lib/qt6/bin/qmltestrunner`. `python3 -m unittest tests.test_player`
   fails at import (`helper_loader` is not on `sys.path`); the runnable form is
   `python3 -m unittest discover -s tests -p 'test_player.py'`. Neither is a
   product defect.

7. **"Zap to first frame" needs a signal that is not `time-pos`.** A
   `loadfile replace` reuses the player, so the **old** `time-pos` is still
   readable immediately after the zap and "wait for non-null `time-pos`" times
   the IPC round trip (67-81 ms), not the frame. The honest signal is
   `media-title` reaching the new channel **and** `time-pos` back under 2 s,
   which gives 277-338 ms warm and 711-781 ms cold. Both are inside the 2 s
   budget, so no verdict changes; the method does.

8. **The fd/RSS leak row cannot be read across a shell restart.** `omarchy
   restart shell` replaces the process, so comparing the old shell's fd count
   with the new one's measures nothing about leaking. Only mpv's own figures
   survive the restart and are comparable, and mpv's RSS climbs with playback
   time, not with restarts. Re-word the row to assert what actually holds: the
   **same mpv pid, one window and full identity through ten consecutive
   restarts**, which is measured and passes.

9. **TC-PLAY-10 needs a severity boundary.** Eight *serial* rapid zaps - all
   the single-threaded guide can produce - agree with the player 4/4. Eight
   *truly concurrent* `play` calls diverged once in eight
   (**D-PLY-11**). The row should say which of the two it is asserting; only
   the serial case is a user-reachable contract.

   **[corrected, cleanup round]** The rate written here was an artefact of the
   arrangement, not a property of the code, and the mechanism behind it was a
   guess. Wave two guaranteed a cold player before each burst and measured
   **10 user-visible divergences in 20 cold concurrent bursts** (plus 3
   stash-only), **0 in 10 warm** and **0 in 6 cold-serial**
   (`docs/QA-RESULTS.md` D1). Fifty per cent, not one in eight.

   The mechanism was **observed**, not inferred: only one `player start` ever
   ran, carrying the burst's FIRST intent, while the player's current playlist
   entry id read 2 or 3 - so a zap reached the socket the instant mpv bound it
   and the start's own `apply_channel` landed after it. `play failed:` appears
   0 times in all 30 bursts, so the rollback ordering (O1) is excluded, and
   the adopting-start family never fired. Nothing self-corrected: every
   divergence still read the same at t+20 s and t+40 s, past two health ticks.

   Severity is unchanged, and on purpose (**CL11**): it is bounded by
   reachability, not by rate. The guide is single threaded and cannot produce
   the concurrency; the open command surface can. Do not re-rate it upward on
   the rate alone. The invariant the plan tests for is **CL6** - the label and
   the player agree within one health tick - not that the last of several
   simultaneous intents wins. Covered by **PLY-H17** and **PLY-H18**.

10. **The evidence root for this pass is
    `/tmp/claude-1000/omarchy-iptv-qa8/`.**

---

## 16. Corrections from the cleanup round's last wave (QA, 2026-09-14)

Third pass over this plan, after wave two's live evidence (`docs/QA-RESULTS.md`
sections D1-D7) and wave three's fix. Everything below is edited in place
above and marked `[corrected, cleanup round]` or `[closed, cleanup round]`;
this section is the index. This lane held no display, so every number it
quotes is either wave two's or was produced here with no shell and no window.

| # | Row or item | What changed |
|---|---|---|
| 1 | **PLY-LIFE-12** (section 1.1) and section 14 item 5 | The one-relaunch half is asserted on the **intent counter**, never on the journal line (**CL10**). `status.player.seq` and the `player.lock` record each advance by exactly 1 here and by 2 on a tree that leaves the delivered relaunch queued. Both readings exist on every M2-02 tree - which is the only reason a comparison is possible. |
| 2 | **PLY-STOP-03** (section 1.1) and runbook 9.6 step 3 | The socket clause is now an **assertion with a deadline and a control**: `ls "$S"` fails at t+0.5 s and still fails at t+30 s, on the wedged path as well as the responsive one, with no `probe`/`status`/`play` of the tester's own in between. 10/10 at `a939fd7`, 5/5 the other way at `8f9447e` and `b16b479`. The old wording described a mechanism and asserted nothing. |
| 3 | Section 14 item 9 (**TC-PLAY-10** / D-PLY-11) | **10 divergences in 20 cold concurrent bursts**, 0 in 10 warm, 0 in 6 cold-serial - not 1 in 8 - and the mechanism is **observed** rather than guessed. Severity is unchanged on purpose (**CL11**): bounded by reachability, not by rate. |
| 4 | **PLY-LIFE-16**, **PLY-LIFE-17** (new, section 1.1) | The two behaviours wave three's fix introduced: the cold start that stands down, and the CL6 convergence. They existed only as a live pass and two unit gates, so the suite could not have caught their loss. |
| 5 | **PLY-H17**, **PLY-H18** (new, section 8.1) | The scenarios that cover them, in `scripts/qa-player-scenarios.sh`. Both run with **no display and no shell** for the half that matters, and both were run against `a939fd7`: PLY-H17 6 of 11 fail there, PLY-H18 phase A 4 of 7. |
| 6 | Section 14 item 5's floor | `EXPECTED_CHECKS` 82 -> **84**. Two of those are new assertions, not new behaviour. |

Two harness defects were found on the way, both the same family as D-PLY-9 -
a comparison with only one side:

1. **`qa-player-scenarios.sh` pinned `HELPER` to the repository root**, so
   every step that calls the helper directly ran **today's** helper under
   `baseline` whatever ref was named. PLY-H15's three helper steps were
   subject to it, and PLY-H17/H18 would have been. It follows
   `OMARCHY_IPTV_PLUGIN_ROOT` now, which is what makes a baseline run of a
   helper-level scenario mean anything at all.
2. **Those scenarios had no assertion floor.** A check that stopped executing
   merely shortened the summary, which is exactly D-PLY-9's shape. The two
   asserting scenarios carry one, per scenario rather than per run.

**Still owed by the lane that holds the display**, and not claimable without
one:

- `player-scenario.sh` at HEAD and at `--baseline 396a69a`, both halves, with
  the repointed P11 lines. Expect **84** assertions on both trees, the two
  intent-counter checks **passing** at HEAD and **failing** on the baseline,
  and the printed journal delta reading **1** on both. That last number is
  the point: it is what the old assertion measured.
- **PLY-H18 phase B** (`run PLY-H18 --apply --with-display`), the CL6
  convergence itself, and the same against `a939fd7`.
