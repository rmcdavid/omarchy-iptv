"""F-HARNESS-44: a cold harness shell starts over a wiped scratch SEEDED with a
shader cache, so a cold open figure pays the plugin's cold costs and not the
cage's software renderer compiling its shaders.

The defect. `run.sh` wipes XDG_CACHE_HOME at every start, and in the nested
headless cage the GL is llvmpipe, which JIT-compiles its shaders into mesa's
cache under that directory at the first frame: every cold open figure on
record (D-PERF-1's 548 / 534, D-PERF-2's ~440) carried about 240 ms of that
compile, which no desktop with a persistent cache pays (the D-PERF-2
attribution spike, 2026-10-24). The fix is in the harness: `run.sh
--seed-cache DIR` copies a directory into the scratch cache AFTER the wipe,
and `open-scenario.sh`'s shell arm warms a cache once with a throwaway shell
and seeds every cold shell from it (`OPEN_SHADER_SEED=0` turns that off).

What is pinned, by CALLING the shipping functions (CLAUDE.md 12, 14), never
by a grep for the strings they were written to contain:

  1. run.sh's parser: `--seed-cache` refuses a path that is not a directory,
     refuses to share a start with `--keep` (the same lever), and consumes its
     value (the parser reaches a deliberate unknown option after it).
  2. run.sh's `reset_scratch_cache`, extracted from the file and run over a
     decoy scratch, in all three modes: wiped (the plugin's cache and a stale
     shader cache both gone), kept (both still there), seeded (both gone and
     the seed present byte for byte, the printed count and bytes those of
     what landed). A revert of run.sh is a revert of what runs here.
  3. open-scenario.sh's `shader_seed_take` and `shader_cache_holds`, extracted
     and run over a fake cache: the seed holds exactly the cache's files, the
     list carries their sizes, and `holds` reads "all N" only while every
     listed file is present at its size -- a missing file and a changed size
     each read "missing".
  4. The names that join the two scripts (CLAUDE.md 13): the scenario passes
     run.sh the option run.sh's parser accepts, and the env switch the
     scenario's header names is the one it reads.

Nothing here starts a shell, a cage or a bus; every invocation dies in the
parser or runs an extracted function over a temporary directory, with the
display variables cleared.

Run: python3 -m unittest discover -s tests
"""
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
RUN_SH = ROOT / "scripts" / "dev-harness" / "run.sh"
OPEN_SH = ROOT / "scripts" / "dev-harness" / "open-scenario.sh"
QA_LIB = ROOT / "scripts" / "qa-lib.sh"
RUN_SH_TEXT = RUN_SH.read_text(encoding="utf-8")
OPEN_SH_TEXT = OPEN_SH.read_text(encoding="utf-8")


def clean_env(scratch):
    env = dict(os.environ)
    env.pop("WAYLAND_DISPLAY", None)
    env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
    env["OMARCHY_IPTV_HARNESS_DIR"] = scratch
    return env


def run_sh(*args):
    """run.sh with everything it could touch pointed at a throwaway directory.

    Every invocation here dies in the option parser, so no shell is started."""
    with tempfile.TemporaryDirectory() as tmp:
        return subprocess.run(["bash", str(RUN_SH)] + list(args), capture_output=True,
                              text=True, timeout=30, env=clean_env(tmp), cwd=str(ROOT))


def bash_function(script, name):
    """The text of `name() { ... }` in script, as the home test takes run.sh's."""
    match = re.search(r"^%s\(\) \{\n.*?^\}\n" % re.escape(name), script, re.S | re.M)
    if match is None:
        raise AssertionError("%s defines no %s()" % (script[:40], name))
    return match.group(0)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def tree(root):
    """{relative path: size} of every file under root."""
    out = {}
    for p in sorted(pathlib.Path(root).rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = p.stat().st_size
    return out


class RunShParserTest(unittest.TestCase):

    def test_seed_cache_refuses_a_path_that_is_not_a_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "no-such-seed")
            completed = run_sh("--seed-cache", missing)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("--seed-cache takes a directory", completed.stderr)
        self.assertNotIn("unknown option", completed.stderr)

    def test_seed_cache_refuses_an_empty_value(self):
        completed = run_sh("--seed-cache", "")
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("--seed-cache takes a directory", completed.stderr)

    def test_seed_cache_and_keep_are_the_same_lever(self):
        with tempfile.TemporaryDirectory() as seed:
            for order in (("--keep", "--seed-cache", seed), ("--seed-cache", seed, "--keep")):
                completed = run_sh(*order)
                self.assertEqual(completed.returncode, 2, (order, completed.stderr))
                self.assertIn("--keep and --seed-cache are the same lever", completed.stderr, order)

    def test_seed_cache_is_consumed_by_the_parser(self):
        # The option after --seed-cache DIR is a deliberate unknown: the
        # parser must reach IT, which it only does after consuming the
        # directory. A tree without --seed-cache dies on --seed-cache itself.
        with tempfile.TemporaryDirectory() as seed:
            completed = run_sh("--seed-cache", seed, "--no-such-option")
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("unknown option: --no-such-option", completed.stderr)
        self.assertNotIn("unknown option: --seed-cache", completed.stderr)

    def test_usage_lists_the_option(self):
        completed = run_sh("usage")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--seed-cache DIR", completed.stdout)


class ResetScratchCacheTest(unittest.TestCase):
    """run.sh's reset_scratch_cache, extracted and run over a decoy scratch."""

    DRIVER = r'''
set -u
die() { printf 'die: %s\n' "$*" >&2; exit 97; }
SCRATCH=$1 KEEP=$2 SEED_CACHE=$3
eval "$4"
declare -F reset_scratch_cache >/dev/null || { echo "run.sh defines no reset_scratch_cache" >&2; exit 96; }
reset_scratch_cache
'''

    def scratch(self, tmp):
        scratch = pathlib.Path(tmp) / "scratch"
        write(scratch / "cache" / "omarchy-iptv" / "channels.json", '{"channels":[]}\n')
        write(scratch / "cache" / "mesa_shader_cache" / "aa" / "stale", "stale shader\n")
        write(scratch / "state" / "omarchy-iptv" / "state.json", "{}\n")
        write(scratch / "runtime" / "omarchy-iptv" / "mpv.sock", "")
        seed = pathlib.Path(tmp) / "seed"
        write(seed / "mesa_shader_cache" / "index", "idx\n")
        write(seed / "mesa_shader_cache" / "3d" / "919b55", "x" * 1234)
        write(seed / "mesa_shader_cache" / "c9" / "3acec6", "y" * 77)
        return scratch, seed

    def reset(self, scratch, keep, seed):
        completed = subprocess.run(
            ["bash", "-c", self.DRIVER, "reset", str(scratch), str(keep), str(seed or ""),
             bash_function(RUN_SH_TEXT, "reset_scratch_cache")],
            capture_output=True, text=True, timeout=30, env=clean_env(str(scratch)), cwd=str(ROOT))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return completed.stdout.strip()

    def test_wiped_by_default_and_said_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            scratch, _ = self.scratch(tmp)
            said = self.reset(scratch, 0, "")
            self.assertEqual(said, "[run.sh] cache wiped")
            self.assertEqual(tree(scratch / "cache"), {})
            self.assertEqual(tree(scratch / "state"), {})
            self.assertFalse((scratch / "runtime" / "omarchy-iptv").exists())
            self.assertTrue((scratch / "cache").is_dir() and (scratch / "state").is_dir())

    def test_kept_with_keep_and_said_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            scratch, seed = self.scratch(tmp)
            before = tree(scratch)
            said = self.reset(scratch, 1, "")
            self.assertEqual(said, "[run.sh] cache kept")
            self.assertEqual(tree(scratch), before)

    def test_seeded_after_the_wipe_byte_for_byte_and_said_what_landed(self):
        with tempfile.TemporaryDirectory() as tmp:
            scratch, seed = self.scratch(tmp)
            said = self.reset(scratch, 0, seed)
            # the plugin's own cache and state are as cold as a wipe leaves them
            self.assertFalse((scratch / "cache" / "omarchy-iptv").exists())
            self.assertEqual(tree(scratch / "state"), {})
            # the stale shader cache is gone, the seed is there, nothing else
            self.assertEqual(tree(scratch / "cache"), tree(seed))
            for rel in tree(seed):
                self.assertEqual((scratch / "cache" / rel).read_bytes(), (seed / rel).read_bytes(), rel)
            # what it printed is what landed: the count and the bytes of the scratch
            self.assertEqual(said, "[run.sh] cache seeded from %s: 3 files, %d bytes" % (seed, 4 + 1234 + 77))


class OpenScenarioSeedTest(unittest.TestCase):
    """open-scenario.sh's shader_seed_take and shader_cache_holds, extracted
    and run over a fake cache."""

    DRIVER = r'''
set -u
eval "$1"
cmd=$2; shift 2
"$cmd" "$@"
'''

    def call(self, name, *args):
        fn = bash_function(OPEN_SH_TEXT, name)
        completed = subprocess.run(["bash", "-c", self.DRIVER, "seed", fn, name] + [str(a) for a in args],
                                   capture_output=True, text=True, timeout=30, cwd=str(ROOT))
        return completed.returncode, completed.stdout.strip(), completed.stderr

    def cache(self, tmp):
        cache = pathlib.Path(tmp) / "cache"
        write(cache / "mesa_shader_cache" / "index", "idx\n")
        write(cache / "mesa_shader_cache" / "3d" / "919b55", "x" * 1234)
        write(cache / "mesa_shader_cache" / "c9" / "3acec6", "y" * 77)
        write(cache / "omarchy-iptv" / "channels.json", "not a shader\n")
        return cache

    def test_take_copies_the_mesa_cache_alone_and_lists_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = self.cache(tmp)
            seed = pathlib.Path(tmp) / "seed"
            listing = pathlib.Path(tmp) / "seed.list"
            rc, out, err = self.call("shader_seed_take", cache, seed, listing)
            self.assertEqual(rc, 0, err)
            self.assertEqual(out, "3 files %d bytes" % (4 + 1234 + 77))
            self.assertEqual(tree(seed), {"mesa_shader_cache/3d/919b55": 1234,
                                          "mesa_shader_cache/c9/3acec6": 77,
                                          "mesa_shader_cache/index": 4})
            self.assertEqual(listing.read_text().splitlines(),
                             ["1234 mesa_shader_cache/3d/919b55", "77 mesa_shader_cache/c9/3acec6",
                              "4 mesa_shader_cache/index"])

    def test_take_fails_without_a_mesa_cache_or_with_an_empty_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            seed = pathlib.Path(tmp) / "seed"
            listing = pathlib.Path(tmp) / "seed.list"
            rc, _, _ = self.call("shader_seed_take", pathlib.Path(tmp) / "none", seed, listing)
            self.assertNotEqual(rc, 0)
            (pathlib.Path(tmp) / "empty" / "mesa_shader_cache").mkdir(parents=True)
            rc, _, _ = self.call("shader_seed_take", pathlib.Path(tmp) / "empty", seed, listing)
            self.assertNotEqual(rc, 0)

    def test_holds_reads_all_only_while_every_file_is_present_at_its_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = self.cache(tmp)
            seed = pathlib.Path(tmp) / "seed"
            listing = pathlib.Path(tmp) / "seed.list"
            rc, _, err = self.call("shader_seed_take", cache, seed, listing)
            self.assertEqual(rc, 0, err)
            # a scratch seeded from that seed: all there
            scratch = pathlib.Path(tmp) / "scratch-cache"
            subprocess.run(["cp", "-a", str(seed) + "/.", str(scratch) + "/"], check=True)
            rc, out, _ = self.call("shader_cache_holds", scratch, listing)
            self.assertEqual((rc, out), (0, "all 3"))
            # one file at another size: missing
            (scratch / "mesa_shader_cache" / "c9" / "3acec6").write_text("y" * 76)
            rc, out, _ = self.call("shader_cache_holds", scratch, listing)
            self.assertEqual((rc, out), (0, "missing 1 of 3"))
            # one file gone as well
            (scratch / "mesa_shader_cache" / "index").unlink()
            rc, out, _ = self.call("shader_cache_holds", scratch, listing)
            self.assertEqual((rc, out), (0, "missing 2 of 3"))
            # a wiped scratch: everything missing, never "all"
            rc, out, _ = self.call("shader_cache_holds", pathlib.Path(tmp) / "wiped", listing)
            self.assertEqual((rc, out), (0, "missing 3 of 3"))


class NamesJoinTest(unittest.TestCase):

    def test_the_scenario_passes_run_sh_the_option_its_parser_accepts(self):
        passed = re.findall(r'SEED_ARGS=\((--seed-cache) "\$SEED_DIR"\)', OPEN_SH_TEXT)
        parsed = re.findall(r"^\s+(--seed-cache)\) SEED_CACHE=\$2; shift$", RUN_SH_TEXT, re.M)
        self.assertEqual(passed, ["--seed-cache"])
        self.assertEqual(parsed, ["--seed-cache"])
        # and every start the scenario makes carries it
        starts = re.findall(r'h --detach --timeout 0 --playlist "\$FIX".*?>"\$WORK/start\.log"', OPEN_SH_TEXT)
        self.assertEqual(len(starts), 2)
        for line in starts:
            self.assertIn('"${SEED_ARGS[@]}"', line)

    def test_the_switch_the_header_names_is_the_one_the_scenario_reads(self):
        header = OPEN_SH_TEXT.split("set -uo pipefail", 1)[0]
        self.assertIn("OPEN_SHADER_SEED=0 open-scenario.sh live", header)
        self.assertEqual(re.findall(r"SHADER_SEED=\$\{(OPEN_SHADER_SEED):-1\}", OPEN_SH_TEXT), ["OPEN_SHADER_SEED"])

    def test_the_figure_lines_name_the_condition(self):
        # "shader cache: seeded" and "shader cache: wiped" are the two words a
        # reader is promised; both come from one function, and the BUDGET
        # line and the shell-arm header print it.
        fn = bash_function(OPEN_SH_TEXT, "shader_cache_line") if "shader_cache_line() {\n" in OPEN_SH_TEXT \
            else re.search(r"^shader_cache_line\(\) \{.*$", OPEN_SH_TEXT, re.M).group(0)
        self.assertIn('"shader cache: seeded', fn)
        self.assertIn('"shader cache: wiped', fn)
        self.assertGreaterEqual(OPEN_SH_TEXT.count("$(shader_cache_line)"), 3)

    def test_no_harness_script_assigns_a_bash_special_name(self):
        # Found the day this file was written: the fixture's group count was
        # held in `GROUPS`, which bash owns (assignments to it have no effect
        # and `$GROUPS` is the user's first gid), so the shell arm's first run
        # generated 1,000 groups where the record has 400 and its summon
        # read 116 ms against 88. A guard over the SHAPE, not a criterion.
        special = re.compile(r"(?:^|[\s;{(])(SECONDS|RANDOM|GROUPS|UID|EUID|PPID|LINENO|SHLVL|DIRSTACK|"
                             r"HISTCMD|BASHPID|COLUMNS|LINES|FUNCNAME|BASH_[A-Z_]+)=", re.M)
        offenders = []
        for script in sorted((ROOT / "scripts").rglob("*.sh")):
            text = script.read_text(encoding="utf-8")
            for m in special.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                if not text.splitlines()[line - 1].lstrip().startswith("#"):
                    offenders.append("%s:%d %s" % (script.relative_to(ROOT), line, m.group(1)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
