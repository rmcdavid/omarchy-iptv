#!/usr/bin/env python3
"""No shipped QML file uses a Qt type or member the host's load patch hides
(D-HOST-10, 2026-11-19).

WHY. Omarchy's own quickshell build rewrites a plugin's unversioned
`import QtQuick` to `import QtQuick 6.11` (D-HOST-9; its packager calls the
patch temporary), while qmllint, the dev harness, the a11y trees and every
plain `qml` run in the gate load the same file at the installed Qt's newest
version. A type first exported after 6.11, or a member revisioned after it,
therefore loads everywhere this project looks and fails to load on the host:
under `import QtQuick 6.11`, `Item { mutabilityGroup: 0 }` does not load at
all ('"Item.mutabilityGroup" is not available in QtQuick 6.11.', measured in
plain qml by rc-host9 on 2026-11-01). Nothing in the gate could see it.

THE RULE. Nothing is hard-coded. The rewrite is READ OUT OF the installed
quickshell (its pattern and its replacement, as tests/test_host_load_patch.py
reads them), each shipped file's imports are read twice -- as written, which
is what the gate loads, and as rewritten, which is what the host loads -- and
the installed qmldir and qmltypes files say what the first reading has that
the second lacks, following the imports a qmldir names (`import QtQml auto`
carries QtQuick's version down to QtQml and QtQml.Models):

  - a TYPE NAME the modules export as written and not as rewritten
    (QtQml.Models' `AllOfFilter`, QtQuick's own `Color`). Red wherever a
    shipped file writes it unqualified, or behind the alias of a Qt import.
    `Commons.Color` is the host kit's and is not judged, and neither is a
    name the file itself declares as an import's alias.
  - a MEMBER (property, signal, method) whose revision the rewritten import
    is too old for, and the handler names it gives (`onFinished`,
    `onLoopsChanged`). Read as source with check-model-members.py's
    tokenizer, so comments and strings are skipped. A binding key written
    directly in an element whose type the installed type files know is
    resolved through that type's prototype chain, and passes when the
    nearest member of that name is one the host does have: `loops:` in a
    NumberAnimation is Animation's, as old as QtQuick, while `loops:` in an
    AnimatedImage is 6.12's. Every other use of such a name -- a member
    access on anything, a bare identifier, a key in an element this cannot
    resolve, a declaration -- is red, because a source reading cannot say
    what the receiver is and the strict reading is the one that cannot ship
    a file the host refuses.

A use that is really something else says so:
    // QT-REVISION-EXCEPTION: <why this name is not Qt's hidden one>
on its line or in the `//` comment directly above.

It refuses to pass blind: no quickshell binary, a module with no qmldir, a
type file it cannot parse, a scanner that lost its place, and a rewrite that
changes no import line of any shipped file are all red. A quickshell that
carries no rewrite at all is green and says so: the host then loads what the
gate loads (tests/test_host_load_patch.py goes red that day on its own, as a
re-measurement request).

What it does not judge: an enum VALUE added to an old enum (the type files
carry no revision for values); a member reached from Model.mjs or another
script file; whether Qt applies a revision to an object no import names,
such as `Qt.styleHints` (read as hidden, the strict reading; not measured).

A code-behind of Service.qml (D-REL-14) has no imports of its own: it is
read under Service.qml's, as written and as rewritten, so a member it names
is judged by what the host loads Service.qml at, and it counts as a file the
rewrite reaches when Service.qml is one. An import that cannot be read is
reported once, on Service.qml, and leaves its code-behinds unjudged.

Usage: check-qt-revisions.py [--root ROOT] [--qml-dir DIR] [--quickshell BIN] [FILE ...]
With no FILE, scripts/release.py's shipped_code: the .qml entries of
ALLOWLIST and the code-behinds Service.qml declares. Exit 0
and a summary line when nothing hidden is used; 1 and one line per problem
otherwise. Python 3 standard library only.
"""

import argparse
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_QML_DIR = "/usr/lib/qt6/qml"
DEFAULT_QUICKSHELL = os.environ.get("OMARCHY_IPTV_QUICKSHELL", "/usr/bin/quickshell")
PRAGMA = "//@ pragma OmarchyLoadPatch"
MARKER = "QT-REVISION-EXCEPTION:"
MEMBER_KINDS = ("Property", "Signal", "Method")
# The engine imports these into every file whatever it writes.
ALWAYS = (("QML", None),)


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


theme = _load("check_theme_names", "check-theme-names.py")
members = theme.members
Unreadable = theme.Unreadable


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def rewrite_from_binary(path):
    """(pattern, replacement) of the installed quickshell's QtQuick import
    rewrite, or None when it carries none. The same reading as
    tests/test_host_load_patch.py's, which holds the two equal."""
    with open(path, "rb") as fh:
        data = fh.read()
    if PRAGMA.encode("ascii") not in data:
        return None
    runs = [m.group(0).decode("utf-16-le") for m in re.finditer(rb"(?:[\x20-\x7e]\x00){6,}", data)]
    patterns = [r for r in runs if "import" in r and "QtQuick" in r and r.startswith("^")]
    replacements = [r for r in runs if re.fullmatch(r"\\1 \d+\.\d+", r)]
    if len(patterns) != 1 or len(replacements) != 1:
        return None
    return re.compile(patterns[0]), replacements[0]


def rewritten(text, rewrite):
    """The file as the host hands it to the engine: the rewrite applied to
    each line, as the patched interceptor applies it."""
    pattern, replacement = rewrite
    return "\n".join(pattern.sub(replacement, line) for line in text.split("\n"))


# --- the installed type files ---------------------------------------------

TYPE_TOKEN = re.compile(
    r'[ \t\r\n]+|//[^\n]*|(?P<str>"(?:\\.|[^"\\])*")|(?P<num>-?\d+(?:\.\d+)?)'
    r'|(?P<ident>[A-Za-z_][\w.]*)|(?P<punct>[{}\[\]:;,])')


def type_tokens(text, label):
    out, i, n = [], 0, len(text)
    while i < n:
        m = TYPE_TOKEN.match(text, i)
        if m is None:
            raise Unreadable("%s: unreadable at line %d" % (label, text.count("\n", 0, i) + 1))
        i = m.end()
        if m.lastgroup == "str":
            out.append(("str", m.group("str")[1:-1]))
        elif m.lastgroup is not None:
            out.append((m.lastgroup, m.group(m.lastgroup)))
    return out


class Block(object):
    __slots__ = ("kind", "fields", "children")

    def __init__(self, kind):
        self.kind, self.fields, self.children = kind, {}, []


def parse_types(text, label):
    """The Component blocks of one qmltypes file, as Block trees."""
    toks = type_tokens(text, label)
    pos = [0]

    def fail(what):
        raise Unreadable("%s: %s at token %d" % (label, what, pos[0]))

    def value():
        kind, tok = toks[pos[0]]
        pos[0] += 1
        if kind == "punct" and tok == "[":
            items = []
            while True:
                if pos[0] >= len(toks):
                    fail("an unclosed list")
                kind, tok = toks[pos[0]]
                if kind == "punct" and tok == "]":
                    pos[0] += 1
                    return items
                if kind == "punct" and tok == ",":
                    pos[0] += 1
                    continue
                items.append(value())
        if kind == "punct" and tok == "{":
            # An object literal as a value: skipped, balanced.
            depth = 1
            while depth:
                if pos[0] >= len(toks):
                    fail("an unclosed object")
                kind, tok = toks[pos[0]]
                pos[0] += 1
                if kind == "punct" and tok == "{":
                    depth += 1
                elif kind == "punct" and tok == "}":
                    depth -= 1
            return None
        if kind == "punct":
            fail("a value was expected, not %r" % tok)
        return int(tok) if kind == "num" and re.fullmatch(r"-?\d+", tok) else tok

    def block(kind):
        b = Block(kind)
        while True:
            if pos[0] >= len(toks):
                fail("an unclosed %s" % kind)
            k, tok = toks[pos[0]]
            pos[0] += 1
            if k == "punct" and tok == "}":
                return b
            if k == "punct" and tok == ";":
                continue
            if k != "ident" or pos[0] >= len(toks):
                fail("a name was expected, not %r" % tok)
            k2, tok2 = toks[pos[0]]
            pos[0] += 1
            if k2 == "punct" and tok2 == "{":
                b.children.append(block(tok))
            elif k2 == "punct" and tok2 == ":":
                b.fields[tok] = value()
            else:
                fail("`{` or `:` was expected after %s" % tok)

    while pos[0] < len(toks):
        k, tok = toks[pos[0]]
        pos[0] += 1
        if k == "ident" and tok == "import":
            # `import QtQuick.tooling 1.2`: one name, then perhaps a version.
            if pos[0] < len(toks) and toks[pos[0]][0] == "ident":
                pos[0] += 1
            if pos[0] < len(toks) and toks[pos[0]][0] == "num":
                pos[0] += 1
            continue
        if k == "ident" and pos[0] < len(toks) and toks[pos[0]] == ("punct", "{"):
            pos[0] += 1
            root = block(tok)
            found = [c for c in root.children if c.kind == "Component"]
            if not found:
                raise Unreadable("%s: its %s block holds no Component" % (label, tok))
            return found
    raise Unreadable("%s: no Module block" % label)


def as_version(revision):
    """A member's `revision` as (major, minor): Qt writes major * 256 + minor,
    and a Qt 5 file's bare minor reads as major 0, older than any import."""
    return (revision >> 8, revision & 0xFF)


class Component(object):
    __slots__ = ("module", "name", "prototype", "exports", "members")


def module_components(uri, qml_dir, cache):
    """Every Component of the type files `uri`'s qmldir names."""
    if uri in cache:
        return cache[uri]
    d = os.path.join(qml_dir, *uri.split("."))
    qmldir = os.path.join(d, "qmldir")
    if not os.path.isfile(qmldir):
        raise Unreadable("%s: no qmldir at %s, so its types cannot be read" % (uri, qmldir))
    out = []
    for line in read(qmldir).split("\n"):
        w = line.split()
        if len(w) >= 2 and w[0] == "typeinfo":
            info = os.path.join(d, w[1])
            if not os.path.isfile(info):
                raise Unreadable("%s: its qmldir names typeinfo %s, which is not there" % (uri, info))
            for block in parse_types(read(info), info):
                c = Component()
                c.module = uri
                c.name = block.fields.get("name")
                c.prototype = block.fields.get("prototype")
                c.exports = []
                for e in block.fields.get("exports") or []:
                    m = theme.EXPORT.fullmatch('"%s"' % e)
                    if m:
                        c.exports.append((m.group("module"), m.group("name"),
                                          (int(m.group("major")), int(m.group("minor")))))
                c.members = []
                for child in block.children:
                    name = child.fields.get("name")
                    if child.kind in MEMBER_KINDS and isinstance(name, str):
                        revision = child.fields.get("revision")
                        version = as_version(revision) if isinstance(revision, int) else (0, 0)
                        c.members.append((child.kind, name, version))
                out.append(c)
    cache[uri] = out
    return out


def module_limits(uri, limit, qml_dir, out=None):
    """{module: limit} for everything `import <uri> <limit>` reaches through
    the qmldir imports, None being the newest. A module reached twice keeps
    the more permissive limit."""
    out = {} if out is None else out
    if uri in out and (out[uri] is None or (limit is not None and limit <= out[uri])):
        return out
    out[uri] = limit
    qmldir = os.path.join(qml_dir, *uri.split("."), "qmldir")
    if not os.path.isfile(qmldir):
        raise Unreadable("%s: no qmldir at %s, so its names cannot be read" % (uri, qmldir))
    imports, _types = theme.qmldir_entries(read(qmldir))
    for sub, version in imports:
        if version == "auto":
            sub_limit = limit
        elif version is None:
            sub_limit = None
        else:
            parts = version.split(".")
            sub_limit = (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        module_limits(sub, sub_limit, qml_dir, out)
    return out


def qt_imports(text):
    """(every Qt or Quickshell module import as (uri, limit), the aliases of
    those imports). The host's own `qs.*` modules are not Qt's to version."""
    unqualified, aliases, _directories = theme.file_imports(text)
    found = [(uri, limit) for uri, limit in unqualified if not uri.startswith("qs.")]
    names = set()
    for m in theme.IMPORT_MODULE.finditer(text):
        if m.group("alias") and not m.group("uri").startswith("qs."):
            limit = None
            if m.group("major") is not None:
                limit = (int(m.group("major")), int(m.group("minor") or 0))
            found.append((m.group("uri"), limit))
            names.add(m.group("alias"))
    return found, names


class Scope(object):
    """What one file's imports give the gate and withhold from the host."""

    def __init__(self, text, rewrite, qml_dir, cache):
        gate_imports, self.aliases = qt_imports(text)
        host_imports, _ = qt_imports(rewritten(text, rewrite))
        self.changed = gate_imports != host_imports
        gate, host = {}, {}
        gate_names, host_names = {}, {}
        for imports, limits, names in ((gate_imports, gate, gate_names), (host_imports, host, host_names)):
            for uri, limit in list(ALWAYS) + imports:
                module_limits(uri, limit, qml_dir, limits)
                for name, module in theme.module_names(uri, limit, qml_dir).items():
                    names.setdefault(name, module)
        self.gate, self.host = gate, host
        self.types = dict((n, m) for n, m in gate_names.items() if n not in host_names)
        self.by_cpp, self.by_export = {}, {}
        self.hidden = {}
        for uri in sorted(gate):
            for c in module_components(uri, qml_dir, cache):
                self.by_cpp.setdefault(c.name, c)
                for _module, name, _version in c.exports:
                    if gate_names.get(name) == uri:
                        self.by_export.setdefault(name, c)
                for kind, name, version in c.members:
                    if self.is_hidden(uri, version):
                        for spelled in member_spellings(kind, name):
                            self.hidden.setdefault(spelled, set()).add("%s.%s" % (c.name, name))

    def is_hidden(self, module, version):
        return theme.within(version, self.gate[module]) and not theme.within(version, self.host.get(module))

    def nearest(self, type_name, key):
        """How `key`, written as a binding in an element of `type_name`,
        reads: 'old' when the nearest member of that name up the prototype
        chain is one the host has, 'hidden' when it is not, None when the
        type or the member cannot be found."""
        c = self.by_export.get(type_name)
        seen = set()
        while c is not None and c.name not in seen:
            seen.add(c.name)
            for kind, name, version in c.members:
                if key in member_spellings(kind, name):
                    return "hidden" if self.is_hidden(c.module, version) else "old"
            c = self.by_cpp.get(c.prototype)
        return None


def member_spellings(kind, name):
    """The identifiers a member can be written as: itself, and a handler."""
    if kind == "Method":
        return (name,)
    handler = "on" + name[:1].upper() + name[1:]
    if kind == "Signal":
        return (name, handler)
    return (name, name + "Changed", handler + "Changed")


# --- one shipped file -------------------------------------------------------

def excused_lines(text):
    """The 1-based lines a QT-REVISION-EXCEPTION comment with a reason
    covers: its own, and the first code line under a `//` comment block that
    carries it."""
    lines = text.split("\n")
    out = set()
    said = re.compile(r"//.*" + re.escape(MARKER) + r"\s*\S")
    carried = False
    for k, line in enumerate(lines):
        if line.strip().startswith("//"):
            carried = carried or bool(said.search(line))
            continue
        if carried or said.search(line):
            out.add(k + 1)
        carried = False
    return out


def element_stack(toks):
    """For each token, the type name of the element whose body directly holds
    it, or None inside a script block, an object literal or no element."""
    out, stack = [], []
    for k, t in enumerate(toks):
        if t.kind == "punct" and t.text == "}":
            if stack:
                stack.pop()
        out.append(stack[-1] if stack else None)
        if t.kind == "punct" and t.text == "{":
            stack.append(element_opened(toks, k))
    return out


def element_opened(toks, k):
    """The type name when toks[k], a `{`, opens an element: `Type {`,
    `Alias.Type {` or `Type on property {`."""
    j = k - 1
    if j >= 2 and toks[j].kind == "ident" and toks[j - 1].kind == "ident" and toks[j - 1].text == "on":
        j -= 2
    if j < 0 or toks[j].kind != "ident" or not re.match(r"[A-Z]", toks[j].text):
        return None
    before = toks[j - 1] if j > 0 else None
    if before is not None and before.kind == "ident" and before.text in ("new", "class", "extends", "function"):
        return None
    return toks[j].text


def judge(path, text, rewrite, qml_dir, cache=None, label=None, importer_text=None):
    """(problems, counts) for one QML file. counts is (type names hidden,
    member names hidden, whether the rewrite changed an import). A
    code-behind passes its importer's text: its imports are those."""
    label = label or os.path.basename(path)
    cache = {} if cache is None else cache
    head = text if importer_text is None else importer_text
    try:
        scope = Scope(head, rewrite, qml_dir, cache)
    except Unreadable as error:
        # A code-behind's imports are its importer's, whose own judgement
        # reports this, once; the code-behind is not judged without them.
        if importer_text is not None:
            return [], (0, 0, False)
        return ["%s: %s" % (label, error)], (0, 0, False)
    try:
        toks = members.tokens(text)
    except members.ScanError as error:
        return ["%s: the scanner lost its place at %s, so nothing after it is judged" % (label, error)], (0, 0, False)
    inside = element_stack(toks)
    excused = excused_lines(text)
    # A named import is searched before every type, so a name an import
    # line declares as its alias is that alias wherever the file writes it.
    declared = set(m.group("alias") for pattern in (theme.IMPORT_MODULE, theme.IMPORT_PATH)
                   for m in pattern.finditer(head) if m.group("alias"))
    version = rewrite[1].split(" ", 1)[1]
    problems = []
    for k, t in enumerate(toks):
        if t.kind != "ident" or t.text in declared or t.line in excused:
            continue
        prev = toks[k - 1] if k > 0 else None
        after = toks[k + 1] if k + 1 < len(toks) else None
        member_of = prev is not None and prev.kind == "punct" and prev.text in (".", "?.") \
            and not theme.spread_before(toks, k)
        if t.text in scope.types:
            behind_alias = member_of and k >= 2 and toks[k - 2].kind == "ident" and toks[k - 2].text in scope.aliases \
                and not (k >= 3 and toks[k - 3].kind == "punct" and toks[k - 3].text in (".", "?."))
            if not member_of or behind_alias:
                problems.append("%s:%d:%d: `%s` is a type %s exports only after %s, which is where the host's load "
                                "patch pins this file's import: it loads in the gate and not on the host (D-HOST-10)"
                                % (label, t.line, t.col, t.text, scope.types[t.text], version))
                continue
        if t.text not in scope.hidden:
            continue
        owners = ", ".join(sorted(scope.hidden[t.text]))
        is_key = (not member_of and inside[k] is not None
                  and after is not None and after.kind == "punct" and after.text == ":"
                  and (prev is None or prev.line < t.line
                       or (prev.kind == "punct" and prev.text in ("{", "}", ";"))))
        if is_key:
            reading = scope.nearest(inside[k], t.text)
            if reading == "old":
                continue
            if reading == "hidden":
                problems.append("%s:%d:%d: `%s` in a %s is a member Qt added after %s (%s): the host's load patch "
                                "pins this file's import there, so the file loads in the gate and not on the host "
                                "(D-HOST-10)" % (label, t.line, t.col, t.text, inside[k], version, owners))
                continue
        problems.append("%s:%d:%d: `%s` is the name of a member Qt added after %s (%s), which the host's load patch "
                        "hides, and this reading cannot tell whose member is meant here; if it is not Qt's, say so "
                        "with `// %s <reason>` (D-HOST-10)" % (label, t.line, t.col, t.text, version, owners, MARKER))
    return problems, (len(scope.types), len(scope.hidden), scope.changed)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=None)
    ap.add_argument("--qml-dir", default=DEFAULT_QML_DIR, help="the Qt QML import path")
    ap.add_argument("--quickshell", default=DEFAULT_QUICKSHELL, help="the host's quickshell binary")
    ap.add_argument("file", nargs="*")
    args = ap.parse_args(argv)
    root = args.root or theme.repo_root()
    try:
        files = [(path, path) for path in args.file] or theme.shipped_code(root)
    except (OSError, ValueError, SyntaxError) as error:
        print("qt revision guard: the shipped code cannot be listed: %s" % error)
        return 1
    if not os.path.isfile(args.quickshell):
        print("qt revision guard: no quickshell at %s, so the version the host loads a plugin at cannot be read"
              % args.quickshell)
        return 1
    rewrite = rewrite_from_binary(args.quickshell)
    if rewrite is None:
        print("qt revision guard: %s carries no QtQuick import rewrite, so the host loads what the gate loads; "
              "nothing to judge" % args.quickshell)
        return 0
    problems, cache = [], {}
    judged, types, hidden, changed = 0, 0, 0, 0
    for path, importer in files:
        try:
            text = read(path)
            importer_text = None if importer == path else read(importer)
        except (OSError, UnicodeDecodeError) as error:
            problems.append("%s: unreadable: %s" % (path, error))
            continue
        p, (n_types, n_hidden, was_changed) = judge(path, text, rewrite, args.qml_dir, cache, importer_text=importer_text)
        problems += p
        judged += 1
        types, hidden = max(types, n_types), max(hidden, n_hidden)
        changed += 1 if was_changed else 0
    if judged and not changed and not problems:
        problems.append("qt revision guard: the host's rewrite changes no import line of any of the %d file(s) "
                        "judged, so nothing was compared and anything would pass" % judged)
    for p in problems:
        print(p)
    if problems:
        return 1
    print("qt revision guard: %d file(s), %d read as the host's rewrite pins them (QtQuick %s): %d type name(s) and "
          "%d member name(s) the installed Qt has past that, none used"
          % (judged, changed, rewrite[1].split(" ", 1)[1], types, hidden))
    return 0


if __name__ == "__main__":
    sys.exit(main())
