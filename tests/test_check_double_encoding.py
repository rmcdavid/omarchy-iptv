"""Prove scripts/check-double-encoding.py catches what it claims to (D-DOC-28).

CLAUDE.md rule 11: every case builds a throwaway git repository, writes the
files the case is about, and runs the SHIPPING checker's main() -- and one
case runs it as the gate does, `python3 -I` in a subprocess. Rule 12:
nothing here re-implements the scan; the only transform this file performs
is the damage itself (a string's UTF-8 read as Latin-1 or as Windows-1252),
which is what the checker has to undo, not what it does.

NO DOUBLE-ENCODED TEXT IS WRITTEN IN THIS FILE, and no fixture file holds
any. Both are tracked, the checker reads every tracked file, and a literal
sequence here would turn the gate red on the test that proves the gate (the
same trap scripts/check-sr-register.py's test documents for its ids). Every
damaged string is composed at run time by latin1() or cp1252(), and this
source is ASCII (rule 8): the real glyph is written as an escape.

The brief's fixture is FixtureCase: one double-encoded glyph, one
legitimate Latin-1 word and one real glyph, red / green / green.
"""
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'scripts', 'check-double-encoding.py')
_s = importlib.util.spec_from_file_location('check_double_encoding', SCRIPT)
checker = importlib.util.module_from_spec(_s)
_s.loader.exec_module(checker)

TV_OFF = '\U000f0503'                 # nf-md-television_off, Model.GLYPHS.tvOff
LATIN1_WORDS = 'caf\xe9, Stra\xdfe, na\xefve, 3\xd7, a \xb7 b'
# French typography: a no-break space inside the guillemets, after an
# upper-case accented letter. U+00C9 U+00A0 is valid UTF-8 (U+0260) and is
# legitimate text; the checker must leave it alone.
GUILLEMETS = '\xab\xa0\xc9T\xc9\xa0\xbb'


def latin1(s):
    """The damage D-DOC-28 found: UTF-8 bytes read back as Latin-1."""
    return s.encode('utf-8').decode('latin-1')


def cp1252(s):
    """The same damage through Windows-1252, the other common reading. The
    five bytes it leaves undefined come through as the C1 control of the same
    number, as Windows' own conversion and the Latin-1 fallback both do."""
    out = []
    for b in s.encode('utf-8'):
        try:
            out.append(bytes([b]).decode('cp1252'))
        except UnicodeDecodeError:
            out.append(chr(b))
    return ''.join(out)


class Repo(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='double-encoding-')
        self.addCleanup(shutil.rmtree, self.dir, True)
        subprocess.run(['git', 'init', '-q', self.dir], check=True)

    def write(self, rel, text, add=True, raw=None):
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as fh:
            fh.write(raw if raw is not None else text.encode('utf-8'))
        if add:
            subprocess.run(['git', '-C', self.dir, 'add', '--', rel], check=True)
        return path

    def run_checker(self, *args):
        out = io.StringIO()
        real = sys.stdout
        sys.stdout = out
        try:
            rc = checker.main(list(args) if args else ['--root', self.dir])
        finally:
            sys.stdout = real
        return rc, out.getvalue()


class FixtureCase(Repo):
    """One double-encoded glyph, one legitimate Latin-1 word, one real glyph."""

    def setUp(self):
        super().setUp()
        self.glyph = self.write('docs/damaged.md', '| Stream failed | `%s` U+F0503 |\n' % latin1(TV_OFF))
        self.word = self.write('docs/latin1.md', 'The channel is %s.\n' % LATIN1_WORDS)
        self.real = self.write('docs/glyph.md', '| Stream failed | `%s` U+F0503 |\n' % TV_OFF)

    def test_the_double_encoded_glyph_is_red_and_named(self):
        rc, out = self.run_checker('--root', self.dir, self.glyph)
        self.assertEqual(rc, 1, out)
        self.assertIn('damaged.md:1:20: U+F0503 written as 4 characters '
                      '(\\u00f3\\u00b0\\u0094\\u0083)', out)
        self.assertIn('1 problem(s)', out)

    def test_the_latin1_word_is_green(self):
        rc, out = self.run_checker('--root', self.dir, self.word)
        self.assertEqual(rc, 0, out)
        # e-acute, sharp s, i-diaeresis and the multiplication sign can each
        # start a sequence and none completes one: four rejected candidates.
        self.assertIn('4 candidate(s) rejected, 0 problem(s)', out)

    def test_the_real_glyph_is_green(self):
        rc, out = self.run_checker('--root', self.dir, self.real)
        self.assertEqual(rc, 0, out)
        self.assertIn('0 candidate(s) rejected, 0 problem(s)', out)

    def test_the_tree_names_only_the_damaged_file(self):
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('docs/damaged.md:1:20: U+F0503', out)
        self.assertNotIn('docs/latin1.md', out)
        self.assertNotIn('docs/glyph.md', out)
        self.assertIn('double-encoding guard: 3 file(s) read (0 untracked), 0 skipped,'
                      ' 4 candidate(s) rejected, 1 problem(s)', out)

    def test_the_gate_command_line_is_red_then_green_after_repair(self):
        cmd = [sys.executable, '-I', SCRIPT, '--root', self.dir]
        red = subprocess.run(cmd, stdout=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(red.returncode, 1, red.stdout)
        fix = subprocess.run([sys.executable, '-I', SCRIPT, '--repair', self.glyph],
                             stdout=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(fix.returncode, 0, fix.stdout)
        self.assertIn('1 sequence(s) repaired', fix.stdout)
        green = subprocess.run(cmd, stdout=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(green.returncode, 0, green.stdout)
        self.assertIn('0 problem(s)', green.stdout)


class ShapeCase(Repo):
    """The siblings by shape (rule 15) and the rejections, one per case."""

    def check_one(self, text):
        self.write('a.md', text)
        return self.run_checker()

    def test_a_cp1252_curly_quote_is_red(self):
        rc, out = self.check_one('a %sname%s b\n' % (cp1252('\U0000201c'), cp1252('\U0000201d')))
        self.assertEqual(rc, 1, out)
        self.assertIn('a.md:1:3: U+201C written as 3 characters', out)
        self.assertIn('U+201D written as 3 characters', out)

    def test_a_latin1_en_dash_is_red(self):
        rc, out = self.check_one('a %s b\n' % latin1('\U00002013'))
        self.assertEqual(rc, 1, out)
        self.assertIn('a.md:1:3: U+2013 written as 3 characters (\\u00e2\\u0080\\u0093)', out)

    def test_a_double_encoded_e_acute_is_red(self):
        rc, out = self.check_one('caf%s\n' % latin1('\xe9'))
        self.assertEqual(rc, 1, out)
        self.assertIn('a.md:1:4: U+00E9 written as 2 characters (\\u00c3\\u00a9)', out)

    def test_a_two_byte_sequence_with_a_c1_control_is_red(self):
        # Cyrillic de, U+0414, is D0 94: its second half is a C1 control.
        rc, out = self.check_one('%s\n' % latin1('\U00000414'))
        self.assertEqual(rc, 1, out)
        self.assertIn('U+0414 written as 2 characters (\\u00d0\\u0094)', out)

    def test_guillemets_after_an_accented_capital_are_green(self):
        rc, out = self.check_one('%s\n' % GUILLEMETS)
        self.assertEqual(rc, 0, out)
        # U+00C9 U+00A0 decodes (U+0260) and is rejected; the second U+00C9
        # is followed by T and completes nothing.
        self.assertIn('2 candidate(s) rejected, 0 problem(s)', out)

    def test_a_sequence_right_after_a_failed_lead_is_still_found(self):
        # e-acute (E9) wants two followers and gets the damaged glyph's first
        # two characters, which do not complete it; the scan resumes one
        # character on, where the damage starts, not past it.
        rc, out = self.check_one('caf\xe9%s\n' % latin1(TV_OFF))
        self.assertEqual(rc, 1, out)
        self.assertIn('a.md:1:5: U+F0503 written as 4 characters', out)
        self.assertIn('1 candidate(s) rejected, 1 problem(s)', out)

    def test_a_lead_at_the_end_of_the_text_is_rejected_not_flagged(self):
        rc, out = self.check_one('\xf3')
        self.assertEqual(rc, 0, out)
        self.assertIn('1 candidate(s) rejected, 0 problem(s)', out)

    def test_an_overlong_form_is_not_a_sequence(self):
        # E0 80 AF would be an overlong slash: not valid UTF-8, so the strict
        # decode refuses it and nothing is flagged; the lead is rejected.
        rc, out = self.check_one('\xe0\x80\xaf\n')
        self.assertEqual(rc, 0, out)
        self.assertIn('1 candidate(s) rejected, 0 problem(s)', out)

    def test_an_untracked_file_is_read_and_says_so(self):
        # F-GATE-1: a file in the tree that is not staged yet is the one a
        # lane is about to commit.
        self.write('new.md', 'x %s\n' % latin1(TV_OFF), add=False)
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('new.md:1:3: U+F0503 written as 4 characters', out)
        self.assertIn('(untracked)', out)
        self.assertIn('1 file(s) read (1 untracked)', out)

    def test_an_ignored_file_is_not_read(self):
        self.write('.gitignore', 'scratch.md\n')
        self.write('scratch.md', 'x %s\n' % latin1(TV_OFF), add=False)
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)

    def test_a_file_with_a_nul_is_skipped_and_named(self):
        # Valid UTF-8 apart from the NUL, damage included: only the NUL says
        # this is not text.
        self.write('blob.bin', None, raw=b'PK\x00\x01' + latin1(TV_OFF).encode('utf-8'))
        self.write('b.md', 'plain\n')
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        self.assertIn('skipped as a link or not UTF-8 text: blob.bin', out)
        self.assertIn('1 file(s) read (0 untracked), 1 skipped', out)

    def test_a_file_that_is_not_utf8_is_skipped_and_named(self):
        self.write('logo.png', None, raw=b'\x89PNG\r\n\x1a\n' + latin1(TV_OFF).encode('utf-8'))
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('skipped as a link or not UTF-8 text: logo.png', out)
        self.assertIn('read no files at all', out)

    def test_a_symbolic_link_is_skipped_and_named(self):
        # A link is read through to wherever it points; the tree's own file
        # is scanned under its own name instead.
        self.write('real.md', 'plain\n')
        os.symlink('real.md', os.path.join(self.dir, 'link.md'))
        subprocess.run(['git', '-C', self.dir, 'add', '--', 'link.md'], check=True)
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)
        self.assertIn('skipped as a link or not UTF-8 text: link.md', out)
        self.assertIn('1 file(s) read (0 untracked), 1 skipped', out)

    def test_nothing_read_is_red(self):
        rc, out = self.run_checker()
        self.assertEqual(rc, 1, out)
        self.assertIn('read no files at all', out)


class RepairCase(Repo):

    def test_repair_changes_only_the_sequences(self):
        before = ('| %s | %s |\r\n%s and %s and %s\n'
                  % (latin1(TV_OFF), LATIN1_WORDS, GUILLEMETS, TV_OFF, cp1252('\U0000201c')))
        path = self.write('ux.md', before)
        rc, out = self.run_checker('--repair', path)
        self.assertEqual(rc, 0, out)
        self.assertIn('2 sequence(s) repaired', out)
        with open(path, 'rb') as fh:
            after = fh.read()
        want = ('| %s | %s |\r\n%s and %s and %s\n'
                % (TV_OFF, LATIN1_WORDS, GUILLEMETS, TV_OFF, '\U0000201c')).encode('utf-8')
        self.assertEqual(after, want)
        rc, out = self.run_checker()
        self.assertEqual(rc, 0, out)

    def test_repair_leaves_a_clean_file_untouched(self):
        path = self.write('ok.md', LATIN1_WORDS + '\n')
        stamp = os.stat(path).st_mtime_ns
        os.utime(path, ns=(stamp - 10**9, stamp - 10**9))
        rc, out = self.run_checker('--repair', path)
        self.assertEqual(rc, 0, out)
        self.assertIn('0 sequence(s) repaired', out)
        self.assertEqual(os.stat(path).st_mtime_ns, stamp - 10**9)

    def test_repair_refuses_a_repair_whose_reverse_is_not_the_original(self):
        # A sequence the scan never found: the reverse transform walks the
        # repaired text back and cannot reach the original, so nothing is
        # returned to write.
        real = checker.scan_text
        checker.scan_text = lambda text: ([(0, 'zz', 'q')], 0)
        try:
            with self.assertRaises(AssertionError):
                checker.repair_text('ab')
        finally:
            checker.scan_text = real

    def test_repair_text_returns_the_reverse_proof_inputs(self):
        text = 'a %s b %s c' % (latin1(TV_OFF), latin1('\xe9'))
        repaired, hits = checker.repair_text(text)
        self.assertEqual(repaired, 'a %s b \xe9 c' % TV_OFF)
        self.assertEqual([(o, d) for o, _c, d in hits], [(2, TV_OFF), (9, '\xe9')])


if __name__ == '__main__':
    unittest.main()
