#!/usr/bin/env python3
"""No shipped QML file names, unqualified, a theme or host-kit name that a Qt
or Quickshell module it imports also exports (D-HOST-9, 2026-11-01).

WHY. Qt 6.12's QtQuick exports a C++ singleton named `Color` (QQuickColor),
and the QML engine looks a JS identifier up in the C++ types of every
unqualified import BEFORE any qmldir composite singleton
(QQmlTypeNameCache::doQuery in qtdeclarative 6.12.0; upstream QTBUG-151278).
The host's theme is a composite singleton (`singleton Color 1.0 Color.qml` in
the host's Commons/qmldir), so an unqualified `Color.accent` in Guide.qml was
QtQuick's on Qt 6.12 WHATEVER the import order: measured by lane-host9 and
rc-host9 in a nested headless cage, #000000 and 15 warnings. The plugin drew
its theme only because Omarchy's own quickshell build rewrites a plugin's
`import QtQuick` to `import QtQuick 6.11` behind a root pragma its packager
calls temporary. qmllint resolves the same name by the last import and
reported the theme's, which is why nothing in the gate saw it.

THE RULE. A named import is searched first, so a host-kit name a Qt or
Quickshell module can shadow is written qualified, the way Omarchy 4.0.6
wrote its own 54 files: `import qs.Commons as Commons` beside the unqualified
`import qs.Commons`, and `Commons.Color.*`. This guard reads every shipped
QML file as source (the tokenizer of check-model-members.py: comments,
strings and regular-expression literals skipped, a template's `${...}` read
as code) and takes every identifier that is a name the host's qs.Commons or
qs.Ui exports, written without a qualifier in front of it -- as an element
type, a member access (`Color.menu.text`) or an argument nested anywhere in
an expression. Each is judged against every name exported by every module
the file imports UNQUALIFIED, read from the installed type files: the
module's qmltypes `exports` at every version up to the import's (an
unversioned import is the newest), its qmldir's composite types and
singletons, and the modules its qmldir imports in turn (QtQuick's `import
QtQml auto`, QtQml's `import QML 1.0`, Quickshell's `default import
Quickshell._Window`, ...). The QML builtins are always in scope. A name both
sides export is red, whatever the import order and whether the module's
type is C++ or composite: the order protects nothing for a C++ type, and a
rule that only holds for one registration kind is the rule the next Qt
release breaks quietly. Nothing is hard-coded, so a Qt or Quickshell update
that ADDS a colliding name turns this red on the first gate run after it.

It refuses to pass blind:
  - a module the file imports that has no qmldir under the Qt import path,
    or whose type files yield no name at all, is red (an `import qs...` is
    the host's, read from the host's own qmldir, and judged as the other
    side);
  - an unqualified quoted directory import is red: its names are in no type
    file this can read;
  - a file that imports qs.Commons or qs.Ui unqualified and yields no
    unqualified use of their names is red (the scanner read nothing, or the
    import is dead);
  - the host's qs.Commons or qs.Ui qmldir missing or empty is red.

What it does not judge: names the plugin's own directory provides (the
implicit import; BarWidget.qml's root `BarWidget` is the host kit's, which
Qt resolves past the file itself), and JavaScript globals, which every
import outranks.

Usage: check-theme-names.py [--root ROOT] [--host SHELL_DIR] [--qml-dir DIR] [FILE ...]
With no FILE, the .qml entries of ALLOWLIST in scripts/release.py. Exit 0
and a summary line when nothing collides; 1 and one line per problem
otherwise. Python 3 standard library only.
"""

import argparse
import ast
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_HOST = os.path.join(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"), "shell")
DEFAULT_QML_DIR = "/usr/lib/qt6/qml"
HOST_KIT = ("qs.Commons", "qs.Ui")
# The engine imports these into every file whatever it writes.
ALWAYS = (("QML", None),)

_spec = importlib.util.spec_from_file_location("check_model_members", os.path.join(HERE, "check-model-members.py"))
members = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(members)

IMPORT_MODULE = re.compile(
    r"^[ \t]*import[ \t]+(?P<uri>[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)*)"
    r"(?:[ \t]+(?P<major>\d+)(?:\.(?P<minor>\d+))?)?"
    r"(?:[ \t]+as[ \t]+(?P<alias>[A-Za-z_$][\w$]*))?[ \t]*;?[ \t]*(?://.*)?$", re.M)
IMPORT_PATH = re.compile(
    r'^[ \t]*import[ \t]+"(?P<path>[^"\n]*)"(?:[ \t]+(?P<version>\d+(?:\.\d+)?))?'
    r'(?:[ \t]+as[ \t]+(?P<alias>[A-Za-z_$][\w$]*))?[ \t]*;?[ \t]*(?://.*)?$', re.M)
EXPORT = re.compile(r'"(?P<module>[A-Za-z_][\w.]*)/(?P<name>[A-Za-z_]\w*) (?P<major>\d+)\.(?P<minor>\d+)"')


class Unreadable(Exception):
    pass


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def repo_root():
    return os.path.dirname(HERE)


def allowlisted_qml(root):
    """The .qml entries of ALLOWLIST in <root>/scripts/release.py, read as a
    literal with ast so nothing in release.py runs."""
    path = os.path.join(root, "scripts", "release.py")
    tree = ast.parse(read(path), path)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "ALLOWLIST" for t in node.targets):
            return [os.path.join(root, e) for e in ast.literal_eval(node.value) if e.endswith(".qml")]
    raise ValueError("%s has no ALLOWLIST assignment" % path)


def within(version, limit):
    """Is an export at `version` (major, minor) visible through an import at
    `limit`? None is an unversioned import: the newest, so everything."""
    return limit is None or version <= limit


def qmldir_entries(text):
    """(imports, types) of one qmldir. imports are (uri, version-or-'auto'-or-None);
    types are (name, (major, minor)) for its composite types and singletons,
    `internal` ones left out because no importer can name them."""
    imports, types = [], []
    for line in text.split("\n"):
        w = line.split()
        if not w or w[0].startswith("#"):
            continue
        if w[0] in ("default", "optional") and len(w) >= 3 and w[1] == "import":
            w = w[1:]
        if w[0] == "import" and len(w) >= 2:
            v = w[2] if len(w) >= 3 else None
            imports.append((w[1], v))
            continue
        if w[0] == "singleton" and len(w) >= 4:
            w = w[1:]
        if re.match(r"^[A-Z]\w*$", w[0]) and len(w) >= 3 and re.match(r"^\d+\.\d+$", w[1]):
            major, minor = w[1].split(".")
            types.append((w[0], (int(major), int(minor))))
    return imports, types


def module_names(uri, limit, qml_dir, seen=None):
    """{name: module} for everything `import <uri> <limit>` brings into an
    unqualified scope, read from the installed qmldir and qmltypes files and
    the qmldir imports they name. Raises Unreadable for a module with no
    qmldir, or one whose files name nothing."""
    seen = {} if seen is None else seen
    key = (uri, limit)
    if key in seen:
        return {}
    seen[key] = True
    d = os.path.join(qml_dir, *uri.split("."))
    qmldir = os.path.join(d, "qmldir")
    if not os.path.isfile(qmldir):
        raise Unreadable("%s: no qmldir at %s, so its names cannot be read" % (uri, qmldir))
    text = read(qmldir)
    imports, types = qmldir_entries(text)
    out = {}
    for name, version in types:
        if within(version, limit):
            out.setdefault(name, uri)
    for line in text.split("\n"):
        w = line.split()
        if len(w) >= 2 and w[0] == "typeinfo":
            info = os.path.join(d, w[1])
            if not os.path.isfile(info):
                raise Unreadable("%s: its qmldir names typeinfo %s, which is not there" % (uri, info))
            for m in EXPORT.finditer(read(info)):
                if within((int(m.group("major")), int(m.group("minor"))), limit):
                    out.setdefault(m.group("name"), uri)
    for sub, version in imports:
        if version == "auto":
            sub_limit = limit
        elif version is None:
            sub_limit = None
        else:
            parts = version.split(".")
            sub_limit = (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        for name, module in module_names(sub, sub_limit, qml_dir, seen).items():
            out.setdefault(name, module)
    if not out and not imports:
        raise Unreadable("%s: its type files name no type at all, so a collision with it cannot be seen" % uri)
    return out


def host_kit_names(host):
    """{name: module} for the host kit's own modules, from their qmldirs."""
    out = {}
    for uri in HOST_KIT:
        path = os.path.join(host, *uri.split(".")[1:], "qmldir")
        if not os.path.isfile(path):
            raise Unreadable("%s: no qmldir at %s" % (uri, path))
        _, types = qmldir_entries(read(path))
        if not types:
            raise Unreadable("%s: %s names no type" % (uri, path))
        for name, _version in types:
            out.setdefault(name, uri)
    return out


def file_imports(text):
    """(unqualified module imports as (uri, limit), qualified aliases {alias: uri},
    unqualified quoted directory imports as (line, path))."""
    unqualified, aliases, directories = [], {}, []
    for m in IMPORT_MODULE.finditer(text):
        limit = None
        if m.group("major") is not None:
            limit = (int(m.group("major")), int(m.group("minor") or 0))
        if m.group("alias"):
            aliases[m.group("alias")] = m.group("uri")
        else:
            unqualified.append((m.group("uri"), limit))
    for m in IMPORT_PATH.finditer(text):
        if m.group("alias") is None and not m.group("path").endswith((".js", ".mjs")):
            directories.append((text.count("\n", 0, m.start()) + 1, m.group("path")))
    return unqualified, aliases, directories


def unqualified_uses(text, names):
    """(line, col, name) for every identifier in code that is one of `names`
    and is not a member of something else (`x.Color`, `x?.Color`), not the
    alias an import declares, and not inside an import line."""
    toks = members.tokens(text)
    out = []
    import_line = set(text.count("\n", 0, m.start()) + 1
                      for m in re.finditer(r"^[ \t]*import[ \t]", text, re.M))
    for k, t in enumerate(toks):
        if t.kind != "ident" or t.text not in names or t.line in import_line:
            continue
        prev = toks[k - 1] if k > 0 else None
        if prev is not None and prev.kind == "punct" and prev.text in (".", "?."):
            continue
        out.append((t.line, t.col, t.text))
    return out


def judge(path, text, kit, qml_dir, label=None):
    """(problems, uses) for one QML file: every complaint, and every
    unqualified host-kit use it judged as (line, col, name)."""
    label = label or os.path.basename(path)
    problems = []
    unqualified, _aliases, directories = file_imports(text)
    for line, where in directories:
        problems.append("%s:%d: an unqualified directory import (\"%s\") brings in names no type file lists; "
                        "this guard cannot judge them" % (label, line, where))
    exported = {}
    kit_imported = False
    for uri, limit in list(ALWAYS) + unqualified:
        if uri in HOST_KIT:
            kit_imported = True
            continue
        if uri.startswith("qs."):
            problems.append("%s: imports %s, a host module this guard does not read" % (label, uri))
            continue
        try:
            for name, module in module_names(uri, limit, qml_dir).items():
                exported.setdefault(name, set()).add(module)
        except Unreadable as error:
            problems.append("%s: %s" % (label, error))
    try:
        uses = unqualified_uses(text, set(kit))
    except members.ScanError as error:
        return problems + ["%s: the scanner lost its place at %s, so nothing after it is judged" % (label, error)], []
    for line, col, name in uses:
        if name in exported:
            problems.append("%s:%d:%d: `%s` is %s's, and %s also exports `%s`: on Qt 6.12 the engine takes an "
                            "imported C++ type ahead of the host's in any import order (D-HOST-9, QTBUG-151278); "
                            "qualify it -- `import %s as %s`, then `%s.%s`"
                            % (label, line, col, name, kit[name], ", ".join(sorted(exported[name])), name,
                               kit[name], kit[name].split(".")[-1], kit[name].split(".")[-1], name))
    if kit_imported and not uses:
        problems.append("%s imports %s unqualified and the scanner found no unqualified use of their names: it "
                        "read nothing, or the import is dead" % (label, " / ".join(HOST_KIT)))
    return problems, uses


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=None)
    ap.add_argument("--host", default=DEFAULT_HOST, help="the Omarchy shell directory (qs.Commons, qs.Ui)")
    ap.add_argument("--qml-dir", default=DEFAULT_QML_DIR, help="the Qt QML import path")
    ap.add_argument("file", nargs="*")
    args = ap.parse_args(argv)
    root = args.root or repo_root()
    files = args.file or allowlisted_qml(root)
    try:
        kit = host_kit_names(args.host)
    except Unreadable as error:
        print("theme name guard: the host kit is unreadable: %s" % error)
        return 1
    problems, total, judged = [], 0, 0
    for path in files:
        try:
            text = read(path)
        except (OSError, UnicodeDecodeError) as error:
            problems.append("%s: unreadable: %s" % (path, error))
            continue
        p, uses = judge(path, text, kit, args.qml_dir)
        problems += p
        total += len(uses)
        judged += 1
    for p in problems:
        print(p)
    if problems:
        return 1
    print("theme name guard: %d unqualified host-kit use(s) in %d file(s), none a name an imported Qt or Quickshell "
          "module exports (%d host-kit names)" % (total, judged, len(kit)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
