#!/usr/bin/env python3
"""serve-and-fetch.py -- put the corpus behind https and run the SHIPPING helper at it.

The one thing logo-scenario.sh cannot do in bash without a detached process:
`fetch_logo` is https-only (LOGO_SCHEMES), so a provider has to exist, and a
server started with `&` behind `setsid` is a pid read from `$!` that is not
the listener (CLAUDE.md, parallel rule 3). So the server lives in a THREAD of
this process and the helper is this process's CHILD: when the helper exits
the server is shut down and joined with a deadline, and when this process
exits there is nothing left to find or kill. No port is chosen -- the kernel
hands out an ephemeral one, so two lanes cannot collide on it.

    serve-and-fetch.py fetch --helper <bin/omarchy-iptv> --corpus <dir> --work <dir>
                             --names a.png,b.jpg,... [--plant a.png,...]
                             [--timeout <s>] [--tree-id <word>]
    serve-and-fetch.py refusal --helper <bin/omarchy-iptv> --corpus <dir>
                               --name <fixture> --url <https url>

`fetch` writes a channel cache under <work>/cache naming every fixture in
--names at https://localhost:<port>/<token>/<name>, copies every fixture in
--plant into the logo cache under the name the helper will look it up by
(a cache "written by 0.13.3", which never checked dimensions), runs
`<helper> logos --fetch --cache-dir <work>/cache` as a subprocess with
SSL_CERT_FILE pointed at the certificate this process just made, and reports:

    RIG port <n>
    RIG token <t>                  (the random path component every URL carries)
    RIG name <fixture> <fnv1a32>   (the cache name the helper derives for it)
    RIG helper rc <n> stdout <path> stderr <path>
    RIG get <fixture> <count>      (how many GETs the server logged for it)
    RIG logos-on-disk <n> <names>  (what the logo directory holds afterwards)

The helper's two streams go to files, never through this process's stdout,
so a credential in them cannot reach the transcript except through a check
that chose to print it. The token in the URL path is the thing the scenario's
rule 5 sweep looks for.

`refusal` loads the helper as a MODULE (bytecode writing off, so no
__pycache__ lands beside it) and prints what `logo_dimension_refusal` says
about one fixture, or `RIG absent` on a tree without that function. That is
the only place the helper is imported rather than run: the refusal text is
swallowed into a count by `logos --fetch`, so the sink it would reach is the
function's own return value, and rule 14 allows calling the shipping logic.

The certificate is EC prime256v1, self-signed, CN=localhost with a DNS SAN,
made by `openssl req` as an argv list (rule 2) and valid for two days. It is
written 0600 into --work and is worth nothing outside this process's life.

fnv1a32 is reimplemented here rather than imported, so that the planted
names are computed by something OTHER than the code under test: the scenario
then checks that the name the helper announces for the good logo is the name
this file computed (its V2), which turns the mirror into a verified join
(CLAUDE.md rule 13) rather than a copy nobody compares.

Python 3 standard library only, ASCII only.
"""

import argparse
import http.server
import importlib.machinery
import importlib.util
import json
import os
import secrets
import shutil
import socketserver
import ssl
import subprocess
import sys
import threading

CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def fnv1a32(value):
    hash_ = 0x811C9DC5
    for byte in str(value).encode("utf-8"):
        hash_ ^= byte
        hash_ = (hash_ * 0x01000193) & 0xFFFFFFFF
    return "%08x" % hash_


def private_dir(path):
    os.makedirs(path, mode=0o700, exist_ok=True)
    os.chmod(path, 0o700)


def make_certificate(work):
    key = os.path.join(work, "key.pem")
    cert = os.path.join(work, "cert.pem")
    argv = ["openssl", "req", "-x509", "-newkey", "ec",
            "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
            "-keyout", key, "-out", cert, "-days", "2",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"]
    subprocess.run(argv, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.chmod(key, 0o600)
    os.chmod(cert, 0o600)
    return cert, key


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def serve_corpus(corpus, token, cert, key):
    """A server answering GET /<token>/<fixture> from the corpus. Returns
    (server, thread, hits): hits is a dict fixture -> GET count, appended to
    under a lock by the handler and read after the helper has exited."""
    hits = {}
    lock = threading.Lock()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parts = self.path.lstrip("/").split("/")
            if len(parts) != 2 or parts[0] != token or "/" in parts[1] or parts[1].startswith("."):
                self.send_response(404)
                self.end_headers()
                return
            name = parts[1]
            path = os.path.join(corpus, name)
            with lock:
                hits[name] = hits.get(name, 0) + 1
            if not os.path.isfile(path):
                self.send_response(404)
                self.end_headers()
                return
            with open(path, "rb") as handle:
                data = handle.read()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPES.get(os.path.splitext(name)[1].lower(), "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = Server(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    thread.start()
    return server, thread, hits


def cmd_fetch(args):
    names = [n for n in args.names.split(",") if n]
    plant = [n for n in (args.plant or "").split(",") if n]
    for name in names + plant:
        if not os.path.isfile(os.path.join(args.corpus, name)):
            sys.stderr.write("serve-and-fetch: no fixture %s in %s\n" % (name, args.corpus))
            return 2
    private_dir(args.work)
    cache = os.path.join(args.work, "cache")
    logos = os.path.join(cache, "logos")
    home = os.path.join(args.work, "home")
    for path in (cache, logos, home):
        private_dir(path)
    cert, key = make_certificate(args.work)
    token = "t" + secrets.token_hex(6)
    server, thread, hits = serve_corpus(args.corpus, token, cert, key)
    port = server.server_address[1]
    print("RIG port %d" % port)
    print("RIG token %s" % token)

    def url_of(name):
        return "https://localhost:%d/%s/%s" % (port, token, name)

    channels = []
    seen = []
    for index, name in enumerate(names + [n for n in plant if n not in names]):
        if name in seen:
            continue
        seen.append(name)
        channels.append({"id": "logo-%d" % index, "name": "Logo %d" % index,
                         "url": "https://localhost:%d/stream/%d.ts" % (port, index),
                         "logo": url_of(name)})
        print("RIG name %s %s" % (name, fnv1a32(url_of(name))))
    with open(os.path.join(cache, "channels.json"), "w") as handle:
        json.dump({"version": 1, "channels": channels}, handle)
    os.chmod(os.path.join(cache, "channels.json"), 0o600)
    for name in plant:
        target = os.path.join(logos, fnv1a32(url_of(name)))
        shutil.copyfile(os.path.join(args.corpus, name), target)
        os.chmod(target, 0o600)
    out_path = os.path.join(args.work, "helper.out")
    err_path = os.path.join(args.work, "helper.err")
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin"),
        "HOME": home,
        "XDG_CACHE_HOME": os.path.join(home, "cache"),
        "XDG_STATE_HOME": os.path.join(home, "state"),
        "XDG_CONFIG_HOME": os.path.join(home, "config"),
        "XDG_RUNTIME_DIR": os.path.join(home, "run"),
        "SSL_CERT_FILE": cert,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    argv = [sys.executable, "-B", args.helper, "logos", "--fetch",
            "--cache-dir", cache, "--timeout", str(args.timeout)]
    try:
        with open(out_path, "wb") as out, open(err_path, "wb") as err:
            # Bounded (rule 3): the helper's own --timeout is per socket
            # operation, and this is the deadline on the whole run.
            proc = subprocess.run(argv, stdout=out, stderr=err, env=env, timeout=args.deadline)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        rc = -15
        with open(err_path, "ab") as err:
            err.write(b"serve-and-fetch: gave up after %d s and killed the helper\n" % args.deadline)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if thread.is_alive():
            print("RIG server thread did not stop within 5 s")
    os.chmod(out_path, 0o600)
    os.chmod(err_path, 0o600)
    print("RIG helper rc %d stdout %s stderr %s" % (rc, out_path, err_path))
    for name in seen:
        print("RIG get %s %d" % (name, hits.get(name, 0)))
    try:
        on_disk = sorted(os.listdir(logos))
    except OSError:
        on_disk = []
    print("RIG logos-on-disk %d %s" % (len(on_disk), " ".join(on_disk)))
    return 0


def load_helper(path):
    sys.dont_write_bytecode = True
    loader = importlib.machinery.SourceFileLoader("omarchy_iptv_under_test", path)
    spec = importlib.util.spec_from_loader("omarchy_iptv_under_test", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def cmd_refusal(args):
    path = os.path.join(args.corpus, args.name)
    with open(path, "rb") as handle:
        data = handle.read()
    ctype = CONTENT_TYPES.get(os.path.splitext(args.name)[1].lower(), "application/octet-stream")
    module = load_helper(args.helper)
    function = getattr(module, "logo_dimension_refusal", None)
    if function is None:
        print("RIG absent")
        return 0
    print("RIG refusal %s" % function(args.url, data, ctype))
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="verb", required=True)
    fetch = sub.add_parser("fetch")
    fetch.add_argument("--helper", required=True)
    fetch.add_argument("--corpus", required=True)
    fetch.add_argument("--work", required=True)
    fetch.add_argument("--names", required=True)
    fetch.add_argument("--plant", default="")
    fetch.add_argument("--timeout", type=float, default=5.0)
    fetch.add_argument("--deadline", type=int, default=60)
    refusal = sub.add_parser("refusal")
    refusal.add_argument("--helper", required=True)
    refusal.add_argument("--corpus", required=True)
    refusal.add_argument("--name", required=True)
    refusal.add_argument("--url", required=True)
    args = parser.parse_args(argv)
    if args.verb == "fetch":
        return cmd_fetch(args)
    return cmd_refusal(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
