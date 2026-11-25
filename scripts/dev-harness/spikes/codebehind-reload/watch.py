#!/usr/bin/env python3
"""scripts/dev-harness/spikes/codebehind-reload/watch.py -- git's writes, or
the shell's reads, timed.

  watch.py DIR OUT READY [writes|opens]

Runs `inotifywait -m -r` over DIR (the decoy plugins folder) and writes one
line per event to OUT: the wall clock in milliseconds (the clock the rig's
Date.now() and run.sh's `date +%s%3N` read), the event names and the path.
`writes` (the default) asks for the events the host's own watcher asks for
(create, close_write, delete, move): git's writes. `opens` asks for open and
close_nowrite: every read of a file, which is how the rig times the shell's
own reads at a cold start (a file git creates is opened too, so an open that
follows a CREATE of the same path is git's, and analyze.py drops it; but git
also re-reads files it checks before it overwrites them and after, and
inotify names no process, so an open inside a merge's span may be git's: the
rig's verdicts rest on the marks and the cache files, never on an open).
READY is created once the watches are established. Ends its inotifywait (its
own child, by the pid it started) on SIGTERM, and exits.
"""
import os
import signal
import subprocess
import sys
import time

EVENTS = {"writes": "close_write,create,delete,move", "opens": "open,close_nowrite"}


def main(argv):
    if len(argv) not in (4, 5) or (len(argv) == 5 and argv[4] not in EVENTS):
        raise SystemExit("usage: watch.py DIR OUT READY [writes|opens]")
    directory, out, ready = argv[1], argv[2], argv[3]
    events = EVENTS[argv[4] if len(argv) == 5 else "writes"]
    child = subprocess.Popen(["inotifywait", "-m", "-r", "-e", events,
                              "--format", "%e|%w%f", directory],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def stop(signum, frame):
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    # inotifywait says "Watches established." on stderr once it is listening.
    while True:
        line = child.stderr.readline()
        if not line:
            raise SystemExit("watch.py: inotifywait ended before it was listening")
        if b"Watches established" in line:
            break
    fd = os.open(ready, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    with open(out, "a", encoding="utf-8") as fh:
        for raw in child.stdout:
            fh.write("%.3f %s\n" % (time.time() * 1000.0, raw.decode("utf-8", "replace").rstrip("\n")))
            fh.flush()


if __name__ == "__main__":
    main(sys.argv)
