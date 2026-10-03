#!/usr/bin/env python3
"""scripts/dev-harness/fixtures/rewind-sweep.py -- count the helper's `player
seek` runs while a key is held (rewind-scenario.sh R13-R15).

Samples /proc every 20 ms for SECONDS and records every process whose
argv[1] resolves to HELPER (exact path, the argv-scenario.sh lesson: a
suffix match once read another lane's processes) and whose argv carries
`seek`. One record per pid: the verb, first and last sample, so the run's
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


def main(argv):
    seconds, helper, out_path = float(argv[0]), os.path.realpath(argv[1]), argv[2]
    seen = {}
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        now = round((time.monotonic() - t0) * 1000)
        for d in os.listdir("/proc"):
            if not d.isdigit():
                continue
            try:
                with open("/proc/%s/cmdline" % d, "rb") as fh:
                    parts = fh.read().split(b"\0")
            except OSError:
                continue
            if len(parts) < 3:
                continue
            try:
                if os.path.realpath(parts[1].decode("utf-8", "replace")) != helper:
                    continue
            except Exception:
                continue
            verb = b" ".join(parts[2:5]).decode("ascii", "replace")
            if b"seek" not in b"\0".join(parts[2:]):
                continue
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
