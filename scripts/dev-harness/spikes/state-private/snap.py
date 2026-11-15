"""scripts/dev-harness/spikes/state-private/snap.py -- one snapshot for
measure.sh (D-SINK-103), run from gdb while the probe shell is STOPPED at a
syscall: every entry of the folders named, its mode, its size, and whether it
holds the marker (the new credential). Prints `SNAP <when> <mode> <size>
<holds> <name>` per regular file, names relative to the work directory, so a
reader of the transcript sees what another account could have read at that
instant: a file holding the marker whose mode grants group or other.

  snap.py WHEN MARKER WORKDIR FOLDER...
"""
import os
import stat
import sys

when, marker, work = sys.argv[1], sys.argv[2].encode(), sys.argv[3]
for folder in sys.argv[4:]:
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        continue
    for name in names:
        path = os.path.join(folder, name)
        try:
            st = os.lstat(path)
        except OSError:
            continue
        if stat.S_ISLNK(st.st_mode):
            print("SNAP %s link %s -> %s" % (when, os.path.relpath(path, work), os.path.relpath(os.path.realpath(path), work)))
            continue
        if not stat.S_ISREG(st.st_mode):
            continue
        try:
            with open(path, "rb") as handle:
                holds = marker in handle.read()
        except OSError:
            holds = False
        print("SNAP %s %03o %d %d %s" % (when, stat.S_IMODE(st.st_mode), st.st_size, 1 if holds else 0, os.path.relpath(path, work)))
sys.stdout.flush()
