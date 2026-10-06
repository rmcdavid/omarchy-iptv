"""Prove scripts/check-board-staleness.py catches staleness and nothing else.

CLAUDE.md rule 11: prove every new check catches something, and when the code
is new and there is no "before", mutate the shipping function instead and show
the test goes red. Every case here does both halves -- it asserts what the
checker does, and then breaks exactly one shipping decision and asserts the
assertion flips. A case whose mutation leaves the suite green is a case that
was testing nothing.

Rule 12: no case re-implements a regex. Each one builds a real git repository
with real commit messages on disk and runs the real main(), board_states(),
assertions_in() and reconcile(). Two cases go further and run the checker
against THIS repository's own history, at the commit that was green while five
rows were stale and at the tip where they are not -- rule 14's standard, an
acceptance that observes the real thing rather than the string the
implementation was written to contain.
"""

# EXAMPLE-DEFECT-IDS: D-AAA D-BAR D-BBB D-CCC D-FOO -- every id below is
# invented. This file builds throwaway boards and commit messages and then
# asserts what the staleness checker makes of them, so these are fixtures, not
# findings. The exemption rule, and why it is declared here rather than
# allowlisted inside the checker, is in scripts/check-defect-ledger.py.

import contextlib
import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

# Loading a module from a path can leave scripts/__pycache__ behind, and an
# untracked directory inside the tree is how a later git status lies.
sys.dont_write_bytecode = True

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = os.path.join(ROOT, 'scripts', 'check-board-staleness.py')
_s = importlib.util.spec_from_file_location('check_board_staleness', _spec)
checker = importlib.util.module_from_spec(_s)
_s.loader.exec_module(checker)

# The commit that was green while five rows read `open` against the code, and
# the tip after they were moved. Both are on dev and main is never rewritten,
# so these are stable; a checkout that does not have them skips those cases
# rather than failing for the wrong reason.
STALE_REV = '6d9b7bb'
GREEN_REV = '64fa114'
STALE_FIVE = ['D-DOC-1', 'D-DOC-2', 'D-PLY-23', 'D-SAVE-6', 'F-SINK-10']
STALE_FOUR = ['D-DOC-2', 'D-PLY-23', 'D-SAVE-6', 'F-SINK-10']

HEADER = (
    '# Status\n\n'
    '## Board\n\n'
    'Prose with no id in it at all.\n\n'
    '## Defects\n\n'
    '| ID | Sev | Task | Repro | State |\n'
    '|---|---|---|---|---|\n'
)


@contextlib.contextmanager
def mutated(**attrs):
    """Swap shipping module attributes, restore them afterwards. Used only to
    prove a case can fail."""
    old = {}
    for name, value in attrs.items():
        old[name] = getattr(checker, name)
        setattr(checker, name, value)
    try:
        yield
    finally:
        for name, value in old.items():
            setattr(checker, name, value)


MATCH_ANYTHING = re.compile(r'^.*$', re.S)
MATCH_NOTHING = re.compile(r'(?!x)x')
NO_SIGNALS = ()


class StalenessCase(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='staleness-test-')
        self.addCleanup(shutil.rmtree, self.dir, True)
        os.makedirs(os.path.join(self.dir, 'docs'))
        subprocess.run(['git', 'init', '-q', self.dir], check=True)

    # -- fixture helpers -------------------------------------------------
    def write(self, rel, text):
        path = os.path.join(self.dir, rel)
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)
        subprocess.run(['git', '-C', self.dir, 'add', rel], check=True)

    def commit(self, message):
        subprocess.run(
            ['git', '-C', self.dir,
             '-c', 'user.name=T', '-c', 'user.email=t@example.invalid',
             'commit', '-q', '--allow-empty', '-m', message], check=True)

    def read(self, rel):
        with io.open(os.path.join(self.dir, rel), encoding='utf-8') as fh:
            return fh.read()

    def board(self, rows, extra=''):
        """rows: (id, sev, task, repro, state)."""
        body = ''.join(
            '| %s | %s | %s | %s | %s |\n' % r for r in rows)
        self.write('docs/STATUS.md', HEADER + body + extra)

    def run_checker(self, *args):
        out = io.StringIO()
        old = sys.stdout
        sys.stdout = out
        try:
            rc = checker.main([self.dir] + list(args))
        finally:
            sys.stdout = old
        return rc, out.getvalue()

    # -- the four states the brief names ---------------------------------
    def test_a_stale_row_is_red(self):
        self.board([('D-FOO-1', 'P2', 'guide', 'A thing went wrong.', 'open')])
        self.commit('Close D-FOO-1 at the sink')
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('D-FOO-1', out)
        self.assertIn('close-governs-id', out)
        # Mutation: with no constructions, the same tree is green -- so this
        # case is carried by the constructions and not by anything incidental.
        with mutated(GATE_SIGNALS=NO_SIGNALS):
            rc2, out2 = self.run_checker()
        self.assertEqual(rc2, 0, out2)

    def test_a_correctly_open_row_is_green(self):
        self.board([('D-FOO-1', 'P2', 'guide', 'A thing went wrong.', 'open')])
        # The id is named, with no claim that it was closed.
        self.commit('D-FOO-1: file the defect and pin the repro')
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        # Mutation: a construction that fires on a bare mention turns this
        # correctly-open row red, which is the cry-wolf failure this check is
        # most at risk of.
        loose = (('bare-mention', re.compile(r'\b(%s)\b' % checker.IDP)),)
        with mutated(GATE_SIGNALS=loose):
            rc2, out2 = self.run_checker()
        self.assertEqual(rc2, 1, out2)

    def test_a_fixed_row_is_green(self):
        self.board([('D-FOO-1', 'P2', 'guide', 'A thing went wrong.',
                     'verified fixed')])
        self.commit('Close D-FOO-1 at the sink')
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        # Mutation: treat every state as open and the fixed row goes red.
        with mutated(BARE_OPEN=MATCH_ANYTHING):
            rc2, out2 = self.run_checker()
        self.assertEqual(rc2, 1, out2)

    def test_a_reasoned_open_row_is_the_escape_hatch(self):
        # The one false alarm measured over 523 commits was a repair landing
        # across a wave of commits (D-PLY-11, four commits). A state cell that
        # says more than the bare word exempts the row, and tells a reader
        # what `open` alone could not.
        self.board([('D-FOO-1', 'P2', 'guide', 'A thing went wrong.',
                     'open, repair in flight across the wave')])
        self.commit('Close D-FOO-1 at the sink')
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        with mutated(BARE_OPEN=re.compile(r'open', re.I)):
            rc2, out2 = self.run_checker()
        self.assertEqual(rc2, 1, out2)

    def test_a_reopened_row_is_exempt(self):
        # D-RUNG-14 really did go fixed -> **reopened** here, so an old fix
        # claim must not flare on a defect that came back.
        self.board([('D-FOO-1', 'P2', 'guide', 'A thing went wrong.',
                     '**reopened**')])
        self.commit('Close D-FOO-1 at the sink')
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        # Mutation: a pattern that cannot tell `reopened` from `open` flares
        # on the defect that came back.
        reopen_blind = re.compile(r'[*_\s]*(?:re)?opened?[*_\s]*$', re.I)
        with mutated(BARE_OPEN=reopen_blind):
            rc2, out2 = self.run_checker()
        self.assertEqual(rc2, 1, out2)

    # -- the false-positive sources, each one measured ------------------
    def test_a_negated_claim_is_not_a_claim(self):
        self.board([('D-FOO-1', 'P2', 'guide', 'A thing went wrong.', 'open')])
        self.commit('guide: a repair that does not close D-FOO-1')
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        with mutated(NEGATION=MATCH_NOTHING):
            rc2, out2 = self.run_checker()
        self.assertEqual(rc2, 1, out2)

    def test_a_negation_that_governs_something_else_hides_nothing(self):
        # The first version of the guard accepted a negation anywhere in the
        # preceding 64 characters, and silently swallowed three real claims in
        # this project's own history, among them "ARCH-P never recorded that
        # the D-PLY-11 repair ...". A guard that hides a claim is worse than
        # the cry-wolf it guards against: nothing says it fired.
        self.board([('D-FOO-1', 'P2', 'guide', 'A thing went wrong.', 'open')])
        self.commit('docs: the design never recorded that the D-FOO-1 repair '
                    'dropped the correction')
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        wide = re.compile(r'\b(?:not|never|no)\b[^.]{0,48}$', re.I)
        with mutated(NEGATION=wide):
            rc2, out2 = self.run_checker()
        self.assertEqual(rc2, 0, out2)

    def test_the_noun_forms_are_not_a_gate_claim(self):
        # "fixes D-FOO-1" in a plan is a promise. docs/PLAN-M4.md's
        # "M4-01 The guide renders (medium) -- fixes D-EPG-2" was written
        # before the work started, and would have been red for 7 commits.
        self.board([('D-FOO-1', 'P2', 'guide', 'A thing went wrong.', 'open')])
        self.commit('plan: M9-01 the thing renders -- fixes D-FOO-1')
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        with mutated(GATE_SIGNALS=checker.REPORT_SIGNALS):
            rc2, out2 = self.run_checker()
        self.assertEqual(rc2, 1, out2)

    def test_an_id_with_no_row_is_not_this_checks_business(self):
        # check-defect-ledger.py already fails on an id with no row. Failing
        # twice for one cause buries the cause.
        self.board([('D-BAR-2', 'P2', 'guide', 'Something else.', 'open')])
        self.commit('Close D-FOO-1 at the sink')
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        self.assertNotIn('D-FOO-1', out)
        claims = {'D-FOO-1': ('close-governs-id', 'abc1234 x', 'Close')}
        self.assertEqual(checker.reconcile({}, claims), [])
        self.assertEqual(
            len(checker.reconcile({'D-FOO-1': 'open'}, claims)), 1)

    # -- what only the report may say -----------------------------------
    def test_the_report_reaches_document_prose_and_never_fails(self):
        self.board([('D-FOO-1', 'P2', 'guide', 'A thing went wrong.', 'open')])
        self.write('docs/QA-RESULTS.md',
                   'The pass is written up here. D-FOO-1 is closed at the '
                   'sink.\n')
        self.commit('qa: write up the pass')
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        self.assertNotIn('D-FOO-1', out)
        rc2, out2 = self.run_checker('--report')
        self.assertEqual(rc2, 0, out2)         # the report never fails
        self.assertIn('D-FOO-1', out2)
        self.assertIn('docs/QA-RESULTS.md', out2)
        # Mutation: drop the report's extra constructions and the write-up
        # stops being visible at all.
        with mutated(REPORT_SIGNALS=NO_SIGNALS):
            rc3, out3 = self.run_checker('--report')
        self.assertEqual(rc3, 0, out3)
        self.assertNotIn('D-FOO-1', out3)

    def test_a_claim_split_over_a_line_break_prints_as_one_line(self):
        # The sentence that is the only route to the fifth stale row of
        # 2026-10-03 lists five ids in one parenthesis, across a line break:
        # "the five 0.9.1 repairs (D-SAVE-6, D-TRK-8, D-PLY-23,\nD-DOC-1,
        # D-DOC-2)". A line-oriented `git grep` cannot see D-DOC-1 there at
        # all, and a quoted claim that carries the break shreds the report's
        # one-line-per-claim layout.
        self.board([('D-FOO-9', 'P2', 'guide', 'A thing went wrong.', 'open')])
        self.write('docs/QA-RESULTS.md',
                   'Three lenses over the four repairs (D-AAA-1, D-BBB-2,\n'
                   'D-FOO-9, D-CCC-3), two refuters each.\n')
        self.commit('qa: write up the review')
        rc, out = self.run_checker('--report')
        self.assertEqual(rc, 0, out)
        self.assertIn('D-FOO-9', out)
        quoted = [l for l in out.split('\n') if l.startswith('  claim:')
                  or 'claim:' in l]
        self.assertTrue(quoted, out)
        self.assertIn('D-FOO-9', quoted[0])
        with mutated(flatten=lambda text: text):
            rc2, out2 = self.run_checker('--report')
        quoted2 = [l for l in out2.split('\n') if 'claim:' in l]
        self.assertTrue(quoted2, out2)
        self.assertNotIn('D-FOO-9', quoted2[0])

    def test_the_boards_own_rows_can_contradict_each_other(self):
        # F-BOARD-1 calls this the sharpest case: D-PLY-24's row says it
        # records what D-PLY-23's REPAIR dropped, beside a D-PLY-23 reading
        # open. It needs no git history.
        self.board([
            ('D-FOO-1', 'P2', 'guide', 'A thing went wrong.', 'open'),
            ('D-FOO-2', 'P3', 'guide',
             "Follow-up: the D-FOO-1 repair dropped the correction.",
             'fixed'),
        ])
        self.commit('board: file the follow-up')
        rc, out = self.run_checker('--report')
        self.assertEqual(rc, 0, out)
        self.assertIn('D-FOO-1', out)
        self.assertIn("D-FOO-2's own row", out)
        with mutated(REPORT_SIGNALS=NO_SIGNALS):
            rc2, out2 = self.run_checker('--report')
        self.assertNotIn("own row", out2)

    def test_a_row_does_not_close_itself(self):
        # Measured: across 523 commits no bare-open row's own Repro cell ever
        # asserted its own closure. The guard stays because the first one that
        # does would otherwise read as a disagreement with nobody.
        self.board([('D-FOO-1', 'P2', 'guide',
                     'A thing went wrong. The D-FOO-1 repair landed.',
                     'open')])
        self.commit('board: file it')
        rc, out = self.run_checker('--report')
        self.assertEqual(rc, 0, out)
        self.assertNotIn("D-FOO-1's own row", out)
        cross = checker.cross_row_claims
        src = self.read('docs/STATUS.md')
        self.assertEqual(cross(src), {})
        # Mutation: stop skipping the self-reference and the row accuses
        # itself.
        def self_accusing(status_text):
            out = {}
            rest = status_text.split(checker.LEDGER_HEADING, 1)[1]
            for line in rest.splitlines():
                m = checker.ROW.match(line)
                if not m:
                    continue
                for i, (sig, w) in checker.assertions_in(
                        line, checker.REPORT_SIGNALS).items():
                    out.setdefault(i, (sig, '%s row' % m.group(1), w))
            return out
        self.assertIn('D-FOO-1', self_accusing(src))

    # -- the earliest claim is the one reported --------------------------
    def test_the_earliest_claim_is_the_one_named(self):
        self.board([('D-FOO-1', 'P2', 'guide', 'A thing went wrong.', 'open')])
        self.commit('Close D-FOO-1 at the sink')
        first = subprocess.run(
            ['git', '-C', self.dir, 'rev-parse', '--short=7', 'HEAD'],
            stdout=subprocess.PIPE, check=True).stdout.decode().strip()
        self.commit('guide: the D-FOO-1 repair needed a second half')
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn(first, out)
        self.assertIn('Close D-FOO-1 at the sink', out)

    # -- pure parsing, where the shipping parse is the thing tested -----
    def test_the_rows_closing_pipe_does_not_swallow_the_state(self):
        # Every row ends in a pipe, so the split always produces one trailing
        # empty cell. Reading the last cell without dropping it makes every
        # state the empty string, no row is ever bare-open, and the check goes
        # quietly dead while still printing a row count.
        self.board([('D-FOO-1', 'P2', 'guide',
                     r'Repro: `grep -c foo \| wc -l` says two.', 'open')])
        src = self.read('docs/STATUS.md')
        # The escaped pipe stays inside its own cell, so the state is still
        # readable: D-PLY-9's Repro cell legitimately quotes shell with `\|`.
        self.assertEqual(checker.board_states(src), {'D-FOO-1': 'open'})
        self.commit('Close D-FOO-1 at the sink')
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        with mutated(state_cell=lambda cells: cells[-1] if cells else ''):
            self.assertEqual(checker.board_states(src), {'D-FOO-1': ''})
            rc2, out2 = self.run_checker()
        self.assertEqual(rc2, 0, out2)
        self.assertIn('0 bare-open', out2)

    def test_a_family_with_a_digit_is_still_an_id(self):
        # The first id filed after check-defect-ledger.py shipped was
        # D-A11Y-1, which its pattern could not see.
        self.assertIn('D-A11Y-1',
                      checker.assertions_in('Close D-A11Y-1 at the sink'))

    # -- acceptance against this repository's real history --------------
    def _rev_exists(self, rev):
        return subprocess.run(['git', '-C', ROOT, 'rev-parse', '--verify',
                               '-q', rev + '^{commit}'],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0

    def _real(self, rev, *args):
        out = io.StringIO()
        old = sys.stdout
        sys.stdout = out
        try:
            rc = checker.main([ROOT, '--at', rev] + list(args))
        finally:
            sys.stdout = old
        return rc, out.getvalue()

    def test_the_real_tree_that_was_green_while_five_rows_were_stale(self):
        if not self._rev_exists(STALE_REV):
            self.skipTest('%s is not in this checkout' % STALE_REV)
        rc, out = self._real(STALE_REV)
        self.assertEqual(rc, 1, out)
        named = sorted(set(re.findall(r'\b[DF]-[A-Z][A-Z0-9]*-[0-9]+\b',
                                      out.split('\n\n')[1])))
        self.assertEqual(named, STALE_FOUR, out)
        rc2, out2 = self._real(STALE_REV, '--report')
        self.assertEqual(rc2, 0, out2)
        for ident in STALE_FIVE:
            self.assertIn(ident, out2)

    def test_the_real_tip_is_green(self):
        if not self._rev_exists(GREEN_REV):
            self.skipTest('%s is not in this checkout' % GREEN_REV)
        rc, out = self._real(GREEN_REV)
        self.assertEqual(rc, 0, out)
        self.assertIn('0 disagreement(s)', out)
        rc2, out2 = self._real(GREEN_REV, '--report')
        self.assertEqual(rc2, 0, out2)
        self.assertIn('0 further disagreement(s)', out2)

    # -- the shapes that lost, kept as assertions so the choice is live --
    def test_a_repro_cell_that_says_fixed_is_not_the_signal_we_chose(self):
        # Shape A: a state keyword the write-up must carry. Measured: on
        # 2026-10-02 none of the five had FIXED anywhere but the state cell
        # they were about to get, so the convention sees no history. This case
        # pins what the chosen check does with such a row: nothing, because
        # the cell is the row's own voice about itself.
        self.board([('D-FOO-1', 'P2', 'guide',
                     'A thing went wrong. **FIXED 2026-10-03** at the sink.',
                     'open')])
        self.commit('board: file it')
        rc, out = self.run_checker('--report')
        self.assertEqual(rc, 0, out)
        self.assertNotIn('D-FOO-1', out)

    # -- the corpus stays markdown-only, deliberately (F-EPG-21) ----------

    def test_a_closure_claim_in_a_source_file_is_not_a_claim(self):
        """The ledger check widened its corpus to every tracked file. This one
        must not, and the reason is the question each one asks.

        A source file is full of text that LOOKS like a past-tense closure
        assertion and is not one: this checker's own docstring quotes five such
        claims while explaining what the signals matched historically, and its
        own tests hold "Close <id> at the sink" as a string whose entire job is
        to be matched. Measured on d5c2d7a, widening yields 24 claims, 13 of
        them from those self-referential sources, and zero new disagreements.

        The widening is also unnecessary: the GATE half reads `git log`, not
        markdown, so an id cited only in a script is already covered the moment
        a commit message claims its closure. That is the next case.
        """
        self.board([('D-FOO-1', 'P2', 'guide', 'A thing went wrong.', 'open')])
        self.write('scripts/grade.py',
                   '# The D-FOO-1 repair is quoted here, not asserted.\n')
        self.commit('board: file it, and record the quotation')
        rc, out = self.run_checker('--report')
        self.assertEqual(rc, 0, out)
        self.assertNotIn('D-FOO-1', out)
        # Mutation: drop the markdown pathspec from the corpus and the same
        # tree reports the quotation as a claim about the present board.
        real_git = checker._git

        def every_tracked_file(root, *args):
            if args[:2] == ('ls-files', '-z'):
                return real_git(root, 'ls-files', '-z')
            return real_git(root, *args)

        with mutated(_git=every_tracked_file):
            rc2, out2 = self.run_checker('--report')
        self.assertEqual(rc2, 0, out2)       # the advisory half never fails
        self.assertIn('D-FOO-1', out2)
        self.assertIn('1 further disagreement(s)', out2)

    def test_a_commit_claim_reaches_an_id_that_lives_only_in_code(self):
        """Why widening the document corpus buys nothing the gate needs.

        The id here is cited in no document at all -- only in a .py and in the
        commit message that claims its closure -- and the gate still refuses
        the tree. This is the half of F-EPG-21 that was already covered, and
        the case exists so that nobody widens the corpus believing it was not.
        """
        self.board([('D-FOO-1', 'P2', 'guide', 'A thing went wrong.', 'open')])
        self.write('scripts/grade.py', '# announced by id only here\n')
        self.commit('Close D-FOO-1 at the sink')
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('D-FOO-1', out)
        with mutated(GATE_SIGNALS=NO_SIGNALS):
            rc2, out2 = self.run_checker()
        self.assertEqual(rc2, 0, out2)



if __name__ == '__main__':
    unittest.main()
