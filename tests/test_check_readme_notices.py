"""Prove scripts/check-readme-notices.py catches what it claims to catch
(F-HARNESS-35).

CLAUDE.md rule 11: every case starts from a tree that PASSES, breaks one
decision, and asserts the real checker's main() goes red and names the
quote. Rule 12: nothing here re-implements the extraction or the join; each
case runs the shipping script, in a throwaway tree for the literal rules and
against THIS tree for the composer, which needs the real Model.mjs and its
constants.

Seen red on the tree: on a9d20f9 the checker names README.md:767
`Playlist warning:` and README.md:776 `Guide data warning:` (2 problems over
28 quotes) -- the plugin never shows either prefix alone, so the README now
quotes them elided, `Playlist warning: ...`, and the tree reads 0 problems.
"""
import io
import os
import shutil
import sys
import tempfile
import unittest
import importlib.util

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = os.path.join(ROOT, 'scripts', 'check-readme-notices.py')
_s = importlib.util.spec_from_file_location('check_readme_notices', _spec)
checker = importlib.util.module_from_spec(_s)
_s.loader.exec_module(checker)

RELEASE = (
    'ALLOWLIST = (\n'
    '    "Guide.qml",\n'
    '    "model/view.mjs",\n'
    '    "bin/omarchy-iptv",\n'
    '    "bin/helper/01-core.py",\n'
    ')\n'
)
GUIDE = (
    'import QtQuick\n'
    'Item {\n'
    '  // The comment says `Not a notice` and that is not copy\n'
    '  property string a: "Set a playlist first"\n'
    "  property string b: 'Bar setting ignored'\n"
    '  property string url: "http://host.test/path"  // a URL is not a comment\n'
    '}\n'
)
VIEW = (
    'var SEP = " \\u00b7 "\n'
    'var FULL = "Sources is full" + SEP + "remove one first"\n'
    'var PREFIX = "Playlist warning: "\n'
    '/* "In a block comment" */\n'
)
STUB = '#!/usr/bin/env python3\n"""Docstring: Not copy either."""\nMSG = "Timed out"\n'
PART = 'def f():\n    """Helper docstring says Source too large but ships nothing."""\n    return "Source not found"\n'
README = (
    '# Plugin\n\n'
    'The footer says `Set a playlist first` and the card says `Bar setting ignored`.\n'
    'A load prints `Playlist warning: ...` after it; `Timed out` and `Source not found` too.\n'
    'Keys: `SUPER + SHIFT + T`; by hand: `OMARCHY_IPTV_URL=... python3 ...`.\n'
    '```\n'
    'echo `Inside a fence` is a command\n'
    '```\n'
)


class SyntheticTree(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='readme-notices-')
        self.addCleanup(shutil.rmtree, self.dir, True)
        for rel in ('scripts', 'model', 'bin/helper'):
            os.makedirs(os.path.join(self.dir, rel))
        self.write('scripts/release.py', RELEASE)
        self.write('Guide.qml', GUIDE)
        self.write('model/view.mjs', VIEW)
        self.write('bin/omarchy-iptv', STUB)
        self.write('bin/helper/01-core.py', PART)
        self.write('README.md', README)

    def write(self, rel, text):
        with io.open(os.path.join(self.dir, rel), 'w', encoding='utf-8') as fh:
            fh.write(text)

    def run_checker(self, *docs, **kw):
        root = kw.get('root', self.dir)
        out = io.StringIO()
        real = sys.stdout
        sys.stdout = out
        try:
            rc = checker.main(['--root', root] + list(docs))
        finally:
            sys.stdout = real
        return rc, out.getvalue()

    def test_clean_readme_is_green_with_every_skip_printed(self):
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        self.assertIn('README.md:5: skipped `SUPER + SHIFT + T` (a key chord)', out)
        self.assertIn('README.md:5: skipped `OMARCHY_IPTV_URL=... python3 ...` (a command)', out)
        self.assertIn('readme notices: 7 quote(s) in 1 file(s), 5 joined (4 exact, 0 composed, 1 elided), 2 skipped, 4 shipped code file(s), 0 composed string(s), 0 problem(s)', out)

    def test_a_quote_the_plugin_no_longer_shows_is_red_and_named(self):
        self.write('Guide.qml', GUIDE.replace('"Set a playlist first"', '"Add a playlist first"'))
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('README.md:3: `Set a playlist first` matches no shipped string', out)
        self.assertIn('1 problem(s)', out)

    def test_a_comment_is_not_copy(self):
        # The quote exists only in a QML line comment, a JS block comment,
        # the stub's docstring and a part's docstring: none of them ships.
        self.write('README.md', README + 'Also `Not a notice`, `In a block comment`, `Not copy either`, `Source too large`.\n')
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        for q in ('Not a notice', 'In a block comment', 'Not copy either', 'Source too large'):
            self.assertIn('README.md:9: `%s` matches no shipped string' % q, out)
        self.assertIn('4 problem(s)', out)

    def test_a_url_inside_a_string_is_not_a_comment_start(self):
        self.write('README.md', README + 'The string `Bar setting ignored` sits above a URL literal.\n')
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)

    def test_a_prefix_without_an_ellipsis_does_not_join(self):
        self.write('README.md', README.replace('`Playlist warning: ...`', '`Playlist warning:`'))
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('README.md:4: `Playlist warning:` matches no shipped string', out)

    def test_an_elided_quote_nothing_starts_with_is_red(self):
        self.write('README.md', README.replace('`Playlist warning: ...`', '`Player warning: ...`'))
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('README.md:4: `Player warning: ...` elided, and nothing shipped starts with `Player warning:`', out)

    def test_a_unicode_ellipsis_elides_too(self):
        self.write('README.md', README.replace('`Playlist warning: ...`', '`Playlist warning: …`'))
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)

    def test_a_fenced_span_is_not_read(self):
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        self.assertNotIn('Inside a fence', out)

    def test_a_missing_document_is_red(self):
        rc, out = self.run_checker('docs/NOPE.md')
        self.assertEqual(rc, 1, out)
        self.assertIn('docs/NOPE.md: not found', out)

    def test_a_decoded_escape_joins_the_readme_glyph(self):
        # VIEW composes nothing (no Model.mjs here), but its SEP literal
        # decodes · to the middle dot the README writes.
        self.write('README.md', README + 'Another: `Sources is full`; the separator literal is ` · `.\n')
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)


class RealTree(unittest.TestCase):
    """The composer path, against this tree's Model.mjs and constants."""

    def run_checker(self, *docs):
        out = io.StringIO()
        real = sys.stdout
        sys.stdout = out
        try:
            rc = checker.main(['--root', ROOT] + list(docs))
        finally:
            sys.stdout = real
        return rc, out.getvalue()

    def test_the_readme_is_green_and_the_composer_ran(self):
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        summary = [l for l in out.split('\n') if l.startswith('readme notices: ')]
        self.assertEqual(len(summary), 1, out)
        self.assertIn(' 2 composed, ', summary[0])
        self.assertNotIn(' 0 composed string(s)', summary[0])

    def test_the_sources_full_quote_is_checked_against_max_sources(self):
        # The README's `(50)` is MAX_SOURCES through Model.sourceErrorMessage;
        # a README that said 51 is red, and so would a README that still
        # said 50 after the constant moved.
        scratch = tempfile.mkdtemp(prefix='readme-notices-real-')
        self.addCleanup(shutil.rmtree, scratch, True)
        path = os.path.join(scratch, 'README.md')
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write('# x\n\nSays `Sources is full (51) · remove one first` and `Sources is full (50) · remove one first`.\n')
        rc, out = self.run_checker(path)
        self.assertEqual(rc, 1, out)
        self.assertIn('`Sources is full (51) · remove one first` matches no shipped string', out)
        self.assertIn('1 problem(s)', out)
        self.assertIn('1 composed, ', out)


if __name__ == '__main__':
    unittest.main()
