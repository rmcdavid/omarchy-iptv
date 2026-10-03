#!/usr/bin/env python3
"""Second pass over live rewind, 2026-10-03: the open questions a DESIGN
depends on (docs/SPIKE-LIVE-REWIND.md section 8). Measurement only; no build.

Four questions, one function each, every one reading a PROPERTY and then
provoking the BEHAVIOUR the property claims, because this project was caught
once by reading `seekable` and never issuing the seek:

  q1  the zap: `loadfile <url> replace` on the same player, exactly as
      bin/omarchy-iptv apply_channel() issues it, with a 90 s back buffer
      behind it. What survives, and how soon can the new channel rewind.
  q2  pause against a FULL back buffer (a), against an empty one (b), after
      a rewind (c), and a rewind issued while paused (d).
  q3  the watchdog and the seek itself: IPC round trips around a `seek -300`
      at the plateau, resume latency, and whether "seconds behind live" can
      be computed on a 1 s tick.
  q4  the floor: is seekable-ranges[0].start the exact floor, and what a
      seek to start+1 / start / start-1 does; then a target inside the range
      that the cache cannot yet serve.

Pre-build pass, 2026-10-03 (docs/M5-01-LIVE-REWIND.md section 10, written
up in docs/SPIKE-LIVE-REWIND.md section 12):

  m1  every field of `demuxer-cache-state` at +30 s and at the plateau,
      with its type: the allowlist the helper forwards, and whether any
      leaf is a string that could carry a path or a URL.
  m2  the refusal detector: absolute seeks that land and seeks that are
      refused (below the floor, past the end), each with the immediate
      `time-pos` read, the read 1 s later and whether the error-level
      log line arrived over the socket the way `player start` sees it.
  m3  `show-text` on a REAL window with the plugin argv (muted, the one
      deviation): screenshot after the line, then fullscreen, then after
      an IPC `seek` to see whether mpv's own OSD bar appears.
  m4  the zero-point error: (wall - wall0) - (pos - pos0) at +60 s on
      three channels, zero point at the first numeric `time-pos` after
      the `loadfile` reply, zapping on one player as the plugin does.

Reuses sweep.py's socket client, spawner and killer, and verdict.py's
judgements; adds nothing to the mpv argv beyond what the plugin passes and
`--vo=null --ao=null` (neither touches the demuxer cache; section 1 of the
spike checked that against the real output).

Process discipline is sweep.py's: every mpv is held by pid, killed by pid,
every wait bounded. URLs never reach stdout; the JSON carries ids only.
"""

import argparse
import json
import os
import signal
import sys
import time

sys.dont_write_bytecode = True

import sweep
import verdict
from select_channels import redact
from sweep import command, get

MIB = 1024.0 * 1024.0

# bin/omarchy-iptv at dev tip b2f944d: MPV_RAW_PREFIX and the four directory
# options mpv_launch_argv() appends after --load-scripts=no. The spike's
# BASE_ARGV predates the prefix; the directories are content-free and point
# at this pass's own scratch here.
MPV_RAW_PREFIX = "$>"
USER_DATA_STASH = "user-data/omarchy-iptv"
USER_DATA_OWNER = "user-data/omarchy-iptv-owner"
MPV_DEFAULT_USER_AGENT = "libmpv"


def plugin_argv(sock_path, scratch, windowed=False):
    argv = [part % sock_path if "%s" in part else part for part in sweep.BASE_ARGV]
    argv = [("--title=%sIPTV" % MPV_RAW_PREFIX) if a == "--title=IPTV" else a for a in argv]
    dirs = os.path.join(scratch, "player-dirs")
    for sub in ("screenshots", "watch-later", "shader-cache"):
        os.makedirs(os.path.join(dirs, sub), mode=0o700, exist_ok=True)
    argv += [
        "--screenshot-dir=%s" % os.path.join(dirs, "screenshots"),
        "--watch-later-dir=%s" % os.path.join(dirs, "watch-later"),
        "--gpu-shader-cache-dir=%s" % os.path.join(dirs, "shader-cache"),
        "--icc-cache-dir=%s" % os.path.join(dirs, "shader-cache"),
    ]
    if windowed:
        # m3 needs the real video output. Audio would reach the owner's
        # speakers, so it is muted: `--mute` touches neither the cache nor
        # the OSD, and it is the only token the plugin does not pass.
        argv += ["--mute=yes"]
    else:
        argv += sweep.HEADLESS_ARGV
    return argv


def zap(ipc, channel, owner_pid):
    """The wire sequence of bin/omarchy-iptv apply_channel(), copied in
    order: pause off, aid/sid auto, title, force-media-title, the three
    header properties (always all three), the stash, loadfile replace, the
    stash again with the entry id, the owner claim.

    Returns (reply, error, loadfile_round_trip_s, t_after_reply).
    """
    command(ipc, "set_property", "pause", False)
    for prop in ("aid", "sid"):
        command(ipc, "set_property", prop, "auto")
    command(ipc, "set_property", "title", MPV_RAW_PREFIX + channel["name"])
    command(ipc, "set_property", "force-media-title", channel["name"])
    default_ua, _ = get(ipc, "option-info/user-agent/default-value")
    command(ipc, "set_property", "user-agent",
            default_ua if isinstance(default_ua, str) and default_ua else MPV_DEFAULT_USER_AGENT)
    command(ipc, "set_property", "referrer", "")
    command(ipc, "set_property", "http-header-fields", [])
    stash = {"schema": 1, "id": channel["id"], "name": channel["name"],
             "entryId": None, "verb": "play", "seq": 0}
    command(ipc, "set_property", USER_DATA_STASH, stash)
    t0 = time.monotonic()
    data, error = command(ipc, "loadfile", channel["url"], "replace")
    t1 = time.monotonic()
    entry = data.get("playlist_entry_id") if isinstance(data, dict) else None
    command(ipc, "set_property", USER_DATA_STASH, dict(stash, entryId=entry))
    command(ipc, "set_property", USER_DATA_OWNER,
            {"schema": 1, "pid": owner_pid, "startTime": 0, "at": int(time.time())})
    return data, error, t1 - t0, t1


def snapshot(ipc, pid, t_ref):
    """One reading of everything a rewind UI could consult, plus the
    derived numbers, stamped with seconds since t_ref."""
    pos, _ = get(ipc, "time-pos")
    state, _ = get(ipc, "demuxer-cache-state")
    cache_time, _ = get(ipc, "demuxer-cache-time")
    cache_dur, _ = get(ipc, "demuxer-cache-duration")
    paused, _ = get(ipc, "pause")
    pfc, _ = get(ipc, "paused-for-cache")
    entry, _ = get(ipc, "playlist-playing-pos")
    count, _ = get(ipc, "playlist-count")
    s = state if isinstance(state, dict) else {}
    ranges = []
    for r in s.get("seekable-ranges") or []:
        if isinstance(r, dict):
            try:
                ranges.append([round(float(r.get("start")), 3), round(float(r.get("end")), 3)])
            except (TypeError, ValueError):
                pass
    cache_end = s.get("cache-end")
    reader = s.get("reader-pts")
    return {
        "t": round(time.monotonic() - t_ref, 3),
        "pos": pos,
        "backSpan": verdict.back_span_seconds(state),
        "ranges": ranges,
        "cacheEnd": cache_end,
        "readerPts": reader,
        "cacheTime": cache_time,
        "cacheDuration": cache_dur,
        "fwBytes": s.get("fw-bytes"),
        "totalBytes": s.get("total-bytes"),
        "underrun": s.get("underrun"),
        "idle": s.get("idle"),
        "eof": s.get("eof"),
        "bof": s.get("bof"),
        "paused": paused,
        "pausedForCache": pfc,
        "playlistPos": entry,
        "playlistCount": count,
        "rssKiB": sweep.rss_kib(pid),
        "behindLive": verdict.behind_live_seconds(state, pos),
    }


def fmt(snap):
    tb = snap.get("totalBytes")
    fb = snap.get("fwBytes")
    return ("t=%7.2f pos=%s back=%s ranges=%s end=%s total=%s MiB fw=%s MiB behind=%s pfc=%s" % (
        snap["t"],
        None if snap["pos"] is None else round(snap["pos"], 2),
        None if snap["backSpan"] is None else round(snap["backSpan"], 1),
        snap["ranges"],
        None if snap["cacheEnd"] is None else round(snap["cacheEnd"], 2),
        None if tb is None else round(tb / MIB, 1),
        None if fb is None else round(fb / MIB, 1),
        None if snap["behindLive"] is None else round(snap["behindLive"], 1),
        snap["pausedForCache"]))


class Player:
    """One mpv, one socket, killed by pid in close()."""

    def __init__(self, args, index, out, windowed=False):
        self.args = args
        self.out = out
        self.sock_path = os.path.join(args.sock_dir, "d%02d" % index)
        try:
            os.unlink(self.sock_path)
        except OSError:
            pass
        self.log_path = os.path.join(args.scratch, "mpv-design-%02d.log" % index)
        log_path = self.log_path
        self.proc = sweep.spawn(plugin_argv(self.sock_path, args.scratch, windowed), log_path)
        self.pid = self.proc.pid
        out("  mpv pid %d on %s" % (self.pid, self.sock_path))
        self.ipc = sweep.Ipc(self.sock_path, timeout=args.ipc_timeout)
        if not self.ipc.connect(time.monotonic() + args.connect_timeout):
            raise RuntimeError("no IPC socket within %.0fs" % args.connect_timeout)

    def play(self, channel):
        """Zap exactly as the plugin does and wait, bounded, for time-pos to
        advance. Returns (t_loadfile_reply, loadfile_rtt)."""
        _, error, rtt, t1 = zap(self.ipc, channel, os.getpid())
        if error:
            raise RuntimeError("loadfile refused: %s" % error)
        ok, reason, _ = sweep.wait_for_playback(self.ipc, time.monotonic() + self.args.start_timeout, self.out)
        if not ok:
            raise RuntimeError(reason)
        return t1, rtt

    def close(self):
        self.ipc.close()
        status = sweep.reap(self.proc, "design pid %d" % self.pid, self.out)
        try:
            os.unlink(self.sock_path)
        except OSError:
            pass
        return status


def soak(player, seconds, every, t_ref, out, label):
    """Play for `seconds`, snapshot every `every`. Returns the snapshots."""
    snaps = []
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        time.sleep(min(every, max(0.1, until - time.monotonic())))
        snap = snapshot(player.ipc, player.pid, t_ref)
        snaps.append(snap)
        out("  %s %s" % (label, fmt(snap)))
    return snaps


def seek_and_judge(player, delta, t_ref, out, label, after=2.0, watch=3.0, mode="relative"):
    """Issue one seek, read the position three times, judge with verdict.py."""
    before, _ = get(player.ipc, "time-pos")
    pre = snapshot(player.ipc, player.pid, t_ref)
    t0 = time.monotonic()
    _, error = command(player.ipc, "seek", str(delta), mode)
    rtt = time.monotonic() - t0
    time.sleep(after)
    mid, _ = get(player.ipc, "time-pos")
    time.sleep(watch)
    later, _ = get(player.ipc, "time-pos")
    post = snapshot(player.ipc, player.pid, t_ref)
    if mode == "relative":
        result = verdict.seek_verdict(before, mid, later, delta)
    else:
        result = verdict.floor_seek_verdict(delta, before, mid, later,
                                            pre["ranges"][0][0] if pre["ranges"] else None)
    row = {"label": label, "mode": mode, "requested": delta, "error": error or "",
           "seekRttMs": round(rtt * 1000, 1), "before": before, "after": mid, "later": later,
           "achieved": verdict.achieved_seconds(before, mid), "verdict": result,
           "pre": pre, "post": post}
    out("  SEEK %s %s %s: before=%s after=%s later=%s achieved=%s -> %s (err=%s, rtt %.1f ms)" % (
        label, mode, delta, None if before is None else round(before, 2),
        None if mid is None else round(mid, 2), None if later is None else round(later, 2),
        None if row["achieved"] is None else round(row["achieved"], 2), result, error or "-", rtt * 1000))
    return row


# --- Q1 -------------------------------------------------------------------

def q1_zap(args, channels, out):
    a, b = channels[args.a], channels[args.b]
    out("Q1 zap: A=%s (%s)  B=%s (%s)" % (a["name"], redact(a["url"]), b["name"], redact(b["url"])))
    result = {"question": "q1", "a": a["id"], "b": b["id"], "aName": a["name"], "bName": b["name"],
              "aHost": redact(a["url"]), "bHost": redact(b["url"])}
    player = Player(args, 1, out)
    result['pid'] = player.pid
    try:
        t_a, _ = player.play(a)
        result["aSoak"] = soak(player, args.q1_soak, 10.0, t_a, out, "A")
        result["aBeforeZap"] = snapshot(player.ipc, player.pid, t_a)
        out("  A before zap: %s" % fmt(result["aBeforeZap"]))

        def zap_and_trace(channel, label, seconds):
            _, error, rtt, t_z = zap(player.ipc, channel, os.getpid())
            trace = []
            first_pos = first_range = first_back = None
            until = t_z + seconds
            while time.monotonic() < until:
                snap = snapshot(player.ipc, player.pid, t_z)
                trace.append(snap)
                if first_pos is None and isinstance(snap["pos"], (int, float)):
                    first_pos = snap["t"]
                if first_range is None and snap["ranges"]:
                    first_range = snap["t"]
                if first_back is None and snap["backSpan"] is not None and snap["backSpan"] >= 1.0:
                    first_back = snap["t"]
                time.sleep(0.25)
            marks = {}
            for want in (0, 1, 2, 5, 10, 20, 30):
                best = min(trace, key=lambda s: abs(s["t"] - want))
                if abs(best["t"] - want) <= 0.6:
                    marks[str(want)] = best
                    out("  %s +%2d s: %s" % (label, want, fmt(best)))
            out("  %s loadfile reply rtt %.1f ms; first time-pos at +%s s; first range at +%s s; "
                "first >=1 s of back buffer at +%s s" % (label, rtt * 1000, first_pos, first_range, first_back))
            return {"loadfileRttMs": round(rtt * 1000, 1), "loadfileError": error or "",
                    "firstPosS": first_pos, "firstRangeS": first_range, "firstBackS": first_back,
                    "marks": marks, "traceLen": len(trace), "t_z": t_z}

        zb = zap_and_trace(b, "B", args.q1_after)
        result["zapToB"] = zb
        result["bSeek"] = seek_and_judge(player, -20, zb["t_z"], out, "B at +30")
        za = zap_and_trace(a, "A again", 6.0)
        result["zapBackToA"] = za
        old = result["aBeforeZap"]
        at5 = za["marks"].get("5", za["marks"].get("2", {}))
        result["aOldHistoryVisible"] = verdict.history_survives(old["ranges"], at5.get("ranges"), at5.get("t"))
        out("  A's old ranges %s vs ranges 5 s after zapping back %s -> old history visible: %s" % (
            old["ranges"], za["marks"].get("5", {}).get("ranges"), result["aOldHistoryVisible"]))
        result["aSeekAt6"] = seek_and_judge(player, -20, za["t_z"], out, "A at +6 (start still cached)")
        remaining = 30.0 - (time.monotonic() - za["t_z"])
        if remaining > 0:
            time.sleep(remaining)
        result["aSeekAt30"] = seek_and_judge(player, -20, za["t_z"], out, "A at +30")
        result["aFinal"] = snapshot(player.ipc, player.pid, za["t_z"])
        out("  A final: %s" % fmt(result["aFinal"]))
    except Exception as exc:
        result["failure"] = "%s: %s" % (exc.__class__.__name__, exc)
        out("  FAILED: %s" % result["failure"])
    finally:
        result["mpvExit"] = player.close()
    return result


# --- Q2 -------------------------------------------------------------------

def pause_until_stall(player, t_ref, out, cap, every=5.0, still=3):
    """Pause, then sample until fw-bytes stops growing for `still` samples
    in a row or `cap` seconds pass. Returns (samples, stop_s, gave_up)."""
    _, error = command(player.ipc, "set_property", "pause", True)
    t_p = time.monotonic()
    samples = []
    flat = 0
    last_fw = None
    gave_up = True
    stop_s = None
    while time.monotonic() - t_p < cap:
        time.sleep(every)
        snap = snapshot(player.ipc, player.pid, t_ref)
        snap["sincePause"] = round(time.monotonic() - t_p, 1)
        samples.append(snap)
        out("  paused %5.0f s: %s" % (snap["sincePause"], fmt(snap)))
        fw = snap["fwBytes"]
        if last_fw is not None and fw is not None and abs(fw - last_fw) < 0.005 * max(1, last_fw):
            flat += 1
        else:
            flat = 0
        last_fw = fw
        if flat >= still:
            gave_up = False
            stop_s = samples[-1 - still]["sincePause"] if len(samples) > still else snap["sincePause"]
            break
    return samples, stop_s, gave_up, error


def resume_and_check(player, t_ref, out, label):
    before, _ = get(player.ipc, "time-pos")
    command(player.ipc, "set_property", "pause", False)
    time.sleep(2.0)
    at2, _ = get(player.ipc, "time-pos")
    time.sleep(3.0)
    at5, _ = get(player.ipc, "time-pos")
    row = {"label": label, "pausedAt": before, "at2": at2, "at5": at5,
           "continuedFromPausedPoint": verdict.resumed_from(before, at2, at5)}
    out("  RESUME %s: paused at %s, +2 s %s, +5 s %s -> continued from paused point: %s" % (
        label, before, at2, at5, row["continuedFromPausedPoint"]))
    return row


def q2a_pause_full(args, channels, out):
    ch = channels[args.a]
    out("Q2a pause with a full back buffer: %s (%s)" % (ch["name"], redact(ch["url"])))
    result = {"question": "q2a", "channel": ch["id"], "name": ch["name"], "host": redact(ch["url"])}
    player = Player(args, 2, out)
    result['pid'] = player.pid
    try:
        t0, _ = player.play(ch)
        result["soak"] = soak(player, args.q2_soak, 20.0, t0, out, "play")
        result["beforePause"] = snapshot(player.ipc, player.pid, t0)
        out("  before pause: %s" % fmt(result["beforePause"]))
        samples, stop_s, gave_up, err = pause_until_stall(player, t0, out, args.q2_cap)
        result.update({"pauseSamples": samples, "stopS": stop_s, "gaveUp": gave_up, "pauseError": err or ""})
        result["atStop"] = samples[-1] if samples else None
        out("  forward growth stopped after %s s (gave up: %s); at stop: %s" % (
            stop_s, gave_up, fmt(samples[-1]) if samples else None))
        result["resume"] = resume_and_check(player, t0, out, "after full-buffer pause")
    except Exception as exc:
        result["failure"] = "%s: %s" % (exc.__class__.__name__, exc)
        out("  FAILED: %s" % result["failure"])
    finally:
        result["mpvExit"] = player.close()
    return result


def q2b_pause_fresh(args, channels, out):
    ch = channels[args.a]
    out("Q2b pause at t=10 on a fresh stream (control): %s (%s)" % (ch["name"], redact(ch["url"])))
    result = {"question": "q2b", "channel": ch["id"], "name": ch["name"], "host": redact(ch["url"])}
    player = Player(args, 3, out)
    result['pid'] = player.pid
    try:
        t0, _ = player.play(ch)
        result["soak"] = soak(player, 10.0, 5.0, t0, out, "play")
        result["beforePause"] = snapshot(player.ipc, player.pid, t0)
        out("  before pause: %s" % fmt(result["beforePause"]))
        samples, stop_s, gave_up, err = pause_until_stall(player, t0, out, args.q2_cap)
        result.update({"pauseSamples": samples, "stopS": stop_s, "gaveUp": gave_up, "pauseError": err or ""})
        result["atStop"] = samples[-1] if samples else None
        out("  forward growth stopped after %s s (gave up: %s); at stop: %s" % (
            stop_s, gave_up, fmt(samples[-1]) if samples else None))
        result["resume"] = resume_and_check(player, t0, out, "after fresh pause")
    except Exception as exc:
        result["failure"] = "%s: %s" % (exc.__class__.__name__, exc)
        out("  FAILED: %s" % result["failure"])
    finally:
        result["mpvExit"] = player.close()
    return result


def q2cd_rewind_pause(args, channels, out):
    ch = channels[args.a]
    out("Q2c/d rewind then pause, pause then rewind: %s (%s)" % (ch["name"], redact(ch["url"])))
    result = {"question": "q2cd", "channel": ch["id"], "name": ch["name"], "host": redact(ch["url"])}
    player = Player(args, 4, out)
    result['pid'] = player.pid
    try:
        t0, _ = player.play(ch)
        result["soak"] = soak(player, 120.0, 20.0, t0, out, "play")
        # (c) rewind 60 then pause 60, resume
        result["cSeek"] = seek_and_judge(player, -60, t0, out, "c: -60 before pause")
        command(player.ipc, "set_property", "pause", True)
        t_p = time.monotonic()
        held = []
        while time.monotonic() - t_p < 60.0:
            time.sleep(10.0)
            snap = snapshot(player.ipc, player.pid, t0)
            snap["sincePause"] = round(time.monotonic() - t_p, 1)
            held.append(snap)
            out("  c paused %4.0f s: %s" % (snap["sincePause"], fmt(snap)))
        result["cHeld"] = held
        result["cPosDriftWhilePaused"] = verdict.achieved_seconds(held[0]["pos"], held[-1]["pos"]) if held else None
        result["cResume"] = resume_and_check(player, t0, out, "c: after rewind+pause")
        # (d) pause 60 s, then seek -30 while paused, then resume
        command(player.ipc, "set_property", "pause", True)
        t_p = time.monotonic()
        while time.monotonic() - t_p < 60.0:
            time.sleep(10.0)
            snap = snapshot(player.ipc, player.pid, t0)
            out("  d paused %4.0f s: %s" % (time.monotonic() - t_p, fmt(snap)))
        result["dSeekWhilePaused"] = seek_and_judge(player, -30, t0, out, "d: -30 while paused",
                                                    after=1.0, watch=2.0)
        result["dResume"] = resume_and_check(player, t0, out, "d: after seek while paused")
    except Exception as exc:
        result["failure"] = "%s: %s" % (exc.__class__.__name__, exc)
        out("  FAILED: %s" % result["failure"])
    finally:
        result["mpvExit"] = player.close()
    return result


# --- Q3 and Q4 --------------------------------------------------------------

def q34_watchdog_floor(args, channels, out):
    ch = channels[args.a]
    out("Q3/Q4 seek at the plateau, the tick, the floor: %s (%s)" % (ch["name"], redact(ch["url"])))
    result = {"question": "q34", "channel": ch["id"], "name": ch["name"], "host": redact(ch["url"])}
    player = Player(args, 5, out)
    result['pid'] = player.pid
    try:
        t0, _ = player.play(ch)
        snaps = []
        until = time.monotonic() + args.q3_cap
        plateau = False
        while time.monotonic() < until:
            time.sleep(20.0)
            snap = snapshot(player.ipc, player.pid, t0)
            snaps.append(snap)
            out("  fill %s" % fmt(snap))
            if verdict.at_plateau(snaps, 200 * MIB):
                plateau = True
                break
        result["fill"] = snaps
        result["plateauReached"] = plateau
        result["leadAtLiveEdge"] = [s["behindLive"] for s in snaps[-3:]]
        out("  plateau reached: %s; lead at live edge (cache end - pos) last 3: %s" % (
            plateau, result["leadAtLiveEdge"]))

        # Q3: the seek, timed, and the first get_property after it.
        before, _ = get(player.ipc, "time-pos")
        pre = snapshot(player.ipc, player.pid, t0)
        t_s = time.monotonic()
        _, seek_err = command(player.ipc, "seek", "-300", "relative")
        rtt_seek = time.monotonic() - t_s
        t_g = time.monotonic()
        pos0, get_err = get(player.ipc, "time-pos")
        rtt_get = time.monotonic() - t_g
        # resume latency: poll until time-pos has advanced 0.5 s past the first post-seek reading
        resume_at = None
        first = None
        poll_until = time.monotonic() + 10.0
        while time.monotonic() < poll_until:
            p, _ = get(player.ipc, "time-pos")
            if isinstance(p, (int, float)):
                if first is None:
                    first = p
                elif p - first >= 0.5:
                    resume_at = time.monotonic() - t_s
                    break
            time.sleep(0.1)
        result["q3"] = {"before": before, "seekError": seek_err or "", "seekRttMs": round(rtt_seek * 1000, 2),
                        "getRttMs": round(rtt_get * 1000, 2), "getError": get_err or "",
                        "posRightAfter": pos0, "firstPostSeekPos": first, "resumedAfterS": None if resume_at is None else round(resume_at, 2),
                        "achieved": verdict.achieved_seconds(before, pos0), "pre": pre}
        out("  Q3 seek -300: before=%s rtt(seek)=%.2f ms rtt(get time-pos)=%.2f ms pos right after=%s "
            "achieved=%s, time-pos advanced 0.5 s at +%s s" % (
                before, rtt_seek * 1000, rtt_get * 1000, pos0,
                None if result["q3"]["achieved"] is None else round(result["q3"]["achieved"], 2), result["q3"]["resumedAfterS"]))
        # 30 ticks at 1 s
        ticks = []
        t_tick = time.monotonic()
        for i in range(30):
            target = t_tick + i + 1
            snap = snapshot(player.ipc, player.pid, t0)
            snap["wall"] = round(time.monotonic() - t_s, 3)
            ticks.append(snap)
            out("  tick %2d %s cacheTime=%s dur=%s" % (
                i, fmt(snap), None if snap["cacheTime"] is None else round(snap["cacheTime"], 2),
                None if snap["cacheDuration"] is None else round(snap["cacheDuration"], 2)))
            rest = target - time.monotonic()
            if rest > 0:
                time.sleep(rest)
        result["ticks"] = ticks
        result["tickRate"] = verdict.tick_rate([(s["wall"], s["pos"]) for s in ticks])
        result["behindTrend"] = verdict.trend([s["behindLive"] for s in ticks])
        result["cacheEndTrend"] = verdict.trend([s["cacheEnd"] for s in ticks])
        out("  tick rate (pos per wall second): %s; behind-live first/last/trend: %s; cache-end trend: %s" % (
            result["tickRate"], result["behindTrend"], result["cacheEndTrend"]))

        # Q4: the floor.
        floor_rows = []
        for offset, label in ((1.0, "start+1"), (0.0, "start"), (-1.0, "start-1")):
            pre4 = snapshot(player.ipc, player.pid, t0)
            if not pre4["ranges"]:
                out("  Q4 %s: no ranges, skipped" % label)
                continue
            start = pre4["ranges"][0][0]
            row = seek_and_judge(player, round(start + offset, 3), t0, out, "Q4 " + label,
                                 after=1.0, watch=3.0, mode="absolute")
            row["floorAtIssue"] = start
            row["landedMinusFloor"] = None if row["after"] is None else round(row["after"] - start, 3)
            out("     floor at issue %.3f, landed %.3f from it" % (start, row["landedMinusFloor"] or 0.0))
            floor_rows.append(row)
        result["floor"] = floor_rows
        # a target inside the range that the cache cannot serve yet: the last half second
        pre5 = snapshot(player.ipc, player.pid, t0)
        if pre5["ranges"] and pre5["cacheEnd"] is not None:
            end = pre5["ranges"][0][1]
            result["edgeSeek"] = seek_and_judge(player, round(end - 0.5, 3), t0, out, "Q4 end-0.5 (inside, at the edge)",
                                                after=1.0, watch=3.0, mode="absolute")
            result["edgeSeek"]["endAtIssue"] = end
            pre6 = snapshot(player.ipc, player.pid, t0)
            end2 = pre6["ranges"][0][1] if pre6["ranges"] else end
            result["beyondSeek"] = seek_and_judge(player, round(end2 + 30.0, 3), t0, out, "Q4 end+30 (outside)",
                                                  after=1.0, watch=3.0, mode="absolute")
            result["beyondSeek"]["endAtIssue"] = end2
        result["final"] = snapshot(player.ipc, player.pid, t0)
        out("  final: %s" % fmt(result["final"]))
    except Exception as exc:
        result["failure"] = "%s: %s" % (exc.__class__.__name__, exc)
        out("  FAILED: %s" % result["failure"])
    finally:
        result["mpvExit"] = player.close()
    return result


# --- Pre-build measurements, section 12 ---------------------------------

def raw_state(ipc):
    state, _ = get(ipc, "demuxer-cache-state")
    return state


def fill_until_evicted(player, t0, out, cap, every=10.0):
    """Play until `seekable-ranges[0].start` leaves zero -- the stream start
    has been evicted, which is the plateau -- or `cap` passes. Returns the
    snapshots, the raw cache state at +30 s, the raw state at the stop and
    whether eviction was seen."""
    snaps, raw30, evicted = [], None, False
    until = time.monotonic() + cap
    while time.monotonic() < until:
        time.sleep(min(every, max(0.1, until - time.monotonic())))
        snap = snapshot(player.ipc, player.pid, t0)
        snaps.append(snap)
        out("  fill %s" % fmt(snap))
        if raw30 is None and snap["t"] >= 30.0:
            raw30 = raw_state(player.ipc)
        if snap["ranges"] and snap["ranges"][0][0] > 0.5:
            evicted = True
            break
    return snaps, raw30, raw_state(player.ipc), evicted


def field_table(state):
    rows = verdict.enumerate_fields(state)
    return {"fields": [{"path": p, "type": k, "sample": v} for p, k, v in rows],
            "strings": verdict.string_fields(state)}


def m1_fields(args, channels, out):
    ch = channels[args.a]
    out("M1 demuxer-cache-state fields: %s (%s)" % (ch["name"], redact(ch["url"])))
    result = {"question": "m1", "channel": ch["id"], "name": ch["name"], "host": redact(ch["url"])}
    player = Player(args, 11, out)
    result["pid"] = player.pid
    try:
        t0, _ = player.play(ch)
        snaps, raw30, rawstop, evicted = fill_until_evicted(player, t0, out, args.m_cap)
        result["fill"] = snaps
        result["evicted"] = evicted
        result["at30"] = field_table(raw30)
        result["atStop"] = field_table(rawstop)
        result["atStopT"] = snaps[-1]["t"] if snaps else None
        # The raw replies too: the enumeration walks a list through its
        # first element, and the per-stream list has one entry per stream.
        result["raw"] = {"at30": raw30, "atStop": rawstop}
        for label, table in (("+30 s", result["at30"]), ("stop", result["atStop"])):
            out("  %s: %d leaves, string leaves: %s" % (label, len(table["fields"]), table["strings"]))
            for row in table["fields"]:
                out("    %-36s %-6s %s" % (row["path"], row["type"], row["sample"]))
    except Exception as exc:
        result["failure"] = "%s: %s" % (exc.__class__.__name__, exc)
        out("  FAILED: %s" % result["failure"])
    finally:
        result["mpvExit"] = player.close()
    return result


# The landed battery: deltas from the current position, clamped inside the
# range the way the helper will clamp (floor + 2, end - 0.5). Backwards
# first, because the player starts at the live edge with nothing ahead.
LANDED_DELTAS = [-10, -30, 10, -5, 5, -60, 30, -3, 3, -2, 2, -120, 60,
                 -10, -10, -10, 10, 10, -45, 45, -7, 7, -90, 20]
REFUSED_BELOW = [1, 2, 5, 10, 30, 60]
REFUSED_PAST = [1, 2, 5, 10, 30, 60]


def one_seek(player, target, out, label, expect, t0):
    """One absolute seek with the reads the helper will make: `time-pos`
    before, immediately after the reply, and 1 s later; then a drain so
    the log event, if any, has arrived."""
    ipc = player.ipc
    pre = snapshot(ipc, player.pid, t0)
    n0 = len(ipc.log_sink)
    before, _ = get(ipc, "time-pos")
    t_s = time.monotonic()
    _, error = command(ipc, "seek", str(round(target, 3)), "absolute")
    rtt = time.monotonic() - t_s
    after, _ = get(ipc, "time-pos")
    t_after = time.monotonic() - t_s
    rest = t_s + 1.0 - time.monotonic()
    if rest > 0:
        time.sleep(rest)
    later, _ = get(ipc, "time-pos")
    t_later = time.monotonic() - t_s
    time.sleep(0.3)
    get(ipc, "pause")                     # drains any event that followed
    lines = [e for e in ipc.log_sink[n0:] if e["cannotSeek"]]
    row = {"label": label, "expect": expect, "target": round(target, 3),
           "floor": pre["ranges"][0][0] if pre["ranges"] else None,
           "end": pre["ranges"][0][1] if pre["ranges"] else None,
           "before": before, "after": after, "later": later,
           "deltaAfter": verdict.achieved_seconds(after, before),
           "deltaLater": verdict.achieved_seconds(later, before),
           "error": error or "", "rttMs": round(rtt * 1000, 2),
           "afterReadAtMs": round(t_after * 1000, 1), "laterReadAtS": round(t_later, 3),
           "logLines": len(lines),
           "logLineAtMs": None if not lines else round((lines[0]["t"] - t_s) * 1000, 1)}
    out("  SEEK %-24s expect=%-8s target=%9.3f floor=%s end=%s before=%s after=%s (+%.1f ms) later=%s (+%.2f s) dAfter=%s dLater=%s log=%d" % (
        label, expect, target, row["floor"], row["end"],
        None if before is None else round(before, 3), None if after is None else round(after, 3), t_after * 1000,
        None if later is None else round(later, 3), t_later,
        None if row["deltaAfter"] is None else round(row["deltaAfter"], 3),
        None if row["deltaLater"] is None else round(row["deltaLater"], 3), len(lines)))
    return row


def m2_refusal(args, channels, out):
    ch = channels[args.a]
    out("M2 refusal detector: %s (%s)" % (ch["name"], redact(ch["url"])))
    result = {"question": "m2", "channel": ch["id"], "name": ch["name"], "host": redact(ch["url"])}
    player = Player(args, 20 + args.index, out)
    result["pid"] = player.pid
    player.ipc.log_sink = []
    _, sub_err = command(player.ipc, "request_log_messages", "error")
    result["logSubscribeError"] = sub_err or ""
    try:
        t0, _ = player.play(ch)
        snaps, raw30, rawstop, evicted = fill_until_evicted(player, t0, out, args.m_cap)
        result["fill"] = snaps
        result["evicted"] = evicted
        result["at30"] = field_table(raw30)
        result["atStop"] = field_table(rawstop)
        out("  evicted: %s at t=%s; string leaves at +30: %s, at stop: %s" % (
            evicted, snaps[-1]["t"] if snaps else None, result["at30"]["strings"], result["atStop"]["strings"]))
        rows = []
        for i, delta in enumerate(LANDED_DELTAS):
            pre = snapshot(player.ipc, player.pid, t0)
            if not pre["ranges"] or pre["pos"] is None:
                out("  no range, skipping landed %d" % i)
                continue
            floor, end = pre["ranges"][0]
            target = min(max(pre["pos"] + delta, floor + 2.0), end - 0.5)
            rows.append(one_seek(player, target, out, "landed %+d" % delta, "landed", t0))
        for n in REFUSED_BELOW:
            pre = snapshot(player.ipc, player.pid, t0)
            if not pre["ranges"]:
                continue
            floor = pre["ranges"][0][0]
            expect = "refused" if floor > 0.5 else "clampedToStart"
            rows.append(one_seek(player, floor - n, out, "below floor -%d" % n, expect, t0))
        for n in REFUSED_PAST:
            pre = snapshot(player.ipc, player.pid, t0)
            if not pre["ranges"]:
                continue
            end = pre["ranges"][0][1]
            rows.append(one_seek(player, end + n, out, "past end +%d" % n, "refused", t0))
        result["seeks"] = rows
        landed = [r for r in rows if r["expect"] == "landed"]
        refused = [r for r in rows if r["expect"] == "refused"]
        result["landedAfter"] = verdict.distribution(verdict.abs_deltas(landed))
        result["landedLater"] = verdict.distribution(verdict.abs_deltas(landed, key_after="later"))
        result["refusedAfter"] = verdict.distribution(verdict.abs_deltas(refused))
        result["refusedLater"] = verdict.distribution(verdict.abs_deltas(refused, key_after="later"))
        result["refusedLogLines"] = sum(1 for r in refused if r["logLines"])
        result["landedLogLines"] = sum(1 for r in landed if r["logLines"])
        try:
            with open(player.log_path, "rb") as handle:
                result["cannotSeekLinesInLogFile"] = handle.read().count(b"Cannot seek in this stream")
        except OSError:
            result["cannotSeekLinesInLogFile"] = None
        out("  landed n=%d |dAfter| %s |dLater| %s; refused n=%d |dAfter| %s |dLater| %s; log lines on refused %d of %d, on landed %d; in file %s" % (
            len(landed), result["landedAfter"], result["landedLater"], len(refused),
            result["refusedAfter"], result["refusedLater"], result["refusedLogLines"], len(refused),
            result["landedLogLines"], result["cannotSeekLinesInLogFile"]))
    except Exception as exc:
        result["failure"] = "%s: %s" % (exc.__class__.__name__, exc)
        out("  FAILED: %s" % result["failure"])
    finally:
        result["mpvExit"] = player.close()
    return result


def hyprctl_json(*words):
    """`hyprctl -j <words>`, argv only, parsed; None on any failure."""
    import subprocess
    try:
        raw = subprocess.run(["hyprctl", "-j"] + list(words), capture_output=True, timeout=5).stdout
        return json.loads(raw.decode("utf-8", "replace"))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def hyprctl(*words):
    import subprocess
    try:
        return subprocess.run(["hyprctl"] + list(words), capture_output=True, timeout=5).stdout.decode("utf-8", "replace").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def window_of(pid):
    for client in hyprctl_json("clients") or []:
        if client.get("pid") == pid:
            return client
    return None


def shot_series(ipc, out, label, path_fmt, geometry, count, pre=None):
    """`pre` is issued, then `count` back-to-back grim captures of
    `geometry`; each row records when the capture command returned
    (an upper bound on the capture instant) relative to the command."""
    t = time.monotonic()
    err = ""
    if pre is not None:
        _, err = command(ipc, *pre)
    rows = []
    for i in range(count):
        ok, ms = grim_region(path_fmt % i, geometry)
        rows.append({"shot": path_fmt % i, "ok": ok, "doneAtMs": round((time.monotonic() - t) * 1000, 1), "grimMs": ms})
    out("  %s: %s" % (label, ", ".join("#%d at %.0f ms" % (i, r["doneAtMs"]) for i, r in enumerate(rows))))
    return {"commandError": err or "", "shots": rows}


def grim_region(path, geometry, scale=None):
    import subprocess
    argv = ["grim"]
    if scale:
        argv += ["-s", str(scale)]
    if geometry:
        argv += ["-g", geometry]
    argv.append(path)
    t = time.monotonic()
    try:
        ok = subprocess.run(argv, capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    return ok, round((time.monotonic() - t) * 1000, 1)


def bar_layers():
    found = []
    for mon, data in (hyprctl_json("layers") or {}).items():
        for lvl, entries in (data.get("levels") or {}).items():
            for entry in entries:
                if "bar" in str(entry.get("namespace") or ""):
                    found.append({"monitor": mon, "level": lvl, "namespace": entry.get("namespace"),
                                  "x": entry.get("x"), "y": entry.get("y"), "w": entry.get("w"), "h": entry.get("h")})
    return found


def m3_osd(args, channels, out):
    ch = channels[args.a]
    out("M3 show-text on a real window: %s (%s)" % (ch["name"], redact(ch["url"])))
    result = {"question": "m3", "channel": ch["id"], "name": ch["name"], "host": redact(ch["url"])}
    shots = os.path.join(args.scratch, "shots")
    os.makedirs(shots, exist_ok=True)
    active_before = (hyprctl_json("activewindow") or {}).get("address")
    result["activeBefore"] = active_before
    result["barLayersBefore"] = bar_layers()
    player = Player(args, 30, out, windowed=True)
    result["pid"] = player.pid
    fullscreen_on = False
    addr = None
    try:
        t0, _ = player.play(ch)
        time.sleep(3.0)
        win = None
        deadline = time.monotonic() + 10.0
        while win is None and time.monotonic() < deadline:
            win = window_of(player.pid)
            if win is None:
                time.sleep(0.25)
        if win is None:
            raise RuntimeError("no Hyprland client for pid %d within 10 s" % player.pid)
        addr = win.get("address")
        at, size = win.get("at"), win.get("size")
        geometry = "%d,%d %dx%d" % (at[0], at[1], size[0], size[1])
        strip = "%d,%d %dx%d" % (at[0], at[1], size[0], 70)
        result["window"] = {"address": addr, "class": win.get("class"), "at": at, "size": size,
                            "floating": win.get("floating"), "fullscreen": win.get("fullscreen"),
                            "workspace": (win.get("workspace") or {}).get("id")}
        out("  window %s class=%s at=%s size=%s floating=%s" % (addr, win.get("class"), at, size, win.get("floating")))
        level, _ = get(player.ipc, "osd-level")
        result["osdLevel"] = level
        result["baseline"] = shot_series(player.ipc, out, "(0) baseline strip, no command",
                                         os.path.join(shots, "m3-0-base-%d.png"), strip, 1)
        # (a) show-text windowed: when does the line appear?
        result["a"] = shot_series(player.ipc, out, "(a) show-text windowed, top strip",
                                  os.path.join(shots, "m3-a-%d.png"), strip, 6,
                                  pre=("show-text", "-1:32 behind live", 3000))
        time.sleep(3.5)
        # (c) an IPC seek, windowed, with no show-text active: mpv's own OSD?
        before, _ = get(player.ipc, "time-pos")
        t = time.monotonic()
        _, err = command(player.ipc, "seek", "-5", "relative")
        rows = []
        for i in range(3):
            ok, ms = grim_region(os.path.join(shots, "m3-c-%d.png" % i), geometry, scale=0.5)
            rows.append({"ok": ok, "doneAtMs": round((time.monotonic() - t) * 1000, 1)})
        after, _ = get(player.ipc, "time-pos")
        result["c"] = {"seekError": err or "", "before": before, "after": after, "shots": rows}
        out("  (c) IPC seek -5 windowed: %s -> %s; shots at %s ms" % (before, after, [r["doneAtMs"] for r in rows]))
        time.sleep(2.0)
        # (b) fullscreen by address, at most 3 s
        # Hyprland 0.56 under a Lua config provider: `hyprctl dispatch X`
        # is `return hl.dispatch(X)`, so the legacy `fullscreen 0` spelling
        # is a syntax error (Model.js G-1). The window is named by address
        # in a table, the shape pipExpression() builds.
        hyprctl("dispatch", 'hl.dsp.focus({ window = "address:%s" })' % addr)
        time.sleep(0.2)
        attempts = []
        fs_expr = 'hl.dsp.window.fullscreen({ window = "address:%s" })' % addr
        for form in (fs_expr,
                     'hl.dsp.window.fullscreen({ window = "address:%s", mode = 0 })' % addr,
                     'hl.dsp.window.fullscreen_state({ window = "address:%s", internal = 2, client = -1 })' % addr):
            reply = hyprctl("dispatch", form)
            time.sleep(0.5)
            w = window_of(player.pid) or {}
            attempts.append({"form": form, "reply": reply, "fullscreen": w.get("fullscreen"),
                             "fullscreenClient": w.get("fullscreenClient"), "size": w.get("size")})
            out("  fullscreen attempt %s -> %r, fullscreen=%s client=%s size=%s" % (
                form, reply, w.get("fullscreen"), w.get("fullscreenClient"), w.get("size")))
            if w.get("fullscreen"):
                fullscreen_on = True
                fs_expr = form
                break
        result["fullscreenAttempts"] = attempts
        t_fs = time.monotonic()
        if fullscreen_on:
            w = window_of(player.pid) or {}
            result["b"] = {"fullscreen": w.get("fullscreen"), "at": w.get("at"), "size": w.get("size"),
                           "barLayers": bar_layers(), "activeWindow": (hyprctl_json("activewindow") or {}).get("address")}
            top = "0,0 %dx70" % (w.get("size") or [1366])[0]
            result["b"]["text"] = shot_series(player.ipc, out, "(b) show-text fullscreen, output top strip",
                                              os.path.join(shots, "m3-b-%d.png"), top, 4,
                                              pre=("show-text", "-1:32 behind live", 3000))
            ok, ms = grim_region(os.path.join(shots, "m3-b-output.png"), None, scale=0.4)
            result["b"]["outputShot"] = ok
            out("  (b) fullscreen: bar layers %s; output shot %s" % (result["b"]["barLayers"], ok))
        elapsed = time.monotonic() - t_fs
        if fullscreen_on:
            if elapsed < 2.0:
                time.sleep(2.0 - elapsed)
            hyprctl("dispatch", fs_expr)            # the verb toggles
            fullscreen_on = False
            result["fullscreenHeldS"] = round(time.monotonic() - t_fs, 2)
            time.sleep(0.5)
            w = window_of(player.pid) or {}
            result["afterRestore"] = {"fullscreen": w.get("fullscreen"), "size": w.get("size")}
            out("  fullscreen held %.2f s, restored fullscreen=%s size=%s" % (result["fullscreenHeldS"], w.get("fullscreen"), w.get("size")))
    except Exception as exc:
        result["failure"] = "%s: %s" % (exc.__class__.__name__, exc)
        out("  FAILED: %s" % result["failure"])
    finally:
        if fullscreen_on and addr:
            hyprctl("dispatch", 'hl.dsp.window.fullscreen({ window = "address:%s" })' % addr)
        result["mpvExit"] = player.close()
        if active_before:
            hyprctl("dispatch", 'hl.dsp.focus({ window = "address:%s" })' % active_before)
        result["activeAfter"] = (hyprctl_json("activewindow") or {}).get("address")
        result["barLayersAfter"] = bar_layers()
        out("  focus restored to %s (was %s)" % (result["activeAfter"], active_before))
    return result


def m4_zero_point(args, channels, out):
    ids = [i for i in (args.a, args.b, args.c) if i]
    out("M4 zero-point error on %d channels" % len(ids))
    result = {"question": "m4", "channels": []}
    player = Player(args, 40, out)
    result["pid"] = player.pid
    try:
        for cid in ids:
            ch = channels[cid]
            out("  %s (%s)" % (ch["name"], redact(ch["url"])))
            row = {"channel": cid, "name": ch["name"], "host": redact(ch["url"])}
            _, error, rtt, t_z = zap(player.ipc, ch, os.getpid())
            row["loadfileError"] = error or ""
            wall0 = pos0 = None
            polls = 0
            deadline = t_z + args.start_timeout
            while time.monotonic() < deadline:
                pos, _ = get(player.ipc, "time-pos")
                polls += 1
                if isinstance(pos, (int, float)):
                    wall0, pos0 = time.monotonic(), float(pos)
                    break
                time.sleep(0.05)
            row.update({"polls": polls, "firstPosAfterZapS": None if wall0 is None else round(wall0 - t_z, 3), "pos0": pos0})
            if wall0 is None:
                row["failure"] = "no time-pos within %.0f s" % args.start_timeout
                result["channels"].append(row)
                out("    FAILED: %s" % row["failure"])
                continue
            ticks = []
            pfc_count = 0
            for i in range(1, args.m4_seconds + 1):
                target = wall0 + i
                rest = target - time.monotonic()
                if rest > 0:
                    time.sleep(rest)
                pos, _ = get(player.ipc, "time-pos")
                wall = time.monotonic()
                pfc, _ = get(player.ipc, "paused-for-cache")
                pfc_count += 1 if pfc else 0
                err = verdict.zero_point_error(wall0, pos0, wall, pos)
                ticks.append({"i": i, "wall": round(wall - wall0, 3), "pos": pos,
                              "error": None if err is None else round(err, 3), "pfc": pfc})
                if i in (1, 5, 10, 30, 60) or i == args.m4_seconds:
                    out("    +%2d s pos=%s error=%s pfc=%s" % (i, None if pos is None else round(pos, 3),
                                                            None if err is None else round(err, 3), pfc))
            errs = [t["error"] for t in ticks if t["error"] is not None]
            tick5 = ticks[4] if len(ticks) >= 5 else None
            final = ticks[-1]
            row.update({"ticks": ticks, "errorAtEnd": final["error"],
                        "errorMin": min(errs) if errs else None, "errorMax": max(errs) if errs else None,
                        "errorAtEndFromTick5": None if not tick5 or tick5["error"] is None or final["error"] is None
                        else round(final["error"] - tick5["error"], 3),
                        "pausedForCacheTicks": pfc_count,
                        "stateAtEnd": snapshot(player.ipc, player.pid, wall0)})
            br, _ = get(player.ipc, "video-bitrate")
            ab, _ = get(player.ipc, "audio-bitrate")
            row["bitrateBps"] = ((br or 0) + (ab or 0)) or None
            out("    error at +%d s: %s (min %s max %s); from a tick-5 zero point: %s; pfc ticks %d; bitrate %s" % (
                args.m4_seconds, row["errorAtEnd"], row["errorMin"], row["errorMax"],
                row["errorAtEndFromTick5"], pfc_count, row["bitrateBps"]))
            result["channels"].append(row)
    except Exception as exc:
        result["failure"] = "%s: %s" % (exc.__class__.__name__, exc)
        out("  FAILED: %s" % result["failure"])
    finally:
        result["mpvExit"] = player.close()
    return result


QUESTIONS = {"q1": q1_zap, "q2a": q2a_pause_full, "q2b": q2b_pause_fresh,
             "q2cd": q2cd_rewind_pause, "q34": q34_watchdog_floor,
             "m1": m1_fields, "m2": m2_refusal, "m3": m3_osd, "m4": m4_zero_point}


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("question", choices=sorted(QUESTIONS))
    parser.add_argument("--channels", required=True, help="a source channels.json, read only")
    parser.add_argument("--a", required=True, help="channel id for A / the single channel")
    parser.add_argument("--b", default="", help="channel id for B (q1, m4)")
    parser.add_argument("--c", default="", help="channel id for C (m4)")
    parser.add_argument("--index", type=int, default=0, help="socket index offset for concurrent m2 runs")
    parser.add_argument("--m-cap", type=float, default=330.0, help="m1/m2: seconds to wait for eviction")
    parser.add_argument("--m4-seconds", type=int, default=60)
    parser.add_argument("--scratch", required=True)
    parser.add_argument("--sock-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--q1-soak", type=float, default=90.0)
    parser.add_argument("--q1-after", type=float, default=31.0)
    parser.add_argument("--q2-soak", type=float, default=240.0)
    parser.add_argument("--q2-cap", type=float, default=420.0)
    parser.add_argument("--q3-cap", type=float, default=420.0)
    parser.add_argument("--connect-timeout", type=float, default=10.0)
    parser.add_argument("--start-timeout", type=float, default=25.0)
    parser.add_argument("--ipc-timeout", type=float, default=6.0)
    args = parser.parse_args(argv)

    os.makedirs(args.scratch, exist_ok=True)
    os.makedirs(args.sock_dir, mode=0o700, exist_ok=True)
    if len(os.path.join(args.sock_dir, "d00").encode("utf-8")) > 100:
        sys.stderr.write("sock-dir too long for an AF_UNIX path\n")
        return 2
    with open(args.channels, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    rows = document.get("channels") if isinstance(document, dict) else document
    channels = {}
    for row in rows:
        if row.get("id") in (args.a, args.b, args.c):
            channels[row["id"]] = {"id": row["id"], "name": row.get("name") or "", "url": row.get("url") or ""}
    if args.a not in channels or (args.question == "q1" and args.b not in channels):
        sys.stderr.write("channel id not in the list\n")
        return 2

    def out(text):
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    # A `timeout` kill must still reach the finally that reaps mpv by pid.
    def on_term(signum, frame):
        raise RuntimeError("terminated by signal %d" % signum)
    signal.signal(signal.SIGTERM, on_term)
    started = time.monotonic()
    result = QUESTIONS[args.question](args, channels, out)
    result["elapsedS"] = round(time.monotonic() - started, 1)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=1)
    out("done %s in %.0f s -> %s" % (args.question, result["elapsedS"], args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
