# Cleanup plan: D-PLY-8, D-PLY-9, D-PLY-10, D-PLY-11 and the harness audit

## Summary

This round closes four open P3 defects from the M2-02 verification pass at `b16b479` and one class of tooling failure that the pass itself exposed. Two items get code: **D-PLY-8** (a wedged stop leaves `mpv.sock` behind - root cause confirmed by an independent adversarial re-measurement, fix is a bounded re-check of the settle guards inside the kill rung's own unused deadline) and **D-PLY-10** (mpv's shader cache lands in `~/.cache/mpv/`, which the product owner has ruled must be contained in the plugin's own tree, consistent with the screenshot and resume-position containment already shipped). One item gets a one-line code fix plus an investigation it does not by itself discharge: **D-PLY-9** (`log_count()` returns two lines and kills one harness assertion by arithmetic error - mechanism confirmed and reproduced, but the skeptic established that the assertion it kills would have passed on both trees, so repairing `log_count` alone converts a silently-absent check into a silently-green one). One item gets **no cause-directed code change at all**: **D-PLY-11** (now-playing names a channel the player is not playing) had its root cause refuted - the proposed most-likely ordering requires a helper crash on a slot that runs one helper at a time, and the second-ranked ordering was shown to be internally impossible because both of its "racing" calls read the same `root.nowPlaying` in the same synchronous turn. The skeptic's replacement explanation (a cold-start fork race) is a hypothesis with a rate that fits the evidence, not a traced fact either. For D-PLY-11 this round funds the investigation that discriminates between the families, plus the three defects both parties independently verified and which are wrong regardless of which ordering fired. Alongside these, the harness audit is treated as a first-class work item and ranked by what each broken check would let through, because this project shipped D-PLY-1 in its second release behind a green suite and the same shape is present in eleven more places.

Deliberately **not** in this round: giving `play` a `--seq` and the player lock (blocked - see Q4); any reconciler that relabels `nowPlaying` from the player's stash (it would name the channel the user did not ask for); making `find_player()` see dying or zombie processes (it would make the ladder report `running:true` after a successful SIGKILL); rewriting the six `qa-player-scenarios.sh` scenarios into asserting scenarios (scoped as one-line exit-code fixes here, full conversion deferred); and any live re-run of PLY-LIFE-03 or TC-PLAY-10 outside the single lane that holds the display.

---

## 1. D-PLY-8 - a wedged stop leaves the socket file behind

### What is KNOWN

The blocking guard is `socket_is_dead()`, **not** `find_player()`. Both the investigator and the skeptic drove the shipping functions against a stand-in that owns both the `--input-ipc-server` token and the bound socket, and both measured the same thing.

- `settle_socket()` is two single-shot guards with no retry: `bin/omarchy-iptv:2517-2525` - `if find_player(sock_path): return False`, then `if not socket_is_dead(sock_path): return False`, then `unlink_stale_socket()`.
- `socket_is_dead()` returns `False` on a **successful** connect (fall-through at `bin/omarchy-iptv:2514`) and on a **timed-out** connect (`MpvIpc.connect`'s `TimeoutError` branch at `bin/omarchy-iptv:1625-1627` does not set `self.refused`). Only ECONNREFUSED or a missing path make it `True`. `bin/omarchy-iptv:2506-2514`.
- `player_stop` calls `stop_ladder(...)` then `settle_socket(sock)` exactly once: `bin/omarchy-iptv:2863-2864`, inside the flock taken at `2855` and released at `2872-2874`. There is no retry at any of the eight call sites (`2767`, `2777`, `2819`, `2860`, `2864`, `2892`, `2957`).
- The existence predicate both the ladder and the settle share keys only on `--input-ipc-server=<path>` in `/proc/<pid>/cmdline`: `bin/omarchy-iptv:2151-2157` (`proc_cmdline`), `2182-2202` (`find_player`), `2204-2219` (`still_the_player`).
- **The QA hypothesis recorded in three documents is measurably false.** A SIGKILLed process runs `exit_mm()` first, so its cmdline is already empty at the first post-SIGKILL sample - 8/8 runs, 0.16-0.33 ms, in state **R**, not Z. `find_player` therefore goes blind *earlier* than everything else, not later. Confirmed independently by both parties.
- **The quit/kill asymmetry is measured on both sides, on real mpv 0.41.** On `quit` the IPC listener is refused **2.08-2.23 ms before** the cmdline empties (4/4). On SIGKILL it is refused **2.71-5.75 ms after** (4/4). What a kill leaves behind that a quit does not is a still-bound listening socket owned by a process the finder can no longer see.
- **The timing inside the code.** `wait_for_exit` (`bin/omarchy-iptv:2528-2536`) checks at the top of its loop before any `_sleep`, and wins on the first check: **0.24-0.39 ms, 12/12**. `find_player` then costs one full `/proc` scan (5.56 ms for 222 pids on this box), so `socket_is_dead`'s connect lands **4.2-8.3 ms** after the SIGKILL. The investigator's "roughly 50-80 ms" figure is about 10x too large and every threshold argument built on it is void.
- **The defect fires when the blind-to-unbound window exceeds that ~4-8 ms observation point**, and the window is teardown-proportional: measured 0.35-0.60 ms at ~10 MB, 1.6-3.4 ms at 256 MB, 33.6-36.5 ms at 768 MB, 113.5-114.3 ms at 1500 MB. Driving the shipping functions: at >=768 MB, `socket_is_dead` returns `False` and the socket is left on disk 6/6; at <=256 MB it returns `True` and settles 6/6.
- **A headless mpv does not reproduce it** (51 MB, `--vo=null`): the window is 2.7-5.8 ms, `socket_is_dead` returned `True` and `settle_socket` unlinked, 3/3.
- The code's guards match the published design. `docs/ARCHITECTURE-PLAYER.md:525` is "`find_player()` empty **and** `connect()` returns ENOENT/ECONNREFUSED -> `unlink_stale_socket()` (S_ISSOCK-guarded). Never unlink on a successful connect." The code honours that. What it does not do is repeat the check.
- The residue is harmless to the next play: mpv unlinks and rebinds over an abandoned socket file (verified directly by both parties), matching QA's "next play succeeded in 665 ms" at `docs/QA-RESULTS.md:2548`.
- Pre-existing: `git log -S 'def settle_socket' -- bin/omarchy-iptv` returns only `056d5d1`. The suite is green at HEAD: 260/260 python, 954 node checks.
- **The kill rung already owns 500 ms it does not spend.** `stop_escalation("term")` returns `waitMs: 0` (`bin/omarchy-iptv:2086`), so `grace = int(step["waitMs"]) or STOP_SETTLE_MS` at `bin/omarchy-iptv:2591` falls back to the full `STOP_SETTLE_MS` = 500 (`bin/omarchy-iptv:1918`), of which `wait_for_exit` spends 0.3 ms. `docs/ARCHITECTURE-PLAYER.md:524-525` already places the settle at the **end** of that 500 ms.

### What is ASSUMED

- **That a real windowed mpv clears the ~4-8 ms bar.** This is inference, not measurement. Neither lane holds the display, so no one has measured the teardown window of an mpv holding a GPU context, a Wayland connection, decoder buffers and a demuxer cache under `--force-window=immediate` (`bin/omarchy-iptv:2066`). The scaling series and QA's determinism at two commits make it very likely; it is not confirmed. **Live-lane item.**
- The two parties' absolute teardown numbers differ by roughly 2x on identical shapes. Do not build any argument on the absolute values; only the *ordering* and the *proportionality* are established.
- The 500 ms between 4.0 s and 4.5 s in `docs/ARCHITECTURE-PLAYER.md:524` belongs to the **kill rung's poll**; line 525 gives the settle a single instant. A polling settle is therefore a modest design change, not "honouring the 4.5 s". The investigator's "~250 ms of already-budgeted headroom" is not headroom the settle owns - that 250 ms is helper startup plus the ladder.

### The fix

Implement the clause; do not drop it. The residue's duration is machine-dependent, so documenting it would mean documenting a number that is not a constant, and dropping it means editing PLY-STOP-03, `docs/ARCHITECTURE-PLAYER.md:525` and the README to promise less than the design already reserves the time for.

**Shape: an absolute deadline carried out of the kill rung, not a flat wait.**

1. `bin/omarchy-iptv:2517-2525` - `settle_socket(sock_path, deadline=None)`: poll **both existing guards** via `_monotonic`/`_sleep` (`bin/omarchy-iptv:1954-1962`) at `STOP_POLL_S` (`bin/omarchy-iptv:1926`) until both pass or the deadline is reached. With `deadline=None` the behaviour is byte-identical to today (one check, no sleep), so the seven other call sites are provably unchanged.
2. `bin/omarchy-iptv:2578-2598` (`stop_ladder`) - return the rung's own remaining deadline alongside `running`/`rung`, so `player_stop` can hand it to the settle.
3. `bin/omarchy-iptv:2864` - the post-ladder settle in `player_stop`, and only that one, receives that deadline. It is the only settle call site inside the flock (the file's only `acquire_lock` calls are `2814` and `2855`), and the lock held across check and unlink is the real defence against a racing spawn.
4. Leave `2767`, `2777`, `2819`, `2860`, `2892`, `2957` at `deadline=None`. The spawn paths are latency-sensitive and mpv rebinds over a stale file anyway; `2892` (`player_probe`) and `2957` (`player_orphan_check`) are both **unlocked** and must not be given a wait - see item 1 of the harness/extra findings below.

**Why an absolute deadline and not `STOP_SETTLE_MS`:** `socket_is_dead` constructs `MpvIpc(sock_path, 0.2)` at `bin/omarchy-iptv:2507`, and a **timed-out** connect burns that 0.2 s per iteration. A loop that checks a flat 500 ms budget before each connect can overshoot by 0.2 s, putting the wedged stop at ~4.7-4.95 s against PLY-PERF-02's 4500 ms and within ~50 ms of `Service.qml:64`'s `stopSettleMs = 5000` backstop, restarted on the same keystroke at `Service.qml:477`. Carrying the kill rung's deadline instead cannot push the command past 4500 ms no matter how long the teardown runs, needs no new constant, implements `docs/ARCHITECTURE-PLAYER.md:524-525` exactly, and makes the whole budget question moot (Q1 below survives only as a wording issue).

**Safety - the part that matters. The fix must NEVER widen the conditions, only re-evaluate them.** Before any unlink, at one instant, all of these must hold:
- `find_player(sock_path)` empty, **re-run every iteration** so a racing spawn aborts the loop;
- `socket_is_dead(sock_path)` `True`, meaning the connect was REFUSED or the path is gone. A **successful** connect (a wedged player answering through its backlog) and a **timed-out** connect (a live player with a full backlog) must both keep blocking it - the current code already gets this right and it must not be relaxed;
- `lstat` still says `S_ISSOCK` at unlink time (already in `unlink_stale_socket`, `bin/omarchy-iptv:1844-1852`);
- the player lock is held across check and unlink - true only at `bin/omarchy-iptv:2864`.

**Do NOT** "fix" this by making `find_player` see dying or zombie processes (`os.kill(pid,0)`, bare `/proc/<pid>` existence). A double-forked grandchild can sit as a zombie until the subreaper waits on it; the ladder would then report `running:true` after a successful SIGKILL and the settle would be blocked indefinitely. Both parties agree on this.

### The test that proves it - deterministic where it can be, probabilistic where it cannot

**Deterministic (unit gate, `tests/test_player.py`, no display):**
- `settle_socket` with `find_player` stubbed empty and `socket_is_dead` returning `False, False, True` on successive calls, `_monotonic`/`_sleep` injected via the existing `LadderTest.clock` pattern (`tests/test_player.py:651-684`): assert it unlinks and returns `True`. Red today for a tautological reason (the function is single-shot by construction) - state that plainly in the commit rather than claiming it proves anything about the kernel window.
- `socket_is_dead` permanently `False` (a live player answering through its backlog): `settle_socket` returns `False`, the file survives, and the injected clock advanced no more than the deadline. Green today; **must stay green**. This is the regression guard that matters.
- Same with a **timed-out** connect rather than a successful one, because that is the second sufficient blocker and it is the biggest input to worst-case latency.
- `find_player` returning a record while `socket_is_dead` is `True`: no unlink for the whole wait. Green today; must stay green.
- `settle_socket(path)` with no deadline behaves exactly as today (one check, no sleep).
- Ladder-level: assert the deadline handed to the settle never exceeds the kill rung's own 500 ms window from `rung_started`.

**Probabilistic by nature, and must be labelled as such:** any test that reproduces D-PLY-8 with a real process depends on a teardown-proportional window. The live-shaped rig (one stand-in that carries the token *and* binds the socket, with a large touched allocation) reproduces at >=768 MB and passes at <=256 MB on this machine - that is a QA rig, not a unit gate. **No unit test will ever fail against this bug as it occurs in the field.** Deterministic coverage comes from injected guards only.

**Live (display lane):** PLY-STOP-03 re-run - `kill -STOP`, stop, then assert `mpv.sock` is gone at t+1 s with no further helper call; five wedged and five responsive runs; PLY-PERF-02 numbers re-measured. Plus one tight `connect()` sampling loop right after the SIGKILL on the real windowed player, to turn the one assumption above into a measurement.

---

## 2. D-PLY-9 - a harness check that never runs

### What is KNOWN

The mechanism is airtight and was reproduced end to end by both parties on bash 5.3.15.

- `scripts/dev-harness/player-scenario.sh:149` is verbatim `log_count() { grep -acE "$1" "$SCRATCH"/harness.log 2>/dev/null || echo 0; }`. `grep -c` prints `0` on stdout **and** exits 1 on no match, so both sides of the `||` run. `od -c` gives exactly `0 \n 0 \n` on a no-match, `1 \n` on a match, `0 \n` on a missing file.
- `scripts/dev-harness/player-scenario.sh:360` - `before11=$(log_count 'mpv unresponsive, restarting player')` is taken before any relaunch, so it holds `$'0\n0'`. Command substitution strips only trailing newlines.
- `scripts/dev-harness/player-scenario.sh:374` - `$(( $(log_count ...) - before11 ))` re-evaluates the variable's value as an arithmetic expression and dies: `arithmetic syntax error in expression (error token is "0")`. A failed arithmetic expansion is an **expansion** error: bash does not execute the simple command whose word failed, so `is` never runs, neither `pass` nor `fail` moves, and the run continues and exits 0. `set -e` does not change this (verified separately); `set -uo pipefail` at line 44 is not why it survives - **nothing** in bash turns this into a failure.
- The count: 72 unindented `is`/`ck` invocations plus the 2 indented ones inside P14's `for again in 1 2` loop (`player-scenario.sh:460,461`) executed twice = **76** expected assertions. `docs/STATUS.md:144` records 75/0. `--race-trials` does not change the count (the P13 loop at 412-429 contains only conditional `bad` calls). There are 12 `|| bad` guards, so the baseline's 80 outcomes are 75 executed assertions plus 5 fired guards.
- Blast radius is one function and one assertion: `log_count` is used only at lines 360 and 374, and line 374 is the only `$(( $( ... ) ))` in `scripts/`.
- The `| wc -l` idiom the file already uses at `player-scenario.sh:102` (`player_count`) is the correct replacement, and GNU grep terminates its last output line even on unterminated input, so it cannot undercount.

**And - this is the part that changes the value of the work - the restored assertion cannot distinguish the two trees.**

- The string being counted, `omarchy-iptv: mpv unresponsive, restarting player`, exists at exactly one place: `Service.qml:510`, inside `restartPlayer()`. Confirmed by grep: one hit in the whole file.
- The second relaunch the D-PLY-1 fix prevents is issued by `relaunchTimer.onTriggered`'s `playerUp` branch at `Service.qml:2485-2487`: `root.playSeq += 1; root.issuePlayerSession("restart", channel, "term")`. `issuePlayerSession` (`Service.qml:1067-1082`) logs nothing.
- A second entry into `restartPlayer()` cannot emit it either: `root.relaunched` is true by then (set at `Service.qml:514`) and is cleared only inside `play()` (`Service.qml:386`), so the second verdict takes the branch at `Service.qml:506` and logs `mpv unresponsive again, stopping the player`, which does not match the ERE.
- Therefore: expect **76/0 and 61/20**, not 60/21. The restored check will PASS on both trees.
- **The same blind spot is in QA's fallback.** `docs/STATUS.md:136`, `docs/STATUS.md:164` and `docs/QA-RESULTS.md:2407` all record that QA counted that same journal string by hand ("delta exactly 1, never 2"). That measurement counts the same non-discriminating string. **The property "exactly one relaunch, never a second at the healthy player" - half of the D-PLY-1 fix - has no machine-checkable witness anywhere, in the harness or in QA's manual count.**

### What is ASSUMED

- That the 76 total is right has been derived statically twice and matches `docs/STATUS.md:144`'s 75 exactly, but neither lane ran the scenario (it opens a real mpv window for ~60 s and wedges a player with SIGSTOP for ~21 s). The first re-run after the fix must confirm 76.
- The investigator's stated reason for rejecting `|| true | head -1` is a bash-semantics error: an empty but set variable evaluates to 0 in arithmetic context even under `set -u` (verified, `b=""; echo $(( 5 - b ))` prints 5). `| wc -l` is still the right fix - one line, always numeric, matches the file's own idiom - but do not repeat the stated reason.

### The fix - split into a code change and an investigation

**(a) Code, established, land it:** replace `scripts/dev-harness/player-scenario.sh:149` with

```
log_count() { grep -aE "$1" "$SCRATCH"/harness.log 2>/dev/null | wc -l | tr -d ' '; }
```

**(b) Code, established, land it:** add an **unguarded** assertion-count floor immediately **before** the summary at `scripts/dev-harness/player-scenario.sh:472`:

```
is "the harness ran every check" "$((pass + fail))" "76"
```

Do **not** write it as `(( fail > 0 )) || is ...` - that guard skips it on exactly the `--baseline` run whose summary most needs it, which is the rule-11 evidence path. Asserting `pass + fail` rather than `pass` works unguarded on both trees. Bash gives no way to turn a failed expansion into a failed test, so this floor is the only thing that closes the class.

**(c) Investigation, NOT a code change to `Service.qml` on anyone's initiative:** the "exactly one relaunch" property needs a witness that a timer-driven relaunch actually produces. Three candidates, in preference order - **the product owner and the shell lane pick one (Q3)**, no lane implements one unilaterally:
1. assert on the `seq` in `$SCRATCH/runtime/omarchy-iptv/player.lock`, or on `svc "d['player']['seq']"`, which `Service.qml:600-606` already exposes;
2. count `player restart` helper processes rather than a log line;
3. add a log line of its own at `Service.qml:2486`, which is the only option that makes the existing journal-counting QA procedure valid.

Until one of those lands, the honest record is: the harness has been one assertion short on every run, **and** that assertion as written would have passed on both trees anyway. Shipping (a) alone converts a silently-absent check into a silently-green one - decoration under CLAUDE.md rule 11.

### The test that proves it

**Deterministic, pure bash, no harness, no display, under one second:** write a scratch log, then assert `[[ $(log_count 'no-such-pattern' | wc -l) -eq 1 ]]`, `[[ $(log_count 'no-such-pattern') == 0 ]]`, `[[ $(log_count 'present') == 1 ]]`, and the missing-file case. The first assertion fails against line 149 as it ships and passes against the `wc -l` form. This is the CLAUDE.md rule 11 before/after pair.

**Deterministic:** prove the count floor fires - temporarily restore the old `log_count` and assert the run goes red rather than printing 75.

**Not deterministic, needs the display lane:** `pass + fail == 76` end to end, and the `--baseline 396a69a` comparison. Note in the run log that the baseline half is **expected to show the restored check PASSING**, per the trace above; if it goes red, that is new information about `Service.qml`, not the confirmation of an expectation.

---

## 3. D-PLY-10 - the player's shader cache escapes the plugin's tree

### What is KNOWN

- The defect as filed: `docs/STATUS.md:145` - the player writes mpv's shader cache into `~/.cache/mpv/`, two files at mode `600` during one containment cycle, outside README `Files it writes`. Privacy impact none: content-free, not keyed to stream content, `600`, and the directory predates the plugin.
- Confirmed on this machine: `~/.cache/mpv/` holds `shader_<hex>` files, all mode `-rw-------`, timestamps spanning the QA window.
- The containment already shipped covers cwd, screenshots and resume positions only: `bin/omarchy-iptv:2018-2044` (`player_dirs`), `bin/omarchy-iptv:2046-2075` (`mpv_launch_argv`), mirrored at `Model.js:1610-1617` (`playerDirs`) and `Model.js:1639-1666` (`buildMpvArgv`), pinned by `tests/fixtures/player-argv.json`. mpv still inherits `HOME`/`XDG_CACHE_HOME` for everything else - `spawn_detached` (`bin/omarchy-iptv:2351`) sets umask, cwd and fd hygiene but does not touch the environment.
- The knobs exist in the installed mpv (v0.41.0, verified by `mpv --list-options`, no window opened): `--gpu-shader-cache-dir` (String, default empty), `--icc-cache-dir` (String, default empty), and their enabling flags `--gpu-shader-cache` / `--icc-cache`, both default `yes`. `--demuxer-cache-dir` also exists but only takes effect with `--cache-on-disk`, which is not enabled.
- `player_dirs` derives everything from the socket path and the state directory, so a **runtime-dir** shader location needs no new plumbing: `runtime` is already computed at `bin/omarchy-iptv:2039`.
- The product owner has ruled: **contain it**, redirecting into the plugin's own tree, consistent with the shipped containment - not a README line.

### What is ASSUMED

- That `--gpu-shader-cache-dir` actually stops writes to `~/.cache/mpv/`. The option exists and parses; it cannot be behaviourally confirmed without a GPU video output, which means a window, which means the display lane. A `--vo=null` mpv compiles no shaders. **Live-lane item.**
- That `--icc-cache-dir` is worth setting in the same change. No ICC file was observed in the QA cycle, but the option has the same default-to-`$XDG_CACHE_HOME` shape, so leaving it is a known second hole. Recommend setting both.

### The fix

1. `bin/omarchy-iptv:2018-2044` (`player_dirs`) - add one entry, `"shaderCache": os.path.join(runtime, "shader-cache")`, with the docstring extended to say why it is ephemeral: a shader cache is a pure performance artifact, content-free and regenerable, so the runtime directory (0700, already ensured for the socket, gone at logout) is the right home and adds **no new durable path to document**. See Q2 for the durable alternative.
2. `bin/omarchy-iptv:2046-2075` (`mpv_launch_argv`) - append `--gpu-shader-cache-dir=%s` and `--icc-cache-dir=%s` from `where["shaderCache"]`, **before** the user's `mpv_args`, exactly as `--screenshot-dir` and `--watch-later-dir` are placed, so a user token can still override.
3. `Model.js:1610-1617` (`playerDirs`) and `Model.js:1639-1666` (`buildMpvArgv`) - the same two lines, same order. The two mirrors move in one commit or the parity test goes red.
4. `tests/fixtures/player-argv.json` - extend the `playerDirs` cases and the argv vectors. This one fixture is what pins the JavaScript and Python mirrors to each other.
5. `bin/omarchy-iptv:2726` (`ensure_player_dirs`) - create the new directory with the rest, so the 0700 guarantee covers it.
6. `docs/ARCHITECTURE-PLAYER.md` (the PO-11 section) and `README.md` "Files it writes" - record the redirect. The runtime directory is already listed, so if Q2 resolves to "ephemeral" this is one clarifying clause rather than a new path.
7. **Do not** reserve `--gpu-shader-cache-dir` / `--icc-cache-dir` in `MPV_RESERVED` (`bin/omarchy-iptv:1933-1939`) without a ruling. The reservation reasoning on record is a **privacy** one - `--watch-later-dir` is reserved because a resume record names a stream path, `--screenshot-dir` is deliberately not reserved because the user may want their screenshots elsewhere. A content-free shader cache falls on the `--screenshot-dir` side of that line. See Q2.

### The test that proves it

**Deterministic, no display:** the `player-argv.json` vectors run by both `tests/Model.test.js` (`Model.buildMpvArgv`, `Model.playerDirs`) and `tests/test_player.py` (`mpv_launch_argv`, `player_dirs`) - the argv carries both options, pointing inside the runtime directory, with user tokens still landing after them. Rule 11: mutate by dropping the option from one mirror and show the parity test goes red in the other. A `tests/test_player.py` case asserting `ensure_player_dirs` creates the directory at 0700.

**Live (display lane), because the unit gate cannot see it:** with a real windowed player, `ls ~/.cache/mpv` before and after a containment cycle - no new `shader_*` file - and the redirected directory populated at mode 0600 inside a 0700 parent. This is the only proof that the option actually diverts the write; everything above only proves the argv is built.

---

## 4. D-PLY-11 - now-playing names one channel while the player plays another

### The cause was REFUTED. For the cause, the fix is investigation, not a code change.

The finding proposed three orderings and ranked O1 ("the rollback that fires with a zap queued behind it") as most likely. The skeptic refuted the ranking and refuted O2 outright:

- **O1's trigger has no demonstrated cause.** It needs the burst's first reply to be an error that is neither `not_running` nor a first `ipc_error`. `playRetries` is reset to 0 by every `play()` (`Service.qml:387`), so a first `ipc_error` always takes the retry branch at `Service.qml:989-995`, never the rollback. That leaves `no_output` - a helper that crashed or was killed. Nothing kills it: `controlProc` has no watchdog (`Service.qml:2609-2617`), and `runControl` refuses a second helper while one is running (`Service.qml:950`), so an eight-call burst spawns **one** control helper at a time. The "eight concurrent helper spawns cause CPU contention" story the ranking rests on describes a concurrency this code cannot create - and the finding's own O5 says so.
- **O2 as written cannot diverge.** It claims `Service.qml:981-988` -> `1011` races a `player start` against a `play`. Both execute in the same synchronous turn, and both read the same `root.nowPlaying`: `startPlayer(channel)` at `Service.qml:985` takes `channel = root.channelIndex[root.nowPlaying.id]` and `issuePlayerSession` re-reads `root.nowPlaying` at `Service.qml:1069-1073`, while `drainPendingPlay` at `Service.qml:1011` issues `pendingPlayId`, which in that same turn is also `nowPlaying.id`. There is no older intent on that path.
- **Two of the three "I ran it" evidence items do not show what they are said to show.** EXPERIMENT 1 holds `player.lock` from the test process for seconds - contention the shell cannot create, since `runPlayer` refuses a second player verb while `playerProc.running` (`Service.qml:1086`) and the only detached lock-takers are the two `player stop` calls, both of which null `nowPlaying` first. EXPERIMENT 2 demonstrates documented additive-flag behaviour (`bin/omarchy-iptv:1789-1799`, `docs/ARCHITECTURE-PLAYER.md:271-273`) with no shell in the picture; it proves "stash disagrees with media-title", not the reported shell-versus-player divergence.
- **The skeptic's replacement is also a hypothesis, not a traced fact.** Its mechanism is that `playerPending` makes `playerUp` true synchronously (`Service.qml:228`, `Service.qml:1077`), so every call after the first in a **cold** burst takes the zap branch at `Service.qml:419-425` and spins a `play` helper roughly every 160 ms at a socket mpv has not bound, and when mpv binds, a zap can slip inside the ~20 ms shadow of `wait_for_socket`'s poll (`SPAWN_POLL_S = 0.02`, `bin/omarchy-iptv:1925`, `2480-2491`) and load the last intent just before `player start`'s `apply_channel` (`bin/omarchy-iptv:2827`) overwrites title, force-media-title and stash with the first. That rate - a ~20 ms window sampled every ~160 ms - is of order 10-12% per cold run, which fits 1-of-8, 0-of-6, 0-of-4 far better than O1 does. It is a good hypothesis. **It has not been reproduced.**

**Therefore: no lane implements a cause-directed fix for D-PLY-11 in this round.** Specifically, do **not** give `play` a `--seq` and the player lock, and do **not** gate the rollback at `Service.qml:1000`, until the investigation below says which family fired. Both are live changes to the zap path and one of them (Q4) would make things worse.

### What IS known, and is independently a defect regardless of which ordering fired

Both parties verified all of these line by line. They are worth fixing on their own merits and they are not contingent on the cause.

- **R1 (the ordering-discipline gap) is a fact.** `play`'s subparser has no `--seq` (`bin/omarchy-iptv:3490-3499`, confirmed with `--help`); `cmd_play` (`bin/omarchy-iptv:1789-1824`) never calls `acquire_lock`, `check_seq` or `write_lock_record`; those three appear together at only two call sites in the whole file, `player_start` (`bin/omarchy-iptv:2814-2816`) and `player_stop` (`bin/omarchy-iptv:2855-2857`). The accurate statement is narrower than the finding's: ordering is defined **among** player verbs and **among** zaps (one control slot), and **undefined between the two slots**. `docs/ARCHITECTURE-PLAYER.md:550-570` introduces the seq for a specific inversion it names - two `execDetached` player verbs racing for the lock - and never says the zap verb carries it; `docs/ARCHITECTURE-PLAYER.md:230-232` explicitly freezes `play`'s spelling.
- **R2 (a nowPlaying write with no matching load) is a fact, line for line.** `Service.qml:1000` restores `nowPlaying = previousPlaying` for every play error that is not `not_running` and not a retryable `ipc_error`; `Service.qml:1011` then unconditionally calls `drainPendingPlay()`, which issues `playArgs(id)` for a different id at `Service.qml:1022` and never touches `nowPlaying`; `playArgs` only appends `--scope`/`--since` when `np.id === key` (`Service.qml:438-448`); `cmd_play` computes `session = bool(scope or since)` (`bin/omarchy-iptv:1803`) and `apply_channel` skips both stash writes when stash is None (`bin/omarchy-iptv:2639`, `2649-2656`).
- **R3 (no reconciler while attached) is a fact, and it is the severity.** The socket subscribes to `request_log_messages error` and `observe_property idle-active` only (`Service.qml:1478-1479`); `parsePlayerEvent` extracts no channel identity from start-file/end-file, only `playlist_entry_id` (`Model.js:1813-1830`); `statusHealthy` reads only `ok` and `running` (`Model.js:1255-1257`); `cmd_status` (`bin/omarchy-iptv:1869-1878`) emits `mediaTitle`/`pathHost`/`paused`/`idle`/`mpvVersion` and **not** the `"stash":{...}|null` field `docs/ARCHITECTURE-PLAYER.md:271-273` says it gains - only the error path's additive `process` field was implemented (`bin/omarchy-iptv:1886-1888`); and no `applyProbe` trigger fires for an attached healthy player. **Whatever the mechanism is, this is why it is permanent.**
- **The warm case is provably clean.** With a warm attached player and all-ok replies, `pendingPlayId` is set together with `nowPlaying` at every writer (`Service.qml:399`/`423`, `1055`, `2504`), so the last zap issued always equals `nowPlaying.id`. Divergence therefore requires exactly one of: a rollback, a player-verb `apply_channel` landing last, or a probe rewrite. The finding's enumeration is complete for the warm case - that is a real result and it should be kept.
- **`rememberEntry` records the wrong owner.** Both call sites pass `root.nowPlaying` (`Service.qml:1007`, `Service.qml:1124`) instead of the reply's own `{id,name}`, which both helpers return (`bin/omarchy-iptv:1812-1813`, `2843-2845`). In any burst the ring maps an entry id to the intent current when the *reply* landed, which is exactly the case `docs/ARCHITECTURE-PLAYER.md:492-499` built the ring for. Consequence: the "Stream failed" toast and PO-3's red row name a channel that never failed.
- **The `no_output` asymmetry is real.** `Service.qml:965` guards the status branch ("neither healthy nor a strike, so a missing subcommand never reaps a working player"); the play branch has no equivalent and falls into the rollback. Both `""` and a python traceback parse to `{code:"no_output"}` (`Model.js:1170-1172`), verified in node by both parties.
- **`controlProc` has no watchdog** (`Service.qml:2609-2617`) while `playlistProc`, `epgProc` and `playerProc` all do.
- **The stash's seq is hardcoded 0** (`bin/omarchy-iptv:1808-1810`) and nothing reads it - `player_probe` takes seq from the lock record (`bin/omarchy-iptv:2887`). The one field that could make a stale stash detectable is both unpopulated and unread. `docs/ARCHITECTURE-PLAYER.md:400-402` shows it carrying a real seq.
- **CLAUDE.md rule 12 violation:** `playArgs` appears 4 times in `Service.qml` (425, 438, 1022, 2505) and **0 times** in `tests/Model.test.js` and `tests/Model.spec.qml`. The decision that skips the stash write is pure logic stranded in a QML component. `Model.js` already exports `seqArg`, `playerSessionArgv`, `playerStartArgv`, `playerStopArgv`, `playerRestartArgv`, `playerProbeArgv` - every argv builder except the zap's.
- **Two error codes reach the rollback that nobody listed:** `unknown_channel` and `no_cache`, both reachable if the cache is rewritten by a refresh mid-burst, because `cmd_play` resolves the channel before it connects (`bin/omarchy-iptv:1805-1806`). `busy` would be a third if `play` ever takes the lock.
- **The "the fork is never a correctness gate" comments are false** (`Service.qml:364-366`, `Service.qml:414-418`). Both parties agree, for different reasons; neither reason is yet established, which is itself the point - the claim rests on nothing measured.

### What is ASSUMED - and is the whole investigation

1. **Whether the failing burst was warm or cold.** This is *the* discriminator: the cold fork race needs cold, O1 needs warm. It is not in the evidence. The surviving artefacts lean cold-capable - the run sampled window **count** 80 times (`/tmp/claude-1000/omarchy-iptv-qa8/logs/burst-wins.txt`, all `1`), a measurement that only means anything around a start.
2. Whether the journal carried `omarchy-iptv: play failed:` (`Service.qml:998`) during the failing burst. That single line separates O1 from everything else. Not captured.
3. What `user-data/omarchy-iptv` read at the moment of divergence. Under O1 the stash agrees with the **wrong** `nowPlaying`; under the ordering family it agrees with the **player**. One `socat` read settles it. Not taken.
4. Whether `Process.onExited` can fire before a `StdioCollector` with `waitForEnd: true` has drained. If yes, `no_output` is common and O1 becomes plausible again. Nobody read Quickshell's source; `docs/SPIKE-QUICKSHELL-SOCKET.md` covers the Socket type only.
5. A simpler artefact hypothesis nobody excluded: `apply_channel` sets `title` and `force-media-title` with `try_command` and merely **logs** a refusal (`bin/omarchy-iptv:2631-2634`). If both refusals happened on the winning zap, the titles keep the previous name while the shell is **right** - and because `t:qa.plain` and `t:qa.live` share `http://127.0.0.1:8791/test.ts` (`tests/fixtures/qa-player/qa-player.m3u:27-30`), nothing in playback would contradict it. Unlikely, but it is the only hypothesis in which the shell is correct.
6. **PLY-LIFE-03** ("Enter hammered on two channels during a cold start, 20 times, starting from nothing playing", `docs/QA-PLAYER.md:141`) - the one live case that exercises the cold path directly - was **not re-run** in this pass. There is no PLY-LIFE-03 row anywhere in `docs/QA-RESULTS.md`. The cold-hammer case is untested at `b16b479`, not proven clean.

### The fix, in the only order that is defensible

**Step 1 - investigation, no behaviour change (helper lane, deterministic, no display):**

- **T-A** `tests/test_player.py::test_an_older_player_start_re_applies_its_channel_over_a_newer_zap`. Bind the stub via `player start --id A --seq 1`; run `play --id B --scope g:uk --since 3000` to completion; run `player start --id A --seq 1` again (it adopts). Assert the final `force-media-title` and `user-data/omarchy-iptv` name B. Today they name A, 1/1. This is the finding's T1 with the artificial lock hold **deleted** - the lock was never the mechanism, and removing it makes the test honest about what is actually missing: a `player start` has no way to learn a newer intent already landed.
- **T-B** the cold interleaving in a box, made deterministic by injecting at a point that already exists: `probe_client` (`bin/omarchy-iptv:2466-2477`) will not return until mpv answers `mpv-version`, while `cmd_play` demands no such handshake. Add a stub mode that binds the socket but withholds the `mpv-version` reply until released. Start `player start --id A --seq 1` as a subprocess, wait for the socket file, run `play --id H --scope g:QA --since 3000` to completion, release, join. Assert the last loadfile and title are H. The stub's gate decides the order, not a sleep - 1/1, no timing luck.
- **T-C** `Model.playFork({playerPending, socketAttached, stopping, controlBusy})`, lifted from `Service.qml:419-427` plus the `playerUp` definition at `Service.qml:228`. Vector: `playerPending && !socketAttached` must **queue** the intent, never emit a zap. This is a pure-logic *characterisation* test in step 1; changing the shipping behaviour to match it is step 3, not step 1.

Together T-A and T-B pin the two mechanisms independently of which one fired in the field. Neither authorises a fix on its own.

**Step 2 - the severity fix, which both parties agree on and which is independent of the cause (helper + shell lanes):**

Implement the reconciliation input the design already specifies and the code never grew.
- `bin/omarchy-iptv:1869-1878` - `cmd_status` emits `"stash":{...}|null`, per `docs/ARCHITECTURE-PLAYER.md:271-273`.
- `bin/omarchy-iptv:1808-1810` - stop writing a hardcoded `0` into the stash's seq; carry a real value so the two sides can be **compared** rather than merely differed.
- `Model.reconcileVerdict(statusStash, nowPlaying, seqs)` - a new pure function with vectors for agree / disagree / stash-null / different sourceKey, wired into the status branch at `Service.qml:961-972`.

**The repair action is deliberately left open (Q5).** Do **not** relabel `nowPlaying` from the stash: in every ordering in this family the user's last intent is the side the shell holds and the player is the stale side, so relabelling makes the UI name the channel the user did not ask for. The candidate repairs are (a) re-apply the intent, i.e. re-zap, or (b) decide from the seq which side is newer - which is why the stash seq above has to land first. Detection this round; repair once the PO rules.

**Step 3 - the independently-verified defects, which need no cause (shell lane):**
- `Service.qml:1007` and `Service.qml:1124` - `rememberEntry` takes `{id, name}` from the reply, via a lifted `Model.replyTarget(status, nowPlaying)`.
- `Service.qml:996-1001` - give the play branch the same `no_output` guard the status branch has at `Service.qml:965`: a reply we could not read is not evidence that the switch failed. Extend the same treatment to `unknown_channel` and `no_cache`.
- `Service.qml:2609-2617` - give `controlProc` the bounded watchdog the other three Processes have; on timeout treat the reply as "cannot tell", never as a failed switch.
- Lift `playArgs` to `Model.zapArgs` and the failed-play verdict to `Model.playFailureVerdict`, per CLAUDE.md rule 12, and cover both with vectors in `tests/Model.test.js`.
- `Service.qml:364-366` and `Service.qml:414-418` - either withdraw the "never a correctness gate" claim or re-word it to what is actually established. Do not leave a comment asserting something no one has measured.

**Explicitly NOT this round:** `play --seq` + lock (Q4); gating the rollback on `pendingPlayId` (it changes behaviour for the lone-failed-zap case the rollback was written for, and it is a cause-directed fix for a cause nobody established); `probeVerdict`'s `appliedSeq` term (it fixes O3, which is ranked below two unestablished candidates and whose trigger is unreachable while the observer is attached).

### The test that proves it - and why part of it can never be deterministic

**Deterministic, no display:** T-A, T-B, T-C above; the `Model.reconcileVerdict` vectors; the `Model.replyTarget` vector (a play reply `{id:'t:qa.live', name:'QA Live Stream', entryId:2}` applied while `nowPlaying` is `t:qa.plain` must record entry 2 -> `t:qa.live`; mutate by restoring the `nowPlaying` argument to show red); the `Model.playFailureVerdict` vectors for `no_output`, `unknown_channel`, `no_cache` and `busy`; a `tests/test_player.py` case that `status` carries `stash` (red today).

**Must remain probabilistic:** the field defect itself. It is 1-in-8 on a burst that only concurrent IPC can produce, and every "deterministic" test above is deterministic **only because it stubs or gates the race**. That is the correct design, and it means the unit suite will still never fail against D-PLY-11 as it occurs in the field. Say so in the commit rather than implying coverage.

**Live (display lane), and this is the deliverable that unblocks step 3's cause-directed successor:** re-run TC-PLAY-10 with the procedure extended to capture, at the moment of divergence: (i) **whether the burst was warm or cold** - the single missing fact; (ii) `user-data/omarchy-iptv` over `socat`; (iii) `playlist/current/id`; (iv) `ipc status`, which already carries `player.seq` and `player.entryId` (`Service.qml:600-606`) and which QA captured neither of; (v) the shell journal, for `omarchy-iptv: play failed:`. Stash agrees with the player and `nowPlaying` is the odd one out -> the ordering family. Stash agrees with the wrong `nowPlaying` and the journal carries the `play failed` line -> O1. **Also re-run PLY-LIFE-03** (`docs/QA-PLAYER.md:141`), which exercises the cold path directly and was not run in this pass.

---

## 5. The harness audit - ranked by what each broken check would let through

A check that never runs is the same class of problem as the bug this project shipped in its second release: the suite was green and the defect was live. Every item below is a check whose green is not evidence. They are ranked by consequence, not by effort.

### Tier A - a false all-clear on a security, privacy or containment constraint

| # | Where | What it lets through | Fix |
|---|---|---|---|
| A1 | `scripts/qa-live.sh:186` | `grep -nE '(https?\|rtsp\|rtmp)://[^ ]*[@?]\|password=\|username=' journal.txt qs-log.txt && echo "REDACTION FAILURE" \|\| echo "redaction ok"` prints **"redaction ok"** when the files are empty, when `journalctl` or `qs log` (lines 175, 177) failed and wrote only an error, and when the capture window caught nothing. This is the S-08 / CLAUDE.md constraint 5 redaction evidence for the **live** pass. Its only positive control, `grep -c 'omarchy-iptv'` at line 188, is printed **after** the verdict and never asserted. A real credential leak in a run whose capture failed reads as clean. | Assert `(( $(grep -c 'omarchy-iptv' journal.txt) > 0 ))` **before** the sweep and fail the phase if it is 0. |
| A2 | `scripts/qa-live.sh:161`, `:163` | `find "$PLUGIN_DIR" -newer "$PLUGIN_DIR/manifest.json"` ("expect nothing") and the symlink `find` both print nothing when `$PLUGIN_DIR` does not exist - stderr is discarded. "No writes inside the plugin directory" (CLAUDE.md constraint 4) reads as proven when the directory was never examined. | Assert the directory exists and that the `find` examined a non-zero file count before reporting the absence of hits. |
| A3 | `scripts/qa-live.sh:207` | `diff <(jq -S . shell.json.before) <(jq -S . "$SHELL_JSON") && echo "shell.json restored"`. If `jq` fails on either side (missing snapshot, malformed file) both substitutions are empty, `diff` exits 0, and the script reports **"shell.json restored"**. A false all-clear on the snapshot/restore guarantee of "Working in parallel" rule 5, on the phase that touches the user's real config. | Assert both `jq` invocations succeeded and both outputs are non-empty before diffing. |
| A4 | `scripts/dev-harness/sources-scenario.sh:291`, `:292`, `:144` | `! grep -E "sourceProbeFinished\|sourceSwitched\|updateEntryInline" "$LOG" \| grep -qE "://\|$FIX"` PASSES on an empty log and on a log that leaks `http://user:pw@host/x` on a non-matching line; it fails only when a leak sits on a line carrying one of the three labels. `:292` and `:144` pass outright when the IPC is dead (`ipc()` at line 42 swallows stderr). This is the privacy sweep for S-08 / SR-privacy and the last check in the file - the one most likely to be cited as evidence. **Correction to the record:** the stated cause (`set -o pipefail` making the pipeline status 1 when the first grep matches nothing) is wrong - the expression behaves identically with pipefail on and off in all six tested combinations, because the second grep already exits 1 on empty input. The real cause is simply the absent positive control. **Also narrower in context than stated:** `:156` asserts positively 135 lines earlier that `updateEntryInline io.github.rmcdavid.iptv keys:` is in the log. The vacuous window is real but requires a run that died between 156 and 291. | Capture `n=$(grep -cE 'sourceProbeFinished\|sourceSwitched\|updateEntryInline' "$LOG")`, assert `(( n > 0 ))`, then run the leak grep against those lines. For `:292`/`:144`, assert the IPC answered (non-empty) before asserting what it does not contain. |
| A5 | `scripts/dev-harness/player-scenario.sh:104`, `:252-257`, `:290-291` | `cmdline_of() { tr '\0' ' ' <"/proc/$1/cmdline" 2>/dev/null; }` with an empty `PID1` collapses `/proc//cmdline` to `/proc/cmdline` and returns the **kernel command line** (reproduced on this machine). All six negative S-03 checks at `:253-257` then compare the kernel command line against the secrets and pass. This is TC-PLAY-08 inverted: no URL, credential, token, header value or channel name on mpv's argv. **Severity corrected from high to medium:** P2 carries its own positive control four lines down - `:258` asserts `--idle=once`, `--wayland-app-id=omarchy-iptv` and `--ytdl=no` are present, none of which appear in the kernel cmdline, and `:244` asserts exactly one player - so an empty `PID1` turns the run red anyway. P5's `:291` is the genuinely unguarded half, preceded only by `:287`'s same-pid check. This is a check that passes vacuously **inside a run that is already red**, not one that ships a green lie. | `cmdline_of() { [[ -n ${1:-} ]] \|\| return 1; ... }`, plus `ck "the command line was actually read" '[[ -n "$cmd" ]]'` before each sweep, including before `:291`. |
| A6 | `scripts/qa-player-scenarios.sh:83-96` | `scratch_player_pids` and `signal_scratch_player` are defined and **never called** (verified: each name appears once in the file, plus one internal call from the other dead function). The header at `:27-28` advertises "it refuses outright to signal a process whose `--input-ipc-server` is not under the scratch tree" - a **safety** guarantee implemented entirely by dead code. The killing that actually happens goes through `"$RUN" reap` / `shell-stop` and `kill $(cat notify.pid)` at `:227`. `run.sh`'s reap is scratch-scoped so the outcome is currently safe, but the script's own stated safety mechanism has never executed. | Route every signal through `signal_scratch_player`, or delete the claim from the header. A safety claim backed by dead code is worse than no claim. |

### Tier B - a scenario or gate with no verdict and no non-zero exit

| # | Where | What it lets through | Fix |
|---|---|---|---|
| B1 | `scripts/qa-player-scenarios.sh:100-101`, `:173`, `:444` | The six PLY-H11..H16 scenarios **assert nothing at all**. `step()` and `sh_step()` run the command and discard its exit status; the bodies are built entirely from `step`/`sh_step`/`expect`/`note`. `svc()` (`:107`), `wins()` (`:114`) and `mpvq()` (`:115`) - the helpers that would let a scenario assert - are defined and never called. `main` ends on `((APPLY)) \|\| printf ...` at `:444`, which is true when `APPLY=1`, so `run all --apply` exits 0 no matter what happened. `cmd_check_harness` ends on a printf at `:173` and returns 0 even with fails - so a **missing harness verb** exits green. Six scenarios covering PLY-RST-02/03/06/08/14/16 and PLY-LIFE-06/07, including H15 whose own note reads "A WINDOWED PLAYER THAT NOTHING CAN REACH IS A P1 FAIL" (`:327`), have no machine-checkable verdict. | Minimum this round, one line each: `cmd_check_harness` exits non-zero when `fail > 0`, and `run` prints a pass/fail summary and exits 1 when `fail > 0`. Full conversion of the EXPECT lines into `is`/`ck` using the dead `svc`/`wins`/`mpvq` helpers is a follow-on. |
| B2 | `scripts/qa-sources-scenarios.sh:1037` | `check-harness) cmd_check_harness; exit 0 ;;` - the Sources capability gate exits 0 unconditionally, printing `MISSING` lines with a green status. Same one-line fix as B1's gate; it was missed in the player half of the audit. | `cmd_check_harness; (( fail == 0 )) \|\| exit 1`. |
| B3 | `scripts/qa-sources-scenarios.sh:114-131` and its call sites | `harness_start()` returns 1 after 30 s with "harness did not answer within 30 s" on stderr, but every call site invokes it bare and the file has no `set -e`. Confirmed: 9 direct call sites plus `common_start` at `:290`, itself called bare from 10 further places (324, 352, 383, 429, 601, 643, 701, 737, 792, 819). All sixteen SRC-H* scenarios then execute every remaining step against a dead harness, printing empty output under each EXPECT line as though the step had been performed. This script has **no pass/fail accounting and no non-zero exit path at all**. | `harness_start ... \|\| return 1` at every call site and in `common_start`, plus a visible `SETUP FAILED` banner. |
| B4 | `scripts/dev-harness/player-scenario.sh:149`, `:374`, `:472` | D-PLY-9 itself: one assertion silently skipped on every run of both trees, and no floor that would notice. See section 2. | Section 2 (a) and (b). |

### Tier C - a scenario measuring a tree or fixture that is not the one under test

| # | Where | What it lets through | Fix |
|---|---|---|---|
| C1 | `scripts/dev-harness/run.sh:110-120` (`prepare_root`) | The exit status of `ln -sfn` (113, 114) and of both `cp` calls (115, 117) is discarded. A failed `cp "$PLUGIN_ROOT/Model.js" "$root/Model.js"` silently leaves the **previous run's** `Model.js` in place while `OMARCHY_IPTV_ROOT` still points `Service.qml`/`Guide.qml` at the new tree. On the `--baseline` path that is a silently mixed tree producing rule-11 "evidence" nobody can trust. Nothing anywhere verifies the copied `Model.js` matches the tree under test. | Check every status; after copying, assert the destination hashes equal the source. |
| C2 | `scripts/dev-harness/run.sh:316-325`, `:246` | Two problems in one block. (i) No `printf %q`: `echo "export OMARCHY_IPTV_PLAYLIST=\"$OMARCHY_IPTV_PLAYLIST\""` re-expands (or executes) a path containing `$`, a backquote, a backslash or a double quote when `restart-shell` sources it at `:246`. That is an argv/shell-injection path in test tooling, the shape CLAUDE.md constraint 2 forbids. (ii) **Sharper:** `last-start.env` records `OMARCHY_IPTV_ROOT` but **not** `OMARCHY_IPTV_PLUGIN_ROOT`, and `restart-shell` (`:235-249`) sources it and then calls `prepare_root`, which copies `Model.js` from `$PLUGIN_ROOT` - computed at `:60` from the **caller's** environment. Any `run.sh restart-shell` invoked without `OMARCHY_IPTV_PLUGIN_ROOT` exported (a plain terminal after a baseline `--detach`) copies the **current repo's** `Model.js` over the baseline's while `Service.qml` stays at the baseline. `player-scenario.sh` is safe only by accident, via its `export` at `:206`. P4 (`:268`), every P13 trial (`:416`) and P14 (`:449`, `:457`) all go through `restart-shell`. | `printf 'export X=%q\n'` for every line of the block; record `OMARCHY_IPTV_PLUGIN_ROOT` too; and have `restart-shell` assert after sourcing that the key values are byte-identical to what `--detach` recorded. |
| C3 | `scripts/dev-harness/run.sh:60` | `PLUGIN_ROOT=$(cd "${OMARCHY_IPTV_PLUGIN_ROOT:-$ROOT}" && pwd)` with no `set -e`: a failed `cd` leaves `PLUGIN_ROOT` empty and every later `"$PLUGIN_ROOT/bin/omarchy-iptv"` and `"$PLUGIN_ROOT/Model.js"` becomes a path at `/`. Nothing checks it. | `[[ -n $PLUGIN_ROOT ]] \|\| die`. |
| C4 | `scripts/dev-harness/player-scenario.sh:268`, `:416`, `:449`, `:457` | The exit status of `"$RUN" restart-shell` is never checked. `run.sh:239-242` exits 2 when `last-start.env` is absent. A failed restart leaves the old shell dead and no new one; P4/P13/P14 then measure nothing while their `wait_log ... \|\| bad` guards attribute it to the wrong cause. | `\|\| { bad "restart-shell failed"; exit 1; }`. |
| C5 | `scripts/dev-harness/sources-scenario.sh:89-91` with `scripts/gen-playlist.py:229` | The 10k fixture is regenerated only when absent (`if [[ ! -f $FIX/gen-10k.m3u ]]`), `$FIX` survives `"$RUN" clean` (`run.sh:220` removes cache/state/runtime/shots only), the generator's exit status is unchecked, and `write_out` is a plain non-atomic `with open(path, "wb")`. An interrupted generation, or a run with a different `OMARCHY_IPTV_SCENARIO_CHANNELS` (`:33`), leaves a stale or truncated playlist every later run reuses. **Severity corrected:** `:154`, `:155` and `:169` compare against `$CHANNELS_10K` and the PERF stats line at `:166` greps for `\($CHANNELS_10K channels`, so a stale fixture produces a loud FAIL, not a silent pass. This is a **false-red / flakiness hazard**, not decoration - but the non-atomic write and the unchecked generator status are real. | Check the generator's status; validate with `[[ $(grep -c '^#EXTINF' "$FIX/gen-10k.m3u") == "$CHANNELS_10K" ]]` and regenerate on mismatch rather than trusting `-f`; make `write_out` atomic (`<path>.tmp` then `os.replace`). |
| C6 | `scripts/dev-harness/sources-scenario.sh:100-108` | `SILENT_PORT=$(cat "$SCRATCH/silent.port")` after a fixed `sleep 0.3`, with no non-empty check. If the background python has not flushed, the cancel-probe block at `:223-232` builds `http://127.0.0.1:/slow.m3u` and `:226` goes red for a reason nobody will read as a race. | Poll for a non-empty port file with a deadline; `bad` on timeout. |
| C7 | `scripts/dev-harness/sources-scenario.sh:111` | The harness is started with `--timeout 120`, while the scenario's own waits sum well past that (a 30 s `wait_log` at `:153`, a 20 s at `:136`, ten switch loops, several 15 s waits). If quickshell is killed mid-run, every later `svc` returns empty and most checks go red - **but `:291` and `:292` PASS**. That is the concrete and most plausible path by which the privacy sweep (A4) reports clean on a dead harness. | Raise the timeout to exceed the scenario's own worst-case, and assert the harness is still alive at the summary. |

### Tier D - capability gates satisfied by a comment or by the wrong parser

| # | Where | What it lets through | Fix |
|---|---|---|---|
| D1 | `scripts/qa-player-scenarios.sh:163` | `grep -q -- "$v" "$RUN"` for `--detach --serve --instance --playlist --timeout` matches `run.sh`'s **header comment** (`run.sh:31`, `:33`) as readily as its parser, so deleting `--detach) DETACH=1; KEEP_PLAYER=1 ;;` (`run.sh:274`) leaves the check green. Line 160 does it correctly, anchoring on the case arm (`grep -qE "^  $v\)"`). | Anchor on the case arm the way `:160` does. |
| D2 | `scripts/qa-player-scenarios.sh:166` | `"$HELPER" ${v#player } --help \|\| "$HELPER" player "${v#player }" --help`. For `player stop` the **first** branch succeeds because the helper has an unrelated top-level `stop` verb (`bin/omarchy-iptv:3501`, the M1 mpv-IPC stop) - verified by running both forms. So `helper player stop` reports ok even if the `player stop` subparser (`bin/omarchy-iptv:3534`) were deleted. **Narrower than "same family" implies:** of the five probed verbs only `stop` collides; `start`, `probe`, `restart` and `orphan-check` have no top-level parser. | Drop the first branch; probe only `"$HELPER" player "${v#player }" --help`. |
| D3 | `scripts/qa-sources-scenarios.sh:1006`, `:1007` | `grep -qE 'validateSourceUrl\|sourceView\|xtreamUrls' Model.js` and the `Service.qml` equivalent are satisfied by a **comment** mentioning the name. **Correction to the record:** `have_verb()` at `:148` is `grep -qE "function $1\("`, which anchors on `function <name>(` and is **not** satisfied by a comment - that part of the finding is wrong and should not be carried into the fix. | Invoke the function or the harness IPC verb rather than grepping the source. Leave `have_verb` alone. |

### Tier E - `scripts/check.sh`, the gate everyone treats as the quality bar

| # | Where | What it lets through | Fix |
|---|---|---|---|
| E1 | `scripts/check.sh:64-65` | `ok "qml spec ($(grep -c '^PASS' /tmp/omarchy-iptv-qmltest.log) passed)"` - the count is interpolated into a message and never asserted, and `grep -c`'s status is discarded inside the argument. A `qmltestrunner` that exits 0 having run **zero** test functions prints `ok   qml spec (0 passed)` and the gate stays green. CLAUDE.md and `docs/QA-PLAYER.md:444` cite "42 passed" / "47 passed" as evidence; the gate itself would accept 0. A renamed or emptied `tests/Model.spec.qml` is invisible. | Capture the count and assert a floor, ideally against a recorded expected count the way the node runner prints one. |
| E2 | `scripts/check.sh:35-36` | `for file in "$ROOT"/*.qml "$ROOT"/tests/*.qml` lints `BarWidget.qml`, `Guide.qml`, `Service.qml` and `tests/Model.spec.qml`. `scripts/dev-harness/shell.qml` - the harness fake that **every scenario in this repo runs against**, and the thing CLAUDE.md rule 10 says must never be more forgiving than the real host - is never linted. And `[[ -f $file ]] \|\| continue` means an unmatched glob silently lints nothing while the gate reports green. | Add `"$ROOT"/scripts/dev-harness/*.qml`; count the files actually linted and fail the step if the count is 0. |
| E3 | `scripts/check.sh:75-81` | The ASCII gate iterates a hand-maintained list and `[[ -f $file ]] \|\| continue` drops directories, so it never scans `scripts/gen-playlist.py` (a `.py` source, which CLAUDE.md rule 8 covers), any of `scripts/*.sh` or `scripts/dev-harness/*`, or anything under `tests/fixtures/*/`. Three fixture subdirectories exist, and `tests/fixtures/qa-player/qa-player.m3u` and `tests/fixtures/qa-sources/nonascii/paste-rtl.txt` carry non-ASCII bytes **today**, unscanned. The gate is green partly by accident: the deliberately non-ASCII `qa-nonascii/` tree is skipped because it is a directory, not because it was excluded on purpose. | Drive the list from `git ls-files -z` over `*.js *.py bin/* *.json scripts/*.sh scripts/dev-harness/*.sh` and the fixture trees, excluding `*/nonascii/*` and `tests/fixtures/qa-nonascii/*` by explicit name so the exclusion is visible rather than incidental. Expect this to turn the gate red on first run; that is the point. |
| E4 | `scripts/check.sh:15`, `:29-31` | `QMLROOT=${QMLROOT:-/tmp/qmlroot}` is a fixed path in shared `/tmp`; `mkdir -p` and both `ln -sfn` statuses are discarded. If the directory exists owned by another user the symlink refresh fails silently and qmllint resolves `qs.Commons` / `qs.Ui` against whatever is planted there - the import root of the entire lint gate. Low probability on a single-user machine; it is still the gate's own foundation. | `QMLROOT=${QMLROOT:-$(mktemp -d)}` with a trap, or check `ln -sfn` and `bad` on failure. |

### Tier F - test-estate shape, injection, and papercuts

| # | Where | What it lets through | Fix |
|---|---|---|---|
| F1 | `scripts/dev-harness/player-scenario.sh:87-93`, `:163-170`, `:455`, `:460`, `:461` | `field()` prints the empty string on **any** exception (missing key, malformed JSON, dead IPC) and `ipc()` (`:84`) swallows stderr; `session_id()` prints the empty string when `state.json` is missing or unparseable. Three P14 assertions then assert the empty string as the expected value. Every failure mode of the tooling produces exactly the value these checks demand. **Severity corrected from high to medium:** `:453`'s `ck "P14 the channel that died unattended is marked" '[[ -n "$mark14" ]]'` requires a live IPC and a non-empty answer and sits immediately before `:455`, so the block as a whole is guarded; only `:460`/`:461` inside the loop are unguarded. | Make the helpers speak sentinels: `session_id` prints `NOFILE`/`NOSESSION`, `field` prints `NOFIELD`, and the assertions expect those rather than `""`. Add a positive control inside the loop. |
| F2 | `scripts/dev-harness/player-scenario.sh:259`, `:265`, `:470` | Three assertions are bare negated `pgrep` calls. A missing `pgrep`, an empty `QS_PID` collapsing to `-P 0`, or a pattern that stopped matching because the launcher's argv changed are all indistinguishable from "nothing is running". `:265` is guarded by `:263`; `:259` and `:470` are not. **The dangerous part is the correlation:** `:470`'s pattern `quickshell -p $SCRATCH/root` is the **same pattern** `run.sh:252`'s `pkill -f` uses. If the argv ever stops matching, reap stops reaping **and** P9 - the whole teardown guarantee - reports PASS. Single point of failure shared between the teardown and its own verifier. (It is also a prefix match, so it covers `root2` as well as `root`.) | Add a positive control: assert the pattern DOES match while the shell is up, then that it does not after. That makes the pattern load-bearing instead of assumed. |
| F3 | `tests/test_player.py:170-187` (`sleeper`), `tests/test_mpv.py:50` (`FakeMpv`, used at `tests/test_player.py:282`), `tests/test_player.py:83-114` (`STUB_MPV`) | CLAUDE.md rule 10: the double must never be more forgiving than the real thing. **Correction to the record:** the claim that "the doubles split mpv into two processes so the coupling cannot be expressed" is wrong. The STUB **does** own both identities in one process - it carries the token in argv and calls `server.bind(path)` - and `test_stop_after_a_start_leaves_nothing_behind` (`tests/test_player.py:779-787`) drives it through `player stop` and asserts the socket is gone. What is too forgiving is the stub's **teardown cost** (~0.35 ms at ~10 MB against the code's 4-8 ms observation point), not an identity split. Worse for the framing: the stub answers `quit` with `os._exit(0)` (`tests/test_player.py:114`), which does **not** close the listener first, so the stub's **quit** path has the kill-path asymmetry real mpv does not - only its small size saves it. `sleeper` carries the token and binds nothing; `FakeMpv` is an in-process thread that owns the socket, carries no token, and cannot die. | Add one double that owns both identities **and** can be made slow to tear down (a large touched allocation), and make the stub's `quit` close the listener before exiting so it models mpv's orderly shutdown. Keep deterministic coverage on injected guards. Miscite to correct: `sleeper` is `tests/test_player.py:170-187`, not 180-190. |
| F4 | `scripts/qa-player-scenarios.sh:101`, `scripts/qa-sources-scenarios.sh:87`, and their call sites (`qa-player` 126-131, 215-227, 262, 284, 303-306, 313, 331-335) | `sh_step() { ... bash -c "$2"; }` with `$SCRATCH` (from `OMARCHY_IPTV_HARNESS_DIR`) interpolated **unquoted** into the snippets. An environment-supplied scratch path containing a quote or `$(...)` is executed. Same family as C2, larger blast radius, and it is a `bash -c` with interpolated data in a repo whose constraint 2 forbids exactly that shape. | Pass data as argv to `bash -c 'snippet' _ "$SCRATCH"`, or convert the snippets to `step` with a real argv. |
| F5 | `scripts/qa-player-scenarios.sh:411` | `step "run" env OMARCHY_IPTV_PLUGIN_ROOT="$exp" "$0" run "$id" ${APPLY:+--apply}`. `APPLY` is always `0` or `1`, and `${var:+word}` expands when the variable is set and **non-empty** - `0` is non-empty. Verified: with `APPLY=0` the expansion is `--apply`. So the dry run, which is this script's entire contract ("DRY BY DEFAULT. Without --apply nothing runs", `:17`), prints a baseline command carrying `--apply`. A reader who copies the printed line executes it against their live session. | `local flag=(); ((APPLY)) && flag=(--apply); step "run" env ... "${flag[@]}"`. |
| F6 | `scripts/qa-player-scenarios.sh:431` | `cmd_baseline "${args[0]}" "${args[1]}"` under `set -u` (`:38`) aborts with `args[0]: unbound variable` on an empty array instead of reaching the script's own `die`/usage. The sibling at `:434` gets it right with `${args[0]:-all}`. Fails loudly, but with a bash internal message on the rule-11 evidence path most likely to be run by hand. | `"${args[0]:-}" "${args[1]:-}"` and validate inside `cmd_baseline` with `die`. |
| F7 | `scripts/qa-live.sh:94`, `:57-60` | `if omarchy menu keybindings --print 2>/dev/null \| grep -E '...' \| sed ...; then` - pipefail saves the no-match case, but a **missing or failing** `omarchy` also yields a non-zero pipeline, so the script reports "SUPER SHIFT + T is free" both when it is free and when the tool could not be run. `show()` at `:57-60` pipes into `sed` and discards the command's status entirely, so a failed preflight command is indistinguishable from one with no output. | Capture the command's status separately from the filter's. |
| F8 | `tests/Model.test.js:13-23` | `check()` compares `JSON.stringify(actual) === JSON.stringify(expected)`. `JSON.stringify(undefined)` returns the value `undefined`, so `check(name, Model.somethingRemoved(), undefined)` passes; `stringify` also drops `undefined` object properties and maps `NaN`/`Infinity` to `null`, so `check(name, {a: undefined}, {})` and `check(name, [undefined], [null])` pass (both verified in node). A comparison that cannot distinguish "absent" from "equal" - the same decoration shape the audit is hunting. No current check obviously relies on it; `checkCall` (`:28-36`) is sound and deliberately turns a missing export into a failure. | Reject `undefined` expectations explicitly and compare with a serializer that renders `undefined` as a distinct token. |

### Cross-cutting extra findings from the D-PLY-8 and D-PLY-11 investigations

| # | Where | Problem | Fix | Severity |
|---|---|---|---|---|
| X1 | `bin/omarchy-iptv:2920-2960` (`player_orphan_check`), settle at `:2956-2957` | Runs the full stop ladder and then `settle_socket` **without ever acquiring the player flock** - the file's only `acquire_lock` calls are `2814` and `2855`. A concurrent `player start` that binds a fresh socket between this settle's refused connect and its `unlink` would have the NEW socket deleted. Weakens `docs/ARCHITECTURE-PLAYER.md:525`'s "never unlink a socket a live player owns" and the "every verb is idempotent, serialised by one flock" claim at `bin/omarchy-iptv:1902-1904`. | Acquire the player lock around the ladder and the settle, as `player_stop` does. **Do not give this call site a settle deadline until it is locked.** | low, pre-existing, narrow window, only on the shell-died path after a 6 s grace |
| X2 | `bin/omarchy-iptv:2877-2920` (`player_probe`), settle at `:2892` | **Unlocked for exactly the same reason as X1**, and omitted from the original fix list. If the unlocked-unlink exposure is worth filing, it is worth filing for both. | Same as X1, or file both together. | low |
| X3 | `bin/omarchy-iptv:2766-2770` (`adopt_or_spawn`) | The same blind predicate on the start/restart path: the ladder reports the old player gone the instant its cmdline empties, `settle_socket` then fails for the D-PLY-8 reason, and a new mpv is spawned while the dying one still owns the bound listener. mpv unlinks and rebinds, so it self-heals, but during the overlap a `wait_for_socket` probe can connect to the old dead-but-bound listener and burn one `--ipc-timeout`. **Do NOT attribute QA observation M9.5 to this** - the finding's own central fact forbids it: a dying mpv has an empty cmdline from ~0.1 ms, so no cmdline-keyed check (`find_player` at `:2182-2190`, or any `pgrep -f`) can ever count it. Two pids on the token means two genuinely live mpvs, which is a different defect. | No code change required for correctness. If closed later, the spawn should wait for `socket_is_dead`, not merely for the finder to go blind, with the wait charged to the spawn timeout. | low |
| X4 | `docs/STATUS.md:143`, `docs/QA-PLAYER.md:160`, `docs/QA-RESULTS.md:2539-2541` | All three record D-PLY-8's cause as "most likely `find_player()` still sees the just-SIGKILLed process". Measurably false. This is an **active trap**: a future lane reading these rows would "fix" the finder with `os.kill(pid,0)`, which makes the ladder report `running:true` after a successful SIGKILL and blocks the settle indefinitely. | Correct all three to name the real guard - `socket_is_dead`, a still-bound listener on a process the finder can no longer see - when D-PLY-8 is dispositioned either way. | low, but it is a trap |
| X5 | `scripts/check.sh` coverage of `scripts/dev-harness/shell.qml` | CLAUDE.md rule 10 makes the harness fake load-bearing, and it is neither linted (E2) nor covered by any test. A QML error there leaves `check.sh` green while every harness scenario fails to start; the scenarios catch it only at `player-scenario.sh:237` / `sources-scenario.sh:113`, and only if someone runs them. | E2 closes the lint half. A dedicated pass over `shell.qml` against the real host's contract is probably worth more than several Tier F items and should be scoped separately. | medium |

---

## 6. Work plan and FILE OWNERSHIP

Three waves. Lanes run in separate git worktrees. **A diff touching an unowned file is rejected.** `docs/STATUS.md` and `docs/QA-RESULTS.md` are owned by **nobody**: each lane writes its row as a fragment in its own branch notes and the integrator applies them at merge, because every lane wants to edit the same two tables.

### Wave 1 - two lanes, parallel, neither holds the display

#### Lane A - helper, parity and the D-PLY-11 investigation

Items: **D-PLY-8** (settle re-check), **D-PLY-10** (shader containment), **D-PLY-11 step 1** (T-A, T-B, T-C characterisation only), **X1/X2** (lock the two unlocked settle call sites), **F3** (the stub's teardown cost and its `quit`), **F8** (`tests/Model.test.js` comparison).

- **Owns (may write):** `bin/omarchy-iptv`, `Model.js`, `tests/test_player.py`, `tests/test_mpv.py`, `tests/test_state.py`, `tests/Model.test.js`, `tests/fixtures/player-argv.json`, `docs/ARCHITECTURE-PLAYER.md`.
- **May read:** everything.
- **Must not open:** `Service.qml`, `Guide.qml`, `BarWidget.qml`, `tests/Model.spec.qml`, anything under `scripts/`, `README.md`, `CHANGELOG.md`, `manifest.json`.

**`Model.js` is the chokepoint of this whole round.** D-PLY-10's Python/JavaScript/fixture triple must move in one commit or the parity test goes red, so Lane A must own it in wave 1. That is why every `Model.js` addition D-PLY-11 wants (`zapArgs`, `playFailureVerdict`, `replyTarget`, `reconcileVerdict`) is deferred to wave 3.

**D-PLY-8 and D-PLY-10 must share this lane.** They touch different functions but the same file (`bin/omarchy-iptv`), and per-file ownership admits no split. They can be separate commits; they cannot be separate worktrees.

#### Lane H - harness and tooling

Items: the entire section 5 audit, **D-PLY-9 (a)** and **(b)**.

- **Owns (may write):** `scripts/**` (`check.sh`, `qa-live.sh`, `qa-player-scenarios.sh`, `qa-sources-scenarios.sh`, `gen-playlist.py`, `dev-harness/**`), `docs/QA-PLAYER.md`, `docs/QA-SOURCES.md`.
- **May read:** everything.
- **Must not open:** `bin/omarchy-iptv`, `Model.js`, `Service.qml`, `Guide.qml`, `BarWidget.qml`, `tests/**`, `docs/ARCHITECTURE-PLAYER.md`.
- **Expect a red gate and report it rather than suppressing it.** E3 widens the ASCII scan over files that currently carry non-ASCII bytes; E2 lints `shell.qml` for the first time. Both are supposed to find things. A lane that narrows the new scan to keep the gate green has defeated the item.
- Lane H must **not** write the D-PLY-11 P15/P16 scenarios in this wave; they depend on an investigation verdict that does not exist yet.

**Lane A and Lane H cannot be merged into one lane** - `bin/omarchy-iptv` and `scripts/dev-harness/run.sh` are both heavily edited, the two skill sets are different, and the harness work must stay free to go red without blocking a helper fix.

### Wave 2 - one lane, exclusive, holds the display

#### Lane D - live confirmation and the D-PLY-11 discriminator

Runs only after Lane A and Lane H merge. **Only this lane may run `wtype`, `grim`, `hyprctl dispatch`, the dev harness, quickshell, or mpv with a window.** Check `pgrep -x hyprlock` before any keystroke. Snapshot `shell.json`, the state directory and the cache first; restore the exact end state.

- **Owns (may write):** `docs/QA-RESULTS.md` (evidence sections only), and nothing else. It is a measuring lane.
- **May read:** everything.
- **Must not write:** any source file. A fix it discovers is a finding handed to wave 3, not a diff.

Deliverables, in priority order:
1. **The D-PLY-11 discriminator**: TC-PLAY-10 re-run with the extended capture (warm-vs-cold, stash over `socat`, `playlist/current/id`, `ipc status`'s `player.seq` and `player.entryId`, the shell journal). Plus PLY-LIFE-03, which was never re-run at `b16b479`. This is what unblocks wave 3.
2. **D-PLY-8**: PLY-STOP-03 re-run (5 wedged, 5 responsive), plus one tight `connect()` sampling loop right after the SIGKILL on the real windowed player.
3. **D-PLY-10**: `ls ~/.cache/mpv` before and after a containment cycle; the redirected directory populated at 0600 inside 0700.
4. **D-PLY-9**: `player-scenario.sh` at HEAD (expect 76/0) and at `--baseline 396a69a` (expect 61/20, with the restored check **passing** on both trees). Record the actual numbers whatever they are.
5. PLY-PERF-02 re-measured.

### Wave 3 - one lane, after wave 2's evidence lands

#### Lane S - shell state reporting

Items: **D-PLY-11 step 2** (the reconciler's detection half), **step 3** (the cause-independent defects), and - **only if wave 2's evidence establishes a family** - the cause-directed fix for that family.

- **Owns (may write):** `Service.qml`, `Model.js`, `tests/Model.test.js`, `tests/Model.spec.qml`, `bin/omarchy-iptv` (the `cmd_status` stash emission and the stash seq only).
- **May read:** everything.
- **Must not open:** `scripts/**`, `Guide.qml`, `BarWidget.qml`.
- Lane S inherits `Model.js` and `bin/omarchy-iptv` from Lane A, so it **cannot start before Lane A merges**.

If wave 2 comes back inconclusive - no divergence reproduced, warm-vs-cold unrecoverable - Lane S still ships step 2 and step 3 (they stand on their own) and D-PLY-11's cause row stays open with the evidence attached. **That is an acceptable outcome and it is better than implementing a fix for a cause nobody established.**

### Sharing rules, stated plainly

- **Can share a lane:** D-PLY-8 + D-PLY-10 + D-PLY-11's helper-layer investigation (all three write `bin/omarchy-iptv` and `tests/test_player.py`). Every harness audit item (all write `scripts/**`).
- **Must not share a lane:** the harness work and the helper work (different files, and the harness lane is expected to go red). The display work and everything else (only one lane may hold the display, and it may not write source). Lane S and Lane A (both want `Model.js`; serialise them across waves).
- **Only one lane may hold the display**, and in this plan that is Lane D, in wave 2, exclusively. No lane in wave 1 or wave 3 may start quickshell, the dev harness, or a windowed mpv. A headless mpv that opens no window and is killed by pid within seconds is the only exception, and only for confirming a behavioural fact.

---

## 7. What a live shell must confirm, and what can be proven without one

### Provable with no display, in the unit gate

- D-PLY-8's guard semantics in full: the bounded re-check unlinks when and only when both guards pass together; a successful connect blocks it; a **timed-out** connect blocks it; a `find_player` hit blocks it; `S_ISSOCK` is checked at unlink time; the no-deadline call behaves exactly as today; the deadline never exceeds the kill rung's window.
- D-PLY-10's argv and directory plumbing: both options present, pointing inside the plugin's tree, user tokens still landing after them, both mirrors agreeing through `tests/fixtures/player-argv.json`, the directory created at 0700.
- D-PLY-9's `log_count`: the pure-bash before/after pair, in under a second, with no harness and no window. And that the count floor fires when an assertion is deliberately broken.
- D-PLY-11's helper-layer orderings: T-A (an adopting `player start` re-applies its own channel over a newer zap) and T-B (a cold-start zap can win the socket ahead of the start's handshake), both gated rather than timed, both 1/1.
- D-PLY-11's pure-logic additions: `reconcileVerdict`, `replyTarget`, `zapArgs`, `playFailureVerdict` - including the `no_output`, `unknown_channel`, `no_cache` and `busy` vectors.
- That `status` carries `stash` (red today).
- Every Tier D, E and F harness item, and the shell-only parts of Tier A/B/C - `cmdline_of ""`, the sources privacy expression against an empty log, `${APPLY:+--apply}`, the `set -u` abort, `qa-live.sh:186` against an empty file, the `JSON.stringify` comparison. All of these were reproduced read-only during the investigation.
- That `check.sh` is green, that `python3 -m unittest discover -s tests` is 260/260 and that `node tests/Model.test.js` is 954/0 - the baseline this round must not break.

### Requires the live shell, and belongs to Lane D alone

1. **D-PLY-8:** that a real windowed mpv's teardown window actually exceeds the code's ~4-8 ms observation point. Everything else about D-PLY-8 is measured; this one step is inference. Sample `connect()` in a tight loop right after the SIGKILL.
2. **D-PLY-8:** PLY-STOP-03 - `mpv.sock` gone at t+1 s after a wedged stop with no further helper call, 5 wedged and 5 responsive.
3. **D-PLY-8:** PLY-PERF-02 re-measured against 4500 ms (was 4236-4263 ms), and confirmation that `Service.qml:64`'s 5000 ms `stopSettleTimer` backstop does not fire.
4. **D-PLY-10:** that `--gpu-shader-cache-dir` actually diverts the write. No headless run can show this - `--vo=null` compiles no shaders. `ls ~/.cache/mpv` before and after.
5. **D-PLY-10:** that the redirected files land at 0600 inside a 0700 directory, and that `omarchy plugin remove` plus the documented cleanup leaves nothing behind.
6. **D-PLY-9:** the real summary counts at HEAD and at `396a69a`, and whether the restored check behaves as traced.
7. **D-PLY-11:** **warm or cold.** The single missing fact. Plus the stash, `playlist/current/id`, `ipc status` and the journal at the moment of divergence.
8. **D-PLY-11:** PLY-LIFE-03, the cold-hammer case, which was not re-run in this pass and is therefore untested at `b16b479`, not proven clean.
9. **The harness fixes themselves:** `player-scenario.sh` and `sources-scenario.sh` open a real window for ~60 s and wedge a player with SIGSTOP for ~21 s. No wave-1 lane can validate its own harness edit end to end; wave 1 validates the pure-bash units and hands the scenario run to Lane D.
10. Whether widening the ASCII gate (E3) and linting `shell.qml` (E2) turn `check.sh` red on the live tree, and what they find.

---

## 8. Open questions for the product owner

**Q1. Does PLY-PERF-02's 4500 ms budget measure "the player process is gone" or "the stop command returned"?**
*Recommendation:* rule it as "the player is gone", which is what the user experiences - `player stop` is `execDetached`, so the UI clears on the keystroke regardless. **But the recommended fix makes this moot in practice:** carrying the kill rung's own absolute deadline into the settle (rather than adding a fresh flat 500 ms after the rung returns) cannot push the command past 4500 ms under either reading. Answer it for the wording in `docs/ARCHITECTURE-PLAYER.md` and the README, not as a blocker.

**Q2. Where should the contained shader cache live - ephemeral or durable - and should the option be reserved?**
*Recommendation:* **ephemeral**, in the runtime directory (`$XDG_RUNTIME_DIR/omarchy-iptv/shader-cache`), because a shader cache is content-free and regenerable, the runtime directory is already 0700 and already documented, and it adds **no new durable path to `Files it writes` and nothing to clean up at uninstall**. It also needs zero new plumbing - `player_dirs` already computes `runtime`. The alternative, `~/.cache/omarchy-iptv/player/`, keeps the shader-compile saving across logins but requires threading the cache directory into `player_dirs`, its `Model.js` mirror, `buildMpvArgv` and the fixture, plus a new line in `Files it writes` and in CLAUDE.md rule 6. On reservation: recommend **not** adding `--gpu-shader-cache-dir` / `--icc-cache-dir` to `MPV_RESERVED`, because the reservation reasoning on record is a privacy one (`--watch-later-dir` reserved, `--screenshot-dir` deliberately not) and a content-free cache falls on the unreserved side. Rule explicitly if you want containment to be a guarantee rather than a default.

**Q3. How should the "exactly one relaunch, never a second at the healthy player" property be witnessed?**
*Recommendation:* add a log line at `Service.qml:2486`, in the `relaunchTimer` `playerUp` branch. It is one line, it makes the *existing* harness assertion at `player-scenario.sh:374` discriminating once `log_count` is fixed, and it retroactively validates the by-hand journal count QA already relied on at `docs/QA-RESULTS.md:2407`. The alternatives (assert on the `player.lock` seq, or count `player restart` processes) need no `Service.qml` change but leave the recorded QA evidence resting on a string that cannot distinguish the trees. Whichever you pick, **the D-PLY-1 second-relaunch property currently has no witness anywhere** and the docs that claim it does need correcting.

**Q4. Should `play` gain `--seq` and take the player lock - and if so, in what order?**
*Recommendation:* **not this round, and never before the `busy` routing exists.** `player_start` holds the lock across `adopt_or_spawn` (`bin/omarchy-iptv:2814-2827`), which contains `wait_for_socket` bounded by `DEFAULT_SPAWN_TIMEOUT = 5.0` (`bin/omarchy-iptv:1920`). Every zap issued during a cold start - exactly the burst case - would then block up to 5 s or return `busy`, and `busy` is **not** handled in the play branch (`Service.qml:973-1008`): it falls to the `else` at `:996-1001`, which is the rollback. The fix would manufacture the failure it is meant to remove, on the exact path the failing burst uses. If you want the ordering gap closed, the order is: (1) route `busy` to the existing backoff at `Service.qml:1164-1172`; (2) then give `play` the seq and the lock. Note also that `docs/ARCHITECTURE-PLAYER.md:230-232` freezes `play`'s spelling, so this needs an amendment to section 4.3, not a workaround.

**Q5. When the shell and the player disagree about the channel, which side is authoritative - and what is the repair?**
*Recommendation:* **the shell**, and the repair is to **re-apply the user's intent (re-zap)**, not to relabel `nowPlaying` from the player's stash. In every ordering in this family the shell holds the user's last intent and the player is the stale side, so relabelling would make the UI name the channel the user did not ask for - it would turn a visible reporting bug into a silent wrong-channel. This round ships **detection only** (`status.stash` emitted, a real seq in the stash, `Model.reconcileVerdict` comparing them); the repair action lands once you rule. Ruling "the player is authoritative" is also defensible but requires the stash seq to land first so the two sides can be compared rather than merely differed.

**Q6. Is concurrent `play` IPC in contract at all?**
`docs/QA-PLAYER.md:1712-1716` asks for a severity boundary on TC-PLAY-10 - "only the serial case is a user-reachable contract". That is true of the **guide**, which is single-threaded QML, but `Service.qml:2725-2745`'s `IpcHandler` exposes `play`/`next`/`previous` to any script with no rate limit, so a user with a keybinding that fires twice can reach it.
*Recommendation:* rule concurrent IPC **in contract but best-effort**: the invariant is "the shell's label and the player's channel agree within one health tick", not "the last of N simultaneous intents wins". That keeps D-PLY-11 at P3, makes the reconciler (Q5) the contract rather than the ordering discipline (Q4), and does not require freezing a semantics for simultaneous IPC that nothing in the product needs.

**Q7. Should the six `qa-player-scenarios.sh` scenarios be converted into asserting scenarios now, or is the exit-code fix enough for this round?**
*Recommendation:* **exit-code fix now, conversion next round.** B1's one-line change (exit non-zero when `fail > 0`) restores the ability of the gate and the runner to fail at all, which is the part that matters. Converting PLY-H11..H16's EXPECT lines into `is`/`ck` using the already-written `svc`/`wins`/`mpvq` helpers is real work on six live scenarios and would put Lane H on the display, which this round's lane structure forbids.

**Q8. Should the unlocked settle call sites (`player_probe` at `:2892`, `player_orphan_check` at `:2957`) be locked as part of D-PLY-8, or filed separately?**
*Recommendation:* **lock them as part of D-PLY-8.** They are one `acquire_lock`/`release_lock` pair each, they sit in the same file the lane already owns, and leaving them unlocked while the sibling call site gains a waiting settle invites a future lane to give one of *them* a wait too - which would lengthen a real TOCTOU exposure. The exposure is pre-existing and narrow either way, so this is a cheap tidy, not a fix for a live defect.

## 9. Product owner rulings (2026-09-14)

Plan accepted. Rulings CL1 to CL8 answer section 8 in order and are binding.

| # | Ruling |
|---|---|
| CL1 | The stop budget measures "the player process is gone", not "the command returned". That is what a user experiences, and the stop command is fired and forgotten so its return tells them nothing. Correct the wording in the design document and the README to say so. |
| CL2 | Contain the shader cache in the runtime directory, ephemeral. It is content-free and regenerable, the directory is already private and already documented, and it adds no durable path and nothing to clean up at uninstall. Do not reserve the option: the reservation list is a privacy instrument, and a content-free cache does not belong on it. Containment here is a sensible default, not a guarantee. |
| CL3 | Add the log line so the property has a witness. The point is not the line, it is that the assertion about a second relaunch at the healthy player, which is half of the P1 this project just shipped, has no witness anywhere and the documents that claim otherwise are wrong. Fix the witness and correct those documents in the same change. |
| CL4 | Do not give the play verb a sequence number and the lock this round, and not before refusals are routed. The analysis is convincing: every channel change during a cold start would block or be refused, and a refusal currently falls through to the rollback branch, so the fix would manufacture the very failure it is meant to remove, on the exact path the failing burst used. The order is refusal routing first, then the sequence and the lock, and it needs an amendment to the design rather than a workaround. |
| CL5 | The shell is authoritative and the repair is to re-apply the user's intent, not to relabel from the player. Relabelling would turn a visible reporting bug into a silent wrong channel, which is far worse: the user would be watching something they did not choose while the interface agreed with the mistake. Ship detection only this round. |
| CL6 | Concurrent requests are in contract but best-effort. The invariant is that the interface's label and the player's channel agree within one health tick, not that the last of several simultaneous intents wins. The guide cannot produce concurrency, but the command surface is open to any script and a doubled keybinding reaches it. |
| CL7 | Exit-code fix now, conversion next round. Restoring a suite's ability to fail at all is the part that matters. |
| CL8 | Lock the two unlocked settle call sites as part of this work. Cheap, same file, and leaving them inconsistent invites someone to widen the exposure later. |

Two things I want carried out of this round beyond the code.

The hypothesis recorded for the socket residue was wrong, and it is written as fact
in three documents. A process killed outright clears its command line before
anything else, so the routine everyone suspected goes blind earlier, not later.
Correct all three. A wrong cause recorded confidently is worse than an open
question, because the next person builds on it.

Sixteen further places in this project's own test tooling can pass without
testing anything. That is not a tidy-up, it is the same failure that shipped a
broken release here already: a suite reported green while the assertion that
mattered had died. Rank them, fix them, and treat any check that has never been
seen failing as unproven until it has.

## 10. Rulings after wave two (product owner, 2026-09-14)

Wave two settled the question the round existed to answer, and corrected two
things I had ruled on.

| # | Ruling |
|---|---|
| CL9 | The divergence has an established cause and wave three fixes it. Ten user-visible divergences in twenty cold concurrent bursts, none in ten warm bursts, none in six cold serial runs. The mechanism was observed rather than inferred: a channel change reaches the socket first and the start re-applies its own channel afterwards. The adopting-start family never fired, and the earlier one-in-eight rate was an artefact of not guaranteeing a cold start. This is now a fifty percent reproduction under known conditions, which is enough to tell a fix from luck. |
| CL10 | My ruling CL3 was half right and I am correcting it. I asked for a log line as the witness. It exists, and it cannot do the job, because it exists only in the fixed tree: an older tree has nothing to match, so the comparison is not a pass against a fail, it is a pass against nothing. A witness that only the fixed code emits can never discriminate between trees. Assert instead on something BOTH trees produce and produce differently: wave two measured the sequence delta, one in the fixed tree where a broken one must read two. Keep the log line for humans reading a journal, and move the assertion to the sequence. |
| CL11 | Severity stays P3 on reachability, not on rate. Fifty percent is alarming, but every reproduction needed genuinely simultaneous requests, and the guide is single threaded and cannot produce them. The exposed command surface can, so a script or a doubled keybinding reaches it, which is why it is worth fixing rather than documenting. Do not re-rate it upward on the rate alone. |
| CL12 | Teardown proportionality is not a fact and must not be recorded as one. Two lanes measured it and disagreed, and the windowed measurement misses the headless scaling series by roughly tenfold. What IS established: a killed player clears its command line in well under a millisecond, and its socket stays bound for roughly ten to twenty-five milliseconds on a real windowed player. CORRECTED: I first recorded a floor of fifteen, and a later pass measured 9.6, so the true range over the ten windowed kills on record (D2 and L5) is 9.6 to 36.9 ms; only the floor of 15 was optimistic, the 37 ceiling was measured (corrected 2026-09-25, D-PLY-8). This makes the single-shot guard's margin thinner than I claimed, clearing the floor by only about 1.3 times, which strengthens rather than weakens the case for the re-check. The re-check itself keeps an eighteen-fold margin against the ceiling and costs about twelve percent of its window. The fix does not depend on the disputed part, which is precisely why it works. |
| CL13 | The interface-clear budget has no instrument fine enough to assert on. Record the bound and stop claiming a verdict. A budget that cannot be measured is not a budget, and pretending otherwise is the same failure as a check that cannot fail. |

The round's own lesson, for the record. This defect was filed at one in eight,
with a cause that turned out to be wrong, and a plan that would have had us fix
it anyway. Refuting the cause cost one agent. Making it reproduce on demand
cost one lane. It is now a fifty percent, observed, single-mechanism defect
with a known trigger. Every step of that was cheaper than shipping a fix for
the wrong cause and believing the problem was solved.

## 11. Rulings after the follow-up lane (product owner, 2026-09-14)

| # | Ruling |
|---|---|
| CL14 | The scenario runner pinned the helper to the working tree, so every helper step of a baseline comparison ran TODAY's helper against yesterday's expectations. That is fixed. It also means any earlier claim of the form "this suite fails against the pre-fix code" that went through that path was partly measuring the current tree, and is downgraded from proof to indication until re-run. Claims proven by other means, the node and python suites run against an older file, and the predicate library that lifts an assertion verbatim, are unaffected. Do not quietly keep the old numbers; re-run what matters and say which is which. |
| CL15 | Add a baseline verb to the sources scenario runner. No scenario in that suite has ever been run against another tree, which means none of them has ever been shown capable of failing. That is the same finding this whole round started from, in the one suite nobody looked at. It is not urgent, because those scenarios were written alongside working code rather than to catch a known defect, but it is the difference between a suite we trust and a suite we hope about. Next round. |

The round's arithmetic, for the record. It began with four small defects. It
produced: one refuted root cause, one measured mechanism replacing a guessed
one, one rate corrected from one-in-eight to ten-in-twenty, seventeen checks in
this project's own tooling that could report success without testing anything,
a baseline mechanism that was comparing a tree against itself, one ruling of
mine that was wrong in a way that could never have shown up as a failure, and
a disputed measurement now recorded as disputed rather than as fact. None of
that was visible from the defect titles. All of it was found by running things
and by having a second agent try to break the first one's answer.
