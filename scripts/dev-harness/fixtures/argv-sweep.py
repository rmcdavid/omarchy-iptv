#!/usr/bin/env python3
r"""scripts/dev-harness/fixtures/argv-sweep.py -- argv-scenario.sh's sweeper:
every 50 ms, every run of the helper, its command line and its environment.

    ARGV_NEEDLE=<credential> ARGV_HELPER=<the helper's real path> \
        argv-sweep.py SECONDS OUT.jsonl

One JSON line per (pid, verb), rewritten each tick. A run of the helper is a
process whose SCRIPT, read past the interpreter's flags (helper_argv.py), is
ARGV_HELPER by exact real path.
"""

import json
import os
import sys
import time

sys.dont_write_bytecode = True

from helper_argv import helper_argv, read_argv  # noqa: E402  (beside this file; no bytecode written)

# The needle arrives in THIS process's environment, not its argv: a sweeper
# that carried the credential on its own command line would be the leak it
# is looking for.
needle = os.environ["ARGV_NEEDLE"].encode(); deadline = time.monotonic() + float(sys.argv[1]); out = open(sys.argv[2], "a")
# Every helper is re-sampled on every tick, not recorded once: the first
# draft recorded each pid the first time it was seen, which for a process
# that shields itself before its imports is ALWAYS the start-up window
# before the shield, and reported the shield as absent. The record for
# a pid is rewritten each tick with first-seen / first-refused times, so the
# window between them is MEASURED and the final state is what is asserted.
seen = {}
t0 = time.monotonic()
while time.monotonic() < deadline:
    for d in os.listdir("/proc"):
        if not d.isdigit(): continue
        argv = read_argv(d)
        try: run = helper_argv(argv) if argv else None
        except Exception: run = None
        # The helper's script past the interpreter's flags (F-HARNESS-87):
        # the service runs `python3 -I <helper> <verb>`, and reading argv[1]
        # as the path saw no helper, so every positive control went red and
        # the leak check passed on nothing.
        if run is None or run[0] != os.environ["ARGV_HELPER"] or not run[1]: continue
        verb = run[1][0]
        key = (d, verb)
        now = round((time.monotonic() - t0) * 1000)
        refused = False
        try:
            with open("/proc/%s/environ" % d, "rb") as f: env = f.read()
        except PermissionError: env = b""; refused = True
        except OSError:
            # Gone between the cmdline read and this one: its last real
            # sample stands. Rewriting it as "not refused" was the first
            # draft's bug in the other direction (last sample wins, with no
            # distinction between readable and vanished).
            continue
        carriers = sorted(set(e.split(b"=", 1)[0].decode("ascii", "replace") for e in env.split(b"\0") if needle in e))
        prev = seen.get(key)
        rec = {"pid": int(d), "verb": verb,
               "cmdline_has_needle": (prev or {}).get("cmdline_has_needle", False) or needle in "\0".join(argv).encode("utf-8", "replace"),
               "environ_has_needle": (prev or {}).get("environ_has_needle", False) or needle in env,
               "environ_refused": refused,
               "environ_carriers": sorted(set((prev or {}).get("environ_carriers", []) + carriers)),
               "env_var_present": (prev or {}).get("env_var_present", False) or b"OMARCHY_IPTV_URL=" in env,
               "first_seen_ms": (prev or {}).get("first_seen_ms", now),
               "first_refused_ms": (prev or {}).get("first_refused_ms") if prev and prev.get("first_refused_ms") is not None else (now if refused else None),
               "samples": (prev or {}).get("samples", 0) + 1}
        seen[key] = rec
    out.seek(0); out.truncate()
    for r in seen.values(): out.write(json.dumps(r) + "\n")
    out.flush()
    time.sleep(0.05)
