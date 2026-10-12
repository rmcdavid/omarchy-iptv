# key-mutations: the two one-decision mutations key-scenario.sh was seen red against

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
two diffs, byte for byte.

| patch | what it breaks | which checks go red |
|---|---|---|
| `d3-save-parked.patch` | `Model.reloadDisposition`'s `save-parked` clause deleted: a reload over a PARKED save is applied as `file-newer` (the D-SRC-15 drop, re-opened) | D2, D3, W2, W3, W4, W6 -- the per-reason counter reads `{"file-newer": 1, "first-load": 1, "own-write": 1}` and `save-parked` is absent |
| `r14-no-return.patch` | `Service.applyUserState`'s R14 `return` deleted: the reload is COUNTED as ignored and then applied anyway | D2, W2, W3, W4, W6 -- and D3 GREEN, with `{"save-parked": 1, ...}` beside the loss at the sink: a counter observes the decision, D2/W2 observe the sink, and the `return` itself is pinned structurally in `tests/Model.test.js` (R14) |

Both apply to the tree they are checked in with (`scripts/qa-lib-test.sh`
runs `git apply --check` on each, so a refactor that moves either hunk is a
red gate, not a silently stale patch).

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
