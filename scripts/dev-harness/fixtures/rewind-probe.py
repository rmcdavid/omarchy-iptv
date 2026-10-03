#!/usr/bin/env python3
"""scripts/dev-harness/fixtures/rewind-probe.py -- read the player, never the
helper. QA tooling for rewind-scenario.sh (M5-01); never shipped, never on
the plugin's allowlist.

Every R-check that says "time-pos moved" reads time-pos off mpv's own socket
through this file, so the observation is independent of the verb under test:
a helper that lied about `moved` would be caught by the number mpv reports.
The client matches replies by request_id and drops events, because a
`socat | head -1` can hand back an unsolicited event line instead of the
reply -- the mistake that voided the first M2-11 sweep (SPIKE-LIVE-REWIND
sweep.py `_send`).

Verbs (all print one JSON object; URLs are never read, so none is printed):

  get   SOCK PROP...            {"time-pos": 12.3, "pause": false, ...}
  range SOCK                    {"pos", "floor", "ceiling", "history", "ahead",
                                 "ranges": [[s, e], ...], "cacheEnd", "underrun"}
  seek  SOCK TARGET MODE        a RAW mpv seek (relative|absolute), then time-pos
                                read immediately and again 1.5 s later:
                                {"reply", "before", "after", "later", "moved"}
  measure SOCK SECONDS EVERY    samples `range` for SECONDS; reports the growth
                                of history in s per wall second (the stream
                                control, R0) and whether the floor moved
  wait  SOCK SECONDS            block until time-pos is numeric and advancing,
                                bounded; {"ok": bool, "pos": ..}

Exit 0 on an answer, 2 when the socket never answered within the bound.
"""

import json
import socket
import sys
import time

sys.dont_write_bytecode = True


class Ipc(object):
    def __init__(self, path, timeout=4.0):
        self.path = path
        self.timeout = timeout
        self.sock = None
        self.buffer = b""
        self.next_id = 1

    def connect(self, bound_s):
        deadline = time.monotonic() + bound_s
        while time.monotonic() < deadline:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            try:
                s.connect(self.path)
                self.sock = s
                return True
            except OSError:
                s.close()
                time.sleep(0.1)
        return False

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _readline(self, deadline):
        while True:
            nl = self.buffer.find(b"\n")
            if nl >= 0:
                line = self.buffer[:nl]
                self.buffer = self.buffer[nl + 1:]
                return line
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            try:
                self.sock.settimeout(max(0.05, min(1.0, left)))
                chunk = self.sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                return None
            if not chunk:
                return None
            self.buffer += chunk

    def command(self, *args):
        """(data, error) for THIS request id; events are skipped, never
        mistaken for the reply."""
        rid = self.next_id
        self.next_id += 1
        line = json.dumps({"command": list(args), "request_id": rid}) + "\n"
        try:
            self.sock.sendall(line.encode("utf-8"))
        except OSError as exc:
            return None, "send failed: %s" % exc.__class__.__name__
        deadline = time.monotonic() + self.timeout
        while True:
            raw = self._readline(deadline)
            if raw is None:
                return None, "no reply within %.1fs" % self.timeout
            try:
                msg = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(msg, dict) or msg.get("request_id") != rid:
                continue
            err = msg.get("error")
            return msg.get("data"), (None if err == "success" else (err or "unknown error"))

    def get(self, name):
        data, err = self.command("get_property", name)
        return None if err else data


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def range_of(ipc):
    """The numbers a rewind UI consults, derived the way the design's
    helper derives them: floor is seekable-ranges[r].start of the range
    the reader sits in, ceiling its end. Nothing here is a string from
    the stream."""
    pos = num(ipc.get("time-pos"))
    state = ipc.get("demuxer-cache-state")
    s = state if isinstance(state, dict) else {}
    ranges = []
    for r in s.get("seekable-ranges") or []:
        if isinstance(r, dict) and num(r.get("start")) is not None and num(r.get("end")) is not None:
            ranges.append([round(float(r["start"]), 3), round(float(r["end"]), 3)])
    floor = ceiling = None
    if ranges:
        hit = None
        if pos is not None:
            for r in ranges:
                if r[0] - 0.5 <= pos <= r[1] + 0.5:
                    hit = r
                    break
        if hit is None:
            hit = ranges[0]
        floor, ceiling = hit[0], hit[1]
    history = None if pos is None or floor is None else round(pos - floor, 3)
    ahead = None if pos is None or ceiling is None else round(ceiling - pos, 3)
    return {"pos": pos, "floor": floor, "ceiling": ceiling, "history": history, "ahead": ahead,
            "ranges": ranges, "cacheEnd": num(s.get("cache-end")), "underrun": s.get("underrun"),
            "paused": ipc.get("pause"), "pausedForCache": ipc.get("paused-for-cache")}


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    verb, sock_path = argv[0], argv[1]
    ipc = Ipc(sock_path)
    if not ipc.connect(5.0):
        print(json.dumps({"ok": False, "error": "no socket"}))
        return 2
    try:
        if verb == "get":
            out = {}
            for prop in argv[2:]:
                out[prop] = ipc.get(prop)
            print(json.dumps(out))
            return 0
        if verb == "range":
            print(json.dumps(range_of(ipc)))
            return 0
        if verb == "seek":
            target, mode = argv[2], argv[3] if len(argv) > 3 else "relative"
            before = num(ipc.get("time-pos"))
            _, err = ipc.command("seek", target, mode)
            after = num(ipc.get("time-pos"))
            time.sleep(1.5)
            later = num(ipc.get("time-pos"))
            moved = None if before is None or after is None else round(after - before, 3)
            print(json.dumps({"reply": err or "success", "before": before, "after": after,
                              "later": later, "moved": moved}))
            return 0
        if verb == "wait":
            bound = float(argv[2]) if len(argv) > 2 else 20.0
            deadline = time.monotonic() + bound
            last = None
            while time.monotonic() < deadline:
                pos = num(ipc.get("time-pos"))
                if pos is not None and last is not None and pos > last:
                    print(json.dumps({"ok": True, "pos": pos}))
                    return 0
                if pos is not None:
                    last = pos
                time.sleep(0.25)
            print(json.dumps({"ok": False, "pos": last}))
            return 0
        if verb == "measure":
            seconds = float(argv[2]) if len(argv) > 2 else 30.0
            every = float(argv[3]) if len(argv) > 3 else 2.0
            t0 = time.monotonic()
            samples = []
            while time.monotonic() - t0 < seconds:
                r = range_of(ipc)
                samples.append({"t": round(time.monotonic() - t0, 2), "pos": r["pos"], "floor": r["floor"],
                                "ceiling": r["ceiling"], "history": r["history"], "ahead": r["ahead"],
                                "underrun": r["underrun"]})
                time.sleep(every)
            good = [s for s in samples if s["history"] is not None]
            rate = None
            if len(good) >= 2:
                a, b = good[0], good[-1]
                if b["t"] > a["t"]:
                    rate = round((b["history"] - a["history"]) / (b["t"] - a["t"]), 3)
            floors = [s["floor"] for s in good]
            print(json.dumps({"samples": samples, "historyRatePerS": rate,
                              "floorMoved": bool(floors) and (max(floors) - min(floors) > 0.5),
                              "firstFloor": floors[0] if floors else None,
                              "lastFloor": floors[-1] if floors else None,
                              "lastHistory": good[-1]["history"] if good else None}))
            return 0
        print(json.dumps({"ok": False, "error": "unknown verb"}))
        return 2
    finally:
        ipc.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
