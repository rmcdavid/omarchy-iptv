"""scripts/check-theme-names.py, held to the failures it guards (D-HOST-9).

The guard says no shipped QML file names, unqualified, a theme or host-kit
name that a Qt or Quickshell module it imports also exports. These tests run
it on the tree (green) and on mutants of the tree (each red): one unqualified
use reintroduced in each shipped file, a collision nested inside another
call's arguments and inside a template, an element type, and -- the case a
hard-coded list could never catch -- a Qt or Quickshell module that gains a
name the host kit also exports, built as a copy of the installed type files.
Rule 11: on rel-0160 (968d097), before Guide.qml and BarWidget.qml were
qualified, the guard printed 25 problems (Guide.qml 24, BarWidget.qml 1) and
exited 1.
"""
import importlib.util
import io
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = os.path.join(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"), "shell")
QML_DIR = "/usr/lib/qt6/qml"

_spec = importlib.util.spec_from_file_location("check_theme_names", os.path.join(ROOT, "scripts", "check-theme-names.py"))
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def once(text, old, new):
    if text.count(old) != 1:
        raise AssertionError("%r occurs %d times, not once" % (old, text.count(old)))
    return text.replace(old, new)


def inside_root(text, line):
    """`line` inserted as the first member of the file's root object."""
    m = re.search(r"^[A-Z][\w.]*\s*\{\s*$", text, re.M)
    return text[:m.end()] + "\n  " + line + text[m.end():]


@unittest.skipUnless(os.path.isfile(os.path.join(HOST, "Commons", "qmldir")) and os.path.isfile(
    os.path.join(QML_DIR, "QtQuick", "qmldir")), "no Omarchy shell or no Qt QML import path on this machine")
class ThemeNameGuard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.kit = guard.host_kit_names(HOST)

    def judge(self, name, text, qml_dir=QML_DIR):
        problems, uses = guard.judge(name, text, self.kit, qml_dir)
        return problems, uses

    def collisions(self, problems):
        return [p for p in problems if "also exports" in p]

    def run_main(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            status = guard.main(list(argv))
        return status, out.getvalue()

    # ---- the tree -------------------------------------------------------

    def test_the_shipped_tree_is_green(self):
        status, out = self.run_main("--root", ROOT, "--host", HOST, "--qml-dir", QML_DIR)
        self.assertEqual(0, status, out)
        m = re.match(r"^theme name guard: (\d+) unqualified host-kit use\(s\) in (\d+) file\(s\)", out)
        self.assertIsNotNone(m, out)
        self.assertGreater(int(m.group(1)), 200, "the scanner stopped seeing the files' Style and Util uses")
        self.assertEqual(3, int(m.group(2)))

    def test_the_host_kit_and_the_imports_are_read_from_the_installed_files(self):
        self.assertEqual({"Border": "qs.Commons", "Color": "qs.Commons", "Style": "qs.Commons", "Util": "qs.Commons"},
                         {n: m for n, m in self.kit.items() if m == "qs.Commons"})
        self.assertIn("BarWidget", self.kit)
        quick = guard.module_names("QtQuick", None, QML_DIR)
        # QtQuick's own, and what its qmldir imports (QtQml auto -> QML, Models)
        for name in ("Item", "Text", "Color", "QtObject", "ListModel", "Component"):
            self.assertIn(name, quick)
        self.assertNotIn("Color", guard.module_names("QtQuick", (6, 11), QML_DIR),
                         "QtQuick 6.11 exports no Color; the version limit is not applied")
        shell = guard.module_names("Quickshell", None, QML_DIR)
        self.assertIn("PanelWindow", shell, "Quickshell's `default import Quickshell._Window` was not followed")

    # ---- one unqualified use reintroduced, in each shipped file ----------

    def test_an_unqualified_color_in_guide_is_red(self):
        text = once(read("Guide.qml"), "property color accent: Commons.Color.accent", "property color accent: Color.accent")
        problems, _ = self.judge("Guide.qml", text)
        self.assertEqual(1, len(self.collisions(problems)), problems)
        self.assertRegex(problems[0], r"^Guide\.qml:\d+:\d+: `Color` is qs\.Commons's, and QtQuick also exports")

    def test_an_unqualified_color_in_the_bar_widget_is_red(self):
        text = once(read("BarWidget.qml"), ": Commons.Color.foreground", ": Color.foreground")
        problems, _ = self.judge("BarWidget.qml", text)
        self.assertEqual(1, len(self.collisions(problems)), problems)
        self.assertIn("BarWidget.qml:", problems[0])

    def test_an_unqualified_color_in_the_service_is_red(self):
        # Service.qml imports no qs.Commons: an unqualified Color there is
        # QtQuick's outright, which is the same mistake.
        text = inside_root(read("Service.qml"), "readonly property color probeTint: Color.accent")
        problems, _ = self.judge("Service.qml", text)
        self.assertEqual(1, len(self.collisions(problems)), problems)
        self.assertIn("Service.qml:", problems[0])

    # ---- where a use can hide --------------------------------------------

    def test_a_collision_nested_inside_another_calls_arguments_is_red(self):
        old = "Style.hoverFillFor(Commons.Color.menu.text, Commons.Color.accent)"
        text = once(read("Guide.qml"), old, "Style.hoverFillFor(Commons.Color.menu.text, Color.accent)")
        problems, _ = self.judge("Guide.qml", text)
        hits = self.collisions(problems)
        self.assertEqual(1, len(hits), problems)
        line = [i for i, l in enumerate(text.split("\n"), 1) if "Commons.Color.menu.text, Color.accent)" in l][0]
        self.assertTrue(hits[0].startswith("Guide.qml:%d:" % line), hits)

    def test_a_collision_inside_a_template_and_a_ternary_is_red(self):
        text = inside_root(read("BarWidget.qml"),
                           "function tintText(on) { return `${on ? Color.accent : Commons.Color.urgent}` }")
        problems, _ = self.judge("BarWidget.qml", text)
        self.assertEqual(1, len(self.collisions(problems)), problems)

    def test_a_name_in_a_comment_a_string_or_another_objects_member_is_not_a_use(self):
        text = inside_root(read("BarWidget.qml"),
                           "// Color.accent\n  readonly property string a: \"Color.accent\"\n"
                           "  readonly property var b: root.Color\n  readonly property var c: ({ x: 'Style' })")
        problems, _ = self.judge("BarWidget.qml", text)
        self.assertEqual([], problems)

    def test_an_element_type_the_qt_side_also_exports_is_red(self):
        # The same rule for a type: built below as a Qt module that gains the
        # host kit's BarIconButton, which BarWidget.qml instantiates.
        qml = self.qml_dir_with("QtQuick", "plugins.qmltypes", '"QtQuick/BarIconButton 6.13"')
        problems, _ = self.judge("BarWidget.qml", read("BarWidget.qml"), qml)
        hits = self.collisions(problems)
        self.assertEqual(1, len(hits), problems)
        self.assertIn("`BarIconButton` is qs.Ui's, and QtQuick also exports", hits[0])

    # ---- a Qt or Quickshell update that adds a colliding name ------------

    def qml_dir_with(self, module, typeinfo, export, append=None):
        """A copy of the installed QML import path in which `module`'s
        `typeinfo` gains one more export (or, with `append`, the named file
        gains one more line): symlinks to everything else."""
        work = tempfile.mkdtemp(prefix="omarchy-iptv-themenames-")
        self.addCleanup(shutil.rmtree, work, True)
        for entry in os.listdir(QML_DIR):
            if entry != module.split(".")[0]:
                os.symlink(os.path.join(QML_DIR, entry), os.path.join(work, entry))
        src = os.path.join(QML_DIR, *module.split("."))
        top = os.path.join(work, module.split(".")[0])
        # every sibling of the module directory linked, the module itself copied
        os.makedirs(top)
        top_src = os.path.join(QML_DIR, module.split(".")[0])
        rel = module.split(".")[1:]
        if rel:
            for entry in os.listdir(top_src):
                if entry != rel[0]:
                    os.symlink(os.path.join(top_src, entry), os.path.join(top, entry))
        dst = os.path.join(work, *module.split("."))
        os.makedirs(dst, exist_ok=True)
        for entry in os.listdir(src):
            if entry == typeinfo:
                with open(os.path.join(src, entry), encoding="utf-8") as fh:
                    text = fh.read()
                if append is not None:
                    text = text.rstrip("\n") + "\n" + append + "\n"
                else:
                    text = text.replace("exports: [", "exports: [%s, " % export, 1)
                with open(os.path.join(dst, entry), "w", encoding="utf-8") as fh:
                    fh.write(text)
            else:
                os.symlink(os.path.join(src, entry), os.path.join(dst, entry))
        return work

    def test_a_qt_update_that_adds_a_host_kit_name_turns_the_tree_red(self):
        qml = self.qml_dir_with("QtQuick", "plugins.qmltypes", '"QtQuick/Style 6.13"')
        status, out = self.run_main("--root", ROOT, "--host", HOST, "--qml-dir", qml)
        self.assertEqual(1, status, out)
        files = sorted(set(re.findall(r"^(\w+\.qml):\d+:\d+: `Style`", out, re.M)))
        self.assertEqual(["BarWidget.qml", "Guide.qml"], files, out[:600])
        guide_uses = len([1 for _, _, n in guard.unqualified_uses(read("Guide.qml"), {"Style"})])
        self.assertEqual(guide_uses, len(re.findall(r"^Guide\.qml:\d+:\d+: `Style`", out, re.M)))

    def test_a_composite_type_or_singleton_in_a_qt_qmldir_counts_too(self):
        # A Qt module can export a name from its qmldir alone (Quickshell.Io's
        # FileView is a qmldir composite): a composite singleton there is
        # searched beside the host's by order, which protects nothing either.
        for line in ("singleton Style 6.13 Style.qml", "Style 6.13 Style.qml"):
            qml = self.qml_dir_with("QtQuick", "qmldir", None, append=line)
            problems, _ = self.judge("BarWidget.qml", read("BarWidget.qml"), qml)
            self.assertEqual(len(guard.unqualified_uses(read("BarWidget.qml"), {"Style"})),
                             len(self.collisions(problems)), (line, problems))
        qml = self.qml_dir_with("QtQuick", "qmldir", None, append="internal Style Style.qml")
        problems, _ = self.judge("BarWidget.qml", read("BarWidget.qml"), qml)
        self.assertEqual([], problems, "an internal type is no importer's name")

    def test_a_quickshell_update_is_judged_only_in_the_files_that_import_it(self):
        qml = self.qml_dir_with("Quickshell", "quickshell-core.qmltypes", '"Quickshell/Util 0.0"')
        status, out = self.run_main("--root", ROOT, "--host", HOST, "--qml-dir", qml)
        self.assertEqual(1, status, out)
        # Guide.qml imports Quickshell and uses Util; BarWidget.qml uses Util
        # and does not import Quickshell; Service.qml imports it and uses none.
        self.assertEqual(["Guide.qml"], sorted(set(re.findall(r"^(\w+\.qml):\d+:\d+: `Util`", out, re.M))), out[:600])

    # ---- the import's version is the engine's -----------------------------

    def test_a_versioned_import_is_judged_at_its_version(self):
        body = "\nItem {\n  property color c: Color.accent\n}\n"
        older, _ = self.judge("Old.qml", "import QtQuick 6.11\nimport qs.Commons\n" + body)
        newer, _ = self.judge("New.qml", "import QtQuick 6.12\nimport qs.Commons\n" + body)
        latest, _ = self.judge("Latest.qml", "import QtQuick\nimport qs.Commons\n" + body)
        named, _ = self.judge("Named.qml", "import QtQuick\nimport qs.Commons as Commons\n"
                                           "\nItem {\n  property color c: Commons.Color.accent\n}\n")
        self.assertEqual([], older)
        self.assertEqual(1, len(self.collisions(newer)), newer)
        self.assertEqual(1, len(self.collisions(latest)), latest)
        self.assertEqual([], named)

    # ---- it refuses to pass blind ------------------------------------------

    def test_a_module_it_cannot_read_is_red(self):
        problems, _ = self.judge("X.qml", "import QtQuick\nimport Not.A.Module\nimport qs.Commons\n"
                                          "\nItem {\n  width: Style.space(1)\n}\n")
        self.assertEqual(1, len(problems), problems)
        self.assertIn("Not.A.Module: no qmldir", problems[0])

    def test_an_unqualified_directory_import_is_red(self):
        problems, _ = self.judge("X.qml", 'import QtQuick\nimport "parts"\nimport qs.Commons\n'
                                          "\nItem {\n  width: Style.space(1)\n}\n")
        self.assertEqual(1, len(problems), problems)
        self.assertIn('directory import ("parts")', problems[0])

    def test_a_file_that_imports_the_kit_and_uses_nothing_of_it_is_red(self):
        problems, _ = self.judge("X.qml", "import QtQuick\nimport qs.Commons\n\nItem {\n  width: 4\n}\n")
        self.assertEqual(1, len(problems), problems)
        self.assertIn("found no unqualified use", problems[0])

    def test_an_unreadable_host_kit_is_red(self):
        work = tempfile.mkdtemp(prefix="omarchy-iptv-themenames-")
        self.addCleanup(shutil.rmtree, work, True)
        status, out = self.run_main("--root", ROOT, "--host", work, "--qml-dir", QML_DIR)
        self.assertEqual(1, status, out)
        self.assertIn("the host kit is unreadable", out)


if __name__ == "__main__":
    unittest.main()
