"""D-CLIP-1 (R8): the helper's `clipboard` verb, run as a SUBPROCESS against a
stub wl-paste on PATH.

The shell never holds more than the bounded reply: the verb runs wl-paste
with a pipe, reads at most MAX_CLIPBOARD_BYTES, terminates the child the
moment the cap, EOF or its deadline is reached, and prints ONE JSON line on
stdout and nothing on stderr. Every case below runs the shipping verb the
way the shell does (python3 bin/omarchy-iptv clipboard, PATH first) against
a stub that streams, hangs, ignores SIGTERM, fails, or is absent, and asks
the operating system what happened: the bytes in the reply, the stub's own
record of whether it reached EOF, whether its pid still exists afterwards,
and what reached stderr (nothing, rule 5). Nothing here reads the user's
clipboard: the real wl-paste is never on the PATH these cases build.

tests/fixtures/clipboard.json is the shared fixture: tests/Model.test.js
pins the shell's numbers to it and this file pins the helper's.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

import helper_loader
from helper_loader import load_helper

helper = load_helper()
HELPER = helper_loader.HELPER
FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "clipboard.json"
CLIP = json.loads(FIXTURE.read_text(encoding="utf-8"))

# The stub wl-paste. Modes, all driven by environment variables the test
# sets on the helper's environment (the stub inherits it):
#   exact        write STUB_WL_PASTE_FILE whole, exit 0
#   stream       write the file in STUB_WL_PASTE_CHUNK-byte pieces, sleeping
#                STUB_WL_PASTE_DELAY seconds between pieces
#   hang         write the file, then sleep until killed
#   ignore-term  ignore SIGTERM, then as hang
#   fail         write the file, exit 1 (wl-paste's "Nothing is copied")
# It writes a line to STUB_WL_PASTE_RECORD at start (pid, argv) and another
# at EOF ("done") or on a broken pipe, so a test can tell "terminated at the
# cap" (no second line) from "the reader closed the pipe" ("broken-pipe")
# from "read to the end" ("done"). It also prints to stderr on every run,
# which must never reach the verb's stderr.
STUB = """#!%(python)s
import json, os, signal, sys, time
mode = os.environ.get("STUB_WL_PASTE_MODE", "exact")
record = os.environ.get("STUB_WL_PASTE_RECORD", "")
def note(event):
    if record:
        with open(record, "a") as handle:
            handle.write(json.dumps({"event": event, "pid": os.getpid(), "argv": sys.argv}) + "\\n")
note("start")
sys.stderr.write("STUB-STDERR-MUST-NOT-REACH-THE-SHELL\\n")
sys.stderr.flush()
path = os.environ.get("STUB_WL_PASTE_FILE", "")
data = open(path, "rb").read() if path else b""
out = sys.stdout.buffer
try:
    if mode == "stream":
        chunk = int(os.environ.get("STUB_WL_PASTE_CHUNK", "1024"))
        delay = float(os.environ.get("STUB_WL_PASTE_DELAY", "0.005"))
        for start in range(0, len(data), chunk):
            out.write(data[start:start + chunk])
            out.flush()
            time.sleep(delay)
    else:
        out.write(data)
        out.flush()
    if mode == "ignore-term":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if mode in ("hang", "ignore-term"):
        note("hanging")
        time.sleep(120)
    if mode == "fail":
        note("failed")
        sys.exit(1)
    note("done")
except BrokenPipeError:
    note("broken-pipe")
    os._exit(0)
""" % {"python": sys.executable}


class ClipboardVerbTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="omarchy-iptv-clip-")
        self.addCleanup(self.tmp.cleanup)
        self.dir = pathlib.Path(self.tmp.name)
        self.bin = self.dir / "bin"
        self.bin.mkdir(mode=0o700)
        stub = self.bin / "wl-paste"
        stub.write_text(STUB, encoding="utf-8")
        stub.chmod(0o700)
        self.empty = self.dir / "empty"
        self.empty.mkdir(mode=0o700)
        self.record = self.dir / "record.jsonl"
        self.payload = self.dir / "payload.bin"
        self.pids = []
        self.addCleanup(self.reap_stubs)

    def reap_stubs(self):
        """Belt and braces: the verb must have reaped every stub itself (that
        is what the tests assert), so this finds nothing on a green run."""
        for pid in self.pids:
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass

    def run_verb(self, mode="exact", data=b"", deadline="2", path=None, **extra):
        self.payload.write_bytes(data)
        env = dict(os.environ)
        env["PATH"] = str(self.bin if path is None else path)
        env["STUB_WL_PASTE_MODE"] = mode
        env["STUB_WL_PASTE_FILE"] = str(self.payload)
        env["STUB_WL_PASTE_RECORD"] = str(self.record)
        env[helper.CLIPBOARD_TIMEOUT_ENV] = deadline
        for key, value in extra.items():
            env[key] = str(value)
        started = time.monotonic()
        completed = subprocess.run([sys.executable, str(HELPER), "clipboard"], env=env,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, timeout=30)
        elapsed = time.monotonic() - started
        for event in self.events():
            if event["event"] == "start":
                self.pids.append(event["pid"])
        return completed, elapsed

    def events(self):
        if not self.record.exists():
            return []
        return [json.loads(line) for line in self.record.read_text(encoding="utf-8").splitlines() if line]

    def reply(self, completed):
        """The one line on stdout, parsed; the assertions every outcome shares."""
        self.assertEqual(completed.stderr, b"", "the verb printed on stderr")
        lines = completed.stdout.decode("utf-8").splitlines()
        self.assertEqual(len(lines), 1, "the verb must print exactly one line: %r" % completed.stdout[:200])
        reply = json.loads(lines[0])
        self.assertEqual(reply["kind"], "clipboard")
        if reply["ok"]:
            self.assertEqual(completed.returncode, 0)
            self.assertEqual(sorted(reply), ["bytes", "kind", "ok", "text", "truncated"])
        else:
            self.assertEqual(completed.returncode, 1)
            self.assertNotIn("text", reply)
            self.assertIn("code", reply)
        return reply

    def assert_stub_gone(self):
        starts = [e for e in self.events() if e["event"] == "start"]
        self.assertEqual(len(starts), 1, "exactly one wl-paste was started")
        pid = starts[0]["pid"]
        with self.assertRaises(ProcessLookupError, msg="the stub wl-paste %d outlived the verb" % pid):
            os.kill(pid, 0)
        return starts[0]

    def stub_end(self):
        ends = [e["event"] for e in self.events() if e["event"] != "start"]
        return ends[-1] if ends else None

    # ---------------------------------------------------------- fixture

    def test_the_fixture_pins_the_helper_constants(self):
        """One number per bound, shared with Model.js through the fixture."""
        self.assertEqual(helper.CLIPBOARD_TIMEOUT * 1000, CLIP["timeoutMs"])
        self.assertEqual(helper.CLIPBOARD_KILL_GRACE * 1000, CLIP["killGraceMs"])
        self.assertEqual(helper.MAX_CLIPBOARD_CHARS, CLIP["maxChars"])
        self.assertEqual(helper.MAX_CLIPBOARD_CHARS, helper.MAX_SOURCE_URL * 4)
        self.assertEqual(helper.MAX_CLIPBOARD_BYTES, CLIP["maxBytes"])
        self.assertEqual(helper.MAX_CLIPBOARD_BYTES, helper.MAX_CLIPBOARD_CHARS * 4)
        self.assertEqual(helper.MAX_CLIPBOARD_BYTES, 32 * 1024)
        self.assertEqual(helper.CLIPBOARD_ARGV, CLIP["argv"])

    def test_the_deadline_defaults_to_the_fixture_and_tests_shrink_it(self):
        saved = os.environ.pop(helper.CLIPBOARD_TIMEOUT_ENV, None)
        try:
            self.assertEqual(helper.clipboard_deadline(), CLIP["timeoutMs"] / 1000)
            os.environ[helper.CLIPBOARD_TIMEOUT_ENV] = "0.25"
            self.assertEqual(helper.clipboard_deadline(), 0.25)
            os.environ[helper.CLIPBOARD_TIMEOUT_ENV] = "soon"
            self.assertEqual(helper.clipboard_deadline(), CLIP["timeoutMs"] / 1000)
            os.environ[helper.CLIPBOARD_TIMEOUT_ENV] = "0"
            self.assertEqual(helper.clipboard_deadline(), 0.05, "a zero deadline is clamped, never a busy loop")
        finally:
            os.environ.pop(helper.CLIPBOARD_TIMEOUT_ENV, None)
            if saved is not None:
                os.environ[helper.CLIPBOARD_TIMEOUT_ENV] = saved

    def test_utf16_cut_counts_the_units_the_shell_counts(self):
        astral = "\U0001F600"
        self.assertEqual(helper.utf16_cut("abc", 3), ("abc", False))
        self.assertEqual(helper.utf16_cut("abcd", 3), ("abc", True))
        self.assertEqual(helper.utf16_cut("ab" + astral, 4), ("ab" + astral, False))
        self.assertEqual(helper.utf16_cut("ab" + astral + "c", 4), ("ab" + astral, True))
        self.assertEqual(helper.utf16_cut("abc" + astral, 4), ("abc", True), "a pair that does not fit is dropped whole")
        self.assertEqual(helper.utf16_cut("", 4), ("", False))

    # ------------------------------------------------------- the verb

    def test_a_small_clipboard_comes_back_whole_through_the_fixture_argv(self):
        completed, _ = self.run_verb("exact", b"hello world")
        reply = self.reply(completed)
        self.assertEqual(reply, {"ok": True, "kind": "clipboard", "text": "hello world", "truncated": False, "bytes": 11})
        start = self.assert_stub_gone()
        self.assertEqual(start["argv"][1:], CLIP["argv"][1:], "the verb runs wl-paste with the fixture's arguments")
        self.assertEqual(os.path.basename(start["argv"][0]), "wl-paste")
        self.assertEqual(self.stub_end(), "done", "the stub reached EOF on its own")

    def test_unicode_and_control_bytes_survive_for_the_guide_to_sanitize(self):
        text = "a\x01b\n\u20ac \U0001F600 \ufeffx"
        completed, _ = self.run_verb("exact", text.encode("utf-8"))
        reply = self.reply(completed)
        self.assertEqual(reply["text"], text)
        self.assertEqual(reply["bytes"], len(text.encode("utf-8")))
        self.assertFalse(reply["truncated"])
        self.assert_stub_gone()

    def test_an_empty_clipboard_is_an_empty_ok_reply(self):
        completed, _ = self.run_verb("exact", b"")
        reply = self.reply(completed)
        self.assertEqual(reply, {"ok": True, "kind": "clipboard", "text": "", "truncated": False, "bytes": 0})
        self.assert_stub_gone()

    def test_the_byte_cap_stops_the_read_and_terminates_the_producer(self):
        """The finding's exhaust half: a producer streaming far more than the
        cap. The verb must hold at most MAX_CLIPBOARD_BYTES and the stub must
        die at the cap -- no "done", no "broken-pipe", the pid gone."""
        total = 4 * 1024 * 1024
        completed, elapsed = self.run_verb("stream", b"a" * total, deadline="20",
                                           STUB_WL_PASTE_CHUNK=4096, STUB_WL_PASTE_DELAY="0.002")
        reply = self.reply(completed)
        self.assertEqual(reply["bytes"], helper.MAX_CLIPBOARD_BYTES)
        self.assertTrue(reply["truncated"])
        self.assertEqual(reply["text"], "a" * helper.MAX_CLIPBOARD_CHARS, "the text is the character cut of the byte cap")
        self.assert_stub_gone()
        self.assertIsNone(self.stub_end(), "the stub was terminated before EOF (it recorded neither done nor broken-pipe)")
        # 1024 chunks at 2 ms is at least 2 s of streaming; the verb must not
        # have waited for it. Generous for a loaded machine, red for a verb
        # that drains the pipe.
        self.assertLess(elapsed, 1.5, "the verb waited for the producer instead of stopping at the cap")

    def test_a_burst_larger_than_the_cap_is_cut_without_being_held(self):
        completed, _ = self.run_verb("exact", b"b" * (helper.MAX_CLIPBOARD_BYTES * 8))
        reply = self.reply(completed)
        self.assertEqual(reply["bytes"], helper.MAX_CLIPBOARD_BYTES)
        self.assertTrue(reply["truncated"])
        self.assert_stub_gone()
        self.assertNotEqual(self.stub_end(), "done", "the stub never got to write the whole burst")

    def test_the_byte_cap_can_only_bind_beyond_the_character_cap(self):
        """The arithmetic: MAX_CLIPBOARD_BYTES is four bytes per unit of
        MAX_CLIPBOARD_CHARS, so a text the character cut keeps always fits
        the byte cap, and a text the byte cap cuts is always cut again by
        characters. 32766 ASCII bytes then a three-byte euro: the byte cap
        lands inside the euro, the decoder drops the partial tail rather
        than replacing it, and the character cut leaves 8192 a's."""
        data = b"a" * (helper.MAX_CLIPBOARD_BYTES - 2) + "\u20ac".encode("utf-8") + b"b"
        self.assertEqual(len(data), helper.MAX_CLIPBOARD_BYTES + 2)
        completed, _ = self.run_verb("exact", data)
        reply = self.reply(completed)
        self.assertEqual(reply["bytes"], helper.MAX_CLIPBOARD_BYTES)
        self.assertTrue(reply["truncated"])
        self.assertEqual(reply["text"], "a" * helper.MAX_CLIPBOARD_CHARS)
        self.assertNotIn("\ufffd", reply["text"])
        self.assert_stub_gone()

    def test_the_cap_cuts_at_a_character_boundary(self):
        """The mechanism itself, on the shipping reader with a cap small
        enough to be the binding one: `ab` then a euro, cap 4 lands inside
        the euro, and the text ends before it with no U+FFFD; cap 5 keeps
        it whole and is still `truncated` (the cap stopped the read before
        EOF, which the docstring says errs toward saying something was cut)."""
        self.payload.write_bytes(b"ab" + "\u20ac".encode("utf-8"))
        env = {"PATH": str(self.bin), "STUB_WL_PASTE_MODE": "exact",
               "STUB_WL_PASTE_FILE": str(self.payload), "STUB_WL_PASTE_RECORD": str(self.record)}
        saved = {key: os.environ.get(key) for key in env}
        os.environ.update(env)
        try:
            inside = helper.read_clipboard(helper.CLIPBOARD_ARGV, 4, 2.0, helper.CLIPBOARD_KILL_GRACE)
            whole = helper.read_clipboard(helper.CLIPBOARD_ARGV, 5, 2.0, helper.CLIPBOARD_KILL_GRACE)
            beyond = helper.read_clipboard(helper.CLIPBOARD_ARGV, 6, 2.0, helper.CLIPBOARD_KILL_GRACE)
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        self.assertEqual(inside, {"ok": True, "text": "ab", "truncated": True, "bytes": 4})
        self.assertEqual(whole, {"ok": True, "text": "ab\u20ac", "truncated": True, "bytes": 5})
        self.assertEqual(beyond, {"ok": True, "text": "ab\u20ac", "truncated": False, "bytes": 5})
        for pid in [e["pid"] for e in self.events() if e["event"] == "start"]:
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_the_character_cap_counts_utf16_units_and_keeps_pairs_whole(self):
        """Under the byte cap but over the character cap, with an astral
        character (two UTF-16 units) straddling it: the pair is dropped whole."""
        text = "a" * (helper.MAX_CLIPBOARD_CHARS - 1) + "\U0001F600" + "b" * 100
        data = text.encode("utf-8")
        self.assertLess(len(data), helper.MAX_CLIPBOARD_BYTES)
        completed, _ = self.run_verb("exact", data)
        reply = self.reply(completed)
        self.assertEqual(reply["text"], "a" * (helper.MAX_CLIPBOARD_CHARS - 1))
        self.assertTrue(reply["truncated"])
        self.assertEqual(reply["bytes"], len(data), "the bytes were read; the characters were cut")
        self.assert_stub_gone()

    def test_exactly_the_character_cap_is_whole(self):
        text = "c" * helper.MAX_CLIPBOARD_CHARS
        completed, _ = self.run_verb("exact", text.encode("utf-8"))
        reply = self.reply(completed)
        self.assertEqual(reply["text"], text)
        self.assertFalse(reply["truncated"])
        self.assert_stub_gone()

    def test_invalid_utf8_in_the_middle_is_replaced_not_fatal(self):
        completed, _ = self.run_verb("exact", b"ab\xffcd")
        reply = self.reply(completed)
        self.assertEqual(reply["text"], "ab\ufffdcd")
        self.assertEqual(reply["bytes"], 5)
        self.assert_stub_gone()

    def test_a_producer_that_never_ends_meets_the_deadline_and_dies(self):
        """The finding's stall half: a producer that writes some and then
        holds the pipe open. The deadline answers "timeout" with NO text,
        and the stub is terminated."""
        completed, elapsed = self.run_verb("hang", b"partial-secret", deadline="0.3")
        reply = self.reply(completed)
        self.assertEqual(reply["code"], "timeout")
        self.assertNotIn(b"partial-secret", completed.stdout)
        self.assertNotIn(b"partial-secret", completed.stderr)
        self.assert_stub_gone()
        self.assertEqual(self.stub_end(), "hanging")
        self.assertLess(elapsed, 0.3 + helper.CLIPBOARD_KILL_GRACE + 3.0)

    def test_a_producer_that_ignores_sigterm_is_killed_after_the_grace(self):
        completed, elapsed = self.run_verb("ignore-term", b"x", deadline="0.3")
        reply = self.reply(completed)
        self.assertEqual(reply["code"], "timeout")
        self.assert_stub_gone()
        self.assertEqual(self.stub_end(), "hanging")
        self.assertGreaterEqual(elapsed, 0.3 + helper.CLIPBOARD_KILL_GRACE - 0.05, "SIGKILL waits the grace out first")
        self.assertLess(elapsed, 0.3 + 2 * helper.CLIPBOARD_KILL_GRACE + 3.0)

    def test_a_slow_drip_under_the_cap_still_meets_the_deadline(self):
        """The protocol's own attack shape: bytes at a trickle. 40 bytes at
        50 ms apiece is 2 s; the 0.4 s deadline wins, and no text leaks."""
        completed, elapsed = self.run_verb("stream", b"drip-secret-" * 10, deadline="0.4",
                                           STUB_WL_PASTE_CHUNK=3, STUB_WL_PASTE_DELAY="0.05")
        reply = self.reply(completed)
        self.assertEqual(reply["code"], "timeout")
        self.assertNotIn(b"drip", completed.stdout)
        self.assert_stub_gone()
        self.assertIsNone(self.stub_end())
        self.assertLess(elapsed, 0.4 + helper.CLIPBOARD_KILL_GRACE + 3.0)

    def test_a_failed_wl_paste_answers_no_text_even_when_it_printed_some(self):
        completed, _ = self.run_verb("fail", b"nothing-is-copied-secret")
        reply = self.reply(completed)
        self.assertEqual(reply["code"], "failed")
        self.assertEqual(reply["status"], 1)
        self.assertNotIn(b"secret", completed.stdout)
        self.assert_stub_gone()

    def test_a_missing_wl_paste_is_a_code_not_a_traceback(self):
        completed, _ = self.run_verb("exact", b"x", path=self.empty)
        reply = self.reply(completed)
        self.assertEqual(reply, {"ok": False, "kind": "clipboard", "code": "no_wl_paste"})
        self.assertEqual(self.events(), [], "nothing was started")

    def test_the_stubs_stderr_never_reaches_the_verbs_stderr(self):
        """Every outcome above asserts stderr is empty through reply(); this
        one says so by name, over the stub's loudest run."""
        completed, _ = self.run_verb("exact", b"quiet")
        self.assertEqual(completed.stderr, b"")
        self.assertNotIn(b"STUB-STDERR", completed.stdout)

    def test_the_verb_takes_no_arguments_and_the_parser_knows_it(self):
        completed = subprocess.run([sys.executable, str(HELPER), "clipboard", "--url", "x"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                                   env=dict(os.environ, PATH=str(self.empty)))
        self.assertEqual(completed.returncode, helper.EXIT_USAGE)
        self.assertEqual(self.events(), [])
        completed = subprocess.run([sys.executable, str(HELPER), "--help"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertIn(b"clipboard", completed.stdout)


if __name__ == "__main__":
    unittest.main()
