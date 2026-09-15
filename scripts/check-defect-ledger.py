#!/usr/bin/env python3
"""Prove the defect ledger and the documents agree.

WHY THIS EXISTS. Defects on this project are filed in prose, in
docs/QA-RESULTS.md and docs/QA.md, by a QA lane that is writing up a live
pass. The project board, docs/STATUS.md, carries a "## Defects" table that is
supposed to be the single place you look to know what is outstanding. Nothing
joined the two: the lane wrote an id into its report, a human was supposed to
copy a row onto the board, and when nobody did, the board simply looked clean.

That is the failure mode CLAUDE.md names -- wherever two things are joined by
a NAME rather than by a call, nothing verifies the join and the failure is
invisible. It is not hypothetical here. A QA lane filed F-CHNO-4 against
exactly this ("the board is stale"), the board was patched by hand, and then
32 more ids drifted off it, including a P2 that was a release gate.

So the join is now a call. Every defect id that appears in a tracked markdown
file must have a row on the board, and every row on the board must have a
severity and a state. Findings (`F-`) count as much as defects (`D-`): a
lane choosing the gentler word does not make the item stop needing an owner. An id you file is an id that shows up here until you
give it a state, and "the release shipped" is not a state.

WHAT IT DOES NOT DO. It does not check that a state is TRUE. Nothing can:
"verified fixed" is a claim about a test somebody ran. It checks that the
claim exists and is attributed, which is the part that was silently missing.
"""

import io
import os
import re
import subprocess
import sys

# Both prefixes. `D-` is a defect, `F-` a finding that a lane filed instead
# of a defect -- the distinction is about tone, not about whether somebody
# has to act, and both went untracked for the same reason.
ID = re.compile(r'\b[DF]-[A-Z]+-[0-9]+\b')
ROW = re.compile(r'^\|\s*([DF]-[A-Z]+-[0-9]+)\s*\|(.*)$')
LEDGER_FILE = 'docs/STATUS.md'
LEDGER_HEADING = '## Defects'

# A state cell must actually say something. These are the words the board
# already uses; the point is to reject an empty cell, a dash, or a "?" that
# reads as tracked when it is not.
STATE_WORDS = (
    'open', 'fixed', 'verified', 'accepted', 'wont fix', 'will not fix',
    'superseded', 'duplicate', 'not a defect', 'withdrawn', 'closed',
)


def tracked_markdown(root):
    out = subprocess.run(
        ['git', '-C', root, 'ls-files', '-z', '--', '*.md'],
        stdout=subprocess.PIPE, check=True).stdout
    return [p for p in out.decode('utf-8').split('\0') if p]


def read(root, rel):
    with io.open(os.path.join(root, rel), encoding='utf-8') as fh:
        return fh.read()


def split_ledger(text):
    """Return (before, ledger, after) around the Defects table."""
    if LEDGER_HEADING not in text:
        return text, '', ''
    head, rest = text.split(LEDGER_HEADING, 1)
    # the table ends at the next level-2 heading, if any
    m = re.search(r'^## ', rest, re.M)
    if m:
        return head, rest[:m.start()], rest[m.start():]
    return head, rest, ''


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    # A root argument exists so tests/test_defect_ledger.py can point this at
    # a synthetic repository and prove each branch below actually fires.
    # CLAUDE.md rule 11: a new check must be shown to catch something.
    root = argv[0] if argv else os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))
    problems = []

    try:
        status = read(root, LEDGER_FILE)
    except IOError:
        # A traceback here would still exit non-zero, so the gate would catch
        # it -- but the person reading the gate would get a stack trace where
        # a sentence belongs.
        print('%s does not exist, so there is no defect ledger to check'
              % LEDGER_FILE)
        return 1
    if LEDGER_HEADING not in status:
        print('%s has no "%s" section at all' % (LEDGER_FILE, LEDGER_HEADING))
        return 1
    before, ledger, after = split_ledger(status)

    # ---- parse the ledger ------------------------------------------------
    declared = {}
    dupes = []
    for line in ledger.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        ident, rest = m.group(1), m.group(2)
        if ident in declared:
            dupes.append(ident)
            continue
        cells = [c.strip() for c in rest.split('|')]
        # Strip exactly ONE trailing empty cell: the artifact of the row's
        # closing pipe. Stripping every trailing empty made an EMPTY STATE
        # CELL vanish, so a row with nothing in its state was reported as a
        # short row instead -- red for the wrong reason, and the wrong repair
        # suggested to whoever reads it. Found by
        # tests/test_defect_ledger.py::test_an_empty_state_cell_is_red.
        if cells and cells[-1] == '':
            cells.pop()
        declared[ident] = cells

    for ident in sorted(set(dupes)):
        problems.append('%s has more than one row on the board' % ident)

    # ---- every row must carry a severity and a state ---------------------
    for ident in sorted(declared):
        cells = declared[ident]
        if len(cells) < 4:
            problems.append(
                '%s row has %d cells after the id, expected at least 4 '
                '(Sev, Task, Repro, State)' % (ident, len(cells)))
            continue
        sev, state = cells[0], cells[-1]
        if not re.match(r'^P[1-4]\b', sev):
            problems.append(
                '%s severity cell is %r, expected P1..P4' % (ident, sev))
        low = state.lower()
        if not any(w in low for w in STATE_WORDS):
            problems.append(
                '%s state cell is %r, which names no state. Use one of: %s'
                % (ident, state[:60], ', '.join(STATE_WORDS)))

    # ---- every id mentioned anywhere must have a row ---------------------
    mentions = {}
    scanned = 0
    for rel in tracked_markdown(root):
        text = read(root, rel)
        if rel == LEDGER_FILE:
            # Mentions INSIDE the ledger do not count as mentions, or every
            # row would justify itself and the orphan check below would be
            # dead. The rest of STATUS.md still counts.
            text = before + after
        scanned += 1
        for ident in ID.findall(text):
            mentions.setdefault(ident, set()).add(rel)

    if scanned == 0:
        print('defect ledger check scanned no markdown files at all '
              '(is this a git checkout?)')
        return 1
    if not mentions and not declared:
        print('defect ledger check found no defect ids anywhere, which means '
              'it is not looking where it thinks it is looking')
        return 1

    for ident in sorted(set(mentions) - set(declared)):
        where = ', '.join(sorted(mentions[ident]))
        problems.append(
            '%s is filed in %s but has no row in %s "%s"'
            % (ident, where, LEDGER_FILE, LEDGER_HEADING))

    # ---- a row for an id nobody mentions is probably a typo --------------
    for ident in sorted(set(declared) - set(mentions)):
        problems.append(
            '%s has a board row but appears in no other tracked document. '
            'Either the id is misspelled on the board or the defect was '
            'never written up' % ident)

    print('defect ledger: %d rows on the board, %d ids across %d markdown '
          'files' % (len(declared), len(set(mentions) | set(declared)), scanned))
    if problems:
        print('')
        for p in problems:
            print('  %s' % p)
        print('')
        print('%d problem(s). The board is the single view of what is '
              'outstanding; an id missing from it reads as no defect at all.'
              % len(problems))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
