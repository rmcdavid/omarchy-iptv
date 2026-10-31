"""D-SINK-47, D-SINK-48 and D-SINK-50 (lane-p2a, 2026-10-29): what a helper run
puts on /proc/<pid>/cmdline, which every account on the computer reads.

The shell hands the helper its private arguments -- a cache folder named by a
key, the keys of the cache verbs, a channel id, a scope, the user's mpv tokens
-- in OMARCHY_IPTV_ARGS behind --args-from-env (Model.helperSpawn). These cases
hold the helper's half, helper_arguments, to the shared fixture
tests/fixtures/helper-args.json that tests/Model.test.js holds the model's half
to, and prove argparse reads the private form exactly as it read the argv the
builders made. The player's half -- the tokens in a private file mpv reads with
--include -- is pinned here at the writer (mode, atomicity, links) and observed
end to end in tests/test_player.py (StartTest) and the windowless rig.
"""
import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
helper = load_helper()
FIXTURE = json.loads((ROOT / "tests" / "fixtures" / "helper-args.json").read_text(encoding="utf-8"))


def namespace(argv):
    return vars(helper.build_parser().parse_args(argv))


class SharedFixtureTest(unittest.TestCase):
    def test_the_names_are_the_models(self):
        self.assertEqual((helper.ARGS_ENV, helper.ARGS_FLAG), (FIXTURE["env"], FIXTURE["flag"]))

    def test_every_case_reads_back_to_the_argv_argparse_is_given(self):
        for case in FIXTURE["cases"]:
            env = {"KEEP": "1"}
            if case["private"]:
                env[FIXTURE["env"]] = json.dumps(case["private"])
            got = helper.helper_arguments(case["command"][3:], env)
            self.assertEqual(got, case["parsed"][3:], case["name"])
            # Taken OUT of the environment on every run, so no child inherits it.
            self.assertEqual(env, {"KEEP": "1"}, case["name"])

    def test_argparse_reads_the_private_form_exactly_as_the_argv_the_builder_made(self):
        for case in FIXTURE["cases"]:
            self.assertEqual(namespace(case["parsed"][3:]), namespace(case["argv"][3:]), case["name"])

    def test_no_private_value_is_on_a_command(self):
        for case in FIXTURE["cases"]:
            left = [item for item in case["private"] if item and item in case["command"]]
            self.assertEqual(left, [], case["name"])
            self.assertEqual(case["command"].count(FIXTURE["flag"]), 1 if case["private"] else 0, case["name"])

    def test_a_doubled_flag_is_refused_and_the_list_still_removed(self):
        # One flag, one list: an argv carrying the flag twice was composed by
        # something other than helperSpawn, and the run stops rather than
        # guess which half of it the list belongs to.
        env = {FIXTURE["env"]: json.dumps(["--id", "t:x"])}
        with self.assertRaises(helper.HelperError) as caught:
            helper.helper_arguments(["play", FIXTURE["flag"], FIXTURE["flag"]], env)
        self.assertEqual(caught.exception.code, "bad_arguments")
        self.assertEqual(env, {})

    def test_without_the_flag_the_environment_is_ignored_and_still_removed(self):
        env = {FIXTURE["env"]: json.dumps(["--id", "t:evil"])}
        self.assertEqual(helper.helper_arguments(["play", "--id", "t:x"], env), ["play", "--id", "t:x"])
        self.assertEqual(env, {})


class OptionsFileTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-args-")
        os.chmod(self.dir, 0o700)
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, True))
        self.path = os.path.join(self.dir, helper.MPV_ARGS_FILE)

    def test_the_file_is_private_whole_and_replaces_what_was_there(self):
        before = os.umask(0o000)
        try:
            helper.write_mpv_args(self.path, ["--volume=50", "--no-osc"])
        finally:
            os.umask(before)
        st = os.lstat(self.path)
        self.assertTrue(stat.S_ISREG(st.st_mode))
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)
        self.assertEqual(pathlib.Path(self.path).read_text(encoding="utf-8"), "volume=%2%50\nno-osc\n")
        helper.write_mpv_args(self.path, ["--fullscreen"])
        self.assertEqual(pathlib.Path(self.path).read_text(encoding="utf-8"), "fullscreen\n")
        self.assertEqual(sorted(os.listdir(self.dir)), [helper.MPV_ARGS_FILE])

    def test_a_link_at_the_name_is_replaced_never_written_through(self):
        target = os.path.join(self.dir, "elsewhere")
        pathlib.Path(target).write_text("theirs\n", encoding="utf-8")
        os.symlink(target, self.path)
        helper.write_mpv_args(self.path, ["--volume=50"])
        self.assertFalse(os.path.islink(self.path))
        self.assertEqual(pathlib.Path(target).read_text(encoding="utf-8"), "theirs\n")
        temp = os.path.join(self.dir, ".%s.%d" % (helper.MPV_ARGS_FILE, os.getpid()))
        os.symlink(target, temp)
        helper.write_mpv_args(self.path, ["--volume=40"])
        self.assertEqual(pathlib.Path(target).read_text(encoding="utf-8"), "theirs\n")
        self.assertEqual(pathlib.Path(self.path).read_text(encoding="utf-8"), "volume=%2%40\n")

    def test_the_length_is_counted_in_utf8_bytes(self):
        self.assertEqual(helper.mpv_args_config(["--user-agent=caf\u00e9 \u2603"]),
                         "user-agent=%9%caf\u00e9 \u2603\n")      # 3 + 2 + 1 + 3 bytes
        self.assertEqual(helper.mpv_args_config(["--user-agent="]), "user-agent=%0%\n")

    def test_a_line_break_or_a_nul_never_reaches_the_file(self):
        for token in ("--title=x\n", "--volume=5\ntls-verify=no", "--a=b\rc", "--a=b\0c"):
            kept, rejected = helper.filter_mpv_args([token])
            self.assertEqual((kept, rejected), ([], [token]), repr(token))
            with self.assertRaises(helper.HelperError):
                helper.mpv_args_config([token])

    def test_a_lone_surrogate_never_reaches_the_file(self):
        # The NUL's sibling: no UTF-8 file can hold a lone surrogate. A byte
        # the argv could not decode arrives as one (U+DC80-U+DCFF), and so
        # does a JSON \ud800 escape in OMARCHY_IPTV_ARGS; the writer met one
        # and raised UnicodeEncodeError, so the start ended `internal`. A
        # PAIRED character is UTF-8 and is kept.
        for token in ("--user-agent=a\udcffb", "--sub-font=x\ud800", "--title-x=\ude00\ud83d"):
            kept, rejected = helper.filter_mpv_args([token])
            self.assertEqual((kept, rejected), ([], [token]), repr(token))
            with self.assertRaises(helper.HelperError):
                helper.mpv_args_config([token])
        astral = "--sub-font=café\U0001f600"
        self.assertEqual(helper.filter_mpv_args([astral]), ([astral], []))
        self.assertEqual(helper.mpv_args_config([astral]), "sub-font=%9%café\U0001f600\n")

    def test_remove_is_quiet_and_complete(self):
        helper.write_mpv_args(self.path, ["--volume=50"])
        helper.remove_mpv_args(self.path)
        helper.remove_mpv_args(self.path)
        self.assertFalse(os.path.lexists(self.path))


if __name__ == "__main__":
    unittest.main()
