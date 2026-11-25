#!/usr/bin/env python3
"""scripts/dev-harness/spikes/codebehind-reload/watch.py -- git's writes, timed.

  watch.py DIR OUT READY

Runs `inotifywait -m -r` over DIR (the decoy plugins folder) with the events
the host's own watcher asks for (create, close_write, delete, move) and writes
one line per event to OUT: the wall clock in milliseconds (the clock the rig's
Date.now() reads), the event names and the path. READY is created once the
watches are established. Ends its inotifywait (its own child, by the pid it
started) on SIGTERM, and exits.
"""
import os
import signal
import subprocess
import sys
import time


def main(argv):
    if len(argv) != 4:
        raise SystemExit("usage: watch.py DIR OUT READY")
    directory, out, ready = argv[1], argv[2], argv[3]
    child = subprocess.Popen(["inotifywait", "-m", "-r", "-e", "close_write,create,delete,move",
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
