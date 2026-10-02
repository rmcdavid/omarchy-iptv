"""Prove scripts/check-text-format.py catches what it claims to catch.

CLAUDE.md rule 11: a new check must be seen catching something. Rule 12: a
test that mirrors the scanner's logic can pass while the scanner is broken,
so every case here writes a real QML file to disk and runs the real guard as
a SUBPROCESS -- the way scripts/check.sh runs it -- and reads its exit status
and its report. Nothing in this file re-implements the brace scan.

The guard exists because of D-TEXT-1: a Text with no textFormat renders a
provider's channel name as markup, and the acceptance grep that was supposed
to cover it could only see a format somebody wrote, never a line nobody
wrote (F-TEXT-2). So the cases that matter most are the MISSING line (a) and
the shipping file with the fix removed (h): the guard must name exactly the
element the marketplace reviewer found.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, 'scripts', 'check-text-format.py')

HEAD = 'import QtQuick\n\nItem {\n'
TAIL = '}\n'


def run(args, cwd=None):
    """Run the guard as a subprocess; return (exit status, combined output)."""
    proc = subprocess.run([sys.executable, GUARD] + list(args), cwd=cwd,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          universal_newlines=True)
    return proc.returncode, proc.stdout


class GuardCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='text-format-guard-')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, name, body):
        path = os.path.join(self.tmp, name)
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        with open(path, 'w') as handle:
            handle.write(body)
        return path

    def qml(self, name, block):
        """A minimal QML file holding one Text block; returns (path, line of
        the `Text {` opener, line of the textFormat line or None)."""
        body = HEAD + block + TAIL
        path = self.write(name, body)
        lines = body.split('\n')
        opener = next(i + 1 for i, l in enumerate(lines)
                      if l.strip().startswith('Text {'))
        fmt = next((i + 1 for i, l in enumerate(lines)
                    if l.strip().startswith('textFormat:')), None)
        return path, opener, fmt

    # (a) the finding itself: a Text with no textFormat line at all.
    def test_a_missing_textformat_fails_and_names_the_line(self):
        path, opener, _ = self.qml('A.qml',
                                   '  Text {\n    text: tile.name\n  }\n')
        status, out = run([path])
        self.assertEqual(status, 1, out)
        self.assertIn('%s:%d:' % (path, opener), out)
        self.assertIn('declares no textFormat', out)

    # (b) PlainText passes.
    def test_b_plaintext_passes(self):
        path, _, _ = self.qml(
            'B.qml', '  Text {\n    textFormat: Text.PlainText\n'
                     '    text: tile.name\n  }\n')
        status, out = run([path])
        self.assertEqual(status, 0, out)
        self.assertIn('1 Text block(s) in 1 file(s)', out)

    # (c) StyledText without the exception comment fails.
    def test_c_styledtext_without_exception_fails(self):
        path, _, fmt = self.qml(
            'C.qml', '  Text {\n    textFormat: Text.StyledText\n'
                     '    text: root.hints\n  }\n')
        status, out = run([path])
        self.assertEqual(status, 1, out)
        self.assertIn('%s:%d:' % (path, fmt), out)
        self.assertIn('MARKUP-EXCEPTION', out)

    # (d) StyledText with the exception comment directly above passes.
    def test_d_styledtext_with_exception_directly_above_passes(self):
        path, _, _ = self.qml(
            'D.qml', '  Text {\n'
                     '    // MARKUP-EXCEPTION: own literals only, proven by a test\n'
                     '    textFormat: Text.StyledText\n'
                     '    text: root.hints\n  }\n')
        status, out = run([path])
        self.assertEqual(status, 0, out)

    # (d2) the comment must be DIRECTLY above: a blank line between them, or
    # the comment above some other property, does not count. An exception
    # that can sit anywhere in the block is an exception that outlives the
    # line it was written for.
    def test_d2_exception_comment_not_directly_above_fails(self):
        path, _, _ = self.qml(
            'D2.qml', '  Text {\n'
                      '    // MARKUP-EXCEPTION: own literals only\n'
                      '\n'
                      '    textFormat: Text.StyledText\n'
                      '  }\n')
        status, out = run([path])
        self.assertEqual(status, 1, out)
        path2, _, _ = self.qml(
            'D3.qml', '  Text {\n'
                      '    // MARKUP-EXCEPTION: own literals only\n'
                      '    text: root.hints\n'
                      '    textFormat: Text.StyledText\n'
                      '  }\n')
        status, out = run([path2])
        self.assertEqual(status, 1, out)

    # (d3) an exception comment with no reason is not an exception.
    def test_d3_exception_comment_without_reason_fails(self):
        path, _, _ = self.qml(
            'D4.qml', '  Text {\n'
                      '    // MARKUP-EXCEPTION:\n'
                      '    textFormat: Text.StyledText\n'
                      '  }\n')
        status, out = run([path])
        self.assertEqual(status, 1, out)

    # (e) RichText fails, and so do AutoText spelled out and a bound
    # expression, because none of them is the one value that stops a fetch.
    def test_e_richtext_autotext_and_expressions_fail(self):
        for value in ('Text.RichText', 'Text.AutoText', 'Text.MarkdownText',
                      'root.wall ? Text.PlainText : Text.RichText'):
            path, _, fmt = self.qml(
                'E.qml', '  Text {\n    textFormat: %s\n    text: x\n  }\n'
                % value)
            status, out = run([path])
            self.assertEqual(status, 1, (value, out))
            self.assertIn('%s:%d:' % (path, fmt), out)

    # (f) a "Text {" inside a // comment is not a block, a "{" inside a
    # string literal does not unbalance the real block, and the one real
    # block is still counted and still checked. The braces in strings sit
    # BEFORE the textFormat line on purpose: a scan that counted them would
    # read that line at depth four, or past a closing brace, and report the
    # block as missing its line -- so this case is red against a scanner
    # that does not mask strings, not merely tolerant of one that does.
    def test_f_comments_and_string_braces_do_not_confuse_the_scan(self):
        body = (HEAD +
                '  // Text { in a comment is not a block\n'
                '  /* and neither is Text {\n'
                '     across a block comment */\n'
                '  Text {\n'
                '    text: "a { brace in a string" + \'{\' + `{`\n'
                '    property string why: "// Text { not a comment either"\n'
                '    property string closer: "}"\n'
                '    textFormat: Text.PlainText\n'
                '  }\n'
                '  Rectangle { property string s: "}" }\n' +
                TAIL)
        path = self.write('F.qml', body)
        status, out = run([path])
        self.assertEqual(status, 0, out)
        self.assertIn('1 Text block(s) in 1 file(s)', out)
        # And the same decoys around a block that IS missing the line: the
        # guard names the real opener, not the comment's line.
        body2 = (HEAD +
                 '  // Text {\n'
                 '  Text {\n'
                 '    text: "a { brace in a string"\n'
                 '  }\n' + TAIL)
        path2 = self.write('F2.qml', body2)
        status, out = run([path2])
        self.assertEqual(status, 1, out)
        self.assertIn('%s:5:' % path2, out)
        self.assertNotIn('%s:4:' % path2, out)

    # (f2) a nested Text is its own block: the child's line does not satisfy
    # the parent, and the parent's does not satisfy the child.
    def test_f2_nested_text_blocks_are_checked_separately(self):
        body = (HEAD +
                '  Text {\n'
                '    textFormat: Text.PlainText\n'
                '    Text {\n'
                '      text: inner\n'
                '    }\n'
                '  }\n' + TAIL)
        path = self.write('N.qml', body)
        status, out = run([path])
        self.assertEqual(status, 1, out)
        self.assertIn('%s:6:' % path, out)
        self.assertIn('1 problem(s) in 2 Text block(s)', out)

    # (f3) `Text` is an identifier, not a suffix: a BodyText { or a
    # Foo.Text { is some other type and is not a Text block.
    def test_f3_other_types_ending_in_text_are_not_blocks(self):
        body = (HEAD +
                '  BodyText {\n    text: x\n  }\n'
                '  Foo.Text {\n    text: x\n  }\n'
                '  Text {\n    textFormat: Text.PlainText\n  }\n' + TAIL)
        path = self.write('O.qml', body)
        status, out = run([path])
        self.assertEqual(status, 0, out)
        self.assertIn('1 Text block(s)', out)

    # (f4) a file with no Text block at all proves nothing, and says so.
    def test_f4_no_text_block_at_all_is_a_failure(self):
        path = self.write('Z.qml', HEAD + '  Rectangle { }\n' + TAIL)
        status, out = run([path])
        self.assertEqual(status, 1, out)
        self.assertIn('no Text block at all', out)

    # (g) the real tree: no arguments, from the repository root, exits 0 and
    # reports the shipped files.
    def test_g_real_tree_passes(self):
        status, out = run([], cwd=ROOT)
        self.assertEqual(status, 0, out)
        self.assertIn(' in 3 file(s)', out)

    # (g2) the no-argument list is derived from ALLOWLIST in
    # scripts/release.py, so a shipped file is covered because it ships, not
    # because somebody listed it twice. Proven against a synthetic tree.
    def test_g2_file_list_comes_from_the_release_allowlist(self):
        self.write('scripts/release.py',
                   '"""stub"""\nALLOWLIST = (\n    "manifest.json",\n'
                   '    "Shipped.qml",\n    "Model.js",\n)\n')
        self.write('Shipped.qml', HEAD + '  Text {\n    text: x\n  }\n' + TAIL)
        # A QML file NOT on the allowlist is not scanned, which is the point:
        # the harness fake and the tests are not what ships.
        self.write('Unshipped.qml',
                   HEAD + '  Text {\n    textFormat: Text.PlainText\n  }\n' + TAIL)
        status, out = run(['--root', self.tmp])
        self.assertEqual(status, 1, out)
        self.assertIn('Shipped.qml:4:', out)
        self.assertNotIn('Unshipped', out)
        self.assertIn('1 Text block(s)', out)

    # (g3) a tree with no release.py gets a sentence, not a traceback.
    def test_g3_missing_release_py_is_a_sentence(self):
        status, out = run(['--root', self.tmp])
        self.assertEqual(status, 1, out)
        self.assertIn('cannot derive the shipped QML list', out)
        self.assertNotIn('Traceback', out)

    # (h) rule 11 on the shipping file. The worktree's Guide.qml with the
    # D-TEXT-1 line removed must fail on exactly that element -- the caption
    # bound to tile.name -- and on nothing else. This is the guard seen red
    # against the code that shipped the bug.
    def test_h_shipping_guide_with_the_fix_removed_names_the_caption(self):
        with open(os.path.join(ROOT, 'Guide.qml')) as handle:
            lines = handle.read().split('\n')
        name_idx = [i for i, l in enumerate(lines)
                    if l.strip() == 'text: tile.name']
        self.assertEqual(len(name_idx), 1,
                         'the caption binding is no longer unique')
        name_idx = name_idx[0]
        opener = next(i for i in range(name_idx, -1, -1)
                      if lines[i].strip() == 'Text {')
        fmt = next(i for i in range(name_idx, len(lines))
                   if lines[i].strip() == 'textFormat: Text.PlainText')
        closer = next(i for i in range(name_idx, len(lines))
                      if lines[i].strip() == '}')
        self.assertLess(fmt, closer, 'the fix is not inside the caption block')
        # The untouched file passes, so the one deletion below is the whole
        # difference between green and red; its block count is what the
        # mutated file must still report, so the deletion removed a line
        # and never a block.
        status, out = run([os.path.join(ROOT, 'Guide.qml')])
        self.assertEqual(status, 0, out)
        blocks = re.search(r'guard: (\d+) Text block', out).group(1)
        del lines[fmt]
        path = self.write('Guide.qml', '\n'.join(lines))
        status, out = run([path])
        self.assertEqual(status, 1, out)
        self.assertIn('1 problem(s) in %s Text block(s)' % blocks, out)
        self.assertIn('%s:%d: Text block declares no textFormat'
                      % (path, opener + 1), out)

    # (h2) the same proof for the footerHints exception: strip the
    # MARKUP-EXCEPTION line and the guard names the StyledText line.
    def test_h2_shipping_guide_without_the_exception_names_footerhints(self):
        with open(os.path.join(ROOT, 'Guide.qml')) as handle:
            lines = handle.read().split('\n')
        exc = [i for i, l in enumerate(lines)
               if l.strip().startswith('// MARKUP-EXCEPTION:')]
        self.assertEqual(len(exc), 1, 'expected exactly one exception')
        self.assertEqual(lines[exc[0] + 1].strip(),
                         'textFormat: Text.StyledText')
        del lines[exc[0]]
        path = self.write('Guide.qml', '\n'.join(lines))
        status, out = run([path])
        self.assertEqual(status, 1, out)
        self.assertIn('%s:%d: Text.StyledText without' % (path, exc[0] + 1),
                      out)
        self.assertIn('1 problem(s)', out)


if __name__ == '__main__':
    unittest.main()
