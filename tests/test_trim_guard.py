"""scripts/check-trim-shapes.py, the D-PERF-3 guard (ruling R30g).

A guard is held to the rule it enforces: it must go red for the shapes it
names (CLAUDE.md rule 14: a check that cannot go red for the failure it
guards is not a check), stay green for the shapes that are linear, and not
read comments or strings as code. TRIM_GUARD_ROOT points the whole-tree case
at another tree, which is how it is seen red against the code before the
change (26 sites on lane-bounds-int).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "scripts", "check-trim-shapes.py")


def run(*args):
    return subprocess.run([sys.executable, "-B", GUARD] + list(args), capture_output=True, text=True, timeout=60)


class TrimGuardTest(unittest.TestCase):

    def file_with(self, text, suffix=".mjs"):
        root = tempfile.mkdtemp(prefix="iptv-trim-")
        self.addCleanup(shutil.rmtree, root, True)
        path = os.path.join(root, "part" + suffix)
        with open(path, "w", encoding="ascii") as handle:
            handle.write(text)
        return path

    def test_the_tree_is_clean(self):
        root = os.environ.get("TRIM_GUARD_ROOT") or ROOT
        done = run("--root", root)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertRegex(done.stdout, r"trim shape guard: \d+ file\(s\), \d+ regex literal\(s\), 0 problem\(s\)")

    def test_it_reads_the_model_and_every_shipped_qml(self):
        done = run()
        files = int(done.stdout.split("trim shape guard: ")[1].split(" ")[0])
        model_parts = len([n for n in os.listdir(os.path.join(ROOT, "model")) if n.endswith(".mjs")])
        self.assertGreaterEqual(files, 1 + model_parts + 3)

    def test_each_quadratic_trim_shape_is_refused(self):
        for line in ['var a = s.replace(/\\s+$/, "")',
                     'var a = s.replace(/^\\s+|\\s+$/g, "")',
                     'var a = s.replace(/\\s*$/, "")',
                     'var a = s.replace(/^[ \\u00a0]+|[ \\u00a0]+$/g, "")',
                     'var a = s.replace(/[\\s-]+$/, "")',
                     'return t.replace(/x|[ \\t]*$/, "")']:
            with self.subTest(line):
                done = run(self.file_with(line + "\n"))
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn("quadratic", done.stdout)

    def test_the_one_sided_natives_V4_lacks_are_refused(self):
        for call in ["s.trimEnd()", "s.trimStart()", "s.trimLeft()", "s.trimRight ()"]:
            with self.subTest(call):
                done = run(self.file_with("var a = " + call + "\n", ".qml"))
                self.assertEqual(done.returncode, 1, done.stdout)
                self.assertIn("does not exist in Qt 6.11.2's V4", done.stdout)

    def test_linear_shapes_comments_and_strings_pass(self):
        text = "\n".join([
            'var a = s.trim()',
            'var b = /^\\s+$/.test(s)',
            'var c = /^[0-9]+$/.test(s)',
            'var d = s.replace(/^[\\s-]+/, "")',
            'var e = s.replace(/\\s+/g, " ")',
            '// s.replace(/\\s+$/, "") was quadratic',
            '  * and so was s.trimEnd() in V4',
            'var f = "/\\s+$/ in a string" // s.replace(/\\s+$/, "")',
            'var g = Model.trimEndSpace(s)',
        ]) + "\n"
        done = run(self.file_with(text))
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("0 problem(s)", done.stdout)


if __name__ == "__main__":
    unittest.main()
