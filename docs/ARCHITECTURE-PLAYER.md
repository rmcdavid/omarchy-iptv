# Omarchy IPTV - detached player (M2-02)

M2-02-00. Owner: ARCH. Status: proposed, awaiting PO acceptance.
Resolves every `[PLAYER-SLOT]` in `docs/PLAN-M2.md` (lines 11, 66, 93, 224, 378).
Verified against HEAD `210cfa3` on Omarchy 4.0.3 / Quickshell 0.3.1 / Qt 6.11 /
mpv 0.41.0 / python3 3.14.

## 1. Problem

`ARCHITECTURE.md` decision 2 chose an attached Quickshell `Process` for mpv
because "only `Process` gives `onExited(exitCode, exitStatus)` and stderr", and
ruling **R10** froze that for M1: destroying the object kills mpv
(`Service.qml:1876-1889`, comment at :1877), so `omarchy restart shell`, a shell
crash and `omarchy update` all end playback. The README ships it as a known
limitation (`README.md:150-152`) and `QA.md` TC-PLAY-11 asserts it. Separately,
`SECURITY-REVIEW.md` finding **S-03** (P3) records that `Model.buildMpvArgv`
ends `argv.push("--"); argv.push(str(p.url))` (`Model.js:1277-1278`) and splices
`headerArgs()` (`Model.js:1224-1240`), so the **first** channel's stream URL and
header values sit in `/proc/<pid>/cmdline` - 0444, on a `/proc` mounted without
`hidepid` - for the life of the mpv process; only later zaps travel over the
0600 socket. This document specifies a player that survives a shell restart and
reattaches, and that never puts a stream URL or a header value on any command
line, on any channel, including the first.

## 2. Decision

**Adopt a hybrid built on approach D ("Adopt"), with four named grafts and six
defect fixes. Name: `player start` / `player stop` / `player probe` /
`player restart` / `player orphan-check` - a `player` verb group in the existing
stdlib-python helper, invoked from QML as argv, spawning mpv as a setsid'd
grandchild, observed from Service.qml through a persistent
`Quickshell.Io/Socket` on mpv's own JSON IPC socket.**

### 2.1 Why this shape

The judges converged on the same verdict for all four submissions: every
detachment mechanism works, and every design died in `Service.qml`. The
mechanism questions were settled by probe evidence that all four approaches
independently reproduced; what remained were lifecycle and ordering defects.
The grafts below exist to close exactly those.

- **Detachment by `setsid` + double fork, not systemd.** Approach B's transient
  unit is a genuinely atomic singleton, but both of its judges found the same
  disqualifier: `systemd-run --unit=` only guards launches that go through
  `systemd-run`, and `bin/omarchy-iptv` is a public CLI that can spawn a player
  directly, so it introduces a second source of truth that can disagree with the
  socket (`ActiveState=active` over a wedged mpv). B's own probe also showed an
  out-of-band `SIGTERM` leaves `Result=success` - indistinguishable from a clean
  stop - so the unit is not even a complete death detector. Against that,
  `setsid` + double fork reparents to `systemd --user` (pid 831 here, the
  session subreaper) and inherits the `wayland-wm@hyprland.desktop.service`
  cgroup, which is `ExitType=main` + `KillMode=control-group` with
  `Linger=no` for uid 1000 - i.e. the player outlives every shell restart and
  is still reaped at logout, with no unit file, no `--collect`, no manager
  dependency and no 90 s `TimeoutStopSec`. `uwsm-app` is rejected outright:
  `/usr/bin/uwsm-app` ends in `eval "$CMDLINE"` on a string read from a FIFO,
  a shell-interpolation surface in the playback path against hard requirement 9.
- **No long-lived supervisor.** Approach C's daemon is the only design that
  restores `waitpid` and a real stderr pipe, but it costs ~650 lines re-deriving
  the D-LIVE-15 / D-LIVE-17 invariants in a second language, and both judges
  found the same fatal: the daemonize spec never detaches stdio, so a process
  forked from a helper whose fds are Quickshell `StdioCollector` pipes holds
  those pipes for hours and dies of `BrokenPipeError` at the exact shell restart
  it exists to survive. We take C's *finding* (stdio hygiene is load-bearing)
  and discharge it in the grandchild instead: `dup2` `/dev/null` onto 0/1/2 and
  close every inherited descriptor before `execvp`.
- **Observation in QML, not in a second python process.** Approach A's `monitor`
  process is a correct idea with a fatal ordering bug - it is started from the
  launcher's `onExited`, i.e. *after* the first `loadfile`, so a dead first
  channel (the commonest real failure: an expired subscription) emits its
  `log-message` and `end-file` to nobody. We keep A's subscriber semantics and
  put them in `Quickshell.Io/Socket`, and we close the ordering hole by having
  **`player start` itself observe the first load** on the connection it already
  holds and report the outcome in its JSON reply. No extra process, no gap.
- **`--idle=once`, which is what SECURITY-REVIEW.md:36 actually prescribes.**
  Three of the four designs silently substituted `--idle=yes` and then paid for
  it with an `idleTimer`, an `idleVerdict` truth table, a lingering empty
  960x540 window and the retirement of decision 12. `--idle=once` idles at
  startup (so the URL leaves argv, which is the whole point) and exits when the
  playlist finishes, which preserves today's UX exactly: the window vanishes on
  a stream failure and on a clean end. It also preserves a working
  **degraded mode** - if `Quickshell.Io/Socket` misbehaves, mpv still exits on
  failure and the existing 10 s `status` poll still detects it. `--idle=yes` has
  no such fallback.

### 2.2 The six defect fixes that make the graft sound

Every one of these closes a fatal that a judge found in at least one submission.

| # | Defect found | Fix in this design |
|---|---|---|
| F1 | Routing stop rungs / launches through the single `controlProc` slot (`Service.qml:796`, `if (controlProc.running) return false`, no queue, no callback) silently skips a rung or drops a zap | Ownership split: `controlProc` keeps `play`/`status` only. A new `playerProc` (with its own watchdog, matching `playlistWatchdog`) runs `player start`/`probe`/`restart`. `player stop` goes out with `Quickshell.execDetached` and runs the **whole** ladder inside one helper, so no rung can be starved and the ladder completes if the shell dies at any rung |
| F2 | `playerUp` derived from an async connection is read at ~20 synchronous decision sites, breaking D-LIVE-15 rollback, the same-row re-select, and `stop()` (which becomes a no-op during a reconnect window) | `playerUp = playerSocket.connected \|\| playerPending`, where `playerPending` is set **synchronously** inside `startPlayer()` - the birth edge `mpvProc.running` gave. Section 4.7 tables every read site by role. `stop()` never gates on it, and no spawn decision depends on it for correctness (the helper is idempotent) |
| F3 | The event subscriber is not attached when the first channel loads, so a fast first-channel failure is silent | `player start` issues `request_log_messages "error"` before `loadfile` and observes `start-file`/`end-file` for `--first-load-timeout` (3 s) on its own connection, reporting the outcome in its reply. The QML socket is a second, independent observer |
| F4 | `playlist_entry_id` sourced from a helper reply that loses the race to the event stream; a null id then gates out **every** failure after a restart | `entryId` comes from `loadfile`'s reply (verified to carry `data.playlist_entry_id`) and is confirmed by the following `start-file`. The QML gate **fails open**: a null or unknown entry id never suppresses a notification (section 4.8) |
| F5 | Singleton by socket `connect()` alone: `connect()` succeeds through the listen backlog against a wedged mpv; mpv silently rebinds over a live socket leaving two windows; `flock` is defeated by unlinking the lock file; a socket that can never bind leaves an un-killable window that the next start multiplies | Three layers: **/proc scan** on the exact `--input-ipc-server=<abspath>` token plus uid is the authoritative existence and PID-discovery check (`connect()` only ever answers "responsive", never "exists"); `flock` with an **inode re-check** (`fstat(fd)` vs `stat(path)`) so an unlink-and-recreate is detected; and a spawn that does not produce a connectable socket within 5 s is reaped by the helper that created it, using the pid it read back over a pipe |
| F6 | `Component.onDestruction` firing a stop - it fires on graceful shell exit (verified: `omarchy-restart-shell` uses `quickshell kill`, and the journal shows "Exiting due to IPC request"), so it kills the player on the very restart the milestone exists to fix | `onDestruction` fires `player orphan-check --owner-pid <Quickshell.processId> --grace 6`. The claim in `user-data/omarchy-iptv-owner` is keyed by shell pid + start time, so a *successor* shell has already overwritten it by t+6 s and the check is a no-op; only "the recorded owner pid is still alive and still owns the claim" means the service was destroyed while its shell lives, i.e. the plugin was disabled or removed |

### 2.3 One correction to the brief and to three of the four designs

Three submissions make "restore the 40-45 mpv assertions deleted from
`tests/Model.test.js`" their mandatory first step. **That premise is false.**
`tests/Model.test.js` contains one NUL byte at offset 53422 (inside the
`Model.sanitizeTyping("a\x00bcdefgh", 4)` case), so `file` reports it as `data`
and plain `grep` prints nothing without `-a`. With `grep -a`: 583 `check(` calls,
`buildMpvArgv` 11 hits, `notifyArgv` 13, `stopEscalation` 7, `healthTick` 4,
`splitMpvArgs` 6, `headerArgs` 2, `mpvWindowTitle`, `focusPlayerArgv`,
`MPV_RAW_PREFIX` and `statusHealthy` all present - including
`buildMpvArgv url after --` at line 339 and the S-01 non-expansion case at 333.
Requirements 2, 3, 4, 5, 6 and 8 **are** pinned. There is no Stage 0. The work
plan in section 9 starts at lane PA. Any lane told to check out
`4b5e0d3:tests/Model.test.js` would delete 272 live assertions.

Two further corrections, same class: `ARCHITECTURE.md` decision 2 and decision 8
and `README.md:150-152` already state correctly that a plugin rescan does **not**
tear the service down (`shell.qml serviceKeepLoaded` / `unloadPluginServices`
lines 1024-1050 confirm it), and `scripts/dev-harness/run.sh:72` already reaps
by cmdline pattern (`pkill -f "input-ipc-server=$SCRATCH/..."`), which works
unchanged on a detached grandchild. No docs edit is budgeted for either.

## 3. Approaches considered

| Approach | One-line summary | Score | Fatal flaws found | Disposition |
|---|---|---|---|---|
| **D "Adopt"** (open) | Detached mpv under a helper-held `flock`; idempotent `player start`; helper-owned stop ladder; QML `Socket` subscriber | 9 | No PID discovery path (only `get_property pid`, dead exactly when the ladder matters); unbindable-socket spawn leaves an un-killable window that the next start multiplies; `onDestruction` stop kills the player on every restart; `user-data` written "at every loadfile" while `cmd_play` is declared unchanged; `stopping` guard deleted with no replacement; `connect()` treated as proof of liveness | **Adopted as the base.** All six fatals are addressed by F1-F6 and sections 4.2-4.10: /proc scan for discovery, pid-over-pipe + reap on spawn timeout, the owner-claim orphan-check, `apply_channel()` shared by `play` and `player start`, `stopping` redefined in section 4.10, `connect()` demoted to "responsive" |
| **B systemd-scope** | mpv as a fixed-name transient user service in `app-graphical.slice`, fed only over its socket | 10 (6 fatal) | Stop rungs 2-4 routed through the single `controlProc`, and `escalateStop` advances `stopStage` on a refused rung, so the SIGTERM is skippable; unbounded cold start occupying the one control channel with no watchdog; `playing` false for the whole cold start (bar reads idle on every Enter); plugin disable orphans a player with no unit file to find it by; `--idle=yes` substituted for the prescribed `--idle=once`; every Service.qml line citation stale | **Rejected as the launcher; three grafts taken.** (1) The cgroup / logout-lifetime analysis (`app-graphical.slice` is `PartOf=graphical-session.target`, `Linger=no`) is the evidence base for section 4.1's claim that no unit is needed. (2) The `--log-file` hardening. (3) The honest finding that an out-of-band `SIGTERM` leaves a unit indistinguishable from a clean stop - which is precisely why our death signal is socket EOF plus a /proc scan, not a supervisor's post-mortem. `systemd-run --user --unit=omarchy-iptv-player.service` is recorded as a drop-in future replacement for `spawn_detached()` if the lock ever proves insufficient |
| **A detached-idle + monitor** | Double-forked idle mpv plus a long-lived stdlib-python `monitor` process piping redacted events into QML | 10 (8 fatal) | Monitor started from the launcher's `onExited`, i.e. after the first `loadfile`, so first-channel failures are silent and are then mis-recovered as a clean stop; `entryId` stashed *before* `loadfile` (the id only exists in the reply), so the hard entry gate discards every `end-file` after a restart; `healthTimer.running` and `stop()`'s guard both bound to a flag the monitor alone owns, giving an uncontrollable playing window with the reconciler switched off; `startPlayer` through `runControl` drops plays silently | **Rejected as a process; four grafts taken.** (1) The CLOEXEC errno pipe from the exec'ing grandchild, which restores the exec-failure reporting `Quickshell.execDetached` throws away (it returns void). (2) The `end-file` reason taxonomy, including the verified finding that a **zap** emits `reason:"stop"` followed by `start-file`, so reason alone cannot classify. (3) `playlist_entry_id` correlation - with its ordering bug fixed (F4) and the gate made fail-open. (4) Redacting log text in python before it crosses into QML. A's own monitor role is filled by `Quickshell.Io/Socket` plus `player start`'s first-load window, at zero extra processes |
| **C supervisor daemon** | `omarchy-iptv-playerd`: a stdlib-python `selectors` daemon that is mpv's parent, publishing `player.json` | 10 (8 fatal) | Daemonize omits stdio detachment, so the daemon holds Quickshell's `StdioCollector` pipes and dies of `BrokenPipeError` on the first shell restart; `flock` defeated by unlinking the lock file (demonstrated); `stop` cannot reach a surviving mpv because only `play` autostarts a daemon, and the shell has permanently surrendered `mpvProc.signal()`; adoption has no branch for a wedged mpv; `Quickshell.processId` asserted absent when it exists; `notifyArgv` "mirror" drops the S-04 quoting | **Rejected as an architecture; three grafts taken.** (1) The proof that a toast **cannot** be raised while the shell is down - `org.freedesktop.Notifications` is owned by quickshell itself and has no activation file under `/usr/share/dbus-1/services/`, so `busctl` returns "The name is not activatable". This is why our helper never notifies and PO-3 exists. (2) The stdio-hygiene requirement, discharged in the grandchild. (3) The lock-file inode attack, closed by the `fstat`/`stat` re-check. C's `player.json` is explicitly **not** adopted: a disk file can outlive the player and claim a channel is playing when nothing is, whereas `user-data` dies with the process it describes |

Rejected across the board, with reasons, because a later reviewer will
re-propose them: **`--log-file`** and **systemd `StandardError=append:`** as the
stderr replacement (forced `-v -v` floor that `--msg-level` cannot lower, mode
0644, the full credentialed URL seven times per failed load - a durable,
world-readable version of the bug being fixed); **`loadfile`'s 4th per-file
options argument** for headers (values must be strings and `http-header-fields`
then serialises comma-separated, so a playlist-supplied `Cookie: a=1, b=2`
splits into two wrong headers - `Model.js:1223` already documents the `-append`
list form as existing precisely to avoid that); **`--playlist=<0600 file>`**
(puts the URL on disk, worse than the transient argv exposure); and
**`state.json.lastPlayed` as the recovery source** (a disk file cannot know
whether the player it names is alive).

## 4. Design

### 4.1 Process model

```
BEFORE (v0.2.0)

systemd --user (831)
`-- wayland-wm@hyprland.desktop.service   (ExitType=main, KillMode=control-group)
    `-- quickshell  "omarchy-shell"
        |-- mpv  --input-ipc-server=... --title=$>BBC --user-agent=VLC -- http://u:p@h/s.m3u8
        |     ^ attached Process; ~Process() SIGKILLs it; URL + headers in /proc/<pid>/cmdline
        `-- python3 bin/omarchy-iptv play|stop|status        (controlProc, ~125 ms)

AFTER (M2-02)

systemd --user (831)
`-- wayland-wm@hyprland.desktop.service   (ExitType=main, KillMode=control-group)
    |-- quickshell  "omarchy-shell"
    |   |-- python3 bin/omarchy-iptv player start|probe|restart   (playerProc, <= 8 s)
    |   `-- python3 bin/omarchy-iptv play|stop|status             (controlProc, ~125 ms)
    |       (execDetached verbs - player stop, orphan-check, notify - reparent immediately)
    `-- mpv  --input-ipc-server=/run/user/1000/omarchy-iptv/mpv.sock
             --wayland-app-id=omarchy-iptv --idle=once ...        (no URL, no headers)
          ^ setsid'd grandchild, ppid 831, stdio /dev/null, same cgroup,
            survives every quickshell death, reaped at logout by the unit above
```

Control flow:

```
BEFORE                                   AFTER

play(id)                                 play(id)
 |- mpv running?                          |- playerUp && !stopping ?
 |    yes -> controlProc: play --id       |     yes -> controlProc: play --id      (unchanged)
 |    no  -> mpvProc.command = argv+URL   |     no  -> playerProc: player start --id --seq N
 |           mpvProc.running = true       |               (idempotent: adopt or spawn, URL over IPC)
 |                                        |
stop()                                   stop()
 |- escalateStop() ladder in QML          |- execDetached: player stop --seq N
 |    quit via controlProc                |     quit -> 2 s -> SIGTERM -> 2 s -> SIGKILL, in ONE
 |    mpvProc.signal(15) @2s              |     helper, pid from /proc, completes without the shell
 |    mpvProc.signal(9)  @4s              |
                                          |
death                                    death
 `- mpvProc.onExited(code)                `- playerSocket.connectionStateChanged -> EOF
       reason = last stderr line                reason = end-file.reason + file_error
                                                         + log-message text (redacted in python)
```

Process count at rest (nothing playing): unchanged - no helper, no mpv. While
playing: mpv plus an occasional 125 ms helper. The QML `Socket` is an object,
not a process.

### 4.2 The runtime directory, the socket, the lock, and their modes

Unchanged paths: `runtimeDir = $XDG_RUNTIME_DIR/omarchy-iptv`,
`socketPath = runtimeDir + "/mpv.sock"` (`Service.qml:34-35`). The live box is
`700 /run/user/1000/omarchy-iptv` with a leftover `srw------- mpv.sock` and no
mpv running - the exact state section 7 row "stale socket" covers.

| Artifact | Mode | Created by | Contents |
|---|---|---|---|
| `$XDG_RUNTIME_DIR/omarchy-iptv/` | 0700 | `mkdirProc` (`mkdir -p -m 700`) **and** `ensure_private_dir()` in every `player` verb | - |
| `mpv.sock` | 0600 | mpv itself, explicitly (verified created 0600 under `umask 0022`) | JSON IPC |
| `player.lock` | 0600 | `os.open(O_CREAT\|O_RDWR, 0o600)` in the `player` verbs | one line: `{"schema":1,"seq":N,"verb":"start\|stop\|restart","at":<epoch>}` |

The helper re-asserts the directory itself rather than trusting `mkdirProc`,
because **mpv fails completely silently when the parent directory is missing**:
no socket, no message, not even at `--msg-level=all=trace`. (There is a live
witness of exactly this on the machine right now: pid 306721,
`mpv --idle=yes ... --input-ipc-server=/tmp/pk-missing-306717/nodir/mpv.sock`,
running with no socket and no diagnostic.) The path is 36 bytes, far under the
108-byte `sun_path` ceiling that produces the same silent failure.

**Lock protocol.** `flock(fd, LOCK_EX|LOCK_NB)` polled every 50 ms to
`--lock-timeout` (default 6 s). After the grant, compare `os.fstat(fd)` against
`os.stat(path)`: a mismatch or `ENOENT` means the file was unlinked and
recreated while we waited, so the lock protects an orphaned inode - release,
reopen, retry, up to 5 times inside the same deadline. Exhaustion reports
`{"code":"busy"}`, which the existing `playRetryTimer` backoff retries. The
kernel releases the lock on any death including SIGKILL, so it can never go
stale.

### 4.3 Helper `player` verb group - the frozen lane interface

All argv are built by pure `Model` functions (lane PA) and consumed by
Service.qml (lane PB). `play`, `stop` and `status` keep their exact current
spelling and reply shape; only additive fields appear.

```
player start   --socket S --cache-dir C --id ID --seq N
               [--scope SCOPE] [--since EPOCH] [--mpv-arg TOKEN]...
               [--lock-timeout 6.0] [--spawn-timeout 5.0]
               [--first-load-timeout 3.0] [--ipc-timeout 2.0]
player stop    --socket S --seq N [--from quit|term|kill] [--lock-timeout 6.0]
player restart --socket S --cache-dir C --id ID --seq N [--scope] [--since]
               [--mpv-arg TOKEN]... [--from term]
player probe   --socket S [--owner-pid PID] [--ipc-timeout 2.0]
player orphan-check --socket S --owner-pid PID [--grace 6.0]
```

User `mpvArgs` tokens travel as **repeated `--mpv-arg TOKEN`**
(`action="append"`), never as a positional list - that sidesteps argparse
consuming an option-looking token entirely, and keeps every element a distinct
argv member with no joining.

Reply shapes (all `{"ok":bool,"kind":...}` per decision 10, all URL-free):

```
player.start  {"ok":true,"kind":"player.start","spawned":bool,"pid":N,
               "id":"t:bbc1.uk","name":"BBC One HD","entryId":2,"seq":41,
               "firstLoad":{"state":"playing"|"failed"|"unknown",
                            "reason":"<redacted, host only>"},
               "warnings":["dropped mpvArg --log-file"]}
player.stop   {"ok":true,"kind":"player.stop","running":false,
               "rung":""|"quit"|"term"|"kill","pid":N|null}
player.probe  {"ok":true,"kind":"player.probe","running":bool,"responsive":bool,
               "pid":N|null,"idle":bool|null,"mpvVersion":"...",
               "stash":{...}|null,"owner":{...}|null,"seq":N,"claimed":bool}
error         {"ok":false,"kind":"player.<verb>","error":{"code":C,"message":M}}
```

Error codes, exhaustive: `busy`, `superseded`, `socket_path_blocked`,
`mpv_missing`, `spawn_failed`, `no_socket`, `not_running`, `ipc_error`,
`no_cache`, `unknown_channel`, `unsupported_scheme`.

Additive changes to existing verbs: `play` gains optional `--scope` / `--since`
(so a zap refreshes the stash) and returns `"entryId"`; `status` gains
`"process":{"found":bool,"pid":N|null}` and `"stash":{...}|null`. `running` in
`status` keeps its current socket-answered semantics so `Model.statusHealthy`
(`Model.js:1014`) and the 23 cases in `tests/test_mpv.py` are untouched.

### 4.4 Exact startup sequence (cold play)

1. `play(id, ...)` in Service.qml: preamble unchanged through `saveState()`
   (`Service.qml:272-318`). `root.playSeq += 1`.
2. `playerUp` is false (or `stopping` is true), so `startPlayer(channel)` runs:
   it sets `root.playerPending = true` **synchronously**, sets
   `root.playerWanted = true` (arms the socket retry timer), starts
   `playerWatchdog`, and issues on `playerProc`:
   `["python3", helperPath, "player", "start", "--socket", S, "--cache-dir", C,
     "--id", key, "--seq", N, "--scope", scope, "--since", since,
     "--mpv-arg", t1, "--mpv-arg", t2, ...]`.
3. Helper: `ensure_private_dir(runtime_dir)` -> 0700. If `socketPath` exists and
   is **not** a socket, stop here with `socket_path_blocked` - nothing is
   unlinked (preserving `test_regular_file_at_socket_path_is_left_alone`) and
   nothing is spawned.
4. Helper: acquire the lock (4.2). Read the record; if `record.seq > N`, release
   and report `superseded` (4.10). Else write our record.
5. Helper: `find_player()` - scan `/proc/[0-9]*/cmdline`, split on NUL, match the
   exact token `--input-ipc-server=<abspath>`, require
   `stat("/proc/<pid>").st_uid == os.getuid()`, read `/proc/<pid>/stat` field 22
   for the start time.
   - One match that answers `get_property mpv-version` inside `--ipc-timeout`
     -> **adopt**, go to step 9 with `spawned:false`.
   - Matches found, none answers -> wedged: run the stop ladder (4.9) on each,
     starting at rung 1, then continue.
   - Several matches and one answers -> stop the others, adopt the answerer.
   - No match -> if a socket file exists, `unlink_stale_socket()`
     (`bin/omarchy-iptv:1796`, already `S_ISSOCK`-guarded), then spawn.
6. Helper `spawn_detached(argv)`: `pipe()` for the grandchild pid, `pipe2(CLOEXEC)`
   for errno. `fork()` -> child `setsid()` -> `fork()` -> grandchild writes its
   own pid to the pid pipe, `dup2`s `/dev/null` onto fds 0/1/2, closes every
   other inherited descriptor except the errno pipe, then `os.execvp("mpv", argv)`
   - argv[0] is the literal `"mpv"`, never caller-supplied, so `player start` is
   not an arbitrary-exec verb. On failure it writes the errno and `_exit(127)`.
   The intermediate child `_exit(0)`; the helper `waitpid`s it (no zombie),
   reads the pid, and reads the errno pipe (empty on a successful exec, because
   CLOEXEC closes it) -> `mpv_missing` / `spawn_failed` if not.
   **This is the step that guarantees mpv never holds a Quickshell pipe.**
7. Helper: poll `connect()` + `get_property mpv-version` every 20 ms to
   `--spawn-timeout` (5 s; measured bind latency 0.114-0.151 s). On timeout, run
   the stop ladder on the pid from step 6, unlink the socket, report `no_socket`.
   A windowed-but-uncontrollable mpv is therefore never left behind.
8. Helper: `request_log_messages "error"` on the live connection, **before** any
   load, so the first channel's failure text is captured (F3).
9. Helper `apply_channel(client, channel, session)` - the body factored out of
   `cmd_play` (`bin/omarchy-iptv:1747-1777`) and shared verbatim by `play` and
   `player start`, in this order:
   a. `set_property title "$>" + name`
   b. `set_property force-media-title name`
   c. the three pairs from `header_properties()` (`bin/omarchy-iptv:1720`),
      unchanged, always all three
   d. `set_property user-data/omarchy-iptv <stash with entryId:null>`
   e. `loadfile <url> replace` -> reply carries `data.playlist_entry_id`
   f. `set_property user-data/omarchy-iptv <stash with entryId:<from e>>`
   g. `set_property user-data/omarchy-iptv-owner <owner claim>` (start/probe only)
10. Helper: release the lock (close the fd). The lock is deliberately **not**
    held across step 11, so a `player stop` can interleave.
11. Helper: observe the connection for `--first-load-timeout` (3 s), collecting
    `start-file` (confirming `entryId`) and `end-file` for that entry, plus
    `log-message` lines run through the existing `redact_urls()`
    (`bin/omarchy-iptv:259`) before they leave python. Emit `firstLoad`.
12. `handlePlayerResult()` in Service.qml: `playerPending = false`;
    `entryOwners[entryId] = {id, name}`; on `firstLoad.state === "failed"`
    raise the failure path (4.8) at once rather than waiting for the socket; on
    `mpv_missing` set `mpvAvailable = false` + `notify("mpvMissing")`; on `busy`
    or `no_socket` use the existing `playRetryTimer` backoff
    (`Service.qml:839-840`, 300 * n, max 3); on `superseded` do nothing.
13. In parallel: `playerSocketTimer` (250 ms, repeat) has been setting
    `playerSocket.connected = true` since step 2 and connects as soon as mpv
    binds. On connect it sends exactly `request_log_messages "error"` and
    `observe_property 1 idle-active`. Observed properties are dropped when a
    connection closes, so a new shell re-subscribes rather than inheriting.

Two concurrent IPC clients are safe: mpv names them `ipc_0`/`ipc_1` and
correlates by `request_id`.

### 4.5 Reattach on service start

`Component.onCompleted` (`Service.qml:1476`) keeps `mkdirProc` and `whichProc`
and adds one call on `playerProc`:
`player probe --socket S --owner-pid <Quickshell.processId>`
(`Quickshell.processId` is verified present: `quickshell-core.qmltypes:898`,
readonly int, `isPropertyConstant`). Until it answers - about 130 ms, the
measured helper start cost - the UI shows idle rather than guessing.

`player probe` is lock-free and side-effect-free except for one stale-socket
unlink. It runs `find_player()`, then `connect()` + four
`get_property` reads (`idle-active`, `mpv-version`,
`user-data/omarchy-iptv`, `user-data/omarchy-iptv-owner`), and with
`--owner-pid` it writes the owner claim. **`path` and `media-title` are never
read into the shell**: `path` is a credentialed URL, and `media-title` is
verified stale after playback ends (it still returns the previous channel's
`force-media-title` while `idle-active` is true).

`applyProbe()` in Service.qml, by case:

| Probe result | Behaviour |
|---|---|
| `running:false` | Nothing playing. `playerWanted = false` (the retry timer stops; no idle polling). If `state.json.session` names a channel, mark it in `failedAt` and clear `session` (PO-3) |
| `running:true, responsive:true, stash.playing:true, idle:false` | Restore `nowPlaying` from the stash; `playerPending = true` until the socket connects; arm `healthTimer`; queue `reconcileNowPlaying()` for `channelsLoaded` |
| `running:true, responsive:true, stash absent or `playing:false`, or `idle:true`` | Under `--idle=once` an idle player exists only between spawn and first `loadfile`, so this is either a racing start or a foreign/pre-M2-02 player. Re-probe once after 500 ms; still ambiguous -> `player stop`, show idle |
| `running:true, responsive:false` | Wedged. `player stop` (ladder from rung 1, pid already known), show idle |

`nowPlaying` is restored **directly from the stash**, before `channelIndex`
exists - the stash carries `name`, `group` and `launchedFrom`, so the bar and
the guide are correct immediately. `reconcileNowPlaying()` then runs once the
channels cache loads, resolves `id` against `channelIndex`, and fixes the zap
ring; a playlist that changed while the shell was down degrades to name-only
rather than resolving to the wrong channel. This is the fix for "the reattach
resolves against an empty index".

### 4.6 Now-playing recovery

The record lives inside the surviving mpv process, never on disk, in two sibling
top-level `user-data` nodes. Both were probe-verified on 0.41: a sub-path write
returns success, a **different** client reads back the identical object with
non-ASCII intact (`"Canal E 7"`), `observe_property` on the sub-path registers,
the top level is not writable (`set_property user-data {...}` -> "error
accessing property"), and there is no delete (`del_property` -> "invalid
parameter"). Deep paths are deliberately not used - two siblings avoid both the
unverified nesting and any read-modify-write race.

```
user-data/omarchy-iptv
{"schema":1,"playing":true,"id":"t:bbc1.uk","name":"BBC One HD","group":"UK",
 "launchedFrom":"g:uk","sourceKey":"a1b2c3d4","since":1758000123,
 "entryId":2,"seq":41}

user-data/omarchy-iptv-owner
{"schema":1,"pid":301706,"startTime":"9912345","at":1758000100}
```

`launchedFrom` is the zap-ring scope (`Model.launchScope` / `Model.zapRing`,
`Model.js:719-725`) - pure UI intent that no built-in mpv property could ever
report - which is exactly why the shell's own value is stashed and echoed. Its
presence is what makes `next`/`previous` ring the same list after a restart.
`sourceKey` (`Service.qml:141`) is carried so a reattach into a *different*
active source resolves as "not in this playlist" instead of matching the wrong
row. Liveness is `socket connected && idle-active === false && stash.playing`;
identity comes only from the stash.

There is no `player.json`, and `state.json.lastPlayed` remains a Recents entry,
not a recovery source.

### 4.7 Liveness: `playerUp` and every read site

```qml
property bool  playerPending: false     // set synchronously in startPlayer()
property bool  playerWanted: false      // arms playerSocketTimer
readonly property bool playerUp: playerSocket.connected || root.playerPending
readonly property bool playing: playerUp && nowPlaying !== null
```

`playerPending` is cleared by the socket connecting, by `handlePlayerResult()`,
or by `playerWatchdog` (12 s) - whichever is first. That gives `playerUp` the
same synchronous birth edge `mpvProc.running` had, and a sub-second death edge
from socket EOF, which is strictly better than a 10 s poll.

Every current `mpvProc.running` read, by role. A lane that changes one without
consulting this table breaks a D-LIVE-15 or D-LIVE-17 invariant.

| Line | Role | New expression | Note |
|---|---|---|---|
| 197 | UI gate (`playing`) | `playerUp` | birth edge preserved by `playerPending` |
| 282 | same-row re-select | `playerUp` | a false negative costs one redundant `player start`, which adopts and re-zaps |
| 308 | `previousPlaying` stash | `playerUp` | |
| 319 | play fork | `playerUp && !stopping` | **never a correctness gate**: the helper is idempotent |
| 356 | `stop()` early return | **deleted** | `stop()` always issues `player stop`; a no-op if nothing is there |
| 370, 381, 385-388 | `escalateStop` ladder | **deleted** | the ladder moves into the helper (4.9) |
| 397 | `restartPlayer` guard | `playerUp && !stopping` | now issues `player restart --from term` |
| 828, 833, 845 | `handleControlResult` play branches | `playerUp` | the `not_running` disambiguation collapses: a failed `play` falls back to the idempotent `startPlayer()` |
| 852, 861 | `handleControlResult` stop branch | `playerUp` | |
| 865 | pending zap drain | `playerUp` | |
| 1618 | `healthTimer.running` | `playerUp \|\| nowPlaying !== null` | **must not** be gated on `playerUp` alone, or a lie switches off its own reconciler |
| 1700 | `relaunchTimer` guard | `!playerUp` | |
| 1715 | `playRetryTimer` guard | `playerUp && !stopping` | |
| 1729 | `focusTimer` guard | `playerUp` | `playerPending` keeps the 3 s focus budget alive across a cold start |

### 4.8 Crash and end-of-stream detection

Four signals, in order of latency.

1. **`player start`'s own first-load window** (0-3 s, cold start only). Catches
   a first channel that fails before any QML subscriber could exist.
2. **`end-file` over the QML socket.** Verified reasons on 0.41: a dead stream
   gives `{"reason":"error","playlist_entry_id":N,"file_error":"loading failed"}`;
   a clean end gives `"eof"`; our `stop` gives `"stop"`; **a zap also gives
   `"stop"`, immediately followed by `start-file` for the new entry**; an
   intermediate `.m3u8` master resolution gives `"redirect"`.
3. **Socket EOF** (`connectionStateChanged` with `connected === false`). Covers
   every death - `quit`, SIGTERM, SIGKILL, segfault - and is the one-for-one
   replacement for `mpvProc.onExited`.
4. **The 10 s `status` poll**, unchanged, which is the only thing that catches a
   wedged-but-connected mpv, and the degraded-mode detector if the QML socket
   is unusable (mpv still exits on failure under `--idle=once`).

`handlePlayerLine(line)` routes: `start-file` sets `currentEntryId` and clears
`lastEndFile`; `end-file` stores `{reason, file_error, playlist_entry_id}`;
`log-message` at level error/fatal goes to `rememberStderr()`
(`Service.qml:902-909`) which applies `Model.redactUrls` and keeps the same
5-line tail - unchanged code, unchanged S-01/D-QA-01 guarantee, memory only.
`property-change idle-active` is informational.

`handlePlayerGone()` is today's `handleMpvExit` (`Service.qml:911-951`) with the
exit code replaced by `Model.endedVerdict(lastEndFile, userStopped, stopping)`:

| Input | Verdict | Rationale |
|---|---|---|
| `userStopped` or `stopping` | silent | we caused it; today's behaviour |
| `reason: "quit"` | silent | the user pressed `q` in mpv; today's exit-0 silence |
| `reason: "eof"` | silent stop | today's exit-0 silence (PO-4) |
| `reason: "error"` | stream failure | notify + `withFailed` |
| `reason: "stop"` with no user stop | stream failure | a load we issued was replaced and then the process died |
| `reason: "redirect"` | ignored, never terminal | fires on the `.m3u8` masters IPTV uses most |
| no `end-file` at all | stream failure, generic reason | crash / SIGKILL |

**The entry gate fails open** (F4). The channel named is
`entryOwners[lastEndFile.playlist_entry_id]` when that id is known, else
`nowPlaying`. `entryOwners` is a QML map of at most four
`entryId -> {id, name}` entries, populated from the `entryId` that both `play`
and `player start` now return. A null or unrecognised entry id never suppresses
a notification - it only degrades which channel is named. Nothing else about the
notification path changes: `Model.notifyArgv` (`Model.js:1295`, with its S-04
leading-dash and typographic-quote rules), `NOTIFY_IDS.streamFailed = 74011`,
`Model.withFailed` and the session-only `failedAt` map are untouched.

### 4.9 The stop ladder

The UI contract is unchanged: `stop()` still clears `pendingPlayId`,
`wantFocus`, the timers and `nowPlaying` synchronously
(`Service.qml:345-355`) so the bar and the guide drop the channel on the
keystroke. `escalateStop()`, `stopTimer` and `stopStage` are deleted from QML.
`stop()` then does exactly one thing, unconditionally:

```qml
root.playSeq += 1
root.stopAt = Date.now()                                   // section 4.10
Quickshell.execDetached(Model.playerStopArgv(socketPath, root.playSeq))
```

Inside the detached helper, synchronously, under the lock:

| t | Rung | Action |
|---|---|---|
| 0 | discover | `find_player()`. No process and no socket -> `{ok:true,running:false}`. Socket but no process -> `unlink_stale_socket()`, done |
| 0 | `quit` | connect, `request(["quit"], allow_close=True)` (today's `cmd_stop` body). Poll `os.kill(pid,0)` every 50 ms for `STOP_QUIT_GRACE_MS` = 2000 |
| 2.0 s | `term` | re-verify pid + start time + the `--input-ipc-server` token, then `os.kill(pid, SIGTERM)`. Poll 2000 ms |
| 4.0 s | `kill` | re-verify, `os.kill(pid, SIGKILL)`. Poll 500 ms |
| 4.5 s | settle | `find_player()` empty **and** `connect()` returns ENOENT/ECONNREFUSED -> `unlink_stale_socket()` (S_ISSOCK-guarded). Never unlink on a successful connect |

The timeline is byte-for-byte `README.md:145-157` and
`Model.stopEscalation`'s ladder (quit@0, SIGTERM@2 s, SIGKILL@4 s), and it is
now **stronger in three ways**: it cannot be starved by a busy control channel;
it completes even if the shell is SIGKILLed one millisecond after it is issued;
and because the pid comes from `/proc` and not from `get_property pid`, a wedged
mpv - the D-LIVE-17 case, where IPC is by definition dead - is reachable. The
pid is re-verified against `/proc/<pid>/stat` field 22 and the cmdline token
immediately before **each** signal, so a recycled pid is never signalled; today
that guard is unnecessary only because Qt signals its own child.

`Model.stopEscalation` (`Model.js:1061`) remains the reducer of record and is
mirrored in python. The two are pinned by a shared vector table in
`tests/fixtures/player-argv.json`, read by both `tests/Model.test.js` and
`tests/test_player.py` - the cross-language parity pattern the repo already uses
for `fnv1a32` and `normalizeText`. The seven existing `stopEscalation` checks
(`tests/Model.test.js:439-445`) stay green unmodified.

`restartPlayer()` (the health verdict) issues `player restart --from term`,
which runs the ladder and the spawn under **one** lock acquisition. That removes
the stop-then-start race that two independent detached calls would have. Its
bookkeeping (`relaunched`, `relaunchPending`, one automatic relaunch per player)
is unchanged.

### 4.10 Ordering: the intent sequence number

`flock` grants are not FIFO on Linux and two `execDetached` spawns are not
guaranteed to start in issue order, so a `stop` then a `play` can execute as
start-then-stop and kill the channel the user just selected. That inversion
killed two of the four submissions.

The fix is a monotonic **intent sequence number** owned by Service.qml:
`root.playSeq += 1` on every `play()` and every `stop()`, passed as `--seq N`.
Under the lock, a verb whose `--seq` is **lower** than the value recorded in
`player.lock` aborts as `superseded` and does nothing. Ordering is then by issue
time, not by lock-grant order. `playSeq` survives a shell restart: `player probe`
returns the recorded `seq`, and `applyProbe()` sets
`playSeq = max(probe.seq, 0) + 1`. If the lock file is deleted or the runtime
dir cleared, both sides reset to 0 together and the inode re-check (4.2) catches
the recreate.

`stopping` is redefined, keeping the property name so its four existing read
sites are untouched:

```qml
property real stopAt: 0
readonly property bool stopping: stopAt > 0        // cleared on socket EOF, or by stopSettleTimer (5 s)
```

While `stopping` is true, `play()` always takes the `startPlayer()` branch and
never the IPC branch, so a zap can never be written to a dying socket. That
preserves the documented behaviour ("Playing a channel while the old player is
still shutting down starts a fresh player once it has exited") with a stronger
mechanism: `player start` blocks on the lock behind the running ladder and, when
it gets in, is guaranteed by the seq rule to be the later intent.

### 4.11 Headers and title (S-01 raw prefix)

**Title.** `--wayland-app-id=omarchy-iptv` stays on the launch argv: a Wayland
`app_id` is fixed at surface creation, so a runtime `set_property` would not
retitle an existing window. Hyprland derives `.class` from the protocol-delivered
`app_id` and has no knowledge of the client's parent, so
`Model.focusPlayerArgv()` (`hyprctl dispatch focuswindow class:omarchy-iptv`,
`Model.js:1283`), the Lua window rules, and `scripts/qa-live.sh:154-155`'s
`pgrep -af -- '--wayland-app-id=omarchy-iptv'` all keep working verbatim after
detachment.

The launch argv keeps the neutral constants `--title=$>IPTV` and
`--force-media-title=IPTV` (which is what `Model.buildMpvArgv` already emits
when `name` is absent, pinned by `tests/Model.test.js:337`), so the window never
flashes mpv's default `"No file - mpv"`. The channel title arrives over IPC in
the same batch as the `loadfile`, from the existing `cmd_play` lines
(`bin/omarchy-iptv:1762-1765`).

The S-01 rule is unchanged and holds on the IPC path, verified on 0.41:
`set_property title "$>BBC ${path} $$"` succeeds and reads back **byte-identical
including the `$>`**, so expansion happens at render time, not at store time,
and a playlist entry named `${path}` still cannot put a credentialed URL in the
window title. `force-media-title` is confirmed **not** expanded (set to
`"BBC ${path}"`, `media-title` returns it verbatim), so it carries the plain
name and must not carry the prefix. `Model.MPV_RAW_PREFIX` / `mpvWindowTitle`
(`Model.js:1246-1250`) and the helper's mirror (`bin/omarchy-iptv:139`) are
untouched, and `--title` stays in `MPV_RESERVED`.

**Headers.** `header_properties()` (`bin/omarchy-iptv:1720-1745`) is unchanged
and still returns all three pairs **unconditionally** on every load -
`user-agent` (falling back to `option-info/user-agent/default-value` then the
literal `libmpv`), `referrer`, `http-header-fields` - so a channel without
headers actively resets the previous channel's. That is requirement 7's clearing
mechanism, it is structural rather than a remembered step, and it is already
covered by `test_clears_headers_for_a_channel_without_any` and
`test_user_agent_falls_back_to_libmpv_without_option_info`. The only change is
that the **first** channel now goes through it too, where today it gets headers
from argv and is the one channel whose headers nothing ever clears.
`Model.headerArgs` leaves `buildMpvArgv` but stays in `Model.js` with its two
tests as the validator of record for `^[A-Za-z0-9-]+$` names and CR/LF rejection.

### 4.12 mpvArgs filtering

`Model.splitMpvArgs` (`Model.js:1207`) is behaviourally unchanged: same
`/^--[a-z0-9][a-z0-9-]*(=.*)?$/` token regex including the D-QA-11
lowercase-only rule, same `--no-` form rejection, same `{args, rejected}` shape,
same `console.warn`. Filtered tokens land **after** the fixed options, so
`--ytdl=yes` still overrides the built-in `--ytdl=no` as documented. The helper
re-validates each `--mpv-arg` against a python mirror of the same regex and set
(defence in depth, and it is a public CLI) and reports dropped tokens in
`warnings`; a parity test asserts the two reserved sets are equal.

`MPV_RESERVED` gains ten entries, every one of which is reachable today from the
settings panel and writes a credentialed URL somewhere durable:

| Added | Why |
|---|---|
| `--log-file` | mode 0644 world-readable, level forced to at least `-v -v` which `--msg-level` **cannot** lower, and one failed load writes the full URL seven times plus the whole command line. A permanent, worse version of S-03 |
| `--dump-stats` | on-disk file including the command line |
| `--stream-record` | writes the stream itself to disk |
| `--save-position-on-quit`, `--watch-later-dir` | writes a watch-later file whose header line is the stream path |
| `--osd-msg1`, `--osd-msg2`, `--osd-msg3` | property-expanding: `--osd-msg1=${path}` puts the credentialed URL on screen and into every screenshot |
| `--term-status-msg`, `--screenshot-template` | property-expanding into a terminal and into file names |

`--ytdl` stays **unreserved** (PO-5): `Model.js:1270-1273` documents re-enabling
it as a deliberate escape hatch for non-direct URLs. The cost is real and must be
written down rather than left silent: with `--ytdl=yes`, mpv's builtin
`ytdl_hook` spawns `yt-dlp ... -- <full URL>` on every failed open, putting the
credentialed URL on **another** process's argv. `~/.config/mpv/mpv.conf` is
outside this filter by construction and is documented as such in
SECURITY-REVIEW.md; the settings panel is the reachable-by-accident path, a
user's own mpv config is their deliberate choice.

### 4.13 Health check

Unchanged: `healthTimer.interval = 10 s`, `Model.healthTick` with its
`HEALTH_SKIPS_BEFORE_RESTART = 3` busy-skip counter, `Model.statusHealthy`, the
two-strike branch in `handleControlResult` (`Service.qml:804-819`), the
`status --socket S` verb on `controlProc`. Two changes only: the timer's gate
becomes `playerUp || nowPlaying !== null` (so it can never be switched off by a
stale false), and the two-strike verdict calls `player restart --from term`
instead of driving a QML ladder. `status`'s new `process:{found,pid}` field lets
the service distinguish "the process is gone" from "the process is wedged"
without a second call.

### 4.14 Teardown on plugin disable or removal

`shell.qml _syncServices()` destroys a service instance when its plugin is
disabled or removed, and `serviceKeepLoaded` is consulted only on the
hot-reload path - so the destroy fires in both cases we must distinguish, and
Quickshell 0.3.1 has no shutdown or `aboutToQuit` signal (verified absent from
`quickshell-core.qmltypes`; only `lastWindowClosed`, `reloadCompleted`,
`reloadFailed`).

The discriminator is the **owner claim**, not the destruction event:

```qml
Component.onDestruction: Quickshell.execDetached(
    Model.playerOrphanCheckArgv(socketPath, Quickshell.processId, 6))
```

`player orphan-check --owner-pid P --grace 6` sleeps 6 s, then reads
`user-data/omarchy-iptv-owner`:

- The claim's `pid` is no longer `P` -> a successor service adopted the player.
  **Do nothing.** (`omarchy-restart-shell` polls `omarchy-shell shell ping`
  every 100 ms for up to 2 s after relaunch, so the successor has claimed well
  inside the grace.)
- The claim is still `P`, and pid `P` is alive with a matching `/proc/<pid>/stat`
  start time -> the service object died while its shell lives: the plugin was
  disabled or removed. **Run `player stop`.**
- The claim is still `P` and pid `P` is dead -> the shell exited and nothing has
  claimed the player within 6 s. **Do nothing** (`omarchy-launch-shell`
  supervises and relaunches; a slow restart must not kill playback).

Residual, stated plainly: a shell that is SIGKILLed and never comes back leaves
a player running until logout. That is not a regression - `Process::~Process()`
only runs on a clean teardown today, so a SIGKILLed quickshell leaves mpv alive
in v0.2.0 too - and the compositor unit's `KillMode=control-group` reaps it at
session end. `omarchy-iptv player stop` is added to the README's Uninstall
section as the manual escape hatch.

## 5. Hard requirements

| # | Requirement | Status | Mechanism |
|---|---|---|---|
| 1 | Exactly ONE player instance. Never a second window | **kept (strengthened)** | Three layers: a `/proc` scan on the exact `--input-ipc-server=<abspath>` token plus uid is the authoritative existence check (never `connect()`, which succeeds through the listen backlog against a wedged mpv); `flock` with an inode re-check serialises launchers and survives an unlink-and-recreate; `player start` is idempotent - a live answering player is adopted and zapped, not duplicated. Only one code path (`spawn_detached`) ever execs mpv. If the scan ever finds several, the one that answers the socket is kept and the rest are laddered down. A spawn whose socket never binds is reaped by the helper that created it using the pid read back over a pipe, so an un-killable window cannot exist and cannot multiply. QML's `playerUp` is advisory UI state and is **never** a spawn gate |
| 2 | Zapping reuses the window via `play --id <id> --socket <s>` -> title / force-media-title / UA / referrer / header-fields -> `loadfile <url> replace` | **kept** | `cmd_play`'s wire sequence and CLI surface are unchanged; its body is factored into `apply_channel()` and shared with `player start`, so first-play and zap become one implementation instead of two. All 23 `tests/test_mpv.py` cases pass unmodified. `pendingPlayId` burst coalescing (`Service.qml:314-318`) and the `previousPlaying` rollback are unchanged. `play` gains optional `--scope`/`--since` and returns `entryId`, both additive. Verified: `loadfile ... replace` while playing emits `end-file{reason:"stop"}` then `start-file` on one pid, window intact |
| 3 | Window class `omarchy-iptv`, title = channel name, `$>` raw prefix on `--title` (force-media-title NOT expanded) | **kept** | `--wayland-app-id` stays on argv (app_id is fixed at surface creation); title and force-media-title move to IPC, where the `$>` marker is verified stored literally and `force-media-title` verified non-expanded on 0.41. `Model.MPV_RAW_PREFIX` / `mpvWindowTitle` and the helper mirror untouched; `--title` stays reserved. Hyprland matching and `focusPlayerArgv` are unaffected by who spawned the client |
| 4 | Stop immediate in the UI; quit -> SIGTERM after 2 s -> SIGKILL after 2 s (D-LIVE-17); never leaves an orphan | **weakened -> PO-2** | The ladder is **strengthened**: `nowPlaying = null` still clears synchronously; the rungs run inside one detached helper so they cannot be starved by a busy control channel and complete even if the shell dies mid-ladder; the pid comes from `/proc`, so a wedged mpv - the case the ladder exists for - is now reachable, where an IPC-only pid source could never signal it; pid + start time + cmdline are re-verified before each signal. Timeline unchanged at quit@0 / TERM@2 s / KILL@4 s. **What weakens:** disabling or removing the plugin no longer kills the player through `~Process()`. Section 4.14's owner-claim orphan-check covers it best-effort; a SIGKILLed shell that never returns leaves the player until logout (not a regression - the same is true today - but it is a longer window). **PO-2 asks whether best-effort plus a documented `player stop` is acceptable** |
| 5 | Health check every 10 s via helper `status`; two consecutive failures relaunch once; stale sockets unlinked | **kept** | Interval, `Model.healthTick`, the busy-skip counter, `Model.statusHealthy`, the two-strike branch and the one-relaunch-per-player rule are all unchanged. The timer's gate becomes `playerUp \|\| nowPlaying !== null` so it can never be gated off by a stale flag. The verdict issues `player restart --from term` - one lock acquisition, ladder then spawn - removing the stop/start race two detached calls would have. Stale-socket unlinking gains three more callers (probe, start's reconcile, stop's settle) and keeps its `S_ISSOCK` guard and both existing tests. Socket EOF adds a sub-second primary death signal on top of the poll |
| 6 | Stream failure or unexpected exit raises a notification naming the channel, stderr redacted to hosts (S-01/D-QA-01), channel marked failed for the session | **weakened -> PO-3** | Live path **improved**: control flow comes from `end-file.reason` + `file_error` rather than an exit code, which separates a deliberate stop from a real error and ignores `redirect`; failure text comes from `request_log_messages "error"`, redacted by `redact_urls()` in python **before** it crosses into QML and then again by `rememberStderr`'s `Model.redactUrls`; a cold-start first-channel failure is caught by `player start`'s own 3 s window, so the commonest real failure cannot be missed; `notifyArgv`, `NOTIFY_IDS`, `withFailed` and the 5-line tail are untouched; the entry gate fails open so a missing `entryId` never suppresses a toast. **What weakens:** a failure that happens while no shell is attached cannot be toasted at all - `org.freedesktop.Notifications` is owned by quickshell itself and is not D-Bus activatable, so nothing on this machine can notify while the shell is down. **PO-3 asks whether to mark the channel failed silently on reattach (recommended) or raise a stale toast** |
| 7 | Per-channel `#EXTVLCOPT`/`#KODIPROP` headers applied and CLEARED between channels | **kept (strengthened)** | `header_properties()` unchanged - it always sets all three properties, so a header-less channel actively resets the previous one's. The only change is that the **first** channel now goes through it too, removing the one channel today whose argv-supplied headers nothing ever clears. `loadfile`'s per-file options were evaluated and rejected: values must be strings and `http-header-fields` then serialises comma-separated, so a playlist-supplied value containing a comma would split into two wrong headers - the hazard `Model.js:1223` already documents |
| 8 | User `mpvArgs` still apply, reserved-option filter intact | **kept (strengthened)** | `splitMpvArgs` and the nine existing `MPV_RESERVED` entries are unchanged, including the `--no-` rule and D-QA-11 case-sensitivity; ordering preserved so `--ytdl=yes` still wins. Ten additions (4.12), each a durable URL-on-disk or URL-on-screen path reachable from the settings panel today. Tokens travel as repeated `--mpv-arg`, never joined, and are re-validated by a python mirror pinned equal by a parity test |
| 9 | argv-only launching. No shell interpolation, no sudo, no third-party runtime dependency. Helper stays stdlib-only python3 | **kept** | Four hops, four argv vectors: QML -> helper is the existing `["python3", helperPath, ...]` `Process` command list and `Quickshell.execDetached(list)`; helper -> mpv is `os.execvp("mpv", argv)` with a literal argv[0]; helper -> notification is never used. No `bash -lc`, no `eval`, no `systemd-run`, no `uwsm-app` (rejected explicitly for its `eval "$CMDLINE"`), no `hyprctl exec_cmd`. New stdlib imports only: `fcntl`, `signal`, `errno` (`socket`, `stat`, `os`, `time`, `json` already imported) |
| 10 | Socket under `$XDG_RUNTIME_DIR/omarchy-iptv/` with 0700/0600 modes | **kept** | Paths unchanged. The directory is 0700 from `mkdirProc` **and** from `ensure_private_dir()` inside every `player` verb, because mpv fails completely silently with no parent directory. mpv sets the socket 0600 itself (verified under `umask 0022`). The one new file, `player.lock`, is `O_CREAT\|O_RDWR` 0600 in the same directory and contains only a sequence number. No log file, no `player.json`, nothing else added |
| 11 | Bar widget and guide keep accurate now-playing state, RECOVERABLE after a shell restart | **kept** | `BarWidget.qml:38-39`, `Guide.qml` and `statusSummary()` are untouched; only `playing`'s definition changes, and `playerPending` preserves its synchronous birth edge so the bar lights up on the same frame as today. Recovery reads `user-data/omarchy-iptv` out of the surviving process - verified readable by a client that connects after the original closed - including `launchedFrom` and `sourceKey`, which mpv could never derive. `nowPlaying` is restored before `channelIndex` exists and reconciled on `channelsLoaded`, so the bar is right immediately and the zap ring is right once the cache lands. `media-title` is never used for identity (verified stale after playback ends) and `path` is never read into the shell at all |

## 6. Security and privacy

**Claim: after M2-02 no stream URL and no header value reaches any command line,
any file, any unit name, any environment variable or any log, on any channel,
including the first.** The proof is by enumeration of every sink.

**Command lines.** The complete mpv launch argv:

```
mpv --input-ipc-server=<runtimeDir>/mpv.sock
    --wayland-app-id=omarchy-iptv
    --force-window=immediate
    --idle=once
    --keep-open=no
    --title=$>IPTV
    --force-media-title=IPTV
    --msg-level=all=error
    --ytdl=no
    <filtered user mpvArgs...>
```

Relative to `Model.js:1257-1281` this drops the trailing `"--"` and
`str(p.url)`, drops the `headerArgs(p.headers)` splice, drops the per-channel
`--title=`/`--force-media-title=`, and changes `--idle=no` to `--idle=once`.
Nothing channel-specific remains. The other three argv:

- `python3 bin/omarchy-iptv player start --socket S --cache-dir C --id t:bbc1.uk
  --seq 41 --scope g:uk --since 1758000123 --mpv-arg --profile=low-latency`
- `python3 bin/omarchy-iptv play --id t:bbc1.uk --socket S --cache-dir C`
  (unchanged today)
- `python3 bin/omarchy-iptv player stop --socket S --seq 42`

`--id` is `Model.channelId()` output: `t:<tvg-id>` or `u:<fnv1a32(url)>`
(`Model.js:245-251`) - a hash or a provider-assigned id, never the URL. The URL
is resolved from `channels.json` (0600) **by the helper itself** and travels only
over the 0600 socket, so it never crosses a process boundary in either
direction. Residual, disclosed rather than hidden: `--id` and
`--force-media-title` are a per-zap record of *what* the user is watching,
readable by other local accounts through `/proc/<pid>/cmdline` (0444, `/proc`
mounted without `hidepid` here). That is unchanged from today and is not a
credential; it is noted in SECURITY-REVIEW.md rather than left implied.

**Files.** New artifacts, complete list:

| Path | Mode | Contents | URL-bearing |
|---|---|---|---|
| `$XDG_RUNTIME_DIR/omarchy-iptv/player.lock` | 0600 | `{"schema":1,"seq":N,"verb":"start","at":1758000100}` | no |
| `$XDG_STATE_HOME/omarchy-iptv/state.json` key `session` | 0600 (existing file, existing mode, `O_EXCL`-created by `state init`) | `{"id":"t:bbc1.uk","name":"BBC One HD","at":1758000123}` | no |

Nothing else. No `player.json`, no log file, no watch-later file, no systemd
unit, no drop-in. `--log-file` and `StandardError=append:` are rejected in
section 3 precisely because they would write credentials to disk.

**Unit names and environment.** There is no unit. `spawn_detached` passes the
inherited environment unchanged - no `--setenv`, so nothing moves from the
0400 `/proc/<pid>/environ` onto a 0444 cmdline (a real, low-severity exposure
one of the rejected designs introduced).

**Logs.** mpv's stdio is `/dev/null` from before `execvp`, so nothing of mpv's
reaches the journal - which matters here because `omarchy-launch-shell` runs
`systemd-cat -t omarchy-shell -- quickshell`, making quickshell's stdout and
stderr a persistent, group-readable journal stream. The helper's own `log()`
goes to stderr, is collected by `StdioCollector`, and is only ever printed
through `console.warn(Model.redactUrls(...))`. Diagnostics travel as
`log-message` events over the 0600 socket and are reduced to `scheme://host` by
`redact_urls()` **inside python** before they enter QML, then again by
`rememberStderr`'s `Model.redactUrls` - two independent passes. Verified that
level-`error` messages still arrive under `--msg-level=all=error`:
`[stream/error] Failed to open http://127.0.0.1:1/secret-token-XYZ/s.m3u8`.
`path` is never observed and `media-title` is never read for identity.

**Net effect on S-03.** Closed, not narrowed. The URL's only homes become
`channels.json` (0600), the helper's memory, mpv's memory, and the 0600 AF_UNIX
socket inside a 0700 directory. `SECURITY-REVIEW.md:36` moves from "open by
design" to fixed, recording that the `--idle` branch was taken as prescribed
(with `once`, not `yes`) and that the `--playlist=<0600 file>` alternative in
the same line was rejected for putting the URL on disk.
`ARCHITECTURE.md:504-505` is discharged. Two new findings are filed: the
ten-option `MPV_RESERVED` gap (4.12) and the `--ytdl=yes` / `yt-dlp` argv
exposure (PO-5).

## 7. Failure modes

| Case | Designed behaviour |
|---|---|
| **Restart while playing** (`omarchy restart shell`, the headline case) | `quickshell kill -p ... --any-display` kills only the quickshell process; mpv is a `setsid`'d grandchild of `systemd --user`, so it is untouched and the stream does not glitch. The new service's `player probe` (about 130 ms after start) finds it by the `/proc` token, reads the stash, restores `nowPlaying` and claims ownership; the socket subscriber reconnects within 250 ms. The bar shows the channel again inside the 2 s acceptance bar. `playSeq` resumes from the lock record. The pending `orphan-check` from the dying shell finds the claim reassigned at t+6 s and does nothing |
| **Crash mid-zap** | The shell dies between `play`'s helper call and its reply. mpv either switched or did not; the stash was written before the `loadfile` with the new identity and rewritten after with the entry id. On reattach the stash is the truth: if `loadfile` landed, `idle-active` is false and the new channel shows; if it did not, mpv exited under `--idle=once`, the probe reports `running:false`, and `state.json.session` names the channel for a silent failed-mark (PO-3) |
| **Overlapping shells** | The runtime directory is the ownership domain. Two services sharing one `XDG_RUNTIME_DIR` both adopt the same player, both zap it and both can stop it - last intent wins by `seq`, and **no second window is possible** because the `/proc` scan sees the existing process. The loser's `orphan-check` is a no-op because the claim names the other shell. The dev harness already exports its own `XDG_RUNTIME_DIR` (`run.sh:93`), so it can never signal the live player |
| **Stale socket** (the live state right now: `srw------- mpv.sock`, no mpv) | `find_player()` returns empty, `connect()` gives ECONNREFUSED, `unlink_stale_socket()` removes it (S_ISSOCK only - a regular file at the path is left alone and reported as `socket_path_blocked` with no spawn), then the spawn proceeds. mpv never unlinks its own socket on **any** exit path - verified for `quit`, SIGTERM and SIGKILL - so unlinking is permanently ours, and the guard means a racing start's fresh socket is never deleted |
| **Wedged process** (SIGSTOP, or the D-LIVE-17 mapped-but-never-answers case) | `connect()` succeeds through the listen backlog and then never replies - which is exactly why `connect()` is not the existence check. `find_player()` sees the process; the `get_property mpv-version` probe times out at 2 s; `status` reports `ok:false` with `process.found:true`; two strikes call `player restart --from term`, which SIGTERMs then SIGKILLs the pid from `/proc` and spawns fresh under the same lock. The equivalent path in an IPC-only design cannot obtain a pid at all |
| **Suspend / resume** | mpv survives suspend and stays connected; a stalled stream after resume is not detected, exactly as today (no stall detection exists in v0.2.0). `status` reports healthy, the guide shows playing. Unchanged behaviour, documented; a future milestone could observe `demuxer-cache-time` |
| **Logout** | `wayland-wm@hyprland.desktop.service` is `ExitType=main` + `KillMode=control-group` + `TimeoutStopUSec=10s`, and mpv inherits that cgroup across `fork` (`setsid` does not change cgroup membership), so it is SIGTERMed then SIGKILLed at session end. `loginctl show-user 1000` reports `Linger=no`, so nothing survives to the next session. No cross-session orphan is possible, which is why no systemd unit is required |
| **`XDG_RUNTIME_DIR` cleared while playing** | The socket file and the lock vanish; mpv holds a listening socket nobody can reach. The `/proc` scan still finds it by cmdline token, `connect()` gives ENOENT -> `responsive:false` -> treated as wedged: laddered down by pid and respawned into a freshly created 0700 directory. `playSeq` resets on both sides together; the lock inode re-check catches the recreate |
| **User-launched mpv with the same app-id** | The `/proc` scan matches on `--input-ipc-server=<our exact socket path>` **and** uid, never on `app_id`, so a user's own `mpv --wayland-app-id=omarchy-iptv` on a different socket is never adopted, never signalled and never counted. Consequence, documented: `hyprctl dispatch focuswindow class:omarchy-iptv` may focus theirs, and `qa-live.sh`'s `pgrep` count may read 2. Narrowing focus to `hyprctl clients -j` matched by pid is deferred |
| **`player start` cannot exec mpv** | The CLOEXEC errno pipe reports it synchronously as `mpv_missing` / `spawn_failed`, restoring the error path `Quickshell.execDetached` destroys (it returns void). Service sets `mpvAvailable = false` and notifies `mpvMissing`, unchanged |
| **mpv starts but never binds the socket** (long path, unwritable dir, bad user `mpvArg`) | The 5 s poll fails; the helper ladders down the pid it read over the pipe, unlinks, and reports `no_socket`. No window is left, and the next `player start` therefore cannot multiply one. The user-visible reason is generic, which is the one diagnostic regression from `/dev/null` stdio (PO-6) |
| **Zap burst across a slow failure** | `end-file{error}` for entry 1 can arrive after the user zapped to entry 2. `entryOwners[1]` names the right channel in the toast and the right row in `failedAt`; `start-file` for entry 2 has already cleared `lastEndFile`. If the entry id is unknown the gate fails open and the toast names `nowPlaying` - degraded, never suppressed |
| **Two players somehow exist** (a user ran `player start` from a terminal against the same socket) | The scan finds both. The one that answers the socket is kept; the others are laddered down and a redacted warning is logged once. `hyprctl clients` returns to exactly one `omarchy-iptv` window |

## 8. Migration and compatibility

**Upgrade from v0.2.0 with a player running.** `omarchy plugin update` +
`omarchy restart shell` normally kills the old attached mpv through
`Process::~Process()`, so the common case is a clean start: the new service
probes, finds nothing, and the leftover socket is unlinked by the first
`player start`. If quickshell was SIGKILLed instead, an old mpv survives with a
URL on its argv and `--idle=no`. The probe finds it by the socket token, it
answers, but `user-data/omarchy-iptv` is absent -> "unknown player" ->
`player stop` -> idle. The user presses Enter once. This is preferable to a
degraded "playing but unidentified" mode that would need its own state and its
own tests. Worth one QA case (PLAYER-MIG-01).

**Contracts.**

| Contract | Change |
|---|---|
| `shell.json` / settings schema | **None.** No new key. `manifest.json` unchanged; `keepLoaded: true` stays required - the service must remain resident to hold the socket subscriber and the timers, even though mpv no longer depends on it |
| `state.json` | One optional nullable key, `session: {id, name, at}`, alongside `lastPlayed`. `STATE_VERSION` stays **2**: `parseState` (`Model.js:759`) and `normalize_state` both whitelist known keys, so a v0.2.0 build reading a v0.3.0 file simply drops it. Written on play, cleared on stop and on a clean end. Its only job is naming the channel for the reattach mark in PO-3 |
| Cache (`channels.json`, EPG, per-source dirs) | **None** |
| Runtime dir | One new file, `player.lock` 0600, beside the unchanged `mpv.sock`. tmpfs, cleared at logout |
| Helper CLI | `play`, `stop`, `status` keep their spelling, exit codes and reply shape; `play` gains optional `--scope`/`--since` and returns `entryId`; `status` gains `process` and `stash`. A new `player` verb group. An older Service.qml against a newer helper therefore still works during a partial upgrade |
| `docs/` | `ARCHITECTURE.md` decision 2 amended (attached `Process` superseded; `waitpid`/stderr replaced by socket EOF + `end-file` + `request_log_messages`), decision 12 amended (`--idle=no` exit-code model replaced by `end-file` reasons, with `--idle=once` preserving the exit-on-end behaviour it relied on), R10 closed, section 3's mpv control path rewritten, 12.1 discharged. `SECURITY-REVIEW.md` S-03 to fixed plus two new findings. `README.md:150-152` limitation deleted; `player stop` added to Uninstall. `QA.md` TC-PLAY-11 inverted, TC-PLAY-08 and SEC-06 rewritten to assert the **absence** of headers and URL from argv. `STATUS.md` gains a real M2-02 board row (line 89 is taken by "merged into M2-01") and a decision-log entry |

**Rollback** is a plugin downgrade plus one shell restart. A player left running
by the new version is reachable with `omarchy-iptv player stop` from a terminal,
or dies at logout with the compositor unit.

## 9. Work plan

Lanes, ownership and merge order are `docs/PLAN-M2.md` section 5 verbatim. A lane
that edits a file it does not own is rejected at merge.

### Lane PA - argv and helper player lifecycle (M2-02-01, lands 1st)

Owns `Model.js`, `bin/omarchy-iptv`, `tests/Model.test.js`,
`tests/Model.spec.qml`, `tests/test_*.py`, `tests/fixtures/player-argv.json`.
Must not touch `Service.qml`, `Guide.qml`, the harness.

- **PA-0 (gate, before any edit).** Headless mpv probes, no window, killed by
  pid: (a) `--idle=once` + `loadfile ... replace` during playback must **not**
  exit mpv; (b) `--idle=once` must exit on `end-file{reason:"error"}`;
  (c) `user-data/omarchy-iptv-owner` as a second top-level sibling node must
  round-trip. If (a) fails, fall back to `--idle=yes` plus an explicit
  quit-on-terminal-idle rule in `player start`/the QML router and re-open PO-1.
- `Model.js`: `buildMpvArgv` drops the URL, the trailing `--`, `headerArgs`,
  `--title=`/`--force-media-title=` per channel, and flips `--idle=no` to
  `--idle=once`; `MPV_RESERVED` gains the ten entries from 4.12; new pure
  functions `playerStartArgv`, `playerStopArgv`, `playerRestartArgv`,
  `playerProbeArgv`, `playerOrphanCheckArgv`, `parsePlayerProbe`,
  `parsePlayerEvent`, `endedVerdict`, `playerStash`. `stopEscalation`,
  `healthTick`, `statusHealthy`, `splitMpvArgs`, `headerArgs`, `mpvWindowTitle`,
  `MPV_RAW_PREFIX`, `notifyArgv`, `focusPlayerArgv`, `redactUrls`, `withFailed`
  unchanged.
- `bin/omarchy-iptv`: factor `cmd_play`'s body into `apply_channel()`; new
  `player` subcommand group (`start`/`stop`/`restart`/`probe`/`orphan-check`);
  `find_player()` (/proc scan), `acquire_lock()` (flock + inode re-check),
  `spawn_detached()` (setsid, double fork, pid pipe, CLOEXEC errno pipe,
  `/dev/null` stdio, close-all), `wait_for_socket()`, `stop_ladder()`,
  `mpv_launch_argv()`, `MPV_RESERVED` mirror, `stop_escalation()` mirror.
  **`MpvIpc` needs one contained change**: `request()` currently drops
  unsolicited event lines with `continue` (`bin/omarchy-iptv:1685`); it must
  append them to `self.events` instead, and a new `drain_events(deadline)` must
  read them, so `request_log_messages` and `end-file` are not discarded.
  `header_properties`, `unlink_stale_socket`, `write_text_atomic`,
  `ensure_private_dir`, `redact_urls`, `load_channels`, `find_channel` reused
  unchanged.
- `tests/`: extend `FakeMpv` to per-connection threads (today `serve()` calls
  `handle(conn)` synchronously, one connection at a time - a persistent
  subscriber would block every control call) and to serve `user-data` sub-paths
  and inject events; new `tests/test_player.py`; author
  `tests/fixtures/player-argv.json` with three vector tables (`mpvArgv`,
  `stopLadder`, `endedVerdict`) read by **both** `tests/Model.test.js` and
  `tests/test_player.py`.

### Lane PB - Service reattach and harness verbs (M2-02-02, lands 2nd)

Owns `Service.qml`, `scripts/dev-harness/*`. Must not touch `Model.js`,
`Guide.qml`, `bin/omarchy-iptv`.

- **PB-0 (gate, before any Service.qml surgery).** Spike
  `Quickshell.Io/Socket` against a python `FakeMpv` in a scratch QML file:
  does setting `connected = true` on a nonexistent path fail cleanly and emit
  `error`, or wedge? Does `parser: SplitParser` deliver mpv's newline JSON?
  The type surface is confirmed present (`quickshell-io.qmltypes:197-239`:
  writable `path`, writable `connected` notifying `connectionStateChanged`,
  `error(QLocalSocket::LocalSocketError)`, `write`, `flush`, `DataStream`
  prototype carrying `parser`) but there is **zero** usage of it anywhere in
  `/usr/share/omarchy/shell`, so nothing on this system exercises it. If the
  spike fails, fall back to degraded mode: no subscriber, failure detection via
  the unchanged 10 s `status` poll plus `player start`'s first-load window, with
  a generic reason. Report to the PO before proceeding.
- Delete `Process { id: mpvProc }` + its `Connections` (`:1876-1889`),
  `launchMpv` (`:874-900`), `handleMpvExit` (`:911-951`), `escalateStop`
  (`:369-394`), `Timer stopTimer` (`:1685`), `stopStage`.
- Add `Socket { id: playerSocket }` + `SplitParser` + `Connections`,
  `Timer playerSocketTimer` (250 ms), `Process { id: playerProc }` +
  `Timer playerWatchdog` (12 s), and the properties `playerPending`,
  `playerWanted`, `playSeq`, `stopAt`, `currentEntryId`, `entryOwners`.
- Add `startPlayer()`, `runPlayerProbe()`, `applyProbe()`,
  `reconcileNowPlaying()`, `handlePlayerLine()`, `handlePlayerGone()`,
  `handlePlayerResult()`; rewire the 20 sites per the table in 4.7;
  `Component.onCompleted` gains the probe; `Component.onDestruction` fires
  `orphan-check`. `play()`, `stop()`'s top, `rememberStderr`, `notify`,
  `focusPlayer`, `statusSummary` and the `IpcHandler` keep their bodies.
- Harness: a `--restart-shell` mode that kills and relaunches the harness
  quickshell against the same scratch runtime dir while a fixture channel plays,
  so the reattach path is exercisable without the live session. `run.sh:72`'s
  `pkill -f "input-ipc-server=$SCRATCH/..."` reap already works on a detached
  grandchild and needs no change; add a second `pkill -f "player run"`-shaped
  line only if PA-0 changes the verb set.

### Lane PC - QA plan (M2-02-03, anytime)

Owns `docs/QA-PLAYER.md`, `tests/fixtures/qa-player/`. Touches no code. Matrix
per section 10, covering every row of section 7 plus S-03 and the 2 s reattach
bar.

### Frozen interface between PA and PB

PB codes against these names before PA lands, and rebases onto PA before its own
integration (the M2-01 SR10 rule). Changing any of them requires a doc revision,
not a lane decision.

1. **Helper verb argv and reply shapes** - section 4.3, verbatim.
2. **`Model` exports PB may call**: `playerStartArgv(socket, cacheDir, id, seq,
   scope, since, mpvArgs[])`, `playerStopArgv(socket, seq, from)`,
   `playerRestartArgv(...)`, `playerProbeArgv(socket, ownerPid)`,
   `playerOrphanCheckArgv(socket, ownerPid, graceSec)`,
   `parsePlayerProbe(text) -> {valid, running, responsive, pid, idle, stash,
   owner, seq}`, `parsePlayerEvent(line) -> {kind, ...}`,
   `endedVerdict(lastEndFile, userStopped, stopping) -> {notify, reason, kind}`,
   plus the unchanged `stopEscalation`, `healthTick`, `statusHealthy`,
   `parseHelperStatus`, `statusReason`, `notifyArgv`, `focusPlayerArgv`,
   `redactUrls`, `withFailed`, `withoutFailed`, `formatClock`, `splitMpvArgs`,
   `mpvWindowTitle`, `channelId`, `launchScope`, `zapRing`.
3. **`user-data` node names and schemas** - section 4.6, verbatim.
4. **The event lines PB must handle**: `start-file`, `end-file`, `log-message`,
   `property-change` for `idle-active`. Anything else is ignored.
5. **`playSeq` ownership**: Service.qml is the only issuer; the helper only
   compares and records.

### M2-02-04 integration, M2-02-05 QA pass

Unchanged from `PLAN-M2.md`. Docs edits (section 8) land with 04.

## 10. Test plan

### Unit, lane PA - `node tests/Model.test.js`

Existing player checks (lines 319-343, 439-458) stay; the `buildMpvArgv` block
is deliberately rewritten, not restored (see 2.3):

- `buildMpvArgv` contains `--idle=once`; contains **no** token matching
  `/:\/\//`; contains no `--user-agent=`, `--referrer=` or
  `--http-header-fields` even for a channel **with** headers; has no trailing
  `"--"`; every token after index 0 begins with `--` (the structural replacement
  for the retired `buildMpvArgv url after --` invariant, which SEC-06 also
  changes).
- `MPV_RESERVED` rejects all ten additions and their `--no-` forms;
  `--ytdl=yes` still survives `splitMpvArgs` and still sorts after `--ytdl=no`.
- `playerStartArgv`/`playerStopArgv`/`playerProbeArgv`: every element a separate
  argv member; user tokens as repeated `--mpv-arg`; `--seq` always present.
- `parsePlayerProbe`: valid body, unknown schema, truncated JSON, garbage - all
  return `valid:false` rather than throwing.
- `endedVerdict` truth table: error/eof/stop/quit/redirect x
  userStopped/stopping/neither, plus "no end-file at all" -> failure, plus the
  fail-open entry-id rule.
- `stopEscalation` and `healthTick` unchanged (7 + 4 existing checks).
- Shared vectors loaded from `tests/fixtures/player-argv.json`.

### Unit, lane PA - `python3 -m unittest discover -s tests`

The 23 existing `tests/test_mpv.py` cases must pass **unmodified** through every
step; if one needs editing, `cmd_play` or `header_properties` changed and
requirement 2 or 7 is at risk. New `tests/test_player.py`:

- `player start` on a clean directory: creates the dir 0700, takes the lock,
  spawns once (stub `mpv` on PATH recording its argv), polls, then sends
  title / force-media-title / three header properties / user-data / loadfile /
  user-data-with-entryId, **in that order**.
- The S-03 regression net: the recorded spawn argv contains no substring of the
  channel URL, no header value, no `--`; it does contain `--idle=once`,
  `--wayland-app-id=omarchy-iptv`, `--ytdl=no`, `--title=$>IPTV`.
- Idempotence: a live `FakeMpv` on the socket -> `spawned:false`, the stub mpv
  was never executed.
- Stale socket unlinked; a **regular file** at the socket path -> no unlink, no
  spawn, `socket_path_blocked` (preserving
  `test_regular_file_at_socket_path_is_left_alone`).
- Lock: a second concurrent `player start` reports `busy` and never spawns;
  unlinking the lock file mid-wait is detected by the inode re-check and retried;
  a `--seq` below the recorded one reports `superseded` and touches nothing.
- Spawn failure: a stub that never binds -> `no_socket`, and the stub's pid is
  dead afterwards (the helper reaped what it created). A missing binary ->
  `mpv_missing` via the errno pipe.
- Ladder with an injected clock: `quit` at 0, SIGTERM at ~2 s, SIGKILL at ~4 s,
  socket unlinked only after the final connect is refused; a pid whose
  `/proc` start time no longer matches is never signalled; `--from term` skips
  rung 1.
- Wedged player: a socket that accepts and never answers -> `responsive:false`,
  and `player start` ladders it down before spawning.
- `player probe` merges the `/proc` half and the socket half; `owner` is written
  only with `--owner-pid`; no raw `path` ever appears in the output.
- `orphan-check`: claim reassigned -> no-op; claim intact and owner alive ->
  stop; claim intact and owner dead -> no-op.
- Privacy sweep: run play -> failure -> stop against a channel whose URL embeds
  `user:pw@` and a token, then grep the whole runtime dir, every recorded argv
  and every emitted line for the password, the token and the path component.
  Must find nothing; `firstLoad.reason` must read `scheme://host` only.
- Parity: `MPV_RESERVED` parsed out of `Model.js` equals the python mirror;
  `stop_escalation()` matches the JS vectors in the shared fixture.

### Unit, lane PB - `QT_QPA_PLATFORM=offscreen qmltestrunner -input tests/Model.spec.qml`

The event router as a pure function over recorded mpv lines: a zap sequence
(`start-file`, `end-file{stop}`, `start-file`) raises no notification; an
`end-file{error}` names the channel from `entryOwners`; a `log-message` carrying
a credentialed URL yields a host-only tail; `playerUp`'s truth table over
(`connected`, `playerPending`).

Gate: `scripts/check.sh` exit 0 - `omarchy plugin validate`, qmllint 0 errors,
node, python, qmltestrunner. Node count should rise above today's 583 checks.

### Dev-harness scenarios (lane PB)

1. Full TC-PLAY-01..14 pass unchanged, plus TC-PLAY-08 **inverted**: headers
   must NOT appear in `ps -o args=`.
2. `--restart-shell` while a fixture channel plays: same mpv pid before and
   after, bar and `status` report the same channel, `pgrep -af --
   '--wayland-app-id=omarchy-iptv' | wc -l` is exactly 1.
3. Double start: two `player start` in a loop -> one window, one spawn.
4. Stale socket, regular file at the socket path, and cleared runtime dir.
5. SIGSTOP the harness mpv -> two failed `status` polls -> `player restart
   --from term` -> SIGKILL lands -> one relaunch.
6. The harness EXIT trap still reaps the detached player (`run.sh:72`).

### What only a live-shell pass can prove (M2-02-05, holds the display)

- **PLAYER-LIVE-01**: `omarchy restart shell` while playing - the stream does
  not glitch, the same mpv pid survives, the bar shows the channel again within
  2 s, `omarchy-shell io.github.rmcdavid.iptv status` reports the same
  `nowPlaying` including `launchedFrom`, and scroll-to-zap still rings the list
  it was launched from.
- **PLAYER-LIVE-02**: `pkill -KILL quickshell` while playing - same, and exactly
  one mpv survives.
- **PLAYER-LIVE-03 (S-03)**: `tr '\0' ' ' < /proc/$(pgrep -f
  wayland-app-id=omarchy-iptv)/cmdline` contains no `://` and no header value,
  on the **first** channel and after ten zaps; `ps aux | grep -c yt-dlp` stays 0
  across a deliberately dead channel.
- **PLAYER-LIVE-04**: disable the plugin from the settings panel while playing -
  the orphan-check stops the player within ~7 s (PO-2's acceptance).
- **PLAYER-LIVE-05**: SIGSTOP mpv, press stop - the window is gone within ~4.5 s,
  nothing survives, the socket is unlinked, `hyprctl clients -j | jq
  '[.[]|select(.class=="omarchy-iptv")]|length'` is 0.
- **PLAYER-LIVE-06**: hammer Enter on two channels during a cold start - exactly
  one window at every instant.
- **PLAYER-LIVE-07**: log out while playing - `pgrep -f omarchy-iptv/mpv.sock`
  empty on the next login.
- **PLAYER-LIVE-08**: the real notification path (the harness has no notification
  daemon of its own): a dead channel raises exactly one toast naming the right
  channel with a host-only reason, and the guide marks the row.
- **PLAYER-LIVE-09 (migration)**: upgrade over a v0.2.0 player that survived a
  SIGKILLed shell -> the unknown player is stopped, one Enter restores service.

Note for sequencing: the live pass will run on a shell that still carries the
two open P1 defects D-LIVE-20 and D-LIVE-21 (settings propagation, `reconcile()`
never runs). They touch `persistActive`, not the player path, so they should not
conflict - but they will make triage noisier, and this milestone is best
sequenced after they land.

## 11. Open questions for the product owner

1. **`--idle=once` vs `--idle=yes`.** `once` is what `SECURITY-REVIEW.md:36`
   prescribes and it preserves today's UX exactly (the window vanishes on a
   stream failure and on a clean end), deletes the whole idle-timer apparatus,
   and leaves a working degraded mode if the QML socket proves unusable. `yes`
   would keep the window alive for a few seconds so an immediate re-zap after a
   dead channel is instant, at the cost of a lingering empty window, a new
   idle-quit rule and no fallback. **Recommendation: `once`**, gated on probe
   PA-0(a) confirming a `loadfile ... replace` does not trigger the exit; if it
   does, we fall back to `yes` plus an explicit quit-on-idle rule and this
   question reopens.
2. **Teardown when the plugin is disabled or removed** (requirement 4, weakened).
   Today `~Process()` guarantees the player dies. After detachment the guarantee
   becomes the best-effort owner-claim orphan-check of 4.14, plus a documented
   `omarchy-iptv player stop`. The alternative - keeping a supervisor purely to
   own this - costs an entire process class. **Recommendation: accept
   best-effort**, with PLAYER-LIVE-04 as the acceptance gate and the manual verb
   in the README's Uninstall section.
3. **Failures that happen while no shell is attached** (requirement 6, weakened).
   No process on this machine can raise a toast while the shell is down -
   `org.freedesktop.Notifications` is owned by quickshell itself and is not
   D-Bus activatable. Options: (a) mark the channel failed in the guide silently
   on reattach, using `state.json.session` for the name, no toast; (b) raise a
   deferred toast for an event that may be minutes old. **Recommendation: (a)** -
   a stale toast for something the user has already seen stop is noise, and the
   red guide row carries the information.
4. **Clean EOF.** Today a clean end exits 0 and is silent
   (`ARCHITECTURE.md` decision 12, `Service.qml:948`). Under the new router
   `end-file{reason:"eof"}` maps to the same silence. A provider rotating a
   source mid-session therefore just stops with no explanation.
   **Recommendation: keep silent** (zero behaviour change); if the PO wants a
   toast it needs its own copy, because "did not play" is wrong for a channel
   that played for an hour.
5. **Should `--ytdl` join `MPV_RESERVED`?** `--ytdl=yes` re-creates an
   S-03-class exposure in a process we never launch (`yt-dlp ... -- <full URL>`
   on its own argv, on every failed open). `Model.js:1270-1273` documents the
   override as a deliberate escape hatch for non-direct URLs.
   **Recommendation: keep it unreserved and add one README sentence naming the
   cost.** The ten additions in 4.12 land regardless.
6. **Diagnostics for a launch that never binds a socket.** `/dev/null` stdio
   means an mpv that dies parsing a bad user `mpvArg` produces no text anywhere
   (no socket, so no `request_log_messages`), and the user sees a generic
   "player did not start". Recovering it would require either a temporary
   0600 log file for the launch window only, or capturing the grandchild's
   stderr into a pipe the helper drains and redacts for the first 5 s.
   **Recommendation: the pipe** - it costs ~20 lines in `spawn_detached`, writes
   nothing to disk, and reuses `redact_urls()`; but it is the one piece of
   section 4 I would cut first if PA runs long.
7. **STATUS.md board row number.** `M2-02` at line 89 is taken by "Multiple
   playlists - merged into M2-01", and the deferral decision needs superseding
   rather than editing. **Recommendation: a new `M2-09` row plus a new
   decision-log entry**, with `PLAN-M2.md`'s existing `M2-02-00..05` task ids
   left alone.

## 12. Product owner acceptance (2026-09-14)

Accepted as the design for M2-02. The hybrid is the right call: four
independent designs each carried fatal flaws found by adversarial review, and
grafting the survivors with the six named defect fixes is exactly what the
exercise was for. Build to this document.

Rulings on section 11, in order. These are binding; a lane that wants to
deviate raises a numbered decision request rather than deciding locally.

| # | Ruling |
|---|---|
| PO-1 | `--idle=once`. It is what the security review prescribed, it preserves today's behavior exactly, it deletes the idle-timer apparatus, and it leaves a working degraded mode if the socket observer proves unusable. Gate it on probe PA-0(a) as proposed. If a `loadfile ... replace` does trigger the exit, stop and raise the fallback as a decision request rather than switching to `--idle=yes` unilaterally. |
| PO-2 | Accept best-effort teardown. Do NOT stop the player when the service object is destroyed: that path cannot distinguish a shell restart from a plugin removal, and stopping there would defeat the entire feature. The owner-claim orphan check at service start, plus a documented `omarchy-iptv player stop` in the README's uninstall section, is the contract. PLAYER-LIVE-04 is the acceptance gate. |
| PO-3 | Option (a): mark the channel failed silently on reattach and show it in the guide. A toast for something that stopped minutes ago, possibly on another login, is noise and would arrive without context. The red row carries the information, and the guide is where the user goes next anyway. |
| PO-4 | Keep a clean end silent. Zero behavior change. I am not adding a toast for a channel that played successfully and ended; if usage shows people are confused by a window vanishing, that is a separate request with its own copy, because "did not play" is wrong for a channel that played for an hour. |
| PO-5 | Keep `--ytdl` unreserved and add the README sentence naming the cost. It is an opt-in escape hatch the user has to type deliberately, it is the documented way to play non-direct URLs, and reserving it would break a legitimate use to prevent a self-inflicted exposure. The ten reserved-list additions in 4.12 land regardless. |
| PO-6 | Implement the stderr pipe for the launch window. It is about twenty lines, writes nothing to disk, and reuses the existing redaction. The alternative is that a bad user option produces a generic "player did not start" with no text anywhere, which is the worst kind of support problem. If lane PA runs long, this is the last thing to cut, not the first. |
| PO-7 | `M2-02` means the detached player everywhere. `PRODUCT.md` and `PLAN-M2.md` already use it that way. The stale `M2-02 Multiple playlists` row in `STATUS.md` is retired as superseded by `M2-01`, since the source history IS the multi-playlist model. Do not introduce an `M2-09`. |

Two additions of my own, neither optional:

- The two weakened requirements, 4 and 6, must be stated in the README as
  known limitations in the same plain language used for the current ones, and
  in the release notes. A weakening that only exists in an architecture
  document is a weakening the user discovers by surprise.
- The harness lesson from D-LIVE-20 applies here with double force. This
  feature's whole point is behavior across a shell restart, which no fake can
  simulate. Every acceptance gate for M2-02 is a live-shell gate, and any
  harness scenario added for it must be shown to fail against the pre-fix code
  before it counts as evidence.

## 13. Amendment after gate PB-0 (product owner, 2026-09-14)

Gate PB-0 ran before lane PB touched anything. The verdict is in
`docs/SPIKE-QUICKSHELL-SOCKET.md`: the socket observer is viable, the
degraded-mode fallback is not needed, and three assumptions in section 4 were
confirmed against real mpv. But the spike disproved the implementation shape
this document prescribed, so two corrections are binding on lane PB.

1. Section 9, lane PB, the bullet reading "Add `Socket { id: playerSocket }`
   plus `SplitParser` plus `Connections`" is WITHDRAWN. A Quickshell `Socket`
   whose connect attempt fails is dead permanently: no property write revives
   it, and re-arming one that is already connected silently arms a hidden
   zero-delay auto-reconnect that bricks the object the moment the peer dies.
   The prescribed single declarative object is therefore the one shape that
   cannot reattach, which is the entire point of the feature. Build it as a
   `Component` with a fresh object constructed per attempt, driven by the
   retry timer, exactly as caveat C1 and the reference snippet in section 6 of
   the spike specify.
2. Section 4.7's `playerUp` definition gains the null guard of caveat C3,
   because the socket handle is now null between attempts.

Lane PB must read the spike document in full before writing any socket code
and honor all ten caveats, in particular capping the retry burst: an
unbounded loop writes roughly fourteen thousand warnings an hour to the
journal.

No ruling PO-1 through PO-7 changes. PO-1 is incidentally strengthened, since
real mpv under `--idle=once` exited one millisecond after an error end-file,
which satisfies half of gate PA-0 in passing. The other half, whether a
replace-load during playback avoids exiting, remains lane PA's to prove.

This is the second time in this milestone that a probe overturned a confident
design detail, after the settings-echo defect. The standing rule holds: for
this feature, an assumption about host behavior is not evidence until
something has run.
