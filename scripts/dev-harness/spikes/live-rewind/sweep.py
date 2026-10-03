#!/usr/bin/env python3
"""Live-rewind measurement pass (M4 decision D2). Measurement only; no build.

Plays real channels through mpv with the plugin's own base argv, reads the
properties that decide whether a backwards seek is possible, and then
ISSUES THE SEEK and reads whether the position actually moved and playback
continued. A property that says seekable and a seek that works are two
different facts.

IPC, and why this file does not reuse the plugin's reader: it matches every
reply to its request by `request_id`. The first M2-11 sweep matched by
position and had to be thrown away -- a `seekable` query came back holding a
leftover `time-pos`, a number and therefore truthy, and the sweep reported
17 of 17 seekable. Events are discarded, replies are indexed by id, and a
reply with no id is dropped rather than guessed at.

Process discipline: every mpv is started with its own socket in the short
directory given on argv -- never the plugin's own socket directory -- is
tracked by the pid this file holds, and is killed BY PID. Nothing here
matches a process by name or command line:
the owner's shell is a quickshell process and a pattern kill has twice gone
wrong in this project. Every wait is bounded and reports giving up.

URLs: the JSON output carries them because a later run has to replay them;
every line this file prints is redacted to scheme and host (requirement 5).
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time

sys.dont_write_bytecode = True

import verdict
from select_channels import redact

# The shipping base argv, bin/omarchy-iptv mpv_launch_argv() at the dev tip
# 64fa114. Copied rather than imported: importing the helper compiles it, and
# this spike owns nothing in bin/. Deviations from shipping are listed in
# EXTRA_* below and are named in the document.
BASE_ARGV = [
    "mpv",
    "--input-ipc-server=%s",
    "--wayland-app-id=omarchy-iptv",
    "--force-window=immediate",
    "--idle=once",
    "--keep-open=no",
    "--title=IPTV",
    "--force-media-title=IPTV",
    "--msg-level=all=error",
    "--ytdl=no",
    "--load-scripts=no",
]

# Headless by default: twenty-four windows in sequence would take over the
# owner's display for the length of the sweep, and neither video nor audio
# output touches the demuxer cache, which is the only thing being measured.
# `--seek-test` runs with real output so the picture can be seen to continue.
HEADLESS_ARGV = ["--vo=null", "--ao=null"]

PROPERTIES = (
    "seekable",
    "partially-seekable",
    "demuxer-cache-duration",
    "demuxer-cache-time",
    "demuxer-cache-state",
    "video-bitrate",
    "audio-bitrate",
    "cache-speed",
    "video-format",
    "file-format",
    "demuxer-via-network",
)


class Ipc:
    """A line-delimited JSON client for mpv's socket, matching by request_id."""

    def __init__(self, path, timeout=6.0):
        self.path = path
        self.timeout = timeout
        self.sock = None
        self.buffer = b""
        self.next_id = 1
        self.replies = {}
        self.events = 0
        # Pre-build pass M2: a list here captures every `log-message` event
        # the way the helper sees it after `request_log_messages`. The text
        # is NOT stored -- an mpv error line can name the URL it failed to
        # open -- only whether it is the refusal line, plus prefix and level.
        self.log_sink = None

    def connect(self, deadline):
        """Bounded connect. A refused connect is retried; the socket appears
        only once mpv has created it."""
        while time.monotonic() < deadline:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(self.timeout)
                sock.connect(self.path)
                self.sock = sock
                return True
            except (FileNotFoundError, ConnectionRefusedError, OSError):
                time.sleep(0.2)
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
            newline = self.buffer.find(b"\n")
            if newline >= 0:
                line = self.buffer[:newline]
                self.buffer = self.buffer[newline + 1:]
                return line
            if time.monotonic() >= deadline:
                return None
            try:
                self.sock.settimeout(max(0.05, min(1.0, deadline - time.monotonic())))
                chunk = self.sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                return None
            if not chunk:
                return None
            self.buffer += chunk


def _send(ipc, args):
    """Send one command and return (data, error) for THAT request id."""
    if ipc.sock is None:
        return None, "no socket"
    request_id = ipc.next_id
    ipc.next_id += 1
    line = json.dumps({"command": list(args), "request_id": request_id}) + "\n"
    try:
        ipc.sock.sendall(line.encode("utf-8"))
    except OSError as exc:
        return None, "send failed: %s" % exc.__class__.__name__
    deadline = time.monotonic() + ipc.timeout
    if request_id in ipc.replies:
        return ipc.replies.pop(request_id)
    while True:
        raw = ipc._readline(deadline)
        if raw is None:
            return None, "no reply within %.1fs" % ipc.timeout
        text = raw.strip()
        if not text:
            continue
        try:
            message = json.loads(text.decode("utf-8", "replace"))
        except ValueError:
            continue
        if not isinstance(message, dict):
            continue
        if "request_id" not in message:
            # An event, or a reply with no id. Never guessed at: this is the
            # exact mistake that voided the first M2-11 sweep.
            ipc.events += 1
            if ipc.log_sink is not None and message.get("event") == "log-message":
                text = str(message.get("text") or "")
                ipc.log_sink.append({
                    "t": time.monotonic(),
                    "level": message.get("level"),
                    "prefix": message.get("prefix"),
                    "cannotSeek": "Cannot seek in this stream" in text,
                })
            continue
        got = message.get("request_id")
        error = message.get("error")
        data = message.get("data")
        pair = (data, None if error == "success" else (error or "unknown error"))
        if got == request_id:
            return pair
        ipc.replies[got] = pair


def command(ipc, *args):
    return _send(ipc, args)


def get(ipc, name):
    data, error = command(ipc, "get_property", name)
    return (None, error) if error else (data, None)


def spawn(argv, log_path):
    """Start mpv detached from this shell's process group, return (proc, pid).

    stdout and stderr go to a file under the scratch directory so a crash
    reason survives the kill; nothing from mpv reaches this script's own
    output, where it could print an unredacted URL.
    """
    log = open(log_path, "wb")
    proc = subprocess.Popen(argv, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                            start_new_session=True)
    log.close()
    return proc


def reap(proc, label, out):
    """Kill one mpv BY PID, bounded, escalating. Returns the exit status."""
    if proc is None:
        return None
    if proc.poll() is not None:
        return proc.returncode
    for sig, grace in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 2.0)):
        try:
            os.kill(proc.pid, sig)
        except ProcessLookupError:
            break
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                return proc.returncode
            time.sleep(0.1)
    status = proc.poll()
    if status is None:
        out("  GAVE UP killing pid %d (%s): still alive after SIGTERM+SIGKILL" % (proc.pid, label))
    return status


def wait_for_playback(ipc, deadline, out):
    """Bounded wait until time-pos advances. Returns (ok, reason, first_pos)."""
    last = None
    while time.monotonic() < deadline:
        pos, error = get(ipc, "time-pos")
        if error is None and isinstance(pos, (int, float)):
            if last is not None and pos > last:
                return True, "", pos
            last = pos
        idle, _ = get(ipc, "idle-active")
        if idle is True and last is None:
            time.sleep(0.5)
            continue
        time.sleep(0.5)
    if last is None:
        return False, "no time-pos within the window", None
    return False, "time-pos never advanced (stuck at %.1f)" % last, last


def read_properties(ipc):
    readings = {}
    for name in PROPERTIES:
        value, error = get(ipc, name)
        readings[name] = value if error is None else None
        if error is not None:
            readings.setdefault("_errors", {})[name] = error
    return readings


def rss_kib(pid):
    """Resident memory of one pid, in KiB, or None.

    The demuxer cache lives in THIS process's address space, so the rewind
    window and the memory bill are the same measurement read two ways. On a
    7.6 GiB box that is the number that decides the feature, not the seek.
    """
    try:
        with open("/proc/%d/status" % pid, "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def measure_one(channel, args, out, index=0):
    """One channel, start to kill. Returns a row dict (never raises)."""
    key = channel["id"].replace("/", "_").replace(":", "_")
    # AF_UNIX paths cap at about 108 bytes and the scratch directory alone is
    # 104 of them, so the socket goes in a short directory of its own and is
    # named by index. mpv's only complaint is "Could not create IPC socket",
    # which looks exactly like a stream failure if you are not watching for it.
    sock_path = os.path.join(args.sock_dir, "s%02d" % index)
    log_path = os.path.join(args.scratch, "mpv-%s.log" % key[:48])
    row = {
        "id": channel["id"], "name": channel["name"], "group": channel["group"],
        "host": channel["host"], "urlRedacted": redact(channel["url"]),
        "played": False, "failure": "", "claim": "unseekable", "seek": "",
        "backBytesLimit": args.back_bytes,
    }
    argv = [part % sock_path if "%s" in part else part for part in BASE_ARGV]
    if args.headless:
        argv += HEADLESS_ARGV
    if args.back_bytes:
        argv.append("--demuxer-max-back-bytes=%d" % args.back_bytes)
    if args.forward_bytes:
        argv.append("--demuxer-max-bytes=%d" % args.forward_bytes)
    argv += list(args.extra or [])

    for stale in (sock_path,):
        try:
            os.unlink(stale)
        except OSError:
            pass

    proc = spawn(argv, log_path)
    ipc = Ipc(sock_path, timeout=args.ipc_timeout)
    try:
        if not ipc.connect(time.monotonic() + args.connect_timeout):
            row["failure"] = "no IPC socket within %.0fs" % args.connect_timeout
            return row
        # The plugin never puts a URL on the command line: the first channel
        # arrives over IPC like every later one (S-03). Same here.
        _, error = command(ipc, "loadfile", channel["url"], "replace")
        if error:
            row["failure"] = "loadfile refused: %s" % error
            return row
        ok, reason, _ = wait_for_playback(ipc, time.monotonic() + args.start_timeout, out)
        if not ok:
            row["failure"] = reason
            return row
        row["played"] = True

        # Let the back buffer fill. Everything below is read after this.
        soak_until = time.monotonic() + args.soak
        samples = []
        while time.monotonic() < soak_until:
            time.sleep(min(args.sample_every, max(0.1, soak_until - time.monotonic())))
            pos, _ = get(ipc, "time-pos")
            state, _ = get(ipc, "demuxer-cache-state")
            samples.append({
                "t": round(time.monotonic() - (soak_until - args.soak), 2),
                "pos": pos,
                # backSpan is the growth curve of the thing under measurement:
                # it climbs one second per second until the byte cap bites,
                # and the value it plateaus at IS the rewind window.
                "backSpan": verdict.back_span_seconds(state),
                "rangeSpan": verdict.seekable_range_span(state),
                "cacheEnd": (state or {}).get("cache-end") if isinstance(state, dict) else None,
                "readerPts": (state or {}).get("reader-pts") if isinstance(state, dict) else None,
                "fwBytes": (state or {}).get("fw-bytes") if isinstance(state, dict) else None,
                "totalBytes": (state or {}).get("total-bytes") if isinstance(state, dict) else None,
                "rssKiB": rss_kib(proc.pid),
            })
        row["samples"] = samples

        readings = read_properties(ipc)
        row["properties"] = readings
        state = readings.get("demuxer-cache-state")
        row["rangeSpan"] = verdict.seekable_range_span(state)
        row["backSpanS"] = verdict.back_span_seconds(state)
        row["claim"] = verdict.property_claim(
            readings.get("seekable"), readings.get("partially-seekable"), row["rangeSpan"])
        row["cacheDuration"] = readings.get("demuxer-cache-duration")
        vb = readings.get("video-bitrate") or 0
        ab = readings.get("audio-bitrate") or 0
        row["bitrateBps"] = (vb + ab) or None
        row["backWindowS"] = verdict.back_window_seconds(
            args.back_bytes or 50 * 1024 * 1024, row["bitrateBps"])

        # THE SEEK. Properties above are a claim; this is the fact.
        # Three frames when a window is up: one at the live edge, one straight
        # after the seek, one after letting it run on. Three decoded frames
        # from the rewound position are what "the picture continued" means;
        # a position number that moves is not the same evidence.
        shots = {}

        def shoot(label):
            if not (args.screenshot_dir and not args.headless):
                return
            path = os.path.join(args.screenshot_dir, "%s-%s.jpg" % (key[:40], label))
            _, error = command(ipc, "screenshot-to-file", path, "video")
            shots[label] = os.path.basename(path) if not error else "FAILED: %s" % error

        shoot("1-live-edge")
        before, _ = get(ipc, "time-pos")
        _, seek_error = command(ipc, "seek", str(-args.seek_back), "relative")
        row["seekError"] = seek_error or ""
        time.sleep(args.after_seek)
        after, _ = get(ipc, "time-pos")
        shoot("2-after-seek")
        time.sleep(args.resume_watch)
        later, _ = get(ipc, "time-pos")
        shoot("3-resumed")
        row["posBefore"], row["posAfter"], row["posLater"] = before, after, later
        row["achievedS"] = verdict.achieved_seconds(before, after)
        row["seek"] = verdict.seek_verdict(before, after, later, -args.seek_back)
        row["dropsAfterSeek"] = get(ipc, "frame-drop-count")[0]

        # THE FLOOR. A -20 seek says "20 seconds is available"; it does not
        # say how much is. So ask for far more than any buffer could hold and
        # read where it lands: the distance is the back-buffer window the
        # viewer would actually get, in seconds, on THIS channel's bitrate.
        if args.deep_seek:
            deep_before, _ = get(ipc, "time-pos")
            _, deep_error = command(ipc, "seek", str(-args.deep_seek), "relative")
            row["deepSeekError"] = deep_error or ""
            time.sleep(args.after_seek)
            deep_after, _ = get(ipc, "time-pos")
            time.sleep(args.resume_watch)
            deep_later, _ = get(ipc, "time-pos")
            row["deepBefore"], row["deepAfter"], row["deepLater"] = (
                deep_before, deep_after, deep_later)
            row["deepAchievedS"] = verdict.achieved_seconds(deep_before, deep_after)
            row["deepSeek"] = verdict.seek_verdict(
                deep_before, deep_after, deep_later, -args.deep_seek)
            deep_state, _ = get(ipc, "demuxer-cache-state")
            row["deepBackSpanS"] = verdict.back_span_seconds(deep_state)
        row["screenshots"] = shots
        return row
    finally:
        ipc.close()
        status = reap(proc, channel["name"], out)
        row["mpvExit"] = status
        row["ipcEventsIgnored"] = ipc.events
        try:
            os.unlink(sock_path)
        except OSError:
            pass


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("sample", help="JSON list from select_channels.py")
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--sock-dir", required=True,
                        help="short directory for the mpv IPC sockets; AF_UNIX caps "
                             "the path at ~108 bytes and the scratch path is longer")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip", type=int, default=0)
    parser.add_argument("--soak", type=float, default=30.0, help="seconds of playback before reading")
    parser.add_argument("--sample-every", type=float, default=5.0)
    parser.add_argument("--seek-back", type=float, default=20.0)
    parser.add_argument("--deep-seek", type=float, default=100000.0,
                        help="second seek, deliberately past any buffer, to find the floor; 0 skips it")
    parser.add_argument("--after-seek", type=float, default=2.0)
    parser.add_argument("--resume-watch", type=float, default=3.0)
    parser.add_argument("--connect-timeout", type=float, default=10.0)
    parser.add_argument("--start-timeout", type=float, default=25.0)
    parser.add_argument("--ipc-timeout", type=float, default=6.0)
    parser.add_argument("--back-bytes", type=int, default=0, help="0 = mpv default (50 MiB)")
    parser.add_argument("--forward-bytes", type=int, default=0)
    parser.add_argument("--extra", action="append", default=[],
                        help="an extra mpv option, repeatable; recorded in the output")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--windowed", dest="headless", action="store_false")
    parser.add_argument("--screenshot-dir", default="")
    args = parser.parse_args(argv)

    os.makedirs(args.scratch, exist_ok=True)
    os.makedirs(args.sock_dir, mode=0o700, exist_ok=True)
    probe = os.path.join(args.sock_dir, "s%02d" % len(PROPERTIES))
    if len(probe.encode("utf-8")) > 100:
        sys.stderr.write("sock-dir too long for an AF_UNIX path: %d bytes\n" % len(probe))
        return 2
    if args.screenshot_dir:
        os.makedirs(args.screenshot_dir, exist_ok=True)
    with open(args.sample, "r", encoding="utf-8") as handle:
        channels = json.load(handle)
    if args.skip:
        channels = channels[args.skip:]
    if args.limit:
        channels = channels[:args.limit]

    def out(text):
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    rows = []
    started = time.monotonic()
    for index, channel in enumerate(channels, 1):
        out("[%2d/%d] %s  %s  %s" % (index, len(channels), channel["name"],
                                     channel["group"], redact(channel["url"])))
        try:
            row = measure_one(channel, args, out, index)
        except Exception as exc:                      # a sweep never dies on one channel
            row = {"id": channel["id"], "name": channel["name"], "group": channel["group"],
                   "host": channel["host"], "urlRedacted": redact(channel["url"]),
                   "played": False, "failure": "harness error: %s: %s" % (
                       exc.__class__.__name__, exc)}
        rows.append(row)
        if row.get("played"):
            out("        seekable=%s partially=%s ranges=%s cacheDur=%s "
                "bitrate=%s -> claim=%s SEEK=%s achieved=%s" % (
                    (row.get("properties") or {}).get("seekable"),
                    (row.get("properties") or {}).get("partially-seekable"),
                    row.get("rangeSpan"), row.get("cacheDuration"),
                    row.get("bitrateBps"), row.get("claim"), row.get("seek"),
                    None if row.get("achievedS") is None else round(row["achievedS"], 2)))
            out("        backSpan=%s  deepSeek=%s deepAchieved=%s  window=%s s" % (
                None if row.get("backSpanS") is None else round(row["backSpanS"], 1),
                row.get("deepSeek"),
                None if row.get("deepAchievedS") is None else round(row["deepAchievedS"], 1),
                None if row.get("backWindowS") is None else round(row["backWindowS"], 1)))
        else:
            out("        FAILED: %s" % row.get("failure"))
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump({"rows": rows, "counts": verdict.summarise(rows),
                       "extra": list(args.extra or []),
                       "forwardBytes": args.forward_bytes,
                       "backBytes": args.back_bytes, "soak": args.soak,
                       "seekBack": args.seek_back, "headless": args.headless,
                       "mpvDefaultBackBytes": 50 * 1024 * 1024}, handle, indent=1)
    counts = verdict.summarise(rows)
    out("elapsed %.0fs  %s" % (time.monotonic() - started, json.dumps(counts)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
