#!/usr/bin/env python3
"""scripts/dev-harness/fixtures/disk-gone-after-init.py -- the real helper,
except that the state directory loses `w` the moment `state init` has run.

WHY IT EXISTS (D-SINK-19 round 11, R21). key-scenario.sh's F and H observe a
state write that FAILS while a bar-entry URL is a migration input: R13 says
the entry keeps the URL (the only copy) and R16 that the logo toggle does
too. Under R21 a URL on the entry is an input only until the migration's own
write -- the start's -- has LANDED, so the write has to fail from the very
start. Taking `w` off the directory before the start does not do it: the
helper's `state init` runs ensure_private_dir, which chmods the state
directory back to 0700 (the plugin's directories are private, CLAUDE.md 6),
and the start's write then lands (measured on lane-key-m1's first live run:
F1 `failed:false landed:true`). Taking it off under the running shell, as
round 10's F did, is too late: the marker has landed by then and the URL is
refused. This takes it off between the two: the real `state init` runs to
completion as a child, then the directory named by `--state-dir` becomes
0500, and the helper exits with the real verb's status -- before the service
issues the parked save that its exit handler issues.

HOW IT IS USED. key-scenario.sh stages a copy of the tree under test with
`bin/omarchy-iptv` renamed `bin/omarchy-iptv.real` and this file in its place
(the slow-helper.py staging), and points the harness at it with
OMARCHY_IPTV_PLUGIN_ROOT for the one start it needs. Every other verb is
exec'd as it is. The directory is the scenario's own scratch; the scenario
gives it back its mode before the next start and in cleanup().

CLAUDE.md rule 2: argv only, no shell. Rule 8: ASCII only. Rule 3: stdlib.
"""

import os
import subprocess
import sys

REAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "omarchy-iptv.real")


def main() -> int:
    args = sys.argv[1:]
    if args[:1] == ["state"] and "init" in args and "--state-dir" in args:
        rc = subprocess.call([sys.executable, REAL] + args)
        directory = args[args.index("--state-dir") + 1]
        os.chmod(directory, 0o500)
        return rc
    os.execv(sys.executable, [sys.executable, REAL] + args)
    return 127


if __name__ == "__main__":
    sys.exit(main())
