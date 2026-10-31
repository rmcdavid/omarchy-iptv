"""mpv JSON IPC tests for bin/omarchy-iptv (play / stop / status) against a
fake mpv server on a unix socket. No real mpv, no network.

Run: python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import os
import pathlib
import shutil
import socket
import tempfile
import threading
import time
import unittest

from helper_loader import load_helper

helper = load_helper()

PLAYLIST = """#EXTM3U
#EXTINF:-1 tvg-id="bbc1.uk" group-title="UK",BBC One HD
http://stream.example.test/live/bbc1.m3u8
#EXTINF:-1 tvg-id="espn.us",ESPN
#EXTVLCOPT:http-user-agent=VLC/3.0.20
#EXTVLCOPT:http-referrer=http://ref.example.test/
#KODIPROP:inputstream.adaptive.stream_headers=X-Forwarded-For=1.2.3.4&Cookie=a%3Db
http://stream.example.test/live/espn.m3u8
"""
STATUS_PROPS = {
    "media-title": "BBC One HD",
    "path": "http://user:pw@provider.example.test/live/u/p/1.m3u8",
    "pause": False,
    "idle-active": False,
    "mpv-version": "mpv 0.41.0",
}


def run(*args):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = helper.main(list(args))
    lines = out.getvalue().strip().splitlines()
    payload = json.loads(lines[-1]) if lines else None
    return code, payload, out.getvalue(), err.getvalue()


# The TLS assertion's wire sequence (assert_tls_verification) on a player
# started WITHOUT the pin block, which is what FakeMpv's defaults are: the two
# D-SINK-16 sets, the demuxer map read (nothing to remove in an empty one),
# load-auto-profiles read as mpv's own "auto" and set to no, then the
# read-back -- the two old readings, the two new ones, and, because nothing on
# this player was set from the command line, mpv's own answer for each option
# a per-file profile could undo and the profile list itself (D-SINK-44).
# Spelled out rather than built from the helper's constants, so a change to
# the sequence has to be a change to this list too.
#
# 2026-10-29 (lane-p1b): the demuxer map also gets the pinned protocol
# whitelist (D-SINK-55: absent here, so it is appended), reset-on-next-file is
# read back with the TLS pins and never written (D-SINK-60), and the
# per-file profile check asks about EVERY pinned option, in the helper's
# sorted order, not only the TLS ones (the lead's decision on the recheck).
#
# lane-p1c (2026-10-29): and the pinned FORMAT list (D-SINK-62), appended the
# same way, and two more pinned options the per-file check asks about,
# load-console (D-SINK-61) and prefetch-playlist (D-SINK-63).
#
# lane-p2a (2026-10-29): load-stats-overlay is pinned (D-SINK-67) but NOT asked
# about here: the helper's PER_FILE_EXEMPT says why (the harness stub).
WHITELIST = "http,https,tls,tcp,crypto,data,httpproxy"
FORMATS = "hls,dash,mpegts,mov,matroska,flv,live_flv,mp3,aac,ac3,eac3,ogg,flac,asf,rtsp,webvtt"
# What a demuxer-lavf-o map holds on a player of this release, less tls_verify.
LISTS = {"protocol_whitelist": WHITELIST, "format_whitelist": FORMATS}
PINNED_OPTIONS = ("demuxer-lavf-o", "demuxer-lavf-propagate-opts", "drag-and-drop", "input-commands",
                  "load-auto-profiles", "load-console", "load-scripts", "load-select", "load-unsafe-playlists",
                  "log-file", "osd-playlist-entry", "player-operation-mode", "prefetch-playlist",
                  "reset-on-next-file", "save-watch-history", "script-opts", "scripts", "stream-lavf-o",
                  "tls-verify", "watch-later-dir")
TLS_PRELUDE_PRE_PIN = [
    ["set_property", "tls-verify", True],
    ["set_property", "stream-lavf-o", {}],
    ["get_property", "demuxer-lavf-o"],
    ["change-list", "demuxer-lavf-o", "append", "protocol_whitelist=" + WHITELIST],
    ["change-list", "demuxer-lavf-o", "append", "format_whitelist=" + FORMATS],
    ["get_property", "load-auto-profiles"],
    ["set_property", "load-auto-profiles", "no"],
    ["get_property", "tls-verify"],
    ["get_property", "stream-lavf-o"],
    ["get_property", "demuxer-lavf-o"],
    ["get_property", "load-auto-profiles"],
    ["get_property", "reset-on-next-file"],
] + [["get_property", "option-info/%s/set-from-commandline" % name] for name in PINNED_OPTIONS] + [
    ["get_property", "profile-list"],
]
# The options the pin block sets from the command line: a FakeMpv given these
# as `cmdline` (and the pinned values as `props`) is a player launched by this
# release's argv.
PINNED_CMDLINE = PINNED_OPTIONS
PINNED_PROPS = {"tls-verify": True, "stream-lavf-o": {},
                "demuxer-lavf-o": dict(LISTS, tls_verify="1"),
                "load-auto-profiles": False, "reset-on-next-file": []}
# The per-file options of the helper's loadfile (channel_load_options): the
# demuxer that refuses a nested playlist (D-PLY-44), the channel's user agent
# and referrer, its header list emptied and then one verbatim -append per
# header. Ordered pairs, because the object repeats a key.
def load_options(agent=helper.MPV_DEFAULT_USER_AGENT, referrer="", fields=()):
    return ([["demuxer", "lavf"], ["user-agent", agent], ["referrer", referrer], ["http-header-fields-clr", ""]]
            + [["http-header-fields-append", f] for f in fields])


class Obj(dict):
    """A JSON object as mpv's own reader takes it: every key in order,
    repeats kept, in `pairs` (measured on mpv 0.41.0: three
    `http-header-fields-append` keys in one object were three headers). As a
    dict it compares like the object Python's json would make of it."""

    def __init__(self, pairs):
        super().__init__(pairs)
        self.pairs = [[k, v] for k, v in pairs]


class FakeMpv:
    """Accepts connections on a unix socket, records every command and answers
    like mpv: {"error": "success", "data": ..., "request_id": N}.

    Each connection is served by its own thread, because the detached player
    keeps a persistent subscriber on the socket while control calls come and
    go: a server that handled one connection at a time would deadlock the
    second caller (and would be more forgiving than mpv, which names its
    clients ipc_0 / ipc_1 and correlates by request_id).

    It also mirrors three things real mpv does that the M2-02 paths depend on:
    `user-data/<node>` sub-paths store and read back per node while the top
    level is not writable, `loadfile` answers with a playlist_entry_id, and
    events can arrive unasked at any moment (`inject`).

    M5-01 taught it the seek semantics docs/SPIKE-LIVE-REWIND.md 11.4 and
    12.2 measured, NO MORE FORGIVING than mpv 0.41 (CLAUDE.md rule 10):
    `seek <t> absolute` always answers `success`; the position moves only
    when the target lies inside a `seekable-ranges` entry of the
    `demuxer-cache-state` prop, and then echoes the target exactly (72 of
    72); outside it the position is unchanged and one error-level
    `Cannot seek in this stream` log-message event is pushed (31 of 31); a
    NEGATIVE target is an offset from the cache end, not a refusal (F-RWD-7,
    5 of 5). `seek_moves=False` is the underrun case: a target inside the
    range that still moves nothing. `show-text` is recorded in `osd`.

    D-SINK-16 taught it the two certificate properties, and taught it that a
    `set_property` on an ordinary property is READABLE afterwards -- which is
    what real mpv does and what this fake used to answer `property not found`
    to, making it MORE forgiving than mpv in the one direction that matters
    here (CLAUDE.md rule 10): the shipping code now reads `tls-verify` back
    rather than trusting the set reply, and a fake that could not answer a
    read-back would have let that read look impossible. The seeded defaults are
    mpv 0.41's own (`tls-verify` NO, `stream-lavf-o` empty), so a FakeMpv with
    no `props` is a player launched the way 0.12.1 launched one; `props` and
    `refuse` between them express the upgraded player and the player whose set
    does not take, and `missing` expresses a property that cannot be read at
    all.

    And the ordering mpv really has (F-RWD-15, measured 2026-10-03): the
    reply to `seek` means QUEUED. The position moves, the `seek` event is
    sent to every client and -- for a dropped seek -- the refusal line is
    sent to the clients that subscribed, all `seek_lag_s` AFTER the reply,
    on another thread, the way the playloop executes a queued seek after
    the IPC thread has answered. A read sent at once can be answered first
    and echo the old position; 1 of 12 did on the real player. `seek_lag_s`
    0 is the synchronous fake the direct-socket semantics tests drive;
    the verb tests run lagged. `seek_silent=True` is the pathological case
    that neither executes nor refuses, for the bound. Log messages reach
    only connections that asked for them, as on mpv.

    And the DECODED landing (F-RWD-8, 2026-10-24): on the real player the
    `seek` event echoes the target and `playback-restart` follows 26-40 ms
    later, when the decoder produces frames at the position it could reach
    -- the next keyframe, up to 5.1 s past the target on a 720p channel.
    So an executed seek emits `seek` with time-pos at the target, then,
    `restart_lag_s` later, moves time-pos to target + `landing_offset` and
    emits `playback-restart`. Both default to 0 so every case pinned
    before this knob existed reads byte for byte as it did; a test that
    wants the keyframe sets the offset. `restart_silent=True` is the
    player that executes but never restarts, for the bound on that half.
    `restart_before_seek=True` emits a STRAY `playback-restart` -- one the
    player raises for its own reasons, a buffering stall ending at the
    same instant -- before the `seek` event, with time-pos still at the
    old position: the helper counts a restart only after a `seek` was
    seen, and this is the knob that makes that decision visible (the
    round-2 recheck, 2026-10-24).
    """

    REFUSAL_LINE = "Cannot seek in this stream. You can force it with '--force-seekable=yes'.\n"
    # mpv 0.41's own defaults for the two D-SINK-16 properties: `--tls-verify`
    # defaults to NO (`mpv --list-options`), and `stream-lavf-o` is an empty
    # key-value map that the JSON IPC answers as {}.
    #
    # 2026-10-29 (D-SINK-43/44 and the adopted-player pins): the rest of what
    # the read-back now asks, at mpv 0.41's own defaults, each measured over a
    # real IPC socket rather than assumed: `demuxer-lavf-o` an empty map,
    # `load-auto-profiles` the STRING "auto" (and, after a set of "no", the
    # BOOLEAN False -- mpv answers that choice's yes/no as JSON booleans, which
    # is what set_property models below), `profile-list` the user's profiles
    # (none here; the builtin ones are never per-file), and the pins
    # pin_adopted_player reads. With no `props` this is still a player the way
    # 0.12.1 launched one: nothing set from the command line (`cmdline`).
    TLS_DEFAULTS = {"tls-verify": False, "stream-lavf-o": {}, "demuxer-lavf-o": {},
                    "load-auto-profiles": "auto", "profile-list": [],
                    "load-select": True, "save-watch-history": False, "load-unsafe-playlists": False,
                    "reset-on-next-file": [], "osd-playlist-entry": "title", "log-file": "",
                    "watch-later-dir": "", "drag-and-drop": "auto", "script-opts": {},
                    # lane-p1c: mpv 0.41's defaults (measured): no prefetch,
                    # the console loaded.
                    "prefetch-playlist": False, "load-console": True,
                    # lane-p2a: and the stats overlay loaded (measured: True).
                    "load-stats-overlay": True}
    # mpv 0.41 answers `yes` and `no` of these choices as booleans (measured for
    # load-auto-profiles: "auto" before, False after `set ... no`; and for
    # drag-and-drop: False for `no`, lane-p1b 2026-10-29).
    CHOICE_BOOLEANS = {"load-auto-profiles": {"no": False, "yes": True}, "drag-and-drop": {"no": False}}

    def __init__(self, path, props=None, event_first=False, silent=False, refuse=(), close_on_quit=True,
                 entry_ids=True, user_data=None, seek_moves=True, seek_lag_s=0.0, seek_silent=False,
                 missing=(), landing_offset=0.0, restart_lag_s=0.0, restart_silent=False,
                 restart_before_seek=False, cmdline=()):
        self.path = path
        # The options this player had on its command line: mpv's own
        # `option-info/<name>/set-from-commandline` answers True for them and
        # False for every other option (measured; a runtime set_property does
        # not change it, also measured).
        self.cmdline = set(cmdline)
        self.props = dict(self.TLS_DEFAULTS)
        self.props.update(props or {})
        self.missing = set(missing)
        for name in self.missing:
            self.props.pop(name, None)
        self.event_first = event_first
        self.silent = silent
        self.refuse = set(refuse)
        self.close_on_quit = close_on_quit
        self.entry_ids = entry_ids
        self.user_data = dict(user_data or {})
        self.seek_moves = seek_moves
        self.seek_lag_s = seek_lag_s
        self.seek_silent = seek_silent
        self.landing_offset = landing_offset
        self.restart_lag_s = restart_lag_s
        self.restart_silent = restart_silent
        self.restart_before_seek = restart_before_seek
        self.log_conns = set()
        self.command_times = []
        self.seeks = []
        self.osd = []
        self.commands = []
        self.log_levels = []
        self.entry_id = 0
        self.lock = threading.Lock()
        self.conns = []
        self.workers = []
        self.running = True
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(path)
        self.server.listen(8)
        self.server.settimeout(0.05)
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while self.running:
            try:
                conn, _ = self.server.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            worker = threading.Thread(target=self.handle, args=(conn,), daemon=True)
            with self.lock:
                self.conns.append(conn)
                self.workers.append(worker)
            worker.start()

    def inject(self, event):
        """Push an unsolicited event line to every live connection, the way
        mpv emits start-file / end-file / seek / property-change -- and a
        log-message only to the connections that subscribed, as mpv does."""
        payload = (json.dumps(event) + "\n").encode("utf-8")
        with self.lock:
            targets = list(self.conns)
            if event.get("event") == "log-message":
                targets = [c for c in targets if c in self.log_conns]
        for conn in targets:
            try:
                conn.sendall(payload)
            except OSError:
                continue

    def handle(self, conn):
        conn.settimeout(3)
        try:
            if self.event_first:
                conn.sendall(b'{"event":"start-file"}\nnot json at all\n')
            buffer = b""
            while True:
                try:
                    chunk = conn.recv(4096)
                except (TimeoutError, OSError):
                    return
                if not chunk:
                    return
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    message = json.loads(line.decode("utf-8"), object_pairs_hook=Obj)
                    with self.lock:
                        self.commands.append(message["command"])
                        self.command_times.append(time.monotonic())
                        if message["command"][0] == "request_log_messages":
                            self.log_conns.add(conn)
                    if self.silent:
                        continue
                    reply = self.reply_for(message)
                    if reply is None:
                        return
                    conn.sendall((json.dumps(reply) + "\n").encode("utf-8"))
        finally:
            with self.lock:
                if conn in self.conns:
                    self.conns.remove(conn)
            try:
                conn.close()
            except OSError:
                pass

    def reply_for(self, message):
        command = message["command"]
        request_id = message.get("request_id")
        if command[0] == "quit":
            return None if self.close_on_quit else {"error": "success", "request_id": request_id}
        if command[0] == "request_log_messages":
            with self.lock:
                self.log_levels.append(command[1])
            return {"error": "success", "request_id": request_id}
        if command[0] == "get_property":
            name = command[1]
            if name in self.missing:
                return {"error": "property not found", "request_id": request_id}
            with self.lock:
                if name in self.props:
                    return {"error": "success", "data": self.props[name], "request_id": request_id}
            if name.startswith("user-data/"):
                node = name.split("/", 1)[1]
                with self.lock:
                    if node in self.user_data:
                        return {"error": "success", "data": self.user_data[node], "request_id": request_id}
                return {"error": "property not found", "request_id": request_id}
            if name == "user-data":
                with self.lock:
                    return {"error": "success", "data": dict(self.user_data), "request_id": request_id}
            if name.startswith("option-info/") and name.endswith("/set-from-commandline"):
                option = name[len("option-info/"):-len("/set-from-commandline")]
                return {"error": "success", "data": option in self.cmdline, "request_id": request_id}
            return {"error": "property not found", "request_id": request_id}
        if command[0] == "change-list":
            # mpv's list editing over IPC, for the key/value lists the helper
            # touches: `remove` deletes a key, `append` sets one. A name in
            # `refuse` refuses this the way it refuses a set.
            name, operation, value = command[1], command[2], command[3]
            if name in self.refuse or name in self.missing:
                return {"error": "property unavailable", "request_id": request_id}
            with self.lock:
                current = dict(self.props.get(name) or {})
                if operation == "remove":
                    current.pop(value, None)
                elif operation == "append":
                    key, _, item = str(value).partition("=")
                    current.pop(key, None)
                    current[key] = item
                self.props[name] = current
            return {"error": "success", "data": None, "request_id": request_id}
        if command[0] == "set_property":
            name = command[1]
            if name in self.refuse:
                return {"error": "property unavailable", "request_id": request_id}
            if name == "user-data":
                # Verified on mpv 0.41: the top level is not writable.
                return {"error": "error accessing property", "request_id": request_id}
            if name.startswith("user-data/"):
                with self.lock:
                    self.user_data[name.split("/", 1)[1]] = command[2]
                return {"error": "success", "request_id": request_id}
            # Real mpv stores it, and a later get_property answers with it. A
            # fake that answered `property not found` to the read-back of its
            # own write is more forgiving than mpv in exactly the direction
            # D-SINK-16's fix depends on (rule 10). A name in `missing` stays
            # unreadable: that is the wedged / too-old player.
            if name not in self.missing:
                value = command[2]
                mapping = self.CHOICE_BOOLEANS.get(name)
                if mapping and isinstance(value, str):
                    value = mapping.get(value, value)
                with self.lock:
                    self.props[name] = value
            return {"error": "success", "data": None, "request_id": request_id}
        if command[0] == "loadfile" and self.entry_ids:
            with self.lock:
                self.entry_id += 1
                entry = self.entry_id
            return {"error": "success", "data": {"playlist_entry_id": entry}, "request_id": request_id}
        if command[0] == "seek":
            self.seek(command)
            return {"error": "success", "data": None, "request_id": request_id}
        if command[0] == "show-text":
            with self.lock:
                self.osd.append(list(command[1:]))
            return {"error": "success", "data": None, "request_id": request_id}
        return {"error": "success", "data": None, "request_id": request_id}

    def seek(self, command):
        """mpv 0.41's measured seek: see the class docstring. Records
        (target, landed) in `seeks`; a refusal pushes the log line."""
        amount = float(command[1])
        mode = command[2] if len(command) > 2 else "relative"
        position = self.props.get("time-pos")
        ranges = []
        state = self.props.get("demuxer-cache-state")
        if isinstance(state, dict):
            ranges = [(float(r["start"]), float(r["end"])) for r in state.get("seekable-ranges", [])]
        landed = False
        target = None
        if isinstance(position, (int, float)) and not isinstance(position, bool):
            target = amount if mode == "absolute" else position + amount
            if mode == "absolute" and amount < 0 and ranges:
                # F-RWD-7: a negative absolute target counts from the END.
                target = ranges[-1][1] + amount
            inside = any(start <= target <= end for start, end in ranges)
            if inside and self.seek_moves:
                landed = True
        with self.lock:
            self.seeks.append((target, landed))

        def restart():
            with self.lock:
                self.props["time-pos"] = target + self.landing_offset
            self.inject({"event": "playback-restart"})

        def execute():
            if self.seek_silent:
                return
            if landed:
                if self.restart_before_seek:
                    # A stray restart, time-pos untouched: not this seek's.
                    self.inject({"event": "playback-restart"})
                self.props["time-pos"] = target
                self.inject({"event": "seek"})
                if self.restart_silent:
                    return
                if self.restart_lag_s > 0:
                    threading.Timer(self.restart_lag_s, restart).start()
                else:
                    restart()
            else:
                self.inject({"event": "log-message", "prefix": "cplayer", "level": "error",
                             "text": self.REFUSAL_LINE})
        if self.seek_lag_s > 0:
            threading.Timer(self.seek_lag_s, execute).start()
        else:
            execute()

    def close(self):
        self.running = False
        self.thread.join(2)
        with self.lock:
            targets = list(self.conns)
            workers = list(self.workers)
        for conn in targets:
            try:
                conn.close()
            except OSError:
                pass
        for worker in workers:
            worker.join(2)
        self.server.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass


class MpvTestCase(unittest.TestCase):
    def setUp(self):
        # AF_UNIX paths are limited to ~108 bytes: keep the socket under /tmp.
        self.dir = tempfile.mkdtemp(prefix="omarchy-iptv-test-", dir="/tmp")
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.sock = os.path.join(self.dir, "mpv.sock")
        self.cache = os.path.join(self.dir, "cache")
        playlist = os.path.join(self.dir, "list.m3u")
        pathlib.Path(playlist).write_text(PLAYLIST, encoding="utf-8")
        code, _, _, stderr = run("playlist", "--url", playlist, "--cache-dir", self.cache)
        self.assertEqual(code, 0, stderr)
        self.server = None

    def start(self, **kwargs):
        self.server = FakeMpv(self.sock, **kwargs)
        self.addCleanup(self.server.close)
        return self.server

    def play(self, *args):
        return run("play", *args, "--cache-dir", self.cache, "--socket", self.sock, "--ipc-timeout", "1")


class PlayTest(MpvTestCase):
    def test_sets_title_headers_then_loadfile_in_order(self):
        server = self.start()
        code, payload, stdout, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload, {"ok": True, "kind": "play", "id": "t:espn.us", "name": "ESPN"})
        self.assertEqual(server.commands, TLS_PRELUDE_PRE_PIN + [
            # D-SINK-16: asserted and READ BACK before anything else, because
            # everything below this is the act of telling an unverified process
            # about a channel (the prelude above).
            ["set_property", "pause", False],
            ["set_property", "aid", "auto"],
            ["set_property", "sid", "auto"],
            ["set_property", "title", "$>ESPN"],
            ["set_property", "force-media-title", "ESPN"],
            # 2026-10-29: the GLOBAL header properties at values that belong
            # to no provider, whatever the channel carries...
            ["get_property", "option-info/user-agent/default-value"],
            ["set_property", "user-agent", helper.MPV_DEFAULT_USER_AGENT],
            ["set_property", "referrer", ""],
            ["set_property", "http-header-fields", []],
            # ...and the channel's own on the loadfile, per file. D-SINK-41:
            # the playlist is a local FILE, which has no host for the
            # channel's to equal, so its Cookie is a sign-in header for
            # another host and is dropped at parse time; the rest arrive.
            ["loadfile", "http://stream.example.test/live/espn.m3u8", "replace", -1,
             dict(load_options("VLC/3.0.20", "http://ref.example.test/", ["X-Forwarded-For: 1.2.3.4"]))],
        ])
        self.assertEqual(server.commands[-1][4].pairs,
                         load_options("VLC/3.0.20", "http://ref.example.test/", ["X-Forwarded-For: 1.2.3.4"]))
        self.assertEqual(len(stdout.strip().splitlines()), 1)
        self.assertNotIn("espn.m3u8", stdout + stderr)

    def test_the_headers_ride_the_loadfile_and_no_global_carries_them(self):
        """2026-10-29 (D-PLY-44's sibling, the review's ctrl-v finding). The
        helper used to set the channel's headers as GLOBAL properties, so an
        entry it did not load -- a paste, a drop, a nested playlist's entry,
        playlist-next -- went out with them. Now no global property is ever
        given a provider value: every set_property of the three names carries
        mpv's default, nothing, or the empty list, and the channel's values
        appear only in the loadfile's own options."""
        server = self.start()
        code, _, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        globals_ = [c for c in server.commands if c[0] == "set_property"
                    and c[1] in ("user-agent", "referrer", "http-header-fields")]
        self.assertEqual(globals_, [["set_property", "user-agent", helper.MPV_DEFAULT_USER_AGENT],
                                    ["set_property", "referrer", ""], ["set_property", "http-header-fields", []]])
        flat = json.dumps([c for c in server.commands if c[0] != "loadfile"])
        for value in ("VLC/3.0.20", "ref.example.test", "1.2.3.4"):
            self.assertNotIn(value, flat)

    def test_a_header_value_with_commas_quotes_and_backslashes_stays_one_header(self):
        """The per-file list is written as one VERBATIM `-append` per header:
        the plain list option splits a value at every comma (measured on mpv
        0.41.0 against a logging server: `X-A: 1,2` arrived as `X-A: 1`). The
        object repeats the key, so it is written in order by hand (IpcPairs)
        and read here as mpv reads it. CR and LF never reach it: the parse
        refuses them (clean_header_value turns them into spaces)."""
        playlist = os.path.join(self.dir, "hard.m3u")
        value = 'v1,v2=v3 "q" back\\slash [br] end\\'
        pathlib.Path(playlist).write_text(
            '#EXTM3U\n#EXTINF:-1 tvg-id="h.test",Hard\n#EXTVLCOPT:http-user-agent=UA, a=b "c"\n'
            "#KODIPROP:inputstream.adaptive.stream_headers=X-A=%s&X-B=two%%0D%%0AX-Evil: 1\n"
            "http://stream.example.test/h.m3u8\n" % value.replace(",", "%2C").replace("&", "%26").replace("=", "%3D"),
            encoding="utf-8")
        code, _, _, stderr = run("playlist", "--url", playlist, "--cache-dir", self.cache)
        self.assertEqual(code, 0, stderr)
        server = self.start()
        code, _, _, stderr = self.play("--id", "t:h.test")
        self.assertEqual(code, 0, stderr)
        options = [c for c in server.commands if c[0] == "loadfile"][0][4].pairs
        self.assertEqual(options, load_options('UA, a=b "c"', "", ["X-A: " + value, "X-B: two  X-Evil: 1"]))

    def test_a_channel_change_resets_the_track_selection(self):
        """M3-02 / 0.9.0 preflight. mpv keeps `aid` and `sid` across a
        loadfile exactly as it keeps `pause`, so a user who picked the
        Spanish audio on one channel got track 2 of the NEXT channel --
        whatever that happens to be -- with the picker cleared and nothing on
        screen saying why. Two shipped sentences promised the opposite. The
        reset is atomic with the load for the same reason the pause reset is:
        the shell's own view is optimistic and cannot be.
        """
        server = self.start()
        code, _, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        sets = [c for c in server.commands if c[0] == "set_property"]
        self.assertIn(["set_property", "aid", "auto"], sets)
        self.assertIn(["set_property", "sid", "auto"], sets)
        # Before the loadfile, or the new channel loads with the old track.
        load = [i for i, c in enumerate(server.commands) if c[0] == "loadfile"][0]
        for prop in ("aid", "sid"):
            self.assertLess(server.commands.index(["set_property", prop, "auto"]), load)

    def test_clears_headers_for_a_channel_without_any(self):
        server = self.start(props={"option-info/user-agent/default-value": "mpv-default-ua"})
        code, payload, _, stderr = self.play("--id", "t:bbc1.uk")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["name"], "BBC One HD")
        self.assertEqual(server.commands, TLS_PRELUDE_PRE_PIN + [
            ["set_property", "pause", False],
            ["set_property", "aid", "auto"],
            ["set_property", "sid", "auto"],
            ["set_property", "title", "$>BBC One HD"],
            ["set_property", "force-media-title", "BBC One HD"],
            ["get_property", "option-info/user-agent/default-value"],
            ["set_property", "user-agent", "mpv-default-ua"],
            ["set_property", "referrer", ""],
            ["set_property", "http-header-fields", []],
            ["loadfile", "http://stream.example.test/live/bbc1.m3u8", "replace", -1,
             dict(load_options("mpv-default-ua"))],
        ])
        self.assertEqual(server.commands[-1][4].pairs, load_options("mpv-default-ua"))

    def test_user_agent_falls_back_to_libmpv_without_option_info(self):
        server = self.start()
        code, _, _, _ = self.play("--id", "t:bbc1.uk")
        self.assertEqual(code, 0)
        self.assertIn(["set_property", "user-agent", helper.MPV_DEFAULT_USER_AGENT], server.commands)

    def test_url_verb_names_the_host_and_sends_no_headers(self):
        server = self.start()
        code, payload, stdout, stderr = self.play("--url", "https://user:pw@live.example.test/secret/path.m3u8?token=abc")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload, {"ok": True, "kind": "play", "id": None, "name": "live.example.test"})
        self.assertEqual(server.commands[-1][:4], ["loadfile", "https://user:pw@live.example.test/secret/path.m3u8?token=abc", "replace", -1])
        self.assertEqual(server.commands[-1][4].pairs, load_options())
        self.assertIn(["set_property", "http-header-fields", []], server.commands)
        for secret in ("user:pw", "secret", "token=abc"):
            self.assertNotIn(secret, stdout + stderr)

    def test_only_an_rtsp_channel_widens_the_demuxer_protocols_and_only_for_itself(self):
        """D-SINK-55 (2026-10-29). The pin block gives every entry the demuxer
        whitelist without rtp and udp (a sniffed SDP's rtp is how a server
        made the player listen). An rtsp channel's demuxer opens its RTP
        transport itself, which the user's own --rtsp-transport=udp needs
        (warned, D-SINK-53; measured: with the global list alone it stopped
        at DESCRIBE), so the helper's loadfile of an rtsp channel -- and of
        nothing else -- adds them, per file."""
        server = self.start()
        for url, extra in (("rtsp://cam.example.test/live", [["demuxer-lavf-o-append",
                                                                "protocol_whitelist=" + WHITELIST + ",rtp,udp"]]),
                           ("RTSP://cam.example.test/live", [["demuxer-lavf-o-append",
                                                                "protocol_whitelist=" + WHITELIST + ",rtp,udp"]]),
                           ("http://stream.example.test/x.ts", []), ("rtmp://cdn.example.test/app/x", []),
                           ("udp://@239.1.1.1:1234", []), ("srt://srt.example.test:9000", [])):
            with self.subTest(url=url):
                code, _, _, stderr = self.play("--url", url)
                self.assertEqual(code, 0, stderr)
                self.assertEqual(server.commands[-1][4].pairs, load_options() + extra)

    def test_unknown_channel_never_touches_mpv(self):
        server = self.start()
        code, payload, _, stderr = self.play("--id", "t:nope")
        self.assertEqual(code, 1)
        self.assertEqual(payload["kind"], "play")
        self.assertEqual(payload["error"]["code"], "unknown_channel")
        self.assertEqual(payload["id"], "t:nope")
        self.assertIn("t:nope", stderr)
        time.sleep(0.05)
        self.assertEqual(server.commands, [])

    def test_missing_cache_is_no_cache(self):
        self.start()
        code, payload, _, _ = run("play", "--id", "t:bbc1.uk", "--cache-dir", os.path.join(self.dir, "nowhere"), "--socket", self.sock)
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "no_cache")

    def test_rejects_unsafe_urls(self):
        server = self.start()
        for bad in ("file:///etc/passwd", "--script=/tmp/evil.lua", "javascript:alert(1)", ""):
            code, payload, _, _ = self.play("--url=" + bad)
            self.assertEqual(code, 1, bad)
            self.assertEqual(payload["error"]["code"], "unsupported_scheme", bad)
        time.sleep(0.05)
        self.assertEqual(server.commands, [])

    def test_not_running_when_socket_is_missing(self):
        code, payload, _, _ = self.play("--id", "t:bbc1.uk")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "not_running")
        self.assertFalse(payload["ok"])

    def test_events_and_junk_lines_are_skipped(self):
        server = self.start(event_first=True)
        code, payload, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(server.commands[-1][0], "loadfile")

    def test_header_failure_aborts_before_loadfile(self):
        server = self.start(refuse={"http-header-fields"})
        code, payload, _, _ = self.play("--id", "t:espn.us")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "ipc_error")
        self.assertIn("http-header-fields", payload["error"]["message"])
        self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])

    def test_title_failure_is_tolerated(self):
        server = self.start(refuse={"title"})
        code, payload, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertIn("refused to set title", stderr)
        self.assertEqual(server.commands[-1][0], "loadfile")

    def test_silent_mpv_times_out(self):
        self.start(silent=True)
        started = time.monotonic()
        code, payload, _, _ = run("play", "--id", "t:bbc1.uk", "--cache-dir", self.cache, "--socket", self.sock, "--ipc-timeout", "0.3")
        elapsed = time.monotonic() - started
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "ipc_error")
        self.assertIn("did not answer", payload["error"]["message"])
        self.assertLess(elapsed, 2.0)

    def test_utf8_channel_names_reach_mpv_unescaped(self):
        playlist = os.path.join(self.dir, "utf8.m3u")
        pathlib.Path(playlist).write_text("#EXTM3U\n#EXTINF:-1 tvg-id=\"tq.ca\",T\u00e9l\u00e9 Qu\u00e9bec\nhttp://stream.example.test/tq.m3u8\n", encoding="utf-8")
        run("playlist", "--url", playlist, "--cache-dir", self.cache)
        server = self.start()
        code, payload, _, _ = self.play("--id", "t:tq.ca")
        self.assertEqual(code, 0)
        self.assertEqual(payload["name"], "T\u00e9l\u00e9 Qu\u00e9bec")
        self.assertIn(["set_property", "title", "$>T\u00e9l\u00e9 Qu\u00e9bec"], server.commands)
        self.assertIn(["set_property", "force-media-title", "T\u00e9l\u00e9 Qu\u00e9bec"], server.commands)

    def test_title_is_sent_with_the_raw_marker_so_mpv_never_expands_it(self):
        # S-01: mpv expands ${property} in `title`; "$>" keeps the rest literal.
        playlist = os.path.join(self.dir, "expand.m3u")
        pathlib.Path(playlist).write_text('#EXTM3U\n#EXTINF:-1 tvg-id="x.test",${path} ${options/input-ipc-server}\nhttp://user:pw@stream.example.test/x.m3u8\n', encoding="utf-8")
        run("playlist", "--url", playlist, "--cache-dir", self.cache)
        server = self.start()
        code, payload, stdout, stderr = self.play("--id", "t:x.test")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["name"], "${path} ${options/input-ipc-server}")
        self.assertIn(["set_property", "title", helper.MPV_RAW_PREFIX + "${path} ${options/input-ipc-server}"], server.commands)
        self.assertEqual(helper.MPV_RAW_PREFIX, "$>")
        self.assertIn(["set_property", "force-media-title", "${path} ${options/input-ipc-server}"], server.commands)
        self.assertEqual(sum(1 for c in server.commands if c[:2] == ["set_property", "title"]), 1)
        self.assertNotIn("user:pw", stdout + stderr)


class ShownNamesTest(MpvTestCase):
    """F-SINK-14 (2026-10-29): the player's window title is the name the guide
    row shows. apply_channel set mpv's `title` and `force-media-title` from the
    RAW channel name, so a playlist name holding a credentialed URL became the
    compositor's toplevel title -- read by every client that lists windows --
    while the guide row printed the host. It now sets both from redact_urls,
    the helper's mirror of Model.sinkText, keeping the `$>` prefix (S-01).

    Driven over the SHARED fixture tests/Model.test.js runs every shown-name
    composer over (tests/fixtures/shown-names.json), through the shipping
    `play` verb against FakeMpv: `py` is exactly what each property is set to.
    Red on dev 2727179: every name with a URL went out whole."""

    def names(self):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "fixtures", "shown-names.json"), encoding="utf-8") as fh:
            return json.load(fh)["names"]

    def test_redact_urls_is_the_fixture_s_py_output(self):
        bad = [(v["why"], helper.redact_urls(v["name"])) for v in self.names() if helper.redact_urls(v["name"]) != v["py"]]
        self.assertEqual([], bad)

    def test_play_sets_title_and_force_media_title_to_the_shown_name(self):
        names = self.names()
        playlist = os.path.join(self.dir, "shown.m3u")
        lines = ["#EXTM3U"]
        for i, v in enumerate(names):
            lines.append('#EXTINF:-1 tvg-id="n%d.test",%s' % (i, v["name"]))
            lines.append("http://stream.example.test/live/n%d.m3u8" % i)
        pathlib.Path(playlist).write_text("\n".join(lines) + "\n", encoding="utf-8")
        code, _, _, stderr = run("playlist", "--url", playlist, "--cache-dir", self.cache)
        self.assertEqual(code, 0, stderr)
        seen = []
        for i, v in enumerate(names):
            with self.subTest(why=v["why"]):
                sock = os.path.join(self.dir, "s%d.sock" % i)
                server = FakeMpv(sock)
                self.addCleanup(server.close)
                code, payload, stdout, stderr = run("play", "--id", "t:n%d.test" % i, "--cache-dir", self.cache,
                                                    "--socket", sock, "--ipc-timeout", "1")
                self.assertEqual(code, 0, stderr)
                titles = [c[2] for c in server.commands if c[:2] == ["set_property", "title"]]
                forced = [c[2] for c in server.commands if c[:2] == ["set_property", "force-media-title"]]
                self.assertEqual(titles, [helper.MPV_RAW_PREFIX + v["py"]])
                self.assertEqual(forced, [v["py"]])
                for frag in v["mustNotAppear"]:
                    self.assertNotIn(frag, titles[0] + forced[0])
                seen.append(v["py"])
        self.assertEqual(len(seen), len(names))


class TitleControlsTest(MpvTestCase):
    """F-SINK-16 (2026-10-29): the player's title carries no control
    character. The playlist parse keeps a provider's C0 and C1 controls in a
    channel name (measured: ESC, BEL, BS, DEL, U+009B and U+009D survive into
    channels.json), apply_channel set them as mpv's `title`, and a toplevel
    title is printed raw by the tools a user runs in a terminal. They are
    dropped before the redaction, so a tab inside a password no longer
    splits the URL (D-SINK-34's cost) on this sink either. Red on dev
    2727179: the title carried every control and the whole URL."""

    def test_title_and_media_title_carry_no_control_character(self):
        name = "News\x1b]52;c;aGk=\x07 \x1b[2J\x08\x7f \x9b31m\x9d0;x\x9c (http://u5er:pa\tS3CRET@cdn.test/x)"
        playlist = os.path.join(self.dir, "controls.m3u")
        pathlib.Path(playlist).write_text('#EXTM3U\n#EXTINF:-1 tvg-id="ctl.test",%s\nhttp://stream.example.test/live/c.m3u8\n' % name,
                                          encoding="utf-8")
        code, _, _, stderr = run("playlist", "--url", playlist, "--cache-dir", self.cache)
        self.assertEqual(code, 0, stderr)
        server = self.start()
        code, payload, _, stderr = self.play("--id", "t:ctl.test")
        self.assertEqual(code, 0, stderr)
        # The cache really holds the controls: this is the parse's output, not
        # a name the test made up after it.
        self.assertIn("\x1b", payload["name"])
        self.assertIn("\x9b", payload["name"])
        titles = [c[2] for c in server.commands if c[:2] == ["set_property", "title"]]
        forced = [c[2] for c in server.commands if c[:2] == ["set_property", "force-media-title"]]
        self.assertEqual(titles, ["$>News]52;c;aGk= [2J 31m0;x (http://cdn.test)"])
        self.assertEqual(forced, ["News]52;c;aGk= [2J 31m0;x (http://cdn.test)"])


class TlsVerificationTest(MpvTestCase):
    """D-SINK-16: apply_channel asserts the certificate properties, and REFUSES
    to load when it cannot make them safe.

    The maintainer raised this against the SHIPPED 0.13.0
    (omacom/omarchy-plugin-marketplace#10389): 0.13.0 made every player this
    plugin LAUNCHES verify, by four layers that all live on the launch argv, and
    an adopted player's argv belongs to whatever version started it. Our own
    filing (D-PLY-25) called that stale state a user could restart away; he named
    the part that makes it live, which is that the helper goes on sending that
    same process new provider headers and new credentialed URLs.

    The failure case is the point of this class. `pause`, `aid` and `sid` are
    best effort because getting them wrong costs a black screen; TLS is not,
    because loading is the act of handing over the credential. `refuse` is the
    set that does not take and `missing` is the property that cannot be read -
    FakeMpv answers both the way mpv does (see its docstring, rule 10).
    """

    FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "player-tls.json"
    LOADFILE = ["loadfile", "http://stream.example.test/live/espn.m3u8", "replace", -1,
                dict(load_options("VLC/3.0.20", "http://ref.example.test/", ["X-Forwarded-For: 1.2.3.4"]))]

    def test_the_property_names_are_the_fixture_and_not_a_second_copy(self):
        """Rule 13: two literals joined by a name are joined by nothing. The
        shared fixture names them and Model.test.js asserts its own constants
        against the same two strings."""
        names = json.loads(self.FIXTURE.read_text(encoding="utf-8"))["properties"]
        self.assertEqual([helper.MPV_TLS_VERIFY_PROP, helper.MPV_STREAM_OPTS_PROP,
                          helper.MPV_DEMUXER_OPTS_PROP, helper.MPV_AUTO_PROFILES_PROP],
                         [names["verify"], names["streamOptions"], names["demuxerOptions"], names["autoProfiles"]])

    def test_the_shared_fixture_decides_the_rule_in_both_languages(self):
        """Rule 12: one fixture, both implementations. tests/Model.test.js runs
        the same cases through Model.tlsPropertiesSafe."""
        cases = json.loads(self.FIXTURE.read_text(encoding="utf-8"))["cases"]
        self.assertGreaterEqual(len(cases), 15)
        got = ["%s: %s" % (c["name"], helper.tls_properties_safe(c["verify"], c["optionCount"], c["unpinned"]))
               for c in cases]
        want = ["%s: %s" % (c["name"], c["safe"]) for c in cases]
        self.assertEqual(got, want)
        # The vectors that matter most are the ones a more forgiving reader would
        # wave through, so assert the fixture still carries them.
        self.assertIn(1, [c["verify"] for c in cases])
        self.assertIn(False, [c["optionCount"] for c in cases])
        self.assertIn(False, [c["unpinned"] for c in cases])
        self.assertIn(None, [c["unpinned"] for c in cases])
        self.assertEqual([c["safe"] for c in cases].count(True), 1)

    def test_both_properties_are_set_and_read_back_before_the_loadfile(self):
        server = self.start()
        code, _, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        names = [c[:2] for c in server.commands]
        load = server.commands.index(self.LOADFILE)
        for command in (["set_property", "tls-verify"], ["set_property", "stream-lavf-o"],
                        ["get_property", "tls-verify"], ["get_property", "stream-lavf-o"]):
            self.assertIn(command, names, command)
            self.assertLess(names.index(command), load, command)
        # In that order, and the set before its own read-back: a read taken
        # first would grade the player as it was found, not as it was left.
        self.assertLess(names.index(["set_property", "tls-verify"]), names.index(["set_property", "stream-lavf-o"]))
        self.assertLess(names.index(["set_property", "tls-verify"]), names.index(["get_property", "tls-verify"]))
        self.assertLess(names.index(["set_property", "stream-lavf-o"]), names.index(["get_property", "stream-lavf-o"]))
        # And the values are the safe ones, not merely the right properties.
        self.assertIn(["set_property", "tls-verify", True], server.commands)
        self.assertIn(["set_property", "stream-lavf-o", {}], server.commands)

    def test_a_pre_upgrade_player_is_migrated_and_then_loaded(self):
        """The exposure, closed: a player with mpv's own defaults and a stale
        `tls_verify=0` left in `stream-lavf-o` by a user argument 0.12.1 did not
        reserve. Both are gone before the URL goes out, and the channel plays."""
        server = self.start(props={"tls-verify": False, "stream-lavf-o": {"tls_verify": "0"}})
        code, payload, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["ok"])
        self.assertIn(self.LOADFILE, server.commands)
        self.assertIs(server.props["tls-verify"], True)
        self.assertEqual(server.props["stream-lavf-o"], {})

    def test_a_player_already_verifying_is_left_as_it_is_and_loaded(self):
        server = self.start(props={"tls-verify": True})
        code, payload, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        self.assertTrue(payload["ok"])
        self.assertIn(self.LOADFILE, server.commands)
        self.assertIs(server.props["tls-verify"], True)

    def test_a_refused_tls_verify_aborts_before_the_loadfile(self):
        server = self.start(refuse={"tls-verify"})
        code, payload, stdout, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 1)
        self.assertEqual(payload["kind"], "play")
        self.assertEqual(payload["error"]["code"], "tls_unverified")
        self.assertNotIn(self.LOADFILE, server.commands)
        self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])
        # And nothing about the channel reached it either: the refusal is raised
        # before the title, so an unsecurable player is not even relabelled.
        self.assertEqual([c for c in server.commands if c[:2] == ["set_property", "title"]], [])
        self.assertEqual([c for c in server.commands if c[:2] == ["set_property", "http-header-fields"]], [])
        # Rule 5: the refusal names no URL and no header value, on either stream.
        for secret in ("espn.m3u8", "stream.example.test", "VLC/3.0.20", "ref.example.test"):
            self.assertNotIn(secret, stdout + stderr, secret)

    def test_a_refused_stream_lavf_o_clear_aborts_before_the_loadfile(self):
        """The layer-3 shape: mpv's own flag says yes while FFmpeg's AVOption
        says no, and the AVOption wins (measured, D-SINK-13). A clear that does
        not take is therefore a refusal, not a warning."""
        server = self.start(props={"tls-verify": True, "stream-lavf-o": {"tls_verify": "0"}},
                            refuse={"stream-lavf-o"})
        code, payload, _, _ = self.play("--id", "t:espn.us")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "tls_unverified")
        self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])

    def test_an_unreadable_property_aborts_before_the_loadfile(self):
        """A set that answers `success` is a statement about the request, not
        about the value, so the read-back is the judge - and a player that
        cannot be read is not a player that can be graded safe."""
        for name in ("tls-verify", "stream-lavf-o"):
            with self.subTest(property=name):
                server = self.start(missing={name})
                code, payload, _, _ = self.play("--id", "t:espn.us")
                self.assertEqual(code, 1)
                self.assertEqual(payload["error"]["code"], "tls_unverified")
                self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])
                server.close()
                self.server = None

    def test_the_refusal_is_a_failed_play_and_not_a_silent_no_op(self):
        """The caller has to treat it as a failed play: exit 1, an `ok: false`
        reply with the stable code the shell switches on, and a journal line.
        Model.playFailureVerdict("tls_unverified") is "failed" on the other side
        of that boundary (tests/Model.test.js)."""
        self.start(refuse={"tls-verify"})
        code, payload, stdout, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 1)
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["error"]["code"], "tls_unverified")
        self.assertIn("verify", payload["error"]["message"])
        self.assertIn("tls-verify", stderr)
        self.assertEqual(len(stdout.strip().splitlines()), 1)

    def test_the_journal_line_carries_the_readings_and_nothing_out_of_the_map(self):
        """Diagnosable without being a sink: a three-valued flag and a count.
        `stream-lavf-o` can hold a proxy address with credentials in it."""
        self.start(props={"stream-lavf-o": {"tls_verify": "0", "http_proxy": "http://u:pw@proxy.test"}},
                   refuse={"tls-verify", "stream-lavf-o"})
        code, payload, stdout, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "tls_unverified")
        self.assertIn("tls-verify reads False", stderr)
        self.assertIn("stream-lavf-o holds 2 entries", stderr)
        for secret in ("u:pw", "proxy.test", "http_proxy", "tls_verify"):
            self.assertNotIn(secret, stdout + stderr, secret)

    def test_mutating_the_refusal_into_best_effort_lets_the_url_out(self):
        """Rule 11 where there is no `before`: break the one decision this
        function exists to make and watch the load happen anyway.

        assert_tls_verification() differs from its three neighbours in exactly
        one way - it raises instead of shrugging - so the mutation is to shrug.
        If this passes, the test above it is proving nothing.
        """
        server = self.start(refuse={"tls-verify"})
        original = helper.assert_tls_verification

        def best_effort(client, label):
            try:
                original(client, label)
            except helper.HelperError:
                return
        helper.assert_tls_verification = best_effort
        self.addCleanup(setattr, helper, "assert_tls_verification", original)
        code, payload, _, _ = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, "the mutation must reach the load, or the test above is decoration")
        self.assertTrue(payload["ok"])
        self.assertIn(self.LOADFILE, server.commands)
        self.assertIs(server.props["tls-verify"], False)


class PinnedTlsTest(MpvTestCase):
    """D-SINK-43 and D-SINK-44 at the IPC layer (2026-10-29): the third reading.

    The launch argv's pin block binds a player THIS release starts. Over IPC the
    helper must also bind one it did not start (D-SINK-16's shape), and must
    not be fooled by what happens AFTER its read-back: libavformat hands
    `demuxer-lavf-o` to every segment open of an HLS or DASH stream, so a
    `tls_verify=0` or a `verifyhost=` there undoes verification (measured);
    auto_profiles.lua applies a profile-cond profile at load, over the
    command line (measured); and mpv applies the user's [protocol.*] and
    [extension.*] profiles at file load to every option that was not set on
    the command line -- a set_property is not one -- which a pre-pin player
    read back as safe and then fetched from the attacker anyway (measured).
    FakeMpv answers each property the way mpv 0.41 measured does (rule 10).
    """

    LOADFILE = ["loadfile", "http://stream.example.test/live/espn.m3u8", "replace", -1,
                dict(load_options("VLC/3.0.20", "http://ref.example.test/", ["X-Forwarded-For: 1.2.3.4"]))]

    def loaded(self, server):
        return [c for c in server.commands if c[0] == "loadfile"] == [self.LOADFILE]

    def test_a_player_launched_with_the_pins_is_read_and_not_rewritten(self):
        """The common path costs reads only: nothing to remove, nothing to turn
        off, and no profile list, because every option a per-file profile
        could undo is already set from the command line."""
        server = self.start(props=dict(PINNED_PROPS), cmdline=PINNED_CMDLINE)
        code, payload, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        self.assertTrue(self.loaded(server))
        self.assertEqual([c for c in server.commands if c[0] == "change-list"], [])
        self.assertNotIn(["set_property", "load-auto-profiles", "no"], server.commands)
        self.assertNotIn(["get_property", "profile-list"], server.commands)

    def test_demuxer_tls_entries_are_removed_before_the_load_and_the_workaround_kept(self):
        """D-SINK-43 on a player that holds them: both kinds go, by key, and the
        user's own live_start_index stays. The removals precede the load."""
        server = self.start(props={"demuxer-lavf-o": dict(LISTS, tls_verify="0", verifyhost="evil.example",
                                                          live_start_index="-1")})
        code, payload, stdout, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        self.assertTrue(self.loaded(server))
        self.assertEqual(server.props["demuxer-lavf-o"], dict(LISTS, live_start_index="-1"))
        removes = [i for i, c in enumerate(server.commands) if c[:3] == ["change-list", "demuxer-lavf-o", "remove"]]
        self.assertEqual(sorted(server.commands[i][3] for i in removes), ["tls_verify", "verifyhost"])
        self.assertLess(max(removes), server.commands.index(self.LOADFILE))
        for secret in ("evil.example", "verifyhost"):
            self.assertNotIn(secret, stdout + stderr, secret)

    def test_a_tls_verify_entry_reading_one_is_left_alone(self):
        server = self.start(props={"demuxer-lavf-o": dict(LISTS, tls_verify="1", live_start_index="-1")})
        code, _, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        self.assertEqual([c for c in server.commands if c[0] == "change-list"], [])

    def test_a_demuxer_entry_that_cannot_be_removed_refuses_the_load(self):
        for options in ({"tls_verify": "0"}, {"verify": "0"}, {"verifyhost": "evil.example"},
                        {"ca_file": "/tmp/evil.pem"}, {"cafile": "/tmp/evil.pem"}, {"listen": "1"},
                        {"external_sock": "1"}):
            with self.subTest(options=sorted(options)):
                server = self.start(props={"demuxer-lavf-o": dict(options, **LISTS)},
                                    refuse={"demuxer-lavf-o"})
                code, payload, _, stderr = self.play("--id", "t:espn.us")
                self.assertEqual(code, 1, stderr)
                self.assertEqual(payload["error"]["code"], "tls_unverified")
                self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])
                self.assertIn("1 other TLS pins are not held", stderr)
                server.close()
                self.server = None

    def test_the_protocol_whitelist_is_appended_whole_and_read_back(self):
        """D-SINK-55 (2026-10-29): a stream server that answers with an SDP
        body made the player LISTEN, through the whitelist the sdp demuxer
        inherited (measured). The pin block gives a player of this release the
        list; a player that lacks it -- or holds another -- gets it appended
        as ONE key, the user's other keys kept, and is loaded only once the
        read-back says it holds exactly that list."""
        for found in ({}, {"protocol_whitelist": "file,http,rtp,udp", "live_start_index": "-1"}):
            with self.subTest(found=found):
                server = self.start(props={"demuxer-lavf-o": dict(found)})
                code, _, _, stderr = self.play("--id", "t:espn.us")
                self.assertEqual(code, 0, stderr)
                self.assertTrue(self.loaded(server))
                self.assertIn(["change-list", "demuxer-lavf-o", "append", "protocol_whitelist=" + WHITELIST],
                              server.commands)
                want = dict(found, **LISTS)
                self.assertEqual(server.props["demuxer-lavf-o"], want)
                server.close()
                self.server = None

    def test_a_player_that_cannot_take_the_whitelist_is_not_loaded_into(self):
        for found in ({}, {"protocol_whitelist": "file,http,rtp,udp"}, {"protocol_whitelist": WHITELIST + ",rtp"},
                      dict(LISTS, protocol_whitelist="file,http")):
            with self.subTest(found=found):
                server = self.start(props={"demuxer-lavf-o": dict(found)}, refuse={"demuxer-lavf-o"})
                code, payload, _, stderr = self.play("--id", "t:espn.us")
                self.assertEqual(code, 1, stderr)
                self.assertEqual(payload["error"]["code"], "tls_unverified")
                self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])
                server.close()
                self.server = None

    def test_the_format_whitelist_is_appended_whole_and_read_back(self):
        """D-SINK-62 (lane-p1c, 2026-10-29). A stream server that answers with
        an IMF composition playlist made FFmpeg open the asset URIs it named,
        and the player LISTENED on 0.0.0.0 -- through a protocol list that has
        to hold tcp (measured by rc-p1b). The pin block gives a player of this
        release the demuxer's format list; a player that lacks it, or holds
        another, gets it appended as ONE key, the user's keys kept, and is
        loaded only once the read-back says it holds exactly that list."""
        for found in ({"protocol_whitelist": WHITELIST},
                      {"protocol_whitelist": WHITELIST, "format_whitelist": "hls,imf,concat", "live_start_index": "-1"}):
            with self.subTest(found=found):
                server = self.start(props={"demuxer-lavf-o": dict(found)})
                code, _, _, stderr = self.play("--id", "t:espn.us")
                self.assertEqual(code, 0, stderr)
                self.assertTrue(self.loaded(server))
                append = ["change-list", "demuxer-lavf-o", "append", "format_whitelist=" + FORMATS]
                self.assertIn(append, server.commands)
                self.assertLess(server.commands.index(append), server.commands.index(self.LOADFILE))
                self.assertEqual(server.props["demuxer-lavf-o"], dict(found, **LISTS))
                server.close()
                self.server = None

    def test_the_segment_demuxers_options_are_removed_before_the_load(self):
        """D-SINK-64 (lane-p1c, 2026-10-29). hls's `seg_format_options` is a
        dictionary FFmpeg parses with its own escapes, so a key the token
        filter refuses can be spelled past it inside one: measured, a
        `format\\_whitelist` there replaced the pinned list in the HLS
        segment's context, and with `extension_picky=0` beside it an SDP
        segment made the player listen. On a player that holds one -- a
        pre-pin player, or a user's mpv.conf -- the key goes, by name, before
        the load, the user's other keys kept, and its value never reaches the
        reply or the journal (it is the user's text)."""
        value = "format\\_whitelist=sdp:protocol\\_whitelist=rtp,udp"
        server = self.start(props={"demuxer-lavf-o": dict(LISTS, seg_format_options=value, live_start_index="-1")})
        code, _, stdout, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        self.assertTrue(self.loaded(server))
        remove = ["change-list", "demuxer-lavf-o", "remove", "seg_format_options"]
        self.assertIn(remove, server.commands)
        self.assertLess(server.commands.index(remove), server.commands.index(self.LOADFILE))
        self.assertEqual(server.props["demuxer-lavf-o"], dict(LISTS, live_start_index="-1"))
        for secret in ("sdp", "seg_format_options"):
            self.assertNotIn(secret, stdout + stderr, secret)
        server.close()
        self.server = None
        # ...and a player that will not let it go is not loaded into.
        server = self.start(props={"demuxer-lavf-o": dict(LISTS, seg_format_options=value)}, refuse={"demuxer-lavf-o"})
        code, payload, _, _ = self.play("--id", "t:espn.us")
        self.assertEqual((code, payload["error"]["code"]), (1, "tls_unverified"))
        self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])

    def test_rtsps_listen_timeout_is_removed_before_the_load(self):
        """rc-p1c (2026-10-29). The rtsp demuxer's `listen_timeout` IMPLIES its
        listen flag, and it is the key that flag cannot bind without; a token
        naming it is refused by the word `listen`, but the read-back removed
        only an exact `listen`, so an mpv.conf `demuxer-lavf-o=listen_timeout=5`
        made an rtsp channel bind its URL's host and port (measured inside
        `unshare -rn`). It goes by name before the load, the user's other keys
        kept, and a player that will not let it go is not loaded into."""
        server = self.start(props={"demuxer-lavf-o": dict(LISTS, listen_timeout="5", rtsp_flags="prefer_tcp")})
        code, _, stdout, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        self.assertTrue(self.loaded(server))
        remove = ["change-list", "demuxer-lavf-o", "remove", "listen_timeout"]
        self.assertIn(remove, server.commands)
        self.assertLess(server.commands.index(remove), server.commands.index(self.LOADFILE))
        self.assertEqual(server.props["demuxer-lavf-o"], dict(LISTS, rtsp_flags="prefer_tcp"))
        server.close()
        self.server = None
        server = self.start(props={"demuxer-lavf-o": dict(LISTS, listen_timeout="5")}, refuse={"demuxer-lavf-o"})
        code, payload, _, _ = self.play("--id", "t:espn.us")
        self.assertEqual((code, payload["error"]["code"]), (1, "tls_unverified"))
        self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])

    def test_a_player_with_reset_on_next_file_is_not_loaded_into(self):
        """D-SINK-60 (lane-p1b, 2026-10-29). mpv backs up the options
        `reset-on-next-file` names when a file STARTS and restores them when it
        ENDS, inside the next loadfile -- after any read-back. Measured on mpv
        0.41.0: with `all`, tls-verify set true over IPC during one file read
        true, and the next load, of a self-signed server, read false again and
        fetched from it; and a player started by v0.15.0's argv whose demuxer
        tls_verify=0 was removed AND whose list was emptied over IPC still
        sent the next HLS segment request to the attacker (the list itself was
        restored too). So a player holding ANY entry is refused, and nothing
        writes the list: emptying it would only make the read-back lie."""
        for value in (["all"], ["tls-verify"], ["http-header-fields"]):
            with self.subTest(value=value):
                server = self.start(props={"reset-on-next-file": value})
                code, payload, _, _ = self.play("--id", "t:espn.us")
                self.assertEqual(code, 1)
                self.assertEqual(payload["error"]["code"], "tls_unverified")
                self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])
                self.assertEqual([c for c in server.commands if c[:2] == ["set_property", "reset-on-next-file"]], [])
                self.assertIn(["get_property", "reset-on-next-file"], server.commands)
                server.close()
                self.server = None
        server = self.start(missing={"reset-on-next-file"})
        code, payload, _, _ = self.play("--id", "t:espn.us")
        self.assertEqual((code, payload["error"]["code"]), (1, "tls_unverified"), "an unreadable list is not an empty one")
        server.close()
        self.server = None

    def test_mutating_the_reset_reading_lets_the_url_out(self):
        """Rule 11 for D-SINK-60: read a refused reset-on-next-file as empty
        and the player that keeps `all` is loaded into."""
        original = helper.read_tls_state

        def blind(client):
            verify, count, unpinned = original(client)
            return verify, count, (unpinned - 1 if isinstance(unpinned, int) and unpinned > 0 else unpinned)
        helper.read_tls_state = blind
        self.addCleanup(setattr, helper, "read_tls_state", original)
        server = self.start(props={"reset-on-next-file": ["all"]})
        code, _, _, _ = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, "the mutation must reach the load, or the reset test is decoration")
        self.assertTrue(self.loaded(server))

    def test_auto_profiles_are_turned_off_and_read_back_as_mpv_answers(self):
        """mpv answers `no` of this choice as the boolean False: the set takes
        the string, the read-back is the boolean, and that is what passes."""
        server = self.start()
        code, _, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        self.assertIs(server.props["load-auto-profiles"], False)
        self.assertLess(server.commands.index(["set_property", "load-auto-profiles", "no"]),
                        server.commands.index(self.LOADFILE))

    def test_auto_profiles_that_cannot_be_turned_off_refuse_the_load(self):
        for props in ({}, {"load-auto-profiles": True}):
            with self.subTest(props=props):
                server = self.start(props=props, refuse={"load-auto-profiles"})
                code, payload, _, _ = self.play("--id", "t:espn.us")
                self.assertEqual(code, 1)
                self.assertEqual(payload["error"]["code"], "tls_unverified")
                self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])
                server.close()
                self.server = None

    def test_the_string_no_is_not_the_reading_mpv_gives(self):
        """Rule 10 in the other direction: a reader that accepted "no" would be
        more forgiving than mpv, which never sends it."""
        server = self.start(props={"load-auto-profiles": "no"}, refuse={"load-auto-profiles"})
        code, payload, _, _ = self.play("--id", "t:espn.us")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "tls_unverified")

    def test_a_per_file_profile_on_a_loose_option_refuses_the_load(self):
        """The D-SINK-44 residual on a pre-pin player, closed: nothing over IPC
        can make `stream-lavf-o` command-line-set, so a [protocol.https]
        profile that sets it would apply at file load, after the read-back.
        That player is not loaded into. Counts only reach the journal."""
        profiles = [{"name": "protocol.https", "options": [{"key": "stream-lavf-o", "value": "tls_verify=0"}]}]
        server = self.start(props={"profile-list": profiles}, cmdline={"tls-verify"})
        code, payload, stdout, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "tls_unverified")
        self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])
        for secret in ("tls_verify=0", "protocol.https"):
            self.assertNotIn(secret, stdout + stderr, secret)

    def test_the_same_profile_is_harmless_on_a_pinned_player(self):
        profiles = [{"name": "protocol.https", "options": [{"key": "stream-lavf-o", "value": "tls_verify=0"},
                                                           {"key": "tls-verify", "value": "no"}]}]
        props = dict(PINNED_PROPS, **{"profile-list": profiles})
        server = self.start(props=props, cmdline=PINNED_CMDLINE)
        code, _, _, stderr = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, stderr)
        self.assertTrue(self.loaded(server))

    def test_a_per_file_profile_on_any_pinned_option_refuses_the_load(self):
        """The lead's decision on rc-mpvpin's recheck (2026-10-29): on a pre-pin
        player a [protocol.http] profile with save-watch-history,
        load-unsafe-playlists or load-select undid pin_adopted_player's runtime
        writes at every load (measured: the watch history got the
        credentialed path, a nested playlist truncated a scratch file, select
        forked ffmpeg with the URL). Such a player is now stopped rather than
        migrated, for EVERY option the pin block holds, an alias of one
        included."""
        for key in ("save-watch-history", "load-unsafe-playlists", "load-select", "script", "scripts-append",
                    "watch-later-directory", "osd-playlist-entry", "drag-and-drop", "script-opts-append",
                    "input-commands", "player-operation-mode", "reset-on-next-file", "log-file",
                    "no-load-select", "prefetch-playlist", "load-console", "load-osd-console"):
            with self.subTest(key=key):
                profiles = [{"name": "protocol.http", "options": [{"key": key, "value": "yes"}]}]
                server = self.start(props={"profile-list": profiles}, cmdline={"tls-verify"})
                code, payload, _, _ = self.play("--id", "t:espn.us")
                self.assertEqual(code, 1)
                self.assertEqual(payload["error"]["code"], "tls_unverified")
                self.assertEqual([c for c in server.commands if c[0] == "loadfile"], [])
                server.close()
                self.server = None

    def test_a_profile_named_by_a_per_file_profile_is_followed(self):
        nested = [{"name": "protocol.https", "options": [{"key": "profile", "value": "a,b"}]},
                  {"name": "a", "options": [{"key": "volume", "value": "50"}]},
                  {"name": "b", "options": [{"key": "profile", "value": "protocol.https"},
                                            {"key": "demuxer-lavf-o-append", "value": "tls_verify=0"}]}]
        harmless = [{"name": "extension.m3u8", "options": [{"key": "cache-secs", "value": "30"}]},
                    {"name": "gpu-hq", "options": [{"key": "stream-lavf-o", "value": "tls_verify=0"}]}]
        included = [{"name": "protocol.http", "options": [{"key": "include", "value": "/tmp/x.conf"}]}]
        for profiles, code_wanted in ((nested, 1), (harmless, 0), (included, 1)):
            with self.subTest(names=[p["name"] for p in profiles]):
                server = self.start(props={"profile-list": profiles}, cmdline={"tls-verify"})
                code, _, _, stderr = self.play("--id", "t:espn.us")
                self.assertEqual(code, code_wanted, stderr)
                server.close()
                self.server = None

    def test_an_unreadable_profile_list_or_flag_refuses_the_load(self):
        # The flag case was named here and not run (recheck, 2026-10-29):
        # read_profile_threats treating an unreadable flag as "set from the
        # command line" turned nothing red, and that reading skips the profile
        # list for the option -- a pre-pin player read as safe.
        for missing in ({"profile-list"}, {"option-info/stream-lavf-o/set-from-commandline"}):
            with self.subTest(missing=sorted(missing)):
                server = self.start(missing=missing)
                code, payload, _, _ = self.play("--id", "t:espn.us")
                self.assertEqual(code, 1)
                self.assertEqual(payload["error"]["code"], "tls_unverified")
                server.close()
                self.server = None

    def test_mutating_the_demuxer_reading_lets_the_url_out(self):
        """Rule 11: break demuxer_tls_unsafe -- read every map as clean -- and a
        player that keeps verifyhost (its removal refused) is loaded into."""
        original = helper.demuxer_tls_unsafe
        helper.demuxer_tls_unsafe = lambda options: 0 if isinstance(options, dict) else None
        self.addCleanup(setattr, helper, "demuxer_tls_unsafe", original)
        server = self.start(props={"demuxer-lavf-o": {"verifyhost": "evil.example"}}, refuse={"demuxer-lavf-o"})
        code, _, _, _ = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, "the mutation must reach the load, or the tests above are decoration")
        self.assertTrue(self.loaded(server))

    def test_mutating_the_profile_reading_lets_the_url_out(self):
        original = helper.per_file_profile_threats
        helper.per_file_profile_threats = lambda profiles, loose: 0 if isinstance(profiles, list) else None
        self.addCleanup(setattr, helper, "per_file_profile_threats", original)
        profiles = [{"name": "protocol.https", "options": [{"key": "stream-lavf-o", "value": "tls_verify=0"}]}]
        server = self.start(props={"profile-list": profiles}, cmdline={"tls-verify"})
        code, _, _, _ = self.play("--id", "t:espn.us")
        self.assertEqual(code, 0, "the mutation must reach the load, or the profile test is decoration")
        self.assertTrue(self.loaded(server))


class AdoptedPinsTest(MpvTestCase):
    """lane-p1c (2026-10-29): what pin_adopted_player now also writes on a
    player this helper did not start, called directly (rule 12). D-SINK-63:
    prefetch-playlist off, so an appended entry is never opened while the
    channel's per-file headers are live; D-SINK-61: load-console off, which
    unloads mpv's console at runtime. Both flags are read as the booleans
    mpv answers (measured) and written only where they differ."""

    def pin(self, server):
        client = helper.MpvIpc(self.sock, 1.0)
        client.connect()
        try:
            return helper.pin_adopted_player(client, self.sock)
        finally:
            client.close()

    def test_prefetch_and_the_console_are_turned_off_on_adoption(self):
        server = self.start(props={"prefetch-playlist": True, "load-console": True})
        self.assertEqual(self.pin(server), 0)
        self.assertIs(server.props["prefetch-playlist"], False)
        self.assertIs(server.props["load-console"], False)
        for prop in ("prefetch-playlist", "load-console"):
            self.assertIn(["get_property", prop], server.commands)
            self.assertIn(["set_property", prop, False], server.commands)

    def test_a_player_that_holds_them_already_is_only_read(self):
        server = self.start(props={"prefetch-playlist": False, "load-console": False})
        self.pin(server)
        sets = [c[1] for c in server.commands if c[0] == "set_property"]
        self.assertNotIn("prefetch-playlist", sets)
        self.assertNotIn("load-console", sets)

    def test_a_write_that_does_not_take_is_counted(self):
        server = self.start(props={"prefetch-playlist": True, "load-console": True},
                            refuse={"prefetch-playlist", "load-console"})
        self.assertGreaterEqual(self.pin(server), 2)
        self.assertIs(server.props["prefetch-playlist"], True)


class DemuxerAndProfileReadingTest(unittest.TestCase):
    """The two pure readings, called directly (rule 12)."""

    def test_demuxer_tls_unsafe_counts_exactly_the_tls_entries(self):
        w = dict(LISTS)
        for options, want in ((w, 0), (dict(w, live_start_index="-1", http_persistent="0"), 0),
                              (dict(w, tls_verify="1"), 0), (dict(w, verify="1"), 0),
                              (dict(w, tls_verify="0"), 1), (dict(w, tls_verify="true"), 1), (dict(w, verify="0"), 1),
                              (dict(w, verifyhost="x"), 1), (dict(w, ca_file="/x"), 1), (dict(w, cafile="/x"), 1),
                              (dict(w, listen="1"), 1), (dict(w, external_sock="1"), 1),
                              (dict(w, tls_verify="0", verifyhost="x", live_start_index="-1"), 2),
                              (dict(w, cert_file="/c.pem", key_file="/k.pem", http_proxy="http://p"), 0),
                              # D-SINK-55: the whitelist must read exactly the pinned list.
                              (dict(w, protocol_whitelist=WHITELIST + ",rtp,udp"), 1),
                              (dict(w, protocol_whitelist="file," + WHITELIST), 1), (dict(w, protocol_whitelist=""), 1),
                              ({"format_whitelist": FORMATS}, 1),
                              # D-SINK-62 (lane-p1c): the format list too, exactly.
                              ({"protocol_whitelist": WHITELIST}, 1), (dict(w, format_whitelist=FORMATS + ",imf"), 1),
                              (dict(w, format_whitelist="hls"), 1), (dict(w, format_whitelist=""), 1),
                              # D-SINK-64: the segment demuxer's options, whatever they hold.
                              (dict(w, seg_format_options=""), 1), (dict(w, seg_format_options="probesize=1"), 1),
                              # rc-p1c: rtsp's listen_timeout implies its listen flag, whatever it holds.
                              (dict(w, listen_timeout="5"), 1), (dict(w, listen_timeout="-1"), 1),
                              (dict(w, rtsp_flags="prefer_tcp"), 0),
                              ({}, 2), ({"tls_verify": "0"}, 3),
                              (None, None), ([], None), ("tls_verify=0", None)):
            with self.subTest(options=options):
                self.assertEqual(helper.demuxer_tls_unsafe(options), want)

    def test_per_file_profile_threats_reads_keys_and_follows_profiles(self):
        loose = ["stream-lavf-o", "demuxer-lavf-o", "demuxer-lavf-propagate-opts", "load-auto-profiles"]
        p = lambda name, *keys: {"name": name, "options": [{"key": k, "value": "v"} for k in keys]}
        for profiles, want in (([], 0), ([p("protocol.https", "volume")], 0),
                               ([p("protocol.https", "stream-lavf-o")], 1),
                               ([p("protocol.https", "stream-lavf-o-append")], 1),
                               ([p("extension.m3u8", "demuxer-lavf-o-set")], 1),
                               ([p("protocol.https", "tls-verify")], 0),       # tls-verify is not loose here
                               ([p("protocol.https", "no-load-auto-profiles")], 1),
                               ([p("named", "stream-lavf-o")], 0),             # named profiles apply only when asked
                               ([p("protocol.http", "include")], 1),
                               ([{"name": "protocol.https", "options": [{"key": "profile", "value": "x"}]},
                                 p("x", "demuxer-lavf-propagate-opts")], 1),
                               ([{"name": "protocol.https", "options": [{"key": "profile", "value": "protocol.https"}]}], 0),
                               ([p("protocol.https", "stream-lavf-o"), p("protocol.http", "stream-lavf-o")], 2),
                               (None, None), ("x", None)):
            with self.subTest(names=[x.get("name") for x in profiles] if isinstance(profiles, list) else profiles):
                self.assertEqual(helper.per_file_profile_threats(profiles, loose), want)


class StopTest(MpvTestCase):
    def test_ok_when_mpv_closes_without_answering(self):
        server = self.start(close_on_quit=True)
        code, payload, _, stderr = run("stop", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload, {"ok": True, "kind": "stop"})
        self.assertEqual(server.commands, [["quit"]])

    def test_ok_when_mpv_answers(self):
        self.start(close_on_quit=False)
        code, payload, _, _ = run("stop", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])

    def test_not_running_when_unreachable(self):
        code, payload, _, _ = run("stop", "--socket", self.sock)
        self.assertEqual(code, 1)
        self.assertEqual(payload["kind"], "stop")
        self.assertEqual(payload["error"]["code"], "not_running")


class StatusTest(MpvTestCase):
    def test_media_title_is_redacted_like_every_provider_string(self):
        # F-SINK-12 (review of the M5-01 round, pre-existing since M2-02):
        # media-title is the channel name the helper set through
        # --force-media-title, provider text, and it went out on stdout
        # verbatim. A name that carries a credentialed URL reaches the
        # sink as scheme and host only, like everything else the helper
        # prints.
        props = dict(STATUS_PROPS)
        props["media-title"] = "Sky One see http://user:s3cret@provider.example.test/live/tok/x.m3u8 now"
        self.start(props=props)
        code, payload, stdout, stderr = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["mediaTitle"], "Sky One see http://provider.example.test now")
        for secret in ("s3cret", "user:", "/live/", "tok", "x.m3u8"):
            self.assertNotIn(secret, stdout + stderr)

    def test_reports_host_never_path(self):
        self.start(props=STATUS_PROPS)
        code, payload, stdout, stderr = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload, {
            "ok": True, "kind": "status", "running": True, "mediaTitle": "BBC One HD",
            "pathHost": "provider.example.test", "paused": False, "idle": False, "mpvVersion": "mpv 0.41.0",
            # D-PLY-11: the health tick's reconciliation input. A player that
            # carries no record of ours answers null rather than dropping the
            # key, so the shell can tell "nothing to compare" from "the
            # helper is too old to be asked".
            "stash": None,
            # M5-01: the same for the rewind readout -- STATUS_PROPS carries
            # no time-pos, and "no position yet" is null, never zero.
            "rewind": None,
        })
        self.assertNotIn("path\"", stdout.replace("pathHost", ""))
        for secret in ("user:pw", "/live/", "1.m3u8"):
            self.assertNotIn(secret, stdout + stderr)

    def test_status_carries_the_players_own_now_playing_record(self):
        # D-PLY-11, the plan's step 2. Without this the health tick asks the
        # player five questions and never the one that matters - which
        # channel - so a shell whose label has diverged from the player has
        # no way to find out, which is why every divergence wave two produced
        # was still there two health ticks later.
        stash = helper.player_stash("t:espn.us", "ESPN", "Sport", "g:QA", "a1b2c3d4", 3000, 7,
                                    entry_id=2, verb="play")
        self.start(props=STATUS_PROPS, user_data={"omarchy-iptv": stash})
        code, payload, stdout, stderr = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(payload["stash"], stash)
        self.assertEqual(payload["stash"]["id"], "t:espn.us")
        self.assertEqual(payload["stash"]["seq"], 7)
        self.assertEqual(payload["stash"]["verb"], "play")
        # Rule 5: the record has never carried a URL and this new sink does
        # not become the first one.
        self.assertNotIn("://", stdout + stderr)

    def test_missing_properties_become_null(self):
        self.start(props={"mpv-version": "mpv 0.41.0", "pause": True})
        code, payload, _, _ = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(code, 0)
        self.assertIsNone(payload["mediaTitle"])
        self.assertIsNone(payload["pathHost"])
        self.assertTrue(payload["paused"])
        self.assertIsNone(payload["idle"])

    def test_local_path_reports_local_file(self):
        self.start(props={"path": "/home/user/video.mkv"})
        code, payload, stdout, _ = run("status", "--socket", self.sock, "--ipc-timeout", "1")
        self.assertEqual(payload["pathHost"], "local file")
        self.assertNotIn("video.mkv", stdout)

    def test_stale_socket_file_is_unlinked(self):
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(self.sock)
        listener.close()  # the file stays, nobody listens: ECONNREFUSED
        self.assertTrue(os.path.exists(self.sock))
        code, payload, _, stderr = run("status", "--socket", self.sock)
        self.assertEqual(code, 1)
        self.assertEqual(payload["kind"], "status")
        self.assertFalse(payload["running"])
        self.assertEqual(payload["error"]["code"], "not_running")
        self.assertFalse(os.path.exists(self.sock))
        self.assertIn("stale socket", stderr)

    def test_missing_socket_is_not_running(self):
        code, payload, _, _ = run("status", "--socket", self.sock)
        self.assertEqual(code, 1)
        self.assertEqual(payload["running"], False)
        self.assertEqual(payload["error"]["code"], "not_running")

    def test_regular_file_at_socket_path_is_left_alone(self):
        pathlib.Path(self.sock).write_text("not a socket", encoding="utf-8")
        code, payload, _, _ = run("status", "--socket", self.sock)
        self.assertEqual(code, 1)
        self.assertEqual(payload["error"]["code"], "not_running")
        self.assertTrue(os.path.exists(self.sock))


if __name__ == "__main__":
    unittest.main()
