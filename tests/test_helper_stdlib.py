"""F-GATE-30: the helper is Python 3 standard library only.

CLAUDE.md's engineering constraint 3 says `bin/omarchy-iptv` imports nothing
but the standard library and adds no runtime dependency, and until this
module nothing in the gate held it. QA-PLAYER's PLY-SEC-17 graded it with a
grep for lines that START with `import` or `from`, and the helper's usual
style is an import inside the function that needs it: of its 112 import
statements 77 sit inside a function, and 17 of its 40 modules (`socket`
among them) are imported nowhere else, so a nested `import requests` left
that grep at `[]` (recheck-c5ds-records, 2026-11-24).

So this module reads the helper's files from the stub's own list
(scripts/helper_files.py, as every other reader of the helper's files does:
no glob, no hand list) and walks each file's syntax tree at ANY depth. It
refuses, naming the file, the line and the module:
  - an `import X` whose top-level module is not in sys.stdlib_module_names;
  - a `from X import ...` (level 0) the same way;
  - a relative import, `from . import x` (the helper is no package, so it has
    nothing to be relative to);
  - a call to `__import__`, `importlib.import_module` or
    `importlib.__import__` (or a bare `import_module`) unless every name it
    can be handed is a standard module. The helper makes ONE such call:
    `limit_memory` (03-io-playlist.py) imports each name of its `preload`
    parameter before it lowers the memory limit, and is handed FETCH_PRELOAD
    by default and EPG_PRELOAD by the epg verb. So the rule judges the
    argument rather than refusing the call blind: a string literal; or the
    target of a `for` over a module-level tuple of string literals (built
    from literals, other such tuples and `+`, assigned once), or over a
    parameter of the enclosing function that is never reassigned there,
    whose default and every value any call in the helper passes resolve the
    same way. Anything else is a computed name and is refused. (The stub's
    `compile` and `exec` run the parts, which this module reads anyway.)
A docstring or a comment is text, not an import, and is never read as one.

F-GATE-32 (2026-11-25) holds the rest of the constraint, the forms that
import or load at run time without an import statement the rule above
reads, and "no new runtime dependency":
  - `exec`, `eval` and `compile`: the stub's loader calls `compile` once and
    `exec` once (they run the parts, which this module reads); any other
    call, and any reference that is not a call, is refused;
  - the import functions reached any other way: an alias from an import
    statement is resolved and its call judged as above; a reference to
    `__import__` or `import_module` that is not a direct call, the name
    `__builtins__`, and a string that spells one of the three, are refused;
  - an import of `runpy`, `pkgutil`, `zipimport`, `imp`, `importlib.util`
    or `importlib.machinery`, or a reference to either submodule: each
    loads code by name or by path;
  - the preload: a tuple and nothing else (a list can grow), a name stored
    once ANYWHERE in the helper (`+=`, a `global` or a `del` in any function
    counts), the function's own parameter read before a module-level name
    that spells the same, and the function that holds the loop referenced
    only as a call (so nobody rebinds its defaults or hands it on);
  - `CDLL`, `PyDLL`, `LoadLibrary` and `find_library`: a call whose first
    argument is the literal None (this process's own libc), nothing else,
    and no reference to `cdll` or `pydll`;
  - a standard module whose library the distribution ships as optional
    (Arch's python lists sqlite, xz and tk: `sqlite3`, `lzma`, `tkinter`
    and what sits on them), statically or in the preload;
  - the programs the helper starts: `programs()` resolves the head of every
    launcher's command, and the pin is mpv, wl-paste and the helper's own
    interpreter for the relay. A program it cannot resolve is named so.
Not seen, stated so nobody takes it for covered: `sys.modules[...]`,
`globals()[...]` with a computed key, an attribute fetched by a computed
`getattr`, and a library a standard module loads by itself.

The reader takes a file list so the cases below hand it mutants. Python 3
standard library only.
"""
import ast
import collections
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import helper_files  # noqa: E402  the helper's files, read from its stub (D-REL-7)

STDLIB = frozenset(sys.stdlib_module_names)
DYNAMIC_ATTRS = {("importlib", "import_module"), ("importlib", "__import__"),
                 ("builtins", "__import__")}
DYNAMIC_NAMES = {"__import__", "import_module"}
DYNAMIC_DOTTED = {"%s.%s" % pair for pair in DYNAMIC_ATTRS} | DYNAMIC_NAMES
EXEC_NAMES = {"exec", "eval", "compile"}
STUB_MAY_CALL = {"exec", "compile"}
LOADERS = ("runpy", "pkgutil", "zipimport", "imp", "importlib.util", "importlib.machinery")
# Arch's python package: "sqlite: for a default database integration",
# "xz: for lzma", "tk: for tkinter" (pacman -Qi python, Optional Deps).
OPTIONAL = {"sqlite3", "_sqlite3", "lzma", "_lzma", "tkinter", "_tkinter", "turtle",
            "turtledemo", "idlelib"}
OPTIONAL_DOTTED = {"dbm.sqlite3"}
LIBRARY_CALLS = {"CDLL", "PyDLL", "LoadLibrary", "find_library"}
LIBRARY_NAMES = {"cdll", "pydll"}
IMPORT_WORDS = {"__import__", "import_module", "__builtins__"}
LAUNCHERS = frozenset(
    ["subprocess." + n for n in ("run", "call", "check_call", "check_output", "Popen",
                                 "getoutput", "getstatusoutput")]
    + ["os." + n for n in ("execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp",
                           "execvpe", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv",
                           "spawnve", "spawnvp", "spawnvpe", "posix_spawn", "posix_spawnp",
                           "system", "popen", "startfile")])


def _aliases(trees):
    """name -> dotted name, for every import in every file (the parts run
    in one namespace)."""
    table = {}
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        table[alias.asname] = alias.name
                    else:
                        top = alias.name.split(".")[0]
                        table[top] = top
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                for alias in node.names:
                    if alias.name != "*":
                        table[alias.asname or alias.name] = "%s.%s" % (node.module, alias.name)
    return table


def _dotted(node, aliases):
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value, aliases)
        return None if head is None else "%s.%s" % (head, node.attr)
    return None


def _dynamic_import(node, aliases=None):
    """True when `node` (an ast.Call) is a call of one of the import
    functions this module judges, by its name or through an import alias."""
    return _dotted(node.func, aliases or {}) in DYNAMIC_DOTTED


def _strings(node, table):
    """The tuple of strings `node` builds from string literals, names in
    `table` and `+`, or None."""
    if isinstance(node, ast.Tuple):
        if all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts):
            return tuple(e.value for e in node.elts)
        return None
    if isinstance(node, ast.Name):
        return table.get(node.id)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _strings(node.left, table), _strings(node.right, table)
        return None if left is None or right is None else left + right
    return None


def _constants(trees):
    """Every module-level name assigned exactly once, across the files in
    the order the stub runs them (one namespace), whose value is a tuple of
    strings; a name assigned twice resolves to nothing, and so does one
    stored, deleted or declared global anywhere else in the helper (`+=` in
    a function is a store)."""
    table, seen = {}, set()
    for tree in trees:
        for node in tree.body:
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            else:
                continue
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id in seen:
                    table[target.id] = None
                    continue
                seen.add(target.id)
                table[target.id] = _strings(value, table)
    stores = collections.Counter()
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                stores[node.id] += 1
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                for name in node.names:
                    stores[name] += 2
    for name in table:
        if stores[name] != 1:
            table[name] = None
    return table


def _stores(func, name):
    return [n for n in ast.walk(func) if isinstance(n, ast.Name) and n.id == name
            and isinstance(n.ctx, ast.Store)]


def _dynamic_values(call, parents, trees, table):
    """Every name the dynamic import `call` can be handed, as a tuple, or
    None when that cannot be shown."""
    arg = call.args[0] if call.args else None
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return (arg.value,)
    if not isinstance(arg, ast.Name):
        return None
    loop, node = None, call
    while node in parents:
        node = parents[node]
        if (loop is None and isinstance(node, ast.For) and isinstance(node.target, ast.Name)
                and node.target.id == arg.id):
            loop = node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            break
    else:
        return None
    if loop is None or len(_stores(node, arg.id)) != 1:
        return None
    if not isinstance(loop.iter, ast.Name):
        return _strings(loop.iter, table)
    params = node.args.posonlyargs + node.args.args
    names = [a.arg for a in params]
    others = [a.arg for a in node.args.kwonlyargs + [node.args.vararg, node.args.kwarg] if a]
    if loop.iter.id in others or _stores(node, loop.iter.id):
        return None
    if loop.iter.id not in names:
        # No parameter and no local of that name: the module's own.
        return _strings(loop.iter, table)
    index = names.index(loop.iter.id)
    defaults = dict(zip(names[len(names) - len(node.args.defaults):], node.args.defaults))
    values = []
    if loop.iter.id in defaults:
        got = _strings(defaults[loop.iter.id], table)
        if got is None:
            return None
        values.extend(got)
    for tree in trees:
        for other in ast.walk(tree):
            if not (isinstance(other, ast.Call) and isinstance(other.func, ast.Name)
                    and other.func.id == node.name):
                continue
            passed = [k.value for k in other.keywords if k.arg == loop.iter.id]
            if len(other.args) > index:
                passed.append(other.args[index])
            if any(isinstance(a, ast.Starred) for a in other.args) or any(
                    k.arg is None for k in other.keywords):
                return None
            for value in passed:
                got = _strings(value, table)
                if got is None:
                    return None
                values.extend(got)
    return tuple(values) if values else None


def census(root, rels=None):
    """Read every file in `rels` (repo-relative to `root`; by default the
    helper's files as the stub lists them) and return a dict: `files` (the
    files read), `statements` (import statements counted, `ast.Import` and
    level-0 `ast.ImportFrom`), `modules` (their top-level modules) and
    `findings`, a list of (file, line, what) for each import this module
    refuses."""
    if rels is None:
        rels = helper_files.helper_paths(str(root))
    statements = 0
    modules, dynamic = set(), set()
    findings = []
    trees = [(rel, ast.parse(helper_files.read(str(root), rel), filename=rel)) for rel in rels]
    table = _constants([tree for _, tree in trees])
    aliases = _aliases([tree for _, tree in trees])
    holders = set()
    for rel, tree in trees:
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                statements += 1
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    modules.add(top)
                    if top not in STDLIB:
                        findings.append((rel, node.lineno, top))
                    else:
                        findings.extend((rel, node.lineno, what) for what in _module_refusals(alias.name))
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    findings.append((rel, node.lineno, "relative import (from %s%s)"
                                     % ("." * node.level, node.module or "")))
                    continue
                statements += 1
                top = node.module.split(".")[0]
                modules.add(top)
                if top not in STDLIB:
                    findings.append((rel, node.lineno, top))
                else:
                    whats = []
                    for full in [node.module] + ["%s.%s" % (node.module, a.name) for a in node.names]:
                        whats.extend(w for w in _module_refusals(full) if w not in whats)
                    findings.extend((rel, node.lineno, what) for what in whats)
            elif isinstance(node, ast.Call) and _dynamic_import(node, aliases):
                holder = node
                while holder in parents and not isinstance(holder, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    holder = parents[holder]
                if isinstance(holder, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    holders.add(holder.name)
                values = _dynamic_values(node, parents, [t for _, t in trees], table)
                if values is None:
                    findings.append((rel, node.lineno, "dynamic import of a computed name"))
                    continue
                for value in values:
                    top = value.split(".")[0]
                    dynamic.add(top)
                    if top not in STDLIB:
                        findings.append((rel, node.lineno, "dynamic import of %s" % top))
                    else:
                        findings.extend((rel, node.lineno, "dynamic %s" % what)
                                        for what in _module_refusals(value))
    for rel, tree in trees:
        findings.extend(_beyond(rel, tree, aliases, holders))
    findings.sort(key=lambda f: (list(rels).index(f[0]), f[1]))
    return {"files": list(rels), "statements": statements, "modules": modules,
            "dynamic": dynamic, "findings": findings}


def _module_refusals(full):
    """What F-GATE-32 refuses about importing the standard module `full`."""
    out = []
    for loader in LOADERS:
        if full == loader or full.startswith(loader + "."):
            out.append("import of %s, which loads code by name" % loader)
    if full.split(".")[0] in OPTIONAL or full in OPTIONAL_DOTTED:
        out.append("import of %s, whose library the distribution ships as optional" % full)
    return out


def _docstrings(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(body[0].value)
    return out


def _beyond(rel, tree, aliases, holders):
    """F-GATE-32's refusals in one file: (rel, line, what) for each."""
    out = []
    called = {node.func: node for node in ast.walk(tree) if isinstance(node, ast.Call)}
    docs = _docstrings(tree)
    stub_calls = collections.Counter()
    # In source order, so "a second" is the later one.
    for node in sorted((n for n in ast.walk(tree) if hasattr(n, "lineno")),
                       key=lambda n: (n.lineno, n.col_offset)):
        line = node.lineno
        if isinstance(node, ast.Constant):
            if isinstance(node.value, str) and node.value in IMPORT_WORDS and node not in docs:
                out.append((rel, line, "the string %r names an import function" % node.value))
            continue
        if not isinstance(node, (ast.Name, ast.Attribute)):
            continue
        last = node.id if isinstance(node, ast.Name) else node.attr
        dotted = _dotted(node, aliases)
        call = called.get(node)
        if isinstance(node, ast.Name) and node.id == "__builtins__":
            out.append((rel, line, "reference to __builtins__"))
        if isinstance(node.ctx, ast.Load) and (
                (isinstance(node, ast.Name) and node.id in EXEC_NAMES)
                or dotted in ("builtins." + n for n in EXEC_NAMES)):
            if call is None:
                out.append((rel, line, "reference to %s that is not a call" % last))
            elif rel != helper_files.STUB or last not in STUB_MAY_CALL:
                out.append((rel, line, "%s outside the stub's loader" % last))
            else:
                stub_calls[last] += 1
                if stub_calls[last] > 1:
                    out.append((rel, line, "a second %s in the stub" % last))
        if isinstance(node.ctx, ast.Load) and call is None and (
                last in DYNAMIC_NAMES or dotted in DYNAMIC_DOTTED):
            out.append((rel, line, "reference to %s that is not a direct call" % last))
        if dotted in ("importlib.util", "importlib.machinery"):
            out.append((rel, line, "reference to %s, which loads code by name" % dotted))
        if last in LIBRARY_CALLS and isinstance(node.ctx, ast.Load):
            if call is None:
                out.append((rel, line, "reference to %s that is not a call" % last))
            elif not (call.args and isinstance(call.args[0], ast.Constant) and call.args[0].value is None):
                out.append((rel, line, "%s is handed a library" % last))
        if last in LIBRARY_NAMES and isinstance(node.ctx, ast.Load):
            out.append((rel, line, "reference to %s" % last))
        if isinstance(node, ast.Name) and node.id in holders and isinstance(node.ctx, ast.Load) and call is None:
            out.append((rel, line, "%s, which holds the judged import, is referenced other than as a call"
                        % node.id))
    return out


# ---------------------------------------------- the programs it starts ----

def _functions(trees):
    out = {}
    for _, tree in trees:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.setdefault(node.name, []).append(node)
    return out


def _list_head(node):
    """The program a list literal names: its first element, a string, or
    that element's source."""
    if not isinstance(node, (ast.List, ast.Tuple)) or not node.elts:
        return None
    head = node.elts[0]
    if isinstance(head, ast.Constant) and isinstance(head.value, str):
        return head.value
    return ast.unparse(head)


def programs(root, rels=None):
    """Every launcher call in the helper and the program each can start.
    Returns `sites`, a list of (file, line, launcher), and `started`, the
    sorted set of programs: a string constant as it is, any other head by
    its source, and `unresolved: <source>` where the head cannot be shown.

    Resolved: a constant; a list literal's head; `name[0]` where `name` is
    stored once in the function, from a call of a helper function whose one
    return is a list literal; a parameter never stored in the function,
    through every call of that function in the helper, each handing it a
    module-level list stored once anywhere."""
    if rels is None:
        rels = helper_files.helper_paths(str(root))
    trees = [(rel, ast.parse(helper_files.read(str(root), rel), filename=rel)) for rel in rels]
    aliases = _aliases([tree for _, tree in trees])
    functions = _functions(trees)
    stores = collections.Counter()
    lists = {}
    for _, tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
                stores[node.id] += 1
            elif isinstance(node, (ast.Global, ast.Nonlocal)):
                for name in node.names:
                    stores[name] += 2
        for node in tree.body:
            if (isinstance(node, ast.Assign) and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)):
                lists[node.targets[0].id] = node.value
    grown = set()
    for _, tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.attr in (
                    "append", "extend", "insert", "pop", "remove", "clear", "reverse", "sort", "__setitem__"):
                grown.add(node.value.id)
            elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and isinstance(
                    node.ctx, (ast.Store, ast.Del)):
                grown.add(node.value.id)

    def constant_list(name):
        if stores[name] != 1 or name not in lists or name in grown:
            return None
        return _list_head(lists[name])

    def head(expr, func, depth=0):
        if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
            return [expr.value]
        if _list_head(expr) is not None:
            return [_list_head(expr)]
        unresolved = ["unresolved: %s" % ast.unparse(expr)]
        if func is None or depth > 2:
            return unresolved
        if (isinstance(expr, ast.Subscript) and isinstance(expr.value, ast.Name)
                and isinstance(expr.slice, ast.Constant) and expr.slice.value == 0):
            name = expr.value.id
            assigned = [n for n in ast.walk(func) if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
            if len(_stores(func, name)) != 1 or len(assigned) != 1:
                return unresolved
            value = assigned[0].value
            if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                    and len(functions.get(value.func.id, [])) == 1 and stores[value.func.id] == 0):
                return unresolved
            made = functions[value.func.id][0]
            returns = [n for n in ast.walk(made) if isinstance(n, ast.Return)]
            if len(returns) != 1 or _list_head(returns[0].value) is None:
                return unresolved
            return [_list_head(returns[0].value)]
        if isinstance(expr, ast.Name):
            params = [a.arg for a in func.args.posonlyargs + func.args.args]
            if expr.id not in params or _stores(func, expr.id) or len(functions.get(func.name, [])) != 1:
                return unresolved
            index, out = params.index(expr.id), []
            for _, tree in trees:
                for call in ast.walk(tree):
                    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                            and call.func.id == func.name):
                        continue
                    handed = [k.value for k in call.keywords if k.arg == expr.id] + call.args[index:index + 1]
                    if len(handed) != 1 or any(isinstance(a, ast.Starred) for a in call.args) or any(
                            k.arg is None for k in call.keywords):
                        return unresolved
                    got = constant_list(handed[0].id) if isinstance(handed[0], ast.Name) else _list_head(handed[0])
                    if got is None:
                        return unresolved
                    out.append(got)
            return out or unresolved
        return unresolved

    sites, started = [], set()
    for rel, tree in trees:
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
                name = _dotted(node, aliases)
                if name in LAUNCHERS and not (isinstance(parents.get(node), ast.Call)
                                              and parents[node].func is node):
                    sites.append((rel, node.lineno, name))
                    started.add("unresolved: %s referenced, not called" % name)
            if not isinstance(node, ast.Call):
                continue
            name = _dotted(node.func, aliases)
            if name not in LAUNCHERS:
                continue
            sites.append((rel, node.lineno, name))
            func = node
            while func in parents and not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func = parents[func]
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func = None
            command = [k.value for k in node.keywords if k.arg in ("args", "file", "path")] + node.args[:1]
            if not command:
                started.add("unresolved: %s with no command" % name)
                continue
            started.update(head(command[0], func))
    return {"sites": sites, "started": sorted(started)}


class TheHelperIsStdlibOnlyTest(unittest.TestCase):
    def test_every_import_in_every_helper_file_is_the_standard_librarys(self):
        got = census(ROOT)
        self.assertEqual(got["findings"], [],
                         "the helper imports outside the standard library (CLAUDE.md "
                         "constraint 3): %s" % got["findings"])

    def test_the_reader_reads_the_stub_and_every_part_it_lists(self):
        got = census(ROOT)
        self.assertEqual(got["files"], helper_files.helper_paths(str(ROOT)))
        self.assertGreater(len(got["files"]), 1, "the stub lists no part")
        # The stub itself imports: a reader that skipped it would count fewer.
        stub_only = census(ROOT, [helper_files.STUB])
        self.assertGreater(stub_only["statements"], 0)
        self.assertGreater(got["statements"], stub_only["statements"])


class TheOneDynamicImportTest(unittest.TestCase):
    def test_limit_memorys_preload_is_judged_name_by_name(self):
        got = census(ROOT)
        # FETCH_PRELOAD and EPG_PRELOAD, resolved through limit_memory's
        # default and its two callers' arguments.
        self.assertIn("xml", got["dynamic"])
        self.assertIn("encodings", got["dynamic"])
        self.assertTrue(got["dynamic"] <= STDLIB)

    def test_a_third_party_name_added_to_the_epg_preload_is_refused(self):
        tmp = tempfile.mkdtemp(prefix="stdlib-pre-")
        self.addCleanup(shutil.rmtree, tmp)
        helper_files.copy_helper(str(ROOT), tmp)
        part = [p for p in helper_files.part_paths(tmp) if p.endswith("03-io-playlist.py")][0]
        path = os.path.join(tmp, part)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        old = '"xml.parsers.expat")'
        self.assertEqual(text.count(old), 1)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(old, '"xml.parsers.expat", "requests")'))
        found = census(tmp)["findings"]
        self.assertEqual([(f, w) for f, _, w in found], [(part, "dynamic import of requests")])


class MutantTest(unittest.TestCase):
    """Each case hands the reader a file it must refuse, or one it must not."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="stdlib-")
        self.addCleanup(shutil.rmtree, self.tmp)

    def judge(self, text):
        with open(os.path.join(self.tmp, "part.py"), "w", encoding="utf-8") as fh:
            fh.write(text)
        return census(self.tmp, ["part.py"])["findings"]

    def test_a_nested_third_party_import_is_refused_with_its_line(self):
        found = self.judge("import os\n\ndef verb():\n    import requests\n    return requests\n")
        self.assertEqual(found, [("part.py", 4, "requests")])

    def test_a_top_level_third_party_import_is_refused(self):
        self.assertEqual(self.judge("import yaml\n"), [("part.py", 1, "yaml")])

    def test_a_from_import_inside_a_method_is_refused(self):
        found = self.judge("class A:\n    def f(self):\n        from attr import s\n")
        self.assertEqual(found, [("part.py", 3, "attr")])

    def test_a_relative_import_is_refused(self):
        found = self.judge("def f():\n    from . import x\n")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][:2], ("part.py", 2))
        self.assertIn("relative import", found[0][2])

    def test_a_dynamic_import_of_a_third_party_module_is_refused(self):
        self.assertEqual(self.judge("m = __import__('requests')\n"),
                         [("part.py", 1, "dynamic import of requests")])
        self.assertEqual(self.judge("import importlib\nm = importlib.import_module('yaml.x')\n"),
                         [("part.py", 2, "dynamic import of yaml")])

    def test_a_dynamic_import_of_a_computed_name_is_refused(self):
        found = self.judge("def f(n):\n    return __import__(n)\n")
        self.assertEqual(found, [("part.py", 2, "dynamic import of a computed name")])

    def test_a_dynamic_import_of_a_standard_module_passes(self):
        self.assertEqual(self.judge("m = __import__('json')\n"), [])

    PRELOAD = ('PRE = ("json", "http.client")\nMORE = PRE + ("ssl",)\n\n'
               'def lim(preload=PRE):\n    import importlib\n    for name in preload:\n'
               '        importlib.import_module(name)\n\n')

    def test_a_preload_loop_over_standard_tuples_passes(self):
        self.assertEqual(self.judge(self.PRELOAD + "lim()\nlim(MORE)\nlim(preload=PRE)\n"), [])

    def test_a_preload_call_that_hands_it_a_third_party_name_is_refused(self):
        self.assertEqual(self.judge(self.PRELOAD + 'lim()\nlim(MORE + ("requests",))\n'),
                         [("part.py", 7, "dynamic import of requests")])

    def test_a_tuple_built_with_plus_that_names_a_third_party_module_is_refused(self):
        text = self.PRELOAD.replace('"ssl",', '"yaml",')
        self.assertEqual(self.judge(text + "lim(MORE)\n"), [("part.py", 7, "dynamic import of yaml")])

    def test_a_preload_default_that_names_a_third_party_module_is_refused(self):
        text = self.PRELOAD.replace('("json",', '("yaml",')
        self.assertEqual(self.judge(text), [("part.py", 7, "dynamic import of yaml")])

    def test_a_preload_handed_a_computed_value_is_refused(self):
        found = self.judge(self.PRELOAD + "lim(tuple(open('x').read().split()))\n")
        self.assertEqual(found, [("part.py", 7, "dynamic import of a computed name")])

    def test_a_preload_whose_parameter_is_reassigned_is_refused(self):
        text = self.PRELOAD.replace("    for name in preload:", "    preload = load()\n    for name in preload:")
        self.assertEqual(self.judge(text), [("part.py", 8, "dynamic import of a computed name")])

    def test_a_tuple_assigned_twice_resolves_to_nothing(self):
        text = self.PRELOAD + 'PRE = ("requests",)\nlim()\n'
        self.assertEqual(self.judge(text), [("part.py", 7, "dynamic import of a computed name")])

    def test_a_docstring_line_that_reads_like_an_import_is_not_one(self):
        # 01-core.py has a docstring line beginning "from its span's start",
        # which a `^\s*(import|from)` grep reads as the module `its`.
        text = ('def f():\n    """Walk the run\n    from its span\'s start to its end.\n'
                '    import requests -- prose too.\n    """\n    # import yaml\n    return 1\n')
        self.assertEqual(self.judge(text), [])

    def test_standard_packages_and_submodules_pass(self):
        text = ("import xml.etree.ElementTree as ET\nfrom http import client\n"
                "from urllib.parse import urlsplit\nfrom __future__ import annotations\n"
                "def f():\n    import socket, ctypes.util\n")
        self.assertEqual(self.judge(text), [])

    def test_a_nested_import_added_to_a_copy_of_the_real_helper_is_found(self):
        # The real tree's files, copied in the layout the stub resolves, with
        # one function-level third-party import added to its last part: the
        # reader, following the copy's own stub, names that part and line.
        helper_files.copy_helper(str(ROOT), self.tmp)
        last = helper_files.part_paths(self.tmp)[-1]
        path = os.path.join(self.tmp, last)
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().count("\n")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("\n\ndef _mutant():\n    import requests\n    return requests\n")
        got = census(self.tmp)
        self.assertEqual(got["findings"], [(last, lines + 4, "requests")])


class BeyondTheImportStatementTest(unittest.TestCase):
    """F-GATE-32: the forms that load code or a library at run time with no
    import statement the first rule reads. Each passed F-GATE-30's reader."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="stdlib-beyond-")
        self.addCleanup(shutil.rmtree, self.tmp)

    def whats(self, text, name="part.py"):
        path = os.path.join(self.tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return [(line, what) for _, line, what in census(self.tmp, [name])["findings"]]

    def test_exec_eval_and_compile_are_refused_in_a_part(self):
        self.assertEqual(self.whats('exec("import requests")\n'), [(1, "exec outside the stub's loader")])
        self.assertEqual(self.whats("x = eval(text)\n"), [(1, "eval outside the stub's loader")])
        self.assertEqual(self.whats('code = compile(src, "x", "exec")\n'),
                         [(1, "compile outside the stub's loader")])
        self.assertEqual(self.whats("import builtins\nbuiltins.exec(text)\n"),
                         [(2, "exec outside the stub's loader")])
        self.assertEqual(self.whats("run = exec\nrun(text)\n"), [(1, "reference to exec that is not a call")])

    def test_a_pattern_compiled_by_re_is_not_the_builtin(self):
        self.assertEqual(self.whats('import re\nP = re.compile("x")\n\ndef f(p):\n    return p.compile()\n'), [])

    def test_the_stub_may_compile_once_and_exec_once_and_never_eval(self):
        stub = helper_files.STUB
        loader = 'codes = [compile(source, path, "exec")]\nfor code in codes:\n    exec(code, namespace)\n'
        self.assertEqual(self.whats(loader, stub), [])
        self.assertEqual(self.whats(loader + "exec(more)\n", stub), [(4, "a second exec in the stub")])
        self.assertEqual(self.whats(loader + 'compile(more, "x", "exec")\n', stub),
                         [(4, "a second compile in the stub")])
        self.assertEqual(self.whats(loader + "eval(more)\n", stub), [(4, "eval outside the stub's loader")])

    def test_an_import_function_behind_an_alias_is_judged(self):
        self.assertEqual(self.whats('import importlib as il\nil.import_module("requests")\n'),
                         [(2, "dynamic import of requests")])
        self.assertEqual(self.whats('from importlib import import_module as im\nim("yaml.x")\n'),
                         [(2, "dynamic import of yaml")])
        self.assertEqual(self.whats('from importlib import import_module as im\nim("json")\n'), [])
        self.assertEqual(self.whats("import importlib as il\n\ndef f(n):\n    il.import_module(n)\n"),
                         [(4, "dynamic import of a computed name")])

    def test_an_import_function_that_is_not_called_directly_is_refused(self):
        self.assertEqual(self.whats('load = __import__\nload("requests")\n'),
                         [(1, "reference to __import__ that is not a direct call")])
        self.assertEqual(self.whats('import importlib\nload = importlib.import_module\n'),
                         [(2, "reference to import_module that is not a direct call")])
        self.assertEqual(self.whats('import importlib\ngetattr(importlib, "import_module")("requests")\n'),
                         [(2, "the string 'import_module' names an import function")])
        self.assertEqual(self.whats('__builtins__["__import__"]("requests")\n'),
                         [(1, "reference to __builtins__"),
                          (1, "the string '__import__' names an import function")])

    def test_a_docstring_that_spells_an_import_function_is_text(self):
        self.assertEqual(self.whats('def f():\n    """__import__"""\n    return 1\n'), [])
        self.assertEqual(self.whats('def f():\n    """Doc."""\n    return "__import__"\n'),
                         [(3, "the string '__import__' names an import function")])

    def test_the_modules_that_load_code_by_name_are_refused(self):
        for text, loader in (("import runpy\n", "runpy"), ("import pkgutil\n", "pkgutil"),
                             ("import zipimport\n", "zipimport"),
                             ("import importlib.util\n", "importlib.util"),
                             ("from importlib import util\n", "importlib.util"),
                             ("from importlib.machinery import SourceFileLoader\n", "importlib.machinery"),
                             ("def f():\n    from importlib.util import spec_from_file_location\n",
                              "importlib.util")):
            found = self.whats(text)
            self.assertEqual([what for _, what in found],
                             ["import of %s, which loads code by name" % loader], text)
        self.assertEqual(self.whats("import importlib\nspec = importlib.util.find_spec(name)\n"),
                         [(2, "reference to importlib.util, which loads code by name")])

    PRELOAD = MutantTest.PRELOAD

    def test_a_preload_held_in_a_list_is_refused(self):
        text = self.PRELOAD.replace('PRE = ("json", "http.client")', 'PRE = ["json", "http.client"]')
        text = text.replace('MORE = PRE + ("ssl",)\n', "\n")
        self.assertEqual(self.whats(text + "lim()\n"), [(7, "dynamic import of a computed name")])

    def test_a_preload_stored_again_inside_a_function_is_refused(self):
        grow = 'def grow():\n    global PRE\n    PRE += ("requests",)\n'
        self.assertEqual(self.whats(self.PRELOAD + grow + "lim()\n"),
                         [(7, "dynamic import of a computed name")])
        # A `global` alone, or a `del`, is enough: the name is no constant.
        self.assertEqual(self.whats(self.PRELOAD + "def g():\n    global PRE\n" + "lim()\n"),
                         [(7, "dynamic import of a computed name")])
        self.assertEqual(self.whats(self.PRELOAD + "def g():\n    del PRE\n" + "lim()\n"),
                         [(7, "dynamic import of a computed name")])

    def test_the_function_that_holds_the_import_is_only_ever_called(self):
        what = "lim, which holds the judged import, is referenced other than as a call"
        self.assertEqual(self.whats(self.PRELOAD + 'lim.__defaults__ = (("requests",),)\nlim()\n'), [(9, what)])
        self.assertEqual(self.whats(self.PRELOAD + 'go = lim\ngo(("requests",))\n'), [(9, what)])
        self.assertEqual(self.whats(self.PRELOAD + "lim()\nlim(MORE)\n"), [])

    def test_the_functions_own_parameter_is_read_before_a_module_name_that_spells_the_same(self):
        text = self.PRELOAD + 'preload = ("json",)\nlim(("requests",))\n'
        self.assertEqual(self.whats(text), [(7, "dynamic import of requests")])

    def test_a_keyword_only_preload_is_refused(self):
        text = self.PRELOAD.replace("def lim(preload=PRE):", "def lim(*, preload=PRE):")
        self.assertEqual(self.whats(text + "lim()\n"), [(7, "dynamic import of a computed name")])
        # And a module-level name that spells the same does not answer for it.
        self.assertEqual(self.whats(text + 'preload = ("json",)\nlim(preload=("requests",))\n'),
                         [(7, "dynamic import of a computed name")])

    def test_a_library_is_loaded_only_as_this_processs_own(self):
        self.assertEqual(self.whats("import ctypes\nlibc = ctypes.CDLL(None, use_errno=True)\n"), [])
        self.assertEqual(self.whats('import ctypes\ncurl = ctypes.CDLL("libcurl.so.4")\n'),
                         [(2, "CDLL is handed a library")])
        self.assertEqual(self.whats("from ctypes import CDLL\nlib = CDLL(name)\n"),
                         [(2, "CDLL is handed a library")])
        self.assertEqual(self.whats("import ctypes\nlib = ctypes.CDLL(name=None)\n"),
                         [(2, "CDLL is handed a library")])
        self.assertEqual(self.whats('import ctypes\nlib = ctypes.cdll.LoadLibrary("libcurl.so.4")\n'),
                         [(2, "LoadLibrary is handed a library"), (2, "reference to cdll")])
        self.assertEqual(self.whats('import ctypes.util\nname = ctypes.util.find_library("curl")\n'),
                         [(2, "find_library is handed a library")])
        self.assertEqual(self.whats("import ctypes\nload = ctypes.CDLL\n"),
                         [(2, "reference to CDLL that is not a call")])
        self.assertEqual(self.whats('import ctypes\nlib = ctypes.PyDLL("libpython3.so")\n'),
                         [(2, "PyDLL is handed a library")])

    def test_a_standard_module_on_an_optional_library_is_refused(self):
        tail = ", whose library the distribution ships as optional"
        self.assertEqual(self.whats("import sqlite3\n"), [(1, "import of sqlite3" + tail)])
        self.assertEqual(self.whats("def f():\n    import lzma\n"), [(2, "import of lzma" + tail)])
        self.assertEqual(self.whats("from tkinter import Tk\n"),
                         [(1, "import of tkinter" + tail), (1, "import of tkinter.Tk" + tail)])
        self.assertEqual(self.whats("import dbm.sqlite3\n"), [(1, "import of dbm.sqlite3" + tail)])
        self.assertEqual(self.whats("import gzip, zlib, bz2, dbm\n"), [])
        text = self.PRELOAD.replace('"ssl",', '"lzma",')
        self.assertEqual(self.whats(text + "lim(MORE)\n"), [(7, "dynamic import of lzma" + tail)])


class TheProgramsTheHelperStartsTest(unittest.TestCase):
    """Constraint 3's other half, "no new runtime dependency": the helper
    starts mpv, wl-paste and its own interpreter (the relay), nothing else."""

    PINNED = ["mpv", "sys.executable or 'python3'", "wl-paste"]

    def test_the_helper_starts_mpv_wl_paste_and_its_own_interpreter(self):
        got = programs(ROOT)
        self.assertEqual(got["started"], self.PINNED)
        self.assertEqual(sorted(name for _, _, name in got["sites"]),
                         ["os.execve", "os.execvpe", "subprocess.Popen"])

    def mutated(self, part_suffix, old, new, count=1):
        tmp = tempfile.mkdtemp(prefix="stdlib-prog-")
        self.addCleanup(shutil.rmtree, tmp)
        helper_files.copy_helper(str(ROOT), tmp)
        part = [p for p in helper_files.part_paths(tmp) if p.endswith(part_suffix)][0]
        path = os.path.join(tmp, part)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if old is None:
            text += new
        else:
            self.assertEqual(text.count(old), count, old)
            text = text.replace(old, new)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return programs(tmp)["started"]

    def test_a_new_program_is_named(self):
        got = self.mutated("11-cli.py", None, '\n\ndef _m(url):\n    os.execvp("curl", ["curl", url])\n')
        self.assertEqual(got, ["curl"] + self.PINNED)
        got = self.mutated("11-cli.py", None,
                           '\n\ndef _m(url):\n    import subprocess as sp\n    sp.run(["ffprobe", url])\n')
        self.assertEqual(got, ["ffprobe"] + self.PINNED)

    def test_a_command_nobody_can_resolve_is_named_unresolved(self):
        got = self.mutated("11-cli.py", None, "\n\ndef _m(cmd):\n    subprocess.run(cmd)\n")
        self.assertEqual(got, ["mpv", "sys.executable or 'python3'", "unresolved: cmd", "wl-paste"])
        got = self.mutated("11-cli.py", None, "\n\ndef _m():\n    cmd = build()\n    subprocess.run(cmd)\n")
        self.assertEqual(got, ["mpv", "sys.executable or 'python3'", "unresolved: cmd", "wl-paste"])
        got = self.mutated("11-cli.py", None, "\n\nstart = os.execvp\n")
        self.assertEqual(got, ["mpv", "sys.executable or 'python3'",
                               "unresolved: os.execvp referenced, not called", "wl-paste"])

    def test_the_clipboards_program_is_read_from_its_constant(self):
        old = 'CLIPBOARD_ARGV = ["wl-paste",'
        self.assertEqual(self.mutated("01-core.py", old, 'CLIPBOARD_ARGV = ["xclip",'),
                         ["mpv", "sys.executable or 'python3'", "xclip"])
        self.assertEqual(self.mutated("11-cli.py", None, '\n\nCLIPBOARD_ARGV.insert(0, "env")\n'),
                         ["mpv", "sys.executable or 'python3'", "unresolved: argv"])
        self.assertEqual(self.mutated("11-cli.py", None, '\n\nCLIPBOARD_ARGV = ["xclip"]\n'),
                         ["mpv", "sys.executable or 'python3'", "unresolved: argv"])
        self.assertEqual(self.mutated("11-cli.py", None, "\n\ndef _m(a):\n    return read_clipboard(a, 1, 1.0, 1.0)\n"),
                         ["mpv", "sys.executable or 'python3'", "unresolved: argv"])

    def test_the_relays_program_is_read_from_relay_argv(self):
        old = 'return [sys.executable or "python3", "-I",'
        self.assertEqual(self.mutated("07-player.py", old, 'return ["node", "-I",'),
                         ["mpv", "node", "wl-paste"])
        self.assertEqual(self.mutated("07-player.py", "    relay = relay_argv()\n",
                                      "    relay = relay_argv()\n    relay = shlex.split(os.environ['R'])\n"),
                         ["mpv", "unresolved: relay[0]", "wl-paste"])

    def test_the_players_program_is_the_literal(self):
        self.assertEqual(self.mutated("07-player.py", 'os.execvpe("mpv", argv, player_env)',
                                      'os.execvpe(argv[0], argv, player_env)'),
                         ["sys.executable or 'python3'", "unresolved: argv[0]", "wl-paste"])


class TheOldGrepCannotSeeItTest(unittest.TestCase):
    """Why the criterion moved: PLY-SEC-17's line grep, run as written
    against a copy holding the nested mutant, prints nothing to refuse while
    the reader above refuses it (rule 14: the grep could not go red)."""

    def test_the_line_grep_misses_a_nested_import_the_reader_finds(self):
        tmp = tempfile.mkdtemp(prefix="stdlib-grep-")
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, "part.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("import os\n\ndef verb():\n    import requests\n")
        out = subprocess.run(["grep", "-hoE", r"^(import|from) [A-Za-z_][A-Za-z0-9_]*", path],
                             capture_output=True, text=True, check=False).stdout
        grep_mods = {line.split()[1] for line in out.splitlines()}
        self.assertEqual(sorted(m for m in grep_mods if m not in STDLIB), [])
        self.assertEqual(census(tmp, ["part.py"])["findings"], [("part.py", 4, "requests")])


if __name__ == "__main__":
    unittest.main()
