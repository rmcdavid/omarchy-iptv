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
  STUB_REFUSE_PROPS  comma-separated property names whose `set_property` is
                 REFUSED, so the path a caller takes when a property cannot be
                 made safe is drivable at all. The value is left exactly as it
                 was: a double that refused and then stored would be more
                 forgiving than the thing it stands in for, in the direction
                 that matters. A `change-list` on such a list is refused too.
  STUB_PROFILES  a JSON list of profiles in mpv's `profile-list` shape
                 ({"name": .., "options": [{"key": .., "value": ..}]}),
                 appended to the built-in ones: the user's mpv.conf, for a
                 player whose pins are not all set from the command line.
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
    `request_log_messages` and to no other. (Earlier versions of this file
    emitted no line, moved the position before replying, and wrote both
    followups to the issuing connection alone; each was found more forgiving
    than mpv -- the last of them by F-MPV-1's own rule, after a write-up had
    excused it on the false premise that the plugin holds one connection.)
    An EVENT now goes to every live client, as mpv's do.

TLS PROPERTIES (D-SINK-16), and these are the lead's measurements on a real
player over a real IPC socket on 2026-10-07, not a guess:

  * `tls-verify` is READABLE, and on a player launched with no TLS token on its
    argv it reads **False** -- not "property unavailable". The stub answered
    unavailable for every name it did not know, which is LESS forgiving than
    mpv in a way that matters the wrong way round: a caller that has to assert
    the property before it loads would take its refusal path against the stub
    and never exercise the ordinary one.
  * `set_property tls-verify True` answers success and reads back True, and the
    next loadfile of a self-signed stream then fetches nothing (attacker GETs 1
    before, 0 after, on the same process, with a plain-http control still
    playing).
  * `stream-lavf-o` reads **{}** on such a player, takes a dict, and can be set
    back to {}.

What is NOT measured is mpv's error TEXT for a refused `set_property` on these
two -- the probe only ever saw them succeed. STUB_REFUSE_PROPS therefore injects
`property unavailable`, a string real mpv does emit for a property that exists
and cannot be read or written right now, and a caller must branch on
`error != "success"` rather than on those words. Said here rather than left
implicit, because a double whose made-up details read as measurements is how a
test double stops being evidence (CLAUDE.md rule 14).

THE PIN READ-BACK (D-SINK-43, D-SINK-44, 2026-10-29). Since the pin block the
helper refuses to load unless it can read, off the player, every OTHER TLS
pin: `demuxer-lavf-o` (its TLS keys), `load-auto-profiles` (False, mpv's
`no`), `option-info/<opt>/set-from-commandline` for the five per-file TLS
options, and -- when one of those is not set from the command line --
`profile-list`. This stub answered "property unavailable" for all four, so
every play into it was refused `tls_unverified`: a double LESS forgiving than
mpv in the direction that hides the ordinary path, the shape the TLS
properties above were fixed for. They are now answered from OPTIONS below,
and every value, coercion and refusal string there was measured on mpv
0.41.0 over a real IPC socket, windowless (`prlimit --core=0 timeout 20 env
-u DISPLAY -u WAYLAND_DISPLAY -u HYPRLAND_INSTANCE_SIGNATURE -u
DBUS_SESSION_BUS_ADDRESS mpv --no-config --vo=null --ao=null`, a private
HOME, the crash journal unchanged). The seven transcripts -- a player
launched with the pin block, one launched by 0.15.0's argv, four bare players
with the list forms, empty values and negations on the command line, and one
of the runtime edges the recheck measured -- are
tests/fixtures/stub-mpv-ipc.json,
and `--self-test` REPLAYS every step of them against this stub and requires
the same reply, so the model is held to the measurement rather than to its
author's reading of it. The steps it does not model are named in the replay
with the reason. What was measured, in short:

  * the initial values come from the launch argv, last token winning:
    `--demuxer-lavf-o=k=v,k=v` sets the list, `-append=k=v` and `-add=k=v`
    add one pair, `-remove=k` drops one, `-clr` empties it;
    `--load-auto-profiles=no|yes|auto` reads False, True or "auto"; a bare
    flag reads True, `--no-<flag>` False, and an EMPTY value (`--tls-verify=`,
    `--load-auto-profiles=`) reads True, mpv's `yes` -- so an empty token
    after an explicit `no` turns the option back on. `--no-load-auto-profiles`
    reads False.
  * `option-info/<opt>/set-from-commandline` is True for an option any token
    on the argv named, in any of those forms, and stays what it was through a
    runtime set_property; an option mpv does not have is `property not found`.
  * a flag takes true/false and the strings "yes"/"no", and the EMPTY string
    as "yes"; any other string is `unsupported format for accessing
    property`, a number or null `error accessing property`.
    `load-auto-profiles` also takes "auto", and refuses an integer with the
    FORMAT error and a fractional number with the ACCESS error.
    `osd-playlist-entry` takes title, filename and both. A key-value list
    takes a map of strings or a
    "k=v,k=v" string; a non-string value or a string without `=` is the
    format error, a list or null the access error. A refused set leaves the
    value alone.
  * `change-list <list> remove <key>` (and `del`, the same) succeeds whether
    or not the key is there; `append`/`add` take one "k=v" (commas stay in
    the value), `set`
    replaces the list, `clr` empties it; an empty key, a pair with no `=`, an
    unknown operation, an option that is not a key-value list and an option
    mpv does not have are all `error running command`.
  * `profile-list` on a --no-config player is mpv's thirteen built-in
    profiles, none of them [protocol.*] or [extension.*]; STUB_PROFILES adds
    the user's own, so the per-file profile threat is drivable at all.
  * a sub-path of a key-value list (`demuxer-lavf-o/tls_verify`) is `error
    accessing property` for a read and for a write; the write changes nothing.
  * a property mpv does not have is `property not found`, for a read and for
    a write. This stub still STORES a write of a name it does not model,
    where mpv refuses it -- the one place it stays more forgiving, named in
    the replay rather than hidden.

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

# ---- the options the helper's TLS read-back and the adopted-player pins read
# (D-SINK-43, D-SINK-44), modelled as mpv 0.41.0 answered them on 2026-10-29
# (the header, and tests/fixtures/stub-mpv-ipc.json, which --self-test
# replays). name -> (kind, the value a player launched without it reads).
OPTIONS = {
    "tls-verify": ("flag", False),
    "demuxer-lavf-propagate-opts": ("flag", True),
    "load-select": ("flag", True),
    "save-watch-history": ("flag", False),
    "load-unsafe-playlists": ("flag", False),
    "load-auto-profiles": ("tristate", "auto"),
    "stream-lavf-o": ("kvlist", {}),
    "demuxer-lavf-o": ("kvlist", {}),
    "reset-on-next-file": ("strlist", []),
    "osd-playlist-entry": ("choice", "title"),
    "log-file": ("string", ""),
    "watch-later-dir": ("string", ""),
}
# The three values of osd-playlist-entry, each measured taking (`both` on
# the recheck of 2026-10-29); "bogus" was measured refused.
CHOICES = {"osd-playlist-entry": ("title", "filename", "both")}
# Options whose option-info this stub answers without modelling their value:
# the helper reads user-agent's default when it restores the header.
INFO_ONLY = {"user-agent": "libmpv"}
OPTION_SUFFIXES = ("-set", "-append", "-add", "-remove", "-clr")
ERR_FORMAT = "unsupported format for accessing property"
ERR_ACCESS = "error accessing property"
ERR_NOT_FOUND = "property not found"
ERR_COMMAND = "error running command"
# mpv 0.41.0's built-in profiles, as `profile-list` lists them on a player
# started with --no-config (measured): the order, the names and the options.
BUILTIN_PROFILES = (
    ('box', (('profile', 'osd-box'), ('profile', 'sub-box'))),
    ('sub-box', (('sub-border-style', 'background-box'), ('sub-outline-size', '0'),
        ('sub-shadow-offset', '4'))),
    ('osd-box', (('osd-border-style', 'background-box'), ('osd-outline-size', '0'),
        ('osd-shadow-offset', '4'), ('script-opt', 'console-border_size=0'), ('script-opt',
        'console-corner_radius=0'), ('script-opt', 'context_menu-padding_y=0'), ('script-opt',
        'context_menu-corner_radius=0'), ('script-opt', 'stats-border_size=0'))),
    ('sw-fast', (('sws-scaler', 'bilinear'), ('sws-fast', 'yes'), ('zimg-scaler', 'bilinear'),
        ('zimg-dither', 'no'))),
    ('low-latency', (('audio-buffer', '0'), ('vd-lavc-threads', '1'), ('cache-pause', 'no'),
        ('demuxer-lavf-o-add', 'fflags=+nobuffer'), ('demuxer-lavf-probe-info', 'nostreams'),
        ('demuxer-lavf-analyzeduration', '0.1'), ('video-sync', 'audio'), ('interpolation', 'no'),
        ('video-latency-hacks', 'yes'), ('stream-buffer-size', '4k'))),
    ('gpu-hq', (('profile', 'high-quality'),)),
    ('high-quality', (('scale', 'ewa_lanczossharp'), ('hdr-peak-percentile', '99.995'),
        ('hdr-contrast-recovery', '0.30'))),
    ('fast', (('scale', 'bilinear'), ('dscale', 'bilinear'), ('dither', 'no'),
        ('correct-downscaling', 'no'), ('linear-downscaling', 'no'), ('sigmoid-upscaling', 'no'),
        ('hdr-compute-peak', 'no'), ('allow-delayed-peak-detect', 'yes'))),
    ('encoding', (('vo', 'lavc'), ('ao', 'lavc'), ('keep-open', 'no'), ('force-window', 'no'),
        ('gapless-audio', 'yes'), ('resume-playback', 'no'), ('load-scripts', 'no'), ('osc', 'no'),
        ('framedrop', 'no'))),
    ('libmpv', (('config', 'no'), ('idle', 'yes'), ('terminal', 'no'), ('input-terminal', 'no'),
        ('osc', 'no'), ('input-default-bindings', 'no'), ('input-vo-keyboard', 'no'),
        ('input-media-keys', 'no'), ('media-controls', 'no'))),
    ('builtin-pseudo-gui', (('terminal', 'no'), ('force-window', 'yes'), ('idle', 'once'),
        ('screenshot-dir', '~~desktop/'))),
    ('pseudo-gui', (('player-operation-mode', 'pseudo-gui'),)),
    ('default', ()),
)


def copy_value(value):
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    return value


def parse_kvlist(text):
    """mpv's `k=v,k=v` for a key-value list, or None when a pair has no `=`
    or no key. mpv's quoting forms are not modelled; nothing the helper or
    the harness sends uses them."""
    out = {}
    if text == "":
        return out
    for pair in text.split(","):
        key, sep, value = pair.partition("=")
        if not sep or key == "":
            return None
        out[key] = value
    return out


def coerce(name, value):
    """(the value mpv stores, None) for a set_property of a modelled option,
    or (None, mpv's refusal string). Measured, except where a line says not."""
    kind = OPTIONS[name][0]
    if kind in ("flag", "tristate"):
        if isinstance(value, bool):
            return value, None
        if isinstance(value, str):
            if value in ("yes", ""):
                return True, None                   # "" is mpv's yes (measured)
            if value == "no":
                return False, None
            if kind == "tristate" and value == "auto":
                return "auto", None
            return None, ERR_FORMAT                 # "bogus", "true"
        if kind == "tristate" and isinstance(value, int):
            return None, ERR_FORMAT                 # load-auto-profiles 1 and 0
        return None, ERR_ACCESS                     # tls-verify 1, load-select 0, 1.5, null
    if kind == "kvlist":
        if isinstance(value, dict):
            if all(isinstance(v, str) for v in value.values()):
                return dict(value), None
            return None, ERR_FORMAT                 # {"n": 1}
        if isinstance(value, str):
            parsed = parse_kvlist(value)            # "a=1,b=2" taken, "x" refused
            return (parsed, None) if parsed is not None else (None, ERR_FORMAT)
        return None, ERR_ACCESS                     # ["a"], null
    if kind == "strlist":
        if isinstance(value, list):
            if all(isinstance(v, str) for v in value):
                return list(value), None
            return None, ERR_FORMAT                 # [1]
        if isinstance(value, str):
            # "x" was measured TAKEN; what it then reads was not measured.
            return (value.split(",") if value else []), None
        return None, ERR_ACCESS                     # not measured
    if kind == "choice":
        if isinstance(value, str):
            return (value, None) if value in CHOICES[name] else (None, ERR_FORMAT)
        return None, ERR_ACCESS                     # not measured
    if isinstance(value, str):
        return value, None
    return None, ERR_ACCESS                         # log-file 5


def string_form(name, value):
    """What get_property_string answers for a modelled option (measured for
    a flag, the tri-state and a key-value list)."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    kind = OPTIONS[name][0]
    if kind == "kvlist":
        return ",".join("%s=%s" % pair for pair in value.items())
    if kind == "strlist":
        return ",".join(value)
    return value


def read_argv(argv):
    """The modelled options as a player launched with `argv` holds them, and
    the set of options any token named (option-info's set-from-commandline).
    mpv takes the LAST token for an option, which is what the plugin's
    trailing pins rely on, so the tokens are applied in order. A token whose
    value mpv would refuse is skipped here; mpv itself would refuse to start."""
    values = dict((name, copy_value(default)) for name, (_, default) in OPTIONS.items())
    named = set()
    for arg in argv:
        if not arg.startswith("--"):
            continue
        name, sep, value = arg[2:].partition("=")
        value = value if sep else None
        negated = False
        if name not in OPTIONS and name.startswith("no-") and name[3:] in OPTIONS and value is None:
            name, negated = name[3:], True
        suffix = ""
        if name not in OPTIONS:
            for candidate in OPTION_SUFFIXES:
                if name.endswith(candidate) and name[:-len(candidate)] in OPTIONS:
                    name, suffix = name[:-len(candidate)], candidate
                    break
        if name not in OPTIONS:
            continue
        kind = OPTIONS[name][0]
        if kind == "kvlist":
            if suffix == "-clr":
                new = {}
            elif suffix in ("-append", "-add") and value is not None:
                key, has, pair_value = value.partition("=")
                if not has or key == "":
                    continue
                new = dict(values[name])
                new[key] = pair_value
            elif suffix == "-remove" and value:
                new = dict(values[name])            # an absent key still names it
                new.pop(value, None)
            elif suffix in ("", "-set") and value is not None:
                new = parse_kvlist(value)
                if new is None:
                    continue
            else:
                continue
        elif kind == "strlist":
            if suffix == "-clr":
                new = []
            elif suffix in ("", "-set") and value is not None:
                new = value.split(",") if value else []
            else:
                continue
        elif suffix:
            continue
        elif negated:
            if kind not in ("flag", "tristate"):
                continue
            new = False                             # --no-load-auto-profiles reads false
        elif value is None:
            if kind not in ("flag", "tristate"):
                continue
            new = True                              # --load-select reads true
        else:
            new, err = coerce(name, value)
            if err:
                continue
        values[name] = new
        named.add(name)
    return values, named


def stub_profiles():
    """The built-in profiles in mpv's shape, then STUB_PROFILES'."""
    out = [{"name": name, "options": [{"key": k, "value": v} for k, v in options]}
           for name, options in BUILTIN_PROFILES]
    extra = os.environ.get("STUB_PROFILES", "")
    if extra:
        added = json.loads(extra)
        if not isinstance(added, list):
            raise ValueError("STUB_PROFILES must be a JSON list of profiles")
        out.extend(added)
    return out


def _env_float(name, default):
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return float(default)


class Stub(object):
    def __init__(self, path, clock=time.monotonic, tls_verify=False, argv=()):
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
        # D-SINK-16, and since 2026-10-29 the pin read-back. `tls-verify` and
        # `stream-lavf-o` are READABLE on a real player and read False and {}
        # on one launched with no TLS token on its argv (measured 2026-10-07,
        # see the header); they are not in `unset`, because mpv does not say
        # "unavailable" for them and a stub that did would push a caller down
        # its cannot-be-made-safe path on every run. The same now holds for
        # every option in OPTIONS (measured 2026-10-29).
        #
        # The INITIAL values come from the launch argv, as real mpv's do. They
        # were hardcoded, which modelled a pre-update player and lied about
        # every player this plugin starts -- so the "already safe, nothing to
        # migrate" path could not be reached at all without a display, which
        # is rule 10 in the direction that hides a case rather than forgives
        # one. Found by the review of the lane that taught the stub
        # tls-verify. `tls_verify=True` is shorthand for that one token.
        self.values, self.from_cli = read_argv(
            (["--tls-verify=yes"] if tls_verify else []) + [str(a) for a in argv])
        self.profiles = stub_profiles()
        # Absent until something sets or loads them - mpv reports
        # "property unavailable" for these on an idle player, and the
        # stand-down decision reads exactly that difference.
        self.unset = set(["path", "media-title", "title", "force-media-title",
                          "user-data/omarchy-iptv", "user-data"])
        for name in os.environ.get("STUB_IDLE_PROPS", "").split(","):
            if name:
                self.unset.add(name)
        # Names whose set_property is refused (D-SINK-16). Fault injection, so
        # the branch a caller takes when it cannot secure a player is reachable
        # from a test at all; see the header on what is and is not measured here.
        self.refuse = set(
            name for name in os.environ.get("STUB_REFUSE_PROPS", "").split(",") if name)

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
            if name in self.values:
                return (copy_value(self.values[name]), None)
            if name == "profile-list":
                return ([dict(p) for p in self.profiles], None)
            if name.startswith("option-info/"):
                option, _, field = name[len("option-info/"):].partition("/")
                if option not in OPTIONS and option not in INFO_ONLY:
                    return (None, ERR_NOT_FOUND)
                if field == "set-from-commandline":
                    return (option in self.from_cli, None)
                if field == "default-value":
                    return (copy_value(OPTIONS[option][1]) if option in OPTIONS else INFO_ONLY[option], None)
                return (None, "property unavailable")   # the node and its other fields: not modelled
            if "/" in name and name.split("/", 1)[0] in OPTIONS:
                return (None, ERR_ACCESS)               # demuxer-lavf-o/tls_verify
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
            # A name mpv does not have (measured: `property not found`).
            return (None, ERR_NOT_FOUND)

    def put(self, name, value):
        """None when it took, an mpv error string when it was refused.

        The refusal returns BEFORE anything is written, so a refused property
        keeps the value it had. A double that answered an error and stored the
        value anyway would let a caller's cannot-be-made-safe path look tested
        while the player it was meant to protect had quietly been changed
        (CLAUDE.md rule 10).
        """
        with self.lock:
            if name in self.refuse:
                return "property unavailable"
            if name == "profile-list" or name.startswith("option-info/"):
                return ERR_ACCESS                       # read-only (measured)
            if "/" in name and name.split("/", 1)[0] in OPTIONS:
                # demuxer-lavf-o/tls_verify and stream-lavf-o/tls_verify
                # (measured): refused, and the list is left as it was. It
                # used to fall through to the store below and answer success.
                return ERR_ACCESS
            if name in self.values:
                # Coerced and refused as mpv does; a refusal stores nothing.
                # set-from-commandline is NOT touched: a runtime set does not
                # change it (measured), which is why the pins survive one.
                stored, err = coerce(name, value)
                if err:
                    return err
                self.values[name] = stored
                self.unset.discard(name)
                return None
            self.unset.discard(name)
            if name == "pause":
                self.set_pause(value)
                return None
            if name.startswith("user-data/"):
                node = self.props.get("user-data")
                if not isinstance(node, dict):
                    node = {}
                node[name.split("/", 1)[1]] = value
                self.props["user-data"] = node
                self.unset.discard("user-data")
            self.props[name] = value
            return None

    def change_list(self, name, operation, value):
        """mpv's `change-list` on a key-value list (measured): None when it
        took, else mpv's refusal, with the list left as it was."""
        with self.lock:
            if name not in OPTIONS or OPTIONS[name][0] != "kvlist":
                return ERR_COMMAND                      # an unknown option, tls-verify
            if name in self.refuse:
                return ERR_COMMAND                      # fault injection, not a measurement
            current = dict(self.values[name])
            value = "" if value is None else str(value)
            if operation == "clr":
                current = {}
            elif operation in ("remove", "del"):        # del is remove (measured)
                if value == "":
                    return ERR_COMMAND
                current.pop(value, None)                # an absent key still succeeds
            elif operation in ("append", "add"):
                key, sep, pair_value = value.partition("=")
                if not sep or key == "":
                    return ERR_COMMAND                  # "novalue"
                current[key] = pair_value               # "k=v,w=x" -> {"k": "v,w=x"}
            elif operation == "set":
                parsed = parse_kvlist(value)
                if parsed is None:
                    return ERR_COMMAND
                current = parsed
            else:
                return ERR_COMMAND
            self.values[name] = current
            return None

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
                # mpv tracks the subscription per CLIENT; so does this.
                if (req.get("command") or [None])[0] == "request_log_messages":
                    with self.lock:
                        if conn not in self.log_conns:
                            self.log_conns.append(conn)
                reply = self.dispatch(req)
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

    def dispatch(self, req):
        """One reply for one request, and WHAT follows it. Who RECEIVES the
        followups is followup_targets(), which the self-test calls directly;
        a seek's move is deferred into `_apply` and its followups into
        `_followup`, both popped by serve(). This used to take a
        `subscribed` flag and filter the refusal line itself, which meant a
        second subscribed client never heard a refusal it did not cause --
        F-MPV-1's shape in the other direction."""
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
            elif verb == "get_property_string" and cmd[1] in OPTIONS:
                out["data"] = string_form(cmd[1], value)
            elif verb == "get_property_string":
                out["data"] = value if isinstance(value, str) else json.dumps(value)
            else:
                out["data"] = value
        elif verb in ("set_property", "set_property_string"):
            # D-SINK-16: a set_property can now ANSWER an error, because a
            # caller that must refuse to load when a property cannot be made
            # safe needs that reply to exist before its refusal is testable.
            err = self.put(cmd[1], cmd[2])
            if err:
                out["error"] = err
        elif verb == "change-list":
            err = self.change_list(cmd[1] if len(cmd) > 1 else "", cmd[2] if len(cmd) > 2 else "",
                                   cmd[3] if len(cmd) > 3 else "")
            if err:
                out["error"] = err
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

        def seek(self, target, mode="relative", apply=True):
            out = self.stub.dispatch({"command": ["seek", target, mode], "request_id": 7})
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
                # F-HARNESS-42. A connection becomes a broadcast target when
                # its serve THREAD runs `serve()` and appends it under the
                # lock -- not when connect() returns -- so under load A's seek
                # could be broadcast before B was a target, and B heard
                # nothing whatever the read bound was (red `[] != ['seek']`
                # at load 2-5, green alone). The bound was the symptom; this
                # wait is the cause closed: nothing is sent until both are
                # registered, bounded, and a timeout is named as its own
                # failure rather than as a missing event.
                deadline = time.time() + 5.0
                while time.time() < deadline:
                    with stub.lock:
                        if len(stub.conns) == 2:
                            break
                    time.sleep(0.01)
                with stub.lock:
                    self.assertEqual(len(stub.conns), 2, "both clients must be registered before anything is sent")
                send(a, "loadfile", "http://127.0.0.1:9/x.m3u8", "replace")
                lines(a, 1)
                # Just enough for time-pos to EXIST. A backward seek from a
                # young position is clamped to 0 by the stub (as mpv does
                # while the start is still cached), so it lands either way;
                # an earlier version waited for time-pos > 6 in 40 steps of
                # 0.1 s, which that loop can never reach, and so spent four
                # seconds of every gate run arriving where it started.
                for _ in range(20):
                    send(a, "get_property", "time-pos")
                    pos = lines(a, 1)
                    if pos and isinstance(pos[0].get("data"), (int, float)):
                        break
                    time.sleep(0.05)
                # Only A subscribes to log messages; both are live clients.
                send(a, "request_log_messages", "error")
                lines(a, 1)
                send(a, "seek", -5.0, "relative")
                got_a = lines(a, 2)
                # 10 s, not 2: B is a registered target (above), so the only
                # thing this bound now waits on is a local socket write, and
                # a green run returns at the first line; the cost of the
                # wider bound falls on red runs alone.
                got_b = lines(b, 1, bound=10.0)
                # A gets its reply and the event; B, which asked for nothing,
                # gets the event alone -- an event it did not cause.
                self.assertEqual([m.get("error") for m in got_a if "request_id" in m], ["success"])
                self.assertIn("seek", [m.get("event") for m in got_a])
                self.assertEqual([m.get("event") for m in got_b], ["seek"], "B was a registered target when the seek was sent and still heard no event within 10 s")
                self.assertNotIn("request_id", got_b[0])
                with stub.lock:
                    self.assertEqual(len(stub.conns), 2)
                    self.assertEqual(len(stub.log_conns), 1)   # A only
                # A DROPPED seek: the refusal line reaches the subscriber and
                # nobody else. Without this the log_conns half of the fix had
                # no check at all -- registering every client as a subscriber,
                # or none, left the suite green (the review's finding).
                send(a, "seek", 99999.0, "absolute")   # past the end: dropped, as mpv drops it
                got_a = lines(a, 2)
                self.assertEqual([m.get("error") for m in got_a if "request_id" in m], ["success"])
                levels = [m for m in got_a if m.get("event") == "log-message"]
                self.assertEqual(len(levels), 1, got_a)
                self.assertIn("Cannot seek in this stream", levels[0]["text"])
                # The absence half, asserted after a KNOWN point rather than
                # after a 0.5 s sleep (F-HARNESS-42's shape in the other
                # direction): B's own next command is answered by the same
                # writer, in order, so a refusal line wrongly aimed at B
                # would sit in front of B's reply. The first line B reads
                # after asking is therefore its reply, or the defect.
                send(b, "request_log_messages", "error")
                got_b = lines(b, 1, bound=10.0)
                self.assertEqual([("request_id" in m) for m in got_b], [True],
                                 "a client that never subscribed heard a refusal: %r" % (got_b,))
                # The follow-up loop writes to its targets OUTSIDE the lock,
                # in connection order, so a wrongly aimed line could in
                # principle land a few microseconds behind B's reply; a short
                # bounded tail closes that window and nothing else.
                self.assertEqual(lines(b, 1, bound=0.2), [], "a refusal reached a non-subscriber after its own reply")
                # A client that goes away stops being a target -- and stops
                # being a SUBSCRIBER, which is a second list and was the one
                # with no check. B subscribed just above, so the assertion
                # cannot pass on an empty list. Bounded wait: the serve thread
                # notices the close on its next read.
                with stub.lock:
                    self.assertEqual(len(stub.log_conns), 2)
                b.close()
                for _ in range(40):
                    with stub.lock:
                        if len(stub.conns) == 1 and len(stub.log_conns) == 1:
                            break
                    time.sleep(0.05)
                with stub.lock:
                    self.assertEqual(len(stub.conns), 1, "a closed connection is still a broadcast target")
                    self.assertEqual(len(stub.log_conns), 1, "a closed connection is still a log subscriber")
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

    class TlsProperties(unittest.TestCase):
        """D-SINK-16. What a real player answers for the two TLS properties, and
        what this stub has to answer so it is not more forgiving than mpv in the
        direction that hides a defect. The measurements are the lead's, on a real
        player over a real IPC socket on 2026-10-07; they are cited in the header
        and are not re-taken here.
        """

        def setUp(self):
            os.environ.pop("STUB_REFUSE_PROPS", None)
            self.stub = Stub("/nonexistent/stub.sock", clock=FakeClock())

        def tearDown(self):
            os.environ.pop("STUB_REFUSE_PROPS", None)

        def refusing(self, names):
            os.environ["STUB_REFUSE_PROPS"] = names
            return Stub("/nonexistent/stub.sock", clock=FakeClock())

        def reply(self, stub, *command):
            return stub.dispatch({"command": list(command), "request_id": 11})

        def test_tls_verify_reads_false_rather_than_unavailable(self):
            # The whole point: "property unavailable" would push a caller that
            # asserts TLS before loading down its refusal path on every run.
            self.assertEqual(self.stub.get("tls-verify"), (False, None))

        def test_stream_lavf_o_reads_an_empty_dict(self):
            self.assertEqual(self.stub.get("stream-lavf-o"), ({}, None))

        def test_the_launch_argv_decides_the_initial_reading(self):
            # Rule 10, in the direction that HIDES a case rather than forgiving
            # one. This was hardcoded False, which models a pre-update player
            # and lies about every player the fixed code launches, so the
            # "already safe, nothing to migrate" path could not be reached in
            # any test. Real mpv takes the LAST token, which is what the
            # plugin's trailing re-assertion relies on.
            self.assertEqual(Stub("/nonexistent/a.sock").get("tls-verify"), (False, None))
            self.assertEqual(Stub("/nonexistent/b.sock", tls_verify=True).get("tls-verify"), (True, None))

        def test_main_reads_the_tls_token_off_its_own_argv_last_one_winning(self):
            import types
            seen = {}
            saved = globals()["Stub"]
            def fake_stub(path, argv=()):
                # main() hands the Stub its whole argv; what the player then
                # READS is the real Stub's answer to that argv.
                seen["tls"] = saved(path, argv=argv).get("tls-verify")[0]
                raise SystemExit(0)
            globals()["Stub"] = fake_stub
            try:
                for argv, want in (
                    (["--input-ipc-server=/x"], False),
                    (["--input-ipc-server=/x", "--tls-verify=yes"], True),
                    (["--input-ipc-server=/x", "--tls-verify=yes", "--tls-verify=no"], False),
                    (["--input-ipc-server=/x", "--tls-verify=no", "--tls-verify=yes"], True),
                    (["--input-ipc-server=/x", "--no-tls-verify"], False),
                ):
                    seen.clear()
                    try:
                        main(argv)
                    except SystemExit:
                        pass
                    self.assertEqual(seen.get("tls"), want, argv)
            finally:
                globals()["Stub"] = saved

        def test_setting_tls_verify_succeeds_and_reads_back(self):
            out = self.reply(self.stub, "set_property", "tls-verify", True)
            self.assertEqual(out["error"], "success")
            self.assertEqual(self.stub.get("tls-verify"), (True, None))

        def test_stream_lavf_o_takes_a_dict_and_can_be_cleared(self):
            self.reply(self.stub, "set_property", "stream-lavf-o", {"tls_verify": "0"})
            self.assertEqual(self.stub.get("stream-lavf-o"), ({"tls_verify": "0"}, None))
            self.reply(self.stub, "set_property", "stream-lavf-o", {})
            self.assertEqual(self.stub.get("stream-lavf-o"), ({}, None))

        def test_a_refused_set_answers_an_error_and_leaves_the_value_alone(self):
            stub = self.refusing("tls-verify")
            out = self.reply(stub, "set_property", "tls-verify", True)
            self.assertNotEqual(out["error"], "success")
            # The half that makes the double honest: refused AND unchanged.
            self.assertEqual(stub.get("tls-verify"), (False, None))

        def test_refusing_one_property_refuses_only_that_one(self):
            stub = self.refusing("tls-verify")
            out = self.reply(stub, "set_property", "stream-lavf-o", {})
            self.assertEqual(out["error"], "success")

        def test_an_unknown_property_is_not_found(self):
            # The default did not get looser: only measured names moved. The
            # words did change, to mpv's own (measured 2026-10-29, the
            # replay below): "property unavailable" is what mpv says of a
            # property it HAS and cannot read right now.
            self.assertEqual(self.stub.get("no-such-mpv-property"),
                             (None, "property not found"))

    class PinReadBack(unittest.TestCase):
        """D-SINK-43, D-SINK-44: what the helper reads back before it loads, as
        mpv 0.41.0 answered it on 2026-10-29 (the header). The first case
        replays the seven measured transcripts whole; the rest name the rules
        one at a time, so a red run says which."""

        FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "tests", "fixtures", "stub-mpv-ipc.json")
        # The steps of the transcripts this stub does not model, each with
        # the reason. Everything else must answer exactly as mpv did.
        UNMODELLED = (
            (lambda c: c[:2] == ["get_property", "mpv-version"],
             "the stub names itself (VERSION), so a log line says which player answered"),
            (lambda c: c[0] == "get_property" and c[1].startswith("option-info/") and c[1].count("/") == 1,
             "the whole option-info node; the helper reads two of its fields, which ARE modelled"),
            (lambda c: c[:2] == ["set_property", "no-such-property"],
             "the stub STORES a write of a name it does not model where mpv refuses it: "
             "more forgiving, and kept so because it cannot list every property mpv has"),
            (lambda c: c[0] == "quit", "the stub exits on quit"),
        )

        def setUp(self):
            os.environ.pop("STUB_REFUSE_PROPS", None)
            os.environ.pop("STUB_PROFILES", None)
            with open(self.FIXTURE, encoding="ascii") as handle:
                self.transcripts = json.load(handle)["transcripts"]

        def tearDown(self):
            os.environ.pop("STUB_PROFILES", None)

        def transcript(self, name):
            return [t for t in self.transcripts if t["name"] == name][0]

        def stub(self, name):
            return Stub("/nonexistent/pin.sock", clock=FakeClock(), argv=self.transcript(name)["argv"][1:])

        def reply(self, stub, *command):
            out = stub.dispatch({"command": list(command), "request_id": 3})
            return {"error": out["error"], "data": out["data"]}

        def test_the_measured_transcripts_replay_identically(self):
            self.assertEqual(sorted(t["name"] for t in self.transcripts), ["argv-a", "argv-b", "argv-c", "argv-d", "pinned", "prepin", "runtime-b"])
            compared, wrong = 0, []
            for t in self.transcripts:
                stub = Stub("/nonexistent/pin.sock", clock=FakeClock(), argv=t["argv"][1:])
                for number, step in enumerate(t["steps"]):
                    command = step["command"]
                    if any(skip(command) for skip, _ in self.UNMODELLED):
                        continue
                    got = self.reply(stub, *command)
                    compared += 1
                    if got != step["reply"]:
                        wrong.append("%s step %d %r: mpv %r, stub %r" % (t["name"], number, command, step["reply"], got))
            self.assertEqual(wrong, [])
            # A replay that skipped its way to green proves nothing: 374 steps
            # were measured and all but the named ones are compared.
            self.assertGreaterEqual(compared, 360)

        def test_a_pinned_player_holds_every_pin_and_says_it_was_told_on_the_command_line(self):
            stub = self.stub("pinned")
            self.assertEqual(stub.get("demuxer-lavf-o"), ({"tls_verify": "1"}, None))
            self.assertEqual(stub.get("load-auto-profiles"), (False, None))
            self.assertEqual(stub.get("stream-lavf-o"), ({}, None))
            for option in ("tls-verify", "stream-lavf-o", "demuxer-lavf-o", "demuxer-lavf-propagate-opts",
                           "load-auto-profiles"):
                self.assertEqual(stub.get("option-info/%s/set-from-commandline" % option), (True, None), option)

        def test_a_player_from_before_the_pins_reads_as_one(self):
            stub = self.stub("prepin")
            self.assertEqual(stub.get("demuxer-lavf-o"), ({}, None))
            self.assertEqual(stub.get("load-auto-profiles"), ("auto", None))
            self.assertEqual(stub.get("option-info/tls-verify/set-from-commandline"), (True, None))
            for option in ("stream-lavf-o", "demuxer-lavf-o", "demuxer-lavf-propagate-opts", "load-auto-profiles"):
                self.assertEqual(stub.get("option-info/%s/set-from-commandline" % option), (False, None), option)

        def test_a_runtime_set_does_not_make_an_option_command_line_set(self):
            stub = self.stub("prepin")
            self.assertEqual(self.reply(stub, "set_property", "load-auto-profiles", "no")["error"], "success")
            self.assertEqual(stub.get("load-auto-profiles"), (False, None))
            self.assertEqual(stub.get("option-info/load-auto-profiles/set-from-commandline"), (False, None))

        def test_the_tristate_takes_its_words_and_refuses_the_rest_unchanged(self):
            stub = self.stub("prepin")
            for value, want in (("no", False), ("yes", True), ("auto", "auto"), (False, False), (True, True)):
                self.assertEqual(self.reply(stub, "set_property", "load-auto-profiles", value)["error"], "success")
                self.assertEqual(stub.get("load-auto-profiles"), (want, None))
            for value, err in (("bogus", "unsupported format for accessing property"),
                               (1, "unsupported format for accessing property"),
                               (None, "error accessing property")):
                self.assertEqual(self.reply(stub, "set_property", "load-auto-profiles", value)["error"], err)
                self.assertEqual(stub.get("load-auto-profiles"), (True, None))

        def test_a_flag_takes_yes_and_no_and_refuses_true_as_a_word(self):
            stub = self.stub("pinned")
            self.assertEqual(self.reply(stub, "set_property", "tls-verify", "no")["error"], "success")
            self.assertEqual(stub.get("tls-verify"), (False, None))
            for value, err in (("true", "unsupported format for accessing property"), (1, "error accessing property")):
                self.assertEqual(self.reply(stub, "set_property", "tls-verify", value)["error"], err)
                self.assertEqual(stub.get("tls-verify"), (False, None))

        def test_change_list_on_the_demuxer_options_as_measured(self):
            stub = self.stub("pinned")
            self.assertEqual(self.reply(stub, "change-list", "demuxer-lavf-o", "remove", "tls_verify")["error"], "success")
            self.assertEqual(stub.get("demuxer-lavf-o"), ({}, None))
            self.assertEqual(self.reply(stub, "change-list", "demuxer-lavf-o", "remove", "absent")["error"], "success")
            self.assertEqual(self.reply(stub, "change-list", "demuxer-lavf-o", "append", "verify=0")["error"], "success")
            self.assertEqual(stub.get("demuxer-lavf-o"), ({"verify": "0"}, None))
            for operation, value in (("append", "novalue"), ("remove", ""), ("bogus-op", "x")):
                self.assertEqual(self.reply(stub, "change-list", "demuxer-lavf-o", operation, value)["error"],
                                 "error running command")
            self.assertEqual(stub.get("demuxer-lavf-o"), ({"verify": "0"}, None))
            self.assertEqual(self.reply(stub, "change-list", "tls-verify", "remove", "x")["error"], "error running command")
            self.assertEqual(self.reply(stub, "change-list", "demuxer-lavf-o", "clr", "")["error"], "success")
            self.assertEqual(stub.get("demuxer-lavf-o"), ({}, None))

        def test_a_refused_list_is_refused_by_change_list_too(self):
            os.environ["STUB_REFUSE_PROPS"] = "demuxer-lavf-o"
            try:
                stub = self.stub("pinned")
            finally:
                os.environ.pop("STUB_REFUSE_PROPS", None)
            self.assertNotEqual(self.reply(stub, "change-list", "demuxer-lavf-o", "remove", "tls_verify")["error"], "success")
            self.assertEqual(stub.get("demuxer-lavf-o"), ({"tls_verify": "1"}, None))

        def test_profile_list_is_the_builtin_thirteen_and_then_the_users(self):
            names = [p["name"] for p in self.stub("prepin").get("profile-list")[0]]
            self.assertEqual(len(names), 13)
            self.assertEqual([n for n in names if n.startswith(("protocol.", "extension."))], [])
            os.environ["STUB_PROFILES"] = json.dumps([{"name": "protocol.https", "options": [
                {"key": "stream-lavf-o", "value": "tls_verify=0"}]}])
            stub = self.stub("prepin")
            self.assertEqual(stub.get("profile-list")[0][-1]["name"], "protocol.https")
            self.assertEqual(self.reply(stub, "set_property", "profile-list", [])["error"], "error accessing property")

        def test_option_info_of_an_option_mpv_does_not_have_is_not_found(self):
            stub = self.stub("pinned")
            self.assertEqual(stub.get("option-info/no-such-option/set-from-commandline"), (None, "property not found"))
            self.assertEqual(stub.get("option-info/user-agent/default-value"), ("libmpv", None))
            self.assertEqual(self.reply(stub, "set_property", "option-info/tls-verify/set-from-commandline", False)["error"],
                             "error accessing property")

    suite = unittest.TestSuite([
        unittest.defaultTestLoader.loadTestsFromTestCase(SeekSemantics),
        unittest.defaultTestLoader.loadTestsFromTestCase(TlsProperties),
        unittest.defaultTestLoader.loadTestsFromTestCase(PinReadBack),
    ])
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


def main(argv):
    if argv[:1] == ["--self-test"]:
        return self_test()
    path = None
    # D-SINK-16. mpv resolves a repeated option by taking the LAST token, which
    # is why the plugin re-asserts --tls-verify=yes after the user's arguments
    # (and since 2026-10-29 the whole pin block); a stub that ignored its argv
    # could not model a player launched by the FIXED code at all, so the
    # "already safe, nothing to migrate" path was unreachable without a
    # display. The whole argv goes to the Stub, which reads it as mpv does
    # (read_argv).
    for arg in argv:
        if arg.startswith("--input-ipc-server="):
            path = arg.split("=", 1)[1]
    if not path:
        # The "spawned but never binds" shape. Sleep past --spawn-timeout.
        time.sleep(float(os.environ.get("STUB_LIFE", "60")))
        return 0
    stub = Stub(path, argv=argv)
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
