"""The suite may not touch the user's own files. Asserted, not assumed.

The defect this exists for: `playlist` resolved its state directory with
`state_dir(getattr(args, "state_dir", None))`, so every invocation that did
not name one reached the live directory. Instrumented, one `python3 -m
unittest discover -s tests` ran 130 channel id remap passes, 124 of them over
the real ~/.local/state/omarchy-iptv/state.json, rewriting it whenever the map
moved anything. Roughly fourteen existing tests call `playlist` with no state
flag, and none of them was wrong to: the helper was.

Two independent things now stop it, and both are checked here rather than
described:

  1. the helper touches no state file unless a state directory is named
     (tests/test_channel_ids.py, PlaylistCommandRemapTest), so omission is
     safe by construction;
  2. tests/helper_loader.py redirects HOME and every XDG variable into a
     throwaway directory before any test runs, so even a command that DOES
     resolve a default path cannot land on the user's copy.

Layer 2 is what this module verifies, by calling the shipping resolvers and
by re-fingerprinting the real file. Delete the redirect from helper_loader and
every test below goes red.
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

import helper_loader
from helper_loader import load_helper

helper = load_helper()
FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
HELPER = helper_loader.HELPER


class RedirectedHomeTest(unittest.TestCase):
    """Every path the helper derives from the environment lands in the sandbox."""

    def assert_in_sandbox(self, path, label):
        resolved = pathlib.Path(path).resolve()
        self.assertTrue(str(resolved).startswith(str(helper_loader.SANDBOX)),
                        "%s resolved to %s, outside the test sandbox" % (label, resolved))
        self.assertFalse(str(resolved).startswith(str(helper_loader.REAL_HOME) + os.sep),
                         "%s resolved into the user's own home" % label)

    def test_the_default_paths_are_all_inside_the_sandbox(self):
        # These four are every directory the helper can reach without being
        # told one, and each of them is a place it writes.
        self.assert_in_sandbox(helper.home_dir(), "home_dir()")
        self.assert_in_sandbox(helper.state_dir(None), "state_dir(None)")
        self.assert_in_sandbox(helper.cache_dir(None), "cache_dir(None)")
        self.assert_in_sandbox(helper.runtime_dir(), "runtime_dir()")

    def test_the_host_config_path_is_inside_the_sandbox(self):
        # D-SINK-18 added a resolver that feeds a CHMOD, which makes it the
        # most dangerous one in the file: `config shield` takes no path, so
        # this function alone decides which file the verb changes.
        self.assert_in_sandbox(helper.config_home(), "config_home()")
        self.assert_in_sandbox(helper.host_config_path(), "host_config_path()")

    def test_a_tilde_path_expands_into_the_sandbox(self):
        # `~` reaches the same place: a CLI argument carrying one cannot walk
        # back out into the user's tree.
        self.assert_in_sandbox(helper.state_dir("~/.local/state/omarchy-iptv"), "state_dir('~/...')")

    def test_a_subprocess_helper_run_inherits_the_redirect(self):
        # Most of the suite runs the helper as a child process, so the
        # redirect is worth nothing unless it crosses the process boundary.
        # `state init` with no --state-dir is the shortest command that writes
        # to the default state directory; it must land in the sandbox.
        completed = subprocess.run([sys.executable, str(HELPER), "state", "init"],
                                   capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        written = pathlib.Path(helper.state_dir(None)) / helper.STATE_FILE
        self.assert_in_sandbox(written, "the state file a child process wrote")
        self.assertTrue(written.is_file())

    def test_the_users_own_state_file_is_byte_identical(self):
        # Fingerprinted by helper_loader at import, before a single test ran.
        # F-HARNESS-113: "changed" is the only red. A fingerprint that moved
        # while the kernel refused this suite every write to the file is the
        # owner's own shell saving, which a gate used to read as its own.
        self.assertNotEqual(helper_loader.live_state_verdict(), "changed",
                            "the test suite modified %s" % helper_loader.REAL_STATE_FILE)

    def test_the_users_own_host_config_is_byte_and_mode_identical(self):
        # D-SINK-18. The bytes AND the mode: a chmod leaves mtime and the
        # digest alone, so the bytes-only fingerprint above cannot see the one
        # change the new verb makes. The lead's own file is 0600 and a suite
        # that moved it would have broken their desktop.
        self.assertNotEqual(helper_loader.live_config_verdict(), "changed",
                            "the test suite modified %s" % helper_loader.REAL_CONFIG_FILE)

    def test_the_mode_half_of_that_fingerprint_would_notice(self):
        # Rule 11 for the half that is new. Same comparison, over a file this
        # test owns, chmod-ed and nothing else: the bytes fingerprint does NOT
        # move and the pair does.
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "shell.json"
            path.write_text("{}", encoding="utf-8")
            os.chmod(path, 0o600)
            bytes_before = helper_loader.fingerprint_of(path)
            before = (bytes_before, helper_loader.mode_of(path))
            self.assertEqual(before[1], 0o600)
            os.chmod(path, 0o644)
            self.assertEqual(helper_loader.fingerprint_of(path), bytes_before)
            self.assertNotEqual((helper_loader.fingerprint_of(path), helper_loader.mode_of(path)), before)
            path.unlink()
            self.assertIsNone(helper_loader.mode_of(path))

    def test_the_fingerprint_would_notice(self):
        # Rule 11: the check above can only be trusted if it can fail. Run the
        # same comparison against a file this test owns and changes.
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "state.json"
            path.write_text(json.dumps({"version": 2, "favorites": []}), encoding="utf-8")
            before = helper_loader.fingerprint_of(path)
            self.assertIsNotNone(before)
            self.assertEqual(helper_loader.fingerprint_of(path), before)
            path.write_text(json.dumps({"version": 2, "favorites": ["u:1"]}), encoding="utf-8")
            self.assertNotEqual(helper_loader.fingerprint_of(path), before)
            path.unlink()
            self.assertIsNone(helper_loader.fingerprint_of(path))


# What a child python does for OwnersSaveTest: it imports helper_loader with
# XDG_STATE_HOME naming a scratch folder, so that folder's state.json is "the
# user's real state file" to it, says it is ready, waits for the test to
# rewrite the file from OUTSIDE, tries a write of its own, and prints what
# the shipping verdict then reads.
OWNERS_SAVE_CHILD = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import helper_loader
print("ready", flush=True)
sys.stdin.readline()
try:
    with open(str(helper_loader.REAL_STATE_FILE) + ".child", "w") as handle:
        handle.write("x")
    wrote = True
except OSError:
    wrote = False
print(json.dumps({"verdict": helper_loader.live_state_verdict(),
                  "readOnly": helper_loader.LIVE_STATE_READ_ONLY,
                  "wrote": wrote}), flush=True)
"""


def bwrap_works():
    import shutil
    if not shutil.which("bwrap"):
        return False
    try:
        return subprocess.run(["bwrap", "--dev-bind", "/", "/", "true"],
                              capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class LiveFileVerdictTest(unittest.TestCase):
    """F-HARNESS-113: the decision itself, every arm."""

    def test_an_unmoved_fingerprint_is_untouched_whatever_the_mount(self):
        for before, after in ((True, True), (False, False), (True, False), (False, True)):
            self.assertEqual(helper_loader.live_file_verdict("a", "a", before, after), "untouched")
        self.assertEqual(helper_loader.live_file_verdict(None, None, False, False), "untouched")

    def test_a_moved_fingerprint_is_the_suites_unless_both_ends_were_read_only(self):
        self.assertEqual(helper_loader.live_file_verdict("a", "b", False, False), "changed")
        self.assertEqual(helper_loader.live_file_verdict("a", "b", True, False), "changed")
        self.assertEqual(helper_loader.live_file_verdict("a", "b", False, True), "changed")
        self.assertEqual(helper_loader.live_file_verdict("a", None, False, False), "changed")
        self.assertEqual(helper_loader.live_file_verdict("a", "b", True, True), "not_ours")

    def test_a_writable_or_absent_path_is_not_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(helper_loader.mount_is_read_only(tmp))
            self.assertFalse(helper_loader.mount_is_read_only(os.path.join(tmp, "absent")))


class OwnersSaveTest(unittest.TestCase):
    """F-HARNESS-113, observed: a save made from outside the suite while a
    child python has the folder read-only reads "not_ours"; the same save
    with the folder writable reads "changed"."""

    def run_child(self, wrap):
        with tempfile.TemporaryDirectory() as tmp:
            folder = pathlib.Path(tmp) / "omarchy-iptv"
            folder.mkdir()
            state = folder / "state.json"
            state.write_text(json.dumps({"version": 2, "favorites": []}), encoding="utf-8")
            env = dict(os.environ, XDG_STATE_HOME=tmp)
            argv = wrap(str(folder)) + [sys.executable, "-c", OWNERS_SAVE_CHILD,
                                        str(pathlib.Path(__file__).resolve().parent)]
            child = subprocess.Popen(argv, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), "ready")
                # The owner's shell, standing outside the child's namespace.
                state.write_text(json.dumps({"version": 2, "favorites": ["u:1"]}), encoding="utf-8")
                out, err = child.communicate("go\n", timeout=30)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()
            self.assertEqual(child.returncode, 0, err)
            return json.loads(out)

    def test_with_the_folder_writable_the_save_reads_as_the_suites(self):
        self.assertEqual(self.run_child(lambda folder: []),
                         {"verdict": "changed", "readOnly": False, "wrote": True})

    @unittest.skipUnless(bwrap_works(), "needs bwrap (a mount namespace without privilege)")
    def test_with_the_folder_read_only_the_save_is_not_the_suites(self):
        answer = self.run_child(lambda folder: ["bwrap", "--dev-bind", "/", "/",
                                                "--ro-bind", folder, folder])
        self.assertEqual(answer, {"verdict": "not_ours", "readOnly": True, "wrote": False})


if __name__ == "__main__":
    unittest.main()
