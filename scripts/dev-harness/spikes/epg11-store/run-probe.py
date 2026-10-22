#!/usr/bin/env python3
"""run-probe.py -- one V4 probe run under prlimit, its RSS read from outside.

    python3 run-probe.py <mode> <epg-now.json> [--tree DIR] [--reps N]
                         [--now-sec S] [--hold-ms MS] [--as BYTES]

<mode> is one of the probe's (epg11-probe.qml): text, parse, store, time,
tick. <epg-now.json> is a file the SHIPPING HELPER wrote (README). --tree is
the directory whose Model.mjs and model/ are measured; the default is this
repository's root, four levels up, and a `git archive <ref> | tar -x` export
of another commit is how a baseline is measured. The tree is never written
into: Model.mjs, model/ and the probe are COPIED into a temporary directory
with the probe's argument file beside them, and that directory is removed
when the run ends.

The qml process ALONE runs under `prlimit --as=<BYTES>` (util-linux; prlimit
execs the command in place, so the pid this script spawned is the probe's,
measured on 2026-10-11 for the logo spike and again here). RSS:
/proc/<pid>/status is sampled every 50 ms from outside the limit; `steady`
is the median VmRSS of the samples taken after the probe printed PROBE HOLD
(the state built and held), `peak` the largest VmRSS at any sample, and
ru_maxrss of the child is printed beside them. One RESULT line, then exit 0
on the probe's exit 0, 1 on any other, 77 when the machine cannot run it
(python3 is here, so: no prlimit, no qml, or the rlimit refused). The pid is
killed by THIS script on the 150 s deadline, which it reports (rule 3: a
bound, and it says so; a pid it recorded, never a pattern).

Stdlib only. ASCII only. Not shipped (nothing under spikes/ is on the
release allowlist).
"""
import json
import os
import resource
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
QML = "/usr/lib/qt6/bin/qml"
MODES = ("text", "parse", "store", "time", "tick")


def usage(msg=""):
    if msg:
        print("run-probe.py: " + msg, file=sys.stderr)
    print(__doc__.strip().split("\n", 1)[0], file=sys.stderr)
    print("    python3 run-probe.py <mode> <epg-now.json> [--tree DIR] [--reps N] [--now-sec S] [--hold-ms MS] [--as BYTES]", file=sys.stderr)
    sys.exit(2)


def parse_args(argv):
    opts = {"tree": ROOT, "reps": None, "now_sec": 0, "hold_ms": 2500, "as": 4000000000}
    positional = []
    k = 0
    while k < len(argv):
        a = argv[k]
        if a in ("--tree", "--reps", "--now-sec", "--hold-ms", "--as"):
            if k + 1 >= len(argv):
                usage(a + " needs a value")
            v = argv[k + 1]
            key = a[2:].replace("-", "_")
            opts[key] = os.path.abspath(v) if a == "--tree" else int(v)
            k += 2
            continue
        if a.startswith("--"):
            usage("unknown option " + a)
        positional.append(a)
        k += 1
    if len(positional) != 2:
        usage("a mode and a file are required")
    mode, path = positional
    if mode not in MODES:
        usage("mode must be one of " + ", ".join(MODES))
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        usage("no such file: " + path)
    if opts["reps"] is None:
        opts["reps"] = 2000 if mode == "tick" else 10
    return mode, path, opts


def can_run(limit):
    if shutil.which("prlimit") is None:
        return "no prlimit (util-linux)"
    if not os.access(QML, os.X_OK):
        return "no " + QML + " (qt6-declarative)"
    try:
        subprocess.run(["prlimit", "--as=%d" % limit, "--", "true"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return "prlimit --as=%d refused" % limit
    return ""


def stage(tree, mode, path, opts):
    """Copy the tree's model and the probe into a fresh temporary directory."""
    agg = os.path.join(tree, "Model.mjs")
    parts = os.path.join(tree, "model")
    if not os.path.isfile(agg) or not os.path.isdir(parts):
        usage("--tree " + tree + " has no Model.mjs and model/")
    work = tempfile.mkdtemp(prefix="epg11-probe-")
    shutil.copy(agg, os.path.join(work, "Model.mjs"))
    shutil.copytree(parts, os.path.join(work, "model"))
    shutil.copy(os.path.join(HERE, "epg11-probe.qml"), os.path.join(work, "epg11-probe.qml"))
    with open(os.path.join(work, "probe-args.json"), "w") as fh:
        json.dump({"mode": mode, "file": path, "reps": opts["reps"], "nowSec": opts["now_sec"], "holdMs": opts["hold_ms"]}, fh)
    return work


def main():
    mode, path, opts = parse_args(sys.argv[1:])
    why_not = can_run(opts["as"])
    if why_not:
        print("run-probe.py: cannot run here: " + why_not)
        sys.exit(77)
    work = stage(opts["tree"], mode, path, opts)
    try:
        cmd = ["prlimit", "--as=%d" % opts["as"], "--", "env", "QT_QPA_PLATFORM=offscreen", "QML_XHR_ALLOW_FILE_READ=1",
               "QT_FORCE_STDERR_LOGGING=1", "QT_LOGGING_RULES=qt.qml.*=false",
               QML, os.path.join(work, "epg11-probe.qml")]
        t0 = time.monotonic()
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        pid = proc.pid
        samples, held, out_lines = [], [], []
        holding = False
        gave_up = False
        os.set_blocking(proc.stdout.fileno(), False)
        buf = ""
        deadline = t0 + 150
        while True:
            try:
                chunk = proc.stdout.read()
            except (BlockingIOError, TypeError):
                chunk = None
            if chunk:
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    out_lines.append(line)
                    if "PROBE HOLD" in line:
                        holding = True
            try:
                with open("/proc/%d/status" % pid) as fh:
                    for line in fh:
                        if line.startswith("VmRSS:"):
                            kb = int(line.split()[1])
                            samples.append(kb)
                            if holding:
                                held.append(kb)
            except OSError:
                pass
            if proc.poll() is not None:
                break
            if time.monotonic() > deadline:
                proc.kill()
                proc.wait()
                gave_up = True
                out_lines.append("RUNNER gave up after 150 s and killed pid %d" % pid)
                break
            time.sleep(0.05)
        rest = proc.stdout.read() or ""
        out_lines.extend((buf + rest).splitlines())
        wall = (time.monotonic() - t0) * 1000
        usage_ = resource.getrusage(resource.RUSAGE_CHILDREN)
        for line in out_lines:
            print("  " + line)
        print("RESULT tree=%s mode=%s file=%s rc=%s steady_rss_kb=%s peak_sample_kb=%s ru_maxrss_kb=%d held_samples=%d wall_ms=%.0f" % (
            os.path.basename(opts["tree"].rstrip("/")), mode, os.path.basename(path), proc.returncode,
            int(statistics.median(held)) if held else "none", max(samples) if samples else "none",
            usage_.ru_maxrss, len(held), wall))
        sys.exit(0 if proc.returncode == 0 and not gave_up else 1)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
