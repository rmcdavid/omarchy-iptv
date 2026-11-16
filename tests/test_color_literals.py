"""scripts/check-color-literals.py, held to the failures it guards (F-GATE-17).

The guard says no shipped QML file writes a colour as a literal without a
CONVENTION-EXCEPTION comment. These tests run it on the tree (green, and it
must have READ the literals that are there) and on mutants of the tree: each
kind of literal put into each shipped file is red, the same literal under an
exception comment is green, and the words and calls that are not literals
stay green. Rule 11: the guard is new, so each decision in it is shown by a
case that goes red or green on that decision alone, and the mutants at the
foot break the guard itself.
"""
import importlib.util
import io
import os
import re
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIPPED = ("Guide.qml", "BarWidget.qml", "Service.qml")

_spec = importlib.util.spec_from_file_location(
    "check_color_literals", os.path.join(ROOT, "scripts", "check-color-literals.py"))
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def inside_root(text, lines):
    """`lines` inserted as the first members of the file's root object."""
    m = re.search(r"^[A-Z][\w.]*\s*\{\s*$", text, re.M)
    if m is None:
        raise AssertionError("no root object found")
    return text[:m.end()] + "\n" + "\n".join("  " + line for line in lines) + text[m.end():]


def problems(text):
    found, counts = guard.judge("x.qml", text)
    return found, counts


def doc(*lines):
    return "import QtQuick\nItem {\n" + "\n".join("  " + line for line in lines) + "\n}\n"


class TheTree(unittest.TestCase):
    def test_the_shipped_files_are_green_and_their_literals_were_read(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = guard.main(["--root", ROOT])
        self.assertEqual(code, 0, out.getvalue())
        m = re.search(r"colour literal guard: (\d+) colour literal\(s\) read in 3 file\(s\) \((\d+) no-paint, (\d+) excused\), 0 problem",
                      out.getvalue())
        self.assertIsNotNone(m, out.getvalue())
        # The seven "transparent" fills F-GATE-17 counted: a scanner that
        # stopped seeing literals would be green on anything.
        self.assertGreaterEqual(int(m.group(1)), 7)
        self.assertEqual(m.group(1), m.group(2))

    def test_the_allowlist_names_the_three_files_these_tests_mutate(self):
        names = sorted(os.path.basename(p) for p in guard.theme.allowlisted_qml(ROOT))
        self.assertEqual(names, sorted(SHIPPED))

    def test_each_kind_of_literal_in_each_shipped_file_is_red(self):
        cases = (
            ('color: "#ff0000"', '"#ff0000"'),
            ('property string tintHex: "#80ff0000"', '"#80ff0000"'),
            ('property color flag: "white"', '"white"'),
            ('property var ink: "black"', '"black"'),
            ('property color warm: "tomato"', '"tomato"'),
            ("property color mixed: Qt.rgba(1, 0.5, 0, 1)", "Qt.rgba(...) of numbers"),
            ("property color dim: Qt.darker('red', 1.2)", '"red"'),
        )
        for name in SHIPPED:
            base = read(name)
            for line, shown in cases:
                with self.subTest(file=name, line=line):
                    found, _ = problems(inside_root(base, [line]))
                    self.assertEqual(len(found), 1, found)
                    self.assertIn(shown, found[0])
                    self.assertIn("CONVENTION-EXCEPTION", found[0])

    def test_the_same_literals_under_an_exception_comment_are_green(self):
        for name in SHIPPED:
            base = read(name)
            with self.subTest(file=name, where="line above"):
                found, counts = problems(inside_root(base, [
                    "// CONVENTION-EXCEPTION: a probe's fixed colour, outside the theme",
                    'property color flag: "#ff0000"']))
                self.assertEqual(found, [])
                self.assertEqual(counts["excused"], 1)
            with self.subTest(file=name, where="top of a comment run"):
                found, counts = problems(inside_root(base, [
                    "// CONVENTION-EXCEPTION: the reason starts here",
                    "// and runs on for a second line.",
                    'property color flag: "white"']))
                self.assertEqual(found, [])
            with self.subTest(file=name, where="own line"):
                found, _ = problems(inside_root(base, [
                    'property color flag: "black"  // CONVENTION-EXCEPTION: ink for a test card']))
                self.assertEqual(found, [])


class WhatAnExceptionCovers(unittest.TestCase):
    def test_a_comment_separated_by_code_or_a_blank_line_excuses_nothing(self):
        found, _ = problems(doc("// CONVENTION-EXCEPTION: for the first only",
                                'property color a: "#111111"',
                                'property color b: "#222222"'))
        self.assertEqual(len(found), 1)
        self.assertIn('"#222222"', found[0])
        found, _ = problems(doc("// CONVENTION-EXCEPTION: too far away", "", 'property color a: "#111111"'))
        self.assertEqual(len(found), 1)

    def test_the_word_inside_a_string_is_not_a_comment(self):
        found, _ = problems(doc('property string note: "CONVENTION-EXCEPTION"; property color a: "#111111"'))
        self.assertEqual(len(found), 1)

    def test_an_ordinary_comment_above_excuses_nothing(self):
        found, _ = problems(doc("// the accent, for now", 'color: "#111111"'))
        self.assertEqual(len(found), 1)


class WhatIsALiteral(unittest.TestCase):
    def test_hex_lengths_qt_reads_are_literals_and_others_are_not(self):
        for digits, want in ((3, 1), (4, 1), (6, 1), (8, 1), (9, 1), (12, 1), (1, 0), (2, 0), (5, 0), (7, 0), (10, 0)):
            with self.subTest(digits=digits):
                found, _ = problems(doc('property string s: "#%s"' % ("a" * digits)))
                self.assertEqual(len(found), want, found)
        found, _ = problems(doc('property string s: "#EXTM3U"', 'property string t: "#ggg"'))
        self.assertEqual(found, [])

    def test_a_colour_in_a_comment_or_a_longer_string_is_not_one(self):
        found, counts = problems(doc("// color: \"#ff0000\" was here once",
                                     "/* \"white\" */",
                                     'property string s: "white space"',
                                     'property string t: "see #ff0000"'))
        self.assertEqual(found, [])
        self.assertEqual(counts["read"], 0)

    def test_a_colour_name_that_is_only_a_word_stays_green(self):
        found, counts = problems(doc('property string group: "Gold"',
                                     'property var tags: ["red", "tan", "snow"]',
                                     'function f(x) { return x === "navy" }',
                                     'state: "orange"'))
        self.assertEqual(found, [])
        self.assertEqual(counts["read"], 0)

    def test_a_colour_name_where_the_code_says_colour_is_red(self):
        for line in ('color: "red"', 'border.color: "Tan"', 'property color c: "gold"',
                     'Component.onCompleted: { x.color = "navy" }',
                     'property var c: Qt.lighter("orange")',
                     'color: ok ? "green" : Commons.Color.urgent',
                     'color: ok ? Commons.Color.accent : "crimson"',
                     'selectedColor: pick("teal")'):
            with self.subTest(line=line):
                found, _ = problems(doc(line))
                self.assertEqual(len(found), 1, found)

    def test_a_binding_does_not_lend_its_name_to_the_next_one(self):
        found, _ = problems(doc("color: Commons.Color.accent", 'text: "red"',
                                "border.color: root.edge", 'objectName: "gold"'))
        self.assertEqual(found, [])

    def test_a_statement_ends_what_a_colour_binding_covers(self):
        found, _ = problems(doc("color: Commons.Color.accent",
                                'function word() { return "red" }',
                                'color: a; objectName: "gold"',
                                'Text { color: root.ink; text: "tan" }'))
        self.assertEqual(found, [])

    def test_a_colour_key_in_an_object_literal_is_read_wherever_it_stands(self):
        for line in ('property var o: ({ color: "red", width: 2 })',
                     'property var o: ({ width: 2, color: "red" })',
                     'property var o: ({ width: 2, edgeColor: "red", z: 1 })'):
            with self.subTest(line=line):
                found, _ = problems(doc(line))
                self.assertEqual(len(found), 1, found)
        found, _ = problems(doc('property var o: ({ color: root.ink, name: "red" })'))
        self.assertEqual(found, [])

    def test_white_and_black_are_literals_wherever_they_stand(self):
        found, _ = problems(doc('function ink(dark) { return dark ? "white" : "Black" }'))
        self.assertEqual(len(found), 2, found)

    def test_transparent_is_counted_and_never_refused(self):
        found, counts = problems(doc('color: "transparent"', 'border.color: on ? root.edge : "transparent"',
                                     'property string word: "transparent"'))
        self.assertEqual(found, [])
        self.assertEqual((counts["read"], counts["none"]), (2, 2))

    def test_a_numeric_qt_call_is_a_literal_and_a_theme_one_is_not(self):
        for line, want in (("color: Qt.rgba(0, 0, 0, 0.4)", 1),
                           ("color: Qt.hsla(0.5, 1, 0.5, 1)", 1),
                           ("color: Qt.hsva(0.1, 0.2, 0.3)", 1),
                           ("color: Qt.rgba(1 / 2, -0.5 + 1, (0.25), 1)", 1),
                           ("color: Qt.rgba(c.r, c.g, c.b, 0.4)", 0),
                           ("color: Qt.rgba(root.red, 0, 0, 1)", 0),
                           ("color: Qt.darker(Commons.Color.accent, 1.3)", 0),
                           ("color: mine.Qt.rgba(0, 0, 0, 1)", 0),
                           ("color: Qt.rgba()", 0)):
            with self.subTest(line=line):
                found, _ = problems(doc(line))
                self.assertEqual(len(found), want, found)

    def test_a_literal_inside_a_template_expression_is_read(self):
        found, _ = problems(doc('property string s: `x ${ok ? "#ff0000" : ""} y`'))
        self.assertEqual(len(found), 1, found)


class TheCommand(unittest.TestCase):
    def run_on(self, text):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "Probe.qml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            out = io.StringIO()
            with redirect_stdout(out):
                code = guard.main(["--root", tmp, path])
            return code, out.getvalue()

    def test_exit_codes_and_the_count_line(self):
        code, out = self.run_on(doc('color: "transparent"'))
        self.assertEqual(code, 0, out)
        self.assertIn("1 colour literal(s) read in 1 file(s) (1 no-paint, 0 excused), 0 problem(s)", out)
        code, out = self.run_on(doc('color: "#abcdef"'))
        self.assertEqual(code, 1, out)
        self.assertIn("Probe.qml:3:10:", out)
        self.assertIn("1 problem(s)", out)

    def test_a_file_the_scanner_cannot_read_is_an_error_not_a_pass(self):
        code, out = self.run_on('Item { property string s: "never closed\n}\n')
        self.assertEqual(code, 2, out)
        out = io.StringIO()
        with redirect_stdout(out):
            code = guard.main(["--root", ROOT, os.path.join(ROOT, "no-such-file.qml")])
        self.assertEqual(code, 2, out.getvalue())


if __name__ == "__main__":
    unittest.main()
