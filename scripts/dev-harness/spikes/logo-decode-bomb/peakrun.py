#!/usr/bin/env python3
"""peakrun.py -- run a child and report its peak resident set.

    python3 peakrun.py <argv...>

Prints the child's combined stdout/stderr, then ONE line:

    PEAKRUN rc=<n> peak_rss_kb=<n> wall_ms=<n>

rc is the child's exit status (negative is the signal that ended it);
peak_rss_kb is ru_maxrss over the waited-for children, which with util-linux
`prlimit` in front of the command is the command itself, because prlimit
sets the limit on itself and execs the command in place rather than forking
(measured 2026-10-11: the pid the command runs under is the pid this process
spawned; `env` execs in place as well).

The limit wraps ONLY the child, never this reporter: a refused allocation in
the reporter would end the measurement rather than report it. So the shape
is always

    python3 peakrun.py prlimit --as=2500000000 -- \\
        env QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qml probe.qml

RLIMIT_AS rather than a service-manager memory scope, for the two reasons
run.sh gives: the marketplace capability scan reads the scope tool's name as
service management anywhere in a tracked file, and under the rlimit an
over-bound decode is a clean allocator refusal (Qt reports Image.Error, rc 1)
rather than a kill.

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
