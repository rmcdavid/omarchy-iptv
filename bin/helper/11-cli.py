# A part of bin/omarchy-iptv (D-REL-7), not a module: the helper compiles
# this file into its own namespace in the order its HELPER_PARTS lists, so
# a part sees every name the parts before it define. Run the helper.
from __future__ import annotations
# ----------------------------------------------------- host config shield
#
# D-SINK-18, raised by the marketplace maintainer against the shipped 0.13.2.
# The plugin persists the active source's playlist and EPG URLs onto its bar
# entry, and the host writes that into ~/.config/omarchy/shell.json -- a file
# this plugin does not own, whose packaged default is 0644, and whose writer
# (Quickshell's FileView with atomicWrites) was MEASURED by the lead to
# neither reset nor tighten the mode of an existing file: 0644 in, 0644 out.
# So the plugin cannot assume the container it is putting a provider
# credential into is private, and rule 6 shows it already knows better for
# the containers it owns (state.json 0600 inside a 0700 directory).
#
# The owner's ruling: the plugin takes responsibility for the CONTAINER it
# puts a secret into. Make that one file private before a URL goes into it,
# and refuse to persist if it cannot be made private. Explicitly NOT the
# parent directories -- a 0600 file is sufficient whatever the directory
# modes are, and ~/.config is shared with everything on the system, so
# tightening it is not ours to do. This verb therefore reports no directory
# mode either: a number in the output is an invitation to act on it.
#
# The precedent in this repository is init_state_file (S-02), which exists
# for the same reason one file up: FileView creates a missing file 0644 and
# keeps the mode of an existing one, so the helper gets there first.


def _shield_open_failure(path: str, error: OSError) -> dict[str, Any]:
    """Classify a failed open of the host settings file.

    `os.path.islink` here is a SECOND resolution of the same name, and
    D-LOGO-10 paid for treating one of those as a decision. It is used for
    the verdict's wording only: nothing is opened, changed or chmod-ed on the
    strength of it, and every verdict below is already "not private".
    """
    if error.errno == errno.ENOENT:
        return _shield_result("absent", 0, 0, False, "config_absent",
                              "the host settings file does not exist")
    if error.errno == errno.ELOOP and os.path.islink(path):
        return _shield_result("symlink", 0, 0, False, "config_symlink",
                              "the host settings file is a symbolic link")
    return _shield_result("error", 0, 0, False, "config_unreadable",
                          "could not open the host settings file: %s"
                          % (error.strerror or errno.errorcode.get(error.errno or 0, "error")))


def _shield_result(verdict: str, before: int, after: int, changed: bool,
                   code: str = "", message: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {
        "verdict": verdict,
        "modeBefore": mode_text(before),
        "modeAfter": mode_text(after),
        "changed": bool(changed),
    }
    if verdict not in CONFIG_SHIELD_PRIVATE_VERDICTS:
        out["code"] = code or "config_unsafe"
        out["message"] = message or "the host settings file is not private"
    return out


def _same_inode(path: str, st: os.stat_result) -> bool:
    """Is `path` still the inode we just tightened?

    lstat, not stat: a symlink put at the path pointing back at our own
    inode would pass a stat comparison and is exactly the thing O_NOFOLLOW
    refused one step earlier.
    """
    try:
        now = os.lstat(path)
    except OSError:
        return False
    return (now.st_dev, now.st_ino) == (st.st_dev, st.st_ino)


def _shield_host_config_once(path: str) -> dict[str, Any]:
    """One attempt at making the host settings file private.

    Everything after the open is done through the FILE DESCRIPTOR, which is
    D-LOGO-10's lesson applied to a chmod instead of an unlink: a check on a
    NAME followed by an operation on the same NAME is two resolutions of that
    name, and whatever swaps the file in between gets the operation. So:

      * O_NOFOLLOW refuses a symlink AT OPEN, atomically, and yields a handle
        on the inode that was checked;
      * O_NONBLOCK is load-bearing, not hygiene: a FIFO at that path would
        make a plain O_RDONLY open block until someone opened the other end,
        and this runs on the service's startup path, where an unbounded wait
        is the bug those rules name;
      * fstat decides regular-file and ownership, fchmod changes the mode and
        a second fstat READS BACK what the kernel actually stored rather than
        trusting the mode we asked for;
      * and the final lstat asks whether that inode is still the one at the
        path, because the host's own writer renames a new file over it -- a
        verdict about an inode that has just been replaced would be a true
        statement about the wrong file.

    What this does NOT do is walk the ancestors. O_NOFOLLOW covers the last
    component; a symlinked ~/.config (what every dotfile manager builds) is
    followed, deliberately, because refusing it would break ordinary installs.
    The bound on that is the operation itself: this only ever SUBTRACTS group
    and other permission bits from a regular file the invoking euid owns, so
    the worst a redirected call can achieve is making one of the user's own
    files private. It cannot disclose anything, and it cannot grant anything.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError as error:
        return _shield_open_failure(path, error)
    try:
        st = os.fstat(fd)
        before = stat.S_IMODE(st.st_mode)
        if not stat.S_ISREG(st.st_mode):
            return _shield_result("not_regular", before, before, False, "config_not_regular",
                                  "the host settings file is not a regular file")
        if st.st_uid != os.geteuid():
            return _shield_result("foreign", before, before, False, "config_foreign",
                                  "the host settings file is owned by another user")
        changed = False
        if before & CONFIG_GROUP_OTHER:
            try:
                os.fchmod(fd, before & ~CONFIG_GROUP_OTHER)
            except OSError as error:
                return _shield_result("exposed", before, stat.S_IMODE(os.fstat(fd).st_mode), False,
                                      "config_unsafe",
                                      "could not make the host settings file private: %s"
                                      % (error.strerror or "chmod failed"))
            changed = True
        after = stat.S_IMODE(os.fstat(fd).st_mode)
        if after & CONFIG_GROUP_OTHER:
            return _shield_result("exposed", before, after, changed, "config_unsafe",
                                  "the host settings file is still readable by group or other")
        if not _same_inode(path, st):
            return _shield_result("replaced", before, after, changed, "config_replaced",
                                  "the host settings file was replaced while it was being secured")
        return _shield_result("private", before, after, changed)
    finally:
        os.close(fd)


def shield_host_config() -> dict[str, Any]:
    """Make the host settings file private, or say why it is not.

    Idempotent: a file that already denies group and other is not written,
    not chmod-ed and reported with `changed: false`.
    """
    path = host_config_path()
    attempts = 0
    result: dict[str, Any] = {}
    while attempts < CONFIG_SHIELD_ATTEMPTS:
        attempts += 1
        result = _shield_host_config_once(path)
        if result["verdict"] != "replaced":
            break
    result["attempts"] = attempts
    result["file"] = os.path.join(HOST_CONFIG_DIR, HOST_CONFIG_FILE)
    result["private"] = result["verdict"] in CONFIG_SHIELD_PRIVATE_VERDICTS
    return result


def cmd_config(args: argparse.Namespace) -> int:
    """`config shield`: one JSON object the shell can switch on.

    Rule 5: the only strings here are a verdict, two octal modes, a count and
    the file's last two path components -- never the file's CONTENTS, never
    the absolute path (which carries the user's name), and never a URL. The
    file is opened read-only and never read.
    """
    result = shield_host_config()
    payload: dict[str, Any] = {
        "ok": bool(result["private"]),
        "kind": "config",
        "action": args.action,
        "verdict": result["verdict"],
        "private": bool(result["private"]),
        "changed": bool(result["changed"]),
        "modeBefore": result["modeBefore"],
        "modeAfter": result["modeAfter"],
        "attempts": result["attempts"],
        "file": result["file"],
    }
    if payload["ok"]:
        # A mode we changed on a file we do not own is worth one line of
        # audit; an already-private file says nothing at all.
        if payload["changed"]:
            log("config shield: %s %s -> %s" % (result["file"], result["modeBefore"], result["modeAfter"]))
    else:
        payload["error"] = {"code": result["code"], "message": redact_urls(result["message"])}
        log("config shield: %s (%s, mode %s)" % (result["message"], result["verdict"], result["modeBefore"]))
    emit(payload)
    return EXIT_OK if payload["ok"] else EXIT_ERROR


# ----------------------------------------------------------- clipboard (R8)

def clipboard_deadline() -> float:
    """Seconds the clipboard read may take: CLIPBOARD_TIMEOUT, or LESS when a
    test shrinks it through CLIPBOARD_TIMEOUT_ENV. The variable can only
    lower the bound (F-HARNESS-36, R32f), like HTTP_DEADLINE_ENV and
    MEMORY_LIMIT_ENV: it used to take any figure over 0.05, so the variable
    that exists for tests could lift the 5 s the engineering rules (rule 5,
    D-CLIP-1) and ARCHITECTURE state. The shell's clipboardWatchdog was the
    outer bound either way."""
    override = os.environ.get(CLIPBOARD_TIMEOUT_ENV, "")
    if override:
        try:
            wanted = float(override)
        except ValueError:
            return CLIPBOARD_TIMEOUT
        if wanted == wanted:              # not NaN
            return min(CLIPBOARD_TIMEOUT, max(0.05, wanted))
    return CLIPBOARD_TIMEOUT


def utf16_cut(text: str, limit: int) -> tuple[str, bool]:
    """`text` cut to at most `limit` UTF-16 units, never inside a surrogate
    pair -- the unit the shell's `substring` counts in, so both sides agree
    on what 8192 characters are. The flag says whether anything was cut."""
    units = 0
    for index, char in enumerate(text):
        width = 2 if ord(char) > 0xFFFF else 1
        if units + width > limit:
            return text[:index], True
        units += width
    return text, False


def reap_child(child: Any, grace: float) -> int | None:
    """Make sure the child is gone: SIGTERM, a bounded wait, then SIGKILL and
    one more bounded wait. Returns its exit status, or None if it survived
    even that (which only a process stuck in the kernel can)."""
    import subprocess
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            child.kill()
            try:
                child.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                pass
    child.stdout.close()
    return child.returncode


def read_clipboard(argv: list[str], max_bytes: int, timeout: float, grace: float) -> dict[str, Any]:
    """Run `argv` (wl-paste) with a pipe on its stdout and read at most
    `max_bytes` from it under a wall-clock `timeout`, terminating the child
    the moment the cap, EOF or the deadline is reached.

    Rule 5: the bytes go into the reply's `text` and NOWHERE else -- never a
    log line, never stderr, never an error message. The child's stderr is
    discarded (wl-paste names nothing useful there and a hostile producer
    could), its stdin is /dev/null, and this process starts no other child.
    The read is non-blocking behind select() so a producer that drips bytes
    at the protocol's 1 s per-read timeout runs into the deadline, not into
    an unbounded read; `truncated` is true when the cap stopped the read
    before EOF (a clipboard of exactly max_bytes reads as truncated, which
    errs toward saying something was cut) or when the character cut below
    dropped anything. The result never carries text on a failure.
    """
    import subprocess
    try:
        child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, close_fds=True)
    except FileNotFoundError:
        return {"ok": False, "code": "no_wl_paste"}
    except OSError:
        return {"ok": False, "code": "spawn_failed"}
    deadline = time.monotonic() + timeout
    fd = child.stdout.fileno()
    os.set_blocking(fd, False)
    parts: list[bytes] = []
    total = 0
    capped = False
    eof = False
    timed_out = False
    status: int | None = None
    # The shell's watchdog ends THIS process with SIGTERM when its outer bound
    # fires. Python's default disposition for that signal skips every
    # `finally`, so the wl-paste child would be reparented with its read of
    # the hostile offer still open (a review orphaned one that way with a
    # never-writing stub). The handler reaps the child first, then exits with
    # the conventional status; the disposition is restored once the read is
    # over so nothing outside this function inherits it.
    import signal as _signal
    def _terminated(signum, frame):
        reap_child(child, grace)
        raise SystemExit(128 + signum)
    previous_term = _signal.signal(_signal.SIGTERM, _terminated)
    try:
        while True:
            if total >= max_bytes:
                capped = True
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                timed_out = True
                break
            try:
                chunk = os.read(fd, min(CLIPBOARD_CHUNK, max_bytes - total))
            except BlockingIOError:
                continue
            if not chunk:
                eof = True
                break
            parts.append(chunk)
            total += len(chunk)
        if eof:
            # The producer is done; its exit status is the one signal that
            # distinguishes an empty clipboard ("Nothing is copied", exit 1)
            # from an empty string on it. Bounded by what is left of the
            # deadline so a child that closes its pipe and lingers cannot
            # hold this process either.
            try:
                status = child.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                timed_out = True
    finally:
        _signal.signal(_signal.SIGTERM, previous_term)
        reaped = reap_child(child, grace)
        if status is None:
            status = reaped
    if timed_out:
        return {"ok": False, "code": "timeout"}
    if eof and status != 0:
        return {"ok": False, "code": "failed", "status": status if status is not None else -1}
    if not eof and status is None:
        return {"ok": False, "code": "child_stuck"}
    data = b"".join(parts)
    # A cut at the byte cap can land inside a UTF-8 sequence: the incremental
    # decoder holds an incomplete tail back (final=False) rather than
    # replacing it, so the text always ends on a character boundary. Invalid
    # bytes anywhere else become U+FFFD, the way the shell's collector read them.
    text = codecs.getincrementaldecoder("utf-8")("replace").decode(data, final=not capped)
    text, cut = utf16_cut(text, MAX_CLIPBOARD_CHARS)
    return {"ok": True, "text": text, "truncated": bool(capped or cut), "bytes": len(data)}


def cmd_clipboard(args: argparse.Namespace) -> int:
    """`clipboard`: ONE JSON object on stdout and nothing on stderr.

    {"ok": true, "kind": "clipboard", "text": ..., "truncated": bool,
    "bytes": n} when wl-paste answered, with `text` cut at a character
    boundary to at most MAX_CLIPBOARD_CHARS UTF-16 units; {"ok": false,
    "kind": "clipboard", "code": "no_wl_paste" | "spawn_failed" | "timeout"
    | "failed" | "child_stuck"} otherwise, with no text at all. The text is
    never logged and no error names what the clipboard held (rule 5).
    """
    result = read_clipboard(CLIPBOARD_ARGV, MAX_CLIPBOARD_BYTES, clipboard_deadline(), CLIPBOARD_KILL_GRACE)
    payload: dict[str, Any] = {"ok": bool(result["ok"]), "kind": "clipboard"}
    for key in ("text", "truncated", "bytes", "code", "status"):
        if key in result:
            payload[key] = result[key]
    emit(payload)
    return EXIT_OK if payload["ok"] else EXIT_ERROR


# -------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omarchy-iptv", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)

    playlist = sub.add_parser("playlist", help="fetch and parse the M3U playlist into channels.json")
    playlist.add_argument("--url", default="", help="http(s) URL or absolute path (file:// accepted); defaults to $%s, which is how the shell passes it so that it is not on the command line" % URL_ENV)
    playlist.add_argument("--cache-dir", default=None, help="default: $XDG_CACHE_HOME/omarchy-iptv")
    playlist.add_argument("--state-dir", default=None, help="move saved channel references in this state directory onto the current id scheme; omitted, no state file is read or written at all")
    playlist.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="network timeout in seconds")
    playlist.set_defaults(func=cmd_playlist)

    epg = sub.add_parser("epg", help="fetch XMLTV (plain or gzip) and write epg-now.json")
    epg.add_argument("--url", default="", help="http(s) URL or absolute path; defaults to $%s, which is how the shell passes it so that it is not on the command line; optional with --now-only" % URL_ENV)
    epg.add_argument("--cache-dir", default=None, help="default: $XDG_CACHE_HOME/omarchy-iptv")
    epg.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="network timeout in seconds")
    epg.add_argument("--ttl", type=float, default=EPG_DEFAULT_TTL, help="seconds before the cached programme window is re-downloaded (default %d)" % EPG_DEFAULT_TTL)
    epg.add_argument("--force", action="store_true", help="re-download even when the cached window is fresh")
    epg.add_argument("--now-only", action="store_true", help="recompute now/next from the cached programme window without fetching")
    epg.add_argument("--now", type=int, default=0, help="clock override in epoch seconds (tests and QA); default: the current time")
    epg.set_defaults(func=cmd_epg)

    play = sub.add_parser("play", help="switch the running mpv to a channel over IPC")
    target = play.add_mutually_exclusive_group(required=True)
    target.add_argument("--id", default="", help="channel id from channels.json")
    target.add_argument("--url", default="", help="play a raw stream URL (IPC play verb); name = host, no headers")
    play.add_argument("--cache-dir", default=None, help="default: $XDG_CACHE_HOME/omarchy-iptv")
    play.add_argument("--socket", default=None, help="default: $XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock")
    play.add_argument("--ipc-timeout", type=float, default=DEFAULT_IPC_TIMEOUT, help="seconds to wait for mpv (default %.0f)" % DEFAULT_IPC_TIMEOUT)
    play.add_argument("--scope", default="", help="zap-ring scope to stash inside mpv (the list the channel was launched from)")
    play.add_argument("--since", type=int, default=0, help="epoch seconds the channel started playing; with --scope it refreshes the stash")
    play.set_defaults(func=cmd_play)

    stop = sub.add_parser("stop", help="ask the running mpv to quit over IPC")
    stop.add_argument("--socket", default=None, help="default: $XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock")
    stop.add_argument("--ipc-timeout", type=float, default=DEFAULT_IPC_TIMEOUT, help="seconds to wait for mpv (default %.0f)" % DEFAULT_IPC_TIMEOUT)
    stop.set_defaults(func=cmd_stop)

    status = sub.add_parser("status", help="query the running mpv over IPC")
    status.add_argument("--socket", default=None, help="default: $XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock")
    status.add_argument("--ipc-timeout", type=float, default=DEFAULT_IPC_TIMEOUT, help="seconds to wait for mpv (default %.0f)" % DEFAULT_IPC_TIMEOUT)
    status.set_defaults(func=cmd_status)

    # The detached player (ARCHITECTURE-PLAYER.md (dev branch) 4.3). User mpv tokens
    # travel as repeated --mpv-arg so argparse can never swallow an
    # option-looking token and no token is ever joined or split.
    player = sub.add_parser("player", help="start, stop, restart, probe or orphan-check the detached player")
    player_actions = player.add_subparsers(dest="action", required=True)
    player_socket = argparse.ArgumentParser(add_help=False)
    player_socket.add_argument("--socket", default=None, help="default: $XDG_RUNTIME_DIR/omarchy-iptv/mpv.sock")
    player_socket.add_argument("--ipc-timeout", type=float, default=DEFAULT_IPC_TIMEOUT, help="seconds to wait for mpv (default %.0f)" % DEFAULT_IPC_TIMEOUT)
    player_session = argparse.ArgumentParser(add_help=False)
    player_session.add_argument("--cache-dir", default=None, help="default: $XDG_CACHE_HOME/omarchy-iptv")
    player_session.add_argument("--id", required=True, help="channel id from channels.json; the URL is read from the 0600 cache, never passed in")
    player_session.add_argument("--seq", type=int, default=0, help="the service's intent sequence number; an older intent is superseded")
    player_session.add_argument("--scope", default="", help="zap-ring scope stashed inside mpv (UI intent no mpv property could report)")
    player_session.add_argument("--since", type=int, default=0, help="epoch seconds the channel started playing")
    player_session.add_argument("--owner-pid", type=int, default=0, help="claim the player for this shell pid (see orphan-check)")
    player_session.add_argument("--mpv-arg", action="append", default=[], help="one user mpv token; repeat for more (never joined)")
    player_session.add_argument("--lock-timeout", type=float, default=DEFAULT_LOCK_TIMEOUT, help="seconds to wait for the player lock (default %.1f)" % DEFAULT_LOCK_TIMEOUT)
    player_session.add_argument("--spawn-timeout", type=float, default=DEFAULT_SPAWN_TIMEOUT, help="seconds to wait for mpv to bind its socket (default %.1f)" % DEFAULT_SPAWN_TIMEOUT)
    player_session.add_argument("--first-load-timeout", type=float, default=DEFAULT_FIRST_LOAD_TIMEOUT, help="seconds to watch the first load (default %.1f)" % DEFAULT_FIRST_LOAD_TIMEOUT)
    start = player_actions.add_parser("start", parents=[player_socket, player_session], help="adopt or spawn the player and play a channel (idempotent)")
    start.add_argument("--from", dest="from_rung", default="", choices=["", "quit", "term", "kill"], help=argparse.SUPPRESS)
    restart = player_actions.add_parser("restart", parents=[player_socket, player_session], help="stop ladder and spawn under one lock (the health verdict)")
    restart.add_argument("--from", dest="from_rung", default="term", choices=["", "quit", "term", "kill"], help="first rung of the ladder (default term: IPC is not answering)")
    stop_player = player_actions.add_parser("stop", parents=[player_socket], help="run the whole quit / SIGTERM / SIGKILL ladder in this process")
    stop_player.add_argument("--seq", type=int, default=0, help="the service's intent sequence number")
    stop_player.add_argument("--from", dest="from_rung", default="", choices=["", "quit", "term", "kill"], help="first rung (default quit over IPC)")
    stop_player.add_argument("--lock-timeout", type=float, default=DEFAULT_LOCK_TIMEOUT, help="seconds to wait for the player lock (default %.1f)" % DEFAULT_LOCK_TIMEOUT)
    probe = player_actions.add_parser("probe", parents=[player_socket], help="report the player without touching it (the reattach read)")
    probe.add_argument("--owner-pid", type=int, default=0, help="claim the player for this shell pid")
    pause = player_actions.add_parser("pause", parents=[player_socket],
                                      help="pause, resume or toggle the live stream; resuming continues from the pause (to go further back: seek)")
    pause.add_argument("--state", choices=("on", "off", "toggle"), default="toggle")
    pause.set_defaults(func=cmd_player)
    seek = player_actions.add_parser("seek", parents=[player_socket],
                                     help="move inside the cache mpv already keeps of the live stream: --by N seconds (negative is back) or --live; clamped to the window, a refusal is reported")
    seek_how = seek.add_mutually_exclusive_group(required=True)
    seek_how.add_argument("--by", type=int, default=None, help="signed whole seconds; negative rewinds")
    seek_how.add_argument("--live", action="store_true", help="back to the cache edge (never a reload: the history is kept)")
    seek.set_defaults(func=cmd_player)
    tracks = player_actions.add_parser("tracks", parents=[player_socket],
                                       help="list audio and subtitle tracks; with --audio/--sub, select first and then list")
    tracks.add_argument("--audio", default=None, help="mpv audio track id, or 'no'")
    tracks.add_argument("--sub", default=None, help="mpv subtitle track id, or 'no'")
    tracks.set_defaults(func=cmd_player)

    orphan = player_actions.add_parser("orphan-check", parents=[player_socket], help="stop the player only if its claiming shell is still alive")
    orphan.add_argument("--owner-pid", type=int, required=True, help="the shell pid whose service was destroyed")
    orphan.add_argument("--grace", type=float, default=DEFAULT_ORPHAN_GRACE, help="seconds to let a successor shell claim the player (default %.1f)" % DEFAULT_ORPHAN_GRACE)
    player.set_defaults(func=cmd_player)

    logos = sub.add_parser("logos", help="report which hosts enabling logos would contact (makes no request)")
    logos.add_argument("--cache-dir", default=None)
    logos.add_argument("--survey", action="store_true", default=True,
                       help="default: read the cache and contact nothing")
    logos.add_argument("--fetch", action="store_true",
                       help="download the logos (contacts the hosts --survey lists)")
    logos.add_argument("--timeout", type=float, default=10.0)
    logos.set_defaults(func=cmd_logos)

    failed = sub.add_parser("failed", help="the dead-channel marks of one source's cache")
    failed.add_argument("action", choices=("mark", "clear", "list"))
    failed.add_argument("--id", default=None, help="channel id; omitted with `clear`, clears all")
    failed.add_argument("--cache-dir", default=None)
    failed.add_argument("--now", type=int, default=None, help="epoch override, for tests")
    failed.set_defaults(func=cmd_failed)

    state = sub.add_parser("state", help="inspect or edit state.json")
    state.add_argument("--state-dir", default=None, help="default: $XDG_STATE_HOME/omarchy-iptv")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state-dir", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    actions = state.add_subparsers(dest="action", required=True)
    actions.add_parser("show", parents=[common], help="print the current state")
    actions.add_parser("init", parents=[common], help="create state.json with mode 0600 when missing (the service runs this before its first write)")
    favorite = actions.add_parser("favorite", parents=[common], help="add or remove a favorite")
    favorite.add_argument("op", choices=["add", "remove"])
    favorite.add_argument("id", help="channel id from channels.json")
    actions.add_parser("clear-recents", parents=[common], help="empty the Recent list")
    source = actions.add_parser("source", parents=[common], help="list or edit the source history (state.json v2); output shows hosts, never URLs")
    ops = source.add_subparsers(dest="op", required=True)
    ops.add_parser("list", parents=[common], help="print the history")
    add = ops.add_parser("add", parents=[common], help="append a source (validated and normalized like the guide does)")
    add.add_argument("--url", required=True, help="playlist http(s) URL, file:// URL or absolute path")
    add.add_argument("--epg-url", default=None, help="optional XMLTV URL or path")
    add.add_argument("--label", default=None, help="custom label (default: derived from the host or file name)")
    add.add_argument("--origin", default="cli", choices=list(SOURCE_ORIGINS), help="record origin (default cli)")
    add.add_argument("--now", type=int, default=0, help="clock override in epoch seconds (tests)")
    update = ops.add_parser("update", parents=[common], help="change the label, playlist URL or EPG URL of a source")
    update.add_argument("key", help="source key (8 hex digits)")
    # D-SRC-11, as overturned by D-SINK-19 (round 11, R21; this help text
    # caught up in round 12, R22f, and again in round 14, R24c): the record is
    # the only store for both URLs and no bar setting overwrites it. A running
    # shell re-reads the file after this write and keeps it (measured, R23g
    # and R24c), merging an unsaved in-app change with it (R24a).
    update.add_argument("--url", default=None, help="new playlist URL (re-keys the record; move or remove its cache). A running shell re-reads state.json after this and keeps it")
    update.add_argument("--epg-url", default=None, help="new EPG URL; an empty string clears it. A running shell re-reads state.json after this and keeps it")
    update.add_argument("--label", default=None, help="new label; an empty string restores the derived one")
    update.add_argument("--now", type=int, default=0, help="clock override in epoch seconds (tests)")
    remove = ops.add_parser("remove", parents=[common], help="drop a source from the history (its cache dir: `cache remove`)")
    remove.add_argument("key", help="source key")
    state.set_defaults(func=cmd_state)

    cache = sub.add_parser("cache", help="per-source cache directories under <cache-dir>/sources/<key>/")
    cache.add_argument("--cache-dir", default=None, help="default: $XDG_CACHE_HOME/omarchy-iptv")
    cache_common = argparse.ArgumentParser(add_help=False)
    cache_common.add_argument("--cache-dir", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    cache_actions = cache.add_subparsers(dest="action", required=True)
    migrate = cache_actions.add_parser("migrate", parents=[cache_common], help="move the 0.1 single-cache files into sources/<key>/ (deleted without --key); idempotent")
    migrate.add_argument("--key", default="", help="key of the active source that owns the legacy files")
    remove_dir = cache_actions.add_parser("remove", parents=[cache_common], help="delete the known cache files of one source and its directory")
    remove_dir.add_argument("--key", required=True, help="source key")
    epg_clear = cache_actions.add_parser("epg-clear", parents=[cache_common], help="delete one source's EPG files, keeping the source's playlist cache and directory")
    epg_clear.add_argument("--key", required=True, help="source key")
    logos_clear = cache_actions.add_parser("logos-clear", parents=[cache_common], help="delete one source's cached logos, keeping the source's playlist cache and directory")
    logos_clear.add_argument("--key", required=True, help="source key")
    prune = cache_actions.add_parser("prune", parents=[cache_common], help="delete the directories of keys not listed; age the EPG files of inactive ones")
    prune.add_argument("--keep", nargs="*", default=[], help="keys to keep (every key in the history)")
    prune.add_argument("--active", default="", help="the active key: its EPG files are never aged")
    prune.add_argument("--epg-max-age", type=float, default=DEFAULT_EPG_MAX_AGE, help="seconds after which inactive EPG files are deleted (default %d)" % DEFAULT_EPG_MAX_AGE)
    cache.set_defaults(func=cmd_cache)

    # D-SINK-18. No path argument, by design: see host_config_path(). The
    # action is spelled out rather than implied so that a second, read-only
    # action can be added later without changing what `config shield` means.
    config = sub.add_parser("config", help="make the host settings file private (it can still hold a URL an older version or omarchy bar set put there)")
    config_actions = config.add_subparsers(dest="action", required=True)
    shield = config_actions.add_parser("shield", help="deny group and other on $HOME/.config/omarchy/shell.json (no-op when it already does); prints the modes and a verdict, never the contents")
    shield.set_defaults(func=cmd_config)
    # D-CLIP-1 (R8): the bounded clipboard read the shell's paste runs.
    clipboard = sub.add_parser("clipboard", help="read the Wayland clipboard through wl-paste, at most 32 KiB, under a deadline; prints one JSON object and never logs the text")
    clipboard.set_defaults(func=cmd_clipboard)
    return parser


# D-SRC-13's rule 15 sweep (2026-10-21): main()'s answer to a bug is part of
# EVERY verb's reply, and the shell collects every helper verb's stdout and
# stderr whole. The exception's own text is the one part of it no verb
# composes -- `str(error)` can quote any input the bug was handed, whatever
# its length -- so the structured message keeps its first
# INTERNAL_MESSAGE_MAX characters and the traceback its first and last
# INTERNAL_TRACE_MAX / 2, the middle counted. Both are cut AFTER the
# redaction, so the redactor always sees a whole URL: a cut can shorten a
# redacted `scheme://host`, never leave part of a userinfo, path or query
# behind it (pinned with a cap that falls inside the userinfo).
INTERNAL_MESSAGE_MAX = 1024
INTERNAL_TRACE_MAX = 16384


def bounded_text(text: str, limit: int, keep_tail: bool = False) -> str:
    """`text` when it fits; else its first `limit` characters, or with
    keep_tail its first and last limit // 2 and a counted line between,
    read for one as well as for many (the round-1 recheck of lane-bounds-p:
    "[1 characters not shown]" was the D-M3U-4 sibling this function
    introduced)."""
    if len(text) <= limit:
        return text
    if not keep_tail:
        return text[:limit]
    half = limit // 2
    hidden = counted_sentence(len(text) - 2 * half, "[%d character not shown]", "[%d characters not shown]")
    return "%s\n%s\n%s" % (text[:half], hidden, text[-half:])


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except MemoryError:
        # D-M3U-1. The fetch verbs answer this themselves, with their status
        # file; this is for one that ran out before or after its own net.
        # The limit is lifted first so the sentence can be composed.
        release_memory_limit(MEMORY_HELD)
        line = "%s needs more memory than this helper allows itself" % args.command
        log("%s: %s" % (args.command, line))
        emit({"ok": False, "kind": args.command, "error": {"code": "too_large", "message": line}})
        return EXIT_ERROR
    except FolderUnusable as error:
        # R25c: not a bug -- a folder the verb needs is a link to nothing, or
        # not a folder. One sentence, the exit every refusal has.
        log("%s: %s" % (args.command, error.sentence))
        emit({"ok": False, "kind": args.command, "error": {"code": "folder_unusable", "message": redact_urls(error.sentence)}})
        return EXIT_ERROR
    except Exception as error:
        # A bug. The traceback is the bug report, but it must not carry a URL
        # (section 9), so it is redacted and paired with a structured error.
        import traceback
        sys.stderr.write(bounded_text(redact_urls(traceback.format_exc()), INTERNAL_TRACE_MAX, keep_tail=True))
        message = bounded_text(redact_urls("%s: %s" % (type(error).__name__, error)), INTERNAL_MESSAGE_MAX)
        emit({"ok": False, "kind": args.command, "error": {"code": "internal", "message": message}})
        return EXIT_ERROR


