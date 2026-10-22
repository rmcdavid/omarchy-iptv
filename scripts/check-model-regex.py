#!/usr/bin/env python3
"""Refuse one KNOWN-BAD regex shape in the shipped JavaScript and QML: two
unbounded repeats over overlapping classes with nothing mandatory between
them.

WHY (D-PERF-11, ruling R32a'' and the round-4 lead decision, 2026-10-22).
`maskUrl` shipped `([^\\/?#]*)([^?#]*)(\\?[^#]*)?(#.*)?$` for a year: two
adjacent unbounded runs over classes that overlap on almost everything, so
when the tail failed (a line terminator after the `#`) the engine retried
every split of the two runs, about k*k/2 steps for k characters. Two lanes
hand-reviewed every regex in model/** and both cleared it; lane H2's helper
guard (scripts/check-helper-regex.py) grades exactly that shape by STRUCTURE
and would have refused it the day it was written -- but it reads only
bin/helper/*.py. This is that grader over the other language, so the shape
cannot come back by habit in the model, Service.qml or Guide.qml either.

THIS IS A GUARD AGAINST A KNOWN-BAD SHAPE, NOT AN ACCEPTANCE CRITERION
(CLAUDE.md rule 14). What shows a bound is arithmetic over the code and the
equivalence tests; what this does is refuse the one shape a reader has now
missed twice. The verdict is `super_linear_pairs` from the helper guard,
imported, not copied: two unbounded repeats (`*`, `+`, `{n,}`) over
single-character atoms whose character sets overlap, with nothing between
them the first run could not have taken (anchors, assertions, groups and
repeats that may match nothing, or single characters the first class also
matches). The D-EPG-12 shape (`\\s*(?:[-/]\\s*)?\\s*`) and the maskUrl shape
are both that.

WHAT IT READS AS A PATTERN: a regex literal; a `RegExp(...)` call, with
or without `new` (F-GATE-9: the two build the same object, and `RegExp("...")`
was a one-token evasion of a guard that looked for `new`); and a string
literal handed to `.match(`, `.search(` or `.matchAll(`, which the
language converts to a RegExp (F-GATE-9 again). A `.replace(` or `.split(`
with a string takes it LITERALLY and builds no pattern, so those are not
read. A `RegExp` call or a `.match`/`.search`/`.matchAll` whose argument is
a template literal is a problem (unreadable), and a `RegExp` call whose
argument is any other expression is listed in BUILT below with the reason it
is linear, or it is a problem; an expression nobody listed is a pattern
nobody read.

WHAT IT DOES NOT SEE, as the helper guard says of itself: a run with no
literal prefix searched from every position (D-EPG-8, F-SINK-11, D-PERF-6),
a nested unbounded repeat (`(a+)+`), a run hidden at the START of an optional
group (the walk looks at one sequence at a time), a string VARIABLE handed
to `.match`/`.search`/`.matchAll` (its value is read where it is built, if
it is a literal there, and not at all if it is composed), and a pattern
reaching a RegExp through any other call (`Reflect.construct`, a wrapper
function). The JavaScript pattern is read by Python's `re` parser after a
small translation (named groups, `[^]`, `\\/`, `\\u{...}`, the `i`/`s`/`m`
flags); the two engines' `\\s` differ by five code points, which cannot turn
a non-overlap into an overlap for the classes the model uses, and a pattern
the parser cannot read is a problem, not a pass. One sample character at a
time is the only input a pattern is ever run on here.

WHAT IT SCANS. The same files as scripts/check-trim-shapes.py (Model.mjs,
model/*.mjs, every .qml in ALLOWLIST), through its own scanner, so the two
guards cannot drift on what a regex literal is. Lines that are comments are
not code and are not read. `--root DIR` scans another tree (the red run
against the code before D-PERF-11); FILE arguments scan exactly those files.

Exit 0 and one summary line ("model regex guard: N file(s), M regex
literal(s), B built, 0 problem(s)") when clean -- B counts every `RegExp`
call and every string handed to `.match`/`.search`/`.matchAll` -- and exit 1
with file:line: reason for each problem otherwise. ASCII only (CLAUDE.md rule 8). Not shipped.
"""
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(HERE, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


trim = _load("check-trim-shapes")
helper_guard = _load("check-helper-regex")

# `new RegExp(<expression>)` sites whose pattern is not one string literal:
# the source text of the first argument, exactly as written, and why the
# pattern it builds is linear. An unlisted expression is a problem.
BUILT = {
    '"^" + GENERATED_NAME_WORD.toLowerCase() + " [0-9]+$"':
        "linear: anchored, a literal prefix, one digit run then $ (GENERATED_NAME_RE, text.mjs)",
}

# `RegExp(` with or without `new`, and not `.RegExp(` (a member) or
# `myRegExp(` (another name): F-GATE-9.
NEW_REGEXP = re.compile(r"(?<![\w$.])(?:new\s+)?RegExp\s*\(")
# A string handed to the three String methods that build a RegExp from it.
STRING_PATTERN_CALL = re.compile(r"\.(match|search|matchAll)\s*\(")
FLAG_BITS = {"i": re.IGNORECASE, "s": re.DOTALL, "m": re.MULTILINE}


def js_string_literal(text, i):
    """The JS string literal starting at text[i] (a quote): (value, end
    index after the closing quote), or None when text[i] opens none."""
    if i >= len(text) or text[i] not in "\"'":
        return None
    quote = text[i]
    out = []
    j = i + 1
    while j < len(text):
        c = text[j]
        if c == "\\":
            j += 1
            if j >= len(text):
                return None
            e = text[j]
            if e == "n":
                out.append("\n")
            elif e == "t":
                out.append("\t")
            elif e == "r":
                out.append("\r")
            elif e == "u" and j + 4 < len(text) and re.match(r"[0-9A-Fa-f]{4}", text[j + 1:j + 5]):
                out.append(chr(int(text[j + 1:j + 5], 16)))
                j += 4
            elif e == "x" and j + 2 < len(text) and re.match(r"[0-9A-Fa-f]{2}", text[j + 1:j + 3]):
                out.append(chr(int(text[j + 1:j + 3], 16)))
                j += 2
            elif e == "0":
                out.append("\x00")
            else:
                out.append(e)
            j += 1
            continue
        if c == quote:
            return "".join(out), j + 1
        out.append(c)
        j += 1
    return None


def argument_source(text, i):
    """The source of the first argument of a call whose `(` is at text[i-1]:
    up to the top-level `,` or the matching `)`."""
    depth = 0
    j = i
    quote = None
    while j < len(text):
        c = text[j]
        if quote:
            if c == "\\":
                j += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'`":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return text[i:j].strip()
            depth -= 1
        elif c == "," and depth == 0:
            return text[i:j].strip()
        j += 1
    return text[i:].strip()


def built_regexps(line):
    """Every `RegExp(...)` (with or without `new`) on a code line, and every
    `.match(`, `.search(` or `.matchAll(` handed a string or template
    literal: (pattern or None, flags, source of the first argument)."""
    out = []
    for m in NEW_REGEXP.finditer(line):
        i = m.end()
        while i < len(line) and line[i] in " \t":
            i += 1
        lit = js_string_literal(line, i)
        if lit is None:
            out.append((None, "", argument_source(line, i)))
            continue
        pattern, j = lit
        flags = ""
        rest = line[j:]
        fm = re.match(r"\s*,\s*([\"'])([a-z]*)\1", rest)
        if fm:
            flags = fm.group(2)
        out.append((pattern, flags, line[i:j]))
    for m in STRING_PATTERN_CALL.finditer(line):
        i = m.end()
        while i < len(line) and line[i] in " \t":
            i += 1
        if i >= len(line) or line[i] not in "\"'`":
            # A regex literal is read by the literal scanner; any other
            # expression (a variable, a call) is outside what this reads.
            continue
        lit = js_string_literal(line, i)
        if lit is None:
            out.append((None, "", argument_source(line, i)))
            continue
        pattern, j = lit
        out.append((pattern, "", line[i:j]))
    return out


def literal_flags(line, pattern, start):
    """The flag letters after the literal `/pattern/` found at or after
    `start` in `line`: (flags, index after them)."""
    needle = "/" + pattern + "/"
    k = line.find(needle, start)
    if k == -1:
        return "", start
    j = k + len(needle)
    f = j
    while f < len(line) and line[f].isalpha():
        f += 1
    return line[j:f], f


def to_python(pattern, flags):
    """A JavaScript pattern as Python's `re` reads it, and its flags."""
    p = pattern
    p = p.replace("(?<=", "\x00LB\x00").replace("(?<!", "\x00NLB\x00")
    p = re.sub(r"\(\?<([A-Za-z_$][\w$]*)>", r"(?P<\1>", p)
    p = p.replace("\x00LB\x00", "(?<=").replace("\x00NLB\x00", "(?<!")
    p = re.sub(r"\\k<([A-Za-z_$][\w$]*)>", r"(?P=\1)", p)
    p = p.replace("[^]", "[\\s\\S]").replace("\\/", "/")
    p = re.sub(r"\\u\{([0-9A-Fa-f]{1,6})\}", lambda m: "\\U%08x" % int(m.group(1), 16), p)
    bits = 0
    for ch in flags:
        bits |= FLAG_BITS.get(ch, 0)
    return p, bits


def grade(pattern, flags):
    """-> a problem string for the known-bad shape or an unreadable
    pattern, else None."""
    py, bits = to_python(pattern, flags)
    try:
        pairs = helper_guard.super_linear_pairs(py, bits)
    except (re.error, ValueError, TypeError, AttributeError, IndexError, OverflowError) as error:
        return "the guard could not walk /%s/%s (%s); read it by hand and say so here" % (pattern, flags, error)
    if pairs:
        first, second = pairs[0]
        return ("super-linear shape in /%s/%s: %s and %s are two unbounded repeats over overlapping classes "
                "with nothing between them the first could not take, so a run of k costs about k*k/2 "
                "(D-PERF-11, D-EPG-12); put a mandatory character the first class cannot hold between "
                "them, or walk the string by index" % (pattern, flags, first, second))
    return None


def scan(files):
    problems = []
    literals = 0
    built = 0
    for path in files:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.read().split("\n")
        for number, line in enumerate(lines, 1):
            code = line.strip()
            if code.startswith("//") or code.startswith("*") or code.startswith("/*"):
                continue
            at = 0
            for pattern in trim.regex_literals(line):
                literals += 1
                flags, at = literal_flags(line, pattern, at)
                problem = grade(pattern, flags)
                if problem:
                    problems.append("%s:%d: %s" % (path, number, problem))
            for pattern, flags, source in built_regexps(line):
                built += 1
                if pattern is None:
                    if source not in BUILT:
                        problems.append("%s:%d: RegExp(%s) (or a .match/.search/.matchAll of it) builds a pattern "
                                        "this guard cannot read; write it as a string literal, or list the expression "
                                        "in BUILT in scripts/check-model-regex.py with why it is linear"
                                        % (path, number, source))
                    continue
                problem = grade(pattern, flags)
                if problem:
                    problems.append("%s:%d: built pattern: %s" % (path, number, problem))
    return problems, literals, built


def main(argv):
    root = trim.repo_root()
    files = []
    args = list(argv)
    while args:
        a = args.pop(0)
        if a == "--root":
            root = os.path.abspath(args.pop(0))
        else:
            files.append(os.path.abspath(a))
    if not files:
        files = trim.scanned_files(root)
    problems, literals, built = scan(files)
    for p in problems:
        print(p)
    print("model regex guard: %d file(s), %d regex literal(s), %d built, %d problem(s)"
          % (len(files), literals, built, len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
