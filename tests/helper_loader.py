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
"""
import atexit
import hashlib
import importlib.machinery
import importlib.util
import os
import pathlib
import shutil
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
HELPER = ROOT / "bin" / "omarchy-iptv"

# The user's real locations, captured BEFORE the redirect. Nothing here is
# ever written; test_live_state_guard.py reads them to prove they were not.
REAL_HOME = pathlib.Path(os.path.expanduser("~")).resolve()
REAL_STATE_FILE = REAL_HOME / ".local" / "state" / "omarchy-iptv" / "state.json"
if "XDG_STATE_HOME" in os.environ:
    REAL_STATE_FILE = pathlib.Path(os.environ["XDG_STATE_HOME"]).resolve() / "omarchy-iptv" / "state.json"


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


# What the file looked like before a single test ran.
LIVE_STATE_BEFORE = live_state_fingerprint()

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
