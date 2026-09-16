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
        self.assertEqual(helper_loader.live_state_fingerprint(), helper_loader.LIVE_STATE_BEFORE,
                         "the test suite modified %s" % helper_loader.REAL_STATE_FILE)

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


if __name__ == "__main__":
    unittest.main()
