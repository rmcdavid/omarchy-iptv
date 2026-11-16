"""scripts/dev-harness/spikes/state-private/interval.py -- D-SINK-103's open
window, timed: from `state private` making state.json 0600 to the writer
linking the text it wrote under a name. measure.sh's `interval` mode runs
it beside one probe shell, in the fix's order only.

  interval.py OUT FOLDER

FOLDER is the one that holds state.json (the state folder, or the folder a
state.json link points into, where QSaveFile writes). Watches it with
inotify and stamps every event with CLOCK_MONOTONIC at the read, doing
nothing else between reads, so the stamp is the event's arrival give or
take one wake-up. Writes `ready` to OUT once the watch is in place, and on
SIGTERM or SIGINT -- or after 120 s, its own bound -- one line:

  start:<chmod|create|none> link:<ms|none> rename:<ms|none> apart:<yes|no|none> events:<n>

start is the LAST event on `state.json` itself before the writer's link:
IN_ATTRIB, the helper's chmod (a file found at another mode), or IN_CREATE,
the helper's O_EXCL create (nothing there). A file already 0600 is not
chmod-ed, so it raises nothing and reads `start:none`; that window starts
at the helper's read-back and cannot be timed here. link is the time from
the start to the FIRST IN_CREATE of a name beginning `state.json.` -- the
writer's linkat of its temporary. That is NOT the writer's open: QSaveFile
opens an unnamed O_TMPFILE, which raises no event, then fchmods it, writes
and commits, and only then links it (RESULT-2026-11-14.txt, under gdb), so
`link` is an UPPER bound on the time from the chmod to the open. rename is
the time from the start to the IN_MOVED_TO of `state.json`, the rename over
the target. apart is `yes` when the start and the link arrived in two
reads (a `no` is a stamp shared by one read, so a 0.0 there is the
observer's own stall, not the window). Prints no path and reads no file. Stdlib only, through libc's
inotify by ctypes.
"""
import ctypes
import os
import select
import signal
import struct
import sys
import time

IN_ATTRIB, IN_MOVED_TO, IN_CREATE = 0x4, 0x80, 0x100
BOUND_S = 120
NAME = b"state.json"

out, folder = sys.argv[1], sys.argv[2]
libc = ctypes.CDLL(None, use_errno=True)
fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
if fd < 0:
    raise SystemExit("interval: inotify_init1 failed: %s" % os.strerror(ctypes.get_errno()))
if libc.inotify_add_watch(fd, os.fsencode(folder), IN_ATTRIB | IN_MOVED_TO | IN_CREATE) < 0:
    raise SystemExit("interval: cannot watch the folder: %s" % os.strerror(ctypes.get_errno()))

stopping = False


def stop(_sig, _frame):
    global stopping
    stopping = True


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

events = []   # (ns, mask, name)
with open(out, "w") as handle:
    handle.write("ready\n")
deadline = time.monotonic() + BOUND_S
while not stopping and time.monotonic() < deadline:
    try:
        ready, _, _ = select.select([fd], [], [], 0.2)
    except InterruptedError:
        continue
    if not ready:
        continue
    try:
        buf = os.read(fd, 65536)
    except (BlockingIOError, InterruptedError):
        continue
    now = time.monotonic_ns()
    offset = 0
    while offset + 16 <= len(buf):
        _wd, mask, _cookie, length = struct.unpack_from("iIII", buf, offset)
        name = buf[offset + 16:offset + 16 + length].split(b"\0", 1)[0]
        events.append((now, mask, name))
        offset += 16 + length

# By position, not by stamp: events read in one batch share a stamp, and the
# order the kernel queued them in is the order they happened in.
link_i = next((i for i, (_ns, mask, name) in enumerate(events)
               if mask & IN_CREATE and name.startswith(NAME + b".")), None)
link_at = None if link_i is None else events[link_i][0]
start_i, start_at, start = None, None, "none"
for i, (ns, mask, name) in enumerate(events[:len(events) if link_i is None else link_i]):
    if name != NAME:
        continue
    if mask & IN_ATTRIB:
        start_i, start_at, start = i, ns, "chmod"
    elif mask & IN_CREATE:
        start_i, start_at, start = i, ns, "create"
rename_at = next((ns for i, (ns, mask, name) in enumerate(events)
                  if mask & IN_MOVED_TO and name == NAME and (start_i is None or i > start_i)), None)


def ms(end):
    if start_at is None or end is None:
        return "none"
    return "%.1f" % ((end - start_at) / 1e6)


with open(out, "w") as handle:
    apart = "none" if start_at is None or link_at is None else ("yes" if link_at != start_at else "no")
    handle.write("start:%s link:%s rename:%s apart:%s events:%d\n" % (start, ms(link_at), ms(rename_at), apart, len(events)))
