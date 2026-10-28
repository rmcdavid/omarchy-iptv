"""A folder the helper writes into that it cannot use: the REAL helper's reply,
joined to the sentence the shell shows for it (tests/fixtures/local-refusals.json).

D-SRC-73 (2026-10-27). A source's cache folder that is a symbolic link to
nothing got two answers: the `playlist` verb's `except OSError` (D-SRC-69)
caught R25c's FolderUnusable and answered `cache_unwritable`, and every other
verb answered R25c's `folder_unusable`, whose sentence names the full path --
which Model.statusReason had no entry for, so the guide-data banner showed it.
Now every verb answers `folder_unusable` with R25c's sentence (the journal
keeps the path) and the model maps the code to one sentence that names none.

D-PLY-30 (2026-10-27). `player start|restart|stop` let a PermissionError from
making the runtime folder, or an IsADirectoryError from opening the lock file,
reach main()'s catch-all: `internal`, the exception and the path, in a reply
of `kind: player`. They now answer in their own shape, `kind: player.<verb>`:
R25c's `folder_unusable` for a runtime folder that is a link to nothing, and
`runtime_unwritable` -- which of the two, the error's own words, no path --
for a folder that cannot be made or a lock that cannot be opened. Nothing is
created, and the lock's folder is left where it is.

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
        if name == "parent-0500":
            if os.geteuid() == 0:
                self.skipTest("root is not refused by a 0500 folder")
            parent = self.root / "ro"
            parent.mkdir(mode=0o500)
            os.chmod(parent, 0o500)
            self.addCleanup(os.chmod, parent, 0o700)
            folder = parent / "omarchy-iptv"
            return folder, lambda: not os.path.lexists(folder) and (parent.stat().st_mode & 0o777) == 0o500
        if name == "lock-dir":
            folder = self.root / "run" / "omarchy-iptv"
            lock = folder / "player.lock"
            lock.mkdir(parents=True)
            os.chmod(folder, 0o700)
            (lock / "keep").write_text("x", encoding="utf-8")
            return folder, lambda: lock.is_dir() and sorted(os.listdir(lock)) == ["keep"] and sorted(os.listdir(folder)) == ["player.lock"]
        raise AssertionError("unknown damage %r" % name)

    def seeded_cache(self):
        """A cache folder holding a channel list, for the verbs that resolve a
        channel before they touch the runtime folder; -> (folder, first id)."""
        cache = self.root / "cache"
        code, lines, err = self.helper(["playlist", "--url", str(FIXTURES / "basic.m3u"), "--cache-dir", str(cache)])
        self.assertEqual(code, 0, err)
        channels = json.loads((cache / "channels.json").read_text(encoding="utf-8"))["channels"]
        return cache, channels[0]["id"]

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
                if "{cache}" in case["argv"]:
                    cache, first = self.seeded_cache()
                    names.update({"cache": str(cache), "id": first})
                code, lines, err = self.helper(self.fill(case["argv"], names))
                want = self.fill(case["reply"], names)
                self.assertEqual(len(lines), 1, lines)
                self.assertEqual((code, json.loads(lines[0])), (1, want), err)
                self.assertNotIn("Traceback", err)
                # The journal keeps what the reply says, the path included
                # (the service logs the helper's stderr, redacted).
                self.assertIn(want["error"]["message"], err)
                self.assertTrue(untouched(), "the damage was changed: %s" % case["id"])


    def test_the_probe_still_answers_over_a_lock_it_cannot_open(self):
        # A guard, green on dev as well: `player probe` takes no lock of its
        # own and settles a stale socket only under the player lock, giving
        # the settle up when it cannot take it (settle_under_lock). The lock's
        # open now raises the named refusal instead of an OSError, and the
        # probe must still read that as "cannot take the lock" and answer.
        # (`orphan-check` reaches the same settle only after it has stopped a
        # player, which needs one running; it is not driven here.)
        self.scratch()
        folder, untouched = self.damage("lock-dir")
        code, lines, err = self.helper(["player", "probe", "--socket", str(folder / "mpv.sock")])
        self.assertEqual((code, len(lines)), (0, 1), err)
        reply = json.loads(lines[0])
        self.assertEqual((reply["ok"], reply["kind"], reply["running"]), (True, "player.probe", False))
        self.assertNotIn("Traceback", err)
        self.assertTrue(untouched())

if __name__ == "__main__":
    unittest.main()
