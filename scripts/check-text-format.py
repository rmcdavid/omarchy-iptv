#!/usr/bin/env python3
"""Prove every shipped Text element says how it renders its text.

WHY THIS EXISTS (D-TEXT-1, filed 2026-10-02 against the shipped 2d3cee3). A
QML `Text` whose `textFormat` is left unset renders under Qt's `AutoText`
default, which sniffs the string for markup and lays it out as rich text when
it finds any. The logo-wall caption bound `text: tile.name` -- a channel
name, which the playlist provider writes -- and set no textFormat, so a name
carrying `<img src="http://...">` made the omarchy-shell process fetch that
URL at text layout, on creation, whether or not the tile was ever visible.
Measured, not reasoned: `Text.StyledText` and `Text.RichText` fetch too, and
neither escaping nor URL redaction closes it. `Text.PlainText` is the only
stop.

Across the three shipped QML files, forty-two Text elements already declared
PlainText (forty in Guide.qml, two in BarWidget.qml), one declared
StyledText (the footer hint line), and six in Guide.qml declared nothing:
five that render the plugin's own glyphs, and the caption, the one bound to
a provider string. That is the 49 blocks the first run of this check
counted. It was found by a marketplace reviewer, because
the acceptance row that was supposed to cover this (SRC-SEC-13) was graded
by a grep for `StyledText|RichText` -- a grep that can see a format somebody
wrote and cannot see a line nobody wrote (F-TEXT-2, CLAUDE.md rule 14). This
check is the call that replaces that grep: it finds every `Text {` block in
every shipped QML file and refuses a missing line, not only a wrong one. The
glyph elements say PlainText now too, because a rule with "unless it looks
harmless" in it is a rule the next caption is written under.

THE RULE. Inside every `Text {` or `Label {` block, at the block's own depth
(a nested child is its own block), there must be exactly one `textFormat:`
line, and:
  * `Text.PlainText` passes;
  * `Text.StyledText` passes ONLY when the line directly above it is a
    comment of the form `// MARKUP-EXCEPTION: <reason>` -- the one shipped
    case is the footer hint line, whose markup is composed from the plugin's
    own literals and whose freedom from user strings tests/Model.test.js
    proves under the label "F-TEXT-2";
  * `Text.AutoText`, `Text.RichText`, `Text.MarkdownText`, a bound
    expression, a StyledText without the exception comment, and a missing
    line all fail, each reported as file:line with the reason.
A QtQuick Controls `Label` is a `Text` subclass and inherits the AutoText
default, so a `Label {` block is held to the same rule and is counted as a
Text block in the report ("N Text block(s)" includes the Labels; the gate
parses that wording). Before this, a Label passed the gate untouched:
measured on a BarWidget.qml copy with `Label { text: root.nowPlayingName }`
appended, exit 0.

A QUALIFIED QTQUICK IMPORT IS REFUSED. `import QtQuick as QQ` (or
`import QtQuick.Controls 2.15 as QQC`) lets the file write `QQ.Text {`,
which this scan skips as some other type -- silently, which is the one
failure mode a guard may not have. So any `import QtQuick...  as <Alias>` in
a scanned file is reported as a problem with the import's line: the scan
reads unqualified `Text` and `Label` only, and the file must import them
unqualified. No shipped file uses a qualified QtQuick import today.
`import "Model.js" as Model` is a JavaScript import, not a QtQuick one, and
is not refused.

WHAT IT SCANS. With no arguments, the `.qml` entries of ALLOWLIST in
scripts/release.py -- what main ships -- so a new shipped QML file is covered
the day it is added to the artifact and never by somebody remembering. The
list is read with `ast`, not by importing release.py, so this check runs no
code from the file it reads. For its own tests the check also accepts an
explicit list of QML files, and `--root DIR` points the ALLOWLIST derivation
at another tree.

HOW IT READS QML. The scan is brace-aware and masks `//` and `/* */`
comments, the insides of string literals (double-quoted, single-quoted and
template) and the insides of regular-expression literals before it counts a
brace or matches `Text {`, so a `Text {` quoted in a comment is not a block
and a `{` inside a bound string does not unbalance the one that is. `Text`
must stand alone as an identifier: a `BodyText {` or `Foo.Text {` is some
other type and is not inspected (and the qualified-import refusal above is
what keeps `Foo.Text` from being a hiding place).

A regex literal is recognised the way a JavaScript tokenizer does it, by
what precedes the slash: a `/` that is the first code on its line, or whose
previous non-blank code character is one of `: = ( , [ { ; ! ? & |`, opens a
literal; a `/` after anything else (an identifier, a number, `)` or `]`) is
division. The literal runs to the next unescaped `/` outside a `[...]`
class, or to the end of the line. Without this, `property var re: /"/` left
the quote open and masked the rest of its line, so a `Text {` on that line
was unseen. KNOWN LIMITATION: a slash after `)` is always read as division,
so a literal in a position such as `if (x) /"/.test(y)` is not recognised
and its quote masks the rest of that line; no shipped file writes one.

Python 3 standard library only. ASCII only.
"""

import ast
import os
import re
import sys

EXCEPTION_RE = re.compile(r'^//\s*MARKUP-EXCEPTION:\s*\S')
# Text and its Controls subclass Label; both default to AutoText.
TEXT_OPEN_RE = re.compile(r'(?<![A-Za-z0-9_.])(?:Text|Label)\s*\{')
# `import QtQuick as QQ`, `import QtQuick.Controls 2.15 as QQC`: a QtQuick
# module (bare or dotted) with an optional version and an `as` alias. Matched
# against the masked source, where a JavaScript import's quoted path has
# been blanked and cannot read as QtQuick.
QUALIFIED_IMPORT_RE = re.compile(
    r'^[ \t]*import[ \t]+(QtQuick(?:\.[A-Za-z0-9_]+)*)'
    r'(?:[ \t]+[0-9][0-9.]*)?[ \t]+as[ \t]+([A-Za-z_][A-Za-z0-9_]*)',
    re.MULTILINE)
# What may precede a `/` that opens a regex literal: a position where
# JavaScript cannot be dividing. Anything else (identifier, number, `)`,
# `]`) makes the slash a division operator.
REGEX_PRECEDERS = set(':=(,[{;!?&|')
TEXT_FORMAT_RE = re.compile(r'(?<![A-Za-z0-9_.])textFormat\s*:\s*([^\n]*)')
PLAIN = 'Text.PlainText'
STYLED = 'Text.StyledText'


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def allowlisted_qml(root):
    """The .qml entries of ALLOWLIST in <root>/scripts/release.py, read as a
    literal with ast so nothing in release.py runs."""
    path = os.path.join(root, 'scripts', 'release.py')
    with open(path, 'r', encoding='utf-8') as handle:
        tree = ast.parse(handle.read(), path)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if 'ALLOWLIST' not in names:
            continue
        entries = ast.literal_eval(node.value)
        return [os.path.join(root, e) for e in entries if e.endswith('.qml')]
    raise ValueError('%s has no ALLOWLIST assignment' % path)


def regex_opens_at(out):
    """Whether a `/` appended now would open a regex literal, judged by the
    last non-blank code character already masked on the current line: none
    (line start) or one of REGEX_PRECEDERS means a literal, anything else
    means division."""
    j = len(out) - 1
    while j >= 0:
        token = out[j]  # one source character, masked to 1 or 2 chars
        if '\n' in token:
            return True
        code = token.strip()
        if code:
            return code[-1] in REGEX_PRECEDERS
        j -= 1
    return True


def mask(source):
    """Return source with comment bodies, string-literal bodies and
    regex-literal bodies replaced by spaces, newlines kept, so offsets and
    line numbers still line up.

    The delimiters themselves survive (a quote stays a quote, a slash a
    slash) so a masked literal is still visibly a literal; only what is
    INSIDE them is blanked.
    """
    out = []
    i = 0
    n = len(source)
    state = 'code'
    quote = ''
    in_class = False
    while i < n:
        c = source[i]
        nxt = source[i + 1] if i + 1 < n else ''
        if state == 'code':
            if c == '/' and nxt == '/':
                state = 'line'
                out.append('  ')
                i += 2
                continue
            if c == '/' and nxt == '*':
                state = 'block'
                out.append('  ')
                i += 2
                continue
            if c == '/' and regex_opens_at(out):
                state = 'regex'
                in_class = False
                out.append(c)
                i += 1
                continue
            if c in ('"', "'", '`'):
                state = 'string'
                quote = c
                out.append(c)
                i += 1
                continue
            out.append(c)
            i += 1
            continue
        if state == 'line':
            if c == '\n':
                state = 'code'
                out.append(c)
            else:
                out.append(' ')
            i += 1
            continue
        if state == 'block':
            if c == '*' and nxt == '/':
                state = 'code'
                out.append('  ')
                i += 2
                continue
            out.append('\n' if c == '\n' else ' ')
            i += 1
            continue
        if state == 'regex':
            if c == '\\' and nxt not in ('', '\n'):
                out.append('  ')
                i += 2
                continue
            if c == '\n':
                # A regex literal cannot span lines; an unterminated one
                # ends with its line rather than swallowing the file.
                state = 'code'
                out.append(c)
                i += 1
                continue
            if c == '[':
                in_class = True
            elif c == ']':
                in_class = False
            elif c == '/' and not in_class:
                state = 'code'
                out.append(c)
                i += 1
                continue
            out.append(' ')
            i += 1
            continue
        # string
        if c == '\\' and nxt != '':
            out.append('  ' if nxt != '\n' else ' \n')
            i += 2
            continue
        if c == quote:
            state = 'code'
            out.append(c)
            i += 1
            continue
        if c == '\n' and quote != '`':
            # An unterminated single-line string: give up on it at the line
            # end rather than swallow the rest of the file.
            state = 'code'
        out.append('\n' if c == '\n' else ' ')
        i += 1
    return ''.join(out)


def line_of(text, offset):
    return text.count('\n', 0, offset) + 1


def qualified_imports(masked):
    """Every qualified QtQuick import in the masked source as
    (line, module, alias)."""
    return [(line_of(masked, m.start()), m.group(1), m.group(2))
            for m in QUALIFIED_IMPORT_RE.finditer(masked)]


def text_blocks(masked):
    """Every `Text {` or `Label {` block in the masked source as
    (open_line, segments), where segments are (start, end) offsets of the
    block's own-depth code, excluding nested child blocks."""
    blocks = []
    for m in TEXT_OPEN_RE.finditer(masked):
        start = m.end()
        depth = 1
        segments = []
        seg_start = start
        i = start
        n = len(masked)
        while i < n and depth > 0:
            c = masked[i]
            if c == '{':
                if depth == 1:
                    segments.append((seg_start, i))
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 1:
                    seg_start = i + 1
                elif depth == 0:
                    segments.append((seg_start, i))
            i += 1
        if depth != 0:
            # Unbalanced: report it as a block with no properties, so it is a
            # failure rather than a silent skip.
            segments.append((seg_start, n))
        blocks.append((line_of(masked, m.start()), segments))
    return blocks


def check_file(path):
    """Return (block_count, problems) for one QML file; each problem is a
    (line, reason) tuple."""
    with open(path, 'r', encoding='utf-8') as handle:
        source = handle.read()
    masked = mask(source)
    lines = source.split('\n')
    problems = []
    for line, module, alias in qualified_imports(masked):
        problems.append((line,
                         'qualified import "%s as %s" would let a "%s.Text {" '
                         'or "%s.Label {" evade this guard, which scans '
                         'unqualified Text and Label only; import it '
                         'unqualified' % (module, alias, alias, alias)))
    blocks = text_blocks(masked)
    for open_line, segments in blocks:
        found = []
        for seg_start, seg_end in segments:
            for m in TEXT_FORMAT_RE.finditer(masked, seg_start, seg_end):
                found.append((line_of(masked, m.start()), m.group(1).strip()))
        if not found:
            problems.append((open_line,
                             'Text block declares no textFormat (AutoText by '
                             'default renders a provider string as markup, '
                             'D-TEXT-1); add textFormat: Text.PlainText'))
            continue
        if len(found) > 1:
            problems.append((found[1][0],
                             'Text block at line %d declares textFormat more '
                             'than once' % open_line))
            continue
        fmt_line, value = found[0]
        # The masked value has had any trailing comment blanked; the real
        # line is what a reader sees.
        value = value.split(';')[0].strip()
        if value == PLAIN:
            continue
        if value == STYLED:
            above = lines[fmt_line - 2].strip() if fmt_line >= 2 else ''
            if EXCEPTION_RE.match(above):
                continue
            problems.append((fmt_line,
                             'Text.StyledText without a "// MARKUP-EXCEPTION: '
                             '<reason>" comment on the line directly above'))
            continue
        problems.append((fmt_line,
                         'textFormat is %r; only Text.PlainText passes '
                         '(or Text.StyledText under a MARKUP-EXCEPTION '
                         'comment)' % value))
    return len(blocks), problems


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    root = None
    files = []
    i = 0
    while i < len(argv):
        if argv[i] == '--root':
            if i + 1 >= len(argv):
                print('--root needs a directory')
                return 2
            root = argv[i + 1]
            i += 2
            continue
        files.append(argv[i])
        i += 1
    if not files:
        root = root or repo_root()
        try:
            files = allowlisted_qml(root)
        except (IOError, OSError, ValueError, SyntaxError) as error:
            print('cannot derive the shipped QML list from %s: %s'
                  % (os.path.join(root, 'scripts', 'release.py'), error))
            return 1
    total_blocks = 0
    total_problems = 0
    report = []
    for path in files:
        if not os.path.isfile(path):
            report.append('%s: not a file' % path)
            total_problems += 1
            continue
        count, problems = check_file(path)
        total_blocks += count
        for line, reason in problems:
            total_problems += 1
            report.append('%s:%d: %s' % (os.path.relpath(path, root) if root
                                          else path, line, reason))
    if total_blocks == 0 and total_problems == 0:
        print('text format guard scanned %d file(s) and found no Text block '
              'at all; a scan that checks nothing proves nothing'
              % len(files))
        return 1
    if total_problems:
        print('text format guard: %d problem(s) in %d Text block(s) across %d '
              'file(s)' % (total_problems, total_blocks, len(files)))
        for line in report:
            print('  ' + line)
        return 1
    print('text format guard: %d Text block(s) in %d file(s), every one '
          'declares Text.PlainText or an excepted Text.StyledText'
          % (total_blocks, len(files)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
