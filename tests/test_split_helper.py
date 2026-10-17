"""D-REL-7: the helper is a stub and its parts, and behaves as one file.

scripts/split-helper.py cuts the one-file `bin/omarchy-iptv` into a stub that
shields and then compiles `bin/helper/NN-*.py` into its own namespace, and
`--check` judges the tree in the gate. These cases run the REAL script
(rule 12) over synthetic one-file helpers small enough to read, built with
the script's own banners so the cut is the shipping cut, and then over this
repository's tree. Every decision the script makes has a case that goes red
when that decision is broken (rule 11: the script is new, so the red runs
are mutations of it, recorded in the write-up on the dev branch).
"""
import importlib.machinery
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "split-helper.py"
sys.path.insert(0, str(ROOT / "scripts"))
import helper_files  # noqa: E402

_spec = importlib.util.spec_from_file_location("split_helper", str(SCRIPT))
split = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(split)


def one_file_helper(main_body='    return used_everywhere() + 1\n'):
    """A one-file helper with every banner the cut looks for: a head ending
    at the shield, one function per section, a `main` in the last, and the
    guard. Section 1 defines `used_everywhere`, which the LAST section calls,
    so a cut that broke the one-namespace property cannot run."""
    out = ['#!/usr/bin/env python3\n', '"""a helper"""\n',
           'from __future__ import annotations\n', '\n', 'import sys\n', '\n', '\n',
           'def shield_environment() -> bool:\n', '    return True\n', '\n', '\n',
           split.SHIELD_LINE, '\n', 'import os\n', '\n', '\n',
           'def used_everywhere() -> int:\n', '    return 41\n', '\n', '\n']
    for index, (name, banner) in enumerate(split.CUTS[1:], 2):
        out += [banner + '\n', 'def section_%d() -> str:\n' % index,
                '    return "%s"\n' % name, '\n', '\n']
    out += ['def main() -> int:\n', main_body, '\n', '\n', split.GUARD_LINE,
            '    sys.exit(main() - 42)\n']
    return ''.join(out)


class Tree:
    """A scratch plugin root holding a one-file helper."""

    def __init__(self, case, text=None):
        self.root = tempfile.mkdtemp(prefix="split-helper-test-")
        case.addCleanup(shutil.rmtree, self.root, True)
        os.makedirs(os.path.join(self.root, "bin"))
        self.text = text if text is not None else one_file_helper()
        self.input = os.path.join(self.root, "one-file")
        with open(self.input, "w", encoding="utf-8") as fh:
            fh.write(self.text)
        with open(self.path(helper_files.STUB), "w", encoding="utf-8") as fh:
            fh.write(self.text)
        os.chmod(self.path(helper_files.STUB), 0o755)

    def path(self, rel):
        return os.path.join(self.root, rel)

    def part(self, name):
        return self.path("%s/%s" % (helper_files.PART_DIR, name))

    def read(self, rel):
        with open(self.path(rel), encoding="utf-8") as fh:
            return fh.read()

    def write_file(self, rel, text):
        with open(self.path(rel), "w", encoding="utf-8") as fh:
            fh.write(text)

    def run_script(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), "--root", self.root] + list(args),
                              capture_output=True, text=True, timeout=60)

    def split(self):
        done = self.run_script("--write", "--input", self.input)
        assert done.returncode == 0, done.stderr
        return self


class TheCutTest(unittest.TestCase):

    def test_a_cut_writes_verifies_and_checks_clean(self):
        tree = Tree(self).split()
        self.assertEqual(split.verify(tree.root, tree.text), [])
        self.assertEqual(split.check(tree.root), [])
        self.assertEqual(sorted(os.listdir(tree.path(helper_files.PART_DIR))),
                         [name for name, _ in split.CUTS])

    def test_the_cut_loses_nothing(self):
        """head + body + tail is the input and the parts without their header
        are the body: the two facts the cut asserts, observed from outside."""
        tree = Tree(self).split()
        stub = tree.read(helper_files.STUB)
        head, rest = stub.split(split.SHIELD_LINE, 1)
        tail = rest[rest.index(split.GUARD_LINE):]
        body = "".join(tree.read("%s/%s" % (helper_files.PART_DIR, n))[len(split.HEADER):]
                       for n, _ in split.CUTS)
        self.assertEqual(head + split.SHIELD_LINE + body + tail, tree.text)

    def test_the_split_helper_runs_as_one_file_and_one_module(self):
        """The property the design rests on. Run, the last part's `main`
        calls the first part's function (exit 0 = 41 + 1 - 42). Loaded the
        way tests/helper_loader.py loads the real one, replacing that
        function on the module reaches the caller in another part."""
        tree = Tree(self).split()
        done = subprocess.run([sys.executable, tree.path(helper_files.STUB)],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        loader = importlib.machinery.SourceFileLoader("split_probe", tree.path(helper_files.STUB))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader("split_probe", loader))
        loader.exec_module(module)
        self.assertEqual(module.main(), 42)
        module.used_everywhere = lambda: 99
        self.assertEqual(module.main(), 100, "a patch on the module did not reach another part")
        self.assertEqual(module.section_11(), "11-cli.py")

    def test_the_parts_are_compiled_after_the_shield(self):
        stub = Tree(self).split().read(helper_files.STUB)
        self.assertLess(stub.index(split.SHIELD_LINE), stub.index("_load_parts(globals())"))

    def test_a_part_that_cannot_be_read_ends_the_run_in_one_line(self):
        tree = Tree(self).split()
        os.unlink(tree.part("04-epg.py"))
        done = subprocess.run([sys.executable, tree.path(helper_files.STUB)],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stderr.count("\n"), 1, done.stderr)
        self.assertIn("bin/helper/04-epg.py", done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_write_refuses_a_root_that_already_has_parts(self):
        tree = Tree(self).split()
        done = tree.run_script("--write", "--input", tree.input)
        self.assertEqual(done.returncode, 1)
        self.assertIn("already holds files", done.stderr)

    def test_a_banner_that_is_missing_or_doubled_is_refused(self):
        name, banner = split.CUTS[3]
        for text in (one_file_helper().replace(banner, "# moved"),
                     one_file_helper().replace(banner, banner + "\n" + banner)):
            with self.assertRaises(split.SplitError) as caught:
                split.cut(text)
            self.assertIn(name, str(caught.exception))

    def test_banners_out_of_order_are_refused_by_name(self):
        """The losslessness assertion would refuse this too, as "not the
        body"; the order check is what names the banner that moved."""
        a, b = split.CUTS[3][1], split.CUTS[4][1]
        text = one_file_helper().replace(a, "@@A@@").replace(b, a).replace("@@A@@", b)
        with self.assertRaises(split.SplitError) as caught:
            split.cut(text)
        self.assertIn("out of order", str(caught.exception))


class VerifyTest(unittest.TestCase):

    def test_verify_sees_a_byte_changed_in_a_part(self):
        tree = Tree(self).split()
        rel = "%s/06-failed.py" % helper_files.PART_DIR
        tree.write_file(rel, tree.read(rel).replace("06-failed", "06-faileD"))
        self.assertEqual(split.verify(tree.root, tree.text), ["%s differs from the cut" % rel])

    def test_verify_sees_a_byte_changed_in_the_stub(self):
        tree = Tree(self).split()
        tree.write_file(helper_files.STUB, tree.read(helper_files.STUB).replace('"""a helper"""', '"""a Helper"""'))
        self.assertEqual(split.verify(tree.root, tree.text), ["%s differs from the cut" % helper_files.STUB])

    def test_verify_sees_a_file_the_cut_does_not_make(self):
        tree = Tree(self).split()
        tree.write_file("%s/12-extra.py" % helper_files.PART_DIR, split.HEADER)
        self.assertTrue(any("12-extra.py" in p for p in split.verify(tree.root, tree.text)))


class CheckTest(unittest.TestCase):

    def problems(self, tree):
        return split.check(tree.root)

    def test_a_named_part_that_is_missing_is_red(self):
        tree = Tree(self).split()
        os.unlink(tree.part("09-cache.py"))
        self.assertTrue(any("09-cache.py" in p and "unreadable" in p for p in self.problems(tree)))

    def test_a_file_the_stub_does_not_name_is_red(self):
        tree = Tree(self).split()
        tree.write_file("%s/12-orphan.py" % helper_files.PART_DIR, split.HEADER)
        self.assertTrue(any("12-orphan.py" in p and "never run" in p for p in self.problems(tree)))

    def test_a_gitignored_bytecode_directory_is_not_a_stray(self):
        tree = Tree(self).split()
        os.makedirs(tree.part("__pycache__"))
        self.assertEqual(self.problems(tree), [])

    def test_a_part_without_the_generated_header_is_red(self):
        tree = Tree(self).split()
        rel = "%s/03-io-playlist.py" % helper_files.PART_DIR
        tree.write_file(rel, tree.read(rel)[len(split.HEADER):])
        self.assertTrue(any("03-io-playlist.py" in p and "header" in p for p in self.problems(tree)))

    def test_a_part_that_does_not_compile_is_red(self):
        tree = Tree(self).split()
        rel = "%s/07-player.py" % helper_files.PART_DIR
        tree.write_file(rel, tree.read(rel) + "def broken(:\n")
        self.assertTrue(any("07-player.py" in p and "compile" in p for p in self.problems(tree)))

    def test_a_hand_edited_loader_is_red(self):
        """The loader is the security-relevant text in the stub: fixed names,
        its own directory. An edit to it is red until it is regenerated."""
        tree = Tree(self).split()
        stub = tree.read(helper_files.STUB)
        tree.write_file(helper_files.STUB, stub.replace('here = os.path.join(', 'here = os.environ.get("X") or os.path.join(', 1))
        self.assertTrue(any("generated loader" in p for p in self.problems(tree)))

    def test_a_loader_moved_above_the_shield_is_red(self):
        tree = Tree(self).split()
        stub = tree.read(helper_files.STUB)
        block = split.loader_block([name for name, _ in split.CUTS])
        moved = stub.replace(block, "\n\n").replace("import sys\n", "import sys\n" + block, 1)
        tree.write_file(helper_files.STUB, moved)
        self.assertTrue(any("directly after the shield" in p for p in self.problems(tree)))

    def test_a_name_dropped_from_the_list_leaves_its_part_an_orphan_which_is_red(self):
        """The loader still matches its own (shorter) list, so the signal is
        the file nothing compiles any more."""
        tree = Tree(self).split()
        stub = tree.read(helper_files.STUB)
        tree.write_file(helper_files.STUB, stub.replace('    "02-sources.py",\n', '', 1))
        self.assertEqual(self.problems(tree), [
            "bin/helper holds what HELPER_PARTS does not name, which would never run: 02-sources.py"])

    def test_a_one_file_helper_is_not_the_split_helper(self):
        tree = Tree(self)
        self.assertTrue(any("assigns no HELPER_PARTS" in p for p in self.problems(tree)))


class HelperFilesTest(unittest.TestCase):
    """The one reader of HELPER_PARTS, which release.py and the tests use."""

    def test_it_reads_the_tuple_in_order_without_running_the_stub(self):
        stub = 'import sys\nsys.exit(3)\nHELPER_PARTS = ("02-b.py", "01-a.py")\n'
        self.assertEqual(helper_files.part_names(stub), ("02-b.py", "01-a.py"))

    def test_a_one_file_helper_has_no_parts(self):
        self.assertEqual(helper_files.part_names('def main():\n    return 0\n'), ())

    def test_what_it_refuses(self):
        for stub in ('HELPER_PARTS = tuple(["01-a.py"])\n',
                     'HELPER_PARTS = ("01-a.py", "01-a.py")\n',
                     'HELPER_PARTS = ("../../etc/passwd",)\n',
                     'HELPER_PARTS = ("01-a.py",)\nHELPER_PARTS = ("02-b.py",)\n',
                     'HELPER_PARTS = ()\n',
                     'HELPER_PARTS = (\n'):
            with self.assertRaises(helper_files.HelperLayoutError, msg=stub):
                helper_files.part_names(stub)

    def test_copy_keeps_the_layout_the_stub_resolves_its_parts_by(self):
        tree = Tree(self).split()
        dest = tempfile.mkdtemp(prefix="split-helper-copy-")
        self.addCleanup(shutil.rmtree, dest, True)
        helper_files.copy_helper(tree.root, dest, stub_name="omarchy-iptv.real")
        done = subprocess.run([sys.executable, os.path.join(dest, "bin", "omarchy-iptv.real")],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual((done.returncode, done.stderr), (0, ""))


class ThisTreeTest(unittest.TestCase):
    """This repository's helper, as the gate sees it."""

    def test_the_tree_checks_clean(self):
        self.assertEqual(split.check(str(ROOT)), [])

    def test_the_parts_are_the_owners_layout(self):
        """docs/HELPER-SPLIT.md, decided 2026-10-15: these eleven, in this
        order. A part added later changes this list and the doc together."""
        self.assertEqual(helper_files.part_names((ROOT / helper_files.STUB).read_text(encoding="utf-8")),
                         tuple(name for name, _ in split.CUTS))

    def test_the_helper_source_is_the_stub_then_every_part(self):
        source = helper_files.helper_source(str(ROOT))
        self.assertTrue(source.startswith((ROOT / helper_files.STUB).read_text(encoding="utf-8")))
        self.assertIn('sub.add_parser("logos"', source)
        self.assertNotIn('sub.add_parser("logos"', (ROOT / helper_files.STUB).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
