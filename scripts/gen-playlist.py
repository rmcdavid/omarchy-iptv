#!/usr/bin/env python3
"""gen-playlist.py -- deterministic synthetic M3U (+ optional XMLTV) generator.

Standard library only. Produces the large inputs for the performance gate
(docs/QA.md, section 4) without touching the network. Output is a pure
function of the flags, so two runs with the same flags are byte-identical
(verify with sha256sum). NEVER commit the generated files; write them to a
scratch directory.

Examples:
  scripts/gen-playlist.py --channels 10000 --groups 120 --seed 1 --epg-ids 0.6 --out /tmp/qa/gen-10k.m3u
  scripts/gen-playlist.py --channels 10000 --groups 120 --seed 1 --epg-ids 0.6 \\
      --out /tmp/qa/gen-10k.m3u --xmltv /tmp/qa/gen-10k.xml.gz --now 1789244100 --hours 24
  scripts/gen-playlist.py --profile realistic --channels 1500 --groups 26 --seed 7 --out - | head

Profiles:
  synthetic  tvg-id="chNNNNN.test" tvg-name tvg-chno group-title="Group NNN Word",
             URLs under http://stream.example.test/live/NNNNN.m3u8 (ASCII, compact)
  realistic  mimics the iptv-org attribute layout from docs/QA-ASSETS.md:
             tvg-id="CamelName.cc[@SD]" tvg-logo="https://logos.example.test/channels/<24hex>/colorLogoPNG.png"
             group-title="Category[;Category]" and names with "(720p)" / "[Not 24/7]" suffixes;
             hosts stay under the reserved .test TLD so nothing can be fetched by accident.
             No tvg-chno anywhere, like every iptv-org list (M2-03 1.5).

Numbering (--numbering, M2-03 ruling CN13):
  blocks  the default for --profile synthetic. One block per group, in group
          order, so numbers read like a provider's card: 100s, 200s, 1000s.
          Inside a block the numbers step by one with GAPS, a deterministic
          fraction become SUBCHANNELS (7, 7.1, 7.2) and at least one
          subchannel pair is guaranteed whatever the seed. An HD/SD twin
          keeps its parent's number, so duplicates are real. This is what the
          live pass wants: a dense 1..N run resembles no provider, and it
          never exercises a gap, a block boundary or a subchannel.
  dense   the pre-CN13 numbering, byte for byte: tvg-chno="<playlist index>".
  none    no tvg-chno at all (hasNumbers false). The default for --profile
          realistic.

The XMLTV (--xmltv) covers every channel that has a tvg-id, in contiguous
30/60/90/120-minute slots from --now minus --hours to --now plus --hours,
with per-channel UTC offsets (+0000, +0100, -0500, +0530, -0800) so the
timezone code path is exercised. A path ending in .gz is gzip-compressed
deterministically (no filename, mtime 0). Pass --now for a reproducible file;
the default is the current hour, which is what the live perf gate wants.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import os
import random
import sys
import time
from typing import IO

ADJECTIVES = [
    "Alpha", "Bright", "Cosmic", "Delta", "Echo", "Fusion", "Global", "Harbor",
    "Iron", "Jade", "Kinetic", "Lunar", "Metro", "Nova", "Orbit", "Prime",
    "Quantum", "Royal", "Solar", "Terra", "Ultra", "Vista", "Wave", "Xenon",
    "Yonder", "Zenith", "Amber", "Blue", "Crimson", "Dusk", "Ember", "Frost",
]
NOUNS = [
    "News", "Sports", "Movies", "Kids", "Music", "Cinema", "Nature", "Drama",
    "Comedy", "Docs", "Live", "Plus", "One", "Two", "Max", "World", "Local",
    "Classic", "Action", "Family", "Science", "Travel", "Food", "Arts",
    "History", "Weather", "Business", "Auto", "Outdoor", "Relax", "Series", "Shop",
]
QUALITY = ["", "", "", " HD", " HD", " 4K", " SD", " FHD"]
REAL_SUFFIX = ["", "", "", "", " (720p)", " (1080p)", " (480p)", " [Not 24/7]", " [Geo-blocked]"]
CATEGORIES = [
    "Animation", "Auto", "Business", "Classic", "Comedy", "Cooking", "Culture",
    "Documentary", "Education", "Entertainment", "Family", "General", "Kids",
    "Legislative", "Lifestyle", "Movies", "Music", "News", "Outdoor", "Relax",
    "Religious", "Series", "Science", "Shop", "Sports", "Travel", "Weather",
]
COUNTRIES = ["us", "uk", "ca", "de", "fr", "es", "it", "br", "mx", "in", "au", "pl", "nl", "se", "jp"]
OFFSETS = ["+0000", "+0100", "-0500", "+0530", "-0800"]
PROGRAMME_WORDS = [
    "Morning", "Evening", "Late", "Tonight", "Report", "Show", "Hour", "Live",
    "Special", "Replay", "Highlights", "Update", "Weekend", "Daily", "Talk",
    "Movie", "Match", "Concert", "Journal", "Magazine", "Story", "Files",
]
SLOT_MINUTES = [30, 30, 60, 60, 60, 90, 120]
# The largest major a channel number may have (M2-03 1.2). Stated in Model.js
# as MAX_CHNO_MAJOR and here, so tests/fixtures/chno-attrs.json holds the one
# value and tests/test_playlist.py and tests/Model.test.js both assert against
# it: a generator that emits 123456 would produce a fixture whose channels are
# displayed with no number and cannot be reached by digits, and the live pass
# would be testing the wrong thing without anything going red.
MAX_CHNO_MAJOR = 99999


def hex_id(rng: random.Random, length: int = 24) -> str:
    return "".join("0123456789abcdef"[rng.randrange(16)] for _ in range(length))


def pick(rng: random.Random, items: list[str]) -> str:
    return items[rng.randrange(len(items))]


def camel(name: str) -> str:
    return "".join(part for part in name.replace("-", " ").split() if part.isalnum())


def format_xmltv_time(epoch: int, offset: str) -> str:
    sign = 1 if offset[0] == "+" else -1
    shift = sign * (int(offset[1:3]) * 3600 + int(offset[3:5]) * 60)
    return time.strftime("%Y%m%d%H%M%S", time.gmtime(epoch + shift)) + " " + offset


def build_groups(rng: random.Random, count: int, profile: str) -> list[str]:
    groups: list[str] = []
    if profile == "realistic":
        for i in range(count):
            category = CATEGORIES[i % len(CATEGORIES)]
            if i < len(CATEGORIES):
                groups.append(category)
            else:
                groups.append("%s | %s" % (COUNTRIES[(i // len(CATEGORIES)) % len(COUNTRIES)].upper(), category))
    else:
        for i in range(count):
            groups.append("Group %03d %s" % (i + 1, pick(rng, NOUNS)))
    return groups


def generate(args: argparse.Namespace) -> tuple[list[dict[str, str]], list[str]]:
    rng = random.Random(args.seed)
    groups = build_groups(rng, max(1, args.groups), args.profile)
    channels: list[dict[str, str]] = []
    index = 0
    while len(channels) < args.channels:
        index += 1
        base_name = "%s %s" % (pick(rng, ADJECTIVES), pick(rng, NOUNS))
        group = groups[rng.randrange(len(groups))]
        if rng.random() < args.multi_group:
            extra = groups[rng.randrange(len(groups))]
            if extra != group:
                group = group + ";" + extra
        country = pick(rng, COUNTRIES)
        has_epg = rng.random() < args.epg_ids
        dead = rng.random() < args.dead
        headers = rng.random() < args.headers
        if args.profile == "realistic":
            name = base_name + pick(rng, REAL_SUFFIX)
            tvg_id = "%s.%s" % (camel(base_name), country) if has_epg else ""
            logo = "https://logos.example.test/channels/%s/colorLogoPNG.png" % hex_id(rng)
            url = "https://streams.example.test/plu-%s.m3u8" % hex_id(rng)
            tvg_name = ""
        else:
            name = "%s%s %04d" % (base_name, pick(rng, QUALITY), index)
            tvg_id = "ch%05d.test" % index if has_epg else ""
            logo = "http://logos.example.test/%05d.png" % index if rng.random() < 0.5 else ""
            url = "http://stream.example.test/live/%05d.m3u8" % index
            tvg_name = base_name
        if dead:
            url = "http://127.0.0.1:9/dead/%05d.ts" % index
        # `chno` is filled in by assign_numbers() after the whole list exists:
        # a block plan needs to know how many channels each group ended up
        # with, and `twin` is how it knows which rows must SHARE a number
        # rather than take one of their own (M2-03 CN13).
        entry = {"name": name, "tvgId": tvg_id, "tvgName": tvg_name, "logo": logo,
                 "group": group, "url": url, "chno": "", "index": index,
                 "twin": "", "headers": "1" if headers else ""}
        channels.append(entry)
        if tvg_id and rng.random() < args.dupes and len(channels) < args.channels:
            twin = dict(entry)
            twin["name"] = name + (" SD" if "HD" in name else " HD")
            twin["url"] = url.replace(".m3u8", "-alt.m3u8").replace(".ts", "-alt.ts")
            twin["twin"] = "1"
            channels.append(twin)
    return channels, groups


def block_size(per_group_max: int, group_count: int) -> int:
    """How far apart two groups' blocks sit.

    Wide enough for the busiest group plus its gaps, and narrow enough that
    the last block still fits under MAX_CHNO_MAJOR (99999, Model.js). A
    number the model refuses is worse than a small block: the channel would
    be displayed with no number and be unreachable by digits.
    """
    want = per_group_max * 2 + 10
    for size in (100, 1000, 10000):
        if want <= size and size * (group_count + 1) <= MAX_CHNO_MAJOR:
            return size
    for size in (10000, 1000, 100, 10):
        if size * (group_count + 1) <= MAX_CHNO_MAJOR:
            return size
    return 0                                    # more groups than the space has room for


def assign_numbers(channels: list[dict[str, str]], args: argparse.Namespace) -> dict[str, int]:
    """Write `chno` on every channel. Returns a stats dict for the summary line.

    M2-03 ruling CN13: the live pass wants numbering that looks like a
    provider's, not 1..N. Three things a dense run never produces, and each
    one is a code path in Model.js:
      - GAPS, so the prefix scan has to walk past a hole (1.5);
      - BLOCKS per group, so the numbers are four digits and out of playlist
        order, which is what makes `channelOrder: number` visibly different;
      - at least one SUBCHANNEL pair, so 7 / 7.1 / 7.2 and the "7 then 7."
        entry path are exercised (2.7).
    Twins keep their parent's number, so duplicates are real (CN9).
    """
    stats = {"numbered": 0, "gaps": 0, "subchannels": 0, "duplicates": 0, "block": 0, "highest": 0}
    if args.numbering == "none":
        return stats
    if args.numbering == "dense":
        for channel in channels:
            channel["chno"] = str(channel["index"])
            stats["numbered"] += 1
            stats["duplicates"] += 1 if channel["twin"] else 0
            stats["highest"] = max(stats["highest"], channel["index"])
        return stats

    rng = random.Random(args.seed + 7919)       # its own stream: the plan must not
                                                # depend on how many names were drawn
    order: list[str] = []
    members: dict[str, list[dict[str, str]]] = {}
    for channel in channels:
        if channel["twin"]:
            continue
        key = channel["group"].split(";")[0]
        if key not in members:
            members[key] = []
            order.append(key)
        members[key].append(channel)
    size = block_size(max(len(v) for v in members.values()), len(order))
    if size == 0:                               # no room for blocks: gaps only
        return assign_dense_with_gaps(channels, rng, args, stats)
    stats["block"] = size
    # At least one subchannel pair, whatever the seed and however small the
    # run: the first group with two channels in it gets one. A generator that
    # "usually" produces the case under test is not a fixture.
    forced = next((key for key in order if len(members[key]) >= 2), "")
    for position, key in enumerate(order):
        base = size * (position + 1)
        rows = members[key]
        # Slots left over after every channel has one: the gap budget. Spending
        # only what is left is what keeps a block from running into the next.
        budget = max(0, size - len(rows) - 1)
        number = base
        major = base
        for at, channel in enumerate(rows):
            sub = (key == forced and at == 1) or (at > 0 and rng.random() < args.subchannels)
            if sub:
                minor = 1
                previous = rows[at - 1]["chno"]
                if "." in previous:
                    major, minor = previous.split(".")[0], int(previous.split(".")[1]) + 1
                    major = int(major)
                channel["chno"] = "%d.%d" % (major, minor)
                stats["subchannels"] += 1
            else:
                if at > 0:
                    step = 1
                    if budget > 0 and rng.random() < args.chno_gap:
                        step = 1 + min(budget, 1 + rng.randrange(3))
                        budget -= step - 1
                        stats["gaps"] += 1
                    number += step
                major = number
                channel["chno"] = str(number)
            stats["highest"] = max(stats["highest"], major)
        stats["numbered"] += len(rows)
    for at, channel in enumerate(channels):
        if channel["twin"] and at > 0:
            channel["chno"] = channels[at - 1]["chno"]
            stats["numbered"] += 1
            stats["duplicates"] += 1
    return stats


def assign_dense_with_gaps(channels: list[dict[str, str]], rng: random.Random,
                           args: argparse.Namespace, stats: dict[str, int]) -> dict[str, int]:
    """The fallback for more groups than the number space has blocks for.

    Still not a dense 1..N run: the gaps stay, because they are the part that
    costs nothing and catches the prefix scan. Reached only above ~9000
    groups, which no asset in this project has.
    """
    number = 1
    for at, channel in enumerate(channels):
        if channel["twin"] and at > 0:
            channel["chno"] = channels[at - 1]["chno"]
            stats["duplicates"] += 1
        else:
            if number > 1 and rng.random() < args.chno_gap:
                number += 1 + rng.randrange(3)
                stats["gaps"] += 1
            if number > MAX_CHNO_MAJOR:
                break
            channel["chno"] = str(number)
            stats["highest"] = number
            number += 1
        stats["numbered"] += 1
    return stats


def write_m3u(handle: IO[str], channels: list[dict[str, str]], args: argparse.Namespace) -> None:
    nl = "\r\n" if args.crlf else "\n"
    if args.bom:
        handle.write("\ufeff")
    epg_hint = ' url-tvg="http://epg.example.test/guide.xml.gz"' if args.xmltv else ""
    handle.write("#EXTM3U" + epg_hint + nl)
    handle.write("# generated by scripts/gen-playlist.py (profile=%s channels=%d groups=%d seed=%d epg-ids=%s); do not commit%s"
                 % (args.profile, args.channels, args.groups, args.seed, args.epg_ids, nl))
    for channel in channels:
        attrs = []
        if channel["tvgId"]:
            attrs.append('tvg-id="%s"' % channel["tvgId"])
        if channel["tvgName"]:
            attrs.append('tvg-name="%s"' % channel["tvgName"])
        if channel["logo"]:
            attrs.append('tvg-logo="%s"' % channel["logo"])
        if channel["chno"]:
            attrs.append('tvg-chno="%s"' % channel["chno"])
        attrs.append('group-title="%s"' % channel["group"])
        handle.write("#EXTINF:-1 %s,%s%s" % (" ".join(attrs), channel["name"], nl))
        if channel["headers"]:
            handle.write("#EXTVLCOPT:http-user-agent=Mozilla/5.0 (X11; Linux x86_64) gen-playlist/1.0" + nl)
            handle.write("#EXTVLCOPT:http-referrer=https://ref.example.test/" + nl)
        handle.write(channel["url"] + nl)


def write_xmltv(handle: IO[str], channels: list[dict[str, str]], args: argparse.Namespace) -> int:
    rng = random.Random(args.seed + 1)
    seen: set[str] = set()
    start_window = args.now - args.hours * 3600
    end_window = args.now + args.hours * 3600
    handle.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    handle.write('<!DOCTYPE tv SYSTEM "xmltv.dtd">\n')
    handle.write('<tv generator-info-name="omarchy-iptv gen-playlist.py" source-info-name="synthetic">\n')
    ids: list[str] = []
    for channel in channels:
        tvg_id = channel["tvgId"]
        if not tvg_id or tvg_id in seen:
            continue
        seen.add(tvg_id)
        ids.append(tvg_id)
        handle.write('  <channel id="%s"><display-name>%s</display-name>' % (tvg_id, escape(channel["name"])))
        if channel["logo"]:
            handle.write('<icon src="%s"/>' % channel["logo"])
        handle.write('</channel>\n')
    programmes = 0
    for tvg_id in ids:
        offset = pick(rng, OFFSETS)
        # Slots start on the half hour before the window so "now" is always inside a programme.
        at = start_window - (start_window % 1800)
        while at < end_window:
            length = SLOT_MINUTES[rng.randrange(len(SLOT_MINUTES))] * 60
            stop = at + length
            title = "%s %s" % (pick(rng, PROGRAMME_WORDS), pick(rng, PROGRAMME_WORDS))
            handle.write('  <programme start="%s" stop="%s" channel="%s"><title>%s</title>'
                         % (format_xmltv_time(at, offset), format_xmltv_time(stop, offset), tvg_id, escape(title)))
            if rng.random() < 0.5:
                handle.write('<desc>%s episode %d.</desc>' % (escape(title), rng.randrange(1, 40)))
            handle.write('</programme>\n')
            programmes += 1
            at = stop
    handle.write('</tv>\n')
    return programmes


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def write_out(path: str, text: str) -> int:
    data = text.encode("utf-8")
    if path == "-":
        sys.stdout.write(text)
        sys.stdout.flush()
        return len(data)
    if path.endswith(".gz"):
        buf = io.BytesIO()
        with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=6) as gz:
            gz.write(data)
        data = buf.getvalue()
    # C5: a plain `open(path, "wb")` leaves a TRUNCATED file behind when the
    # generation is interrupted, and the scenario that consumes it regenerates
    # only when the file is ABSENT - so every later run reused the truncation.
    # Write beside it and rename: a reader sees the old file or the new one.
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return len(data)


def sha256_of(path: str) -> str:
    if path == "-":
        return "-"
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gen-playlist.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--channels", type=int, default=10000, help="number of #EXTINF entries (default 10000)")
    parser.add_argument("--groups", type=int, default=120, help="number of distinct group-title values (default 120)")
    parser.add_argument("--seed", type=int, default=1, help="PRNG seed; same flags + seed = identical bytes (default 1)")
    parser.add_argument("--epg-ids", type=float, default=0.6, help="fraction of channels that get a tvg-id (default 0.6)")
    parser.add_argument("--out", required=True, help="M3U output path, or - for stdout")
    parser.add_argument("--xmltv", default="", help="also write an XMLTV file covering every tvg-id (.gz suffix = gzip)")
    parser.add_argument("--profile", choices=["synthetic", "realistic"], default="synthetic")
    parser.add_argument("--now", type=int, default=0, help="epoch seconds the EPG window is centred on (default: current hour)")
    parser.add_argument("--hours", type=int, default=12, help="EPG window half-width in hours (default 12)")
    parser.add_argument("--multi-group", type=float, default=0.1, help="fraction with a second ;group (default 0.1)")
    parser.add_argument("--headers", type=float, default=0.02, help="fraction with #EXTVLCOPT header lines (default 0.02)")
    parser.add_argument("--dupes", type=float, default=0.03, help="fraction of tvg-ids duplicated as HD/SD twins (default 0.03)")
    parser.add_argument("--dead", type=float, default=0.0, help="fraction of URLs pointing at 127.0.0.1:9 (connection refused)")
    parser.add_argument("--numbering", choices=["blocks", "dense", "none"], default="",
                        help="tvg-chno plan (default: blocks for --profile synthetic, none for realistic)")
    parser.add_argument("--chno-gap", type=float, default=0.15,
                        help="fraction of numbering steps that skip 1-3 numbers (default 0.15)")
    parser.add_argument("--subchannels", type=float, default=0.04,
                        help="fraction of numbers that become a subchannel of the one before (default 0.04)")
    parser.add_argument("--crlf", action="store_true", help="CRLF line endings")
    parser.add_argument("--bom", action="store_true", help="prefix a UTF-8 BOM")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.channels < 1 or args.groups < 1:
        sys.stderr.write("gen-playlist: --channels and --groups must be positive\n")
        return 2
    for name in ("epg_ids", "multi_group", "headers", "dupes", "dead", "chno_gap", "subchannels"):
        value = getattr(args, name)
        if not 0.0 <= value <= 1.0:
            sys.stderr.write("gen-playlist: --%s must be between 0 and 1\n" % name.replace("_", "-"))
            return 2
    if not args.numbering:
        args.numbering = "none" if args.profile == "realistic" else "blocks"
    if not args.now:
        args.now = int(time.time()) // 3600 * 3600
    channels, groups = generate(args)
    stats = assign_numbers(channels, args)
    m3u = io.StringIO()
    write_m3u(m3u, channels, args)
    m3u_bytes = write_out(args.out, m3u.getvalue())
    sys.stderr.write("gen-playlist: m3u %s channels=%d groups=%d bytes=%d sha256=%s\n"
                     % (args.out, len(channels), len(groups), m3u_bytes, sha256_of(args.out)))
    # CN13 asks for the gap to be recorded explicitly in the QA results, so the
    # generator states it rather than leaving QA to count it by hand.
    sys.stderr.write("gen-playlist: numbering=%s numbered=%d block=%d gaps=%d subchannels=%d duplicates=%d highest=%d\n"
                     % (args.numbering, stats["numbered"], stats["block"], stats["gaps"],
                        stats["subchannels"], stats["duplicates"], stats["highest"]))
    if args.xmltv:
        xml = io.StringIO()
        programmes = write_xmltv(xml, channels, args)
        xml_bytes = write_out(args.xmltv, xml.getvalue())
        sys.stderr.write("gen-playlist: xmltv %s now=%d hours=%d programmes=%d bytes=%d sha256=%s\n"
                         % (args.xmltv, args.now, args.hours, programmes, xml_bytes, sha256_of(args.xmltv)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
