"""F-HARNESS-49 (2026-10-27): key-scenario.sh's `--only` selector, and the
promise it makes -- a FULL run executes and counts exactly what it did
before the flag existed, and a partial run can never be read as a full one.

`--only A,B19` runs the instrument arm, the named shell-arm blocks, then P1,
P2 and T1. It exists because A2 and B19 went red on 2026-10-27 and a full
live run costs about ten minutes a sample. `PRUNE` was a rig (no check) that
only `--only` ran; since D-SRC-69 was fixed it holds B41 and runs in every
full run like A and B19 (pinned below: a check that only an opt-in flag
reaches is a check no release run counts). What can go wrong with such a
flag is exactly what these cases pin:

  * a block a full run used to execute is skipped when the flag is ABSENT
    (the count would drop and the floor catch it -- but only on a live run;
    this catches it on every commit): every guard in shell_arm is one of
    the three shapes, and only the opt-in shape may hold no check;
  * the partial floor drifts from the blocks it counts: ONLY_CHECKS is
    compared with the ck lines between each block's own markers;
  * a name matches more than it says (`B1` selecting `B19`): seg_on is
    DRIVEN, extracted from the file and run (rule 12);
  * a mistyped or misplaced flag starts a cage: every refusal is driven
    with a PATH whose cage, quickshell and qs are stand-ins that only record
    being run, and must exit 2 with no transcript and no stand-in run.

Rule 11: `FH49_ROOT=<tree>` runs these against another checkout.
"""

import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(os.environ.get("FH49_ROOT") or pathlib.Path(__file__).resolve().parent.parent)
KS = ROOT / "scripts" / "dev-harness" / "key-scenario.sh"


def text():
    return KS.read_text(encoding="utf-8")


def only_checks(src):
    m = re.search(r"^declare -A ONLY_CHECKS=\(([^)]*)\)$", src, re.M)
    if not m:
        return None
    return {k: int(v) for k, v in re.findall(r"\[([A-Za-z0-9]+)\]=([0-9]+)", m.group(1))}


def shell_arm_lines(src):
    lines = src.split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith("shell_arm() {"))
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")
    return lines[start + 1:end]


GUARD_FULL = re.compile(r"^  if \[\[ -z \$ONLY \]\]; then   # --only: (.+), full runs only$")
GUARD_SEG = re.compile(r"^  if seg_on ([A-Za-z0-9]+); then   # --only \1 begins$")
GUARD_OPTIN = re.compile(r"^  if \[\[ -n \$ONLY \]\] && seg_on ([A-Za-z0-9]+); then   # --only \1 begins \(a rig: never in a full run\)$")
END = re.compile(r"^  fi   # --only(: end of .+| [A-Za-z0-9]+ ends)$")
CK = re.compile(r'^ *ck "[A-Z][0-9]')


def blocks(src):
    """[(kind, name, [lines])] for the guarded blocks of shell_arm, in
    order, and the lines outside any guard as kind "always". Raises on a
    guard of any other shape, a nested guard or one left open."""
    out, cur, kind, name = [], [], "always", ""
    for line in shell_arm_lines(src):
        m_full, m_seg, m_opt = GUARD_FULL.match(line), GUARD_SEG.match(line), GUARD_OPTIN.match(line)
        if m_full or m_seg or m_opt:
            if kind != "always":
                raise AssertionError("a guard opened inside another: %r" % line)
            out.append((kind, name, cur))
            cur = []
            kind, name = ("full", m_full.group(1)) if m_full else (("seg", m_seg.group(1)) if m_seg else ("optin", m_opt.group(1)))
            continue
        if END.match(line):
            if kind == "always":
                raise AssertionError("a guard closed that was never opened: %r" % line)
            out.append((kind, name, cur))
            cur, kind, name = [], "always", ""
            continue
        if "$ONLY" in line and line.lstrip().startswith("if "):
            raise AssertionError("a guard on $ONLY of another shape: %r" % line)
        cur.append(line)
    if kind != "always":
        raise AssertionError("the %s guard %s is never closed" % (kind, name))
    out.append((kind, name, cur))
    return out


class OnlyIsNarrowAndAFullRunIsWhole(unittest.TestCase):
    def test_every_guard_is_true_without_the_flag_or_holds_no_check(self):
        bs = blocks(text())
        kinds = [k for k, _, _ in bs]
        self.assertIn("seg", kinds)
        self.assertIn("full", kinds)
        for kind, name, lines in bs:
            if kind == "optin":
                self.assertEqual([l for l in lines if CK.match(l)], [], "the opt-in block %s holds a check a full run would not count" % name)

    def test_the_partial_floor_is_each_blocks_own_ck_lines(self):
        src = text()
        table = only_checks(src)
        self.assertIsNotNone(table, "no ONLY_CHECKS table")
        found = {}
        for kind, name, lines in blocks(src):
            if kind in ("seg", "optin"):
                found[name] = sum(1 for l in lines if CK.match(l))
        self.assertEqual(table, found)
        self.assertEqual(table.get("A"), 2)
        self.assertEqual(table.get("B19"), 1)
        self.assertEqual(table.get("PRUNE"), 1)

    def test_prune_is_a_counted_block_of_every_full_run(self):
        # D-SRC-69 (2026-10-27): the rig became B41. It must be a `seg` block
        # (true when --only is absent), hold B41 and nothing else, and no
        # opt-in block may be left holding it.
        kinds = {(k, n): lines for k, n, lines in blocks(text())}
        self.assertNotIn(("optin", "PRUNE"), kinds)
        self.assertIn(("seg", "PRUNE"), kinds)
        cks = [re.match(r'^ *ck "([A-Z][0-9]+)', l).group(1) for l in kinds[("seg", "PRUNE")] if CK.match(l)]
        self.assertEqual(cks, ["B41"])

    def test_a_full_run_counts_what_the_floor_says(self):
        # The floor's own recipe (qa-lib-test.sh joins it too): every lettered
        # ck line in the file, and none of them inside an opt-in block (above).
        src = text()
        floors = re.findall(r"^ *EXPECTED_CHECKS=([0-9]+)$", src, re.M)
        self.assertEqual(len(floors), 2)
        self.assertEqual(int(floors[1]), sum(1 for l in src.split("\n") if CK.match(l)))

    def test_seg_on_matches_whole_names_and_everything_without_the_flag(self):
        m = re.search(r"^seg_on\(\) \{.*\}$", text(), re.M)
        self.assertIsNotNone(m, "seg_on is not a one-line function any more")
        driver = m.group(0) + '\nONLY=$1; shift\nfor n in "$@"; do if seg_on "$n"; then printf "%s " "$n"; fi; done\n'
        names = ["A", "B19", "B1", "PRUNE", "A2", "B"]

        def on(only):
            r = subprocess.run(["bash", "-c", driver, "seg_on", only] + names, capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout.split()

        self.assertEqual(on(""), names)
        self.assertEqual(on("A"), ["A"])
        self.assertEqual(on("B19"), ["B19"])
        self.assertEqual(on("A,B19"), ["A", "B19"])
        self.assertEqual(on("B1"), ["B1"])


class RefusalsStartNothing(unittest.TestCase):
    """Each refusal exits 2 above the transcript, and no cage, quickshell or
    qs is ever run: the three are stand-ins here that append to a log."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fh49-only-")
        self.bin = os.path.join(self.tmp, "bin")
        os.mkdir(self.bin)
        self.ran = os.path.join(self.tmp, "ran.log")
        for name in ("cage", "quickshell", "qs"):
            path = os.path.join(self.bin, name)
            with open(path, "w") as f:
                f.write("#!/bin/sh\necho %s >>%s\nexit 1\n" % (name, self.ran))
            os.chmod(path, 0o755)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def refuse(self, *args):
        harness = os.path.join(self.tmp, "h")
        env = dict(os.environ)
        env["PATH"] = self.bin + os.pathsep + env.get("PATH", "")
        env["OMARCHY_IPTV_HARNESS_DIR"] = harness
        env.pop("KEY_CAGE_BIN", None)
        r = subprocess.run(["bash", str(KS)] + list(args), capture_output=True, text=True, timeout=60, env=env)
        transcripts = os.path.join(harness, "transcripts")
        landed = os.listdir(transcripts) if os.path.isdir(transcripts) else []
        ran = open(self.ran).read() if os.path.exists(self.ran) else ""
        return r.returncode, landed, ran, r.stderr

    def test_refusals(self):
        cases = [
            (["live", "--only"], "--only needs a segment list"),
            (["live", "--only", "--baseline"], "--only needs a segment list"),
            (["live", "--only", "Z"], "'Z' is not a selectable segment"),
            (["live", "--only", "B1"], "'B1' is not a selectable segment"),
            (["live", "--only", "A,,B19"], "'' is not a selectable segment"),
            (["check-tree", "--only", "A"], "check-tree runs the instrument arm alone"),
        ]
        for args, says in cases:
            with self.subTest(args=args):
                rc, landed, ran, err = self.refuse(*args)
                self.assertEqual((rc, landed, ran), (2, [], ""), err)
                self.assertIn(says, err)


if __name__ == "__main__":
    unittest.main()
