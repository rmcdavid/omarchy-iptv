"""D-SINK-87 (the owner, 2026-11-08): a channel stream address whose host is
a name D-SINK-86 refuses is never handed to the player.

D-SINK-86's host_name_refused refuses a host name that holds `@`, `%`, `;`,
`=`, `&`, a second `:` (one port is fine), whitespace or an invisible format
character, and the helper asks it before every connection it opens itself.
A channel's stream address is not one of those: the helper hands it to the
player, which reads the host and looks it up. So the two gates that decide
what reaches the player ask it too:

1. Parse. stream_entry_refusal (called by parse_m3u) refuses such a
   location line, so it never becomes a channel in channels.json, and the
   `playlist` verb counts it with the other refused entries in a sentence
   that names no host and no URL.
2. Play. player_target refuses such an address before anything is sent to
   the player, whether it comes from a cache written before the rule or from
   a typed `play --url`, with `unsupported_scheme` (the shell's channel
   refusal) and one fixed sentence that names no host and no URL.

The host is judged as the PLAYER would read it, and where the helper's
reading and the player's could differ, by every reading, each asked of the
same predicate: the authority's host[:port] as written, after its last `@`
(FFmpeg reads a port as the digits up to the next colon, urlsplit reads no
port at all, so what follows the port is judged too; urlsplit's own host is
inside it, which SubsumptionTest holds); and, for the schemes mpv
percent-escapes before FFmpeg reads them (http, https, mmsh, and mms,
rewritten to mmsh), that host[:port] as mpv escapes it -- a `%` for every
byte outside the unreserved and reserved sets, so a Unicode host name the
helper reads whole reaches the player, on a plain stream's path, as a name
holding `%`.

How this module observes it: the shipping `playlist` verb as a subprocess
on a local playlist FILE (nothing is fetched, nothing is looked up), and
the shipping `play` and `player start|restart` verbs, in process, against
tests/test_mpv.py's FakeMpv on a scratch socket under /tmp, never the
default socket and never a real player: "never handed to the player" means
the FakeMpv recorded no `loadfile` and no command naming the address. A
control channel on the same FakeMpv IS loaded, so the absence is the gate's.
"""
import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.parse
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper
# Helpers alone, no test case: nothing of that module runs here.
from test_mpv import FakeMpv, IdentitySeam

helper = load_helper()

ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER = ROOT / "bin" / "omarchy-iptv"

# Every refused address names `evil` in its host (or, for the one literal,
# its path) and no control does, so a leak of either the host or the URL is
# a search for one word.
LEAK = ("evil", "qqqqqq")

REFUSED = [
    # 1. The host urlsplit reads holds one of them.
    "http://evil.test;sid=qqqqqq/live/1.ts",
    "http://evil.test&p=qqqqqq/live/1.ts",
    "http://evil.test=qqqqqq/live/1.ts",
    "http://h%40evil.test/live/1.ts",
    "http://h" + chr(0x20) + "evil.test/live/1.ts",
    "http://h" + chr(0x3000) + "evil.test/live/1.ts",
    "http://h" + chr(0xAD) + "evil.test/live/1.ts",
    "http://h" + chr(0x200E) + "evil.test/live/1.ts",
    "http://h" + chr(0xFEFF) + "evil.test/live/1.ts",
    "http://h" + chr(0xE0041) + "evil.test/live/1.ts",
    "http://[v1.evil;sid=qqqqqq]/live/1.ts",
    "rtmp://evil.test live=1",
    "rtsp://evil.test;sid=qqqqqq/stream",
    "srt://evil.test%3Bx:9000?mode=caller",
    "mmsh://evil.test=qqqqqq/live/1",
    # 2. Its host[:port] as written holds one past the port, where the
    #    two readers disagree on the port (urlsplit reads none).
    "http://evil.test:80;sid=qqqqqq/live/1.ts",
    "http://evil.test:80:81/live/1.ts",
    "https://evil.test:443&p=qqqqqq/live/1.ts",
    "http://[2001:db8::1]:80:81/evil/1.ts",
    "rtsp://evil.test:554" + chr(0x20) + "1/stream",
    # 3. As mpv escapes an http-like URL before FFmpeg reads it: a `%`.
    "http://evil" + chr(0xFC) + ".test/live/1.ts",
    "https://evil" + chr(0xE9) + ".test/live/1.ts",
    "mms://evil" + chr(0xFC) + ".test/live/1",
    "http://evil" + chr(0x5C) + "x.test/live/1.ts",
    "http://evil|x.test/live/1.ts",
]

CONTROLS = [
    "http://stream.example.test/live/1.ts",
    # The refused characters in the userinfo, the path and the query: the
    # rule is the HOST's, and a password or a token may hold any of them.
    "http://us;er=1&x:p%40ss;w=1@stream.example.test/live/2.ts",
    # Two at-signs: the userinfo ends at the LAST (D-SINK-1).
    "http://me@mail.test:pa%3Bss@stream.example.test/live/7.ts",
    "http://stream.example.test:8080/live/a;b=c&d=e%20f?u=a@b&p=c%40d",
    "https://stream.example.test:443/live/3.ts",
    "http://stream.example.test:/live/4.ts",
    # An IPv6 literal keeps its colons and its zone's `%` (D-SINK-86).
    "http://[fe80::1%25eth0]:8080/live/5.ts",
    "http://xn--bcher-kva.test/live/6.ts",
    # rtsp is not escaped by mpv (its demuxer opens the URL as given), so
    # the one reading is the name, which the predicate allows.
    "rtsp://b" + chr(0xFC) + "cher.test/stream",
    # librtmp-style options after a space belong to the path, not the host.
    "rtmp://stream.example.test/live/stream live=1",
    "udp://@239.1.1.1:1234",
    "srt://stream.example.test:9000?mode=caller&passphrase=a;b=c",
]

PLURAL = "%d entries skipped: stream host names holding characters no host name may hold"
SINGULAR = "1 entry skipped: a stream host name holding a character no host name may hold"


def leaks(text):
    return [word for word in LEAK if word in text]


def playlist_text():
    lines = ["#EXTM3U"]
    for index, url in enumerate(REFUSED):
        lines += ["#EXTINF:-1 tvg-id=\"r%d.test\",R%d" % (index, index),
                  "#KODIPROP:inputstream.adaptive.stream_headers=Authorization=a&Cookie=b", url]
    for index, url in enumerate(CONTROLS):
        lines += ["#EXTINF:-1 tvg-id=\"c%d.test\",C%d" % (index, index), url]
    return "\n".join(lines) + "\n"


def pre_rule_cache(directory):
    """channels.json as a cache written before D-SINK-87 could hold it: every
    refused address a channel, beside one control, from a local file (so the
    LAN rule, D-SINK-41, refuses none of them on its own)."""
    rows = [{"id": "r%d" % i, "name": "R%d" % i, "group": "G", "url": url,
             "headers": {"Authorization": "a"}} for i, url in enumerate(REFUSED)]
    rows.append({"id": "c0", "name": "C0", "group": "G", "url": CONTROLS[0]})
    path = pathlib.Path(directory)
    path.mkdir(mode=0o700, exist_ok=True)
    (path / "channels.json").write_text(json.dumps({"version": 1, "sourceHost": "local file", "channels": rows}),
                                        encoding="utf-8")
    return [row["id"] for row in rows[:-1]]


def run(*args):
    """The shipping helper's main(), in process: (exit, last JSON line,
    stdout, stderr)."""
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(args))
    lines = out.getvalue().strip().splitlines()
    return code, (json.loads(lines[-1]) if lines else None), out.getvalue(), err.getvalue()


class ReadingsTest(unittest.TestCase):
    """stream_host_name_refused, the play-time gate's one question, over
    every vector: each refused address by at least one reading, no control
    by any."""

    def test_every_refused_address_is_refused_and_no_control_is(self):
        predicate = getattr(helper, "stream_host_name_refused", lambda url: "<missing>")
        self.assertEqual([(ascii(u), predicate(u)) for u in REFUSED + CONTROLS],
                         [(ascii(u), True) for u in REFUSED] + [(ascii(u), False) for u in CONTROLS])

    def test_each_refused_address_was_a_stream_url_before(self):
        """The vectors are not refused by an older rule: every one passes
        is_stream_url, so the refusal above is this rule's."""
        self.assertEqual([ascii(u) for u in REFUSED + CONTROLS if not helper.is_stream_url(u)], [])


class SubsumptionTest(unittest.TestCase):
    """The gate judges the authority's host[:port] as written and not
    urlsplit's hostname separately, because the first holds the second: the
    hostname is that text up to its port (or a bracket's content),
    lower-cased. These hold the two halves of that claim, so the reading the
    gate leaves out is one it cannot need."""

    def test_lower_casing_changes_no_code_points_verdict(self):
        predicate = getattr(helper, "host_name_refused")
        wrong = [hex(c) for c in range(0x110000) if not 0xD800 <= c <= 0xDFFF
                 and predicate("h%s.test" % chr(c)) != predicate(("h%s.test" % chr(c)).lower())]
        self.assertEqual(wrong[:8], [])

    def test_every_vector_urlsplit_refuses_the_gate_refuses(self):
        gate = getattr(helper, "stream_host_name_refused", lambda url: "<missing>")
        missed = [ascii(u) for u in REFUSED + CONTROLS
                  if helper.host_name_refused(urllib.parse.urlsplit(u).hostname or "") and gate(u) is not True]
        self.assertEqual(missed, [])


class ParseTest(unittest.TestCase):
    """The `playlist` verb, run as the service runs it, over a local file."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)
        self.cache = self.dir / "cache"
        self.list = self.dir / "list.m3u"
        self.list.write_text(playlist_text(), encoding="utf-8")

    def playlist(self):
        env = {k: v for k, v in os.environ.items()
               if k.lower() not in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")
               and not k.startswith("OMARCHY_IPTV_")}
        done = subprocess.run([sys.executable, str(HELPER), "playlist", "--url", str(self.list),
                               "--cache-dir", str(self.cache)], capture_output=True, text=True, env=env, timeout=60)
        lines = [l for l in done.stdout.strip().splitlines() if l.strip()]
        return done.returncode, (json.loads(lines[-1]) if lines else None), done.stdout, done.stderr

    def test_no_refused_address_becomes_a_channel_and_each_is_counted(self):
        code, reply, stdout, stderr = self.playlist()
        self.assertEqual(code, 0, stderr)
        document = json.loads((self.cache / "channels.json").read_text(encoding="utf-8"))
        self.assertEqual([ascii(c["url"]) for c in document["channels"]], [ascii(u) for u in CONTROLS])
        self.assertIn(PLURAL % len(REFUSED), reply.get("warnings") or [], reply)

    def test_nothing_the_verb_writes_or_prints_names_a_refused_host_or_address(self):
        code, _, stdout, stderr = self.playlist()
        self.assertEqual(code, 0, stderr)
        written = {path.name: path.read_text(encoding="utf-8", errors="replace")
                   for path in sorted(self.cache.rglob("*")) if path.is_file()}
        self.assertIn("channels.json", written)
        self.assertEqual({name: leaks(text) for name, text in dict(written, stdout=stdout, stderr=stderr).items()
                          if leaks(text)}, {})

    def test_one_refused_entry_is_counted_in_the_singular(self):
        result = helper.parse_m3u("#EXTM3U\n#EXTINF:-1,R\n%s\n#EXTINF:-1,C\n%s\n" % (REFUSED[0], CONTROLS[0]),
                                  {"host": "", "local": True})
        self.assertEqual(([c["name"] for c in result["channels"]], result["warnings"]), (["C"], [SINGULAR]))


class PlayTargetTest(unittest.TestCase):
    """player_target, the play-time gate, over a cache written before the
    rule and over a typed `--url`."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cache = os.path.join(tmp.name, "cache")
        self.ids = pre_rule_cache(self.cache)

    def outcome(self, channel_id, url):
        try:
            target = helper.player_target(channel_id, url, self.cache)
        except helper.HelperError as error:
            return error.code, leaks(error.message)
        return "played", target["url"]

    def test_a_cached_refused_address_is_refused_naming_no_host(self):
        self.assertEqual([self.outcome(cid, "") for cid in self.ids],
                         [("unsupported_scheme", [])] * len(REFUSED))
        self.assertEqual(self.outcome("c0", ""), ("played", CONTROLS[0]))

    def test_a_typed_refused_address_is_refused_naming_no_host(self):
        self.assertEqual([self.outcome("", url) for url in REFUSED], [("unsupported_scheme", [])] * len(REFUSED))
        self.assertEqual([self.outcome("", url) for url in CONTROLS], [("played", url) for url in CONTROLS])


class PlayerWireTest(IdentitySeam, unittest.TestCase):
    """The address never reaches the player's command: `play` (a cached id
    and a typed `--url`), and `player start` and `player restart` (a cached
    id, the shell's only form of either), against a FakeMpv on a scratch
    socket. The start's spawn is replaced by a connection to that FakeMpv,
    so no player is ever started, whatever the tree under test does."""

    def setUp(self):
        # AF_UNIX paths are limited to ~108 bytes: keep the socket under /tmp.
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-test-", dir="/tmp")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.sock = os.path.join(self.dir, "mpv.sock")
        self.cache = os.path.join(self.dir, "cache")
        self.ids = pre_rule_cache(self.cache)
        self.server = FakeMpv(self.sock)
        self.addCleanup(self.server.close)
        self.install_identity_seam(helper)
        self.holder = self.identity(self.sock)

    def loads(self):
        return [c[1] for c in self.server.commands if c and c[0] == "loadfile"]

    def assert_never_sent(self, replies):
        """Every reply a refusal naming no host, and nothing of any refused
        address on the player's wire."""
        self.assertEqual([(r[0], ((r[1] or {}).get("error") or {}).get("code"), leaks(r[2] + r[3])) for r in replies],
                         [(helper.EXIT_ERROR, "unsupported_scheme", [])] * len(replies))
        self.assertEqual([ascii(u) for u in self.loads()], [])
        self.assertEqual(leaks(json.dumps(self.server.commands)), [])

    def play(self, *target):
        return run("play", *target, "--cache-dir", self.cache, "--socket", self.sock, "--ipc-timeout", "1")

    def test_play_hands_the_player_no_refused_address(self):
        replies = [self.play("--id", cid) for cid in self.ids] + [self.play("--url", url) for url in REFUSED]
        self.assert_never_sent(replies)
        # The FakeMpv and the identity seam are live: the control is loaded.
        code, reply, _, stderr = self.play("--id", "c0")
        self.assertEqual((code, self.loads()), (helper.EXIT_OK, [CONTROLS[0]]), stderr)

    def outcome(self):
        """adopt_or_spawn's reply for the player this test vouches for: the
        FakeMpv, connected, never a spawn."""
        client = helper.MpvIpc(self.sock, 1.0)
        client.connect()
        return {"spawned": False, "client": client, "pid": self.holder.pid, "vouched": self.holder.pid,
                "replaced": 0, "carry": {}}

    def start(self, verb, cid):
        with mock.patch.object(helper, "adopt_or_spawn", lambda *a, **k: self.outcome()), \
                mock.patch.object(helper, "stop_ladder", lambda *a, **k: None), \
                mock.patch.object(helper, "settle_socket", lambda *a, **k: True), \
                mock.patch.object(helper, "observe_first_load", lambda *a, **k: {"state": "unknown", "reason": ""}):
            return run("player", verb, "--socket", self.sock, "--cache-dir", self.cache, "--id", cid,
                       "--seq", "1", "--ipc-timeout", "1", "--lock-timeout", "1", "--spawn-timeout", "1",
                       "--first-load-timeout", "0.2")

    def test_a_start_or_a_restart_with_a_channel_hands_the_player_no_refused_address(self):
        replies = [self.start(verb, cid) for verb in ("start", "restart") for cid in self.ids]
        self.assert_never_sent(replies)
        code, reply, _, stderr = self.start("start", "c0")
        self.assertEqual((code, self.loads()), (helper.EXIT_OK, [CONTROLS[0]]), stderr)


if __name__ == "__main__":
    unittest.main()
