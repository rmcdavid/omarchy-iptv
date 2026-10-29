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


def load_helper():
    loader = importlib.machinery.SourceFileLoader("omarchy_iptv", str(HELPER))
    spec = importlib.util.spec_from_loader("omarchy_iptv", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
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
