"""Prove scripts/check-defect-ledger.py catches what it claims to catch.

CLAUDE.md rule 11: prove every new check catches something, by mutation if
there is no "before". Rule 12: a test that mirrors logic instead of calling it
can pass while the shipping path is broken -- so every case here builds a real
git repository on disk and runs the real checker's main() against it, rather
than re-implementing its regexes.

Each case starts from a ledger that PASSES, breaks exactly one thing, and
asserts the checker turns red and says why. A case that cannot make the
checker red is a case the checker does not actually cover.
"""

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

_spec = os.path.join(ROOT, 'scripts', 'check-defect-ledger.py')
# The script has a hyphen in its name, so it cannot be imported by name.
import importlib.util
_s = importlib.util.spec_from_file_location('check_defect_ledger', _spec)
checker = importlib.util.module_from_spec(_s)
_s.loader.exec_module(checker)


HEADER = (
    '# Status\n\n'
    '## Board\n\n'
    'Nothing here mentions an id.\n\n'
    '## Defects\n\n'
    '| ID | Sev | Task | Repro | State |\n'
    '|---|---|---|---|---|\n'
)


class LedgerCase(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='ledger-test-')
        self.addCleanup(shutil.rmtree, self.dir, True)
        os.makedirs(os.path.join(self.dir, 'docs'))
        subprocess.run(['git', 'init', '-q', self.dir], check=True)

    def write(self, rel, text):
        path = os.path.join(self.dir, rel)
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)
        subprocess.run(['git', '-C', self.dir, 'add', rel], check=True)

    def run_checker(self):
        """Run the real main(), capturing what it printed."""
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = checker.main([self.dir])
        return code, buf.getvalue()

    def assertGreen(self):
        code, out = self.run_checker()
        self.assertEqual(code, 0, 'expected green, got:\n' + out)
        return out

    def assertRed(self, pattern):
        code, out = self.run_checker()
        self.assertEqual(code, 1, 'expected red, got green:\n' + out)
        self.assertTrue(
            re.search(pattern, out),
            'red for the wrong reason. Wanted %r, got:\n%s' % (pattern, out))
        return out

    # -- the baseline this whole file mutates from ------------------------

    def good_ledger(self):
        self.write('docs/STATUS.md', HEADER + (
            '| D-AAA-1 | P2 | M1 | a thing broke | verified fixed at abc1234 |\n'
            '| D-AAA-2 | P3 | M1 | another thing | open |\n'))
        self.write('docs/QA-RESULTS.md',
                   'The pass filed D-AAA-1 and also D-AAA-2.\n')

    def test_a_consistent_ledger_is_green(self):
        self.good_ledger()
        out = self.assertGreen()
        self.assertIn('2 rows on the board', out)

    # -- one mutation per branch ------------------------------------------

    def test_an_id_filed_in_prose_with_no_board_row_is_red(self):
        self.good_ledger()
        self.write('docs/QA-RESULTS.md',
                   'The pass filed D-AAA-1, D-AAA-2 and D-AAA-3.\n')
        self.assertRed(r'D-AAA-3 is filed in docs/QA-RESULTS\.md but has no row')

    def test_a_row_for_an_id_nobody_wrote_up_is_red(self):
        self.good_ledger()
        self.write('docs/STATUS.md', HEADER + (
            '| D-AAA-1 | P2 | M1 | a thing broke | verified fixed at abc1234 |\n'
            '| D-AAA-2 | P3 | M1 | another thing | open |\n'
            '| D-AAA-9 | P3 | M1 | typo in the id | open |\n'))
        self.assertRed(r'D-AAA-9 has a board row but appears in no other')

    def test_an_empty_state_cell_is_red(self):
        self.good_ledger()
        self.write('docs/STATUS.md', HEADER + (
            '| D-AAA-1 | P2 | M1 | a thing broke | verified fixed at abc1234 |\n'
            '| D-AAA-2 | P3 | M1 | another thing |  |\n'))
        self.assertRed(r"D-AAA-2 state cell is '', which names no state")

    def test_a_state_cell_that_names_no_state_is_red(self):
        self.good_ledger()
        self.write('docs/STATUS.md', HEADER + (
            '| D-AAA-1 | P2 | M1 | a thing broke | verified fixed at abc1234 |\n'
            '| D-AAA-2 | P3 | M1 | another thing | shipped in 0.5.0 |\n'))
        # "the release shipped" is the exact non-answer this rejects
        self.assertRed(r'D-AAA-2 state cell is .*which names no state')

    def test_a_missing_severity_is_red(self):
        self.good_ledger()
        self.write('docs/STATUS.md', HEADER + (
            '| D-AAA-1 | P2 | M1 | a thing broke | verified fixed at abc1234 |\n'
            '| D-AAA-2 | - | M1 | another thing | open |\n'))
        self.assertRed(r"D-AAA-2 severity cell is '-'")

    def test_a_truncated_row_is_red(self):
        self.good_ledger()
        self.write('docs/STATUS.md', HEADER + (
            '| D-AAA-1 | P2 | M1 | a thing broke | verified fixed at abc1234 |\n'
            '| D-AAA-2 | P3 | open |\n'))
        self.assertRed(r'D-AAA-2 row has \d+ cells after the id')

    def test_the_same_id_twice_is_red(self):
        self.good_ledger()
        self.write('docs/STATUS.md', HEADER + (
            '| D-AAA-1 | P2 | M1 | a thing broke | verified fixed at abc1234 |\n'
            '| D-AAA-2 | P3 | M1 | another thing | open |\n'
            '| D-AAA-2 | P3 | M1 | filed twice | verified fixed |\n'))
        self.assertRed(r'D-AAA-2 has more than one row')

    def test_a_ledger_with_no_defects_section_is_red(self):
        self.good_ledger()
        self.write('docs/STATUS.md', '# Status\n\nNo defects section here.\n')
        self.assertRed(r'has no "## Defects" section at all')

    # -- the "exits 0 having done nothing" failure this project keeps hitting

    def test_a_board_row_does_not_justify_itself(self):
        """The ledger's own rows must not count as prose mentions.

        If they did, every row would be self-justifying and the orphan branch
        above would be permanently dead while still appearing to run.
        """
        self.write('docs/STATUS.md', HEADER + (
            '| D-AAA-1 | P2 | M1 | a thing broke | open |\n'))
        self.write('docs/QA-RESULTS.md', 'This pass filed nothing.\n')
        self.assertRed(r'D-AAA-1 has a board row but appears in no other')

    def test_a_repository_with_no_markdown_at_all_is_red(self):
        self.write('docs/STATUS.md', HEADER)
        os.remove(os.path.join(self.dir, 'docs', 'STATUS.md'))
        subprocess.run(['git', '-C', self.dir, 'rm', '-q', '--cached',
                        'docs/STATUS.md'], check=True)
        code, out = self.run_checker()
        self.assertEqual(code, 1)
        # Any of the three is a loud, diagnosed failure. What must NOT happen
        # is a green run, or a stack trace where a sentence belongs -- both of
        # which this case caught while it was being written.
        self.assertTrue(
            'does not exist' in out
            or 'no "## Defects"' in out
            or 'scanned no markdown' in out,
            'expected a loud empty-run failure, got:\n' + out)
        self.assertNotIn('Traceback', out)

    def test_a_cited_model_symbol_that_does_not_exist_is_red(self):
        """A citation is a fact a script can settle, unlike a state.

        The checker's own docstring says it cannot verify that a state is TRUE,
        which is right about states and too modest about names. Two citations
        had already drifted before this existed: a board row described a
        constant that had been renamed, and an ACCEPTANCE CRITERION graded a
        function that never existed in any commit.
        """
        self.good_ledger()
        self.write('Model.js', 'function realThing() { return 1 }\n')
        self.write('docs/QA-RESULTS.md',
                   'The pass filed D-AAA-1 and D-AAA-2. See `Model.realThing`.\n')
        self.assertGreen()
        self.write('docs/QA-RESULTS.md',
                   'The pass filed D-AAA-1 and D-AAA-2. See `Model.ghostThing`.\n')
        self.assertRed(r'Model\.ghostThing is cited in docs/QA-RESULTS\.md')

    def test_citations_with_no_model_file_are_red_but_silence_is_not(self):
        """A repo with neither citations nor a Model.js is consistent."""
        self.good_ledger()
        self.assertGreen()
        self.write('docs/QA-RESULTS.md',
                   'The pass filed D-AAA-1, D-AAA-2 and cites `Model.anything`.\n')
        self.assertRed(r'Model\.js is unreadable')

    def test_a_family_name_containing_digits_is_still_seen(self):
        """`D-A11Y-1` must be an id, not invisible text.

        The first id filed after this check shipped was exactly that, and the
        pattern of the day could not see it: a silent miss inside the check
        written to stop silent misses. It was caught only because the row
        count failed to move.
        """
        self.good_ledger()
        self.write('docs/QA-RESULTS.md',
                   'The pass filed D-AAA-1, D-AAA-2 and D-A11Y-1.\n')
        self.assertRed(r'D-A11Y-1 is filed in docs/QA-RESULTS\.md but has no row')

    def test_a_finding_id_is_tracked_exactly_like_a_defect_id(self):
        """F- and D- are the same obligation.

        A lane that writes "finding" instead of "defect" has still found
        something somebody must decide about. Both of this project's real
        F- ids sat untracked for exactly as long as the D- ids did.
        """
        self.good_ledger()
        self.write('docs/QA-RESULTS.md',
                   'The pass filed D-AAA-1, D-AAA-2 and also F-BBB-7.\n')
        self.assertRed(r'F-BBB-7 is filed in docs/QA-RESULTS\.md but has no row')

    def test_a_finding_row_satisfies_a_finding_mention(self):
        self.write('docs/STATUS.md', HEADER + (
            '| F-BBB-7 | P3 | M2 | a lane specified verbs nobody built | '
            'fixed at abc1234 |\n'))
        self.write('docs/QA-RESULTS.md', 'The pass filed F-BBB-7.\n')
        self.assertGreen()

    def test_ids_in_any_tracked_markdown_count_not_just_docs(self):
        """A defect cited in a harness README is still a filed defect."""
        self.good_ledger()
        self.write('scripts/dev-harness/README.md', 'See D-AAA-4 for why.\n')
        self.assertRed(r'D-AAA-4 is filed in scripts/dev-harness/README\.md')


if __name__ == '__main__':
    unittest.main()
