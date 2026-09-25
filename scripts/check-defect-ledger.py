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
# The family part allows digits after its first letter. It did not, and the
# very first id filed after this check shipped was `D-A11Y-1`, which the
# pattern could not see -- a silent miss, in the check written to stop silent
# misses. Caught within the hour only because the row count did not move.
ID = re.compile(r'\b[DF]-[A-Z][A-Z0-9]*-[0-9]+\b')
ROW = re.compile(r'^\|\s*([DF]-[A-Z][A-Z0-9]*-[0-9]+)\s*\|(.*)$')
# A cell boundary is a pipe the author did not escape. Splitting on every pipe
# scattered D-PLY-9's Repro cell -- which legitimately quotes shell containing
# `\|` -- across five phantom cells, and the state was then read from the last
# of them by luck rather than by parse.
CELL = re.compile(r'(?<!\\)\|')
LEDGER_FILE = 'docs/STATUS.md'
LEDGER_HEADING = '## Defects'

# ---- titled findings must carry an id ----------------------------------
#
# The join above only works for text that already has an id. A finding
# written into a QA document as a numbered item with a bold title and a
# severity in prose -- "3. **PO-2's escape hatch is not a runnable
# command.** ... Suggested: P2" -- has everything a defect has except the
# one thing this check can see. docs/QA-PLAYER.md section 11 held ten of
# those for eleven days. One recurred twice in shipped files before anyone
# noticed (D-REL-3); three had been fixed within the hour and read as open;
# one was half done and read as done (D-PLY-17). So: under a heading that
# calls its contents findings, defects, problems, gaps, contradictions,
# issues or weaknesses, every numbered item that opens with a bold title is
# a finding and must name a D- or F- id. An untitled item is a remark or a
# step and is not held to it. A heading that says "no defect ids" or "not
# defects" is declaring its list out of scope, visibly, on the line a reader
# sees first; SECURITY-REVIEW.md's hardening list already did.
FINDING_HEADING = re.compile(
    r'^(#{2,4})\s+(.*)$')
FINDING_WORDS = re.compile(
    r'\b(?:finding|defect|problem|gap|contradiction|issue|weakness)(?:es|s)?\b'
    r'|\bfound while\b', re.I)
FINDING_EXEMPT = re.compile(r'\bno defect ids\b|\bnot defects\b', re.I)
TITLED_ITEM = re.compile(r'^\s{0,3}(\d+)\.\s+\*\*(.+?)\*\*')

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


def titled_findings_without_id(text):
    """(line number, heading, title) for every bold-titled numbered item
    under a findings-style heading that names no D-/F- id anywhere in the
    item, continuation lines included. Pure, so the shipping decision can
    be called from a test against the documents as they were."""
    lines = text.split('\n')
    found = []
    i = 0
    while i < len(lines):
        m = FINDING_HEADING.match(lines[i])
        if not m or not FINDING_WORDS.search(m.group(2)) \
                or FINDING_EXEMPT.search(m.group(2)):
            i += 1
            continue
        level, heading = len(m.group(1)), m.group(2).strip()
        j = i + 1
        item = None  # (line, title, text)
        def close():
            if item and not ID.search(item[2]):
                found.append((item[0], heading, item[1]))
        while j < len(lines) and not re.match(r'^#{1,%d}\s' % level, lines[j]):
            t = TITLED_ITEM.match(lines[j])
            if t:
                close()
                item = [j + 1, t.group(2), lines[j]]
            elif re.match(r'^\s{0,3}\d+\.\s', lines[j]):
                close()
                item = None          # an untitled item ends the titled one
            elif item is not None and lines[j].strip():
                item[2] += '\n' + lines[j]
            elif item is not None and not lines[j].strip():
                # a blank line ends the item; a later id does not rescue it
                close()
                item = None
            j += 1
        close()
        i = j
    return found


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
        cells = [c.strip() for c in CELL.split(rest)]
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
        if len(cells) != 4:
            # Was "at least 4", which is how a corrupted board stayed green.
            # A script relabelling rows in bulk emitted a doubled separator, so
            # every row it touched grew an empty cell and its state slid one
            # column right. The board rendered wrong, the state was no longer
            # where the schema says it is, and this check passed anyway: five
            # cells cleared "at least 4", and cells[-1] still happened to hold
            # a state word. A row is four cells exactly, and too many is the
            # direction that hides damage rather than announcing it.
            problems.append(
                '%s row has %d cells after the id, expected exactly 4 '
                '(Sev, Task, Repro, State). A pipe inside a cell must be '
                'written \\| or the column it opens shifts every cell after '
                'it' % (ident, len(cells)))
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

    # ---- a titled finding with no id is invisible to everything above ---
    titled = 0
    for rel in tracked_markdown(root):
        for line, heading, title in titled_findings_without_id(read(root, rel)):
            titled += 1
            problems.append(
                '%s:%d "%s" under "%s" is a titled finding with no D-/F- id; '
                'file it, cite the row that already covers it, or say '
                '"not defects" in the heading' % (rel, line, title[:50], heading[:40]))
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

    # ---- every cited Model symbol must actually exist ------------------
    #
    # The docstring above says this check "does not check that a state is
    # TRUE. Nothing can." That is right about states and too modest about
    # CITATIONS. A row that says `Model.BAR_IDLE_DARKEN` is not expressing an
    # opinion; it is naming a symbol, and whether that symbol exists is a fact
    # a script can settle.
    #
    # It had drifted twice before anyone noticed. D-RUNG-3's state cell
    # described a constant and a factor that had been replaced, so a reader
    # sizing the contrast work read numbers that were gone. And an ACCEPTANCE
    # CRITERION graded `Model.pipLuaDispatch`, a function that never existed in
    # any commit -- a test specified against a name nobody had checked.
    sources = {}
    for name in ('Model.js',):
        try:
            sources[name] = read(root, name)
        except IOError:
            pass
    if not sources:
        # A repository with no Model.js and no citations of one is consistent,
        # not broken -- the synthetic fixtures in tests/test_defect_ledger.py
        # are exactly that. Only a repo that CITES symbols it cannot resolve
        # has a problem, so the complaint moves inside the citation scan.
        cited_anywhere = any(
            re.search(r'`Model\.[A-Za-z_]', read(root, rel))
            for rel in tracked_markdown(root))
        if cited_anywhere:
            problems.append(
                'documents cite Model.* symbols but Model.js is unreadable, '
                'so no citation could be checked')
    else:
        blob = '\n'.join(sources.values())
        cited = {}
        for rel in tracked_markdown(root):
            text = read(root, rel)
            for m in re.finditer(r'`Model\.([A-Za-z_][A-Za-z0-9_]*)`', text):
                cited.setdefault(m.group(1), set()).add(rel)
        # `Model.js` is the FILE, named in 22 documents, and `Model.X` is the
        # placeholder this very check is described with. Neither is a citation.
        # Kept as a named, short list rather than a clever pattern: an
        # exception you can read is an exception somebody will notice.
        not_symbols = {'js', 'X'}
        for symbol in sorted(cited):
            if symbol in not_symbols:
                continue
            # A symbol resolves if it is exported, defined, or declared.
            if re.search(r'\b%s\s*[:=]' % re.escape(symbol), blob):
                continue
            if re.search(r'function\s+%s\b' % re.escape(symbol), blob):
                continue
            problems.append(
                'Model.%s is cited in %s and resolves in no source file. '
                'Either the symbol was renamed and the document was not, or '
                'the document names something that never existed'
                % (symbol, ', '.join(sorted(cited[symbol]))))
        print('symbol citations: %d distinct Model.* names checked' % len(cited))

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
