"""scripts/build_stamps.py: every runtime file names its build (D-REL-16).

Rule 12: every case runs the shipping module -- its judge over the cases'
small tree (tests/fixtures/build-stamps/cases.json, the same cases --check
runs as its self-test), and its cut over a scratch git repository holding
THIS tree's 26 runtime files, read through release.py's own runtime_files.
Rule 11: each decision of the guard was broken one at a time in a copy of
the script and this suite went red for it; the mutants and the counts are
in docs/QA-RESULTS.md, "D-REL-16: the build stamps and their guard".
"""

import collections
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'scripts', 'build_stamps.py')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import build_stamps  # noqa: E402
import model_files  # noqa: E402
import service_files  # noqa: E402

GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME='test', GIT_AUTHOR_EMAIL='t@example.invalid',
               GIT_COMMITTER_NAME='test', GIT_COMMITTER_EMAIL='t@example.invalid',
               GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')


def read(path):
    with open(path, encoding='utf-8', newline='') as fh:
        return fh.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(text)


class TheTree(unittest.TestCase):
    """This tree, as the gate and release.py check read it."""

    def test_every_runtime_file_carries_its_stamp_and_the_table_agrees(self):
        found, stamps = build_stamps.stamps(ROOT)
        self.assertEqual([], [str(p) for p in found])
        order = build_stamps.runtime_order(ROOT)
        self.assertEqual(order, list(stamps))
        # The runtime files are the three QML entry points, the service's
        # code-behinds and the model's files, each read from its own reader.
        want = {'BarWidget.qml', 'Guide.qml'} | set(service_files.service_names(ROOT)) | set(model_files.model_paths(ROOT))
        self.assertEqual(want, set(order))
        for rel, value in stamps.items():
            self.assertTrue(build_stamps.version_key(value), (rel, value))
        with open(os.path.join(ROOT, 'manifest.json'), encoding='utf-8') as fh:
            self.assertEqual(json.load(fh)['version'], stamps[build_stamps.BUILD])

    def test_json_prints_the_stamps_the_judge_reads(self):
        out = subprocess.run([sys.executable, '-I', SCRIPT, '--json', '--root', ROOT],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        self.assertEqual(0, out.returncode, out.stderr)
        printed = json.loads(out.stdout.decode(), object_pairs_hook=collections.OrderedDict)
        self.assertEqual(build_stamps.stamps(ROOT)[1], printed)

    def test_check_judges_the_tree_and_runs_every_case(self):
        out = subprocess.run([sys.executable, '-I', SCRIPT, '--check', '--root', ROOT],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        text = out.stdout.decode()
        self.assertEqual(0, out.returncode, text)
        n = len(build_stamps.load_cases()['cases'])
        self.assertIn('build-stamps: check ok (26 runtime file(s), 26 stamp(s) read, 25 BUILD_FILES row(s); '
                      'self-test %d of %d cases)' % (n, n), text)


class TheCases(unittest.TestCase):
    """The fixture --check runs as its self-test, case by case."""

    def setUp(self):
        self.data = build_stamps.load_cases()

    def test_every_case_gets_its_verdict(self):
        for case in self.data['cases']:
            with self.subTest(case=case['name']):
                ok, got = build_stamps.run_case(case, self.data['base'])
                self.assertTrue(ok, got)

    def test_the_cases_hold_every_refusal_kind(self):
        seen = set()
        for case in self.data['cases']:
            want = case['expect']
            seen.add(want.get('refusal'))
            seen.add(want.get('refused'))
            if want.get('stale'):
                seen.add('stale')
        self.assertTrue(set(build_stamps.KINDS) <= seen, sorted(set(build_stamps.KINDS) - seen))
        modes = collections.Counter(case.get('mode', 'check') for case in self.data['cases'])
        self.assertGreaterEqual(modes['cut'], 3, modes)
        self.assertGreaterEqual(modes['strict'], 2, modes)

    def test_a_case_the_judge_gets_wrong_is_reported_and_reds_the_check(self):
        flipped = json.loads(json.dumps(self.data))
        flipped['cases'][1]['expect'] = {'refusal': 'twice'}
        where = tempfile.mkdtemp(prefix='build-stamps-test-')
        self.addCleanup(shutil.rmtree, where, True)
        path = os.path.join(where, 'cases.json')
        write(path, json.dumps(flipped))
        ran, wrong = build_stamps.self_test(path)
        self.assertEqual(len(flipped['cases']), ran)
        self.assertEqual(1, len(wrong), wrong)
        self.assertIn(flipped['cases'][1]['name'], wrong[0])
        out = io.StringIO()
        with mock.patch.object(build_stamps, 'self_test', lambda: (ran, wrong)):
            self.assertEqual(1, build_stamps.check(ROOT, out=out))
        self.assertIn('self-test case wrong', out.getvalue())
        self.assertNotIn('check ok', out.getvalue())

    def test_a_tree_problem_reds_the_check(self):
        out = io.StringIO()
        bad = [build_stamps.Problem('missing', 'Guide.qml', 0, 'carries no build stamp')]
        with mock.patch.object(build_stamps, 'stamps', lambda root, runtime=None: (bad, collections.OrderedDict())):
            self.assertEqual(1, build_stamps.check(ROOT, run_self_test=False, out=out))
        self.assertIn('Guide.qml: carries no build stamp [missing]', out.getvalue())


class TheTable(unittest.TestCase):
    """What a `table` refusal says: the kind alone would let one reason
    stand for another (a missing row also breaks the generated form)."""

    def setUp(self):
        data = build_stamps.load_cases()
        self.base = data['base']
        self.order = [rel for rel in self.base if rel != 'manifest.json']

    def problems(self, old, new):
        files = dict(self.base)
        self.assertEqual(1, files['model/build.mjs'].count(old))
        files['model/build.mjs'] = files['model/build.mjs'].replace(old, new)
        found, _read, _at = build_stamps.judge(files, self.order)
        return [str(p) for p in found]

    def test_a_missing_row_is_named(self):
        self.assertEqual(['model/build.mjs:7: BUILD_FILES has no row for model/text.mjs [table]'],
                         self.problems('  "model/text.mjs": "1.0.0",\n', ''))

    def test_an_extra_row_is_named(self):
        self.assertEqual(['model/build.mjs:7: BUILD_FILES has a row for README.md, which is no runtime file but '
                          'this one [table]'],
                         self.problems('  "model/form-edit.mjs": "1.2.0"\n', '  "model/form-edit.mjs": "1.2.0",\n  "README.md": "1.2.0"\n'))

    def test_rows_out_of_order_are_named(self):
        found = self.problems('  "BarWidget.qml": "1.2.0",\n  "Guide.qml": "1.1.0",\n',
                              '  "Guide.qml": "1.1.0",\n  "BarWidget.qml": "1.2.0",\n')
        self.assertEqual(1, len(found), found)
        self.assertIn('rows are not in the order the plugin loads them', found[0])

    def test_a_row_unequal_to_its_file_is_named_with_both_values(self):
        self.assertEqual(['model/build.mjs:9: the row for Guide.qml says 1.2.0, and the file carries 1.1.0 [table]'],
                         self.problems('  "Guide.qml": "1.1.0",', '  "Guide.qml": "1.2.0",'))

    def test_a_block_moved_off_plugin_version_is_named(self):
        self.assertEqual(['model/build.mjs:8: BUILD_FILES is not in its generated form directly under PLUGIN_VERSION '
                          '(its comment, then the table) [table]'],
                         self.problems('var PLUGIN_VERSION = "1.2.0"\n', 'var PLUGIN_VERSION = "1.2.0"\n\n'))


class TheNames(unittest.TestCase):

    def test_a_part_stamp_is_the_part_upper_cased_with_its_dashes_underscores(self):
        self.assertEqual('BUILD_STAMP_FORM_EDIT', build_stamps.stamp_name('model/form-edit.mjs', 'part', {}))
        self.assertEqual('BUILD_STAMP_SOURCE_RECORDS', build_stamps.stamp_name('model/source-records.mjs', 'part', {}))

    def test_a_code_behind_stamp_is_named_for_its_qualifiers_domain(self):
        quals = dict((f, q) for f, q, _n in service_files.declarations(read(os.path.join(ROOT, 'Service.qml'))))
        self.assertTrue(quals)
        for rel, q in quals.items():
            self.assertEqual('buildStamp' + q[len('Service'):], build_stamps.stamp_name(rel, 'code-behind', quals))
        self.assertEqual('buildStampPip', build_stamps.stamp_name('Service-pip.js', 'code-behind', quals))

    def test_each_form_reads_its_own_line_back(self):
        for kind in build_stamps.FORMS:
            line = build_stamps.stamp_line(kind, 'NAME', '1.2.3')
            m = build_stamps.exact(kind, 'NAME').fullmatch(line)
            self.assertTrue(m, (kind, line))
            self.assertEqual('1.2.3', m.group(1))


class TheCut(unittest.TestCase):
    """--cut and the cut's own check over a scratch repository holding this
    tree's 26 runtime files and its manifest: REF is a commit there, and the
    working tree is what a cut would commit."""

    def setUp(self):
        self.order = build_stamps.runtime_order(ROOT)
        self.dir = tempfile.mkdtemp(prefix='build-stamps-cut-')
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.git('init', '-q', '-b', 'dev')
        for rel in self.order + ['manifest.json']:
            write(os.path.join(self.dir, rel), read(os.path.join(ROOT, rel)))
        self.version = json.loads(read(os.path.join(ROOT, 'manifest.json')))['version']

    def git(self, *args):
        return subprocess.run(['git', '-C', self.dir] + list(args), check=True, env=GIT_ENV,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode()

    def commit_ref(self):
        self.git('add', '-A')
        self.git('commit', '-q', '-m', 'ref')
        self.git('branch', '-f', 'ref', 'HEAD')

    def edit(self, rel, old, new):
        path = os.path.join(self.dir, rel)
        text = read(path)
        self.assertEqual(1, text.count(old), (rel, old))
        write(path, text.replace(old, new))

    def bump(self, version):
        self.edit('manifest.json', '"version": "%s"' % self.version, '"version": "%s"' % version)
        self.edit(build_stamps.BUILD, 'var PLUGIN_VERSION = "%s"' % self.version, 'var PLUGIN_VERSION = "%s"' % version)

    def cut(self):
        return build_stamps.cut(self.dir, 'ref', runtime=self.order, out=io.StringIO())

    def stamps(self):
        found, read_ = build_stamps.stamps(self.dir, runtime=self.order)
        self.assertEqual([], [str(p) for p in found])
        return read_

    def snapshot(self):
        out = {}
        for top, _dirs, files in os.walk(self.dir):
            if '.git' in top.split(os.sep):
                continue
            for name in files:
                path = os.path.join(top, name)
                out[os.path.relpath(path, self.dir)] = read(path)
        return out

    def unstamped(self):
        """Every stamp line out of the scratch copy, and BUILD_FILES out of
        build.mjs: a REF from before the stamps, as main is at 0.20.0."""
        texts = build_stamps.read_texts(self.dir, self.order)
        found, read_, at = build_stamps.judge(texts, self.order)
        self.assertEqual([], found)
        for rel in self.order:
            lines = texts[rel].split('\n')
            if rel == build_stamps.BUILD:
                start = at[rel] + 1
                end = next(i for i in range(start, len(lines)) if lines[i] == '}')
                del lines[start:end + 1]
            else:
                del lines[at[rel]]
            write(os.path.join(self.dir, rel), '\n'.join(lines))
        found, _read, _at = build_stamps.judge(build_stamps.read_texts(self.dir, self.order), self.order)
        self.assertEqual(sorted(['missing'] * 25 + ['table']), sorted(p.kind for p in found))

    def test_a_ref_without_stamps_restamps_all_26_and_a_second_cut_changes_nothing(self):
        self.unstamped()
        self.commit_ref()
        for rel in self.order + ['manifest.json']:
            write(os.path.join(self.dir, rel), read(os.path.join(ROOT, rel)))
        self.bump('9.9.9')
        self.assertEqual(25, len(build_stamps.cut_problems(self.dir, 'ref', '9.9.9', runtime=self.order)))
        written = self.cut()
        self.assertEqual(self.order, written)
        self.assertEqual(dict((rel, '9.9.9') for rel in self.order), dict(self.stamps()))
        self.assertEqual([], build_stamps.cut_problems(self.dir, 'ref', '9.9.9', runtime=self.order))
        before = self.snapshot()
        self.assertEqual([], self.cut())
        self.assertEqual(before, self.snapshot())

    def test_only_the_files_that_changed_take_the_version(self):
        self.commit_ref()
        self.bump('9.9.9')
        changed = ['Guide.qml', 'Service-pip.js', 'model/text.mjs']
        for rel in changed:
            with open(os.path.join(self.dir, rel), 'a', encoding='utf-8') as fh:
                fh.write('// changed\n')
        stale = build_stamps.cut_problems(self.dir, 'ref', '9.9.9', runtime=self.order)
        self.assertEqual(changed, [p.file for p in stale])
        self.assertEqual({'stale'}, set(p.kind for p in stale))
        written = self.cut()
        self.assertEqual([rel for rel in self.order if rel in changed or rel == build_stamps.BUILD], written)
        stamps = self.stamps()
        for rel in self.order:
            want = '9.9.9' if rel in changed or rel == build_stamps.BUILD else build_stamps.stamps(ROOT)[1][rel]
            self.assertEqual(want, stamps[rel], rel)
        self.assertEqual([], build_stamps.cut_problems(self.dir, 'ref', '9.9.9', runtime=self.order))
        self.assertEqual([], self.cut())

    def test_a_refused_cut_writes_nothing(self):
        self.commit_ref()
        self.bump('9.9.9')
        self.edit('Guide.qml', '  readonly property string buildStamp: "%s"\n' % build_stamps.stamps(ROOT)[1]['Guide.qml'], '')
        with open(os.path.join(self.dir, 'Service.qml'), 'a', encoding='utf-8') as fh:
            fh.write('// changed\n')
        before = self.snapshot()
        with self.assertRaises(build_stamps.Refused) as refused:
            self.cut()
        self.assertEqual(['missing'], [p.kind for p in refused.exception.problems])
        self.assertEqual(before, self.snapshot())

    def test_a_cut_before_the_plugin_version_is_bumped_is_refused(self):
        self.commit_ref()
        self.edit('manifest.json', '"version": "%s"' % self.version, '"version": "9.9.9"')
        before = self.snapshot()
        with self.assertRaises(build_stamps.Refused) as refused:
            self.cut()
        self.assertEqual(['stale'], [p.kind for p in refused.exception.problems])
        self.assertEqual(before, self.snapshot())

    def test_a_ref_that_names_nothing_is_an_error_not_a_verdict(self):
        self.commit_ref()
        self.bump('9.9.9')
        with self.assertRaisesRegex(build_stamps.BuildStampsError, 'no-such-ref names no commit'):
            build_stamps.cut(self.dir, 'no-such-ref', runtime=self.order, out=io.StringIO())
        with self.assertRaises(build_stamps.BuildStampsError):
            build_stamps.cut_problems(self.dir, 'no-such-ref', '9.9.9', runtime=self.order)

    def test_the_cut_compares_the_blob_git_would_store(self):
        """A working copy that differs from REF only where the repository's
        own filters fold it back is the blob REF holds: unchanged, so its
        stamp stays. ident folds `$Id: <hex> $` to `$Id$` on add."""
        write(os.path.join(self.dir, '.gitattributes'), 'BarWidget.qml ident\n')
        self.edit('BarWidget.qml', '  id: root\n', '  id: root\n  // $Id$\n')
        self.commit_ref()
        self.bump('9.9.9')
        self.edit('BarWidget.qml', '// $Id$', '// $Id: 0123456789abcdef0123456789abcdef01234567 $')
        self.assertEqual([], build_stamps.cut_problems(self.dir, 'ref', '9.9.9', runtime=self.order))
        self.assertNotIn('BarWidget.qml', self.cut())
        self.assertEqual(build_stamps.stamps(ROOT)[1]['BarWidget.qml'], self.stamps()['BarWidget.qml'])

    def test_the_cut_writes_inside_the_tree_and_leaves_no_temporary_file(self):
        self.commit_ref()
        self.bump('9.9.9')
        with open(os.path.join(self.dir, 'Guide.qml'), 'a', encoding='utf-8') as fh:
            fh.write('// changed\n')
        mode = os.stat(os.path.join(self.dir, 'Guide.qml')).st_mode
        self.cut()
        status = self.git('status', '--porcelain', '--untracked-files=all')
        self.assertEqual(sorted([' M Guide.qml', ' M manifest.json', ' M model/build.mjs']),
                         sorted(line for line in status.split('\n') if line))
        self.assertEqual(mode, os.stat(os.path.join(self.dir, 'Guide.qml')).st_mode)

    def test_the_cli_cut_and_strict_say_what_they_did(self):
        self.commit_ref()
        self.bump('9.9.9')
        with open(os.path.join(self.dir, 'Guide.qml'), 'a', encoding='utf-8') as fh:
            fh.write('// changed\n')
        # The scratch tree has no release.py to read its runtime files from,
        # so the CLI is driven through main() with the order handed in.
        with mock.patch.object(build_stamps, 'runtime_order', lambda root: self.order):
            out = io.StringIO()
            with mock.patch('sys.stdout', out):
                self.assertEqual(1, build_stamps.main(['--strict', '--root', self.dir, '--against', 'ref']))
                self.assertEqual(0, build_stamps.main(['--cut', '--root', self.dir, '--against', 'ref']))
                self.assertEqual(0, build_stamps.main(['--strict', '--root', self.dir, '--against', 'ref']))
        text = out.getvalue()
        self.assertIn('Guide.qml', text.split('\n')[0])
        self.assertIn('[stale]', text.split('\n')[0])
        self.assertIn('build-stamps: cut 9.9.9 against ref: wrote Guide.qml, model/build.mjs', text)
        self.assertIn('build-stamps: strict ok against ref', text)


if __name__ == '__main__':
    unittest.main()
