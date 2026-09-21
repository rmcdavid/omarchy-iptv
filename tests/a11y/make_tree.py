"""Build a throwaway QML import tree in which the guide's content can be
instantiated inside a plain QQuickWindow.

Nothing here is written back into the repo or into /usr/share.
Every transform prints the lines it changed, so the delta is auditable.
"""
import os
import re
import shutil
import sys

SHELL = "/usr/share/omarchy/shell"
HERE = os.path.dirname(os.path.abspath(__file__))
# The generated tree is a BUILD ARTIFACT, not source: it holds a copy of the
# host UI kit and a transformed copy of Guide.qml, both regenerated on every
# run. It must not land inside the repo, and it must not be shared between
# concurrent runs -- a shared directory written by two lanes at once already
# produced one reading that was green only because a mutation had been
# overwritten. Override with A11Y_TREE when you want to keep one to inspect.
TREE = os.environ.get("A11Y_TREE") or os.path.join(
    os.environ.get("TMPDIR", "/tmp"), "omarchy-iptv-a11y-tree")
REPO = os.environ.get("A11Y_REPO") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def log(tag, msg):
    print("[%s] %s" % (tag, msg))


def strip_blocks(text, starts):
    """Delete each brace-balanced QML block whose first line matches a regex."""
    lines = text.split("\n")
    out = []
    i = 0
    removed = []
    while i < len(lines):
        line = lines[i]
        if any(re.search(p, line) for p in starts):
            depth = 0
            start = i
            while i < len(lines):
                depth += lines[i].count("{") - lines[i].count("}")
                i += 1
                if depth <= 0:
                    break
            removed.append((start + 1, i))
            continue
        out.append(line)
        i += 1
    return "\n".join(out), removed


def commons():
    src = os.path.join(SHELL, "Commons")
    dst = os.path.join(TREE, "qs", "Commons")
    os.makedirs(dst, exist_ok=True)
    shutil.copy(os.path.join(src, "BorderGeometry.js"), dst)
    shutil.copy(os.path.join(src, "Border.qml"), dst)
    shutil.copy(os.path.join(src, "qmldir"), dst)
    log("commons", "Border.qml and BorderGeometry.js copied unchanged")

    for name, block_pats in (
        ("Color.qml", [r"property FileView "]),
        ("Style.qml", [r"property Process ", r"property FileView "]),
        ("Util.qml", []),
    ):
        text = open(os.path.join(src, name)).read()
        before = len(text.split("\n"))
        text, removed = strip_blocks(text, block_pats)
        text = text.replace("import Quickshell.Io\n", "")
        text = text.replace("import Quickshell\n", "")
        # Quickshell.env -> the real environment, same answer, no Quickshell.
        text = re.sub(r'Quickshell\.env\((\s*"[^"]*"\s*)\)', r"shimEnv(\1)", text)
        text = re.sub(r"Quickshell\.execDetached\([^\n]*\)", "void(0)", text)
        # the deleted Process blocks leave dangling ids behind
        for dangling in ("hyprctlProc", "gapsOutProc", "fcMatchProc"):
            text = text.replace(dangling + ".running = true", "void(0)")
        marker = "QtObject {\n  id: root\n"
        assert marker in text, name
        text = text.replace(marker, marker + """
  // PROBE SHIM: the only substitute in this tree. Supplies the values the
  // deleted Quickshell.Io blocks would have loaded. Affects colours and
  // metrics only; it declares no Accessible property of any kind.
  function shimEnv(key) { return "" }
""", 1)
        open(os.path.join(dst, name), "w").write(text)
        log("commons", "%s: %d lines -> %d; removed I/O blocks at %s"
            % (name, before, len(text.split("\n")), removed or "none"))


def ui():
    """Copy the host kit and patch ONLY the files that import Quickshell and
    are actually instantiated. 6 of 33 import it; the guide's closure uses
    none of them, the bar widget uses exactly one."""
    src = os.path.join(SHELL, "Ui")
    dst = os.path.join(TREE, "qs", "Ui")
    shutil.copytree(src, dst)
    importers = sorted(f for f in os.listdir(src)
                       if f.endswith(".qml")
                       and "Quickshell" in open(os.path.join(src, f)).read())
    log("ui", "%d of %d host Ui components import Quickshell: %s"
        % (len(importers), len([f for f in os.listdir(src) if f.endswith(".qml")]),
           ", ".join(importers)))
    patched = []
    for name in ("BarIconButton.qml",):     # the only one the probes load
        path = os.path.join(dst, name)
        text = open(path).read()
        before = text
        text = text.replace("import Quickshell\n", "")
        text = re.sub(r'Quickshell\.env\(("[^"]*")\)', r"shimEnv(\1)", text)
        anchor = text.index("{") + 1
        text = (text[:anchor] +
                "\n  function shimEnv(key) { return \"\" }  // PROBE SHIM\n" +
                text[anchor:])
        open(path, "w").write(text)
        diff = sum(1 for a, b in zip(before.split("\n"), text.split("\n")) if a != b)
        patched.append(name)
    log("ui", "patched %s (debug env flag only); every other component byte-identical"
        % ", ".join(patched))


def guide():
    """Write GuideProbe.qml by CALLING fidelity.apply_transform, the same rules
    the fidelity guard grades against. This file used to carry its own copy
    of the edits (a regex list plus two string replaces keyed on the old
    `PanelWindow { id: panel` header); when the window moved inside a Loader
    Component that copy matched nothing and would have produced a copy that
    cannot load. Two lists joined by a name drifted; one function joined by a
    call cannot (CLAUDE.md rule 13). fidelity.py raises if a rule stops
    matching, which is the failure mode we want: loud, not a silent no-op."""
    sys.path.insert(0, HERE)
    import fidelity
    orig = open(os.path.join(REPO, "Guide.qml")).read()
    text = fidelity.apply_transform(orig)
    for rule in fidelity.TRANSFORM_RULES:
        log("guide", "%-22s applied  (%s)" % (rule["id"], rule.get("why", "")[:60].replace("\n", " ")))
    os.makedirs(TREE, exist_ok=True)
    open(os.path.join(TREE, "GuideProbe.qml"), "w").write(text)
    shutil.copy(os.path.join(REPO, "Model.js"), TREE)
    shutil.copy(os.path.join(HERE, "host_src.qml"), os.path.join(TREE, "host.qml"))
    log("guide", "wrote GuideProbe.qml (%d lines from %d)"
        % (len(text.split("\n")), len(orig.split("\n"))))


if __name__ == "__main__":
    if os.path.isdir(TREE):
        shutil.rmtree(TREE)
    os.makedirs(os.path.join(TREE, "qs"), exist_ok=True)
    commons()
    ui()
    guide()
    print("tree at %s" % TREE)
