"""Prove scripts/check-sr-register.py catches what it claims to catch (F-M3-20).

CLAUDE.md rule 11: a check never seen red is decoration, so every case here
builds a throwaway git repository with a register that PASSES, breaks one
decision, and asserts the real checker's main() turns red and names the
site. Rule 12: nothing here re-implements the checker's regexes; each case
runs the shipping script.

Seen red on the tree as well: on a9d20f9 the checker names SR27, SR29 and
SR34 as cited nowhere outside their own rows (3 problems over 40 rows); the
three citations were added where each ruling is implemented, in
docs/QA-SOURCES.md, and the tree reads 0 problems.

The ids below are composed ("SR" + "9") where they must NOT resolve, because
this file is tracked and the checker reads every tracked file: a literal
unresolvable id written here would be the checker's own red.
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = os.path.join(ROOT, 'scripts', 'check-sr-register.py')
_s = importlib.util.spec_from_file_location('check_sr_register', _spec)
checker = importlib.util.module_from_spec(_s)
_s.loader.exec_module(checker)

REGISTER = (
    '# Sources architecture\n\n'
    '| Id | Topic | Ruling |\n'
    '|---|---|---|\n'
    '| SR1 | Identifiers | the state file keeps these names |\n'
    '| SR2 | Actions | addSource and friends; SR1 names them |\n'
    '| SR3 | Mask | the token replaces userinfo |\n'
)
CITING = (
    '# QA\n\n'
    'SRC-01 covers SR1 and SR3; the harness fake is SR2 territory.\n'
)


class RegisterCase(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='sr-register-')
        self.addCleanup(shutil.rmtree, self.dir, True)
        os.makedirs(os.path.join(self.dir, 'docs'))
        subprocess.run(['git', 'init', '-q', self.dir], check=True)
        self.write('docs/ARCHITECTURE-SOURCES.md', REGISTER)
        self.write('docs/QA-SOURCES.md', CITING)

    def write(self, rel, text, binary=False):
        path = os.path.join(self.dir, rel)
        if binary:
            with open(path, 'wb') as fh:
                fh.write(text)
        else:
            with io.open(path, 'w', encoding='utf-8') as fh:
                fh.write(text)
        subprocess.run(['git', '-C', self.dir, 'add', '--', rel], check=True)

    def run_checker(self):
        out = io.StringIO()
        real = sys.stdout
        sys.stdout = out
        try:
            rc = checker.main(['--root', self.dir])
        finally:
            sys.stdout = real
        return rc, out.getvalue()

    def test_clean_register_is_green_and_counts(self):
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        self.assertIn('sr register: 3 rows, 4 citations in 2 files, 0 overturned, 0 binary skipped, 0 problem(s)', out)

    def test_removed_row_is_red_and_named(self):
        # The row SR3 goes; the citation in QA-SOURCES is left behind.
        self.write('docs/ARCHITECTURE-SOURCES.md', REGISTER.replace(
            '| SR3 | Mask | the token replaces userinfo |\n', ''))
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('docs/QA-SOURCES.md:3: cites SR3, which has no row in docs/ARCHITECTURE-SOURCES.md', out)
        self.assertIn('1 problem(s)', out)

    def test_citation_of_an_unwritten_id_is_red(self):
        self.write('docs/UX-SOURCES.md', '# UX\n\nThe form follows ' + 'SR' + '9' + ' here.\n')
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('docs/UX-SOURCES.md:3: cites ' + 'SR' + '9' + ', which has no row', out)

    def test_row_cited_nowhere_is_red(self):
        self.write('docs/QA-SOURCES.md', CITING.replace('SR3', 'the mask rule'))
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('docs/ARCHITECTURE-SOURCES.md:7: SR3 is cited nowhere outside its own row', out)

    def test_a_rows_own_id_does_not_count_as_its_citation(self):
        # SR3 cited only by itself: "SR3 stands" on its own line.
        self.write('docs/ARCHITECTURE-SOURCES.md', REGISTER.replace(
            '| SR3 | Mask | the token replaces userinfo |',
            '| SR3 | Mask | the token replaces userinfo; SR3 stands |'))
        self.write('docs/QA-SOURCES.md', CITING.replace('SR3', 'the mask rule'))
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('SR3 is cited nowhere outside its own row', out)

    def test_duplicate_row_is_red(self):
        self.write('docs/ARCHITECTURE-SOURCES.md', REGISTER + '| SR2 | Actions again | a second row |\n')
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('docs/ARCHITECTURE-SOURCES.md:8: SR2 has a second row (first at line 6)', out)

    def test_overturned_row_is_printed_with_its_count_not_failed(self):
        self.write('docs/ARCHITECTURE-SOURCES.md', REGISTER.replace(
            '| SR3 | Mask | the token replaces userinfo |',
            '| SR3 | Mask | **OVERTURNED 2026-10-13:** the token replaces userinfo |'))
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        self.assertIn('sr register: SR3 mentions overturned/withdrawn/superseded at docs/ARCHITECTURE-SOURCES.md:7 and is cited 1 time(s)', out)
        self.assertIn('1 overturned', out)

    def test_binary_file_is_skipped_and_counted(self):
        self.write('docs/preview.png', b'\x89PNG\r\n\x1a\n\xff\xfe\x00', binary=True)
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        self.assertIn('1 binary skipped', out)

    def test_missing_register_file_is_red(self):
        subprocess.run(['git', '-C', self.dir, 'rm', '-q', '--cached', 'docs/ARCHITECTURE-SOURCES.md'], check=True)
        os.remove(os.path.join(self.dir, 'docs', 'ARCHITECTURE-SOURCES.md'))
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('register file missing', out)


class TreeCase(unittest.TestCase):
    """The real tree, through the same main() the gate runs."""

    def test_the_tree_is_green_with_at_least_forty_rows(self):
        out = io.StringIO()
        real = sys.stdout
        sys.stdout = out
        try:
            rc = checker.main(['--root', ROOT])
        finally:
            sys.stdout = real
        text = out.getvalue()
        self.assertEqual(rc, 0, text)
        summary = [l for l in text.split('\n') if l.startswith('sr register: ') and ' rows, ' in l]
        self.assertEqual(len(summary), 1, text)
        rows = int(summary[0].split('sr register: ')[1].split(' rows')[0])
        self.assertGreaterEqual(rows, 40, summary[0])


if __name__ == '__main__':
    unittest.main()
