"""scripts/check-model-regex.py, the D-PERF-11 guard over model/** and the
shipped QML (round 5 of the bounds sweep, 2026-10-22).

A guard is held to the rule it enforces (CLAUDE.md rule 14: a check that
cannot go red for the failure it guards is not a check): it must refuse the
shape it names -- maskUrl's old `([^\\/?#]*)([^?#]*)` and the D-EPG-12
`\\s*(?:[-/]\\s*)?\\s*` -- in a regex literal and in a `new RegExp` string,
stay green for the linear shapes the model uses, read JavaScript's own
syntax, not read comments or strings as code, and refuse a `new RegExp`
built from an expression nobody listed. F-GATE-9 (round 6, R32a'''): it
must also read `RegExp(` WITHOUT `new` and a string literal handed to
`.match(`, `.search(` or `.matchAll(`, which the language converts to a
RegExp -- two one-token evasions the round-5 guard let through -- while a
string handed to `.replace(` or `.split(` is taken literally and is not a
pattern. MODEL_REGEX_GUARD_ROOT points the whole-tree case at another tree,
which is how it is seen red against the code before the change (dev
9739a3e carries the old maskUrl pattern at model/sources.mjs:630).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "scripts", "check-model-regex.py")
TRIM = os.path.join(ROOT, "scripts", "check-trim-shapes.py")


def run(*args):
    return subprocess.run([sys.executable, "-B", GUARD] + list(args), capture_output=True, text=True, timeout=120)


class ModelRegexGuardTest(unittest.TestCase):

    def file_with(self, text, suffix=".mjs"):
        root = tempfile.mkdtemp(prefix="iptv-model-regex-")
        self.addCleanup(shutil.rmtree, root, True)
        path = os.path.join(root, "part" + suffix)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_the_tree_is_clean(self):
        root = os.environ.get("MODEL_REGEX_GUARD_ROOT") or ROOT
        done = run("--root", root)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertRegex(done.stdout, r"model regex guard: \d+ file\(s\), \d+ regex literal\(s\), \d+ built, 0 problem\(s\)")

    def test_it_reads_every_literal_the_trim_guard_reads_and_the_one_built_pattern(self):
        done = run()
        trim = subprocess.run([sys.executable, "-B", TRIM], capture_output=True, text=True, timeout=120)
        mine = done.stdout.strip().split("\n")[-1]
        theirs = trim.stdout.strip().split("\n")[-1]
        files = int(mine.split("model regex guard: ")[1].split(" ")[0])
        literals = int(mine.split(" file(s), ")[1].split(" ")[0])
        built = int(mine.split(" regex literal(s), ")[1].split(" ")[0])
        self.assertEqual(files, int(theirs.split("trim shape guard: ")[1].split(" ")[0]))
        self.assertEqual(literals, int(theirs.split(" file(s), ")[1].split(" ")[0]))
        self.assertGreaterEqual(built, 1)

    def test_the_known_bad_shape_is_refused_in_a_literal_and_in_a_built_pattern(self):
        for line in ['var m = s.match(/^([A-Za-z][A-Za-z0-9+.-]*):\\/\\/([^\\/?#]*)([^?#]*)(\\?[^#]*)?(#.*)?$/)',
                     'var r = /\\[\\s*not\\s*24\\s*[-/]?\\s*7\\s*\\]/',
                     'var r = /^\\[[0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*\\]$/',
                     'var r = /a+a+b/',
                     'var r = /[a-z]*\\w+x/i',
                     'var r = new RegExp("([^\\\\/?#]*)([^?#]*)$")',
                     'var r = new RegExp("[ab]*[BC]*d", "i")']:
            with self.subTest(line):
                done = run(self.file_with(line + "\n"))
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn("super-linear shape", done.stdout)
                self.assertIn("D-PERF-11", done.stdout)

    def test_linear_shapes_javascript_syntax_comments_and_strings_pass(self):
        text = "\n".join([
            'var a = /^([A-Za-z][A-Za-z0-9+.-]*):([\\s\\S]*)$/.exec(s)',
            'var b = s.search(/[\\/?#]/)',
            'var c = /^--[a-z0-9][a-z0-9-]*(=.*)?$/.test(t)',
            'var d = /^\\[(?=[0-9A-Fa-f.]*:)[0-9A-Fa-f:.]*(?:%25[A-Za-z0-9._~-]+)?\\]$/.test(h)',
            'var e = /\\[\\s*not\\s*24\\s*(?:[-/]\\s*)?7\\s*\\]/.test(n)',
            'var f = /(?<name>[a-z]+)-(?<tail>[0-9]+)/.exec(s)',
            'var g = /[^]/.test(s)',
            'var h = /a\\/b\\/c/.test(s)',
            'var i = /\\u{1f600}/u.test(s)',
            'var j = s.replace(/\\s+/g, " ")',
            'var k = x / 2 / y',
            '// var bad = /a*a*b/ in a comment',
            ' * var bad = /a*a*b/ in a block comment',
            'var l = "/a*a*b/ in a string" // /a*a*b/',
            'var m = new RegExp("^" + GENERATED_NAME_WORD.toLowerCase() + " [0-9]+$")',
            'var n = new RegExp("^[a-z]+$")',
        ]) + "\n"
        done = run(self.file_with(text))
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("0 problem(s)", done.stdout)
        self.assertIn("2 built", done.stdout)

    def test_f_gate_9_regexp_without_new_and_a_string_handed_to_match_search_matchall_are_read(self):
        # Each of these built the maskUrl shape past the round-5 guard; the
        # last two vary the quote and the spacing so a guard that matched
        # one spelling could not pass by accident.
        for line in ['var F = RegExp("([^\\\\/?#]*)([^?#]*)(\\\\?[^#]*)?(#.*)?$")',
                     'var G = RegExp("[ab]*[BC]*d", "i")',
                     'var S = s.match("([^/?#]*)([^?#]*)$")',
                     'var T = s.search("([^/?#]*)([^?#]*)$")',
                     'var U = s.matchAll("([^/?#]*)([^?#]*)$")',
                     "var V = s.match('([^/?#]*)([^?#]*)$')",
                     'var W = s.match( "([^/?#]*)([^?#]*)$" )']:
            with self.subTest(line):
                done = run(self.file_with(line + "\n"))
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn("super-linear shape", done.stdout)
                self.assertIn("1 built", done.stdout)

    def test_f_gate_9_a_literal_string_to_replace_or_split_and_a_variable_to_match_are_not_patterns(self):
        text = "\n".join([
            'var a = s.replace("([^/?#]*)([^?#]*)$", "")',
            'var b = s.split("([^/?#]*)([^?#]*)$")',
            'var c = s.match(pattern)',
            'var d = s.search(someRe)',
            'var e = myRegExp("([^/?#]*)([^?#]*)$")',
            'var f = obj.RegExp("([^/?#]*)([^?#]*)$")',
            'var g = s.match(/[\\/?#]/)',
            'var h = RegExp("^[a-z]+$")',
            'var i = s.match("^[a-z]+$")',
        ]) + "\n"
        done = run(self.file_with(text))
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("0 problem(s)", done.stdout)
        self.assertIn("1 regex literal(s), 2 built", done.stdout)

    def test_f_gate_9_a_template_literal_handed_to_match_or_regexp_is_a_problem(self):
        for line in ['var r = RegExp(`[a-z]+`)', 'var r = s.match(`[a-z]+`)', 'var r = new RegExp(`[a-z]+`)']:
            with self.subTest(line):
                done = run(self.file_with(line + "\n"))
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn("cannot read", done.stdout)

    def test_a_built_pattern_nobody_listed_is_a_problem(self):
        done = run(self.file_with('var r = new RegExp(prefix + "[0-9]+")\n'))
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("builds a pattern this guard cannot read", done.stdout)
        self.assertIn('prefix + "[0-9]+"', done.stdout)

    def test_a_pattern_the_parser_cannot_read_is_a_problem_not_a_pass(self):
        done = run(self.file_with('var r = /(?z)/\n'))
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("could not walk", done.stdout)

    def test_qml_is_read_too(self):
        done = run(self.file_with('    var m = text.match(/([^\\/?#]*)([^?#]*)$/)\n', ".qml"))
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("super-linear shape", done.stdout)


if __name__ == "__main__":
    unittest.main()
