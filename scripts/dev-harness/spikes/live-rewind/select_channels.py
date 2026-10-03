#!/usr/bin/env python3
"""Pick a host- and group-diverse sample out of a source channels.json.

Deterministic: no RNG, no clock. Round-robin over groups ordered by size
(descending, name as tie-break); inside a group the channels are taken in
name order, and a channel is skipped when its URL host has already been
taken. Host diversity is the hard constraint because the question under
measurement -- does this stream let mpv seek backwards -- is a property of
the origin server and its packaging, not of the channel's genre.

Reads nothing but the file named on argv. Writes JSON to stdout: a list of
{id, name, group, host, url}. The URL is in the machine-readable output
because the harness has to play it; every human-facing sink in this spike
prints scheme and host only (CLAUDE.md requirement 5).
"""

import argparse
import json
import sys
from urllib.parse import urlparse


def host_of(url):
    """Network location of a URL, or "" when it has none."""
    try:
        return urlparse(url or "").netloc or ""
    except ValueError:
        return ""


def redact(url):
    """scheme://host, the only form of a playlist URL that may be printed."""
    try:
        parts = urlparse(url or "")
    except ValueError:
        return "(unparseable)"
    if not parts.scheme or not parts.netloc:
        return "(no host)"
    return "%s://%s" % (parts.scheme, parts.netloc)


def group_order(channels):
    """Group names, biggest first, name as the tie-break."""
    sizes = {}
    for channel in channels:
        name = channel.get("group") or ""
        sizes[name] = sizes.get(name, 0) + 1
    return [name for name in sorted(sizes, key=lambda g: (-sizes[g], g))]


def pick(channels, want, per_group_cap=2):
    """Round-robin over groups, at most one channel per URL host.

    `per_group_cap` bounds how many rounds a single group can win, so one
    enormous group (this list has 263 in General) cannot dominate a sample
    that is supposed to say something about the list as a whole.
    """
    by_group = {}
    for channel in channels:
        if not host_of(channel.get("url")):
            continue
        by_group.setdefault(channel.get("group") or "", []).append(channel)
    for name in by_group:
        by_group[name].sort(key=lambda c: (c.get("name") or "", c.get("id") or ""))

    order = group_order(channels)
    taken, hosts, cursor, rounds = [], set(), {}, {}
    progressed = True
    while len(taken) < want and progressed:
        progressed = False
        for name in order:
            if len(taken) >= want:
                break
            if rounds.get(name, 0) >= per_group_cap:
                continue
            pool = by_group.get(name) or []
            index = cursor.get(name, 0)
            while index < len(pool):
                channel = pool[index]
                index += 1
                host = host_of(channel.get("url"))
                if host in hosts:
                    continue
                hosts.add(host)
                rounds[name] = rounds.get(name, 0) + 1
                taken.append({
                    "id": channel.get("id") or "",
                    "name": channel.get("name") or "",
                    "group": name,
                    "host": host,
                    "url": channel.get("url") or "",
                })
                progressed = True
                break
            cursor[name] = index
    return taken


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("channels", help="path to a source channels.json")
    parser.add_argument("--want", type=int, default=32)
    parser.add_argument("--per-group-cap", type=int, default=2)
    args = parser.parse_args(argv)

    with open(args.channels, "r", encoding="utf-8") as handle:
        document = json.load(handle)
    channels = document.get("channels") if isinstance(document, dict) else document
    if not isinstance(channels, list):
        sys.stderr.write("no channels array\n")
        return 2
    chosen = pick(channels, args.want, args.per_group_cap)
    json.dump(chosen, sys.stdout, indent=1)
    sys.stdout.write("\n")
    sys.stderr.write("picked %d of %d, %d groups, %d hosts\n" % (
        len(chosen), len(channels),
        len({c["group"] for c in chosen}), len({c["host"] for c in chosen})))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
