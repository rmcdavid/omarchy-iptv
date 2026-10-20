# key-mutations: the one-decision mutations key-scenario.sh was seen red against

`scripts/dev-harness/key-scenario.sh` grades D-SINK-19 on the real
`Service.qml` under a nested headless cage, and rule 11 says every check in
it has to have been SEEN RED on code that carries the failure it names. For
the round-4 checks (D3 by reason, W1-W6) no earlier tree carries exactly the
one failure each check names, so the red runs were made by MUTATION: one
decision broken on purpose in a copy of the tree, the scenario run over the
copy. Round 4 kept those two mutations as throwaway git branches
(`mut-d3-save-parked`, `mut-r14-no-return`, single commits parented on
lane-key-t1) and cited them through `--baseline`; the lead ruled in round 5
that a mutation is a PATCH FILE the reader applies to a copy, not a branch
that can be merged by accident, and deleted the branches. These are those
two diffs, byte for byte, with one move: when the chain landed on the
D-REL-5 split (2026-10-12) the model stopped being one `Model.js`, and
`d3-save-parked.patch` was re-made against `model/state.mjs`, the part that
declares `reloadDisposition` -- the same removed line and the same added
line, only the file and the hunk's position changed.

| patch | what it breaks | which checks go red |
|---|---|---|
| `d3-save-parked.patch` | `Model.reloadDisposition`'s (in `model/state.mjs`) `save-parked` clause deleted: a reload over a PARKED save is applied as `file-newer` (the D-SRC-15 drop, re-opened) | D2, D3, W2, W3, W4, W6 -- the per-reason counter reads `{"file-newer": 1, "first-load": 1, "own-write": 1}` and `save-parked` is absent. Since R26 (2026-10-16, lane-clean-a1, --tree: 76 passed, 53 failed) the clause is load-bearing for EVERY in-app save: each save waits behind a read whose load is the base, and only `save-parked` keeps that load from being applied over the change, so the in-app edits of D, N, M, G, C, E, R, O, W, F, U, A, Y, Q, V and B7..B31 are lost. D3 and W3 still read `save-parked:NOFIELD` (the read's own loads count as `pre-save-*`) |
| `r14-no-return.patch` | `Service.applyUserState`'s R14 `return` deleted: the reload is COUNTED as ignored and then applied anyway | D2, W2, W3, W4, W6 -- and D3 GREEN, with `{"save-parked": 1, ...}` beside the loss at the sink: a counter observes the decision, D2/W2 observe the sink, and the `return` itself is pinned structurally in `tests/Model.test.js` (R14) |
| `r23a-no-rearm.patch` | `Service.liftStateBlock`'s `root.stateBlockTold = false` deleted (round 13, R23a): the lift no longer re-arms the no-write notice, so a second episode in one session is never told -- the round-12 data-loss lens's X13, which no check saw (0 of 2354 node failures, nothing red live) | B9 (`told:1/1`), and in `tests/Model.test.js` the four R23a pins (4 of 2358, both own-write echo modes) |
| `r24g-no-kill.patch` | the start-up watchdog's KILL in `Service.qml` deleted (round 14, R24g): a TERM-ignoring start-up process (the slow tree's init with `OMARCHY_IPTV_SLOW_IGNORE_TERM=1`) is never ended | B17 (`helper:no(<pid>)`, `blocked:` empty, `told:0`), and in `tests/Model.test.js` the four R24g pins (init and mkdir, both hosts) |
| `r25a-keep-landed.patch` | `Service.qml`'s `stateFile.onSaved` no longer clears `recentSaves` when a save lands (round 15, R25a): the old eight-text own-write record, so a backup of an earlier own save put back is ignored as an echo and written over | the four R25a node pins per host and echo mode (16 of 2491), and key-scenario's B19 restore |
| `r25a-clear-every-saved.patch` | `recentSaves` cleared on EVERY `saved`, mid-burst included (round 15, R25a's other half) | the coalesced-burst pin in own echo `load` (the mid-burst echo reads `foreign-save-in-flight`), R13's coalesced burst and R26a's skipped read (6 of 2565 own echo load, 4 none, since F-HARNESS-31; before it R24a IN FLIGHT, R25d a7, R25b's saved-search pin and R26b's census went red too, 14 / 12, all four of them through the foreign load the double then delivered during our write) |
| `r25b-silent-drop.patch` | the merge's cap drop is logged but the user is not told (round 15, R25b) | the four R25b node pins at 49 sources over a FAILED save (4 of 2565 in each own-echo mode; the four in-flight saved-search pins went red too until F-HARNESS-31 showed their cap merge needed a load the measured view never delivers) |
| `r25d-a5-base-not-moved.patch` | `Service.mergeForeignText` does not move the base to theirs (the round-14 lens's a5, F-HARNESS-26): a second foreign write in one held window is compared with a stale base | the four R25d a5 node pins |
| `r25d-a7-no-inflight-half.patch` | the in-flight half of `mergeForeignText`'s re-save decision deleted (the lens's a7): our older in-flight save lands over a merge equal to theirs | **nothing, since F-HARNESS-31 (2026-10-16): 2565 checks, 0 failures in each own-echo mode** (8 before, the four R25d a7 pins and the in-flight R25b saved-search pin). Every pin that reached this half did it with a FOREIGN load delivered while our write was in flight, which the double used to deliver and the measured FileView does not (30 of 30); re-levelled to the same-instant loss, they no longer reach the half at all. Whether any load the real view delivers can reach it -- one asked before our `setText` and delivered after it, say -- is unmeasured; the clause is kept, and the lead holds that question |
| `r25d-no-reload-on-change.patch` | `stateFile`'s `onFileChanged: reload()` deleted (round 15, R25d): the view still watches, the service never reloads | key-scenario's B21 (the existing-folder session damaged after an own save: the garbage unnoticed) |
| `r26a-no-read.patch` | `Service.saveState`'s read before a write deleted (R26a, 2026-10-16): a save the gate allows is written at once, a refusal stands as the gate gave it -- the 1c88877 behaviour, with R26b's deferral kept | key-scenario's B23..B28 and B31 (--tree: 122 passed, 7 failed; B28 `created:644 holds:[state.json] blocked: told:0`); in `tests/Model.test.js` the R26a pins that need the read and R26d's FRESH (36 of 2561 in each own-echo mode) |
| `r26b-no-defer.patch` | `Service.saveState`'s deferral deleted (R26b): a save asked for inside one of `stateFile`'s handlers is written there and then, which raises no `saved` (D-SRC-46) | key-scenario's B30 INLOAD (--tree: 128 passed, 1 failed, B30 `inFlight:1 saveFailed:true` with the merge on disk); in `tests/Model.test.js` R26b's D-SRC-46, handler-write census and structural pin, R13's burst and the eight R22a unmigrated starts whose migration save meets the chmod reload (19 of 2565 own echo load, 17 none, since F-HARNESS-31; 23 / 21 before it, with R24a IN FLIGHT, whose merge inside a load came from a foreign load the measured view does not deliver during our write) |
| `r26a-no-verb-recheck.patch` | `Service.recheckStateBlock`'s reload deleted (R26a, D-SRC-35): a source verb meeting a liftable no-write mode is refused and nothing reads the file again | key-scenario's B29 (--tree: 128 passed, 1 failed, B29 `lifted:[absent] second:false`); in `tests/Model.test.js` the four R26a/R26e source-verb pins (4 of 2561) |
| `r26d-periodic-reload.patch` | a 2 s `Timer` that reloads `stateFile` whatever happens -- the periodic reload R26d refused (lane W's option B) | key-scenario's B31, its idle half (--tree: 126 passed, 3 failed, B31 `idle-loads:+15` in 30 s; B28 and B29 red too, because the timer sees the empty folder and the returned target before the first call does: `edit:false`, `first:ok`): no tree before it reloads while idle, so that half is green on every tree without this patch; no node pin (the harness runs no Timer) |
| `r26a-watchdog-20ms.patch` | `stateVerifyWatchdog`'s `interval: 2000` made `interval: 20` (F4, 2026-10-16, lane-clean-f1): the read before a save is given up after 20 ms, so under load or on a slow filesystem a save goes without its read -- the pre-R26 write, the 0644 file included. A review mutant of the same line passed node (2561 / 0) and a live key-scenario (129 / 0), because nothing ran the Timer | in `tests/Model.test.js` the four "the read's bound is 2 s" pins (4 of 2565 in each own-echo mode: `late:[false,1,1]`, the save gone without its read at 1,999 ms). No live check: key-scenario's reads answer in milliseconds, so a 20 ms bound never fires there (the review's run: 0 `was not read back` lines) |
| `r26a-watchdog-no-interval.patch` | the same Timer's `interval` line deleted: Qt's default, 1000 ms | the same four pins (`interval:1000`, 4 of 2565 in each own-echo mode) |
| `r27a-no-wait.patch` | `Model.stateSavePlan`'s R27a wait line (in `model/state.mjs`) put back to R26's: a save asked while our write is in flight is deferred and then written from the next turn WITHOUT its read (D-SINK-22 window a, 2026-10-20) | in `tests/Model.test.js` 19 of 2602 in each own-echo mode: the R27a window-a pins, the write-wait bound, the plan table, and R13's and R25a's bursts (which form again). Not run live through --tree: on behaviour no live check could see it, because on this machine the first write had always landed by the deferred turn (6f1d176 skipped no read in B33 either) |
| `r27a-wait-never-released.patch` | `Service.endStateWriteWait` no longer asks for the held save: a save that waited for our write is never written (until some later save picks it up) | key-scenario's B33 (--tree: 133 passed, 1 failed of the 134 lettered checks then, `disk:...C=w-one`); in `tests/Model.test.js` 23 of 2634 in each own-echo mode (window a, D-SINK-22, the bound, D-SRC-47's mechanism, R13's and R25a's bursts, R26b's structural pin). The burst measurement that was B34 stayed green here -- a later edit of the burst picks the held one up -- and was dropped as a check for it |
| `r23e-editable-field.patch` | the form field's `readOnly: true` in `Guide.qml` made `false` (round 13): the D-CLIP-1 switch off, one editable TextInput per form field | B13 (`editable:` above 0 on the first-run form): the control that shows the harness's editable-input census (`ipc editable`) can see a field, so B11's `editable:0` on the no-write surface is an observation and not a census that cannot count |

Round 14 (R24a) re-made `d3-save-parked.patch` and `r14-no-return.patch`
for the new shape of the same two decisions: `reloadDisposition` now
computes WHY a change is held before asking whether the text is the base,
so the save-parked clause is the first arm of that expression, and the R14
`return` sits below the merge branch. The removed decision and the added
comment line are the same; the hunks moved. Round 15 (R25a) re-made
`d3-save-parked.patch` once more: R25a's `unchanged` arm now sits in the
nothing-held branch below the deleted clause, so the hunk's context moved;
the decision broken is the same, and with memory moved by the adoption the
reload still lands on `file-newer`.

R26 (2026-10-16) re-made `r25a-keep-landed.patch` and
`r25a-clear-every-saved.patch`: R26b wraps `stateFile`'s `onSaved` body in
a handler-depth count and a `try`, which re-indented the hunks. The
decisions broken are the same two lines, and the node reds are the same
pins (the coalesced burst, R24a IN FLIGHT and R25d a7 for the second),
re-levelled to put the save in flight first.

All seventeen apply to the tree they are checked in with (`scripts/qa-lib-test.sh`
runs `git apply --check` on each, so a refactor that moves a hunk is a red
gate, not a silently stale patch).

## Running one

Never apply a patch to the working tree. Export the tree, apply the patch in
the export, point the scenario at the export with `--tree` (the lever that
takes a directory where `--baseline` takes a ref; the export is yours to
remove afterwards):

```bash
cp=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-key-mut.XXXXXX")
git archive HEAD | tar -x -C "$cp"
( cd "$cp" && git apply "$OLDPWD/scripts/dev-harness/spikes/key-mutations/d3-save-parked.patch" )
scripts/dev-harness/key-scenario.sh live --tree "$cp"      # D2, D3, W2, W3, W4, W6 red
rm -rf "$cp"
```

`git apply` works outside a repository as a patch tool; the `index` lines in
the files are zeroed on purpose so they name no blob. A patch that no longer
applies is reported by `git apply` and by the qa-lib-test pin; rewrite it
against the decision it names, never against a line number.

Measured 2026-10-12 on lane-key-u2 (round 5, 63 lettered checks): the
counts are in key-scenario.sh's header under "RULE 11, THE RED RUN" and in
the transcript each run prints as its first line.

R27a (2026-10-20, lane-sweep-a1) re-made `r25a-keep-landed.patch`,
`r26a-no-read.patch`, `r26b-no-defer.patch` and `r26d-periodic-reload.patch`
against the tree that carries R27a's lines (the wait branch beside the
refusal, the end of the write wait in `onSaved`, the wait's own Timer after
the read's): the same removed and added lines, only their context moved, so
`git apply --check` passes again (scripts/qa-lib-test.sh). They were not
re-run live through --tree after the re-make.
