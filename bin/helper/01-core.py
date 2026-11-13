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



def json_decode(text: str) -> Any:
    """json.loads for every document the helper reads. D-STATE-7: the C
    decoder raises RecursionError, which is no ValueError, once a document
    nests past what its stack takes (about 50,000 levels), and every reader
    here catches ValueError: a state or cache file nested that deep ended its
    verb `internal`. It is damage like any other text that does not parse, so
    it is raised as the ValueError those readers already handle."""
    try:
        return json.loads(text)
    except RecursionError:
        raise ValueError("JSON nested too deeply") from None


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
            found = json_decode(fh.read()).get("version")
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
# D-SINK-94 (2026-11-11): the schemes a refusal may NAME. The three
# scheme refusals (a source, a stream to play, a redirect) quoted whatever
# came before the URL's first `:`, and for an address typed without its
# `http://` -- `user:pass@host/list.m3u` -- that is the username, which
# reached the reply, the status file and the stderr line. A scheme not on
# this list is refused without its name (scheme_phrase).
NAMED_SCHEMES = frozenset(STREAM_SCHEMES | SOURCE_SCHEMES | {
    "ftp", "ftps", "sftp", "data", "smb", "rtmpe", "rtmpt", "mmst", "tcp", "tls", "magnet", "acestream"})


def scheme_phrase(scheme: Any) -> str:
    """` 'ftp'` -- a space and the quoted scheme -- for a scheme on
    NAMED_SCHEMES, compared lower-cased; "" for any other text, the empty
    one included (D-SINK-94)."""
    name = str(scheme or "").lower()
    return " '%s'" % name if name in NAMED_SCHEMES else ""

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
# D-SINK-47, D-SINK-48 (lane-p2a, 2026-10-29): how the shell hands every verb
# the arguments that must not sit on a world-readable /proc/<pid>/cmdline --
# the source's cache directory and the keys in it (a 32-bit hash of the
# credentialed playlist URL on every source added before this release), a
# channel's `--id` (a `u:` id hashes a stream URL), a zap-ring `--scope`
# (a provider's group name) and the user's `--mpv-arg` tokens (where a proxy
# password goes). The argv carries ARGS_FLAG in their place, and they arrive
# as a JSON list of strings in ARGS_ENV, read once by helper_arguments before
# argparse sees anything and appended after the public argv. The stub has
# shielded the process before this line runs, so the environment is closed to
# every other uid from exec and to this uid from the shield on, as the URL's
# is (D-SINK-9). Mirror of Model.HELPER_ARGS_ENV / Model.HELPER_ARGS_FLAG.
ARGS_ENV = "OMARCHY_IPTV_ARGS"
ARGS_FLAG = "--args-from-env"
# The kernel's own bound on one environment string (MAX_ARG_STRLEN, 32 pages):
# nothing longer can have been handed to an exec, so a longer value is not ours.
ARGS_ENV_MAX = 131072
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
# D-SINK-57 (owner, 2026-10-29): and the playlist URL's port (its scheme's
# default when it names none), because on LOOPBACK the playlist's own host is
# host AND port (own_host_match).
HOME_PORT_ENV = "OMARCHY_IPTV_PLAYLIST_PORT"
ORIGIN_USER = "user"
ORIGIN_PLAYLIST = "playlist"
# Every class address_class answers. "global" is the only one a destination
# the provider chose may reach unconditionally; "unresolved" is never an
# address's class, only a proxied target this machine could not look up.
ADDRESS_CLASSES = ("global", "loopback", "private", "shared", "link-local",
                   "unspecified", "multicast", "reserved")
# The version of the rules a cache was WRITTEN under (playlist-status.json
# `destinationRules`; Model.DESTINATION_RULES is the same number). 1 is the
# destination rules (D-SINK-41: a cache before them holds channels nothing
# checked); 2 is the attribute grammar (D-SINK-80: a cache before it can hold
# a name, a group or a guide hint cut inside a URL, and the credential's tail
# as a title); 3 is the stream host-name rules, D-SINK-87, D-SINK-88, D-SINK-89
# and D-SINK-91, with D-SINK-90's reading of a query name (a cache before them
# can hold a channel whose address names a host the player would read in a
# form no host name or port may take, an IPv6 zone the player would cut into
# another host, a host of one label from a playlist that is not local, or a
# listening parameter spelled with an encoded NUL, which player_target then
# refuses at every play); 4 is the D-SINK-95 and D-SINK-96 reading of a URL
# and a credential token in free text (a cache before it can hold a name or a
# group cut, or split at a `;`, inside a URL whose mark a control, a
# zero-width or combining character, a fullwidth colon or a slash look-alike
# breaks, or inside a scheme-less `user:pass@host`, and a tvg-id holding one,
# each of which every sink then prints in part). A cache written under an
# older version, or carrying none, is refetched once, whatever its age, when
# its source is the active one: the active source's at the next start, each other source's at
# its next swap, and each shows its old cache until that refetch lands -- or,
# if it fails, until a later one succeeds (Model.cacheBeforeDestinationRules,
# read by Service.qml's applyFreshness for the active cache only).
DESTINATION_RULES = 4
# The same for a guide window (its meta line's `guideRules`): 1 is the fold
# that keeps a URL's run whole (D-SINK-79: a window written before it can hold
# a title or a detail split inside a URL, which every sink prints as the
# username and the password's tail); 2 is the D-SINK-95 and D-SINK-96
# reading (a window before it can hold a title or a detail folded, cut or left
# unredacted inside a URL whose mark an odd character breaks, or inside a
# scheme-less `user:pass@host`, which clean_detail's old `://` guard stored
# as it came). A window written under an older
# version, or carrying none, is refetched at the source's next fetch run,
# whatever its age (needs_refetch): the playlist's stamp above refetches the
# playlist, and the guide run beside it read the old window as fresh. A
# refetch that fails leaves the old window in use, stale and reported as a
# failure, until one succeeds; `--now-only` never refetches.
GUIDE_RULES = 2
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
# D-SRC-77: `\Z`, not `$`. Every reader uses `.match`, and Python's `$` also
# matches before a final line feed, so a key ending in one was kept here and
# refused by the shell (Model.isSourceKey), which then dropped the record.
SOURCE_KEY_RE = re.compile(r"^[0-9a-f]{8}(-[0-9]{1,3})?\Z")
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
# re-read from every word boundary; the scan is anchored on a mark's slashes
# now (next_url, D-SINK-95) and these are the parts of that pattern it still
# needs. The tail ends at the six
# delimiters alone (R32a'''; it was that pattern's `[^\s'"<>]+` until
# 2026-10-22, and the 30-point union for one round after that). The `\b`
# is gone (D-SINK-74, 2026-11-04): a scheme glued to a word character is a
# URL all the same, as it always was to Model.redactUrls.
_URL_TAIL_RE = re.compile("[^" + URL_DELIMITER_CHARS + "]+")
# The sentence punctuation redact_urls strips off a run's end and puts back
# after the host; Model.trailingPunctuationLength has the same set. A `]` is
# kept when the run holds a `[` (an IPv6 literal).
_TRAILING_PUNCTUATION = ".,;:!?)]'\"<>"
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
# D-STATE-2: the whitespace clean_name takes off a name, enumerated as the
# folds' class below enumerates it (_PUNCT, D-ID-5): the 29 code points
# CPython 3.14's str.isspace() holds, so it answers as the bare strip() did
# and no `n:` id, which is hashed from clean_name's answer, moved. A U+FEFF
# at a name's edge stays, as it always has here. Every other strip the model
# mirrors takes URL_SPACE_CHARS, the reader's class above and
# Model.stripSpace's, and so does Model.cleanName, for what is shown. The
# channel-ids fixture's foldSpace pins this list.
CLEAN_NAME_SPACE = "".join(map(chr, [*range(0x09, 0x0e), *range(0x1c, 0x21), 0x85, 0xa0, 0x1680,
                                *range(0x2000, 0x200b), 0x2028, 0x2029, 0x202f, 0x205f, 0x3000]))
# make_channel's last-resort display name, and the pattern that recognises one
# after normalize_id_text. Built from the same constant so the two cannot drift:
# engineering rule 13 (dev branch), two things joined by a call rather than by a name.
GENERATED_NAME_WORD = "Channel"
GENERATED_NAME_FORMAT = GENERATED_NAME_WORD + " %d"
_GENERATED_NAME = re.compile(r"^" + GENERATED_NAME_WORD.lower() + r" [0-9]+$")
_CONTROL_WS = re.compile(r"[\s\x00-\x1f\x7f]+")
# Mirrors Model.sanitizeInput: C0 controls, DEL and C1 controls are dropped.
_CONTROL_CHARS = re.compile("[\x00-\x1f\x7f-\x9f]")
# A URL's `://` as a sink that deletes _CONTROL_CHARS' class before it
# redacts reads one (F-SINK-16): a `:` and two `/`, with any of that class
# between them. cut_free_text (D-SINK-75) and split_groups (D-SINK-78) look
# for it, so the two agree on where a URL starts.
_URL_MARK = re.compile(":[\x00-\x1f\x7f-\x9f]*/[\x00-\x1f\x7f-\x9f]*/")


def url_mark_start(text: str, pos: int = 0) -> int:
    """Where `_URL_MARK.search(text, pos)` starts, or -1 when it finds none.

    The same answer at native cost on the usual text (D-PERF-13). The mark's
    filler is _CONTROL_CHARS' class, so a mark that is not exactly a `://`
    holds one of those characters. In an ASCII str they are exactly the
    non-printable ones (C0 and DEL; it has no C1). So when the first `://`
    at or after `pos` has no such character before it (or there is no `://`
    and none at all), no other mark can start first: one that did would
    start at a `:` before the `://`, and with no control after that `:` it
    would be a `://` itself, or would need a `/` or a control where the
    `://`'s own `:` stands. str.find and isprintable run in C. Any other
    text is searched with the pattern. On a run of `:` with no `//` after
    any of them the pattern made one failed attempt at each `:`
    (`<n>:::...;/`, 512 characters a channel); this makes none. `pos` is
    never negative here: str.find would count it from the end, where the
    pattern starts at 0."""
    if text.isascii():
        found = text.find("://", pos)
        before = text[pos:found] if found >= 0 else (text[pos:] if pos else text)
        if before.isprintable():
            return found
    mark = _URL_MARK.search(text, pos)
    return -1 if mark is None else mark.start()


# D-SINK-95 (2026-11-11): where a free-text redactor reads a URL, for the
# DISPLAY path. _URL_MARK above is the fetch side's mark, and it stays
# narrow (hint_first_entry and absorbed_attribute read it); everything a
# redactor prints is read by next_url below, which both redactors,
# fold_space and the parsers share. Until then a credential was found only
# behind an unbroken `scheme://`: any character that is not a scheme
# character, between the scheme and its `:` or inside the `://`, hid the
# whole URL from both redactors -- a control (which the window title and the
# notification delete before they redact, so they read a URL where the row
# did not), a character drawn with no width, a combining mark, a fullwidth
# colon or a slash look-alike -- and the guide row, the channel wall, the
# bar, the accessible names, the IPC replies and the helper's stderr printed
# the username and the password. The owner's decision (2026-11-08): any odd
# character before or inside the `//` is a URL's mark, false positives
# accepted. Model.urlAt is the mirror, over UTF-16 code units; this reads
# code points, and every rule below works on runs, so an astral character
# (two surrogates there, one code point here) reads the same in both. The
# shared url-mark fixture holds both to one answer.
#
# The classes, none of them a Unicode table:
#   SCHEME     [A-Za-z0-9+.-]; a scheme starts at an ASCII letter.
#   SLASH      `/`, or one of SLASH_ALIKE_CHARS.
#   CROSSABLE  everything outside U+0020..U+007E: the controls, every
#              non-ASCII character, a lone surrogate.
#   FILLER     CROSSABLE but no slash look-alike.
#   STAND_IN   FILLER above U+009F that is not in the reader's space union
#              (URL_SPACE_CHARS): a character that stands in for the colon.
# The deleted controls (_CONTROL_CHARS) are no STAND_IN, because the sinks
# that delete them would read no colon there, and the spaces are none
# because `ESPN<NBSP>//<NBSP>HD` is a name.
#
# The slash look-alikes a provider's text draws as `/`: each reads as a
# slash, and the host a redactor prints is cut at the first of them
# (run_host_parts). Model.SLASH_ALIKE_CODES is the mirror. U+30CE, U+4E3F
# and U+2CC6 are left out: they are common letters.
SLASH_ALIKE_CHARS = "".join(map(chr, (0x1735, 0x2041, 0x2044, 0x2215, 0x2571, 0x27CB,
                                      0x29F8, 0x2F03, 0x3033, 0x31D3, 0xFF0F)))
# The reader's space union above U+009F: FILLER, never a STAND_IN. Derived
# from URL_SPACE_CHARS, never retyped.
_SPACE_ABOVE_C1 = "".join(ch for ch in URL_SPACE_CHARS if ch > "\x9f")
_SLASH_ALIKE = re.compile("[" + SLASH_ALIKE_CHARS + "]")
_MARK_STAND_IN = re.compile("[^\x00-\x9f" + _SPACE_ABOVE_C1 + SLASH_ALIKE_CHARS + "]")
# A pair of SLASHes with only FILLER between them, behind a run of `:` and
# FILLER (the mark's P) that a SCHEME character or a look-alike precedes:
# the only shape a mark the reading accepts can take, since the scheme walk
# needs a letter before P, or a look-alike to cross. Since the review of
# 4d13d71 it takes only the candidates the reading could accept, so a run
# of them it rejects costs one native search and not one Python step each
# (`x:@` and `a!.<U+200B><U+2215><U+2215>` repeated took 0.6 s a million
# characters in next_url, read whole by parse_attrs' quoted value): the
# stretches of P between its colons, and the FILLER between the slashes,
# each hold at most one WIDE code point (_WIDE_STRETCH, the caps next_url
# also asks), and P stands after a SCHEME segment that holds a letter
# (matched from its last letter), after a letterless one a CROSSABLE
# character precedes, or after a look-alike that a SCHEME character or a
# deleted control precedes -- the only segments a scheme walk can leave
# with a letter. Each branch opens with a character class, so the engine
# skips to the next possible lead natively. The same URLs: the url-mark
# suite (dev branch) holds next_url to the reading stated one character at
# a time, which asks every pair.
_WIDE_STRETCH = "[\x00-\x1f\x7f-\x9f]*+(?:[^\x00-\x9f" + SLASH_ALIKE_CHARS + "][\x00-\x1f\x7f-\x9f]*+)?+"
# The run of `:`, FILLER and SLASH (every character but printable ASCII, and
# `:` and `/`) a mark may go on through: from a bare value's end
# (parse_attrs, D-SINK-95), and from next_url's `stop`.
_MARK_REACH = re.compile(r"[^ -.0-9;-~]*")
# Two WIDE FILLER code points with only deleted controls between them: a
# stretch no mark may hold (next_url's bound past its `stop`).
_FILLER_WIDE_PAIR = re.compile("[^\x00-\x9f" + SLASH_ALIKE_CHARS + "][\x00-\x1f\x7f-\x9f]*+[^\x00-\x9f"
                               + SLASH_ALIKE_CHARS + "]")
_URL_CANDIDATE = re.compile("(?:[A-Za-z][0-9+.\\-]*+|[0-9+.\\-](?<=[^ -~][0-9+.\\-])[0-9+.\\-]*+|[" + SLASH_ALIKE_CHARS
                            + "](?<=[A-Za-z0-9+.\\-\x00-\x1f\x7f-\x9f][" + SLASH_ALIKE_CHARS + "]))((?=[^ -9;-~"
                            + SLASH_ALIKE_CHARS + "])" + _WIDE_STRETCH + "(?::"
                            + _WIDE_STRETCH + ")*+)[/" + SLASH_ALIKE_CHARS + "]" + _WIDE_STRETCH + "[/"
                            + SLASH_ALIKE_CHARS + "]")
# The run of SCHEME and CROSSABLE characters that ENDS at a given position,
# by the window match _SCHEME_RUN_RE takes (D-PERF-6): the stretch a scheme
# walk may cross.
_CROSS_SPAN_RE = re.compile(r"(?:.*[ -*,/:-@\[-`{-~])?", re.S)
_LAST_LETTER = re.compile(".*[A-Za-z]", re.S)
_LAST_CROSSABLE = re.compile(".*[^ -~]", re.S)
_ASCII_LETTER = re.compile("[A-Za-z]")
_CROSSABLE = re.compile("[^ -~]")
# D-SINK-95's caps (the review of cbd6679, 2026-11-12). A code point above
# U+009F is WIDE; the deleted controls (U+0000..U+001F, U+007F..U+009F)
# never are, so the sinks that delete them read the same marks. Each stretch
# the reading crosses holds at most ONE wide code point: a FILLER stretch of
# a mark's P between its colons, the FILLER between its slashes, and each
# CROSSABLE run the scheme walk crosses. Without the caps P ran back over a
# whole space-less sentence to its nearest ASCII word, and the text between
# the slashes could be any number of characters, so `CCTV5...<CJK>:<CJK>/
# <CJK>/<CJK>` printed only its last word in both mirrors; with them that
# reading needs two odd code points side by side, which no fuzz input the
# round measured holds. Two wide code points with only deleted controls
# between them are one stretch too wide (_WIDE_PAIR). What the caps leave,
# stated: one odd code point a stretch still marks a URL, false positives
# the owner accepted (2026-11-08) -- a name with one beside its `//`
# (`ESPN<U+200B>//<U+200B>HD` prints `<U+200B>HD`), a list of single CJK,
# Korean or Cyrillic characters behind an ASCII word
# (`Audio:<U+56FD>/<U+7CA4>/<U+82F1>` prints `<U+82F1>`, `RU:<U+0420>/
# <U+0421>/<U+0424>` prints `<U+0444>`), and a fullwidth colon glued to CJK
# prose (`file<U+FF1A>//<U+201D>...`), which prints the rest of the
# paragraph, to the next ASCII space, as a lowercased host (the review of
# 4d13d71).
_WIDE_PAIR = re.compile("[^\x00-\x9f][\x00-\x1f\x7f-\x9f]*+[^\x00-\x9f]")
# Where a scheme walk cannot pass: a printable character that is neither a
# scheme character nor CROSSABLE, or the second of two wide code points in
# one crossable run (cut_free_text's bound on the URL it asks for).
_WALK_BARRIER = re.compile("[ -*,/:-@\\[-`{-~]|[^\x00-\x9f][\x00-\x1f\x7f-\x9f]*+[^\x00-\x9f]")
# D-SINK-96: a token that holds an ASCII `:` with an ASCII `@` after it,
# from a space (or the text's start) to the next space: the shape of a
# `user:pass@host` with no scheme in front of it, and the tokens
# credential_spans asks.
_CREDENTIAL_TOKEN = re.compile("(?<![^ ])[^ :]*+:[^ @]*+@[^ ]*+")
# The code points credential_spans counts between a token's `:` and its
# `@`: above U+009F and no slash look-alike (D-SINK-96's cap, the review of
# cbd6679); _LAST_COUNTED is the last one before a given position.
_LAST_COUNTED = re.compile(".*[^\x00-\x9f" + SLASH_ALIKE_CHARS + "]", re.S)
# The code points the cap counts on a credential's PASSWORD side, between its
# `:` and its `@` (the review of 4d13d71): COUNTED code points of the scripts
# written without spaces, where a sentence before a handle or an address is
# one token -- Han, the CJK symbols and kana, Hangul, Thai, Lao, Myanmar,
# Khmer, the halfwidth and fullwidth forms, and every astral code point --
# with the three slash look-alikes inside these ranges (U+2F03, U+3033,
# U+FF0F) cut out, as COUNTED cuts them. Counting every COUNTED code point
# there let two accented letters, two NBSP or two euro signs in a Latin,
# Cyrillic or Greek password print the whole credential at every sink of
# both mirrors (`News j<U+00FC>rgen:m<U+00FC><U+00DF>ig@cdn.test/...`). The
# username side still counts every COUNTED code point (_LAST_COUNTED).
# Model.SPACELESS_RANGES is the mirror, held equal over every code point.
SPACELESS_RANGES = (
    (0x0E00, 0x0EFF), (0x1000, 0x109F), (0x1100, 0x11FF), (0x1780, 0x17FF), (0x2E80, 0x2F02), (0x2F04, 0x2FDF),
    (0x3000, 0x3032), (0x3034, 0x30FF), (0x3130, 0x318F), (0x31F0, 0x31FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF),
    (0xA960, 0xA97F), (0xAC00, 0xD7AF), (0xD7B0, 0xD7FF), (0xF900, 0xFAFF), (0xFF00, 0xFF0E), (0xFF10, 0xFFEF),
    (0x10000, 0x10FFFF))
_LAST_SPACELESS = re.compile(".*[" + "".join(chr(a) + "-" + chr(b) for a, b in SPACELESS_RANGES) + "]", re.S)
# fold_space's class inside a URL's scheme and mark: the line and
# paragraph separators, which become RUN_REPLACEMENT there.
_MARK_SEPARATORS = re.compile("[\U00002028\U00002029]")


def _run_start(pattern: "re.Pattern[str]", text: str, low: int, at: int) -> int:
    """Where `pattern`'s window match puts the start of the run that ends at
    `at` (_SCHEME_RUN_RE, _CROSS_SPAN_RE), never below `low`. The window
    doubles until the start is strictly inside it, so the work is
    proportional to the run, not to the text (F-SINK-11)."""
    window = 64
    while True:
        lo = at - window
        if lo < low:
            lo = low
        start = pattern.match(text, lo, at).end()
        if start > lo or lo == low:
            return start
        window *= 2


def _scheme_start(text: str, at: int, low: int) -> int:
    """D-SINK-95: where the scheme of a mark whose P starts at `at` starts,
    or -1 when there is none, never below `low`. The SCHEME segment ending
    at `at` starts it at its first letter when it holds one (D-SINK-74's
    pins stay exact: a letter-holding segment is never crossed); when it
    holds none and a CROSSABLE run stands before it, the walk crosses that
    run and asks the next segment, so `http<U+0001>1://` reads `http1` as
    the deleting sinks do. A run that holds two WIDE code points is not
    crossed (the cap, _WIDE_PAIR): the walk ends there with no scheme. In
    one pass: the stretch the walk may cross is the run of SCHEME and
    CROSSABLE characters ending at `at`, and the scheme is the first letter
    of the segment that holds its last letter, unless a run too wide stands
    between that letter and `at`."""
    start = _run_start(_SCHEME_RUN_RE, text, low, at)
    first = _ASCII_LETTER.search(text, start, at)
    if first is not None:
        return first.start()
    if start == low or " " <= text[start - 1] <= "~":
        return -1
    span = _run_start(_CROSS_SPAN_RE, text, low, at)
    last = _LAST_LETTER.match(text, span, at)
    if last is None:
        return -1
    letter = last.end() - 1
    # The walk crosses everything between that letter's segment and `at`,
    # and a pair of wide code points there is a run it cannot cross.
    if _WIDE_PAIR.search(text, letter + 1, at) is not None:
        return -1
    crossed = _LAST_CROSSABLE.match(text, span, letter)
    return _ASCII_LETTER.search(text, span if crossed is None else crossed.end(), letter + 1).start()


def _slash_at_or_after(text: str, at: int, hi: int) -> int:
    """The first SLASH (`/` or a look-alike) in [at, hi), or `hi`: one
    native search for each, the look-alike's no further than the `/`."""
    slash = text.find("/", at, hi)
    if slash < 0:
        slash = hi
    alike = _SLASH_ALIKE.search(text, at, slash)
    return slash if alike is None else alike.start()


def _stop_end(text: str, stop: int) -> int:
    """Where next_url's search for candidates ends when it is given `stop`:
    just past the run's second SLASH, or its only one, or `stop`, where the
    run is that of `:`, FILLER and SLASH that starts at `stop` (_MARK_REACH),
    or the end of the first pair of wide FILLER code points in that run
    (_FILLER_WIDE_PAIR) when that is sooner, and never before `stop` + 1.
    A function of the text and `stop` alone, so a UrlReading asks it once
    (the review of 2942e41: asked once a next_url call, with the slashes
    searched for from `stop` to the text's end before the run bounded them,
    the cut's credential reading cost one pass over the rest of the text for
    each URL in its window, 53.9 s on one description of a million
    characters through clean_detail). The run is matched first and the
    slashes are searched for only inside it, which is the same end, since it
    is never past the run's: so a text with no slash after `stop` costs the
    run, and a run of FILLER as long as the text costs one pass, once a
    reading.

    When the run holds fewer than two SLASHes the end is the one it holds,
    or `stop` (the review of e038d58, the lead's call under the owner's
    standing authority of 2026-11-09): a candidate whose P starts at or
    before `stop` and whose mark runs past it has every character from
    `stop` to its mark's end in the run, so it ends at the run's second
    SLASH when `stop` stands in its P, and at the run's first when `stop`
    stands between its slashes (`ab:/<U+200B>/x` stopped at 4 is one); with
    no SLASH in the run none runs past `stop`. Ending at the run's end
    instead, the reading's last next_url call searched the whole run for
    candidates it could only refuse: a window of URLs before a tail of `:`
    cost 172.6 ms at 1M characters through clean_detail, and costs the run's
    one match now (40.6 ms). The lead's call named `stop` + 1 whenever the
    run holds no second SLASH, which loses the candidate `stop` stands
    inside; the first SLASH is the end that keeps it (StopEndTests holds
    both; the review's identity sweep, 120,000 next_url calls against
    2942e41, finds no difference with either)."""
    reach = _MARK_REACH.match(text, stop).end()
    first = _slash_at_or_after(text, stop, reach)
    if first == reach:
        return stop + 1
    second = _slash_at_or_after(text, first + 1, reach)
    end = (first if second == reach else second) + 1
    pair = _FILLER_WIDE_PAIR.search(text, stop, end)
    return max(stop + 1, end if pair is None else pair.end())


def next_url(text: str, search: int, resume: int, plain: bool | None = None,
             stop: int | None = None, stop_end: int | None = None) -> tuple[int, int, int, int] | None:
    """D-SINK-95: the first URL the redactors read in `text` at or after
    `resume`, as (scheme start, mark start, mark end, run end), or None.

    The reading. Each pair of SLASHes whose FILLER between them holds at
    most one WIDE code point, left to right, is asked: P is the run of `:`
    and FILLER ending at the pair's first slash, never reaching below
    `resume`, and the pair is a MARK when P holds a `:` or a STAND_IN and
    each FILLER stretch of P between its colons holds at most one WIDE code
    point (the caps, _WIDE_STRETCH in _URL_CANDIDATE; the review of
    cbd6679), and only a pair whose P stands where a scheme walk can leave
    with a letter is a candidate at all (_URL_CANDIDATE, the review of
    4d13d71; exact, since every other walk finds none). The mark starts at
    P and ends after the pair's second slash. Its scheme is found by
    _scheme_start, never below the later of `resume` and the start of the
    last P whose walk found none (the dead bound, which keeps the walk
    linear once look-alikes are crossable and changes no answer); and a
    walk with no ASCII letter between that bound and P finds none, so it is
    not taken, and no candidate whose P starts before the next letter is
    asked (the review's shortcut, exact for the same reason). A mark with
    no scheme is no URL, and the search goes on. The run is from the mark's
    end to the first of the six delimiters (URL_DELIMITER_CHARS, R32a'''
    unchanged), or the end, and it may be empty: an empty run is a URL in
    both mirrors since the review of cbd6679, where the model printed
    `[url]` and redact_urls left the text alone, so the plain, deleting and
    folded sinks read different tokens around one, and a walk that found a
    scheme for an empty run moved no bound, which was quadratic on `a` and
    `<U+200B><U+2215><U+2215><TAB>` repeated (13 s at 40,001 characters).
    The scheme is found before the run is read: reading the run first was
    quadratic on `1://` repeated. What a run a TAB, LF, VT, FF or CR ends
    leaves, empty or not, stated (R32a''', D-SINK-34; the review of
    4d13d71): the plain sinks print the text after it as text, so a path
    or query credential behind an empty run prints there
    (`http://<TAB>cdn.test/live/qqqqqq/...`) unless an `@` after it makes
    the token a credential (_eligible_colon); and the sinks that delete
    controls (the window title, the notification) join the run to the text
    after it and print that text's head as the host, credential text or not
    (`News a://<TAB>qqqqqq:///x HD` prints `News qqqqqq HD` there, where
    the plain sinks print `[url]` twice), or, when the joined run takes the
    credential's `:` and `@` as its own userinfo, the token is no
    credential there and the URLs before it in the token print their hosts,
    which are the username's text (the review of 2942e41:
    `News http://q.qqqa<U+2215>://<TAB>qq:zzzzzz@cdn.test/live/1.ts HD`
    prints `News http://q.qqqa HD` there, where the plain sinks withhold
    the token).

    `plain` is whether the text is printable ASCII (asked once a text by
    the caller, or here): there no FILLER, STAND_IN or look-alike can
    occur, so a mark is a run of `:` before `//` and the walk never
    crosses, which str.find reads at native cost. The same answer either
    way; the redaction-cost corpus holds it. `search` is where candidates
    are looked for, `resume` the low bound; every caller passes the same.
    `stop`, when given, ends the search at the first mark that starts past
    it: cut_free_text asks only for a URL whose scheme starts before its
    limit, and no such URL has its mark past a walk barrier after it.
    `stop_end` is _stop_end(text, stop) when the caller holds it (a
    UrlReading asks it once a reading); without it, it is asked here."""
    if plain is None:
        plain = text.isascii() and text.isprintable()
    if plain:
        j = text.find("://", search)
        while j >= 0:
            mark = j
            while mark > resume and text[mark - 1] == ":":
                mark -= 1
            if stop is not None and mark > stop:
                return None
            start = _run_start(_SCHEME_RUN_RE, text, resume, mark)
            first = _ASCII_LETTER.search(text, start, mark)
            if first is not None:
                tail = _URL_TAIL_RE.match(text, j + 3)
                return first.start(), mark, j + 3, j + 3 if tail is None else tail.end()
            j = text.find("://", j + 1)
        return None
    dead = resume
    # With `stop`, the candidates are searched for no further than
    # _stop_end: just past the second SLASH of the run of `:`, FILLER and
    # SLASH that starts at it (_MARK_REACH), or past its only one, or past
    # `stop` when it holds none, or the end of the first pair of wide FILLER
    # code points in that run (_FILLER_WIDE_PAIR) when that is sooner. A
    # candidate whose P starts at or before `stop` ends before `stop` or at
    # one of those slashes, inside that run, holding no such pair (the
    # caps), so the search finds it, and the first one it finds past `stop`
    # ends the reading as it would have. Without that end the search
    # read on to the text's end once candidates the reading rejects were no
    # longer candidates (the review of 4d13d71).
    end = len(text)
    if stop is not None:
        end = _stop_end(text, stop) if stop_end is None else stop_end
    asked = -1
    first = 0
    while True:
        if asked != dead:
            # A walk finds a scheme only from an ASCII letter at or after its
            # bound, so no candidate whose lead stands before the first such
            # letter is asked, and with none the reading is done (the
            # review's shortcut, asked before the search since the review of
            # 4d13d71: once _URL_CANDIDATE stopped taking the candidates no
            # walk accepts, the search read on to the text's end where the
            # first rejected one had ended it). Asked again only when the
            # bound moves, so the stretches it reads are disjoint.
            asked = dead
            letter = _ASCII_LETTER.search(text, dead, end)
            if letter is None:
                return None
            first = letter.start()
        found = _URL_CANDIDATE.search(text, max(search, first), end)
        if found is None:
            return None
        mark, slash = found.span(1)
        mark_end = found.end()
        if stop is not None and mark > stop:
            return None
        # A look-alike that closed this candidate may lead the next one, so
        # the search resumes at P, not after the pair.
        search = mark
        if text.find(":", mark, slash) < 0 and _MARK_STAND_IN.search(text, mark, slash) is None:
            continue
        # The caps (a WIDE pair in a stretch of P, or between the slashes)
        # are _URL_CANDIDATE's own since the review of 4d13d71.
        start = _scheme_start(text, mark, dead)
        if start < 0:
            dead = mark
            continue
        tail = _URL_TAIL_RE.match(text, mark_end)
        return start, mark, mark_end, mark_end if tail is None else tail.end()


def url_mark_any(text: str, pos: int = 0) -> int:
    """The first mark at or after `pos` that either reading protects: the
    smaller of url_mark_start (the narrow _URL_MARK) and the mark start of
    the first URL next_url finds there (no run needed), or -1. On printable
    ASCII it is url_mark_start itself (a wide mark there is a narrow one
    behind a scheme). cut_free_text, split_groups, parse_attrs and
    make_channel ask it, so no parser hands a redactor half a URL the
    D-SINK-95 reading finds."""
    if text.isascii() and text.isprintable():
        # url_mark_start's own answer there, without its second look at the
        # text: on printable ASCII its mark is exactly a `://` (D-PERF-13).
        return text.find("://", pos)
    narrow = url_mark_start(text, pos)
    url = next_url(text, pos, pos, False)
    if url is None:
        return narrow
    return url[1] if narrow < 0 else min(narrow, url[1])


def redaction_can_change(text: str) -> bool:
    """Whether redact_urls can rewrite `text`: it holds a SLASH (a mark
    needs two), or both an ASCII `:` and `@` (a D-SINK-96 token needs
    them). Exact, so a caller may skip the call on False (clean_detail);
    Model.redactionCanChange is the mirror."""
    if "/" in text or (":" in text and "@" in text):
        return True
    return not text.isascii() and _SLASH_ALIKE.search(text) is not None


def _trailing_cut(run: str) -> int:
    """How much of `run` to keep before its sentence punctuation
    (_TRAILING_PUNCTUATION), which the redactors put back after what they
    print; a `]` is kept when the run holds a `[` (an IPv6 literal)."""
    bracket = "[" in run
    keep = len(run)
    while keep > 0 and run[keep - 1] in _TRAILING_PUNCTUATION and not (bracket and run[keep - 1] == "]"):
        keep -= 1
    return keep


class UrlReading:
    """next_url's URLs of `text` from `low`, in order, read only as far as a
    caller asks (need): credential_spans asks which URL holds a position,
    and cut_free_text asks no further than the token it judges. `starts`
    holds each URL's scheme start, for bisect. `stop`, when given, ends the
    reading at the first mark past it, as next_url's own `stop` does: a
    caller that judges only [low, reach) passes the first walk barrier at or
    after `reach`, since no URL whose mark starts past one has its scheme
    start before it (cut_free_text; the review of 4d13d71 measured its
    credential's reading going on to the text's end, 2.1 s on a 4 MB
    description)."""

    def __init__(self, text: str, low: int, plain: bool | None = None, whole: bool = False,
                 stop: int | None = None) -> None:
        self.text = text
        self.low = low
        self.plain = text.isascii() and text.isprintable() if plain is None else plain
        # Passed to next_url: the reading ends at the first mark that starts
        # past it (cut_free_text, the review of 4d13d71). Its search end is
        # asked once, here, and handed to every next_url call (the review of
        # 2942e41: asked a call, it read the rest of the text once for each
        # URL in the cut's window).
        self.stop = stop
        self.stop_end = None if stop is None or self.plain else _stop_end(text, stop)
        self.urls: list[tuple[int, int, int, int]] = []
        self.starts: list[int] = []
        self.done = False
        if whole:
            self.need(len(text))

    def need(self, pos: int) -> None:
        """Read until a URL starts past `pos`, or none is left."""
        urls = self.urls
        while not self.done and (not urls or urls[-1][0] <= pos):
            low = urls[-1][3] if urls else self.low
            url = next_url(self.text, low, low, self.plain, self.stop, self.stop_end)
            if url is None:
                self.done = True
            else:
                urls.append(url)
                self.starts.append(url[0])

    def holding(self, pos: int) -> int:
        """The index of the URL whose span [scheme start, run end) holds
        `pos`, or -1."""
        self.need(pos)
        i = bisect.bisect_right(self.starts, pos) - 1
        return i if i >= 0 and self.urls[i][3] > pos else -1


def _eligible_colon(text: str, lo: int, hi: int, reading: UrlReading) -> int:
    """The first ASCII `:` in [lo, hi) that is a credential's to take, or -1
    (D-SINK-96): one outside every URL span, or one a URL holds whose run
    holds no ASCII `@` after it. A colon whose `@` the same URL's run holds
    is that URL's, so `http://u:p@cdn.test/x` is the URL's to print. But a
    URL whose run a TAB, LF, VT, FF or CR ends before the `@` holds the
    colon and not the `@` (the review of 4d13d71):
    `http://qqqqqq:zz<TAB>zz@cdn.test/x` printed `qqqqqq` as its host in the
    plain sinks, and `qqqqqq` and the password's tail in the folded and
    stored ones, where its scheme-less twin was withheld; that colon is the
    credential's now, and the token is withheld whole. The cost, stated: a
    URL TAB-joined to a later word holding `@` is withheld with it
    (`http://h.test:8080/x<TAB>mail@x.test`). Each `@` is searched for once,
    in the run after a colon, and the search goes on after it."""
    colon = text.find(":", lo, hi)
    while colon >= 0:
        i = reading.holding(colon)
        if i < 0:
            return colon
        at = text.find("@", colon + 1, reading.urls[i][3])
        if at < 0:
            return colon
        colon = text.find(":", at + 1, hi)
    return -1


def _counted_ends(text: str, lo: int, hi: int, reading: UrlReading, want: int,
                  last: "re.Pattern[str]" = _LAST_COUNTED) -> list[int]:
    """The ends of the last `want` COUNTED code points (above U+009F, no
    slash look-alike; or, with `last` _LAST_SPACELESS, of the scripts
    written without spaces) in [lo, hi) that lie outside every URL span,
    the last first. Walks the stretches between the URLs from the right,
    each with one native match a code point found."""
    reading.need(hi)
    urls = reading.urls
    j = bisect.bisect_left(reading.starts, hi) - 1
    ends: list[int] = []
    top = hi
    while top > lo and len(ends) < want:
        if j >= 0 and urls[j][3] > lo:
            bottom = max(urls[j][3], lo)
            below = max(urls[j][0], lo)
            j -= 1
        else:
            bottom = below = lo
        while bottom < top and len(ends) < want:
            found = last.match(text, bottom, top)
            if found is None:
                break
            ends.append(found.end())
            top = found.end() - 1
        top = below
    return ends


def token_credential(text: str, ts: int, te: int, reading: UrlReading,
                     pos: int | None = None) -> tuple[int, int, int] | None:
    """D-SINK-96 for the token [ts, te) (a run of characters other than
    U+0020), as the reviews of cbd6679 and 4d13d71 restated it: (its
    credential's colon, that colon's `@`, where the withheld span starts),
    or None. `pos`, when given, asks for the first credential whose colon
    is at or after it (cut_free_text reads a token's credentials in turn);
    the span's start is still judged from `ts`.

    The token holds a credential when an ASCII `:` that is a credential's
    (_eligible_colon: outside every URL span, or held by a URL whose run
    holds no `@` after it) has an ASCII `@` after it -- anywhere later in
    the token, a URL's run included -- with at most one code point of a
    script written without spaces (_LAST_SPACELESS: COUNTED, and Han, kana,
    Hangul, Thai, Lao, Myanmar, Khmer, the fullwidth forms or astral)
    outside the URL spans between them. The colon is the first such; the
    span starts at the token's start when [ts, colon) holds at most one
    COUNTED code point (above U+009F, no slash look-alike, a deleted
    control never) outside the URL spans, and otherwise just after the last
    of them, so a sentence of CJK prose before a credential keeps its text.
    Why each part:
    - across URL spans, not only the free pieces between them: a mark the
      reading finds inside a password (`qqqqqq:zz<U+00E9>//zz@cdn.test`)
      started a URL inside the token, so the piece before it held the `:`
      with no `@`, and every sink printed the username;
    - a colon whose `@` its own URL's run holds is that URL's, so
      `http://u:p@cdn.test/x` is that URL's to print, and
      `abc:http://u:p@h/x` is withheld whole (the cost the lead accepted).
      That cost reaches past a userinfo, accepted too (the lead's call under
      the owner's standing authority of 2026-11-09): a `Label:` glued to a
      URL whose PATH or QUERY holds an `@` is withheld whole
      (`Twitter:https://twitter.com/@BBCNews`,
      `Info:https://www.bbc.co.uk/contact?mail=tips@bbc.co.uk`); counting
      only an `@` in the URL's authority would read
      `qqqqqq:zz<X>//a/b@cdn.test` as a URL with host `a` and print the
      username;
    - the cap (the review of cbd6679's changes-too-much finding): a
      space-less CJK description holding a time and, later, a handle or an
      address (`<CJK>20:00<CJK>...@<CJK>`) was withheld whole; with it, a
      credential needs its `:` and `@` within one such code point of each
      other. It counts only the scripts written without spaces (the review
      of 4d13d71): counting every COUNTED code point let two accented
      letters, two NBSP or two euro signs in a Latin, Cyrillic or Greek
      password print the WHOLE credential;
    - the count skips URL text, so the odd characters of a mark inside the
      password (`qqqqqq:zz:<X>/<X>/zz@...`) do not count against it;
    - and a URL in the token after text, with no NAMED scheme, an `@` in its
      run and a `:` in its mark or its run before that `@`, withholds the
      token from its start
      (_unnamed_scheme_credential, the review of 4d13d71): its scheme is a
      username's tail, and its mark took the credential's colon.
    What it leaves, stated: a credential with two or more code points of a
    script written without spaces outside URLs between its `:` and its `@`
    is no credential, and the WHOLE credential prints, username and
    password (`qqqqqq:<U+5BC6><U+7801>@cdn.test`, a Han password); two or
    more COUNTED code points before its `:` start the span after the last
    of them, so the username's head prints before HOST_WITHHELD.
    Model.tokenCredential is the mirror. Each `@` is asked once, from the
    first eligible colon after the last one, so the work is linear."""
    if pos is None:
        pos = ts
    held = _unnamed_scheme_credential(text, ts, te, reading, pos)
    found = None
    while True:
        colon = _eligible_colon(text, pos, te, reading)
        if colon < 0:
            break
        at = text.find("@", colon + 1, te)
        if at < 0:
            break
        ends = _counted_ends(text, colon + 1, at, reading, 2, _LAST_SPACELESS)
        if len(ends) == 2:
            colon = _eligible_colon(text, ends[1], at, reading)
            if colon < 0:
                pos = at + 1
                continue
        before = _counted_ends(text, ts, colon, reading, 2)
        found = colon, at, (ts if len(before) < 2 else before[0])
        break
    if held is None:
        return found
    if found is None or held[0] < found[0]:
        return held[0], held[1], ts
    return found[0], found[1], ts


# The opening brackets and quotes: text of these alone before a scheme in its
# token holds no username (_unnamed_scheme_credential, the review of 2942e41).
_OPENING_RUN = re.compile("[(\\[{<\"'`]*")


def _unnamed_scheme_credential(text: str, ts: int, te: int, reading: UrlReading,
                               pos: int) -> tuple[int, int] | None:
    """(the first `:` of its mark or its run before the run's first `@`,
    that `@`) for the first URL starting in the token [ts, te), after `ts`
    and at or after `pos`, after text in its token that is not opening
    brackets and quotes alone, whose run holds an ASCII `@` and whose mark
    or run holds an ASCII `:` before it, and whose scheme is no NAMED one or
    whose mark is not the clean `://` (it holds a FILLER or a STAND_IN, a
    look-alike slash or another colon) or whose run opens with a `:`; or
    None (the review of 4d13d71). Such a URL is a credential's username
    read as a scheme: `qq_qqqq:<U+200B>//zzzzzz@cdn.test` read `qqqq` as the
    scheme and its mark took the credential's colon, and in
    `qq_qqqq<U+200B>//:zzzzzz@cdn.test` the colon opens the run; every sink
    of both mirrors printed `qq_` before the host. The lead's call named a
    `:` in P only; the run's `:` before its `@` is the nearest variant that
    closes the second shape too (63,299 of 63,484 code points leaked the
    username there), and it moved none of the 3,705 realistic strings. A
    named scheme counts when its mark is not clean (the review of 2942e41):
    `qq_tcp:<U+200B>//zzzzzz@cdn.test` printed `qq_tcp://cdn.test` in the
    helper and `qq_cdn.test` in the model. A URL like it with nothing
    before its scheme in the token prints no username
    (`qqqqqq://zzzzzz@cdn.test` prints `cdn.test`), nor does one after
    opening brackets and quotes alone (the review of 2942e41:
    `(ssh://git@github.com/x)` printed `[host withheld])`, where only the
    bracket stood before the scheme); and a named scheme behind a clean
    `://` is a URL's (`1http://u:p@h` prints its host, D-SINK-74's pin).
    What that leaves, stated: a username ending in a named scheme after a
    non-scheme character, before a password that starts with the clean
    `://` (`qq_tcp://zzzzzz@cdn.test`, case-blind), prints whole in the
    helper (`qq_tcp://cdn.test`) and its head in the model (`qq_cdn.test`),
    as `1http://u:p@h` does. The token is withheld from its start, as
    `abc:http://u:p@h` is. And a control inside the mark
    (`News qq_tcp:<NUL>//zzzzzz@cdn.test/live/1.ts HD`) is withheld at the
    plain sinks and printed at the window title and the notification -- the
    helper prints the whole username, the model its head -- and at the fold
    for the controls it removes (U+0000..U+0008, U+000E..U+001F, U+007F and
    U+0085): those sinks delete the control before they read, and read the
    clean `://` (the review of e038d58, stated as the lead's call under the
    owner's standing authority of 2026-11-09; pinned in url-mark.json, and
    MultiInsertTest exempts exactly this class).
    Model.unnamedSchemeCredential is the mirror."""
    reading.need(te)
    urls = reading.urls
    opening = _OPENING_RUN.match(text, ts, te).end()
    i = bisect.bisect_left(reading.starts, max(ts + 1, pos))
    while i < len(urls) and urls[i][0] < te:
        start, mark, mark_end, end = urls[i]
        i += 1
        if start <= opening:
            continue
        at = text.find("@", mark_end, end)
        if at < 0:
            continue
        colon = text.find(":", mark, at)
        if colon >= 0 and (_CROSSABLE.sub("", text[start:mark]).lower() not in NAMED_SCHEMES
                           or text[mark:mark_end] != "://" or text.startswith(":", mark_end)):
            return colon, at
    return None


def credential_spans(text: str, reading: UrlReading) -> list[tuple[int, int, int]]:
    """Every D-SINK-96 credential of `text` as (span start, span end, token
    end): the span ends at the token's end less its trailing punctuation
    (_trailing_cut, the redactors' set and `]` rule), which is put back
    after HOST_WITHHELD, and no URL that starts inside the token is printed
    (token_credential says what a credential is)."""
    if ":" not in text or "@" not in text:
        return []
    out: list[tuple[int, int, int]] = []
    for token in _CREDENTIAL_TOKEN.finditer(text):
        ts, te = token.span()
        found = token_credential(text, ts, te, reading)
        if found is not None:
            start = found[2]
            out.append((start, start + _trailing_cut(text[start:te]), te))
    return out


def redact_tokens(text: str) -> str:
    """D-SINK-96 over a text read as free text, with no URL in it: every
    credential token (token_credential) printed as HOST_WITHHELD and its
    trailing punctuation. redact_urls reads the same tokens across its URLs;
    Model.redactTokens is the mirror."""
    if ":" not in text or "@" not in text:
        return text
    reading = UrlReading(text, len(text), True)
    reading.done = True
    out: list[str] = []
    copied = 0
    for start, end, _ in credential_spans(text, reading):
        out.append(text[copied:start])
        out.append(HOST_WITHHELD)
        copied = end
    out.append(text[copied:])
    return "".join(out)


# fold_space's class inside a URL's run, after its mark: the controls the
# plain fold turns into a space (C0, DEL and U+0085, _CONTROL_WS's controls)
# and the line and paragraph separators (U+2028, U+2029), each of which
# fold_space replaces there with U+FFFD (RUN_REPLACEMENT, D-SINK-79).
_RUN_CONTROLS = re.compile("[\x00-\x1f\x7f\x85\u2028\u2029]")
RUN_REPLACEMENT = "\ufffd"


_HELD_DELIMITERS = re.compile("[\t\n\x0b\x0c\r]")
_HELD_CONTROLS = re.compile("[\x00-\x08\x0e-\x1f\x7f\x85]")


def _fold_held(text: str) -> str:
    """fold_space inside a credential's withheld span (D-SINK-96): the
    characters kept, so every redactor reads the same credential in the
    stored text as in the raw one, and every one of them still withholds
    it. The ASCII delimiters but the space become a TAB, which is one too:
    each ends a URL's run and none ends a token, so a URL in the span keeps
    its run and every colon after it stays outside it. The other controls
    the plain fold takes (C0, DEL, U+0085) are deleted: none is WIDE or a
    delimiter, so no mark, walk, run, token or count moves. U+2028 and
    U+2029 become U+00A0: each is FILLER, WIDE, counted and no STAND_IN, as
    U+00A0 is. A space would split the token, and every sink would print
    its username (`qqqqqq:zz<TAB>zz@cdn.test`); U+FFFD, a STAND_IN, would
    make a mark the raw text lacks before a `//`; and U+00A0 in place of a
    control, as the first version of this fold put it, is counted, so two
    of them between the `:` and the `@` lifted the cap. A NUL, U+001F and
    DEL never reach a stored text, nor does a line break: what is kept is a
    TAB, inside a span every sink prints as HOST_WITHHELD."""
    return _MARK_SEPARATORS.sub("\xa0", _HELD_CONTROLS.sub("", _HELD_DELIMITERS.sub("\t", text)))


def _fold_url(text: str, url: tuple[int, int, int, int]) -> str:
    """fold_space over one URL that no credential holds (D-SINK-79): its
    scheme and mark lose their controls, a line or paragraph separator
    there becomes RUN_REPLACEMENT, and its run's controls become
    RUN_REPLACEMENT."""
    start, _, mark_end, end = url
    return (_MARK_SEPARATORS.sub(RUN_REPLACEMENT, _CONTROL_CHARS.sub("", text[start:mark_end]))
            + _RUN_CONTROLS.sub(RUN_REPLACEMENT, text[mark_end:end]))


def fold_space(text: str) -> str:
    """`text` with every run of whitespace and control characters folded to
    one space (_CONTROL_WS), except inside a URL and inside a credential
    token, which are never folded (D-SINK-79, 2026-11-05; D-SINK-95 and
    D-SINK-96, 2026-11-11).

    The guide's cleaners (clean_title, clean_detail, retain_programme) used
    to fold the whole text with _CONTROL_WS before any redactor saw it. A
    redactor ends a URL's run at the six ASCII delimiters ALONE
    (URL_DELIMITER_CHARS, R32a'''), so every other whitespace or control code
    point is URL text, and a password holding one redacts to the host. The
    fold turned exactly those into a space, which ends a run at every sink:
    `http://qqqqqq:zz<U+00A0>zz@cdn.test/x` was stored as
    `http://qqqqqq:zz zz@cdn.test/x`, both redactors then read `qqqqqq` as
    the host and printed it, and the password's tail after it carried no
    scheme for anything to redact. Measured through parse_xmltv on 20 code
    points XML allows (U+007F, U+0085, U+00A0, U+1680, U+2000..U+200A,
    U+2028, U+2029, U+202F, U+205F, U+3000), in a title, a description, a
    category and an episode, in the userinfo and in Xtream's path and query.

    A URL is what the redactors read as one (next_url, D-SINK-95, from the
    text's start), and its run ends at the first of URL_DELIMITER_CHARS
    after its mark, else at the end of the text. A mark with no scheme
    letter before it (`1://`, ` ://`) is no URL to any redactor, so its
    text is free text; a URL behind it is read on its own (`1://a?u=http:
    <DEL>//...`, the review's F9 recheck). A credential is what the
    redactors withhold (credential_spans, D-SINK-96, read on the RAW text),
    from its span's start to its token's end, and a URL inside it is part
    of it. Inside a credential the characters are kept as _fold_held says.
    Inside a URL no credential holds:
    - from the scheme to the mark's end, the mark keeps its characters and
      loses its controls: every control in that span (_CONTROL_CHARS, a tab
      among them) is deleted, as the player's title and the notification
      delete them before they redact, so `:<DEL>//`, `:/<TAB>/` and
      `http<DEL>://` are the URL a deleting sink reads, to the plain
      redactors too; U+2028 and U+2029 there become U+FFFD
      (RUN_REPLACEMENT), so no line break reaches a row; every other
      character -- a look-alike, a STAND_IN, NBSP, a crossed character --
      is kept, so the stored text is still read as the same URL;
    - after the mark, every control the plain fold turns into a space (C0,
      DEL and U+0085) and the line and paragraph separators (U+2028,
      U+2029) -- _RUN_CONTROLS -- each become U+FFFD, which both redactors
      read as URL text, so it splits nothing; which is also what keeps NUL,
      U+001F and DEL out of every cleaned text, as the guide's records need
      (the first two separate retain_programme's fields, and DEL separates a
      channel's records, EPG_RECORD_SEP, which json.dumps does not escape),
      and keeps a line break out of every row a stored title is drawn in.
      REPLACED, not deleted (the review's F9): deleting one could make a
      port of digits out of `:<DEL>/` or `:12<DEL>34/`, and a dotted
      username before a digits-only password prefix is the one userinfo
      both redactors print (R32a'', D-SINK-35), where the raw text's
      non-numeric port has them withhold the host;
    - every other character is kept as it is: the other non-ASCII spaces,
      which both redactors read as URL text, and the C1 controls the plain
      fold never touched, which they read as URL text too and the deleting
      sinks delete.
    Everything else is free text, and takes _CONTROL_WS's fold byte for
    byte: a space it puts in a credential's token before its span starts
    the token later, which leaves the span as long or longer.

    Costs, stated: a control or a line separator inside a URL is drawn as
    U+FFFD where it used to become a space, in the host a redactor prints
    too; a credential keeps a TAB for each ASCII delimiter in it, which no
    sink draws, since every one withholds the span; and a non-ASCII space
    glued after a URL keeps the word behind it inside the run, so a
    redactor drops that word with the URL's path, exactly as it reads the
    raw text. And because the mark's controls are deleted -- a tab, a line
    feed and a carriage return among them -- prose with a word's `:` at the
    end of a line and `//` at the start of the next (`Featuring:<LF>// The
    Band`) is stored as `Featuring:// The Band`, which every sink reads as
    a URL with an empty run (`[url] The Band`, in both mirrors since the
    review of 4d13d71); the raw text reads the same since the review of
    cbd6679 gave both mirrors one empty-run reading. That is the price of
    `http:<LF>//user:pw@host` being redacted, where the raw text and the
    old fold printed it whole.

    Linear: the reading is read once (UrlReading), the credentials once
    over its URLs, and the subs read each piece once. A text that
    redact_urls cannot change (redaction_can_change), or that is printable
    ASCII -- where a URL's run and a token hold nothing the plain fold
    touches but the space that ends them -- takes the plain fold, which is
    every programme title without a URL.
    """
    if not redaction_can_change(text) or (text.isascii() and text.isprintable()):
        return _CONTROL_WS.sub(" ", text)
    reading = UrlReading(text, 0, False, True)
    urls = reading.urls
    out: list[str] = []
    pos = 0
    ui = 0
    for start, _, token_end in credential_spans(text, reading):
        while ui < len(urls) and urls[ui][0] < start:
            out.append(_CONTROL_WS.sub(" ", text[pos:urls[ui][0]]))
            out.append(_fold_url(text, urls[ui]))
            pos = urls[ui][3]
            ui += 1
        out.append(_CONTROL_WS.sub(" ", text[pos:start]))
        out.append(_fold_held(text[start:token_end]))
        pos = token_end
        while ui < len(urls) and urls[ui][0] < token_end:
            ui += 1
    for url in urls[ui:]:
        out.append(_CONTROL_WS.sub(" ", text[pos:url[0]]))
        out.append(_fold_url(text, url))
        pos = url[3]
    out.append(_CONTROL_WS.sub(" ", text[pos:]))
    return "".join(out)


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


def run_host_parts(body: str, printing: bool = False) -> tuple[str, bool]:
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
    branch) holds both mirrors to it. The host it RETURNS is cut at its first
    slash look-alike (slash_alike_cut, D-SINK-95); `withheld` is asked of
    the host before that cut."""
    space = _URL_DELIMITER.search(body)
    if space is not None:
        body = body[:space.start()]
    cut = _AUTHORITY_END.search(body)
    authority = body if cut is None else body[:cut.start()]
    rest = "" if cut is None else body[cut.start():]
    hostport = authority[authority.rfind("@") + 1:]
    if hostport.startswith("["):
        close = hostport.find("]")
        return slash_alike_cut(hostport[:close + 1].lower() if close != -1 else ""), False
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
    # `printing` (the redactors' print path, the review of cbd6679): a
    # non-numeric port behind a userinfo is withheld too, with no later `@`
    # needed. `http://<TAB>:@qqqqqq:zzzzzz` is withheld whole by the plain
    # sinks (a credential token), and with the tab deleted the sinks that
    # delete controls read the run `:@qqqqqq:zzzzzz`: host `qqqqqq`, port
    # `zzzzzz`, which they printed. The predicate the Sources form warns
    # with (host_withheld, Model.urlHostWithheld) does not move, nor does
    # the host a stored record shows.
    if printing and bad_port and "@" in authority:
        return slash_alike_cut(host.lower()), True
    return slash_alike_cut(host.lower()), later_at and (dotless or bad_port)


def slash_alike_cut(host: str) -> str:
    """D-SINK-95: `host` up to its first slash look-alike
    (SLASH_ALIKE_CHARS). The authority still ends only at an ASCII `/`, `?`
    or `#`, so a URL whose slashes are all look-alikes, or a clean `://`
    with fullwidth path slashes, printed its path -- credentials and all --
    as the host; the printed host stops at the first look-alike instead.
    The withheld predicate is asked of the host before this cut, so it does
    not move. Model.runHostParts cuts the same way."""
    if host.isascii():
        return host
    found = _SLASH_ALIKE.search(host)
    return host if found is None else host[:found.start()]


def host_withheld(url: str) -> bool:
    """R32a': the predicate alone, over a whole URL (or any text holding one)."""
    j = url.find("://")
    return j != -1 and run_host_parts(url[j + 3:])[1]


def run_host(raw: str) -> str:
    """What redact_urls prints for one `scheme://...` run: the RFC host, or
    HOST_WITHHELD."""
    host, withheld = run_host_parts(raw[raw.find("://") + 3:], True)
    return HOST_WITHHELD if withheld else host


def _url_shown(s: str, url: tuple[int, int, int, int], plain: bool) -> tuple[str, int]:
    """What redact_urls prints for one URL no credential holds, and where
    the text it prints over ends: the scheme and `://` when the scheme is
    one NAMED_SCHEMES lists, then the host, HOST_WITHHELD, or `[redacted]`
    for none, then the run's trailing punctuation, over the URL to its
    run's end; an empty run, or one of trailing punctuation alone, prints
    `[url]` and that punctuation, with no scheme, as the model does.

    D-EPG-18 (2026-11-12): a URL whose mark is followed by exactly
    HOST_WITHHELD is one a redactor already printed (a programme
    description is stored redacted and redacted again where it is shown; a
    helper line is redacted again by the shell). The token holds a space,
    which ends the run, so the run is `[host` and a second pass printed
    `http://[redacted] withheld]` (`[url] withheld]` in the model). It
    prints as a withheld host, its scheme by the same list, over the text
    through the token's `]`. Only the printing moves: the run, the reading
    and every credential's token are what they were, so what follows the
    `]` is read as text after the space that ended the run.

    The scheme is printed from a list (the review of cbd6679, D-SINK-94's
    sibling by rule 15): the printed scheme is the text from the scheme's
    start to its mark, CROSSABLE characters removed, lowercased, and since
    D-SINK-95 a mark may start inside a username or a password, so
    `qqqqqq:<U+200B>//zzzzzz@cdn.test` printed `qqqqqq://cdn.test` in the
    window title and on stderr, where the model, which prints no scheme,
    printed the host. D-SINK-94 had closed the same shape in the refusals.
    Any other scheme prints as the model prints the URL."""
    start, mark, mark_end, end = url
    if s.startswith(HOST_WITHHELD, mark_end):
        scheme = (s[start:mark] if plain else _CROSSABLE.sub("", s[start:mark])).lower()
        shown = scheme + "://" + HOST_WITHHELD if scheme in NAMED_SCHEMES else HOST_WITHHELD
        return shown, mark_end + len(HOST_WITHHELD)
    run = s[mark_end:end]
    # Sentence punctuation after a URL is put back. A `]` is kept when the
    # run holds a `[`: it closes an IPv6 literal, and stripping it left
    # `http://[2001:db8::5].` with no host to show (R32a; a D-SINK-23
    # sibling lane S recorded). The scheme and the mark hold no `[`.
    keep = _trailing_cut(run)
    if keep == 0:
        # An empty run, or one of sentence punctuation alone, prints the
        # model's word with no scheme (the review of 4d13d71): the helper
        # printed `file://[redacted]` and `[redacted]` where the model
        # printed `[url]`, so a stored description and the guide title over
        # the same text read differently.
        return "[url]" + run, end
    host, withheld = run_host_parts(run[:keep], True)
    shown = HOST_WITHHELD if withheld else host or "[redacted]"
    scheme = (s[start:mark] if plain else _CROSSABLE.sub("", s[start:mark])).lower()
    if scheme in NAMED_SCHEMES:
        shown = scheme + "://" + shown
    return shown + run[keep:], end


def redact_urls(text: Any) -> str:
    """Replace every URL inside `text` with scheme://host (R12), and every
    credential token with HOST_WITHHELD.

    D-SINK-95 and D-SINK-96 (2026-11-11), as the review of cbd6679
    restated them (2026-11-12). The URLs are next_url's reading: a scheme
    behind a mark that one odd character may break -- a control, a
    character drawn with no width, a combining mark, a fullwidth colon, a
    slash look-alike, before or inside the `//` -- where this read only an
    unbroken `scheme://`, so a provider's name, group or programme text
    printed the username and the password in every sink that runs it, the
    player's window title among them. A credential is a token of the whole
    text, across its URLs, shaped `a:b@c` (token_credential), and its span
    is withheld whole, a URL inside it with it, where a `user:pass@host`
    with no scheme in front of it went out whole. A URL no credential holds
    prints as _url_shown says: its scheme only from NAMED_SCHEMES, the host
    run_host_parts' over the run less its sentence punctuation (printing,
    so a non-numeric port behind a userinfo is withheld), cut at its first
    slash look-alike (D-SINK-95: a URL whose slashes are all look-alikes
    printed its path as the host, and so did
    `http://cdn.test<U+FF0F>live<U+FF0F>...` in 0.18.0), or HOST_WITHHELD,
    or `[redacted]` when there is none, and `[url]` for an empty run. A text
    redaction_can_change refuses is returned as it is, which is exact.

    F-SINK-11. Linear: the pattern this replaced,
    `\\b([A-Za-z][A-Za-z0-9+.-]*)://[^\\s'"<>]+`, re-read its scheme run from
    every word boundary, and `.`, `+` and `-` are scheme-legal and are not
    word characters, so "aaaa." repeated cost 2826.2 ms at 40,000
    characters on python 3.14.7, against 0.012 ms after. next_url reads the
    scheme before the run, since reading the run first made `1://` repeated
    quadratic (2.2 s at 40,000 characters); the scheme walk never goes back
    past where the last failed one started; the credentials are asked once
    a candidate token, each `@` once. The redaction-cost suite (dev branch)
    holds this to a statement of the rule, over the shared fixtures and
    thousands of generated strings, character for character.

    D-SINK-74 (2026-11-04). The old pattern also asked `\\b` of a scheme's
    start, and so did this scan until then, so `1http://user:pass@host/x`
    and `http` right after `_` or a non-ASCII letter went out whole. A
    scheme starts at the first ASCII letter of the SCHEME segment before its
    mark, whatever stands before it, and Model.redactUrls reads the same.

    This makes the caps in front of this sink cheap, not unnecessary:
    cut_text, clean_title, clean_field and clean_detail are still what keeps
    a 64 MiB description out of a renderer, and every cap cut before a
    redaction -- on text stored as written, or, in clean_detail, redacted
    just after -- cuts through cut_free_text, which drops a cut URL or token
    rather than hand a redactor half of one (D-SINK-75).
    """
    s = "" if text is None else str(text)
    if not redaction_can_change(s):
        return s
    plain = s.isascii() and s.isprintable()
    reading = UrlReading(s, 0, plain, True)
    urls = reading.urls
    out: list[str] = []
    copied = 0                      # everything before this is already in `out`
    ui = 0
    for start, end, token_end in credential_spans(s, reading):
        while ui < len(urls) and urls[ui][0] < start:
            shown, stop = _url_shown(s, urls[ui], plain)
            out.append(s[copied:urls[ui][0]])
            out.append(shown)
            copied = stop
            ui += 1
        # A span may start inside a token a URL above was printed through
        # (D-EPG-18: in `http://[host withheld]qqqqqq:zzzzzz@cdn.test` the
        # credential's token is `withheld]qqqqqq:zzzzzz@cdn.test`). What is
        # printed stays printed, and the span is withheld after it.
        if start > copied:
            out.append(s[copied:start])
        out.append(HOST_WITHHELD)
        copied = max(copied, end)
        while ui < len(urls) and urls[ui][0] < token_end:
            ui += 1
    for url in urls[ui:]:
        shown, stop = _url_shown(s, url, plain)
        out.append(s[copied:url[0]])
        out.append(shown)
        copied = stop
    out.append(s[copied:])
    return "".join(out)


# How far past its limit cut_free_text reads a run for its credential, at
# least: the window is the limit or this, whichever is longer.
CUT_CREDENTIAL_WINDOW = 4096


def cut_free_text(text: str, limit: int, separator: str = "") -> str:
    """`text` cut to `limit` code points, and never through a URL or a
    credential token (D-SINK-75; D-SINK-95 and D-SINK-96, 2026-11-11).

    F-M4-1's rule, which of the cuts made before a redaction only
    clean_detail applied until then: REDACTION NEVER SEES A TRUNCATED URL. A URL cut between its
    `//` and its `@` keeps a userinfo with no `@` after it, so run_host_parts
    and Model.redactUrls read the username as the host and print it:
    `... http://myuser:S3CRETpw` from `... http://myuser:S3CRETpw@cdn.test/x`.
    So when the cut lands inside a run that an ASCII space ends, the cut
    drops back to the start of the item in that run that it would cut: the
    run's first URL (next_url's reading, from the run's start) when the cut
    keeps its whole mark -- a cut before the mark's end keeps a scheme and
    part of a mark, which no reading takes for a URL -- or the run's
    credential (token_credential) when the `@` that makes it one is not
    kept, from its span's start; a space just before that start goes with
    it. A run the cut does not touch is
    kept whole, so a redactor sees all of it, and so is the part of the run
    before its first item: the review of cbd6679 found the first version of
    this rule dropping the whole run, so a space-less Chinese or Japanese
    description or title whose cut held a false positive was stored EMPTY,
    or as its first words, until the next fetch.

    Why a space, and not the six delimiters that end a redactor's run: the
    window title and the notification delete every control character before
    they redact (F-SINK-16), so there a tab, VT, FF or CR inside a URL joins
    the runs on either side of it, and a run read at the six kept
    `http://myuser:zz<TAB>z`, which those sinks then read as `myuser`. So
    the run's FIRST URL counts whatever delimiter ends its own run: the
    deleting sinks read it to the space. They read the same start, since a
    deleted control is neither WIDE nor a STAND_IN and moves no mark (a
    scheme start they read can only be earlier, inside letters, and what is
    kept before it holds no mark); the cut suite holds that. A space ends a
    run at every sink, and it is all a D-SINK-96 token ends at. The costs: a
    cut URL loses its host as well, a cut run of several tab-joined URLs
    loses every one from the first, and a run that starts with its item
    comes back without it ("" when it is the text).

    `separator` is what splits the text before any sink sees it, the group
    text's `;`, and it counts only where split_groups splits at it: before
    the run's first mark, and before its token's `:` (D-SINK-78). So a cut
    inside a URL or a token keeps up to the later of the item's start and
    the last `;` before the mark, the token's `:` or the cut, keeping the
    groups before it, and a `;` after the mark, which split_groups keeps
    inside the URL's group, is no end here either: the first version of
    this function ended a run at every `;`, and a cut at the `;` of
    `http://myuser:pa;ss@cdn.test/x` kept `http://myuser:pa`.

    The helper holds two definitions of a URL's run, and they differ on
    purpose. This function and split_groups end a run at an ASCII space, for
    the reason above. parse_attrs (D-SINK-80) and fold_space (D-SINK-79) end
    it at the six delimiters, so an attribute a TAB separates from a URL value
    is still read, and a TAB after a URL in a guide text still ends it. The
    two differ only for a URL that holds a TAB, VT, FF or CR, which is
    D-SINK-34's accepted class.

    Bounded: the URL is asked for only up to the first walk barrier after
    the limit (_WALK_BARRIER: no scheme that starts before the limit has its
    mark past one), and the credential only in a window past the limit
    (CUT_CREDENTIAL_WINDOW): a run longer than that past the cut, with a `:`
    before and an `@` past the window and no credential inside it, is
    dropped whole, the first version's answer, stated.
    """
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if text[limit] == " ":
        return cut
    start = cut.rfind(" ")
    low = start + 1
    run_end = text.find(" ", limit)
    if run_end < 0:
        run_end = len(text)
    plain = text.isascii() and text.isprintable()
    barrier = _WALK_BARRIER.search(text, limit)
    url = next_url(text, low, low, plain, len(text) if barrier is None else barrier.end() - 1)
    bound = url[0] if url is not None and url[2] <= limit else limit
    # The credential the cut splits, when the `@` that makes it one is not
    # kept: what the cut keeps of it is a username, or a part of one. It is
    # the run's first credential whose colon stands after the last `@` the
    # cut keeps (the review of 4d13d71: asking for the run's FIRST
    # credential found `qq:zz@a.test`, whose `@` is kept, so
    # `qq:zz@a.test;qqqqqq:zzzzzz@cdn.test` cut at 26 kept
    # `qq:zz@a.test;qqqqqq:zzzzzz`, which split_groups split at its `;`, and
    # the group `qqqqqq:zzzzzz` printed). Every credential whose colon stands
    # before that `@` has its own `@` kept, and every one after it has not.
    # It is asked no further than a window past the limit, and its URLs are
    # read no further than the first walk barrier past the window (the
    # review of 4d13d71: the reading went on to the text's end, 2.1 s on a
    # 4 MB description through clean_detail; no URL whose mark starts past a
    # barrier has its scheme start before it). A run with an `@` past the
    # window after such a `:` and none found before it drops whole, as
    # every run did before the review of cbd6679, rather than read a
    # million characters of URLs to learn which.
    colon = text.find(":", low, run_end)
    split = -1
    if colon >= 0 and text.find("@", colon + 1, run_end) >= 0:
        reach = min(run_end, limit + max(limit, CUT_CREDENTIAL_WINDOW))
        past = _WALK_BARRIER.search(text, reach)
        reading = UrlReading(text, low, plain, stop=len(text) if past is None else past.end() - 1)
        after = text.rfind("@", low, bound) + 1
        found = token_credential(text, low, reach, reading, max(low, after))
        if found is not None:
            split = found[0]
            if found[2] < bound:
                bound = found[2]
        else:
            rest = text.find(":", max(low, after), run_end)
            if rest >= 0 and reach < run_end and text.find("@", max(rest + 1, reach), run_end) >= 0:
                split = rest
                bound = low
    if bound == limit:
        return cut
    end = bound - 1 if bound > 0 and text[bound - 1] == " " else bound
    if separator:
        # Up to the later of that and the last `;` before what split_groups
        # keeps in one group, and never ending in a `;`: before the run's
        # first mark, and before the colon of the credential the cut
        # splits, or of the run's first `:` with an `@` after it.
        mark = url_mark_any(cut, low)
        keep = limit if mark < 0 else mark
        if split >= 0:
            keep = min(keep, split)
        elif colon >= 0 and text.find("@", colon + 1, run_end) >= 0:
            keep = min(keep, colon)
        end = max(end, cut.rfind(separator, low, keep))
        if end > low and cut[end - 1] == separator:
            end -= 1
    return cut[:max(end, 0)]


def log(message: str) -> None:
    sys.stderr.write("omarchy-iptv: %s\n" % redact_urls(message))


# ------------------------------------------------------- normalization
# Must match the model's normalizeText/normalizeIdText/searchKey/fnv1a32
# byte for byte. The folds do, except on the letters whose lower case the two
# runtimes' Unicode tables disagree on (D-SRC-12): the whitespace class is
# enumerated in both since D-ID-5, and the shell takes the ids this helper
# writes rather than recompute them.

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
# The whitespace both folds collapse (D-ID-5), written out at the head of
# _PUNCT and _ID_PUNCT below: the 29 code points `\s` matched on CPython 3.14
# when it was enumerated, so no stored `n:` id moved when it was. Not `\s`
# itself: that is this interpreter's Unicode tables, which the model's engine
# does not share (its `\s` matches U+FEFF and not U+001C-U+001F or U+0085, so
# for a name holding one of those six the two mirrors folded different text),
# and which a later interpreter may change under every id hashed from them.
# The same list heads PUNCT_RE and ID_PUNCT_RE in the model; the
# channel-ids.json fixture (dev branch) holds it, and both suites check every
# BMP code point of both folds against it.
_PUNCT = re.compile(r"[\t\n\x0b\x0c\r\x1c-\x20\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000!-/:-@\[-`{-~]+")
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
_ID_PUNCT = re.compile(r"[\t\n\x0b\x0c\r\x1c-\x20\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000!-)\,-/:-@\[-`{-~]+")
# FOLD as a str.translate table: the same replacement, character for
# character, as "".join(FOLD.get(ch, ch) for ch in text), in C.
FOLD_TABLE = str.maketrans(FOLD)


def _ascii_space_table(punct: "re.Pattern[str]") -> dict[int, str] | None:
    """fold_text's ASCII path for `punct` (D-PERF-13): {code: " "} for each
    ASCII character the class holds, read off the pattern itself so the two
    cannot drift; or None when the path would not give the whole fold's
    answer, and fold_text then takes the whole fold (FOLD, then the pattern).

    For an ASCII text the fold is `punct.sub(" ", text).strip(" ")`: each
    maximal run of the class becomes one space, and the ends lose theirs.
    Mapping each class character to a space and joining str.split()'s words
    with one space is the same text, provided the only whitespace str.split()
    can still see is that space: every ASCII character it splits at must be
    in the class (both classes hold all ten), and FOLD must leave ASCII alone
    (its lowest key is U+00DF). Measured on a 213-character group text (S1's
    16 groups joined), at load 1.7: 35 us a fold through the per-character
    join and the pattern, 4 us this way; a channel name, 3.3 us to 1.1."""
    if any(ord(ch) < 128 for ch in FOLD):
        return None
    table: dict[int, str] = {}
    for code in range(128):
        if punct.fullmatch(chr(code)):
            table[code] = " "
        elif chr(code).isspace():
            return None
    return table


_ASCII_SPACE_TABLES = {pattern: _ascii_space_table(pattern) for pattern in (_PUNCT, _ID_PUNCT)}


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
    input, not on playlist text). _ID_PUNCT folds whitespace (`\\s` then,
    an enumerated list since D-ID-5), so a tab keyed the same from either side, but
    `\\x7f`, `\\x00-\\x08` and `\\x0e-\\x1b` are not in it:
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
    Mirrors the model's decompose()/normalizeText (NFD, not NFKD), except
    where the two runtimes' lower-casing tables differ, a gap that moves with
    either runtime's Unicode version (D-SRC-12 measured 28 codepoints). The
    whitespace is one enumerated list in both (D-ID-5)."""
    return fold_text(value, _PUNCT)


def normalize_id_text(value: Any) -> str:
    """The id fold (mirror: Model.normalizeIdText). Identical to
    normalize_text except that `+` and `*` survive, because they are the
    difference between two channels rather than noise inside one. Never use
    it for search."""
    return fold_text(value, _ID_PUNCT)


def fold_text(value: Any, punct: "re.Pattern[str]") -> str:
    text = ("" if value is None else str(value)).lower()
    if text.isascii():
        # FOLD has no ASCII key, so an ASCII text's class runs are folded
        # natively when the class has a table (_ascii_space_table,
        # D-PERF-13). Without one it takes the whole fold below, FOLD
        # included, as every text did before.
        table = _ASCII_SPACE_TABLES.get(punct)
        if table is not None:
            return " ".join(text.translate(table).split())
    else:
        import unicodedata
        text = unicodedata.normalize("NFC", _LATIN_MARKS.sub(r"\1", unicodedata.normalize("NFD", text)))
    return punct.sub(" ", text.translate(FOLD_TABLE)).strip(" ")


def search_key(name: Any, group: Any) -> str:
    return search_key_of(normalize_text(name), group)


def search_key_of(key: str, group: Any) -> str:
    """search_key for a name already folded by normalize_text. make_channel
    stores that fold as `nameKey` as well, and folds it once for both
    (D-PERF-13): the second fold read the same name with the same class."""
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
    lookup can tell (the connect-time check makes that lookup; a cached
    channel's host is looked up at play time, stream_lookup_refusal, and
    the player looks it up again, which is the rebinding residual stated in
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


# D-SINK-57: the port a URL names, or its scheme's default (http 80 = no
# port). Schemes with no default (srt, udp, rtp) answer None.
URL_DEFAULT_PORTS = {"http": 80, "https": 443, "rtmp": 1935, "rtmps": 443, "rtsp": 554, "mms": 80, "mmsh": 80}


def url_port(url: str) -> int | None:
    """The port of a URL, its scheme's default when it names none, None when
    neither is known or the URL does not parse (D-SINK-57)."""
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    return port if port is not None else URL_DEFAULT_PORTS.get(parts.scheme.lower())


def own_host_match(host: Any, port: Any, home: dict[str, Any]) -> bool:
    """Is `host` (at `port`) the playlist's OWN host? D-SINK-57 (owner,
    2026-10-29): the host keys are equal (host_key), and when the home is on
    LOOPBACK the ports are equal too -- so a local relay (Threadfin, xTeVe, an
    nginx cache) on 127.0.0.1:34400 is its own host and 127.0.0.1:631 is not.
    A LAN or public home keeps any port. `home` is {"host": host_key, "port":
    int or None, "loopback": bool}; the home is loopback when its literal is
    (host_class) or when its fetch connected to loopback (a name that resolves
    there). A port that is not known is never equal to one that is."""
    key = str(home.get("host") or "")
    if key == "" or host_key(host) != key:
        return False
    if not home.get("loopback") and host_class(host) != "loopback":
        return True
    want = home.get("port")
    return isinstance(port, int) and not isinstance(port, bool) and port == want


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


# D-SINK-82 (owner, 2026-11-05): a playlist's guide hint that is a LIST.
# `url-tvg="https://epg.test/guide.xml.gz,http://prov.test/xmltv.php?
# username=U&password=P"` is several guides to Kodi's pvr.iptvsimple and to
# the apps that follow it, and it was ONE URL to Model.epgHintVerdict: the
# first URL's host, with `,http://prov.test/...` in its path, so the second
# URL's credential went to the first URL's host on every guide refresh, with
# no click (D-SINK-40's userinfo test reads only the text before the first
# `/`). The list's separator is a `,` followed -- after any run of the six
# ASCII delimiters (URL_DELIMITER_CHARS, R32a''') -- by a scheme and a URL's
# `://` as _URL_MARK reads one (controls allowed between the `:` and the
# `//`, as a control-deleting sink reads it); a `,` anywhere else is URL text
# (`?ids=1,2` is a legal query). Only the FIRST entry is adopted
# (Model.hintFirstEntry, before every D-SINK-40 check), and the guide fetch
# of a URL the playlist chose refuses one that is not its own first entry
# (fetch_bytes, 03-io-playlist.py), so a 0.16.0 or 0.17.0 shell that still
# hands over the whole list -- one loaded before an update, D-SINK-70's
# shape -- sends nothing; that fetch also refuses a host holding a `,`,
# because those shells normalize the list first (the review's F10). A shell
# before 0.16.0 sets no origin, so its fetch reads as the user's and keeps
# the defect until it restarts (F4). The shared provider-hosts fixture (dev
# branch) runs both mirrors.
# Linear: a literal `,` first, then runs over three classes that are each
# ended by a character the run cannot hold (check-helper-regex.py).
_HINT_LIST_COMMA = re.compile(",[" + URL_DELIMITER_CHARS + "]*[A-Za-z][A-Za-z0-9+.\\-]*" + _URL_MARK.pattern)


def hint_first_entry(text: Any) -> str:
    """The first entry of a guide hint that may be a comma-joined list
    (D-SINK-82): the text before the first `,` that opens another URL
    (_HINT_LIST_COMMA), the six ASCII delimiters taken off both its ends;
    the text itself, untouched, when no `,` opens one -- so
    `hint_first_entry(url) != url` reads "url is a list". An empty first
    entry (`,http://...`) is "", never the second. Mirror of
    Model.hintFirstEntry, both held to the provider-hosts fixture."""
    value = text if isinstance(text, str) else str(text or "")
    found = _HINT_LIST_COMMA.search(value)
    if found is None:
        return value
    return value[:found.start()].strip(URL_DELIMITER_CHARS)


# D-SINK-80's cost, the review's F1 (2026-11-06): a URL's run takes the rest
# of its run (parse_attrs), so a quoted attribute glued after a URL value
# (`tvg-logo="https://l.test/a.png"catchup-source="http://p.test/U/P/..."`),
# a quoted list (`url-tvg="A","B"`) or a bare attribute glued by a comma
# (`url-tvg=A,x-tvg-url=B`) is stored INSIDE the first URL -- whole, which is
# what keeps every redactor's reading right, and wrong as an address: the
# guide fetch and the logo fetch sent the second URL's credential to the
# first URL's host, in the request line. The parse now stores no hint and no
# logo from a value that ran past where every earlier release ended it
# (own_value, 02-sources.py; the recheck found that a bare value takes
# ANY text glued after its comma, not only an attribute), so this is the
# fetches' BACKSTOP, for an address stored or handed over before that rule:
# a raw `"` is in no component of a URL (RFC 3986), and a `,` followed by an
# attribute key, a `=` and a URL's `://` (_URL_MARK) is a glued attribute
# holding a URL. It is not the whole class: other text glued after a bare
# value's comma passes here, and only the parse's rule stops it. A `,` in a
# QUOTED value is the provider's own text (`?ids=1,2`, Cloudinary's
# `w_100,h_100/https://...`), as is a `key=https://` after `?` or `&` (an
# image proxy's `?url=`), and passes. Linear: a literal `,` first, then runs
# over classes that are each ended by a character the run cannot hold, `,`
# among them (check-helper-regex.py).
_ABSORBED_URL = re.compile(",[A-Za-z0-9_.\\-]+=[A-Za-z][A-Za-z0-9+.\\-]*" + _URL_MARK.pattern)


def absorbed_attribute(text: Any) -> bool:
    """Does an address the PLAYLIST chose hold one of two shapes of what a
    URL's run absorbed from beyond its own attribute -- a raw `"`, or a `,`
    that opens an attribute holding a URL (_ABSORBED_URL)? Such an address
    is never fetched: the guide fetch refuses it (fetch_bytes, origin
    `playlist`), a logo with it has no host (logo_survey_host) and is
    refused (fetch_logo, `logo_url`), and the shell adopts no such hint and
    counts no such logo (Model.absorbedAttribute, both held to the
    provider-hosts fixture). The backstop behind the parse's own rule
    (own_value), for a cache or a shell from before it; never asked of
    a URL the user typed. The cost, stated: a quoted hint or logo holding
    one of the shapes is not used, where 0.17.0 used it whole (a quoted
    `?a=1,url=https://...`); no writer is known to produce one."""
    value = text if isinstance(text, str) else str(text or "")
    return '"' in value or _ABSORBED_URL.search(value) is not None


def dotless_host(host: Any) -> bool:
    """Is this host ONE DNS label -- a host the provider chose that is
    refused before any lookup (D-SINK-83, the owner's ruling of
    2026-11-05)? Lower-cased and with ONE trailing `.` removed, it holds no
    `.`, is not empty, and is not an IPv6 literal, bracketed (as a URL
    writes one) or not (as http.client hands one to the connect).

    Why: a URL holding an ASCII space or tab in its userinfo is cut there by
    every redactor, and at a space by every tokenizer (D-SINK-34's accepted
    class, which no grammar can close), and the piece left is
    `http://USER:...`, whose host is the USERNAME -- one label, no dot,
    unless the username holds one: a dotted or encoded e-mail username
    reads as a dotted host and is looked up and named as before, since no
    test can tell it from a host (D-SINK-35's class; the review's F12, and
    the provider-hosts fixture pins it). Refusing it keeps the username
    away from the resolver (and through it the search domains' servers) and
    out of the Sources row and the logo consent dialog. Applied to a guide
    hint (Model.epgHintVerdict: no hint at all, the playlist's own host
    excepted), to a logo (logo_host, fetch_logo: never excepted), and on
    every hop of a fetch whose URL the provider chose
    (DestinationPolicy.refuses_name). Never to a URL the user typed.

    The cost, stated: a single-label name that would resolve to a GLOBAL
    address through a DNS search domain -- a non-global answer is already
    refused at connect (D-SINK-41) -- is refused for a guide hint off the
    playlist's host and for every logo (public CAs issue no certificate for
    a single-label name, and logos are https only); and so is an all-digit
    or `0x` host, `2130706433` among them, whatever it names, and
    `localhost`. Mirror of Model.dotlessHost, both held to the
    provider-hosts fixture."""
    text = str(host or "").lower()
    if text.endswith("."):
        text = text[:-1]
    if text == "" or "." in text:
        return False
    if ":" in text or text.startswith("["):
        address = parse_ip_literal(text)
        if address is not None and address.version == 6:
            return False
    return True
