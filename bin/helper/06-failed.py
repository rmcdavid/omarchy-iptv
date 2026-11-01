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
            # D-SRC-45's sibling (rule 15): this raise reached main's
            # catch-all, so a missing id answered `code: internal` with
            # "HelperError:" in front of it and a traceback. Answered here,
            # with its own code, as every other refusal of this verb would be.
            error = HelperError("bad_id", "A channel id is required to mark a channel.")
            log("failed: %s" % error.message)
            emit(error_payload("failed", error, action=args.action))
            return EXIT_ERROR
        rows = [r for r in rows if r["id"] != cid]
        rows.insert(0, {"id": cid, "at": now})
    elif args.action == "clear":
        cid = (args.id or "").strip()
        rows = [] if not cid else [r for r in rows if r["id"] != cid]
    # `list` falls through: pruning and emitting is the whole of it.
    rows = prune_failed(rows, now, known_channel_ids(directory))
    if args.action in ("mark", "clear"):
        # D-SRC-72: the marks' file refused with the playlist verb's code
        # (cache_unwritable, D-SRC-69) when it cannot be written, as every
        # other refusal of this verb is answered here, never left to
        # main()'s `internal`. Nothing on screen reads this reply (the
        # service fires and forgets, Service.persistFailed); the shell's
        # in-memory mark stands for the session either way. A folder that is
        # a link to nothing stays R25c's `folder_unusable`.
        path = os.path.join(directory, FAILED_FILE)
        try:
            ensure_private_dir(directory)
            write_json_atomic(path, {"version": 1, "failed": rows})
        except FolderUnusable:
            raise
        except OSError as io_error:
            error = cache_unwritable(path, io_error)
            log("failed: %s" % error.message)
            emit(error_payload("failed", error, action=args.action))
            return EXIT_ERROR
    emit({"ok": True, "kind": "failed", "action": args.action, "count": len(rows), "failed": rows})
    return 0


# D-LOGO-16 (R30e): the most one `logos --fetch` run may spend STARTING
# downloads, in seconds. Before it the run had no wall-clock bound at all: it
# fetches one logo at a time, failed hosts are retried on every run, and
# MAX_LOGO_FILES counts files, not requests, so a playlist of unroutable logo
# hosts cost at least the 10 s connect timeout per distinct URL -- 50,000 x
# 10 s, about 5.8 days, by arithmetic. An hour is about three times the
# quarter of an hour D-LOGO-8 measured for a first enable of 1,436 logos;
# what a run leaves is fetched by the next one (the service starts one after
# every refresh), because a file already on disk is never fetched again. Each
# logo gets LOGO_DEADLINE or what is left of this, whichever is less, so the
# run stops starting fetches at this mark and ends one logo deadline after
# it at the latest. Mirrored by Model.LOGO_RUN_DEADLINE_MS through the shared
# logo-deadlines fixture; the shell's watchdog (Service.qml
# logoFetchWatchdog, Model.LOGO_FETCH_WATCHDOG_MS) sits past both.
LOGO_RUN_DEADLINE = 3600.0
# A logo's file name: fnv1a32 of its URL, eight lowercase hex digits
# (logo_filename). The ceiling's sweep removes only names of this shape.
_LOGO_NAME = re.compile(r"[0-9a-f]{8}\Z")


class LogoFolderBusy(Exception):
    """Another `logos --fetch` holds this source's logo folder (D-LOGO-18)."""


def lock_logo_dir(logo_dir: str, needed: bool) -> int | None:
    """An exclusive, non-blocking flock on the source's logo folder, held by
    the returned descriptor for the whole run (D-LOGO-18, R30b). -> None when
    there is nothing to hold: no folder and nothing this run could fetch,
    which is when it can write nothing either. Raises LogoFolderBusy when
    another run holds it.

    Two runs on one source each counted the folder at their start and could
    together pass the ceiling; the shell runs one at a time, but a run from
    a terminal beside it, or one left behind by a shell restart, did not
    know. The folder is created here when a fetch may need it (0700, as
    write_logo would), and opened through a link the way write_logo writes
    through one (D-SRC-32), so the lock is on the folder the files go to. A
    filesystem without flock answers an error other than EWOULDBLOCK; the run
    goes on unlocked then, as before, and says so. So does a run whose folder
    cannot be made or opened -- a file or a dangling link where it should be:
    it has nothing to guard, because nothing can be written there, and
    logo_dir_entries counts such a folder as full, so it fetches nothing."""
    if not needed and not os.path.isdir(logo_dir):
        return None
    try:
        ensure_private_dir(logo_dir)
        fd = os.open(logo_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except OSError as error:
        log("logos: the logo folder cannot be used (%s); nothing will be fetched" % type(error).__name__)
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise LogoFolderBusy() from None
    except OSError as error:
        log("logos: could not lock the logo folder (%s); this run is not exclusive" % type(error).__name__)
    # R32f: the folder is marked when a run STARTS as well as when it ends
    # (cmd_logos), through the descriptor, so "a day since a fetch last ran
    # for it" (README; cache_prune, age_logo_folder) is true of a run the
    # shell stopped with SIGTERM -- a source switch, the setting turned off,
    # its watchdog -- which runs no `finally`. Such a run that wrote nothing
    # kept the folder's older time and could be aged at the next prune a
    # few hours after a fetch ran in it; erring toward deleting, but the
    # sentence was stronger than the code (the round-2 recheck).
    try:
        os.utime(fd)
    except OSError:
        pass
    return fd


def present_logo_names(channels: list[Any], logo_dir: str) -> list[str]:
    """D-LOGO-23 (R32f): what a run that does NOT hold the folder's lock may
    announce -- the cached file of every logo the playlist names that passes
    the cached-file check as it stands (header within bounds, a PNG already
    canonical), each as a progress line as it is found, in channel order and
    once per URL. Read-only by construction: `canonical_logo_file` with
    `rewrite` False never writes, nothing here unlinks, and a file that fails
    the check is simply not named; the holder's run rewrites or sweeps it.
    What this cannot promise, stated: the holder may unlink a file after it
    was named here (its sweep, or its ceiling's sweep of unnamed files), and
    the guide then logs one `Cannot open` for it until the holder's own
    summary replaces the set."""
    names: list[str] = []
    seen: set[str] = set()
    for channel in channels:
        url = channel.get("logo") if isinstance(channel, dict) else None
        if not isinstance(url, str) or not url or url in seen:
            continue
        seen.add(url)
        name = logo_filename(url)
        path = os.path.join(logo_dir, name)
        if os.path.exists(path) and cached_logo_state(path, rewrite=False):
            names.append(name)
            emit({"ok": True, "kind": "logo", "name": name})
    return names


def logo_escape(escaped: BaseException, where: str) -> HelperError:
    """D-LOGO-24's backstop: an exception the logo path did not expect,
    turned into the failure of ONE logo -- `logo_fetch`, counted and
    memoised like any other -- rather than main()'s `internal`, which ended
    the whole run before the memo was saved, so the same logo ended every
    later run too. Said once on stderr by the exception's CLASS only, never
    its text, which can quote a URL (rule 5). Never called for MemoryError
    (the run's memory refusal, cmd_logos) or FolderUnusable (main()'s
    `folder_unusable`): those are the run's, not the logo's."""
    kind = type(escaped).__name__
    log("logos: %s ended in %s; counted as that logo's failure" % (where, kind))
    return HelperError("logo_fetch", "a logo %s ended in %s" % (where, kind))


def cached_logo_state(path: str, rewrite: bool = True) -> str:
    """The cached-file check for one file already on disk -- its header
    within bounds (logo_file_within_bounds), then canonical_logo_file -- and
    "" (not announced) when the check itself raises (D-LOGO-24's backstop):
    a file this cannot judge is a file the guide is never pointed at."""
    try:
        return canonical_logo_file(path, rewrite) if logo_file_within_bounds(path) else ""
    except (MemoryError, FolderUnusable):
        raise
    except Exception as escaped:
        logo_escape(escaped, "check of a cached file")
        return ""


def sweep_unnamed_logos(logo_dir: str, named: set[str]) -> int:
    """At the ceiling (D-LOGO-18, R30b): remove the logo files no channel of
    the current playlist names. -> how many. They are a cache -- a channel
    that names one again gets it fetched again -- and until this a playlist
    whose logos changed over time filled the folder with files nothing drew
    and then fetched nothing new until `cache logos-clear`. Only names of a
    logo's own shape, only regular files (never followed); anything else in
    the folder stays and still counts toward the ceiling."""
    removed = 0
    try:
        with os.scandir(logo_dir) as entries:
            for entry in entries:
                if not _LOGO_NAME.match(entry.name) or entry.name in named:
                    continue
                try:
                    if entry.is_file(follow_symlinks=False):
                        os.unlink(entry.path)
                        removed += 1
                except OSError:
                    continue
    except OSError:
        return removed
    return removed


def cmd_logos(args: argparse.Namespace) -> int:
    directory = cache_dir(args.cache_dir)
    try:
        channels = load_channels(directory)
    except HelperError as error:
        # D-SRC-45. A source with no channel list yet is not a bug: it used
        # to reach main's catch-all as `code: internal` with the exception's
        # class name in front of the sentence, and a traceback on stderr.
        # Answered here the way `play` and `epg` answer the same absence,
        # with their code and one plain sentence. The shell's fetch reads
        # this line as "no names" (Model.logoSummaryNames) and logs the exit.
        log("logos: %s" % error.message)
        emit(error_payload("logos", error, action="fetch" if args.fetch else "survey"))
        return EXIT_ERROR
    survey = logo_survey(channels)
    if not args.fetch:
        emit(dict(survey, ok=True, kind="logos", action="survey"))
        return 0
    # The fetch is opt-in twice over: the setting is off by default (the
    # ruling's first line) and this flag is off by default here, so nothing
    # contacts anyone because a command was run without reading it.
    logo_dir = os.path.join(directory, LOGO_SUBDIR)
    try:
        lock = lock_logo_dir(logo_dir, survey["wouldContact"] > 0)
    except LogoFolderBusy:
        # D-LOGO-23 (R32f): counted and said, and the names already on disk
        # that pass the cached-file check are ANNOUNCED, read-only -- so a
        # shell that restarts while a fetch is still running (the case the
        # lock exists for) draws the logos it has rather than blank rows
        # until the next run. The first version answered no `names` at all,
        # which kept the old shell's set and gave a new shell nothing.
        # `busy` stays true, so the shell's one journal line stays
        # (Model.logoSummaryNotice), and nothing is written: no rewrite of a
        # non-canonical PNG, no sweep of a file that fails the check, no
        # temporary swept, no folder marked. That is the holder's work.
        log("logos: another logo fetch is running for this source; this one fetched nothing")
        names = present_logo_names(channels, logo_dir)
        emit(dict(survey, ok=True, kind="logos", action="fetch", busy=True, fetched=0,
                  cached=len(names), names=names))
        return 0
    # D-LOGO-15 (R30e): bounded like the playlist and epg verbs (D-M3U-1),
    # before anything is fetched, and lifted before the summary is composed
    # (D-M3U-3). What a logo costs is bounded by MAX_LOGO_BYTES and the
    # headers' own limits, and no redirect body is read any more; this is
    # what holds when that arithmetic is wrong.
    held = limit_memory()
    result: dict[str, Any] | None = None
    try:
        try:
            result = fetch_logo_run(channels, logo_dir, args.timeout)
        finally:
            release_memory_limit(held)
    except MemoryError:
        result = None
    finally:
        if lock is not None:
            # The folder's modification time is when a run for this source
            # last started (lock_logo_dir) or ended, which `cache prune`
            # ages the folder by (D-LOGO-17, R30a): a run that fetched
            # nothing new still marks it. Through the descriptor, so it is
            # the folder that was locked.
            try:
                os.utime(lock)
            except OSError:
                pass
            os.close(lock)
    if result is None:
        error = memory_refusal("logo fetch", "this source", held)
        log("logos: %s" % error.message)
        emit(error_payload("logos", error, action="fetch"))
        return EXIT_ERROR
    refusal = result.pop("refusal")
    # Said ONCE on stderr as well, counted, because a ceiling that stops
    # fetches in silence reads as a provider being down; the shell, which
    # reads no stderr from this process, writes its own journal line from
    # the summary (Model.logoSummaryNotice, R30c).
    if result["atCeiling"]:
        log("logos: the logo folder holds %d files, its ceiling is %d; %s"
            % (result["files"], MAX_LOGO_FILES,
               counted_sentence(result["deferred"], "%d logo was not fetched", "%d logos were not fetched")))
    if result["runExpired"]:
        log("logos: this run reached its %d s limit; %s"
            % (int(LOGO_RUN_DEADLINE),
               counted_sentence(result["postponed"], "%d logo was left for the next run",
                                "%d logos were left for the next run")))
    limits = {"cap": MAX_LOGO_FILES, "maxBytes": MAX_LOGO_BYTES, "maxSide": MAX_LOGO_SIDE, "maxPixels": MAX_LOGO_PIXELS}
    if refusal is not None:
        # D-SRC-72: a logo or the failure memo could not be written. The
        # run's own code and sentence, never main()'s `internal` -- and the
        # summary still carries `names`, every file on disk this run
        # validated, which is the line the shell replaces its set from
        # (Model.logoSummaryNames reads `names` whatever `ok` says).
        log("logos: %s" % refusal.message)
        emit(dict(survey, **error_payload("logos", refusal, action="fetch", busy=False, **result, **limits)))
        return EXIT_ERROR
    emit(dict(survey, ok=True, kind="logos", action="fetch", busy=False, **result, **limits))
    return 0


def logo_failed_path(logo_dir: str) -> str:
    """The memo's path: beside the logo folder, in the source's own
    directory (D-LOGO-22), never inside the folder the census counts."""
    return os.path.join(os.path.dirname(logo_dir.rstrip(os.sep) or logo_dir), LOGO_FAILED_FILE)


def load_logo_failed(path: str, now: float) -> dict[str, tuple[int, str]]:
    """The memo as {name: (at, reason)}, entries older than LOGO_FAILED_TTL
    dropped, at most LOGO_FAILED_MAX of the newest kept. A name is a logo
    file name's own shape (eight hex digits, the fnv1a32 of the URL,
    logo_filename) and a reason a short code; anything else in the file
    is skipped, and a file that is not a JSON object is an empty memo.
    An `at` in the future reads as now, so a clock that stepped cannot
    make an entry immortal."""
    document = read_json(path)
    entries = document.get("failed") if isinstance(document, dict) else None
    memo: dict[str, tuple[int, str]] = {}
    if not isinstance(entries, dict):
        return memo
    for name, entry in entries.items():
        if not isinstance(name, str) or not _LOGO_NAME.match(name) or not isinstance(entry, dict):
            continue
        at = entry.get("at")
        reason = entry.get("reason")
        if isinstance(at, bool) or not isinstance(at, (int, float)) or at != at:
            continue
        at = min(int(at), int(now))
        if now - at >= LOGO_FAILED_TTL:
            continue
        if not failed_reason_ok(reason):
            reason = "failed"
        memo[name] = (at, reason)
    if len(memo) > LOGO_FAILED_MAX:
        newest = sorted(memo.items(), key=lambda item: (-item[1][0], item[0]))[:LOGO_FAILED_MAX]
        memo = dict(newest)
    return memo


def save_logo_failed(path: str, memo: dict[str, tuple[int, str]]) -> HelperError | None:
    """Write the memo atomically, 0600 in the source's 0700 directory
    (write_json_atomic). Names and codes only, never a URL (rule 5): the
    name is the hash the folder already uses, and a reason is one of the
    helper's own error codes. An empty memo removes the file.

    D-SRC-72: -> None, or the refusal when the memo cannot be written
    (cache_unwritable), which the run answers with once it has finished --
    a memo is not worth stopping the run for, and an OSError here used to
    end it in main()'s `internal` with no summary at all."""
    if not memo:
        try:
            os.unlink(path)
        except OSError:
            pass
        return None
    try:
        write_json_atomic(path, {"version": 1, "failed": {
            name: {"at": at, "reason": reason} for name, (at, reason) in sorted(memo.items())}})
    except FolderUnusable:
        raise
    except OSError as io_error:
        return cache_unwritable(path, io_error)
    return None


def failed_reason_ok(reason: Any) -> bool:
    """A memo reason is one of the helper's own error codes: ASCII, a
    lowercase letter first, letters, digits and underscores, at most 32
    (no regex: the helper's regex guard reviews every pattern, and a
    membership test over a code needs none)."""
    return (isinstance(reason, str) and 0 < len(reason) <= 32 and reason.isascii()
            and reason[0].islower() and reason.replace("_", "a").isalnum() and reason == reason.lower())


def fetch_logo_run(channels: list[Any], logo_dir: str, timeout: float) -> dict[str, Any]:
    """The run itself, under the lock and the memory limit: every cached
    logo validated and announced, every missing one fetched while the
    ceiling, the run's deadline and the failure memo allow. -> the
    summary's counts.

    D-LOGO-22, the memo (logo-failed.json beside the folder): a URL whose
    fetch failed THIS run or within the last LOGO_FAILED_TTL (a day) is
    not fetched. Without it the run walked `channels` from the top every
    time with a fresh `seen`, so a head of dead addresses -- each costing
    up to min(LOGO_DEADLINE, what was left of the run) -- ate the same
    hour of LOGO_RUN_DEADLINE every run and the live logos behind it were
    never reached; the D-LOGO-16 comment's "the next run starts where
    this one stopped" was true of files that landed and of nothing else.
    IPTV lists with hundreds of dead logo links are ordinary input. The
    memo is consulted after the on-disk check (a file on disk is announced
    whatever the memo says) and before the ceiling and the deadline, so a
    memoised address counts in `skippedFailed` and nowhere else; it is
    written when the run's deadline passes, because a run the shell
    SIGTERMs (a switch, the setting off) reaches no `finally` and would
    otherwise record nothing, and again on the way out of the walk, in a
    `finally` (D-LOGO-24), so an exception that still ends the run records
    what it learned first. Every failure is recorded alike: a timeout, a
    refusal at the gate (scheme, userinfo, redirect, type, bytes, size,
    dimensions, scans, chunks), an HTTP error, a network error, http.client's
    own errors, and anything else one logo's fetch raises (logo_escape, the
    backstop); a full memo (LOGO_FAILED_MAX) records nothing new. A
    memoised address is tried again a day later, so a host that was down
    gets another chance, and `cache logos-clear` drops the memo with the
    folder so the user's own reset is a reset."""
    # D-SRC-60: a temporary a killed write left here is swept before the
    # folder is counted, so a leftover does not hold a slot under the
    # ceiling (sweep_stale_temps; once per folder per process).
    stale = sweep_stale_temps_once(logo_dir)
    # D-LOGO-12: MAX_LOGO_FILES is a ceiling on what the logo directory
    # HOLDS, not on what one run downloads. It used to be compared with
    # `fetched` alone, which counts this run's downloads, so the directory
    # grew by up to the cap on every run (2, 4, 6, 7 over four runs with the
    # cap lowered to 2) and a MAX_CHANNELS playlist reached 50,000 files over
    # ten service starts while the comments called 5,000 a ceiling. Now a run
    # counts what is there before it starts -- every entry, whatever it is,
    # because the claim is about the directory -- and fetches only while
    # `present + fetched < MAX_LOGO_FILES`. `present` falls by one for each
    # file a sweep below unlinks, and rises with nothing else: a fetch is
    # only ever made for a name that is not on disk (or whose unlink failed,
    # which then counts twice and errs on the side of the ceiling). Since
    # D-LOGO-18 the count is also exact against other runs: this one holds
    # the folder's lock (lock_logo_dir).
    present = logo_dir_entries(logo_dir)
    run_deadline = time.monotonic() + LOGO_RUN_DEADLINE
    fetched, cached, refused, failed, swept, deferred, rewritten = 0, 0, 0, 0, 0, 0, 0
    postponed, unnamed, skipped_failed = 0, 0, 0
    unnamed_checked = False
    memo_path = logo_failed_path(logo_dir)
    memo_at = int(time.time())
    memo = load_logo_failed(memo_path, memo_at)
    memo_dirty = False
    memo_saved_at_deadline = False
    # D-SRC-72: the first write this run could not make (a logo, or the
    # memo), and how many logos it left unfetched or unkept for it.
    refusal: HelperError | None = None
    fetch_stopped = False
    unsaved = 0
    reasons: dict[str, int] = {}
    seen: set[str] = set()
    names: list[str] = []
    # D-LOGO-24: the memo is saved on EVERY way out of the walk, in a
    # `finally`. It was saved after the loop, so an exception that left the
    # loop -- any logo whose error the fetch did not map -- recorded nothing,
    # and the same logo was tried, and ended the run, every time. What can
    # still leave it now is the run's own: a memory refusal, a folder that
    # is a link to nothing, a stdout gone.
    try:
        for channel in channels:
            # The ceiling is checked BELOW the cached-file branch, not here. The
            # cap used to be the first line of this loop, as a `break`, which
            # bounded the wrong thing: in a run that fetched 5,000 new files,
            # every cached file later in channel order was neither validated nor
            # announced that run, so the guide drew blank slots for logos it
            # already had and a cached bomb past the cap was never swept (R5). A
            # review found the comment beside the sweep claiming the branch was
            # not bounded by the cap, which was true only while fetched < 5000.
            url = channel.get("logo") if isinstance(channel, dict) else None
            # `seen` is the run's memory of every URL it has looked at, failed
            # ones included (D-LOGO-22, R32f): a URL two channels name is
            # fetched once a run. Across runs the memo below is the memory
            # (logo-failed.json, a day): a failed address is not tried again
            # until its entry expires.
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
                # isolation, 37 us on 44 KB files). This branch is not held back
                # by the ceiling below, at any count, nor by the run's deadline:
                # it reads files already on disk, and since D-LOGO-12 the ceiling
                # bounds what is on disk, so this validates at most MAX_LOGO_FILES
                # files per run -- unless an earlier version left more, which this
                # run validates too and never adds to.
                # D-LOGO-13: a PNG is announced only in its canonical form, so a
                # file an earlier version cached verbatim is rewritten in place
                # first, and one whose chunks cannot be walked is swept below.
                state = cached_logo_state(path)
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
                    present -= 1
                except OSError:
                    pass
            if name in memo:
                # D-LOGO-22: failed within the day (this run included, through
                # the entry a failure below adds). Not fetched, not a failure
                # again, not held back by the ceiling or the deadline.
                skipped_failed += 1
                continue
            if fetch_stopped:
                # D-SRC-72: a logo could not be written into this folder, and
                # every later one goes to the same folder -- so nothing more is
                # FETCHED: a logo the run cannot keep is a request to its host
                # for nothing. The pass goes on, because a cached file further
                # down is still validated and announced (the lesson of the
                # ceiling's old `break`, above).
                unsaved += 1
                continue
            if present + fetched >= MAX_LOGO_FILES and not unnamed_checked:
                # D-LOGO-18 (R30b): at the ceiling, before a URL is counted as
                # held back, the files no current channel names are swept, once a
                # run. Named from every channel, not only the ones this loop has
                # reached, so a file a later channel names is kept.
                unnamed_checked = True
                named = {logo_filename(c["logo"]) for c in channels
                         if isinstance(c, dict) and isinstance(c.get("logo"), str) and c["logo"]}
                gone = sweep_unnamed_logos(logo_dir, named)
                unnamed += gone
                present -= gone
            if present + fetched >= MAX_LOGO_FILES:
                # The CEILING (D-LOGO-12): the directory holds MAX_LOGO_FILES
                # entries and no fetch may add one. A cached file was validated
                # and announced above whatever the count; a URL that would need a
                # new file is not fetched and is counted here rather than
                # vanishing, so a run that stopped at the ceiling says so (the
                # same reason `swept` is a number). A swept bomb stays off the
                # disk and off the stream, and is refused at the gate on the run
                # that has room to fetch it.
                deferred += 1
                continue
            remaining = run_deadline - time.monotonic()
            if remaining <= 0:
                # D-LOGO-16: the run's own deadline. Counted, never fetched; the
                # next run starts where this one stopped, because what it fetched
                # is on disk and what failed is in the memo -- written HERE, once,
                # the first time the deadline is seen past (D-LOGO-22): the shell
                # may stop this run before its end.
                if memo_dirty and not memo_saved_at_deadline:
                    memo_saved_at_deadline = True
                    memo_refusal = save_logo_failed(memo_path, memo)
                    refusal = refusal or memo_refusal
                postponed += 1
                continue
            try:
                data, ctype = fetch_logo(url, timeout, min(LOGO_DEADLINE, remaining))
                landed = write_logo(logo_dir, url, data, ctype)
            except HelperError as caught:
                failure = caught
            except (MemoryError, FolderUnusable):
                raise
            except Exception as escaped:
                # D-LOGO-24: the backstop. read_logo_response maps every error
                # the fetch is known to raise; anything else costs this logo
                # alone, as a counted, memoised `logo_fetch`, never the run.
                failure = logo_escape(escaped, "fetch")
            else:
                names.append(landed)
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
                emit({"ok": True, "kind": "logo", "name": landed})
                continue
            if failure.code == "cache_unwritable":
                # D-SRC-72 (write_logo): this folder's failure, not the
                # address's -- not counted as one, not remembered in the
                # memo, and the fetching stops here (above).
                refusal = failure
                fetch_stopped = True
                unsaved += 1
                continue
            # Hosts and codes only, never the URL (rule 5).
            reasons[failure.code] = reasons.get(failure.code, 0) + 1
            # D-SINK-40: `local_address` is the policy's too -- a logo, or a
            # hop of one, aimed at this machine or a local network.
            if failure.code in ("logo_scheme", "logo_userinfo", "logo_redirect",
                                "logo_type", "logo_bytes", "logo_too_large",
                                "logo_dimensions", "logo_scans", "logo_chunks", "local_address"):
                refused += 1
            else:
                failed += 1
            # D-LOGO-22: remembered by name and code, for a day. A full memo
            # records nothing new; an entry already there is refreshed.
            if name in memo or len(memo) < LOGO_FAILED_MAX:
                memo[name] = (memo_at, failure.code)
                memo_dirty = True
    finally:
        if memo_dirty:
            memo_refusal = save_logo_failed(memo_path, memo)
            refusal = refusal or memo_refusal
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
    # `rewritten` counts the cached PNGs made canonical this run (D-LOGO-13);
    # they are in `cached` too, and a file that could not be is in `swept`.
    # `deferred` is the number of logos the ceiling held back from a fetch
    # (D-LOGO-12) -- the cached-file branch above is never held back, so a
    # cached logo past the ceiling is in `names` and a cached bomb past it is
    # in `swept` -- `atCeiling` says the run stopped there, and `files` is
    # what the directory holds by this run's own count -- never more than
    # `cap` unless an earlier version left it fuller, which this version
    # never grows further. `unnamed` is how many files the ceiling's sweep
    # removed because no channel names them (D-LOGO-18). `postponed` is how
    # many logos the run's deadline left for the next run, and `runExpired`
    # says it was reached (D-LOGO-16); a logo whose own deadline passed is a
    # failure, reason `logo_timeout`. `staleTemps` is how many leftovers of a
    # killed write were swept (D-SRC-60). `skippedFailed` is how many
    # addresses the failure memo kept this run from trying (D-LOGO-22).
    # `unsaved` is how many logos a write this folder refused left unkept or
    # unfetched (D-SRC-72); `refusal` is that write's refusal, or the memo's,
    # which cmd_logos answers with -- and takes out of the summary.
    return {"fetched": fetched, "cached": cached, "refusedOnPolicy": refused, "failed": failed,
            "reasons": reasons, "names": names, "swept": swept, "rewritten": rewritten,
            "deferred": deferred, "atCeiling": deferred > 0, "files": present + fetched,
            "unnamed": unnamed, "postponed": postponed, "runExpired": postponed > 0,
            "staleTemps": stale, "skippedFailed": skipped_failed, "unsaved": unsaved, "refusal": refusal}


def logo_dir_entries(logo_dir: str) -> int:
    """How many entries the logo directory holds, of any kind (D-LOGO-12).

    Every name counts -- a logo, a `.tmp-` file a killed write left behind, a
    stray directory -- because the ceiling is a claim about the directory and
    not about the files this run recognises. Followed, not lstat-ed: a link
    at this path to a folder is where `write_logo` writes (ensure_private_dir
    follows it, D-SRC-32), so that folder is the one counted. A directory
    that is not there holds nothing; one that cannot be listed counts as
    full, so a run that cannot see what is there fetches nothing rather than
    growing it blind.
    """
    try:
        return len(os.listdir(logo_dir))
    except FileNotFoundError:
        return 0
    except OSError:
        return MAX_LOGO_FILES


def read_channel_document(directory: str) -> dict[str, Any]:
    """channels.json whole: the channel list and what the parse recorded
    about its playlist (player_target's cached_source reads that half)."""
    document = read_json(os.path.join(directory, CHANNELS_FILE))
    if not isinstance(document, dict) or not isinstance(document.get("channels"), list):
        raise HelperError("no_cache", "This source has no channel list yet; refresh the playlist first.")
    return document


def load_channels(directory: str) -> list[dict[str, Any]]:
    return read_channel_document(directory)["channels"]


def find_channel(channels: list[dict[str, Any]], wanted: str) -> dict[str, Any]:
    for channel in channels:
        if isinstance(channel, dict) and channel.get("id") == wanted:
            return channel
    raise HelperError("unknown_channel", "channel %s is not in the playlist cache" % wanted)


def header_values(headers: dict[str, Any]) -> tuple[str, str, list[str]]:
    """A channel's headers as (user-agent, referrer, the other header lines),
    "" / "" / [] where the channel has none. Names are held to the WHOLE of
    _HEADER_NAME (fullmatch, as make_channel's: a cached `Cookie\n` is no
    name) and values lose their line breaks, so nothing here can add a
    header line of its own.

    Since 2026-10-29 these ride the `loadfile` as PER-FILE options
    (channel_load_options, 08), not global properties: an entry the helper did
    not load -- a nested playlist's entry, a paste, a drop -- never inherits
    them. Requirement 7 (a channel without headers sends none of the previous
    one's) now holds by construction, because mpv restores a per-file option
    when its file ends."""
    user_agent = ""
    referrer = ""
    fields: list[str] = []
    for name, value in headers.items():
        if not isinstance(name, str) or not isinstance(value, str) or not _HEADER_NAME.fullmatch(name):
            continue
        cleaned = clean_header_value(value)
        lower = name.lower()
        if lower == "user-agent":
            user_agent = cleaned
        elif lower in ("referer", "referrer"):
            referrer = cleaned
        elif cleaned:
            fields.append("%s: %s" % (name, cleaned))
    return user_agent, referrer, fields


def default_user_agent(client: MpvIpc) -> str:
    """mpv's own default user agent (`option-info/user-agent/default-value`),
    or MPV_DEFAULT_USER_AGENT when the player cannot say."""
    ok, default = client.try_command("get_property", "option-info/user-agent/default-value")
    return default if ok and isinstance(default, str) and default else MPV_DEFAULT_USER_AGENT


def neutral_header_properties(user_agent: str) -> list[tuple[str, Any]]:
    """The three GLOBAL header properties at values that belong to no
    provider: mpv's default user agent, no referrer, no extra fields. Set
    before every load (apply_channel) and on adoption (pin_adopted_player),
    because a player started or last driven by a helper from before
    2026-10-29 holds the previous channel's headers as GLOBALS, and an entry
    nobody gated would be sent them. `user_agent` is default_user_agent's."""
    return [("user-agent", user_agent), ("referrer", ""), ("http-header-fields", [])]


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


