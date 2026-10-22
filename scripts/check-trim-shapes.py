#!/usr/bin/env python3
"""Refuse two known-bad trim shapes in the shipped JavaScript and QML.

WHY (D-PERF-3, ruling R30g, 2026-10-21). The model trimmed provider text --
the whole channels.json before JSON.parse, every channel name, every group on
every browse pass -- with `/\\s+$/` and `/^\\s+|\\s+$/g`. An unanchored
`\\s+$` is retried from every position of a whitespace run and backs out of
the rest of the run each time, so its cost is quadratic in the run, on the
shell's main thread, and the helper keeps interior runs in names, groups,
tvg-ids and stream URLs. F-SINK-11 had fixed the same shape in the two URL
redactors and nothing looked for it anywhere else. The replacements are the
engine's own `trim()` and the model's index walks (Model.trimEndSpace,
Model.trimEdgeSpace).

And the obvious replacement for a TRAILING trim is a trap: Qt 6.11.2's V4,
the engine the shell runs, has NO String.prototype.trimEnd or trimStart
(measured offscreen, tests/test_proto_v4.py pins it). Node has both, so a
model calling them passes every node check and throws in the shell.

THIS IS A GUARD AGAINST TWO KNOWN-BAD SHAPES, NOT AN ACCEPTANCE CRITERION
(CLAUDE.md rule 14). What shows the bound is the arithmetic and the
equivalence tests; what this does is stop the shape coming back by habit:
  1. a call to `.trimEnd(`, `.trimStart(`, `.trimLeft(` or `.trimRight(`;
  2. a regex literal with an alternative that is NOT anchored by `^` and ends
     in a quantified whitespace atom before `$`: `\\s+$`, `\\s*$`, or a class
     holding `\\s`, a space or `\\u00a0` under `+` or `*` before `$`.
An alternative anchored at `^` is tried at one position only, so `^\\s+$` and
`/^[0-9]+$/` pass. Lines that are comments (`//`, `*`) are not code and are
not read.

WHAT IT SCANS. Model.mjs, model/*.mjs and every .qml entry of ALLOWLIST in
scripts/release.py (read with ast, nothing in release.py runs). `--root DIR`
scans another tree (the red run against the code before the change); FILE
arguments scan exactly those files.

Exit 0 and one summary line ("trim shape guard: N file(s), M regex
literal(s), 0 problem(s)") when clean; exit 1 with file:line: reason for each
problem otherwise. ASCII only (CLAUDE.md rule 8). Not shipped.
"""
import ast
import glob
import os
import re
import sys

NATIVE_ONE_SIDED = re.compile(r"\.(trimEnd|trimStart|trimLeft|trimRight)\s*\(")
# A `/` that opens a regex literal: after one of these, or at the line start.
REGEX_OPENERS = "(,=:!&|?{};[+-*%<>~^"


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def allowlisted_qml(root):
    path = os.path.join(root, "scripts", "release.py")
    with open(path, "r", encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), path)
    for node in tree.body:
        if isinstance(node, ast.Assign) and "ALLOWLIST" in [t.id for t in node.targets if isinstance(t, ast.Name)]:
            return [os.path.join(root, e) for e in ast.literal_eval(node.value) if e.endswith(".qml")]
    raise ValueError("%s has no ALLOWLIST assignment" % path)


def scanned_files(root):
    files = [os.path.join(root, "Model.mjs")] + sorted(glob.glob(os.path.join(root, "model", "*.mjs")))
    return files + allowlisted_qml(root)


def regex_literals(line):
    """Every `/pattern/flags` that opens where a regex literal can open,
    skipping string literals and stopping at a `//` comment."""
    out = []
    i = 0
    n = len(line)
    quote = None
    prev = ""
    while i < n:
        c = line[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "\"'`":
            quote = c
            prev = c
            i += 1
            continue
        if c == "/" and i + 1 < n and line[i + 1] == "/":
            break
        if c == "/" and (prev == "" or prev in REGEX_OPENERS or line[:i].rstrip().endswith("return")):
            j = i + 1
            in_class = False
            while j < n:
                d = line[j]
                if d == "\\":
                    j += 2
                    continue
                if d == "[":
                    in_class = True
                elif d == "]":
                    in_class = False
                elif d == "/" and not in_class:
                    break
                j += 1
            if j >= n:
                break
            out.append(line[i + 1:j])
            i = j + 1
            while i < n and line[i].isalpha():
                i += 1
            prev = "/"
            continue
        if not c.isspace():
            prev = c
        i += 1
    return out


def alternatives(pattern):
    """Top-level `|` alternatives (not inside a class or a group)."""
    parts = []
    depth = 0
    in_class = False
    start = 0
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "\\":
            i += 2
            continue
        if in_class:
            if c == "]":
                in_class = False
        elif c == "[":
            in_class = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == "|" and depth == 0:
            parts.append(pattern[start:i])
            start = i + 1
        i += 1
    parts.append(pattern[start:])
    return parts


TRAILING_SPACE = re.compile(r"(\\s|\[[^\]]*(\\s| |\\u00a0)[^\]]*\])[+*]\$$")


def bad_trailing_trim(pattern):
    for alt in alternatives(pattern):
        if not alt.startswith("^") and TRAILING_SPACE.search(alt):
            return alt
    return None


def scan(files):
    problems = []
    literals = 0
    for path in files:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().split("\n")
        for number, line in enumerate(lines, 1):
            code = line.strip()
            if code.startswith("//") or code.startswith("*") or code.startswith("/*"):
                continue
            m = NATIVE_ONE_SIDED.search(line)
            if m:
                problems.append("%s:%d: .%s() does not exist in Qt 6.11.2's V4 (use Model.trimEndSpace or trim())"
                                % (path, number, m.group(1)))
            for pattern in regex_literals(line):
                literals += 1
                alt = bad_trailing_trim(pattern)
                if alt is not None:
                    problems.append("%s:%d: /%s/ -- the alternative `%s` is a trailing-whitespace trim that is "
                                    "quadratic in a whitespace run (use trim(), Model.trimEndSpace or Model.trimEdgeSpace)"
                                    % (path, number, pattern, alt))
    return problems, literals


def main(argv):
    root = repo_root()
    files = []
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--root":
            root = os.path.abspath(args.pop(0))
        else:
            files.append(os.path.abspath(a))
    if not files:
        files = scanned_files(root)
    problems, literals = scan(files)
    for p in problems:
        print(p)
    print("trim shape guard: %d file(s), %d regex literal(s), %d problem(s)" % (len(files), literals, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
