"""Per-source cache directory tests for bin/omarchy-iptv (`cache` subcommand,
ARCHITECTURE-SOURCES.md 2.3): layout, migrate, remove, prune, and the
key / path-traversal / symlink guards.

Run: python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

from helper_loader import load_helper

helper = load_helper()
ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER = ROOT / "bin" / "omarchy-iptv"
FIXTURES = ROOT / "tests" / "fixtures"
KEY = "d5977d8a"
OTHER = "d990c2e4"
FILES = ("channels.json", "playlist-status.json", "epg-now.json", "epg-status.json", "epg-window.txt")


def run(*args):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(args))
    lines = out.getvalue().strip().splitlines()
    return code, json.loads(lines[-1]) if lines else None, err.getvalue()


class CacheTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = pathlib.Path(self.tmp.name) / "cache"
        self.sources = self.cache / "sources"

    def cache_cmd(self, *args):
        return run("cache", "--cache-dir", str(self.cache), *args)

    def seed(self, directory, names=FILES, age=0):
        directory.mkdir(parents=True, exist_ok=True)
        for name in names:
            path = directory / name
            path.write_text("{}\n", encoding="utf-8")
            if age:
                stamp = time.time() - age
                os.utime(path, (stamp, stamp))
        return directory

    def names(self, directory):
        return sorted(p.name for p in directory.iterdir()) if directory.exists() else None


class LayoutTest(CacheTestCase):
    def test_playlist_writes_into_a_private_per_source_dir(self):
        target = self.sources / KEY
        code, status, _ = run("playlist", "--url", str(FIXTURES / "basic.m3u"), "--cache-dir", str(target))
        self.assertEqual(code, 0)
        self.assertEqual(status["channelCount"], 3)
        self.assertEqual(self.names(target), ["channels.json", "playlist-status.json"])
        for name in ("channels.json", "playlist-status.json"):
            self.assertEqual((target / name).stat().st_mode & 0o777, 0o600)
        self.assertEqual(target.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.sources.stat().st_mode & 0o777, 0o700)
        # The legacy location stays untouched.
        self.assertEqual(self.names(self.cache), ["sources"])


class MigrateTest(CacheTestCase):
    def test_moves_the_five_names_and_cleans_temp_files(self):
        self.seed(self.cache)
        (self.cache / ".tmp-channels.json-deadbeef").write_text("x", encoding="utf-8")
        (self.cache / "keep.me").write_text("x", encoding="utf-8")
        code, payload, _ = self.cache_cmd("migrate", "--key", KEY)
        self.assertEqual(code, 0)
        self.assertEqual(payload["kind"], "cache")
        self.assertEqual(payload["action"], "migrate")
        self.assertEqual(payload["key"], KEY)
        self.assertEqual(payload["moved"], list(FILES))
        self.assertEqual(payload["removed"], [".tmp-channels.json-deadbeef"])
        self.assertEqual(self.names(self.sources / KEY), sorted(FILES))
        self.assertEqual(self.names(self.cache), ["keep.me", "sources"])
        self.assertEqual((self.sources / KEY).stat().st_mode & 0o777, 0o700)
        # Idempotent.
        code, payload, _ = self.cache_cmd("migrate", "--key", KEY)
        self.assertEqual(code, 0)
        self.assertEqual((payload["moved"], payload["removed"]), ([], []))

    def test_existing_target_wins_and_legacy_is_deleted(self):
        self.seed(self.cache, ("channels.json",))
        (self.sources / KEY).mkdir(parents=True)
        (self.sources / KEY / "channels.json").write_text('{"new": true}', encoding="utf-8")
        code, payload, _ = self.cache_cmd("migrate", "--key", KEY)
        self.assertEqual(code, 0)
        self.assertEqual((payload["moved"], payload["removed"]), ([], ["channels.json"]))
        self.assertEqual((self.sources / KEY / "channels.json").read_text(encoding="utf-8"), '{"new": true}')
        self.assertFalse((self.cache / "channels.json").exists())

    def test_without_a_key_legacy_files_are_deleted(self):
        self.seed(self.cache, ("channels.json", "epg-window.txt"))
        code, payload, _ = self.cache_cmd("migrate")
        self.assertEqual(code, 0)
        self.assertEqual(payload["key"], "")
        self.assertEqual(payload["moved"], [])
        self.assertEqual(payload["removed"], ["channels.json", "epg-window.txt"])
        self.assertEqual(self.names(self.cache), ["sources"])

    def test_missing_cache_dir_is_fine(self):
        code, payload, _ = self.cache_cmd("migrate", "--key", KEY)
        self.assertEqual(code, 0)
        self.assertEqual((payload["moved"], payload["removed"]), ([], []))
        self.assertTrue((self.sources / KEY).is_dir())


class RemoveTest(CacheTestCase):
    def test_removes_known_files_and_the_directory(self):
        self.seed(self.sources / KEY)
        (self.sources / KEY / ".tmp-epg-window.txt-0011").write_text("x", encoding="utf-8")
        self.seed(self.sources / OTHER, ("channels.json",))
        code, payload, _ = self.cache_cmd("remove", "--key", KEY)
        self.assertEqual(code, 0)
        self.assertEqual(payload, {"ok": True, "kind": "cache", "action": "remove", "key": KEY,
                                   "removed": [".tmp-epg-window.txt-0011", *sorted(FILES)], "kept": []})
        self.assertFalse((self.sources / KEY).exists())
        self.assertEqual(self.names(self.sources / OTHER), ["channels.json"])   # untouched

    def test_unknown_files_keep_the_directory(self):
        self.seed(self.sources / KEY, ("channels.json",))
        (self.sources / KEY / "notes.txt").write_text("mine", encoding="utf-8")
        (self.sources / KEY / "sub").mkdir()
        code, payload, _ = self.cache_cmd("remove", "--key", KEY)
        self.assertEqual(code, 0)
        self.assertEqual(payload["removed"], ["channels.json"])
        self.assertEqual(payload["kept"], ["notes.txt", "sub"])
        self.assertEqual(self.names(self.sources / KEY), ["notes.txt", "sub"])

    def test_missing_directory_is_ok(self):
        code, payload, _ = self.cache_cmd("remove", "--key", KEY)
        self.assertEqual(code, 0)
        self.assertEqual((payload["removed"], payload["kept"]), ([], []))

    def test_bad_keys_are_refused_and_nothing_is_deleted(self):
        self.seed(self.cache, ("channels.json",))
        self.seed(self.sources / KEY)
        victim = pathlib.Path(self.tmp.name) / "victim"
        self.seed(victim)
        for bad in ("../x", "abc", "d5977d8a/..", "D5977D8A", "d5977d8a-", "d5977d8a-1234", "", "sources", "..", "d5977d8a/../" + KEY):
            code, payload, stderr = self.cache_cmd("remove", "--key", bad)
            self.assertEqual(code, 1, bad)
            self.assertEqual(payload["error"]["code"], "bad_key", bad)
            self.assertEqual(payload["action"], "remove")
            self.assertNotIn(self.tmp.name, json.dumps(payload) + stderr)
        self.assertEqual(self.names(self.sources / KEY), sorted(FILES))
        self.assertEqual(self.names(self.cache), ["channels.json", "sources"])
        self.assertEqual(self.names(victim), sorted(FILES))

    def test_symlinked_key_directory_is_refused(self):
        victim = pathlib.Path(self.tmp.name) / "victim"
        self.seed(victim)
        self.sources.mkdir(parents=True)
        os.symlink(victim, self.sources / KEY)
        code, payload, _ = self.cache_cmd("remove", "--key", KEY)
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "bad_key")
        self.assertEqual(self.names(victim), sorted(FILES))
        self.assertTrue((self.sources / KEY).is_symlink())
        # A symlink to a sibling key directory inside sources/ is refused too.
        self.seed(self.sources / OTHER)
        os.symlink(self.sources / OTHER, self.sources / "0000aaaa")
        code, payload, _ = self.cache_cmd("remove", "--key", "0000aaaa")
        self.assertEqual(payload["error"]["code"], "bad_key")
        self.assertEqual(self.names(self.sources / OTHER), sorted(FILES))

    def test_symlinked_files_are_unlinked_not_followed(self):
        target = pathlib.Path(self.tmp.name) / "outside.json"
        target.write_text("precious", encoding="utf-8")
        (self.sources / KEY).mkdir(parents=True)
        os.symlink(target, self.sources / KEY / "channels.json")
        code, payload, _ = self.cache_cmd("remove", "--key", KEY)
        self.assertEqual(code, 0)
        self.assertEqual(payload["removed"], ["channels.json"])
        self.assertEqual(target.read_text(encoding="utf-8"), "precious")
        self.assertFalse((self.sources / KEY).exists())


class PruneTest(CacheTestCase):
    def test_keeps_listed_keys_removes_orphans_and_skips_non_keys(self):
        self.seed(self.sources / KEY)
        self.seed(self.sources / OTHER)
        self.seed(self.sources / "1a2b3c4d")
        self.seed(self.sources / "1a2b3c4d-2")
        self.seed(self.sources / "not-a-key")
        (self.sources / "a1b2c3d4").write_text("a file, not a dir", encoding="utf-8")
        stubborn = self.seed(self.sources / "ffffffff", ("channels.json",))
        (stubborn / "user.txt").write_text("x", encoding="utf-8")
        code, payload, _ = self.cache_cmd("prune", "--keep", KEY, OTHER, "--active", KEY, "--epg-max-age", "86400")
        self.assertEqual(code, 0)
        self.assertEqual(payload["removed"], ["1a2b3c4d", "1a2b3c4d-2"])
        self.assertEqual(payload["kept"], ["ffffffff"])
        self.assertEqual(payload["skipped"], ["a1b2c3d4", "not-a-key"])
        self.assertEqual(payload["agedEpg"], [])
        self.assertEqual(self.names(self.sources), ["a1b2c3d4", KEY, OTHER, "ffffffff", "not-a-key"])
        self.assertEqual(self.names(stubborn), ["user.txt"])
        self.assertEqual(self.names(self.sources / "not-a-key"), sorted(FILES))

    def test_ages_epg_files_of_inactive_keys_only(self):
        self.seed(self.sources / KEY, age=2 * 86400)
        self.seed(self.sources / OTHER, age=2 * 86400)
        fresh = self.seed(self.sources / "0000aaaa", age=3600)
        code, payload, _ = self.cache_cmd("prune", "--keep", KEY, OTHER, "0000aaaa", "--active", KEY)
        self.assertEqual(code, 0)
        self.assertEqual(payload["agedEpg"], [OTHER])
        self.assertEqual(payload["removed"], [])
        self.assertEqual(self.names(self.sources / KEY), sorted(FILES))                      # active: never aged
        self.assertEqual(self.names(self.sources / OTHER), ["channels.json", "playlist-status.json"])
        self.assertEqual(self.names(fresh), sorted(FILES))                                  # younger than the max age

    def test_no_keep_removes_every_key_dir(self):
        self.seed(self.sources / KEY)
        code, payload, _ = self.cache_cmd("prune")
        self.assertEqual(code, 0)
        self.assertEqual(payload["removed"], [KEY])
        self.assertEqual(self.names(self.sources), [])

    def test_bad_keys_in_keep_or_active_abort_before_deleting(self):
        self.seed(self.sources / KEY)
        for args in (["--keep", "../x"], ["--keep", KEY, "--active", "abc"]):
            code, payload, _ = self.cache_cmd("prune", *args)
            self.assertEqual(code, 1, args)
            self.assertEqual(payload["error"]["code"], "bad_key", args)
        self.assertEqual(self.names(self.sources / KEY), sorted(FILES))

    def test_active_key_is_kept_even_when_not_listed(self):
        # D-SRC-07 (SRC-HELP-07): `--active` is implicitly kept; its EPG
        # files are still never aged.
        active = self.seed(self.sources / "11111111", age=2 * 86400)
        self.seed(self.sources / "22222222", age=2 * 86400)
        self.seed(self.sources / "33333333")
        self.seed(self.sources / "44444444")
        code, payload, _ = self.cache_cmd("prune", "--keep", "22222222", "33333333", "--active", "11111111", "--epg-max-age", "86400")
        self.assertEqual(code, 0)
        self.assertEqual(payload["removed"], ["44444444"])
        self.assertEqual(payload["agedEpg"], ["22222222"])
        self.assertEqual(self.names(self.sources), ["11111111", "22222222", "33333333"])
        self.assertEqual(self.names(active), sorted(FILES))
        # `--active` alone (no --keep) keeps just that key.
        code, payload, _ = self.cache_cmd("prune", "--active", "11111111")
        self.assertEqual(code, 0)
        self.assertEqual(payload["removed"], ["22222222", "33333333"])
        self.assertEqual(self.names(self.sources), ["11111111"])

    def test_symlinked_key_dirs_are_skipped(self):
        victim = pathlib.Path(self.tmp.name) / "victim"
        self.seed(victim)
        self.sources.mkdir(parents=True)
        os.symlink(victim, self.sources / KEY)
        code, payload, _ = self.cache_cmd("prune")
        self.assertEqual(code, 0)
        self.assertEqual(payload["skipped"], [KEY])
        self.assertEqual(self.names(victim), sorted(FILES))


class CacheCliTest(CacheTestCase):
    def test_exactly_one_json_line_and_no_paths_on_stdout(self):
        self.seed(self.cache, ("channels.json",))
        for args in (["migrate", "--key", KEY], ["remove", "--key", KEY], ["prune", "--keep", KEY], ["remove", "--key", "../x"]):
            completed = subprocess.run([sys.executable, str(HELPER), "cache", "--cache-dir", str(self.cache), *args],
                                       capture_output=True, text=True, timeout=30)
            self.assertEqual(len(completed.stdout.strip().splitlines()), 1, args)
            json.loads(completed.stdout)
            self.assertNotIn(self.tmp.name, completed.stdout + completed.stderr, args)

    def test_cache_dir_after_the_action_also_works(self):
        self.seed(self.sources / KEY)
        code, payload, _ = run("cache", "remove", "--key", KEY, "--cache-dir", str(self.cache))
        self.assertEqual(code, 0)
        self.assertEqual(payload["removed"], sorted(FILES))


if __name__ == "__main__":
    unittest.main()
