# Dev harness

A standalone Quickshell config that loads `Service.qml`, `Guide.qml` and
`BarWidget.qml` straight from this repo with fake `shell`, `manifest`, `bar`
and `settings` objects, plus scratch XDG directories, so the plugin can be
smoke-tested without installing it into `~/.config/omarchy/plugins`.

Running it opens real windows (a thin fake bar strip at the top of the
screen and, on `--open`, the guide overlay) on the current Wayland session.
Keep runs short; `run.sh` kills Quickshell after `--timeout` seconds
(default 15). An `EXIT` trap reaps everything it started (the fixture HTTP
server, Quickshell and any harness mpv) on a normal exit, the timeout,
Ctrl-C or SIGTERM; a SIGKILL of `run.sh` cannot be trapped, so the next
start also reaps a stale fixture server. The playlist/EPG source is echoed
as `scheme://host` only and `updateEntryInline` logs the entry's keys, never
its values: a real provider URL would carry credentials into the terminal
scrollback.

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

### Sources (M2-01)

The fake `updateEntryInline` applies the entry to the fake `barConfig`
exactly like the host does (full-entry replace, `id` forced, `false` when
nothing changed), so `switchSource` / `addSource` round-trip through the
same settings binding the service uses in the real shell. The log line
still names the entry's keys only. Source signals
(`sourceProbeFinished`, `sourceSwitched`, `sourceRemoved`,
`sourcesPersistFailed`) are logged as `[harness] ...` lines; their payloads
are URL-free by contract.

Service actions over IPC (arguments may carry a URL or path; results never
do; pass `""` for an argument you do not need):

```bash
$H ipc addSource /path/or/url "" ""        # -> {"ok":true,"code":"ok","message":"","id":"<key>"}
$H ipc addSource http://h/x.m3u http://h/e.xml "My label"
$H ipc updateSource <key> '{"label":"NAS"}'            # label / epgUrl commit at once
$H ipc updateSource <key> '{"playlistUrl":"/new.m3u"}' # probes first, re-keys on success
$H ipc switchSource <key>      $H ipc retrySource <key>     $H ipc removeSource <key>
$H ipc cancelProbe             # while probing: discards the probe's cache dir
$H ipc xtream http://127.0.0.1:8765 user 'pa ss'       # -> addSource of the built URLs
$H ipc sources                 # JSON of service.sources (id/label/host/kind/counts, no URL)
$H ipc editMasked <key>        # the edit-form view with playlistMasked / epgMasked only (alias: sourceEdit)
$H ipc signals                 # the last 20 source signal payloads (sourceProbeFinished, sourceSwitched,
                               #   sourceRemoved, sourcesPersistFailed, configuredChanged), oldest first
$H ipc failPersist true        # takes updateEntryInline off the shell api (a host that cannot write
                               #   our entry) until `failPersist false`; a false RETURN is not a failure
$H ipc activeCache             # cache/omarchy-iptv/sources/<key> of the active source
$H ipc set playlistUrl /path   # CLI parity: reconciles into the history (origin cli)
$H ipc setStored playlistUrl /path  # `set` without the user-config re-read: the host stores the value
                               #   but has not published it, so the plugin still sees the previous one
$H ipc hostEntry               # {"stored":"<key>","published":"<key>"}: what the host has stored for our
                               #   entry vs what it has handed the plugin. They differ by one write.
$H ipc state                   # + activeSourceKey, cacheReady, probing, switching, sourceErrors, settingsInvalid,
                               #   canAddSource; guide: returnMode, sourceCursor(Kind), formFocus, formActive,
                               #   formProbing, sourcesNotice (the Sources result line: a failed switch probe),
                               #   sourcesProbeText (`Fetching from <host>...` while a switch probes),
                               #   invalidSettingsText (UX 5.4 sentence for a CLI-invalid playlistUrl),
                               #   footerHint (tags stripped) and `form` (kind, origin, sourceId, focus, error,
                               #   values as { value: masked, length, masked, revealed } per field; credentials are ****)
```

`state().guide.form` masks with the plugin's own `Model.js`, which `run.sh`
copies into the scratch root next to `shell.qml`; a raw form value never
reaches the terminal.

`run.sh --source2 SRC` seeds the history with a second, never-fetched
record before start (helper `state source add`), so `switchSource` takes
the probe path. `OMARCHY_IPTV_DEBUG=1` makes the service log
`omarchy-iptv switch <ms>` per switch (measured from `switchSource` to the
new `channels.json` being applied).

`run.sh scenario` runs `sources-scenario.sh`: a scripted pass over H1
(migration from a v0.1 cache + v1 state), H5 (add failure keeps the active
source and saves nothing, SR23), H2 (add, probe, switch), H6/H8 (five
switches each way against a generated 10k list, median must stay under
150 ms), probe cancel (a silent loopback server), H9 (CLI parity through
`set playlistUrl`), H11 (duplicate), H12 (label / EPG edits, `editMasked`),
H7 (remove the active source), a `failPersist` switch (SR25) and privacy
greps over the log and IPC output. It prints one PASS/FAIL line per check and a summary; the
harness log is `$SCRATCH/scenario.log`.

### The fake host publishes one write behind (D-LIVE-20 / D-LIVE-21)

`shell.qml` here reproduces the real host's config plumbing in its shape
**and its declaration order**: `shellConfig`, then the change handler that
republishes every plugin api (`/usr/share/omarchy/shell/shell.qml:66` ->
`pluginsChanged` -> `syncPluginApis` -> `publicBarConfig`), then the
`barConfig` binding that handler reads (shell.qml:109). A QML change handler
runs before the bindings that depend on the same property are re-evaluated,
so what a plugin is handed is the **previous** bar. An external write gets a
second assignment when the user-config FileView re-reads the changed file
and so lands promptly; a plugin's own `updateEntryInline` is the last
assignment there is, and the host's own `FileView.setText` does not
re-trigger its watcher, so its echo never arrives at all.

The earlier fake fed the plugin's own write straight back into
`fakeShell.barConfig`, which is exactly what the real host does not do: it
masked both P1 defects through two QA passes. Keep the ordering above
intact. `ipc hostEntry` shows the two sides, and the scenario's
`== D-LIVE-20` block asserts that a switch takes effect **while** the
published bar still names the previous source. Against a service that waits
for the echo that block fails, along with H2, H6/H8 and H7.

Pitfalls seen in the QA and fix passes: `wtype space` types the letters
s-p-a-c-e (use `wtype -k space`); `wtype -d 0` is rejected (`-d 1` works);
chords are `wtype -M ctrl u -m ctrl` (there is no `-k ctrl+u`); and a
`pkill -f`/`pgrep -f` whose pattern also appears in your own shell's
command line matches (and kills) that shell, so bracket one character of
the pattern (`quickshell -p .../roo[t]`). The AF_UNIX socket path is limited
to ~108 bytes: keep `OMARCHY_IPTV_HARNESS_DIR` short.

## What the fixture contains

`fixtures/harness.m3u.in` has 20 channels in 9 groups (multi-group
`Animation;Kids;Religious`, an ungrouped pair, diacritics, Cyrillic, an
`#EXTVLCOPT` user agent). Every stream URL points at `127.0.0.1:9` (TCP
discard, connection refused) so mpv fails within a second and exercises the
failure path; `--serve` swaps the first channel for a generated local video
so the success path (window, title, health checks, stop) can be watched.

The diacritics and the Cyrillic are the point of two of those rows
(`Tele-Quebec`, `Pervyj kanal`, spelled in full in the file), and they are
also why `scripts/check.sh` is currently RED. The ASCII gate used to iterate a
hand-maintained list that silently skipped every directory, so this file and
`tests/fixtures/qa-player/qa-player.m3u` had never been scanned; the widened
gate scans them and reports them. CLAUDE.md rule 8 covers `.js` and `.py`
sources, not playlist fixtures, so the likely resolution is to name these two
in the gate's visible exclusion list beside `*/nonascii/*` - but that is one
ruling covering a file in another lane's tree as well as this one, and
narrowing a scan on a lane's own initiative is exactly what the cleanup round
forbids. Left red on purpose, with the decision raised rather than taken.

Note: while Lane A's helper `play` / `stop` / `status` subcommands are stubs
(`not_implemented`, exit 3) the service treats their answers as "unknown"
(no health failure counted), zapping while mpv runs logs the stub error,
and stop falls back to SIGTERM after 2 s.
