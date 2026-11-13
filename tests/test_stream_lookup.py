"""D-SINK-101 (the marketplace maintainer on omacom/omarchy-plugin-marketplace
#14817, against 0.19.0 at 34fac24): a channel from a playlist that is not
local named a dotted host NAME whose address is on this machine or the LAN,
and the player was handed it, because every rule judged what the address
SAYS -- a literal is classed as written -- and the player, not the helper,
looked the name up. So a remote playlist could send the player's requests to
a local service with no DNS rebinding.

Since 2026-11-13 player_target looks a cached channel's host name up itself
(stream_lookup_refusal, through stream_resolve and resolve_within) and
judges every address the answer holds by the rule a literal meets
(_class_refusal): one refused address refuses the channel as `local_address`
with one fixed sentence that names no host; a name it cannot look up within
STREAM_LOOKUP_TIMEOUT_S is `unchecked_address`.

How this module observes it. NOTHING HERE ASKS A REAL RESOLVER: the helper
is loaded without the suite's stand-in (load_helper(stream_lookup=None)),
and every test replaces stream_resolve with a Resolver whose answers it
states, or, for the shipping lookup's own path, socket.getaddrinfo with a
double. The shipping functions are called (player_target over caches as the
parse writes them) and the shipping `play` and `player start|restart` verbs
run in process against tests/test_mpv.py's FakeMpv on a scratch socket
under /tmp, never the default socket and never a real player.
"""
import contextlib
import io
import json
import os
import pathlib
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper
# Helpers alone, no test case: nothing of that module runs here.
from test_mpv import FakeMpv, IdentitySeam

helper = load_helper(stream_lookup=None)

# Every name here holds this word, so a refusal that names its host is a
# search for one word.
LEAK = "qqqqqq"
NAME = "svc.qqqqqq.test"
GLOBAL = "93.184.216.34"

# The addresses the finding's attacker would answer with, each refused from a
# playlist that is not local: (address, family).
REFUSED_ANSWERS = [("127.0.0.1", socket.AF_INET), ("::1", socket.AF_INET6), ("::ffff:127.0.0.1", socket.AF_INET6),
                   ("0.0.0.0", socket.AF_INET), ("10.0.0.1", socket.AF_INET), ("192.168.1.10", socket.AF_INET),
                   ("169.254.1.1", socket.AF_INET), ("fe80::1%2", socket.AF_INET6), ("fd00::1", socket.AF_INET6)]


def answer(address, port=80):
    """One getaddrinfo entry for `address`."""
    if ":" in address:
        return (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (address, port, 0, 0))
    return (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))


class Resolver:
    """stream_resolve's stand-in: `answers` maps a name (as the helper asks
    it, str or bytes) to a list of addresses or to an exception to raise;
    a name it was not told about is an AssertionError, which the shipping
    code does not catch, so a lookup a test did not expect is red. Every
    name asked is recorded with its port."""

    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    def __call__(self, name, port):
        self.asked.append((name, port))
        if name not in self.answers:
            raise AssertionError("unexpected lookup of %r" % (name,))
        found = self.answers[name]
        if isinstance(found, BaseException):
            raise found
        return [answer(a, port) for a in found]


def resolving(answers):
    resolver = Resolver(answers)
    # create: a tree before D-SINK-101 (the red-first run) has no seam.
    return resolver, mock.patch.object(helper, "stream_resolve", resolver, create=True)


REMOTE = {"sourceHost": "prov.example.test", "sourceClass": "global", "sourceLocal": False, "sourcePort": 80}
RELAY = {"sourceHost": "127.0.0.1", "sourceClass": "loopback", "sourceLocal": True, "sourcePort": 34400}
LAN = {"sourceHost": "192.168.1.5", "sourceClass": "private", "sourceLocal": True, "sourcePort": 80}
FILE = {"sourceHost": "local file"}


def write_cache(directory, urls, source):
    """channels.json as the parse writes it, one channel per address."""
    rows = [{"id": "e%d" % i, "name": "E%d" % i, "group": "G", "url": url} for i, url in enumerate(urls)]
    document = dict({"version": 1, "channels": rows}, **source)
    path = pathlib.Path(directory)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    (path / "channels.json").write_text(json.dumps(document), encoding="utf-8")
    return [row["id"] for row in rows]


def run(*args):
    """The shipping helper's main(), in process: (exit, last JSON line,
    stdout, stderr)."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(args))
    lines = out.getvalue().strip().splitlines()
    return code, (json.loads(lines[-1]) if lines else None), out.getvalue(), err.getvalue()


class PlayTargetTest(unittest.TestCase):
    """player_target, the play-time gate, over caches as the parse writes them."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.count = 0

    def outcomes(self, source, urls, answers):
        """[(code or "played", message or url, a refusal names the host)]
        and the resolver, for each of `urls` from a playlist `source`."""
        self.count += 1
        directory = os.path.join(self.root, "c%d" % self.count)
        ids = write_cache(directory, urls, source)
        resolver, patch = resolving(answers)
        got = []
        with patch:
            for cid in ids:
                try:
                    target = helper.player_target(cid, "", directory)
                except helper.HelperError as error:
                    got.append((error.code, error.message, LEAK in error.message))
                    continue
                got.append(("played", target["url"]))
        return got, resolver

    def refused(self, count=1):
        return [("local_address", getattr(helper, "STREAM_RESOLVED_REFUSAL", "<none>"), False)] * count

    def test_a_remote_playlists_name_that_resolves_here_or_to_the_lan_is_refused_naming_none(self):
        for address, _ in REFUSED_ANSWERS:
            with self.subTest(address=address):
                got, resolver = self.outcomes(REMOTE, ["http://%s/live/1.ts" % NAME], {NAME: [address]})
                self.assertEqual(got, self.refused())
                self.assertEqual(resolver.asked, [(NAME, 80)])

    def test_a_remote_playlists_name_that_resolves_to_a_global_address_plays(self):
        urls = ["http://%s/live/1.ts" % NAME, "https://%s:8443/live/2.m3u8" % NAME, "rtsp://%s/s" % NAME]
        got, resolver = self.outcomes(REMOTE, urls, {NAME: [GLOBAL, "2606:4700::1111"]})
        self.assertEqual(got, [("played", u) for u in urls])
        self.assertEqual(resolver.asked, [(NAME, 80), (NAME, 8443), (NAME, 554)])

    def test_one_refused_address_among_global_ones_refuses_it_whichever_comes_first(self):
        for answers in ([GLOBAL, "127.0.0.1"], ["::1", GLOBAL], [GLOBAL, "2606:4700::1111", "192.168.1.10"]):
            with self.subTest(answers=answers):
                got, _ = self.outcomes(REMOTE, ["http://%s/live/1.ts" % NAME], {NAME: answers})
                self.assertEqual(got, self.refused())

    def test_a_name_that_cannot_be_looked_up_is_refused_as_unchecked_naming_none(self):
        unchecked = [("unchecked_address", getattr(helper, "STREAM_LOOKUP_REFUSAL", "<none>"), False)]
        for found in (socket.gaierror(socket.EAI_NONAME, "Name or service not known"),
                      socket.gaierror(socket.EAI_AGAIN, "Temporary failure in name resolution"),
                      TimeoutError(110, "the host-name lookup took longer than 3.0 s"),
                      UnicodeError("label too long"),
                      helper.HelperError("bad_url", helper.HOST_NAME_REFUSAL), []):
            with self.subTest(found=repr(found)):
                got, _ = self.outcomes(REMOTE, ["http://%s/live/1.ts" % NAME], {NAME: found})
                self.assertEqual(got, unchecked)

    def test_a_lookup_that_outlives_its_bound_is_refused_through_the_shipping_lookup(self):
        """The shipping stream_resolve and resolve_within, with
        socket.getaddrinfo a double that never answers until released: the
        channel is refused once the bound passes, not when the resolver
        gives up."""
        release = threading.Event()
        self.addCleanup(release.set)
        asked = []

        def getaddrinfo(host, port, *rest, **more):
            asked.append(host)
            release.wait(30)
            raise socket.gaierror(socket.EAI_AGAIN, "released")

        directory = os.path.join(self.root, "slow")
        ids = write_cache(directory, ["http://%s/live/1.ts" % NAME], REMOTE)
        with mock.patch.object(socket, "getaddrinfo", getaddrinfo), \
                mock.patch.object(helper, "STREAM_LOOKUP_TIMEOUT_S", 0.3, create=True):
            started = time.monotonic()
            with self.assertRaises(helper.HelperError) as caught:
                helper.player_target(ids[0], "", directory)
            spent = time.monotonic() - started
        self.assertEqual((caught.exception.code, caught.exception.message),
                         ("unchecked_address", getattr(helper, "STREAM_LOOKUP_REFUSAL", "<none>")))
        self.assertEqual(asked, [NAME])
        self.assertLess(spent, 2.0)
        self.assertGreaterEqual(spent, 0.29)

    def test_the_shipping_lookup_is_resolve_within_under_its_bound(self):
        calls = []
        with mock.patch.object(helper, "resolve_within", lambda h, p, t: calls.append((h, p, t)) or [answer(GLOBAL)]):
            self.assertEqual(helper.stream_resolve(NAME, 80), [answer(GLOBAL)])
        self.assertEqual(calls, [(NAME, 80, helper.STREAM_LOOKUP_TIMEOUT_S)])
        # Under the shell's 8 s watchdog over one `play` (Service.qml,
        # controlTimeoutMs), with the zap's own connect beside it.
        self.assertLessEqual(helper.STREAM_LOOKUP_TIMEOUT_S + helper.DEFAULT_IPC_TIMEOUT, 8.0 - 2.0)

    def test_a_loopback_relays_channels_name_the_lan_and_its_own_port_only(self):
        urls = ["http://%s/live/1.ts" % NAME, "http://%s:34400/live/2.ts" % NAME, "http://%s:631/" % NAME,
                "http://%s:34400/live/3.ts" % NAME]
        answers = {NAME: ["192.168.1.10"]}
        got, _ = self.outcomes(RELAY, urls[:1], answers)
        self.assertEqual(got, [("played", urls[0])])
        got, resolver = self.outcomes(RELAY, urls[1:], {NAME: ["127.0.0.1"]})
        self.assertEqual(got, [("played", urls[1])] + self.refused() + [("played", urls[3])])
        self.assertEqual(resolver.asked, [(NAME, 34400), (NAME, 631), (NAME, 34400)])
        # The unspecified address is this machine too, held to the port.
        got, _ = self.outcomes(RELAY, urls[1:3], {NAME: ["0.0.0.0"]})
        self.assertEqual(got, [("played", urls[1])] + self.refused())

    def test_a_local_file_or_a_lan_playlist_is_never_asked(self):
        urls = ["http://%s/live/1.ts" % NAME, "rtsp://%s/s" % NAME]
        for source in (FILE, LAN):
            with self.subTest(source=source["sourceHost"]):
                got, resolver = self.outcomes(source, urls, {})
                self.assertEqual(got, [("played", u) for u in urls])
                self.assertEqual(resolver.asked, [])

    def test_the_playlists_own_host_name_plays_and_is_not_asked(self):
        own = dict(REMOTE, sourceHost=NAME)
        urls = ["http://%s/live/1.ts" % NAME, "http://%s:8080/live/2.ts" % NAME.upper(), "http://%s./x" % NAME]
        got, resolver = self.outcomes(own, urls, {NAME: ["192.168.1.10"]})
        self.assertEqual(got, [("played", u) for u in urls])
        self.assertEqual(resolver.asked, [])
        # Another name in the same zone is not the playlist's own.
        got, _ = self.outcomes(own, ["http://other.qqqqqq.test/x"], {"other.qqqqqq.test": ["192.168.1.10"]})
        self.assertEqual(got, self.refused())

    def test_multicast_stays_as_it_was(self):
        """udp and rtp take a multicast LITERAL only (D-SINK-42), so a name
        there is refused before any lookup, as it was; a group literal plays
        and is not asked; and a name that answers a group is refused on
        any other scheme, as the group's literal is."""
        urls = ["udp://@%s:5000" % NAME, "rtp://%s:5004" % NAME, "udp://@239.1.1.1:5000", "http://%s/x" % NAME]
        got, resolver = self.outcomes(REMOTE, urls, {NAME: ["239.1.1.1"]})
        self.assertEqual([g[0] for g in got[:2]], ["unsupported_scheme"] * 2)
        self.assertEqual(got[2:], [("played", urls[2])] + self.refused())
        self.assertEqual(resolver.asked, [(NAME, 80)])

    def test_literals_and_typed_addresses_are_never_asked(self):
        got, resolver = self.outcomes(REMOTE, ["http://%s/x" % GLOBAL, "http://[2606:4700::1111]/x", "http://localhost/x"], {})
        self.assertEqual([g[0] for g in got], ["played", "played", "local_address"])
        self.assertEqual(resolver.asked, [])
        resolver, patch = resolving({})
        with patch:
            target = helper.player_target("", "http://%s/live/1.ts" % NAME, self.root)
        self.assertEqual((target["url"], resolver.asked), ("http://%s/live/1.ts" % NAME, []))

    def test_a_name_an_older_rule_refuses_is_never_looked_up(self):
        """The lookup is last, so the names D-SINK-83 and D-SINK-89 keep from
        the resolver stay kept from it."""
        urls = ["http://userqqqqqq/live/1.ts", "http://evil%40qqqqqq.test/x", "http://127.0.0.1:631/"]
        got, resolver = self.outcomes(REMOTE, urls, {})
        self.assertEqual([g[0] for g in got], ["local_address", "unsupported_scheme", "local_address"])
        self.assertEqual(resolver.asked, [])

    def test_the_name_is_asked_as_the_player_asks_it(self):
        """As written after the last `@`, before the port: an ASCII name as
        its text, case kept; a name that is not ASCII as its UTF-8 bytes,
        which resolve_within hands the resolver with no idna codec."""
        upper = "Svc.QQQQQQ.test"
        wide = "Stra" + chr(0xDF) + "e.qqqqqq.test"
        urls = ["rtsp://me:pw@%s:8554/s" % upper, "rtsp://%s/s" % wide]
        got, resolver = self.outcomes(REMOTE, urls, {upper: [GLOBAL], wide.encode("utf-8"): ["127.0.0.1"]})
        self.assertEqual(got, [("played", urls[0])] + self.refused())
        self.assertEqual(resolver.asked, [(upper, 8554), (wide.encode("utf-8"), 554)])

    def test_resolve_within_hands_a_bytes_name_to_the_resolver_as_bytes(self):
        asked = []

        def getaddrinfo(host, port, *rest, **more):
            asked.append(host)
            return [answer(GLOBAL)]

        wide = ("Stra" + chr(0xDF) + "e.qqqqqq.test").encode("utf-8")
        with mock.patch.object(socket, "getaddrinfo", getaddrinfo):
            self.assertEqual(helper.resolve_within(wide, 554, 1.0), [answer(GLOBAL)])
            # And a refused name is refused before the resolver, bytes or not.
            with self.assertRaises(helper.HelperError):
                helper.resolve_within("a;b.qqqqqq.test".encode("utf-8"), 554, 1.0)
        self.assertEqual(asked, [wide])


class PlayerWireTest(IdentitySeam, unittest.TestCase):
    """Rule 15: every verb that hands a channel to the player -- `play` (a
    zap), `player start` (a first play, a channel change that replaces
    another build's player), `player start --keep-pause` (the automatic
    restart on adoption, the shell's re-establish of an adopted player) and
    `player restart` (the health path) -- goes through player_target, and
    none sends a load for a refused name. Against a FakeMpv on a scratch
    socket; the start's spawn is replaced by a connection to it, so no
    player is ever started."""

    def setUp(self):
        # AF_UNIX paths are limited to ~108 bytes: keep the socket under /tmp.
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-test-", dir="/tmp")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.sock = os.path.join(self.dir, "mpv.sock")
        self.cache = os.path.join(self.dir, "cache")
        self.urls = ["http://%s/live/1.ts" % NAME, "http://down.qqqqqq.test/live/2.ts", "http://ok.qqqqqq.test/live/3.ts"]
        self.ids = write_cache(self.cache, self.urls, REMOTE)
        self.server = FakeMpv(self.sock)
        self.addCleanup(self.server.close)
        self.install_identity_seam(helper)
        self.holder = self.identity(self.sock)
        self.resolver, patch = resolving({NAME: ["127.0.0.1"], "ok.qqqqqq.test": [GLOBAL],
                                          "down.qqqqqq.test": socket.gaierror(socket.EAI_NONAME, "no")})
        patch.start()
        self.addCleanup(patch.stop)

    def loads(self):
        return [c[1] for c in self.server.commands if c and c[0] == "loadfile"]

    def outcome(self):
        client = helper.MpvIpc(self.sock, 1.0)
        client.connect()
        return {"spawned": False, "client": client, "pid": self.holder.pid, "vouched": self.holder.pid,
                "replaced": 0, "carry": {}}

    def verb(self, verb, cid, *more):
        if verb == "play":
            return run("play", "--id", cid, "--cache-dir", self.cache, "--socket", self.sock, "--ipc-timeout", "1")
        with mock.patch.object(helper, "adopt_or_spawn", lambda *a, **k: self.outcome()), \
                mock.patch.object(helper, "stop_ladder", lambda *a, **k: None), \
                mock.patch.object(helper, "settle_socket", lambda *a, **k: True), \
                mock.patch.object(helper, "observe_first_load", lambda *a, **k: {"state": "unknown", "reason": ""}):
            return run("player", verb, "--socket", self.sock, "--cache-dir", self.cache, "--id", cid,
                       "--seq", "1", "--ipc-timeout", "1", "--lock-timeout", "1", "--spawn-timeout", "1",
                       "--first-load-timeout", "0.2", *more)

    def test_every_verb_that_loads_a_channel_refuses_the_name_and_loads_the_checked_one(self):
        paths = [("play",), ("start",), ("start", "--keep-pause"), ("restart",)]
        got = []
        for path in paths:
            for cid in self.ids:
                code, reply, out, err = self.verb(path[0], cid, *path[1:])
                got.append((path, cid, code, ((reply or {}).get("error") or {}).get("code"), LEAK in out + err))
        want = []
        for path in paths:
            want += [(path, "e0", helper.EXIT_ERROR, "local_address", False),
                     (path, "e1", helper.EXIT_ERROR, "unchecked_address", False),
                     (path, "e2", helper.EXIT_OK, None, False)]
        self.assertEqual(got, want)
        # Only the checked channel was ever loaded, once per path, and no
        # refused name reached the player in any command.
        self.assertEqual(self.loads(), [self.urls[2]] * len(paths))
        self.assertNotIn(NAME, json.dumps(self.server.commands))
        self.assertNotIn("down.qqqqqq", json.dumps(self.server.commands))
        self.assertEqual(sorted(set(self.resolver.asked)), [("down.qqqqqq.test", 80), ("ok.qqqqqq.test", 80), (NAME, 80)])


if __name__ == "__main__":
    unittest.main()
