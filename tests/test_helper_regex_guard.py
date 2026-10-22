"""Prove scripts/check-helper-regex.py catches what it claims to catch.

The guard (R30g, D-EPG-8) holds every regex the helper compiles to a
reviewed verdict on its cost. Rule 11: each case below feeds the REAL guard,
run as a subprocess the way scripts/check.sh runs it, a copy of the helper's
parts with one thing changed, and reads its exit status and report. Rule 12:
nothing here re-implements the scan.

The case that matters most is (f): the helper as it stood on lane-bounds-int,
whose quadratic qualifier pattern is the finding, must be refused by name.

Round 3 (D-EPG-12, ruling R32d): the table alone certified
`\\[\\s*not\\s*24\\s*[-/]?\\s*7\\s*\\]` linear for a false reason, so the guard
now grades that shape by STRUCTURE too. (h) runs the real guard over a copy
of the parts carrying the old pattern and reads the super-linear line; (i)
calls the grader on named patterns it must flag and must clear; (j) a
flags argument the guard cannot read is refused rather than walked under
the wrong flags.
"""
import importlib.util
import io
import os
import pathlib
import re
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

# The `[not 24/7]` alternative of _EPG_NAME_NOISE before and after D-EPG-12,
# as the source spells it.
NEW_NOISE_LINE = 'r"|\\[\\s*not\\s*24\\s*(?:[-/]\\s*)?7\\s*\\]"'
OLD_NOISE_LINE = 'r"|\\[\\s*not\\s*24\\s*[-/]?\\s*7\\s*\\]"'


def load_guard():
    """The guard as a module, so (i) calls the shipping grader (rule 12)."""
    spec = importlib.util.spec_from_file_location("check_helper_regex", GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    def test_h_the_old_noise_pattern_is_graded_super_linear_by_structure(self):
        """D-EPG-12, rule 11: the guard against a copy of the old pattern.
        The unreviewed line would be there anyway (the text changed); the
        line that matters is the one the table could not write."""
        parts = self.copy_parts()
        self.edit(parts / "01-core.py", NEW_NOISE_LINE, OLD_NOISE_LINE)
        code, report = run_guard(parts)
        self.assertEqual(code, 1, report)
        lines = [line for line in report.splitlines() if "super-linear shape in" in line]
        self.assertEqual(len(lines), 1, report)
        self.assertIn("01-core.py", lines[0])
        self.assertIn("not\\\\s*24\\\\s*[-/]?\\\\s*7", lines[0])
        self.assertIn("\\s{0,} and \\s{0,}", lines[0])
        self.assertIn("D-EPG-12", lines[0])
        # And the shipping pattern draws no such line.
        code, report = run_guard()
        self.assertEqual(code, 0, report)
        self.assertNotIn("super-linear shape", report)

    def test_i_the_grader_flags_the_shape_and_clears_its_neighbours(self):
        guard = load_guard()
        flagged = [
            (OLD_NOISE_LINE[3:-1].lstrip("|"), re.IGNORECASE),
            (r"^\[[0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*(?:%25[A-Za-z0-9._~\-]+)?\]$", 0),   # the old _IPV6_LITERAL
            (r"\s*\s*", 0), (r"\s*x?\s*", 0), (r"\s*(?:x)?\s*", 0), (r"\s*(?=x)\s*", 0),
            (r"[a-]*-[a-]*", 0), (r".*\n.*", re.DOTALL), (r"[a-z]*A*", re.IGNORECASE),
            (r"(\s*)(\s*)", 0), (r"\s*?\s*", 0), (r"\s+\s+", 0), (r"\s*[^a]*", 0), (r"\d*\w*", 0),
            (r"(?i)[a-z]*A*", 0),
        ]
        for pattern, flags in flagged:
            self.assertTrue(guard.super_linear_pairs(pattern, flags), pattern)
        cleared = [
            (NEW_NOISE_LINE[3:-1].lstrip("|"), re.IGNORECASE),
            (r"^\[(?=[0-9A-Fa-f.]*:)[0-9A-Fa-f:.]*(?:%25[A-Za-z0-9._~\-]+)?\]$", 0),   # the new one
            (r"\s*not\s*", 0), (r"a*b*", 0), (r"[ab]*:[bc]*", 0), (r".*\n.*", 0), (r"[a-z]*A*", 0),
            (r"\s*x\s*", 0), (r"\s*(?:x)\s*", 0), (r"\s{0,8}\s*", 0), (r"[-/]?\s*7", 0),
            # A different super-linear shape, read by a person and recorded
            # in the table (D-EPG-8's, F-SINK-11's): not this grader's.
            (r"\s*\([^()]*\)\s*$", 0), (r"(a+)+$", 0),
        ]
        for pattern, flags in cleared:
            self.assertEqual(guard.super_linear_pairs(pattern, flags), [], pattern)

    def test_j_flags_the_guard_cannot_read_are_refused(self):
        parts = self.copy_parts()
        self.edit(parts / "04-epg.py", "def clean_title(text: str | None) -> str:\n",
                  "_F = 0\n_NEW = re.compile(r\"[0-9]+\", _F)\n\n\ndef clean_title(text: str | None) -> str:\n")
        code, report = run_guard(parts)
        self.assertEqual(code, 1, report)
        self.assertIn("flags this guard cannot read", report)
        # Named flags are read, in both positions a call can carry them.
        guard = load_guard()
        import ast
        call = ast.parse('re.sub(r"a", "", s, 0, re.I | re.S)').body[0].value
        self.assertEqual(guard.call_flags(call), int(re.I | re.S))
        call = ast.parse('re.compile(r"a", flags=re.IGNORECASE)').body[0].value
        self.assertEqual(guard.call_flags(call), int(re.IGNORECASE))
        call = ast.parse('re.search(r"a", s)').body[0].value
        self.assertEqual(guard.call_flags(call), 0)


if __name__ == "__main__":
    unittest.main()
