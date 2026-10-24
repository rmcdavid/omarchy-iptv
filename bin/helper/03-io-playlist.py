# A part of bin/omarchy-iptv (D-REL-7), not a module: the helper compiles
# this file into its own namespace in the order its HELPER_PARTS lists, so
# a part sees every name the parts before it define. Run the helper.
from __future__ import annotations
# ------------------------------------------------------------------- IO

# validate_source_url codes -> the helper's runtime error codes of 0.1 (the
# guide renders these through Model.statusReason; CLI users see them too).
_RESOLVE_CODES = {"empty": "no_source", "scheme": "unsupported_scheme", "invalid": "bad_url", "relative_path": "bad_url"}


def resolve_source(url: str, label: str = "playlist") -> tuple[str, str]:
    """-> ("http", normalized url) or ("file", absolute path). Refuses
    anything else through validate_source_url (D11: the guide and the
    helper accept exactly the same set; the 2,048-character cap and control
    characters are enforced here too). A leading `~` is expanded first, as
    in 0.1, for values set from the command line."""
    value = (url or "").strip()
    if value.startswith("~"):
        value = os.path.expanduser(value)
    result = validate_source_url(value)
    if not result["ok"]:
        code = _RESOLVE_CODES.get(result["code"], result["code"])
        if code == "no_source":
            raise HelperError(code, "no %s URL configured" % label)
        raise HelperError(code, "%s %s" % (label, result["message"]))
    return result["kind"], result["url"]


def read_capped(stream: Any, limit: int) -> bytes:
    """At most `limit` + 1 bytes of `stream`, read HTTP_CHUNK at a time.

    D-M3U-1. `stream.read(limit + 1)` looks the same and is not: CPython
    allocates the whole `limit + 1` bytes before it reads one, so every
    playlist, a three-line one included, reserved the 64 MiB input cap --
    measured as the floor of every `playlist` run under an address-space
    limit, 93 MiB for a 3-channel file and for a 10,000-channel one alike.
    In chunks, what is reserved is what arrived (and once more while they
    are joined). The caller still decides what more than `limit` means."""
    chunks: list[bytes] = []
    total = 0
    while total <= limit:
        chunk = stream.read(min(HTTP_CHUNK, limit + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def read_local_source(path: str, label: str = "playlist") -> bytes:
    """Messages carry the base name only, never the full path (R12, D-QA-12)."""
    real = os.path.realpath(path)
    name = os.path.basename(real) or "file"
    if not os.path.isabs(real) or real.startswith(("/proc/", "/sys/", "/dev/")):
        raise HelperError("unsafe_path", "refusing to read a %s from /proc, /sys or /dev" % label)
    if not os.path.isfile(real):
        raise HelperError("not_found", "%s file not found: %s" % (label, name))
    size = os.path.getsize(real)
    if size > MAX_SOURCE_BYTES:
        raise HelperError("too_large", "%s file %s is larger than %d MB" % (label, name, MAX_SOURCE_BYTES // (1024 * 1024)))
    # R23b (rule 15): the path is the user's own, but what is at it can be
    # swapped between the isfile above and this open, and a FIFO would hang
    # the fetch until the service's watchdog killed it.
    try:
        fd = open_regular(real)
    except NotRegularFile:
        raise HelperError("not_found", "%s file not found: %s" % (label, name)) from None
    with os.fdopen(fd, "rb") as handle:
        return read_capped(handle, MAX_SOURCE_BYTES)


def split_userinfo(url: str) -> tuple[str, str]:
    """-> (URL without user:pass@, "user:pass" or ""). urllib does not accept
    userinfo in the netloc, so it is sent as HTTP Basic auth instead."""
    parts = urllib.parse.urlsplit(url)
    if parts.username is None:
        return url, ""
    host = parts.hostname or ""
    if ":" in host:
        host = "[" + host + "]"
    if parts.port is not None:
        host = "%s:%d" % (host, parts.port)
    auth = "%s:%s" % (urllib.parse.unquote(parts.username), urllib.parse.unquote(parts.password or ""))
    return urllib.parse.urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment)), auth


def request_origin(url: str) -> tuple[str, str, int | None]:
    """(scheme, host, port): the scope a credential belongs to."""
    try:
        parts = urllib.parse.urlsplit(url)
        return parts.scheme.lower(), (parts.hostname or "").lower(), parts.port
    except ValueError:
        return "", "", None


def close_quietly(stream: Any) -> None:
    try:
        stream.close()
    except (OSError, ValueError, AttributeError):
        pass


class UnreadBody:
    """What the stdlib's redirect method is handed in place of a 3xx
    response (D-LOGO-15, D-SRC-58): `read` answers nothing and touches
    nothing, `close` closes the real response, anything else is the
    response's own. See unread_redirect_handler."""

    def __init__(self, response: Any) -> None:
        self._response = response

    def read(self, *_: Any) -> bytes:
        return b""

    def close(self) -> None:
        close_quietly(self._response)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._response, name)


def unread_redirect_handler() -> Any:
    """urllib.request.HTTPRedirectHandler with its five redirect methods
    overridden so that a redirect's BODY is never read (D-LOGO-15, D-SRC-58).

    The stdlib's HTTPRedirectHandler.http_error_302 (CPython 3.14,
    urllib/request.py) composes the next request, checks for a loop, and
    then runs `fp.read(); fp.close()` on the 3xx response before following
    it: an unbounded read of whatever body the server attaches, up to
    max_redirections (10) times a fetch, with no byte cap -- MAX_SOURCE_BYTES
    and MAX_LOGO_BYTES apply to the FINAL response only. http_error_301,
    http_error_303, http_error_307 and http_error_308 are the same function,
    bound by name in that class's body (`http_error_301 = http_error_303 =
    ... = http_error_302`), so a subclass that overrides http_error_302
    alone leaves the other four reading; all five are overridden here. Each
    closes the response at once, which drops the connection and whatever
    the server was still sending, and hands the stdlib method an UnreadBody
    in its place, so the stdlib's decisions -- the Location header, the
    scheme check, the loop check, the subclass's redirect_request -- are
    the stdlib's own and only the read is gone. Nothing needs the body: a
    redirect is followed or refused on its headers."""
    import urllib.request

    class UnreadRedirectHandler(urllib.request.HTTPRedirectHandler):
        def http_error_302(self, req: Any, fp: Any, code: int, msg: str, headers: Any) -> Any:
            close_quietly(fp)
            return super().http_error_302(req, UnreadBody(fp), code, msg, headers)

        http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302

    return UnreadRedirectHandler


class FetchExpired(BaseException):
    """Raised by FetchDeadline's alarm. A BaseException so no `except
    OSError` or `except Exception` on the way out of urllib can mistake it
    for a network error or swallow it; the fetch that armed the deadline
    turns it into its own `timeout` refusal."""


class FetchDeadline:
    """`with FetchDeadline(seconds):` -- the whole body runs under ONE
    wall-clock deadline (R30e: D-SRC-58, D-LOGO-16).

    A per-socket timeout bounds each read and each connect, never their sum:
    a server that sends one byte inside every timeout keeps a fetch alive
    for as long as it likes, in the connect, the TLS handshake, the status
    line, the headers (http.client allows 100 lines of 65,536 bytes), any
    redirect, and the body. The deadline the helper had (S-05) was checked
    only between body reads, after `open()` had returned. This arms
    ITIMER_REAL for the budget with a SIGALRM handler that raises
    FetchExpired, so the fetch is interrupted wherever it is waiting:
    CPython retries a socket call interrupted by a signal only after running
    the handler (PEP 475), and the handler's exception ends the call.

    What it cannot cut short: a call that does not return to the
    interpreter until it is done. The one on this path was the host-name
    lookup -- getaddrinfo runs in the C library, which retries its own poll
    after a signal -- so a lookup ended on the system resolver's timeout and
    the handler ran then. MEASURED 2026-10-24 (D-SRC-62,
    scripts/dev-harness/spikes/resolver-overrun, a user namespace whose
    only resolver never answers): with a 0.5 s deadline the `playlist` verb
    answered `timeout` after 1.26-1.28 s under `options timeout:1
    attempts:1` and after 10.29-10.35 s under glibc's defaults, the
    resolver's own 1.04-1.09 s and 10.05-10.06 s plus the helper's start.
    So since that day the lookup is the one thing the fetch runs on a
    thread of its own (resolve_within, through bounded_create_connection on
    every connection the openers make, redirect hops included): the main
    thread waits for it in slices it returns from, the alarm interrupts
    that wait as it interrupts a read, and the worker blocks SIGALRM so the
    signal is delivered to the thread that handles it. Measured the same
    day on the same rig: 0.77-0.84 s under both resolver settings, the
    lookup given up at the deadline and the rest the helper's own start,
    which the before-figures carry too. The address the worker found is the
    one the socket connects to, so the lookup is made once per connection
    and never repeated by the stdlib.

    Only the main thread may install a signal handler. Anywhere else (a test
    calling from a thread) the body runs without the alarm and the read
    loop's own monotonic check is the only bound, as before; the lookup
    there is bounded by the socket timeout alone, as a connect is. A timer
    already armed (none is, on any path that fetches) is put back with what
    remained of it. The helper arms no other timer while a fetch runs, and
    the resolver's worker is the only thread it ever starts; it is a daemon
    thread, so one the deadline abandoned dies with the process."""

    def __init__(self, seconds: float) -> None:
        self.seconds = max(0.001, float(seconds))
        self.armed = False
        self.installed = False
        self.previous: Any = None
        self.prior: tuple[float, float] = (0.0, 0.0)
        self.started = 0.0

    def expire(self, *_: Any) -> None:
        if self.armed:
            self.armed = False
            raise FetchExpired()

    def __enter__(self) -> FetchDeadline:
        try:
            self.previous = signal.signal(signal.SIGALRM, self.expire)
        except (ValueError, OSError, AttributeError):
            return self
        self.installed = True
        self.armed = True
        self.started = time.monotonic()
        self.prior = signal.setitimer(signal.ITIMER_REAL, self.seconds)
        return self

    def __exit__(self, *_: Any) -> bool:
        if not self.installed:
            return False
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
        finally:
            # A SIGALRM already pending when the timer is cancelled runs the
            # handler right here; the caller's `except FetchExpired` sits
            # outside this block and answers it as the timeout it is.
            self.armed = False
            signal.signal(signal.SIGALRM, self.previous if self.previous is not None else signal.SIG_DFL)
            if self.prior[0] > 0:
                left = self.prior[0] - (time.monotonic() - self.started)
                signal.setitimer(signal.ITIMER_REAL, max(left, 0.001), self.prior[1])
        return False


# D-SRC-62: the main thread waits for the resolver's worker in slices of
# this many seconds, so a SIGALRM that the kernel delivered while the wait
# was not interruptible still reaches its handler within one slice.
RESOLVE_WAIT_SLICE_S = 0.05
# The worker's stack. getaddrinfo needs well under this; the default 8 MiB
# would be the largest single anonymous mapping a fetch verb makes under
# limit_memory's RLIMIT_DATA.
RESOLVE_STACK_BYTES = 1024 * 1024


def resolve_within(host: str, port: int, timeout: float) -> list[Any]:
    """getaddrinfo(host, port) for a stream socket, on a daemon thread the
    main thread waits for at most `timeout` seconds (D-SRC-62).

    The wait is a loop of short joins, so it returns to the interpreter
    every RESOLVE_WAIT_SLICE_S and a FetchDeadline alarm ends it there, as
    it ends a read; the worker blocks SIGALRM first, so the kernel hands
    the signal to the main thread, whose wait is interrupted at once. A
    lookup that outlives the wait raises TimeoutError, the error a connect
    that took too long raises, and the caller answers it as one; the worker
    then finishes on the resolver's own clock and is discarded (daemon:
    the process does not wait for it at exit). Nothing is cached here and
    nothing is re-looked-up: the result goes straight to the connect."""
    import socket
    import threading
    result: list[Any] = []

    def lookup() -> None:
        try:
            signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
        except (OSError, ValueError, AttributeError):
            pass
        try:
            result.append(socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM))
        except BaseException as error:         # handed to the main thread whole
            result.append(error)

    previous = threading.stack_size()
    try:
        threading.stack_size(RESOLVE_STACK_BYTES)
    except (ValueError, RuntimeError):
        pass
    try:
        worker = threading.Thread(target=lookup, name="omarchy-iptv-resolve", daemon=True)
        worker.start()
    finally:
        try:
            threading.stack_size(previous)
        except (ValueError, RuntimeError):
            pass
    bound = max(0.0, float(timeout))
    until = time.monotonic() + bound
    while worker.is_alive():
        left = until - time.monotonic()
        if left <= 0:
            break
        worker.join(min(RESOLVE_WAIT_SLICE_S, left))
    if not result:
        raise TimeoutError("the host-name lookup took longer than %.1f s" % bound)
    found = result[0]
    if isinstance(found, BaseException):
        raise found
    return found


def bounded_create_connection(address: tuple[str, int], timeout: Any = None,
                              source_address: Any = None, **_: Any) -> Any:
    """socket.create_connection with its lookup under resolve_within, the
    same signature, the same first-address-that-connects loop (D-SRC-62).
    Installed as every connection's `_create_connection` by
    bounded_handlers, which is the one place http.client turns a host name
    into a socket, so a redirect hop gets the same bound as the first hop.
    `timeout` that is not a number (the stdlib's default sentinel) is
    bounded by DEFAULT_TIMEOUT rather than left open."""
    import socket
    host, port = address
    bound = float(timeout) if isinstance(timeout, (int, float)) and not isinstance(timeout, bool) else float(DEFAULT_TIMEOUT)
    error: OSError | None = None
    for family, kind, proto, _, sockaddr in resolve_within(host, port, bound):
        sock = None
        try:
            sock = socket.socket(family, kind, proto)
            if isinstance(timeout, (int, float)) and not isinstance(timeout, bool):
                sock.settimeout(timeout)
            if source_address:
                sock.bind(source_address)
            sock.connect(sockaddr)
            return sock
        except OSError as failure:
            error = failure
            if sock is not None:
                sock.close()
    if error is not None:
        raise error
    raise OSError("getaddrinfo returned an empty list")


def bounded_handlers(context: Any) -> list[Any]:
    """The HTTP and HTTPS handlers every opener of this helper is built
    with: the stdlib's, opening the stdlib's connection classes with their
    `_create_connection` replaced by bounded_create_connection (D-SRC-62).
    build_opener drops its own HTTPHandler and HTTPSHandler for these, as
    it does for any subclass it is handed. `context` None gives the HTTPS
    handler the stdlib's default context, as before."""
    import http.client
    import urllib.request

    class BoundedHTTPConnection(http.client.HTTPConnection):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._create_connection = bounded_create_connection

    class BoundedHTTPSConnection(http.client.HTTPSConnection):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._create_connection = bounded_create_connection

    class BoundedHTTPHandler(urllib.request.HTTPHandler):
        def http_open(self, req: Any) -> Any:
            return self.do_open(BoundedHTTPConnection, req)

    class BoundedHTTPSHandler(urllib.request.HTTPSHandler):
        def https_open(self, req: Any) -> Any:
            return self.do_open(BoundedHTTPSConnection, req, context=self._context)

    return [BoundedHTTPHandler(), BoundedHTTPSHandler(context=context)]


# D-SRC-59: the most of a library error's text a network refusal carries.
# For http.client.BadStatusLine (a server whose first line is not a status
# line) and UnknownProtocol (one whose first word is not a known HTTP
# version), str(error) is the provider's own first line, read with
# readline(_MAXLINE + 1): up to 65,536 characters, which reached the
# playlist, probe and guide replies, both status files and the stderr line.
# Redacted FIRST and cut after, so a cut can never leave the userinfo of a
# URL that the redaction would have removed; control characters are folded
# to spaces (a raw line carries its CR LF, and a C0 character escapes to six
# bytes of JSON). The status line is decoded ISO-8859-1, so every character
# left is at most two bytes of UTF-8 and the detail at most
# (200 + 3) x 2 = 406 bytes of a reply.
NETWORK_DETAIL_MAX = 200


def network_detail(error: Any) -> str:
    text = redact_urls(error)
    if len(text) > NETWORK_DETAIL_MAX:
        text = text[:NETWORK_DETAIL_MAX].rstrip() + "..."
    return _CONTROL_CHARS.sub(" ", text).strip()


def make_opener(label: str, host: str) -> Any:
    """urlopen replacement whose redirect handler (S-06) refuses non-http(s)
    targets (urllib's default happily follows a 302 to ftp://) and drops
    Authorization / Cookie when the origin (scheme, host, port) changes, so
    a provider that bounces to a third party never receives the user's
    credentials. urllib itself refuses file:/data: targets and loops with a
    3xx HTTPError, which read_http_source maps to the same error code. A
    redirect's body is never read (unread_redirect_handler)."""
    import urllib.request

    class SafeRedirectHandler(unread_redirect_handler()):
        def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Any:
            scheme = stream_scheme(newurl)
            if scheme not in ("http", "https"):
                try:
                    fp.close()
                except OSError:
                    pass
                raise HelperError("unsafe_redirect", "%s from %s redirected to an unsupported scheme '%s'" % (label, host, scheme or "none"))
            new = super().redirect_request(req, fp, code, msg, headers, newurl)
            if new is not None and request_origin(newurl) != request_origin(req.full_url):
                for name in ("Authorization", "Cookie"):
                    new.remove_header(name)
            return new

    # D-SRC-62: the connections are the stdlib's with the host-name lookup
    # bounded; the TLS context is the one limit_memory prepared, or the
    # stdlib's default when none was.
    handlers: list[Any] = [SafeRedirectHandler(), *bounded_handlers(TLS_CONTEXT.get("https"))]
    return urllib.request.build_opener(*handlers)


def http_deadline(timeout: float) -> float:
    """Wall-clock budget in seconds for one download (see HTTP_DEADLINE_MIN).
    HTTP_DEADLINE_ENV can only LOWER it, like MEMORY_LIMIT_ENV: it used to
    take any figure over 0.05, so the variable that exists for tests could
    lift the bound the README states."""
    budget = max(HTTP_DEADLINE_MIN, 3.0 * float(timeout))
    override = os.environ.get(HTTP_DEADLINE_ENV, "")
    if override:
        try:
            wanted = float(override)
        except ValueError:
            return budget
        if wanted == wanted:              # not NaN
            return min(budget, max(0.05, wanted))
    return budget


# What limit_memory set in this process (see there). A dict changed in
# place, so no part needs a `global` statement.
MEMORY_HELD: dict[str, Any] = {"limit": 0, "previous": None}


def memory_limit_bytes() -> int:
    """The data limit a fetch verb sets (D-M3U-1): MEMORY_LIMIT_MIB,
    or a LOWER figure from MEMORY_LIMIT_ENV, in whole MiB. A higher one, or
    anything but one to seven digits, is ignored, so the variable can only
    tighten the limit."""
    limit = MEMORY_LIMIT_MIB * 1024 * 1024
    override = os.environ.get(MEMORY_LIMIT_ENV, "").strip()
    if re.fullmatch(r"[0-9]{1,7}", override):
        wanted = int(override) * 1024 * 1024
        if 0 < wanted < limit:
            limit = wanted
    return limit


# Every module a fetch verb imports lazily on its way through, imported
# BEFORE the limit is set (limit_memory): a module loaded under the limit
# maps its shared object there, and a refused mapping is an ImportError
# from somewhere deep in urllib, not the MemoryError the verb answers.
# Measured, not supposed: under a 16 MiB ADDRESS-SPACE limit set before
# these (RLIMIT_AS, the first version), the playlist verb ended in
# "ImportError: ... binascii ...: failed to map segment from shared object"
# and the epg verb in "No module named expat". RLIMIT_DATA does not count
# a library's text, so this matters less under it; it still counts the
# library's writable pages, and the preload keeps imports out of the
# question either way.
# The names are the lazy `import` lines of 01- to 04- and 11-cli.py's
# traceback, plus what urllib loads on a request: `ssl` (http.client), and
# `encodings.idna` (socket encodes every host name through it).
FETCH_PRELOAD = ("base64", "binascii", "http.client", "ssl", "urllib.error", "urllib.request",
                 "encodings.idna", "unicodedata", "traceback")
EPG_PRELOAD = FETCH_PRELOAD + ("calendar", "hashlib", "xml.etree.ElementTree", "xml.parsers.expat")


def quiet_unraisable(unraisable: Any) -> None:
    """sys.unraisablehook while a fetch verb runs bounded (D-M3U-1). A
    MemoryError inside urllib can leave a half-built HTTPResponse whose
    finalizer then fails, and CPython's own hook prints that as a traceback
    on stderr -- seen under a 16 MiB limit. This keeps the verb's promise of
    one sentence and no traceback: one line naming the two types, never the
    object's repr or the exception's text, either of which can quote a URL."""
    log("ignored %s while releasing %s" % (type(unraisable.exc_value).__name__,
                                           type(unraisable.object).__name__ if unraisable.object is not None else "an object"))


# The TLS context urllib would build for this run's opener, built instead
# by limit_memory before the limit is set (D-M3U-1). urllib makes one per
# opener -- loading the system's CA store -- and OpenSSL reports an
# allocation it was refused as an SSLError ("No cipher can be selected"),
# not a MemoryError: seen under an 8 MiB test limit. It is the SAME
# context, from the same function urllib.request.HTTPSHandler calls when
# it is given none (http.client._create_https_context), so certificate
# verification, the ALPN and the post-handshake setting are exactly
# urllib's; when that function is missing the opener builds its own, as
# before. Empty until a fetch verb runs as the program.
TLS_CONTEXT: dict[str, Any] = {}


def prepare_tls_context() -> None:
    try:
        import http.client
        create = getattr(http.client, "_create_https_context", None)
        if create is not None:
            TLS_CONTEXT["https"] = create(http.client.HTTPSConnection._http_vsn)
    except (ImportError, AttributeError, OSError, ValueError):
        TLS_CONTEXT.pop("https", None)


def limit_memory(preload: tuple[str, ...] = FETCH_PRELOAD) -> dict[str, Any]:
    """Hold this process to memory_limit_bytes() of data, before a fetch
    verb downloads or parses anything (D-M3U-1), once `preload` is loaded.

    RLIMIT_DATA, not RLIMIT_AS, measured on this machine with CPython 3.14
    (2026-10-20). Over a parse, both end in a plain MemoryError the verb
    catches, each within a few MiB of the run's peak VmData or VmSize (the
    two differ by the libraries' text, about 14 MiB). What decided it is
    everything that is not the parse: AS counts every FILE mapping too, so a
    shared library the run maps after the limit is refused under AS and
    fails as something other than memory -- measured for an extension
    module (the import error above); an NSS module that getaddrinfo
    dlopens to resolve the provider's host is the same mapping and would
    read as a network failure (not measured). DATA
    counts the private writable memory, which is every Python object, the
    heap and every anonymous mapping CPython makes, and leaves out read-only
    and executable file mappings, which are bounded by the files. An
    existing soft limit that is already tighter (a user's own `ulimit -d`)
    is kept. -> {"limit": the bytes the run is held to (0 when unbounded),
    "previous": the (soft, hard) pair it replaced, for release_memory_limit,
    or None when nothing changed}. Best effort: where the module or the call
    is unavailable the verb runs unbounded, as before, and says so on stderr.

    Only when this file is the program. A test that loads the helper as a
    module and calls a verb in its own process would otherwise hold its
    whole test runner to the limit for the rest of the run, so there the
    verb runs unbounded and the limit is observed by running the helper as
    a subprocess, the way the service does (the D-M3U-1 tests, dev branch).

    The record is also kept in MEMORY_HELD, which main() reads when a
    MemoryError escapes a verb anyway, to lift the limit before it speaks."""
    MEMORY_HELD.clear()
    MEMORY_HELD.update({"limit": 0, "previous": None})
    if __name__ != "__main__":
        return MEMORY_HELD
    sys.unraisablehook = quiet_unraisable
    try:
        import importlib
        import resource
        for name in preload:
            try:
                importlib.import_module(name)
            except ImportError:
                pass            # the verb meets the same absence unbounded
        prepare_tls_context()
        limit = memory_limit_bytes()
        soft, hard = resource.getrlimit(resource.RLIMIT_DATA)
        if hard != resource.RLIM_INFINITY and hard < limit:
            limit = hard
        if soft != resource.RLIM_INFINITY and soft <= limit:
            MEMORY_HELD["limit"] = soft
            return MEMORY_HELD
        resource.setrlimit(resource.RLIMIT_DATA, (limit, hard))
        MEMORY_HELD.update({"limit": limit, "previous": (soft, hard)})
    except (ImportError, ValueError, OSError) as error:
        log("could not set a memory limit (%s); this run is not bounded" % type(error).__name__)
    return MEMORY_HELD


def release_memory_limit(held: dict[str, Any]) -> None:
    """Put back the limit limit_memory replaced, so a refusal can be written
    however close to the limit the run stopped (the verb exits right after)."""
    previous = held.get("previous")
    if previous is None:
        return
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_DATA, previous)
    except (ImportError, ValueError, OSError):
        pass


def memory_refusal(label: str, host: str, held: dict[str, Any]) -> HelperError:
    """The one sentence a run that hit the limit ends with. The host only,
    never the URL; `too_large`, so the guide reads it as `Source too large`.
    Called after the run's own objects are released and the limit lifted
    (release_memory_limit), which is what leaves room to compose it."""
    limit = int(held.get("limit") or 0)
    bound = "the %d MiB of memory this helper allows itself" % (limit // (1024 * 1024)) if limit else "the memory available"
    return HelperError("too_large", "%s from %s needs more than %s" % (label, host or "the source", bound))


def download_timeout(label: str, host: str) -> HelperError:
    # No seconds in the message: the guide renders the code as "Timed out"
    # and the README states the deadline, so a number here could only
    # disagree with them (D-LIVE-11).
    return HelperError("timeout", "%s download from %s exceeded its deadline" % (label, host))


def read_http_source(url: str, timeout: float, label: str = "playlist") -> bytes:
    """The playlist's, the guide's and the source probe's one download, under
    ONE wall-clock deadline of http_deadline(timeout) seconds from before
    the connection is opened to the last byte, redirects included (R30e,
    D-SRC-58): FetchDeadline interrupts the connect, the TLS handshake, the
    headers and the body wherever they wait, and the monotonic check in the
    read loop -- and once more after it, for the chunked trailers http.client
    reads inside the last read1 -- stays for a caller off the main thread.
    No redirect body is read (make_opener)."""
    import urllib.request
    host = source_host(url)
    target, auth = split_userinfo(url)
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if auth:
        import base64
        headers["Authorization"] = "Basic " + base64.b64encode(auth.encode("utf-8")).decode("ascii")
    request = urllib.request.Request(target, headers=headers)
    opener = make_opener(label, host)
    budget = http_deadline(timeout)
    deadline = time.monotonic() + budget
    try:
        with FetchDeadline(budget):
            return read_http_response(opener, request, timeout, label, host, deadline)
    except FetchExpired:
        raise download_timeout(label, host) from None


def read_http_response(opener: Any, request: Any, timeout: float, label: str, host: str, deadline: float) -> bytes:
    import http.client
    import urllib.error
    chunks: list[bytes] = []
    total = 0
    try:
        with opener.open(request, timeout=timeout) as response:
            # read1: at most one socket read per call, so a trickling server
            # cannot park us inside read() past the deadline check.
            while total <= MAX_SOURCE_BYTES:
                if time.monotonic() >= deadline:
                    raise download_timeout(label, host)
                chunk = response.read1(HTTP_CHUNK)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
        if time.monotonic() >= deadline:
            # The last read1 of a chunked body reads the trailer lines
            # inside itself; a download that ran past its deadline there is
            # refused, not accepted (the time-and-disk review, 2026-10-21).
            raise download_timeout(label, host)
    except HelperError:
        raise
    except urllib.error.HTTPError as error:
        if 300 <= error.code < 400:
            # urllib refused the redirect itself (file:, data:, a loop); its
            # message carries the target URL, so it is not repeated here.
            raise HelperError("unsafe_redirect", "%s redirect from %s not followed" % (label, host))
        raise HelperError("http_%d" % error.code, "HTTP %d from %s" % (error.code, host))
    except urllib.error.URLError as error:
        reason = getattr(error, "reason", error)
        raise HelperError("network", "could not reach %s: %s" % (host, network_detail(reason)))
    except (TimeoutError, OSError, ValueError, http.client.HTTPException) as error:
        raise HelperError("network", "could not reach %s: %s" % (host, network_detail(error)))
    if total > MAX_SOURCE_BYTES:
        raise HelperError("too_large", "%s from %s exceeds %d MB" % (label, host, MAX_SOURCE_BYTES // (1024 * 1024)))
    return b"".join(chunks)


def fetch_bytes(url: str, timeout: float, label: str = "playlist") -> bytes:
    kind, target = resolve_source(url, label)
    if kind == "file":
        return read_local_source(target, label)
    return read_http_source(target, timeout, label)


def too_large_inflated(label: str) -> HelperError:
    return HelperError("too_large", "decompressed %s exceeds %d MB" % (label, MAX_SOURCE_BYTES // (1024 * 1024)))


def decode_text(data: bytes, label: str = "playlist") -> str:
    """UTF-8 text; gzip (by magic bytes) is inflated with the same 64 MB cap
    as the download so a gzip bomb cannot exhaust memory (D-QA-06)."""
    return inflate_source(data, label).decode("utf-8", errors="replace")


def playlist_lines(data: bytes, label: str = "playlist") -> Any:
    """The source's lines, decoded one at a time, each with its line break.

    D-M3U-1. decode_text's one str is what parse_m3u used to walk, and a str
    is stored at the width of its widest character: a 64 MiB playlist with a
    flag emoji in one name in ten (a common provider habit) became a 256 MiB
    str, and its split another copy, which put the verb at 474 MiB of a
    512 MiB limit. Line by line, the text never exists whole. The result is
    identical: a line break is ASCII and can sit inside no UTF-8 sequence,
    so the decoder starts every line fresh either way, and errors="replace"
    replaces exactly what decoding the whole would have."""
    for raw in io.BytesIO(inflate_source(data, label)):
        yield raw.decode("utf-8", errors="replace")


def inflate_source(data: bytes, label: str = "playlist") -> bytes:
    """`data`, gunzipped when it is gzip (by magic bytes), under the cap."""
    if data[:2] == b"\x1f\x8b":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as stream:
                data = read_capped(stream, MAX_SOURCE_BYTES)
        except (OSError, EOFError, zlib.error) as error:
            raise HelperError("bad_gzip", "could not decompress %s: %s" % (label, error))
        if len(data) > MAX_SOURCE_BYTES:
            raise too_large_inflated(label)
    return data


class CappedReader:
    """Binary stream wrapper that refuses to hand out more than `limit` bytes
    in total (the inflated-size cap for streamed gzip, D-QA-06)."""

    def __init__(self, stream: Any, limit: int, label: str) -> None:
        self.stream = stream
        self.limit = limit
        self.label = label
        self.total = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self.stream.read(size)
        self.total += len(chunk)
        if self.total > self.limit:
            raise too_large_inflated(self.label)
        return chunk

    def close(self) -> None:
        self.stream.close()


class EntityRefusingReader:
    """D-EPG-6 (the maintainer on #11892): ElementTree expands the entities a
    feed declares in its internal subset, and MAX_SOURCE_BYTES bounds only the
    input. XMLTV declares none (a DOCTYPE naming xmltv.dtd WITHOUT a subset is
    common, and passes), so the first read runs the prolog through its own
    expat parser, whose EntityDeclHandler refuses general and parameter
    entities alike, and hands the parse nothing until that parser reaches the
    root's start tag: a declaration can only come before it."""

    class Root(Exception):
        pass

    def __init__(self, stream: Any) -> None:
        self.stream = stream
        self.cleared = False

    def read(self, size: int = -1) -> bytes:
        if self.cleared:
            return self.stream.read(size)
        import xml.parsers.expat

        def declared(*_: Any) -> None:
            raise HelperError("bad_xml", "refused the EPG: it declares an XML entity, which XMLTV feeds never do")

        def root(*_: Any) -> None:
            raise EntityRefusingReader.Root()

        parser = xml.parsers.expat.ParserCreate()
        parser.EntityDeclHandler = declared
        parser.StartElementHandler = root
        held = []
        chunk = b"-"
        while chunk:
            chunk = self.stream.read(size)
            held.append(chunk)
            try:
                parser.Parse(chunk, not chunk)
            except EntityRefusingReader.Root:
                break
            except xml.parsers.expat.ExpatError as error:
                raise HelperError("bad_xml", "could not parse EPG XML: %s" % error)
        self.cleared = True
        return b"".join(held)


def open_xml_stream(data: bytes) -> Any:
    """Bytes -> readable stream; gzip is detected by magic bytes, not by name."""
    if data[:2] == b"\x1f\x8b":
        return CappedReader(gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb"), MAX_SOURCE_BYTES, "EPG")
    return io.BytesIO(data)


# D-SRC-60. The atomic writers' `except BaseException` removes their
# temporary on every exit Python sees, and a SIGTERM is not one: the default
# disposition ends the process inside the write, and the service sends it
# from the playlist, guide and probe watchdogs, from a probe's cancel and
# from the logo fetch's stop (a source switch, the setting turned off, its
# watchdog). Each such kill can leave one `.tmp-<name>-<8 hex>` beside its
# target, no larger than the target, 0600 in a 0700 folder, and nothing
# swept one in a kept or active source's folder, its logos/ or the state
# folder. So the first atomic write a process makes into a folder first
# removes the leftovers there (sweep_stale_temps).
#
# Which ones: exactly the names these two writers make -- `.tmp-`, a name,
# `-`, eight lowercase hex digits -- that are regular files (never followed),
# owned by this user, and last modified at least STALE_TEMP_AGE ago. A
# writer owns its temporary from the O_EXCL create to the rename, and both
# writers write it in one call and rename it straight after, so a temporary
# a live writer holds was modified moments ago; a day is about 23 times the
# longest watchdog in the service (the logo fetch's, LOGO_RUN_DEADLINE plus
# margins, 3,690 s) and 480 times the playlist's. The one writer this could
# wrong is a process stopped (SIGSTOP, a hung filesystem) inside a write for
# a day, whose rename then fails as an OSError the caller already answers.
# In a folder that is not the plugin's (`private_dir` False: the target of a
# state.json link) only the target's OWN leftovers are swept, never another
# name's. Once per folder per process, so the logo fetch's thousands of
# writes into one folder list it once.
STALE_TEMP_AGE = 86400
_TEMP_SUFFIX = re.compile(r"-[0-9a-f]{8}\Z")
SWEPT_TEMP_DIRS: set[tuple[str, str]] = set()


def is_stale_temp_name(name: str, target: str = "") -> bool:
    """Is `name` one the atomic writers make (for `target`, when given)?"""
    prefix = TEMP_PREFIX + target + "-" if target else TEMP_PREFIX
    if not name.startswith(prefix) or not _TEMP_SUFFIX.search(name):
        return False
    return len(name) == len(prefix) + 8 if target else len(name) > len(prefix) + 9


def sweep_stale_temps(directory: str, target: str = "", now: float | None = None) -> int:
    """Remove the stale temporaries in `directory` (all of them, or `target`'s
    only); -> how many. Never raises: a leftover is not worth a refusal."""
    now = time.time() if now is None else now
    removed = 0
    uid = os.geteuid()
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if not is_stale_temp_name(entry.name, target):
                    continue
                try:
                    st = entry.stat(follow_symlinks=False)
                    if (stat.S_ISREG(st.st_mode) and st.st_uid == uid
                            and now - st.st_mtime >= STALE_TEMP_AGE):
                        os.unlink(entry.path)
                        removed += 1
                except OSError:
                    continue
    except OSError:
        return removed
    return removed


def sweep_stale_temps_once(directory: str, target: str = "") -> int:
    key = (os.path.abspath(directory), target)
    if key in SWEPT_TEMP_DIRS:
        return 0
    SWEPT_TEMP_DIRS.add(key)
    return sweep_stale_temps(directory, target)


def write_text_atomic(path: str, text: str, private_dir: bool = True) -> None:
    """Temp file in the same (0700) directory, mode 0600, rename over `path`.

    `private_dir` False (R24b, round 14): the directory is not the plugin's
    -- the target of a state.json symlink, a dotfiles folder -- so it is
    neither created nor chmod-ed; the temporary file is still 0600 and
    O_EXCL, and the rename still replaces `path` atomically. Leftovers of a
    killed write are swept first (D-SRC-60, above)."""
    directory = os.path.dirname(path)
    if private_dir:
        ensure_private_dir(directory)
    sweep_stale_temps_once(directory, "" if private_dir else os.path.basename(path))
    tmp = os.path.join(directory, ".tmp-%s-%s" % (os.path.basename(path), os.urandom(4).hex()))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            os.fchmod(handle.fileno(), 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_bytes_atomic(path: str, data: bytes) -> None:
    """The binary sibling of write_text_atomic, same 0700 / 0600 discipline.

    Added for logos (M2-04), which are the first non-text thing this helper
    writes into the cache.
    """
    directory = os.path.dirname(path)
    ensure_private_dir(directory)
    sweep_stale_temps_once(directory)
    tmp = os.path.join(directory, ".tmp-%s-%s" % (os.path.basename(path), os.urandom(4).hex()))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            os.fchmod(handle.fileno(), 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_json_atomic(path: str, payload: Any, private_dir: bool = True) -> None:
    # json.dumps (one-shot C encoder) is several times faster than json.dump.
    write_text_atomic(path, json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", private_dir)


def json_string(text: str) -> str:
    """JSON string literal; the common quote-free case skips the encoder."""
    if '"' in text or "\\" in text:
        return json.dumps(text, ensure_ascii=False)
    return '"' + text + '"'


# D-SINK-19 round 13, R23b, rule 15: every open() in this helper of a path
# a user or another program can replace, and its verdict (2026-10-13).
#   Routed through open_regular (never blocks; a regular file or a symlink to
#   one, decided by fstat on the descriptor):
#     state.json -- `state init`, every other `state` verb (read_state_strict)
#       and the D-ID-1 remap (remap_state_file, via read_json);
#     every cache JSON read by read_json -- channels.json, failed.json,
#       playlist-status.json, epg-status.json, the logo and EPG indexes;
#     the EPG window cache (load_window); a cached logo (_read_logo_prefix);
#     the player lock record (read_lock_file); a local playlist or EPG file
#       (read_local_source), whose isfile check a swap could outrun.
#   Left as they are, with why:
#     the player lock's O_CREAT|O_RDWR open (acquire_lock): O_RDWR on
#       a FIFO does not block on Linux, and its fchmod is gated on S_ISREG;
#     the host config shield's open of shell.json: already O_NONBLOCK, and
#       refused by fstat unless a regular file the euid owns;
#     the cache walk's directory opens: O_DIRECTORY fails at once on
#       anything that is not a directory;
#     the atomic writers' temporary files: created by this process with
#       O_EXCL in a 0700 directory, never an existing path;
#     manifest.json in the plugin directory (nothing writes there at
#       runtime, rule 4), /proc/<pid>/*, os.devnull.
class NotRegularFile(OSError):
    """Something other than a regular file (or a symlink to one) where one
    is read. An OSError, so every tolerant reader that already answers None
    for a file it cannot read answers None for this too."""


def open_regular(path: str) -> int:
    """Open `path` for reading WITHOUT ever blocking, and only when it is a
    regular file or a symlink to one. -> a descriptor the caller closes.

    D-SINK-19 round 13, R23b. A plain open() of a FIFO blocks until a writer
    appears: with a FIFO at state.json, `state init`, `show` and `favorite
    add` each sat in open() until killed, the service waited on that init
    forever, and every start left an orphaned helper behind (the round-12
    lenses, measured; the shipped 0.13.6 the same). So: O_NONBLOCK (a FIFO
    opens at once with no writer), O_NOCTTY (a terminal at the path never
    becomes ours), and the decision is an fstat of the descriptor that WAS
    opened -- never an lstat of the name before it, which a rename in
    between would make a statement about another file. A socket cannot be
    opened at all (ENXIO) and is reported the same way. O_NONBLOCK changes
    nothing about reads from a regular file. The rule-15 list of the reads
    routed here, and of those left as they are, is the comment above."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY | os.O_CLOEXEC)
    except OSError as error:
        if error.errno == errno.ENXIO:
            raise NotRegularFile(errno.ENXIO, "not a regular file", path) from None
        raise
    try:
        mode = os.fstat(fd).st_mode
    except BaseException:
        os.close(fd)
        raise
    if not stat.S_ISREG(mode):
        os.close(fd)
        raise NotRegularFile(errno.EINVAL, "not a regular file", path)
    return fd


def read_regular_text(path: str) -> str:
    with os.fdopen(open_regular(path), "r", encoding="utf-8") as handle:
        return handle.read()


def read_json(path: str) -> Any:
    try:
        return json.loads(read_regular_text(path))
    except (OSError, ValueError):
        return None


def emit(payload: Any) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def error_payload(kind: str, error: HelperError, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "kind": kind,
        "error": {"code": error.code, "message": redact_urls(error.message)},
    }
    payload.update(error.extra)
    payload.update(extra)
    return payload


def write_status_quietly(path: str, status: dict[str, Any]) -> None:
    try:
        write_json_atomic(path, status)
    except OSError as io_error:
        log("could not write %s: %s" % (os.path.basename(path), io_error))


# ------------------------------------------------------------ playlist

def url_from(args: argparse.Namespace) -> str:
    """The source URL of a fetch verb: a non-empty --url, else $OMARCHY_IPTV_URL.

    D-SINK-8. The shell passes the URL in the environment, never on the
    command line: /proc/<pid>/cmdline is world-readable for as long as the
    fetch runs, and /proc/<pid>/environ is refused to everyone but root from
    before this file imports anything but sys (shield_environment, D-SINK-9).
    The playlist and epg verbs download with urllib and start no child process -- this helper does fork
    mpv, but only in `player start`, on a Process the service never hands
    this variable -- so nothing inherits it. --url stays for a human at their
    own shell, whose argv is their own; an EMPTY --url is treated as absent.
    The value is read once, here, and the URL's host is the only part of it
    that ever reaches a message (source_host); a LOCAL file's base name is
    printed on purpose (D12, read_local_source) and carries no credential;
    log() redacts whatever is left.
    """
    explicit = (getattr(args, "url", None) or "").strip()
    if explicit:
        return explicit
    return (os.environ.get(URL_ENV) or "").strip()


def cmd_playlist(args: argparse.Namespace) -> int:
    directory = cache_dir(args.cache_dir)
    channels_path = os.path.join(directory, CHANNELS_FILE)
    status_path = os.path.join(directory, PLAYLIST_STATUS_FILE)
    previous = read_json(status_path) or {}
    url = url_from(args)
    started = time.monotonic()
    text = parsed = document = None
    error: HelperError | None = None
    now = 0
    # D-M3U-1: bounded before anything is fetched or parsed. The refresh
    # and the source probe are both this verb.
    held = limit_memory()
    try:
        try:
            if not url:
                # A status the service can switch on, not an argparse usage exit:
                # the verb has no required argument any more, because the shell
                # never passes one.
                raise HelperError("bad_url", "no playlist URL: pass --url or set $%s" % URL_ENV)
            text = fetch_bytes(url, args.timeout, "playlist")
            parsed = parse_m3u(playlist_lines(text))
            text = None
            if not parsed["channels"]:
                if not parsed["isPlaylist"]:
                    raise HelperError("not_a_playlist", "source from %s is not an M3U playlist (no #EXTM3U or #EXTINF lines)" % source_host(url))
                raise HelperError("empty_playlist", "no playable channels found in playlist from %s" % source_host(url))
            now = int(time.time())
            document = {
                "version": 1,
                "generatedAt": now,
                "sourceHost": source_host(url),
                "epgUrlHint": parsed["epgUrlHint"],
                "count": len(parsed["channels"]),
                "channels": parsed["channels"],
            }
            write_json_atomic(channels_path, document)
            document = None
        finally:
            # D-M3U-3: the limit covers the fetch, the parse and channels.json
            # and NOTHING after them. Lifted here, on every way out of the
            # block -- success, a refusal, the memory refusal, a bug -- so no
            # status is composed, written or printed under it. It used to be
            # lifted on MemoryError alone, so a refusal raised near the limit
            # wrote its status under it and, when that write ran out, reached
            # main()'s fallback with no status file rewritten.
            release_memory_limit(held)
    except HelperError as caught:
        error = caught
    except MemoryError:
        # D-M3U-1. Release before speaking: the text, the channel list and
        # the document are dropped here and the frames the traceback held go
        # with this clause (the limit is already lifted, above). Nothing was
        # half-written: write_json_atomic composes the document before it
        # opens the temporary file, and removes the file when a write fails,
        # so channels.json is the previous run's or absent.
        text = parsed = document = None
        error = memory_refusal("playlist", source_host(url) if url else "", held)
    if error is None:
        assert parsed is not None
        groups = {channel["group"] for channel in parsed["channels"]}
        status = {
            "ok": True,
            "kind": "playlist",
            "sourceHost": source_host(url),
            "fetchedAt": now,
            "durationMs": int((time.monotonic() - started) * 1000),
            "channelCount": len(parsed["channels"]),
            "groupCount": len(groups),
            "warnings": parsed["warnings"],
            "stale": False,
            "error": None,
        }
        write_json_atomic(status_path, status)
        # The upgrade path of ARCHITECTURE.md decision 6. A state file written
        # under id scheme 1 still names its favorites by a hash of the
        # credentialed stream URL, and this is the one place the helper holds
        # both that state and the channel list needed to move them. It writes
        # at most once per state file and never fails the fetch: a playlist
        # that parsed is a success whatever the state file turns out to be.
        #
        # `--state-dir` is REQUIRED, with no default of any kind. An earlier
        # version resolved it with `state_dir(getattr(args, "state_dir",
        # None))`, so every `playlist` run that did not name a state directory
        # reached into the live one: one `unittest discover` put 124 remap
        # passes over the user's own ~/.local/state/omarchy-iptv/state.json,
        # and `playlist --url ... --cache-dir /tmp/scratch` did the same from
        # a shell. Two callers pass a playlist URL here -- the active source's
        # fetch and the probe that runs while a NEW source is being added --
        # and only the first may move saved references, so the caller has to
        # say which it is. Silence means touch nothing.
        if args.state_dir:
            try:
                moved = remap_state_file(os.path.join(state_dir(args.state_dir), STATE_FILE), parsed["channels"])
                if moved:
                    log("playlist: moved %d saved channel reference(s) onto id scheme %d" % (moved, CHANNEL_ID_SCHEME))
            except OSError as io_error:
                log("playlist: could not update saved channel references (%s)" % type(io_error).__name__)
        emit(status)
        return EXIT_OK
    stale = os.path.isfile(channels_path)
    status = error_payload(
        "playlist", error,
        sourceHost=source_host(url) if url else "",   # no URL is not a "local file"
        fetchedAt=previous.get("fetchedAt") if isinstance(previous, dict) else None,
        stale=stale,
        durationMs=int((time.monotonic() - started) * 1000),
    )
    write_status_quietly(status_path, status)
    log("playlist: %s" % error.message)
    emit(status)
    return EXIT_ERROR


