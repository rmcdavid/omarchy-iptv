# A part of bin/omarchy-iptv (D-REL-7), not a module: the helper compiles
# this file into its own namespace in the order its HELPER_PARTS lists, so
# a part sees every name the parts before it define. Run the helper.
from __future__ import annotations
# --------------------------------------------------------------- state
# state.json version 2 (ARCHITECTURE-SOURCES.md section 2): the 0.1 keys
# unchanged plus `cacheLayout` and the `sources` history. A version-1 file
# reads as version 2 with an empty history; the first write upgrades it.
# v0.3.0 adds one optional nullable key, `session`, with NO version bump
# (ARCHITECTURE-PLAYER.md section 8), handled exactly the way the version-1
# keys are: normalize_state whitelists what it knows, so a file that predates
# the key reads it as None and an older build simply drops it. The key is the
# service's, but every `state` action rewrites the whole document, so the CLI
# has to carry it through or a `favorite add` would silently erase the record
# a running player depends on (ruling PO-3).
# Every `state` action prints the state through public_state(), which
# replaces `url` / `epgUrl` by their hosts: stdout must never carry a URL.

def default_state() -> dict[str, Any]:
    return {"version": STATE_VERSION, "cacheLayout": 0, "favorites": [], "recents": [], "lastPlayed": None,
            "session": None, "sources": [], "savedSearches": [], "hiddenGroups": [], "activeKey": ""}


def normalize_active_key(raw: Any) -> str:
    """Mirror of Model.activeKeyText: the active source's key (D-SINK-19), or
    "" when the value is not a key. A key naming no record is KEPT -- the shell
    resolves that case (Model.activeKeyOf) and dropping it here would hide it.

    This is the fifth key this reader had to be taught and the one whose loss
    would be worst: default_state() is rebuilt field by field and copied into,
    so a key this function does not exist for is ERASED by the next
    `state favorite add` -- which for this key means the plugin reads as not
    configured at all. savedSearches and hiddenGroups both carry that warning
    above them; this one would have been visible."""
    if not isinstance(raw, str):
        return ""
    key = raw.strip()
    return key if SOURCE_KEY_RE.match(key) else ""


# Must match the model's MAX_SAVED_SEARCHES / MAX_SAVED_TERMS / MAX_SAVED_QUERY and
# savedSearchTerms / savedSearchRecord. One shared fixture runs both.
MAX_SAVED_SEARCHES = 20
# Mirror of Model.MAX_HIDDEN_GROUPS (M3-01); the hidden-groups fixture on the
# dev branch pins both readers to the same list on the same bytes.
MAX_HIDDEN_GROUPS = 200


def normalize_hidden_groups(raw: Any) -> list[str]:
    """Mirror of Model.hiddenGroupList: strings only, stripped, non-empty,
    first occurrence wins, capped at MAX_HIDDEN_GROUPS. Anything else --
    a number, a dict, a non-list -- reads as nothing rather than failing."""
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    seen: set[str] = set()
    for item in raw:
        if len(out) >= MAX_HIDDEN_GROUPS:
            break
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out
MAX_SAVED_TERMS = 8
MAX_SAVED_QUERY = 64


def saved_search_terms(query: Any) -> list[str]:
    text = normalize_text(str(query or "")[:MAX_SAVED_QUERY])
    if not text:
        return []
    return text.split(" ")[:MAX_SAVED_TERMS]


def normalize_saved_search(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    query = str(entry.get("query") or "")[:MAX_SAVED_QUERY]
    if not saved_search_terms(query):
        return None
    # float() then int(), NOT int() alone, and the shared fixture is what
    # forced it: the model does Math.trunc(Number(x)), which reads "12.9" as 12,
    # while int("12.9") raises and this reader would have stored 0. The vector
    # is in the fixture precisely so the two cannot drift apart again.
    #
    # normalize_played above still has the int()-alone form and therefore still
    # disagrees with playedRecord on that input. Filed as D-STATE-1 rather than
    # changed here: it is a pre-existing divergence on a different key and it
    # is not this feature's to move.
    return {"query": query, "at": coerce_int(entry.get("at"))}


def normalize_played(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, dict) or not entry.get("id"):
        return None
    return {"id": str(entry["id"]), "name": str(entry.get("name") or ""),
            "at": coerce_int(entry.get("at"))}


def coerce_int(value: Any) -> int:
    """D-STATE-1. Mirror the model's `Math.trunc(Number(x)) || 0` exactly.

    This used to be `int(x)`, which accepts only a plain integer literal and
    RAISES on everything else -- so `"12.9"` stored 0 where the guide read 12,
    and `"1e3"` stored 0 where the guide read 1000. Same bytes, two answers, on
    `recents[].at`, `lastPlayed.at` and `session.at`.

    float() first is what buys the whole JavaScript numeric grammar: decimals,
    exponents and surrounding whitespace all parse, a trailing tail does not
    (`"7abc"` is 0 in both), and int() then truncates TOWARD ZERO rather than
    down, which is what Math.trunc does and why `-3.7` is -3 and not -4.

    Found by the saved-search fixture, which carried `at: "12.9"` for its own
    key and went red on a key it was not written for.
    """
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def non_negative_int(value: Any) -> int:
    """The same coercion, then clamped at zero.

    D-STATE-1 was filed against normalize_played alone. It was never only
    there: this function had the identical `int(x)` and therefore the identical
    disagreement, on five more keys -- `addedAt`, `lastUsed`, `fetchedAt`,
    `channelCount` and `groupCount` on every source record. The model reads
    "12.9" as 12 and "1e3" as 1000 for all of them; this read 0.

    One coercion with two callers, so a third caller cannot reintroduce the
    split by writing `int()` again out of habit.
    """
    number = coerce_int(value)
    return number if number > 0 else 0


# D-SINK-19 round 10, R20a (D-SRC-20): THE HELPER KEEPS WHAT THE SERVICE
# WRITES. normalize_state is a whitelist, so a key the service writes and this
# reader does not know is ERASED by the next hand-run `state favorite add`
# (round 9's pendingEpg and epgSetAt were, and the user's guide URL existed
# nowhere afterwards). The check that holds the two readers together is ONE
# fixture both run (the shared state-keys fixture, dev branch): the node suite
# requires every key the service can serialise to equal its list, and the
# python suite requires this reader to emit exactly that list.
#
# Round 11 (R21) withdrew the three keys round 9 and 10 taught this reader
# (pendingEpg, epgSetAt, entryInputs) with the machinery that wrote them, and
# added one: the migration marker, below.


def normalize_entry_migrated(raw: Any) -> bool:
    """Mirror of Model.entryMigratedOf: the migration marker (D-SINK-19 R21a),
    True only for the JSON boolean true. A string "true" or a 1 is no marker:
    the model reads `=== true`, and a coercion here would read an unmigrated
    file as migrated on one side and not the other (the activeKeyText lesson).

    Erasing it is NOT harmless and NOT fatal, and the difference matters: a
    state without it makes the next shell start migrate again, which reads the
    bar entry's URLs as inputs once more. That is the downgrade the ruling
    accepts on purpose (0.13.6 drops it and writes its URL back onto the
    entry, and the re-upgrade must adopt that URL); it is not something a
    hand-run `state` verb of THIS helper may cause."""
    return raw is True


def normalize_migration_pending(raw: Any) -> dict[str, Any] | None:
    """Mirror of Model.migrationPendingOf (D-SRC-64, round 7, 2026-10-22):
    the pair a migration held at the MAX_SOURCES cap has parked in the state
    -- `{"playlistUrl": <non-empty str>, "epgUrl": <str>}` -- or None. Not a
    source record (never counted against the cap, never listed), never
    rewritten or validated here: the shell validates it when it lands, as it
    validated the bar entry's value it was read from. A reader not taught it
    would ERASE it on the next hand-run `state` verb, and it is the ONLY copy
    of that credential while the hold lasts (the bar entry is stripped once
    the state write carrying it has landed), which is the savedSearches
    trap with a worse loss. Anything that is not that shape reads as none,
    exactly as the model reads it (the shared state-keys fixture)."""
    if not isinstance(raw, dict):
        return None
    playlist = raw.get("playlistUrl")
    if not isinstance(playlist, str) or playlist == "":
        return None
    epg = raw.get("epgUrl")
    return {"playlistUrl": playlist, "epgUrl": epg if isinstance(epg, str) else ""}


def normalize_source(raw: Any) -> dict[str, Any] | None:
    """One history record per the section 2.1 field rules; None drops it.
    A `url` with a control character (NUL, CR, ...) drops the record with a
    log line naming the key only (D-SRC-09, mirrors Model.parseState); the
    validator would otherwise strip the character and keep a record whose
    key no longer matches its URL. The same character in `epgUrl` clears
    that field only."""
    if not isinstance(raw, dict):
        return None
    key = raw.get("key")
    if not isinstance(key, str) or not SOURCE_KEY_RE.match(key):
        return None
    url = raw.get("url")
    if not isinstance(url, str):
        return None
    if _CONTROL_CHARS.search(url):
        log("state: dropped source %s (control characters in url)" % key)
        return None
    playlist = validate_source_url(url, origin="cli")
    if not playlist["ok"]:
        log("state: dropped source %s (invalid url: %s)" % (key, playlist["code"]))
        return None
    raw_epg = raw.get("epgUrl")
    if isinstance(raw_epg, str) and _CONTROL_CHARS.search(raw_epg):
        log("state: cleared the epgUrl of source %s (control characters)" % key)
        raw_epg = ""
    epg = validate_source_url(raw_epg, origin="cli") if isinstance(raw_epg, str) else None
    # SR22: the helper truncates an over-cap label on read, never errors.
    label = cap_code_points(sanitize_input(raw.get("label"), MAX_SOURCE_URL), MAX_LABEL) or derive_label(playlist["url"], playlist["kind"])
    origin = raw.get("origin")
    record = {
        "key": key,
        "url": playlist["url"],
        "epgUrl": epg["url"] if epg is not None and epg["ok"] else "",
        "kind": playlist["kind"],
        "label": label,
        "labelCustom": raw.get("labelCustom") is True,
        "origin": origin if origin in SOURCE_ORIGINS else "guide",
        "addedAt": non_negative_int(raw.get("addedAt")),
        "lastUsed": non_negative_int(raw.get("lastUsed")),
        "fetchedAt": non_negative_int(raw.get("fetchedAt")),
        "channelCount": non_negative_int(raw.get("channelCount")),
        "groupCount": non_negative_int(raw.get("groupCount")),
    }
    return record


def normalize_state(raw: Any) -> dict[str, Any]:
    """Tolerant reader mirroring Model.parseState: unknown shapes fall back
    to an empty state, entries are de-duplicated and coerced. A version-1
    file (0.1.0) yields `sources: []`, `cacheLayout: 0`; a file from before
    the detached player yields `session: None`; records that fail the field
    rules are dropped, a repeated url or key keeps the first."""
    state = default_state()
    if not isinstance(raw, dict):
        return state
    favorites = raw.get("favorites")
    if isinstance(favorites, list):
        for item in favorites:
            key = str(item or "")
            if key and key not in state["favorites"]:
                state["favorites"].append(key)
    recents = raw.get("recents")
    if isinstance(recents, list):
        for item in recents:
            entry = normalize_played(item)
            if entry is not None:
                state["recents"].append(entry)
    # Saved searches. This writer rebuilds from default_state() and copies only
    # keys it knows, so an un-taught copy ERASES the key -- proven live before
    # this was added: one `state favorite add` through the real CLI dropped it,
    # exit 0, "ok": true, no warning. Mirrors Model.parseState, including the
    # de-duplication on the FOLDED terms rather than the raw string.
    saved = raw.get("savedSearches")
    if isinstance(saved, list):
        seen_terms = set()
        for item in saved:
            if len(state["savedSearches"]) >= MAX_SAVED_SEARCHES:
                break
            record = normalize_saved_search(item)
            if record is None:
                continue
            sig = " ".join(saved_search_terms(record["query"]))
            if sig in seen_terms:
                continue
            seen_terms.add(sig)
            state["savedSearches"].append(record)
    # Hidden groups (M3-01). Same whitelist trap as savedSearches above: this
    # writer rebuilds from default_state(), so a key it is not taught is
    # erased by the next `state favorite add`.
    state["hiddenGroups"] = normalize_hidden_groups(raw.get("hiddenGroups"))
    # Which source is active, by key (D-SINK-19). Same whitelist trap again.
    state["activeKey"] = normalize_active_key(raw.get("activeKey"))
    state["lastPlayed"] = normalize_played(raw.get("lastPlayed"))
    # What the player was last asked to play (4.6, section 8). Same record as
    # lastPlayed, different lifetime: the service clears it when the player
    # stops or ends cleanly, so one left behind means the player died with no
    # shell attached and the channel is marked failed in the guide on reattach
    # instead of raising a toast minutes late. Never URL-bearing: a channel id
    # and a display name, which is never a URL.
    state["session"] = normalize_played(raw.get("session"))
    # D-SINK-19 R21a: the migration marker, absent unless it is exactly true,
    # exactly as Model.parseState reads it. Same whitelist trap as every key
    # above: a reader not taught it erases it, and the next shell start would
    # read the bar entry's URLs as migration inputs again.
    if normalize_entry_migrated(raw.get("entryMigrated")):
        state["entryMigrated"] = True
    # D-SRC-64: the parked pair of a migration held at the cap, absent unless
    # it reads as one; the same whitelist trap, and the only copy of a
    # credential while it is held.
    pending = normalize_migration_pending(raw.get("migrationPending"))
    if pending is not None:
        state["migrationPending"] = pending
    state["cacheLayout"] = CACHE_LAYOUT if raw.get("cacheLayout") == CACHE_LAYOUT else 0
    sources = raw.get("sources")
    if isinstance(sources, list):
        for item in sources:
            record = normalize_source(item)
            if record is None or len(state["sources"]) >= MAX_SOURCES:
                continue
            if find_source(state["sources"], record["key"]) or find_source_by_url(state["sources"], record["url"]):
                continue
            # D-SINK-17, the half the first fix missed. derive_label's output
            # is STORED, so repairing the derivation does nothing for a record
            # written before the repair: an install that added
            # https://u@er:pass@host.example/list.m3u on 0.13.1 or earlier
            # holds er:pass@host.example as its label, and the label is a wider
            # sink than the host beside it -- public_source emits it verbatim
            # next to the host it correctly redacts, and redact_urls cannot
            # help because a bare er:pass@host has no "://" in it. A label the
            # USER did not choose is therefore re-derived on every load. It is
            # deterministic, so an unaffected record gets the string it already
            # had; an affected one heals itself the first time the file is
            # read. labelCustom is the whole of the distinction. Re-derived
            # here rather than in normalize_source because uniqueness is a
            # property of the LIST: two sources on one host must not both come
            # back as that host.
            if not record.get("labelCustom"):
                record["label"] = unique_label(
                    derive_label(record["url"], record["kind"]),
                    [s2.get("label", "") for s2 in state["sources"]])
            state["sources"].append(record)
    return state


def public_source(record: dict[str, Any]) -> dict[str, Any]:
    """The record with `url` / `epgUrl` replaced by `host` / `epgHost`."""
    out: dict[str, Any] = {}
    for name, value in record.items():
        if name == "url":
            out["host"] = source_host(value) if record.get("kind") == "http" else "local file"
        elif name == "epgUrl":
            out["epgHost"] = "" if not value else (source_host(value) if not value.startswith("/") else "local file")
        else:
            out[name] = value
    return out


def public_state(state: dict[str, Any]) -> dict[str, Any]:
    """Every `state` action prints this; stdout is a sink (rule 5) and must
    never carry a URL. `activeKey` needs no treatment and is printed as it is:
    it is fnv1a32 of the URL, which the cache directory names on disk already,
    and it is the identifier every other field here is keyed by."""
    out = dict(state)
    out["sources"] = [public_source(record) for record in state.get("sources", [])]
    # D-SRC-64: the parked pair of a held migration is two URLs, printed as
    # their hosts exactly as a record's are (rule 5; found by reading this
    # function while teaching the reader the key, rule 15: `dict(state)`
    # copies every top-level key, so a URL-bearing key is on stdout the day
    # it is added unless it is treated here).
    pending = state.get("migrationPending")
    if isinstance(pending, dict):
        playlist = str(pending.get("playlistUrl", ""))
        epg = str(pending.get("epgUrl", ""))
        out["migrationPending"] = {
            "host": "local file" if playlist.startswith("/") else source_host(playlist),
            "epgHost": "" if not epg else ("local file" if epg.startswith("/") else source_host(epg)),
        }
    return out


def check_custom_label(cleaned: str, others: list[str]) -> str:
    """A label the user typed (Model.validateLabel): refused over MAX_LABEL
    code points (label_too_long, never cut, SR22) and when another source
    has it case-insensitively (label_taken); never rewritten (UX 5.6)."""
    custom = sanitize_input(cleaned, MAX_SOURCE_URL)
    if len(custom) > MAX_LABEL:
        raise HelperError("label_too_long", "label longer than %d characters" % MAX_LABEL, field="label")
    if custom.lower() in {label_key(item) for item in others}:
        raise HelperError("label_taken", "a source named '%s' already exists" % custom, field="label")
    return custom


def add_source_record(state: dict[str, Any], url: Any, epg_url: Any, label: Any, origin: str, now: int) -> str:
    """Append a history record (the CLI counterpart of Model.addSource);
    raises the UX-SOURCES.md 5.4 codes plus duplicate / too_many /
    label_taken / label_too_long. Returns the new key."""
    playlist = validate_source_url(url)
    if not playlist["ok"]:
        raise HelperError(playlist["code"], "playlist %s" % playlist["message"])
    epg = ""
    if epg_url is not None and sanitize_input(epg_url, MAX_SOURCE_URL + 1) != "":
        checked = validate_source_url(epg_url)
        if not checked["ok"]:
            raise HelperError(checked["code"], "EPG %s" % checked["message"], field="epgUrl")
        epg = checked["url"]
    sources = state["sources"]
    existing = find_source_by_url(sources, playlist["url"])
    if existing is not None:
        raise HelperError("duplicate", "already in the source history as '%s'" % existing["label"], key=existing["key"])
    if len(sources) >= MAX_SOURCES:
        raise HelperError("too_many", "the source history holds at most %d sources" % MAX_SOURCES)
    labels = [record["label"] for record in sources]
    cleaned = _CONTROL_CHARS.sub("", "" if label is None else str(label)).strip(" \u00a0")
    if cleaned != "":
        final_label, label_custom = check_custom_label(cleaned, labels), True
    else:
        final_label, label_custom = unique_label(derive_label(playlist["url"], playlist["kind"]), labels), False
    key = allocate_source_key(sources, playlist["url"])
    sources.append({
        "key": key,
        "url": playlist["url"],
        "epgUrl": epg,
        "kind": playlist["kind"],
        "label": final_label,
        "labelCustom": label_custom,
        "origin": origin if origin in SOURCE_ORIGINS else "cli",
        "addedAt": now,
        "lastUsed": now,
        "fetchedAt": 0,
        "channelCount": 0,
        "groupCount": 0,
    })
    return key


# D-SRC-11, OVERTURNED IN PART BY D-SINK-19. The record fields `state source
# update` warns about, with the flag that writes each and the plugin setting
# the bar entry used to carry for it.
#
# What D-SRC-11 found (2026-10-03, measured on the live install): the settings
# were the source of truth for the ACTIVE source and the history followed
# them, so `--epg-url` on the active record was rewritten from the plugin's
# `epgUrl` setting the moment the shell re-read state.json -- which this
# command's own write caused -- and the helper said "ok": true about a value
# that was already gone. The warning below was written for that.
#
# D-SINK-19 inverted the ownership. The bar entry's `playlistUrl` and `epgUrl`
# are not read at all once an install has migrated (round 11, R21: the shell
# reads them once, to migrate a 0.13.x entry, and refuses and removes a value
# found there afterwards); `activeKey` in state.json names the active source;
# the record is the only store for both URLs and the shell reads it.
# So this command's write is no longer undone by a reconcile, and a re-key
# through `--url` moves `activeKey` with the record (update_source_record).
# What the warning says now is the two things still worth a line:
#  - the running shell PICKS THE NEW VALUE UP: its FileView reloads on this
#    helper's atomic rename (measured, R23g; the first session after a fresh
#    install included since R24c re-arms the watch), and a change made in
#    the guide and not yet saved is MERGED with it, this write winning where
#    both changed the same record (R24a). Rounds 9 to 12 said the opposite
#    (D-SRC-19); round 14 measured that only the dir-absent first session
#    behaved that way, and closed it;
#  - `--url` RE-KEYS the record: the cache directory of the old key is the
#    caller's to move or remove (the shell does it for its own edits; this
#    command does not), and the channels are fetched again.
# The warning still fires for an inactive source too, which is wider than it
# needs to be; narrowing it is a behaviour change on a documented warning and
# is not taken here.
#
# WHY THIS WARNS RATHER THAN REFUSES (unchanged): writing the host's
# shell.json is out of scope for a stdlib-only helper that names that file
# nowhere, and refusing would break the half that is right for every source.
# Exit code stays 0 because the write did happen.
#
# Scope, stated rather than implied: this fires for `update`, which is what
# D-SRC-11 is filed against; `add` is a source that is not active yet, where
# nothing competes with the record.
SETTING_OWNED_SOURCE_FIELDS = (
    ("epgUrl", "--epg-url", "epgUrl", "guide (EPG) URL"),
    ("url", "--url", "playlistUrl", "playlist URL"),
)


def setting_owned_warnings(fields: Any) -> list[str]:
    """Lines for a `state source update` that writes a URL field of a record
    (D-SRC-11, as overturned in part by D-SINK-19), in a fixed order. Empty
    when nothing asked for is one, so `--label` on its own says nothing."""
    asked = [row for row in SETTING_OWNED_SOURCE_FIELDS if row[0] in set(fields or ())]
    if not asked:
        return []
    out = []
    for field, flag, setting, _human in asked:
        rekey = ""
        if field == "url":
            rekey = (" It also RE-KEYED the record: a new key, 'activeKey' moved with it when it was "
                     "the active source, the old key's cache directory is yours to remove, and the "
                     "channels are fetched again.")
        out.append("%s wrote the record's %s. The record is the only store for it: the plugin "
                   "setting '%s' on the bar entry is not where the value is kept, and the "
                   "running shell no longer reads it -- it was read once, to migrate an "
                   "older install, and a value found there now is refused and removed "
                   "(D-SINK-19; the D-SRC-11 warning that stood here said the shell would undo "
                   "this write, and that design is gone).%s"
                   % (flag, field, setting, rekey))
    # Round 14 (R24c, rule 15): this line said for two rounds that a running
    # shell does not re-read state.json after this write. Measured: it does
    # (R23g), the first session after a fresh install included now (R24c),
    # and an unsaved in-app change is merged with it rather than written over
    # it (R24a), this write winning where both changed the same record.
    out.append("A running omarchy-shell re-reads state.json after this write and keeps the %s it "
               "wrote. If the same source was changed in the guide and that change was not saved "
               "yet, this write wins for that source. The guide's Sources screen edits the same "
               "record inside the shell." % " and ".join(row[3] for row in asked))
    return out


def update_source_record(state: dict[str, Any], key: str, url: Any, epg_url: Any, label: Any, now: int) -> tuple[str, str]:
    """Edit a record in place. A changed playlist URL re-keys it (fetchedAt
    and the counts reset; the caller moves or removes the cache directory).
    -> (key, replaced key or "")."""
    sources = state["sources"]
    record = find_source(sources, check_source_key(key))
    if record is None:
        raise HelperError("unknown_source", "no source with that key")
    replaced = ""
    if url is not None:
        playlist = validate_source_url(url)
        if not playlist["ok"]:
            raise HelperError(playlist["code"], "playlist %s" % playlist["message"])
        if playlist["url"] != record["url"]:
            other = find_source_by_url(sources, playlist["url"])
            if other is not None:
                raise HelperError("duplicate", "already in the source history as '%s'" % other["label"], key=other["key"])
            replaced = record["key"]
            record["url"] = playlist["url"]
            record["kind"] = playlist["kind"]
            record["key"] = allocate_source_key([item for item in sources if item is not record], playlist["url"])
            # D-SINK-19. The active source is named by key now, so a re-key has
            # to carry the pointer with it or state.json is left naming a
            # record that no longer exists. Introduced by that change rather
            # than fixed by it: before it, nothing in this file could tell
            # which source was active.
            if state.get("activeKey") == replaced:
                state["activeKey"] = record["key"]
            record["fetchedAt"] = 0
            record["channelCount"] = 0
            record["groupCount"] = 0
            if not record["labelCustom"]:
                record["label"] = unique_label(derive_label(playlist["url"], playlist["kind"]),
                                               [item["label"] for item in sources if item is not record])
    if epg_url is not None:
        if sanitize_input(epg_url, MAX_SOURCE_URL + 1) == "":
            record["epgUrl"] = ""
        else:
            checked = validate_source_url(epg_url)
            if not checked["ok"]:
                raise HelperError(checked["code"], "EPG %s" % checked["message"], field="epgUrl")
            record["epgUrl"] = checked["url"]
    if label is not None:
        cleaned = _CONTROL_CHARS.sub("", str(label)).strip(" \u00a0")
        others = [item["label"] for item in sources if item is not record]
        if cleaned == "":
            record["label"] = unique_label(derive_label(record["url"], record["kind"]), others)
            record["labelCustom"] = False
        else:
            record["label"] = check_custom_label(cleaned, others)
            record["labelCustom"] = True
    return record["key"], replaced


def remove_source_record(state: dict[str, Any], key: str) -> dict[str, Any]:
    record = find_source(state["sources"], check_source_key(key))
    if record is None:
        raise HelperError("unknown_source", "no source with that key")
    state["sources"] = [item for item in state["sources"] if item is not record]
    # D-SINK-19, the same obligation as the re-key above: removing the ACTIVE
    # source clears the pointer. Model.activeKeyOf resolves a dangling key to
    # "" so a shell reading this file is safe either way, but leaving one
    # behind means the next reader has to decide the same question again.
    if state.get("activeKey") == record["key"]:
        state["activeKey"] = ""
    return record


def state_file_target(path: str) -> str:
    """The file a `state` verb reads and WRITES for the state path `path`.

    D-SINK-19 round 14, R24b (D-SRC-23): ONE ANSWER PER PATH. A symlink at
    state.json (a dotfiles user's) was followed for a read by open_regular
    and then REPLACED by the write's rename, and a DANGLING one -- the
    target moved, a folder not mounted yet -- read as ENOENT, so every verb
    treated it as a fresh state: `show` printed an empty listing and
    `favorite add` and `source add` wrote an empty state plus their change
    over the link, exit 0, while `state init` lstat()s the same path and
    answers `link` (`other` before this round), and the shell refuses it.
    Measured on this machine on 2026-10-14 (spikes/filewatch, set r24): the
    shell's own FileView save over a VALID link writes THROUGH it -- the link
    stays a link and the target takes the bytes -- and this helper's write
    replaced it with a regular file, after which the running shell saw none
    of the helper's later writes. So now:
      nothing at the path      the path itself (a fresh state)
      a regular file           the path itself
      a symlink to a regular   the link's TARGET (os.path.realpath): the
        file                   write lands beside it and is renamed onto
                               it, so the link survives (write_state_file)
      a symlink to anything    refused, exit 1, nothing written, link
        else, or to nothing    untouched
      anything else            the path; read_state_strict refuses it
    A link retargeted between this answer and the write is a race this does
    not close; nothing here follows a link it did not just resolve."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return path
    except NotADirectoryError:
        raise HelperError("state_unreadable", "the state folder is not a folder (a file is at its path, or above it); nothing was written")
    except OSError:
        return path
    if not stat.S_ISLNK(st.st_mode):
        return path
    try:
        target = os.stat(path)
    except OSError:
        raise HelperError("state_unreadable", "state.json is a symbolic link whose target is missing; nothing was written")
    if not stat.S_ISREG(target.st_mode):
        raise HelperError("state_unreadable", "state.json is not a regular file; nothing was written")
    return os.path.realpath(path)


def write_state_file(path: str, target: str, payload: Any) -> None:
    """Write state.json for a `state` verb: at the path, or THROUGH the link
    to `target` (state_file_target). A target that is not the path lives in
    a directory that is not the plugin's, which is not created or chmod-ed;
    the file itself is still written 0600 by an atomic rename.

    D-SINK-19 round 15 (D-SRC-34): that folder can refuse the write -- it is
    never chmod-ed back to 0700 the way the plugin's own state folder is --
    and the refusal is a sentence, exit 1, nothing written (the temporary
    file is removed by write_text_atomic), where it used to be a
    PermissionError traceback and `code: internal`."""
    through_link = os.path.abspath(target) != os.path.abspath(path)
    try:
        write_json_atomic(target, payload, private_dir=not through_link)
    except FolderUnusable:
        raise
    except OSError as error:
        reason = error.strerror or type(error).__name__
        if through_link:
            raise HelperError("state_unwritable", "state.json is a symbolic link into a folder that cannot be written (%s); nothing was written" % reason)
        raise HelperError("state_unwritable", "state.json could not be written (%s); nothing was written" % reason)


def broken_folder_link(directory: str) -> str:
    """The state FOLDER's rule, R25c (D-SRC-32): R24b's rule for the file,
    one level up. A symbolic link at the state folder, or at a folder above
    it, that dangles or leads to something that is not a folder -> its path;
    "" when the chain is sound (every component that exists is a folder,
    through links that lead to folders) or simply absent. Only the FIRST
    component that exists is asked about: below it nothing exists, and above
    it the lstat of that component already succeeded."""
    current = os.path.abspath(directory)
    while current:
        if os.path.lexists(current):
            if os.path.islink(current) and not os.path.isdir(current):
                return current
            return ""
        parent = os.path.dirname(current)
        if parent == current:
            return ""
        current = parent
    return ""


def state_path_found(path: str) -> str:
    """What is at the state path, BEFORE anything is created or chmod-ed.

    D-SINK-19 round 12, R22a: the service's FileView reports "file not found"
    both for a path with nothing at it and for a file inside a directory it
    cannot search (measured on Quickshell 0.3.1: a 0000 or 0600 directory
    reads exactly like a fresh install), and a fresh install is the one load
    failure that may be written over. This is the witness: an lstat, made
    first, because init_state_file then restores the modes it finds and the
    evidence would be gone. -> "absent" (nothing there: ENOENT, a missing
    parent included), "file" (a regular file, or a symlink to one),
    "link" (R24b: a symlink whose target is missing or is not a regular
    file -- the `state` verbs refuse it, state_file_target), "not-a-dir"
    (R24b: something that is not a directory where the state directory, or
    one above it, should be: lstat answers ENOTDIR), "other" (a directory,
    a FIFO, anything else), or "unreadable" (lstat itself failed otherwise:
    the directory cannot be searched)."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return "absent"
    except NotADirectoryError:
        return "not-a-dir"
    except OSError:
        return "unreadable"
    if stat.S_ISREG(st.st_mode):
        return "file"
    if stat.S_ISLNK(st.st_mode):
        try:
            return "file" if stat.S_ISREG(os.stat(path).st_mode) else "link"
        except OSError:
            return "link"
    return "other"


def init_state_file(path: str, state: dict[str, Any]) -> bool:
    """Create `path` with mode 0600 when missing (S-02). Quickshell's FileView,
    which the service uses to write state.json, creates a missing file 0644
    and keeps the mode of an existing one, so the service runs `state init`
    once at startup before its first write. O_EXCL makes the check-and-create
    atomic: a file that appears in between is left alone. An existing file
    is not rewritten; its mode is tightened only when it is not 0600 already
    (D-SRC-15, R10): a chmod is an inotify IN_ATTRIB on the file the shell's
    FileView watches, mode changed or not, and the reload it causes arrives
    while the shell's first save is still parked. The shell survives that
    reload on its own (it ignores a reload while a save is parked or in
    flight); this leaves the already-private file untouched so the ordinary
    start never raises it at all. Returns True when created."""
    ensure_private_dir(os.path.dirname(path))
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    except FileExistsError:
        # R23d: a REGULAR file (or a symlink to one) is the only thing this
        # repairs. A directory, a FIFO or a socket at the path is the user's,
        # and the no-write mode's notice tells them to move it aside; making
        # it 0600 made a directory unsearchable (round 12, measured live).
        chmod_if_kind(path, 0o600, stat.S_ISREG)
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(state, ensure_ascii=False, separators=(",", ":")) + "\n")
        os.fchmod(handle.fileno(), 0o600)
    return True


def read_state_strict(path: str) -> dict[str, Any]:
    """state.json for a verb that reads it to WRITE it (or to report it).

    D-SINK-19 round 12, R22a, the helper's half: a state that did not load is
    never written. read_json answers None for a missing file, an unreadable
    one and one that does not parse alike, and normalize_state turns None
    into the empty default -- so `state favorite add` over a file it could
    not read used to write an empty state plus one favourite over it, every
    source and credential gone, exit 0. Only "the file does not exist" is a
    fresh state now; anything else is refused before anything is written,
    with the reason and never the file's contents."""
    try:
        text = read_regular_text(path)
    except FileNotFoundError:
        return default_state()
    except NotRegularFile:
        # R23b: a directory, a FIFO or a socket at the path. Opened without
        # blocking and refused on the descriptor's own fstat.
        raise HelperError("state_unreadable", "state.json is not a regular file; nothing was written")
    except OSError as error:
        raise HelperError("state_unreadable", "state.json could not be read (%s); nothing was written"
                          % (error.strerror or type(error).__name__))
    except ValueError:
        raise HelperError("state_unreadable", "state.json is not UTF-8 text; nothing was written")
    try:
        raw = json.loads(text)
    except ValueError:
        raw = None
    if not isinstance(raw, dict):
        raise HelperError("state_unreadable", "state.json is not a valid state file; nothing was written")
    return normalize_state(raw)


# D-SINK-19 round 14, R24d (D-SRC-24). How long `state init` may live, in
# seconds, armed as SIGALRM at the top of the verb with its DEFAULT action
# (the process ends; nothing here handles it). The service bounds the
# start-up check at stateInitTimeoutMs (15 s) plus stateInitKillGraceMs (2 s)
# and reaps what it stops -- but only while the shell outlives the init: a
# shell stopped inside that window (a restart, a crash) left a hung init
# reparented to the user's service manager for as long as the hang lasted
# (the round-13 live lens, measured). 30 s is past the service's bound, so
# this never pre-empts it, and it is the most the init can outlive any
# shell by. What no signal reaches: a process in uninterruptible sleep on a
# hung filesystem (state D) takes the signal only when the kernel lets go.
STATE_INIT_DEADLINE = 30


def state_mode_repair(directory: str, path: str) -> dict[str, Any]:
    """`state mode` (D-SRC-49, D-SINK-22 windows b and c; 2026-10-24): the
    modes the plugin's own files are meant to have, repaired when they are
    not -- the state folder 0700 and state.json 0600 -- and nothing else:
    no directory is created, no file is created or read, no migration runs.
    The service's FileView keeps an existing file's mode and creates a
    missing one at the umask's (0644), so a state.json the user `mv`ed in
    at 0644, or one a save created after a re-point of the folder, was
    written into at that mode for the rest of the session, provider URLs
    included; `state init` repaired it only at the next start. The service
    runs this after every save that LANDS (one interpreter start, the
    sealed stub, about 30 ms of CPU), so the window is the milliseconds
    between the save and this repair. Both repairs are chmod_if_kind: an
    O_PATH descriptor, the KIND checked on the inode (a directory at the
    file's path, a link to nothing, a FIFO: untouched), and no chmod at all
    when the mode is already right -- so in the steady state this raises no
    IN_ATTRIB on the file the shell watches. The one bounded reply says
    what changed; a chmod that does fire raises one reload of the base
    text, which the service ignores (Model.reloadDisposition, unchanged)."""
    return {"folder": "changed" if chmod_if_kind(directory, 0o700, stat.S_ISDIR) else "kept",
            "file": "changed" if chmod_if_kind(path, 0o600, stat.S_ISREG) else "kept"}


def cmd_state(args: argparse.Namespace) -> int:
    action = args.action
    if action in ("init", "mode"):
        # FIRST, before the path is even named: everything after this can
        # touch a filesystem that hangs. `mode` runs after every landed save
        # against the same path, so it has the same bound.
        signal.alarm(STATE_INIT_DEADLINE)
    directory = state_dir(args.state_dir)
    path = os.path.join(directory, STATE_FILE)
    extra: dict[str, Any] = {}
    if action == "source":
        extra["op"] = args.op
    if action == "mode":
        # Before the folder-link check: a folder that is a link to nothing
        # is simply not a directory, so both repairs answer "kept".
        payload_mode: dict[str, Any] = {"ok": True, "kind": "state", "action": action}
        payload_mode.update(state_mode_repair(directory, path))
        emit(payload_mode)
        return EXIT_OK
    try:
        # R25c (D-SRC-32): a link at the state folder, or above it, that leads
        # nowhere. Every verb used to read it as a fresh state -- `show` and
        # `source list` printed an empty listing, exit 0 -- and the writers
        # and the init ended in a traceback; now the init names it and every
        # other verb refuses it, the link untouched.
        broken = broken_folder_link(directory)
        if broken and action == "init":
            emit({"ok": True, "kind": "state", "action": action, "found": "folder-link", "created": False,
                  "state": public_state(default_state())})
            return EXIT_OK
        if broken:
            raise HelperError("state_unreadable", "the state folder is a symbolic link whose target is missing or is not a folder; nothing was written")
        if action == "init":
            # R22a: `found` first -- the lstat witness, before anything is
            # repaired. The init NEVER rewrites a file that exists, whatever
            # it holds -- O_EXCL refuses to create over it and the existing
            # branch only chmods a regular file (R23d) -- so a state it could
            # not parse is left byte for byte as it was (test_state's R22a
            # cases).
            found = state_path_found(path)
            if found == "not-a-dir":
                # R24b (D-SRC-26): a file where the state DIRECTORY should be.
                # Nothing can be created under it and nothing is changed; the
                # answer says what was found (this printed a traceback and
                # `code: internal` before).
                emit({"ok": True, "kind": "state", "action": action, "found": found, "created": False,
                      "state": public_state(default_state())})
                return EXIT_OK
            # The init reads tolerantly: what it read is only ever written
            # when nothing was there (O_EXCL), so tolerance costs nothing.
            # R23b: through the one opener, so a FIFO answers at once. The
            # descriptor outranks the lstat: a regular file swapped for
            # something else in between is "other".
            try:
                state = normalize_state(json.loads(read_regular_text(path)))
            except NotRegularFile:
                state = default_state()
                if found != "link":
                    found = "other"
            except (OSError, ValueError):
                state = default_state()
            created = init_state_file(path, state)
            emit({"ok": True, "kind": "state", "action": action, "found": found, "created": created,
                  "state": public_state(state)})
            return EXIT_OK
        # R22a: every other verb, the read-only `show` and `source list`
        # included -- an empty listing of a file that could not be read would
        # be a false statement about it. R24b: through the link to its target
        # when state.json is a symlink to a regular file, and refused when it
        # is one to anything else (state_file_target).
        target = state_file_target(path)
        state = read_state_strict(target)
        if action == "favorite":
            key = str(args.id or "").strip()
            if not key:
                raise HelperError("usage", "favorite needs a channel id")
            if args.op == "add":
                if key not in state["favorites"]:
                    state["favorites"].append(key)
            else:
                state["favorites"] = [item for item in state["favorites"] if item != key]
            write_state_file(path, target, state)
        elif action == "clear-recents":
            state["recents"] = []
            write_state_file(path, target, state)
        elif action == "source":
            now = int(args.now) if getattr(args, "now", 0) else int(time.time())
            if args.op == "add":
                extra["key"] = add_source_record(state, args.url, args.epg_url, args.label, args.origin, now)
                write_state_file(path, target, state)
            elif args.op == "update":
                extra["key"], extra["replacedKey"] = update_source_record(state, args.key, args.url, args.epg_url, args.label, now)
                write_state_file(path, target, state)
                # D-SRC-11: the write happened, and for the active source the
                # shell owns what was written. Say so on stderr AND in the
                # payload, so neither a human nor a script can read "ok": true
                # as "this stuck". Only after the write succeeds: a HelperError
                # above leaves the record alone and there is nothing to warn
                # about.
                # argparse's dest is DERIVED from the flag rather than written
                # out a second time, because two spellings of one name is how a
                # join stops being checked (rule 13). And `getattr` is called
                # with no default on purpose: if the flag is ever renamed, this
                # raises instead of quietly deciding the flag was not passed and
                # dropping the warning, which is the failure that would be
                # invisible.
                asked = [field for field, flag, _setting, _human in SETTING_OWNED_SOURCE_FIELDS
                         if getattr(args, flag.lstrip("-").replace("-", "_")) is not None]
                notes = setting_owned_warnings(asked)
                if notes:
                    extra["warnings"] = notes
                    for note in notes:
                        log("state source update: %s" % note)
            elif args.op == "remove":
                extra["removed"] = remove_source_record(state, args.key)["key"]
                write_state_file(path, target, state)
        payload: dict[str, Any] = {"ok": True, "kind": "state", "action": action}
        payload.update(extra)
        payload["state"] = public_state(state)
        emit(payload)
        return EXIT_OK
    except HelperError as error:
        log("state: %s" % error.message)
        emit(error_payload("state", error, action=action, **extra))
        return EXIT_ERROR


