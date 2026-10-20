#!/bin/bash
# scripts/dev-harness/open-scenario.sh -- R27f (2026-10-20, D-PERF-1): the
# guide's open, measured with the delegates in it.
#
#   open-scenario.sh check-tree               the instrument arm ONLY; run by check.sh
#   open-scenario.sh [live] [--tree DIR]      the instrument arm, then the shell arm
#   open-scenario.sh [live] --baseline REF    the same over an export of REF
#
# THE DEFECT. `openMs` (shell.qml) force-lays-out the channel view in the
# SAME turn as the summon and stops its clock there, so the view is not laid
# out when it looks: at 10,000 channels it reported 4 realised rows for the
# list and 1 tile for the wall, and every open-budget figure since
# 2026-09-23 was taken without the delegates. Rule 7's 150 ms budget has
# never been verified against the thing it is about (D-PERF-1).
#
# THE INSTRUMENT (shell.qml `openAsync` / `openAsyncResult`, the settle rule
# in harness-lib.js `openSettle`). The clock starts at the summon and the
# call RETURNS; the guide's window swaps frames, and on each swap the
# delegates the PRESENTING view has realised are counted and the creation of
# its last delegate is timed. The open is over at the first frame of a run
# of three frames with the same count above zero, provided no delegate was
# created after it; the frame after the last delegate's creation is reported
# beside it, so a run shows which definition settles and whether they agree.
#
# Two arms:
#   the instrument arm (check-tree, and the preflight of live): openSettle
#   DRIVEN from node over hand-made traces (a count that settles, one that
#   is still growing, one whose last delegate comes after a stable run, an
#   empty view, frames too few), and the seams: shell.qml's frame handler
#   calls HarnessLib.openSettle, counts by `channelId` on the presenting
#   view, and asks the window for the next frame.
#   the shell arm (live): the dev-harness fake shell with the real
#   Service.qml and Guide.qml, in the harness-only floating window, under a
#   nested headless cage this script starts, over a 10,000-channel playlist
#   gen-playlist.py writes. COLD is the first open of a fresh shell, WARM a
#   closed guide summoned again. Each warm instrument open is interleaved
#   with PERF-02's method A (docs/QA.md: the round trip of `open` over IPC
#   minus the median round trip of a call that does nothing), list view and
#   wall. OPEN_COLD shells per view, OPEN_WARM opens per shell. The checks
#   grade the INSTRUMENT (it ran, it named the view it was asked for, it
#   settled, it counted a screen of delegates, it measured after the summon,
#   and the legacy openMs still reads fewer delegates than it does); the
#   BUDGET is reported in plain words beside them, not graded, because a
#   number over 150 ms is a product finding to file, not an instrument fault.
#
# PROVING IT CAN FAIL (rule 11): spikes/open-mutations/slow-delegate.patch
# makes every channel delegate spend 4 ms in its Component.onCompleted; run
# this with --tree over a copy carrying it and the realised time must grow by
# about 4 ms a delegate while openMs's number does not.
#
# Run the live arm on a PRIVATE D-Bus (CLAUDE.md, parallel 6b):
#   scripts/dev-harness/private-bus.sh <dir> 1800 scripts/dev-harness/open-scenario.sh live
# It refuses the user's own session bus. Holds no display, sends no key:
# everything lives on the display cage creates. Every process it starts is
# stopped by the pid it recorded; nothing is matched by a pattern.
set -uo pipefail
SKIP=77
CAGE_BIN=${OPEN_CAGE_BIN:-cage}
MODE=${1:-}
case $MODE in
  check-tree) shift ;;
  live|"") MODE=live; (( $# )) && shift ;;
  -*) MODE=live ;;
  *) echo "usage: open-scenario.sh [check-tree|live] [--tree DIR | --baseline REF]" >&2; exit 2 ;;
esac
BASELINE=""; TREE=""
while (( $# )); do
  case $1 in
    --baseline) [[ ${2:-} == "" || ${2:-} == -* ]] && { echo "--baseline needs a git ref" >&2; exit 2; }; BASELINE=$2; shift ;;
    --tree) [[ ${2:-} == "" || ${2:-} == -* ]] && { echo "--tree needs a directory" >&2; exit 2; }; TREE=$2; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
[[ -n $BASELINE && -n $TREE ]] && { echo "--baseline and --tree are the same lever; pass one" >&2; exit 2; }
for tool in node python3; do
  command -v "$tool" >/dev/null 2>&1 || { echo "SKIP open-scenario: $tool is not on PATH" >&2; exit $SKIP; }
done
if [[ $MODE == live ]]; then
  for tool in "$CAGE_BIN" quickshell qs; do
    command -v "$tool" >/dev/null 2>&1 || { echo "SKIP open-scenario: $tool is not on PATH" >&2; exit $SKIP; }
  done
  REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
  if [[ -z ${DBUS_SESSION_BUS_ADDRESS:-} || $DBUS_SESSION_BUS_ADDRESS == "unix:path=$REAL_RUNTIME/bus" ]]; then
    echo "REFUSING open-scenario live: not on a private D-Bus (run it under scripts/dev-harness/private-bus.sh, CLAUDE.md parallel 6b)" >&2
    exit 2
  fi
fi
HERE=${BASH_SOURCE[0]%/*}
[[ $HERE == "${BASH_SOURCE[0]}" ]] && HERE=.
HERE=$(cd "$HERE" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
# shellcheck source=scripts/qa-lib.sh
. "$ROOT/scripts/qa-lib.sh"
RUN="$HERE/run.sh"
REAL_RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
LIVE_DISPLAY=${WAYLAND_DISPLAY:-wayland-1}
SCRATCH=${OMARCHY_IPTV_HARNESS_DIR:-$REAL_RUNTIME/omarchy-iptv-open}
export OMARCHY_IPTV_HARNESS_DIR=$SCRATCH
qa_harness_home "$SCRATCH" || exit 2
PLUGIN_ROOT=$ROOT
EXPORT_DIR=""
TREE_LINE="== tree $ROOT ($(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo no-git))"
if [[ -n $TREE ]]; then
  PLUGIN_ROOT=$(cd "$TREE" 2>/dev/null && pwd) || { echo "--tree $TREE is not a directory I can enter" >&2; exit 2; }
  [[ -f $PLUGIN_ROOT/Guide.qml && -f $PLUGIN_ROOT/Service.qml ]] && qa_model_files "$PLUGIN_ROOT" >/dev/null \
    || { echo "--tree $PLUGIN_ROOT is not a plugin tree" >&2; exit 2; }
  TREE_LINE="== prepared tree $PLUGIN_ROOT"
fi
if [[ -n $BASELINE ]]; then
  git -C "$ROOT" rev-parse --verify -q "$BASELINE^{commit}" >/dev/null || { echo "--baseline '$BASELINE' is not a commit here" >&2; exit 2; }
  EXPORT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-open-baseline.XXXXXX") || exit 2
  chmod 0700 "$EXPORT_DIR"
  git -C "$ROOT" archive "$BASELINE" | tar -x -C "$EXPORT_DIR" || { echo "could not export $BASELINE" >&2; rm -rf "$EXPORT_DIR"; exit 2; }
  PLUGIN_ROOT=$EXPORT_DIR
  TREE_LINE="== baseline tree $BASELINE ($(git -C "$ROOT" rev-parse --short "$BASELINE")) exported to $EXPORT_DIR"
fi
if [[ $MODE == live ]]; then
  qa_transcript_start open || exit 2
fi
echo "$TREE_LINE"
echo "== mode $MODE   plugin tree $PLUGIN_ROOT   instrument $HERE/shell.qml + harness-lib.js   caller's display $LIVE_DISPLAY (never driven)"

WORK=$(mktemp -d "${TMPDIR:-/tmp}/omarchy-iptv-open.XXXXXX") || exit 2
chmod 0700 "$WORK"
CAGE_PID=""; CAGE_CHILD=""; SHELL_STARTED=0; SHELL_PID=""; NESTED=""
cleanup() {
  (( SHELL_STARTED )) && env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY="$NESTED" "$RUN" reap >/dev/null 2>&1
  [[ -n $CAGE_CHILD ]] && kill -TERM "$CAGE_CHILD" 2>/dev/null
  if [[ -n $CAGE_PID ]] && kill -0 "$CAGE_PID" 2>/dev/null; then kill -TERM "$CAGE_PID" 2>/dev/null; wait "$CAGE_PID" 2>/dev/null; fi
  [[ -n ${EXPORT_DIR:-} && -d $EXPORT_DIR ]] && rm -rf "$EXPORT_DIR"
  [[ -n ${WORK:-} && -d $WORK ]] && rm -rf "$WORK"
  return 0
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "PASS $1"; }
fail() { FAIL=$((FAIL+1)); echo "FAIL $1${2:+ -- $2}"; }
ck() { local label=$1 got=$2 want=$3; [[ $got == "$want" ]] && pass "$label: $want" || fail "$label" "got [$got], want [$want]"; }

# ------------------------------------------------------- the instrument arm
instrument() {
  local out
  echo "== instrument arm: harness-lib.js openSettle, driven"
  out=$(node -e '
const H = require(process.argv[1])
const f = (...cs) => cs.map((c, i) => ({ at: 16 * (i + 1), count: c }))
const s = (fr, lc, k) => { const r = H.openSettle(fr, lc, k); return [r.settled, r.stableAt, r.stableCount, r.lastChildFrameAt].join(",") }
console.log("O1 " + s(f(0, 12, 30, 30, 30), 30, 3))
console.log("O2 " + s(f(0, 12, 20, 30), 40, 3))
console.log("O3 " + s(f(30, 30, 30, 31), 60, 3))
console.log("O4 " + s(f(0, 0, 0, 0), -1, 3))
console.log("O5 " + s(f(30, 30), 10, 3))
console.log("O6 " + s(f(5, 30, 30, 30, 30), -1, 3))
console.log("O7 " + s(f(30, 31, 31, 31), 20, 3))
' "$HERE/harness-lib.js" 2>&1)
  line() { printf '%s\n' "$out" | grep -a "^$1 " | head -1 | cut -d' ' -f2-; }
  ck "O1 a count that grows and then holds three frames settles at the first frame of the run, with the last delegate's frame beside it" "$(line O1)" "true,48,30,32"
  ck "O2 a count still growing when the frames run out has not settled" "$(line O2)" "false,-1,-1,48"
  ck "O3 a delegate created after a stable run means it had not settled" "$(line O3)" "false,16,30,64"
  ck "O4 an empty view never settles" "$(line O4)" "false,-1,-1,-1"
  ck "O5 two frames are not three" "$(line O5)" "false,-1,-1,16"
  ck "O6 no child event (a warm open over delegates that already exist) settles on the count alone" "$(line O6)" "true,32,30,-1"
  ck "O7 a count that moves once and then holds settles at the frame it reached its final value" "$(line O7)" "true,32,31,32"
  local seam
  seam="$(qa_count '^    var settle = HarnessLib\.openSettle\(frames, r\.lastChildAt, harness\.openSettleFrames\)$' "$HERE/shell.qml") $(qa_count '^      try \{ if \(kids\[i\] && kids\[i\]\.channelId !== undefined\) n\+\+ \} catch \(e\) \{\}$' "$HERE/shell.qml") $(qa_count 'p\.Window\.window\.update\(\)' "$HERE/shell.qml") $(qa_count 'function onFrameSwapped\(\) \{ p\.frame\(\) \}' "$HERE/shell.qml")"
  ck "S1 shell.qml's frame handler decides through HarnessLib.openSettle, counts delegates by channelId (twice: openMs's and openAsync's), asks the window for the next frame and listens to its swaps" "$seam" "1 2 1 1"
  echo "== instrument arm done"
}

# ------------------------------------------------------------ the shell arm
h()   { env -u HYPRLAND_INSTANCE_SIGNATURE WAYLAND_DISPLAY="$NESTED" "$RUN" "$@"; }
ipc() { h ipc "$@" 2>/dev/null; }
svc() { qa_field "d$1" "$(ipc state)"; }
jf()  { qa_json_field "d$1" "$2"; }
cage_start() {
  local secs=$1 i
  rm -f "$WORK/display" "$WORK/child.pid"
  cat >"$WORK/child.sh" <<CHILD
#!/bin/bash
echo "\$WAYLAND_DISPLAY" >"$WORK/display"
echo \$\$ >"$WORK/child.pid"
exec sleep $secs
CHILD
  chmod 0700 "$WORK/child.sh"
  env -u WAYLAND_DISPLAY -u DISPLAY WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 \
    timeout -k 5 $((secs + 10)) "$CAGE_BIN" -- "$WORK/child.sh" >"$WORK/cage.log" 2>&1 &
  CAGE_PID=$!
  for ((i = 0; i < 100; i++)); do [[ -s $WORK/display && -s $WORK/child.pid ]] && break; sleep 0.1; done
  NESTED=$(cat "$WORK/display" 2>/dev/null); CAGE_CHILD=$(cat "$WORK/child.pid" 2>/dev/null)
  if [[ -z $NESTED || -z $CAGE_CHILD ]]; then echo "SKIP open-scenario: cage brought up no display within 10 s" >&2; exit $SKIP; fi
  if [[ $NESTED == "$LIVE_DISPLAY" || $NESTED == wayland-1 ]]; then echo "REFUSING: cage's child reports the live display '$NESTED'" >&2; exit 2; fi
}
cage_stop() {
  local i
  [[ -n $CAGE_CHILD ]] && kill -TERM "$CAGE_CHILD" 2>/dev/null
  for ((i = 0; i < 50; i++)); do kill -0 "$CAGE_PID" 2>/dev/null || break; sleep 0.1; done
  kill -0 "$CAGE_PID" 2>/dev/null && kill -KILL "$CAGE_PID" 2>/dev/null
  wait "$CAGE_PID" 2>/dev/null; CAGE_PID=""; CAGE_CHILD=""
}
# A detached shell over the 10k fixture, in the floating window, settled
# (state loaded, cache ready, every channel in memory). Bounded 60 s.
start_shell() {
  h --detach --timeout 0 --playlist "$FIX" --window floating >"$WORK/start.log" 2>&1
  SHELL_PID=$(cat "$SCRATCH/qs.pid" 2>/dev/null); SHELL_STARTED=1
  local i
  for ((i = 0; i < 600; i++)); do
    [[ $(svc "['channels']") == "$CHANNELS" ]] && return 0
    sleep 0.1
  done
  echo "   the shell (pid $SHELL_PID) did not hold $CHANNELS channels within 60 s: $(svc "['channels']")"
  return 1
}
stop_shell() { h shell-stop >/dev/null 2>&1; local i; for ((i = 0; i < 50; i++)); do kill -0 "$SHELL_PID" 2>/dev/null || break; sleep 0.1; done; SHELL_STARTED=0; }
# One asynchronous open, waited for (bounded 8 s), its result JSON on stdout.
async_open() {
  local view=$1 i res
  ipc close >/dev/null; sleep 0.4
  ipc openAsync "$view" >"$WORK/started.json"
  for ((i = 0; i < 80; i++)); do
    res=$(ipc openAsyncResult)
    [[ $(jf "['state']" "$res") == done ]] && { printf '%s\n' "$res"; return 0; }
    sleep 0.1
  done
  printf '%s\n' "$res"
  return 1
}
# PERF-02 method A: the round trip of `open` (guide closed first), in ms.
method_a() {
  local t0 t1
  ipc close >/dev/null; sleep 0.4
  t0=$(date +%s%N); ipc open "{}" >/dev/null; t1=$(date +%s%N)
  echo $(( (t1 - t0) / 1000000 ))
}
ping_ms() { local t0 t1; t0=$(date +%s%N); ipc ping >/dev/null; t1=$(date +%s%N); echo $(( (t1 - t0) / 1000000 )); }
# The legacy openMs on a COLD open of a fresh shell: what D-PERF-1 found it
# reports (4 rows for the list and 1 tile for the wall at 10,000 channels).
# On a warm open the delegates already exist and it counts them, so only a
# cold one shows the defect.
legacy_cold() {   # legacy_cold <view>
  start_shell || { echo "   the legacy shell ($1) did not settle"; return 1; }
  [[ $1 == wall ]] && ipc wall true >/dev/null || ipc wall false >/dev/null
  ipc openMs 1
  stop_shell
}

SAMPLES="$WORK/samples.tsv"
: >"$SAMPLES"
record() { printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$@" >>"$SAMPLES"; }
measure_shell() {   # measure_shell <view> <shell-number>
  local view=$1 n=$2 res a k want_view
  [[ $view == wall ]] && want_view=channelWall || want_view=resultList
  start_shell || { echo "   shell $n ($view) did not settle; no samples from it"; return 1; }
  # COLD: the first open this shell makes
  if res=$(async_open "$view"); then
    record "$view" cold "$(jf "['summonMs']" "$res")" "$(jf "['realisedMs']" "$res")" "$(jf "['lastChildFrameMs']" "$res")" "$(jf "['count']" "$res")" "-"
    [[ $n == 1 ]] && { COLD_RES=$res; }
  else
    record "$view" cold-unsettled "$(jf "['summonMs']" "$res")" -1 -1 "$(jf "['count']" "$res")" "-"
    [[ $n == 1 ]] && COLD_RES=$res
  fi
  # WARM, interleaved with method A
  for ((k = 0; k < WARM; k++)); do
    if res=$(async_open "$view"); then
      record "$view" warm "$(jf "['summonMs']" "$res")" "$(jf "['realisedMs']" "$res")" "$(jf "['lastChildFrameMs']" "$res")" "$(jf "['count']" "$res")" "-"
      WARM_RES=$res
    else
      record "$view" warm-unsettled "$(jf "['summonMs']" "$res")" -1 -1 "$(jf "['count']" "$res")" "-"
    fi
    a=$(method_a); record "$view" methodA - - - - "$a"
    record "$view" ping - - - - "$(ping_ms)"
  done
  stop_shell
}

instrument
if [[ $MODE == check-tree ]]; then
  EXPECTED_CHECKS=8
else
  CHANNELS=${OPEN_CHANNELS:-10000}
  COLD=${OPEN_COLD:-3}
  WARM=${OPEN_WARM:-8}
  FIX="$WORK/fixtures/gen-10k.m3u"
  mkdir -p "$WORK/fixtures"
  python3 "$ROOT/scripts/gen-playlist.py" --channels "$CHANNELS" --groups 400 --seed 1 --out "$FIX" >/dev/null || { echo "gen-playlist failed" >&2; exit 2; }
  export OMARCHY_IPTV_PLUGIN_ROOT=$PLUGIN_ROOT
  mkdir -p "$SCRATCH/bin" && ln -sfn "$HERE/stub-hyprctl.py" "$SCRATCH/bin/hyprctl"
  cage_start 1700
  h reap >/dev/null 2>&1
  echo "== shell arm: $CHANNELS channels, $COLD cold shells and $WARM warm opens per view, floating window, cage $NESTED, load $(cut -d' ' -f1-3 /proc/loadavg)"
  for view in list wall; do
    for ((s = 1; s <= COLD; s++)); do
      COLD_RES=""; WARM_RES=""; LEGACY=""
      measure_shell "$view" "$s"
      if [[ $s == 1 ]]; then
        [[ $view == wall ]] && want=channelWall || want=resultList
        L=${view:0:1}; L=${L^^}
        ck "${L}1 $view: the instrument ran to its end on the cold open and named the presenting view" "$(jf "['state']" "$COLD_RES") $(jf "['view']" "$COLD_RES")" "done $want"
        ck "${L}2 $view: the cold open SETTLED (a count stable over three frames, no delegate after it) and saw the guide's window" "$(jf "['settled']" "$COLD_RES") $(jf "['hasWindow']" "$COLD_RES")" "true true"
        ck "${L}3 $view: a warm open settled too" "$(jf "['settled']" "$WARM_RES")" "true"
        ck "${L}4 $view: it counted a SCREEN of delegates (more than 4, the legacy instrument's list figure)" "$(python3 -c 'import sys; print("yes" if int(sys.argv[1]) > 4 else "no:" + sys.argv[1])' "$(jf "['count']" "$COLD_RES")" 2>/dev/null)" "yes"
        ck "${L}5 $view: the realised time is measured AFTER the summon returned (realised >= summon)" "$(python3 -c 'import sys; print("yes" if float(sys.argv[2]) >= float(sys.argv[1]) else "no")' "$(jf "['summonMs']" "$COLD_RES")" "$(jf "['realisedMs']" "$COLD_RES")" 2>/dev/null)" "yes"
        LEGACY=$(legacy_cold "$view")
        ck "${L}6 $view: the legacy openMs, on a cold open of its own fresh shell, realised FEWER delegates than the async instrument counts on a cold open (D-PERF-1, still true of openMs)" "$(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print("yes" if int(d.get("realised",-1)) < int(sys.argv[2]) else "no:%s/%s" % (d.get("realised"), sys.argv[2]))' "$LEGACY" "$(jf "['count']" "$COLD_RES")" 2>/dev/null)" "yes"
        echo "   $view cold trace (ms:count): $(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(" ".join("%s:%s" % (f["at"], f["count"]) for f in d.get("trace", [])[:20]))' "$COLD_RES" 2>/dev/null)"
        echo "   $view legacy openMs: $LEGACY"
      fi
    done
  done
  cage_stop
  echo "== samples (view, kind, summon, realised, lastChild, count, method A or ping round trip; ms)"
  sed 's/^/   /' "$SAMPLES"
  echo "== results (ms; realised = the first frame of the stable count, lastChild = the frame after the last delegate)"
  python3 - "$SAMPLES" <<'PY'
import statistics, sys
rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1]) if l.strip()]
def num(x):
    try: return float(x)
    except Exception: return None
def summary(xs):
    xs = [x for x in xs if x is not None and x >= 0]
    if not xs: return "n=0"
    return "n=%d median %.0f min %.0f max %.0f" % (len(xs), statistics.median(xs), min(xs), max(xs))
verdict = []
for view in ("list", "wall"):
    pings = [num(r[6]) for r in rows if r[0] == view and r[1] == "ping"]
    ping = statistics.median([p for p in pings if p is not None]) if pings else 0
    for kind in ("cold", "warm"):
        rs = [r for r in rows if r[0] == view and r[1] == kind]
        un = [r for r in rows if r[0] == view and r[1] == kind + "-unsettled"]
        print("  %-4s %-4s summon %s | realised %s | lastChild %s | count %s | unsettled %d" % (view, kind,
              summary([num(r[2]) for r in rs]), summary([num(r[3]) for r in rs]), summary([num(r[4]) for r in rs]),
              summary([num(r[5]) for r in rs]), len(un)))
        real = [num(r[3]) for r in rs if num(r[3]) is not None and num(r[3]) >= 0]
        if real:
            verdict.append("%s %s median %.0f ms max %.0f ms: %s" % (view, kind, statistics.median(real), max(real),
                           "within 150 ms" if max(real) < 150 else ("median within, max over" if statistics.median(real) < 150 else "OVER 150 ms")))
    a = [num(r[6]) for r in rows if r[0] == view and r[1] == "methodA"]
    a = [x - ping for x in a if x is not None]
    # method A's difference can be negative: the round trip is mostly the
    # IPC client's own start, and the open's share sits inside its noise
    sa = ("n=%d median %.0f min %.0f max %.0f" % (len(a), statistics.median(a), min(a), max(a))) if a else "n=0"
    print("  %-4s PERF-02 method A (open round trip - median ping %.0f): %s" % (view, ping, sa))
print("BUDGET (rule 7, 150 ms, the realised time): " + "; ".join(verdict))
PY
  EXPECTED_CHECKS=20
fi
ran=$((PASS + FAIL))
if (( ran == EXPECTED_CHECKS )); then
  pass "the scenario ran every check it has ($ran)"
else
  fail "the scenario ran $ran checks, expected $EXPECTED_CHECKS" "one stopped executing"
fi
echo "== $PASS passed, $FAIL failed"
(( FAIL == 0 ))
