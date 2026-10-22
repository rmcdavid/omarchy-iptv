"""scripts/split-model.mjs cuts the model into parts and judges its own cut (D-REL-5).

Every case drives the SHIPPING script as a subprocess over a small monolith
written here, the way it is run at integration over the D-SINK-19 chain's
Model.js, so nothing below reimplements what it checks (CLAUDE.md rule 12).
Each refusal is asserted by its exit status AND by the sentence that names
the declaration, because a refusal for the wrong reason is a pass for the
wrong reason.

Rule 11, recorded: each case was run against a copy of the script with the
one decision it guards broken, and went red there; the mutations and their
counts are in the lane's report for D-REL-5.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, 'scripts', 'split-model.mjs')

MONOLITH = '''// Model.js -- a fixture monolith.
//
// The header goes to the aggregator.

var A = 1
// leads B, and travels with it
var B = A + 1

function f(x) {
  return x + B + g()
}

// ---- section two
function g() {
  return 2
}
var C = g()

if (typeof module !== "undefined") {
  module.exports = {
    // a guard comment
    A: A,
    f: f,
    C: C
  }
}
'''

# Section 9 of a fixture ARCHITECTURE.md: every line the cut of MONOLITH
# drops (its header's two text lines and its one guard comment), recorded.
RECORD = '''# Architecture

## 9. Coding standards

```
// Model.js -- a fixture monolith.
// The header goes to the aggregator.
// a guard comment
```

## 10. Next
'''

PARTS = [
    {'name': 'one', 'about': 'the first part', 'names': ['A', 'B', 'f']},
    {'name': 'two', 'about': 'the second part', 'names': ['g', 'C']},
]


def node_available():
    return shutil.which('node') is not None


@unittest.skipUnless(node_available(), 'node is required (see scripts/check.sh)')
class SplitModel(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.mkdtemp(prefix='split-model-')
        self.addCleanup(shutil.rmtree, self.work, ignore_errors=True)

    def write(self, rel, text):
        path = os.path.join(self.work, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as fh:
            fh.write(text)
        return path

    def read(self, rel):
        with open(os.path.join(self.work, rel)) as fh:
            return fh.read()

    def run_script(self, mode, monolith=MONOLITH, parts=None, record=RECORD):
        self.write('Model.js', monolith)
        self.write('parts.json', json.dumps({'parts': parts if parts is not None else PARTS}))
        if record is not None:
            self.write('docs/ARCHITECTURE.md', record)
        elif os.path.exists(os.path.join(self.work, 'docs', 'ARCHITECTURE.md')):
            os.remove(os.path.join(self.work, 'docs', 'ARCHITECTURE.md'))
        argv = ['node', SCRIPT, '--' + mode, '--root', self.work,
                '--manifest', os.path.join(self.work, 'parts.json')]
        if mode in ('write', 'verify'):
            argv += ['--input', os.path.join(self.work, 'Model.js')]
        proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        return proc.returncode, proc.stdout.decode('utf-8', 'replace')

    def node_eval(self, expr):
        src = ('import(%s).then(function (M) { process.stdout.write(JSON.stringify(%s)) })'
               % (json.dumps('file://' + os.path.join(self.work, 'Model.mjs')), expr))
        return json.loads(subprocess.check_output(['node', '-e', src], timeout=60).decode())

    # ------------------------------------------------------------ the cut

    def test_a_clean_cut_writes_verifies_and_checks(self):
        code, out = self.run_script('write')
        self.assertEqual(code, 0, out)
        self.assertIn('runtime: Model.mjs exports 3 names', out)
        self.assertEqual(self.node_eval('Object.keys(M).sort()'), ['A', 'C', 'f'])
        self.assertEqual(self.node_eval('M.f(1)'), 1 + 2 + 2, 'the call across parts must work')
        for mode in ('verify', 'check'):
            code, out = self.run_script(mode)
            self.assertEqual(code, 0, '%s: %s' % (mode, out))

    def test_the_aggregator_header_is_generated_and_comments_travel_with_code(self):
        # R4: the monolith's header said "No ES module syntax" and
        # `import "Model.js"`, false of a module, so it is not carried over.
        self.assertEqual(self.run_script('write')[0], 0)
        agg = self.read('Model.mjs')
        self.assertTrue(agg.startswith('// Model.mjs -- the model of io.github.rmcdavid.iptv'), agg)
        self.assertNotIn('a fixture monolith', agg)
        one = self.read('model/one.mjs')
        self.assertIn('// leads B, and travels with it\nvar B = A + 1\n', one)
        two = self.read('model/two.mjs')
        self.assertIn('\n// ---- section two\nfunction g() {', two)
        self.assertNotIn('function g', one)

    def test_the_generated_lines_name_no_path_an_install_lacks(self):
        # They ship. A comment naming scripts/... in a shipped file cites a
        # file that does not exist in an install (D-REL-2), and release.py
        # check refused the first cut for exactly that.
        self.assertEqual(self.run_script('write')[0], 0)
        for rel in ('Model.mjs', 'model/one.mjs', 'model/two.mjs'):
            generated = [l for l in self.read(rel).splitlines()
                         if 'split-model' in l]
            self.assertTrue(generated, rel)
            for line in generated:
                self.assertNotIn('scripts/', line, rel)
                self.assertIn('on the dev branch', line, rel)

    def test_the_generated_header_says_what_the_file_is_and_how_it_is_made(self):
        self.assertEqual(self.run_script('write')[0], 0)
        agg = self.read('Model.mjs')
        header = agg[:agg.index('// Generated by split-model.mjs')]
        for needle in ('GENERATED by split-model.mjs on the dev branch',
                       'import "Model.mjs" as Model',
                       'AS A MODULE', '--write --from-git REF', '--verify --from-git REF',
                       '--relink', '--check', 'section 9'):
            self.assertIn(needle, header)
        # It ships: no path an install lacks (D-REL-2), and no Model.js (R5).
        self.assertNotIn('scripts/', header)
        self.assertNotIn('docs/', header)
        self.assertNotIn('Model.js', header)

    def test_check_refuses_a_hand_edited_aggregator_header_and_relink_restores_it(self):
        self.assertEqual(self.run_script('write')[0], 0)
        agg = self.read('Model.mjs')
        self.write('Model.mjs', agg.replace('// GENERATED by', '// Written by'))
        code, out = self.run_script('check')
        self.assertEqual(code, 1, out)
        self.assertIn('Model.mjs: its generated lines are not what --relink writes', out)
        self.assertEqual(self.run_script('relink')[0], 0)
        self.assertEqual(self.read('Model.mjs'), agg)

    def test_every_dropped_line_is_accounted_for_by_name(self):
        code, out = self.run_script('write')
        self.assertEqual(code, 0, out)
        self.assertIn('dropped by the cut and recorded in docs/ARCHITECTURE.md section 9: 3 of 3 line(s) '
                      '(2 header, 1 export-guard)', out)
        code, out = self.run_script('verify')
        self.assertEqual(code, 0, out)
        self.assertIn('3 of 3 line(s)', out)

    def test_an_unrecorded_header_line_is_red_by_name(self):
        record = RECORD.replace('// The header goes to the aggregator.\n', '')
        for mode in ('write', 'verify'):
            code, out = self.run_script(mode, record=record)
            self.assertEqual(code, 1, '%s: %s' % (mode, out))
            self.assertIn("`// The header goes to the aggregator.` (the one-file model's header) is dropped "
                          'by the cut and not recorded in docs/ARCHITECTURE.md section 9', out)

    def test_an_unrecorded_guard_comment_is_red_by_name(self):
        mono = MONOLITH.replace('    // a guard comment\n', '    // a guard comment\n    // a new one\n')
        code, out = self.run_script('write', monolith=mono)
        self.assertEqual(code, 1, out)
        self.assertIn('`// a new one` (a comment inside its export guard) is dropped by the cut', out)

    def test_a_line_recorded_outside_section_9_does_not_count(self):
        record = RECORD.replace('// a guard comment\n', '').replace('## 10. Next\n', '## 10. Next\n\n// a guard comment\n')
        code, out = self.run_script('verify', record=record)
        self.assertEqual(code, 1, out)
        self.assertIn('`// a guard comment` (a comment inside its export guard) is dropped', out)

    def test_no_record_at_all_is_red(self):
        code, out = self.run_script('write', record=None)
        self.assertEqual(code, 1, out)
        self.assertIn('docs/ARCHITECTURE.md: missing, so the 3 line(s) the cut drops are recorded nowhere', out)

    def test_the_guard_comments_are_reported_not_silently_dropped(self):
        code, out = self.run_script('write')
        self.assertEqual(code, 0, out)
        self.assertIn('comment lines inside the export guard, which the generated export lines replace: 1', out)
        self.assertIn('// a guard comment', out)

    # ------------------------------------------------------------ init locality

    def test_an_initializer_reading_another_part_is_refused(self):
        parts = [dict(PARTS[0], names=['A', 'B', 'f', 'g']), dict(PARTS[1], names=['C'])]
        code, out = self.run_script('write', parts=parts)
        self.assertEqual(code, 2, out)
        self.assertIn('init locality: the initializer of `C` (two) reads `g` of part one', out)
        self.assertFalse(os.path.exists(os.path.join(self.work, 'Model.mjs')), 'a refused cut must write nothing')

    def test_init_locality_follows_a_same_part_function_to_another_part(self):
        mono = MONOLITH.replace('function g() {\n  return 2\n}', 'function g() {\n  return A + 1\n}')
        code, out = self.run_script('write', monolith=mono)
        self.assertEqual(code, 2, out)
        self.assertIn('the initializer of `C` (two) reads `A` of part one (C -> g -> A)', out)

    def test_a_function_body_may_call_across_parts(self):
        # f (one) calls g (two) and reads B (one): bodies run after every part has evaluated
        code, out = self.run_script('write')
        self.assertEqual(code, 0, out)
        self.assertNotIn('init locality', out)

    # ------------------------------------------------------------ declaration order

    def test_a_var_named_above_its_declaration_in_its_part_is_refused(self):
        # Quickshell logged qt.qml.usedbeforedeclared, with the module's
        # file:// URL, for exactly this shape in a module (and never for the
        # classic script it came from). Measured on the real cut: two of them.
        mono = MONOLITH.replace('  return x + B + g()\n}\n', '  return x + B + g() + LATER\n}\nvar LATER = 3\n')
        parts = [dict(PARTS[0], names=['A', 'B', 'f', 'LATER']), PARTS[1]]
        code, out = self.run_script('write', monolith=mono, parts=parts)
        self.assertEqual(code, 2, out)
        self.assertIn('`f` names `LATER`, which is declared below it in part one', out)

    def test_the_same_var_in_another_part_is_an_import_and_is_fine(self):
        mono = MONOLITH.replace('  return x + B + g()\n}\n', '  return x + B + g() + LATER\n}\nvar LATER = 3\n')
        parts = [PARTS[0], dict(PARTS[1], names=['LATER', 'g', 'C'])]
        code, out = self.run_script('write', monolith=mono, parts=parts)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.node_eval('M.f(1)'), 1 + 2 + 2 + 3)

    # ------------------------------------------------------------ writes

    def test_an_assignment_to_a_top_level_binding_is_refused(self):
        mono = MONOLITH.replace('  return 2\n', '  A = 5\n  return 2\n')
        code, out = self.run_script('write', monolith=mono)
        self.assertEqual(code, 2, out)
        self.assertIn('`g` assigns to the top-level binding `A`', out)

    def test_an_in_place_mutation_of_a_top_level_binding_is_refused(self):
        mono = MONOLITH.replace('var A = 1\n', 'var A = [1]\n').replace('  return 2\n', '  A.push(3)\n  return 2\n')
        code, out = self.run_script('write', monolith=mono)
        self.assertEqual(code, 2, out)
        self.assertIn('`g` mutates the top-level binding `A` in place', out)

    def test_a_local_that_shadows_a_top_level_name_is_not_a_write(self):
        # (in f, which no initializer reaches: init locality reads a body's
        # names without scoping them, which errs toward refusing)
        mono = MONOLITH.replace('  return x + B + g()\n', '  var C = 3\n  C = 4\n  return x + B + g() + C\n')
        code, out = self.run_script('write', monolith=mono)
        self.assertEqual(code, 0, out)

    # ------------------------------------------------------------ the manifest

    def test_an_unnamed_declaration_follows_the_nearest_named_one_and_is_reported(self):
        # after g, so the nearest named declaration is in the SECOND part
        mono = MONOLITH.replace('var C = g()\n', 'function added() {\n  return f(0)\n}\nvar C = g()\n')
        code, out = self.run_script('write', monolith=mono)
        self.assertEqual(code, 0, out)
        self.assertIn('placed after the nearest preceding named declaration): added -> two', out)
        self.assertIn('function added()', self.read('model/two.mjs'))

    def test_a_name_the_input_does_not_declare_is_reported(self):
        parts = [dict(PARTS[0], names=['A', 'B', 'f', 'gone']), PARTS[1]]
        code, out = self.run_script('write', parts=parts)
        self.assertEqual(code, 0, out)
        self.assertIn('named by the manifest but not declared in the input: gone', out)

    # ------------------------------------------------------------ the input

    def test_top_level_code_that_is_not_a_declaration_is_refused(self):
        mono = MONOLITH.replace('var C = g()\n', 'var C = g()\nB.x = 1\n')
        code, out = self.run_script('write', monolith=mono)
        self.assertEqual(code, 2, out)
        self.assertIn('a column-0 line inside a declaration', out)

    def test_an_export_bound_to_another_name_is_refused(self):
        mono = MONOLITH.replace('    f: f,\n', '    f: g,\n')
        code, out = self.run_script('write', monolith=mono)
        self.assertEqual(code, 2, out)
        self.assertIn('export `f` is bound to `g`, not to its own name', out)

    # ------------------------------------------------------------ verify

    def test_verify_sees_a_byte_changed_in_a_part(self):
        self.assertEqual(self.run_script('write')[0], 0)
        path = os.path.join(self.work, 'model', 'one.mjs')
        self.write('model/one.mjs', self.read('model/one.mjs').replace('return x + B + g()', 'return x + B + g() '))
        code, out = self.run_script('verify')
        self.assertEqual(code, 1, out)
        self.assertIn('model/one.mjs: differs from what the cut of', out)
        self.assertIn('`f` (input line 9) is found at the cursor of 0 parts, not exactly one', out)
        self.assertTrue(os.path.exists(path))

    def test_verify_sees_a_declaration_moved_by_hand(self):
        self.assertEqual(self.run_script('write')[0], 0)
        one, two = self.read('model/one.mjs'), self.read('model/two.mjs')
        chunk = '\n// ---- section two\nfunction g() {\n  return 2\n}\n'
        self.assertIn(chunk, two)
        self.write('model/two.mjs', two.replace(chunk, '\n'))
        self.write('model/one.mjs', one.replace('\nexport {', chunk + 'export {'))
        code, out = self.run_script('verify')
        self.assertEqual(code, 1, out)
        self.assertIn('`g` (input line 14) is found at the cursor of 0 parts', out)

    def test_the_runtime_comparison_catches_what_bytes_cannot(self):
        # Byte-identical code, different value: `this` in a plain call is the
        # global object in the CommonJS monolith and undefined in a module.
        mono = MONOLITH.replace('var C = g()\n', 'var C = g()\nvar D = (function () { return this === undefined })()\n')
        mono = mono.replace('    C: C\n', '    C: C,\n    D: D\n')
        parts = [PARTS[0], dict(PARTS[1], names=['g', 'C', 'D'])]
        code, out = self.run_script('write', monolith=mono, parts=parts)
        self.assertEqual(code, 1, out)
        self.assertIn('D: false vs true', out)

    # ------------------------------------------------------------ check / relink

    def test_check_sees_a_missing_import_and_relink_restores_it(self):
        self.assertEqual(self.run_script('write')[0], 0)
        one = self.read('model/one.mjs')
        imp = 'import {\n  g\n} from "./two.mjs"\n'
        self.assertIn(imp, one)
        self.write('model/one.mjs', one.replace(imp, ''))
        code, out = self.run_script('check')
        self.assertEqual(code, 1, out)
        self.assertIn('model/one.mjs: its generated lines are not what --relink writes', out)
        code, out = self.run_script('relink')
        self.assertEqual(code, 0, out)
        self.assertEqual(self.read('model/one.mjs'), one)

    def test_a_name_mentioned_only_in_a_comment_or_a_literal_is_not_an_import(self):
        # F-GATE-8 (2026-10-22): the relinker read identifiers out of the
        # part's RAW text, so a comment that named another part's export
        # created a cross-part import of it (three were found in
        # model/settings.mjs by the D-EPG-11 round's correctness lens; the
        # fix found dozens across 16 parts). Here `f` no longer calls g and
        # names it only in a line comment, a block comment, a string and a
        # regex; part one must import nothing from part two, and the
        # genuine reference the other way (C's initializer calls g, in the
        # same part) is untouched. On the relinker before the fix, one.mjs
        # carried `import { g } from "./two.mjs"`.
        mono = MONOLITH.replace(
            'function f(x) {\n  return x + B + g()\n}\n',
            'function f(x) {\n'
            '  // g() is not called here; see g in part two\n'
            '  /* nor here: g, C */\n'
            '  var s = "g()" + \'C\'\n'
            '  var r = /g|C/.test(s)\n'
            '  return x + B + (r ? 1 : 0)\n'
            '}\n')
        code, out = self.run_script('write', monolith=mono)
        self.assertEqual(code, 0, out)
        one = self.read('model/one.mjs')
        self.assertNotIn('from "./two.mjs"', one, one)
        self.assertNotIn('import {', one, one)
        self.assertIn('model/one.mjs', out)
        self.assertRegex(out, r'model/one\.mjs .* imports -\n', 'the report must show part one importing nothing')
        self.assertEqual(self.node_eval('M.f(1)'), 1 + 2 + 1)
        # and a real call across parts still imports (the control)
        mono2 = mono.replace('  return x + B + (r ? 1 : 0)\n', '  return x + B + (r ? 1 : 0) + g()\n')
        code, out = self.run_script('write', monolith=mono2)
        self.assertEqual(code, 0, out)
        self.assertIn('import {\n  g\n} from "./two.mjs"\n', self.read('model/one.mjs'))
        self.assertEqual(self.node_eval('M.f(1)'), 1 + 2 + 1 + 2)

    def test_check_applies_init_locality_to_an_edited_part(self):
        self.assertEqual(self.run_script('write')[0], 0)
        two = self.read('model/two.mjs')
        self.write('model/two.mjs', two.replace('var C = g()\n', 'var C = g() + A\n'))
        code, out = self.run_script('relink')
        self.assertEqual(code, 1, out)
        self.assertIn('the initializer of `C` (two) reads `A` of part one', out)

    def test_check_sees_a_part_the_aggregator_does_not_load(self):
        self.assertEqual(self.run_script('write')[0], 0)
        self.write('model/stray.mjs', '// model/stray.mjs -- stray. x\nexport {\n  nothing\n}\n')
        code, out = self.run_script('check')
        self.assertEqual(code, 1, out)
        self.assertIn('model/stray.mjs: a part the manifest does not list', out)


if __name__ == '__main__':
    unittest.main()
