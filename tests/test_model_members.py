"""scripts/check-model-members.py: a mistyped Model member in QML is red
(D-REL-5 round 2, R2).

Rule 12: every case calls the shipping function. Rule 14: one case runs the
REAL qmllint over a copy of a real entry point with one member mistyped, so
the check is proven against the sink it reads and not only against output
written by hand here.
"""

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    'check_model_members', os.path.join(ROOT, 'scripts', 'check-model-members.py'))
cmm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cmm)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import model_files  # noqa: E402

QMLLINT = os.path.join(os.environ.get('QT_BIN', '/usr/lib/qt6/bin'), 'qmllint')
QML_IMPORTS = os.environ.get('QML_IMPORTS', '/usr/lib/qt6/qml')
SHELL_DIR = os.path.join(os.environ.get('OMARCHY_PATH', '/usr/share/omarchy'), 'shell')


def warning(name, where='Service.qml:12:5'):
    return 'Warning: %s: Member "%s" not found on type "Model" [missing-property]\n' % (where, name)


IMPORTING = 'import QtQuick\nimport "Model.mjs" as Model\nItem {}\n'


class Judge(unittest.TestCase):

    def test_a_member_the_aggregator_exports_is_accepted(self):
        problems, count = cmm.problems_for(warning('redactUrls') + warning('PLUGIN_VERSION'),
                                           ['redactUrls', 'PLUGIN_VERSION'], IMPORTING, 'X.qml')
        self.assertEqual(([], 2), (problems, count))

    def test_a_member_the_aggregator_does_not_export_is_red_and_named(self):
        out = warning('redactUrls') + warning('zzBogusMember', 'Guide.qml:40:9')
        problems, count = cmm.problems_for(out, ['redactUrls'], IMPORTING, 'Guide.qml')
        self.assertEqual(2, count)
        self.assertEqual(1, len(problems), problems)
        self.assertIn('Guide.qml:40:9', problems[0])
        self.assertIn('Model.zzBogusMember', problems[0])

    def test_other_warnings_are_not_judged(self):
        out = ('Warning: Guide.qml:1:1: Unqualified access [unqualified]\n'
               'Warning: Guide.qml:2:1: Member "zz" not found on type "Style" [missing-property]\n'
               + warning('redactUrls'))
        self.assertEqual(([], 1), cmm.problems_for(out, ['redactUrls'], IMPORTING, 'Guide.qml'))

    def test_a_file_that_imports_the_model_and_yields_no_member_line_is_red(self):
        """Blind is not green: a qmllint that stops naming members, or starts
        resolving ES modules, would otherwise pass every typo silently."""
        problems, count = cmm.problems_for('Warning: X.qml:1:1: something else\n',
                                           ['redactUrls'], IMPORTING, 'X.qml')
        self.assertEqual(0, count)
        self.assertEqual(1, len(problems), problems)
        self.assertIn('reads nothing', problems[0])

    def test_a_file_that_does_not_import_the_model_may_yield_none(self):
        self.assertEqual(([], 0), cmm.problems_for('', ['redactUrls'], 'import QtQuick\nItem {}\n', 'X.qml'))

    def test_a_relative_import_of_the_model_counts_as_importing_it(self):
        problems, _ = cmm.problems_for('', ['x'], 'import "../Model.mjs" as Model\n', 'Model.spec.qml')
        self.assertEqual(1, len(problems), problems)

    def test_main_exits_one_and_prints_the_member(self):
        d = tempfile.mkdtemp(prefix='model-members-')
        self.addCleanup(shutil.rmtree, d, True)
        qml = os.path.join(d, 'X.qml')
        with open(qml, 'w') as fh:
            fh.write(IMPORTING)
        stdin, buf = sys.stdin, io.StringIO()
        try:
            sys.stdin = io.StringIO(warning('zzBogusMember'))
            with redirect_stdout(buf):
                rc = cmm.main(['--root', ROOT, '--file', qml])
        finally:
            sys.stdin = stdin
        self.assertEqual(1, rc)
        self.assertIn('Model.zzBogusMember', buf.getvalue())


class TheNamesAreTheModulesNames(unittest.TestCase):
    """The judge's list and the module are joined by NAME (rule 13), so the
    join is checked against what node actually loads."""

    def test_public_names_equal_the_loaded_namespace(self):
        if not shutil.which('node'):
            self.skipTest('node is not installed')
        script = ('import(process.argv[1]).then(M => console.log(JSON.stringify(Object.keys(M).sort())))')
        out = subprocess.run(['node', '-e', script, 'file://' + os.path.join(ROOT, 'Model.mjs')],
                             stdout=subprocess.PIPE, check=True).stdout.decode()
        self.assertEqual(json.loads(out), sorted(model_files.public_names(ROOT)))

    def test_an_aggregator_with_no_export_block_is_a_layout_error(self):
        d = tempfile.mkdtemp(prefix='model-members-')
        self.addCleanup(shutil.rmtree, d, True)
        with open(os.path.join(d, 'Model.mjs'), 'w') as fh:
            fh.write('// nothing\nexport {} from "./model/a.mjs"\n')
        with self.assertRaises(model_files.ModelLayoutError):
            model_files.public_names(d)


@unittest.skipUnless(os.access(QMLLINT, os.X_OK) and os.path.isdir(os.path.join(SHELL_DIR, 'Commons')),
                     'qmllint or the host shell is not installed')
class TheRealLinter(unittest.TestCase):
    """The real sink: qmllint over a copy of an entry point, with the real
    model beside it, one member mistyped."""

    def lint(self, name, edit):
        d = tempfile.mkdtemp(prefix='model-members-lint-')
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, 'qmlroot', 'qs'))
        os.symlink(os.path.join(SHELL_DIR, 'Commons'), os.path.join(d, 'qmlroot', 'qs', 'Commons'))
        os.symlink(os.path.join(SHELL_DIR, 'Ui'), os.path.join(d, 'qmlroot', 'qs', 'Ui'))
        model_files.copy_model(ROOT, d)
        with open(os.path.join(ROOT, name), encoding='utf-8') as fh:
            text = edit(fh.read())
        target = os.path.join(d, name)
        with open(target, 'w', encoding='utf-8') as fh:
            fh.write(text)
        out = subprocess.run([QMLLINT, '-I', os.path.join(d, 'qmlroot'), '-I', QML_IMPORTS, target],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.decode('utf-8', 'replace')
        return cmm.problems_for(out, model_files.public_names(ROOT), text, name)

    def test_the_real_bar_widget_is_clean(self):
        problems, count = self.lint('BarWidget.qml', lambda t: t)
        self.assertEqual([], problems)
        self.assertGreater(count, 0)

    def test_a_mistyped_member_in_the_real_bar_widget_is_red(self):
        def edit(t):
            self.assertIn('Model.barGlyph(', t)
            return t.replace('Model.barGlyph(', 'Model.zzBogusMember(', 1)
        problems, _ = self.lint('BarWidget.qml', edit)
        self.assertEqual(1, len(problems), problems)
        self.assertIn('Model.zzBogusMember', problems[0])


if __name__ == '__main__':
    unittest.main()
