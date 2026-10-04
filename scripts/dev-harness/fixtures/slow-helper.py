#!/usr/bin/env python3
"""scripts/dev-harness/fixtures/slow-helper.py -- a helper that is SLOW on
purpose, for one verb or a few, and otherwise the real thing.

WHY IT EXISTS (F-RWD-18). Ruling D10 says a seek run does not count as busy
for the health tick's three-strikes restart. The decision is only visible
WHILE the control slot is held, and a healthy `player seek` run holds it for
about 220 ms, so an observation of it is a coincidence rather than a
measurement -- which is how the old R14 came to pass whether or not the
exemption existed. This wrapper stretches the run to seconds, deterministic
and under the service's own 8 s control watchdog, so a health tick really
does land on a running seek and a sample really does land inside the window.

HOW IT IS USED. rewind-scenario.sh's R16 copies the tree under test into a
scratch directory, renames `bin/omarchy-iptv` to `bin/omarchy-iptv.real`,
drops this file in its place, and points the harness at that tree with
OMARCHY_IPTV_PLUGIN_ROOT. The service spawns its helper as
`python3 <root>/bin/omarchy-iptv ...` (Service.qml runControl), so the
stand-in has to be python; a shell wrapper would never be read.

It is NOT a stub: after the sleep it execs the real helper with the same
argv, so every reply the service parses is the real helper's. The only
difference a verb sees is when it starts.

    OMARCHY_IPTV_SLOW_MS     how long to sleep before exec (default 4000)
    OMARCHY_IPTV_SLOW_VERBS  comma separated verbs to sleep for
                             (default "seek,status"); anything else is
                             exec'd immediately

The verb is read the way the helper's own argv is shaped: `player seek ...`
is "seek", `status --socket ...` is "status".

CLAUDE.md rule 2: argv only, no shell. Rule 8: ASCII only. Rule 3: python 3
standard library only -- this file is dev tooling and never ships, but it
runs the shipped helper and must not need anything the helper does not.
"""

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REAL = os.path.join(HERE, "omarchy-iptv.real")


def verb_of(argv):
    """The verb this invocation names, or "" when it names none."""
    if not argv:
        return ""
    if argv[0] == "player" and len(argv) > 1:
        return argv[1]
    return argv[0]


def main():
    argv = sys.argv[1:]
    slow = [v.strip() for v in os.environ.get("OMARCHY_IPTV_SLOW_VERBS", "seek,status").split(",")]
    try:
        ms = int(os.environ.get("OMARCHY_IPTV_SLOW_MS", "4000"))
    except ValueError:
        ms = 4000
    if not os.path.exists(REAL):
        sys.stderr.write("slow-helper: no omarchy-iptv.real beside me\n")
        return 2
    if verb_of(argv) in slow and ms > 0:
        time.sleep(ms / 1000.0)
    # Same interpreter, same argv, no shell: the reply the service reads is
    # the real helper's own.
    os.execv(sys.executable, [sys.executable, REAL] + argv)
    return 0   # unreachable unless execv fails, which raises


if __name__ == "__main__":
    sys.exit(main())
