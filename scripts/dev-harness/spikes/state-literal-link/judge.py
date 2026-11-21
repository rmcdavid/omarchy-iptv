#!/usr/bin/env python3
"""scripts/dev-harness/spikes/state-literal-link/judge.py -- the helper's
half of the D-STATE-9 spike (2026-11-21): what the shipping helper's guard
says about a layout BEFORE the probe saves through QSaveFile, and whether
that matches where the save landed.

  judge.py before ROOT PATH OUT
      loads ROOT's helper (bin/omarchy-iptv, no bytecode written), and
      writes to OUT a JSON object: `literal`, qt_link_literal(PATH) -- the
      file the helper says QSaveFile writes (PATH itself past QSaveFile's
      bound of 127 links), null where a link cannot be read --
      `split`, state_link_split(PATH), and `kernel`, the file the kernel
      resolves PATH to (realpath; null when it cannot be resolved). A tree
      with no guard (a baseline run) writes `guard: false` and no verdict.
      Reads only: no state verb runs here.
  judge.py after OUT PROBE_OUT CASE EXPECT WORK
      reads the probe's lines and the files on disk after the save and
      prints one CHECK line: whether the helper's literal file is the file
      that holds NEW (or, where QSaveFile could not open, that its folder is
      missing too), whether NEW missed the kernel's file, and whether the
      helper's `split` is that miss and is EXPECT (yes|no). Exit 1 on a
      FAIL.
  judge.py corpus
      the cleanPath corpus, one hex line per input ("-" for the empty one):
      a hand-written list and a seeded random set.
  judge.py fixture CLEAN_OUT QT_VERSION
      the probe's `--clean` lines -> tests/fixtures/qt-clean-path.json.
ASCII only (CLAUDE.md, engineering constraint 8)."""
import importlib.machinery
import importlib.util
import json
import os
import random
import sys


def load_helper(root):
    loader = importlib.machinery.SourceFileLoader("omarchy_iptv", os.path.join(root, "bin", "omarchy-iptv"))
    spec = importlib.util.spec_from_loader("omarchy_iptv", loader)
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    loader.exec_module(module)
    return module


def text_of(path):
    try:
        if os.path.islink(path):
            return "<link>"
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.readline().strip()
    except FileNotFoundError:
        return None
    except OSError as error:
        return "<%s>" % (error.strerror or type(error).__name__)


def before(root, path, out):
    helper = load_helper(root)
    verdict = {"guard": hasattr(helper, "state_link_split")}
    try:
        os.stat(path)
        verdict["kernel"] = os.path.realpath(path, strict=True)
    except FileNotFoundError:
        verdict["kernel"] = os.path.realpath(path)
    except OSError as error:
        verdict["kernel"] = None
        verdict["kernelError"] = error.strerror or type(error).__name__
    if verdict["guard"]:
        verdict["literal"] = helper.qt_link_literal(path)
        verdict["split"] = helper.state_link_split(path)
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(verdict, handle)


def after(out, probe_out, case, expect, work):
    with open(out, encoding="utf-8") as handle:
        verdict = json.load(handle)
    lines = open(probe_out, encoding="utf-8", errors="replace").read().splitlines()
    open_failed = any("open failed" in line for line in lines)
    # A name that is not UTF-8 (the kernel's, a surrogate) and the U+FFFD
    # name QSaveFile writes for it are printed as their bytes, \x-escaped.
    rel = lambda p: "none" if p is None else os.fsencode(os.path.relpath(p, work)).decode("ascii", "backslashreplace")
    if not verdict["guard"]:
        print("  CHECK case=%s guard=none (this tree's helper has no state_link_split)" % case)
        return 0
    literal, kernel, split = verdict["literal"], verdict["kernel"], verdict["split"]
    problems = []
    if literal is None:
        written = "unreadable-link"
    elif open_failed:
        written = "open-failed" + ("" if not os.path.isdir(os.path.dirname(literal)) else "-BUT-FOLDER-THERE")
        if os.path.isdir(os.path.dirname(literal)):
            problems.append("QSaveFile could not open, yet the helper's literal folder exists")
    else:
        written = "yes" if text_of(literal) == "NEW" else "NO"
        if written == "NO":
            problems.append("the helper's literal file does not hold NEW")
    if kernel is None:
        miss = "n/a"
        if split:
            problems.append("split claimed where the kernel cannot resolve the path")
    else:
        miss = "no" if text_of(kernel) == "NEW" else "yes"
        if split != (miss == "yes"):
            problems.append("split is %s but the save %s the kernel's file" % (split, "missed" if miss == "yes" else "reached"))
    if ("yes" if split else "no") != expect:
        problems.append("split is %s, expected %s" % ("yes" if split else "no", expect))
    print("  CHECK case=%s helper-literal=%s literal-written=%s kernel=%s missed-kernel=%s split=%s expected=%s %s"
          % (case, rel(literal), written, rel(kernel), miss, "yes" if split else "no", expect,
             "ok" if not problems else "FAIL: " + "; ".join(problems)))
    return 1 if problems else 0


CORPUS = [
    "", "/", "//", "///", ".", "./", "..", "../", "/.", "/./", "/..", "/../", "/../..", "/../a", "/../a/..",
    "/../a/../b", "/a/../..", "/a/../../b", "/a/b/../c", "/a/./b", "//a//b", "/a/b/", "/a/b//", "/a/..", "/a/../",
    "/a/b/..", "/a/b/../..", "/a/b/../../..", "a/../../b", "a/..", "a/../..", "a/b/../../..", "../..", "../../a",
    "./..", ".//..", "x/./../..", "/a/.../b", "/a/..b/c", "/a/b..", "/a/.b", "/a//../b", "/./..", "/a/./../b", "./a",
    "a/./b", "a//b", "../a/./../b", "/a/b/./", "/a/b/.", "/a/b/c/../../d/./e/../f", "/a\\b/../c", "/a/b\\../c",
    "/a/~/../b", "/x/state/../wide/state.json", "/c/home/.local/state/omarchy-iptv/../../x/state.json",
    "/a/b/../../../../c", "/..a", "/a/..../b", "/a/ /../b", "/a/\u00e9/../b", "/a/\ufffd/../b", "//..", "///../a",
    "/a/b/./../c/", "/ab/cd/../../ef", "/a/b/c/../../../..", "/a/b/c/../../../../..", "/t/s/../../../../../x",
]
SEGMENTS = ["", ".", "..", "a", "b", "..a", "a..", ".a", "...", "a\\b", "\\..", "st ate"]


def corpus():
    rng = random.Random(9)   # D-STATE-9; a fixed seed, so the corpus is the same every run
    cases = list(CORPUS)
    for _ in range(400):
        parts = [rng.choice(SEGMENTS) for _ in range(rng.randint(1, 8))]
        text = "/".join(parts)
        cases.append(("/" + text) if rng.random() < 0.75 else text)
    seen = []
    for text in cases:
        if text not in seen:
            seen.append(text)
    for text in seen:
        print(text.encode("utf-8").hex() or "-")


def fixture(clean_out, qt_version):
    decode = lambda h: "" if h == "-" else bytes.fromhex(h).decode("utf-8")
    pairs = []
    for line in open(clean_out, encoding="utf-8", errors="replace"):
        words = line.split()
        if len(words) == 3 and words[0] == "CLEAN":
            pairs.append([decode(words[1]), decode(words[2])])
    if not pairs:
        print("judge.py: no CLEAN lines in %s" % clean_out, file=sys.stderr)
        return 1
    document = {
        "about": ("D-STATE-9 (2026-11-21): QDir::cleanPath as the installed Qt computes it, one [input, output] "
                  "pair per entry, written by scripts/dev-harness/spikes/state-literal-link/measure.sh --clean "
                  "(probe.cpp's --clean mode, run under gdb on a private bus; judge.py's corpus: a hand-written "
                  "list and 400 seeded random paths). The helper's qt_clean_path reimplements it -- QSaveFile "
                  "cleans each hop of a state.json link with it -- and tests/test_state_literal_link.py holds it "
                  "to every pair. Regenerate it with that command when Qt changes, and read the diff."),
        "qt": qt_version,
        "pairs": pairs,
    }
    json.dump(document, sys.stdout, ensure_ascii=True, indent=1)
    sys.stdout.write("\n")
    return 0


def main(argv):
    if argv[:1] == ["before"] and len(argv) == 4:
        before(*argv[1:])
        return 0
    if argv[:1] == ["after"] and len(argv) == 6:
        return after(*argv[1:])
    if argv == ["corpus"]:
        corpus()
        return 0
    if argv[:1] == ["fixture"] and len(argv) == 3:
        return fixture(*argv[1:])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
