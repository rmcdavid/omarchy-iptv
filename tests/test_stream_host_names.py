"""D-SINK-87 (the owner, 2026-11-08): no channel stream address that names a
host the player would read in a form D-SINK-86 refuses is handed to the
player.

D-SINK-86's host_name_refused refuses a host name that holds `@`, `%`, `;`,
`=`, `&`, a second `:` (one port is fine), whitespace or an invisible format
character, and, since D-SINK-88, one whose NFKD form does; the helper asks it
before every connection it opens itself. A channel's stream address is not
one of those: the helper hands it to the player, which reads the host and
looks it up. So the two gates that decide what reaches the player ask it too:

1. Parse. stream_entry_refusal (called by parse_m3u) refuses such a
   location line, so it never becomes a channel in channels.json, and the
   `playlist` verb counts it with the other refused entries in a sentence
   that names no host and no URL.
2. Play. player_target refuses such an address before anything is sent to
   the player, whether it comes from a cache written before the rule or from
   a typed `play --url`, with `unsupported_scheme` and one fixed sentence
   that names no host and no URL.

The host is judged as the PLAYER would read it, and where the helper's
reading and the player's could differ, by every reading, each asked of the
same predicate (bin/helper/02-sources.py, the D-SINK-87 block):
  1. the authority's host[:port] as written, after its last `@` (FFmpeg
     reads a port as the digits up to the next colon, urlsplit reads no port
     at all, so what follows the port is judged too), in SR15's form: a port
     of ASCII digits or none, and a bracket only as a leading IPv6 literal's
     pair (FFmpeg reads `[v1.a:b]` as the name `v1.a:b`; urlsplit reads
     `a[@v1.evil]x` as the host `v1.evil]x`), which FormTest holds. urlsplit's
     own host is then inside it, which SubsumptionTest holds;
  2. for the schemes mpv percent-escapes before FFmpeg reads them (http,
     https, mmsh, and mms, rewritten to mmsh), that host[:port] as mpv
     escapes it -- a `%` for every byte outside the unreserved and reserved
     sets, so a Unicode host name the helper reads whole reaches the player
     as a name holding `%`;
  3. for udp and rtp, every entry of the `sources` and `block` values,
     which FFmpeg decodes (once; rtp twice, and resolves both) and looks up
     by name, under any name FFmpeg reads as one of those two (it decodes a
     name into a C string, so `sources%00x` is `sources`); a reading holding
     `'`, a backslash, a bracket or a NUL, as decoded, is refused whole.
A fast accept in front of the readings (an authority of plain ASCII with a
digits-only port, never for udp or rtp) is held equal to them by
FastPathTest over every code point, and held to be TAKEN for the plain
addresses a playlist is made of; reading 3's own fast accept is held equal
to its per-entry judgment by ReadingShortcutTest the same way. CostTest
holds reading 3's own shortcuts, so a 4,096-character source list costs a
few calls per line, not one per entry, however many pairs repeat it.

How this module observes it: the shipping `playlist` verb as a subprocess
on a local playlist FILE (nothing is fetched, nothing is looked up), and
the shipping `play` and `player start|restart` verbs, in process, against
tests/test_mpv.py's FakeMpv on a scratch socket under /tmp, never the
default socket and never a real player: "never handed to the player" means
the FakeMpv recorded no `loadfile` and no command naming the address. A
control channel on the same FakeMpv IS loaded, so the absence is the gate's.
A typed `--url` holding a byte no text decodes runs the verb as a
subprocess, so its argv is decoded as the helper's own is.
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
    # A `]` in the host after a `[` in the userinfo, which urlsplit reads as
    # an IPvFuture-shaped host and never splits at the bracket (the review
    # of 95f1bb9): not SR15's form, though no character of it is refused.
    "http://a[@v1.evil]x/live/1.ts",
    "http://u[@v1.a]evil.test:80/live/1.ts",
    # 3. As mpv escapes an http-like URL before FFmpeg reads it: a `%`.
    "http://evil" + chr(0xFC) + ".test/live/1.ts",
    "https://evil" + chr(0xE9) + ".test/live/1.ts",
    "mms://evil" + chr(0xFC) + ".test/live/1",
    "http://evil" + chr(0x5C) + "x.test/live/1.ts",
    "http://evil|x.test/live/1.ts",
    "mmsh://evil" + chr(0xFC) + ".test/live/1",
    # 4. The form: a bracket that is no IPv6 literal (FFmpeg reads its
    #    content as the host, a name holding a colon; urlsplit accepts it as
    #    IPvFuture), and a port that is not digits (FFmpeg reads host
    #    `evil`, port 123).
    "http://[v1.evil:qqqqqq]/live/1.ts",
    "rtsp://[v1.evil:qqqqqq]/stream",
    "srt://[v1.evil:qqqqqq]?mode=caller",
    "https://user:pw@[v1.evil:qqqqqq]/live/1.ts",
    "http://evil:123qqqqqq/live/1.ts",
    "rtmp://evil:1935qqqqqq/live/1",
    # 5. The hosts a udp or rtp query names, which FFmpeg decodes (rtp
    #    twice) and looks up entry by entry: an escaped `@`, a userinfo, an
    #    escaped `;` and `=`, `+` as a space, an escaped name, a second
    #    entry, `+` escaped once (a space only on rtp's second decode),
    #    quoting, a host folded to `=` (D-SINK-88), and a space av_get_token
    #    does not trim.
    "udp://@239.1.1.1:5000?sources=evil%40qqqqqq.test",
    "udp://@239.1.1.1:5000?sources=ok.test,u:p@evil.test&p=qqqqqq",
    "udp://@239.1.1.1:5000?block=evil%3Bsid%3Dqqqqqq",
    "udp://@239.1.1.1:5000?sources=evil+qqqqqq",
    "udp://@239.1.1.1:5000?%73ources=evil%25qqqqqq",
    "rtp://239.1.1.1:5004?block=10.0.0.1,evil;qqqqqq",
    "rtp://239.1.1.1:5004?sources=evil%2Bqqqqqq.test",
    "udp://@239.1.1.1:5000?sources='evil,qqqqqq'",
    "udp://@239.1.1.1:5000?sources=evil" + chr(0x5C) + ",qqqqqq",
    # The same, escaped: the quote and the backslash are the DECODED
    # reading's, which is what av_get_token reads.
    "udp://@239.1.1.1:5000?sources=%27evil,qqqqqq%27",
    "udp://@239.1.1.1:5000?sources=evil%5C,qqqqqq",
    # rtp's once-decoded reading, which rtp resolves itself, holds `%`; its
    # twice-decoded one (`evilAqqqqqq.test`) would pass.
    "rtp://239.1.1.1:5004?sources=evil%2541qqqqqq.test",
    # A later pair whose first reading is an earlier pair's second: its own
    # second decode (`fe80::1@evil.qqqqqq`) is one the first pair never
    # made, and the one rtp hands udp, FFmpeg keeping the last value. Every
    # reading before it is a literal whose zone holds only zone characters
    # (the review of 6371c67: decoding that stopped at the repeated reading
    # let it play).
    "rtp://239.1.1.1:5004?sources=fe80::1%252540evil.qqqqqq&sources=fe80::1%2540evil.qqqqqq",
    # A value repeated before the refused pair, under one name or across
    # both: decoding skips a value already read and goes on to the next
    # pair (the review of bf47cdc: a `break` at that skip let both through,
    # with every suite green).
    "udp://@239.1.1.1:5000?sources=a.example.test&sources=a.example.test&sources=evil%40qqqqqq.test",
    "udp://@239.1.1.1:5000?block=a.example.test&sources=a.example.test&block=evil%40qqqqqq.test",
    # An ENTRY already judged before the refused one, in an earlier pair or
    # earlier in the same reading: the walk passes over it and goes on (the
    # review of cce5548: a `break` at that skip passed every suite, and what
    # it let through moved with the hash seed while the entries were walked
    # as a set). `fe80::1` holds a colon, so no reading here is plain.
    "udp://@239.1.1.1:5000?sources=fe80::1&block=fe80::1,evil%40qqqqqq.test",
    "udp://@239.1.1.1:5000?sources=fe80::1,+fe80::1,evil%40qqqqqq.test",
    "udp://@239.1.1.1:5000?sources=evil" + chr(0xFF1D) + "qqqqqq.test",
    # av_get_token trims only its four ASCII spaces: U+3000 stays in the name.
    "udp://@239.1.1.1:5000?sources=qqqqqq.evil%E3%80%80",
    # A name FFmpeg n9.0.2 reads up to its first decoded NUL: find_opt
    # decodes it into a C string, so `sources%00` and `block%00x` are
    # `sources` and `block` to it (the review of 3ba4044).
    "udp://@239.1.1.1:5000?sources%00=evil;sid=qqqqqq.test",
    "udp://@239.1.1.1:5000?block%00x=user:pass@evil.test",
    "rtp://239.1.1.1:5004?sources%00=evil%3Bsid.qqqqqq",
    "rtp://239.1.1.1:5004?block%00=evil+qqqqqq.test",
    # A bracket in an entry: ip.c hands each entry to getaddrinfo as it is,
    # with no bracket handling, so `[2001:db8::1]qqqqqq` is looked up as a
    # NAME holding `[`, colons and `]` (the review of 3ba4044).
    "udp://@239.1.1.1:5000?sources=[2001:db8::1]qqqqqq",
    "udp://@239.1.1.1:5000?sources=%5Bfe80::1%2525evil.qqqqqq%5D",
    "rtp://239.1.1.1:5004?block=[::1]evil.test,10.0.0.1",
    "udp://@239.1.1.1:5000?block=10.0.0.1,qqqqqq]evil",
    # A NUL in a value ends FFmpeg's C string, so the list past it is not the
    # one FFmpeg reads: refused whole, as a quote is, not read two ways.
    "udp://@239.1.1.1:5000?sources=10.0.0.1,evil.test%00qqqqqq",
    # An entry holding only a decoded `:`, `=`, `&` or tab of the refused
    # characters: reading 3's fast accept must trust none of them (the
    # review of 3ba4044 added each to it with every suite green).
    "udp://@239.1.1.1:5000?sources=user%3Aqqqqqq.evil.test",
    "udp://@239.1.1.1:5000?block=a%3Dqqqqqq.evil",
    "udp://@239.1.1.1:5000?sources=evil%26qqqqqq",
    "udp://@239.1.1.1:5000?sources=evil%09qqqqqq",
    # 6. D-SINK-88: an unescaped scheme's host whose folded form (the idna
    #    codec's, and NFKD's) holds `;`, `%40` or a space.
    "rtsp://evil" + chr(0xFF1B) + "qqqqqq.test/stream",
    "srt://evil" + chr(0xFE6A) + "40qqqqqq.test:9000?mode=caller",
    "rtmp://evil" + chr(0xA8) + "qqqqqq.test/live/1",
    # A sequence, not one code point: B.2 maps U+0345 to a letter that
    # keeps U+FF1D's `=` from composing with U+0338, so the codec hands on
    # `=`, while NFKC alone composes it away (the review of 95f1bb9).
    "rtsp://sid" + chr(0xFF1D) + chr(0x345) + chr(0x338) + "evil.test/stream",
    # 7. D-SINK-92 (the review of bf47cdc): a backslash in an unescaped
    #    scheme's host, which systemd-resolved reads as an escape -- a
    #    backslash and 058 a colon, 091 and 093 brackets, 064 an `@`, and
    #    one before a dot keeps the dot inside one label -- and U+FF3C,
    #    which the codec folds to one. mpv escapes an http-like URL's to
    #    `%5C` (section 3).
    "rtsp://evil" + chr(0x5C) + "058qqqqqq.test/stream",
    "rtmp://evil" + chr(0x5C) + "091qqqqqq" + chr(0x5C) + "093.test/live/1",
    "srt://evil" + chr(0x5C) + "064qqqqqq.test:9000?mode=caller",
    "rtsp://evilqqqqqq" + chr(0x5C) + ".x/stream",
    "rtmp://evil" + chr(0xFF3C) + "qqqqqq.test/live/1",
    # Each of the six code points D-SINK-92's fold reads as a bracket or a
    # backslash (U+FF3B, U+FF3D, U+FE47, U+FE48; U+FF3C, U+FE68), in a udp
    # or rtp source entry, where the ASCII three are refused whole by the
    # reading and the folds only by the name rule, and in an unescaped
    # scheme's authority (the review of cce5548: either call site could
    # stop asking about them with every suite green).
    "udp://@239.1.1.1:5000?sources=evil%EF%BC%BBqqqqqq.test",
    "udp://@239.1.1.1:5000?sources=10.0.0.1,evil%EF%B9%87qqqqqq.test",
    "udp://@239.1.1.1:5000?block=evil%EF%BC%BCqqqqqq.test",
    "rtp://239.1.1.1:5004?block=evil%EF%BC%BDqqqqqq.test",
    "rtp://239.1.1.1:5004?block=10.0.0.1,evil%EF%B9%88qqqqqq.test",
    "rtp://239.1.1.1:5004?sources=evil%EF%B9%A8qqqqqq.test",
    "rtsp://evil" + chr(0xFF3B) + "qqqqqq.test/stream",
    "rtsp://evil" + chr(0xFF3D) + "qqqqqq.test/stream",
    "rtmp://evil" + chr(0xFE47) + "qqqqqq.test/live/1",
    "srt://evil" + chr(0xFE48) + "qqqqqq.test:9000?mode=caller",
    "srt://evil" + chr(0xFE68) + "qqqqqq.test:9000?mode=caller",
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
    # An IPv6 literal keeps its colons and its zone's `%` (D-SINK-86). Its
    # zone is digits: one that is not (`%25eth0`) FFmpeg cuts into another
    # host, which D-SINK-91 refuses (tests/test_stream_label_zone.py).
    "http://[fe80::1%252]:8080/live/5.ts",
    "http://xn--bcher-kva.test/live/6.ts",
    # rtsp is not escaped by mpv (its demuxer opens the URL as given), so
    # the one reading is the name, which the predicate allows.
    "rtsp://b" + chr(0xFC) + "cher.test/stream",
    # librtmp-style options after a space belong to the path, not the host.
    "rtmp://stream.example.test/live/stream live=1",
    "udp://@239.1.1.1:1234",
    "srt://stream.example.test:9000?mode=caller&passphrase=a;b=c",
    "http://[2001:db8::1]/live/8.ts",
    # IP literals, a bare IPv6 one, and av_get_token's trimmed space: what
    # a multicast source list holds.
    "udp://@239.1.1.1:1234?sources=10.0.0.1,10.0.0.2",
    "rtp://239.1.1.1:5004?block=192.0.2.1,+192.0.2.2&ttl=4",
    "udp://@239.1.1.1:1234?sources=fe80::1",
    # `+` escaped once is a `+` to udp, which decodes once.
    "udp://@239.1.1.1:1234?sources=a%2Bb.test",
    # An http query names no host the player looks up.
    "http://stream.example.test/live/9.ts?sources=a@b%40c&block=x;y",
    # A host whose NFKC form is a full stop and a letter.
    "rtsp://stream" + chr(0xFF0E) + "example.test/stream",
]

PLURAL = "%d entries skipped: their addresses name hosts the player would read in forms no host name or port may take"
SINGULAR = "1 entry skipped: its address names a host the player would read in a form no host name or port may take"


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
    """The gate judges the authority's host[:port] as written, in SR15's
    form, and not urlsplit's hostname separately, because the first holds
    the second: with a digits-only port and a bracket only as an IPv6
    literal's, the hostname is that text up to its port, or the literal's
    content, lower-cased. Before the form was held this was false: `[v1.a:b]`
    spent the port's one colon inside its bracket and played, while urlsplit's
    hostname `v1.a:b` is refused (the review of fdd95a4). These hold the two
    halves of the claim, so the reading the gate leaves out is one it cannot
    need: lower-casing changes no code point's verdict, and every vector,
    the IPvFuture ones and these brackets among them, that urlsplit's
    hostname refuses the gate refuses."""

    BRACKETS = ["http://[v1.a:b]/x", "http://[v1.a]/x", "http://[v1.a;b]:80/x", "http://[V1.A:B]/x",
                "http://[fe80::1%25eth0]/x", "http://[fe80::1%25a]:80/x", "http://[::ffff:192.0.2.1]/x",
                "http://[2001:db8::1]:8080/x", "rtsp://[v7.a:b:c]/x"]

    def test_lower_casing_changes_no_code_points_verdict(self):
        predicate = getattr(helper, "host_name_refused")
        wrong = [hex(c) for c in range(0x110000) if not 0xD800 <= c <= 0xDFFF
                 and predicate("h%s.test" % chr(c)) != predicate(("h%s.test" % chr(c)).lower())]
        self.assertEqual(wrong[:8], [])

    def test_every_vector_urlsplit_refuses_the_gate_refuses(self):
        gate = getattr(helper, "stream_host_name_refused", lambda url: "<missing>")
        vectors = REFUSED + CONTROLS + self.BRACKETS
        missed = [ascii(u) for u in vectors
                  if helper.host_name_refused(urllib.parse.urlsplit(u).hostname or "") and gate(u) is not True]
        self.assertEqual(missed, [])
        # The IPvFuture vectors whose content holds a colon are among them,
        # the case the review found, so this can go red.
        future = [u for u in vectors if (urllib.parse.urlsplit(u).hostname or "").startswith("v")
                  and ":" in urllib.parse.urlsplit(u).hostname]
        self.assertGreaterEqual(len(future), 7)


class FormTest(unittest.TestCase):
    """_stream_authority_refused, readings 1 and 2, asked of host[:port]
    texts directly: urlsplit (Python 3.14) refuses some of these before the
    gate is asked -- a netloc holding one kind of bracket, text before a `[`
    in the host[:port] or between its `]` and a port's colon, a bracketed
    host that is neither an IPv6 address nor IPvFuture-shaped -- so a vector
    through the gate alone could not hold the form's every decision."""

    REFUSED = ["[::1]x", "[::1]x:80", "[::1]]", "[::1]:8[0]", "[v1.a]", "[v1.a:b]:80", "[::1", "a]b", "a[b",
               "v1.evil]x", "v1.a]b.test:80", "h.test:8o", "h.test:80:81"]
    ALLOWED = ["[::1]", "[::1]:", "[::1]:80", "[fe80::1%25eth0]:8080", "[2001:db8::1]", "h.test", "h.test:",
               "h.test:80", "127.0.0.1:5000"]

    def test_a_bracket_is_only_a_leading_literals_pair_and_a_port_only_digits(self):
        refused = getattr(helper, "_stream_authority_refused")
        got = [(scheme, text, refused(text, scheme)) for scheme in ("http", "rtsp")
               for text in self.REFUSED + self.ALLOWED]
        want = [(scheme, text, text in self.REFUSED) for scheme in ("http", "rtsp")
                for text in self.REFUSED + self.ALLOWED]
        self.assertEqual(got, want)


class FastPathTest(unittest.TestCase):
    """The fast accept in front of the readings (_plain_authority, asked by
    _stream_name_refused) is a shortcut, not a rule: whatever it accepts,
    every reading (_stream_name_readings) lets through, for an escaped
    scheme (http) and an unescaped one (rtsp). Held over every code point
    inserted into the host, the port, and the host after a userinfo, and
    over the ASCII range before the host and right after the port's colon,
    so a character the shortcut wrongly trusts, a port it wrongly reads as
    digits, or a userinfo it ends in the wrong place, is found. And the
    shortcut is what the gate answers with: over the low code points
    _stream_name_refused equals the readings, and udp and rtp, whose query
    hosts the readings judge, never take it."""

    EVERY = [("stream", ".example.test"), ("stream.example.test:8", "0"), ("us:er@stream", ".example.test")]
    ASCII = [("", "stream.example.test:8080"), ("stream.example.test:", "")]

    def test_what_the_shortcut_accepts_no_reading_refuses(self):
        plain = getattr(helper, "_plain_authority", None)
        readings = getattr(helper, "_stream_name_readings", None)
        self.assertIsNotNone(plain)
        accepted, wrong = 0, []
        for netlocs, top in ((self.EVERY, 0x110000), (self.ASCII, 0x80)):
            for head, tail in netlocs:
                for c in range(top):
                    netloc = head + chr(c) + tail
                    if plain(netloc):
                        accepted += 1
                        for scheme in ("http", "rtsp"):
                            if readings("%s://%s/x" % (scheme, netloc), netloc, scheme) is not False:
                                wrong.append((scheme, ascii(netloc)))
        # Each of the three host parts takes the 66 plain characters and an
        # `@` (which ends a userinfo, leaving a plain authority after it);
        # each port part the ten digits and an `@`: 67 * 3 + 11 * 2. So a
        # shortcut that trusted nothing would be red here too, while every
        # answer stayed right.
        self.assertEqual((accepted, wrong[:8]), (223, []))

    def test_the_gate_answers_the_readings_and_udp_and_rtp_never_take_the_shortcut(self):
        gate, readings = helper._stream_name_refused, helper._stream_name_readings
        wrong = []
        for head, tail in self.EVERY + self.ASCII:
            for c in range(0x800):
                netloc = head + chr(c) + tail
                for scheme in ("http", "rtsp"):
                    url = "%s://%s/x" % (scheme, netloc)
                    if gate(url, netloc, scheme) != readings(url, netloc, scheme):
                        wrong.append((scheme, ascii(netloc)))
        for scheme in ("udp", "rtp"):
            url = "%s://@239.1.1.1:5000?sources=evil%%40qqqqqq.test" % scheme
            if gate(url, "@239.1.1.1:5000", scheme) is not True:
                wrong.append((scheme, "the query hosts were skipped"))
        self.assertEqual(wrong[:8], [])


    def test_the_shortcut_is_taken_for_a_playlists_plain_addresses(self):
        """The shortcut is what the gate answers with, not only what it may
        answer: over the stream lines of test_playlist's PerformanceTest and
        every control with a plain authority that is not udp or rtp, the
        parse's question never reaches the readings, and over the udp and rtp
        controls it always does. Without this, a gate that dropped the
        shortcut was held only by a timing budget it missed by about 1%."""
        real = helper._stream_name_readings
        calls = []

        def counted(*args, **kwargs):
            calls.append(args[0])
            return real(*args, **kwargs)

        lines = ["http://stream.example.test/live/%d/index.m3u8" % i for i in range(0, 10000, 37)]
        plain = [u for u in CONTROLS if urllib.parse.urlsplit(u).scheme not in ("udp", "rtp")
                 and helper._plain_authority(urllib.parse.urlsplit(u).netloc)]
        query = [u for u in CONTROLS if urllib.parse.urlsplit(u).scheme in ("udp", "rtp")]
        source = {"host": "", "local": True}
        with mock.patch.object(helper, "_stream_name_readings", counted):
            answers = [helper.stream_entry_refusal(u, source)[0] for u in lines + plain]
            taken = list(calls)
            del calls[:]
            for u in query:
                helper.stream_entry_refusal(u, source)
        self.assertEqual((set(answers), taken, len(plain) >= 8), ({""}, [], True))
        self.assertEqual(calls, query)


class ReadingShortcutTest(unittest.TestCase):
    """Reading 3's fast accept (_plain_reading, asked by
    _query_reading_refused) is a shortcut, not a rule, held as FastPathTest
    holds the authority's: whatever it accepts, the per-entry judgment
    (_query_entries_refused) lets through. Held over every code point alone,
    at an entry's edge, as an entry between two, and inside an entry, so a
    character it wrongly trusts is found wherever av_get_token's trim would
    hide it (a tab at an entry's edge is trimmed, inside one it is not). And
    the shortcut is what the reading's judgment answers with: over the low
    code points in the same places, _query_reading_refused answers what it
    answers with the shortcut turned off. The review of 3ba4044 added `:`,
    `=`, `&` and a tab to the shortcut's set, each with every suite green."""

    PLACES = ["%s", "10.0.0.1%s,10.0.0.2", "10.0.0.1,%s,10.0.0.2", "h.te%sst"]

    def test_what_the_shortcut_accepts_no_entry_refuses(self):
        plain = getattr(helper, "_plain_reading", None)
        entries = getattr(helper, "_query_entries_refused", None)
        self.assertIsNotNone(plain)
        self.assertIsNotNone(entries)
        accepted, wrong = 0, []
        for place in self.PLACES:
            for c in range(0x110000):
                reading = place % chr(c)
                if plain(reading):
                    accepted += 1
                    if entries(reading, set()) is not False:
                        wrong.append(ascii(reading))
        # The 66 plain characters and the comma, in each of the four places:
        # a shortcut that trusted nothing would be red here too.
        self.assertEqual((accepted, wrong[:8]), (67 * 4, []))

    def test_the_reading_is_judged_as_with_the_shortcut_off(self):
        judge = helper._query_reading_refused
        readings = [place % chr(c) for place in self.PLACES for c in range(0x800)]
        on = [judge(reading) for reading in readings]
        with mock.patch.object(helper, "_plain_reading", lambda reading: False):
            off = [judge(reading) for reading in readings]
        wrong = [ascii(reading) for reading, a, b in zip(readings, on, off) if a != b]
        # Both answers occur: 43 code points below U+0800 are refused in each
        # place, and inside an entry also the four av_get_token trims at an
        # edge (tab, LF, CR and the space).
        self.assertEqual((wrong[:8], on.count(True)), ([], 43 * 4 + 4))


class CostTest(unittest.TestCase):
    """Reading 3's cost (constraint 7): a provider's `sources` or `block`
    list, as long as a stream URL may be (M3U_MAX_URL), costs the parse at
    most three calls of host_name_refused per line here (the authority and
    each distinct entry) and one read of the query, not one call per entry -- the review of 95f1bb9 measured such lists at up to
    68 s per 10,000 lines. Counted, not timed, so it cannot pass by luck or
    fail by load: a reading of plain characters is accepted at once (lists
    of distinct numbers, IPv4 literals and names among the shapes), each
    distinct entry is judged once per line however many pairs repeat it (a
    query of `sources=::1&` pairs among the shapes, which the review of
    3ba4044 counted at 340 calls a line), a value already read on the line
    is not decoded again, a reading already judged on it, rtp's unchanged
    second decode among them, is not judged again (the shapes say how many
    distinct readings each holds), and the listening rule's read of the
    query is reused. A list of DISTINCT entries that are not plain still
    costs a call per entry: one whose entries hold colons, IPv6 literals
    say, needs it; one whose entries hold none could take a per-code-point
    verdict with the same answers, a shortcut not taken; and whether to
    bound a list at all is the owner's open question (the D-SINK-87 row:
    FFmpeg's own names fail the open at 512 bytes, a name only this reading
    takes does not)."""

    @staticmethod
    def filled(head, unit):
        return head + unit * ((helper.M3U_MAX_URL - len(head)) // len(unit))

    @staticmethod
    def distinct(head, entry):
        """head, then entry % 0, entry % 1, ... joined by commas, to the
        longest stream URL the parse keeps: every entry its own name."""
        url, index = head, 0
        while len(url) + len(entry % index) + 1 <= helper.M3U_MAX_URL:
            url += entry % index + ","
            index += 1
        return url

    def shapes(self):
        """(url, the distinct readings it holds): one for each list, none for
        the `%41&` query, which names no source, one for a line of one pair
        repeated, and two for one of two pairs repeated."""
        shapes = []
        for scheme, authority in (("udp", "@239.1.1.1:5000"), ("rtp", "239.1.1.1:5004")):
            for name in ("sources", "block"):
                head = "%s://%s?%s=" % (scheme, authority, name)
                shapes += [(self.filled(head, "1,"), 1), (self.filled(head, ","), 1), (self.filled(head, "::1,"), 1),
                           (self.filled(head, "10.0.0.1,"), 1), (self.filled(head, "+192.0.2.2,"), 1),
                           (self.distinct(head, "%d"), 1), (self.distinct(head, "10.0.%d.1"), 1),
                           (self.distinct(head, "h%d.test"), 1)]
            query = "%s://%s?" % (scheme, authority)
            shapes += [(self.filled(query, "%41&"), 0), (self.filled(query, "sources=::1&"), 1),
                       (self.filled(query, "block=::1&"), 1), (self.filled(query, "sources=::1,::2&block=::2,::1&"), 2)]
        return shapes

    def test_a_long_source_list_costs_a_few_calls_per_line(self):
        real_name, real_params = helper.host_name_refused, helper.stream_params
        real_reading, real_decode = helper._query_reading_refused, urllib.parse.unquote_plus
        names, params, readings, decodes = [], [], [], []

        def name(*args, **kwargs):
            names.append(args[0])
            return real_name(*args, **kwargs)

        def read(*args, **kwargs):
            params.append(args[0])
            return real_params(*args, **kwargs)

        def reading(*args, **kwargs):
            readings.append(args[0])
            return real_reading(*args, **kwargs)

        def decode(*args, **kwargs):
            decodes.append(args[0])
            return real_decode(*args, **kwargs)

        got = []
        with mock.patch.object(helper, "host_name_refused", name), mock.patch.object(helper, "stream_params", read), \
                mock.patch.object(helper, "_query_reading_refused", reading), \
                mock.patch.object(urllib.parse, "unquote_plus", decode):
            for url, _ in self.shapes():
                del names[:], params[:], readings[:], decodes[:]
                refusal = helper.stream_entry_refusal(url, {"host": "", "local": True})[0]
                # Only reading 3 decodes with `+` as a space: each distinct
                # value once a decode, at most two values here, rtp's twice.
                got.append((url[:32], len(url) > 4000, refusal, len(names) <= 3, len(params), len(readings),
                            len(decodes) <= 4))
        self.assertEqual(got, [(url[:32], True, "", True, 1, count, True) for url, count in self.shapes()])


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

    def test_a_typed_address_holding_a_byte_no_text_decodes_gets_the_refusal(self):
        """A `--url` typed with a byte that is no UTF-8 reaches the helper,
        as every argv does, as a lone surrogate (surrogateescape). The gate's
        escaped reading percent-escapes it (surrogatepass), as mpv escapes
        every byte outside its kept set, so the reading holds `%` and is
        refused, rather than ending in an `internal` error and a traceback. A subprocess, so the argv is the
        interpreter's own decoding; the refusal comes before any connection,
        so the socket is never opened."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("OMARCHY_IPTV_")}
        done = subprocess.run([sys.executable, str(HELPER), "play", "--url", b"http://evil\xffqqqqqq.test/live/1.ts",
                               "--socket", os.path.join(self.dir, "none.sock"), "--ipc-timeout", "1"],
                              capture_output=True, text=True, env=env, timeout=60)
        lines = [l for l in done.stdout.strip().splitlines() if l.strip()]
        reply = json.loads(lines[-1]) if lines else {}
        error = reply.get("error") or {}
        self.assertEqual((done.returncode, error.get("code"), error.get("message"), "Traceback" in done.stderr,
                          leaks(done.stdout + done.stderr)),
                         (helper.EXIT_ERROR, "unsupported_scheme", getattr(helper, "STREAM_HOST_NAME_REFUSAL", None),
                          False, []), done.stderr)
        self.assertEqual(self.loads(), [])

    def test_a_start_or_a_restart_with_a_channel_hands_the_player_no_refused_address(self):
        replies = [self.start(verb, cid) for verb in ("start", "restart") for cid in self.ids]
        self.assert_never_sent(replies)
        code, reply, _, stderr = self.start("start", "c0")
        self.assertEqual((code, self.loads()), (helper.EXIT_OK, [CONTROLS[0]]), stderr)


if __name__ == "__main__":
    unittest.main()
