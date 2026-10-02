#!/usr/bin/env python3
"""The sink, observed: a stdlib HTTP server that logs every request line
(method, path, User-Agent) to LOGFILE and answers 404 to all of them.

Usage: probe_server.py PORT LOGFILE

Started by run.sh in this directory and by nothing else. It never serves a
file: the question the spike asks is whether a request ARRIVES, and a 404
answers it as well as a 200 while keeping the content of the reply out of
the measurement (a RichText element that received an image would lay it
out, which is a second effect the spike does not measure).
"""
import http.server
import socketserver
import sys

PORT = int(sys.argv[1])
LOG = sys.argv[2]


class Handler(http.server.BaseHTTPRequestHandler):
    def _log(self):
        with open(LOG, "a") as f:
            f.write("%s %s UA=%r\n" % (self.command, self.path, self.headers.get("User-Agent")))
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_HEAD = do_POST = _log

    def log_message(self, *args):
        pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


with Server(("127.0.0.1", PORT), Handler) as server:
    server.serve_forever()
