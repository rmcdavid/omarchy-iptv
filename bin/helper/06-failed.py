# A part of bin/omarchy-iptv (D-REL-7), not a module: the helper compiles
# this file into its own namespace in the order its HELPER_PARTS lists, so
# a part sees every name the parts before it define. Run the helper.
from __future__ import annotations
# ---- dead-channel memory (PO 2026-09-24, amending R8 / R11 / UX ruling 9)
#
# Mirror of Model.normalizeFailed / prunedFailed. Must match the model.
# The marks live in the SOURCE CACHE, never in state.json: channel ids are
# global across sources, so a state-level map would mark another provider's
# working channel, and it would fall inside D-ID-1's id-rotation blast radius
# which that defect records as excluded precisely because this was
# session-only. Per source, it stays excluded.
MAX_FAILED = 300
FAILED_TTL_SEC = 14 * 24 * 3600


def normalize_failed(rows: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        cid = row.get("id")
        at = coerce_int(row.get("at"))
        if not isinstance(cid, str) or not cid or at is None or at <= 0:
            continue
        if cid in seen:
            continue
        seen.add(cid)
        out.append({"id": cid, "at": at})
        if len(out) >= MAX_FAILED:
            break
    return out


def prune_failed(rows: Any, now: int, known: set[str] | None) -> list[dict[str, Any]]:
    """Drop what aged out and what the playlist no longer has.

    The second half is what makes this self-healing: an id rotation, a
    provider reshuffle and a removed channel all leave marks naming nothing,
    and all three are cleaned up here instead of by a migration. `known` of
    None skips it, so a caller without channels cannot wipe the file.
    """
    out = []
    for row in normalize_failed(rows):
        if now > 0 and row["at"] < now - FAILED_TTL_SEC:
            continue
        if known is not None and row["id"] not in known:
            continue
        out.append(row)
    return out


def read_failed(directory: str) -> list[dict[str, Any]]:
    doc = read_json(os.path.join(directory, FAILED_FILE))
    return normalize_failed(doc.get("failed") if isinstance(doc, dict) else None)


def known_channel_ids(directory: str) -> set[str] | None:
    """The current playlist's ids, or None when there is no cache to ask."""
    doc = read_json(os.path.join(directory, CHANNELS_FILE))
    if not isinstance(doc, dict) or not isinstance(doc.get("channels"), list):
        return None
    return {c["id"] for c in doc["channels"] if isinstance(c, dict) and isinstance(c.get("id"), str) and c["id"]}


def cmd_failed(args: argparse.Namespace) -> int:
    """mark / clear / list the failure marks of one source's cache."""
    directory = cache_dir(args.cache_dir)
    now = int(args.now) if args.now else int(time.time())
    rows = read_failed(directory)
    if args.action == "mark":
        cid = (args.id or "").strip()
        if not cid:
            raise HelperError("bad_id", "a channel id is required")
        rows = [r for r in rows if r["id"] != cid]
        rows.insert(0, {"id": cid, "at": now})
    elif args.action == "clear":
        cid = (args.id or "").strip()
        rows = [] if not cid else [r for r in rows if r["id"] != cid]
    # `list` falls through: pruning and emitting is the whole of it.
    rows = prune_failed(rows, now, known_channel_ids(directory))
    if args.action in ("mark", "clear"):
        ensure_private_dir(directory)
        write_json_atomic(os.path.join(directory, FAILED_FILE), {"version": 1, "failed": rows})
    emit({"ok": True, "kind": "failed", "action": args.action, "count": len(rows), "failed": rows})
    return 0


def cmd_logos(args: argparse.Namespace) -> int:
    directory = cache_dir(args.cache_dir)
    channels = load_channels(directory)
    survey = logo_survey(channels)
    if not args.fetch:
        emit(dict(survey, ok=True, kind="logos", action="survey"))
        return 0
    # The fetch is opt-in twice over: the setting is off by default (the
    # ruling's first line) and this flag is off by default here, so nothing
    # contacts anyone because a command was run without reading it.
    logo_dir = os.path.join(directory, LOGO_SUBDIR)
    fetched, cached, refused, failed, swept, deferred, rewritten = 0, 0, 0, 0, 0, 0, 0
    reasons: dict[str, int] = {}
    seen: set[str] = set()
    names: list[str] = []
    for channel in channels:
        # MAX_LOGO_FILES is checked BELOW the cached-file branch, not here.
        # It used to be the first line of this loop, as a `break`, which
        # bounded the wrong thing: in a run that fetched 5,000 new files,
        # every cached file later in channel order was neither validated nor
        # announced that run, so the guide drew blank slots for logos it
        # already had and a cached bomb past the cap was never swept (R5). A
        # review found the comment beside the sweep claiming the branch was
        # not bounded by the cap, which was true only while fetched < 5000.
        url = channel.get("logo") if isinstance(channel, dict) else None
        if not isinstance(url, str) or not url or url in seen:
            continue
        seen.add(url)
        # Already on disk: no request. Without this the shell re-downloaded
        # every logo on every start, because the service runs a fetch whenever
        # the channel cache loads -- 1,445 requests to sixty-three third
        # parties per launch, which is precisely the disclosure the ruling
        # exists to bound. The file name is a pure function of the URL, so
        # "have we got this one" is a stat and not a lookup.
        name = logo_filename(url)
        path = os.path.join(logo_dir, name)
        if os.path.exists(path):
            # D-LOGO-11 / R5: the cache written by 0.13.3 and earlier was
            # never dimension-checked, so "already on disk" is not evidence
            # that this file is safe to hand the shell. The header is proved
            # BEFORE the name is announced, because the guide points an Image
            # at a file only when this command names it (Model.logoSlot,
            # Service.qml logoHave). Reading a header is a small read and it
            # happens in the HELPER, off the UI thread and nowhere near the
            # guide's 150 ms open budget. Measured on this machine with 5,000
            # real 220x120 logos all already cached: the whole `logos --fetch`
            # subprocess went from a median 375 ms to 601 ms, so the check
            # costs about 45 us per cached file end to end (22 us per call in
            # isolation, 37 us on 44 KB files). This branch is NOT bounded by
            # MAX_LOGO_FILES, and since the cap check moved below it that is
            # true for the whole run and not only while fetched < 5000:
            # `fetched` counts new downloads, so the cap bounds fetches per
            # run and not the size of the cache or the number of files this
            # validates (D-LOGO-12 records the consequence for the cache).
            # D-LOGO-13: a PNG is announced only in its canonical form, so a
            # file an earlier version cached verbatim is rewritten in place
            # first, and one whose chunks cannot be walked is swept below.
            state = canonical_logo_file(path) if logo_file_within_bounds(path) else ""
            if state:
                cached += 1
                rewritten += state == "rewritten"
                names.append(name)
                emit({"ok": True, "kind": "logo", "name": name})
                continue
            # Not announced, and NOT counted as `cached`: it is not on disk
            # any more. The pass falls through to the fetch below, which
            # refuses the same bytes at the gate and counts the reason there,
            # so one bomb is one refusal rather than two -- and a provider
            # that has since replaced the file with a sane one gets it. If the
            # unlink fails the name is still withheld; the fetch may yet
            # replace the bytes, and a name the guide is never given is a file
            # the shell never decodes.
            swept += 1
            try:
                os.unlink(path)
            except OSError:
                pass
        if fetched >= MAX_LOGO_FILES:
            # The cap bounds NEW FETCHES ONLY. A cached file past it was
            # validated and announced above; a URL past it is not fetched this
            # run and is counted here rather than vanishing, so a run that
            # stopped short says so (the same reason `swept` is a number). A
            # swept bomb past the cap stays off the disk and off the stream,
            # and is refused at the gate on the run that reaches it.
            deferred += 1
            continue
        try:
            data, ctype = fetch_logo(url, args.timeout)
            names.append(write_logo(logo_dir, url, data, ctype))
            fetched += 1
            # D-LOGO-8: announce each file AS IT LANDS, not only in the summary.
            # The shell gates a row on knowing the file is there, and the
            # summary arrives at the END -- so on a first enable the user
            # accepted a 63-host disclosure and then watched nothing happen for
            # a quarter of an hour while the logos they were waiting for were
            # already on disk. Measured: 355 files down, 10 of the 10 channels
            # visible in the guide cached, every row still blank.
            #
            # One line per file, newline-delimited, and the summary object is
            # still the last line. A reader that wants only the summary reads
            # the last line; nothing else about the contract changes.
            emit({"ok": True, "kind": "logo", "name": names[-1]})
        except HelperError as error:
            # Hosts and codes only, never the URL (rule 5).
            reasons[error.code] = reasons.get(error.code, 0) + 1
            if error.code in ("logo_scheme", "logo_userinfo", "logo_redirect",
                              "logo_type", "logo_bytes", "logo_too_large",
                              "logo_dimensions", "logo_chunks"):
                refused += 1
            else:
                failed += 1
    # `names` is what is ON DISK now, and it is the whole reason this command
    # reports anything at all: the guide points an Image at a file only when
    # that file is in this list. Pointing at a missing one is not merely a
    # blank slot -- Qt logs "Cannot open" for every attempt, so one dead logo
    # host fills the user's journal every time the row scrolls into view.
    # Seen live 2026-09-23 before this existed.
    #
    # It carries no URLs, only their hashes, so it is safe on stdout.
    #
    # `swept` is the number of files the dimension check removed from the
    # cache (D-LOGO-11, R5). It is reported because a removal that appeared in
    # no number at all would be invisible whenever the refetch then succeeded,
    # and because `cached` had to stop counting those files to stay true.
    # `deferred` is the number of URLs the per-run cap held back from a fetch;
    # the cached-file branch above is never held back, so a cached logo past
    # the cap is in `names` and a cached bomb past it is in `swept`.
    # `rewritten` counts the cached PNGs made canonical this run (D-LOGO-13);
    # they are in `cached` too, and a file that could not be is in `swept`.
    emit(dict(survey, ok=True, kind="logos", action="fetch", fetched=fetched,
              cached=cached, refusedOnPolicy=refused, failed=failed, reasons=reasons,
              names=names, swept=swept, rewritten=rewritten, deferred=deferred, cap=MAX_LOGO_FILES,
              maxBytes=MAX_LOGO_BYTES, maxSide=MAX_LOGO_SIDE, maxPixels=MAX_LOGO_PIXELS))
    return 0


def load_channels(directory: str) -> list[dict[str, Any]]:
    document = read_json(os.path.join(directory, CHANNELS_FILE))
    if not isinstance(document, dict) or not isinstance(document.get("channels"), list):
        raise HelperError("no_cache", "channel cache not found; refresh the playlist first")
    return document["channels"]


def find_channel(channels: list[dict[str, Any]], wanted: str) -> dict[str, Any]:
    for channel in channels:
        if isinstance(channel, dict) and channel.get("id") == wanted:
            return channel
    raise HelperError("unknown_channel", "channel %s is not in the playlist cache" % wanted)


def header_properties(headers: dict[str, Any], client: MpvIpc) -> list[tuple[str, Any]]:
    """Ordered (property, value) pairs applying the channel's HTTP headers.

    Every property is always set: a channel without headers resets
    user-agent / referrer / http-header-fields so nothing leaks from the
    previous channel.
    """
    user_agent = ""
    referrer = ""
    fields: list[str] = []
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str) or not _HEADER_NAME.match(name):
            continue
        cleaned = clean_header_value(value)
        lower = name.lower()
        if lower == "user-agent":
            user_agent = cleaned
        elif lower in ("referer", "referrer"):
            referrer = cleaned
        elif cleaned:
            fields.append("%s: %s" % (name, cleaned))
    if not user_agent:
        ok, default = client.try_command("get_property", "option-info/user-agent/default-value")
        user_agent = default if ok and isinstance(default, str) and default else MPV_DEFAULT_USER_AGENT
    return [("user-agent", user_agent), ("referrer", referrer), ("http-header-fields", fields)]


def cmd_play(args: argparse.Namespace) -> int:
    """Zap an already-running player. The wire sequence and the reply shape
    are unchanged (requirement 2); the body is `apply_channel()`, shared
    verbatim with `player start`, so first play and every later zap are one
    implementation instead of two.

    `--scope` / `--since` are additive: with either of them the zap also
    refreshes the now-playing stash inside mpv and the reply carries the new
    `entryId`, which is what makes a reattach after a shell restart name the
    channel the user actually switched to.
    """
    sock = socket_path(args.socket)
    client = MpvIpc(sock, args.ipc_timeout)
    scope = getattr(args, "scope", "") or ""
    since = int(getattr(args, "since", 0) or 0)
    session = bool(scope or since)
    try:
        target = player_target(args.id, args.url, args.cache_dir)
        client.connect()
        stash = None
        if session:
            # D-PLY-11 / the plan's step 2: the seq used to be a hardcoded 0,
            # so the two sides could only be seen to DIFFER, never compared.
            # It is read from the lock record rather than from a `--seq` of
            # this verb's own, because ruling CL4 forbids giving `play` a
            # sequence number (and the lock that would come with it) until
            # refusals are routed. The lock record is a plain file read: no
            # flock, nothing to block on, nothing that can answer `busy`.
            stash = player_stash(target["id"], target["name"], target["group"], scope,
                                 source_key_of(cache_dir(args.cache_dir)), since or int(time.time()),
                                 record_seq(read_lock_file(sock)), verb="play")
        entry_id = apply_channel(client, target, stash=stash, label="play")
        payload: dict[str, Any] = {"ok": True, "kind": "play", "id": args.id or None, "name": target["name"]}
        if session:
            # Additive, and tied to the additive flags: without --scope /
            # --since the reply is byte-identical to v0.2.1's.
            payload["entryId"] = entry_id
        emit(payload)
        return EXIT_OK
    except HelperError as error:
        log("play: %s" % error.message)
        emit(error_payload("play", error, id=args.id or None))
        return EXIT_ERROR
    finally:
        client.close()


def cmd_stop(args: argparse.Namespace) -> int:
    client = MpvIpc(socket_path(args.socket), args.ipc_timeout)
    try:
        client.connect()
        reply = client.request(["quit"], allow_close=True)
        if reply.get("error") != "success":
            raise HelperError("ipc_error", "mpv refused quit: %s" % reply.get("error"))
        emit({"ok": True, "kind": "stop"})
        return EXIT_OK
    except HelperError as error:
        log("stop: %s" % error.message)
        emit(error_payload("stop", error))
        return EXIT_ERROR
    finally:
        client.close()


def unlink_stale_socket(path: str) -> bool:
    try:
        if stat.S_ISSOCK(os.lstat(path).st_mode):
            os.unlink(path)
            return True
    except OSError:
        pass
    return False


def cmd_status(args: argparse.Namespace) -> int:
    path = socket_path(args.socket)
    client = MpvIpc(path, args.ipc_timeout)
    try:
        try:
            client.connect()
        except HelperError as error:
            if client.refused and unlink_stale_socket(path):
                log("status: removed stale socket file")
            raise
        values: dict[str, Any] = {}
        for prop in ("media-title", "path", "pause", "idle-active", "mpv-version", USER_DATA_STASH):
            ok, data = client.try_command("get_property", prop)
            values[prop] = data if ok else None
        path_value = values["path"]
        stash = values[USER_DATA_STASH] if isinstance(values[USER_DATA_STASH], dict) else None
        emit({
            "ok": True,
            "kind": "status",
            "running": True,
            # The player's media-title is the channel name the helper set
            # through --force-media-title: provider text. It reaches stdout,
            # which is a sink (rule 5), so it is redacted like every other
            # provider string -- it had gone out verbatim since M2-02 and no
            # consumer in the shell reads it (F-SINK-12, from the review).
            "mediaTitle": redact_urls(values["media-title"]) if isinstance(values["media-title"], str) else None,
            "pathHost": (url_host(path_value) or ("local file" if path_value.startswith("/") else "")) if isinstance(path_value, str) and path_value else None,
            "paused": bool(values["pause"]) if values["pause"] is not None else None,
            "idle": bool(values["idle-active"]) if values["idle-active"] is not None else None,
            "mpvVersion": values["mpv-version"] if isinstance(values["mpv-version"], str) else None,
            # The reconciliation input ARCHITECTURE-PLAYER.md (dev branch) 271-273
            # specified and the code never grew: the health tick already asks
            # the player a question every few seconds, and until now the one
            # thing it never asked was WHICH CHANNEL. Never a URL - the record
            # carries the channel id, the name and the scope and nothing else.
            "stash": stash,
            # M5-01: the rewind readout rides the tick the service already
            # runs, so "behind live" re-syncs every ten seconds with no new
            # process. Null until the player has a position (design 2.2).
            "rewind": read_rewind(client, stash, paused=bool(values["pause"]) if values["pause"] is not None else None),
        })
        return EXIT_OK
    except HelperError as error:
        # `running` keeps its socket-answered meaning (Model.statusHealthy and
        # the 23 test_mpv.py (dev branch tests) cases depend on it). `process` is additive
        # and says whether the player is gone or merely wedged, so the health
        # verdict does not need a second call (4.13).
        found = find_player(path)
        log("status: %s" % error.message)
        emit(error_payload("status", error, running=False,
                           process={"found": bool(found), "pid": int(found[0]["pid"]) if found else None}))
        return EXIT_ERROR
    finally:
        client.close()


