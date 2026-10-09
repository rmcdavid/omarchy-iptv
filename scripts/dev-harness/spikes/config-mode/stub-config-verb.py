#!/usr/bin/env python3
"""D-SINK-18 grading instrument: a reference 'config shield' plus its defects.

WHAT THIS IS, AND WHAT IT IS NOT. It is NOT a shim and it is not the fix. The
helper verb this stands for lives in bin/omarchy-iptv and belongs to another
lane; this lane may not write that file and the verb did not exist when
config-mode-scenario.sh was written. CLAUDE.md rule 11 still applies: a test
nobody has seen fail is decoration, and when the code is new the rule says to
mutate the shipping function and show the red.

So this file is the MUTATION TARGET. It implements the lead's ruling as
faithfully as this lane can read it, and STUB_MUTATION turns exactly one
decision off at a time. config-mode-scenario.sh --helper <this file> then
grades the scenario: each mutation must redden the one check that guards that
decision and leave the others green. The scenario's REAL run points at
bin/omarchy-iptv and this file takes no part in it. Nothing in the gate runs
it, and no acceptance claim rests on it -- it grades the questions, never the
answers.

The ruling it implements (docs/QA-RESULTS.md, "Fourth maintainer finding", and
the lead's measurements of 2026-10-09):
  * the path is COMPUTED from the environment, never taken as an argument;
  * group and other must both be clear, because a 0640 config is as exposed to
    the owning group as a 0644 one is to the world;
  * a container that cannot be made private is a REFUSAL, so the caller never
    persists the URL -- the plugin does not write the credential and hope;
  * a container that is already private is left ALONE, because a needless
    write into a user's own config is its own small harm;
  * nothing it prints carries a URL (CLAUDE.md rule 5).

Python 3 stdlib only, ASCII only, argv only, no sudo -- the same constraints
the real helper is held to, so a decision that cannot be made under them is
not proposed here either.
"""

import os
import stat
import sys

MUTATION = os.environ.get("STUB_MUTATION", "none")

# The one path this verb is allowed to touch, relative to XDG_CONFIG_HOME.
REL = os.path.join("omarchy", "shell.json")

# Everyone but the owner. The mask is 077 and not 004: see the ruling above.
EXPOSED = stat.S_IRWXG | stat.S_IRWXO


def fail(message):
    """Refuse, on stderr, with a status the caller must not read as consent."""
    sys.stderr.write("omarchy-iptv: %s\n" % message)
    return 3


def config_path():
    """The file this verb may act on, computed and never accepted."""
    base = os.environ.get("XDG_CONFIG_HOME") or ""
    if not base:
        home = os.environ.get("HOME") or ""
        if not home:
            return None
        base = os.path.join(home, ".config")
    if not os.path.isabs(base):
        return None
    return os.path.join(base, REL)


def shield(argv):
    # The path is computed, so an argument offering one is a refusal rather
    # than an override. MUTATION any-path is the lane that honours it.
    if argv:
        if MUTATION == "any-path":
            path = argv[0]
        else:
            return fail("config shield takes no arguments; the path is computed")
    else:
        path = config_path()
    if not path:
        return fail("cannot compute the host config path")

    # accept-unshieldable is the defect R1 and R2 guard: it reports success
    # over a container it has not shielded and cannot shield. It has to bypass
    # BOTH guards -- this one and the chmod failure below -- because lstat does
    # not resolve a symlink, so a self-referential shell.json is refused here,
    # at ISREG, and never reaches the chmod at all. An earlier mutation touched
    # only the chmod branch and so was unreachable: it reddened nothing, which
    # is how this comment came to exist.
    lenient = MUTATION == "accept-unshieldable"
    try:
        before = os.lstat(path)
    except OSError as exc:
        if lenient:
            sys.stdout.write("ok\n")
            return 0
        return fail("host config is not a file we can make private (%s)" % exc.errno)
    if not stat.S_ISREG(before.st_mode) and not lenient:
        # A symlink, a directory or a socket here is not a container this verb
        # can reason about, and following one would let whatever planted it
        # choose the file we chmod.
        return fail("host config is not a regular file")

    mode = stat.S_IMODE(before.st_mode)
    # The mask, and its two halves are mutated APART. world-only reads a 0640
    # file as private, group-only reads a 0604 one as private. That is the
    # qa_transcript_start lesson, whose first version was graded only against
    # 1777 /tmp -- a mode that trips every candidate mask, so the mask itself
    # was never under test.
    if MUTATION == "world-only":
        mask = stat.S_IRWXO
    elif MUTATION == "group-only":
        mask = stat.S_IRWXG
    else:
        mask = EXPOSED

    if not (mode & mask):
        if MUTATION == "unconditional-chmod":
            # Already private, and this chmods anyway. Content and mtime do
            # not move; ctime does, every time, measured 2026-10-09. A check
            # watching only content and mtime cannot see this.
            os.chmod(path, mode)
        sys.stdout.write("already private\n")
        return 0

    try:
        if MUTATION != "no-chmod":
            # no-chmod is the plainest defect there is: it reports success
            # without changing anything, which is what a verb wired up but
            # never observed looks like from the caller's side.
            os.chmod(path, mode & ~EXPOSED)
    except OSError as exc:
        if lenient:
            # It could not make the container private and answers 0 anyway, so
            # the caller goes on to persist the credential into a file group or
            # other can read. This is the ENABLING half of the ordering defect;
            # the ordering itself is Service.qml's, not this verb's.
            sys.stdout.write("ok\n")
            return 0
        return fail("cannot make the host config private (%s)" % exc.errno)

    # The verb reads the mode back rather than trusting its own chmod, which is
    # the only way it can honestly answer "this container is private now".
    # no-chmod skips the read-back too: a defect that does nothing AND checks
    # nothing is what the caller actually sees, and leaving the read-back in
    # would make the stub catch its own mutation instead of the scenario.
    if MUTATION != "no-chmod":
        after = stat.S_IMODE(os.stat(path).st_mode)
        if after & EXPOSED:
            return fail("host config is still readable by others after chmod")
    if MUTATION == "leak-url":
        # Rule 5's sink, one line long: the verb has no business holding a URL
        # at all, and this prints the one the environment carries.
        sys.stdout.write("shielded for %s\n" % os.environ.get("OMARCHY_IPTV_URL", ""))
    else:
        sys.stdout.write("shielded\n")
    return 0


def main(argv):
    if len(argv) >= 2 and argv[0] == "config" and argv[1] == "shield":
        return shield(argv[2:])
    sys.stderr.write("omarchy-iptv: unknown verb\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
