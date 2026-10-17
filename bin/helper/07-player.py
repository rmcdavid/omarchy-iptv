# A part of bin/omarchy-iptv (D-REL-7), not a module: the helper compiles
# this file into its own namespace in the order its HELPER_PARTS lists, so
# a part sees every name the parts before it define. Run the helper.
from __future__ import annotations
# --------------------------------------------------------------- player
# The detached player (ARCHITECTURE-PLAYER.md (dev branch)). mpv runs as a setsid'd
# grandchild of this helper, reparented to the session subreaper, so it
# outlives every shell restart and is still reaped at logout by the
# compositor's own cgroup. The shell observes it over mpv's JSON IPC socket.
#
# Nothing channel-specific is ever on mpv's command line: the URL, the headers
# and the title travel over the 0600 socket instead (S-03, requirement 9).
# Every verb is idempotent, serialised by one flock with an inode re-check,
# and ordered by the caller's --seq intent number rather than by the order the
# kernel happens to grant the lock in.

PLAYER_LOCK_FILE = "player.lock"
PLAYER_STASH_SCHEMA = 1
# Two sibling top-level user-data nodes (4.6), probe-verified on mpv 0.41: a
# second client reads back the identical object, the top level is not
# writable, and there is no delete. The record dies with the process it
# describes, which is exactly why it is not a file on disk.
USER_DATA_STASH = "user-data/omarchy-iptv"
USER_DATA_OWNER = "user-data/omarchy-iptv-owner"
# M5-01 live rewind (M5-01-LIVE-REWIND.md 2.2, dev branch): the third sibling node,
# the zero point "behind live" is measured from. Keyed by the stash's
# `entryId`, so a zap -- which changes the entry id -- invalidates it by
# construction, and a shell restart recovers it from the player the way
# pause state is recovered today. Written lazily by `status`, `pause` and
# `seek`, whichever first sees a numeric `time-pos` for the current entry;
# `probe` reads it and never writes (the probe is side-effect-free).
USER_DATA_REWIND = "user-data/omarchy-iptv-rewind"
REWIND_SCHEMA = 1
PLAYER_GENERIC_FAILURE = "Playback stopped unexpectedly"   # mirrors Model.PLAYER_GENERIC_FAILURE
# The D-LIVE-17 ladder, unchanged: quit at 0, SIGTERM at 2 s, SIGKILL at 4 s.
STOP_QUIT_GRACE_MS = 2000
STOP_KILL_GRACE_MS = 2000
STOP_SETTLE_MS = 500
DEFAULT_LOCK_TIMEOUT = 6.0
DEFAULT_SPAWN_TIMEOUT = 5.0
DEFAULT_FIRST_LOAD_TIMEOUT = 3.0
DEFAULT_ORPHAN_GRACE = 6.0
LOCK_POLL_S = 0.05
LOCK_RETRIES = 5
# X1/X2: the two settle call sites that hold no lock of their own take one
# briefly. Short on purpose - a probe that cannot have it simply does not
# unlink, which is the safe half of the decision.
SETTLE_LOCK_TIMEOUT = 0.5
SPAWN_POLL_S = 0.02
STOP_POLL_S = 0.05
LAUNCH_STDERR_MAX = 4096          # PO-6: the launch window's stderr, memory only
PLAYER_UMASK = 0o077              # PO-11: 0600 files / 0700 dirs, requirement 10
# Mirror of Model.splitMpvArgs (4.12). The helper re-validates every
# --mpv-arg because bin/omarchy-iptv is a public CLI, and a parity test pins
# the two reserved sets equal.
MPV_ARG_RE = re.compile(r"^--[a-z0-9][a-z0-9-]*(=.*)?$")
MPV_RESERVED = frozenset((
    "--input-ipc-server", "--wayland-app-id", "--title", "--force-media-title",
    "--idle", "--input-ipc-client", "--script", "--scripts", "--config-dir",
    # D-SINK-4: reserved rather than merely defaulted off. `--load-scripts=no`
    # is in the base argv, but user mpv_args are concatenated AFTER it, so a
    # pasted `--load-scripts=yes` would win and put the credentialed stream
    # URL back on the session bus via mpv-mpris. Unlike --ytdl (PO-5) this one
    # guards a credential and has no legitimate counter-position.
    "--load-scripts",
    # D-SINK-2: --script is mpv's ALIAS for --scripts-append, so naming only
    # the alias reserved nothing. Matching is by base name now (see
    # filter_mpv_args), and --include loads a config that can set any of these.
    "--include",
    # D-SINK-13, and the reason layer 2 is not the whole fix.
    # `--stream-lavf-o` hands key=value straight to libavformat for the
    # STREAM, and FFmpeg's own AVOption is `tls_verify` -- a different knob
    # from mpv's `--tls-verify`, reaching the same place -- so the trailing
    # re-assertion cannot outvote it. Measured 2026-10-07 with BOTH
    # tls-verify tokens in place: `--stream-lavf-o=tls_verify=0` PLAYED the
    # attacker's stream, as did the -add, -append and -set forms.
    # mpv_option_base strips the list suffixes, so this covers all six.
    # `--demuxer-lavf-o` is NOT reserved: measured, it does not bypass.
    "--stream-lavf-o",
    "--log-file", "--dump-stats", "--stream-record", "--save-position-on-quit",
    "--watch-later-dir", "--osd-msg1", "--osd-msg2", "--osd-msg3",
    "--term-status-msg", "--screenshot-template",
    # M5-01 (design 2.6, D3). The privacy-relevant switch is not whether mpv
    # caches on disk but whether the file OUTLIVES the process: mpv unlinks
    # its cache file the moment it is created (F-RWD-5), and `whendone` or
    # `no` here keeps a copy of the stream at a path the plugin never listed,
    # which is `--stream-record`'s class. `--cache-on-disk` itself stays a
    # user choosing their own disk (PO-5's shape) and is warned about below.
    "--demuxer-cache-unlink-files",
    # D-SINK-13, layer 3 of four. mpv's `--tls-verify` defaults to NO, so the
    # plugin was handing provider headers and an HTTPS stream URL to a peer it
    # never authenticated; measured by the lead on 2026-10-07, the shipped argv
    # played a self-signed server, exit 0. The TLS peer is a rule 5 sink and
    # the one that gets the credential unredacted.
    #
    # Reserved here AND re-asserted as the final token in mpv_launch_argv. Not
    # alternatives: the trailing token is what makes verification safe (a later
    # command-line token beats an earlier one, and `--profile` carries
    # arbitrary options), this entry is what makes the refusal honest, so a
    # pasted `--tls-verify=no` is reported dropped instead of silently undone.
    # Both spellings fall out of the existing `no_form` arm in
    # filter_mpv_args: it rebuilds `--tls-verify` from `--no-tls-verify` and
    # finds it here, so no new branch is needed.
    #
    # Deliberately NOT reserved: `--tls-ca-file`, the targeted escape for a
    # provider with a self-signed or private-CA certificate (measured working
    # behind the trailing token - the `--screenshot-dir` shape, a user choice
    # that lands after ours and wins); and `--profile`, a legitimate mpv
    # feature that the trailing token makes harmless. `--tls-cert-file` and
    # `--tls-key-file` are CLIENT certificates, a different thing, untouched.
    "--tls-verify",
))
# D-SINK-13, layers 1 and 2: one string, written into the argv twice on
# purpose. Mirror of Model.MPV_TLS_VERIFY; the two literals are pinned to each
# other by the shared player-argv.json vectors. See mpv_launch_argv.
MPV_TLS_VERIFY = "--tls-verify=yes"
# D-SINK-16. The same two knobs, named as mpv PROPERTIES rather than as
# command-line options, because an ADOPTED player has no launch argv left to
# change: all four of D-SINK-13's layers live on the argv, so a process started
# by 0.12.1 -- mpv's own default is `tls-verify=no` -- goes on not verifying
# after the upgrade while this helper goes on sending it new provider headers
# and a new credentialed URL on every zap. Mirrors Model.MPV_TLS_VERIFY_PROP /
# Model.MPV_STREAM_OPTS_PROP.
MPV_TLS_VERIFY_PROP = "tls-verify"
MPV_STREAM_OPTS_PROP = "stream-lavf-o"
PLAYER_VERBS = ("start", "stop", "restart", "probe", "orphan-check", "pause", "tracks", "seek")
# Mirror of MPV_HANDOFF (model/mpv.mjs, internal to the model) and friends (PO-10, D-PLY-5). These options are
# allowed - PO-5 keeps `--ytdl` as the documented escape hatch for links that
# are not direct streams - but each one puts the credentialed stream address
# on a SECOND program's command line, so the user is told at the moment the
# option is in force. Pinned to the JavaScript by the `mpvHandoff` vectors in
# the player-argv.json. fixture (dev branch)
MPV_HANDOFF = frozenset(("--ytdl-format", "--ytdl-raw-options"))
MPV_HANDOFF_SCRIPT_OPTS = frozenset(("--script-opts", "--script-opt"))
MPV_YTDL_OFF = frozenset(("no", "0", "false"))
MPV_HANDOFF_TEXT = " hands the stream address to another program"
# M5-01 (design 2.6): the same PO-10 mechanism, a different cost. `--cache-on-disk`
# writes the stream to the user's own disk continuously (1.8 to 4.5 GiB per
# hour at the measured bitrates, into a file mpv unlinks at creation, so `ls`
# and `du` show nothing). Allowed, because it is the user's disk; said out
# loud, because nothing else would say it. Mirror of Model.MPV_DISK_WARN.
MPV_DISK_WARN = frozenset(("--cache-on-disk",))
MPV_DISK_TEXT = " writes the stream to disk while it plays"
MPV_LIST_SUFFIX_RE = re.compile(r"-(add|append|set|pre|clr|del|remove|toggle)$")


def _monotonic() -> float:
    """Indirection so tests can drive the stop ladder with a fake clock."""
    return time.monotonic()


def _sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def filter_mpv_args(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Mirror of Model.splitMpvArgs on already-split tokens."""
    args: list[str] = []
    rejected: list[str] = []
    for token in tokens or []:
        text = str(token)
        name = text.split("=", 1)[0]
        # D-SINK-2: the BASE name decides. `mpv_option_base` was defined
        # fifteen lines below this filter and never used by it, so
        # `--scripts-append` -- which mpv's own --list-options calls the
        # option that `--script` is an ALIAS for -- was accepted here and by
        # the JavaScript mirror.
        base = mpv_option_base(name)
        bare = "--" + name[5:] if name.startswith("--no-") else ""
        no_form = bool(bare) and (bare in MPV_RESERVED or mpv_option_base(bare) in MPV_RESERVED)
        if not MPV_ARG_RE.match(text) or name in MPV_RESERVED or base in MPV_RESERVED or no_form:
            rejected.append(text)
        else:
            args.append(text)
    return args, rejected


def mpv_option_base(name: str) -> str:
    """Mirror of Model.mpvOptionBase: `--opt-append` and `--opt-set` set the
    same option `--opt` does, so the base name is what decides."""
    return MPV_LIST_SUFFIX_RE.sub("", str(name))


def mpv_arg_hands_off_url(token: str) -> str:
    """Mirror of Model.mpvHandoffName. "" when the token is harmless, else the
    option NAME. The VALUE is never returned: it can carry a credentialed URL
    of its own (a proxy in --ytdl-raw-options) and a warning is a sink (R12).
    """
    text = str(token)
    name, _, value = text.partition("=")
    if name.startswith("--no-"):          # --no-ytdl turns the handoff OFF
        return ""
    base = mpv_option_base(name)
    if base == "--ytdl":
        return "" if value.lower() in MPV_YTDL_OFF else name
    if base in MPV_HANDOFF:
        return name
    if base in MPV_HANDOFF_SCRIPT_OPTS:
        return name if "ytdl" in value else ""
    return ""


def mpv_arg_writes_disk(token: str) -> str:
    """Mirror of Model.mpvDiskName: the option NAME when the token turns the
    disk cache on, "" otherwise. A flag like `--ytdl`: `--no-cache-on-disk`
    and `=no` turn it off and are silent."""
    text = str(token)
    name, _, value = text.partition("=")
    if name.startswith("--no-"):
        return ""
    if mpv_option_base(name) in MPV_DISK_WARN:
        return "" if value.lower() in MPV_YTDL_OFF else name
    return ""


def mpv_arg_warning(token: str) -> str:
    """Mirror of Model.mpvArgWarning: the whole warning line for one token,
    or "". The two costs carry their own sentence, so the user is told WHAT
    the option does rather than that it is "dangerous"."""
    name = mpv_arg_hands_off_url(token)
    if name:
        return "mpvArg " + name + MPV_HANDOFF_TEXT
    name = mpv_arg_writes_disk(token)
    if name:
        return "mpvArg " + name + MPV_DISK_TEXT
    return ""


def mpv_arg_warnings(tokens: list[str]) -> list[str]:
    """Mirror of Model.mpvArgWarnings: one line per distinct option, in the
    order the user wrote them."""
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens or []:
        line = mpv_arg_warning(token)
        if not line or line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out


def player_dirs(sock_path: str, state_override: str | None = None) -> dict[str, str]:
    """Where the player is allowed to write (PO-11, D-PLY-7).

    mpv's own key bindings are live on its window and two of them write a
    durable file: `s` takes a screenshot and `Q` (quit-watch-later) writes a
    resume record. Both used to land wherever the shell happened to be - the
    user's home for the screenshot, mpv's own ~/.local/state/mpv tree for the
    resume record - at mode 0644, outside every list of files this plugin
    says it writes.

    - `cwd` is the runtime directory (0700, already ensured for the socket).
      It is where anything relative still lands, so a cwd-relative write we
      have not anticipated goes somewhere private and disappears at logout
      instead of accumulating in $HOME.
    - `screenshots` is durable on purpose: a screenshot is something the user
      asked for, so the runtime directory would be data loss at logout. It
      lives under the state directory this plugin already owns and documents.
    - `watchLater` is a resume position for a live stream, which is never
      worth keeping: ephemeral, private, gone at logout.
    - `shaderCache` is D-PLY-10, ruling CL2: mpv compiles its shaders into
      $XDG_CACHE_HOME/mpv/ otherwise, which is outside every list of files
      this plugin says it writes. A shader cache is content-free and
      regenerable - it is not keyed to anything that was watched - so the
      runtime directory is the right home: already 0700, already documented,
      gone at logout, and it adds NO durable path and nothing to clean up at
      uninstall. Containment here is a sensible default, not a guarantee:
      neither option is reserved, because MPV_RESERVED is a privacy
      instrument and a content-free cache does not belong on it (CL2).
    """
    runtime = os.path.dirname(sock_path)
    return {
        "cwd": runtime,
        "screenshots": os.path.join(state_dir(state_override), "screenshots"),
        "watchLater": os.path.join(runtime, "watch-later"),
        "shaderCache": os.path.join(runtime, "shader-cache"),
    }


def mpv_launch_argv(sock_path: str, mpv_args: list[str],
                    dirs: dict[str, str] | None = None) -> list[str]:
    """Mirror of Model.buildMpvArgv, pinned by the player-argv.json. fixture (dev branch)

    No URL, no "--", no header options, no per-channel title: the first
    channel arrives over IPC like every later one (S-03). `--idle=once` (PO-1)
    idles at startup and still exits when the playlist finishes, which keeps
    today's UX and the degraded status-poll fallback.

    The two output directories (PO-11) are fixed options, so a user who wants
    their screenshots elsewhere can still say so: `--screenshot-dir` is not
    reserved and user tokens land after these. `--watch-later-dir` IS
    reserved, because a resume record naming a stream path has no business
    being redirected back into $HOME.

    The two cache directories are D-PLY-10 / CL2, in the same shape and for
    the same reason: mpv's shader and ICC caches default into
    $XDG_CACHE_HOME/mpv/, outside this plugin's tree. Neither is reserved -
    both are content-free - so a user token can still point them elsewhere.

    D-SINK-13 breaks the "user tokens land last" shape on purpose, for exactly
    one option: `--tls-verify=yes` appears in the base argv AND again as the
    final token, after the user's. See the comment on the return.
    """
    where = dirs or player_dirs(sock_path)
    return [
        "mpv",
        "--input-ipc-server=%s" % sock_path,
        "--wayland-app-id=omarchy-iptv",
        "--force-window=immediate",
        "--idle=once",
        "--keep-open=no",
        "--title=%sIPTV" % MPV_RAW_PREFIX,
        "--force-media-title=IPTV",
        "--msg-level=all=error",
        "--ytdl=no",
        # D-SINK-4. mpv autoloads every script in its system directory, which
        # here includes mpv-mpris; it publishes `xesam:url` -- the stream URL,
        # credentials and all -- on the session bus for as long as a channel
        # plays. Measured on the real bus. mpv-mpris has no configuration
        # surface, so keeping it and not leaking is not available, and this
        # plugin loads no script of its own. Cost: Omarchy's media widget
        # stops showing the channel, which the bar widget already shows.
        "--load-scripts=no",
        "--screenshot-dir=%s" % where["screenshots"],
        "--watch-later-dir=%s" % where["watchLater"],
        "--gpu-shader-cache-dir=%s" % where["shaderCache"],
        "--icc-cache-dir=%s" % where["shaderCache"],
        # D-SINK-13, LAYER 1: stated here, where a reader looks to find out what
        # the player is launched with. mpv's own default is `--tls-verify=no`
        # (`mpv --list-options`, 0.41.0). Layer 1 alone is NOT the fix.
        MPV_TLS_VERIFY,
    # D-SINK-13, LAYER 2, and the line that actually guarantees verification.
    #
    # THE TWO OCCURRENCES OF MPV_TLS_VERIFY ARE NOT REDUNDANT. Removing either
    # is a security change, not a tidy-up, and this one is the one that holds.
    # mpv takes the LAST token for a repeated option, so user mpv_args land
    # between the base argv and this one and are overridden rather than
    # overriding. That matters because `--tls-verify` is not the only way off:
    # `--profile=NAME` applies every option in that profile where the token
    # appears, and a profile in the user's own mpv.conf can set
    # `tls-verify=no`. Measured by the lead on 2026-10-07: with layer 1 only,
    # `--profile=evil` PLAYED a self-signed stream (exit 0); with this trailing
    # token the same command refused it (exit 2), as did `--tls-verify=no` and
    # `--no-tls-verify` behind it. So this layer covers the indirections nobody
    # has enumerated, which is why `--profile` is not reserved. A bare `--`
    # cannot escape it: MPV_ARG_RE requires `--` followed by a lowercase letter
    # or digit, so filter_mpv_args puts `--` in the rejected bucket (measured by
    # calling it). And it leaves the escape hatch intact: `--tls-ca-file` is
    # unreserved and names a CA for THIS token to verify against.
    #
    # Mirror of Model.buildMpvArgv's return; pinned to it by the
    # `--profile=evil` vector in the player-argv.json fixture (dev branch),
    # whose user arguments are what make this line visible at all.
    ] + list(mpv_args or []) + [MPV_TLS_VERIFY]


def stop_escalation(stage: str) -> dict[str, Any]:
    """Mirror of Model.stopEscalation (the reducer of record)."""
    text = stage or ""
    if text == "":
        return {"action": "quit", "signal": 0, "waitMs": STOP_QUIT_GRACE_MS}
    if text == "quit":
        return {"action": "term", "signal": 15, "waitMs": STOP_KILL_GRACE_MS}
    if text == "term":
        return {"action": "kill", "signal": 9, "waitMs": 0}
    return {"action": "kill", "signal": 0, "waitMs": 0}


def ended_verdict(end_file: dict[str, Any] | None, user_stopped: bool = False,
                  stopping: bool = False) -> dict[str, Any]:
    """Mirror of Model.endedVerdict (4.8): why the player ended.

    The entry id is deliberately not consulted - it decides which channel the
    message names, never whether there is one (F4, the gate fails open).
    """
    if user_stopped or stopping:
        return {"notify": False, "reason": "", "kind": "silent"}
    if not isinstance(end_file, dict):
        return {"notify": True, "reason": PLAYER_GENERIC_FAILURE, "kind": "failed"}
    reason = str(end_file.get("reason") or "")
    if reason == "redirect":
        # The .m3u8 master resolution IPTV uses most: never terminal.
        return {"notify": False, "reason": "", "kind": "ignored"}
    if reason in ("quit", "eof"):
        return {"notify": False, "reason": "", "kind": "silent"}
    detail = redact_urls(end_file.get("fileError") or end_file.get("file_error") or "").strip()
    return {"notify": True, "reason": detail or PLAYER_GENERIC_FAILURE, "kind": "failed"}


def player_stash(channel_id: str, name: str, group: str, scope: str, source_key: str,
                 since: int, seq: int, entry_id: int | None = None,
                 playing: bool = True, verb: str = "play") -> dict[str, Any]:
    """Mirror of Model.playerStash: the now-playing record mpv carries for us.

    `launchedFrom` is the zap-ring scope - pure UI intent no mpv property
    could ever report, which is why the shell's own value is stashed here and
    echoed back on reattach.

    `verb` says which slot wrote the record last, and it exists because `seq`
    stopped being able to say so. The zap used to hardcode `seq` to 0, which
    made "not zero" a usable stand-in for "a player verb wrote this" - the
    reading wave two's evidence leaned on. Now that both sides carry a real
    intent number the two can be COMPARED, which is the point, but the
    writer has to be named outright rather than inferred from a zero.
    """
    return {
        "schema": PLAYER_STASH_SCHEMA,
        "playing": bool(playing),
        "id": str(channel_id or ""),
        "name": str(name or ""),
        "group": str(group or ""),
        "launchedFrom": str(scope or ""),
        "sourceKey": str(source_key or ""),
        "since": int(since or 0),
        "entryId": entry_id if isinstance(entry_id, int) and entry_id > 0 else None,
        "seq": int(seq or 0),
        "verb": str(verb or ""),
    }


def source_key_of(directory: str) -> str:
    """The source key a per-source cache directory belongs to, so the stash
    can say which playlist the channel id resolves against without the URL
    or the key crossing a command line of its own."""
    parent, base = os.path.split(os.path.normpath(directory or ""))
    if os.path.basename(parent) == SOURCES_DIR and SOURCE_KEY_RE.match(base or ""):
        return base
    return ""


# ------------------------------------------------------- process discovery
# `connect()` only ever answers "responsive": it succeeds through the listen
# backlog against a wedged mpv. The authoritative existence check is a /proc
# scan for our exact --input-ipc-server token plus our uid, which is also the
# only way to obtain a pid for an mpv whose IPC is dead - the very case the
# stop ladder exists for.

def proc_cmdline(pid: int) -> list[str]:
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as handle:
            raw = handle.read()
    except OSError:
        return []
    return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]


def proc_start_time(pid: int) -> str:
    """Field 22 of /proc/<pid>/stat, read after the last ')' so a comm
    containing spaces or parentheses cannot shift the fields."""
    try:
        with open("/proc/%d/stat" % pid, "rb") as handle:
            data = handle.read().decode("utf-8", "replace")
    except OSError:
        return ""
    close = data.rfind(")")
    if close == -1:
        return ""
    fields = data[close + 1:].split()
    return fields[19] if len(fields) > 19 else ""


def proc_is_ours(pid: int) -> bool:
    try:
        return os.stat("/proc/%d" % pid).st_uid == os.getuid()
    except OSError:
        return False


def find_player(sock_path: str) -> list[dict[str, Any]]:
    """Every live process of ours whose argv carries our exact socket token."""
    token = "--input-ipc-server=%s" % sock_path
    found: list[dict[str, Any]] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return found
    mine = os.getpid()
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid == mine:
            continue
        if token not in proc_cmdline(pid) or not proc_is_ours(pid):
            continue
        found.append({"pid": pid, "startTime": proc_start_time(pid)})
    found.sort(key=lambda record: record["pid"])
    return found


def still_the_player(record: dict[str, Any], sock_path: str) -> bool:
    """Re-verified immediately before every signal: pid alive, same start
    time, same socket token, same uid - so a recycled pid is never signalled."""
    pid = int(record.get("pid") or 0)
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    if not proc_is_ours(pid):
        return False
    recorded = str(record.get("startTime") or "")
    if recorded and proc_start_time(pid) != recorded:
        return False
    return ("--input-ipc-server=%s" % sock_path) in proc_cmdline(pid)


# ------------------------------------------------------------------ lock

def player_lock_path(sock_path: str) -> str:
    return os.path.join(os.path.dirname(sock_path), PLAYER_LOCK_FILE)


def acquire_lock(path: str, timeout: float) -> int:
    """flock with an inode re-check.

    A plain flock is defeated by unlinking the lock file and recreating it:
    the winner then holds a lock on an orphaned inode while a second launcher
    locks the new one. After every grant we compare fstat(fd) with stat(path)
    and start over when they differ. The kernel releases the lock on any
    death including SIGKILL, so it can never go stale.
    """
    deadline = _monotonic() + max(0.0, float(timeout))
    for _ in range(LOCK_RETRIES):
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            # R23d (rule 15): only a regular file is made 0600, decided on
            # the descriptor. O_RDWR never blocks on a FIFO (Linux), so the
            # open above needs no O_NONBLOCK; the chmod is what is gated.
            if stat.S_ISREG(os.fstat(fd).st_mode):
                os.fchmod(fd, 0o600)
        except OSError:
            pass
        granted = False
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                granted = True
                break
            except OSError as error:
                if error.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                    os.close(fd)
                    raise HelperError("busy", "could not lock the player: %s" % (error.strerror or error))
                if _monotonic() >= deadline:
                    break
                _sleep(LOCK_POLL_S)
        if not granted:
            os.close(fd)
            raise HelperError("busy", "another player command holds the lock")
        try:
            same_inode = os.fstat(fd).st_ino == os.stat(path).st_ino
        except OSError:
            same_inode = False
        if same_inode:
            return fd
        os.close(fd)
        if _monotonic() >= deadline:
            break
    raise HelperError("busy", "the player lock file kept being replaced")


def release_lock(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass


def read_lock_record(fd: int) -> dict[str, Any]:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, 4096)
    except OSError:
        return {}
    try:
        document = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def read_lock_file(sock_path: str) -> dict[str, Any]:
    """The record without taking the lock (probe is lock-free)."""
    try:
        with os.fdopen(open_regular(player_lock_path(sock_path)), "rb") as handle:
            document = json.loads(handle.read().decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return document if isinstance(document, dict) else {}


def record_seq(record: dict[str, Any]) -> int:
    value = record.get("seq")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def write_lock_record(fd: int, seq: int, verb: str) -> None:
    payload = json.dumps({"schema": 1, "seq": int(seq), "verb": verb, "at": int(time.time())})
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        os.truncate(fd, 0)
        os.write(fd, payload.encode("utf-8"))
    except OSError:
        pass


def check_seq(record: dict[str, Any], seq: int, verb: str) -> None:
    """Ordering by issue time, not by lock-grant order (4.10): a verb whose
    intent number is older than the recorded one does nothing at all."""
    if seq > 0 and record_seq(record) > seq:
        raise HelperError("superseded", "intent %d is older than the recorded %d" % (seq, record_seq(record)))


# ----------------------------------------------------------------- spawn

def _read_pipe(fd: int, timeout: float) -> bytes:
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            ready, _, _ = select.select([fd], [], [], remaining)
        except OSError:
            break
        if not ready:
            break
        try:
            chunk = os.read(fd, 4096)
        except OSError:
            break
        if not chunk:
            break
        chunks.append(chunk)
    return b"".join(chunks)


def spawn_detached(argv: list[str], cwd: str = "/") -> dict[str, Any]:
    """setsid + double fork, and the fd hygiene that makes it survivable.

    The grandchild reports its own pid over a pipe (so a spawn that never
    binds a socket is still reapable by the helper that created it), reports
    an exec failure over a CLOEXEC pipe (restoring the error
    Quickshell.execDetached throws away - it returns void), keeps its stderr
    on a pipe for the launch window only (PO-6), puts /dev/null on stdin and
    stdout and closes every other inherited descriptor before execvp - which
    is what guarantees mpv never holds a Quickshell StdioCollector pipe for
    hours and dies of BrokenPipeError at the restart it exists to survive.

    argv[0] is the literal "mpv", never caller-supplied, so `player start` is
    not an arbitrary-exec verb.

    PO-11: the working directory is explicit, never inherited. A process that
    inherits the shell's cwd is running in the user's home, and mpv's own key
    bindings write files relative to it. The umask is explicit for the same
    reason: mpv creates whatever it writes with the process umask, which is
    0022 under the shell and gave D-PLY-7 its world-readable 0644 screenshot.
    0o077 puts every file the player creates at 0600 and every directory it
    creates at 0700, matching requirement 10. `chdir` failing must never
    leave us in the inherited directory, so "/" is the fallback.
    """
    pid_r, pid_w = os.pipe()
    err_r, err_w = os.pipe2(os.O_CLOEXEC)
    log_r, log_w = os.pipe()
    child = os.fork()
    if child == 0:                                        # pragma: no cover
        try:
            os.setsid()
            if os.fork() > 0:
                os._exit(0)
            os.write(pid_w, str(os.getpid()).encode("ascii"))
            os.close(pid_w)
            os.umask(PLAYER_UMASK)
            try:
                os.chdir(cwd or "/")
            except OSError:
                os.chdir("/")
            devnull = os.open(os.devnull, os.O_RDWR)
            os.dup2(devnull, 0)
            os.dup2(devnull, 1)
            os.dup2(log_w, 2)
            # Once this helper exits nobody reads that pipe; an ignored
            # SIGPIPE (inherited through execve) keeps a failed diagnostic
            # write from ever killing the player.
            signal.signal(signal.SIGPIPE, signal.SIG_IGN)
            try:
                limit = int(os.sysconf("SC_OPEN_MAX"))
            except (ValueError, OSError):
                limit = 4096
            for fd in range(3, min(limit, 4096)):
                if fd == err_w:
                    continue
                try:
                    os.close(fd)
                except OSError:
                    pass
            os.execvp("mpv", argv)
        except BaseException as error:                    # noqa: BLE001 - reported over the pipe
            number = getattr(error, "errno", 0) or 0
            try:
                os.write(err_w, str(int(number)).encode("ascii"))
            except OSError:
                pass
        os._exit(127)
    os.close(pid_w)
    os.close(err_w)
    os.close(log_w)
    try:
        os.waitpid(child, 0)                              # the intermediate child, never a zombie
    except OSError:
        pass
    pid_text = _read_pipe(pid_r, 2.0).decode("ascii", "replace").strip()
    os.close(pid_r)
    failure = _read_pipe(err_r, DEFAULT_SPAWN_TIMEOUT).decode("ascii", "replace").strip()
    os.close(err_r)
    pid = int(pid_text) if pid_text.isdigit() else 0
    if failure:
        os.close(log_r)
        number = int(failure) if failure.isdigit() else 0
        if number == errno.ENOENT:
            raise HelperError("mpv_missing", "mpv is not installed")
        raise HelperError("spawn_failed", "could not start mpv: %s" % (os.strerror(number) if number else "exec failed"))
    if pid <= 0:
        os.close(log_r)
        raise HelperError("spawn_failed", "the player did not report a pid")
    os.set_blocking(log_r, False)
    return {"pid": pid, "stderrFd": log_r}


# The un-redacted tail of a partial line, per fd, between calls to
# drain_launch_stderr. It exists because redaction is not distributive over a
# split: redact(a) + redact(b) is not redact(a + b) when a URL straddles the
# boundary. The old code redacted each 4096-byte os.read separately and a
# stream whose URL crossed a read left `http://host.example/li` in the buffer
# -- the path, which rule 5 says never leaves the helper -- and, at another
# offset, the username. Same defect class as the clean_detail cut-before-
# redact blocker, at a sink that reaches a desktop notification through
# launch_reason (D-SINK-12).
#
# Bounded: a tail is at most one line, and a line longer than
# LAUNCH_STDERR_MAX is redacted and flushed rather than grown, so a single
# newline-free stream cannot hold memory open.
_LAUNCH_TAIL: dict[int, str] = {}


def drain_launch_stderr(fd: int, buffer: list[str]) -> None:
    """PO-6: whatever mpv said while starting, redacted, memory only, capped.

    Kept drained so a chatty mpv can never block on a full pipe. Redacts
    whole LINES, carrying an unterminated one to the next call, because mpv's
    stderr is line-oriented and a URL never spans a newline.
    """
    def keep(text: str) -> None:
        room = LAUNCH_STDERR_MAX - sum(len(part) for part in buffer)
        if room > 0:
            buffer.append(text[:room])

    pending = _LAUNCH_TAIL.pop(fd, "")
    while True:
        try:
            chunk = os.read(fd, 4096)
        except (BlockingIOError, OSError):
            break
        if not chunk:
            # EOF: whatever is left is a whole line as far as this fd goes.
            if pending:
                keep(redact_urls(pending))
            return
        pending += chunk.decode("utf-8", "replace")
        head, sep, tail = pending.rpartition("\n")
        if sep:
            keep(redact_urls(head + sep))
            pending = tail
        if len(pending) > LAUNCH_STDERR_MAX:
            # A single line longer than the whole budget. It is DROPPED, not
            # flushed: emitting it would mean redacting a fragment that may be
            # cut mid-URL, which is the defect this function was repaired for.
            # Measured while repairing it -- flushing the over-long partial
            # leaked at 33 of 48 boundary offsets, because the flush itself is
            # a cut. Nothing a person would read is lost: launch_reason wants
            # mpv's last LINE, and a newline-free blob of this size is not one.
            pending = ""
    if pending:
        _LAUNCH_TAIL[fd] = pending


def launch_reason(buffer: list[str]) -> str:
    lines = [line.strip() for line in "".join(buffer).splitlines() if line.strip()]
    return lines[-1] if lines else ""


# ------------------------------------------------------------ connection

def probe_client(sock_path: str, ipc_timeout: float) -> MpvIpc | None:
    """A connected client that actually answered, or None."""
    client = MpvIpc(sock_path, ipc_timeout)
    try:
        client.connect()
        ok, _ = client.try_command("get_property", "mpv-version")
        if ok:
            return client
    except HelperError:
        pass
    client.close()
    return None


def wait_for_socket(sock_path: str, timeout: float, ipc_timeout: float,
                    stderr_fd: int = -1, stderr_buffer: list[str] | None = None) -> MpvIpc | None:
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        if stderr_fd >= 0 and stderr_buffer is not None:
            drain_launch_stderr(stderr_fd, stderr_buffer)
        client = probe_client(sock_path, ipc_timeout)
        if client is not None:
            return client
        if time.monotonic() >= deadline:
            return None
        time.sleep(SPAWN_POLL_S)


def quit_over_ipc(sock_path: str, ipc_timeout: float) -> bool:
    client = MpvIpc(sock_path, ipc_timeout)
    try:
        client.connect()
        client.request(["quit"], allow_close=True)
        return True
    except HelperError:
        return False
    finally:
        client.close()


def socket_is_dead(sock_path: str) -> bool:
    client = MpvIpc(sock_path, 0.2)
    try:
        client.connect()
    except HelperError:
        return client.refused or not os.path.exists(sock_path)
    finally:
        client.close()
    return False


def settle_socket(sock_path: str, deadline: float | None = None) -> bool:
    """Unlink the socket only once nothing is listening and nothing of ours
    is running (S_ISSOCK-guarded), so a racing start's fresh socket is never
    deleted. mpv never unlinks its own socket on any exit path.

    D-PLY-8: after a SIGKILL those two facts do not become true at the same
    instant. A killed process runs exit_mm first, so its command line is
    already empty at the first sample - 0.13-0.31 ms, 8/8 on real headless
    mpv 0.41 here - while its listening socket stays bound for another
    2.7-4.9 ms (and far longer for a windowed player, which tears down a GPU
    context, a Wayland connection and decoder buffers as well). The stop path
    asks both questions 4.5-7.5 ms after the kill: one /proc scan (3.7-4.9 ms
    for 225 pids on this box) after wait_for_exit wins on its first check.
    Ask once and the answer can be "not yet", after which nothing asks again
    and the socket file is left on disk until the next helper call.

    So with a `deadline` both guards are re-checked until they agree or the
    time is up. This NEVER widens the conditions - a racing spawn seen by
    find_player, a successful connect (a wedged player answering through its
    backlog) and a timed-out connect all still block the unlink, every
    iteration - it only stops giving up after one look.

    With `deadline=None` the behaviour is byte-identical to before: one check
    of each guard, no sleep. That is what every call site outside the stop
    ladder gets.

    The deadline is absolute and comes from the rung that is already waiting
    (4.9), so the settle spends time the ladder had reserved and never adds
    any. Worst case it overruns by one refused-connect timeout, the 0.2 s
    inside socket_is_dead, which is bounded and cannot repeat.
    """
    while True:
        if find_player(sock_path):
            return False
        if socket_is_dead(sock_path):
            return unlink_stale_socket(sock_path)
        if deadline is None or _monotonic() >= deadline:
            return False
        _sleep(min(STOP_POLL_S, max(0.0, deadline - _monotonic())))


def settle_under_lock(sock_path: str, deadline: float | None = None,
                      lock_timeout: float = SETTLE_LOCK_TIMEOUT) -> bool:
    """The settle for the two call sites that hold no lock of their own
    (X1/X2, ruling CL8).

    The unlink is only safe with the player lock held across the check AND
    the unlink: a `player start` that binds a fresh socket between this
    settle's refused connect and its os.unlink would have the NEW socket
    deleted. player_stop has always been safe that way (it settles inside its
    own lock); player_probe and player_orphan_check were not.

    A call site that cannot take the lock does not unlink. Another verb owns
    the socket at this instant and will settle it itself, and neither of
    these two verbs is worth failing over a leftover file.
    """
    try:
        lock_fd = acquire_lock(player_lock_path(sock_path), lock_timeout)
    except (HelperError, OSError):
        return False
    try:
        return settle_socket(sock_path, deadline)
    finally:
        release_lock(lock_fd)


def wait_for_exit(targets: list[dict[str, Any]], sock_path: str, wait_ms: int) -> bool:
    deadline = _monotonic() + max(0, int(wait_ms)) / 1000.0
    while True:
        if not any(still_the_player(record, sock_path) for record in targets):
            return True
        if _monotonic() >= deadline:
            return False
        _sleep(STOP_POLL_S)


def signal_targets(targets: list[dict[str, Any]], sock_path: str, number: int) -> bool:
    sent = False
    for record in targets:
        if not still_the_player(record, sock_path):
            continue
        try:
            os.kill(int(record["pid"]), number)
            sent = True
        except OSError:
            continue
    return sent


STOP_STAGE_BEFORE = {"": "", "quit": "", "term": "quit", "kill": "term"}


def stop_ladder(sock_path: str, targets: list[dict[str, Any]], from_rung: str = "",
                ipc_timeout: float = DEFAULT_IPC_TIMEOUT) -> dict[str, Any]:
    """The whole D-LIVE-17 ladder inside one process (4.9).

    quit at 0, SIGTERM at 2 s, SIGKILL at 4 s - the same timeline as today,
    but no rung can be starved by a busy control channel, the ladder finishes
    even if the shell dies one millisecond after issuing it, and the pid comes
    from /proc rather than from `get_property pid`, so a wedged mpv (the case
    the ladder exists for, where IPC is by definition dead) is reachable.
    `stop_escalation()` drives the rungs so the shared vectors really govern.

    `deadline` in the reply is the absolute monotonic instant the rung that
    actually ran would have kept waiting until. The kill rung reserves 500 ms
    (`stop_escalation("term")` gives waitMs 0, so `grace` falls back to
    STOP_SETTLE_MS) and spends about 0.3 ms of it, because wait_for_exit
    checks before it sleeps and a killed process is gone at once. Handing
    that instant to the settle (D-PLY-8) spends time the ladder had already
    reserved rather than adding any, so the stop cannot run longer than the
    published timeline whatever the teardown does.
    """
    result: dict[str, Any] = {"rung": "", "running": True, "deadline": None}
    stage = STOP_STAGE_BEFORE.get(from_rung or "", "")
    for _ in range(3):
        step = stop_escalation(stage)
        action = str(step["action"])
        # Each rung's grace is measured from the rung's OWN start, so the
        # next one lands where the timeline says it does. The quit rung is
        # the reason: against an unresponsive player `request(["quit"])`
        # spends the whole --ipc-timeout before anything is waited for, and
        # that cost sat OUTSIDE the 2 s grace - so SIGTERM arrived at 4 s,
        # SIGKILL at 6 s, and a wedged player took ~6.27 s to reap against a
        # 4.5 s budget. Counting it inside costs a responsive player nothing
        # (it answers `quit` at once and exits in about a third of a second,
        # with the full grace still ahead of it) and keeps the guarantee
        # that it is asked politely first.
        rung_started = _monotonic()
        grace = int(step["waitMs"]) or STOP_SETTLE_MS
        # Recorded before the rung acts, so every exit below reports the
        # window this rung owned - including the one where there was nothing
        # left to signal, which is precisely when a socket can still be bound
        # by a process the finder can no longer see.
        result["deadline"] = rung_started + grace / 1000.0
        if action == "quit":
            quit_over_ipc(sock_path, ipc_timeout)
            result["rung"] = "quit"
        elif step["signal"]:
            if not signal_targets(targets, sock_path, int(step["signal"])):
                result["running"] = False
                return result
            result["rung"] = action
        else:
            break
        spent = int((_monotonic() - rung_started) * 1000.0)
        if wait_for_exit(targets, sock_path, max(0, grace - spent)):
            result["running"] = False
            return result
        stage = action
    result["deadline"] = _monotonic() + STOP_SETTLE_MS / 1000.0
    result["running"] = not wait_for_exit(targets, sock_path, STOP_SETTLE_MS)
    return result


# end of 07-player.py: 45346 bytes above, crc32 d88b22ed
