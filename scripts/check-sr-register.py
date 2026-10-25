#!/usr/bin/env python3
"""Prove the SR ruling register and its citations agree (F-M3-20).

WHY. The Sources rulings are a table of `| SRn | ... |` rows in
docs/ARCHITECTURE-SOURCES.md, and every other document, test and script
cites them by id: 40 ids from 35 tracked files on 2026-10-24. That join is
made by a NAME and not by a call, which is CLAUDE.md rule 13's shape, one
register along from the defect ids scripts/check-defect-ledger.py pins: a
row renumbered, retired or never written leaves every citation reading as
current, and a row nobody cites is a decision nothing implements. Found by
the D-SINK-19 docs lane on 2026-10-11; filed 2026-10-12.

WHAT IT CHECKS, over every tracked file (`git ls-files`, binaries skipped
and counted):
  1. every `SRn` cited anywhere resolves to exactly one row of the register;
  2. every row of the register is cited at least once OUTSIDE the
     register's table: a citation from another row's text is the register
     talking to itself, not a document, test or script implementing the
     ruling, so it counts for check 1 (it must resolve) and never for this
     one. The first version counted it, and a row cited only by its
     neighbour read as implemented (P23 recheck, 2026-10-24; one real row
     was in that state on the tree and is now cited where it is kept);
  3. no id has two rows.
The citation corpus is every tracked file, so THIS SCRIPT, ITS TEST AND THE
GATE MUST NOT WRITE A REGISTER ID: a literal in a comment or a docstring is
a citation, and the first version's gate comment and test docstring named
the three rows that were its red proof, which kept them cited after their
real citations were reverted -- the check could not go red for the failure
it was written to catch. The test composes its ids; the gate comment names
line numbers. (scripts/check-defect-ledger.py made the same rule for the
same reason, and refused a whole-file exemption: it would unmark a real
citation in that file forever.)
A row whose text says it was overturned, withdrawn or superseded is PRINTED
with its citation count and is not a problem: an overturned ruling stays
cited as history on purpose (ARCHITECTURE-SOURCES keeps such rows with a
dated marker rather than deleting them), and the reader of the citation is
sent to a row that says so in its first bold sentence. What this cannot see
is a citation that reads an overturned row as current; that is the marker's
job, not this script's.

Registers are a table so a second one (CN in docs/M2-03-CHANNEL-NUMBERS.md,
PO in docs/ARCHITECTURE-PLAYER.md) is one more entry, not a second script;
only SR is checked today, because the others were not graded by the row.

Exit 0 and one summary line ("sr register: R rows, C citations in F files,
O overturned, S binary skipped, 0 problem(s)") when clean; exit 1 with one
`file:line: reason` per problem otherwise. `--root DIR` checks another
tree (the tests build throwaway git repositories). ASCII only (CLAUDE.md
rule 8). Not shipped.
"""
import io
import os
import re
import subprocess
import sys

REGISTERS = [
    {
        "name": "sr",
        "prefix": "SR",
        "file": "docs/ARCHITECTURE-SOURCES.md",
        "row": re.compile(r"^\| (SR(\d+)) \|"),
        "cite": re.compile(r"\bSR(\d+)\b"),
    },
]
OVERTURNED = re.compile(r"overturned|withdrawn|superseded", re.I)


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def tracked_files(root):
    out = subprocess.run(
        ["git", "-C", root, "ls-files", "-z"],
        stdout=subprocess.PIPE, check=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def read_text(root, rel):
    """The file's text, or None when it is not UTF-8 text (preview.png, a
    gzipped fixture). A skip is counted and printed, never silent."""
    try:
        with io.open(os.path.join(root, rel), encoding="utf-8") as fh:
            return fh.read()
    except (IOError, OSError, UnicodeDecodeError):
        return None


def check_register(root, reg, texts):
    problems = []
    rows = {}        # id -> (line number, row text)
    reg_text = texts.get(reg["file"])
    if reg_text is None:
        problems.append("%s: register file missing or unreadable" % reg["file"])
        return problems, rows, {}, 0
    for n, line in enumerate(reg_text.split("\n"), 1):
        m = reg["row"].match(line)
        if not m:
            continue
        ident = m.group(1)
        if ident in rows:
            problems.append("%s:%d: %s has a second row (first at line %d)"
                            % (reg["file"], n, ident, rows[ident][0]))
            continue
        rows[ident] = (n, line)
    cites = {}       # id -> list of "file:line" OUTSIDE the register's table
    in_table = {}    # id -> list of "file:line" inside another row's text
    for rel, text in texts.items():
        if text is None:
            continue
        for n, line in enumerate(text.split("\n"), 1):
            # A register row defines its own id and may mention others;
            # neither is a citation (check 2), but a mention of an id with
            # no row is still a dangling reference (check 1).
            table_row = rel == reg["file"] and reg["row"].match(line) is not None
            for m in reg["cite"].finditer(line):
                ident = reg["prefix"] + m.group(1)
                if table_row:
                    if not (ident in rows and rows[ident][0] == n):
                        in_table.setdefault(ident, []).append("%s:%d" % (rel, n))
                    continue
                cites.setdefault(ident, []).append("%s:%d" % (rel, n))
    mentioned = set(cites) | set(in_table)
    for ident in sorted(mentioned, key=lambda s: int(s[len(reg["prefix"]):])):
        if ident not in rows:
            for where in cites.get(ident, []) + in_table.get(ident, []):
                problems.append("%s: cites %s, which has no row in %s"
                                % (where, ident, reg["file"]))
    for ident in sorted(rows, key=lambda s: int(s[len(reg["prefix"]):])):
        if not cites.get(ident):
            problems.append("%s:%d: %s is cited nowhere outside the register"
                            % (reg["file"], rows[ident][0], ident))
    total = sum(len(v) for v in cites.values())
    return problems, rows, cites, total


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    root = repo_root()
    if argv[:1] == ["--root"]:
        root = os.path.abspath(argv[1])
        argv = argv[2:]
    if argv:
        print("usage: check-sr-register.py [--root DIR]")
        return 2
    files = tracked_files(root)
    texts = {}
    skipped = 0
    for rel in files:
        text = read_text(root, rel)
        if text is None:
            skipped += 1
        texts[rel] = text
    problems = []
    rows_n = cites_n = over_n = 0
    citing_files = set()
    for reg in REGISTERS:
        p, rows, cites, total = check_register(root, reg, texts)
        problems.extend(p)
        rows_n += len(rows)
        cites_n += total
        for sites in cites.values():
            citing_files.update(where.rsplit(":", 1)[0] for where in sites)
        for ident in sorted(rows, key=lambda s: int(s[len(reg["prefix"]):])):
            n, line = rows[ident]
            if OVERTURNED.search(line):
                over_n += 1
                print("%s register: %s mentions overturned/withdrawn/superseded"
                      " at %s:%d and is cited %d time(s)"
                      % (reg["name"], ident, reg["file"], n, len(cites.get(ident, []))))
    cited_files = len(citing_files)
    for line in problems:
        print(line)
    print("sr register: %d rows, %d citations in %d files, %d overturned,"
          " %d binary skipped, %d problem(s)"
          % (rows_n, cites_n, cited_files, over_n, skipped, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
