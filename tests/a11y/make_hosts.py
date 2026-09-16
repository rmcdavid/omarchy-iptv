"""Lane 2: add the bar widget to the throwaway tree make_tree.py built.

Runs AFTER make_tree.py (which wipes and rebuilds tree/). It copies
BarWidget.qml in with ZERO edits and proves it: the byte digest of the copy
must equal the digest of the repo file, or this exits non-zero.

That is the fidelity assertion for the bar half. The guide half needs a
different one because its copy IS edited; this half needs only "unchanged",
so it gets the strongest form available -- identical bytes.
"""
import hashlib
import os
import shutil
import sys

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


def digest(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def main():
    if not os.path.isdir(TREE):
        print("no tree/ -- run make_tree.py first")
        return 2
    src = os.path.join(REPO, "BarWidget.qml")
    dst = os.path.join(TREE, "BarWidget.qml")
    shutil.copy(src, dst)
    a, b = digest(src), digest(dst)
    if a != b:
        print("FIDELITY: BarWidget.qml copy differs from the repo file")
        return 1
    print("[bar] BarWidget.qml copied unedited, sha256 %s matches the repo file" % a[:16])

    shutil.copy(os.path.join(HERE, "host_bar.qml"),
                os.path.join(TREE, "barhost.qml"))
    print("[bar] barhost.qml written")

    shutil.copy(os.path.join(HERE, "host_guide.qml"),
                os.path.join(TREE, "host2.qml"))
    print("[guide] host2.qml written (loads the shared GuideProbe.qml)")

    # Model.js is already in the tree from make_tree.py; the bar reads
    # Model.barAccessibleName, Model.barGlyph and Model.BAR_IDLE_DARKEN from
    # the same copy the guide uses.
    if not os.path.exists(os.path.join(TREE, "Model.js")):
        print("no tree/Model.js -- run make_tree.py first")
        return 2
    mrepo = digest(os.path.join(REPO, "Model.js"))
    mtree = digest(os.path.join(TREE, "Model.js"))
    if mrepo != mtree:
        print("FIDELITY: tree/Model.js differs from the repo file")
        return 1
    print("[bar] Model.js in the tree matches the repo file, sha256 %s" % mrepo[:16])
    return 0


if __name__ == "__main__":
    sys.exit(main())
