#!/usr/bin/env python3
"""scripts/dev-harness/spikes/barconfig-window/snap.py -- every state.json
that lands, read off the file.

  snap.py DIR OUT READY PLAYLIST

Runs `inotifywait -m` over DIR (the decoy HOME's ~/.local/state/omarchy-iptv)
and, at each close_write or moved_to of state.json (the service's FileView
writes atomically: a temporary renamed over the path), reads the file as it
is then and appends one JSON line to OUT: the wall clock in ms when the
event was read (the clock the rig's and the service's log lines read), the
event, and the readout -- recents count, the migration marker, the sources
(count, and for each whether its url is PLAYLIST, the fixture's file; no url
is written), activeKey set or not, the file's mode -- or the parse error.
A file replaced again before it is read is read as the later one; the
order holds, a burst can fold. READY is created once the watch is
established. Ends its inotifywait (its own child, by the pid it started) on
SIGTERM. Python 3 standard library only.
"""
import json
import os
import signal
import subprocess
import sys
import time


def readout(path, playlist):
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError as error:
        return {"error": "unreadable: %s" % error.strerror}
    try:
        st = json.loads(text)
    except ValueError:
        return {"error": "unparsed", "bytes": len(text)}
    if not isinstance(st, dict):
        return {"error": "not an object"}
    sources = st.get("sources") if isinstance(st.get("sources"), list) else []
    return {"recents": len(st.get("recents") or []), "marker": st.get("entryMigrated") is True,
            "sources": len(sources), "sourceIsPlaylist": [isinstance(s, dict) and s.get("url") == playlist for s in sources],
            "activeKeySet": bool(st.get("activeKey")), "mode": "%o" % (os.stat(path).st_mode & 0o777)}


def main(argv):
    if len(argv) != 5:
        raise SystemExit("usage: snap.py DIR OUT READY PLAYLIST")
    directory, out, ready, playlist = argv[1:]
    child = subprocess.Popen(["inotifywait", "-m", "-e", "close_write,moved_to", "--format", "%e|%f", directory],
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
    while True:
        line = child.stderr.readline()
        if not line:
            raise SystemExit("snap.py: inotifywait ended before it was listening")
        if b"Watches established" in line:
            break
    fd = os.open(ready, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    with open(out, "a", encoding="utf-8") as fh:
        for raw in child.stdout:
            event, _, name = raw.decode("utf-8", "replace").rstrip("\n").partition("|")
            if name != "state.json":
                continue
            rec = {"t": round(time.time() * 1000.0, 1), "event": event}
            rec.update(readout(os.path.join(directory, name), playlist))
            fh.write(json.dumps(rec) + "\n")
            fh.flush()


if __name__ == "__main__":
    main(sys.argv)
