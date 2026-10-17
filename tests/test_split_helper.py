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
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zlib

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
        body = "".join(split.split_witness(n, tree.read("%s/%s" % (helper_files.PART_DIR, n)))[0][len(split.HEADER):]
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

    def test_a_part_whose_last_line_does_not_match_it_is_red(self):
        tree = Tree(self).split()
        rel = "%s/05-ipc-logos.py" % helper_files.PART_DIR
        text = tree.read(rel)
        tree.write_file(rel, text[:len(text) // 2])
        self.assertTrue(any("05-ipc-logos.py" in p and "last line" in p for p in self.problems(tree)))
        tree.write_file(rel, text.replace("def ", "def  ", 1))
        self.assertTrue(any("05-ipc-logos.py" in p and "last line" in p for p in self.problems(tree)))

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
        body, _ = split.split_witness("03-io-playlist.py", tree.read(rel))
        tree.write_file(rel, body + "def added() -> int:\n    return 3\n")
        self.assertTrue(split.check(tree.root))
        done = tree.run_script("--seal")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.splitlines()[0], "split-helper: sealed %s" % rel)
        self.assertEqual(split.check(tree.root), [])
        run = subprocess.run([sys.executable, tree.path(helper_files.STUB)],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual((run.returncode, run.stderr), (0, ""))

    def test_seal_replaces_a_stale_last_line_rather_than_stacking_one(self):
        tree = Tree(self).split()
        rel = "%s/08-player-verbs.py" % helper_files.PART_DIR
        text = tree.read(rel)
        tree.write_file(rel, text.replace("08-player-verbs.py\"", "08-player-verbz.py\"", 1))
        tree.run_script("--seal")
        self.assertEqual(tree.read(rel).count("# end of 08-player-verbs.py:"), 1)

    def test_seal_on_a_clean_tree_changes_nothing(self):
        tree = Tree(self).split()
        before = {n: tree.read("%s/%s" % (helper_files.PART_DIR, n)) for n, _ in split.CUTS}
        done = tree.run_script("--seal")
        self.assertEqual((done.returncode, done.stdout.count("sealed ")), (0, 0), done.stdout)
        self.assertEqual({n: tree.read("%s/%s" % (helper_files.PART_DIR, n)) for n, _ in split.CUTS}, before)

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


def copy_plugin(case):
    """A copy of this repository's helper as an install holds it (the stub,
    its parts, the manifest beside them), and an empty home to run it in."""
    top = tempfile.mkdtemp(prefix="split-helper-damage-")
    case.addCleanup(shutil.rmtree, top, True)
    plugin = os.path.join(top, "plugin")
    os.makedirs(os.path.join(plugin, "bin"))
    helper_files.copy_helper(str(ROOT), plugin)
    shutil.copy2(str(ROOT / "manifest.json"), plugin)
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


def damage_part(plugin, damage, part):
    """Apply one damage named in tests/fixtures/helper-damaged.json."""
    here = os.path.join(plugin, helper_files.PART_DIR)
    path = os.path.join(here, part)
    if damage == "extra-file":
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(split.HEADER)
        return
    if damage == "unlistable":
        os.chmod(here, 0o311)
        return
    with open(path, "rb") as fh:
        data = fh.read()
    above = data[:data.rfind(b"\n", 0, len(data) - 1) + 1]
    header = len(split.HEADER.encode())

    def resealed(body):
        return body + (split.WITNESS % (part, len(body), zlib.crc32(body))).encode()

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
    middle = len(data) // 2
    while data[middle - 1:middle] == b"\n":
        middle += 1
    out = {
        "empty": lambda: b"",
        "truncated-at-a-line": lambda: data[:data.rfind(b"\n", 0, len(data) // 2) + 1],
        "truncated-mid-line": lambda: data[:middle],
        "syntax-error": lambda: data[:header] + b"def broken(:\n" + data[header:],
        "syntax-error-resealed": lambda: resealed(above[:header] + b"def broken(:\n" + above[header:]),
        "nul-byte": lambda: data[:header] + b"\0" + data[header:],
        "nul-byte-resealed": lambda: resealed(above[:header] + b"#\0\n" + above[header:]),
        "not-utf8-resealed": lambda: resealed(above[:header] + b"# \xff\n" + above[header:]),
        # The right shape, the right name and checksum, a length one short.
        "wrong-last-line": lambda: above + (split.WITNESS % (part, len(above) - 1, zlib.crc32(above))).encode(),
    }[damage]()
    with open(path, "wb") as fh:
        fh.write(out)


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
        return subprocess.run(["/usr/bin/env", "-i", "HOME=" + home, "PATH=/usr/bin:/bin", sys.executable, "-I",
                               os.path.join(plugin, helper_files.STUB)] + argv,
                              capture_output=True, timeout=60, cwd=home)

    def test_an_intact_copy_writes_so_the_probe_can_see_a_write(self):
        plugin, home = copy_plugin(self)
        for verb in self.VERBS:
            done = self.run_helper(plugin, home, verb(home))
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertNotEqual(tree_listing(home), [])

    def test_every_damage_is_refused_before_anything_runs_or_writes(self):
        if os.geteuid() == 0:
            self.skipTest("root reads a mode-0 file")
        self.assertEqual(len(FIXTURE["refusals"]), 16)
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
