"""A PUBLIC provider on a machine that has none, with no seam (D-SINK-40).

Run INSIDE `unshare -rn` by tests/test_destinations.py: a private network
namespace whose only interfaces are its own loopback and a dummy one
carrying 11.0.0.1/32, an address the helper's real classifier calls global.
Nothing can leave the namespace, so a server on 11.0.0.1 stands for the
internet and one on 127.0.0.1 for this machine, and the SHIPPING helper runs
as a subprocess between them, exactly as the service runs it. Prints one
JSON object. Not a test module (unittest discovers test_*.py only).

usage: python3 -I netns_public.py <helper> <scratch dir>
"""
import http.server
import json
import os
import subprocess
import sys
import threading

HELPER, SCRATCH = sys.argv[1], sys.argv[2]
PLAYLIST = b"#EXTM3U\n#EXTINF:-1,Fine\nhttp://stream.example.test/a.m3u8\n#EXTINF:-1,Router\nhttp://192.168.1.1/cgi-bin/reboot.cgi\n"


def ip(*args):
    return subprocess.run(["ip", *args], capture_output=True, text=True).returncode == 0


ready = ip("link", "set", "lo", "up") and ip("link", "add", "d0", "type", "dummy") \
    and ip("link", "set", "d0", "up") and ip("addr", "add", "11.0.0.1/32", "dev", "d0")
if not ready:
    print(json.dumps({"skip": "no dummy interface in this namespace"}))
    sys.exit(0)

SEEN = []


def server(host, routes):
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_GET(self):
            SEEN.append("%s%s" % (host, self.path))
            status, headers, body = routes.get(self.path, (404, (), b""))
            self.send_response(status)
            for name, value in headers:
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

    httpd = http.server.ThreadingHTTPServer((host, 0), Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


lan = server("127.0.0.1", {"/admin": (200, (), PLAYLIST)})
public = server("11.0.0.1", {
    "/redirect.m3u": (302, (("Location", "http://127.0.0.1:%d/admin" % lan.server_address[1]),), b""),
    "/same.m3u": (302, (("Location", "/real.m3u"),), b""),
    "/real.m3u": (200, (), PLAYLIST),
})


def run(path, cache):
    env = {k: v for k, v in os.environ.items() if not k.startswith("OMARCHY_IPTV_") and "proxy" not in k.lower()}
    env.update({"OMARCHY_IPTV_URL": "http://11.0.0.1:%d%s" % (public.server_address[1], path), "OMARCHY_IPTV_ORIGIN": "user"})
    os.makedirs(cache, mode=0o700, exist_ok=True)
    done = subprocess.run([sys.executable, HELPER, "playlist", "--cache-dir", cache, "--timeout", "5"],
                          capture_output=True, text=True, env=env, timeout=60)
    lines = [l for l in done.stdout.splitlines() if l.strip()]
    status = json.loads(lines[-1]) if lines else None
    cached = None
    if os.path.exists(os.path.join(cache, "channels.json")):
        with open(os.path.join(cache, "channels.json"), encoding="utf-8") as fh:
            cached = json.load(fh)
    return status, cached


del SEEN[:]
refused, _ = run("/redirect.m3u", os.path.join(SCRATCH, "a"))
seen_refused = list(SEEN)
del SEEN[:]
followed, cached = run("/same.m3u", os.path.join(SCRATCH, "b"))
print(json.dumps({
    "redirect": {"code": ((refused or {}).get("error") or {}).get("code"), "seen": seen_refused},
    "same": {"ok": (followed or {}).get("ok"), "warnings": (followed or {}).get("warnings"),
             "sourceClass": (cached or {}).get("sourceClass"),
             "names": [c["name"] for c in (cached or {}).get("channels", [])], "seen": list(SEEN)},
}))
public.shutdown()
lan.shutdown()
