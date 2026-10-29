"""D-LOGO-12: MAX_LOGO_FILES is a ceiling on what one source's logo directory
HOLDS, not on what one run downloads.

The defect: `cmd_logos` compared the cap with `fetched`, the count of this
run's downloads, so the directory grew by up to the cap on every run. The
row's measurement, with the cap lowered to 2 against 7 safe logos over a
local TLS server, grew the cache 2, 4, 6, 7 across four runs; at the shipped
numbers a MAX_CHANNELS playlist reached 50,000 files over ten service starts
while the comments beside CACHE_SUBDIRS and inside cache_logos_clear called
5,000 a ceiling. The lead's rule: the ceiling the comments state must be TRUE
of what can be on disk.

How this module is shaped, and why:

* The cap is LOWERED (monkeypatched to 2 or 3) and the inputs are ordinary
  small logos -- the 501-byte `png-small` of the dimension fixture, served
  under different paths. Nothing here is large, and nothing is built to cost
  anything: the claim at the shipped cap is arithmetic over the code, stated
  in the helper's comments.
* The network is REAL: a TLS server on 127.0.0.1 in a thread of this
  process, with a self-signed certificate made by `openssl` as argv and
  trusted through SSL_CERT_FILE, so `fetch_logo` and `logo_opener` run as
  they ship. The server counts GETs, which is how "fetched nothing" is
  observed rather than read off the helper's own summary.
* `cmd_logos` runs in this process (the cap has no command-line lever, and
  one that could also raise it would be a disclosure lever), and the
  directory is counted with `os.listdir` by the test, not by the helper.
"""
import argparse
import contextlib
import http.server
import io
import json
import os
import pathlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper, loopback_reads_public

helper = load_helper()

HERE = pathlib.Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "logo-dimensions.json"
PNG = bytes.fromhex(next(c["hex"] for c in json.loads(FIXTURE.read_text(encoding="ascii"))["cases"]
                         if c["id"] == "png-small"))
CEILING_LINE = "the logo folder holds"


@unittest.skipUnless(shutil.which("openssl"), "openssl is needed to make a certificate")
class LogoCeilingOverTlsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.mkdtemp()
        key, cert = os.path.join(cls.work, "k.pem"), os.path.join(cls.work, "c.pem")
        made = subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                               "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
                               "-keyout", key, "-out", cert], capture_output=True, timeout=60)
        if made.returncode != 0:
            shutil.rmtree(cls.work, True)
            raise unittest.SkipTest("openssl could not make a certificate: %r" % made.stderr[-200:])
        cls.cert = cert
        cls.gets = []
        gets = cls.gets

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                gets.append(self.path)
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(PNG)))
                self.end_headers()
                self.wfile.write(PNG)

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        cls.server = server
        cls.thread = threading.Thread(target=server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        shutil.rmtree(cls.work, True)

    def setUp(self):
        self.gets.clear()
        # D-SINK-40: a logo never reaches this machine, and the fixture
        # server is on it; the one seam (helper_loader.loopback_reads_public)
        # makes 127.0.0.1 read public for these tests of the run's other rules.
        seam = loopback_reads_public(helper)
        seam.start()
        self.addCleanup(seam.stop)
        self.cache = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.cache, True)
        self.logo_dir = os.path.join(self.cache, helper.LOGO_SUBDIR)
        saved = os.environ.get("SSL_CERT_FILE")
        os.environ["SSL_CERT_FILE"] = self.cert

        def restore():
            if saved is None:
                os.environ.pop("SSL_CERT_FILE", None)
            else:
                os.environ["SSL_CERT_FILE"] = saved
        self.addCleanup(restore)

    def url(self, i):
        return "https://127.0.0.1:%d/logo-%d.png" % (self.port, i)

    def write_channels(self, count):
        urls = [self.url(i) for i in range(count)]
        with open(os.path.join(self.cache, helper.CHANNELS_FILE), "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "count": count, "channels": [
                {"id": "c%d" % i, "name": "C%d" % i, "group": "G", "url": "http://127.0.0.1/%d" % i,
                 "logo": u} for i, u in enumerate(urls)]}, handle)
        return urls

    def plant(self, i, data):
        os.makedirs(self.logo_dir, mode=0o700, exist_ok=True)
        path = os.path.join(self.logo_dir, helper.logo_filename(self.url(i)))
        with open(path, "wb") as handle:
            handle.write(data)
        return os.path.basename(path)

    def run_fetch(self, cap):
        """One `logos --fetch` run with the ceiling lowered to `cap`.
        -> (summary, announced names, stderr text)."""
        real = helper.MAX_LOGO_FILES
        helper.MAX_LOGO_FILES = cap
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = helper.cmd_logos(argparse.Namespace(cache_dir=self.cache, fetch=True,
                                                           survey=False, timeout=5))
        finally:
            helper.MAX_LOGO_FILES = real
        self.assertEqual(code, 0, err.getvalue())
        lines = [json.loads(l) for l in out.getvalue().splitlines() if l.strip()]
        return lines[-1], [l["name"] for l in lines if l.get("kind") == "logo"], err.getvalue()

    def on_disk(self):
        try:
            return len(os.listdir(self.logo_dir))
        except FileNotFoundError:
            return 0

    def test_the_directory_never_holds_more_than_the_ceiling_across_runs(self):
        """The row's own measurement, rerun: 7 ordinary logos, the cap at 2,
        four runs. It grew 2, 4, 6, 7 on f55a32f; it must stay at 2, with one
        round of GETs and none after."""
        self.write_channels(7)
        counts, summaries = [], []
        for _ in range(4):
            summary, announced, err = self.run_fetch(2)
            counts.append(self.on_disk())
            summaries.append(summary)
            self.assertEqual(sorted(announced), sorted(summary["names"]))
            # Said ONCE per run, counted, on stderr, carrying no URL.
            self.assertEqual(err.count(CEILING_LINE), 1, err)
            self.assertIn("ceiling is 2; 5 logos were not fetched", err)
            self.assertNotIn("127.0.0.1", err)
        self.assertEqual(counts, [2, 2, 2, 2], "the logo directory outgrew its ceiling")
        self.assertEqual(len(self.gets), 2, "only the first run had room to fetch")
        first = summaries[0]
        self.assertEqual((first["fetched"], first["cached"], first["deferred"]), (2, 0, 5), first)
        self.assertTrue(first["atCeiling"])
        self.assertEqual(first["files"], 2)
        self.assertEqual(first["cap"], 2)
        for later in summaries[1:]:
            self.assertEqual((later["fetched"], later["cached"], later["deferred"]), (0, 2, 5), later)
            self.assertEqual(later["files"], 2)
            self.assertEqual(sorted(later["names"]), sorted(first["names"]))

    def test_a_run_below_the_ceiling_fetches_everything_and_says_nothing(self):
        self.write_channels(3)
        summary, announced, err = self.run_fetch(3)
        self.assertEqual((summary["fetched"], summary["deferred"], summary["files"]), (3, 0, 3), summary)
        self.assertFalse(summary["atCeiling"])
        self.assertNotIn(CEILING_LINE, err)
        self.assertEqual(len(announced), 3)
        self.assertEqual(self.on_disk(), 3)

    def test_a_swept_file_frees_its_slot_and_its_url_is_fetched_into_it(self):
        """A cached file the check removes is no longer on disk, so the count
        falls with it and the refetch of the same URL fits."""
        sound = self.plant(0, PNG)
        self.plant(1, b"\x89PNG\r\n\x1a\n")       # a signature and nothing: unreadable, swept
        self.write_channels(4)
        summary, announced, err = self.run_fetch(2)
        self.assertEqual(summary["swept"], 1, summary)
        self.assertEqual(summary["cached"], 1, summary)
        self.assertEqual(summary["fetched"], 1, summary)
        self.assertEqual(self.gets, ["/logo-1.png"])
        self.assertEqual(summary["deferred"], 2, summary)
        self.assertEqual(self.on_disk(), 2)
        self.assertIn(sound, announced)

    def test_a_directory_an_older_version_left_fuller_is_never_grown(self):
        """0.14.3 and earlier could leave up to 5,000 files per run. This
        version announces what is there and adds nothing."""
        planted = [self.plant(i, PNG) for i in range(3)]
        self.write_channels(6)
        summary, announced, err = self.run_fetch(2)
        self.assertEqual(self.gets, [])
        self.assertEqual(self.on_disk(), 3)
        self.assertEqual(sorted(announced), sorted(planted))
        self.assertEqual((summary["cached"], summary["fetched"], summary["deferred"]), (3, 0, 3), summary)
        self.assertEqual(summary["files"], 3)
        self.assertTrue(summary["atCeiling"])

    def test_every_entry_counts_whatever_it_is(self):
        """A `.tmp-` file a killed write left and a stray directory are on
        disk, so they are counted: the ceiling is a claim about the
        directory, not about the names this run recognises."""
        os.makedirs(os.path.join(self.logo_dir, "stray"), mode=0o700)
        with open(os.path.join(self.logo_dir, ".tmp-left-behind"), "wb") as handle:
            handle.write(PNG)
        self.write_channels(3)
        summary, _, _ = self.run_fetch(3)
        self.assertEqual(self.gets, ["/logo-0.png"])
        self.assertEqual((summary["fetched"], summary["deferred"], summary["files"]), (1, 2, 3), summary)
        self.assertEqual(self.on_disk(), 3)

    def test_a_directory_that_cannot_be_listed_counts_as_full_and_contacts_nobody(self):
        """A file where the logo folder should be: the count cannot be taken,
        so nothing is fetched -- and no logo host is contacted for a write
        that could not land anyway."""
        with open(self.logo_dir, "wb") as handle:
            handle.write(b"not a folder")
        self.assertEqual(helper.logo_dir_entries(self.logo_dir), helper.MAX_LOGO_FILES)
        self.assertEqual(helper.logo_dir_entries(os.path.join(self.cache, "absent")), 0)
        self.write_channels(2)
        summary, announced, _ = self.run_fetch(2)
        self.assertEqual(self.gets, [])
        self.assertEqual(announced, [])
        self.assertEqual(summary["deferred"], 2, summary)


class LogosWithoutAChannelListTest(unittest.TestCase):
    """D-SRC-45: `logos` over a source with no channel list answered
    `code: internal` with "HelperError:" in front of the sentence and a
    traceback on stderr -- a sentence dressed as a crash. It is the same
    absence `play` and `epg` already answer as `no_cache`."""

    def run_helper(self, *args):
        done = subprocess.run([sys.executable, str(helper_path()), *args],
                              capture_output=True, text=True, timeout=60, env=dict(os.environ))
        lines = [l for l in done.stdout.splitlines() if l.strip()]
        return done, json.loads(lines[-1]) if lines else None

    def test_both_forms_answer_no_cache_in_one_plain_sentence(self):
        with tempfile.TemporaryDirectory() as tmp:
            for extra in ([], ["--fetch"]):
                done, payload = self.run_helper("logos", "--cache-dir", tmp, *extra)
                self.assertEqual(done.returncode, 1, extra)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["kind"], "logos")
                self.assertEqual(payload["action"], "fetch" if extra else "survey")
                self.assertEqual(payload["error"]["code"], "no_cache", payload)
                message = payload["error"]["message"]
                self.assertNotIn("HelperError", message)
                self.assertNotIn("Traceback", done.stderr)
                self.assertEqual(message, "This source has no channel list yet; refresh the playlist first.")
                self.assertEqual(message.count("."), 1, "one sentence")
                # Nothing was created for a source that is not there.
                self.assertEqual(os.listdir(tmp), [])


def helper_path():
    return pathlib.Path(__file__).resolve().parent.parent / "bin" / "omarchy-iptv"


if __name__ == "__main__":
    unittest.main()
