"""Restart on adoption (owner, 2026-10-31 and 2026-11-01): which build
launched the player a connection reaches.

The launch argv names the build (`player_build`, one script-opts key, version
and checksum only), and `launch_verdict` reads a process's /proc/<pid>/cmdline
back as bytes: "current" when the tail from our socket token BEGINS with what
this build composes (either form; the screenshot folder tolerated), whatever
a user's `mpv` wrapper appends after it but a second socket option (D-PLY-61),
"older" for any other launch of ours, "unknown" when there is nothing of ours
to read.
Every case here is judged on a REAL process, whose command line the kernel
reports, never on a list handed to the function: the shape the verdict reads
is the one the kernel keeps (measured on mpv 0.41.0 by lane RA's M1, byte for
byte, both forms).

The vectors are tests/fixtures/player-launch.json; the older shapes in it are
each tag's own composition, never the verdict's (design 17.8).

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import zlib
from unittest import mock

from helper_loader import load_helper

helper = load_helper()

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "player-launch.json"
VECTORS = json.loads(FIXTURE.read_text(encoding="utf-8"))
HOLDER = "import time\ntime.sleep(30)\n"


def edited(argv, edit, fill=lambda a: a):
    """`argv` with the case's edit applied; `fill` resolves the fixture's
    placeholders in the elements the edit brings in (an appended
    `--input-ipc-server=__SOCK__`, D-PLY-61)."""
    out = list(argv)
    if not edit:
        return out
    if "replace" in edit:
        prefix, element = edit["replace"]
        at = next(i for i, a in enumerate(out) if a.startswith(prefix))
        out[at] = fill(element)
    if "drop" in edit:
        out.remove(edit["drop"])
    # rc-sk72: the prefix rule's edges -- an element moved to the end, the
    # tail cut short from the end or down to its first elements.
    if "move" in edit:
        at = next(i for i, a in enumerate(out) if a.startswith(edit["move"]))
        out.append(out.pop(at))
    if "pop" in edit:
        del out[len(out) - int(edit["pop"]):]
    if "keep" in edit:
        del out[int(edit["keep"]):]
    if "append" in edit:
        out += [fill(a) for a in edit["append"]]
    return out


class LaunchCase(unittest.TestCase):
    """A scratch socket folder (under /tmp: AF_UNIX's 108 bytes), its state
    folder, and holder processes reaped at cleanup."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-launch-", dir="/tmp")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.runtime = os.path.join(self.dir, "run")
        os.makedirs(self.runtime, 0o700)
        self.sock = os.path.join(self.runtime, "mpv.sock")
        self.holder = os.path.join(self.dir, "holder.py")
        pathlib.Path(self.holder).write_text(HOLDER, encoding="utf-8")

    def hold(self, argv, sock=None):
        """A process whose command line is `python3 <holder>` and then
        `argv`: everything before our socket token is ignored by the verdict,
        so the two leading elements change nothing about it. Returned once
        the kernel reports the command line (F-HARNESS-41: briefly empty
        after exec)."""
        process = subprocess.Popen([sys.executable, self.holder] + list(argv), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.reap, process)
        want = os.fsencode(self.holder)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                with open("/proc/%d/cmdline" % process.pid, "rb") as handle:
                    if want in handle.read().split(b"\0"):
                        break
            except OSError:
                pass
            time.sleep(0.005)
        return process

    @staticmethod
    def reap(process):
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)

    def current_tail(self, include, sock=None):
        sock = sock or self.sock
        return helper.mpv_launch_argv(sock, ["--x"] if include else [], helper.player_dirs(sock))[1:]

    def case_argv(self, case, sock=None):
        sock = sock or self.sock
        fill = lambda a: (a.replace("__SOCK__", sock).replace("__RUNTIME__", os.path.dirname(sock))
                          .replace("__STATE__", helper.state_dir()))
        if "shape" in case:
            return edited([fill(a) for a in VECTORS["older"][case["shape"]]], case.get("edit"), fill)
        return list(case["prefix"]) + edited(self.current_tail(case["include"], sock), case.get("edit"), fill)


class LaunchVerdictVectorTest(LaunchCase):

    def test_every_vector_reads_as_the_fixture_says_on_a_real_process(self):
        cases = VECTORS["cases"]
        got = []
        for case in cases:
            try:
                argv = self.case_argv(case)
            except StopIteration:
                # an edit whose element this build no longer composes: say so
                # in the comparison rather than stopping before the others
                got.append("%s: cannot be built" % case["name"])
                continue
            process = self.hold(argv)
            got.append("%s: %s" % (case["name"], helper.launch_verdict(process.pid, self.sock)))
        self.assertEqual(got, ["%s: %s" % (c["name"], c["verdict"]) for c in cases])
        # The fixture keeps the cases that make each mutant of the verdict
        # visible (the lane's report runs them): an older argv from a REAL
        # release, a pin removed, a foreign screenshot folder, a prepending
        # wrapper, both option-file forms -- and, since D-PLY-61, a wrapper's
        # tokens appended after each form (current), the same appended after
        # an older argv, after a change inside the tail and after another
        # build's marker (older), and a second socket option in two
        # spellings (older). And (rc-sk72) the prefix rule's edges, each
        # older: the composition's last element replaced or run on into a
        # longer one, an element moved, the tail cut short -- red under the
        # comparison read off by one, order-blind or as joined bytes.
        verdicts = [c["verdict"] for c in cases]
        self.assertGreaterEqual(verdicts.count("current"), 7)
        self.assertGreaterEqual(verdicts.count("older"), 16)
        self.assertIn("unknown", verdicts)
        appended = [c["verdict"] for c in cases if "append" in c.get("edit", {})]
        self.assertGreaterEqual(appended.count("current"), 2)
        self.assertGreaterEqual(appended.count("older"), 8)
        edges = [c["verdict"] for c in cases if {"move", "pop", "keep"} & set(c.get("edit", {}))]
        self.assertEqual(edges, ["older"] * 5)

    def test_the_older_shapes_are_the_tags_own_and_differ_from_this_build_only_where_they_should(self):
        """v0.16.0's argv is this tree's less the marker (the shapes were
        composed by v0.16.0's own helper), so the marker is what tells them
        apart; v0.15.0's carries its user token on the argv itself."""
        older = VECTORS["older"]
        mine = [a for a in self.case_argv({"prefix": ["mpv"], "tail": "current", "include": False}) if
                not a.startswith("--script-opts-append=%s=" % helper.PLAYER_BUILD_KEY)]
        self.assertEqual(self.case_argv({"shape": "v0.16.0"}), mine)
        self.assertIn("--osd-duration=4321", older["v0.15.0"])
        self.assertNotIn("--osd-duration=4321", older["v0.16.0-include"])
        for shape in older.values():
            self.assertFalse(any(a.startswith("--script-opts-append=%s=" % helper.PLAYER_BUILD_KEY) for a in shape))

    def test_a_command_line_that_is_empty_or_gone_is_unknown(self):
        # A zombie's command line is empty, as a just-exec'd one briefly is
        # (F-HARNESS-41); a reaped pid has none at all.
        process = subprocess.Popen(["true"])
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                with open("/proc/%d/stat" % process.pid, "rb") as handle:
                    if handle.read().rsplit(b")", 1)[1].split()[0] == b"Z":
                        break
            except OSError:
                break
            time.sleep(0.005)
        empty = helper.launch_verdict(process.pid, self.sock)
        process.wait(timeout=5)
        gone = helper.launch_verdict(process.pid, self.sock)
        self.assertEqual([empty, gone], ["unknown", "unknown"])
        for nothing in (0, -1, None, True, "123"):
            self.assertEqual(helper.launch_verdict(nothing, self.sock), "unknown", nothing)

    def test_a_socket_folder_whose_name_is_not_utf8_reads_current(self):
        """Read as BYTES: a runtime folder named with the byte 0xff puts that
        byte in the socket token and every runtime element, and a "replace"
        decode would turn it into U+FFFD -- another build, for ever."""
        odd = os.fsdecode(os.fsencode(self.dir) + b"/run-\xff")
        os.makedirs(odd, 0o700)
        sock = os.path.join(odd, "mpv.sock")
        process = self.hold(["mpv"] + self.current_tail(False, sock))
        self.assertEqual(helper.launch_verdict(process.pid, sock), "current")


class PlayerBuildTest(unittest.TestCase):

    def test_the_build_is_the_version_and_the_checksum_of_the_part_table(self):
        parts = helper.HELPER_PARTS
        text = "".join("%s:%d:%08x\n" % (name, size, crc) for name, size, crc in parts)
        self.assertEqual(helper.player_build(), "%s+%08x" % (helper.VERSION, zlib.crc32(text.encode("ascii"))))

    def test_every_part_edit_and_every_release_changes_it(self):
        before = helper.player_build()
        name, size, crc = helper.HELPER_PARTS[0]
        with mock.patch.object(helper, "HELPER_PARTS", ((name, size, crc ^ 1),) + helper.HELPER_PARTS[1:]):
            edited_part = helper.player_build()
        with mock.patch.object(helper, "VERSION", "9.9.9"):
            released = helper.player_build()
        self.assertEqual(len({before, edited_part, released}), 3)

    def test_a_build_that_is_not_one_is_the_word_unknown(self):
        with mock.patch.object(helper, "VERSION", "1.0 beta"):
            self.assertEqual(helper.player_build(), "unknown")
        with mock.patch.object(helper, "HELPER_PARTS", ()):
            self.assertEqual(helper.player_build(), "unknown")
        self.assertEqual(helper.mpv_build_marker("x\n"), "--script-opts-append=omarchy_iptv-build=unknown")
        self.assertEqual(helper.mpv_build_marker("x" * 65), "--script-opts-append=omarchy_iptv-build=unknown")

    def test_the_launch_argv_carries_it_once_in_the_base_section(self):
        sock = "/run/user/1000/omarchy-iptv/mpv.sock"
        marker = helper.mpv_build_marker(helper.player_build())
        for tokens in ([], ["--cache=yes"]):
            argv = helper.mpv_launch_argv(sock, tokens)
            pins = helper.mpv_pin_block(helper.player_dirs(sock))
            self.assertEqual(argv.count(marker), 1, tokens)
            # after layer 1 of TLS, before the options file and the pin block
            self.assertEqual(argv.index(marker), argv.index(helper.MPV_TLS_VERIFY) + 1, tokens)
            self.assertLess(argv.index(marker), len(argv) - len(pins) - (1 if tokens else 0), tokens)


if __name__ == "__main__":
    unittest.main()
