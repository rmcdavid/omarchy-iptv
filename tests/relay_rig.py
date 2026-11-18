#!/usr/bin/env python3
"""tests/relay_rig.py -- the rig of scripts/dev-harness/relay-scenario.sh
(D-SINK-102). Not a unit test: unittest discovery does not load it, because
it starts mpv and servers.

D-SINK-102 is the marketplace maintainer's finding on
omacom/omarchy-plugin-marketplace#14290 against 0.19.1 (9e006be): the
player's destination checks judged the address the HELPER saw, and the
player then followed an HTTP redirect, opened an HLS or DASH playlist,
segment or key on another host, or looked a name up again itself. The fix
pins the player to a relay the helper runs (bin/helper/12-relay.py), which
judges every connection the player makes against the address it connects
to. This rig observes that at the sinks, the way rule 14 asks: a logging
server the player must never reach logs nothing.

It runs INSIDE `unshare -rn` (relay-scenario.sh starts it there and passes
the caller's network namespace, which it refuses to share): a private
namespace whose only interfaces are its own loopback and a dummy one
carrying 11.0.0.1/32 and 10.0.0.1/32. The helper's own classifier calls
11.0.0.1 global and 10.0.0.1 a local network, so a server on 11.0.0.1
stands for the internet, one on 10.0.0.1 for the LAN and one on 127.0.0.1
for this machine. Nothing can leave the namespace, and every address here
is a literal: nothing is ever looked up by name.

The plugin is the SHIPPING helper of `--tree`, run as the service runs it:
`playlist` writes each source's channels.json, `player start` spawns the
real mpv (and, on a tree with the relay, the relay as its parent), and
`play` zaps. mpv runs headless (`--vo=null --ao=null --force-window=no`),
with no DISPLAY, WAYLAND_DISPLAY or session bus, a scratch HOME, XDG tree
and runtime directory, and its socket in that scratch runtime, never the
owner's. The core limit is 0 for everything this rig starts.

Servers (threads of this process, so nothing of theirs outlives it):
  pub     http://11.0.0.1:18080    the provider (the public playlist too)
  pubs    https://11.0.0.1:18443   the provider over TLS, signed by this run's CA
  trap    http://127.0.0.1:18081   this machine: must log nothing
  traps   https://127.0.0.1:18444  this machine over TLS: must accept nothing
  lan     http://10.0.0.1:18082    the LAN (and the local playlist of R19)
  lpl     http://127.0.0.1:18083   a loopback relay source (R13)
  uproxy  http://127.0.0.1:18084   a proxy the user's session or mpv.conf names
  ka      http://11.0.0.1:18085    a keep-alive provider (HTTP/1.1, R17)
  rtsp    rtsp://11.0.0.1:18554    a fake RTSP server (R14)
  rtrap   tcp 127.0.0.1:18555      an RTSP listener on this machine: no accept
  rtmps   tcp 11.0.0.1:18936       R15's rtmps server: counts and holds each
                                   connection and answers nothing

Checks, each asserting the FIXED behaviour (relay-scenario.sh --baseline
9e006be reds R1..R8, R10, R11 and the relay-only checks; the controls stay
green):
  R1   an http channel whose server 302s to 127.0.0.1: trap logs nothing,
       and the start answers local_address
  R2   the same over https, the 302 to https://127.0.0.1: traps accepts nothing
  R3   an HLS master on 11.0.0.1 whose variant is on 127.0.0.1
  R4   an HLS variant whose segments are on 10.0.0.1
  R5   an HLS variant whose AES-128 key is on 127.0.0.1
  R6a  an fMP4 HLS variant whose EXT-X-MAP init section is on 127.0.0.1
  R6b  a master whose WebVTT rendition is on 127.0.0.1: trap logs nothing,
       and the channel still plays (without the subtitle)
  R7   a DASH manifest whose BaseURL is on 127.0.0.1
  R8   an HLS variant that 302s to 10.0.0.1
  R9   the controls: a same-host 302 (http and https), an HLS stream with
       its key, an fMP4 stream with its WebVTT rendition, and a DASH stream,
       every part on 11.0.0.1, PLAY (time-pos moves, their parts logged)
  R10  the helper started with `no_proxy=*` and `http_proxy` naming uproxy:
       R1's shape is still refused, uproxy logs nothing, and the player's
       own environment holds neither lowercase name
  R11  an mpv.conf naming uproxy as `http-proxy`, in a [protocol.http]
       profile (with `stream-lavf-o=http_proxy=`) and as a
       `demuxer-lavf-o=http_proxy=` line: R1's and R3's shapes refused,
       uproxy logs nothing, and an all-public HLS control still plays
  R12  `--http-proxy=` naming uproxy as an mpvArgs token: dropped in the
       start's reply, uproxy logs nothing, a control plays through the relay
  R13  a loopback relay source on 127.0.0.1:18083: its channel that 302s to
       127.0.0.1:18081 is refused, its channel that 302s to 10.0.0.1 plays
  R14  an rtsp channel whose server 302s to 127.0.0.1: rtrap accepts
       nothing; and an rtsp control, with the user's `--rtsp-transport=udp`,
       is set up interleaved over TCP and plays
  R15  an rtmps channel to 11.0.0.1: its connection reaches the server only
       through the relay -- the relay counts an upstream connection for that
       load's token, one for every connection the server accepted, so
       nothing connected directly. The CONNECT reaches the relay before any
       TLS or RTMP byte, so no TLS rtmp server is needed: the server holds
       the connection and answers nothing, and the load waits in its TLS
       handshake while the rig reads the token off the player
  R16  the relay SIGKILLed during play: the player is gone within 2 s, and
       no server logs a request after it
  R17  a keep-alive HLS stream: the provider served more requests than it
       accepted connections, and every connection it accepted is one the
       relay made (the relay's upstream count)
  R18  a loadfile from another IPC client (no token): the provider logs
       nothing
  R19  a zap from a public channel to a local playlist's channel: the old
       load's token, read off the player before the zap, is still judged by
       the PUBLIC rule after it (10.0.0.1 refused, a public target served),
       and the new token by the local one (10.0.0.1 served)
  R20  an mmsh channel in a public playlist is skipped at the parse

usage: relay_rig.py --tree DIR --work DIR --runtime DIR --outer-netns ID
Exit 0 green, 1 red, 2 a refusal, 77 when mpv, ffmpeg, openssl or ip is
missing or the namespace cannot be made. Stdlib only.
"""
from __future__ import annotations

import argparse
import base64
import http.server
import json
import os
import resource
import select
import shutil
import signal
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time

PUB_IP, LAN_IP, LO_IP = "11.0.0.1", "10.0.0.1", "127.0.0.1"
PORTS = {"pub": 18080, "pubs": 18443, "trap": 18081, "traps": 18444, "lan": 18082, "lpl": 18083,
         "uproxy": 18084, "ka": 18085, "rtsp": 18554, "rtrap": 18555, "rtmps": 18936}
ADDRS = {"pub": PUB_IP, "pubs": PUB_IP, "trap": LO_IP, "traps": LO_IP, "lan": LAN_IP, "lpl": LO_IP,
         "uproxy": LO_IP, "ka": PUB_IP, "rtsp": PUB_IP, "rtrap": LO_IP, "rtmps": PUB_IP}
PUB = "http://%s:%d" % (PUB_IP, PORTS["pub"])
PUBS = "https://%s:%d" % (PUB_IP, PORTS["pubs"])
TRAP = "http://%s:%d" % (LO_IP, PORTS["trap"])
TRAPS = "https://%s:%d" % (LO_IP, PORTS["traps"])
LAN = "http://%s:%d" % (LAN_IP, PORTS["lan"])
LPL = "http://%s:%d" % (LO_IP, PORTS["lpl"])
UPROXY = "http://%s:%d" % (LO_IP, PORTS["uproxy"])
KA = "http://%s:%d" % (PUB_IP, PORTS["ka"])
RTSP = "rtsp://%s:%d" % (PUB_IP, PORTS["rtsp"])
KEY_HEX = "00112233445566778899aabbccddeeff"
IV_HEX = "0f0e0d0c0b0a09080706050403020100"
SKIP = 77

# ------------------------------------------------------------------ the log

LOCK = threading.Lock()
LOG: list[dict] = []
ACCEPTS: dict[str, int] = {name: 0 for name in PORTS}
ROUTES: dict[tuple[str, str], object] = {}
WWW = ""
T0 = time.monotonic()


def record(server: str, method: str, path: str, conn: int, extra: dict | None = None) -> None:
    entry = {"t": time.monotonic(), "server": server, "method": method, "path": path, "conn": conn}
    entry.update(extra or {})
    with LOCK:
        LOG.append(entry)


def accepted(server: str) -> None:
    with LOCK:
        ACCEPTS[server] += 1


def hits(server: str, prefix: str = "", since: float = 0.0) -> list[dict]:
    with LOCK:
        return [e for e in LOG if e["server"] == server and e["path"].startswith(prefix) and e["t"] >= since]


def accepts(server: str) -> int:
    with LOCK:
        return ACCEPTS[server]


def mark() -> float:
    return time.monotonic()


# ------------------------------------------------------------------ servers

def file_route(rel: str, ctype: str):
    def route(_handler):
        with open(os.path.join(WWW, rel), "rb") as fh:
            return 200, [("Content-Type", ctype)], fh.read()
    return route


def redirect(location: str):
    return 302, [("Location", location)], b""


def m3u8(text: str):
    return 200, [("Content-Type", "application/vnd.apple.mpegurl")], text.encode()


CTYPES = {".m3u8": "application/vnd.apple.mpegurl", ".mpd": "application/dash+xml", ".vtt": "text/vtt",
          ".m4s": "video/iso.segment", ".mp4": "video/mp4", ".ts": "video/mp2t", ".bin": "application/octet-stream"}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    server_version = "rig"

    def log_message(self, *args):
        pass

    def answer(self, method: str) -> None:
        name = self.server.rig_name
        path = self.path
        record(name, method, path, id(self.connection))
        if name == "uproxy":
            # A proxy this run never lets anything through: what reaches it
            # is the finding. It answers 502, so nothing is fetched for it.
            self.reply(502, [], b"")
            return
        route = ROUTES.get((name, path.split("?")[0]))
        if route is None and path.startswith("/m/"):
            full = os.path.normpath(os.path.join(WWW, path[3:].split("?")[0].lstrip("/")))
            if full.startswith(WWW + os.sep) and os.path.isfile(full):
                route = file_route(os.path.relpath(full, WWW), CTYPES.get(os.path.splitext(full)[1], "application/octet-stream"))
        if route is None:
            self.reply(404, [], b"")
            return
        status, headers, body = route(self) if callable(route) else route
        self.reply(status, headers, body if method != "HEAD" else b"", len(body))

    def reply(self, status: int, headers: list, body: bytes, length: int | None = None) -> None:
        try:
            self.send_response(status)
            for key, value in headers:
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body) if length is None else length))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass

    def do_GET(self):
        self.answer("GET")

    def do_HEAD(self):
        self.answer("HEAD")

    def do_CONNECT(self):
        self.answer("CONNECT")


class KeepAlive(Handler):
    protocol_version = "HTTP/1.1"


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, name: str, handler, tls: ssl.SSLContext | None) -> None:
        self.rig_name = name
        self.tls = tls
        super().__init__((ADDRS[name], PORTS[name]), handler)

    def get_request(self):
        sock, addr = self.socket.accept()
        accepted(self.rig_name)
        if self.tls is None:
            return sock, addr
        sock.settimeout(5)
        try:
            return self.tls.wrap_socket(sock, server_side=True), addr
        except (OSError, ssl.SSLError):
            sock.close()
            raise


def serve_rtsp(ts_path: str) -> None:
    """A fake RTSP server (tests/tls_pins_rig.py's, on 11.0.0.1): OPTIONS,
    DESCRIBE (one MP2T track), SETUP, PLAY. DESCRIBE of /r14/redir answers
    302 to 127.0.0.1's rtrap. A TCP-interleaved SETUP is streamed the file
    in RTP/MP2T; a UDP one is answered and sent nothing. Every request's
    method, path and Transport is logged."""
    with open(ts_path, "rb") as fh:
        ts = fh.read()
    lsock = socket.socket()
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind((ADDRS["rtsp"], PORTS["rtsp"]))
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
                parts = lines[0].split(" ")
                method, url = parts[0], (parts[1] if len(parts) > 1 else "")
                path = "/" + url.split("/", 3)[3] if url.count("/") >= 3 else url
                hdr = {l.split(":", 1)[0].strip().lower(): l.split(":", 1)[1].strip() for l in lines[1:] if ":" in l}
                record("rtsp", method, path, id(conn), {"transport": hdr.get("transport", "")})
                status, extra, body = "200 OK", "", b""
                if method == "OPTIONS":
                    extra = "Public: OPTIONS, DESCRIBE, SETUP, PLAY, TEARDOWN\r\n"
                elif method == "DESCRIBE" and path.startswith("/r14/redir"):
                    status = "302 Found"
                    extra = "Location: rtsp://%s:%d/r14/x\r\n" % (LO_IP, PORTS["rtrap"])
                elif method == "DESCRIBE":
                    body = (b"v=0\r\no=- 0 0 IN IP4 11.0.0.1\r\ns=x\r\nc=IN IP4 0.0.0.0\r\nt=0 0\r\n"
                            b"m=video 0 RTP/AVP 33\r\na=control:track1\r\n")
                    extra = "Content-Type: application/sdp\r\nContent-Base: %s/live/\r\n" % RTSP
                elif method == "SETUP":
                    tr = hdr.get("transport", "")
                    interleaved = "interleaved" in tr
                    extra = "Session: 4242;timeout=60\r\nTransport: %s\r\n" % (
                        "RTP/AVP/TCP;unicast;interleaved=0-1" if interleaved else tr + ";server_port=47821-47822")
                elif method == "PLAY":
                    extra = "Session: 4242\r\n"
                conn.sendall(("RTSP/1.0 %s\r\nCSeq: %s\r\n%sContent-Length: %d\r\n\r\n"
                              % (status, hdr.get("cseq", "1"), extra, len(body))).encode() + body)
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


def serve_rtmps() -> None:
    """R15's server on 11.0.0.1: accepts, counts and holds each connection,
    reading what arrives and answering nothing, so an rtmps load waits in its
    TLS handshake (mpv's network timeout is 60 s) while the rig asks the
    relay about it. Closed when the peer closes, or after 90 s."""
    lsock = socket.socket()
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind((ADDRS["rtmps"], PORTS["rtmps"]))
    lsock.listen(8)

    def hold(conn):
        conn.settimeout(90)
        try:
            while conn.recv(4096):
                pass
        except OSError:
            pass
        finally:
            conn.close()

    while True:
        conn, _ = lsock.accept()
        accepted("rtmps")
        threading.Thread(target=hold, args=(conn,), daemon=True).start()


def serve_rtrap() -> None:
    lsock = socket.socket()
    lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    lsock.bind((ADDRS["rtrap"], PORTS["rtrap"]))
    lsock.listen(8)
    while True:
        conn, _ = lsock.accept()
        accepted("rtrap")
        conn.close()


# ------------------------------------------------------------------ setup

def run(argv: list[str], timeout: float = 60, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                          preexec_fn=no_core, **kw)


def no_core() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def netns_up(outer: str) -> str:
    """'' once this process is in a namespace of its own with the two
    addresses up, else why not."""
    own = os.readlink("/proc/self/ns/net")
    if not outer or own == outer:
        return "not inside a private network namespace (own %s, caller %s); run under `unshare -rn`" % (own, outer or "unstated")
    for argv in (["ip", "link", "set", "lo", "up"], ["ip", "link", "add", "d0", "type", "dummy"],
                 ["ip", "link", "set", "d0", "up"], ["ip", "addr", "add", PUB_IP + "/32", "dev", "d0"],
                 ["ip", "addr", "add", LAN_IP + "/32", "dev", "d0"]):
        done = run(argv, timeout=10)
        if done.returncode != 0:
            return "`%s` failed: %s" % (" ".join(argv), done.stderr.strip()[-200:])
    return ""


def make_media(work: str) -> dict[str, list[str]]:
    """The media and the certificates. Segment names per kind, in order."""
    certs = os.path.join(work, "certs")
    os.makedirs(certs, mode=0o700)
    for sub in ("ts", "enc", "fmp4", "dash"):
        os.makedirs(os.path.join(WWW, sub), mode=0o700)

    def ossl(*args):
        done = run(["openssl"] + list(args))
        if done.returncode != 0:
            raise RuntimeError("openssl " + args[0] + ": " + done.stderr.strip()[-200:])
    ossl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", certs + "/ca.key", "-out", certs + "/ca.pem",
         "-days", "2", "-subj", "/CN=relay rig CA", "-addext", "basicConstraints=critical,CA:TRUE",
         "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    ossl("req", "-newkey", "rsa:2048", "-nodes", "-keyout", certs + "/srv.key", "-out", certs + "/srv.csr",
         "-subj", "/CN=relay rig")
    with open(certs + "/srv.ext", "w") as fh:
        fh.write("subjectAltName=IP:%s,IP:%s,IP:%s\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\n"
                 % (PUB_IP, LAN_IP, LO_IP))
    ossl("x509", "-req", "-in", certs + "/srv.csr", "-CA", certs + "/ca.pem", "-CAkey", certs + "/ca.key",
         "-CAcreateserial", "-out", certs + "/srv.pem", "-days", "2", "-extfile", certs + "/srv.ext")
    env = dict(os.environ, HOME=work)
    ff = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin"]
    mpeg2 = ff + ["-f", "lavfi", "-i", "testsrc=size=64x64:rate=10", "-f", "lavfi",
                  "-i", "sine=frequency=440:sample_rate=48000", "-c:v", "mpeg2video", "-c:a", "mp2"]
    h264 = ff + ["-f", "lavfi", "-i", "testsrc=size=64x64:rate=10", "-f", "lavfi",
                 "-i", "sine=frequency=440:sample_rate=48000", "-t", "12", "-c:v", "libx264", "-preset",
                 "ultrafast", "-g", "10", "-c:a", "aac"]
    jobs = (
        (mpeg2 + ["-t", "30", "-f", "mpegts", os.path.join(WWW, "long.ts")], "long"),
        (mpeg2 + ["-t", "12", "-g", "20", "-f", "hls", "-hls_time", "2", "-hls_playlist_type", "vod",
                  "-hls_segment_filename", os.path.join(WWW, "ts", "s%03d.ts"), os.path.join(WWW, "ts", "v.m3u8")], "ts"),
        (h264 + ["-f", "hls", "-hls_time", "2", "-hls_playlist_type", "vod", "-hls_segment_type", "fmp4",
                 "-hls_fmp4_init_filename", "init.mp4", "-hls_segment_filename", os.path.join(WWW, "fmp4", "s%03d.m4s"),
                 os.path.join(WWW, "fmp4", "v.m3u8")], "fmp4"),
        (h264 + ["-f", "dash", "-seg_duration", "2", "-init_seg_name", "init-$RepresentationID$.m4s",
                 "-media_seg_name", "chunk-$RepresentationID$-$Number%05d$.m4s",
                 os.path.join(WWW, "dash", "manifest.mpd")], "dash"),
    )
    for argv, what in jobs:
        done = run(argv, timeout=120, env=env)
        if done.returncode != 0:
            raise RuntimeError("ffmpeg " + what + ": " + done.stderr.strip()[-200:])
    names = {"ts": sorted(n for n in os.listdir(os.path.join(WWW, "ts")) if n.endswith(".ts")),
             "fmp4": sorted(n for n in os.listdir(os.path.join(WWW, "fmp4")) if n.endswith(".m4s"))}
    with open(os.path.join(WWW, "enc", "key.bin"), "wb") as fh:
        fh.write(bytes.fromhex(KEY_HEX))
    for name in names["ts"]:
        ossl("enc", "-aes-128-cbc", "-K", KEY_HEX, "-iv", IV_HEX, "-in", os.path.join(WWW, "ts", name),
             "-out", os.path.join(WWW, "enc", name))
    with open(os.path.join(WWW, "sub0.vtt"), "w") as fh:
        fh.write("WEBVTT\nX-TIMESTAMP-MAP=MPEGTS:0,LOCAL:00:00:00.000\n\n00:00:00.000 --> 00:00:11.000\nrig line\n")
    return names


def durations(kind: str) -> list[str]:
    with open(os.path.join(WWW, kind, "v.m3u8")) as fh:
        return [line.strip() for line in fh if line.startswith("#EXTINF")]


def vod(kind: str, names: list[str], base: str, key: str = "", init: str = "", version: int = 3) -> str:
    """A VOD media playlist over `names`, each at `base` + name, with an
    AES-128 key at `key` and an init section at `init` when given."""
    out = ["#EXTM3U", "#EXT-X-VERSION:%d" % version, "#EXT-X-TARGETDURATION:3", "#EXT-X-MEDIA-SEQUENCE:0",
           "#EXT-X-PLAYLIST-TYPE:VOD"]
    if key:
        out.append('#EXT-X-KEY:METHOD=AES-128,URI="%s",IV=0x%s' % (key, IV_HEX))
    if init:
        out.append('#EXT-X-MAP:URI="%s"' % init)
    for extinf, name in zip(durations(kind), names):
        out += [extinf, base + name]
    return "\n".join(out + ["#EXT-X-ENDLIST", ""])


def live_route(base: str, names: list[str]):
    """A live media playlist that slides over `names` every two seconds and
    never ends, so a player keeps asking for it."""
    def route(_handler):
        seq = int((time.monotonic() - T0) / 2)
        out = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-TARGETDURATION:3", "#EXT-X-MEDIA-SEQUENCE:%d" % seq]
        for i in range(seq, seq + 3):
            if i % len(names) == 0 and i:
                out.append("#EXT-X-DISCONTINUITY")
            out += ["#EXTINF:2.000,", base + names[i % len(names)]]
        return m3u8("\n".join(out) + "\n")
    return route


def master(variant: str, subs: str = "") -> str:
    if subs:
        return ('#EXTM3U\n#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="s",NAME="English",DEFAULT=YES,AUTOSELECT=YES,'
                'LANGUAGE="en",URI="%s"\n#EXT-X-STREAM-INF:BANDWIDTH=300000,SUBTITLES="s"\n%s\n' % (subs, variant))
    return "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=300000\n%s\n" % variant


def subs_playlist(vtt: str) -> str:
    return "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:12\n#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:12.000,\n%s\n#EXT-X-ENDLIST\n" % vtt


def mpd(base: str) -> bytes:
    with open(os.path.join(WWW, "dash", "manifest.mpd")) as fh:
        text = fh.read()
    if base:
        at = text.index("<Period")
        text = text[:at] + "<BaseURL>%s</BaseURL>\n" % base + text[at:]
    return text.encode()


def routes(names: dict[str, list[str]]) -> dict[str, list[tuple[str, str]]]:
    """Every route the cases use, and the three playlists' channels (name, URL)."""
    ts, fm = names["ts"], names["fmp4"]
    tsb, encb, fmb = PUB + "/m/ts/", PUB + "/m/enc/", PUB + "/m/fmp4/"
    R = ROUTES
    live_ts = live_route(tsb, ts)
    pub = []

    def chan(name, url, playlist=pub):
        playlist.append((name, url))

    # R9a and R1: a 302 on the same host (the control) and into this machine.
    R["pub", "/c1/stream.ts"] = redirect(PUB + "/c1/real.ts")
    R["pub", "/c1/real.ts"] = file_route("long.ts", "video/mp2t")
    chan("C1 same-host 302", PUB + "/c1/stream.ts")
    for case in ("r1", "r10", "r11a", "r21"):
        R["pub", "/%s/stream.ts" % case] = redirect(TRAP + "/%s/admin" % case)
        chan(case.upper() + " 302 to this machine", PUB + "/%s/stream.ts" % case)
    # R21's control: an address the provider answers 404, which no relay refuses.
    chan("R21 gone", PUB + "/r21/gone.ts")
    # R2 and R9e over TLS.
    R["pubs", "/r2/stream.ts"] = redirect(TRAPS + "/r2/admin")
    chan("R2 https 302 to this machine", PUBS + "/r2/stream.ts")
    R["pubs", "/c9e/stream.ts"] = redirect(PUBS + "/c9e/real.ts")
    R["pubs", "/c9e/real.ts"] = file_route("long.ts", "video/mp2t")
    chan("C9E https same-host 302", PUBS + "/c9e/stream.ts")
    # R3, R11b: a master whose variant is on this machine.
    for case in ("r3", "r11b"):
        R["pub", "/%s/master.m3u8" % case] = m3u8(master(TRAP + "/%s/v.m3u8" % case))
        chan(case.upper() + " HLS variant on this machine", PUB + "/%s/master.m3u8" % case)
    # R4: segments on the LAN.
    R["pub", "/r4/v.m3u8"] = m3u8(vod("ts", ts, LAN + "/r4/"))
    chan("R4 HLS segments on the LAN", PUB + "/r4/v.m3u8")
    # R5: the key on this machine (segments encrypted, on the provider).
    R["pub", "/r5/v.m3u8"] = m3u8(vod("ts", ts, encb, key=TRAP + "/r5/key.bin"))
    chan("R5 HLS key on this machine", PUB + "/r5/v.m3u8")
    # R6a: the init section on this machine; R6b: the subtitle rendition.
    R["pub", "/r6a/v.m3u8"] = m3u8(vod("fmp4", fm, fmb, init=TRAP + "/r6a/init.mp4", version=7))
    chan("R6A HLS init section on this machine", PUB + "/r6a/v.m3u8")
    R["pub", "/r6b/master.m3u8"] = m3u8(master(PUB + "/r6b/v.m3u8", subs=TRAP + "/r6b/subs.m3u8"))
    R["pub", "/r6b/v.m3u8"] = m3u8(vod("fmp4", fm, fmb, init=fmb + "init.mp4", version=7))
    chan("R6B HLS subtitles on this machine", PUB + "/r6b/master.m3u8")
    # R7: DASH whose BaseURL is this machine's.
    R["pub", "/r7/manifest.mpd"] = (200, [("Content-Type", "application/dash+xml")], mpd(TRAP + "/r7/"))
    chan("R7 DASH BaseURL on this machine", PUB + "/r7/manifest.mpd")
    # R8: a variant that 302s to the LAN.
    R["pub", "/r8/master.m3u8"] = m3u8(master(PUB + "/r8/v302.m3u8"))
    R["pub", "/r8/v302.m3u8"] = redirect(LAN + "/r8/v.m3u8")
    chan("R8 HLS variant 302 to the LAN", PUB + "/r8/master.m3u8")
    # R9b-d: the controls, every part on the provider.
    R["pub", "/c9b/master.m3u8"] = m3u8(master(PUB + "/c9b/v.m3u8"))
    R["pub", "/c9b/v.m3u8"] = m3u8(vod("ts", ts, encb, key=PUB + "/c9b/key.bin"))
    R["pub", "/c9b/key.bin"] = file_route(os.path.join("enc", "key.bin"), "application/octet-stream")
    chan("C9B HLS with its key", PUB + "/c9b/master.m3u8")
    R["pub", "/c9c/master.m3u8"] = m3u8(master(PUB + "/c9c/v.m3u8", subs=PUB + "/c9c/subs.m3u8"))
    R["pub", "/c9c/v.m3u8"] = m3u8(vod("fmp4", fm, fmb, init=fmb + "init.mp4", version=7))
    R["pub", "/c9c/subs.m3u8"] = m3u8(subs_playlist(PUB + "/c9c/sub0.vtt"))
    R["pub", "/c9c/sub0.vtt"] = file_route("sub0.vtt", "text/vtt")
    chan("C9C fMP4 HLS with WebVTT", PUB + "/c9c/master.m3u8")
    R["pub", "/c9d/manifest.mpd"] = (200, [("Content-Type", "application/dash+xml")], mpd(PUB + "/m/dash/"))
    chan("C9D DASH", PUB + "/c9d/manifest.mpd")
    R["pub", "/c11/v.m3u8"] = m3u8(vod("ts", ts, tsb))
    chan("C11 HLS control", PUB + "/c11/v.m3u8")
    # The live channels R16, R18 and R19 keep asking for.
    R["pub", "/live/v.m3u8"] = live_ts
    chan("LIVE public", PUB + "/live/v.m3u8")
    R["pub", "/r18/other.ts"] = file_route("long.ts", "video/mp2t")
    # R14: rtsp.
    chan("R14 rtsp 302 to this machine", RTSP + "/r14/redir")
    chan("C14 rtsp control", RTSP + "/live")
    # R15: rtmps, to a server that holds the connection and answers nothing.
    chan("R15 rtmps", "rtmps://%s:%d/r15/x" % (PUB_IP, PORTS["rtmps"]))
    # R17: a keep-alive provider.
    R["ka", "/ka/v.m3u8"] = m3u8(vod("ts", ts, KA + "/m/ts/"))
    chan("R17 keep-alive HLS", KA + "/ka/v.m3u8")
    # R20: an mmsh channel, refused at the parse from a public playlist.
    chan("R20 mmsh", "mmsh://%s:%d/r20/stream" % (PUB_IP, PORTS["pub"]))
    # R13: the loopback relay source.
    lpl = []
    R["lpl", "/r13a/stream.ts"] = redirect(TRAP + "/r13a/admin")
    chan("R13A 302 to another port here", LPL + "/r13a/stream.ts", lpl)
    R["lpl", "/r13b/stream.ts"] = redirect(LAN + "/r13b/real.ts")
    R["lan", "/r13b/real.ts"] = file_route("long.ts", "video/mp2t")
    chan("R13B 302 to the LAN", LPL + "/r13b/stream.ts", lpl)
    # R19: the local playlist on the LAN.
    lan = []
    R["lan", "/r19/v.m3u8"] = live_route(LAN + "/m/ts/", ts)
    chan("R19 LAN live", LAN + "/r19/v.m3u8", lan)
    R["lan", "/r19/late"] = (200, [], b"late")
    R["pub", "/r19/late"] = (200, [], b"late")
    for name, items in (("pub", pub), ("lpl", lpl), ("lan", lan)):
        body = "#EXTM3U\n" + "".join("#EXTINF:-1,%s\n%s\n" % item for item in items)
        R[name, "/list.m3u"] = (200, [("Content-Type", "audio/x-mpegurl")], body.encode())
    return {"pub": pub, "lpl": lpl, "lan": lan}


def start_servers(work: str, names: dict[str, list[str]]) -> None:
    certs = os.path.join(work, "certs")
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(certs + "/srv.pem", certs + "/srv.key")
    for name in ("pub", "pubs", "trap", "traps", "lan", "lpl", "uproxy", "ka"):
        server = Server(name, KeepAlive if name == "ka" else Handler, tls if name in ("pubs", "traps") else None)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=serve_rtsp, args=(os.path.join(WWW, "long.ts"),), daemon=True).start()
    threading.Thread(target=serve_rtrap, daemon=True).start()
    threading.Thread(target=serve_rtmps, daemon=True).start()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        up = 0
        for name, port in PORTS.items():
            with socket.socket() as s:
                s.settimeout(0.2)
                up += s.connect_ex((ADDRS[name], port)) == 0
        if up == len(PORTS):
            break
        time.sleep(0.1)
    # The probes above are connections too; the counts start here.
    time.sleep(0.2)
    with LOCK:
        for name in ACCEPTS:
            ACCEPTS[name] = 0
        del LOG[:]


# ------------------------------------------------------------------ the plugin

class Rig:
    def __init__(self, tree: str, work: str, runtime: str) -> None:
        self.tree = tree
        self.helper = os.path.join(tree, "bin", "omarchy-iptv")
        self.work = work
        self.runtime = runtime
        self.sock = os.path.join(runtime, "omarchy-iptv", "mpv.sock")
        self.home = os.path.join(work, "home")
        for sub in ("", ".config/mpv", ".cache", ".local/state", ".local/share"):
            os.makedirs(os.path.join(self.home, sub), mode=0o700, exist_ok=True)
        self.ca = os.path.join(work, "certs", "ca.pem")
        self.ids: dict[str, dict[str, str]] = {}
        self.caches: dict[str, str] = {}
        self.seen: dict[int, str] = {}     # pid -> what it is (mpv, relay), every one this run started
        self.passed = 0
        self.failed = 0

    # -- reporting
    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        if ok:
            self.passed += 1
            print("PASS %s" % label, flush=True)
        else:
            self.failed += 1
            print("FAIL %s%s" % (label, " -- " + detail if detail else ""), flush=True)
        return ok

    # -- the helper
    def env(self, extra: dict | None = None) -> dict:
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": self.home, "LANG": "C.UTF-8",
               "XDG_CONFIG_HOME": os.path.join(self.home, ".config"), "XDG_CACHE_HOME": os.path.join(self.home, ".cache"),
               "XDG_STATE_HOME": os.path.join(self.home, ".local/state"),
               "XDG_DATA_HOME": os.path.join(self.home, ".local/share"), "XDG_RUNTIME_DIR": self.runtime}
        env.update(extra or {})
        return env

    def helper_run(self, args: list[str], extra: dict | None = None, timeout: float = 60) -> tuple[int, dict | None, str]:
        done = run([sys.executable, "-I", self.helper] + args, timeout=timeout, env=self.env(extra))
        lines = [line for line in done.stdout.splitlines() if line.strip()]
        try:
            reply = json.loads(lines[-1]) if lines else None
        except ValueError:
            reply = None
        return done.returncode, reply, done.stderr

    def parse(self, name: str) -> dict:
        cache = os.path.join(self.work, "cache-" + name)
        os.makedirs(cache, mode=0o700, exist_ok=True)
        base = {"pub": PUB, "lpl": LPL, "lan": LAN}[name]
        _, reply, _ = self.helper_run(["playlist", "--cache-dir", cache, "--timeout", "10"],
                                      {"OMARCHY_IPTV_URL": base + "/list.m3u", "OMARCHY_IPTV_ORIGIN": "user"})
        ids = {}
        try:
            with open(os.path.join(cache, "channels.json")) as fh:
                for channel in json.load(fh).get("channels", []):
                    ids[channel["name"]] = channel["id"]
        except (OSError, ValueError, KeyError):
            pass
        self.ids[name] = ids
        self.caches[name] = cache
        return reply or {}

    MPV_ARGS = ("--vo=null", "--ao=null", "--force-window=no", "--rtsp-transport=udp")

    def start(self, playlist: str, name: str, extra_env: dict | None = None, mpv_extra: tuple = ()) -> dict:
        cid = self.ids.get(playlist, {}).get(name)
        if cid is None:
            return {"ok": False, "error": {"code": "rig_no_channel", "message": name}}
        args = ["player", "start", "--socket", self.sock, "--id", cid, "--cache-dir", self.caches[playlist],
                "--first-load-timeout", "8", "--spawn-timeout", "10"]
        for token in self.MPV_ARGS + ("--tls-ca-file=" + self.ca,) + tuple(mpv_extra):
            args.append("--mpv-arg=" + token)
        _, reply, _ = self.helper_run(args, extra_env, timeout=90)
        self.note_players()
        return reply or {}

    def zap(self, playlist: str, name: str, session: bool = False) -> dict:
        """`play`; with `session`, as the shell sends it (`--scope` and
        `--since`), which is the reply that carries the load's relay handle."""
        cid = self.ids.get(playlist, {}).get(name)
        if cid is None:
            return {"ok": False}
        args = ["play", "--socket", self.sock, "--id", cid, "--cache-dir", self.caches[playlist]]
        if session:
            args += ["--scope", "all", "--since", "1"]
        _, reply, _ = self.helper_run(args)
        return reply or {}

    def stop(self) -> None:
        self.helper_run(["player", "stop", "--socket", self.sock], timeout=60)
        self.settle_gone(5.0)

    # -- the processes this run started
    def ours(self, pid: int) -> str:
        """What `pid` is, when its command line says it is one this run
        started: an mpv on THIS run's scratch socket, or a relay of THIS
        tree's helper. '' otherwise."""
        try:
            with open("/proc/%d/cmdline" % pid, "rb") as fh:
                argv = [os.fsdecode(a) for a in fh.read().split(b"\0") if a]
        except OSError:
            return ""
        if "--input-ipc-server=" + self.sock in argv:
            return "mpv"
        if (argv[-3:-1] == ["player", "relay"] and argv[-1].startswith("--child=")
                and os.path.realpath(self.helper) in [os.path.realpath(a) for a in argv if a.startswith("/")]):
            return "relay"
        return ""

    def note_players(self) -> None:
        """Every process whose command line holds this run's own scratch
        socket, and every relay of this tree's helper whose child is one of
        them -- read off /proc by command line, never by ancestry."""
        for entry in os.listdir("/proc"):
            if entry.isdigit():
                what = self.ours(int(entry))
                if what == "mpv":
                    self.seen.setdefault(int(entry), what)
        for entry in os.listdir("/proc"):
            if entry.isdigit() and self.ours(int(entry)) == "relay":
                try:
                    with open("/proc/%s/cmdline" % entry, "rb") as fh:
                        child = int(fh.read().split(b"\0")[-2].split(b"=", 1)[1])
                except (OSError, ValueError, IndexError):
                    continue
                if child in self.seen:
                    self.seen.setdefault(int(entry), "relay")

    @staticmethod
    def relay_child(pid: int) -> int:
        try:
            with open("/proc/%d/cmdline" % pid, "rb") as fh:
                return int(fh.read().split(b"\0")[-2].split(b"=", 1)[1])
        except (OSError, ValueError, IndexError):
            return 0

    def pidfd(self, pid: int, what: str) -> int | None:
        """A pidfd for `pid`, opened only while its command line reads as
        `what` of this run, and still the process the pidfd holds."""
        try:
            fd = os.pidfd_open(pid)
        except OSError:
            return None
        if self.ours(pid) != what:
            os.close(fd)
            return None
        try:
            signal.pidfd_send_signal(fd, 0)
        except OSError:
            os.close(fd)
            return None
        return fd

    def alive(self) -> list[int]:
        return [pid for pid, what in self.seen.items() if self.ours(pid) == what]

    def settle_gone(self, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while self.alive() and time.monotonic() < deadline:
            time.sleep(0.1)
        return not self.alive()

    def reap(self) -> list[int]:
        """The last resort, at the end: SIGKILL through a pidfd to every
        process this run started that is still there, each checked by its
        command line on the pidfd first. -> the pids that needed it."""
        left = []
        for pid, what in list(self.seen.items()):
            fd = self.pidfd(pid, what)
            if fd is None:
                continue
            left.append(pid)
            try:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
            except OSError:
                pass
            finally:
                os.close(fd)
        return left

    # -- mpv's IPC
    def ipc(self, *command, timeout: float = 3.0):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect(self.sock)
                s.sendall(json.dumps({"command": list(command), "request_id": 7}).encode() + b"\n")
                buf = b""
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    chunk = s.recv(65536)
                    if not chunk:
                        return False, None
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        try:
                            msg = json.loads(line)
                        except ValueError:
                            continue
                        if msg.get("request_id") == 7:
                            return msg.get("error") == "success", msg.get("data")
        except OSError:
            pass
        return False, None

    def playing(self, seconds: float = 10.0) -> bool:
        """time-pos moved by half a second or more within `seconds`."""
        first = None
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            ok, value = self.ipc("get_property", "time-pos")
            if ok and isinstance(value, (int, float)):
                if first is None:
                    first = value
                elif value - first >= 0.5:
                    return True
            time.sleep(0.25)
        return False

    def token(self) -> tuple[str, int]:
        """The load's token and the relay's port, off the player's own
        per-file http-proxy, or ('', 0)."""
        ok, value = self.ipc("get_property", "http-proxy")
        if not ok or not isinstance(value, str) or not value.startswith("http://iptv:"):
            return "", 0
        try:
            userinfo, hostport = value[len("http://"):].rstrip("/").rsplit("@", 1)
            return userinfo.split(":", 1)[1], int(hostport.rsplit(":", 1)[1])
        except (ValueError, IndexError):
            return "", 0

    # -- the relay
    def relay_status(self) -> tuple[int, dict | None]:
        """The relay's own answer on its control socket and its pid, read
        from the socket's peer credentials (never from ancestry)."""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect(self.sock + ".relay")
                pid = struct.unpack("3i", s.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))[0]
                s.sendall(b'{"op":"status"}\n')
                buf = b""
                while b"\n" not in buf:
                    chunk = s.recv(8192)
                    if not chunk:
                        break
                    buf += chunk
                return pid, json.loads(buf.split(b"\n", 1)[0])
        except (OSError, ValueError):
            return 0, None

    def relay_count(self, token: str) -> dict | None:
        """The relay's counts for one load's token (`{"op":"count"}` on its
        control socket), or None."""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(2)
                s.connect(self.sock + ".relay")
                s.sendall(json.dumps({"op": "count", "token": token}).encode() + b"\n")
                buf = b""
                while b"\n" not in buf:
                    chunk = s.recv(8192)
                    if not chunk:
                        break
                    buf += chunk
                reply = json.loads(buf.split(b"\n", 1)[0])
                return reply if isinstance(reply, dict) and reply.get("ok") is True else None
        except (OSError, ValueError):
            return None

    def via_relay(self, port: int, token: str, url: str) -> int:
        """One absolute-form GET through the relay with `token`, as FFmpeg
        sends it after the 407; -> the status the relay answered, 0 for none."""
        auth = base64.b64encode(("iptv:%s" % token).encode()).decode()
        host = url.split("/", 3)[2]
        head = "GET %s HTTP/1.1\r\nHost: %s\r\nProxy-Authorization: Basic %s\r\nConnection: close\r\n\r\n" % (url, host, auth)
        try:
            with socket.create_connection((LO_IP, port), timeout=5) as s:
                s.sendall(head.encode())
                line = s.makefile("rb").readline().decode("latin-1")
            return int(line.split(" ")[1])
        except (OSError, ValueError, IndexError):
            return 0


def code(reply: dict) -> str:
    return ((reply or {}).get("error") or {}).get("code") or ("ok" if (reply or {}).get("ok") else "none")


def first_state(reply: dict) -> str:
    return ((reply or {}).get("firstLoad") or {}).get("state", "none")


def environ_names(pid: int) -> set[str] | None:
    try:
        with open("/proc/%d/environ" % pid, "rb") as fh:
            return {item.split(b"=", 1)[0].decode("latin-1") for item in fh.read().split(b"\0") if item}
    except OSError:
        return None


def wait_until(predicate, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return predicate()


# ------------------------------------------------------------------ the cases

def refused(rig: Rig, label: str, playlist: str, name: str, premise: tuple[str, str], sinks: list[tuple[str, str]],
            **start) -> None:
    """A start the relay must refuse: the first hop reached the provider
    (the premise, without which the sink being empty proves nothing), no
    sink was reached, and the start answered local_address."""
    since = mark()
    reply = rig.start(playlist, name, **start)
    server, prefix = premise
    rig.check("%s premise: the first hop reached %s" % (label, server), wait_until(lambda: hits(server, prefix, since), 3),
              "no %s request on %s" % (prefix, server))
    time.sleep(1.0)
    for sink, prefix in sinks:
        if sink in ("traps", "rtrap"):
            got = accepts(sink) - rig.accepts_before.get(sink, 0)
            rig.accepts_before[sink] = accepts(sink)
            rig.check("%s: %s accepted no connection" % (label, sink), got == 0, "%d accepted" % got)
        else:
            got = hits(sink, prefix, since)
            rig.check("%s: %s logged nothing under %s" % (label, sink, prefix or "/"), not got,
                      "%d request(s): %s" % (len(got), ", ".join(e["method"] + " " + e["path"] for e in got[:3])))
    rig.check("%s: the start answered local_address" % label, code(reply) == "local_address", "got %s" % code(reply))


def played(rig: Rig, label: str, playlist: str, name: str, server: str, prefix: str, least: int = 2, **start) -> dict:
    since = mark()
    reply = rig.start(playlist, name, **start)
    rig.check("%s: the start's first load is playing" % label, first_state(reply) == "playing",
              "got %s/%s" % (code(reply), first_state(reply)))
    rig.check("%s: time-pos moves" % label, rig.playing())
    got = wait_until(lambda: len(hits(server, prefix, since)) >= least, 6)
    rig.check("%s: %s served at least %d requests under %s" % (label, server, least, prefix), got,
              "%d" % len(hits(server, prefix, since)))
    return reply


def main() -> int:
    global WWW
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--runtime", required=True)
    ap.add_argument("--outer-netns", default="")
    opts = ap.parse_args()
    no_core()
    # A TERM (the scenario's bound) unwinds through main's `finally`, which
    # stops every player this run started; Python's default would not.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    for tool in ("mpv", "ffmpeg", "openssl", "ip"):
        if shutil.which(tool) is None:
            print("SKIP relay-scenario: %s is not on PATH" % tool)
            return SKIP
    why = netns_up(opts.outer_netns)
    if why:
        print("SKIP relay-scenario: %s" % why)
        return SKIP
    tree = os.path.realpath(opts.tree)
    if not os.path.isfile(os.path.join(tree, "bin", "omarchy-iptv")):
        print("REFUSING: %s holds no bin/omarchy-iptv" % tree)
        return 2
    sock = os.path.join(opts.runtime, "omarchy-iptv", "mpv.sock")
    if len(os.fsencode(sock + ".relay")) > 107:
        print("REFUSING: the scratch socket path is %d bytes with its relay suffix, over sun_path's 107;"
              " set TMPDIR somewhere shorter" % len(os.fsencode(sock + ".relay")))
        return 2
    WWW = os.path.join(opts.work, "www")
    os.makedirs(WWW, mode=0o700)
    names = make_media(opts.work)
    playlists = routes(names)
    start_servers(opts.work, names)
    rig = Rig(tree, opts.work, opts.runtime)
    rig.accepts_before = {}
    try:
        cases(rig, playlists)
    finally:
        rig.stop()
        left = rig.reap()
        rig.check("teardown: every mpv and relay this run started is gone after `player stop`", not left,
                  "SIGKILLed through a checked pidfd: %s" % left)
        rig.check("teardown: the scratch socket and its relay socket are gone",
                  not os.path.lexists(rig.sock) and not os.path.lexists(rig.sock + ".relay"))
    print("== relay rig: %d passed, %d failed; %d mpv and %d relay process(es) started"
          % (rig.passed, rig.failed, sum(1 for w in rig.seen.values() if w == "mpv"),
             sum(1 for w in rig.seen.values() if w == "relay")))
    return 0 if rig.failed == 0 else 1


def cases(rig: Rig, playlists: dict) -> None:
    # R20 first: the parse.
    rig.parse("pub")
    rig.parse("lpl")
    rig.parse("lan")
    ids = rig.ids["pub"]
    rig.check("setup: the public playlist parsed (%d channels)" % len(ids), len(ids) >= 20, "%d" % len(ids))
    rig.check("setup: the loopback and LAN playlists parsed",
              len(rig.ids["lpl"]) == 2 and len(rig.ids["lan"]) == 1, "%r %r" % (rig.ids["lpl"], rig.ids["lan"]))
    rig.check("R20: an mmsh channel in a public playlist is skipped at the parse", "R20 mmsh" not in ids)

    # The controls first: without them every empty sink below proves nothing.
    played(rig, "R9a same-host 302", "pub", "C1 same-host 302", "pub", "/c1/", least=2)
    refused(rig, "R1 302 to 127.0.0.1", "pub", "R1 302 to this machine", ("pub", "/r1/"), [("trap", "/r1/")])
    played(rig, "R9e https same-host 302", "pub", "C9E https same-host 302", "pubs", "/c9e/", least=2)
    refused(rig, "R2 https 302 to 127.0.0.1", "pub", "R2 https 302 to this machine", ("pubs", "/r2/"), [("traps", "")])
    refused(rig, "R3 HLS variant on 127.0.0.1", "pub", "R3 HLS variant on this machine", ("pub", "/r3/"), [("trap", "/r3/")])
    refused(rig, "R4 HLS segments on 10.0.0.1", "pub", "R4 HLS segments on the LAN", ("pub", "/r4/"), [("lan", "/r4/")])
    refused(rig, "R5 HLS key on 127.0.0.1", "pub", "R5 HLS key on this machine", ("pub", "/r5/"), [("trap", "/r5/")])
    refused(rig, "R6a HLS init section on 127.0.0.1", "pub", "R6A HLS init section on this machine", ("pub", "/r6a/"),
            [("trap", "/r6a/")])
    since = mark()
    reply = rig.start("pub", "R6B HLS subtitles on this machine")
    rig.check("R6b premise: the master reached pub", bool(hits("pub", "/r6b/", since)))
    rig.check("R6b: the channel still plays without its subtitle", first_state(reply) == "playing" and rig.playing(),
              "got %s/%s" % (code(reply), first_state(reply)))
    rig.check("R6b: trap logged nothing under /r6b/", not hits("trap", "/r6b/", since),
              "%d request(s)" % len(hits("trap", "/r6b/", since)))
    refused(rig, "R7 DASH BaseURL on 127.0.0.1", "pub", "R7 DASH BaseURL on this machine", ("pub", "/r7/"), [("trap", "/r7/")])
    refused(rig, "R8 HLS variant 302 to 10.0.0.1", "pub", "R8 HLS variant 302 to the LAN", ("pub", "/r8/v302"),
            [("lan", "/r8/")])
    played(rig, "R9b HLS with its key", "pub", "C9B HLS with its key", "pub", "/m/enc/", least=2)
    rig.check("R9b: its key was fetched from pub", bool(hits("pub", "/c9b/key.bin")))
    played(rig, "R9c fMP4 HLS with WebVTT", "pub", "C9C fMP4 HLS with WebVTT", "pub", "/m/fmp4/", least=2)
    rig.check("R9c: its WebVTT rendition was fetched from pub", bool(hits("pub", "/c9c/sub0.vtt")))
    played(rig, "R9d DASH", "pub", "C9D DASH", "pub", "/m/dash/", least=2)

    # R13: the loopback relay source.
    refused(rig, "R13a loopback source, 302 to another port here", "lpl", "R13A 302 to another port here",
            ("lpl", "/r13a/"), [("trap", "/r13a/")])
    played(rig, "R13b loopback source, 302 to the LAN", "lpl", "R13B 302 to the LAN", "lan", "/r13b/", least=1)

    # R14: rtsp.
    rig.accepts_before["rtrap"] = accepts("rtrap")
    since = mark()
    reply = rig.start("pub", "R14 rtsp 302 to this machine")
    rig.check("R14 premise: the rtsp DESCRIBE reached the provider", bool(hits("rtsp", "/r14/redir", since)))
    time.sleep(1.0)
    rig.check("R14: rtrap accepted no connection", accepts("rtrap") == rig.accepts_before["rtrap"],
              "%d accepted" % (accepts("rtrap") - rig.accepts_before["rtrap"]))
    since = mark()
    reply = rig.start("pub", "C14 rtsp control")
    setups = [e for e in hits("rtsp", "", since) if e["method"] == "SETUP"]
    rig.check("R14 control: its SETUP asked for TCP interleaved over the user's --rtsp-transport=udp",
              bool(setups) and all("interleaved" in e.get("transport", "") for e in setups),
              "transports %r" % [e.get("transport", "") for e in setups])
    rig.check("R14 control: it plays", first_state(reply) == "playing" and rig.playing(),
              "got %s/%s" % (code(reply), first_state(reply)))
    # R17: keep-alive through the relay.
    _, status = rig.relay_status()
    up_before = (status or {}).get("upstream", -1)
    acc_before = accepts("ka")
    since = mark()
    played(rig, "R17 keep-alive HLS", "pub", "R17 keep-alive HLS", "ka", "/m/ts/", least=3)
    wait_until(lambda: len(hits("ka", "", since)) >= 5, 6)
    _, status = rig.relay_status()
    up = (status or {}).get("upstream", -1) - up_before if status and up_before >= 0 else -1
    got_acc, got_req = accepts("ka") - acc_before, len(hits("ka", "", since))
    rig.check("R17: ka served more requests than it accepted connections (%d over %d)" % (got_req, got_acc),
              0 < got_acc < got_req)
    rig.check("R17: every connection ka accepted is one the relay made (relay upstream +%d)" % up, up == got_acc,
              "relay upstream +%d, ka accepted %d" % (up, got_acc))

    # R15: rtmps through the relay. FFmpeg's rtmps hands its options to tls,
    # which tunnels through the per-file http-proxy with a CONNECT before any
    # TLS or RTMP byte (measured by the design's rig, QA-RESULTS "D-SINK-102"); the relay judges
    # 11.0.0.1 and connects. The token is read off the player while the
    # load still waits in its handshake (the server answers nothing), and
    # the relay is asked that token's counts: every connection the server
    # accepted must be one the relay made for it. An FFmpeg that stopped
    # handing the option to rtmps's tls would connect directly, and the
    # relay would count none.
    acc_before = accepts("rtmps")
    reply = rig.start("pub", "R15 rtmps")
    token, _ = rig.token()
    counts = rig.relay_count(token) if token else None
    got_acc = accepts("rtmps") - acc_before
    up = (counts or {}).get("upstream", -1)
    rig.check("R15 premise: the rtmps channel's connection reached its server (%d accepted; start %s/%s)"
              % (got_acc, code(reply), first_state(reply)), got_acc >= 1)
    rig.check("R15: the rtmps load's token is on the player's per-file http-proxy", bool(token))
    rig.check("R15: the relay made an upstream connection for that load's token (+%d)" % up, up >= 1)
    rig.check("R15: every connection the rtmps server accepted is one the relay made for that token,"
              " so nothing connected directly", up == got_acc, "relay upstream %d, rtmps accepted %d" % (up, got_acc))
    rig.stop()

    # R19: a zap from a public channel to a local playlist's channel.
    played(rig, "R19 public live channel", "pub", "LIVE public", "pub", "/m/ts/", least=1)
    old, port = rig.token()
    rig.check("R19: the public load's token is on the player's per-file http-proxy", bool(old))
    since = mark()
    reply = rig.zap("lan", "R19 LAN live")
    rig.check("R19: the zap to the LAN playlist's channel was applied", (reply or {}).get("ok") is True and rig.playing(),
              "got %s" % code(reply))
    new, port2 = rig.token()
    rig.check("R19: the new load has a token of its own", bool(new) and new != old and port2 == port)
    t = mark()
    rig.check("R19: the old token still reaches a public target (it is live)",
              bool(old) and rig.via_relay(port, old, PUB + "/r19/late") == 200)
    rig.check("R19: the old token is still judged by the public rule: 10.0.0.1 refused 403",
              bool(old) and rig.via_relay(port, old, LAN + "/r19/late") == 403)
    rig.check("R19: and lan logged nothing for it", not [e for e in hits("lan", "/r19/late", t)])
    t2 = mark()
    rig.check("R19: the new token is judged by the local rule: 10.0.0.1 served",
              bool(new) and rig.via_relay(port, new, LAN + "/r19/late") == 200 and bool(hits("lan", "/r19/late", t2)))

    # R16: the relay SIGKILLed during play.
    rig.note_players()
    relay_pid, status = rig.relay_status()
    mpv_pid = (status or {}).get("child", 0)
    # The relay's pid is the control socket's peer, never another process's
    # parent; it is signalled only through a pidfd opened while its command
    # line reads as this tree's relay of THIS player.
    rfd = (rig.pidfd(relay_pid, "relay") if relay_pid > 1 and rig.seen.get(relay_pid) == "relay"
           and rig.relay_child(relay_pid) == mpv_pid else None)
    mfd = rig.pidfd(mpv_pid, "mpv") if mpv_pid > 1 else None
    rig.check("R16 premise: the relay answers, and its pid and its player's read as this run's",
              rfd is not None and mfd is not None, "relay %d player %d" % (relay_pid, mpv_pid))
    if rfd is not None and mfd is not None:
        signal.pidfd_send_signal(rfd, signal.SIGKILL)
        killed = mark()
        gone = bool(select.select([mfd], [], [], 2.0)[0])
        rig.check("R16: the player is gone within 2 s of its relay's SIGKILL", gone)
        time.sleep(3.0)
        late = [e for e in LOG if e["t"] > killed + 0.3]
        rig.check("R16: no server logged a request after it", not late,
                  "%d: %s" % (len(late), ", ".join(e["server"] + " " + e["path"] for e in late[:3])))
    for fd in (rfd, mfd):
        if fd is not None:
            os.close(fd)
    rig.settle_gone(3.0)

    # R18: a loadfile from another IPC client, with no token.
    played(rig, "R18 public live channel", "pub", "LIVE public", "pub", "/m/ts/", least=1)
    since = mark()
    ok, _ = rig.ipc("loadfile", PUB + "/r18/other.ts", "replace")
    rig.check("R18 premise: the player took the other client's loadfile", ok)
    time.sleep(4.0)
    rig.check("R18: pub logged nothing for the entry nobody here loaded", not hits("pub", "/r18/", since),
              "%d request(s)" % len(hits("pub", "/r18/", since)))
    rig.stop()

    # R21 (D-PLY-66): a ZAP the relay refuses, and the question the shell asks
    # once the failed open has ended the player. The shell's side of it is
    # the node suite's; here the shipping helper and the real relay answer it
    # in the window the real relay leaves (RELAY_LINGER_S after its player).
    for label, name, want in (("R21 a zap redirected to 127.0.0.1", "R21 302 to this machine", True),
                              ("R21c a zap to a 404, the control", "R21 gone", False)):
        played(rig, label + ": a public live channel first", "pub", "LIVE public", "pub", "/m/ts/", least=1)
        rig.note_players()
        relay_pid, status = rig.relay_status()
        mpv_pid = (status or {}).get("child", 0)
        mfd = rig.pidfd(mpv_pid, "mpv") if mpv_pid > 1 else None
        since = mark()
        reply = rig.zap("pub", name, session=True)
        handle = (reply or {}).get("relay")
        handle = handle if isinstance(handle, dict) else {}
        rig.check("%s: the zap was applied and its reply names the relay's pid and a load number" % label,
                  (reply or {}).get("ok") is True and relay_pid > 1 and handle.get("pid") == relay_pid
                  and isinstance(handle.get("load"), int) and handle.get("load", 0) >= 2,
                  "got %s, relay %r, the relay's pid %d" % (code(reply), handle, relay_pid))
        gone = mfd is not None and bool(select.select([mfd], [], [], 10.0)[0])
        died = time.monotonic()
        rig.check("%s premise: the failed open ended the player" % label, gone)
        ask = ["player", "refused", "--socket", rig.sock, "--relay-pid", str(handle.get("pid", 0)),
               "--load", str(handle.get("load", 0))]
        rc, answer, _ = rig.helper_run(ask)
        took = time.monotonic() - died
        count = (answer or {}).get("refused")
        if want:
            rig.check("%s: asked once the player had gone, the relay answers that it refused the load" % label,
                      rc == 0 and isinstance(count, int) and not isinstance(count, bool) and count >= 1,
                      "exit %d, %r, %.2f s after the player's death" % (rc, answer, took))
            rig.check("%s: trap logged nothing under /r21/" % label, not hits("trap", "/r21/", since),
                      "%d request(s)" % len(hits("trap", "/r21/", since)))
        else:
            rig.check("%s: asked once the player had gone, the relay answers that it refused nothing" % label,
                      rc == 0 and count == 0 and not isinstance(count, bool),
                      "exit %d, %r, %.2f s after the player's death" % (rc, answer, took))
        print("NOTE %s: the answer came %.2f s after the player's death" % (label, took), flush=True)
        if mfd is not None:
            os.close(mfd)
        rig.settle_gone(5.0)
        rc, late, _ = rig.helper_run(ask)
        rig.check("%s: once the relay has gone too, the question answers null and is no error" % label,
                  rc == 0 and late == {"ok": True, "kind": "player.refused", "refused": None}, "exit %d, %r" % (rc, late))

    # R10: the session's proxy variables.
    proxy_env = {"http_proxy": UPROXY, "no_proxy": "*"}
    up_before = len(hits("uproxy"))
    refused(rig, "R10 no_proxy=* and http_proxy in the session", "pub", "R10 302 to this machine", ("pub", "/r10/"),
            [("trap", "/r10/")], extra_env=proxy_env)
    mpvs = [pid for pid, what in rig.seen.items() if what == "mpv" and rig.ours(pid) == "mpv"]
    if not mpvs:
        rig.start("pub", "LIVE public", extra_env=proxy_env)
        mpvs = [pid for pid, what in rig.seen.items() if what == "mpv" and rig.ours(pid) == "mpv"]
    names = environ_names(mpvs[0]) if mpvs else None
    rig.check("R10: the player's environment holds no lowercase http_proxy or no_proxy",
              names is not None and not {"http_proxy", "no_proxy"} & names,
              "player %s, names %s" % (mpvs[:1], sorted({"http_proxy", "no_proxy"} & (names or set()))))
    rig.check("R10: uproxy logged nothing", len(hits("uproxy")) == up_before, "%d" % (len(hits("uproxy")) - up_before))
    rig.stop()

    # R11: the user's mpv.conf.
    conf = os.path.join(rig.home, ".config", "mpv", "mpv.conf")
    with open(conf, "w") as fh:
        fh.write("http-proxy=%s\ndemuxer-lavf-o=http_proxy=%s\n[protocol.http]\nhttp-proxy=%s\n"
                 "stream-lavf-o=http_proxy=%s\n" % (UPROXY, UPROXY, UPROXY, UPROXY))
    try:
        up_before = len(hits("uproxy"))
        refused(rig, "R11a mpv.conf proxies, 302 to 127.0.0.1", "pub", "R11A 302 to this machine", ("pub", "/r11a/"),
                [("trap", "/r11a/")])
        refused(rig, "R11b mpv.conf proxies, HLS variant on 127.0.0.1", "pub", "R11B HLS variant on this machine",
                ("pub", "/r11b/"), [("trap", "/r11b/")])
        played(rig, "R11c mpv.conf proxies, HLS control", "pub", "C11 HLS control", "pub", "/m/ts/", least=2)
        rig.check("R11: uproxy logged nothing", len(hits("uproxy")) == up_before, "%d" % (len(hits("uproxy")) - up_before))
        rig.stop()
    finally:
        os.unlink(conf)

    # R12: --http-proxy as a token.
    up_before = len(hits("uproxy"))
    reply = played(rig, "R12 --http-proxy token, HLS control", "pub", "C11 HLS control", "pub", "/m/ts/", least=2,
                   mpv_extra=("--http-proxy=" + UPROXY,))
    rig.check("R12: the start's reply says the token was dropped",
              "dropped mpvArg --http-proxy" in (reply or {}).get("warnings", []), "warnings %r" % (reply or {}).get("warnings"))
    _, status = rig.relay_status()
    rig.check("R12: the control went through the relay", (status or {}).get("upstream", 0) > 0)
    rig.check("R12: uproxy logged nothing", len(hits("uproxy")) == up_before, "%d" % (len(hits("uproxy")) - up_before))


if __name__ == "__main__":
    sys.exit(main())
