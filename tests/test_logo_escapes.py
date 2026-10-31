"""D-LOGO-24 (2026-10-29): one logo's error costs that logo, never the run.

`read_logo_response` caught URLError, OSError and ValueError, and
http.client's own errors are none of those: a status line that is not one,
a header line or a header count over http.client's limits, a chunked body
that does not parse, and InvalidURL -- raised before any connection for a
logo URL with a space in its path or a port that is not a number -- reached
main()'s `internal`. The run ended there, before the failure memo was
saved, so the same logo ended every later run the same way and no logo
after it in channel order was ever fetched; InvalidURL's text, which quotes
the path and query, was printed on stdout and in the traceback. The
playlist path has caught http.client.HTTPException since D-SRC-59.

Now: the catch on the logo path (`logo_fetch`, the class name only), a
backstop in the run for whatever escapes next, the memo saved in a
`finally`, and the cached-file check under the same backstop.

Every server is a ScriptedServer over real TLS with a throwaway
certificate, finite and small, as tests/test_logo_run.py's are; the one
seam (helper_loader.loopback_reads_public) lets 127.0.0.1 read public for
these tests of the run's other rules (D-SINK-40 refuses it otherwise).
"""
import argparse
import contextlib
import io
import json
import os
import pathlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper, loopback_reads_public  # redirects HOME and $XDG_* first
from scripted_server import ScriptedServer, response

helper = load_helper()

HERE = pathlib.Path(__file__).resolve().parent
PNG = bytes.fromhex(next(c["hex"] for c in json.loads((HERE / "fixtures" / "logo-dimensions.json").read_text(encoding="ascii"))["cases"]
                         if c["id"] == "png-small"))
LOGO = response("200 OK", (("Content-Type", "image/png"),), PNG)
SECRET = "LOGOSECRET123"


class LogoEscapeCase(unittest.TestCase):
    def setUp(self):
        getattr(helper, "SWEPT_TEMP_DIRS", set()).clear()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        self.cache = self.root / "sources" / "0123abcd"
        self.cache.mkdir(parents=True, mode=0o700)
        self.logo_dir = self.cache / helper.LOGO_SUBDIR

    def write_channels(self, urls):
        doc = {"version": 1, "count": len(urls), "channels": [
            {"id": "c%d" % i, "name": "C%d" % i, "group": "G", "url": "http://127.0.0.1/%d" % i, "logo": u}
            for i, u in enumerate(urls)]}
        (self.cache / helper.CHANNELS_FILE).write_text(json.dumps(doc), encoding="utf-8")

    def run_fetch(self, fetcher=None):
        """One in-process `logos --fetch` -> (exit, last line, announced, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            if fetcher is not None:
                stack.enter_context(mock.patch.object(helper, "fetch_logo", fetcher))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = helper.main(["logos", "--fetch", "--cache-dir", str(self.cache), "--timeout", "5"])
        lines = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
        announced = [l["name"] for l in lines[:-1] if l.get("kind") == "logo"]
        return code, lines[-1], announced, out.getvalue(), err.getvalue()

    def memo(self):
        path = self.cache / helper.LOGO_FAILED_FILE
        if not path.exists():
            return None
        return {name: entry["reason"] for name, entry in json.loads(path.read_text(encoding="utf-8"))["failed"].items()}


@unittest.skipUnless(shutil.which("openssl"), "openssl is needed to make a certificate")
class HttpClientErrorsTest(LogoEscapeCase):
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
        cls.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cls.context.load_cert_chain(cert, key)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.work, True)

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {"SSL_CERT_FILE": self.cert})
        patcher.start()
        self.addCleanup(patcher.stop)
        seam = loopback_reads_public(helper)
        seam.start()
        self.addCleanup(seam.stop)
        self.server = ScriptedServer({
            "/garbage.png": (b"GARBAGE-STATUS-LINE\r\n\r\n",),
            "/long-status.png": (b"HTTP/1.1 200 " + b"A" * 66000 + b"\r\n\r\n",),
            "/headers.png": (response("200 OK", tuple(("X-H%d" % i, "v") for i in range(150))
                                      + (("Content-Type", "image/png"),), PNG),),
            "/chunk.png": (response("200 OK", (("Content-Type", "image/png"), ("Transfer-Encoding", "chunked"))) + b"ZZZZ\r\n\r\n",),
            "/good.png": (LOGO,),
        }, self.context)
        self.addCleanup(self.server.close)
        self.port = self.server.port
        # Before the server's paths: two that never connect at all.
        self.urls = ["https://127.0.0.1:%d/img/My Logo.png?token=%s" % (self.port, SECRET),
                     "https://127.0.0.1:abc/x.png",
                     self.server.url("/garbage.png"), self.server.url("/long-status.png"),
                     self.server.url("/headers.png"), self.server.url("/chunk.png"),
                     self.server.url("/good.png")]

    def test_each_error_costs_its_own_logo_and_the_run_goes_on(self):
        self.write_channels(self.urls)
        code, summary, announced, stdout, stderr = self.run_fetch()
        self.assertEqual(code, 0, stderr)
        self.assertTrue(summary["ok"], summary)
        self.assertEqual((summary["fetched"], summary["failed"]), (1, 6), summary)
        self.assertEqual(summary["reasons"], {"logo_fetch": 6}, summary)
        self.assertEqual(announced, [helper.logo_filename(self.urls[-1])])
        self.assertEqual(self.server.paths, ["/garbage.png", "/long-status.png", "/headers.png",
                                             "/chunk.png", "/good.png"],
                         "the two malformed URLs open no connection; every other logo is tried once")
        self.assertEqual(self.memo(), {helper.logo_filename(u): "logo_fetch" for u in self.urls[:-1]})
        # Each is mapped where it arises (read_logo_response), not by the
        # run's backstop, which would say so on stderr.
        self.assertNotIn("ended in", stderr)
        # Rule 5: InvalidURL's own text quotes the path and the query.
        for text in (stdout, stderr):
            self.assertNotIn(SECRET, text)
            self.assertNotIn("My Logo", text)

    def test_the_next_run_skips_them_from_the_memo(self):
        self.write_channels(self.urls)
        self.run_fetch()
        before = len(self.server.paths)
        code, summary, announced, _, stderr = self.run_fetch()
        self.assertEqual(code, 0, stderr)
        self.assertEqual((summary["skippedFailed"], summary["cached"], summary["fetched"]), (6, 1, 0), summary)
        self.assertEqual(len(self.server.paths), before, "a memoised logo was requested again")

    def test_read_logo_response_names_the_class_and_never_the_url(self):
        request = helper.urllib.request.Request(self.urls[0], headers={"User-Agent": "t"})
        opener = helper.logo_opener("127.0.0.1:%d" % self.port)
        with self.assertRaises(helper.HelperError) as caught:
            helper.read_logo_response(opener, request, 5, "127.0.0.1:%d" % self.port)
        self.assertEqual(caught.exception.code, "logo_fetch")
        self.assertTrue(caught.exception.message.endswith(": InvalidURL"), caught.exception.message)
        self.assertNotIn(SECRET, caught.exception.message)


class BackstopTest(LogoEscapeCase):
    """What read_logo_response does not map costs one logo too: the run's
    backstop, observed by making the fetch raise something nobody expects."""

    URLS = ["https://logos.example.test/odd.png", "https://logos.example.test/fine.png",
            "https://logos.example.test/after.png"]

    def test_an_unexpected_exception_is_that_logos_failure(self):
        self.write_channels(self.URLS)

        def fetcher(url, timeout, budget=None):
            if url.endswith("odd.png"):
                raise LookupError("https://logos.example.test/odd.png?" + SECRET)
            return PNG, "image/png"
        code, summary, announced, stdout, stderr = self.run_fetch(fetcher)
        self.assertEqual(code, 0, stderr)
        self.assertEqual((summary["fetched"], summary["failed"]), (2, 1), summary)
        self.assertEqual(summary["reasons"], {"logo_fetch": 1}, summary)
        self.assertEqual(len(announced), 2)
        self.assertEqual(self.memo(), {helper.logo_filename(self.URLS[0]): "logo_fetch"})
        self.assertIn("ended in LookupError", stderr)
        self.assertNotIn(SECRET, stdout + stderr)

    def test_a_memory_refusal_still_ends_the_run_and_the_memo_is_saved_first(self):
        """MemoryError is the run's own refusal (cmd_logos answers it as
        too_large), not one logo's: it still ends the run. What changed is
        that the memo of the failures before it is saved on the way out."""
        self.write_channels(self.URLS)

        def fetcher(url, timeout, budget=None):
            if url.endswith("odd.png"):
                raise helper.HelperError("logo_type", "refused text/html from logos.example.test")
            raise MemoryError()
        code, summary, _, _, stderr = self.run_fetch(fetcher)
        self.assertEqual(code, 1, stderr)
        self.assertEqual(summary["error"]["code"], "too_large", summary)
        self.assertEqual(self.memo(), {helper.logo_filename(self.URLS[0]): "logo_type"})

    def test_a_cached_file_the_check_cannot_judge_is_not_announced_and_the_run_goes_on(self):
        self.write_channels(self.URLS[:2])
        self.logo_dir.mkdir(mode=0o700)
        planted = self.logo_dir / helper.logo_filename(self.URLS[0])
        planted.write_bytes(helper.canonical_png(PNG))
        real = helper.logo_file_within_bounds

        def check(path):
            if os.path.basename(path) == planted.name:
                raise ValueError("a parser bug")
            return real(path)
        with mock.patch.object(helper, "logo_file_within_bounds", check):
            code, summary, announced, _, stderr = self.run_fetch(lambda url, timeout, budget=None: (PNG, "image/png"))
        self.assertEqual(code, 0, stderr)
        self.assertEqual((summary["cached"], summary["swept"], summary["fetched"]), (0, 1, 2), summary)
        self.assertEqual(sorted(announced), sorted(helper.logo_filename(u) for u in self.URLS[:2]))
        self.assertIn("check of a cached file ended in ValueError", stderr)


if __name__ == "__main__":
    unittest.main()
