"""D-SINK-89 and D-SINK-91 (2026-11-09): two hosts a channel's address can
make the player look up that no older rule judged.

D-SINK-89 (the owner, 2026-11-08: "yes, refuse one-word stream hosts from
remote playlists too"). D-SINK-83 refuses, before any lookup, a host of ONE
DNS label that the provider chose for a guide hint or a logo, because the
host a URL's space cut leaves is the username of `http://USER:...`. A
channel's stream address is the same provider's choice, and the player
looks its host up. So from a playlist that is NOT local (a file, or an
http(s) source whose last hop connected to a non-global address, is local)
a channel is refused when the host its address names is one label by
dotless_host: the authority's, and, for udp and rtp, every entry of every
reading of a `sources` or `block` value (the names FFmpeg resolves, the
D-SINK-87 suite's reading 3). The playlist's own host is excepted, compared
as DestinationPolicy.refuses_name compares it (host_key, no port). A local
playlist keeps one-label names. Refused at the parse (`label`, counted in a
sentence that names no host) and at play time for a CACHED channel
(`local_address`, the code the shell routes as a channel refused for where
its playlist sent it, with one fixed sentence naming no host); never for a
typed `--url`, which has no playlist.

D-SINK-91. FFmpeg n9.0.2 never percent-decodes a URL's host, and every
stream protocol but udp and srt hands it to the one beneath through
ff_url_join, which brackets it only when getaddrinfo reads it numerically.
A zone that is not digits (`%25eth0` is the zone `25eth0` to it) is no
number, so `rtp://[ff02::1%25eth0]:5004` reaches udp unbracketed and
av_url_split cuts it at its first colon: a lookup of the name `ff02`; nor
are digits past 4294967295, which glibc's strtoull reading refuses (the
review of bf47cdc). So an IPv6 literal whose zone, as the address writes
it, is not ASCII digits of a value at most 4294967295 is refused on every
stream scheme, from any playlist and when typed: `zone` at
the parse, `unsupported_scheme` at play time with its own fixed sentence.

How this module observes it: the shipping functions called
(stream_entry_refusal, player_target), the shipping `playlist` verb in
process on a playlist served from 127.0.0.1 under the one test seam that
reads that address as public (helper_loader.loopback_reads_public), and on
a local FILE, and the shipping `play` and `player start|restart` verbs in
process against tests/test_mpv.py's FakeMpv on a scratch socket under /tmp,
never the default socket and never a real player. Nothing is looked up:
every refused address is refused before any connection, and the controls
are never fetched.
"""
import contextlib
import http.server
import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helper_loader import load_helper, loopback_reads_public
# Helpers alone, no test case: nothing of that module runs here.
from test_mpv import FakeMpv, IdentitySeam

helper = load_helper()

# Every one-label host here holds this word, so a leak of a refused host is
# a search for one word.
LEAK = "qqqqqq"

# From a playlist that is not local, each names a host of one label.
LABEL_REFUSED = [
    "http://userqqqqqq/live/1.ts",
    "http://userqqqqqq:8080/live/2.ts",
    # Upper case and one trailing dot: still one label.
    "https://USERqqqqqq./live/3.ts",
    # The userinfo is not the host; the host after it is one label.
    "http://me:pw@userqqqqqq/live/4.ts",
    "rtsp://userqqqqqq/stream",
    "rtmp://userqqqqqq/live/1",
    "srt://userqqqqqq:9000?mode=caller",
    "mms://userqqqqqq/live/1",
    "mmsh://userqqqqqq/live/1",
    # An IPv4 address written as one number is one label to dotless_host,
    # as it is for a hint or a logo (the cost the row states).
    "http://16843009/live/5.ts",
    # The names a udp or rtp query hands the resolver: an entry, a second
    # entry after av_get_token's trimmed space, one trailing dot, a name
    # FFmpeg reads up to its NUL, a name read case-folded and an escaped
    # entry, and both of rtp's readings.
    "udp://@239.1.1.1:5000?sources=userqqqqqq",
    "udp://@239.1.1.1:5000?sources=10.0.0.1,+userqqqqqq",
    "udp://@239.1.1.1:5000?block=userqqqqqq.",
    # av_get_token trims the space after the dot, which leaves one label.
    "udp://@239.1.1.1:5000?block=userqqqqqq.+",
    "udp://@239.1.1.1:5000?sources%00=userqqqqqq",
    "udp://@239.1.1.1:5000?SOURCES=user%71qqqqq",
    "udp://@239.1.1.1:5000?sources=fe80::1%2Cuserqqqqqq",
    "rtp://239.1.1.1:5004?sources=userqqqqqq",
    "rtp://239.1.1.1:5004?block=10.0.0.1,userqqqqqq",
    # Only rtp's second reading holds it: the first is one IPv6 literal
    # whose zone is `2Cuserqqqqqq`, the second `fe80::1,userqqqqqq`.
    "rtp://239.1.1.1:5004?sources=fe80::1%252Cuserqqqqqq",
    # Only a later pair's second reading holds it, and that pair's first
    # reading is the earlier pair's second: decoding goes on past a reading
    # already read, under one name or across both.
    "rtp://239.1.1.1:5004?sources=fe80::1%25252Cuserqqqqqq&sources=fe80::1%252Cuserqqqqqq",
    "rtp://239.1.1.1:5004?block=fe80::1%25252Cuserqqqqqq&sources=fe80::1%252Cuserqqqqqq",
    # A value repeated before the pair that holds it: the walk skips the
    # repeat and goes on (the review of bf47cdc: a `break` there passed).
    "udp://@239.1.1.1:5000?sources=a.example.test&sources=a.example.test&sources=userqqqqqq",
    # An ENTRY already asked before the one-label one, in an earlier pair or
    # earlier in the same reading: the walk passes over it and goes on (the
    # review of cce5548: a `break` at that skip passed every suite, and what
    # it let through moved with the hash seed while the entries were walked
    # as a set).
    "udp://@239.1.1.1:5000?sources=a.example.test&block=a.example.test,userqqqqqq",
    "udp://@239.1.1.1:5000?sources=a.example.test,+a.example.test,userqqqqqq",
    "rtp://239.1.1.1:5004?block=10.0.0.1&sources=10.0.0.1,userqqqqqq",
]

# From the same playlist, none does.
LABEL_CONTROLS = [
    "http://stream.example.test/live/1.ts",
    "https://stream.example.test./live/2.ts",
    "http://8.8.8.8/live/3.ts",
    "http://[2001:4860::8888]/live/4.ts",
    "udp://@239.1.1.1:5000",
    "udp://@239.1.1.1:5000?sources=192.0.2.1,198.51.100.2",
    "udp://@239.1.1.1:5000?sources=fe80::1",
    "rtp://239.1.1.1:5004?block=a.example.test,+b.example.test",
    "rtp://239.1.1.1:5004?sources=fe80::1%252Cb.example.test",
]

# The playlist's own host, one label itself, at another port and spelled
# another way: excepted, as refuses_name excepts it.
OWN = ["http://provider:8080/live/1.ts", "http://PROVIDER./live/2.ts", "udp://@239.1.1.1:5000?sources=provider",
       "rtp://239.1.1.1:5004?block=10.0.0.1,Provider"]

# Each an IPv6 literal whose zone, as written, is not a number.
ZONE_REFUSED = [
    "rtp://[ff02::1%25eth0]:5004",
    "rtp://[ff02::1%eth0]:5004",
    "rtp://[::ffff:239.1.1.1%25eth0]:5004",
    "http://[2606:4700::1%25eth0]/live/1.ts",
    "http://[2a00:1450::1%25eth0]:8080/live/2.ts",
    "https://[fe80::1%25qqqqqq]/live/3.ts",
    "http://me:pw@[fe80::1%251a]:8080/live/4.ts",
    "rtsp://[fe80::1%25eth0]/stream",
    "rtmp://[fe80::1%25eth0]/live/1",
    "mms://[fe80::1%25eth0]/live/1",
    "mmsh://[fe80::1%25eth0]/live/1",
    "udp://@[ff02::1%25eth0]:5004",
    "srt://[fe80::1%25eth0]:9000?mode=caller",
    # Digits past 4294967295 are no number to glibc either (strtoull, then
    # `number <= UINT32_MAX`), so FFmpeg cuts them as it cuts `%25eth0`: the
    # zone as written, `%25` and all (the review of bf47cdc). From a public
    # list too, for a multicast group or a global literal.
    "rtp://[ff02::1%254294967296]:5004",
    "rtp://[ff02::1%4294967296]:5004",
    "http://[2a00:1450::1%2599999999999]/live/5.ts",
    "rtp://[::ffff:239.1.1.1%2599999999999]:5004",
    "https://[2606:4700::1%254294967296]/live/6.ts",
    # The host follows the userinfo's LAST `@`, as av_url_split and urlsplit
    # read it (D-SINK-1), whatever the userinfo holds.
    "http://a@b@[fe80::1%25eth0]/live/7.ts",
    "http://a@b@[2606:4700::1%25eth0]/live/8.ts",
    "rtp://u@v@[ff02::1%25eth0]:5004",
]

# A literal with no zone, or a zone of digits glibc reads as a number, and
# IPv4 multicast.
ZONE_CONTROLS = [
    "rtp://[ff02::1]:5004",
    "rtp://239.1.1.1:5004",
    "udp://@[ff15::1]:1234",
    "rtp://[ff02::1%251]:5004",
    "http://[fe80::1%252]:8080/live/1.ts",
    "rtsp://me:pw@[fe80::1%2512]/stream",
    # The largest zone glibc reads as a number, and one under it that `%25`
    # begins.
    "rtp://[ff02::1%4294967295]:5004",
    "rtp://[ff02::1%254294967]:5004",
]

LABEL_PLURAL = ("%d entries skipped: their addresses name hosts of one label, not the playlist's own, from a playlist "
                "that is not on this machine or a local network")
LABEL_SINGULAR = ("1 entry skipped: its address names a host of one label, not the playlist's own, from a playlist "
                  "that is not on this machine or a local network")
ZONE_PLURAL = "%d entries skipped: their addresses are IPv6 literals whose zones are not numbers"
ZONE_SINGULAR = "1 entry skipped: its address is an IPv6 literal whose zone is not a number"


def remote(host="prov.example.test"):
    """playlist_source of an http playlist whose last hop connected to a
    global address: not local."""
    return helper.playlist_source("url", "http://%s/list.m3u" % host, "global")


def local_sources():
    """A file, a LAN literal's http playlist, and a named one whose last hop
    connected to a private address: each local."""
    return {"file": helper.playlist_source("file", "/srv/tv/list.m3u"),
            "lan": helper.playlist_source("url", "http://192.168.1.5:9981/list.m3u", "private"),
            "named lan": helper.playlist_source("url", "http://tvheadend:9981/list.m3u", "private")}


def entries(urls):
    lines = ["#EXTM3U"]
    for index, url in enumerate(urls):
        lines += ["#EXTINF:-1 tvg-id=\"e%d.test\",E%d" % (index, index), url]
    return "\n".join(lines) + "\n"


def write_cache(directory, urls, local, host="prov.example.test"):
    """channels.json as the parse would have written it before the rule:
    every address a channel, from a public playlist on `host` or, `local`,
    from a local file."""
    rows = [{"id": "e%d" % i, "name": "E%d" % i, "group": "G", "url": url} for i, url in enumerate(urls)]
    document = {"version": 1, "channels": rows}
    if local:
        document["sourceHost"] = "local file"
    else:
        document.update({"sourceHost": host, "sourceClass": "global", "sourceLocal": False,
                         "sourcePort": 80})
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


class LabelGateTest(unittest.TestCase):
    """stream_entry_refusal, the parse's one question of a location line."""

    def test_vectors_pass_every_older_rule(self):
        """Each vector is a stream URL that names no host D-SINK-87 refuses,
        so a refusal below is this rule's."""
        older = [ascii(u) for u in LABEL_REFUSED + LABEL_CONTROLS + OWN
                 if not helper.is_stream_url(u) or helper.stream_host_name_refused(u)]
        self.assertEqual(older, [])

    def test_a_remote_playlists_one_label_hosts_are_refused_and_its_others_kept(self):
        got = [(ascii(u), helper.stream_entry_refusal(u, remote())[0]) for u in LABEL_REFUSED + LABEL_CONTROLS]
        self.assertEqual(got, [(ascii(u), "label") for u in LABEL_REFUSED] + [(ascii(u), "") for u in LABEL_CONTROLS])

    def test_a_local_playlist_keeps_them(self):
        got = [(name, ascii(u), helper.stream_entry_refusal(u, source)[0])
               for name, source in local_sources().items() for u in LABEL_REFUSED]
        self.assertEqual(got, [(name, ascii(u), "") for name in local_sources() for u in LABEL_REFUSED])

    def test_the_playlists_own_host_is_excepted_without_its_port(self):
        own = remote("provider")
        self.assertEqual((own["host"], own["local"]), ("provider", False))
        got = [(ascii(u), helper.stream_entry_refusal(u, own)[0]) for u in OWN + LABEL_REFUSED[:1]]
        self.assertEqual(got, [(ascii(u), "") for u in OWN] + [(ascii(LABEL_REFUSED[0]), "label")])

    def test_a_parse_with_no_source_reads_it_as_public(self):
        """parse_m3u without a source fails closed (D-SINK-41's rule): one
        label is refused there too."""
        result = helper.parse_m3u(entries(LABEL_REFUSED[:1] + LABEL_CONTROLS[:1]))
        self.assertEqual(([c["url"] for c in result["channels"]], result["warnings"]),
                         ([LABEL_CONTROLS[0]], [LABEL_SINGULAR]))


class LabelParseTest(unittest.TestCase):
    """The `playlist` verb, in process, on a playlist served from 127.0.0.1
    under the seam that reads that one address as public."""

    def serve(self, body):
        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return "http://127.0.0.1:%d/list.m3u" % server.server_address[1]

    def playlist(self, urls):
        url = self.serve(entries(urls).encode("utf-8"))
        cache = tempfile.mkdtemp(prefix="omarchy-iptv-label-")
        self.addCleanup(shutil.rmtree, cache, True)
        environment = {k: v for k, v in os.environ.items() if not k.startswith("OMARCHY_IPTV_")
                       and k.lower() not in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")}
        environment.update({helper.URL_ENV: url, helper.ORIGIN_ENV: "user"})
        with loopback_reads_public(helper), mock.patch.dict(os.environ, environment, clear=True):
            result = run("playlist", "--cache-dir", cache)
        document = json.loads((pathlib.Path(cache) / "channels.json").read_text(encoding="utf-8"))
        written = "".join(path.read_text(encoding="utf-8", errors="replace")
                          for path in sorted(pathlib.Path(cache).rglob("*")) if path.is_file())
        return result, document, written

    def test_no_one_label_host_becomes_a_channel_and_each_is_counted_naming_none(self):
        (code, reply, stdout, stderr), document, written = self.playlist(LABEL_REFUSED + LABEL_CONTROLS)
        self.assertEqual(code, 0, stderr)
        self.assertEqual((document.get("sourceClass"), document.get("sourceLocal")), ("global", False))
        self.assertEqual([ascii(c["url"]) for c in document["channels"]], [ascii(u) for u in LABEL_CONTROLS])
        self.assertIn(LABEL_PLURAL % len(LABEL_REFUSED), reply.get("warnings") or [], reply)
        self.assertEqual([where for where, text in (("stdout", stdout), ("stderr", stderr), ("cache", written))
                          if LEAK in text], [])

    def test_a_local_file_keeps_every_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = pathlib.Path(tmp) / "list.m3u"
            source.write_text(entries(LABEL_REFUSED), encoding="utf-8")
            cache = pathlib.Path(tmp) / "cache"
            code, reply, _, stderr = run("playlist", "--url", str(source), "--cache-dir", str(cache))
            document = json.loads((cache / "channels.json").read_text(encoding="utf-8"))
        self.assertEqual(code, 0, stderr)
        self.assertEqual([ascii(c["url"]) for c in document["channels"]], [ascii(u) for u in LABEL_REFUSED])


class ZoneGateTest(unittest.TestCase):
    """stream_zone_refused and the parse's `zone` reason."""

    def test_vectors_pass_every_older_rule(self):
        older = [ascii(u) for u in ZONE_REFUSED + ZONE_CONTROLS
                 if not helper.is_stream_url(u) or helper.stream_host_name_refused(u)]
        self.assertEqual(older, [])

    def test_a_zone_that_is_not_a_number_is_refused_from_any_playlist(self):
        sources = dict(local_sources(), remote=remote())
        got = [(name, ascii(u), helper.stream_entry_refusal(u, source)[0]) for name, source in sources.items()
               for u in ZONE_REFUSED + ZONE_CONTROLS]
        want = []
        for name, source in sources.items():
            for u in ZONE_REFUSED:
                # From a public list a link-local or other non-global literal
                # is D-SINK-41's `local` first, which is asked before.
                older = helper.stream_host_refused(u, source)
                want.append((name, ascii(u), "local" if older else "zone"))
            for u in ZONE_CONTROLS:
                want.append((name, ascii(u), "local" if helper.stream_host_refused(u, source) else ""))
        self.assertEqual(got, want)
        # The rule itself, not only `local`, answers from the public list.
        self.assertGreaterEqual(sum(1 for name, _, why in got if name == "remote" and why == "zone"), 5)

    def test_the_netloc_text(self):
        refused = getattr(helper, "stream_zone_refused", lambda netloc: "<missing>")
        texts = [("[ff02::1%25eth0]:5004", True), ("[ff02::1%eth0]", True), ("u:p@[fe80::1%25a]:80", True),
                 ("[fe80::1%251" + chr(0x663) + "]", True), ("[ff02::1%251]:5004", False), ("[ff02::1]:5004", False),
                 ("@239.1.1.1:5000", False), ("h.test:80", False), ("u%25x@[::1]:80", False), ("", False),
                 # The last `@` ends the userinfo, as FFmpeg reads it.
                 ("a@b@[fe80::1%25eth0]:80", True), ("a@[::1]@[fe80::1%25eth0]", True),
                 # glibc's bound: a value of at most 4294967295, leading
                 # zeros allowed, whatever the zone's length (int() refuses
                 # more than 4,300 digits, and a typed `--url` has no bound).
                 ("[ff02::1%4294967295]", False), ("[ff02::1%4294967296]", True), ("[ff02::1%254294967295]", True),
                 ("[ff02::1%00000000000000000001]:5004", False), ("[ff02::1%" + "0" * 5000 + "1]", False),
                 ("[ff02::1%" + "9" * 5000 + "]", True), ("[ff02::1%0]", False), ("[ff02::1%]", True)]
        self.assertEqual([(t, refused(t)) for t, _ in texts], texts)

    def test_parse_counts_them_naming_none(self):
        result = helper.parse_m3u(entries(ZONE_REFUSED + ZONE_CONTROLS), local_sources()["file"])
        self.assertEqual([c["url"] for c in result["channels"]], ZONE_CONTROLS)
        self.assertEqual(result["warnings"], [ZONE_PLURAL % len(ZONE_REFUSED)])
        one = helper.parse_m3u(entries(ZONE_REFUSED[:1]), local_sources()["file"])
        self.assertEqual(one["warnings"], [ZONE_SINGULAR])


class PlayTargetTest(unittest.TestCase):
    """player_target, the play-time gate."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name

    def outcome(self, directory, channel_id, url=""):
        try:
            target = helper.player_target(channel_id, url, directory)
        except helper.HelperError as error:
            return error.code, error.message, LEAK in error.message
        return "played", target["url"]

    def test_a_cached_one_label_host_from_a_public_list_is_refused_naming_none(self):
        directory = os.path.join(self.root, "public")
        ids = write_cache(directory, LABEL_REFUSED + LABEL_CONTROLS, local=False)
        sentence = getattr(helper, "STREAM_LABEL_REFUSAL", "<no STREAM_LABEL_REFUSAL>")
        got = [self.outcome(directory, cid) for cid in ids]
        self.assertEqual(got, [("local_address", sentence, False)] * len(LABEL_REFUSED)
                         + [("played", u) for u in LABEL_CONTROLS])

    def test_the_playlists_own_one_label_host_plays_from_the_cache(self):
        """The own-host exception at play time, as at the parse: a cache
        from a public playlist on the one-label host `provider` plays its
        own host's channels, at another port and spelled another way, and
        still refuses another one-label host (the review of bf47cdc: the
        exception dropped at play passed every suite)."""
        directory = os.path.join(self.root, "own")
        other = ["http://other:8080/live/1.ts", "udp://@239.1.1.1:5000?sources=other"]
        ids = write_cache(directory, OWN + other, local=False, host="provider")
        sentence = getattr(helper, "STREAM_LABEL_REFUSAL", "<no STREAM_LABEL_REFUSAL>")
        self.assertEqual([self.outcome(directory, cid) for cid in ids],
                         [("played", u) for u in OWN] + [("local_address", sentence, False)] * len(other))

    def test_a_cache_from_before_the_destination_rules_reads_as_public(self):
        """A cache recording no class and no locality, on a named host,
        reads as public (cached_source's stricter reading)."""
        directory = os.path.join(self.root, "old")
        ids = write_cache(directory, LABEL_REFUSED[:1], local=False)
        path = pathlib.Path(directory) / "channels.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        for key in ("sourceClass", "sourceLocal", "sourcePort"):
            del document[key]
        path.write_text(json.dumps(document), encoding="utf-8")
        self.assertEqual(self.outcome(directory, ids[0])[0], "local_address")

    def test_a_cached_one_label_host_from_a_local_file_plays(self):
        directory = os.path.join(self.root, "file")
        ids = write_cache(directory, LABEL_REFUSED, local=True)
        self.assertEqual([self.outcome(directory, cid) for cid in ids], [("played", u) for u in LABEL_REFUSED])

    def test_a_typed_one_label_host_plays(self):
        """A `--url` has no playlist: the rule is never asked of it."""
        self.assertEqual([self.outcome(self.root, "", u) for u in LABEL_REFUSED], [("played", u) for u in LABEL_REFUSED])

    def test_a_zone_that_is_not_a_number_is_refused_cached_or_typed(self):
        directory = os.path.join(self.root, "zone")
        ids = write_cache(directory, ZONE_REFUSED + ZONE_CONTROLS, local=True)
        sentence = getattr(helper, "STREAM_ZONE_REFUSAL", "<no STREAM_ZONE_REFUSAL>")
        refused = [("unsupported_scheme", sentence, False)] * len(ZONE_REFUSED)
        self.assertEqual([self.outcome(directory, cid) for cid in ids], refused + [("played", u) for u in ZONE_CONTROLS])
        self.assertEqual([self.outcome(self.root, "", u) for u in ZONE_REFUSED + ZONE_CONTROLS],
                         refused + [("played", u) for u in ZONE_CONTROLS])
        # A typed zone longer than int() reads is refused, not `internal`.
        self.assertEqual(self.outcome(self.root, "", "rtp://[ff02::1%25" + "9" * 5000 + "]:5004"), refused[0])


class PlayerWireTest(IdentitySeam, unittest.TestCase):
    """Nothing refused reaches the player's command: `play` (a cached id, and
    a typed `--url` for the zones), and `player start` and `player restart`
    (a cached id), against a FakeMpv on a scratch socket. The start's spawn
    is replaced by a connection to that FakeMpv, so no player is ever
    started."""

    def setUp(self):
        # AF_UNIX paths are limited to ~108 bytes: keep the socket under /tmp.
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-test-", dir="/tmp")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.sock = os.path.join(self.dir, "mpv.sock")
        self.public = os.path.join(self.dir, "public")
        self.label_ids = write_cache(self.public, LABEL_REFUSED + LABEL_CONTROLS[:1], local=False)
        self.file = os.path.join(self.dir, "file")
        self.zone_ids = write_cache(self.file, ZONE_REFUSED + ZONE_CONTROLS[:1], local=True)
        self.server = FakeMpv(self.sock)
        self.addCleanup(self.server.close)
        self.install_identity_seam(helper)
        self.holder = self.identity(self.sock)

    def loads(self):
        return [c[1] for c in self.server.commands if c and c[0] == "loadfile"]

    def codes(self, replies):
        return [(r[0], ((r[1] or {}).get("error") or {}).get("code"), LEAK in r[2] + r[3]) for r in replies]

    def play(self, cache, *target):
        return run("play", *target, "--cache-dir", cache, "--socket", self.sock, "--ipc-timeout", "1")

    def outcome(self):
        client = helper.MpvIpc(self.sock, 1.0)
        client.connect()
        return {"spawned": False, "client": client, "pid": self.holder.pid, "vouched": self.holder.pid,
                "replaced": 0, "carry": {}}

    def start(self, verb, cache, cid):
        with mock.patch.object(helper, "adopt_or_spawn", lambda *a, **k: self.outcome()), \
                mock.patch.object(helper, "stop_ladder", lambda *a, **k: None), \
                mock.patch.object(helper, "settle_socket", lambda *a, **k: True), \
                mock.patch.object(helper, "observe_first_load", lambda *a, **k: {"state": "unknown", "reason": ""}):
            return run("player", verb, "--socket", self.sock, "--cache-dir", cache, "--id", cid,
                       "--seq", "1", "--ipc-timeout", "1", "--lock-timeout", "1", "--spawn-timeout", "1",
                       "--first-load-timeout", "0.2")

    def test_play_start_and_restart_hand_the_player_none_of_them(self):
        label = [self.play(self.public, "--id", cid) for cid in self.label_ids[:-1]]
        label += [self.start(verb, self.public, cid) for verb in ("start", "restart") for cid in self.label_ids[:-1]]
        zone = [self.play(self.file, "--id", cid) for cid in self.zone_ids[:-1]]
        zone += [self.play(self.file, "--url", url) for url in ZONE_REFUSED]
        zone += [self.start(verb, self.file, cid) for verb in ("start", "restart") for cid in self.zone_ids[:-1]]
        self.assertEqual(self.codes(label), [(helper.EXIT_ERROR, "local_address", False)] * len(label))
        self.assertEqual(self.codes(zone), [(helper.EXIT_ERROR, "unsupported_scheme", False)] * len(zone))
        self.assertEqual(self.loads(), [])
        self.assertNotIn(LEAK, json.dumps(self.server.commands))
        # The FakeMpv and the identity seam are live: each cache's control is
        # loaded.
        code, _, _, stderr = self.play(self.public, "--id", self.label_ids[-1])
        self.assertEqual(code, helper.EXIT_OK, stderr)
        code, _, _, stderr = self.play(self.file, "--id", self.zone_ids[-1])
        self.assertEqual((code, self.loads()), (helper.EXIT_OK, [LABEL_CONTROLS[0], ZONE_CONTROLS[0]]), stderr)


class CostTest(unittest.TestCase):
    """The one-label rule's cost (constraint 7), counted: an entry holding a
    colon passed D-SINK-87, which lets a colon through only in an IPv6
    literal, so it is never asked of dotless_host (whose literal parse is
    the expensive part), and each distinct entry of a line is asked once
    however many pairs repeat it. A local playlist asks nothing. And a list
    of PLAIN entries from a public playlist -- names, IPv4 literals --
    which reading 3 accepts with one translate, is walked here an entry at
    a time, a call per distinct entry: the cost the D-SINK-89 row states
    for it, about three times a local list's per line (the review of
    cce5548, which found it stated only for a list of IPv6 literals)."""

    def calls(self, url, source):
        real = helper.dotless_host
        seen = []

        def counted(host):
            seen.append(host)
            return real(host)

        with mock.patch.object(helper, "dotless_host", counted):
            refusal = helper.stream_entry_refusal(url, source)[0]
        return refusal, len(seen)

    def test_counted(self):
        listed, index = "", 1
        while len(listed) + 48 < helper.M3U_MAX_URL:
            listed += "::%x," % index
            index += 1
        ipv6 = "udp://@239.1.1.1:5000?sources=" + listed
        rtp6 = "rtp://239.1.1.1:5004?block=" + listed
        pairs = "rtp://239.1.1.1:5004?" + "sources=a.example.test&" * 150
        names = "udp://@239.1.1.1:5000?block=" + ",".join("h%d.example.test" % i for i in range(200))
        ipv4, index = "udp://@239.1.1.1:5000?sources=", 0
        while len(ipv4) + 16 < helper.M3U_MAX_URL:
            ipv4 += "10.%d.%d.1," % (index // 256, index % 256)
            index += 1
        got = [self.calls(ipv6, remote()), self.calls(rtp6, remote()), self.calls(pairs, remote()),
               self.calls(names, remote()), self.calls(ipv6, local_sources()["file"]),
               self.calls("http://stream.example.test/x", remote()), self.calls(ipv4, remote()),
               self.calls(ipv4, local_sources()["file"])]
        # The authority's host is asked once a line; the lists of literals
        # ask only the empty entry their last comma leaves, never a literal;
        # a plain list from a public playlist asks every distinct entry,
        # the empty one its last comma leaves among them.
        self.assertEqual(got, [("", 2), ("", 2), ("", 2), ("", 201), ("", 0), ("", 1), ("", index + 2), ("", 0)])
        self.assertGreater(len(ipv6), 4000)
        self.assertGreater(len(ipv4), 4000)
        self.assertGreater(index, 300)


if __name__ == "__main__":
    unittest.main()
