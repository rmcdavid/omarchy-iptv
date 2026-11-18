"""scripts/dev-harness/fixtures/helper_argv.py -- read a process's command
line as a run of the plugin's helper (F-HARNESS-87).

Since D-SINK-50 the service starts the helper as `python3 -I <helper> <verb>
...` (Model.helperArgv), so argv[1] is `-I` and the helper's path is argv[2].
A scanner that reads argv[1] as the path finds no helper at all, and a
scanner that cannot see a helper answers "none" whatever is running.
key-scenario.sh carries this reader as HELPER_ARGV_PY (F-HARNESS-86); the two
sweepers beside this file import it, and tests/test_harness_sweepers.py holds
the two copies to the same answers.

helper_argv(argv) -> (the script's real path, the arguments after it), or
None: after the interpreter it skips the interpreter's own flags (`-I`,
`-B`, ...; `-X` and `-W` with their value) to the script. A `-c` or `-m` run
names no script and answers None, so a scanner's own `python3 -c` never
matches itself. A tree from before D-SINK-50 has no flag and reads the same.
"""

import os


def helper_argv(argv):
    i = 1
    while i < len(argv) and argv[i].startswith("-") and argv[i] != "-":
        if argv[i] in ("-c", "-m"):
            return None
        i += 2 if argv[i] in ("-X", "-W") else 1
    if i >= len(argv):
        return None
    return os.path.realpath(argv[i]), argv[i + 1:]


def read_argv(pid):
    try:
        with open("/proc/%s/cmdline" % pid, "rb") as fh:
            raw = fh.read().split(b"\0")
    except OSError:
        return None
    return [a.decode("utf-8", "replace") for a in raw if a]
