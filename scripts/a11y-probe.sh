#!/bin/bash
# scripts/a11y-probe.sh -- the accessibility harness, end to end.
#
# WHAT THIS PROVES, AND WHAT IT DOES NOT. It instantiates the plugin's own
# QtQuick content in a plain, hidden Qt window, lets Qt's AT-SPI bridge publish
# a real accessibility tree for it, and walks that tree asserting roles, names,
# descriptions and VALUES. So it proves our markup becomes real nodes carrying
# the right words.
#
# It does NOT prove any of it reaches a screen reader, and on this desktop none
# of it does: no window Quickshell creates publishes a tree at all (D-GS-3,
# quickshell issue 1144), so the shipping guide announces nothing to anything
# today. Read every PASS as "the markup composes and publishes correctly in a
# window the user never sees" and nothing more.
#
# WHY IT IS NOT IN check.sh. PLAN-NEXT decision 9. Its baseline on shipping
# code is deliberately RED -- those failures are real defects, not noise -- and
# CLAUDE.md forbids committing a red check.sh. It also needs a graphical
# session, which the rest of the gate does not. The FIDELITY half has no such
# needs and IS in the gate; see tests/a11y/test_fidelity.py.
#
# THE BASELINE IS A SET, NOT A COUNT, AND THIS SCRIPT GRADES AGAINST IT. Three
# checks fail on shipping code and all three are filed defects; a run matching
# exactly that set exits 0. Anything else -- a new failure, or a recorded one
# that started passing -- exits 1 and names it.
#
# It did not always. 0.7.8 added one unguarded service call to Guide.open(),
# the fake service here has no such method, open() threw, and every guide
# scenario graded a guide that never finished opening: 3 failures became 31
# and shipped that way, because "compare against the baseline in
# docs/QA-A11Y.md" is a step a person performs and therefore a step a person
# skips.
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

# The tree is a BUILD ARTIFACT: a copy of the host UI kit plus a transformed
# copy of Guide.qml, rebuilt every run. Never inside the repo, and never shared
# between concurrent runs -- a shared directory written by two lanes at once
# already produced one reading that was green only because a mutation had been
# overwritten (CLAUDE.md rule 4b).
export A11Y_TREE=${A11Y_TREE:-$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-a11y-XXXXXX")}
echo "tree: $A11Y_TREE"
echo

step() { printf '\n== %s\n' "$1"; }

step "build the tree (host kit + the transformed guide copy)"
python3 tests/a11y/make_tree.py  || { echo "FAILED to build the tree"; exit 1; }

step "build the hosts (the QML that drives each scenario)"
python3 tests/a11y/make_hosts.py || { echo "FAILED to build the hosts"; exit 1; }

step "fidelity guard (is the copy still the shipping guide?)"
# The harness must refuse to report a result over a drifted copy: a green run
# on a copy that no longer matches what ships looks like proof and is not.
python3 - <<'PY' || exit 1
import os, sys
sys.path.insert(0, os.path.join(os.getcwd(), "tests", "a11y"))
import fidelity
drift = fidelity.guard_tree(os.environ["A11Y_TREE"])
if drift:
    print("REFUSING TO MEASURE: the tree has drifted from the repo")
    for d in drift:
        print("  %s %s" % (d.layer, d))
    raise SystemExit(1)
print("no drift: the copy is the shipping guide, the kit is the shipping kit")
PY

step "walk the bus and assert what a screen reader would hear"
python3 tests/a11y/check_bus.py
rc=$?

printf '\n'
if (( rc )); then
  echo "a11y-probe: OFF BASELINE. Something changed that this harness can see;"
  echo "the lines above name it. Do not read a run in this state as evidence."
else
  echo "a11y-probe: on baseline -- exactly the recorded failures and nothing else."
fi
exit $rc
