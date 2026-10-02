#!/usr/bin/env python3
"""The sink, observed: a stdlib HTTP server that logs EVERY request it gets
to LOGFILE -- the request line, then every header the client sent, name and
value, nothing dropped -- and answers 404 to all of them.

Usage: probe_server.py PORT LOGFILE

Log format, one block per request, blocks separated by a blank line:

    GET /a.png
      Host: 127.0.0.1:PORT
      User-Agent: Mozilla/5.0
      ...

The whole header set is kept because the question is not only WHETHER a
request arrives but WHAT it carries: the CHANGELOG used to say the fetch
carried "the address from the tag and a generic browser identification,
nothing else of yours" when nothing had logged the other headers, and a
server that logs only the User-Agent cannot show what else there is. This
one logs everything, and the CHANGELOG now names the five headers it found.
Loopback only, so the values logged are the ones Qt sends to a host it was
told nothing about.

Started by run.sh in this directory and by nothing else. It never serves a
file: a 404 shows that a request ARRIVED as well as a 200 would while keeping
the content of the reply out of the measurement (a RichText element that
received an image would lay it out, which is a second effect the spike does
not measure).
"""
import http.server
import socketserver
import sys

PORT = int(sys.argv[1])
LOG = sys.argv[2]


class Handler(http.server.BaseHTTPRequestHandler):
    def _log(self):
        lines = ["%s %s" % (self.command, self.path)]
        for name, value in self.headers.items():
            lines.append("  %s: %s" % (name, value))
        with open(LOG, "a") as f:
            f.write("\n".join(lines) + "\n\n")
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
