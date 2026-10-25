"""The two carriage-return playlist fixtures keep their bytes under
`.gitattributes` (F-HARNESS-34).

`.gitattributes` says `* text=auto eol=lf` so a checkout under
`core.autocrlf=true` can still run the gate (a CR after a shebang is
`bad interpreter`). Two fixtures carry a carriage return ON PURPOSE and must
never be normalised: `qa-nonascii/qa-bom-crlf.m3u` is CRLF throughout behind
a BOM (the BOM+CRLF case), and `qa-headers.m3u` is LF with ONE bare CR
inside a header value (SEC-03: a bare 0x0D inside a value must be
neutralised). git's own `text=auto` heuristic calls the second one binary
because of that lone CR, and the first one it would renormalise; both are
excluded with `-text` so neither depends on a heuristic.

This pins it by CALLING git for the attribute it resolves and the line
endings it sees (not by grepping `.gitattributes` for the line, rule 14),
and by reading the bytes. Seen red on a9d20f9, where no `.gitattributes`
existed (`attr/` blank on both, the attribute `unspecified`).
"""

import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRLF_FIXTURE = 'tests/fixtures/qa-nonascii/qa-bom-crlf.m3u'
LONE_CR_FIXTURE = 'tests/fixtures/qa-headers.m3u'
# A file the LF rule must reach: the gate's own entry point.
LF_CONTROL = 'scripts/check.sh'


def git_attr(name, rel):
    out = subprocess.check_output(['git', '-C', ROOT, 'check-attr', name, '--', rel], timeout=30)
    # "<path>: <name>: <value>"
    return out.decode('utf-8').strip().rsplit(': ', 1)[1]


def git_eol(rel):
    out = subprocess.check_output(['git', '-C', ROOT, 'ls-files', '--eol', '--', rel], timeout=30)
    line = out.decode('utf-8').strip()
    return line.split('\t')[0].split() if line else []


def read_bytes(rel):
    with open(os.path.join(ROOT, rel), 'rb') as fh:
        return fh.read()


@unittest.skipUnless(shutil.which('git') and os.path.exists(os.path.join(ROOT, '.git')),
                     'needs git and the git checkout (.git is a file in a worktree)')
class CarriageReturnFixtures(unittest.TestCase):
    def test_the_bom_crlf_fixture_is_crlf_throughout(self):
        data = read_bytes(CRLF_FIXTURE)
        self.assertTrue(data.startswith(b'\xef\xbb\xbf'), 'the BOM is gone')
        self.assertIn(b'\r\n', data, 'lost its CRLF')
        self.assertNotIn(b'\n', data.replace(b'\r\n', b''), 'a bare LF crept into the CRLF fixture')
        self.assertNotIn(b'\r', data.replace(b'\r\n', b''), 'a bare CR crept into the CRLF fixture')

    def test_the_headers_fixture_keeps_its_one_bare_cr(self):
        data = read_bytes(LONE_CR_FIXTURE)
        self.assertNotIn(b'\r\n', data, 'the LF fixture gained CRLF')
        self.assertEqual(data.count(b'\r'), 1, 'the one bare CR of SEC-03 is not one')
        self.assertIn(b'Evil/1.0\rX-Injected', data, 'the bare CR is no longer inside the header value')

    def test_git_leaves_both_fixtures_alone_and_normalises_the_rest(self):
        for rel in (CRLF_FIXTURE, LONE_CR_FIXTURE):
            with self.subTest(file=rel):
                self.assertEqual(git_attr('text', rel), 'unset',
                                 '%s is not marked -text, so a renormalise could rewrite it' % rel)
                self.assertIn('attr/-text', git_eol(rel), git_eol(rel))
        self.assertEqual(git_attr('text', LF_CONTROL), 'auto')
        self.assertEqual(git_attr('eol', LF_CONTROL), 'lf')
        self.assertEqual(git_eol(LF_CONTROL)[:2], ['i/lf', 'w/lf'])

    def test_the_crlf_fixture_is_what_the_rule_would_have_rewritten(self):
        """The control: the exclusion protects against something real. git
        sees the CRLF fixture as CRLF in the index and the tree, which
        `* text=auto eol=lf` renormalises on the next add without `-text`."""
        self.assertEqual(git_eol(CRLF_FIXTURE)[:2], ['i/crlf', 'w/crlf'])


if __name__ == '__main__':
    unittest.main()
