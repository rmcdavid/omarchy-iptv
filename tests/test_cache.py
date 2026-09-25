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

    def test_a_symlinked_subdirectory_is_refused_never_followed(self):
        """D-LOGO-10, through the verb that has shipped with the hole since
        D-LOGO-4 introduced CACHE_SUBDIRS: `cache remove` cleared the contents
        of a symlinked logos/ target too."""
        victim = pathlib.Path(self.tmp.name) / "victim"
        victim.mkdir()
        (victim / "important.txt").write_text("precious", encoding="utf-8")
        self.seed(self.sources / KEY)
        os.symlink(victim, self.sources / KEY / "logos")
        code, payload, _ = self.cache_cmd("remove", "--key", KEY)
        self.assertEqual(code, 0)
        self.assertEqual(self.names(victim), ["important.txt"])
        self.assertIn("logos", payload["kept"])
        self.assertTrue((self.sources / KEY / "logos").is_symlink())

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


class EpgClearTest(CacheTestCase):
    """M2-09 GS11 / D-GS-4. Clearing a source's guide URL has to take the cache
    that URL produced, for the same reason removing a source takes its whole
    directory: otherwise the next start loads epg-now.json for a guide source
    that is no longer configured and its warning is back in the footer. The
    source itself stays, so the playlist half of the cache and the directory
    are untouched -- which is the whole difference from `remove`."""

    EPG = ("epg-now.json", "epg-status.json", "epg-window.txt")
    KEPT = ("channels.json", "playlist-status.json")

    def test_removes_the_epg_files_and_keeps_the_source(self):
        self.seed(self.sources / KEY)
        self.seed(self.sources / OTHER)
        code, payload, _ = self.cache_cmd("epg-clear", "--key", KEY)
        self.assertEqual(code, 0)
        self.assertEqual(payload, {"ok": True, "kind": "cache", "action": "epg-clear", "key": KEY,
                                   "removed": sorted(self.EPG)})
        self.assertEqual(self.names(self.sources / KEY), sorted(self.KEPT))
        self.assertEqual(self.names(self.sources / OTHER), sorted(FILES))   # untouched

    def test_clearing_a_url_that_was_never_set_is_not_an_error(self):
        self.seed(self.sources / KEY, self.KEPT)
        code, payload, _ = self.cache_cmd("epg-clear", "--key", KEY)
        self.assertEqual((code, payload["removed"]), (0, []))
        self.assertEqual(self.names(self.sources / KEY), sorted(self.KEPT))
        # and again on a source that has no directory at all
        code, payload, _ = self.cache_cmd("epg-clear", "--key", OTHER)
        self.assertEqual((code, payload["removed"]), (0, []))

    def test_an_empty_directory_is_left_for_the_source_that_owns_it(self):
        self.seed(self.sources / KEY, self.EPG)
        code, payload, _ = self.cache_cmd("epg-clear", "--key", KEY)
        self.assertEqual(payload["removed"], sorted(self.EPG))
        self.assertEqual(self.names(self.sources / KEY), [])
        self.assertTrue((self.sources / KEY).is_dir())

    def test_files_that_are_not_ours_are_not_touched(self):
        self.seed(self.sources / KEY)
        (self.sources / KEY / "notes.txt").write_text("mine", encoding="utf-8")
        (self.sources / KEY / ".tmp-channels.json-0011").write_text("x", encoding="utf-8")
        code, payload, _ = self.cache_cmd("epg-clear", "--key", KEY)
        self.assertEqual(payload["removed"], sorted(self.EPG))
        self.assertEqual(self.names(self.sources / KEY),
                         sorted([".tmp-channels.json-0011", "notes.txt", *self.KEPT]))

    def test_bad_keys_are_refused_and_nothing_is_deleted(self):
        self.seed(self.sources / KEY)
        for bad in ("../x", "abc", "d5977d8a/..", "D5977D8A", "", "sources", "..", "d5977d8a/../" + KEY):
            code, payload, stderr = self.cache_cmd("epg-clear", "--key", bad)
            self.assertEqual(code, 1, bad)
            self.assertEqual(payload["error"]["code"], "bad_key", bad)
            self.assertEqual(payload["action"], "epg-clear", bad)
            self.assertNotIn(self.tmp.name, json.dumps(payload) + stderr, bad)
        self.assertEqual(self.names(self.sources / KEY), sorted(FILES))

    def test_symlinks_are_refused_or_unlinked_never_followed(self):
        victim = pathlib.Path(self.tmp.name) / "victim"
        self.seed(victim)
        self.sources.mkdir(parents=True)
        os.symlink(victim, self.sources / KEY)
        code, payload, _ = self.cache_cmd("epg-clear", "--key", KEY)
        self.assertEqual((code, payload["error"]["code"]), (1, "bad_key"))
        self.assertEqual(self.names(victim), sorted(FILES))
        # a symlinked EPG file inside a real key directory is unlinked, and
        # whatever it pointed at survives
        target = pathlib.Path(self.tmp.name) / "outside.json"
        target.write_text("precious", encoding="utf-8")
        (self.sources / OTHER).mkdir(parents=True)
        os.symlink(target, self.sources / OTHER / "epg-now.json")
        code, payload, _ = self.cache_cmd("epg-clear", "--key", OTHER)
        self.assertEqual((code, payload["removed"]), (0, ["epg-now.json"]))
        self.assertEqual(target.read_text(encoding="utf-8"), "precious")
        self.assertEqual(self.names(self.sources / OTHER), [])


class LogosClearTest(CacheTestCase):
    """D-LOGO-9. The twin of epg-clear, filed for the reason GS11 gave for that
    one: the part of the cache an input produced has to be reclaimable when the
    user withdraws the input. Turning showLogos off stopped the fetch and
    blanked the rows and reclaimed nothing -- measured on a live install at
    1,173 files and 40.9 MB, 99 per cent of that source's whole cache, against
    a documented ceiling of 1.28 GB per source that no prune could ever collect
    because prune only clears keys that are NOT kept. The source stays, so the
    playlist half of the cache and the directory are untouched."""

    LOGOS = ("1a2b3c4d", "5e6f7a8b", "9c0d1e2f")
    KEPT = ("channels.json", "playlist-status.json")

    def seed_logos(self, key=KEY, names=LOGOS, size=100):
        directory = self.sources / key / "logos"
        directory.mkdir(parents=True, exist_ok=True)
        for name in names:
            (directory / name).write_bytes(b"x" * size)
        return directory

    def test_removes_the_logos_and_keeps_the_source(self):
        self.seed(self.sources / KEY)
        self.seed_logos()
        self.seed(self.sources / OTHER)
        self.seed_logos(OTHER)
        code, payload, _ = self.cache_cmd("logos-clear", "--key", KEY)
        self.assertEqual(code, 0)
        self.assertEqual(payload, {"ok": True, "kind": "cache", "action": "logos-clear",
                                   "key": KEY, "removed": True, "files": 3,
                                   "bytes": 300, "kept": 0})
        self.assertEqual(self.names(self.sources / KEY), sorted(FILES))
        self.assertFalse((self.sources / KEY / "logos").exists())
        # the other source keeps every one of its own
        self.assertEqual(self.names(self.sources / OTHER / "logos"), sorted(self.LOGOS))

    def test_the_playlist_half_and_the_directory_survive(self):
        self.seed(self.sources / KEY, self.KEPT)
        self.seed_logos()
        code, payload, _ = self.cache_cmd("logos-clear", "--key", KEY)
        self.assertEqual((code, payload["removed"]), (0, True))
        self.assertEqual(self.names(self.sources / KEY), sorted(self.KEPT))
        self.assertTrue((self.sources / KEY).is_dir())

    def test_clearing_logos_that_were_never_fetched_is_not_an_error(self):
        self.seed(self.sources / KEY, self.KEPT)
        code, payload, _ = self.cache_cmd("logos-clear", "--key", KEY)
        self.assertEqual(code, 0)
        self.assertEqual((payload["removed"], payload["files"], payload["bytes"]), (False, 0, 0))
        self.assertEqual(self.names(self.sources / KEY), sorted(self.KEPT))
        # and again on a source that has no directory at all
        code, payload, _ = self.cache_cmd("logos-clear", "--key", OTHER)
        self.assertEqual((code, payload["removed"], payload["files"]), (0, False, 0))

    def test_running_it_twice_changes_nothing_the_second_time(self):
        self.seed(self.sources / KEY)
        self.seed_logos()
        first = self.cache_cmd("logos-clear", "--key", KEY)[1]
        second = self.cache_cmd("logos-clear", "--key", KEY)[1]
        self.assertEqual((first["removed"], first["files"]), (True, 3))
        self.assertEqual((second["removed"], second["files"], second["bytes"]), (False, 0, 0))
        self.assertEqual(self.names(self.sources / KEY), sorted(FILES))

    def test_files_that_are_not_ours_are_not_touched(self):
        self.seed(self.sources / KEY)
        self.seed_logos()
        (self.sources / KEY / "notes.txt").write_text("mine", encoding="utf-8")
        code, payload, _ = self.cache_cmd("logos-clear", "--key", KEY)
        self.assertEqual(payload["files"], 3)
        self.assertEqual(self.names(self.sources / KEY), sorted(["notes.txt", *FILES]))

    def test_a_nested_directory_is_left_and_reported_never_descended_into(self):
        self.seed(self.sources / KEY, self.KEPT)
        logos = self.seed_logos()
        (logos / "nested").mkdir()
        (logos / "nested" / "deep.bin").write_bytes(b"y" * 999)
        code, payload, _ = self.cache_cmd("logos-clear", "--key", KEY)
        # the three regular files went; the directory did not, so the rmdir
        # failed and `removed` says so rather than claiming success
        self.assertEqual((code, payload["removed"]), (0, False))
        self.assertEqual((payload["files"], payload["bytes"], payload["kept"]), (3, 300, 1))
        self.assertEqual(self.names(logos), ["nested"])
        self.assertTrue((logos / "nested" / "deep.bin").exists())

    def test_a_symlink_is_unlinked_never_followed_and_adds_no_bytes(self):
        target = pathlib.Path(self.tmp.name) / "outside.bin"
        target.write_bytes(b"z" * 9999)
        self.seed(self.sources / KEY, self.KEPT)
        logos = self.seed_logos(names=("1a2b3c4d",))
        os.symlink(target, logos / "cccccccc")
        code, payload, _ = self.cache_cmd("logos-clear", "--key", KEY)
        self.assertEqual((code, payload["removed"]), (0, True))
        # 100 bytes from the one real file. NOT 10099: a link to a big file
        # must never be reported as space this verb freed.
        self.assertEqual((payload["files"], payload["bytes"]), (1, 100))
        self.assertEqual(target.read_bytes(), b"z" * 9999)
        self.assertFalse(logos.exists())

    def test_a_symlinked_logos_directory_is_refused_never_followed(self):
        """D-LOGO-10. source_dir has refused a symlinked KEY directory since
        the beginning; the guard never reached one level down. os.listdir
        follows a link, so this deleted the contents of whatever it pointed
        at -- and reported `removed: false` while doing it."""
        victim = pathlib.Path(self.tmp.name) / "victim"
        victim.mkdir()
        (victim / "important.txt").write_text("precious", encoding="utf-8")
        (victim / "also.txt").write_text("precious", encoding="utf-8")
        self.seed(self.sources / KEY, self.KEPT)
        os.symlink(victim, self.sources / KEY / "logos")
        code, payload, _ = self.cache_cmd("logos-clear", "--key", KEY)
        self.assertEqual(code, 0)
        self.assertEqual(self.names(victim), ["also.txt", "important.txt"])
        # nothing was freed, and the payload must not pretend otherwise
        self.assertEqual((payload["removed"], payload["files"], payload["bytes"]),
                         (False, 0, 0))
        self.assertTrue((self.sources / KEY / "logos").is_symlink())

    def test_no_name_based_check_is_consulted_so_there_is_no_window_to_race(self):
        """D-LOGO-10, second round. The first fix was `if os.path.islink(path):
        return False`, and a check on a NAME followed by an operation on the
        same NAME is two resolutions of that name. Racing the second one --
        swapping the directory for a symlink between them -- deleted two files
        outside the cache while the payload reported `removed: false`.

        The fix was structural: O_DIRECTORY|O_NOFOLLOW refuses a link AT OPEN
        and yields a handle on the inode that was checked, and every lstat,
        unlink and rmdir is dir_fd-relative to that handle. So this asserts the
        property that makes the race impossible: no name-based link check is
        consulted on the logos path at all. It goes red the moment someone
        reintroduces a check-then-use pair.

        If a future implementation legitimately calls islink AFTER opening,
        this test is wrong rather than the code -- but it should have to be
        argued, which is the point."""
        self.seed(self.sources / KEY, self.KEPT)
        self.seed_logos()
        target = str(self.sources / KEY / "logos")
        seen = []
        real = os.path.islink

        def watched(path):
            if str(path) == target:
                seen.append(str(path))
            return real(path)

        os.path.islink = watched
        try:
            code, payload, _ = self.cache_cmd("logos-clear", "--key", KEY)
        finally:
            os.path.islink = real
        self.assertEqual((code, payload["removed"], payload["files"]), (0, True, 3))
        self.assertEqual(seen, [], "a name-based link check reopened the TOCTOU window")

    def test_the_swap_lands_between_the_open_and_the_unlinks_and_misses(self):
        """D-LOGO-10, the operation half. The structural test above proves
        there is no name-based CHECK to race; this proves the OPERATIONS are
        anchored too. The swap is injected after the directory has been opened
        and listed -- the exact window a path-based unlink would resolve
        through -- and the deletions must still land on the inode that was
        opened, not on whatever the name now points at.

        Reverting `os.unlink(entry, dir_fd=fd)` to `os.unlink(os.path.join(
        path, entry))` makes this test empty the victim directory."""
        victim = pathlib.Path(self.tmp.name) / "victim"
        victim.mkdir()
        for name in ("taxes.pdf", "thesis.odt"):
            (victim / name).write_text("precious", encoding="utf-8")
        self.seed(self.sources / KEY, self.KEPT)
        logos = self.seed_logos()

        real_listdir = os.listdir
        seen = []
        swapped = []

        def racing_listdir(target):
            out = real_listdir(target)
            # The logos directory is listed through a handle twice: once by
            # subdir_census to measure it, then by remove_cache_subdir to
            # delete it. Fire on the SECOND -- after the removal has opened
            # the inode, before it unlinks -- which is the window a path-based
            # unlink would resolve through. Firing on the first only proves
            # the open refuses a link, which the test above already covers.
            if isinstance(target, int) and sorted(out) == sorted(self.LOGOS):
                seen.append(True)
                if len(seen) == 2 and not swapped:
                    swapped.append(True)
                    os.rename(logos, str(logos) + ".moved")
                    os.symlink(victim, logos)
            return out

        os.listdir = racing_listdir
        try:
            code, payload, _ = self.cache_cmd("logos-clear", "--key", KEY)
        finally:
            os.listdir = real_listdir

        self.assertTrue(swapped, "the injection never fired; the test proves nothing")
        self.assertEqual(code, 0)
        # the victim is untouched: the unlinks went to the inode that was
        # opened, not to whatever the name pointed at by the time they ran
        self.assertEqual(sorted(p.name for p in victim.iterdir()),
                         ["taxes.pdf", "thesis.odt"])
        # and the real logo files DID go, from the directory that was opened,
        # which is now reachable only under its renamed path
        self.assertEqual(sorted(p.name for p in pathlib.Path(str(logos) + ".moved").iterdir()), [])
        self.assertEqual(payload["files"], 3)

    def test_bad_keys_are_refused_and_nothing_is_deleted(self):
        self.seed(self.sources / KEY)
        self.seed_logos()
        for bad in ("../x", "abc", "d5977d8a/..", "D5977D8A", "", "sources", "..", "d5977d8a/../" + KEY):
            code, payload, stderr = self.cache_cmd("logos-clear", "--key", bad)
            self.assertEqual(code, 1, bad)
            self.assertEqual(payload["error"]["code"], "bad_key", bad)
            self.assertEqual(payload["action"], "logos-clear", bad)
            self.assertNotIn(self.tmp.name, json.dumps(payload) + stderr, bad)
        self.assertEqual(self.names(self.sources / KEY / "logos"), sorted(self.LOGOS))

    def test_a_symlinked_key_directory_is_refused(self):
        victim = pathlib.Path(self.tmp.name) / "victim"
        (victim / "logos").mkdir(parents=True)
        (victim / "logos" / "1a2b3c4d").write_bytes(b"x" * 100)
        self.sources.mkdir(parents=True)
        os.symlink(victim, self.sources / KEY)
        code, payload, _ = self.cache_cmd("logos-clear", "--key", KEY)
        self.assertEqual((code, payload["error"]["code"]), (1, "bad_key"))
        self.assertEqual(self.names(victim / "logos"), ["1a2b3c4d"])

    def test_the_payload_carries_counts_and_never_a_filename(self):
        """Rule 5. A logo filename is the fnv1a32 of its URL, so the listing
        epg-clear can safely emit would here re-identify the channels the user
        just stopped consenting to fetch -- the exposure D-LOGO-4 found in the
        leftovers, which there is no reason to recreate on stdout."""
        self.seed(self.sources / KEY, self.KEPT)
        self.seed_logos()
        code, payload, stderr = self.cache_cmd("logos-clear", "--key", KEY)
        blob = json.dumps(payload) + stderr
        for name in self.LOGOS:
            self.assertNotIn(name, blob)
        self.assertNotIn(self.tmp.name, blob)    # nor any path
        # "logos" appears only as the action name, never as a path component
        self.assertNotIn("/logos", blob)
        self.assertEqual(sorted(payload),
                         ["action", "bytes", "files", "kept", "key", "kind", "ok", "removed"])


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
        for args in (["migrate", "--key", KEY], ["remove", "--key", KEY], ["prune", "--keep", KEY], ["remove", "--key", "../x"],
                     ["epg-clear", "--key", KEY], ["epg-clear", "--key", "../x"]):
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
