#!/usr/bin/env python3
"""No shipped QML file writes a metric as a number without saying why
(F-GATE-24, 2026-11-19).

WHY. Engineering constraint 1 says every metric comes from the theme's
`Style.*`, and docs/UX.md 5.9 names them: no pixel size, corner radius, gap
or border width as a number. The colour half of that list has had a guard
since F-GATE-17 (check-color-literals.py); this half was graded by nothing,
so a `font.pixelSize: 13` would have shipped green and drawn the same size
on every theme and every display scale.

WHAT IS A METRIC HERE. A number cannot say what it measures, so the NAME it
is bound to has to. Read from the code tokens of each file (the tokenizer
of check-model-members.py: comments and strings skipped), a metric binding
is a binding (`name: ...`), an assignment (`name = ...`) or a property
declaration whose name -- its last word -- is

  * `pixelSize` or `pointSize`;
  * `radius`, `spacing`, `padding`, `margins`, or any name that ends in
    Radius, Spacing, Padding, Margin, Margins, Inset or Gap
    (`anchors.leftMargin`, `rowSpacing`, `cornerRadius`);
  * `width` directly under `border` (`border.width:`, `border { width: }`);
  * for a property DECLARATION only (`property int rowHeight: ...`), a name
    that ends in Height or Width as well. A plain `width:` or `height:`
    binding is not judged: a count, a ratio and a pixel size all bind
    there and the name does not tell them apart. (Not Size: the service's
    `preparedLruSize` is a count.)

WHAT IS REFUSED. In the expression such a name is bound to, a number other
than zero is a hardcoded metric unless it is

  * an argument of a `Style.` call (`Style.space(8)`: the theme's own
    spacing unit, scaled by the host);
  * a factor: directly beside `*` or `/` (`width / 2`, `height * 0.42`);
  * one side of a comparison (`count > 1 ? Style.space(2) : 0`), or an
    index (`sizes[1]`);

and an expression made of numbers alone is refused whatever its
arithmetic. Zero is never a metric: it is the absence of one.

THE EXCEPTION. As for colours: `CONVENTION-EXCEPTION` in a `//` comment on
the number's own line or in the unbroken run of `//` comment lines directly
above it. The comment says why; the guard does not judge the reason.

WHAT IT DOES NOT SEE (stated, rule 14): a size bound to `width`, `height`,
`x` or `y`; a metric a function returns or the `.mjs` model computes; a
number passed to a function of the plugin's own (`root.scaled(12)` IS
refused, `scaled(n)` called with a variable is not followed). A ternary
broken so that its middle operand starts a line reads that operand as a
name, and misses, as the colour guard's does.

With no FILE, the .qml entries of ALLOWLIST in scripts/release.py. Exit 0
clean, 1 on a problem, 2 when a file or the allowlist cannot be read.
"""
import argparse
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


colours = _load("check_color_literals", "check-color-literals.py")
theme = colours.theme
members = colours.members
EXCEPTION = colours.EXCEPTION

METRIC_NAME = re.compile(r"^(?:pixelSize|pointSize|radius|spacing|padding|margins"
                         r"|\w*(?:Radius|Spacing|Padding|Margin|Margins|Inset|Gap))$")
DECLARED_ONLY = re.compile(r"^\w*(?:Height|Width)$")
FACTORS = frozenset(("*", "/"))
OPENERS = frozenset(("(", "[", "{"))
CLOSERS = frozenset((")", "]", "}"))
# A token that, ending a line or starting the next, carries an expression
# on. The tokenizer hands every operator over one character at a time
# (`===` is three `=`), `?.` excepted.
CONTINUES = frozenset(("+", "-", "*", "/", "%", "?", ":", ",", "&", "|", "<", ">", "=", ".", "?.", "(", "["))


def is_punct(tok, texts):
    return tok is not None and tok.kind == "punct" and tok.text in texts


def compared(toks, start, end, j):
    """Is the number toks[j] one side of a comparison: `<`, `>`, `<=`,
    `>=`, `==`, `===`, `!=` or `!==` directly before or after it?"""
    prev = toks[j - 1] if j > start else None
    if is_punct(prev, ("<", ">")):
        return True
    if is_punct(prev, ("=",)) and j - 2 >= start and is_punct(toks[j - 2], ("=", "!", "<", ">")):
        return True
    after = toks[j + 1] if j + 1 < end else None
    if is_punct(after, ("<", ">")):
        return True
    return is_punct(after, ("=", "!")) and j + 2 < end and is_punct(toks[j + 2], ("=",))


def groups(toks):
    """For each token, the word before the `{` that directly encloses it
    (`border` inside `border { ... }`), or None."""
    out, stack = [], []
    for k, t in enumerate(toks):
        if is_punct(t, ("}",)) and stack:
            stack.pop()
        out.append(stack[-1] if stack else None)
        if is_punct(t, ("{",)):
            stack.append(toks[k - 1].text if k and toks[k - 1].kind == "ident" else None)
    return out


def statement_name(toks, k, group):
    """When a statement's name starts at toks[k] -- a run of words and dots
    on one line, ended by `:` or `=` -- (the index after that sign, the
    metric's name or None, whether it is a declaration). None when no name
    starts here."""
    before = toks[k - 1] if k else None
    if before is not None and before.line == toks[k].line and not is_punct(before, ("{", ";", ",", "}")):
        return None
    j = k
    words = []
    while j < len(toks) and toks[j].line == toks[k].line and (toks[j].kind == "ident" or is_punct(toks[j], (".",))):
        if toks[j].kind == "ident":
            words.append(toks[j].text)
        j += 1
    if not words or j >= len(toks) or not is_punct(toks[j], (":", "=")):
        return None
    if toks[j].text == "=" and is_punct(toks[j + 1] if j + 1 < len(toks) else None, ("=", ">")):
        return None  # `==`, `===` and an arrow are not an assignment
    declared = "property" in words[:-1]
    name = words[-1]
    under_border = (len(words) >= 2 and words[-2] == "border") or (len(words) == 1 and group == "border")
    if METRIC_NAME.match(name) or (name == "width" and under_border) or (declared and DECLARED_ONLY.match(name)):
        shown = ".".join(words[-2:]) if under_border and len(words) >= 2 else ("border.width" if under_border else name)
        return j + 1, shown, declared
    return j + 1, None, declared


def expression_end(toks, start):
    """The index one past the expression that starts at toks[start]: it ends
    at a `;`, a `,` or a closing bracket of an outer level, or at a new line
    that nothing carries the expression onto."""
    depth = 0
    j = start
    while j < len(toks):
        t = toks[j]
        if is_punct(t, OPENERS):
            depth += 1
        elif is_punct(t, CLOSERS):
            if depth == 0:
                return j
            depth -= 1
        elif depth == 0:
            if is_punct(t, (";", ",")):
                return j
            if j > start and t.line > toks[j - 1].line and not is_punct(toks[j - 1], CONTINUES) \
                    and not is_punct(t, CONTINUES):
                return j
        j += 1
    return j


def in_style_call(toks, start, k):
    """Is toks[k] inside the argument list of a call whose callee starts
    with `Style.`, opened at or after toks[start]?"""
    depth = 0
    j = k - 1
    while j >= start:
        t = toks[j]
        if is_punct(t, (")", "]", "}")):
            depth += 1
        elif is_punct(t, ("(", "[", "{")):
            if depth > 0:
                depth -= 1
            elif t.text == "(":
                c = j - 1
                while c - 2 >= start and toks[c].kind == "ident" and is_punct(toks[c - 1], (".",)) \
                        and toks[c - 2].kind == "ident":
                    c -= 2
                if c < j - 1 and toks[c].kind == "ident" and toks[c].text == "Style":
                    return True
        j -= 1
    return False


def in_index(toks, start, k):
    """Is toks[k] directly inside `[ ... ]` opened at or after toks[start]?"""
    depth = 0
    j = k - 1
    while j >= start:
        t = toks[j]
        if is_punct(t, CLOSERS):
            depth += 1
        elif is_punct(t, OPENERS):
            if depth == 0:
                return t.text == "["
            depth -= 1
        j -= 1
    return False


def is_zero(text):
    try:
        return float(text) == 0
    except ValueError:
        try:
            return int(text, 0) == 0
        except ValueError:
            return False


def metric_literals(text):
    """(bindings, found): how many metric bindings the file holds, and
    [(line, col, name, number, why)] for every hardcoded number in one."""
    toks = members.tokens(text)
    inside = groups(toks)
    found = []
    bindings = 0
    k = 0
    while k < len(toks):
        if toks[k].kind != "ident":
            k += 1
            continue
        named = statement_name(toks, k, inside[k])
        if named is None:
            k += 1
            continue
        start, name, _declared = named
        if name is None:
            k = start
            continue
        end = expression_end(toks, start)
        bindings += 1
        body = toks[start:end]
        alone = not any(t.kind in ("ident", "str", "tmpl") for t in body)
        for j in range(start, end):
            t = toks[j]
            if t.kind != "num" or is_zero(t.text):
                continue
            prev = toks[j - 1] if j > start else None
            after = toks[j + 1] if j + 1 < end else None
            if alone:
                found.append((t.line, t.col, name, t.text, "a number alone"))
                continue
            if is_punct(prev, FACTORS) or is_punct(after, FACTORS):
                continue
            if compared(toks, start, end, j):
                continue
            if in_style_call(toks, start, j) or in_index(toks, start, j):
                continue
            found.append((t.line, t.col, name, t.text, "a number added to, or set beside, the theme's value"))
        k = start
    return bindings, found


def judge(label, text):
    """-> (problems, counts) for one file's text. counts is a dict with
    'bindings' (metric bindings read), 'numbers' (hardcoded numbers found)
    and 'excused'."""
    lines = text.split("\n")
    bindings, found = metric_literals(text)
    problems = []
    counts = {"bindings": bindings, "numbers": len(found), "excused": 0}
    for line, col, name, number, why in found:
        if colours.excused(lines, line):
            counts["excused"] += 1
        else:
            problems.append("%s:%d:%d: `%s` is given the number %s (%s) with no %s comment: take the metric from "
                            "the theme (Style.space(n), Style.spacing.*, Style.font.*), or say on the line above "
                            "why this one cannot be" % (label, line, col, name, number, why, EXCEPTION))
    return problems, counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", default=theme.repo_root())
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    try:
        files = args.files or theme.allowlisted_qml(args.root)
    except (OSError, ValueError, SyntaxError) as exc:
        print("metric literal guard: cannot read the allowlist: %s" % exc)
        return 2
    if not files:
        print("metric literal guard: no QML file to read")
        return 2
    problems = []
    total = {"bindings": 0, "numbers": 0, "excused": 0}
    for path in files:
        try:
            text = theme.read(path)
            found, counts = judge(os.path.relpath(path, args.root), text)
        except (OSError, UnicodeDecodeError, members.ScanError) as exc:
            print("metric literal guard: cannot read %s: %s" % (path, exc))
            return 2
        problems.extend(found)
        for key in total:
            total[key] += counts[key]
    for line in problems:
        print(line)
    print("metric literal guard: %d metric binding(s) read in %d file(s) (%d hardcoded number(s), %d excused), "
          "%d problem(s)" % (total["bindings"], len(files), total["numbers"], total["excused"], len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
