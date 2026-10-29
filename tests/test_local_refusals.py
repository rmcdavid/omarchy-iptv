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

D-SRC-74 (2026-10-28). `cache remove|epg-clear|logos-clear --key K` over a
regular file at sources/K reached main()'s catch-all (`internal`, a
NotADirectoryError naming the path, a traceback). They answer R25c's
`folder_unusable` now, as `cache migrate` did, and the rule-15 matrix below
holds every cache subverb to one answer per damage.

D-PLY-34 (2026-10-28). Two player-verb replies the shell read in the fetch
verbs' words are pinned here as the helper gives them: the player lock's
`busy` (this test holds the lock) and main()'s answer to a MemoryError on a
player verb, `too_large` with `kind: player` or `kind: play`. The second runs
the helper's main() in this process, with MemoryError raised where the verb
reads the channel list: main() answers every MemoryError the same way, and no
limit on a real process lands that error at a predictable line.

D-PLY-31 (2026-10-28). The player's own refusals the "did not play" card
showed in the helper's words (`socket_path_blocked`, `spawn_failed`) are
driven here as the shell meets them -- a file at the socket path, an `mpv`
that cannot be executed -- and the spawn's own exhaustion, which reached
main()'s `internal`, is driven with the fork refused (RLIMIT_NPROC 0) and with
no room for a pipe (the descriptor table full but for the lock and one more):
both now answer `spawn_failed` with the error's words. Those limits are set in
the helper's own process, between the fork and the exec, never in this one.
The clipboard verb's `spawn_failed` (a wl-paste that cannot be executed) is
pinned beside them, because the two share a code and not a sentence.

D-EPG-13 (2026-10-28). The EPG verb's two parse refusals, `bad_xml` (a feed
that does not parse, and one that declares an XML entity, D-EPG-6) and
`empty_epg`, from three small fixture feeds into a fresh cache folder.

The helper's code and the model's sentence are joined by a name, so this file
and tests/Model.test.js run the same fixture (rule 13). Each case damages a
scratch folder for real and runs the helper as the shell does, a subprocess
with a timeout, with HOME, the XDG folders and PATH inside the scratch
directory: nothing of the user's is read, and no mpv can be started.

Run: python3 -m unittest discover -s tests
"""
import contextlib
import fcntl
import io
import json
import os
import pathlib
import resource
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from helper_loader import load_helper          # redirects HOME and $XDG_* first

ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER = ROOT / "bin" / "omarchy-iptv"
FIXTURES = ROOT / "tests" / "fixtures"
FIXTURE = json.loads((FIXTURES / "local-refusals.json").read_text(encoding="utf-8"))
TIMEOUT = 20
KEY = "b067481d"
# pipes-refused: the descriptor table the helper starts with. Every slot from
# 3 to NOFILE_LIMIT - 3 holds /dev/null, so after the exec the helper has the
# last two: the player's lock takes one, and a pipe needs two.
NOFILE_LIMIT = 16

helper_module = load_helper()


def refuse_fork():
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))


def leave_two_descriptors():
    """Between the fork and the exec of the helper: lower RLIMIT_NOFILE and
    fill every slot below its last two with an INHERITABLE /dev/null (dup2
    makes one), so what the helper finds free after the exec does not depend
    on which descriptors this test process happened to hold. Slots the parent
    held close-on-exec are overwritten here, never left to be freed at exec."""
    resource.setrlimit(resource.RLIMIT_NOFILE, (NOFILE_LIMIT, NOFILE_LIMIT))
    null = os.open(os.devnull, os.O_RDONLY)
    for fd in range(3, NOFILE_LIMIT - 2):
        if fd != null:
            os.dup2(null, fd)
    if 3 <= null < NOFILE_LIMIT - 2:
        os.set_inheritable(null, True)
    else:
        os.close(null)


class LocalRefusalTest(unittest.TestCase):
    def scratch(self):
        """A fresh scratch directory for one case."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        (self.root / "no-bin").mkdir()
        self.preexec = None
        self.close_fds = True
        self.in_process = False
        self.names = {}

    def env(self):
        return {
            "PATH": str(self.root / "no-bin"),
            "HOME": str(self.home),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
            "XDG_STATE_HOME": str(self.home / ".local" / "state"),
            "XDG_RUNTIME_DIR": str(self.root / "runtime"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

    def helper(self, argv):
        if self.in_process:
            return self.helper_in_process(argv)
        try:
            proc = subprocess.run([sys.executable, "-I", str(HELPER), *argv], capture_output=True, text=True,
                                  env=self.env(), timeout=TIMEOUT, stdin=subprocess.DEVNULL,
                                  preexec_fn=self.preexec, close_fds=self.close_fds)
        except subprocess.TimeoutExpired:
            self.fail("the helper did not answer within %d s: %s" % (TIMEOUT, " ".join(argv)))
        lines = proc.stdout.strip().splitlines()
        return proc.returncode, lines, proc.stderr

    def helper_in_process(self, argv):
        """main() in this process, with MemoryError where the verb reads the
        channel list -- the reply main() gives any MemoryError (D-M3U-1)."""
        out, err = io.StringIO(), io.StringIO()
        # read_channel_document since 2026-10-29: player_target reads the
        # whole channels.json (what the parse recorded about its playlist,
        # D-SINK-58) and load_channels reads it through the same function.
        with mock.patch.object(helper_module, "read_channel_document", side_effect=MemoryError()), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = helper_module.main(list(argv))
        return code, out.getvalue().strip().splitlines(), err.getvalue()

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
        if name == "socket-file":
            folder = self.root / "run" / "omarchy-iptv"
            folder.mkdir(parents=True, mode=0o700)
            blocker = folder / "mpv.sock"
            blocker.write_text("x", encoding="utf-8")
            return folder, lambda: blocker.is_file() and blocker.read_text(encoding="utf-8") == "x" and not blocker.is_symlink()
        if name in ("mpv-not-executable", "wl-paste-not-executable"):
            program = self.root / "no-bin" / name.split("-not-")[0]
            program.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            os.chmod(program, 0o644)
            folder = self.root / "run" / "omarchy-iptv"
            return folder, lambda: (program.stat().st_mode & 0o777) == 0o644 and not os.path.lexists(folder / "mpv.sock")
        if name == "fork-refused":
            if os.geteuid() == 0:
                self.skipTest("root is not refused by RLIMIT_NPROC")
            self.preexec = refuse_fork
            folder = self.root / "run" / "omarchy-iptv"
            return folder, lambda: not os.path.lexists(folder / "mpv.sock")
        if name == "pipes-refused":
            self.preexec = leave_two_descriptors
            self.close_fds = False
            folder = self.root / "run" / "omarchy-iptv"
            return folder, lambda: not os.path.lexists(folder / "mpv.sock")
        if name in ("key-file", "sources-link"):
            cache_root = self.root / "cache-root"
            sources = cache_root / "sources"
            self.names = {"root": str(cache_root), "key": KEY}
            if name == "key-file":
                sources.mkdir(parents=True, mode=0o700)
                folder = sources / KEY
                folder.write_text("x", encoding="utf-8")
                return folder, lambda: folder.is_file() and not folder.is_symlink() and folder.read_text(encoding="utf-8") == "x"
            cache_root.mkdir(mode=0o700)
            os.symlink(cache_root / "gone", sources)
            return sources, lambda: os.path.islink(sources) and not os.path.lexists(cache_root / "gone")
        if name == "fresh":
            folder = self.root / "fresh"
            folder.mkdir(mode=0o700)
            return folder, lambda: sorted(os.listdir(folder)) == ["epg-status.json"]
        if name == "lock-held":
            folder = self.root / "run" / "omarchy-iptv"
            folder.mkdir(parents=True, mode=0o700)
            held = os.open(folder / "player.lock", os.O_CREAT | os.O_RDWR, 0o600)
            self.addCleanup(os.close, held)
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return folder, lambda: sorted(os.listdir(folder)) == ["player.lock"]
        if name == "out-of-memory":
            self.in_process = True
            folder = self.root / "run" / "omarchy-iptv"
            return folder, lambda: not os.path.lexists(folder)
        raise AssertionError("unknown damage %r" % name)

    def seeded_cache(self):
        """A cache folder holding a channel list, for the verbs that resolve a
        channel before they touch the runtime folder; -> (folder, first id)."""
        cache = self.root / "cache"
        in_process, preexec, close_fds = self.in_process, self.preexec, self.close_fds
        self.in_process, self.preexec, self.close_fds = False, None, True
        code, lines, err = self.helper(["playlist", "--url", str(FIXTURES / "basic.m3u"), "--cache-dir", str(cache)])
        self.in_process, self.preexec, self.close_fds = in_process, preexec, close_fds
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

    def run_case(self, case):
        """Damage, run, and compare: -> the reply."""
        self.scratch()
        folder, untouched = self.damage(case["damage"])
        names = {"dir": str(folder), "fixtures": str(FIXTURES)}
        names.update(self.names)
        if "{cache}" in case["argv"]:
            cache, first = self.seeded_cache()
            names.update({"cache": str(cache), "id": first})
        code, lines, err = self.helper(self.fill(case["argv"], names))
        want = self.fill(case["reply"], names)
        self.assertEqual(len(lines), 1, (lines, err))
        got = json.loads(lines[0])
        for key, value in list(want.items()):
            # `{int}`: the run's own durationMs, any whole number.
            if value == "{int}" and isinstance(got.get(key), int) and got[key] >= 0:
                want[key] = got[key]
        self.assertEqual((code, got), (1, want), err)
        self.assertNotIn("Traceback", err)
        if "error" in want:
            # The journal keeps what the reply says, the path included
            # (the service logs the helper's stderr, redacted).
            self.assertIn(want["error"]["message"], err)
        else:
            # The clipboard verb: one object on stdout and nothing on stderr.
            self.assertEqual(err, "")
        self.assertTrue(untouched(), "the damage was changed: %s" % case["id"])
        return got

    def test_every_case_is_the_fixtures_reply_one_line_and_exit_1_with_nothing_written(self):
        for case in FIXTURE["refusals"]:
            with self.subTest(case=case["id"]):
                self.run_case(case)

    def test_every_other_refusal_is_the_fixtures_reply_one_line_and_exit_1(self):
        # The replies the checks over `refusals` cannot take (the fixture's
        # `about` says why): the player lock's `busy` and main()'s
        # MemoryError on a player verb (D-PLY-34), the clipboard's
        # spawn_failed (D-PLY-31) and the guide's own refusals, the
        # provider's (D-EPG-13).
        for case in FIXTURE["otherRefusals"]:
            with self.subTest(case=case["id"]):
                self.run_case(case)

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

    # D-SRC-74, rule 15: every `cache` subverb over each damage at a key, the
    # way the shell's cacheProc runs it. ONE answer per damage, and where a
    # subverb differs, the reason: `prune` sweeps the sources folder and
    # skips (never touches) any name that is not a key folder, so a file or
    # a link AT a key is `skipped` there, not refused; every key verb keeps
    # `bad_key` for a link at the key (D-SRC-73's decision: source_dir
    # refuses a linked key folder before anything else). A damage at the
    # sources folder or above it is R25c's from every subverb, the removals
    # included, which on dev answered ok for a link to nothing there and
    # `internal` for a file. Red on dev 795a7bf.
    CACHE_VERBS = (("migrate", ["--key", KEY]), ("remove", ["--key", KEY]), ("epg-clear", ["--key", KEY]),
                   ("logos-clear", ["--key", KEY]), ("prune", ["--keep", KEY, "--active", KEY]))
    CACHE_DAMAGES = {
        "key-file": ("folder_unusable", "sources/" + KEY, "is not a folder"),
        "key-link": ("bad_key", None, "cache key is a symbolic link"),
        "key-link-to-file": ("bad_key", None, "cache key is a symbolic link"),
        "sources-link": ("folder_unusable", "sources", "is a symbolic link whose target is missing or is not a folder"),
        "sources-file": ("folder_unusable", "sources", "is not a folder"),
        "cache-root-file": ("folder_unusable", "", "is not a folder"),
    }

    def cache_damage(self, name):
        cache_root = self.root / "cache-root"
        sources = cache_root / "sources"
        key_dir = sources / KEY
        if name.startswith("key-"):
            sources.mkdir(parents=True, mode=0o700)
            if name == "key-file":
                key_dir.write_text("x", encoding="utf-8")
            elif name == "key-link":
                os.symlink(sources / "gone", key_dir)
            else:
                (sources / "a-file").write_text("x", encoding="utf-8")
                os.symlink(sources / "a-file", key_dir)
            target = key_dir
        elif name.startswith("sources-"):
            cache_root.mkdir(mode=0o700)
            if name == "sources-link":
                os.symlink(cache_root / "gone", sources)
            else:
                sources.write_text("x", encoding="utf-8")
            target = sources
        else:
            cache_root.parent.mkdir(parents=True, exist_ok=True)
            cache_root.write_text("x", encoding="utf-8")
            target = cache_root
        before = (os.path.islink(target), target.is_file(), os.readlink(target) if os.path.islink(target) else None)
        return cache_root, target, lambda: (os.path.islink(target), target.is_file(),
                                            os.readlink(target) if os.path.islink(target) else None) == before

    def test_every_cache_subverb_answers_one_way_per_damage(self):
        for damage, (code, where, what) in self.CACHE_DAMAGES.items():
            for verb, extra in self.CACHE_VERBS:
                with self.subTest(damage=damage, verb=verb):
                    self.scratch()
                    cache_root, target, untouched = self.cache_damage(damage)
                    exit_code, lines, err = self.helper(["cache", "--cache-dir", str(cache_root), verb, *extra])
                    self.assertEqual(len(lines), 1, (lines, err))
                    reply = json.loads(lines[0])
                    self.assertNotIn("Traceback", err)
                    self.assertTrue(untouched(), "the damage was changed")
                    if verb == "prune" and damage.startswith("key-"):
                        # The sweep's own reading: skipped, never touched.
                        self.assertEqual((exit_code, reply["ok"], KEY in reply["skipped"]), (0, True, True))
                        continue
                    self.assertEqual((exit_code, reply["ok"], reply["kind"], (reply.get("error") or {}).get("code")), (1, False, "cache", code))
                    if where is None:
                        self.assertEqual(reply["error"]["message"], what)
                    else:
                        folder = cache_root / where if where else cache_root
                        self.assertEqual(reply["error"]["message"], "%s %s; nothing was written" % (folder, what))


if __name__ == "__main__":
    unittest.main()
