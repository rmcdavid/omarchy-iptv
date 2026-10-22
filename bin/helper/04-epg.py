# A part of bin/omarchy-iptv (D-REL-7), not a module: the helper compiles
# this file into its own namespace in the order its HELPER_PARTS lists, so
# a part sees every name the parts before it define. Run the helper.
from __future__ import annotations
# ----------------------------------------------------------------- EPG

def parse_xmltv_time(raw: str | None, cache: dict[str, int | None]) -> int | None:
    """`20260912213000 +0100` -> epoch seconds. Missing offset means UTC.

    Shorter forms (YYYYMMDD, YYYYMMDDHH, YYYYMMDDHHMM) are padded with zeros.
    Returns None for anything unparseable. `cache` is keyed by the raw
    string because a feed repeats the same few thousand boundaries.
    """
    if not raw:
        return None
    if raw in cache:
        return cache[raw]
    match = _XMLTV_TIME.match(raw.strip())
    if not match:
        cache[raw] = None
        return None
    import calendar
    year, month, day, hour, minute, second = (int(match.group(index) or 0) for index in range(1, 7))
    try:
        ts = calendar.timegm((year, month, day, hour, minute, second, 0, 0, 0))
    except (ValueError, OverflowError):
        cache[raw] = None
        return None
    if match.group(7):
        offset = int(match.group(8)) * 3600 + int(match.group(9)) * 60
        ts -= offset if match.group(7) == "+" else -offset
    cache[raw] = ts
    return ts


def clean_field(text: str | None, limit: int) -> str:
    """Fold every run of whitespace and control characters to one space, trim,
    and cut at `limit` code points. A str is cut on a code-point boundary,
    never inside one, so the result is always encodable."""
    if not text:
        return ""
    return _CONTROL_WS.sub(" ", text).strip()[:limit]


def clean_title(text: str | None) -> str:
    return clean_field(text, EPG_MAX_TITLE)


def element_text(elem: Any) -> str:
    """Every run of text under an XMLTV element, children included.

    `elem.text` is only the text BEFORE the first child element, and that is
    what every field here used to read: `<desc>Hello <b>world</b> and
    more</desc>` arrived as "Hello" and the body of the synopsis was dropped
    with no warning and no count. XMLTV's DTD declares these fields as
    #PCDATA, so markup inside one is already malformed -- but a provider that
    ships it is not a hypothetical (the same feeds ship it ESCAPED, which
    arrives as text and was always kept in full), and losing the text is a
    worse answer than keeping it. Nothing is trusted by keeping it: the run
    goes to clean_field or clean_detail exactly as before, so it is folded,
    capped, URL-redacted and rendered as PlainText.
    """
    if elem is None:
        return ""
    return "".join(elem.itertext())


def clean_detail(text: str | None, limit: int) -> str:
    """clean_field plus URL redaction, for the M4-02 detail fields.

    These three fields (<desc>, <category>, <episode-num>) are
    provider-controlled text on its way to a renderer, like the channel name
    (D-TEXT-1) and the programme title before them, so they are a rule 5
    sink. Two things are true of them and neither is optional:

    - Any URL inside the text is reduced to scheme://host here, so no path,
      query or userinfo reaches the panel. Nothing else in the guide's markup
      is read: <icon src> and <url> children are never looked at, so no
      address enters a record except through this redaction.
    - The text is entity-DECODED by the XML parser, so `&lt;img src=...&gt;`
      arrives as real markup, and redaction leaves a fetchable
      `<img src="http://host">` (D-TEXT-1 measured exactly that). The guide
      renders every one of these fields as PLAIN TEXT -- `Text.PlainText` is
      the only stop, and the gate's text format guard (dev branch) fails on
      a Text that does not declare its format.

    The cap is applied on the way IN as well as on the way out, and the
    order of the three steps is a SECURITY property, not a preference. The
    rule is Model.epgDetailText's (the model, the JS mirror of this sink):
    REDACTION NEVER SEES A TRUNCATED URL. Cutting first and redacting second
    was what this function did until 2026-10-03, and it leaked the username:
    `http://user:pw@host/x` cut after `pw` is `http://user:pw`, which has no
    `@` left, so urlparse reads `user` as the host and redaction PUBLISHES
    IT -- into the panel, into epg-now.json and onto the accessibility bus.
    Measured at every cut offset of all three caps before the fix.

    The cut is still bounded, and the reason has CHANGED -- it used to be the
    cost. It was measured here on the shape that defeats the `://` guard
    (`a-a-a-...` plus one real URL): 1.2 ms at 400 code points and four times
    that for every doubling, 173 ms at 6,400, 694 ms at 12,800, which put a
    single 64 MiB description out of reach of any budget. F-SINK-11 made
    redaction linear, so that argument is gone and the bound now stands on what
    it should have stood on all along: the panel reuses a fixed geometry and
    the input is provider-controlled up to MAX_SOURCE_BYTES, so a description
    nobody can read is not worth carrying. The SPLIT stays for a reason the
    cost never touched: the text is cut at `limit`, and when that cut lands
    inside a token carrying `://` the whole token is dropped rather than handed
    to the redactor, because half a URL is what published the username above.
    A URL cannot contain whitespace (redact_urls' tail excludes it), so the
    only token the cut can ever have truncated is the last one, and dropping it
    costs a fragment that was unreadable anyway.

    What the caller sees: a value at most `limit` code points long -- at most,
    because redacting an unparseable URL GROWS the text ("[redacted]") and
    the final cut takes it back to the cap -- and usually shorter than the
    cap when the text carried URLs, by what the redaction removed.
    """
    text = _CONTROL_WS.sub(" ", text or "").strip()
    if len(text) > limit:
        cut = text[:limit]
        if text[limit] != " ":
            # The cut landed inside a token. Every run of whitespace is one
            # space by now, so rpartition finds the start of exactly that
            # token, and a token carrying "://" is a URL the redactor must
            # not be given half of.
            head, _, tail = cut.rpartition(" ")
            if "://" in tail:
                cut = head
        text = cut
    if "://" not in text:
        # The common case, and the hot one. redact_urls cannot rewrite text
        # without "://", so this guard changes no answer. It was worth 2.7 s of
        # a 6.3 s 48,000-programme fetch with a 600-character description on
        # every programme, back when the old pattern retried at every word
        # boundary and prose is all word boundaries; redact_urls takes the same
        # exit itself now (F-SINK-11), so this one is a call it does not make
        # rather than a stall it avoids. Kept: one `in` beats one call.
        return text
    return clean_field(redact_urls(text), limit)


def episode_ns_text(raw: str) -> str:
    """xmltv_ns `season.episode.part` -> "S1 E2".

    Every field is zero-based and may carry a "/total" tail or be empty.
    Season and episode are rendered one-based; part is dropped. A field that
    is not a plain number is dropped rather than guessed, so an unparseable
    system yields "" and the panel shows no episode line at all.
    """
    fields = raw.split(".")
    out = []
    for prefix, index in (("S", 0), ("E", 1)):
        if index >= len(fields):
            break
        number = fields[index].split("/")[0].strip()
        if number.isdigit():
            out.append("%s%d" % (prefix, int(number) + 1))
    return " ".join(out)


def episode_text(elem: Any) -> str:
    """The first readable <episode-num> of a programme, as text to render.

    Only the two systems XMLTV defines as an EPISODE NUMBER are rendered:
    `onscreen`, the number as shown to the viewer, preferred wherever it
    exists and taken as the provider wrote it; and `xmltv_ns`, the machine
    form, translated by episode_ns_text. An element with NO system attribute
    is taken as onscreen, which is the common shorthand.

    Every other system is an identifier or a date, not an episode number, and
    is ignored -- found by looking at the panel on real data rather than at a
    fixture. On the project's own XMLTV asset, `original-air-date` outnumbers
    `onscreen` 8,799 to 4,273 and comes FIRST in the element order, so taking
    "anything else as the provider wrote it" put a fourteen-digit timestamp
    (`20080101000000 +0000`) under the label "Episode" on 4,526 programmes;
    the same feed's `pluto` system is a 24-character hex id. A field the
    viewer cannot read is worse than no field, because the panel spends a
    line on it.
    """
    fallback = ""
    for child in elem.iterfind("episode-num"):
        system = (child.get("system") or "").strip().lower()
        if system in ("onscreen", ""):
            text = clean_detail(element_text(child), EPG_MAX_EPISODE)
            if text:
                return text
        elif system == "xmltv_ns" and not fallback:
            fallback = episode_ns_text(clean_field(element_text(child), EPG_MAX_EPISODE))
    return fallback


def programme_detail(elem: Any) -> dict[str, str]:
    """<desc>, the FIRST <category> and <episode-num> of a programme.

    Only the first category is kept: a provider that lists six genres would
    push six strings per programme into a window file the guide re-reads on
    every refresh, and the panel shows one line. "First" means the one the
    provider listed first -- XMLTV does not rank them, so neither do we.
    """
    detail: dict[str, str] = {}
    desc = elem.find("desc")
    if desc is not None:
        text = clean_detail(element_text(desc), EPG_MAX_DESC)
        if text:
            detail["desc"] = text
    category = elem.find("category")
    if category is not None:
        text = clean_detail(element_text(category), EPG_MAX_CATEGORY)
        if text:
            detail["category"] = text
    episode = episode_text(elem)
    if episode:
        detail["episode"] = episode
    return detail


def build_alias(channels_doc: Any) -> tuple[dict[str, Any] | None, int]:
    """-> (match index, playlist channel total), or (None, 0) with no cache.

    The index is what joins an XMLTV channel to a playlist channel. Every
    strategy answers with a playlist `tvgId`, because that is the key the
    window, epg-now.json and the guide's own lookup all use (Model.epgFields
    is reached through `row.tvgId`), so a channel matched by NAME still
    reaches its row with nothing changed downstream. Four maps, tried in
    this order by match_xmltv_channel, the later never overriding the earlier
    (D-EPG-2, the M4 plan (dev branch), M4-01 repairs 1 and 2, F-EPG-11):

      "exact"  the tvg-id as written, plus its lower-case form when that is
               free -- case-sensitive first, case-insensitive second, as
               shipped since M1.
      "addr"   the first EPG_ADDR_MAX_TOKENS distinct alphanumeric runs of at
               least EPG_ADDR_MIN_TOKEN characters in the row's STREAM URL,
               and only when a run
               belongs to exactly one playlist tvg-id. A guide channel whose
               id IS one of those runs is streamed by that row: the join is
               an exact equality between a whole guide id and a whole token
               of the address the row opens. Worth 185 of the 1,453
               installed channels -- a STREAM-field census, see
               EPG_MATCH_ADDR -- 40 of them reached by nothing else
               (F-EPG-11).

               The LOGO url is deliberately not indexed. It reaches 8 more
               rows and costs 0, because all 8 match by name anyway -- and 7
               of the 8 stream from a different distributor than the artwork
               (`images.pluto.tv` artwork on Amagi, CloudFront and Google
               DAI addresses), so indexing it would assert a stream identity
               on the strength of a hotlinked picture. Artwork provenance is
               not stream identity. Measured: matched 265 either way. The
               union of the two fields is 193 rows, and that union -- not
               this strategy's 185 -- is the number the round originally
               quoted here.

               Case-SENSITIVE, unlike "exact". A URL path is case-sensitive
               by the URL spec, so folding case would read an identity the
               address does not assert; and 0 of the 185 need the fold (every
               id in the guide is already lower case).
      "feed"   the id cut at the first "@", lower-cased. iptv-org writes
               tvg-id="Name.us@SD" where a guide may declare id="Name.us",
               and the reverse happens too, so every playlist id contributes
               its base whether or not it carries a suffix. Worth, as
               measured for D-EPG-2 across the published guide index: 735 of
               the installed 1,453 channels are covered by a guide under the
               bare id against 582 under channel@feed.
      "name"   the normalised channel name, and ONLY when that name belongs
               to exactly one playlist tvg-id. Precision is the acceptance
               criterion: a programme on the wrong channel is worse than a
               blank row, so an ambiguous name is dropped and counted, never
               guessed.

    Two known limits, both one-to-one consequences of the index answering
    with a single id. A playlist carrying `A.us@SD` and `A.us@HD` offers one
    base, so a guide declaring `A.us` lands on whichever came first in the
    playlist and the twin row stays blank (two rows sharing one tvg-id both
    match, because they share the key). And a channel with no tvg-id at all
    can never be matched by any strategy, name included, because there is no
    key to publish it under; `nameIndexed` counts only channels that have one.

    Size: "addr" is bounded by EPG_ADDR_MAX_TOKENS per row, so by
    MAX_CHANNELS * EPG_ADDR_MAX_TOKENS = 800,000 entries, and the cost is
    linear in address BYTES rather than in rows -- which is why that cap
    exists and why its comment carries the measurement at the caps rather
    than an argument. On the installed 1,453-channel list this map holds 719
    tokens; at the caps, 800,000 of them, about 7.5 s and a 178.8 MiB traced
    peak (about 12 s and 379.4 MiB without the cap, about 1.5 s and 20.0 MiB
    before ADDR existed).
    """
    if not isinstance(channels_doc, dict) or not isinstance(channels_doc.get("channels"), list):
        return None, 0
    exact: dict[str, str] = {}
    feed: dict[str, str] = {}
    # normalised name -> the one tvg-id that claims it, "" once two claim it.
    name_owner: dict[str, str] = {}
    name_rows: dict[str, int] = {}
    # The same discipline for addresses: address token -> the one tvg-id that
    # claims it, "" once two claim it. The name rule's reason applies
    # unchanged -- a programme on the wrong channel is worse than a blank row
    # -- and a token shared by two rows says nothing about which of them the
    # guide channel is.
    addr_owner: dict[str, str] = {}
    addr_rows: dict[str, int] = {}
    # bare name key -> the rows carrying it. A measurement, not a strategy.
    bares: dict[str, list[str]] = {}
    total = 0
    for channel in channels_doc["channels"]:
        total += 1
        if not isinstance(channel, dict):
            continue
        tvg = channel.get("tvgId")
        if not isinstance(tvg, str) or not tvg:
            continue
        if tvg not in exact:
            exact[tvg] = tvg
        base = tvg.split("@", 1)[0].lower()
        if base and base not in feed:
            feed[base] = tvg
        url = channel.get("url")
        if isinstance(url, str) and url:
            # `seen_tokens`: one row naming the same token twice is still one
            # claim, so `addr_rows[token]` counts ROWS and not occurrences,
            # exactly as `name_rows` does. The SUM of it does not -- see
            # `addr_dropped` below, which is the number the status reports.
            #
            # finditer and a break, not set(findall()): the cap has to be able
            # to stop reading a 60 KiB address, and findall materialises every
            # token of it before the cap could apply. Order inside one row
            # cannot change the outcome -- each distinct token is processed
            # once and the owner rule is commutative -- so reading in address
            # order rather than in set order changes nothing but the cap's
            # meaning, which is "the first EPG_ADDR_MAX_TOKENS of them".
            seen_tokens: set[str] = set()
            for match in _EPG_ADDR_TOKEN.finditer(url):
                token = match.group()
                if token in seen_tokens:
                    continue
                seen_tokens.add(token)
                addr_rows[token] = addr_rows.get(token, 0) + 1
                if token not in addr_owner:
                    addr_owner[token] = tvg
                elif addr_owner[token] != tvg:
                    addr_owner[token] = ""
                if len(seen_tokens) >= EPG_ADDR_MAX_TOKENS:
                    break
        # The row's bare name key, for addrNameConflicts and nothing else
        # (bare_name_key). A list, not an owner-or-blank: this is a
        # measurement and a key two rows share must not silently vanish from
        # it the way an ambiguous MATCH key has to.
        bare = bare_name_key(channel.get("name"))
        if bare:
            owners = bares.get(bare)
            if owners is None:
                bares[bare] = [tvg]
            elif tvg not in owners:
                owners.append(tvg)
        # The matcher's own key (epg_name_key), not the cached `nameKey`:
        # that one is the SEARCH key and keeps `(1080p)` in, which is exactly
        # what stops the guide matching. Computed from the name here, so an
        # older cache needs no refresh for this to work.
        key = epg_name_key(channel.get("name"))
        if not key:
            continue
        name_rows[key] = name_rows.get(key, 0) + 1
        if key not in name_owner:
            name_owner[key] = tvg
        elif name_owner[key] != tvg:
            # Ambiguous on OUR side. Two rows under one tvg-id are not: they
            # are one channel listed twice and they share the key.
            name_owner[key] = ""
    for tvg in list(exact):
        low = tvg.lower()
        if low not in exact:
            exact[low] = tvg
    names = {key: tvg for key, tvg in name_owner.items() if tvg}
    dropped = sum(rows for key, rows in name_rows.items() if not name_owner[key])
    addrs = {token: tvg for token, tvg in addr_owner.items() if tvg}
    addr_dropped = sum(rows for token, rows in addr_rows.items() if not addr_owner[token])
    index = {
        "exact": exact,
        "addr": addrs,
        "feed": feed,
        "name": names,
        # Counts the epg status reports. `nameIndexed` is normalised names
        # available for a name match (one per channel, since an indexed name
        # belongs to one id); `nameDroppedPlaylist` counts the CHANNELS whose
        # name was thrown away as ambiguous, not the names.
        "nameIndexed": len(names),
        "nameDroppedPlaylist": dropped,
        # The same two numbers for "addr", so the strategy is reportable and
        # not only assertable (rule 14). `addrIndexed` counts TOKENS, since a
        # row contributes as many as its address holds.
        #
        # `addrDroppedPlaylist` counts ambiguous token-CLAIMS. It is NOT the
        # row count its neighbour `nameDroppedPlaylist` is, and it is not
        # bounded by `channelTotal`: a row naming three ambiguous tokens
        # contributes three. On the owner's 1,453 rows it reports 301 over 70
        # ambiguous tokens spanning 281 distinct rows. The round that added it
        # described it as a row count in a test docstring and in the comment
        # above the loop; both were wrong and both are corrected. Counting
        # distinct rows EXACTLY would need either a row set per token or a
        # second scan of every address, and the per-address cost is the thing
        # EPG_ADDR_MAX_TOKENS exists to bound, so the number stays what it is
        # and says so here.
        "addrIndexed": len(addrs),
        "addrDroppedPlaylist": addr_dropped,
        # The country-qualifier-stripped name key of each row, for the ADDR
        # strategy's own contradiction counter. See `bare_name_key` and
        # parse_xmltv's `addrNameConflicts`: this is a MEASUREMENT surface and
        # no strategy reads it, which is why an ambiguous key is kept here
        # (as a list) instead of being dropped the way "name" drops one.
        "bare": bares,
    }
    return index, total


def match_xmltv_channel(index: dict[str, Any], cid: str,
                        guide_names: dict[str, str]) -> tuple[str, int]:
    """One XMLTV channel id -> (playlist tvgId, strategy rank), or ("", -1).

    `guide_names` is the XMLTV side's cid -> normalised display name, built by
    parse_xmltv; an entry is "" once the name is ambiguous among the guide's
    own declarations, which is the second half of the uniqueness rule.

    The ADDR strategy needs no guide-side uniqueness rule, unlike NAME. A
    name is a label and two guide channels may carry the same one; `cid` is
    the guide's own identity key and parse_xmltv already keeps one entry per
    id, so an address token resolves to one guide channel by construction.
    Two guide channels reaching one row is still possible across strategies
    and is still claim_channel's job.

    WHICH WINS, A CASE FOLD OR AN EXACT ADDRESS. The ID map has two halves and
    only the first is a declaration: `exact[tvg] = tvg` is what the playlist
    author wrote, and `exact[tvg.lower()] = tvg` (build_alias's post-pass) is
    a fold the matcher performs. Both are consulted here BEFORE "addr", so a
    case-folded tvg-id beats an exact-case address equality. Driven through
    the real verb: a row declaring tvg-id="ABCDEFGHIJKL" takes a guide
    channel declared `abcdefghijkl` even when a DIFFERENT row's address
    carries `abcdefghijkl` character for character.

    That order is kept, and "a declaration outranks a deduction" is NOT the
    reason -- the fold is a deduction, so that sentence justifies the
    exact-case half of this map and nothing more. The reason is what the two
    fields are FOR. `tvg-id` exists only to name a guide channel; a row
    carrying tvg-id="ABCDEFGHIJKL" has asserted which guide channel it is,
    and all the fold discards is the case of an identifier that XMLTV
    authors write inconsistently. A stream address exists to open a stream;
    a guide id appearing in it is an exact equality, but on a string nobody
    wrote as an identity assertion. The declared join field, folded, beats a
    deduction from a field that is not a join field at all.

    UNVERIFIED on the project's inputs: 0 of the frozen guide's 427
    declarations need the fold at all (every id in it is already lower case),
    so nothing measured here ranks the folded half against ADDR and the
    paragraph above is an argument. The ordering is nonetheless PINNED, in
    both directions, by
    test_a_case_folded_tvg_id_outranks_an_exact_case_address -- which the
    round that added ADDR left unpinned: taking the fold out of `exact` and
    consulting it after "addr" left the whole suite green. Moving only the
    `cid.lower()` LOOKUP is not that mutation and changes nothing, because
    the fold is written into `exact` itself and the line above already hits
    it; the test's own docstring records both.
    """
    exact = index["exact"]
    key = exact.get(cid) or exact.get(cid.lower())
    if key:
        return key, EPG_MATCH_ID
    key = index["addr"].get(cid)
    if key:
        return key, EPG_MATCH_ADDR
    base = cid.split("@", 1)[0].lower()
    if base:
        key = index["feed"].get(base)
        if key:
            return key, EPG_MATCH_FEED
    name = guide_names.get(cid)
    if name:
        key = index["name"].get(name)
        if key:
            return key, EPG_MATCH_NAME
    return "", -1


def source_key(url: str) -> str:
    import hashlib
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:16]


# The last epoch second that still fits ten digits: 2286-11-20T17:46:39Z.
#
# Ten digits is not a formatting preference, it is the record format's
# CONTRACT. The readers slice [0:10], [11:21] and [22:] rather than splitting,
# because bisect over fixed-width prefixes is what buys the 10,000-channel
# budget (see EPG_RECORD_SEP). But "%010d" sets a MINIMUM width and not a
# maximum, so a larger timestamp pushed the title into the number field and
# produced a line no JSON parser would accept -- and epg-now.json is written by
# concatenation, so ONE such programme cost every channel of that source its
# guide data, silently, while the helper exited 0 reporting ok:true. An
# eleven-digit stop was quieter and worse: valid JSON carrying a truncated
# stop, so the row showed as having nothing on.
#
# Feeds really do carry these. `99991231235959` is a common "runs forever"
# sentinel for 24/7 streams, and it is twelve digits.
#
# Clamping here makes the function total and keeps the invariant at the one
# place records are made, rather than asking three readers to defend against
# input their own format forbids.
EPG_MAX_EPOCH = 9999999999


def encode_record(start: int, stop: int, title: str, detail: dict[str, str] | None = None) -> str:
    """See EPG_RECORD_SEP. `start`/`stop` are clamped into the ten-digit range
    the record format requires; a stop past 2286 means "runs forever" and is
    truthfully represented by the furthest instant the format can hold.

    `detail` is the M4-02 panel data: every value is JSON-encoded here, so no
    caller ever hands this function a ready-made JSON fragment. Keys outside
    EPG_DETAIL_KEYS are ignored and an empty value is omitted, which is why a
    programme with no detail produces exactly the record it always did.
    """
    start = 0 if start < 0 else min(start, EPG_MAX_EPOCH)
    stop = 0 if stop < 0 else min(stop, EPG_MAX_EPOCH)
    # The title stays the FIRST thing at index 22, bare, exactly as it was
    # before M4-02: the detail members are appended after it, so a reader
    # that prepends '{"title":' gets a whole object and a detail-free record
    # is unchanged.
    body = json.dumps(title, ensure_ascii=False)
    if detail:
        for key in EPG_DETAIL_KEYS:
            value = detail.get(key)
            if value:
                body += ',"%s":%s' % (key, json.dumps(value, ensure_ascii=False))
    return "%010d %010d %s" % (start, stop, body)


def encode_records(items: list[tuple[int, int | None, str, dict[str, str]]]) -> tuple[str, int]:
    """Sort, infer missing stops, drop duplicates, cap, and pack a channel's
    programmes into the record string described at EPG_RECORD_SEP.

    An item is (start, stop or None, title, detail); the detail dict takes
    part in the duplicate check, so the same programme listed twice with and
    without a description keeps both -- the records differ, and choosing
    between them is not this function's decision to make.
    """
    items.sort(key=lambda item: item[0])
    records: list[str] = []
    last: tuple[int, int, str, dict[str, str]] | None = None
    count = len(items)
    for index, (start, stop, title, detail) in enumerate(items):
        if stop is None:
            stop = start + EPG_DEFAULT_DURATION
            for later in range(index + 1, count):
                if items[later][0] > start:
                    stop = items[later][0]
                    break
        if stop <= start or start < 0:
            continue
        current = (start, stop, title, detail)
        if current == last:
            continue
        last = current
        records.append(encode_record(start, stop, title, detail))
        if len(records) >= EPG_MAX_PER_CHANNEL:
            break
    return EPG_RECORD_SEP.join(records), len(records)


def claim_channel(claim: dict[str, tuple[int, str]], pending: dict[str, list[Any]],
                  key: str, rank: int, cid: str) -> int:
    """May `cid` (matched at strategy `rank`) own the playlist channel `key`?

    -> 1 when the claim is granted and this is the first grant, 0 when it was
    already held by the same guide channel at the same rank, -1 when it is
    refused. Two guide channels must never pour programmes into one row: with
    the name fallback in play the guide can reach one playlist channel by id
    and a DIFFERENT one by name, and merging them would interleave two
    schedules into one that is wrong everywhere.

    Resolution is by strategy, not by arrival: a stronger rank displaces a
    weaker claim and DISCARDS what it collected, so the answer does not
    depend on the order the guide happened to stream its channels in. Equal
    ranks are first-come, because nothing distinguishes them.
    """
    held = claim.get(key)
    if held is None:
        claim[key] = (rank, cid)
        return 1
    if held == (rank, cid):
        return 0
    if rank < held[0]:
        pending.pop(key, None)
        claim[key] = (rank, cid)
        return 1
    return -1


def parse_xmltv(stream: BinaryIO, now: int, index: dict[str, Any] | None) -> dict[str, Any]:
    """Stream-parse XMLTV into per-channel record strings for the window.

    `index` (from build_alias) restricts the result to playlist channels and
    maps XMLTV ids onto playlist tvg-ids by the three strategies of M4-01;
    None keeps every channel under its XMLTV id. Elements are released as
    soon as they are processed.

    The name strategy needs a channel's <display-name>, so the channel pass
    retains one: the first one A PLAYLIST CHANNEL CLAIMS, out of however many
    the provider listed (see the channel branch). A name no playlist channel
    claims can never match, so it is never stored.

    That makes the retained table proportional to the GUIDE and not to the
    playlist, which an earlier version of this docstring had backwards. The
    bound is one entry per guide <channel> whose name a playlist channel
    claims, and the ambiguity branch below writes an entry per colliding
    DECLARATION: measured against this function with a playlist of ONE name,
    a guide declaring that name 50,000 times reaches nameDroppedGuide 50,000
    and a traced peak of 4.8 MiB above the start, matching 0 rows. The hard
    bound on it is MAX_SOURCE_BYTES (64 MiB, on the download and on the
    inflated stream), not the playlist.

    A name is only usable while it is unique on the guide's side too, so the
    second declaration of a name blanks the first one's entry, REVOKES any
    claim and programmes the first one had already banked, and both are
    counted as dropped. Conforming XMLTV declares every <channel> before the
    first <programme> (the DTD orders them), so a conforming guide has its
    whole name table built before the first lookup. A guide that interleaves
    them instead still misses the programmes that arrive before their own
    declaration -- but it no longer GAINS a match the uniqueness rule
    forbids, which is what the revocation is for and what this paragraph
    claimed by omission until 2026-10-03. Id matching is unaffected either
    way.
    """
    import xml.etree.ElementTree as ET
    window_start = now - EPG_PAST_SECONDS
    window_end = now + EPG_FUTURE_SECONDS
    time_cache: dict[str, int | None] = {}
    pending: dict[str, list[tuple[int, int | None, str, dict[str, str]]]] = {}
    seen_ids: set[str] = set()
    # playlist key -> (strategy rank, the guide channel id that owns it).
    claim: dict[str, tuple[int, str]] = {}
    playlist_names: dict[str, str] = index["name"] if index is not None else {}
    guide_names: dict[str, str] = {}          # guide cid -> normalised name, "" when ambiguous
    guide_name_owner: dict[str, str] = {}     # normalised name -> the one cid that declares it
    guide_name_collided: set[str] = set()
    guide_names_dropped = 0
    # bare_name_key -> the guide cids that declare it, kept only for keys some
    # playlist row carries (bare_rows), so this table is bounded by the GUIDE
    # the same way guide_names is. Read once, after the parse, for
    # addrNameConflicts.
    bare_rows: dict[str, list[str]] = index["bare"] if index is not None else {}
    bare_guide: dict[str, set[str]] = {}
    channel_elements = 0
    bad_time = 0
    no_title = 0
    unknown = 0
    contested = 0
    total_programmes = 0
    root: Any = None
    try:
        for event, elem in ET.iterparse(EntityRefusingReader(stream), events=("start", "end")):
            if event == "start":
                if root is None:
                    root = elem
                continue
            tag = elem.tag
            if tag == "programme":
                total_programmes += 1
                cid = _CONTROL_WS.sub(" ", elem.get("channel") or "").strip()
                if index is None:
                    key, rank = cid, EPG_MATCH_ID
                else:
                    key, rank = match_xmltv_channel(index, cid, guide_names)
                if not key:
                    unknown += 1
                elif claim_channel(claim, pending, key, rank, cid) < 0:
                    contested += 1
                else:
                    seen_ids.add(key)
                    start = parse_xmltv_time(elem.get("start"), time_cache)
                    if start is None:
                        bad_time += 1
                    else:
                        stop = parse_xmltv_time(elem.get("stop"), time_cache)
                        effective_stop = stop if stop is not None else start + EPG_DEFAULT_DURATION
                        if effective_stop > window_start and start < window_end:
                            title_elem = elem.find("title")
                            title = clean_title(element_text(title_elem))
                            if title:
                                pending.setdefault(key, []).append(
                                    (start, stop, title, programme_detail(elem)))
                            else:
                                no_title += 1
            elif tag == "channel":
                channel_elements += 1
                cid = _CONTROL_WS.sub(" ", elem.get("id") or "").strip()
                if cid and cid not in guide_names:
                    # The FIRST <display-name> a playlist channel claims, not
                    # the first one the provider listed. XMLTV allows several
                    # and ranks none of them, and on real guides the first is
                    # routinely not the name: a channel number
                    # (<display-name>101</display-name>) or a language the
                    # user does not have come first, and taking the first
                    # non-empty one threw the match away while the guide was
                    # declaring it. Choosing among CLAIMED names needs no
                    # language policy, because the playlist is the policy.
                    # A channel declaring two claimed names takes the first:
                    # one guide channel cannot hold two rows (claim_channel).
                    #
                    # The loop no longer BREAKS on the first claimed name,
                    # because the bare-name pass below has to see every
                    # declaration of this channel; `name` is still the first
                    # claimed one, which is the decision that paragraph
                    # describes.
                    name = ""
                    for child in elem.iterfind("display-name"):
                        text = child.text
                        candidate = epg_name_key(text)
                        if candidate and candidate in playlist_names and not name:
                            name = candidate
                        # The bare key, for addrNameConflicts and nothing else.
                        # Computed from `candidate` when the raw text carries
                        # no trailing parenthetical, which is the common case
                        # and costs no second fold.
                        if bare_rows:
                            bare = candidate
                            if not isinstance(text, str) or text.rstrip().endswith(")"):
                                bare = bare_name_key(text)
                            if bare and bare in bare_rows:
                                bare_guide.setdefault(bare, set()).add(cid)
                    if name:
                        owner = guide_name_owner.get(name)
                        if owner is None:
                            guide_name_owner[name] = cid
                            guide_names[cid] = name
                        elif owner != cid:
                            # Ambiguous on the GUIDE's side: neither may match.
                            guide_names[owner] = ""
                            guide_names[cid] = ""
                            # And neither may KEEP a match it already won. A
                            # guide that declares each channel beside its own
                            # programmes (the DTD orders them the other way,
                            # but feeds are not all conforming) has already
                            # banked the first declaration's claim by the
                            # time the second one arrives, so blanking the
                            # lookup is not enough: the claim and the
                            # programmes collected under it are revoked here,
                            # which is what makes the rule independent of the
                            # order the guide streamed.
                            owned = playlist_names[name]
                            for loser in (owner, cid):
                                if claim.get(owned) == (EPG_MATCH_NAME, loser):
                                    claim.pop(owned, None)
                                    pending.pop(owned, None)
                                    seen_ids.discard(owned)
                            if name in guide_name_collided:
                                guide_names_dropped += 1
                            else:
                                guide_name_collided.add(name)
                                guide_names_dropped += 2
            # Release every finished element: the tree never holds more than
            # the element being built, whatever the feed puts under <tv>.
            if root is not None and elem is not root:
                root.clear()
    except ET.ParseError as error:
        raise HelperError("bad_xml", "could not parse EPG XML: %s" % error)
    except (OSError, EOFError, zlib.error) as error:
        raise HelperError("bad_gzip", "could not decompress EPG: %s" % error)
    if total_programmes == 0:
        raise HelperError("empty_epg", "no programmes found in the EPG")

    # addrNameConflicts: rows the ADDRESS strategy holds where the guide also
    # declares a DIFFERENT channel under the row's own bare name. Read off the
    # final `claim`, so a claim revoked by the guide-side ambiguity branch is
    # not counted, and off `bare_guide`, which saw every declaration.
    #
    # This is the reverse of the check the address strategy was accepted on.
    # That one asked whether the NAME matcher had paired these rows with a
    # different guide channel and found 0, which is true and is blind to the
    # 40 rows NAME left blank. This one asks the question from the guide's
    # side and reports 1 on the frozen inputs: see bare_name_key for the row,
    # the product owner's ruling on it, and why it is counted rather than
    # re-ranked.
    addr_name_conflicts = 0
    for bare, owners in bare_rows.items():
        declared = bare_guide.get(bare)
        if not declared:
            continue
        for tvg in owners:
            held = claim.get(tvg)
            if held is not None and held[0] == EPG_MATCH_ADDR and declared - {held[1]}:
                addr_name_conflicts += 1

    channels: dict[str, str] = {}
    kept = 0
    for key, items in pending.items():
        blob, count = encode_records(items)
        if count:
            channels[key] = blob
            kept += count
    warnings: list[str] = []
    if bad_time:
        warnings.append("%d programmes with unreadable times skipped" % bad_time)
    if no_title:
        warnings.append("%d programmes without a title skipped" % no_title)
    if index is not None and unknown:
        warnings.append("%d programmes for channels not in the playlist dropped" % unknown)
    if contested:
        warnings.append("%d programmes dropped: another guide channel already matched that playlist channel" % contested)
    return {
        "channels": channels,
        "seenIds": seen_ids,
        # playlist key -> the strategy rank that won it, for match_counts.
        "strategyOf": {key: held[0] for key, held in claim.items()},
        "windowStart": window_start,
        "windowEnd": window_end,
        "epgChannels": len(seen_ids),
        "channelElements": channel_elements,
        "programmeCount": kept,
        # Guide-side declarations dropped because another declaration folds
        # to the same name. Counted only over names a playlist channel
        # claims, because a name nothing claims cannot match either way.
        "nameDroppedGuide": guide_names_dropped,
        "addrNameConflicts": addr_name_conflicts,
        "warnings": warnings,
    }


def match_counts(channels_doc: Any, seen_ids: set[str], strategy_of: dict[str, int]) -> dict[str, int]:
    """Playlist channels an XMLTV channel MATCHED, split by strategy.

    Counted over CHANNELS and not over guide ids, because the acceptance of
    M4-01 is a number of rows: two playlist rows sharing one tvg-id both
    count, exactly as `matched` has always counted them.

    A match, not a render. `seen_ids` is added to when a claim is granted,
    which is before the window, time and title tests, so a channel whose
    only programme is a month out counts here and renders nothing: `matched`
    is the match count and `nowCount` is the render count, and a report that
    quotes one as the other overstates whichever is larger. They agree on the
    real data the milestone was accepted on (227 and 227) and they are free
    to diverge. Claim REVOCATION (parse_xmltv's guide-side ambiguity branch)
    is the one case that also takes a key back OUT of `seen_ids`, so a
    revoked claim is not counted as a match it no longer holds.
    """
    # Built FROM EPG_MATCH_KEYS rather than spelled out, so a strategy added
    # to that tuple cannot be counted into a bucket that does not exist.
    counts = {"matched": 0}
    for name in EPG_MATCH_KEYS:
        counts[name] = 0
    for channel in channels_doc.get("channels", []):
        tvg = channel.get("tvgId") if isinstance(channel, dict) else None
        if isinstance(tvg, str) and tvg in seen_ids:
            counts["matched"] += 1
            rank = strategy_of.get(tvg)
            if rank is not None and 0 <= rank < len(EPG_MATCH_KEYS):
                counts[EPG_MATCH_KEYS[rank]] += 1
    return counts


def channels_mtime(path: str) -> int | None:
    try:
        return int(os.stat(path).st_mtime_ns)
    except OSError:
        return None


def window_lines(channels: dict[str, str]) -> list[str]:
    """'"<id>"\t<records>' per channel; the id is stored JSON-encoded."""
    return ["%s\t%s" % (json_string(cid), blob) for cid, blob in channels.items()]


def write_window(path: str, meta: dict[str, Any], channels: dict[str, str]) -> None:
    lines = [json.dumps(meta, ensure_ascii=False, separators=(",", ":"))]
    lines.extend(window_lines(channels))
    write_text_atomic(path, "\n".join(lines) + "\n")


def load_window(path: str) -> dict[str, Any] | None:
    """-> the header keys plus "lines" (the raw channel lines), or None."""
    try:
        text = read_regular_text(path)
    except OSError:
        return None
    head, _, body = text.partition("\n")
    try:
        meta = json.loads(head)
    except ValueError:
        return None
    if not isinstance(meta, dict) or meta.get("version") != 1:
        return None
    window = dict(meta)
    window["lines"] = body.split("\n")
    return window


def window_channels(window: dict[str, Any]) -> dict[str, str]:
    """Channel id -> record blob (diagnostics and tests; not the hot path)."""
    out: dict[str, str] = {}
    for line in window.get("lines", []):
        cid, tab, blob = line.partition("\t")
        if tab:
            out[json.loads(cid)] = blob
    return out


def needs_refetch(window: dict[str, Any], url: str, now: int, ttl: float, channels_path: str) -> str:
    """Empty string when the cached window is still good, else the reason."""
    if window.get("sourceKey") != source_key(url):
        return "source changed"
    fetched_at = int(window.get("fetchedAt") or 0)
    if now - fetched_at >= ttl or fetched_at > now + 60:
        return "cache older than ttl"
    if int(window.get("windowEnd") or 0) - now < EPG_REFETCH_MARGIN:
        return "window nearly exhausted"
    if window.get("channelsMtime") != channels_mtime(channels_path):
        return "playlist changed"
    return ""


def fetch_window(url: str, timeout: float, now: int, directory: str) -> dict[str, Any]:
    channels_path = os.path.join(directory, CHANNELS_FILE)
    data = fetch_bytes(url, timeout, "EPG")
    channels_doc = read_json(channels_path)
    mtime = channels_mtime(channels_path)
    index, channel_total = build_alias(channels_doc)
    parsed = parse_xmltv(open_xml_stream(data), now, index)
    counts = match_counts(channels_doc, parsed["seenIds"], parsed["strategyOf"]) if index is not None else {}
    matched = counts.get("matched") if index is not None else None
    warnings = list(parsed["warnings"])
    if index is not None and matched == 0:
        warnings.append("no EPG channel id matches a playlist tvg-id")
    meta = {
        "version": 1,
        "fetchedAt": now,
        "sourceHost": source_host(url),
        "sourceKey": source_key(url),
        "channelsMtime": mtime,
        "windowStart": parsed["windowStart"],
        "windowEnd": parsed["windowEnd"],
        "restricted": index is not None,
        "channelTotal": channel_total if index is not None else None,
        "matched": matched,
        # M4-01's acceptance, carried in the window so that a `--now-only`
        # recompute reports the same numbers as the fetch that produced them.
        # The window stays version 1 on purpose: these keys are additive and
        # an older cache simply answers None for them, which is worth more
        # than throwing a good window away at the first upgrade.
        "matchedById": counts.get("matchedById") if index is not None else None,
        "matchedByAddr": counts.get("matchedByAddr") if index is not None else None,
        "matchedByFeed": counts.get("matchedByFeed") if index is not None else None,
        "matchedByName": counts.get("matchedByName") if index is not None else None,
        "nameIndexed": index["nameIndexed"] if index is not None else None,
        "nameDroppedPlaylist": index["nameDroppedPlaylist"] if index is not None else None,
        "nameDroppedGuide": parsed["nameDroppedGuide"] if index is not None else None,
        "addrIndexed": index["addrIndexed"] if index is not None else None,
        "addrDroppedPlaylist": index["addrDroppedPlaylist"] if index is not None else None,
        # The ADDR strategy's own contradiction count (see bare_name_key).
        # Additive like the keys above, so an older window answers None.
        "addrNameConflicts": parsed["addrNameConflicts"] if index is not None else None,
        "epgChannels": parsed["epgChannels"],
        "programmeCount": parsed["programmeCount"],
        "warnings": warnings,
    }
    write_window(os.path.join(directory, EPG_WINDOW_FILE), meta, parsed["channels"])
    window = dict(meta)
    window["lines"] = window_lines(parsed["channels"])
    return window


def record_to_dict(record: str) -> dict[str, Any]:
    """-> {"title", "start", "stop"} plus whichever EPG_DETAIL_KEYS the record
    carries. Diagnostics and tests; programme_json is the hot path."""
    out = dict(json.loads('{"title":' + record[22:] + "}"))
    out["start"] = int(record[:10])
    out["stop"] = int(record[11:21])
    return out


def programme_json(record: str) -> str:
    """The `now`/`next` object of epg-now.json, by concatenation.

    The record's tail from index 22 is the title's JSON value followed by the
    optional detail members, already encoded by encode_record, so this
    function only names the title, wraps the tail and appends the two
    numbers. That is what keeps the 10,000-channel recompute free of
    per-programme encoding work.
    """
    start = record[:10]
    stop = record[11:21]
    if start[0] == "0" or stop[0] == "0":
        start, stop = str(int(start)), str(int(stop))  # no leading zeros in JSON numbers
    return '{"title":' + record[22:] + ',"start":' + start + ',"stop":' + stop + "}"


def compute_now_next(window: dict[str, Any], now: int) -> tuple[list[str], int, int]:
    """-> (JSON fragments `"id":{"now":...,"next":...}`, validUntil, channels with a `now`).

    `now` is the programme with the latest start <= now that has not ended
    (a few earlier records are probed so an overlapped long programme still
    counts); `next` is the first programme starting after now. The hot path
    for 10k channels: fixed-width record prefixes make bisect and string
    comparison enough, and the output is assembled as text.
    """
    sep = EPG_RECORD_SEP
    bisect_right = bisect.bisect_right
    now_str = "%010d" % now
    now_key = now_str + "~"
    boundary = "%010d" % (now + EPG_VALID_MAX)
    now_count = 0
    fragments: list[str] = []
    for line in window["lines"]:
        cid, tab, blob = line.partition("\t")
        if not tab:
            continue
        records = blob.split(sep)
        index = bisect_right(records, now_key)
        current = None
        probe = index - 1
        floor = index - 5
        while probe >= 0 and probe > floor:
            record = records[probe]
            if record[11:21] > now_str:
                current = record
                break
            probe -= 1
        following = records[index] if index < len(records) else None
        if current is None and following is None:
            continue
        parts: list[str] = []
        if current is not None:
            parts.append('"now":' + programme_json(current))
            if current[11:21] < boundary:
                boundary = current[11:21]
            now_count += 1
        if following is not None:
            parts.append('"next":' + programme_json(following))
            if following[:10] < boundary:
                boundary = following[:10]
        fragments.append(cid + ":{" + ",".join(parts) + "}")
    return fragments, max(int(boundary), now + 1), now_count


def write_epg_now(directory: str, window: dict[str, Any], now: int) -> tuple[int, int]:
    fragments, valid_until, now_count = compute_now_next(window, now)
    head = json.dumps({
        "version": 1,
        "generatedAt": now,
        "validUntil": valid_until,
        "fetchedAt": window.get("fetchedAt"),
        "sourceHost": window.get("sourceHost", ""),
    }, ensure_ascii=False, separators=(",", ":"))
    text = head[:-1] + ',"channels":{' + ",".join(fragments) + "}}\n"
    write_text_atomic(os.path.join(directory, EPG_NOW_FILE), text)
    return valid_until, now_count


def cmd_epg(args: argparse.Namespace) -> int:
    directory = cache_dir(args.cache_dir)
    now = int(args.now) if args.now else int(time.time())
    window_path = os.path.join(directory, EPG_WINDOW_FILE)
    status_path = os.path.join(directory, EPG_STATUS_FILE)
    channels_path = os.path.join(directory, CHANNELS_FILE)
    url = url_from(args)
    started = time.monotonic()
    previous = read_json(status_path) or {}
    window = None
    error: HelperError | None = None
    cached = False
    refresh_error: OSError | None = None
    from_cache = False
    valid_until = now_count = 0
    # D-M3U-1: bounded before the cached window is read or a guide fetched.
    held = limit_memory(EPG_PRELOAD)
    try:
        try:
            try:
                window = load_window(window_path)
                if args.now_only:
                    if window is None:
                        raise HelperError("no_cache", "no cached EPG window yet; fetch the EPG first")
                    from_cache = True
                else:
                    if not url:
                        raise HelperError("no_source", "no EPG URL configured")
                    reason = "forced" if args.force else ("no cache" if window is None else needs_refetch(window, url, now, args.ttl, channels_path))
                    if reason:
                        window = fetch_window(url, args.timeout, now, directory)
                        from_cache = False
                    else:
                        from_cache = True
                assert window is not None
                valid_until, now_count = write_epg_now(directory, window, now)
            except HelperError as caught:
                error = caught
                cached = window is not None
                if window is not None:
                    # The window that is still good -- the cached one, when a
                    # refetch was refused -- keeps epg-now.json current. Data,
                    # not the status, so it is written under the limit like
                    # every other derivation of the window; a MemoryError here
                    # is the memory refusal below. Its failure is spoken of
                    # once the limit is lifted.
                    try:
                        write_epg_now(directory, window, now)
                    except OSError as io_error:
                        refresh_error = io_error
        finally:
            # D-M3U-3, as in cmd_playlist: the limit covers reading or fetching
            # the window and deriving epg-now.json from it, and NOTHING after
            # them. Lifted here, on every way out -- success, a refusal, the
            # memory refusal, a bug -- so no status is composed, written or
            # printed under it.
            release_memory_limit(held)
    except MemoryError:
        # D-M3U-1, as in cmd_playlist: the limit is lifted (above), release,
        # then speak. The window is dropped whichever one it was -- the cached
        # one, or a fetched one whose epg-now.json may be the step that ran
        # out -- so nothing is recomputed on the way out. Both files are
        # written atomically: what is on disk is the previous run's, or
        # nothing, and `stale` says whether a previous window is there.
        window = None
        refresh_error = None
        error = memory_refusal("EPG", source_host(url) if url else "", held)
        cached = os.path.isfile(window_path)
    if error is None:
        assert window is not None
        fetched_at = int(window.get("fetchedAt") or 0)
        status = {
            "ok": True,
            "kind": "epg",
            "sourceHost": window.get("sourceHost", ""),
            "fetchedAt": fetched_at,
            "generatedAt": now,
            "validUntil": valid_until,
            "durationMs": int((time.monotonic() - started) * 1000),
            "fromCache": from_cache,
            "matched": window.get("matched"),
            "channelTotal": window.get("channelTotal"),
            # M4-01 is accepted on these counts and on nothing else: a flag
            # saying the matcher is on proves nothing (rule 14). They come
            # from the window, so `--now-only` reports the fetch's numbers;
            # a window written before M4 answers None rather than 0, which
            # is the truthful answer for "not measured".
            "matchedById": window.get("matchedById"),
            "matchedByAddr": window.get("matchedByAddr"),
            "matchedByFeed": window.get("matchedByFeed"),
            "matchedByName": window.get("matchedByName"),
            "nameIndexed": window.get("nameIndexed"),
            "nameDroppedPlaylist": window.get("nameDroppedPlaylist"),
            "nameDroppedGuide": window.get("nameDroppedGuide"),
            "addrIndexed": window.get("addrIndexed"),
            "addrDroppedPlaylist": window.get("addrDroppedPlaylist"),
            "addrNameConflicts": window.get("addrNameConflicts"),
            "epgChannels": window.get("epgChannels", 0),
            "programmeCount": window.get("programmeCount", 0),
            "nowCount": now_count,
            "warnings": list(window.get("warnings") or []),
            "stale": from_cache and (now - fetched_at > args.ttl),
            "error": None,
        }
        write_json_atomic(status_path, status)
        emit(status)
        return EXIT_OK
    if refresh_error is not None:
        log("could not refresh %s: %s" % (EPG_NOW_FILE, refresh_error))
    host = source_host(url) if url else (window.get("sourceHost", "") if window else "")
    status = error_payload(
        "epg", error,
        sourceHost=host,
        fetchedAt=window.get("fetchedAt") if window else (previous.get("fetchedAt") if isinstance(previous, dict) else None),
        stale=cached,
        matched=window.get("matched") if window else None,
        channelTotal=window.get("channelTotal") if window else None,
        durationMs=int((time.monotonic() - started) * 1000),
    )
    write_status_quietly(status_path, status)
    log("epg: %s" % error.message)
    emit(status)
    return EXIT_ERROR


