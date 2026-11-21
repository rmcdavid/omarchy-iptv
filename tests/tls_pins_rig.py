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
NOT exercised is the service, which the live arm and player-scenario cover.
On a tree with the relay (D-SINK-102) the player is started by the tree's own
detached spawn beside its own relay; see "The relay" below.

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
and with it the provider header the case set. Every server also logs each
connection it ACCEPTS, and a TLS server whether its side of the handshake
completed (F-HARNESS-111), so "the attacker gets nothing" can be told apart
from "nothing ever reached the attacker".

The relay (F-HARNESS-111, 2026-11-21). Since D-SINK-102 a tree's
apply_channel registers each load with the player's relay before it sends a
line (relay_register: the relay must answer as the player's ancestor), and
its read-back refuses a player whose `http-proxy` is not that relay's pin.
This rig used to start mpv as its own child with the pin naming port 0 and
no relay, so on such a tree every load was refused `not_running` before
anything was sent: W1..W6 and the other "nothing reaches it" checks passed
for that reason, and every control was red. Now, for a tree that has the
relay:
  - the player is started the way `player start` starts it: the tree's own
    bind_relay_listeners binds the proxy listener and the control socket,
    the tree's own mpv_launch_argv composes the argv with that port in the
    pin, and the tree's own spawn_player forks the tree's own `player relay
    --child=<mpv>` as mpv's parent, mpv's environment the case's through the
    tree's player_environment. The rig still adds `--config-dir`, `--vo=null
    --ao=null` and drops `--force-window`, as before; and it waits for the
    relay with the tree's wait_for_relay, as adopt_or_spawn does (R0).
  - every load the rig makes is registered under the rule the tree's own
    player_target composes for a channel of a local playlist FILE
    (relay_rule): local and not a loopback relay, a local playlist's rule
    (a file's, or a LAN host's: _class_refusal reads them alike), under
    which the relay lets every connection to 127.0.0.1 through on any port.
    A typed --url's rule and a loopback relay playlist's both hold loopback
    to one host:port after the first connection, so the attacker's HLS
    segment on 8781 under the provider's 8780 would have been the relay's
    refusal, vacuous again for a new reason. C3 alone, the loopback relay
    playlist, is loaded as the tree loads it: the target, its headers and
    its rule are the tree's player_target over C3's own cache.
  - each "the attacker gets nothing" check (tls_held) now requires the load
    SENT, the attacker's ACCEPT of the player's connection, no request after
    it, a certificate error line from the player, and the relay's own counts
    (asked by its pid) showing an upstream connection and no destination
    refusal; the checks refused by design before any connection (W9, W17,
    W18 at the read-back through readback_held, W9 and W18 with the relay
    pin read back as held; W30 at the build gate) say so in their line and
    require that refusal's own code, never `not_running` from a relay that
    did not answer: W30's code is the gate's `not_running`, which is also
    relay_register's, so W30 requires that its case's relay answered. C6 is
    their positive control through the relay.
  - the --pre-pin tree (v0.15.0, no relay) composes its own argv; the tree's
    relay pin is appended to it and the player is started beside the tree's
    relay: the model of a player of the tree under test whose other options
    were changed at runtime, which still holds this build's pin from the
    command line. Where that tree loads the channel such a player was
    playing (W17's first channel) it cannot register it, so the rig does,
    and sets that load's per-file proxy value as the player's http-proxy
    first (feed). W28b, the pre-pin tree loading its own player, keeps no
    relay: that is its control, unchanged.
  - this rig is a child subreaper, so the relay the double fork reparents is
    reaped here; every signal goes through a pidfd opened on a pid the rig
    recorded (the spawn's report for mpv, the relay's own status answer for
    the relay) and only while /proc still reads it as this case's.
  - R2b: the player's exit status is its relay's to read now, not the rig's;
    it reads that the player exited on `quit` with nothing on stderr.
  - nothing it starts outlives it. The spawn's setsid puts a relay and its
    mpv in a session of their own, which a signal to this rig's process
    group (GNU timeout's, the gate's wrapper) does not reach, and the relay
    watches only its child, never its own parent. So SIGTERM, SIGHUP and
    SIGINT (each unless it was ignored when the rig started) end the rig
    through SystemExit (stop_on_signal), every `finally` runs, and
    Player.finish kills each player it still holds through its pidfd after
    a short grace, then its relay; a player started inside a deferred stop
    (deferred_stop, around the spawn and its Player) is registered first,
    and main's own `finally` finishes any player still registered (LIVE). A
    second signal while it stops is ignored, so the stop runs to its end.
  - an entry the helper did not load (W14, W22) meets the launch pin, which
    carries no token, and stops at the relay before any server. So that
    the header's absence is measured and not only implied, the rig
    registers a token of its OWN for such an entry and appends it with that
    per-file `http-proxy` and nothing else: it then reaches the lab server
    as it does on a player with no relay, under the global options mpv
    restored when the channel's file ended.
Baselines: a tree without the relay (anything before D-SINK-102, e.g.
`--baseline v0.19.1` or the --pre-pin default) runs exactly as before, its
player this rig's own child; a tree with it runs as above. A `--pre-pin` ref
with the relay composes its own pin and is started under the tree's relay,
supported in code and not run; two cases assume a pre-pin tree from BEFORE
the pins and are red by design on a later one: W17's premise (the
player's mpv.conf `reset-on-next-file=all`, which a pinned tree's own launch
argv overrides, so the next load is sent rather than refused) and W28b's
control (the pre-pin tree's own load with a demuxer tls_verify=0 must reach
the attacker, which a pinned tree's own pins stop).

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
      channel's provider header does not reach it, and the entry is fetched
      (on a player with a relay under a token the rig registers for it,
      "The relay" above); the channel's own request must carry the header
  W15 the paste-to-playlist key (D-PLY-46): with the user's own input.conf
      binding ctrl+v to append a URL -- the deterministic stand-in for mpv's
      clipboard binding, which a headless player has no clipboard for -- the
      key appends nothing (the playlist holds one entry straight after the
      key, and the entry it would append is never fetched, even after
      playlist-next)
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
      that port is fetched, and the channel plays with the Cookie, loaded as
      the tree's player_target composes it from C3's own cache (on a tree
      with the relay, under that playlist's rule: loopback held to its port)

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
      channel plays is fetched without the channel's provider header (on a
      player with a relay under a token the rig registers for it, "The
      relay" above)
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
(W19..W21, W24, W25 and W27's no-token control also require that the load
reached its server, F-HARNESS-111: "nothing listens" holds for a load that
was never sent.)

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
  W29 the user's tokens (D-SINK-47) -- one carrying the secret, one with
      `,`, quotes, `#` and a trailing backslash -- take effect in a real
      player whose /proc/<pid>/cmdline holds none of them, only the name of
      the private options file, which is gone once the socket answers

Restart on adoption (lane RA, 2026-11-01): the tree's apply_channel now
refuses any player another build launched before it sends anything (the
build gate, judged on SO_PEERCRED and the player's /proc/<pid>/cmdline), and
every player here is one the rig itself spawned, its argv the tree's less
--force-window, which reads as another build's. So the rig VOUCHES for the
pid it spawned, as `player start` vouches for the pid it launched, and every
W case keeps testing what it tested; the pre-pin cases (W9, W17, W18, W26b,
W28a) then model a player of this build whose state was changed at runtime,
the one the TLS layers still guard (design 6), and W9's refusal must be the
TLS one, not the gate's. Without the split they would pass for the wrong
reason. Added:
  W30 the pre-pin player fed by the tree's UNVOUCHED apply_channel (the
      keepLoaded old Service's `play` after an update, D-SINK-70): refused by
      the gate, with nothing sent -- tls-verify still reads mpv's default,
      nothing loaded -- and the attacker gets nothing
  R1  the tree's own player: /proc/<pid>/cmdline is the exec argv byte for
      byte, the build marker in it once (lane RA's M1, M2)
  R2  its script-opts hold the marker's key and the tree's build, and (R2b)
      nothing is logged at error level (M2)
  R3  SO_PEERCRED on a client of its socket names it (M3)
  R4  pause set before the load (the restart's --keep-pause): file-loaded
      arrives and the player stays paused; volume, mute and fullscreen set
      before the first load survive it (M4)
  R5  `quit` over IPC: a second client sees end-file reason quit, then EOF (M5)
A --baseline tree before the gate reds R1 and W30 (no marker, no gate).

F-HARNESS-111 (2026-11-21) adds, on a tree with the relay:
  R0  the tree's own relay answers as its player's (wait_for_relay)
  C6  a load the RIG sends itself through the tree's relay, under the same
      rule, with tls-verify turned off over IPC and no read-back: the
      attacker's log shows the request with the provider header, and the
      relay counts the upstream connection -- so a TLS check that saw no
      request was not blinded by the relay

usage: tls_pins_rig.py --tree DIR [--pre-pin DIR] --work DIR
Exit 0 green, 1 red, 77 when mpv, ffmpeg or openssl is missing. Stdlib only.
"""
from __future__ import annotations

import http.server
import contextlib
import inspect
import json
import os
import re
import resource
import select
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time

PORTS = {"provider": 8780, "attacker": 8781, "hlsok": 8782, "alt": 8783, "plain": 8784, "lab": 8785, "rtsp": 8807}
CONN_LOG = "connections.log"
# F-HARNESS-111: how long a relay may take to exit once its player has gone
# (it answers RELAY_LINGER_S, 1 s, more, then stops), before the rig asks it
# to stop through its pidfd.
RELAY_EXIT_S = 6.0
# The longest control-socket path a case makes, the relay's sun_path bound
# (RELAY_SUN_PATH_MAX): checked once, before anything starts.
LONGEST_CASE = "W27-none"
SUN_PATH_MAX = 107
PR_SET_CHILD_SUBREAPER = 36
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

    # F-HARNESS-111: every connection this server accepts, and for a TLS
    # server whether its handshake completed, in a log of its own beside the
    # request log. A request in the request log needs a completed handshake;
    # an accept whose handshake failed is a client that reached this server
    # and then refused it -- TLS's refusal, not the relay's, which would
    # have left no accept at all.
    conn_log = os.path.join(os.path.dirname(log), CONN_LOG)

    def note(record: dict) -> None:
        fd = os.open(conn_log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a") as fh:
            fh.write(json.dumps(record) + "\n")

    class Server(http.server.ThreadingHTTPServer):
        seen = 0
        last = 0.0

        def get_request(self):
            sock, addr = self.socket.accept()
            record = {"server": name, "tls": "none"}
            try:
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
                # Bounded, so a client that never says hello cannot hold
                # this accept loop for the cases after it.
                sock.settimeout(10)
                try:
                    tls = ctx.wrap_socket(sock, server_side=True)
                except OSError:
                    record["tls"] = "failed"
                    sock.close()
                    raise
                tls.settimeout(None)
                record["tls"] = "ok"
                return tls, addr
            finally:
                note(record)

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


def start_servers(work: str, rig: dict[str, str], procs: list[subprocess.Popen]) -> list[subprocess.Popen]:
    """Start every server, each appended to `procs` as it starts (main's
    `finally` stops what is there, a stop signal mid-way included)."""
    c = rig["certs"]
    log = os.path.join(work, "requests.log")
    for path in (log, os.path.join(work, CONN_LOG)):
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600))
        os.chmod(path, 0o600)
    specs = {
        "provider": (c + "/good.pem", c + "/good.key", "", "", "https://127.0.0.1:%d/seg.ts" % PORTS["attacker"]),
        "attacker": (c + "/evil.pem", c + "/evil.key", "", "", ""),
        "hlsok": (c + "/good.pem", c + "/good.key", "", "", "https://127.0.0.1:%d/seg.ts" % PORTS["hlsok"]),
        "alt": (c + "/good.pem", c + "/good.key", c + "/name.pem", c + "/name.key", "https://127.0.0.1:%d/seg.ts" % PORTS["alt"]),
        "plain": ("", "", "", "", ""),
        "lab": ("", "", "", "", ""),
    }
    procs.append(subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "--serve-rtsp", str(PORTS["rtsp"]),
                                   rig["www"], log], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL))
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


def connections(work: str) -> list[dict]:
    """Every connection a server accepted (serve's `note`), in order."""
    with open(os.path.join(work, CONN_LOG)) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def load_helper(tree: str) -> dict:
    stub = os.path.join(tree, "bin", "omarchy-iptv")
    ns = {"__name__": "tls_pins_rig_helper", "__file__": stub}
    with open(stub, "rb") as fh:
        exec(compile(fh.read(), stub, "exec", dont_inherit=True), ns)
    return ns


# ------------------------------------------------------------ the players
#
# F-HARNESS-111 (2026-11-21). Since D-SINK-102 a tree's apply_channel first
# registers the load with the player's relay (relay_register), which must
# answer as the player's ANCESTOR on its control socket, and its read-back
# refuses a player whose `http-proxy` is not that relay's pin. The rig used
# to start mpv itself with no relay and the pin naming port 0, so every load
# into a tree with the relay was refused `not_running` before anything was
# sent: the W checks that want "the attacker gets nothing" passed for that
# reason and the controls could not pass. So a player of a tree with the
# relay is now started by that tree's OWN spawn: its bind_relay_listeners
# binds the two listeners, the launch argv names the proxy listener's port,
# and its spawn_player forks the relay (`player relay --child=<mpv>`, the
# tree's own stub) with mpv as its child, exactly as `player start` does.
# What the rig still chooses is mpv's argv on top of the tree's (its
# `--config-dir`, `--vo=null --ao=null`, no `--force-window`) and the
# player's environment (the case's private HOME and XDG tree, through the
# tree's player_environment). A tree before D-SINK-102 starts as it always
# did, as this rig's own child.

# The review of 0c435d0: the spawn's setsid puts a relay and its mpv in a
# session of their own, out of reach of a signal to this rig's process group
# (GNU timeout signals its whole group), and the relay exits only after its
# child. A rig ended by the default SIGTERM ran no `finally`, so the case's
# relay and an mpv idling for its load under --idle=once outlived it. Now a
# stop signal is SystemExit, every `finally` runs, and every player this rig
# holds is finished: those still registered in LIVE by main's own `finally`.
STOP = {"signal": 0, "defer": 0}
LIVE: list = []


def stop_on_signal(signum: int, frame) -> None:
    """SIGTERM, SIGHUP, SIGINT: end the rig through SystemExit, so every
    `finally` runs. A second signal while it stops is ignored, so the stop
    runs to its end; one inside deferred_stop is raised when that ends."""
    if STOP["signal"]:
        return
    STOP["signal"] = signum
    if not STOP["defer"]:
        raise SystemExit(128 + signum)


def stop_point() -> None:
    """Raise the stop a signal asked for, if one did and nothing defers it
    (also the backstop for a SystemExit something swallowed)."""
    if STOP["signal"] and not STOP["defer"]:
        raise SystemExit(128 + STOP["signal"])


@contextlib.contextmanager
def deferred_stop():
    """No stop between a spawn and the Player that registers what it started
    (a signal there is raised once the Player exists). Signals are DEFERRED,
    never masked: a mask would be inherited by the relay and mpv the spawn
    execs, and change how the shipping relay hears its SIGTERM."""
    STOP["defer"] += 1
    try:
        yield
    finally:
        STOP["defer"] -= 1
    stop_point()


def has_relay(ns: dict) -> bool:
    """Whether this tree pins its player to a relay it spawns (D-SINK-102)."""
    return all(name in ns for name in ("relay_register", "bind_relay_listeners", "spawn_player",
                                       "wait_for_relay", "relay_status", "relay_request", "mpv_relay_pin"))


_RULES: dict[int, dict] = {}


def relay_rule(ns: dict, work: str) -> dict:
    """The rule every load the rig registers with a relay is judged by (C3's
    excepted): the one `ns`'s own player_target composes for a channel of a
    playlist that is a local FILE, read off player_target over a one-channel
    cache that says so (rule 12: called, not copied). Chosen because it is a
    local playlist's rule -- a file's, or a LAN host's, which _class_refusal
    reads alike -- under which the relay lets every connection to this
    machine through: local and not a loopback relay, so _class_refusal
    holds no loopback address to a port. A typed --url's rule
    holds every connection after the first to the URL's own host AND port on
    loopback, and so does a loopback relay playlist's, so the attacker's
    segment on another port of 127.0.0.1 would be the RELAY's refusal and
    the TLS checks vacuous again for a new reason (the brief's trap (a))."""
    if id(ns) not in _RULES:
        where = os.path.join(work, "relay-rule-%d" % len(_RULES))
        os.makedirs(where, mode=0o700)
        document = {"sourceHost": "local file",
                    "channels": [{"id": "rig-rule", "name": "Rule", "url": "http://127.0.0.1:%d/rule.ts" % PORTS["plain"]}]}
        fd = os.open(os.path.join(where, "channels.json"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(document, fh)
        _RULES[id(ns)] = dict(ns["player_target"]("rig-rule", "", where)["relay"])
    return dict(_RULES[id(ns)])


def pidfd_done(fd: int | None, timeout: float) -> bool:
    """Whether the process behind the pidfd `fd` has exited, waiting up to
    `timeout` seconds (a pidfd is readable once its process has exited)."""
    if fd is None:
        return True
    ready, _, _ = select.select([fd], [], [], max(0.0, timeout))
    return bool(ready)


def cmdline_of(pid: int) -> list[bytes]:
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as fh:
            return [part for part in fh.read().split(b"\0") if part]
    except OSError:
        return []


def pump(fd: int, path: str) -> threading.Thread:
    """mpv's stderr, from the pipe the tree's spawn hands back, into the
    case's mpv.stderr for the player's whole life (the shipping helper reads
    it only for the launch window, PO-6; the rig is an observer)."""
    def run() -> None:
        os.set_blocking(fd, True)
        try:
            out_fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(out_fd, "ab") as out:
                while True:
                    try:
                        chunk = os.read(fd, 65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    out.write(chunk)
        finally:
            os.close(fd)
    thread = threading.Thread(target=run, name="tls-rig-stderr", daemon=True)
    thread.start()
    return thread


class Player:
    """One player this rig started, held by the pid its own start reported
    and a pidfd opened on it at once. Every signal goes through a pidfd, and
    only while /proc still reads the process as this case's player (its
    `--config-dir` element) -- or, for its relay, as this tree's `player
    relay --child=<that pid>` -- checked before the signal, with the pidfd
    then proving it is still the process that was read. Nothing is ever
    signalled by a pid read off another process's ancestry: the relay's pid
    is the relay's own answer on its control socket (SO_PEERCRED)."""

    def __init__(self, pid: int, marker: str, popen: subprocess.Popen | None = None) -> None:
        self.pid = pid
        self.marker = os.fsencode(marker)
        self.popen = popen
        try:
            self.fd: int | None = os.pidfd_open(pid)
        except OSError:
            self.fd = None
        self.relayed = False
        self.relay_port = 0
        self.relay_pid = 0
        self.relay_fd: int | None = None
        self.reader: threading.Thread | None = None
        self.returncode: int | None = None
        self.killed = False
        LIVE.append(self)

    def alive(self) -> bool:
        if self.popen is not None:
            return self.popen.poll() is None
        return not pidfd_done(self.fd, 0)

    def wait(self, timeout: float) -> bool:
        if self.popen is not None:
            try:
                self.returncode = self.popen.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                return False
            return True
        return pidfd_done(self.fd, timeout)

    def kill(self) -> None:
        if self.fd is not None and self.marker in cmdline_of(self.pid):
            try:
                signal.pidfd_send_signal(self.fd, signal.SIGKILL)
            except OSError:
                pass

    def attach_relay(self, ns: dict, sock: str, stub: str) -> bool:
        """The relay the tree's spawn started answers as this player's
        (the tree's own wait_for_relay, as adopt_or_spawn asks it), and its
        pid is held: from its status answer, and only while its command line
        reads as `stub`'s relay of this player."""
        if not ns["wait_for_relay"](sock, (self.pid,), self.relay_port):
            return False
        reply = ns["relay_status"](sock, self.pid, self.relay_port) or {}
        pid = reply.get("_pid")
        if not isinstance(pid, int) or pid <= 1:
            return False
        try:
            fd = os.pidfd_open(pid)
        except OSError:
            return False
        argv = cmdline_of(pid)
        ok = (argv[-3:] == [b"player", b"relay", b"--child=%d" % self.pid]
              and os.fsencode(os.path.realpath(stub)) in argv)
        try:
            signal.pidfd_send_signal(fd, 0)
        except OSError:
            ok = False
        if not ok:
            os.close(fd)
            return False
        self.relay_pid, self.relay_fd = pid, fd
        return True

    def relay_counts(self, ns: dict, sock: str) -> dict | None:
        """The relay's own counts for this player's life so far: the upstream
        connections it made and the requests it refused by destination.
        Asked of the relay BY ITS PID (relay_request's `relay_pid`, as
        relay_refused_count asks it), because a player whose load failed has
        usually exited under --idle=once by now and the ancestor check can
        no longer be made; the relay answers RELAY_LINGER_S after it."""
        if self.relay_fd is None:
            return None
        reply = ns["relay_request"](sock, {"op": "status"}, 0, relay_pid=self.relay_pid)
        if not isinstance(reply, dict) or reply.get("ok") is not True or reply.get("port") != self.relay_port:
            return None
        return {"upstream": reply.get("upstream"), "refused": reply.get("refused")}

    def signal_relay(self, number: int) -> None:
        if self.relay_fd is not None and cmdline_of(self.relay_pid)[-1:] == [b"--child=%d" % self.pid]:
            try:
                signal.pidfd_send_signal(self.relay_fd, number)
            except OSError:
                pass

    def finish(self, grace: float = 8.0) -> None:
        """Wait for the player (after the caller's `quit`), SIGKILL it past
        `grace`; then its relay, which exits RELAY_LINGER_S after its child:
        asked to stop past RELAY_EXIT_S, killed 5 s after that, and reaped
        (this rig is a child subreaper, so the double fork lands it here);
        and an mpv whose relay went first, which lands here too. While the
        rig stops on a signal no `quit` was sent, so the grace is short."""
        try:
            self._finish(0.5 if STOP["signal"] else grace)
        finally:
            if self in LIVE:
                LIVE.remove(self)

    def _finish(self, grace: float) -> None:
        if not self.wait(grace):
            self.killed = True
            self.kill()
            self.wait(5.0)
        if self.relay_fd is not None:
            if not pidfd_done(self.relay_fd, RELAY_EXIT_S):
                self.signal_relay(signal.SIGTERM)
                if not pidfd_done(self.relay_fd, 5.0):
                    self.signal_relay(signal.SIGKILL)
                    pidfd_done(self.relay_fd, 5.0)
            try:
                os.waitid(os.P_PIDFD, self.relay_fd, os.WEXITED | os.WNOHANG)
            except ChildProcessError:
                pass
            os.close(self.relay_fd)
            self.relay_fd = None
        if self.popen is None and self.fd is not None:
            try:
                os.waitid(os.P_PIDFD, self.fd, os.WEXITED | os.WNOHANG)
            except ChildProcessError:
                pass
        if self.reader is not None:
            self.reader.join(5.0)
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def case_env(base: str) -> dict:
    env = {k: v for k, v in os.environ.items()
           if k not in ("DISPLAY", "WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE", "DBUS_SESSION_BUS_ADDRESS", "MPV_HOME")}
    env.update(HOME=base + "/home", XDG_CACHE_HOME=base + "/cache", XDG_STATE_HOME=base + "/state",
               XDG_CONFIG_HOME=base + "/config", XDG_DATA_HOME=base + "/data", XDG_RUNTIME_DIR=base + "/run")
    return env


def launch(base: str, runtime: str, env: dict, argv_ns: dict, logic_ns: dict,
           tokens: list[str]) -> tuple[Player, list[str], str]:
    """Start one windowless player: its argv `argv_ns`'s own mpv_launch_argv
    (less --force-window), and, when `logic_ns` -- the tree that will load
    it -- has the relay, started by `logic_ns`'s own spawn beside that
    tree's relay, the argv's pin naming the relay's port. An `argv_ns`
    before the relay (the --pre-pin tree) composes no pin, so the relay
    pin `logic_ns` composes is appended last: the model of a player of the
    tree under test whose other options were changed at runtime (restart on
    adoption's design 6), which holds that tree's relay pin from the command
    line as every player it launches does. -> the player, its exec argv,
    and the private options file it was handed ("" when none)."""
    sock = os.path.join(runtime, "mpv.sock")
    dirs = argv_ns["player_dirs"](sock, os.path.join(base, "state", "omarchy-iptv"))
    relayed = has_relay(logic_ns)
    proxy = control = None
    port = 0
    if relayed:
        proxy, control = logic_ns["bind_relay_listeners"](sock)
        port = proxy.getsockname()[1]
    try:
        compose = argv_ns["mpv_launch_argv"]
        if relayed and "relay_port" in inspect.signature(compose).parameters:
            argv = compose("mpv.sock", tokens, dirs, relay_port=port)
        else:
            argv = compose("mpv.sock", tokens, dirs)
            if relayed:
                argv = argv + [logic_ns["mpv_relay_pin"](port)]
        # lane-p2a (D-SINK-47): a tree whose launch argv names the private
        # options file gets it written as its own adopt_or_spawn writes it --
        # the user's tokens and the raw ones past the filter, in order -- and
        # removed once the socket answers, as the helper removes it. A tree
        # before it carries the tokens on the argv itself.
        options = dirs.get("mpvArgs", "")
        if options and "write_mpv_args" in argv_ns and any(a == "--include=" + options for a in argv):
            argv_ns["write_mpv_args"](options, tokens)
        else:
            options = ""
        marker = "--config-dir=" + base + "/config/mpv"
        cmd = ["mpv", marker, "--vo=null", "--ao=null"] + [a for a in argv[1:] if not a.startswith("--force-window")]
        errpath = os.path.join(base, "mpv.stderr")
        stop_point()
        if relayed:
            penv = logic_ns["player_environment"](env) if "player_environment" in logic_ns else dict(env)
            # Deferred, so a stop signal cannot land between the spawn and the
            # Player that registers what it started (LIVE).
            with deferred_stop():
                launched = logic_ns["spawn_player"](cmd, runtime, proxy.fileno(), control.fileno(), env=penv)
                player = Player(launched["pid"], marker)
                player.reader = pump(launched["stderrFd"], errpath)
                player.relayed, player.relay_port = True, port
        else:
            fd = os.open(errpath, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as err, deferred_stop():
                popen = subprocess.Popen(cmd, cwd=runtime, env=env, stdin=subprocess.DEVNULL, stdout=err, stderr=err,
                                         preexec_fn=no_core)
                player = Player(popen.pid, marker, popen)
    finally:
        # adopt_or_spawn's shape: the relay holds its own copies now.
        for held in (proxy, control):
            if held is not None:
                held.close()
    return player, cmd, options


def feed(ns: dict, client, target: dict, player: Player, work: str, relay_ns: dict | None = None,
         vouch: bool = True, rule: dict | None = None, **kw):
    """One channel through `ns`'s own apply_channel. A tree with the relay
    is handed the relay rule on the target, where player_target would have
    put its own: `rule` when the caller has the one player_target composed
    (C3), else relay_rule's. A tree WITHOUT one feeding a player that has a
    relay (the --pre-pin tree loading the channel an adopted player was
    playing, W17) cannot register the load, so the rig registers it with
    `relay_ns`'s relay_register and sets that load's per-file proxy value
    as the player's http-proxy before the load: what this build's load of
    that channel would have left the player holding. Restart on adoption:
    the rig vouches for the pid it spawned, as `player start` vouches for
    the pid it launched, unless `vouch` is False (W30)."""
    target = dict(target)
    if has_relay(ns):
        target["relay"] = dict(rule) if rule is not None else relay_rule(ns, work)
    elif relay_ns is not None and player.relayed:
        proxy, _ = relay_ns["relay_register"](client.path, {"relay": relay_rule(relay_ns, work)}, player.pid)
        client.try_command("set_property", "http-proxy", proxy)
    if vouch and "vouched_pid" in inspect.signature(ns["apply_channel"]).parameters:
        kw["vouched_pid"] = player.pid
    return ns["apply_channel"](client, target, **kw)


def bypass_load(ns: dict, client, target: dict, player: Player, work: str) -> None:
    """C6 only, and the rig's own load, NOT the tree's: registered with the
    player's relay under relay_rule and composed by the tree's own
    channel_load_options, but with `tls-verify` set false over IPC first and
    no read-back. It is the positive control that the TLS checks above can
    go red through the relay: the attacker's log must show its request."""
    target = dict(target, relay=relay_rule(ns, work))
    proxy, _ = ns["relay_register"](client.path, target, player.pid)
    client.try_command("set_property", "tls-verify", False)
    options = ns["channel_load_options"](target, ns["default_user_agent"](client), proxy)
    client.command("loadfile", target["url"], "replace", -1, options)


def appended(url: str, flag: str):
    """A post command (probe's `post`) that appends `url` as an entry the
    helper did not load, composed when it runs. On a player with a relay the
    entry would meet the launch pin, which carries no token, and stop at the
    relay before any server, so the header's absence would be implied, not
    measured (the review of 0c435d0). So there the rig registers a token of
    its OWN for the entry under relay_rule and appends it with that per-file
    `http-proxy` and nothing else: the entry then reaches the lab server
    under the options mpv restored when the channel's file ended, as it does
    on a player with no relay, and a provider header that reached it is
    seen."""
    def compose(ns: dict, client, player: Player, work: str) -> list:
        if not player.relayed:
            return ["loadfile", url, flag]
        proxy, _ = ns["relay_register"](client.path, {"relay": relay_rule(ns, work)}, player.pid)
        return ["loadfile", url, flag, -1, {ns["MPV_HTTP_PROXY_PROP"]: proxy}]
    return compose


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
          drawwatch=False, cmdline_words=(), vouch=True, after_post=(), bypass=False, rule=None) -> dict:
    stop_point()
    base = os.path.join(work, "cases", case)
    for sub in ("home", "cache", "state", "config/mpv", "data", "run/omarchy-iptv"):
        os.makedirs(os.path.join(base, sub), mode=0o700, exist_ok=True)
    with open(os.path.join(base, "config", "mpv", "mpv.conf"), "w") as fh:
        fh.write(conf)
    with open(os.path.join(base, "config", "mpv", "input.conf"), "w") as fh:
        fh.write(inputconf)
    env = case_env(base)
    runtime = os.path.join(base, "run", "omarchy-iptv")
    sock = os.path.join(runtime, "mpv.sock")
    kept, rejected = argv_ns["filter_mpv_args"](list(user))
    before = len(requests(work))
    cbefore = len(connections(work))
    jb = journal()
    old = os.getcwd()
    os.chdir(runtime)
    result = {"case": case, "rejected": rejected, "applied": None, "timePos": None, "props": {}, "kids": [], "post": [],
              "listening": [], "ends": [], "drawn": [], "errlines": [], "cmdlineHas": None, "afterPost": [],
              "relayed": has_relay(logic_ns), "relay": None, "relayCounts": None}
    watcher = None
    player = None
    try:
        player, _, options = launch(base, runtime, env, argv_ns, logic_ns, kept + list(raw))
        client = logic_ns["wait_for_socket"]("mpv.sock", 8.0, 3.0)
        if options and "remove_mpv_args" in argv_ns:
            result["optionsFile"] = os.path.lexists(options)
            argv_ns["remove_mpv_args"](options)
        if cmdline_words:
            # lane-p2a (D-SINK-47): what /proc shows every account, read off
            # the player itself while it runs. Which words, never the line.
            line = b"\0".join(cmdline_of(player.pid)).decode("utf-8", "replace")
            result["cmdlineHas"] = [word for word in cmdline_words if word in line] if line else None
        if client is None:
            result["error"] = "no socket"
        else:
            if player.relayed:
                # F-HARNESS-111: the tree's relay answers as this player's,
                # as adopt_or_spawn asks before it hands the player on.
                result["relay"] = player.attach_relay(logic_ns, sock, logic_ns["__file__"])
            if drawwatch:
                # lane-p1c, W23: a second client at mpv's TRACE level sees
                # every command a script runs to draw -- `show-text`, an OSD
                # overlay, a line handed to the console -- with its text.
                watcher = logic_ns["MpvIpc"]("mpv.sock", 3.0)
                watcher.connect()
                watcher.try_command("request_log_messages", "trace")
            if migrate:
                kw = ({"relay_port": player.relay_port}
                      if player.relayed and "relay_port" in inspect.signature(logic_ns["migrate_tls"]).parameters else {})
                result["migrate"] = logic_ns["migrate_tls"](client, **kw)
                if "pin_adopted_player" in logic_ns:
                    logic_ns["pin_adopted_player"](client, sock)
            try:
                client.try_command("request_log_messages", "error")
                if first_url:
                    # The channel the player was playing when it was adopted:
                    # loaded by the tree that LAUNCHED it (argv_ns), as the
                    # shell before the upgrade loaded it.
                    feed(argv_ns, client, {"id": "", "url": first_url, "name": "Rig First",
                                           "headers": {HEADER: HEADER_VALUE}, "group": ""},
                         player, work, relay_ns=logic_ns)
                    time.sleep(1.5)
                    ok, pos = client.try_command("get_property", "time-pos")
                    result["firstPlayed"] = bool(ok) and isinstance(pos, (int, float))
                target = {"id": "", "url": url, "name": "Rig Channel",
                          "headers": dict(headers) if headers is not None else {HEADER: HEADER_VALUE}, "group": ""}
                if bypass:
                    bypass_load(logic_ns, client, target, player, work)
                else:
                    feed(logic_ns, client, target, player, work, vouch=vouch, rule=rule)
                result["applied"] = True
            except logic_ns["HelperError"] as error:
                result["applied"] = False
                result["refusal"] = getattr(error, "code", "")
                if result["refusal"] == "tls_unverified" and "read_profile_threats" in logic_ns:
                    # Which reading refused it, as counts and a boolean: the
                    # per-file profiles that could undo a loose pin, and
                    # whether the relay pin itself was held.
                    try:
                        result["threats"] = logic_ns["read_profile_threats"](client)
                        if player.relayed:
                            ok, value = client.try_command("get_property", "http-proxy")
                            result["pinHeld"] = bool(ok) and logic_ns["relay_proxy_held"](value, player.relay_port)
                    except logic_ns["HelperError"]:
                        pass
            started = time.monotonic()
            pending = list(post)
            while time.monotonic() - started < seconds and player.alive():
                try:
                    ok, pos = client.try_command("get_property", "time-pos")
                    if ok and isinstance(pos, (int, float)):
                        result["timePos"] = pos
                    for prop in watch:
                        ok, value = client.try_command("get_property", prop)
                        if ok:
                            result["props"][prop] = value
                    for held in listening(player.pid):
                        if held not in result["listening"]:
                            result["listening"].append(held)
                except logic_ns["HelperError"]:
                    break
                stop_point()
                while pending and time.monotonic() - started >= pending[0][0]:
                    command = pending.pop(0)[1]
                    if callable(command):
                        # Composed now, against this case's player and relay
                        # (appended(), W14 and W22).
                        command = command(logic_ns, client, player, work)
                    reply = client.request(command, allow_close=True)
                    result["post"].append(reply.get("error"))
                    time.sleep(1.0)
                    result["kids"] += kids_with_secret(player.pid)
                    # W15: what the post command left, read before the next
                    # one runs (a playlist-next would otherwise hide it).
                    for prop in after_post:
                        try:
                            ok, value = client.try_command("get_property", prop)
                        except logic_ns["HelperError"]:
                            ok, value = False, None
                        result["afterPost"].append(value if ok else None)
                if watcher is not None:
                    drain_draws(watcher, result)
                if player.relayed:
                    result["relayCounts"] = player.relay_counts(logic_ns, sock) or result["relayCounts"]
                time.sleep(0.25)
            # F-HARNESS-111: the relay's own counts, last, while it still
            # answers (it lingers RELAY_LINGER_S after its player).
            if player.relayed:
                result["relayCounts"] = player.relay_counts(logic_ns, sock) or result["relayCounts"]
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
        if player is not None:
            player.finish()
    time.sleep(0.3)
    result["requests"] = requests(work)[before:]
    result["conns"] = connections(work)[cbefore:]
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


def launch_checks(work: str, tree: dict, url: str) -> list[tuple[str, bool, str]]:
    """R1-R5 (restart on adoption, lane RA's M1-M5 as assertions): the tree's
    own player, windowless, its argv the tree's (less --force-window), the
    channel a plain-http file on the rig's own server, loaded by the tree's
    apply_channel with the pid the rig spawned vouched for."""
    stop_point()
    out: list[tuple[str, bool, str]] = []
    if "player_build" not in tree:
        return [("R1 the launch argv names the build (M1, M2)", False, "this tree composes no build marker")]
    base = os.path.join(work, "cases", "R")
    for sub in ("home", "cache", "state", "config/mpv", "data", "run/omarchy-iptv"):
        os.makedirs(os.path.join(base, sub), mode=0o700, exist_ok=True)
    open(os.path.join(base, "config", "mpv", "mpv.conf"), "w").close()
    env = case_env(base)
    runtime = os.path.join(base, "run", "omarchy-iptv")
    marker = tree["mpv_build_marker"](tree["player_build"]())
    old = os.getcwd()
    os.chdir(runtime)
    player = None
    try:
        player, cmd, _ = launch(base, runtime, env, tree, tree, [])
        client = tree["wait_for_socket"]("mpv.sock", 8.0, 3.0)
        if client is None:
            return [("R1 the tree's player answers its socket", False, "no socket")]
        if player.relayed:
            attached = player.attach_relay(tree, os.path.join(runtime, "mpv.sock"), tree["__file__"])
            out.append(("R0 the tree's own relay answers as this player's, its parent (F-HARNESS-111)", attached,
                        "answered %s" % attached))
        got = cmdline_of(player.pid)
        want = [os.fsencode(a) for a in cmd]
        out.append(("R1 /proc/<pid>/cmdline is the exec argv byte for byte, the build marker in it once (M1, M2)",
                    got == want and got.count(os.fsencode(marker)) == 1,
                    "%d elements, equal %s, marker %d" % (len(got), got == want, got.count(os.fsencode(marker)))))
        ok, opts = client.try_command("get_property", "script-opts")
        key = tree["PLAYER_BUILD_KEY"]
        out.append(("R2 script-opts carry the build marker's key and the tree's build (M2)",
                    ok and isinstance(opts, dict) and opts.get(key) == tree["player_build"](),
                    "key there %s" % (isinstance(opts, dict) and key in opts)))
        out.append(("R3 SO_PEERCRED on a client of its socket names the player (M3)", client.peer_pid() == player.pid,
                    "peer %d, player %d" % (client.peer_pid(), player.pid)))
        for prop, value in (("volume", 37), ("mute", True), ("fullscreen", True)):
            client.try_command("set_property", prop, value)
        client.try_command("request_log_messages", "error")
        try:
            entry = feed(tree, client, {"id": "", "url": url, "name": "Rig R", "headers": {}, "group": ""}, player, work,
                         paused=True)
        except tree["HelperError"] as error:
            # F-HARNESS-111: a refused load is this check's failure, said as
            # one, never a traceback that ends the run with no count.
            return out + [("R4 paused before the load: file-loaded arrives and it stays paused (M4)", False,
                           "the load was refused as %s" % getattr(error, "code", ""))]
        first = tree["observe_first_load"](client, entry, 6.0)
        time.sleep(1.0)
        reads = {p: client.try_command("get_property", p)[1] for p in ("pause", "volume", "mute", "fullscreen", "time-pos")}
        time.sleep(1.0)
        later = client.try_command("get_property", "time-pos")[1]
        out.append(("R4 paused before the load: file-loaded arrives and it stays paused; volume, mute, fullscreen survive (M4)",
                    first.get("state") == "playing" and reads["pause"] is True and reads["volume"] == 37
                    and reads["mute"] is True and reads["fullscreen"] is True and later == reads["time-pos"],
                    "first load %s, %s, time-pos then %s" % (first.get("state"), reads, later)))
        observer = tree["MpvIpc"]("mpv.sock", 3.0)
        observer.connect()
        time.sleep(0.3)
        observer.events = []
        client.request(["quit"], allow_close=True)
        seen, eof = [], False
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            batch = observer.drain_events(min(deadline, time.monotonic() + 1.0))
            if batch is None:
                eof = True
                break
            seen += [str(e.get("reason")) for e in batch if e.get("event") == "end-file"]
        observer.close()
        client.close()
        out.append(("R5 quit over IPC: a second client sees end-file reason quit, then EOF (M5)", seen == ["quit"] and eof,
                    "end-files %s, EOF %s" % (seen, eof)))
    finally:
        os.chdir(old)
        if player is not None:
            player.finish()
    with open(os.path.join(base, "mpv.stderr"), "rb") as fh:
        logged = fh.read()
    # F-HARNESS-111: since D-SINK-102 the player's parent is its relay, which
    # reaps it, so its exit status is the relay's to read and not this
    # rig's; that it has exited is read off its pidfd.
    if player.popen is not None:
        exited, status = player.returncode == 0, "exit %s" % player.returncode
    else:
        exited, status = not player.killed, "exit status read by its relay (its parent), exited on quit %s" % (not player.killed)
    out.append(("R2b nothing at error level from the tree's player (M2)", logged == b"" and exited,
                "%d bytes, %s" % (len(logged), status)))
    return out


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


def accepted(result: dict, server: str) -> int:
    """Connections `server` accepted during the case."""
    return len([c for c in result["conns"] if c["server"] == server])


def tls_refused(result: dict, server: str) -> int:
    """Connections to `server` whose TLS handshake did not complete."""
    return len([c for c in result["conns"] if c["server"] == server and c["tls"] == "failed"])


def cert_errors(result: dict) -> int:
    """Error-level lines from the player that speak of a certificate (how
    many, never which)."""
    return len([line for line in result["errlines"] if "certificate" in line.lower()])


def tls_held(result: dict, server: str = "attacker") -> tuple[bool, str]:
    """F-HARNESS-111: "the attacker gets nothing", made non-vacuous. The load
    was SENT (apply_channel returned), the server ACCEPTED the player's
    connection, no request followed it, and the player logged a certificate
    error; on a player with a relay the relay also made the upstream
    connection and refused nothing by destination -- so the refusal is the
    player's TLS, not the relay's. A load that was never sent is red here,
    whatever the server logged: that is the shape this rig had while no
    relay answered it (F-HARNESS-111). Whether the server's side of the
    handshake completed is reported, not required: with this FFmpeg (n9.0.2,
    built with GnuTLS) it completed in every TLS case of the run that fixed
    this, and the client then sent nothing and logged the certificate error
    -- it judged the peer once its handshake was done -- where a client that
    checks during the handshake would end it with an alert. C6 is the same
    path with tls-verify off, and there the request arrives."""
    n, a, t = got(result, server), accepted(result, server), tls_refused(result, server)
    counts = result.get("relayCounts")
    via = ""
    relay_ok = True
    if result.get("relayed"):
        relay_ok = (isinstance(counts, dict) and counts.get("refused") == 0
                    and isinstance(counts.get("upstream"), int) and counts["upstream"] >= 1)
        via = "; its relay connected upstream %s time(s) and refused %s" % (
            (counts or {}).get("upstream"), (counts or {}).get("refused"))
    if result["applied"] is not True:
        return False, ("NOT SENT (refused as %s), so this case never reached TLS; the %s server accepted %d and got %d request(s)"
                       % (result.get("refusal"), server, a, n))
    return (n == 0 and a >= 1 and cert_errors(result) >= 1 and relay_ok,
            "sent; the %s server accepted %d connection(s) (%d handshake(s) completed on its side, %d failed) and got "
            "%d request(s); the player logged %d certificate error line(s)%s"
            % (server, a, a - t, t, n, cert_errors(result), via))


def readback_held(result: dict, server: str = "attacker") -> tuple[bool, str]:
    """For the cases refused BY DESIGN before any connection (an adopted
    pre-pin player the read-back will not load into): refused as
    `tls_unverified`, which is the read-back's code, never `not_running`
    (the relay's or the gate's), and the server saw nothing. Such a case
    cannot show a connection, and its line says so."""
    n, a = got(result, server), accepted(result, server)
    ok = result["applied"] is False and result.get("refusal") == "tls_unverified" and n == 0 and a == 0
    return ok, ("refused as %s, at the read-back, before any connection, so the %s server cannot show one here: "
                "it accepted %d and got %d request(s)" % (result.get("refusal"), server, a, n))


def reached(result: dict, server: str = "lab") -> bool:
    """F-HARNESS-111's sibling: a "nothing listens" or "nothing fetched"
    check is vacuous unless the load reached the server at all."""
    return got(result, server) > 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--serve"]:
        serve(argv[1], int(argv[2]), argv[3], argv[4], argv[5], argv[6], argv[7], argv[8], argv[9])
        return 0
    if argv[:1] == ["--serve-rtsp"]:
        serve_rtsp(int(argv[1]), argv[2], argv[3])
        return 0
    # The rig only, never a server: a stop signal is SystemExit, so every
    # `finally` runs and nothing this rig starts outlives it (stop_on_signal).
    # A signal ignored when the rig started stays ignored (nohup, a job
    # started with SIGINT ignored).
    for number in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        if signal.getsignal(number) is not signal.SIG_IGN:
            signal.signal(number, stop_on_signal)
    # One line per check, in order with the helper's own stderr lines.
    sys.stdout.reconfigure(line_buffering=True)
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
    longest = os.path.join(work, "cases", LONGEST_CASE, "run", "omarchy-iptv", "mpv.sock.relay")
    if len(os.fsencode(os.path.abspath(longest))) > SUN_PATH_MAX:
        print("REFUSING: the relay control socket of the longest case would be %d bytes, over sun_path's %d; "
              "set TMPDIR somewhere shorter" % (len(os.fsencode(os.path.abspath(longest))), SUN_PATH_MAX))
        return 2
    # F-HARNESS-111: the tree's spawn double-forks, so the relay it starts is
    # reparented on the way; as a child subreaper this rig is where it lands
    # and is reaped, not the session's own manager. And no proxy of the
    # caller's reaches a relay this rig starts (spawn_player hands the relay
    # this process's environment, and the relay chains to `http_proxy`).
    try:
        import ctypes
        reaper = ctypes.CDLL(None, use_errno=True).prctl(PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) == 0
    except (ImportError, OSError, AttributeError):
        reaper = False
    for name in list(os.environ):
        if name.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
            del os.environ[name]
    tree = load_helper(opts["--tree"])
    pre = load_helper(opts["--pre-pin"]) if opts["--pre-pin"] else None
    print("   the tree's players start %s; the --pre-pin tree's %s; this rig %s a child subreaper" % (
        "beside its own relay, through its own spawn_player" if has_relay(tree) else "with no relay, as this rig's children",
        ("(none given)" if pre is None else "under the tree's relay, the tree's relay pin appended to its argv"
         if has_relay(tree) and "relay_port" not in inspect.signature(pre["mpv_launch_argv"]).parameters
         else "under the tree's relay, its own argv naming the relay's port" if has_relay(tree) else "as the tree's do"),
        "is" if reaper else "is NOT"))
    procs: list[subprocess.Popen] = []
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
        # Inside the try, so a stop signal while the servers start still
        # stops the ones that did (start_servers fills `procs` as it goes).
        rig = make_rig(work)
        ca = "--tls-ca-file=" + rig["certs"] + "/ca.pem"
        start_servers(work, rig, procs)
        p, a = "https://127.0.0.1:%d" % PORTS["provider"], "https://127.0.0.1:%d" % PORTS["attacker"]
        hls = p + "/live/rig/%s/live.m3u8" % SECRET
        direct_evil = a + "/live/rig/%s/seg.ts" % SECRET
        r = run(["openssl", "verify", "-CAfile", rig["certs"] + "/ca.pem", rig["certs"] + "/good.pem", rig["certs"] + "/evil.pem"])
        check("G1 the rig discriminates: the provider's certificate verifies against the CA, the attacker's does not",
              "good.pem: OK" in r.stdout and "evil.pem: OK" not in r.stdout, "openssl verify")
        r = probe(work, "W1", tree, tree, hls, user=[ca, "--demuxer-lavf-o=tls_verify=0"])
        held, how = tls_held(r)
        check("W1 --demuxer-lavf-o=tls_verify=0 in mpvArgs: refused, and the attacker gets nothing",
              r["rejected"] == ["--demuxer-lavf-o=tls_verify=0"] and held,
              "rejected %d token(s); %s" % (len(r["rejected"]), how))
        r = probe(work, "W2", tree, tree, hls, user=[ca], raw=["--demuxer-lavf-o=tls_verify=0,live_start_index=-1"])
        held, how = tls_held(r)
        check("W2 the same key past the filter: the attacker gets nothing", held, how)
        time.sleep(1.5)
        r = probe(work, "W3", tree, tree, "https://127.0.0.1:%d/live/rig/%s/live.m3u8" % (PORTS["alt"], SECRET),
                  user=[ca], raw=["--demuxer-lavf-o=verifyhost=evil.test"])
        # F-HARNESS-111: the reopen reached `alt` (an accept beyond the one
        # that served the playlist) and made no request there.
        counts = r.get("relayCounts") or {}
        check("W3 verifyhost=<the attacker's own name> past the filter: the reopen is refused",
              r["applied"] is True and got(r, "alt") <= 1 and r["timePos"] is None
              and accepted(r, "alt") > got(r, "alt") and cert_errors(r) >= 1
              and (not r["relayed"] or counts.get("refused") == 0),
              "applied %s, alt accepted %d connection(s) (%d handshake(s) failed on its side) and got %d request(s), "
              "the player logged %d certificate error line(s), relay refused %s, played %s" % (
                  r["applied"], accepted(r, "alt"), tls_refused(r, "alt"), got(r, "alt"), cert_errors(r),
                  counts.get("refused"), r["timePos"] is not None))
        time.sleep(1.5)
        r = probe(work, "W4", tree, tree, direct_evil, conf="[protocol.https]\nstream-lavf-o=tls_verify=0\n")
        check("W4 [protocol.https] stream-lavf-o=tls_verify=0 in mpv.conf: the attacker gets nothing", *tls_held(r))
        r = probe(work, "W5", tree, tree, hls, user=[ca], conf="[protocol.https]\ndemuxer-lavf-o=tls_verify=0\n")
        check("W5 [protocol.https] demuxer-lavf-o=tls_verify=0 on HLS: the attacker gets nothing", *tls_held(r))
        r = probe(work, "W6", tree, tree, direct_evil, conf="[rigauto]\nprofile-cond=p.path ~= nil\ntls-verify=no\n")
        check("W6 a profile-cond profile with tls-verify=no: the attacker gets nothing", *tls_held(r))
        plain = "http://127.0.0.1:%d/live/rig/%s/long.ts" % (PORTS["plain"], SECRET)
        r = probe(work, "W7", tree, tree, plain, conf="save-watch-history=yes\n", seconds=3)
        check("W7 save-watch-history=yes in mpv.conf: no file outside the runtime folder holds the credential",
              r["leaks"] == [] and r["timePos"] is not None, "files %s, played %s" % (r["leaks"], r["timePos"] is not None))
        r = probe(work, "W8", tree, tree, "http://127.0.0.1:%d/live/rig/%s/sub.mkv" % (PORTS["plain"], SECRET), seconds=7,
                  post=[[1.5, ["set_property", "sid", 1]], [2.5, ["script-binding", "select/select-subtitle-line"]]])
        check("W8 select's subtitle-line binding: no child of the player carries the credential",
              r["kids"] == [] and r["timePos"] is not None,
              "children with it: %s, played %s" % (r["kids"], r["timePos"] is not None))
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
            # F-HARNESS-111: refused by the read-back, and for the PROFILE --
            # it counts the one per-file profile -- with the relay pin held,
            # so it is not the pin's absence that refused it.
            held, how = readback_held(r)
            check("W9 an adopted pre-pin player with that profile: the load is refused and the attacker gets nothing",
                  held and isinstance(r.get("threats"), int) and r["threats"] >= 1
                  and (not r["relayed"] or r.get("pinHeld") is True),
                  "%s; per-file profiles that undo a loose pin %s, relay pin held %s" % (
                      how, r.get("threats"), r.get("pinHeld")))
            # W30 (restart on adoption, D-SINK-70): the same pre-pin player fed
            # by the tree WITHOUT the rig's vouching -- the keepLoaded old
            # Service's `play` after an update: refused by the gate before the
            # TLS assertion's first set. The assertion would have turned
            # load-auto-profiles off and appended the protocol whitelist on a
            # v0.15.0 player (whose argv already says --tls-verify=yes), so
            # both still read as that player's own -- nothing was sent --
            # nothing is loaded, and the attacker gets nothing.
            if "feed_gate" in tree:
                r = probe(work, "W30", pre, tree, direct_evil, seconds=2, vouch=False,
                          watch=("load-auto-profiles", "demuxer-lavf-o", "idle-active"))
                demux = r["props"].get("demuxer-lavf-o")
                # Refused by the gate before any command, so the attacker can
                # show no connection here; that nothing reached it is read
                # off its accept log as well as its request log.
                check("W30 the pre-pin player fed by the tree's unvouched apply_channel: refused by the build gate with nothing sent, the attacker gets nothing",
                      r["applied"] is False and r.get("refusal") == "not_running" and got(r, "attacker") == 0
                      and accepted(r, "attacker") == 0
                      # The review of 0c435d0: `not_running` is also
                      # relay_register's code, so the case's relay must have
                      # answered, or a regressed gate behind a relay that
                      # did not start would read the same.
                      and (not r["relayed"] or r["relay"] is True)
                      and r["props"].get("load-auto-profiles") == "auto" and isinstance(demux, dict)
                      and "protocol_whitelist" not in demux and r["props"].get("idle-active") is True,
                      "applied %s, refused as %s before any command, load-auto-profiles %s, whitelist there %s, idle %s, "
                      "attacker accepted %d and got %d request(s), its relay answered %s" % (
                          r["applied"], r.get("refusal"), r["props"].get("load-auto-profiles"),
                          isinstance(demux, dict) and "protocol_whitelist" in demux, r["props"].get("idle-active"),
                          accepted(r, "attacker"), got(r, "attacker"), r["relay"]))
            else:
                check("W30 the pre-pin player fed by the tree's unvouched apply_channel: refused by the build gate",
                      False, "this tree has no build gate")
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
                  post=[[1.5, appended(lab + "/pasted.ts", "append-play")], [2.0, ["playlist-next"]]])
        pasted = lab_headers(r, "/pasted.ts")
        # F-HARNESS-111 and its review: on a player with a relay the entry
        # carries a token of the rig's own and nothing else (appended), so it
        # reaches the server there too, and "fetched" is required on every
        # tree: a pasted request with no header is the observation, where a
        # pasted request that never arrived implied it.
        check("W14 an entry the helper did not load: the channel's provider header does not reach it",
              pasted != [] and not any(HEADER_VALUE in json.dumps(h) for h in pasted)
              and any(HEADER_VALUE in json.dumps(h) for h in lab_headers(r, "/chan.ts")),
              "the channel's own request carried it %s; pasted requests %d, with the header %d%s" % (
                  any(HEADER_VALUE in json.dumps(h) for h in lab_headers(r, "/chan.ts")), len(pasted),
                  sum(HEADER_VALUE in json.dumps(h) for h in pasted),
                  "; the entry carried a token of the rig's own through the relay" if r["relayed"] else ""))
        r = probe(work, "W15", tree, tree, lab + "/chan2.ts", seconds=4,
                  inputconf="ctrl+v loadfile %s/pasted2.ts append-play\n" % lab,
                  # append-play only appends while a channel plays; the next
                  # entry is what fetches it.
                  post=[[1.5, ["keypress", "ctrl+v"]], [2.0, ["playlist-next"]]], after_post=("playlist-count",))
        # F-HARNESS-111: "never fetched" alone holds on a player with a relay
        # whether or not the key appended (the launch pin stops the entry),
        # and on a player that played nothing; so the playlist itself is read
        # straight after the key: one entry, the channel's.
        check("W15 the paste-to-playlist key appends nothing",
              lab_headers(r, "/pasted2.ts") == [] and r["afterPost"][:1] == [1] and reached(r),
              "playlist entries after the key %s, pasted requests %d, the channel reached the server %s" % (
                  r["afterPost"][:1], len(lab_headers(r, "/pasted2.ts")), reached(r)))
        before = len(requests(work))
        code, reply = helper_verb(opts["--tree"], work, "W16", "playlist", lab + "/redir.m3u", {"OMARCHY_IPTV_ORIGIN": "user"})
        admin = [x for x in requests(work)[before:] if x["server"] == "plain" and x["path"] == "/admin"]
        check("W16 a typed loopback source redirected to another port of the same address: refused, never contacted",
              code == 1 and (reply.get("error") or {}).get("code") == "local_address" and admin == [],
              "exit %d, code %s, the other port got %d" % (code, (reply.get("error") or {}).get("code"), len(admin)))
        if pre is not None:
            r = probe(work, "W17", pre, tree, hls, user=[ca, "--demuxer-lavf-o=tls_verify=0"], conf="reset-on-next-file=all\n",
                      first_url="http://127.0.0.1:%d/live/rig/%s/long.ts" % (PORTS["plain"], SECRET), seconds=5)
            # F-HARNESS-111: the channel the pre-pin tree loaded PLAYED (the
            # reset list backs up at a file's start), and the next load was
            # refused by the read-back, not by a relay that never answered.
            held, how = readback_held(r)
            check("W17 an adopted pre-pin player with reset-on-next-file=all: the next load is refused, the attacker gets nothing",
                  held and r.get("firstPlayed") is True,
                  "the first channel played %s; %s" % (r.get("firstPlayed"), how))
            r = probe(work, "W18", pre, tree, "http://127.0.0.1:%d/live/rig/%s/long.ts" % (PORTS["plain"], SECRET),
                      conf="[protocol.http]\nsave-watch-history=yes\n", migrate=True, seconds=3)
            # The review of 0c435d0: refused by the read-back before any
            # connection (the plain server, the channel's, saw nothing), for
            # the PROFILE -- the per-file profile counted -- with the relay
            # pin read back as held, so not for the pin's absence; W9's shape.
            held, how = readback_held(r, "plain")
            check("W18 an adopted pre-pin player whose per-file profile sets a non-TLS pin: refused, nothing written",
                  held and r["leaks"] == [] and isinstance(r.get("threats"), int) and r["threats"] >= 1
                  and (not r["relayed"] or r.get("pinHeld") is True),
                  "%s; per-file profiles that undo a loose pin %s, relay pin held %s, files %s" % (
                      how, r.get("threats"), r.get("pinHeld"), r["leaks"]))
        # ---- lane-p1c (2026-10-29): D-SINK-62..64, D-SINK-61, and the
        # kinds the format list keeps.
        if os.environ.get("OMARCHY_IPTV_RIG_NETNS") != "1":
            print("SKIP W19 W20 W21 W24 W25: they need unshare -rn (a baseline player would listen on this machine)")
        else:
            imf = [probe(work, "W19" + tag, tree, tree, lab + leaf, seconds=4)
                   for tag, leaf in (("a", "/imf1/cpl.xml"), ("b", "/imf2/cpl.xml"), ("c", "/imf3/cpl.xml"),
                                     ("d", "/imf4/x.ts"))]
            maps = sum(len([x for x in r["requests"] if x["path"].endswith("/ASSETMAP.xml")]) for r in imf)
            # F-HARNESS-111's siblings, W19-W21, W24, W25: "nothing listens"
            # holds for a load that was never sent, so each must have reached
            # the lab server.
            check("W19 a server that answers with an IMF composition playlist (tcp, tls and listen=2 assets, and as .ts): nothing listens, no ASSETMAP is fetched",
                  all(r["listening"] == [] and reached(r) for r in imf) and maps == 0,
                  "listening %s, ASSETMAP fetched %d, each reached the server %s" % (
                      [r["listening"] for r in imf], maps, [reached(r) for r in imf]))
            rel = probe(work, "W20a", tree, tree, lab + "/cc1/list.ts", seconds=4)
            unsafe = probe(work, "W20b", tree, tree, lab + "/cc2/list.ts", raw=["--demuxer-lavf-o=safe=0"], seconds=4)
            check("W20 an ffconcat file naming the CPL, and one naming a tcp listener under the user's safe=0: nothing listens",
                  rel["listening"] == [] and unsafe["listening"] == [] and reached(rel) and reached(unsafe),
                  "listening %s / %s, reached the server %s / %s" % (rel["listening"], unsafe["listening"],
                                                                     reached(rel), reached(unsafe)))
            r = probe(work, "W21", tree, tree, lab + "/dash/manifest.mpd", seconds=3)
            check("W21 a DASH manifest whose BaseURL is a tcp listener: nothing listens", r["listening"] == [] and reached(r),
                  "listening %s, reached the server %s" % (r["listening"], reached(r)))
            esc = '--demuxer-lavf-o=extension_picky=0,seg_format_options="format\\_whitelist=sdp:protocol\\_whitelist=rtp,udp"'
            told = probe(work, "W24a", tree, tree, lab + "/seg/v.m3u8", user=[esc], seconds=3)
            past = probe(work, "W24b", tree, tree, lab + "/seg/v.m3u8", raw=[esc], seconds=3)
            check("W24 the hls segment demuxer's options, escaped past every word: refused as a token, and past the filter nothing listens",
                  told["rejected"] == [esc] and told["listening"] == [] and past["listening"] == []
                  and reached(told) and reached(past),
                  "rejected %d, listening %s / %s, reached the server %s / %s" % (
                      len(told["rejected"]), told["listening"], past["listening"], reached(told), reached(past)))
            r = probe(work, "W25", tree, tree, lab + "/fc/list.ts", raw=["--demuxer-lavf-format=concat"], seconds=4)
            check("W25 a forced --demuxer-lavf-format=concat over an ffconcat file naming the CPL: nothing listens",
                  r["listening"] == [] and reached(r), "listening %s, reached the server %s" % (r["listening"], reached(r)))
        told = probe(work, "W22a", tree, tree, lab + "/pre/chan.ts", user=["--prefetch-playlist=yes"], seconds=5,
                     post=[[0.3, appended(lab + "/pre/next-a.ts", "append")], [3.5, ["playlist-next"]]])
        past = probe(work, "W22b", tree, tree, lab + "/pre/chan.ts", raw=["--prefetch-playlist=yes"], seconds=5,
                     post=[[0.3, appended(lab + "/pre/next-b.ts", "append")], [3.5, ["playlist-next"]]])
        conf = probe(work, "W22c", tree, tree, lab + "/pre/chan.ts", conf="prefetch-playlist=yes\n", seconds=5,
                     post=[[0.3, appended(lab + "/pre/next-c.ts", "append")], [3.5, ["playlist-next"]]])
        # The appended entry is fetched one way or the other: prefetched while
        # the channel's per-file options are live, or at the playlist-next.
        # On a player with a relay it carries a token of the rig's own and
        # nothing else (appended, the review of 0c435d0), so it reaches the
        # server at the playlist-next there too; a prefetch made under the
        # channel's per-file options would carry the channel's token and its
        # header (reasoned, not measured: the pin keeps prefetch off), and is
        # the leak this check is red for.
        cases = ((told, "a"), (past, "b"), (conf, "c"))
        nexts = [lab_headers(r, "/pre/next-%s.ts" % leaf) for r, leaf in cases]
        leaked = [h for got in nexts for h in got if HEADER_VALUE in json.dumps(h)]
        chans = [any(HEADER_VALUE in json.dumps(h) for h in lab_headers(r, "/pre/chan.ts")) for r, _ in cases]
        check("W22 prefetch-playlist on by token, past the filter and from mpv.conf: refused as a token, and an appended entry gets no provider header",
              told["rejected"] == ["--prefetch-playlist=yes"] and leaked == [] and all(chans)
              and all(got != [] for got in nexts),
              "rejected %d, each channel's own request carried the header %s, appended entry fetched %s, with the header %d%s" % (
                  len(told["rejected"]), chans, [len(got) for got in nexts], len(leaked),
                  "; each entry carried a token of the rig's own through the relay"
                  if any(r["relayed"] for r, _ in cases) else ""))
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
                  bound != [] and untold == [] and control["listening"] == [] and reached(control, "rtsp"),
                  "%d of %d spellings bind, %d of them unwarned %s; no token: listening %s, reached the server %s" % (
                      len(bound), len(rows), len(untold), untold, control["listening"], reached(control, "rtsp")))
        if pre is not None:
            off = probe(work, "W28a", pre, tree, hls, user=[ca], conf="demuxer-lavf-propagate-opts=no\n", migrate=True,
                        seconds=5, watch=("demuxer-lavf-propagate-opts",))
            ctl = probe(work, "W28b", pre, pre, hls, user=[ca], raw=["--demuxer-lavf-o=tls_verify=0"], seconds=5)
            held, how = tls_held(off)
            check("W28 an adopted pre-pin player whose plain mpv.conf turns propagation off: the attacker's HLS segment gets nothing (control: the pre-pin tree's own load with tls_verify=0 reaches it)",
                  off["props"].get("demuxer-lavf-propagate-opts") is False and held and got(ctl, "attacker") > 0,
                  "propagate %s; %s; control %d request(s)" % (off["props"].get("demuxer-lavf-propagate-opts"), how,
                                                               got(ctl, "attacker")))
        # D-SINK-47: the user's tokens reach the player through the private
        # options file, and only there.
        tok = ["--volume=37", "--script-opts=rigkey=%s" % SECRET, '--sub-font=a,b "c" #d e\\']
        r = probe(work, "W29", tree, tree, plain, user=tok, seconds=3, watch=("volume", "script-opts", "sub-font"),
                  cmdline_words=(SECRET, "rigkey", "--volume=37", "sub-font", "--include="), headers={})
        opts_file = os.path.join(work, "cases", "W29", "run", "omarchy-iptv", "mpv-args.conf")
        check("W29 the user's tokens -- one carrying a secret, one with `,`, quotes, `#` and a trailing backslash -- take effect in a real player whose command line holds none of them, only the private file's name, and that file is gone once the socket answers",
              r["timePos"] is not None and r["props"].get("volume") == 37.0
              and (r["props"].get("script-opts") or {}).get("rigkey") == SECRET and r["props"].get("sub-font") == tok[2][11:]
              and r["cmdlineHas"] == ["--include="] and r.get("optionsFile") is True and not os.path.lexists(opts_file),
              "played %s, volume %s, script-opts carries it %s, sub-font verbatim %s, command line holds %s, file there at the socket %s, after %s" % (
                  r["timePos"] is not None, r["props"].get("volume"),
                  (r["props"].get("script-opts") or {}).get("rigkey") == SECRET, r["props"].get("sub-font") == tok[2][11:],
                  r["cmdlineHas"], r.get("optionsFile"), os.path.lexists(opts_file)))
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
        # The review of 0c435d0: on a tree with the relay C3 is loaded as the
        # tree loads it -- the URL, the headers and the relay rule are the
        # tree's own player_target over C3's own cache, so the relay holds
        # loopback to this playlist's port, the shipping rule for the one
        # source shape C3 covers, not relay_rule's local-file one.
        c3_url, c3_headers, c3_rule, composed = lab + "/stream/1", {"Cookie": "relay=1"}, None, "relay_rule's"
        if has_relay(tree) and channels.get("channels"):
            try:
                c3 = tree["player_target"](str(channels["channels"][0].get("id") or ""), "",
                                           os.path.dirname(cache))
                c3_url, c3_headers, c3_rule = c3["url"], dict(c3.get("headers") or {}), dict(c3.get("relay") or {})
                composed = "player_target's (loopback %s, local %s, port %s)" % (
                    c3_rule.get("loopback"), c3_rule.get("local"), c3_rule.get("port"))
            except tree["HelperError"] as error:
                composed = "none: player_target refused it as %s" % getattr(error, "code", "")
        r = probe(work, "C3", tree, tree, c3_url, seconds=3, headers=c3_headers, rule=c3_rule)
        check("C3 a loopback relay on one port: its sign-in header is kept, its guide on that port fetched, its channel plays with it (control)",
              code == 0 and kept == [{"Cookie": "relay=1"}] and ecode == 0 and r["timePos"] is not None
              and any("relay=1" in json.dumps(h) for h in lab_headers(r, "/stream/1"))
              and (not has_relay(tree) or (c3_rule or {}).get("loopback") is True),
              "playlist exit %d, headers %s, guide exit %d, played %s%s" % (
                  code, kept, ecode, r["timePos"] is not None,
                  ", under the relay rule %s" % composed if has_relay(tree) else ""))
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
        if has_relay(tree):
            # F-HARNESS-111: the positive control of the TLS checks on a
            # player with a relay. The rig's own load (bypass_load), through
            # the tree's relay under the same rule, with tls-verify off: the
            # attacker's log shows the request, header and all, so a TLS
            # check above that saw none was not blinded by the relay.
            r = probe(work, "C6", tree, tree, direct_evil, seconds=3, bypass=True)
            counts = r.get("relayCounts") or {}
            hit = [x for x in r["requests"] if x["server"] == "attacker"]
            check("C6 a load the rig itself sends through the tree's relay with tls-verify off reaches the attacker (control)",
                  r["applied"] is True and hit != [] and all(x["header"] for x in hit) and counts.get("refused") == 0
                  and isinstance(counts.get("upstream"), int) and counts["upstream"] >= 1,
                  "attacker requests %d, with the header %d; its relay connected upstream %s time(s) and refused %s" % (
                      len(hit), len([x for x in hit if x["header"]]), counts.get("upstream"), counts.get("refused")))
        else:
            print("SKIP C6: this tree starts its player with no relay (before D-SINK-102); W28b is its control")
        for label, ok, detail in launch_checks(work, tree, "http://127.0.0.1:%d/live/rig/%s/long.ts" % (PORTS["plain"], SECRET)):
            check(label, ok, detail)
    finally:
        # Any player a stop signal left registered (LIVE), then the servers.
        for player in list(LIVE):
            player.finish()
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
