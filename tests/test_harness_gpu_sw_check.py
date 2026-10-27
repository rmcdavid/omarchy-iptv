"""F-HARNESS-46: player-scenario.sh's P2 check for D-PLY-27's `--gpu-sw=yes`.

D-PLY-27 (dev 1044f7b, owner's decision 2026-10-26) put `--gpu-sw=yes` in
the BASE section of the player's launch argv in both mirrors: after the two
cache directories, before D-SINK-13's layer 1 `--tls-verify=yes`, once,
never re-asserted, never reserved. player-scenario.sh's P2 reads the live
player's `/proc/<pid>/cmdline` and now asserts that token there, by
POSITION: run.sh's harness_env appends a second `--gpu-sw=yes` to the
user's mpvArgs under a pixman cage (F-HARNESS-45), after layer 1, so a
check that counted the token anywhere would pass on a tree that lost the
base one.

Why a test here and not only the scenario. player-scenario.sh needs a
display and a player, so check.sh never runs it; between live runs nothing
would notice if the check's SKIP grew (a baseline-aware check that skips one
ref too many is a check that cannot go red, rule 14) or if its argv parse
went back to a substring of the space-joined command line. The live run
observes the real cmdline; this pins the two decisions the live run takes
on trust, by DRIVING the scenario's own functions, pulled out of the file as
text (tests/test_harness_cage_player.py's shape), never a copy of them:

1. gpu_sw_base reads the argv as NUL-separated ITEMS of a real process and
   counts exact `--gpu-sw=yes` items before the first `--tls-verify=yes`.
2. gpu_sw_skip_reason SKIPs only for a --baseline ref that lacks D-PLY-27's
   code commit AND declares 0.15.0 or older in its manifest; no baseline, a
   ref containing the commit, a later release, an unknown ref or an
   unreadable manifest all ASSERT. The version half exists because release
   commits on `main` contain no dev commit at all (release.py exports onto
   main's own history), so on ancestry alone a future v0.16.0 would skip.
3. The P2 block itself, extracted between its first line and its `fi`,
   routes those answers to a counted SKIP or to an asserted PASS/FAIL.
4. DPLY27_CODE names the commit that introduced MPV_GPU_SW in both mirrors.

Rule 11: `FH46_ROOT=<tree>` runs these against another checkout. Written by
a copy of lane-fh46 that was stopped before it committed (F-M3-25), held out
of the tree, read line by line and adopted by lane-hfu on 2026-10-26 against
dev e243c29's committed player-scenario.sh, where all 20 pass. Red:
- dev b43c4a4 (before F-HARNESS-46): all 20 fail, each on the frame the
  scenario does not have yet (28 failures counting subtests).
- four mutants of the shipped P2, each in a copy of player-scenario.sh:
  the token counted anywhere (the `break` at layer 1 removed): 6 fail;
  the skip on ancestry only (the version's range ignored): 2 fail;
  the skip on version only (the ancestry ignored): 4 fail;
  a joined-string parse (argv read as the space-joined command line): 2 fail.

The scenario's text is EVALUATED, so every range taken out of it must end
where the thing it names ends: a start anchor whose end anchor is missing
would hand sed's range the rest of the file -- the scenario's top level --
and on b43c4a4 it did (the frame's `skp()` did not exist yet; it stopped at
the first unset variable, `set -u`, having only defined functions). Each
extraction is checked for its end before it is run.
"""

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(os.environ.get("FH46_ROOT") or pathlib.Path(__file__).resolve().parent.parent)
SCENARIO = ROOT / "scripts" / "dev-harness" / "player-scenario.sh"

# The scenario's counting frame (ok/bad/is/ck/skp), its four functions and
# its DPLY27_CODE line, evaluated from the file as text, then one mode.
DRIVER = r'''
set -u
SCENARIO=$1 MODE=$2; shift 2
frame=$(sed -n '/^ok()  { printf/,/^skp() { printf/p' "$SCENARIO")
[[ $(tail -n 1 <<<"$frame") == "skp() { printf"* && $(wc -l <<<"$frame") -lt 20 ]] \
  || { echo "player-scenario.sh has no ok()..skp() frame to take whole" >&2; exit 96; }
eval "$frame"
for f in ok bad is ck skp; do
  declare -F "$f" >/dev/null || { echo "player-scenario.sh defines no $f" >&2; exit 96; }
done
for f in argv_items gpu_sw_base gpu_sw_items gpu_sw_skip_reason; do
  body=$(sed -n "/^$f() {/,/^}/p" "$SCENARIO")
  [[ -n $body && $(tail -n 1 <<<"$body") == "}" && $(wc -l <<<"$body") -lt 40 ]] \
    || { echo "player-scenario.sh defines no $f to take whole" >&2; exit 96; }
  eval "$body"
  declare -F "$f" >/dev/null || { echo "player-scenario.sh defines no $f" >&2; exit 96; }
done
eval "$(grep -E '^DPLY27_CODE=[0-9a-f]+$' "$SCENARIO")"
[[ -n ${DPLY27_CODE-} ]] || { echo "player-scenario.sh sets no DPLY27_CODE" >&2; exit 96; }
pass=0 fail=0 checks=0 skipped=0
case $MODE in
  code)  printf '%s\n' "$DPLY27_CODE" ;;
  base)  gpu_sw_base "$1" ;;
  items) gpu_sw_items "$1" ;;
  skip)  # skip <root> <code or ""> <ref>
    ROOT=$1; [[ -n $2 ]] && DPLY27_CODE=$2
    why=$(gpu_sw_skip_reason "$3"); rc=$?
    printf 'rc=%s\nwhy=%s\n' "$rc" "$why" ;;
  p2)    # p2 <root> <code or ""> <baseline> <pid>
    ROOT=$1; [[ -n $2 ]] && DPLY27_CODE=$2; BASELINE=$3; PID1=$4
    block=$(sed -n "/^printf '   P2 argv items read/,/^fi\$/p" "$SCENARIO")
    [[ -n $block && $(tail -n 1 <<<"$block") == fi && $(wc -l <<<"$block") -lt 15 ]] \
      || { echo "player-scenario.sh has no P2 gpu-sw block to take whole" >&2; exit 96; }
    eval "$block"
    printf 'counters pass=%s fail=%s checks=%s skipped=%s\n' "$pass" "$fail" "$checks" "$skipped" ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac
'''

# A process whose argv the test chooses: python's own four items, then ours.
SLEEPER = [sys.executable, "-I", "-c", "import time; time.sleep(60)"]
LEAD = len(SLEEPER)

SHIPPED = ["--idle=once", "--icc-cache-dir=/r/shader", "--gpu-sw=yes", "--tls-verify=yes",
           "--ao=null", "--gpu-sw=yes", "--tls-verify=yes"]
LOST = ["--idle=once", "--icc-cache-dir=/r/shader", "--tls-verify=yes",
        "--ao=null", "--gpu-sw=yes", "--tls-verify=yes"]


def drive(*args):
    proc = subprocess.run(["bash", "-c", DRIVER, "fh46", str(SCENARIO)] + [str(a) for a in args],
                          capture_output=True, text=True, timeout=30)
    if proc.returncode == 96:
        raise AssertionError(proc.stderr.strip())
    return proc


class Sleeper:
    """A live process with a chosen argv, reaped on exit."""

    def __init__(self, items):
        self.items = items

    def __enter__(self):
        self.proc = subprocess.Popen(SLEEPER + list(self.items), stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self.proc.pid

    def __exit__(self, *exc):
        self.proc.kill()
        self.proc.wait(timeout=10)


def git(repo, *args, env_extra=None):
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@t")
    out = subprocess.run(["git", "-C", str(repo)] + list(args), capture_output=True, text=True,
                         env=env, timeout=30)
    if out.returncode != 0:
        raise AssertionError("git %s: %s" % (" ".join(args), out.stderr))
    return out.stdout.strip()


class ArgvItems(unittest.TestCase):
    """1. The token is counted as an ITEM, before layer 1, on a real process."""

    def base(self, items):
        with Sleeper(items) as pid:
            return drive("base", pid).stdout.strip()

    def test_the_shipped_shape_reads_one_base_copy_beside_the_levers(self):
        self.assertEqual(self.base(SHIPPED), "layer1:yes base:1")

    def test_a_tree_that_lost_the_base_token_reads_zero_though_the_levers_copy_is_there(self):
        # The case the position exists for: the lever's copy after layer 1.
        self.assertEqual(self.base(LOST), "layer1:yes base:0")
        self.assertEqual(LOST.count("--gpu-sw=yes"), 1)

    def test_two_base_copies_are_not_once(self):
        items = ["--gpu-sw=yes", "--gpu-sw=yes", "--tls-verify=yes"]
        self.assertEqual(self.base(items), "layer1:yes base:2")

    def test_no_layer_one_is_its_own_answer(self):
        # The positive control: without layer 1 there is no "before".
        self.assertEqual(self.base(["--idle=once", "--gpu-sw=yes"]), "layer1:no base:1")

    def test_the_token_inside_another_item_is_not_an_item(self):
        # Joined with spaces (cmdline_of's form) this reads as the token
        # before layer 1; read as items it is a title, and nothing else.
        items = ["--title=$>x --gpu-sw=yes", "--tls-verify=yes", "--gpu-sw=yes", "--tls-verify=yes"]
        joined = " ".join(items)
        self.assertLess(joined.index(" --gpu-sw=yes"), joined.index("--tls-verify=yes"))
        self.assertEqual(self.base(items), "layer1:yes base:0")

    def test_a_longer_value_is_not_the_token(self):
        self.assertEqual(self.base(["--gpu-sw=yesno", "--tls-verify=yes"]), "layer1:yes base:0")

    def test_a_users_later_no_does_not_move_the_base_answer(self):
        items = ["--gpu-sw=yes", "--tls-verify=yes", "--gpu-sw=no", "--tls-verify=yes"]
        self.assertEqual(self.base(items), "layer1:yes base:1")

    def test_an_unreadable_pid_is_noargv_never_the_kernels_command_line(self):
        for pid in ("", "abc", "1/../1", "4194399"):
            with self.subTest(pid=pid):
                self.assertEqual(drive("base", pid).stdout.strip(), "NOARGV")

    def test_the_transcript_line_names_each_deciding_item_with_its_index(self):
        with Sleeper(SHIPPED) as pid:
            out = drive("items", pid).stdout.strip()
        want = "#%d --gpu-sw=yes #%d --tls-verify=yes #%d --ao=null #%d --gpu-sw=yes #%d --tls-verify=yes of %d items" % (
            LEAD + 2, LEAD + 3, LEAD + 4, LEAD + 5, LEAD + 6, LEAD + len(SHIPPED))
        self.assertEqual(out, want)


class SkipDecision(unittest.TestCase):
    """2 and 3. A hermetic history in dev's and main's shapes."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="fh46-")
        repo = cls.repo = pathlib.Path(cls.tmp.name) / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "dev")

        def commit(version, msg, extra=None):
            if version is None:
                (repo / "manifest.json").unlink(missing_ok=True)
            else:
                (repo / "manifest.json").write_text(json.dumps({"version": version}))
            (repo / "f").write_text(msg)
            git(repo, "add", "-A")
            git(repo, "commit", "-q", "-m", msg)
            return git(repo, "rev-parse", "HEAD")

        cls.pre = commit("0.15.0", "dev before D-PLY-27")
        cls.code = commit("0.15.0", "D-PLY-27 code")
        cls.post = commit("0.15.0", "dev after D-PLY-27")
        cls.dev_016 = commit("0.16.0", "dev bumps for the cut")
        # main: release.py's export, a history of its own.
        git(repo, "checkout", "-q", "--orphan", "main")
        cls.rel_0143 = commit("0.14.3", "release: 0.14.3")
        cls.rel_0150 = commit("0.15.0", "release: 0.15.0")
        cls.rel_0160 = commit("0.16.0", "release: 0.16.0")
        cls.rel_rc = commit("0.15.0-rc1", "a version that is not three numbers")
        cls.no_manifest = commit(None, "no manifest at all")
        git(repo, "tag", "v0.15.0", cls.rel_0150)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def decide(self, ref, code=None):
        out = drive("skip", self.repo, code or self.code, ref).stdout
        fields = dict(line.split("=", 1) for line in out.strip().splitlines())
        return fields["rc"], fields["why"]

    def assert_asserts(self, ref, code=None):
        rc, why = self.decide(ref, code)
        self.assertEqual((rc, why), ("1", ""), "ref %r must ASSERT" % ref)

    def assert_skips(self, ref):
        rc, why = self.decide(ref)
        self.assertEqual(rc, "0", "ref %r must SKIP" % ref)
        self.assertIn("does not contain D-PLY-27", why)
        self.assertIn(ref, why)

    def test_no_baseline_always_asserts(self):
        self.assert_asserts("")

    def test_a_ref_that_contains_the_code_asserts(self):
        for ref in (self.code, self.post, self.dev_016, "dev"):
            with self.subTest(ref=ref):
                self.assert_asserts(ref)

    def test_a_dev_ref_before_the_code_skips(self):
        self.assert_skips(self.pre)

    def test_a_release_through_0_15_0_skips(self):
        for ref in (self.rel_0143, self.rel_0150, "v0.15.0"):
            with self.subTest(ref=ref):
                self.assert_skips(ref)

    def test_a_later_release_asserts_though_main_contains_no_dev_commit(self):
        # Ancestry alone says "does not contain" here; the version says it
        # carries the token.
        self.assertNotEqual(subprocess.run(["git", "-C", str(self.repo), "merge-base", "--is-ancestor",
                                            self.code, self.rel_0160]).returncode, 0)
        self.assert_asserts(self.rel_0160)

    def test_anything_git_or_the_manifest_cannot_answer_asserts(self):
        self.assert_asserts("no-such-ref")
        self.assert_asserts(self.rel_rc)
        self.assert_asserts(self.no_manifest)
        self.assert_asserts(self.rel_0150, code="0123456789abcdef0123456789abcdef01234567")

    def p2(self, baseline, items):
        with Sleeper(items) as pid:
            return drive("p2", self.repo, self.code, baseline, pid).stdout

    def test_p2_fails_on_the_lost_token_with_no_baseline(self):
        out = self.p2("", LOST)
        self.assertIn("counters pass=0 fail=1 checks=1 skipped=0", out)
        self.assertIn("(got 'layer1:yes base:0', want 'layer1:yes base:1')", out)
        self.assertIn("P2 argv items read:", out)

    def test_p2_passes_on_the_shipped_shape(self):
        self.assertIn("counters pass=1 fail=0 checks=1 skipped=0", self.p2("", SHIPPED))

    def test_p2_skips_counted_and_with_its_reason_on_a_pre_d_ply_27_baseline(self):
        out = self.p2("v0.15.0", LOST)
        self.assertIn("counters pass=0 fail=0 checks=0 skipped=1", out)
        self.assertRegex(out, r"(?m)^SKIP P2 the base section carries --gpu-sw=yes .*: v0\.15\.0 \(manifest 0\.15\.0\) does not contain D-PLY-27")

    def test_p2_still_asserts_on_a_baseline_that_has_the_code(self):
        self.assertIn("counters pass=0 fail=1 checks=1 skipped=0", self.p2(self.post, LOST))
        self.assertIn("counters pass=0 fail=1 checks=1 skipped=0", self.p2(self.rel_0160, LOST))


class TheConstant(unittest.TestCase):
    """4. DPLY27_CODE is the commit that put MPV_GPU_SW in both mirrors."""

    def test_the_named_commit_introduces_the_token_in_both_mirrors(self):
        code = drive("code").stdout.strip()
        have = subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", code + "^{commit}"],
                              capture_output=True)
        if have.returncode != 0:
            self.skipTest("this checkout has no history holding %s" % code)
        for path, line in (("bin/helper/07-player.py", 'MPV_GPU_SW = "--gpu-sw=yes"'),
                           ("model/build.mjs", 'var MPV_GPU_SW = "--gpu-sw=yes"')):
            with self.subTest(path=path):
                after = git(ROOT, "show", "%s:%s" % (code, path))
                before = git(ROOT, "show", "%s^:%s" % (code, path))
                self.assertIn(line, after)
                self.assertNotIn("MPV_GPU_SW", before)


if __name__ == "__main__":
    unittest.main()
