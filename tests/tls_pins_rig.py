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

PORTS = {"provider": 8780, "attacker": 8781, "hlsok": 8782, "alt": 8783, "plain": 8784}
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
                                     "ua": self.headers.get("User-Agent", "")}) + "\n")
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
    }
    procs = []
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


def probe(work: str, case: str, argv_ns: dict, logic_ns: dict, url: str, user=(), raw=(), conf="",
          seconds=5.0, post=(), migrate=False, watch=()) -> dict:
    base = os.path.join(work, "cases", case)
    for sub in ("home", "cache", "state", "config/mpv", "data", "run/omarchy-iptv"):
        os.makedirs(os.path.join(base, sub), mode=0o700, exist_ok=True)
    with open(os.path.join(base, "config", "mpv", "mpv.conf"), "w") as fh:
        fh.write(conf)
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
    result = {"case": case, "rejected": rejected, "applied": None, "timePos": None, "props": {}, "kids": [], "post": []}
    try:
        client = logic_ns["wait_for_socket"]("mpv.sock", 8.0, 3.0)
        if client is None:
            result["error"] = "no socket"
        else:
            if migrate:
                result["migrate"] = logic_ns["migrate_tls"](client)
                if "pin_adopted_player" in logic_ns:
                    logic_ns["pin_adopted_player"](client, os.path.join(runtime, "mpv.sock"))
            try:
                logic_ns["apply_channel"](client, {"id": "", "url": url, "name": "Rig Channel",
                                                    "headers": {HEADER: HEADER_VALUE}, "group": ""})
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
                except logic_ns["HelperError"]:
                    break
                while pending and time.monotonic() - started >= pending[0][0]:
                    reply = client.request(pending.pop(0)[1], allow_close=True)
                    result["post"].append(reply.get("error"))
                    time.sleep(1.0)
                    result["kids"] += kids_with_secret(player.pid)
                time.sleep(0.25)
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


def got(result: dict, server: str) -> int:
    return len([r for r in result["requests"] if r["server"] == server])


def main(argv: list[str]) -> int:
    if argv[:1] == ["--serve"]:
        serve(argv[1], int(argv[2]), argv[3], argv[4], argv[5], argv[6], argv[7], argv[8], argv[9])
        return 0
    opts = {"--tree": "", "--pre-pin": "", "--work": ""}
    i = 0
    while i < len(argv):
        if argv[i] not in opts or i + 1 >= len(argv):
            print("usage: tls_pins_rig.py --tree DIR [--pre-pin DIR] --work DIR")
            return 2
        opts[argv[i]] = argv[i + 1]
        i += 2
    for tool in ("mpv", "ffmpeg", "openssl", "journalctl"):
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
