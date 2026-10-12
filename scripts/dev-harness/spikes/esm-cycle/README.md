# Spike: a cyclic import graph between ES module parts (D-REL-5)

The model became `Model.mjs` plus parts under `model/`, and parts cut by
domain call each other both ways, so the import graph has cycles (today one
strongly connected component holds all eighteen parts). Before the split
was allowed to rely on that, it was measured on 2026-10-12 here: node
v26.8.1, Qt 6.11.2, Quickshell under a nested headless cage.

`parts/a.mjs`, `b.mjs` and `c.mjs` import each other in a cycle; `Agg.mjs`
re-exports from them in an order that is not the dependency order.
`b.mjs` carries one deliberate hazard: an initializer that reads `A_CONST`
from `a.mjs` across the cycle.

| Engine | Links and calls across the cycle | `B_SEES_A_AT_INIT` |
|---|---|---|
| node (`import`) | yes: `aFn(1)` = `ab315c73b3z`, `cFn()` = `c73b3z` | `undefined` |
| qmltestrunner | yes: 3 passed, 0 failed | `undefined` |
| Quickshell, nested cage | yes: `QS-CYCLE PASS` in its log | `undefined` |

So cycles are fine for calls, which run after every part has evaluated,
and an initializer that reads another part of a cycle gets `undefined`
SILENTLY -- no error in any of the three. That is why
`scripts/split-model.mjs` enforces init locality (no top-level initializer
reads another part, directly or through a same-part function) instead of an
acyclic graph, and refuses to write a split that breaks it.

Re-run: `./run.sh` (node and qmltestrunner). The Quickshell arm, under a
nested cage only, never the live session:

    WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 \
      cage -- sh -c 'echo "$WAYLAND_DISPLAY" > /tmp/d; exec sleep 600' &
    # then, with D the nested display and R a private 0700 runtime directory:
    env -u HYPRLAND_INSTANCE_SIGNATURE XDG_RUNTIME_DIR=$R \
      WAYLAND_DISPLAY=/run/user/$(id -u)/$D timeout 30 quickshell -p shell.qml

and read `QS-CYCLE` from its output (`Qt.quit()` has no receiver in
Quickshell, so the timeout ends it). Stop the cage by killing its child.
