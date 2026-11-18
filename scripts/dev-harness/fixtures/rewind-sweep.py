#!/usr/bin/env python3
"""scripts/dev-harness/fixtures/rewind-sweep.py -- count the helper's `player
seek` runs while a key is held (rewind-scenario.sh R13-R15).

Samples /proc every 20 ms for SECONDS and records every process whose
script resolves to HELPER (exact path, the argv-scenario.sh lesson: a
suffix match once read another lane's processes) and whose arguments carry
`seek`. The script is read past the interpreter's flags (helper_argv.py,
F-HARNESS-87): the service runs the helper as `python3 -I <helper> ...`, and
reading argv[1] as the path counted no run at all. One record per pid: the verb, first and last sample, so the run's
lifetime is bounded above by (last - first + 20 ms).

    rewind-sweep.py SECONDS HELPER OUT.json

OUT.json: {"runs": N, "lifetimesMs": [...], "verbs": {...}}. Nothing here
reads an environment, and the command line it reads carries no URL: the
seek verb's argv is a socket path and a number.
"""

import json
import os
import sys
import time

sys.dont_write_bytecode = True

from helper_argv import helper_argv, read_argv  # noqa: E402  (beside this file; no bytecode written)


def main(argv):
    seconds, helper, out_path = float(argv[0]), os.path.realpath(argv[1]), argv[2]
    seen = {}
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        now = round((time.monotonic() - t0) * 1000)
        for d in os.listdir("/proc"):
            if not d.isdigit():
                continue
            argv = read_argv(d)
            try:
                run = helper_argv(argv) if argv else None
            except Exception:
                run = None
            if run is None or run[0] != helper or "seek" not in run[1]:
                continue
            verb = " ".join(run[1][:3])
            rec = seen.get(d)
            if rec is None:
                seen[d] = {"pid": int(d), "verb": verb, "first": now, "last": now, "samples": 1}
            else:
                rec["last"] = now
                rec["samples"] += 1
        time.sleep(0.02)
    runs = list(seen.values())
    verbs = {}
    for r in runs:
        verbs[r["verb"]] = verbs.get(r["verb"], 0) + 1
    with open(out_path, "w") as fh:
        json.dump({"runs": len(runs), "lifetimesMs": [r["last"] - r["first"] + 20 for r in runs],
                   "verbs": verbs, "pids": [r["pid"] for r in runs]}, fh)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
