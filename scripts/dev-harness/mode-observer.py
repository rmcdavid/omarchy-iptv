"""scripts/dev-harness/mode-observer.py -- D-SINK-103: who could have read a
new credential while the shell wrote it. Watches folders with inotify and,
after every batch of events, reads every regular file in them: its mode and
whether it holds the marker. A file holding the marker with a group or other
bit is a SIGHTING another account could have read at that instant, given a
folder it can enter. key-scenario.sh's PRIVATE segment runs it beside the
real Service.qml; nothing here asks the code what it meant to do.

  mode-observer.py OUT MARKER FOLDER...

Writes `ready` to OUT once every watch is in place (the caller waits for it
before the save), and on SIGTERM or SIGINT -- or after 120 s, its own bound
-- one line:

  observed:<n> exposed:<n> final:<mode|none> [span:<ms> name:mode ...]

observed counts the snapshots that found the marker in some file, exposed
the sightings of a file holding it that granted group or other, final is
the mode of the last file seen holding it, and after it, on a red run, how
long the credential was readable (span: from the first exposed sighting to
the first snapshot after it with none, in ms) and where (the exposed
sightings, folder-relative). The marker is never printed. Stdlib only, through libc's inotify by ctypes; every read and stat
tolerates a file that went away between the event and the look.
"""
import ctypes
import os
import select
import signal
import stat
import sys
import time

IN_MODIFY, IN_ATTRIB, IN_CLOSE_WRITE, IN_MOVED_TO, IN_CREATE = 0x2, 0x4, 0x8, 0x80, 0x100
BOUND_S = 120

out, marker, folders = sys.argv[1], sys.argv[2].encode(), sys.argv[3:]
libc = ctypes.CDLL(None, use_errno=True)
fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
if fd < 0:
    raise SystemExit("mode-observer: inotify_init1 failed: %s" % os.strerror(ctypes.get_errno()))
for folder in folders:
    if libc.inotify_add_watch(fd, os.fsencode(folder), IN_MODIFY | IN_ATTRIB | IN_CLOSE_WRITE | IN_MOVED_TO | IN_CREATE) < 0:
        raise SystemExit("mode-observer: cannot watch a folder: %s" % os.strerror(ctypes.get_errno()))

observed = 0
exposed = []
final = "none"
stopping = False
first_exposed = None
span_ms = None


def stop(_sig, _frame):
    global stopping
    stopping = True


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)


def look():
    global observed, final, first_exposed, span_ms
    holding = False
    was = len(exposed)
    for i, folder in enumerate(folders):
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            path = os.path.join(folder, name)
            try:
                st = os.lstat(path)
                if not stat.S_ISREG(st.st_mode):
                    continue
                with open(path, "rb") as handle:
                    data = handle.read()
            except OSError:
                continue
            if marker not in data:
                continue
            holding = True
            mode = stat.S_IMODE(st.st_mode)
            final = "%o" % mode
            if mode & 0o077:
                exposed.append("%d/%s:%o" % (i, name, mode))
    if holding:
        observed += 1
    now = time.monotonic()
    if len(exposed) > was and first_exposed is None:
        first_exposed = now
    elif len(exposed) == was and first_exposed is not None and span_ms is None:
        span_ms = (now - first_exposed) * 1000.0


with open(out, "w") as handle:
    handle.write("ready\n")
look()
deadline = time.monotonic() + BOUND_S
while not stopping and time.monotonic() < deadline:
    try:
        ready, _, _ = select.select([fd], [], [], 0.2)
    except InterruptedError:
        continue
    if not ready:
        continue
    try:
        while True:
            buf = os.read(fd, 65536)
            if not buf:
                break
    except BlockingIOError:
        pass
    except OSError:
        pass
    look()
look()
seen = sorted(set(exposed))
with open(out, "w") as handle:
    span = "" if first_exposed is None else (" span:%s" % ("open" if span_ms is None else "%.1f" % span_ms))
    handle.write("observed:%d exposed:%d final:%s%s%s\n" % (observed, len(exposed), final, span, (" " + " ".join(seen)) if seen else ""))
