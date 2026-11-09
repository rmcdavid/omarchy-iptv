"""Prove scripts/release.py ships exactly what it says and refuses what it must.

CLAUDE.md rule 11: a new check has no "before", so it is proven by mutation.
Rule 12: every case builds a real git repository and runs the real module.

The must-ship set in must_ship() is written out BY HAND, on purpose, rather
than read from release.ALLOWLIST. A test that asserted "the tree equals the
allowlist" would stay green if someone deleted bin/omarchy-iptv from the
allowlist; this one goes red. Verified: drop that entry and
test_the_artifact_holds_exactly_what_the_plugin_needs fails.

The model's files (D-REL-5) are the one part not written out here: they are
read from THIS repository's Model.mjs through scripts/model_files.py, the
same reader everything else uses, and never from release.ALLOWLIST -- so a
part dropped from the allowlist is still red, and a part added to the model
is expected to ship the day it exists.
"""

import importlib.util
import inspect
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    'release', os.path.join(ROOT, 'scripts', 'release.py'))
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import model_files  # noqa: E402  the model's files, read from Model.mjs (D-REL-5)
import helper_files  # noqa: E402  the helper's files, read from its stub (D-REL-7)

# The real model's layout, so the fixture tree has the same files the
# artifact must carry. The first part holds the fixture's PLUGIN_VERSION.
PARTS = model_files.part_paths(ROOT)
VERSION_PART = PARTS[0]

# The real helper's parts (D-REL-7), read from THIS repository's stub through
# the one reader of HELPER_PARTS, so the fixture carries what the artifact
# must and a part dropped from the allowlist is red. The parser lives in the
# part that holds `build_parser`, and the fixture writes its doubles there.
HELPER_PARTS = helper_files.part_paths(ROOT)
PARSER_PART = [rel for rel in HELPER_PARTS
               if 'def build_parser(' in helper_files.read(ROOT, rel)][0]


def helper_stub(parts):
    """A stub in the shape the split writes: the list is all the resolver reads."""
    return ('#!/usr/bin/env python3\nimport sys\nHELPER_PARTS = (\n%s)\n'
            % ''.join('    ("%s", 1, 0x00000000),\n' % rel.rsplit('/', 1)[1] for rel in parts))


def must_ship():
    return {
        'manifest.json', 'README.md', 'LICENSE', 'CHANGELOG.md', 'preview.png',
        'BarWidget.qml', 'Guide.qml', 'Service.qml',
        'bin/omarchy-iptv',
        'contrib/bindings.lua', 'contrib/omarchy-menu.jsonc', 'contrib/windows.lua',
    } | set(model_files.model_paths(ROOT)) | set(helper_files.part_paths(ROOT))


def aggregator(parts):
    """A Model.mjs in the generated form, re-exporting nothing from each part."""
    return '// fixture\n' + ''.join('export {} from "./%s"\n' % rel for rel in parts)


TODAY = '2026-09-26'


def premise_fixture(exception=False):
    """THIS repository's accessibility premise fixture, with or without its
    exception. The cut reads it and the real tree always carries it, so the
    double carries it too (rule 10); without the exception it is the fixture
    as it reads when nothing excuses the premise."""
    with io.open(os.path.join(ROOT, release.A11Y_PREMISE_FIXTURE), encoding='utf-8') as fh:
        data = json.load(fh)
    data.pop('exception', None)
    if exception:
        data['exception'] = {
            'authorisedBy': 'the product owner', 'date': '2026-10-31',
            'boardRow': 'D-A11Y-1',
            'platform': {'quickshell': '0.3.2.r7.g2b4501a-1', 'qt6-base': '6.12.0-3',
                         'at-spi2-core': '2.62.1-1'},
            'evidence': {'upstreamFix': '916a0dd', 'probe': 'a11y-probe.sh'},
            'why': 'unrelated work may land; nothing ships',
        }
    return json.dumps(data, indent=2) + '\n'

MUST_NOT_SHIP = ('CLAUDE.md', 'docs/PRODUCT.md', 'tests/test_x.py',
                 'scripts/check.sh', '.gitignore')


class ReleaseCase(unittest.TestCase):

    def setUp(self):
        # The clone and its origin sit side by side under one directory, so the
        # remote is outside the work tree and one cleanup removes both.
        self.top = tempfile.mkdtemp(prefix='release-test-')
        self.addCleanup(shutil.rmtree, self.top, True)
        self.dir = os.path.join(self.top, 'clone')
        self.origin = os.path.join(self.top, 'origin.git')
        os.mkdir(self.dir)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 't@example.invalid')
        self.git('config', 'user.name', 'test')
        # A first main commit with the full tree, standing in for the history
        # before the split; then dev branches from it.
        for path in sorted(must_ship() | set(MUST_NOT_SHIP)):
            self.write(path, 'content of %s\n' % path)
        self.write('manifest.json', '{"version": "0.9.9", "entryPoints": '
                   '{"barWidget": "BarWidget.qml", "overlay": "Guide.qml", '
                   '"service": "Service.qml"}}\n')
        self.write('Service.qml', 'import "Model.mjs" as Model\n'
                   'x: Qt.resolvedUrl("bin/omarchy-iptv")\n')
        self.write('Model.mjs', aggregator(PARTS))
        self.write('bin/omarchy-iptv', helper_stub(HELPER_PARTS))
        # D-HOST-1: the runtime compares this against manifest.json to notice a
        # hot reload that left an older component mounted, so the check demands
        # it and the double must carry it. A double more forgiving than the
        # real tree is what rule 10 forbids.
        self.write(VERSION_PART, 'var PLUGIN_VERSION = "0.9.9"\n')
        self.write('README.md', 'Copy `contrib/bindings.lua`. See the dev branch: '
                   'https://example.invalid/tree/dev/docs/UX.md\n')
        # The cut requires a heading naming this version and dated the day of
        # the build, so the double carries one (rule 10: a double that ships
        # what the real tree cannot is the forgiving kind).
        self.write('CHANGELOG.md', '# Changelog\n\n## 0.9.9 (%s)\n\n- a thing\n' % TODAY)
        # The cut refuses while D-A11Y-1's exception stands and refuses a tree
        # it cannot read the premise from, so the double carries the fixture,
        # as the real tree does, with no exception in it.
        self.write(release.A11Y_PREMISE_FIXTURE, premise_fixture())
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'before the split')
        # D-REL-13: the cut asks origin whether its main holds a commit the
        # local one lacks, and refuses a clone it cannot ask. The real clone
        # always has one, so the double does too (rule 10): a local bare
        # repository holding main (fetched into it, not pushed), which every
        # cut below passes through rather than around.
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', self.origin],
                       check=True, stdout=subprocess.PIPE)
        subprocess.run(['git', '-C', self.origin, 'fetch', '-q', self.dir,
                        'refs/heads/main:refs/heads/main'], check=True, stdout=subprocess.PIPE)
        self.git('remote', 'add', 'origin', self.origin)
        self.git('checkout', '-q', '-b', 'dev')

    def git(self, *args):
        return subprocess.run(['git', '-C', self.dir] + list(args), check=True,
                              stdout=subprocess.PIPE).stdout.decode()

    def write(self, rel, text):
        path = os.path.join(self.dir, rel)
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        with io.open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)

    def commit_all(self, msg='change'):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', msg)

    def build(self):
        return release.build(self.dir, gate_already_green=True, validate=False,
                             tag=True, out=io.StringIO(), today=TODAY)

    def main_tree(self):
        return set(p for p in self.git('ls-tree', '-r', '--name-only', '-z',
                                       'main').split('\0') if p)

    # -- what ships ------------------------------------------------------

    def test_the_artifact_holds_exactly_what_the_plugin_needs(self):
        self.build()
        self.assertEqual(must_ship(), self.main_tree())

    def test_no_agent_instruction_file_and_no_dev_directory_ships(self):
        self.build()
        tree = self.main_tree()
        for path in MUST_NOT_SHIP:
            self.assertNotIn(path, tree)
        for name in release.AGENT_INSTRUCTION_NAMES:
            self.assertNotIn(name, tree)
        self.assertFalse([p for p in tree if p.split('/')[0] in release.DEV_ONLY_DIRS])

    def test_main_stays_linear_so_installs_can_fast_forward(self):
        old = self.git('rev-parse', 'main').strip()
        new = self.build()
        self.assertEqual(old, self.git('rev-parse', 'main^').strip())
        self.assertEqual(new, self.git('rev-parse', 'main').strip())
        self.assertEqual(new, self.git('rev-parse', 'v0.9.9^{commit}').strip())

    def test_the_artifact_carries_dev_content_not_stale_main_content(self):
        self.write(VERSION_PART, 'new model\nvar PLUGIN_VERSION = "0.9.9"\n')
        self.commit_all()
        self.build()
        blob = self.git('show', 'main:' + VERSION_PART)
        self.assertEqual('new model\nvar PLUGIN_VERSION = "0.9.9"\n', blob)

    # -- refusals --------------------------------------------------------

    def test_a_dirty_tree_is_refused(self):
        self.write(VERSION_PART, 'uncommitted\nvar PLUGIN_VERSION = "0.9.9"\n')
        with self.assertRaisesRegex(release.ReleaseError, 'dirty'):
            self.build()

    def test_a_release_from_the_wrong_branch_is_refused(self):
        self.git('checkout', '-q', 'main')
        with self.assertRaisesRegex(release.ReleaseError, "cut from 'dev'"):
            self.build()

    def test_a_missing_allowlisted_file_is_refused(self):
        self.git('rm', '-q', 'contrib/windows.lua')
        self.commit_all()
        with self.assertRaisesRegex(release.ReleaseError, 'not tracked'):
            self.build()

    def test_nothing_new_is_refused(self):
        self.build()
        # bump the version so the tag does not collide, change nothing else
        self.write('manifest.json', self.git('show', 'dev:manifest.json')
                   .replace('0.9.9', '1.0.0'))
        # D-HOST-1: a real release bumps BOTH, and the check refuses a tree
        # where they disagree -- otherwise every install shows the restart
        # notice forever. Bumping only the manifest here would be testing a
        # release that could not ship.
        self.write(VERSION_PART, self.git('show', 'dev:' + VERSION_PART)
                   .replace('0.9.9', '1.0.0'))
        # And the release notes, because the cut now requires the heading to
        # name the version being shipped and to be dated the day it ships.
        # Bumping the manifest alone here would be testing a release that
        # could not ship, for the second reason in as many comments.
        self.write('CHANGELOG.md', '# Changelog\n\n## 1.0.0 (%s)\n\n- a thing\n' % TODAY)
        self.commit_all()
        # manifest.json IS on the allowlist, so this is a real change; make
        # the no-change case for real by building twice at the same content
        self.build()
        with self.assertRaisesRegex(release.ReleaseError, 'already exists'):
            self.build()

    def test_an_existing_tag_at_another_commit_is_refused(self):
        self.git('tag', 'v0.9.9', 'main')
        with self.assertRaisesRegex(release.ReleaseError, 'already exists'):
            self.build()

    # -- D-A11Y-1's exception: nothing ships while it stands --------------

    def test_the_cut_refuses_while_the_a11y_exception_stands(self):
        old_main = self.git('rev-parse', 'main').strip()
        self.write(release.A11Y_PREMISE_FIXTURE, premise_fixture(exception=True))
        self.commit_all('the owner\'s exception')
        with self.assertRaises(release.ReleaseError) as refused:
            self.build()
        said = str(refused.exception)
        self.assertIn('D-A11Y-1', said)
        self.assertIn('no release is cut while it stands', said)
        # One sentence: the releaser reads it at the prompt and acts on it.
        self.assertNotIn('. ', said)
        self.assertTrue(said.endswith('.'), said)
        # Refused means nothing moved: no commit on main, no tag.
        self.assertEqual(old_main, self.git('rev-parse', 'main').strip())
        self.assertEqual('', self.git('tag', '--list', 'v0.9.9').strip())

    def test_the_same_tree_cuts_once_the_exception_is_removed(self):
        self.write(release.A11Y_PREMISE_FIXTURE, premise_fixture(exception=True))
        self.commit_all('the owner\'s exception')
        with self.assertRaisesRegex(release.ReleaseError, 'D-A11Y-1'):
            self.build()
        self.write(release.A11Y_PREMISE_FIXTURE, premise_fixture())
        self.commit_all('D-A11Y-1 masked; the exception removed')
        new = self.build()
        self.assertEqual(new, self.git('rev-parse', 'v0.9.9^{commit}').strip())

    def test_the_everyday_gate_stays_green_while_the_exception_stands(self):
        # The exception exists so dev can take unrelated work; `check` runs in
        # check.sh, and refusing there would undo the owner's decision.
        self.write(release.A11Y_PREMISE_FIXTURE, premise_fixture(exception=True))
        self.commit_all('the owner\'s exception')
        self.assertEqual([], release.check(self.dir, out=io.StringIO()))
        # And as check.sh runs it: the command, its exit status.
        ran = self.release_cli('check')
        self.assertEqual(0, ran.returncode, ran.stdout)

    def release_cli(self, *args):
        return subprocess.run(
            [sys.executable, os.path.join(ROOT, 'scripts', 'release.py'), '--root', self.dir]
            + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True, timeout=120)

    def test_the_command_line_cut_refuses_in_one_sentence(self):
        self.write(release.A11Y_PREMISE_FIXTURE, premise_fixture(exception=True))
        self.commit_all('the owner\'s exception')
        ran = self.release_cli('build', '--gate-already-green', '--no-validate')
        self.assertEqual(1, ran.returncode, ran.stdout)
        self.assertRegex(ran.stdout, r'^release: REFUSED\. tests/fixtures/a11y-premise'
                                     r'\.json carries the dated exception for D-A11Y-1')
        self.assertEqual(1, len(ran.stdout.strip().splitlines()), ran.stdout)

    def test_an_empty_or_null_exception_still_refuses(self):
        # The premise test calls these malformed and goes red on them; the cut
        # does not wait for that: the key being there is the condition.
        for value in ('{}', 'null', '""'):
            with self.subTest(value=value):
                text = premise_fixture().rstrip().rstrip('}') + ',\n  "exception": %s\n}\n' % value
                self.assertIn('exception', json.loads(text))
                self.write(release.A11Y_PREMISE_FIXTURE, text)
                self.commit_all('an empty exception')
                with self.assertRaisesRegex(release.ReleaseError, 'no release is cut'):
                    self.build()

    def test_a_tree_without_the_premise_fixture_is_refused(self):
        self.git('rm', '-q', release.A11Y_PREMISE_FIXTURE)
        self.commit_all('no premise')
        with self.assertRaisesRegex(release.ReleaseError, 'could not be read.*D-A11Y-1'):
            self.build()

    def test_a_premise_fixture_that_is_not_an_object_is_refused(self):
        for text in ('not json\n', '["exception"]\n'):
            with self.subTest(text=text):
                self.write(release.A11Y_PREMISE_FIXTURE, text)
                self.commit_all('broken premise')
                with self.assertRaisesRegex(release.ReleaseError, 'D-A11Y-1 exception stands'):
                    self.build()

    def test_the_guard_reads_the_fixture_the_premise_test_reads(self):
        # Two files name one path: the guard and tests/test_a11y_premise.py.
        # Joined by a name, so the join is checked here (rule 13).
        spec = importlib.util.spec_from_file_location(
            'premise_for_release', os.path.join(ROOT, 'tests', 'test_a11y_premise.py'))
        premise = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(premise)
        self.assertEqual(os.path.join(ROOT, release.A11Y_PREMISE_FIXTURE), premise.FIXTURE)
        self.assertTrue(os.path.isfile(premise.FIXTURE))

    # -- D-REL-13: no cut while origin's main holds what main lacks ---------
    #
    # On 2026-11-08 the owner's web commit moved origin's main (dc402e7 ->
    # ce68db5) and no clone had fetched it. `build` parented the release on
    # the LOCAL main, so a cut that day would have built on dc402e7, and the
    # remote's ruleset refuses that push only after the cut has moved main and
    # written the tag. The origin here is the fixture's local bare repository.

    def ogit(self, *args, **kwargs):
        """git in the fixture's bare origin."""
        return subprocess.run(['git', '-C', self.origin] + list(args), check=True,
                              stdout=subprocess.PIPE, **kwargs).stdout.decode()

    def origin_commit(self, ref='refs/heads/main', path='CODE_OF_CONDUCT.md'):
        """A commit on origin that this clone has not fetched, made the way the
        owner's web commit was: on the remote alone, origin's main plus one
        file, parented on origin's main."""
        blob = self.ogit('hash-object', '-w', '--stdin', input=b'Be kind.\n').strip()
        listing = self.ogit('ls-tree', 'refs/heads/main')
        listing += '100644 blob %s\t%s\n' % (blob, path)
        tree = self.ogit('mktree', input=listing.encode()).strip()
        new = self.ogit('-c', 'user.name=web', '-c', 'user.email=web@example.invalid',
                        'commit-tree', tree, '-p', 'refs/heads/main',
                        '-m', 'Add a code of conduct').strip()
        self.ogit('update-ref', ref, new)
        return new

    def local_commit(self):
        """A commit on the local main that origin lacks: a cut not pushed yet."""
        tree = self.git('rev-parse', 'main^{tree}').strip()
        new = self.git('commit-tree', tree, '-p', 'main', '-m', 'an unpushed cut').strip()
        self.git('update-ref', 'refs/heads/main', new)
        return new

    def bump(self, version):
        """manifest, PLUGIN_VERSION and a dated heading, as a real cut bumps them."""
        self.write('manifest.json', self.git('show', 'dev:manifest.json').replace('0.9.9', version))
        self.write(VERSION_PART, self.git('show', 'dev:' + VERSION_PART).replace('0.9.9', version))
        self.write('CHANGELOG.md', '# Changelog\n\n## %s (%s)\n\n- a thing\n' % (version, TODAY))
        self.commit_all(version)

    def origin_takes_main(self):
        """Whether origin would take this clone's main as a fast-forward: the
        bare repository fetches it into its own main without a `+`, which git
        refuses unless it fast-forwards -- the ruleset's rule, and no push."""
        return subprocess.run(['git', '-C', self.origin, 'fetch', '-q', self.dir,
                               'refs/heads/main:refs/heads/main'], stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE).returncode == 0

    def footprint(self):
        """What a guard that only reads leaves alone: every ref, HEAD, the
        config, FETCH_HEAD and the object store."""
        gitdir = os.path.join(self.dir, '.git')

        def content(name):
            try:
                with io.open(os.path.join(gitdir, name), 'rb') as fh:
                    return fh.read()
            except FileNotFoundError:
                return None
        return {'refs': self.git('for-each-ref', '--format=%(refname) %(objectname)'),
                'HEAD': self.git('symbolic-ref', 'HEAD'),
                'config': content('config'),
                # Its bytes, not whether it exists: a fetch rewrites one that is there.
                'FETCH_HEAD': content('FETCH_HEAD'),
                'objects': self.git('count-objects', '-v')}

    def assert_refused(self, *said, gate_already_green=True):
        """The cut refuses, says each of `said` in one sentence that never
        mentions forcing anything, and leaves the clone exactly as it was."""
        before = self.footprint()
        with self.assertRaises(release.ReleaseError) as refused:
            release.build(self.dir, gate_already_green=gate_already_green, validate=False,
                          tag=True, out=io.StringIO(), today=TODAY)
        message = str(refused.exception)
        for part in said:
            self.assertIn(part, message)
        self.assertNotIn('. ', message)
        self.assertTrue(message.endswith('.'), message)
        self.assertNotIn('force', message.lower())
        self.assertEqual(before, self.footprint())
        return message

    def test_a_cut_refuses_while_origin_holds_a_commit_this_clone_lacks(self):
        web = self.origin_commit()
        self.assert_refused("origin's main is at %s, a commit this clone does not have" % web[:12],
                            'run git fetch origin main:main and cut again')
        # What it says to run is what lets the cut go, and the cut then
        # fast-forwards origin.
        self.git('fetch', '-q', 'origin', 'main:main')
        new = self.build()
        self.assertEqual(web, self.git('rev-parse', '%s^' % new).strip())
        self.assertTrue(self.origin_takes_main())

    def test_a_cut_refuses_while_origin_is_ahead_with_its_commit_already_here(self):
        """A plain `git fetch` brings the commit in and moves origin/main, not
        main: present, so this is the ancestry decision, not the presence one."""
        old = self.git('rev-parse', 'main').strip()
        web = self.origin_commit()
        self.git('fetch', '-q', 'origin')
        self.assertEqual(web, self.git('rev-parse', 'refs/remotes/origin/main').strip())
        self.assertEqual(old, self.git('rev-parse', 'main').strip())
        self.assert_refused("origin's main is at %s, ahead of the local main at %s" % (web[:12], old[:12]),
                            'run git fetch origin main:main and cut again')

    def test_a_cut_refuses_when_origin_and_main_have_diverged(self):
        web = self.origin_commit()
        self.git('fetch', '-q', 'origin')
        mine = self.local_commit()
        said = self.assert_refused(
            "origin's main at %s and the local main at %s have diverged" % (web[:12], mine[:12]),
            'git fetch origin main:main would be refused', 'a person must compare the two')
        self.assertNotIn('run git', said)
        self.assertNotIn('+main', said)
        # And it is right that no cut here can be pushed.
        self.assertFalse(self.origin_takes_main())

    def test_a_cut_proceeds_when_origin_holds_exactly_main(self):
        old = self.git('rev-parse', 'main').strip()
        self.assertEqual('%s\trefs/heads/main\n' % old, self.git('ls-remote', 'origin', 'refs/heads/main'))
        new = self.build()
        self.assertEqual(old, self.git('rev-parse', '%s^' % new).strip())
        self.assertTrue(self.origin_takes_main())

    def test_a_cut_proceeds_when_main_is_ahead_of_origin(self):
        """An earlier cut not pushed yet: origin's main is its ancestor, and the
        two still go up as one fast-forward."""
        old = self.git('rev-parse', 'main').strip()
        first = self.build()
        self.bump('1.0.0')
        second = self.build()
        self.assertEqual(first, self.git('rev-parse', '%s^' % second).strip())
        self.assertEqual(old, self.git('ls-remote', 'origin', 'refs/heads/main').split()[0])
        self.assertTrue(self.origin_takes_main())

    def test_a_clone_with_no_origin_is_refused(self):
        self.git('remote', 'remove', 'origin')
        self.assert_refused("this clone has no remote named 'origin'",
                            'a cut that cannot see it does not ship')

    def test_an_origin_that_cannot_be_read_is_refused(self):
        self.git('remote', 'set-url', 'origin', os.path.join(self.top, 'gone.git'))
        self.assert_refused('git ls-remote origin refs/heads/main failed (',
                            'does not appear to be a git repository',
                            'a cut that cannot see it does not ship')

    def test_an_origin_that_does_not_answer_is_refused_in_bounded_time(self):
        # An upload-pack that never advertises: it ends when git hangs up, or
        # after 5 s, so a guard with no timeout of its own reads a failure.
        hang = os.path.join(self.top, 'silent-upload-pack')
        with io.open(hang, 'w', encoding='utf-8') as fh:
            fh.write('#!/bin/sh\nexec timeout 5 cat\n')
        os.chmod(hang, 0o755)
        self.git('config', 'remote.origin.uploadpack', hang)
        with mock.patch.object(release, 'REMOTE_TIMEOUT', 1):
            start = time.monotonic()
            self.assert_refused('git ls-remote origin refs/heads/main did not answer within 1 s',
                                'a cut that cannot see it does not ship')
            self.assertLess(time.monotonic() - start, 4.5)

    def test_an_origin_without_main_is_refused(self):
        self.ogit('update-ref', 'refs/heads/dev', 'refs/heads/main')
        self.ogit('update-ref', '-d', 'refs/heads/main')
        self.assert_refused('origin has no refs/heads/main',
                            'find out what happened to it before cutting')

    # ls-remote's pattern is a tail match at a slash boundary, so both of these
    # are printed beside the real main, one before it and one after.
    DECOYS = ('refs/heads/a/refs/heads/main', 'refs/heads/x/refs/heads/main')

    def plant_decoys(self, sha):
        for ref in self.DECOYS:
            self.ogit('update-ref', ref, sha)
        printed = [line.split('\t')[1] for line in
                   self.git('ls-remote', 'origin', 'refs/heads/main').splitlines()]
        self.assertEqual([self.DECOYS[0], 'refs/heads/main', self.DECOYS[1]], printed)

    def test_a_decoy_that_would_refuse_does_not_decide(self):
        stranger = self.origin_commit(ref=self.DECOYS[0])
        self.plant_decoys(stranger)
        new = self.build()
        self.assertEqual(new, self.git('rev-parse', 'v0.9.9^{commit}').strip())

    def test_a_decoy_that_would_pass_does_not_decide(self):
        web = self.origin_commit()
        self.plant_decoys(self.git('rev-parse', 'main').strip())
        self.assert_refused("origin's main is at %s, a commit this clone does not have" % web[:12])

    def test_a_refused_cut_moves_no_ref_and_writes_no_tag(self):
        self.origin_commit()
        before = self.git('for-each-ref')
        with self.assertRaisesRegex(release.ReleaseError, "origin's main"):
            self.build()
        self.assertEqual(before, self.git('for-each-ref'))
        self.assertEqual('', self.git('tag', '--list').strip())

    def test_the_origin_guard_runs_before_the_allowlist_check_and_the_gate(self):
        marker = os.path.join(self.top, 'gate-ran')
        self.write('scripts/check.sh', '#!/bin/sh\n: > "%s"\nexit 1\n' % marker)
        os.chmod(os.path.join(self.dir, 'scripts', 'check.sh'), 0o755)
        self.git('rm', '-q', 'contrib/windows.lua')
        self.commit_all('a red gate and an allowlist that is not whole')
        self.origin_commit()
        said = self.assert_refused("origin's main is at", gate_already_green=False)
        self.assertNotIn('allowlist', said)
        self.assertFalse(os.path.exists(marker), 'the gate ran before the origin guard')

        # The rig sees the other two: once main is fetched the allowlist check
        # speaks, and once the allowlist is whole the gate runs, red.
        def cut():
            return release.build(self.dir, gate_already_green=False, validate=False,
                                 tag=True, out=io.StringIO(), today=TODAY)
        self.git('fetch', '-q', 'origin', 'main:main')
        with self.assertRaisesRegex(release.ReleaseError, 'not tracked'):
            cut()
        self.assertFalse(os.path.exists(marker))
        self.git('checkout', '-q', 'HEAD~1', '--', 'contrib/windows.lua')
        self.commit_all('the allowlist whole again')
        with self.assertRaisesRegex(release.ReleaseError, 'check.sh is red'):
            cut()
        self.assertTrue(os.path.exists(marker))

    def test_the_command_line_cut_refuses_while_origin_is_ahead(self):
        web = self.origin_commit()
        before = self.git('for-each-ref')
        ran = self.release_cli('build', '--gate-already-green', '--no-validate')
        self.assertEqual(1, ran.returncode, ran.stdout)
        self.assertRegex(ran.stdout, r"^release: REFUSED\. origin's main is at %s, a commit this "
                                     r"clone does not have, .*: run git fetch origin main:main "
                                     r"and cut again\.$" % web[:12])
        self.assertEqual(1, len(ran.stdout.strip().splitlines()), ran.stdout)
        self.assertEqual(before, self.git('for-each-ref'))

    def test_the_guard_only_reads(self):
        """No fetch, no ref, no object, no config, whatever it answers."""
        def ask(name, refuses):
            before = self.footprint()
            said = release.remote_main_problems(self.dir)
            self.assertEqual(refuses, bool(said), (name, said))
            self.assertEqual(before, self.footprint(), name)
            self.assertFalse(os.path.exists(os.path.join(self.dir, '.git', 'FETCH_HEAD')), name)
        ask('origin is main', False)
        self.local_commit()
        ask('main is ahead', False)
        self.origin_commit()
        ask('diverged, origin\'s commit not here', True)
        self.ogit('update-ref', 'refs/heads/main', 'refs/heads/main^')
        self.git('update-ref', 'refs/heads/main', 'refs/heads/main^')
        self.origin_commit(path='SECURITY.md')
        ask('origin is ahead, its commit not here', True)

    def test_the_remote_is_asked_with_prompts_off_and_the_environment_kept(self):
        seen = os.path.join(self.top, 'upload-pack-env')
        wrapper = os.path.join(self.top, 'recording-upload-pack')
        with io.open(wrapper, 'w', encoding='utf-8') as fh:
            fh.write('#!/bin/sh\nenv > "%s"\nexec git-upload-pack "$@"\n' % seen)
        os.chmod(wrapper, 0o755)
        self.git('config', 'remote.origin.uploadpack', wrapper)
        with mock.patch.dict(os.environ, {'RELEASE_TEST_KEPT': 'yes', 'GIT_TERMINAL_PROMPT': '1'}):
            self.assertEqual([], release.remote_main_problems(self.dir))
        with io.open(seen, encoding='utf-8') as fh:
            env = fh.read().splitlines()
        self.assertIn('GIT_TERMINAL_PROMPT=0', env)
        self.assertIn('RELEASE_TEST_KEPT=yes', env)

    def test_a_quoted_git_message_loses_the_urls_userinfo(self):
        said = release._git_detail(b"fatal: unable to access 'https://x-access-token:p@ss@github.com"
                                   b"/r/x.git/': boom.\nmore\n")
        self.assertEqual("fatal: unable to access 'https://github.com/r/x.git/': boom", said)

    def test_nothing_skips_the_origin_guard(self):
        """No flag and no parameter goes around D-REL-13's guard. A new one turns
        this red, on purpose: it has to be argued for, not slipped in."""
        self.assertEqual(['root', 'gate_already_green', 'validate', 'tag', 'trailers', 'out', 'today'],
                         list(inspect.signature(release.build).parameters))
        usage = self.release_cli('build', '--help').stdout.split('\n\n')[0]
        self.assertEqual({'-h', '--gate-already-green', '--no-validate', '--no-tag', '--trailer'},
                         set(re.findall(r'\[(--?[a-z][-a-z]*)', usage)))

    # -- the allowlist check that runs in the gate ------------------------

    def test_a_clean_tree_passes_check(self):
        self.assertEqual([], release.check(self.dir, out=io.StringIO()))

    def test_a_runtime_import_outside_the_allowlist_is_a_problem(self):
        self.write('Guide.qml', 'import "Extra.js" as Extra\n')
        self.write('Extra.js', 'x\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("loads 'Extra.js'" in p for p in problems), problems)

    def test_a_readme_that_names_a_dev_file_is_a_problem(self):
        self.write('README.md', 'Start with `docs/PRODUCT.md` and `CLAUDE.md`.\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any('docs/PRODUCT.md' in p for p in problems), problems)
        self.assertTrue(any('CLAUDE.md' in p for p in problems), problems)

    def test_a_readme_url_into_the_dev_branch_is_fine(self):
        self.write('README.md',
                   'https://github.com/x/y/blob/dev/docs/PRODUCT.md\n')
        self.commit_all()
        self.assertEqual([], release.check(self.dir, out=io.StringIO()))

    # -- D-REL-3: shipped prose may not run the helper bare ---------------

    HELPER_WITH_PARSER = ('sub.add_parser("player")\nsub.add_parser("logos")\n'
                          'sub.add_parser("cache")\n')

    def test_shipped_prose_that_runs_the_helper_bare_is_a_problem(self):
        """PLY-WEAK-05, verified 2026-09-14: the README told the user to run
        `omarchy-iptv player stop`, and omarchy-iptv is on nobody's PATH."""
        self.write(PARSER_PART, self.HELPER_WITH_PARSER)
        self.write('README.md', 'If one is left behind, run `omarchy-iptv player stop`.\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("README.md:1 tells the user to run 'omarchy-iptv player'" in p
                            and 'not on PATH' in p for p in problems), problems)

    def test_the_changelog_ships_too_and_is_scanned_too(self):
        """The third instance, 2026-09-25: fixed in the README and written
        again into the CHANGELOG in the same change."""
        self.write(PARSER_PART, self.HELPER_WITH_PARSER)
        self.write('CHANGELOG.md', '- Run `omarchy-iptv cache logos-clear --key <key>`.\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any('CHANGELOG.md:1' in p and 'D-REL-3' in p for p in problems), problems)

    def test_the_path_form_and_the_names_that_are_not_commands_are_fine(self):
        self.write(PARSER_PART, self.HELPER_WITH_PARSER)
        self.write('README.md',
                   'Run `python3 ~/.config/omarchy/plugins/x/bin/omarchy-iptv player stop`.\n'
                   'One mpv window, class `omarchy-iptv`, titled with the channel name.\n'
                   "pkill -f -- '^mpv .*--wayland-app-id=omarchy-iptv'\n"
                   'Cached under `~/.cache/omarchy-iptv/sources/<key>/logos/`.\n'
                   "The same helper's `logos` subcommand prints that survey.\n")
        self.commit_all()
        self.assertEqual([], release.check(self.dir, out=io.StringIO()))

    def test_the_subcommand_list_comes_from_the_helper_not_from_a_copy(self):
        """A helper that declares no parser makes the scan inert rather than
        wrong; one that declares `frobnicate` makes `omarchy-iptv frobnicate`
        a problem without anyone editing the check."""
        self.assertEqual([], release.bare_helper_invocations('run omarchy-iptv player stop', []))
        self.write(PARSER_PART, 'sub.add_parser("frobnicate")\n')
        self.write('README.md', 'Try `omarchy-iptv frobnicate` and `omarchy-iptv player stop`.\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("'omarchy-iptv frobnicate'" in p for p in problems), problems)
        self.assertFalse(any("'omarchy-iptv player'" in p for p in problems), problems)

    def test_the_scan_catches_every_line_that_actually_shipped(self):
        """The three real instances, verbatim, against the real helper's
        parser. README bullet 6 at 05a0d3a~1 (2026-09-14, PLY-WEAK-05);
        README line 101 as shipped in v0.7.6 through v0.7.10; and the
        CHANGELOG line written on 2026-09-25 and caught before it shipped."""
        subs = release.helper_subcommands(helper_files.helper_source(ROOT))
        self.assertIn('player', subs)
        self.assertIn('logos', subs)
        shipped = (
            # README.md:164 at 21487f7
            "  longer guaranteed to stop with it; run `omarchy-iptv player stop`, or log",
            # README.md:100 as shipped in v0.7.6
            'can see exactly what enabling them would cost your privacy: `omarchy-iptv logos` reads the cached playlist and prints which hosts it would contact and',
            # CHANGELOG.md, 2026-09-25, before review
            "  `omarchy-iptv cache logos-clear --key <key>`, with `ls ~/.cache/omarchy-iptv/sources/`",
        )
        for line in shipped:
            self.assertEqual(1, len(release.bare_helper_invocations(line, subs)), line)
        # and the wrapped form a per-line scan cannot see
        wrapped = "if one is left behind, run `omarchy-iptv\n  player stop`, or log out."
        self.assertEqual([(1, 'omarchy-iptv player')], release.bare_helper_invocations(wrapped, subs))

    def test_a_blank_line_inside_a_shipped_table_is_a_problem(self):
        """README.md's settings table shipped as three tables: two blank lines
        split fourteen rows into 4 + 4 + 6, and the last ten rendered as
        paragraphs of pipes. Three adversarial prose passes read past it,
        because they were reading the text and this is a defect in the shape."""
        self.write('README.md', 'Settings:\n\n| Key | Type |\n|---|---|\n'
                                '| `a` | string |\n\n| `b` | string |\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any('README.md:6 is a blank line INSIDE a table' in p
                            for p in problems), problems)

    def test_a_blank_line_after_a_table_ends_it_and_is_fine(self):
        self.write('README.md', '| Key | Type |\n|---|---|\n| `a` | string |\n\nProse after.\n')
        self.commit_all()
        self.assertEqual([], release.check(self.dir, out=io.StringIO()))

    def test_a_readme_version_that_disagrees_with_the_manifest_is_a_problem(self):
        """The artifact shipped once saying Status: v0.7.0 beside a 0.7.1 manifest."""
        self.write('README.md', 'Status: v0.9.8. Copy `contrib/bindings.lua`.\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any('Status: v0.9.8 but manifest.json says 0.9.9' in p
                            for p in problems), problems)

    def test_a_readme_version_that_matches_the_manifest_is_fine(self):
        self.write('README.md', 'Status: v0.9.9. Copy `contrib/bindings.lua`.\n')
        self.commit_all()
        self.assertEqual([], release.check(self.dir, out=io.StringIO()))

    def test_a_shipped_source_that_cites_a_dev_path_is_a_problem(self):
        """D-REL-2: 0.7.1 shipped 70 comments naming CLAUDE.md, docs/, tests/
        or scripts/ -- citations to files that do not exist in an install."""
        self.write(VERSION_PART, '// see docs/UX.md section 3 and CLAUDE.md rule 12\n'
                   'var PLUGIN_VERSION = "0.9.9"\n')
        self.write('bin/omarchy-iptv', '#!/usr/bin/env python3\n# pinned by tests/fixtures/x.json\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("%s:1 names 'docs/UX.md'" % VERSION_PART in p for p in problems), problems)
        self.assertTrue(any("bin/omarchy-iptv:2 names 'tests/fixtures/x.json'" in p for p in problems), problems)

    def test_a_helper_part_is_a_shipped_source_too(self):
        """D-REL-7. The parts carry the comments the one-file helper did, so
        the citation scan reads them: a part citing a path the install lacks
        is the same D-REL-2 problem as the stub doing it."""
        self.write(HELPER_PARTS[3], '# measured by tests/test_logo_chunks.py\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("%s:1 names 'tests/test_logo_chunks.py'" % HELPER_PARTS[3] in p
                            for p in problems), problems)

    # -- the helper's parts (D-REL-7) --------------------------------------

    def test_a_part_the_stub_loads_must_be_on_the_allowlist(self):
        """The prototype of the split showed this check green while the
        artifact it would build shipped a stub naming parts it did not carry:
        a helper that cannot start on any install."""
        extra = 'bin/helper/12-extra.py'
        self.write(extra, '# a part nobody listed\n')
        self.write('bin/omarchy-iptv', helper_stub(HELPER_PARTS + [extra]))
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any(extra in p and 'not on the allowlist' in p for p in problems), problems)

    def test_an_allowlisted_part_the_stub_does_not_load_is_a_problem(self):
        dropped = HELPER_PARTS[5]
        self.write('bin/omarchy-iptv', helper_stub([p for p in HELPER_PARTS if p != dropped]))
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any(dropped in p and 'does not load' in p for p in problems), problems)

    def test_a_stub_whose_part_list_cannot_be_read_is_a_problem(self):
        self.write('bin/omarchy-iptv', '#!/usr/bin/env python3\nHELPER_PARTS = tuple(PARTS)\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any('HELPER_PARTS is not a literal' in p for p in problems), problems)

    def test_the_whole_helper_ships_and_nothing_else_under_bin(self):
        self.write('bin/helper/notes.txt', 'scratch\n')
        self.commit_all()
        self.build()
        tree = self.main_tree()
        self.assertTrue(set(HELPER_PARTS) <= tree, sorted(set(HELPER_PARTS) - tree))
        self.assertNotIn('bin/helper/notes.txt', tree)

    def test_a_shipped_source_naming_the_rule_and_the_branch_is_fine(self):
        self.write(VERSION_PART, '// engineering rule 12 (dev branch); UX.md section 3 on the dev branch\n'
                   'var PLUGIN_VERSION = "0.9.9"\n')
        self.commit_all()
        self.assertEqual([], release.check(self.dir, out=io.StringIO()))

    # -- the model's modules (D-REL-5) -------------------------------------

    def test_a_part_the_aggregator_loads_must_be_on_the_allowlist(self):
        """A part cut out of the model and not added to ALLOWLIST would ship
        a Model.mjs whose import fails on every install."""
        self.write('model/extra.mjs', 'var EXTRA = 1\nexport { EXTRA }\n')
        self.write('Model.mjs', aggregator(PARTS + ['model/extra.mjs']))
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("Model.mjs loads './model/extra.mjs' at runtime and it is not on "
                            "the allowlist" in p for p in problems), problems)

    def test_an_import_between_parts_is_followed(self):
        """The generated import block closes on its own line; a part another
        PART imports is as much a runtime file as one the aggregator names."""
        self.write('model/hidden.mjs', 'var HIDDEN = 1\nexport { HIDDEN }\n')
        self.write(PARTS[-1], 'import {\n  HIDDEN\n} from "./hidden.mjs"\nvar LAST = HIDDEN\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("%s loads './hidden.mjs' at runtime and it is not on the allowlist"
                            % PARTS[-1] in p for p in problems), problems)

    def test_an_allowlisted_module_nothing_loads_is_a_problem(self):
        self.write('Model.mjs', aggregator(PARTS[:-1]))
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any('%s is on the allowlist but nothing the plugin loads imports it'
                            % PARTS[-1] in p for p in problems), problems)

    def test_a_module_reaching_outside_the_plugin_is_a_problem(self):
        self.write(PARTS[-1], 'import { X } from "../../elsewhere.mjs"\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("loads '../../elsewhere.mjs', which is outside the plugin directory" in p
                            for p in problems), problems)

    # Every static form the engine accepts (measured on Qt 6.11.2: single
    # quotes load in QML, in a module and in a classic script's .import).
    # The round-1 lens put a single-quoted orphan import in a part and this
    # check passed it; only split-model's column-0 rule caught it.
    def assert_orphan_found(self, rel, text, ref):
        self.write('model/orphan.mjs', 'var ORPHAN = 1\nexport { ORPHAN }\n')
        self.write(rel, text)
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("%s loads '%s' at runtime and it is not on the allowlist" % (rel, ref) in p
                            for p in problems), problems)

    def test_a_single_quoted_import_from_is_followed(self):
        self.assert_orphan_found(PARTS[-1], "import { ORPHAN } from './orphan.mjs'\n", './orphan.mjs')

    def test_a_double_quoted_one_line_import_from_is_followed(self):
        self.assert_orphan_found(PARTS[-1], 'import { ORPHAN } from "./orphan.mjs";\n', './orphan.mjs')

    def test_a_namespace_and_default_import_are_followed(self):
        self.assert_orphan_found(PARTS[-1], "import * as O from './orphan.mjs'\n", './orphan.mjs')
        self.assert_orphan_found(PARTS[-1], 'import O, { ORPHAN } from "./orphan.mjs"\n', './orphan.mjs')

    def test_a_single_quoted_export_from_is_followed(self):
        self.assert_orphan_found(PARTS[-1], "export * from './orphan.mjs'\n", './orphan.mjs')
        self.assert_orphan_found(PARTS[-1], "export { ORPHAN as O } from './orphan.mjs'\n", './orphan.mjs')

    def test_a_bare_import_is_followed_in_either_quoting(self):
        self.assert_orphan_found(PARTS[-1], "import './orphan.mjs'\n", './orphan.mjs')
        self.assert_orphan_found(PARTS[-1], 'import "./orphan.mjs"\n', './orphan.mjs')

    def test_a_from_on_its_own_line_is_followed(self):
        self.assert_orphan_found(PARTS[-1], "import {\n  ORPHAN\n}\nfrom './orphan.mjs'\n", './orphan.mjs')

    def test_a_single_quoted_qml_import_is_followed(self):
        self.write('Extra.js', 'x\n')
        self.write('Guide.qml', "import 'Extra.js' as Extra\nx: Qt.resolvedUrl('bin/elsewhere')\n")
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("Guide.qml loads 'Extra.js'" in p for p in problems), problems)
        self.assertTrue(any("Guide.qml loads 'bin/elsewhere'" in p for p in problems), problems)

    def test_a_classic_script_dot_import_is_followed(self):
        self.write('lib.js', ".import 'orphan.js' as O\nfunction f() {}\n")
        self.write('orphan.js', 'function g() {}\n')
        self.write('Guide.qml', 'import "lib.js" as Lib\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("Guide.qml loads 'lib.js'" in p for p in problems), problems)
        # lib.js is not allowlisted, so it is not followed; allowlist it in a
        # fresh case to show the .import itself is read.
        release_allow = release.ALLOWLIST
        try:
            release.ALLOWLIST = release_allow + ('lib.js',)
            problems = release.check(self.dir, out=io.StringIO())
        finally:
            release.ALLOWLIST = release_allow
        self.assertTrue(any("lib.js loads 'orphan.js' at runtime and it is not on the allowlist" in p
                            for p in problems), problems)

    def test_a_comment_that_reads_like_an_import_is_not_followed(self):
        self.write(PARTS[-1], "// import { X } from './nowhere.mjs'\n"
                              "// a dynamic import('./nowhere.mjs') would be refused\n"
                              "/* the old form\n * export * from './nowhere.mjs'\n */\nvar LAST = 1\n")
        self.commit_all()
        self.assertEqual([], release.check(self.dir, out=io.StringIO()))

    def test_a_dynamic_import_is_a_problem(self):
        self.write(PARTS[-1], "function load() { return import('./orphan.mjs') }\n")
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any('%s:1 imports dynamically' % PARTS[-1] in p for p in problems), problems)

    def test_an_unreadable_model_is_a_message_not_a_traceback(self):
        """model_files raising used to leave `m` None and the next branch read
        m.group: the gate went red on the traceback and the message that says
        why was never printed (the round-1 lens, P3)."""
        self.write('Model.mjs', '// an aggregator that names no part\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any(p.startswith('the model is unreadable: ') for p in problems), problems)

    # No shipped file names Model.js in the present tense (round 2, R5).
    def model_js_problems(self, rel, text):
        self.write(rel, text)
        self.commit_all()
        return [p for p in release.check(self.dir, out=io.StringIO()) if 'names Model.js' in p]

    def test_a_shipped_comment_naming_model_js_is_red_in_every_kind_of_file(self):
        for rel, text in (('Guide.qml', 'import "Model.mjs" as Model\n// the value lives in Model.js\n'),
                          ('bin/omarchy-iptv', '#!/usr/bin/env python3\n# Must match Model.js.\n'),
                          (PARTS[-1], '// see Model.js for why\n'),
                          ('README.md', 'The model is Model.js.\n'),
                          ('CHANGELOG.md', '# Changelog\n\n## 0.9.9 (%s)\n\n- Model.js got smaller\n' % TODAY),
                          ('contrib/bindings.lua', '-- calls into Model.js\n')):
            problems = [p for p in self.model_js_problems(rel, text) if p.startswith(rel + ':')]
            self.assertEqual(1, len(problems), (rel, problems))

    def test_a_name_followed_by_punctuation_is_still_red(self):
        # bin/omarchy-iptv:7415 at 1ebbc5b read "Mirror Model.js's ...", so the
        # possessive is a form that shipped; the D-REL-5 round-2 lens showed a
        # lookahead that also excludes the apostrophe passed every other test.
        for line in ("// Mirror Model.js's Math.trunc\n", '// (see Model.js)\n', '// in Model.js, then\n',
                     '// lives in Model.js.\n', '// "Model.js"\n'):
            self.assertEqual(1, len(self.model_js_problems('Guide.qml', line)), line)

    def test_an_import_of_model_js_by_path_is_red(self):
        self.assertEqual(1, len(self.model_js_problems('Guide.qml', 'import "./Model.js" as Model\n')))

    def test_history_that_names_its_commit_is_allowed(self):
        self.assertEqual([], self.model_js_problems(
            'Guide.qml', '// Model.js at 422c8e1 held this; Model.js at commit 0bd4515ab did too\n'))

    def test_history_without_a_commit_is_still_red(self):
        for line in ('// Model.js used to hold this\n', '// Model.js at some point\n',
                     '// Model.js at 422c8e1 and then Model.js\n'):
            self.assertEqual(1, len(self.model_js_problems('Guide.qml', line)), line)

    def test_other_names_are_not_model_js(self):
        self.assertEqual([], self.model_js_problems(
            'Guide.qml', '// Model.mjs, Model.json, Model.test.js, xModel.js\n'))

    def test_a_file_that_does_not_ship_may_name_model_js(self):
        self.assertEqual([], self.model_js_problems('tests/test_x.py', '# Model.js\n'))

    def test_every_reached_module_is_scanned_for_dev_paths(self):
        self.write(PARTS[-1], '// pinned by tests/fixtures/x.json\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any("%s:1 names 'tests/fixtures/x.json'" % PARTS[-1] in p
                            for p in problems), problems)

    def test_the_real_tree_reaches_the_whole_model(self):
        out = io.StringIO()
        self.assertEqual([], release.check(ROOT, out=out))
        self.assertIn('%d runtime sources scanned' % (3 + len(model_files.model_paths(ROOT))),
                      out.getvalue())

    # -- the size ceiling (D-REL-5) -----------------------------------------

    def test_the_ceiling_sits_64_kib_under_the_scanners_limit(self):
        self.assertEqual(release.SCANNER_FILE_LIMIT, 524288)   # 512 * 1024, the marketplace's number
        self.assertEqual(release.FILE_CEILING, 458752)         # 448 KiB
        self.assertEqual(release.SCANNER_FILE_LIMIT - release.FILE_CEILING, 64 * 1024)

    def test_a_shipped_file_over_the_ceiling_is_red(self):
        """The failure the marketplace hit at 0.13.5, with 64 KiB to spare."""
        self.write(PARTS[-1], '//' + 'x' * (release.FILE_CEILING - 2) + '\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any('%s is %d bytes, over the %d-byte ceiling'
                            % (PARTS[-1], release.FILE_CEILING + 1, release.FILE_CEILING) in p
                            for p in problems), problems)

    def test_a_shipped_file_at_the_ceiling_is_fine(self):
        self.write(PARTS[-1], '//' + 'x' * (release.FILE_CEILING - 3) + '\n')
        self.commit_all()
        out = io.StringIO()
        self.assertEqual([], release.check(self.dir, out=out))
        self.assertIn('largest %s at %d of %d bytes' % (PARTS[-1], release.FILE_CEILING, release.FILE_CEILING),
                      out.getvalue())

    def test_the_executable_helper_is_held_to_the_ceiling_too(self):
        """The scanner exempts executables from its size limit, and that is a
        hole rather than a pass: an oversized mode-100755 file is probed as a
        binary instead of being scanned, so a helper past the limit would
        ship UNREAD. This does not exempt it.

        The fixture must BE executable, on disk and in git, or the test proves
        nothing about executables: the first version wrote it 0644 and the
        D-REL-5 lens's mutation C4 (`and not os.access(path, os.X_OK)` on the
        ceiling) survived it. Seen red against that mutation since."""
        path = os.path.join(self.dir, 'bin', 'omarchy-iptv')
        self.write('bin/omarchy-iptv', '#!/usr/bin/env python3\n#' + 'x' * release.FILE_CEILING + '\n')
        os.chmod(path, 0o755)
        self.commit_all()
        self.assertTrue(os.access(path, os.X_OK), 'the fixture helper is not executable')
        self.assertTrue(self.git('ls-files', '-s', 'bin/omarchy-iptv').startswith('100755 '),
                        'git does not record the fixture helper as executable')
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any(p.startswith('bin/omarchy-iptv is ') and 'ceiling' in p for p in problems), problems)

    def test_the_real_tree_is_under_the_ceiling(self):
        for path in release.ALLOWLIST:
            self.assertLessEqual(os.path.getsize(os.path.join(ROOT, path)), release.FILE_CEILING, path)

    def test_a_manifest_entry_point_outside_the_allowlist_is_a_problem(self):
        self.write('manifest.json', '{"version": "0.9.9", "entryPoints": '
                   '{"overlay": "Other.qml"}}\n')
        self.commit_all()
        problems = release.check(self.dir, out=io.StringIO())
        self.assertTrue(any('Other.qml' in p for p in problems), problems)


if __name__ == '__main__':
    unittest.main()


class ChangelogHeadingTest(unittest.TestCase):
    """The join the 0.8.0 cut did not have.

    `build` reads the version from manifest.json alone, so nothing tied the
    changelog heading to it: 0.8.0 shipped a section dated the day before the
    release, and a cut made without editing the heading would ship an
    artifact whose own changelog says "(unreleased)".
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def write(self, version, heading):
        with io.open(os.path.join(self.root, 'manifest.json'), 'w', encoding='utf-8') as fh:
            fh.write(json.dumps({"version": version}))
        with io.open(os.path.join(self.root, 'CHANGELOG.md'), 'w', encoding='utf-8') as fh:
            fh.write("# Changelog\n\n%s\n\nthings\n" % heading)

    def test_the_cut_refuses_an_unreleased_heading(self):
        self.write("0.9.0", "## 0.9.0 (unreleased)")
        problems = release.changelog_problems(self.root, strict=True, today="2026-09-26")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("dated", problems[0])
        # Silent outside the cut, which is how a release is drafted.
        self.assertEqual(release.changelog_problems(self.root, strict=False), [])

    def test_the_cut_refuses_a_heading_for_another_version(self):
        self.write("0.9.0", "## 0.8.0 (2026-09-25)")
        problems = release.changelog_problems(self.root, strict=True, today="2026-09-26")
        self.assertTrue(any("wrong release notes" in p for p in problems), problems)

    def test_the_cut_refuses_yesterdays_date(self):
        """0.8.0's own symptom: the heading was written on the 25th and the
        build run on the 26th, so the shipped artifact is dated a day before
        it exists. Nothing compared the two."""
        self.write("0.9.0", "## 0.9.0 (2026-09-25)")
        problems = release.changelog_problems(self.root, strict=True, today="2026-09-26")
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("date the section on", problems[0])

    def test_a_dated_heading_for_this_version_passes_both_ways(self):
        self.write("0.9.0", "## 0.9.0 (2026-09-26)")
        self.assertEqual(release.changelog_problems(self.root, strict=True, today="2026-09-26"), [])
        self.assertEqual(release.changelog_problems(self.root, strict=False), [])

    def test_a_draft_ahead_of_the_manifest_is_normal_outside_the_cut(self):
        self.write("0.8.0", "## 0.9.0 (unreleased)")
        self.assertEqual(release.changelog_problems(self.root, strict=False), [])
        self.assertTrue(release.changelog_problems(self.root, strict=True, today="2026-09-26"))

    def test_the_cut_itself_refuses_it_and_not_only_the_helper(self):
        """The join. `changelog_problems` was tested and `build`'s single call
        to it was not, so deleting that line left every test green -- a rule
        13 name-join inside the repair that exists to stop one."""
        case = ReleaseCase('run')
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.write('CHANGELOG.md', '# Changelog\n\n## 0.9.9 (unreleased)\n\n- a thing\n')
        case.commit_all()
        with self.assertRaisesRegex(release.ReleaseError, 'release notes'):
            case.build()
        # And the same tree cuts once the heading is dated.
        case.write('CHANGELOG.md', '# Changelog\n\n## 0.9.9 (%s)\n\n- a thing\n' % TODAY)
        case.commit_all()
        case.build()

    def test_a_missing_heading_is_reported_rather_than_ignored(self):
        with io.open(os.path.join(self.root, 'manifest.json'), 'w', encoding='utf-8') as fh:
            fh.write(json.dumps({"version": "0.9.0"}))
        with io.open(os.path.join(self.root, 'CHANGELOG.md'), 'w', encoding='utf-8') as fh:
            fh.write("# Changelog\n\nno sections yet\n")
        self.assertTrue(release.changelog_problems(self.root, strict=True, today="2026-09-26"))

