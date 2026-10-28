"""A folder the helper writes into that it cannot use: the REAL helper's reply,
joined to the sentence the shell shows for it (tests/fixtures/local-refusals.json).

D-SRC-73 (2026-10-27). A source's cache folder that is a symbolic link to
nothing got two answers: the `playlist` verb's `except OSError` (D-SRC-69)
caught R25c's FolderUnusable and answered `cache_unwritable`, and every other
verb answered R25c's `folder_unusable`, whose sentence names the full path --
which Model.statusReason had no entry for, so the guide-data banner showed it.
Now every verb answers `folder_unusable` with R25c's sentence (the journal
keeps the path) and the model maps the code to one sentence that names none.

The helper's code and the model's sentence are joined by a name, so this file
and tests/Model.test.js run the same fixture (rule 13). Each case damages a
scratch folder for real and runs the helper as the shell does, a subprocess
with a timeout, with HOME, the XDG folders and PATH inside the scratch
directory: nothing of the user's is read, and no mpv can be started.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER = ROOT / "bin" / "omarchy-iptv"
FIXTURES = ROOT / "tests" / "fixtures"
FIXTURE = json.loads((FIXTURES / "local-refusals.json").read_text(encoding="utf-8"))
TIMEOUT = 20


class LocalRefusalTest(unittest.TestCase):
    def scratch(self):
        """A fresh scratch directory for one case."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        (self.root / "no-bin").mkdir()

    def helper(self, argv):
        env = {
            "PATH": str(self.root / "no-bin"),
            "HOME": str(self.home),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
            "XDG_STATE_HOME": str(self.home / ".local" / "state"),
            "XDG_RUNTIME_DIR": str(self.root / "runtime"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        try:
            proc = subprocess.run([sys.executable, "-I", str(HELPER), *argv], capture_output=True, text=True,
                                  env=env, timeout=TIMEOUT, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            self.fail("the helper did not answer within %d s: %s" % (TIMEOUT, " ".join(argv)))
        lines = proc.stdout.strip().splitlines()
        return proc.returncode, lines, proc.stderr

    def damage(self, name):
        """Make the damage for real; -> ({dir}, a check that it was left as it was)."""
        if name == "folder-link":
            target = self.root / "gone"
            folder = self.root / "d"
            os.symlink(target, folder)
            return folder, lambda: (os.path.islink(folder), os.path.lexists(target)) == (True, False)
        if name == "folder-file":
            folder = self.root / "d"
            folder.write_text("x", encoding="utf-8")
            return folder, lambda: folder.is_file() and folder.read_text(encoding="utf-8") == "x"
        raise AssertionError("unknown damage %r" % name)

    @staticmethod
    def fill(value, names):
        if isinstance(value, str):
            for key, text in names.items():
                value = value.replace("{%s}" % key, text)
            return value
        if isinstance(value, list):
            return [LocalRefusalTest.fill(item, names) for item in value]
        if isinstance(value, dict):
            return {key: LocalRefusalTest.fill(item, names) for key, item in value.items()}
        return value

    def test_every_case_is_the_fixtures_reply_one_line_and_exit_1_with_nothing_written(self):
        for case in FIXTURE["refusals"]:
            with self.subTest(case=case["id"]):
                self.scratch()
                folder, untouched = self.damage(case["damage"])
                names = {"dir": str(folder), "fixtures": str(FIXTURES)}
                code, lines, err = self.helper(self.fill(case["argv"], names))
                want = self.fill(case["reply"], names)
                self.assertEqual(len(lines), 1, lines)
                self.assertEqual((code, json.loads(lines[0])), (1, want), err)
                self.assertNotIn("Traceback", err)
                # The journal keeps what the reply says, the path included
                # (the service logs the helper's stderr, redacted).
                self.assertIn(want["error"]["message"], err)
                self.assertTrue(untouched(), "the damage was changed: %s" % case["id"])


if __name__ == "__main__":
    unittest.main()
