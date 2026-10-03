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
