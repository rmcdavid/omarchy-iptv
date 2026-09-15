"""The fidelity guard: the generated copy the AT-SPI harness grades must not
drift from the file that ships.

The problem
-----------
No window Quickshell creates publishes an accessibility tree
(docs/ACCESSIBILITY-INVESTIGATION.md section 6, upstream quickshell #1144), so
the harness cannot grade `Guide.qml` as it ships. It grades a GENERATED COPY
with the guide's content hoisted out of the `PanelWindow` into a plain hidden
`QQuickWindow`. Everything the harness claims rests on that copy still being
the shipping guide. Nothing checked that. A harness grading a drifted copy is
a subtler version of the grep it was built to replace: green, and about the
wrong file.

Why a hash cannot do it
-----------------------
The copy is DELIBERATELY different. The question is not "is it the same file"
but "does it still carry every accessibility-bearing declaration, attached to
the same element, and has the transform changed nothing else".

What this guard asserts
-----------------------
L1  No line the transform touches contains `Accessible.` at all. The transform
    is forbidden from editing accessibility markup, whatever else it does.
L2  Every line the copy adds or removes is attributed to exactly one declared
    rule in TRANSFORM_RULES below, with exact counts. An undeclared change is
    red, and a declared rule that did not fire is red too, so the table cannot
    rot into a permissive wildcard.
L3  The ACCESSIBILITY PROJECTION of the two files is equal, after exactly one
    declared attachment rewrite (`PanelWindow#panel` -> `Window#panel`). The
    projection is every `Accessible.*` binding AND every other binding on the
    same element, because Qt derives accessibility from more than the
    `Accessible` attached property: the credential this round is about
    (D-A11Y-1) is published from the field's `text:` binding. See qmlscan.py.
L4  Elements the transform ADDS declare no accessibility at all, so the copy
    cannot publish a node the shipping guide does not have.
L5  The shipping file declares no accessibility on the element the transform
    rehosts. That is the honest limit: an `Accessible.*` on the `PanelWindow`
    could not be graded faithfully by this harness, so its arrival must be
    red rather than quietly regraded under a different type.
L6  Files the transform copies verbatim (Model.js, which composes the row,
    source and bar names) are byte-identical.
L7  Inventory: every tracked .qml that declares accessibility and has no
    generated counterpart is named as an UNGRADED SURFACE, so a missing
    scenario is visible instead of absent.

This guard needs no display, no D-Bus and no Qt. It is pure text over two
files, it is the half of the harness that can run anywhere, and per
docs/PLAN-NEXT.md decision 9 neither half is wired into scripts/check.sh.

Stdlib only, ASCII only (CLAUDE.md rules 3 and 8).
"""

import argparse
import collections
import difflib
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qmlscan


SHELL_DIR = os.environ.get("OMARCHY_PATH", "/usr/share/omarchy") + "/shell"
REPO = os.environ.get("A11Y_REPO") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

# ---------------------------------------------------------------------------
# The transform, declared as data.
#
# Each rule is a contiguous block of lines in the shipping file and the block
# that replaces it. This table is BOTH the specification the guard attributes
# changes against and the executable transform (apply_transform below), so a
# generator and a checker cannot drift apart into two truths -- CLAUDE.md rule
# 13, a cross-document id joined by a check rather than by a name.
#
# `count` is exact. A rule that matches a different number of times is an
# error, not a silent partial application.
# ---------------------------------------------------------------------------
TRANSFORM_RULES = [
    {
        "id": "T1-imports",
        "why": "Quickshell's module and its Wayland layer-shell module do not "
               "exist outside the shell process; the plain Window type does.",
        "before": [
            "import Quickshell",
            "import Quickshell.Wayland",
        ],
        "after": [
            "import QtQuick.Window",
        ],
    },
    {
        "id": "T2-clipboard-shim",
        "why": "Two Quickshell singletons are reachable from ordinary "
               "functions. Neither is an accessibility sink; both would fail "
               "to resolve outside the shell. A local object stands in.",
        "before": [
            "Item {",
            "  id: root",
        ],
        "after": [
            "Item {",
            "  id: root",
            "",
            "  QtObject {",
            "    id: probeShim",
            "    property string clipboardText: \"\"",
            "    function execDetached(argv) { }",
            "  }",
        ],
    },
    {
        "id": "T3-execDetached",
        "why": "Clipboard write. Not an accessibility sink.",
        "before": ["    Quickshell.execDetached([\"wl-copy\", String(text)])"],
        "after": ["    probeShim.execDetached([\"wl-copy\", String(text)])"],
    },
    {
        "id": "T4-clipboardText",
        "why": "Clipboard read. Not an accessibility sink.",
        "before": ["    var text = Quickshell.clipboardText"],
        "after": ["    var text = probeShim.clipboardText"],
    },
    {
        "id": "T5-window",
        "why": "The one line this whole harness exists to route around. A "
               "PanelWindow is not a QQuickWindow and publishes no tree; a "
               "plain Window does. Its geometry came from the layer-shell "
               "anchors that go with it, so a fixed size replaces them, and "
               "the window is never shown (visible: false) so nothing maps on "
               "the compositor. `id`, `color` and every child are untouched.",
        "before": [
            "  PanelWindow {",
            "    id: panel",
            "    visible: root.opened",
            "    anchors { top: true; bottom: true; left: true; right: true }",
            "    color: \"transparent\"",
            "    WlrLayershell.namespace: \"omarchy-iptv\"",
            "    WlrLayershell.layer: WlrLayer.Overlay",
            "    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive",
            "    exclusionMode: ExclusionMode.Ignore",
        ],
        "after": [
            "  Window {",
            "    id: panel",
            "    visible: false",
            "    width: 1920",
            "    height: 1080",
            "    color: \"transparent\"",
        ],
    },
]

# The ONE attachment point the transform is allowed to rename, and the only
# reason L3 is not a plain equality. Anything else that moves is drift.
PATH_REWRITES = [("PanelWindow#panel", "Window#panel")]

# Elements that exist only in the copy. Each must declare no accessibility.
ADDED_ELEMENT_IDS = ["probeShim"]

# The element the transform rehosts: nothing accessibility-bearing may be
# declared directly on it (L5).
REHOSTED_ELEMENT_ID = "panel"


class Failure(object):
    def __init__(self, layer, summary, detail=""):
        self.layer = layer
        self.summary = summary
        self.detail = detail

    def __str__(self):
        out = "%s  %s" % (self.layer, self.summary)
        if self.detail:
            out += "\n" + "\n".join("        " + line
                                    for line in self.detail.split("\n"))
        return out


# ---------------------------------------------------------------------------
# The transform, executable.
# ---------------------------------------------------------------------------

def apply_transform(text, rules=None):
    """Produce the reference copy. Raises if a rule does not match exactly."""
    rules = TRANSFORM_RULES if rules is None else rules
    for rule in rules:
        before = "\n".join(rule["before"]) + "\n"
        after = "\n".join(rule["after"]) + "\n"
        want = rule.get("count", 1)
        got = text.count(before)
        if got != want:
            raise ValueError(
                "transform rule %s matched %d time(s), expected %d.\n"
                "The shipping file changed under the transform. Update the "
                "rule and re-read what it now removes." % (rule["id"], got, want))
        text = text.replace(before, after, want)
    return text


def _net_change(rule):
    """The lines a rule really removes and adds, ignoring its context lines."""
    removed = []
    added = []
    sm = difflib.SequenceMatcher(None, rule["before"], rule["after"],
                                 autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(rule["before"][i1:i2])
        if tag in ("replace", "insert"):
            added.extend(rule["after"][j1:j2])
    return removed, added


def transform_report(rules=None):
    """Human-readable statement of what the transform removes, keeps and adds."""
    rules = TRANSFORM_RULES if rules is None else rules
    lines = []
    for rule in rules:
        removed, added = _net_change(rule)
        lines.append("%s (x%d)  %s" % (rule["id"], rule.get("count", 1),
                                       rule["why"]))
        for line in removed:
            lines.append("    -  %s" % line)
        for line in added:
            lines.append("    +  %s" % line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# The layers.
# ---------------------------------------------------------------------------

def _diff_lines(source, generated):
    a = source.split("\n")
    b = generated.split("\n")
    removed = []
    added = []
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend((i1 + k + 1, a[i1 + k]) for k in range(i2 - i1))
        if tag in ("replace", "insert"):
            added.extend((j1 + k + 1, b[j1 + k]) for k in range(j2 - j1))
    return removed, added


def check_pair(source_text, generated_text, source_name="Guide.qml",
               generated_name="the generated copy", rules=None):
    """Grade one (shipping file, generated copy) pair. Returns [Failure]."""
    rules = TRANSFORM_RULES if rules is None else rules
    failures = []
    removed, added = _diff_lines(source_text, generated_text)

    # ---- L1: the transform may not touch accessibility markup -------------
    touched = [("-", n, t) for n, t in removed if "Accessible." in t] + \
              [("+", n, t) for n, t in added if "Accessible." in t]
    if touched:
        failures.append(Failure(
            "L1",
            "the transform touched %d accessibility-bearing line(s); it is "
            "not allowed to edit any" % len(touched),
            "\n".join("%s %s:%d  %s" % (sign, source_name if sign == "-"
                                        else generated_name, n, t.strip())
                      for sign, n, t in touched)))

    # ---- L2: every changed line attributed to a declared rule -------------
    removed_left = collections.Counter(t for _n, t in removed)
    added_left = collections.Counter(t for _n, t in added)
    for rule in rules:
        rule_removed, rule_added = _net_change(rule)
        count = rule.get("count", 1)
        missing = []
        for line in rule_removed:
            for _ in range(count):
                if removed_left[line] <= 0:
                    missing.append("-  " + line)
                else:
                    removed_left[line] -= 1
        for line in rule_added:
            for _ in range(count):
                if added_left[line] <= 0:
                    missing.append("+  " + line)
                else:
                    added_left[line] -= 1
        if missing:
            failures.append(Failure(
                "L2", "declared transform rule %s did not fire as declared "
                      "(%d line(s) it claims are missing from the diff)"
                      % (rule["id"], len(missing)),
                "\n".join(missing)))
    residual_removed = _residual(removed, removed_left)
    residual_added = _residual(added, added_left)
    if residual_removed or residual_added:
        detail = "\n".join(
            ["- %s:%d  %s" % (source_name, n, t) for n, t in residual_removed] +
            ["+ %s:%d  %s" % (generated_name, n, t) for n, t in residual_added])
        failures.append(Failure(
            "L2", "%d line(s) changed that no declared transform rule explains"
                  % (len(residual_removed) + len(residual_added)), detail))

    # ---- L3: the accessibility projection is unchanged --------------------
    try:
        src_proj = qmlscan.projection(source_text, source_name)
        gen_proj = qmlscan.projection(generated_text, generated_name)
    except qmlscan.QmlParseError as exc:
        failures.append(Failure("L3", "the scanner refused to parse", str(exc)))
        return failures
    for old, new in PATH_REWRITES:
        src_proj = [line.replace(old, new, 1) for line in src_proj]
    if src_proj != gen_proj:
        delta = [line for line in difflib.unified_diff(
            src_proj, gen_proj, fromfile=source_name + " (projection)",
            tofile=generated_name + " (projection)", lineterm="", n=1)]
        lost = len([d for d in delta if d.startswith("-")
                    and not d.startswith("---")])
        gained = len([d for d in delta if d.startswith("+")
                      and not d.startswith("+++")])
        failures.append(Failure(
            "L3", "the accessibility projection drifted: %d declaration(s) "
                  "lost, %d gained or altered" % (lost, gained),
            "\n".join(delta)))

    # ---- L4: added elements declare no accessibility ----------------------
    gen_records, _gen_frames = qmlscan.scan(generated_text, generated_name)
    for element_id in ADDED_ELEMENT_IDS:
        marker = "#%s" % element_id
        offenders = [r for r in gen_records
                     if marker in r["path"] and r["kind"] == "accessible"]
        if offenders:
            failures.append(Failure(
                "L4", "the element %s, which exists only in the copy, declares "
                      "accessibility the shipping file cannot have" % element_id,
                "\n".join("%s:%d  %s" % (generated_name, r["line"], r["prop"])
                          for r in offenders)))

    # ---- L5: nothing accessibility-bearing on the rehosted element --------
    src_records, _src_frames = qmlscan.scan(source_text, source_name)
    marker = "#%s" % REHOSTED_ELEMENT_ID
    on_window = [r for r in src_records
                 if r["kind"] == "accessible" and r["path"].endswith(marker)]
    if on_window:
        failures.append(Failure(
            "L5", "%d accessibility declaration(s) sit on the element the "
                  "transform rehosts. This harness cannot grade them: the copy "
                  "gives that element a different type and never shows it."
                  % len(on_window),
            "\n".join("%s:%d  %s = %s" % (source_name, r["line"], r["prop"],
                                          r["value"]) for r in on_window)))
    return failures


def _residual(changed, left):
    """The changed lines no rule consumed, with their line numbers, in order."""
    out = []
    for number, text in changed:
        if left[text] > 0:
            left[text] -= 1
            out.append((number, text))
    return out


def check_copy(source_path, copy_path):
    """L6: a file the transform copies verbatim must be byte-identical."""
    def digest(path):
        with open(path, "rb") as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    if not os.path.exists(copy_path):
        return [Failure("L6", "%s is missing from the harness tree"
                        % os.path.basename(copy_path))]
    if digest(source_path) != digest(copy_path):
        return [Failure("L6", "%s is not byte-identical to the shipping file"
                        % os.path.basename(copy_path),
                        "shipping %s\ncopy     %s"
                        % (digest(source_path), digest(copy_path)))]
    return []


# L7 fires for any accessibility-declaring surface nothing grades. These are
# the ones we have decided to leave ungraded FOR NOW, each with its reason, so
# the layer reports drift rather than restating a state we already know. Adding
# a name here is a decision that needs a board row; deleting one is free.
UNGRADED_ACCEPTED = {
    "BarWidget.qml":
        "no generated host yet. Its 2 declarations are graded by nobody, "
        "which is tracked as an open item, not accepted forever.",
}

KIT_PATCHED = {
    "Ui/BarIconButton.qml":
        "a debug env flag read through Quickshell.env",
    "Commons/Color.qml":
        "the FileView block that loads the theme",
    "Commons/Style.qml":
        "the Process and FileView blocks that read gaps and fonts",
    "Commons/Util.qml":
        "Quickshell.env and Quickshell.execDetached",
}


def check_kit(src_dir, copy_dir, patched=None):
    """L8: the host UI kit the copy imports is the kit that ships.

    The guide's fields ARE host components: `Ui/TextField.qml` is a QtQuick
    Controls TextField, and the credential the harness hunts is published by
    that control's own accessibility, not by anything Guide.qml declares. A
    guard that checks only Guide.qml would let the kit be swapped underneath
    it. The host kit declares no `Accessible.` property anywhere (measured:
    zero in Ui/ and Commons/), so every file must be byte-identical except
    the declared patched set, and no patch may introduce or remove one.
    """
    patched = KIT_PATCHED if patched is None else patched
    failures = []

    def listing(root):
        out = {}
        for base, _dirs, files in os.walk(root):
            for name in files:
                full = os.path.join(base, name)
                out[os.path.relpath(full, root)] = full
        return out

    # Keys are named the way the kit is: "Ui/TextField.qml", not the path a
    # particular caller happened to pass in.
    section = os.path.basename(src_dir.rstrip(os.sep))

    src = listing(src_dir)
    copy = listing(copy_dir)
    missing = sorted(set(src) - set(copy))
    extra = sorted(set(copy) - set(src))
    if missing:
        failures.append(Failure("L8", "%d host kit file(s) the copy does not "
                                      "have" % len(missing), "\n".join(missing)))
    if extra:
        failures.append(Failure("L8", "%d file(s) in the kit copy that the host "
                                      "kit does not have" % len(extra),
                                "\n".join(extra)))
    for rel in sorted(set(src) & set(copy)):
        with open(src[rel], "rb") as handle:
            a = handle.read()
        with open(copy[rel], "rb") as handle:
            b = handle.read()
        declared = "%s/%s" % (section, rel) in patched
        if a == b:
            if declared:
                failures.append(Failure(
                    "L8", "%s is declared as patched but is byte-identical; "
                          "the declaration is stale" % rel))
            continue
        if not declared:
            failures.append(Failure(
                "L8", "%s differs from the host kit and no patch is declared "
                      "for it" % rel))
            continue
        removed, added = _diff_lines(a.decode("utf-8", "replace"),
                                     b.decode("utf-8", "replace"))
        touched = [t for _n, t in removed + added if "Accessible." in t]
        if touched:
            failures.append(Failure(
                "L8", "the patch to %s touches accessibility markup" % rel,
                "\n".join(touched)))
    return failures


def guard_tree(tree_dir, repo=None, guide_copy="GuideProbe.qml",
               model_copy="Model.js", kit=None):
    """Grade a harness tree in one call, for the checker to use as its gate.

    The harness should refuse to report a result at all until this returns
    empty: a green run over a drifted copy is the failure mode this guard
    exists for, and it is worse than a red one because it looks like proof.

        import fidelity
        drift = fidelity.guard_tree(TREE)
        if drift:
            raise SystemExit("\\n".join(str(d) for d in drift))
    """
    repo = repo or REPO
    guide = os.path.join(repo, "Guide.qml")
    copy = os.path.join(tree_dir, guide_copy)
    if not os.path.exists(copy):
        return [Failure("L0", "no generated copy at %s" % copy)]
    with open(guide) as handle:
        source_text = handle.read()
    with open(copy) as handle:
        generated_text = handle.read()
    found = check_pair(source_text, generated_text, "Guide.qml", guide_copy)
    found.extend(check_copy(os.path.join(repo, "Model.js"),
                            os.path.join(tree_dir, model_copy)))

    # L8 and L7 used to be reachable ONLY from the command line, while this
    # function's own docstring told the checker to use it as its gate. So a
    # checker that did what it was told ran four layers of eight and could not
    # tell. Measured by the reviewer: swapping the host kit underneath the copy
    # turned a real credential failure green with this returning no findings.
    #
    # That is this project's oldest defect wearing a new hat. A thing named as
    # the complete check was not the complete check, and only the name said
    # otherwise (CLAUDE.md rule 13). The kit is the load-bearing case: the
    # guide's fields ARE host components, and the credential the harness hunts
    # is published by `Ui/TextField.qml`'s own accessibility rather than by
    # anything Guide.qml declares.
    if kit is not False:
        kit_src = kit or os.environ.get("A11Y_KIT_SRC") or SHELL_DIR
        kit_copy = os.path.join(tree_dir, "qs")
        if os.path.isdir(kit_copy) and os.path.isdir(kit_src):
            found.extend(check_kit(kit_src, kit_copy))
        else:
            found.append(Failure(
                "L8", "the host kit was not graded",
                "expected a copy at %s and a source at %s. Pass kit=False to "
                "say a tree has no kit ON PURPOSE. Silence is not an option "
                "here: an ungraded kit can be swapped underneath the copy and "
                "take a real failure green with it." % (kit_copy, kit_src)))

    for name, count in ungraded_surfaces(repo, {"Guide.qml"}):
        if name in UNGRADED_ACCEPTED:
            continue
        found.append(Failure(
            "L7", "%s declares accessibility and nothing grades it" % name,
            "%d binding(s) with no generated copy. Either generate one, or add "
            "it to UNGRADED_ACCEPTED with a reason and a board row." % count))
    return found


def ungraded_surfaces(repo, graded):
    """L7: tracked QML that declares accessibility and is graded by nobody."""
    out = []
    for name in sorted(os.listdir(repo)):
        if not name.endswith(".qml") or name in graded:
            continue
        path = os.path.join(repo, name)
        with open(path) as handle:
            text = handle.read()
        try:
            records, _frames = qmlscan.scan(text, name)
        except qmlscan.QmlParseError:
            continue
        declared = [r for r in records if r["kind"] == "accessible"]
        if declared:
            out.append((name, len(declared)))
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Assert the harness's generated copy still is the "
                    "shipping guide, accessibility-wise.")
    parser.add_argument("--pair", action="append", default=[],
                        metavar="SOURCE=GENERATED",
                        help="a shipping file and the copy the harness grades")
    parser.add_argument("--copy", action="append", default=[],
                        metavar="SOURCE=COPY",
                        help="a file the transform copies verbatim")
    parser.add_argument("--kit", action="append", default=[],
                        metavar="SRC_DIR=COPY_DIR",
                        help="the host UI kit and the harness's copy of it")
    parser.add_argument("--repo", default=REPO,
                        help="repo root, for the ungraded-surface inventory")
    parser.add_argument("--generate", metavar="SOURCE=OUT",
                        help="write the reference copy and exit; the harness "
                             "can use this instead of its own generator")
    parser.add_argument("--print-transform", action="store_true",
                        help="print what the transform removes, keeps and adds")
    args = parser.parse_args(argv)

    if args.print_transform:
        print(transform_report())
        return 0

    if args.generate:
        source_path, out_path = args.generate.split("=", 1)
        text = open(source_path).read()
        open(out_path, "w").write(apply_transform(text))
        print("wrote %s from %s through %d declared rule(s)"
              % (out_path, source_path, len(TRANSFORM_RULES)))
        return 0

    if not args.pair:
        parser.error("nothing to grade: pass at least one --pair")

    failures = []
    graded = set()
    for pair in args.pair:
        source_path, generated_path = pair.split("=", 1)
        graded.add(os.path.basename(source_path))
        if not os.path.exists(generated_path):
            failures.append(Failure(
                "L0", "the harness produced no copy of %s at %s"
                      % (os.path.basename(source_path), generated_path)))
            continue
        source_text = open(source_path).read()
        generated_text = open(generated_path).read()
        found = check_pair(source_text, generated_text,
                           os.path.basename(source_path),
                           os.path.basename(generated_path))
        records, _frames = qmlscan.scan(source_text, source_path)
        declared = len([r for r in records if r["kind"] == "accessible"])
        elements = len(set(r["path"] for r in records
                           if r["kind"] == "accessible"))
        print("%-16s -> %-20s  %d declaration(s) on %d element(s), %d "
              "finding(s)" % (os.path.basename(source_path),
                              os.path.basename(generated_path),
                              declared, elements, len(found)))
        failures.extend(found)

    for copy in args.copy:
        source_path, copy_path = copy.split("=", 1)
        found = check_copy(source_path, copy_path)
        print("%-16s -> %-20s  verbatim copy, %d finding(s)"
              % (os.path.basename(source_path), os.path.basename(copy_path),
                 len(found)))
        failures.extend(found)

    for kit in args.kit:
        src_dir, copy_dir = kit.split("=", 1)
        found = check_kit(src_dir, copy_dir)
        total = sum(len(files) for _b, _d, files in os.walk(src_dir))
        print("%-16s -> %-20s  %d host kit file(s), %d declared patch(es), "
              "%d finding(s)" % (os.path.basename(src_dir.rstrip("/")),
                                 os.path.basename(copy_dir.rstrip("/")),
                                 total, len(KIT_PATCHED), len(found)))
        failures.extend(found)

    gaps = ungraded_surfaces(args.repo, graded)
    for name, count in gaps:
        print("UNGRADED SURFACE  %s declares %d accessibility binding(s) and "
              "no generated copy grades it" % (name, count))

    print("")
    if failures:
        print("fidelity: %d finding(s)" % len(failures))
        for failure in failures:
            print(failure)
        return 1
    print("fidelity: the copy matches the shipping file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
