"""scripts/check-metric-literals.py, held to the failures it guards (F-GATE-24).

The guard says no shipped QML file binds a metric -- a pixel size, a corner
radius, a gap, a margin, a border width -- to a number without a
CONVENTION-EXCEPTION comment. These tests run it on the tree (green, and it
must have READ the metric bindings that are there) and on mutants of the
tree: a hardcoded number put into each shipped file is red, the same number
under an exception comment is green, and the numbers that are not metrics
stay green. Rule 11: the guard is new, so each decision in it is shown by a
case that goes red or green on that decision alone, and single-decision
mutants of the guard were each red (docs/QA-RESULTS.md, "F-GATE-24").
"""
import importlib.util
import io
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIPPED = ("Guide.qml", "BarWidget.qml", "Service.qml")

_spec = importlib.util.spec_from_file_location(
    "check_metric_literals", os.path.join(ROOT, "scripts", "check-metric-literals.py"))
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


def doc(*lines):
    return "import QtQuick\nItem {\n" + "\n".join("  " + line for line in lines) + "\n}\n"


class Cases(unittest.TestCase):

    def red(self, lines, name, number, count=1):
        found, counts = guard.judge("x.qml", doc(*lines))
        self.assertEqual(len(found), count, "%r: %r" % (lines, found))
        self.assertIn("`%s` is given the number %s " % (name, number), found[0])
        self.assertIn("CONVENTION-EXCEPTION", found[0])
        return found, counts

    def green(self, lines, bindings=None):
        found, counts = guard.judge("x.qml", doc(*lines))
        self.assertEqual(found, [], lines)
        if bindings is not None:
            self.assertEqual(counts["bindings"], bindings, lines)
        return counts


class TheTree(Cases):

    def test_the_shipped_files_are_green_and_their_metric_bindings_were_read(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = guard.main(["--root", ROOT])
        self.assertEqual(code, 0, out.getvalue())
        m = re.search(r"metric literal guard: (\d+) metric binding\(s\) read in 3 file\(s\) "
                      r"\((\d+) hardcoded number\(s\), (\d+) excused\), 0 problem", out.getvalue())
        self.assertIsNotNone(m, out.getvalue())
        # A scanner that stopped seeing bindings would be green on anything:
        # the guide alone binds well over a hundred metrics.
        self.assertGreaterEqual(int(m.group(1)), 150)
        self.assertEqual(int(m.group(2)), int(m.group(3)))

    def test_a_hardcoded_metric_put_into_each_shipped_file_is_red(self):
        for name in SHIPPED:
            base = read(name)
            self.assertEqual(guard.judge(name, base)[0], [], name)
            for line, metric, number in (("property int probeGap: 7", "probeGap", "7"),
                                         ("property real probeRadius: Style.cornerRadius + 3", "probeRadius", "3")):
                found, _ = guard.judge(name, inside_root(base, [line]))
                self.assertEqual(len(found), 1, "%s + %s: %r" % (name, line, found))
                self.assertIn("%s:" % name, found[0])
                self.assertIn("`%s` is given the number %s " % (metric, number), found[0])

    def test_the_same_number_under_an_exception_comment_is_green(self):
        base = read("Guide.qml")
        text = inside_root(base, ["// CONVENTION-EXCEPTION: a hairline is one device pixel on every scale",
                                  "property int probeGap: 7"])
        found, counts = guard.judge("Guide.qml", text)
        self.assertEqual(found, [])
        self.assertEqual(counts["excused"], 1)


class WhatIsRefused(Cases):

    def test_a_font_size(self):
        found, _ = self.red(["Text { font.pixelSize: 13 }"], "pixelSize", "13")
        self.assertIn("x.qml:3:26:", found[0])
        self.assertIn("a number alone", found[0])
        self.red(["Text { font.pointSize: 9.5 }"], "pointSize", "9.5")

    def test_a_radius_a_gap_and_a_margin(self):
        self.red(["Rectangle { radius: 4 }"], "radius", "4")
        self.red(["Row { spacing: 6 }"], "spacing", "6")
        self.red(["Item { anchors.leftMargin: 8 }"], "leftMargin", "8")
        self.red(["Item { anchors.margins: 8 }"], "margins", "8")
        self.red(["Item { padding: 2 }"], "padding", "2")
        self.red(["Item { leftPadding: 2 }"], "leftPadding", "2")
        self.red(["Grid { rowSpacing: 2 }"], "rowSpacing", "2")

    def test_a_border_width_dotted_and_grouped(self):
        self.red(["Rectangle { border.width: 1 }"], "border.width", "1")
        self.red(["Rectangle {", "  border {", "    width: 2", "  }", "}"], "border.width", "2")
        self.red(["Rectangle { border { width: 2; color: c } }"], "border.width", "2")

    def test_the_grouped_forms_of_the_others(self):
        self.red(["Text { font { pixelSize: 12; bold: true } }"], "pixelSize", "12")
        self.red(["Item { anchors { fill: parent; margins: 6 } }"], "margins", "6")

    def test_a_property_the_file_declares(self):
        self.red(["property int rowHeight: 44"], "rowHeight", "44")
        self.red(["readonly property real columnWidth: 240"], "columnWidth", "240")
        self.red(["property int cornerRadius: 6"], "cornerRadius", "6")
        self.red(["property int contentInset: 6"], "contentInset", "6")
        self.red(["property int tileGap: 6"], "tileGap", "6")

    def test_an_assignment_and_an_object_key(self):
        self.red(["function f(r) { r.radius = 5 }"], "radius", "5")
        self.red(["function f(r) {", "  r.border.width = 2", "}"], "border.width", "2")
        self.red(["property var f: Qt.font({ family: n, pixelSize: 12 })"], "pixelSize", "12")

    def test_a_number_beside_the_themes_value(self):
        found, _ = self.red(["Row { spacing: Style.space(2) + 3 }"], "spacing", "3")
        self.assertIn("added to, or set beside", found[0])
        self.red(["Rectangle { radius: Math.max(1, Style.cornerRadius) }"], "radius", "1")
        self.red(["Item { anchors.leftMargin: wide ? Style.space(4) : 12 }"], "leftMargin", "12")
        self.red(["Item { padding: root.scaled(12) }"], "padding", "12")

    def test_numbers_alone_are_red_whatever_their_arithmetic(self):
        found, _ = self.red(["Rectangle { radius: 4 * 2 }"], "radius", "4", count=2)
        self.assertIn("a number alone", found[0])
        self.red(["Rectangle { radius: -3 }"], "radius", "3")

    def test_an_expression_carried_onto_the_next_line_is_read_to_its_end(self):
        self.red(["Item {", "  anchors.leftMargin: wide", "    ? Style.space(4)", "    : 12", "}"], "leftMargin", "12")
        self.red(["Row {", "  spacing: Style.space(2) +", "    3", "}"], "spacing", "3")

    def test_each_binding_ends_where_the_next_begins(self):
        found, counts = guard.judge("x.qml", doc("Rectangle {", "  spacing: Style.space(2)", "  radius: 4", "  width: 13", "}"))
        self.assertEqual(len(found), 1, found)
        self.assertIn("`radius` is given the number 4 ", found[0])
        self.assertEqual(counts["bindings"], 2)

    def test_every_number_in_one_binding_is_named(self):
        found, counts = guard.judge("x.qml", doc("Row { spacing: Style.space(2) + 3 + root.extra - 5 }"))
        self.assertEqual([re.search(r"number (\S+) ", f).group(1) for f in found], ["3", "5"])
        self.assertEqual(counts["numbers"], 2)


class WhatIsNot(Cases):

    def test_the_themes_own_units(self):
        self.green(["Row { spacing: Style.space(8) }", "Text { font.pixelSize: Style.font.body }",
                    "Item { anchors.margins: Style.spacing.md }"], bindings=3)
        self.green(["Rectangle { radius: Math.min(root.cornerRadius, Style.space(1)) }"], bindings=1)
        self.green(["Row { spacing: Style.font.scaled(1.5, 2) }"], bindings=1)

    def test_zero_is_no_metric(self):
        self.green(["Column { spacing: 0 }", "Rectangle { radius: 0.0 }",
                    "Item { anchors.leftMargin: shown ? Style.spacing.md : 0 }"], bindings=3)

    def test_a_factor(self):
        self.green(["Rectangle { radius: width / 2 }", "Text { font.pixelSize: Math.round(parent.height * 0.42) }",
                    "Item { anchors.bottomMargin: (root.rowHeight - Style.font.caption) / 2 }",
                    "Row { spacing: 2 * Style.spacing.md }"], bindings=4)

    def test_a_comparison_and_an_index(self):
        self.green(["Row { spacing: root.count > 1 ? Style.space(2) : 0 }",
                    "Row { spacing: 1 < root.count ? Style.space(2) : 0 }",
                    "Item { anchors.margins: root.count === 3 ? Style.space(2) : 0 }",
                    "Item { anchors.margins: 3 !== root.count ? Style.space(2) : 0 }",
                    "Item { padding: root.count >= 2 ? Style.space(2) : 0 }",
                    "Item { padding: 2 <= root.count ? Style.space(2) : 0 }",
                    "Rectangle { radius: root.radii[1] }"], bindings=7)

    def test_a_number_inside_another_call_inside_a_style_call(self):
        self.green(["Row { spacing: Style.space(Math.max(2, root.n)) }"], bindings=1)

    def test_names_that_are_not_metrics(self):
        counts = self.green(["Item { width: 300; height: 40; x: 5; opacity: 0.5; z: 2 }",
                             "property int cursorIndex: 3", "readonly property int transientMs: 3000",
                             "property int preparedLruSize: 2", "Text { lineHeight: 1.2; maximumLineCount: 2 }",
                             "Rectangle { border.color: c; border.pixelAligned: true }",
                             "Rectangle { color: c; width: 2 }"])
        self.assertEqual(counts["bindings"], 0)

    def test_width_is_a_metric_only_under_border(self):
        self.green(["Item { width: 2 }", "Item { implicitWidth: 2 }", "Item { item.width: 2 }"], bindings=0)

    def test_a_comment_or_a_string_is_not_a_binding(self):
        self.green(["// radius: 4 was the old value", "/* font.pixelSize: 13 */",
                    'property string hint: "spacing: 6"'], bindings=0)

    def test_a_comparison_that_starts_a_line_is_not_an_assignment(self):
        self.green(["function f(radius) {", "  var same =", "    radius === 4", "  return same", "}"], bindings=0)

    def test_a_ternary_s_colon_is_not_a_binding(self):
        # `radius : 4` here is the conditional's else, inside a binding
        # whose name says nothing of metrics.
        self.green(["property int n: wide ? radius : 4"], bindings=0)

    def test_an_exception_on_the_line_or_directly_above(self):
        counts = self.green(["Rectangle { border.width: 1 } // CONVENTION-EXCEPTION: one device pixel",
                             "// CONVENTION-EXCEPTION: the focus ring is two device pixels by design",
                             "// (UX 5.4).", "Rectangle { border.width: 2 }"])
        self.assertEqual((counts["numbers"], counts["excused"]), (2, 2))

    def test_an_exception_does_not_reach_past_a_code_line(self):
        self.red(["// CONVENTION-EXCEPTION: one device pixel", "Rectangle { border.width: 1 }",
                  "Rectangle { border.width: 2 }"], "border.width", "2")


class Main(unittest.TestCase):

    def run_main(self, text):
        d = tempfile.mkdtemp(prefix="metric-literals-")
        path = os.path.join(d, "F.qml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        out = io.StringIO()
        try:
            with redirect_stdout(out):
                code = guard.main(["--root", d, path])
        finally:
            os.unlink(path)
            os.rmdir(d)
        return code, out.getvalue()

    def test_green_counts_what_it_read(self):
        code, out = self.run_main(doc("Row { spacing: Style.space(2) }", "Rectangle { radius: 0 }"))
        self.assertEqual(code, 0, out)
        self.assertIn("metric literal guard: 2 metric binding(s) read in 1 file(s) (0 hardcoded number(s), 0 excused), "
                      "0 problem(s)", out)

    def test_red_names_the_place(self):
        code, out = self.run_main(doc("Row { spacing: 6 }"))
        self.assertEqual(code, 1)
        self.assertIn("F.qml:3:18: `spacing` is given the number 6 ", out)
        self.assertIn("1 problem(s)", out)

    def test_a_file_the_scanner_cannot_read_is_an_error_not_a_pass(self):
        code, out = self.run_main('Item { objectName: "unclosed\n}')
        self.assertEqual(code, 2, out)
        self.assertIn("cannot read", out)

    def test_a_missing_file_is_an_error_not_a_pass(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = guard.main(["--root", ROOT, os.path.join(ROOT, "NoSuchFile.qml")])
        self.assertEqual(code, 2, out.getvalue())


if __name__ == "__main__":
    unittest.main()
