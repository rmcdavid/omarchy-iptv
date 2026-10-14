#!/bin/bash
# scripts/dev-harness/spikes/filewatch/measure.sh -- R23g (D-SINK-19 round
# 13): what does Quickshell's FileView do to its watch?
#
#   measure.sh [HELPER]     HELPER: the bin/omarchy-iptv whose `state` verb
#                           makes the atomic rename (default: this tree's)
#
# Runs shell.qml (one FileView declared as Service.qml's stateFile is) in a
# nested headless cage on a PRIVATE D-Bus (../../private-bus.sh, CLAUDE.md
# 6b), over a real state.json, and drives sequences of changes to the file
# from outside: the FileView's OWN save (setText over `qs ipc`), the
# helper's atomic rename (`state favorite add`, write_json_atomic), an
# external IN-PLACE write (bash `>`: O_TRUNC on the same inode), a chmod,
# an explicit reload(), and a restart of the shell. After each step it waits
# STEP_WAIT seconds and prints which signals the step raised and whether the
# view now holds the bytes on disk. Every sequence starts a fresh shell over
# a fresh file, so no step's effect leaks into another sequence.
#
# Holds no display and sends no key: everything lives on the display cage
# creates. Starts nothing it does not stop by recorded pid. The work
# directory is a short one under $XDG_RUNTIME_DIR, 0700, removed at exit.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../.." && pwd)
STEP_WAIT=${STEP_WAIT:-1.5}

if [[ ${1:-} == --child ]]; then
  # ------------------------------------------------------------ inside cage
  WORK=$2 HELPER=$3
  OUT=$WORK/result.txt
  QS_PID=""
  stop_qs() {
    local i
    [[ -n $QS_PID ]] || return 0
    kill -TERM "$QS_PID" 2>/dev/null
    for ((i = 0; i < 50; i++)); do kill -0 "$QS_PID" 2>/dev/null || break; sleep 0.1; done
    kill -0 "$QS_PID" 2>/dev/null && kill -KILL "$QS_PID" 2>/dev/null
    wait "$QS_PID" 2>/dev/null
    QS_PID=""
  }
  trap stop_qs EXIT
  ipc() { timeout 5 qs ipc -p "$WORK/cfg" call probe "$@" 2>/dev/null; }
  start_qs() {
    local i reply
    FVPROBE_FILE="$WORK/state/state.json" quickshell -p "$WORK/cfg" >>"$WORK/qs.log" 2>&1 &
    QS_PID=$!
    for ((i = 0; i < 100; i++)); do
      reply=$(ipc counts)
      [[ $reply == *'"loaded":1'* || $reply == *'"failed":1'* ]] && return 0
      sleep 0.1
    done
    echo "GAVE UP: the probe did not load within 10 s" >>"$OUT"
    return 1
  }
  fresh_file() {
    rm -rf "$WORK/state"
    mkdir -m 700 "$WORK/state"
    printf '{"version":2,"cacheLayout":0,"favorites":["t:seed"],"recents":[],"lastPlayed":null,"session":null,"sources":[],"savedSearches":[],"hiddenGroups":[],"activeKey":""}\n' >"$WORK/state/state.json"
    chmod 600 "$WORK/state/state.json"
  }
  N=0
  # A step written NAME! is not waited on: the next step follows at once,
  # the way a burst of saves or a damage straight after a save arrives.
  # The counts are taken before the FIRST step of a run of unwaited steps
  # and after the waited step that ends it, so the line printed for that
  # step reports what the whole burst raised.
  GROUP_BEFORE="" GROUP=""
  step() {
    local what=${1%!} wait=$STEP_WAIT before after
    [[ $1 == *! ]] && wait=0
    [[ -z $GROUP_BEFORE ]] && GROUP_BEFORE=$(ipc counts)
    before=$GROUP_BEFORE
    N=$((N + 1))
    case $what in
      own)      ipc save "{\"version\":2,\"favorites\":[\"t:own$N\"],\"sources\":[]}" >/dev/null ;;
      helper)   python3 -I "$HELPER" state --state-dir "$WORK/state" favorite add "t:helper$N" >/dev/null 2>&1 ;;
      inplace)  printf '{"version":2,"favorites":["t:inplace%s"],"sources":[]}\n' "$N" >"$WORK/state/state.json" ;;
      truncate) : >"$WORK/state/state.json" ;;
      chmod)    chmod 600 "$WORK/state/state.json" ;;
      reload)   ipc reload >/dev/null ;;
      restart)  stop_qs; start_qs || return 1; before='{"changed":0,"loaded":0,"failed":0,"saved":0,"saveFailed":0}' ;;
    esac
    sleep "$wait"
    if [[ $wait == 0 ]]; then GROUP="$GROUP$what+"; return 0; fi
    what="$GROUP$what"; GROUP="" GROUP_BEFORE=""
    after=$(ipc counts)
    python3 -I - "$what" "$before" "$after" "$WORK/state/state.json" >>"$OUT" <<'PY'
import json, sys
what, before, after, path = sys.argv[1], json.loads(sys.argv[2] or "{}"), json.loads(sys.argv[3] or "{}"), sys.argv[4]
d = {k: after.get(k, 0) - before.get(k, 0) for k in ("changed", "loaded", "failed", "saved", "saveFailed")}
try:
    disk = open(path, encoding="utf-8").read()
except OSError:
    disk = None
seen = after.get("text", "") == disk
print("  %-14s fileChanged+%d loaded+%d loadFailed+%d saved+%d saveFailed+%d  view==disk:%s"
      % (what, d["changed"], d["loaded"], d["failed"], d["saved"], d["saveFailed"], "yes" if seen else "NO"))
PY
  }
  sequence() {
    local name=$1 s
    shift
    echo "SEQ $name: $*" >>"$OUT"
    fresh_file
    start_qs || return
    for s in "$@"; do step "$s" || break; done
    stop_qs
  }
  mkdir -m 700 -p "$WORK/cfg"
  cp "$HERE/shell.qml" "$WORK/cfg/shell.qml"
  : >"$OUT"
  sequence A inplace inplace truncate inplace
  sequence B own inplace inplace
  sequence C helper inplace inplace
  sequence D own helper inplace
  sequence E chmod inplace inplace
  sequence F own reload inplace
  sequence G own inplace restart inplace inplace
  sequence H helper own inplace
  sequence I own own inplace
  sequence J own! own! own inplace inplace
  sequence K own! inplace inplace
  sequence L own! helper inplace
  sequence M chmod! own inplace inplace
  sequence N own! own inplace
  sequence O own! inplace! inplace inplace
  sequence P helper! inplace inplace
  echo "END" >>"$OUT"
  exit 0
fi

# ---------------------------------------------------------------- outside
HELPER=${1:-$ROOT/bin/omarchy-iptv}
RUNTIME=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
WORK=$(mktemp -d "$RUNTIME/omarchy-iptv-fw.XXXXXX") || exit 2
chmod 700 "$WORK"
cleanup() { rm -rf -- "$WORK"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
echo "filewatch: work $WORK, helper $HELPER, step wait ${STEP_WAIT}s, load $(cut -d' ' -f1-3 /proc/loadavg)"
env -u WAYLAND_DISPLAY -u DISPLAY WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1 \
  "$ROOT/scripts/dev-harness/private-bus.sh" "$WORK/bus" 240 \
  cage -- "$0" --child "$WORK" "$HELPER" >"$WORK/cage.log" 2>&1
status=$?
if [[ -s $WORK/result.txt ]]; then cat "$WORK/result.txt"; else echo "NO RESULT (cage exit $status)"; tail -n 20 "$WORK/cage.log"; fi
grep -c 'FVPROBE' "$WORK/qs.log" 2>/dev/null | sed 's/^/probe signal lines: /'
exit "$status"
