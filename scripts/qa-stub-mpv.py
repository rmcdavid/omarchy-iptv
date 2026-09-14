#!/usr/bin/env python3
"""scripts/qa-stub-mpv.py -- a stand-in for mpv that binds the JSON IPC socket.

WHY THIS EXISTS. PLY-H17 and PLY-H18 assert the two behaviours the D-PLY-11
fix introduced, and both of them turn on an ORDERING inside a cold start: a
channel change has to reach the player between the spawn and `player start`'s
own apply_channel. On a real mpv that window is about twenty milliseconds wide
and the scenario would be a coin flip. Here the ordering is decided by a gate
this stub holds open, so the scenario is 1/1 - which is what CLAUDE.md rule 11
needs from a check that has to be shown failing on another tree.

It also means both scenarios run with NO DISPLAY and NO SHELL: nothing here
opens a window, the helper is the only thing under test, and the socket lives
wherever the caller puts it.

It speaks only the part of mpv's protocol the helper uses: newline-delimited
JSON commands in, {"error":..,"data":..,"request_id":..} out, one thread per
client so the helper's handshake connection and the zap's connection are live
at the same time (they are, in the field).

  --input-ipc-server=PATH   bind here. Without it the stub sleeps and exits,
                            which is the "never binds" stub PLY-H15 needs.
Environment:
  STUB_LOG       append every request line here (default: no log)
  STUB_LIFE      seconds to stay up (default 60)
  STUB_GATE      path to a gate file. While it EXISTS, every reply on the
                 FIRST client connection is withheld; the file is removed by
                 the scenario once the zap has landed. `probe_client` will not
                 return until mpv answers `mpv-version`, and `cmd_play`
                 demands no such handshake, so holding the first connection
                 holds `player start` exactly where the field race puts it.
  STUB_IDLE_PROPS  comma-separated property names to report as unavailable
                 until the first loadfile, so a freshly spawned player looks
                 the way mpv 0.41 does (no user-data node of ours).

Not a test double for anything the product ships: it is QA tooling, it never
runs inside the plugin, and it never touches a path it was not given.
"""

import json
import os
import socket
import sys
import threading
import time

VERSION = "mpv 0.41.0 (qa-stub)"


class Stub(object):
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.loads = []
        self.clients = 0
        self.log_path = os.environ.get("STUB_LOG", "")
        self.gate = os.environ.get("STUB_GATE", "")
        self.props = {
            "mpv-version": VERSION,
            "pid": os.getpid(),
            "idle-active": True,
            "playlist-count": 0,
            "playlist": [],
            "playlist/current/id": None,
        }
        # Absent until something sets or loads them - mpv reports
        # "property unavailable" for these on an idle player, and the
        # stand-down decision reads exactly that difference.
        self.unset = set(["path", "media-title", "title", "force-media-title",
                          "user-data/omarchy-iptv", "user-data"])
        for name in os.environ.get("STUB_IDLE_PROPS", "").split(","):
            if name:
                self.unset.add(name)

    def log(self, line):
        if not self.log_path:
            return
        try:
            with open(self.log_path, "a") as fh:
                fh.write(line + "\n")
        except OSError:
            pass

    # ---- property access, with mpv's nested user-data addressing

    def get(self, name):
        with self.lock:
            if name in self.unset:
                return (None, "property unavailable")
            if name in self.props:
                return (self.props[name], None)
            if name.startswith("user-data/"):
                node = self.props.get("user-data")
                key = name.split("/", 1)[1]
                if isinstance(node, dict) and key in node:
                    return (node[key], None)
                return (None, "property unavailable")
            return (None, "property unavailable")

    def put(self, name, value):
        with self.lock:
            self.unset.discard(name)
            if name.startswith("user-data/"):
                node = self.props.get("user-data")
                if not isinstance(node, dict):
                    node = {}
                node[name.split("/", 1)[1]] = value
                self.props["user-data"] = node
                self.unset.discard("user-data")
            self.props[name] = value

    def loadfile(self, url):
        with self.lock:
            self.loads.append(url)
            n = len(self.loads)
            self.props["playlist-count"] = n
            self.props["playlist"] = [
                {"id": i + 1, "filename": u, "current": i == n - 1}
                for i, u in enumerate(self.loads)
            ]
            self.props["playlist/current/id"] = n
            self.props["idle-active"] = False
            self.unset.discard("path")
            self.props["path"] = url

    # ---- the gate: hold the first connection until the scenario releases it

    def hold(self, first):
        if not (first and self.gate):
            return
        limit = time.time() + 30
        while os.path.exists(self.gate) and time.time() < limit:
            time.sleep(0.01)

    def serve(self, conn):
        with self.lock:
            self.clients += 1
            first = self.clients == 1
        buf = b""
        while True:
            try:
                chunk = conn.recv(65536)
            except OSError:
                return
            if not chunk:
                return
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    req = json.loads(line.decode("utf-8", "replace"))
                except ValueError:
                    continue
                self.log("REQ " + line.decode("utf-8", "replace"))
                self.hold(first)
                reply = self.dispatch(req)
                if reply is None:
                    return
                try:
                    conn.sendall((json.dumps(reply) + "\n").encode("utf-8"))
                except OSError:
                    return
                self.log("REP " + json.dumps(reply))

    def dispatch(self, req):
        rid = req.get("request_id", 0)
        cmd = req.get("command") or []
        out = {"error": "success", "request_id": rid, "data": None}
        if not cmd:
            out["error"] = "invalid parameter"
            return out
        verb = cmd[0]
        if verb in ("get_property", "get_property_string"):
            value, err = self.get(cmd[1])
            if err:
                out["error"] = err
            elif verb == "get_property_string":
                out["data"] = value if isinstance(value, str) else json.dumps(value)
            else:
                out["data"] = value
        elif verb in ("set_property", "set_property_string"):
            self.put(cmd[1], cmd[2])
        elif verb == "loadfile":
            self.loadfile(cmd[1])
        elif verb == "quit":
            try:
                return out
            finally:
                threading.Timer(0.05, lambda: os._exit(0)).start()
        elif verb in ("observe_property", "unobserve_property",
                      "request_log_messages", "client_name", "enable_event",
                      "disable_event", "script-message", "ignore"):
            pass
        else:
            # Unknown verbs succeed rather than erroring: the helper treats an
            # error as a refusal and this stub is not a conformance test.
            pass
        return out


def main(argv):
    path = None
    for arg in argv:
        if arg.startswith("--input-ipc-server="):
            path = arg.split("=", 1)[1]
    if not path:
        # The "spawned but never binds" shape. Sleep past --spawn-timeout.
        time.sleep(float(os.environ.get("STUB_LIFE", "60")))
        return 0
    stub = Stub(path)
    try:
        os.unlink(path)
    except OSError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    os.chmod(path, 0o600)
    srv.listen(8)
    srv.settimeout(0.5)
    stub.log("BOUND %s pid=%d" % (path, os.getpid()))
    deadline = time.time() + float(os.environ.get("STUB_LIFE", "60"))
    while time.time() < deadline:
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        threading.Thread(target=stub.serve, args=(conn,)).start()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
