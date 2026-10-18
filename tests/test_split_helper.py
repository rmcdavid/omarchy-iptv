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
import ast
import importlib.machinery
import importlib.util
import json
import os
import pathlib
import re
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
        self.assertEqual(split.verify(tree.root, tree.text), ["%s differs from the cut (from line 7)" % rel])

    def test_verify_sees_a_byte_changed_in_the_stub(self):
        tree = Tree(self).split()
        tree.write_file(helper_files.STUB, tree.read(helper_files.STUB).replace('"""a helper"""', '"""a Helper"""'))
        self.assertEqual(split.verify(tree.root, tree.text), ["%s differs from the cut (in its head)" % helper_files.STUB])

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
        self.assertTrue(any("12-orphan.py" in p and "refuses" in p for p in self.problems(tree)))

    def test_a_bytecode_directory_is_a_stray_because_the_stub_refuses_it(self):
        """It used to be exempt here as "gitignored, never ships". The stub
        now refuses ANY entry its list does not name, so a gate that let one
        through would be greener than the helper it judges (rule 10)."""
        tree = Tree(self).split()
        os.makedirs(tree.part("__pycache__"))
        self.assertTrue(any("__pycache__" in p for p in self.problems(tree)))
        done = subprocess.run([sys.executable, tree.path(helper_files.STUB)],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 1)
        self.assertIn("bin/helper/__pycache__ is not one of this helper's parts", done.stderr)

    def test_a_part_that_does_not_match_its_entry_is_red(self):
        """Cut off, or edited without --seal: the stub would refuse it, so
        the gate does (rule 10)."""
        tree = Tree(self).split()
        rel = "%s/05-ipc-logos.py" % helper_files.PART_DIR
        text = tree.read(rel)
        tree.write_file(rel, text[:len(text) // 2])
        self.assertTrue(any("05-ipc-logos.py" in p and "does not match its entry" in p for p in self.problems(tree)))
        tree.write_file(rel, text.replace("def ", "def  ", 1))
        self.assertTrue(any("05-ipc-logos.py" in p and "does not match its entry" in p for p in self.problems(tree)))

    def test_a_crlf_part_matches_its_entry_as_the_stub_reads_it(self):
        """P1 of the follow-up: core.autocrlf=true checks every part out with
        CRLF; the entry is over the text with CRLF read as LF, in the gate as
        in the stub, so such a part is the part."""
        tree = Tree(self).split()
        path = tree.part("05-ipc-logos.py")
        with open(path, "rb") as fh:
            data = fh.read()
        with open(path, "wb") as fh:
            fh.write(data.replace(b"\n", b"\r\n"))
        self.assertEqual(self.problems(tree), [])

    def test_a_name_starting_with_a_dot_is_not_a_stray_and_the_stub_ignores_it_too(self):
        """P2c: an editor's swap file beside a part being edited is not a part,
        and refusing it stopped the dev tree's helper while vim was open. The
        gate and the stub exempt the same names, and nothing else."""
        tree = Tree(self).split()
        tree.write_file("%s/.05-ipc-logos.py.swp" % helper_files.PART_DIR, "\0vim swap\n")
        self.assertEqual(self.problems(tree), [])
        done = subprocess.run([sys.executable, tree.path(helper_files.STUB)],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        tree.write_file("%s/05-ipc-logos.py.swp" % helper_files.PART_DIR, "x\n")
        self.assertTrue(any("05-ipc-logos.py.swp" in p for p in self.problems(tree)))

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
        block = split.loader_block(helper_files.part_records(stub))
        moved = stub.replace(block, "\n\n").replace("import sys\n", "import sys\n" + block, 1)
        tree.write_file(helper_files.STUB, moved)
        self.assertTrue(any("directly after the shield" in p for p in self.problems(tree)))

    def test_a_name_dropped_from_the_list_leaves_its_part_an_orphan_which_is_red(self):
        """The loader still matches its own (shorter) list, so the signal is
        the file nothing compiles any more."""
        tree = Tree(self).split()
        stub = tree.read(helper_files.STUB)
        tree.write_file(helper_files.STUB, re.sub(r'    \("02-sources\.py", [0-9]+, 0x[0-9a-f]{8}\),\n', '', stub, count=1))
        self.assertEqual(self.problems(tree), [
            "bin/helper holds what HELPER_PARTS does not name, which the helper refuses to start "
            "beside: 02-sources.py"])

    def test_a_one_file_helper_is_not_the_split_helper(self):
        tree = Tree(self)
        self.assertTrue(any("assigns no HELPER_PARTS" in p for p in self.problems(tree)))


class SealTest(unittest.TestCase):
    """--seal: the tool for an ordinary edit to a part, after which --check
    is green again. The parts are cut once and then edited as code."""

    def test_an_edit_then_seal_checks_clean_and_runs(self):
        tree = Tree(self).split()
        rel = "%s/03-io-playlist.py" % helper_files.PART_DIR
        stub = tree.read(helper_files.STUB)
        tree.write_file(rel, tree.read(rel) + "def added() -> int:\n    return 3\n")
        self.assertTrue(split.check(tree.root))
        done = tree.run_script("--seal")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.splitlines()[0], "split-helper: sealed %s" % helper_files.STUB)
        self.assertEqual(split.check(tree.root), [])
        before = dict((e[0], e) for e in helper_files.part_records(stub))
        after = dict((e[0], e) for e in helper_files.part_records(tree.read(helper_files.STUB)))
        self.assertEqual([n for n in after if after[n] != before[n]], ["03-io-playlist.py"],
                         "an edit to one part changes that part's entry and no other")
        run = subprocess.run([sys.executable, tree.path(helper_files.STUB)],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual((run.returncode, run.stderr), (0, ""))

    def test_seal_removes_the_last_line_lane_split_f1_wrote(self):
        """Every part ended in a generated last line at lane-split-f1 (never
        shipped); the stub's entry replaces it, and --seal removes it."""
        tree = Tree(self).split()
        rel = "%s/08-player-verbs.py" % helper_files.PART_DIR
        text = tree.read(rel)
        tree.write_file(rel, text + "# end of 08-player-verbs.py: %d bytes above, crc32 0badf00d\n" % len(text))
        done = tree.run_script("--seal")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(tree.read(rel), text)

    def test_seal_on_a_clean_tree_changes_nothing(self):
        tree = Tree(self).split()
        rels = [helper_files.STUB] + ["%s/%s" % (helper_files.PART_DIR, n) for n, _ in split.CUTS]
        before = {rel: tree.read(rel) for rel in rels}
        done = tree.run_script("--seal")
        self.assertEqual((done.returncode, done.stdout.count("sealed ")), (0, 0), done.stdout)
        self.assertEqual({rel: tree.read(rel) for rel in rels}, before)

    def test_seal_regenerates_a_hand_edited_loader(self):
        tree = Tree(self).split()
        stub = tree.read(helper_files.STUB)
        tree.write_file(helper_files.STUB, stub.replace('"helper")', 'os.environ.get("X", "helper"))', 1))
        self.assertTrue(any("generated loader" in p for p in split.check(tree.root)))
        tree.run_script("--seal")
        self.assertEqual(tree.read(helper_files.STUB), stub)

    def test_verify_names_the_region_of_the_stub_that_differs(self):
        tree = Tree(self).split()
        tree.write_file(helper_files.STUB, tree.read(helper_files.STUB).replace('"""a helper"""', '"""edited"""'))
        self.assertEqual(split.verify(tree.root, tree.text),
                         ["%s differs from the cut (in its head)" % helper_files.STUB])


class HelperFilesTest(unittest.TestCase):
    """The one reader of HELPER_PARTS, which release.py and the tests use."""

    def test_it_reads_the_tuple_in_order_without_running_the_stub(self):
        stub = 'import sys\nsys.exit(3)\nHELPER_PARTS = (("02-b.py", 9, 0x0000000a), ("01-a.py", 1, 0xffffffff))\n'
        self.assertEqual(helper_files.part_names(stub), ("02-b.py", "01-a.py"))
        self.assertEqual(helper_files.part_records(stub), (("02-b.py", 9, 10), ("01-a.py", 1, 0xFFFFFFFF)))

    def test_a_one_file_helper_has_no_parts(self):
        self.assertEqual(helper_files.part_names('def main():\n    return 0\n'), ())

    def test_what_it_refuses(self):
        for stub in ('HELPER_PARTS = tuple([("01-a.py", 1, 0)])\n',
                     'HELPER_PARTS = (("01-a.py", 1, 0), ("01-a.py", 2, 0))\n',
                     'HELPER_PARTS = (("../../etc/passwd", 1, 0),)\n',
                     'HELPER_PARTS = (("01-a.py", 1, 0),)\nHELPER_PARTS = (("02-b.py", 1, 0),)\n',
                     'HELPER_PARTS = ()\n',
                     'HELPER_PARTS = (\n',
                     # the names-only shape of lane-split-f1: no entry to check
                     'HELPER_PARTS = ("01-a.py",)\n',
                     'HELPER_PARTS = (("01-a.py", 0, 0),)\n',
                     'HELPER_PARTS = (("01-a.py", 1, -1),)\n',
                     'HELPER_PARTS = (("01-a.py", 1, 0x100000000),)\n',
                     'HELPER_PARTS = (("01-a.py", True, 0),)\n',
                     'HELPER_PARTS = (("01-a.py", 1),)\n'):
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


FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "helper-damaged.json").read_text(encoding="utf-8"))


def marked_helper():
    """The synthetic helper with a SIDE EFFECT at the top level of its first
    part: it creates the file $SPLIT_MARK names. Every part is compiled into
    one namespace in order, so if the stub ran a part before it had checked
    them all, the mark would exist after a refusal over a LATER part."""
    return one_file_helper().replace(
        "import os\n",
        "import os\nif os.environ.get('SPLIT_MARK'):\n    open(os.environ['SPLIT_MARK'], 'w').close()\n", 1)


class NothingRunsBeforeEveryPartIsCheckedTest(unittest.TestCase):
    """P2 of the split's reviews: `_load_parts` used to compile and run each
    part as it read it, so with a damaged later part the earlier ones had
    already run -- and an EMPTY part compiled to nothing and let the verbs
    run without it. Now every part is read and checked, then all run."""

    def run_marked(self, tree, mark):
        env = dict(os.environ, SPLIT_MARK=mark)
        return subprocess.run([sys.executable, tree.path(helper_files.STUB)],
                              capture_output=True, text=True, timeout=30, env=env)

    def test_the_mark_is_made_by_an_intact_helper(self):
        tree = Tree(self, marked_helper()).split()
        mark = tree.path("mark")
        done = self.run_marked(tree, mark)
        self.assertEqual((done.returncode, done.stderr, os.path.exists(mark)), (0, "", True))

    def test_a_damaged_last_part_stops_the_first_part_running(self):
        for damage in ("empty", "cut"):
            tree = Tree(self, marked_helper()).split()
            last = tree.part(split.CUTS[-1][0])
            with open(last, "rb") as fh:
                data = fh.read()
            with open(last, "wb") as fh:
                fh.write(b"" if damage == "empty" else data[:len(data) // 2])
            mark = tree.path("mark")
            done = self.run_marked(tree, mark)
            self.assertEqual(done.returncode, 1, damage)
            self.assertFalse(os.path.exists(mark), "%s: a part ran before the damaged one was refused" % damage)
            self.assertEqual(json.loads(done.stdout)["error"]["code"], "helper_damaged", damage)


def as_committed(top):
    """Every file under `top` with CRLF read as LF: the bytes main's blobs
    hold, whatever line endings the checkout these tests run in was given
    (a core.autocrlf checkout of dev writes CRLF, and a damage or a blob
    built from those bytes would not be the one an install receives)."""
    for base, _, files in os.walk(top):
        for name in files:
            path = os.path.join(base, name)
            with open(path, "rb") as fh:
                data = fh.read()
            if b"\r\n" in data:
                with open(path, "wb") as fh:
                    fh.write(data.replace(b"\r\n", b"\n"))


def copy_plugin(case):
    """A copy of this repository's helper as an install holds it (the stub,
    its parts, the manifest beside them), and an empty home to run it in."""
    top = tempfile.mkdtemp(prefix="split-helper-damage-")
    case.addCleanup(shutil.rmtree, top, True)
    plugin = os.path.join(top, "plugin")
    os.makedirs(os.path.join(plugin, "bin"))
    helper_files.copy_helper(str(ROOT), plugin)
    shutil.copy2(str(ROOT / "manifest.json"), plugin)
    as_committed(plugin)
    home = os.path.join(top, "home")
    os.makedirs(home)
    return plugin, home


def tree_listing(top):
    out = []
    for base, dirs, files in os.walk(top):
        for name in dirs + files:
            path = os.path.join(base, name)
            out.append((os.path.relpath(path, top), os.lstat(path).st_mode))
    return sorted(out)


def reseal(plugin):
    """Rewrite the stub's entries for the parts as they now are, the way
    --seal does after an edit, on a copy of the plugin."""
    split.seal(plugin)


def damage_part(plugin, damage, part):
    """Apply one damage named in tests/fixtures/helper-damaged.json."""
    here = os.path.join(plugin, helper_files.PART_DIR)
    path = os.path.join(here, part)
    if damage == "extra-file":
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(split.HEADER)
        return
    if damage == "extra-directory":
        os.mkdir(path)
        return
    if damage == "unlistable":
        os.chmod(here, 0o311)
        return
    if damage == "entry-length-one-short":
        stub = os.path.join(plugin, helper_files.STUB)
        with open(stub, encoding="utf-8") as fh:
            text = fh.read()
        text, n = re.subn(r'\("%s", ([0-9]+),' % re.escape(part),
                          lambda m: '("%s", %d,' % (part, int(m.group(1)) - 1), text)
        assert n == 1, "the stub has no entry for %s" % part
        with open(stub, "w", encoding="utf-8") as fh:
            fh.write(text)
        return
    with open(path, "rb") as fh:
        data = fh.read()
    header = len(split.HEADER.encode())
    if damage == "missing":
        os.unlink(path)
        return
    if damage == "unreadable":
        os.chmod(path, 0)
        return
    if damage == "directory":
        os.unlink(path)
        os.mkdir(path)
        return
    if damage == "fifo":
        os.unlink(path)
        os.mkfifo(path)
        return
    middle = len(data) // 2
    while data[middle - 1:middle] == b"\n":
        middle += 1
    out = {
        "empty": lambda: b"",
        "truncated-at-a-line": lambda: data[:data.rfind(b"\n", 0, len(data) // 2) + 1],
        "truncated-mid-line": lambda: data[:middle],
        "syntax-error": lambda: data[:header] + b"def broken(:\n" + data[header:],
        "syntax-error-resealed": lambda: data[:header] + b"def broken(:\n" + data[header:],
        "nul-byte": lambda: data[:header] + b"\0" + data[header:],
        "nul-byte-resealed": lambda: data[:header] + b"#\0\n" + data[header:],
        "not-utf8-resealed": lambda: data[:header] + b"# \xff\n" + data[header:],
        # Whole and valid, as the next release's copy of the part would be.
        "another-release": lambda: data + b"# a later release\n",
    }[damage]()
    with open(path, "wb") as fh:
        fh.write(out)
    if damage.endswith("-resealed"):
        reseal(plugin)


def restore_modes(plugin):
    for base, dirs, files in os.walk(plugin):
        for name in dirs:
            os.chmod(os.path.join(base, name), 0o755)
    here = os.path.join(plugin, helper_files.PART_DIR)
    os.chmod(here, 0o755)
    for name in os.listdir(here):
        path = os.path.join(here, name)
        if os.path.isfile(path):
            os.chmod(path, 0o644)


class DamagedPartMatrixTest(unittest.TestCase):
    """P2 and P3a, on this repository's real helper: every damage in the
    shared fixture is refused before ANY part runs or writes, with exactly the
    fixture's JSON object on stdout, its message as the one stderr line, and
    exit status 1. Three verbs that write -- the ones the review measured
    running without an empty 05 -- each leave the home exactly as it was.
    Run the way the shell runs it, isolated (`python3 -I`, `env -i`)."""

    VERBS = (lambda home: ["state", "--state-dir", os.path.join(home, "state"), "init"],
             lambda home: ["cache", "--cache-dir", os.path.join(home, "cache"), "prune"],
             lambda home: ["failed", "mark", "--id", "t:x", "--cache-dir", os.path.join(home, "cache")])

    def run_helper(self, plugin, home, argv):
        # A short timeout: a FIFO in a part's place used to block the
        # loader in open() until something wrote to it (P2b).
        return subprocess.run(["/usr/bin/env", "-i", "HOME=" + home, "PATH=/usr/bin:/bin", sys.executable, "-I",
                               os.path.join(plugin, helper_files.STUB)] + argv,
                              capture_output=True, timeout=20, cwd=home)

    def test_an_intact_copy_writes_so_the_probe_can_see_a_write(self):
        plugin, home = copy_plugin(self)
        for verb in self.VERBS:
            done = self.run_helper(plugin, home, verb(home))
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotEqual(tree_listing(home), [])

    def test_every_damage_is_refused_before_anything_runs_or_writes(self):
        if os.geteuid() == 0:
            self.skipTest("root reads a mode-0 file")
        self.assertEqual(len(FIXTURE["refusals"]), 18)
        for case in FIXTURE["refusals"]:
            with self.subTest(damage=case["damage"], part=case["part"]):
                plugin, home = copy_plugin(self)
                damage_part(plugin, case["damage"], case["part"])
                self.addCleanup(restore_modes, plugin)
                plugin_before = tree_listing(plugin)
                want_out = (json.dumps(case["reply"]) + "\n").encode()
                want_err = ("omarchy-iptv: %s\n" % case["reply"]["error"]["message"]).encode()
                for verb in self.VERBS:
                    done = self.run_helper(plugin, home, verb(home))
                    self.assertEqual((done.returncode, done.stdout, done.stderr), (1, want_out, want_err))
                self.assertEqual(tree_listing(home), [], "a verb wrote before the refusal")
                self.assertEqual(tree_listing(plugin), plugin_before, "the run wrote into the plugin")

    def test_a_name_starting_with_a_dot_is_ignored_and_the_verbs_run(self):
        """P2c, on the real helper: an editor's swap or lock file beside the
        parts is not refused; the verbs run and write as an intact copy's do."""
        self.assertEqual(len(FIXTURE["ignored"]), 2)
        for case in FIXTURE["ignored"]:
            with self.subTest(part=case["part"]):
                plugin, home = copy_plugin(self)
                damage_part(plugin, case["damage"], case["part"])
                for verb in self.VERBS:
                    done = self.run_helper(plugin, home, verb(home))
                    self.assertEqual((done.returncode, done.stderr), (0, b""), case["part"])
                    self.assertTrue(json.loads(done.stdout)["ok"])


class SymlinkedStubTest(unittest.TestCase):
    """P3b: the stub finds its parts through realpath(__file__), so a symlink
    to bin/omarchy-iptv placed elsewhere runs as the one-file helper did, and
    a symlinked plugin directory keeps working."""

    def test_a_symlink_to_the_stub_elsewhere_runs(self):
        plugin, home = copy_plugin(self)
        os.makedirs(os.path.join(home, "bin"))
        link = os.path.join(home, "bin", "omarchy-iptv")
        os.symlink(os.path.join(plugin, helper_files.STUB), link)
        done = subprocess.run(["/usr/bin/env", "-i", "HOME=" + home, "PATH=/usr/bin:/bin", sys.executable, "-I",
                               link, "state", "--state-dir", os.path.join(home, "state"), "init"],
                              capture_output=True, text=True, timeout=60, cwd=home)
        self.assertEqual((done.returncode, done.stderr), (0, ""))
        self.assertTrue(json.loads(done.stdout)["ok"])

    def test_a_symlinked_plugin_directory_runs_and_reads_its_manifest(self):
        plugin, home = copy_plugin(self)
        link = os.path.join(home, "plugin-link")
        os.symlink(plugin, link)
        done = subprocess.run(["/usr/bin/env", "-i", "HOME=" + home, "PATH=/usr/bin:/bin", sys.executable, "-I",
                               os.path.join(link, helper_files.STUB), "--version"],
                              capture_output=True, text=True, timeout=60, cwd=home)
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((done.returncode, done.stdout.strip(), done.stderr), (0, manifest["version"], ""))


class SymlinkedStubVersionTest(unittest.TestCase):
    """P3s of the follow-up: `_manifest_version` resolves the manifest
    through realpath, as the loader resolves the parts, so --version through
    a symlink to the stub placed elsewhere prints the plugin's version (it
    printed 0.0.0+unknown, as the one-file helper did, while the verbs ran)."""

    def test_version_through_a_symlink_to_the_stub_elsewhere(self):
        plugin, home = copy_plugin(self)
        os.makedirs(os.path.join(home, "bin"))
        link = os.path.join(home, "bin", "omarchy-iptv")
        os.symlink(os.path.join(plugin, helper_files.STUB), link)
        done = subprocess.run(["/usr/bin/env", "-i", "HOME=" + home, "PATH=/usr/bin:/bin", sys.executable, "-I",
                               link, "--version"], capture_output=True, text=True, timeout=60, cwd=home)
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((done.returncode, done.stdout.strip(), done.stderr), (0, manifest["version"], ""))


def run_isolated(plugin, home, argv, timeout=60):
    return subprocess.run(["/usr/bin/env", "-i", "HOME=" + home, "PATH=/usr/bin:/bin", sys.executable, "-I",
                           os.path.join(plugin, helper_files.STUB)] + argv,
                          capture_output=True, timeout=timeout, cwd=home)


def writing_verbs(home):
    return (["state", "--state-dir", os.path.join(home, "state"), "init"],
            ["failed", "mark", "--id", "t:x", "--cache-dir", os.path.join(home, "cache", "sources", "k")],
            ["cache", "--cache-dir", os.path.join(home, "cache"), "prune"])


def move_definition(plugin, name, src, dst):
    """Release B of a pair: `def name` moves from part `src` to the end of
    part `dst`, and the stub is resealed. Every name still resolves at call
    time, so B whole runs exactly as A whole does."""
    here = os.path.join(plugin, helper_files.PART_DIR)
    with open(os.path.join(here, src), encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"^def %s\(.*?(?=^\S)" % re.escape(name), text, re.M | re.S)
    assert m, "no def %s in %s" % (name, src)
    with open(os.path.join(here, src), "w", encoding="utf-8") as fh:
        fh.write(text[:m.start()] + text[m.end():])
    with open(os.path.join(here, dst), "a", encoding="utf-8") as fh:
        fh.write("\n\n" + m.group(0).rstrip("\n") + "\n")
    reseal(plugin)


class MixedReleaseTest(unittest.TestCase):
    """P2a of the follow-up. An update rewrites the parts one after another
    and the stub after them, so a helper spawned in between used to meet
    whole parts of two releases: with `write_json_atomic` moved from
    03-io-playlist.py to 09-cache.py in the next release, `failed mark`
    created its cache directories and then died on a NameError traceback
    (the robust lens, measured). The stub's entries now name each part's
    length and CRC-32, so a part of another release is refused before any
    part runs, in either direction."""

    def pair(self):
        old, home = copy_plugin(self)
        new = os.path.join(os.path.dirname(old), "next")
        shutil.copytree(old, new, symlinks=True)
        move_definition(new, "write_json_atomic", "03-io-playlist.py", "09-cache.py")
        return old, new, home

    def test_each_release_whole_runs_the_writing_verbs(self):
        old, new, home = self.pair()
        for plugin in (old, new):
            for argv in writing_verbs(home):
                done = run_isolated(plugin, home, argv)
                self.assertEqual((done.returncode, done.stderr), (0, b""), (plugin, argv))
            shutil.rmtree(home)
            os.makedirs(home)

    def test_a_part_of_the_next_release_beside_this_stub_is_refused_and_nothing_is_written(self):
        old, new, home = self.pair()
        here = helper_files.PART_DIR
        cases = (
            # git's order: 03 of the next release is written while this stub
            # and this 09 are in place -- the state the robust lens measured.
            ("next 03 under this stub", old, new, "03-io-playlist.py"),
            # and the other way round, which a parallel checkout could make
            ("this 03 under the next stub", new, old, "03-io-playlist.py"),
            ("next 09 under this stub", old, new, "09-cache.py"),
        )
        for label, into, frm, part in cases:
            with self.subTest(label):
                mixed = os.path.join(os.path.dirname(old), "mixed")
                shutil.rmtree(mixed, True)
                shutil.copytree(into, mixed, symlinks=True)
                shutil.copy2(os.path.join(frm, here, part), os.path.join(mixed, here, part))
                for argv in writing_verbs(home):
                    done = run_isolated(mixed, home, argv)
                    self.assertEqual(done.returncode, 1, (label, argv, done.stderr))
                    reply = json.loads(done.stdout)
                    self.assertEqual((reply["error"]["code"], reply["part"]), ("helper_damaged", part))
                    self.assertNotIn(b"Traceback", done.stderr)
                self.assertEqual(tree_listing(home), [], "%s: a verb wrote before the refusal" % label)


def file_states(old_path, new_path):
    """What a reader can meet at one file while git rewrites it in place
    (measured with inotify: DELETE, CREATE, the writes, CLOSE_WRITE; no
    temporary file, no rename): -> [(label, bytes or None for missing)]."""
    with open(new_path, "rb") as fh:
        data = fh.read()
    return [("missing", None), ("empty", b""), ("half written", data[:len(data) // 2]),
            ("written", data)]


def put(path, data):
    if os.path.lexists(path):
        os.unlink(path)
    if data is not None:
        with open(path, "wb") as fh:
            fh.write(data)


class UpdateWindowTest(unittest.TestCase):
    """What a spawn can meet at each step of an in-place update, emulated in
    the order git was measured to write (docs/HELPER-SPLIT.md on the dev
    branch): the changed parts in index order, then the stub. Every state is
    either a whole release, which runs, or one that writes nothing: a part
    step is refused with the helper_damaged reply, and a stub step (missing,
    empty, half written) runs no verb at all, because the verb is the stub's
    last statement and the parts are compiled only by a whole loader."""

    def test_every_step_of_an_update_runs_a_whole_release_or_writes_nothing(self):
        old, home = copy_plugin(self)
        new = os.path.join(os.path.dirname(old), "next")
        shutil.copytree(old, new, symlinks=True)
        move_definition(new, "write_json_atomic", "03-io-playlist.py", "09-cache.py")
        live = os.path.join(os.path.dirname(old), "live")
        shutil.copytree(old, live, symlinks=True)
        order = ["%s/03-io-playlist.py" % helper_files.PART_DIR, "%s/09-cache.py" % helper_files.PART_DIR,
                 helper_files.STUB]
        seen = []
        for rel in order:
            for label, data in file_states(os.path.join(old, rel), os.path.join(new, rel)):
                put(os.path.join(live, rel), data)
                whole = rel == helper_files.STUB and label == "written"
                for argv in writing_verbs(home):
                    done = run_isolated(live, home, argv)
                    if whole:
                        self.assertEqual((done.returncode, done.stderr), (0, b""), (rel, label, argv))
                        continue
                    self.assertEqual(tree_listing(home), [], "%s %s: %s wrote" % (rel, label, argv[0]))
                    if rel == helper_files.STUB:
                        self.assertEqual(done.stdout, b"", (rel, label))
                    else:
                        self.assertEqual((done.returncode, json.loads(done.stdout)["error"]["code"]),
                                         (1, "helper_damaged"), (rel, label))
                seen.append((rel, label))
                if not whole:
                    shutil.rmtree(home)
                    os.makedirs(home)
        self.assertEqual(len(seen), 12)

    def test_no_prefix_of_the_stub_runs_a_verb_or_loads_a_part(self):
        """The stub is written in place too, so a spawn can compile any prefix
        of it. Of every byte prefix that compiles, none calls `main`, and none
        calls `_load_parts` unless it holds the whole loader."""
        text = (ROOT / helper_files.STUB).read_text(encoding="utf-8")
        full = ast.parse(text)
        loader = [ast.dump(n) for n in full.body
                  if isinstance(n, ast.FunctionDef) and n.name == "_load_parts"]
        parts = [ast.dump(n) for n in full.body
                 if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "HELPER_PARTS" for t in n.targets)]
        self.assertEqual((len(loader), len(parts)), (1, 1))
        last = text.rstrip("\n").rfind("\n") + 1      # the verb's own line
        compiled = 0
        for end in range(len(text)):
            try:
                tree = ast.parse(text[:end])
            except SyntaxError:
                continue
            compiled += 1
            calls = [n.func.id for n in ast.walk(tree)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
            if end < last:
                self.assertNotIn("main", calls, "a prefix of %d bytes runs a verb" % end)
            if "_load_parts" in calls:
                self.assertIn(loader[0], [ast.dump(n) for n in tree.body], end)
                self.assertIn(parts[0], [ast.dump(n) for n in tree.body], end)
        self.assertGreater(compiled, 100)


def git_env(home):
    """git as `omarchy plugin add` and `omarchy-plugin-update` run it, but
    under a scratch HOME whose .gitconfig is the only configuration read."""
    return {"HOME": home, "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GIT_CONFIG_NOSYSTEM": "1",
            "XDG_CONFIG_HOME": os.path.join(home, ".config"), "LANG": "C"}


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class CrlfCheckoutTest(unittest.TestCase):
    """P1 of the follow-up's review. `omarchy plugin add` is a plain `git
    clone` and `omarchy-plugin-update` a `git fetch` and `git merge --ff-only`;
    both honour a user's core.autocrlf=true, main ships no .gitattributes, and
    so every part arrives with CRLF. The stub must read that as the part it
    is: every verb refused on it while 0.14.2 ran, and reinstalling cloned the
    same thing again. Cloned for real, from a scratch upstream holding this
    tree's helper, for an add and for a fast-forward update."""

    def git(self, cwd, env, *args):
        done = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True,
                              env=env, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def assert_verbs_run(self, plugin, home, label):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        done = run_isolated(plugin, home, ["--version"])
        self.assertEqual((done.returncode, done.stdout.strip().decode(), done.stderr), (0, manifest["version"], b""),
                         label)
        for argv in writing_verbs(home):
            done = run_isolated(plugin, home, argv)
            self.assertEqual((done.returncode, done.stderr), (0, b""), (label, argv))
            self.assertTrue(json.loads(done.stdout)["ok"], (label, argv))

    def test_an_add_and_an_update_under_core_autocrlf_true_run_every_verb(self):
        top = tempfile.mkdtemp(prefix="split-helper-crlf-")
        self.addCleanup(shutil.rmtree, top, True)
        home = os.path.join(top, "home")
        run_home = os.path.join(top, "run")
        os.makedirs(home)
        os.makedirs(run_home)
        with open(os.path.join(home, ".gitconfig"), "w", encoding="utf-8") as fh:
            fh.write("[core]\n\tautocrlf = true\n[user]\n\tname = t\n\temail = t@example.invalid\n"
                     "[init]\n\tdefaultBranch = main\n")
        env = git_env(home)
        upstream = os.path.join(top, "upstream")
        os.makedirs(os.path.join(upstream, "bin"))
        helper_files.copy_helper(str(ROOT), upstream)
        shutil.copy2(str(ROOT / "manifest.json"), upstream)
        as_committed(upstream)
        # The upstream's blobs are this tree's text, LF, as main's are.
        self.git(upstream, env, "-c", "core.autocrlf=false", "init", "-q")
        self.git(upstream, env, "-c", "core.autocrlf=false", "add", "-A")
        self.git(upstream, env, "-c", "core.autocrlf=false", "commit", "-q", "-m", "this release")

        plugin = os.path.join(top, "plugin")
        self.git(top, env, "clone", "-q", "--", upstream, plugin)
        part = os.path.join(plugin, helper_files.PART_DIR, "06-failed.py")
        with open(part, "rb") as fh:
            self.assertIn(b"\r\n", fh.read(), "the clone is not CRLF, so this case proves nothing")
        self.assert_verbs_run(plugin, run_home, "after add")
        shutil.rmtree(run_home)
        os.makedirs(run_home)

        # The next release changes one part, sealed as the dev tree seals it.
        with open(os.path.join(upstream, helper_files.PART_DIR, "06-failed.py"), "a", encoding="utf-8") as fh:
            fh.write("# the next release\n")
        reseal(upstream)
        self.git(upstream, env, "-c", "core.autocrlf=false", "commit", "-q", "-am", "next release")
        self.git(plugin, env, "fetch", "--quiet", "origin", "HEAD")
        self.git(plugin, env, "merge", "--ff-only", "FETCH_HEAD")
        with open(part, "rb") as fh:
            self.assertTrue(fh.read().endswith(b"# the next release\r\n"), "the update did not arrive as CRLF")
        self.assert_verbs_run(plugin, run_home, "after update")
        self.assertEqual(self.git(plugin, env, "status", "--porcelain", "--ignored"), "",
                         "a verb wrote into the plugin")


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
