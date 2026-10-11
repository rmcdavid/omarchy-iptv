#!/usr/bin/env python3
"""peakrun.py -- run a child and report its peak resident set.

    python3 peakrun.py <argv...>

Prints the child's combined stdout/stderr, then ONE line:

    PEAKRUN rc=<n> peak_rss_kb=<n> wall_ms=<n>

rc is the child's exit status (negative is the signal that ended it: -9 is
the memory cap's SIGKILL); peak_rss_kb is ru_maxrss over the waited-for
children, which with `systemd-run --scope` in front of the command is the
command itself, because --scope execs it in place rather than forking (the
child's parent pid is this process; measured 2026-10-11).

The cap wraps ONLY the child, never this reporter: an OOM kill that took the
reporter with it would take the measurement too. So the shape is always

    python3 peakrun.py systemd-run --user --scope -q -p MemoryMax=1500M \\
        -p MemorySwapMax=0 -- env QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qml probe.qml

The child is given PEAKRUN_TIMEOUT seconds (default 60) before this reporter
kills it and reports rc=-15: the probe's own 20 s Timer is the normal bound,
and this is the bound on a child that never reaches QML at all (rule 3: every
wait has a deadline and says it gave up). Python 3 standard library only.
"""
import os
import resource
import subprocess
import sys
import time

limit = float(os.environ.get("PEAKRUN_TIMEOUT", "60"))
t0 = time.monotonic()
try:
    proc = subprocess.run(sys.argv[1:], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=limit)
    out, rc = proc.stdout, proc.returncode
except subprocess.TimeoutExpired as expired:
    out = (expired.stdout or b"") + ("\nPEAKRUN gave up after %.0f s and killed the child\n" % limit).encode()
    rc = -15
wall = time.monotonic() - t0
usage = resource.getrusage(resource.RUSAGE_CHILDREN)
sys.stdout.write(out.decode("utf-8", "replace"))
print("PEAKRUN rc=%d peak_rss_kb=%d wall_ms=%d" % (rc, usage.ru_maxrss, wall * 1000))
