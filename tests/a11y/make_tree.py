"""Build a throwaway QML import tree in which the guide's content can be
instantiated inside a plain QQuickWindow.

Nothing here is written back into the repo or into /usr/share.
Every transform prints the lines it changed, so the delta is auditable.
"""
import os
import re
import shutil
import sys

# The kit is read from where fidelity.py grades it (OMARCHY_PATH), so a tree
# built against another Omarchy is graded against the same one.
SHELL = os.environ.get("OMARCHY_PATH", "/usr/share/omarchy") + "/shell"
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
    """Delete each brace-balanced QML block whose first line matches a regex.
    Returns the text, the (first, last) line of each removed block, and each
    removed block's own text."""
    lines = text.split("\n")
    out = []
    i = 0
    removed = []
    blocks = []
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
            blocks.append("\n".join(lines[start:i]))
            continue
        out.append(line)
        i += 1
    return "\n".join(out), removed, blocks


# What the tree holds of the host's qs.Commons, decided FILE BY FILE
# (F-HARNESS-99, 2026-11-06). Importing a QML module compiles every SINGLETON
# its qmldir names, for each file that imports the module, used or not
# (measured on omarchy 4.5.0-3: an unused singleton whose file is missing, or
# one that imports Quickshell.Hyprland, breaks every importer); a plain type
# is compiled only where it is used. 4.5.0 named eight more types than 4.0.6,
# and a builder that copied four by name turned test_bar_shown_names and the
# whole accessibility harness red with "Type AudioNodes unavailable".
#
#   copy       byte-identical: the module file, every .js helper, a singleton
#              that imports no Quickshell, and a PLAIN type (compiled only
#              where used; no probe uses ShellIpc or Translations, and a probe
#              that ever does fails loudly at load, which is the right
#              failure: the unchanged file is the faithful one)
#   transform  a singleton whose Quickshell use is I/O alone: its Process,
#              FileView, Connections and IpcHandler blocks and its Quickshell
#              imports are removed, what the removed ids answered reads as
#              empty, a Quickshell `Singleton` root becomes an Item, the
#              QtQuick type that holds child objects (a QtObject cannot: a
#              default property a document declares is not the default of
#              its own root, measured), and Quickshell.env reads "" (PROBE
#              SHIM)
#   stub       a singleton whose LOGIC stands on a Quickshell service, which
#              no transform can remove without inventing an answer
#
# A host file in no row stops the build with its name, so the next host
# update is a decision here rather than a load error in an unrelated test.
# Every file this changes must be declared, with its reason, in
# fidelity.KIT_PATCHED, and every Commons declaration there must be a file
# this changes: the build checks both, by calling, so the builder and the
# guard cannot drift (rule 13).
COMMONS = {
    "qmldir": "copy",
    "Border.qml": "copy",
    "BorderGeometry.js": "copy",
    "AudioNodesModel.js": "copy",
    "Numbers.js": "copy",
    "Plural.js": "copy",
    "ShellIpc.qml": "copy",
    "Translations.qml": "copy",
    "Color.qml": "transform",
    "Style.qml": "transform",
    "Util.qml": "transform",
    "I18n.qml": "transform",
    "AudioNodes.qml": "transform",
    "InputDevices.qml": "transform",
    "InputMethodState.qml": "transform",
    "IpcRegistry.qml": "transform",
    "UntypedInput.qml": "stub",
}

QS_BLOCKS = ("Process", "FileView", "Connections", "IpcHandler")
BLOCK_STARTS = [r"^\s*property (?:%s) \w+\s*:" % "|".join(QS_BLOCKS),
                r"^\s*(?:%s)\s*\{" % "|".join(QS_BLOCKS)]
# Quickshell-only names that must not survive a transform in code.
QS_ONLY = r"\b(?:Quickshell|Singleton|Process|FileView|Connections|IpcHandler|SplitParser|StdioCollector|Pipewire|PwNode|Hyprland)\b"


def code_only(text):
    """The text with // comments removed (a // after a space or at a line's
    start; a URL's // inside a string is preceded by a colon)."""
    return "\n".join(re.sub(r"(^|\s)//.*$", r"\1", line) for line in text.split("\n"))


def qmldir_types(path):
    """{file: is_singleton} for every type a qmldir names."""
    out = {}
    for line in open(path).read().split("\n"):
        words = line.split()
        singleton = bool(words) and words[0] == "singleton"
        if singleton:
            words = words[1:]
        if len(words) >= 2 and re.match(r"^[A-Z]\w*$", words[0]) and words[-1].endswith((".qml", ".js")):
            out[words[-1]] = singleton
    return out


def transform_commons(name, text):
    """One Commons singleton, its Quickshell I/O removed (see COMMONS)."""
    before = len(text.split("\n"))
    text, removed, blocks = strip_blocks(text, BLOCK_STARTS)
    gone = []
    for block in blocks:
        m = re.match(r"^\s*property \w+ (\w+)\s*:", block)
        if m:
            gone.append(m.group(1))
        gone.extend(re.findall(r"^\s*id:\s*(\w+)", block, re.M))
    gone = sorted(set(gone))
    text = re.sub(r"^import Quickshell(?:\.\w+)*[ \t]*\n", "", text, flags=re.M)
    holder = bool(re.search(r"^Singleton \{", text, re.M))
    text = re.sub(r"^Singleton \{", "Item {", text, count=1, flags=re.M)
    # Quickshell.env -> the real environment, same answer, no Quickshell.
    text = re.sub(r'Quickshell\.env\((\s*"[^"]*"\s*)\)', r"shimEnv(\1)", text)
    text = re.sub(r"Quickshell\.execDetached\([^\n]*\)", "void(0)", text)
    # The deleted blocks leave their ids behind: starting one is a no-op, a
    # file one read reads as empty, one that ran reads as not running, and
    # one passed as a value is null. Any other use stops the build.
    for dead in gone:
        text = re.sub(r"\b%s\.(?:running|command)\s*=\s*[^\n;}]+" % dead, "void(0)", text)
        text = re.sub(r"\b%s\.text\(\)" % dead, '""', text)
        text = re.sub(r"\b%s\.(?:reload|restart|start|write)\([^()\n]*\)" % dead, "void(0)", text)
        text = re.sub(r"\b%s\.running\b" % dead, "false", text)
        text = re.sub(r"\(%s\)" % dead, "(null)", text)
        if re.search(r"\b%s\b" % dead, code_only(text)):
            raise SystemExit("make_tree: Commons/%s still names %s, a block the transform removed; "
                             "decide what it reads as here" % (name, dead))
    left = re.search(QS_ONLY, re.sub(r"^pragma Singleton[ \t]*$", "", code_only(text), flags=re.M))
    if left:
        raise SystemExit("make_tree: Commons/%s still uses %s after the transform; "
                         "stub it or extend the transform" % (name, left.group(0)))
    marker = ("Item" if holder else "QtObject") + " {\n  id: root\n"
    if marker not in text:
        raise SystemExit("make_tree: Commons/%s has no `%s` root to shim" % (name, marker.split("\n")[0]))
    text = text.replace(marker, marker + """
  // PROBE SHIM: the only substitute in this tree. Supplies the values the
  // deleted Quickshell.Io blocks would have loaded. Affects colours and
  // metrics only; it declares no Accessible property of any kind.
  function shimEnv(key) { return "" }
""" + ("""  // PROBE SHIM: the host's root was Quickshell's Singleton; this Item
  // stands in for it, holds the same children, and is never drawn.
""" if holder else ""), 1)
    return text, before, removed, gone


def commons():
    src = os.path.join(SHELL, "Commons")
    dst = os.path.join(TREE, "qs", "Commons")
    os.makedirs(dst, exist_ok=True)
    present = sorted(os.listdir(src))
    unknown = [f for f in present if f not in COMMONS]
    if unknown:
        raise SystemExit("make_tree: the host's Commons/ holds %s, which this tree neither copies, "
                         "transforms nor stubs; decide which in make_tree.COMMONS (F-HARNESS-99)"
                         % ", ".join(unknown))
    types = qmldir_types(os.path.join(src, "qmldir"))
    absent = sorted(f for f in types if f not in present)
    if absent:
        raise SystemExit("make_tree: the host's Commons/qmldir names %s, which is not in Commons/"
                         % ", ".join(absent))
    sys.path.insert(0, HERE)
    import fidelity
    changed = []
    for name in present:
        how = COMMONS[name]
        path = os.path.join(src, name)
        text = open(path).read()
        imports_qs = bool(re.search(r"^import Quickshell", text, re.M))
        if how == "copy":
            if types.get(name) and imports_qs:
                raise SystemExit("make_tree: Commons/%s is a singleton that imports Quickshell; "
                                 "copied unchanged it breaks every importer" % name)
            shutil.copy(path, dst)
            log("commons", "%s copied unchanged" % name)
        elif how == "transform":
            out, before, removed, gone = transform_commons(name, text)
            open(os.path.join(dst, name), "w").write(out)
            changed.append(name)
            log("commons", "%s: %d lines -> %d; removed I/O blocks at %s; dangling ids %s"
                % (name, before, len(out.split("\n")), removed or "none", ", ".join(gone) or "none"))
        else:
            open(os.path.join(dst, name), "w").write(
                ("pragma Singleton\n" if types.get(name) else "") + "import QtQuick\n\n"
                "// PROBE STUB: the host's %s stands on a Quickshell service that\n"
                "// plain qml cannot load. No probe runs it; it is here because\n"
                "// importing qs.Commons compiles every singleton the qmldir names.\n"
                "QtObject {}\n" % name)
            changed.append(name)
            log("commons", "%s: PROBE STUB (compiled, never run)" % name)
    declared = sorted(k.split("/", 1)[1] for k in fidelity.KIT_PATCHED if k.startswith("Commons/"))
    undeclared = sorted(set(changed) - set(declared))
    stale = sorted(n for n in set(declared) - set(changed) if n in present)
    if undeclared or stale:
        raise SystemExit("make_tree: fidelity.KIT_PATCHED does not match what this builds: changed but "
                         "undeclared %s; declared but unchanged %s" % (undeclared or "none", stale or "none"))


def ui():
    """Copy the host kit and patch ONLY the files that import Quickshell and
    are actually instantiated. 7 of 39 import it on omarchy 4.5.0-3 (6 of 33
    on 4.0.6; the log line below counts them on every build); the guide's
    closure uses none of them, the bar widget uses exactly one."""
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
    # The model is Model.mjs and the parts under model/ it names (D-REL-5),
    # copied at their own relative paths so the copy's imports resolve.
    sys.path.insert(0, os.path.join(REPO, "scripts"))
    import model_files
    model_files.copy_model(REPO, TREE)
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
