#!/bin/bash
# scripts/dev-harness/spikes/codebehind-calllater/run.sh -- D-REL-15: what
# happens to a function made in a classic-JS code-behind, and to the same
# function made on the root, when the Service that made it is deleted before
# something calls it.
#
#   run.sh [SHAPE...] every shape below (or those named), in both forms,
#                     deleted and kept; one detail line per run, then one
#                     verdict line per shape; exit 0 when every run reads as
#                     it was measured
#
# THE SHAPES. Plain.qml and Bound.qml are the probe's Service (the second
# with `pragma ComponentBehavior: Bound` and an ES-module import, as the
# plugin's Service.qml has); Service-probe.js is its code-behind, imported
# with no .import and no .pragma, so it runs in the Service's own scope.
#   old       a closure made in the code-behind, handed to Qt.callLater (a
#             replica of C3's adoptActive): SIGSEGV in libQt6Qml once the
#             Service is gone
#   oldread   the same, its function reading the root first, as adoptActive
#             does (shipped.sh drives adoptActive's own text): a
#             ReferenceError ("root is not defined") instead of the SIGSEGV
#             -- the outcome turns on what the function did before making
#             the closure
#   root      the same closure made in a root function: a TypeError
#             ("Cannot call method 'persistActive' of null"), no crash
#   new       a code-behind calling that root function (the fix's
#             adoptActive and persistActiveLater): a TypeError, no crash
#   method    root.ping handed to Qt.callLater from the code-behind: skipped
#             once the Service is gone; kept, two calls fold into one
#   fold      Qt.callLater(root.persistActive, key) twice in one turn: one
#             call, the LAST key -- why the fix hands callLater a closure
#   stored    a code-behind closure stored on the root and called by a root
#             function from a child Timer of the root (startCacheLayout's
#             onDone, called from cacheProc's handlers): the child dies with
#             the Service, so nothing calls it, and nothing crashes
#   held      that stored closure held by an object OUTSIDE the Service and
#             called by it directly after the Service is gone: a
#             ReferenceError ("root is not defined"), no crash -- but its
#             maker, stash(), looks up the root first (to assign root.queue),
#             as oldread's does
#   heldbare  the same direct call, the closure made by a code-behind
#             function that looks up no name before making it (makeHeld
#             returns it): SIGSEGV in libQt6Qml -- a direct call crashes too
#   heldroot  the same, the closure made on the root: a TypeError
#   connect   a code-behind closure connected to a signal of an object
#             outside the Service, which emits it after the Service is gone:
#             SIGSEGV in libQt6Qml, as Qt.callLater's
#   connectread  the same, its function reading the root first: a
#             ReferenceError, as oldread's -- with heldbare and held, what
#             the maker looked up before making the closure decides, not
#             who calls it
#   connectroot  the same closure made on the root: a TypeError
#   binding   a code-behind closure given to an outside object's property
#             as Qt.binding: the binding is dropped with the Service, and a
#             change after it is gone re-evaluates nothing
#   bindingroot  the same, made on the root: the same
# "Deleted": the driver asks the Service's destroy() and then makes the
# calls (old, oldread, root, new, method, fold) -- destroy() is deferred, so
# the calls still reach a live object -- or makes them and then asks it
# (stored, held, heldbare, heldroot, connect, connectread, connectroot,
# binding, bindingroot), and the outside object calls back 100 ms later.
# Asked the other way round -- the calls first and destroy() after them in
# the same turn -- shapes old, new and method ran their deferred calls before
# the deletion, in both forms: old's and new's both keys, method's one PING,
# its two calls folded (one scratch run each on 2026-11-24, not a case
# here). "Kept": no destroy().
#
# NOT RUN BY THE GATE: shapes old, heldbare and connect crash by design.
# What holds the rule on the tree is the service split guard
# (scripts/split-service.py --check, kind `closure`); this spike is the
# observation behind it (rule 14).
#
# SAFETY. Every qml this starts runs under gdb (debuginfod off, signals not
# passed, the inferior killed at the stop), so a SIGSEGV is caught there: no
# core is written and no crash card is posted. It refuses to start one any other way.
# Offscreen, with no DISPLAY, WAYLAND_DISPLAY, Hyprland signature or session
# bus, decoy HOME and XDG folders and a decoy runtime folder, in a 0700 work
# folder under $TMPDIR removed at exit. It reads the crash journal's count
# before and after every run and stops at once if it moves.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
. "$HERE/gdbrun.sh"
# What each run must read, deleted (1) and kept (0).
declare -A WANT=(
  [old-1]="SIGSEGV"             [old-0]="ran: PERSIST k1,PERSIST k2"
  [oldread-1]="ReferenceError x2" [oldread-0]="ran: PERSIST k1,PERSIST k2"
  [root-1]="TypeError x2"       [root-0]="ran: PERSIST k1,PERSIST k2"
  [new-1]="TypeError x2"        [new-0]="ran: PERSIST k1,PERSIST k2"
  [method-1]="nothing ran"      [method-0]="ran: PING"
  [fold-1]="nothing ran"        [fold-0]="ran: PERSIST k2"
  [stored-1]="nothing ran"      [stored-0]="ran: PERSIST k1:done"
  [held-1]="ReferenceError x1"         [held-0]="ran: PERSIST k1:late"
  [heldbare-1]="SIGSEGV"        [heldbare-0]="ran: PERSIST k1:late"
  [heldroot-1]="TypeError x1"   [heldroot-0]="ran: PERSIST k1:late"
  [connect-1]="SIGSEGV"         [connect-0]="ran: PERSIST signal"
  [connectread-1]="ReferenceError x1" [connectread-0]="ran: PERSIST signal"
  [connectroot-1]="TypeError x1" [connectroot-0]="ran: PERSIST signal"
  [binding-1]="ran: LABEL bound 0 2"     [binding-0]="ran: LABEL bound 0 2,LABEL bound 1 2"
  [bindingroot-1]="ran: LABEL bound 0 2" [bindingroot-0]="ran: LABEL bound 0 2,LABEL bound 1 2"
)
SHAPES="old oldread root new method fold stored held heldbare heldroot connect connectread connectroot binding bindingroot"
if (( $# > 0 )); then
  for s in "$@"; do [[ " $SHAPES " == *" $s "* ]] || { echo "run.sh: no shape $s (shapes: $SHAPES)" >&2; exit 2; }; done
  SHAPES="$*"
fi
work=$(mktemp -d "${TMPDIR:-/tmp}/codebehind-calllater.XXXXXX") || exit 2
chmod 700 "$work"
trap 'rm -rf -- "$work"' EXIT
j0=$(spike_journal)
echo "crash journal before: $j0"
declare -A GOT
for shape in $SHAPES; do
  for form in Plain Bound; do
    for del in 1 0; do
      name=d-$shape-$form-$del
      f=$HERE/$name.qml
      [[ -f $f ]] || { echo "run.sh: $name.qml is not there" >&2; exit 2; }
      mkdir -p "$work/$name"
      spike_run_qml "$HERE" "$f" "$work/$name/out.txt"
      spike_verdict "$work/$name/out.txt"
      v=$SPIKE_VERDICT
      detail=$SPIKE_DETAIL
      GOT[$name]=$v
      mark="ok"
      [[ $v == "${WANT[$shape-$del]}" ]] || mark="UNEXPECTED (want: ${WANT[$shape-$del]})"
      printf '%-24s %-34s %s%s\n' "$name" "$v" "$mark" "${detail:+  [$detail]}"
      j=$(spike_journal)
      if (( j != j0 )); then echo "run.sh: the crash journal moved ($j0 -> $j) after $name; stopping" >&2; exit 1; fi
    done
  done
done
echo "crash journal after: $(spike_journal)"
status=0
for shape in $SHAPES; do
  good=1
  for form in Plain Bound; do for del in 1 0; do
    [[ ${GOT[d-$shape-$form-$del]} == "${WANT[$shape-$del]}" ]] || good=0
  done; done
  if (( good )); then verdict="as measured"; else verdict="DIFFERS from the record above"; status=1; fi
  printf 'shape %-9s deleted: %-14s kept: %-28s both forms: %s\n' "$shape" "${GOT[d-$shape-Plain-1]}" "${GOT[d-$shape-Plain-0]}" "$verdict"
done
exit $status
