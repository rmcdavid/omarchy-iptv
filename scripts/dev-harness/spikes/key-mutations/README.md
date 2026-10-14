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
| `d3-save-parked.patch` | `Model.reloadDisposition`'s (in `model/state.mjs`) `save-parked` clause deleted: a reload over a PARKED save is applied as `file-newer` (the D-SRC-15 drop, re-opened) | D2, D3, W2, W3, W4, W6 -- the per-reason counter reads `{"file-newer": 1, "first-load": 1, "own-write": 1}` and `save-parked` is absent |
| `r14-no-return.patch` | `Service.applyUserState`'s R14 `return` deleted: the reload is COUNTED as ignored and then applied anyway | D2, W2, W3, W4, W6 -- and D3 GREEN, with `{"save-parked": 1, ...}` beside the loss at the sink: a counter observes the decision, D2/W2 observe the sink, and the `return` itself is pinned structurally in `tests/Model.test.js` (R14) |
| `r23a-no-rearm.patch` | `Service.liftStateBlock`'s `root.stateBlockTold = false` deleted (round 13, R23a): the lift no longer re-arms the no-write notice, so a second episode in one session is never told -- the round-12 data-loss lens's X13, which no check saw (0 of 2354 node failures, nothing red live) | B9 (`told:1/1`), and in `tests/Model.test.js` the four R23a pins (4 of 2358, both own-write echo modes) |
| `r24g-no-kill.patch` | the start-up watchdog's KILL in `Service.qml` deleted (round 14, R24g): a TERM-ignoring start-up process (the slow tree's init with `OMARCHY_IPTV_SLOW_IGNORE_TERM=1`) is never ended | B17 (`helper:no(<pid>)`, `blocked:` empty, `told:0`), and in `tests/Model.test.js` the four R24g pins (init and mkdir, both hosts) |
| `r25a-keep-landed.patch` | `Service.qml`'s `stateFile.onSaved` no longer clears `recentSaves` when a save lands (round 15, R25a): the old eight-text own-write record, so a backup of an earlier own save put back is ignored as an echo and written over | the four R25a node pins per host and echo mode (16 of 2491), and key-scenario's B19 restore |
| `r25a-clear-every-saved.patch` | `recentSaves` cleared on EVERY `saved`, mid-burst included (round 15, R25a's other half) | the coalesced-burst pin in own echo `load` (the mid-burst echo reads `foreign-save-in-flight`), with R24a IN FLIGHT and R25d a7 |
| `r25b-silent-drop.patch` | the merge's cap drop is logged but the user is not told (round 15, R25b) | the eight R25b node pins |
| `r25d-a5-base-not-moved.patch` | `Service.mergeForeignText` does not move the base to theirs (the round-14 lens's a5, F-HARNESS-26): a second foreign write in one held window is compared with a stale base | the four R25d a5 node pins |
| `r25d-a7-no-inflight-half.patch` | the in-flight half of `mergeForeignText`'s re-save decision deleted (the lens's a7): our older in-flight save lands over a merge equal to theirs | the four R25d a7 node pins, and the in-flight R25b saved-search pin |
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

All ten apply to the tree they are checked in with (`scripts/qa-lib-test.sh`
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
