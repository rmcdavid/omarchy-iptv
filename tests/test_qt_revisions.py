"""scripts/check-qt-revisions.py, held to the failure it guards (D-HOST-10).

The host loads a plugin's `import QtQuick` at the version its load patch
pins (6.11 today) while the gate loads the same file at the installed Qt's
newest, so a type or member Qt added in between loads in every check and
fails on the host. The guard reads the pin out of the quickshell binary and
the difference out of the installed type files.

Two sets of tests. The first runs the guard over type files BUILT HERE, a
small Qt whose 6.12 adds a type and four members, so the rule is held
whatever Qt this machine carries. The second runs it over the installed Qt
and the shipped tree: green as it stands, red with a hidden member or type
written into each shipped file. Rule 11: the guard is new, so
its decisions were broken one at a time and each mutant turned tests here
red (docs/QA-RESULTS.md, "D-HOST-10").

D-REL-14 C2: the shipped files are release.py's shipped_code, so the tree's
count and the files mutated here are derived from it, a code-behind among
them once one ships, judged under its importer's imports; and a hidden
member written into the guards' fixture code-behind is red (ab3d287's guard
read ALLOWLIST's .qml entries alone and passed it).
"""
import importlib.util
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
import split_fixture  # noqa: E402  the shipped code, and a split tree (D-REL-14)
QML_DIR = "/usr/lib/qt6/qml"
QUICKSHELL = os.environ.get("OMARCHY_IPTV_QUICKSHELL", "/usr/bin/quickshell")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load("check_qt_revisions", os.path.join(ROOT, "scripts", "check-qt-revisions.py"))

# The host's rewrite as the installed 4.5.0 quickshell carries it, written
# out so the built-here tests do not need the binary.
PATTERN = r"^([ \t]*import[ \t]+QtQuick)(?=[ \t]*(?:as[ \t]|;|//|/\*|$))"
REWRITE = (re.compile(PATTERN), r"\1 6.11")

R612 = 6 * 256 + 12
R602 = 6 * 256 + 2

TOY_QTQUICK = """import QtQuick.tooling 1.2

// A small QtQuick: what 6.12 adds is marked.
Module {
    Component {
        file: "item.h"
        name: "ToyItem"
        prototype: "ToyObject"
        exports: ["QtQuick/Item 2.0", "QtQuick/Item 6.0", "QtQuick/Item 6.12"]
        exportMetaObjectRevisions: [512, 1536, %(new)d]
        Property { name: "width"; type: "double"; index: 0 }
        Property {
            name: "mutabilityGroup"
            revision: %(new)d
            type: "int"
            index: 1
        }
        Signal { name: "mutabilityGroupChanged"; revision: %(new)d }
        Method {
            name: "grab"
            revision: %(old)d
            Parameter { name: "size"; type: "QSize" }
        }
    }
    Component {
        name: "ToyAnimation"
        prototype: "ToyObject"
        exports: ["QtQuick/Animation 2.0"]
        Property { name: "loops"; type: "int"; index: 0 }
        Signal { name: "finished"; revision: %(old)d }
    }
    Component {
        name: "ToyNumberAnimation"
        prototype: "ToyAnimation"
        exports: ["QtQuick/NumberAnimation 2.0"]
    }
    Component {
        name: "ToyAnimatedImage"
        prototype: "ToyItem"
        exports: ["QtQuick/AnimatedImage 2.0", "QtQuick/AnimatedImage 6.12"]
        Property { name: "loops"; revision: %(new)d; type: "int"; index: 0 }
        Signal { name: "finished"; revision: %(new)d }
    }
    Component {
        name: "ToyColor"
        exports: ["QtQuick/Color 6.12"]
        isCreatable: false
        isSingleton: true
    }
    Component {
        name: "ToyStyleHints"
        Property { name: "wakeUpDelay"; revision: %(new)d; type: "int"; index: 0 }
    }
}
""" % {"new": R612, "old": R602}

TOY_MODELS = """import QtQuick.tooling 1.2
Module {
    Component {
        name: "ToyListModel"
        prototype: "ToyObject"
        exports: ["QtQml.Models/ListModel 2.0"]
        Property { name: "sortRole"; revision: %d; type: "int"; index: 0 }
    }
    Component {
        name: "ToyRangeFilter"
        prototype: "ToyObject"
        exports: ["QtQml.Models/RangeFilter 6.12"]
    }
}
""" % R612

TOY_BUILTINS = """import QtQuick.tooling 1.2
Module {
    Component {
        name: "ToyObject"
        exports: ["QML/QtObject 1.0"]
        Property { name: "objectName"; type: "QString"; index: 0 }
    }
}
"""

TOY_PINNED = """import QtQuick.tooling 1.2
Module {
    Component {
        name: "ToyPinned"
        prototype: "ToyObject"
        exports: ["Toy.Pinned/Pinned 1.0", "Toy.Pinned/Late 6.12"]
    }
}
"""


def build_qt(root, models_import="import QtQml.Models auto"):
    def module(uri, qmldir, types):
        d = os.path.join(root, *uri.split("."))
        os.makedirs(d)
        with open(os.path.join(d, "qmldir"), "w", encoding="utf-8") as fh:
            fh.write("module %s\ntypeinfo plugins.qmltypes\n%s" % (uri, qmldir))
        with open(os.path.join(d, "plugins.qmltypes"), "w", encoding="utf-8") as fh:
            fh.write(types)

    module("QML", "", TOY_BUILTINS)
    module("QtQuick", "import QtQml auto\n", TOY_QTQUICK)
    module("QtQml", "import QML 1.0\n%s\n" % models_import, TOY_BUILTINS.replace("QML/QtObject", "QtQml/QtObject"))
    module("QtQml.Models", "depends QML 1.0\n", TOY_MODELS)
    module("Toy.Pinned", "import QtQuick 6.12\n", TOY_PINNED)
    return root


class BuiltHere(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.mkdtemp(prefix="qt-revisions-")
        cls.qt = build_qt(os.path.join(cls.work, "qml"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def judge(self, body, header="import QtQuick\n", qt=None):
        problems, counts = guard.judge("x.qml", header + body, REWRITE, qt or self.qt)
        return problems, counts

    def red(self, body, word, header="import QtQuick\n"):
        problems, _ = self.judge(body, header)
        self.assertEqual(len(problems), 1, "%r: %r" % (body, problems))
        self.assertIn("`%s`" % word, problems[0])
        self.assertIn("D-HOST-10", problems[0])
        return problems[0]

    def green(self, body, header="import QtQuick\n"):
        problems, _ = self.judge(body, header)
        self.assertEqual(problems, [], body)

    def test_the_toy_qt_reads_as_it_was_built(self):
        _, (types, hidden, changed) = self.judge("Item {}")
        self.assertTrue(changed)
        self.assertEqual(types, 2)  # Color, and RangeFilter through `auto`
        scope = guard.Scope("import QtQuick\nItem {}", REWRITE, self.qt, {})
        self.assertEqual(sorted(scope.types), ["Color", "RangeFilter"])
        self.assertEqual(sorted(scope.hidden), [
            "finished", "loops", "loopsChanged", "mutabilityGroup", "mutabilityGroupChanged",
            "onFinished", "onLoopsChanged", "onMutabilityGroupChanged", "onSortRoleChanged", "onWakeUpDelayChanged",
            "sortRole", "sortRoleChanged", "wakeUpDelay", "wakeUpDelayChanged"])
        self.assertEqual(hidden, 14)

    def test_a_member_qt_added_after_the_pin_is_red_as_a_binding(self):
        message = self.red("Item { mutabilityGroup: 0 }", "mutabilityGroup")
        self.assertIn("x.qml:2:8:", message)
        self.assertIn("after 6.11", message)
        self.assertIn("in a Item", message)

    def test_it_is_red_on_a_subtype_through_the_prototype_chain(self):
        self.red("Item { AnimatedImage { mutabilityGroup: 1 } }", "mutabilityGroup")

    def test_its_handlers_are_red(self):
        self.red("Item { onMutabilityGroupChanged: {} }", "onMutabilityGroupChanged")
        self.red("Item { AnimatedImage { onFinished: {} } }", "onFinished")
        self.red("Item { AnimatedImage { onLoopsChanged: {} } }", "onLoopsChanged")

    def test_an_old_member_of_the_same_name_on_another_type_passes(self):
        self.green("Item { NumberAnimation { loops: 3; onFinished: {} } }")
        self.green("Item { NumberAnimation on width { loops: 3 } }")
        self.green("Item { Animation { loops: 3 } }")

    def test_the_new_member_of_that_name_is_red_where_it_is_the_nearest(self):
        self.red("Item { AnimatedImage { loops: 2 } }", "loops")

    def test_a_member_revisioned_before_the_pin_passes(self):
        self.green("Item { function f() { return grab() } }")

    def test_a_member_access_on_anything_is_red(self):
        self.red("Item { width: Qt.styleHints.wakeUpDelay }", "wakeUpDelay")
        self.red("Item { function f(o) { return o.finished } }", "finished")
        self.red("Item { function f(o) { return o?.loops } }", "loops")

    def test_a_bare_name_a_declaration_and_an_unknown_element_are_red(self):
        self.red("Item { function f() { var finished = 1; return 2 } }", "finished")
        self.red("Item { property int loops: 1 }", "loops")
        self.red("Item { Elsewhere { loops: 1 } }", "loops")
        self.red("Item { width: ok ?\n loops :\n 2 }", "loops")

    def test_a_name_before_a_colon_inside_an_expression_is_not_a_binding_key(self):
        # NumberAnimation has an old `loops`; this one is a bare name in a
        # conditional, whatever it resolves to at run time.
        self.red("Item { NumberAnimation { duration: ok ? loops : 2 } }", "loops")

    def test_a_member_of_a_module_imported_auto_is_red(self):
        message = self.red("Item { ListModel { sortRole: 1 } }", "sortRole")
        self.assertIn("in a ListModel", message)

    def test_an_alias_an_import_line_declares_is_not_a_use(self):
        self.green("Item { width: Color.x }", 'import QtQuick\nimport "colours.js" as Color\n')

    def test_a_script_object_key_inside_an_element_is_not_read_as_that_elements_binding(self):
        # `{ loops: 1 }` is an object literal, not NumberAnimation's own key.
        self.red("Item { NumberAnimation { property var o: ({ loops: 1 }) } }", "loops")

    def test_an_exception_with_a_reason_passes_and_one_without_does_not(self):
        self.green("Item {\n  // QT-REVISION-EXCEPTION: a field of the helper's reply\n  property bool finished: false\n}")
        self.green("Item {\n  // The reply's own word.\n  // QT-REVISION-EXCEPTION: a field of the helper's reply\n"
                   "  // (see the service).\n  property bool finished: false\n}")
        self.green("Item {\n  property bool finished: false // QT-REVISION-EXCEPTION: the reply's field\n}")
        self.red("Item {\n  // QT-REVISION-EXCEPTION:\n  property bool finished: false\n}", "finished")
        self.red("Item {\n  // QT-REVISION-EXCEPTION: the reply's field\n  property int a: 1\n"
                 "  property bool finished: false\n}", "finished")

    def test_a_comment_or_a_string_is_not_a_use(self):
        self.green('Item {\n  // mutabilityGroup, loops and Color are not used here\n'
                   '  objectName: "finished loops Color"\n  /* RangeFilter */\n}')

    def test_a_type_first_exported_after_the_pin_is_red(self):
        message = self.red("Item { property color c: Color.red }", "Color")
        self.assertIn("QtQuick exports only after 6.11", message)
        self.red("Item { property var s: ({ ...Color }) }", "Color")

    def test_a_type_of_a_module_imported_auto_is_red(self):
        message = self.red("Item { RangeFilter {} }", "RangeFilter")
        self.assertIn("QtQml.Models", message)

    def test_a_module_qtquick_does_not_import_auto_keeps_its_own_version(self):
        qt = build_qt(os.path.join(self.work, "fixed"), models_import="import QtQml.Models 6.12")
        problems, (types, _hidden, _changed) = self.judge("Item { RangeFilter {} }", qt=qt)
        self.assertEqual(problems, [])
        self.assertEqual(types, 1)

    def test_the_host_kits_name_behind_its_alias_is_not_qts(self):
        self.green("Item { property color c: Commons.Color.red }",
                   "import QtQuick\nimport qs.Commons as Commons\n")

    def test_a_qt_import_behind_an_alias_is_judged(self):
        header = "import QtQuick as Q\n"
        self.red("Q.Item { property color c: Q.Color.red }", "Color", header)
        self.red("Q.Item { mutabilityGroup: 0 }", "mutabilityGroup", header)

    def test_a_file_that_pins_its_own_version_is_read_as_written(self):
        problems, (types, hidden, changed) = self.judge(
            "Item { mutabilityGroup: 0; property color c: Color.red }", "import QtQuick 6.12\n")
        self.assertEqual((problems, types, hidden, changed), ([], 0, 0, False))

    def test_another_import_that_brings_qtquick_back_at_its_newest_hides_nothing(self):
        # Toy.Pinned's qmldir says `import QtQuick 6.12`, as QtQuick.Window's
        # says `import QtQuick auto`: the rewrite cannot reach it.
        problems, (types, hidden, _changed) = self.judge(
            "Item { mutabilityGroup: 0 }", "import QtQuick\nimport Toy.Pinned\n")
        self.assertEqual((problems, types, hidden), ([], 0, 0))

    def test_a_module_with_no_qmldir_is_red(self):
        problems, _ = self.judge("Item {}", "import QtQuick\nimport Not.There\n")
        self.assertEqual(len(problems), 1)
        self.assertIn("no qmldir", problems[0])

    def test_a_type_file_that_cannot_be_parsed_is_red(self):
        for label, text, word in (("empty", "import QtQuick.tooling 1.2\nModule {\n}\n", "holds no Component"),
                                  ("cut", TOY_QTQUICK[:TOY_QTQUICK.index("    Component {\n        name: \"ToyAnimation\"")], "unclosed"),
                                  ("junk", "import QtQuick.tooling 1.2\nModule { Component { name: @ } }\n", "unreadable")):
            qt = build_qt(os.path.join(self.work, "bad-" + label))
            with open(os.path.join(qt, "QtQuick", "plugins.qmltypes"), "w", encoding="utf-8") as fh:
                fh.write(text)
            problems, _ = self.judge("Item {}", qt=qt)
            self.assertEqual(len(problems), 1, label)
            self.assertIn(word, problems[0], label)

    def test_a_file_the_scanner_cannot_read_is_red(self):
        problems, _ = self.judge('Item { objectName: "unclosed\n}')
        self.assertEqual(len(problems), 1)
        self.assertIn("scanner lost its place", problems[0])


class Main(unittest.TestCase):
    """main(), with a quickshell that is a file of the right bytes."""

    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.mkdtemp(prefix="qt-revisions-main-")
        cls.qt = build_qt(os.path.join(cls.work, "qml"))
        cls.patched = os.path.join(cls.work, "quickshell")
        with open(cls.patched, "wb") as fh:
            fh.write(b"\x7fELF" + guard.PRAGMA.encode("ascii") + b"\x00\x00"
                     + PATTERN.encode("utf-16-le") + b"\x00\x00\x01\x02" + r"\1 6.11".encode("utf-16-le") + b"\x00\x00")
        cls.plain = os.path.join(cls.work, "quickshell-plain")
        with open(cls.plain, "wb") as fh:
            fh.write(b"\x7fELF no load patch in this one\x00")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, ignore_errors=True)

    def run_main(self, texts, quickshell):
        d = tempfile.mkdtemp(dir=self.work)
        paths = []
        for k, text in enumerate(texts):
            paths.append(os.path.join(d, "F%d.qml" % k))
            with open(paths[-1], "w", encoding="utf-8") as fh:
                fh.write(text)
        out = io.StringIO()
        with redirect_stdout(out):
            rc = guard.main(["--qml-dir", self.qt, "--quickshell", quickshell] + paths)
        return rc, out.getvalue()

    def test_the_rewrite_is_read_out_of_the_binary(self):
        pattern, replacement = guard.rewrite_from_binary(self.patched)
        self.assertEqual((pattern.pattern, replacement), (PATTERN, r"\1 6.11"))
        self.assertIsNone(guard.rewrite_from_binary(self.plain))

    def test_green_says_what_it_compared(self):
        rc, out = self.run_main(["import QtQuick\nItem { width: 1 }\n", "import QtQuick 6.12\nItem {}\n"], self.patched)
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"^qt revision guard: 2 file\(s\), 1 read as the host's rewrite pins them \(QtQuick 6\.11\): "
                              r"2 type name\(s\) and 14 member name\(s\)")

    def test_red_names_the_use(self):
        rc, out = self.run_main(["import QtQuick\nItem { mutabilityGroup: 0 }\n"], self.patched)
        self.assertEqual(rc, 1)
        self.assertIn("F0.qml:2:8: `mutabilityGroup`", out)
        self.assertNotIn("none used", out)

    def test_no_quickshell_is_red(self):
        rc, out = self.run_main(["import QtQuick\nItem {}\n"], os.path.join(self.work, "absent"))
        self.assertEqual(rc, 1)
        self.assertIn("no quickshell", out)

    def test_a_quickshell_without_the_rewrite_is_green_and_says_nothing_was_judged(self):
        rc, out = self.run_main(["import QtQuick\nItem { mutabilityGroup: 0 }\n"], self.plain)
        self.assertEqual(rc, 0)
        self.assertIn("carries no QtQuick import rewrite", out)
        self.assertIn("nothing to judge", out)
        self.assertNotIn("none used", out)

    def test_a_rewrite_that_reaches_no_file_is_red(self):
        rc, out = self.run_main(["import QtQuick 6.12\nItem {}\n", "import QtQml\nQtObject {}\n"], self.patched)
        self.assertEqual(rc, 1)
        self.assertIn("changes no import line", out)


def installed_rewrite():
    if not os.path.isfile(QUICKSHELL) or not os.path.isfile(os.path.join(QML_DIR, "QtQuick", "qmldir")):
        return None
    return guard.rewrite_from_binary(QUICKSHELL)


@unittest.skipUnless(installed_rewrite() is not None,
                     "no quickshell carrying the load patch, or no Qt QML import path, on this machine")
class Installed(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rewrite = installed_rewrite()
        with open(os.path.join(ROOT, "Guide.qml"), encoding="utf-8") as fh:
            cls.scope = guard.Scope(fh.read(), cls.rewrite, QML_DIR, {})

    def shipped(self, name):
        with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
            return fh.read()

    def inside_root(self, text, line):
        m = re.search(r"^[A-Z][\w.]*\s*\{\s*$", text, re.M)
        return text[:m.end()] + "\n  " + line + text[m.end():]

    def test_this_reading_of_the_binary_is_the_load_patch_tests_own(self):
        other = _load("host_load_patch", os.path.join(ROOT, "tests", "test_host_load_patch.py"))
        theirs = other.rewrite_from_binary(QUICKSHELL)
        self.assertEqual((self.rewrite[0].pattern, self.rewrite[1]), (theirs[0].pattern, theirs[1]))
        self.assertEqual(guard.PRAGMA, other.PRAGMA)

    def code(self):
        """(name, importer's text or None) for every shipped file of code."""
        out = []
        for entry in split_fixture.shipped(ROOT):
            imp = None if entry.importer == entry.path else self.shipped(os.path.relpath(entry.importer, ROOT))
            out.append((os.path.relpath(entry.path, ROOT), imp))
        return out

    def test_the_tree_is_green(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = guard.main(["--root", ROOT, "--qml-dir", QML_DIR, "--quickshell", QUICKSHELL])
        self.assertEqual(rc, 0, out.getvalue())
        n = len(self.code())
        self.assertGreaterEqual(n, 3)
        self.assertRegex(out.getvalue(), r"^qt revision guard: %d file\(s\), %d read as the host's rewrite pins them" % (n, n))

    def test_every_shipped_file_is_one_the_rewrite_reaches(self):
        for name, imp in self.code():
            _, (_types, _hidden, changed) = guard.judge(name, self.shipped(name), self.rewrite, QML_DIR, importer_text=imp)
            self.assertTrue(changed, name)

    def test_what_the_row_measured_is_what_the_installed_type_files_say(self):
        # rc-host9's measurement: Item.mutabilityGroup does not load at 6.11.
        # Skipped once the pin reaches the installed Qt and nothing is hidden.
        if not self.scope.hidden and not self.scope.types:
            self.skipTest("the installed Qt has nothing past the host's pin")
        if self.rewrite[1] != r"\1 6.11":
            self.skipTest("the host pins another version than the row measured")
        self.assertIn("mutabilityGroup", self.scope.hidden)
        self.assertIn("Color", self.scope.types)
        self.assertEqual(self.scope.host["QtQml.Models"], (6, 11))
        self.assertEqual(self.scope.nearest("Item", "mutabilityGroup"), "hidden")
        self.assertEqual(self.scope.nearest("ListView", "mutabilityGroup"), "hidden")
        self.assertEqual(self.scope.nearest("NumberAnimation", "loops"), "old")
        self.assertEqual(self.scope.nearest("Item", "noSuchMember"), None)
        self.assertEqual(self.scope.nearest("NoSuchType", "loops"), None)

    def test_a_hidden_member_or_type_written_into_each_shipped_file_is_red(self):
        if not self.scope.hidden or not self.scope.types:
            self.skipTest("the installed Qt has nothing past the host's pin")
        member = sorted(n for n in self.scope.hidden if not n.startswith("on") and not n.endswith("Changed"))[0]
        type_name = sorted(self.scope.types)[0]
        for name, imp in self.code():
            text = self.shipped(name)
            self.assertEqual(guard.judge(name, text, self.rewrite, QML_DIR, importer_text=imp)[0], [], name)
            for line, js, word in (("property var probeA: root.%s" % member, "var probeA = root.%s" % member, member),
                                   ("property var probeB: %s" % type_name, "var probeB = %s" % type_name, type_name)):
                problems, _ = guard.judge(name, split_fixture.into_code(name, text, line, js), self.rewrite, QML_DIR,
                                          importer_text=imp)
                self.assertEqual(len(problems), 1, "%s + %s: %r" % (name, line, problems))
                self.assertIn("`%s`" % word, problems[0])

    def run_tree(self, mutant=None):
        with tempfile.TemporaryDirectory() as tmp:
            split_fixture.tree(tmp, mutant)
            out = io.StringIO()
            with redirect_stdout(out):
                rc = guard.main(["--root", tmp, "--qml-dir", QML_DIR, "--quickshell", QUICKSHELL])
            return rc, out.getvalue()

    def test_the_fixture_code_behind_is_read_under_its_importers_imports(self):
        rc, out = self.run_tree()
        self.assertEqual(rc, 0, out)
        self.assertRegex(out, r"^qt revision guard: 2 file\(s\), 2 read as the host's rewrite pins them")

    def test_a_hidden_member_in_a_code_behind_is_red(self):
        if "mutabilityGroup" not in self.scope.hidden:
            self.skipTest("the installed Qt hides no mutabilityGroup from the host's pin")
        rc, out = self.run_tree("item.mutabilityGroup = 0")
        self.assertEqual(rc, 1, out)
        self.assertRegex(out, r"Service-demo\.js:\d+:\d+: `mutabilityGroup` is the name of a member Qt added after")


if __name__ == "__main__":
    unittest.main()
