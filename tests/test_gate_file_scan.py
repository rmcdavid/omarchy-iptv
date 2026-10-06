"""F-GATE-1: the gate's byte scans must see a file that EXISTS, not a file
that has been staged.

The two scans in scripts/check.sh -- the ASCII check (CLAUDE.md rule 8) and
the control-byte check -- were driven from `git ls-files`, which lists the
INDEX. So a brand-new file in the working tree was not scanned at all, and the
printed count ("162 files scanned") read as coverage while silently excluding
exactly the population a lane is adding. The helper lane hit it on itself: it
ran the gate green, staged, and its first commit was red for a literal e-acute
in a new test file. The check that was meant to stop that byte ran BEFORE the
`git add` that made the byte visible to it. CLAUDE.md rule 14's shape exactly.

Two rules shape this file.

Rule 12 -- do not reimplement the thing under test. These cases do not build a
file list in python and diff it. They invoke the REAL scan functions, through
`scripts/check.sh --byte-scan ascii|control <root>`, a door that runs one scan
against a root given on the command line and nothing else. If the shipping
function stops seeing untracked files, these go red.

Rule 11 -- the test must be seen failing. The named mutation is MUT-1: in
`gate_load_corpus`, replace
    git -C "$ROOT" ls-files --cached --others --exclude-standard -z -- "$@"
with the pre-fix
    git -C "$ROOT" ls-files -z -- "$@"
and the four cases that turn on an unstaged file go red while the rest stay
green. Both counts are reported in the lane's write-up. Drive a mutated copy
with GATE_UNDER_TEST=<path to the mutated check.sh>.

Nothing here touches the real repository. Every case builds a throwaway git
repository under tempfile.mkdtemp() and removes it in tearDown. ASCII only in
this file (rule 8): the offending bytes are written as b"\\xc3\\xa9" and
b"\\x00", never as literals, which is also the only way a test for this gate
could itself pass the gate.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
GATE = os.environ.get("GATE_UNDER_TEST", os.path.join(REPO, "scripts", "check.sh"))

# A literal e-acute in UTF-8: the byte that made the helper lane's first commit
# red after this gate had called the same file green.
E_ACUTE = b"\xc3\xa9"

# The two fixtures the ASCII step exempts BY NAME. Every throwaway tree carries
# them, because the step asserts its own exclusions still name a real path.
EXEMPT_PLAYER = "tests/fixtures/qa-player/qa-player.m3u"
EXEMPT_HARNESS = "scripts/dev-harness/fixtures/harness.m3u.in"

# Deterministic git: ignore whatever global or system config this machine has,
# so a developer's core.excludesFile cannot change what the scan sees.
GIT_ENV = dict(
    os.environ,
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
    GIT_AUTHOR_NAME="gate test",
    GIT_AUTHOR_EMAIL="gate@example.invalid",
    GIT_COMMITTER_NAME="gate test",
    GIT_COMMITTER_EMAIL="gate@example.invalid",
)


class GateScanCase(unittest.TestCase):
    """A throwaway git repository, plus the two scan doors."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="gate-file-scan-")
        self.git("init", "-q")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    # -- building the tree -------------------------------------------------

    def git(self, *args):
        proc = subprocess.run(
            ("git", "-C", self.root) + args,
            env=GIT_ENV, capture_output=True, text=True,
        )
        self.assertEqual(
            proc.returncode, 0,
            "git %s failed: %s%s" % (" ".join(args), proc.stdout, proc.stderr),
        )
        return proc.stdout

    def write(self, rel, data):
        """Write bytes (or str) at a repo-relative path. Does NOT stage it."""
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if isinstance(data, str):
            data = data.encode("ascii")
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def stage(self, rel, data):
        self.write(rel, data)
        self.git("add", "--", rel)

    def seed(self, gitignore=None):
        """The minimum tree both scans need: a committed file in each scan's
        pathspec, and the two by-name ASCII exemptions, which the step now
        asserts still exist."""
        self.stage("bin/omarchy-iptv", "#!/usr/bin/env python3\n")
        self.stage("tests/fixtures/sample.json", '{"ok": true}\n')
        self.stage(EXEMPT_PLAYER, "#EXTM3U\n")
        self.stage(EXEMPT_HARNESS, "#EXTM3U\n")
        if gitignore is not None:
            self.stage(".gitignore", gitignore)
        self.git("commit", "-q", "-m", "seed")

    # -- running the real scans -------------------------------------------

    def scan(self, kind):
        proc = subprocess.run(
            ("bash", GATE, "--byte-scan", kind, self.root),
            env=GIT_ENV, capture_output=True, text=True,
        )
        return proc.returncode, proc.stdout + proc.stderr

    def counts(self, output):
        """('162 files scanned, 0 untracked') -> (162, 0)."""
        for token in output.split("("):
            if "files scanned" in token:
                head = token.split(")")[0]
                scanned, untracked = head.split(",")
                return (int(scanned.split()[0]), int(untracked.split()[0]))
        self.fail("no count in scan output: %r" % output)


class TestFindingPremise(GateScanCase):
    """F-GATE-1 stated as a measurement of git, not of our scan.

    This is the gap itself: the instrument the gate used cannot see the file.
    It is pinned here so that nobody 'simplifies' the corpus command back on
    the belief that ls-files lists the working tree.
    """

    def test_plain_ls_files_cannot_see_an_unstaged_file(self):
        self.seed()
        self.write("tests/test_brand_new.py", b"x = '" + E_ACUTE + b"'\n")
        old = self.git("ls-files", "-z", "--", "*.py").split("\0")
        new = self.git("ls-files", "--cached", "--others", "--exclude-standard",
                       "-z", "--", "*.py").split("\0")
        self.assertNotIn("tests/test_brand_new.py", old,
                         "git ls-files started listing untracked files; "
                         "F-GATE-1's premise has changed")
        self.assertIn("tests/test_brand_new.py", new)

    def test_the_two_sets_do_not_overlap(self):
        """--cached and --others are disjoint, so the printed count cannot
        double-count a path. The count is the only coverage signal the gate
        gives, and a count that over-reports is the same lie as one that
        under-reports."""
        self.seed()
        self.write("tests/test_brand_new.py", "x = 1\n")
        listing = [p for p in self.git(
            "ls-files", "--cached", "--others", "--exclude-standard",
            "-z", "--", "*.py", "*.json", "bin/*").split("\0") if p]
        self.assertEqual(sorted(listing), sorted(set(listing)))


class TestUnstagedViolationsAreCaught(GateScanCase):
    """The four cases MUT-1 turns red."""

    def test_ascii_scan_is_red_for_an_unstaged_non_ascii_py(self):
        self.seed()
        self.write("tests/test_brand_new.py", b"NAME = 'caf" + E_ACUTE + b"'\n")
        rc, out = self.scan("ascii")
        self.assertEqual(rc, 1, out)
        self.assertIn("non-ASCII bytes in tests/test_brand_new.py", out)
        self.assertIn("FAIL ascii check", out)

    def test_ascii_finding_says_the_file_is_untracked(self):
        """A contributor seeing this for the first time needs the diagnosis in
        the line, not in the script: the file is not in the index, and if it is
        scratch the declaration belongs in .gitignore."""
        self.seed()
        self.write("scripts/dev-harness/probe.sh", b"# caf" + E_ACUTE + b"\n")
        rc, out = self.scan("ascii")
        self.assertEqual(rc, 1, out)
        self.assertIn("untracked", out)
        self.assertIn(".gitignore", out)

    def test_control_scan_is_red_for_an_unstaged_nul(self):
        self.seed()
        self.write("tests/scratch_probe.py", b"SEP = '" + b"\x00" + b"'\n")
        rc, out = self.scan("control")
        self.assertEqual(rc, 1, out)
        self.assertIn("raw control bytes in tests/scratch_probe.py", out)
        self.assertIn("FAIL control-byte check", out)

    def test_untracked_share_of_the_count_is_reported(self):
        """'4 files scanned' used to mean 'of the ones in the index'. The
        number now says how many of them were not."""
        self.seed()
        self.write("tests/helper_probe.py", "x = 1\n")
        rc, out = self.scan("ascii")
        self.assertEqual(rc, 0, out)
        scanned, untracked = self.counts(out)
        self.assertEqual(untracked, 1, out)
        # bin/omarchy-iptv and tests/fixtures/sample.json, plus the probe. The
        # two by-name exemptions are in the corpus and deliberately not counted.
        self.assertEqual(scanned, 3, out)


class TestStagedViolationsStillCaught(GateScanCase):
    """Nothing that used to be scanned stopped being scanned."""

    def test_ascii_scan_is_red_for_a_committed_non_ascii_py(self):
        self.seed()
        self.stage("tests/test_old.py", b"NAME = 'caf" + E_ACUTE + b"'\n")
        self.git("commit", "-q", "-m", "add it")
        rc, out = self.scan("ascii")
        self.assertEqual(rc, 1, out)
        self.assertIn("non-ASCII bytes in tests/test_old.py", out)
        self.assertNotIn("untracked -- in your tree", out)

    def test_control_scan_is_red_for_a_committed_nul(self):
        self.seed()
        self.stage("tests/old_probe.py", b"SEP = '" + b"\x00" + b"'\n")
        self.git("commit", "-q", "-m", "add it")
        rc, out = self.scan("control")
        self.assertEqual(rc, 1, out)
        self.assertIn("raw control bytes in tests/old_probe.py", out)

    def test_a_tracked_file_deleted_from_the_tree_is_skipped(self):
        """`--cached` still lists a path whose file is gone. The `[[ -f ]]`
        guard drops it instead of grepping a hole, and the count drops with
        it."""
        self.seed()
        rc, before = self.scan("ascii")
        self.assertEqual(rc, 0, before)
        os.unlink(os.path.join(self.root, "tests/fixtures/sample.json"))
        rc, after = self.scan("ascii")
        self.assertEqual(rc, 0, after)
        self.assertIn("ok   ascii check", after)
        self.assertEqual(self.counts(after)[0], self.counts(before)[0] - 1)


class TestIgnoredFilesStayOut(GateScanCase):
    """--exclude-standard is load-bearing, not tidiness."""

    def test_an_ignored_scratch_tree_is_not_scanned(self):
        self.seed(gitignore="__pycache__/\n*.pyc\n/scratch/\n")
        self.write("scratch/notes.py", b"NAME = 'caf" + E_ACUTE + b"'\n")
        rc, out = self.scan("ascii")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("scratch/notes.py", out)
        self.assertEqual(self.counts(out)[1], 0, out)

    def test_a_pycache_tree_does_not_turn_the_control_scan_red(self):
        """Dropping --exclude-standard reads __pycache__ byte-compiled output,
        which is control bytes end to end -- the gate would be red for
        everyone who has ever run the python suite."""
        self.seed(gitignore="__pycache__/\n*.pyc\n")
        self.write("bin/__pycache__/omarchy_iptv.py", b"\x00\x01\x02\x03")
        rc, out = self.scan("control")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("__pycache__", out)


class TestDeliberateExclusionsStillWork(GateScanCase):
    """The by-name non-ASCII exemptions, and the join that holds them."""

    def test_the_named_fixture_trees_stay_exempt(self):
        self.seed()
        self.stage("tests/fixtures/qa-nonascii/qa-unicode.m3u",
                   b"#EXTINF:-1,caf" + E_ACUTE + b"\n")
        self.stage("tests/fixtures/qa-sources/nonascii/paste-rtl.txt",
                   b"caf" + E_ACUTE + b"\n")
        self.git("commit", "-q", "-m", "fixtures")
        rc, out = self.scan("ascii")
        self.assertEqual(rc, 0, out)

    def test_the_two_named_fixture_files_stay_exempt(self):
        self.seed()
        self.write(EXEMPT_PLAYER, b"#EXTINF:-1,caf" + E_ACUTE + b"\n")
        self.write(EXEMPT_HARNESS, b"#EXTINF:-1,caf" + E_ACUTE + b"\n")
        rc, out = self.scan("ascii")
        self.assertEqual(rc, 0, out)

    def test_an_unstaged_file_in_an_exempt_tree_is_still_exempt(self):
        """Widening the corpus must not change what the exemption MEANS. A new
        fixture in a tree named for carrying non-ASCII is the case the ruling
        of 2026-09-14 covers, staged or not."""
        self.seed()
        self.write("tests/fixtures/qa-nonascii/qa-new.m3u",
                   b"#EXTINF:-1,caf" + E_ACUTE + b"\n")
        rc, out = self.scan("ascii")
        self.assertEqual(rc, 0, out)

    def test_an_exclusion_naming_a_vanished_path_is_red(self):
        """Rule 13 inside this very step: the exclusion list and the tree are
        joined by a NAME. A line that names a fixture somebody moved reads like
        a considered exemption while guarding nothing, so the join is asserted
        rather than trusted."""
        self.seed()
        self.git("rm", "-q", "--", EXEMPT_HARNESS)
        rc, out = self.scan("ascii")
        self.assertEqual(rc, 1, out)
        self.assertIn("ascii exclusion names a path that does not exist", out)
        self.assertIn(EXEMPT_HARNESS, out)

    def test_control_scan_still_skips_compressed_and_image_bytes(self):
        self.seed()
        self.write("scripts/dev-harness/fixtures/qa-epg.xml.gz", b"\x1f\x8b\x08\x00\x00")
        rc, out = self.scan("control")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("qa-epg.xml.gz", out)


class TestScanCannotPassVacuously(GateScanCase):
    """A scan that exits 0 having read nothing is the failure the whole floor
    discipline in check.sh exists for."""

    def test_an_empty_repository_is_red_for_both_scans(self):
        for kind in ("ascii", "control"):
            rc, out = self.scan(kind)
            self.assertEqual(rc, 1, out)
            self.assertIn("scanned no files at all", out)

    def test_the_door_refuses_a_bad_invocation(self):
        for args in (("--byte-scan", "ascii"),
                     ("--byte-scan", "sideways", self.root),
                     ("--byte-scan", "ascii", os.path.join(self.root, "nope"))):
            proc = subprocess.run(("bash", GATE) + args,
                                  env=GIT_ENV, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2,
                             "%s -> %s %s" % (args, proc.stdout, proc.stderr))

    def test_the_door_runs_only_the_one_scan(self):
        """It must stay above the first `step`, or driving it would run the
        whole gate against a throwaway tree."""
        self.seed()
        rc, out = self.scan("ascii")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("omarchy plugin validate", out)
        self.assertNotIn("qmllint", out)
        self.assertEqual(out.count("ascii check"), 1, out)


if __name__ == "__main__":
    unittest.main()
