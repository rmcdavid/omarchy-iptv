"""Import bin/omarchy-iptv (no .py suffix) as a module for unit tests, and
point the whole test process at a throwaway HOME before it does.

The redirect is not hygiene, it is the fix for a defect. The helper resolves
its cache, state and runtime directories from $XDG_*, falling back to $HOME,
so a test that invoked a subcommand without naming a directory reached the
user's own files. One `python3 -m unittest discover -s tests` put 130 channel
id remap passes over a state file, 124 of them over the real
~/.local/state/omarchy-iptv/state.json -- the data the suite exists to
protect, rewritten by the suite whenever the map moved anything.

Every test module that touches the helper imports this one, and unittest
imports all of them before it runs any test, so this runs first. What it does
is asserted by tests/test_live_state_guard.py rather than trusted: that module
calls the shipping path resolvers and fails if any of them still answers with
a path under the user's real home.

Since D-SINK-18 the helper can also CHMOD a file -- the host's own
shell.json, which it derives from $HOME as the host does -- so the HOME
redirect is what keeps it off the live file, and that file's mode is
fingerprinted beside its bytes.
"""
import atexit
import hashlib
import importlib.machinery
import importlib.util
import os
import pathlib
import shutil
import stat as stat_module
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER = ROOT / "bin" / "omarchy-iptv"

# The user's real locations, captured BEFORE the redirect. Nothing here is
# ever written; test_live_state_guard.py reads them to prove they were not.
REAL_HOME = pathlib.Path(os.path.expanduser("~")).resolve()
REAL_STATE_FILE = REAL_HOME / ".local" / "state" / "omarchy-iptv" / "state.json"
if "XDG_STATE_HOME" in os.environ:
    REAL_STATE_FILE = pathlib.Path(os.environ["XDG_STATE_HOME"]).resolve() / "omarchy-iptv" / "state.json"

# D-SINK-18 brought a second live file within reach: the HOST's settings file,
# which the suite must leave alone in BOTH its bytes and its MODE. A chmod
# does not move mtime, so a bytes-only fingerprint would miss exactly the
# thing the new verb changes -- captured here as (fingerprint, mode) before
# any test module is imported.
# Always $HOME/.config, never $XDG_CONFIG_HOME: the shield derives the file
# from $HOME because the host does (host_config_path's docstring), so that is
# the file a test could tighten. Following XDG_CONFIG_HOME here guarded a file
# the shield never touches on any machine where the two differ (F-HARNESS-20's
# sibling, found by its lane).
REAL_CONFIG_FILE = REAL_HOME / ".config" / "omarchy" / "shell.json"


def fingerprint_of(path):
    """(size, mtime_ns, sha256) of a file, or None when it does not exist."""
    path = pathlib.Path(path)
    try:
        stat = path.stat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime_ns, digest)


def live_state_fingerprint():
    """The same, for the user's real state file."""
    return fingerprint_of(REAL_STATE_FILE)


def mode_of(path):
    """The permission bits of a file, or None when it does not exist."""
    try:
        return stat_module.S_IMODE(pathlib.Path(path).lstat().st_mode)
    except OSError:
        return None


def live_config_fingerprint():
    """(bytes fingerprint, mode) of the HOST's settings file (D-SINK-18)."""
    return (fingerprint_of(REAL_CONFIG_FILE), mode_of(REAL_CONFIG_FILE))


# What the files looked like before a single test ran.
LIVE_STATE_BEFORE = live_state_fingerprint()
LIVE_CONFIG_BEFORE = live_config_fingerprint()

SANDBOX = pathlib.Path(tempfile.mkdtemp(prefix="omarchy-iptv-test-home-"))
atexit.register(shutil.rmtree, str(SANDBOX), True)


def _sandbox_home():
    """Redirect every directory the helper derives from the environment.

    HOME is redirected as well as the three XDG variables, because
    `os.path.expanduser` is the helper's fallback when an XDG variable is
    unset and because `~` in a CLI argument expands through it too. Each
    target is created 0700, the mode the helper itself uses.
    """
    for name, relative in (("HOME", "home"),
                           ("XDG_CACHE_HOME", "cache"),
                           ("XDG_STATE_HOME", "state"),
                           ("XDG_RUNTIME_DIR", "run"),
                           ("XDG_CONFIG_HOME", "config")):
        target = SANDBOX / relative
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.environ[name] = str(target)


_sandbox_home()


# D-SINK-101 (2026-11-13): the address the suite's stand-in resolver gives
# every name the play-time lookup asks about. Global (address_class), and
# never connected to: no test's player is real.
SUITE_STREAM_ADDRESS = "93.184.216.34"


def suite_stream_resolve(name, port):
    """The suite's stand-in for the helper's play-time lookup
    (stream_resolve): every name answers SUITE_STREAM_ADDRESS.

    Why it exists. Since D-SINK-101 player_target looks a cached channel's
    host NAME up before the player is handed it, and the suite's channels
    name hosts under `.test` and `.example`, which no resolver answers --
    with a real one every play test of every other property would refuse
    with `unchecked_address`, and the suite would ask the network. The
    project never lets a test ask a real resolver, and never one about a
    name that leads to this machine or the LAN.

    Why it is no more forgiving than it has to be (rule 10): it stands in
    for that ONE lookup -- resolve_within, which the fetches use, is not
    touched -- and in the test process only. tests/test_stream_lookup.py
    loads the helper WITHOUT it (load_helper(stream_lookup=None)), states
    every answer it tests, including the refusals, and holds the shipping
    stream_resolve to resolve_within and its bound."""
    import socket
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (SUITE_STREAM_ADDRESS, int(port or 0)))]


def load_helper(stream_lookup=suite_stream_resolve, path=None):
    """The helper at `path` (default: this tree's stub) as a module.

    F-HARNESS-116 (2026-11-16): loaded with `sys.dont_write_bytecode` set,
    so the import writes no `bin/__pycache__/` beside the stub it loads. It
    used to write one into whatever tree it loaded from, and `python3 -I`
    does not stop that: `-I` implies `-E`, which ignores
    PYTHONDONTWRITEBYTECODE. Pointed at the live install, that is the
    2026-09-27 write CLAUDE.md's never-touch list records. The previous
    value is put back, so the rest of the suite is unchanged."""
    loader = importlib.machinery.SourceFileLoader("omarchy_iptv", str(path or HELPER))
    spec = importlib.util.spec_from_loader("omarchy_iptv", loader)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    # D-SINK-101: a tree before the lookup (a --baseline run) has no seam.
    if stream_lookup is not None and hasattr(module, "stream_resolve"):
        module.stream_resolve = stream_lookup
    return module


def loopback_reads_public(helper, address="127.0.0.1"):
    """A test SEAM for D-SINK-40, and the only one: while it is entered, the
    helper's address classifier calls exactly one address -- the one the
    fixture TLS and HTTP servers bind, 127.0.0.1 -- `global`, and hands every
    other value to the real classifier unchanged.

    Why it exists. A logo never reaches a non-global address, on any hop, so
    with the real classifier no logo can be fetched from a server on this
    machine, and this machine has no public server to fetch from. The tests
    that need one are about the logo run's OTHER properties (its ceiling,
    its deadlines, its redirect rules), not about where it may connect.

    Why it is no more forgiving than it has to be (rule 10): it widens ONE
    address and nothing else -- 127.0.0.2, ::1 and the IPv4-mapped
    ::ffff:127.0.0.1 stay loopback under it -- and it lives in the test
    process only, so no shipped code path can reach it. tests/
    test_destinations.py holds it to that, and proves the same fetches are
    refused without it."""
    import unittest.mock
    real = helper.address_class

    def classify(value):
        text = str(value).split("%", 1)[0]
        return "global" if text == address else real(value)
    return unittest.mock.patch.object(helper, "address_class", classify)


class FakeRelay:
    """D-SINK-102: the player's relay for a test whose player is a double --
    the FakeMpv on the socket, a holder process for its identity -- run IN
    the test process on real sockets: a TCP listener on 127.0.0.1 and the
    control socket at the path the helper derives (relay_socket_path).

    Why it exists. Since D-SINK-102 the build gate reads a player as this
    build's only when its relay answers as the player's (player_verdict),
    and every load registers a token with it (relay_register) before any
    line about a channel. With no relay every play would refuse with
    `not_running`, and the suite would test nothing past the gate.

    Why it is no more forgiving than the real relay (rule 10): it IS the
    real relay's code -- the helper's own RelayServer and RelayState, the
    control protocol, the token table, the 407 to a request no load
    registered, the per-token counts -- with nothing stood in for. What
    differs is where it runs. In the test process, so the kernel names the
    test process as the control socket's listener (SO_PEERCRED), and that
    process is the PARENT of every holder process a test starts, as the
    spawn makes the real relay the player's parent: relay_request's
    ancestor check passes for a holder this test started and for nothing
    else. It has no child to reap and never exits on its own; close() stops
    it and removes its socket. A socket no FakeRelay was started for has no
    relay at all, and the helper meets exactly what it meets on a machine
    where the relay is gone.

    A test that sends it a PROXY request states the answers of the relay's
    lookup itself (stream_resolve): under the suite's stand-in every name,
    a literal included, would answer SUITE_STREAM_ADDRESS, a public address
    the relay would then connect to."""

    def __init__(self, helper, sock_path):
        import socket
        import threading
        self.helper = helper
        self.path = helper.relay_socket_path(sock_path)
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        self.proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.proxy.bind(("127.0.0.1", 0))
        self.proxy.listen(64)
        self.port = self.proxy.getsockname()[1]
        try:
            os.unlink(self.path)
        except OSError:
            pass
        self.control = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.control.bind(self.path)
        self.control.listen(4)
        self.state = helper.RelayState(self.port, helper.player_build())
        self.server = helper.RelayServer(self.proxy, self.control, self.state)
        self.thread = threading.Thread(target=self.server.serve, daemon=True)
        self.thread.start()

    def tokens(self):
        """The tokens registered, oldest first."""
        with self.state.lock:
            return [entry.token for entry in self.state.tokens]

    def policies(self):
        """The policy record each registered load carries, oldest first."""
        with self.state.lock:
            return [dict(entry.record) for entry in self.state.tokens]

    def close(self):
        self.server.stop()
        self.thread.join(2)
        for sock in (self.proxy, self.control):
            try:
                sock.close()
            except OSError:
                pass
        self.server.close()
        try:
            os.unlink(self.path)
        except OSError:
            pass
