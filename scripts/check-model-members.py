#!/usr/bin/env python3
"""A mistyped `Model.<name>` in QML goes red, although qmllint cannot say so
any more (D-REL-5, round 2, R2).

WHY. While the model was the classic script Model.js, qmllint resolved its
members: a real one drew no warning and a nonexistent one drew
`Member "X" not found on type "Model" [missing-property]` naming it, so a
typo in BarWidget.qml read 0 -> 1 warning. Since the model is an ES module
(Model.mjs), qmllint 6.11 reads none of its exports and EVERY member warns --
257 in Service.qml alone -- so a typo is one more line in a bucket nobody can
tell apart. The first comment written about this said no signal was lost;
that was measured false by the round-1 live lens.

So this reads qmllint's output for one file on stdin, takes the member name
out of every `not found on type "Model"` line, and refuses any name that is
not one of the aggregator's public names (model_files.public_names, the
generated export lines; `split-model.mjs --check` proves the loaded namespace
equals them). A real member's warning is expected noise; an unknown one is a
call that throws a TypeError at runtime.

What it CANNOT see, measured 2026-10-12 on Qt 6.11.2: a member qmllint never
reaches. qmllint stops analysing an expression at its first unresolved
member, so a `Model.X` used as an argument of another `Model.Y(...)` call,
or inside a binding it gives up on earlier, is not reported at all. Over
BarWidget.qml, Service.qml and Guide.qml the tip reaches 528 code positions
and misses 82; the classic Model.js reached exactly ONE of those 82
(Guide.qml:403, the third argument of Model.captionAlpha). So this restores
the old signal at every position but that kind, and is not a substitute for
the node suite or the QML spec, which call the model for real.

It also refuses to pass blind: a file that imports "Model.mjs" and yields no
Model-member line at all means qmllint's wording changed or it began to
resolve ES modules, and either way this check is no longer reading anything.

Usage: qmllint ... FILE | check-model-members.py --root ROOT --file FILE
Exit 0 and one summary line when every member is known; 1 and one line per
unknown member otherwise. Python 3 standard library only.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model_files  # noqa: E402

MEMBER_LINE = re.compile(
    r'^Warning: (?P<where>.*?:\d+:\d+): Member "(?P<name>[^"]+)" not found on type "Model" '
    r'\[missing-property\]\s*$', re.M)
IMPORTS_MODEL = re.compile(r'^\s*import\s+"(?:[^"]*/)?Model\.mjs"\s+as\s+Model\b', re.M)


def member_lines(output):
    """(where, name) for every Model-member warning in one qmllint output."""
    return [(m.group('where'), m.group('name')) for m in MEMBER_LINE.finditer(output)]


def problems_for(output, names, qml_text, label):
    """Every complaint about one file's lint output: unknown members, or a
    file that imports the model and produced no member line to judge."""
    known = set(names)
    lines = member_lines(output)
    problems = ['%s: `Model.%s` is not a name Model.mjs exports (a TypeError on the first call)'
                % (where, name) for where, name in lines if name not in known]
    if not lines and IMPORTS_MODEL.search(qml_text or ''):
        problems.append('%s imports Model.mjs and qmllint reported no Model member at all: '
                        'its wording changed or it now resolves ES modules, so this check '
                        'reads nothing; re-measure before trusting it' % label)
    return problems, len(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', required=True)
    ap.add_argument('--file', required=True, help='the QML file qmllint was run on')
    args = ap.parse_args(argv)
    try:
        names = model_files.public_names(args.root)
    except model_files.ModelLayoutError as error:
        print('model members: the model is unreadable: %s' % error)
        return 1
    try:
        with open(args.file, encoding='utf-8') as fh:
            qml_text = fh.read()
    except OSError as error:
        print('model members: %s is unreadable: %s' % (args.file, error))
        return 1
    problems, count = problems_for(sys.stdin.read(), names, qml_text, os.path.basename(args.file))
    for p in problems:
        print(p)
    if problems:
        return 1
    print('%d Model-member line(s), each a name Model.mjs exports (%d names)' % (count, len(names)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
