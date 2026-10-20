# open-mutations: what open-scenario.sh was seen red against

`scripts/dev-harness/open-scenario.sh` (R27f, D-PERF-1; R28d) times the
guide's open up to the first frame whose presenting view DRAWS a whole screen:
the delegates that intersect its visible area, tiling it, against the rows
the guide has. Rule 11: the number has to MOVE when delegate creation gets
slower, and a view that draws part of a screen and fills the rest later must
not pass, or it is the old `openMs` again -- a clock that stops before the
work it is about.

| patch | what it breaks | what moves |
|---|---|---|
| `slow-delegate.patch` | every channel delegate, list row and wall tile alike, spends 4 ms in its `Component.onCompleted` | on a COLD open both the summon time and the realised time grow. The summon grows too because a cold summon builds delegates synchronously, the hidden view's among them (lane-sweep-a1's run, `open-20261020-123804-1537394`: cold summon 95 -> 207 ms for the list and 94 -> 198 ms for the wall; R27f's realised time +101 ms and +60 ms). Until R28d this file said the summon time does not grow, which that run contradicted. The R28d re-measure is in the harness README |
| `late-fill.patch` | both channel views' model is `min(rowCount, 6)` until 300 ms after `open()`, then the whole `rowCount`: a view that draws part of a screen and fills the rest in late | the realised time: R28d's instrument does not call the open realised until the screen is tiled, so a WARM open reads about 300 ms and L6 / W6 (the warm median under 150 ms) go red. R27f's instrument read the six-row screen as the open and passed L1-L5 with a fast BUDGET (round 1's live review) |

Apply to an export, never to the working tree:

    git archive HEAD | tar -x -C /tmp/x && patch -d /tmp/x -p1 < slow-delegate.patch
    scripts/dev-harness/private-bus.sh <dir> 1800 scripts/dev-harness/open-scenario.sh live --tree /tmp/x
