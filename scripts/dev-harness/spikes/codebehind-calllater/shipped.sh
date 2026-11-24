#!/bin/bash
# scripts/dev-harness/spikes/codebehind-calllater/shipped.sh -- D-REL-15 on
# the SHIPPED text: the plugin's own Service-sources.js and model beside a
# stand-in Service (standin.py), adoptActive driven twice in one turn through
# its forwarder, with the Service deleted before the deferred calls run and
# with it kept.
#
#   shipped.sh [REV]  the tree's Service-sources.js, and REV's (default
#                     baea04a, the commit before the fix, where adoptActive
#                     still made its closure in the code-behind) read with
#                     git show; one verdict line per run
#
# Measured on 2026-11-24. The tree's: two TypeErrors deleted ("Cannot call
# method 'persistActive' of null"), both playlists persisted in order kept.
# REV's: two ReferenceErrors deleted ("root is not defined"), not the
# SIGSEGV run.sh's shape old takes -- adoptActive reads the root before it
# makes its closure, and run.sh's shape oldread shows that such a read turns
# the replica's SIGSEGV into this ReferenceError: what a code-behind closure
# does once its Service is gone depends on what its function did before
# making it, which no reading of the source can be held to; the closure the
# root makes is a TypeError in every shape measured. The same kept. Every
# qml runs under gdb, as gdbrun.sh does it (see run.sh's SAFETY); not run by
# the gate.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../.." && pwd)
REV=${1:-baea04a78d2a6b9294c42c5cb6ae31176eae8138}
. "$HERE/gdbrun.sh"
work=$(mktemp -d "${TMPDIR:-/tmp}/codebehind-shipped.XXXXXX") || exit 2
chmod 700 "$work"
trap 'rm -rf -- "$work"' EXIT
for f in Service-sources.js Service.qml; do
  git -C "$ROOT" show "$REV:$f" >"$work/old-$f" || { echo "shipped.sh: git show $REV:$f failed" >&2; exit 2; }
done
declare -A WANT=([tree-1]="TypeError x2" [tree-0]="ran: PERSIST a.m3u,PERSIST b.m3u"
                 [rev-1]="ReferenceError x2" [rev-0]="ran: PERSIST a.m3u,PERSIST b.m3u")
j0=$(spike_journal)
echo "crash journal before: $j0"
status=0
for which in tree rev; do
  w=$work/$which
  mkdir -p "$w"
  src=$ROOT/Service-sources.js svc=$ROOT/Service.qml
  [[ $which == rev ]] && src=$work/old-Service-sources.js svc=$work/old-Service.qml
  label="the tree's Service-sources.js"
  [[ $which == rev ]] && label="$REV's Service-sources.js"
  echo "$label: $(python3 -I "$HERE/standin.py" "$ROOT" "$w" "$src" "$svc")"
  for del in 1 0; do
    mkdir -p "$work/run-$which-$del"
    spike_run_qml "$w" "$w/d-shipped-$del.qml" "$work/run-$which-$del/out.txt"
    spike_verdict "$work/run-$which-$del/out.txt"
    mark="ok"
    if [[ $SPIKE_VERDICT != "${WANT[$which-$del]}" ]]; then mark="UNEXPECTED (want: ${WANT[$which-$del]})"; status=1; fi
    printf '%-6s %-8s %-34s %s%s\n' "$which" "$( ((del)) && echo deleted || echo kept)" "$SPIKE_VERDICT" "$mark" \
      "${SPIKE_DETAIL:+  [$SPIKE_DETAIL]}"
    j=$(spike_journal)
    if (( j != j0 )); then echo "shipped.sh: the crash journal moved ($j0 -> $j); stopping" >&2; exit 1; fi
  done
done
echo "crash journal after: $(spike_journal)"
exit $status
