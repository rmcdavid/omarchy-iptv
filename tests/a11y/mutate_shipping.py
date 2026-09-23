"""QA-A11Y section 9 item 9: the mutation mode that edits a SHIPPING file.

Every mutation in `mutate_guard.py` disables a layer of the guard. None of them
touches `Guide.qml`, and that gap is not cosmetic: the guard grades a GENERATED
COPY against the source, and the copy is generated FROM the source. So if the
source itself loses a declaration, both sides lose it together and the
comparison has nothing to compare. That is the shared-oracle failure, and it
cannot be seen from inside the guard's own mutations.

This runs it. A throwaway copy of the repo, one accessibility declaration
removed from `Guide.qml`, the tree regenerated from the mutated source, and the
guard asked what it thinks. Nothing in the real repo is touched.

Read the result carefully. A guard that stays GREEN here is not broken -- it is
answering the question it was built to answer, which is "does the copy still
carry what the source declares". Whether the source declares the right thing is
a different question with different owners: `tests/Model.test.js` for the
composers and the AT-SPI checker for the nodes. The point of running this is to
know which is which, and to stop a green fidelity run from being cited as
evidence that the guide's accessibility is intact.

    python3 tests/a11y/mutate_shipping.py

Stdlib only, ASCII only.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

# Each entry removes or corrupts ONE accessibility declaration in the shipping
# guide. The `expect` column is what this pass measured, not what it hoped.
MUTATIONS = [
    ("baseline (shipping guide intact)", None, None),
    ("drop an Accessible.name from the shipping guide",
     re.compile(r"^(\s*)Accessible\.name: .*$", re.M), ""),
    ("drop an Accessible.role from the shipping guide",
     re.compile(r"^(\s*)Accessible\.role: .*$", re.M), ""),
    ("turn a declared role into Accessible.ignored",
     re.compile(r"^(\s*)Accessible\.role: Accessible\.\w+$", re.M),
     r"\1Accessible.ignored: true"),
]


def run(label, pattern, replacement):
    """Ask the GUARD directly, not its test suite.

    Running the suite here reports the wrong thing: several of its cases anchor
    on text in the shipping guide, so mutating that text breaks the FIXTURES and
    the run goes red for a reason that has nothing to do with detection. The
    first version of this file did exactly that and reported three mutations as
    caught when the guard had not noticed any of them.
    """
    print(label)
    work = tempfile.mkdtemp(prefix="a11y-shipping-")
    try:
        repo = os.path.join(work, "repo")
        shutil.copytree(REPO, repo, symlinks=True, ignore=shutil.ignore_patterns(
            ".git", "node_modules", "__pycache__", "*.pyc"))
        guide_path = os.path.join(repo, "Guide.qml")
        text = open(guide_path).read()
        before = text.count("Accessible.")
        if pattern is not None:
            text, count = pattern.subn(replacement, text, count=1)
            if count != 1:
                print("  SKIPPED: the pattern matched %d time(s)" % count)
                return None
            open(guide_path, "w").write(text)
        sys.path.insert(0, os.path.join(repo, "tests", "a11y"))
        for stale in ("fidelity", "qmlscan"):
            sys.modules.pop(stale, None)
        os.environ["A11Y_REPO"] = repo
        import fidelity
        source = open(guide_path).read()
        generated = fidelity.apply_transform(source)
        found = fidelity.check_pair(source, generated)
        after = source.count("Accessible.")
        print("  declarations %d -> %d, guard findings: %d" % (before, after, len(found)))
        for item in found[:2]:
            print("    %s" % item)
        sys.path.remove(os.path.join(repo, "tests", "a11y"))
        for stale in ("fidelity", "qmlscan"):
            sys.modules.pop(stale, None)
        return len(found)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    print("mutating the GUIDE, not the guard. Repo: %s\n" % REPO)
    results = []
    for label, pattern, replacement in MUTATIONS:
        results.append((label, run(label, pattern, replacement)))
        print("")
    baseline = results[0][1]
    print("baseline findings: %s" % baseline)
    blind = [label for label, failed in results[1:] if failed == baseline]
    if blind:
        print("\nThe guard is BLIND to these, and that is by design rather than a defect:")
        for label in blind:
            print("  - %s" % label)
        print("\nIt compares a generated copy against the source it was generated FROM.")
        print("A source that loses a declaration loses it on both sides at once, so")
        print("there is nothing left to compare. What is NOT blind to it: the Model.js")
        print("suite for the composers, and the AT-SPI checker for the nodes.")
        print("\nSo a green fidelity run is evidence that the copy is faithful. It is")
        print("NOT evidence that the guide's accessibility is intact, and no filed run")
        print("may be read as though it were.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
