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
| `watch-later/`, `shader-cache/` | 0700, 0600 files | `ensure_player_dirs()` before the spawn | mpv's own resume records (PO-11) and its shader/ICC caches (D-PLY-10, CL2). Both ephemeral: named here so they do not land in `$HOME` and `$XDG_CACHE_HOME/mpv/` |

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
player tracks  --socket S [--audio ID|no] [--sub ID|no] [--ipc-timeout 2.0]
```

**[Amended 2026-10-28, D-PLY-35: the service passes NONE of the four timeout
flags on any verb (Model.playerStartArgv, playerRestartArgv, playerProbeArgv;
pinned by a node check), so the defaults above are the bounds every shell run
waits out, and the shell's watchdog over the player slot is derived from them
(4.4's bracket). Two more bounds sit inside `start` and `restart` and were
literals until this day: the spawn's wait for the grandchild's pid,
`SPAWN_PID_TIMEOUT` (2 s), and the one connect `socket_is_dead` makes before a
settle unlinks, `SETTLE_CONNECT_TIMEOUT` (0.2 s); both are named now, values
unchanged. Every one of these numbers, with `LOCK_POLL_S`, `STOP_SETTLE_MS`,
`SETTLE_LOCK_TIMEOUT` and the ladder's two graces, is pinned by
tests/fixtures/player-bounds.json, which the python side reads off the helper
by name (tests/test_player_bounds.py, which also observes the two former
literals being used) and the model mirrors (Model.PLAYER_BOUNDS).]**

`player tracks` (M3-02) lists mpv's `track-list` and, given a selection,
sets `aid` / `sid` FIRST and lists after, so one reply carries the player's
answer to the request (PLAN-M3 decision 5). The list is a sink (rule 5, dev
branch): `external-filename` is a path or URL and `title` is whoever muxed
the stream, so the reply is a whitelist of fields -- `id`, `type`,
`selected`, `lang`, `title`, `codec`, `default`, `forced`, `external` -- with
`title` through `redact_urls`, and `external-filename` never emitted.
Side-effect-free like `pause`: no player, no spawn, `running: false`.

User `mpvArgs` tokens travel as **repeated `--mpv-arg TOKEN`**
(`action="append"`), never as a positional list - that sidesteps argparse
consuming an option-looking token entirely, and keeps every element a distinct
argv member with no joining.

**[Amended 2026-10-29, lane-p2a (D-SINK-47, D-SINK-48, D-SINK-50).** The
spellings above are still the CLI a human types, and the helper still takes
every one of them from its argv. When the SHELL starts it, none of the values
that a local account could use is on that argv any more: `/proc/<pid>/cmdline`
is mode 0444 on a proc mounted without `hidepid`, and it carried `--cache-dir
<cache>/sources/<key>` and the cache verbs' `--key`, `--keep` and `--active`
(every key made before this release is fnv1a32 of the credentialed playlist
URL, a 32-bit check on a guessed password), `--id` (a `u:` id hashes a stream
URL), `--scope` (a provider's group name) and each `--mpv-arg` (where a proxy
password goes). Every helper spawn goes through `Service.runHelper`, which
assigns the command and the environment `Model.helperSpawn` makes, together,
immediately before the run: those options, with their values, leave the argv
for a JSON list in `OMARCHY_IPTV_ARGS`, and `--args-from-env` stands in their
place. The helper's `helper_arguments` reads the list once, before argparse,
appends it after the public argv, and takes the variable out of its own
environment, so the player it forks never inherits it; a flag with no list, or
a list that is not strings, is `bad_arguments`, exit 2, and no verb runs -- a
`failed mark` that lost its `--cache-dir` must not write the default cache.
The verbs, `--socket`, `--seq`, `--since`, `--owner-pid`, `--from`, `--state-dir`
and the timeouts stay on the argv, where `pgrep -a` and the harness find them.
The environment is the route D-SINK-8 moved the URL to: closed to other uids
from exec, and to this uid from the stub's shield on. And every spawn is
`python3 -I` (`Model.helperArgv`, the one builder), so the session's
`PYTHONPATH`, user-site `.pth` files and `sitecustomize` no longer run before
that shield -- measured: a `ctypes.py` on `PYTHONPATH` ran with the URL in
the environment and switched the shield off, before `-I`, and does not run
after. The shared fixture `tests/fixtures/helper-args.json` holds the two
halves together.]**

Reply shapes (all `{"ok":bool,"kind":...}` per decision 10, all URL-free):

```
player.start  {"ok":true,"kind":"player.start","spawned":bool,"pid":N,
               "id":"t:bbc1.uk","name":"BBC One HD","entryId":2,"seq":41,
               "firstLoad":{"state":"playing"|"failed"|"unknown",
                            "reason":"<redacted, host only>",
                            "ended":"end-file"|"closed",       <- "failed" only
                            "fileError":"<mpv's file_error>"},  <- "end-file" only
               "warnings":["dropped mpvArg --log-file"]}
player.stop   {"ok":true,"kind":"player.stop","running":false,
               "rung":""|"quit"|"term"|"kill","pid":N|null}
player.probe  {"ok":true,"kind":"player.probe","running":bool,"responsive":bool,
               "pid":N|null,"idle":bool|null,"mpvVersion":"...",
               "stash":{...}|null,"owner":{...}|null,"seq":N,"claimed":bool}
error         {"ok":false,"kind":"player.<verb>","error":{"code":C,"message":M}}
```

**[Amended 2026-10-28, D-PLY-36: `firstLoad` gains two members, additive
(a shell from before ignores them). A `failed` says which ending the window
saw: `ended` is `end-file` when mpv sent an `end-file` error for the start's
own entry, with mpv's `file_error` beside it in `fileError` (redacted and
cut like `reason`), or `closed` when mpv closed the connection with no such
`end-file` -- under `--idle=once` that is the player dying (a crash, a
kill, a VO abort). `playing` and `unknown` carry neither. The shell's
`Model.deathReport` marks the channel only for the first (4.8, as amended);
the shared fixture `tests/fixtures/player-endings.json` holds the replies,
run by both suites.]**

Error codes, exhaustive: `busy`, `superseded`, `socket_path_blocked`,
`mpv_missing`, `spawn_failed`, `no_socket`, `not_running`, `ipc_error`,
`no_cache`, `unknown_channel`, `unsupported_scheme`.
**[Amended 2026-10-27, D-PLY-30: `start`, `restart` and `stop` make the
runtime folder (step 3) and open the lock file (4.2) before they touch a
player (`start` and `restart` resolve the channel from the cache first, so
`no_cache` and `unknown_channel` still come before either), and a failure
of either is now a refusal in the shape above
(`kind: player.<verb>`). `folder_unusable` is R25c's (D-SRC-32): the runtime
folder, or one above it, is a symbolic link whose target is missing or is not
a folder, or something that is not a folder is at its path; the message is
R25c's sentence and names the path. `runtime_unwritable` is any other
failure: the folder could not be made (a parent this user cannot write, a
full or read-only filesystem), `could not make the player's runtime folder
(<error>)`, or the lock file could not be opened (a folder at its name, a
file this user may not write), `could not open the player's lock file
(<error>)`. Its message names no path. Until then a folder that could not
be made and a lock file that could not be opened reached the helper's
catch-all, `internal` with the exception's text and the path, and a link to
nothing reached main()'s R25c answer, `folder_unusable` with R25c's
sentence, both in a reply of `kind: player`. `Model.statusReason` gives the user `A folder the plugin uses
is a broken link or not a folder` and `Could not write the player's runtime
folder`, in the "did not play" notification. `probe` takes no lock of its
own, and it still answers over a lock it cannot open, as it did before. The
list above was already incomplete before this bracket: `start` and `restart`
also answer `tls_unverified` (D-SINK-16), any verb can answer the helper's
catch-all `internal`, and the later `pause` and `tracks` verbs answer
`pause_refused`, `track_refused` and `bad_track`.]**
**[Amended 2026-10-28, D-PLY-34: no code is added or retired; two keep
their code and change their words. `busy` here is the player LOCK (another
`start`, `restart` or `stop` holds it past `--lock-timeout`, or the lock
file kept being replaced), and `too_large`, which a player verb answers
only from main()'s MemoryError (reply `kind: player`), is this helper's own
memory. `Model.statusReason` read both in the fetch verbs' words, `Another
fetch is running` and `Source too large`, on the "Could not start playback"
notification and in `lastError`. It now chooses by the reply's kind: for
`player`, `player.<verb>`, `play`, `stop`, `status` and `seek` they read
`The player is busy` (the guide's pause line's own words) and `Helper ran
out of memory`; the playlist and EPG verbs keep theirs.]**
**[Amended 2026-10-28, D-PLY-31: no code is added. `spawn_failed` now also
covers the spawn's OWN failures before the grandchild exists: one of its
three pipes refused (EMFILE, ENFILE) or its first fork refused (EAGAIN
under RLIMIT_NPROC, ENOMEM) answers `could not start mpv: <error's words>`
-- the message shape the grandchild's own fork, setsid and exec failures
already had over the errno pipe -- with whatever it had opened closed first.
Until then those reached main()'s catch-all as `internal` (with the
exception's text) and read "Helper failed unexpectedly". The user reads
`Could not start mpv` for every `spawn_failed`, and `Something else is at
the player's socket path` for `socket_path_blocked`, where both used to
reach the "Could not start playback" notification as the helper's lowercase
message. `spawn_failed` is also the `clipboard` verb's code for a wl-paste
that cannot be started; that reply carries no `error` object and the shell
drops every clipboard failure without a word, so mpv's sentence is chosen
only for a player verb's kind. Both codes are local (`PROBE_LOCAL_REFUSALS`,
D-PLY-30's reading; `Model.playerStartFailure` already read them so).]**

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
    **[Amended 2026-10-28, D-PLY-36: with `ended` and, for an `end-file`,
    `fileError` (4.3).]**
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

**[Amended 2026-10-28, D-PLY-35: the bounds of steps 4 to 11 add up past
the one 12 s `playerWatchdog` step 2 starts -- the lock's 6 s, the spawn's 5 s
and the first-load window's 3 s are 14 s before any IPC -- and the watchdog
TERMs the helper. Measured on dev da0000d, headless and in a nested cage on a
private bus (QA-RESULTS "D-PLY-35"): with the lock held 5.8 s by a stand-in, the
spawn slowed 4 s and the stream's first byte 6 s late, the start was TERMed at
12.0 s, a second after its loadfile (step 9e); the player it had spawned
played the channel on, with the shell's observer off, `nowPlaying` null, the
session record retired and a "Could not start playback / Helper produced no
output" card up. The next play adopted that player (step 5), so nothing
multiplied; nothing observed it in between either. Two changes.
(1) The watchdog's interval is the bound of the verb in flight,
`Model.playerWatchdogMs(verb)`: the verb's longest path through the helper's
code with every wait it survives at its full bound and the one wait that ends
it, plus a 5 s margin for the interpreter, the cache read and the /proc scans
(a whole `player probe` with no player measured 259-306 ms, a start that
resolves its id in a 10,000-channel cache 356-390 ms, at load 3.2). Start
43.25 s (the lock, a found player that does not answer and its whole ladder,
the spawn's pipes, its bind window and the last probe of it, then the larger of
the `no_socket` tail and one caught request plus the first-load window),
restart 46.45 s (the lock, its ladder from term and a settle, then all of a
start's path after its lock: a player that ladder could not end -- a process in
uninterruptible sleep acts on neither signal -- is found by adopt_or_spawn,
probed and laddered again from quit; the first version said 35.45 s and left
that path out, found by the recheck), probe 11 s (its connect and request and
one more request). model/player.mjs carries the arithmetic and
tests/fixtures/player-bounds.json its result; tests/test_player_bounds.py walks
the shipping verbs' long paths under a virtual clock, each wait at the bound
the code itself sets, and holds each inside its watchdog less the margin
(start 38.07 s, restart 41.12 s, probe 6 s). Not summed: every other IPC request at its 2 s bound -- a request
that reaches its bound raises and ends the verb, so only an mpv answering
each of a start's twenty-odd requests just inside 2 s could run past it.
(2) That residual, and anything else that runs past, is recovered rather than
bounded: step 12 reads a start or restart the watchdog stopped (an empty reply
with the watchdog's flag) as `helper_timeout` -- the S-05 status the fetch
slots already synthesise -- and not as a refusal. With an intent still
standing the shell tells nothing yet, keeps `nowPlaying`, arms the socket hunt
and runs the reattach probe (4.5). A player carrying the stash is adopted,
the start's relaunch and retries settled as an ok reply settles them; if its
stash names another channel the intent is put back and sent again (ruling
CL5). Anything else -- no player, one that does not answer, one it cannot
identify or make verify -- ends the start as the local failure it would have
answered, `Could not start playback` with "Helper timed out", marking nothing
(D-PLY-32). A probe that is stale (a newer play went out) or a socket EOF that
already told a death drops the stopped start untold.]**

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
`force-media-title` while `idle-active` is true). **Amended by D-SINK-16
(4.5.1):** the call adoption makes also reads two TLS properties and, when
they do not already read safe, writes them and reads them back. That write is
UNCONDITIONAL: `player probe` calls `migrate_tls` on every run, with no flag to
gate it. An earlier draft of this paragraph said it was opt-in on the call,
"the same shape as the owner claim, so a bare `player probe` run by a human
stays a read", and that was never true of the shipped helper. It is kept
unconditional deliberately -- any probe that finds an unverified player should
leave it verified, and a flag would mean a probe that found the exposure and
walked past it -- so the honest statement is the one with the consequence in
it: `player probe` is no longer purely a read, and a human running it against
their own player will change that player's TLS setting. Corrected 2026-10-07
by the review of the lane that wrote it.

`applyProbe()` in Service.qml, by case:

| Probe result | Behaviour |
|---|---|
| `running:false` | Nothing playing. `playerWanted = false` (the retry timer stops; no idle polling). If `state.json.session` names a channel, mark it in `failedAt` and clear `session` (PO-3) |
| `running:true, responsive:true, stash.playing:true, idle:false` | Restore `nowPlaying` from the stash; `playerPending = true` until the socket connects; arm `healthTimer`; queue `reconcileNowPlaying()` for `channelsLoaded`. **4.5.1 runs on this row before any of it**, and its read-back can turn this row into a stop |
| `running:true, responsive:true, stash absent or `playing:false`, or `idle:true`` | Under `--idle=once` an idle player exists only between spawn and first `loadfile`, so this is either a racing start or a foreign/pre-M2-02 player. Re-probe once after 500 ms; still ambiguous -> `player stop`, show idle |
| `running:true, responsive:false` | Wedged. `player stop` (ladder from rung 1, pid already known), show idle |

`nowPlaying` is restored **directly from the stash**, before `channelIndex`
exists - the stash carries `name`, `group` and `launchedFrom`, so the bar and
the guide are correct immediately. `reconcileNowPlaying()` then runs once the
channels cache loads, resolves `id` against `channelIndex`, and fixes the zap
ring; a playlist that changed while the shell was down degrades to name-only
rather than resolving to the wrong channel. This is the fix for "the reattach
resolves against an empty index".

#### 4.5.1 TLS on a player this shell did not launch (D-SINK-16)

Every layer in 4.15 as it shipped is a layer on the argv of a player this
shell LAUNCHES, and argv is fixed at exec. Adoption is the one path in this
document that meets a player whose argv is older than the installed plugin,
and it is not a passive path. Once adopted, that process is driven like any
other: `apply_channel` sends it the three provider header properties and a
credentialed `https` URL on every channel change (4.11), and the stream it
already has open keeps requesting -- a segmented live stream re-requests with
the credentials the URL carries on every segment, which is how HTTP and HLS
work rather than something this project has observed. So a player launched by
0.12.1 and adopted by 0.13.0 did not merely keep a stale option: **the plugin
went on feeding it.** Raised by the marketplace maintainer against the SHIPPED
0.13.0 (5d527d7), omacom/omarchy-plugin-marketplace#10389, on the verification
request for that same snapshot, hours after it was published. This project had
the first half of it as D-PLY-25 and wrote it up as stale state a user could
fix by restarting the player; that filing is superseded, and how it came to be
undersold is in the `ARCHITECTURE.md` register rather than here.

**Measured by the lead on 2026-10-07, before any lane was briefed.** This
section does not restate those runs as its own: they are the D-SINK-16 row in
`docs/STATUS.md` and the write-up in `docs/QA-RESULTS.md`. What they
establish, over a real IPC socket against a local server with a self-signed
certificate: `tls-verify` is READABLE over the socket and reads False on a
player launched the way 0.12.1 launched one, and a `loadfile` of the attacker
URL on that player put the GET in the attacker's log; `set_property tls-verify
True` answers success, reads back True, and the next `loadfile` of that same
URL fetched NOTHING -- attacker GETs 1 before and 0 after, on the SAME
process, with a positive control (a plain-`http` URL from a second local
server, fetched and played) proving the migrated player is not simply broken.
`stream-lavf-o` sets and clears the same way. Runtime migration therefore
works, and this design rests on that measurement and not on an argument.

**What is read.** On the connection the adoption call already holds -- the one
that reads `idle-active`, `mpv-version` and the two `user-data` nodes --
`tls-verify` and `stream-lavf-o`, and nothing else is added to that read set.
`path` is still never read (4.5).

**What is set, and only where the read says it is needed.** `tls-verify` to
true when it does not already read true; `stream-lavf-o` to the empty map when
it reads non-empty. The second is wholesale rather than selective on purpose:
D-SINK-15's finding is that FFmpeg reaches the same TLS decision under its own
option names and this project has not enumerated them, so "strip the keys we
recognise" would be that same overclaim a second time. Clearing it leaves the
adopted player holding what 0.13.0 would have launched it with anyway, because
the token that carries those keys has been refused by the shipping filter
since 0.13.0 (4.12).

**What is read back, and why the verdict is the read-back's.** Both
properties, after the set, on the same connection. The decision is never the
set's own `success`: "we asked" is not "it is so", which is engineering rule
14 one property over, and it is exactly the shape of mistake the first fix
made by trusting a token's presence. A connection that dies anywhere in the
sequence is a failure, not a silence to be read as consent.

**Rule 5 at this sink.** Neither value is echoed into the shell, the console,
a tooltip or a notification. `tls-verify` is a boolean. `stream-lavf-o` is
whatever a pre-update user put on their own `mpvArgs`, which is a place a
credential can sit (a `headers=` entry, say), so the reply carries WHETHER it
is empty and not what is in it, and any text about it crosses into QML through
`redact_urls` like every other helper string. Reasoning, not a measurement
that a credential has ever been in there.

| Read-back | Behaviour |
|---|---|
| Already safe: `tls-verify` true, `stream-lavf-o` empty | Adopt exactly as the 4.5 table says. Nothing is set, nothing is reloaded, no rebuffer. Every player launched by 0.13.0 or later lands here, so the cost below is paid once, on the upgrade that crosses this version |
| Made safe, and the read-back confirms it | Adopt, then re-establish the current channel before the shell sends that process anything else. The stash names it (`id`, `launchedFrom`, `since`), `Model.zapArgs` composes the `play`, and `player_target` resolves the id against `channels.json` inside the helper, so the reload does not wait for the shell's own cache. One visible rebuffer |
| NOT made safe: a refusal, a read-back that still reads unsafe, or a connection that died mid-sequence | The player is STOPPED, by the 4.9 ladder, and the shell shows idle: the `stopForeignPlayer()` path, which is already what a wedged or unidentifiable player gets. Loading is the act of handing over the URL and the headers, so a process that could not be secured is not loaded into, it is ended. The channel is NOT marked failed -- PO-3's mark is for a channel that died unattended, and this one was stopped by us |
| Made safe, but the channel cannot be re-established: `unknown_channel`, because the playlist no longer carries the stash's id | Stopped, for the reason in the row above -- the connection still open is the unverified one, and leaving it running is the thing the finding is about. **This row is this section's reading of the ruling rather than the ruling itself**, which covered the properties and not a reload that cannot be issued; it is raised as a decision request instead of being treated as settled |

**The other adoption, and why it needs nothing of its own.** `player start` is
idempotent: a live answering player is adopted and ZAPPED rather than
duplicated (requirement 1). That path ends in a `loadfile`, so layer 6 covers
it whole -- the properties are asserted on the process before the load and the
load is refused if they cannot be made safe. What this section is for is the
adoption that does NOT load: a probe that picks up a player and leaves it
playing what it was already playing, which is the common case on an upgrade
and the one the first fix missed.

**Why a reload, and this is the sentence to read twice.** Setting the property
governs the NEXT `loadfile`. Whether a stream ALREADY OPEN picks the change up
for its ongoing fetches is **UNMEASURED**: the probe behind this design used a
short file, not a segmented live stream, and nothing in this project has
observed it. The reload exists BECAUSE that is unmeasured -- not because it
was measured not to happen, and the difference is the whole reason this
paragraph is here. There is a second reason that does not depend on the
measurement either way: the connection in hand was established without anyone
checking the peer, and there is no verification that can be applied to it
after the fact. So the reload is not an optimisation for a later reader who
finds the `set_property` sufficient to tidy away. It may be dropped on the
strength of a measurement against a real segmented live stream and on nothing
else, and if that measurement is ever taken it belongs in this section.

**Ordering, and the one gap it leaves.** The migration and its read-back
happen on the adoption call, before the shell writes anything to that process;
the shell's first write to an adopted player is the re-establish, and it is
issued only on a clean read-back. The 4.10 sequence can supersede the adoption
reply -- a play the user issued while the probe was in flight is the newer
word and `applyProbe` returns early -- and that branch is safe for a different
reason: the user's own `play` goes through `apply_channel`, which is 4.15's
layer 6 and refuses to load into a player it cannot make safe. What the
superseded branch does NOT do is stop a player that could not be secured. It
is left running its old stream, refused any further load, until the user stops
it or the failure path ends it. Named here rather than papered over, and
raised with the row above.

**The cost, which is not nothing.** One rebuffer, visible, once, on the
upgrade that crosses this version, on the player that happened to be running.
A player that cannot be made safe is stopped, which is playback the user did
not ask to lose. And for a provider whose certificate needs `--tls-ca-file`,
whose running player was launched without it, the re-established load fails
verification and what the user sees is the channel stopping, through 4.8's
failure path -- 4.15's already-accepted cost arriving at a different moment,
not a new one. **UNVERIFIED BY ME:** the lane that wrote this section holds no
display and has run no player; everything outside the measurement paragraph is
specification, and the live gate for it is QA's.

**What this deliberately does not do.** It does not relaunch the adopted
player: relaunching is the other option D-PLY-25 left open and it would
destroy the window whose survival is the entire point of M2-02 (sections 1 and
2), so the properties are migrated in place instead. It does not migrate any
other launch option, `--tls-ca-file` included, which stays a user argument
that takes effect on the next launch. It does not touch `--demuxer-lavf-o`,
measured by D-SINK-15 as NOT a bypass and therefore neither reserved nor
cleared here.

**[2026-10-29, D-SINK-43 and D-SINK-44: the paragraph above is wrong in two
places, and this bracket is what is true now.]** `--demuxer-lavf-o` IS a
bypass for HLS and DASH -- D-SINK-15 measured it on a direct stream, the one
shape where it is not -- so the adoption now reads it too, and it is not the
only addition. The readings are THREE, and the third is a sum of counts:
the TLS entries of `demuxer-lavf-o` (removed by key, so the user's
`live_start_index` stays), `load-auto-profiles` not reading off (set to `no`
at runtime, which UNLOADS auto_profiles.lua -- measured 3 of 3 on a pre-pin
player: the profile-cond profile that had turned verification off stopped
applying), and the user's `[protocol.*]` / `[extension.*]` profiles that
could set, at file load and so after the read-back, an option this player
does not have set from the command line. That last one no migration can
reach -- nothing over IPC makes an option command-line-set -- so a pre-pin
player whose mpv.conf holds such a profile reads unsafe and is STOPPED by
the table above (measured: such a player read back safe under the old
readings and then fetched from the attacker; under the new ones the load is
refused, 0 GETs). Every player launched by 0.15.0 or earlier now reads
"migrated" on the first probe after the upgrade (its `load-auto-profiles` is
mpv's `auto`), so the one rebuffer of the second row is paid once by every
such player, not only by a pre-0.13.0 one. The probe and the adoption branch
of `player start` also carry the pins that are not about the TLS peer, best
effort (`pin_adopted_player`, 4.12.1). Section 4.12.1 has the measurements.

**[2026-10-29, lane-p1b: two more readings make an adopted player unsafe, and
the adoption carries four more pins.]** (1) The per-file profiles the third
reading counts are now those that touch ANY option the pin block holds, not
only the TLS ones (the lead's decision on rc-mpvpin's recheck, which measured
a `[protocol.http]` profile with `save-watch-history`, `load-unsafe-playlists`
or `load-select` undoing `pin_adopted_player`'s runtime writes at every load):
such a pre-pin player is STOPPED rather than migrated (`tls-scenario.sh
--windowless` W18: refused, and no file outside the runtime folder holds the
credential; on sec-int 6c79a9a it was loaded and the watch history held the
URL). (2) D-SINK-60: a player whose `reset-on-next-file` holds any entry is
not safe, and nothing can make it so. mpv BACKS UP the options that list names
when a file STARTS and restores them when that file ENDS -- inside the next
`loadfile`, after every read-back -- so every migration made while the
current file plays is undone at the next load, the list itself included.
Measured on mpv 0.41.0, windowless: with `all` and no pin block, `tls-verify`
set true during file A read true and the load of a self-signed B read false
and fetched from it; and on a player started by v0.15.0's argv with a
`--demuxer-lavf-o=tls_verify=0` and `reset-on-next-file=all` in its mpv.conf
(W17), the first version of this fix removed the key AND emptied the list,
read back safe, and the attacker still received the next HLS segment request.
So the list is READ with the TLS pins (`read_tls_state`) and never written:
a non-empty list counts one, and the player is stopped. (3) The adoption now
also sets `drag-and-drop` off, binds `ctrl+v` to `ignore`, sets the OSC's
title middle-click to `ignore` (one key of `script-opts`, the user's others
kept) and puts the three GLOBAL header properties at values that belong to
no provider, because the helper before this one set the channel's headers
there (4.11). And `secure_player` appends the demuxer's protocol whitelist
(D-SINK-55, 4.12.1) to a player that lacks it; the read-back requires it.

**[2026-10-29, lane-p1c: and the format list, and two more pins.]**
`secure_player` appends the demuxer's format list (D-SINK-62, 4.12.2) the same
way, and the read-back requires it exactly; it removes a `seg_format_options`
key (D-SINK-64), which the read-back counts. `pin_adopted_player` sets
`prefetch-playlist` off (D-SINK-63) and `load-console` off, which unloads the
console script at runtime (D-SINK-61; mpv answered both flags as booleans
over IPC, measured). Every player started by sec-int 124589e or earlier lacks
the format list, so it reads "migrated" on the first probe after the update
and pays the one rebuffer of the second row.

**Where the flag and the field names are fixed.** The owner claim is the
precedent for an opt-in write on a verb documented as a read
(`Model.playerProbeArgv`'s own comment: "Omitted, the probe is read-only"),
and the migration follows it, which is what keeps `player probe` from a
terminal a read. The flag's spelling and the reply's field names are the code
lane's to choose, and 4.3's frozen-interface table records them when they
land. What this section fixes is the behaviour, which is the part a renamed
field cannot invalidate.

**[2026-10-29, lane-p2a, D-SINK-68: measured, not a bypass on this FFmpeg.]**
The read-back never reads `demuxer-lavf-propagate-opts`, and the adoption
never sets it, so a pre-pin player whose PLAIN mpv.conf line says
`demuxer-lavf-propagate-opts=no` keeps it -- and with it off, the demuxer's
`tls_verify=1` and the user's `--tls-ca-file` no longer reach an HLS segment
open. Measured windowless (`tls-scenario.sh --windowless` W28): a player
started by v0.15.0's argv with that line, adopted and loaded by this tree, an
HLS master on the CA-signed provider whose segment is on a self-signed
attacker -- the attacker got NOTHING, because FFmpeg n9.0.1's own TLS options
default to verifying (`ffmpeg -h protocol=tls`: `tls_verify` default true); the
control, the pre-pin tree's own load with `tls_verify=0` past the filter, did
reach it. So nothing is set or refused on adoption for it. What is left: an
FFmpeg whose TLS default does not verify (before 8.0) would be the bypass, and
the pin block's comment already records propagation as "a default this layer
does not choose"; and a private-CA provider's segments fail on such a player,
which is availability, not exposure.

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
or by `playerWatchdog` (12 s) - whichever is first. **[Amended 2026-10-28,
D-PLY-35: 12 s is now the Timer's bound only while no verb runs, after a reply
(`Model.PLAYER_BIRTH_EDGE_MS`); while `start`, `restart` or `probe` runs it
carries that verb's own bound (4.4's bracket), and a start it stops keeps the
birth edge while the reattach probe looks for what it left.]** That gives `playerUp` the
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
| `reason: "error"` | stream failure **[Amended 2026-10-28, D-PLY-33, owner's decision: marked only when the `end-file` is for the named channel's own entry -- the entry-owner ring's, or, the ring silent, the entry the player last started; an error for any other entry is told as `playerStopped` and marks nothing]** **[Amended 2026-10-28, D-PLY-37, owner's decision: an error whose `file_error` names an OUTPUT of this machine -- `audio output initialization failed`, `video output initialization failed` -- is not the stream failing to load: told as `outputFailed` (`Audio output failed` / `Video output failed`, replace id 74023), marked never, whichever entry it names]** | notify + `withFailed` |
| `reason: "stop"` with no user stop | stream failure **[Amended 2026-10-28, D-PLY-33: told as `playerStopped`, marks nothing -- the death came after the load was replaced, so nothing says the stream caused it]** | a load we issued was replaced and then the process died |
| `reason: "redirect"` | ignored, never terminal | fires on the `.m3u8` masters IPTV uses most |
| no `end-file` at all | stream failure, generic reason **[Amended 2026-10-28, D-PLY-33, owner's decision: told, never marked -- `playerStopped`, `Playback stopped` / `“<name>” stopped unexpectedly` (UX 6.4, replace id 74022), the generic sentence in `lastError` and no log-tail line on the card]** | crash / SIGKILL |

**The entry gate fails open** (F4). The channel named is
`entryOwners[lastEndFile.playlist_entry_id]` when that id is known, else
`nowPlaying`. `entryOwners` is a QML map of at most four
`entryId -> {id, name}` entries, populated from the `entryId` that both `play`
and `player start` now return. A null or unrecognised entry id never suppresses
a notification - it only degrades which channel is named. Nothing else about the
notification path changes: `Model.notifyArgv` (`Model.js:1295`, with its S-04
leading-dash and typographic-quote rules), `NOTIFY_IDS.streamFailed = 74011`,
`Model.withFailed` is untouched in shape; the `failedAt` map stopped being session-only on 2026-09-24 (R11 as amended) and now persists in the source cache.

> **Amended 2026-10-28** (D-PLY-32): this table is the verdict at the socket's
> end and is unchanged. A `player start|restart` that REFUSES never reaches it
> and is not a stream failure: `Model.playerStartFailure` sends every refusal
> but `unsupported_scheme` to a local notification that marks nothing
> (requirement 6 in section 5). The "no `end-file` at all" row -- a crash, a
> kill, an out-of-memory kill, D-PLY-27's VO abort -- still marks the channel
> and says `Stream failed`. Whether it should is an open question for the
> owner, raised with D-PLY-32's report rather than decided here, because no
> code tells a player that died on this machine's account from one a stream
> crashed.

> **Decided 2026-10-28** (D-PLY-33, the owner: "a player death with NO
> end-file stops marking the channel"). The rows above are amended in place,
> and the decision is one model function, `Model.deathReport`, that every
> detector asks: a channel is marked failed only when mpv said its load
> failed -- an `end-file` with reason `error` for that channel's own entry
> (the entry-owner ring names it, or, the ring not having heard of it yet, it
> is the entry the player last started; the reply that fills the ring can
> land after mpv has failed the load and quit). Then, and only then,
> `Stream failed` and `withFailed`. Every other death the verdict says to
> tell -- no `end-file` at all, a `stop` and then a death, an error for
> another entry -- is told as `playerStopped` (`Playback stopped` /
> `“<name>” stopped unexpectedly`, replace id 74022) and marks nothing:
> `failedAt`, `failed.json` and `lastFailedId` untouched, the channel still in
> the zap ring. F4 holds: the gate decides the mark and the copy, never
> whether there is a card. The card carries no log-tail line, because at a
> death with no `end-file` the tail is a driver warning as often as a cause
> (D-PLY-29), and a crash or a kill leaves none; `lastError` reads the
> generic sentence. The same rule reaches PO-3 (4.5): a session record found
> with no player is a death nobody saw an `end-file` for, so the reattach
> marks nothing and, as before, tells nothing; it still retires the record.
> One detector the rule cannot reach yet: signal 1, `player start`'s
> first-load window, answers `failed` both for an `end-file` error on its
> entry and for mpv closing the connection (`observe_first_load` returns the
> same `{state, reason}` for both), so the shell still takes that `failed` as
> a stream failure and marks -- until the helper's reply says which it saw.

> **Decided 2026-10-28** (D-PLY-36 and D-PLY-37, the owner). **D-PLY-36**:
> the reply now says which it saw (4.3): `firstLoad.ended` is `end-file`,
> with mpv's `file_error` in `fileError`, or `closed`. `Model.deathReport`'s
> first-load branch reads it: an `end-file` is the stream's (marked, `Stream
> failed`), a `closed` connection is a death with no `end-file` (told as
> `playerStopped`, marked never) -- the D-PLY-33 rule, reaching signal 1. A
> reply with no `ended` (a helper from before) is the helper's word, as it was.
> **D-PLY-37**: an audio or video OUTPUT that could not be opened is this
> machine's failure, not the stream's. mpv 0.41.0 ends the file with reason
> `error` and `file_error` `audio output initialization failed` for an ALSA
> device that does not exist, PulseAudio down and PipeWire down alike, and
> only when the file ends -- the picture plays on until then (measured
> 2026-10-28, windowless and silent). Every detector asks
> `Model.outputFailure` before the own-entry test; an output's error is told
> as `outputFailed` and marks nothing. The join is on mpv's prose, so the two
> strings are pinned in `tests/fixtures/player-endings.json` with the mpv
> version, and `tests/test_player_endings.py` runs the real mpv to read the
> audio one again. The video string, `video output initialization failed`,
> is mpv's own name for the error and was reached by none of the five video
> output failures measured: a per-file one reads `no audio or video data
> played` when nothing else can play (that string still marks: under this
> player's launch shape it can only be a stream with nothing playable), or
> nothing at all when the sound plays on; and `--force-window=immediate`
> makes a video output that cannot open an exit before the socket (D-PLY-27,
> no `end-file`). It is kept on the owner's word and is UNVERIFIED. The
> helper's `ended_verdict` decides only whether an ending is told, never the
> mark or the card, so it needs no mirror of this rule; the helper passes
> mpv's `file_error` through and the model classifies it.

### 4.9 The stop ladder

> **Amended by section 14** (F-PLY-3): a detached stop cannot observe a
> `superseded` refusal, so the stop-settle timer probes and re-issues past
> the recorded sequence (`Service.qml` `stopSettleTimer`; harness P10). Read
> 4.9 with that in hand; 4.9.1 was edited in place after section 14 existed
> and carried no such pointer, which is the risk this line retires.

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
| 4.0-4.5 s | settle | `find_player()` empty **and** `connect()` returns ENOENT/ECONNREFUSED -> `unlink_stale_socket()` (S_ISSOCK-guarded). Never unlink on a successful connect, and never on a timed-out one. Both guards are re-checked at `STOP_POLL_S` until they agree or the kill rung's own 500 ms is up - see 4.9.1 |

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

#### 4.9.1 The settle, and why one look was not enough (D-PLY-8)

A wedged stop used to reap the player and leave `mpv.sock` on disk, and the
cause on record - that `find_player()` still saw the just-SIGKILLed process -
is **measurably false**. It is corrected here because a wrong cause recorded
confidently is worse than an open question: the "fix" it invites is to make
the finder see dying or zombie processes, and a double-forked grandchild can
sit as a zombie until the subreaper waits on it, so the ladder would then
report `running:true` after a successful SIGKILL and block the settle for
good.

What actually happens, measured on this machine against real mpv 0.41, killed
by pid, no window:

| After a... | `/proc/<pid>/cmdline` empties | the socket stops accepting | order |
|---|---|---|---|
| SIGKILL | 0.13-0.31 ms, 8/8 | 2.70-4.85 ms later | the finder goes **blind first** |
| `quit` | 3.7-5.7 ms | 2.0-2.7 ms **before** that, 6/6 | the listener goes first |

A killed process runs `exit_mm()` before it closes its descriptors, so its
command line is empty almost at once while its listening socket is still
bound. What a kill leaves behind that a quit does not is a **live listener
owned by a process the finder can no longer see** - and the blocking guard is
therefore `socket_is_dead()`, never `find_player()`.

The stop path asks each guard once, 4.5-7.5 ms after the signal: `wait_for_exit`
wins on its first check (it tests before it sleeps) and then one `/proc` scan
costs 3.7-4.9 ms for 225 pids here. A headless player's window is just under
that bar, which is why it settles cleanly in a test and why only a real
windowed player - a GPU context, a Wayland connection, decoder buffers and a
demuxer cache to tear down - reproduces the defect.

So `settle_socket(sock_path, deadline)` re-checks **both** guards at
`STOP_POLL_S` until they agree or the deadline passes. It never widens them:
a racing spawn seen by `find_player`, a **successful** connect (a wedged
player answering through its listen backlog) and a **timed-out** connect all
still block the unlink, on every iteration, and `unlink_stale_socket` still
re-checks `S_ISSOCK` at the moment it unlinks. Called without a deadline it is
byte-identical to one look and no sleep, which is what every call site outside
the stop ladder gets.

The deadline is the **kill rung's own**, not a new budget: `stop_ladder()`
reports the instant the rung that ran would have waited until, the kill rung
reserves 500 ms (`stop_escalation("term")` returns `waitMs: 0`, so the grace
falls back to `STOP_SETTLE_MS`) and spends about 0.3 ms of it. Only the
post-ladder settle in `player_stop` receives it, and that is the one call site
already inside the player lock - which is what makes an unlink safe across a
wait, because the lock is what stops a fresh socket appearing between the
check and the `os.unlink`.

**The budget measures the player, not the command (ruling CL1).** PLY-PERF-02's
4500 ms is the time until the player process is gone, not until `player stop`
returns. That is what the user experiences: `stop` is fired and forgotten, the
interface clears on the keystroke, and the command's return tells them nothing.
The settle runs after the process is already gone, so it cannot spend that
budget at all; the README says the same.

`player_probe` and `player_orphan_check` settled outside any lock, so a start
binding a fresh socket between their refused connect and their unlink would
have had the **new** socket deleted. Both now go through `settle_under_lock()`,
which takes the lock briefly and simply does not unlink when it cannot get it
(ruling CL8). Neither gets a deadline: a waiting unlink at a call site that
holds no lock of its own would lengthen the very exposure being closed.

### 4.10 Ordering: the intent sequence number

> **Amended by section 14** (F-PLY-3): the sequence rule below is stated
> without the correction that a detached stop cannot see the refusal it
> triggers; section 14 records it and PLY-STOP-07 tests the corrected
> behaviour.

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

**[2026-10-29, lane-p1b: the headers are PER FILE now, and the paragraph
above describes a mechanism that is gone.]** `header_properties` set the
channel's user agent, referrer and header list as GLOBAL properties before
the `loadfile`, so every entry the player went on to play without the helper
-- a nested playlist's entry (D-PLY-44), a pasted URL (the review's Ctrl+V
finding), a dropped one (D-PLY-46), `playlist-next` -- went out with the
provider's headers (measured: an appended entry's request carried the
channel's header on sec-int 6c79a9a, `tls-scenario.sh --windowless` W14).
Now `apply_channel` sets the three GLOBAL properties to values that belong to
no provider (mpv's default user agent, no referrer, no fields:
`neutral_header_properties`, still not best effort) and hands the channel's
own to the `loadfile` as PER-FILE options (`channel_load_options`):
`demuxer=lavf` (D-PLY-44), `user-agent`, `referrer`, `http-header-fields-clr`
and one `http-header-fields-append` per header. mpv restores a per-file
option when its file ends and applies none to an entry the helper did not
load, so requirement 7 holds by construction rather than by a remembered
reset. **The form, measured** (mpv 0.41.0 against a logging server inside
`unshare -rn`): the options argument as a STRING is a comma-separated
key=value list, and `http-header-fields=X-A: 1,2` arrived as `X-A: 1`; as a
JSON OBJECT it is read key by key, but the plain list option still splits
its value at commas (the same `X-A: 1`), and a backslash-escaped comma cannot
carry a value that ends in a backslash (`X-A: a\,X-B: b` arrived as ONE
header). `-append` takes its value verbatim, and an object that repeats the
key arrived as that many headers, in order, with `,`, `=`, both quotes and a
trailing backslash intact (W13 holds it). Python's json cannot repeat a key,
so the helper writes that object itself (`IpcPairs` / `ipc_json`, 05).
**[2026-10-29, lane-p1c, D-SINK-63: "applies none of them to an entry the
helper did not load" held only while mpv did not PREFETCH.]** With
`prefetch-playlist` on, mpv opens the next entry while the playing file's
per-file options are still in force, so an appended entry was sent the
channel's provider headers (rc-p1b measured it by token; W22 by token, past
the filter and from mpv.conf on sec-int 124589e). `--prefetch-playlist=no`
is now pinned and the name refused, so the sentence holds again.
The positional form, `["loadfile", url, "replace", -1, {...}]`, and the
named form (`{"name": "loadfile", ...}`) were measured equal; the positional
one is used because every double of the player and the harness stub read
the array, and mpv 0.41.0 takes `index` (-1, its default) before `options`
-- the pin block already needs an mpv that new. CR and LF never reach a
value: the parse turns them into spaces (`clean_header_value`).

**TLS joins this sequence (D-SINK-16, 4.15 layer 6).** `apply_channel` already
asserts `pause`, `aid`, `sid` and the three header properties before every
load, each for the same class of reason: mpv keeps them across a `loadfile`,
so the load must say what it wants rather than inherit it. `tls-verify` and
`stream-lavf-o` are asserted on the same line, with one difference that is
load-bearing and must not be smoothed out into consistency with its
neighbours: `pause`, `aid` and `sid` go through `try_command` and are best
effort, and TLS may not be. If those two properties cannot be made safe the
`loadfile` is REFUSED and reported the way the function reports its other
failures, because loading is precisely the act of handing a credentialed URL
and these header values to a process we could not secure.

### 4.12 mpvArgs filtering

`Model.splitMpvArgs` (`Model.js:1207`) is behaviourally unchanged: same
`/^--[a-z0-9][a-z0-9-]*(=.*)?$/` token regex including the D-QA-11
lowercase-only rule, same `--no-` form rejection, same `{args, rejected}` shape,
same `console.warn`. Filtered tokens land **after** the fixed options, so
`--ytdl=yes` still overrides the built-in `--ytdl=no` as documented. The helper
re-validates each `--mpv-arg` against a python mirror of the same regex and set
(defence in depth, and it is a public CLI) and reports dropped tokens in
`warnings`; a parity test asserts the two reserved sets are equal.

**[2026-10-29, lane-p2a, D-SINK-47: the kept tokens are no longer ON the
player's argv.** That argv is `/proc/<pid>/cmdline`, readable by every account
for the hours a detached player runs, and `COREDUMP_CMDLINE` in the system
journal if it crashes. The helper writes the kept tokens into
`<runtime>/mpv-args.conf` -- 0600, created under a name of its own with
`O_EXCL | O_NOFOLLOW` in the 0700 runtime folder and renamed into place, one
line per token in mpv's length-quoted form, `name=%N%value` (N the value's
UTF-8 byte length) or `name` for a flag -- and the launch argv names it once,
`--include=<that file>`, WHERE THE TOKENS STOOD: after the base argv, before the
pin block. Measured on mpv 0.41.0 (windowless, QA-RESULTS "D-SINK-47"): mpv
parses an included file at its position (an earlier argv token loses to it, a
later one beats it) and marks what it sets as set from the command line, so a
per-file profile cannot replace a token's value and the pin block keeps the
last word; sixteen tokens holding `=`, `,`, both quotes, spaces, `#`, `%`, a
trailing backslash and UTF-8 read back identical through the file and on the
argv (the plain `name=value` form cuts `a#b` to `a`); the five-way table below,
re-run with the tokens in the file, holds every pin. The file is removed as
soon as the socket answers -- mpv binds it only after reading its whole
command line -- and on every way out of a launch; a restart writes it again. A
crash or an adoption sees the file's NAME on the argv and no file. What
differs from the argv, stated: a line mpv cannot parse is reported and skipped
where a token stopped the player from starting; the eleven options mpv takes on
the command line only (`--help`, `--version`, `--v`, `--list-*`, `--show-profile`,
`--input-cmdlist`, `--input-keylist`) are refused in a file; and `--no-config`
(`--config=no`) is read too late to stop mpv reading the user's own mpv.conf.
A token holding a line break or a NUL cannot be one line and is refused by both
filters; so is one holding a lone surrogate, which no UTF-8 file can hold (a
byte the helper's argv could not decode arrives as one, and so does a JSON
`\ud800` escape): the first version kept it and the start ended `internal`
at the write (`Model.splitMpvArgs` / `filter_mpv_args`, through
`mpv_token_writable`). mpv's report of a line it cannot parse ECHOES the value
(`<file>:1: setting option volume='<value>' failed.`, and the option's own
complaint before it), which for a token holding a secret would be a sink; it
is not one here only because mpv 0.41.0 writes those lines to its standard
OUTPUT, which `spawn_detached` points at /dev/null -- measured, windowless, the
helper's own descriptors: nothing on the stderr pipe the launch reason is read
from, the same lines on stdout when stdout is a pipe. Capturing the player's
stdout for a better launch reason would open it, and needs the kept tokens'
values scrubbed first. Residual: a player adopted after the upgrade keeps the
tokens it was launched with on its argv until it restarts.]**

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
user's own mpv config is their deliberate choice. **[2026-10-29: still
outside the FILTER, no longer outside the design -- 4.12.1. The owner's
decision is to keep reading mpv.conf and pin, after the user's tokens, every
option a security layer depends on, because a plain line, a named profile, a
profile-cond profile and a per-file profile in that file each undid a layer
(measured, D-SINK-44).]**

The table above is the M2-02 round, not the whole of `MPV_RESERVED`. Later
rounds added entries on the same reasoning for different sinks:
`--load-scripts` (D-SINK-4, the MPRIS session bus),
`--demuxer-cache-unlink-files` (M5-01 ruling D3, a cache file that outlives the
player) and `--tls-verify` (D-SINK-13, section 4.15). **The TLS entry is the
one that is not sufficient on its own**, and 4.15 is where that is specified:
reserving a name stops the token that spells it and stops nothing that reaches
the same setting indirectly, and `--profile` reaches it -- measured. So the
guarantee for that option lives in the composition, as a re-assertion of
`--tls-verify=yes` after `p.extraArgs`, and the reserved entry exists so the
user is told rather than silently outvoted. `--tls-ca-file` stays unreserved
by the same PO-5 shape as `--ytdl`: it is the documented escape, and
`--screenshot-dir` is the precedent for an option this list deliberately leaves
alone.

`--gpu-sw` is left alone too, and its shape is the OPPOSITE of 4.15's -- the
shape `--ytdl=no`, `--screenshot-dir` and the two cache directories already
have, a base token a user's later one may beat (D-PLY-27, the owner's
decision of 2026-10-26). mpv
0.41.0's automatic VO probe aborts on any compositor that can serve no
hardware GL or Vulkan context -- a VM on llvmpipe, a pixman compositor: it
loses the `waylandvk` surface, fails `x11vk` through a lazy Xwayland or with
no DISPLAY at all, refuses the llvmpipe EGL context as a software renderer
without releasing its Wayland state -- a pointer that shares a union with
`vo->x11` since mpv a310a65d -- and trips its own assertion at `x11egl`,
`vo_x11_init: Assertion '!vo->x11' failed` (video/out/x11_common.c:679;
mpv-player/mpv#17190, fixed on master by a58dd8ac4 and in no release as of
2026-10-26; this paragraph first blamed `x11vk`, D-DOC-26), about 5 s after
every launch; the service relaunches it every ~5.5 s for as
long as the play intent stands, a crash card and a coredump journal entry per
zap (no core file: D-SINK-39 holds the player's core limit at 0). Measured on
2026-10-25 in the harness's pixman cage with this argv shape (QA-RESULTS
"F-HARNESS-45"): `--gpu-sw=yes` makes the probe accept the software context
(`current-vo gpu-next`, `vo-configured true`); DISPLAY is not the lever and
`--vo=wlshm` is not an alternative. So `--gpu-sw=yes` is in the base argv
(`MPV_GPU_SW` in both mirrors, after the two cache directories and before
layer 1 of TLS) as a rendering PREFERENCE, not a security layer: once, before
the user's tokens, so a `--gpu-sw=no` or `--no-gpu-sw` in `mpvArgs` lands
after it and wins by the last-token rule; never re-asserted at the tail;
never reserved. The shared fixture pins the count and the position off its
own `gpuSoftware` field in both suites, and carries the user override as a
case. The base argv does NOT carry `--ao=null` with it: a user's player must
have sound, and that token is the harness's own (F-HARNESS-45).

The token's cost, read from mpv's probe order and NOT measured: with
`--gpu-sw=yes` the probe accepts the FIRST context that comes up rather than
the first that comes up in hardware, and `waylandvk` is tried before the
wayland EGL context. So a machine whose GL is hardware but whose only Vulkan
device is a CPU one (lavapipe, `vulkan-swrast`, with no hardware Vulkan ICD)
would render through Vulkan in software where the token's absence would have
fallen through to hardware EGL; a machine with a hardware Vulkan ICD is not
in that class (libplacebo prefers it), and this machine is not (Intel and
NVIDIA ICDs, no `vulkan-swrast`). That user's lever is `--gpu-sw=no` in
`mpvArgs`, and the README names it. "Comes up on a VM" is likewise read
from the class, not measured on a VM: what was measured is a pixman cage.

### 4.12.1 Pin and classify: the player's last word (2026-10-29, D-SINK-43 to D-SINK-46)

**[2026-10-29, the owner's decisions on the security review of that day.]**
The reserved list was a list of the options somebody had thought about, and
the review found eight it had not: `--demuxer-lavf-o` for HLS (D-SINK-43),
the user's mpv.conf routes the argv never pinned (D-SINK-44), the tokens past
the list that undo a layer (D-SINK-45), and mpv's built-in select menu
(D-SINK-46). Fixing them one at a time is D-SINK-2, D-SINK-13 and D-SINK-15
again, so the model changed. Three decisions, the owner's:

- **Pin and classify, not a strict allowlist.** A user's existing `mpvArgs`
  keep working. Every option a security layer depends on is PINNED on the
  launch argv after the user's tokens, which is D-SINK-13's layer-2 shape: the
  last word wins over a token, a named profile and a plain mpv.conf line, and
  a token there is SET FROM THE COMMAND LINE, which is what keeps a
  `[protocol.*]` or `[extension.*]` profile from replacing it at file load.
  The names that undo a layer are RESERVED in both mirrors, and a gate
  classifies every option the installed mpv offers, so an option nobody has
  classified turns it red.
- **Keep reading mpv.conf, with pins** -- not `--no-config`. `--load-auto-profiles=no`
  is pinned; its cost is that the user's profile-cond auto-profiles stop
  applying inside this player only. Protocol and extension profiles still
  apply, but cannot replace a pinned option (measured below).
- **Turn off only the select menu**: `--load-select=no`, pinned and reserved.
  Stats, the console, the context menu, commands and positioning stay.
  **[2026-10-29, the owner's decision on D-SINK-61: the console goes too --
  `--load-console=no`, pinned, with mpv's alias `--load-osd-console`
  reserved beside it. Stats, the context menu, commands and positioning
  stay. Measured below, in the routes paragraph.]** **[2026-10-29, lane-p2a,
  D-SINK-67, the owner's "yes" to turning stats off: the stats overlay goes
  too -- `--load-stats-overlay=no`, pinned and reserved. The context menu,
  commands and positioning stay.]**

**The classification** is `tests/fixtures/mpv-options.json` (dev branch): every
one of the 899 option bases `mpv --no-config --list-options` prints on mpv
0.41.0, each with one of five classes, and a one-line `why` for every
string-shaped, list, key/value, object-list and `[file]` option and every
alias.

| Class | What the plugin does | Count (mpv 0.41.0) |
|---|---|---|
| `allowed` | a user token passes and lands after the base argv | 827; 825 since 2026-10-29; 822 since lane-p1c (the same day); 821 since lane-p2a (the same day) |
| `reserved` | a user token is REFUSED, by name, in both mirrors' `MPV_RESERVED` | 39 |
| `pinned` | re-asserted by the trailing pin block, AFTER the user's tokens; refused as a token as well, except the key-pinned `--demuxer-lavf-o` and (2026-10-29) `--script-opts` | 18 (16 options and 2 aliases); 21 since 2026-10-29 (+ `--drag-and-drop`, `--script-opts` and its alias); 24 since lane-p1c (+ `--load-console` and its alias, `--prefetch-playlist`); 25 since lane-p2a (+ `--load-stats-overlay`) |
| `warned` | kept, with the PO-10 footer line | 7; 6 since 2026-10-29 (`--script-opts` moved to key-pinned and still warns for ytdl; `--rtsp-transport` joined) |
| `base` | set before the user's tokens; a user token may override it | 8 |

An alias takes its target's class (`--watch-later-directory` is mpv's alias
for the reserved `--watch-later-dir`, and base-name matching could not see
it). The two names `--{` and `--}` are refused by shape, `MPV_ARG_RE`, so the
two mirrors hold 54 names. The unit tests pin both mirrors to the file by
CALLING the filter and the argv builder (`tests/test_mpv_options.py`,
`tests/Model.test.js`); `scripts/check-mpv-options.py`, run by
`scripts/check.sh` as "mpv option guard", holds the file against the mpv
that is installed -- an unclassified option, a changed type or alias target,
an alias classified apart from its target, or a string option without a
reason is red; an option the file names that this mpv lacks is a note -- and,
when the ffmpeg CLI is installed, against FFmpeg's own TLS protocol options
(`ffmpeg -h protocol=tls`), because a `--demuxer-lavf-o` key reaches each of
them on every HLS segment open. With no mpv it answers 77, which the gate
reads as red unless `MPV_OPTIONS_SKIP_OK=1`. Seen red with `--load-select`
deleted from the file, with FFmpeg's `verifyhost` deleted, and with the
`--watch-later-directory` alias classified `allowed`.

**The pin block**, in order, after the user's tokens, in both mirrors
(`MPV_PIN_BLOCK`, preceded by the one pin that carries a path):

| Pin | The layer it holds |
|---|---|
| `--watch-later-dir=<runtime>/watch-later` | the resume record names the stream path; a named profile moved it to `$HOME` (measured) |
| `--load-scripts=no` | D-SINK-4; a named profile turned autoload back on (measured) |
| `--scripts-clr` | a plain mpv.conf `script=` line loaded a script despite `--load-scripts=no`, and the script read the credentialed path (measured) |
| `--input-commands-clr` | commands run at startup: `load-script`, `run`, `set` (D-SINK-45; a plain mpv.conf line ran them, measured) |
| `--input-commands-append=keybind ctrl+v ignore` | **[2026-10-29, lane-p1b, D-PLY-46]** mpv's default `Ctrl+v` is `loadfile ${clipboard/text} append-play`: a pasted URL became an entry no gate saw. `ignore` replaces it and the user's own input.conf binding of the key (measured: the binding list shows `ignore` at a higher priority than both, and a keypress appended nothing, W15); the same `keybind` is sent on adoption |
| `--load-auto-profiles=no` | auto_profiles.lua applies a profile-cond profile at every load, over the command line (D-SINK-44) |
| `--player-operation-mode=cplayer` | `pseudo-gui` makes mpv apply the user's `[pseudo-gui]` profile AFTER the command line with nothing preserved, which undid every other pin; a plain mpv.conf line was enough (measured by the recheck, below; D-SINK-44) |
| `--load-select=no` | select.lua: `g l` forks `ffmpeg -i <path>`, the credentialed URL on a 0444 `/proc` cmdline for the life of the stream (measured), `g p` draws it (D-SINK-46) |
| `--load-console=no` | **[2026-10-29, lane-p1c, D-SINK-61, the owner's "turn the console off"]** commands.lua queues every log line at the terminal's level for the console, and the console draws them when it opens; an HLS key that 404s while a channel plays is logged at error level with its whole URL. On sec-int 124589e the console key put that line in the console's buffer and drew it (read at mpv's trace level from a second client: the `script-message-to console log` that handed it over and the `show-text` the console drew with both carried the URL's secret -- the console's terminal-mode render, `--video-osd=no` in the rig, which has no window to draw an overlay on); with the pin the console is not loaded, `script-binding console/enable` is refused, the key draws nothing that carries it, and the same error line still reaches an error-level client (`tls-scenario.sh --windowless` W23). Also set off on adoption, which unloads the script |
| `--load-stats-overlay=no` | **[2026-10-29, lane-p2a, D-SINK-67, the owner's "turn stats off"]** the stats overlay's first page (`i`, `I`, `script-binding stats/display-stats-toggle`) and its file page (`stats/display-page-5`, which the OSC title's left click runs) draw `${filename}`, and mpv's `filename` of a URL whose last path segment is empty is the WHOLE URL -- userinfo and path credentials -- and of a URL with no path its userinfo (measured by rc-p1c). On dev 2727179 the rig's channel `.../live/rig/<secret>/` drew the secret twice of three draws; with the pin nothing it draws carries it, both bindings are refused, and the option reads off, on a player this release starts and on an adopted pre-pin one, where it is set off at the reattach and mpv unloads the script (`tls-scenario.sh --windowless` W26). Left out of the per-file profile read-back for now (`PER_FILE_EXEMPT`: the harness stub does not model the option), so a pre-pin player whose own mpv.conf turns stats back on per file gets them back until it restarts |
| `--prefetch-playlist=no` | **[2026-10-29, lane-p1c, D-SINK-63]** with it on, mpv opens the NEXT entry while the playing file's per-file options are still in force, so an entry the helper did not load was sent the channel's provider headers (measured by rc-p1b; on sec-int 124589e by token, past the filter and from mpv.conf, W22). Reserved as a token, and set off on adoption |
| `--load-unsafe-playlists=no` | mpv's origin rule for nested entries: with it on, a server's playlist made the player write a file the server named and play a local file (measured, D-SINK-44) |
| `--save-watch-history=no` | appends every path played, credentials and all, to `~/.local/state/mpv/watch_history.jsonl` (measured from mpv.conf) |
| `--log-file=` | a log naming every URL (a plain mpv.conf `log-file` wrote one; pinned empty, no file at all) |
| `--reset-on-next-file-clr` | `all` restores the PREVIOUS channel's header options at the next load, so a zap sent the first provider's headers to the second provider's host (measured, D-SINK-51) |
| `--osd-playlist-entry=title` | `filename` makes `${playlist}` (F8, the OSC's playlist buttons) draw the whole loadfile URL (measured) |
| `--drag-and-drop=no` | **[2026-10-29, D-PLY-46]** mpv's default `auto` loads a URL dropped on the window as a new entry no gate saw; read back as off (mpv answers `no` as the boolean False), and set on adoption. A drop itself was not performed: there is no window here |
| `--script-opts-append=osc-title_mbtn_mid_command=ignore` | **[2026-10-29, D-SINK-52, the owner's "pin and refuse"]** the OSC binds the title's middle click to `show-text ${path}`, which draws the whole credentialed URL (read from the osc.lua in /usr/bin/mpv, not clicked). `-append` replaces that one key: a user token setting it lost to the pin and the user's other key stayed (measured). Of the OSC's other command defaults, the playlist buttons' middle click draws `${playlist}`, which reads the channel's title under the pinned osd-playlist-entry (measured with expand-text); the rest draw no path |
| `--stream-lavf-o-clr` | command-line-set, so a `[protocol.https]` profile can no longer put FFmpeg's `tls_verify=0` back (D-SINK-44) |
| `--demuxer-lavf-propagate-opts=yes` | the next pins reach segment and key opens only by propagation; off, they fall back to FFmpeg's own default -- true in n9.0.1, and a default this layer does not choose |
| `--demuxer-lavf-o-append=protocol_whitelist=http,https,tls,tcp,crypto,data,httpproxy` | **[2026-10-29, D-SINK-55]** a stream server that answers an http(s) URL with an SDP body makes FFmpeg's sdp demuxer open `rtp` with the whitelist it inherited from http, and the player LISTENS (rc-dest measured `c=0.0.0.0` binding 0.0.0.0:P and P+1, under a .ts path too). With this list nothing bound, and every scheme the gate admits still played or reached its server (the table below). Read back exactly over IPC (`demuxer_tls_unsafe`), appended on adoption, refused in a token (`protocol_whitelist`, `protocol_blacklist` joined the filter's words). An rtsp channel's own loadfile adds `rtp,udp` for that file only, because its demuxer opens its RTP transport itself and a user's `--rtsp-transport=udp` (warned, D-SINK-53) needs them |
| `--demuxer-lavf-o-append=format_whitelist=hls,dash,mpegts,mov,matroska,flv,live_flv,mp3,aac,ac3,eac3,ogg,flac,asf,rtsp,webvtt` | **[2026-10-29, lane-p1c, D-SINK-62]** the demuxers libavformat may use, checked against the format a probe chose or a user forced and copied into every nested context. A demuxer that opens the URLs its content names opens them with the protocol list above, which has to hold tcp and tls, so FFmpeg's IMF demuxer listened on 0.0.0.0 through an asset URI, and an ffconcat file naming the CPL reached it too; with the list, nothing listens and every channel kind the gate admits still plays (4.12.2 has the search and the measurements). Read back exactly, appended on adoption, refused in a token (`format_whitelist`, `format_blacklist`) |
| `--demuxer-lavf-o-append=tls_verify=1` | D-SINK-43: the last word on FFmpeg's `tls_verify` for every segment open; `-append` replaces that one key and keeps the user's others |
| `--tls-verify=yes` | D-SINK-13 layer 2, still the last element |

**Measured five ways per pin** on 2026-10-29, windowless (mpv 0.41.0 / FFmpeg
n9.0.1, `--vo=null --ao=null`, a private HOME and XDG tree, `--config-dir`
naming the case's own mpv.conf as the model of the user's), the argv built by
each tree's shipping `mpv_launch_argv` and the channel loaded by its shipping
`apply_channel`, against 127.0.0.1 servers: a CA-signed provider trusted
through `--tls-ca-file`, a self-signed attacker, and an attacker that answers
libavformat's reopen with a certificate valid for its OWN name. Each contrary
value was delivered as (i) a token injected PAST the filter, (ii) a plain
mpv.conf line, (iii) a `[protocol.<scheme>]` profile, (iv) a profile-cond
profile and (v) a named profile the user's `--profile` token applies. On the
tree every one of the 75 cells held the pin. On dev 713afbf, 58 of 75 did not:
`demuxer-lavf-o`, `load-auto-profiles`, `load-select`, `save-watch-history`,
`log-file`, `osd-playlist-entry`, `input-commands` and `load-unsafe-playlists`
all five ways; `stream-lavf-o` by the two per-file routes and `tls-verify` by
the profile-cond one, the routes D-SINK-16's runtime set cannot reach;
`demuxer-lavf-propagate-opts` every way but the profile-cond one;
`script=` and `reset-on-next-file` by the token, the plain line and the named
profile; `watch-later-dir` by the token, the profile-cond profile and the
named profile; `load-scripts` by the token and the named profile. The crash
journal read 81 entries before and after every one of the 150 runs. The TLS
and sink rows of it are re-runnable: `scripts/dev-harness/tls-scenario.sh
--windowless` (W1 to W9 and the controls C1 and C2, in the same windowless
shape, with an adopted player started by v0.15.0's own argv) read 13 passed,
0 failed on the tree and, with `--baseline 713afbf`, 4 passed and 9 failed --
every attack check red, both controls green.

**[2026-10-29, lane-p2a: re-measured with the user's tokens in the private
options file (D-SINK-47).** The same rig, the same five routes, the
contrary token and the user's `--profile` now delivered through
`--include`, plus a sixteenth row for the stats overlay (D-SINK-67): on the
lane's tree all 80 cells held the pin, the file present at the socket in all 41
cases that had one; on dev 2727179 the fifteen older rows held all 75 and the
stats row was contrary all five ways (stats on). Crash journal 81 before and
after each of the 160 runs.]**

**[2026-10-29, the recheck: a sixteenth pin.]** The five routes above are not
every way mpv.conf reaches the options. With `player-operation-mode=pseudo-gui`
-- a plain mpv.conf line, a named profile or a token -- mpv applies the user's
`[pseudo-gui]` profile once at startup, AFTER the command line and with nothing
preserved, so it overrode every pin while `set-from-commandline` still read
true. Measured on the tree as it stood (the lane's tip, 99d23aa): a script
loaded and wrote the credentialed path, the resume record and the watch
history landed outside the runtime folder, select forked `ffmpeg` with the
URL, and with `load-unsafe-playlists` in that profile a server's nested
playlist truncated a scratch file the server named. The TLS peer held, because
`apply_channel` re-sets and reads back its properties before every load. A
trailing `--player-operation-mode=cplayer` (pinned, and the name reserved)
closes it: the profile is consulted only when the mode reads `pseudo-gui`
after the whole command line. `tls-scenario.sh --windowless` W10 observes it:
red on 99d23aa and on dev 713afbf, green with the pin (14 passed, 0 failed).
The `[encoding]` profile, which mpv applies the same way in encoding mode,
needs `--o`, which is reserved and which mpv refuses in a config file
(measured); no other post-command-line profile was found, by reading, not
by a search of mpv's source.

**[2026-10-29, lane-p1b: every scheme the gate admits, under the whole pin
set.]** Measured windowless inside `unshare -rn` (loopback only; multicast
routed onto it in the namespace), each channel loaded by the tree's own
`apply_channel`, the player's listening sockets read with `ss`, crash
journal 81 before and after every run (the lane's rig, the QA-RESULTS block):

| Scheme | Result with the pins | On sec-int 6c79a9a |
|---|---|---|
| http TS, https TS (CA via `--tls-ca-file`) | play | play |
| HLS master over http, variant and segments over https | play, segments fetched | play |
| rtmp (an `ffmpeg -listen 1` server) | plays | plays |
| rtmps | reaches its server (TLS handshake, RTMP C0) | the same |
| rtsp, mpv's default TCP transport (a fake server streaming MP2T interleaved) | plays, binds nothing | plays |
| rtsp with the user's `--rtsp-transport=udp` | reaches SETUP and binds its RTP/RTCP pair -- the user's warned choice (D-SINK-53); with the global list alone it stopped at DESCRIBE, which is why an rtsp channel's loadfile adds `rtp,udp`. **[2026-10-29, lane-p2a, D-SINK-65: FFmpeg's own `rtsp_transport` through `--demuxer-lavf-o` binds the same pair, and it takes FLAGS: `udp`, `1`, `0x1`, `2*0.5`, `+udp`, `-tcp`, `0`, `udp+tcp`, quoted, bracketed, `%3%udp`, `udp_multicast`, the `-append`/`-set` forms, beside another key and as a later repeat all bound (13 of 19 spellings, inside `unshare -rn`); `tcp`, `http`, `tcp+http` and every `rtsp_flags` spelling bound nothing (the numeric `listen`, 2, fails without the `listen_timeout` the read-back removes). Both mirrors now warn on every occurrence of the key unless each value is a plain `+`-join of tcp, http and https -- W27 holds every binding spelling to a warning; an mpv.conf line is unwarned, as `--rtsp-transport` there is]** | binds |
| rtsp whose server answers a TCP request with a UDP transport | binds nothing | -- |
| udp and rtp multicast (`ffmpeg` senders on 239.x) | play, bind the group | the same |
| srt as caller (an `ffmpeg` srt listener) | plays (its own ephemeral UDP socket, a caller's) | the same |
| mms, mmsh | reach the server (mpv maps mms to mmsh, HTTP) | the same |
| a server answering with an SDP body, `.sdp` and `.ts` | nothing binds (W12) | binds 0.0.0.0:P and P+1 |
| a server answering with a plain M3U (http, srt listener, rtp entries) | `unrecognized file format`; nothing fetched, nothing binds (W11) | the http entry fetched, srt and rtp bound |
| a `.pls` or plain `.m3u` redirector as the channel | `unrecognized file format`, told as a sentence (below) | played through the nested entry |
| `--ytdl=yes` on a page yt-dlp resolves into separate video and audio formats (a stand-in yt-dlp on the rig's own server) | does NOT play: mpv joins the two as an `edl://` playlist of its own, and the per-file `demuxer=lavf` refuses it (nothing past the page fetched); a page resolved into ONE format plays | plays |

That last row is a cost the owner's decision did not name: PO-5's documented
escape hatch stops working for split-format sources. It is raised as a
decision request rather than routed around -- skipping `demuxer=lavf` when
`--ytdl` is on would reopen the nested route for exactly the users who
already accepted a handoff -- and the README says it.

**The token filter adds one rule.** A `--demuxer-lavf-o*` token whose text
contains `verify`, `ca_file`, `cafile`, `listen` or `external_sock` is
refused (`MPV_DEMUXER_TLS_WORDS`). A substring of the raw token rather than a
parse of mpv's key/value syntax, because FFmpeg matches option names exactly,
so every spelling of a key -- quoted, `%n%`-escaped, `-append`ed -- still
carries the word; the price is refusing a token whose VALUE says `verify`.
The token half is the honest half. The binding half is the third IPC reading
(4.5.1 and 4.15 layer 9), which judges the PARSED map and no quoting reaches:
`tls_verify` or `verify` must read `"1"` when present, and `ca_file`,
`cafile`, `verifyhost`, `listen` and `external_sock` must be absent -- the
two sets are FFmpeg's TLS options as the gate lists them, classified in the
fixture, and every key the fixture forbids or pins contains one of the
filter's words, which the gate also holds.

**[2026-10-29, lane-p1c: three more words, and the premise above is false in
one place.]** `format_whitelist` and `format_blacklist` (D-SINK-62: the pin
block now owns the demuxer's format list; FFmpeg n9.0.1 has no
`format_blacklist`, refused rather than reasoned about) and
`seg_format_options` (D-SINK-64). "Every spelling of a key still carries the
word" holds for a key of the demuxer-lavf-o map itself, which mpv hands to
FFmpeg as dictionary entries, byte for byte. It does NOT hold inside a key
whose VALUE is itself an options dictionary, because FFmpeg parses that
value with its own escapes and quotes: hls's `seg_format_options` (the
options of each segment's demuxer) took `"format\_whitelist=sdp:protocol\_whitelist=rtp,udp"`,
which carries neither word, passed this filter in both mirrors, and replaced
both pinned lists in the segment's context; with the user's
`extension_picky=0` beside it, a stream server answering an HLS segment with
an SDP body made the player listen on 0.0.0.0 -- on sec-int 124589e and,
past the filter, on the format-listed tree before this word (measured
inside `unshare -rn`). So the key is refused whole, and the read-back
counts it (`DEMUXER_FORMAT_FORBIDDEN`) and `secure_player` removes it before
every load, the way it removes a TLS key, because a plain mpv.conf line
lands in the same map (`tls-scenario.sh --windowless` W24). The search for
another such key over every demuxer and protocol the list admits
(`ffmpeg -h demuxer=X`, `-h protocol=X`, `-h full` for the context's own):
the only other dictionary-typed option is mov's `decryption_keys`, a map of
key identifiers to keys, which carries no option name.
**[2026-10-29, rc-p1c: the read-back's exact keys had the same blind spot one
layer down.]** The token filter matches a WORD; the read-back removes exact
KEYS, and `DEMUXER_TLS_FORBIDDEN` holds `listen` and no other listener key.
The rtsp demuxer's `listen_timeout` implies its listen flag (a value above 0
sets it in `rtsp_read_header`), and it is the key that flag cannot bind
without (the listener's tcp timeout is the value times 1000; the default -1
is out of tcp's range, so `rtsp_flags=listen` alone fails to open). A token
naming it is refused by the word `listen`, but a plain mpv.conf
`demuxer-lavf-o=listen_timeout=5` reached the map, and an rtsp channel then
LISTENED on its URL's host and port -- measured inside `unshare -rn` on
sec-int 124589e and on lane-p1c, by mpv.conf, with `rtsp_flags=listen,
listen_timeout=0`, and on an adopted pre-pin player; the URL's host is the
provider's, so it binds where that name resolves to this machine. The key is
now in `DEMUXER_FORMAT_FORBIDDEN` (`removed` in the fixture's ffmpegFormat):
counted by the read-back and removed before every load, after which the same
three bound nothing and an rtsp channel with the user's other rtsp key
played. The search over the admitted demuxers' and protocols' options for
another key that turns the client into a listener: `listen` (http, tcp,
tls: removed already), rtsp's `rtsp_flags` (its listen bit cannot open
without this key) and `listen_timeout`; none other.

**What else is reserved** (each reason in the fixture): `--stream-dump` and
`--o` (the stream to a file, `--stream-record`'s class), `--watch-history-path`,
`--ao-pcm-file` and `--vo-image-outdir` (the stream's decoded audio or every
frame to a directory the plugin never listed), `--osd-playing-msg`,
`--osd-status-msg`, `--term-playing-msg`, `--term-title` (property
expansion), `--input-conf` (a file of commands, fetched from a URL at startup:
measured), `--playlist` (entries loaded before the shell, user-origin, so
every protocol passes, and the newborn-player check would read them as
another client's), and `--sub-files`, `--audio-files`, `--external-files`,
`--cover-art-files` and `--chapters-file` with their CLI aliases, each of
which opened a second address the token named and sent it the channel's
provider headers (measured, D-SINK-51). `--http-proxy` is WARNED, not
refused: for a plain-http stream the proxy receives the whole credentialed
request line and the headers (measured), and some users need one.

**The routes by which an option reaches the player**, the rule-15 list, each
with what holds it now: a token (the filter, then the pin block); a plain
mpv.conf line (loses to anything on the command line); a named profile, the
user's own `--profile` (the pin block comes after it); a profile-cond
profile (never loaded: `--load-auto-profiles=no`); the `[pseudo-gui]`
profile mpv applies after the command line in that operation mode (never:
`--player-operation-mode=cplayer`, pinned, added by the recheck); a
`[protocol.*]` or `[extension.*]` profile (cannot replace a
command-line-set option, so every pin is one); `--include` and `--config-dir` (reserved; since D-SINK-47 the
plugin's own `--include` names the user's options file, before the pins); input.conf and
`--input-commands` (commands at startup cleared; key bindings are the user's
keypresses); IPC `set_property` from the helper (the third reading, before
every load); and the built-in scripts, which `--load-scripts=no` does not
stop: ytdl_hook (inert under `--ytdl=no`), auto_profiles (off), select (off),
osc, console, stats, commands, context menu, positioning. Of those that stay,
read from the scripts embedded in `/usr/bin/mpv` and not clicked: the OSC's
title middle-click runs `show-text ${path}` and draws the whole credentialed
URL (D-SINK-52; **[2026-10-29: pinned to `ignore`, the owner's "pin and
refuse"]**), the stats page the OSC title's left click
opens draws `${filename}`, which carries a query-string token (measured:
`long.ts?token=...`) (**[2026-10-29: kept on; the owner turned off only
select and the console]** **[2026-10-29, lane-p2a, D-SINK-67: and the whole
URL, userinfo and path credentials, for a URL whose last segment is empty,
measured by rc-p1c; the owner turned stats off, pinned above]**), the context
menu's select entries are dead with select off, the console forks only
`wl-paste` on a user's paste, and commands and positioning fork nothing that
carries `path`. **[2026-10-29, lane-p1b: the console DRAWS a sink of its
own, reported and not changed (the owner's call, proposed D-SINK-61).]**
commands.lua enables `silent:terminal-default` at load, so mpv queues every
log line at the terminal's level -- `--msg-level=all=error` here -- and draws
them when the console opens. mpv logs a failed open at ERROR level with the
WHOLE URL: measured over IPC at that level, `[stream] Failed to open
http://u9:pass9@127.0.0.1:47800/live/tok9/missing.ts.` So a channel that
fails to open puts its credentialed address on screen, and into any
screenshot, the next time the user opens the console in that player. The
shell's own copy of that line is redacted (`Model.pushPlayerLog`); the
console's is mpv's. Levers, none taken: `--load-console=no` (the owner kept
the console), `--msg-level=stream=fatal` (also silences the line the shell's
failure tail uses), or living with it as a user action on the user's screen.
**[2026-10-29, lane-p1c: the owner's decision is to turn the console off,
`--load-console=no` in the pin block (the table above has the
measurement).]** Two corrections to the paragraph. Under `--idle=once` a
load that fails ends the player, so the line that sits in the console's
queue is one logged while a channel PLAYS -- an HLS key that will not open
(`hls: Unable to open key file <URL>` at error level), a segment refused by
hls's extension check (`URL <URL> is not in allowed_segment_extensions`) --
which is what W23 drives. And with the console gone, commands.lua stays
loaded (`--load-commands` is the owner's to keep) and still asks mpv to queue
the log for it, silently, but it hands the queue to no one: its prompt opens
through the console, so the key that would open it reaches a script that is
not there, nothing is drawn, the queue is never delivered (measured: no
command the player is told to run carries the URL), and the key adds no
error line of its own to what the shell reads. The shell's failure tail is
unchanged: mpv sends the same error-level line to a client that asked for
error-level messages, and the shell redacts it (`Model.pushPlayerLog`; W23
reads the line and `redact_urls` of it).

**An adopted player.** A player launched by 0.15.0 or earlier holds none of
the pin block. Over IPC the helper migrates what can be migrated and refuses
what cannot (4.5.1): measured on a player launched by dev 713afbf's argv and
driven by the tree's `migrate_tls`, `pin_adopted_player` and `apply_channel`,
a `[protocol.https]` profile setting `stream-lavf-o` or `demuxer-lavf-o` was
refused (0 GETs; the player is stopped), a profile-cond `tls-verify=no` was
unloaded and refused the attacker, a `demuxer-lavf-o` `tls_verify=0` or
`verifyhost` was removed with the user's other key kept, mpv.conf's watch
history stopped, and select's fork did not happen; the CA-signed control
played. What remains on such a player, stated exactly: a script it already
loaded from a `script=` line in mpv.conf keeps running (nothing unloads it),
startup `input-commands` already ran, and an `include`-carrying per-file
profile reads unsafe and stops it. **[2026-10-29, the recheck.]** And the
non-TLS pins `pin_adopted_player` writes at runtime do not hold against a
per-file profile, which applies at every load to an option that was not set
on the command line: measured on a player launched by dev 713afbf's argv and
driven by this tree, a `[protocol.http]` profile with `save-watch-history`
wrote the credentialed path to the watch history, one with
`load-unsafe-playlists` let a server's nested playlist truncate a scratch
file, and one with `load-select` let select's subtitle-line key fork `ffmpeg`
with the URL. Only the TLS options are counted by the third reading, so such
a player is migrated, not stopped, and those three stay open until it is
replaced -- the owner's DR7 question. **[2026-10-29, lane-p1b: closed by the
lead's decision.]** The third reading counts a per-file profile that touches
ANY pinned option, an alias of one included (`script`, `watch-later-directory`,
`script-opt`), so that player is stopped (W18). A player of THIS release reads every pin
set from the command line, so none of that applies to it.

**What a user sees.** Their own profile-cond auto-profiles do not apply in the
IPTV player; nor does a `script=` line, `input-commands`, watch history, a
log file, `reset-on-next-file`, `osd-playlist-entry=filename` or
`load-unsafe-playlists` from their mpv.conf. The select menu (`g` and a
letter, and the OSC's right-click menus) is gone from this player. A token
for any reserved or pinned option is refused with the existing footer line.
A `--demuxer-lavf-o` workaround keeps working unless it names a TLS key.
`--http-proxy` draws a footer warning. Every player running when the user
upgrades rebuffers once when the new shell adopts it, and one whose mpv.conf
carries a per-file profile that touches a TLS option is stopped instead.
**[2026-10-29, lane-p1b.]** And: a channel whose address is itself a plain
`.m3u` or `.pls` redirector no longer plays, told as "The address sent a
playlist file or a web page, which the player does not open"
(`Model.unopenedFormatSentence`, which outranks the log tail for mpv's
`unrecognized file format` and for nothing else); `Ctrl+V` in the player no
longer appends the clipboard, and a URL dropped on it is not loaded; the
OSC's title middle-click does nothing; a `--script-opts` token that sets an
OSC `*_command`, `*_mbtn_*` or `*_wheel_*` key or carries `${` is refused by
the existing footer line (every other key passes); `--drag-and-drop` and a
`--demuxer-lavf-o` protocol list are refused; `--rtsp-transport=udp`,
`udp_multicast` or `lavf` draws "opens ports on this computer that anyone can
send to", and a `--demuxer-lavf-o` carrying `http_proxy` draws the handoff
warning (D-SINK-59); a player started by an earlier version whose
`reset-on-next-file` is set, or whose mpv.conf has a per-file profile that
touches any pinned option, is stopped on the first probe instead of migrated
(press Enter for a fresh player).
**[2026-10-29, lane-p1c.]** And: the console is gone from the player (the
`` ` `` key and `script-binding console/enable` do nothing); `--prefetch-playlist`,
`--load-console` and its alias are refused by the footer line, as is a
`--demuxer-lavf-o` token naming a format list or hls's `seg_format_options`;
a channel whose server answers with a format the player does not take (4.12.2)
fails with the sentence above; and a player started by an earlier version is
given the format list and loses a `seg_format_options` key on its first
probe, which is the rebuffer 4.5.1 already describes.

### 4.12.2 The demuxers that open what a stream server names (2026-10-29, lane-p1c, D-SINK-62)

**What was wrong.** D-SINK-55's protocol list governs what libavformat may
open BELOW a demuxer, and that list has to hold tcp and tls, because http and
https run over them. So a demuxer that opens the URLs its CONTENT names opens
`tcp://0.0.0.0:P?listen=1` as readily as a segment. rc-p1b found the one
that does it from a stream server's answer: FFmpeg's IMF demuxer, chosen by
the probe at score 100 from the bytes `<CompositionPlaylist` and
`ContentTitle>` (as `text/xml`, and as `video/mp2t` under `.ts`), fetches
`ASSETMAP.xml` beside the CPL and opens every asset URI in it -- a
`tcp://`, `tls://` or `listen=2` asset bound 0.0.0.0 -- and an ffconcat file
naming the CPL by a relative name reaches it too. Measured again on sec-int
124589e through its own `apply_channel` inside `unshare -rn`: all four IMF
forms bound, the relative ffconcat bound, and with the user's `safe=0` past
the filter an absolute ffconcat entry bound; a forced
`--demuxer-lavf-format=concat` bound as well.

**The lever: FFmpeg's `format_whitelist`, as the player's last word.** It is
an AVFormatContext option, so it travels in `demuxer-lavf-o` beside the
protocol list (`--demuxer-lavf-o-append=format_whitelist=...` in the pin
block). FFmpeg checks it in `avformat_open_input` against the format the
probe CHOSE -- or the one a caller forced -- after the probe and before the
demuxer reads a byte (`Format not on whitelist`), so a format off the list
fails closed whatever its score; and `ff_copy_whiteblacklists` copies it into
every nested context (read in the n9.0.1 source: hls's segment and
subtitle contexts, dash's representations, concat's and imf's children,
vobsub's, avi's GAB2 subtitles, rtsp's asf and RealMedia payloads; imf then
narrows its own children to `mxf`). Measured that it binds at every depth:
with the list less one nested format, the stream that needs it fails --
HLS over TS without `mpegts`, fMP4 HLS and DASH without `mov`, packed-audio
HLS without `aac`, `ac3` or `eac3`, and an HLS channel with a WebVTT
rendition without `webvtt` (the whole channel fails, not only the subtitle
track, which is why `webvtt` is on the list); an rtsp channel without
`rtsp`, its loadfile's per-file protocol widening included. The list is read
back exactly before every load and appended on adoption, and a token naming
`format_whitelist` or `format_blacklist` is refused (4.12.1).

**The list, from what IPTV carries:** `hls,dash,mpegts,mov,matroska,flv,
live_flv,mp3,aac,ac3,eac3,ogg,flac,asf,rtsp,webvtt`. `mov` matches FFmpeg's
`mov,mp4,m4a,3gp,3g2,mj2` and `matroska` its `matroska,webm` (FFmpeg
compares each name of a list with each). Three are beyond the brief's list,
each for a measured reason: `dash` (a DASH channel played on sec-int, and
IPTV lists carry them; bounded exactly as hls is, below), `live_flv` (FFmpeg
picks it over `flv` for an FLV whose metadata says NGINX RTMP, which is what
an nginx HTTP-FLV live channel serves -- measured with such a file) and
`flac` (an internet-radio form; it opens nothing). Off it, and a cost:
raw H.264 or HEVC, MJPEG and multipart MJPEG (an IP camera's), AVI, MPEG-PS,
WAV and RealMedia over rtsp. HLS needs no raw-video demuxer: its segments are
TS, fMP4 or packed audio (measured: an HLS channel of each plays), and the
timed-metadata path is `hls` itself (it reads a packed segment's ID3
timestamp before handing the rest to `aac`, `ac3` or `eac3`) and `mpegts`
(an ID3 stream inside TS is one of its streams).

**The rule-15 search.** Every demuxer this FFmpeg lists (`ffmpeg -demuxers`:
377, eleven of them devices) that opens another URL or file from what it
reads, found by searching the n9.0.1 source for `io_open`,
`avformat_open_input`, `avformat_alloc_context`, `ffurl_open_whitelist` and
`av_probe_input_format` in libavformat (read-only, on github.com), with
`mov.c`, which is too large for that search, read by hand:

| Demuxer | Opens what | Here |
|---|---|---|
| imf | ASSETMAP.xml beside the CPL, then every asset URI it names, any scheme the protocol list admits | excluded (W19) |
| concat | every file its ffconcat list names: relative names on its own host under `safe=1`, any URL under `safe=0` | excluded (W20, W25) |
| sdp | rtp/udp at the addresses and ports the SDP names | excluded, and the protocol list has no rtp (W12) |
| rtp | its own URL (probed by the name `rtp:` only), then rtp built from the packets | excluded; an `rtp://` channel is played by mpv's stream layer as `mpegts` (measured) |
| sap | the SAP multicast address, then an sdp child (probed by the name `sap:` only; read in the source) | excluded |
| vobsub | its own URL with `.sub` for its extension, same host | excluded (sec-int fetched the `.sub` of an index a server answered with; the tree fetches nothing past the index) |
| mlv | up to 100 siblings of its own URL, same host (read) | excluded |
| image2 | numbered siblings of its own URL (probed by a `%d` in the name) | excluded; not reached through mpv's probe on sec-int either (measured) |
| dvdvideo | a DVD structure at its own path; forced only (read) | excluded |
| avisynth | imports its own path as an AviSynth script (extension `avs`); the library is not installed here | excluded |
| vapoursynth | evaluates the stream as a VapourSynth Python script; forced only (its probe answers 0; read); the library IS installed here | excluded, which also refuses a user's `--demuxer-lavf-format=vapoursynth` |
| lavfi (a device) | a filter graph whose movie sources open any URL; forced only (read) | excluded |
| the other devices | local capture; forced only | excluded |
| hls | playlists, variants, keys, init sections and segments, over http(s), data and crypto only (its own scheme check; `file` is not on the protocol list); each segment through a child with the lists copied and an opener that refuses every further open, and an extension check (`extension_picky`) | admitted, bounded so; the LAN reach of a segment is 19.2's residual |
| dash | the manifest's segments over http(s) only (its own scheme check); each representation through a child with the lists copied and an opener that refuses every further open | admitted, bounded so (W21: a tcp BaseURL bound nothing, on sec-int too) |
| rtsp | its own server's control connection and redirects (rtsp only), RTP over udp only when the user chose that transport (D-SINK-53's per-file widening); asf (WMS) and RealMedia payloads through children read from memory (read) | admitted (measured: over TCP and with the user's udp); RealMedia over rtsp would fail, `rdt` being off the list (read, not measured) |
| mov | external data references: off by default (`enable_drefs`), an absolute one only with `use_absolute_path` too, and a dref path has every `:` turned into `/` as it is read, so it is a local path | admitted; with both user keys past the filter the absolute reference was opened as `file`, which the protocol list refuses (measured) |
| avi | GAB2 subtitles through an srt or ass child read from memory (read) | excluded (not IPTV; opens nothing) |
| every other demuxer | nothing beyond its own stream, by the search | excluded unless listed; the listed ones open nothing |

**Every admitted channel kind, played through the tree's own
`apply_channel`** (mpv 0.41.0 / FFmpeg n9.0.1, windowless, inside `unshare
-rn` with multicast routed onto lo, crash journal 81 before and after every
run; the lane's format rig): http and https TS, an HLS master and variant
over TS (http and https), fMP4 HLS, packed-audio HLS of AAC, AC-3 and E-AC-3
with ID3 timestamps, HLS with a WebVTT rendition (the subtitle track there),
progressive MP4, MKV, FLV over http, an nginx-style live FLV, FLV over rtmp
(an `ffmpeg -listen` server), an Icecast-style MP3 and AAC stream, Ogg
Vorbis and Opus, FLAC, ASF over http, DASH, rtsp over TCP, srt as caller,
udp and rtp multicast: each played (`time-pos` moved), as the same format
FFmpeg chose on sec-int. rtmps, mms and mmsh reached their servers as before
(no server of theirs plays here), and the user's `--rtsp-transport=udp` bound
its RTP/RTCP pair, as asked.

**Every route refused** (nothing listens, on the tree; on sec-int as shown):
IMF with tcp, tls and listen=2 assets and as `.ts` (sec-int: all four bound),
and with an http asset on another port (sec-int: fetched there); ffconcat
relative to the CPL (bound), absolute under the user's `safe=0` (bound), and
naming another port (fetched under `safe=0`); a forced concat (bound); phase
1b's twenty SDP answers (five `c=` lines under four servings; sec-int: none
bound already, the protocol list; now also refused as a format); DASH with a
tcp, tls or udp BaseURL (none bound on either); an absolute mov reference,
with and without the user's two keys; an image2 pattern; a vobsub index
(sec-int fetched the `.sub`); and rc-p1b's nested-playlist battery -- M3U as
.m3u and as .ts, m3u8 without tags, a bare list, PLS, ASX, CUE, EDL as .edl
and as .ts, a redirect to an M3U, and an HLS segment that is itself an HLS
playlist, an ffconcat list or an IMF CPL. A refused format ends the load
like any unrecognised one, `unrecognized file format`, which the shell
already words (`Model.unopenedFormatSentence`).

**What it costs.** A channel whose server answers with a format off the list
stops playing and reads "The address sent a playlist file or a web page,
which the player does not open": raw elementary video, an MJPEG camera, an
AVI or MPEG-PS file, a WAV stream, RealMedia over rtsp. And a
`--demuxer-lavf-format` naming such a format fails the same way.

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

### 4.15 TLS verification on the player (D-SINK-13)

**What was wrong.** mpv's `--tls-verify` is a flag whose default is `no`
(`mpv --list-options`, mpv v0.41.0 / FFmpeg n9.0.1 / OpenSSL 3.6.4 on this
machine), so mpv passes `tls_verify=0` down to FFmpeg's TLS layer and the peer
certificate is never checked. The base argv (section 6, and `buildMpvArgv` with
its helper mirror) never said otherwise, while `apply_channel` (4.11) sets the
three provider header
properties and then `loadfile`s the `https` stream URL over exactly that
connection. An on-path attacker could therefore impersonate the provider,
replace the media, and collect the credentials carried in the URL and in the
headers. Raised by the marketplace maintainer against the SHIPPED 0.12.1
(22ba4ce), omacom/omarchy-plugin-marketplace#10323. The exposure is confined to
this one sink: the helper's own playlist, EPG and probe fetches go through
`urllib`, which verifies by default and is not disabled anywhere, and they
refuse a self-signed certificate today (measured). The claim to make is
therefore "everywhere except the player", not "now verifies everywhere".

**Specification: FIVE layers on the launch argv, and TWO over IPC.** All
seven are REQUIRED and each answers a different question. The lead measured
every row cited here on 2026-10-07
against a local TLS server (self-signed, and signed by a generated CA) serving
a 106,220-byte MPEG-TS, driven by the real shipped argv taken out of
`mpv_launch_argv` rather than retyped, with `curl` as the discriminating
control; the evidence is the D-SINK-13 row in `docs/STATUS.md` and the
write-up in `docs/QA-RESULTS.md`. **Two rigs, not one:** rows 1 to 5 are that
argv rig, and rows 6 and 7 were measured the same day on a different one -- a
running player driven over its IPC socket, with an attacker's own request log
as the discriminator -- so their evidence is the D-SINK-16 row on the board
and not the runs described in this paragraph.

| # | Layer | Job | Measured basis |
|---|---|---|---|
| 1 | `--tls-verify=yes` in the base argv, beside `--load-scripts=no` | The intent is where a reader of the argv looks. Nothing else | Today's argv plays a self-signed certificate (exit 0); the same argv plus this token exits 2 on `tls: Peer certificate failed verification` |
| 2 | `--tls-verify=yes` re-asserted as the FINAL element of the COMPOSED argv, after the filtered user `mpvArgs` | The layer that actually binds. A later command-line token beats an earlier one, so layer 1 alone is undoable | `yes ... --tls-verify=no ... yes`, `yes ... --no-tls-verify ... yes` and `yes ... --profile=evil ... yes` all exit 2. Without the trailing token all three of those PLAY |
| 3 | `--tls-verify` in `MPV_RESERVED`, matched in both the `--tls-verify=no` and the `--no-tls-verify` forms | Makes it honest. A direct attempt is refused LOUDLY, with the existing dropped-token warning, instead of being silently outvoted by layer 2 | The existing `--no-` rule in `filter_mpv_args` / `splitMpvArgs` already covers the second form once the name is on the list |
| 4 | `--tls-ca-file` left UNRESERVED | The targeted escape for a provider with a self-signed or private-CA certificate, and the only one offered | A certificate signed by a generated CA plays with `--tls-verify=yes --tls-ca-file=<that CA>`, and still plays as a user token behind layer 2's trailing re-assertion |
| 5 | `--stream-lavf-o` in `MPV_RESERVED`, one entry covering all six spellings because `mpvOptionBase` strips the list suffixes (D-SINK-15) | The bypass layer 2 CANNOT reach: it hands `key=value` straight to libavformat for the STREAM, and FFmpeg's own AVOption `tls_verify` is a different knob arriving at the same place, so our last token does not outvote it. This one can only be closed by the reserved list, which is why that list is load-bearing again here | With BOTH `tls-verify` tokens in place, `--stream-lavf-o=tls_verify=0` PLAYED the attacker's self-signed stream (exit 0, the GET in the attacker's log), and so did the `-add`, `-append` and `-set` forms. `--demuxer-lavf-o=tls_verify=0` did NOT bypass (exit 2, refused) and is therefore NOT reserved, recorded as measured rather than reserved on suspicion. **[2026-10-29, D-SINK-43: measured on a DIRECT stream only. For HLS (and by reading DASH) it played the attacker's segment with both tokens in place; layers 8 and 9 below, 4.12.1]** |
| 6 | `tls-verify` and `stream-lavf-o` asserted over IPC in `apply_channel` before EVERY `loadfile`, and NOT best effort: a load that cannot be made safe is refused and reported (D-SINK-16, 4.11) | Layers 1 to 5 bind a player this shell launched. This one binds the process actually about to be handed a URL, whoever launched it and whenever that was. It is the one wire sequence `play` and `player start` share | `tls-verify` is readable AND writable over the socket, and after `set_property tls-verify True` the same process fetched nothing from the attacker: GETs 1 before, 0 after, with a positive control still playing |
| 7 | Adoption migrates both properties, reads them BACK, and re-establishes the current channel; a player that cannot be made safe is stopped rather than fed (D-SINK-16, specified in 4.5.1) | argv is fixed at exec, so no argv layer reaches a player that was already running when the plugin was updated -- the exact case the first fix missed, while the shell went on sending that player new headers and new credentialed URLs | The same migration runs as layer 6. What is NOT measured is whether an already-open stream picks the change up for its ongoing fetches, which is why the reload is in the layer and not an argument that it is unnecessary |

**[2026-10-29, D-SINK-43/44: two more layers, both REQUIRED.]**

| # | Layer | Job | Measured basis |
|---|---|---|---|
| 8 | The trailing pin block (4.12.1): `--stream-lavf-o-clr`, `--demuxer-lavf-propagate-opts=yes`, `--demuxer-lavf-o-append=tls_verify=1`, `--load-auto-profiles=no` and (2026-10-29, the recheck) `--player-operation-mode=cplayer` among the pins, before the final `--tls-verify=yes` | Makes the libavformat lists COMMAND-LINE-SET, so no per-file profile replaces them, gives FFmpeg's own `tls_verify` the last word for every segment open, and keeps auto_profiles.lua from ever loading and the `[pseudo-gui]` profile from applying after the command line | Five ways per pin -- a contrary token, a plain mpv.conf line, a `[protocol.*]` profile, a profile-cond profile, a named profile: on dev 713afbf the attacker got the GET through `demuxer-lavf-o` all five ways, through `stream-lavf-o` by the two per-file profiles and through `tls-verify` by the profile-cond one; on the tree, 0 GETs in all fifteen |
| 9 | The third reading over IPC, `unpinned`, before every load and on adoption: the TLS entries of `demuxer-lavf-o` (removed by key), `load-auto-profiles` (set off), and the per-file profiles that could set a loose TLS option after the read-back (not fixable: the load is refused). **[2026-10-29, lane-p1b: and the demuxer's protocol whitelist, which must read exactly the pinned list (appended when absent, D-SINK-55); `reset-on-next-file`, which must be empty and is never written (D-SINK-60: mpv restores what it backed up at the playing file's start inside the next load); and per-file profiles touching ANY pinned option]** **[lane-p1c: and the demuxer's format list, which must read exactly the pinned list (D-SINK-62), and no `seg_format_options` key (D-SINK-64), removed before the load]** | `verifyhost=<the attacker's own name>` in `demuxer-lavf-o` is a key the trailing pin cannot outvote, and a player started without the pins has no command-line-set lists | `--demuxer-lavf-o=verifyhost=evil.test` past the filter, with the tls_verify pin in place: on dev the attacker's certificate for its own name was accepted and its segment played; on the tree the key is removed before the load and the reopen is refused |

Layers 1 to 5 are blind to a player this shell did not launch, every one of
them, and that blindness is what D-SINK-16 is: the fix was complete for new
players and absent for adopted ones, and adoption is a designed path, not an
edge case (section 1). Layers 6 and 7 are the correction -- 6 at the sink on
every load, 7 at the only path that meets an older player. Layer 5's row was
missing from this table while the sentence above it already said five; it
dates from D-SINK-15 and is added here with 6 and 7 rather than left to be
inferred from the reserved list.

Layer 2 is not a duplicate of layer 1 and must not be tidied away as one.
That is the whole finding of the addendum to the measurements: `--profile`
carries arbitrary options, including `tls-verify=no`, from the user's own mpv
config, and a profile named in `mpvArgs` lands after the base argv. Both
mechanisms were proved live before being accused -- against a fake `HOME` and
`XDG_CONFIG_HOME`, an `mpv.conf` saying `tls-verify=yes` with no argv option
refused the self-signed certificate, and `--profile=good` refused it -- so the
bypass is a measurement and not an inference. `--profile` is deliberately NOT
reserved: layer 2 makes it harmless, profiles are a legitimate mpv feature, and
reserving it would still leave whatever indirection nobody has enumerated.
Anyone reaching for the reserved list for `--profile` should stop here.

A trailing token has one obvious attack and it is closed by construction: a
bare `--` would make every later token a FILENAME, and the shipping argument
filter cannot pass one -- `MPV_ARG_RE` is `^--[a-z0-9][a-z0-9-]*(=.*)?$` and
calling `filter_mpv_args(["--"])` returns `--` in the rejected bucket
(measured by calling it). The reverse direction is closed too: a user's own
`~/.config/mpv/mpv.conf` saying `tls-verify=no` does NOT beat our command line
(exit 2, refused), so a pre-existing config cannot undo the fix. **[2026-10-29,
D-SINK-44: true of a PLAIN line only. A `profile-cond` profile in mpv.conf
applies at every load over the command line (auto_profiles.lua runs
`apply-profile`), and a `[protocol.https]` profile replaced `stream-lavf-o`
and `demuxer-lavf-o`, which nothing set on the command line; each fetched
from the attacker. Closed by layers 8 and 9.]**

**Compatibility, and the cost.** With `--tls-verify=yes` and no
`--tls-ca-file`, a real public certificate still verifies against the system
store: against a public `https` host the only remaining failure was the
demuxer's `Failed to recognize file format`, identical to the control run with
no TLS options at all. So the fix is free on a normal provider. It is NOT free
for everyone, and the ruling accepts that rather than hiding it: a user whose
provider presents a self-signed certificate can no longer play by switching
verification off wholesale, and must name that provider's CA with
`--tls-ca-file` instead. That is a smaller blast radius for the same
capability, which is why the ruling went this way.

`--tls-cert-file` and `--tls-key-file` are CLIENT certificates, a different
mechanism, and are untouched by this round.

**Where it is pinned.** Both mirrors -- `Model.buildMpvArgv` and the helper's
`mpv_launch_argv` -- carry layers 1 and 2, and both reserved sets carry layer 3;
the shared vectors in `tests/fixtures/player-argv.json` are the one pinning for
all of it, including the composed-argv case where a user token tries to undo it
(engineering rule 12: one fixture, both implementations). An assertion that the
token appears somewhere in an array is a restatement of the implementation and
does not count under engineering rule 14; what counts is calling the composition
with hostile `mpvArgs` and asserting the LAST element, and observing the sink
itself in the harness scenario (QA.md section 3.1).

Layers 6 and 7 cannot be pinned by a vector over an argv, because neither
touches argv. What pins them is the decision: the verdict taken from the
read-back, and the refusal that follows an unsafe one, belong in `Model.js`
with a mirror in the helper and ONE shared fixture, so a test calls the
shipping decision instead of restating it (engineering rules 12 and 14). The
fixture has to carry the FAILURE rows as well as the clean ones, and the
IPC fakes have to answer the way the measurements say mpv does -- a fake whose
`set_property` always succeeds, or whose read-back echoes whatever was just
written, is more forgiving than the real thing and proves nothing (engineering
rule 10). The sink itself is the harness scenario's, against a server
presenting a certificate nobody signed, on a player launched WITHOUT the
tokens so that the migration has something to migrate; a scenario that cannot
be shown red against the code as it shipped in 0.13.0 is not evidence. Which
scenario and which case ids are QA's to fix, not this section's.

## 5. Hard requirements

| # | Requirement | Status | Mechanism |
|---|---|---|---|
| 1 | Exactly ONE player instance. Never a second window | **kept (strengthened)** | Three layers: a `/proc` scan on the exact `--input-ipc-server=<abspath>` token plus uid is the authoritative existence check (never `connect()`, which succeeds through the listen backlog against a wedged mpv); `flock` with an inode re-check serialises launchers and survives an unlink-and-recreate; `player start` is idempotent - a live answering player is adopted and zapped, not duplicated. Only one code path (`spawn_detached`) ever execs mpv. If the scan ever finds several, the one that answers the socket is kept and the rest are laddered down. A spawn whose socket never binds is reaped by the helper that created it using the pid read back over a pipe, so an un-killable window cannot exist and cannot multiply. QML's `playerUp` is advisory UI state and is **never** a spawn gate |
| 2 | Zapping reuses the window via `play --id <id> --socket <s>` -> title / force-media-title / UA / referrer / header-fields -> `loadfile <url> replace` | **kept** | `cmd_play`'s wire sequence and CLI surface are unchanged; its body is factored into `apply_channel()` and shared with `player start`, so first-play and zap become one implementation instead of two. All 23 `tests/test_mpv.py` cases pass unmodified. `pendingPlayId` burst coalescing (`Service.qml:314-318`) and the `previousPlaying` rollback are unchanged. `play` gains optional `--scope`/`--since` and returns `entryId`, both additive. Verified: `loadfile ... replace` while playing emits `end-file{reason:"stop"}` then `start-file` on one pid, window intact. **Amended by D-SINK-16:** the two TLS properties are asserted on this same sequence before the `loadfile`, and unlike every other element of it they are not best effort -- an assertion that cannot be made safe refuses the load (4.11, 4.15 layer 6) |
| 3 | Window class `omarchy-iptv`, title = channel name, `$>` raw prefix on `--title` (force-media-title NOT expanded) | **kept** | `--wayland-app-id` stays on argv (app_id is fixed at surface creation); title and force-media-title move to IPC, where the `$>` marker is verified stored literally and `force-media-title` verified non-expanded on 0.41. `Model.MPV_RAW_PREFIX` / `mpvWindowTitle` and the helper mirror untouched; `--title` stays reserved. Hyprland matching and `focusPlayerArgv` are unaffected by who spawned the client |
| 4 | Stop immediate in the UI; quit -> SIGTERM after 2 s -> SIGKILL after 2 s (D-LIVE-17); never leaves an orphan | **weakened -> PO-2** | The ladder is **strengthened**: `nowPlaying = null` still clears synchronously; the rungs run inside one detached helper so they cannot be starved by a busy control channel and complete even if the shell dies mid-ladder; the pid comes from `/proc`, so a wedged mpv - the case the ladder exists for - is now reachable, where an IPC-only pid source could never signal it; pid + start time + cmdline are re-verified before each signal. Timeline unchanged at quit@0 / TERM@2 s / KILL@4 s. **What weakens:** disabling or removing the plugin no longer kills the player through `~Process()`. Section 4.14's owner-claim orphan-check covers it best-effort; a SIGKILLed shell that never returns leaves the player until logout (not a regression - the same is true today - but it is a longer window). **PO-2 asks whether best-effort plus a documented `player stop` is acceptable** |
| 5 | Health check every 10 s via helper `status`; two consecutive failures relaunch once; stale sockets unlinked | **kept** | Interval, `Model.healthTick`, the busy-skip counter, `Model.statusHealthy`, the two-strike branch and the one-relaunch-per-player rule are all unchanged. The timer's gate becomes `playerUp \|\| nowPlaying !== null` so it can never be gated off by a stale flag. The verdict issues `player restart --from term` - one lock acquisition, ladder then spawn - removing the stop/start race two detached calls would have. Stale-socket unlinking gains three more callers (probe, start's reconcile, stop's settle) and keeps its `S_ISSOCK` guard and both existing tests. Socket EOF adds a sub-second primary death signal on top of the poll |
| 6 | Stream failure or unexpected exit raises a notification naming the channel, stderr redacted to hosts (S-01/D-QA-01), channel marked failed for the session | **weakened -> PO-3** | Live path **improved**: control flow comes from `end-file.reason` + `file_error` rather than an exit code, which separates a deliberate stop from a real error and ignores `redirect`; failure text comes from `request_log_messages "error"`, redacted by `redact_urls()` in python **before** it crosses into QML and then again by `rememberStderr`'s `Model.redactUrls`; a cold-start first-channel failure is caught by `player start`'s own 3 s window, so the commonest real failure cannot be missed; `notifyArgv`, `NOTIFY_IDS`, `withFailed` and the 5-line tail are untouched; the entry gate fails open so a missing `entryId` never suppresses a toast. **What weakens:** a failure that happens while no shell is attached cannot be toasted at all - `org.freedesktop.Notifications` is owned by quickshell itself and is not D-Bus activatable, so nothing on this machine can notify while the shell is down. **PO-3 asks whether to mark the channel failed silently on reattach (recommended) or raise a stale toast** **[Amended 2026-10-28, D-PLY-32: "stream failure" here means a failure of the STREAM. A `player start|restart` reply that refuses is no verdict on it -- a stream that fails to load arrives as an ok reply with `firstLoad.state` "failed" (signal 1 of 4.8) or as the socket's end (signal 3), never as a refusal -- so the refusal tail of `handlePlayerResult` asks `Model.playerStartFailure(code)`. `local` (every code but one: the runtime folder and its lock, the socket path, the spawn, the TLS read-back of 4.15, the player's connection, the cache, `busy` and `no_socket` with their retries spent, main()'s and the stub's refusals, an empty reply) records `lastError`, retires the session record as before, marks NOTHING (`failedAt`, `failed.json` and `lastFailedId` untouched) and raises `NOTIFY_IDS.localPlayFailure` (74021, `Could not start playback`, the same body) once per episode. `channel` (`unsupported_scheme`, the entry's own URL) keeps `raiseStreamFailure`: the mark and `Stream failed`. Until D-PLY-32 every refusal marked the channel, so a broken runtime folder turned every channel tried red and took each out of the zap ring for the mark's 14 days. The two death signals are unchanged; 4.8's "no `end-file` at all" row still marks (see the note under that table).]** **[Amended 2026-10-28, D-PLY-33 (the owner: "a player death with NO end-file stops marking the channel"): "channel marked failed" now holds only for a load mpv said failed -- an `end-file` error for the channel's own entry (4.8, as amended). An "unexpected exit" with no such `end-file` -- a crash, an external or out-of-memory kill, D-PLY-27's VO abort, a `stop` and then a death -- still raises a notification naming the channel (F4), `Playback stopped` / `“<name>” stopped unexpectedly` (replace id 74022), and marks nothing; its text is that sentence, not the stderr tail. PO-3 follows the same rule: a session record found with no player is a death nobody saw an `end-file` for, so the reattach clears the record and marks nothing (it told nothing before either). 4.5's `running:false` row and section 12's PO-3 row still say "mark" and are superseded on that point by this bracket. Not reached yet: signal 1's first-load window, whose `failed` cannot tell an `end-file` error from a closed connection, still marks (4.8's note).]** **[Amended 2026-10-28, D-PLY-36, D-PLY-37 and the owner's "refresh on every try" (after D-HOST-5): signal 1 is now reached -- `player start`'s reply says whether its window saw an `end-file` error (marked) or mpv close the connection (`playerStopped`, unmarked; 4.3, 4.8). An `end-file` error that names an output of this machine (the audio or video output could not be opened) is told as `outputFailed` (`Audio output failed`, replace id 74023, "“<name>” stopped · This computer's audio output could not be opened") and marks nothing, whichever detector sees it. The local refusal above (`localPlayFailure`, 74021) is raised on EVERY refused try, not once per episode: each post sends back the id the notification server returned for the last one (`Model.notifyPost`, D-HOST-5), so the tries refresh ONE card in place. D-PLY-41: it is told whenever the play was the user's and no stop took it back (`userStopped`); a stop from before the play that is still settling no longer silences it.]** |
| 7 | Per-channel `#EXTVLCOPT`/`#KODIPROP` headers applied and CLEARED between channels | **kept (strengthened)** | `header_properties()` unchanged - it always sets all three properties, so a header-less channel actively resets the previous one's. The only change is that the **first** channel now goes through it too, removing the one channel today whose argv-supplied headers nothing ever clears. `loadfile`'s per-file options were evaluated and rejected: values must be strings and `http-header-fields` then serialises comma-separated, so a playlist-supplied value containing a comma would split into two wrong headers - the hazard `Model.js:1223` already documents |
| 8 | User `mpvArgs` still apply, reserved-option filter intact | **kept (strengthened)** | `splitMpvArgs` and the nine existing `MPV_RESERVED` entries are unchanged, including the `--no-` rule and D-QA-11 case-sensitivity; ordering preserved so `--ytdl=yes` still wins. Ten additions (4.12), each a durable URL-on-disk or URL-on-screen path reachable from the settings panel today. Tokens travel as repeated `--mpv-arg`, never joined, and are re-validated by a python mirror pinned equal by a parity test |
| 9 | argv-only launching. No shell interpolation, no sudo, no third-party runtime dependency. Helper stays stdlib-only python3 | **kept** | Four hops, four argv vectors: QML -> helper is the existing `["python3", helperPath, ...]` `Process` command list and `Quickshell.execDetached(list)`; helper -> mpv is `os.execvp("mpv", argv)` with a literal argv[0]; helper -> notification is never used. No `bash -lc`, no `eval`, no `systemd-run`, no `uwsm-app` (rejected explicitly for its `eval "$CMDLINE"`), no `hyprctl exec_cmd`. New stdlib imports only: `fcntl`, `signal`, `errno` (`socket`, `stat`, `os`, `time`, `json` already imported) |
| 10 | Socket under `$XDG_RUNTIME_DIR/omarchy-iptv/` with 0700/0600 modes | **kept** | Paths unchanged. The directory is 0700 from `mkdirProc` **and** from `ensure_private_dir()` inside every `player` verb, because mpv fails completely silently with no parent directory. mpv sets the socket 0600 itself (verified under `umask 0022`). The one new file, `player.lock`, is `O_CREAT\|O_RDWR` 0600 in the same directory and contains only a sequence number. No log file, no `player.json`, nothing else added. **Amended by PO-11 and by D-PLY-10 / CL2:** the player's own key bindings and its own caches now write into named 0700 directories instead of inheriting `$HOME` and `$XDG_CACHE_HOME` - `watch-later/` and `shader-cache/` under the runtime directory, ephemeral, and `screenshots/` under the state directory, durable because the user asked for that file. `ensure_player_dirs()` creates all three, because mpv would otherwise create them itself at 0755 |
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
    --tls-verify=yes
    <filtered user mpvArgs...>
    --tls-verify=yes
```

The two `--tls-verify=yes` are both deliberate and section 4.15 is the
specification: the first states the intent where a reader looks, the second
binds it, because a later command-line token beats an earlier one and a user
`--profile` carries arbitrary options. Deleting the trailing one as a
duplicate re-opens D-SINK-13, measured.

This block is the M2-02 argv. Later rounds added tokens to the same base and
did not rewrite it here: `--load-scripts=no` (D-SINK-4), `--screenshot-dir`
and `--watch-later-dir` (PO-11), `--gpu-shader-cache-dir` and
`--icc-cache-dir` (D-PLY-10 / CL2), and `--gpu-sw=yes` (D-PLY-27, section
4.12: the one base token a user's own `--gpu-sw=no` is meant to beat, so it
sits before the user's tokens and before the first `--tls-verify=yes`, and
is never re-asserted). `Model.buildMpvArgv` and the helper's
`mpv_launch_argv` are the current list, pinned to each other by
`tests/fixtures/player-argv.json`.

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
direction. Residual, disclosed rather than hidden: `--id` on the helper's
argv is a per-zap record of *what* the user is watching **[2026-10-29,
lane-p2a, D-SINK-48: no longer -- the shell hands `--id`, `--cache-dir` and
`--scope` over the environment (4.3's amendment); a `u:` id hashes a stream
URL, so it was a check on a guessed credential and not only a record]**, and `Model.notifyArgv`
puts the channel name on `omarchy-notification-send`'s argv on each failure;
both are readable by other local accounts through `/proc/<pid>/cmdline` (0444,
`/proc` mounted without `hidepid` here) for the life of those short-lived
processes, and neither is a credential. **[corrected 2026-09-25, D-PLY-19]**
This paragraph named `--force-media-title` as part of that residual for
eleven days after section 4.11 fixed it to the constant `IPTV`; the launch argv
carries `--force-media-title=IPTV` and the option is reserved, so it reveals
nothing, and the channel title reaches the player only over IPC. The README's
Playback notes and CHANGELOG 0.3.0 name both real residuals.

**Files.** New artifacts, complete list:

| Path | Mode | Contents | URL-bearing |
|---|---|---|---|
| `$XDG_RUNTIME_DIR/omarchy-iptv/player.lock` | 0600 | `{"schema":1,"seq":N,"verb":"start","at":1758000100}` | no |
| `$XDG_RUNTIME_DIR/omarchy-iptv/watch-later/` | 0700 dir, 0600 files | mpv's own resume record, written by its `Q` key (PO-11). Ephemeral: a resume position for a live stream is never worth keeping | the header line names the stream, which is why `--watch-later-dir` is reserved and the directory is private and ephemeral |
| `$XDG_RUNTIME_DIR/omarchy-iptv/shader-cache/` | 0700 dir, 0600 files | mpv's compiled shader cache and ICC cache, redirected out of `$XDG_CACHE_HOME/mpv/` (D-PLY-10, ruling CL2). Ephemeral, content-free, regenerable | no - it is keyed to the GPU and the shader source, not to anything that was watched |
| `$XDG_STATE_HOME/omarchy-iptv/screenshots/` | 0700 dir, 0600 files | mpv's own `s` key (PO-11). DURABLE on purpose: the user asked for that file | no |
| `$XDG_STATE_HOME/omarchy-iptv/state.json` key `session` | 0600 (existing file, existing mode, `O_EXCL`-created by `state init`) | `{"id":"t:bbc1.uk","name":"BBC One HD","at":1758000123}` | no |

Nothing else. No `player.json`, no log file, no systemd unit, no drop-in.
`--log-file` and `StandardError=append:` are rejected in section 3 precisely
because they would write credentials to disk. The three directories above are
the player's own key bindings and its own caches, named rather than
inherited: without that they land in `$HOME` and `$XDG_CACHE_HOME/mpv/`,
outside every list this plugin publishes, which is exactly what D-PLY-7 and
D-PLY-10 were.

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

**The sink class this enumeration had no category for (D-SINK-13, 2026-10-07).**
Every heading above asks where the URL and the headers are WRITTEN -- a command
line, a file, a unit name, an environment variable, a log. All of those answers
stand. The question none of them asks is who the URL and the headers are SENT
TO, and the answer was "whoever answers on that address", because the player
did not verify the peer's certificate (section 4.15). The credentials never
left the 0600 files and the 0600 socket on this side and were handed to an
unauthenticated peer on the other, which is why an enumeration of local sinks
could be complete and the system still be wrong. The claim at the head of this
section is unchanged and remains true as written; it was never the whole claim.
Closed by the layers in 4.15 -- five on the launch argv in that round, and two
more over IPC after D-SINK-16 found that not one of the five reaches a player
that was ALREADY RUNNING when the plugin was updated, while the shell went on
sending that player new provider headers and new credentialed URLs (4.5.1).
That is the same lesson one turn further on: an enumeration can be complete
over the code it audits and still miss the process the code is talking to.
Whether the layers have landed is the board rows' business, not this
paragraph's. What remains on this sink, stated exactly:
a certificate that chains to neither the system store nor a `--tls-ca-file` the
user named now aborts the connection -- measured as a refusal (exit 2) and not
as a measurement of what was already on the wire. The request line and the
header fields are HTTP, written after the TLS handshake, so a handshake that
fails carries neither; that ordering is protocol, not something this project
observed, and it is written here as reasoning. What this does NOT defend
against is unchanged and belongs to whoever holds the certificate: a peer
presenting a certificate the user's trust store accepts for that host is
trusted, and a CA the user names through `--tls-ca-file` can vouch for any host
the player then opens, which is the cost of that escape and the reason it names
one CA rather than switching verification off. UNVERIFIED: whether
`--tls-ca-file` REPLACES the system store for that run or adds to it was not
measured, so the escape is documented as "name your provider's CA" and not as
"keep everything else as well".

**The core dump (D-SINK-39, 2026-10-25).** Every heading above asks where
the URL and the headers are written while the player RUNS; a crash writes all
of it at once. systemd-coredump stores a user process's core under
`/var/lib/systemd/coredump/` as `root:root 0640` with an ACL granting the
crashing uid read, for two weeks by default (the tmpfiles.d age of that
directory, `2w`; this paragraph first said "no retention time", D-DOC-26),
and the host's
`omarchy-crash-watch` then posts a card whose click points an AI agent at the
dump (`omarchy-agent-crash`, the `diagnose-crash` skill: `coredumpctl dump` to
a temporary file, `gdb ... bt`, "read the whole core, not just frame 0"). That
same-uid reader class is the one D-SINK-9 closed `/proc/<pid>/environ` against
by making the helper non-dumpable -- and the kernel sets dumpable back to 1 on
every exec, so the shield reaches no child. Measured 2026-10-25 (QA-RESULTS
"D-SINK-39"): a player started through `player start` with `--vo=null
--ao=null`, loaded through `apply_channel` with a synthetic userinfo
credential, a User-Agent, a Referer and a custom header, dumped by gdb's
`gcore` from its ancestor while `time-pos` moved -- no crash, no journal
entry, no card. Its argv and its environment held nothing, 0 and 0, in both
runs. Its core held the URL's userinfo 13 times in the clean run: one talloc'd
copy in the main heap (the playlist entry, which `path` reads), the helper's
own `loadfile` command text twice as received over IPC (raw, and tokenised in
place), and ten in the thread arenas -- talloc'd demuxer and stream copies,
FFmpeg's url and filename copies beside its protocol whitelist, a scheme-less
parse buffer and a directory-prefix copy; the User-Agent value 4 times (three
mpv option copies in the main heap, one FFmpeg `user_agent`); the Referer
value 5 times and the custom header 7, among them the `set_property
http-header-fields` command text twice, FFmpeg's `headers` string carrying
both as `Name: value` lines, and the stale request buffer. No `Authorization:
Basic` form was present: FFmpeg builds it only after a 401 challenge and the
fixture server never challenged, so a challenging provider would add it (read
in FFmpeg's `http.c`, not measured). Closed at the exec: `spawn_detached`'s
grandchild sets RLIMIT_CORE to (0, 0), soft and hard, as its last act before
`execvp` (`disable_core_dumps` says why both halves), and with it
systemd-coredump journals the crash and stores nothing (`COREDUMP_RLIMIT 0`,
no `COREDUMP_FILENAME`, measured the same day). `read_clipboard`'s wl-paste
gets the same as a `preexec_fn`: the clipboard it reads is the form's paste
path for a provider URL. And the player this shell ADOPTS -- D-SINK-16's
shape, the one the exec-time lever cannot reach, because the old code forked
it -- has its limit lowered from outside at the reattach: `player probe`
(beside the TLS migration) and `player start`'s adopt branch call
`limit_core_of`, which is `prlimit(2)` on the player's pid, allowed to a
same-uid caller without ptrace and irreversible by the player (raising the
hard limit back takes CAP_SYS_RESOURCE; measured). The counts above are one
run's: three gcore runs gave the userinfo 12, 13 and 10 copies and the header
values 3 to 9, so the number is "about a dozen", not a constant. The one
re-run of the rig against the fixed helper, and one crash of that player with
SIGSEGV, read `Max core file size 0 0` on the live process and left journal
entry 34 of the day with `COREDUMP_RLIMIT 0`, no `COREDUMP_FILENAME` and the
coredump directory unchanged at 67 files. What remains, stated exactly: the journal entry,
whose fields were read on a real dump of the harness rig -- `COREDUMP_CMDLINE`
is the launch argv, URL-free by S-03 **[2026-10-29, lane-p2a: and free of
the user's mpvArgs tokens since D-SINK-47 -- they carried a proxy password or a
header value into the journal before; a player adopted after the upgrade keeps
its old argv until it restarts]**; `COREDUMP_ENVIRON` is the shell's whole
environment, which the player's helper Process never hands a URL (no
`OMARCHY_IPTV_URL` among its 257 names); `COREDUMP_OPEN_FDS` names sockets and
pipes by inode, so an HTTP channel shows nothing and a `file://` channel would
show its path; `COREDUMP_PROC_MAPS`, `_STATUS`, `_LIMITS` and `_CWD` carry no
string of the stream's. The crash card and the agent it starts remain and then
find no core. The cost: a crashed player leaves no core for the user's own
diagnosis either. And the shell itself, which holds every source URL in its own
heap, is host-owned and dumpable: the same sink one layer up, outside this
plugin's reach, recorded for the owner.

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

**Upgrade from 0.12.1 or earlier with a player running (D-SINK-16).** The case
above is the one where the old player is gone or unidentifiable. The case that
matters for security is the one where everything works: the player survives,
it carries a stash, and the new service adopts it exactly as designed -- with
the argv of the version that launched it, so without TLS verification, while
the new shell goes on zapping it. 4.5.1 is what the adoption does about that:
read the two properties, set them if they are not already safe, read them
back, re-establish the current channel, and stop the player rather than feed
it if the read-back is not clean. The user-visible shape of the upgrade is one
rebuffer, once, and the README says so in the user's own words. This needs a
live case of its own, on a player launched from the 0.12.1 argv and adopted by
an installed build, and the id for it is QA's; it cannot be proved by any fake
for the reason section 12 gives about this whole feature.

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
  `Timer playerWatchdog` (12 s; **[Amended 2026-10-28, D-PLY-35: per verb,
  derived from the helper's bounds; 12 s is the birth edge, 4.7]**), and the properties `playerPending`,
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
   guide's own failed marking carries the information.
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
| PO-3 | Option (a): mark the channel failed silently on reattach and show it in the guide. A toast for something that stopped minutes ago, possibly on another login, is noise and would arrive without context. The guide's failed marking carries the information, and the guide is where the user goes next anyway. |
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

## 14. Amendment after lane PB (product owner, 2026-09-14)

Lane PB built the service side and found one more thing that only a live shell
could show. Recording it here so sections 4.9 and 4.10 are not read as correct
as written.

A detached stop cannot observe a `superseded` refusal. The stop ladder is
issued as one detached helper call precisely so it completes even if the shell
dies mid-ladder, but that also means nothing reads its reply. Once any other
launcher leaves a higher sequence number in the lock, including the
`omarchy-iptv player stop` command this document tells users to run, every stop
from the interface became a silent no-op: the interface went idle while the
player kept playing. Lane PB fixed it by having the stop-settle timer probe and
re-issue past the recorded sequence. Sections 4.9 and 4.10 must be read with
that correction: either the service confirms a detached stop, as it now does,
or `stop` is exempt from the sequence rule. The service confirming it is the
better answer, because it also covers a stop that loses to an unrelated race.

Two more notes for whoever picks this up next.

The `session` key described in sections 4.6 and 8 was not built by either lane,
because lane PA finished before the need was clear and lane PB does not own the
state file. Ruling PO-3, marking a channel failed silently on reattach rather
than raising a stale notification, is unimplementable without it. A follow-up
lane is closing that gap and adding the router test cases lane PB could not
write, since it owns no test file. That ownership rule is right, but it has a
cost worth naming: a lane that owns implementation and no tests will always
leave its own paths uncovered, and the plan must schedule someone to close it
rather than assuming it happens.

Counting the four corrections lane PA found by building and the one lane PB
found live, this design has now been corrected in eleven places since it was
accepted, on top of the shape that gate PB-0 withdrew before anyone wrote code.
Every one came from running something. None came from re-reading the document.

## 15. Known issue carried into the quality pass (product owner, 2026-09-14)

One pre-existing race is knowingly unresolved and must be tested rather than
assumed harmless. At service start, the state file is read asynchronously while
a play can be issued immediately. If a play beats the file, the handler that
applies the loaded state can overwrite the in-memory session record that play
just wrote. The window is small and the consequence is bounded, namely a
failure that happened during that window would not be marked on a later
reattach, but nothing proves the window is as small as it looks.

It is deliberately not being fixed blind. Gate it in the quality pass: provoke
the ordering, measure how often it loses, and fix it only if it reproduces.
This project has now spent nine corrections on details that were reasoned
rather than run, and guessing at a fix for a race nobody has observed would be
the tenth.

## 16. Rulings on the quality-pass defects (product owner, 2026-09-14)

| # | Ruling |
|---|---|
| PO-8, on D-PLY-2 | Accept that removing the plugin can strand a running player, and stop trying to win the race. Removal already uses the same signal disabling does, and the stop is genuinely attempted: the orphan check executes about 414 ms in. It fails because the directory deletion lands about 20 ms earlier and the helper is gone before it can run. Nothing the plugin owns can beat another program's `rm -rf`, and the one mechanism that would, staging a copy of the helper elsewhere, buys a rare case by permanently violating requirement 10 and adding an executable outside the plugin directory. Not worth it. Disabling reaps the player in about seven seconds and is the supported way to stop cleanly. For the stranded case the README documents a command that needs nothing installed. |
| PO-9, on the stranded-player command | Document `pkill -f -- '^mpv .*--wayland-app-id=omarchy-iptv'`, and document the leading anchor as load-bearing, because the lane proved that without it the pattern matches and kills the shell the user pasted it into. A command that can kill the terminal it is typed in must never appear in documentation without that warning. Show a `pgrep` first so the user sees what will be killed before killing it. |
| PO-10, on D-PLY-5 | Implement the cheap catch. The lane offered roughly ten lines plus its mirror to detect the handful of options that hand a stream address to another program, and surface it through the warning line that already exists. Take it. A warning the user sees when they actually use the option beats a paragraph in a README they read once, and the documentation stays either way. |
| PO-11, on D-PLY-7 | Fix it. The player inherits the shell's working directory, which is the user's home, and its own key bindings are live, so one keystroke on the player window writes a durable image of what was being watched into the home directory at mode 0644, outside every list of files this plugin claims to write. Spawn the player with an explicit working directory rather than an inherited one, point its screenshot output somewhere sensible and documented, and say plainly in the README that the player's own keys work and where anything it saves goes. The plugin does not get to be quiet about a file it causes to exist. |

Two observations for the record. First, the P1 in this pass came from the same
family as every other hard defect here: an event arriving in a window nobody
modelled, in this case the old player's socket closing while the call that
replaced it was still running. Second, the startup race is the clearest
argument yet for measuring rather than reasoning. I wrote in section 15 that
its window looked small and its consequence bounded. It dropped the play in 29
of 30 trials.

## 17. Amendments after the cleanup round (product owner, 2026-09-14)

Rulings CL1 to CL8 are in `docs/CLEANUP-PLAN.md` section 9. Four of them
change this document.

**CL1 - what the stop budget measures.** PLY-PERF-02's 4500 ms measures the
time until the **player process is gone**, not until the `player stop` command
returns. `stop` is issued with `execDetached` and nothing reads its reply, the
interface clears on the keystroke, and the command's return therefore tells
the user nothing. Section 4.9.1 and the README are worded that way. A settle
that keeps looking after the process has died cannot spend that budget at all.

**The D-PLY-8 cause on record was wrong, and is corrected in 4.9.1.** It was
recorded in three documents as "most likely `find_player()` still sees the
just-SIGKILLed process". A SIGKILLed process runs `exit_mm()` before it closes
its descriptors, so the finder goes blind **first** - 0.13-0.31 ms, 8/8 on
real mpv 0.41 here - while the listening socket stays bound for another
2.7-4.9 ms. The blocking guard is `socket_is_dead()`. The false version is an
active trap, because it invites making the finder see dying or zombie
processes, which would make the ladder report `running:true` after a
successful SIGKILL. The other two records are in `docs/STATUS.md` (the D-PLY-8
row) and `docs/QA-RESULTS.md` (section V9), with the same sentence repeated in
`docs/QA-PLAYER.md`'s corrections index; correcting those belongs to whoever
owns them.

**CL2 - mpv's caches are contained, ephemeral, and not reserved.**
`--gpu-shader-cache-dir` and `--icc-cache-dir` point into
`$XDG_RUNTIME_DIR/omarchy-iptv/shader-cache`, created 0700 with the other
player directories. The cache is content-free and regenerable, so the runtime
directory is right: nothing durable to document, nothing to clean up at
uninstall. Neither option joins `MPV_RESERVED` - that list is a privacy
instrument, which is why `--watch-later-dir` is on it and `--screenshot-dir`
deliberately is not - so containment here is a sensible default and a user
token still wins. What no headless test can show is that mpv honours the
option: `--vo=null` compiles no shaders, so the display lane confirms it by
watching `~/.cache/mpv` stay empty across a containment cycle.

**CL8 - the two unlocked settle call sites are locked.** See the end of 4.9.1.

> **Amended 2026-09-25** (F-PLY-4): the paragraph below predates the fix by
> two hours and was never revisited. D-PLY-11 is verified fixed at merge
> 739c229 (the helper stand-down) with the CL5 shell-side re-apply; the board
> row carries the live confirmation (0 divergences in 20 cold concurrent
> bursts at d76b649) and QA-RESULTS L1/L2 the evidence, including the cost
> this document never recorded: one extra `loadfile` on the cold concurrent
> burst path, entry id 3 in 12 of 20 runs where the pre-fix tree read 2 in 18.
> A correct and cheap trade, and a behaviour change, so it is written here.

**D-PLY-11 is still open, and section 4.10 is not the answer to it.** The
proposed cause was refuted and its replacement is a hypothesis, so this round
characterised the two candidate mechanisms rather than fixing either:
`tests/test_player.py::OrderingTest` pins that an adopting `player start`
re-applies its own channel over a zap that already landed, and that a `play`
can win the socket inside a cold start's handshake and be overwritten.
`Model.playFork` / `Model.playForkBlind` state the shell's fork where a test
can reach it and are **wired to nothing**; whoever wires them checks them
against the shipping fork first. Ruling CL4 still stands: `play` does not get
a sequence number and the lock until refusals are routed, and that needs an
amendment to 4.3 rather than a workaround.

## 18. Live rewind (M5-01)

The design is `docs/M5-01-LIVE-REWIND.md`, approved on every decision on
2026-10-03; its sections 2.1-2.7 are the specification and section 9 the
twelve rulings. The evidence is `docs/SPIKE-LIVE-REWIND.md` sections 1-7 and
11. This document is not rewritten for it: nothing in sections 4.1-4.14
changes shape, and the 13-file allowlist is untouched. Three things are
ADDED, and a reader of the sections they touch should know they exist.

**A third `user-data` sibling node (amends 4.6).** 4.6 says the record lives
in "two sibling top-level `user-data` nodes"; it is now three.
`user-data/omarchy-iptv-rewind` holds the behind-live zero point, `(wall0,
pos0)` taken at the first numeric `time-pos` after each `loadfile`, keyed by
the `entryId` the stash already captures from the `loadfile` reply. It is a
SIBLING, not a sub-path of the stash, for the reason 4.6 gives: deep paths
are unverified and a nested write is a read-modify-write race. A zap changes
the entry id, so a stale zero point is invalid by construction; a shell
restart recovers it from the player exactly as pause state is recovered,
because the player is authoritative. The helper writes it lazily from
`status`, `pause` or `seek`, whichever first sees a numeric `time-pos` for
the current entry. "No zero point yet" is `null`, never zero (D-DEAD-1).
`behindLive` is `(wall - wall0) - (pos - pos0)`, never `cache end -
time-pos`: after a rewind deeper than the forward quota mpv stops fetching,
the cache end freezes, and that difference counts DOWN while the real gap
holds (spike 11.3, measured 300.60-300.64 across thirty ticks).
A reading AHEAD of the zero point re-takes it (F-RWD-11, integration): the
point is first taken where the reader sits after a `loadfile`, which is the
HLS lead behind the cache end, and a `live` seek lands past it, so the
formula reads negative there; the helper then writes a fresh `(wall0, pos0)`
at that reading on the verbs that write, and the probe, which never writes,
returns the raw value for the shell to clamp. `behindLive` from `status`,
`pause` or `seek` is therefore never negative, and it is `null` until the
reader sits inside a seekable range: a position reported with no range (a
stream still opening, or one that never opens) takes no zero point and
moves none (F-RWD-16).

**A seek verb in the control slot (amends 4.3).** `player seek --socket S
--by N` (N a signed integer of seconds, negative is back) and `player seek
--socket S --live`, beside `player pause`, with the same request-id
discipline and `probe_client`, on `controlProc`. In one run it reads
`time-pos` and `demuxer-cache-state`, clamps -- a backward target to
`seekable-ranges[r].start + 2.0`, a forward target and `--live` to the range
end minus 0.5 s -- issues one ABSOLUTE seek, reads `time-pos` again, and
replies with the schema in design 2.1. `success` from mpv is not evidence of
movement: a refused seek replies `success` with `time-pos` unmoved and one
error-level log line (spike 11.4), so `moved` is the difference of the two
reads and a request that did not move is reported as refused with the floor
it hit. The second read waits for mpv to say the seek ran: the reply to
`seek` means queued, and a read sent at once can be answered before the
playloop executes it (F-RWD-15, 1 of 12 on a local stream), so the verb
subscribes to error-level log messages first and waits, bounded at 250 ms,
for the `seek` event or the refusal line before reading. The same `rewind` object is added to the `status`, `pause` and
`probe` replies so the existing ticks carry the numbers without a new
process. Numbers and booleans only; `path` is never echoed. Like `pause` and
`tracks` it is side-effect-free: no player, no spawn, `running: false`.
The service coalesces presses while a seek is in flight, caps the pending
sum at the last-read `history`, throttles the next run 300 ms from the
previous reply, and runs `drainPendingPlay()` on every path of the branch
(the D-PLY-24 lesson).

**A health-count exemption (amends 4.13).** `Model.healthTick`'s busy-skip
counter exists to restart a helper that never returns, and the 8 s control
watchdog (`controlTimeoutMs`, 4.3's slot) already terminates that case. A
slot re-occupied every few hundred milliseconds by a sub-second verb -- a
held rewind key -- is the benign case the three-strikes counter must not
punish, so seek runs are exempt: `busy = controlProc.running &&
controlKind !== "seek"` (D10). The seek itself replied in 0.10 ms and the
read after it in 0.34 ms against that 8 s watchdog (spike 11.3); the
exemption is for the slot's occupancy, not its latency.

## 19. Where a channel may send this machine (D-SINK-41, D-SINK-42, D-PLY-44; 2026-10-29)

The owner's policy of 2026-10-29 (ARCHITECTURE.md section 6 has its fetch
half): a destination the PROVIDER chose may not reach a non-global address
unless it is the user's own playlist host; udp and rtp only to multicast
groups; no stream form that listens; no sign-in header to another host.
The helper never sees mpv's connection, so for a stream its only lever is
what it lets into channels.json and what it lets through `player_target`.

### 19.1 The gate, and the layer each part sits in

- **Listening forms (D-SINK-42), context-free, at parse time AND at play
  time.** Measured with mpv 0.41.0 / FFmpeg n9.0.1 inside `unshare -rn`
  (loopback only, so nothing bound a real interface; crash journal 81
  before and after every run): `udp://0.0.0.0:P` and `udp://[::]:P` bind
  every interface, `udp://127.0.0.1:P` binds that address (an input binds
  the URL's own host), `rtp://` unicast binds its port and its RTCP port on
  0.0.0.0, `srt://...?mode=listener` binds P and `mode=rendezvous` binds P,
  and `localport`, `localaddr` and `localrtpport` move the bind;
  `udp://@239.1.1.1:P` binds the GROUP address. rtmp `?listen=1` and
  `?rtmp_listen=1`, rtsp `?listen` and `?rtsp_flags=listen`, http
  `?listen=1`, mms and mmsh bound nothing (FFmpeg reads no option from those
  URLs); `tcp://` is not a stream scheme. `is_stream_url` now refuses udp
  and rtp to anything but a multicast literal, srt in any mode but caller,
  and any stream URL carrying one of `LISTEN_PARAMS` -- the measured binders
  and the aliases FFmpeg's udp, rtp, tcp, rtmp and rtsp protocols give them,
  read the way FFmpeg reads them (after the FIRST `?`, a `#` included, so
  `srt://h:1#?mode=listener` is refused) and compared case-folded and
  %-decoded, which is stricter than FFmpeg. `player_target` runs every
  cached URL through `is_stream_url` before a load, so a cache written
  before this cannot open a port either; it answers `unsupported_scheme`,
  as for any URL the gate refuses (a CHANNEL refusal, D-PLY-31's reading).
  A refused line is counted: `N entries skipped: the streams would listen on
  this machine for anyone to send to`. Cost the owner accepted: an ISP
  multicast list that pins the interface with `localaddr` is refused, and a
  provider URL whose query happens to carry one of those names is refused.
- **Non-global literal hosts (D-SINK-41), at parse time, against the
  playlist.** `parse_m3u` is handed `playlist_source(kind, url,
  policy.last_class)`: the typed URL's host key, and whether the source is
  LOCAL -- a file the user pointed at, or an http(s) source whose last hop
  connected to a non-global address (the fetch's own DestinationPolicy). A
  channel whose LITERAL host is not global (any spelling of loopback, the
  LAN, link-local, CGNAT, unspecified or reserved; `localhost`) is skipped
  and counted unless the source is local or the host is the playlist's own;
  a multicast udp or rtp group passes. A parse that is told nothing reads
  as a public source on no host and fails closed.
- **Sign-in headers (D-SINK-41).** `Authorization`, `Cookie`,
  `Proxy-Authorization` and `Host` from `#KODIPROP` (`#EXTVLCOPT` gives only
  `User-Agent` and `Referer`) are dropped, counted, unless the channel's
  host is the playlist's own. A local FILE has no host, so its channels keep
  none of them -- the owner's rule read literally, and raised as a decision
  request by the lane.
- **No control character, and a header name read whole (the lane's
  recheck, 2026-10-29).** The gate reads a URL's host with `urlsplit`; the
  player reads the URL after the helper's own JSON IPC `loadfile`, where
  mpv decodes a `\u0000` and ends the string at it. So a NUL after the host
  gave the two of them different hosts, and every rule above read the one
  the player never used (measured through the shipping `playlist` verb and
  `apply_channel` in an unprivileged network namespace: the loopback server
  received the list's sign-in headers, and a udp form bound 0.0.0.0). Any
  C0, DEL or C1 character now makes a line no stream URL, at parse time and
  at play time (`stream_form_ok`, `stream_entry_refusal`), counted with the
  `unsupported URL scheme` entries. And `_HEADER_NAME` is applied with
  `fullmatch` at both its readers, because `re.match` let `$` match before a
  final line break: `Cookie%0A` decoded to a `Cookie\n` the sign-in rule,
  which compares names exactly, did not see.

**[2026-10-29, lane-p1b: the player now closes what the gate cannot reach
of the nested route, the paste and the drop, and a server's own SDP answer.]**
The owner's decision on D-PLY-44 is to REFUSE nested playlists: the
helper's `loadfile` carries the per-file `demuxer=lavf`, so a plain M3U or
PLS a stream server returns -- its http, srt and rtp entries alike -- is
`unrecognized file format`, nothing fetched, nothing bound, while HLS master,
HLS variant and MPEG-TS play (`tls-scenario.sh --windowless` W11; sec-int
6c79a9a fetched the http entry and bound the srt and rtp listeners). The
provider's headers are per-file options of that same `loadfile` (4.11), so
an entry the helper did not load is sent none of them (W14). The paste key is
bound to `ignore` and drag-and-drop is off, at start and on adoption (D-PLY-46,
W15). And D-SINK-55, which rc-dest found the gate's form check could not see
-- any http(s) URL whose server answers with an SDP body made FFmpeg open
`rtp` with the whitelist inherited from http, binding 0.0.0.0:P and P+1 --
is closed by the pin block's demuxer `protocol_whitelist` (4.12.1, W12).
Below, 19.2 as written; the brackets in it say what moved.

**[2026-10-29, lane-p1c: two more.]** (1) D-SINK-57's scope (the lead's
decision): a LOOPBACK source's channel whose literal host is loopback must be
on the source's own port -- refused and counted at parse time, refused at play
time -- while its LAN channels still pass (ARCHITECTURE.md section 6 has the
rule and its cost). (2) The demuxer's format list (4.12.2, D-SINK-62) closes
what the nested-route paragraph below called closed and was not: a stream
server answering with an IMF composition playlist, or an ffconcat file naming
one, made FFmpeg open listeners the protocol list had to admit.

### 19.2 What the gate cannot reach, stated exactly

- **A NAME that resolves to a LAN address.** mpv resolves it, not the
  helper. A pre-resolve in `apply_channel` was weighed and not made: it is
  check-then-use against the provider's own DNS, and a provider who runs a
  server beats it without DNS at all -- measured: FFmpeg followed a 302 from
  127.0.0.1:47200 to 127.0.0.1:47201 and carried the per-file
  `http-header-fields` (`X-Test: provider`) to the second host. FFmpeg's
  `max_redirects` would stop that, but only through `--stream-lavf-o`, which
  must stay EMPTY (D-SINK-13 layer three, D-SINK-16's read-back), and a
  redirect-free player would break every load-balanced provider.
- **HLS variant and segment URLs.** FFmpeg's hls demuxer fetches them
  itself; measured, it opens only http(s), file and data URLs (an HLS-shaped
  playlist whose "segments" were `udp://0.0.0.0:P` and `rtp://0.0.0.0:P`
  bound nothing through it), so the LAN reach of a segment is the residual
  and a listening segment is not.
- **The nested route and D-PLY-44: entries the helper did not load.** A
  plain M3U the stream server returns is expanded by mpv's own playlist
  demuxer, and mpv counts srt and rtp as SAFE protocols for a network
  playlist, so `load-unsafe-playlists=no` lets `srt://0.0.0.0:P?mode=
  listener` and `rtp://0.0.0.0:P` through (measured: both bound; udp was
  refused). mpv's default Ctrl+V binding (`loadfile ${clipboard/text}
  append-play`) appends an entry nobody gated, which then plays with the
  previous channel's provider headers, because the helper sets them as
  GLOBAL properties. Measured on 2026-10-29, the levers, in the brief's order:
  1. **An `on_load` hook over the shell's own IPC connection does not
     exist**: mpv 0.41.0 answers `hook-add` over JSON IPC with
     `Command 'hook-add' not found` (hooks are client-API only, `mpv_hook_add`;
     the JSON IPC has no mapping). Rejected by measurement.
  2. `access-references=no` stops the nested route -- and every HLS master
     and variant playlist with it (`unrecognized file format`). Rejected:
     HLS is most of IPTV.
  3. **What works, all helper-side:** a PER-FILE `demuxer=lavf` on the
     helper's own `loadfile` refuses a nested plain M3U (http, srt and rtp
     entries alike: `unrecognized file format`, nothing fetched, nothing
     bound) while HLS master, HLS variant and MPEG-TS play; PER-FILE header
     options (`http-header-fields`, and the user agent and referrer, on the
     `loadfile` instead of `set_property`) reach the channel and its HLS
     segments and do NOT reach a nested entry or an appended one (measured:
     the nested and the pasted request carried no `X-Test`, every segment
     request did); and `keybind ctrl+v ignore` sent once per player
     replaces the default binding (measured with `keypress`: a bound
     loadfile appended one entry, the same key after `ignore` appended
     none). The cost of `demuxer=lavf`: a channel whose URL is itself a
     plain playlist (a radio `.pls`, an `.m3u` redirector) stops playing.
  **Not shipped by lane-dest**: all three sit in `apply_channel` and the
  player argv (bin/helper/08-player-verbs.py, 07-player.py), which belong to
  the concurrent lane-mpvpin, and the brief forbade shipping half a lever.
  Until they land, the nested route and Ctrl+V are open as described, with
  D-SINK-42's listening forms closed only for URLs the helper loads.
  **[2026-10-29, lane-p1b: all three shipped, with drag-and-drop off and the
  SDP answer closed -- the bracket above 19.2. The cost the owner accepted is
  told: a channel whose URL is itself a plain playlist ends with mpv's
  `unrecognized file format`, which the shell shows as "The address sent a
  playlist file or a web page, which the player does not open"
  (`Model.unopenedFormatSentence`), marked like any stream that failed to
  load. What stays open of this item: nothing of the nested route. The
  FFmpeg-redirect residual above is unchanged: a per-file option belongs to
  the file, so FFmpeg's own 302 still carries the channel's headers to the
  host it names.]** **[2026-10-29, lane-p1c: "nothing of the nested route"
  was wrong when written. mpv's playlist demuxer was closed; FFmpeg's own
  were not -- its IMF demuxer opens the asset URIs a CPL's ASSETMAP names,
  and its concat demuxer the files an ffconcat list names, through the
  protocol list D-SINK-55 pinned, which has to hold tcp (rc-p1b's recheck,
  D-SINK-62: tcp, tls and listen=2 assets bound 0.0.0.0). Closed by the
  demuxer's format list (4.12.2), measured with every route above refused
  and every channel kind still playing; and mpv's prefetch handed an entry
  the helper did not load the channel's per-file headers (D-SINK-63, pinned
  off, 4.11).]**

### 19.3 The fixture

`tests/fixtures/destinations.json` holds every host spelling with its class
and key (both suites), every stream form with the gate's verdict (`streams`,
`streamHosts`; the python suite: the model has no stream gate), and the
helper's refusal replies with the shell's sentence for them.
