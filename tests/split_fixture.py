"""A plugin root holding a split service, for the gate guards' tests
(D-REL-14 C2). NOT a test: tests/test_color_literals.py and the other
guards' tests import it.

tree(tmp, mutant) makes `tmp` a plugin root: the guards' fixture
(tests/fixtures/service-split/guards/: Service.qml and its one code-behind,
Service-demo.js, the `// MUTANT` line replaced by `mutant` when one is
given), a scripts/release.py holding only an ALLOWLIST that names them and
the model, and this tree's Model.mjs and model/ linked in, so every guard
reads it through release.py's shipped_code as it reads this tree.
shipped(root) is that shipped_code, and into_code(path, text, qml, js) puts a
line into a shipped file -- `qml` as the first member of a .qml's root
object, `js` as the first statement of a code-behind's first function -- so
a test that mutates every shipped file mutates a code-behind too.
"""

import importlib.util
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARDS = os.path.join(ROOT, "tests", "fixtures", "service-split", "guards")
MARK = "    // MUTANT\n"

_spec = importlib.util.spec_from_file_location("release", os.path.join(ROOT, "scripts", "release.py"))
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def tree(tmp, mutant=None):
    for name in ("Service.qml", "Service-demo.js"):
        text = read(os.path.join(GUARDS, name))
        if name == "Service-demo.js" and mutant is not None:
            if text.count(MARK) != 1:
                raise AssertionError("the fixture code-behind lost its MUTANT line")
            text = text.replace(MARK, "    " + mutant + "\n")
        write(os.path.join(tmp, name), text)
    os.makedirs(os.path.join(tmp, "scripts"), exist_ok=True)
    write(os.path.join(tmp, "scripts", "release.py"),
          '"""The guards\' fixture tree: its ALLOWLIST alone."""\nALLOWLIST = (\n'
          '    "Service.qml",\n    "Service-demo.js",\n    "Model.mjs",\n)\n')
    os.symlink(os.path.join(ROOT, "Model.mjs"), os.path.join(tmp, "Model.mjs"))
    os.symlink(os.path.join(ROOT, "model"), os.path.join(tmp, "model"))
    return tmp


def shipped(root):
    return release.shipped_code(root)


def into_code(path, text, qml, js):
    if path.endswith(".qml"):
        m = re.search(r"^[A-Z][\w.]*\s*\{\s*$", text, re.M)
        if m is None:
            raise AssertionError("%s: no root object found" % path)
        return text[:m.end()] + "\n  " + qml + text[m.end():]
    m = re.search(r"^  function [A-Za-z_]\w*\([^)]*\) \{[^\n]*$", text, re.M)
    if m is None:
        raise AssertionError("%s: no function found" % path)
    return text[:m.end()] + "\n    " + js + text[m.end():]
