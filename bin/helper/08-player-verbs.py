# A part of bin/omarchy-iptv (D-REL-7), not a module: the helper compiles
# this file into its own namespace in the order its HELPER_PARTS lists, so
# a part sees every name the parts before it define. Run the helper.
from __future__ import annotations
# ------------------------------------------------------------- the channel

def fallback_channel_name(url: str, default: str) -> str:
    """The name of a channel that has none: its host, which is the title mpv
    shows and the name a notification quotes. D-SINK-31 (R32a', 2026-10-22):
    when the URL's RFC host has no dot and an `@` follows it -- the typo
    shape, where that host is most likely a username -- the name is the word
    `Stream`, through the one predicate the free-text redactors withhold
    with (host_withheld); a dotted host (every Xtream link) still names it."""
    if host_withheld(url):
        return "Stream"
    return url_host(url) or default


def player_target(channel_id: str, raw_url: str, directory: str) -> dict[str, Any]:
    """Resolve the channel the helper will play. The URL is read from the
    0600 cache by the helper itself and never crosses a process boundary."""
    if channel_id:
        channel = find_channel(load_channels(cache_dir(directory)), channel_id)
        url = str(channel.get("url") or "")
        name = str(channel.get("name") or "") or fallback_channel_name(url, "channel")
        headers = channel.get("headers") if isinstance(channel.get("headers"), dict) else {}
        group = str(channel.get("group") or "")
    else:
        url = (raw_url or "").strip()
        name = fallback_channel_name(url, "stream")
        headers = {}
        group = ""
    if not is_stream_url(url):
        raise HelperError("unsupported_scheme", "unsupported stream URL scheme '%s'" % (stream_scheme(url) or "none"))
    return {"id": channel_id or "", "url": url, "name": name, "headers": headers, "group": group}


def tls_properties_safe(verify: Any, option_count: Any) -> bool:
    """Is this player's certificate handling safe to hand a credentialed URL to?

    Mirror of Model.tlsPropertiesSafe; both sides run the shared
    player-tls.json fixture (dev branch).

    `verify` is mpv's `tls-verify` and must be the boolean True -- not 1, not
    "yes": those are not shapes mpv's IPC produces, and accepting them would
    make this reader more forgiving than the thing it reads. `option_count` is
    how many entries `stream-lavf-o` holds, which must be zero: FFmpeg's own
    `tls_verify` AVOption reaches the same place as mpv's option and OUTVOTES
    it (measured, D-SINK-13 layer 3), so a non-empty map is not safe whatever
    happens to be in it. None means the reading could not be taken, which is
    not safe either.
    """
    if verify is not True:
        return False
    if isinstance(option_count, bool) or not isinstance(option_count, int):
        return False
    return option_count == 0


def read_tls_state(client: MpvIpc) -> tuple[Any, Any]:
    """The two D-SINK-16 readings, taken OFF the player.

    Read back rather than inferred from a set_property reply, because a
    `success` reply is a statement about the request and not about the value;
    the lead measured the read-back working on a real player over IPC on
    2026-10-07. An unreadable property answers None, and tls_properties_safe
    refuses None.

    A COUNT, never the keys or the values: `stream-lavf-o` can hold a proxy
    address with credentials in it, and this number travels out of here into a
    reply the shell reads (engineering rule 5). The count is the whole of what
    the decision needs.
    """
    ok, verify = client.try_command("get_property", MPV_TLS_VERIFY_PROP)
    verify = verify if ok and isinstance(verify, bool) else None
    ok, options = client.try_command("get_property", MPV_STREAM_OPTS_PROP)
    count = len(options) if ok and isinstance(options, dict) else None
    return verify, count


def assert_tls_verification(client: MpvIpc, label: str) -> None:
    """Make this player verify the stream's certificate, or REFUSE to load.

    D-SINK-16. The security-critical difference from this sequence's other
    pre-load assertions: `pause`, `aid` and `sid` go out through try_command
    and are best effort, because getting them wrong costs a black screen or
    the wrong audio track. TLS may not be best effort. Loading is precisely
    the act of handing a credentialed URL and the provider headers to the
    process, so a player that cannot be made to verify gets neither -- the
    caller turns this HelperError into a failed play, exactly as it does the
    header refusal two lines further down.

    Set, then READ BACK, then judge. The set replies are deliberately not
    consulted: the measurement that this fix rests on is a read-back, and a
    `success` reply says nothing about the value that ended up there.
    """
    client.try_command("set_property", MPV_TLS_VERIFY_PROP, True)
    client.try_command("set_property", MPV_STREAM_OPTS_PROP, {})
    verify, count = read_tls_state(client)
    if tls_properties_safe(verify, count):
        return
    # Diagnosable without being a sink: a three-valued flag and a count, never
    # a key or a value out of that map.
    log("%s: %s reads %r and %s holds %r entries after being set"
        % (label, MPV_TLS_VERIFY_PROP, verify, MPV_STREAM_OPTS_PROP, count))
    raise HelperError("tls_unverified", "the player would not verify the stream's certificate")


def migrate_tls(client: MpvIpc) -> dict[str, Any]:
    """Make an ADOPTED player verify, and say whether it had to be changed.

    D-SINK-16, the half `apply_channel` cannot reach: a player started before
    the upgrade is already streaming, and the shell has to decide whether to
    adopt it before it sends it anything. So the probe -- the reattach read --
    migrates it here and reports the readings it ends up with.

    `migrated` means "this player was NOT already safe when I found it", which
    is the shell's signal to re-establish the channel: setting the property
    covers the next load, and whether an already-open stream picks the change
    up for its ongoing segment fetches is UNMEASURED. It stays True even when
    the set did not take, so the shell can tell "nothing to do" from "I had to
    act" independently of whether the acting worked; the readings are what say
    whether it worked.

    Runtime migration over IPC was measured by the lead on 2026-10-07: on one
    unchanged process, `set_property tls-verify True` read back True and the
    attacker's log went from one GET to none, with a plain http:// stream from
    a second local server still playing as the positive control.
    """
    verify, count = read_tls_state(client)
    if tls_properties_safe(verify, count):
        return {"verify": verify, "optionCount": count, "migrated": False}
    client.try_command("set_property", MPV_TLS_VERIFY_PROP, True)
    client.try_command("set_property", MPV_STREAM_OPTS_PROP, {})
    verify, count = read_tls_state(client)
    return {"verify": verify, "optionCount": count, "migrated": True}


def apply_channel(client: MpvIpc, target: dict[str, Any], stash: dict[str, Any] | None = None,
                  owner: dict[str, Any] | None = None, label: str = "play") -> int | None:
    """The wire sequence of a zap, shared verbatim by `play` and
    `player start` so first play and every later zap are one implementation.

    the TLS assertion -> title -> force-media-title -> the three header
    properties (always all three, so a channel without headers actively resets
    the previous one's, which is requirement 7's clearing mechanism) -> the
    stash -> loadfile -> the stash again with the entry id -> the owner claim.
    """
    # D-SINK-16, and the FIRST thing this sequence does, because every line
    # below it is a line that tells the player something about a channel. mpv
    # keeps `tls-verify` across a loadfile the way it keeps `pause`, `aid` and
    # `sid` -- and an adopted player may never have had it set at all. Unlike
    # its three neighbours this one is not best effort: it raises, and both
    # callers turn that into a failed play. Raised BEFORE the title, so a
    # player that cannot be secured is not even relabelled with a channel it
    # will never load.
    assert_tls_verification(client, label)
    # PAUSE LIVE TV: mpv keeps `pause` across a loadfile, so tuning a new
    # channel while paused would load it PAUSED while every surface said
    # playing -- a black screen the user has no reason to suspect. Cleared
    # here rather than in the shell, because it must be atomic with the load:
    # the shell's own flag is optimistic and a refused clear would leave the
    # two disagreeing. Found by the 0.7.10 preflight, not by the suite.
    client.try_command("set_property", "pause", False)
    # M3-02, and the same mechanism one property over. mpv keeps `aid` and
    # `sid` across a loadfile exactly as it keeps `pause`, so a user who
    # picked the Spanish audio on one channel got track 2 of the NEXT
    # channel -- whatever that happens to be -- with the picker cleared and
    # nothing on screen saying why. Two shipped sentences promised the
    # opposite ("the choice is not remembered across channels"), which is
    # the intent: remembering a LANGUAGE is a separate feature with its own
    # questions, and remembering a track NUMBER is meaningless across
    # streams. "auto" is mpv's default: pick the file's own preference.
    # Found by the 0.9.0 preflight, reasoned from this comment's own
    # neighbour, then measured on a real player.
    for prop in ("aid", "sid"):
        client.try_command("set_property", prop, "auto")
    for prop, value in (("title", MPV_RAW_PREFIX + target["name"]), ("force-media-title", target["name"])):
        ok, _ = client.try_command("set_property", prop, value)
        if not ok:
            log("%s: mpv refused to set %s" % (label, prop))
    for prop, value in header_properties(target["headers"], client):
        client.command("set_property", prop, value)
    if stash is not None:
        client.try_command("set_property", USER_DATA_STASH, dict(stash, entryId=None))
    data = client.command("loadfile", target["url"], "replace")
    entry_id = data.get("playlist_entry_id") if isinstance(data, dict) else None
    if not isinstance(entry_id, int) or isinstance(entry_id, bool) or entry_id <= 0:
        entry_id = None
    # Everything after the loadfile is bookkeeping, and under `--idle=once` a
    # channel that fails instantly can take the process (and the connection)
    # down before these land. A dead connection here means the load failed,
    # which is the first-load window's verdict to report - not an error that
    # should sink the whole verb.
    for prop, value in ((USER_DATA_STASH, dict(stash, entryId=entry_id) if stash is not None else None),
                        (USER_DATA_OWNER, owner)):
        if value is None:
            continue
        try:
            client.try_command("set_property", prop, value)
        except HelperError:
            log("%s: the player closed while recording %s" % (label, prop))
            break
    return entry_id


def applied_by_another_client(client: MpvIpc) -> dict[str, Any] | None:
    """What some other client has already applied to a player this helper has
    just SPAWNED, or None if the player is still as it was born.

    Only ever asked of a spawned player, and that restriction is the whole of
    why the answer is safe to act on. A newborn mpv is idle with
    `playlist-count` 0 and no `user-data/omarchy-iptv` node at all - confirmed
    against real mpv 0.41, headless: the node answers `property not found`
    until something writes it, and the count answers 0 until something loads.
    Nothing on the launch argv can put a file there either (`filter_mpv_args`
    keeps bare tokens off it, and `--idle=once` idles). So a channel sitting
    there NOW was applied by a client that connected after the spawn, and
    every such client is carrying an intent this start was issued BEFORE.

    That ordering is established by the spawn, not by a sequence number,
    which is what makes the check legal while ruling CL4 stands: `play` gains
    no `--seq` and takes no lock, so no channel change during a cold start
    can be delayed or refused.

    An adopted player is never asked: there, a stash is evidence of nothing
    at all - it may be the last thing the user chose or it may be minutes
    old, and ordering it would need exactly the sequence number CL4 withholds.
    """
    ok, count = client.try_command("get_property", "playlist-count")
    loaded = bool(ok and isinstance(count, int) and not isinstance(count, bool) and count > 0)
    ok, data = client.try_command("get_property", USER_DATA_STASH)
    stash = data if ok and isinstance(data, dict) else None
    if not loaded and stash is None:
        return None
    entry = (stash or {}).get("entryId")
    return {
        "id": str((stash or {}).get("id") or ""),
        "name": str((stash or {}).get("name") or ""),
        "entryId": entry if isinstance(entry, int) and not isinstance(entry, bool) and entry > 0 else None,
        # No `seq` here on purpose (D-CL-1). The number on that stash is this
        # start's own, read back out of the lock record the zap borrowed it
        # from, so it can only ever equal ours - a field that looks like
        # evidence of ordering and is not. The spawn is what orders these two.
        #
        # Which slot wrote that stash. Unlike a seq this really does vary
        # between the two sides of a stand-down (D-CL-1): the record on the
        # player reads "play", the one this verb was about to write reads
        # "start" - and a stash with no verb at all is an older schema or
        # something that is not ours, which is itself worth seeing.
        "verb": str((stash or {}).get("verb") or ""),
        "loaded": loaded,
    }


def stand_down_note(seq: int, target: dict[str, Any], newer: dict[str, Any]) -> str:
    """The journal line a start writes when it stands down (D-CL-1).

    It used to end `(intent %d over %d)`, and those two numbers are EQUAL by
    construction on the only path that reaches this line. The start holds the
    player lock across its whole spawn and stamps the lock record with its own
    seq before taking it; ruling CL4 withholds `--seq` from `play`, so the zap
    that beats it here stamps the stash with `record_seq(read_lock_file())` -
    which, inside that window, can only be the start's own number read back.
    Five live stand-downs printed `(intent 662 over 662)`, `(654 over 654)`
    and so on, 5/5. There is no second intent number to print, and a
    diagnostic that cannot vary is an assertion that cannot fail.

    What a person reading a journal after a user complains actually needs is
    the pair that DOES vary: the channel this start gave up on and the channel
    the user is left watching, plus who put it there. Those two are the
    complaint ("I pressed one thing and got another") in the two fields the
    shell's own repair compares. The one intent number is kept, named once, as
    the handle that ties the line to the shell's `player.seq`.
    """
    mine = str(target.get("id") or "") or "an unnamed stream"
    theirs = str(newer.get("id") or "")
    entry = newer.get("entryId")
    entry = entry if isinstance(entry, int) and not isinstance(entry, bool) and entry > 0 else None
    writer = str(newer.get("verb") or "")
    if theirs and theirs == mine:
        where = "the player is on that same channel"
    elif theirs:
        where = "the player is on %s" % theirs
    elif writer:
        where = "the player is on an unnamed stream"
    else:
        # Loaded, but nothing wrote a stash: not one of ours, or one that
        # died between the loadfile and the stash. Say which it is rather
        # than printing an id and a writer that are only empty strings.
        where = "the player is on a load this helper did not label"
    if writer and entry is not None:
        where += ", written by %s as entry %d" % (writer, entry)
    elif writer:
        where += ", written by %s" % writer
    elif entry is not None:
        where += ", entry %d" % entry
    intent = "intent %d would have applied %s" % (seq, mine) if seq > 0 else "it would have applied %s" % mine
    return ("a newer channel change reached the player first (%s; %s); left it playing"
            % (intent, where))


def owner_claim(owner_pid: int) -> dict[str, Any] | None:
    """The claim that tells a successor shell the player is already adopted
    (4.14). Keyed by pid AND start time so a recycled pid cannot inherit it."""
    if not owner_pid or owner_pid <= 0:
        return None
    return {"schema": PLAYER_STASH_SCHEMA, "pid": int(owner_pid),
            "startTime": proc_start_time(int(owner_pid)), "at": int(time.time())}


# D-SRC-13's rule 15 sweep (2026-10-21): the reason a first load failed is
# mpv's last error-level log line, which is free text of any length (a
# demuxer or a server can put its own words in it), and it rides the
# `player start` reply the shell collects whole (playerStdout). Cut here, at
# the one place the reply's reason is composed; the launch window's own
# reason is already held to LAUNCH_STDERR_MAX, and mpv's file_error is one
# of its fixed strings.
FIRST_LOAD_REASON_MAX = 512


def first_load_result(state: str, reason: str) -> dict[str, Any]:
    return {"state": state, "reason": reason[:FIRST_LOAD_REASON_MAX].rstrip()}


def observe_first_load(client: MpvIpc, entry_id: int | None, timeout: float,
                       launch_errors: list[str] | None = None) -> dict[str, Any]:
    """F3: `player start` watches its own first load on the connection it
    already holds, so a first channel that dies before any QML subscriber
    could exist - an expired subscription, the commonest real failure - is
    never silent. Log text is redacted here, inside python, before it can
    cross into QML.
    """
    deadline = time.monotonic() + max(0.0, timeout)
    state = "unknown"
    reason = ""
    last_error = launch_reason(launch_errors or [])
    while time.monotonic() < deadline:
        events = client.drain_events(deadline)
        if events is None:                       # mpv closed the connection
            state = "failed"
            break
        for message in events:
            event = str(message.get("event") or "")
            mine = entry_id is None or message.get("playlist_entry_id") == entry_id
            if event == "log-message" and str(message.get("level") or "") in ("error", "fatal"):
                last_error = redact_urls(str(message.get("text") or "")).strip() or last_error
            elif event == "file-loaded":
                return {"state": "playing", "reason": ""}
            elif event == "end-file" and mine:
                verdict = ended_verdict(message)
                why = str(message.get("reason") or "")
                # `ended_verdict` is the POST-MORTEM reducer (4.8): it answers
                # "why did the player end", for a player that has ended. Here
                # the connection is still open and mpv is still running, so two
                # of its answers mean something different and must not be taken
                # at face value.
                if verdict["kind"] == "ignored":
                    # D-PLY-13. "redirect" is mpv resolving an .m3u8 master,
                    # which is the commonest shape in IPTV. The load has NOT
                    # ended, so returning here stopped the watch before the
                    # resolved stream could fail -- and an expired subscription
                    # failing at exactly that moment is what this watch exists
                    # for. Keep draining.
                    continue
                if verdict["kind"] == "failed" and why == "stop":
                    # D-PLY-12. After the fact, "stop" can only mean "a load we
                    # issued was replaced AND THEN the process died", so the
                    # reducer calls it a failure. On a LIVE connection it cannot
                    # mean that: it means another IPC client replaced our entry,
                    # which is a zap. Reporting failure here put a "did not
                    # play" notification on screen for a channel the user had
                    # deliberately just left, and marked it failed in the guide.
                    return {"state": "unknown", "reason": ""}
                if verdict["kind"] == "failed":
                    # The log line says what actually went wrong; mpv's own
                    # file_error is a generic "loading failed". Both are
                    # already redacted, here, inside python (section 6).
                    return first_load_result("failed", last_error or verdict["reason"])
                return {"state": "unknown", "reason": ""}
    if state == "failed" and not reason:
        reason = last_error or PLAYER_GENERIC_FAILURE
    return first_load_result(state, reason)


# -------------------------------------------------------------- the verbs

def player_runtime(sock_path: str) -> str:
    """The socket's folder, made 0700 (rule 6) -> its path.

    D-PLY-30 (2026-10-27): every way this can fail is a refusal in the
    player verbs' own reply shape (`kind: player.<verb>`), never main()'s
    `internal` with an exception and a path. A link to nothing, or something
    that is not a folder, at the folder or above it is R25c's
    `folder_unusable` with R25c's sentence, which names the path (the
    journal keeps it; Model.statusReason shows the user a sentence). Any
    other failure to make it -- a parent this user cannot write, a full or
    read-only filesystem -- is `runtime_unwritable`."""
    directory = os.path.dirname(sock_path)
    try:
        ensure_private_dir(directory)
    except FolderUnusable as error:
        raise HelperError("folder_unusable", error.sentence) from None
    except OSError as io_error:
        raise runtime_unwritable("make the player's runtime folder", io_error) from None
    return directory


def check_socket_path(sock_path: str) -> None:
    """A regular file at the socket path is never unlinked and never spawned
    over (it is the user's, or a sign something else owns the path)."""
    try:
        mode = os.lstat(sock_path).st_mode
    except OSError:
        return
    if not stat.S_ISSOCK(mode):
        raise HelperError("socket_path_blocked", "the socket path is not a socket")


def ensure_player_dirs(dirs: dict[str, str], warnings: list[str]) -> None:
    """PO-11: pre-create what the player writes into, at 0700.

    mpv does create a missing --screenshot-dir / --watch-later-dir - verified
    on 0.41 - but it creates it 0755, which is exactly the exposure being
    closed. Creating it here first settles the mode. A failure is not worth
    refusing a play over: the option still goes on argv, mpv reports its own
    error into the launch window, and the user is told which directory the
    plugin could not make. `shaderCache` (D-PLY-10) joins them for the same
    reason: mpv would otherwise create it itself, at its own mode.
    """
    for key in ("screenshots", "watchLater", "shaderCache"):
        try:
            ensure_private_dir(dirs[key])
        except OSError as error:
            warnings.append("could not create %s (%s)" % (dirs[key], error.strerror or "error"))


def adopt_or_spawn(sock_path: str, mpv_args: list[str], spawn_timeout: float,
                   ipc_timeout: float, warnings: list[str],
                   dirs: dict[str, str] | None = None) -> dict[str, Any]:
    """Requirement 1, all three layers: the /proc scan is the existence check,
    a live answering player is adopted rather than duplicated, several
    matches collapse to the one that answers, and a spawn whose socket never
    binds is reaped by the helper that created it - so an uncontrollable
    window can neither exist nor multiply.
    """
    found = find_player(sock_path)
    if found:
        client = probe_client(sock_path, ipc_timeout)
        if client is not None:
            keep = _connected_pid(client, found)
            # D-SINK-39, D-SINK-16's shape: this player was forked by whoever
            # ran before, so its core limit is whatever it inherited then.
            # Lowered here, before apply_channel feeds it anything; a refusal
            # is impossible for a live same-uid process, so it is reported
            # rather than fatal (limit_core_of says why).
            if not limit_core_of(keep):
                warnings.append("could not limit the adopted player's core dumps")
            others = [record for record in found if record["pid"] != keep]
            if others:
                # Never rung 1 here: `quit` travels over the shared socket and
                # would hit the player we are keeping. Signal the rest by pid.
                warnings.append("stopped %d other player process(es) on this socket" % len(others))
                stop_ladder(sock_path, others, "term", ipc_timeout)
            return {"spawned": False, "client": client, "pid": keep}
        # Matches found, none answers: wedged. Ladder them down and respawn.
        warnings.append("stopped an unresponsive player")
        stop_ladder(sock_path, found, "", ipc_timeout)
    settle_socket(sock_path)
    where = dirs or player_dirs(sock_path)
    ensure_player_dirs(where, warnings)
    launched = spawn_detached(mpv_launch_argv(sock_path, mpv_args, where), where["cwd"])
    errors: list[str] = []
    client = wait_for_socket(sock_path, spawn_timeout, ipc_timeout, launched["stderrFd"], errors)
    if client is None:
        drain_launch_stderr(launched["stderrFd"], errors)
        os.close(launched["stderrFd"])
        stop_ladder(sock_path, [{"pid": launched["pid"], "startTime": proc_start_time(launched["pid"])}], "term", ipc_timeout)
        settle_socket(sock_path)
        detail = launch_reason(errors)
        raise HelperError("no_socket", "the player did not open its socket" + (": %s" % detail if detail else ""))
    drain_launch_stderr(launched["stderrFd"], errors)
    os.close(launched["stderrFd"])
    return {"spawned": True, "client": client, "pid": launched["pid"], "launchErrors": errors}


def _connected_pid(client: MpvIpc, found: list[dict[str, Any]]) -> int:
    """Which of the scanned processes is the one answering the socket. With a
    single match that is settled; with several, mpv's own `pid` property
    decides, and the scan is still the authority on existence."""
    if len(found) == 1:
        return int(found[0]["pid"])
    ok, data = client.try_command("get_property", "pid")
    if ok and isinstance(data, int) and any(record["pid"] == data for record in found):
        return int(data)
    return int(found[0]["pid"]) if found else 0


def player_start(args: argparse.Namespace, verb: str = "start") -> int:
    kind = "player.%s" % verb
    sock = socket_path(args.socket)
    seq = max(0, int(args.seq or 0))
    warnings: list[str] = []
    mpv_args, rejected = filter_mpv_args(list(args.mpv_arg or []))
    for token in rejected:
        # D-SINK-24 (R32b', 2026-10-22): the option NAME only -- the text
        # before "=" -- and only when the token is option-shaped (MPV_ARG_RE,
        # `^--[a-z0-9][a-z0-9-]*(=.*)?$`), so a token refused BECAUSE its name
        # is not (`--u:pw@h=1`) prints the fixed word "<token>", as does a
        # value (a bearer or basic-auth value split off a header option, a
        # scheme-less user:pw@proxy). Never a value, never a bare token.
        # Mirrors Model.mpvRejectedName; the reply's warnings reach the journal.
        warnings.append("dropped mpvArg %s" % (token.split("=", 1)[0] if MPV_ARG_RE.match(token) else "<token>"))
    # PO-10: kept, not dropped - and said out loud. The service shows the
    # same line the guide already has; this one is for the CLI and the log.
    warnings.extend(mpv_arg_warnings(mpv_args))
    lock_fd = -1
    client = None
    newer: dict[str, Any] | None = None
    try:
        target = player_target(args.id, "", args.cache_dir)
        player_runtime(sock)
        check_socket_path(sock)
        lock_fd = acquire_lock(player_lock_path(sock), args.lock_timeout)
        check_seq(read_lock_record(lock_fd), seq, verb)
        write_lock_record(lock_fd, seq, verb)
        if verb == "restart":
            stop_ladder(sock, find_player(sock), args.__dict__.get("from_rung") or "term", args.ipc_timeout)
            settle_socket(sock)
        outcome = adopt_or_spawn(sock, mpv_args, args.spawn_timeout, args.ipc_timeout, warnings)
        client = outcome["client"]
        # Subscribe BEFORE any load, so the first channel's failure text is
        # captured on the connection we already hold (F3).
        client.try_command("request_log_messages", "error")
        stash = player_stash(target["id"], target["name"], target["group"], args.scope,
                             source_key_of(cache_dir(args.cache_dir)), args.since or int(time.time()), seq,
                             verb=verb)
        # D-PLY-11. The measured mechanism (QA-RESULTS.md (dev branch) D1, ruling CL9):
        # during a cold start a channel change reaches the socket the instant
        # mpv binds it, while this verb is still inside `wait_for_socket`'s
        # handshake - and then this line put the burst's FIRST intent back
        # over it, unconditionally, because nothing here ever looked. Ten
        # user-visible divergences in twenty cold concurrent bursts.
        #
        # So look. A start that discovers it is no longer the newest intent
        # stands down: it leaves the newer channel playing and says so in its
        # reply. It does not relabel anything and it does not decide what the
        # user wanted - the shell is authoritative for that under ruling CL5,
        # and re-applies its own intent when this reply disagrees with it.
        newer = applied_by_another_client(client) if outcome["spawned"] else None
        if newer is None:
            entry_id = apply_channel(client, target, stash=stash, owner=owner_claim(args.owner_pid),
                                     label="player %s" % verb)
        else:
            entry_id = newer["entryId"]
            claim = owner_claim(args.owner_pid)
            if claim is not None:
                # The claim is about which shell owns the player, not about
                # which channel is on it, so it is still ours to write.
                client.try_command("set_property", USER_DATA_OWNER, claim)
            log("player %s: %s" % (verb, stand_down_note(seq, target, newer)))
            warnings.append("a newer channel change reached the player first")
    except HelperError as error:
        if lock_fd >= 0:
            release_lock(lock_fd)
        if client is not None:
            client.close()
        log("player %s: %s" % (verb, error.message))
        emit(error_payload(kind, error, id=args.id or None, seq=seq))
        return EXIT_ERROR
    # The lock is deliberately not held across the first-load window, so a
    # `player stop` can interleave (4.4 step 10).
    release_lock(lock_fd)
    try:
        # Nothing of ours is loading when we stood down: the load being
        # watched for would be someone else's, and waiting out the whole
        # first-load window for an event that already happened would only
        # delay the reply. "unknown" is the honest verdict and the one the
        # observer already handles.
        first_load = ({"state": "unknown", "reason": ""} if newer is not None
                      else observe_first_load(client, entry_id, args.first_load_timeout, outcome.get("launchErrors")))
    finally:
        client.close()
    emit({"ok": True, "kind": kind, "spawned": bool(outcome["spawned"]), "pid": int(outcome["pid"]),
          "id": target["id"] or None, "name": target["name"], "entryId": entry_id, "seq": seq,
          "firstLoad": first_load, "warnings": warnings,
          # Additive, and the two fields the shell's repair reads: whether
          # this verb's own channel is what the player ended up on, and what
          # it is on instead when it is not.
          "applied": newer is None,
          "playing": None if newer is None else {"id": newer["id"], "name": newer["name"]}})
    return EXIT_OK


def player_stop(args: argparse.Namespace) -> int:
    sock = socket_path(args.socket)
    seq = max(0, int(args.seq or 0))
    lock_fd = -1
    try:
        player_runtime(sock)
        lock_fd = acquire_lock(player_lock_path(sock), args.lock_timeout)
        check_seq(read_lock_record(lock_fd), seq, "stop")
        write_lock_record(lock_fd, seq, "stop")
        found = find_player(sock)
        if not found:
            settle_socket(sock)
            emit({"ok": True, "kind": "player.stop", "running": False, "rung": "", "pid": None})
            return EXIT_OK
        result = stop_ladder(sock, found, args.from_rung, args.ipc_timeout)
        # D-PLY-8. The only settle in the file that gets a deadline, and the
        # only one already inside the player lock - which is what makes an
        # unlink safe across the wait. The deadline is the ladder's own,
        # nearly all of it unspent.
        settle_socket(sock, result.get("deadline"))
        emit({"ok": True, "kind": "player.stop", "running": bool(result["running"]),
              "rung": result["rung"], "pid": int(found[0]["pid"])})
        return EXIT_OK
    except HelperError as error:
        log("player stop: %s" % error.message)
        emit(error_payload("player.stop", error, seq=seq))
        return EXIT_ERROR
    finally:
        if lock_fd >= 0:
            release_lock(lock_fd)


def player_probe(args: argparse.Namespace) -> int:
    """Lock-free, and side-effect-free but for one stale-socket unlink, the
    owner claim and the TLS migration. `path` and `media-title` are never read
    into the shell: one is a credentialed URL, the other is verified stale
    after playback ends.

    D-SINK-16 is what added the third exception, and it is a deliberate widening
    of this verb's contract. The probe IS the reattach: it is the one moment the
    shell holds a connection to a player it did not launch and has not yet sent
    anything to, which makes it the only place a pre-upgrade player can be made
    to verify before it is fed. The write is idempotent and it is a security
    assertion, so a later probe over the same player changes nothing and reports
    nothing to do."""
    sock = socket_path(args.socket)
    try:
        found = find_player(sock)
        payload: dict[str, Any] = {
            "ok": True, "kind": "player.probe", "running": bool(found), "responsive": False,
            "pid": int(found[0]["pid"]) if found else None, "idle": None, "mpvVersion": None,
            "stash": None, "owner": None, "seq": record_seq(read_lock_file(sock)), "claimed": False,
            "rewind": None,
            # D-SINK-16. Read by Model.playerTlsVerdict; null for a player that
            # was never reached, which that verdict reads as "do not feed it".
            "tls": None,
        }
        client = probe_client(sock, args.ipc_timeout) if found else None
        if client is None:
            if not found:
                # X2 / CL8: under the lock, because check-then-unlink without
                # it can delete a racing start's FRESH socket. Never with a
                # deadline - the probe is a read, and a waiting unlink at an
                # unlocked-by-nature call site would lengthen the very
                # exposure being closed.
                settle_under_lock(sock)
            emit(payload)
            return EXIT_OK
        try:
            payload["responsive"] = True
            # D-SINK-16, before any other property is touched: whatever else
            # this probe learns, a player that is not verifying stops being one
            # here rather than at the next zap.
            payload["tls"] = migrate_tls(client)
            payload["pid"] = _connected_pid(client, found)
            # D-SINK-39, beside the TLS migration and for the same reason: the
            # reattach is the one moment a pre-upgrade player can be kept from
            # dumping its memory before the new code feeds it. prlimit, not a
            # property: nothing over IPC reaches a resource limit.
            if not limit_core_of(payload["pid"]):
                log("player probe: could not limit the player's core dumps")
            ok, idle = client.try_command("get_property", "idle-active")
            payload["idle"] = bool(idle) if ok and idle is not None else None
            ok, version = client.try_command("get_property", "mpv-version")
            payload["mpvVersion"] = version if ok and isinstance(version, str) else None
            ok, stash = client.try_command("get_property", USER_DATA_STASH)
            payload["stash"] = stash if ok and isinstance(stash, dict) and stash.get("id") else None
            ok, owner = client.try_command("get_property", USER_DATA_OWNER)
            payload["owner"] = owner if ok and isinstance(owner, dict) else None
            # M5-01: the reattach read recovers "behind live" from the zero
            # point the player carries. Read only -- the probe writes nothing
            # but the owner claim, and a zero point taken here would be one
            # taken by a verb that is documented as side-effect-free.
            payload["rewind"] = read_rewind(client, payload["stash"], write=False)
            claim = owner_claim(args.owner_pid)
            if claim is not None:
                written, _ = client.try_command("set_property", USER_DATA_OWNER, claim)
                payload["claimed"] = bool(written)
                if written:
                    payload["owner"] = claim
        finally:
            client.close()
        emit(payload)
        return EXIT_OK
    except HelperError as error:
        log("player probe: %s" % error.message)
        emit(error_payload("player.probe", error, running=False))
        return EXIT_ERROR


def player_orphan_check(args: argparse.Namespace) -> int:
    """PO-2: the service object being destroyed cannot tell a shell restart
    from a plugin removal, so the claim decides, not the destruction event.
    A successor shell overwrites the claim well inside the grace."""
    sock = socket_path(args.socket)
    owner_pid = int(args.owner_pid or 0)
    _sleep(max(0.0, float(args.grace)))
    try:
        found = find_player(sock)
        if not found:
            emit({"ok": True, "kind": "player.orphan-check", "stopped": False, "reason": "no_player"})
            return EXIT_OK
        client = probe_client(sock, args.ipc_timeout)
        claim = None
        if client is not None:
            try:
                ok, data = client.try_command("get_property", USER_DATA_OWNER)
                claim = data if ok and isinstance(data, dict) else None
            finally:
                client.close()
        if not isinstance(claim, dict) or int(claim.get("pid") or 0) != owner_pid or owner_pid <= 0:
            emit({"ok": True, "kind": "player.orphan-check", "stopped": False, "reason": "reassigned"})
            return EXIT_OK
        alive = False
        try:
            os.kill(owner_pid, 0)
            alive = proc_is_ours(owner_pid) and (not claim.get("startTime") or proc_start_time(owner_pid) == str(claim.get("startTime")))
        except OSError:
            alive = False
        if not alive:
            # The shell exited and nothing claimed the player: a slow restart
            # must not kill playback.
            emit({"ok": True, "kind": "player.orphan-check", "stopped": False, "reason": "owner_dead"})
            return EXIT_OK
        result = stop_ladder(sock, found, "", args.ipc_timeout)
        # X1 / CL8: same reasoning as the probe. This one runs the ladder
        # first, so the socket it is about to unlink belonged to a player it
        # just reaped - and a start racing it is exactly the case the lock
        # exists for. No deadline here either.
        settle_under_lock(sock)
        emit({"ok": True, "kind": "player.orphan-check", "stopped": not result["running"],
              "reason": "owner_alive", "rung": result["rung"]})
        return EXIT_OK
    except HelperError as error:
        log("player orphan-check: %s" % error.message)
        emit(error_payload("player.orphan-check", error, stopped=False))
        return EXIT_ERROR


def player_pause(args: argparse.Namespace) -> int:
    """Pause, resume, or toggle the live stream.

    WHAT THIS IS AND IS NOT. mpv keeps filling its demuxer cache while paused,
    so resuming continues from the moment you pressed it -- you are then
    watching behind live. Going back to BEFORE the keypress is `player seek`
    (M5-01), which moves inside the same cache: `seekable` reads false on
    every live channel measured and 31 of 32 rewound anyway, because the
    property that decides it is `demuxer-cache-state.seekable-ranges`
    (SPIKE-LIVE-REWIND.md, dev branch). An earlier version of this docstring read
    the wrong property and called the feature impossible. Never call either
    feature DVR: nothing is recorded.

    The bound of a pause is mpv's forward quota, 150 MiB, which on a
    ~3.8 Mbps stream measured 315 s before the buffer stopped growing, with
    or without history behind it. A long pause then reclaims the rewind
    window one second per paused second down to the 50 MiB the back buffer
    owns outright (11.2), which the `rewind` object in this reply shows.

    Side-effect-free when the player is not there: no spawn, no lock, no
    stale-socket unlink. Pausing something that is not playing is a no-op and
    says so, rather than starting a player to pause it.
    """
    sock = socket_path(args.socket)
    payload: dict[str, Any] = {"ok": True, "kind": "player.pause", "running": False,
                               "paused": None, "changed": False, "rewind": None}
    if not find_player(sock):
        emit(payload)
        return EXIT_OK
    client = probe_client(sock, args.ipc_timeout)
    if client is None:
        emit(payload)
        return EXIT_OK
    try:
        payload["running"] = True
        ok, current = client.try_command("get_property", "pause")
        was = bool(current) if ok and current is not None else None
        if args.state == "toggle":
            want = (not was) if was is not None else True
        else:
            want = args.state == "on"
        if was is not None and was == want:
            payload["paused"] = was
            payload["rewind"] = read_rewind(client, paused=was)
            emit(payload)
            return EXIT_OK
        set_ok, _ = client.try_command("set_property", "pause", want)
        if not set_ok:
            raise HelperError("pause_refused", "the player refused to change pause state")
        payload["paused"] = want
        payload["changed"] = True
        payload["rewind"] = read_rewind(client, paused=want)
        emit(payload)
        return EXIT_OK
    except HelperError as error:
        # D-PLY-20: the code `pause_refused` was raised here and caught by
        # nothing, so the service received `internal` and stderr a traceback.
        emit(error_payload("player.pause", error))
        return EXIT_ERROR
    finally:
        client.close()


# ---- M3-02: audio and subtitle tracks ---------------------------------------
#
# mpv's `track-list` is a sink (rule 5, dev branch). FOUR of its fields are
# free text mpv documents as coming from the file, so none of them is ours:
#
#   external-filename  a path or URL for an external track. NOT on the
#                      whitelist below and never emitted: dropping it beats
#                      redacting it, because nothing in the picker needs it.
#   title              written by whoever muxed the stream. Emitted through
#                      redact_urls, and scrubbed a second time by
#                      Model.parseTracks before it reaches guide text or an
#                      accessible name.
#   lang               "track language as identified by the file" (mpv
#                      manual). Emitted through redact_urls for the same
#                      reason as `title`: it is a free string, not the
#                      three-letter code the format recommends, and the
#                      guide turns it into a displayed name.
#   codec              the decoder name mpv resolved. Emitted through
#                      redact_urls on the same footing.
#
# An earlier version of this comment said "two of its fields" and redacted
# one. That is the completed-audit claim rule 5 exists to stop: the author
# audited the fields they thought of rather than the ones mpv documents as
# file-supplied. Counted against the manual by the 0.9.0 preflight.
TRACK_TYPES = ("audio", "sub")
TRACK_FIELDS = ("id", "type", "selected", "lang", "title", "codec", "default", "forced", "external")
# D-SRC-13's rule 15 sweep (2026-10-21): the tracks reply is collected WHOLE
# by the shell (controlStdout, a StdioCollector with waitForEnd), and both
# the number of tracks and the three free-text fields are the stream's, so
# neither was bounded by anything but the stream. Each is now a constant:
# at most TRACK_MAX_ROWS rows, kept in mpv's order, the rest COUNTED in the
# reply's `tracksOmitted` (parse_m3u's channel_warning shape); each text cut
# to its cap. The figures are chosen, not measured: a picker of 64 rows is
# already more than a person reads, a language code is three letters and a
# codec name a word, so the caps cut nothing an ordinary stream carries,
# and the reply is at most TRACK_MAX_ROWS rows of a constant size.
TRACK_MAX_ROWS = 64
TRACK_MAX_TITLE = 256
TRACK_MAX_LANG = 64
TRACK_MAX_CODEC = 64


def track_text(value: Any, limit: int) -> str:
    """A track's free-text field, redacted and then cut to `limit` code points
    (the cut after the redaction, so a URL is never half-redacted)."""
    if not isinstance(value, str):
        return ""
    return redact_urls(value)[:limit]


def track_rows(data: Any, omitted: list[int] | None = None) -> list[dict[str, Any]]:
    """The picker's rows from a raw track-list: audio and sub only, ints for
    ids, strings for text, bools for flags, in the order mpv listed them.
    Anything malformed is dropped rather than raising: a picker with one
    strange row missing beats no picker. At most TRACK_MAX_ROWS rows; every
    well-formed row past them is counted into `omitted[0]` when it is given."""
    rows: list[dict[str, Any]] = []
    if not isinstance(data, list):
        return rows
    for entry in data:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("type")
        ident = entry.get("id")
        if kind not in TRACK_TYPES or isinstance(ident, bool) or not isinstance(ident, int):
            continue
        if len(rows) >= TRACK_MAX_ROWS:
            if omitted is not None:
                omitted[0] += 1
            continue
        rows.append({
            "id": ident,
            "type": kind,
            "selected": entry.get("selected") is True,
            "lang": track_text(entry.get("lang"), TRACK_MAX_LANG),
            "title": track_text(entry.get("title"), TRACK_MAX_TITLE),
            "codec": track_text(entry.get("codec"), TRACK_MAX_CODEC),
            "default": entry.get("default") is True,
            "forced": entry.get("forced") is True,
            "external": entry.get("external") is True,
        })
    return rows


def track_choice(text: str | None) -> int | str | None:
    """`--audio 2` / `--sub no`: an mpv track id or the word `no`; None when
    the option was not given. Anything else is a usage error, raised as a
    HelperError so it reaches the service as a status and not a traceback."""
    if text is None:
        return None
    value = text.strip().lower()
    if value == "no":
        return "no"
    # isascii() as well as isdigit(): str.isdigit() is True for superscripts
    # and other Unicode digits that int() then refuses, so the bare isdigit()
    # let a ValueError escape this function's own contract and come out of
    # main() as code "internal" with a traceback -- D-PLY-20's exact failure
    # mode, inside the release that fixes D-PLY-20. Found by the 0.9.0
    # preflight, measured with "\u00b2".
    if value.isascii() and value.isdigit():
        return int(value)
    raise HelperError("bad_track", "a track is a number or 'no'")


def player_tracks(args: argparse.Namespace) -> int:
    """List the audio and subtitle tracks, after applying a selection if one
    was asked for. The reply always carries the list AS MPV NOW HAS IT, so
    the guide shows what the player did rather than what it was asked
    (PLAN-M3 decision 5). Side-effect-free like `pause`: no player, no spawn,
    `running: false` and an empty list."""
    sock = socket_path(args.socket)
    payload: dict[str, Any] = {"ok": True, "kind": "player.tracks", "running": False,
                               "tracks": [], "changed": False}
    try:
        audio = track_choice(args.audio)
        sub = track_choice(args.sub)
    except HelperError as error:
        emit(error_payload("player.tracks", error))
        return EXIT_ERROR
    if not find_player(sock):
        emit(payload)
        return EXIT_OK
    client = probe_client(sock, args.ipc_timeout)
    if client is None:
        emit(payload)
        return EXIT_OK
    try:
        payload["running"] = True
        for prop, want in (("aid", audio), ("sid", sub)):
            if want is None:
                continue
            set_ok, _ = client.try_command("set_property", prop, want)
            if not set_ok:
                raise HelperError("track_refused", "the player refused that track")
            payload["changed"] = True
        ok, data = client.try_command("get_property", "track-list")
        omitted = [0]
        payload["tracks"] = track_rows(data, omitted) if ok else []
        if omitted[0]:
            # Additive, and present only when rows were left out: the reply
            # of every ordinary stream is byte-identical to before.
            payload["tracksOmitted"] = omitted[0]
        emit(payload)
        return EXIT_OK
    except HelperError as error:
        # A status the service can switch on, like every other verb. Without
        # this the refusal fell through to main() as `internal` with a
        # traceback on stderr -- which is what `pause` did from 0.7.10 until
        # the tracks verb was built beside it (D-PLY-20).
        emit(error_payload("player.tracks", error))
        return EXIT_ERROR
    finally:
        client.close()


# ---- M5-01: live rewind ----------------------------------------------------
#
# M5-01-LIVE-REWIND.md (dev branch) 2.1 and 2.2, on SPIKE-LIVE-REWIND.md (dev branch) 11 and
# 12. Rewind, forward and back-to-live INSIDE the demuxer cache mpv already
# keeps on the plugin's own argv: no option added, nothing written, nothing
# forked. The verb is `player seek`, beside `player pause`, same socket, same
# request ids, same single control slot.
#
# What the measurements fixed, and this code obeys:
#   - `seekable` and `partially-seekable` read false on every live channel
#     that rewound; `demuxer-cache-state.seekable-ranges` is the truth.
#   - mpv answers `success` to a seek it DROPS (below the floor or past the
#     end), so a reply is no evidence of movement. The detector is the
#     immediate `time-pos` read after the reply: a landed seek echoes its
#     target to the millisecond (72 of 72), a refused one echoes the previous
#     position within one frame (31 of 31, max 0.033 s). Threshold 0.5 s.
#   - A NEGATIVE absolute target is an offset from the cache END, not a
#     refusal (F-RWD-7, 5 of 5 moved to the live edge). The clamp keeps every
#     target at or above `floor + 2`, and with no range at all the helper
#     refuses WITHOUT seeking: `position + by` is never sent raw.
#   - "Behind live" is `(wall - wall0) - (pos - pos0)` from a zero point
#     taken at the first `time-pos` after each loadfile, never
#     `cache end - time-pos`: after a deep rewind the fetch stalls, the cache
#     end freezes and that difference counts DOWN while the real gap holds.
#     Zero-point error measured below 0.05 s at a minute on clean streams.
#   - Every field of `demuxer-cache-state` was enumerated on the real player
#     (12.1): twenty leaves, one string among them (`ts-per-stream[].type`,
#     mpv's own "video"/"audio"), nothing that is a path, URL or title. The
#     allowlist below is built from that reply; the string never enters.
#
# Nothing in a reply is a string from the stream: numbers, booleans and null.
# `path` is never read here. The one line that reaches the player's OSD is
# composed from numbers and this file's own words, and never contains `$`,
# because `show-text` property-expands (the reason --osd-msg1..3 are
# reserved).
SEEK_FLOOR_MARGIN_S = 2.0        # a target at the floor lands 1-2 s above it; below it is dropped
SEEK_EDGE_MARGIN_S = 0.5         # the edge target, inside the range
SEEK_MOVED_THRESHOLD_S = 0.5     # 0.467 above the refused max, 1.5 below the smallest request (12.2)
# How long `player seek` waits, after mpv's reply to the seek command, for
# the `seek` event (the seek executed) or the refusal log line (it was
# dropped) before reading `time-pos`. The reply to `seek` is sent when the
# seek is QUEUED, and the playloop executes it afterwards, so a read sent
# at once can be answered first and echo the old position: measured on
# 2026-10-03 on a local HLS stream, 1 of 12 immediate reads (the fastest,
# 0.10 ms after the reply) read the old position while the event arrived
# 0.31-0.87 ms after the reply on all 12 and the read after it was exact on
# all 12 (F-RWD-15). The bound is 300 times that latency and inside the
# 300 ms per-press budget; only a seek that is neither executed nor refused
# within it pays the whole bound, and then the read and the threshold decide.
SEEK_EVENT_BOUND_S = 0.25
SEEK_REFUSAL_TEXT = "Cannot seek in this stream"
BEHIND_LIVE_SHOW_S = 2           # mirrors Model.BEHIND_LIVE_SHOW_S (12.4: fifty-fold margin)
OSD_TEXT_MS = 3000               # the show-text duration M3 measured
# The twelve leaves forwarded out of `demuxer-cache-state` (12.1), as
# (mpv name, our name, type). The other eight -- the three debug-* counters,
# raw-input-rate and the four ts-per-stream[] leaves -- are dropped.
CACHE_STATE_SCALARS = (
    ("cache-end", "cacheEnd", float), ("reader-pts", "readerPts", float),
    ("cache-duration", "cacheDuration", float), ("fw-bytes", "fwBytes", int),
    ("total-bytes", "totalBytes", int), ("underrun", "underrun", bool),
    ("idle", "idle", bool), ("eof", "eof", bool), ("eof-cached", "eofCached", bool),
    ("bof-cached", "bofCached", bool),
)


def _boot_clock() -> float:
    """The clock the zero point is taken on. CLOCK_BOOTTIME counts a suspend
    (the provider's edge moves on while the box sleeps, so the viewer IS that
    much further behind) and never jumps with NTP, which the wall clock does.
    Indirection so tests can hold it still."""
    try:
        return time.clock_gettime(time.CLOCK_BOOTTIME)
    except (AttributeError, OSError):
        return time.monotonic()


def round3(value: float) -> float:
    """Three decimals, half up, the same arithmetic as Model.round3 so the
    shared fixtures compare equal across the two implementations."""
    return math.floor(float(value) * 1000.0 + 0.5) / 1000.0


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def cache_state_view(raw: Any) -> dict[str, Any]:
    """The allowlisted view of `demuxer-cache-state` (12.1). Only the twelve
    enumerated leaves pass, each coerced to its measured type; a leaf of the
    wrong type is dropped rather than forwarded. The reply's one string leaf
    is not on the list, so no string ever enters."""
    view: dict[str, Any] = {"seekableRanges": []}
    if not isinstance(raw, dict):
        return view
    for mpv_name, ours, kind in CACHE_STATE_SCALARS:
        value = raw.get(mpv_name)
        if kind is bool:
            if isinstance(value, bool):
                view[ours] = value
        elif kind is int:
            if isinstance(value, int) and not isinstance(value, bool):
                view[ours] = value
        else:
            number = _finite(value)
            if number is not None:
                view[ours] = number
    ranges = raw.get("seekable-ranges")
    if isinstance(ranges, list):
        for entry in ranges:
            if not isinstance(entry, dict):
                continue
            start = _finite(entry.get("start"))
            end = _finite(entry.get("end"))
            if start is not None and end is not None and end >= start:
                view["seekableRanges"].append({"start": start, "end": end})
    return view


def range_for(ranges: list[dict[str, Any]], position: float | None) -> dict[str, Any] | None:
    """The seekable range the reader sits in; failing that the last range
    that starts at or before the position; failing that the first. None
    when there is no range at all, which is the one case the verb must
    refuse WITHOUT seeking (F-RWD-7)."""
    if not ranges:
        return None
    if position is not None:
        for entry in ranges:
            if entry["start"] <= position <= entry["end"]:
                return entry
        below = [entry for entry in ranges if entry["start"] <= position]
        if below:
            return below[-1]
    return ranges[0]


def clamp_seek(opts: dict[str, Any]) -> dict[str, Any]:
    """Mirror of Model.clampSeek, pinned by the rewind-clamp.json fixture (dev branch).

    `opts`: position, floor, ceiling (seconds; floor and ceiling from the
    seekable range the reader sits in), mode "by" | "live", by (signed
    seconds, negative is back). Returns the plan: `target` (absolute), whether
    it was `clamped` and to what, `atFloor` / `atEdge`, and `issue` -- False
    when the target is within the not-moved threshold of the position, where
    a seek would be reported refused whether or not mpv moved (12.2).

    A back press never produces a target above the position and a forward or
    live press never one below it, so a tiny range (the first seconds after
    a zap) answers atFloor / atEdge rather than moving the wrong way.
    """
    mode = "live" if opts.get("mode") == "live" else "by"
    by = _finite(opts.get("by"))
    by = 0.0 if by is None else by
    position = _finite(opts.get("position"))
    floor = _finite(opts.get("floor"))
    ceiling = _finite(opts.get("ceiling"))
    # A whole-second request stays the integer it was asked as (-10, not
    # -10.0): JSON readers see the number the design shows.
    requested = int(by) if by == int(by) else round3(by)
    plan: dict[str, Any] = {
        "ok": False, "mode": mode, "requested": requested if mode == "by" else None,
        "target": None, "clamped": False, "clampedTo": None,
        "atFloor": False, "atEdge": False, "issue": False,
    }
    if position is None or floor is None or ceiling is None or ceiling < floor:
        return plan
    plan["ok"] = True
    low = floor + SEEK_FLOOR_MARGIN_S
    high = ceiling - SEEK_EDGE_MARGIN_S
    if mode == "live":
        want = high
        plan["requested"] = round3(high - position)
    else:
        want = position + by
    target = want
    if mode == "by" and by < 0:
        if target < low:
            target = low
            plan["clamped"] = True
            plan["atFloor"] = True
        if target > position:
            target = position
    elif mode == "by" and by > 0:
        if target > high:
            target = high
            plan["clamped"] = True
            plan["atEdge"] = True
        if target < position:
            target = position
    elif mode == "live":
        plan["atEdge"] = True
        if target < position:
            target = position
    else:
        target = position
    plan["issue"] = abs(target - position) >= SEEK_MOVED_THRESHOLD_S
    plan["target"] = round3(target)
    plan["clampedTo"] = round3(target) if plan["clamped"] else None
    return plan


def clock_span(seconds: Any) -> str:
    """Mirror of Model.clockSpan: "m:ss", or "h:mm:ss" from an hour on."""
    number = _finite(seconds)
    total = 0 if number is None or number < 0 else int(math.floor(number))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours > 0:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%d:%02d" % (minutes, secs)


def rewind_osd_text(reply: Any) -> str:
    """Mirror of Model.rewindOsdText, pinned by the rewind-osd.json fixture (dev branch).

    The one line `player seek` puts on the player's OSD (owner decision D9).
    Composed from the reply's numbers and this function's own words only:
    nothing from the stream, and never a `$`, because show-text expands
    `${...}` against the player's properties, `path` included. "" when there
    is nothing to say -- a refused seek, or no zero point yet.
    """
    if not isinstance(reply, dict) or reply.get("refused") is True:
        return ""
    rewind = reply.get("rewind")
    if not isinstance(rewind, dict):
        return ""
    behind = _finite(rewind.get("behindLive"))
    if behind is None:
        return ""
    if behind < BEHIND_LIVE_SHOW_S:
        text = "live"
    else:
        text = "-" + clock_span(behind) + " behind live"
    if reply.get("atFloor") is True:
        text += ", as far back as it goes"
    elif reply.get("atEdge") is True and behind >= BEHIND_LIVE_SHOW_S:
        text += ", at the edge of the buffer"
    if rewind.get("paused") is True:
        text = "paused, " + text
    return text


def rewind_node_valid(node: Any, entry_id: int | None) -> bool:
    """A zero point is valid for exactly one entry id: the one the stash
    carries now. Any other, or an absent entry id, is no zero point."""
    if entry_id is None or not isinstance(node, dict):
        return False
    return (node.get("schema") == REWIND_SCHEMA and node.get("entryId") == entry_id
            and _finite(node.get("wall0")) is not None and _finite(node.get("pos0")) is not None)


def stash_entry_id(stash: Any) -> int | None:
    entry = stash.get("entryId") if isinstance(stash, dict) else None
    return entry if isinstance(entry, int) and not isinstance(entry, bool) and entry > 0 else None


def zero_point(client: MpvIpc, entry_id: int | None, position: float | None,
               wall: float, write: bool) -> dict[str, Any] | None:
    """The zero point for `entry_id`, read from the player; with `write`,
    taken now from (`wall`, `position`) when none valid exists. `position`
    must be a read that no seek sits between it and `wall`."""
    ok, node = client.try_command("get_property", USER_DATA_REWIND)
    if ok and rewind_node_valid(node, entry_id):
        return node
    if not write or entry_id is None or position is None:
        return None
    node = {"schema": REWIND_SCHEMA, "entryId": entry_id, "wall0": wall, "pos0": position}
    written, _ = client.try_command("set_property", USER_DATA_REWIND, node)
    return node if written else None


def rebase_zero_point(client: MpvIpc, zero: dict[str, Any] | None, entry_id: int | None,
                      position: float | None, wall: float, write: bool) -> dict[str, Any] | None:
    """A reading AHEAD of the zero point is a better observation of the live
    edge than the one stored, so the zero point moves to it (F-RWD-11).

    The zero point is taken where the reader first sits after a loadfile, and
    the reader sits behind the cache end there by the HLS lead: 3.6 s on the
    QA stream, 13-21 s on the owner's channels (spike 11.3). A `live` seek
    lands at the cache end, past that point, and the formula then reads
    negative -- not "ahead of live", which nobody can be, but "the edge was
    further on than first observed". Left alone, the next `back 10` reads
    7 behind on a stream with a 3 s lead and 0 on one with a 20 s lead, under
    a transient that says "Back 10 s". Re-based, it reads 10. With `write`
    False (the probe, which never writes) the raw reading is returned and the
    node left alone; the shell clamps at 0 for display either way."""
    if zero is None or position is None or not write or entry_id is None:
        return zero
    behind = (wall - float(zero["wall0"])) - (position - float(zero["pos0"]))
    if behind >= 0:
        return zero
    node = {"schema": REWIND_SCHEMA, "entryId": entry_id, "wall0": wall, "pos0": position}
    written, _ = client.try_command("set_property", USER_DATA_REWIND, node)
    return node if written else zero


def rewind_view(position: float | None, cache: dict[str, Any], zero: dict[str, Any] | None,
                paused: Any, paused_for_cache: Any, entry_id: int | None, wall: float) -> dict[str, Any] | None:
    """The `rewind` object every player reply carries (2.1). None when the
    player has no numeric `time-pos` -- a demuxer still opening after a zap
    -- and `behindLive` None when there is no zero point: absent, never 0
    (D-DEAD-1)."""
    if position is None:
        return None
    current = range_for(cache.get("seekableRanges") or [], position)
    behind = None
    # Only inside a range: with a valid node and a position outside every
    # range (a stream re-opening, a discontinuity) the formula read -36 on
    # the live-pass tree, and the invariant the shell relies on is "never
    # negative, or null" (review finding against design 2.2). No range, no
    # number.
    if zero is not None and current is not None:
        behind = round3((wall - float(zero["wall0"])) - (position - float(zero["pos0"])))
    return {
        "position": round3(position),
        "floor": round3(current["start"]) if current else None,
        "ceiling": round3(current["end"]) if current else None,
        "history": round3(position - current["start"]) if current else None,
        "ahead": round3(current["end"] - position) if current else None,
        "behindLive": behind,
        "zeroed": zero is not None,
        "paused": paused is True,
        "pausedForCache": paused_for_cache is True,
        "entryId": entry_id,
    }


def read_rewind(client: MpvIpc, stash: Any = None, paused: Any = None, write: bool = True) -> dict[str, Any] | None:
    """One read of the rewind state for the `status`, `pause` and `probe`
    replies: time-pos, the allowlisted cache state, paused-for-cache, and the
    zero point (written lazily unless `write` is False). `stash` is the
    stash already read by the caller, or None to read it here."""
    if stash is None:
        ok, stash = client.try_command("get_property", USER_DATA_STASH)
        stash = stash if ok and isinstance(stash, dict) else None
    entry_id = stash_entry_id(stash)
    ok, pos = client.try_command("get_property", "time-pos")
    position = _finite(pos) if ok else None
    wall = _boot_clock()
    ok, raw = client.try_command("get_property", "demuxer-cache-state")
    cache = cache_state_view(raw if ok else None)
    if paused is None:
        ok, value = client.try_command("get_property", "pause")
        paused = bool(value) if ok and value is not None else False
    ok, pfc = client.try_command("get_property", "paused-for-cache")
    paused_for_cache = bool(pfc) if ok and pfc is not None else False
    # A position with no seekable range is not a playing position (F-RWD-16):
    # mpv reports time-pos 0 while a stream is still opening, or never
    # opens, and a zero point taken there counts up from a moment nothing
    # had played. Read it, say it, but neither take nor move the zero point
    # until the reader sits inside a range.
    inside = position is not None and range_for(cache["seekableRanges"], position) is not None
    zero = zero_point(client, entry_id, position, wall, write and inside) if position is not None else None
    zero = rebase_zero_point(client, zero, entry_id, position, wall, write and inside)
    return rewind_view(position, cache, zero, paused, paused_for_cache, entry_id, wall)


def await_seek_outcome(client: MpvIpc, deadline: float) -> tuple[str | None, bool]:
    """After the reply to `seek`: ("landed", settled) once the `seek` event
    has arrived (mpv executed it), ("refused", False) when the error-level
    refusal line arrives (mpv dropped it), (None, False) when neither did
    by `deadline`. `settled` is True when the `playback-restart` event
    followed the `seek` event before `deadline`: mpv's "the decoder is
    producing frames at the new position", which is the DECODED landing
    (F-RWD-8). The `seek` event alone is the request echoed -- the
    F-RWD-15 probe read time-pos after it and saw the target 12 of 12,
    with `playback-restart` 26-40 ms later and the picture up to 5.1 s
    past the target on the next keyframe -- so a read taken on `seek`
    reports what was asked, not where the player is, and the OSD line
    composed from it drew the wrong number for up to a status tick. The
    wait for the restart costs those 26-40 ms against SEEK_EVENT_BOUND_S
    and the 300 ms per-press budget; a `seek` with no restart by the bound
    is still "landed" (the read decides, as before), with `settled` False
    so the reply says which it got and the status tick stays the truth.
    The caller must have subscribed with `request_log_messages error`. The
    line's text is matched, never printed: it is mpv's own sentence, but
    the rule for this sink is nothing from the player reaches stdout
    unexamined.

    A `seek` event carries no origin, so one raised by a seek that is not
    ours -- the user's own arrow key in the player window at the same
    instant -- counts as ours (review nit, accepted): the read that
    follows still decides by the threshold, and the status tick re-syncs.
    A `playback-restart` is counted only after a `seek` was seen."""
    landed = False
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return ("landed" if landed else None), False
        events = client.drain_events(deadline)
        if events is None:
            return ("landed" if landed else None), False
        for event in events:
            name = event.get("event")
            if name == "seek":
                landed = True
            elif name == "playback-restart" and landed:
                return "landed", True
            elif name == "log-message" and SEEK_REFUSAL_TEXT in str(event.get("text", "")):
                return "refused", False


def player_seek(args: argparse.Namespace) -> int:
    """`player seek --by N` (signed seconds, negative is back) or `--live`.

    One run: read time-pos and the cache state, clamp (clamp_seek), issue ONE
    absolute seek, wait for the `seek` event and then the `playback-restart`
    that says the decoder landed, or the refusal line (bounded, F-RWD-15,
    F-RWD-8), read time-pos again, decide moved or refused by the
    not-moved threshold, take the zero point if none exists, put one
    numbers-only line on the OSD when the request was honoured, and reply;
    `settled` in the reply says whether the restart was seen, so `applied`
    is the decoded landing when it is True and the request as echoed when
    it is False. Side-effect-free when no player is there, like `pause`.
    """
    sock = socket_path(args.socket)
    mode = "live" if args.live else "by"
    by = int(args.by) if mode == "by" and args.by is not None else 0
    payload: dict[str, Any] = {
        "ok": True, "kind": "seek", "running": False, "mode": mode,
        "requested": by if mode == "by" else None, "applied": 0,
        "clamped": False, "clampedTo": None, "refused": True,
        "atFloor": False, "atEdge": False, "rewind": None, "settled": False,
    }
    if not find_player(sock):
        emit(payload)
        return EXIT_OK
    client = probe_client(sock, args.ipc_timeout)
    if client is None:
        emit(payload)
        return EXIT_OK
    try:
        payload["running"] = True
        ok, stash = client.try_command("get_property", USER_DATA_STASH)
        stash = stash if ok and isinstance(stash, dict) else None
        entry_id = stash_entry_id(stash)
        ok, pos = client.try_command("get_property", "time-pos")
        before = _finite(pos) if ok else None
        wall_before = _boot_clock()
        ok, raw = client.try_command("get_property", "demuxer-cache-state")
        cache = cache_state_view(raw if ok else None)
        ok, value = client.try_command("get_property", "pause")
        paused = bool(value) if ok and value is not None else False
        ok, pfc = client.try_command("get_property", "paused-for-cache")
        paused_for_cache = bool(pfc) if ok and pfc is not None else False
        # The zero point is taken from the PRE-seek read: a seek breaks the
        # (wall, pos) relation, so one taken after it would read a fresh
        # rewind as "at live". And only from a position inside a range
        # (F-RWD-16): with no range there is nothing playing to be behind.
        current = range_for(cache["seekableRanges"], before)
        zero = zero_point(client, entry_id, before, wall_before, current is not None) if before is not None else None
        plan = clamp_seek({
            "position": before, "mode": mode, "by": by,
            "floor": current["start"] if current else None,
            "ceiling": current["end"] if current else None,
        })
        payload["requested"] = plan["requested"]
        payload["clamped"] = plan["clamped"]
        payload["clampedTo"] = plan["clampedTo"]
        payload["atFloor"] = plan["atFloor"]
        payload["atEdge"] = plan["atEdge"]
        after = before
        if not plan["ok"]:
            # No position or no range: nothing to seek within. Refused here,
            # never computed and sent (F-RWD-7).
            payload["refused"] = True
        elif not plan["issue"]:
            payload["refused"] = False
        else:
            # The reply to `seek` means queued, not executed (F-RWD-15): the
            # read that decides moved-or-refused waits for the event that
            # says it ran AND the restart that says the decoder landed
            # (F-RWD-8), or the line that says it was dropped, or the
            # bound. The outcome decides only WHEN to read; the verdict is
            # the read against the threshold, as measured (12.2) -- a
            # `refused` clause on the outcome was an equivalent mutant,
            # because a dropped seek leaves the position where it was. The
            # subscription is error-level only and the text is never emitted.
            client.try_command("request_log_messages", "error")
            sent, _ = client.try_command("seek", plan["target"], "absolute")
            if sent:
                _, payload["settled"] = await_seek_outcome(client, time.monotonic() + SEEK_EVENT_BOUND_S)
            ok, pos = client.try_command("get_property", "time-pos")
            after = _finite(pos) if ok else None
            if not sent or after is None or before is None or abs(after - before) < SEEK_MOVED_THRESHOLD_S:
                payload["refused"] = True
                after = before if after is None else after
            else:
                payload["refused"] = False
                payload["applied"] = round3(after - before)
        # The post-seek reading, on a clock read AFTER the seek. A `live` that
        # landed past the zero point re-bases it here (F-RWD-11), so the
        # reply reads 0.0 at the edge and the next `back 10` reads 10.
        wall_after = _boot_clock()
        zero = rebase_zero_point(client, zero, entry_id, after, wall_after, current is not None)
        payload["rewind"] = rewind_view(after, cache, zero, paused, paused_for_cache, entry_id, wall_after)
        # The composer decides what is said and when (a refused seek and a
        # missing zero point both compose to ""), so there is ONE guard, the
        # one the shared fixture pins. A second `if not refused` here was an
        # equivalent mutant: nothing could tell it from its absence.
        text = rewind_osd_text(payload)
        if text:
            client.try_command("show-text", text, OSD_TEXT_MS)
        emit(payload)
        return EXIT_OK
    except HelperError as error:
        emit(error_payload("seek", error))
        return EXIT_ERROR
    finally:
        client.close()


def cmd_player(args: argparse.Namespace) -> int:
    action = args.action
    if action == "start":
        return player_start(args, "start")
    if action == "restart":
        return player_start(args, "restart")
    if action == "stop":
        return player_stop(args)
    if action == "probe":
        return player_probe(args)
    if action == "pause":
        return player_pause(args)
    if action == "tracks":
        return player_tracks(args)
    if action == "seek":
        return player_seek(args)
    return player_orphan_check(args)


