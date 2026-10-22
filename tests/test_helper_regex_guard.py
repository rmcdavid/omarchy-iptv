"""Prove scripts/check-helper-regex.py catches what it claims to catch.

The guard (R30g, D-EPG-8) holds every regex the helper compiles to a
reviewed verdict on its cost. Rule 11: each case below feeds the REAL guard,
run as a subprocess the way scripts/check.sh runs it, a copy of the helper's
parts with one thing changed, and reads its exit status and report. Rule 12:
nothing here re-implements the scan.

The case that matters most is (f): the helper as it stood on lane-bounds-int,
whose quadratic qualifier pattern is the finding, must be refused by name.
"""
import io
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
GUARD = ROOT / "scripts" / "check-helper-regex.py"
PARTS = ROOT / "bin" / "helper"
INT_BASE = "17a2407"


def run_guard(helper_dir=None):
    argv = [sys.executable, str(GUARD)]
    if helper_dir is not None:
        argv += ["--helper-dir", str(helper_dir)]
    done = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    return done.returncode, done.stdout + done.stderr


class HelperRegexGuardTest(unittest.TestCase):

    def copy_parts(self):
        work = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, work, True)
        target = work / "helper"
        shutil.copytree(PARTS, target, ignore=shutil.ignore_patterns("__pycache__"))
        return target

    def edit(self, part, old, new):
        text = part.read_text(encoding="utf-8")
        self.assertEqual(text.count(old), 1, old)
        part.write_text(text.replace(old, new), encoding="utf-8")

    def test_a_the_shipping_helper_passes_and_counts_every_call(self):
        code, report = run_guard()
        self.assertEqual(code, 0, report)
        summary = [line for line in report.splitlines() if " regex call(s) in " in line]
        self.assertEqual(len(summary), 1, report)
        self.assertGreaterEqual(int(summary[0].split(": ")[1].split()[0]), 34, report)
        self.assertIn("0 problem(s)", summary[0])

    def test_b_a_new_pattern_is_refused_until_reviewed(self):
        parts = self.copy_parts()
        self.edit(parts / "04-epg.py", "def clean_title(text: str | None) -> str:\n",
                  "_NEW = re.compile(r\"(a+)+$\")\n\n\ndef clean_title(text: str | None) -> str:\n")
        code, report = run_guard(parts)
        self.assertEqual(code, 1, report)
        self.assertIn("unreviewed regex '(a+)+$'", report)
        self.assertIn("04-epg.py", report)

    def test_c_a_changed_pattern_is_a_new_one(self):
        parts = self.copy_parts()
        self.edit(parts / "01-core.py", '_CONTROL_WS = re.compile(r"[\\s\\x00-\\x1f\\x7f]+")',
                  '_CONTROL_WS = re.compile(r"(?:[\\s\\x00-\\x1f\\x7f]+)+")')
        code, report = run_guard(parts)
        self.assertEqual(code, 1, report)
        self.assertIn("unreviewed regex", report)
        # And the reviewed form it replaced is reported as gone.
        self.assertIn("which no helper part compiles any more", report)

    def test_d_a_call_through_another_name_is_refused(self):
        parts = self.copy_parts()
        self.edit(parts / "04-epg.py", "def clean_title(text: str | None) -> str:\n",
                  "from re import sub as _sub\n\n\ndef clean_title(text: str | None) -> str:\n")
        code, report = run_guard(parts)
        self.assertEqual(code, 1, report)
        self.assertIn("`from re import` hides a regex call", report)
        parts = self.copy_parts()
        self.edit(parts / "04-epg.py", "def clean_title(text: str | None) -> str:\n",
                  "import re as _re\n\n\ndef clean_title(text: str | None) -> str:\n")
        code, report = run_guard(parts)
        self.assertEqual(code, 1, report)
        self.assertIn("`import re as _re` hides a regex call", report)

    def test_e_an_open_verdict_is_reported_and_does_not_fail(self):
        code, report = run_guard()
        self.assertEqual(code, 0, report)
        self.assertIn("OPEN on provider text", report)

    def test_f_the_helper_on_lane_bounds_int_is_refused_by_name(self):
        if shutil.which("git") is None:
            self.skipTest("git is needed to read the baseline helper")
        probe = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", INT_BASE + "^{commit}"],
                               capture_output=True, timeout=30)
        if probe.returncode != 0:
            self.skipTest("the baseline commit %s is not in this checkout" % INT_BASE)
        work = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, work, True)
        archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", INT_BASE, "bin/helper"],
                                 capture_output=True, timeout=60)
        self.assertEqual(archive.returncode, 0, archive.stderr)
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            tar.extractall(work, filter="data")
        code, report = run_guard(os.path.join(work, "bin", "helper"))
        self.assertEqual(code, 1, report)
        self.assertIn("unreviewed regex '\\\\s*\\\\([^()]*\\\\)\\\\s*$'", report)
        self.assertIn("unreviewed regex '^\\\\[[0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*", report)

    def test_g_an_empty_directory_is_not_a_pass(self):
        work = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, work, True)
        code, report = run_guard(work)
        self.assertEqual(code, 1, report)
        # Refused for being empty, not merely for the reviewed patterns it
        # no longer finds (which would also fail, for a different reason).
        self.assertIn("no helper parts under", report)


if __name__ == "__main__":
    unittest.main()
