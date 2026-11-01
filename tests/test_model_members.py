"""scripts/check-model-members.py: a mistyped Model member in QML is red
(D-REL-5 round 2, R2; repaired for Qt 6.12, 2026-10-31).

Rule 12: every case calls the shipping function. Rule 14: the guard reads
the QML source, so the real sink is the shipped QML itself -- every case
under TheRealSources edits a copy of a real file the gate lints and runs the
guard on it. What holds the SCANNER to a real reading of those files is
TheRealLinter: every Model-member position the real qmllint reports, in each
file the gate lints, must be one the scanner found. The guard never consults
qmllint; that case is the scanner's fidelity check, and it refuses to pass
blind when qmllint reports no position at all.
"""

import importlib.util
import io
import json
import os
import re
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
HARNESS_DIR = os.path.join(ROOT, 'scripts', 'dev-harness')

HEAD = 'import QtQuick\nimport "Model.mjs" as Model\n'
NAMES = ['redactUrls', 'PLUGIN_VERSION', 'GLYPHS']


def judge(body, names=NAMES, head=HEAD, label='X.qml'):
    return cmm.problems_for(head + body, names, label)


def linted_files():
    """The QML files check.sh's qmllint step judges, in its order: the root
    entry points, the QML spec, and the harness fake."""
    out = []
    for d in (ROOT, os.path.join(ROOT, 'tests'), HARNESS_DIR):
        out += sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith('.qml'))
    return out


def read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


class Judge(unittest.TestCase):

    def test_a_member_the_aggregator_exports_is_accepted(self):
        self.assertEqual(([], 2), judge('Item { property string a: Model.redactUrls(Model.PLUGIN_VERSION) }\n'))

    def test_a_member_the_aggregator_does_not_export_is_red_and_named(self):
        problems, count = judge('Item {\n  property string a: Model.redactUrls("x")\n'
                                '  property string b: Model.zzBogusMember("x")\n}\n', label='Guide.qml')
        self.assertEqual(2, count)
        self.assertEqual(1, len(problems), problems)
        self.assertIn('Guide.qml:5:28', problems[0])
        self.assertIn('Model.zzBogusMember', problems[0])

    def test_a_member_inside_another_members_arguments_is_judged(self):
        """The position qmllint never reached: an argument of another call."""
        problems, count = judge('Item { property string a: Model.redactUrls(Model.zzNested(1), 2) }\n')
        self.assertEqual(2, count)
        self.assertEqual(1, len(problems), problems)
        self.assertIn('Model.zzNested', problems[0])

    def test_optional_and_literal_index_access_are_judged(self):
        problems, count = judge('Item { property var a: [Model?.zzOpt, Model["zzIndex"], Model.GLYPHS.x] }\n')
        self.assertEqual(3, count)
        self.assertEqual(2, len(problems), problems)
        self.assertIn('Model.zzOpt', problems[0])
        self.assertIn('Model.zzIndex', problems[1])

    def test_an_access_split_over_lines_is_judged(self):
        problems, _ = judge('Item { function f() { return Model\n      .zzSplit() } }\n')
        self.assertEqual(1, len(problems), problems)
        self.assertIn('X.qml:4:8', problems[0])

    def test_a_name_in_a_comment_or_a_string_is_not_judged(self):
        body = ('// Model.zzLine is a comment\n'
                '/* Model.zzBlock\n   Model.zzBlock2 */\n'
                'Item {\n'
                '  property string a: "Model.zzDouble" + \'Model.zzSingle\' + `Model.zzTemplate`\n'
                '  property string b: Model.redactUrls(a) // Model.zzTrailing\n'
                '}\n')
        self.assertEqual(([], 1), judge(body))

    def test_a_template_substitution_is_code(self):
        problems, count = judge('Item { property string a: `x ${Model.zzInTemplate({ k: `${Model.redactUrls(1)}` })} y` }\n')
        self.assertEqual(2, count)
        self.assertEqual(1, len(problems), problems)
        self.assertIn('Model.zzInTemplate', problems[0])

    def test_a_regular_expression_does_not_open_a_comment_or_a_string(self):
        """`//`, `/*` and a quote inside a regex literal are the regex's: the
        code after it, on that line and the next, is still read."""
        body = ('Item {\n'
                '  property bool a: /^file:\\/\\//.test(x) && Model.zzAfterSlashes(1)\n'
                '  property bool b: /[/*"\']/.test(x)\n'
                '  property bool c: Model.zzNextLine()\n'
                '}\n')
        problems, count = judge(body)
        self.assertEqual(2, count)
        self.assertEqual(['Model.zzAfterSlashes', 'Model.zzNextLine'],
                         [re.search(r'Model\.\w+', p).group(0) for p in problems])

    def test_a_division_is_not_a_regular_expression(self):
        problems, count = judge('Item { property real a: width / 2 + Model.zzDivided / 3 }\n')
        self.assertEqual(1, count)
        self.assertEqual(1, len(problems), problems)
        self.assertIn('Model.zzDivided', problems[0])

    def test_a_division_after_a_keyword_named_property_is_not_a_regular_expression(self):
        """`return /x/` opens a regex; `page.of / 2` divides. Read as a regex
        the slash would take the rest of the line with it, the member in it
        included, and nothing would say so."""
        for lhs in ('page.of', 'root.in', 'item?.delete', 'x.return'):
            problems, count = judge('Item { property real a: %s / 2 + Model.zzDivided / 3 }\n' % lhs)
            self.assertEqual(1, count, lhs)
            self.assertEqual(1, len(problems), (lhs, problems))
            self.assertIn('Model.zzDivided', problems[0])
        # The keyword itself still opens one: read as a division, the quote
        # in it would open a string that never closes on the line.
        self.assertEqual(([], 1), judge('Item { function f(s) { return /\'/.test(s) && Model.redactUrls(s) } }\n'))

    def test_someone_elses_property_of_the_same_name_is_not_judged(self):
        self.assertEqual(([], 1), judge('Item { property var a: [root.Model.zzOther, Model.redactUrls] }\n'))

    def test_the_alias_is_read_from_the_import(self):
        head = 'import QtQuick\nimport "../Model.mjs" as M\n'
        problems, count = judge('Item { property var a: [M.zzAliased, M.redactUrls, Model.zzNotTheModel] }\n',
                                head=head)
        self.assertEqual(2, count)
        self.assertEqual(1, len(problems), problems)
        self.assertIn('Model.zzAliased', problems[0])

    def test_a_file_that_imports_the_model_and_yields_no_reference_is_red(self):
        """Blind is not green: a file that imports the model and has no
        reference the scanner can see means it read nothing."""
        problems, count = judge('Item {}\n// Model.redactUrls only in a comment\n')
        self.assertEqual(0, count)
        self.assertEqual(1, len(problems), problems)
        self.assertIn('read nothing', problems[0])

    def test_a_file_that_does_not_import_the_model_may_yield_none(self):
        self.assertEqual(([], 0), cmm.problems_for('import QtQuick\nItem { property int a: Model.zz }\n',
                                                   NAMES, 'X.qml'))

    def test_a_relative_import_of_the_model_counts_as_importing_it(self):
        problems, _ = cmm.problems_for('import "../Model.mjs" as Model\nItem {}\n', ['x'], 'Model.spec.qml')
        self.assertEqual(1, len(problems), problems)

    def test_the_model_used_as_a_value_is_red(self):
        for body in ('Item { property var m: Model }\n',
                     'Item { function f() { return helper(Model, 1) } }\n',
                     'Item { property var a: Model[name] }\n'):
            problems, _ = judge(body + 'Item { property var b: Model.redactUrls }\n')
            self.assertEqual(1, len(problems), (body, problems))
            self.assertIn('cannot judge', problems[0])

    def test_the_model_handed_whole_to_another_imported_script_is_reported_not_red(self):
        """The harness hands the model to harness-lib.js, whose uses
        qa-lib-test.sh runs with the real model in node."""
        head = HEAD + 'import "harness-lib.js" as Lib\n'
        body = 'Item { function f(e) { return Lib.entryKey(Model, Model.redactUrls(e)) } }\n'
        problems, refs, handed = cmm.judge(head + body, NAMES, 'shell.qml')
        self.assertEqual([], problems)
        self.assertEqual(1, len(refs))
        self.assertEqual([(4, 44, 'Lib.entryKey')], handed)
        # Not an imported script, or not a whole argument: red.
        for bad in ('Item { function f(e) { return Other.entryKey(Model, Model.redactUrls(e)) } }\n',
                    'Item { function f(e) { return Lib.entryKey(Model || e, Model.redactUrls(e)) } }\n'):
            problems, _ = cmm.problems_for(head + bad, NAMES, 'shell.qml')
            self.assertEqual(1, len(problems), (bad, problems))

    def test_a_scanner_that_lost_its_place_is_red(self):
        for body, what in (('Item { property string a: "never closed }\n', 'newline inside a quoted string'),
                           ('Item { property string a: Model.redactUrls(1) }\n/* never closed\n', 'block comment'),
                           ('Item { property string a: Model.redactUrls(`never closed) }\n', 'template literal'),
                           ('Item { property string a: `${Model.redactUrls(1)`\n}\n', 'template literal')):
            problems, count = judge(body)
            self.assertEqual(0, count, body)
            self.assertEqual(1, len(problems), (body, problems))
            self.assertIn('lost its place', problems[0])
            self.assertIn(what, problems[0])

    def test_main_exits_one_and_prints_the_member(self):
        d = tempfile.mkdtemp(prefix='model-members-')
        self.addCleanup(shutil.rmtree, d, True)
        good, bad = os.path.join(d, 'Good.qml'), os.path.join(d, 'Bad.qml')
        with open(good, 'w') as fh:
            fh.write(HEAD + 'Item { property string v: Model.PLUGIN_VERSION }\n')
        with open(bad, 'w') as fh:
            fh.write(HEAD + 'Item { property string v: Model.zzBogusMember }\n')
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmm.main(['--root', ROOT, '--file', good, '--file', bad])
        self.assertEqual(1, rc)
        self.assertIn('Bad.qml:3:33: `Model.zzBogusMember`', buf.getvalue())
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmm.main(['--root', ROOT, '--file', good])
        self.assertEqual(0, rc)
        self.assertIn('Good.qml: 1 Model reference(s) in code', buf.getvalue())

    def test_main_refuses_an_unreadable_file(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmm.main(['--root', ROOT, '--file', os.path.join(ROOT, 'no-such-file.qml')])
        self.assertEqual(1, rc)
        self.assertIn('unreadable', buf.getvalue())


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


class TheRealSources(unittest.TestCase):
    """The sink the guard reads is the QML itself: the real files, as the gate
    passes them, and copies of them with one member mistyped."""

    def setUp(self):
        self.names = model_files.public_names(ROOT)

    def mistyped(self, rel, needle, replacement):
        text = read(os.path.join(ROOT, rel))
        self.assertIn(needle, text, rel)
        return cmm.problems_for(text.replace(needle, replacement, 1), self.names, os.path.basename(rel))

    def test_every_file_the_gate_lints_is_clean_and_read(self):
        files = linted_files()
        self.assertGreaterEqual(len(files), 5, files)
        for path in files:
            problems, refs, _ = cmm.judge(read(path), self.names, os.path.basename(path))
            self.assertEqual([], problems, path)
            self.assertGreater(len(refs), 0, path)

    def test_through_main_as_the_gate_calls_it(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cmm.main(['--root', ROOT] + sum((['--file', f] for f in linted_files()), []))
        self.assertEqual(0, rc, buf.getvalue())
        self.assertIn('handed whole to HarnessLib.entryKey', buf.getvalue())

    def test_a_mistyped_member_in_the_real_bar_widget_is_red(self):
        """The case that went green on Qt 6.12's qmllint, whose text output
        carries no line for BarWidget.qml:86 at all."""
        problems, _ = self.mistyped('BarWidget.qml', 'Model.barGlyph(', 'Model.zzBogusMember(')
        self.assertEqual(1, len(problems), problems)
        self.assertIn('BarWidget.qml:86:', problems[0])
        self.assertIn('Model.zzBogusMember', problems[0])

    def test_a_mistyped_member_in_each_real_file_is_red(self):
        cases = (('Guide.qml', 'Model.captionAlpha(', 'Model.captionAlpah('),
                 ('Service.qml', 'Model.redactUrls(', 'Model.redactUrl('),
                 ('tests/Model.spec.qml', 'Model.searchKey(', 'Model.serachKey('),
                 ('scripts/dev-harness/shell.qml', 'Model.findBarEntry(', 'Model.findBarEntyr('))
        for rel, needle, typo in cases:
            problems, _ = self.mistyped(rel, needle, typo)
            self.assertEqual(1, len(problems), (rel, problems))
            self.assertIn(typo.rstrip('('), problems[0])

    def test_a_mistyped_member_in_a_nested_argument_of_a_real_file_is_red(self):
        """Positions qmllint never reported: a constant passed to another
        member, and a call inside another call's arguments."""
        cases = (('Guide.qml', 'Color.menu.background, Model.CAPTION_FLOOR_REGULAR',
                  'Color.menu.background, Model.CAPTION_FLOOR_REGULR'),
                 ('Guide.qml', 'Model.captionAlpha(Color.menu.text, Model.qmlFill(',
                  'Model.captionAlpha(Color.menu.text, Model.qmlFil('),
                 ('Service.qml', 'Model.MAX_CHNO_LABEL)', 'Model.MAX_CHNO_LABLE)'))
        for rel, needle, typo in cases:
            problems, _ = self.mistyped(rel, needle, typo)
            self.assertEqual(1, len(problems), (rel, problems))
            self.assertIn(re.findall(r'Model\.\w+', typo)[-1], problems[0])


@unittest.skipUnless(os.access(QMLLINT, os.X_OK) and os.path.isdir(os.path.join(SHELL_DIR, 'Commons')),
                     'qmllint or the host shell is not installed')
class TheRealLinter(unittest.TestCase):
    """The scanner's fidelity: qmllint's JSON output, over each file the gate
    lints (the harness fake staged beside the model as check.sh stages it),
    names a Model-member warning at the column of every member it reaches.
    Every one of those positions must be a reference the scanner found. JSON
    and not the text output, because qmllint 6.12.0's text output prints only
    a trailing run of what it found."""

    MEMBER = re.compile(r'^Member "(?P<name>[^"]+)" not found on type "Model"')

    def setUp(self):
        self.d = tempfile.mkdtemp(prefix='model-members-lint-')
        self.addCleanup(shutil.rmtree, self.d, True)
        os.makedirs(os.path.join(self.d, 'qmlroot', 'qs'))
        for part in ('Commons', 'Ui'):
            os.symlink(os.path.join(SHELL_DIR, part), os.path.join(self.d, 'qmlroot', 'qs', part))
        self.stage = os.path.join(self.d, 'dev-harness')
        os.makedirs(self.stage)
        for f in os.listdir(HARNESS_DIR):
            if f.endswith('.qml') or f.endswith('.js'):
                shutil.copyfile(os.path.join(HARNESS_DIR, f), os.path.join(self.stage, f))
        os.symlink(os.path.join(ROOT, 'Model.mjs'), os.path.join(self.stage, 'Model.mjs'))
        os.symlink(os.path.join(ROOT, 'model'), os.path.join(self.stage, 'model'))

    def lint_positions(self, path):
        out = os.path.join(self.d, os.path.basename(path) + '.json')
        subprocess.run([QMLLINT, '-I', os.path.join(self.d, 'qmlroot'), '-I', QML_IMPORTS, '--json', out, path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        with open(out, encoding='utf-8') as fh:
            report = json.load(fh)
        found = set()
        for f in report.get('files', []):
            for w in f.get('warnings', []):
                m = self.MEMBER.match(w.get('message', ''))
                if m:
                    found.add((w['line'], w['column'], m.group('name')))
        return found

    def test_every_member_position_qmllint_reports_is_one_the_scanner_found(self):
        files = [p if not p.startswith(HARNESS_DIR + os.sep) else os.path.join(self.stage, os.path.basename(p))
                 for p in linted_files()]
        reached = 0
        for path in files:
            linted = self.lint_positions(path)
            refs, _, _ = cmm.references(read(path))
            missed = sorted(linted - set(refs))
            self.assertEqual([], missed, '%s: qmllint reports Model members where the scanner found none' % path)
            reached += len(linted)
        self.assertGreater(reached, 0, 'qmllint reported no Model-member position in any file: its wording '
                                       'changed or it now resolves ES modules, so this fidelity check compares '
                                       'nothing; re-measure the scanner another way before trusting it')


class GateWiring(unittest.TestCase):
    """STRUCTURAL pin, and labelled as one: it reads check.sh, it does not run
    the qmllint step. The judge above is driven for real; what this pins is the
    lines that make its verdict COUNT. The D-REL-5 round-2 lens dropped them
    one at a time (`(( members_status != 0 && 0 ))`, `members_status=0`) and
    the gate stayed green with a bogus member in Service.qml, because no test
    read them. A refactor that moves the step must move this pin with it.
    """

    def setUp(self):
        with open(os.path.join(ROOT, 'scripts', 'check.sh'), encoding='utf-8') as f:
            self.lines = [l.strip() for l in f.read().splitlines()]

    def judge_line(self):
        return next(n for n, l in enumerate(self.lines)
                    if 'check-model-members.py' in l and l.startswith('members_out='))

    def test_the_judge_status_is_taken_straight_from_the_judge(self):
        i = self.judge_line()
        self.assertEqual('members_status=$?', self.lines[i + 1])
        self.assertEqual(1, sum(1 for l in self.lines if l.startswith('members_status=')))

    def test_the_judge_is_handed_the_file_being_linted(self):
        line = self.lines[self.judge_line()]
        self.assertIn('--file "$file"', line)
        loop = max(n for n, l in enumerate(self.lines[:self.judge_line()]) if l.startswith('for file in '))
        self.assertTrue(self.lines[loop].endswith('; do'), self.lines[loop])
        self.assertFalse(any(l == 'done' for l in self.lines[loop:self.judge_line()]),
                         'the judge runs after the per-file loop has closed')

    def test_a_non_zero_verdict_turns_the_gate_red(self):
        i = self.lines.index('if (( members_status != 0 )); then')
        self.assertTrue(self.lines[i + 1].startswith('bad '), self.lines[i + 1])


if __name__ == '__main__':
    unittest.main()
