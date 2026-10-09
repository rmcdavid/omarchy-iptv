"""D-SINK-18: `config shield` over real files, with the modes read back.

The mode of a file is directly observable, so nothing here greps the
implementation for a string it was written to contain (rule 14). Every case
below creates a real file under a scratch $XDG_CONFIG_HOME, runs the shipping
verb against it, and asks the filesystem what happened.

The user's own ~/.config/omarchy/shell.json is never reachable from here:
tests/helper_loader.py redirects HOME and XDG_CONFIG_HOME into a throwaway
directory before any test module is imported, every case below sets its own
XDG_CONFIG_HOME on top of that, and tests/test_live_state_guard.py
fingerprints the real file's bytes AND its mode to prove the suite left both
alone.

Run: python3 -m unittest discover -s tests
"""
import contextlib
import errno
import io
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import helper_loader
from helper_loader import load_helper

helper = load_helper()
HELPER = helper_loader.HELPER
FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "config-shield.json"
VECTORS = json.loads(FIXTURE.read_text(encoding="utf-8"))

# The packaged default on this machine: a root-owned 0644 regular file at
# exactly the shape this verb resolves. It makes the ownership refusal a real
# measurement instead of a mock, and it is the one case where a bug here would
# try to chmod a file under /usr/share, which CLAUDE.md forbids touching.
PACKAGED_CONFIG_HOME = "/usr/share/omarchy/config"
PACKAGED_FILE = pathlib.Path(PACKAGED_CONFIG_HOME) / "omarchy" / "shell.json"


def packaged_is_foreign():
    try:
        st = PACKAGED_FILE.stat()
    except OSError:
        return False
    return stat.S_ISREG(st.st_mode) and st.st_uid != os.geteuid()


class ShieldTestCase(unittest.TestCase):
    """A scratch $XDG_CONFIG_HOME with the host's directory layout in it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        # D-SINK-18 repair: the helper derives the path from $HOME, not from
        # $XDG_CONFIG_HOME, because the HOST does (shell.qml:23 and :32, pinned
        # by tests/test_host_config_path.py). The first version of this fixture
        # isolated by XDG_CONFIG_HOME, which was testing a path the host never
        # writes. The layout below is the host's: $HOME/.config/omarchy/.
        self.home = pathlib.Path(self.tmp.name) / "home"
        self.config_home = self.home / ".config"
        self.dir = self.config_home / "omarchy"
        self.dir.mkdir(mode=0o755, parents=True)
        self.path = self.dir / "shell.json"
        # Some of the host's real content, so a verb that wrote would be
        # caught by the byte comparison rather than by an empty-file guess.
        self.body = '{"bar":{"layout":{"center":[{"id":"io.github.rmcdavid.iptv"}]}}}\n'

    def write(self, mode, body=None):
        self.path.write_text(self.body if body is None else body, encoding="utf-8")
        os.chmod(self.path, mode)
        return self.path

    def mode(self, path=None):
        return stat.S_IMODE((path or self.path).lstat().st_mode)

    def shield(self, config_home=None, cwd=None, env=None):
        """Run the real verb as a child process, the way the service does."""
        merged = dict(os.environ)
        base = self.config_home if config_home is None else pathlib.Path(str(config_home))
        merged["HOME"] = str(base.parent if str(base) not in ("", ".") else base)
        # Set deliberately WRONG, so every run of every case re-proves that the
        # helper ignores it. If it ever starts honouring it again, these go red
        # rather than silently testing the wrong file.
        merged["XDG_CONFIG_HOME"] = str(pathlib.Path(self.tmp.name) / "xdg-must-be-ignored")
        if env:
            merged.update(env)
        completed = subprocess.run([sys.executable, str(HELPER), "config", "shield"],
                                   capture_output=True, text=True, env=merged,
                                   cwd=cwd, timeout=30)
        payload = None
        if completed.stdout.strip():
            payload = json.loads(completed.stdout.strip().splitlines()[-1])
        return completed.returncode, payload, completed.stderr

    def in_process(self, config_home=None):
        """Call the shipping function directly, for the races a child cannot
        be made to lose on command. The patches below are on `os`, so what
        runs is the real shield_host_config over a real file."""
        base = self.config_home if config_home is None else pathlib.Path(str(config_home))
        with mock.patch.dict(os.environ,
                             {"HOME": str(base.parent),
                              "XDG_CONFIG_HOME": str(pathlib.Path(self.tmp.name) / "xdg-must-be-ignored")}):
            return helper.shield_host_config()


class VocabularyJoinTest(unittest.TestCase):
    """The helper and Model.js are joined by verdict STRINGS (rule 13)."""

    def test_the_fixture_is_the_helpers_verdict_list(self):
        named = [row["verdict"] for row in VECTORS["verdicts"]]
        self.assertEqual(sorted(named), sorted(helper.CONFIG_SHIELD_VERDICTS))
        self.assertEqual(len(named), len(set(named)))

    def test_the_fixture_agrees_on_which_verdicts_mean_private(self):
        private = sorted(row["verdict"] for row in VECTORS["verdicts"] if row["private"])
        self.assertEqual(private, sorted(helper.CONFIG_SHIELD_PRIVATE_VERDICTS))
        # And it is exactly one, which is the point: "private" is the only
        # answer that lets a credential be written.
        self.assertEqual(private, ["private"])

    def test_the_unknown_verdict_is_genuinely_unknown(self):
        # The fixture's fail-closed probe must not accidentally name a real
        # verdict, or the node check it feeds proves nothing.
        self.assertNotIn(VECTORS["unknownVerdict"], helper.CONFIG_SHIELD_VERDICTS)


class ShieldModeTest(ShieldTestCase):
    def test_0644_becomes_0600_and_the_contents_do_not_move(self):
        self.write(0o644)
        before = self.path.read_bytes()
        mtime = self.path.lstat().st_mtime_ns
        code, payload, _ = self.shield()
        self.assertEqual(code, 0)
        self.assertEqual(self.mode(), 0o600)
        self.assertEqual(payload["verdict"], "private")
        self.assertTrue(payload["private"])
        self.assertTrue(payload["changed"])
        self.assertEqual((payload["modeBefore"], payload["modeAfter"]), ("0644", "0600"))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.path.lstat().st_mtime_ns, mtime)

    def test_an_already_private_file_is_not_touched_at_all(self):
        self.write(0o600)
        # ctime moves on a chmod, so an unchanged ctime is the observation
        # that no chmod happened -- not a claim read off the payload.
        ctime = self.path.lstat().st_ctime_ns
        code, payload, err = self.shield()
        self.assertEqual(code, 0)
        self.assertEqual(payload["verdict"], "private")
        self.assertFalse(payload["changed"])
        self.assertEqual((payload["modeBefore"], payload["modeAfter"]), ("0600", "0600"))
        self.assertEqual(self.path.lstat().st_ctime_ns, ctime)
        self.assertEqual(err, "")

    def test_it_clears_group_and_other_and_keeps_the_owner_bits(self):
        # Including the cases that are not 0644: group-read only, other-read
        # only, and a file somebody made executable.
        for before, after in ((0o640, 0o600), (0o604, 0o600), (0o666, 0o600),
                              (0o755, 0o700), (0o660, 0o600), (0o400, 0o400)):
            with self.subTest(before=oct(before)):
                self.write(before)
                code, payload, _ = self.shield()
                self.assertEqual(code, 0, payload)
                self.assertEqual(self.mode(), after)
                self.assertEqual(self.mode() & 0o077, 0)
                self.assertEqual(payload["changed"], before != after)

    def test_it_is_idempotent(self):
        self.write(0o644)
        first = self.shield()
        second = self.shield()
        self.assertEqual((first[0], second[0]), (0, 0))
        self.assertTrue(first[1]["changed"])
        self.assertFalse(second[1]["changed"])
        self.assertEqual(self.mode(), 0o600)

    def test_a_file_recreated_0644_is_caught_by_the_next_run(self):
        # The residual the service re-arms against: omarchy-refresh-config
        # copies the 0644 package default, and `cp -f` onto a file that is NOT
        # there gives the new file the umask's mode. One shield does not make
        # the file private for ever; the next one catches it.
        self.write(0o644)
        self.assertEqual(self.shield()[0], 0)
        self.assertEqual(self.mode(), 0o600)
        self.path.unlink()
        self.write(0o644)
        self.assertEqual(self.mode(), 0o644)
        code, payload, _ = self.shield()
        self.assertEqual(code, 0)
        self.assertTrue(payload["changed"])
        self.assertEqual(self.mode(), 0o600)


class ShieldRefusalTest(ShieldTestCase):
    def test_a_missing_file_is_refused_and_nothing_is_created(self):
        code, payload, err = self.shield()
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["private"])
        self.assertEqual(payload["verdict"], "absent")
        self.assertEqual(payload["error"]["code"], "config_absent")
        self.assertFalse(self.path.exists())
        self.assertIn("config shield", err)

    def test_a_directory_at_the_path_is_refused_and_left_alone(self):
        self.path.mkdir(mode=0o755)
        code, payload, _ = self.shield()
        self.assertEqual(code, 1)
        self.assertEqual(payload["verdict"], "not_regular")
        self.assertEqual(payload["error"]["code"], "config_not_regular")
        self.assertEqual(self.mode(), 0o755)

    def test_a_fifo_is_refused_without_blocking(self):
        # O_NONBLOCK is load-bearing: a plain O_RDONLY open of a FIFO waits
        # for a writer for ever, and this verb runs on the service's startup
        # path. The 30 s subprocess timeout is what would catch a regression.
        os.mkfifo(self.path, 0o644)
        code, payload, _ = self.shield()
        self.assertEqual(code, 1)
        self.assertEqual(payload["verdict"], "not_regular")
        self.assertEqual(self.mode(), 0o644)

    def test_a_symlink_is_refused_and_its_target_is_not_tightened(self):
        # The assertion that matters is the TARGET's mode: a chmod that
        # followed the link would read as success and silently change a file
        # the verb was never pointed at.
        target = pathlib.Path(self.tmp.name) / "elsewhere.json"
        target.write_text("{}", encoding="utf-8")
        os.chmod(target, 0o644)
        self.path.symlink_to(target)
        code, payload, _ = self.shield()
        self.assertEqual(code, 1)
        self.assertEqual(payload["verdict"], "symlink")
        self.assertEqual(payload["error"]["code"], "config_symlink")
        self.assertEqual(stat.S_IMODE(target.lstat().st_mode), 0o644)
        self.assertTrue(self.path.is_symlink())

    def test_a_symlink_to_a_private_file_is_still_refused(self):
        # Not "is the end state private" -- "is this file ours to change".
        target = pathlib.Path(self.tmp.name) / "private.json"
        target.write_text("{}", encoding="utf-8")
        os.chmod(target, 0o600)
        self.path.symlink_to(target)
        code, payload, _ = self.shield()
        self.assertEqual((code, payload["verdict"]), (1, "symlink"))

    @unittest.skipUnless(packaged_is_foreign(),
                         "needs the root-owned packaged default at %s" % PACKAGED_FILE)
    def test_a_file_owned_by_another_user_is_refused_untouched(self):
        """Driven in process, because the path comes from $HOME now and a
        root-owned file cannot be placed at $HOME/.config/omarchy/shell.json
        without root. The patch is on the fstat the shipping code performs, so
        the real shield runs over a real file and only the reported owner is
        forced."""
        self.write(0o644)
        real_fstat = os.fstat

        def foreign_fstat(fd):
            st = real_fstat(fd)
            return os.stat_result((st.st_mode, st.st_ino, st.st_dev, st.st_nlink,
                                   st.st_uid + 1, st.st_gid, st.st_size,
                                   int(st.st_atime), int(st.st_mtime), int(st.st_ctime)))

        with mock.patch.object(os, "fstat", side_effect=foreign_fstat):
            payload = self.in_process()
        self.assertEqual(payload["verdict"], "foreign")
        self.assertFalse(payload["changed"])
        self.assertEqual(self.mode(), 0o644, "a file we refused was modified anyway")
    def test_ownership_is_decided_by_the_effective_uid(self):
        # The same refusal without needing a root-owned file: our own file
        # seen by a process whose euid is somebody else's.
        self.write(0o644)
        with mock.patch.object(os, "geteuid", return_value=os.geteuid() + 1):
            result = self.in_process()
        self.assertEqual(result["verdict"], "foreign")
        self.assertFalse(result["private"])
        self.assertEqual(self.mode(), 0o644)

    def test_a_chmod_that_fails_reports_exposed_rather_than_success(self):
        self.write(0o644)

        def refuse(fd, mode):
            raise OSError(errno.EPERM, os.strerror(errno.EPERM))

        with mock.patch.object(os, "fchmod", side_effect=refuse):
            result = self.in_process()
        self.assertEqual(result["verdict"], "exposed")
        self.assertFalse(result["private"])
        self.assertFalse(result["changed"])
        self.assertEqual(result["code"], "config_unsafe")
        self.assertEqual(self.mode(), 0o644)

    def test_a_chmod_that_silently_does_nothing_reports_exposed(self):
        # The read-back, not the return value: fchmod is asked for 0600 and
        # the mode afterwards is read from the kernel. A no-op chmod must not
        # be reported as a private file.
        self.write(0o644)
        with mock.patch.object(os, "fchmod", return_value=None):
            result = self.in_process()
        self.assertEqual(result["verdict"], "exposed")
        self.assertEqual(result["modeAfter"], "0644")
        self.assertEqual(self.mode(), 0o644)


class ShieldRaceTest(ShieldTestCase):
    """The file being replaced between the check and the read-back."""

    def swap_in_fchmod(self, times):
        """Rename a fresh 0644 file over the path from inside fchmod, which is
        exactly where the host's own atomic writer would land."""
        real = os.fchmod
        state = {"left": times}

        def swapping(fd, mode):
            real(fd, mode)
            if state["left"] > 0:
                state["left"] -= 1
                other = self.dir / "incoming.json"
                other.write_text(self.body, encoding="utf-8")
                os.chmod(other, 0o644)
                os.replace(other, self.path)

        return swapping

    def test_a_replacement_is_reported_rather_than_claimed_private(self):
        self.write(0o644)
        with mock.patch.object(os, "fchmod", side_effect=self.swap_in_fchmod(99)):
            result = self.in_process()
        self.assertEqual(result["verdict"], "replaced")
        self.assertFalse(result["private"])
        self.assertEqual(result["code"], "config_replaced")
        # Bounded, and the bound is the one the constant names.
        self.assertEqual(result["attempts"], helper.CONFIG_SHIELD_ATTEMPTS)

    def test_a_single_replacement_is_retried_and_wins(self):
        self.write(0o644)
        with mock.patch.object(os, "fchmod", side_effect=self.swap_in_fchmod(1)):
            result = self.in_process()
        self.assertEqual(result["verdict"], "private")
        self.assertTrue(result["private"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(self.mode(), 0o600)

    def swap_a_symlink_to_our_own_inode(self):
        """Replace the path with a symlink pointing at the very inode we just
        tightened. `os.stat` would compare EQUAL through that link; `os.lstat`
        does not, and that is the whole reason _same_inode uses lstat."""
        real = os.fchmod

        def swapping(fd, mode):
            real(fd, mode)
            keep = self.dir / "kept.json"
            if not keep.exists():
                os.link(self.path, keep)
                self.path.unlink()
                self.path.symlink_to(keep)

        return swapping

    def test_a_symlink_to_our_own_inode_does_not_count_as_unchanged(self):
        # One attempt, so what is asserted is the single pass's own answer:
        # it must say "replaced" rather than "private". With stat in place of
        # lstat this reads as private and a credential goes into a file
        # anybody who can write the link can repoint.
        self.write(0o644)
        with mock.patch.object(helper, "CONFIG_SHIELD_ATTEMPTS", 1), \
             mock.patch.object(os, "fchmod", side_effect=self.swap_a_symlink_to_our_own_inode()):
            result = self.in_process()
        self.assertEqual(result["verdict"], "replaced")
        self.assertFalse(result["private"])
        self.assertEqual(result["attempts"], 1)

    def test_the_retry_re_resolves_the_name_and_reports_what_is_there_now(self):
        # With the real bound the second attempt opens the NAME again, meets
        # the symlink and refuses at O_NOFOLLOW. Either way: not private.
        self.write(0o644)
        with mock.patch.object(os, "fchmod", side_effect=self.swap_a_symlink_to_our_own_inode()):
            result = self.in_process()
        self.assertEqual(result["verdict"], "symlink")
        self.assertFalse(result["private"])
        self.assertEqual(result["attempts"], 2)
        self.assertIn(result["verdict"], helper.CONFIG_SHIELD_VERDICTS)


class ShieldPathTest(ShieldTestCase):
    def test_the_verb_takes_no_path(self):
        # The capability this verb deliberately does not own. A positional
        # path and the obvious flag spellings are all usage errors, with no
        # JSON on stdout.
        for extra in (["/etc/passwd"], ["--path", "/etc/passwd"],
                      ["--config-home", "/tmp"], ["--file", "/tmp/x"]):
            with self.subTest(extra=extra):
                completed = subprocess.run([sys.executable, str(HELPER), "config", "shield", *extra],
                                           capture_output=True, text=True, timeout=30)
                self.assertEqual(completed.returncode, 2, completed.stdout)
                self.assertEqual(completed.stdout.strip(), "")

    def test_config_without_an_action_is_a_usage_error(self):
        completed = subprocess.run([sys.executable, str(HELPER), "config"],
                                   capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 2)

    def test_home_decides_the_path_and_xdg_config_home_does_not(self):
        """The D-SINK-18 repair as the case that would otherwise have shipped.
        The HOST names its settings file from $HOME (shell.qml:23 and :32,
        pinned by tests/test_host_config_path.py), so the helper must too. On a
        machine where $XDG_CONFIG_HOME points elsewhere the first version
        tightened a decoy, reported success, and left the host's real file
        exposed."""
        self.write(0o644)
        decoy_home = pathlib.Path(self.tmp.name) / "xdg-must-be-ignored"
        (decoy_home / "omarchy").mkdir(mode=0o755, parents=True)
        decoy = decoy_home / "omarchy" / "shell.json"
        decoy.write_text("{}", encoding="utf-8")
        os.chmod(decoy, 0o644)
        code, payload, _ = self.shield()
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["verdict"], "private")
        self.assertEqual(self.mode(), 0o600)
        self.assertEqual(stat.S_IMODE(decoy.lstat().st_mode), 0o644,
                         "a moved XDG_CONFIG_HOME still steered the shield")
    def test_a_relative_home_does_not_resolve_against_the_working_directory(self):
        """What a relative value costs a verb that chmods: the file it changes
        would be chosen by whatever directory the shell was started in. The
        helper takes $HOME now, so the guard moves with it."""
        trap = pathlib.Path(self.tmp.name) / "cwd"
        (trap / ".config" / "omarchy").mkdir(mode=0o755, parents=True)
        bait = trap / ".config" / "omarchy" / "shell.json"
        bait.write_text("{}", encoding="utf-8")
        os.chmod(bait, 0o644)
        merged = dict(os.environ)
        merged["HOME"] = "."
        completed = subprocess.run([sys.executable, str(HELPER), "config", "shield"],
                                   capture_output=True, text=True, env=merged,
                                   cwd=str(trap), timeout=30)
        self.assertEqual(stat.S_IMODE(bait.lstat().st_mode), 0o644,
                         "a relative HOME was resolved against the working directory")
        self.assertIsNotNone(completed.returncode)
    def test_an_empty_home_falls_back_to_an_absolute_path_or_to_nothing(self):
        """Driven IN PROCESS with the password database patched, deliberately.

        Running the verb with HOME="" would fall back to the real passwd home
        and aim it at the developer's own ~/.config/omarchy/shell.json, which
        is the one file these tests must never touch. The first version of this
        test did exactly that. What matters is the rule, and the rule is
        checkable without going near it: an unusable HOME never yields a
        RELATIVE target, it yields an absolute one or none at all.
        """
        import pwd as pwdmod

        class Fake:
            pw_dir = "/somewhere/absolute"

        with mock.patch.dict(os.environ, {"HOME": ""}), \
             mock.patch.object(pwdmod, "getpwuid", return_value=Fake()):
            self.assertEqual(helper.host_config_path(),
                             "/somewhere/absolute/.config/omarchy/shell.json")

        class Relative:
            pw_dir = "relative/home"

        with mock.patch.dict(os.environ, {"HOME": ""}), \
             mock.patch.object(pwdmod, "getpwuid", return_value=Relative()):
            self.assertEqual(helper.host_config_path(), "",
                             "a relative passwd home produced a target anyway")

        with mock.patch.dict(os.environ, {"HOME": ""}), \
             mock.patch.object(pwdmod, "getpwuid", side_effect=KeyError("no such uid")):
            self.assertEqual(helper.host_config_path(), "")
class ShieldOutputTest(ShieldTestCase):
    """Rule 5 at this sink: a verdict and two modes, nothing else."""

    def test_the_payload_names_no_absolute_path_and_no_contents(self):
        secret = ('{"bar":{"layout":{"center":[{"id":"io.github.rmcdavid.iptv",'
                  '"playlistUrl":"https://user:s3cret@provider.test/get.php?username=u&password=p"}]}}}\n')
        self.write(0o644, body=secret)
        code, payload, err = self.shield()
        self.assertEqual(code, 0)
        blob = json.dumps(payload) + err
        for leak in ("s3cret", "password", "provider.test", "playlistUrl",
                     str(self.config_home), str(self.path), os.path.expanduser("~")):
            self.assertNotIn(leak, blob, leak)
        self.assertEqual(payload["file"], "omarchy/shell.json")
        self.assertEqual(self.path.read_text(encoding="utf-8"), secret)

    def test_every_outcome_has_the_same_shape_and_ok_mirrors_private(self):
        # Model.configShieldState reads `ok`, `private` and `verdict` and
        # demands all three agree; this is the end of that contract the helper
        # owns. Four real outcomes, no mocks.
        seen = {}
        self.write(0o644)
        seen["private"] = self.shield()
        self.path.unlink()
        seen["absent"] = self.shield()
        self.path.mkdir(mode=0o755)
        seen["not_regular"] = self.shield()
        self.path.rmdir()
        self.path.symlink_to(pathlib.Path(self.tmp.name) / "nothing")
        seen["symlink"] = self.shield()
        keys = ("ok", "kind", "action", "verdict", "private", "changed",
                "modeBefore", "modeAfter", "attempts", "file")
        for verdict, (code, payload, _) in seen.items():
            with self.subTest(verdict=verdict):
                self.assertEqual(payload["verdict"], verdict)
                self.assertEqual(payload["ok"], payload["private"])
                self.assertEqual(payload["ok"], code == 0)
                self.assertEqual(payload["kind"], "config")
                self.assertEqual(payload["action"], "shield")
                self.assertIn(payload["verdict"], helper.CONFIG_SHIELD_VERDICTS)
                for key in keys:
                    self.assertIn(key, payload)
                self.assertEqual("error" in payload, not payload["ok"])
        self.assertEqual(len(seen), 4)

    def test_a_changed_mode_is_announced_on_stderr_and_an_unchanged_one_is_not(self):
        # The plugin changed the mode of a file it does not own; the user
        # should be able to find that afterwards. An idempotent run is silent.
        self.write(0o644)
        _, _, loud = self.shield()
        self.assertIn("0644 -> 0600", loud)
        _, _, quiet = self.shield()
        self.assertEqual(quiet, "")

    def test_the_modes_are_read_back_from_the_kernel(self):
        # modeAfter is what the file IS, not what the chmod was asked for.
        self.write(0o640)
        _, payload, _ = self.shield()
        self.assertEqual(payload["modeAfter"], helper.mode_text(self.path.lstat().st_mode))
        self.assertEqual(payload["modeBefore"], "0640")


class ShieldHelperApiTest(ShieldTestCase):
    """The pieces Service.qml and the verb are built out of."""

    def test_host_config_path_is_the_hosts_file_under_home(self):
        """And $XDG_CONFIG_HOME does not move it, which is the whole repair."""
        with mock.patch.dict(os.environ, {"HOME": str(self.home),
                                          "XDG_CONFIG_HOME": "/tmp/not-where-the-host-writes"}):
            self.assertEqual(helper.host_config_path(), str(self.path))

    def test_mode_text_is_four_octal_digits(self):
        self.assertEqual([helper.mode_text(m) for m in (0o600, 0o644, 0o7, 0, 0o100644)],
                         ["0600", "0644", "0007", "0000", "0644"])

    def test_the_parent_directories_are_never_touched(self):
        # The owner's ruling, as an assertion: a 0600 file is sufficient
        # whatever the directory modes are, and ~/.config is shared with
        # everything on the system.
        self.write(0o644)
        before = [stat.S_IMODE(p.lstat().st_mode) for p in (self.dir, self.config_home)]
        self.assertEqual(self.shield()[0], 0)
        self.assertEqual([stat.S_IMODE(p.lstat().st_mode) for p in (self.dir, self.config_home)], before)
        self.assertEqual(before[0], 0o755)

    def test_the_file_is_never_opened_for_writing(self):
        # Observed at the syscall boundary rather than argued: every open of
        # the target carries O_RDONLY, and none carries a create or a write
        # flag. A verb that rewrote the host's config would be a far worse
        # defect than the one it is fixing.
        self.write(0o644)
        real = os.open
        flags = []

        def watching(path, flag, *rest, **kw):
            if str(path) == str(self.path):
                flags.append(flag)
            return real(path, flag, *rest, **kw)

        with mock.patch.object(os, "open", side_effect=watching):
            result = self.in_process()
        self.assertEqual(result["verdict"], "private")
        self.assertTrue(flags)
        for flag in flags:
            self.assertEqual(flag & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND), 0)
            self.assertTrue(flag & os.O_NOFOLLOW)
            self.assertTrue(flag & os.O_NONBLOCK)


class ShieldSubcommandContractTest(ShieldTestCase):
    def test_the_verb_is_listed_in_help(self):
        completed = subprocess.run([sys.executable, str(HELPER), "--help"],
                                   capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0)
        self.assertIn("config", completed.stdout)

    def test_an_unknown_config_action_is_a_usage_error(self):
        completed = subprocess.run([sys.executable, str(HELPER), "config", "unshield"],
                                   capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
