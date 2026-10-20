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
# THE INSTRUMENT (shell.qml `openAsync` / `openAsyncResult`; the decision in
# harness-lib.js `openDrawnSet` and `openDrawnSettle`). The clock starts at
# the summon and the call RETURNS; the guide's window swaps frames, and on
# each swap the PRESENTING view is sampled. R28d (2026-10-20, the lead's
# ruling): it counts what is DRAWN -- the delegates that intersect the view's
# visible area, never the cacheBuffer's off-screen ones that R27f counted
# (13 rows and 21 tiles where 10 and 16 are drawn) -- and the open is
# realised at the FIRST frame whose drawn set tiles that area, measured
# against the rows the guide has (its rowCount, not the view's count), so a
# view that draws part of a screen and fills the rest later is realised only
# when it has. It samples on for 600 ms after the decision and counts the
# frames whose drawn set changed. R27f's rule (a count stable over three
# frames) trailed the drawn screen by the off-screen delegates' cost (94-182
# ms on a cold open) and passed a view that filled in late.
#
# Two arms:
#   the instrument arm (check-tree, and the preflight of live): openDrawnSet
#   and openDrawnSettle DRIVEN from node over hand-made frames (a list screen
#   under its cacheBuffer, a gap, a screen filled in part, a guide that ends
#   on screen, a scrolled list missing a row above, a grid's full rows, a
#   grid row half-filled, a grid that ends on screen, hidden delegates, an
#   empty view; a decision, none, a drawn set that changes after it, a tail
#   not yet run), and the seams: shell.qml's frame handler decides through
#   both, against the guide's rowCount, and asks the window for the next
#   frame.
#   the shell arm (live): the dev-harness fake shell with the real
#   Service.qml and Guide.qml, in the harness-only floating window, under a
#   nested headless cage this script starts, over a 10,000-channel playlist
#   gen-playlist.py writes. COLD is the first open of a fresh shell, WARM a
#   closed guide summoned again. Each warm instrument open is interleaved
#   with PERF-02's method A (docs/QA.md: the round trip of `open` over IPC
#   minus the median round trip of a call that does nothing), list view and
#   wall. OPEN_COLD shells per view, OPEN_WARM opens per shell. The checks
#   grade the INSTRUMENT (it ran, it named the view it was asked for, it
#   settled, it counted a drawn screen and not the off-screen delegates, it
#   measured after the summon, nothing drawn changed after its decision) and
#   the WARM budget (rule 7's 150 ms, the median of the warm opens: it holds
#   there, and a view that fills in late breaks it); the COLD budget is
#   reported in plain words beside them, not graded, because the first open
#   of a session is over 150 ms (round 17, most of it the window's first
#   show) and that is a product finding filed by the lead, not an
#   instrument fault. The legacy openMs is printed beside the result for
#   comparison and graded by nothing (round 1's L6 claimed it under-counts;
#   against the DRAWN screen it does not).
#
# PROVING IT CAN FAIL (rule 11), spikes/open-mutations/, through --tree over
# a copy carrying the patch: slow-delegate.patch makes every channel
# delegate spend 4 ms in its Component.onCompleted, and both the summon (a
# cold summon builds delegates synchronously, the hidden view's among them)
# and the realised time grow; late-fill.patch gives both channel views a
# model of 6 rows until 300 ms after open(), and the warm budget check (L6,
# W6) goes red where R27f's instrument read that partial screen as the open.
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
  echo "== instrument arm: harness-lib.js openDrawnSet / openDrawnSettle, driven"
  out=$(node -e '
const H = require(process.argv[1])
const row = (i, h) => ({ index: i, x: 0, y: i * 52, w: 600, h: h || 50, shown: true })
const tile = (i, cols) => ({ index: i, x: (i % cols) * 120, y: Math.floor(i / cols) * 130, w: 120, h: 130, shown: true })
const range = (a, b) => { const o = []; for (let i = a; i < b; i++) o.push(i); return o }
const LIST = { kind: "list", total: 10000, spacing: 2 }, GRID = { kind: "grid", total: 10000, cellW: 120, cellH: 130 }
const vp = (y, h, w) => ({ x: 0, y: y || 0, w: w || 600, h: h || 514 })
const d = (items, v, l) => { const r = H.openDrawnSet(items, v, l); return [r.drawn, r.built, r.minIndex, r.maxIndex, r.complete, r.reason].join(",") }
console.log("D1 " + d(range(0, 13).map(i => row(i)), vp(), LIST))
console.log("D2 " + d(range(0, 13).filter(i => i !== 4).map(i => row(i)), vp(), LIST))
console.log("D3 " + d(range(0, 6).map(i => row(i)), vp(), LIST))
console.log("D4 " + d(range(0, 6).map(i => row(i)), vp(), Object.assign({}, LIST, { total: 6 })))
console.log("D5 " + d(range(4, 20).map(i => row(i)), vp(4 * 52 - 30), LIST))
console.log("D6 " + d(range(0, 20).map(i => tile(i, 4)), vp(0, 520, 480), GRID))
console.log("D7 " + d(range(0, 14).map(i => tile(i, 4)), vp(0, 520, 480), GRID))
console.log("D8 " + d(range(0, 14).map(i => tile(i, 4)), vp(0, 520, 480), Object.assign({}, GRID, { total: 14 })))
console.log("D9 " + d(range(0, 13).map(i => Object.assign(row(i), { shown: i !== 3 })), vp(), LIST))
console.log("D10 " + d([], vp(), LIST))
console.log("D11 " + d(range(0, 13).map(i => Object.assign(row(i), { opacity: 0 })), vp(), LIST))
console.log("D12 " + d(range(0, 13).map(i => Object.assign(row(i), { opacity: i === 3 ? 0 : 1 })), vp(), LIST))
console.log("D13 " + d(range(0, 13).map(i => Object.assign(row(i), { opacity: 0.3 })), vp(), LIST))
const fr = (...xs) => xs.map((x, i) => Object.assign({ at: 16 * (i + 1) }, x))
const A = { drawn: 6, minIndex: 0, maxIndex: 5, complete: false }, C = { drawn: 10, minIndex: 0, maxIndex: 9, complete: true }
const S = (frames, tail) => { const r = H.openDrawnSettle(frames, tail); return [r.settled, r.realisedAt, r.count, r.changedAfter, r.tailFrames, r.tailDone].join(",") }
console.log("E1 " + S(fr(A, A, C, C, C, C), 40))
console.log("E2 " + S(fr(A, A, A, A), 40))
console.log("E3 " + S(fr(A, C, Object.assign({}, C, { drawn: 11, maxIndex: 10 }), C, C), 100))
console.log("E4 " + S(fr(A, C, C), 600))
' "$HERE/harness-lib.js" 2>&1)
  line() { printf '%s\n' "$out" | grep -a "^$1 " | head -1 | cut -d' ' -f2-; }
  ck "D1 a list screen with its cacheBuffer below: 13 built, the 10 that intersect the visible area are drawn, and they tile it" "$(line D1)" "10,13,0,9,true,"
  ck "D2 a row missing among the drawn ones is a gap, not a screen" "$(line D2)" "9,12,0,9,false,gap"
  ck "D3 six rows drawn where ten fit, the guide holding 10,000: not complete (the slot after the last is in view)" "$(line D3)" "6,6,0,5,false,below"
  ck "D4 the same six rows when the guide HAS six: complete (the guide ends on screen)" "$(line D4)" "6,6,0,5,true,"
  ck "D5 a scrolled list whose first drawn row starts below the top with rows before it: not complete (a row missing above)" "$(line D5)" "10,16,4,13,false,above"
  ck "D6 a grid of four columns: the four full rows in view are drawn, the fifth row of the cacheBuffer is not" "$(line D6)" "16,20,0,15,true,"
  ck "D7 a grid whose last row in view has two of its four cells: not complete" "$(line D7)" "14,14,0,13,false,below"
  ck "D8 the same grid when the guide ends at that cell: complete" "$(line D8)" "14,14,0,13,true,"
  ck "D9 a hidden delegate is not drawn, and the hole it leaves is a gap" "$(line D9)" "9,13,0,9,false,gap"
  ck "D10 an empty view draws nothing" "$(line D10)" "0,0,-1,-1,false,empty"
  # R29e (round 2's live review, P3): a view painted at opacity 0 is not
  # drawn. A fade counts from its first frame above 0 (D13): the claim is
  # "painted at all", never "painted at full strength".
  ck "D11 a screen of delegates whose effective opacity is 0 draws nothing" "$(line D11)" "0,13,-1,-1,false,empty"
  ck "D12 one delegate at opacity 0 is a hole, so a gap" "$(line D12)" "9,13,0,9,false,gap"
  ck "D13 a screen at opacity 0.3 counts as drawn (what the instrument does not grade: a fade's strength)" "$(line D13)" "10,13,0,9,true,"
  ck "E1 the open is realised at the FIRST frame whose drawn set is complete; nothing changes in the tail, which runs out" "$(line E1)" "true,48,10,0,2,true"
  ck "E2 a set that never completes never settles" "$(line E2)" "false,-1,-1,0,0,false"
  ck "E3 a drawn set that changes after the decision is counted in the tail" "$(line E3)" "true,32,10,1,3,false"
  ck "E4 a tail that has not run its time is not done" "$(line E4)" "true,32,10,0,1,false"
  local seam
  seam="$(qa_count '^    var settle = HarnessLib\.openDrawnSettle\(frames, harness\.openTailMs\)$' "$HERE/shell.qml") $(qa_count '^    return HarnessLib\.openDrawnSet\(items, \{ x: v\.contentX, y: v\.contentY, w: v\.width, h: v\.height \},$' "$HERE/shell.qml") $(qa_count 'kind: grid \? "grid" : "list", total: g \? g\.rowCount : v\.count,' "$HERE/shell.qml") $(qa_count 'p\.Window\.window\.update\(\)' "$HERE/shell.qml") $(qa_count 'function onFrameSwapped\(\) \{ p\.frame\(\) \}' "$HERE/shell.qml") $(qa_count '^ *opacity: alpha \* \(Number\(k\.opacity\) >= 0 \? Number\(k\.opacity\) : 1\) \}\)$' "$HERE/shell.qml")"
  ck "S1 shell.qml's frame handler decides through HarnessLib.openDrawnSettle, samples through openDrawnSet over the visible area against the guide's rowCount (each delegate with its effective opacity), asks the window for the next frame and listens to its swaps" "$seam" "1 1 1 1 1 1"
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
# view, kind, summon, realised, drawn, built, changedAfter, method A or ping
record() { printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$@" >>"$SAMPLES"; }
rec_open() {   # rec_open <view> <kind> <result json>
  record "$1" "$2" "$(jf "['summonMs']" "$3")" "$(jf "['realisedMs']" "$3")" "$(jf "['count']" "$3")" "$(jf "['built']" "$3")" "$(jf "['changedAfter']" "$3")" "-"
}
measure_shell() {   # measure_shell <view> <shell-number>
  local view=$1 n=$2 res a k
  start_shell || { echo "   shell $n ($view) did not settle; no samples from it"; return 1; }
  # COLD: the first open this shell makes
  if res=$(async_open "$view"); then rec_open "$view" cold "$res"; else rec_open "$view" cold-unsettled "$res"; fi
  [[ $n == 1 ]] && COLD_RES=$res
  # WARM, interleaved with method A
  for ((k = 0; k < WARM; k++)); do
    if res=$(async_open "$view"); then rec_open "$view" warm "$res"; WARM_RES=$res; else rec_open "$view" warm-unsettled "$res"; fi
    a=$(method_a); record "$view" methodA - - - - - "$a"
    record "$view" ping - - - - - "$(ping_ms)"
  done
  stop_shell
}
# The figures one view's samples give, for the checks and the BUDGET line.
view_stat() {   # view_stat <view> <what>: warm-median | changed | unsettled
  python3 - "$SAMPLES" "$1" "$2" <<'PY'
import statistics, sys
rows = [l.rstrip("\n").split("\t") for l in open(sys.argv[1]) if l.strip()]
view, what = sys.argv[2], sys.argv[3]
def num(x):
    try: return float(x)
    except Exception: return None
opens = [r for r in rows if r[0] == view and r[1] in ("cold", "warm")]
if what == "warm-median":
    xs = [num(r[3]) for r in opens if r[1] == "warm" and num(r[3]) is not None and num(r[3]) >= 0]
    print("%.0f" % statistics.median(xs) if xs else "none")
elif what == "changed":
    print(sum(int(num(r[6]) or 0) for r in opens))
elif what == "unsettled":
    print(len([r for r in rows if r[0] == view and r[1].endswith("-unsettled")]))
PY
}

instrument
if [[ $MODE == check-tree ]]; then
  EXPECTED_CHECKS=18
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
    [[ $view == wall ]] && want=channelWall || want=resultList
    L=${view:0:1}; L=${L^^}
    for ((s = 1; s <= COLD; s++)); do
      COLD_RES=""; WARM_RES=""
      measure_shell "$view" "$s"
      if [[ $s == 1 ]]; then
        ck "${L}1 $view: the instrument ran to its end on the cold open, its tail included, and named the presenting view" "$(jf "['state']" "$COLD_RES") $(jf "['endedBy']" "$COLD_RES") $(jf "['view']" "$COLD_RES")" "done settled $want"
        ck "${L}2 $view: the cold open SETTLED (a frame whose drawn set tiles the visible area) and saw the guide's window" "$(jf "['settled']" "$COLD_RES") $(jf "['hasWindow']" "$COLD_RES")" "true true"
        ck "${L}3 $view: a warm open settled too" "$(jf "['settled']" "$WARM_RES")" "true"
        # Against the most the view held in the run, tail included, not at
        # the decision: a view may build its cacheBuffer rows a frame AFTER
        # the screen is drawn (late-fill.patch's run did), and the count is
        # right then too.
        ck "${L}4 $view: it counted the DRAWN screen -- more than 4 delegates, and fewer than the view built in the run (the cacheBuffer's off-screen ones are not counted)" "$(python3 -c 'import sys; c, b = int(sys.argv[1]), int(sys.argv[2]); print("yes" if 4 < c < b else "no:%d/%d" % (c, b))' "$(jf "['count']" "$COLD_RES")" "$(jf "['builtMax']" "$COLD_RES")" 2>/dev/null)" "yes"
        ck "${L}5 $view: the realised time is measured AFTER the summon returned (realised >= summon)" "$(python3 -c 'import sys; print("yes" if float(sys.argv[2]) >= float(sys.argv[1]) else "no")' "$(jf "['summonMs']" "$COLD_RES")" "$(jf "['realisedMs']" "$COLD_RES")" 2>/dev/null)" "yes"
        echo "   $view cold trace (ms:drawn/built:reason): $(python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(" ".join("%s:%s/%s:%s" % (f["at"], f["drawn"], f["built"], f["reason"] or "ok") for f in d.get("trace", [])[:20]))' "$COLD_RES" 2>/dev/null)"
        echo "   $view legacy openMs, cold, a shell of its own (printed, not graded): $(legacy_cold "$view")"
      fi
    done
    wm=$(view_stat "$view" warm-median)
    ck "${L}6 $view: the WARM open is within rule 7's budget -- the median realised time of the warm opens is under 150 ms" "$(python3 -c 'import sys; print("yes" if sys.argv[1] != "none" and float(sys.argv[1]) < 150 else "no:" + sys.argv[1])' "$wm" 2>/dev/null)" "yes"
    ck "${L}7 $view: in the 600 ms after every decision, cold and warm, nothing drawn changed (no view still filling after the instrument called it open), and every open settled" "changed:$(view_stat "$view" changed) unsettled:$(view_stat "$view" unsettled)" "changed:0 unsettled:0"
  done
  cage_stop
  echo "== samples (view, kind, summon, realised, drawn, built, changed after, method A or ping round trip; ms)"
  sed 's/^/   /' "$SAMPLES"
  echo "== results (ms; realised = the first frame whose drawn set tiles the visible area)"
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
    pings = [num(r[7]) for r in rows if r[0] == view and r[1] == "ping"]
    ping = statistics.median([p for p in pings if p is not None]) if pings else 0
    for kind in ("cold", "warm"):
        rs = [r for r in rows if r[0] == view and r[1] == kind]
        un = [r for r in rows if r[0] == view and r[1] == kind + "-unsettled"]
        print("  %-4s %-4s summon %s | realised %s | drawn %s | built %s | unsettled %d" % (view, kind,
              summary([num(r[2]) for r in rs]), summary([num(r[3]) for r in rs]), summary([num(r[4]) for r in rs]),
              summary([num(r[5]) for r in rs]), len(un)))
        real = [num(r[3]) for r in rs if num(r[3]) is not None and num(r[3]) >= 0]
        if real:
            verdict.append("%s %s median %.0f ms max %.0f ms: %s" % (view, kind, statistics.median(real), max(real),
                           "within 150 ms" if max(real) < 150 else ("median within, max over" if statistics.median(real) < 150 else "OVER 150 ms")))
    a = [num(r[7]) for r in rows if r[0] == view and r[1] == "methodA"]
    a = [x - ping for x in a if x is not None]
    # method A's difference can be negative: the round trip is mostly the
    # IPC client's own start, and the open's share sits inside its noise
    sa = ("n=%d median %.0f min %.0f max %.0f" % (len(a), statistics.median(a), min(a), max(a))) if a else "n=0"
    print("  %-4s PERF-02 method A (open round trip - median ping %.0f): %s" % (view, ping, sa))
print("BUDGET (rule 7, 150 ms, the realised time; the warm median is graded as L6/W6, the rest reported): " + "; ".join(verdict))
PY
  EXPECTED_CHECKS=32
fi
ran=$((PASS + FAIL))
if (( ran == EXPECTED_CHECKS )); then
  pass "the scenario ran every check it has ($ran)"
else
  fail "the scenario ran $ran checks, expected $EXPECTED_CHECKS" "one stopped executing"
fi
echo "== $PASS passed, $FAIL failed"
(( FAIL == 0 ))
