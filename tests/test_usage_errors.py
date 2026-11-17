"""D-SINK-106 and D-SINK-107's journal half (2026-11-16): what a refused
command line and two journal lines print.

D-SINK-106. argparse's own error() printed the message it composed, and that
message quotes what did not parse: an unknown flag with the value after it,
a number it could not read, a choice, an ambiguous prefix with its
`=value`. The shell hands `player start` and `player restart` their private
arguments in OMARCHY_IPTV_ARGS and writes the helper's stderr to the
journal, so a usage error put a value the argv was kept free of there whole.
Every parser of the helper is now a HelperArgumentParser, whose error()
prints the static usage and one line naming the kind of error (from a fixed
table, matched on argparse's own templates) and at most three option strings
the helper DEFINES that the message holds: never a value, an unknown
option-shaped token included. Exit 2 and no stdout reply, as before. Its
sibling: a private argument list the helper refuses (`bad_arguments`) was
answered as the first argv item that is not an option, whatever it was, in
the reply's `kind` and the journal line; now only one of the helper's verbs,
else "helper".

D-SINK-107, the journal half. `find_channel`'s refusal said `channel <id> is
not in the playlist cache`, and the stand-down note named both channels' ids.
A `u:` id is an unkeyed 32-bit hash of the stream's address, credentials and
all, and both lines reach the journal. Neither names an id now; the replies
still carry them.

Every value below is synthetic (`qqqqqq`, `zzzzzz`, `.test` hosts).
"""
import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from helper_loader import HELPER, load_helper

helper = load_helper()

SECRETS = ("qqqqqq", "zzzzzz", "Bearer", "Authorization", "retired-flag", "http-header-fields", "d4c55ad5",
           "0badf00d", "cdn.test")


class HelperRun(unittest.TestCase):
    """Runs the shipping helper as the shell does, as a process, with a
    scratch runtime and cache: no verb here gets as far as doing anything,
    and if one did it would find only these folders."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="usage-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.runtime = os.path.join(self.dir, "rt")
        os.mkdir(self.runtime, 0o700)
        self.cache = os.path.join(self.dir, "cache")
        self.sock = os.path.join(self.runtime, "mpv.sock")

    def helper(self, *argv, private=None):
        env = {k: v for k, v in os.environ.items() if k != helper.ARGS_ENV}
        env["XDG_RUNTIME_DIR"] = self.runtime
        env["XDG_CACHE_HOME"] = self.cache
        if private is not None:
            env[helper.ARGS_ENV] = json.dumps(private)
        done = subprocess.run([sys.executable, "-I", str(HELPER), *argv], env=env, capture_output=True,
                              text=True, timeout=60, stdin=subprocess.DEVNULL)
        return done.returncode, done.stdout, done.stderr

    def refused(self, *argv, private=None):
        """A usage error: exit 2, nothing on stdout, and stderr's last line,
        which must hold no secret."""
        code, out, err = self.helper(*argv, private=private)
        self.assertEqual(code, helper.EXIT_USAGE, err)
        self.assertEqual(out, "", out)
        for secret in SECRETS:
            self.assertNotIn(secret, err, (argv, private))
        line = err.strip().splitlines()[-1]
        self.assertTrue(line.endswith("; the values given are not shown"), line)
        return line, err


class UsageErrorTest(HelperRun):

    def test_an_unknown_flag_in_the_private_list_is_not_echoed_with_its_value(self):
        # (a), the shape the shell can really send: a token an older shell's
        # builder still passes, with a credential-shaped value after it.
        line, _ = self.refused("player", "start", "--args-from-env",
                               private=["--id", "u:d4c55ad5", "--cache-dir", self.cache, "--socket", self.sock,
                                        "--retired-flag", "g:qqqqqq:zzzzzz@cdn.test"])
        self.assertEqual(line, "omarchy-iptv: error: unrecognized arguments; the values given are not shown")
        self.assertFalse(os.path.exists(self.sock))

    def test_an_unreadable_number_names_its_option_and_not_the_value(self):
        # (b), on the command line and in the private list.
        line, _ = self.refused("play", "--id", "t:a", "--since", "qqqqqq:zzzzzz")
        self.assertEqual(line, "omarchy-iptv play: error: invalid value (--since); the values given are not shown")
        line, _ = self.refused("player", "start", "--args-from-env",
                               private=["--id", "u:d4c55ad5", "--socket", self.sock, "--since", "qqqqqq:zzzzzz"])
        self.assertEqual(line, "omarchy-iptv player start: error: invalid value (--since); "
                               "the values given are not shown")

    def test_an_invalid_choice_names_no_value(self):
        # (c), a verb, an action and a positional choice.
        for argv, prog in ((("qqqqqq:zzzzzz",), "omarchy-iptv"),
                           (("state", "qqqqqq:zzzzzz"), "omarchy-iptv state"),
                           (("failed", "zzzzzz", "--cache-dir", self.cache), "omarchy-iptv failed")):
            with self.subTest(argv=argv):
                line, _ = self.refused(*argv)
                self.assertEqual(line, "%s: error: invalid choice; the values given are not shown" % prog)

    def test_a_missing_required_option_is_named(self):
        # (d)
        line, _ = self.refused("player", "relay")
        self.assertEqual(line, "omarchy-iptv player relay: error: the following arguments are required (--child); "
                               "the values given are not shown")
        line, _ = self.refused("player", "orphan-check", "--socket", self.sock)
        self.assertIn("(--owner-pid)", line)

    def test_a_header_token_on_a_verb_that_takes_none_is_not_echoed(self):
        # (e): `player probe` takes no --mpv-arg; the option is the helper's
        # own (start's), so it is named, and nothing after its `=` is.
        line, _ = self.refused("player", "probe", "--socket", self.sock,
                               "--mpv-arg=--http-header-fields=Authorization: Bearer zzzzzz")
        self.assertEqual(line, "omarchy-iptv: error: unrecognized arguments (--mpv-arg); the values given are not shown")

    def test_a_value_that_starts_with_a_dash_is_never_named(self):
        # (f): an option-shaped value is a value. Only strings the helper
        # defines are named, so `-qqqqqq` and `--zzzzzz` are not.
        for argv in (("play", "--id", "t:a", "--since=-qqqqqq"),
                     ("play", "--id", "t:a", "--since", "-qqqqqq"),
                     ("play", "--id", "t:a", "--since=--zzzzzz"),
                     ("play", "--id", "t:a", "--zzzzzz-qqqqqq"),
                     ("player", "probe", "--socket", self.sock, "-qqqqqq")):
            with self.subTest(argv=argv):
                line, _ = self.refused(*argv)
                names = line.split("(", 1)[1].split(")", 1)[0].split(", ") if "(" in line else []
                for name in names:
                    self.assertIn(name, helper.defined_option_strings(helper.build_parser()), line)

    def test_an_ambiguous_prefix_names_only_options_it_could_be(self):
        line, _ = self.refused("player", "start", "--s=qqqqqq:zzzzzz", "--id", "t:a", "--socket", self.sock)
        self.assertTrue(line.startswith("omarchy-iptv player start: error: ambiguous option ("), line)
        names = line.split("(", 1)[1].split(")", 1)[0].split(", ")
        self.assertLessEqual(len(names), helper.USAGE_ERROR_MAX_NAMES)
        for name in names:
            self.assertTrue(name.startswith("--s"), name)

    def test_options_that_exclude_each_other_are_named_without_their_values(self):
        line, _ = self.refused("play", "--id", "t:qqqqqq", "--url", "http://zzzzzz@cdn.test/x")
        self.assertEqual(line, "omarchy-iptv play: error: these options cannot be given together (--url, --id); "
                               "the values given are not shown")

    def test_the_whole_of_stderr_is_the_same_whatever_the_value(self):
        # Nothing of a value reaches stderr at all, the usage included: two
        # refusals that differ only in the value print the same bytes.
        _, first = self.refused("play", "--id", "t:a", "--since", "qqqqqq")
        _, second = self.refused("play", "--id", "t:a", "--since", "zzzzzz:zzzzzz@cdn.test")
        self.assertEqual(first, second)
        _, first = self.refused("player", "start", "--args-from-env",
                                private=["--id", "t:a", "--socket", self.sock, "--retired-flag", "qqqqqq"])
        _, second = self.refused("player", "start", "--args-from-env",
                                 private=["--id", "t:a", "--socket", self.sock, "--retired-flag", "zzzzzz@cdn.test"])
        self.assertEqual(first, second)

    def test_a_refused_private_list_is_answered_as_a_verb_never_as_a_value(self):
        # The sibling: `bad_arguments` named the first non-option item.
        code, out, err = self.helper("qqqqqq:zzzzzz", "--args-from-env")
        self.assertEqual(code, helper.EXIT_USAGE, err)
        reply = json.loads(out.strip().splitlines()[-1])
        self.assertEqual((reply["kind"], reply["error"]["code"]), ("helper", "bad_arguments"))
        self.assertEqual(err, "omarchy-iptv: helper: --args-from-env was given and $%s is not set\n" % helper.ARGS_ENV)
        code, out, err = self.helper("--socket", "/run/qqqqqq.sock", "player", "start", "--args-from-env")
        self.assertEqual(json.loads(out.strip().splitlines()[-1])["kind"], "helper")
        self.assertNotIn("qqqqqq", out + err)
        # A verb the helper has is still its own kind, as the shell reads it.
        code, out, err = self.helper("player", "start", "--args-from-env")
        self.assertEqual(json.loads(out.strip().splitlines()[-1])["kind"], "player")


class UsageErrorPartsTest(unittest.TestCase):
    """The decisions on their own, called directly."""

    def test_every_parser_in_the_tree_is_the_helpers(self):
        # add_subparsers builds each verb's parser with the class of the one
        # it hangs off, so this holds while the root is one and no
        # add_subparsers names another class.
        pending, seen = [helper.build_parser()], 0
        while pending:
            parser = pending.pop()
            seen += 1
            self.assertIsInstance(parser, helper.HelperArgumentParser, parser.prog)
            for action in parser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    pending.extend(action.choices.values())
        self.assertGreater(seen, 30)

    def test_names_are_defined_whole_words_at_most_three_in_message_order(self):
        defined = frozenset(("--since", "--id", "--url", "--scope", "-h"))
        names = helper.usage_error_names
        self.assertEqual(names("unrecognized arguments: --url x --id y --since z --scope w", defined),
                         ["--url", "--id", "--since"])
        self.assertEqual(names("unrecognized arguments: --sincere x--since --since_x --since-x", defined), [])
        self.assertEqual(names("argument --since: invalid int value: '--zzzzzz'", defined), ["--since"])
        self.assertEqual(names("ambiguous option: --s=--id could match --since, --scope", defined),
                         ["--id", "--since", "--scope"])
        self.assertEqual(names("unrecognized arguments: --http-header-fields=a -hx", defined), [])

    def test_the_kind_is_the_tables_and_a_value_cannot_choose_it(self):
        kind = helper.usage_error_kind
        self.assertEqual(kind("argument --since: invalid int value: 'unrecognized arguments: x'"), "invalid value")
        self.assertEqual(kind("unrecognized arguments: invalid choice: x"), "unrecognized arguments")
        self.assertEqual(kind("argument command: invalid choice: 'x' (choose from a, b)"), "invalid choice")
        self.assertEqual(kind("argument --owner-token: not an owner token (32 lowercase hex digits)"),
                         helper.USAGE_ERROR_DEFAULT_KIND)
        for start, phrase in helper.USAGE_ERROR_KINDS:
            self.assertEqual(kind("argument --x: " + start + "qqqqqq"), phrase)
            self.assertNotIn("qqqqqq", phrase)

    def test_the_line_holds_nothing_of_the_message_but_defined_names(self):
        defined = helper.defined_option_strings(helper.build_parser())
        line = helper.usage_error_line("omarchy-iptv play", "argument --since: invalid int value: 'qqqqqq'", defined)
        self.assertEqual(line, "omarchy-iptv play: error: invalid value (--since); the values given are not shown\n")

    def test_an_error_called_in_process_exits_2_and_writes_only_stderr(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                self.assertRaises(SystemExit) as caught:
            helper.main(["play", "--id", "t:a", "--since", "qqqqqq:zzzzzz"])
        self.assertEqual(caught.exception.code, helper.EXIT_USAGE)
        self.assertEqual(out.getvalue(), "")
        self.assertNotIn("qqqqqq", err.getvalue())
        self.assertTrue(err.getvalue().startswith("usage: omarchy-iptv play "), err.getvalue())


class JournalIdTest(HelperRun):
    """D-SINK-107's journal half."""

    def test_an_unknown_channel_is_refused_without_its_id_in_the_sentence(self):
        directory = os.path.join(self.cache, "omarchy-iptv")
        os.makedirs(directory, 0o700)
        with open(os.path.join(directory, helper.CHANNELS_FILE), "w", encoding="utf-8") as fh:
            json.dump({"channels": [{"id": "t:news.test", "name": "News", "url": "http://cdn.test/n.ts"}]}, fh)
        code, out, err = self.helper("play", "--id", "u:d4c55ad5x", "--cache-dir", directory, "--socket", self.sock,
                                     "--ipc-timeout", "1")
        self.assertEqual(code, helper.EXIT_ERROR, err)
        reply = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(reply["error"]["code"], "unknown_channel")
        self.assertNotIn("d4c55ad5", reply["error"]["message"])
        self.assertNotIn("d4c55ad5", err)
        self.assertEqual(err, "omarchy-iptv: play: the channel asked for is not in the playlist cache\n")
        # The reply still says which channel was asked for.
        self.assertEqual(reply["id"], "u:d4c55ad5x")
        with self.assertRaises(helper.HelperError) as caught:
            helper.find_channel([{"id": "u:0badf00d"}], "u:d4c55ad5")
        self.assertNotIn("d4c55ad5", caught.exception.message)

    def test_the_stand_down_note_compares_the_pair_and_names_neither(self):
        note = helper.stand_down_note
        other = note(9, {"id": "u:d4c55ad5"}, {"id": "u:0badf00d", "verb": "play", "entryId": 1})
        self.assertEqual(other, "a newer channel change reached the player first (intent 9 would have applied this "
                                "start's channel; the player is on another channel, written by play as entry 1); "
                                "left it playing")
        same = note(9, {"id": "u:d4c55ad5"}, {"id": "u:d4c55ad5", "verb": "play", "entryId": 1})
        self.assertIn("the player is on that same channel, written by play as entry 1", same)
        unnamed = note(0, {"id": ""}, {"id": "u:0badf00d", "verb": "play"})
        self.assertIn("it would have applied an unnamed stream; the player is on another channel", unnamed)
        for line in (other, same, unnamed):
            self.assertNotIn("d4c55ad5", line)
            self.assertNotIn("0badf00d", line)


if __name__ == "__main__":
    unittest.main()
