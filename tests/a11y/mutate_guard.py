"""CLAUDE.md rule 11, applied to the guard itself.

The fidelity guard is new code, so there is no "before" to run its suite
against. The rule's other half applies: break one decision in the shipping
function deliberately and show the suite goes red.

Each mutation below disables exactly one layer of the guard, or one faculty of
the scanner, in a THROWAWAY copy of tests/a11y/. Nothing in the repo is
touched. The table records which cases each mutation is expected to kill; a
mutation that kills nothing means that layer is decoration and the run says
so.

    python3 tests/a11y/mutate_guard.py

Stdlib only, ASCII only.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

# (label, file, old, new)
MUTATIONS = [
    ("baseline (guard intact)", None, None, None),
    ("L1 off: let the transform edit accessibility markup",
     "fidelity.py",
     '    touched = [("-", n, t) for n, t in removed if "Accessible." in t] + \\\n'
     '              [("+", n, t) for n, t in added if "Accessible." in t]',
     '    touched = []'),
    ("L2 off: stop attributing changed lines to declared rules",
     "fidelity.py",
     "    if residual_removed or residual_added:",
     "    if False:"),
    ("L2 off: stop noticing a rule that did not fire",
     "fidelity.py",
     "        if missing:",
     "        if False:"),
    ("L3 off: stop comparing the accessibility projection",
     "fidelity.py",
     "    if src_proj != gen_proj:",
     "    if False:"),
    ("L4 off: let an added element declare accessibility",
     "fidelity.py",
     "        if offenders:",
     "        if False:"),
    ("L5 off: stop naming what the transform cannot carry",
     "fidelity.py",
     "    if on_window:",
     "    if False:"),
    ("L6 off: stop comparing the verbatim copies",
     "fidelity.py",
     "    if digest(source_path) != digest(copy_path):",
     "    if False:"),
    ("L7 off: stop naming ungraded surfaces",
     "fidelity.py",
     "        if declared:",
     "        if False:"),
    ("scanner: forget the sibling bindings (the text: sink)",
     "qmlscan.py",
     '        for index, (name, value, line) in enumerate(frame.bindings):',
     '        for index, (name, value, line) in [(i, frame.bindings[i])\n'
     '                                           for i in frame.accessible]:'),
    ("scanner: forget the attachment point",
     "qmlscan.py",
     "        path = _path(frame)",
     '        path = "ELEMENT"'),
    ("scanner: forget the declared value",
     "qmlscan.py",
     '    return ["%s | %s | %s = %s" % (r["path"], r["kind"], r["prop"], r["value"])\n'
     "            for r in records]",
     '    return ["%s | %s | %s" % (r["path"], r["kind"], r["prop"])\n'
     "            for r in records]"),
]


def run_case(label, filename, old, new):
    work = tempfile.mkdtemp(prefix="a11y-mutate-")
    try:
        for name in ("fidelity.py", "qmlscan.py", "test_fidelity.py"):
            shutil.copy(os.path.join(HERE, name), os.path.join(work, name))
        if filename:
            path = os.path.join(work, filename)
            with open(path) as handle:
                text = handle.read()
            if text.count(old) != 1:
                print("  SKIPPED: the anchor occurs %d time(s) in %s"
                      % (text.count(old), filename))
                return None
            with open(path, "w") as handle:
                handle.write(text.replace(old, new, 1))
        env = dict(os.environ)
        env["A11Y_REPO"] = REPO
        env.pop("A11Y_GENERATED", None)
        proc = subprocess.run(
            [sys.executable, os.path.join(work, "test_fidelity.py")],
            env=env, capture_output=True, text=True, timeout=600)
        tail = proc.stderr.strip().split("\n")
        ran = 0
        for line in tail:
            match = re.match(r"^Ran (\d+) test", line)
            if match:
                ran = int(match.group(1))
        failed = len(re.findall(r"^(FAIL|ERROR): ", proc.stderr, re.M))
        names = sorted(set(re.findall(r"^(?:FAIL|ERROR): (\w+)", proc.stderr,
                                      re.M)))
        print("  ran %d, %d red%s" % (ran, failed,
                                      ("  [" + ", ".join(names) + "]")
                                      if names else ""))
        return failed
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    print("mutating the guard, not the guide. Repo: %s\n" % REPO)
    results = []
    for label, filename, old, new in MUTATIONS:
        print("=== %s" % label)
        results.append((label, run_case(label, filename, old, new)))
    print("")
    baseline = results[0][1]
    if baseline != 0:
        print("BASELINE IS RED (%s failures): every result below is unreadable"
              % baseline)
        return 1
    survivors = [label for label, failed in results[1:] if failed == 0]
    if survivors:
        print("%d mutation(s) SURVIVED -- those layers assert nothing:" %
              len(survivors))
        for label in survivors:
            print("  " + label)
        return 1
    print("baseline green, all %d mutation(s) killed" % (len(results) - 1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
