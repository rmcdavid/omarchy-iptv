"""D-HOST-7: every notice the plugin posts depends on the host's
`omarchy-notification-send` taking `-p` and printing the id the server
returned, alone on one line (D-HOST-5: that id is what the next post of the
kind sends back as `-r`, so the card is replaced and not stacked). A wrapper
that does not know `-p` exits 1 with an empty stdout and every notice is
lost in silence; one that prints the reply some other way leaves the plugin
with no id, and every post is a new card. Nothing pinned either.

This RUNS the host's wrapper (rule 14: the sink, not a grep of it) with the
argv the shipping model builds (Model.notifyArgv, asked through node) and a
stub `busctl` first on PATH, which records its arguments and answers as
busctl does, `u <id>`. It then hands what the wrapper printed to the
shipping reader (Model.notifyReplyId). No notification is posted: the stub
stands where busctl was, and the session bus address handed to the wrapper
names a socket that does not exist, so a wrapper that reached the bus some
other way would fail rather than draw a card.

A red here after an Omarchy update is a re-measurement request, not a
plugin defect. OMARCHY_NOTIFY_SEND points the test at a copy, which is how
each pin was proven red (rule 11): a copy with the `-p | --print-id` case
removed, one whose print is `"$out"` rather than `"${out##* }"`, and one
that sends the summary and the body in the other order.
"""
import json
import os
import stat
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WRAPPER = os.environ.get("OMARCHY_NOTIFY_SEND", "/usr/bin/omarchy-notification-send")

SERVER_ID = 42

# (event, params, the id the plugin holds for the kind or None). The second
# name is text a careless reader would take for options.
CASES = [
    ("streamFailed", {"name": "BBC One HD", "reason": "HTTP 403"}, None),
    ("streamFailed", {"name": "--exec -p -r 9", "reason": "-u critical"}, 7),
    ("playerStopped", {"name": "News & <b>Sport</b>"}, 4294967295),
]

STUB = """#!/bin/sh
printf '%s\\0' "$@" > "$BUSCTL_LOG"
echo "u $BUSCTL_ID"
"""


def model(script):
    run = subprocess.run(["node", "-e", 'const M=require("./Model.mjs");' + script], capture_output=True,
                         text=True, cwd=ROOT, timeout=60)
    if run.returncode != 0:
        raise AssertionError("node could not run the model: " + run.stderr[-400:])
    return json.loads(run.stdout)


@unittest.skipUnless(os.path.isfile(WRAPPER), "no %s; the host's notification wrapper cannot be run here" % WRAPPER)
class NotifyWrapperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.argvs = model("console.log(JSON.stringify(%s.map(function (c) { return M.notifyArgv(c[0], c[1], c[2]) })))"
                          % json.dumps(CASES))

    def post(self, argv):
        """Run the host's wrapper with the plugin's argv over the stub.
        Returns (exit code, stdout, stderr, what busctl was called with)."""
        with tempfile.TemporaryDirectory() as tmp:
            bindir = os.path.join(tmp, "bin")
            os.mkdir(bindir)
            stub = os.path.join(bindir, "busctl")
            with open(stub, "w") as f:
                f.write(STUB)
            os.chmod(stub, stat.S_IRWXU)
            log = os.path.join(tmp, "busctl.argv")
            env = {
                "PATH": bindir + ":/usr/bin:/bin",
                "HOME": tmp,
                "XDG_RUNTIME_DIR": tmp,
                "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + os.path.join(tmp, "no-such-bus"),
                "BUSCTL_LOG": log,
                "BUSCTL_ID": str(SERVER_ID),
            }
            run = subprocess.run([WRAPPER] + argv[1:], capture_output=True, text=True, env=env, timeout=30)
            called = None
            if os.path.exists(log):
                with open(log, "rb") as f:
                    called = [a.decode("utf-8") for a in f.read().split(b"\0")[:-1]]
            return run.returncode, run.stdout, run.stderr, called

    def test_the_plugin_names_the_wrapper_and_asks_for_the_id(self):
        for argv in self.argvs:
            self.assertEqual(argv[0], "omarchy-notification-send")
            self.assertIn("-p", argv[1:-2], "the pin below is about -p; the plugin no longer sends it")

    def test_the_wrapper_takes_the_plugins_argv_and_prints_the_id_alone(self):
        for case, argv in zip(CASES, self.argvs):
            with self.subTest(case=case):
                code, out, err, called = self.post(argv)
                self.assertEqual(code, 0, "the host's wrapper refused the plugin's argv, so the notice is lost: " + err[-300:])
                self.assertIsNotNone(called, "the wrapper never ran busctl; how it reaches the server has changed")
                self.assertEqual(out, "%d\n" % SERVER_ID, "the wrapper no longer prints the server's id alone on one line")

    def test_the_shipping_reader_holds_the_id_the_wrapper_printed(self):
        replies = []
        for argv in self.argvs:
            code, out, _err, _called = self.post(argv)
            replies.append([out, code])
        ids = model("console.log(JSON.stringify(%s.map(function (r) { return M.notifyReplyId(r[0], r[1]) })))"
                    % json.dumps(replies))
        self.assertEqual(ids, [SERVER_ID] * len(CASES), "Model.notifyReplyId reads no id from what the wrapper printed")

    def test_the_card_carries_the_plugins_words_as_single_arguments(self):
        for case, argv in zip(CASES, self.argvs):
            with self.subTest(case=case):
                _code, _out, _err, called = self.post(argv)
                self.assertIsNotNone(called)
                self.assertIn("Notify", called)
                at = called.index("Notify")
                # Notify susssasa{sv}i: app_name, replaces_id, app_icon, summary, body.
                self.assertEqual(called[at + 1], "susssasa{sv}i", "the Notify signature the wrapper sends has changed")
                app, replaces, _icon, summary, body = called[at + 2:at + 7]
                self.assertEqual(app, "IPTV")
                self.assertEqual(replaces, argv[argv.index("-r") + 1], "the id after -r is not the id the server is asked to replace")
                if case[2] is not None:
                    self.assertEqual(replaces, str(case[2]), "the plugin did not send back the id it holds")
                self.assertEqual(summary, argv[-2])
                self.assertEqual(body, argv[-1], "the body reached the server changed, split or read as options")
                hints = called[at + 7:]
                glyph = argv[argv.index("-g") + 1]
                self.assertIn(["omarchy-glyph", "s", glyph], [hints[i:i + 3] for i in range(len(hints))])
                self.assertNotIn("omarchy-exec-argv", hints, "text in a name became a click command")


if __name__ == "__main__":
    unittest.main()
