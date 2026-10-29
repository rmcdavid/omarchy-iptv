# A part of bin/omarchy-iptv (D-REL-7), not a module: the helper compiles
# this file into its own namespace in the order its HELPER_PARTS lists, so
# a part sees every name the parts before it define. Run the helper.
from __future__ import annotations

import argparse
import array
import bisect
import codecs
import errno
import fcntl
import gzip
import io
import json
import math
import os
import pwd
import re
import select
import signal
import stat
import time
import urllib.parse
import zlib
from typing import Any, BinaryIO



# Heavier modules (socket, calendar, hashlib, unicodedata, urllib.request,
# xml.etree, traceback) are imported where needed so that `play`, `status`
# and `epg --now-only` start faster.

def _manifest_version() -> str:
    """The plugin's version, read from manifest.json beside this helper.

    D-REL-1: a constant here said 0.2.0 for four releases while the manifest
    moved on, so --version and the User-Agent both lied and nothing noticed.
    manifest.json is on the release allowlist, so it is always beside the
    helper in an install; the fallback only keeps a stray copy starting.
    Resolved through realpath, as the stub finds its parts (D-REL-7), so a
    symlink to the helper placed elsewhere reads the manifest it belongs to."""
    try:
        here = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(here, os.pardir, "manifest.json"), encoding="utf-8") as fh:
            found = json.load(fh).get("version")
        if isinstance(found, str) and found.strip():
            return found.strip()
    except (OSError, ValueError):
        pass
    return "0.0.0+unknown"


VERSION = _manifest_version()
USER_AGENT = "omarchy-iptv/" + VERSION

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

# Schemes a stream URL may use. Anything else is dropped at parse time so it
# can never reach mpv (neither as argv nor over IPC).
STREAM_SCHEMES = {"http", "https", "rtmp", "rtmps", "rtsp", "udp", "rtp", "mms", "mmsh", "srt"}
# Schemes a playlist/EPG *source* may use.
SOURCE_SCHEMES = {"http", "https", "file"}

MAX_SOURCE_BYTES = 64 * 1024 * 1024
# Bounds on what channels.json may carry (S-07): the shell parses that file
# on its UI thread and the guide builds one column row per group. A 64 MB
# source of 40-byte entries would otherwise be ~1.5 M channels. Real lists
# top out around 11k channels / 1k groups; entries beyond MAX_CHANNELS are
# dropped with a warning, groups beyond MAX_GROUPS fold into UNGROUPED
# (which may exist as one extra bucket, so at most MAX_GROUPS + 1 groups).
MAX_CHANNELS = 50000
MAX_GROUPS = 2000
# D-M3U-1 (the maintainer on #11935, against 0.14.2). The two counts above
# bound how MANY channels there are and say nothing about how LONG each one
# is, and MAX_SOURCE_BYTES bounds the input, not what the parser copies out
# of it. `#EXTGRP` persists until the next one, so a single long group line
# was copied into the `group`, `groups` and `searchKey` of every entry after
# it: one line, paid for once in the input, paid for again per channel. So
# every provider-controlled text the parser keeps per channel has a length
# cap here, in code points, and per-channel output is bounded by a constant.
# Display text is CUT at its cap (trailing whitespace trimmed, nothing
# appended); an identifier, a URL or an option value is DROPPED instead,
# because a truncated one is a different and wrong value. Either way the
# parser counts it and says so once per kind in `warnings`, as it already
# does for the counts above.
#
# Chosen from what real playlists carry, measured over all 23 playlist
# fixtures (the test suite's and the dev harness's, on the dev branch; 285
# channels, 2026-10-20): the longest title 290 (qa-attrs.m3u's deliberately
# long one; the next is 89), group-title 24, one group 18, groups per entry 3, #EXTGRP 9,
# tvg-id 26, tvg-name 18, tvg-chno 4, tvg-logo 77, stream URL 84, option
# key 37 and value 88, headers 3 and options 2 per channel. Every cap sits
# well above those, so no fixture's output moves (pinned by the D-M3U-1
# tests), and well below what made the finding: each one is a constant.
M3U_MAX_NAME = 512              # the title and tvg-name: cut
M3U_MAX_GROUP_TEXT = 512        # #EXTGRP or group-title, before the `;` split: cut
M3U_MAX_GROUP = 128             # one group after the split: cut
M3U_MAX_GROUPS_PER_CHANNEL = 16  # groups after the first sixteen: dropped
M3U_MAX_TVG_ID = 256            # tvg-id: dropped (it becomes an id and an EPG key)
M3U_MAX_CHNO = 32               # a channel-number attribute: dropped
M3U_MAX_URL = 4096              # a stream URL: the entry is skipped
M3U_MAX_LOGO_URL = 2048         # tvg-logo: dropped (MAX_SOURCE_URL's figure)
M3U_MAX_OPTION_KEY = 64         # an #EXTVLCOPT / #KODIPROP key or header name: dropped
M3U_MAX_OPTION_VALUE = 1024     # its value, or one header value: dropped
M3U_MAX_OPTIONS = 16            # headers, and options, per channel: the rest dropped
M3U_MAX_EPG_HINT = 2048         # url-tvg / x-tvg-url: dropped (MAX_SOURCE_URL's figure)
# The per-channel warnings ("dropped option-looking key for <name>") were
# bounded only by MAX_CHANNELS times the name: a few MB on the one status
# line the service collects (lane A's OQ-6, D-CLIP-1). The first ones are
# kept verbatim, the rest counted in one more line.
M3U_MAX_CHANNEL_WARNINGS = 20
# D-M3U-1, defence in depth: the marketplace maintainer's second memory
# finding in the helper (after D-EPG-6's entities), and the fourth memory
# path in the plugin's handling of provider bytes (with D-QA-06's gzip,
# found by our own QA, and the shell's logo decoder, D-LOGO-11/13); the
# service's 180 s watchdog bounds time only. So the
# verbs that parse provider bytes -- `playlist` (the refresh and the source
# probe both run it) and `epg` -- set RLIMIT_DATA to this before they fetch
# or parse anything (limit_memory, which says why DATA and not AS), and a
# run that needs more ends with one sentence under the code `too_large`,
# never a traceback.
#
# From the measured need of the largest ordinary inputs, each the smallest
# RLIMIT_DATA the run succeeds under (bisected to 2 MiB, CPython 3.14.7,
# 2026-10-20; the playlists from the dev branch's gen-playlist.py): 10,000
# channels 34-36 MiB; 50,000 (MAX_CHANNELS) 108; a 64 MiB playlist of
# 280,000 ordinary entries 160, and 256 with a flag emoji in one name in
# ten; a 62.4 MB guide for 10,000 channels 138, and a 54.9 MB one for
# 48,000, 206. So 2.0x over the worst of them, 4.7x over MAX_CHANNELS, and
# a 64 MiB input cannot reach it with ordinary content.
MEMORY_LIMIT_MIB = 512
# Tests and QA LOWER the limit through this (in MiB); a value above the
# default is ignored, so the variable can never be used to lift it. The
# service never sets it.
MEMORY_LIMIT_ENV = "OMARCHY_IPTV_MEMORY_LIMIT_MB"
DEFAULT_TIMEOUT = 20
# `--timeout` is a per-socket-operation timeout; a server that trickles one
# byte per second would keep the helper alive forever (S-05). Every HTTP
# download also runs under a wall-clock budget of max(HTTP_DEADLINE_MIN,
# 3 x --timeout) seconds, read in chunks so the check runs often. Tests
# shrink the budget through HTTP_DEADLINE_ENV; the service never sets it.
HTTP_DEADLINE_MIN = 60.0
HTTP_DEADLINE_ENV = "OMARCHY_IPTV_HTTP_DEADLINE"
HTTP_CHUNK = 256 * 1024
DEFAULT_IPC_TIMEOUT = 2.0
UNGROUPED = "Ungrouped"

CHANNELS_FILE = "channels.json"
PLAYLIST_STATUS_FILE = "playlist-status.json"
# D-SINK-8: how the shell hands `playlist` and `epg` their URL (see url_from).
URL_ENV = "OMARCHY_IPTV_URL"
# D-SINK-40 (2026-10-29): where that URL CAME FROM, set by the shell beside
# it at every spawn that carries one (Model.fetchEnvironmentFor). `user` is a
# URL the user typed -- its first hop may reach any address, LAN and loopback
# included; `playlist` is one the provider chose (the url-tvg guide hint).
# Absent reads `user` (a human at their own shell with --url); any other
# value reads `playlist`, the stricter one. The playlist's own host and the
# address class its first hop connected to (channels.json `sourceClass`)
# ride beside them, so a provider-chosen destination on THAT host may stay
# on it (DestinationPolicy, 03-io-playlist.py). No URL is in either.
ORIGIN_ENV = "OMARCHY_IPTV_ORIGIN"
HOME_HOST_ENV = "OMARCHY_IPTV_PLAYLIST_HOST"
HOME_CLASS_ENV = "OMARCHY_IPTV_PLAYLIST_CLASS"
ORIGIN_USER = "user"
ORIGIN_PLAYLIST = "playlist"
# Every class address_class answers. "global" is the only one a destination
# the provider chose may reach unconditionally; "unresolved" is never an
# address's class, only a proxied target this machine could not look up.
ADDRESS_CLASSES = ("global", "loopback", "private", "shared", "link-local",
                   "unspecified", "multicast", "reserved")
# The version of the destination rules a cache was written under
# (playlist-status.json `destinationRules`). A cache without it predates
# them, holds channels nothing checked, and is refreshed at the next start
# (Model.cacheBeforeDestinationRules).
DESTINATION_RULES = 1
EPG_NOW_FILE = "epg-now.json"
EPG_STATUS_FILE = "epg-status.json"
# Helper-private programme window (not a QML contract). Line 1 is a JSON
# header; every following line is "<channel id>\t<records>" so that a
# 10k-channel window loads with str.split instead of a JSON parse.
EPG_WINDOW_FILE = "epg-window.txt"
STATE_FILE = "state.json"
# D-SINK-18. The host's own settings file, the ONE path `config shield` may
# touch, and the only two names this helper needs to know about the shell.
# Its SCHEMA still belongs to the host and is still refused here (see the
# D-SRC-11 note above setting_owned_warnings): the shield changes the file's
# MODE and never opens it for writing, so it learns a path and not a schema.
HOST_CONFIG_DIR = "omarchy"
HOST_CONFIG_FILE = "shell.json"
# Group and other, all three bits each. Clearing exactly these is the whole
# authorised change: owner bits and the setuid / setgid / sticky bits are
# left alone, because "make this file private" is the ruling and nothing
# wider was asked for.
CONFIG_GROUP_OTHER = 0o077
# Every verdict `config shield` can print, and the subset that means the
# container is private. The model (Model.mjs) switches on these strings, so the join is
# made by a call rather than by a name (engineering rule 13, dev branch): one
# shared config-shield JSON fixture (dev branch) is the single list, asserted
# against this tuple by the python suite and against the model by the node
# suite.
CONFIG_SHIELD_VERDICTS = ("private", "exposed", "absent", "not_regular",
                          "symlink", "foreign", "replaced", "error")
CONFIG_SHIELD_PRIVATE_VERDICTS = ("private",)
# A rename over the path between our open and our read-back is a race with
# the host's own atomic writer, not a failure: re-open and look again. Three
# is a bound, not patience -- an unbounded retry is the bug the project's
# parallel-working rules (dev branch) name.
CONFIG_SHIELD_ATTEMPTS = 3
# Per-source cache layout (ARCHITECTURE-SOURCES.md D5/D6): every source keeps
# the five file names above inside <cache-dir>/sources/<key>/. The key is
# fnv1a32 of the normalized playlist URL (8 hex digits, "-2", "-3" on a
# collision); it is validated before it ever becomes a path component.
SOURCES_DIR = "sources"
SOURCE_KEY_RE = re.compile(r"^[0-9a-f]{8}(-[0-9]{1,3})?$")
FAILED_FILE = "failed.json"
# FAILED_FILE is in this tuple deliberately: it is what makes a removed
# source take its failure marks with it, which is D-LOGO-4's lesson applied
# before the defect rather than after it.
# D-LOGO-22: the per-source memo of logo addresses whose fetch failed,
# beside channels.json and never inside logos/ (whose census counts
# entries); in CACHE_FILES for FAILED_FILE's reason, so a removed source
# takes it along and clear_source_dir can still empty the directory.
LOGO_FAILED_FILE = "logo-failed.json"
CACHE_FILES = (CHANNELS_FILE, PLAYLIST_STATUS_FILE, EPG_NOW_FILE, EPG_STATUS_FILE, EPG_WINDOW_FILE,
               FAILED_FILE, LOGO_FAILED_FILE)
EPG_CACHE_FILES = (EPG_WINDOW_FILE, EPG_NOW_FILE, EPG_STATUS_FILE)
# The one subdirectory a source owns. Named here rather than spelled in
# three places, because `cache logos-clear` deletes what `logos --fetch`
# writes and a rename that reached one and not the other would either
# strand the files forever or delete a directory nobody meant.
LOGO_SUBDIR = "logos"
TEMP_PREFIX = ".tmp-"
DEFAULT_EPG_MAX_AGE = 86400
# D-LOGO-22 (the lead's ruling of 2026-10-24): a logo address that failed
# -- timeout, refusal at the gate, an HTTP error, a header the bounds
# refused -- is not tried again for a day, the one TTL the memo has
# (DEFAULT_EPG_MAX_AGE's figure), so a dead host costs one try a day
# rather than one a run; and the memo holds at most LOGO_FAILED_MAX
# entries (MAX_LOGO_FILES' figure, 05-ipc-logos.py; the cap on the folder
# the memo stands beside), a full one recording nothing new until an
# entry expires. The memo's constants live here because the parts
# compile in order and 06-failed.py reads them; its code is there.
LOGO_FAILED_TTL = DEFAULT_EPG_MAX_AGE
LOGO_FAILED_MAX = 5000
# Channel id schemes (ARCHITECTURE.md decision 6). Scheme 1 shipped from 0.1
# to 0.7: `t:<tvg-id>` when unique in the playlist, else `u:<fnv1a32(url)>`.
# The stream URL of an Xtream provider carries the account password, so every
# `u:` id dies the day that password is rotated -- measured on the user's own
# 3,335-channel list, exactly 1 id of 3,335 survived a rotation, taking every
# favorite, recent, lastPlayed and session record with it. Scheme 2 tries the
# channel NAME in between: the one column a credential rotation cannot touch.
CHANNEL_ID_SCHEME_LEGACY = 1
CHANNEL_ID_SCHEME = 2
# state.json version 2 (ARCHITECTURE-SOURCES.md section 2.1); caps per SR5.
STATE_VERSION = 2
CACHE_LAYOUT = 2
MAX_SOURCES = 50
MAX_SOURCE_URL = 2048
MAX_LABEL = 64
# D-CLIP-1 (R8): the `clipboard` verb is the ONE process allowed to hold
# clipboard bytes, briefly, and die. The shell used to collect wl-paste's
# whole output before cutting it (a user Ctrl+V over a 100 MB foreign offer
# cost the shell +298 MB and kept most of it); now the helper reads at most
# MAX_CLIPBOARD_BYTES from the pipe and terminates the child at the cap.
# The arithmetic: the shell keeps LIMITS.url * 4 characters (2048 * 4 =
# 8192 UTF-16 units, the cut Service.qml always applied), and a UTF-8
# character is at most 4 bytes, so 8192 * 4 = 32768 bytes (32 KiB) is the
# most any reply can need. The deadline mirrors Model.CLIPBOARD_TIMEOUT_MS;
# the shared fixture clipboard.json pins both sides to one number. Tests
# shrink the deadline through CLIPBOARD_TIMEOUT_ENV; the service never sets it.
CLIPBOARD_ARGV = ["wl-paste", "--no-newline", "--type", "text"]
MAX_CLIPBOARD_CHARS = MAX_SOURCE_URL * 4
MAX_CLIPBOARD_BYTES = MAX_CLIPBOARD_CHARS * 4
CLIPBOARD_TIMEOUT = 5.0
CLIPBOARD_KILL_GRACE = 1.0
CLIPBOARD_CHUNK = 4096
CLIPBOARD_TIMEOUT_ENV = "OMARCHY_IPTV_CLIPBOARD_DEADLINE"
SOURCE_ORIGINS = ("guide", "xtream", "cli", "migrated")
SOURCE_KINDS = ("http", "file")
UNSAFE_PATH_PREFIXES = ("/proc", "/sys", "/dev")

# EPG window kept in the private cache: programmes overlapping
# [now - EPG_PAST_SECONDS, now + EPG_FUTURE_SECONDS] at fetch time.
EPG_PAST_SECONDS = 2 * 3600
EPG_FUTURE_SECONDS = 12 * 3600
EPG_DEFAULT_TTL = 6 * 3600
EPG_REFETCH_MARGIN = 2 * 3600     # re-download when the window ends sooner than this
EPG_VALID_MAX = 300               # epg-now.json is never declared valid longer than this
EPG_MAX_TITLE = 200
EPG_MAX_PER_CHANNEL = 400
# D-EPG-7: the time memo's bounds (parse_xmltv_time). A well-formed XMLTV
# time is at most 20 characters ("YYYYMMDDHHMMSS +HHMM"); 64 leaves room for
# padding whitespace and refuses only junk. The memo keeps an ASCII key only
# (the round-1 recheck of lane-bounds-l, P3 (d)): the first version said
# "about 3 MiB, whatever the feed" while a 64-character key of astral
# characters is a 316-byte str, which put the worst case near 6 MiB. A
# non-ASCII value is still parsed (`\d` reads any decimal digit); it is only
# not remembered, and a memo changes no answer. At the cap the memo holds
# 16,384 ASCII keys of at most 64 characters: 16,384 x (105 bytes, what
# sys.getsizeof gives a 64-character ASCII str on CPython 3.14 + 32 for the
# epoch int + about 40 of dict table) = 2.9 MB, about 2.8 MiB, whatever the
# feed.
EPG_TIME_CACHE_MAX = 16384
EPG_TIME_CACHE_KEY_MAX = 64
# D-EPG-8 (R30g): a guide <display-name> is folded (_CONTROL_WS) and cut to
# this many code points before either name key is made, the playlist's own
# cap on a channel name, so a name key costs at most what a playlist name
# can. A longer name could never equal a playlist name anyway. Since
# D-EPG-12 (R32d) the fold is epg_name_text, inside the key functions, so
# the playlist side takes the same one.
EPG_MAX_DISPLAY_NAME = M3U_MAX_NAME
# D-EPG-10 (R30d): WITHOUT a playlist index (no readable channels.json when
# the guide is fetched) the parse keeps every guide channel under its own
# id, and what it keeps -- the claim, the programme list, the id itself,
# and the epg-now.json entry the shell holds -- was bounded only by the
# input. It now admits at most MAX_CHANNELS distinct guide channels, the
# playlist's own cap (the shell can show no more rows than that), and an
# id longer than M3U_MAX_TVG_ID, which no playlist tvg-id can equal, is
# not admitted at all (rule 15: the entry's KEY was the other unbounded
# term). Programmes refused either way are counted, never dropped in
# silence. With an index neither applies: every key is a playlist tvg-id.
EPG_MAX_GUIDE_ID = M3U_MAX_TVG_ID
EPG_DEFAULT_DURATION = 3600       # for a programme without a stop and no successor
# M4-02 detail caps, in code points, applied when the whitespace is folded
# and again after the URLs are redacted (see clean_detail). A longer value is
# CUT at the cap with nothing appended: no ellipsis, no word boundary, so the
# panel can end mid-word, and a value carrying URLs ends up shorter than the
# cap because redaction removed something.
#
# 400 is a judgement, not a measurement: the synopsis length of a real guide
# has not been measured here. What HAS been measured is what the cap is for.
# The window keeps up to EPG_MAX_PER_CHANNEL records per channel and the
# recompute reads all of them, so the description is the one field that can
# multiply the cache: a synthetic 2,000-channel guide carrying a
# 600-character desc on every one of 48,000 programmes takes
# epg-window.txt from 2.41 to 23.13 MiB and epg-now.json from 0.35 to 2.07
# MiB.
#
# This number is NOT the only lever, which is what this comment used to say.
# MAX_SOURCE_BYTES is the hard one and it binds first. Measured on this
# machine with every detail field filled to exactly these caps:
#   10,000 channels x 28 programmes -> 188.84 MiB of XML, REFUSED outright
#       ("EPG file ... is larger than 64 MB"), so the ~100 MiB cache that
#       extrapolating the 2,000-channel run suggests is not reachable.
#   10,000 x 9 -> 61.15 MiB of XML, the largest detail-bearing guide that
#       fits: 90,000 programmes, epg-window.txt 48.96 MiB, epg-now.json
#       11.60 MiB, nowCount 10,000. epg-now.json is bounded by CHANNELS, not
#       programmes, so 11.60 MiB is its ceiling at 10,000 channels either way.
# The cost that shows is the recompute: `epg --now-only` over that window
# reads 176 ms (in-process, best of 3) against 84 ms for the same 10,000
# channels detail-free. That is over the 100 ms the 10,000-channel now-only
# budget case names as its budget, and under its 500 ms ceiling
# (`test_now_only_10k_channels_is_fast`, the EPG test module on the dev
# branch); the detail-bearing window is pinned beside it by
# `test_now_only_10k_detail_bearing_channels_is_fast`, whose ceiling is set
# from this measurement rather than inherited. Move this number with a
# measurement, and re-level that case.
EPG_MAX_DESC = 400
EPG_MAX_CATEGORY = 48
EPG_MAX_EPISODE = 32
# The detail keys, in the fixed order encode_record emits them. Fixed because
# epg-now.json is compared byte for byte by the gzip twin test (dev branch).
EPG_DETAIL_KEYS = ("desc", "category", "episode")
# The four matcher strategies, as RANKS: strongest first, and the order the
# names appear in is the order build_alias's maps are tried in.
# A stronger strategy displaces a weaker one on the same playlist channel
# whatever order the guide streamed them in (see claim_channel).
#
# ADDR is F-EPG-11, added after the M4-01 precision audit measured that the
# identifier it used as its ORACLE -- a guide channel id sitting in the
# playlist row's own stream address -- was reaching 185 rows that the matcher
# itself never read. Why it ranks where it does, measured on the frozen
# 1,453-channel list against the frozen Pluto guide (427 declarations) --
# a dated measurement, 2026-10-03, over inputs that no longer exist
# (F-EPG-24, F-EPG-26: not re-derivable; the live list drifts):
#
# EVERY census below counts the STREAM url and nothing else, which is the
# only field this strategy reads. The round that added ADDR quoted 193 and
# 153 here instead; those are the stream-OR-LOGO union, taken from the
# precision audit's id oracle, which read the logo as a fallback without
# saying so (F-EPG-14). Re-derived field by field over the frozen inputs,
# by plain substring search for each of the guide's 427 declared
# <channel id> values: STREAM 185 rows, LOGO 64, union 193, logo-only 8.
# So a census quoted without its field is unusable, and this one says it
# every time. (Filed by the four-lens review of the F-EPG-11 round; the id
# is the lead's to allocate on the board, which is why this comment names
# the measurement and not a number nobody can look up.)
#
#   ID    first, unchanged: the playlist author writing tvg-id="<guide id>"
#         is the only strategy where the join is DECLARED rather than
#         inferred. Contributed 0 on these inputs, so nothing measured here
#         ranks it; it stays first because a declaration outranks a
#         deduction. The CASE-FOLDED half of that map is not a declaration
#         and is ranked by a different argument -- see match_xmltv_channel.
#   ADDR  second. Against NAME the ordering is measured: of the 185 rows
#         whose STREAM address names a guide channel, 145 were already paired
#         with THAT channel by name, 0 were paired with a different one, and
#         40 were paired with nothing. The one row where the two strategies
#         compete for a guide channel is decided by the address and the
#         address is right: the guide's `Heartland` is Pluto's playout of it,
#         `Heartland.us@Web` streams exactly that playout and
#         `Heartland.us@Eastern` streams the broadcaster's own, which the
#         name fold could not tell apart. Against FEED the ordering is
#         UNVERIFIED on these inputs (FEED contributed 0) and is set by
#         argument: FEED compares a TRUNCATION of the two ids and its own
#         docstring records that it picks arbitrarily between @SD/@HD twins,
#         while ADDR compares a whole id for equality.
#   FEED, NAME  unchanged, one rank weaker each.
EPG_MATCH_ID = 0
EPG_MATCH_ADDR = 1
EPG_MATCH_FEED = 2
EPG_MATCH_NAME = 3
EPG_MATCH_KEYS = ("matchedById", "matchedByAddr", "matchedByFeed", "matchedByName")
# The shortest alphanumeric run in a stream address that ADDR will accept as
# a guide channel id. It is a TRIM, not the collision guard: the guard is the
# ambiguity rule below (a token claimed by two rows is thrown away), and the
# floor only keeps short words out of the index.
#
# The strategy is "a guide channel id that appears verbatim as an
# alphanumeric token of the row's stream URL", which is provider-general: it
# names no provider, no host and no id SHAPE. The absurd collision it has to
# refuse is a short id -- a guide declaring id="tv" or id="playlist" would
# otherwise claim a row for every address containing that word.
#
# What the floor actually buys, re-measured over the 1,453 real STREAM
# addresses of the list frozen 2026-10-03 (F-EPG-24: a dated measurement
# over an input that no longer exists, not re-derivable; the field this
# strategy reads; the figures the round shipped here were taken over
# stream+logo and are wrong on this field):
#
#   With no floor at all, 626 alphanumeric tokens occur in more than one
#   row's address and NONE of them is a 24-hex id. The longest is
#   `44f73ba4d03e9607dcd9bebdcb8494d86964f1d8`, 40 characters, 2 rows. 134
#   of the 626 are longer than eight characters. Restricted to purely
#   ALPHABETIC tokens -- the kindest reading of "URL vocabulary" -- the
#   longest is `montgomerycommunitymedia`, 24 characters, and 32 of them are
#   at least twelve characters long and so survive this floor:
#   `sinclairstoryline` (4 rows), `getstreamhosting` (6), `lionsgatestudio`
#   (3), `ewscrippscompan` (5), `toonamiaftermath` (2). Twelve therefore does
#   NOT clear the vocabulary, which is what the previous version of this
#   comment claimed; `channels` is 6 stream rows and 131 LOGO rows, and
#   `provider` is 0 stream rows.
#
#   Swept through build_alias itself, the floor changes no OUTCOME on this
#   provider. Declared guide ids the index reaches: 185 at every floor from
#   4 to 24, and 0 at 25 (past the guide's 24-character ids). At 8,
#   `playlist` (583 rows) is indexed and then discarded as ambiguous anyway,
#   so the ambiguity rule is doing the work. What the floor buys is index
#   SIZE: addrIndexed/addrDroppedPlaylist go 2198/7696 at floor 4, 1271/1757
#   at 8, 719/301 at 12, 299/71 at 24. That is the whole of it, and it is
#   worth keeping for the reason in EPG_ADDR_MAX_TOKENS below -- every
#   indexed token is a row the guide could claim -- not because it makes a
#   collision impossible.
#
# A provider whose ids are shorter than this, or whose ids contain a
# character that is not a letter or a digit (`ESPN.us` -- the dot is a token
# boundary, so the token is `ESPN`, not the id), gets NOTHING from this
# strategy and is matched exactly as it was before. That is the intended
# failure: silence, not a guess.
#
# What the floor does NOT buy, and the class this strategy can get WRONG
# rather than silent: a guide id that is itself a >= 12-character
# alphanumeric run occurring in exactly one row's address. Driven through the
# real verb, not reasoned about: a guide declaring id="masterplaylist" takes
# the one row whose address carries that word (matched 1, matchedByAddr 1),
# and a guide declaring id="1791015219000" takes the one row whose query
# string carries that millisecond expiry. Both are wrong answers, not
# silence. The same id in TWO rows is silence (addrDroppedPlaylist 2,
# matched 0) -- that is the ambiguity rule, again, and it is the only thing
# standing here. Pinned by test_epg_match.py's AddressCollisionTest.
#
# Rule 5. A playlist URL carries provider credentials, so this index reads
# one. It is BUILT from them and nothing is published from it: the maps stay
# inside build_alias's return value, the only things that leave are the three
# integers `addrIndexed`, `addrDroppedPlaylist` and `addrNameConflicts`, and
# every key the window and epg-now.json carry is a playlist tvgId exactly as
# before. A hostile
# GUIDE could try to steal a row by declaring an id equal to a token of the
# user's address, but it would have to guess a run of >= 12 characters that
# belongs to exactly one row, and it is never told whether it succeeded --
# the helper fetches the guide and sends it nothing back.
EPG_ADDR_MIN_TOKEN = 12
_EPG_ADDR_TOKEN = re.compile(r"[A-Za-z0-9]{%d,}" % EPG_ADDR_MIN_TOKEN)
# The most tokens ADDR will take from ONE address, and the reason the index
# has a size the reader can compute.
#
# The index is linear in address BYTES, not in rows, and the docstring of
# build_alias used to say "bounded by the ADDRESSES, so by MAX_CHANNELS rows
# of a source that MAX_SOURCE_BYTES already caps at 64 MiB" as if that were
# reassurance. Nobody had measured it at those caps. Measured now, three
# revisions back to back in one process, 3 runs each, over MAX_CHANNELS rows
# whose addresses carry 50 long tokens each -- 61.3 MiB of address text,
# inside MAX_SOURCE_BYTES -- reporting the minimum of each (this machine was
# loaded; the RATIOS are the finding, the absolute seconds are not):
#
#   pre-ADDR  (eb89f0f)   1,481-1,542 ms   peak traced  20.0 MiB   no addr map
#   as shipped (ada9220) 11,792-12,119 ms   peak traced 379.4 MiB   2,500,000 tokens
#   with this cap         7,485-7,721 ms   peak traced 178.8 MiB     800,000 tokens
#
# (the range is two whole runs of the same harness on this machine; the
# memory figures repeated to the tenth of a MiB, the wall times did not)
#
# Not quadratic, and 11.8 s is inside Service.qml's helperTimeoutMs, so the
# shipped behaviour was never a hang. It was ~6x the input in Python objects
# inside the helper on every guide fetch, where the index before ADDR held
# one name key per row.
#
# What the cap changes is that the bound is now a product of two constants a
# reader can multiply -- at most MAX_CHANNELS * EPG_ADDR_MAX_TOKENS = 800,000
# entries -- instead of "bounded by the addresses". Measured: 2.1x less
# memory and about 1.6x less time at the caps. It does NOT make the cost
# constant: scanning stops after the cap's tokens, so the time is still
# linear in the bytes read up to that point, and about 1.2 s of the 7.5 is
# the "bare" map this round added for addrNameConflicts (measured by removing
# it: 6,170 ms against 7,383 ms in the same pair of runs). Pinned by
# test_the_address_map_is_bounded_per_row, which is a bound on the INDEX and
# not a wall-clock budget -- a timing assertion at these caps would take 7 s
# of every suite run and would fail on a loaded machine for reasons that are
# not this code.
#
# The synthetic shape above is adversarial on purpose. The owner's real
# 1,453-row list (frozen 2026-10-03, F-EPG-24: a dated figure over an input
# that no longer exists) averaged 0.7 qualifying tokens per address, so a
# 50,000-row list in that shape would not come near these figures; the caps
# are what
# MAX_SOURCE_BYTES and MAX_CHANNELS actually permit, which is the number a
# bound has to be stated at.
#
# Sixteen, and the recall cost on the frozen data is ZERO. Measured 2026-10-03
# over the owner's 1,453 addresses, frozen then and gone since (F-EPG-24; not
# re-derivable): the most qualifying tokens any one of them holds
# is SIX, and every one of the 185 declared guide ids the index reaches is
# the FIRST qualifying token of its row's address (position 0 of the de-duped
# run). Swept, the index is byte-identical to the uncapped one at every cap
# down to 6 (addrIndexed 719, addrDroppedPlaylist 301, the same 185 ids) and
# the 185 ids survive even at a cap of 1. Sixteen is 2.7x the measured
# maximum on a real provider list, which is the headroom; it is not a number
# this data forces.
#
# One further effect is ARGUED and UNMEASURED, and says so rather than
# sitting here as a second reason: the cap would also narrow the hijack
# surface the EPG_ADDR_MIN_TOKEN comment names, because the tokens it drops
# are the ones at the END of a long address -- JWTs, signatures, expiries in
# a query string -- and each of those is a >= 12-character run belonging to
# exactly one row, which is that comment's uncovered class. On THIS data the
# cap drops nothing at all (the busiest address holds six tokens), so no
# measurement here supports it, and it is not why the cap is 16.
EPG_ADDR_MAX_TOKENS = 16
# One record per programme,
# 'SSSSSSSSSS EEEEEEEEEE "title"[,"desc":"...","category":"...","episode":"..."]'
# (fixed-width epochs, then the JSON-encoded title FOLLOWED BY the optional
# M4-02 detail members), joined by DEL. The fixed prefix lets bisect and plain
# string comparison find now/next, and the pre-encoded tail lets the recompute
# emit epg-now.json by concatenation (no per-channel encoder work): the
# readers prepend '{"title":' to the tail and append the two numbers.
#
# A programme with no detail therefore produces the record it produced before
# M4-02, byte for byte, which is why an epg-window.txt written by an older
# helper is still readable by this one and costs nothing to keep.
#
# Why the M4-02 detail fields cannot break the bisect contract: every
# comparison the readers make is decided at or before index 10. Records sort
# by start, every record carries ten digits at [0:10] and a space at [10],
# and compute_now_next bisects against '<ten digits>~' -- "~" (0x7e) is above
# every digit and above the space, so a record with the same start always
# compares below the probe whatever follows it. The stop comparison slices
# [11:21] by position. Nothing any reader does looks past index 22 except
# json.loads of the whole body, so the body may grow freely.
EPG_RECORD_SEP = "\x7f"

MPV_DEFAULT_USER_AGENT = "libmpv"   # mpv 0.41 `--list-options` default, used when option-info is unavailable
# mpv property-expands the `title` option ("${path}" would render the stream
# URL, credentials included, in the window title; S-01). "$>" disables
# expansion for the rest of the string (verified on mpv 0.41 via expand-text).
# `force-media-title` is not expanded (verified) and stays raw so media-title
# and the OSC show the plain name. Mirrors Model.MPV_RAW_PREFIX.
MPV_RAW_PREFIX = "$>"

_HEADER_NAME = re.compile(r"^[A-Za-z0-9-]+$")
_SAFE_OPTION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")   # never option-looking (D-QA-09)
# Combining Diacritical Marks (U+0300-U+036F) after an ASCII letter, i.e. a
# decomposed Latin accent. Marks on other scripts stay (Cyrillic breve in
# "\u0439" must not fold to "\u0438").
_LATIN_MARKS = re.compile("([a-z])[\u0300-\u036f]+")
# TWO whitespace classes for two purposes, and the difference is the rule
# (R32a''', 2026-10-22, D-SINK-36; R32a'' before it, D-SINK-32, D-SINK-33):
#
#   A URL READER REFUSES THE UNION. validate_source_url (and
#   Model.validateSourceUrl over URL_SPACE_CODES) refuses a typed or stored
#   URL holding ANY member of URL_SPACE_CHARS, the union of JS `\s`, Python
#   `\s` and U+FEFF, so that no engine's own notion of whitespace is ever
#   consulted and a URL one mirror accepts is never one the other splits.
#
#   A FREE-TEXT REDACTOR DELIMITS AT ASCII. redact_urls ends a URL run
#   (_URL_TAIL_RE), and run_host_parts ends its authority (_URL_DELIMITER),
#   at URL_DELIMITER_CHARS ONLY: space, tab, LF, CR, FF, VT -- six code
#   points, Model.URL_DELIMITER_CODES the same six. Every other whitespace
#   or control code point is URL TEXT: a password holding U+FEFF, NBSP,
#   U+2028, U+0085 or an information separator stays inside the run, its
#   authority ends at the `@`, and the HOST prints. Under R32a'' both
#   redactors ended the run at the union, and each mirror took the other's
#   worse case: this helper printed `http://myuser<U+FEFF>ss@prov.test/live/1.ts`
#   -- the username and the tail -- where 0.14.3 printed the host
#   (D-SINK-36). A redactor's job is that nothing of a credential survives;
#   the wider the class that ends the run, the more of a password it copies
#   through. The accepted cost (D-SINK-34) is now confined to the six
#   delimiters: a SPACE or a TAB inside a password still splits the run,
#   and the shared fixture pins that output for each of the six and the
#   HOST for every other member.
#
# Both lists are pinned code point by code point over the whole Unicode
# range by the shared url-whitespace fixture (dev branch) in both suites.
# The union, every member listed, none a regex metacharacter inside a class:
#   U+0009 tab, U+000A LF, U+000B VT, U+000C FF, U+000D CR,
#   U+001C U+001D U+001E U+001F (the information separators: Python's `\s`,
#     not JS's),
#   U+0020 space, U+0085 NEL (Python's, not JS's), U+00A0 NBSP,
#   U+1680 ogham space, U+2000..U+200A (en quad .. hair space),
#   U+2028 line separator, U+2029 paragraph separator,
#   U+202F narrow NBSP, U+205F medium mathematical space,
#   U+3000 ideographic space, U+FEFF (JS's `\s`, not Python's).
# `'`, `"`, `<` and `>` are in neither: a password may hold them, so they
# are trailing punctuation (_TRAILING_PUNCTUATION), stripped off the run's
# end and put back.
URL_SPACE_CHARS = ("\t\n\x0b\x0c\r\x1c\x1d\x1e\x1f \x85\xa0\u1680"
                   "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
                   "\u2028\u2029\u202f\u205f\u3000\ufeff")
# The reader's class: what validate_source_url refuses.
_URL_SPACE = re.compile("[" + URL_SPACE_CHARS + "]")
# The redactor's class (R32a'''): the six ASCII delimiters, and nothing
# else, end a free-text URL run and its authority.
URL_DELIMITER_CHARS = "\t\n\x0b\x0c\r "
_URL_DELIMITER = re.compile("[" + URL_DELIMITER_CHARS + "]")
# redact_urls' pieces (F-SINK-11). It used to be one pattern,
# `\b([A-Za-z][A-Za-z0-9+.\-]*)://[^\s'\"<>]+`, whose scheme run the engine
# re-read from every word boundary; the scan is anchored on "://" now and these
# are the parts of that pattern it still needs. The tail ends at the six
# delimiters alone (R32a'''; it was that pattern's `[^\s'"<>]+` until
# 2026-10-22, and the 30-point union for one round after that). `\w` is
# asked rather than guessed, so the word-boundary rule stays Python's own
# outside ASCII.
_URL_TAIL_RE = re.compile("[^" + URL_DELIMITER_CHARS + "]+")
# The sentence punctuation redact_urls strips off a run's end and puts back
# after the host; Model.trailingPunctuationLength has the same set. A `]` is
# kept when the run holds a `[` (an IPv6 literal).
_TRAILING_PUNCTUATION = ".,;:!?)]'\"<>"
_WORD_CHAR_RE = re.compile(r"\w")
# The scheme-legal run that ENDS at a given position. D-PERF-6 (R32e): it
# was `[A-Za-z0-9+.\-]*\Z` under search(s, lo, j), which has NO literal
# prefix, so the engine tried every start in the window and a failed start
# cost the distance to the next non-scheme character: about K*K/2 steps on
# `'a'*K + '!' + 'a'*K + '://x'`, reached on uncapped text (track titles,
# main()'s message and traceback, a fetch error's status line). Now one
# anchored match on [lo, j): `.*` under DOTALL runs to j and backs off to the
# LAST non-scheme character, so the match's end is the run's start, or lo
# when the window is all scheme characters -- the same b, found in one pass
# over the window. A python character loop walking back was measured slower
# (168.5 ms against 54.4 at 1 MiB, F-SINK-11), which is why this stays a
# native match rather than a loop. Equal output on the shared fixture and on
# the generated corpus (the redaction-cost suite on the dev branch); the
# bound is arithmetic, UNVERIFIED by run under the round's input rule.
_SCHEME_RUN_RE = re.compile(r"(?:.*[^A-Za-z0-9+.\-])?", re.S)
# run_host_parts' host end inside the authority (which _AUTHORITY_END has
# already cut at `/`, `?` or `#`): the port's `:` and the parameter
# delimiters `;`, `=`, `&`, so a neighbouring parameter never prints (R32a').
_RUN_HOST_END = re.compile(r"[:;=&]")
# ... and where the port after that `:` ends (R32a'', the non-numeric-port arm).
_PORT_END = re.compile(r"[;=&]")
# The token a free-text redactor prints in place of a withheld host (R32a').
# Model.HOST_WITHHELD owns it; the shared redaction fixture holds both to it.
HOST_WITHHELD = "[host withheld]"
_LEADING_DASHES = re.compile(r"^[\s\-]+")
# make_channel's last-resort display name, and the pattern that recognises one
# after normalize_text. Built from the same constant so the two cannot drift:
# engineering rule 13 (dev branch), two things joined by a name rather than by a call.
GENERATED_NAME_WORD = "Channel"
GENERATED_NAME_FORMAT = GENERATED_NAME_WORD + " %d"
_GENERATED_NAME = re.compile(r"^" + GENERATED_NAME_WORD.lower() + r" [0-9]+$")
_CONTROL_WS = re.compile(r"[\s\x00-\x1f\x7f]+")
# Mirrors Model.sanitizeInput: C0 controls, DEL and C1 controls are dropped.
_CONTROL_CHARS = re.compile("[\x00-\x1f\x7f-\x9f]")
_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):(.*)$", re.S)
# Model.validateSourceUrl's scheme match ([\s\S]* there): a line separator
# after the scheme is caught by the whitespace rule (`invalid`, D-SRC-06),
# never read as a missing scheme.
_SOURCE_SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.\-]*):(.*)$", re.S)
_AUTHORITY_END = re.compile(r"[/?#]")
_BARE_HOST_CHARS = re.compile(r"[:\[\]]")
_ASCII_DIGITS = re.compile(r"^[0-9]+$")
_ZERO_WIDTH = re.compile("[\u200b-\u200d\u2060\ufeff]")
# R30g, rule 15 over D-EPG-8: this was `^\[[0-9A-Fa-f:.]*:[0-9A-Fa-f:.]*...`,
# two adjacent runs over the SAME class (the colon between them is in it), so
# a literal that failed after the second run was retried at every split
# point, k*k steps for k characters. It reads user text only (a source URL,
# already capped at MAX_SOURCE_URL), but a quadratic pattern is the shape
# R30g refuses wherever it stands. Same language: "a run over [hex:.]
# holding at least one colon" is "a run whose first character outside
# [hex.] is a colon", which a lookahead over the class WITHOUT the colon
# asks in one pass; the single run that follows ends where the class does,
# so nothing after it can make it back off more than once a character.
# Held equal to the old pattern by an equivalence test (the parse-bounds
# suite, dev branch).
_IPV6_LITERAL = re.compile(r"^\[(?=[0-9A-Fa-f.]*:)[0-9A-Fa-f:.]*(?:%25[A-Za-z0-9._~\-]+)?\]$")
_BAD_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_XMLTV_TIME = re.compile(r"^(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?\s*(?:([+-])(\d{2})(\d{2})|Z)?$")


class HelperError(Exception):
    """A user-facing failure. `code` is stable (UI may switch on it)."""

    def __init__(self, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


# ----------------------------------------------------------------- paths

def home_dir() -> str:
    return os.path.expanduser("~")


def cache_dir(explicit: str | None = None) -> str:
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(home_dir(), ".cache")
    return os.path.join(base, "omarchy-iptv")


def state_dir(explicit: str | None = None) -> str:
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(home_dir(), ".local", "state")
    return os.path.join(base, "omarchy-iptv")


def runtime_dir() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR") or cache_dir()
    return os.path.join(base, "omarchy-iptv")


def default_socket_path() -> str:
    return os.path.join(runtime_dir(), "mpv.sock")


def disable_core_dumps() -> None:
    """RLIMIT_CORE (0, 0), soft AND hard, on the process that calls this
    (D-SINK-39). Called in a CHILD between fork and exec -- the player's
    (spawn_detached) and wl-paste's (read_clipboard, as Popen's
    preexec_fn) -- and never in this helper itself.

    Why a child needs its own lever: this helper is non-dumpable from its
    first statement (the stub's shield), but the kernel sets dumpable back
    to 1 on every exec, so the shield reaches no child; RLIMIT_CORE is
    inherited across fork and exec and is the one setting that does. What it
    closes, measured 2026-10-25: systemd-coredump stores a user process's
    core under /var/lib/systemd/coredump as root:root 0640 with an ACL that
    lets EVERY process of that uid read it, for two weeks by default (the
    tmpfiles.d age of that directory), and the host then offers to point an
    AI agent at it; a playing
    mpv's memory holds the stream URL, userinfo and all, in ten to thirteen
    copies (three gcore runs: 12, 13, 10), and every provider header value
    in three to eight, while its argv and environment hold none. With a soft limit of 0 systemd-coredump journals the crash
    and stores nothing (COREDUMP_RLIMIT 0, no COREDUMP_FILENAME).

    Why the HARD limit too: the soft limit is only the process's current
    request, and anything in the child's own address space -- the program,
    a library it loads, a config it reads -- may raise it back up to the
    hard one with a plain setrlimit; raising the hard limit takes
    CAP_SYS_RESOURCE. A user's `ulimit -c unlimited` in the shell's
    environment is what the child INHERITS, and (0, 0) replaces both halves
    of it. Lowering both can fail only for a process forbidden to change
    its limits at all; the error propagates to the caller's spawn path (the
    player's error pipe, Popen's SubprocessError) and the child is not
    started -- a spawn that cannot be made safe is refused, never shrugged
    at, the D-SINK-16 shape.
    """
    import resource
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def limit_core_of(pid: int) -> bool:
    """RLIMIT_CORE (0, 0) on a player this helper did NOT start (D-SINK-39,
    the D-SINK-16 half). The detached player survives a shell restart by
    design, so after an upgrade the shell reattaches to an mpv the OLD code
    forked -- nothing between its fork and its exec set a limit -- and then
    feeds it credentialed URLs and provider headers: the same live feed into
    an unprotected process that D-SINK-16 closed for TLS. disable_core_dumps
    reaches only a child of this helper; this reaches a process that is not.

    prlimit(2) lets a process set another's limits when the target's real,
    effective and saved uids and gids all match the caller's -- no ptrace, so
    Yama's scope does not apply -- and lowering takes no capability while
    raising the hard limit back takes CAP_SYS_RESOURCE, so the player cannot
    undo it. Measured 2026-10-25 on a same-uid process: (-1, -1) -> (0, 0),
    the raise refused with EPERM. Returns whether the kernel now reads
    (0, 0); False for a pid that is gone or not ours, which the caller says
    out loud. pid 0 would mean THIS process to prlimit, so it is refused.
    """
    import resource
    if pid <= 0:
        return False
    try:
        resource.prlimit(pid, resource.RLIMIT_CORE, (0, 0))
        return resource.prlimit(pid, resource.RLIMIT_CORE) == (0, 0)
    except (OSError, ValueError, OverflowError):
        return False


def socket_path(explicit: str | None = None) -> str:
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))
    return default_socket_path()


def config_home() -> str:
    """$XDG_CONFIG_HOME, else ~/.config.

    A RELATIVE $XDG_CONFIG_HOME is IGNORED, which the XDG basedir spec
    requires and which matters more here than it would anywhere else in this
    file: this one value decides which file `config shield` changes the mode
    of, and a relative value would aim it at whatever directory the shell
    happened to be started in. cache_dir() and state_dir() accept a relative
    value today; for them the cost is a cache in the wrong place, and the
    difference is exactly that this function feeds a chmod.
    """
    base = os.environ.get("XDG_CONFIG_HOME") or ""
    if base and os.path.isabs(base):
        return base
    return os.path.join(home_dir(), ".config")


def host_config_path() -> str:
    """The one file `config shield` is allowed to touch (D-SINK-18).

    There is deliberately NO path argument and no override flag. A verb that
    chmods whatever path it is handed is a capability this plugin has no
    reason to own, it is the first thing a reviewer looks for, and the shell
    does not need it.

    DERIVED FROM $HOME, NOT FROM $XDG_CONFIG_HOME, because that is what the
    HOST does. The first version of this used config_home() and its docstring
    said "$XDG_CONFIG_HOME is honoured because the host honours it", which is
    the opposite of the truth and was the lead's own instruction. Measured on
    this machine: /usr/share/omarchy/shell/shell.qml:32 reads

        readonly property string userConfigPath: home + "/.config/omarchy/shell.json"

    with `home` from Quickshell.env("HOME") at line 23, and the file contains
    no other reference to XDG_CONFIG_HOME. So on any machine where
    XDG_CONFIG_HOME points somewhere other than $HOME/.config -- a supported,
    ordinary configuration -- the shield would have tightened a file the host
    never writes and reported success, while the credential went into the
    host's real file untouched. Two reviewers found this independently.

    The join between this path and the host's is a NAME, which rule 13 says
    nothing verifies, so the host-config-path test (dev branch) reads that line
    out of the host's own source and goes red if it ever moves. The measured
    host facts are in the plugin contract document (dev branch).

    The home must be ABSOLUTE, and that guard is not decoration. The version
    of this function that first dropped config_home() also dropped its
    relative-value check, and the tests caught it the same minute: with
    HOME="." the verb changed the mode of ./.config/omarchy/shell.json, a file
    chosen by whatever directory the shell happened to be started in, and with
    HOME="" it built a relative path at all. A verb that changes a file mode
    may not take its target from a value meaning "wherever we happen to be".
    Returns "" when nothing names a home, and the caller refuses rather than
    guessing.
    """
    home = os.environ.get("HOME") or ""
    if not os.path.isabs(home):
        try:
            home = pwd.getpwuid(os.getuid()).pw_dir or ""
        except (KeyError, OSError):
            home = ""
    if not os.path.isabs(home):
        # Nothing names a home, so nothing names the file. The caller reports
        # this the way it reports any other refusal; it never guesses.
        return ""
    return os.path.join(home, ".config", HOST_CONFIG_DIR, HOST_CONFIG_FILE)


def mode_text(mode: int) -> str:
    """A file mode as the four-digit octal a human reads, e.g. "0644"."""
    return "0%03o" % stat.S_IMODE(mode)


class FolderUnusable(NotADirectoryError):
    """A folder ensure_private_dir needs is a symbolic link that does not lead
    to a folder (it dangles, or leads to a file), or something that is not a
    folder sits at its path or one above it. An OSError, so every caller that
    already turns an OSError into a warning keeps doing so (ensure_player_dirs);
    main() reports the rest as `folder_unusable` with this sentence, never a
    traceback."""

    def __init__(self, path: str, what: str) -> None:
        super().__init__(errno.ENOTDIR, what)
        self.sentence = "%s %s; nothing was written" % (path, what)


def missing_folders(path: str) -> list[str]:
    """The folders missing at `path` and above it, nearest first, up to the
    first one that exists; creates nothing.

    R25c's refusal is HERE, so the verbs that only delete in a folder refuse
    exactly what the verbs that write into it refuse (D-SRC-74, 2026-10-28):
    a symbolic link at `path`, or above it, that dangles or leads to
    something that is not a folder, or a file or anything else that is not a
    folder there, raises FolderUnusable with R25c's sentence. A link that
    leads to a folder is a folder (os.path.isdir follows it) and ends the
    walk, as it always has in ensure_private_dir."""
    missing: list[str] = []
    current = path
    while current and not os.path.isdir(current):
        if os.path.lexists(current):
            if os.path.islink(current):
                raise FolderUnusable(current, "is a symbolic link whose target is missing or is not a folder")
            raise FolderUnusable(current, "is not a folder")
        missing.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return missing


def ensure_private_dir(path: str) -> None:
    """mkdir -p with every directory this call creates set to 0700 (the
    per-source layout means the helper may be the first to create
    <cache-dir>/sources/, which must be private like its children).

    D-SINK-19 round 15, R25c (D-SRC-32). A symbolic link AT `path` that leads
    to a folder is FOLLOWED, and the folder it leads to is made 0700 like
    one this created -- measured 2026-10-14 on this machine, the helper as a
    subprocess: a link to a 0755 (or 0500) folder came out 0700 after `state
    init`, a state write, `cache migrate`, `failed mark` and `player stop`
    alike, the link left a link. That is the folder the plugin keeps its
    files in, wherever the user put it, so it gets the plugin's own mode;
    the README says so. A link here (or ABOVE it) that DANGLES or leads to
    something that is not a folder is refused with FolderUnusable before
    anything is created: it used to reach a mkdir under the link and end in
    a FileNotFoundError traceback and `code: internal` (every caller --
    the state folder, a cache folder, the runtime socket folder, the logo
    folder -- measured, the same before.txt run). The walk and the refusal
    are missing_folders', which the deleting cache verbs share (D-SRC-74)."""
    for directory in reversed(missing_folders(path)):
        try:
            os.mkdir(directory, 0o700)
        except FileExistsError:
            continue
        chmod_if_kind(directory, 0o700, stat.S_ISDIR)
    # R23d (rule 15): only a DIRECTORY is made 0700. This chmod used to take
    # whatever was at the path, so a regular file where the state directory
    # should be came out 0700 -- executable -- and a FIFO there was chmod-ed.
    chmod_if_kind(path, 0o700, stat.S_ISDIR)


def chmod_if_kind(path: str, mode: int, kind: Any) -> bool:
    """chmod `path` to `mode` only when what is there is the KIND it repairs
    (`stat.S_ISREG` or `stat.S_ISDIR`), decided on the inode that is changed.

    D-SINK-19 round 13, R23d. `state init` chmod-ed a DIRECTORY at the state
    file's path 0755 -> 0600 and made it unsearchable: the mode repair asked
    what the mode was and never what the thing was. An O_PATH descriptor is
    the one open that needs no permission on its target (the 0000 file and
    the 0000 directory this repairs are exactly the ones a read open cannot
    reach), never opens a FIFO or a device (nothing blocks, nothing has a
    side effect), and its fstat decides the kind; the chmod then goes
    through /proc/self/fd/N, which names that inode and no other, so a
    rename between the check and the change cannot redirect it (fchmod
    refuses an O_PATH descriptor with EBADF, measured on Python 3.14 /
    Linux 7.2). Symlinks are followed, as os.chmod always followed them. No
    /proc means no repair, never a chmod by name. A mode that is already
    right is not touched: a chmod is an inotify IN_ATTRIB on whatever the
    shell watches. -> True when the mode was changed; never raises."""
    try:
        fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
    except OSError:
        return False
    try:
        st = os.fstat(fd)
        if not kind(st.st_mode) or stat.S_IMODE(st.st_mode) == mode:
            return False
        os.chmod("/proc/self/fd/%d" % fd, mode)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


# ------------------------------------------------------------- redaction

def url_host(url: str) -> str:
    """Host name of a URL, never the userinfo, path or query."""
    try:
        return urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return ""


def source_host(url: str) -> str:
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return ""
    if parts.scheme in ("http", "https"):
        return parts.hostname or ""
    return "local file"


def run_host_parts(body: str) -> tuple[str, bool]:
    """Mirror of Model.runHostParts (R32a', D-SINK-29, 2026-10-22): for the
    text after one `scheme://`, the RFC host a FREE-TEXT redactor prints and
    whether it is WITHHELD.

    The authority ends at the first `/`, `?`, `#` or whitespace after the
    scheme, its userinfo at the LAST `@` within it (D-SINK-1), and the host
    is what follows that `@`, cut at the first `:` (a port), `;`, `=` or `&`
    (a parameter delimiter, so a neighbouring parameter never prints,
    D-SINK-23); a bracketed literal is the host up to its `]`, or nothing.
    `withheld` is the one predicate the Sources form warns with
    (Model.urlHostWithheld), two arms (R32a'', 2026-10-22), each needing an
    `@` after the authority before whitespace: the host is not bracketed
    and has no dot -- a dotless "host" with a later `@` is most likely a
    username in front of a password holding an unencoded `/`, `?` or `#`,
    and printing it printed the username (`http://myuser:pa#ss@...` ->
    `http://myuser`, D-SINK-28); OR the authority carries a NON-NUMERIC
    port, a `:` after its last `@` whose text up to the next `;`, `=` or
    `&` is non-empty and not all digits (`http://user.name:pa/ss@h.test/x`
    reads as host `user.name`, port `pa`: a dotted username and a password,
    D-SINK-35; `http://me@mail.test:pa/ss@h.test/x` the same). What
    remains, stated: a dotted username before a digits-only password
    prefix (`http://user.name:2024/ab@host/x` -> `user.name`) reads as host
    and port. An empty port validates as an RFC shape and does not count;
    a bracketed literal is never withheld. The authority ends at the six
    ASCII delimiters (_URL_DELIMITER, R32a''': the same six that end the
    run; the authority and the run were cut at two classes until R32a'',
    D-SINK-32, and at the 30-point union for one round after it,
    D-SINK-36) and at no other whitespace: a password holding U+FEFF or
    NBSP is URL text, and its host prints. Where that cut is observable,
    stated: through redact_urls REMOVING it changes nothing (the run
    handed in was already cut at the same six), while cutting at a WIDER
    class shows (a run holding U+FEFF would print the username, D-SINK-32's
    shape, pinned by the shared vectors); through host_withheld over
    validate_source_url's text, removing it shows since D-SRC-63 (a tab is
    kept there): `http://my:pa<TAB>/ss@h.test/x` ends its authority at the
    tab, before the `/`, so the later `@` is not seen (pinned by the
    source tests; each mutation measured red, 2026-10-22). Not url_host:
    urllib's RFC reading is
    right for a display sink and for validation (source_host,
    validate_source_url) and prints that username. Not round 3's last-`@`-
    of-the-run scan either (never shipped): crossing the `/` put a password
    TAIL in the host position (`/live/U5ER/P4@SSW0RD/1.ts` -> `ssw0rd`,
    D-SINK-29) on mpv's error line into the journal and the notification.
    The cost, stated in ARCHITECTURE-SOURCES 3.1: a dotless intranet URL with
    a path `@` withholds its host, `localhost` included. One pass over the
    run: one search per class, no retry; the shared redaction fixture (dev
    branch) holds both mirrors to it."""
    space = _URL_DELIMITER.search(body)
    if space is not None:
        body = body[:space.start()]
    cut = _AUTHORITY_END.search(body)
    authority = body if cut is None else body[:cut.start()]
    rest = "" if cut is None else body[cut.start():]
    hostport = authority[authority.rfind("@") + 1:]
    if hostport.startswith("["):
        close = hostport.find("]")
        return (hostport[:close + 1].lower() if close != -1 else ""), False
    end = _RUN_HOST_END.search(hostport)
    host = hostport if end is None else hostport[:end.start()]
    port = ""
    if end is not None and hostport[end.start()] == ":":
        port = hostport[end.start() + 1:]
        port_end = _PORT_END.search(port)
        if port_end is not None:
            port = port[:port_end.start()]
    later_at = "@" in rest
    dotless = host != "" and "." not in host
    bad_port = port != "" and _ASCII_DIGITS.match(port) is None
    return host.lower(), later_at and (dotless or bad_port)


def host_withheld(url: str) -> bool:
    """R32a': the predicate alone, over a whole URL (or any text holding one)."""
    j = url.find("://")
    return j != -1 and run_host_parts(url[j + 3:])[1]


def run_host(raw: str) -> str:
    """What redact_urls prints for one `scheme://...` run: the RFC host, or
    HOST_WITHHELD."""
    host, withheld = run_host_parts(raw[raw.find("://") + 3:])
    return HOST_WITHHELD if withheld else host


def redact_urls(text: Any) -> str:
    """Replace every URL inside `text` with scheme://host (R12).

    F-SINK-11. ANCHORED ON "://", because the pattern this replaced was
    quadratic in a run of scheme-legal characters and every string that
    reaches here is provider-controlled.

    The old pattern was `\\b([A-Za-z][A-Za-z0-9+.-]*)://[^\\s'"<>]+`. Its `\\b`
    hid the simplest shape -- a run of plain letters offers only one word
    boundary -- so the model's mirror was measured first and this side read as
    cheap. It is not: any run that CONTAINS a word boundary every few
    characters gives the engine a fresh start position for a run that reaches
    to the end of the text, and `.`, `+` and `-` are scheme-legal and are not
    word characters. Measured on python 3.14.7 over "aaaa." repeated: 1.6 ms at
    1,000 characters, 45.0 at 5,000, 174.5 at 10,000, 705.5 at 20,000 and
    2826.2 at 40,000 -- the same curve as the JS side, on a different vector.
    After this change, same vector and same machine: 0.001 / 0.002 / 0.003 /
    0.006 / 0.012 ms. The slowest vector that remains is a single run of
    letters that ends in a real URL, where the whole run is the "scheme" the
    old pattern also swallowed: 0.013 / 0.052 / 0.096 / 0.187 / 0.363 ms. That
    is also the ONE vector this change makes slower, and saying so is the point:
    0.143 ms against 0.363 at 40,000, and 44.5 ms against 51.7 at 1 MiB. Linear
    either way. The trade is four orders of magnitude on the shape that was
    quadratic for a factor of two on the one that never was.

    Why it is the same answer and not a narrower pattern. `:` and `/` are not
    scheme-legal, so the old pattern's greedy scheme run always ended EXACTLY
    at the `://` that followed it and there was never a shorter candidate to
    backtrack to. So the leftmost start the engine took for a given `://` is
    the first position in the scheme-legal run ending at it that holds an ASCII
    letter AND satisfies `\\b`; inside the run the only non-word characters are
    `+`, `.` and `-`, so that test is a character comparison everywhere except
    the run's own first position, where `\\w` is asked (`_` and every non-ASCII
    word character are why it has to be asked). The redaction-cost suite (dev
    branch) drives the OLD pattern as an oracle over the shared fixture and
    thousands of generated strings and asserts the two agree character for
    character.

    This makes the caps in front of this sink cheap, not unnecessary:
    clean_name, clean_field and clean_detail are still what keeps a 64 MiB
    description out of a renderer, and clean_detail still drops a cut token
    carrying "://" rather than hand the redactor half a URL.
    """
    s = "" if text is None else str(text)
    j = s.find("://")
    if j < 0:                       # the old pattern cannot match: same answer
        return s
    out: list[str] = []
    copied = 0                      # everything before this is already in `out`
    # The engine's pos: no match may start before it. `j` is only ever searched
    # from `resume` or from a position already at or past it, so there is no
    # `j < resume` case to guard -- and a guard for a case that cannot happen is
    # a branch no test can go red for.
    resume = 0
    while j >= 0:
        # The scheme-legal run ending at this "://". Searched over a window
        # that doubles until the run's start is strictly inside it (or the
        # window reaches `resume`), so the total work is proportional to the
        # run and not to the text, and no slice is copied.
        window = 64
        while True:
            lo = j - window
            if lo < resume:
                lo = resume
            b = _SCHEME_RUN_RE.match(s, lo, j).end()
            if b > lo or lo == resume:
                break
            window *= 2
        # `\b` at a position whose character is a word character (a letter
        # always is) means "position 0, or the character before is not a word
        # character". Only the run's first position can be preceded by
        # something outside the scheme-legal set, so only it needs `\w`.
        boundary_at_b = b == 0 or _WORD_CHAR_RE.match(s, b - 1) is None
        start = -1
        for p in range(b, j):
            c = s[p]
            if not (("a" <= c <= "z") or ("A" <= c <= "Z")):
                continue
            if p == b:
                if not boundary_at_b:
                    continue
            elif s[p - 1] not in "+.-":
                continue
            start = p
            break
        tail = _URL_TAIL_RE.match(s, j + 3)
        if start < 0 or tail is None:
            # No scheme, or nothing the tail `+` can consume: the old pattern
            # has no match ending at this `://`. j+1 and j+2 cannot begin one
            # of their own; +1 keeps that from being load-bearing.
            j = s.find("://", j + 1)
            continue
        end = tail.end()
        raw = s[start:end]
        # Sentence punctuation after a URL is put back. A `]` is kept when the
        # run holds a `[`: it closes an IPv6 literal, and stripping it left
        # `http://[2001:db8::5].` with no host to show (R32a; a D-SINK-23
        # sibling lane S recorded).
        bracket = "[" in raw
        trailing = ""
        while raw and raw[-1] in _TRAILING_PUNCTUATION and not (bracket and raw[-1] == "]"):
            trailing = raw[-1] + trailing
            raw = raw[:-1]
        host = run_host(raw)
        out.append(s[copied:start])
        out.append("%s://%s%s" % (s[start:j].lower(), host or "[redacted]", trailing))
        copied = end
        resume = end
        j = s.find("://", resume)
    out.append(s[copied:])
    return "".join(out)


def log(message: str) -> None:
    sys.stderr.write("omarchy-iptv: %s\n" % redact_urls(message))


# ------------------------------------------------------- normalization
# Must match the model's normalizeText/searchKey/fnv1a32 byte for byte.

FOLD_GROUPS = [
    ("\u00e0\u00e1\u00e2\u00e3\u00e4\u00e5\u0101\u0103\u0105", "a"),
    ("\u00e7\u0107\u010d", "c"),
    ("\u010f\u0111", "d"),
    ("\u00e8\u00e9\u00ea\u00eb\u0113\u0117\u0119\u011b", "e"),
    ("\u00ec\u00ed\u00ee\u00ef\u012b\u0131", "i"),
    ("\u0142\u013e", "l"),
    ("\u00f1\u0144\u0148", "n"),
    ("\u00f2\u00f3\u00f4\u00f5\u00f6\u00f8\u014d\u0151", "o"),
    ("\u0159", "r"),
    ("\u015b\u0161\u015f", "s"),
    ("\u0165\u0163", "t"),
    ("\u00f9\u00fa\u00fb\u00fc\u016b\u016f\u0171", "u"),
    ("\u00fd\u00ff", "y"),
    ("\u017a\u017c\u017e", "z"),
    ("\u00df", "ss"),
    ("\u00e6", "ae"),
    ("\u0153", "oe"),
]
FOLD = {ch: to for chars, to in FOLD_GROUPS for ch in chars}
_PUNCT = re.compile(r"[\s!-/:-@\[-`{-~]+")
# The same class WITHOUT `*` (U+002A) and `+` (U+002B), for the id fold only.
# Folding is two jobs, not one. SEARCH wants punctuation gone -- a user typing
# "amc" must reach "USA: AMC+" -- so _PUNCT and search_key stay exactly as they
# are. An ID wants every character that tells two streams apart, and over the
# user's four real playlists `+` and `*` are the two that do: dropping them
# merges "USA  AMC" with "USA: AMC+", "US: ESPN" with "US: ESPN*", "US NESN
# (A)" with "US NESN+ (A)" and four Fanduel regional pairs. Measured, keeping
# them takes the four lists from 75 colliding name groups / 155 rows to 65 /
# 133 and raises surviving ids from 5,108 to 5,127 of 5,221. `&`, `#` and `@`
# were measured the same way and change nothing on any of the four, so they
# are not in the class. Mirrors ID_PUNCT_RE in the model.
_ID_PUNCT = re.compile(r"[\s!-)\,-/:-@\[-`{-~]+")


# A channel NAME as the EPG matcher compares it: normalize_id_text with the
# distribution markers taken out first (the ID fold, since D-EPG-5; see
# epg_name_key below). `48 Hours (1080p)` and `48 Hours` are the same programme
# stream; `(1080p)` says how it is encoded and `[Geo-blocked]` says where it
# works, and neither is part of the channel's identity.
#
# WHAT THE STRIP IS WORTH, AND ON WHICH INPUTS (F-EPG-13). This comment stated
# one figure in the PRESENT tense through two supersessions, and said
# `normalize_text` after the fold had already changed under it. Both halves are
# fixed by saying which run each number came from, because no number here is
# about today unless it says so.
#
# A dated record, not re-runnable from any checkout: matching on normalize_text
# alone reached 126 channels and taking these markers out first reached 227,
# measured through build_alias -> parse_xmltv -> match_counts on the frozen
# 1,453-row source of 2026-10-03 against the project's own XMLTV asset, both
# arms under the pre-D-EPG-5 SEARCH fold. 1,155 of those 1,453 names carried a
# marker. That 227 was superseded twice -- 226 by the name-key repair (D-EPG-5)
# and 265 by the address strategy (F-EPG-11) -- and neither successor re-ran
# the strip-OFF arm, so the delta above has no current counterpart and the
# frozen inputs are in no checkout. The strip's own contribution is therefore
# UNVERIFIED at today's baseline; QA-EPG-PRECISION.md (dev branch) 8 says so
# and names what is re-runnable instead. Do not restate 126/227 as a live
# figure.
#
# What IS re-derivable, from the install's own cache rather than a re-fetch:
# on the 1,450-row source installed here on 2026-10-06 the matcher as a whole
# reaches 264 -- 185 by address, 79 by name -- and 1,153 of those 1,450 names
# carry a marker this pattern strips.
#
# That 264 is ONE number, not three. An earlier version of this paragraph
# called epg-status.json's `matched`, epg-now.json's channel count and
# epg-window.txt's line count three artifacts that agree, and invoked rule 14
# while breaking it: the status's `matched` IS the window header's `matched`
# read back by load_window, the same field twice; the window's line count is
# one line per key of the dict match_counts counted; and on this run
# epg-now.json's key set equals the window's exactly, so its length is
# `nowCount`, which match_counts' own docstring below says is the RENDER count
# and a different quantity from the match count. What re-derives the 264 is
# CALLING match_counts over the cached channels.json with the cached window's
# channel keys as `seen_ids` -- 264, measured 2026-10-06 -- and that is exact
# only because `epgChannels` (len(seen_ids)) is 264 too, so no granted claim
# fell outside the window; where the two differ it is a lower bound.
# QA-EPG-PRECISION.md (dev branch) 8 carries the command.
#
# 1,155 of 1,453 against 1,153 of 1,450 is not a like-for-like pair, and
# saying so is the point of this paragraph: the 1,155 was taken while the
# bracket half of this pattern was still the broad `\[[^\]]*\]`, before the
# F-EPG-10 narrowing (1f940b9, 2026-10-04). The pattern change is worth ZERO
# rows on the list that exists -- the pre-narrowing pattern and the shipped one
# both count 1,153 of the live 1,450, measured 2026-10-06 -- so the 2-row drop
# in markers under a 3-row drop in the source is the provider's drift and not a
# change here (F-EPG-24). The frozen arm cannot be re-run to close it.
#
# Deliberately NOT applied inside normalize_text, which is the SEARCH key: a
# user who types "1080" is searching for exactly these markers, and the four
# ranking tiers are calibrated on that key. Two keys, two jobs.
#
# Ambiguity is the price and it is paid by the uniqueness rule, not here:
# stripping takes playlist collisions from 2 channels to 10 on that list (1
# colliding NAME to 5 -- the ten are `nameDroppedPlaylist`, which counts
# channels, and the five names are four News 12 regions and Tennis Channel 2),
# and build_alias drops every colliding name rather than guessing between them.
# The bracket half is TWO LITERALS, not an arbitrary span (F-EPG-10, ruled by
# the product owner on 2026-10-04). It used to be `\[[^\]]*\]`, which strips
# whatever a provider puts in brackets, and that is a branch whose blast
# radius is arbitrary content: a bracket span that carries part of a channel's
# identity would be deleted from the key and the row would match the wrong
# guide channel, silently. Measured before the ruling: the owner's 1,453 names
# carry exactly TWO distinct spans, `[Not 24/7]` 82 times and `[Geo-blocked]`
# 60; 0 of the guide's 427 declarations carry one at all, counting every
# display-name and not just the first; and a named mutation deleting the
# bracket alternative outright produced the SAME pairs, set difference empty
# in both directions, every grade unchanged. So the branch was needed by no
# pair and broke no pair, and narrowing it costs nothing measurable here.
#
# What it costs ELSEWHERE, stated correctly after an adversarial pass refuted
# the first version of this paragraph. That version said an unknown marker
# means "silence, not a wrong answer". It does not, and the reason is that
# narrowing makes the key LONGER: the words inside an unknown span stay in
# it, and they can complete the name of a DIFFERENT guide channel.
# Measured through the real verb on constructed inputs:
#
#   `ESPN [Deportes]` keys as `espn deportes`, which matches a guide channel
#   declared `ESPN Deportes`; the broad pattern keyed it `espn` and matched
#   `ESPN`. Which of those is right depends on what the provider meant by the
#   brackets, and nothing in the data says.
#   `===[ SPORTS ]===`, a separator row, keys as `sports` and matches a guide
#   channel called `Sports`. The broad pattern keyed it empty and matched
#   nothing, which was silence by accident rather than by design.
#
# So BOTH patterns have a wrong-match route and they point opposite ways: the
# broad one deletes a span that carried identity and lands on the generic
# channel, this one keeps a span that was an annotation and lands on the
# specific one. Neither is safe for bracket content nobody has looked at,
# which is the finding F-EPG-10 made in the first place; the narrowing is
# taken because the content on this data IS the two markers and because
# deleting unknown identity is the worse of the two failures, not because
# this one cannot fail.
#
# A new marker is a one-line addition with a census behind it, the bar the
# two above were held to. The census itself is scoped: it covers the 1,453-row
# source installed on this machine, not the four provider lists (5,221
# channels) the id-fold decision below was measured across, which have never
# been censused for bracket spans and are not in this checkout.
_EPG_NAME_NOISE = re.compile(
    r"\((?:\d{3,4}p|sd|hd|fhd|uhd|4k|h\.?26[45])\)"
    # The two markers, tolerant of how they are SPELLED but not of which
    # markers exist. A trailing space, a double space, a hyphen for the
    # slash or a space for the hyphen are the same marker; the first version
    # of this narrowing matched the two byte-for-byte and lost all 142 rows
    # to any of those, which is a provider changing its own punctuation
    # between fetches, not a different provider.
    #
    # D-EPG-12 (ruling R32d, 2026-10-21): this alternative used to read
    # `24\s*[-/]?\s*7`, two unbounded `\s*` runs with only an OPTIONAL atom
    # between them, so the two were adjacent repeats over one class: after
    # `[not 24` a whitespace run of k not followed by `7` was retried at
    # every split of the run, about k*k/2 steps, and build_alias reached it
    # twice per playlist row on the unfolded name. The guard the round before
    # had certified it linear because "its runs are separated by literals",
    # which the optional `[-/]?` is not. Now the second run exists only
    # behind the separator, `(?:[-/]\s*)?`, which whitespace cannot open, so
    # each run backs off at most once over its own length. Same language:
    # held equal to the old pattern on generated inputs, and the helper
    # regex guard on the dev branch grades the old shape super-linear by
    # structure, not by the table alone.
    r"|\[\s*not\s*24\s*(?:[-/]\s*)?7\s*\]"
    r"|\[\s*geo[\s-]*blocked\s*\]", re.IGNORECASE)


def epg_name_text(value: Any) -> str:
    """The ONE fold a channel name takes before it is keyed, on BOTH sides
    of the match: every run of whitespace and control characters to one
    space, the ends trimmed, cut to EPG_MAX_DISPLAY_NAME code points.

    D-EPG-12, ruling R32d (2026-10-21). The guide side folded a
    <display-name> through clean_field before keying (D-EPG-8), and the
    playlist side keyed the raw channels.json name, which the M3U parse
    leaves holding a DEL or a C0 control (sanitize_input runs on user
    input, not on playlist text). _ID_PUNCT folds `\\s`, so a tab keyed
    the same from either side, but `\\x7f` and `\\x00-\\x1b` are not `\\s`:
    a row and a display-name that both carried U+007F keyed differently
    and did not match, and a DEL on one side only matched a name without
    it on the other. Folding inside the key functions, so every caller
    keys the same whatever it passes, is what makes the two sides one.
    An ordinary name is unchanged by it: the key already folded its
    whitespace, and a playlist name is at most M3U_MAX_NAME, which is the
    cap here. Idempotent, so the guide side may fold once more to look at
    the text itself (parse_xmltv's trailing-parenthesis test) at no change.
    """
    if not value:
        return ""
    return _CONTROL_WS.sub(" ", str(value)).strip()[:EPG_MAX_DISPLAY_NAME]


def epg_name_key(value: Any) -> str:
    """The channel-name key the EPG matcher joins on (D-EPG-2, M4-01).

    Folds on normalize_id_text, NOT normalize_text, since D-EPG-5: the id
    fold keeps `+` and `*` "because they are the difference between two
    channels rather than noise inside one", which is exactly the question a
    matcher asks. The search fold drops them, and that single character put
    the guide's `Bloomberg TV+` schedule on the playlist's `Bloomberg TV`
    row, and made four News12/News12+ regional pairs and Tennis Channel
    2/+2 collide so the uniqueness rule dropped all ten rather than guess.
    The project already owned the right rule and the matcher used the other
    one.

    Measured end to end on the frozen inputs (the 1,453-row list and the
    guide frozen 2026-10-03; gone since, F-EPG-24 and F-EPG-26, so a dated
    figure and not a current one) when this changed: matched 227 -> 226,
    and the one pair lost is the wrong one; nameIndexed 1,443 -> 1,453 and
    nameDroppedPlaylist 10 -> 0, so the repair costs one bad pair and
    returns ten channels to the index. No confirmed pair moved.

    Folds through epg_name_text first (D-EPG-12): the playlist side and the
    guide side of the match key the same text the same way.
    """
    return normalize_id_text(_EPG_NAME_NOISE.sub(" ", epg_name_text(value)))


def strip_trailing_qualifier(text: str) -> str:
    """`text` without a TRAILING parenthetical, which on the owner's list is
    the country qualifier: `Pluto TV Reality (United States)` ->
    `Pluto TV Reality`. Nothing in the matcher reads this; see bare_name_key.

    D-EPG-8, ruling R30g: no regex whose cost is super-linear in its input
    is applied to provider text. This was `\\s*\\([^()]*\\)\\s*$` under
    .sub(), which has no literal prefix (it opens with `\\s*`), so the engine
    tried it at EVERY position, and at each position inside a run of k
    whitespace characters `\\s*` took the rest of the run and backed off one
    character at a time looking for `(`: about k*k/2 steps for one run, on
    `<display-name>` text that nothing folded or capped. The answer is the
    same and is computed by three linear scans, because the pattern's match
    is unique when it exists: the `)` must be the last non-whitespace
    character (`\\s*$` takes all trailing whitespace, a final newline
    included), the `(` the last one before it with no `)` between them
    (`[^()]*` holds neither), and the match starts where the whitespace run
    before that `(` starts (the leftmost start the engine reaches), so what
    is left is everything before the `(`, right-stripped. `str.rstrip()`
    and `\\s` test the same predicate (Py_UNICODE_ISSPACE); the equivalence
    test runs the old pattern as an oracle over every code point and over
    generated names, and calls this.
    """
    stripped = text.rstrip()
    if not stripped.endswith(")"):
        return text
    close = len(stripped) - 1
    open_at = stripped.rfind("(", 0, close)
    if open_at < 0 or stripped.find(")", open_at + 1, close) >= 0:
        return text
    return stripped[:open_at].rstrip()


def bare_name_key(value: Any) -> str:
    """epg_name_key with a TRAILING parenthetical removed first.

    A MEASUREMENT key, never a matching key. The loosening it performs is
    exactly the one F-EPG-7/F-EPG-10 refused to put in the matcher -- a
    parenthetical span can carry identity, and deleting unknown identity
    lands a row on the wrong guide channel silently -- so this function is
    read by one thing only: parse_xmltv's `addrNameConflicts`, which counts
    rows the ADDRESS strategy claimed where the guide ALSO declares a
    different channel under the row's own name with its country qualifier
    stripped.

    Why that counter exists. The address strategy's acceptance measured
    whether the NAME matcher had paired these rows with a DIFFERENT guide
    channel, and found 0. That measurement is blind by construction to the 40
    rows the name matcher left blank, and one of them is the pairing the
    product owner has since ruled on: `Pluto TV Reality (United States)` is
    held by the address at `69fa3faab9c0f0d444e64de3`, whose display-name is
    `Pluto TV Pride`, while the guide separately declares
    `5d8bf0b06d2d855ee15115e3` as `Pluto TV Reality` and no row claims it.
    The row's own stream URL carries Pride's id; its artwork names a third id
    the guide never declares; the neighbouring `VH1 Queens of Reality` row
    carries the same Pride id in both. The provider's own fields disagree
    about this row, and the ruling is that the ADDRESS wins, because it names
    the playout that will actually be opened. That ruling is not reopened
    here and this counter does not change any pairing. What it changes is
    that the case is now COUNTED instead of invisible: `addrNameConflicts` is
    1 on the frozen inputs, and a reader who sees it rise knows a second one
    exists without having to run an audit nobody scheduled.

    The fold (epg_name_text) comes BEFORE the strip, as the guide side has
    always ordered it, so the playlist side gives the same key for the same
    text (D-EPG-12); epg_name_key folds once more, which changes nothing.
    """
    return epg_name_key(strip_trailing_qualifier(epg_name_text(value)))


def normalize_text(value: Any) -> str:
    """Lower-case, fold Latin diacritics (precomposed via FOLD, decomposed via
    NFD + dropping U+0300-U+036F after an ASCII letter, then NFC so every
    other script recomposes), ASCII punctuation to one space (D-QA-08).
    Mirrors the model's decompose()/normalizeText byte for byte (NFD, not NFKD)."""
    return fold_text(value, _PUNCT)


def normalize_id_text(value: Any) -> str:
    """The id fold (mirror: Model.normalizeIdText). Identical to
    normalize_text except that `+` and `*` survive, because they are the
    difference between two channels rather than noise inside one. Never use
    it for search."""
    return fold_text(value, _ID_PUNCT)


def fold_text(value: Any, punct: "re.Pattern[str]") -> str:
    text = ("" if value is None else str(value)).lower()
    if not text.isascii():
        import unicodedata
        text = unicodedata.normalize("NFC", _LATIN_MARKS.sub(r"\1", unicodedata.normalize("NFD", text)))
    folded = "".join(FOLD.get(ch, ch) for ch in text)
    return punct.sub(" ", folded).strip(" ")


def search_key(name: Any, group: Any) -> str:
    key = normalize_text(name)
    grp = normalize_text(group)
    if grp:
        key = grp if not key else key + " " + grp
    return key


def fnv1a32(value: Any) -> str:
    text = "" if value is None else str(value)
    hash_ = 0x811C9DC5
    for byte in text.encode("utf-8"):
        hash_ ^= byte
        hash_ = (hash_ * 0x01000193) & 0xFFFFFFFF
    return "%08x" % hash_




# ---------------------------------------------------------- destinations
#
# D-SINK-40, D-SINK-41, D-SINK-42 (2026-10-29). Where provider data may send
# this machine. The owner's policy: a source the USER typed may reach any
# address on its first hop; a destination the PROVIDER chose -- a guide hint,
# a redirect hop, a logo, a channel URL -- may not reach a non-global
# address unless it is the user's own playlist host, in the same class.
# These functions classify; the policy is applied at connect time
# (DestinationPolicy, 03-io-playlist.py) and at parse time (02-sources.py).
# Mirrored by Model.hostClass / Model.hostKey, both run over the shared
# destinations fixture (dev branch).
#
# The table is EXPLICIT rather than ipaddress's `is_global`, measured on
# CPython 3.14.7: is_global answers True for multicast, for 64:ff9b::7f00:1
# (NAT64 over loopback), ::7f00:1 (IPv4-compatible), ::ffff:0:7f00:1
# (IPv4-translated), fec0::/10 (site-local), 4000::1 (unallocated) and
# 192.88.99.0/24 -- each a place a provider could aim at this machine or its
# LAN -- and its table moved between 3.12 and 3.13. Every address this table
# calls global, is_global calls global too (the python suite asserts it over
# the fixture), so it is never the more forgiving of the two.
_ADDRESS_TABLE_V4 = (
    ("0.0.0.0/8", "unspecified"),     # "this network"; 0.0.0.0 connects to this machine on Linux
    ("10.0.0.0/8", "private"),
    ("100.64.0.0/10", "shared"),      # CGNAT, and every Tailscale tailnet: other people's devices
    ("127.0.0.0/8", "loopback"),
    ("169.254.0.0/16", "link-local"),  # 169.254.169.254 among them
    ("172.16.0.0/12", "private"),
    ("192.0.0.0/24", "reserved"),
    ("192.0.2.0/24", "reserved"),
    ("192.88.99.0/24", "reserved"),
    ("192.168.0.0/16", "private"),
    ("198.18.0.0/15", "reserved"),
    ("198.51.100.0/24", "reserved"),
    ("203.0.113.0/24", "reserved"),
    ("224.0.0.0/4", "multicast"),
    ("240.0.0.0/4", "reserved"),      # 255.255.255.255 among them
)
_ADDRESS_TABLE_V6 = (
    ("::/128", "unspecified"),
    ("::1/128", "loopback"),
    ("64:ff9b:1::/48", "reserved"),
    ("100::/64", "reserved"),
    ("2001::/23", "reserved"),        # Teredo (2001::/32) among them
    ("2001:db8::/32", "reserved"),
    ("3fff::/20", "reserved"),
    ("5f00::/16", "reserved"),
    ("fc00::/7", "private"),          # ULA
    ("fe80::/10", "link-local"),
    ("fec0::/10", "private"),         # site-local, deprecated, still routed by some LANs
    ("ff00::/8", "multicast"),
)
# Compiled on first use into (version, first, last, class) integer ranges;
# a dict filled in place, as TLS_CONTEXT is, so no part needs `global`.
_ADDRESS_RANGES: dict[str, Any] = {}
_LOCALHOST_NAMES = ("localhost", "localhost.")
_DECIMAL_DIGITS = frozenset("0123456789")
_OCTAL_DIGITS = frozenset("01234567")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _address_ranges() -> list[tuple[int, int, int, str]]:
    if "ranges" not in _ADDRESS_RANGES:
        import ipaddress
        ranges = []
        for text, kind in _ADDRESS_TABLE_V4 + _ADDRESS_TABLE_V6:
            net = ipaddress.ip_network(text)
            ranges.append((net.version, int(net.network_address), int(net.broadcast_address), kind))
        _ADDRESS_RANGES["ranges"] = ranges
    return _ADDRESS_RANGES["ranges"]


def parse_ipv4_literal(host: str) -> int | None:
    """The 32-bit address a host NAMES when it is numeric IPv4 in any spelling
    the WHATWG URL parser and glibc's inet_aton accept, else None: one to four
    dot-separated parts, each decimal, `0x` hex or `0` octal, the last filling
    the bytes the others leave (`127.1`, `2130706433`, `0x7f000001`,
    `0177.0.0.1`), one trailing dot allowed (WHATWG's; glibc would look the
    dotted name up instead, so reading it as the address is the stricter
    choice). A part over 32 characters is no address, so provider text can
    never ask int() for a long conversion."""
    text = host[:-1] if host.endswith(".") and len(host) > 1 else host
    parts = text.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    numbers = []
    for part in parts:
        if part == "" or len(part) > 32:
            return None
        if part[:2] in ("0x", "0X"):
            if not set(part[2:]) <= _HEX_DIGITS:
                return None
            numbers.append(int(part[2:] or "0", 16))
        elif not set(part) <= _DECIMAL_DIGITS:
            return None
        elif len(part) > 1 and part[0] == "0":
            if not set(part) <= _OCTAL_DIGITS:
                return None
            numbers.append(int(part, 8))
        else:
            numbers.append(int(part))
    last = numbers.pop()
    if any(n > 255 for n in numbers) or last >= 256 ** (4 - len(numbers)):
        return None
    value = last
    for index, n in enumerate(numbers):
        value += n << (8 * (3 - index))
    return value


def parse_ip_literal(host: Any) -> Any:
    """An ipaddress object for a URL host that is a numeric literal -- IPv6
    with or without its brackets and with any `%zone` dropped, or IPv4 in
    any parse_ipv4_literal spelling -- else None (a name, or nothing)."""
    import ipaddress
    text = str(host or "").strip().lower()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    if text == "":
        return None
    if ":" in text:
        try:
            return ipaddress.IPv6Address(text.split("%", 1)[0])
        except ValueError:
            return None
    value = parse_ipv4_literal(text)
    return ipaddress.IPv4Address(value) if value is not None else None


def address_class(address: Any) -> str:
    """One of ADDRESS_CLASSES for an address (an ipaddress object or the
    numeric text a socket address carries, `%zone` and all). An IPv4-mapped
    (::ffff:a.b.c.d) or NAT64 (64:ff9b::/96) address is the class of the
    IPv4 address inside it; a 6to4 one (2002::/16) is that class when it is
    not global, else `reserved`; any other IPv6 outside 2000::/3 that the
    table does not name is `reserved`. Text that is no address is
    `reserved` too: what cannot be read is never global."""
    import ipaddress
    if not isinstance(address, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
        try:
            address = ipaddress.ip_address(str(address).split("%", 1)[0])
        except ValueError:
            return "reserved"
    return _classify_address(address)


def _classify_address(address: Any) -> str:
    """address_class over a parsed address; it recurses HERE, never through
    the public name, so the tests' one seam (which replaces address_class
    for one address) cannot reach an address wrapped inside another."""
    import ipaddress
    if address.version == 6:
        if address.ipv4_mapped is not None:
            return _classify_address(address.ipv4_mapped)
        value = int(address)
        if value >> 32 == 0x0064FF9B << 64:
            return _classify_address(ipaddress.IPv4Address(value & 0xFFFFFFFF))
        if address.sixtofour is not None:
            inner = _classify_address(address.sixtofour)
            return inner if inner != "global" else "reserved"
    value = int(address)
    for version, first, last, kind in _address_ranges():
        if version == address.version and first <= value <= last:
            return kind
    if address.version == 6 and value >> 125 != 0b001:
        return "reserved"
    return "global"


def host_class(host: Any) -> str:
    """The class of a URL host: a numeric literal's address_class,
    `loopback` for `localhost` and every `*.localhost` name (RFC 6761: they
    resolve to this machine), "" for any other name, whose class only a
    lookup can tell (the connect-time check makes that lookup; a stream
    host's lookup is mpv's, and the residual is stated in
    ARCHITECTURE-PLAYER)."""
    text = str(host or "").strip().lower()
    if text in _LOCALHOST_NAMES or text.endswith(".localhost") or text.endswith(".localhost."):
        return "loopback"
    if not may_be_ip_literal(text):
        return ""
    address = parse_ip_literal(text)
    return address_class(address) if address is not None else ""


def may_be_ip_literal(text: str) -> bool:
    """False only for text parse_ip_literal is sure to answer None for: no
    `:` (so no IPv6) and a last label -- one trailing dot dropped, as the
    parser drops it -- that is neither all decimal digits nor `0x`-led (so
    no IPv4 part). Every channel URL's host passes through host_class, and
    nearly every one is a name: this keeps a 10,000-channel parse inside its
    budget (engineering constraint 7) without importing ipaddress for them."""
    if ":" in text:
        return True
    label = text[:-1] if text.endswith(".") and len(text) > 1 else text
    last = label.rsplit(".", 1)[-1].lower()
    return last != "" and (last[:2] == "0x" or set(last) <= _DECIMAL_DIGITS)


def host_key(host: Any) -> str:
    """What "the same host" compares: a numeric literal as its address
    (`127.1` and `127.0.0.1` are one host) -- IPv4 dotted, IPv6 as eight
    four-digit hex groups composed here from the integer, because both of
    ipaddress's own spellings of an IPv4-mapped address (str() and
    .exploded) end in a dotted quad on CPython 3.14 and did not before 3.13;
    Model.hostKey composes the same eight groups -- a name case-folded with
    one trailing dot dropped. Never a port and never userinfo."""
    text = str(host or "").strip().lower()
    address = parse_ip_literal(text)
    if address is not None:
        if address.version == 4:
            return str(address)
        value = int(address)
        return ":".join("%04x" % ((value >> (16 * (7 - index))) & 0xFFFF) for index in range(8))
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return text[:-1] if text.endswith(".") else text
