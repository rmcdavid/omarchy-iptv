# A part of bin/omarchy-iptv (D-REL-7), not a module: the helper compiles
# this file into its own namespace in the order its HELPER_PARTS lists, so
# a part sees every name the parts before it define. Run the helper.
from __future__ import annotations
# --------------------------------------------------------------- relay
#
# D-SINK-102 (the marketplace maintainer on omacom/omarchy-plugin-marketplace
# #14290, against 0.19.1 at 9e006be). Every destination rule here judged the
# address the HELPER saw -- a channel's URL as written, and since D-SINK-101
# the answers of its own play-time lookup -- and the player then made its own
# connections. An HTTP redirect the stream server sent, an HLS or DASH
# playlist, segment or key on another host, and a name that answered the
# player differently a moment later (DNS rebinding) all reached addresses
# nobody here had judged.
#
# The relay is the fix for everything the player fetches over http and
# https. The player is pinned to it as its HTTP proxy (spawn_player's launch
# argv, and a per-file value on every load apply_channel makes), and FFmpeg then never resolves a proxied target:
# it connects to this relay's 127.0.0.1 port and hands it the NAME, in an
# absolute-form request line for plain http and in a CONNECT for https
# (READ in FFmpeg n9.0.2's http.c and tls.c; MEASURED by the design's rigs
# with literal targets). Each redirect hop and each nested HLS or DASH open
# is a request of its own. The relay looks every target up itself (relay_lookup, through the
# play-time lookup stream_resolve), judges EVERY answer -- a playlist's load
# by the rule a channel's literal meets (stream_answer_refusal), a typed
# --url's by DestinationPolicy across all of its connections (StreamPolicy,
# RelayTypedPolicy) -- and connects only to an address it judged, through
# bounded_create_connection, the one connector the helper's own fetches
# use. Check and use are one act, so a name cannot answer the check one way
# and the use another.
#
# What it serves, and to whom:
#   * fd 3, a TCP listener on 127.0.0.1 the helper bound (the proxy), and
#     fd 4, a Unix listener in the 0700 runtime directory (the control
#     socket); it refuses to run as anything else (relay_inherited).
#   * A proxy connection is served only to a peer of this uid, read from
#     /proc/net/tcp before a byte is read (relay_peer_uid), and every request
#     must carry, as Basic proxy authentication, a token the helper
#     registered for one load (RelayState.register). The pin on the player's
#     argv carries no token, so a load nobody here registered gets a 407 and
#     reaches no origin.
#   * Each token carries its own load's rule, never the next channel's, so a
#     request the replaced stream makes while the player tears it down is
#     judged by that stream's own rule. The newest RELAY_TOKENS_MAX are kept.
#   * The control socket speaks one JSON line each way: `load` registers a
#     policy and answers a token and the port, `status` answers counts and
#     this relay's port and build, `count` one token's counts. Nothing it
#     answers names a host, a path or a userinfo.
#
# It holds request lines and headers, credentials included, in memory for
# the life of a request and writes them nowhere: it logs nothing, no reply
# carries one, and it runs non-dumpable (the stub's shield) with RLIMIT_CORE
# (0, 0). It reaps its children, the player first among them, and exits when
# none is left, so every way the player ends ends the relay too. Asked to
# stop (SIGTERM), it kills a child still alive in its process group once
# RELAY_TERM_GRACE_S has passed; only a process that left the group (a
# wrapper that calls setsid) can outlive it.
#
# What stays outside it, stated in the design: the protocols that never ask
# an HTTP proxy (the design pins rtmp, rtsp and srt to the judged literal
# and refuses mms and mmsh from a playlist that is not local; rtmps reaches
# the relay as a CONNECT, and rtsps, which never asks it, is in no
# playlist's scheme list -- both measured headless), the user's own
# --ytdl, and, through the user's own proxy, a name that proxy resolves
# differently from this machine (check_proxied's residual, ARCHITECTURE.md
# section 6).


class RelayLookupFailed(OSError):
    """The relay's lookup of a target answered nothing it could use: the
    resolver failed, took longer than its bound, or answered an empty list.
    An OSError, so DestinationPolicy.check_proxied reads it as a target that
    cannot be resolved, and bounded_create_connection lets it through
    unchanged (it catches only the connect's errors); the relay answers it
    502 RELAY_LOOKUP_FAILED."""


class RelayReply(Exception):
    """A request the relay answers itself and then closes: `status` an HTTP
    status code and `reason` one of the fixed reasons (RELAY_REASONS, or
    RELAY_LOOKUP_FAILED for a 502 whose lookup failed), never text from the
    request."""

    def __init__(self, status: int, reason: str = "") -> None:
        super().__init__(status)
        self.status = status
        self.reason = reason


RELAY_REASONS = {
    200: "Connection established",
    400: "Bad Request",
    403: RELAY_REFUSED,
    405: "Method Not Allowed",
    407: "Proxy Authentication Required",
    408: "Request Timeout",
    431: "Request Header Fields Too Large",
    502: RELAY_CONNECT_FAILED,
    503: "Service Unavailable",
}
# A token is what secrets.token_hex(16) writes: 32 lowercase hex digits.
_RELAY_TOKEN_DIGITS = frozenset("0123456789abcdef")
# RFC 9110's tchar, which a method and a header name are made of.
_RELAY_TCHARS = frozenset(b"!#$%&'*+-.^_`|~0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
_RELAY_POLICY_KEYS = frozenset(("origin", "host", "port", "loopback", "local", "class"))
_RELAY_USER_KEYS = frozenset(("origin", "host", "port"))


def relay_response(status: int, reason: str = "") -> bytes:
    """The whole reply the relay sends for `status`, then closes: no body,
    `Connection: close`, and on a 407 the challenge FFmpeg answers with the
    token from the per-file proxy URL (MEASURED by the design's rigs: one
    407 per new proxy connection, none on a reused one)."""
    line = "HTTP/1.1 %d %s\r\n" % (status, reason or RELAY_REASONS[status])
    if status == 200:
        return (line + "\r\n").encode("ascii")
    extra = 'Proxy-Authenticate: Basic realm="%s"\r\n' % RELAY_REALM if status == 407 else ""
    return (line + extra + "Content-Length: 0\r\nConnection: close\r\n\r\n").encode("ascii")


def relay_lookup(host: str, port: int, bound: Any = None) -> list[Any]:
    """The relay's lookup of a target: the play-time lookup's own
    (stream_resolve, so its bound is STREAM_LOOKUP_TIMEOUT_S and the suite's
    stand-in answers it; `bound` is the connector's and is not used), with
    the name asked as the player would have asked it, D-SINK-101's reading:
    an ASCII name as its text, one that is not as its UTF-8 bytes, which
    resolve_within hands to the resolver with no idna codec. Raises
    RelayLookupFailed for every way it can come back empty-handed, and
    RelayReply 502 (RELAY_LOOKUP_FAILED) at once while RELAY_LOOKUPS_MAX
    lookups are still running (stream_resolve's ResolveBusy): a RelayReply,
    not an OSError, so no caller reads it as a name that cannot be resolved
    (check_proxied lets such a name pass on a typed URL's first hop)."""
    name: str | bytes = host if host.isascii() else host.encode("utf-8")
    try:
        found = stream_resolve(name, port)
    except ResolveBusy:
        raise RelayReply(502, RELAY_LOOKUP_FAILED) from None
    except (OSError, ValueError, UnicodeError, HelperError):
        raise RelayLookupFailed(errno.EADDRNOTAVAIL, RELAY_LOOKUP_FAILED) from None
    if not found:
        raise RelayLookupFailed(errno.EADDRNOTAVAIL, RELAY_LOOKUP_FAILED)
    return list(found)


def relay_proxy_lookup(host: Any, port: int, bound: Any) -> list[Any]:
    """The lookup of the user's own proxy's name (relay_upstream_connect),
    resolve_within under the connector's bound and RELAY_LOOKUPS_MAX, as
    every lookup the relay makes is; RelayReply 502 past the cap, as
    relay_lookup answers it."""
    try:
        return resolve_within(host, port, bound, limit=RELAY_LOOKUPS_MAX)
    except ResolveBusy:
        raise RelayReply(502, RELAY_LOOKUP_FAILED) from None


def relay_start(thread: Any) -> None:
    """Start one of the relay's own threads under RESOLVE_LOCK, so none
    starts while a lookup's start has the process-wide stack size at
    RESOLVE_STACK_BYTES (resolve_within): every one takes
    RELAY_THREAD_STACK_BYTES."""
    with RESOLVE_LOCK:
        thread.start()


class RelayTypedPolicy(DestinationPolicy):
    """A typed --url's rule (origin `user`), DestinationPolicy's own, held
    across ALL of the token's upstream connections (RelayToken), with one
    thing more: the FIRST connection gets the first hop's freedom -- any
    address -- only when it is to the URL's own host, `record`'s host_key,
    and, where it connects to this machine (loopback), its own port
    (own_host_match, D-SINK-57's reading of "the same host"). A first
    connection to anything else is judged as a later hop, and the token's
    first hop is spent on it. Nothing under the token is known to open
    before the typed URL itself; this is so that nothing that does -- a URL
    a user's --ytdl hook substitutes, say -- inherits the URL's freedom
    (the lead's call under the owner's standing authority of 2026-11-09,
    made on 2026-11-16)."""

    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__("stream", ORIGIN_USER)
        self.typed = {"host": record.get("host") or "", "port": record.get("port")}

    def typed_first(self, host: str, kind: str, first: bool, port: int | None) -> bool:
        return first and own_host_match(host, port, dict(self.typed, loopback=kind == "loopback"))

    def permits(self, host: str, kind: str, first: bool, port: int | None = None) -> bool:
        return super().permits(host, kind, self.typed_first(host, kind, first, port), port)

    def connected(self, host: str, kind: str, first: bool, port: int | None = None) -> None:
        super().connected(host, kind, self.typed_first(host, kind, first, port), port)

    def check_proxied(self, host: str, port: int, timeout: float, first: bool, resolve: Any = None) -> None:
        # Through the user's proxy a target that cannot be resolved passes
        # on the first hop (`unresolved`); only the URL's own host may.
        super().check_proxied(host, port, timeout, self.typed_first(host, "unresolved", first, port), resolve)


class RelayToken:
    """One load the helper registered: its token, its playlist's rule (a
    record relay_policy_record accepted), and what the relay counted for it.

    A typed --url (origin `user`) keeps its first-hop rule across ALL of the
    token's upstream connections, as DestinationPolicy keeps it across one
    fetch's hops (the lead's call under the owner's standing authority of
    2026-11-09, made on 2026-11-14): its first upstream
    connect may reach any address when it is to the URL's own host
    (RelayTypedPolicy), and later ones only a global address or
    that first connection's own host in the class it connected to. Which
    connection is the first is decided under the token's lock -- the first
    to reach the connect wins and holds `settle` until it has connected or
    failed, so a later one is judged against what the first recorded, never
    beside it."""

    def __init__(self, token: str, record: dict[str, Any]) -> None:
        import threading
        self.token = token
        self.record = record
        self.user = record.get("origin") == ORIGIN_USER
        self.destination = RelayTypedPolicy(record) if self.user else None
        self.lock = threading.Lock()
        self.settle = threading.Lock()
        self.claimed = False
        self.upstream = 0
        self.refused = 0

    def claim(self) -> bool:
        """-> whether this connection is the token's FIRST upstream connect
        (only a typed URL has one); a later one waits for the first to
        settle, at most as long as the first can take, and is then judged
        as a later hop whatever the first came to."""
        if not self.user:
            return False
        with self.lock:
            first = not self.claimed
            if first:
                self.claimed = True
                self.settle.acquire()
        if not first and self.settle.acquire(timeout=STREAM_LOOKUP_TIMEOUT_S + RELAY_CONNECT_S):
            self.settle.release()
        return first

    def settled(self) -> None:
        """The first connect is over: release the connections waiting on it."""
        self.settle.release()


class StreamPolicy:
    """bounded_create_connection's policy (DestinationPolicy's shape) for one
    upstream connection made for `entry`'s load, of `scheme` (`http` for an
    absolute-form request, `https` for a CONNECT; the scheme matters only to
    the multicast rule, which no proxied scheme meets).

    A playlist's token is judged by the channel rule: every answer by
    stream_answer_refusal, the function the play-time lookup asks (rule 12),
    and a host of one label that is not the playlist's own refused before
    any lookup (stream_label_refused, D-SINK-89), never for a local
    playlist. A typed URL's token is judged by DestinationPolicy itself, the
    rule a typed fetch meets, kept across the token's connections (RelayToken).
    Every refusal is `local_address` with RELAY_REFUSED, which names no host."""

    def __init__(self, entry: RelayToken, scheme: str) -> None:
        self.entry = entry
        self.scheme = scheme
        self.source = entry.record

    def refuses_name(self, host: str) -> bool:
        if self.entry.user:
            return False
        return stream_label_refused("", host, self.scheme, self.source)

    def name_refusal(self, first: bool) -> HelperError:
        return HelperError("local_address", RELAY_REFUSED)

    def permits(self, host: str, kind: str, first: bool, port: int | None = None) -> bool:
        if self.entry.destination is not None:
            return self.entry.destination.permits(host, kind, first, port)
        return stream_answer_refusal(kind, host, port, self.scheme, self.source) == ""

    def connected(self, host: str, kind: str, first: bool, port: int | None = None) -> None:
        if self.entry.destination is not None:
            self.entry.destination.connected(host, kind, first, port)

    def refusal(self, host: str, first: bool) -> HelperError:
        return HelperError("local_address", RELAY_REFUSED)

    def check_proxied(self, host: str, port: int, first: bool) -> None:
        """A target the relay hands to the USER's proxy (relay_upstream),
        judged by name with check_proxied's semantics, because that proxy
        may connect to any address the name answers: every answer this
        machine's resolver gives must be permitted, and a name it cannot
        resolve is refused (RelayLookupFailed) except where a fetch would
        let it pass -- a typed URL's first hop, or a later hop to that host
        when the first was unresolved too (DestinationPolicy.check_proxied
        itself), and a playlist's own host when its fetch went through a
        proxy too (`class` unresolved, D-SINK-101's pass)."""
        if self.entry.destination is not None:
            try:
                self.entry.destination.check_proxied(host, port, RELAY_CONNECT_S, first, resolve=relay_lookup)
            except HelperError as error:
                if error.code == "network":
                    raise RelayLookupFailed(errno.EADDRNOTAVAIL, RELAY_LOOKUP_FAILED) from None
                raise HelperError("local_address", RELAY_REFUSED) from None
            return
        refuse_host_name(host)
        if self.refuses_name(host):
            raise self.name_refusal(first)
        try:
            answers = relay_lookup(host, port)
        except RelayLookupFailed:
            source = self.source
            if (not source.get("local") and source.get("class") == "unresolved"
                    and own_host_match(host, port, source)):
                return
            raise
        for answer in answers:
            if not self.permits(host, address_class(answer[4][0]), first, port):
                raise self.refusal(host, first)


def relay_policy_record(raw: Any) -> dict[str, Any] | None:
    """A `load` request's policy, as the helper builds it (apply_channel,
    through relay_register), or None when it is not one:
      * a playlist's: cached_source's record -- `host` (its host_key, "" for
        a local file), `port` (an int or null), `loopback` and `local`
        (booleans), and `class` (one of ADDRESS_CLASSES, `unresolved`, or
        "" for a cache that records none) -- with `origin` "playlist" or
        absent;
      * a typed --url's: {"origin": "user", "host": ..., "port": ...}: the
        URL's host and port (its scheme's default when it names none), which
        the token's first upstream connection must be to for the first
        hop's freedom (RelayTypedPolicy).
    Nothing else is accepted, so a record the relay cannot read the rule of
    is no rule at all."""
    if not isinstance(raw, dict):
        return None
    origin = raw.get("origin", ORIGIN_PLAYLIST)
    keys = _RELAY_USER_KEYS if origin == ORIGIN_USER else _RELAY_POLICY_KEYS
    if origin not in (ORIGIN_USER, ORIGIN_PLAYLIST) or not set(raw) <= keys:
        return None
    host = raw.get("host", "")
    port = raw.get("port")
    if not isinstance(host, str) or len(host) > MAX_SOURCE_URL:
        return None
    if port is not None and (not isinstance(port, int) or isinstance(port, bool) or not 0 < port < 65536):
        return None
    if origin == ORIGIN_USER:
        return {"origin": ORIGIN_USER, "host": host_key(host) if host else "", "port": port}
    flags = [raw.get("loopback", False), raw.get("local", False)]
    klass = raw.get("class", "")
    if not all(isinstance(flag, bool) for flag in flags):
        return None
    if klass not in ADDRESS_CLASSES and klass not in ("unresolved", ""):
        return None
    return {"origin": ORIGIN_PLAYLIST, "host": host_key(host) if host else "", "port": port,
            "loopback": flags[0], "local": flags[1], "class": klass}


class RelayState:
    """What the relay keeps: the tokens, the counts, and its own identity
    (the port it serves, the build that loaded it, its first child)."""

    def __init__(self, port: int, build: str, child: int = 0, address: str = "127.0.0.1") -> None:
        import threading
        self.port = port
        self.address = address
        self.build = build
        self.child = child
        self.lock = threading.Lock()
        self.tokens: list[RelayToken] = []
        self.active = 0
        self.controls = 0
        self.upstream = 0
        self.refused = 0

    def register(self, record: dict[str, Any]) -> str:
        """A new token for one load; the oldest is dropped past
        RELAY_TOKENS_MAX. A token is never revoked early otherwise: each
        carries its own load's rule."""
        import secrets
        token = secrets.token_hex(16)
        with self.lock:
            self.tokens.append(RelayToken(token, record))
            del self.tokens[:-RELAY_TOKENS_MAX]
        return token

    def find(self, token: Any) -> RelayToken | None:
        """The live entry whose token is `token`, compared in constant time
        against every entry (hmac.compare_digest), or None."""
        import hmac
        if not isinstance(token, str) or len(token) != 32 or not set(token) <= _RELAY_TOKEN_DIGITS:
            return None
        wanted = token.encode("ascii")
        with self.lock:
            entries = list(self.tokens)
        found = None
        for entry in entries:
            if hmac.compare_digest(entry.token.encode("ascii"), wanted):
                found = entry
        return found

    def live(self, entry: RelayToken) -> bool:
        with self.lock:
            return any(held is entry for held in self.tokens)

    def count_refusal(self, entry: RelayToken) -> None:
        with self.lock:
            entry.refused += 1
            self.refused += 1

    def count_upstream(self, entry: RelayToken) -> None:
        with self.lock:
            entry.upstream += 1
            self.upstream += 1

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {"ok": True, "port": self.port, "build": self.build, "child": self.child,
                    "tokens": len(self.tokens), "connections": self.active, "upstream": self.upstream,
                    "refused": self.refused}


# ------------------------------------------------------- reading a request

def relay_authority(text: str, need_port: bool, default: int = 80) -> tuple[str, int] | None:
    """(host, port) of a request's authority, read by the SR15 reader the
    play-time gate uses (_stream_authority_refused, through
    stream_host_name_refused's readings): host[:port], a bracket only as a
    leading IPv6 literal's pair, a port of 1-65535 in at most five ASCII
    digits, and a host host_name_refused accepts; an IPv6 zone that is not a
    number is refused as the gate refuses it (stream_zone_refused). Never
    urlsplit. `need_port` for CONNECT's authority form; otherwise a missing
    port is `default`. None when it is not one.

    The escaped reading mpv takes of an http URL (reading 2) is not asked:
    the relay looks the name up as it receives it, after any escaping."""
    if text == "" or "@" in text:
        return None
    if _stream_authority_refused(text, "") or stream_zone_refused(text):
        return None
    if text.startswith("["):
        close = text.find("]")
        host, rest = text[1:close], text[close + 1:]
        has_port, port_text = rest.startswith(":"), rest[1:]
    else:
        host, colon, port_text = text.partition(":")
        has_port = colon == ":"
    if host == "":
        return None
    if not has_port:
        return None if need_port else (host, default)
    if not (port_text.isascii() and port_text.isdigit()) or len(port_text) > 5:
        return None
    port = int(port_text)
    return (host, port) if 0 < port < 65536 else None


def relay_parse_head(head: bytes, state: RelayState) -> dict[str, Any]:
    """One request head (its lines, without the empty line that ends it) ->
    the request the relay may act on, or RelayReply:
      400  not HTTP/1.0 or 1.1 with CRLF lines; a folded or nameless header;
           a body (Content-Length other than 0, any Transfer-Encoding); two
           Proxy-Authorization headers; a target that is not CONNECT's
           authority form or GET's and HEAD's `http://` absolute form; an
           `https://` absolute form; userinfo in the authority; an
           authority relay_authority refuses;
      407  no Proxy-Authorization, or not Basic `iptv:<a live token>`;
      405  any method but CONNECT, GET and HEAD.
    Asked in that order, so a peer without a token learns nothing but 407
    about a well-formed request. The reply carries no part of the head."""
    import base64
    lines = head.split(b"\r\n")
    if any(b"\r" in line or b"\n" in line for line in lines):
        raise RelayReply(400)
    parts = lines[0].split(b" ")
    if len(parts) != 3 or parts[2] not in (b"HTTP/1.1", b"HTTP/1.0"):
        raise RelayReply(400)
    method, target, version = parts
    if not _relay_token(method) or not target or any(byte < 0x21 or byte == 0x7F for byte in target):
        raise RelayReply(400)
    kept: list[bytes] = []
    auth: list[bytes] = []
    for line in lines[1:]:
        name, colon, value = line.partition(b":")
        if not colon or not _relay_token(name):
            raise RelayReply(400)
        lowered = name.lower()
        if lowered == b"proxy-authorization":
            auth.append(value)
        elif lowered == b"proxy-connection":
            continue
        elif lowered == b"transfer-encoding" or (lowered == b"content-length" and value.strip() != b"0"):
            raise RelayReply(400)
        else:
            kept.append(line)
    if len(auth) > 1:
        raise RelayReply(400)
    entry = None
    if auth:
        scheme, _, credential = auth[0].strip().partition(b" ")
        if scheme.lower() == b"basic":
            try:
                user, colon, token = base64.b64decode(credential.strip(), validate=True).partition(b":")
            except ValueError:
                user, colon, token = b"", b"", b""
            if colon and user == RELAY_USER.encode("ascii"):
                entry = state.find(token.decode("ascii", "replace"))
    if entry is None:
        raise RelayReply(407)
    if method == b"CONNECT":
        if target[:1] == b"/" or b"://" in target:
            raise RelayReply(400)
        host_port = _relay_authority_bytes(target, True, 443)
        return {"connect": True, "method": method, "host": host_port[0], "port": host_port[1], "entry": entry,
                "version": version, "headers": kept, "target": target, "origin": b""}
    if method not in (b"GET", b"HEAD"):
        raise RelayReply(405)
    if target[:7].lower() != b"http://":
        raise RelayReply(400)
    rest = target[7:]
    cut = min([index for index in (rest.find(b"/"), rest.find(b"?"), rest.find(b"#")) if index >= 0] or [len(rest)])
    authority, path = rest[:cut], rest[cut:]
    host_port = _relay_authority_bytes(authority, False, 80)
    path = path.partition(b"#")[0]
    origin = path if path.startswith(b"/") else b"/" + path
    return {"connect": False, "method": method, "host": host_port[0], "port": host_port[1], "entry": entry,
            "version": version, "headers": kept, "target": b"http://" + authority + path, "origin": origin}


def _relay_token(text: bytes) -> bool:
    """Is `text` an RFC 9110 token (one or more tchar)?"""
    return bool(text) and set(text) <= _RELAY_TCHARS


def _relay_authority_bytes(raw: bytes, need_port: bool, default: int) -> tuple[str, int]:
    """relay_authority over the authority's bytes, which must be UTF-8;
    RelayReply(400) when it is not one (userinfo included)."""
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        raise RelayReply(400) from None
    found = relay_authority(text, need_port, default)
    if found is None:
        raise RelayReply(400)
    return found


def relay_read_head(sock: Any, buffer: bytearray, deadline: float | None) -> bytes | None:
    """The next request head from `sock`, without its terminating empty line
    (what is read past it stays in `buffer`), or None when the peer closed
    first. At most RELAY_HEAD_BYTES (else RelayReply 431), by `deadline`
    (else RelayReply 408); a deadline of None waits for the head's FIRST
    byte as long as the peer keeps the connection (no idle timeout on an
    established connection) and then gives the rest
    RELAY_HEAD_S.

    The wait is a poll on the descriptor, never a socket timeout: the
    client socket is written by the pump thread while this reads it, and a
    Python socket's timeout is one setting for both directions."""
    import select
    while True:
        end = buffer.find(b"\r\n\r\n")
        if end >= 0:
            if end + 4 > RELAY_HEAD_BYTES:
                raise RelayReply(431)
            head = bytes(buffer[:end])
            del buffer[:end + 4]
            return head
        if len(buffer) >= RELAY_HEAD_BYTES:
            raise RelayReply(431)
        if deadline is None and buffer:
            deadline = time.monotonic() + RELAY_HEAD_S
        if deadline is not None:
            left = deadline - time.monotonic()
            if left <= 0:
                raise RelayReply(408)
            poller = select.poll()
            poller.register(sock.fileno(), select.POLLIN)
            if not poller.poll(int(left * 1000) + 1):
                continue
        chunk = sock.recv(min(65536, RELAY_HEAD_BYTES + 4 - len(buffer)))
        if not chunk:
            return None
        buffer += chunk


# ------------------------------------------------------- the user's proxy

def relay_no_proxy_match(no_proxy: Any, host: str) -> bool:
    """FFmpeg's ff_http_match_no_proxy (libavformat/network.c, n9.0.2, READ
    2026-11-14), which decides for every hop whether FFmpeg would have used
    the proxy, transcribed: the list splits at runs of spaces and commas;
    `*` matches every host; otherwise one leading `*` and then one leading
    `.` are dropped and the rest must be the whole host, or a suffix of it
    that a `.` precedes. Byte-for-byte and case-sensitive (strcmp), as
    FFmpeg compares; an empty entry left by a trailing separator matches
    only a host that ends in a dot, as it does there."""
    if not isinstance(no_proxy, str) or not isinstance(host, str):
        return False
    rest = no_proxy
    while True:
        rest = rest.lstrip(" ,")
        cut = min([index for index in (rest.find(" "), rest.find(",")) if index >= 0] or [-1])
        pattern, rest = (rest, None) if cut < 0 else (rest[:cut], rest[cut + 1:])
        if _relay_host_pattern(pattern, host):
            return True
        if rest is None:
            return False


def _relay_host_pattern(pattern: str, host: str) -> bool:
    """network.c's match_host_pattern."""
    if pattern == "*":
        return True
    if pattern.startswith("*"):
        pattern = pattern[1:]
    if pattern.startswith("."):
        pattern = pattern[1:]
    if len(pattern) > len(host) or not host.endswith(pattern):
        return False
    return len(host) == len(pattern) or host[len(host) - len(pattern) - 1] == "."


def relay_upstream(environ: Any) -> dict[str, Any] | None:
    """The user's own proxy, from the relay's environment by FFmpeg's rules
    (http.c and tls.c, n9.0.2): `http_proxy`, lowercase only, and used only
    when it starts with `http://`; its host, port and userinfo read as
    av_url_split reads them (the authority ends at the first `/`, `?` or
    `#`; the userinfo at its last `@`; a bracketed IPv6 host; the port as
    atoi reads the text after the colon, 0 when there is none -- and FFmpeg
    then fails the open, as the relay's connect to it does). None when no
    proxy would have been used. The value and its userinfo are the user's,
    never logged."""
    value = environ.get("http_proxy") if environ is not None else None
    if not isinstance(value, str) or not value.startswith("http://"):
        return None
    rest = value[len("http://"):]
    cut = min([index for index in (rest.find("/"), rest.find("?"), rest.find("#")) if index >= 0] or [len(rest)])
    authority = rest[:cut]
    auth, at, hostport = authority.rpartition("@")
    if not at:
        auth = ""
    if hostport.startswith("[") and "]" in hostport:
        close = hostport.index("]")
        host, tail = hostport[1:close], hostport[close + 1:]
        port_text = tail[1:] if tail.startswith(":") else None
    else:
        host, colon, port_text = hostport.partition(":")
        port_text = port_text if colon else None
    return {"host": host, "port": _relay_atoi(port_text) if port_text is not None else 0, "auth": auth}


def _relay_atoi(text: str) -> int:
    """C's atoi, as av_url_split reads a port: leading white space, a sign,
    then the digits up to the first that is not one; 0 for none."""
    rest = text.lstrip(" \t\n\v\f\r")
    sign = -1 if rest[:1] == "-" else 1
    if rest[:1] in "+-" and rest:
        rest = rest[1:]
    digits = ""
    for char in rest:
        if not ("0" <= char <= "9"):
            break
        digits += char
    return sign * int(digits) if digits and len(digits) <= 10 else 0


def relay_upstream_authorization(upstream: dict[str, Any]) -> bytes:
    """The Proxy-Authorization line for the user's proxy, from its userinfo
    as FFmpeg sends it after a 407 (httpauth.c: the userinfo percent-decoded,
    then Basic), sent at once rather than after a challenge; b"" when it has
    none."""
    import base64
    auth = upstream.get("auth") or ""
    if not auth:
        return b""
    credential = urllib.parse.unquote_to_bytes(auth)
    return b"Proxy-Authorization: Basic " + base64.b64encode(credential) + b"\r\n"


def relay_upstream_connect(upstream: dict[str, Any]) -> Any:
    """A connection to the user's proxy, which is the user's choice and so
    not judged (bounded_create_connection with no policy: the proxy's own
    name is looked up as the helper's fetches look a proxy up). A port that
    is not 1-65535 fails, as FFmpeg's open fails."""
    port = upstream.get("port")
    if not isinstance(port, int) or not 0 < port < 65536 or not upstream.get("host"):
        raise OSError(errno.EINVAL, RELAY_CONNECT_FAILED)
    return bounded_create_connection((upstream["host"], port), RELAY_CONNECT_S, resolve=relay_proxy_lookup,
                                     stagger=RELAY_ATTEMPT_STAGGER_S, in_flight=RELAY_ATTEMPTS_IN_FLIGHT)


def _relay_hostport(host: str, port: int) -> bytes:
    text = "[%s]:%d" % (host, port) if ":" in host else "%s:%d" % (host, port)
    return text.encode("utf-8")


def relay_tunnel_upstream(sock: Any, host: str, port: int, upstream: dict[str, Any]) -> bytes:
    """Ask the user's proxy for a CONNECT tunnel to host:port; -> any bytes
    it sent past its reply head. Its reply is read like a request head
    (RELAY_HEAD_BYTES, by RELAY_CONNECT_S); anything but a 2xx is a failed
    connect (OSError), never relayed."""
    target = _relay_hostport(host, port)
    sock.sendall(b"CONNECT " + target + b" HTTP/1.1\r\nHost: " + target + b"\r\n"
                 + relay_upstream_authorization(upstream) + b"\r\n")
    buffer = bytearray()
    try:
        head = relay_read_head(sock, buffer, time.monotonic() + RELAY_CONNECT_S)
    except RelayReply:
        head = None
    status = head.split(b"\r\n", 1)[0].split(b" ") if head else []
    if len(status) < 2 or not status[0].startswith(b"HTTP/1.") or not (status[1].isdigit() and status[1][:1] == b"2"):
        raise OSError(errno.ECONNREFUSED, RELAY_CONNECT_FAILED)
    return bytes(buffer)


# ---------------------------------------------------------- serving it

def relay_peer_uid(address: str, port: int, relay_address: str, relay_port: int, lines: Any = None) -> int | None:
    """The uid that owns the CLIENT end of a connection to the relay, from
    /proc/net/tcp (or `lines`, the same text): the line whose local address
    is the peer's (`address`:`port`) and whose remote address is the
    relay's own. Addresses there are the kernel's `%08X:%04X`, the IPv4
    address as the 32-bit value read in this machine's byte order. None when
    no line matches or it cannot be read. IPv4 only: the relay listens on
    127.0.0.1, and a peer it cannot find is refused."""
    import socket
    import struct
    try:
        local = "%08X:%04X" % (struct.unpack("=I", socket.inet_aton(address))[0], port)
        remote = "%08X:%04X" % (struct.unpack("=I", socket.inet_aton(relay_address))[0], relay_port)
    except (OSError, struct.error, OverflowError, TypeError, ValueError):
        return None
    handle = None
    if lines is None:
        try:
            handle = open("/proc/net/tcp", encoding="ascii", errors="replace")
        except OSError:
            return None
        lines = handle
    try:
        for line in lines:
            fields = line.split()
            if len(fields) < 8 or fields[1].upper() != local or fields[2].upper() != remote:
                continue
            uid = fields[7]
            return int(uid) if uid.isascii() and uid.isdigit() and len(uid) <= 10 else None
        return None
    except OSError:
        return None
    finally:
        if handle is not None:
            handle.close()


def _relay_close(*socks: Any) -> None:
    import socket
    for sock in socks:
        if sock is None:
            continue
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def _relay_pump(source: Any, sink: Any) -> None:
    """Copy bytes from `source` to `sink`, blind, until either side ends;
    then end both, so the other direction ends too."""
    try:
        while True:
            chunk = source.recv(65536)
            if not chunk:
                break
            sink.sendall(chunk)
    except OSError:
        pass
    finally:
        _relay_close(source, sink)


def _relay_answer(conn: Any, reply: RelayReply) -> None:
    """Send `reply`, then end the connection gracefully: the write side
    shut, and at most RELAY_HEAD_BYTES of what the client still sends read
    and dropped for at most RELAY_DRAIN_S, so a client that wrote past the
    head the relay refused reads the reply rather than a reset."""
    import select
    import socket
    try:
        conn.sendall(relay_response(reply.status, reply.reason))
        conn.shutdown(socket.SHUT_WR)
        poller = select.poll()
        poller.register(conn.fileno(), select.POLLIN)
        until = time.monotonic() + RELAY_DRAIN_S
        dropped = 0
        while dropped < RELAY_HEAD_BYTES:
            left = until - time.monotonic()
            if left <= 0 or not poller.poll(int(left * 1000) + 1):
                break
            chunk = conn.recv(65536)
            if not chunk:
                break
            dropped += len(chunk)
    except OSError:
        pass


def _relay_forward(request: dict[str, Any], upstream: dict[str, Any] | None) -> bytes:
    """The head the origin (or the user's proxy) is sent for a plain http
    request: origin form to an origin, the absolute form to a proxy with its
    own Proxy-Authorization; Proxy-Authorization and Proxy-Connection gone;
    every other header as FFmpeg wrote it, a provider's Host included."""
    if upstream is None:
        line = request["method"] + b" " + request["origin"] + b" " + request["version"]
        extra = b""
    else:
        line = request["method"] + b" " + request["target"] + b" " + request["version"]
        extra = relay_upstream_authorization(upstream)
    return line + b"\r\n" + b"".join(header + b"\r\n" for header in request["headers"]) + extra + b"\r\n"


class RelayServer:
    """The relay's two listeners and its connections. `proxy` and `control`
    are listening sockets; serve() runs until stop(). The verb (player_relay)
    adds the checks, the signals and the reaping; the suite runs this alone,
    in process, on scratch sockets."""

    def __init__(self, proxy: Any, control: Any, state: RelayState, environ: Any = None) -> None:
        self.proxy = proxy
        self.control = control
        self.state = state
        self.environ = os.environ if environ is None else environ
        self.wake_read, self.wake_write = os.pipe()
        self.stopping = False

    def stop(self) -> None:
        self.stopping = True
        try:
            os.write(self.wake_write, b"x")
        except OSError:
            pass

    def serve(self) -> None:
        import select
        import threading
        poller = select.poll()
        for sock in (self.proxy, self.control):
            sock.setblocking(False)
            poller.register(sock.fileno(), select.POLLIN)
        poller.register(self.wake_read, select.POLLIN)
        while not self.stopping:
            for fd, _ in poller.poll():
                if self.stopping or fd == self.wake_read:
                    continue
                listener = self.proxy if fd == self.proxy.fileno() else self.control
                try:
                    conn, peer = listener.accept()
                except OSError:
                    continue
                conn.setblocking(True)
                if listener is self.proxy:
                    self.accept_proxy(conn, peer, threading)
                else:
                    self.accept_control(conn, threading)

    def close(self) -> None:
        """The wake pipe, once nothing can stop() this any more (a stop
        after it would write to a descriptor number the process may have
        reused)."""
        for fd in (self.wake_read, self.wake_write):
            try:
                os.close(fd)
            except OSError:
                pass

    def accept_proxy(self, conn: Any, peer: Any, threading: Any) -> None:
        state = self.state
        uid = relay_peer_uid(peer[0], peer[1], state.address, state.port)
        if uid != os.getuid():
            conn.close()
            return
        with state.lock:
            full = state.active >= RELAY_CONNECTIONS_MAX
            if not full:
                state.active += 1
        if full:
            try:
                conn.setblocking(False)
                conn.send(relay_response(503))
            except OSError:
                pass
            conn.close()
            return
        try:
            relay_start(threading.Thread(target=self.serve_proxy, args=(conn,), name="omarchy-iptv-relay", daemon=True))
        except RuntimeError:
            with state.lock:
                state.active -= 1
            conn.close()

    def accept_control(self, conn: Any, threading: Any) -> None:
        state = self.state
        with state.lock:
            full = state.controls >= RELAY_CONTROL_MAX
            if not full:
                state.controls += 1
        if full:
            conn.close()
            return
        try:
            relay_start(threading.Thread(target=self.serve_control, args=(conn,), name="omarchy-iptv-relay-control",
                                         daemon=True))
        except RuntimeError:
            with state.lock:
                state.controls -= 1
            conn.close()

    # -- the proxy

    def serve_proxy(self, conn: Any) -> None:
        held: dict[str, Any] = {"sock": None, "pump": None}
        try:
            self.proxy_connection(conn, held)
        except RelayReply as reply:
            _relay_answer(conn, reply)
        except Exception:
            # Nothing is logged (the relay holds credentials); a bug ends
            # the connection and only the connection.
            pass
        finally:
            _relay_close(conn, held["sock"])
            if held["pump"] is not None:
                held["pump"].join(RELAY_IPC_S)
            for sock in (conn, held["sock"]):
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
            with self.state.lock:
                self.state.active -= 1

    def proxy_connection(self, conn: Any, held: dict[str, Any]) -> None:
        """One client connection, its first request to its last. The
        upstream socket and the pump thread go into `held` as soon as they
        exist, for serve_proxy to end whatever happens."""
        import threading
        buffer = bytearray()
        head = relay_read_head(conn, buffer, time.monotonic() + RELAY_HEAD_S)
        if head is None:
            return
        request = relay_parse_head(head, self.state)
        entry = request["entry"]
        upstream = relay_upstream(self.environ)
        if upstream is not None and relay_no_proxy_match(self.environ.get("no_proxy"), request["host"]):
            upstream = None
        sock = held["sock"] = self.open_upstream(request, upstream)
        self.state.count_upstream(entry)
        # Both directions block from here on, and neither has a timeout: a
        # paused player keeps its connection, as it would without the relay.
        sock.settimeout(None)
        try:
            if request["connect"]:
                leftover = relay_tunnel_upstream(sock, request["host"], request["port"], upstream) if upstream else b""
                conn.sendall(relay_response(200) + leftover)
                if buffer:
                    sock.sendall(bytes(buffer))
            else:
                sock.sendall(_relay_forward(request, upstream))
        except OSError:
            raise RelayReply(502) from None
        pump = threading.Thread(target=_relay_pump, args=(sock, conn), daemon=True)
        relay_start(pump)
        held["pump"] = pump
        if request["connect"]:
            _relay_pump(conn, sock)
            return
        first = request
        while True:
            try:
                head = relay_read_head(conn, buffer, None)
            except (RelayReply, OSError):
                break
            if head is None:
                break
            try:
                request = relay_parse_head(head, self.state)
            except RelayReply:
                break
            # Every later request on the connection is checked as the first
            # was, and must be for the same token, still live, and the same
            # host and port: it goes over the upstream connection whose
            # address was judged for them.
            if (request["connect"] or request["entry"] is not entry or not self.state.live(entry)
                    or host_key(request["host"]) != host_key(first["host"]) or request["port"] != first["port"]):
                break
            try:
                sock.sendall(_relay_forward(request, upstream))
            except OSError:
                break

    def open_upstream(self, request: dict[str, Any], upstream: dict[str, Any] | None) -> Any:
        """Judge the request's target and connect: directly, through
        bounded_create_connection under the token's StreamPolicy (every
        answer judged before it is connected to, a no_proxy match of the
        user's own proxy included), or to the user's proxy after judging the target by
        name (StreamPolicy.check_proxied). RelayReply 403 (counted against the
        token), 502 for a lookup or a connect that failed."""
        entry = request["entry"]
        policy = StreamPolicy(entry, "https" if request["connect"] else "http")
        first = entry.claim()
        try:
            if upstream is None:
                return bounded_create_connection((request["host"], request["port"]), RELAY_CONNECT_S,
                                                 policy=policy, first=first, resolve=relay_lookup,
                                                 stagger=RELAY_ATTEMPT_STAGGER_S,
                                                 in_flight=RELAY_ATTEMPTS_IN_FLIGHT)
            policy.check_proxied(request["host"], request["port"], first)
            return relay_upstream_connect(upstream)
        except RelayLookupFailed:
            raise RelayReply(502, RELAY_LOOKUP_FAILED) from None
        except HelperError as error:
            if error.code == "local_address":
                self.state.count_refusal(entry)
                raise RelayReply(403) from None
            raise RelayReply(400) from None
        except OSError:
            raise RelayReply(502) from None
        finally:
            if first:
                entry.settled()

    # -- the control socket

    def serve_control(self, conn: Any) -> None:
        try:
            if relay_control_peer_uid(conn) == os.getuid():
                reply = self.control_reply(conn)
                conn.sendall(json.dumps(reply, separators=(",", ":")).encode("ascii") + b"\n")
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass
            with self.state.lock:
                self.state.controls -= 1

    def control_reply(self, conn: Any) -> dict[str, Any]:
        import socket
        deadline = time.monotonic() + RELAY_IPC_S
        line = bytearray()
        while b"\n" not in line:
            if len(line) > RELAY_CONTROL_BYTES:
                return relay_control_error("too_large")
            left = deadline - time.monotonic()
            if left <= 0:
                return relay_control_error("timeout")
            conn.settimeout(left)
            try:
                chunk = conn.recv(RELAY_CONTROL_BYTES + 1 - len(line) if len(line) <= RELAY_CONTROL_BYTES else 1)
            except (socket.timeout, TimeoutError):
                return relay_control_error("timeout")
            if not chunk:
                return relay_control_error("bad_request")
            line += chunk
        text = bytes(line).split(b"\n", 1)[0]
        if len(text) > RELAY_CONTROL_BYTES:
            return relay_control_error("too_large")
        return relay_control_answer(self.state, text)


def relay_control_error(code: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": RELAY_CONTROL_REFUSAL}}


def relay_control_answer(state: RelayState, text: bytes) -> dict[str, Any]:
    """The answer to one control line: `{"op":"status"}`,
    `{"op":"load","policy":{...}}` (relay_policy_record) -> a token and the
    port, `{"op":"count","token":...}` -> that token's counts. Anything else,
    an unknown key included, is refused with one fixed sentence."""
    try:
        request = json_decode(text.decode("utf-8"))
    except (UnicodeError, ValueError):
        return relay_control_error("bad_request")
    if not isinstance(request, dict):
        return relay_control_error("bad_request")
    op = request.get("op")
    if op == "status" and set(request) == {"op"}:
        return state.status()
    if op == "load" and set(request) == {"op", "policy"}:
        record = relay_policy_record(request.get("policy"))
        if record is None:
            return relay_control_error("bad_policy")
        return {"ok": True, "token": state.register(record), "port": state.port}
    if op == "count" and set(request) == {"op", "token"}:
        entry = state.find(request.get("token"))
        if entry is None:
            return relay_control_error("unknown_token")
        with state.lock:
            return {"ok": True, "refused": entry.refused, "upstream": entry.upstream}
    return relay_control_error("bad_request")


def relay_control_peer_uid(conn: Any) -> int | None:
    """The uid of the process at the other end of a control connection
    (SO_PEERCRED), or None."""
    import socket
    import struct
    try:
        raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        return struct.unpack("3i", raw)[1]
    except (OSError, struct.error):
        return None


# ------------------------------------------------------------ the verb

def relay_inherited(fd: int, family: int) -> Any:
    """The listener this relay was handed at `fd`, which must be a LISTENING
    stream socket of `family` (SO_ACCEPTCONN, SO_DOMAIN), a TCP one on
    127.0.0.1; HelperError otherwise, so the verb is never anything but the
    relay of a spawn that bound both."""
    import socket
    try:
        sock = socket.socket(fileno=fd)
    except OSError:
        raise HelperError("relay_refused", RELAY_INHERITED_REFUSAL) from None
    try:
        listening = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1
        domain = sock.getsockopt(socket.SOL_SOCKET, socket.SO_DOMAIN)
        kind = sock.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
        where = sock.getsockname()
    except OSError:
        listening, domain, kind, where = False, -1, -1, None
    ok = listening and domain == family and kind == socket.SOCK_STREAM
    if ok and family == socket.AF_INET:
        ok = isinstance(where, tuple) and where[0] == "127.0.0.1"
    if ok and family == socket.AF_UNIX:
        ok = isinstance(where, str) and where.startswith("/")
    if not ok:
        sock.detach()
        raise HelperError("relay_refused", RELAY_INHERITED_REFUSAL)
    return sock


def relay_prctl(option: int, value: int) -> bool:
    """prctl(option, value) through ctypes, as the stub's shield calls it;
    False where it cannot be called."""
    try:
        import ctypes
        return ctypes.CDLL(None, use_errno=True).prctl(option, value, 0, 0, 0) == 0
    except (ImportError, OSError, AttributeError):
        return False


PR_SET_CHILD_SUBREAPER = 36


def relay_child_pidfd(child: int) -> int:
    """A pidfd for the relay's `--child`, taken at the relay's start, before
    its reaper can reap anything, and held to be THIS process's child (a
    waitid on it with WNOWAIT, which leaves a dead child to the reaper): the
    only way the relay signals its child alone, so a pid the kernel has
    reused once the child was reaped is never reached (a reaped child's
    pidfd answers ESRCH). HelperError when it cannot be opened or is not
    this process's child: a relay with no child of its own to answer for is
    no relay a spawn started."""
    try:
        fd = os.pidfd_open(child)
    except (OSError, AttributeError):
        raise HelperError("relay_refused", RELAY_INHERITED_REFUSAL) from None
    try:
        os.waitid(os.P_PIDFD, fd, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    except (OSError, AttributeError):
        os.close(fd)
        raise HelperError("relay_refused", RELAY_INHERITED_REFUSAL) from None
    return fd


def relay_group_child_alive() -> bool:
    """Whether a child of this relay is still alive in the process group
    the relay leads (its pid is the group's id); a dead one found on the way
    is reaped. True as well when the kernel cannot say, so a doubt kills
    rather than leaves a player behind."""
    while True:
        try:
            pid, _ = os.waitpid(-os.getpid(), os.WNOHANG)
        except ChildProcessError:
            return False
        except OSError:
            return True
        if pid == 0:
            return True


def player_relay(args: argparse.Namespace) -> int:
    """`player relay --child=<pid>`: the player's relay, started by the
    player's spawn (never by hand) with the two listeners at fds 3 and 4 and
    the player as its child. Runs until it has no child left, then answers
    its control socket RELAY_LINGER_S more, closes both listeners, removes
    its control socket when that path is still the file it was given, and
    exits.

    SIGTERM sends SIGTERM to its process group (the player's spawn made it
    the group's leader; a relay started any other way signals its own child
    alone, through the pidfd relay_child_pidfd took) and then exits the same
    way once its children are gone, or RELAY_TERM_GRACE_S later, whichever
    comes first. On the second, a child still alive in the group it leads
    (relay_group_child_alive) is killed with the whole group, SIGKILL to the
    group whose id is the relay's own pid, after the socket is removed: so
    the player and a user's wrapper's real player get their SIGTERM to quit
    on, and none outlives the relay with a dead proxy unless it left the
    group (a wrapper that calls setsid, which the spawn cannot see). The
    relay dies of that SIGKILL itself. A SIGKILL of the relay leaves the
    player to its death signal (PR_SET_PDEATHSIG, set by the spawn) and a
    wrapper's real player to nothing (ARCHITECTURE-PLAYER 20.9). Writes
    nothing to stdout or stderr after its checks, ever."""
    import signal as signals
    import socket
    import threading
    child = args.child
    if not isinstance(child, int) or child <= 1:
        raise HelperError("relay_refused", RELAY_INHERITED_REFUSAL)
    proxy = relay_inherited(3, socket.AF_INET)
    control = relay_inherited(4, socket.AF_UNIX)
    child_fd = relay_child_pidfd(child)
    # The control socket's SO_PEERCRED names the process that last called
    # listen(2) on it, and the spawn that bound it has exited; listening again
    # here makes it name this relay, which is what relay_request asks of it
    # (measured: a re-listen in a child moved the answer from the binder to
    # the child). A connection already queued keeps the binder's, and is
    # refused by that check and asked again.
    control.listen(RELAY_CONTROL_MAX)
    for name in (URL_ENV, ARGS_ENV):
        os.environ.pop(name, None)
    disable_core_dumps()
    relay_prctl(PR_SET_CHILD_SUBREAPER, 1)
    path = control.getsockname()
    try:
        held = os.stat(path)
        identity = (held.st_dev, held.st_ino)
    except OSError:
        identity = None
    try:
        threading.stack_size(RELAY_THREAD_STACK_BYTES)
    except (ValueError, RuntimeError):
        pass
    state = RelayState(proxy.getsockname()[1], player_build(), child)
    server = RelayServer(proxy, control, state)
    terminated = threading.Event()

    def terminate(signum: int, frame: Any) -> None:
        signals.signal(signals.SIGTERM, signals.SIG_IGN)
        terminated.set()
        try:
            # The group only when this is its leader, as the spawn makes it,
            # and only the group whose id is this relay's own pid: a relay
            # started any other way signals its own child alone, through its
            # pidfd, so a reaped child's reused pid is never reached.
            if os.getpgrp() == os.getpid():
                os.killpg(os.getpid(), signals.SIGTERM)
            else:
                signals.pidfd_send_signal(child_fd, signals.SIGTERM)
        except OSError:
            pass
        grace = threading.Timer(RELAY_TERM_GRACE_S, server.stop)
        grace.daemon = True
        grace.start()

    def reap() -> None:
        while True:
            try:
                os.waitpid(-1, 0)
            except ChildProcessError:
                break
            except OSError:
                break
        # Still the port's holder, so nothing else can bind it, and still
        # answering a start's last count (RELAY_LINGER_S).
        time.sleep(RELAY_LINGER_S)
        server.stop()

    signals.signal(signals.SIGTERM, terminate)
    threading.Thread(target=reap, name="omarchy-iptv-relay-reaper", daemon=True).start()
    try:
        server.serve()
    finally:
        for sock in (proxy, control):
            try:
                sock.close()
            except OSError:
                pass
        if identity is not None:
            try:
                now = os.stat(path)
                if (now.st_dev, now.st_ino) == identity:
                    os.unlink(path)
            except OSError:
                pass
        # Asked to stop and the grace is over: nothing of the group it leads
        # outlives it with a dead proxy (the docstring).
        if terminated.is_set() and os.getpgrp() == os.getpid() and relay_group_child_alive():
            try:
                os.killpg(os.getpid(), signals.SIGKILL)
            except OSError:
                pass
    return EXIT_OK
