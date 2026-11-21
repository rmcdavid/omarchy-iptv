"""D-STATE-9 (2026-11-21): a state.json link that the FileView's writer reads
as TEXT to a different file than the kernel reads it.

The service writes state.json through Quickshell's FileView with atomicWrites,
which is Qt's QSaveFile, and QSaveFile resolves a link at the path by its
literal text: each hop's target joined to the previous hop's folder AS TEXT
and cleaned with QDir::cleanPath, which resolves no link. The kernel -- and so
the FileView's read, the helper and every other program -- resolves the same
link through the folders as they really are. Where a `..` climbs out of a
folder that is itself a link, the two name different files, and the save
lands where nothing reads it back (measured: scripts/dev-harness/spikes/
state-literal-link, docs/QA-RESULTS.md "D-STATE-9"). The guard: `state
private` and `state init` refuse such a link by name (`split-link`), comparing
the two answers as FILES, never as strings, because two strings for one file
is the common, supported case (a link in a linked state folder, an absolute
target through ~/Sync -> /mnt/data/Sync).

Every layout is built in a 0700 scratch folder (tempfile, under the suite's
TMPDIR), and every assertion reads the filesystem, never the code. The Qt
half is held by tests/fixtures/qt-clean-path.json, QDir::cleanPath's own
answers written by the spike's probe; the model half runs Model.mjs in node.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import subprocess
import tempfile
import unittest

from test_state import run, v2
from helper_loader import load_helper

helper = load_helper()
ROOT = pathlib.Path(__file__).resolve().parent.parent
CLEAN_FIXTURE = ROOT / "tests" / "fixtures" / "qt-clean-path.json"
SPLIT_SENTENCE = ("state.json is a symbolic link that the shell would save to a different file than the one it "
                  "reads (its target climbs with .. out of a folder that is itself a symbolic link); nothing may "
                  "be written to it")


class QtCleanPathTest(unittest.TestCase):
    """The helper's qt_clean_path against QDir::cleanPath's own answers."""

    def test_every_pair_the_installed_qt_answered_is_reproduced(self):
        document = json.loads(CLEAN_FIXTURE.read_text(encoding="utf-8"))
        self.assertGreater(len(document["pairs"]), 400)
        wrong = [(given, want, helper.qt_clean_path(given)) for given, want in document["pairs"]
                 if helper.qt_clean_path(given) != want]
        self.assertEqual(wrong, [])

    def test_the_corners_that_are_not_normpaths_are_in_the_fixture(self):
        # What the port exists for: a `..` above the root kept, and removal
        # back to the root skipping one slash only. Asserted from the fixture
        # (Qt's words), so the fixture cannot lose them unseen.
        pairs = dict(map(tuple, json.loads(CLEAN_FIXTURE.read_text(encoding="utf-8"))["pairs"]))
        self.assertEqual([pairs["/a/../../b"], pairs["/.."], pairs["/.//a/"], pairs["/x/state/../wide/state.json"]],
                         ["/../b", "/..", "//a", "/x/wide/state.json"])


class StateLinkGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = pathlib.Path(self.tmp.name)
        os.chmod(self.c, 0o700)
        self.real = json.dumps(v2(favorites=["t:real"])) + "\n"

    # ---- layouts
    def put(self, path, mode=0o600, text=None):
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.real if text is None else text, encoding="utf-8")
        os.chmod(path, mode)
        return path

    def linked_state(self):
        """state -> T/state, the state folder a link; returns the state path."""
        (self.c / "T" / "state").mkdir(parents=True)
        os.chmod(self.c / "T" / "state", 0o700)
        os.symlink(self.c / "T" / "state", self.c / "state")
        return self.c / "state"

    def link(self, at, target):
        at = pathlib.Path(at)
        at.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, at)

    def listing(self):
        """Every entry under the scratch root: kind, mode, inode, link target, text."""
        seen = {}
        for folder, dirs, files in os.walk(self.c):
            for name in dirs + files:
                path = os.path.join(folder, name)
                st = os.lstat(path)
                entry = [oct(st.st_mode), st.st_ino]
                if os.path.islink(path):
                    entry.append(os.readlink(path))
                elif os.path.isfile(path):
                    entry.append(pathlib.Path(path).read_text(encoding="utf-8", errors="replace"))
                seen[os.path.relpath(path, self.c)] = entry
        return seen

    # ---- verbs
    def private(self, state_dir):
        return run("state", "--state-dir", str(state_dir), "private")

    def init(self, state_dir):
        return run("state", "--state-dir", str(state_dir), "init")

    def assert_kept(self, state_dir):
        code, payload, err = self.private(state_dir)
        self.assertEqual((code, payload), (0, {"ok": True, "kind": "state", "action": "private", "file": "kept"}), err)
        code, payload, err = self.init(state_dir)
        self.assertEqual((code, payload["found"], payload["created"]), (0, "file", False), err)
        self.assertEqual(payload["state"]["favorites"], ["t:real"])   # the file the kernel names, read

    def assert_split(self, state_dir, init_changes=False):
        before = self.listing()
        code, payload, err = self.private(state_dir)
        self.assertEqual((code, payload["ok"], payload.get("why"), payload["error"]["code"], payload["error"]["message"]),
                         (1, False, "split-link", "state_not_private", SPLIT_SENTENCE), err)
        self.assertNotIn("created", payload)
        self.assertEqual(self.listing(), before)   # nothing created, chmod-ed or moved
        code, payload, err = self.init(state_dir)
        self.assertEqual((code, payload["found"], payload["created"]), (0, "split-link", False), err)
        if not init_changes:
            self.assertEqual(self.listing(), before)

    # ---- layouts that must NOT be refused
    def test_no_link_at_all(self):
        state = self.c / "state"
        state.mkdir(mode=0o700)
        self.put(state / "state.json")
        self.assert_kept(state)

    def test_an_absolute_link(self):
        state = self.linked_state()
        self.put(self.c / "T" / "wide" / "state.json")
        (self.c / "wide").mkdir()   # somewhere for a literal misreading to land
        self.link(self.c / "T" / "state" / "state.json", self.c / "T" / "wide" / "state.json")
        self.assert_kept(state)

    def test_a_relative_link_with_no_dotdot(self):
        state = self.c / "state"
        state.mkdir(mode=0o700)
        self.put(state / "sub" / "state.json")
        self.link(state / "state.json", "sub/state.json")
        self.assert_kept(state)

    def test_a_link_inside_a_linked_state_folder_that_names_the_same_file(self):
        state = self.linked_state()
        self.put(self.c / "T" / "state" / "state.real.json")
        self.link(self.c / "T" / "state" / "state.json", "state.real.json")
        self.assert_kept(state)

    def test_a_dotdot_out_of_the_linked_folder_and_back_into_one_of_its_name_is_one_file_by_two_strings(self):
        # The literal reading is state/state.real.json and the kernel's
        # T/state/state.real.json: different strings, the same file.
        state = self.linked_state()
        self.put(self.c / "T" / "state" / "state.real.json")
        self.link(self.c / "T" / "state" / "state.json", "../state/state.real.json")
        self.assertNotEqual(helper.qt_link_literal(str(state / "state.json")), os.path.realpath(state / "state.json"))
        self.assert_kept(state)

    def test_an_absolute_target_through_a_linked_folder(self):
        # ~/Sync -> /mnt/data/Sync, state.json -> ~/Sync/state.json.
        state = self.c / "home" / ".local" / "state" / "omarchy-iptv"
        state.mkdir(parents=True)
        self.put(self.c / "mnt" / "data" / "Sync" / "state.json")
        os.symlink(self.c / "mnt" / "data" / "Sync", self.c / "home" / "Sync")
        self.link(state / "state.json", self.c / "home" / "Sync" / "state.json")
        self.assertNotEqual(helper.qt_link_literal(str(state / "state.json")), os.path.realpath(state / "state.json"))
        self.assert_kept(state)

    def test_a_relative_dotdot_target_where_no_folder_it_climbs_out_of_is_a_link(self):
        state = self.c / "home" / ".local" / "state" / "omarchy-iptv"
        state.mkdir(parents=True)
        self.put(self.c / "home" / ".local" / "dotfiles" / "state.json")
        self.link(state / "state.json", "../../dotfiles/state.json")
        self.assert_kept(state)

    def test_forty_links_on_the_literal_reading_are_followed(self):
        # The bound's other side: 40 links (state.json, then s0..s38) end at
        # the file the kernel reads, so nothing is refused.
        self.chain_of(40)
        self.assert_kept(self.c / "state")

    # ---- layouts that must be refused
    def row_layout(self, real_mode=0o600, literal_folder=True):
        state = self.linked_state()
        self.put(self.c / "T" / "wide" / "state.json", real_mode)
        if literal_folder:
            (self.c / "wide").mkdir()
        self.link(self.c / "T" / "state" / "state.json", "../wide/state.json")
        return state

    def test_the_rows_case_a_folder_at_the_literal_location(self):
        state = self.row_layout(real_mode=0o644)
        self.assert_split(state, init_changes=True)
        # `state private` refused before anything changed; `state init`, as
        # for any link at the path, made the file the kernel names 0600 and
        # created nothing.
        self.assertEqual(os.stat(self.c / "T" / "wide" / "state.json").st_mode & 0o777, 0o600)
        self.assertFalse(os.path.lexists(self.c / "wide" / "state.json"))

    def test_no_folder_at_the_literal_location(self):
        # QSaveFile's open fails there (measured: No such file or directory),
        # so no save reaches the file read either: refused by name.
        state = self.row_layout(literal_folder=False)
        self.assert_split(state)

    def test_a_dangling_link_whose_literal_folder_exists_is_refused_before_anything_is_created(self):
        # 0.19.1 + D-SINK-103: `state private` created the kernel's file 0600
        # and empty while the save landed in the literal one.
        state = self.linked_state()
        (self.c / "T" / "wide").mkdir()
        (self.c / "wide").mkdir()
        self.link(self.c / "T" / "state" / "state.json", "../wide/state.json")
        self.assert_split(state)
        self.assertFalse(os.path.lexists(self.c / "T" / "wide" / "state.json"))

    def test_a_chain_read_hop_by_hop_against_the_previous_hops_folder(self):
        # T/state/state.json -> ../a/b/state.json (the kernel: T/a/b/state.json);
        # the literal a/b/state.json -> ../w/state.json, read against a/b:
        # a/w/state.json, the spike's chain2 case.
        state = self.linked_state()
        self.put(self.c / "T" / "a" / "b" / "state.json")
        (self.c / "a" / "w").mkdir(parents=True)
        self.link(self.c / "a" / "b" / "state.json", "../w/state.json")
        self.link(self.c / "T" / "state" / "state.json", "../a/b/state.json")
        self.assertEqual(helper.qt_link_literal(str(state / "state.json")), str(self.c / "a" / "w" / "state.json"))
        self.assert_split(state)

    def test_a_linked_parent_of_a_real_state_folder(self):
        # home/.local/state -> data/state, the state folder real beneath it.
        (self.c / "data" / "state" / "omarchy-iptv").mkdir(parents=True)
        os.chmod(self.c / "data" / "state" / "omarchy-iptv", 0o700)
        (self.c / "home" / ".local" / "x").mkdir(parents=True)
        os.symlink(self.c / "data" / "state", self.c / "home" / ".local" / "state")
        self.put(self.c / "data" / "x" / "state.json")
        self.link(self.c / "data" / "state" / "omarchy-iptv" / "state.json", "../../x/state.json")
        self.assert_split(self.c / "home" / ".local" / "state" / "omarchy-iptv")

    def test_a_hard_link_at_the_literal_location_is_one_file_but_two_entries(self):
        # QSaveFile renames its new file over the literal NAME, which leaves
        # the kernel's name on the old inode (the spike's hardlink case).
        state = self.row_layout()
        os.link(self.c / "T" / "wide" / "state.json", self.c / "wide" / "state.json")
        self.assert_split(state)

    def chain_of(self, links):
        """state.json and links-1 more on the literal reading, ending at the
        file the kernel reads (T/l/s0) by an absolute target; the kernel's own
        reading is two links."""
        self.linked_state()
        self.put(self.c / "T" / "l" / "s0")
        (self.c / "l").mkdir()
        self.link(self.c / "T" / "state" / "state.json", "../l/s0")
        for k in range(links - 2):
            self.link(self.c / "l" / ("s%d" % k), "s%d" % (k + 1))
        self.link(self.c / "l" / ("s%d" % (links - 2)), self.c / "T" / "l" / "s0")

    def test_forty_one_links_on_the_literal_reading_are_past_the_bound(self):
        self.chain_of(41)
        self.assertIsNone(helper.qt_link_literal(str(self.c / "state" / "state.json")))
        self.assert_split(self.c / "state")

    def test_a_literal_loop_the_kernel_resolves(self):
        # The literal a/state.json -> ../a/state.json is itself; the kernel
        # reads T/a/state.json. QSaveFile, past its own bound, wrote over the
        # path itself (the spike's loop case).
        state = self.linked_state()
        self.put(self.c / "T" / "a" / "state.json")
        self.link(self.c / "a" / "state.json", "../a/state.json")
        self.link(self.c / "T" / "state" / "state.json", "../a/state.json")
        self.assert_split(state)

    def test_a_loop_the_kernel_cannot_resolve_either_keeps_its_own_answers(self):
        state = self.c / "state"
        state.mkdir(mode=0o700)
        self.link(state / "state.json", "state.json")
        before = self.listing()
        self.assertFalse(helper.state_link_split(str(state / "state.json")))
        code, payload, err = self.private(state)
        self.assertEqual((code, payload.get("why")), (1, "unreachable"), err)
        code, payload, err = self.init(state)
        self.assertEqual((code, payload["found"]), (0, "link"), err)
        self.assertEqual(self.listing(), before)


class ModelSplitLinkTest(unittest.TestCase):
    """The shell's half, in node: the init's word blocks a start that could
    not load the file with its own sentence, and `state private`'s word
    reaches the journal line, not "refused"."""

    def test_the_model_reads_split_link(self):
        script = (
            'const M=require("./Model.mjs");'
            'const P="/home/u/.local/state/omarchy-iptv/state.json";'
            'const L=o=>JSON.stringify(Object.assign({kind:"state"},o))+"\\n";'
            'const n=M.stateUnreadableNotice("split-link",P,false);'
            'process.stdout.write(JSON.stringify(['
            ' M.stateInitFound(L({ok:true,action:"init",found:"split-link",created:false}),0),'
            ' M.stateLoadDecision({kind:"absent",initFound:"split-link"}),'
            ' M.stateLoadDecision({kind:"absent",initFound:"split-link",retried:true}),'
            ' M.stateLoadDecision({kind:"unparsed",initFound:"split-link",retried:true}),'
            ' M.stateLoadDecision({kind:"loaded",initFound:"split-link"}),'
            ' M.statePrivateReply(L({ok:false,action:"private",why:"split-link"}),1),'
            ' n.title, n.body, M.stateUnreadableNotice("split-link",P,true).title]))')
        done = subprocess.run(["node", "-e", script], capture_output=True, text=True, cwd=ROOT, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr[-800:])
        self.assertEqual(json.loads(done.stdout), [
            "split-link",
            {"act": "retry", "reason": "absent"},
            {"act": "block", "reason": "split-link"},
            {"act": "block", "reason": "split-link"},
            {"act": "apply", "reason": "loaded"},
            {"ok": False, "why": "split-link"},
            "Saved sources not loaded",
            "/home/u/.local/state/omarchy-iptv/state.json is a symbolic link that would be saved to a different "
            "file than the one it is read from, because its target climbs with .. out of a folder that is itself "
            "a symbolic link. Sources, favorites and settings changed now are not kept. Point it at the file that "
            "holds your state with an absolute path that has no .. in it, then run omarchy restart shell.",
            "Saving has stopped",
        ])


if __name__ == "__main__":
    unittest.main()
