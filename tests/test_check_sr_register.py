"""Prove scripts/check-sr-register.py catches what it claims to catch (F-M3-20).

CLAUDE.md rule 11: a check never seen red is decoration, so every case here
builds a throwaway git repository with a register that PASSES, breaks one
decision, and asserts the real checker's main() turns red and names the
site. Rule 12: nothing here re-implements the checker's regexes; each case
runs the shipping script.

Seen red on the tree as well: on a9d20f9 the checker named three rows
(docs/ARCHITECTURE-SOURCES.md:1761, :1763 and :1776) as cited nowhere
outside the register (3 problems over 40 rows); each is now cited where its
ruling is implemented, in docs/QA-SOURCES.md, and the tree reads 0 problems.
A fourth row (:1775) was cited only by two neighbouring rows of the table;
once the checker stopped counting the register's own rows it went red too
and is now cited in QA-SOURCES as well (P23 recheck, 2026-10-24).

NO REGISTER ID IS WRITTEN IN THIS FILE, resolvable or not. It is tracked, the
checker reads every tracked file, and an id here is a citation: the first
version of this docstring named the three rows above as literals, and that
kept them "cited" after their real citations were reverted, so the check
could not go red for its own red proof (the P23 recheck's probe). Every id
below is composed through sr(); a literal unresolvable id would be the
checker's own red, a literal resolvable one its own green.
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


def sr(n):
    """A register id, composed so this file never carries one as a literal."""
    return 'S' + 'R' + str(n)


REGISTER = (
    '# Sources architecture\n\n'
    '| Id | Topic | Ruling |\n'
    '|---|---|---|\n'
    '| %s | Identifiers | the state file keeps these names |\n'
    '| %s | Actions | addSource and friends; %s names them |\n'
    '| %s | Mask | the token replaces userinfo |\n'
) % (sr(1), sr(2), sr(1), sr(3))
ROW3 = '| %s | Mask | the token replaces userinfo |\n' % sr(3)
CITING = (
    '# QA\n\n'
    'SRC-01 covers %s and %s; the harness fake is %s territory.\n'
) % (sr(1), sr(3), sr(2))


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
        # Three citations, all from QA-SOURCES: the second row's mention of
        # the first is the register talking to itself and is not counted,
        # and the register file is not a citing file.
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        self.assertIn('sr register: 3 rows, 3 citations in 1 files, 0 overturned, 0 binary skipped, 0 problem(s)', out)

    def test_removed_row_is_red_and_named(self):
        # The third row goes; the citation in QA-SOURCES is left behind.
        self.write('docs/ARCHITECTURE-SOURCES.md', REGISTER.replace(ROW3, ''))
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('docs/QA-SOURCES.md:3: cites %s, which has no row in docs/ARCHITECTURE-SOURCES.md' % sr(3), out)
        self.assertIn('1 problem(s)', out)

    def test_citation_of_an_unwritten_id_is_red(self):
        self.write('docs/UX-SOURCES.md', '# UX\n\nThe form follows %s here.\n' % sr(9))
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('docs/UX-SOURCES.md:3: cites %s, which has no row' % sr(9), out)

    def test_an_unwritten_id_inside_a_register_row_is_red(self):
        # A row's text points at a row that does not exist: not a citation
        # for check 2, but a dangling reference for check 1 all the same.
        self.write('docs/ARCHITECTURE-SOURCES.md', REGISTER.replace(
            ROW3, '| %s | Mask | the token replaces userinfo, as %s says |\n' % (sr(3), sr(9))))
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('docs/ARCHITECTURE-SOURCES.md:7: cites %s, which has no row' % sr(9), out)

    def test_row_cited_nowhere_is_red(self):
        self.write('docs/QA-SOURCES.md', CITING.replace(sr(3), 'the mask rule'))
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('docs/ARCHITECTURE-SOURCES.md:7: %s is cited nowhere outside the register' % sr(3), out)

    def test_a_rows_own_id_does_not_count_as_its_citation(self):
        # The third row cited only by itself: "<id> stands" on its own line.
        self.write('docs/ARCHITECTURE-SOURCES.md', REGISTER.replace(
            ROW3, '| %s | Mask | the token replaces userinfo; %s stands |\n' % (sr(3), sr(3))))
        self.write('docs/QA-SOURCES.md', CITING.replace(sr(3), 'the mask rule'))
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('%s is cited nowhere outside the register' % sr(3), out)

    def test_a_row_cited_only_by_another_row_is_red(self):
        # The P23 recheck's shape: the third row's only mention is in the
        # second row's text. The register talking to itself is not a document,
        # test or script implementing the ruling. Red on the checker as first
        # committed, which counted it (1 real row was in this state).
        self.write('docs/ARCHITECTURE-SOURCES.md', REGISTER.replace(
            '| %s | Actions | addSource and friends; %s names them |\n' % (sr(2), sr(1)),
            '| %s | Actions | addSource and friends; %s names them, %s masks them |\n' % (sr(2), sr(1), sr(3))))
        self.write('docs/QA-SOURCES.md', CITING.replace(sr(3), 'the mask rule'))
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('docs/ARCHITECTURE-SOURCES.md:7: %s is cited nowhere outside the register' % sr(3), out)
        self.assertIn('1 problem(s)', out)

    def test_duplicate_row_is_red(self):
        self.write('docs/ARCHITECTURE-SOURCES.md', REGISTER + '| %s | Actions again | a second row |\n' % sr(2))
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('docs/ARCHITECTURE-SOURCES.md:8: %s has a second row (first at line 6)' % sr(2), out)

    def test_overturned_row_is_printed_with_its_count_not_failed(self):
        self.write('docs/ARCHITECTURE-SOURCES.md', REGISTER.replace(
            ROW3, '| %s | Mask | **OVERTURNED 2026-10-13:** the token replaces userinfo |\n' % sr(3)))
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        self.assertIn('sr register: %s mentions overturned/withdrawn/superseded at docs/ARCHITECTURE-SOURCES.md:7 and is cited 1 time(s)' % sr(3), out)
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

    def test_the_checker_its_test_and_the_gate_carry_no_register_id(self):
        # The self-citation guard: a literal id in any of these three files is
        # a citation the checker counts, so the rule in the docstring is
        # observed on the files themselves rather than trusted.
        for rel in ('scripts/check-sr-register.py', 'tests/test_check_sr_register.py', 'scripts/check.sh'):
            with io.open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
                text = fh.read()
            hits = [m.group(0) for m in checker.REGISTERS[0]['cite'].finditer(text)]
            self.assertEqual(hits, [], '%s carries register id(s) as literals: %s' % (rel, hits))


if __name__ == '__main__':
    unittest.main()
