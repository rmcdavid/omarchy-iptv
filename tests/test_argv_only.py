"""F-GATE-31: every process the plugin starts is started from an argv list.

CLAUDE.md's engineering constraint 2 says: argv-only process launching,
never `bash -c`, never string interpolation into a command, never
`shell=True`. Until this module nothing in the gate held it. The plans
graded it with a grep (QA's SEC-01, QA-SOURCES' SRC-SEC-12, QA-PLAYER's
PLY-SEC-15 step 9) whose include lists miss the model's `.mjs` parts, and
PLY-SEC-15's the helper's `.py` parts too; the marketplace capability scan
holds `sudo` and `pkexec` and no shell form.

Two readers, each handed files so the cases below can hand them mutants.

`python_census` reads the helper's files from the stub's own list
(scripts/helper_files.py) and walks each syntax tree at any depth. The
parts run in one namespace, so an import alias made in one file is known in
every file. It refuses, naming the file and the line:
  - a `shell=` keyword on any call unless its value is the literal False;
  - any reference to `os.system`, `os.popen`, `subprocess.getoutput`,
    `subprocess.getstatusoutput` or asyncio's `create_subprocess_shell`,
    through an alias, a `from` import or a `getattr` with a constant name;
    a `getattr` on `os` or `subprocess` with a computed name; and a star
    import from either;
  - a string constant that names a shell (`sh`, `bash`, `/bin/sh`,
    `bash -c ...`), anywhere but a docstring: an argv headed by a shell
    needs one;
  - a launcher (`subprocess.run`, `call`, `check_call`, `check_output`,
    `Popen`, `os.execv`, `execve`, `execvp`, `execvpe`) whose command is
    built as a string (a literal, an f-string, a `+` or `%` over one, a
    `.format` or a `.join`), or that takes `**` keywords, which could carry
    `shell`.

`script_census` reads the shipped QML, its code-behinds and the model
(release.py's shipped_code and scripts/model_files.py: no glob, no hand
list) through the gate's own tokenizer, so a comment is never read as code.
It refuses:
  - a string or template literal that names a shell, as above;
  - `execDetached(` handed a string or a template;
  - a `command:` binding or a `command =` assignment whose value opens
    with a string or a template.

What neither reader can see, stated so nobody takes it for covered: a
command string built in a variable first and launched by name
(`var c = a + b; proc.command = c`), a shell reached through `env` with a
computed name, and a Python launcher called through a variable. The node
checks hold the content of the named argv builders.

Python 3 standard library only.
"""
import ast
import importlib.util
import os
import pathlib
import re
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import helper_files  # noqa: E402  the helper's files, read from its stub (D-REL-7)
import model_files  # noqa: E402  the model's parts, read from Model.mjs (D-REL-5)
import release  # noqa: E402  shipped_code: the QML main ships and its code-behinds

_spec = importlib.util.spec_from_file_location(
    "check_model_members", str(ROOT / "scripts" / "check-model-members.py"))
members = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(members)

SHELLS = ("ash", "bash", "busybox", "csh", "dash", "fish", "ksh", "mksh", "sh", "tcsh", "zsh")
# The text opens with a shell's name, bare or as a path, and the name ends
# there: "sh", "/bin/sh", "bash -c x". "shell" and "show" do not match.
SHELL_TEXT = re.compile(r"^\s*(?:\S*/)?(?:%s)(?:\s|$)" % "|".join(SHELLS))

FORBIDDEN = frozenset((
    "os.system", "os.popen", "posix.system", "posix.popen",
    "subprocess.getoutput", "subprocess.getstatusoutput",
    "asyncio.create_subprocess_shell", "asyncio.subprocess.create_subprocess_shell"))
SUBPROCESS_LAUNCHERS = frozenset(
    "subprocess." + n for n in ("run", "call", "check_call", "check_output", "Popen"))
EXEC_LAUNCHERS = frozenset("os." + n for n in ("execv", "execve", "execvp", "execvpe"))
OPAQUE_MODULES = frozenset(("os", "posix", "subprocess"))
BACKSLASH = chr(92)


def names_a_shell(text):
    return bool(SHELL_TEXT.match(text))


# ------------------------------------------------------------- python ----

def _aliases(trees):
    """name -> dotted name, for every import in every file (one namespace)."""
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


def _dotted(node, table):
    if isinstance(node, ast.Name):
        return table.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value, table)
        return None if head is None else "%s.%s" % (head, node.attr)
    return None


def _stringy(node):
    """True when `node` builds a string: a command line, not an argv."""
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, bytes))
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return _stringy(node.left) or _stringy(node.right)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("format", "join")):
        return True
    return False


def _docstrings(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(body[0].value)
    return out


def python_census(root, rels=None):
    """Read every file in `rels` (repo-relative to `root`; by default the
    helper's files as the stub lists them). Returns `files`, `launchers`
    (the dotted name of every launcher call read, in order) and `findings`,
    a list of (file, line, what)."""
    if rels is None:
        rels = helper_files.helper_paths(str(root))
    trees = [(rel, ast.parse(helper_files.read(str(root), rel), filename=rel)) for rel in rels]
    table = _aliases([tree for _, tree in trees])
    findings, launchers = [], []
    for rel, tree in trees:
        docs = _docstrings(tree)
        for node in ast.walk(tree):
            line = getattr(node, "lineno", 0)
            if isinstance(node, ast.ImportFrom) and node.module and not node.level:
                for alias in node.names:
                    if alias.name == "*" and node.module.split(".")[0] in OPAQUE_MODULES:
                        findings.append((rel, line, "star import from %s" % node.module))
                    elif "%s.%s" % (node.module, alias.name) in FORBIDDEN:
                        findings.append((rel, line, "%s.%s runs a shell" % (node.module, alias.name)))
            elif isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
                name = _dotted(node, table)
                if name in FORBIDDEN:
                    findings.append((rel, line, "%s runs a shell" % name))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node not in docs and names_a_shell(node.value):
                    findings.append((rel, line, "a string names a shell"))
            elif isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == "shell" and not (
                            isinstance(keyword.value, ast.Constant) and keyword.value.value is False):
                        findings.append((rel, line, "shell= is not the literal False"))
                name = _dotted(node.func, table)
                if name == "getattr" and len(node.args) >= 2:
                    owner, attr = _dotted(node.args[0], table), node.args[1]
                    if isinstance(attr, ast.Constant) and isinstance(attr.value, str):
                        if "%s.%s" % (owner, attr.value) in FORBIDDEN:
                            findings.append((rel, line, "%s.%s runs a shell" % (owner, attr.value)))
                    elif owner in OPAQUE_MODULES:
                        findings.append((rel, line, "getattr of a computed name on %s" % owner))
                if name in SUBPROCESS_LAUNCHERS or name in EXEC_LAUNCHERS:
                    launchers.append(name)
                    if any(k.arg is None for k in node.keywords):
                        findings.append((rel, line, "%s takes ** keywords" % name))
                    if name in SUBPROCESS_LAUNCHERS:
                        command = [k.value for k in node.keywords if k.arg == "args"] + node.args[:1]
                    else:
                        command = node.args[1:2]
                    if any(_stringy(c) for c in command):
                        findings.append((rel, line, "%s is handed a command built as a string" % name))
    return {"files": list(rels), "launchers": launchers, "findings": findings}


# ------------------------------------------------------- qml, js, mjs ----

def _template_piece(text, starts, tok):
    """The literal text of one template piece: from just after the backtick
    or the `}` its token stands on (the tokenizer keeps the place, not the
    text) to the closing backtick or the next `${`."""
    j = starts[tok.line - 1] + tok.col
    begin = j
    while j < len(text):
        if text[j] == BACKSLASH:
            j += 2
            continue
        if text[j] == "`" or text.startswith("${", j):
            break
        j += 1
    return text[begin:j]


def _opens_a_string(tok):
    return tok is not None and tok.kind in ("str", "tmpl")


def judge_script(label, text):
    """-> (findings, sites) for one QML, code-behind or model file's text:
    findings as (label, line, what), sites as a dict counting the
    `execDetached` calls and the `command` bindings and assignments read."""
    toks = members.tokens(text)
    starts = [0]
    for line in text.split("\n")[:-1]:
        starts.append(starts[-1] + len(line) + 1)
    findings = []
    sites = {"execDetached": 0, "command": 0}
    for k, tok in enumerate(toks):
        nxt = toks[k + 1] if k + 1 < len(toks) else None
        after = toks[k + 2] if k + 2 < len(toks) else None
        if tok.kind == "str" and names_a_shell(tok.text):
            findings.append((label, tok.line, "a string names a shell"))
        elif tok.kind == "tmpl" and names_a_shell(_template_piece(text, starts, tok)):
            findings.append((label, tok.line, "a string names a shell"))
        elif tok.kind == "ident" and tok.text == "execDetached":
            if nxt is not None and nxt.kind == "punct" and nxt.text == "(":
                sites["execDetached"] += 1
                if _opens_a_string(after):
                    findings.append((label, tok.line, "execDetached is handed a string"))
        elif tok.kind == "ident" and tok.text == "command":
            if nxt is None or nxt.kind != "punct" or nxt.text not in (":", "="):
                continue
            if nxt.text == "=" and after is not None and after.kind == "punct" and after.text in ("=", ">"):
                continue  # a comparison or an arrow, not an assignment
            sites["command"] += 1
            if _opens_a_string(after):
                findings.append((label, tok.line, "command is given a string"))
    return findings, sites


def shipped_scripts(root):
    """Every QML file main ships, the code-behinds it declares, the model's
    aggregator and its parts: repo-relative, each once."""
    root = str(root)
    rels = [os.path.relpath(entry.path, root) for entry in release.shipped_code(root)]
    rels.append(model_files.AGGREGATOR)
    rels.extend(model_files.part_paths(root))
    return rels


def script_census(root, rels=None):
    if rels is None:
        rels = shipped_scripts(root)
    findings = []
    sites = {"execDetached": 0, "command": 0}
    for rel in rels:
        with open(os.path.join(str(root), rel), encoding="utf-8") as fh:
            found, seen = judge_script(rel, fh.read())
        findings.extend(found)
        for key in sites:
            sites[key] += seen[key]
    return {"files": list(rels), "sites": sites, "findings": findings}


# -------------------------------------------------------------- cases ----

class TheHelperLaunchesFromArgvTest(unittest.TestCase):
    def test_no_helper_file_names_a_shell_or_builds_a_command_string(self):
        got = python_census(ROOT)
        self.assertEqual(got["findings"], [],
                         "the helper launches through a shell or from a string (CLAUDE.md "
                         "constraint 2): %s" % got["findings"])

    def test_the_reader_reads_the_launches_the_helper_makes(self):
        got = python_census(ROOT)
        self.assertEqual(got["files"], helper_files.helper_paths(str(ROOT)))
        # The player's exec, the relay's exec and wl-paste's Popen: a reader
        # that lost its launcher table would count none of them.
        self.assertIn("os.execvpe", got["launchers"])
        self.assertIn("os.execve", got["launchers"])
        self.assertIn("subprocess.Popen", got["launchers"])


class TheShellLaunchesFromArgvTest(unittest.TestCase):
    def test_no_shipped_script_names_a_shell_or_launches_a_string(self):
        got = script_census(ROOT)
        self.assertEqual(got["findings"], [],
                         "shipped QML or JavaScript launches through a shell or from a string "
                         "(CLAUDE.md constraint 2): %s" % got["findings"])

    def test_the_reader_reads_the_qml_the_code_behinds_and_the_model(self):
        got = script_census(ROOT)
        files = got["files"]
        self.assertEqual(len(files), len(set(files)))
        self.assertIn("Service.qml", files)
        self.assertIn("Service-player.js", files)
        self.assertIn("Model.mjs", files)
        self.assertIn("model/mpv.mjs", files)
        # Service.qml's Process blocks and assignments, and the code-behinds'
        # detached stops: a reader that lost its place would count fewer.
        self.assertGreaterEqual(got["sites"]["command"], 15)
        self.assertGreaterEqual(got["sites"]["execDetached"], 5)


class PythonMutantTest(unittest.TestCase):
    """Each case hands the reader a file it must refuse, or one it must not."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="argv-")
        self.addCleanup(shutil.rmtree, self.tmp)

    def judge(self, text, name="part.py"):
        with open(os.path.join(self.tmp, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        return python_census(self.tmp, [name])["findings"]

    def whats(self, text):
        return [(line, what) for _, line, what in self.judge(text)]

    def test_shell_true_is_refused(self):
        found = self.whats('import subprocess\n\ndef f(url):\n    subprocess.run("mpv " + url, shell=True)\n')
        self.assertEqual(found, [(4, "shell= is not the literal False"),
                                 (4, "subprocess.run is handed a command built as a string")])

    def test_a_computed_shell_keyword_is_refused_and_a_literal_false_passes(self):
        self.assertEqual(self.whats("import subprocess\nsubprocess.run(argv, shell=flag)\n"),
                         [(2, "shell= is not the literal False")])
        self.assertEqual(self.whats("import subprocess\nsubprocess.run(argv, shell=False)\n"), [])

    def test_os_system_and_popen_are_refused(self):
        self.assertEqual(self.whats('import os\n\ndef f():\n    os.system("mpv x")\n'),
                         [(4, "os.system runs a shell")])
        self.assertEqual(self.whats("import os\nout = os.popen(cmd).read()\n"),
                         [(2, "os.popen runs a shell")])

    def test_an_alias_a_from_import_and_a_getattr_are_followed(self):
        self.assertEqual(self.whats("import os as o\nrun = o.system\n"), [(2, "os.system runs a shell")])
        self.assertEqual(self.whats("from os import system as s\n\ndef f(c):\n    s(c)\n"),
                         [(1, "os.system runs a shell"), (4, "os.system runs a shell")])
        self.assertEqual(self.whats("import os\ngetattr(os, 'system')(c)\n"), [(2, "os.system runs a shell")])
        self.assertEqual(self.whats("import os\ngetattr(os, name)(c)\n"),
                         [(2, "getattr of a computed name on os")])
        self.assertEqual(self.whats("import os\nflag = getattr(os, 'O_NOFOLLOW', 0)\n"), [])
        self.assertEqual(self.whats("from subprocess import *\n"), [(1, "star import from subprocess")])
        self.assertEqual(self.whats("import subprocess as sp\nsp.getoutput(c)\n"),
                         [(2, "subprocess.getoutput runs a shell")])

    def test_an_alias_made_in_one_file_is_known_in_the_next(self):
        with open(os.path.join(self.tmp, "a.py"), "w", encoding="utf-8") as fh:
            fh.write("import os as o\n")
        with open(os.path.join(self.tmp, "b.py"), "w", encoding="utf-8") as fh:
            fh.write("def f(c):\n    o.system(c)\n")
        self.assertEqual(python_census(self.tmp, ["a.py", "b.py"])["findings"],
                         [("b.py", 2, "os.system runs a shell")])

    def test_an_argv_headed_by_a_shell_is_refused(self):
        self.assertEqual(self.whats('import subprocess\nsubprocess.run(["bash", "-c", cmd])\n'),
                         [(2, "a string names a shell")])
        self.assertEqual(self.whats('import os\nos.execvp("/bin/sh", ["sh", "-c", cmd])\n'),
                         [(2, "a string names a shell"), (2, "a string names a shell")])
        self.assertEqual(self.whats('ARGV = ("env", "zsh", "-lc", cmd)\n'), [(1, "a string names a shell")])
        self.assertEqual(self.whats('line = "sh -c " + cmd\n'), [(1, "a string names a shell")])

    def test_words_that_only_begin_like_a_shell_pass(self):
        text = ('a = ["show", "shell", "fishing", "dashboard", "bashful", "--sh"]\n'
                'b = "the sh in the middle"\n')
        self.assertEqual(self.whats(text), [])

    def test_a_docstring_that_names_a_shell_is_not_code(self):
        text = 'def f():\n    """bash -c is never used here.\n    sh neither.\n    """\n    # sh -c\n    return 1\n'
        self.assertEqual(self.whats(text), [])

    def test_a_command_built_as_a_string_is_refused(self):
        self.assertEqual(self.whats('import subprocess\nsubprocess.Popen(f"mpv {url}")\n'),
                         [(2, "subprocess.Popen is handed a command built as a string")])
        self.assertEqual(self.whats('import subprocess\nsubprocess.call("mpv %s" % url)\n'),
                         [(2, "subprocess.call is handed a command built as a string")])
        self.assertEqual(self.whats('import subprocess\nsubprocess.check_output(args=" ".join(argv))\n'),
                         [(2, "subprocess.check_output is handed a command built as a string")])
        self.assertEqual(self.whats('import os\nos.execvp("mpv", "mpv " + url)\n'),
                         [(2, "os.execvp is handed a command built as a string")])

    def test_argv_lists_pass(self):
        text = ('import os, subprocess\n\ndef f(argv, env, relay, player):\n'
                '    subprocess.Popen(argv, close_fds=True)\n'
                '    subprocess.run(["wl-paste", "--no-newline"] + argv)\n'
                '    os.execvpe("mpv", argv, env)\n'
                '    os.execve(relay[0], relay + ["--child=%d" % player], env)\n')
        self.assertEqual(self.whats(text), [])

    def test_star_keywords_on_a_launcher_are_refused(self):
        self.assertEqual(self.whats("import subprocess\nsubprocess.run(argv, **options)\n"),
                         [(2, "subprocess.run takes ** keywords")])

    def test_each_of_the_boards_helper_mutants_is_found_in_a_copy_of_the_real_helper(self):
        # F-GATE-31's row: these passed every check the gate had.
        for added, whats in (
                ('import subprocess\n    subprocess.run("mpv " + url, shell=True)',
                 ["shell= is not the literal False", "subprocess.run is handed a command built as a string"]),
                ('import os\n    os.system("mpv x")', ["os.system runs a shell"]),
                ('import subprocess\n    subprocess.run(["bash", "-c", url])', ["a string names a shell"])):
            tmp = tempfile.mkdtemp(prefix="argv-real-")
            self.addCleanup(shutil.rmtree, tmp)
            helper_files.copy_helper(str(ROOT), tmp)
            last = helper_files.part_paths(tmp)[-1]
            with open(os.path.join(tmp, last), "a", encoding="utf-8") as fh:
                fh.write("\n\ndef _mutant(url):\n    %s\n" % added)
            found = python_census(tmp)["findings"]
            self.assertEqual([what for _, _, what in found], whats)
            self.assertEqual({rel for rel, _, _ in found}, {last})


class ScriptMutantTest(unittest.TestCase):
    def whats(self, text):
        return [(line, what) for _, line, what in judge_script("x.qml", text)[0]]

    def test_an_argv_headed_by_a_shell_is_refused(self):
        self.assertEqual(self.whats('function f(cmd) {\n  Quickshell.execDetached(["sh", "-c", cmd])\n}\n'),
                         [(2, "a string names a shell")])
        self.assertEqual(self.whats('Process {\n  command: ["/usr/bin/bash", "-c", root.line]\n}\n'),
                         [(2, "a string names a shell")])
        self.assertEqual(self.whats("var a = ['env', 'zsh']\n"), [(1, "a string names a shell")])
        self.assertEqual(self.whats("var a = `bash -c ${x}`\n"), [(1, "a string names a shell")])
        self.assertEqual(self.whats("var a = `${dir}/x`\nvar b = `${x}sh -c y`\nvar c = [`zsh`]\n"),
                         [(2, "a string names a shell"), (3, "a string names a shell")])
        self.assertEqual(self.whats("var a = `${x} then show ${y} shell`\n"), [])

    def test_exec_detached_handed_a_string_is_refused(self):
        self.assertEqual(self.whats('Quickshell.execDetached("mpv " + url)\n'),
                         [(1, "execDetached is handed a string")])
        self.assertEqual(self.whats("Quickshell.execDetached(`mpv ${url}`)\n"),
                         [(1, "execDetached is handed a string")])

    def test_a_command_given_a_string_is_refused(self):
        self.assertEqual(self.whats('Process {\n  id: p\n  command: "mpv " + root.url\n}\n'),
                         [(3, "command is given a string")])
        self.assertEqual(self.whats('function f() {\n  p.command = "mpv " + url\n}\n'),
                         [(2, "command is given a string")])
        self.assertEqual(self.whats("function f() {\n  p.command = `mpv ${url}`\n}\n"),
                         [(2, "command is given a string")])

    def test_argv_lists_builders_and_a_json_key_pass(self):
        text = ('Process {\n  command: ["which", "mpv"]\n}\n'
                'Process {\n  command: Model.stateInitArgv(root.helperPath, root.stateDir)\n}\n'
                'function f(argv, command, requestId) {\n'
                '  run.command = argv\n'
                '  Quickshell.execDetached(Model.helperArgv(root.helperPath, argv))\n'
                '  Quickshell.execDetached(["mkdir", "-p", root.dir + "/sources"])\n'
                '  sock.write(JSON.stringify({ command: command, request_id: requestId }))\n'
                '  if (x.command == "show") return\n'
                '}\n')
        found, sites = judge_script("x.qml", text)
        self.assertEqual(found, [])
        self.assertEqual(sites, {"execDetached": 2, "command": 4})

    def test_a_comment_that_names_a_shell_is_not_code(self):
        text = '// never ["sh", "-c", x]\n/* execDetached("bash -c") */\nvar a = ["show", "shell"]\n'
        self.assertEqual(self.whats(text), [])

    def test_the_boards_code_behind_mutant_is_found_in_the_real_file(self):
        # F-GATE-31's row: Quickshell.execDetached(["sh", "-c", cmd]) in
        # Service-player.js passed every check the gate had.
        with open(str(ROOT / "Service-player.js"), encoding="utf-8") as fh:
            text = fh.read()
        lines = text.count("\n")
        self.assertEqual(judge_script("Service-player.js", text)[0], [])
        text += '\nfunction mutant(root, cmd) {\n  Quickshell.execDetached(["sh", "-c", cmd])\n}\n'
        self.assertEqual(judge_script("Service-player.js", text)[0],
                         [("Service-player.js", lines + 3, "a string names a shell")])

    def test_a_shell_named_in_a_model_part_is_found(self):
        tmp = tempfile.mkdtemp(prefix="argv-model-")
        self.addCleanup(shutil.rmtree, tmp)
        os.makedirs(os.path.join(tmp, "model"))
        rel = "model/mpv.mjs"
        with open(str(ROOT / rel), encoding="utf-8") as fh:
            text = fh.read()
        lines = text.count("\n")
        with open(os.path.join(tmp, rel), "w", encoding="utf-8") as fh:
            fh.write(text + '\nexport function mutantArgv(cmd) {\n  return ["bash", "-c", cmd]\n}\n')
        self.assertEqual(script_census(tmp, [rel])["findings"], [(rel, lines + 3, "a string names a shell")])


if __name__ == "__main__":
    unittest.main()
