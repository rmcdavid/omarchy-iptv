"""The harness shell asks before it calls a model member an older staged tree
lacks (F-HARNESS-19).

The harness runs TODAY'S scripts/dev-harness/shell.qml over whatever tree a
scenario stages: tls-scenario.sh's S6 stages `b731882^` by default, and the
scenarios' `--baseline <ref>` red runs stage older code still. Since 51d686b
the shell called Model.logoHaveCount, which `b731882^` does not export, so
every state read threw and S6 read "the stage shell never parsed the
playlist" on dev for a rig reason -- a regression in the adoption path it
exists to prove would have read the same.

So: every `Model.<name>` this file uses that some staged tree's model does
not export must be guarded by `typeof Model.<name>` within the same function,
on or above the line that uses it. The staged trees are every ref the
repository names as one -- PRE_TLS_REF in tls-scenario.sh and every
`--baseline <commit|tag>` in the harness scripts, the harness README and the
documents -- so a baseline documented tomorrow is checked tomorrow.

THIS IS A STRUCTURAL PIN, labelled as such (rule 14): QML cannot be run from
here. What observes the sink is S6 itself under the nested cage, which read
red at 1345 before the guard and is re-run after it (the lane's report).
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHELL = os.path.join(ROOT, 'scripts', 'dev-harness', 'shell.qml')
TLS = os.path.join(ROOT, 'scripts', 'dev-harness', 'tls-scenario.sh')

PRE_TLS = re.compile(r'^PRE_TLS_REF="([^"]+)"', re.M)
BASELINE = re.compile(r'--baseline[ =]+(v\d+\.\d+\.\d+|[0-9a-f]{7,40})\b')
MEMBER = re.compile(r'(?<![\w$.])Model\.([A-Za-z_$][\w$]*)')


def git(*args):
    return subprocess.run(['git', '-C', ROOT] + list(args), stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL)


def staged_refs():
    """Every ref the repository names as a tree a scenario stages."""
    refs = []
    with open(TLS, encoding='utf-8') as fh:
        refs += PRE_TLS.findall(fh.read())
    places = [os.path.join(ROOT, 'scripts', 'dev-harness')] + [os.path.join(ROOT, 'docs')]
    for place in places:
        for name in sorted(os.listdir(place)):
            if not name.endswith(('.sh', '.md')):
                continue
            with open(os.path.join(place, name), encoding='utf-8', errors='replace') as fh:
                refs += BASELINE.findall(fh.read())
    seen, out = set(), []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            out.append(ref)
    return out


def exports_at(ref, work):
    """The model's public names at `ref`, loaded by node the way it ships
    there: the one-file Model.js, or Model.mjs and its parts. None when the
    ref does not resolve or holds neither."""
    if git('rev-parse', '--verify', '-q', ref + '^{commit}').returncode != 0:
        return None
    dest = os.path.join(work, re.sub(r'[^\w.-]', '_', ref))
    os.makedirs(dest)
    old = git('show', ref + ':Model.js')
    if old.returncode == 0:
        path = os.path.join(dest, 'Model.js')
        with open(path, 'wb') as fh:
            fh.write(old.stdout)
        script = 'console.log(JSON.stringify(Object.keys(require(process.argv[1]))))'
    else:
        tar = git('archive', ref, 'Model.mjs', 'model')
        if tar.returncode != 0:
            return None
        subprocess.run(['tar', '-x', '-C', dest], input=tar.stdout, check=True)
        path = 'file://' + os.path.join(dest, 'Model.mjs')
        script = 'import(process.argv[1]).then(M => console.log(JSON.stringify(Object.keys(M))))'
    out = subprocess.run(['node', '-e', script, path], stdout=subprocess.PIPE, check=True)
    return set(json.loads(out.stdout.decode()))


def member_uses(text):
    """(line number, name) for every Model member a code line uses."""
    uses = []
    for n, line in enumerate(text.split('\n'), 1):
        if line.lstrip().startswith('//'):
            continue
        uses += [(n, m.group(1)) for m in MEMBER.finditer(line) if m.group(1) != 'mjs']
    return uses


def unguarded(text, missing):
    """Uses of a missing member with no `typeof Model.<name>` between the
    nearest `function` at or above the line and the line itself."""
    lines = text.split('\n')
    bad = []
    for n, name in member_uses(text):
        if name not in missing:
            continue
        guard = 'typeof Model.' + name
        k = n - 1
        while k > 0 and not re.search(r'\bfunction\b', lines[k]):
            k -= 1
        if not any(guard in lines[j] for j in range(k, n)):
            bad.append('shell.qml:%d uses Model.%s, which %s lack(s), without asking first'
                       % (n, name, ', '.join(sorted(missing[name]))))
    return bad


@unittest.skipUnless(shutil.which('node') and git('rev-parse', '--git-dir').returncode == 0,
                     'needs node and the repository history')
class HarnessShellAsksFirst(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.mkdtemp(prefix='harness-shell-model-')
        cls.refs = staged_refs()
        cls.exports = {}
        for ref in cls.refs:
            names = exports_at(ref, cls.work)
            if names is not None:
                cls.exports[ref] = names
        with open(SHELL, encoding='utf-8') as fh:
            cls.text = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def missing(self):
        out = {}
        used = set(name for _, name in member_uses(self.text))
        for ref, names in self.exports.items():
            for name in used - names:
                out.setdefault(name, set()).add(ref)
        return out

    def test_the_stage_trees_are_found_and_read(self):
        """Not blind: S6's default tree is among them and its model loads."""
        self.assertIn('b731882^', self.refs)
        self.assertIn('b731882^', self.exports)
        self.assertGreater(len(self.exports['b731882^']), 500)
        self.assertGreaterEqual(len(self.exports), 5, self.exports.keys())

    def test_the_f_harness_19_member_is_one_the_stage_tree_lacks(self):
        self.assertIn('logoHaveCount', self.missing())

    def test_every_member_a_staged_tree_lacks_is_asked_for_first(self):
        self.assertEqual([], unguarded(self.text, self.missing()))

    def test_an_unguarded_use_is_found(self):
        """The judge itself, on a line written here: an unguarded call is
        reported, and the same call behind a typeof is not."""
        missing = {'zz': {'r1'}}
        self.assertEqual(1, len(unguarded('  function f() {\n    return Model.zz(1)\n  }\n', missing)))
        self.assertEqual([], unguarded(
            '  function f() {\n    if (typeof Model.zz !== "function") return 0\n    return Model.zz(1)\n  }\n',
            missing))
        self.assertEqual(1, len(unguarded(
            '  if (typeof Model.zz !== "function") x()\n  function f() {\n    return Model.zz(1)\n  }\n',
            missing)), 'a guard in another function does not count')


if __name__ == '__main__':
    unittest.main()
