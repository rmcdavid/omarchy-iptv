"""`logos --fetch` as a bounded run: its deadlines, its memory limit, its
lock, its ceiling's sweep, its folder's age, and the line the shell reads.

R30e (D-LOGO-15, D-LOGO-16): one logo had no wall-clock bound -- a host
sending a byte inside every 10 s read timeout held it for days -- and the run
had none either; a redirect's body was read whole, uncapped; and the verb ran
without the memory limit the playlist and epg verbs run under. R30b
(D-LOGO-18): two runs on one source could together pass the ceiling, and at
the ceiling files no channel names any more kept their slots. R30a
(D-LOGO-17): nothing aged a kept source's logo folder. D-SRC-60: a killed
write's temporary held a slot under the ceiling. R30c: the shell's one line.

By the project's input rule, every server is a ScriptedServer
(tests/scripted_server.py) giving an ordinary small logo a fixed fraction of
a second later than the deadline the test lowers, over real TLS with a
throwaway certificate trusted through SSL_CERT_FILE, as tests/
test_logo_ceiling.py does; where no network is needed, `fetch_logo` is a
double with the real signature. Caps and ages are lowered, never filled.
"""
import argparse
import contextlib
import fcntl
import io
import json
import os
import pathlib
import resource
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper          # redirects HOME and $XDG_* first
from scripted_server import ScriptedServer, response
from test_reply_bounds import PROBE, PROBE_LIMIT_MIB, LIMIT_ENV

helper = load_helper()

HERE = pathlib.Path(__file__).resolve().parent
HELPER = HERE.parent / "bin" / "omarchy-iptv"
DEADLINES = json.loads((HERE / "fixtures" / "logo-deadlines.json").read_text(encoding="utf-8"))
PNG = bytes.fromhex(next(c["hex"] for c in json.loads((HERE / "fixtures" / "logo-dimensions.json").read_text(encoding="ascii"))["cases"]
                         if c["id"] == "png-small"))
# The form the helper caches (D-LOGO-13): a file planted in it is announced
# as it stands, so a run over it writes nothing into the folder.
CANON = helper.canonical_png(PNG)
LOGO = response("200 OK", (("Content-Type", "image/png"),), PNG)
LATE = 0.9
BEFORE_LATE = 0.8


def png_double(url, timeout, budget=None):
    """fetch_logo with its real signature, for the runs that need no network."""
    return PNG, "image/png"


def with_text_chunk(png):
    """The same PNG with a tEXt chunk after IHDR: valid, drawn identically,
    and NOT canonical (D-LOGO-13), so the cached-file pass rewrites it."""
    import zlib
    body = b"Comment\x00made for a test"
    chunk = len(body).to_bytes(4, "big") + b"tEXt" + body + zlib.crc32(b"tEXt" + body).to_bytes(4, "big")
    ihdr_end = 8 + 4 + 4 + 13 + 4
    return png[:ihdr_end] + chunk + png[ihdr_end:]


NOT_CANON = with_text_chunk(PNG)


class LogoRunCase(unittest.TestCase):
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

    def plant(self, name, data=CANON, age=None):
        self.logo_dir.mkdir(mode=0o700, exist_ok=True)
        path = self.logo_dir / name
        path.write_bytes(data)
        if age is not None:
            when = time.time() - age
            os.utime(path, (when, when))
        return path

    def run_fetch(self, fetcher=None, cap=None):
        """One in-process `logos --fetch` -> (exit, summary, announced, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with contextlib.ExitStack() as stack:
            if fetcher is not None:
                stack.enter_context(mock.patch.object(helper, "fetch_logo", fetcher))
            if cap is not None:
                stack.enter_context(mock.patch.object(helper, "MAX_LOGO_FILES", cap))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = helper.cmd_logos(argparse.Namespace(cache_dir=str(self.cache), fetch=True, survey=False, timeout=5))
        lines = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
        return code, lines[-1], [l["name"] for l in lines[:-1] if l.get("kind") == "logo"], err.getvalue()

    def on_disk(self):
        return sorted(os.listdir(self.logo_dir)) if self.logo_dir.is_dir() else []


@unittest.skipUnless(shutil.which("openssl"), "openssl is needed to make a certificate")
class LogoDeadlineOverTlsTest(LogoRunCase):
    """R30e over a real TLS server: one logo's deadline, the run's, and a
    redirect body nobody waits for."""

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

    def serve(self, routes):
        server = ScriptedServer(routes, self.context)
        self.addCleanup(server.close)
        return server

    def timed_fetch(self):
        started = time.monotonic()
        result = self.run_fetch()
        return result, time.monotonic() - started

    def test_a_logo_later_than_its_deadline_fails_and_the_others_arrive(self):
        server = self.serve({"/a.png": (LOGO,), "/slow.png": (LATE, LOGO), "/b.png": (LOGO,)})
        self.write_channels([server.url("/a.png"), server.url("/slow.png"), server.url("/b.png")])
        with mock.patch.object(helper, "LOGO_DEADLINE", 0.5, create=True):
            (code, summary, announced, _), elapsed = self.timed_fetch()
        self.assertEqual(code, 0)
        self.assertEqual((summary["fetched"], summary["failed"]), (2, 1), summary)
        self.assertEqual(summary["reasons"], {"logo_timeout": 1}, summary)
        self.assertEqual(len(announced), 2)
        self.assertLess(elapsed, BEFORE_LATE + 0.3, "the slow logo was waited for (%.2f s)" % elapsed)

    def test_the_run_starts_no_fetch_after_its_deadline(self):
        each = (0.25, LOGO)
        server = self.serve({"/%d.png" % i: each for i in range(5)})
        self.write_channels([server.url("/%d.png" % i) for i in range(5)])
        with mock.patch.object(helper, "LOGO_RUN_DEADLINE", 0.6, create=True):
            (code, summary, _, stderr), elapsed = self.timed_fetch()
        self.assertEqual(code, 0)
        self.assertIs(summary.get("runExpired"), True, summary)
        self.assertGreaterEqual(summary.get("postponed") or 0, 1, summary)
        self.assertEqual(summary["fetched"] + summary["failed"] + (summary.get("postponed") or 0), 5, summary)
        # A postponed logo is never requested.
        self.assertEqual(len(server.paths), summary["fetched"] + summary["failed"], (server.paths, summary))
        self.assertLess(elapsed, 1.0, "the run went on past its deadline (%.2f s)" % elapsed)
        self.assertIn("left for the next run", stderr)

    def test_a_logo_redirect_whose_body_is_late_is_followed_at_once(self):
        server = self.serve({})
        redirect = response("302 Found", (("Location", server.url("/real.png")), ("Content-Length", "20")))
        server.routes.update({"/r.png": (redirect, LATE, b"x" * 20), "/real.png": (LOGO,)})
        self.write_channels([server.url("/r.png")])
        with mock.patch.object(helper, "LOGO_DEADLINE", 0.5, create=True):
            (code, summary, announced, _), elapsed = self.timed_fetch()
        self.assertEqual(summary["fetched"], 1, summary)
        self.assertEqual(server.paths, ["/r.png", "/real.png"])
        self.assertLess(elapsed, BEFORE_LATE, "the redirect's body was waited for (%.2f s)" % elapsed)


class LogoMemoryLimitTest(LogoRunCase):
    """R30e: `logos --fetch` runs under the data limit the playlist and epg
    verbs run under, observed in a real helper process at the open of a
    cached logo, and lifted before the summary is printed (D-M3U-3)."""

    def test_the_run_holds_the_limit_and_lifts_it_before_the_summary(self):
        soft = resource.getrlimit(resource.RLIMIT_DATA)[0]
        limit = PROBE_LIMIT_MIB * 1024 * 1024
        if soft != resource.RLIM_INFINITY and soft <= limit:
            self.skipTest("this process already runs under a data limit")
        url = "https://logos.example.test/a.png"
        self.write_channels([url])
        cached = self.plant(helper.logo_filename(url)).name
        record = self.root / "record.json"
        env = dict(os.environ)
        env[LIMIT_ENV] = str(PROBE_LIMIT_MIB)
        done = subprocess.run([sys.executable, "-c", PROBE, str(record), str(HELPER), "logos", "--fetch",
                               "--cache-dir", str(self.cache)], capture_output=True, text=True, env=env, timeout=60)
        result = json.loads(record.read_text(encoding="utf-8"))
        summary = json.loads(done.stdout.strip().splitlines()[-1])
        self.assertEqual(summary["cached"], 1, done.stderr)
        held = [s for kind, name, s in result["events"] if kind == "open" and name == cached]
        self.assertTrue(held, result["events"])
        self.assertEqual(set(held), {limit}, result["events"])
        stdout = [s for kind, _, s in result["events"] if kind == "stdout"]
        self.assertEqual(stdout[-1], result["baseline"], "the summary was printed under the limit")
        self.assertEqual(result["end"], result["baseline"])


class LogoFolderLockTest(LogoRunCase):
    """R30b: one run per source's logo folder; a second answers busy,
    counted, and fetches nothing."""

    def test_a_second_run_answers_busy_and_fetches_nothing(self):
        self.write_channels(["https://logos.example.test/%d.png" % i for i in range(3)])
        self.logo_dir.mkdir(mode=0o700)
        holder = os.open(self.logo_dir, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, holder)
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        calls = []

        def fetcher(url, timeout, budget=None):
            calls.append(url)
            return PNG, "image/png"
        code, summary, announced, stderr = self.run_fetch(fetcher)
        self.assertEqual(code, 0)
        self.assertEqual(calls, [])
        self.assertEqual(announced, [])
        self.assertIs(summary.get("busy"), True, summary)
        self.assertEqual(summary["wouldContact"], 3)
        # D-LOGO-23: a busy run ANSWERS `names` -- what is on disk and passes
        # the check, here nothing -- so the shell's set is replaced, never
        # left stale (the first version answered no field at all).
        self.assertEqual((summary.get("names"), summary.get("cached")), ([], 0), summary)
        self.assertEqual(self.on_disk(), [])
        self.assertIn("another logo fetch is running", stderr)

    def test_a_busy_run_announces_what_is_present_and_writes_nothing(self):
        # D-LOGO-23 (R32f): the cached files that pass the check as they
        # stand are announced; a PNG that would need rewriting, a file that
        # fails the check and a stale temporary are all left EXACTLY as they
        # are, and the folder is not marked: the run holding the lock does
        # that work, and this one may write nothing.
        urls = ["https://logos.example.test/%d.png" % i for i in range(4)]
        self.write_channels(urls + [urls[0]])                 # one URL twice: announced once
        good = self.plant(helper.logo_filename(urls[0])).name
        self.plant(helper.logo_filename(urls[1]), NOT_CANON)
        self.plant(helper.logo_filename(urls[2]), b"not an image at all")
        self.plant(".tmp-0000beef-0123abcd", b"half a logo", age=2 * 86400)
        when = time.time() - 2 * 86400
        os.utime(self.logo_dir, (when, when))
        before = {name: (self.logo_dir / name).read_bytes() for name in self.on_disk()}
        holder = os.open(self.logo_dir, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, holder)
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        calls = []

        def fetcher(url, timeout, budget=None):
            calls.append(url)
            return PNG, "image/png"
        code, summary, announced, stderr = self.run_fetch(fetcher)
        self.assertEqual((code, calls), (0, []))
        self.assertEqual(announced, [good])
        self.assertEqual((summary.get("busy"), summary.get("fetched"), summary.get("cached"), summary.get("names")),
                         (True, 0, 1, [good]), summary)
        self.assertNotIn("rewritten", summary)
        self.assertNotIn("swept", summary)
        after = {name: (self.logo_dir / name).read_bytes() for name in self.on_disk()}
        self.assertEqual(after, before, "a busy run wrote, rewrote or swept something")
        self.assertLess(abs(os.stat(self.logo_dir).st_mtime - when), 1, "a busy run marked the folder")
        self.assertIn("another logo fetch is running", stderr)
        # The same folder, once the holder has let go: the run that holds the
        # lock rewrites the PNG and sweeps the junk, and announces both the
        # canonical files.
        fcntl.flock(holder, fcntl.LOCK_UN)
        code, summary, announced, _ = self.run_fetch(fetcher)
        self.assertEqual((summary["busy"], summary["rewritten"], summary["swept"]), (False, 1, 1), summary)
        self.assertEqual(sorted(summary["names"]), sorted([good, helper.logo_filename(urls[1]),
                                                           helper.logo_filename(urls[2]), helper.logo_filename(urls[3])]))

    def test_a_url_that_failed_is_not_tried_again_within_the_run(self):
        # D-LOGO-22 (R32f): the run's `seen` set is its memory of every URL,
        # failed ones included -- a URL named by two channels that times out,
        # is refused or answers 404 is tried once a run. ACROSS runs it is
        # tried again, as before, and that is pinned here as it stands.
        dead = ["https://dead.example.test/a.png", "https://dead.example.test/b.png"]
        live = "https://logos.example.test/c.png"
        self.write_channels([dead[0], dead[1], dead[0], dead[1], live, dead[0]])
        calls = []

        def fetcher(url, timeout, budget=None):
            calls.append(url)
            if url in dead:
                raise helper.HelperError("logo_fetch", "could not fetch a logo from dead.example.test: TimeoutError")
            return PNG, "image/png"
        code, summary, _, _ = self.run_fetch(fetcher)
        self.assertEqual((code, calls), (0, [dead[0], dead[1], live]))
        self.assertEqual((summary["failed"], summary["fetched"], summary["reasons"]), (2, 1, {"logo_fetch": 2}), summary)
        del calls[:]
        self.run_fetch(fetcher)
        self.assertEqual(calls, [dead[0], dead[1]], "across runs a failed URL is tried again (stated, not changed)")

    def test_a_logo_gets_no_more_than_what_is_left_of_the_run(self):
        # The round-2 recheck's M8: `min(LOGO_DEADLINE, remaining)` replaced
        # by LOGO_DEADLINE kept every test green. With the run's deadline
        # lowered below one logo's, every budget handed to fetch_logo must be
        # what is left of the run, never the logo's own 30 s.
        self.write_channels(["https://logos.example.test/%d.png" % i for i in range(3)])
        budgets = []

        def fetcher(url, timeout, budget=None):
            budgets.append(budget)
            return PNG, "image/png"
        with mock.patch.object(helper, "LOGO_RUN_DEADLINE", 0.6, create=True):
            code, summary, _, _ = self.run_fetch(fetcher)
        self.assertEqual((code, summary["fetched"]), (0, 3), summary)
        self.assertEqual(len(budgets), 3)
        for budget in budgets:
            self.assertIsNotNone(budget)
            self.assertGreater(budget, 0)
            self.assertLessEqual(budget, 0.6, budgets)
            self.assertLess(budget, helper.LOGO_DEADLINE, budgets)

    def test_the_lock_is_let_go_when_the_run_ends(self):
        self.write_channels(["https://logos.example.test/a.png"])
        self.assertIs(self.run_fetch(png_double)[1].get("busy"), False)
        self.assertIs(self.run_fetch(png_double)[1].get("busy"), False)
        probe = os.open(self.logo_dir, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, probe)
        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)        # raises if a run still held it

    def test_nothing_to_fetch_makes_no_folder(self):
        # The real fetch_logo: an http logo is refused before any connection.
        self.write_channels(["http://not-https.example.test/a.png", ""])
        code, summary, _, _ = self.run_fetch()
        self.assertEqual((code, summary["refusedOnPolicy"]), (0, 1), summary)
        self.assertFalse(self.logo_dir.exists())


class CeilingSweepTest(LogoRunCase):
    """R30b: at the ceiling, before a logo is counted as held back, the files
    no channel of the current playlist names are swept, once a run."""

    def test_unnamed_files_give_their_slots_to_new_logos(self):
        urls = ["https://logos.example.test/%d.png" % i for i in range(3)]
        self.write_channels(urls)
        named = self.plant(helper.logo_filename(urls[0])).name
        self.plant("00000001", b"an old logo")
        self.plant("00000002", b"another")
        self.plant("notes.txt", b"not a logo's name")         # stays, and counts
        code, summary, announced, _ = self.run_fetch(png_double, cap=4)
        self.assertEqual(code, 0)
        self.assertEqual((summary.get("unnamed"), summary["fetched"], summary["deferred"], summary["files"]),
                         (2, 2, 0, 4), summary)
        self.assertEqual(self.on_disk(), sorted([named, helper.logo_filename(urls[1]),
                                                 helper.logo_filename(urls[2]), "notes.txt"]))
        self.assertIs(summary["atCeiling"], False)

    def test_a_file_a_later_channel_names_is_kept(self):
        urls = ["https://logos.example.test/%d.png" % i for i in range(3)]
        self.write_channels(urls)
        later = self.plant(helper.logo_filename(urls[2])).name
        self.plant("0000000a", b"unnamed")
        code, summary, announced, _ = self.run_fetch(png_double, cap=2)
        self.assertEqual((summary.get("unnamed"), summary["fetched"], summary["deferred"]), (1, 1, 1), summary)
        self.assertIn(later, self.on_disk())
        self.assertIn(later, summary["names"])
        self.assertIs(summary["atCeiling"], True)

    def test_a_stale_temporary_gives_its_slot_back(self):
        # D-SRC-60: a temporary a killed write left is swept before the
        # folder is counted (STALE_TEMP_AGE, a day: this one is two).
        urls = ["https://logos.example.test/%d.png" % i for i in range(2)]
        self.write_channels(urls)
        self.plant(helper.logo_filename(urls[0]))
        self.plant(".tmp-0000beef-0123abcd", b"half a logo", age=2 * 86400)
        code, summary, _, _ = self.run_fetch(png_double, cap=2)
        self.assertEqual((summary.get("staleTemps"), summary["fetched"], summary["deferred"]), (1, 1, 0), summary)
        self.assertNotIn(".tmp-0000beef-0123abcd", self.on_disk())


class LogoFolderAgeTest(LogoRunCase):
    """R30a (D-LOGO-17): a run marks its folder when it ends, and `cache
    prune` removes a kept, non-active source's folder once no run has ended
    in it for --epg-max-age seconds (lowered here to 60)."""

    def age(self, path, seconds):
        when = time.time() - seconds
        os.utime(path, (when, when))

    def test_a_run_marks_its_folder_even_when_it_fetches_nothing(self):
        url = "https://logos.example.test/a.png"
        self.write_channels([url])
        self.plant(helper.logo_filename(url))
        self.age(self.logo_dir, 2 * 86400)
        calls = []

        def fetcher(url, timeout, budget=None):
            calls.append(url)
            return PNG, "image/png"
        code, summary, _, _ = self.run_fetch(fetcher)
        self.assertEqual((code, summary["cached"], summary["rewritten"], calls), (0, 1, 0, []))
        self.assertLess(time.time() - os.stat(self.logo_dir).st_mtime, 60)

    def test_a_run_marks_its_folder_before_its_first_fetch(self):
        # R32f (the round-2 recheck's README sentence b): the mark used to be
        # made only in cmd_logos's `finally`, which a SIGTERM -- a source
        # switch, the setting turned off, the watchdog -- never reaches, so a
        # run that wrote nothing left the folder's older time and the next
        # prune could age a folder a fetch had just run in. Now the start
        # marks it too: the time a fetch SEES on the folder is fresh.
        urls = ["https://logos.example.test/%d.png" % i for i in range(2)]
        self.write_channels(urls)
        self.plant(helper.logo_filename(urls[0]))
        self.age(self.logo_dir, 2 * 86400)
        seen = []

        def fetcher(url, timeout, budget=None):
            seen.append(time.time() - os.stat(self.logo_dir).st_mtime)
            raise helper.HelperError("logo_fetch", "a refusal, so the write cannot be what marked it")
        code, summary, _, _ = self.run_fetch(fetcher)
        self.assertEqual((code, summary["cached"], summary["failed"], len(seen)), (0, 1, 1, 1), summary)
        self.assertLess(seen[0], 60, "the folder was not marked before the first fetch")

    def test_prune_leaves_a_folder_a_run_holds_and_says_so_once(self):
        # D-LOGO-21 (R32f): age_logo_folder takes the folder's flock, the one
        # a running `logos --fetch` holds; a held folder is skipped, named in
        # `busyLogos`, said once on stderr for however many, and aged at the
        # next prune once the run has let go.
        held = [self.seed("22222222", logo_age=120), self.seed("44444444", logo_age=120)]
        free = self.seed("33333333", logo_age=120)
        holders = []
        for folder in held:
            fd = os.open(folder / helper.LOGO_SUBDIR, os.O_RDONLY | os.O_DIRECTORY)
            self.addCleanup(os.close, fd)
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            holders.append(fd)
        code, payload = self.prune("prune", "--keep", "22222222", "33333333", "44444444", "--epg-max-age", "60")
        self.assertEqual(code, 0, payload)
        self.assertEqual((payload.get("busyLogos"), payload.get("agedLogos")), (["22222222", "44444444"], ["33333333"]), payload)
        for folder in held:
            self.assertTrue((folder / helper.LOGO_SUBDIR / "0000aaaa").exists(), "a held folder was aged")
        self.assertFalse((free / helper.LOGO_SUBDIR).exists())
        lines = [line for line in self.last_stderr.splitlines() if "held by" in line]
        self.assertEqual(len(lines), 1, self.last_stderr)
        self.assertIn("2 logo folders are held by running fetches", lines[0])
        for leak in ("22222222", "44444444", "/"):
            self.assertNotIn(leak, lines[0])
        for fd in holders:
            fcntl.flock(fd, fcntl.LOCK_UN)
        code, payload = self.prune("prune", "--keep", "22222222", "33333333", "44444444", "--epg-max-age", "60")
        self.assertEqual((payload.get("busyLogos"), payload.get("agedLogos")), ([], ["22222222", "44444444"]), payload)

    def seed(self, key, logo_age=None):
        folder = self.root / "sources" / key
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        (folder / helper.CHANNELS_FILE).write_text("{}", encoding="utf-8")
        logos = folder / helper.LOGO_SUBDIR
        if logo_age is not None:
            logos.mkdir(mode=0o700)
            (logos / "0000aaaa").write_bytes(PNG)
            self.age(logos, logo_age)
        return folder

    def prune(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = helper.main(["cache", "--cache-dir", str(self.root)] + list(argv))
        self.last_stderr = err.getvalue()
        return code, json.loads(out.getvalue().strip().splitlines()[-1])

    def test_prune_ages_the_logo_folders_of_kept_inactive_sources(self):
        active = self.seed("11111111", logo_age=120)
        old = self.seed("22222222", logo_age=120)
        young = self.seed("33333333", logo_age=10)
        code, payload = self.prune("prune", "--keep", "22222222", "33333333", "--active", "11111111",
                                   "--epg-max-age", "60")
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload.get("agedLogos"), ["22222222"], payload)
        self.assertFalse((old / helper.LOGO_SUBDIR).exists())
        self.assertTrue((old / helper.CHANNELS_FILE).exists())          # the source stays
        self.assertTrue((active / helper.LOGO_SUBDIR / "0000aaaa").exists())
        self.assertTrue((young / helper.LOGO_SUBDIR / "0000aaaa").exists())

    def test_prune_sweeps_stale_temporaries_of_kept_inactive_sources(self):
        folder = self.seed("22222222", logo_age=10)
        for path in (folder / ".tmp-channels.json-0123abcd", folder / helper.LOGO_SUBDIR / ".tmp-0000aaaa-0123abcd"):
            path.write_text("left", encoding="utf-8")
            self.age(path, 2 * 86400)
        self.age(folder / helper.LOGO_SUBDIR, 10)
        code, payload = self.prune("prune", "--keep", "22222222", "--epg-max-age", "60")
        self.assertEqual(payload.get("staleTemps"), 2, payload)
        self.assertEqual(sorted(os.listdir(folder)), [helper.CHANNELS_FILE, helper.LOGO_SUBDIR])
        self.assertEqual(os.listdir(folder / helper.LOGO_SUBDIR), ["0000aaaa"])


class SharedFixtureTest(LogoRunCase):
    """tests/fixtures/logo-deadlines.json, the other half of which
    tests/Model.test.js runs: the helper's deadlines are the fixture's, and
    the summary carries every field Model.logoSummaryNotice reads."""

    def test_the_deadlines_are_the_fixtures(self):
        self.assertEqual(int(helper.LOGO_DEADLINE * 1000), DEADLINES["logoMs"])
        self.assertEqual(int(helper.LOGO_RUN_DEADLINE * 1000), DEADLINES["runMs"])
        self.assertEqual(DEADLINES["watchdogMs"], DEADLINES["runMs"] + DEADLINES["logoMs"] + DEADLINES["marginMs"])

    def test_the_summary_carries_every_field_the_shell_reads(self):
        kinds = {"boolean": bool, "number": int}
        self.write_channels(["https://logos.example.test/a.png"])
        _, summary, _, _ = self.run_fetch(png_double)
        self.logo_dir.mkdir(exist_ok=True)
        holder = os.open(self.logo_dir, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, holder)
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _, busy, _, _ = self.run_fetch(png_double)
        self.assertIs(busy["busy"], True)
        for field, kind in DEADLINES["summaryFields"].items():
            self.assertIn(field, summary)
            self.assertIs(type(summary[field]), kinds[kind], field)


if __name__ == "__main__":
    unittest.main()
