# Dev harness

A standalone Quickshell config that loads `Service.qml`, `Guide.qml` and
`BarWidget.qml` straight from this repo with fake `shell`, `manifest`, `bar`
and `settings` objects, plus scratch XDG directories, so the plugin can be
smoke-tested without installing it into `~/.config/omarchy/plugins`.

Running it opens real windows (a thin fake bar strip at the top of the
screen and, on `--open`, the guide overlay) on the current Wayland session.
Keep runs short; `run.sh` kills Quickshell after `--timeout` seconds
(default 15) and reaps any mpv it launched.

## How `qs.Commons` / `qs.Ui` resolve (Quickshell 0.3.1)

Quickshell maps the `qs` import prefix to the **config root** (the
directory given to `quickshell -p`). `run.sh` therefore builds a scratch
root under `$XDG_RUNTIME_DIR/omarchy-iptv-harness/root/` containing a copy
of `shell.qml` and two symlinks, `Commons -> /usr/share/omarchy/shell/Commons`
and `Ui -> /usr/share/omarchy/shell/Ui`. Files loaded from outside that root
(the plugin's own QML, referenced by absolute `file://` URLs) still resolve
`import qs.Commons` because the mapping is engine-wide -- the same mechanism
the real shell uses for third-party plugins. No symlinks are ever created
inside the plugin folder (the validator rejects them).

`QML_IMPORT_PATH`-style mapping (`/tmp/qmlroot/qs/{Commons,Ui}`) is only
used by `scripts/check.sh` for `qmllint`; Quickshell itself needs the root
layout above.

## Scratch layout and environment

```
$OMARCHY_IPTV_HARNESS_DIR   (default $XDG_RUNTIME_DIR/omarchy-iptv-harness)
  root/      shell.qml + Commons/ Ui/ symlinks
  cache/     XDG_CACHE_HOME  -> cache/omarchy-iptv/{channels,playlist-status,epg-now}.json
  state/     XDG_STATE_HOME  -> state/omarchy-iptv/state.json
  runtime/   XDG_RUNTIME_DIR -> runtime/omarchy-iptv/mpv.sock (+ hypr -> real hypr dir)
  fixtures/  generated harness.m3u (and test.ts with --serve)
  shots/     screenshots from `run.sh shot`
```

Because `XDG_RUNTIME_DIR` is redirected, `run.sh` exports `WAYLAND_DISPLAY`
as the absolute socket path (libwayland accepts that) and symlinks the real
`hypr/` directory so `hyprctl` keeps working. `run.sh ipc` re-exports the
same runtime dir so `qs ipc` can find the instance.

Environment read by `shell.qml` (all set by `run.sh`): `OMARCHY_IPTV_ROOT`,
`OMARCHY_IPTV_PLAYLIST`, `OMARCHY_IPTV_EPG`, `OMARCHY_IPTV_OPEN`,
`OMARCHY_IPTV_VERTICAL`, `OMARCHY_IPTV_SHOW_NAME`, `OMARCHY_IPTV_LABEL_MAX`,
`OMARCHY_IPTV_MPV_ARGS`.

## Usage

```bash
scripts/dev-harness/run.sh --open                    # fixture playlist, guide opens, 15 s
scripts/dev-harness/run.sh --open --fake-epg         # + synthetic epg-now.json in the cache
scripts/dev-harness/run.sh --open --serve --timeout 40   # local test video on 127.0.0.1:8765
scripts/dev-harness/run.sh --open --playlist /nonexistent.m3u --keep   # error banner over a kept cache
scripts/dev-harness/run.sh --open --vertical         # glyph-only bar widget
scripts/dev-harness/run.sh clean
```

Drive a running harness from another terminal:

```bash
H=scripts/dev-harness/run.sh
$H ipc open '{}'          $H ipc close        $H ipc toggle
$H ipc query sky          $H ipc mode         $H ipc move 1      $H ipc scope 1
$H ipc setScope favorites $H ipc activate true  # Space semantics (keep open)
$H ipc favorite           $H ipc remove       $H ipc stop        $H ipc refresh
$H ipc zap 1              $H ipc set showChannelName false
$H ipc state              # JSON dump of guide + service state
$H ipc widget             # JSON dump of the bar widget (glyph, label, tooltip)
$H ipc tooltip            # last tooltip text the widget asked the bar to show
$H key -k Tab             # real key events via wtype (overlay has exclusive focus)
$H key j j f              # e.g. list mode: down, down, favorite
$H shot search            # grim screenshot -> shots/search.png
```

`run.sh key` uses `wtype`, which delivers real key events through the
compositor, so both keyboard modes can be verified end to end
(`wtype -k Escape`, `wtype -k Return`, `wtype bbc`).

## What the fixture contains

`fixtures/harness.m3u.in` has 20 channels in 9 groups (multi-group
`Animation;Kids;Religious`, an ungrouped pair, diacritics, Cyrillic, an
`#EXTVLCOPT` user agent). Every stream URL points at `127.0.0.1:9` (TCP
discard, connection refused) so mpv fails within a second and exercises the
failure path; `--serve` swaps the first channel for a generated local video
so the success path (window, title, health checks, stop) can be watched.

Note: while Lane A's helper `play` / `stop` / `status` subcommands are stubs
(`not_implemented`, exit 3) the service treats their answers as "unknown"
(no health failure counted), zapping while mpv runs logs the stub error,
and stop falls back to SIGTERM after 2 s.
