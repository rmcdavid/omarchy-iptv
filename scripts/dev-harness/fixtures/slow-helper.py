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
    OMARCHY_IPTV_SLOW_IGNORE_TERM=1
                             D-SINK-19 round 14, R24g (F-HARNESS-24): a
                             slowed verb IGNORES SIGTERM, so only the
                             service's KILL can end it -- the half of the
                             start-up watchdog nothing observed. SIG_IGN
                             survives exec, so the real helper ignores it too.
    OMARCHY_IPTV_SLOW_AT=inside
                             R24d (D-SRC-24): instead of sleeping BEFORE the
                             real helper runs, run it in this process and
                             make its first lstat() of a state.json sleep --
                             a hung filesystem, made deterministic -- so the
                             real verb's own code is what is held, its own
                             SIGALRM self-deadline included. The helper is
                             loaded from omarchy-iptv.real with bytecode off
                             (the tree is the scenario's scratch copy).

The verb is read the way the helper's own argv is shaped: `player seek ...`
is "seek", `status --socket ...` is "status".

CLAUDE.md rule 2: argv only, no shell. Rule 8: ASCII only. Rule 3: python 3
standard library only -- this file is dev tooling and never ships, but it
runs the shipped helper and must not need anything the helper does not.
"""

import sys


def shield_environment():
    """Non-dumpable, as this file's FIRST act, exactly as the real helper
    does for the same reason (D-SINK-9).

    This fixture sits between the service and the helper and INHERITS the
    helper's environment, OMARCHY_IPTV_URL and its credentials with it. The
    real helper shields itself within about 30 ms of exec since it became a
    stub and its parts (D-REL-7; about 105 ms as one file); this one sleeps
    for seconds on purpose, so leaving it dumpable would turn a measured
    window of milliseconds into a measured four-second one and re-open the
    sink the helper closed -- in a fixture a scenario runs on the owner's own
    machine. The review of the F-RWD-18 round found it. prctl(PR_SET_DUMPABLE,
    0) is what the helper calls; it is in ctypes, which is why the import
    below is the only one above this line."""
    try:
        import ctypes
        return ctypes.CDLL(None, use_errno=True).prctl(4, 0, 0, 0, 0) == 0
    except Exception:
        return False


SHIELDED = shield_environment()

import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REAL = os.path.join(HERE, "omarchy-iptv.real")


def verb_of(argv):
    """The verb this invocation names, or "" when it names none.

    `state --state-dir <dir> init` is "state init" (D-SINK-19 R5:
    key-scenario.sh stretches the service's start-up `state init` so the
    window between the parked state save and the entry mirror is seconds
    wide and a shell can be stopped inside it): the sub-verb after the
    `--flag value` pairs, joined to "state" with a space so the plain
    "state" of an older OMARCHY_IPTV_SLOW_VERBS list still names nothing
    that this one does not."""
    if not argv:
        return ""
    if argv[0] == "player" and len(argv) > 1:
        return argv[1]
    if argv[0] == "state":
        i = 1
        while i < len(argv):
            if argv[i].startswith("--"):
                i += 2
                continue
            return "state " + argv[i]
        return "state"
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
    if not SHIELDED:
        # Refuse rather than sleep for seconds holding a credentialed
        # environment in a readable /proc entry.
        sys.stderr.write("slow-helper: could not go non-dumpable, refusing to hold the environment\n")
        return 2
    held = verb_of(argv) in slow and ms > 0
    if held and os.environ.get("OMARCHY_IPTV_SLOW_IGNORE_TERM", "") == "1":
        import signal
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if held and os.environ.get("OMARCHY_IPTV_SLOW_AT", "") == "inside":
        return run_inside(argv, ms)
    if held:
        time.sleep(ms / 1000.0)
    # Same interpreter, same argv, no shell: the reply the service reads is
    # the real helper's own.
    os.execv(sys.executable, [sys.executable, REAL] + argv)
    return 0   # unreachable unless execv fails, which raises


def run_inside(argv, ms):
    """The real helper's main() in THIS process, with its first lstat() of a
    path ending in state.json held for `ms` (OMARCHY_IPTV_SLOW_AT=inside)."""
    import importlib.machinery
    import importlib.util
    sys.dont_write_bytecode = True
    loader = importlib.machinery.SourceFileLoader("omarchy_iptv_real", REAL)
    spec = importlib.util.spec_from_loader("omarchy_iptv_real", loader)
    helper = importlib.util.module_from_spec(spec)
    loader.exec_module(helper)
    real_lstat = os.lstat
    state = {"held": False}

    def held_lstat(path, *args, **kwargs):
        if not state["held"] and str(path).endswith("state.json"):
            state["held"] = True
            time.sleep(ms / 1000.0)
        return real_lstat(path, *args, **kwargs)

    os.lstat = held_lstat
    return helper.main(argv)


if __name__ == "__main__":
    sys.exit(main())
