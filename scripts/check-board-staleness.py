#!/usr/bin/env python3
"""Prove no board row reads `open` against a commit that says it was closed.

WHY THIS EXISTS. scripts/check-defect-ledger.py made the board-to-write-up
join a call: every D-/F- id filed in a tracked document has a row in
docs/STATUS.md "## Defects", and every row carries a severity and a state.
It proves the two places AGREE THAT THE ID EXISTS. It does not prove they
agree about anything else, and the state column is still a word a human
copies from one document to another.

On 2026-10-03 five of the nine rows reading `open` had already been fixed in
the code (F-BOARD-1). One of them, F-SINK-10, read `open` for a day after the
commit whose own subject line is "Close F-SINK-10 at the sink". Three more --
D-SAVE-6, D-PLY-23, D-DOC-2 -- read `open` for a week after the commit that
says "the D-SAVE-6 repair", "the D-PLY-23 repair" and "the D-DOC-2 repair" in
its own body. The gate was green through all of it.

WHAT THIS CHECKS, AND WHY IT IS NOT A PROSE ORACLE. It never decides whether
a defect is fixed; nothing in a script can. It decides whether two things the
SAME author wrote contradict each other: a commit message that says a row was
closed, and a board row that still reads a bare `open`. Either half can be
made true, and the author chooses which.

THE CONSTRUCTIONS. Only three, and all three are past-tense assertions in
which the verb governs the id:

    close / closes / closed / closing <ID>    "Close F-SINK-10 at the sink"
    <ID>'s repair, the <ID> repair/fix        "the D-SAVE-6 repair gave ..."
    <ID> is/was (now) closed/fixed            "D-PLY-10 is closed"

Deliberately NOT included in the gate: `repairs (<ID>, <ID>, ...)` and
`fixes <ID>`, the noun forms. They are the only constructions that reach the
fifth stale row of 2026-10-03, D-DOC-1, which no commit message ever names --
and they are also the only ones that cannot tell a finished repair from a
planned one. docs/PLAN-M4.md says "M4-01 The guide renders (medium) -- fixes
D-EPG-2" about work that had not started, and a 2026-09-13 line in the Board
section reads "... fixes verified, 137 cases re-run ..." with an unrelated id
in the next clause. They live in --report instead, which prints and never
fails.

WHAT WAS MEASURED, over the whole project to 64fa114 -- 523 commits, 486 of
them carrying a Defects table -- by driving THESE functions at every commit
with the board as that commit's tree had it:

    this check, as a gate       47 red commits of 486 (9.7%). 5 ids ever
    (commit messages, the       flagged: 4 truly stale (D-SAVE-6, D-PLY-23,
    three verb constructions)   D-DOC-2, F-SINK-10), 1 false alarm
                                (D-PLY-11, red for 4 commits). 4 of the 5
                                rows of 2026-10-03; D-DOC-1 is unreachable.
    adding document prose and   59 red commits of 486 (12.1%). 10 ids:
    the noun forms (--report)   5 true -- all five of 2026-10-03 -- and 5
                                false (D-LIVE-16, D-PLY-10, D-EPG-2,
                                D-PLY-11, D-PLY-12). The fifth catch costs
                                four more false alarms, so it reports.
    the board's own rows        48 red commits, 5 ids: the same 4 as the
    contradicting each other    commit messages plus D-ID-3 (5 commits). No
    (--report, cross-row)       extra catch, more noise, and it needs no git
                                history at all -- see cross_row_claims.
    a state keyword the         0 of the 5 caught. Before 2026-10-03 no
    write-up must carry         write-up and no Repro cell said FIXED for any
    beside the id               of the five, so the convention sees no history
                                and would start from 220 markers nobody has
                                written. It also moves the hand-copy rather
                                than removing it.

THE ONE FALSE ALARM, and the escape hatch it names. D-PLY-11's repair landed
across a wave of commits; 73ccbf6 wrote "the D-PLY-11 repair" and the row
moved four commits later at the merge, the same day. So a repair that is
genuinely in flight CAN turn this red. A row stays exempt by saying something
other than a bare `open` in its state cell -- "open, repair in flight", the
way D-PERF-1 already reads "open, ships with 0.8.0 by ruling" and D-PIP-3
reads "open. Rulings PIP5 and PIP13 keep it ...". That is not appeasing a
checker: it records a fact a reader of the board wants anyway, and it is
visible on the line they read first. Historical cost of that discipline: one
row, once, four commits.

No grace window, because none separates the cases. The false alarm was red
for 4 commits and the smallest true catch, F-SINK-10, for 6 -- and both
happened inside a single day, so a day-based window misses F-SINK-10
entirely. A window tuned on one false alarm is a window fitted to noise.
"""

import io
import os
import re
import subprocess
import sys

IDP = r'[DF]-[A-Z][A-Z0-9]*-[0-9]+'
# Same shapes as scripts/check-defect-ledger.py, for the same reasons: the
# family part may carry digits after its first letter (D-A11Y-1 was invisible
# to the first version of that pattern), and a cell boundary is an UNESCAPED
# pipe, because D-PLY-9's Repro cell legitimately quotes shell containing
# `\|`.
ID = re.compile(r'\b%s\b' % IDP)
ROW = re.compile(r'^\|\s*(%s)\s*\|(.*)$' % IDP)
CELL = re.compile(r'(?<!\\)\|')
LEDGER_FILE = 'docs/STATUS.md'
LEDGER_HEADING = '## Defects'

# A row is eligible only when its state cell is the bare word, with markdown
# emphasis and surrounding space allowed. Everything else -- "open, upstream",
# "open, accepted. Measured on the real lists ...", "**reopened**" -- is a
# state somebody reasoned about in the cell, and this check has nothing to add
# to it. Measured: 6 of the 220 rows at 64fa114 are bare `open`, and all four
# rows this check would have caught were bare `open` at the time.
BARE_OPEN = re.compile(r'^[*_\s]*open[*_\s]*$', re.I)

# The three gate constructions. Each captures the id in group 1.
GATE_SIGNALS = (
    ('close-governs-id',
     re.compile(r'\b(?:close|closes|closed|closing)\b(?:\s+\S+){0,2}?\s+(%s)\b'
                % IDP, re.I)),
    ('past-repair',
     re.compile(r'\b(%s)(?:\'s)?\s+(?:repair|fix)\b' % IDP)),
    ('id-is-fixed',
     re.compile(r'\b(%s)\b\s+(?:is|was)\s+(?:now\s+)?(?:closed|fixed)\b' % IDP,
                re.I)),
)

# Report-only. The noun forms, which do not distinguish tense: `fixes D-EPG-2`
# in a plan is a promise, not a report. REPAIR_NOUN collects every id in the
# rest of the sentence because the one sentence that reaches D-DOC-1 lists
# five ids in a single parenthesis.
REPORT_SIGNALS = GATE_SIGNALS + (
    ('repair-noun', None),          # handled by REPAIR_NOUN below
)
REPAIR_NOUN = re.compile(r'\b(?:repairs|fixes)\b([^.]{0,160})')

# A negation IMMEDIATELY in front of the construction turns the assertion
# inside out: "this does not close D-FOO-1", "rather than close D-FOO-1",
# "would close D-FOO-1". It must be the word before, or the word before that,
# and nothing further: the first version of this guard accepted a negation
# anywhere in the preceding 64 characters and suppressed three legitimate
# claims whose negation governed something else -- "ARCH-P never recorded
# that the D-PLY-11 repair ...", "never the app id (D-PIP-5) The D-PIP-1
# repair ...". A guard that hides a real claim is worse than the cry-wolf it
# was guarding against, because it fails silently.
#
# Narrowed, it suppresses nothing in this project's 523 commit messages or in
# any tracked document, so it is unmeasured on real history and is proven only
# by tests/test_board_staleness.py. It stays because the first message that
# needs it would otherwise read as a lie about a row somebody has to act on.
NEGATION = re.compile(
    r'\b(?:not|never|no|nor|cannot|can\'t|without|would|should|will|must|may'
    r'|instead\s+of|rather\s+than|unable\s+to|deferred)\s+(?:\w+\s+)?$', re.I)
WS = re.compile(r'[ \t\r\n]+')


def flatten(text):
    """One space for every run of whitespace.

    Matching does not need it -- `\\s` and the negated classes used above both
    cross a newline -- but QUOTING does: a claim lifted out of a document and
    printed with its line break inside it breaks the report's one line per
    claim, and the only sentence that reaches D-DOC-1 breaks between
    `D-PLY-23,` and `D-DOC-1`. It also keeps the preceding-words window that
    NEGATION reads from ending at a line break instead of at a word."""
    return WS.sub(' ', text)


def state_cell(cells):
    """The state is the LAST cell, after dropping exactly ONE trailing empty:
    the artifact of the row's closing pipe. Dropping none leaves every state
    reading as the empty string, so every row looks exempt and the whole check
    goes quietly dead -- which is why this is its own function and
    tests/test_board_staleness.py mutates it."""
    if cells and cells[-1] == '':
        cells = cells[:-1]
    return cells[-1] if cells else ''


def board_states(status_text):
    """id -> state cell, for every row of the Defects table. Pure, so the
    shipping parse is what the tests exercise."""
    if LEDGER_HEADING not in status_text:
        return {}
    rest = status_text.split(LEDGER_HEADING, 1)[1]
    end = re.search(r'^## ', rest, re.M)
    ledger = rest[:end.start()] if end else rest
    out = {}
    for line in ledger.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        cells = [c.strip() for c in CELL.split(m.group(2))]
        out.setdefault(m.group(1), state_cell(cells))
    return out


def assertions_in(text, signals=None):
    """id -> (signal name, the matched words) for every past-tense claim in
    `text` that an id was closed. First match per id wins; a later mention
    does not weaken an earlier claim.

    `signals` defaults to GATE_SIGNALS by LOOKUP rather than by a default
    argument, so tests/test_board_staleness.py can mutate the table and see
    this function change behaviour. A default argument binds once at import
    and would have made every mutation case pass against the real regexes."""
    signals = GATE_SIGNALS if signals is None else signals
    flat = flatten(text)
    out = {}
    for name, rx in signals:
        if rx is None:
            continue
        for m in rx.finditer(flat):
            if NEGATION.search(flat[max(0, m.start() - 40):m.start()]):
                continue
            out.setdefault(m.group(1), (name, m.group(0).strip()[:90]))
    if any(n == 'repair-noun' for n, _ in signals):
        for m in REPAIR_NOUN.finditer(flat):
            if NEGATION.search(flat[max(0, m.start() - 40):m.start()]):
                continue
            for mm in ID.finditer(m.group(1)):
                out.setdefault(mm.group(0),
                               ('repair-noun', m.group(0).strip()[:90]))
    return out


def reconcile(states, claims):
    """One tuple per disagreement: an id whose row reads a bare `open` while
    something claims it was closed. `claims` is id -> (signal, where, words).
    An id with no row is not this check's business -- check-defect-ledger.py
    already fails on it, and failing twice for one cause buries the cause."""
    out = []
    for ident in sorted(claims):
        state = states.get(ident)
        if state is None or not BARE_OPEN.match(state):
            continue
        signal, where, words = claims[ident]
        out.append((ident, state.strip(), signal, where, words))
    return out


def _git(root, *args):
    proc = subprocess.run(['git', '-C', root] + list(args),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        return None
    return proc.stdout.decode('utf-8', 'replace')


def commit_claims(root, rev='HEAD'):
    """id -> (signal, "<short sha> <subject>", words) over every commit
    reachable from `rev`, oldest first, so the EARLIEST claim is the one
    reported: that is the commit that should have moved the row."""
    # Record separator 0x1e, field separator 0x1f. A commit body can contain
    # anything else, newlines and pipes included.
    blob = _git(root, 'log', '--reverse', '--format=%x1e%H%x1f%s%x1f%b', rev)
    if blob is None:
        return None
    claims = {}
    for chunk in blob.split('\x1e'):
        if not chunk.strip():
            continue
        parts = chunk.split('\x1f')
        if len(parts) < 3:
            continue
        sha, subject, body = parts[0].strip(), parts[1], parts[2]
        for ident, (signal, words) in assertions_in(
                subject + '\n' + body).items():
            claims.setdefault(
                ident, (signal, '%s %s' % (sha[:7], subject.strip()[:62]),
                        words))
    return claims


def cross_row_claims(status_text):
    """id -> (signal, "the <other id> row", words) for every board row whose
    own text asserts ANOTHER row's repair.

    This is the contradiction F-BOARD-1 calls the sharpest one: D-PLY-24's row
    says it records what D-PLY-23's REPAIR dropped, and sat next to a D-PLY-23
    reading `open` for a week. It needs no git history at all -- two cells of
    one table disagree -- and over this project it reaches the same four rows
    the commit messages do, plus one more false alarm (D-ID-3, five commits).
    Same catch, more noise, so it reports rather than fails.

    A row's claim about ITSELF is not read. Measured: across 523 commits no
    bare-open row's own Repro cell ever asserted its own closure, in any
    construction or as **FIXED** markup, so a check for it could not have gone
    red once and would be decoration."""
    if LEDGER_HEADING not in status_text:
        return {}
    rest = status_text.split(LEDGER_HEADING, 1)[1]
    end = re.search(r'^## ', rest, re.M)
    ledger = rest[:end.start()] if end else rest
    claims = {}
    for line in ledger.splitlines():
        m = ROW.match(line)
        if not m:
            continue
        owner = m.group(1)
        for ident, (signal, words) in assertions_in(
                line, REPORT_SIGNALS).items():
            if ident == owner:
                continue
            claims.setdefault(ident,
                              (signal, '%s\'s own row' % owner, words))
    return claims


def document_claims(root, rev=None):
    """The same, over tracked markdown rather than commit messages, with the
    noun forms added. Report only."""
    if rev is None:
        listing = _git(root, 'ls-files', '-z', '--', '*.md')
        names = [p for p in (listing or '').split('\0') if p]
        reader = lambda rel: _read(root, rel)
    else:
        listing = _git(root, 'ls-tree', '-r', '--name-only', rev)
        names = [p for p in (listing or '').split('\n')
                 if p.endswith('.md')]
        reader = lambda rel: _git(root, 'show', '%s:%s' % (rev, rel)) or ''
    claims = {}
    for rel in names:
        text = reader(rel)
        if rel == LEDGER_FILE and LEDGER_HEADING in text:
            # Inside the Defects table, a row speaks per row and never about
            # itself, so the table is read by cross_row_claims and the prose
            # scan gets the rest of the file.
            for ident, hit in cross_row_claims(text).items():
                claims.setdefault(ident, hit)
            head, rest = text.split(LEDGER_HEADING, 1)
            end = re.search(r'^## ', rest, re.M)
            text = head + (rest[end.start():] if end else '')
        for ident, (signal, words) in assertions_in(
                text, REPORT_SIGNALS).items():
            claims.setdefault(ident, (signal, rel, words))
    return claims


def _read(root, rel):
    with io.open(os.path.join(root, rel), encoding='utf-8') as fh:
        return fh.read()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    report = False
    rev = None
    root = None
    while argv:
        a = argv.pop(0)
        if a == '--report':
            report = True
        elif a == '--at':
            rev = argv.pop(0) if argv else None
        elif a.startswith('--'):
            print('unknown option %s' % a)
            return 2
        else:
            root = a
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # The board comes from the WORKING TREE by default, so moving the row in
    # the diff you are about to commit turns the gate green before the commit
    # exists. --at reads a revision instead, which is how the historical
    # measurement and tests/test_board_staleness.py point it at the tree that
    # was green while five rows were stale.
    try:
        status = (_read(root, LEDGER_FILE) if rev is None
                  else _git(root, 'show', '%s:%s' % (rev, LEDGER_FILE)))
    except IOError:
        status = None
    if not status:
        print('%s is unreadable, so there is no board to reconcile'
              % LEDGER_FILE)
        return 1
    if LEDGER_HEADING not in status:
        print('%s has no "%s" section at all' % (LEDGER_FILE, LEDGER_HEADING))
        return 1
    states = board_states(status)
    if not states:
        print('%s "%s" has no rows, so nothing could be stale'
              % (LEDGER_FILE, LEDGER_HEADING))
        return 1

    claims = commit_claims(root, rev or 'HEAD')
    if claims is None:
        print('git log failed, so no commit message could be read '
              '(is this a git checkout?)')
        return 1
    bare = sorted(i for i, s in states.items() if BARE_OPEN.match(s))
    flags = reconcile(states, claims)

    print('board staleness: %d rows, %d bare-open, %d commit fix-claims, '
          '%d disagreement(s)'
          % (len(states), len(bare), len(claims), len(flags)))

    if report:
        docs = document_claims(root, rev)
        extra = [f for f in reconcile(states, docs)
                 if f[0] not in set(x[0] for x in flags)]
        print('document fix-claims: %d, %d further disagreement(s) '
              '(advisory, this half never fails the gate)'
              % (len(docs), len(extra)))
        for ident, state, signal, where, words in flags + extra:
            print('  %-12s board %-6r  %-16s  %s' % (ident, state, signal,
                                                     where))
            print('               claim: %s' % words)
        if not flags and not extra:
            print('  nothing: every bare-open row is open in every document '
                  'that mentions it')
        return 0

    if flags:
        print('')
        for ident, state, signal, where, words in flags:
            print('  %s reads %r on the board, and %s says it was closed:'
                  % (ident, state, where))
            print('      %s  [%s]' % (words, signal))
        print('')
        print('%d row(s) say open where a commit of ours says closed. Move '
              'the row, or -- if the repair is in flight, or the message '
              'overstated it -- say so in the state cell, which exempts the '
              'row and tells a reader what a bare `open` could not.'
              % len(flags))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
