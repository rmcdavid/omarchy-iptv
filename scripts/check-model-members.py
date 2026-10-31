#!/usr/bin/env python3
"""A mistyped `Model.<name>` in QML goes red, read from the QML itself and
not from what qmllint says about it (D-REL-5 round 2, R2; repaired for Qt
6.12, 2026-10-31).

WHY. While the model was the classic script Model.js, qmllint resolved its
members: a real one drew no warning and a nonexistent one drew
`Member "X" not found on type "Model" [missing-property]` naming it, so a
typo in BarWidget.qml read 0 -> 1 warning. Since the model is an ES module
(Model.mjs) qmllint reads none of its exports and EVERY member it reaches
warns, so a typo is one more line in a bucket nobody can tell apart. The
first version of this guard therefore took the member name out of every such
line and judged it. That version had two blind spots, and the second one
emptied it:

  - qmllint stops analysing an expression at its first unresolved member, so
    a `Model.X` inside the arguments of another `Model.Y(...)` was never
    reported: measured on Qt 6.11.2, 82 code positions over BarWidget.qml,
    Service.qml and Guide.qml.
  - qmllint 6.12.0's TEXT output prints only a trailing run of the warnings
    its own `--json` output lists for the same file (measured 2026-10-31:
    BarWidget.qml 7 of 25, Guide.qml 385 of 649, Service.qml 43 of 388,
    Model.spec.qml 17 of 918, the harness shell.qml 4 of 187; the wording of
    a line it does print is unchanged). The guard read the text output, so a
    `Model.zzBogusMember(` at BarWidget.qml:86 drew no line at all and the
    guard passed: it could no longer go red, and nothing said so, because
    every file still yielded a few member lines to judge.

So this reads the QML. A small scanner walks the file as QML/JavaScript
source -- line and block comments, the three string forms (a template's
`${...}` is code and is read), regular-expression literals told apart from a
division by the token before them -- and takes every `Model.<name>` (and
`Model?.<name>`, `Model["<name>"]`) that is code. Each name is judged
against the aggregator's public names (model_files.public_names, the
generated export lines; `split-model.mjs --check` proves the loaded
namespace equals them). The alias is read from the file's own
`import "<...>/Model.mjs" as <Alias>` line rather than assumed. A name that
is not exported is a TypeError on the first call. qmllint is not consulted,
so neither its wording nor what it reaches can empty the check, and the
positions it never reached are judged like every other. Measured on the tree
of 2026-10-31 (dev cc63a49) over the three entry points: the scanner judges
717 references (BarWidget.qml 10, Guide.qml 339, Service.qml 368); qmllint
6.12.0's JSON names 632 of them and nothing else, its text output 118.

It refuses to pass blind, in the forms that fit a reader of source:
  - a file that imports Model.mjs and yields no reference is red (the scanner
    read nothing, or the import is dead and should go);
  - a use of the alias the guard cannot judge -- passed as a value, indexed
    by an expression -- is red, because whatever receives it can call any
    name. One form is reported instead of refused: the alias handed WHOLE as
    an argument to a function of another script the file imports
    (`HarnessLib.entryKey(Model, ...)` in the harness fake), because that
    script is JavaScript this guard does not read and its uses are run with
    the real model in node (scripts/qa-lib-test.sh drives that function);
    the summary line names each such hand-over;
  - a string, template or block comment still open at the end of the file,
    and a newline inside a quoted string, is red: the scanner lost its
    place, and everything after that point would otherwise go unread.
What holds the scanner to the real reading is tests/test_model_members.py:
every Model-member position qmllint's JSON output reports, in each file the
gate lints, must be a position this scanner found.

What it cannot see: a name built at runtime (there is none today, and the
indexing rule above refuses the form), and the model's own parts, which
import each other by name and are judged by node and by `split-model.mjs
--check`. It is not a substitute for the node suite or the QML spec, which
call the model for real.

Usage: check-model-members.py --root ROOT --file FILE [--file FILE ...]
Exit 0 and one summary line per file when every reference is a known name;
1 and one line per problem otherwise. Python 3 standard library only.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model_files  # noqa: E402

# `import "Model.mjs" as Model`, `import "../Model.mjs" as Model`: the alias
# is whatever the file names it, read from the import itself.
IMPORT_MODEL = re.compile(
    r'^[ \t]*import[ \t]+"(?:[^"\n]*/)?Model\.mjs"[ \t]+as[ \t]+(?P<alias>[A-Za-z_$][A-Za-z0-9_$]*)',
    re.M)

# Any other script a QML file imports by alias: `import "harness-lib.js" as
# HarnessLib`. A call into one of these may be handed the model as a value.
IMPORT_SCRIPT = re.compile(
    r'^[ \t]*import[ \t]+"(?P<path>[^"\n]*\.m?js)"[ \t]+as[ \t]+(?P<alias>[A-Za-z_$][A-Za-z0-9_$]*)',
    re.M)

IDENT = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*')
NUMBER = re.compile(
    r'(?:0[xXoObB][0-9a-fA-F_]+|\d[\d_]*\.?[\d_]*(?:[eE][+-]?\d+)?|\.\d[\d_]*(?:[eE][+-]?\d+)?)n?')
# After one of these words a `/` opens a regular expression, not a division.
REGEX_AFTER_WORDS = frozenset((
    'return', 'typeof', 'instanceof', 'in', 'of', 'new', 'delete', 'void',
    'throw', 'case', 'do', 'else', 'yield', 'await'))


class ScanError(Exception):
    """The scanner lost its place in the file: everything after `line` would
    go unread, so the check refuses rather than passing."""

    def __init__(self, line, what):
        Exception.__init__(self, 'line %d: %s' % (line, what))
        self.line = line


class Token(object):
    __slots__ = ('kind', 'text', 'line', 'col')

    def __init__(self, kind, text, line, col):
        self.kind, self.text, self.line, self.col = kind, text, line, col


def tokens(text):
    """The code tokens of one QML file, comments and whitespace dropped.

    kind is 'ident', 'num', 'str' (a quoted string, text is its value),
    'tmpl' (one literal piece of a template), 'regex', or 'punct'. A
    template's `${...}` is tokenized as code in place. line and col are
    1-based, col counted in characters, as qmllint reports them."""
    out = []
    n = len(text)
    i = 0
    line, line_start = 1, 0
    # Each entry is the brace depth at which a template's `${` was opened.
    template_stack = []
    brace_depth = 0

    def regex_allowed():
        if not out:
            return True
        prev = out[-1]
        if prev.kind == 'ident':
            return prev.text in REGEX_AFTER_WORDS
        if prev.kind in ('num', 'str', 'regex'):
            return False
        if prev.kind == 'tmpl':
            # The end of a template is a value; its `${` opening is not.
            return prev.text == '${'
        return prev.text not in (')', ']', '}', '++', '--')

    def scan_template(start, start_line, start_line_start):
        """From just after a backtick or a `}` closing `${`: to the closing
        backtick (returns its index + 1, closed=True) or to `${` (closed=False)."""
        j = start
        ln, ls = start_line, start_line_start
        while j < n:
            c = text[j]
            if c == '\\':
                if j + 1 < n and text[j + 1] == '\n':
                    ln, ls = ln + 1, j + 2
                j += 2
                continue
            if c == '\n':
                ln, ls = ln + 1, j + 1
            elif c == '`':
                return j + 1, True, ln, ls
            elif c == '$' and j + 1 < n and text[j + 1] == '{':
                return j + 2, False, ln, ls
            j += 1
        raise ScanError(start_line, 'a template literal is never closed')

    while i < n:
        c = text[i]
        if c == '\n':
            line, line_start = line + 1, i + 1
            i += 1
            continue
        if c in ' \t\r\f\v\ufeff':
            i += 1
            continue
        col = i - line_start + 1
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            j = text.find('\n', i)
            i = n if j < 0 else j
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '*':
            j = text.find('*/', i + 2)
            if j < 0:
                raise ScanError(line, 'a block comment is never closed')
            line += text.count('\n', i, j)
            k = text.rfind('\n', i, j)
            if k >= 0:
                line_start = k + 1
            i = j + 2
            continue
        if c in '"\'':
            j = i + 1
            value = []
            while True:
                if j >= n:
                    raise ScanError(line, 'a string is never closed')
                d = text[j]
                if d == '\\':
                    if j + 1 < n and text[j + 1] == '\n':
                        line, line_start = line + 1, j + 2
                    value.append(text[j:j + 2])
                    j += 2
                    continue
                if d == '\n':
                    raise ScanError(line, 'a newline inside a quoted string (a multi-line string, '
                                          'or the scanner lost its place)')
                if d == c:
                    break
                value.append(d)
                j += 1
            out.append(Token('str', ''.join(value), line, col))
            i = j + 1
            continue
        if c == '`':
            tok_line = line
            j, closed, line, line_start = scan_template(i + 1, line, line_start)
            out.append(Token('tmpl', '`' if closed else '${', tok_line, col))
            if not closed:
                template_stack.append(brace_depth)
                brace_depth += 1
            i = j
            continue
        if c == '}' and template_stack and template_stack[-1] == brace_depth - 1:
            template_stack.pop()
            brace_depth -= 1
            tok_line = line
            j, closed, line, line_start = scan_template(i + 1, line, line_start)
            out.append(Token('tmpl', '`' if closed else '${', tok_line, col))
            if not closed:
                template_stack.append(brace_depth)
                brace_depth += 1
            i = j
            continue
        if c == '/' and regex_allowed():
            j = i + 1
            in_class = False
            while j < n and text[j] != '\n':
                d = text[j]
                if d == '\\':
                    j += 2
                    continue
                if d == '[':
                    in_class = True
                elif d == ']':
                    in_class = False
                elif d == '/' and not in_class:
                    break
                j += 1
            if j < n and text[j] == '/':
                j += 1
                while j < n and (text[j].isalnum() or text[j] in '_$'):
                    j += 1
                out.append(Token('regex', text[i:j], line, col))
                i = j
                continue
            # No closing slash on this line: not a regular expression.
        m = IDENT.match(text, i)
        if m:
            out.append(Token('ident', m.group(0), line, col))
            i = m.end()
            continue
        m = NUMBER.match(text, i)
        if m and m.end() > i:
            out.append(Token('num', m.group(0), line, col))
            i = m.end()
            continue
        if text.startswith('?.', i) and not (i + 2 < n and text[i + 2].isdigit()):
            out.append(Token('punct', '?.', line, col))
            i += 2
            continue
        if text.startswith('++', i) or text.startswith('--', i):
            out.append(Token('punct', text[i:i + 2], line, col))
            i += 2
            continue
        if c == '{':
            brace_depth += 1
        elif c == '}':
            brace_depth -= 1
        out.append(Token('punct', c, line, col))
        i += 1
    if template_stack:
        raise ScanError(line, 'a template literal\'s ${...} is never closed')
    return out


def aliases(text):
    """The names this file gives Model.mjs in its imports."""
    return sorted(set(m.group('alias') for m in IMPORT_MODEL.finditer(text)))


def script_aliases(text):
    """The names this file gives every OTHER script it imports."""
    model = set(aliases(text))
    return sorted(set(m.group('alias') for m in IMPORT_SCRIPT.finditer(text)
                      if m.group('alias') not in model))


def _handed_to(toks, k, libraries):
    """`Lib.fn` when toks[k] is a whole argument of a call `Lib.fn(..., Model, ...)`
    on another imported script, else None."""
    before = toks[k - 1] if k > 0 else None
    after = toks[k + 1] if k + 1 < len(toks) else None
    if before is None or after is None or before.text not in ('(', ',') or after.text not in (',', ')'):
        return None
    depth = 0
    j = k - 1
    while j >= 0:
        t = toks[j]
        if t.kind == 'punct' and t.text in (')', ']', '}'):
            depth += 1
        elif t.kind == 'punct' and t.text in ('(', '[', '{'):
            if depth == 0:
                break
            depth -= 1
        j -= 1
    if j < 3 or toks[j].text != '(':
        return None
    fn, dot, lib = toks[j - 1], toks[j - 2], toks[j - 3]
    if fn.kind != 'ident' or dot.text != '.' or lib.kind != 'ident' or lib.text not in libraries:
        return None
    if j >= 4 and toks[j - 4].text in ('.', '?.'):
        return None
    return '%s.%s' % (lib.text, fn.text)


def references(text):
    """(refs, handed, unjudged) for one QML file.

    refs are (line, col, name) for every `<Alias>.<name>`, `<Alias>?.<name>`
    and `<Alias>["<name>"]` in code, col at the name as qmllint reports it.
    handed are (line, col, 'Lib.fn') for every place the alias is passed whole
    as an argument to a function of another script the file imports: the
    members that script uses are judged where that script is run, not here.
    unjudged are (line, col, why) for every other use of the alias in code.
    Raises ScanError when the scanner loses its place."""
    names = set(aliases(text))
    libraries = set(script_aliases(text))
    refs, handed, unjudged = [], [], []
    if not names:
        return refs, handed, unjudged
    toks = tokens(text)
    for k, t in enumerate(toks):
        if t.kind != 'ident' or t.text not in names:
            continue
        prev = toks[k - 1] if k > 0 else None
        if prev is not None and prev.kind == 'punct' and prev.text in ('.', '?.'):
            continue  # someone else's property that happens to share the name
        if prev is not None and prev.kind == 'ident' and prev.text == 'as':
            continue  # the import's own declaration of the alias
        nxt = toks[k + 1] if k + 1 < len(toks) else None
        after = toks[k + 2] if k + 2 < len(toks) else None
        if nxt is not None and nxt.kind == 'punct' and nxt.text in ('.', '?.') \
                and after is not None and after.kind == 'ident':
            refs.append((after.line, after.col, after.text))
            continue
        if nxt is not None and nxt.kind == 'punct' and nxt.text == '[' and after is not None \
                and after.kind == 'str' and k + 3 < len(toks) and toks[k + 3].text == ']':
            refs.append((after.line, after.col + 1, after.text))
            continue
        callee = _handed_to(toks, k, libraries)
        if callee is not None:
            handed.append((t.line, t.col, callee))
            continue
        why = ('indexed by an expression' if nxt is not None and nxt.text == '['
               else 'used as a value, so whatever receives it can call any name')
        unjudged.append((t.line, t.col, why))
    return refs, handed, unjudged


def judge(qml_text, names, label):
    """(problems, refs, handed) for one QML file: every complaint, the
    references it judged and the hand-overs to another script it did not."""
    known = set(names)
    alias_names = aliases(qml_text or '')
    if not alias_names:
        return [], [], []
    try:
        refs, handed, unjudged = references(qml_text)
    except ScanError as error:
        return ['%s: the scanner lost its place at %s, so nothing after it is judged; '
                'fix the source or teach the scanner the form' % (label, error)], [], []
    problems = ['%s:%d:%d: `Model.%s` is not a name Model.mjs exports (a TypeError on the first call)'
                % (label, line, col, name) for line, col, name in refs if name not in known]
    problems += ['%s:%d:%d: Model.mjs is %s; this guard cannot judge that use'
                 % (label, line, col, why) for line, col, why in unjudged]
    if not refs:
        problems.append('%s imports Model.mjs as %s and the scanner found no reference to it: '
                        'it read nothing, or the import is dead; re-measure before trusting it'
                        % (label, ', '.join(alias_names)))
    return problems, refs, handed


def problems_for(qml_text, names, label):
    """Every complaint about one QML file, and how many references it judged."""
    problems, refs, _ = judge(qml_text, names, label)
    return problems, len(refs)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', required=True)
    ap.add_argument('--file', required=True, action='append',
                    help='a QML file to judge (repeatable)')
    args = ap.parse_args(argv)
    try:
        names = model_files.public_names(args.root)
    except model_files.ModelLayoutError as error:
        print('model members: the model is unreadable: %s' % error)
        return 1
    status = 0
    summaries = []
    for path in args.file:
        try:
            with open(path, encoding='utf-8') as fh:
                qml_text = fh.read()
        except (OSError, UnicodeDecodeError) as error:
            print('model members: %s is unreadable: %s' % (path, error))
            status = 1
            continue
        label = os.path.basename(path)
        problems, refs, handed = judge(qml_text, names, label)
        for p in problems:
            print(p)
        if problems:
            status = 1
        else:
            summary = ('%s: %d Model reference(s) in code, each a name Model.mjs exports (%d names)'
                       % (label, len(refs), len(names)))
            if handed:
                summary += '; handed whole to %s, judged where that runs' % ', '.join(
                    '%s at %d' % (callee, line) for line, _, callee in handed)
            summaries.append(summary)
    if status == 0:
        for s in summaries:
            print(s)
    return status


if __name__ == '__main__':
    sys.exit(main())
