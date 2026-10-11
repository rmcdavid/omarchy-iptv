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
the one switch on that slot in every version of it; and, for the paste the
user asks for, the helper's `clipboard` verb (R8, `51866a3`), which reads at
most 32 KiB of `wl-paste`'s output and terminates it, so the shell holds one
bounded reply and never the offer. The scenario that observes both is
`scripts/dev-harness/clip-scenario.sh`, built from the probes here.

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
the catchpoint stopped eighteen times on the editable probe, four of them
the WaylandClient thread-start pipes the no-field probe has too, and the
other FOURTEEN after the offer, every one through
`QInternalMimeData::retrieveData <- QMimeData::text <-
QQuickTextInput::q_canPasteChanged <- QPlatformClipboard::emitChanged <-
wl_display_dispatch_queue_pending`; the no-field probe created no pipe after
the offer (an earlier version of this paragraph said ten; the recount is
`docs/QA-RESULTS.md`'s, by `grep -c q_canPasteChanged` over the gdb log). A
reader asking for the offer as a consumer would (`wl-paste`) received
104,857,601 bytes, so the producer served what it offered.

## The same three rows under a nested headless cage, 2026-10-11

What `clip-scenario.sh` re-measures: the probe arm of every live run over
100 MB, and `check-tree` on every commit over 25 MB (DR-B1, below). One
`cage` (`WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1`)
on a display of its own, read from cage's child (it was `wayland-0` every
time; never assumed); a virtual keyboard held on the seat (`wtype -s`); each
probe started with `QT_QPA_PLATFORM=wayland` on that display, its RSS left
to settle (two samples 300 ms apart within 512 KB), then the offer of
`text/plain` from `wl-copy --foreground` on the same display and about 2 s
of samples. The first measurement sampled at 100 ms (20 samples); the
scenario now samples at 20 ms (50 samples, about 40 ms a turn with the read
of `/proc`), for the reason the 25 MB rows give:

| offer | probe | RSS before | RSS peak | growth | runs |
|---|---|---|---|---|---|
| 100 MB | `editable.qml` | 279..281 MB | 517..588 MB | **+235..+307 MB** (2.3..3.1x the payload) | 13 of 13 |
| 100 MB | `readonly.qml` | 281 MB | 281 MB | +0 | 13 of 13 |
| 100 MB | `nofield.qml` | 276..280 MB | 276..280 MB | +0 | 13 of 13 |
| 25 MB, sampled at 100 ms | `editable.qml` | 281 MB | 318..362 MB | +36..+80 MB (1.4..3.2x) | 4 of 4 |
| 25 MB, sampled at 20 ms | `editable.qml` | 279..281 MB | 338..360 MB | **+58..+80 MB** (2.3..3.2x) | 7 of 7 |
| 25 MB | `readonly.qml` | 281..282 MB | 281..282 MB | +0 | 7 of 7 |
| 25 MB | `nofield.qml` | 276 MB | 276 MB | +0 | 7 of 7 |

A 25 MB read is a transient of about 80 ms -- sampled at 20 ms, one editable
run read 0, 0, 15, 37, 43, 78 and then 36 MB for the rest of its window --
so a sampler at 100 ms reports whatever its one sample inside the transient
happened to see, from the +36 MB that stays (the decoded string; 1.4x the
payload) to the +80 MB peak. The scenario's P3 asserts growth of at least
the payload, which even the settled tail satisfies at 25 MB; sampling at
20 ms is what makes the number it prints the read's and not the sampler's.
At 100 MB the read takes several hundred ms and either rate catches it.

The no-field row reads +0 here and +52 MB in the lead's table because the
scenario offers only after the RSS has settled, so Qt's startup growth is
already behind the "before" sample. The "before" is higher than the lead's
because the pixman renderer and the wayland platform plugin map more than
the lead's GL path did. The three probes, with the compositor's start and a
consumer reading the full offer back, take about 9 s at 25 MB and about
14 s at 100 MB.

**Why the gate offers 25 MB (DR-B1).** The editable probe holds about three
times the payload while it reads: at 100 MB that is a 300 MB transient on
every commit, and a machine short of memory could kill the probe mid-read
and turn P3 red for a reason that is not the sink. A quarter of the payload
keeps the gate's transient under 100 MB; the live run keeps the lead's and
the maintainer's 100 MB. `CLIP_OFFER_MB` overrides either.

**The seat, found by lane A and load-bearing.** cage's headless seat has no
keyboard, and a compositor hands `wl_data_device.selection` only to the
client holding keyboard focus, so with nothing on the seat NOT EVEN the
editable probe reads (+0 on both probes, and a consumer `wl-paste` on that
display receives 0 bytes; reproduced by two reviewers). cage's log says
nothing about it: under `WLR_BACKENDS=headless` the log is six wlroots INFO
lines -- the backend and renderer being chosen and created, `Failed to
create wlr_drm_lease_manager_v1`, and last `Starting headless backend` --
with no line about a seat or a keyboard (read off a cage started by hand
2026-10-11; an earlier version of this paragraph quoted a `This seat has no
keyboard` line that no cage log carries). The sink opens only once a
keyboard is on the
seat: a virtual keyboard (`wtype -s 60000 ''`, held across the offer on the
nested display) reproduces the lead's numbers. A cage measurement that
omits this passes vacuously, which is why the scenario asserts the editable
row's growth in both of its arms as the control that offers are delivered
at all.

## The shell itself, 2026-10-11, same cage

The dev-harness fake shell with the real `Guide.qml` and `Service.qml`, in
the harness-only floating window, opened into the first-run form with the
playlist field focused, the same 100 MB offer, RSS sampled 1 s before and
3 s after concurrently with twelve IPC round trips timed from the instant
of the offer (`clip-scenario.sh live`, four runs each):

| tree | RSS before | peak | growth | round trips after the offer (ms) |
|---|---|---|---|---|
| `d55149b` (shipped 0.13.4, fields editable) | 344..349 MB | 589..642 MB | **+240..+297 MB** (about 2.5x the payload) | 105..147, 57..81, then ONE of **673..746** when a call lands inside the read (7 runs of 7), 56..61 after |
| `44b250b` and later (fields read-only) | 319..349 MB | same | **+0 MB** | 96..159 first (process cold start), 55..88 after |

The baseline's RSS falls back to about 435..444 MB within a second (the byte
array freed, the decoded string kept), which is why the sampler runs during
the read and not after it: sampled afterwards the growth read +89 MB where
the peak is +254. A paste through Ctrl+V of a 5,000-byte offer lands at
2,112 characters on both trees (the fixed tree through the helper and
`Model.editInsert` fitted to `Model.formCapacity`, the baseline through Qt's
own `maximumLength` truncation).

### The user's own paste over the offer (L10), same cage, 2026-10-11

The change-driven read is the finding; the user-initiated one is its other
half (the review's DR-1). The field is selected whole (Ctrl+A) and Ctrl+V is
sent over the same 100 MB offer, with the shell's RSS sampled from 0.5 s
before the chord for about 6 s and any clipboard helper under the shell
watched by pid:

| tree | shell before | peak | growth | kept at the window's end | helper child |
|---|---|---|---|---|---|
| `96f5261` (read-only fields; the SHELL runs `wl-paste` and collects its whole output, then cuts) | 329..334 MB | 639 MB | **+304..+310 MB** | +292..+300 MB | none |
| `d55149b` (editable; Qt pastes natively) | 435 MB (the offer's decoded string still held from L4) | 557 MB | **+122 MB** | +0 | none |
| `51866a3` (R8: the helper's `clipboard` verb reads at most 32 KiB) | 331 MB | 331..338 MB | **+0, +0, +7 MB** | -3..+6 | one, peak RSS 32 MB, gone within the window |

The field reads 2,112 characters of the new letter on every tree, so the
paste landed in each case; what differs is who read the offer and how much
of it. The band L10 asserts is the shell's 16 MB, the same as L4's.

### Interrupted runs

`timeout -s TERM 19 clip-scenario.sh` (landing after L3, with the detached
shell, the cage and the nested socket all up) with the EXIT trap alone left
`cage -- .../child.sh`, `quickshell -p .../omarchy-iptv-clip/root`,
`sleep 120`, `wayland-0` and the work directory behind: bash runs no EXIT
trap for a signal that kills it while it waits on a foreground child. With
`trap 'exit 130' INT` and `trap 'exit 143' TERM` beside it (the lines
player-, rewind- and tls-scenario.sh already had), the same TERM at 24 s and
at 6 s, and an INT at 24 s, left nothing: no cage, no shell, no `sleep`, no
`wtype`, no socket, no work directory. Measured 2026-10-11, both ways.

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
