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

The reader takes a file list so the cases below hand it mutants. Python 3
standard library only.
"""
import ast
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


def _dynamic_import(node):
    """True when `node` (an ast.Call) is a call of one of the import
    functions this module judges."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in DYNAMIC_NAMES
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return (func.value.id, func.attr) in DYNAMIC_ATTRS
    return False


def _strings(node, table):
    """The tuple of strings `node` builds from string literals, names in
    `table` and `+`, or None."""
    if isinstance(node, (ast.Tuple, ast.List)):
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
    strings; a name assigned twice resolves to nothing."""
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
    direct = _strings(loop.iter, table)
    if direct is not None:
        return direct
    if not isinstance(loop.iter, ast.Name):
        return None
    params = node.args.posonlyargs + node.args.args
    names = [a.arg for a in params]
    if loop.iter.id not in names or _stores(node, loop.iter.id):
        return None
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
            elif isinstance(node, ast.Call) and _dynamic_import(node):
                values = _dynamic_values(node, parents, [t for _, t in trees], table)
                if values is None:
                    findings.append((rel, node.lineno, "dynamic import of a computed name"))
                    continue
                for value in values:
                    top = value.split(".")[0]
                    dynamic.add(top)
                    if top not in STDLIB:
                        findings.append((rel, node.lineno, "dynamic import of %s" % top))
    return {"files": list(rels), "statements": statements, "modules": modules,
            "dynamic": dynamic, "findings": findings}


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
