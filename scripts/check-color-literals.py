#!/usr/bin/env python3
"""No shipped QML file writes a colour as a literal without saying why
(F-GATE-17, 2026-11-16).

WHY. Engineering constraint 1 says every colour comes from the theme
(`Commons.Color.*`, or the bar's own tokens), and that a literal needs a
`CONVENTION-EXCEPTION` comment. docs/UX.md 5.9 names the literals: any hex
colour, "white", "black", a `Qt.rgba(...)` of numbers. The theme-name half
of the constraint has had a guard since D-HOST-9 (check-theme-names.py);
this half was graded by a grep in docs/QA.md (TC-UI-06) that nobody ran, so
a hex literal would have shipped green.

WHAT IS A COLOUR LITERAL HERE. Read from the code tokens of each file (the
tokenizer of check-model-members.py: comments skipped, a template's `${...}`
read as code), so a colour named in a comment is not one:

  1. a quoted string that is a hex colour as Qt reads one -- `#` and 3, 4,
     6, 8, 9 or 12 hex digits -- ANYWHERE in the file;
  2. the quoted strings "white" and "black", ANYWHERE (UX 5.9 names them);
  3. any other SVG colour name ("red", "tan", "gold", ...) where the code
     says it is a colour: in a binding or an assignment whose line names a
     property ending in `color` (`color:`, `border.color:`, `fooColor =`,
     `property color x:`), or as an argument of a `Qt.*` call
     (`Qt.darker("red")`). Elsewhere such a word is a word;
  4. a `Qt.rgba(...)`, `Qt.hsla(...)` or `Qt.hsva(...)` call whose arguments
     are all numbers. `Qt.rgba(c.r, c.g, c.b, 0.4)` is a
     theme colour with an alpha, not a literal.

"transparent" is counted and never refused. It is the absence of paint, not
a colour a theme could supply: the host's own theme has no token for it
(its `Color.qml` answers the role "transparent" with `Qt.rgba(0, 0, 0, 0)`),
44 of the host's own files write the string, and UX 5.9 does not list it.
The lead's call under the owner's standing authority of 2026-11-09, as the
board row left it; to overturn it, remove the name from NO_PAINT.

THE EXCEPTION. A literal is excused by `CONVENTION-EXCEPTION` in a `//`
comment on its own line or in the unbroken run of `//` comment lines
directly above it. The comment says why; the guard does not judge the
reason.

WHAT IT DOES NOT SEE (stated, rule 14): a colour name other than white and
black that a function RETURNS or a model computes, since nothing on the line
says colour; a colour built from pieces (`"#" + hex`); the `.mjs` model,
which is read by no part of this guard (it holds no hex string today). A
ternary broken so that its middle operand starts a line (`cond ?` / `a :` /
`"red"`) reads that operand as the binding's name, and misses.
Metrics are not this guard's: the constraint's other literal, a pixel size
that should be `Style.*`, has no check yet (F-GATE-24).

With no FILE, the .qml entries of ALLOWLIST in scripts/release.py. Exit 0
clean, 1 on a problem, 2 when a file or the allowlist cannot be read.
"""
import argparse
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

_spec = importlib.util.spec_from_file_location("check_theme_names", os.path.join(HERE, "check-theme-names.py"))
theme = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(theme)
members = theme.members

HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8}|[0-9a-fA-F]{9}|[0-9a-fA-F]{12})$")
NO_PAINT = frozenset(("transparent",))
ANYWHERE = frozenset(("white", "black"))
# The SVG 1.0 colour keywords Qt's QColor accepts by name.
SVG_NAMES = frozenset("""
aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond
blue blueviolet brown burlywood cadetblue chartreuse chocolate coral
cornflowerblue cornsilk crimson cyan darkblue darkcyan darkgoldenrod darkgray
darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid
darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey
darkturquoise darkviolet deeppink deepskyblue dimgray dimgrey dodgerblue
firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold goldenrod
gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki
lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan
lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon
lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue
lightyellow lime limegreen linen magenta maroon mediumaquamarine mediumblue
mediumorchid mediumpurple mediumseagreen mediumslateblue mediumspringgreen
mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin
navajowhite navy oldlace olive olivedrab orange orangered orchid
palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru
pink plum powderblue purple red rosybrown royalblue saddlebrown salmon
sandybrown seagreen seashell sienna silver skyblue slateblue slategray
slategrey snow springgreen steelblue tan teal thistle tomato turquoise violet
wheat white whitesmoke yellow yellowgreen
""".split())
NUMERIC_CALLS = frozenset(("rgba", "hsla", "hsva"))
EXCEPTION = "CONVENTION-EXCEPTION"
COMMENT_LINE = re.compile(r"^\s*//")


def colour_named(name):
    return name.lower().endswith("color")


def in_qt_call(toks, k):
    """Is toks[k] inside the argument list of a `Qt.<name>(` call, at any
    depth of that call's own parentheses?"""
    depth = 0
    j = k - 1
    while j >= 0:
        t = toks[j]
        if t.kind == "punct":
            if t.text in (")", "]"):
                depth += 1
            elif t.text in ("(", "["):
                if depth == 0:
                    if (t.text == "(" and j >= 3 and toks[j - 1].kind == "ident"
                            and toks[j - 2].kind == "punct" and toks[j - 2].text == "."
                            and toks[j - 3].kind == "ident" and toks[j - 3].text == "Qt"):
                        return True
                else:
                    depth -= 1
            elif t.text in ("{", "}", ";") and depth == 0:
                return False
        j -= 1
    return False


def binding_names_colour(toks, k):
    """Does the binding or assignment toks[k] stands in name a colour? Walk
    back, without leaving the statement, to the nearest `name :` or `name =`
    that BEGINS a statement -- its name (dotted, or `property color x`, all
    on one line) is first on its line or follows `{`, `;` or `,` -- and ask
    every identifier of that name. A ternary's `a : b` follows something
    else and is passed over."""
    depth = 0
    j = k - 1
    while j >= 1:
        t = toks[j]
        if t.kind == "punct":
            if t.text in (")", "]"):
                depth += 1
            elif t.text in ("(", "["):
                if depth > 0:
                    depth -= 1
            elif t.text in ("{", "}", ";") and depth == 0:
                return False
            elif t.text in (":", "=") and depth == 0 and toks[j - 1].kind == "ident":
                start = j - 1
                while (start > 0 and toks[start - 1].line == toks[start].line
                       and (toks[start - 1].kind == "ident"
                            or (toks[start - 1].kind == "punct" and toks[start - 1].text == "."))):
                    start -= 1
                before = toks[start - 1] if start > 0 else None
                if (before is None or before.line != toks[start].line
                        or (before.kind == "punct" and before.text in ("{", ";", ","))):
                    return any(x.kind == "ident" and colour_named(x.text) for x in toks[start:j])
        j -= 1
    return False


def numeric_call_end(toks, k):
    """toks[k] is `Qt`. When it opens `Qt.rgba(` (or hsla, hsva) whose
    arguments hold no identifier and no string -- numbers and arithmetic
    alone -- return the call's name, else None."""
    if not (k + 3 < len(toks) and toks[k + 1].kind == "punct" and toks[k + 1].text == "."
            and toks[k + 2].kind == "ident" and toks[k + 2].text in NUMERIC_CALLS
            and toks[k + 3].kind == "punct" and toks[k + 3].text == "("):
        return None
    if k > 0 and toks[k - 1].kind == "punct" and toks[k - 1].text in (".", "?."):
        return None
    depth = 0
    seen_number = False
    for t in toks[k + 3:]:
        if t.kind == "punct" and t.text == "(":
            depth += 1
        elif t.kind == "punct" and t.text == ")":
            depth -= 1
            if depth == 0:
                return toks[k + 2].text if seen_number else None
        elif t.kind == "num":
            seen_number = True
        elif t.kind != "punct":
            return None
    return None


def excused(lines, line):
    """Is the literal on 1-based `line` covered by an exception comment: on
    its own line, or in the run of `//` comment lines directly above?"""
    own = lines[line - 1]
    cut = own.find("//")
    if cut >= 0 and EXCEPTION in own[cut:]:
        return True
    j = line - 2
    while j >= 0 and COMMENT_LINE.match(lines[j]):
        if EXCEPTION in lines[j]:
            return True
        j -= 1
    return False


def literals(text):
    """[(line, col, shown, kind)] for every colour literal in the code of
    one file. kind is 'hex', 'name', 'call' or 'none' (no paint)."""
    toks = members.tokens(text)
    out = []
    for k, t in enumerate(toks):
        if t.kind == "str":
            low = t.text.lower()
            if HEX.match(t.text):
                out.append((t.line, t.col, '"%s"' % t.text, "hex"))
            elif low in NO_PAINT:
                if binding_names_colour(toks, k) or in_qt_call(toks, k):
                    out.append((t.line, t.col, '"%s"' % t.text, "none"))
            elif low in ANYWHERE:
                out.append((t.line, t.col, '"%s"' % t.text, "name"))
            elif low in SVG_NAMES and (binding_names_colour(toks, k) or in_qt_call(toks, k)):
                out.append((t.line, t.col, '"%s"' % t.text, "name"))
        elif t.kind == "ident" and t.text == "Qt":
            name = numeric_call_end(toks, k)
            if name:
                out.append((t.line, t.col, "Qt.%s(...) of numbers" % name, "call"))
    return out


def judge(label, text):
    """-> (problems, counts) for one file's text. counts is a dict with
    'read' (every literal), 'none' (no paint) and 'excused'."""
    lines = text.split("\n")
    problems = []
    counts = {"read": 0, "none": 0, "excused": 0}
    for line, col, shown, kind in literals(text):
        counts["read"] += 1
        if kind == "none":
            counts["none"] += 1
        elif excused(lines, line):
            counts["excused"] += 1
        else:
            problems.append("%s:%d:%d: the colour literal %s has no %s comment: take the colour from the "
                            "theme (Commons.Color.*), or say on the line above why this one cannot be"
                            % (label, line, col, shown, EXCEPTION))
    return problems, counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", default=theme.repo_root())
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)
    try:
        files = args.files or theme.allowlisted_qml(args.root)
    except (OSError, ValueError, SyntaxError) as exc:
        print("colour literal guard: cannot read the allowlist: %s" % exc)
        return 2
    if not files:
        print("colour literal guard: no QML file to read")
        return 2
    problems = []
    total = {"read": 0, "none": 0, "excused": 0}
    for path in files:
        try:
            text = theme.read(path)
            found, counts = judge(os.path.relpath(path, args.root), text)
        except (OSError, UnicodeDecodeError, members.ScanError) as exc:
            print("colour literal guard: cannot read %s: %s" % (path, exc))
            return 2
        problems.extend(found)
        for key in total:
            total[key] += counts[key]
    for line in problems:
        print(line)
    print("colour literal guard: %d colour literal(s) read in %d file(s) (%d no-paint, %d excused), %d problem(s)"
          % (total["read"], len(files), total["none"], total["excused"], len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
