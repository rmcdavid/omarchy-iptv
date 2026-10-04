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
  STUB_WINDOW_S  seconds of history the back buffer holds before the floor
                 starts to move (default 60). STUB_LEAD_S is the forward
                 cache ahead of the reader (default 3.6, what a 2 s-segment
                 HLS stream showed). STUB_STARTUP_S is how long after a
                 loadfile `time-pos` stays unavailable (default 0; mpv 0.41
                 took about 5 s on a real channel, SPIKE-LIVE-REWIND 11.1).

SEEK SEMANTICS (M5-01), no more forgiving than mpv 0.41 as measured in
docs/SPIKE-LIVE-REWIND.md 4.3, 11.1, 11.4 and 12.2 and on the harness's own
HLS stream (docs/QA-REWIND.md section 2):

  * `seek` ALWAYS replies `success`. mpv's reply is not evidence of movement
    and neither is this one; read `time-pos` to know.
  * a target inside `seekable-ranges[0]` moves `time-pos` to it exactly,
    which is what the immediate read after a landed seek echoes (72 of 72).
  * a target below the floor is DROPPED once the start of the stream has
    been evicted: `time-pos` does not move. While the start is still cached
    (floor 0) a RELATIVE over-long seek lands at 0.0, the clamp 4.3 saw.
  * a target past the range end is dropped the same way.
  * a NEGATIVE absolute target seeks from the cache end (12.2, 5 of 5).
  * every loadfile restarts the timeline at 0 and discards the history
    (11.1): nothing of the previous channel survives.
  * `pause` freezes `time-pos` but the cache end keeps growing, so once the
    window is full the floor moves one second per paused second (11.2): a
    pause eats the history.
  * `demuxer-cache-state` carries ONLY the twelve numeric and boolean leaves
    the helper forwards (M1: seekable-ranges[].start/end, cache-end,
    reader-pts, cache-duration, fw-bytes, total-bytes, underrun, idle, eof,
    eof-cached, bof-cached). No string leaf, nothing from the stream.
  * what follows the reply to `seek` is what mpv sends next (F-RWD-15): the
    position moves and the `seek` event goes out AFTER the reply has been
    written, never before, so a client that reads `time-pos` at once reads
    the old position the way it can on mpv; a dropped seek is followed by
    the error-level refusal line, to the connections that subscribed with
    `request_log_messages` and to no other. (An earlier version of this
    file emitted no line and moved the position before replying; the review
    of the integrated tree found both more forgiving than mpv.) One half
    stays unmodelled and is stated: mpv broadcasts the `seek` event to EVERY
    client, and this stub writes it only to the connection that issued the
    seek. The plugin opens one control connection per helper run, so no
    scenario can tell the difference; a test that needs the broadcast
    would be the first to.

`python3 scripts/qa-stub-mpv.py --self-test` runs the unittest cases that
pin these, against a fake clock. Each case was seen red by mutating the rule
it names (counts in docs/QA-REWIND.md section 5).

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


def _env_float(name, default):
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return float(default)


class Stub(object):
    def __init__(self, path, clock=time.monotonic):
        self.path = path
        self.clock = clock
        self.lock = threading.RLock()
        self.loads = []
        self.clients = 0
        # Live connections, and the subset that asked for log messages. Real
        # mpv BROADCASTS an event to every connected IPC client and answers a
        # command only to the client that sent it; a log message reaches only
        # the clients that subscribed. F-MPV-1 is this project's record of
        # what a double that gets this wrong costs: it made D-PLY-12's
        # triggering input inexpressible, because the bug was an event
        # arriving on a connection that did not cause it. The other two
        # doubles were fixed then; this one was not, and its M5-01 seek
        # followups went to the issuing connection alone until the lead
        # noticed the same shape while writing it up.
        self.conns = []
        self.log_conns = []
        self.log_path = os.environ.get("STUB_LOG", "")
        self.gate = os.environ.get("STUB_GATE", "")
        # The live-stream timeline (M5-01). `loaded_at` is None until the
        # first loadfile; after it, the cache end is wall seconds since the
        # load plus the lead, the reader is wall seconds minus the paused
        # time minus the seek offset, and the floor is the end minus the
        # window once the window has filled.
        self.window_s = _env_float("STUB_WINDOW_S", 60.0)
        self.lead_s = _env_float("STUB_LEAD_S", 3.6)
        self.startup_s = _env_float("STUB_STARTUP_S", 0.0)
        self.byte_rate = 170.0 * 1024.0      # B/s, the harness stream's measured rate
        self.loaded_at = None
        self.seek_offset = 0.0
        self.paused_total = 0.0
        self.paused_since = None
        self.props = {
            "mpv-version": VERSION,
            "pid": os.getpid(),
            "idle-active": True,
            "playlist-count": 0,
            "playlist": [],
            "playlist/current/id": None,
            "pause": False,
            "paused-for-cache": False,
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

    # ---- the timeline

    def _elapsed(self):
        return None if self.loaded_at is None else max(0.0, self.clock() - self.loaded_at)

    def _paused_for(self):
        total = self.paused_total
        if self.paused_since is not None:
            total += max(0.0, self.clock() - self.paused_since)
        return total

    def cache_end(self):
        e = self._elapsed()
        return None if e is None else round(e + self.lead_s, 3)

    def time_pos(self):
        e = self._elapsed()
        if e is None or e < self.startup_s:
            return None
        return round(max(0.0, e - self._paused_for() - self.seek_offset), 3)

    def floor(self):
        end = self.cache_end()
        if end is None:
            return None
        return round(max(0.0, end - self.lead_s - self.window_s), 3)

    def cache_state(self):
        """Only the twelve leaves the helper forwards (M1). Nothing here is a
        string and nothing comes from the stream."""
        end, floor, pos = self.cache_end(), self.floor(), self.time_pos()
        if end is None:
            return {"seekable-ranges": [], "cache-end": None, "reader-pts": None,
                    "cache-duration": None, "fw-bytes": 0, "total-bytes": 0, "underrun": False,
                    "idle": True, "eof": False, "eof-cached": False, "bof-cached": False}
        reader = pos if pos is not None else floor
        return {
            "seekable-ranges": [{"start": floor, "end": end}],
            "cache-end": end,
            "reader-pts": reader,
            "cache-duration": round(end - reader, 3),
            "fw-bytes": int(max(0.0, end - reader) * self.byte_rate),
            "total-bytes": int((end - floor) * self.byte_rate),
            "underrun": False,
            "idle": False,
            "eof": False,
            "eof-cached": False,
            "bof-cached": floor == 0.0,
        }

    def seek(self, target, mode):
        """mpv's measured behaviour, reply success in every case. Returns
        True when time-pos moved (for the self-test; the wire never says).
        Called through plan_seek() from dispatch, which defers the move
        until the reply has been written (F-RWD-15 ordering)."""
        try:
            delta = float(target)
        except (TypeError, ValueError):
            return False
        pos, floor, end = self.time_pos(), self.floor(), self.cache_end()
        if pos is None or floor is None or end is None:
            return False
        if mode == "relative":
            want = pos + delta
            if want < floor and floor == 0.0:
                want = 0.0                      # the start is still cached: clamp (4.3)
        elif mode == "absolute":
            want = end + delta if delta < 0 else delta   # negative: from the cache end (12.2)
        else:
            return False
        if want < floor or want > end:
            return False                        # dropped silently, time-pos carries on
        self.pending_offset = pos - want
        return True

    def apply_seek(self):
        """The deferred half of seek(): the position moves now. serve()
        calls it after writing the reply and before the followups."""
        with self.lock:
            self.seek_offset += getattr(self, "pending_offset", 0.0)
            self.pending_offset = 0.0

    def set_pause(self, value):
        want = bool(value)
        if want and self.paused_since is None:
            self.paused_since = self.clock()
        elif not want and self.paused_since is not None:
            self.paused_total += max(0.0, self.clock() - self.paused_since)
            self.paused_since = None
        self.props["pause"] = want

    def get(self, name):
        with self.lock:
            if name in self.unset:
                return (None, "property unavailable")
            if name == "time-pos":
                pos = self.time_pos()
                return (pos, None) if pos is not None else (None, "property unavailable")
            if name == "demuxer-cache-state":
                return (self.cache_state(), None)
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
            if name == "pause":
                self.set_pause(value)
                return
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
            # Every loadfile restarts the demuxer timeline at 0 and the old
            # history is gone at the first read after the reply (11.1).
            self.loaded_at = self.clock()
            self.seek_offset = 0.0
            self.paused_total = 0.0
            self.paused_since = self.clock() if self.props.get("pause") else None
            return {"playlist_entry_id": n}

    # ---- the gate: hold the first connection until the scenario releases it

    def hold(self, first):
        if not (first and self.gate):
            return
        limit = time.time() + 30
        while os.path.exists(self.gate) and time.time() < limit:
            time.sleep(0.01)

    def followup_targets(self, event, issuing, conns, log_conns):
        """Which connections an unsolicited line goes to, as mpv delivers it:
        an EVENT to every live client, a log message only to the clients that
        subscribed. `issuing` is the connection whose command produced it and
        carries no privilege -- that is the whole point of F-MPV-1, and the
        reason this is a function the self-test calls rather than a branch
        inside the writer loop (rule 12)."""
        live = list(conns)
        if str(event.get("event")) == "log-message":
            return [c for c in live if c in log_conns]
        return live

    def serve(self, conn):
        with self.lock:
            self.clients += 1
            first = self.clients == 1
            self.conns.append(conn)
        try:
            self.serve_loop(conn, first)
        finally:
            with self.lock:
                if conn in self.conns:
                    self.conns.remove(conn)
                if conn in self.log_conns:
                    self.log_conns.remove(conn)

    def serve_loop(self, conn, first):
        buf = b""
        subscribed = False   # request_log_messages on THIS connection (mpv is per client)
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
                if (req.get("command") or [None])[0] == "request_log_messages":
                    subscribed = True
                    with self.lock:
                        if conn not in self.log_conns:
                            self.log_conns.append(conn)
                reply = self.dispatch(req, subscribed)
                if reply is None:
                    return
                followup = reply.pop("_followup", [])
                apply = reply.pop("_apply", None)
                try:
                    # The REPLY is point to point, as mpv answers the client
                    # that asked.
                    conn.sendall((json.dumps(reply) + "\n").encode("utf-8"))
                except OSError:
                    return
                # mpv's order: the reply says queued; the playloop moves the
                # position and sends the event afterwards.
                if apply is not None:
                    apply()
                for event in followup:
                    with self.lock:
                        targets = self.followup_targets(event, conn, self.conns, self.log_conns)
                    payload = (json.dumps(event) + "\n").encode("utf-8")
                    for target in targets:
                        try:
                            target.sendall(payload)
                        except OSError:
                            if target is conn:
                                return
                self.log("REP " + json.dumps(reply))

    def dispatch(self, req, subscribed=False):
        """One reply for one request. `subscribed` is whether THIS connection
        asked for log messages; the refusal line is filtered here, so the
        self-test can see the filter (a filter in serve() was invisible to
        it: the review's finding). A seek's move is deferred into `_apply`
        and its followups into `_followup`, both popped by serve()."""
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
            out["data"] = self.loadfile(cmd[1])
        elif verb == "seek":
            # Success whether or not anything moved: that is what mpv says.
            # What follows the reply is what mpv sends next (F-RWD-15): the
            # `seek` event to every client when it executed, the error-level
            # refusal line to the clients that subscribed when it was
            # dropped. serve() writes them after the reply, in that order.
            with self.lock:
                moved = self.seek(cmd[1] if len(cmd) > 1 else None, cmd[2] if len(cmd) > 2 else "relative")
            out["_apply"] = self.apply_seek
            # WHAT follows is decided here; WHO receives it is followup_targets
            # (mpv broadcasts the event and filters only the log line). The
            # first version filtered the log line here from the issuing
            # connection's own subscription, which meant a second subscribed
            # client never heard a refusal -- the F-MPV-1 shape again.
            out["_followup"] = [{"event": "seek"}] if moved else [
                {"event": "log-message", "prefix": "cplayer", "level": "error",
                 "text": "Cannot seek in this stream. You can force it with '--force-seekable=yes'.\n"}]
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


# ---- the self-test: each case names the measured rule it pins, and each
# was seen red by mutating that rule (docs/QA-REWIND.md section 5).

def self_test():
    import unittest

    class FakeClock(object):
        def __init__(self):
            self.now = 1000.0

        def __call__(self):
            return self.now

        def tick(self, s):
            self.now += s

    class SeekSemantics(unittest.TestCase):
        def setUp(self):
            os.environ.pop("STUB_WINDOW_S", None)
            self.clock = FakeClock()
            self.stub = Stub("/nonexistent/stub.sock", clock=self.clock)
            self.stub.window_s = 30.0
            self.stub.lead_s = 3.6
            self.stub.startup_s = 0.0

        def get(self, name):
            return self.stub.get(name)

        def seek(self, target, mode="relative", subscribed=True, apply=True):
            out = self.stub.dispatch({"command": ["seek", target, mode], "request_id": 7}, subscribed)
            # dispatch decides WHAT follows; followup_targets decides who gets
            # it, and the self-test drives the two separately.
            fn = out.pop("_apply", None)
            if apply and fn is not None:
                fn()
            return out

        def load_and_play(self, seconds):
            self.stub.dispatch({"command": ["loadfile", "http://127.0.0.1:9/x.m3u8", "replace"], "request_id": 1})
            self.clock.tick(seconds)

        def test_a_landed_seek_is_followed_by_the_seek_event_and_a_dropped_one_by_the_refusal_line(self):
            # F-RWD-15: the reply says success either way; what mpv sends
            # NEXT is how a client tells them apart without a timed read.
            self.load_and_play(20.0)
            out = self.seek(-5.0)
            self.assertEqual(out["error"], "success")
            self.assertEqual(out["_followup"], [{"event": "seek"}])
            self.clock.tick(40.0)   # the start is evicted: window 30
            out = self.seek(1.0, "absolute")
            self.assertEqual(out["error"], "success")
            self.assertEqual([e["event"] for e in out["_followup"]], ["log-message"])
            self.assertIn("Cannot seek in this stream", out["_followup"][0]["text"])
            self.assertEqual(out["_followup"][0]["level"], "error")

        def test_a_landed_seek_raises_the_event_and_a_dropped_one_the_refusal_line(self):
            # WHAT follows the reply. WHO receives it is the next case.
            self.load_and_play(20.0)
            self.assertEqual(self.seek(-5.0)["_followup"], [{"event": "seek"}])
            self.clock.tick(40.0)
            dropped = self.seek(1.0, "absolute")["_followup"]
            self.assertEqual([e["event"] for e in dropped], ["log-message"])

        def test_over_real_sockets_a_second_client_hears_the_seek_it_did_not_cause(self):
            """The wiring, not the decision: two real connections to a real
            serve loop. The decision above is a function; this is the sink
            (rule 14). Everything is torn down by pid-free means -- the
            server thread is a daemon and both sockets are closed here."""
            import socket as _socket, tempfile, threading as _threading
            root = tempfile.mkdtemp(prefix="stub-broadcast-")
            path = os.path.join(root, "s")
            stub = Stub(path)
            stub.window_s, stub.lead_s, stub.startup_s = 600.0, 3.6, 0.0
            srv = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            srv.bind(path)
            srv.listen(4)
            srv.settimeout(0.5)
            stop = _threading.Event()

            def accept_loop():
                while not stop.is_set():
                    try:
                        conn, _ = srv.accept()
                    except OSError:
                        return
                    _threading.Thread(target=stub.serve, args=(conn,), daemon=True).start()
            accepter = _threading.Thread(target=accept_loop, daemon=True)
            accepter.start()

            def connect():
                c = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
                c.settimeout(3)
                c.connect(path)
                return c

            def send(c, *command):
                c.sendall((json.dumps({"command": list(command), "request_id": 1}) + "\n").encode())

            def lines(c, want, bound=2.0):
                """Up to `want` JSON objects, or fewer if `bound` elapses."""
                out, buf, deadline = [], b"", time.time() + bound
                while len(out) < want and time.time() < deadline:
                    c.settimeout(max(0.05, deadline - time.time()))
                    try:
                        chunk = c.recv(65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        raw, buf = buf.split(b"\n", 1)
                        if raw.strip():
                            out.append(json.loads(raw.decode()))
                return out

            try:
                a, b = connect(), connect()
                send(a, "loadfile", "http://127.0.0.1:9/x.m3u8", "replace")
                lines(a, 1)
                for _ in range(40):
                    send(a, "get_property", "time-pos")
                    pos = lines(a, 1)
                    if pos and isinstance(pos[0].get("data"), (int, float)) and pos[0]["data"] > 6:
                        break
                    time.sleep(0.1)
                # Only A subscribes to log messages; both are live clients.
                send(a, "request_log_messages", "error")
                lines(a, 1)
                send(a, "seek", -5.0, "relative")
                got_a = lines(a, 2)
                got_b = lines(b, 1)
                # A gets its reply and the event; B, which asked for nothing,
                # gets the event alone -- an event it did not cause.
                self.assertEqual([m.get("error") for m in got_a if "request_id" in m], ["success"])
                self.assertIn("seek", [m.get("event") for m in got_a])
                self.assertEqual([m.get("event") for m in got_b], ["seek"])
                self.assertNotIn("request_id", got_b[0])
                with stub.lock:
                    self.assertEqual(len(stub.conns), 2)
                # A client that goes away stops being a target. Bounded wait:
                # the serve thread notices the close on its next read.
                b.close()
                for _ in range(40):
                    with stub.lock:
                        if len(stub.conns) == 1:
                            break
                    time.sleep(0.05)
                with stub.lock:
                    self.assertEqual(len(stub.conns), 1, "a closed connection is still a broadcast target")
                a.close()
            finally:
                stop.set()
                srv.close()
                accepter.join(2)
                try:
                    os.unlink(path)
                    os.rmdir(root)
                except OSError:
                    pass

        def test_an_event_reaches_every_client_and_a_log_message_only_the_subscribers(self):
            # F-MPV-1: real mpv broadcasts an event to every connected client
            # and answers a command only to the client that sent it; a client
            # hears an event it did not cause. The two other doubles were
            # fixed for this; this one delivered its M5-01 seek followups to
            # the issuing connection alone.
            issuing, other, quiet = object(), object(), object()
            conns = [issuing, other, quiet]
            logs = [issuing, other]
            seek_event = {"event": "seek"}
            line = {"event": "log-message", "level": "error", "text": "x"}
            self.assertEqual(self.stub.followup_targets(seek_event, issuing, conns, logs), conns)
            self.assertEqual(self.stub.followup_targets(line, issuing, conns, logs), logs)
            # The issuing connection carries no privilege either way: a client
            # that never subscribed hears no line even when it asked for the
            # seek, and a subscriber hears one it did not ask for.
            self.assertEqual(self.stub.followup_targets(line, quiet, conns, logs), logs)
            self.assertNotIn(quiet, self.stub.followup_targets(line, quiet, conns, logs))
            self.assertIn(other, self.stub.followup_targets(line, issuing, conns, logs))
            # Nobody is listening: no target, and no crash.
            self.assertEqual(self.stub.followup_targets(seek_event, issuing, [], []), [])

        def test_the_position_moves_only_after_the_reply_has_been_written(self):
            # F-RWD-15's ordering: a read sent at once reads the old position.
            self.load_and_play(20.0)
            before = self.get("time-pos")[0]
            out = self.seek(-5.0, apply=False)
            self.assertEqual(out["error"], "success")
            self.assertEqual(self.get("time-pos")[0], before)       # queued, not yet moved
            self.stub.apply_seek()
            self.assertEqual(self.get("time-pos")[0], before - 5.0)  # moved after the reply

        def test_time_pos_unavailable_until_loadfile_then_wall_clock(self):
            self.assertEqual(self.get("time-pos"), (None, "property unavailable"))
            self.load_and_play(12.0)
            self.assertEqual(self.get("time-pos"), (12.0, None))

        def test_loadfile_reply_carries_the_entry_id(self):
            reply = self.stub.dispatch({"command": ["loadfile", "http://127.0.0.1:9/x.m3u8", "replace"], "request_id": 1})
            self.assertEqual(reply["error"], "success")
            self.assertEqual(reply["data"], {"playlist_entry_id": 1})

        def test_history_grows_one_second_per_second_until_the_window_fills(self):
            self.load_and_play(10.0)
            state, _ = self.get("demuxer-cache-state")
            self.assertEqual(state["seekable-ranges"], [{"start": 0.0, "end": 13.6}])
            self.clock.tick(40.0)                      # 50 s in, window 30: floor at 20
            state, _ = self.get("demuxer-cache-state")
            self.assertEqual(state["seekable-ranges"], [{"start": 20.0, "end": 53.6}])

        def test_seek_inside_the_range_moves_exactly_and_replies_success(self):
            self.load_and_play(40.0)
            reply = self.seek("-10")
            self.assertEqual(reply["error"], "success")
            self.assertEqual(self.get("time-pos"), (30.0, None))
            self.clock.tick(2.0)
            self.assertEqual(self.get("time-pos"), (32.0, None))   # playback continues

        def test_seek_below_the_floor_replies_success_and_does_not_move(self):
            self.load_and_play(50.0)                   # floor 20, pos 50
            reply = self.seek("-31")                   # target 19, one below the floor
            self.assertEqual(reply["error"], "success")
            self.assertEqual(self.get("time-pos"), (50.0, None))
            reply = self.seek("19", "absolute")
            self.assertEqual(reply["error"], "success")
            self.assertEqual(self.get("time-pos"), (50.0, None))

        def test_seek_at_the_floor_lands(self):
            self.load_and_play(50.0)
            self.seek("20", "absolute")
            self.assertEqual(self.get("time-pos"), (20.0, None))

        def test_seek_past_the_end_replies_success_and_does_not_move(self):
            self.load_and_play(50.0)                   # end 53.6
            reply = self.seek("60", "absolute")
            self.assertEqual(reply["error"], "success")
            self.assertEqual(self.get("time-pos"), (50.0, None))
            self.seek("30")                            # relative past the end
            self.assertEqual(self.get("time-pos"), (50.0, None))

        def test_overlong_relative_seek_lands_at_zero_while_the_start_is_cached(self):
            self.load_and_play(20.0)                   # floor still 0
            self.seek("-100000")
            self.assertEqual(self.get("time-pos"), (0.0, None))

        def test_overlong_relative_seek_is_dropped_once_the_start_is_evicted(self):
            self.load_and_play(50.0)                   # floor 20
            self.seek("-100000")
            self.assertEqual(self.get("time-pos"), (50.0, None))

        def test_negative_absolute_target_seeks_from_the_cache_end(self):
            self.load_and_play(50.0)                   # end 53.6
            self.seek("-10", "absolute")
            self.assertEqual(self.get("time-pos"), (43.6, None))

        def test_pause_freezes_time_pos_and_eats_the_history(self):
            self.load_and_play(40.0)                   # floor 10, history 30 (full)
            self.stub.dispatch({"command": ["set_property", "pause", True], "request_id": 2})
            self.clock.tick(15.0)
            self.assertEqual(self.get("time-pos"), (40.0, None))
            state, _ = self.get("demuxer-cache-state")
            self.assertEqual(state["seekable-ranges"][0]["start"], 25.0)   # moved 15 s while paused
            self.stub.dispatch({"command": ["set_property", "pause", False], "request_id": 3})
            self.clock.tick(2.0)
            self.assertEqual(self.get("time-pos"), (42.0, None))           # resumed from the paused point

        def test_rewind_then_pause_holds_and_resumes_from_the_rewound_point(self):
            self.load_and_play(40.0)
            self.seek("-20")
            self.stub.dispatch({"command": ["set_property", "pause", True], "request_id": 2})
            self.clock.tick(5.0)
            self.assertEqual(self.get("time-pos"), (20.0, None))
            self.stub.dispatch({"command": ["set_property", "pause", False], "request_id": 3})
            self.clock.tick(1.0)
            self.assertEqual(self.get("time-pos"), (21.0, None))

        def test_loadfile_restarts_the_timeline_and_discards_the_history(self):
            self.load_and_play(50.0)
            self.seek("-20")
            self.stub.dispatch({"command": ["loadfile", "http://127.0.0.1:9/y.m3u8", "replace"], "request_id": 4})
            self.assertEqual(self.get("time-pos"), (0.0, None))
            state, _ = self.get("demuxer-cache-state")
            self.assertEqual(state["seekable-ranges"], [{"start": 0.0, "end": 3.6}])
            self.clock.tick(5.0)
            self.seek("-20")                           # no history to rewind into: lands at 0 (start cached)
            self.assertEqual(self.get("time-pos"), (0.0, None))

        def test_cache_state_has_only_the_twelve_allowlisted_leaves_and_no_strings(self):
            self.load_and_play(10.0)
            state, _ = self.get("demuxer-cache-state")
            self.assertEqual(sorted(state.keys()), sorted([
                "seekable-ranges", "cache-end", "reader-pts", "cache-duration", "fw-bytes",
                "total-bytes", "underrun", "idle", "eof", "eof-cached", "bof-cached"]))
            self.assertEqual(sorted(state["seekable-ranges"][0].keys()), ["end", "start"])
            for value in list(state.values()) + list(state["seekable-ranges"][0].values()):
                self.assertNotIsInstance(value, str)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SeekSemantics)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


def main(argv):
    if argv[:1] == ["--self-test"]:
        return self_test()
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
