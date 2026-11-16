"""D-SINK-102 (the marketplace maintainer on omacom/omarchy-plugin-marketplace
#14290, against 0.19.1 at 9e006be): every destination rule judged the address
the helper saw, and the player then made its own connections -- an HTTP
redirect, an HLS or DASH open on another host, and a name that answered the
player differently a moment later all reached addresses nobody had judged.
The fix is a relay (bin/helper/12-relay.py) the player is pinned to as its
HTTP proxy, which looks every target up itself, judges every answer by the
rule a channel's literal meets, and connects only to an address it judged.

How this module observes it (rule 14: the sink, never a string). The real
RelayServer runs in process on scratch sockets -- a TCP listener on
127.0.0.1 and a Unix listener under a scratch directory, as the player's
spawn binds them -- and the real `player relay` verb runs as a subprocess
for its lifecycle. Every origin is a listener of this test on a loopback
literal that counts what it ACCEPTS and records every byte it receives: a
refusal is an origin that saw nothing, a pass one that saw the request.

NOTHING HERE ASKS A REAL RESOLVER. The helper is loaded without the suite's
stand-in (load_helper(stream_lookup=None)) and every test replaces the
relay's lookup -- stream_resolve, the play-time lookup's own, which
relay_lookup asks -- with a Resolver whose answers it states; a name it was
not told about is recorded and fails the test. Literals are answered too,
because the relay looks a literal up the same way (getaddrinfo makes no
query for one). The one other lookup, of the user's own proxy in the
upstream proxy tests, is of the literal 127.0.0.1, and for the whole module resolve_within
answers literals only (literal_lookups_only): the red-first run of this
module against 7c1784c, whose connector swallowed the `resolve` keyword,
asked a real resolver about two `.test` names before this guard existed.

The address classes. 127.0.0.1 is the only address an origin of this test
can bind that the real classifier calls anything but loopback, so a test
that needs a public origin, or a LAN one, reads one or two loopback
addresses as that class with `reads_as` below -- the same seam as the
suite's loopback_reads_public, widened per test to the addresses and
classes it names, and never more forgiving than the real classifier for any
address it does not name. A permitted connection therefore always lands on a
listener of this test, and a refused one is refused before any connect, so
no test, and no mutant of the relay, ever opens a connection off this
machine.

Run: python3 -m unittest discover -s tests
"""
import base64
import contextlib
import io
import json
import os
import pathlib
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import HELPER, ROOT, load_helper

helper = load_helper(stream_lookup=None)

# Every host, path and userinfo a refusal could leak holds this word.
LEAK = "qqqqqq"
STUB_MPV = ROOT / "scripts" / "qa-stub-mpv.py"
FIXTURE = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "relay-no-proxy.json")
                     .read_text(encoding="utf-8"))
DESTINATIONS = json.loads((pathlib.Path(__file__).resolve().parent / "fixtures" / "destinations.json")
                          .read_text(encoding="utf-8"))

def literal_lookups_only(real):
    """resolve_within for this module: the real one for an IP literal, which
    getaddrinfo answers without a query (the user's own proxy at 127.0.0.1
    in the upstream proxy tests), and a failure for any name. The relay never asks it of
    a target -- its lookups go through stream_resolve -- so a name reaching it
    is a test, or a tree, that would have asked a real resolver."""
    import ipaddress

    def lookup(host, port, timeout, **limit):
        text = host.decode("utf-8", "replace") if isinstance(host, bytes) else str(host)
        try:
            ipaddress.ip_address(text.split("%", 1)[0])
        except ValueError:
            raise AssertionError("a name reached resolve_within: %r" % (host,)) from None
        return real(host, port, timeout, **limit)
    return lookup


REAL_RESOLVE_WITHIN = helper.resolve_within
_GUARD = mock.patch.object(helper, "resolve_within", literal_lookups_only(helper.resolve_within))


def setUpModule():
    _GUARD.start()


def tearDownModule():
    _GUARD.stop()


REMOTE = {"origin": "playlist", "host": "prov.qqqqqq.test", "port": 80, "loopback": False, "local": False,
          "class": "global"}
PROXIED = dict(REMOTE, **{"class": "unresolved"})
LAN = {"origin": "playlist", "host": "192.168.1.5", "port": 80, "loopback": False, "local": True, "class": "private"}
USER = {"origin": "user", "host": "nas.qqqqqq.test", "port": 8080}


def loopback_relay(port):
    return {"origin": "playlist", "host": "127.0.0.1", "port": port, "loopback": True, "local": True,
            "class": "loopback"}


def reads_as(classes):
    """While entered, the helper's classifier answers `classes[address]` for
    the loopback addresses the test names and the real class for every
    other value (the module docstring)."""
    real = helper.address_class

    def classify(value):
        text = str(value).split("%", 1)[0]
        return classes[text] if text in classes else real(value)
    return mock.patch.object(helper, "address_class", classify)


def public(*addresses):
    return reads_as({address: "global" for address in addresses})


class Resolver:
    """The relay's lookup: `answers` maps a name, as the relay asks it (str,
    or bytes for a name that is not ASCII), to a list of addresses, each an
    address or (address, port), or to an exception. Every name asked is
    recorded; one it was not told about is recorded in `unexpected` and
    answers nothing."""

    def __init__(self, answers):
        self.answers = answers
        self.asked = []
        self.unexpected = []

    def __call__(self, name, port):
        self.asked.append((name, port))
        if name not in self.answers:
            self.unexpected.append(name)
            return []
        found = self.answers[name]
        if isinstance(found, BaseException):
            raise found
        out = []
        for item in found:
            address, at = item if isinstance(item, tuple) else (item, port)
            if ":" in address:
                out.append((socket.AF_INET6, socket.SOCK_STREAM, 6, "", (address, at, 0, 0)))
            else:
                out.append((socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, at)))
        return out


class Origin:
    """A listener of this test on a loopback literal: counts what it
    accepts and records every byte, and answers each request head with a
    200 whose body is `body` (keep-alive), or echoes every byte (`echo`)."""

    def __init__(self, case, address="127.0.0.1", body=b"stream-bytes", echo=False, context=None):
        self.sock = socket.socket(socket.AF_INET6 if ":" in address else socket.AF_INET)
        self.sock.bind((address, 0))
        self.sock.listen(16)
        self.address = address
        self.port = self.sock.getsockname()[1]
        self.body = body
        self.echo = echo
        self.context = context
        self.accepted = 0
        self.heads = []
        self.received = bytearray()
        self.lock = threading.Lock()
        self.closed = False
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        case.addCleanup(self.close)

    def loop(self):
        while not self.closed:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with self.lock:
                self.accepted += 1
            threading.Thread(target=self.serve, args=(conn,), daemon=True).start()

    def serve(self, conn):
        try:
            if self.context is not None:
                conn = self.context.wrap_socket(conn, server_side=True)
            buffer = b""
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    return
                with self.lock:
                    self.received += chunk
                if self.echo:
                    conn.sendall(chunk)
                    continue
                buffer += chunk
                while b"\r\n\r\n" in buffer:
                    head, buffer = buffer.split(b"\r\n\r\n", 1)
                    with self.lock:
                        self.heads.append(head)
                    conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n%s" % (len(self.body), self.body))
        except (OSError, ssl.SSLError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def close(self):
        self.closed = True
        try:
            self.sock.close()
        except OSError:
            pass


class Relay:
    """The real RelayServer, in process, on the two listeners the player's
    spawn would bind: TCP on 127.0.0.1 port 0, and a Unix socket in a 0700
    scratch directory."""

    def __init__(self, case, environ=None, build="0.0.0+0badf00d"):
        self.dir = tempfile.mkdtemp(prefix="relay-")
        os.chmod(self.dir, 0o700)
        case.addCleanup(shutil.rmtree, self.dir, True)
        self.proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.proxy.bind(("127.0.0.1", 0))
        self.proxy.listen(64)
        self.port = self.proxy.getsockname()[1]
        self.path = os.path.join(self.dir, "mpv.sock.relay")
        self.control = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.control.bind(self.path)
        self.control.listen(8)
        self.state = helper.RelayState(self.port, build, 4242)
        self.server = helper.RelayServer(self.proxy, self.control, self.state, {} if environ is None else environ)
        self.thread = threading.Thread(target=self.server.serve, daemon=True)
        self.thread.start()
        case.addCleanup(self.close)

    def close(self):
        self.server.stop()
        self.thread.join(5)
        self.server.close()
        for sock in (self.proxy, self.control):
            sock.close()

    def control_line(self, raw, timeout=5):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(self.path)
            sock.sendall(raw)
            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
        return json.loads(data) if data else None

    def ask(self, request):
        return self.control_line(json.dumps(request).encode("ascii") + b"\n")

    def control_answer(self, raw, timeout=5):
        """Every byte a control connection sending `raw` is answered with
        before the relay ends it; b"" for none, a reset included (the relay
        closing on a line it never read resets the connection)."""
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(self.path)
            data = b""
            try:
                sock.sendall(raw)
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    data += chunk
            except (ConnectionResetError, BrokenPipeError):
                pass
        return data

    def register(self, policy):
        reply = self.ask({"op": "load", "policy": policy})
        assert reply["ok"], reply
        return reply["token"]

    def connect(self):
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        return sock


def auth(token, user="iptv"):
    return b"Proxy-Authorization: Basic " + base64.b64encode(user.encode() + b":" + token.encode()) + b"\r\n"


def get(target, token=None, extra=b"", method=b"GET"):
    head = method + b" " + target.encode("utf-8") + b" HTTP/1.1\r\nHost: h\r\n"
    if token is not None:
        head += auth(token)
    return head + extra + b"\r\n"


def read_reply(sock):
    """One response: (status, head, body), reading the body by its
    Content-Length; (None, b"", b"") on a connection closed first."""
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(65536)
        if not chunk:
            return None, data, b""
        data += chunk
    head, body = data.split(b"\r\n\r\n", 1)
    length = 0
    for line in head.split(b"\r\n")[1:]:
        name, _, value = line.partition(b":")
        if name.strip().lower() == b"content-length":
            length = int(value.strip())
    while len(body) < length:
        chunk = sock.recv(65536)
        if not chunk:
            break
        body += chunk
    return int(head.split(b" ")[1]), head, body


def closed(sock, wait=3.0):
    """Whether the peer closed `sock` (EOF or reset) within `wait`."""
    sock.settimeout(wait)
    try:
        return sock.recv(1) == b""
    except (ConnectionResetError, BrokenPipeError):
        return True
    except socket.timeout:
        return False


def exchange(relay, raw):
    """Send one head on a new connection; -> (status, head, body)."""
    with relay.connect() as sock:
        sock.sendall(raw)
        return read_reply(sock)


class Fixture(unittest.TestCase):
    """A relay, a resolver and the bookkeeping every test shares."""

    def resolving(self, answers):
        resolver = Resolver(answers)
        patch = mock.patch.object(helper, "stream_resolve", resolver)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(lambda: self.assertEqual(resolver.unexpected, [], "a lookup nobody stated"))
        return resolver

    def classes(self, mapping):
        patch = reads_as(mapping)
        patch.start()
        self.addCleanup(patch.stop)


# ------------------------------------------------------ head parsing

class HeadParsingTest(Fixture):
    """The request heads the relay acts on, and the 400, 405 and 431
    every other one gets, read by the shipping relay_parse_head."""

    def setUp(self):
        self.state = helper.RelayState(1, "b", 0)
        self.token = self.state.register(helper.relay_policy_record(REMOTE))

    def parse(self, raw):
        return helper.relay_parse_head(raw, self.state)

    def status(self, raw):
        try:
            self.parse(raw)
        except helper.RelayReply as reply:
            return reply.status
        return 0

    def test_absolute_get_and_head_and_both_connect_forms_are_read(self):
        got = self.parse(get("http://Stream.qqqqqq.test:8080/live/1.m3u8?x=1#frag", self.token)[:-4])
        self.assertEqual((got["connect"], got["host"], got["port"], got["origin"], got["target"]),
                         (False, "Stream.qqqqqq.test", 8080, b"/live/1.m3u8?x=1",
                          b"http://Stream.qqqqqq.test:8080/live/1.m3u8?x=1"))
        got = self.parse(get("http://s.qqqqqq.test?x", self.token, method=b"HEAD")[:-4])
        self.assertEqual((got["method"], got["port"], got["origin"]), (b"HEAD", 80, b"/?x"))
        got = self.parse(get("s.qqqqqq.test:443", self.token, method=b"CONNECT")[:-4])
        self.assertEqual((got["connect"], got["host"], got["port"]), (True, "s.qqqqqq.test", 443))
        got = self.parse(get("[2606:4700::1111]:8443", self.token, method=b"CONNECT")[:-4])
        self.assertEqual((got["host"], got["port"]), ("2606:4700::1111", 8443))

    def test_a_method_other_than_get_head_and_connect_is_405(self):
        for method in (b"POST", b"PUT", b"OPTIONS", b"get"):
            with self.subTest(method=method):
                self.assertEqual(self.status(get("http://s.qqqqqq.test/x", self.token, method=method)[:-4]), 405)

    def test_a_body_is_400(self):
        for extra in (b"Content-Length: 5\r\n", b"Transfer-Encoding: chunked\r\n", b"content-length: 1\r\n"):
            with self.subTest(extra=extra):
                self.assertEqual(self.status(get("http://s.qqqqqq.test/x", self.token, extra)[:-4]), 400)
        self.assertEqual(self.status(get("http://s.qqqqqq.test/x", self.token, b"Content-Length: 0\r\n")[:-4]), 0)

    def test_a_target_that_is_not_one_of_the_two_forms_is_400(self):
        for target, method in (("http://u:p@s.qqqqqq.test/x", b"GET"), ("https://s.qqqqqq.test/x", b"GET"),
                               ("/x", b"GET"), ("s.qqqqqq.test:80", b"GET"), ("ftp://s.qqqqqq.test/x", b"GET"),
                               ("http://s.qqqqqq.test/x", b"CONNECT"), ("s.qqqqqq.test", b"CONNECT"),
                               ("u@s.qqqqqq.test:443", b"CONNECT"), ("http:///x", b"GET")):
            with self.subTest(target=target):
                self.assertEqual(self.status(get(target, self.token, method=method)[:-4]), 400)

    def test_an_authority_the_sr15_reader_refuses_is_400(self):
        hosts = ["s.qqqqqq.test:0", "s.qqqqqq.test:65536", "s.qqqqqq.test:+1", "s.qqqqqq.test:" + chr(0xB9),
                 "s.qqqqqq.test:080808", "s%40qqqqqq.test", "s;qqqqqq.test", "s.qqqqqq.test:80:81", "a[b]qqqqqq.test",
                 "[::1]x.qqqqqq.test:80", "[v1.qqqqqq]", "s.qqqqqq.test:", "[fe80::1%25eth0]:80", "s.qqqqqq.test:8 0"]
        for host in hosts:
            with self.subTest(host=host):
                self.assertEqual(self.status(get("http://%s/x" % host, self.token)[:-4]), 400)
                if " " not in host:
                    self.assertEqual(self.status(get(host if ":" in host[-6:] else host + ":443", self.token,
                                                     method=b"CONNECT")[:-4]), 400)

    def test_a_malformed_head_is_400(self):
        for raw in (b"GET http://s.qqqqqq.test/x HTTP/2.0\r\nHost: h",
                    b"GET http://s.qqqqqq.test/x\r\nHost: h",
                    b"GET  http://s.qqqqqq.test/x HTTP/1.1",
                    b"GET http://s.qqqqqq.test/x HTTP/1.1\r\nHost: h\r\n folded",
                    b"GET http://s.qqqqqq.test/x HTTP/1.1\r\nno colon here",
                    b"GET http://s.qqqqqq.test/x HTTP/1.1\r\nBad Name: v",
                    b"GET http://s.qqqqqq.test/x HTTP/1.1\nHost: h",
                    b"GET http://s.qqqqqq.test/\x01x HTTP/1.1"):
            with self.subTest(raw=raw):
                self.assertEqual(self.status(raw + b"\r\n" + auth(self.token)[:-2]), 400)

    def test_two_proxy_authorization_headers_are_400(self):
        raw = get("http://s.qqqqqq.test/x", self.token, auth(self.token))[:-4]
        self.assertEqual(self.status(raw), 400)


class HeadBoundsTest(Fixture):
    """Over the wire: a head over RELAY_HEAD_BYTES is 431 and one that
    stalls is 408 at RELAY_HEAD_S, and neither reaches the resolver."""

    def test_an_oversized_head_is_431_and_looks_nothing_up(self):
        resolver = self.resolving({})
        relay = Relay(self)
        token = relay.register(REMOTE)
        raw = get("http://s.qqqqqq.test/x", token, b"X-Pad: " + b"a" * helper.RELAY_HEAD_BYTES + b"\r\n")
        self.assertEqual(exchange(relay, raw)[0], 431)
        self.assertEqual(resolver.asked, [])

    def test_a_stalled_head_is_408_at_its_bound(self):
        resolver = self.resolving({})
        relay = Relay(self)
        with mock.patch.object(helper, "RELAY_HEAD_S", 0.4), relay.connect() as sock:
            started = time.monotonic()
            sock.sendall(b"GET http://s.qqqqqq.test/x HTTP/1.1\r\nHost:")
            status, _, _ = read_reply(sock)
            elapsed = time.monotonic() - started
        self.assertEqual(status, 408)
        self.assertLess(elapsed, 3.0)
        self.assertEqual(resolver.asked, [])


# ---------------------------------------------------- authentication

class AuthenticationTest(Fixture):
    """No live token, no connection: a 407 with the realm, then closed,
    and the origin never contacted."""

    def test_every_request_without_a_live_token_is_407_and_reaches_no_origin(self):
        resolver = self.resolving({})
        origin = Origin(self)
        relay = Relay(self)
        evicted = relay.register(REMOTE)
        for _ in range(helper.RELAY_TOKENS_MAX - 1):
            relay.register(REMOTE)
        live = relay.register(REMOTE)
        self.assertIsNone(relay.state.find(evicted))
        self.assertIsNotNone(relay.state.find(live))
        target = "http://127.0.0.1:%d/x" % origin.port
        cases = [get(target), get(target, "0" * 32), get(target, evicted),
                 get(target).replace(b"\r\n\r\n", b"\r\n" + auth(live, user="root") + b"\r\n"),
                 get(target).replace(b"\r\n\r\n", b"\r\nProxy-Authorization: Bearer " + live.encode() + b"\r\n\r\n"),
                 get(target).replace(b"\r\n\r\n", b"\r\nProxy-Authorization: Basic !!!!\r\n\r\n")]
        for raw in cases:
            with self.subTest(raw=raw[:60]):
                with relay.connect() as sock:
                    sock.sendall(raw)
                    status, head, _ = read_reply(sock)
                    self.assertEqual(status, 407)
                    self.assertIn(b'Proxy-Authenticate: Basic realm="omarchy-iptv"', head)
                    self.assertIn(b"Connection: close", head)
                    self.assertTrue(closed(sock))
        self.assertEqual((origin.accepted, resolver.asked), (0, []))

    def test_the_token_a_registration_answers_is_the_one_the_relay_takes(self):
        self.resolving({"127.0.0.1": ["127.0.0.1"]})
        self.classes({"127.0.0.1": "global"})
        origin = Origin(self)
        relay = Relay(self)
        token = relay.register(REMOTE)
        status, _, body = exchange(relay, get("http://127.0.0.1:%d/live/1.ts" % origin.port, token))
        self.assertEqual((status, body, origin.accepted), (200, b"stream-bytes", 1))


# --------------------------------------------------------- judgement

class JudgementTest(Fixture):
    """Every answer is judged by the channel rule before it is connected
    to, and a refused one is never connected to."""

    def setUp(self):
        self.public = Origin(self, "127.0.0.1")
        self.target = Origin(self, "127.0.0.2")
        self.classes({"127.0.0.1": "global"})

    def fetch(self, policy, host, port, answers, path="/x"):
        resolver = Resolver(answers)
        with mock.patch.object(helper, "stream_resolve", resolver):
            relay = Relay(self)
            token = relay.register(policy)
            status = exchange(relay, get("http://%s:%d%s" % (host, port, path), token))[0]
        self.assertEqual(resolver.unexpected, [])
        return status, resolver, relay

    def test_a_remote_playlists_name_reaches_a_global_answer(self):
        status, resolver, _ = self.fetch(REMOTE, "cdn.qqqqqq.test", self.public.port, {"cdn.qqqqqq.test": ["127.0.0.1"]})
        self.assertEqual((status, self.public.accepted, resolver.asked), (200, 1, [("cdn.qqqqqq.test", self.public.port)]))

    def test_a_remote_playlists_name_answering_this_machine_or_the_lan_is_403_and_never_connected(self):
        for kind in ("loopback", "private", "link-local", "shared", "unspecified", "multicast", "reserved"):
            with self.subTest(kind=kind), reads_as({"127.0.0.1": "global", "127.0.0.2": kind}):
                status, _, relay = self.fetch(REMOTE, "evil.qqqqqq.test", self.target.port,
                                              {"evil.qqqqqq.test": ["127.0.0.2"]})
                self.assertEqual((status, self.target.accepted), (403, 0))
                self.assertEqual(relay.state.status()["refused"], 1)

    def test_a_literal_is_judged_as_the_answer_it_is(self):
        status, _, _ = self.fetch(REMOTE, "127.0.0.2", self.target.port, {"127.0.0.2": ["127.0.0.2"]})
        self.assertEqual((status, self.target.accepted), (403, 0))

    def test_the_playlists_own_host_answering_the_lan_is_refused(self):
        own = dict(REMOTE, port=self.target.port)
        with reads_as({"127.0.0.1": "global", "127.0.0.2": "private"}):
            status, _, _ = self.fetch(own, "PROV.qqqqqq.test", self.target.port, {"PROV.qqqqqq.test": ["127.0.0.2"]})
        self.assertEqual((status, self.target.accepted), (403, 0))

    def test_a_local_playlist_may_reach_the_lan(self):
        with reads_as({"127.0.0.1": "global", "127.0.0.2": "private"}):
            status, _, _ = self.fetch(LAN, "tuner.qqqqqq.test", self.target.port, {"tuner.qqqqqq.test": ["127.0.0.2"]})
        self.assertEqual((status, self.target.accepted), (200, 1))

    def test_a_loopback_relays_channels_reach_its_own_port_only(self):
        source = loopback_relay(self.target.port)
        status, _, _ = self.fetch(source, "127.0.0.2", self.target.port, {"127.0.0.2": ["127.0.0.2"]})
        self.assertEqual((status, self.target.accepted), (200, 1))
        other = Origin(self, "127.0.0.2")
        status, _, _ = self.fetch(source, "127.0.0.2", other.port, {"127.0.0.2": ["127.0.0.2"]})
        self.assertEqual((status, other.accepted), (403, 0))

    def test_a_one_label_name_is_refused_before_any_lookup_and_a_bad_name_never_reaches_the_resolver(self):
        status, resolver, _ = self.fetch(REMOTE, "user" + LEAK, self.target.port, {})
        self.assertEqual((status, resolver.asked), (403, []))
        for host in ("evil%40qqqqqq.test", "a" + chr(0xFF1B) + "qqqqqq.test"):
            with self.subTest(host=host):
                status, resolver, _ = self.fetch(REMOTE, host, self.target.port, {})
                self.assertIn(status, (400, 403))
                self.assertEqual(resolver.asked, [])
        # The playlist's own host is excepted, and a local playlist keeps them.
        status, _, _ = self.fetch(dict(REMOTE, host="tvheadend"), "tvheadend", self.public.port,
                                  {"tvheadend": ["127.0.0.1"]})
        self.assertEqual(status, 200)

    def test_a_name_that_cannot_be_looked_up_is_502_naming_none(self):
        for found in (socket.gaierror(socket.EAI_NONAME, "nope"), TimeoutError(110, "slow"), []):
            with self.subTest(found=found):
                resolver = Resolver({"gone.qqqqqq.test": found})
                with mock.patch.object(helper, "stream_resolve", resolver):
                    relay = Relay(self)
                    token = relay.register(REMOTE)
                    status, head, _ = exchange(relay, get("http://gone.qqqqqq.test:%d/x" % self.public.port, token))
                self.assertEqual((status, head.split(b"\r\n")[0]),
                                 (502, b"HTTP/1.1 502 " + helper.RELAY_LOOKUP_FAILED.encode()))

    def test_a_name_that_is_not_ascii_is_asked_as_its_utf8_bytes(self):
        name = "Stra" + chr(0xDF) + "e.qqqqqq.test"
        resolver = Resolver({name.encode("utf-8"): ["127.0.0.1"]})
        with mock.patch.object(helper, "stream_resolve", resolver):
            relay = Relay(self)
            token = relay.register(REMOTE)
            status = exchange(relay, get("http://%s:%d/x" % (name, self.public.port), token))[0]
        self.assertEqual((status, resolver.asked), (200, [(name.encode("utf-8"), self.public.port)]))


class DestinationVectorsTest(Fixture):
    """Over the shared fixture: destinations.json streamHosts, the rule a
    channel's literal meets at the parse, met by the relay's judgment of an
    answer of that class."""

    def test_the_destination_vectors_meet_the_relay_as_they_meet_the_parse(self):
        """destinations.json streamHosts, every http and https vector,
        through the real relay: the vector's host in the request, its source
        as cached_source records it (with the class its own host's literal
        has), and the answer a listener of this test that the classifier
        reads as the vector's own class."""
        sink = Origin(self, "127.0.0.3")
        ran = 0
        for vector in DESTINATIONS["streamHosts"]:
            scheme, _, rest = vector["url"].partition("://")
            if scheme not in ("http", "https"):
                continue
            ran += 1
            authority = rest.split("/", 1)[0]
            source = vector["source"]
            record = {"origin": "playlist", "host": source["host"], "port": source.get("port"),
                      "loopback": source.get("loopback", False), "local": source["local"],
                      "class": helper.host_class(source["host"]) or ("global" if source["host"] else "")}
            host = authority.rpartition("]")[0][1:] if authority.startswith("[") else authority.split(":")[0]
            kind = helper.host_class(host) or "global"
            with self.subTest(url=vector["url"], source=source), reads_as({"127.0.0.3": kind}):
                before = sink.accepted
                resolver = Resolver({host: [("127.0.0.3", sink.port)]})
                with mock.patch.object(helper, "stream_resolve", resolver):
                    relay = Relay(self)
                    token = relay.register(record)
                    if scheme == "https":
                        target = authority if ":" in authority.rpartition("]")[2] else authority + ":443"
                        raw = get(target, token, method=b"CONNECT")
                    else:
                        raw = get(vector["url"], token)
                    status = exchange(relay, raw)[0]
                refused = sink.accepted == before
                self.assertEqual(refused, vector["refused"], status)
                self.assertEqual(status in (400, 403), vector["refused"], status)
        self.assertGreater(ran, 30)


# ----------------------------------------------------- check and use

class CheckAndUseTest(Fixture):
    """The address the relay connects to is the address it judged, from
    its own lookup, whatever the helper's own lookup was told a moment
    before (DNS rebinding)."""

    def test_a_name_that_answered_the_play_time_lookup_publicly_and_the_relay_locally_is_refused(self):
        self.classes({"127.0.0.1": "global"})
        target = Origin(self, "127.0.0.2")
        tmp = tempfile.mkdtemp(prefix="relay-cache-")
        self.addCleanup(shutil.rmtree, tmp, True)
        url = "http://svc.qqqqqq.test:%d/live/1.ts" % target.port
        document = {"version": 1, "sourceHost": "prov.qqqqqq.test", "sourceClass": "global", "sourceLocal": False,
                    "sourcePort": 80, "channels": [{"id": "e0", "name": "E0", "group": "G", "url": url}]}
        pathlib.Path(tmp, "channels.json").write_text(json.dumps(document), encoding="utf-8")
        answers = iter([["93.184.216.34"], ["127.0.0.2"]])
        asked = []

        def rebinding(name, port):
            asked.append(name)
            return Resolver({name: next(answers)})(name, port)
        with mock.patch.object(helper, "stream_resolve", rebinding):
            played = helper.player_target("e0", "", tmp)
            relay = Relay(self)
            token = relay.register(dict(helper.cached_source(document), origin="playlist"))
            status = exchange(relay, get(played["url"], token))[0]
        self.assertEqual((played["url"], status, target.accepted, asked), (url, 403, 0, ["svc.qqqqqq.test"] * 2))

    def test_a_refused_answer_is_skipped_and_only_the_judged_one_is_connected_to(self):
        self.classes({"127.0.0.1": "global"})
        lan = Origin(self, "127.0.0.2")
        public = Origin(self, "127.0.0.1")
        resolver = self.resolving({"mixed.qqqqqq.test": [("127.0.0.2", lan.port), ("127.0.0.1", public.port)]})
        relay = Relay(self)
        token = relay.register(REMOTE)
        status = exchange(relay, get("http://mixed.qqqqqq.test:%d/x" % public.port, token))[0]
        self.assertEqual((status, lan.accepted, public.accepted), (200, 0, 1))
        self.assertEqual(resolver.asked, [("mixed.qqqqqq.test", public.port)])

    def test_the_resolver_is_asked_once_per_upstream_connection(self):
        self.classes({"127.0.0.1": "global"})
        public = Origin(self, "127.0.0.1")
        resolver = self.resolving({"cdn.qqqqqq.test": ["127.0.0.1"]})
        relay = Relay(self)
        token = relay.register(REMOTE)
        target = "http://cdn.qqqqqq.test:%d/seg" % public.port
        with relay.connect() as sock:
            for _ in range(3):
                sock.sendall(get(target, token))
                self.assertEqual(read_reply(sock)[0], 200)
        exchange(relay, get(target, token))
        self.assertEqual((len(resolver.asked), public.accepted, len(public.heads)), (2, 2, 4))


# -------------------------------------------------------- keep-alive

class KeepAliveTest(Fixture):
    """Every later request on a client connection is read and checked
    as the first was, and travels only over the connection judged for it."""

    def setUp(self):
        self.classes({"127.0.0.1": "global"})
        self.origin = Origin(self, "127.0.0.1")
        self.other = Origin(self, "127.0.0.1")
        self.resolver = self.resolving({"a.qqqqqq.test": ["127.0.0.1"], "b.qqqqqq.test": ["127.0.0.1"]})
        self.relay = Relay(self)
        self.token = self.relay.register(REMOTE)

    def test_a_second_request_for_the_same_target_reuses_the_judged_connection(self):
        with self.relay.connect() as sock:
            for path in ("/seg0", "/seg1"):
                sock.sendall(get("http://a.qqqqqq.test:%d%s" % (self.origin.port, path), self.token))
                self.assertEqual(read_reply(sock)[0], 200)
        self.assertEqual((self.origin.accepted, [h.split(b" ")[1] for h in self.origin.heads]), (1, [b"/seg0", b"/seg1"]))

    def test_a_second_request_for_another_host_or_port_closes_both_sides(self):
        for second in ("http://b.qqqqqq.test:%d/x" % self.origin.port, "http://a.qqqqqq.test:%d/x" % self.other.port):
            with self.subTest(second=second), self.relay.connect() as sock:
                sock.sendall(get("http://a.qqqqqq.test:%d/seg0" % self.origin.port, self.token))
                self.assertEqual(read_reply(sock)[0], 200)
                sock.sendall(get(second, self.token))
                self.assertTrue(closed(sock))
        self.assertEqual(self.other.accepted, 0)
        self.assertEqual(len(self.origin.heads), 2)

    def test_a_later_request_whose_token_is_gone_or_another_closes_both_sides(self):
        other = self.relay.register(REMOTE)
        with self.relay.connect() as sock:
            sock.sendall(get("http://a.qqqqqq.test:%d/seg0" % self.origin.port, self.token))
            self.assertEqual(read_reply(sock)[0], 200)
            sock.sendall(get("http://a.qqqqqq.test:%d/seg1" % self.origin.port, other))
            self.assertTrue(closed(sock))
        with self.relay.connect() as sock:
            sock.sendall(get("http://a.qqqqqq.test:%d/seg0" % self.origin.port, self.token))
            self.assertEqual(read_reply(sock)[0], 200)
            for _ in range(helper.RELAY_TOKENS_MAX):
                self.relay.register(REMOTE)
            sock.sendall(get("http://a.qqqqqq.test:%d/seg1" % self.origin.port, self.token))
            self.assertTrue(closed(sock))
        self.assertEqual([h.split(b" ")[1] for h in self.origin.heads], [b"/seg0", b"/seg0"])

    def test_a_later_head_that_stalls_after_its_first_byte_closes_the_connection_at_its_bound(self):
        """A kept-alive connection waits for a later head's first byte as long
        as the peer keeps it, and then gives the rest RELAY_HEAD_S; over that
        the connection is closed, with no reply, because the pump thread may
        be writing to the client."""
        with mock.patch.object(helper, "RELAY_HEAD_S", 0.4), self.relay.connect() as sock:
            sock.sendall(get("http://a.qqqqqq.test:%d/seg0" % self.origin.port, self.token))
            self.assertEqual(read_reply(sock)[0], 200)
            time.sleep(0.6)
            started = time.monotonic()
            sock.sendall(b"GET http://a.qqqqqq.test")
            self.assertTrue(closed(sock, 3.0), "a stalled later head held the connection past its bound")
            elapsed = time.monotonic() - started
        self.assertLess(elapsed, 2.5)
        self.assertEqual([h.split(b" ")[1] for h in self.origin.heads], [b"/seg0"])


# --------------------------------------------------------- rewriting

class RewritingTest(Fixture):
    """What the origin receives is the request in origin form with the
    relay's own headers gone and every other byte as the player wrote it;
    the token reaches no origin, over plain http or CONNECT."""

    def test_the_origin_receives_origin_form_and_the_players_headers_byte_for_byte(self):
        self.classes({"127.0.0.1": "global"})
        origin = Origin(self)
        self.resolving({"a.qqqqqq.test": ["127.0.0.1"]})
        relay = Relay(self)
        token = relay.register(REMOTE)
        raw = (b"GET http://a.qqqqqq.test:%d/live/1.ts?u=1 HTTP/1.1\r\nUser-Agent: Lavf/62\r\n"
               b"Host: provider.example.test\r\nProxy-Connection: keep-alive\r\n%s"
               b"Authorization: Basic c2lnbmVkOmlu\r\nIcy-MetaData: 1\r\n\r\n") % (origin.port, auth(token))
        self.assertEqual(exchange(relay, raw)[0], 200)
        self.assertEqual(origin.heads, [b"GET /live/1.ts?u=1 HTTP/1.1\r\nUser-Agent: Lavf/62\r\n"
                                        b"Host: provider.example.test\r\nAuthorization: Basic c2lnbmVkOmlu\r\n"
                                        b"Icy-MetaData: 1"])
        self.assertNotIn(token.encode(), bytes(origin.received))
        self.assertNotIn(b"roxy-", bytes(origin.received))

    def test_no_byte_a_tunnelled_origin_receives_holds_the_token(self):
        self.classes({"127.0.0.1": "global"})
        echo = Origin(self, echo=True)
        self.resolving({"a.qqqqqq.test": ["127.0.0.1"]})
        relay = Relay(self)
        token = relay.register(REMOTE)
        with relay.connect() as sock:
            sock.sendall(get("a.qqqqqq.test:%d" % echo.port, token, method=b"CONNECT"))
            status, _, _ = read_reply(sock)
            sock.sendall(b"client-hello")
            self.assertEqual(sock.recv(64), b"client-hello")
        self.assertEqual(status, 200)
        self.assertEqual(bytes(echo.received), b"client-hello")


# -------------------------------------------------------- the tunnel

class TunnelTest(Fixture):
    """CONNECT passes bytes both ways unchanged, and TLS stays end to
    end: through the tunnel a client verifies the origin's certificate with
    the right CA and fails without it."""

    def test_bytes_pass_both_ways_unchanged(self):
        self.classes({"127.0.0.1": "global"})
        echo = Origin(self, echo=True)
        self.resolving({"a.qqqqqq.test": ["127.0.0.1"]})
        relay = Relay(self)
        token = relay.register(REMOTE)
        payload = bytes(range(256)) * 512
        with relay.connect() as sock:
            sock.sendall(get("a.qqqqqq.test:%d" % echo.port, token, method=b"CONNECT"))
            status, head, _ = read_reply(sock)
            self.assertEqual(head, b"HTTP/1.1 200 Connection established")
            sock.sendall(payload)
            back = b""
            while len(back) < len(payload):
                chunk = sock.recv(65536)
                if not chunk:
                    break
                back += chunk
        self.assertEqual((status, back), (200, payload))

    def test_a_tunnel_ends_both_sides_when_either_side_ends(self):
        """An origin that closes inside a CONNECT tunnel closes the client's
        side, and a client that ends closes the origin's: the relay keeps no
        half of a tunnel open."""
        self.classes({"127.0.0.1": "global"})
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(4)
        self.addCleanup(listener.close)
        port = listener.getsockname()[1]
        seen = {}

        def origin(case):
            conn, _ = listener.accept()
            with conn:
                conn.settimeout(5)
                if case == "origin":
                    seen[case] = conn.recv(64)
                    return
                try:
                    seen[case] = (conn.recv(64), conn.recv(64))
                except OSError as error:
                    seen[case] = error
        self.resolving({"a.qqqqqq.test": ["127.0.0.1"]})
        relay = Relay(self)
        token = relay.register(REMOTE)
        for case in ("origin", "client"):
            with self.subTest(case=case):
                thread = threading.Thread(target=origin, args=(case,), daemon=True)
                thread.start()
                sock = relay.connect()
                try:
                    sock.sendall(get("a.qqqqqq.test:%d" % port, token, method=b"CONNECT"))
                    self.assertEqual(read_reply(sock)[0], 200)
                    sock.sendall(b"x")
                    if case == "origin":
                        self.assertTrue(closed(sock, 3.0), "the client's side outlived the origin's")
                    else:
                        sock.shutdown(socket.SHUT_WR)
                        thread.join(5)
                        self.assertEqual(seen.get(case), (b"x", b""), "the origin's side outlived the client's")
                finally:
                    sock.close()
                thread.join(5)

    @unittest.skipUnless(shutil.which("openssl"), "openssl is needed to make a certificate")
    def test_tls_through_the_tunnel_verifies_with_the_ca_and_fails_without_it(self):
        work = tempfile.mkdtemp(prefix="relay-tls-")
        self.addCleanup(shutil.rmtree, work, True)
        key, cert = os.path.join(work, "k.pem"), os.path.join(work, "c.pem")
        made = subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                               "-subj", "/CN=tls.qqqqqq.test", "-addext", "subjectAltName=DNS:tls.qqqqqq.test",
                               "-keyout", key, "-out", cert], capture_output=True, timeout=60)
        if made.returncode != 0:
            self.skipTest("openssl could not make a certificate")
        server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.load_cert_chain(cert, key)
        self.classes({"127.0.0.1": "global"})
        origin = Origin(self, context=server)
        self.resolving({"tls.qqqqqq.test": ["127.0.0.1"]})
        relay = Relay(self)
        token = relay.register(REMOTE)
        results = []
        for cafile in (cert, None):
            client = ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()
            with relay.connect() as sock:
                sock.sendall(get("tls.qqqqqq.test:%d" % origin.port, token, method=b"CONNECT"))
                self.assertEqual(read_reply(sock)[0], 200)
                try:
                    with client.wrap_socket(sock, server_hostname="tls.qqqqqq.test") as tls:
                        tls.sendall(b"GET /k HTTP/1.1\r\nHost: tls.qqqqqq.test\r\n\r\n")
                        results.append(read_reply(tls)[0])
                except ssl.SSLCertVerificationError:
                    results.append("unverified")
        self.assertEqual(results, [200, "unverified"])


# ---------------------------------------------- the user's own proxy

class UpstreamProxyTest(Fixture):
    """The user's own proxy, from the relay's
    environment by FFmpeg's rules, carries what it carried before, each
    target judged by name first; a no_proxy match goes direct and is judged
    by address like any unproxied connection."""

    def setUp(self):
        self.classes({"127.0.0.1": "global"})
        self.proxy = Origin(self, "127.0.0.1")

    def test_the_no_proxy_vectors_are_ffmpegs(self):
        for vector in FIXTURE["vectors"]:
            with self.subTest(vector=vector):
                self.assertEqual(helper.relay_no_proxy_match(vector["noProxy"], vector["host"]), vector["match"])

    def test_the_proxy_is_read_as_ffmpeg_reads_it(self):
        for value, want in (("http://u%3Ax:p%40ss@127.0.0.1:3128/", {"host": "127.0.0.1", "port": 3128, "auth": "u%3Ax:p%40ss"}),
                            ("http://a@b@[::1]:8080", {"host": "::1", "port": 8080, "auth": "a@b"}),
                            ("http://proxy.qqqqqq.test", {"host": "proxy.qqqqqq.test", "port": 0, "auth": ""}),
                            ("HTTP://127.0.0.1:3128", None), ("https://127.0.0.1:3128", None),
                            ("127.0.0.1:3128", None), ("", None)):
            with self.subTest(value=value):
                self.assertEqual(helper.relay_upstream({"http_proxy": value}), want)
        self.assertIsNone(helper.relay_upstream({"HTTP_PROXY": "http://127.0.0.1:3128"}))

    def test_a_judged_target_goes_to_the_users_proxy_with_its_credentials(self):
        resolver = self.resolving({"cdn.qqqqqq.test": ["127.0.0.1"]})
        relay = Relay(self, {"http_proxy": "http://me:s%%40cret@127.0.0.1:%d" % self.proxy.port})
        token = relay.register(REMOTE)
        status = exchange(relay, get("http://cdn.qqqqqq.test:8080/live/1.ts", token))[0]
        self.assertEqual(status, 200)
        self.assertEqual(self.proxy.heads, [b"GET http://cdn.qqqqqq.test:8080/live/1.ts HTTP/1.1\r\nHost: h\r\n"
                                            b"Proxy-Authorization: Basic " + base64.b64encode(b"me:s@cret")])
        self.assertEqual(resolver.asked, [("cdn.qqqqqq.test", 8080)])

    def test_a_target_the_users_proxy_would_reach_on_this_machine_is_refused_before_the_proxy_is_asked(self):
        self.resolving({"evil.qqqqqq.test": ["127.0.0.1", "127.0.0.2"]})
        relay = Relay(self, {"http_proxy": "http://127.0.0.1:%d" % self.proxy.port})
        token = relay.register(REMOTE)
        self.assertEqual(exchange(relay, get("http://evil.qqqqqq.test/x", token))[0], 403)
        self.assertEqual(self.proxy.accepted, 0)

    def test_an_unresolvable_target_is_refused_except_a_proxied_playlists_own_host(self):
        self.resolving({"gone.qqqqqq.test": socket.gaierror(socket.EAI_NONAME, "nope"),
                        "prov.qqqqqq.test": socket.gaierror(socket.EAI_NONAME, "nope")})
        relay = Relay(self, {"http_proxy": "http://127.0.0.1:%d" % self.proxy.port})
        remote = relay.register(PROXIED)
        self.assertEqual(exchange(relay, get("http://gone.qqqqqq.test/x", remote))[0], 502)
        self.assertEqual(self.proxy.accepted, 0)
        self.assertEqual(exchange(relay, get("http://prov.qqqqqq.test/x", remote))[0], 200)
        self.assertEqual(exchange(relay, get("http://prov.qqqqqq.test/x", relay.register(REMOTE)))[0], 502)
        self.assertEqual(self.proxy.accepted, 1)

    def test_a_tunnel_through_the_users_proxy_is_asked_for_and_then_blind(self):
        self.resolving({"cdn.qqqqqq.test": ["127.0.0.1"]})
        upstream = socket.socket()
        upstream.bind(("127.0.0.1", 0))
        upstream.listen(4)
        self.addCleanup(upstream.close)
        seen = []

        def proxy():
            conn, _ = upstream.accept()
            with conn:
                data = b""
                while b"\r\n\r\n" not in data:
                    data += conn.recv(4096)
                seen.append(data)
                conn.sendall(b"HTTP/1.1 200 OK\r\n\r\n")
                conn.sendall(conn.recv(4096))
        thread = threading.Thread(target=proxy, daemon=True)
        thread.start()
        relay = Relay(self, {"http_proxy": "http://u:p@127.0.0.1:%d" % upstream.getsockname()[1]})
        token = relay.register(REMOTE)
        with relay.connect() as sock:
            sock.sendall(get("cdn.qqqqqq.test:443", token, method=b"CONNECT"))
            self.assertEqual(read_reply(sock)[0], 200)
            sock.sendall(b"hello")
            self.assertEqual(sock.recv(16), b"hello")
        thread.join(5)
        self.assertEqual(seen, [b"CONNECT cdn.qqqqqq.test:443 HTTP/1.1\r\nHost: cdn.qqqqqq.test:443\r\n"
                                b"Proxy-Authorization: Basic " + base64.b64encode(b"u:p") + b"\r\n\r\n"])

    def test_a_no_proxy_match_goes_direct_and_is_judged_by_address(self):
        """A no_proxy match whose answer is a refused address is refused,
        and neither the user's proxy nor the target sees anything; one whose
        answer is permitted goes direct."""
        target = Origin(self, "127.0.0.2")
        public = Origin(self, "127.0.0.1")
        resolver = self.resolving({"lan.qqqqqq.test": [("127.0.0.2", target.port)],
                                   "ok.qqqqqq.test": [("127.0.0.1", public.port)]})
        relay = Relay(self, {"http_proxy": "http://127.0.0.1:%d" % self.proxy.port, "no_proxy": "qqqqqq.test"})
        token = relay.register(REMOTE)
        self.assertEqual(exchange(relay, get("http://lan.qqqqqq.test:%d/x" % target.port, token))[0], 403)
        self.assertEqual(exchange(relay, get("http://ok.qqqqqq.test:%d/x" % public.port, token))[0], 200)
        self.assertEqual((self.proxy.accepted, target.accepted, public.accepted), (0, 0, 1))
        self.assertEqual(public.heads[0].split(b"\r\n")[0], b"GET /x HTTP/1.1")
        self.assertEqual(len(resolver.asked), 2)


# ------------------------------------------------------- connection bounds

def wait_for(predicate, wait=5.0):
    until = time.monotonic() + wait
    while time.monotonic() < until:
        if predicate():
            return True
        time.sleep(0.02)
    return False


class ConnectionBoundsTest(Fixture):
    """Past RELAY_CONNECTIONS_MAX a client gets 503 and reaches no origin,
    and past RELAY_CONTROL_MAX a control connection is closed unanswered;
    each frees once a held connection ends."""

    def test_past_the_connection_cap_a_client_gets_503_and_reaches_no_origin(self):
        self.classes({"127.0.0.1": "global"})
        origin = Origin(self)
        resolver = self.resolving({"127.0.0.1": ["127.0.0.1"]})
        with mock.patch.object(helper, "RELAY_CONNECTIONS_MAX", 2):
            relay = Relay(self)
            token = relay.register(REMOTE)
            held = [relay.connect() for _ in range(2)]
            self.assertTrue(wait_for(lambda: relay.state.active == 2))
            with relay.connect() as sock:
                status, head, _ = read_reply(sock)
                try:
                    sock.sendall(get("http://127.0.0.1:%d/x" % origin.port, token))
                except OSError:
                    pass
                self.assertTrue(closed(sock))
            self.assertEqual((status, head.split(b"\r\n")[0]), (503, b"HTTP/1.1 503 Service Unavailable"))
            self.assertEqual((origin.accepted, resolver.asked, relay.state.active), (0, [], 2))
            for sock in held:
                sock.close()
            self.assertTrue(wait_for(lambda: relay.state.active == 0))
            self.assertEqual(exchange(relay, get("http://127.0.0.1:%d/x" % origin.port, token))[0], 200)
        self.assertEqual(origin.accepted, 1)

    def test_past_the_control_cap_a_control_connection_is_closed_unanswered(self):
        with mock.patch.object(helper, "RELAY_CONTROL_MAX", 1), mock.patch.object(helper, "RELAY_IPC_S", 5.0):
            relay = Relay(self)
            held = socket.socket(socket.AF_UNIX)
            self.addCleanup(held.close)
            held.connect(relay.path)
            self.assertTrue(wait_for(lambda: relay.state.controls == 1))
            self.assertEqual(relay.control_answer(b'{"op":"status"}\n'), b"")
            held.close()
            self.assertTrue(wait_for(lambda: relay.state.controls == 0))
            self.assertTrue(relay.ask({"op": "status"})["ok"])


# ---------------------------------------------------- the peer's uid

class PeerUidTest(Fixture):
    """A proxy connection is served only to a client of this uid, read
    from /proc/net/tcp before a byte is read."""

    TABLE = ["  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode",
             "   0: 0100007F:9C40 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 1 1",
             "   1: 0100007F:D431 0100007F:1F90 01 00000000:00000000 00:00000000 00000000  1001        0 2 1",
             "   2: 0100007F:D432 0100007F:1F90 01 00000000:00000000 00:00000000 00000000  1000        0 3 1",
             "   3: 0200007F:D433 0100007F:1F90 01 00000000:00000000 00:00000000 00000000     0        0 4 1",
             "   4: 0100007F:1F90 0100007F:D432 01 00000000:00000000 00:00000000 00000000  1000        0 5 1",
             "   5: garbage"]

    def test_the_table_is_read_for_the_client_end_only(self):
        lookup = helper.relay_peer_uid
        if lookup("127.0.0.1", 0xD431, "127.0.0.1", 0x1F90, ["0100007F"]) is not None:
            self.fail("a short line was read")
        self.assertEqual(lookup("127.0.0.1", 0xD431, "127.0.0.1", 0x1F90, self.TABLE), 1001)
        self.assertEqual(lookup("127.0.0.1", 0xD432, "127.0.0.1", 0x1F90, self.TABLE), 1000)
        self.assertEqual(lookup("127.0.0.2", 0xD433, "127.0.0.1", 0x1F90, self.TABLE), 0)
        self.assertIsNone(lookup("127.0.0.1", 0xD439, "127.0.0.1", 0x1F90, self.TABLE))
        self.assertIsNone(lookup("127.0.0.1", 0xD432, "127.0.0.1", 0x1F91, self.TABLE))
        self.assertIsNone(lookup("::1", 0xD432, "127.0.0.1", 0x1F90, self.TABLE))

    def test_this_processs_own_connection_is_found_with_its_uid(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        self.addCleanup(listener.close)
        with socket.create_connection(listener.getsockname(), timeout=5) as client:
            address, port = client.getsockname()
            self.assertEqual(helper.relay_peer_uid(address, port, "127.0.0.1", listener.getsockname()[1]), os.getuid())

    def test_a_client_of_another_uid_is_closed_before_a_byte_is_read(self):
        self.classes({"127.0.0.1": "global"})
        origin = Origin(self)
        resolver = self.resolving({})
        relay = Relay(self)
        token = relay.register(REMOTE)
        with mock.patch.object(helper, "relay_peer_uid", lambda *a, **k: os.getuid() + 1), relay.connect() as sock:
            sock.sendall(get("http://127.0.0.1:%d/x" % origin.port, token))
            self.assertTrue(closed(sock))
        self.assertEqual((origin.accepted, resolver.asked), (0, []))


# ------------------------------------------------ the control socket

class ControlTest(Fixture):
    """The control socket, one JSON line each way."""

    def test_a_line_that_is_not_a_request_is_refused_with_one_sentence(self):
        relay = Relay(self)
        refusal = {"ok": False, "error": {"code": "bad_request", "message": helper.RELAY_CONTROL_REFUSAL}}
        for raw in (b"{\n", b"[]\n", b'{"op":"nope"}\n', b'{"op":"status","x":1}\n', b'"status"\n', b"\xff\n",
                    b'{"op":"load"}\n'):
            with self.subTest(raw=raw):
                self.assertEqual(relay.control_line(raw), refusal)
        self.assertEqual(relay.ask({"op": "load", "policy": {"host": 5}})["error"]["code"], "bad_policy")
        self.assertEqual(relay.ask({"op": "count", "token": "0" * 32})["error"]["code"], "unknown_token")

    def test_a_control_peer_of_another_uid_gets_no_reply_and_registers_nothing(self):
        relay = Relay(self)
        with mock.patch.object(helper, "relay_control_peer_uid", lambda conn: os.getuid() + 1):
            for raw in (b'{"op":"status"}\n', b'{"op":"load","policy":' + json.dumps(REMOTE).encode() + b'}\n'):
                with self.subTest(raw=raw[:20]):
                    self.assertEqual(relay.control_answer(raw), b"")
        self.assertEqual(relay.ask({"op": "status"})["tokens"], 0)

    def test_an_oversized_line_is_refused(self):
        relay = Relay(self)
        got = relay.control_line(b'{"op":"status","pad":"' + b"a" * helper.RELAY_CONTROL_BYTES + b'"}\n')
        self.assertEqual(got["error"]["code"], "too_large")

    def test_status_answers_counts_and_identity_only(self):
        relay = Relay(self)
        relay.register(REMOTE)
        status = relay.ask({"op": "status"})
        self.assertEqual(status, {"ok": True, "port": relay.port, "build": "0.0.0+0badf00d", "child": 4242,
                                  "tokens": 1, "connections": 0, "upstream": 0, "refused": 0})

    def test_a_registration_answers_a_token_and_the_port_and_the_table_keeps_the_newest_eight(self):
        relay = Relay(self)
        replies = [relay.ask({"op": "load", "policy": REMOTE}) for _ in range(helper.RELAY_TOKENS_MAX + 1)]
        for reply in replies:
            self.assertEqual(sorted(reply), ["ok", "port", "token"])
            self.assertRegex(reply["token"], r"\A[0-9a-f]{32}\Z")
            self.assertEqual(reply["port"], relay.port)
        self.assertEqual(len({reply["token"] for reply in replies}), helper.RELAY_TOKENS_MAX + 1)
        self.assertEqual(relay.ask({"op": "status"})["tokens"], helper.RELAY_TOKENS_MAX)
        self.assertEqual(relay.ask({"op": "count", "token": replies[0]["token"]})["error"]["code"], "unknown_token")
        self.assertEqual(relay.ask({"op": "count", "token": replies[1]["token"]}), {"ok": True, "refused": 0, "upstream": 0})

    def test_a_policy_is_read_strictly(self):
        good = [REMOTE, LAN, USER, loopback_relay(34400), {"host": "", "port": None, "loopback": False, "local": True},
                dict(REMOTE, **{"class": "unresolved"})]
        bad = [None, [], {"origin": "shell"}, dict(REMOTE, extra=1), dict(USER, local=True), dict(REMOTE, port=0),
               dict(REMOTE, port=True), dict(REMOTE, port="80"), dict(REMOTE, local="no"),
               dict(REMOTE, **{"class": "lan"}), dict(REMOTE, host=["h"]), dict(REMOTE, host="h" * 5000)]
        for policy in good:
            with self.subTest(policy=policy):
                self.assertIsNotNone(helper.relay_policy_record(policy))
        for policy in bad:
            with self.subTest(policy=policy):
                self.assertIsNone(helper.relay_policy_record(policy))


# ------------------------------------------- a typed URL's first hop

def typed(origin):
    """The record of a typed --url naming `origin`'s own host and port."""
    return {"origin": "user", "host": origin.address, "port": origin.port}


class TypedUrlTest(Fixture):
    """A typed --url's token keeps its first-hop rule
    across ALL of its upstream connections, as DestinationPolicy keeps it
    across one fetch's hops, and the first hop's freedom goes only to a
    first connection to the URL's own host (and, on this machine, its own
    port)."""

    def test_the_first_connection_may_reach_the_lan_and_later_ones_only_its_host(self):
        self.classes({"127.0.0.3": "private", "127.0.0.4": "private"})
        first = Origin(self, "127.0.0.3")
        second = Origin(self, "127.0.0.4")
        self.resolving({"127.0.0.3": ["127.0.0.3"], "127.0.0.4": ["127.0.0.4"]})
        relay = Relay(self)
        token = relay.register(typed(first))
        self.assertEqual(exchange(relay, get("http://127.0.0.3:%d/a" % first.port, token))[0], 200)
        self.assertEqual(exchange(relay, get("http://127.0.0.3:%d/b" % first.port, token))[0], 200)
        self.assertEqual(exchange(relay, get("http://127.0.0.4:%d/c" % second.port, token))[0], 403)
        self.assertEqual((first.accepted, second.accepted), (2, 0))

    def test_the_first_connection_is_decided_under_the_tokens_lock(self):
        self.classes({"127.0.0.3": "private", "127.0.0.4": "private"})
        first = Origin(self, "127.0.0.3")
        second = Origin(self, "127.0.0.4")
        gate = threading.Event()
        order = []

        def slow(name, port):
            order.append(name)
            if name == "127.0.0.3":
                gate.wait(5)
            return Resolver({name: [name]})(name, port)
        with mock.patch.object(helper, "stream_resolve", slow):
            relay = Relay(self)
            token = relay.register(typed(first))
            results = {}

            def fetch(host, port):
                results[host] = exchange(relay, get("http://%s:%d/x" % (host, port), token))[0]
            one = threading.Thread(target=fetch, args=("127.0.0.3", first.port))
            one.start()
            for _ in range(100):
                if order:
                    break
                time.sleep(0.02)
            two = threading.Thread(target=fetch, args=("127.0.0.4", second.port))
            two.start()
            time.sleep(0.3)
            gate.set()
            one.join(10)
            two.join(10)
        self.assertEqual(results, {"127.0.0.3": 200, "127.0.0.4": 403})
        self.assertEqual(second.accepted, 0)

    def test_a_later_connection_to_the_first_ones_host_waits_for_it_to_settle(self):
        """The wait itself: a second connection to the FIRST one's own LAN
        host, made while the first is still in its lookup, is judged
        against what the first recorded once it has connected, and passes;
        judged beside it, before anything was recorded, it would be a later
        hop to a LAN host nobody had reached, and refused."""
        self.classes({"127.0.0.3": "private"})
        first = Origin(self, "127.0.0.3")
        gate = threading.Event()
        asked = []

        def slow(name, port):
            asked.append(name)
            if len(asked) == 1:
                gate.wait(5)
            return Resolver({name: [name]})(name, port)
        self.addCleanup(gate.set)
        with mock.patch.object(helper, "stream_resolve", slow):
            relay = Relay(self)
            token = relay.register(typed(first))
            results = []

            def fetch(path):
                results.append(exchange(relay, get("http://127.0.0.3:%d%s" % (first.port, path), token))[0])
            one = threading.Thread(target=fetch, args=("/a",))
            one.start()
            for _ in range(100):
                if asked:
                    break
                time.sleep(0.02)
            two = threading.Thread(target=fetch, args=("/b",))
            two.start()
            time.sleep(0.3)
            waited = len(asked)
            gate.set()
            one.join(10)
            two.join(10)
        self.assertEqual(waited, 1, "the second connection looked its target up before the first had settled")
        self.assertEqual((results, first.accepted), ([200, 200], 2))

    def test_a_first_connection_to_another_host_is_a_later_hop_and_spends_the_first(self):
        self.classes({"127.0.0.3": "private", "127.0.0.4": "private"})
        typed_host = Origin(self, "127.0.0.3")
        other = Origin(self, "127.0.0.4")
        self.resolving({"127.0.0.3": ["127.0.0.3"], "127.0.0.4": ["127.0.0.4"]})
        relay = Relay(self)
        token = relay.register(typed(typed_host))
        self.assertEqual(exchange(relay, get("http://127.0.0.4:%d/a" % other.port, token))[0], 403)
        self.assertEqual(exchange(relay, get("http://127.0.0.3:%d/b" % typed_host.port, token))[0], 403)
        self.assertEqual((typed_host.accepted, other.accepted), (0, 0))
        fresh = relay.register(typed(typed_host))
        self.assertEqual(exchange(relay, get("http://127.0.0.3:%d/c" % typed_host.port, fresh))[0], 200)

    def test_on_this_machine_the_first_hop_is_the_typed_hosts_own_port(self):
        """Typed as a loopback literal, or as a name that answers loopback:
        either way a first connection to the same host on another port of
        this machine is another host (D-SINK-57), judged as a later hop."""
        typed_port = Origin(self, "127.0.0.1")
        other_port = Origin(self, "127.0.0.1")
        self.resolving({"127.0.0.1": ["127.0.0.1"], "box.qqqqqq.test": ["127.0.0.1"]})
        relay = Relay(self)
        for host in ("127.0.0.1", "box.qqqqqq.test"):
            with self.subTest(host=host):
                record = {"origin": "user", "host": host, "port": typed_port.port}
                token = relay.register(record)
                self.assertEqual(exchange(relay, get("http://%s:%d/a" % (host, other_port.port), token))[0], 403)
                fresh = relay.register(record)
                self.assertEqual(exchange(relay, get("http://%s:%d/b" % (host, typed_port.port), fresh))[0], 200)
        self.assertEqual((typed_port.accepted, other_port.accepted), (2, 0))

    def test_through_the_users_proxy_only_the_typed_host_passes_unresolved_on_the_first_hop(self):
        self.classes({"127.0.0.1": "global"})
        proxy = Origin(self, "127.0.0.1")
        self.resolving({"gone.qqqqqq.test": socket.gaierror(socket.EAI_NONAME, "nope"),
                        "nas.qqqqqq.test": socket.gaierror(socket.EAI_NONAME, "nope")})
        relay = Relay(self, {"http_proxy": "http://127.0.0.1:%d" % proxy.port})
        token = relay.register({"origin": "user", "host": "nas.qqqqqq.test", "port": 80})
        self.assertEqual(exchange(relay, get("http://gone.qqqqqq.test/x", token))[0], 502)
        self.assertEqual(proxy.accepted, 0)
        fresh = relay.register({"origin": "user", "host": "nas.qqqqqq.test", "port": 80})
        self.assertEqual(exchange(relay, get("http://nas.qqqqqq.test/x", fresh))[0], 200)
        self.assertEqual(proxy.accepted, 1)


# ---------------------------------------------- a dead first address

class DeadFirstAddressTest(Fixture):
    """A name whose first answer hangs and whose second
    connects must not fail a channel. The relay starts the next attempt
    RELAY_ATTEMPT_STAGGER_S after the last, as FFmpeg's own connect does,
    where the helper's fetches still try one address after another."""

    def hanging(self):
        """A listener on 127.0.0.2 whose accept queue is full, so a connect to
        it hangs (Linux drops the SYN of a full queue)."""
        sock = socket.socket()
        sock.bind(("127.0.0.2", 0))
        sock.listen(0)
        self.addCleanup(sock.close)
        fill = []
        for _ in range(3):
            client = socket.socket()
            client.setblocking(False)
            client.connect_ex(sock.getsockname())
            fill.append(client)
            self.addCleanup(client.close)
        time.sleep(0.1)
        probe = socket.socket()
        probe.settimeout(0.3)
        try:
            probe.connect(sock.getsockname())
            self.skipTest("this kernel accepted a connect to a full queue")
        except (socket.timeout, TimeoutError):
            pass
        finally:
            probe.close()
        return sock.getsockname()[1]

    def attempts(self):
        """While entered, every socket the process creates that is not an
        accepted connection is recorded in the list it yields, so a test can
        ask, after a connect, which of the connect's attempts are still open:
        a reference held here keeps one the connector forgot open, where
        dropping its last reference would have closed it."""
        made = []
        real = socket.socket

        class Recorded(real):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if kwargs.get("fileno") is None and (len(args) < 4 or args[3] is None):
                    made.append(self)

        @contextlib.contextmanager
        def recording():
            with mock.patch.object(socket, "socket", Recorded):
                yield made
            self.addCleanup(lambda: [sock.close() for sock in made])
        return recording()

    def test_the_relay_reaches_the_second_answer_within_one_stagger(self):
        hang = self.hanging()
        good = Origin(self, "127.0.0.1")
        self.resolving({"dual.qqqqqq.test": [("127.0.0.2", hang), ("127.0.0.1", good.port)]})
        relay = Relay(self)
        token = relay.register(LAN)
        started = time.monotonic()
        status = exchange(relay, get("http://dual.qqqqqq.test:%d/x" % good.port, token))[0]
        elapsed = time.monotonic() - started
        self.assertEqual((status, good.accepted), (200, 1))
        self.assertLess(elapsed, 1.5)

    def test_the_staggered_connect_and_the_fetches_serial_one(self):
        hang = self.hanging()
        good = Origin(self, "127.0.0.1")
        answers = Resolver({"dual.qqqqqq.test": [("127.0.0.2", hang), ("127.0.0.1", good.port)]})

        def lookup(host, port, bound):
            return answers(host, port)
        started = time.monotonic()
        with self.attempts() as made:
            sock = helper.bounded_create_connection(("dual.qqqqqq.test", good.port), 2.0, resolve=lookup,
                                                    stagger=helper.RELAY_ATTEMPT_STAGGER_S,
                                                    in_flight=helper.RELAY_ATTEMPTS_IN_FLIGHT)
        staggered = time.monotonic() - started
        self.assertEqual((sock.getpeername()[1], sock.gettimeout()), (good.port, 2.0))
        # The losing attempt, still connecting to the dead answer when the
        # second won, was closed: only the winner is open.
        self.assertEqual(len(made), 2)
        self.assertEqual([attempt for attempt in made if attempt.fileno() != -1], [sock])
        sock.close()
        started = time.monotonic()
        sock = helper.bounded_create_connection(("dual.qqqqqq.test", good.port), 1.0, resolve=lookup)
        serial = time.monotonic() - started
        sock.close()
        self.assertLess(staggered, 1.0)
        self.assertGreaterEqual(serial, 0.9)

    def test_every_attempt_ends_at_the_bound(self):
        hang = self.hanging()
        answers = Resolver({"dead.qqqqqq.test": [("127.0.0.2", hang)] * 4})
        started = time.monotonic()
        with self.attempts() as made, self.assertRaises(OSError):
            helper.bounded_create_connection(("dead.qqqqqq.test", hang), 0.6, resolve=lambda h, p, b: answers(h, p),
                                             stagger=0.05, in_flight=3)
        self.assertLess(time.monotonic() - started, 1.5)
        # Three were in flight at the bound, the fourth never started, and
        # every one that started was closed.
        self.assertEqual(len(made), 3)
        self.assertEqual([attempt for attempt in made if attempt.fileno() != -1], [])


# ------------------------------------------------------ the lookups' threads

def stated_getaddrinfo(blocked, release):
    """socket.getaddrinfo for the tests below, which run the SHIPPING
    resolve_within: a name in `blocked` waits for `release` and then answers
    nothing; an IP literal is answered as getaddrinfo answers one, with no
    query; any other name is an error, and never reaches a real resolver.
    `asked` records (host, port) for every call, the test's own connects to
    the relay included."""
    import ipaddress
    real = socket.getaddrinfo
    asked = []

    def lookup(host, port, *rest, **kwargs):
        text = host.decode("utf-8", "replace") if isinstance(host, bytes) else str(host)
        asked.append((text, port))
        if text in blocked:
            release.wait(10)
            raise socket.gaierror(socket.EAI_NONAME, "stated: no answer")
        try:
            ipaddress.ip_address(text)
        except ValueError:
            raise socket.gaierror(socket.EAI_NONAME, "stated: a name nobody stated") from None
        return real(host, port, *rest, **kwargs)
    return lookup, asked


class LookupThreadsTest(Fixture):
    """The relay asks lookups from many threads at once. The process-wide
    stack size each lookup's start sets is restored as it was found, however
    the starts interleave; and once RELAY_LOOKUPS_MAX lookups are
    outstanding -- a lookup that outlived its bound still runs on the
    resolver's own clock -- a new upstream connection is answered 502 and
    reaches no origin, until they end."""

    def test_interleaved_lookups_leave_the_stack_size_as_they_found_it(self):
        real_thread = threading.Thread

        class SlowStart(real_thread):
            """Holds a lookup's start open, so a second caller arrives while
            the first has the stack size set and not yet restored."""
            def start(self):
                if self.name == "omarchy-iptv-resolve":
                    time.sleep(0.2)
                super().start()
        original = threading.stack_size(helper.RELAY_THREAD_STACK_BYTES)
        self.addCleanup(threading.stack_size, original)
        release = threading.Event()
        release.set()
        lookup, _ = stated_getaddrinfo((), release)
        errors = []

        def ask():
            try:
                REAL_RESOLVE_WITHIN("127.0.0.1", 80, 2.0)
            except BaseException as error:
                errors.append(error)
        callers = [real_thread(target=ask) for _ in range(2)]
        with mock.patch.object(socket, "getaddrinfo", lookup), mock.patch.object(threading, "Thread", SlowStart):
            callers[0].start()
            time.sleep(0.1)
            callers[1].start()
            for caller in callers:
                caller.join(10)
        self.assertEqual(errors, [])
        self.assertEqual(threading.stack_size(), helper.RELAY_THREAD_STACK_BYTES)

    def test_past_the_outstanding_lookups_cap_a_connection_is_502_and_reaches_no_origin(self):
        self.classes({"127.0.0.1": "global"})
        origin = Origin(self)
        release = threading.Event()
        self.addCleanup(release.set)
        lookup, asked = stated_getaddrinfo(("hang.qqqqqq.test",), release)
        base = helper.RESOLVE_WORKERS["live"]
        with mock.patch.object(helper, "resolve_within", REAL_RESOLVE_WITHIN), \
                mock.patch.object(socket, "getaddrinfo", lookup), \
                mock.patch.object(helper, "STREAM_LOOKUP_TIMEOUT_S", 0.3), \
                mock.patch.object(helper, "RELAY_LOOKUPS_MAX", base + 2):
            relay = Relay(self)
            token = relay.register(REMOTE)
            for _ in range(2):
                status, head, _ = exchange(relay, get("http://hang.qqqqqq.test/x", token))
                self.assertEqual(head.split(b"\r\n")[0], b"HTTP/1.1 502 " + helper.RELAY_LOOKUP_FAILED.encode())
            self.assertEqual(helper.RESOLVE_WORKERS["live"], base + 2)
            target = get("http://127.0.0.1:%d/x" % origin.port, token)
            started = time.monotonic()
            status, head, _ = exchange(relay, target)
            elapsed = time.monotonic() - started
            self.assertEqual(head.split(b"\r\n")[0], b"HTTP/1.1 502 " + helper.RELAY_LOOKUP_FAILED.encode())
            self.assertLess(elapsed, 0.3, "the refusal waited for a lookup")
            self.assertEqual((origin.accepted, asked.count(("127.0.0.1", origin.port))), (0, 0))
            release.set()
            self.assertTrue(wait_for(lambda: helper.RESOLVE_WORKERS["live"] == base))
            self.assertEqual(exchange(relay, target)[0], 200)
        self.assertEqual(origin.accepted, 1)
        self.assertEqual([at for at in asked if at[0] == "hang.qqqqqq.test"], [("hang.qqqqqq.test", 80)] * 2)
        self.assertEqual(asked.count(("127.0.0.1", origin.port)), 1)

    def test_past_the_outstanding_lookups_cap_the_users_proxy_is_not_looked_up_and_the_connect_is_502(self):
        """The lookup of the user's own proxy's NAME (relay_proxy_lookup) is
        held to RELAY_LOOKUPS_MAX as every lookup the relay makes is (the
        branch's recheck, 2026-11-16: no test reached it). The workers are
        held at the cap by two target lookups that never answer, through the
        shipping lookup and a stated getaddrinfo; the next target is answered
        by the suite's stand-in for the play-time lookup, so the proxy's own
        lookup is the one that meets the cap: 502 RELAY_LOOKUP_FAILED at
        once, the proxy's name never asked and the proxy never reached. Once
        the held lookups end the same request reaches the proxy, by the
        stated answer for its name (a literal of this test's own listener)."""
        self.classes({"127.0.0.1": "global"})
        proxy = Origin(self)
        release = threading.Event()
        self.addCleanup(release.set)
        lookup, asked = stated_getaddrinfo(("hang.qqqqqq.test",), release)

        def named(host, port, *rest, **kwargs):
            text = host.decode("utf-8", "replace") if isinstance(host, bytes) else str(host)
            if text == "proxy.qqqqqq.test":
                asked.append((text, port))
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]
            return lookup(host, port, *rest, **kwargs)
        targets = Resolver({"cdn.qqqqqq.test": ["127.0.0.1"]})
        refused = b"HTTP/1.1 502 " + helper.RELAY_LOOKUP_FAILED.encode()
        base = helper.RESOLVE_WORKERS["live"]
        with mock.patch.object(helper, "resolve_within", REAL_RESOLVE_WITHIN), \
                mock.patch.object(socket, "getaddrinfo", named), \
                mock.patch.object(helper, "STREAM_LOOKUP_TIMEOUT_S", 0.3), \
                mock.patch.object(helper, "RELAY_LOOKUPS_MAX", base + 2):
            relay = Relay(self, {"http_proxy": "http://proxy.qqqqqq.test:%d" % proxy.port})
            token = relay.register(REMOTE)
            for _ in range(2):
                self.assertEqual(exchange(relay, get("http://hang.qqqqqq.test/x", token))[0], 502)
            self.assertEqual(helper.RESOLVE_WORKERS["live"], base + 2)
            target = get("http://cdn.qqqqqq.test:8080/live/1.ts", token)
            with mock.patch.object(helper, "stream_resolve", targets):
                started = time.monotonic()
                status, head, _ = exchange(relay, target)
                elapsed = time.monotonic() - started
                self.assertEqual(head.split(b"\r\n")[0], refused)
                self.assertLess(elapsed, 0.3, "the refusal waited for a lookup")
                self.assertEqual(targets.asked, [("cdn.qqqqqq.test", 8080)])
                self.assertEqual((proxy.accepted, [at for at in asked if at[0] == "proxy.qqqqqq.test"]), (0, []))
                release.set()
                self.assertTrue(wait_for(lambda: helper.RESOLVE_WORKERS["live"] == base))
                self.assertEqual(exchange(relay, target)[0], 200)
        self.assertEqual(proxy.accepted, 1)
        self.assertEqual([at for at in asked if at[0] == "proxy.qqqqqq.test"], [("proxy.qqqqqq.test", proxy.port)])
        self.assertEqual(targets.unexpected, [])


# ----------------------------------------------------- nothing named

class NothingNamedTest(Fixture):
    """No reply, refusal or status the relay sends carries a host, a
    path or a userinfo -- every one is a fixed text."""

    def test_no_reply_names_what_it_was_asked_about(self):
        self.classes({"127.0.0.1": "global"})
        target = Origin(self, "127.0.0.2")
        self.resolving({"evil.qqqqqq.test": ["127.0.0.2"], "gone.qqqqqq.test": [],
                        "dead.qqqqqq.test": [("127.0.0.1", 9)]})
        relay = Relay(self)
        token = relay.register(REMOTE)
        replies = []
        for raw in (get("http://evil.qqqqqq.test:%d/qqqqqq/k?qqqqqq=1" % target.port, token),
                    get("http://gone.qqqqqq.test/qqqqqq", token),
                    get("http://dead.qqqqqq.test/qqqqqq", token),
                    get("http://user:qqqqqq@evil.qqqqqq.test/qqqqqq", token),
                    get("http://evil.qqqqqq.test/qqqqqq"),
                    get("http://evil.qqqqqq.test/qqqqqq", token, method=b"POST"),
                    get("evil.qqqqqq.test:%d" % target.port, token, method=b"CONNECT"),
                    get("http://userqqqqqq/x", token)):
            with relay.connect() as sock:
                sock.sendall(raw)
                data = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
            replies.append(data)
        replies.append(json.dumps(relay.ask({"op": "status"})).encode())
        replies.append(json.dumps(relay.ask({"op": "count", "token": token})).encode())
        self.assertEqual(len([r for r in replies if r]), 10)
        for reply in replies:
            self.assertNotIn(LEAK.encode(), reply)
        self.assertEqual(target.accepted, 0)


# ---------------------------------------------- the verb's lifecycle

LAUNCHER = r"""
import ctypes, fcntl, os, sys
proxy, control, stub, child_argv = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4:]
high = [fcntl.fcntl(fd, fcntl.F_DUPFD, 10) for fd in (proxy, control)]
for fd in (proxy, control):
    os.close(fd)
for fd, at in zip(high, (3, 4)):
    os.dup2(fd, at)
    os.close(fd)
parent = os.getpid()
pid = os.fork()
if pid == 0:
    ctypes.CDLL(None, use_errno=True).prctl(1, 9, 0, 0, 0)   # PR_SET_PDEATHSIG, SIGKILL
    if os.getppid() != parent:
        os._exit(1)
    os.close(3)
    os.close(4)
    null = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null, 2)
    os.execv(child_argv[0], child_argv)
os.execv(sys.executable, [sys.executable, "-I", stub, "player", "relay", "--child=%d" % pid])
"""


# The relay OFF its group's lead, in a pid namespace of its own, so that a
# reaped child's pid can be handed to another process on purpose
# (ns_last_pid) and a signal sent by pid would reach it. Pid 1 here is this
# script: it dies with the unshare that started it, and when it exits the
# kernel kills everything left in the namespace. Every signal it sends goes
# to the relay it forked itself, through a pidfd whose command line it read.
NAMESPACE = r"""
import ctypes, fcntl, json, os, signal, socket, sys, time
work, stub, mode = sys.argv[1], sys.argv[2], sys.argv[3]
ctypes.CDLL(None, use_errno=True).prctl(1, 9, 0, 0, 0)   # PR_SET_PDEATHSIG, SIGKILL


def bounded(predicate, wait):
    until = time.monotonic() + wait
    while time.monotonic() < until:
        if predicate():
            return True
        time.sleep(0.02)
    return False


proxy = socket.socket()
proxy.bind(("127.0.0.1", 0))
proxy.listen(8)
path = os.path.join(work, "ns.sock.relay")
control = socket.socket(socket.AF_UNIX)
control.bind(path)
control.listen(8)
go, termed, ready = (os.path.join(work, name) for name in ("go", "termed", "ready"))
relay = os.fork()
if relay == 0:
    high = [fcntl.fcntl(sock.fileno(), fcntl.F_DUPFD, 10) for sock in (proxy, control)]
    proxy.close()
    control.close()
    for fd, at in zip(high, (3, 4)):
        os.dup2(fd, at)
        os.close(fd)
    child = os.fork()
    if child == 0:
        os.close(3)
        os.close(4)
        if mode == "live":
            def done(signum, frame):
                open(termed, "w").write("term")
                os._exit(0)
            signal.signal(signal.SIGTERM, done)
            time.sleep(20)
            os._exit(0)
        if os.fork() == 0:          # keeps the relay serving once the child has gone
            time.sleep(20)
            os._exit(0)
        bounded(lambda: os.path.exists(go), 20)
        os._exit(0)
    os.execv(sys.executable, [sys.executable, "-I", stub, "player", "relay", "--child=%d" % child])
proxy.close()
control.close()


def status():
    try:
        with socket.socket(socket.AF_UNIX) as sock:
            sock.settimeout(2)
            sock.connect(path)
            sock.sendall(b'{"op":"status"}\n')
            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
        return json.loads(data) if data else None
    except (OSError, ValueError):
        return None


found = {}


def answered():
    found["status"] = status()
    return found["status"] is not None


result = {"mode": mode}
if not bounded(answered, 15):
    result["error"] = "the relay never answered"
else:
    child = found["status"]["child"]
    relay_fd = os.pidfd_open(relay)
    if b"relay" not in open("/proc/%d/cmdline" % relay, "rb").read().split(b"\0"):
        raise SystemExit("not the relay")
    if mode == "reuse":
        open(go, "w").write("1")
        if not bounded(lambda: not os.path.exists("/proc/%d" % child), 10):
            raise SystemExit("the child was never reaped")
        with open("/proc/sys/kernel/ns_last_pid", "w") as handle:
            handle.write(str(child - 1))
        impostor = os.fork()
        if impostor == 0:
            def hit(signum, frame):
                open(termed, "w").write("impostor")
                os._exit(0)
            signal.signal(signal.SIGTERM, hit)
            open(ready, "w").write("1")
            time.sleep(20)
            os._exit(0)
        result["reused"] = impostor == child
        bounded(lambda: os.path.exists(ready), 10)
    signal.pidfd_send_signal(relay_fd, signal.SIGTERM)

    def ended():
        pid, code = os.waitpid(relay, os.WNOHANG)
        return pid != 0
    result["relayEnded"] = bounded(ended, 10)
    time.sleep(0.3)
    result["termed"] = open(termed).read() if os.path.exists(termed) else ""
print(json.dumps(result))
"""


class LifecycleTest(unittest.TestCase):
    """The real `player relay` verb, as a subprocess, with a child
    started the way the design's spawn starts the player (a launcher that
    hands it the two listeners at fds 3 and 4, forks the child with
    PR_SET_PDEATHSIG, and execs the relay in its own session).

    The LAUNCHER covers the `player relay` verb only, never the spawn: it is
    a copy of spawn_player's shape, not a call of it, and it makes no
    PR_SET_CHILD_SUBREAPER call of its own, so the wrapper case below
    exercises the flag the relay sets at its own start, after its `go` file
    waited for the relay to answer. The spawn's own call, made before the
    player is forked, is held by tests/test_relay_player.py's
    SpawnPlayerTest (a wrapper that backgrounds the player through the
    shipping `player start`)."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="relay-life-")
        os.chmod(self.dir, 0o700)
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.processes = []
        self.pidfds = []
        self.addCleanup(self.reap)

    def reap(self):
        # Only processes this test started: the launchers through their Popen
        # (which sends nothing once it has reaped one, so a reused pid is
        # never reached), and each child the relay names through a pidfd taken
        # while its command line named this test's directory (track).
        for fd in self.pidfds:
            try:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
            except OSError:
                pass
            os.close(fd)
        for process in self.processes:
            if process.poll() is None:
                process.kill()
                try:
                    process.wait(5)
                except subprocess.TimeoutExpired:
                    pass

    def track(self, pid):
        """Pin the relay's child `pid` for the cleanup, once its command
        line names this test's own directory; never a pid read off ancestry."""
        fd = os.pidfd_open(pid)
        try:
            if os.fsencode(self.dir) not in pathlib.Path("/proc/%d/cmdline" % pid).read_bytes():
                raise AssertionError("pid %d is not this test's child; not tracking it" % pid)
            signal.pidfd_send_signal(fd, 0)
        except BaseException:
            os.close(fd)
            raise
        self.pidfds.append(fd)
        return pid

    def start(self, child_argv, environ=None):
        proxy = socket.socket()
        proxy.bind(("127.0.0.1", 0))
        proxy.listen(64)
        path = os.path.join(self.dir, "mpv.sock.relay")
        control = socket.socket(socket.AF_UNIX)
        control.bind(path)
        control.listen(8)
        launcher = os.path.join(self.dir, "launch.py")
        pathlib.Path(launcher).write_text(LAUNCHER, encoding="ascii")
        env = dict(os.environ if environ is None else environ)
        env.pop("DISPLAY", None)
        err = open(os.path.join(self.dir, "stderr"), "wb")
        self.addCleanup(err.close)
        process = subprocess.Popen([sys.executable, "-I", launcher, str(proxy.fileno()), str(control.fileno()),
                                    str(HELPER)] + child_argv, pass_fds=(proxy.fileno(), control.fileno()),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err, env=env,
                                   start_new_session=True)
        self.processes.append(process)
        proxy.close()
        control.close()
        return process, path

    def status(self, path, wait=10.0):
        until = time.monotonic() + wait
        while time.monotonic() < until:
            try:
                with socket.socket(socket.AF_UNIX) as sock:
                    sock.settimeout(2)
                    sock.connect(path)
                    sock.sendall(b'{"op":"status"}\n')
                    data = b""
                    while not data.endswith(b"\n"):
                        chunk = sock.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    if data:
                        return json.loads(data)
            except OSError:
                pass
            time.sleep(0.05)
        self.fail("the relay never answered its status")

    def gone(self, pid, wait):
        until = time.monotonic() + wait
        while time.monotonic() < until:
            try:
                with open("/proc/%d/stat" % pid) as handle:
                    if handle.read().rsplit(")", 1)[1].split()[0] == "Z":
                        return True
            except OSError:
                return True
            time.sleep(0.05)
        return False

    def stub(self, life):
        sock = os.path.join(self.dir, "mpv.sock")
        return [sys.executable, "-I", str(STUB_MPV), "--input-ipc-server=" + sock], dict(os.environ, STUB_LIFE=str(life))

    def test_the_relay_exits_when_its_child_does_and_removes_its_socket(self):
        argv, env = self.stub(1.5)
        process, path = self.start(argv, env)
        status = self.status(path)
        self.assertEqual(status["build"], helper.player_build())
        self.assertEqual(process.wait(15), 0)
        self.assertFalse(os.path.exists(path))

    def test_a_relay_killed_takes_its_child_with_it(self):
        argv, env = self.stub(60)
        process, path = self.start(argv, env)
        child = self.status(path)["child"]
        self.track(child)
        process.kill()
        process.wait(5)
        self.assertTrue(self.gone(child, 2.0))

    def test_sigterm_reaches_the_player_and_then_ends_the_relay(self):
        """SIGTERM is passed to the group the relay leads, so the player
        quits on its own SIGTERM (it writes a marker from its handler here)
        before the relay exits and its death signal kills what is left."""
        marker = os.path.join(self.dir, "termed")
        player = [sys.executable, "-I", "-c",
                  "import signal, sys, time\n"
                  "def done(signum, frame):\n"
                  "    open(sys.argv[1], 'w').write('term')\n"
                  "    sys.exit(0)\n"
                  "signal.signal(signal.SIGTERM, done)\n"
                  "time.sleep(60)\n", marker]
        process, path = self.start(player)
        child = self.status(path)["child"]
        self.track(child)
        process.send_signal(signal.SIGTERM)
        self.assertEqual(process.wait(10), 0)
        self.assertTrue(self.gone(child, 3.0))
        self.assertEqual(pathlib.Path(marker).read_text() if os.path.exists(marker) else "", "term")
        self.assertFalse(os.path.exists(path))

    def test_a_wrapper_that_backgrounds_the_player_leaves_the_relay_running_while_the_player_does(self):
        """The relay is the player's subreaper: a user's wrapper that runs
        the player in the background and exits hands the player to the
        relay, which then lives as long as the player does."""
        go = os.path.join(self.dir, "go")
        done = os.path.join(self.dir, "done")
        wrapper = [sys.executable, "-I", "-c",
                   "import os, sys, time\n"
                   "pid = os.fork()\n"
                   "if pid == 0:\n"
                   "    for _ in range(600):\n"
                   "        if os.path.exists(sys.argv[2]):\n"
                   "            break\n"
                   "        time.sleep(0.02)\n"
                   "    os._exit(0)\n"
                   "for _ in range(600):\n"
                   "    if os.path.exists(sys.argv[1]):\n"
                   "        break\n"
                   "    time.sleep(0.02)\n", go, done]
        process, path = self.start(wrapper)
        self.status(path)
        pathlib.Path(go).write_text("1")
        time.sleep(1.0)
        self.assertIsNone(process.poll(), "the relay ended with its player still running")
        self.assertEqual(self.status(path)["ok"], True)
        pathlib.Path(done).write_text("1")
        self.assertEqual(process.wait(15), 0)

    def test_the_relay_is_not_dumpable_has_no_core_and_says_nothing(self):
        argv, env = self.stub(60)
        env = dict(env, OMARCHY_IPTV_URL="http://u:qqqqqq@x.test/p")
        process, path = self.start(argv, env)
        status = self.status(path)
        with self.assertRaises(PermissionError):
            open("/proc/%d/environ" % process.pid, "rb").read()
        limits = pathlib.Path("/proc/%d/limits" % process.pid).read_text()
        core = [line for line in limits.splitlines() if line.startswith("Max core file size")][0].split()
        self.assertEqual(core[4:6], ["0", "0"])
        cmdline = pathlib.Path("/proc/%d/cmdline" % process.pid).read_bytes().split(b"\0")
        self.assertEqual(cmdline[-4:], [b"player", b"relay", b"--child=%d" % status["child"], b""])
        # A credentialed request, refused for want of a token, then one with it.
        with socket.socket(socket.AF_UNIX) as sock:
            sock.connect(path)
            sock.sendall(b'{"op":"load","policy":{"origin":"user","host":"x.test","port":9}}\n')
            token = json.loads(sock.makefile().readline())["token"]
        for raw in (get("http://u:qqqqqq@127.0.0.1:9/qqqqqq"), get("http://127.0.0.1:9/qqqqqq", token)):
            with socket.create_connection(("127.0.0.1", status["port"]), timeout=5) as sock:
                sock.sendall(raw)
                read_reply(sock)
        self.assertNotIn(token.encode(), b"\0".join(cmdline))
        process.send_signal(signal.SIGTERM)
        process.wait(10)
        self.assertEqual(pathlib.Path(self.dir, "stderr").read_bytes(), b"")

    def test_a_socket_that_replaced_the_relays_own_at_its_path_survives_the_relays_exit(self):
        """A newer relay binds the same path while an older one waits out its
        linger (a restart, a replacement); the older one removes the path at
        exit only while it is still the file it was given."""
        done = os.path.join(self.dir, "done")
        child = [sys.executable, "-I", "-c",
                 "import os, sys, time\n"
                 "for _ in range(1500):\n"
                 "    if os.path.exists(sys.argv[1]):\n"
                 "        break\n"
                 "    time.sleep(0.02)\n", done]
        process, path = self.start(child)
        self.status(path)
        os.unlink(path)
        newer = socket.socket(socket.AF_UNIX)
        self.addCleanup(newer.close)
        newer.bind(path)
        newer.listen(1)
        held = os.stat(path)
        pathlib.Path(done).write_text("1")
        self.assertEqual(process.wait(15), 0)
        self.assertTrue(os.path.exists(path), "the relay removed a socket it was not given")
        now = os.stat(path)
        self.assertEqual((now.st_dev, now.st_ino), (held.st_dev, held.st_ino))

    def test_a_sigterm_kills_a_child_of_its_group_that_ignores_it_once_the_grace_is_over(self):
        """A user's wrapper that ignores SIGTERM, and the real player it
        forked, which has no death signal of its own: the relay passes the
        SIGTERM on, waits RELAY_TERM_GRACE_S, removes its socket, and then
        kills the group it leads, itself included, so neither outlives it
        with a dead proxy."""
        ready = os.path.join(self.dir, "grandchild")
        wrapper = [sys.executable, "-I", "-c",
                   "import os, signal, sys, time\n"
                   "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                   "if os.fork() == 0:\n"
                   "    open(sys.argv[1] + '.tmp', 'w').write(str(os.getpid()))\n"
                   "    os.rename(sys.argv[1] + '.tmp', sys.argv[1])\n"
                   "    time.sleep(60)\n"
                   "    os._exit(0)\n"
                   "time.sleep(60)\n", ready]
        process, path = self.start(wrapper)
        self.status(path)
        until = time.monotonic() + 10
        while not os.path.exists(ready) and time.monotonic() < until:
            time.sleep(0.02)
        grandchild = self.track(int(pathlib.Path(ready).read_text()))
        started = time.monotonic()
        process.send_signal(signal.SIGTERM)
        code = process.wait(15)
        elapsed = time.monotonic() - started
        self.assertTrue(self.gone(grandchild, 3.0), "a child of the relay's group outlived it")
        self.assertEqual(code, -signal.SIGKILL)
        self.assertFalse(os.path.exists(path))
        self.assertGreaterEqual(elapsed, helper.RELAY_TERM_GRACE_S - 0.2)

    def test_it_refuses_a_child_that_is_not_its_own(self):
        """--child must name this process's own child, pinned by a pidfd
        before the reaper runs: a relay that is not a spawn's never starts."""
        proxy = socket.socket()
        proxy.bind(("127.0.0.1", 0))
        proxy.listen(1)
        self.addCleanup(proxy.close)
        control = socket.socket(socket.AF_UNIX)
        control.bind(os.path.join(self.dir, "c.relay"))
        control.listen(1)
        self.addCleanup(control.close)
        launch = ("import fcntl, os, sys\n"
                  "high = [fcntl.fcntl(int(fd), fcntl.F_DUPFD, 10) for fd in sys.argv[1:3]]\n"
                  "for fd, at in zip(high, (3, 4)):\n"
                  "    os.dup2(fd, at)\n"
                  "os.execv(sys.executable, [sys.executable, '-I', sys.argv[3], 'player', 'relay', "
                  "'--child=' + sys.argv[4]])\n")
        done = subprocess.run([sys.executable, "-I", "-c", launch, str(proxy.fileno()), str(control.fileno()),
                               str(HELPER), str(os.getpid())], pass_fds=(proxy.fileno(), control.fileno()),
                              capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL,
                              start_new_session=True)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual(json.loads(done.stdout.strip().splitlines()[-1])["error"]["code"], "relay_refused")

    def in_namespace(self, mode):
        """NAMESPACE run as pid 1 of a new pid namespace; -> its result."""
        if not shutil.which("unshare"):
            self.skipTest("unshare is needed for a pid namespace")
        script = os.path.join(self.dir, "ns.py")
        pathlib.Path(script).write_text(NAMESPACE, encoding="ascii")
        env = dict(os.environ)
        env.pop("DISPLAY", None)
        done = subprocess.run(["unshare", "-rpf", "--mount-proc", sys.executable, "-I", script, self.dir, str(HELPER),
                               mode], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL,
                              start_new_session=True, env=env)
        lines = [line for line in done.stdout.splitlines() if line.startswith('{"mode"')]
        if not lines and "unshare failed" in done.stderr:
            self.skipTest("no pid namespace here: %s" % done.stderr.strip()[:200])
        self.assertTrue(lines, "no result: rc %d, stderr %r" % (done.returncode, done.stderr[-400:]))
        return json.loads(lines[-1])

    def test_off_its_groups_lead_a_sigterm_reaches_its_child_through_the_pidfd(self):
        result = self.in_namespace("live")
        self.assertNotIn("error", result)
        self.assertEqual((result["relayEnded"], result["termed"]), (True, "term"))

    def test_off_its_groups_lead_a_sigterm_never_reaches_a_reaped_childs_reused_pid(self):
        """The child is reaped and its pid handed to an impostor that would
        record a SIGTERM; the relay, asked to stop, signals its child through
        the pidfd it took at its start, which answers ESRCH, and the
        impostor hears nothing."""
        result = self.in_namespace("reuse")
        self.assertNotIn("error", result)
        self.assertTrue(result["reused"], "the namespace did not hand the reaped child's pid on")
        self.assertEqual((result["relayEnded"], result["termed"]), (True, ""))

    def test_it_refuses_to_run_without_its_two_listeners(self):
        done = subprocess.run([sys.executable, "-I", str(HELPER), "player", "relay", "--child=4242"],
                              capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        self.assertEqual(done.returncode, 1)
        self.assertEqual(json.loads(done.stdout.strip().splitlines()[-1])["error"]["code"], "relay_refused")
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        self.addCleanup(listener.close)
        unix = socket.socket(socket.AF_UNIX)
        unix.bind(os.path.join(self.dir, "c"))
        unix.listen(1)
        self.addCleanup(unix.close)
        for fds in ((listener, unix), (unix, unix)):
            with self.subTest(fds=[s.family for s in fds]):
                launch = ("import os, sys\nos.dup2(int(sys.argv[1]), 3)\nos.dup2(int(sys.argv[2]), 4)\n"
                          "os.execv(sys.executable, [sys.executable, '-I', sys.argv[3], 'player', 'relay', '--child=4242'])\n")
                done = subprocess.run([sys.executable, "-I", "-c", launch, str(fds[0].fileno()), str(fds[1].fileno()),
                                       str(HELPER)], pass_fds=(fds[0].fileno(), fds[1].fileno()),
                                      capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
                self.assertEqual(done.returncode, 1, done.stderr)
                self.assertIn('"relay_refused"', done.stdout)


if __name__ == "__main__":
    unittest.main()
