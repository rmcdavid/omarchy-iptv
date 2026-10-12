#!/bin/bash
# scripts/dev-harness/spikes/esm-cycle/run.sh -- D-REL-5's cycle measurement,
# re-runnable. Three .mjs parts import each other in a cycle; Agg.mjs
# re-exports from them in an order that is not the dependency order. Asks
# node and qmltestrunner (no display) whether the graph links, whether calls
# across the cycle work, and what an INITIALIZER reading another part of the
# cycle sees. The Quickshell arm needs a nested display: README.md.
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE" || exit 2
node -e 'import("./Agg.mjs").then(m => { console.log("node: aFn=" + m.aFn(1) + " cFn=" + m.cFn() + " B_SEES_A_AT_INIT=" + m.B_SEES_A_AT_INIT) })'
node_rc=$?
QT_QPA_PLATFORM=offscreen timeout 60 /usr/lib/qt6/bin/qmltestrunner -input Cycle.spec.qml 2>&1 | grep -E 'CYCLE|^Totals'
qml_rc=${PIPESTATUS[0]}
echo "node exit=$node_rc qmltestrunner exit=$qml_rc"
(( node_rc == 0 && qml_rc == 0 ))
