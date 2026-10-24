"""The playlist, guide and probe download (read_http_source): one wall-clock
deadline over the whole fetch, redirect bodies never read, the status line's
text capped, and the atomic writers' leftovers swept.

R30e (D-SRC-58, D-LOGO-15's playlist half): the 60-second deadline was
checked only between body reads, after `open()` had returned, so connect,
TLS, the status line, the headers and every redirect -- whose BODY the
stdlib read whole -- ran outside it; and a chunked body's trailers, read
inside the last read1, could end a download that had overrun its deadline
and have it ACCEPTED. D-SRC-59: the server's raw first line reached the
replies whole. D-SRC-60: a killed atomic write left its temporary forever.

How this module is shaped, by the project's input rule: every server is a
ScriptedServer (tests/scripted_server.py) giving an ORDINARY small response
a fixed fraction of a second later than the deadline the test lowers
(OMARCHY_IPTV_HTTP_DEADLINE, which can only lower it); nothing waits on a
connection held open, and nothing is large. A deadline is shown by WHEN the
refusal comes: before the delayed response could have arrived. The redirect
methods are also called directly with a fake response that records whether
it was read.
"""
import contextlib
import email.message
import io
import json
import os
import pathlib
import signal
import sys
import tempfile
import time
import unittest
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper          # redirects HOME and $XDG_* first
from scripted_server import ScriptedServer, response

helper = load_helper()

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
PLAYLIST = b"#EXTM3U\n#EXTINF:-1,One\nhttp://127.0.0.1/one\n"
DEADLINE = 0.5           # the lowered budget, seconds
LATE = 0.9               # a little more than it: the response's delay
BEFORE_LATE = 0.8        # a refusal before this came from the deadline, not the response


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(argv))
    lines = [line for line in out.getvalue().splitlines() if line.strip()]
    return code, json.loads(lines[-1]) if lines else None, err.getvalue()


class LoweredDeadline(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {helper.HTTP_DEADLINE_ENV: str(DEADLINE)})
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = tmp.name

    def serve(self, routes, context=None):
        server = ScriptedServer(routes, context)
        self.addCleanup(server.close)
        return server


class FakeResponse:
    """A 3xx response that records what is done to it. `read` is the call
    that must never come."""

    def __init__(self):
        self.calls = []

    def read(self, *args):
        self.calls.append(("read",) + args)
        return b"a body"

    def close(self):
        self.calls.append(("close",))


class FakeParent:
    def __init__(self):
        self.opened = []

    def open(self, request, timeout=None):
        self.opened.append(request.full_url)
        return "followed"


class RedirectBodyNeverReadTest(unittest.TestCase):
    """D-LOGO-15 / D-SRC-58: every one of the five redirect methods closes the
    3xx response without reading it, and still follows the redirect."""

    def handler_of(self, opener):
        found = [h for h in opener.handlers if isinstance(h, urllib.request.HTTPRedirectHandler)]
        self.assertEqual(len(found), 1, opener.handlers)
        return found[0]

    def check(self, opener, start, target):
        handler = self.handler_of(opener)
        for code in (301, 302, 303, 307, 308):
            with self.subTest(code=code):
                handler.parent = FakeParent()
                fp = FakeResponse()
                headers = email.message.Message()
                headers["Location"] = target
                request = urllib.request.Request(start)
                request.timeout = 5          # OpenerDirector.open sets it
                result = getattr(handler, "http_error_%d" % code)(request, fp, code, "Moved", headers)
                self.assertEqual(result, "followed")
                self.assertEqual(handler.parent.opened, [target])
                self.assertNotIn("read", [call[0] for call in fp.calls], fp.calls)
                self.assertIn(("close",), fp.calls)

    def test_the_playlist_openers_redirects_close_the_body_unread(self):
        self.check(helper.make_opener("playlist", "a.test"), "http://a.test/list.m3u", "http://b.test/list.m3u")

    def test_the_logo_openers_redirects_close_the_body_unread(self):
        self.check(helper.logo_opener("a.test"), "https://a.test/logo.png", "https://b.test/logo.png")


class WholeDownloadDeadlineTest(LoweredDeadline):
    """R30e: ONE deadline from before the connection opens to the last byte."""

    def timed(self, *argv):
        started = time.monotonic()
        result = run(*argv)
        return result, time.monotonic() - started

    def test_a_status_line_later_than_the_deadline_is_cut_off_at_the_deadline(self):
        server = self.serve({"/list.m3u": (LATE, response("200 OK", (), PLAYLIST))})
        (code, status, stderr), elapsed = self.timed("playlist", "--url", server.url("/list.m3u"), "--cache-dir", self.cache)
        self.assertEqual(code, 1, stderr)
        self.assertEqual(status["error"]["code"], "timeout", status)
        self.assertLess(elapsed, BEFORE_LATE, "refused only after the response came (%.2f s)" % elapsed)

    def test_headers_later_than_the_deadline_are_cut_off_at_the_deadline(self):
        whole = response("200 OK", (), PLAYLIST)
        server = self.serve({"/list.m3u": (whole[:17], LATE, whole[17:])})
        (code, status, _), elapsed = self.timed("playlist", "--url", server.url("/list.m3u"), "--cache-dir", self.cache)
        self.assertEqual(status["error"]["code"], "timeout", status)
        self.assertLess(elapsed, BEFORE_LATE, "refused only after the headers came (%.2f s)" % elapsed)

    def test_a_redirect_whose_body_is_late_is_followed_at_once(self):
        # The 302's headers come at once and its 20-byte body after LATE.
        # The stdlib waited for that body before following; now nothing does.
        redirect = response("302 Found", (("Location", "/real.m3u"), ("Content-Length", "20")))
        server = self.serve({"/list.m3u": (redirect, LATE, b"x" * 20),
                             "/real.m3u": (response("200 OK", (), PLAYLIST),)})
        (code, status, stderr), elapsed = self.timed("playlist", "--url", server.url("/list.m3u"), "--cache-dir", self.cache)
        self.assertEqual(code, 0, (status, stderr))
        self.assertEqual(status["channelCount"], 1)
        self.assertEqual(server.paths, ["/list.m3u", "/real.m3u"])
        self.assertLess(elapsed, BEFORE_LATE, "the redirect's body was waited for (%.2f s)" % elapsed)

    def test_chunked_trailers_past_the_deadline_refuse_the_download(self):
        # The body is whole at once; the trailer lines then come 0.3 s apart.
        # http.client reads them inside the read1 that ends the body, and
        # the download used to be accepted after its deadline.
        head = response("200 OK", (("Transfer-Encoding", "chunked"),))
        body = b"%x\r\n%s\r\n0\r\n" % (len(PLAYLIST), PLAYLIST)
        server = self.serve({"/list.m3u": (head + body, 0.3, b"X-A: 1\r\n", 0.3, b"X-B: 2\r\n", 0.3, b"\r\n")})
        (code, status, _), _ = self.timed("playlist", "--url", server.url("/list.m3u"), "--cache-dir", self.cache)
        self.assertEqual(code, 1, status)
        self.assertEqual(status["error"]["code"], "timeout", status)

    def test_the_guide_download_is_held_to_the_same_deadline(self):
        server = self.serve({"/guide.xml": (LATE, response("200 OK", (), b"<tv></tv>"))})
        (code, status, _), elapsed = self.timed("epg", "--url", server.url("/guide.xml"), "--cache-dir", self.cache, "--force")
        self.assertEqual(code, 1, status)
        self.assertEqual(status["error"]["code"], "timeout", status)
        self.assertLess(elapsed, BEFORE_LATE, "refused only after the response came (%.2f s)" % elapsed)

    def test_the_alarm_is_put_back_as_it_was_found(self):
        seen = []

        def mine(signum, frame):
            seen.append(signum)
        previous = signal.signal(signal.SIGALRM, mine)
        self.addCleanup(signal.signal, signal.SIGALRM, previous)
        server = self.serve({"/fast.m3u": (response("200 OK", (), PLAYLIST),),
                             "/late.m3u": (LATE, response("200 OK", (), PLAYLIST))})
        self.assertEqual(run("playlist", "--url", server.url("/fast.m3u"), "--cache-dir", self.cache)[0], 0)
        self.assertEqual(run("playlist", "--url", server.url("/late.m3u"), "--cache-dir", self.cache)[0], 1)
        self.assertIs(signal.getsignal(signal.SIGALRM), mine)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        self.assertEqual(seen, [])

    def test_the_variable_can_only_lower_the_deadline(self):
        with mock.patch.dict(os.environ, {helper.HTTP_DEADLINE_ENV: "600"}):
            self.assertEqual(helper.http_deadline(20), 60.0)
        with mock.patch.dict(os.environ, {helper.HTTP_DEADLINE_ENV: "nan"}):
            self.assertEqual(helper.http_deadline(20), 60.0)
        with mock.patch.dict(os.environ, {helper.HTTP_DEADLINE_ENV: "0.25"}):
            self.assertEqual(helper.http_deadline(20), 0.25)

    def test_off_the_main_thread_trailers_past_the_deadline_still_refuse_the_download(self):
        # The round-2 recheck's M1: the check AFTER the read loop served only
        # a caller off the main thread, where no SIGALRM handler can be
        # installed, and nothing called from one. This does. The body is
        # whole at once; the trailer's end comes LATE, inside the last read1,
        # and with the post-loop check removed the download is accepted.
        import threading
        head = response("200 OK", (("Transfer-Encoding", "chunked"),))
        body = b"%x\r\n%s\r\n0\r\n" % (len(PLAYLIST), PLAYLIST)
        server = self.serve({"/list.m3u": (head + body, LATE, b"\r\n")})
        outcome = {}

        def fetch():
            try:
                outcome["data"] = helper.read_http_source(server.url("/list.m3u"), 5, "playlist")
            except helper.HelperError as error:
                outcome["code"] = error.code
            except BaseException as error:            # a FetchExpired here would be the alarm, which must be absent
                outcome["raised"] = type(error).__name__
            outcome["alarm"] = signal.getitimer(signal.ITIMER_REAL)
        worker = threading.Thread(target=fetch)
        worker.start()
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive(), "the download never ended")
        self.assertEqual(outcome.get("alarm"), (0.0, 0.0), outcome)
        self.assertEqual(outcome.get("code"), "timeout", outcome)


class LookupBoundTest(LoweredDeadline):
    """D-SRC-62: the host-name lookup is under the deadline too.

    glibc's getaddrinfo does not return to the interpreter until the
    resolver gives up -- it retries its own poll after a signal -- so the
    alarm's handler ran only THEN, and a fetch overran its deadline by the
    resolver's timeout (measured in a user namespace whose only resolver
    never answers: 1.26-1.28 s for a 0.5 s deadline under `timeout:1
    attempts:1`, 10.29-10.35 s under glibc's defaults, 2026-10-24,
    scripts/dev-harness/spikes/resolver-overrun). The lookup now runs on a
    worker thread the main thread waits for in short slices, so the alarm
    ends the wait as it ends a read.

    The double here has the C library's SHAPE, which is what makes it red
    on the code before the fix: it blocks SIGALRM in the calling thread for
    its whole delay, so the alarm cannot end it and is delivered only when
    the mask lifts -- exactly as glibc hands the signal on only after the
    resolver gave up. A plain `time.sleep` would not do: the raising
    handler interrupts it, and the old code would pass.
    """

    SLOW = 2.0

    def slow_lookup(self, only_host=None):
        import socket
        real = socket.getaddrinfo
        calls = []

        def getaddrinfo(host, port, *args, **kwargs):
            calls.append(host)
            if only_host is None or host == only_host:
                signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
                try:
                    time.sleep(self.SLOW)
                finally:
                    signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGALRM})
            return real(host, port, *args, **kwargs)
        patcher = mock.patch.object(socket, "getaddrinfo", getaddrinfo)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls

    def timed(self, *argv):
        started = time.monotonic()
        result = run(*argv)
        return result, time.monotonic() - started

    def test_a_lookup_longer_than_the_deadline_is_cut_off_at_the_deadline(self):
        server = self.serve({"/list.m3u": (response("200 OK", (), PLAYLIST),)})
        calls = self.slow_lookup()
        (code, status, stderr), elapsed = self.timed("playlist", "--url", server.url("/list.m3u"), "--cache-dir", self.cache)
        self.assertEqual(code, 1, stderr)
        self.assertEqual(status["error"]["code"], "timeout", status)
        self.assertLess(elapsed, BEFORE_LATE, "refused only after the resolver gave up (%.2f s)" % elapsed)
        self.assertEqual(calls, ["127.0.0.1"], "the lookup was not the one call")
        self.assertEqual(server.paths, [], "a connection was made before the lookup ended")

    def test_the_address_the_lookup_found_is_the_one_connected_to(self):
        # One getaddrinfo per connection, and the stdlib makes none of its
        # own after it: the result goes straight to the connect. Red on a
        # mutation that hands the host name back to socket.create_connection.
        server = self.serve({"/list.m3u": (response("200 OK", (), PLAYLIST),)})
        calls = self.slow_lookup(only_host="never")
        (code, status, stderr), elapsed = self.timed("playlist", "--url", server.url("/list.m3u"), "--cache-dir", self.cache)
        self.assertEqual(code, 0, (status, stderr))
        self.assertEqual(status["channelCount"], 1)
        self.assertEqual(calls, ["127.0.0.1"])

    def test_a_redirect_hop_s_lookup_is_under_the_same_deadline(self):
        # The second hop names a different host (`localhost`), whose lookup
        # is the slow one; the first resolves at once. Every connection the
        # opener makes goes through the bounded lookup, not only the first.
        redirect = response("302 Found", (("Location", "http://localhost:%d/real.m3u" % 0),))
        server = self.serve({"/list.m3u": (redirect,), "/real.m3u": (response("200 OK", (), PLAYLIST),)})
        redirect = response("302 Found", (("Location", "http://localhost:%d/real.m3u" % server.port),))
        server.routes["/list.m3u"] = (redirect,)
        calls = self.slow_lookup(only_host="localhost")
        (code, status, stderr), elapsed = self.timed("playlist", "--url", server.url("/list.m3u"), "--cache-dir", self.cache)
        self.assertEqual(code, 1, stderr)
        self.assertEqual(status["error"]["code"], "timeout", status)
        self.assertLess(elapsed, BEFORE_LATE, "the redirect's lookup overran the deadline (%.2f s)" % elapsed)
        self.assertEqual(calls, ["127.0.0.1", "localhost"])
        self.assertEqual(server.paths, ["/list.m3u"])

    def test_a_logo_s_lookup_is_under_its_own_deadline(self):
        # The logo opener (05-ipc-logos.py) is the other opener; its fetch
        # runs under fetch_logo's budget, lowered here to the same 0.5 s.
        self.slow_lookup()
        started = time.monotonic()
        with self.assertRaises(helper.HelperError) as caught:
            helper.fetch_logo("https://127.0.0.1:9/a.png", 5, DEADLINE)
        elapsed = time.monotonic() - started
        self.assertEqual(caught.exception.code, "logo_timeout")
        self.assertLess(elapsed, BEFORE_LATE, "the logo's lookup overran its deadline (%.2f s)" % elapsed)

    def test_off_the_main_thread_the_socket_timeout_bounds_the_lookup(self):
        # No alarm can be installed off the main thread; there the lookup is
        # held to the per-socket timeout as a connect is, and answered as a
        # connect that took too long (`network`), never left to the resolver.
        import threading
        server = self.serve({"/list.m3u": (response("200 OK", (), PLAYLIST),)})
        self.slow_lookup()
        outcome = {}

        def fetch():
            started = time.monotonic()
            try:
                outcome["data"] = helper.read_http_source(server.url("/list.m3u"), 0.3, "playlist")
            except helper.HelperError as error:
                outcome["code"] = error.code
                outcome["message"] = error.message
            outcome["elapsed"] = time.monotonic() - started
        worker = threading.Thread(target=fetch)
        worker.start()
        worker.join(timeout=10)
        self.assertFalse(worker.is_alive(), "the download never ended")
        self.assertEqual(outcome.get("code"), "network", outcome)
        self.assertIn("host-name lookup took longer than 0.3 s", outcome.get("message", ""))
        self.assertLess(outcome["elapsed"], BEFORE_LATE, outcome)


class StatusLineDetailTest(LoweredDeadline):
    """D-SRC-59: a server's first line, when it is not a status line, reaches
    the reply redacted, then cut to NETWORK_DETAIL_MAX characters, its control
    characters folded."""

    PREFIX = "could not reach 127.0.0.1: "

    def detail(self, first_line):
        server = self.serve({"/list.m3u": (first_line,)})
        code, status, stderr = run("playlist", "--url", server.url("/list.m3u"), "--cache-dir", self.cache)
        self.assertEqual(code, 1, stderr)
        self.assertEqual(status["error"]["code"], "network", status)
        message = status["error"]["message"]
        self.assertTrue(message.startswith(self.PREFIX), message)
        on_disk = json.loads((pathlib.Path(self.cache) / helper.PLAYLIST_STATUS_FILE).read_text(encoding="utf-8"))
        self.assertEqual(on_disk["error"]["message"], message)
        return message[len(self.PREFIX):], stderr

    def test_an_ordinary_long_first_line_is_cut(self):
        detail, stderr = self.detail(b"BAD http://user:SECRETPW@h.test/pppp " + b"w" * 300 + b"\r\n\r\n")
        # The stated figure (03-io-playlist.py, the README): 200 characters
        # and the three dots of the cut.
        self.assertEqual(getattr(helper, "NETWORK_DETAIL_MAX", None), 200)
        self.assertLessEqual(len(detail), 200 + 3, detail)
        self.assertTrue(detail.endswith("..."), detail)
        self.assertTrue(detail.startswith("BAD http://h.test "), detail)
        for leak in ("SECRETPW", "user", "pppp", "\r", "\n"):
            self.assertNotIn(leak, detail)
            self.assertNotIn(leak if leak not in ("\n",) else "\r", stderr)

    def test_the_cut_comes_after_the_redaction(self):
        # A cut at 15 falls inside the userinfo: cut first, then redacted,
        # would read "BAD http://user" -- the username in the reply.
        with mock.patch.object(helper, "NETWORK_DETAIL_MAX", 15, create=True):
            detail, _ = self.detail(b"BAD http://user:SECRETPW@h.test/pppp\r\n\r\n")
        self.assertEqual(detail, "BAD http://h.te...")

    def test_control_characters_are_folded(self):
        detail, _ = self.detail(b"BAD\x01first\x7fsecond\x1bthird\r\n\r\n")
        self.assertEqual(detail, "BAD first second third")


class StaleTemporarySweepTest(unittest.TestCase):
    """D-SRC-60: the first atomic write a process makes into a folder removes
    the temporaries a killed write left there -- only names of the writers'
    own shape, only regular files, only ones STALE_TEMP_AGE old (lowered here
    to 60 s; the files are dated 120 s and 10 s back, never waited for)."""

    def setUp(self):
        getattr(helper, "SWEPT_TEMP_DIRS", set()).clear()
        patcher = mock.patch.object(helper, "STALE_TEMP_AGE", 60, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name) / "sources" / "0123abcd"
        self.dir.mkdir(parents=True, mode=0o700)
        self.outside = pathlib.Path(tmp.name) / "outside"
        self.outside.write_text("keep me", encoding="utf-8")

    def plant(self, name, age, folder=None):
        path = (folder or self.dir) / name
        path.write_text("left by a killed write", encoding="utf-8")
        when = time.time() - age
        os.utime(path, (when, when))
        return path

    def names(self, folder=None):
        return sorted(os.listdir(folder or self.dir))

    def test_the_first_write_into_a_folder_sweeps_its_stale_temporaries(self):
        self.plant(".tmp-channels.json-0123abcd", 120)
        self.plant(".tmp-epg-now.json-89abcdef", 120)
        self.plant(".tmp-channels.json-fedcba98", 10)          # young: a live writer's, perhaps
        self.plant(".tmp-notours", 120)                         # not the writers' shape
        self.plant(".tmp-x-0123ABCD", 120)                      # upper case: not theirs
        self.plant("channels.json-0123abcd", 120)               # no prefix
        os.symlink(self.outside, self.dir / ".tmp-link-01234567")
        os.mkdir(self.dir / ".tmp-dir-01234567")
        helper.write_json_atomic(str(self.dir / "channels.json"), {"version": 1})
        self.assertEqual(self.names(), [".tmp-channels.json-fedcba98", ".tmp-dir-01234567", ".tmp-link-01234567",
                                        ".tmp-notours", ".tmp-x-0123ABCD", "channels.json", "channels.json-0123abcd"])
        self.assertEqual(self.outside.read_text(encoding="utf-8"), "keep me")

    def test_a_folder_that_is_not_the_plugins_loses_only_the_targets_own(self):
        self.plant(".tmp-state.json-0123abcd", 120)
        self.plant(".tmp-notes.txt-0123abcd", 120)
        helper.write_text_atomic(str(self.dir / "state.json"), "{}\n", private_dir=False)
        self.assertEqual(self.names(), [".tmp-notes.txt-0123abcd", "state.json"])

    def test_a_temporary_owned_by_another_user_is_left_alone(self):
        # The round-2 recheck's M4: the owner check could not be seen to
        # matter without a file of another uid, which no test can make. The
        # sweep asks os.geteuid for ITS uid, so the shipping sweep is run
        # against a uid that is not the file's -- and must leave it; the
        # same file under the real uid goes.
        self.plant(".tmp-channels.json-0123abcd", 120)
        with mock.patch.object(os, "geteuid", return_value=os.geteuid() + 1):
            self.assertEqual(helper.sweep_stale_temps(str(self.dir)), 0)
        self.assertEqual(self.names(), [".tmp-channels.json-0123abcd"])
        self.assertEqual(helper.sweep_stale_temps(str(self.dir)), 1)
        self.assertEqual(self.names(), [])

    def test_the_binary_writer_sweeps_too(self):
        logos = self.dir / "logos"
        logos.mkdir(mode=0o700)
        self.plant(".tmp-0000aaaa-0123abcd", 120, logos)
        helper.write_bytes_atomic(str(logos / "0000bbbb"), b"x")
        self.assertEqual(self.names(logos), ["0000bbbb"])

    def test_the_verbs_sweep_the_folder_they_write(self):
        self.plant(".tmp-channels.json-0123abcd", 120)
        code, payload, stderr = run("failed", "mark", "--id", "t:one", "--cache-dir", str(self.dir))
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.names(), [helper.FAILED_FILE])
        getattr(helper, "SWEPT_TEMP_DIRS", set()).clear()
        self.plant(".tmp-playlist-status.json-0123abcd", 120)
        code, payload, stderr = run("playlist", "--url", str(FIXTURES / "basic.m3u"), "--cache-dir", str(self.dir))
        self.assertEqual(code, 0, stderr)
        self.assertNotIn(".tmp-playlist-status.json-0123abcd", self.names())


class EnvironmentLeverTest(unittest.TestCase):
    """F-HARNESS-36 (R32f), rule 15 over every environment variable the
    helper reads that touches a stated bound: each exists so a test can
    shrink the bound, and none may raise it. The helper's other variables
    (OMARCHY_IPTV_URL, $HOME and the four $XDG_* paths) carry no bound."""

    def test_every_lever_on_a_bound_can_only_lower_it(self):
        levers = (
            (helper.HTTP_DEADLINE_ENV, lambda: helper.http_deadline(20), 60.0, "0.25", 0.25),
            (helper.CLIPBOARD_TIMEOUT_ENV, helper.clipboard_deadline, helper.CLIPBOARD_TIMEOUT, "0.25", 0.25),
            (helper.MEMORY_LIMIT_ENV, helper.memory_limit_bytes, helper.MEMORY_LIMIT_MIB * 1024 * 1024, "16", 16 * 1024 * 1024),
        )
        for name, read, ceiling, lower, lowered in levers:
            for raised in ("600", "99999", "inf", "nan", "soon", ""):
                with self.subTest(name=name, value=raised), mock.patch.dict(os.environ, {name: raised}):
                    self.assertEqual(read(), ceiling)
            with self.subTest(name=name, value=lower), mock.patch.dict(os.environ, {name: lower}):
                self.assertEqual(read(), lowered)
            with self.subTest(name=name, value="unset"), mock.patch.dict(os.environ):
                os.environ.pop(name, None)
                self.assertEqual(read(), ceiling)


if __name__ == "__main__":
    unittest.main()
