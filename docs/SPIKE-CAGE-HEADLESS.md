# Spike: the dev harness under headless cage

2026-09-21. Two independent runs, the second reproducing the first from its
recipe alone. Both against a nested compositor with its own display; the live
session (`wayland-1`, quickshell pid 1058) was never used, verified by pid,
by socket mtime, and by a guard that refused any `wtype`/`grim`/`quickshell`
aimed at `wayland-1`.

## Verdict: PARTIAL, and the blocker is ours

`cage` 0.3.1 starts headless on this machine on the first try
(`WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1`),
1280x720. Inside it:

| Capability | Result |
|---|---|
| Screen capture (`grim`, zwlr_screencopy v3) | works; a stdlib PNG decoder tells a blank frame (1 colour) from a mapped window (300-1000) |
| Keyboard injection (`wtype`, zwp_virtual_keyboard v1) | works; reaches a focused `TextInput` in an ordinary Quickshell `FloatingWindow` |
| Qt Quick rendering | works, under GL, software and llvmpipe alike |
| Theme tokens | resolve to the live theme (`#1e1e2e`, not `Color.qml`'s fallback) |
| The harness IPC surface (state, query, rows, sources, numbers, open/close) | works; ready guide 2.0-2.3 s after launch |
| **The guide's window** | **never maps**: cage advertises no `zwlr_layer_shell_v1`, and `Guide.qml:1912` is a `PanelWindow` with `WlrLayershell` attached |

Quickshell logs `Failed to initialize layershell integration` three times a
run and carries on windowless. The registry dump lists 25 globals; layer-shell
is not among them, and no renderer or environment variable changes that.

The X11 route is closed by the plugin, not by cage: on `xcb` the harness bar
maps and draws in theme colours, but `Guide.qml:1917-1919` sets
`WlrLayershell` attached properties unconditionally, which is a creation error
there, so the guide component does not load at all -- and an X11 panel window
under cage takes no keyboard focus anyway.

## What this buys today

Anything graded through IPC or by observing processes can run headless now:
the harness under cage, a stub `hyprctl` on `$OMARCHY_IPTV_HARNESS_DIR/bin`,
`HYPRLAND_INSTANCE_SIGNATURE` unset. That includes the D-ID-1 residue -- the
real helper's argv during an active fetch -- and the IPC verbs of D-QA-04.

## What one small change would buy forever

A harness-only window mode in which the guide is hosted in a `FloatingWindow`
(production unchanged: `PanelWindow` + layer-shell on the real shell) would
let pixel and keystroke cases run under cage: row heights, contrast rungs,
header and footer strings, the hint's rendering. Keyboard focus semantics
differ from the exclusive layer-shell focus, so cases about focus itself stay
live; cases about what is painted and what a keystroke does to the model do
not.

## Runner hygiene, measured

- The nested display was `wayland-0` both times, not `wayland-2`: cage takes
  the first free name. Never assume; read it from the child.
- Stop cage by killing its CHILD (recorded by the child itself); cage then
  exits in 0.2 s and removes its socket. `SIGTERM` to cage was ignored for
  10 s and left a stale `wayland-0` behind.
- Pass `WAYLAND_DISPLAY=<nested>` into every `run.sh` call; `harness_env`
  defaults an unset value to `wayland-1`, the live session.
- The service probes `hyprctl` at startup; stub it or it reads the live
  compositor.
- Under XWayland expect a `cannot open display` race for ~10 s after the
  last X client exits; retry, do not conclude.

Full transcripts under the session's `subagents/workflows/wf_d968f512-15e/`.
