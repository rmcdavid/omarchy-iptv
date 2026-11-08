"""F-HARNESS-96, -97 and -98: the harness's own printers say what a shipped
line would, and no harness command line carries a credential.

The defects. run.sh's `source_label` and the chno scenarios' `url_context`
cut a URL down to its host with patterns of their own, which could not cross
an `@` in a password, stopped at a `;sid=` parameter's end rather than its
start, or ended a match at the `@` and so printed the username and password.
The live-rewind spike printed urllib's netloc, userinfo included, and names
and groups raw. probe-provider-api.sh put the subscription's username and
password on python3's command line, which every user can read in
/proc/<pid>/cmdline.

What is pinned, by CALLING the shipping code (CLAUDE.md 12, 14):

  1. run.sh's `source_label`, extracted from the file and run in bash, prints
     the shipping helper's redaction for every measured shape, and the URL
     never reaches an argv: a `python3` on PATH records every argument list
     it is handed.
  2. `url_context`, extracted from BOTH chno scenarios, prints no part of a
     userinfo, including when its 60 characters of context start inside an
     earlier URL.
  3. The spike's `select_channels` host, label and name printers, and the
     `shown` that sweep.py and design_pass.py print names through, are the
     same function.
  4. probe-provider-api.sh, run whole against a local stub of the provider
     API, still sends the credentials to the provider, never hands them to
     python3 as arguments, and names the provider host without the playlist
     URL's userinfo.

Nothing here starts a shell, a cage, a bus or a player, and nothing leaves
127.0.0.1.

Run: python3 -m unittest discover -s tests
"""
import http.server
import importlib.util
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
HARNESS = ROOT / "scripts" / "dev-harness"
RUN_SH = HARNESS / "run.sh"
SCENARIOS = [HARNESS / "chno-scenario.sh", HARNESS / "chno-entry-scenario.sh"]
SPIKE = HARNESS / "spikes" / "live-rewind"
PROBE = ROOT / "scripts" / "probe-provider-api.sh"

USER, PASS = "u5er", "p4ss"
# The measured shapes from the board rows, and what the shipping redactor
# prints for each (bin/helper/01-core.py redact_urls).
LABELS = [
    ("", "(none)"),
    ("http://u5er:p4@ss@prov.test/x", "http://prov.test"),
    ("http://u5er:p4/ss@prov.test/x", "http://[host withheld]"),
    ("http://u5er:p4#ss@prov.test/x", "http://[host withheld]"),
    ("http://u5er:p4?ss@prov.test/x", "http://[host withheld]"),
    ("http://h.test;sid=SECRET/x", "http://h.test"),
    ("https://u5er:p4ss@Prov.Test:8443/live/1.ts", "https://prov.test"),
    ("file:///tmp/a.m3u", "local file"),
    ("/tmp/a.m3u", "local file"),
]
SECRET_PIECES = ("u5er", "p4", "ss@", "SECRET")


def bash_function(script, name):
    """The text of `name() { ... }` in script, multi-line or on one line."""
    match = (re.search(r"^%s\(\) \{\n.*?^\}\n" % re.escape(name), script, re.S | re.M)
             or re.search(r"^%s\(\) \{ .*\}$" % re.escape(name), script, re.M))
    if match is None:
        raise AssertionError("no %s() in the script" % name)
    return match.group(0)


class ArgvRecorder:
    """A directory holding a `python3` that appends each argument list it is
    handed (NUL-separated, one record per line) to a log, then runs the real
    interpreter with the same arguments and stdin."""

    def __init__(self, tmp):
        self.bin = os.path.join(tmp, "bin")
        os.mkdir(self.bin, 0o700)
        self.log = os.path.join(tmp, "argv.log")
        real = sys.executable
        with open(os.path.join(self.bin, "python3"), "w", encoding="ascii") as handle:
            handle.write("#!/bin/bash\n"
                         "{ printf '%%s\\0' \"$@\"; printf 'PROBE_HOST=%%s\\n' \"${PROBE_HOST-}\"; } >> %s\n"
                         "exec %s \"$@\"\n" % (self.log, real))
        os.chmod(os.path.join(self.bin, "python3"), 0o700)

    def env(self):
        env = dict(os.environ)
        env["PATH"] = self.bin + os.pathsep + env.get("PATH", "")
        for key in ("WAYLAND_DISPLAY", "DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE"):
            env.pop(key, None)
        return env

    def records(self):
        try:
            with open(self.log, encoding="utf-8", errors="replace") as handle:
                return handle.read()
        except FileNotFoundError:
            return ""


def call_function(body, name, value, recorder):
    """Run an extracted bash function on one value, with ROOT set as the
    scripts set it. The value reaches bash as its own argument (the test's
    doing); what the FUNCTION starts is recorded by `recorder`."""
    return subprocess.run(["bash", "-c", 'ROOT="$0"\n%s\n%s "$1"' % (body, name), str(ROOT), value],
                          capture_output=True, text=True, timeout=60, env=recorder.env(), cwd=str(ROOT))


class SourceLabelTest(unittest.TestCase):
    def test_source_label_prints_the_shipping_redaction_and_no_argv_holds_the_url(self):
        body = bash_function(RUN_SH.read_text(encoding="utf-8"), "source_label")
        with tempfile.TemporaryDirectory() as tmp:
            recorder = ArgvRecorder(tmp)
            for url, want in LABELS:
                result = call_function(body, "source_label", url, recorder)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), want, url)
            argvs = recorder.records()
            self.assertIn("helper_redact.py", argvs)
            for url, _ in LABELS:
                if url.startswith(("http", "https")):
                    self.assertNotIn(url, argvs)
            for piece in ("u5er", "p4ss", "SECRET"):
                self.assertNotIn(piece, argvs)


class UrlContextTest(unittest.TestCase):
    ANSWERS = [
        "Failed to open http://u5er:p4ss@prov.test/live/1.ts",
        "{\"error\": \"" + "x" * 30 + " http://u5er:p4ss@prov.test/live/1.ts then http://cdn.test/x\"}",
        "a http://u5er:p4/ss@prov.test/x b",
        # A quote inside the password ends the context's URL match there, so a
        # cut made BEFORE the redaction hands the redactor `http://u5er:p4`,
        # whose host reads as the username. The whole answer is redacted
        # first, where the quote is URL text (R32a''': a run ends only at the
        # six ASCII whitespace characters).
        '{"url": "http://u5er:p4"ss@prov.test/x"}',
    ]

    def test_both_scenarios_print_no_userinfo(self):
        for script in SCENARIOS:
            body = bash_function(script.read_text(encoding="utf-8"), "url_context")
            with tempfile.TemporaryDirectory() as tmp:
                recorder = ArgvRecorder(tmp)
                for answer in self.ANSWERS:
                    result = call_function(body, "url_context", answer, recorder)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("://", result.stdout, (script.name, answer))
                    for piece in ("u5er", "p4ss", "p4/"):
                        self.assertNotIn(piece, result.stdout, (script.name, answer, result.stdout))
                for piece in ("u5er", "p4ss"):
                    self.assertNotIn(piece, recorder.records(), script.name)


def load_spike(name):
    sys.dont_write_bytecode = True
    if str(SPIKE) not in sys.path:
        sys.path.insert(0, str(SPIKE))
    spec = importlib.util.spec_from_file_location(name, str(SPIKE / (name + ".py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class SpikeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.select = load_spike("select_channels")

    def test_host_and_label_are_the_shipping_redaction(self):
        for url, want in LABELS:
            if url.startswith("http"):
                self.assertEqual(self.select.redact(url), want, url)
                self.assertEqual(self.select.host_of(url), want.split("://", 1)[1], url)

    def test_a_sample_host_carries_no_userinfo(self):
        channels = [{"id": "c%d" % i, "name": "N%d" % i, "group": "G", "url": url}
                    for i, (url, _) in enumerate(LABELS) if url.startswith("http")]
        for row in self.select.pick(channels, 32, 99):
            for piece in ("u5er", "p4", "SECRET"):
                self.assertNotIn(piece, row["host"], row)

    def test_names_and_groups_print_through_the_redactor(self):
        shown = self.select.shown("News http://u5er:p4ss@prov.test/live/1.ts HD")
        self.assertEqual(shown, "News http://prov.test HD")
        self.assertEqual(self.select.shown(None), "")

    def test_sweep_and_design_pass_print_through_the_same_shown(self):
        # The join between the printers and the redactor is a NAME (CLAUDE.md
        # 13): both scripts import it from select_channels, so the call is
        # the same object, and a row written by sweep.measure_one's row shape
        # is redacted.
        sweep = load_spike("sweep")
        self.assertIs(sweep.shown, self.select.shown)
        self.assertIs(sweep.redact, self.select.redact)
        design = load_spike("design_pass")
        self.assertIs(design.shown, self.select.shown)


class ProviderProbeTest(unittest.TestCase):
    def test_credentials_reach_the_provider_and_no_argv(self):
        seen = []

        class Api(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(self.path)
                body = b"[]"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Api)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            with tempfile.TemporaryDirectory() as tmp:
                playlist = os.path.join(tmp, "list.m3u")
                with open(playlist, "w", encoding="ascii") as handle:
                    handle.write("#EXTM3U\n#EXTINF:-1,One\n"
                                 "http://zz:yy@127.0.0.1:%d/%s/%s/101.ts\n" % (port, USER, PASS))
                recorder = ArgvRecorder(tmp)
                result = subprocess.run(["bash", str(PROBE), playlist], capture_output=True,
                                        text=True, timeout=120, env=recorder.env(), cwd=tmp)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                records = recorder.records()
        finally:
            server.shutdown()
            server.server_close()
        # The credentials still reach the provider: that is the script's job.
        self.assertTrue(seen, result.stdout)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(seen[0]).query)
        self.assertEqual(query.get("username"), [USER])
        self.assertEqual(query.get("password"), [PASS])
        # ...and never as an argument to anything the script starts.
        self.assertNotIn(USER, records)
        self.assertNotIn(PASS, records)
        # The host handed over names no userinfo.
        self.assertIn("PROBE_HOST=http://127.0.0.1:%d\n" % port, records)
        self.assertNotIn("zz:yy", records)
        # And the script's own output names none of it.
        for piece in (USER, PASS, "zz:yy"):
            self.assertNotIn(piece, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
