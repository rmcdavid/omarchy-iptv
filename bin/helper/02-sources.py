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


# D-SINK-86 (the owner, 2026-11-08): what no host NAME may hold. A name that
# holds one of these seven (five, and since D-SINK-92 the two brackets), a second `:` (one port is fine), the reader's
# whitespace (URL_SPACE_CHARS) or an invisible format character
# (HOST_FORMAT_RANGES) is refused: by validate_source_url as `invalid`, and
# by the connection layer before any lookup, on every hop (03-io-playlist.py:
# resolve_within, bounded_create_connection, check_proxied, the request each
# hop opens, whose host urllib holds percent-decoded, and both redirect
# handlers). No DNS name holds any of them. `@` ends a userinfo and `%` opens
# an escape (`u%40h` is a request for `u@h`); `;`, `=` and `&` are
# D-SINK-30's parameter delimiters; a colon past the port's belongs to a
# userinfo or a second port (http.client splits at the LAST colon, so
# `user:pass@host` is a lookup of `user:pass@host`); and a format character
# draws as nothing while IDNA's nameprep maps some away (`h<U+00AD>.test` is
# looked up as `h.test`), so the name a user reads is not the name asked
# for. Mirrored by Model.hostNameRefused over the shared source-urls fixture.
#
# D-SINK-92 (2026-11-09): and `[` and `]`, which no DNS name holds either.
# A bracket is URL syntax only around an IPv6 literal in a URL's authority;
# a host handed to a connection has had a literal's brackets taken off
# (http.client and urlsplit both remove them), so a bracket left in a name
# is the provider's text -- `http://%5B::1%5Dx.test/` is a request for
# `[::1]x.test`, which http.client keeps whole and the resolver would be
# handed, colons and all -- and so is a fullwidth bracket the idna codec
# folds to one (`a<U+FF3B>b.test` is handed on as `a[b.test`).
HOST_NAME_REFUSED_CHARS = "@%;=&[]"
# Unicode category Cf, every code point of it, as (first, last): what Python
# 3.14's unicodedata (Unicode 16.0) and node 26's \p{Cf} (17.0) both answer.
# Explicit rather than unicodedata.category, so both mirrors refuse one set
# whatever either engine's Unicode version; each suite holds its table to its
# engine's category over the whole range (test_host_names.py, Model.test.js)
# and the fixture pins both ends of every range in both mirrors.
HOST_FORMAT_RANGES = ((0x00AD, 0x00AD), (0x0600, 0x0605), (0x061C, 0x061C), (0x06DD, 0x06DD),
                      (0x070F, 0x070F), (0x0890, 0x0891), (0x08E2, 0x08E2), (0x180E, 0x180E),
                      (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x2064), (0x2066, 0x206F),
                      (0xFEFF, 0xFEFF), (0xFFF9, 0xFFFB), (0x110BD, 0x110BD), (0x110CD, 0x110CD),
                      (0x13430, 0x1343F), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A), (0xE0001, 0xE0001),
                      (0xE0020, 0xE007F))
_HOST_NAME_REFUSED = frozenset(HOST_NAME_REFUSED_CHARS + URL_SPACE_CHARS).union(
    chr(code) for first, last in HOST_FORMAT_RANGES for code in range(first, last + 1))
# What an IPv6 literal's zone may hold: _IPV6_LITERAL's `%25[A-Za-z0-9._~-]+`.
_ZONE_CHARS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._~-")


def _ipv6_literal_text(text: str) -> bool:
    """Is `text` an IPv6 address without its brackets, with at most a zone
    of _ZONE_CHARS after a `%` -- decoded (`eth0`, as a request holds it) or
    not (`25eth0`, as a URL spells it)? Imports ipaddress only for text
    whose address part holds a colon."""
    address, sep, zone = text.partition("%")
    if ":" not in address or (sep and (zone == "" or not _ZONE_CHARS.issuperset(zone))):
        return False
    import ipaddress
    try:
        ipaddress.IPv6Address(address)
    except ValueError:
        return False
    return True


def host_name_refused(text: Any, with_port: bool = False) -> bool:
    """D-SINK-86: does this host NAME hold what no name may hold?

    `text` is a host as a connection is handed it (no port, and an IPv6
    literal without its brackets, which http.client and urlsplit have taken
    off), or, `with_port`, a host[:port] as a request object holds it, where
    one colon is the port's. An IPv6 literal is no name: its colons and its
    zone's `%` are its own, so a bare one passes where no port can follow
    it, and, `with_port`, a leading bracketed one is set aside when nothing
    or a port's colon follows its `]`. Any other bracket is refused
    (D-SINK-92, 2026-11-09): text after a literal's `]` (`[::1]x.test`,
    which http.client keeps whole, brackets and colons included, and would
    hand the resolver), a bracket anywhere else, and with no port any
    bracket at all, since a connection is never handed a literal's. Every
    character is asked once against one frozenset, so the cost is linear;
    nothing here looks anything up. Model.hostNameRefused is the validator's
    half.

    D-SINK-88 (2026-11-08): and a name that is not ASCII is judged again in
    its NFKD form, which holds every refused character the resolver path can
    read in it. CPython's socket hands a str host to the C resolver through
    the idna codec, whose nameprep removes stringprep's B.1 characters, case
    folds by B.2 and then applies NFKC (Unicode 3.2), label by label, so
    `user<U+FF1B>sid.test` passed the code points above and was looked up as
    `user;sid.test`. Judging the NFKC form, as this did first, missed some:
    composition only ever REMOVES a refused character (`=` and U+0338
    compose to U+2260), and B.2 can block a composition that NFKC alone
    makes -- it maps the combining mark U+0345 to the letter U+03B9 -- so
    `sid<U+FF1D><U+0345><U+0338>x.test` folds under NFKC to a name holding
    U+2260 and no `=`, while the codec hands the resolver `xn--sid=x-pod61g.test`
    (the review of 95f1bb9, 2026-11-08). The decomposed form never
    composes, and the D-SINK-86 suite on the dev branch holds, over every
    code point, that B.1, B.2 and Unicode 3.2's decompositions add no
    refused character the current NFKD of the same code point lacks, so the
    rule needs neither nameprep's tables nor its version. The fold is the
    running Unicode's, which refuses 73 code points beyond the code-point
    rule: the 70 nameprep folds, U+FE13 and U+FE14 (unassigned in 3.2, which
    the codec hands on unfolded), and U+2260 itself, which only NFKD reads
    as `=`; since D-SINK-92 refuses the brackets, four more, 77: U+FF3B and
    U+FF3D, which the codec folds to `[` and `]`, and U+FE47 and U+FE48,
    which only the running Unicode does. A colon the fold adds is a colon in
    the name, never the port's.
    An ASCII name pays nothing, and the fold is asked only of a name the
    first judgment let through. Model.hostNameRefused folds the same way."""
    name = str(text or "")
    if _host_name_refused_as_written(name, with_port):
        return True
    if name.isascii():
        return False
    import unicodedata
    folded = unicodedata.normalize("NFKD", name)
    return folded != name and (folded.count(":") > name.count(":") or _host_name_refused_as_written(folded, with_port))


def _host_name_refused_as_written(name: str, with_port: bool) -> bool:
    """host_name_refused's judgment of the code points as they stand."""
    if with_port and name.startswith("["):
        close = name.find("]")
        if close != -1 and _ipv6_literal_text(name[1:close]):
            name = name[close + 1:]
            if name and not name.startswith(":"):
                return True
    elif not with_port and _ipv6_literal_text(name):
        return False
    if name.count(":") > (1 if with_port else 0):
        return True
    return not _HOST_NAME_REFUSED.isdisjoint(name)


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
    (SR15), and a host name that host_name_refused refuses (D-SINK-86).
    Messages never contain a URL."""
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
        # D-SINK-86: and a name holding what no name may hold (`@`, `%`, `;`,
        # `=`, `&`, a colon, whitespace, a format character); the bracketed
        # literal above is judged by _IPV6_LITERAL instead.
        if _BARE_HOST_CHARS.search(host) or host_name_refused(host):
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
    """Cache directory name of a normalized playlist URL (Model.sourceKey):
    the key every source added before 2026-10-29 was given, and still the
    key those records carry. A NEW source's key is random since D-SINK-48
    (allocate_source_key); nothing derives a key from a URL any more."""
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


def allocate_source_key(sources: list[dict[str, Any]], url: str, preferred: str = "",
                        draw: Any = None) -> str:
    """The record's key when the URL is known, else a NEW key with a "-2",
    "-3", ... suffix while another record already uses it.

    D-SINK-48 (lane-p2a, 2026-10-29): the new key is RANDOM, no longer
    fnv1a32 of the URL: a 32-bit hash of a credentialed URL is a check on a
    guessed password for anyone who reads the key (SR40), and the key names
    a cache folder, sits in the shell's settings mirror and in journal lines.
    Every lookup goes by the key the record stores, so nothing needs it to be
    a function of the URL; what dedupes a re-added URL is find_source_by_url
    above, as it always was. Existing keys are untouched. `preferred` is kept
    when it is a free, well-formed key; `draw` returns a 32-bit integer
    (secrets.randbits(32) unless a test hands one in). Mirror of
    Model.allocateSourceKey."""
    existing = find_source_by_url(sources, url)
    if existing is not None:
        return str(existing["key"])
    if preferred and SOURCE_KEY_RE.match(preferred) and find_source(sources, preferred) is None:
        return preferred
    if draw is None:
        import secrets
        number = secrets.randbits(32)
    else:
        number = int(draw()) % 4294967296
    base = "%08x" % number
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


def parse_attrs(text: str, past: dict[str, tuple[int, bool]] | None = None) -> tuple[dict[str, str], str]:
    """Parse `key="value" key2=value ...` from the start of `text`.

    Returns (attrs, remainder). Attribute values may contain commas; the
    remainder starts at the first character that is not an attribute.
    Keys are lower-cased; when a key repeats, the last non-empty value wins.

    `past`, when given, receives the key of every stored value that runs
    PAST where every release before D-SINK-80 ended it -- a quoted value
    past its first `"`, a bare one past its first `,`, `"` or Python
    whitespace -- mapped to (that old end's offset in the stored value,
    whether a comma-joined guide list opens there in the line, which only a
    bare value's old end can be) (own_value, the recheck of the review's F1
    and the check of its fixes, 2026-11-06).

    D-SINK-80: a URL's run is opaque to this grammar. A quoted value used to
    end at its first `"` and a bare one at its first `,`, `"` or Python
    whitespace, before any redactor saw it, and every redactor reads a `"`,
    a `,` and every whitespace but the six ASCII delimiters as URL text
    (R32a'''). So `group-title="http://myuser:pa"ss@h/x"`
    stored `http://myuser:pa`, which both redactors print as the host
    `myuser`, and the rest of the line -- `ss@h/x"`, every attribute after
    it and the real title -- became the channel's NAME, with no scheme for
    any redactor to find, in the window title, the guide, the bus and the
    notifications. For ANY attribute, read or not (`catchup-source`), and on
    #EXTM3U a cut guide hint was adopted with the username as its host.

    The rule, for each attribute, after today's match (_ATTR_QUOTED, else
    _ATTR_BARE), which decides everything outside a URL's run byte for byte:

      Quoted. The value starts at `vs` and today ends at `q`, its first `"`.
      That quote is INSIDE A URL'S RUN when a `://` (_URL_MARK, as the sinks
      that delete control characters read one) stands in the value between
      the last ASCII space before `q` and `q` -- cut_free_text's membership
      test. Then the run ends at `e`, the first of the six ASCII delimiters
      (URL_DELIMITER_CHARS) at or after `q`, or the text's end, and the value
      closes at the LAST `"` before `e` that a delimiter, a `,`, the end, or
      a run of Python whitespace reaching `e` follows (the last because a
      non-ASCII space after the closing quote ends nothing: `"URL"<NBSP>
      next="v"` reads as 0.17.0 read it, the final check of 2026-11-06); the
      walk goes on after it. With no such `"` the value is
      unterminated, as an unterminated quote is today: the walk ends at the
      attribute's start, and the rest of the line, URL whole, is the title.

      Bare. The value today is [vs, ve), ending at whitespace, `,` or `"`.
      It is inside a URL's run when a `://` STARTS in it (a mark may run
      past `ve`, through controls Python calls whitespace); then it takes
      the rest of the run, to the first delimiter at or after the later of
      `ve` and the end of the mark that runs past it, when one does.

    Why: a URL takes the rest of its run (split_groups' shape, D-SINK-78),
    and that is what both redactors read as one URL: they end it only at the
    six delimiters, so a URL stored whole redacts to its host whatever `"`,
    `,` or non-ASCII whitespace it holds. A value with no URL parses as it
    always has. Membership looks back to an ASCII SPACE, not to the six, so
    a tab between a `://` and the quote does not end it: the window title
    and the notification delete the tab and read one run. The run's END is
    the six, so an attribute a TAB separates from a URL value is still read
    (qa-attrs.m3u holds a TAB separator). That makes two run definitions in
    the helper: cut_free_text and split_groups end a run at a space only,
    and this grammar ends it at the six. They differ only for a URL holding
    a tab, VT, FF or CR, which is D-SINK-34's accepted class: no grammar can
    keep such a URL whole for the redactors, which split it there.

    The costs: an attribute glued straight after a URL value, or separated
    from it by non-ASCII whitespace only, is absorbed into the URL, and so is
    a title glued after one that holds `",` or ends in `"`; a bare URL value
    glued to the title's comma takes the title's first word. A value that
    ran past where every earlier release ended it is never stored as a guide
    hint or a logo (`past`, own_value; the review's F1 and its recheck):
    kept whole, a hint or a logo that took whatever followed it sent that
    text's credential to its own host. And a URL that itself holds `",`,
    whose own closing quote is glued to what follows it, separated from it
    by non-ASCII whitespace only, or missing, is still cut at that `",`, as
    in every release (F3): the line reads exactly as `attr="URL",<title>`
    does, and the fallback to the last `",` is what keeps that line
    whole. Linear: each
    test reads only the value the match already scanned (the quoted one from
    the last `:` before the run's first `/`; the bare one in one bounded
    search, and once more at its last `:` when a control ends it), the
    run's end is found once, and the walk resumes past it or stops."""
    attrs: dict[str, str] = {}
    pos = 0
    size = len(text)
    old = -1
    opens = False
    # A line with no `/` holds no `://`, and parses as it always has.
    urls = "/" in text
    while pos < size:
        match = _ATTR_QUOTED.match(text, pos)
        if match is not None:
            start, quote = match.span(2)
            end = match.end()
            value = match.group(2)
            # The run before the quote, from the last space. A `://` in it
            # needs a `/`, and none can start before the last `:` ahead of the
            # run's first `/` (only controls stand between a mark's `:` and
            # its `/`), so the search starts there: a run of colons costs one
            # attempt, not one each (D-PERF-13's shape).
            low = max(start, text.rfind(" ", start, quote) + 1)
            slash = text.find("/", low, quote) if urls else -1
            if slash != -1 and _URL_MARK.search(text, max(low, text.rfind(":", low, slash)), quote) is not None:
                run = _URL_DELIMITER.search(text, quote)
                run_end = run.start() if run is not None else size
                # The run's last character that is not Python whitespace (a
                # run holds none of the six, so only the non-ASCII spaces,
                # U+001C..U+001F and U+0085): each run is walked once.
                tail = run_end
                while tail > quote + 1 and text[tail - 1].isspace():
                    tail -= 1
                close = tail - 1 if text[tail - 1] == '"' else text.rfind('",', quote, run_end)
                if close < 0:
                    break
                value = text[start:close]
                end = close + 1
                if close != quote:
                    # In the stored value's coordinates: the value is stripped
                    # below, so its leading whitespace is taken off.
                    old = quote - start - (len(value) - len(value.lstrip()))
        else:
            match = _ATTR_BARE.match(text, pos)
            if match is None:
                break
            start, end = match.span(2)
            # A `://` that starts in the value either ends in it, which one
            # bounded search finds, or runs past its end. That one passes the
            # character that ended the value, so that character is a control
            # (whitespace to Python, a mark's filler to _URL_MARK), and it
            # starts at the value's LAST `:`, since a mark holds no other.
            last = None
            if urls and end < size and (text[end] < " " or "\x7f" <= text[end] <= "\x9f"):
                colon = text.rfind(":", start, end)
                last = _URL_MARK.match(text, colon) if colon != -1 else None
            if urls and (last is not None or _URL_MARK.search(text, start, end) is not None):
                run = _URL_DELIMITER.search(text, max(end, last.end()) if last is not None else end)
                grown = run.start() if run is not None else size
                if grown != end:
                    # A bare value starts with no whitespace, so this is its
                    # offset in the stored value. A list opening is judged in
                    # the LINE at the old end, delimiters after the comma
                    # allowed, as hint_first_entry reads one (`A, B`).
                    old = end - start
                    opens = _HINT_LIST_COMMA.match(text, end) is not None
                end = grown
            value = text[start:end]
        key = match.group(1).lower()
        stripped = value.strip()
        if stripped or key not in attrs:
            attrs[key] = stripped
            if past is not None:
                if old >= 0:
                    past[key] = (old, opens)
                else:
                    past.pop(key, None)
        old = -1
        opens = False
        pos = end
    return attrs, text[pos:]


def own_value(value: str, entry: tuple[int, bool], listed: bool) -> str:
    """The part of a stored attribute value that is its OWN, for a value that
    ran past its old end (`entry`, parse_attrs' `past`: the old end's offset
    and whether a guide list opens there) -- or "" when it absorbed what
    came after it, so it is no address to fetch. The recheck of the review's
    F1 and the check of its fixes (2026-11-06): keeping a URL value whole to
    its run's end (D-SINK-80) let a bare `url-tvg=A,<anything>` or
    `tvg-logo=A,<anything>` take whatever the provider glued after the
    comma, and only the shapes absorbed_attribute reads (a raw `"`,
    `,key=scheme://`) were refused, so `,x-tvg-url='B'`, `,=B`,
    `,username=U,password=P` and a bare logo list sent their text,
    credentials and all, to the first URL's host, which no release before
    D-SINK-80 did: a bare value ended at its first `,`.
    Decided where the absorption happens, not by the shape of the text. The
    value is its old end's piece, exactly what 0.17.0 stored, when it ran
    past by its trailing comma alone (`A,` before a delimiter: nothing after
    the comma was taken), or, for a hint (`listed`), when a comma-joined
    list opens at that end (`A,https://B`, `A, https://B`), read as its
    first entry (D-SINK-82): so no later entry is ever stored, and no shell,
    however old, fetches one. Anything else is "": a quoted value's old end
    is its `"`, which neither case allows. The value stays whole for the
    redactors in every other attribute.
    The cost, stated: a bare hint or logo holding a `,` or a non-ASCII space
    in its own text (`?ch=1,2`, `w_100,h_100/...`), or glued to the title's
    comma, is not used; 0.17.0 cut it there and fetched the piece before
    it, which for a credential holding one was the username as the host."""
    old, opens = entry
    if value[old:] == "," or (listed and opens):
        return value[:old]
    return ""


# parse_extinf's duration, compiled once rather than looked up in re's cache
# on every #EXTINF line (D-PERF-13).
_EXTINF_DURATION = re.compile(r"\s*(-?\d+(?:\.\d+)?)?")


def parse_extinf(line: str, past: dict[str, tuple[int, bool]] | None = None) -> tuple[dict[str, str], str]:
    """#EXTINF:<duration> [attrs],<title> -> (attrs, title).

    The comma is optional: `#EXTINF:-1 tvg-id="x" Name` yields title "Name".
    `past` is parse_attrs'.
    """
    body = line[len("#EXTINF:"):]
    match = _EXTINF_DURATION.match(body)
    body = body[match.end():] if match else body
    attrs, rest = parse_attrs(body, past)
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
    """Allow-listed scheme with a non-empty host; never option-looking (D-QA-07);
    never a form that makes the player LISTEN (D-SINK-42, stream_listen_refusal).
    player_target re-checks every cached URL through this at play time, so a
    cache written before the rule cannot open a port either."""
    return stream_form_ok(url) and stream_listen_refusal(url) == ""


def stream_form_ok(url: str) -> bool:
    """The allow-listed scheme with a non-empty host, never option-looking:
    is_stream_url before D-SINK-42, kept apart so parse_m3u can count a
    listening form as itself rather than as an unsupported scheme.

    No control character (C0, DEL, C1) anywhere, either: urlsplit reads the
    host past a NUL and mpv's JSON IPC ends the string at it, so
    `http://127.0.0.1:631<NUL>@p.example/x` was the playlist's own host to
    every rule here and 127.0.0.1:631 to the player (measured through the
    shipping playlist verb and apply_channel, the recheck of D-SINK-41/42)."""
    if url.startswith("-") or _CONTROL_CHARS.search(url):
        return False
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return parts.scheme.lower() in STREAM_SCHEMES and bool(parts.hostname)


# D-SINK-42 (2026-10-29). The URL forms that make mpv's FFmpeg BIND a socket
# others can send to, measured with mpv 0.41.0 / FFmpeg n9.0.1 inside
# `unshare -rn` (loopback only): udp://0.0.0.0:P and udp://[::]:P bind every
# interface, udp://127.0.0.1:P binds that address (an input binds the URL's
# host), rtp:// unicast binds its port and its RTCP port on 0.0.0.0, srt
# mode=listener binds P and mode=rendezvous binds P, and `localport`,
# `localaddr` and `localrtpport` move the bind; a multicast group
# (udp://@239.x:p) binds the GROUP address, which only that group's traffic
# reaches. rtmp `listen=1`, rtmp_listen, rtsp `?listen`, `?rtsp_flags=listen`
# and http `?listen=1` bound nothing (FFmpeg reads no option from those
# URLs), and tcp:// is not a stream scheme. So: udp and rtp only to a
# multicast literal, srt only as a caller, and none of these parameter names
# on ANY stream URL (the owner's rule; the measured binders and the aliases
# FFmpeg's udp, rtp, tcp, rtmp and rtsp protocols give them).
LISTEN_PARAMS = frozenset({
    "listen", "listen_timeout", "rtmp_listen", "rtsp_flags",
    "localport", "local_port", "localaddr", "local_addr",
    "localrtpport", "local_rtpport", "localrtcpport", "local_rtcpport",
    "reuse", "reuse_socket",
})
MULTICAST_ONLY_SCHEMES = ("udp", "rtp")


def stream_params(url: str) -> list[tuple[str, str]]:
    """The (name, value) pairs FFmpeg reads off a stream URL: everything after
    the FIRST `?` -- a `#` does not end it, unlike urlsplit's query, which is
    how `srt://h:1#?mode=listener` would have slipped past -- split at `&`,
    each name cut at its `=`. Each name is read as FFmpeg n9.0.2 reads it
    (libavformat/utils.c find_opt: percent-decoded into a C string that its
    option lookup reads up to the first NUL, so `mode%00=listener` sets
    srt's `mode` and `sources%00x` is `sources`; the review of 3ba4044 read
    it upstream and measured it with ffprobe), and is then compared
    case-folded and trimmed, which FFmpeg does not do: stricter, never
    looser. FFmpeg also decodes a `+` to a space, which no option's name
    holds, so a `+` before the NUL makes a name no option's either way, and
    is left as written. The value is returned as written."""
    mark = url.find("?")
    if mark == -1:
        return []
    pairs = []
    for item in url[mark + 1:].split("&"):
        name, _, value = item.partition("=")
        name = urllib.parse.unquote(name)
        if "\x00" in name:
            name = name.partition("\x00")[0]
        pairs.append((name.strip().lower(), value))
    return pairs


def stream_listen_refusal(url: str) -> str:
    """"" when the URL opens no listening socket by its form, else why:
    `multicast_only` (udp or rtp to anything but a multicast literal),
    `listener` (srt in a mode other than caller, or a LISTEN_PARAMS name)."""
    return _listen_refusal(url, stream_scheme(url), url_host(url))


def _listen_refusal(url: str, scheme: str, host: str, params: list[tuple[str, str]] | None = None) -> str:
    if params is None:
        params = stream_params(url)
    if any(name in LISTEN_PARAMS for name, _ in params):
        return "listener"
    if scheme == "srt":
        for name, value in params:
            if name == "mode" and value.strip().lower() != "caller":
                return "listener"
    if scheme in MULTICAST_ONLY_SCHEMES and host_class(host) != "multicast":
        return "multicast_only"
    return ""


# D-SINK-87 (the owner, 2026-11-08): no channel stream address that names a
# host the player would read in a form host_name_refused refuses is handed to
# the player, which reads the host itself and looks it up. The helper cannot
# ask the player which reading it takes, so where the two could differ the
# address is refused by ANY reading rather than one picked, each asked of
# host_name_refused itself (no second rule):
#   1. the authority's host[:port] as written, after the netloc's LAST `@`
#      (where urlsplit and FFmpeg both end a userinfo, and both end the
#      authority at the first `/`, `?` or `#`), judged with its port: FFmpeg
#      reads a port as the digits up to the next colon and urlsplit reads no
#      port at all (rc-p1b's `127.0.0.1:631:80`), so what follows a port is
#      judged too (`h.test:80;sid=x`, `h.test:80:81`). Its form is held to
#      SR15's, as validate_source_url holds a source's: a port is ASCII
#      digits or nothing (`user:123secret` is host `user`, port 123, to
#      FFmpeg's av_url_split: the username alone, looked up), and a bracket
#      holds an IPv6 literal (av_url_split reads a bracket's content as the
#      host, so `[v1.a:b]`, which urlsplit accepts as an IPvFuture literal,
#      is the name `v1.a:b`), so a `[` or `]` anywhere else, or text between
#      a literal's `]` and its port's colon, is refused. urlsplit (Python
#      3.14) refuses a netloc holding only one kind of bracket; holding both,
#      it refuses text before a `[` in the host[:port] after the last `@`, or
#      between its `]` and a port's colon, and otherwise requires the host
#      (the bracket's content, or with no `[` there the text up to the first
#      colon) to be an IPv6 address or IPvFuture-shaped. So with the `[` in
#      the userinfo it reads `http://a[@v1.evil]x/` as the host `v1.evil]x`,
#      an IPvFuture match, which av_url_split reads the same way, and this
#      holds the whole form itself rather than leaning on urlsplit (the
#      reviews of 95f1bb9 and 3ba4044).
#      That form is what makes urlsplit's own reading, the hostname every
#      other stream rule here takes, a part of this one: that hostname is
#      this text up to its port, or an IPv6 literal's content, lower-cased,
#      and lower-casing changes no code point's verdict (SubsumptionTest, in
#      the dev branch's D-SINK-87 suite, holds that over every code point,
#      and the whole claim over its vectors, IPvFuture ones among them);
#   2. for the schemes mpv percent-escapes before FFmpeg reads them, that
#      host[:port] as mpv escapes it. mpv 0.41.0's stream/stream_lavf.c
#      (read upstream 2026-11-08): open_f rewrites mms:// to mmsh://, then
#      normalize_url escapes an http, https or mmsh URL with mp_url_escape
#      (stream/stream.c), byte by byte, keeping only ASCII letters, digits,
#      `-._~` and PLAYER_URL_KEPT. The stream layer opens every such stream
#      through that copy, and the demuxer probes what it reads; an HLS one is
#      then opened again by FFmpeg from the URL as given (demux_lavf passes
#      the stream's own url, which open_f never rewrites), so an HLS stream
#      goes through both readings. So `b<U+00FC>cher.test`, one name to the
#      helper, is `b%C3%BCcher.test` on the player's first path: a name
#      holding `%`, refused. urllib.parse.quote's always-safe set is exactly
#      mp_url_escape's. rtsp, rtmp, udp, rtp and srt are not escaped, so the
#      first reading is theirs;
#   3. for udp and rtp, the hosts the address's query names
#      (STREAM_QUERY_HOST_SCHEMES). FFmpeg n9.0.2's udp.c and rtpproto.c read
#      what follows the URL's FIRST `?` as their options
#      (ff_parse_opts_from_query_string: split at `&`, every name and value
#      percent-decoded with `+` read as a space, each into a C string, so a
#      decoded NUL ends it), and ip.c resolves each entry of `sources` and
#      `block` by name (av_get_token at `,`, then getaddrinfo, no
#      AI_NUMERICHOST, and no bracket handling: an entry is handed on as it
#      is); rtp resolves them itself and pastes them, decoded, into the udp
#      URL it opens, where udp decodes them again. So every value whose name
#      stream_params reads as `sources` or `block` (`sources%00x` among them:
#      the review of 3ba4044) is read, and every entry of every reading --
#      decoded once, and for rtp twice -- is judged with no port, trimmed of
#      only the ASCII whitespace av_get_token skips. A reading holding `'` or
#      a backslash is refused whole, because av_get_token's quoting would
#      join or split its entries otherwise: the reading's, not the raw
#      value's, since `%27user,+pass%27` is the one name `user, pass` to
#      FFmpeg. So is one holding `[` or `]`: host_name_refused sets a leading
#      bracketed IPv6 literal aside as URL syntax, and here it is none, so
#      `[2001:db8::1]x` would be looked up as a name holding brackets and
#      colons (the review of 3ba4044); and one holding a NUL, where FFmpeg's
#      C string ends the list and this reading would not. rtp's once-decoded
#      reading is resolved too, so both of its readings are judged.
#      `sources=10.0.0.1,10.0.0.2` and a bare `fe80::1` play. Such a name is
#      a lookup, not a listener, so it is a `name`, never D-SINK-42's
#      `listener`. No other option the player reads from a stream URL of any
#      scheme here names a host it looks up (read in mpv 0.41.0 and FFmpeg
#      n9.0.2 on 2026-11-08; `localaddr` is a LISTEN_PARAMS name, under any
#      name stream_params reads as that one; the search is recorded in the
#      dev branch's QA-RESULTS).
# A percent-decoded reading of the authority adds nothing: a raw `%` outside
# an IPv6 zone is refused already, and urlsplit deletes tab, CR and LF before
# it reads, which is why every caller asks this AFTER the control-character
# check (stream_form_ok, stream_entry_refusal), the D-SINK-54 lesson. The
# fold of D-SINK-88 is host_name_refused's own, so every reading has it.
#
# The cost (constraint 7, D-PERF-13): _stream_name_refused accepts at once an
# authority whose host is only ASCII letters, digits and `_.-~` and whose
# port is ASCII digits or nothing. No reading can refuse it: none of those
# characters is one host_name_refused refuses or folds, it holds no bracket
# and at most one colon, its port is digits, and quote returns it unchanged.
# It is a shortcut held equal to the readings over every code point
# (FastPathTest, the dev branch's D-SINK-87 suite), not a second rule, and a
# udp or rtp address never takes it, so its query hosts are always read.
# Reading 3 has three of its own, so a provider's source list costs no more
# than its length (the review of 95f1bb9 measured a 4,096-character list of
# `::1` entries at 68 s per 10,000 lines): a reading of only
# _PLAIN_HOST_CHARS and commas (_PLAIN_READING_BYTES) is accepted at once
# (_plain_reading), for the same reason as the authority and held to the
# per-entry judgment the same way (ReadingShortcutTest, the dev branch's
# D-SINK-87 suite); each distinct entry is judged once per line, across
# every reading of every pair, however often the line repeats it (the
# review of 3ba4044 counted 340 calls for a line of `sources=::1&` pairs,
# deduplicated then only within a value); and a reading already judged on
# the line, rtp's unchanged second decode among them, is not read again.
# The query's pairs are read once per line, by the listening rule and this
# one together. A line of DISTINCT entries that are not plain (IPv6
# literals, one-code-point Unicode names) still costs a call per entry.
# For entries holding no colon that is this code's choice, not a limit: such
# an entry's verdict is the OR of its code points' own, so a per-code-point
# verdict would accept the list in linear time with the same answers (not
# taken; the review of 6371c67). Entries holding colons need the call.
# Whether to bound a list at all is the owner's open question (the D-SINK-87
# row on the dev branch): FFmpeg n9.0.2 fails the udp or rtp open before
# any lookup when a value of an option it knows is 512 raw bytes or more,
# and keeps only a string option's last value, but skips undecoded a value
# under a name it does not know, which this reading still judges
# (`SOURCES=`), so a line that plays can carry such a list.
PLAYER_ESCAPED_SCHEMES = frozenset({"http", "https", "mms", "mmsh"})
PLAYER_URL_KEPT = ":/?#[]@!$&'()*+,;=%"
# Reading 3: each scheme whose query names hosts, and how many times FFmpeg
# decodes them before it looks them up.
STREAM_QUERY_HOST_SCHEMES = {"udp": 1, "rtp": 2}
STREAM_QUERY_HOST_PARAMS = frozenset({"sources", "block"})
# av_get_token's WHITESPACES: what it skips before an entry and trims after.
_TOKEN_SPACE = " \n\t\r"
_PLAIN_HOST_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-~"
# A reading of only these is accepted at once. Asked as bytes.translate's
# deletion, which costs a 4,096-character reading about 4 us where str.strip
# over the same set cost about 39.
_PLAIN_READING_BYTES = (_PLAIN_HOST_CHARS + ",").encode("ascii")
_PORT_DIGITS = "0123456789"
# player_target's refusal: one fixed sentence, naming no host and no URL
# (the host may be a userinfo the provider spelled wrong).
STREAM_HOST_NAME_REFUSAL = ("refused a stream whose address names a host the player would read in a form no host "
                            "name or port may take; not played")


def _stream_name_refused(url: str, netloc: str, scheme: str, params: list[tuple[str, str]] | None = None) -> bool:
    """D-SINK-87's question of one location line and its urlsplit: `url` the
    line, `netloc` its netloc, `scheme` lower-cased, `params` its
    stream_params when the caller has them. The fast accept above
    (_plain_authority), never for udp or rtp, then every reading
    (_stream_name_readings)."""
    if scheme not in STREAM_QUERY_HOST_SCHEMES and _plain_authority(netloc):
        return False
    return _stream_name_readings(url, netloc, scheme, params)


def _plain_authority(netloc: str) -> bool:
    """The fast accept: is the host[:port] after the netloc's last `@` only
    _PLAIN_HOST_CHARS, then at most one colon and ASCII digits? str.strip
    over a set is quote's own idiom for "only these"."""
    host, _, port = netloc.rpartition("@")[2].partition(":")
    return not host.strip(_PLAIN_HOST_CHARS) and not port.strip(_PORT_DIGITS)


def _stream_name_readings(url: str, netloc: str, scheme: str, params: list[tuple[str, str]] | None = None) -> bool:
    """Every reading, with no shortcut: the authority (readings 1 and 2) and,
    for udp and rtp, the hosts the query names (reading 3)."""
    if _stream_authority_refused(netloc.rpartition("@")[2], scheme):
        return True
    decodes = STREAM_QUERY_HOST_SCHEMES.get(scheme, 0)
    return decodes > 0 and _stream_query_hosts_refused(url, decodes, params)


def _stream_authority_refused(hostport: str, scheme: str) -> bool:
    """Readings 1 and 2 of an authority's host[:port], and its form: a
    bracket only as a leading IPv6 literal's pair, followed by nothing or by
    a port's colon, and a port of ASCII digits or none. The whole form is
    asked here, because urlsplit (Python 3.14) checks a host's brackets only
    where its own split puts them: with a `[` in the userinfo and a `]` in
    the host it accepts an IPvFuture-shaped host such as `v1.evil]x`."""
    if hostport.startswith("["):
        close = hostport.find("]")
        if close == -1 or not _ipv6_literal_text(hostport[1:close]):
            return True
        rest = hostport[close + 1:]
        if rest and not rest.startswith(":"):
            return True
        port = rest[1:]
    else:
        if "[" in hostport or "]" in hostport:
            return True
        port = hostport.partition(":")[2]
    if port.strip(_PORT_DIGITS):
        return True
    if host_name_refused(hostport, True):
        return True
    return scheme in PLAYER_ESCAPED_SCHEMES and host_name_refused(
        urllib.parse.quote(hostport, safe=PLAYER_URL_KEPT, errors="surrogatepass"), True)


def _stream_query_hosts_refused(url: str, decodes: int, params: list[tuple[str, str]] | None = None) -> bool:
    """Reading 3: does a `sources` or `block` value name a host, in any of
    its `decodes` readings (_query_readings), that host_name_refused
    refuses? `judged` carries the entries already asked across every pair,
    so a line costs a call per DISTINCT entry however many pairs repeat
    it."""
    judged: set[str] = set()
    for reading in _query_readings(url, decodes, params):
        if _query_reading_refused(reading, judged):
            return True
    return False


def _query_readings(url: str, decodes: int, params: list[tuple[str, str]] | None = None) -> Any:
    """Each distinct reading of each `sources` or `block` value on this
    line, in order, lazily: decoded once, and for rtp (`decodes` 2) twice.
    stream_params reads the names as FFmpeg does (up to a decoded NUL) or
    more widely (case-folded, trimmed); `params` is its answer when the
    caller has it. A value already read on this line is not decoded again,
    and a reading already given (rtp's unchanged second decode among them)
    is not given again -- but decoding goes on past it, because a later
    pair's first reading can equal an earlier pair's second, and its own
    second decode is then one the earlier pair never made, and the one rtp
    hands udp when that pair is the last (FFmpeg keeps a string option's
    last value). Asked by reading 3 (D-SINK-87) and by the one-label rule
    (D-SINK-89)."""
    values: set[str] = set()
    readings: set[str] = set()
    for name, value in (stream_params(url) if params is None else params):
        if name not in STREAM_QUERY_HOST_PARAMS or value in values:
            continue
        values.add(value)
        reading = value
        for _ in range(decodes):
            reading = urllib.parse.unquote_plus(reading)
            if reading in readings:
                continue
            readings.add(reading)
            yield reading


# A decoded reading holding any of these is refused whole: av_get_token's
# quote and escape, a bracket (an entry is looked up as it is, so a
# bracketed IPv6 literal would be a name holding brackets and colons), and
# a NUL, where FFmpeg's C string ends the list.
_READING_REFUSED = ("'", "\\", "[", "]", "\x00")


def _query_reading_refused(reading: str, judged: set[str] | None = None) -> bool:
    """One decoded `sources` or `block` reading: refused whole when it holds
    one of _READING_REFUSED, accepted at once when it is only
    _PLAIN_READING_BYTES (_plain_reading), and otherwise judged entry by
    entry (_query_entries_refused), `judged` the entries already asked on
    the line."""
    if any(mark in reading for mark in _READING_REFUSED):
        return True
    if _plain_reading(reading):
        return False
    return _query_entries_refused(reading, set() if judged is None else judged)


def _plain_reading(reading: str) -> bool:
    """Reading 3's fast accept: is the reading only _PLAIN_READING_BYTES,
    plain host characters and commas? No entry of it can be refused: none of
    those characters is one host_name_refused refuses or folds, and a
    trimmed entry of them holds no colon. A shortcut held equal to
    _query_entries_refused over every code point (ReadingShortcutTest, the
    dev branch's D-SINK-87 suite), not a second rule."""
    return reading.isascii() and not reading.encode("ascii").translate(None, _PLAIN_READING_BYTES)


def _query_entries_refused(reading: str, judged: set[str]) -> bool:
    """Reading 3's judgment with no shortcut: is an entry of `reading`, split
    at `,` and trimmed of _TOKEN_SPACE as av_get_token reads it, a name
    host_name_refused refuses? An entry already in `judged` is not asked
    again; every entry asked is added to it."""
    for raw in set(reading.split(",")):
        entry = raw.strip(_TOKEN_SPACE)
        if entry in judged:
            continue
        judged.add(entry)
        if host_name_refused(entry):
            return True
    return False


def stream_host_name_refused(url: str) -> bool:
    """D-SINK-87: would the player be handed a host, by any reading of this
    stream URL (_stream_name_refused), in a form host_name_refused refuses?
    A URL urlsplit cannot read is refused. Asked by player_target after
    is_stream_url, which refuses a control character first."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return True
    return _stream_name_refused(url, parts.netloc, parts.scheme.lower())


# D-SINK-91 (2026-11-09): an IPv6 literal whose zone is not a number. FFmpeg
# n9.0.2 never percent-decodes a URL's host, so it holds the zone as the
# address writes it (`ff02::1%25eth0`: the zone `25eth0`), and every stream
# protocol but udp and srt hands that host to the protocol beneath it
# through ff_url_join (libavformat/url.c: rtp to udp in build_udp_url, http
# and rtsp and rtmp to tcp, https and rtmps to tls and then tcp, mmsh to
# http), which brackets it only when getaddrinfo with AI_NUMERICHOST reads
# it as an IPv6 address. glibc reads a zone numerically only when it is
# digits or, on a link-local address, an interface's name, so
# `rtp://[ff02::1%25eth0]:5004` reaches udp as `udp://ff02::1%25eth0:5004`,
# and av_url_split cuts an unbracketed host at its first colon: udp looks
# up the NAME `ff02`, port 0 (read upstream, the review of 6371c67). The
# same cut makes http's tcp look up `2a00` for `[2a00:1450::1%25eth0]` and
# connect to 0.0.10.46 for `[2606:4700::1%25eth0]`, and rtp's
# `[::ffff:239.1.1.1%25eth0]` bind every interface (observed by that review
# inside an unshared network namespace, numeric hosts only). So such a
# literal is refused, on every stream scheme: udp and srt hand the zone to
# the resolver as written, and an interface's name may be present on one
# machine and gone on the next, so one rule over the literal is kept
# rather than a list of the protocols that rewrite it today. A zone of
# ASCII digits (`%252`, read as 252) and a literal with no zone play.
STREAM_ZONE_REFUSAL = "refused a stream whose IPv6 address carries a zone that is not a number; not played"


def stream_zone_refused(netloc: str) -> bool:
    """D-SINK-91: is the host after this netloc's last `@` a bracketed IPv6
    literal whose zone, as the address writes it, is not ASCII digits? No
    zone, or a host that is no bracketed literal, is no question here."""
    hostport = netloc.rpartition("@")[2]
    if not hostport.startswith("["):
        return False
    zone = hostport[1:].partition("]")[0].partition("%")
    return zone[1] != "" and not (zone[2].isascii() and zone[2].isdigit())


# D-SINK-89 (the owner, 2026-11-08: "yes, refuse one-word stream hosts from
# remote playlists too"): D-SINK-83's rule, which refuses before any lookup
# a host of ONE DNS label that the provider chose for a guide hint or a
# logo, reaches the channels too. A host a URL's space cut leaves (D-SINK-
# 34's class) is the username of `http://USER:...`, one label, and the
# player would ask the resolver, and through it the search domains'
# servers, about it. So from a playlist that is not local
# (playlist_source's `local`: a file, or an http(s) source whose last hop
# connected to a non-global address) a channel is refused when the host
# its address names is one label by dotless_host -- the authority's, as
# urlsplit reads it, which D-SINK-87's form makes the player's too -- and,
# for udp and rtp, when any entry of any reading of a `sources` or `block`
# value is (_query_readings: the names FFmpeg looks up). The playlist's own
# host is excepted, compared as DestinationPolicy.refuses_name compares it:
# host_key equal, the port not compared. A local playlist keeps one-label
# names (a LAN's own names: `tvheadend`, `hdhomerun`). A dotted IPv4 or an
# IPv6 literal is never one label; an IPv4 address written as one number
# or in hex (`16843009`) is, as it is for a hint or a logo. Asked after
# D-SINK-87's readings, which let an entry hold a colon only as an IPv6
# literal, so an entry holding a colon is no question here and costs no
# literal parse.
STREAM_LABEL_REFUSAL = ("refused a stream whose address names a host of one label, from a playlist that is not on this "
                        "machine or a local network; not played")


def stream_label_refused(url: str, host: str, scheme: str, source: dict[str, Any],
                         params: list[tuple[str, str]] | None = None) -> bool:
    """D-SINK-89: `url` a channel's address, `host` its urlsplit hostname,
    `scheme` lower-cased, `source` playlist_source's (or cached_source's)
    record of its playlist, `params` stream_params(url) when the caller has
    it. -> whether it names a host of one label the playlist may not."""
    if source.get("local"):
        return False
    home = str(source.get("host") or "")
    if dotless_host(host) and host_key(host) != home:
        return True
    decodes = STREAM_QUERY_HOST_SCHEMES.get(scheme, 0)
    if decodes == 0:
        return False
    asked: set[str] = set()
    for reading in _query_readings(url, decodes, params):
        for raw in set(reading.split(",")):
            entry = raw.strip(_TOKEN_SPACE)
            if entry in asked:
                continue
            asked.add(entry)
            if ":" not in entry and dotless_host(entry) and host_key(entry) != home:
                return True
    return False


def stream_entry_refusal(url: str, source: dict[str, Any]) -> tuple[str, str]:
    """parse_m3u's one read of a location line, with ONE urlsplit (the
    10,000-channel budget): -> (why it is not a channel, its host), the
    reason "" for a channel, `scheme` (not a stream URL: is_stream_url's
    first half, a control character included: stream_form_ok), `listener`
    (stream_listen_refusal, D-SINK-42), `local` (stream_host_refused,
    D-SINK-41), `port` (the same rule's loopback-relay half, D-SINK-57),
    `name` (the address names a host the player would read in a form
    host_name_refused refuses, D-SINK-87), `zone` (an IPv6 literal whose
    zone is not a number, D-SINK-91) or `label` (a host of one label from a
    playlist that is not local, D-SINK-89). `name`, `zone` and `label` are
    asked last, in that order: the rules before them classify a literal and
    look nothing up, so a line two rules refuse keeps the older reason, and
    the parse's host rule still answers row for row as play time's does
    (the destinations fixture, dev branch)."""
    if url.startswith("-") or _CONTROL_CHARS.search(url):
        return "scheme", ""
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname or ""
    except ValueError:
        return "scheme", ""
    scheme = parts.scheme.lower()
    if scheme not in STREAM_SCHEMES or host == "":
        return "scheme", host
    params = stream_params(url)
    if _listen_refusal(url, scheme, host, params) != "":
        return "listener", host
    # url_port's reading, from the one urlsplit: the scheme's default stands
    # only for a port the URL does not name. A port that does not parse is no
    # port, never the default -- `http://127.0.0.1:631:80/` is 631 to FFmpeg
    # (it reads digits up to the next colon) and was the playlist's own port
    # 80 here while stream_host_refused refused it at play time (rc-p1b).
    try:
        port = parts.port
        if port is None:
            port = URL_DEFAULT_PORTS.get(scheme)
    except ValueError:
        port = None
    refusal = _host_refusal(host, scheme, source, port)
    if refusal:
        return refusal, host
    if _stream_name_refused(url, parts.netloc, scheme, params):
        return "name", host
    # Each asked only where it can answer, so a plain line of a local list,
    # the 10,000-channel case, pays two tests and no call: a netloc with no
    # `[` holds no literal, and a local playlist keeps every label.
    if "[" in parts.netloc and stream_zone_refused(parts.netloc):
        return "zone", host
    if not source.get("local") and stream_label_refused(url, host, scheme, source, params):
        return "label", host
    return "", host


# D-SINK-41 (2026-10-29). The sign-in headers a playlist may attach only to
# a channel on its OWN host: anything else hands a provider-chosen
# credential, or a forged Host, to a party the provider picked.
SIGN_IN_HEADERS = frozenset({"authorization", "cookie", "proxy-authorization", "host"})


def playlist_source(kind: str, url: str, connected_class: str = "", first_class: str = "") -> dict[str, Any]:
    """What parse_m3u knows about the playlist it parses (D-SINK-41): the
    user-typed URL's host key, and whether the source is LOCAL -- a file the
    user pointed at, or an http(s) source whose last hop connected to a
    non-global address (DestinationPolicy.last_class). A source this
    machine could not classify is not local.

    D-SINK-57 (2026-10-29): and the typed URL's port, with whether that host
    is on LOOPBACK -- its literal or localhost name says so, or its first hop
    connected there (`first_class`) -- because on loopback the playlist's own
    host is host AND port (own_host_match)."""
    if kind == "file":
        return {"host": "", "port": None, "loopback": False, "local": True}
    host = url_host(url)
    return {"host": host_key(host), "port": url_port(url),
            "loopback": first_class == "loopback" or host_class(host) == "loopback",
            "local": connected_class not in ("", "global", "unresolved")}


def stream_host_refused(url: str, source: dict[str, Any]) -> bool:
    """A channel URL whose LITERAL host is not global (loopback, private,
    link-local, CGNAT, unspecified, reserved, a localhost name) from a
    playlist that is neither local nor on that same host. A multicast udp or
    rtp group is the ISP-multicast case and passes. A NAME that resolves to
    such an address is mpv's lookup and not seen here (ARCHITECTURE-PLAYER,
    the residuals)."""
    return _host_refused(url_host(url), stream_scheme(url), source, url_port(url))


def _host_refused(host: str, scheme: str, source: dict[str, Any], port: int | None = None) -> bool:
    return _host_refusal(host, scheme, source, port) != ""


def _host_refusal(host: str, scheme: str, source: dict[str, Any], port: int | None = None) -> str:
    """Why a channel host is not one this playlist may name: "" when it may,
    `local` (a non-global literal from a playlist that is neither local nor
    on that host), or `port`.

    `port` is D-SINK-57's scope (the lead, 2026-10-29, after the owner's "on
    this machine, only the relay's own port is the playlist's host"): a
    LOOPBACK source -- a local relay such as Threadfin or xTeVe -- is a local
    source, and a local source's channels may name the LAN (a relay passing
    an HDHomeRun or a TVHeadend stream through keeps working), but a channel
    whose literal host is loopback must be on the relay's own PORT. Any
    other port of this machine is some other service, which the relay's
    playlist did not have to name: the review's reproduction 1 again, one
    layer down, as a channel rather than a redirect. A port the source does
    not record (a cache written before sourcePort) matches none.

    rc-p1c (2026-10-29): an UNSPECIFIED literal -- 0.0.0.0, `::` and their
    spellings -- is this machine too: a connect to it reaches whatever listens
    on loopback at that port (measured inside `unshare -rn`: `0.0.0.0:P`
    reached a 127.0.0.1 listener and `::` a ::1 one, and the player played a
    loopback relay's channel at `http://0.0.0.0:<another port>/` from the
    server there). So it is held to the relay's port the same way."""
    kind = host_class(host)
    if kind in ("", "global"):
        return ""
    if kind == "multicast" and scheme in MULTICAST_ONLY_SCHEMES:
        return ""
    if source.get("local"):
        if kind in ("loopback", "unspecified") and source.get("loopback"):
            want = source.get("port")
            same = (isinstance(port, int) and not isinstance(port, bool)
                    and isinstance(want, int) and not isinstance(want, bool) and port == want)
            return "" if same else "port"
        return ""
    return "" if own_host_match(host, port, source) else "local"


def drop_sign_in_headers(channel: dict[str, Any], source: dict[str, Any], host: str | None = None) -> int:
    """Remove SIGN_IN_HEADERS from a channel whose host is not the playlist's
    own (D-SINK-41); -> how many were removed. A local FILE has no host, so
    its channels keep none of them (the owner's rule, read literally).
    `host` is the channel URL's, when the caller has it already."""
    headers = channel.get("headers")
    if not isinstance(headers, dict):
        return 0
    url = str(channel.get("url") or "")
    if host is None:
        host = url_host(url)
    # D-SINK-57: on loopback the own host is host AND port.
    if own_host_match(host, url_port(url), source):
        return 0
    dropped = [name for name in headers if name.lower() in SIGN_IN_HEADERS]
    for name in dropped:
        del headers[name]
    if not headers:
        del channel["headers"]
    return len(dropped)


def clean_header_value(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()


# What splits a group text into groups (split_groups), and so what else
# ends a run for its cut (cut_free_text, D-SINK-75), where it does: each
# group reaches the sinks on its own.
GROUP_SEPARATOR = ";"
# One group of a text that holds a `;` and a `://` (split_groups): text up to
# a `;` that separates, where a `://` (_URL_MARK) takes the rest of its run,
# to the next space, whole, `;`s and all, and a `:` that starts no `://` is
# taken alone.
GROUP_PART = re.compile("(?:[^;:]+|" + _URL_MARK.pattern + "[^ ]*|:)+")
# A `;` that stands in a URL's run: one after the first `://` of a run
# (from a space to the next), the one place GROUP_PART keeps a `;` inside a
# group; a text with none splits at every `;` (split_groups, D-PERF-13).
# Searched in " " + text, so every run, the first included, opens with the
# literal space and an attempt starts only there. An attempt reads its run
# once and never backs off (possessive): the characters before the run's
# first `://`, a run of neither space nor `:` and then each `:` that starts
# none with the run after it, then the `://`, then up to the run's end or a
# `;`. So the search is one pass, where a plain `://[^ ;]*;` would rescan a
# run from each `://` in it.
GROUP_URL_SEPARATOR = re.compile(" [^ :]*+(?:(?!" + _URL_MARK.pattern + "):[^ :]*+)*+" + _URL_MARK.pattern + "[^ ;]*+;")
# split_groups' last answer, by its text: a persistent #EXTGRP is split again
# for every channel after it, the same text each time, and consecutive
# entries often repeat one group-title. A dict changed in place (as
# MEMORY_HELD is), holding one entry.
SPLIT_GROUPS_LAST: dict[str, list[str]] = {}


def split_groups(value: str) -> list[str]:
    """`A;B;C` -> ["A", "B", "C"] (trimmed, empties and repeats dropped, the
    first of each kept in order).

    D-SINK-78: a `;` separates groups only when no `://` (_URL_MARK, read as
    the sinks that delete control characters read one) stands between it
    and the last ASCII space before it. Every redactor reads a `;` as URL
    text, in a userinfo, a path or a query, so splitting there handed each
    sink half a URL: `http://myuser:pa;ss@cdn.test/x` was listed under
    `http://myuser:pa`, shown as the host `myuser`, and `ss@cdn.test/x`
    went beside it as a group no redactor could touch. So from a `://` to
    the space that ends its run every `;` stays in its group, and the URL
    reaches the sinks whole. A space, because it ends a run at every sink,
    as it does for cut_free_text. The cost: a group written straight after
    a URL, with no space before its `;`, is part of the URL's group.

    Linear (rule 15 over R30h, lane-bounds-h): a `name not in groups` test
    per part scanned the list, k*k/2 comparisons for k parts, and a
    persistent `#EXTGRP` of up to M3U_MAX_GROUP_TEXT characters -- up to 256
    one-character parts -- is split again for every channel after it, so a
    50,000-channel list paid about 32,000 comparisons a channel. Same list,
    one pass. The `://` test is one pass too, and native: GROUP_PART takes
    each URL's run whole as it reaches it and never searches back from a
    `;`, and a text in which no `;` stands in a URL's run is split natively.
    A text split last time is answered from SPLIT_GROUPS_LAST, as a new
    list.

    D-PERF-13: GROUP_PART loops once per piece it takes, about 100 ns a
    character over 512 characters of `a:// ;` repeated, so it runs only
    where its answer can differ from the native split's: where a `;` stands
    in a URL's run (GROUP_URL_SEPARATOR). Where none does, every `;`
    separates, and GROUP_PART's parts are exactly the native split's
    non-empty pieces; empty ones are dropped below either way. A text with
    no `://` at all (url_mark_start, native on the usual text) is not
    searched, so a run of `:` with no `//` costs no attempt."""
    last = SPLIT_GROUPS_LAST.get(value)
    if last is not None:
        return list(last)
    url_separator = False
    if GROUP_SEPARATOR in value and "/" in value and url_mark_start(value) >= 0:
        # A `;` written straight after a space, or first, opens its run, so
        # no `://` can stand before it there: when every `;` is one of those
        # (`A ; B`), none is in a URL's run and the search is not needed.
        opening = value.count(" " + GROUP_SEPARATOR) + value.startswith(GROUP_SEPARATOR)
        url_separator = (value.count(GROUP_SEPARATOR) > opening
                         and GROUP_URL_SEPARATOR.search(" " + value) is not None)
    if url_separator:
        parts = GROUP_PART.findall(value)
    else:
        # No `;` in a URL's run: every `;` separates, and the native split
        # is the rule's answer at native cost.
        parts = value.split(GROUP_SEPARATOR)
    # Trimmed, first of each kept in order, the empty name dropped: one
    # native pass, where a generator per part cost about 0.2 us each.
    names = dict.fromkeys(map(str.strip, parts))
    names.pop("", None)
    groups = list(names)
    SPLIT_GROUPS_LAST.clear()
    SPLIT_GROUPS_LAST[value] = groups
    return list(groups)


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
    would be parsed as an option. Leading dashes and CLEAN_NAME_SPACE off the
    front, CLEAN_NAME_SPACE off the end (D-STATE-2; it was `^[\\s\\-]+` and
    strip(), the same set on this CPython). Model.cleanName does the same with
    the reader's class, which also takes a U+FEFF: the answer here is what the
    `n:` id is hashed from, so a U+FEFF stays."""
    return (value or "").lstrip(CLEAN_NAME_SPACE + "-").strip(CLEAN_NAME_SPACE)


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


def cut_text(value: str, limit: int, kind: str, bounds: dict[str, int] | None,
             separator: str = "") -> str:
    """D-M3U-1: `value` cut to `limit` code points (a str slice never splits
    one), and never through a URL (cut_free_text, D-SINK-75: a name or a
    group is redacted only at its sinks, after this cut), trailing whitespace
    trimmed, counted under `kind` when it was cut. A group text passes
    GROUP_SEPARATOR, so the cut drops at most its last group's run."""
    if len(value) <= limit:
        return value
    bound_count(bounds, kind)
    return cut_free_text(value, limit, separator).rstrip()


def bound_groups(groups: list[str], bounds: dict[str, int] | None) -> list[str]:
    """split_groups' list with each name cut to M3U_MAX_GROUP and at most
    M3U_MAX_GROUPS_PER_CHANNEL of them; a cut that makes two names equal
    keeps the first, as split_groups does for a repeat.

    D-PERF-13: when the first M3U_MAX_GROUPS_PER_CHANNEL names are distinct,
    none is empty and none is over M3U_MAX_GROUP, the loop below keeps each
    of them as it is and stops at the next, counting it; that answer is
    taken natively. split_groups' list is distinct and has no empty name,
    so a persistent 512-character #EXTGRP of short groups (38 of them, 16
    kept) is no longer walked name by name for every channel."""
    head = groups[:M3U_MAX_GROUPS_PER_CHANNEL]
    if head and max(map(len, head)) <= M3U_MAX_GROUP and "" not in head and len(set(head)) == len(head):
        if len(groups) > len(head):
            bound_count(bounds, "groupCount")
        return head
    out: list[str] = []
    for name in groups:
        if len(out) >= M3U_MAX_GROUPS_PER_CHANNEL:
            bound_count(bounds, "groupCount")
            break
        # cut_text's own first test, made here: a name within the cap is
        # returned as it is, and this skips the call (D-PERF-13).
        if len(name) > M3U_MAX_GROUP:
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
    # D-SINK-80 (owner, 2026-11-05): a tvg-id holding a `://` (_URL_MARK) is
    # read as absent, so the row takes an `n:` or `u:` id and joins no guide
    # at all: every guide match, by name too, publishes under the row's
    # tvg-id (match_xmltv_channel), so a row the guide matched by name before
    # loses its guide -- the stated cost (the review's F15). No playlist
    # writer read puts a URL in a tvg-id; kept, the raw `t:` id would carry
    # the WHOLE credential
    # (now that parse_attrs stores a URL value whole) to the IPC status and
    # channel replies, state.json, the player's stash and OMARCHY_IPTV_ARGS,
    # none of which redacts an id, since an id is what `play` takes back. An
    # `@` alone (`CNN.us@HD`) is no URL and is kept. The group scope stays
    # raw (D-SINK-78): hidden groups and saved scopes match on it.
    if _URL_MARK.search(tvg_id) is not None:
        tvg_id = ""
    tvg_name = cut_text(attrs.get("tvg-name", "").strip(), M3U_MAX_NAME, "tvgName", bounds)
    # Never fall back to the URL: the name is rendered everywhere (R12, D-QA-02).
    name = cut_text(clean_name(title), M3U_MAX_NAME, "name", bounds) or clean_name(tvg_name) or clean_name(tvg_id) or GENERATED_NAME_FORMAT % index
    # D-M3U-1: `extgrp` is the value that PERSISTS across entries, so it
    # arrives already cut (parse_m3u cuts it once, at its own line, and
    # counts it there); a group-title is this entry's own and is cut here.
    group_title = attrs.get("group-title", "").strip()
    group_text = cut_text(group_title, M3U_MAX_GROUP_TEXT, "groupText", bounds, GROUP_SEPARATOR) if group_title else extgrp
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
                # fullmatch: `$` in `re.match` also matches before a final
                # line break, so `Cookie%0A` passed as `Cookie\n` and slipped
                # the sign-in rule below, which compares names exactly.
                if not _HEADER_NAME.fullmatch(hname):
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
    # The name is folded once, for searchKey and nameKey alike (search_key_of).
    name_key = normalize_text(name)
    channel["searchKey"] = search_key_of(name_key, " ".join(groups) if groups else group)
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
    channel["nameKey"] = name_key
    return channel


def parse_m3u(text: Any, source: dict[str, Any] | None = None) -> dict[str, Any]:
    """Tolerant M3U/M3U8 parser.

    `source` is playlist_source() of the playlist being parsed (D-SINK-41):
    the `playlist` verb always passes it. Without it the parse knows nothing
    about where the list came from and reads it as a public source on no
    host -- every non-global literal stream host is skipped and every
    sign-in header dropped -- so a caller that forgets it fails closed.
    Each refusal is counted in `warnings` like every other skip.

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
    UNGROUPED keeps its provider groups in `searchKey`, and in `groups` when
    it has two or more. And
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
    playlist = source if isinstance(source, dict) else {"host": "", "local": False}
    skipped_name = 0
    skipped_zone = 0
    skipped_label = 0
    skipped_listen = 0
    skipped_local = 0
    skipped_port = 0
    dropped_sign_in = 0

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
            past: dict[str, tuple[int, bool]] = {}
            attrs, _ = parse_attrs(line[len("#EXTM3U"):], past)
            # A hint whose value ran past its old end keeps only its own
            # piece (own_value), "" when it absorbed what followed it; the
            # other key may still name one.
            for key in ("url-tvg", "x-tvg-url"):
                if key in past:
                    attrs[key] = own_value(attrs.get(key, ""), past[key], True)
            # Only a list's FIRST entry is stored (D-SINK-82, the check of
            # the review's fixes): the shell reads no other, and a shell
            # before the rule then has no later entry to fetch.
            hint = hint_first_entry(attrs.get("url-tvg") or attrs.get("x-tvg-url") or "")
            if len(hint) > M3U_MAX_EPG_HINT:
                bound_count(bounds, "epgHint")
            elif hint:
                epg_hint = hint
            continue
        if line.startswith("#EXTINF:"):
            is_playlist = True
            if pending is not None:
                skipped_no_url += 1
            past = {}
            pending = parse_extinf(line, past)
            # A logo whose value ran past its old end keeps only its own
            # piece (own_value): it has no list reading.
            if "tvg-logo" in past:
                pending[0]["tvg-logo"] = own_value(pending[0].get("tvg-logo", ""), past["tvg-logo"], False)
            continue
        if line.startswith("#EXTGRP:"):
            extgrp = cut_text(line[len("#EXTGRP:"):].strip(), M3U_MAX_GROUP_TEXT, "groupText", bounds, GROUP_SEPARATOR)
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
        refusal, host = ("", "") if len(url) > M3U_MAX_URL else stream_entry_refusal(url, playlist)
        if len(url) > M3U_MAX_URL:
            bound_count(bounds, "url")
        elif refusal == "scheme":
            skipped_scheme += 1
        elif refusal == "name":
            skipped_name += 1                 # D-SINK-87: a host in a form no host takes
        elif refusal == "zone":
            skipped_zone += 1                 # D-SINK-91: an IPv6 zone that is not a number
        elif refusal == "label":
            skipped_label += 1                # D-SINK-89: one label, from a list that is not local
        elif refusal == "listener":
            skipped_listen += 1               # D-SINK-42: a form that would listen
        elif refusal == "local":
            skipped_local += 1                # D-SINK-41: a LAN literal from a public list
        elif refusal == "port":
            skipped_port += 1                 # D-SINK-57: another port of this machine, from a relay
        elif len(channels) >= MAX_CHANNELS:
            over_cap += 1
        else:
            attrs, title = pending
            channel = make_channel(attrs, title, url, extgrp, vlcopt, kodiprop, warnings, len(channels) + 1, bounds)
            dropped_sign_in += drop_sign_in_headers(channel, playlist, host)
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
    if skipped_name:
        # D-SINK-87: a count, never the host (it may be a userinfo).
        warnings.append(counted_sentence(skipped_name, "%d entry skipped: its address names a host the player would read in a form no host name or port may take",
                                         "%d entries skipped: their addresses name hosts the player would read in forms no host name or port may take"))
    if skipped_zone:
        warnings.append(counted_sentence(skipped_zone, "%d entry skipped: its address is an IPv6 literal whose zone is not a number",
                                         "%d entries skipped: their addresses are IPv6 literals whose zones are not numbers"))
    if skipped_label:
        # D-SINK-89: a count, never the host (it may be a username).
        warnings.append(counted_sentence(skipped_label, "%d entry skipped: its address names a host of one label, not the playlist's own, from a playlist that is not on this machine or a local network",
                                         "%d entries skipped: their addresses name hosts of one label, not the playlist's own, from a playlist that is not on this machine or a local network"))
    if skipped_listen:
        warnings.append(counted_sentence(skipped_listen, "%d entry skipped: the stream would listen on this machine for anyone to send to",
                                         "%d entries skipped: the streams would listen on this machine for anyone to send to"))
    if skipped_local:
        warnings.append(counted_sentence(skipped_local, "%d entry skipped: a stream address on this machine or a local network, from a playlist that is not",
                                         "%d entries skipped: stream addresses on this machine or a local network, from a playlist that is not"))
    if skipped_port:
        warnings.append(counted_sentence(skipped_port, "%d entry skipped: a stream address on this machine at another port than the playlist's",
                                         "%d entries skipped: stream addresses on this machine at other ports than the playlist's"))
    if dropped_sign_in:
        warnings.append(counted_sentence(dropped_sign_in, "%d sign-in header dropped: its channel is on another host than the playlist",
                                         "%d sign-in headers dropped: their channels are on other hosts than the playlist"))
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

    Mirrors Model.nameIdKey, except where the two runtimes' lower-casing
    tables differ (D-SRC-12; the whitespace is one enumerated list in both
    since D-ID-5). The
    name is normalized through the id fold, normalize_id_text, so re-casing a
    title (outside the hundred or so codepoints whose upper or title case
    does not lower back to them, such as the fi ligature, the long s, the
    micro sign, final sigma and the Greek letters with a subscript iota),
    folding its Latin accents, or swapping one run
    of ASCII punctuation and whitespace between words for another, neither
    holding `+` or `*`, does not move the id. Not the search fold, normalize_text: it folds `+`
    and `*` to a space, so `USA: AMC+` and `USA AMC` would share a name key,
    and a playlist holding both would give neither an `n:` id.
    A name that normalizes to nothing cannot key anything, and neither can
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
    the URL hash uses its name_id_key, `n:<fnv1a32(normalize_id_text(name))>`,
    instead, only when the name keys one (it does not fold to nothing, and
    does not fold to `channel <digits>`, the shape make_channel generates,
    which a provider's own `Channel 4` also has) and that key is unique
    across the whole playlist. Every other row keeps the exact id it already
    had.

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
    and the helper's budget is 10,000 channels parsed in under a second.

    Only a `u:` row is ever substituted, so a list with none comes back as
    it went in, and its names are neither folded nor hashed (D-PERF-13):
    the count below decides nothing without one. Measured on PerformanceTest's
    10,000 rows, each with a tvg-id of its own: 77 ms, then under 1."""
    if not any(base.startswith("u:") for base in legacy):
        return list(legacy)
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


