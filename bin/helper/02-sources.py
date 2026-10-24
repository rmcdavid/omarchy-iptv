# A part of bin/omarchy-iptv (D-REL-7), not a module: the helper compiles
# this file into its own namespace in the order its HELPER_PARTS lists, so
# a part sees every name the parts before it define. Run the helper.
from __future__ import annotations
# -------------------------------------------------------------- sources
# Python mirror of Model.sanitizeInput / validateSourceUrl / sourceKey /
# deriveLabel (ARCHITECTURE-SOURCES.md section 3, codes per UX-SOURCES.md
# 5.4 as ruled by SR6). Both sides run the source-urls.json. fixture (dev branch)

def utf16_length(text: str) -> int:
    """Length in UTF-16 code units, the unit JS strings and caps use."""
    return len(text) + sum(1 for ch in text if ord(ch) > 0xFFFF)


def truncate_utf16(text: str, limit: int) -> str:
    if utf16_length(text) <= limit:
        return text
    out: list[str] = []
    used = 0
    for ch in text:
        width = 2 if ord(ch) > 0xFFFF else 1
        if used + width > limit:
            break
        out.append(ch)
        used += width
    return "".join(out)


def sanitize_input(value: Any, limit: int) -> str:
    """Model.sanitizeInput: one leading byte-order mark (a paste artefact,
    SR15) dropped, control characters (CR, LF, TAB included) removed, ASCII
    space and NBSP trimmed, capped at `limit` UTF-16 units. Applied at every
    field boundary and again inside validate_source_url."""
    text = "" if value is None else str(value)
    if text.startswith("\ufeff"):
        text = text[1:]
    text = _CONTROL_CHARS.sub("", text)
    return truncate_utf16(text.strip(" \u00a0"), limit)


def cap_code_points(text: str, limit: int) -> str:
    """Model.capCodePoints: the label cap counts Unicode code points, not
    UTF-16 units (SR22: JS [...s].length, Python len)."""
    return text[:limit]


def _validation(ok: bool, code: str, message: str, kind: str = "", url: str = "", host: str = "") -> dict[str, Any]:
    return {"ok": ok, "code": code, "message": message, "kind": kind, "url": url, "host": host}


_URL_EDGE_SPACE = URL_DELIMITER_CHARS + "\xa0"


def _sanitize_url_input(value: Any, limit: int) -> str:
    """Model.sanitizeUrlInput, the boundary rule for a URL (D-SRC-63,
    R32a''', 2026-10-22): NOTHING inside the text is deleted. sanitize_input
    served validate_source_url until then and rewrote the URL --
    `http://u:pa<TAB>ss@h.test/x` validated as the password `pass`, here as
    in the model, and a multi-line value collapsed into one URL nobody
    typed. A reader REFUSES whitespace and control characters, and it can
    only refuse what reaches it. What is taken off: one leading byte-order
    mark (SR15), and the six ASCII whitespace characters plus NBSP off both
    ENDS (a trailing newline, a tab-indented line); then the cap in UTF-16
    units. The shared source-urls fixture holds both mirrors to it."""
    text = "" if value is None else str(value)
    if text.startswith("\ufeff"):
        text = text[1:]
    return truncate_utf16(text.strip(_URL_EDGE_SPACE), limit)


def _validate_path(path: str) -> dict[str, Any]:
    # D-SRC-63: a decoded `file:` path may carry what the raw text did not
    # (`file:///a%09b`); refused, as normalize_state drops a record whose
    # url holds a control character.
    if _CONTROL_CHARS.search(path):
        return _validation(False, "invalid", "path contains a control character")
    for prefix in UNSAFE_PATH_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return _validation(False, "unsafe_path", "paths under /proc, /sys and /dev are not allowed")
    return _validation(True, "ok", "", "file", path, "")


def looks_like_host(text: str) -> bool:
    """SR12: a "." or ":" before the first "/" reads as a host."""
    return re.search(r"[.:]", text.split("/", 1)[0]) is not None


def validate_source_url(text: Any, origin: str = "form") -> dict[str, Any]:
    """Mirror of Model.validateSourceUrl(text, {origin}) -> {ok, code,
    message, kind, url, host}; `url` is the normalized form (the source
    identity): scheme and host lower-cased, numeric port normalized (leading
    zeros stripped, the scheme default dropped), empty path `/`, query
    verbatim, fragment dropped, userinfo kept. Codes: empty, too_long,
    scheme, invalid, relative_path, unsafe_path (UX-SOURCES.md 5.4, SR6).
    `origin` "cli" accepts `~` paths verbatim (SR11; expanded by the reader),
    the forms refuse them. The authority refuses backslashes, zero-width
    characters, ports above 65535 and bracket literals that are not IPv6
    (SR15). Messages never contain a URL."""
    cli = origin == "cli"
    # D-SRC-63 (R32a'''): the URL boundary rule deletes nothing inside the
    # text, so what sanitize_input used to rewrite is refused below instead.
    value = _sanitize_url_input(text, MAX_SOURCE_URL + 1)
    if value == "":
        return _validation(False, "empty", "no source URL or path given")
    if utf16_length(value) > MAX_SOURCE_URL:
        return _validation(False, "too_long", "source URL longer than %d characters" % MAX_SOURCE_URL)
    # D-SRC-63: a control character anywhere -- a tab, a line break, an
    # information separator, U+0085, a NUL -- is REFUSED, never deleted.
    # Both state readers drop a record whose url holds one, so accepting it
    # would store a source the next load discards. Mirrors
    # Model.validateSourceUrl; the tab is whitespace first, so it is named
    # as whitespace here as the model's union check would.
    if _CONTROL_CHARS.search(value):
        if _URL_SPACE.search(value):
            return _validation(False, "invalid", "URL contains whitespace")
        return _validation(False, "invalid", "URL contains a control character")
    if value.startswith("//"):
        return _validation(False, "scheme", "scheme-relative URLs are not supported (use http or https)")
    if value.startswith("/"):
        return _validate_path(value)
    if value.startswith("~"):
        if cli:
            return _validation(True, "ok", "", "file", value, "")
        return _validation(False, "relative_path", "use an absolute path (starts with /, not ~)")
    if value in (".", "..") or value.startswith("./") or value.startswith("../"):
        return _validation(False, "relative_path", "use an absolute path (starts with /)")
    match = _SOURCE_SCHEME_RE.match(value)
    if not match:
        if looks_like_host(value):
            return _validation(False, "scheme", "use http, https, file or an absolute path")
        return _validation(False, "relative_path", "use an absolute path (starts with /)")
    scheme = match.group(1).lower()
    rest = match.group(2)
    if scheme == "file":
        if not rest.startswith("//"):
            return _validation(False, "invalid", "file URL is missing the two slashes after the scheme")
        after = re.sub(r"[?#].*$", "", rest[2:], flags=re.S)
        slash = after.find("/")
        if slash == -1:
            return _validation(False, "invalid", "file URL has no path")
        path = after[slash:]
        if _BAD_ESCAPE.search(path):
            return _validation(False, "invalid", "file URL has a malformed percent escape")
        try:
            path = urllib.parse.unquote(path, errors="strict")
        except UnicodeDecodeError:
            return _validation(False, "invalid", "file URL path is not valid UTF-8")
        if not path.startswith("/"):
            return _validation(False, "invalid", "file URL path is not absolute")
        return _validate_path(path)
    if scheme not in ("http", "https"):
        return _validation(False, "scheme", "unsupported source scheme '%s' (use http, https or an absolute path)" % scheme)
    if not rest.startswith("//"):
        return _validation(False, "invalid", "URL is missing the two slashes after the scheme")
    if _URL_SPACE.search(rest):
        return _validation(False, "invalid", "URL contains whitespace")
    body = rest[2:]
    cut = _AUTHORITY_END.search(body)
    authority = body if cut is None else body[:cut.start()]
    tail = "" if cut is None else body[cut.start():]
    if "\\" in authority or _ZERO_WIDTH.search(authority):
        return _validation(False, "invalid", "URL host contains an invalid character")
    at = authority.rfind("@")
    userinfo = authority[:at] if at != -1 else ""
    hostport = authority[at + 1:] if at != -1 else authority
    # R32a (D-SINK-27, 2026-10-21): the authority ends at the first "/", "?"
    # or "#" and its userinfo at the LAST "@" within it; an "@" after the
    # authority is path or query and refuses nothing. The round-2 refusal
    # that stood here (the mirror of passwordReadAsPort) dropped a stored
    # Xtream /playlist/<email>/<pass>/m3u_plus link on the first normalize
    # after the upgrade, and is withdrawn. Mirrors Model.validateSourceUrl.
    port = ""
    if hostport.startswith("["):
        close = hostport.find("]")
        if close == -1:
            return _validation(False, "invalid", "unterminated IPv6 literal")
        host = hostport[:close + 1]
        if not _IPV6_LITERAL.match(host):
            return _validation(False, "invalid", "bracket literal is not an IPv6 address")
        after_host = hostport[close + 1:]
        if after_host:
            if not after_host.startswith(":"):
                return _validation(False, "invalid", "unexpected text after the IPv6 literal")
            port = after_host[1:]
    else:
        colon = hostport.rfind(":")
        host, port = (hostport[:colon], hostport[colon + 1:]) if colon != -1 else (hostport, "")
        if _BARE_HOST_CHARS.search(host):
            return _validation(False, "invalid", "URL host contains an invalid character")
    if host == "":
        return _validation(False, "invalid", "URL has no host name")
    host = host.lower()
    if port != "":
        if not _ASCII_DIGITS.match(port):
            return _validation(False, "invalid", "URL port is not a number")
        port = port.lstrip("0") or "0"
        if int(port) > 65535:
            return _validation(False, "invalid", "URL port is above 65535")
    if port == ("80" if scheme == "http" else "443"):
        port = ""
    hash_at = tail.find("#")
    if hash_at != -1:
        tail = tail[:hash_at]
    query_at = tail.find("?")
    path = tail if query_at == -1 else tail[:query_at]
    query = "" if query_at == -1 else tail[query_at + 1:]
    if path == "":
        path = "/"
    url = "%s://%s%s%s%s%s" % (scheme, userinfo + "@" if userinfo else "", host, ":" + port if port else "", path, "?" + query if query else "")
    return _validation(True, "ok", "", "http", url, host)


def source_cache_key(url: str) -> str:
    """Cache directory name of a normalized playlist URL (Model.sourceKey)."""
    return fnv1a32(url)


def find_source(sources: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    for record in sources:
        if record.get("key") == key:
            return record
    return None


def find_source_by_url(sources: list[dict[str, Any]], url: str) -> dict[str, Any] | None:
    for record in sources:
        if record.get("url") == url:
            return record
    return None


def allocate_source_key(sources: list[dict[str, Any]], url: str) -> str:
    """The record's key when the URL is known, else fnv1a32 with a "-2",
    "-3", ... suffix while another record already uses that key."""
    existing = find_source_by_url(sources, url)
    if existing is not None:
        return str(existing["key"])
    base = source_cache_key(url)
    key = base
    suffix = 2
    while find_source(sources, key) is not None:
        key = "%s-%d" % (base, suffix)
        suffix += 1
    return key


def cut_host_params(hostport: str) -> str:
    """Where a PRINTED host ends: at the first `;`, `=` or `&` (D-SINK-30).

    RFC 3986's reg-name admits all three, so `http://h.test;sid=SECRET/x`
    validates with host `h.test;sid=secret`, and a reader that stops at `:`
    alone prints the parameter wherever it prints the host. ONE copy of the
    rule in the helper, shared by every reader that derives a printable host
    from an authority -- `host_port_of` (the Sources row and its default
    label) and `logo_host` (the consent survey and the logo refusal lines) --
    mirrored by Model.cutHostParams. The `:` port is NOT cut here: each
    caller keeps or drops it on its own line, and a bracketed literal is
    unaffected because none of the three can appear inside the brackets.
    A `find` per character rather than a pattern: the helper's regex guard
    holds every compiled pattern to a reviewed table.
    """
    for delimiter in ";=&":
        end = hostport.find(delimiter)
        if end != -1:
            hostport = hostport[:end]
    return hostport


def host_port_of(url: str) -> str:
    """Mirror of hostPortOf (model/sources.mjs, internal to the model): host[:port] of a URL, lower-cased; "" for paths.

    D-SINK-17. The userinfo ends at the LAST at-sign in the authority, not the
    first. This matched `(?:[^@/?#]*@)?`, which cannot cross an at-sign, so
    `https://user:p@ss@host.example/list.m3u` returned `ss@host.example` and
    `https://u@er:pass@host.example/list.m3u` returned `er:pass@host.example`
    -- the whole password, into the Sources row's host and default label, on a
    source whose URL is masked everywhere else. D-SINK-1 was the same defect in
    `redact_urls`; `url_host` and `validate_source_url` have been right all
    along because they hand the string to a real parser or cut at the last
    at-sign, and this now does the same.

    D-SINK-30 (2026-10-24). RFC 3986's reg-name admits `;`, `=` and `&`, so
    `http://h.test;sid=SECRET/x` validates with host `h.test;sid=secret` and
    this printed it so, where run_host_parts had cut the free-text host at
    `:`, `;`, `=` and `&` since R32a'. The printed host[:port] now ends at
    the first of the three (the `:` port is kept); validation is unchanged
    (D-SINK-27). The cut is `cut_host_params`, shared with `logo_host`.
    """
    match = re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*://([^/?#]*)", url)
    if not match:
        return ""
    authority = match.group(1)
    at = authority.rfind("@")
    hostport = authority if at == -1 else authority[at + 1:]
    return cut_host_params(hostport).lower()


def derive_label(url: str, kind: str) -> str:
    """Model.deriveLabel (UX-SOURCES.md 5.6): host (lower-case, leading www.
    removed, :port kept when it is not the default) for http(s); the file
    name for paths; capped at MAX_LABEL code points (SR19, SR20, SR22)."""
    text = "" if url is None else str(url)
    checked = validate_source_url(text, origin="cli")
    if kind == "file" or checked["kind"] == "file":
        source = checked["url"] if checked["ok"] else text
        name = source.rstrip("/").rsplit("/", 1)[-1]
        return cap_code_points(sanitize_input(name, MAX_SOURCE_URL), MAX_LABEL) or "local file"
    hostport = host_port_of(checked["url"] if checked["ok"] else text)
    if hostport == "":
        return cap_code_points(sanitize_input(text, MAX_SOURCE_URL), MAX_LABEL)
    if hostport.startswith("www."):
        hostport = hostport[4:]
    return cap_code_points(sanitize_input(hostport, MAX_SOURCE_URL), MAX_LABEL)


def label_key(text: Any) -> str:
    """Mirror of labelKey (model/sources.mjs, internal to the model): the case-insensitive comparison form (SR21)."""
    return sanitize_input(text, MAX_SOURCE_URL).lower()


def unique_label(label: str, existing: list[str]) -> str:
    """Model.uniqueLabel: " 2", " 3", ... appended while `label` is taken by
    another source (case-insensitive, SR21); the cap counts code points
    (SR22). Derived labels only; a typed label is refused instead."""
    taken = {label_key(item) for item in existing}
    base = cap_code_points(sanitize_input(label, MAX_SOURCE_URL), MAX_LABEL) or "source"
    if base.lower() not in taken:
        return base
    for suffix in range(2, 1000):
        tail = " %d" % suffix
        candidate = cap_code_points(base, MAX_LABEL - len(tail)) + tail
        if candidate.lower() not in taken:
            return candidate
    return base


_ATTR_QUOTED = re.compile(r'\s*([A-Za-z0-9_.\-]+)="([^"]*)"')
_ATTR_BARE = re.compile(r'\s*([A-Za-z0-9_.\-]+)=([^\s,"]+)')

# Channel-number attributes, in precedence order (M2-03 1.1, ruling CN11).
# `tvg-chno` is what every asset in this repo uses; the two aliases are read
# because a playlist that HAS numbers and silently shows none is the worst
# failure this feature can have, and there is no error for the user to search
# for. Keys arrive lower-cased from parse_attrs, so the match is
# case-insensitive, and both the quoted and the bare form are already handled.
CHNO_ATTRS = ("tvg-chno", "tvg-channel-number", "channel-number")


def parse_attrs(text: str) -> tuple[dict[str, str], str]:
    """Parse `key="value" key2=value ...` from the start of `text`.

    Returns (attrs, remainder). Attribute values may contain commas; the
    remainder starts at the first character that is not an attribute.
    Keys are lower-cased; when a key repeats, the last non-empty value wins.
    """
    attrs: dict[str, str] = {}
    pos = 0
    while pos < len(text):
        match = _ATTR_QUOTED.match(text, pos) or _ATTR_BARE.match(text, pos)
        if not match:
            break
        key = match.group(1).lower()
        value = match.group(2).strip()
        if value or key not in attrs:
            attrs[key] = value
        pos = match.end()
    return attrs, text[pos:]


def parse_extinf(line: str) -> tuple[dict[str, str], str]:
    """#EXTINF:<duration> [attrs],<title> -> (attrs, title).

    The comma is optional: `#EXTINF:-1 tvg-id="x" Name` yields title "Name".
    """
    body = line[len("#EXTINF:"):]
    match = re.match(r"\s*(-?\d+(?:\.\d+)?)?", body)
    body = body[match.end():] if match else body
    attrs, rest = parse_attrs(body)
    rest = rest.lstrip()
    if rest.startswith(","):
        rest = rest[1:]
    return attrs, rest.strip()


def stream_scheme(url: str) -> str:
    try:
        return urllib.parse.urlsplit(url).scheme.lower()
    except ValueError:
        return ""


def is_stream_url(url: str) -> bool:
    """Allow-listed scheme with a non-empty host; never option-looking (D-QA-07)."""
    if url.startswith("-"):
        return False
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return parts.scheme.lower() in STREAM_SCHEMES and bool(parts.hostname)


def clean_header_value(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()


def split_groups(value: str) -> list[str]:
    """`A;B;C` -> ["A", "B", "C"] (trimmed, empties and repeats dropped, the
    first of each kept in order).

    Linear (rule 15 over R30h, lane-bounds-h): a `name not in groups` test
    per part scanned the list, k*k/2 comparisons for k parts, and a
    persistent `#EXTGRP` of up to M3U_MAX_GROUP_TEXT characters -- up to 256
    one-character parts -- is split again for every channel after it, so a
    50,000-channel list paid about 32,000 comparisons a channel. Same list,
    one pass."""
    return list(dict.fromkeys(name for name in (part.strip() for part in value.split(";")) if name))


def channel_number(attrs: dict[str, str]) -> str:
    """The first non-empty channel-number attribute, whitespace-trimmed.

    Normalization stops here, deliberately (M2-03 1.1-1.2): which ATTRIBUTE
    carries the number and what an empty one means is the helper's business,
    what the number MEANS is Model.parseChno's. So the value is stored
    verbatim after `.strip()` - leading zeros, `.` / `-` subchannel
    separators, `N/A` and everything else reach channels.json as written,
    and one implementation decides that 007 is channel 7 (rule: one rule,
    one place). Returns "" when no attribute carries one, and the caller
    omits the key entirely so a reader can tell "no number" from "empty".
    """
    for key in CHNO_ATTRS:
        value = attrs.get(key, "").strip()
        if value:
            return value
    return ""


def clean_name(value: str) -> str:
    """Display-name candidate: never starts with "-" (S-04). The name is an
    argv item for omarchy-notification-send, where "--urgency=x did not play"
    would be parsed as an option. Mirrors Model.cleanName."""
    return _LEADING_DASHES.sub("", value or "").strip()


# D-M3U-1: the warning each length cap adds, once per kind and with a count,
# in the order they are reported. The figure in each is its cap. D-M3U-4:
# each kind carries its sentence for ONE and for more than one, because the
# count is the user's number ("1 channel names cut" was in the guide footer);
# counted_sentence picks between them, and every other counted sentence
# parse_m3u writes goes through it too.
M3U_CUT_WARNINGS = (
    ("name", "%d channel name cut to " + str(M3U_MAX_NAME) + " characters",
             "%d channel names cut to " + str(M3U_MAX_NAME) + " characters"),
    ("tvgName", "%d tvg-name value cut to " + str(M3U_MAX_NAME) + " characters",
                "%d tvg-name values cut to " + str(M3U_MAX_NAME) + " characters"),
    ("groupText", "%d group value cut to " + str(M3U_MAX_GROUP_TEXT) + " characters",
                  "%d group values cut to " + str(M3U_MAX_GROUP_TEXT) + " characters"),
    ("group", "%d group name cut to " + str(M3U_MAX_GROUP) + " characters",
              "%d group names cut to " + str(M3U_MAX_GROUP) + " characters"),
    ("groupCount", "%d channel listed in more than " + str(M3U_MAX_GROUPS_PER_CHANNEL) + " groups kept the first " + str(M3U_MAX_GROUPS_PER_CHANNEL),
                   "%d channels listed in more than " + str(M3U_MAX_GROUPS_PER_CHANNEL) + " groups kept the first " + str(M3U_MAX_GROUPS_PER_CHANNEL)),
    ("tvgId", "%d tvg-id value longer than " + str(M3U_MAX_TVG_ID) + " characters dropped",
              "%d tvg-id values longer than " + str(M3U_MAX_TVG_ID) + " characters dropped"),
    ("chno", "%d channel number longer than " + str(M3U_MAX_CHNO) + " characters dropped",
             "%d channel numbers longer than " + str(M3U_MAX_CHNO) + " characters dropped"),
    ("logo", "%d logo URL longer than " + str(M3U_MAX_LOGO_URL) + " characters dropped",
             "%d logo URLs longer than " + str(M3U_MAX_LOGO_URL) + " characters dropped"),
    ("option", "%d option or header dropped: a name over " + str(M3U_MAX_OPTION_KEY) + " or a value over " + str(M3U_MAX_OPTION_VALUE) + " characters",
               "%d options or headers dropped: a name over " + str(M3U_MAX_OPTION_KEY) + " or a value over " + str(M3U_MAX_OPTION_VALUE) + " characters"),
    ("optionCount", "%d option or header dropped: more than " + str(M3U_MAX_OPTIONS) + " on one channel",
                    "%d options or headers dropped: more than " + str(M3U_MAX_OPTIONS) + " on one channel"),
    ("url", "%d entry skipped: stream URL longer than " + str(M3U_MAX_URL) + " characters",
            "%d entries skipped: stream URL longer than " + str(M3U_MAX_URL) + " characters"),
    ("epgHint", "%d EPG hint longer than " + str(M3U_MAX_EPG_HINT) + " characters dropped",
                "%d EPG hints longer than " + str(M3U_MAX_EPG_HINT) + " characters dropped"),
    ("warnings", "%d more warning like the ones above not listed",
                 "%d more warnings like the ones above not listed"),
)


def counted_sentence(count: int, one: str, many: str) -> str:
    """`one % count` for a count of exactly one, `many % count` otherwise
    (D-M3U-4). Both templates take the count as their first %d."""
    return (one if count == 1 else many) % count


def bound_warnings(bounds: dict[str, int]) -> list[str]:
    """The M3U_CUT_WARNINGS sentence of every kind `bounds` counted, in the
    table's order, each read for its own count."""
    return [counted_sentence(bounds[kind], one, many)
            for kind, one, many in M3U_CUT_WARNINGS if bounds.get(kind)]


def bound_count(bounds: dict[str, int] | None, kind: str) -> None:
    if bounds is not None:
        bounds[kind] = bounds.get(kind, 0) + 1


def cut_text(value: str, limit: int, kind: str, bounds: dict[str, int] | None) -> str:
    """D-M3U-1: `value` cut to `limit` code points (a str slice never splits
    one), trailing whitespace trimmed, counted under `kind` when it was cut."""
    if len(value) <= limit:
        return value
    bound_count(bounds, kind)
    return value[:limit].rstrip()


def bound_groups(groups: list[str], bounds: dict[str, int] | None) -> list[str]:
    """split_groups' list with each name cut to M3U_MAX_GROUP and at most
    M3U_MAX_GROUPS_PER_CHANNEL of them; a cut that makes two names equal
    keeps the first, as split_groups does for a repeat."""
    out: list[str] = []
    for name in groups:
        if len(out) >= M3U_MAX_GROUPS_PER_CHANNEL:
            bound_count(bounds, "groupCount")
            break
        name = cut_text(name, M3U_MAX_GROUP, "group", bounds)
        if name and name not in out:
            out.append(name)
    return out


def channel_warning(warnings: list[str], bounds: dict[str, int] | None, text: str) -> None:
    """A per-channel warning: kept while fewer than M3U_MAX_CHANNEL_WARNINGS
    have been, counted after that (D-M3U-1's sibling, lane A's OQ-6)."""
    if bounds is None:
        warnings.append(text)
        return
    if bounds.get("listed", 0) < M3U_MAX_CHANNEL_WARNINGS:
        bounds["listed"] = bounds.get("listed", 0) + 1
        warnings.append(text)
    else:
        bound_count(bounds, "warnings")


def bounded_option(key: str, value: str, store: dict[str, str], bounds: dict[str, int] | None) -> None:
    """store[key] = value unless either is over its D-M3U-1 cap or the store
    already holds M3U_MAX_OPTIONS other keys: then dropped and counted."""
    if len(key) > M3U_MAX_OPTION_KEY or len(value) > M3U_MAX_OPTION_VALUE:
        bound_count(bounds, "option")
    elif key not in store and len(store) >= M3U_MAX_OPTIONS:
        bound_count(bounds, "optionCount")
    else:
        store[key] = value


def make_channel(attrs: dict[str, str], title: str, url: str, extgrp: str,
                 vlcopt: dict[str, str], kodiprop: dict[str, str],
                 warnings: list[str], index: int = 1,
                 bounds: dict[str, int] | None = None) -> dict[str, Any]:
    """One channels.json row. Every provider-controlled text it keeps is
    held to its D-M3U-1 cap (01-core.py); `bounds` counts what was cut or
    dropped, for parse_m3u's warnings. Without `bounds` the caps still
    apply and only the counting is skipped."""
    tvg_id = attrs.get("tvg-id", "").strip()
    if len(tvg_id) > M3U_MAX_TVG_ID:
        bound_count(bounds, "tvgId")
        tvg_id = ""
    tvg_name = cut_text(attrs.get("tvg-name", "").strip(), M3U_MAX_NAME, "tvgName", bounds)
    # Never fall back to the URL: the name is rendered everywhere (R12, D-QA-02).
    name = cut_text(clean_name(title), M3U_MAX_NAME, "name", bounds) or clean_name(tvg_name) or clean_name(tvg_id) or GENERATED_NAME_FORMAT % index
    # D-M3U-1: `extgrp` is the value that PERSISTS across entries, so it
    # arrives already cut (parse_m3u cuts it once, at its own line, and
    # counts it there); a group-title is this entry's own and is cut here.
    group_title = attrs.get("group-title", "").strip()
    group_text = cut_text(group_title, M3U_MAX_GROUP_TEXT, "groupText", bounds) if group_title else extgrp
    groups = bound_groups(split_groups(group_text), bounds) if group_text else []
    # Sources ruling R5 (groups; not the D-LOGO-11 logo ruling of the same
    # number): multi-group entries list under the FIRST group; the whole
    # group string stays searchable through searchKey and `groups`.
    group = groups[0] if groups else UNGROUPED
    channel: dict[str, Any] = {
        "id": "",
        "name": name,
        "group": group,
        "url": url,
    }
    if len(groups) > 1:
        channel["groups"] = groups
    if tvg_id:
        channel["tvgId"] = tvg_id
    if tvg_name and tvg_name != name:
        channel["tvgName"] = tvg_name
    logo = attrs.get("tvg-logo", "").strip()
    if logo and stream_scheme(logo) in ("http", "https"):
        if len(logo) > M3U_MAX_LOGO_URL:
            bound_count(bounds, "logo")
        else:
            channel["logo"] = logo
    chno = channel_number(attrs)
    if len(chno) > M3U_MAX_CHNO:
        bound_count(bounds, "chno")
        chno = ""
    if chno:
        channel["chno"] = chno

    headers: dict[str, str] = {}
    options: dict[str, str] = {}
    for key, value in vlcopt.items():
        cleaned = clean_header_value(value)
        if key == "http-user-agent":
            if cleaned:
                bounded_option("User-Agent", cleaned, headers, bounds)
        elif key == "http-referrer":
            if cleaned:
                bounded_option("Referer", cleaned, headers, bounds)
        elif _SAFE_OPTION.match(key):
            bounded_option("vlc:" + key, value, options, bounds)
        else:
            channel_warning(warnings, bounds, "dropped option-looking key for %s" % name)
    for key, value in kodiprop.items():
        if key in ("inputstream.adaptive.stream_headers", "inputstream.adaptive.manifest_headers"):
            for hname, hvalue in urllib.parse.parse_qsl(value, keep_blank_values=False):
                cleaned = clean_header_value(hvalue)
                if not _HEADER_NAME.match(hname):
                    channel_warning(warnings, bounds, "dropped header with unsafe name for %s" % name)
                elif cleaned:
                    bounded_option(hname, cleaned, headers, bounds)
        elif _SAFE_OPTION.match(key):
            bounded_option("kodi:" + key, value, options, bounds)
        else:
            channel_warning(warnings, bounds, "dropped option-looking key for %s" % name)
    if headers:
        channel["headers"] = headers
    if options:
        channel["options"] = options
    channel["searchKey"] = search_key(name, " ".join(groups) if groups else group)
    # F-PERF-1. `searchKey` has been precomputed since M0 precisely so the
    # guide's filter does not fold 10,000 strings on every keystroke. The
    # ranker needs a SECOND fold -- the name alone, to rank a name match above
    # a group match -- and that one was never added, so `filterChannels` fell
    # back to folding it per channel per call. Measured over 10,000 channels:
    # 28.05 ms for the query "a" against a 30 ms keystroke budget, of which
    # the ranker itself is 2.9 ms; with this key present the same call is
    # 5.11 ms, and a query matching nothing goes from 22.31 to 1.07.
    #
    # An older cache without this key still works -- the reader keeps its
    # fallback -- so there is no migration, only a slower guide until the next
    # refresh writes one.
    channel["nameKey"] = normalize_text(name)
    return channel


def parse_m3u(text: Any) -> dict[str, Any]:
    """Tolerant M3U/M3U8 parser.

    `text` is the playlist as one str, or its lines as any iterable of str
    (playlist_lines, which is how the `playlist` verb calls it, D-M3U-1: a
    whole-document str costs up to four bytes per character for EVERY
    character once one of them is outside the BMP, and a flag emoji is).
    The two give the same result; a line may keep its line break.

    Understands #EXTM3U (url-tvg / x-tvg-url hint), #EXTINF with quoted or
    bare attributes and a title that may contain commas (comma optional),
    #EXTGRP (persists until the next #EXTGRP, like VLC; group-title wins),
    #EXTVLCOPT and #KODIPROP (apply to the next URL line only, and are
    reset by it whether or not it made a channel). Unknown
    comments are ignored. Accepts a BOM, CRLF and blank lines. Location
    lines outside STREAM_SCHEMES (bare paths, option-looking lines, free
    text, URLs without a host) are skipped and counted; an #EXTINF that is
    followed by another #EXTINF is counted as having no URL. Output is
    bounded by MAX_CHANNELS and MAX_GROUPS (S-07); a channel moved to
    UNGROUPED keeps its provider group in `groups` and `searchKey`. And
    each channel is bounded by a constant (D-M3U-1): every text it keeps is
    held to its M3U_MAX_* cap, so the whole output is at most MAX_CHANNELS
    times that constant, whatever the input repeats.

    What persists from one entry to the next, and why (D-M3U-1, rule 15):
      #EXTGRP  persists, because that is what the tag means -- it opens a
               group for the entries that follow, and lists that use it
               write it once per block. It is the value the finding was
               about, so it is cut to M3U_MAX_GROUP_TEXT ONCE, at its own
               line, and counted there; every entry after it copies at
               most that.
      #EXTVLCOPT, #KODIPROP  never pass a location line: both are reset by
               the next URL line, kept or skipped, and by an orphan line.
               Between two #EXTINF lines with no URL they carry forward to
               the next entry that has one, which is still one channel.
      #EXTM3U's url-tvg / x-tvg-url  one value for the whole document,
               written once into channels.json and copied into no channel;
               held to M3U_MAX_EPG_HINT anyway.
      A pending #EXTINF  belongs to the one entry it opens.
    """
    channels: list[dict[str, Any]] = []
    warnings: list[str] = []
    pending: tuple[dict[str, str], str] | None = None
    extgrp = ""
    vlcopt: dict[str, str] = {}
    kodiprop: dict[str, str] = {}
    epg_hint = ""
    skipped_scheme = 0
    skipped_orphan = 0
    skipped_no_url = 0
    over_cap = 0
    regrouped = 0
    seen_groups: set[str] = set()
    is_playlist = False
    bounds: dict[str, int] = {}

    if isinstance(text, str):
        if text.startswith("\ufeff"):
            text = text[1:]
        lines: Any = text.split("\n")
    else:
        lines = text
    first = True

    for raw in lines:
        if first:
            first = False
            if raw.startswith("\ufeff"):
                raw = raw[1:]
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTM3U"):
            is_playlist = True
            attrs, _ = parse_attrs(line[len("#EXTM3U"):])
            hint = attrs.get("url-tvg") or attrs.get("x-tvg-url") or ""
            if len(hint) > M3U_MAX_EPG_HINT:
                bound_count(bounds, "epgHint")
            elif hint:
                epg_hint = hint
            continue
        if line.startswith("#EXTINF:"):
            is_playlist = True
            if pending is not None:
                skipped_no_url += 1
            pending = parse_extinf(line)
            continue
        if line.startswith("#EXTGRP:"):
            extgrp = cut_text(line[len("#EXTGRP:"):].strip(), M3U_MAX_GROUP_TEXT, "groupText", bounds)
            continue
        if line.startswith("#EXTVLCOPT:"):
            key, _, value = line[len("#EXTVLCOPT:"):].partition("=")
            vlcopt[key.strip().lower()] = value.strip()
            continue
        if line.startswith("#KODIPROP:"):
            key, _, value = line[len("#KODIPROP:"):].partition("=")
            kodiprop[key.strip().lower()] = value.strip()
            continue
        if line.startswith("#"):
            continue
        # Any other line is the pending entry's location (VLC semantics), even
        # a bare path or free text: those fail the allow-list and are counted.
        if pending is None:
            skipped_orphan += 1
            vlcopt, kodiprop = {}, {}
            continue
        url = line
        if len(url) > M3U_MAX_URL:
            bound_count(bounds, "url")
        elif not is_stream_url(url):
            skipped_scheme += 1
        elif len(channels) >= MAX_CHANNELS:
            over_cap += 1
        else:
            attrs, title = pending
            channel = make_channel(attrs, title, url, extgrp, vlcopt, kodiprop, warnings, len(channels) + 1, bounds)
            group = channel["group"]
            if group not in seen_groups:
                if len(seen_groups) >= MAX_GROUPS and group != UNGROUPED:
                    channel["group"] = group = UNGROUPED
                    regrouped += 1
                seen_groups.add(group)
            channels.append(channel)
        pending = None
        vlcopt, kodiprop = {}, {}

    if pending is not None:
        skipped_no_url += 1
    # D-M3U-4, rule 15: every count here is the user's number, so each
    # sentence is read for one as well as for many (counted_sentence).
    if skipped_scheme:
        warnings.append(counted_sentence(skipped_scheme, "%d entry skipped: unsupported URL scheme",
                                         "%d entries skipped: unsupported URL scheme"))
    if skipped_orphan:
        warnings.append(counted_sentence(skipped_orphan, "%d URL line without #EXTINF skipped",
                                         "%d URL lines without #EXTINF skipped"))
    if skipped_no_url:
        warnings.append(counted_sentence(skipped_no_url, "%d #EXTINF entry without a URL skipped",
                                         "%d #EXTINF entries without a URL skipped"))
    if over_cap:
        warnings.append("truncated to %s (%s)" % (
            counted_sentence(MAX_CHANNELS, "%d channel", "%d channels"),
            counted_sentence(over_cap, "%d entry skipped", "%d entries skipped")))
    if regrouped:
        warnings.append("group count capped at %d; %s under %s" % (
            MAX_GROUPS, counted_sentence(regrouped, "%d channel listed", "%d channels listed"), UNGROUPED))
    warnings.extend(bound_warnings(bounds))
    assign_ids(channels)
    return {"channels": channels, "warnings": warnings, "epgUrlHint": epg_hint, "isPlaylist": is_playlist}


def name_id_key(name: Any) -> str:
    """The `n:` base of a channel name, or "" when the name cannot key one.

    Mirrors Model.nameIdKey. The name is normalized through the shared
    normalize_text, so re-casing or re-punctuating a title does not move the
    id. A name that normalizes to nothing cannot key anything, and neither can
    make_channel's last-resort `Channel <n>`: that n is the row's POSITION in
    the file, so keying on it would move the id whenever the provider inserts
    a row above -- worse than the URL hash it would replace.
    """
    norm = normalize_id_text(name)
    if norm == "" or _GENERATED_NAME.match(norm):
        return ""
    return "n:" + fnv1a32(norm)


def suffix_ids(bases: list[str]) -> list[str]:
    """`#2`, `#3`... on a repeated base so every row stays addressable."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for base in bases:
        count = seen.get(base, 0) + 1
        seen[base] = count
        out.append(base if count == 1 else "%s#%d" % (base, count))
    return out


def channel_ids(channels: list[dict[str, Any]], scheme: int = CHANNEL_ID_SCHEME) -> list[str]:
    """Every channel's id, in playlist order (mirror: Model.channelIds).

    Scheme 1: `t:<tvg-id>` when that tvg-id is unique in the playlist, else
    `u:<fnv1a32(url)>`, with `#2`, `#3`... on a repeat.

    Scheme 2 is scheme 1 with ONE substitution: a row that would fall back to
    the URL hash uses `n:<fnv1a32(normalize_text(name))>` instead, and only
    when that name key is unique across the whole playlist. Every other row
    keeps the exact id it already had.

    Doing it as a substitution rather than as a third branch of the base rule
    is what makes the upgrade safe, and it took a failing test to find that
    out. Recompute the suffixes over the new stream instead and a list with
    two rows on one URL re-uses one row's OLD id for the OTHER row -- the
    saved favorite still resolves, silently, to a different channel, which is
    the exact failure this change exists to stop. As a substitution, a
    scheme-2 id is either the row's own scheme-1 id or an `n:` id that has
    never existed before, so no id can ever change meaning.

    The uniqueness test on the name is the other half. A name two rows share
    cannot tell them apart, so an HD/SD twin pair or two feeds of one channel
    keep their URL ids rather than being merged into one favorite. The test
    runs on the HASHED key, so an fnv1a32 collision between two different
    names is handled by the same rule: both sides keep their URL ids.

    Names are counted over EVERY channel, including the ones that take a `t:`
    id. Counting only the rest buys 33 more surviving ids on the user's
    1,833-channel sports list (99.1 per cent against 97.3) at the price of
    coupling the name column to the tvg-id column: a tvg-id appearing or
    ceasing to be unique would then move a DIFFERENT row's id. The name pool
    is kept independent of anything but names.

    ACCEPTED LIMIT, UNRESOLVED AND NOT DESIGNED AROUND (D-ID-1). The
    uniqueness test above is answered from ONE snapshot of the playlist, and
    uniqueness is a property that only exists ACROSS snapshots. When two rows
    share a name today the test refuses both, which looks safe and is only a
    DEFERRAL: the day the provider drops one member of the pair, the survivor
    is suddenly unique, takes the `n:` key, and inherits any favorite that
    meant the row which went away. That is a silent WRONG channel, which is
    worse than the silent loss this whole change exists to stop -- the same
    failure mode that made scheme 2 a substitution rather than a third branch,
    reappearing on a longer timescale.

    Measured with name_id_key over the user's four real lists:

      USChannels.m3u     3,335 rows, 26 colliding name groups,  55 rows, largest 3
      SportsPPVAll.m3u   1,833 rows, 39 colliding name groups,  78 rows, largest 2
      Kids.m3u              48 rows,  0
      Default.m3u            5 rows,  0

    So at most 133 rows of 5,221 are exposed, and only if a provider removes a
    member of a colliding pair while the user holds a reference to it. Nobody
    has a second snapshot of these lists over time, so the rate is UNKNOWN,
    not small: the number above bounds how many rows could be affected, not
    how often it happens.

    What would settle it: keep the previous playlist's name pool in the cache
    and refuse to hand a freed `n:` key to a survivor -- a key that was ever
    shared stays burned. That needs a second snapshot to design against and a
    cache field this version does not have, so it is recorded here rather than
    guessed at. Until then the exposure is accepted, measured and named.
    """
    legacy = legacy_channel_ids(channels)
    return legacy if scheme < CHANNEL_ID_SCHEME else substitute_name_ids(channels, legacy)


def legacy_channel_ids(channels: list[dict[str, Any]]) -> list[str]:
    """Scheme 1, and the base every scheme-2 id is built from."""
    tvg_counts: dict[str, int] = {}
    for channel in channels:
        tvg = channel.get("tvgId", "")
        if tvg:
            tvg_counts[tvg] = tvg_counts.get(tvg, 0) + 1
    return suffix_ids([
        "t:" + channel.get("tvgId", "") if channel.get("tvgId") and tvg_counts[channel["tvgId"]] == 1
        else "u:" + fnv1a32(channel.get("url", ""))
        for channel in channels
    ])


def substitute_name_ids(channels: list[dict[str, Any]], legacy: list[str]) -> list[str]:
    """The one substitution scheme 2 makes on top of scheme 1. Separate from
    channel_ids so channel_id_remap can hash every URL once instead of twice:
    measured on the user's 3,335-channel list that is 80 ms against 123 ms,
    and the helper's budget is 10,000 channels parsed in under a second."""
    name_keys = [name_id_key(channel.get("name", "")) for channel in channels]
    name_counts: dict[str, int] = {}
    for key in name_keys:
        if key:
            name_counts[key] = name_counts.get(key, 0) + 1
    return [
        name_keys[index] if legacy[index].startswith("u:") and name_keys[index] and name_counts[name_keys[index]] == 1
        else legacy[index]
        for index in range(len(legacy))
    ]


def assign_ids(channels: list[dict[str, Any]], scheme: int = CHANNEL_ID_SCHEME) -> None:
    """Stable ids per ARCHITECTURE.md decision 6, written onto the channels."""
    for channel, value in zip(channels, channel_ids(channels, scheme)):
        channel["id"] = value


def channel_id_remap(channels: list[dict[str, Any]]) -> dict[str, str]:
    """{scheme-1 id: scheme-2 id} for the rows the scheme change moves.

    Computable from any channel list whose URLs have not rotated yet, which is
    the ordinary upgrade: the fix lands, then some day the password changes.

    Idempotent with no marker anywhere in state.json, and no schema change of
    any kind. Because scheme 2 is a substitution (channel_ids), every key of
    this map is the scheme-1 id of a row that now answers to an `n:` id, and
    an `n:` id is never a key. So after one pass nothing in the state holds a
    key and a second pass moves nothing. `test_no_key_is_also_a_new_id` pins
    that invariant: it is what makes the whole upgrade safe, so it is checked
    rather than asserted in prose.
    """
    old = legacy_channel_ids(channels)
    new = substitute_name_ids(channels, old)
    return {before: after for before, after in zip(old, new) if before != after}


def remap_state_ids(state: dict[str, Any], remap: dict[str, str]) -> int:
    """Move every channel reference state.json persists (Model.remapStateIds).

    Returns the number of references moved. Favorites keep their order and one
    that lands on a favorite already in the list is merged rather than
    duplicated -- which is possible, because favorites are global across
    sources (ARCHITECTURE-SOURCES.md D14) and another source may already have
    contributed the target id. Recents are merged the same way, most recent
    entry kept: they are keyed by id exactly as favorites are, and review
    found only favorites were being de-duplicated, so two rows landing on one
    id left the guide rendering the channel twice.

    Deliberately tolerant of a RAW state dict, not only a normalized one: the
    file this runs against is rewritten in place (remap_state_file) so that
    keys this helper version does not know survive the write. A field of an
    unexpected shape is left exactly as it is rather than coerced.
    """
    if not remap:
        return 0
    moved = 0
    items = state.get("favorites")
    if isinstance(items, list):
        favorites: list[Any] = []
        for item in items:
            target = remap.get(item, item) if isinstance(item, str) else item
            if target != item:
                moved += 1
            if target not in favorites:
                favorites.append(target)
        state["favorites"] = favorites
    entries = state.get("recents")
    if isinstance(entries, list):
        recents: list[Any] = []
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                recents.append(entry)
                continue
            current = entry.get("id")
            target = remap.get(current) if isinstance(current, str) else None
            if target is not None:
                entry["id"] = target
                moved += 1
            key = entry.get("id")
            if isinstance(key, str):
                if key in seen:
                    continue
                seen.add(key)
            recents.append(entry)
        state["recents"] = recents
    for name in ("lastPlayed", "session"):
        entry = state.get(name)
        if not isinstance(entry, dict):
            continue
        current = entry.get("id")
        target = remap.get(current) if isinstance(current, str) else None
        if target is not None:
            entry["id"] = target
            moved += 1
    return moved


def remap_state_file(path: str, channels: list[dict[str, Any]]) -> int:
    """Rewrite state.json's channel references onto the current id scheme.

    Runs after a successful playlist fetch, when the caller named a state
    directory explicitly (cmd_playlist), and writes only when something
    actually moves -- which is at most once per state file, ever. It cannot
    become a periodic writer, because after the first pass the map moves
    nothing.

    What the running shell does with this write, MEASURED (D-SRC-19, as
    re-measured in rounds 13 and 14): its FileView RELOADS state.json after
    this helper's atomic rename (spikes/filewatch, R23g, idle and under
    load), and since round 14 that holds for the first session after a fresh
    install too -- the service re-arms the watch once its start-up check has
    created the directory (R24c; before that, a session whose state
    directory did not exist when it first loaded saw no change all session).
    The reloaded text is not the service's own, so it is a FOREIGN write:
    applied when the service holds no unsaved change, and three-way MERGED
    into memory when it does (Model.mergeForeignState, R24a), so neither
    this write nor the change waiting to be saved is lost. Rounds 9 to 12
    said the shell never reloads after this rename; that was measured on
    rigs lost with /tmp, and the dir-absent first session is the one shape
    that reproduces it. For THIS write the remap is harmless either way: the
    service's active-source fetch is the one call site that passes
    --state-dir (D-ID-1), and the service remaps its own in-memory state
    onto the same scheme when it applies the list (Service.adoptIdScheme,
    D-ID-3), so the two agree. The service does not pass --state-dir while
    it is in the no-write mode (R24e), so this never writes a file the
    shell has refused to write. A symlink at the path is written through to
    its target, or left alone when it leads nowhere (R24b).

    The write edits the RAW document. An earlier version rebuilt it from
    normalize_state, which is a whitelist: every key this helper version does
    not know -- a field a newer version wrote, or an older one -- was silently
    dropped on a write the user never asked for. Moving four fields is the
    whole remit, so four fields are what it touches.
    """
    try:
        target = state_file_target(path)
    except HelperError:
        return 0
    raw = read_json(target)
    if not isinstance(raw, dict):
        return 0
    remap = channel_id_remap(channels)
    if not remap:
        return 0
    updated = dict(raw)
    moved = remap_state_ids(updated, remap)
    if moved:
        write_state_file(path, target, updated)
    return moved


