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

So the join is now a call. Every defect id that appears in any tracked file --
document, script, QML or fixture -- must have a row on the board, and every row
on the board must have a severity and a state. Findings (`F-`) count as much as
defects (`D-`): a lane choosing the gentler word does not make the item stop
needing an owner. An id you file is an id that shows up here until you give it
a state, and "the release shipped" is not a state.

WHAT IT DOES NOT DO. It does not check that a state is TRUE. Nothing can:
"verified fixed" is a claim about a test somebody ran. It checks that the
claim exists and is attributed, which is the part that was silently missing.

WHY THE CORPUS IS EVERY TRACKED FILE AND NOT ONLY MARKDOWN (F-EPG-21). This
check read `git ls-files -- '*.md'` for its first month, so an id cited in a
`.py`, `.js`, `.qml`, `.sh` or fixture file was invisible to it. That is the
same join-by-name failure one layer down: the EPG grader went on announcing a
finding by an id integration had renamed, and nothing could see it because the
citation lived in a script. Measured on d5c2d7a: 47 markdown files against 221
tracked files that decode as UTF-8 (two do not -- a PNG and a gzipped
fixture), and 186 distinct ids cited outside markdown, 88 of them in
`bin/omarchy-iptv`, which has no extension at all. That last number is why the
corpus is "every tracked file that is text" rather than a list of extensions:
the helper is the single most id-dense source file in the tree and an
extension allowlist would have missed it.

Widening it found one real thing, which is the whole argument for the change:
a single id cited in Service.qml as "found live", with no row on the board and
no write-up under that id anywhere. (Not quoted here by id. Every numbered id
written into this file would be a citation like any other, and this file is in
the corpus it scans -- see the note on the marker token below.)

THE EXAMPLE-ID EXEMPTION, and the trade it makes. Widening the corpus pulls in
the ids that this check's own tests and the staleness checker's own narrative
INVENT -- the D-AAA, D-BBB, D-CCC, D-FOO, D-BAR and F-BBB families. They are
fixtures and illustrations, not findings, and a naive widening reports all
twelve of them. (Families, not ids, for the same reason as above.)

The rule chosen is a per-file declaration, because the alternatives both put
the exemption somewhere a reader of the citing file cannot see it:

  * An explicit exclusion of this checker's own test files was rejected. It
    exempts whole FILES rather than ids, so a real finding cited in one of
    them is silently unchecked forever; it lives here rather than where the
    ids are; and the next test file needs an edit to this script, which is the
    shape every allowlist rots into.
  * A reserved example namespace hardcoded here (AAA, BBB, FOO, BAR ...) was
    rejected on a collision this project actually has. `D-BAR` is currently a
    synthetic family in tests/test_board_staleness.py, and `BAR` is a
    perfectly plausible real family HERE: the bar widget is one of the
    plugin's three kinds. A reserved list containing a word from the project's
    own domain is the "unless it looks harmless" shape, and the day somebody
    files a real bar-widget defect the gate goes quiet about it.

So a file declares its own examples, on one line, with the literal token
EXAMPLE-DEFECT-IDS followed by a colon, one or more FAMILIES (prefix and
family, no number), a `--`, and a reason. Written with the token as a
placeholder:

    # <MARKER>: D-AAA F-BBB -- synthetic ids; this file is the ledger check's
    # own test and invents boards to break

The token is a placeholder in that line on purpose: a complete marker in THIS
file would declare families this file does not cite, and the checks below
would rightly report it. A convention that cannot be written in its own
documentation is a convention whose self-check works.

The declaration is honoured only in the file that carries it, and four things
make it hard to hide a real finding behind it. Each can go red:

  1. A declared family that has a board row is reported. A family the board
     tracks is a real family, whatever a marker says about it.
  2. A declared family cited in any markdown file is reported. Markdown is
     where real findings get written up, so an example id has no business
     there -- documentation of the convention uses `D-XXX`, which carries no
     number and is not an id.
  3. A declared family cited in another tracked file that does not itself
     declare it is reported as a leak. The citations of an example family are
     confined to the files that say they are examples.
  4. A declared family the declaring file never cites is reported. A dead
     exemption is how an exemption list rots.
  5. A marker whose family list parses to nothing is reported, rather than
     ignored: otherwise the author reads "no row on the board" about an id
     they believe they exempted, and goes looking in the wrong place.

A marker the parser cannot read -- no `--`, or a numbered id where a family
belongs -- declares NOTHING, which leaves those ids held to the board. That is
the direction that announces itself.

What this does not stop: a deliberate false declaration. Somebody who names a
real finding's family in a marker, with a reason, in the file that cites it,
gets their exemption. That is a lie in a diff, and this check has never
claimed to grade honesty -- the paragraph above about states says the same
thing. What it buys is that the exemption is local, named, reasoned, counted
on every run, and impossible to acquire by accident.
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


def tracked_files(root):
    """Every tracked path, markdown and source alike. The id scan reads this;
    the prose scans below still read tracked_markdown, for reasons stated at
    each one."""
    out = subprocess.run(
        ['git', '-C', root, 'ls-files', '-z'],
        stdout=subprocess.PIPE, check=True).stdout
    return [p for p in out.decode('utf-8').split('\0') if p]


def read(root, rel):
    with io.open(os.path.join(root, rel), encoding='utf-8') as fh:
        return fh.read()


def read_text(root, rel):
    """The file's text, or None when it is not UTF-8 text at all.

    A tracked tree holds binaries -- preview.png, a gzipped EPG fixture -- and
    a decode error on one of those must not take the gate down with a
    traceback. Returning None keeps the SKIP visible: main() counts them and
    prints the count, so a tree where the scan quietly stopped looking at half
    its files cannot read as full coverage."""
    try:
        with io.open(os.path.join(root, rel), encoding='utf-8') as fh:
            return fh.read()
    except (IOError, OSError, UnicodeDecodeError):
        return None


def family_of(ident):
    """`D-AAA-n` -> `D-AAA`. The id pattern guarantees the trailing -<digits>,
    so the split is total. (Written with `n` rather than a digit because a real
    id here would be a citation: this file is inside the corpus it scans.)"""
    return ident.rsplit('-', 1)[0]


# ---- the example-id exemption -------------------------------------------
#
# See the module docstring for the rule and the two alternatives it beat. The
# marker is the token, a colon, the families, `--`, and a reason; the reason is
# mandatory because it is the part a reviewer reads.
# The token is assembled from halves so that the complete literal never
# appears in THIS file. The scan below reads every tracked file, this one
# included, and a complete token here would make the checker carry a marker of
# its own -- one with no family after it, which check 5 would then report. Same
# reason the docstring draws the marker with a placeholder.
_TOKEN = 'EXAMPLE-DEFECT' + '-IDS:'
EXAMPLE_MARKER = re.compile(re.escape(_TOKEN) + r'([^\n]*?)--')
# A family, and NOT a numbered id: `D-AAA-n` on a marker line parses to
# nothing, so a marker that lists ids instead of families exempts nothing and
# the ids stay held to the board.
MARKER_FAMILY = re.compile(r'\b([DF]-[A-Z][A-Z0-9]*)\b(?!-[0-9])')
# A marker-shaped line with no `--` at all. Recognised only so it can be
# reported: silently ignoring it would leave the author reading "no row on the
# board" about an id they thought they had exempted.
MARKER_TOKEN = re.compile(re.escape(_TOKEN))


def example_families(text):
    """(families declared by this text, whether it carries a marker at all).

    Pure, so tests/test_defect_ledger.py exercises the shipping parse rather
    than a copy of this regex."""
    families = set()
    for m in EXAMPLE_MARKER.finditer(text):
        families |= set(MARKER_FAMILY.findall(m.group(1)))
    return families, bool(MARKER_TOKEN.search(text))


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

    # ---- read the corpus: every tracked file that is text ----------------
    markdown = set(tracked_markdown(root))
    texts = {}
    skipped = []
    for rel in tracked_files(root):
        text = read_text(root, rel)
        if text is None:
            skipped.append(rel)
            continue
        if rel == LEDGER_FILE:
            # Mentions INSIDE the ledger do not count as mentions, or every
            # row would justify itself and the orphan check below would be
            # dead. The rest of STATUS.md still counts.
            text = before + after
        texts[rel] = text
    scanned = len(texts)

    if scanned == 0:
        print('defect ledger check scanned no tracked files at all '
              '(is this a git checkout?)')
        return 1

    # ---- which families does each file declare as examples? --------------
    #
    # A marker belongs in a SOURCE file. A document is where real findings get
    # written up, so a document carrying example ids -- or declaring them -- is
    # a contradiction in terms, and documentation of this convention names an
    # unnumbered family, which is not an id and is invisible to the scan.
    examples = {}            # rel -> set of families
    for rel in sorted(texts):
        families, had_marker = example_families(texts[rel])
        if had_marker and rel in markdown:
            problems.append(
                '%s is a document and carries an example-id marker. A document '
                'is where real findings are written up; name an unnumbered '
                'family such as D-XXX, which is not an id, and the marker is '
                'not needed' % rel)
            continue
        if families:
            examples[rel] = families
        elif had_marker:
            problems.append(
                '%s carries an example-id marker whose family list parses to '
                'nothing. List FAMILIES and end them with " -- <reason>": '
                '`D-AAA F-BBB -- why`, not numbered ids and not a bare list. '
                'Until it parses, nothing in that file is exempt' % rel)
    example_families_in_use = set()
    for families in examples.values():
        example_families_in_use |= families

    # ---- every id mentioned anywhere must have a row ---------------------
    #
    # An id whose family THIS file declares is a fixture, not a filing. An id
    # whose family some OTHER file declares is a leak out of that declaration,
    # and in a document it is a real finding wearing an example's name. Each
    # gets exactly one message: reporting one citation twice buries the cause.
    mentions = {}
    exempt = {}              # rel -> set of ids the marker in that file covers
    for rel in sorted(texts):
        own = examples.get(rel, set())
        # set(), not the raw findall: a leak reported once per OCCURRENCE
        # printed the same sentence twice for one citation on the first run.
        for ident in sorted(set(ID.findall(texts[rel]))):
            family = family_of(ident)
            if family in own:
                exempt.setdefault(rel, set()).add(ident)
                continue
            if family in example_families_in_use:
                declarers = sorted(r for r in examples if family in examples[r])
                if rel in markdown:
                    problems.append(
                        '%s cites %s, whose family is declared an EXAMPLE in '
                        '%s. A document is where real findings are written up, '
                        'so either the id is real and the example family must '
                        'be renamed, or the document should name an unnumbered '
                        'family instead'
                        % (rel, ident, ', '.join(declarers)))
                else:
                    problems.append(
                        '%s cites %s, but %s is declared an EXAMPLE family in '
                        '%s and not here. Either this is a real finding and the '
                        'family must be renamed where it is used as an '
                        'example, or this citation is an example too and this '
                        'file must say so'
                        % (rel, ident, family, ', '.join(declarers)))
                continue
            mentions.setdefault(ident, set()).add(rel)

    # ---- the exemption must not cover anything real ----------------------
    for rel in sorted(examples):
        for family in sorted(examples[rel]):
            rows = sorted(i for i in declared if family_of(i) == family)
            if rows:
                problems.append(
                    '%s declares %s as an example family, and the board '
                    'carries %s. A family the board tracks is a real family: '
                    'rename the example, not the finding'
                    % (rel, family, ', '.join(rows)))
            if not any(family_of(i) == family
                       for i in exempt.get(rel, ())):
                problems.append(
                    '%s declares %s as an example family and cites no %s-<n> '
                    'id. Drop the declaration: a dead exemption is how an '
                    'exemption list rots into one nobody reads'
                    % (rel, family, family))

    # ---- a titled finding with no id is invisible to everything above ---
    #
    # Markdown only, deliberately, and unlike the id scan above. The
    # construction it reads -- a numbered item opening with a bold title,
    # under a heading that names findings -- is a document convention. A
    # docstring is not a document section, and a `**bold**` run inside one is
    # a word the author emphasised.
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
            '%s has a board row but appears in no other tracked file. '
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
    #
    # Markdown only, and unlike the id scan, on a MEASUREMENT rather than a
    # preference. Widened to every tracked file on d5c2d7a it reports five
    # unresolved symbols and all five are self-reference: `Model.BAR_IDLE_DARKEN`
    # and `Model.pipLuaDispatch` are the two renamed symbols the paragraph above
    # NARRATES, and `Model.realThing`, `Model.ghostThing` and `Model.anything`
    # are fixtures in tests/test_defect_ledger.py whose job is to be
    # unresolvable. An id citation survives being quoted; a symbol citation
    # inside a story about a symbol that was deleted does not. So the symbol
    # half stays where its corpus is prose that ASSERTS.
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

    # Printed on every run, green included. An exemption nobody sees is an
    # exemption that grows, so the census is part of the output a reader of the
    # gate gets rather than something they have to go looking for.
    print('example-id exemptions: %d file(s), %d family(ies), %d citation(s) '
          'not held to the board'
          % (len(examples), len(example_families_in_use),
             sum(len(v) for v in exempt.values())))
    print('defect ledger: %d rows on the board, %d ids across %d tracked '
          'file(s) (%d markdown, %d not text and skipped)'
          % (len(declared), len(set(mentions) | set(declared)), scanned,
             len(markdown & set(texts)), len(skipped)))
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
