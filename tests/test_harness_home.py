"""F-HARNESS-20: every user path the shipped code derives, under the dev
harness's environment, lands inside the harness directory.

The defect. The service runs the helper's `config shield` at every start, and
the helper takes the host's settings file from $HOME (host_config_path(), which
mirrors the host's own shell.qml on purpose and has no override by ruling).
The harness replaced the XDG directories and left HOME real, so every harness
run aimed that chmod at the developer's live ~/.config/omarchy/shell.json. The
fix is in the harness, so this test is about the harness: it builds the
environment the way scripts/dev-harness/run.sh builds it -- run.sh's own
`harness_env` and its own seeding functions, EXTRACTED from the file and run,
the way scripts/qa-lib-test.sh runs `seed_scratch_config` -- and then asks the
SHIPPED code where it would write. Nothing here reimplements a path rule
(rule 12): the helper's own functions are called, the helper's own
`config shield` verb is run as the service runs it, and mpv and Python are
asked for their own user directories.

Nothing real is in reach. The "real home" below is a decoy directory this test
creates, handed to the harness as $HOME with every XDG variable pointing into
it and MPV_HOME / XCOMPOSEFILE aimed at it too -- the shape of this machine's
own session environment, which exports XDG_DATA_HOME and XCOMPOSEFILE into the
home. The decoy holds a 0644 shell.json, so an isolation that fails is SEEN
failing: the shield tightens the decoy. On `dev` at 8c8862f (before this fix)
that is exactly what happens; see the board's F-HARNESS-20 row.

The helper is loaded from THIS TREE's bin/, never from the live install, with
bytecode writing off so the tree gains no __pycache__.

Run: python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN_SH = ROOT / "scripts" / "dev-harness" / "run.sh"
QA_LIB = ROOT / "scripts" / "qa-lib.sh"
HELPER = ROOT / "bin" / "omarchy-iptv"
SCENARIOS = ROOT / "scripts" / "dev-harness"

SEED_BODY = '{"version":1,"bar":{"layout":{"right":[{"id":"io.github.rmcdavid.iptv"}]}}}\n'
COLORS = 'foreground = "#123456"\nbackground = "#654321"\naccent = "#abcdef"\n'
SHELL_TOML = '[bar]\nbackground = "accent"\n'

# The harness side, in bash. It sources qa-lib.sh, pulls `harness_env` and
# every `seed_scratch_*` function out of run.sh as text and evaluates them --
# so a revert of run.sh is a revert of what runs here -- calls them in the
# order run.sh's `start` does, and then hands over to the probe. A seed that
# dies is reported, not fatal: a tree whose seed cannot run must still show
# where its shield would have gone.
DRIVER = r'''
set -u
die() { printf 'die: %s\n' "$*" >&2; exit 97; }
QA_LIB=$1 RUN_SH=$2 SCRATCH=$3 REAL_RUNTIME=$4 PROBE=$5
. "$QA_LIB"
eval "$(sed -n '/^harness_env() {/,/^}/p' "$RUN_SH")"
eval "$(sed -n '/^seed_scratch_[a-z_]*() {/,/^}/p' "$RUN_SH")"
declare -F harness_env >/dev/null || { echo "run.sh defines no harness_env" >&2; exit 96; }
harness_env
mkdir -p "$SCRATCH/home" && chmod 0700 "$SCRATCH/home"
for f in $(declare -F | awk '$3 ~ /^seed_scratch_/ { print $3 }'); do
  ( "$f" ) >/dev/null 2>&1 || echo "seed $f failed" >&2
done
exec python3 -I "$PROBE"
'''

# The shipped side, in Python, run under the environment the driver built.
PROBE = r'''
import importlib.machinery, importlib.util, json, os, re, shutil, subprocess, sys
sys.dont_write_bytecode = True
helper_path = os.environ["FH20_HELPER"]
loader = importlib.machinery.SourceFileLoader("omarchy_iptv_fh20", helper_path)
spec = importlib.util.spec_from_loader("omarchy_iptv_fh20", loader)
h = importlib.util.module_from_spec(spec)
loader.exec_module(h)
out = {"env": {k: os.environ.get(k) for k in (
    "HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
    "XDG_STATE_HOME", "XDG_RUNTIME_DIR", "MPV_HOME", "XCOMPOSEFILE")}}
sock = h.default_socket_path()
out["helper"] = {
    "host_config_path": h.host_config_path(),
    "home_dir": h.home_dir(),
    "cache_dir": h.cache_dir(),
    "state_dir": h.state_dir(),
    "runtime_dir": h.runtime_dir(),
    "default_socket_path": sock,
    "config_home": h.config_home(),
}
for k, v in h.player_dirs(sock).items():
    out["helper"]["player_dirs." + k] = v
# The verb, the way the service runs it (Model.configShieldArgv).
r = subprocess.run(["python3", helper_path, "config", "shield"],
                   capture_output=True, text=True, timeout=30)
try:
    out["shield"] = json.loads(r.stdout.strip().splitlines()[-1])
except Exception:
    out["shield"] = {"unreadable": r.stdout[-300:], "rc": r.returncode}
# Python's own user directory (the helper's interpreter would load a user
# site from here, and -I above is only this probe's choice).
r = subprocess.run(["python3", "-c", "import site; print(site.getuserbase())"],
                   capture_output=True, text=True, timeout=30)
out["python_userbase"] = r.stdout.strip()
# mpv, asked rather than reasoned about: at debug level it names the
# directories it resolved its config from.
out["mpv"] = None
if shutil.which("mpv"):
    r = subprocess.run(["mpv", "--idle=no", "--msg-level=global=debug"],
                       capture_output=True, text=True, timeout=30)
    out["mpv"] = re.findall(r"(?:home|user) path: '[^']*' -> '([^']*)'", r.stdout + r.stderr)
print(json.dumps(out))
'''


def tree_listing(root):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = pathlib.Path(dirpath) / name
            st = p.lstat()
            found.append((str(p), stat.S_IMODE(st.st_mode), st.st_mtime_ns, st.st_ctime_ns))
    return sorted(found)


def inside(path, root):
    if not path:
        return False
    try:
        pathlib.Path(os.path.abspath(path)).relative_to(root)
        return True
    except ValueError:
        return False


class HarnessHome(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="omarchy-iptv-fh20-")
        base = pathlib.Path(cls.tmp)
        cls.real = base / "realhome"
        cls.scratch = base / "harness"
        runtime = base / "run"
        runtime.mkdir(mode=0o700)
        cls.scratch.mkdir(mode=0o700)
        # The decoy home, laid out as the host and a session see it.
        cfg = cls.real / ".config" / "omarchy" / "shell.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(SEED_BODY, encoding="utf-8")
        os.chmod(cfg, 0o644)
        theme = cls.real / ".local" / "state" / "omarchy" / "current" / "theme"
        theme.mkdir(parents=True)
        (theme / "colors.toml").write_text(COLORS, encoding="utf-8")
        (theme / "shell.toml").write_text(SHELL_TOML, encoding="utf-8")
        (theme / "unrelated.png").write_bytes(b"not needed")
        cls.real_config = cfg
        cls.real_before = tree_listing(cls.real)
        probe = base / "probe.py"
        probe.write_text(PROBE, encoding="utf-8")
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LANG": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": str(cls.real),
            "XDG_CONFIG_HOME": str(cls.real / ".config"),
            "XDG_DATA_HOME": str(cls.real / ".local" / "share"),
            "XDG_CACHE_HOME": str(cls.real / ".cache"),
            "XDG_STATE_HOME": str(cls.real / ".local" / "state"),
            "XDG_RUNTIME_DIR": str(runtime),
            "WAYLAND_DISPLAY": "wayland-fh20",
            "MPV_HOME": str(cls.real / ".config" / "mpv"),
            "XCOMPOSEFILE": str(cls.real / ".XCompose"),
            "FH20_HELPER": str(HELPER),
        }
        r = subprocess.run(["bash", "-c", DRIVER, "fh20", str(QA_LIB), str(RUN_SH),
                            str(cls.scratch), str(runtime), str(probe)],
                           env=env, capture_output=True, text=True, timeout=120)
        cls.stderr = r.stderr
        try:
            cls.out = json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            cls.out = None
            cls.raw = (r.returncode, r.stdout[-500:], r.stderr[-500:])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.assertIsNotNone(self.out, "the probe produced nothing: %r" % (getattr(self, "raw", None),))

    def test_host_config_path_is_inside_the_harness(self):
        # THE defect: on the old harness this is <realhome>/.config/omarchy/shell.json.
        got = self.out["helper"]["host_config_path"]
        self.assertEqual(got, str(self.scratch / "home" / ".config" / "omarchy" / "shell.json"))

    def test_every_helper_path_is_inside_the_harness(self):
        bad = {k: v for k, v in self.out["helper"].items() if not inside(v, self.scratch)}
        self.assertEqual(bad, {}, "helper paths outside %s" % self.scratch)
        # Not vacuous: the probe asked every function it names.
        self.assertGreaterEqual(len(self.out["helper"]), 11)

    def test_every_user_directory_variable_is_inside_the_harness(self):
        env = self.out["env"]
        for k in ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
                  "XDG_STATE_HOME", "XDG_RUNTIME_DIR"):
            self.assertTrue(inside(env[k], self.scratch), "%s=%s" % (k, env[k]))
        # The two per-user overrides that bypass HOME are dropped when they
        # name the real home.
        self.assertIsNone(env["MPV_HOME"])
        self.assertIsNone(env["XCOMPOSEFILE"])

    def test_the_shield_acts_on_the_harness_copy_and_not_the_real_one(self):
        # The real one first: on the old harness this is the line that goes
        # red, 0644 -> 0600, which is the defect observed at its sink.
        self.assertEqual(stat.S_IMODE(self.real_config.stat().st_mode), 0o644)
        shield = self.out["shield"]
        self.assertTrue(shield.get("changed"), shield)
        self.assertEqual(shield.get("modeBefore"), "0644", shield)
        self.assertEqual(shield.get("modeAfter"), "0600", shield)
        seeded = self.scratch / "home" / ".config" / "omarchy" / "shell.json"
        self.assertTrue(seeded.is_file(), "run.sh seeded no host config inside the harness home")
        self.assertEqual(stat.S_IMODE(seeded.stat().st_mode), 0o600)

    def test_nothing_in_the_real_home_moved(self):
        # Mode, mtime and ctime of every entry: a chmod moves only ctime.
        self.assertEqual(tree_listing(self.real), self.real_before)

    def test_the_theme_is_a_copy_and_only_the_two_files_the_host_reads(self):
        theme = self.scratch / "home" / ".local" / "state" / "omarchy" / "current" / "theme"
        self.assertEqual(sorted(p.name for p in theme.iterdir()), ["colors.toml", "shell.toml"])
        for name, body in (("colors.toml", COLORS), ("shell.toml", SHELL_TOML)):
            p = theme / name
            self.assertFalse(p.is_symlink())
            self.assertEqual(p.read_text(encoding="utf-8"), body)
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)

    def test_the_harness_home_holds_no_symlink(self):
        # A link into the real home is a path by which a write in the harness
        # reaches the user's files.
        links = [os.path.join(d, n) for d, ds, fs in os.walk(self.scratch / "home")
                 for n in ds + fs if os.path.islink(os.path.join(d, n))]
        self.assertEqual(links, [])
        self.assertEqual(stat.S_IMODE((self.scratch / "home").stat().st_mode), 0o700)

    def test_python_user_site_is_inside_the_harness(self):
        self.assertTrue(inside(self.out["python_userbase"], self.scratch), self.out["python_userbase"])

    @unittest.skipUnless(shutil.which("mpv"), "mpv is not installed")
    def test_mpv_resolves_its_user_directories_inside_the_harness(self):
        paths = self.out["mpv"]
        self.assertTrue(paths, "mpv named no home or user path; the probe cannot see it")
        self.assertEqual([p for p in paths if not inside(p, self.scratch)], [])


class EveryDriverIsolatesItself(unittest.TestCase):
    """BOOKKEEPING, said so (rule 14): a name join, not an observation. Every
    scenario that drives run.sh exports the harness home for its OWN
    processes too, so a helper run or a probe it starts resolves the same
    way the service's do. What is observed is the function itself, above and
    in scripts/qa-lib-test.sh; this only catches a driver that forgot it."""

    def test_drivers_that_use_run_sh_call_qa_harness_home(self):
        missing = []
        for p in sorted(SCENARIOS.glob("*-scenario.sh")):
            text = p.read_text(encoding="utf-8")
            if '"$RUN"' in text or "run.sh" in text and "RUN=" in text:
                calls = [ln for ln in text.splitlines()
                         if ln.strip().startswith('qa_harness_home "$SCRATCH"')]
                if not calls:
                    missing.append(p.name)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
