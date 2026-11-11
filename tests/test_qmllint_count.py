"""The gate's qmllint counts are qmllint's own (F-GATE-16).

check.sh printed, per QML file, how many warnings qmllint found, counted by
grepping qmllint's text output. On qmllint 6.12.0 that text is only a
trailing run of what the `--json` report lists (BarWidget.qml 13 lines of 44
entries with no import root, measured 2026-11-11), so the printed counts,
the CHECK_VERBOSE listing and the baseline in check.sh's header all read
low. scripts/qmllint-count.py now runs qmllint, reads the report, and
check.sh prints its numbers.

Three layers, each calling the shipping code (CLAUDE.md 12):

  * read_report over reports written here: what counts as an error, a
    warning and a Model member, and what is no report at all;
  * the script as the gate runs it, a subprocess over the real qmllint and
    generated QML files;
  * check.sh's own door, `--qmllint-file`, over the tree's BarWidget.qml:
    the line the gate PRINTS holds as many warnings as the report this test
    asks qmllint for itself. That is the layer that is red with the old
    grep put back into check.sh: on this machine the old line read 6
    warnings and 1 on Model members where the report holds 17 and 8.

Offscreen and local: qmllint reads files and prints; nothing is started
that could reach a display. Skips where qmllint is absent, and the door
case where the Omarchy shell's kit is.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "qmllint-count.py")
GATE = os.path.join(ROOT, "scripts", "check.sh")
QMLLINT = os.path.join(os.environ.get("QT_BIN", "/usr/lib/qt6/bin"), "qmllint")
SHELL_KIT = os.path.join(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"), "shell")
_s = importlib.util.spec_from_file_location("qmllint_count", SCRIPT)
counter = importlib.util.module_from_spec(_s)
_s.loader.exec_module(counter)


def report(*entries, filename="X.qml"):
    return json.dumps({"files": [{"filename": filename, "success": False, "warnings": list(entries)}], "revision": 6})


def entry(kind="warning", ident="unqualified", message="Unqualified access", line=3, column=10):
    return {"type": kind, "id": ident, "message": message, "line": line, "column": column, "suggestions": []}


MEMBER = entry(ident="missing-property", message='Member "barGlyph" not found on type "Model"')


class ReadReportTest(unittest.TestCase):
    def test_counts_warnings_and_the_model_members_among_them(self):
        text = report(entry(), entry(line=4), MEMBER,
                      entry(ident="missing-property", message='Member "b" not found on type "int"'),
                      entry(kind="info", ident="unqualified", message="Did you mean x?"))
        self.assertEqual(counter.read_report(text, 0)[:3], (0, 4, 1))

    def test_a_member_of_another_id_or_another_type_is_no_model_member(self):
        text = report(entry(ident="unqualified", message='Member "x" not found on type "Model"'),
                      entry(kind="info", ident="missing-property", message='Member "x" not found on type "Model"'))
        self.assertEqual(counter.read_report(text, 0)[:3], (0, 1, 0))

    def test_a_status_that_is_not_zero_is_an_error_even_with_none_typed_so(self):
        # qmllint 6.12.0 types a syntax error as a warning and exits 255.
        text = report(entry(ident="syntax", message="Expected token `;'"))
        self.assertEqual(counter.read_report(text, 255)[:3], (1, 1, 0))
        self.assertEqual(counter.read_report(text, 0)[:3], (0, 1, 0))

    def test_entries_typed_as_errors_are_counted_and_not_doubled_by_the_status(self):
        text = report(entry(kind="error"), entry(kind="Critical"), entry(kind="fatal"), entry())
        self.assertEqual(counter.read_report(text, 255)[:3], (3, 1, 0))
        self.assertEqual(counter.read_report(text, 0)[:3], (3, 1, 0))

    def test_every_file_entry_is_counted(self):
        text = json.dumps({"files": [{"filename": "A.qml", "warnings": [entry()]},
                                     {"filename": "B.qml", "warnings": [entry(), MEMBER]}]})
        errors, warnings, members, entries = counter.read_report(text, 0)
        self.assertEqual((errors, warnings, members), (0, 3, 1))
        self.assertEqual([name for name, _ in entries], ["A.qml", "B.qml", "B.qml"])

    def test_what_is_not_a_report_is_refused(self):
        for text in ("", "Warning: X.qml:3:10: Unqualified access [unqualified]", "[]", "{}", '{"files": {}}',
                     '{"files": [[]]}', '{"files": [{"filename": "X.qml"}]}',
                     '{"files": [{"warnings": ["text"]}]}', '{"files": [{"warnings": [{"id": "x"}]}]}'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    counter.read_report(text, 0)

    def test_a_listed_entry_is_one_line(self):
        self.assertEqual(counter.entry_line("X.qml", entry(message="two\nlines")),
                         "warning: X.qml:3:10: two lines [unqualified]")


@unittest.skipUnless(os.access(QMLLINT, os.X_OK), "qmllint is not installed")
class ScriptTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-qmllint-")
        self.addCleanup(shutil.rmtree, self.dir, True)

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def run_script(self, *args):
        return subprocess.run([sys.executable, "-I", SCRIPT, *args], capture_output=True, text=True, timeout=180,
                              stdin=subprocess.DEVNULL)

    def test_eighty_findings_are_eighty_and_each_is_listed(self):
        body = "".join("  property int p%d: missing%d\n" % (i, i) for i in range(80))
        path = self.write("Many.qml", "import QtQuick\nItem {\n" + body + "}\n")
        done = self.run_script("--list", QMLLINT, path)
        self.assertEqual(done.returncode, 0, done.stderr)
        lines = done.stdout.splitlines()
        self.assertEqual(lines[0], "0 80 0")
        self.assertEqual(len(lines), 81)
        self.assertEqual(sorted(int(re.search(r":(\d+):\d+: ", line).group(1)) for line in lines[1:]),
                         list(range(3, 83)))
        self.assertTrue(all(line.endswith("[unqualified]") for line in lines[1:]))
        self.assertEqual(self.run_script(QMLLINT, path).stdout, "0 80 0\n")

    def test_a_file_qmllint_cannot_parse_is_an_error(self):
        path = self.write("Bad.qml", "import QtQuick\nItem {\n  width: \n}\n")
        done = self.run_script(QMLLINT, path)
        self.assertEqual((done.returncode, done.stdout), (0, "1 1 0\n"), done.stderr)

    def test_a_clean_file_counts_nothing(self):
        path = self.write("Clean.qml", "import QtQuick\nItem {\n  width: 10\n}\n")
        done = self.run_script("--list", QMLLINT, path)
        self.assertEqual((done.returncode, done.stdout), (0, "0 0 0\n"), done.stderr)

    def test_no_report_is_status_two_and_one_sentence(self):
        path = self.write("Clean.qml", "import QtQuick\nItem {}\n")
        for program in ("/usr/bin/false", os.path.join(self.dir, "no-such-qmllint")):
            with self.subTest(program=program):
                done = self.run_script(program, path)
                self.assertEqual((done.returncode, done.stdout), (2, ""))
                self.assertEqual(len(done.stderr.strip().splitlines()), 1)
        self.assertEqual(self.run_script().returncode, 2)

    def test_the_script_leaves_nothing_in_its_temporary_directory(self):
        path = self.write("Clean.qml", "import QtQuick\nItem {}\n")
        scratch = os.path.join(self.dir, "tmp")
        os.mkdir(scratch)
        done = subprocess.run([sys.executable, "-I", SCRIPT, QMLLINT, path], capture_output=True, text=True,
                              timeout=180, env=dict(os.environ, TMPDIR=scratch))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(os.listdir(scratch), [])


@unittest.skipUnless(os.access(QMLLINT, os.X_OK) and os.path.isdir(os.path.join(SHELL_KIT, "Commons")),
                     "qmllint or the Omarchy shell kit is not installed")
class GateDoorTest(unittest.TestCase):
    """What check.sh PRINTS for a file, through its own door."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-qmllint-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.root = os.path.join(self.dir, "qmlroot")
        self.env = dict(os.environ, QMLROOT=self.root, TMPDIR=self.dir)
        self.env.pop("CHECK_VERBOSE", None)

    def door(self, path, **extra):
        return subprocess.run(["bash", GATE, "--qmllint-file", path], capture_output=True, text=True, timeout=300,
                              stdin=subprocess.DEVNULL, env=dict(self.env, **extra))

    def test_the_printed_count_is_the_report_s(self):
        path = os.path.join(ROOT, "BarWidget.qml")
        done = self.door(path)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        found = re.fullmatch(r"ok   BarWidget\.qml: 0 errors, (\d+) warning\(s\) \+ (\d+) on Model members\n", done.stdout)
        self.assertIsNotNone(found, done.stdout)
        # The same question put to qmllint by this test, with the import
        # root the door built: the report's own length.
        target = os.path.join(self.dir, "report.json")
        asked = subprocess.run([QMLLINT, "--json", target, "-I", self.root,
                                "-I", os.environ.get("QML_IMPORTS", "/usr/lib/qt6/qml"), path],
                               capture_output=True, timeout=180, stdin=subprocess.DEVNULL)
        self.assertEqual(asked.returncode, 0)
        with open(target, encoding="utf-8") as fh:
            entries = json.load(fh)["files"][0]["warnings"]
        warnings = [e for e in entries if e["type"] == "warning"]
        members = [e for e in warnings if 'on type "Model"' in e["message"]]
        self.assertGreater(len(members), 5)
        self.assertGreater(len(warnings), len(members))
        self.assertEqual((int(found.group(1)), int(found.group(2))),
                         (len(warnings) - len(members), len(members)))

    def test_verbose_lists_every_entry(self):
        path = os.path.join(ROOT, "BarWidget.qml")
        done = self.door(path, CHECK_VERBOSE="1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        found = re.fullmatch(r"ok   BarWidget\.qml: 0 errors, (\d+) warning\(s\) \+ (\d+) on Model members", lines[0])
        self.assertIsNotNone(found, lines[0])
        listed = [line for line in lines[1:] if line.startswith("warning: ")]
        self.assertEqual(len(listed), int(found.group(1)) + int(found.group(2)))

    def test_a_file_that_does_not_parse_fails_the_door(self):
        path = os.path.join(self.dir, "Bad.qml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("import QtQuick\nItem {\n  width: \n}\n")
        done = self.door(path)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("FAIL Bad.qml: 1 error(s), 1 warning(s)", done.stdout)
        self.assertIn("[syntax]", done.stdout)

    def test_a_qmllint_that_writes_no_report_fails_the_door(self):
        fake = os.path.join(self.dir, "bin")
        os.mkdir(fake)
        with open(os.path.join(fake, "qmllint"), "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\nexit 0\n")
        os.chmod(os.path.join(fake, "qmllint"), 0o755)
        done = self.door(os.path.join(ROOT, "BarWidget.qml"), QT_BIN=fake)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("FAIL BarWidget.qml: qmllint's findings could not be counted", done.stdout)

    def test_a_mistyped_model_member_fails_the_door(self):
        # The judge's verdict counts (tests/test_model_members.py pins the
        # lines; this runs them): a copy of BarWidget.qml with one member
        # mistyped, beside links to the tree's aggregator and its parts.
        with open(os.path.join(ROOT, "BarWidget.qml"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertEqual(text.count("Model.barGlyph("), 1)
        path = os.path.join(self.dir, "BarWidget.qml")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace("Model.barGlyph(", "Model.barGlyphh("))
        os.symlink(os.path.join(ROOT, "Model.mjs"), os.path.join(self.dir, "Model.mjs"))
        os.symlink(os.path.join(ROOT, "model"), os.path.join(self.dir, "model"))
        done = self.door(path)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("FAIL BarWidget.qml: a Model member that Model.mjs does not export", done.stdout)
        self.assertIn("Model.barGlyphh", done.stdout)
        self.assertIn("ok   BarWidget.qml: 0 errors, ", done.stdout)

    def test_the_door_takes_one_existing_file(self):
        for args in ((), (os.path.join(self.dir, "nope.qml"),), (GATE, GATE)):
            done = subprocess.run(["bash", GATE, "--qmllint-file", *args], capture_output=True, text=True,
                                  timeout=60, stdin=subprocess.DEVNULL, env=self.env)
            self.assertEqual(done.returncode, 2, done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
