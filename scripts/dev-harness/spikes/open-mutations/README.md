# open-mutations: what open-scenario.sh was seen red against

`scripts/dev-harness/open-scenario.sh` (R27f, D-PERF-1) times the guide's
open up to the frame its presenting view has realised a screen of delegates.
Rule 11: the number has to MOVE when delegate creation gets slower, or it is
the old `openMs` again -- a clock that stops before the work it is about.

| patch | what it breaks | what moves |
|---|---|---|
| `slow-delegate.patch` | every channel delegate, list row and wall tile alike, spends 4 ms in its `Component.onCompleted` | the realised time grows by about 4 ms a delegate on a COLD open (13 rows, 21 tiles at 1280x720); the summon time does not, because a view creates its delegates after the summon returns -- which is the whole of D-PERF-1 |

Apply to an export, never to the working tree:

    git archive HEAD | tar -x -C /tmp/x && patch -d /tmp/x -p1 < slow-delegate.patch
    scripts/dev-harness/private-bus.sh <dir> 1800 scripts/dev-harness/open-scenario.sh live --tree /tmp/x
