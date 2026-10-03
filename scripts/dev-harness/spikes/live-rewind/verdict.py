#!/usr/bin/env python3
"""The judgements this spike makes, separated from the thing it measures.

Nothing here opens a socket or starts a process, so every rule the spike
applies to a reading can be run against a hand-written reading and seen to
go red when the rule is broken. The harness imports these; it does not
re-implement them (CLAUDE.md requirement 12 in spirit: logic a test cannot
reach is logic nobody has checked).
"""

MIN_BACKWARD_MOVE_S = 1.0     # below this the position did not move at all
MIN_RESUME_ADVANCE_S = 0.5    # below this playback did not continue


def back_window_seconds(limit_bytes, bitrate_bits_per_s):
    """How many seconds of history a byte-capped back buffer can hold.

    mpv caps the back buffer in BYTES (--demuxer-max-back-bytes), so the
    window a user would experience is bytes over bitrate and is therefore
    a different number on every channel. None when either input is absent
    or non-positive, because a window of zero and an unknown window are
    not the same answer.
    """
    try:
        limit = float(limit_bytes)
        rate = float(bitrate_bits_per_s)
    except (TypeError, ValueError):
        return None
    if limit <= 0 or rate <= 0:
        return None
    return limit * 8.0 / rate


def seekable_range_span(cache_state):
    """Widest seekable range mpv reports in demuxer-cache-state, in seconds.

    This is the property that decides a cache seek: mpv publishes the
    ranges it can actually serve. None when the key is absent (an older
    reading, or a demuxer that publishes nothing), 0.0 when the key is
    present and empty -- again, absent and empty are different answers.
    """
    if not isinstance(cache_state, dict):
        return None
    ranges = cache_state.get("seekable-ranges")
    if ranges is None:
        return None
    if not isinstance(ranges, list):
        return None
    widest = 0.0
    for entry in ranges:
        if not isinstance(entry, dict):
            continue
        try:
            start = float(entry.get("start"))
            end = float(entry.get("end"))
        except (TypeError, ValueError):
            continue
        if end > start:
            widest = max(widest, end - start)
    return widest


def seek_verdict(before, after, later, requested_delta):
    """Did a backwards seek work?

    `before` is time-pos before the seek, `after` straight after it,
    `later` a second reading taken after letting it play on. A property
    that says seekable and a seek that works are two different facts, so
    this judges only the three numbers.

    Returns one of:
      lost      -- the player stopped answering
      refused   -- the position did not move backwards
      stalled   -- it moved back but playback did not continue
      rewound   -- it moved back and kept playing
    """
    if before is None or after is None:
        return "lost"
    moved_back = float(before) - float(after)
    if moved_back < MIN_BACKWARD_MOVE_S:
        return "refused"
    if later is None:
        return "stalled"
    if float(later) - float(after) < MIN_RESUME_ADVANCE_S:
        return "stalled"
    return "rewound"


def achieved_seconds(before, after):
    """How far back the position actually went, or None when unknown."""
    if before is None or after is None:
        return None
    return float(before) - float(after)


def back_span_seconds(cache_state):
    """Seconds of HISTORY behind the read position, from demuxer-cache-state.

    Not the same number as seekable_range_span: a range covers the forward
    cache too, and for HLS the forward cache is whole segments ahead of the
    reader, so the range is wider than anything a rewind could use. What
    bounds a backwards seek is reader-pts minus the start of the range the
    reader is inside. None when the reading does not carry both.
    """
    if not isinstance(cache_state, dict):
        return None
    try:
        reader = float(cache_state.get("reader-pts"))
    except (TypeError, ValueError):
        return None
    ranges = cache_state.get("seekable-ranges")
    if not isinstance(ranges, list):
        return None
    best = None
    for entry in ranges:
        if not isinstance(entry, dict):
            continue
        try:
            start = float(entry.get("start"))
            end = float(entry.get("end"))
        except (TypeError, ValueError):
            continue
        if start <= reader <= end:
            span = reader - start
            best = span if best is None else max(best, span)
    return best


def property_claim(seekable, partially_seekable, range_span):
    """What mpv's own properties CLAIM about rewind, before any seek.

    The point of the spike: M2-11 read `seekable` alone and concluded
    rewind was dead. `partially-seekable` is true exactly when the stream
    is seekable only inside the cache, which is the case that matters.
    """
    if seekable is True:
        return "seekable"
    if partially_seekable is True:
        return "partially-seekable"
    if range_span is not None and range_span > 0:
        return "cache-range-only"
    return "unseekable"


def summarise(rows):
    """Counts over a list of measured rows, for the document's verdict line."""
    counts = {
        "measured": 0, "played": 0, "failed": 0,
        "seekable": 0, "partially-seekable": 0,
        "cache-range-only": 0, "unseekable": 0,
        "rewound": 0, "stalled": 0, "refused": 0, "lost": 0,
    }
    for row in rows:
        counts["measured"] += 1
        if row.get("played"):
            counts["played"] += 1
        else:
            counts["failed"] += 1
            continue
        claim = row.get("claim")
        if claim in counts:
            counts[claim] += 1
        seek = row.get("seek")
        if seek in counts:
            counts[seek] += 1
    return counts


# --- Second pass, 2026-10-03 (design_pass.py) --------------------------------

FLOOR_TOLERANCE_S = 1.5       # a landing this close to the target counts as hitting it
PLATEAU_GROWTH_S = 2.0        # back buffer growing less than this over two samples is flat
CONTINUED_PLAY_S = 3.5        # an ignored seek read up to this much later just kept playing


def behind_live_seconds(cache_state, time_pos):
    """Seconds between the play head and the newest cached packet:
    cache-end minus time-pos. This is the number a UI would show as
    "behind live" on a 1 s tick. None when either side is missing. Note
    that at the live edge it is NOT zero: HLS keeps whole segments ahead of
    the reader, so the figure a UI shows has to subtract the lead it saw
    before the first rewind.
    """
    if not isinstance(cache_state, dict):
        return None
    try:
        end = float(cache_state.get("cache-end"))
        pos = float(time_pos)
    except (TypeError, ValueError):
        return None
    return end - pos


def history_survives(old_ranges, new_ranges, seconds_since_zap, lead_s=30.0):
    """Does the OLD channel's history still show after a loadfile?

    Not an overlap test: measured 2026-10-03, every HLS loadfile restarts the
    demuxer timeline at 0, so the old [0, 106] and a fresh [0, 1.99] overlap
    by construction and say nothing. What a fresh demuxer CANNOT produce is a
    range wider than the seconds it has been running plus the forward lead
    it fetches ahead (lead_s, generous). True when any new range is wider
    than that; False otherwise; None when a side is unknown.
    """
    if not isinstance(old_ranges, list) or not isinstance(new_ranges, list):
        return None
    try:
        budget = float(seconds_since_zap) + float(lead_s)
    except (TypeError, ValueError):
        return None
    for new in new_ranges:
        try:
            if float(new[1]) - float(new[0]) > budget:
                return True
        except (TypeError, ValueError, IndexError):
            continue
    return False


def resumed_from(paused_at, at2, at5):
    """After an unpause, did playback continue from the paused position?
    True when the +2 s reading is within 1.5 s of where it was paused and
    the +5 s reading has advanced past it; False when it jumped (to live,
    or anywhere else) or did not move; None when a reading is missing.
    """
    if paused_at is None or at2 is None or at5 is None:
        return None
    near = abs(float(at2) - float(paused_at)) <= 2.0 + FLOOR_TOLERANCE_S
    moving = float(at5) - float(at2) >= MIN_RESUME_ADVANCE_S
    return bool(near and moving)


def floor_seek_verdict(target, before, after, later, floor):
    """An ABSOLUTE seek near the floor of the seekable range.

      refused  -- the position just carried on playing: it neither moved
                  back nor jumped forward by more than CONTINUED_PLAY_S,
                  which is what an ignored seek looks like when the second
                  reading is taken a second or three later (measured
                  2026-10-03: a seek to start-1 answered "success" and the
                  position read before+1.0 one second later)
      clamped  -- the target was below the floor and it came to rest at the
                  floor; checked BEFORE landed because a target one second
                  under the floor is within tolerance of both
      landed   -- came to rest within FLOOR_TOLERANCE_S of the target
      stalled  -- moved but did not play on
      elsewhere-- moved to somewhere that is none of the above
    """
    if before is None or after is None:
        return "lost"
    delta = float(after) - float(before)
    if -MIN_BACKWARD_MOVE_S < delta <= CONTINUED_PLAY_S:
        return "refused"
    if later is None or float(later) - float(after) < MIN_RESUME_ADVANCE_S:
        return "stalled"
    if floor is not None and float(target) < float(floor) and abs(float(after) - float(floor)) <= FLOOR_TOLERANCE_S:
        return "clamped"
    if abs(float(after) - float(target)) <= FLOOR_TOLERANCE_S:
        return "landed"
    return "elsewhere"


def at_plateau(snapshots, cap_bytes):
    """Has the back buffer stopped growing? True once the cache total is
    within 3 per cent of the cap AND the back span grew less than
    PLATEAU_GROWTH_S across the last two samples. Needs three samples."""
    if len(snapshots) < 3:
        return False
    a, b, c = snapshots[-3], snapshots[-2], snapshots[-1]
    try:
        total = float(c.get("totalBytes"))
        spans = [float(a.get("backSpan")), float(b.get("backSpan")), float(c.get("backSpan"))]
    except (TypeError, ValueError):
        return False
    if total < 0.97 * float(cap_bytes):
        return False
    return (spans[2] - spans[0]) < PLATEAU_GROWTH_S


def tick_rate(pairs):
    """Median and worst per-tick rate of time-pos against the wall clock
    over (wall_s, pos) pairs: {"median": r, "min": r, "max": r, "ticks": n}.
    A player advancing at 1 s/s reads 1.0; a stall reads 0. None when fewer
    than two usable pairs."""
    rates = []
    last = None
    for wall, pos in pairs:
        if not isinstance(pos, (int, float)) or not isinstance(wall, (int, float)):
            last = None
            continue
        if last is not None and wall > last[0]:
            rates.append((pos - last[1]) / (wall - last[0]))
        last = (wall, pos)
    if not rates:
        return None
    rates.sort()
    return {"median": round(rates[len(rates) // 2], 3), "min": round(rates[0], 3),
            "max": round(rates[-1], 3), "ticks": len(rates)}


def trend(values):
    """First, last and the sign of a series: {"first", "last", "delta",
    "direction"} where direction is "down", "up" or "flat" (within 2 s).
    None values are skipped; None when nothing is left."""
    kept = [float(v) for v in values if isinstance(v, (int, float))]
    if not kept:
        return None
    delta = kept[-1] - kept[0]
    if delta <= -2.0:
        direction = "down"
    elif delta >= 2.0:
        direction = "up"
    else:
        direction = "flat"
    return {"first": round(kept[0], 2), "last": round(kept[-1], 2), "delta": round(delta, 2),
            "direction": direction, "n": len(kept)}
