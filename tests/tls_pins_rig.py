#!/usr/bin/env python3
"""tests/tls_pins_rig.py -- the windowless arm of scripts/dev-harness/tls-scenario.sh
(`tls-scenario.sh --windowless [--baseline REF]`). Not a unit test: unittest
discovery does not load it, because it starts mpv and servers.

D-SINK-43..46 (2026-10-29). The player's TLS peer, and the other sinks the pin
block closes, observed from the attacker's side the way tls-scenario's S1..S6
are, but WITHOUT a window, a shell or a cage: mpv runs with `--vo=null
--ao=null`, no DISPLAY, WAYLAND_DISPLAY or DBUS_SESSION_BUS_ADDRESS, a core
limit of 0, a private HOME and XDG tree, and `--config-dir` naming the case's
own mpv.conf -- the model of the user's. The argv is the tree's own
`filter_mpv_args` + `mpv_launch_argv` (less `--force-window`), and the channel
is loaded by the tree's own `apply_channel` over the IPC socket, so what is
measured is the shipping composition and the shipping wire sequence; what is
NOT exercised is the service and the detached spawn, which the live arm and
player-scenario cover.

The servers are this file's own, on 127.0.0.1 only, ports 8780-8786, started
as children of this process and stopped by the pids it holds:
  provider  CA-signed for 127.0.0.1; its live.m3u8's one segment is on the attacker
  attacker  self-signed for 127.0.0.1
  hlsok     CA-signed; its live.m3u8's segment is on itself (the control)
  alt       the FIRST connection of a case gets the CA-signed 127.0.0.1
            certificate, every later one a CA-signed certificate for
            `evil.test`: an on-path attacker that lets mpv's probe through and
            answers libavformat's reopen with a certificate valid for its OWN name
  plain     plain http (watch history, select)
A request in the attacker's log is the attacker holding the stream request,
and with it the provider header the case set.

Checks, each asserting the FIXED behaviour (so `--baseline <ref before the
fix>` reds W1..W10 and the controls stay green):
  W1  an HLS channel with `--demuxer-lavf-o=tls_verify=0` in mpvArgs: refused
      by the filter, and the attacker gets nothing
  W2  the same key past the filter (a token the filter missed, or an mpv.conf
      line of the same option): the attacker gets nothing
  W3  `verifyhost=evil.test` past the filter: the reopen is refused
  W4  `[protocol.https] stream-lavf-o=tls_verify=0` in mpv.conf: nothing
  W5  `[protocol.https] demuxer-lavf-o=tls_verify=0` on HLS: nothing
  W6  a profile-cond profile with `tls-verify=no`: nothing
  W7  `save-watch-history=yes` in mpv.conf: no file outside the runtime
      folder holds the credential
  W8  select's `g l` (`script-binding select/select-subtitle-line`): no child
      of the player carries the credential on its command line
  W9  an ADOPTED player started by the --pre-pin tree's argv, with W4's
      profile in its mpv.conf: the tree's migration and apply_channel refuse
      to load, and the attacker gets nothing
  W10 `player-operation-mode=pseudo-gui` as a plain mpv.conf line: mpv then
      applies the user's [pseudo-gui] profile AFTER the command line, over
      every pin (recheck, 2026-10-29). With that profile turning on a script,
      the watch history, the select menu and a resume record in $HOME: no
      file outside the runtime folder holds the credential and no child of
      the player carries it
  C1  a common harmless set (--hwdec=auto-safe --profile=low-latency
      --cache-secs=30 --volume=50 --tls-ca-file=<CA>) is kept and PLAYS
  C2  a CA-signed HLS channel with --demuxer-lavf-o=live_start_index=-1 PLAYS
      and keeps the user's key

lane-p1b (2026-10-29) adds, against a seventh server, `lab` (plain http,
8785, every request's headers logged), and with the player's own listening
sockets read by `ss` -- which is why tls-scenario.sh runs this rig inside
`unshare -rn` when it can, where nothing but this rig's servers and players
is on the namespace's only interface:
  W11 a channel whose server answers with a PLAIN playlist (D-PLY-44) naming
      an http entry, an srt listener and an rtp listener: no entry is
      fetched, nothing listens, and the load ends `unrecognized file format`
  W12 a channel whose server answers with an SDP body, under .sdp and under
      .ts (D-SINK-55): nothing listens
  W13 provider headers with commas, `=`, quotes and backslashes (the per-file
      loadfile options, 2026-10-29): each arrives as ONE header, verbatim
  W14 an entry the helper did not load (an append, then playlist-next): the
      channel's provider header does not reach it
  W15 the paste-to-playlist key (D-PLY-46): with the user's own input.conf
      binding ctrl+v to append a URL -- the deterministic stand-in for mpv's
      clipboard binding, which a headless player has no clipboard for -- the
      key appends nothing (the entry it would append is never fetched, even
      after playlist-next)
  W16 a typed loopback playlist source whose 302 names the same address on
      ANOTHER port (D-SINK-57, the review's reproduction 1): the shipping
      `playlist` verb refuses it and the other port gets nothing
  W17 an ADOPTED player started by the --pre-pin tree's argv with
      `reset-on-next-file=all` in its mpv.conf and a demuxer tls_verify=0
      left on its command line (D-SINK-60), playing a channel the pre-pin
      tree loaded: the tree's apply_channel refuses the next channel, an HLS
      one whose segment is the attacker's, and the attacker gets nothing --
      mpv restores what the reset list backed up when the playing file ends,
      inside the loadfile, so no migration made during it survives
  W18 an ADOPTED pre-pin player whose mpv.conf has a [protocol.http] profile
      setting save-watch-history (a non-TLS pin): the load is refused and no
      file outside the runtime folder holds the credential
  C3  a loopback relay (Threadfin's shape: playlist, guide and streams on one
      port): the playlist verb keeps its channel's Cookie, the guide hint on
      that port is fetched, and the channel plays with the Cookie

lane-p1c (2026-10-29) adds, on the same lab server and, for the listener
checks, inside the same `unshare -rn`:
  W19 a channel whose server answers with an IMF composition playlist whose
      ASSETMAP names `tcp://0.0.0.0:P?listen=1`, its tls and listen=2 forms,
      and the same CPL served as video/mp2t under .ts (D-SINK-62): nothing
      listens and the ASSETMAP is never fetched
  W20 an ffconcat file naming the CPL by a relative name, and one naming a
      tcp listener with the user's `safe=0` past the filter: nothing listens
  W21 a DASH manifest whose BaseURL is a tcp listener: nothing listens (dash
      opens http(s) only; green before the fix too, kept observed)
  W22 the user's `--prefetch-playlist=yes`, refused as a token, then past the
      filter and as an mpv.conf line (D-SINK-63): an entry appended while the
      channel plays is fetched without the channel's provider header
  W23 an HLS key that 404s while the channel plays logs its whole URL at error
      level; the console key and both console bindings then draw nothing that
      carries it (D-SINK-61: no console), and the same error line still
      reaches a client that asked for error-level messages, which is what the
      shell's own redacted failure tail reads
  W24 hls's `seg_format_options` carrying `format\\_whitelist` and
      `protocol\\_whitelist` (escapes no word of the filter sees) beside
      `extension_picky=0`, past the filter, over an HLS segment that answers
      with an SDP body (D-SINK-64): refused as a token, and past the filter
      nothing listens
  W25 `--demuxer-lavf-format=concat` past the filter over an ffconcat file
      naming the CPL: the forced format is refused like a sniffed one
  C4  a fragmented-MP4 HLS channel with a WebVTT rendition plays and has its
      subtitle track (the format list reaches nested contexts and keeps what
      HLS needs)
  C5  a DASH channel plays (the same, for DASH's nested demuxer)

lane-p2a (2026-10-29) adds an eighth server, `rtsp` (8807, a fake RTSP
server: OPTIONS, DESCRIBE with one MP2T track, SETUP, PLAY; a TCP-interleaved
SETUP is streamed, a UDP one answered with the client's own ports), and:
  W26 the stats overlay (D-SINK-67, the owner's "turn stats off") on a
      channel whose last path segment is empty, so mpv's `filename` is the
      whole credentialed URL: `i`, `I`, `script-binding
      stats/display-stats-toggle` and `stats/display-page-5` (what the OSC's
      title left-click runs) draw nothing that carries it, the bindings are
      refused, and the option reads off -- on a player this tree starts, and
      on a pre-pin player once the tree's adoption has turned it off
  W27 every spelling of `--demuxer-lavf-o` that makes an rtsp channel bind
      its RTP/RTCP pair is WARNED by the tree's filter (D-SINK-65): each is
      played past the filter inside the namespace and, where it binds, the
      tree's mpv_arg_warnings must name it; a spelling that binds nothing is
      a control
  W28 an ADOPTED pre-pin player whose PLAIN mpv.conf line says
      `demuxer-lavf-propagate-opts=no` (D-SINK-68): the HLS segment on the
      attacker gets nothing -- FFmpeg n9.0.1's own tls_verify default is true
      -- with the same case's control, a pre-pin player loaded by the pre-pin
      tree with a demuxer tls_verify=0 past the filter, reaching the attacker
      (the rig can see a bypass in this shape)

usage: tls_pins_rig.py --tree DIR [--pre-pin DIR] --work DIR
Exit 0 green, 1 red, 77 when mpv, ffmpeg or openssl is missing. Stdlib only.
"""
from __future__ import annotations

import http.server
import json
import os
import re
import resource
import shutil
import socket
import ssl
import subprocess
import sys
import time

PORTS = {"provider": 8780, "attacker": 8781, "hlsok": 8782, "alt": 8783, "plain": 8784, "lab": 8785, "rtsp": 8807}
# W11's nested entries name these; nothing may ever listen on them.
NEST_SRT, NEST_RTP, SDP_RTP = 8790, 8792, 8794
# lane-p1c's listeners (W19-W21, W24, W25): nothing may ever listen on them.
IMF_TCP, IMF_TLS, IMF_LISTEN2, IMF_TS, CC_REL, CC_ABS, DASH_BASE, SEG_SDP, FORCED = (
    8796, 8797, 8798, 8799, 8800, 8801, 8802, 8804, 8806)
CPL = ('<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n'
       '<CompositionPlaylist xmlns="http://www.smpte-ra.org/schemas/2067-3/2016" '
       'xmlns:cc="http://www.smpte-ra.org/schemas/2067-2/2016">\n'
       '<Id>urn:uuid:8713c020-2489-45f5-a9f7-87be539e20b5</Id><IssueDate>2021-07-13T17:06:22Z</IssueDate>'
       '<Creator>t</Creator><ContentTitle>Hello</ContentTitle><EditRate>24 1</EditRate>\n'
       '<SegmentList><Segment><Id>urn:uuid:81fed4e5-9722-400a-b9d1-7f2bd21df4b6</Id><SequenceList>'
       '<cc:MainImageSequence><Id>urn:uuid:6ae100b0-92d1-41be-9321-85e0933dfc42</Id>'
       '<TrackId>urn:uuid:e8ef9653-565c-479c-8039-82d4547973c5</TrackId><ResourceList>'
       '<Resource xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="TrackFileResourceType">'
       '<Id>urn:uuid:7be07495-1aaa-4a69-8b92-3ec162122b34</Id><EditRate>24 1</EditRate>'
       '<IntrinsicDuration>24</IntrinsicDuration><SourceDuration>24</SourceDuration><RepeatCount>1</RepeatCount>'
       '<TrackFileId>urn:uuid:00000000-0000-0000-0000-000000000001</TrackFileId></Resource></ResourceList>'
       '</cc:MainImageSequence></SequenceList></Segment></SegmentList></CompositionPlaylist>\n')


def assetmap(uri: str) -> str:
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<AssetMap xmlns="http://www.smpte-ra.org/schemas/429-9/2007/AM">'
            '<Id>urn:uuid:68d9f591-8191-46b5-38b4-affb87a14132</Id><AssetList><Asset>'
            '<Id>urn:uuid:00000000-0000-0000-0000-000000000001</Id><ChunkList><Chunk><Path>%s</Path></Chunk></ChunkList>'
            '</Asset></AssetList></AssetMap>\n' % uri.replace("&", "&amp;"))


def listener(port: int, proto: str = "tcp", form: str = "listen=1") -> str:
    return "%s://0.0.0.0:%d?%s&listen_timeout=3000" % (proto, port, form)

HARD_VALUE = 'a,b=c "d" \'e\' back\\slash end\\'
XMLTV = (b'<?xml version="1.0"?><tv><channel id="a.test"><display-name>A</display-name></channel>'
         b'<programme start="20260101000000 +0000" stop="20991231000000 +0000" channel="a.test"><title>T</title></programme></tv>')
SECRET = "rigPINpass7q"
HEADER = "X-Rig-Secret"
HEADER_VALUE = "rig-provider-header-4k"
MID = "fc2e22bc6ee647b6b90729ab34a250b1"


# ------------------------------------------------------------------ servers

def serve(name: str, port: int, www: str, log: str, cert: str, key: str, alt_cert: str, alt_key: str, seg_url: str) -> None:
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *args):
            pass

        def do_GET(self):
            fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            with os.fdopen(fd, "a") as fh:
                fh.write(json.dumps({"server": name, "path": self.path.split("?")[0],
                                     "secret": SECRET in self.path, "header": HEADER_VALUE in str(self.headers),
                                     "ua": self.headers.get("User-Agent", ""),
                                     "headers": [[k, v] for k, v in self.headers.items()]}) + "\n")
            if name == "lab":
                return self.lab()
            if self.headers.get("User-Agent", "").startswith("Lavf"):
                time.sleep(4)        # keeps a forked ffmpeg alive long enough to be seen
            base = os.path.basename(self.path.split("?")[0])
            if base == "live.m3u8" and seg_url:
                body = ("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:4\n#EXT-X-MEDIA-SEQUENCE:0\n"
                        "#EXTINF:4.0,\n%s\n#EXT-X-ENDLIST\n" % seg_url).encode()
                ctype = "application/vnd.apple.mpegurl"
            else:
                path = os.path.join(www, base)
                if not base or not os.path.isfile(path):
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                with open(path, "rb") as fh:
                    body = fh.read()
                ctype = "video/x-matroska" if base.endswith(".mkv") else "video/mp2t"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def lab(self):
            """lane-p1b's routes: what a stream server can answer with."""
            lab = "http://127.0.0.1:%d" % port
            path = self.path.split("?")[0]
            sdp = ("v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=x\r\nc=IN IP4 0.0.0.0\r\nt=0 0\r\n"
                   "m=video %d RTP/AVP 33\r\n" % SDP_RTP).encode()
            routes = {
                "/nest.m3u": (200, "audio/x-mpegurl", ("#EXTM3U\n#EXTINF:-1,a\n%s/inner.ts\n#EXTINF:-1,b\nsrt://0.0.0.0:%d?mode=listener\n"
                                                       "#EXTINF:-1,c\nrtp://0.0.0.0:%d\n" % (lab, NEST_SRT, NEST_RTP)).encode()),
                "/x.sdp": (200, "application/sdp", sdp),
                "/x.ts": (200, "video/mp2t", sdp),
                "/epg.xml": (200, "application/xml", XMLTV),
                "/relay.m3u": (200, "audio/x-mpegurl", ('#EXTM3U url-tvg="%s/epg.xml"\n#EXTINF:-1 tvg-id="r.test",Relay\n'
                                                        "#KODIPROP:inputstream.adaptive.stream_headers=Cookie=relay%%3D1\n"
                                                        "%s/stream/1\n" % (lab, lab)).encode()),
            }
            # lane-p1c: what a stream server can answer with, the second round.
            for name, uri in (("imf1", listener(IMF_TCP)), ("imf2", listener(IMF_TLS, "tls")),
                              ("imf3", listener(IMF_LISTEN2, form="listen=2")), ("imf4", listener(IMF_TS)),
                              ("cc1", listener(CC_REL)), ("fc", listener(FORCED))):
                routes["/%s/cpl.xml" % name] = (200, "text/xml", CPL.encode())
                routes["/%s/ASSETMAP.xml" % name] = (200, "text/xml", assetmap(uri).encode())
            routes["/imf4/x.ts"] = (200, "video/mp2t", CPL.encode())
            routes["/cc1/list.ts"] = (200, "video/mp2t", b"ffconcat version 1.0\nfile cpl.xml\n")
            routes["/cc2/list.ts"] = (200, "video/mp2t", ("ffconcat version 1.0\nfile %s\n" % listener(CC_ABS)).encode())
            routes["/fc/list.ts"] = (200, "video/mp2t", b"ffconcat version 1.0\nfile cpl.xml\n")
            routes["/dash/manifest.mpd"] = (200, "application/dash+xml", (
                '<?xml version="1.0" encoding="utf-8"?>\n<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" '
                'profiles="urn:mpeg:dash:profile:isoff-live:2011" type="static" mediaPresentationDuration="PT4.0S" '
                'minBufferTime="PT2.0S">\n<BaseURL>tcp://0.0.0.0:%d?listen=1&amp;listen_timeout=3000/</BaseURL>\n'
                '<Period id="0" start="PT0.0S"><AdaptationSet id="0" contentType="video"><Representation id="0" '
                'mimeType="video/mp4" codecs="avc1.f4000b" bandwidth="100000"><SegmentTemplate timescale="1000" '
                'initialization="init-$RepresentationID$.m4s" media="chunk-$RepresentationID$-$Number$.m4s" '
                'startNumber="1" duration="2000"/></Representation></AdaptationSet></Period></MPD>\n' % DASH_BASE).encode())
            routes["/seg/v.m3u8"] = (200, "application/vnd.apple.mpegurl",
                                     b"#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:4\n#EXT-X-MEDIA-SEQUENCE:0\n"
                                     b"#EXTINF:4.0,\nseg0.ts\n#EXT-X-ENDLIST\n")
            routes["/seg/seg0.ts"] = (200, "video/mp2t", ("v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=x\r\nc=IN IP4 0.0.0.0\r\n"
                                                          "t=0 0\r\nm=video %d RTP/AVP 33\r\n" % SEG_SDP).encode())
            # W23: an HLS stream whose second segment's key does not exist,
            # its URL carrying the secret, the way a provider's key URL does.
            key = "%s/live/rig/%s/key.bin" % (lab, SECRET)
            routes["/ck/v.m3u8"] = (200, "application/vnd.apple.mpegurl", (
                "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:4\n#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:4.0,\nck0.ts\n"
                '#EXT-X-KEY:METHOD=AES-128,URI="%s"\n#EXTINF:4.0,\nck1.ts\n#EXT-X-KEY:METHOD=NONE\n'
                "#EXTINF:4.0,\nck2.ts\n#EXTINF:4.0,\nck3.ts\n#EXT-X-ENDLIST\n" % key).encode())
            routes["/live/rig/%s/key.bin" % SECRET] = (404, "text/plain", b"")
            if path.startswith("/m/"):
                base = os.path.join(www, "m")
                full = os.path.join(base, os.path.normpath(path[3:]).lstrip("/"))
                if os.path.isfile(full) and not os.path.relpath(full, base).startswith(".."):
                    ctype = {".m3u8": "application/vnd.apple.mpegurl", ".mpd": "application/dash+xml",
                             ".vtt": "text/vtt", ".m4s": "video/iso.segment", ".mp4": "video/mp4"}.get(
                                 os.path.splitext(full)[1], "application/octet-stream")
                    with open(full, "rb") as fh:
                        routes[path] = (200, ctype, fh.read())
            if path == "/redir.m3u":
                self.send_response(302)
                self.send_header("Location", "http://127.0.0.1:%d/admin?op=x" % PORTS["plain"])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path in routes:
                status, ctype, body = routes[path]
            else:
                with open(os.path.join(www, "long.ts"), "rb") as fh:
                    status, ctype, body = 200, "video/mp2t", fh.read()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                pass

    class Server(http.server.ThreadingHTTPServer):
        seen = 0
        last = 0.0

        def get_request(self):
            sock, addr = self.socket.accept()
            if not cert:
                return sock, addr
            now = time.monotonic()
            if now - Server.last >= 1.0:
                Server.seen = 0
            Server.last = now
            Server.seen += 1
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            if alt_cert and Server.seen > 1:
                ctx.load_cert_chain(alt_cert, alt_key)
            else:
                ctx.load_cert_chain(cert, key)
            return ctx.wrap_socket(sock, server_side=True), addr

    Server(("127.0.0.1", port), Handler).serve_forever()


def serve_rtsp(port: int, www: str, log: str) -> None:
    """lane-p2a: a fake RTSP server (W27). OPTIONS, DESCRIBE (one MP2T
    track), SETUP, PLAY. A TCP-interleaved SETUP is streamed long.ts in
    RTP/MP2T; a UDP SETUP is answered with the client's ports and nothing is
    sent -- the player binds its RTP/RTCP pair on SETUP whatever follows,
    which is the sink. Every request's method and Transport is logged."""
    import struct
    import threading
    with open(os.path.join(www, "long.ts"), "rb") as fh:
        ts = fh.read()
    lsock = socket.socket()
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind(("127.0.0.1", port))
    lsock.listen(8)

    def client(conn):
        buf, interleaved = b"", False
        conn.settimeout(15)
        try:
            while True:
                while b"\r\n\r\n" not in buf:
                    chunk = conn.recv(4096)
                    if not chunk:
                        return
                    buf += chunk
                head, buf = buf.split(b"\r\n\r\n", 1)
                lines = head.decode("latin-1").split("\r\n")
                method = lines[0].split(" ")[0]
                hdr = {l.split(":", 1)[0].strip().lower(): l.split(":", 1)[1].strip() for l in lines[1:] if ":" in l}
                fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                with os.fdopen(fd, "a") as fh:
                    fh.write(json.dumps({"server": "rtsp", "path": method, "transport": hdr.get("transport", ""),
                                         "secret": False, "header": False, "ua": "", "headers": []}) + "\n")
                extra, body = "", b""
                if method == "OPTIONS":
                    extra = "Public: OPTIONS, DESCRIBE, SETUP, PLAY, TEARDOWN\r\n"
                elif method == "DESCRIBE":
                    body = (b"v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=x\r\nc=IN IP4 0.0.0.0\r\nt=0 0\r\n"
                            b"m=video 0 RTP/AVP 33\r\na=control:track1\r\n")
                    extra = "Content-Type: application/sdp\r\nContent-Base: rtsp://127.0.0.1:%d/live/\r\n" % port
                elif method == "SETUP":
                    tr = hdr.get("transport", "")
                    interleaved = "interleaved" in tr
                    extra = "Session: 4242;timeout=60\r\nTransport: %s\r\n" % (
                        "RTP/AVP/TCP;unicast;interleaved=0-1" if interleaved else tr + ";server_port=47821-47822")
                elif method == "PLAY":
                    extra = "Session: 4242\r\n"
                conn.sendall(("RTSP/1.0 200 OK\r\nCSeq: %s\r\n%sContent-Length: %d\r\n\r\n"
                              % (hdr.get("cseq", "1"), extra, len(body))).encode() + body)
                if method == "PLAY" and interleaved:
                    seq = stamp = 0
                    for off in range(0, len(ts) - 1316, 1316):
                        pkt = struct.pack("!BBHII", 0x80, 33, seq & 0xFFFF, stamp & 0xFFFFFFFF, 0x1234) + ts[off:off + 1316]
                        conn.sendall(b"$" + bytes([0]) + struct.pack("!H", len(pkt)) + pkt)
                        seq, stamp = seq + 1, stamp + 900
                        time.sleep(0.004)
                    return
        except OSError:
            return
        finally:
            conn.close()

    while True:
        conn, _ = lsock.accept()
        threading.Thread(target=client, args=(conn,), daemon=True).start()


# ------------------------------------------------------------------ the rig

def run(argv: list[str], timeout: int = 60, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, **kw)


def no_core() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def journal() -> int:
    out = run(["journalctl", "MESSAGE_ID=" + MID, "-o", "json", "--no-pager"]).stdout
    return len([line for line in out.splitlines() if line.strip()])


def make_rig(work: str) -> dict[str, str]:
    c = os.path.join(work, "certs")
    www = os.path.join(work, "www")
    os.makedirs(c, mode=0o700)
    os.makedirs(www, mode=0o700)
    def ossl(*args):
        done = run(["openssl"] + list(args))
        if done.returncode != 0:
            raise RuntimeError("openssl " + args[0] + ": " + done.stderr.strip()[-200:])
    ossl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", c + "/ca.key", "-out", c + "/ca.pem", "-days", "2",
         "-subj", "/CN=tls pins rig CA", "-addext", "basicConstraints=critical,CA:TRUE",
         "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    for name, san in (("good", "IP:127.0.0.1"), ("name", "DNS:evil.test")):
        ossl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", "%s/%s.key" % (c, name), "-out", "%s/%s.csr" % (c, name),
             "-subj", "/CN=" + san.split(":")[1])
        with open("%s/%s.ext" % (c, name), "w") as fh:
            fh.write("subjectAltName=%s\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n" % san)
        ossl("x509", "-req", "-in", "%s/%s.csr" % (c, name), "-CA", c + "/ca.pem", "-CAkey", c + "/ca.key",
             "-CAcreateserial", "-out", "%s/%s.pem" % (c, name), "-days", "2", "-extfile", "%s/%s.ext" % (c, name))
    ossl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", c + "/evil.key", "-out", c + "/evil.pem", "-days", "2",
         "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1")
    env = dict(os.environ, HOME=work)
    for name, extra in (("seg.ts", ["-t", "4"]), ("long.ts", ["-t", "30"])):
        done = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"] + extra
                   + ["-c:v", "mpeg2video", "-c:a", "mp2", "-f", "mpegts", os.path.join(www, name)], env=env, preexec_fn=no_core)
        if done.returncode != 0:
            raise RuntimeError("ffmpeg: " + done.stderr.strip()[-200:])
    with open(os.path.join(www, "sub.srt"), "w") as fh:
        fh.write("1\n00:00:00,000 --> 00:00:20,000\nhello\n")
    done = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5",
                "-i", os.path.join(www, "sub.srt"), "-t", "20", "-c:v", "mpeg2video", "-c:s", "srt", "-f", "matroska",
                os.path.join(www, "sub.mkv")], env=env, preexec_fn=no_core)
    if done.returncode != 0:
        raise RuntimeError("ffmpeg mkv: " + done.stderr.strip()[-200:])
    # lane-p1c's C4 and C5: a fragmented-MP4 HLS variant under a master that
    # adds a WebVTT rendition, and a DASH presentation, both H.264 + AAC.
    m = os.path.join(www, "m")
    for sub in ("fmp4", "dash"):
        os.makedirs(os.path.join(m, sub), mode=0o700)
    av = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10",
          "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "12", "-c:v", "libx264", "-preset",
          "ultrafast", "-g", "10", "-c:a", "aac"]
    for args, what in ((["-f", "hls", "-hls_time", "2", "-hls_playlist_type", "vod", "-hls_segment_type", "fmp4",
                         "-hls_fmp4_init_filename", "init.mp4", "-hls_segment_filename",
                         os.path.join(m, "fmp4", "s%03d.m4s"), os.path.join(m, "fmp4", "v.m3u8")], "hls"),
                       (["-f", "dash", "-seg_duration", "2", "-init_seg_name", "init-$RepresentationID$.m4s",
                         "-media_seg_name", "chunk-$RepresentationID$-$Number%05d$.m4s",
                         os.path.join(m, "dash", "manifest.mpd")], "dash")):
        done = run(av + args, env=env, preexec_fn=no_core)
        if done.returncode != 0:
            raise RuntimeError("ffmpeg " + what + ": " + done.stderr.strip()[-200:])
    with open(os.path.join(m, "master.m3u8"), "w") as fh:
        fh.write('#EXTM3U\n#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="s",NAME="English",DEFAULT=YES,AUTOSELECT=YES,'
                 'LANGUAGE="en",URI="subs.m3u8"\n#EXT-X-STREAM-INF:BANDWIDTH=300000,SUBTITLES="s"\nfmp4/v.m3u8\n')
    with open(os.path.join(m, "subs.m3u8"), "w") as fh:
        fh.write("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:12\n#EXT-X-MEDIA-SEQUENCE:0\n"
                 "#EXTINF:12.000,\nsub0.vtt\n#EXT-X-ENDLIST\n")
    with open(os.path.join(m, "sub0.vtt"), "w") as fh:
        fh.write("WEBVTT\nX-TIMESTAMP-MAP=MPEGTS:0,LOCAL:00:00:00.000\n\n00:00:00.000 --> 00:00:11.000\nrig line\n")
    return {"certs": c, "www": www}


def start_servers(work: str, rig: dict[str, str]) -> list[subprocess.Popen]:
    c = rig["certs"]
    log = os.path.join(work, "requests.log")
    open(log, "w").close()
    os.chmod(log, 0o600)
    specs = {
        "provider": (c + "/good.pem", c + "/good.key", "", "", "https://127.0.0.1:%d/seg.ts" % PORTS["attacker"]),
        "attacker": (c + "/evil.pem", c + "/evil.key", "", "", ""),
        "hlsok": (c + "/good.pem", c + "/good.key", "", "", "https://127.0.0.1:%d/seg.ts" % PORTS["hlsok"]),
        "alt": (c + "/good.pem", c + "/good.key", c + "/name.pem", c + "/name.key", "https://127.0.0.1:%d/seg.ts" % PORTS["alt"]),
        "plain": ("", "", "", "", ""),
        "lab": ("", "", "", "", ""),
    }
    procs = [subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "--serve-rtsp", str(PORTS["rtsp"]),
                               rig["www"], log], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)]
    for name, (cert, key, acert, akey, seg) in specs.items():
        procs.append(subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "--serve", name, str(PORTS[name]),
                                       rig["www"], log, cert, key, acert, akey, seg],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        up = 0
        for port in PORTS.values():
            with socket.socket() as s:
                s.settimeout(0.2)
                up += s.connect_ex(("127.0.0.1", port)) == 0
        if up == len(PORTS):
            break
        time.sleep(0.1)
    return procs


def requests(work: str) -> list[dict]:
    with open(os.path.join(work, "requests.log")) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_helper(tree: str) -> dict:
    stub = os.path.join(tree, "bin", "omarchy-iptv")
    ns = {"__name__": "tls_pins_rig_helper", "__file__": stub}
    with open(stub, "rb") as fh:
        exec(compile(fh.read(), stub, "exec", dont_inherit=True), ns)
    return ns


def kids_with_secret(pid: int) -> list[str]:
    out, frontier, seen = [], [pid], set()
    while frontier:
        p = frontier.pop()
        if p in seen:
            continue
        seen.add(p)
        try:
            tids = os.listdir("/proc/%d/task" % p)
        except OSError:
            continue
        for tid in tids:
            try:
                children = open("/proc/%d/task/%s/children" % (p, tid)).read().split()
            except OSError:
                continue
            for k in children:
                frontier.append(int(k))
                try:
                    if SECRET in open("/proc/%s/cmdline" % k, "rb").read().decode("utf-8", "replace"):
                        out.append(open("/proc/%s/comm" % k).read().strip())
                except OSError:
                    pass
    return out


def listening(pid: int) -> list[str]:
    """The inet sockets mpv itself holds open for anyone to send to (ss's
    listening TCP and unconnected UDP rows owned by this pid)."""
    out = run(["ss", "-Hlunp"]).stdout + run(["ss", "-Hltnp"]).stdout
    return sorted({line.split()[3] for line in out.splitlines() if "pid=%d," % pid in line})


def probe(work: str, case: str, argv_ns: dict, logic_ns: dict, url: str, user=(), raw=(), conf="",
          seconds=5.0, post=(), migrate=False, watch=(), inputconf="", first_url="", headers=None,
          drawwatch=False) -> dict:
    base = os.path.join(work, "cases", case)
    for sub in ("home", "cache", "state", "config/mpv", "data", "run/omarchy-iptv"):
        os.makedirs(os.path.join(base, sub), mode=0o700, exist_ok=True)
    with open(os.path.join(base, "config", "mpv", "mpv.conf"), "w") as fh:
        fh.write(conf)
    with open(os.path.join(base, "config", "mpv", "input.conf"), "w") as fh:
        fh.write(inputconf)
    env = {k: v for k, v in os.environ.items()
           if k not in ("DISPLAY", "WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE", "DBUS_SESSION_BUS_ADDRESS", "MPV_HOME")}
    env.update(HOME=base + "/home", XDG_CACHE_HOME=base + "/cache", XDG_STATE_HOME=base + "/state",
               XDG_CONFIG_HOME=base + "/config", XDG_DATA_HOME=base + "/data", XDG_RUNTIME_DIR=base + "/run")
    runtime = os.path.join(base, "run", "omarchy-iptv")
    kept, rejected = argv_ns["filter_mpv_args"](list(user))
    dirs = argv_ns["player_dirs"](os.path.join(runtime, "mpv.sock"), os.path.join(base, "state", "omarchy-iptv"))
    argv = argv_ns["mpv_launch_argv"]("mpv.sock", kept + list(raw), dirs)
    cmd = ["mpv", "--config-dir=" + base + "/config/mpv", "--vo=null", "--ao=null"] + [a for a in argv[1:] if not a.startswith("--force-window")]
    before = len(requests(work))
    jb = journal()
    old = os.getcwd()
    os.chdir(runtime)
    err = open(os.path.join(base, "mpv.stderr"), "wb")
    player = subprocess.Popen(cmd, cwd=runtime, env=env, stdin=subprocess.DEVNULL, stdout=err, stderr=err, preexec_fn=no_core)
    result = {"case": case, "rejected": rejected, "applied": None, "timePos": None, "props": {}, "kids": [], "post": [],
              "listening": [], "ends": [], "drawn": [], "errlines": []}
    watcher = None
    try:
        client = logic_ns["wait_for_socket"]("mpv.sock", 8.0, 3.0)
        if client is None:
            result["error"] = "no socket"
        else:
            if drawwatch:
                # lane-p1c, W23: a second client at mpv's TRACE level sees
                # every command a script runs to draw -- `show-text`, an OSD
                # overlay, a line handed to the console -- with its text.
                watcher = logic_ns["MpvIpc"]("mpv.sock", 3.0)
                watcher.connect()
                watcher.try_command("request_log_messages", "trace")
            if migrate:
                result["migrate"] = logic_ns["migrate_tls"](client)
                if "pin_adopted_player" in logic_ns:
                    logic_ns["pin_adopted_player"](client, os.path.join(runtime, "mpv.sock"))
            try:
                client.try_command("request_log_messages", "error")
                if first_url:
                    # The channel the player was playing when it was adopted:
                    # loaded by the tree that LAUNCHED it (argv_ns), as the
                    # shell before the upgrade loaded it.
                    argv_ns["apply_channel"](client, {"id": "", "url": first_url, "name": "Rig First",
                                                       "headers": {HEADER: HEADER_VALUE}, "group": ""})
                    time.sleep(1.5)
                logic_ns["apply_channel"](client, {"id": "", "url": url, "name": "Rig Channel",
                                                    "headers": dict(headers) if headers is not None else {HEADER: HEADER_VALUE},
                                                    "group": ""})
                result["applied"] = True
            except logic_ns["HelperError"] as error:
                result["applied"] = False
                result["refusal"] = getattr(error, "code", "")
            started = time.monotonic()
            pending = list(post)
            while time.monotonic() - started < seconds and player.poll() is None:
                try:
                    ok, pos = client.try_command("get_property", "time-pos")
                    if ok and isinstance(pos, (int, float)):
                        result["timePos"] = pos
                    for prop in watch:
                        ok, value = client.try_command("get_property", prop)
                        if ok:
                            result["props"][prop] = value
                    for sock in listening(player.pid):
                        if sock not in result["listening"]:
                            result["listening"].append(sock)
                except logic_ns["HelperError"]:
                    break
                while pending and time.monotonic() - started >= pending[0][0]:
                    reply = client.request(pending.pop(0)[1], allow_close=True)
                    result["post"].append(reply.get("error"))
                    time.sleep(1.0)
                    result["kids"] += kids_with_secret(player.pid)
                if watcher is not None:
                    drain_draws(watcher, result)
                time.sleep(0.25)
            # The end-file of a load that failed arrives with nothing waiting
            # for it, and under --idle=once just before the connection
            # closes: read what is buffered, bounded, before judging.
            seen_events, client.events = list(client.events), []
            for _ in range(50):
                try:
                    batch = client.drain_events(time.monotonic() + 0.2)
                except Exception:
                    break
                if not batch:
                    break
                seen_events += batch
            for event in seen_events:
                if event.get("event") == "end-file":
                    result["ends"].append(str(event.get("file_error") or event.get("reason") or ""))
                elif event.get("event") == "log-message" and event.get("level") in ("error", "fatal"):
                    result["errlines"].append(str(event.get("text") or ""))
            if watcher is not None:
                drain_draws(watcher, result)
                watcher.close()
            try:
                client.request(["quit"], allow_close=True)
            except Exception:
                pass
            client.close()
    finally:
        os.chdir(old)
        try:
            player.wait(timeout=8)
        except subprocess.TimeoutExpired:
            player.kill()
            player.wait(timeout=5)
        err.close()
    time.sleep(0.3)
    result["requests"] = requests(work)[before:]
    leaks = []
    for top in ("home", "cache", "state", "data"):
        for dirpath, _, names in os.walk(os.path.join(base, top)):
            for n in names:
                p = os.path.join(dirpath, n)
                if os.path.isfile(p) and not os.path.islink(p):
                    with open(p, "rb") as fh:
                        if SECRET.encode() in fh.read(4 << 20):
                            leaks.append(os.path.relpath(p, base))
    result["leaks"] = leaks
    result["journal"] = [jb, journal()]
    return result


def drain_draws(watcher, result: dict) -> None:
    """What the player was told to DRAW, from the trace-level client: an OSD
    message (`show-text`), an OSD overlay, or a line handed to the console
    (`script-message-to console log`). Only whether each carries the secret
    is kept, and how many there were."""
    deadline = time.monotonic() + 0.1
    while True:
        try:
            batch = watcher.drain_events(deadline)
        except Exception:
            return
        if not batch:
            return
        for event in batch:
            text = str(event.get("text") or "") if event.get("event") == "log-message" else ""
            if text.startswith("Run command:") and any(k in text for k in ("show-text", "osd-overlay",
                                                                            "script-message-to")):
                result["draws"] = result.get("draws", 0) + 1
                if SECRET in text:
                    result["drawn"].append(text[13:40])


def helper_verb(tree_dir: str, work: str, case: str, verb: str, url: str, env_extra: dict) -> tuple[int, dict]:
    """The tree's helper as a SUBPROCESS, the way the shell runs it: the URL
    in OMARCHY_IPTV_URL, a private cache folder. -> (exit code, reply)."""
    cache = os.path.join(work, "cases", case, "cache-" + verb)
    os.makedirs(cache, mode=0o700, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}
    env.update({"OMARCHY_IPTV_URL": url}, **env_extra)
    done = run([sys.executable, os.path.join(tree_dir, "bin", "omarchy-iptv"), verb, "--cache-dir", cache, "--timeout", "5"],
               env=env)
    lines = [line for line in done.stdout.strip().splitlines() if line.strip()]
    return done.returncode, (json.loads(lines[-1]) if lines else {})


def lab_headers(result: dict, path: str) -> list[list[list[str]]]:
    return [r.get("headers", []) for r in result["requests"] if r["server"] == "lab" and r["path"] == path]


def got(result: dict, server: str) -> int:
    return len([r for r in result["requests"] if r["server"] == server])


def main(argv: list[str]) -> int:
    if argv[:1] == ["--serve"]:
        serve(argv[1], int(argv[2]), argv[3], argv[4], argv[5], argv[6], argv[7], argv[8], argv[9])
        return 0
    if argv[:1] == ["--serve-rtsp"]:
        serve_rtsp(int(argv[1]), argv[2], argv[3])
        return 0
    opts = {"--tree": "", "--pre-pin": "", "--work": ""}
    i = 0
    while i < len(argv):
        if argv[i] not in opts or i + 1 >= len(argv):
            print("usage: tls_pins_rig.py --tree DIR [--pre-pin DIR] --work DIR")
            return 2
        opts[argv[i]] = argv[i + 1]
        i += 2
    if os.environ.get("OMARCHY_IPTV_RIG_NETNS") == "1":
        # tls-scenario.sh ran this inside `unshare -rn`: a namespace whose
        # only interface is a loopback that starts down.
        run(["ip", "link", "set", "lo", "up"])
    for tool in ("mpv", "ffmpeg", "openssl", "journalctl", "ss"):
        if not shutil.which(tool):
            print("SKIP tls windowless: %s is not on PATH" % tool)
            return 77
    for name, port in PORTS.items():
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                print("REFUSING: port %d (%s) is already in use" % (port, name))
                return 2
    work = opts["--work"]
    tree = load_helper(opts["--tree"])
    pre = load_helper(opts["--pre-pin"]) if opts["--pre-pin"] else None
    rig = make_rig(work)
    ca = "--tls-ca-file=" + rig["certs"] + "/ca.pem"
    procs = start_servers(work, rig)
    passed = failed = 0
    j0 = journal()

    def check(label: str, ok: bool, detail: str) -> None:
        nonlocal passed, failed
        if ok:
            passed += 1
            print("PASS %s (%s)" % (label, detail))
        else:
            failed += 1
            print("FAIL %s (%s)" % (label, detail))

    try:
        p, a = "https://127.0.0.1:%d" % PORTS["provider"], "https://127.0.0.1:%d" % PORTS["attacker"]
        hls = p + "/live/rig/%s/live.m3u8" % SECRET
        direct_evil = a + "/live/rig/%s/seg.ts" % SECRET
        r = run(["openssl", "verify", "-CAfile", rig["certs"] + "/ca.pem", rig["certs"] + "/good.pem", rig["certs"] + "/evil.pem"])
        check("G1 the rig discriminates: the provider's certificate verifies against the CA, the attacker's does not",
              "good.pem: OK" in r.stdout and "evil.pem: OK" not in r.stdout, "openssl verify")
        r = probe(work, "W1", tree, tree, hls, user=[ca, "--demuxer-lavf-o=tls_verify=0"])
        check("W1 --demuxer-lavf-o=tls_verify=0 in mpvArgs: refused, and the attacker gets nothing",
              r["rejected"] == ["--demuxer-lavf-o=tls_verify=0"] and got(r, "attacker") == 0,
              "rejected %d token(s), attacker requests %d" % (len(r["rejected"]), got(r, "attacker")))
        r = probe(work, "W2", tree, tree, hls, user=[ca], raw=["--demuxer-lavf-o=tls_verify=0,live_start_index=-1"])
        check("W2 the same key past the filter: the attacker gets nothing", got(r, "attacker") == 0,
              "attacker requests %d, applied %s" % (got(r, "attacker"), r["applied"]))
        time.sleep(1.5)
        r = probe(work, "W3", tree, tree, "https://127.0.0.1:%d/live/rig/%s/live.m3u8" % (PORTS["alt"], SECRET),
                  user=[ca], raw=["--demuxer-lavf-o=verifyhost=evil.test"])
        check("W3 verifyhost=<the attacker's own name> past the filter: the reopen is refused",
              got(r, "alt") <= 1 and r["timePos"] is None, "alt requests %d, played %s" % (got(r, "alt"), r["timePos"] is not None))
        time.sleep(1.5)
        r = probe(work, "W4", tree, tree, direct_evil, conf="[protocol.https]\nstream-lavf-o=tls_verify=0\n")
        check("W4 [protocol.https] stream-lavf-o=tls_verify=0 in mpv.conf: the attacker gets nothing",
              got(r, "attacker") == 0, "attacker requests %d" % got(r, "attacker"))
        r = probe(work, "W5", tree, tree, hls, user=[ca], conf="[protocol.https]\ndemuxer-lavf-o=tls_verify=0\n")
        check("W5 [protocol.https] demuxer-lavf-o=tls_verify=0 on HLS: the attacker gets nothing",
              got(r, "attacker") == 0, "attacker requests %d" % got(r, "attacker"))
        r = probe(work, "W6", tree, tree, direct_evil, conf="[rigauto]\nprofile-cond=p.path ~= nil\ntls-verify=no\n")
        check("W6 a profile-cond profile with tls-verify=no: the attacker gets nothing",
              got(r, "attacker") == 0, "attacker requests %d" % got(r, "attacker"))
        plain = "http://127.0.0.1:%d/live/rig/%s/long.ts" % (PORTS["plain"], SECRET)
        r = probe(work, "W7", tree, tree, plain, conf="save-watch-history=yes\n", seconds=3)
        check("W7 save-watch-history=yes in mpv.conf: no file outside the runtime folder holds the credential",
              r["leaks"] == [] and r["timePos"] is not None, "files %s, played %s" % (r["leaks"], r["timePos"] is not None))
        r = probe(work, "W8", tree, tree, "http://127.0.0.1:%d/live/rig/%s/sub.mkv" % (PORTS["plain"], SECRET), seconds=7,
                  post=[[1.5, ["set_property", "sid", 1]], [2.5, ["script-binding", "select/select-subtitle-line"]]])
        check("W8 select's subtitle-line binding: no child of the player carries the credential",
              r["kids"] == [], "children with it: %s" % r["kids"])
        marker = os.path.join(work, "marker.lua")
        with open(marker, "w") as fh:
            fh.write('local h = os.getenv("HOME")\n'
                     'mp.register_event("file-loaded", function()\n'
                     '  local f = io.open(h .. "/marker.txt", "a"); f:write((mp.get_property("path") or "") .. "\\n"); f:close()\n'
                     'end)\n')
        home10 = os.path.join(work, "cases", "W10", "home")
        r = probe(work, "W10", tree, tree, "http://127.0.0.1:%d/live/rig/%s/sub.mkv" % (PORTS["plain"], SECRET), seconds=7,
                  conf=("player-operation-mode=pseudo-gui\n[pseudo-gui]\nsave-watch-history=yes\nload-select=yes\n"
                        "script=%s\nwrite-filename-in-watch-later-config=yes\nwatch-later-dir=%s/wl\n" % (marker, home10)),
                  post=[[1.5, ["set_property", "sid", 1]], [2.0, ["script-binding", "select/select-subtitle-line"]],
                        [2.5, ["write-watch-later-config"]]])
        check("W10 a [pseudo-gui] profile switched on by a plain mpv.conf line: nothing outside the runtime folder holds the credential, no child carries it",
              r["leaks"] == [] and r["kids"] == [] and r["timePos"] is not None,
              "files %s, children %s, played %s" % (r["leaks"], r["kids"], r["timePos"] is not None))
        if pre is not None:
            r = probe(work, "W9", pre, tree, direct_evil, conf="[protocol.https]\nstream-lavf-o=tls_verify=0\n", migrate=True)
            check("W9 an adopted pre-pin player with that profile: the load is refused and the attacker gets nothing",
                  r["applied"] is False and got(r, "attacker") == 0,
                  "applied %s, attacker requests %d" % (r["applied"], got(r, "attacker")))
        lab = "http://127.0.0.1:%d" % PORTS["lab"]
        if os.environ.get("OMARCHY_IPTV_RIG_NETNS") != "1":
            # A baseline player LISTENS here, on every interface it has: only
            # in a namespace of its own is that nobody's but the rig's.
            print("SKIP W11 W12: they need unshare -rn (tls-scenario.sh --windowless runs the rig in it where it can)")
        else:
            r = probe(work, "W11", tree, tree, lab + "/nest.m3u", seconds=4,
                      post=[[1.5, ["playlist-next"]], [2.5, ["playlist-next"]]])
            check("W11 a server that answers with a plain playlist: no entry is fetched, nothing listens, the load ends unrecognized",
                  lab_headers(r, "/inner.ts") == [] and r["listening"] == [] and "unrecognized file format" in r["ends"],
                  "inner fetched %d, listening %s, ends %s" % (len(lab_headers(r, "/inner.ts")), r["listening"], r["ends"]))
            r1 = probe(work, "W12a", tree, tree, lab + "/x.sdp", seconds=3)
            r2 = probe(work, "W12b", tree, tree, lab + "/x.ts", seconds=3)
            check("W12 a server that answers with an SDP body, under .sdp and under .ts: nothing listens",
                  r1["listening"] == [] and r2["listening"] == [] and lab_headers(r1, "/x.sdp") != [] and lab_headers(r2, "/x.ts") != [],
                  "listening %s / %s" % (r1["listening"], r2["listening"]))
        hard = {"X-Hard": HARD_VALUE, "X-Two": "1,2", "User-Agent": "UA, x=y \"z\"", "Referer": "http://r.test/a,b"}
        r = probe(work, "W13", tree, tree, lab + "/hdr.ts", seconds=2, headers=hard)
        seen = lab_headers(r, "/hdr.ts")[:1]
        mine = [[k, v] for k, v in (seen[0] if seen else []) if k.lower() in ("x-hard", "x-two", "user-agent", "referer")]
        check("W13 headers with commas, =, quotes and backslashes each arrive as ONE header, verbatim",
              sorted(mine) == sorted([["X-Hard", HARD_VALUE], ["X-Two", "1,2"], ["User-Agent", hard["User-Agent"]],
                                      ["Referer", hard["Referer"]]]), "got %s" % mine)
        r = probe(work, "W14", tree, tree, lab + "/chan.ts", seconds=4,
                  post=[[1.5, ["loadfile", lab + "/pasted.ts", "append-play"]], [2.0, ["playlist-next"]]])
        pasted = lab_headers(r, "/pasted.ts")
        check("W14 an entry the helper did not load: the channel's provider header does not reach it",
              pasted != [] and not any(HEADER_VALUE in json.dumps(h) for h in pasted)
              and any(HEADER_VALUE in json.dumps(h) for h in lab_headers(r, "/chan.ts")),
              "pasted requests %d, with the header %d" % (len(pasted), sum(HEADER_VALUE in json.dumps(h) for h in pasted)))
        r = probe(work, "W15", tree, tree, lab + "/chan2.ts", seconds=4,
                  inputconf="ctrl+v loadfile %s/pasted2.ts append-play\n" % lab,
                  # append-play only appends while a channel plays; the next
                  # entry is what fetches it.
                  post=[[1.5, ["keypress", "ctrl+v"]], [2.0, ["playlist-next"]]])
        check("W15 the paste-to-playlist key appends nothing", lab_headers(r, "/pasted2.ts") == [],
              "pasted requests %d" % len(lab_headers(r, "/pasted2.ts")))
        before = len(requests(work))
        code, reply = helper_verb(opts["--tree"], work, "W16", "playlist", lab + "/redir.m3u", {"OMARCHY_IPTV_ORIGIN": "user"})
        admin = [x for x in requests(work)[before:] if x["server"] == "plain" and x["path"] == "/admin"]
        check("W16 a typed loopback source redirected to another port of the same address: refused, never contacted",
              code == 1 and (reply.get("error") or {}).get("code") == "local_address" and admin == [],
              "exit %d, code %s, the other port got %d" % (code, (reply.get("error") or {}).get("code"), len(admin)))
        if pre is not None:
            r = probe(work, "W17", pre, tree, hls, user=[ca, "--demuxer-lavf-o=tls_verify=0"], conf="reset-on-next-file=all\n",
                      first_url="http://127.0.0.1:%d/live/rig/%s/long.ts" % (PORTS["plain"], SECRET), seconds=5)
            check("W17 an adopted pre-pin player with reset-on-next-file=all: the next load is refused, the attacker gets nothing",
                  r["applied"] is False and got(r, "attacker") == 0,
                  "attacker requests %d, applied %s" % (got(r, "attacker"), r["applied"]))
            r = probe(work, "W18", pre, tree, "http://127.0.0.1:%d/live/rig/%s/long.ts" % (PORTS["plain"], SECRET),
                      conf="[protocol.http]\nsave-watch-history=yes\n", migrate=True, seconds=3)
            check("W18 an adopted pre-pin player whose per-file profile sets a non-TLS pin: refused, nothing written",
                  r["applied"] is False and r["leaks"] == [], "applied %s, files %s" % (r["applied"], r["leaks"]))
        # ---- lane-p1c (2026-10-29): D-SINK-62..64, D-SINK-61, and the
        # kinds the format list keeps.
        if os.environ.get("OMARCHY_IPTV_RIG_NETNS") != "1":
            print("SKIP W19 W20 W21 W24 W25: they need unshare -rn (a baseline player would listen on this machine)")
        else:
            imf = [probe(work, "W19" + tag, tree, tree, lab + leaf, seconds=4)
                   for tag, leaf in (("a", "/imf1/cpl.xml"), ("b", "/imf2/cpl.xml"), ("c", "/imf3/cpl.xml"),
                                     ("d", "/imf4/x.ts"))]
            maps = sum(len([x for x in r["requests"] if x["path"].endswith("/ASSETMAP.xml")]) for r in imf)
            check("W19 a server that answers with an IMF composition playlist (tcp, tls and listen=2 assets, and as .ts): nothing listens, no ASSETMAP is fetched",
                  all(r["listening"] == [] for r in imf) and maps == 0,
                  "listening %s, ASSETMAP fetched %d" % ([r["listening"] for r in imf], maps))
            rel = probe(work, "W20a", tree, tree, lab + "/cc1/list.ts", seconds=4)
            unsafe = probe(work, "W20b", tree, tree, lab + "/cc2/list.ts", raw=["--demuxer-lavf-o=safe=0"], seconds=4)
            check("W20 an ffconcat file naming the CPL, and one naming a tcp listener under the user's safe=0: nothing listens",
                  rel["listening"] == [] and unsafe["listening"] == [],
                  "listening %s / %s" % (rel["listening"], unsafe["listening"]))
            r = probe(work, "W21", tree, tree, lab + "/dash/manifest.mpd", seconds=3)
            check("W21 a DASH manifest whose BaseURL is a tcp listener: nothing listens", r["listening"] == [],
                  "listening %s" % r["listening"])
            esc = '--demuxer-lavf-o=extension_picky=0,seg_format_options="format\\_whitelist=sdp:protocol\\_whitelist=rtp,udp"'
            told = probe(work, "W24a", tree, tree, lab + "/seg/v.m3u8", user=[esc], seconds=3)
            past = probe(work, "W24b", tree, tree, lab + "/seg/v.m3u8", raw=[esc], seconds=3)
            check("W24 the hls segment demuxer's options, escaped past every word: refused as a token, and past the filter nothing listens",
                  told["rejected"] == [esc] and told["listening"] == [] and past["listening"] == [],
                  "rejected %d, listening %s / %s" % (len(told["rejected"]), told["listening"], past["listening"]))
            r = probe(work, "W25", tree, tree, lab + "/fc/list.ts", raw=["--demuxer-lavf-format=concat"], seconds=4)
            check("W25 a forced --demuxer-lavf-format=concat over an ffconcat file naming the CPL: nothing listens",
                  r["listening"] == [], "listening %s" % r["listening"])
        told = probe(work, "W22a", tree, tree, lab + "/pre/chan.ts", user=["--prefetch-playlist=yes"], seconds=5,
                     post=[[0.3, ["loadfile", lab + "/pre/next-a.ts", "append"]], [3.5, ["playlist-next"]]])
        past = probe(work, "W22b", tree, tree, lab + "/pre/chan.ts", raw=["--prefetch-playlist=yes"], seconds=5,
                     post=[[0.3, ["loadfile", lab + "/pre/next-b.ts", "append"]], [3.5, ["playlist-next"]]])
        conf = probe(work, "W22c", tree, tree, lab + "/pre/chan.ts", conf="prefetch-playlist=yes\n", seconds=5,
                     post=[[0.3, ["loadfile", lab + "/pre/next-c.ts", "append"]], [3.5, ["playlist-next"]]])
        # The appended entry is fetched one way or the other: prefetched while
        # the channel's per-file options are live, or at the playlist-next.
        nexts = [lab_headers(r, "/pre/next-%s.ts" % leaf) for r, leaf in ((told, "a"), (past, "b"), (conf, "c"))]
        leaked = [h for got in nexts for h in got if HEADER_VALUE in json.dumps(h)]
        check("W22 prefetch-playlist on by token, past the filter and from mpv.conf: refused as a token, and an appended entry gets no provider header",
              told["rejected"] == ["--prefetch-playlist=yes"] and leaked == [] and all(got != [] for got in nexts)
              and any(HEADER_VALUE in json.dumps(h) for h in lab_headers(past, "/pre/chan.ts")),
              "rejected %d, appended entry fetched %s, with the header %d" % (
                  len(told["rejected"]), [len(got) for got in nexts], len(leaked)))
        r = probe(work, "W23", tree, tree, lab + "/ck/v.m3u8", raw=["--video-osd=no"], seconds=7, drawwatch=True,
                  post=[[4.5, ["keypress", "`"]], [5.0, ["script-binding", "console/enable"]],
                        [5.5, ["script-binding", "commands/open"]]], watch=("load-console",))
        told = [line for line in r["errlines"] if SECRET in line]
        redacted = [tree["redact_urls"](line) for line in told]
        check("W23 the console draws nothing of a key URL logged at error level; the line still reaches an error-level client, and redacts",
              r["drawn"] == [] and told != [] and not any(SECRET in line for line in redacted)
              and r["props"].get("load-console") is False,
              "drawn with the secret %d of %d, error lines with it %d, console loaded %s" % (
                  len(r["drawn"]), r.get("draws", 0), len(told), r["props"].get("load-console")))
        # ---- lane-p2a (2026-10-29): D-SINK-67, D-SINK-65, D-SINK-68.
        bare = lab + "/live/rig/%s/" % SECRET            # an empty last segment: `filename` is the whole URL
        stats_post = [[2.0, ["keypress", "i"]], [2.6, ["keypress", "I"]],
                      [3.2, ["script-binding", "stats/display-stats-toggle"]],
                      [3.8, ["script-binding", "stats/display-page-5"]]]
        own = probe(work, "W26a", tree, tree, bare, raw=["--video-osd=no"], seconds=6, drawwatch=True,
                    post=stats_post, watch=("load-stats-overlay", "filename"))
        stats = [own]
        if pre is not None:
            stats.append(probe(work, "W26b", pre, tree, bare, raw=["--video-osd=no"], seconds=6, drawwatch=True,
                               post=stats_post, migrate=True, watch=("load-stats-overlay", "filename")))
        check("W26 the stats overlay draws nothing of a URL whose `filename` is the whole of it: i, I, the toggle and page 5 (the OSC title's left click); the bindings are refused and the option reads off -- on this tree's player and on an adopted pre-pin one",
              all(r["drawn"] == [] and SECRET in str(r["props"].get("filename", "")) and r["timePos"] is not None
                  and r["props"].get("load-stats-overlay") is False and r["post"][2:] == ["error running command"] * 2
                  for r in stats),
              "; ".join("%s: drawn with the secret %d of %d, filename carries it %s, bindings %s, option %s" % (
                  r["case"], len(r["drawn"]), r.get("draws", 0), SECRET in str(r["props"].get("filename", "")),
                  r["post"][2:], r["props"].get("load-stats-overlay")) for r in stats))
        if os.environ.get("OMARCHY_IPTV_RIG_NETNS") != "1":
            print("SKIP W27: it needs unshare -rn (an rtsp channel over udp binds on every interface)")
        else:
            rtsp = "rtsp://127.0.0.1:%d/live/x" % PORTS["rtsp"]
            spellings = ["--demuxer-lavf-o=rtsp_transport=udp", "--demuxer-lavf-o=rtsp_transport=1",
                         "--demuxer-lavf-o=rtsp_transport=0x1", "--demuxer-lavf-o=rtsp_transport=+udp",
                         "--demuxer-lavf-o=rtsp_transport=-tcp", "--demuxer-lavf-o=rtsp_transport=0",
                         "--demuxer-lavf-o=rtsp_transport=udp+tcp", '--demuxer-lavf-o=rtsp_transport="udp"',
                         "--demuxer-lavf-o=rtsp_transport=udp_multicast", "--demuxer-lavf-o-append=rtsp_transport=udp",
                         "--demuxer-lavf-o-set=rtsp_transport=udp", "--demuxer-lavf-o=live_start_index=-1,rtsp_transport=udp",
                         "--demuxer-lavf-o=rtsp_transport=tcp,rtsp_transport=udp", "--demuxer-lavf-o=rtsp_flags=prefer_tcp",
                         "--demuxer-lavf-o=rtsp_flags=2", "--demuxer-lavf-o=rtsp_flags=+filter_src",
                         "--demuxer-lavf-o=rtsp_transport=tcp", "--demuxer-lavf-o=rtsp_transport=http",
                         "--demuxer-lavf-o=rtsp_transport=tcp+http"]
            rows = []
            for i, token in enumerate(spellings):
                r = probe(work, "W27-%02d" % i, tree, tree, rtsp, raw=[token], seconds=3)
                rows.append((token, r["listening"], tree["mpv_arg_warnings"]([token])))
            control = probe(work, "W27-none", tree, tree, rtsp, seconds=3)
            bound = [row for row in rows if row[1]]
            untold = [row[0] for row in bound if not row[2]]
            for token, sockets, told in rows:
                print("   W27 %-62s binds %-3s warned %s" % (token, "yes" if sockets else "no", "yes" if told else "no"))
            check("W27 every --demuxer-lavf-o spelling that makes an rtsp channel bind its RTP/RTCP pair is warned, and the channel with no token binds nothing",
                  bound != [] and untold == [] and control["listening"] == [],
                  "%d of %d spellings bind, %d of them unwarned %s; no token: listening %s" % (
                      len(bound), len(rows), len(untold), untold, control["listening"]))
        if pre is not None:
            off = probe(work, "W28a", pre, tree, hls, user=[ca], conf="demuxer-lavf-propagate-opts=no\n", migrate=True,
                        seconds=5, watch=("demuxer-lavf-propagate-opts",))
            ctl = probe(work, "W28b", pre, pre, hls, user=[ca], raw=["--demuxer-lavf-o=tls_verify=0"], seconds=5)
            check("W28 an adopted pre-pin player whose plain mpv.conf turns propagation off: the attacker's HLS segment gets nothing (control: the pre-pin tree's own load with tls_verify=0 reaches it)",
                  off["props"].get("demuxer-lavf-propagate-opts") is False and got(off, "attacker") == 0 and got(ctl, "attacker") > 0,
                  "propagate %s, attacker requests %d; control %d" % (off["props"].get("demuxer-lavf-propagate-opts"),
                                                                      got(off, "attacker"), got(ctl, "attacker")))
        r = probe(work, "C4", tree, tree, lab + "/m/master.m3u8", seconds=5, watch=("track-list", "file-format"))
        tracks = sorted((t.get("type"), t.get("codec")) for t in (r["props"].get("track-list") or []))
        check("C4 a fragmented-MP4 HLS channel with a WebVTT rendition plays, its subtitle track there (control)",
              r["timePos"] is not None and r["props"].get("file-format") == "hls"
              and tracks == [("audio", "aac"), ("sub", "webvtt"), ("video", "h264")],
              "played %s as %s, tracks %s" % (r["timePos"] is not None, r["props"].get("file-format"), tracks))
        r = probe(work, "C5", tree, tree, lab + "/m/dash/manifest.mpd", seconds=5, watch=("file-format",))
        check("C5 a DASH channel plays (control)", r["timePos"] is not None and r["props"].get("file-format") == "dash",
              "played %s as %s" % (r["timePos"] is not None, r["props"].get("file-format")))
        code, reply = helper_verb(opts["--tree"], work, "C3", "playlist", lab + "/relay.m3u", {"OMARCHY_IPTV_ORIGIN": "user"})
        cache = os.path.join(work, "cases", "C3", "cache-playlist", "channels.json")
        channels = json.load(open(cache)) if os.path.isfile(cache) else {}
        kept = [c.get("headers") for c in channels.get("channels", [])]
        ecode, ereply = helper_verb(opts["--tree"], work, "C3", "epg", lab + "/epg.xml",
                                    {"OMARCHY_IPTV_ORIGIN": "playlist", "OMARCHY_IPTV_PLAYLIST_HOST": "127.0.0.1",
                                     "OMARCHY_IPTV_PLAYLIST_CLASS": "loopback", "OMARCHY_IPTV_PLAYLIST_PORT": str(PORTS["lab"])})
        r = probe(work, "C3", tree, tree, lab + "/stream/1", seconds=3, headers={"Cookie": "relay=1"})
        check("C3 a loopback relay on one port: its sign-in header is kept, its guide on that port fetched, its channel plays with it (control)",
              code == 0 and kept == [{"Cookie": "relay=1"}] and ecode == 0 and r["timePos"] is not None
              and any("relay=1" in json.dumps(h) for h in lab_headers(r, "/stream/1")),
              "playlist exit %d, headers %s, guide exit %d, played %s" % (code, kept, ecode, r["timePos"] is not None))
        r = probe(work, "C1", tree, tree, p + "/live/rig/%s/long.ts" % SECRET, seconds=4,
                  user=["--hwdec=auto-safe", "--profile=low-latency", "--cache-secs=30", "--volume=50", ca],
                  watch=("volume", "cache-secs"))
        check("C1 a common harmless set is kept and plays (control)",
              r["rejected"] == [] and r["timePos"] is not None and r["props"].get("volume") == 50.0,
              "rejected %d, played %s, volume %s" % (len(r["rejected"]), r["timePos"] is not None, r["props"].get("volume")))
        r = probe(work, "C2", tree, tree, "https://127.0.0.1:%d/live/rig/%s/live.m3u8" % (PORTS["hlsok"], SECRET), seconds=5,
                  user=[ca, "--demuxer-lavf-o=live_start_index=-1"], watch=("demuxer-lavf-o",))
        check("C2 a CA-signed HLS channel with a demuxer workaround plays and keeps the key (control)",
              r["timePos"] is not None and (r["props"].get("demuxer-lavf-o") or {}).get("live_start_index") == "-1",
              "played %s" % (r["timePos"] is not None))
    finally:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
    j1 = journal()
    check("the crash journal did not move", j1 == j0, "%d before, %d after" % (j0, j1))
    print("tls windowless: %d passed, %d failed" % (passed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
