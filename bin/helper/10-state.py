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


def stored_text(value: Any) -> str:
    """Model.storedText (D-STATE-6): what a file's text field reads as -- a
    JSON string, or nothing. str() turned a number, a boolean, an array or
    an object into text Python's way and the model's str() into other text
    (1.0 was "1.0" here and "1" there, True and "true", ['news'] and
    "news"), so the two state readers disagreed about a hand-edited file.
    The shared state-text-fields fixture (dev branch) runs both."""
    return value if isinstance(value, str) else ""


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
    key = raw.strip(URL_SPACE_CHARS)  # D-STATE-2: Model.activeKeyText's class
    return key if SOURCE_KEY_RE.match(key) else ""


# Must match the model's MAX_SAVED_SEARCHES / MAX_SAVED_TERMS / MAX_SAVED_QUERY and
# savedSearchTerms / savedSearchRecord. One shared fixture runs both.
MAX_SAVED_SEARCHES = 20
# Mirror of Model.MAX_HIDDEN_GROUPS (M3-01); the hidden-groups fixture on the
# dev branch pins both readers to the same list on the same bytes.
MAX_HIDDEN_GROUPS = 200


def normalize_hidden_groups(raw: Any) -> list[str]:
    """Mirror of Model.hiddenGroupList: strings only, stripped of
    URL_SPACE_CHARS, the reader's class (D-STATE-2: Model.stripSpace's, which
    takes off what either engine's own strip ever took, so a name any earlier
    writer stored reads as the group it hid), non-empty, first occurrence
    wins, capped at MAX_HIDDEN_GROUPS. Anything else -- a number, a dict, a
    non-list -- reads as nothing rather than failing."""
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    seen: set[str] = set()
    for item in raw:
        if len(out) >= MAX_HIDDEN_GROUPS:
            break
        if not isinstance(item, str):
            continue
        name = item.strip(URL_SPACE_CHARS)
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out
MAX_SAVED_TERMS = 8
MAX_SAVED_QUERY = 64


def saved_query_cut(query: Any) -> str:
    """A saved query's cut, Model.savedQueryCut's mirror (D-STATE-3): at most
    MAX_SAVED_QUERY UTF-16 units, as the model counts, never inside a pair,
    and with a high surrogate taken off the end of what is left. This side
    cut by code points, so the two readers kept different text past the
    Basic Multilingual Plane; and the model's cut could leave half a pair,
    which a file may still hold and which no write of this helper's can
    encode."""
    text = truncate_utf16(str(query or ""), MAX_SAVED_QUERY)
    if text and 0xD800 <= ord(text[-1]) <= 0xDBFF:
        text = text[:-1]
    return text


def saved_search_terms(query: Any) -> list[str]:
    text = normalize_text(saved_query_cut(query))
    if not text:
        return []
    return text.split(" ")[:MAX_SAVED_TERMS]


def normalize_saved_search(entry: Any) -> dict[str, Any] | None:
    # D-STATE-6: a query that is not a string is no search, as
    # Model.savedSearchRecord reads it (stored_text's rule).
    if not isinstance(entry, dict) or not isinstance(entry.get("query"), str):
        return None
    query = saved_query_cut(entry.get("query"))
    if not saved_search_terms(query):
        return None
    # coerce_int, NOT int(): the shared fixture is what forced it, because the
    # model reads "12.9" as 12 and int("12.9") raises.
    return {"query": query, "at": coerce_int(entry.get("at"))}


# D-SINK-111 (the owner's decision of 2026-11-16, the owner's own and not the
# standing authority): a channel id 0.18.0 or earlier made from a tvg-id
# holding a credential -- `t:qqqqqq:zzzzzz@cdn.test`, 0.17.0's `t:http://...`
# -- is DELETED on load from favorites and from the recents, last-played and
# session records, by both state readers (Model.parseState is the mirror,
# held to the shared withheld-ids fixture): channel_id_withheld, the tvg-id
# rule over the id's tail, and nothing else. No current parse makes such an
# id (the row takes an `n:` or `u:` id), so the guide never named it and the
# user could not remove it; nothing reachable is lost. The file loses it at
# the next save, which every state verb that writes makes.
def normalize_played(entry: Any) -> dict[str, Any] | None:
    # D-STATE-6: an id is a string or the record is none, and a name is a
    # string or empty (stored_text), as Model.loadedPlayedRecord reads them.
    if not isinstance(entry, dict):
        return None
    cid = stored_text(entry.get("id"))
    if not cid or channel_id_withheld(cid):
        return None
    return {"id": cid, "name": stored_text(entry.get("name")),
            "at": coerce_int(entry.get("at"))}


# D-STATE-4: the one spelling a stored integer's string may take, after the
# reader's class is off its ends. The model's STORED_DECIMAL (model/state.mjs).
_STORED_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
# And no longer than this: the model's STORED_TEXT_MAX. V4's Number()
# reads any string over 16,384 characters as NaN. Only ASCII passes the
# grammar, so a length here is the same number in either runtime's units.
_STORED_TEXT_MAX = 64


def coerce_int(value: Any) -> int:
    """Mirror of storedInt (model/state.mjs): what a stored integer reads
    as, on both sides, with one fixture (played-records.json).

    D-STATE-1: this used to be `int(x)`, which accepts only a plain integer
    literal and RAISES on everything else -- so `"12.9"` stored 0 where the
    guide read 12, and `"1e3"` stored 0 where the guide read 1000. Found by
    the saved-search fixture, which carried `at: "12.9"` for its own key and
    went red on a key it was not written for.

    D-STATE-4: the fix for that was float() and then int(), whose docstring
    said float() bought the whole JavaScript numeric grammar. It bought Python's:
    "1_000" and other scripts' digits parsed here and nowhere in the shell,
    "0x10" and a one-element array parsed in the shell and not here, and an
    infinite number (1e400, "Infinity", "inf"), which float() reads as an
    infinite float, raised OverflowError in int(), which the except, for TypeError
    and ValueError only, did not catch, so every `state` verb that reads the file, and the `failed`
    verb, ended `internal`. Neither
    engine's Number() is one grammar either (storedInt's comment says how), so
    the two sides now share an explicit one. A JSON number is its value and a
    boolean 1 or 0; a string is read only as a decimal literal of at most
    _STORED_TEXT_MAX characters once URL_SPACE_CHARS is off its ends; the
    answer is truncated TOWARD ZERO, as
    Math.trunc does, so `-3.7` is -3 and not -4; and everything else, or
    anything not finite, is 0. float() of an int is the double JSON.parse
    reads the same digits as, so an int past 2**53 rounds alike on both sides.
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except OverflowError:
            return 0
    elif isinstance(value, str):
        text = value.strip(URL_SPACE_CHARS)
        if len(text) > _STORED_TEXT_MAX or not _STORED_DECIMAL.fullmatch(text):
            return 0
        number = float(text)
    else:
        return 0
    return int(number) if math.isfinite(number) else 0


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
    label = cap_code_points(sanitize_input(stored_text(raw.get("label")), MAX_SOURCE_URL), MAX_LABEL) or derive_label(playlist["url"], playlist["kind"])
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
            key = stored_text(item)  # D-STATE-6
            if key and key not in state["favorites"] and not channel_id_withheld(key):
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
    # D-STATE-4: through coerce_int, as Model.parseState reads it through
    # storedInt; `==` read the string "2" as no layout where the shell read 2.
    state["cacheLayout"] = CACHE_LAYOUT if coerce_int(raw.get("cacheLayout")) == CACHE_LAYOUT else 0
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
            state["sources"].append(record)
        # D-SINK-100 (2026-11-16, round 2 of the security review; the lead's
        # call under the owner's standing authority of 2026-11-09): placed in
        # a second pass, against EVERY typed label in the list wherever it
        # is listed and every label placed before it, raw and as it reads
        # (label_keys), so a stored derived label listed before a typed one
        # that reads alike becomes `<host> 2` once, at the next load, as
        # Model.parseState places it. Two typed labels stored alike stay
        # alike until one is edited. One reading a label, so O(n) a load.
        keys = label_keys([item["label"] for item in state["sources"] if item.get("labelCustom")])
        for record in state["sources"]:
            if not record.get("labelCustom"):
                record["label"] = unique_label_over(derive_label(record["url"], record["kind"]), keys)
                label_keys_add(keys, record["label"])
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


def check_custom_label(cleaned: str, others: list[str], stored: str | None = None) -> str:
    """A label the user typed (Model.validateLabel): refused over MAX_LABEL
    code points (label_too_long, never cut, SR22) and when another source
    has it case-insensitively (label_taken); never rewritten (UX 5.6).
    D-SINK-100 (2026-11-16): also label_taken when it READS as another
    source's label reads (label_sink_text), unless it is the record's own
    `stored` label left unchanged on an edit (Model.selfStoredLabel's
    exemption): two records may already read alike, stored before this or
    by a 0.19 helper, and an edit that keeps its label is never refused.
    The sentence quotes the label as the Sources list reads it
    (D-SINK-108)."""
    custom = sanitize_input(cleaned, MAX_SOURCE_URL)
    if len(custom) > MAX_LABEL:
        raise HelperError("label_too_long", "label longer than %d characters" % MAX_LABEL, field="label")
    raw, read = label_keys(others)
    reads = label_read_key(custom)
    unchanged = stored is not None and custom == sanitize_input(stored, MAX_SOURCE_URL)
    if custom.lower() in raw or (not unchanged and reads != "" and reads in read):
        raise HelperError("label_taken", "a source named '%s' already exists" % label_sink_text(custom), field="label")
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
        raise HelperError("duplicate", "already in the source history as '%s'" % label_sink_text(existing["label"]), key=existing["key"])
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
                raise HelperError("duplicate", "already in the source history as '%s'" % label_sink_text(other["label"]), key=other["key"])
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
            record["label"] = check_custom_label(cleaned, others, record["label"])
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


# D-STATE-5: what the shell takes off state.json's two ends before it parses
# it -- its engine's own trim (Model.parseJsonObject; Qt's V4: ECMAScript's
# WhiteSpace and LineTerminator, and U+0085), which is the reader's class
# less U+001C..U+001F. json.loads takes the four JSON whitespace characters
# there and nothing else, so a file an editor saved with a byte-order mark,
# or one ending in a no-break space, loaded in the guide while every state
# verb that reads the file answered state_unreadable and `init` read it as an
# empty state. The shared state-edges fixture (dev branch) holds this list,
# Model.parseState in node and in V4, and the verbs to one answer. Nothing
# inside the text is touched, and a U+001C..U+001F at an edge is refused, as
# the shell reads such a file as unparsed.
STATE_EDGE_CHARS = "".join(char for char in URL_SPACE_CHARS if not "\x1c" <= char <= "\x1f")


def state_json(text: str) -> Any:
    """state.json's text parsed as the shell parses it: STATE_EDGE_CHARS off
    both ends, then json_decode. Raises ValueError as json_decode does."""
    return json_decode(text.strip(STATE_EDGE_CHARS))


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
        raw = state_json(text)
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
    sealed stub) [2026-11-14, D-SINK-103: about 250 ms of CPU, measured,
    not the ~30 ms this said, so the window was about a quarter of a
    second; the file is now made 0600 BEFORE every write by `state
    private`, and this repair is the second layer]. Both repairs are chmod_if_kind: an
    O_PATH descriptor, the KIND checked on the inode (a directory at the
    file's path, a link to nothing, a FIFO: untouched), and no chmod at all
    when the mode is already right -- so in the steady state this raises no
    IN_ATTRIB on the file the shell watches. The one bounded reply says
    what changed; a chmod that does fire raises one reload of the base
    text, which the service ignores (Model.reloadDisposition, unchanged)."""
    return {"folder": "changed" if chmod_if_kind(directory, 0o700, stat.S_ISDIR) else "kept",
            "file": "changed" if chmod_if_kind(path, 0o600, stat.S_ISREG) else "kept"}


# D-STATE-9 (2026-11-21): the most links the walk below follows -- QSaveFile's
# own bound, measured on qt6-base 6.12.0-3 (the spike's chain127 and chain128
# cases): a literal reading of 127 links reaches its file, and at 128 it stops
# and writes over the PATH itself, replacing the link at it (a loop on the
# literal reading included). The kernel's MAXSYMLINKS (ELOOP past 40) bounds
# one resolution of its own, not this walk: a literal reading can take 41 or
# 127 links where the kernel takes 2 and still end at the kernel's file
# (corrected by the review of 2026-11-21, which measured it; this said 40).
STATE_LINK_HOPS = 127


def qt_clean_path(path: str) -> str:
    """QDir::cleanPath on Unix, as the installed Qt computes it, ported step
    by step from its qt_normalizePathSegments (Qt 6's modified RFC 3986
    "remove dot segments", for a local path) because its corners are not
    posixpath.normpath's: a `..` with nothing before it is KEPT, above the
    root too (`/a/../../b` is `/../b`, where normpath answers `/b`), and
    removing a segment back to the root skips one slash only, so
    `/.//a/` is `//a`. Then the trailing slash goes, but the root's. A
    backslash is a character, not a separator, and nothing is asked of the
    filesystem, so no link is resolved. Held to Qt 6.12.0 by the shared
    qt-clean-path fixture (dev branch), QDir::cleanPath's own answers
    written by the D-STATE-9 spike's probe and run by the python suite:
    the Qt source is not on this machine, so the port is held to the
    library's answers, not its text."""
    if path == "":
        return ""
    text = path
    size = len(text)
    root = 1 if text.startswith("/") else 0
    # Is there a `.` or `..` segment, or a doubled slash, at all?
    at, after_slash = root, True
    while at < size:
        if after_slash and text[at] == ".":
            if at + 1 == size or text[at + 1] == "/":
                break
            if text[at + 1] == "." and (at + 2 == size or text[at + 2] == "/"):
                break
        if after_slash and text[at] == "/" and at > 0:
            at -= 1
            break
        after_slash = text[at] == "/"
        at += 1
    if at < size:
        out = list(text[:at])
        start, read = root, at
        while True:
            if read < size and text[read] == "/":
                out.append("/")
                read += 1
                while read < size and text[read] == "/":
                    read += 1
            kind = ""
            if read < size and text[read] == ".":
                if read + 1 == size or text[read + 1] == "/":
                    kind = "."
                elif text[read + 1] == "." and (read + 2 == size or text[read + 2] == "/"):
                    kind = ".."
            if kind == "":
                while read < size and text[read] != "/":
                    out.append(text[read])
                    read += 1
            elif kind == ".." and len(out) == start:
                # Nothing to climb out of: kept, and the root moves past it.
                out.extend("..")
                if read + 2 != size:
                    out.append("/")
                    read += 1
                start = len(out)
                read += 2
            else:
                if kind == "..":
                    if len(out) > start:
                        out.pop()
                    while len(out) > start and out[-1] != "/":
                        out.pop()
                    read += 2
                else:
                    read += 1
                if read != size and len(out) > start and out[-1] == "/":
                    out.pop()
                if len(out) == start:
                    if read != size and text[read] == "/":
                        read += 1
                    while root == 0 and read != size and text[read] == "/":
                        read += 1
            if read >= size:
                break
        text = "".join(out) or "."
    if len(text) > 1 and text.endswith("/"):
        text = text[:-1]
    return text


def qt_link_literal(path: str) -> str | None:
    """The file QSaveFile -- the FileView's atomic writer -- writes for
    `path`: its LITERAL reading of the links there (D-STATE-9). While what is
    at the current path is a symbolic link, its target replaces it, a
    relative one joined to the current path's folder AS TEXT (everything
    before its last `/`) and the whole cleaned with qt_clean_path; the first
    path is made absolute and cleaned the same way (QFileSystemEngine's
    absoluteName). So a `..` climbs out of the folder the TEXT names, where
    the kernel climbs out of the folder that folder really is: through a
    linked folder they differ. A target is decoded as UTF-8, an invalid byte
    read as U+FFFD, as QFile::decodeName reads it. Measured, not read: the
    Qt source is not on this machine, and the spike's driver asserts for
    every case that this names the file the installed QSaveFile wrote.
    -> that path (it may not exist; nothing at it, or a folder missing on
    the way, ends the walk as it ends QSaveFile's); `path` itself, as given
    and made absolute, while a link is still there after STATE_LINK_HOPS
    links, because QSaveFile then writes over the path, replacing its link
    (measured: chain128, loop); or None where a link cannot be read."""
    current = qt_clean_path(os.path.join(os.getcwd(), path))
    hops = 0
    while True:
        try:
            if not stat.S_ISLNK(os.lstat(current).st_mode):
                return current
        except OSError:
            return current
        if hops == STATE_LINK_HOPS:
            return os.path.join(os.getcwd(), path)
        hops += 1
        try:
            target = os.readlink(os.fsencode(current)).decode("utf-8", "replace")
        except OSError:
            return None
        if not target.startswith("/"):
            target = (current.rpartition("/")[0] or "/") + "/" + target
        current = qt_clean_path(target)


def state_link_entry(folder: str, name: str) -> tuple[tuple[int, int], str] | None:
    """One directory entry, as a writer that renames onto it sees it: the
    folder by its (st_dev, st_ino) and the name in it. What is at the name
    is not part of it: a rename replaces the entry whatever file it held
    (the review of 2026-11-21; the file's identity was compared here, and a
    hard link passed). None when the folder cannot be read as a folder
    (missing, not one, not searchable: the name is looked up in it, and only
    a name with nothing there is an answer)."""
    try:
        held = os.stat(folder)
    except OSError:
        return None
    if not stat.S_ISDIR(held.st_mode):
        return None
    try:
        os.stat(os.path.join(folder, name))
    except FileNotFoundError:
        pass
    except OSError:
        return None
    return (held.st_dev, held.st_ino), name


def state_link_split(path: str) -> bool:
    """True when state.json is a symbolic link that QSaveFile would save to
    a different file than the kernel -- and so the FileView's read, the
    helper and every other program -- reads (D-STATE-9): a relative target
    that climbs with `..` out of a linked folder, at any hop of a chain, or a
    target that is not UTF-8 (QSaveFile reads an invalid byte as U+FFFD and
    writes the file of that name, measured: nonutf8). The two answers are
    compared as directory ENTRIES, never as strings: qt_clean_path
    resolves no link and the kernel resolves every one, so a link inside a
    linked state folder, or an absolute target through a linked folder
    (~/Sync -> /mnt/data/Sync), names the same file by two strings. What is
    compared is the ENTRY a rename replaces: the folder (by st_dev and
    st_ino, so a bind mount of it is the same folder) and the name in it.
    Two names of one inode are two entries, in two folders or in ONE:
    QSaveFile's rename would replace the one and leave the other, which the
    plugin reads, holding the old text (measured, the spike's hardlink and
    hardlink2). So a different name is a different entry, always [the
    review of 2026-11-21: this let a second name in the same folder pass
    when it named the same inode, for a case-folding filesystem, and a hard
    link there was saved past]. The cost, stated: on a case-folding
    filesystem, two spellings of one name that the two readings end at are
    refused too, where they are one entry; the readings can end in two
    spellings only after they have gone through different links (not
    measured: such a filesystem needs root to make).
    False when there is no link at the path, and when the kernel cannot
    resolve it either (a loop, a folder that cannot be searched): the
    verbs' own answers name those (`link`, `unreachable`). True when a link
    on the literal walk cannot be read, when no folder is at its end, which
    QSaveFile cannot open (`open failed: No such file or directory`,
    measured), because then no save reaches the file the plugin reads
    either, and when the walk passes STATE_LINK_HOPS, because QSaveFile then
    writes over the path's own entry, a link, which is never the entry the
    kernel reads."""
    try:
        if not stat.S_ISLNK(os.lstat(path).st_mode):
            return False
    except OSError:
        return False
    try:
        os.stat(path)
        kernel = os.path.realpath(path, strict=True)
    except FileNotFoundError:
        kernel = os.path.realpath(path)
    except OSError:
        return False
    read = state_link_entry(os.path.dirname(kernel), os.path.basename(kernel))
    if read is None:
        return False
    literal = qt_link_literal(path)
    if literal is None:
        return True
    written = state_link_entry(literal.rpartition("/")[0] or "/", literal.rpartition("/")[2])
    if written is None:
        return True
    return written != read


# undo_state_private_create's reason when the inode it created is no longer
# empty: another program wrote into it in place (a `cp` of a backup onto
# the name opens it with O_TRUNC and writes into the SAME inode), and
# those bytes are not ours to remove (the recheck of D-SINK-103,
# 2026-11-15).
STATE_PRIVATE_WRITTEN = "written"


def state_private_refusal(why: str, reason: str = "", created: tuple[str, str] = ("", "")) -> HelperError:
    """The one sentence `state private` refuses with (D-SINK-103): what it
    found, never the path, and that nothing may be written. `why` is a fixed
    word the service's journal line carries (Model.statePrivateReply).
    `created`, only on a refusal after the run created the file itself, is
    what became of that file (undo_state_private_create's answer):
    "removed", or "left" -- a fixed word in the reply's `created`, and a
    clause of the sentence, which never names the path either."""
    sentences = {
        "not-a-file": "state.json is not a regular file",
        "not-owned": "state.json belongs to another account",
        "unreachable": "state.json could not be reached (%s)" % (reason or "error"),
        "unconfirmed": "state.json could not be made private (%s)" % (reason or "error"),
        # D-STATE-9: the shell's writer reads the link as text, so its save
        # would land in a file the plugin never reads back.
        "split-link": "state.json is a symbolic link that the shell would save to a different file than the one it reads (a target on the way climbs with .. out of a folder that is itself a symbolic link, or is not UTF-8)",
    }
    word, failure = created
    if failure == STATE_PRIVATE_WRITTEN:
        left = "; the file it created was left, because something was written into it"
    elif failure:
        left = "; the empty file it created was left, because it could not be removed (%s)" % failure
    else:
        left = "; the empty file it created was left, because the path no longer names it"
    tails = {
        "": "",
        "removed": "; the empty file it created was removed",
        "left": left,
    }
    extra: dict[str, Any] = {"why": why}
    if word:
        extra["created"] = word
    return HelperError("state_not_private", sentences[why] + "; nothing may be written to it" + tails[word], **extra)


class StatePrivateMade:
    """The file `state private` CREATED, for undo_state_private_create:
    an O_PATH descriptor on the folder it was created in, its name there,
    and the (st_dev, st_ino) of the created inode, read off the creating
    descriptor itself."""

    def __init__(self, folder_fd: int, name: str, identity: tuple[int, int]) -> None:
        self.folder_fd = folder_fd
        self.name = name
        self.identity = identity


def undo_state_private_create(made: StatePrivateMade) -> tuple[str, str]:
    """Remove the empty file `state private` created, when the run refuses
    after creating it (the claims check of D-SINK-103, 2026-11-14): left
    there, the next start reads it as not a valid state, the no-write mode,
    for a file nobody but this run made. Removed only while the name still
    names THAT inode -- an lstat at the folder the file was created in (no
    link at the name is followed, and the folder is the one held open since
    the create, so a re-pointed folder link does not move the removal) whose
    st_dev and st_ino are the creating descriptor's -- AND that inode is
    still empty. Anything else at the name -- a file another writer renamed
    over it, a link, nothing -- is left as it is, and so is the run's own
    inode once something has been written into it in place (a `cp` of a
    backup onto the name truncates and writes the same inode; the recheck of
    2026-11-15 lost such a backup to the identity test alone). -> (word,
    reason): ("removed", ""), ("left", "") when the name no longer names
    it, ("left", STATE_PRIVATE_WRITTEN) when the inode holds bytes,
    ("left", strerror) when the lstat or the unlink failed. What no syscall
    closes: a replacement, or an in-place write, landing between this lstat
    and the unlink, which takes an account that can write that folder or
    that file -- this one, over a file the plugin made a moment ago, or
    another, whose write to a folder it can write is not defended anyway
    (D-SINK-103's row)."""
    try:
        st = os.stat(made.name, dir_fd=made.folder_fd, follow_symlinks=False)
    except FileNotFoundError:
        return "left", ""
    except OSError as error:
        return "left", error.strerror or type(error).__name__
    if (st.st_dev, st.st_ino) != made.identity:
        return "left", ""
    if st.st_size != 0:
        return "left", STATE_PRIVATE_WRITTEN
    try:
        os.unlink(made.name, dir_fd=made.folder_fd)
    except FileNotFoundError:
        return "left", ""
    except OSError as error:
        return "left", error.strerror or type(error).__name__
    return "removed", ""


def state_private_open(path: str) -> tuple[int, str, StatePrivateMade | None]:
    """The descriptor `state private` judges, and what it did to get it:
    "found" for a file already at the path (through a link, as the FileView
    writes through one), "created" for one it created 0600 and empty
    because nothing was there. An O_PATH descriptor opens no FIFO and needs
    no permission on its target, so a 0000 file of ours is still repaired
    (chmod_if_kind's reasoning). Nothing at the path, or a link to nothing:
    the file is created with O_EXCL and O_NOFOLLOW at what the link names --
    a name another writer takes in between is opened instead, never written
    through -- with no folder created on the way (a missing folder is
    `unreachable`, which the FileView's own write would have made 0755).
    The third value is what it created (StatePrivateMade, its folder held
    open) or None; the caller closes it, and undoes the create if it
    refuses."""
    try:
        return os.open(path, os.O_PATH | os.O_CLOEXEC), "found", None
    except FileNotFoundError:
        pass
    except OSError as error:
        raise state_private_refusal("unreachable", error.strerror or type(error).__name__)
    target = os.path.realpath(path) if os.path.islink(path) else path
    folder, name = os.path.split(target)
    try:
        # The folder by descriptor, so the removal of what this creates is
        # made in the folder it was created in (undo_state_private_create).
        folder_fd = os.open(folder or ".", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    except OSError as error:
        raise state_private_refusal("unreachable", error.strerror or type(error).__name__)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600,
                     dir_fd=folder_fd)
    except FileExistsError:
        os.close(folder_fd)
        try:
            return os.open(path, os.O_PATH | os.O_CLOEXEC), "found", None
        except OSError as error:
            raise state_private_refusal("unreachable", error.strerror or type(error).__name__)
    except OSError as error:
        os.close(folder_fd)
        raise state_private_refusal("unreachable", error.strerror or type(error).__name__)
    # The umask can only narrow 0600 (a 0277 umask gives 0400, which
    # QSaveFile refuses to replace): the mode is set and read back below,
    # on the descriptor this returns, like any file found there.
    try:
        st = os.fstat(fd)
    finally:
        os.close(fd)
    made = StatePrivateMade(folder_fd, name, (st.st_dev, st.st_ino))
    try:
        return os.open(path, os.O_PATH | os.O_CLOEXEC), "created", made
    except OSError as error:
        undone = undo_state_private_create(made)
        os.close(folder_fd)
        raise state_private_refusal("unreachable", error.strerror or type(error).__name__, created=undone)


def state_private(path: str) -> dict[str, Any]:
    """`state private` (D-SINK-103, 2026-11-14): make state.json private
    BEFORE the service writes it, and say so only once it is.

    Why before. The service writes state.json through Quickshell's FileView
    with atomicWrites, which is Qt's QSaveFile, and QSaveFile gives the new
    file the mode the OLD one had: measured on Quickshell 0.3.2 / Qt 6.12.0
    under gdb (QA-RESULTS "D-SINK-103", dev branch), the text is written into
    an unnamed O_TMPFILE created 0600 in the TARGET's folder (through a
    link, the folder the link points into), fchmod-ed to the old file's
    mode -- read when the write opens -- linked under a temporary name and
    renamed over the target. Over a 0644 file, the temporary is 0644 from
    the link to the rename and the file 0644 after it, holding the new text
    either way; with nothing there, the mode is the umask's (0644 at 022).
    Over a 0600 file nothing is ever wider than 0600. So this makes the file
    0600 (creating it 0600 and empty when nothing is there), and the service
    writes only on this reply; `state mode` after the save stays, as the
    second layer.

    Refused, exit 1, nothing changed: a target that is not a regular file
    (`not-a-file`: a directory, a FIFO), one another account owns
    (`not-owned`: a chmod would fail anyway, and the rename would put our
    text in its folder), one that cannot be reached or created
    (`unreachable`) and a mode that could not be set or read back
    (`unconfirmed`). The FILE only: the state folder is left as it is --
    `state init` at every start and `state mode` after every landed save
    repair it, as before -- because a folder this run made writable would
    change what a 0500 folder does to the write that follows, and nothing in
    the folder is readable once the file and the writer's temporary are
    0600. Through a link, the folder the link points into is never touched.
    A refusal after this run CREATED the file removes what it created first,
    while the name it created (the path's, or what a link at the path names)
    still names that inode (undo_state_private_create), and says what
    became of it in the reply's `created`; so a filesystem that keeps its
    own modes leaves no empty state.json of this run's behind, unless
    something else took the name meanwhile (the claims check of
    D-SINK-103, 2026-11-14).
    Refused first, before anything is opened or changed (D-STATE-9,
    2026-11-21): a state.json link that the FileView's writer, QSaveFile,
    reads as TEXT to a different file than the kernel reads it
    (`split-link`, state_link_split): its save would land where nothing
    reads it back, and the 0600 this run makes, or the empty file it
    creates, would be the other file's. The lead's call under the owner's
    standing authority of 2026-11-09.
    -> {"file": "kept"|"changed"|"created"}"""
    if state_link_split(path):
        raise state_private_refusal("split-link")
    fd, how, made = state_private_open(path)

    def refuse(why: str, reason: str = "") -> HelperError:
        return state_private_refusal(why, reason, undo_state_private_create(made) if made is not None else ("", ""))

    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise refuse("not-a-file")
        if st.st_uid != os.geteuid():
            raise refuse("not-owned")
        changed = False
        if stat.S_IMODE(st.st_mode) != 0o600:
            try:
                os.chmod("/proc/self/fd/%d" % fd, 0o600)
            except OSError as error:
                raise refuse("unconfirmed", error.strerror or type(error).__name__)
            changed = True
        # Read back on the same inode: the reply is the mode the file HAS.
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode) != 0o600:
            raise refuse("unconfirmed", "mode %o" % stat.S_IMODE(st.st_mode))
    finally:
        os.close(fd)
        if made is not None:
            os.close(made.folder_fd)
    return {"file": "created" if how == "created" else ("changed" if changed else "kept")}


def cmd_state(args: argparse.Namespace) -> int:
    action = args.action
    if action in ("init", "mode", "private"):
        # FIRST, before the path is even named: everything after this can
        # touch a filesystem that hangs. `mode` runs after every landed save
        # against the same path, and `private` before every save
        # (D-SINK-103), so they have the same bound.
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
        if action == "private":
            # D-SINK-103: the file made 0600 before the service writes it;
            # the service writes only on this reply. Reads nothing.
            payload_private: dict[str, Any] = {"ok": True, "kind": "state", "action": action}
            payload_private.update(state_private(path))
            emit(payload_private)
            return EXIT_OK
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
            # D-STATE-9 (2026-11-21): a link the FileView's writer reads as
            # text to another file than the kernel does is named, as a link
            # to nothing is (`link`), so a start that cannot load the file
            # blocks with the sentence that fixes it. Nothing more is done
            # than for any link at the path: nothing is created through it
            # (O_EXCL meets the link), and the file the kernel names is made
            # 0600, which writes no text and narrows the file the plugin
            # reads. `state private` refuses every save over it.
            if found in ("file", "link") and state_link_split(path):
                found = "split-link"
            # The init reads tolerantly: what it read is only ever written
            # when nothing was there (O_EXCL), so tolerance costs nothing.
            # R23b: through the one opener, so a FIFO answers at once. The
            # descriptor outranks the lstat: a regular file swapped for
            # something else in between is "other".
            try:
                state = normalize_state(state_json(read_regular_text(path)))
            except NotRegularFile:
                state = default_state()
                if found not in ("link", "split-link"):
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


