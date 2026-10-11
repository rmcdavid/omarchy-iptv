# clip-offer: the D-CLIP-1 measurement, re-runnable

An editable QtQuick `TextInput` is a clipboard READER. On the released Qt
6.11.2 every one of them subscribes to `QClipboard::dataChanged`, and the
slot calls `QMimeData::text()`, which on Wayland reads the whole foreign
offer through a pipe -- 1 s timeout per read, no total limit, no deadline --
synchronously, on the main thread of the process that owns the field. For
this plugin that process is `omarchy-shell` and the fields are the first-run
and add-source form's, for as long as the form is open, at every clipboard
change by any application on the desktop. Raised by the marketplace
maintainer on omacom/omarchy-plugin-marketplace#11077 against the shipped
0.13.4 (`d55149b`); the lead's write-up, with the attribution to the two
upstream commits that added the read (`c82ef988`, 2026-02-18, shipped in
6.11.2) and removed it (`7d0a433a`, 2026-09-15, after the cut), is
`docs/QA-RESULTS.md` under "Sixth maintainer finding, 2026-10-11". The fix
is `readOnly: true` on every form field (lane A, `44b250b`): `readOnly` is
the one switch on that slot in every version of it. The scenario that
observes the sink is `scripts/dev-harness/clip-scenario.sh`, built from the
probes here.

## The files

| file | what it is |
|---|---|
| `editable.qml` | the lead's probe: one `QtQuick.Controls` `TextField` (the base type the host's `qs.Ui.TextField` inherits), `readOnly: false`, `maximumLength: 2048`, in a 320x120 window that quits itself after 9 s |
| `readonly.qml` | the same with `readOnly: true` |
| `nofield.qml` | the same window with a `Rectangle` and no field at all |
| `gdb.cmds` | the catchpoint on `pipe2` (the offer read creates its pipe there) with an 18-frame backtrace at every hit, which is how the read was attributed rather than inferred |

All four are byte-for-byte the lead's rig (sha256 in the commit that added
them). They are not edited to run faster: the scenario kills each probe by
its pid once its window has been sampled, so the 9 s timer is never reached.

## The lead's table, 2026-10-11, under the user's compositor

A throwaway `qml` client (never the user's shell) on `wayland-1`, a foreign
producer (`wl-copy`) offering 100 MB of `text/plain` 2.5 s after the window
was up, resident set sampled every 100 ms from outside:

| probe | RSS before | RSS peak | growth | last growth at |
|---|---|---|---|---|
| `editable.qml` | 164 MB | 403 MB | +238 MB | 600 ms after the offer |
| `readonly.qml` | 163 MB | 163 MB | +0 | none |
| `nofield.qml` | 105 MB | 157 MB | +52 MB | 600 ms, one sample in `pipe_read` |

The 52 MB of the no-field row is the toolkit starting up, not the clipboard:
the catchpoint saw ten `pipe2` hits after one offer on the editable probe,
every one through `QInternalMimeData::retrieveData <- QMimeData::text <-
QQuickTextInput::q_canPasteChanged <- QPlatformClipboard::emitChanged <-
wl_display_dispatch_queue_pending`, and ZERO on the no-field probe. A reader
asking for the offer as a consumer would (`wl-paste`) received 104,857,601
bytes, so the producer served what it offered.

## The same three rows under a nested headless cage, 2026-10-11

What `clip-scenario.sh check-tree` re-measures on every commit. One `cage`
(`WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1`) on a
display of its own, read from cage's child (it was `wayland-0` every time;
never assumed); a virtual keyboard held on the seat (`wtype -s`); each probe
started with `QT_QPA_PLATFORM=wayland` on that display, its RSS left to
settle (two samples 300 ms apart within 512 KB), then 100 MB of `text/plain`
from `wl-copy --foreground` on the same display and 2 s of samples at 100 ms:

| probe | RSS before | RSS peak | growth | runs |
|---|---|---|---|---|
| `editable.qml` | 279..281 MB | 517..586 MB | **+235..+305 MB** (2.3..3.0x the payload) | 10 of 10 |
| `readonly.qml` | 281 MB | 281 MB | +0 | 10 of 10 |
| `nofield.qml` | 276..280 MB | 276..280 MB | +0 | 10 of 10 |

The no-field row reads +0 here and +52 MB in the lead's table because the
scenario offers only after the RSS has settled, so Qt's startup growth is
already behind the "before" sample. The "before" is higher than the lead's
because the pixman renderer and the wayland platform plugin map more than
the lead's GL path did. Each probe takes about 3.8 s; the three, with the
compositor's start and a consumer reading the full offer back, 12.5 s.

**The seat, found by lane A and load-bearing.** With cage's default headless
seat the compositor logs `This seat has no keyboard` and hands
`wl_data_device.selection` to NO client, so not even the editable probe
reads (+0 on both). The sink opens only once a keyboard is on the seat: a
virtual keyboard (`wtype -s 60000 ''`, held across the offer on the nested
display) reproduces the lead's numbers. A cage measurement that omits this
passes vacuously, which is why the scenario asserts the editable row's
growth in both of its arms as the control that offers are delivered at all.

## The shell itself, 2026-10-11, same cage

The dev-harness fake shell with the real `Guide.qml` and `Service.qml`, in
the harness-only floating window, opened into the first-run form with the
playlist field focused, the same 100 MB offer, RSS sampled 1 s before and
3 s after concurrently with twelve IPC round trips timed from the instant
of the offer (`clip-scenario.sh live`, four runs each):

| tree | RSS before | peak | growth | round trips after the offer (ms) |
|---|---|---|---|---|
| `d55149b` (shipped 0.13.4, fields editable) | 344..349 MB | 600..642 MB | **+254..+297 MB** | 105..147, 57..81, then ONE of **673..685** when a call lands inside the read (4 runs of 4), 56..61 after |
| `44b250b` (fields read-only) | 319..349 MB | same | **+0 MB** | 96..159 first (process cold start), 55..88 after |

The baseline's RSS falls back to about 435..444 MB within a second (the byte
array freed, the decoded string kept), which is why the sampler runs during
the read and not after it: sampled afterwards the growth read +89 MB where
the peak is +254. A paste through Ctrl+V of a 5,000-byte offer lands at
2,112 characters on both trees (the fixed tree through `wl-paste` and
`Model.editInsert` fitted to `Model.formCapacity`, the baseline through Qt's
own `maximumLength` truncation).

Two things about the nested compositor that a re-run must know, both found
by measurement: a producer (`wl-copy`) maps a surface of its own for an
instant to obtain a serial, and one restarted within milliseconds of the
previous one's death leaves the shell's window with NO active focus item
until the next surface maps -- 2 runs in 10, for longer than 4 s -- so a
chord sent then is refused by `run.sh key`'s focus guard (exit 3) rather
than typed; a `wl-paste -l` on the nested display brought focus back within
100 ms in every case, and that is the scenario's nudge.

## Recipe, by hand

```
# a nested compositor on its own display; read the name from the child
WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 \
  cage -- sh -c 'echo $WAYLAND_DISPLAY > /tmp/nested; exec sleep 60' &
N=$(cat /tmp/nested)
WAYLAND_DISPLAY=$N wtype -s 60000 '' &                 # the keyboard on the seat
WAYLAND_DISPLAY=$N QT_QPA_PLATFORM=wayland /usr/lib/qt6/bin/qml editable.qml &
# ... sample /proc/<qml pid>/status VmRSS at 100 ms from here ...
python3 -c "import sys; sys.stdout.write('A'*(100*1024*1024))" \
  | WAYLAND_DISPLAY=$N wl-copy --foreground --type text/plain &
# stop everything by the pids recorded above; cage exits when its child does
```

Nothing in it touches the user's clipboard: the producer and every consumer
are clients of the nested display. The gdb half (`gdb -x gdb.cmds --args
/usr/lib/qt6/bin/qml editable.qml`, then the offer) is for a human and is
not part of any gate; the scenario is.
