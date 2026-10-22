"""A local HTTP(S) server whose every response is a SCRIPT: bytes to send and
short pauses between them, per path. For the fetch-deadline tests (R30e,
D-SRC-58, D-LOGO-15, D-LOGO-16, D-SRC-59).

What it is not, by the project's input rule: a server built to hold a
connection open indefinitely or to send without end. Every script is a
finite, ordinary small response, and every pause is a fixed fraction of a
second, a little longer than the deadline the test lowers; a pause ends at
once when the server is closed. A client that has given up and closed its
end costs the script a failed send, which is swallowed.

Not a test module (unittest discovers test_*.py only).
"""
import socket
import ssl
import threading

NOT_FOUND = (b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n",)


def response(status, headers=(), body=b""):
    """One ordinary HTTP/1.1 response as bytes, Content-Length and
    Connection: close included unless `headers` names them."""
    names = {name.lower() for name, _ in headers}
    lines = ["HTTP/1.1 %s" % status]
    lines += ["%s: %s" % pair for pair in headers]
    if "content-length" not in names and "transfer-encoding" not in names:
        lines.append("Content-Length: %d" % len(body))
    if "connection" not in names:
        lines.append("Connection: close")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body


class ScriptedServer:
    """`routes` maps a request path to a sequence of steps: bytes are sent,
    a float is a pause in seconds. `context` makes it TLS. `paths` records
    every request in arrival order; `url(path)` composes the address."""

    def __init__(self, routes, context=None):
        self.routes = dict(routes)
        self.context = context
        self.paths = []
        self.stopping = threading.Event()
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(16)
        self.listener.settimeout(0.1)
        self.port = self.listener.getsockname()[1]
        self.workers = []
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def url(self, path):
        return "%s://127.0.0.1:%d%s" % ("https" if self.context else "http", self.port, path)

    def close(self):
        self.stopping.set()
        try:
            self.listener.close()
        except OSError:
            pass
        self.thread.join(timeout=5)
        for worker in list(self.workers):
            worker.join(timeout=5)

    def _serve(self):
        while not self.stopping.is_set():
            try:
                conn, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            worker = threading.Thread(target=self._handle, args=(conn,), daemon=True)
            self.workers.append(worker)
            worker.start()

    def _handle(self, conn):
        try:
            conn.settimeout(5)
            if self.context is not None:
                conn = self.context.wrap_socket(conn, server_side=True)
            data = b""
            while b"\r\n\r\n" not in data and len(data) < 65536:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                data += chunk
            parts = data.split(b" ", 2)
            path = parts[1].decode("latin-1") if len(parts) > 1 else ""
            self.paths.append(path)
            for step in self.routes.get(path, NOT_FOUND):
                if isinstance(step, float):
                    if self.stopping.wait(step):
                        return
                else:
                    conn.sendall(step)
        except (OSError, ssl.SSLError, ValueError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass
