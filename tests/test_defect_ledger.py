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

# EXAMPLE-DEFECT-IDS: D-AAA F-BBB -- every id below is invented. This file
# writes synthetic repositories to a temporary directory and breaks them one
# decision at a time, so these are fixtures, not findings. The rule that makes
# this line exempt them, and the two alternatives it beat, are documented in
# scripts/check-defect-ledger.py.

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

    def write_bytes(self, rel, blob):
        """A tracked file that is not text at all -- this tree has two."""
        path = os.path.join(self.dir, rel)
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with open(path, 'wb') as fh:
            fh.write(blob)
        subprocess.run(['git', '-C', self.dir, 'add', rel], check=True)

    def marker(self, families, reason='invented for this case'):
        """An example-id marker line, ASSEMBLED rather than written as a
        literal.

        This is load-bearing. A complete marker written as a literal in THIS
        file would declare those families FOR THIS FILE in the real
        repository's own gate run, and several cases below deliberately declare
        families this file does not cite -- which the dead-exemption check
        would then report, correctly, against the test file. Splitting the
        token keeps the synthetic markers synthetic.
        """
        return '# EXAMPLE-DEFECT%s %s -- %s\n' % ('-IDS:', families, reason)

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

    def test_a_doubled_cell_separator_is_red(self):
        """The real incident: a bulk relabel emitted `| | state |`.

        Every row it touched grew an empty cell and its state slid one column
        right. The board rendered wrong and the whole gate stayed green,
        because the old check asked for "at least 4" cells and then read the
        LAST one, which still held a state word. Too many cells is the
        direction that hides damage, so the shape is now exact.
        """
        self.good_ledger()
        self.write('docs/STATUS.md', HEADER + (
            '| D-AAA-1 | P2 | M1 | a thing broke | verified fixed at abc1234 |\n'
            '| D-AAA-2 | P3 | M1 | another thing | | open |\n'))
        self.assertRed(r'D-AAA-2 row has 5 cells after the id, '
                       r'expected exactly 4')

    def test_an_escaped_pipe_inside_a_cell_stays_green(self):
        """The fix must not punish a cell that legitimately quotes a pipe.

        D-PLY-9's Repro cell quotes shell containing a pipe, written `\\|` so
        the table still renders. Splitting on every pipe scattered that row
        across five phantom cells; an exact-shape check over a naive split
        would have called the board corrupt and been wrong.
        """
        self.good_ledger()
        self.write('docs/STATUS.md', HEADER + (
            '| D-AAA-1 | P2 | M1 | a thing broke | verified fixed at abc1234 |\n'
            '| D-AAA-2 | P3 | M1 | `grep -c x \\| head -1` lies | open |\n'))
        self.assertGreen()

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
            or 'scanned no tracked files' in out,
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

    # -- a titled finding with no id (D-REL-3's class) ---------------------

    FINDINGS_DOC = (
        '## 11. Contradictions and gaps found while planning\n\n'
        '1. **The README tells the user to run a command that is not on PATH.**\n'
        '   Suggested: P2 documentation.\n'
        '2. **CHANGELOG has no 0.3.0 section.** Filed as D-AAA-2.\n'
        '3. Step three of a procedure, not a finding, so no id is owed.\n'
    )

    def test_a_titled_finding_with_no_id_is_red(self):
        self.good_ledger()
        self.write('docs/QA-X.md', self.FINDINGS_DOC)
        out = self.assertRed(r'docs/QA-X\.md:3 "The README tells the user to run a command.*is a titled finding with no D-/F- id')
        self.assertNotIn('CHANGELOG has no', out)          # item 2 cites one
        self.assertNotIn('Step three', out)                # untitled: a remark

    def test_the_id_may_sit_on_a_continuation_line(self):
        self.good_ledger()
        self.write('docs/QA-X.md', self.FINDINGS_DOC.replace(
            '   Suggested: P2 documentation.\n',
            '   Suggested: P2 documentation. **Filed as D-AAA-1 (2026-09-25).**\n'))
        self.assertGreen()

    def test_a_blank_line_ends_the_item_so_a_later_id_does_not_rescue_it(self):
        self.good_ledger()
        self.write('docs/QA-X.md', self.FINDINGS_DOC.replace(
            '   Suggested: P2 documentation.\n',
            '   Suggested: P2 documentation.\n\n   See D-AAA-1.\n'))
        self.assertRed(r'is a titled finding with no D-/F- id')

    def test_a_heading_that_declares_no_defect_ids_is_exempt(self):
        self.good_ledger()
        self.write('docs/QA-X.md', self.FINDINGS_DOC.replace(
            '## 11. Contradictions and gaps found while planning',
            '## Hardening (non-blocking, no defect ids)'))
        self.assertGreen()
        self.write('docs/QA-Y.md', self.FINDINGS_DOC.replace(
            '## 11. Contradictions and gaps found while planning',
            '## The three problems, stated plainly (not defects)'))
        self.assertGreen()

    def test_a_heading_that_does_not_name_findings_is_not_scanned(self):
        self.good_ledger()
        self.write('docs/QA-X.md', self.FINDINGS_DOC.replace(
            '## 11. Contradictions and gaps found while planning',
            '## 9. Live runbook'))
        self.assertGreen()

    def test_the_scan_stops_at_the_next_heading_of_the_same_level(self):
        self.good_ledger()
        self.write('docs/QA-X.md',
                   '## Findings\n\n1. **A real one.** Filed as D-AAA-1.\n\n'
                   '## Runbook\n\n1. **Bold step title**, no id owed here.\n')
        self.assertGreen()

    def test_every_heading_vocabulary_word_triggers_the_scan(self):
        self.good_ledger()
        for word in ('Findings', 'Defects', 'Problems', 'Gaps', 'Contradictions',
                     'Issues', 'Weaknesses', 'Things found while planning'):
            self.write('docs/QA-X.md', self.FINDINGS_DOC.replace(
                '## 11. Contradictions and gaps found while planning', '## ' + word))
            with self.subTest(word=word):
                # "Weaknesses" was the one that slipped: the first regex
                # allowed one optional "s" and this plural takes "es".
                self.assertRed(r'titled finding with no D-/F- id')

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

    # -- the corpus is every tracked file, not only markdown (F-EPG-21) ----
    #
    # These cases are the "before" half of CLAUDE.md rule 11: each one is
    # green against the checker as it was, because `git ls-files -- '*.md'`
    # could not see the file the id is in.

    def test_an_id_cited_only_in_a_python_file_needs_a_row(self):
        """The finding this round exists for.

        An id cited in a script is a filed id. The grader that went on
        announcing a renamed finding did it from a .py, and both gates were
        green the whole time because neither one was looking at .py files.
        """
        self.good_ledger()
        self.write('scripts/grade.py',
                   '# The premise this grader announces is D-AAA-3.\n')
        self.assertRed(r'D-AAA-3 is filed in scripts/grade\.py but has no row')

    def test_an_id_cited_only_in_qml_needs_a_row(self):
        """Where the one real catch on this tree actually lives."""
        self.good_ledger()
        self.write('Service.qml',
                   '  // D-AAA-3, found live: this used to pass the wrong\n'
                   '  // thing straight through.\n')
        self.assertRed(r'D-AAA-3 is filed in Service\.qml but has no row')

    def test_an_id_cited_only_in_an_extensionless_file_needs_a_row(self):
        """No extension, 88 citations.

        `bin/omarchy-iptv` is the most id-dense source file in the tree and has
        no suffix at all, so a corpus built from a list of extensions would
        read as widened and still miss it. This case is the one that makes the
        difference between `git ls-files` and `git ls-files -- '*.py' '*.js'
        ...` visible.
        """
        self.good_ledger()
        self.write('bin/helper',
                   '#!/usr/bin/env python3\n'
                   '# Repair 2 (D-AAA-3): the id as written, plus lower case.\n')
        self.assertRed(r'D-AAA-3 is filed in bin/helper but has no row')

    def test_a_row_cited_only_in_code_is_not_an_orphan(self):
        """The other direction of the same widening.

        Before it, a row whose only write-up was a code comment read as "never
        written up" -- the widening has to satisfy the orphan branch as well as
        feed the missing-row branch, or it trades one false report for another.
        """
        self.write('docs/STATUS.md', HEADER + (
            '| D-AAA-1 | P2 | M1 | a thing broke | verified fixed at abc1234 |\n'))
        self.write('docs/QA-RESULTS.md', 'This pass filed nothing.\n')
        self.write('Model.js', '// D-AAA-1\'s fix: keep the raw list.\n')
        self.assertGreen()

    def test_an_id_cited_only_in_markdown_is_still_reported(self):
        """The widening must not move the behaviour it already had.

        Green against the old checker and green against the new one, by
        design: a regression guard rather than a catch.
        """
        self.good_ledger()
        self.write('docs/QA-RESULTS.md',
                   'The pass filed D-AAA-1, D-AAA-2 and D-AAA-3.\n')
        self.assertRed(r'D-AAA-3 is filed in docs/QA-RESULTS\.md but has no row')

    def test_a_tracked_binary_is_skipped_and_counted(self):
        """A PNG and a gzipped fixture are tracked here.

        Widening the corpus means reading files that are not text, and a
        decode error must not take the gate down with a traceback where a
        sentence belongs -- the same defect this file already caught once, on
        a missing STATUS.md. The count is printed so a tree where the scan
        quietly stopped looking cannot read as full coverage.
        """
        self.good_ledger()
        self.write_bytes('preview.png', b'\x89PNG\r\n\x1a\n\xff\xfe\x00D-AAA-3')
        out = self.assertGreen()
        self.assertIn('1 not text and skipped', out)
        self.assertNotIn('Traceback', out)

    # -- the example-id exemption -----------------------------------------

    def test_a_marker_exempts_its_own_families_in_its_own_file(self):
        """The twelve synthetic ids this widening would otherwise report."""
        self.good_ledger()
        self.write('tests/test_thing.py',
                   self.marker('F-BBB') +
                   'cases = ["F-BBB-7", "F-BBB-8"]\n')
        out = self.assertGreen()
        self.assertIn('example-id exemptions: 1 file(s), 1 family(ies), '
                      '2 citation(s)', out)

    def test_the_census_is_printed_on_a_green_run(self):
        """An exemption nobody sees is an exemption that grows.

        The count is in the gate's own output, not in a comment somebody has to
        go and find, so a declaration that appears in a diff also appears in
        the number the next green run prints.
        """
        self.good_ledger()
        out = self.assertGreen()
        self.assertIn('example-id exemptions: 0 file(s), 0 family(ies), '
                      '0 citation(s)', out)

    def test_a_marker_does_not_exempt_a_family_it_did_not_declare(self):
        """The exemption is per family, not per file.

        This is the whole reason an explicit exclusion of the checkers' own
        test files was rejected: that form exempts a FILE, so a real finding
        cited in it is unchecked forever.
        """
        self.good_ledger()
        self.write('tests/test_thing.py',
                   self.marker('F-BBB') +
                   'cases = ["F-BBB-7", "D-AAA-3"]\n')
        self.assertRed(r'D-AAA-3 is filed in tests/test_thing\.py '
                       r'but has no row')

    def test_a_marker_in_one_file_does_not_exempt_another_file(self):
        """A declaration is local, and a leak out of it is reported.

        Without this the example families would be a global namespace by the
        back door: declare D-AAA once in a test and every citation of it
        anywhere in the tree goes quiet.
        """
        self.good_ledger()
        self.write('tests/test_thing.py',
                   self.marker('F-BBB') + 'cases = ["F-BBB-7"]\n')
        self.write('Service.qml', '  // F-BBB-7, found live.\n')
        self.assertRed(r'Service\.qml cites F-BBB-7, but F-BBB is declared '
                       r'an EXAMPLE family in tests/test_thing\.py')

    def test_a_declared_family_that_has_a_board_row_is_red(self):
        """The anti-abuse half: you cannot declare a real family an example.

        A family the board tracks is a family somebody is acting on. If the
        marker could cover it, the exemption would be a way to delete a row's
        write-up from the gate's view without touching the row.
        """
        self.good_ledger()
        self.write('tests/test_thing.py',
                   self.marker('D-AAA') + 'cases = ["D-AAA-1"]\n')
        self.assertRed(r'tests/test_thing\.py declares D-AAA as an example '
                       r'family, and the board carries D-AAA-1, D-AAA-2')

    def test_a_declared_family_cited_in_a_document_is_red(self):
        """Markdown is where real findings get written up.

        So an example id has no business in one, and a document explaining the
        convention names an unnumbered family instead. This is the check that
        makes it hard for a real finding to hide behind the exemption by
        accident: a finding gets written up, and the write-up is a document.
        """
        self.write('docs/STATUS.md', HEADER + (
            '| F-BBB-7 | P3 | M2 | a thing broke | open |\n'))
        self.write('docs/QA-RESULTS.md',
                   'The pass filed F-BBB-7 and also D-AAA-4.\n')
        self.write('tests/test_thing.py',
                   self.marker('D-AAA') + 'cases = ["D-AAA-4"]\n')
        self.assertRed(r'docs/QA-RESULTS\.md cites D-AAA-4, whose family is '
                       r'declared an EXAMPLE in tests/test_thing\.py')

    def test_a_document_may_not_carry_a_marker(self):
        """The exemption is for source files.

        A document that declares its own example ids would be exempting itself
        from the one rule that makes a real finding hard to hide: that a
        finding gets written up, and a write-up is a document.
        """
        self.good_ledger()
        self.write('docs/QA-X.md',
                   self.marker('F-BBB') + '\nF-BBB-7 is an example.\n')
        self.assertRed(r'docs/QA-X\.md is a document and carries an '
                       r'example-id marker')

    def test_a_declared_family_the_file_never_cites_is_red(self):
        """A dead exemption is how an exemption list rots.

        It is also how one is smuggled in ahead of the citation it was meant
        for: a marker that covers nothing today covers whatever is written
        under that family tomorrow, in silence.
        """
        self.good_ledger()
        self.write('tests/test_thing.py',
                   self.marker('F-BBB') + 'cases = []\n')
        self.assertRed(r'tests/test_thing\.py declares F-BBB as an example '
                       r'family and cites no F-BBB-<n> id')

    def test_a_marker_with_no_reason_exempts_nothing(self):
        """Fail closed, and say so.

        The reason after `--` is mandatory because it is the part a reviewer
        reads. A marker without one is not a marker, so the ids stay held to
        the board -- and the author is told why, rather than being left to
        wonder why an id they believed exempt is still being reported.
        """
        self.good_ledger()
        self.write('tests/test_thing.py',
                   '# EXAMPLE-DEFECT%s D-AAA\n' % '-IDS:' +
                   'cases = ["D-AAA-3"]\n')
        out = self.assertRed(r'tests/test_thing\.py carries an example-id '
                             r'marker whose family list parses to nothing')
        self.assertIn('D-AAA-3 is filed in tests/test_thing.py', out)

    def test_a_marker_listing_numbered_ids_exempts_nothing(self):
        """Families, not ids.

        `D-AAA-3` on a marker line looks like it exempts D-AAA-3 and would
        quietly exempt the whole D-AAA family if the parse were loose about
        it. It parses to nothing instead, which is the direction that
        announces itself.
        """
        self.good_ledger()
        self.write('tests/test_thing.py',
                   self.marker('D-AAA-3') + 'cases = ["D-AAA-3"]\n')
        out = self.assertRed(r'family list parses to nothing')
        self.assertIn('D-AAA-3 is filed in tests/test_thing.py', out)

    def test_the_exemption_parse_is_the_shipping_one(self):
        """Rule 12: call the shipping function, do not mirror the regex."""
        families, had = checker.example_families(
            self.marker('D-AAA F-BBB'))
        self.assertEqual(families, set(['D-AAA', 'F-BBB']))
        self.assertTrue(had)
        families, had = checker.example_families('nothing to declare here\n')
        self.assertEqual(families, set())
        self.assertFalse(had)
        self.assertEqual(checker.family_of('D-A11Y-1'), 'D-A11Y')



if __name__ == '__main__':
    unittest.main()
