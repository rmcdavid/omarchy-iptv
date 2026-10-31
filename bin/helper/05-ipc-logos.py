# A part of bin/omarchy-iptv (D-REL-7), not a module: the helper compiles
# this file into its own namespace in the order its HELPER_PARTS lists, so
# a part sees every name the parts before it define. Run the helper.
from __future__ import annotations
# ------------------------------------------------------------- mpv IPC

class IpcPairs(list):
    """A JSON OBJECT written in this order, a key as often as it is listed:
    the per-file options of a `loadfile` (apply_channel, 2026-10-29). Python's
    dict keeps a key once, and `http-header-fields-append` has to appear once
    per header, because `-append` is the one spelling that takes its value
    verbatim -- the plain list option splits a header value at every comma
    (measured on mpv 0.41.0 against a logging server: `X-A: 1,2` arrived as
    `X-A: 1`; three `-append` keys in one object arrived as three headers,
    commas, `=`, quotes and a trailing backslash intact, in order). mpv's own
    JSON reader keeps every key of an object in order (the same measurement).
    A list of (key, value) pairs; a value may be another IpcPairs."""


def ipc_json(value: Any) -> str:
    """json.dumps, except that an IpcPairs is written as an object in its own
    order with its repeated keys. ensure_ascii=False, as request() has always
    sent: mpv reads UTF-8."""
    if isinstance(value, IpcPairs):
        return "{" + ", ".join("%s: %s" % (json.dumps(str(k), ensure_ascii=False), ipc_json(v))
                               for k, v in value) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(ipc_json(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False)


class MpvIpc:
    """Minimal client for mpv's JSON IPC: one request at a time, replies
    correlated by request_id, unsolicited events KEPT.

    Events used to be dropped where a reply was expected. `player start`
    subscribes with `request_log_messages` before the first `loadfile` and
    then has to see that load's `start-file` / `end-file` / `log-message`
    (F3), so an event a request steps over is appended to `self.events` and
    read back by `drain_events()` instead of being thrown away.
    """

    def __init__(self, path: str, timeout: float) -> None:
        self.path = path
        self.timeout = timeout
        self.sock: Any = None
        self.buffer = b""
        self.next_id = 1
        self.refused = False
        self.events: list[dict[str, Any]] = []
        self.closed = False

    def connect(self) -> None:
        import socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(self.path)
        except FileNotFoundError:
            sock.close()
            raise HelperError("not_running", "mpv socket not found")
        except ConnectionRefusedError:
            sock.close()
            self.refused = True
            raise HelperError("not_running", "mpv socket not reachable")
        except TimeoutError:
            sock.close()
            raise HelperError("not_running", "mpv socket did not accept the connection")
        except OSError as error:
            sock.close()
            raise HelperError("ipc_error", "could not connect to mpv: %s" % (error.strerror or error))
        self.sock = sock

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def read_line(self, deadline: float) -> bytes | None:
        """One JSON line from mpv, or None once mpv closed the connection."""
        assert self.sock is not None
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise HelperError("ipc_error", "mpv did not answer within %.1f s" % self.timeout)
            self.sock.settimeout(remaining)
            try:
                chunk = self.sock.recv(65536)
            except TimeoutError:
                raise HelperError("ipc_error", "mpv did not answer within %.1f s" % self.timeout)
            except (ConnectionResetError, BrokenPipeError):
                return None
            except OSError as error:
                raise HelperError("ipc_error", "could not read from mpv: %s" % (error.strerror or error))
            if not chunk:
                return None
            self.buffer += chunk
        line, _, self.buffer = self.buffer.partition(b"\n")
        return line

    def request(self, command: list[Any], allow_close: bool = False) -> dict[str, Any]:
        """Send `command` and return mpv's reply object for it.

        With allow_close, mpv closing the connection after the request was
        sent counts as `{"error": "success"}` (used by `quit`).
        """
        assert self.sock is not None
        request_id = self.next_id
        self.next_id += 1
        payload = '{"command": %s, "request_id": %d}\n' % (ipc_json(list(command)), request_id)
        try:
            self.sock.sendall(payload.encode("utf-8"))
        except (ConnectionResetError, BrokenPipeError):
            if allow_close:
                return {"error": "success", "request_id": request_id}
            raise HelperError("ipc_error", "mpv closed the connection")
        except OSError as error:
            raise HelperError("ipc_error", "could not write to mpv: %s" % (error.strerror or error))
        deadline = time.monotonic() + self.timeout
        while True:
            line = self.read_line(deadline)
            if line is None:
                if allow_close:
                    return {"error": "success", "request_id": request_id}
                raise HelperError("ipc_error", "mpv closed the connection")
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if not isinstance(message, dict):
                continue
            if message.get("request_id") == request_id:
                return message
            if "request_id" not in message:
                self.events.append(message)

    def drain_events(self, deadline: float) -> list[dict[str, Any]] | None:
        """Event lines mpv sent unasked, waiting until `deadline` (an absolute
        time.monotonic value) for one. `[]` means nothing arrived in time,
        `None` means mpv closed the connection - which under `--idle=once` is
        itself the death signal."""
        if self.events:
            drained, self.events = self.events, []
            return drained
        if self.sock is None or self.closed:
            return None
        try:
            line = self.read_line(deadline)
        except HelperError:
            return []
        if line is None:
            self.closed = True
            return None
        try:
            message = json.loads(line)
        except ValueError:
            return []
        if isinstance(message, dict) and "request_id" not in message:
            return [message]
        return []

    def command(self, *args: Any) -> Any:
        """Run a command; an mpv-side error becomes HelperError(ipc_error)."""
        reply = self.request(list(args))
        if reply.get("error") != "success":
            # Property names are safe to print; values (URLs) never are.
            what = " ".join(str(part) for part in args[:2]) if args[0] in ("set_property", "get_property") else str(args[0])
            raise HelperError("ipc_error", "mpv refused %s: %s" % (what, reply.get("error") or "unknown error"))
        return reply.get("data")

    def try_command(self, *args: Any) -> tuple[bool, Any]:
        """Like command(), but an mpv-side error yields (False, None)."""
        reply = self.request(list(args))
        if reply.get("error") != "success":
            return False, None
        return True, reply.get("data")


# ---- M2-04 logos: the survey that contacts nothing -------------------------
#
# Ruling rule 6 (the logo privacy ruling, dev branch): a generic "logos may contact
# third parties" is not informed consent when the real answer is countable. On
# the list this was measured against, turning logos on would contact 63 hosts
# and hand i.imgur.com alone a request pattern covering two thirds of the
# channels. So the number is produced BEFORE the choice, by reading the cache
# and making no request at all.
#
# Output carries HOSTS and never URLs (engineering rule 5, dev branch). A logo URL can carry a
# provider path and, on a provider whose logos sit beside its playlist, a query
# string; the host is the whole of what a user needs to judge the disclosure.
LOGO_SCHEMES = ("https",)
LOGO_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")


def logo_host(netloc: str) -> str:
    """The host a logo URL would disclose to, or "" when it discloses to none.

    The PORT is not part of the answer. The question the survey exists to
    answer is how many parties learn which channels this user has, and
    `cdn.test` and `cdn.test:8443` are one party; counting them separately
    inflates the only number in the consent sentence.

    Userinfo makes the answer "": fetch_logo refuses such a URL outright, so
    the host is never contacted, and naming it would print the credentials in
    the consent text. Mirrored by Model.splitLogoUrl.

    D-SINK-30 (2026-10-24). The answer ends at the first `;`, `=` or `&` too,
    through the same `cut_host_params` the Sources row's host goes through:
    `https://cdn.test;sid=SECRET/a.png` is a valid URL whose authority is a
    credential, urllib hands it over whole in `netloc`, and this stopped at
    `:` alone -- so the survey the consent dialog is composed from and the
    `refused a logo from %s` lines (logo_dimension_refusal, logo_chunks; since
    D-LOGO-25 logo_scans too) named
    `cdn.test;sid=secret`. The `@` test runs over the WHOLE netloc first:
    `cdn.test;u=p@evil` is refused by fetch_logo, so a cut that hid its `@`
    would count a host that is never contacted.
    """
    text = (netloc or "").strip().lower()
    if "@" in text:
        return ""
    text = cut_host_params(text)
    if text.startswith("["):
        # IPv6 literal: the bracketed half is the host, any :port follows it.
        close = text.find("]")
        return text[: close + 1] if close != -1 else ""
    return text.split(":", 1)[0]


def logo_survey(channels: Any) -> dict[str, Any]:
    """Who enabling logos would contact, counted from the cache.

    Pure: no network, no filesystem beyond what the caller already read.
    """
    rows = channels if isinstance(channels, list) else []
    hosts: dict[str, int] = {}
    schemes: dict[str, int] = {}
    with_logo = 0
    refused = 0
    for channel in rows:
        if not isinstance(channel, dict):
            continue
        raw = channel.get("logo")
        if not isinstance(raw, str) or not raw:
            continue
        with_logo += 1
        parsed = urllib.parse.urlsplit(raw)
        scheme = (parsed.scheme or "").lower()
        schemes[scheme] = schemes.get(scheme, 0) + 1
        if scheme not in LOGO_SCHEMES:
            # Counted, never contacted: rule 3 of the ruling is https only.
            refused += 1
            continue
        host = logo_host(parsed.netloc or "")
        if not host:
            # No host at all, or userinfo. fetch_logo refuses a URL carrying
            # userinfo rather than stripping it, so a survey that counted one
            # as contactable would promise a fetch that cannot happen -- and
            # would print `user:pass@provider.test` into the consent text the
            # user is reading. The credential-sink rule (engineering rule 5): every sink redacts to scheme
            # and host, and the consent dialog is a sink. Caught by
            # the shared logo-survey fixture (dev branch) before it was ever drawn.
            refused += 1
            continue
        hosts[host] = hosts.get(host, 0) + 1
    ordered = sorted(hosts.items(), key=lambda pair: (-pair[1], pair[0]))
    return {
        "channels": len(rows),
        "withLogo": with_logo,
        "wouldContact": sum(hosts.values()),
        "refused": refused,
        "hostCount": len(ordered),
        "hosts": [{"host": h, "channels": n} for h, n in ordered],
        "schemes": schemes,
        "allowedSchemes": list(LOGO_SCHEMES),
        "allowedTypes": list(LOGO_TYPES),
    }


# The most bytes of one logo's body a fetch reads (the final response's: a
# redirect's body is never read, D-LOGO-15), so the most a cached logo is.
MAX_LOGO_BYTES = 256 * 1024
# The most entries ONE source's logo directory holds (D-LOGO-12): a fetch run
# counts what is there first and fetches only while that count plus its own
# downloads stays below this, so a source's logos never exceed
# MAX_LOGO_FILES * MAX_LOGO_BYTES = 1,310,720,000 bytes (1.22 GiB) on disk. It
# used to bound downloads per RUN, and the directory grew by up to this much on
# every service start. Per source, not per install: see cache_prune for what
# every source together can hold (D-LOGO-17).
MAX_LOGO_FILES = 5000

# The DIMENSION bound, D-LOGO-11. MAX_LOGO_BYTES bounds the wrong axis: the
# decoder's cost is quadratic in a number the HEADER declares and the bytes do
# not have to honour, so a 304-byte progressive JPEG whose SOF says
# 20000x20000 took a Qt process standing in for the shell -- the lead's probe,
# an Image declared exactly as the guide's row slot declares it -- to 840 MB,
# and a 555-byte 3-component one to 1,239 MB (measured 2026-10-09 on Qt
# 6.11.2; the table is in the QA results on the dev branch). The shell itself
# was never fed one, deliberately. Qt's own allocation limit cannot refuse a JPEG
# on that path at all: it is compared against ceil(dim/8)^2 * 4 -- the image
# already divided by libjpeg's largest scale denominator -- and the format's own
# largest dimension, 65535, gives ceil(65535/8) = 8192 with
# 8192 * 8192 * 4 = 268,435,456 bytes, exactly the 256 MiB default, so the
# guard is unreachable rather than weak.
#
# What these two numbers cost AT the bound, which is the reason they are these
# numbers: the largest area either of them admits is MAX_LOGO_PIXELS, and a
# 4:4:4 progressive JPEG of that area holds
# 4,194,304 px x 3 components x 2 bytes per coefficient = 25,165,824 bytes,
# 24 MiB of coefficients -- the same order as the 23.8 MiB Qt was already
# willing to allocate before any of this existed. The side cap is the second
# half because area alone would admit 65535x64, which is 4.2 Mpx laid out as
# one enormous row. A 1920x1080 provider banner is 2,073,600 px with both
# sides under the side cap and passes, as does every square logo up to
# 2048x2048.
MAX_LOGO_SIDE = 4096
MAX_LOGO_PIXELS = 4194304         # 2048 * 2048

# The SCAN bound, D-LOGO-25 (2026-10-29): the dimension bound's CPU axis. A
# progressive JPEG is decoded scan by scan, and a file within the byte cap
# can carry thousands of scans. Measured on Qt 6.11.2 with an Image
# declared as the row slot (offscreen) and with libjpeg-turbo 3.2.0's djpeg,
# on files of 1 to 512 scans: about 0.85 ms of CPU a scan for first scans
# and 4.1 ms for refinement scans, on the shell's image reader thread, which
# every other asynchronous image in the shell queues behind.
# _jpeg_dimensions stops at the frame header and never saw a scan. 64 is above the most libjpeg's own progressive scripts write for
# any component count it encodes -- 10 for YCbCr, 6 for grey (measured with
# cjpeg -progressive), 6 a component otherwise, at most 10 components -- and
# costs at most about a quarter of a second at the dimension bound.
MAX_JPEG_SCANS = 64

# How much of a logo the cached-file sweep reads before asking the parsers
# (R5). Every header they read sits either at a fixed offset -- PNG, GIF and
# WEBP all declare their size inside the first 30 bytes -- or within the APPn
# metadata a JPEG puts before its first frame header. The arithmetic for that
# second case, stated exactly because an earlier version of this comment got
# it wrong by four bytes: a segment's length field is at most 65,535 and
# counts itself, so a maximal APPn segment is 65,537 bytes with its marker,
# and two of them after the 2-byte SOI put the frame marker at offset
# 131,076 -- four bytes PAST this read. So this covers one maximal segment and
# nearly two, not two; a file with two (a reviewer built one, 131,445 bytes,
# a valid 64x64) parses as None from this read alone and is proved by the
# second read below. It is a fixed read rather than the whole file so that
# 5,000 of them stay cheap. It is not a window on the PARSERS: `write_logo`
# hands them every byte it holds, and `logo_file_within_bounds` reads the
# rest of a larger file when the small read cannot prove it, so the sweep and
# the gate can never disagree about the same file and sweep it on every run.
LOGO_HEADER_BYTES = 128 * 1024


def logo_filename(url: str) -> str:
    """A name derived from the URL, never FROM the URL.

    The provider's path never reaches the filesystem: it can carry a channel
    name, a subscriber id or a query string, and a path from an untrusted
    string is also how a traversal gets written outside the cache. fnv1a32 of
    the URL plus the extension implied by the content type at write time.
    """
    return fnv1a32(url)


def logo_opener(host: str, policy: Any = None) -> Any:
    """An opener that enforces the https rule on EVERY hop, not just the first.

    D-LOGO-1. `fetch_logo` checked the scheme of the URL it was handed and then
    called the bare `urllib.request.urlopen`, which uses the module-global
    default opener -- and urllib's default redirect handler happily follows a
    302 to `http://` or `ftp://`. So an https logo could redirect the fetch
    into cleartext, or onto an unauthenticated FTP connection, and an ftp
    target would even pass the content-type gate because urllib synthesizes
    Content-Type for an FTP response from the filename.

    That breaks two things this feature is built on: RULING-LOGOS.md (dev
    branch) rule 3, https only, which this function's own docstring claims;
    and the consent sentence, which tells the user how many hosts will be
    contacted and names the busiest.

    `make_opener` already exists for this class of bug (S-06) but is one step
    too permissive here: it allows http as well as https, which is right for a
    playlist and wrong for a logo. This is the narrower sibling.

    RESIDUAL, stated rather than rounded away: a redirect to a different HTTPS
    host is allowed, and the consent count does not cover it. Refusing every
    cross-host redirect would break ordinary CDN behaviour, and the disclosure
    is to a party the named host chose rather than one this plugin invented.
    It is transient, carries no credentials, and is reasoned about here rather
    than left implicit.

    D-LOGO-15: the handler is unread_redirect_handler's, so a redirect's body
    is never read. This handler overrode redirect_request alone, and the
    stdlib's http_error_302 (and 301, 303, 307, 308, the same function) read
    each 3xx body whole before following it, up to ten hops, with no byte cap:
    MAX_LOGO_BYTES bounded the final response only. The TLS context is the
    one limit_memory prepared, as make_opener's is, so the CA store is loaded
    once a run and before the memory limit rather than once a logo under it.

    D-SINK-40 (2026-10-29): and never to an address on this machine or a
    local network, on ANY hop -- the first included, because a logo URL is
    the provider's choice. The check is the connect-time one every fetch
    makes (DestinationPolicy.for_logos), so an https logo that redirects to
    127.0.0.1 or 192.168.1.1, or whose name answers one, opens no socket
    there; it is refused as `local_address` and counted with the policy
    refusals. The residual above is narrowed to GLOBAL https hosts.
    """
    import urllib.request

    if policy is None:
        policy = DestinationPolicy.for_logos()

    class LogoRedirectHandler(unread_redirect_handler()):
        def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
            parsed = urllib.parse.urlsplit(newurl)
            if parsed.scheme.lower() not in LOGO_SCHEMES:
                try:
                    fp.close()
                except OSError:
                    pass
                raise HelperError("logo_redirect",
                                  "a logo from %s redirected to '%s', which is not https"
                                  % (host, parsed.scheme.lower() or "no scheme"))
            if "@" in parsed.netloc:
                try:
                    fp.close()
                except OSError:
                    pass
                raise HelperError("logo_redirect",
                                  "a logo from %s redirected to a URL carrying userinfo" % host)
            new = super().redirect_request(req, fp, code, msg, headers, newurl)
            if new is not None:
                # Nothing sets these on a logo request; removed anyway so a
                # future caller cannot reintroduce the leak by adding a header.
                for name in ("Authorization", "Cookie"):
                    new.remove_header(name)
            return new

    # No FTPHandler: build_opener adds the defaults, and the redirect guard
    # already refuses an ftp target, but a handler that cannot be reached is
    # one fewer thing to reason about.
    # D-SRC-62: the connections are the stdlib's with the host-name lookup
    # bounded (bounded_handlers), as make_opener's are.
    handlers: list[Any] = [LogoRedirectHandler(), *bounded_handlers(TLS_CONTEXT.get("https"), policy)]
    opener = urllib.request.build_opener(*handlers)
    opener.handlers = [h for h in opener.handlers
                       if h.__class__.__name__ not in ("FTPHandler", "CacheFTPHandler",
                                                       "FileHandler", "DataHandler")]
    return opener


# D-LOGO-16 (R30e): the most one logo may take, in seconds, from before its
# connection is opened to its last byte, redirects included, whatever the
# per-read `--timeout` (10 s by default) allows each step. A 256 KiB logo in
# 30 s needs about 70 kbit/s. Before this the only bound was that per-read
# timeout, so a host sending one byte inside every 10 s held one logo for up
# to 262,145 x 10 s, about 30 days, and the run fetches one logo at a time.
# The run as a whole has its own deadline, LOGO_RUN_DEADLINE (06-failed.py),
# and a logo is never given more than what is left of it. Mirrored by
# Model.LOGO_DEADLINE_MS through the shared logo-deadlines fixture.
LOGO_DEADLINE = 30.0


def fetch_logo(url: str, timeout: float, budget: float | None = None) -> tuple[bytes, str]:
    """Fetch one logo under the ruling's guards. Returns (bytes, content type).

    Deliberately NOT read_http_source. That path sends an Authorization header
    whenever the URL carries userinfo, which is right for a playlist and is the
    one thing a logo request must never do: a provider whose logos sit beside
    its playlist would receive the subscription credentials as a side effect of
    a picture. This sends no credentials, follows no userinfo, and refuses
    anything that is not https.

    The whole fetch -- connect, TLS, headers, every redirect (whose bodies are
    never read) and the body -- runs under ONE wall-clock deadline of `budget`
    seconds, LOGO_DEADLINE when not given (FetchDeadline, R30e), and answers
    `logo_timeout` when it passes.
    """
    import urllib.request
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() not in LOGO_SCHEMES:
        raise HelperError("logo_scheme", "refused a non-https logo host")
    if "@" in parsed.netloc:
        raise HelperError("logo_userinfo", "refused a logo URL carrying userinfo")
    host = parsed.netloc.lower()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "image/*"})
    try:
        with FetchDeadline(LOGO_DEADLINE if budget is None else budget):
            data, ctype = read_logo_response(logo_opener(host), request, timeout, host)
    except FetchExpired:
        raise HelperError("logo_timeout", "a logo from %s took longer than its deadline" % host) from None
    if len(data) > MAX_LOGO_BYTES:
        raise HelperError("logo_too_large", "a logo from %s exceeds %d KB" % (host, MAX_LOGO_BYTES // 1024))
    return data, ctype


def read_logo_response(opener: Any, request: Any, timeout: float, host: str) -> tuple[bytes, str]:
    """One logo's response under the type gate, or `logo_fetch` naming the
    host and the error's CLASS only, never its text (rule 5).

    D-LOGO-24 (2026-10-29): http.client's own errors are not OSErrors, and
    urllib wraps only OSErrors, so they used to pass straight through to
    main()'s `internal`, ending the whole run before the failure memo was
    written -- and the same logo ended every later run the same way: a
    status line that is not one (BadStatusLine), a header line or a header
    count over http.client's limits (LineTooLong, HTTPException), a chunked
    body that does not parse (IncompleteRead), and InvalidURL, raised before
    any connection for a URL with a space or a control character in its
    path or a port that is not a number -- whose text quotes the path and
    query. read_http_response has caught them since D-SRC-59; this is the
    same catch on the logo path, and the run keeps a backstop of its own
    (fetch_logo_run) for whatever escapes next."""
    import http.client
    import urllib.error
    try:
        with opener.open(request, timeout=timeout) as response:
            ctype = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype not in LOGO_TYPES:
                raise HelperError("logo_type", "refused %s from %s" % (ctype or "an unnamed type", host))
            data = response.read(MAX_LOGO_BYTES + 1)
    except HelperError:
        raise
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as error:
        raise HelperError("logo_fetch", "could not fetch a logo from %s: %s" % (host, error.__class__.__name__))
    return data, ctype


# The first bytes each allowed type must begin with. The content type is the
# SERVER's claim about bytes we are about to store and hand to an image
# decoder, and nothing so far has checked the claim against the payload.
#
# Measured on Qt 6.11.2 before this was written: QML's Image loads a local
# file by CONTENT, not by name. An extension-less PNG, GIF and JPEG all reach
# Image.Ready at their true size, and so does a PNG named `.txt`. So the
# extension the cache used to append was never a gate -- a file whose bytes
# are SVG renders as SVG whatever it is called, and Qt's SVG renderer is a
# larger surface than a bitmap decoder.
#
# Checking the magic is the gate the extension only looked like. It is done
# here rather than at write time so a mismatch is refused BEFORE anything
# touches the disk.
LOGO_MAGIC = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    # RIFF....WEBP: the size sits between the two, so both halves are checked.
    "image/webp": (b"RIFF",),
}


def logo_bytes_match_type(data: bytes, ctype: str) -> bool:
    """Do these bytes actually begin the way `ctype` says they do?"""
    prefixes = LOGO_MAGIC.get(ctype)
    if not prefixes:
        return False
    if ctype == "image/webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return any(data.startswith(prefix) for prefix in prefixes)


def logo_sniff_type(data: bytes) -> str | None:
    """Which allowed type these bytes actually are, or None.

    The cache file name is the fnv1a32 of the URL and nothing else, so a file
    on disk carries no record of the content type it arrived with. The sweep
    has to ask the bytes. Deliberately the same predicate the gate uses, so
    there is one answer to "what is this" and not two.
    """
    for ctype in LOGO_TYPES:
        if logo_bytes_match_type(data, ctype):
            return ctype
    return None


# A JPEG frame header is SOF0..SOF15, which is 0xC0..0xCF MINUS the three
# markers that share that range and are not frames: 0xC4 DHT, 0xC8 JPG and
# 0xCC DAC. Listed rather than ranged so the exclusions are readable. A reader
# that takes only 0xC0..0xC2 -- baseline plus the two common progressive
# frames -- cannot see SOF3 or any of the arithmetic-coded and lossless
# frames, and a frame header this cannot find means None, which R4 turns into
# a refusal: the narrow reader refuses real images rather than passing bombs.
JPEG_SOF_MARKERS = frozenset(
    (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF)
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    """Walk the markers from the SOI and read the first frame header."""
    size = len(data)
    if size < 4 or data[0] != 0xFF or data[1] != 0xD8:
        return None
    pos = 2
    while pos < size:
        if data[pos] != 0xFF:
            # Not standing on a marker. Entropy-coded bytes only follow an
            # SOS and this returns at the SOS, so the stream is malformed:
            # refuse rather than hunting forward for the next 0xFF, which is
            # how a reader ends up reading a number out of image data.
            return None
        while pos < size and data[pos] == 0xFF:
            pos += 1                      # fill bytes are legal before a marker
        if pos >= size:
            return None
        marker = data[pos]
        pos += 1
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:
            continue                      # TEM, RSTn, a repeated SOI: no payload
        if marker in (0xD9, 0xDA):
            # EOI or the first scan, with no frame header seen. A conforming
            # file puts the SOF before the SOS, so there is nothing to read.
            return None
        if pos + 2 > size:
            return None
        length = (data[pos] << 8) | data[pos + 1]
        if length < 2:
            return None
        if marker in JPEG_SOF_MARKERS:
            # length(2) precision(1) height(2) width(2) components(1)
            if length < 8 or pos + 7 > size:
                return None
            height = (data[pos + 3] << 8) | data[pos + 4]
            width = (data[pos + 5] << 8) | data[pos + 6]
            return (width, height)
        if pos + length > size:
            return None                   # truncated segment: refuse, do not guess
        pos += length
    return None


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    """IHDR, which the spec requires to be the first chunk."""
    if not data.startswith(PNG_SIGNATURE) or len(data) < 24:
        return None
    # Fixed offsets, and a chunk that is not IHDR here is not a chunk this
    # will read dimensions out of: trusting the first chunk's NAME rather
    # than its position is how a crafted file gets a second opinion.
    if data[12:16] != b"IHDR" or int.from_bytes(data[8:12], "big") != 13:
        return None
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    if width > 0x7FFFFFFF or height > 0x7FFFFFFF:
        return None                       # the spec's own ceiling
    return (width, height)


def _gif_skip_subblocks(data: bytes, pos: int) -> int | None:
    """Step over a data sub-block chain; None when it runs off the end."""
    size = len(data)
    while True:
        if pos >= size:
            return None
        count = data[pos]
        pos += 1
        if count == 0:
            return pos
        pos += count


def _gif_dimensions(data: bytes) -> tuple[int, int] | None:
    """The logical screen, widened to every frame's right and bottom EDGE.

    The LOGICAL SCREEN is the allocation: the lead's measurement includes a
    110-byte GIF whose canvas is 65500x65500 and whose only frame is 64x64,
    and it refused at the control's memory for the canvas, not the frame. A
    frame descriptor can declare a rectangle larger than the canvas, so the
    answer is the maximum over both.

    An edge and not a size (D-LOGO-14, the maintainer on #11892): Qt 6.11.2's
    handler sizes a ZERO screen from the first frame's left+width and
    top+height before it allocates or scales, so a 1x1 frame at 8190,8190
    under a 0x0 screen is an 8191x8191 canvas, and this read it as 1x1. A
    zero screen or a zero frame is refused rather than reasoned about.

    The walk has to reach the trailer. Qt clips a later frame to the canvas
    (read in its source, not measured), and this does not rely on it: a
    frame this did not reach is a frame whose size is unproven, and R4 makes
    unproven a refusal. The cost is stated rather than hidden: a GIF whose
    block structure does not complete inside the bytes handed to this
    function is refused, and for the sweep that is the whole file (see
    logo_file_within_bounds).
    """
    size = len(data)
    if size < 13 or data[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    width = data[6] | (data[7] << 8)
    height = data[8] | (data[9] << 8)
    if not width or not height:
        return None
    flags = data[10]
    pos = 13
    if flags & 0x80:
        pos += 3 * (1 << ((flags & 0x07) + 1))     # global colour table
    while True:
        if pos >= size:
            return None
        block = data[pos]
        pos += 1
        if block == 0x3B:                          # trailer: the walk is complete
            return (width, height)
        if block == 0x21:                          # extension: label, sub-blocks
            pos += 1
            nxt = _gif_skip_subblocks(data, pos)
            if nxt is None:
                return None
            pos = nxt
            continue
        if block == 0x2C:                          # image descriptor
            # left(2) top(2) width(2) height(2) packed(1) after the separator.
            if pos + 9 > size:
                return None
            left = data[pos] | (data[pos + 1] << 8)
            top = data[pos + 2] | (data[pos + 3] << 8)
            frame_w = data[pos + 4] | (data[pos + 5] << 8)
            frame_h = data[pos + 6] | (data[pos + 7] << 8)
            if not frame_w or not frame_h:
                return None                        # a zero-sized frame
            packed = data[pos + 8]
            pos += 9
            if packed & 0x80:
                pos += 3 * (1 << ((packed & 0x07) + 1))   # local colour table
            if pos >= size:
                return None
            pos += 1                               # LZW minimum code size
            nxt = _gif_skip_subblocks(data, pos)
            if nxt is None:
                return None
            pos = nxt
            width = max(width, left + frame_w)
            height = max(height, top + frame_h)
            continue
        return None                                # not a block this format defines


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    """All three variants: VP8 lossy, VP8L lossless, VP8X extended.

    All three, because R4 refuses what it cannot read, so skipping a variant
    would refuse real lossless and real animated logos rather than failing
    open. The container is validated the way logo_bytes_match_type validates
    it -- RIFF....WEBP -- before any chunk is believed.
    """
    size = len(data)
    if size < 16 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    # The RIFF size counts everything after the first 8 bytes. It is used only
    # as an upper bound: a file may carry trailing bytes, and the bytes handed
    # to this function may be a prefix of a larger file.
    end = min(size, 8 + int.from_bytes(data[4:8], "little"))
    pos = 12
    while pos + 8 <= end:
        fourcc = data[pos:pos + 4]
        length = int.from_bytes(data[pos + 4:pos + 8], "little")
        body = pos + 8
        if body + length > end:
            return None                   # truncated chunk
        if fourcc == b"VP8X":
            # 24-bit canvas width-1 and height-1 after 4 bytes of flags. VP8X
            # states the CANVAS, which is what an extended file -- alpha,
            # animation, or a plain still -- is composed into and allocated at,
            # so it is the number that matters and the inner frame cannot
            # enlarge it.
            if length < 10:
                return None
            width = int.from_bytes(data[body + 4:body + 7], "little") + 1
            height = int.from_bytes(data[body + 7:body + 10], "little") + 1
            return (width, height)
        if fourcc == b"VP8 ":
            if length < 10:
                return None
            if data[body] & 0x01:
                return None               # not a keyframe: carries no dimensions
            if data[body + 3:body + 6] != b"\x9d\x01\x2a":
                return None               # start code absent
            width = int.from_bytes(data[body + 6:body + 8], "little") & 0x3FFF
            height = int.from_bytes(data[body + 8:body + 10], "little") & 0x3FFF
            return (width, height)
        if fourcc == b"VP8L":
            if length < 5 or data[body] != 0x2F:
                return None
            # 14 bits of width-1 then 14 bits of height-1, bit-packed little
            # endian after the signature byte.
            bits = int.from_bytes(data[body + 1:body + 5], "little")
            return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        pos = body + length + (length & 1)         # chunks pad to even length
    return None


def logo_dimensions(data: bytes, ctype: str) -> tuple[int, int] | None:
    """The size the header DECLARES, or None when it cannot be read.

    D-LOGO-11. Nothing here decodes anything: these are the provider's own
    claims about its bytes, read out of the header, which is exactly the
    number Qt's cost is quadratic in.

    None means "cannot tell", never "small". A bounds check that cannot tell
    those two apart IS the defect, so every caller treats None as a refusal
    (R4): a blank slot in a decorative feature against the user's shell.

    All four allowed types, not only JPEG. JPEG is the only one of the four
    that Qt's decoder can scale, which is the only reason it is the only one
    exposed today -- and that asymmetry is upstream behaviour nobody here
    controls, so a Qt that learns to scale PNG during decode must not reopen
    this in silence (R3).
    """
    if not isinstance(data, (bytes, bytearray)) or not data:
        return None
    raw = bytes(data)
    if ctype == "image/jpeg":
        dims = _jpeg_dimensions(raw)
    elif ctype == "image/png":
        dims = _png_dimensions(raw)
    elif ctype == "image/gif":
        dims = _gif_dimensions(raw)
    elif ctype == "image/webp":
        dims = _webp_dimensions(raw)
    else:
        return None
    if dims is None:
        return None
    width, height = dims
    if width <= 0 or height <= 0:
        return None                       # a zero side is not an image
    return (width, height)


def logo_within_bounds(data: bytes, ctype: str) -> bool:
    """True ONLY when the dimensions parse and both bounds hold."""
    dims = logo_dimensions(data, ctype)
    if dims is None:
        return False
    width, height = dims
    if width > MAX_LOGO_SIDE or height > MAX_LOGO_SIDE:
        return False
    return width * height <= MAX_LOGO_PIXELS


def jpeg_scan_count(data: bytes) -> int:
    """An UPPER bound on the scans a decoder runs over this JPEG (D-LOGO-25):
    every occurrence of the byte pair FF DA. A scan starts only at an SOS
    marker, and libjpeg finds a marker by reading 0xFF (any fill bytes) and
    then its code, so every scan it can start is one of these pairs --
    including one it reaches by skipping garbage, which a marker walk that
    stopped at the garbage would miss. Entropy-coded data cannot hold the
    pair (an 0xFF in it is followed by 0x00 or a restart marker), so the
    count is exact for an ordinary file and over by one for an EXIF
    thumbnail or a coincidence inside a table: an over-count only refuses
    more. One linear pass in C, nothing decoded."""
    return bytes(data).count(b"\xff\xda")


def logo_scans_within_bound(data: bytes, ctype: str) -> bool:
    """True for every type but JPEG; for a JPEG, its scan count is at most
    MAX_JPEG_SCANS (D-LOGO-25). Over ALL of a file's bytes: a count over a
    prefix is a lower bound and proves nothing."""
    return ctype != "image/jpeg" or jpeg_scan_count(data) <= MAX_JPEG_SCANS


def logo_dimension_refusal(url: str, data: bytes, ctype: str) -> str:
    """The refusal text: a HOST and numbers, never a URL (rule 5, R6)."""
    host = logo_host(urllib.parse.urlsplit(url).netloc or "") or "an unnamed host"
    dims = logo_dimensions(data, ctype)
    if dims is None:
        return "refused a logo from %s: its header could not be read" % host
    return ("refused a logo from %s: its header declares %dx%d, over the %d px side "
            "or %d pixel bound" % (host, dims[0], dims[1], MAX_LOGO_SIDE, MAX_LOGO_PIXELS))


def _read_logo_prefix(path: str, limit: int) -> bytes | None:
    # os.read on the descriptor, not a buffered file object: the sweep reads
    # every cached logo on every start, twice for a PNG since D-LOGO-13, and
    # the buffered read cost twice as much (5,000 cached 220x120 PNGs,
    # 2026-10-15, medians: `logos --fetch` 1,003-1,069 ms buffered, 815-872
    # ms here, 725-735 ms before D-LOGO-13 added the second read and its CRC).
    try:
        fd = open_regular(path)
    except OSError:
        return None
    parts: list[bytes] = []
    try:
        while limit > 0:
            part = os.read(fd, limit)
            if not part:
                break
            parts.append(part)
            limit -= len(part)
    except OSError:
        return None
    finally:
        os.close(fd)
    return b"".join(parts)


def logo_file_within_bounds(path: str) -> bool:
    """Is a file ALREADY in the cache within the bound (R5)?

    Reads LOGO_HEADER_BYTES first, which is every header the parsers know how
    to read. The second read is what keeps this and `write_logo` from
    disagreeing about one file: the gate sees all the bytes, so when the small
    read cannot prove a file that has MORE bytes on disk, the rest is read --
    under the same MAX_LOGO_BYTES the gate enforces -- rather than refusing
    something the gate would accept and sweeping it again on every run. The
    common case, and every case for a logo under 128 KiB, is one read.

    A file whose bytes are none of the four allowed types is refused too. The
    magic check has guarded the write path since M2-04, but a file on disk is
    not evidence that it went through it.
    """
    head = _read_logo_prefix(path, LOGO_HEADER_BYTES)
    if not head:
        return False
    ctype = logo_sniff_type(head)
    if ctype is None:
        return False
    complete = len(head) < LOGO_HEADER_BYTES          # the small read was the whole file
    # D-LOGO-25: a JPEG's scans are counted over the WHOLE file, so a JPEG
    # the small read did not finish is read whole whatever its header says.
    if logo_within_bounds(head, ctype) and (complete or ctype != "image/jpeg"):
        return logo_scans_within_bound(head, ctype)
    if complete:
        return False
    whole = _read_logo_prefix(path, MAX_LOGO_BYTES + 1)
    if whole is None or len(whole) > MAX_LOGO_BYTES:
        return False                      # over the byte cap as well
    return logo_within_bounds(whole, ctype) and logo_scans_within_bound(whole, ctype)


# D-LOGO-13, raised by the marketplace maintainer against the shipped 0.13.6:
# D-LOGO-11 bounds what a PNG's header declares, and the rest of the file
# reached the decoder as the provider wrote it -- including zTXt, iTXt and
# iCCP, which libpng INFLATES while it reads the header, before a row is
# decoded and whatever `sourceSize` says. The byte cap bounds them compressed
# and nothing bounds them inflated. So a PNG is cached in a canonical form
# holding only what drawing needs: IHDR, PLTE, IDAT, IEND, and these four
# small colour chunks at the lengths the spec gives them (tRNS's depends on
# the colour type and the palette). Everything else -- text, profiles, eXIf,
# APNG frames, private chunks -- is dropped, so IDAT is the only compressed
# stream left, and its memory is the dimensions D-LOGO-11 bounds. Measured
# here: nothing. The fix is judged by what it keeps and drops.
PNG_COLOUR_CHUNKS = {b"gAMA": 4, b"cHRM": 32, b"sRGB": 1, b"tRNS": 0}
MAX_PNG_CHUNKS = 4096


def canonical_png(data: bytes) -> bytes | None:
    """The PNG with only the chunks drawing needs, or None to refuse it.

    Walks the chunk list and inflates NOTHING. Every chunk is copied
    verbatim or dropped whole, so the IDAT bytes -- and the pixels -- are the
    provider's own, and a canonical file comes back byte for byte (the sweep
    relies on that: anything else would be rewritten on every start). None
    when the walk cannot prove what the file holds: a bad CRC on ANY chunk,
    dropped ones included; a chunk running off the end or no IEND; anything
    after IEND; more than MAX_PNG_CHUNKS chunks; IHDR not first or twice; no
    IDAT, or IDAT split by another chunk; a second or misplaced PLTE, or one
    that is not 1-256 entries; a critical chunk this does not know (libpng
    refuses those too). A colour chunk at the wrong length, out of its place
    or after one already kept is DROPPED rather than refused, because libpng
    ignores it as well, so dropping changes nothing it draws.
    """
    if not isinstance(data, (bytes, bytearray)) or not data.startswith(PNG_SIGNATURE):
        return None
    data = bytes(data)
    view = memoryview(data)               # the CRC reads it in place
    size, pos, count, colour, palette = len(data), 8, 0, -1, 0
    kept, seen, last = [], set(), b""
    while pos + 12 <= size and count < MAX_PNG_CHUNKS:
        count += 1
        length = int.from_bytes(data[pos:pos + 4], "big")
        kind = data[pos + 4:pos + 8]
        end = pos + 12 + length
        if (end > size or not kind.isalpha()
                or zlib.crc32(view[pos + 4:end - 4]) != int.from_bytes(data[end - 4:end], "big")):
            return None
        keep = True
        if count == 1:
            if kind != b"IHDR" or length != 13:
                return None
            colour = data[pos + 17]
        elif kind == b"IEND":
            if length or b"IDAT" not in seen or end != size:
                return None
            if len(kept) + 1 == count:
                return data               # nothing to drop: already canonical
            return PNG_SIGNATURE + b"".join(data[a:b] for a, b in kept) + data[pos:end]
        elif kind == b"IDAT":
            if b"IDAT" in seen and last != b"IDAT":
                return None
        elif kind == b"PLTE":
            if kind in seen or b"IDAT" in seen or not 0 < length <= 768 or length % 3:
                return None
            palette = length // 3
        elif kind in PNG_COLOUR_CHUNKS:
            if kind == b"tRNS":
                fits = length == {0: 2, 2: 6}.get(colour) or colour == 3 and 0 < length <= palette
            else:
                fits = length == PNG_COLOUR_CHUNKS[kind] and b"PLTE" not in seen
            keep = fits and kind not in seen and b"IDAT" not in seen
        elif not kind[0] & 0x20:
            return None                   # a critical chunk not named above, IHDR again included
        else:
            keep = False
        if keep:
            kept.append((pos, end))
            seen.add(kind)                # dropped chunks never count as seen
        last = kind
        pos = end
    return None


def canonical_logo_file(path: str, rewrite: bool = True) -> str:
    """D-LOGO-13 for a file already in the cache, which every version before
    0.14.1 wrote verbatim. -> "as-is" when it may be announced as it stands
    (a canonical PNG, or another type), "rewritten" when it was a PNG with
    other chunks and now holds the canonical form (atomically, 0600), or ""
    when it may not be announced at all. Read under the byte cap plus one, so
    a PNG longer than that cannot end in IEND inside the read and is refused.

    `rewrite` False (D-LOGO-23, R32f): a READ-ONLY check, for a run that
    does not hold the folder's lock. A PNG that would need rewriting is then
    "" -- not announced, and left exactly as it is for the run that holds
    the lock -- because the guide may only ever be pointed at a canonical
    file, and this run may write nothing.
    """
    data = _read_logo_prefix(path, MAX_LOGO_BYTES + 1)
    if not data:
        return ""
    if not data.startswith(PNG_SIGNATURE):
        return "as-is"
    canon = canonical_png(data)
    if canon is None:
        return ""
    if canon == data:
        return "as-is"
    if not rewrite:
        return ""
    try:
        write_bytes_atomic(path, canon)
    except OSError:
        return ""
    return "rewritten"


def write_logo(logo_dir: str, url: str, data: bytes, ctype: str) -> str:
    """Write one logo 0600 into a 0700 directory. Returns the file name.

    The name is the fnv1a32 of the URL and NOTHING else. It used to carry an
    extension implied by the content type, which cost a second source of
    truth: the guide would have had to read an index to turn a channel's logo
    URL into a file name, and that index is a parse inside the 150 ms open
    budget. Qt names nothing from the extension anyway (see LOGO_MAGIC), so
    dropping it removes a file the guide would have had to read and takes
    nothing away.
    """
    if ctype not in LOGO_TYPES:
        raise HelperError("logo_type", "refused an unlisted content type")
    if not logo_bytes_match_type(data, ctype):
        raise HelperError("logo_bytes", "refused bytes that are not %s" % ctype)
    # D-LOGO-11, and deliberately HERE: after the magic check, before
    # ensure_private_dir, so a refusal still creates nothing on disk -- not
    # the file, not the directory. The helper is the process that is allowed
    # to die; the shell, which renders this, is not, and `Image` has no lever
    # for this anyway (R1).
    if not logo_within_bounds(data, ctype):
        raise HelperError("logo_dimensions", logo_dimension_refusal(url, data, ctype))
    if not logo_scans_within_bound(data, ctype):
        # D-LOGO-25: the same place, the same reason, the decoder's CPU.
        host = logo_host(urllib.parse.urlsplit(url).netloc or "") or "an unnamed host"
        raise HelperError("logo_scans", "refused a logo from %s: its JPEG carries %d scans, over the %d scan bound"
                          % (host, jpeg_scan_count(data), MAX_JPEG_SCANS))
    if ctype == "image/png":
        # D-LOGO-13: only the canonical form is cached, and a PNG whose
        # chunks cannot be walked is not cached at all. Same place, same
        # reason: a refusal still creates nothing on disk.
        canon = canonical_png(data)
        if canon is None:
            host = logo_host(urllib.parse.urlsplit(url).netloc or "") or "an unnamed host"
            raise HelperError("logo_chunks", "refused a logo from %s: its PNG chunks are malformed" % host)
        data = canon
    name = logo_filename(url)
    path = os.path.join(logo_dir, name)
    # D-SRC-72: a logo that cannot be put in the cache -- the disk full, the
    # folder not writable, something else at the file's name -- is refused
    # with the playlist verb's code (cache_unwritable, D-SRC-69), naming the
    # file (a hash of the URL, never the URL) and the error's own words. It
    # used to reach main()'s `internal` and end the run with no summary.
    # The run stops FETCHING at it (fetch_logo_run): this is not the
    # address's failure, and a logo it cannot keep is a request for nothing.
    # A logo folder that is a link to nothing stays R25c's FolderUnusable.
    try:
        ensure_private_dir(logo_dir)
        write_bytes_atomic(path, data)
    except FolderUnusable:
        raise
    except OSError as io_error:
        raise cache_unwritable(path, io_error) from None
    return name


