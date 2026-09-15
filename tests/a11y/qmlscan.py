"""Scan a QML file for its accessibility-bearing declarations and the exact
element each one is attached to.

Why this exists
---------------
The AT-SPI harness cannot instantiate `Guide.qml` as it ships: the content
lives inside a Quickshell `PanelWindow`, and no window Quickshell creates
publishes an accessibility tree at all (docs/ACCESSIBILITY-INVESTIGATION.md
section 6). So the harness grades a GENERATED COPY of the guide, hoisted into a
plain hidden `QQuickWindow`. A copy can drift from what ships, and a harness
grading a drifted copy is a subtler version of the grep it replaces.

`fidelity.py` uses this module to assert the copy still carries every
accessibility-bearing declaration the shipping file has, attached at the same
point. A hash comparison cannot do that job, because the copy is deliberately
different.

What counts as "accessibility-bearing"
--------------------------------------
Two things, and the second one is the one a naive guard misses:

1. Every `Accessible.<property>` binding, and every `Accessible.announce(`
   call site.
2. Every OTHER binding declared on the same element as one of those, because
   Qt derives accessibility from more than the `Accessible` attached property.
   The credential leak this whole round is about (D-A11Y-1) is published from
   the field's `text:` binding, not from anything spelled `Accessible.`; the
   prototype harness's own mutation 7 rewrites exactly that line in the copy.
   An element that carries a role and a name is an accessible node, and every
   declaration on it is part of what the bus will say.

Attachment point
----------------
Each record carries the chain of enclosing QML object declarations, innermost
last, as `Type#id` when the object declares an id and `Type[n]` (index among
same-type siblings) when it does not. A block of JS or a grouped property
(`anchors { ... }`) is not an object; it appears as `{}` so that a declaration
somewhere it has no business being is visible rather than silently flattened.

Deliberate limits, because a guard that lies about its reach is worse than no
guard:

- This is a structural scanner, not a QML parser. It resolves no bindings, so
  two declarations that differ only in an expression this file cannot evaluate
  compare as text.
- It cannot see accessibility that comes from a TYPE rather than a
  declaration: a `qs.Ui` component or a QtQuick Controls `TextField` publishes
  a role of its own. What it does assert is that the type name in the
  attachment path is unchanged, so a copy that swaps the control out is red.
- A regex literal in JS (`/.../`) is not lexed. The repo has none in QML
  today; if one appears, `scan()` raises rather than mis-parsing, which is the
  intended failure direction.

Stdlib only, ASCII only (CLAUDE.md rules 3 and 8).
"""

import re


class QmlParseError(Exception):
    """The scanner refuses to guess. Raised rather than returning a wrong tree."""


# A QML object declaration header: `Rectangle {`, `delegate: BorderSurface {`,
# `Behavior on x { ... }`. Type names are capitalised; property bindings,
# function bodies and JS blocks are not object declarations and get no frame.
_OBJECT_HEADER = re.compile(r"([A-Z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\s*$")
_BEHAVIOR_HEADER = re.compile(
    r"([A-Z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\s+on\s+[A-Za-z_][A-Za-z0-9_.]*\s*$")

# Statement-level tokens. `id` and a binding name are only meaningful at the
# start of a statement, which is what the preceding-character test enforces.
_TOKEN = re.compile(r"""
    (?P<open>\{)
  | (?P<close>\})
  | (?P<announce>\bAccessible\.announce\s*\()
  | (?P<bind>(?P<name>[A-Za-z_][A-Za-z0-9_.]*)\s*:)
""", re.VERBOSE)

_STATEMENT_START = set("{};\n")
# A property declaration is still a statement start; its type words sit
# between the boundary and the name.
_PROPERTY_HEADER = re.compile(
    r"^(?:default\s+|required\s+|readonly\s+)*property\s+"
    r"(?:alias|[A-Za-z_][A-Za-z0-9_.<>]*)\s*$")
# An expression continued on the next line starts with one of these.
_CONTINUATION = ("?", ":", "+", "-", "*", "/", "%", "&", "|", ".", ",",
                 ")", "]", "}", "=", "<", ">", "!")


def blank_noncode(text):
    """Return `text` with comments and string CONTENTS blanked, same length.

    Length preserving on purpose: every offset computed against the blanked
    text indexes the real text, so values are read from the source while
    braces, colons and quotes inside comments and strings are invisible.
    """
    out = list(text)
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        elif c in "\"'`":
            quote = c
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == quote:
                    break
                if text[j] == "\n" and quote != "`":
                    raise QmlParseError(
                        "unterminated string literal at offset %d" % i)
                j += 1
            if j >= n:
                raise QmlParseError("unterminated string literal at offset %d" % i)
            for k in range(i + 1, j):
                if out[k] != "\n":
                    out[k] = "X"
            i = j + 1
        else:
            i += 1
    return "".join(out)


class _Frame(object):
    def __init__(self, type_name, parent):
        self.type_name = type_name
        self.id = None
        self.parent = parent
        self.kids = {}
        self.ordinal = 0
        self.bindings = []          # [(name, value, line)]
        self.accessible = []        # indexes into self.bindings
        if parent is not None and type_name is not None:
            parent.kids[type_name] = parent.kids.get(type_name, 0) + 1
            self.ordinal = parent.kids[type_name]

    def label(self):
        if self.type_name is None:
            return "{}"
        if self.id:
            return "%s#%s" % (self.type_name, self.id)
        return "%s[%d]" % (self.type_name, self.ordinal)


def _path(frame):
    """Innermost-last chain, excluding the synthetic file-level frame."""
    parts = []
    f = frame
    while f is not None and f.parent is not None:
        parts.append(f.label())
        f = f.parent
    parts.reverse()
    return "/".join(parts)


def _header_before(clean, pos):
    """The text between the previous statement boundary and `pos`."""
    k = pos - 1
    while k >= 0 and clean[k] not in _STATEMENT_START:
        k -= 1
    return clean[k + 1:pos]


def _value_end(clean, start):
    """Where the expression beginning at `start` ends.

    Follows bracket depth, and follows a line break when the next line opens
    with a continuation operator or when nothing has been read yet. That is
    what carries the multi-line ternary at Guide.qml:3223 and the multi-line
    call argument at Guide.qml:2452.
    """
    n = len(clean)
    depth = 0
    i = start
    while i < n:
        c = clean[i]
        if c in "([{":
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return i
            depth -= 1
        elif c == "\n" and depth == 0:
            if clean[start:i].strip() == "":
                i += 1
                continue
            j = i + 1
            while j < n:
                line_end = clean.find("\n", j)
                line_end = n if line_end < 0 else line_end
                nxt = clean[j:line_end].strip()
                if nxt == "":
                    j = line_end + 1
                    continue
                if nxt.startswith(_CONTINUATION):
                    break
                return i
            else:
                return i
            i += 1
            continue
        elif c == ";" and depth == 0:
            return i
        i += 1
    return n


def _normalise(value):
    return re.sub(r"\s+", " ", value).strip()


def scan(text, filename="<qml>"):
    """Return (records, frames).

    `records` is an ordered list of dicts:
        path      attachment chain, e.g. "Item#root/Window#panel/BorderSurface#card"
        kind      "accessible" for an Accessible.* binding or announce() call,
                  "sibling" for another binding on an element that has one
        prop      "Accessible.name", "text", "Keys.forwardTo", ...
        value     the normalised right-hand side ("" for an announce call)
        line      1-based line number in `text`
    `frames` is the list of every typed object frame, for callers that need to
    ask a structural question (fidelity.py asks which frame is the window).
    """
    clean = blank_noncode(text)
    if clean.count("{") != clean.count("}"):
        raise QmlParseError("%s: unbalanced braces after blanking comments and "
                            "strings (%d open, %d close)"
                            % (filename, clean.count("{"), clean.count("}")))
    line_of = [0] * (len(clean) + 1)
    ln = 1
    for i, c in enumerate(clean):
        line_of[i] = ln
        if c == "\n":
            ln += 1
    line_of[len(clean)] = ln

    root = _Frame(None, None)
    root.type_name = None
    stack = [root]
    frames = []
    pending_type = None
    pos = 0
    n = len(clean)
    while pos < n:
        m = _TOKEN.search(clean, pos)
        if not m:
            break
        pos = m.end()
        if m.group("open"):
            header = _header_before(clean, m.start())
            hm = _OBJECT_HEADER.search(header) or _BEHAVIOR_HEADER.search(header)
            type_name = hm.group(1) if hm else None
            frame = _Frame(type_name, stack[-1])
            if type_name is not None:
                frames.append(frame)
            stack.append(frame)
            continue
        if m.group("close"):
            if len(stack) == 1:
                raise QmlParseError("%s: stray '}' at line %d"
                                    % (filename, line_of[m.start()]))
            stack.pop()
            continue
        before = _header_before(clean, m.start()).strip()
        prefix = ""
        if before != "":
            if _PROPERTY_HEADER.match(before):
                prefix = before + " "
            else:
                # Not at statement start: a ternary's `:`, an object literal
                # key, a label. `isHeader ? Accessible.Heading :
                # Accessible.ListItem` must not read as a declaration of
                # `Accessible.Heading`.
                continue
        frame = stack[-1]
        if m.group("announce"):
            frame.bindings.append(("Accessible.announce()", "", line_of[m.start()]))
            frame.accessible.append(len(frame.bindings) - 1)
            continue
        name = m.group("name")
        end = _value_end(clean, m.end())
        value = _normalise(text[m.end():end])
        if name == "id" and not prefix and frame.type_name is not None \
                and frame.id is None:
            frame.id = value
        frame.bindings.append((prefix + name, value, line_of[m.start()]))
        if name.startswith("Accessible."):
            frame.accessible.append(len(frame.bindings) - 1)

    if len(stack) != 1:
        raise QmlParseError("%s: %d unclosed block(s) at end of file"
                            % (filename, len(stack) - 1))

    records = []
    for frame in frames:
        if not frame.accessible:
            continue
        path = _path(frame)
        for index, (name, value, line) in enumerate(frame.bindings):
            records.append({
                "path": path,
                "kind": "accessible" if index in frame.accessible else "sibling",
                "prop": name,
                "value": value,
                "line": line,
            })
    return records, frames


def projection(text, filename="<qml>"):
    """The comparable form: one line per record, ordered as declared."""
    records, _frames = scan(text, filename)
    return ["%s | %s | %s = %s" % (r["path"], r["kind"], r["prop"], r["value"])
            for r in records]
