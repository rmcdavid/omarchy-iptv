# A part of bin/omarchy-iptv (D-REL-7), not a module: the helper compiles
# this file into its own namespace in the order its HELPER_PARTS lists, so
# a part sees every name the parts before it define. Run the helper.
from __future__ import annotations
# --------------------------------------------------------------- cache
# Per-source cache directories (ARCHITECTURE-SOURCES.md section 2.3). QML
# never composes a delete: the service asks for `cache migrate | remove |
# prune` with keys only. Every key is validated against SOURCE_KEY_RE, the
# target is realpath-checked to stay under <cache-dir>/sources/, symlinked
# directories are refused, and only the five known file names plus .tmp-*
# leftovers are ever unlinked (an unknown file keeps its directory). Output
# names keys and base names only, never a path (R12).

def sources_root(directory: str) -> str:
    return os.path.join(directory, SOURCES_DIR)


def check_source_key(key: Any) -> str:
    if not isinstance(key, str) or not SOURCE_KEY_RE.match(key):
        raise HelperError("bad_key", "invalid cache key")
    return key


def source_dir(directory: str, key: Any) -> str:
    """Validated <cache-dir>/sources/<key>; raises bad_key for anything that
    is not a key, escapes the sources directory, or is a symlink."""
    key = check_source_key(key)
    root = sources_root(directory)
    target = os.path.join(root, key)
    if not os.path.realpath(target).startswith(os.path.realpath(root) + os.sep):
        raise HelperError("bad_key", "cache key escapes the sources directory")
    if os.path.islink(target):
        raise HelperError("bad_key", "cache key is a symbolic link")
    return target


def is_temp_name(name: str) -> bool:
    return name.startswith(TEMP_PREFIX)


def remove_regular(path: str) -> bool:
    """Unlink a regular file or a symlink (never following it); False when
    the name is a directory or missing."""
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError:
        return False
    if stat.S_ISDIR(mode):
        return False
    os.unlink(path)
    return True


# Subdirectories this plugin creates inside sources/<key>/ and is therefore
# responsible for deleting. M2-04's `logos/` is the first one that has ever
# existed, and it exposed that clear_source_dir could not remove a directory
# at all: remove_regular returns False for one, so it always landed in `kept`,
# the `if not kept` rmdir never fired, and `cache prune` classified the whole
# source key as kept rather than removed. A removed source left its whole logo
# directory on disk permanently, and no later prune could ever collect it --
# with filenames that are fnv1a32 of the logo URLs, so the leftovers identify
# the channels that source carried (D-LOGO-4). That directory holds at most
# MAX_LOGO_FILES entries of at most MAX_LOGO_BYTES each, 1.22 GiB, since
# D-LOGO-12 made the cap a ceiling on what is there; before it, the cap
# bounded one run's downloads and the directory had no ceiling at all. A
# kept source's folder is aged by `cache prune` since D-LOGO-17 (see
# cache_prune for the install-wide figure).
CACHE_SUBDIRS = (LOGO_SUBDIR,)
# D-LOGO-17 (the lead's ruling of 2026-10-24, K = 2): how many kept,
# non-active sources keep their logo folder past a prune whatever its age
# -- the two most recently fetched for -- so the install holds at most
# 1 + LOGO_KEPT_FOLDERS folders after every start and switch. The day rule
# still ages those two; this is the bound on the count, which the day
# rule alone never gave (fifty sources switched through in a day kept
# fifty folders). cache_prune states the figures.
LOGO_KEPT_FOLDERS = 2
# The age that makes age_logo_folder remove a folder whatever its mtime,
# a future one included: no `now - mtime` is below it.
LOGO_AGE_ANY = float("-inf")


def remove_cache_subdir(path: str) -> bool:
    """Delete one of OUR cache subdirectories. False when it is not there.

    Deliberately not shutil.rmtree and deliberately not recursive: this
    removes names one level down and then the directory itself, so a nested
    directory is LEFT and reported rather than descended into, and the rmdir
    then fails and returns False. A symlink is unlinked, never followed, so
    whatever it points at is untouched. A cache cleaner that recurses is one
    bug away from deleting something it does not own.

    (This paragraph used to say a symlink INSIDE was LEFT. It is not --
    remove_regular unlinks it, as its own docstring says. The load-bearing
    guarantee, never followed, was always true of the entries; the wording was
    not, and cache_logos_clear was written against it.)

    D-LOGO-10: the directory ITSELF being a symlink was a different matter and
    was not guarded at all. os.listdir follows it, so every caller -- `cache
    remove` and `cache prune` since D-LOGO-4 shipped this function, and
    `cache logos-clear` the moment it was written against it -- deleted the
    contents of whatever it pointed at. source_dir has refused a symlinked KEY
    directory since the beginning; the guard simply never reached one level
    down to the subdirectory.

    The first fix for that was `if os.path.islink(path): return False`, and it
    was not enough. A check on a NAME followed by an operation on the same NAME
    is two different resolutions of that name, and anything that swaps the
    directory for a link in between gets the deletion to follow it anyway --
    demonstrated, with the payload still reporting `removed: false` while two
    files outside the cache went. So nothing here re-walks a path:

      * `O_DIRECTORY | O_NOFOLLOW` refuses a symlink AT OPEN, atomically, and
        yields a handle on the inode that was checked;
      * every lstat and every unlink is `dir_fd=` relative to that handle, so
        they cannot be redirected by anything that happens to the name after;
      * the final rmdir is relative to a handle on the PARENT, opened the same
        way, so the empty-directory removal cannot be redirected either.

    The residual is a same-uid race on a 0700 directory, where the attacker
    already has every one of the user's own rights; this closes it regardless
    because deletion code should not be the place we reason about how much
    access is enough. A link is reported as removing nothing rather than as an
    error, because the caller is a queued background job and the safe answer is
    to leave a thing we do not own alone.
    """
    trimmed = path.rstrip(os.sep) or path
    parent, name = os.path.split(trimmed)
    if not name or name in (os.curdir, os.pardir):
        return False
    try:
        parent_fd = os.open(parent or os.curdir, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return False
    try:
        try:
            # O_NOFOLLOW makes a symlinked directory raise ELOOP here rather
            # than resolving, which is the whole D-LOGO-10 guarantee.
            fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        except OSError:
            return False
        try:
            entries = sorted(os.listdir(fd))
            for entry in entries:
                try:
                    mode = os.lstat(entry, dir_fd=fd).st_mode
                except FileNotFoundError:
                    continue
                if stat.S_ISDIR(mode):
                    continue
                os.unlink(entry, dir_fd=fd)
        finally:
            os.close(fd)
        try:
            os.rmdir(name, dir_fd=parent_fd)
        except OSError:
            return False
        return True
    finally:
        os.close(parent_fd)


def clear_source_dir(path: str) -> tuple[list[str], list[str]]:
    """Delete the known cache files inside `path` and rmdir it when nothing
    else is left. -> (removed names, kept names)."""
    removed: list[str] = []
    kept: list[str] = []
    try:
        names = sorted(os.listdir(path))
    except FileNotFoundError:
        return removed, kept
    for name in names:
        full = os.path.join(path, name)
        if name in CACHE_SUBDIRS and remove_cache_subdir(full):
            removed.append(name)
        elif (name in CACHE_FILES or is_temp_name(name)) and remove_regular(full):
            removed.append(name)
        else:
            kept.append(name)
    if not kept:
        os.rmdir(path)
    return removed, kept


def cache_migrate(directory: str, key: str | None) -> dict[str, Any]:
    """Move the 0.1 single-cache files into sources/<key>/ (os.replace, same
    filesystem, atomic); without a key they are deleted. Idempotent."""
    ensure_private_dir(directory)
    ensure_private_dir(sources_root(directory))
    target = source_dir(directory, key) if key else None
    if target is not None:
        ensure_private_dir(target)
    moved: list[str] = []
    removed: list[str] = []
    for name in CACHE_FILES:
        legacy = os.path.join(directory, name)
        try:
            mode = os.lstat(legacy).st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISDIR(mode):
            continue
        if target is None or os.path.lexists(os.path.join(target, name)):
            os.unlink(legacy)
            removed.append(name)
        else:
            os.replace(legacy, os.path.join(target, name))
            moved.append(name)
    for name in sorted(os.listdir(directory)):
        if is_temp_name(name) and remove_regular(os.path.join(directory, name)):
            removed.append(name)
    return {"key": key or "", "moved": moved, "removed": removed}


def cache_remove(directory: str, key: str) -> dict[str, Any]:
    removed, kept = clear_source_dir(source_dir(directory, key))
    return {"key": key, "removed": removed, "kept": kept}


def cache_epg_clear(directory: str, key: str) -> dict[str, Any]:
    """Delete one source's EPG files, keeping the source itself (M2-09 GS11).

    Removing a source deletes its whole cache directory; clearing that
    source's guide URL has to do the same for the part of the cache the URL
    produced, or the warnings it raised come back after the next restart for
    a guide source the user has removed. The playlist half of the cache is
    untouched -- the source is still there, only its guide data is gone -- and
    so is the directory, which the source still owns. Idempotent: clearing a
    URL that was never set removes nothing and still succeeds."""
    path = source_dir(directory, key)
    removed: list[str] = []
    for name in EPG_CACHE_FILES:
        if remove_regular(os.path.join(path, name)):
            removed.append(name)
    return {"key": key, "removed": sorted(removed)}


def subdir_census(path: str) -> tuple[int, int, int]:
    """(regular files, bytes, other entries) one level inside `path`.

    Measured with lstat and never followed: a symlink counts as an `other`
    and contributes no bytes, so a link to a 4 GB file cannot be reported as
    space this verb freed. Missing directory is (0, 0, 0), which is what
    makes logos-clear idempotent rather than an error.
    """
    files = 0
    size = 0
    other = 0
    # D-LOGO-10. Opened the same way removal opens it, for the same reason:
    # O_NOFOLLOW refuses a symlinked directory atomically, and measuring
    # through one would report bytes that were not freed and cannot be.
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError:
        return (0, 0, 0)
    try:
        try:
            names = sorted(os.listdir(fd))
        except OSError:
            return (0, 0, 0)
        for name in names:
            try:
                st = os.lstat(name, dir_fd=fd)
            except FileNotFoundError:
                continue
            if stat.S_ISREG(st.st_mode):
                files += 1
                size += st.st_size
            else:
                other += 1
        return (files, size, other)
    finally:
        os.close(fd)


def cache_logos_clear(directory: str, key: str) -> dict[str, Any]:
    """Delete one source's logo cache, keeping the source itself (D-LOGO-9).

    The twin of cache_epg_clear, and filed for the same reason GS11 gave for
    that one: the part of the cache an input produced has to be reclaimable
    when the user withdraws the input. Turning showLogos off stops the fetch
    and blanks the rows, and until this verb existed it reclaimed nothing,
    because prune only clears keys that are NOT kept.

    What it reclaims, as a ceiling that holds (D-LOGO-12): a fetch adds a
    file only while the directory holds fewer than MAX_LOGO_FILES entries,
    so one source's logos are at most 5,000 files of at most 256 KiB,
    1,310,720,000 bytes (1.22 GiB). An earlier version could leave a
    directory fuller than that -- its cap counted one run's downloads, and
    the directory grew by up to 5,000 a run -- and this version never adds to
    one; this verb is what empties it. The ceiling is PER SOURCE: the history
    keeps up to MAX_SOURCES (50) sources, each with its own directory. What
    bounds them together is `cache prune`, which since D-LOGO-17 (R30a)
    removes the logo folder of a kept source that is not active once no
    fetch has ended in it for a day, and since the count cap keeps at most
    LOGO_KEPT_FOLDERS such folders at all; cache_prune states the figure.

    The playlist half of the cache is untouched: the source is still there,
    only its pictures are gone. Deletion is remove_cache_subdir's, so it is
    one level deep and non-recursive by construction: a nested directory is
    left, counted in `kept`, and makes `removed` false; a symlink is unlinked
    without being followed, so its target survives and contributes no bytes.
    `files` and `bytes` count regular files only.

    Idempotent: clearing logos that were never fetched removes nothing and
    still succeeds.

    The payload carries COUNTS, never names. A logo filename is the fnv1a32
    of its URL, so the listing cache_epg_clear can safely emit would here
    re-identify the channels the user just stopped consenting to fetch -- the
    exposure D-LOGO-4 found in the leftovers themselves, which there is no
    reason to recreate on stdout (rule 5).
    """
    source = source_dir(directory, key)
    path = os.path.join(source, LOGO_SUBDIR)
    before = subdir_census(path)
    removed = remove_cache_subdir(path)
    after = subdir_census(path)
    # D-LOGO-22: the failure memo goes with the folder, so the user's reset
    # is a reset -- every address, the ones that failed included, is tried
    # again by the next fetch. Not counted: it is no logo.
    remove_regular(os.path.join(source, LOGO_FAILED_FILE))
    # `files` and `bytes` are the BEFORE counts, not before-minus-after, and
    # deliberately so: remove_cache_subdir unlinks every regular entry or
    # raises, so after[0] and after[1] are always zero and a subtraction is a
    # difference no test can ever make differ. The second census is still
    # taken, for `kept` -- the entries that are genuinely still there, which
    # is the number that can vary.
    return {
        "key": key,
        "removed": removed,
        "files": before[0],
        "bytes": before[1],
        "kept": after[0] + after[2],
    }


def age_logo_folder(source_path: str, now: float, max_age: float) -> str:
    """D-LOGO-17 (R30a): remove a kept, non-active source's logo folder once
    no fetch run has started or ended in it for `max_age` seconds.
    -> "aged" when removed, "busy" when a run holds it, "" otherwise.

    The folder's own modification time is the clock: every `logos --fetch`
    run marks it when it starts (lock_logo_dir) and when it ends
    (cmd_logos), a run that fetched nothing new included, and runs happen
    only for the ACTIVE source with logos on -- from the shell; a run from a
    terminal can name any source. So a folder older than `max_age` belongs
    to a source nobody has had logos for in that long. lstat, never
    followed: a link at logos/ is left alone, as remove_cache_subdir would
    leave it. The removal is that function's, one level deep, so a nested
    directory keeps the folder and answers "".

    D-LOGO-21 (R32f): the removal happens under the same exclusive flock a
    run holds for its length (lock_logo_dir), taken non-blocking on a
    descriptor opened O_NOFOLLOW; a folder another run holds is skipped and
    answered "busy", so a `logos --fetch` run from a terminal on a
    non-active source cannot lose its folder mid-run and then recreate an
    unlocked, uncounted one with write_logo. The descriptor is held across
    the removal and closed after it. A filesystem without flock answers an
    error other than EWOULDBLOCK; the folder is then aged unlocked, as
    before. The start mark makes a held folder young in every case the
    shell can make (a run lasts at most LOGO_FETCH_WATCHDOG_MS); the lock is
    what holds when the clock does not."""
    path = os.path.join(source_path, LOGO_SUBDIR)
    try:
        st = os.lstat(path)
    except OSError:
        return ""
    if not stat.S_ISDIR(st.st_mode) or now - st.st_mtime < max_age:
        return ""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        return ""
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return "busy"
        except OSError:
            pass
        return "aged" if remove_cache_subdir(path) else ""
    finally:
        os.close(fd)


def logo_folder_mtime(source_path: str) -> float | None:
    """The modification time of a source's logo folder, the clock
    age_logo_folder reads (lstat, never followed; a link or a file at
    logos/ is no folder). None when there is none."""
    try:
        st = os.lstat(os.path.join(source_path, LOGO_SUBDIR))
    except OSError:
        return None
    return st.st_mtime if stat.S_ISDIR(st.st_mode) else None


def cache_prune(directory: str, keep: list[str], active: str | None, epg_max_age: float) -> dict[str, Any]:
    """Delete every sources/<key> not in `keep`; age the EPG files AND the
    logo folder (D-LOGO-17, age_logo_folder) of kept, non-active keys older
    than `epg_max_age` seconds; remove the logo folder of every kept,
    non-active key but the LOGO_KEPT_FOLDERS most recently fetched for,
    whatever its age; and sweep the leftovers of killed writes there
    (D-SRC-60, sweep_stale_temps). The `active` key is implicitly kept
    (D-SRC-07): the active source's directory is never removed or touched,
    listed under `keep` or not. Names that are not keys (and symlinks) are
    skipped, never touched.

    What that bounds, install-wide (R30a; D-LOGO-20, R32f; the count cap,
    2026-10-24): the service runs this once at every start AND at every
    source switch (Service.qml schedulePrune / queuePrune), with the active
    source and the history's keys. Each source's logo folder holds at most
    MAX_LOGO_FILES x MAX_LOGO_BYTES (1,310,720,000 bytes, 1.22 GiB,
    D-LOGO-12); a folder is only ever written by a run for the ACTIVE
    source (from the shell), and leaving a source is a switch, which runs
    this. So after any start or switch the install holds the active
    source's folder and at most LOGO_KEPT_FOLDERS (2) others -- the kept
    sources whose folder was most recently marked by a fetch run, ranked by
    that mark, the clock age_logo_folder reads -- and those two only while
    their mark is younger than `epg_max_age` (a day, DEFAULT_EPG_MAX_AGE):
    **1.22 GiB x (1 + 2), 3.66 GiB**, at every moment of a session and not
    only after a restart. Before the count cap the figure was 1.22 GiB x
    (1 + the sources given logos in the day before the last start or
    switch), and MAX_SOURCES (50) times 1.22 GiB, 65.5 GB, was reachable by
    switching through all fifty with logos on inside one day; now the
    third-most-recent folder is removed at the switch that makes it third,
    whatever its age. The cost, by the ruling: a user rotating through four
    sources with logos on re-fetches one source's logos at each switch
    that cycles back, which contacts that source's logo hosts again (the
    disclosure R5 bounds), where the day rule alone re-fetched only after a
    day away. UNVERIFIED at size; arithmetic over this code. A folder a run
    holds (its flock) is skipped, answered in `busyLogos` and said once on
    stderr (D-LOGO-21); it occupies one of the two kept slots when its mark
    ranks it there, and is left for the next prune when it does not.

    What this does NOT age, stated beside the bound (rule 15, the same
    shape -- a per-source cap times MAX_SOURCES, never aged): a kept
    source's channels.json, at most MAX_SOURCE_BYTES (64 MiB) each, so up
    to 50 x 64 MiB = 3.2 GB across the history by arithmetic. Deliberate: a
    kept source switches back without a fetch (the SR rulings), and the
    list is what makes it a source; only `cache remove` takes it."""
    keep_set = {check_source_key(item) for item in keep}
    if active:
        keep_set.add(check_source_key(active))
    root = sources_root(directory)
    ensure_private_dir(root)
    removed: list[str] = []
    aged: list[str] = []
    aged_logos: list[str] = []
    busy_logos: list[str] = []
    stale = 0
    skipped: list[str] = []
    kept_dirs: list[str] = []
    kept_entries: list[Any] = []
    now = time.time()
    for entry in sorted(os.scandir(root), key=lambda item: item.name):
        name = entry.name
        if not SOURCE_KEY_RE.match(name) or entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
            skipped.append(name)
            continue
        if name not in keep_set:
            _, kept = clear_source_dir(entry.path)
            (kept_dirs if kept else removed).append(name)
            continue
        if name == active:
            continue
        kept_entries.append(entry)
    # The count cap: the LOGO_KEPT_FOLDERS most recently marked folders keep
    # the day rule; every other kept, non-active folder is aged whatever
    # its mark. Ranked by the mark alone, the newest first; two equal marks
    # rank by name, so the choice is a function of the tree and not of
    # scandir's order.
    marked = sorted(((mtime, entry.name) for entry in kept_entries
                     if (mtime := logo_folder_mtime(entry.path)) is not None),
                    key=lambda item: (-item[0], item[1]))
    recent = {name for _, name in marked[:LOGO_KEPT_FOLDERS]}
    for entry in kept_entries:
        name = entry.name
        touched = False
        for file_name in EPG_CACHE_FILES:
            path = os.path.join(entry.path, file_name)
            try:
                st = os.lstat(path)
            except FileNotFoundError:
                continue
            if stat.S_ISREG(st.st_mode) and now - st.st_mtime >= epg_max_age:
                os.unlink(path)
                touched = True
        if touched:
            aged.append(name)
        verdict = age_logo_folder(entry.path, now, epg_max_age if name in recent else LOGO_AGE_ANY)
        if verdict == "aged":
            aged_logos.append(name)
        elif verdict == "busy":
            busy_logos.append(name)
        stale += sweep_stale_temps(entry.path, now=now)
        logo_path = os.path.join(entry.path, LOGO_SUBDIR)
        if not os.path.islink(logo_path) and os.path.isdir(logo_path):
            stale += sweep_stale_temps(logo_path, now=now)
    if busy_logos:
        # Once per prune, counted, keys only (R12): a folder left because a
        # run holds it is not an error, and the next prune ages it.
        log("cache prune: %s; left for the next prune"
            % counted_sentence(len(busy_logos), "%d logo folder is held by a running fetch",
                               "%d logo folders are held by running fetches"))
    return {"removed": removed, "agedEpg": aged, "agedLogos": aged_logos, "busyLogos": busy_logos,
            "staleTemps": stale, "skipped": skipped, "kept": kept_dirs}


def cmd_cache(args: argparse.Namespace) -> int:
    directory = cache_dir(args.cache_dir)
    action = args.action
    try:
        if action == "migrate":
            payload = cache_migrate(directory, args.key or None)
        elif action == "remove":
            payload = cache_remove(directory, args.key)
        elif action == "epg-clear":
            payload = cache_epg_clear(directory, args.key)
        elif action == "logos-clear":
            payload = cache_logos_clear(directory, args.key)
        else:
            payload = cache_prune(directory, list(args.keep or []), args.active or None, args.epg_max_age)
        result: dict[str, Any] = {"ok": True, "kind": "cache", "action": action}
        result.update(payload)
        emit(result)
        return EXIT_OK
    except HelperError as error:
        log("cache %s: %s" % (action, error.message))
        emit(error_payload("cache", error, action=action))
        return EXIT_ERROR


