"""scripts/dev-harness/spikes/state-private/cost.py -- what one helper `state`
run costs, for measure.sh's `cost` mode (D-SINK-103: `state private` runs
before every write of state.json, and `state mode` after every landed one).

  cost.py N PRIVATE_ARGV_JSON MODE_ARGV_JSON

Runs the two argvs measure.sh built through the model
(Model.statePrivateArgv, Model.stateModeArgv) and a bare `python3 -I -c
pass`, interleaved, N times each, one at a time, and reads each child's
wall time (CLOCK_MONOTONIC around spawn and reap) and CPU time (its own
rusage from wait4, user plus system). Prints one line per run, then per
kind its min, median and max, and the load average before and after.
Prints no path: the argvs name a scratch folder.
"""
import json
import os
import statistics
import subprocess
import sys
import time

n = int(sys.argv[1])
kinds = [("private", json.loads(sys.argv[2])), ("mode", json.loads(sys.argv[3])),
         ("bare", [sys.executable, "-I", "-c", "pass"])]


def load():
    with open("/proc/loadavg", encoding="ascii") as handle:
        return " ".join(handle.read().split()[:3])


def once(argv):
    start = time.monotonic_ns()
    child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = child.stdout.read(), child.stderr.read()
    _pid, status, usage = os.wait4(child.pid, 0)
    wall = (time.monotonic_ns() - start) / 1e6
    child.returncode = os.waitstatus_to_exitcode(status)
    reply = out.decode("utf-8", "replace").strip().splitlines()
    word = ""
    if reply:
        try:
            o = json.loads(reply[-1])
            word = str(o.get("file", "")) + ("/" + str(o["folder"]) if "folder" in o else "")
        except ValueError:
            word = "unparsed"
    return wall, (usage.ru_utime + usage.ru_stime) * 1000.0, child.returncode, word, len(err)


print("# load before %s" % load())
seen = {kind: [] for kind, _ in kinds}
for i in range(n):
    for kind, argv in kinds:
        wall, cpu, rc, word, errlen = once(argv)
        seen[kind].append((wall, cpu))
        print("   RUN %-7s %2d rc=%d wall=%.1f cpu=%.1f%s%s" % (kind, i + 1, rc, wall, cpu,
              (" reply=" + word) if word else "", (" stderr=%dB" % errlen) if errlen else ""))
for kind, _ in kinds:
    walls = [w for w, _ in seen[kind]]
    cpus = [c for _, c in seen[kind]]
    print("   COST %-7s n=%d wall %.1f-%.1f median %.1f ms, cpu %.1f-%.1f median %.1f ms"
          % (kind, len(walls), min(walls), max(walls), statistics.median(walls),
             min(cpus), max(cpus), statistics.median(cpus)))
print("# load after %s" % load())
